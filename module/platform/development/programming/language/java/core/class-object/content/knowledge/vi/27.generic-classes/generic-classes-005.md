# Tham số kiểu của lớp generic không dùng trực tiếp trong ngữ cảnh static — Java 17+

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích `class Box<T>` khai báo **tham số kiểu cấp lớp** `T`, có thể dùng trong instance field, constructor, instance method và một số nested contexts hợp lệ.
- Hiểu **static thuộc về class**, không thuộc riêng `Box<String>`, `Box<Integer>` hay một object cụ thể, vì các parameterizations chia sẻ cùng class runtime.
- Nhận diện compile-time errors khi dùng `T` của class trực tiếp trong **static field declaration**, **static method declaration/body**, **static initializer** hoặc **static nested class**.
- Phân biệt hai nguyên nhân: **class type parameter không có nghĩa trong static context** và **static context không có `this` hay instance members**; hai lỗi độc lập nhưng dễ xuất hiện cùng nhau.
- Viết static generic factory/helper bằng cách khai **type parameter riêng của method**: `static <U> Box<U> of(U value)`.
- Nắm rằng `<U>` đứng **trước return type**, không phải sau tên method; hiểu type inference và cách gọi explicit như `Box.<String>of("A")`.
- Nhận diện tên `T` khai lại trong method static là **method type parameter mới**, không phải cách “lấy” `T` cấp class; ưu tiên dùng `U` hoặc `R` để tránh che tên.
- Khai static constants/fields với types cụ thể như `int`, `String`, `List<?>`, `Box<?>`, hoặc static helpers có method-level generic parameters khi hợp lý.
- Phân biệt `Box.COUNT` hợp lệ với `Box<String>.COUNT` không hợp lệ theo rules static member qualification của parameterized types.
- Phân biệt **static nested class** không được dùng outer `T` và **non-static inner class** có thể dùng outer `T` do gắn với một enclosing instance/parameterization.
- Tránh nhầm việc không thể viết `T.class`, `new T()`, `new T[10]`, `instanceof T` với lỗi chỉ do static: đây còn là các giới hạn liên quan type erasure/reifiability ngay cả trong instance methods.
- Áp dụng generic type tokens `Class<T>` khi cần runtime type information, thay vì kỳ vọng type parameter tồn tại như một runtime Class literal.
- Thiết kế static count/cache/registry không giả định có một bản static state cho mỗi parameterization, và nhận diện rủi ro shared mutable state/concurrency.
- Sử dụng bounded generic static methods, generic static factories, wildcards và generic instance APIs đúng chỗ.
- Tự biên dịch các ví dụ Java 17+, so sánh stdout chính xác, tự làm bài tập và phân biệt code cố tình sai với chương trình runnable.

> **Phạm vi:** Bài chỉ tập trung vào **quy tắc dùng tham số kiểu của lớp trong static contexts của Java generic class**, cùng cơ chế và cách khắc phục cần thiết. Các demo đầy đủ sử dụng JDK 17 trở lên. Ví dụ lỗi biên dịch được đánh dấu và thường comment để không làm hỏng các demo có thể chạy.

## 1. Trực giác: `T` là mô tả kiểu **của instance**, không phải kiểu riêng cho phần static

Một generic class:

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

Ví dụ dùng:

~~~java
Box<String> text = new Box<>("hello");
Box<Integer> number = new Box<>(42);
~~~

Ở source code, compiler hiểu:

- `text.get()` có compile-time return type `String`.
- `number.get()` có compile-time return type `Integer`.
- Trong instance methods của `Box<T>`, `T` có thể dùng làm field type, method result/parameter type.
- Nhưng `Box<String>` và `Box<Integer>` **không phải hai class runtime độc lập** tạo ra hai nhóm static members riêng.

Một instance có **type argument theo compile-time view**. Static member gắn với generic class declaration như một **class-level member**.

Nếu cố tạo một static field có kiểu `T`:

~~~java
class Box<T> {
    // static T shared; // Không hợp lệ.
}
~~~

Java không có một `T` xác định để dùng ở thời điểm static member được khai báo: `T` của `Box<String>` hay `T` của `Box<Integer>`? Cả hai parameterizations cùng định nghĩa **một class**, không có storage static theo từng type argument.

Đó là trực giác; **quy tắc ngôn ngữ chính thức** được mô tả ở JLS `6.5.5.1 và `8.1.2: tham chiếu đến type parameter của generic class bị hạn chế trong static context.

## 2. Bảng phân biệt phạm vi dùng tham số kiểu

| Vị trí trong `class Box<T>` | Dùng `T` cấp lớp trực tiếp? | Ví dụ |
| --- | --- | --- |
| Instance field | **Có** | `private T value;` |
| Constructor instance | **Có** | `Box(T value)` |
| Instance method signature/body | **Có** | `T get()`, `void set(T x)` |
| Instance field initializer | **Có**, nếu code hợp lệ | `List<T> items = new ArrayList<>();` |
| Static field declaration | **Không** | `static T cached;` sai |
| Static method signature/body | **Không** | `static T id(T x)` sai |
| Static initializer | **Không** | `static { T x = ...; }` sai |
| Static nested class | **Không** | `static class Node { T x; }` sai |
| Static method có riêng `<U>` | **Có thể dùng U**, không dùng outer T | `static <U> Box<U> of(U x)` |
| Static nested class có riêng `<U>` | **Có thể dùng U**, không dùng outer T | `static class Node<U> { U x; }` |
| Non-static inner class | **Có** | `class Cell { T value; }` |
| Static field với wildcard/type cố định | **Có** | `static Box<?> empty;` hoặc `static int count;` |
| `T.class` | **Không** | Không hợp lệ ngay cả trong instance method |

Từ “static context” không chỉ là một method có keyword `static`. Nó bao gồm các vị trí được đặc tả như static field initializers, static initializer blocks và body của static methods; static nested types có rules riêng do không gắn với enclosing instance.

### 2.1. Hai điều “không có” khác nhau

Trong static method của generic class:

1. **Không có enclosing instance `this`** của `Box`. Do đó gọi instance method `get()` không receiver hoặc đọc instance field `value` trực tiếp là sai.
2. **Không được dùng class-level type parameter `T`** như một type name trong static context. Dù không đụng đến `this`, signature `static T copy(T x)` vẫn sai.

Sửa hai lỗi bằng hai cách khác nhau: truyền **object** nếu cần instance state; khai **method type parameter mới** nếu cần generic type cho utility/factory.

## 3. Chương trình 1: instance field hợp lệ, static counter dùng chung

Lưu **`GenericStaticCounterDemo.java`**:

~~~java
public class GenericStaticCounterDemo {
    static class Box<T> {
        private static int constructed;
        private final T value;

        Box(T value) {
            this.value = value;
            constructed++;
        }

        T value() {
            return value;
        }

        static int constructedCount() {
            return constructed;
        }
    }

    public static void main(String[] args) {
        Box<String> first = new Box<>("Java");
        Box<Integer> second = new Box<>(17);

        System.out.println("first=" + first.value());
        System.out.println("second=" + second.value());
        System.out.println("counter=" + Box.constructedCount());
        System.out.println("same class=" +
                (first.getClass() == second.getClass()));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericStaticCounterDemo.java
java GenericStaticCounterDemo
~~~

**Stdout:**

~~~text
first=Java
second=17
counter=2
same class=true
~~~

### 3.1. Vì sao kết quả như vậy?

- Hai calls `new Box<>(...)` tạo **hai objects** khác nhau.
- `value` là field riêng mỗi object, có compile-time type phù hợp cho mỗi parameterization.
- `constructed` là **một static int** gắn với runtime Box class. Cả hai constructor calls tăng **cùng counter**.
- `first.getClass() == second.getClass()` là true vì runtime class của cả hai objects là cùng declaration Box.
- `Box.constructedCount()` được gọi bằng **generic class name**, không dùng `Box<String>.constructedCount()`.

**Lưu ý:** static counter ví dụ chưa thread-safe: `constructed++` không atomic. Code đa luồng cần `AtomicInteger`/synchronization nếu thật sự muốn đếm chính xác. Điều này độc lập với generic typing.

## 4. Những khai báo static dùng outer `T` bị compiler từ chối

Giả sử:

~~~java
class Repository<T> {
    private T current;

    // static T cached;             // Sai: static field type.
    // static java.util.List<T> xs; // Sai: T trong static field type.
    // static T getCached() {       // Sai: static return type.
    //     return null;
    // }
    // static void put(T value) { } // Sai: static parameter type.

    T getCurrent() {               // Đúng: instance method.
        return current;
    }

    void setCurrent(T value) {      // Đúng: instance method.
        current = value;
    }
}
~~~

Các dòng lỗi đều được comment; đây là **snippet**, không phải file runnable có main.

**Kết luận:** outer `T` xuất hiện trong bất kỳ vị trí type tương ứng của static field/static method cũng bị cấm, kể cả khi static method body không truy cập dữ liệu.

### 4.1. Một câu hỏi dễ nhầm

> “Nếu tôi chỉ viết `static T identity(T x) { return x; }`, không dùng field, sao vẫn sai?”

Vì ký hiệu `T` đang **trỏ tới type parameter của generic class**, và vị trí khai báo static method không được tham chiếu nó. Muốn có hàm generic độc lập thì phải khai type parameter **riêng của method**: `static <U> U identity(U x)`.

## 5. Static generic method có **tham số kiểu riêng**

Cú pháp quan trọng:

~~~java
static <U> U identity(U input) {
    return input;
}
~~~

`<U>` phải xuất hiện **sau các modifiers (`static`, `public` nếu có)** và **trước return type**. `U` là type parameter của **method**, được tạo ra theo **khai báo method**, không phải một cách “với tới” outer T.

So sánh:

~~~java
class Box<T> {
    T instanceEcho(T x) {
        return x;
    }

    // static T wrong(T x) { return x; } // Sai, outer T.

    static <U> U staticEcho(U x) {
        return x;
    }
}
~~~

### 5.1. Scope và shadowing

Java cho phép một method generic khai tên `<T>` giống outer `T` trong một số trường hợp scope hợp lệ; lúc ấy **method T shadow outer T**. Dù viết trùng tên, chúng là hai declarations **khác nhau**. Ví dụ để tránh nhầm lẫn thường dùng `<U>`, `<R>` hoặc một ký hiệu có ý nghĩa như `<E>` cho element.

### 5.2. Không cần một Box instance để gọi

Static method generic có thể được dùng như `Box.staticEcho("A")`. Compiler suy `U = String` ở invocation tương ứng; gọi `Box.staticEcho(10)` thì `U = Integer`. Đó không phải outer class parameterization `Box<String>` hay `Box<Integer>`.

## 6. Chương trình 2: static generic utility độc lập với outer `T`

Lưu **`GenericStaticMethodDemo.java`**:

~~~java
public class GenericStaticMethodDemo {
    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T value() {
            return value;
        }

        static <U> U echo(U input) {
            return input;
        }

        static <U> String label(U input) {
            return "value=" + input;
        }
    }

    public static void main(String[] args) {
        String text = Box.echo("Java");
        Integer number = Box.echo(17);

        System.out.println("text=" + text);
        System.out.println("number=" + number);
        System.out.println(Box.label(true));

        Box<Long> instance = new Box<>(5L);
        System.out.println("instance=" + instance.value());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericStaticMethodDemo.java
java GenericStaticMethodDemo
~~~

Output:

~~~text
text=Java
number=17
value=true
instance=5
~~~

- `echo` và `label` có **method-owned `U`**.
- `Box<Long> instance` giữ outer type parameter Long trong instance methods.
- Không phải vì `instance` là Box<Long> mà `echo` bị giới hạn dùng Long.
- Mọi calls `Box.echo(...)` là static method calls trên class Box.

### 6.1. Explicit type argument cho static generic method

Có thể chỉ rõ type argument của method:

~~~java
String s = Box.<String>echo("Java");
Integer n = Box.<Integer>echo(17);
~~~

Đây là snippet đặt trong code có Box khai method echo phù hợp. `Box.<String>echo(...)` chỉ định **U của echo**, không tạo parameterization class `Box<String>`.

## 7. Static factory cho generic class: `static <U> Box<U> of(U value)`

Mẫu API thường gặp:

~~~java
class Box<T> {
    private final T value;

    private Box(T value) {
        this.value = value;
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
~~~

**Đọc đúng chữ ký:**

- `static`: method thuộc Box class.
- `<U>`: method tự khai type variable U.
- `Box<U>`: return type là Box parameterized bằng **method U**.
- `of(U value)`: input cùng U.
- `new Box<>(value)`: compiler infer type argument phù hợp.

**Không đúng:**

~~~java
// static Box<T> of(T value) { return new Box<>(value); }
// Không thể dùng outer T trong static signature/body.
~~~

### 7.1. Vì sao factory cần type parameter riêng?

Ở thời điểm caller gọi `Box.of("abc")`, compiler infer `U = String`, return type `Box<String>`. Lần caller gọi `Box.of(100)`, U = Integer, return type `Box<Integer>`. **Một method declaration** được dùng theo hai compile-time type instantiations; không có “factory riêng cho Box<String>” trong class runtime.

## 8. Chương trình 3: factory với type inference

Lưu **`GenericFactoryDemo.java`**:

~~~java
public class GenericFactoryDemo {
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
        Box<String> first = Box.of("ready");
        Box<Integer> second = Box.of(42);
        Box<Number> third = Box.<Number>of(3.5);

        System.out.println("first=" + first.get());
        System.out.println("second=" + second.get());
        System.out.println("third=" + third.get());
        System.out.println("runtime same=" +
                (first.getClass() == second.getClass()));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericFactoryDemo.java
java GenericFactoryDemo
~~~

Output:

~~~text
first=ready
second=42
third=3.5
runtime same=true
~~~

`Box.<Number>of(3.5)` là **explicit method type argument** để U = Number; `3.5` autobox thành Double và có thể được truyền khi method parameter type là Number.

`Box.of` là tên dễ đọc cho static factory, không dùng dấu `<String>` gắn vào class name để truy cập static.

## 9. Static method không có `this`

Một lỗi khác static ≠ instance:

~~~java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    // static Object wrong() {
    //     return this.value;   // Sai: không có this trong static method.
    // }

    // static Object alsoWrong() {
    //     return get();       // Sai: instance method thiếu receiver.
    // }
}
~~~

Ngay cả nếu đổi field thành `Object value` thay vì `T value`, static method vẫn **không có receiver** để đọc field ấy trực tiếp.

### 9.1. Cách sửa nếu cần instance state

Truyền một **instance** vào static method; dùng wildcard nếu helper không cần biết argument type:

~~~java
static Object readAsObject(Holder<?> source) {
    return source.get();
}
~~~

`Holder<?>` là một reference type hợp lệ trong static method signature vì nó **không tham chiếu outer class type parameter T**. Helper nhận một object cụ thể rồi gọi instance method `get()` qua receiver `source`.

Nếu muốn type safety giữ đúng type của input, dùng method-owned U:

~~~java
static <U> U read(Holder<U> source) {
    return source.get();
}
~~~

## 10. Chương trình 4: truyền receiver cho static helper

Lưu **`GenericStaticReceiverDemo.java`**:

~~~java
public class GenericStaticReceiverDemo {
    static class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        static Object asObject(Holder<?> source) {
            return source.get();
        }

        static <U> U read(Holder<U> source) {
            return source.get();
        }
    }

    public static void main(String[] args) {
        Holder<String> text = new Holder<>("Hello");
        Holder<Integer> number = new Holder<>(10);

        String keptString = Holder.read(text);
        Integer keptNumber = Holder.read(number);

        System.out.println("text=" + keptString);
        System.out.println("number=" + keptNumber);
        System.out.println("object=" + Holder.asObject(text));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericStaticReceiverDemo.java
java GenericStaticReceiverDemo
~~~

Output:

~~~text
text=Hello
number=10
object=Hello
~~~

Mặc dù helper là static, nó có thể đọc dữ liệu **của object được truyền vào**, không phải một `this` ngầm. `Holder.read` dùng U riêng của method nên kết quả giữ compile-time type của source.

## 11. Static field nên dùng type nào?

Các mẫu hợp lệ:

~~~java
class Registry<T> {
    private static int count;
    private static final String VERSION = "1";
    private static final java.util.List<?> EMPTY =
            java.util.List.of();
    private static final java.util.Map<String, Integer> CODES =
            java.util.Map.of("OK", 200);

    // private static T last;            // Sai.
    // private static java.util.List<T> cache; // Sai.
}
~~~

`List<?>` mô tả một list có element type không biết trong static declaration. `Map<String,Integer>` mô tả static map với **concrete type arguments**, không dùng T của Registry.

Static fields không “thay đổi kiểu” theo parameterizations. `Registry<String>.last` và `Registry<Integer>.last` không phải hai stores có type-safe separation.

### 11.1. Khi nào wildcard là đúng?

Nếu static field thật sự chứa **heterogeneous generic instances** mà caller chỉ cần xem dữ liệu qua safe API, `List<Box<?>>` có thể là representation phù hợp. Không thể vì `Box<?>` chấp nhận nhiều concrete parameterizations mà suy được chúng đều là `Box<T>` của current object; wildcard diễn đạt **unknown element type**.

### 11.2. Nếu cần collection empty theo từng type

Thay vì lưu `static final List<T> EMPTY` (sai), static generic factory có thể trả empty list với U độc lập:

~~~java
static <U> java.util.List<U> emptyList() {
    return java.util.List.of();
}
~~~

`List.of()` là một static generic factory của library với phù hợp type inference; không cần tạo mutable static List<T> field riêng.

## 12. Chương trình 5: static constant, wildcard và generic empty factory

Lưu **`GenericStaticCollectionsDemo.java`**:

~~~java
import java.util.List;

public class GenericStaticCollectionsDemo {
    static class Store<T> {
        private static final List<?> EMPTY = List.of();

        static int emptySize() {
            return EMPTY.size();
        }

        static <U> List<U> emptyList() {
            return List.of();
        }
    }

    public static void main(String[] args) {
        List<String> words = Store.emptyList();
        List<Integer> numbers = Store.emptyList();

        System.out.println("words size=" + words.size());
        System.out.println("numbers size=" + numbers.size());
        System.out.println("static empty=" + Store.emptySize());

        System.out.println("words add supported=" +
                canAddWord(words));
    }

    static boolean canAddWord(List<String> list) {
        try {
            list.add("X");
            return true;
        } catch (UnsupportedOperationException expected) {
            return false;
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericStaticCollectionsDemo.java
java GenericStaticCollectionsDemo
~~~

Output:

~~~text
words size=0
numbers size=0
static empty=0
words add supported=false
~~~

Một method-owned U cho phép `Store.emptyList()` trả List<String>/List<Integer> trong các target contexts khác nhau. `List.of()` trả unmodifiable List, nên cố add ném `UnsupportedOperationException`.

**Không nhầm:** `EMPTY` là một static List<?> an toàn về declaration; Java không bảo đảm luôn tạo object mới khi gọi `List.of()`, và ở bài này cũng không cần điều đó.

## 13. Static initializer cũng không có outer `T`

Static initializer chạy khi **class initialization** diễn ra, không chạy theo từng `Box<String>` hay `Box<Integer>`. Trong initializer này, outer class type parameter không được dùng như một type name.

~~~java
class Example<T> {
    private static int initialized;

    static {
        initialized = 1;
        // T value = null; // Sai: class T trong static context.
    }

    static int status() {
        return initialized;
    }
}
~~~

Nếu block cần xử lý type-specific dữ liệu, nó không có một T cụ thể để quyết định. Tốt hơn là:

- Dùng concrete static metadata độc lập với T.
- Truyền type token hay object vào **method** lúc runtime.
- Đặt per-instance data ở instance fields.
- Nếu cần generic processing, dùng static method type parameters riêng.

### 13.1. Thứ tự initialization

Class initialization chỉ diễn ra theo JVM class init rules. Static fields/blocks không được tạo lại mỗi khi lập một parameterization khác. Constructor chạy **mỗi lần tạo object**, còn static initializer chạy theo class initialization lifecycle.

## 14. Chương trình 6: static block một lần cho nhiều parameterizations

Lưu **`GenericStaticInitDemo.java`**:

~~~java
public class GenericStaticInitDemo {
    static class Box<T> {
        private static int sequence;

        static {
            System.out.println("Box static initialized");
        }

        private final int id;
        private final T value;

        Box(T value) {
            this.value = value;
            id = ++sequence;
            System.out.println("constructed " + id);
        }

        int id() {
            return id;
        }

        T value() {
            return value;
        }
    }

    public static void main(String[] args) {
        System.out.println("before");
        Box<String> first = new Box<>("A");
        Box<Integer> second = new Box<>(2);

        System.out.println("first=" + first.id() + ":" + first.value());
        System.out.println("second=" + second.id() + ":" + second.value());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericStaticInitDemo.java
java GenericStaticInitDemo
~~~

Output:

~~~text
before
Box static initialized
constructed 1
constructed 2
first=1:A
second=2:2
~~~

Trong một JVM mới, static initializer in **một lần** khi Box lần đầu được initialized. `sequence` tăng qua cả hai objects, dù type arguments khác nhau. Nếu constructors chạy đa luồng, `++sequence` cần synchronization/atomic counter để đảm bảo ID duy nhất; ví dụ chủ ý single-thread.

## 15. Static nested class không capture outer generic `T`

Một generic outer class:

~~~java
class Container<T> {
    static class Slot<U> {
        U value;
    }

    class Inner {
        T value;
    }
}
~~~

- `Slot<U>` là **static nested class**: không có enclosing `Container<T>` instance, nên **không được trực tiếp dùng outer T** trong declaration/body.
- Nó có thể tự khai một **type parameter U** trên chính Slot.
- `Inner` là **non-static inner class**: gắn với một enclosing Container<T> instance, nên có thể dùng outer T.
- Kể cả trong `Slot` có instance method, nó vẫn **không** vì thế nhìn thấy outer T. Đây là lỗi thường gặp: chữ “instance” của Slot không phải instance của Container.

Sai:

~~~java
class Container<T> {
    static class Wrong {
        // T field; // Compile-time error: outer T không usable.
    }
}
~~~

Đúng:

~~~java
class Container<T> {
    static class Slot<U> {
        U field;
    }
}
~~~

### 15.1. Type parameters của nested class khác outer class

`Container.Slot<Integer>` dùng U=Integer. Nó **không** dùng T của `Container<String>`. Static nested classes không gắn generic parameterization của enclosing class vào tên type khi truy cập.

## 16. Chương trình 7: static nested và non-static inner

Lưu **`GenericNestedClassesDemo.java`**:

~~~java
public class GenericNestedClassesDemo {
    static class Envelope<T> {
        private final T item;

        Envelope(T item) {
            this.item = item;
        }

        class Inner {
            T readOuter() {
                return item;
            }
        }

        static class Slot<U> {
            private final U value;

            Slot(U value) {
                this.value = value;
            }

            U value() {
                return value;
            }
        }
    }

    public static void main(String[] args) {
        Envelope<String> envelope = new Envelope<>("hello");
        Envelope<String>.Inner inner = envelope.new Inner();

        Envelope.Slot<Integer> slot =
                new Envelope.Slot<>(17);

        System.out.println("inner=" + inner.readOuter());
        System.out.println("slot=" + slot.value());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericNestedClassesDemo.java
java GenericNestedClassesDemo
~~~

Output:

~~~text
inner=hello
slot=17
~~~

### 16.1. Lý do cú pháp khác nhau

`Envelope<String>.Inner` là inner type gắn với `Envelope<String>`; expression `envelope.new Inner()` cung cấp enclosing instance.

`Envelope.Slot<Integer>` là static nested type, truy cập qua **raw outer class name dùng như qualifier**, không qua một instance và không gắn type argument String của outer Envelope.

**Không viết** `Envelope<String>.Slot<Integer>`: static member type của generic class không được qualified bằng parameterized outer type.

## 17. Nested record và nested enum cũng ngầm static

Java 17 quy định member/local record và enum có static semantics đặc thù. Một **member record** trong generic class:

~~~java
class Table<T> {
    record Row<U>(U value) {
    }

    // record Invalid(T value) {} // Sai: không dùng outer T trực tiếp.
}
~~~

`Row<U>` tự khai U riêng. Nó không capture một Table<T> instance và không có field lưu outer T mặc định.

Một **member enum** cũng implicitly static, không dùng outer type parameter T trực tiếp trong body. Enum không được khai generic type parameters riêng như `enum E<T>`, nên nếu cần stored state generic theo caller, enum không thay thế được generic class/record.

### 17.1. Chương trình 8: nested record có generic riêng

Lưu **`GenericNestedRecordDemo.java`**:

~~~java
public class GenericNestedRecordDemo {
    static class Table<T> {
        record Row<U>(U value, int index) {
        }
    }

    public static void main(String[] args) {
        Table.Row<String> first = new Table.Row<>("A", 0);
        Table.Row<Integer> second = new Table.Row<>(20, 1);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("same row class=" +
                (first.getClass() == second.getClass()));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericNestedRecordDemo.java
java GenericNestedRecordDemo
~~~

Output:

~~~text
first=Row[value=A, index=0]
second=Row[value=20, index=1]
same row class=true
~~~

`Table.Row` không cần `new Table<?>` trước. Hai parameterizations của static nested record Row vẫn chia sẻ runtime Row class; chính Row instances chứa U values khác nhau.

## 18. Type erasure giải thích vì sao static state không chuyên biệt theo T

Java generics sử dụng **type erasure**. Ví dụ:

~~~java
Box<String> text = new Box<>("A");
Box<Integer> number = new Box<>(1);
~~~

Type checking của `Box<String>`/`Box<Integer>` xảy ra lúc compile. Khi chạy, cùng một generic class declaration Box được JVM dùng cho hai objects (cùng defining class loader). JVM không tạo một class BoxOfString và BoxOfInteger với static storage riêng.

Những khác biệt về `String` và `Integer` vẫn có ý nghĩa compile-time rất lớn: compiler ngăn truyền Box<Integer> đến API đòi Box<String>, và có thể sinh casts phù hợp sau erasure. Nhưng **runtime class identity** không phụ thuộc generic type arguments đó.

### 18.1. Đừng suy rằng generic T luôn là Object

Nếu `class Numeric<T extends Number>`, erasure của T là bound đầu `Number` thay vì lúc nào cũng Object. Vì vậy không nên mô tả generic erasure như “mọi T biến thành Object”. Quy tắc static type parameter không khả dụng vẫn đúng, bất kể bound.

### 18.2. Static fields lưu ở đâu?

Về mặt semantic, static fields thuộc một runtime class, không thuộc từng instance. JVM initialization/field layout chi tiết là implementation concern; đừng giả định tệp class khác nhau cho mỗi parameterized type.

## 19. Chương trình 9: type erasure và class identity

Lưu **`GenericErasureStaticDemo.java`**:

~~~java
public class GenericErasureStaticDemo {
    static class Pair<T> {
        private static int total;
        private final T value;

        Pair(T value) {
            this.value = value;
            total++;
        }

        T value() {
            return value;
        }

        static int total() {
            return total;
        }
    }

    public static void main(String[] args) {
        Pair<String> a = new Pair<>("A");
        Pair<Double> b = new Pair<>(2.5);

        System.out.println("same runtime type=" +
                (a.getClass() == b.getClass()));
        System.out.println("shared total=" + Pair.total());
        System.out.println("a=" + a.value());
        System.out.println("b=" + b.value());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericErasureStaticDemo.java
java GenericErasureStaticDemo
~~~

Output:

~~~text
same runtime type=true
shared total=2
a=A
b=2.5
~~~

Lại thấy static state chung cho hai parameterizations. Đây là **một class runtime**, hai objects với khác compile-time generic views.

## 20. Không qualifier static member bằng parameterized class name

Sai trong Java source:

~~~java
// int count = Pair<String>.total();
//              ^^^^^^^^^^^^ không được dùng
// parameterized type để qualified static member.
~~~

Đúng:

~~~java
int count = Pair.total();
~~~

Hai dòng là snippets với `Pair` có static method `total()` hợp lệ. JLS `4.5.2 quy định static member khai trong generic type được tham chiếu qua **generic class/interface name**, không qua parameterized type.

Điều tương tự áp dụng cho:

- Static field `Box.COUNT`.
- Static method `Box.of(...)`.
- Static nested type `Box.Nested<U>`.
- Không viết `Box<String>.COUNT` hoặc `Box<String>.of(...)`.
- Không cần một instance để truy cập static member; dù Java có một số dạng access qua expression, cách đó làm người đọc dễ hiểu nhầm và thường có cảnh báo từ IDE.

**Chú ý đặc biệt:** `Box.<String>of(...)` **khác** `Box<String>.of(...)`. Dấu type arguments **sau dấu chấm, trước method name** là explicit **generic method invocation**; type arguments **gắn vào class name** là parameterized outer type, không hợp lệ khi qualifying static member.

## 21. Class type parameter với runtime `Class<T>`

Một lỗi khác:

~~~java
class TypeBox<T> {
    // Class<T> không thể khai thành static field theo outer T.
    // static Class<T> TOKEN; // Sai.

    // T.class cũng sai, vì T không phải reifiable type.
}
~~~

### 21.1. `T.class` không được, kể cả ở instance method

~~~java
class TypeBox<T> {
    // Class<?> rawType() {
    //     return T.class; // Compile-time error.
    // }
}
~~~

Lý do không phải chỉ là static/instance; type variable T không có class literal phù hợp dưới type erasure.

### 21.2. Truyền explicit `Class<T>` token

Cách điển hình:

~~~java
class TypedBox<T> {
    private final Class<T> type;

    TypedBox(Class<T> type) {
        this.type = type;
    }

    T cast(Object input) {
        return type.cast(input);
    }
}
~~~

Caller truyền `String.class` khi tạo `TypedBox<String>`, giúp runtime biết expected raw Class type. Nhưng token `Class<T>` **không giữ tất cả generic type arguments** của các cấu trúc nested như `List<String>` do `List.class` không biểu diễn parameterized type chi tiết.

## 22. Chương trình 10: generic static factory và type token

Lưu **`GenericTypeTokenDemo.java`**:

~~~java
public class GenericTypeTokenDemo {
    static final class TypeBox<T> {
        private final Class<T> type;

        private TypeBox(Class<T> type) {
            this.type = type;
        }

        static <U> TypeBox<U> of(Class<U> type) {
            return new TypeBox<>(type);
        }

        T cast(Object input) {
            return type.cast(input);
        }

        String typeName() {
            return type.getSimpleName();
        }
    }

    public static void main(String[] args) {
        TypeBox<String> strings = TypeBox.of(String.class);
        TypeBox<Integer> integers = TypeBox.of(Integer.class);

        System.out.println("string type=" + strings.typeName());
        System.out.println("integer type=" + integers.typeName());
        System.out.println("cast string=" + strings.cast("ready"));
        System.out.println("cast integer=" + integers.cast(17));

        try {
            integers.cast("not an integer");
        } catch (ClassCastException expected) {
            System.out.println("wrong type rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericTypeTokenDemo.java
java GenericTypeTokenDemo
~~~

Output:

~~~text
string type=String
integer type=Integer
cast string=ready
cast integer=17
wrong type rejected
~~~

Static factory `TypeBox.of(Class<U>)` tự có `<U>`, còn mỗi object lưu `Class<T> type` như **instance field**. `Class.cast` kiểm tra runtime raw class khi cần, không dùng `T.class`.

## 23. `new T()`, `T[]` và `instanceof T` không phải cách sửa static restriction

Đôi khi người mới nghĩ: “Dùng T trong static không được thì chuyển method thành instance rồi `new T()` thôi.” Vẫn sai theo rules khác.

~~~java
class Example<T> {
    // T create() {
    //     return new T(); // Không hợp lệ do erasure/type variable.
    // }

    // T[] createArray() {
    //     return new T[10]; // Không hợp lệ: generic array creation.
    // }

    // boolean matches(Object input) {
    //     return input instanceof T; // Không hợp lệ: T không reifiable.
    // }
}
~~~

`T` usable làm field/parameter/return type ở instance context, **nhưng** không phải mọi operation cần runtime concrete type đều hợp lệ với T.

**Các hướng khắc phục:**

- Truyền `Supplier<T>` nếu cần tạo values bằng factory.
- Truyền `Class<T>` và dùng `type.cast(...)` khi runtime raw type check đủ.
- Dùng collection `List<T>` thay generic array nếu thuật toán cho phép.
- Dùng `instanceof Box<?>` đối với wildcard-reifiable type thay vì `instanceof Box<String>` khi generic parameterization không reifiable.

### 23.1. Không trộn hai loại lỗi

| Code | Tại sao sai? |
| --- | --- |
| `static T x;` | Outer T không usable trong static context |
| `static T copy(T x)` | Outer T không usable ở static method signature |
| `static Object f() { return this; }` | Static method không có `this` |
| `static Object f() { return value; }` | Instance field cần receiver |
| `T.class` trong instance method | Class literal yêu cầu reifiable type; type variable không thỏa |
| `new T()` trong instance method | Không thể trực tiếp instantiate type variable |
| `new T[10]` | Generic array creation restriction |
| `input instanceof T` | Type variable không reifiable |
| `Box<String>.count` | Static member không qualified bằng parameterized type |
| `static <U> U copy(U x)` | **Hợp lệ**, U thuộc generic method |

Hiểu nguyên nhân giúp sửa đúng chỗ, thay vì đổi ngẫu nhiên static/instance.

## 24. Bounded generic class và bounded static method

Một generic class có bound:

~~~java
class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double doubleValue() {
        return value.doubleValue();
    }

    // static T zero() { ... } // Vẫn sai.
}
~~~

`T extends Number` không tạo ra một “một T cố định” cho static member. Bounded type parameter của **class** vẫn không usable trong static context.

Một static method có thể khai **own bounded type variable**:

~~~java
static <N extends Number> double twice(N number) {
    return number.doubleValue() * 2;
}
~~~

`N` thuộc method và có bound Number, do đó code được gọi `doubleValue()`.

## 25. Chương trình 11: bounded generic static method

Lưu **`GenericStaticBoundDemo.java`**:

~~~java
public class GenericStaticBoundDemo {
    static class NumericBox<T extends Number> {
        private final T number;

        NumericBox(T number) {
            this.number = number;
        }

        double instanceValue() {
            return number.doubleValue();
        }

        static <N extends Number> double twice(N input) {
            return input.doubleValue() * 2.0;
        }
    }

    public static void main(String[] args) {
        NumericBox<Integer> first = new NumericBox<>(7);
        NumericBox<Double> second = new NumericBox<>(2.5);

        System.out.println("first=" + first.instanceValue());
        System.out.println("second=" + second.instanceValue());
        System.out.println("twice 7=" + NumericBox.twice(7));
        System.out.println("twice 2.5=" + NumericBox.twice(2.5));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericStaticBoundDemo.java
java GenericStaticBoundDemo
~~~

Output:

~~~text
first=7.0
second=2.5
twice 7=14.0
twice 2.5=5.0
~~~

`N extends Number` là **method-owned N**, không phải outer `T extends Number`. Tại mỗi invocation, compiler infer N hợp lệ.

## 26. Generic static methods nhiều type parameters

Một static method có thể khai `<K, V>` để trả cặp giá trị:

~~~java
static <K, V> Pair<K, V> pair(K key, V value) {
    return new Pair<>(key, value);
}
~~~

Outer class `Factory<T>` nếu có vẫn không liên quan đến K/V của static method.

### 26.1. Chương trình 12: pair factory

Lưu **`GenericStaticPairFactoryDemo.java`**:

~~~java
public class GenericStaticPairFactoryDemo {
    record Pair<K, V>(K key, V value) {
    }

    static class Factory<T> {
        static <K, V> Pair<K, V> pair(K key, V value) {
            return new Pair<>(key, value);
        }
    }

    public static void main(String[] args) {
        Pair<String, Integer> age = Factory.pair("Lan", 20);
        Pair<Integer, String> code = Factory.pair(200, "OK");

        System.out.println("age=" + age);
        System.out.println("code=" + code);
        System.out.println("key=" + age.key());
        System.out.println("value=" + code.value());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericStaticPairFactoryDemo.java
java GenericStaticPairFactoryDemo
~~~

Output:

~~~text
age=Pair[key=Lan, value=20]
code=Pair[key=200, value=OK]
key=Lan
value=OK
~~~

`Pair<K,V>` là một generic record với own type parameters, còn `Factory<T>` không mang type information cho static `pair`. Factory static method vẫn trả strongly typed Pair.

## 27. Generic interface cũng có giới hạn static tương tự

Không chỉ generic classes: generic interfaces có type parameters cấp interface.

~~~java
interface Converter<T> {
    T convert(String input);

    // static T wrong(String s) { return null; }
    // Sai: static method của generic interface không dùng outer T.
}
~~~

Một static method của interface có thể có type parameter riêng:

~~~java
interface Converter<T> {
    T convert(String input);

    static <U> U identity(U value) {
        return value;
    }
}
~~~

Với interface, fields luôn implicitly `public static final`, nên không thể có interface field kiểu outer T trực tiếp. Static interface methods cũng không được inherit như instance methods qua implementing classes.

### 27.1. Chương trình 13: interface instance + generic static helper

Lưu **`GenericInterfaceStaticDemo.java`**:

~~~java
public class GenericInterfaceStaticDemo {
    interface Transformer<T> {
        T transform(T input);

        static <U> U echo(U input) {
            return input;
        }
    }

    static class Uppercase implements Transformer<String> {
        @Override
        public String transform(String input) {
            return input.toUpperCase(java.util.Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        Transformer<String> converter = new Uppercase();

        System.out.println("instance=" +
                converter.transform("hello"));
        System.out.println("static string=" +
                Transformer.echo("ready"));
        System.out.println("static integer=" +
                Transformer.echo(17));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericInterfaceStaticDemo.java
java GenericInterfaceStaticDemo
~~~

Output:

~~~text
instance=HELLO
static string=ready
static integer=17
~~~

Interface method `transform(T)` dùng type parameter T vì là instance contract. Static `echo<U>` tự khai U và được gọi bằng `Transformer.echo(...)`. Không dùng `Transformer<String>.echo(...)`.

## 28. Shared mutable static cache: lỗi thiết kế thường gặp

Giả sử một generic repository giữ:

~~~java
class Cache<T> {
    static Object last;
}
~~~

Đây là declaration **hợp lệ** vì Object không phải outer T. Nhưng nó **không type-safe theo T**: tất cả `Cache<String>`, `Cache<Integer>` chia sẻ một static field `last`.

Nếu code lấy lại `last` và cast tùy theo expected T, người lập trình có thể gây `ClassCastException` ở runtime hoặc làm leak dữ liệu giữa logical types. Thay `Object` thành raw `List` còn có thể làm xuất hiện unchecked warnings/heap pollution.

### 28.1. Code anti-pattern không nên áp dụng

~~~java
class UnsafeCache<T> {
    private static Object last;

    void remember(T value) {
        last = value;
    }

    @SuppressWarnings("unchecked")
    T getLast() {
        return (T) last; // Unchecked cast, không có per-T isolation.
    }
}
~~~

Mã trên **có thể compile**, nhưng không chứng minh an toàn. Sau type erasure, cast ở call site có thể vỡ khi lần ghi/đọc đến từ parameterization khác.

**Sửa theo bài toán thực tế:**

- Nếu cache thuộc **mỗi object**, dùng instance field `private T last`.
- Nếu cache thuộc một application scope, dùng external typed service hoặc key đầy đủ với type token/checks thích hợp.
- Nếu cache đọc-only chung và independent of T, dùng static immutable constant với type cụ thể/wildcard.
- Nếu caching thực sự cần per-type, thiết kế rõ `Map<Class<?>, ...>` và runtime type checks/ownership; không coi generic parameterizations tự cấp separate static fields.

## 29. Chương trình 14: dùng instance field để tách trạng thái theo T

Lưu **`GenericInstanceCacheDemo.java`**:

~~~java
public class GenericInstanceCacheDemo {
    static class Cache<T> {
        private T last;

        void remember(T value) {
            last = value;
        }

        T last() {
            return last;
        }
    }

    public static void main(String[] args) {
        Cache<String> text = new Cache<>();
        Cache<Integer> numbers = new Cache<>();

        text.remember("A");
        numbers.remember(99);

        System.out.println("text=" + text.last());
        System.out.println("numbers=" + numbers.last());
        System.out.println("same runtime cache class=" +
                (text.getClass() == numbers.getClass()));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericInstanceCacheDemo.java
java GenericInstanceCacheDemo
~~~

Output:

~~~text
text=A
numbers=99
same runtime cache class=true
~~~

Runtime class của hai Caches giống nhau, **nhưng** mỗi instance giữ một field `last` riêng. `T` ở instance context cho compiler compile-time type safety đối với từng reference.

### 29.1. Nếu cần “một cache cho mỗi T” có phải instance field là đủ?

Không hẳn: mỗi Cache<T> instance có state riêng, chứ không mặc định mọi Cache<String> instances cùng dùng một cache. Nếu muốn thực sự shared cache per logical type, cần **explicit registry design** phù hợp với lifecycle, key identity và concurrency; generic class static fields không tự làm điều đó.

## 30. Static registry theo token: giải pháp mạnh nhưng phải thận trọng

Một registry type-aware thường dùng `Class<?>` làm keys:

~~~java
java.util.Map<Class<?>, Object> values =
        new java.util.HashMap<>();
~~~

Điều này tách keys như `String.class` và `Integer.class` ở runtime, nhưng:

- `Class<List<String>>` không có literal riêng; `List.class` không mang đủ nested parameterization.
- `Object` values cần runtime cast/validation lúc đọc.
- Nếu global registry dùng concurrency, cần thread-safe data structure/quy ước atomicity.
- Shared static state tạo lifetime/cleanup concerns.
- A class token có thể khác nhau giữa class loaders với cùng textual name.
- `Class<T>` token giúp kiểm tra raw class chứ không tự đảm bảo tất cả nested generic arguments.

Vì thế không nên đề xuất “cứ `Map<Class<?>, Object>` là generic cache an toàn tuyệt đối”. Với dữ liệu nghiệp vụ, có thể tốt hơn dùng object-scoped instance cache hoặc dependency injection service.

## 31. Static singleton cho generic class có giới hạn kiểu

Một pattern hay bị thử:

~~~java
class Service<T> {
    // static final Service<T> INSTANCE = new Service<>();
    // Sai: outer T trong static field type.
}
~~~

Nếu tất cả instances thật sự giống nhau, có thể có:

~~~java
class Service<T> {
    private static final Service<?> SHARED = new Service<>();

    private Service() {
    }
}
~~~

Nhưng chuyển `Service<?>` thành `Service<T>` tùy ý **không tự type-safe**. Nếu Service giữ mutable state phụ thuộc T, dùng chung singleton giữa String/Integer dễ sai. Một factory generic có thể tạo instance mới cho mỗi lần gọi mà an toàn hơn:

~~~java
static <U> Service<U> create() {
    return new Service<>();
}
~~~

Nếu type không có instance state phụ thuộc U và API thật sự dùng stateless singleton, một carefully encapsulated cast có thể chấp nhận trong library internals, nhưng phải được chứng minh; không áp dụng chỉ để “làm cho compiler yên”.

## 32. Static methods và overload resolution/type inference

Static generic method có thể infer U dựa vào arguments và target type. Ví dụ:

~~~java
static <U> java.util.List<U> singleton(U element) {
    return java.util.List.of(element);
}
~~~

Call:

~~~java
java.util.List<String> words = Box.singleton("A");
java.util.List<Integer> nums = Box.singleton(1);
~~~

U được infer theo từng method invocation. Không có static storage “thuộc String” hay “thuộc Integer” hình thành vì inference; chỉ có một static method declaration.

### 32.1. Những lỗi inference không nên chữa bằng raw types

Nếu compiler báo không infer được U, hãy kiểm tra constraints, overloads, target type và bounds. Sử dụng raw `Box` hay cast không kiểm soát có thể tắt warning nhưng tạo heap pollution. Có thể chỉ rõ method type argument như `Box.<Number>singleton(1)` khi API cho phép.

### 32.2. Generic method type variable không nhất thiết là class T

Kể cả trong `class Box<T>`, một method instance cũng có thể khai thêm `<U>` riêng; đó là sự linh hoạt của Java generics, không phải static-only feature.

## 33. Bài so sánh: cùng chữ `T` nhưng khác declaration

~~~java
class Example<T> {
    private T value;

    T instanceIdentity(T item) {
        return item;
    }

    static <U> U staticIdentity(U item) {
        return item;
    }

    static <T> T confusing(T item) {
        return item;
    }
}
~~~

Cả đoạn là class snippet hợp lệ (đặt file/scope phù hợp). Trong `static <T> T confusing(T item)`, chữ T là **method type parameter**, shadow class T. Mặc dù compiler cho phép, style thường dùng `<U>` cho method để tránh nhầm outer/class generic state.

**Không viết:**

~~~java
// static T missing(T item) { return item; }
// Vì method KHÔNG khai <T>, chữ T trỏ outer T.
~~~

Đây chính là một khác biệt nhỏ về cú pháp nhưng quyết định compile-time correctness.

## 34. Chương trình 15: method-owned T trùng tên vẫn không dùng outer T

Lưu **`GenericStaticShadowDemo.java`**:

~~~java
public class GenericStaticShadowDemo {
    static class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T instanceValue() {
            return value;
        }

        static <T> T echo(T value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Holder<String> holder = new Holder<>("outer");

        System.out.println("instance=" + holder.instanceValue());
        System.out.println("static integer=" + Holder.echo(10));
        System.out.println("static text=" + Holder.echo("inner"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericStaticShadowDemo.java
java GenericStaticShadowDemo
~~~

Output:

~~~text
instance=outer
static integer=10
static text=inner
~~~

Dù Holder khai outer T và echo khai method T cùng chữ, static method echo vẫn độc lập, không được “đọc T=String từ holder”. Nếu đặt type parameters khác tên, intent càng rõ.

## 35. Trường hợp kế thừa generic class và static members

Giả sử:

~~~java
class Parent<T> {
    static int count;
}

class Child<U> extends Parent<U> {
}
~~~

`Parent.count` là static field của Parent generic declaration. Dù Child extends Parent<U>, nó không tạo một count riêng cho Parent<String> hoặc Parent<Integer>. Static fields có thể được **inherited/hiding** theo Java rules, nhưng đó không phải per-type-parameter storage.

Khi đọc code, nên dùng **declaring class name** `Parent.count` để chỉ rõ nguồn static field, thay vì access qua instance/derived name làm nhầm member resolution.

Nếu subclass khai một static field trùng tên, đó là **field hiding** (khác với instance polymorphism), không phải generic type specialization. Tránh dùng tên giống nhau khi không cần thiết.

## 36. Bảng lỗi thường gặp và cách sửa

| Hiểu sai hoặc code lỗi | Cách sửa / diễn giải đúng |
| --- | --- |
| `static T cache;` trong `class Box<T>` | Outer T không usable trong static context; dùng instance field hoặc type cụ thể/wildcard |
| `static List<T> items;` | Cấm dùng outer T làm type argument trong static declaration |
| `static T create(T x)` | Khai `static <U> U create(U x)` nếu method độc lập |
| `static Box<T> of(T x)` | Dùng `static <U> Box<U> of(U x)` |
| `static T get() { return null; }` | Signature đã sai dù body không access instance |
| `static Object f(){ return this; }` | Không có `this` trong static method |
| `static Object f(){ return value; }` | Instance field cần một receiver cụ thể |
| `static { T x = ...; }` | Static initializer không dùng outer T |
| `static class Node { T data; }` | Static nested class không dùng outer T; khai `Node<U>` |
| `record Entry(T value)` nested trong generic class | Member record implicitly static; khai `Entry<U>` |
| `static final List<T> EMPTY` | Dùng `List<?>` hoặc static generic method trả `List<U>` |
| `Box<String>.count` | Qualify static member bằng `Box.count` |
| `Box<String>.of(x)` | Dùng `Box.of(x)` hoặc `Box.<String>of(x)` |
| “`Box<String>` có static field riêng” | Không; một runtime class, static state chung |
| `new T()` ở instance method | Không hợp lệ do type variable/reifiability, không phải chỉ static |
| `T.class` ở instance method | Không; truyền `Class<T>` token khi cần |
| `instanceof T` | Không; dùng reifiable target/check phù hợp |
| `Box<List<String>>.getClass()` trả Class riêng | Runtime raw class identity chung |
| “`T extends Number` làm static T hợp lệ” | Không, bound không bỏ static-context restriction |
| “`static <T>` chính là outer T” | Không, method type parameter mới che outer T |
| “Static counter thread-safe vì generic” | Không; `++` cần concurrency control nếu đa luồng |
| “`Object` static cache phù hợp mọi T” | Compiler có thể cho phép nhưng có thể mất type safety |
| “`Class<T>` token giữ toàn bộ nested generics” | Không; token cho raw runtime class, nested arguments bị erasure |

## 37. Checklist code review

- [ ] Class có type parameter `<T>`, field nào là instance và field nào static?
- [ ] Có outer T xuất hiện trong static field declaration không?
- [ ] Có outer T trong static method signature/body không?
- [ ] Có outer T trong static initializer không?
- [ ] Có static nested class/record/enum vô tình tham chiếu outer T không?
- [ ] Mỗi static generic utility đã khai own `<U>` trước return type chưa?
- [ ] Type parameters method và class có đặt trùng chữ gây hiểu nhầm không?
- [ ] Nếu static method cần instance data, có nhận object receiver phù hợp chưa?
- [ ] Static members có được qualifier bằng generic class name thay parameterized name không?
- [ ] Có dựa vào giả định static field được nhân bản theo `Box<String>` và `Box<Integer>` không?
- [ ] Nếu lưu static shared mutable state, concurrency/ownership/lifetime thế nào?
- [ ] Có dùng `List<?>` hoặc concrete static types có căn cứ, thay raw type không?
- [ ] Nếu cần type-specific state, instance field hoặc explicit type-keyed service đúng hơn?
- [ ] `new T()`/`T.class`/`instanceof T` có bị nhầm là sửa được bằng chuyển non-static không?
- [ ] Bounded static generic helper có own bounds, như `<U extends Number>` chưa?
- [ ] Constructor/factory có return type `Box<U>` phù hợp compiler inference không?
- [ ] Static nested class có tự khai type parameter nếu cần lưu values generic chưa?
- [ ] Inner class có thật sự cần enclosing instance lifetime và outer T không?
- [ ] Generic interface static methods có own type parameters đúng rules chưa?
- [ ] Unit tests chạy Java 17+ không dựa warning/error wording cố định?
- [ ] Có kiểm tra class identity và static count ở hai parameterizations trong cùng JVM?
- [ ] Nếu cần `Class<T>` token, có giới hạn generic nested type được xử lý đúng không?

## 38. Bài tập và đáp án

**Câu 1.** Trong `class Box<T>`, `static T value;` hợp lệ không?  
**Đáp án:** Không. Outer class T không usable trong static field declaration.

**Câu 2.** Vì sao Java không lưu static value riêng cho Box<String>/Box<Integer>?  
**Đáp án:** Các parameterizations dùng cùng runtime class, static state gắn class declaration, không từng type argument.

**Câu 3.** `T get()` instance method hợp lệ không?  
**Đáp án:** Có.

**Câu 4.** `static T get()` hợp lệ dù method chỉ `return null;`?  
**Đáp án:** Không. Static return type T vẫn là outer class type parameter.

**Câu 5.** Viết một static generic identity method.  
**Đáp án:** `static <U> U identity(U input) { return input; }`.

**Câu 6.** `<U>` đứng trước hay sau return type?  
**Đáp án:** Sau modifiers, trước return type.

**Câu 7.** `static <T> T copy(T value)` trong `class Box<T>` có dùng outer T không?  
**Đáp án:** Không; method T là một declaration mới shadow outer T.

**Câu 8.** `Box.<String>of("A")` chỉ type argument cho class hay method?  
**Đáp án:** Cho static generic method `of`.

**Câu 9.** `Box<String>.of("A")` dùng để gọi static member hợp lệ không?  
**Đáp án:** Không; static member không được qualified qua parameterized type.

**Câu 10.** `Box.count` và `Box<Integer>.count` khác nhau?  
**Đáp án:** Cách thứ nhất hợp lệ; cách thứ hai không dùng làm qualifier của static member.

**Câu 11.** Static helper muốn đọc value của Box<T>, có thể nhận `Box<?> input` không?  
**Đáp án:** Có, rồi gọi instance accessor trên receiver.

**Câu 12.** Muốn giữ return type chính xác U khi đọc Holder<U> từ static method?  
**Đáp án:** `static <U> U read(Holder<U> h) { return h.get(); }`.

**Câu 13.** `static final List<?> EMPTY = List.of()` hợp lệ?  
**Đáp án:** Có, không dùng outer T.

**Câu 14.** `static final List<T> EMPTY` trong Box<T> hợp lệ?  
**Đáp án:** Không; T của outer class ở static declaration.

**Câu 15.** Static nested class trong Generic<T> dùng trực tiếp T không?  
**Đáp án:** Không.

**Câu 16.** Non-static inner class trong Generic<T> dùng T không?  
**Đáp án:** Có khi rules/scope hợp lệ, vì gắn với enclosing instance.

**Câu 17.** `static class Slot<U>` được khai type parameter U không?  
**Đáp án:** Có; U thuộc nested class.

**Câu 18.** Member record trong Generic<T> có thể dùng outer T trong header?  
**Đáp án:** Không, member record implicitly static; phải khai own type parameter.

**Câu 19.** Generic class static initializer có dùng T làm local variable type không?  
**Đáp án:** Không.

**Câu 20.** Nếu Box<T> chỉ giữ `static int count`, số count có tách theo String/Integer không?  
**Đáp án:** Không, static count chung.

**Câu 21.** `T.class` có hợp lệ trong instance method không?  
**Đáp án:** Không, T không là reifiable type.

**Câu 22.** `new T()` có hợp lệ trong instance constructor không?  
**Đáp án:** Không, không được instantiate type variable trực tiếp.

**Câu 23.** Lấy runtime Class<T> bằng cách nào?  
**Đáp án:** Có thể truyền `Class<T>` token từ caller qua constructor/factory, tùy domain.

**Câu 24.** `Class<T>` token có phân biệt `List<String>` và `List<Integer>` runtime không?  
**Đáp án:** Không bằng List.class; nested generic arguments không được giữ kiểu reified như vậy.

**Câu 25.** Bounded class `Numeric<T extends Number>` có thể khai `static T zero` không?  
**Đáp án:** Không.

**Câu 26.** Bounded static method `static <U extends Number> double twice(U x)` hợp lệ?  
**Đáp án:** Có.

**Câu 27.** `static Object last` trong Cache<T> có phải type-safe per T không?  
**Đáp án:** Không, static object shared; đọc sai kiểu dễ ClassCastException.

**Câu 28.** Cần lưu state riêng theo mỗi Cache<T> object làm gì?  
**Đáp án:** Dùng `private T last` instance field.

**Câu 29.** Cần cache shared per logical runtime type thì generics tự làm được không?  
**Đáp án:** Không; cần explicit registry/ownership/type checks, cân nhắc class tokens.

**Câu 30.** Static method trong generic interface có thể dùng interface type parameter không?  
**Đáp án:** Không; khai own generic method parameter nếu cần.

**Câu 31.** Static method type inference nghĩa là JVM sinh method riêng cho mỗi type argument?  
**Đáp án:** Không, compile-time inference, runtime class/method declaration chung.

**Câu 32.** Nếu generic class có instance methods dùng T và static methods dùng U, đó là lỗi thiết kế?  
**Đáp án:** Không; đó là pattern bình thường nếu mỗi method có trách nhiệm rõ.

**Câu 33.** `Pair<K,V>` return từ `static <K,V> Pair<K,V> pair(K k,V v)` có type-safe không?  
**Đáp án:** Có khi các type declarations và overloads hợp lệ.

**Câu 34.** Lỗi lớn nhất cần nhớ?  
**Đáp án:** Không có `T` cấp lớp xác định cho **static context**; dùng instance members, method-owned generics hoặc explicit runtime type information theo mục tiêu.

## 39. Chương trình kiểm thử tổng hợp

Lưu **`GenericStaticContractTest.java`**:

~~~java
public class GenericStaticContractTest {
    static class Box<T> {
        private static int created;
        private final T value;

        private Box(T value) {
            this.value = value;
            created++;
        }

        static <U> Box<U> of(U input) {
            return new Box<>(input);
        }

        T value() {
            return value;
        }

        static int count() {
            return created;
        }

        static <U> U read(Box<U> box) {
            return box.value();
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Box<String> words = Box.of("JDK");
        Box<Integer> digits = Box.of(17);

        check(words.value().equals("JDK"), "word value");
        check(digits.value() == 17, "integer value");
        check(Box.count() == 2, "one shared static count");
        check(words.getClass() == digits.getClass(),
                "one runtime class");
        check(Box.read(words).equals("JDK"),
                "static method owns U");

        System.out.println("generic static checks passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericStaticContractTest.java
java GenericStaticContractTest
~~~

**Stdout:**

~~~text
generic static checks passed
~~~

Method `check` luôn kiểm tra dù Java `assert` bị tắt mặc định nếu không bật `-ea`. Chương trình dùng **một static field chung**, hai generic instance values, một generic factory và một generic static read helper.

## 40. Tài liệu tham khảo chính thức

- [Java Language Specification SE 17 `8.1.2 — Generic Classes and Type Parameters`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.2): class type parameters, sharing runtime class across parameterizations.
- [JLS `8.1.3 — Inner Classes and Enclosing Instances`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): static nested/inner distinctions.
- [JLS `6.5.5.1 — Simple Type Names`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5.5.1): prohibition on class type parameter references in static context and nested static types.
- [JLS `4.5.2 — Members and Constructors of Parameterized Types`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.2): static members phải được qualified bằng generic type declaration name, không qua parameterized type.
- [JLS `8.4.4 — Generic Methods`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.4): syntax và method-owned type parameters.
- [JLS `4.6 — Type Erasure`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): erased runtime representation.
- [JLS `8.3 — Field Declarations`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): static/instance fields.
- [JLS `8.7 — Static Initializers`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): static blocks.
- [JLS `15.8.2 — Class Literals`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.2): why `T.class` cannot be used.
- [JLS `15.20.2 — Type Comparison Operator instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): reifiable type restrictions.
- [JLS `9.1.2 — Generic Interfaces`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.2): similar interface-level generic restrictions.
- [Java SE 17, Class.cast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#cast(java.lang.Object)): runtime casting with explicit Class token.
- [Java SE 17, List.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#of()): type-inferred unmodifiable collection factory.
- [Oracle Java Tutorial — Generic Methods](https://docs.oracle.com/javase/tutorial/java/generics/methods.html): method type parameter declaration and type inference (tutorial examples historically Java 8; JLS 17 ở trên là chuẩn cho bài).

## Tổng kết

Trong `class Box<T>`, **T là tham số kiểu cấp class để mô tả instance-typed data/behavior**. `static` thuộc generic class declaration, không thuộc riêng `Box<String>` hoặc `Box<Integer>`; các parameterizations cùng dùng một runtime class. Vì vậy Java **không cho dùng outer `T` trực tiếp trong static fields, static methods, static initializers hoặc static nested classes**.

Cách sửa phụ thuộc vào mục tiêu:

1. Nếu dữ liệu thuộc từng object, dùng **instance field/method** với T.
2. Nếu cần generic static factory/helper, khai **method type parameter riêng**: `static <U> Box<U> of(U input)`.
3. Nếu cần static metadata dùng chung, khai type cụ thể/wildcard, không kỳ vọng static state tự phân chia theo T.
4. Nếu cần xử lý runtime type, truyền explicit `Class<T>` token hoặc một typed factory, đồng thời nhớ erasure không giữ mọi nested generic arguments.
5. Nếu static method cần dữ liệu instance, nhận một object parameter và gọi qua receiver, không viết `this`.
6. Với static nested class/record, khai own generic type parameters thay vì tham chiếu outer class T.
7. Đừng dùng parameterized class name để qualify static members: `Box.count` hoặc `Box.<String>of(...)` mới là các forms tương ứng.

**Một câu ghi nhớ:** *Tham số kiểu T của class gắn với cách dùng instance ở compile time; ngữ cảnh static muốn generic thì phải có tham số kiểu riêng của method/type, không vay trực tiếp T của lớp ngoài.*

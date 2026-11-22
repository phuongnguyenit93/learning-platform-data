# Giới hạn dùng T của lớp trong trường và phương thức static (Java Generics)

## 1. Tình huống và quy tắc cần nhớ

Một lớp generic khai báo tham số kiểu sau tên lớp, ví dụ `class Box<T>`. Tham số `T` mô tả kiểu dữ liệu của **một cách tham số hóa lớp** như `Box<String>` hoặc `Box<Integer>`. Ta có thể sử dụng `T` trong trường instance, constructor và phương thức instance. Tuy nhiên, **không được lấy trực tiếp `T` của lớp để khai báo kiểu của trường hoặc phương thức `static`**.

```java
// Mảnh minh họa độc lập về cú pháp.
class Box<T> {
    private T value;                // Đúng: trường instance thuộc Box<T>.

    Box(T value) {                  // Đúng: constructor dùng T của lớp.
        this.value = value;
    }

    T get() {                       // Đúng: phương thức instance trả T.
        return value;
    }

    // private static T shared;     // Sai: static field không dùng T của lớp.
    // static T identity(T input) { // Sai: static method không dùng T của lớp.
    //     return input;
    // }

    static <U> U identity(U input) { // Đúng: U do phương thức khai báo riêng.
        return input;
    }
}
```

Với `Box<String>`, getter `get()` được kiểm tra như trả `String`; với `Box<Integer>`, getter trả `Integer`. Nhưng `Box.identity(42)` là lời gọi phương thức `static` dùng `U = Integer` của **chính phương thức**, không phụ thuộc vào một `Box<T>` nào.

Quy tắc này áp dụng với cả trường `static final`, phương thức `static`, các khối khởi tạo `static` và những phần khai báo thành viên ở **ngữ cảnh static** nếu chúng cố tham chiếu `T` của lớp. Không có ngoại lệ chỉ vì trường đặt `final` hoặc phương thức không truy cập trạng thái đối tượng.

Bài học áp dụng Java 17+, có mã chạy độc lập và những đoạn cố tình không biên dịch được giữ dưới dạng comment hoặc ghi chú.

## 2. Phân biệt phạm vi của `T`: lớp và từng đối tượng

`class Box<T>` khai báo `T` trong **type parameter list của lớp**. `T` có thể xuất hiện trong những ngữ cảnh instance sau:

| Vị trí | Ví dụ | Hợp lệ? | Giải thích |
| --- | --- | --- | --- |
| Trường instance | `private T value;` | Có | Trường gắn với mỗi đối tượng `Box<T>`. |
| Constructor | `Box(T initial)` | Có | Kiểm tra đầu vào theo kiểu `T` của đối tượng tạo ra. |
| Phương thức instance | `void set(T value)` | Có | Setter thuộc đối tượng, nên biết `T`. |
| Giá trị trả về instance | `T get()` | Có | Liên kết kiểu trả về với kiểu của đối tượng. |
| Tham số generic của trường instance | `List<T> items` | Có | Kiểu phần tử của collection vẫn là `T`. |
| Trường static | `static T shared` | Không | Thành viên thuộc lớp chung, không thể chọn một `T` của từng cách tham số hóa. |
| Kiểu trả về static | `static T getShared()` | Không | Không có `T` của lớp trong static context. |
| Tham số static | `static void accept(T value)` | Không | Cũng tham chiếu `T` của lớp từ static context. |
| Phương thức static khai báo kiểu riêng | `static <U> U echo(U value)` | Có | `U` thuộc chính phương thức, không thuộc lớp. |

Một ví dụ lớp chứa dữ liệu có kiểu rõ ràng:

```java
import java.util.*;

final class TypedList<T> {
    private final List<T> items = new ArrayList<>();

    void add(T item) {
        items.add(item);
    }

    List<T> snapshot() {
        return List.copyOf(items);
    }
}
```

`TypedList<String>` có các phần tử được trình biên dịch kiểm tra như `String`. `TypedList<Integer>` có các phần tử được kiểm tra như `Integer`. Hai đối tượng có thể cùng chạy một định nghĩa lớp, nhưng luồng dữ liệu qua thành viên instance vẫn giữ hợp đồng generic tương ứng.

Ở đây `List.copyOf` tạo một danh sách không sửa được và không nhận phần tử `null`. Đây là lựa chọn API, không phải đặc tính bắt buộc của `T`. Nếu lớp cho phép null thì nên sử dụng cách tạo snapshot phù hợp.

## 3. Tại sao trường static không được dùng `T` của lớp?

Trường instance được gắn với **đối tượng**: mỗi `Box<String>` có thể chứa `String`, mỗi `Box<Integer>` có thể chứa `Integer`. Trường `static` thì gắn với **lớp runtime**, không với một đối tượng hay một cách truyền tham số kiểu cụ thể.

Giả sử Java cho phép khai báo sau:

```java
class InvalidBox<T> {
    // static T sharedValue; // Không hợp lệ; cố tình comment.
}
```

Nếu `sharedValue` thực sự có cùng một ô lưu trữ cho cả `InvalidBox<String>` và `InvalidBox<Integer>`, compiler sẽ không thể đồng thời bảo đảm nó chỉ nhận `String` và chỉ nhận `Integer`. Cấm khai báo này là cách Java giữ hợp đồng kiểu nhất quán.

Đó là quy tắc ngôn ngữ về **static context**: tham số kiểu của một lớp generic không thể được tham chiếu từ khai báo static của chính lớp ấy. **Không phải chỉ do trình biên dịch “chưa biết dữ liệu ban đầu”**: ngay cả khi mọi constructor truyền cùng một loại dữ liệu tại một thời điểm, static member vẫn là thành viên cấp lớp.

### Trường static dùng kiểu cụ thể vẫn hợp lệ

```java
import java.util.List;

class Repository<T> {
    static int instanceCount = 0;                // Hợp lệ.
    static final String CATEGORY = "repository"; // Hợp lệ.
    static final List<String> FLAGS = List.of("A", "B"); // Hợp lệ.

    private T item;  // Hợp lệ: trường instance.
}
```

`static final List<String> FLAGS` là một **kiểu generic có tham số cụ thể `String`**, nên vẫn hợp lệ. Điều bị cấm là dùng **chính tham số `T` của lớp** ở kiểu của thành viên static, chẳng hạn `static List<T> FLAGS`.

`static final` không làm giá trị tham chiếu tự động bất biến: ví dụ `static final ArrayList<String>` vẫn có thể bị thay đổi nội dung qua các phương thức của list. `List.of(...)` trong ví dụ tạo list không sửa được để diễn đạt rõ chính sách dữ liệu.

### Không có bản sao static cho mỗi type argument

```java
class CounterBox<T> {
    private static int count;

    CounterBox() {
        count++;
    }

    static int count() {
        return count;
    }
}

// CounterBox<String> a = new CounterBox<>();
// CounterBox<Integer> b = new CounterBox<>();
// CounterBox.count() là 2, không có hai bộ đếm riêng.
```

`count` là **một** trường cho `CounterBox`, không phải `CounterBox<String>.count` và `CounterBox<Integer>.count`. Nếu muốn đếm theo kiểu dữ liệu, chương trình phải **tự truyền thông tin phân nhóm** (chẳng hạn một `Class<?>` token, key hoặc tên loại) và quản lý một ánh xạ phù hợp; Java không tự tạo static data riêng cho từng tham số kiểu.

## 4. Vì sao phương thức static cũng không dùng `T` của lớp?

Phương thức instance gọi thông qua đối tượng có kiểu cụ thể:

```java
// Mảnh minh họa, giả sử Box<T> có T get().
Box<String> title = new Box<>("Java");
String content = title.get();
```

Phương thức `get()` gắn với đối tượng `title`, nên compiler biết đó là `Box<String>`. Trái lại, phương thức `static` có thể gọi thông qua **tên lớp** mà không tạo đối tượng:

```java
// Mảnh minh họa cho một static method tự khai báo <U>.
String s = Box.identity("Java");
Integer n = Box.identity(10);
```

Nếu phương thức static cố nhận `T` của `class Box<T>`, nó sẽ không có một `Box<String>` hoặc `Box<Integer>` cụ thể để ràng buộc kiểu.

```java
class Wrong<T> {
    // static T wrong(T item) { return item; } // Lỗi biên dịch.

    static <U> U correct(U item) {
        return item;
    }
}
```

Ở `correct`, tham số kiểu `U` được khai báo **ngay trước kiểu trả về**. Mỗi lần gọi phương thức có thể suy luận `U` theo đối số và ngữ cảnh kết quả. Đây là **static generic method**, khác với phương thức static dùng `T` của lớp.

### Cú pháp chuẩn của static generic method

```java
class Utility {
    static <U> U first(U left, U right) {
        return left;
    }

    static <K, V> java.util.Map.Entry<K, V> pair(K key, V value) {
        return java.util.Map.entry(key, value);
    }
}

// String value = Utility.first("A", "B");
// Map.Entry<String,Integer> entry = Utility.pair("age", 21);
```

Lưu ý thứ tự: các modifier như `public` và `static` đứng trước danh sách type parameter `<U>`, sau đó mới đến kiểu trả về. Không viết `static U <U> first(...)`.

## 5. Ba trường hợp phải phân biệt trong lớp generic

Xét:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T get() {                  // (1)
        return value;
    }

    <U> U convert(java.util.function.Function<? super T, ? extends U> f) { // (2)
        return f.apply(value);
    }

    static <U> U echo(U input) { // (3)
        return input;
    }
}
```

| Phương thức | Có phải generic method? | Dùng tham số kiểu nào? |
| --- | --- | --- |
| `T get()` | Không, vì không tự khai báo `<...>` | `T` của `Holder<T>` |
| `<U> U convert(...)` | Có | `T` của lớp, `U` của phương thức |
| `static <U> U echo(U)` | Có | Chỉ `U` của phương thức |

Ví dụ:

```java
Holder<String> holder = new Holder<>("Java");
String a = holder.get();                       // T = String.
Integer b = holder.convert(String::length);    // U = Integer.
Long c = Holder.echo(10L);                     // U = Long, không liên quan holder.
```

`convert` là **instance generic method**: có thể truy cập `this.value`, dùng `T` của lớp và đồng thời khai báo `U` riêng. `echo` là **static generic method**: không thể truy cập `this` hoặc `value` như trường instance.

Điểm quan trọng: một phương thức **có thể** generic mà không static, hoặc static mà không generic. Hai tính chất này độc lập. `static int count()` là static method thông thường; `<U> U convert(...)` là generic instance method.

## 6. Tránh khai báo `<T>` làm che khuất `T` của lớp

Java cho phép phương thức khai báo một tham số kiểu mới trùng **tên** với tham số kiểu của lớp. Đây là tình huống dễ đọc sai nhất:

```java
class Confusing<T> {
    private final T value;

    Confusing(T value) {
        this.value = value;
    }

    // T trong chữ ký echo là T MỚI của phương thức.
    static <T> T echo(T input) {
        return input;
    }

    // T ở đây là T của lớp.
    T get() {
        return value;
    }
}
```

Với `Confusing<String>`, getter `get()` trả `String`, nhưng `Confusing.echo(42)` vẫn trả `Integer`. Hai chữ `T` có hình thức giống nhau nhưng **không cùng một khai báo**; `T` của phương thức che khuất `T` của lớp ở phạm vi của phương thức đó.

Cách thiết kế rõ hơn:

```java
class Clear<T> {
    private final T value;

    Clear(T value) { this.value = value; }

    T get() { return value; }

    static <U> U echo(U input) { return input; }
}
```

Dùng `<U>`, `<R>` hoặc tên khác cho tham số của phương thức static để tránh người đọc tưởng nó bị ràng buộc bởi type argument ở lớp.

**Đừng “sửa” lỗi static bằng cách viết `static <T> T method(...)` nếu logic thực sự cần đọc trạng thái của một đối tượng**. Trường hợp đó nên là instance method, hoặc static method phải nhận chính đối tượng đã được tham số hóa:

```java
class Reader<T> {
    private final T value;

    Reader(T value) { this.value = value; }

    T get() { return value; }

    static <U> U readFrom(Reader<U> source) {
        return source.get();
    }
}

// Reader<String> item = new Reader<>("Java");
// String result = Reader.readFrom(item);
```

`readFrom` hợp lệ vì nguồn `Reader<U>` được truyền **tường minh dưới dạng tham số**. Nó dùng `U` của phương thức để liên hệ kiểu nguồn và kết quả, không lấy `T` của lớp từ static context.

## 7. Static factory: cách hợp lệ để tạo `Box<U>` từ ngữ cảnh static

Điều quan trọng khi sửa lỗi `static T` là **không biến đầu vào thành `Object`**. Nếu cần tạo một instance mới có kiểu giữ nguyên từ đối số, phương thức static phải tự khai báo `U` và liên kết `U` giữa tham số với kết quả:

~~~java
final class Box<T> {
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
~~~

`Box.of("Java")` trả `Box<String>`; `Box.of(17)` trả `Box<Integer>`. Trong cả hai lời gọi, **`U` của factory** được suy luận riêng, còn `T` của class chỉ có nghĩa khi object `Box<U>` đã được tham số hóa. Đây là cách sửa đúng lỗi dùng type variable của lớp trong thành viên static mà vẫn giữ kiểu kết quả.

Bài về **phương thức static generic** triển khai riêng type witness, nhiều type parameters, callback `Function` và các factory có bound; ở đây chỉ cần nắm bất biến: **static không mượn `T` của class**, nhưng có thể tạo một `Box<U>` qua `static <U>`.

## 8. Bound thuộc tham số kiểu do static method khai báo

Khi thuật toán static cần dùng một API của giá trị đầu vào, giới hạn phải đặt trên **type parameter riêng của phương thức**, không phải dựa vào `T` của lớp bao:

~~~java
class NumericContainer<T> {
    static <U extends Number> double twice(U number) {
        return number.doubleValue() * 2;
    }
}
~~~

`NumericContainer.twice(2.5)` hợp lệ và cho `5.0`, còn `NumericContainer.twice("2.5")` bị compiler từ chối. `U extends Number` chỉ ràng buộc lời gọi `twice`; nó **không phụ thuộc cách tham số hóa** `NumericContainer<String>` hay `NumericContainer<Integer>`. Với thuật toán khác, có thể dùng bound `Comparable<? super U>` hoặc nhiều bounds nếu thật sự cần.

Chọn bounds theo thao tác cần thực hiện, và nhớ rằng **bound là ràng buộc kiểu lúc biên dịch**, không làm `U` trở thành một class token runtime có thể dùng trực tiếp như `U.class`.

## 9. Static nested class là một ranh giới khác với inner class

Một lớp lồng `static` cũng không được dùng trực tiếp `T` của generic outer class; trong khi một **non-static inner class** có thể làm vậy bởi nó gắn với một enclosing instance:

~~~java
class Outer<T> {
    private final T value;
    Outer(T value) { this.value = value; }

    class Inner {
        T read() { return value; }
    }

    static class Nested<U> {
        U data;
        Nested(U data) { this.data = data; }
    }
}
~~~

Ở nơi sử dụng, `Outer<String>.Inner` được tạo bằng `outer.new Inner()`; `Outer.Nested<Integer>` được tạo bằng `new Outer.Nested<>(42)`. Type parameter `U` thuộc chính `Nested`; nó không liên quan ngầm đến `T` của `Outer`.

Ví dụ này chỉ minh họa cùng **giới hạn ngữ cảnh static** với field/method. Cách tạo, mô hình enclosing-instance, lifecycle và generic bounds của từng loại lớp lồng được giải thích chuyên sâu trong các bài tương ứng.

## 10. Static block, static initializer và việc truy cập dữ liệu

Một khối `static { ... }` chạy khi lớp được khởi tạo theo quy tắc của Java. Nó không có đối tượng `this`, không có `T` của lớp generic, và không thể trực tiếp truy cập trường instance:

```java
class Configuration<T> {
    private T value;
    private static final String DEFAULT_LABEL;

    static {
        DEFAULT_LABEL = "READY"; // Đúng: field static có kiểu String cụ thể.
        // T v = null;          // Sai: không dùng T của lớp trong static context.
        // value = null;        // Sai: không có instance của Configuration<T>.
    }

    Configuration(T value) { this.value = value; }
    T get() { return value; }

    static String label() {
        return DEFAULT_LABEL;
    }
}
```

Một static method có thể gọi các phương thức static khác hoặc dùng static field bình thường; vấn đề chỉ xuất hiện khi nó cố sử dụng `T` của lớp hoặc truy cập một instance member khi không có đối tượng.

Với một đối tượng được truyền vào làm tham số, static method **vẫn có thể gọi instance method** của đối tượng đó, ví dụ `source.get()` ở `Reader.readFrom(...)`. Quy tắc đúng là phải có **tham chiếu đối tượng rõ ràng**, không dùng `this` hoặc truy cập trực tiếp member instance từ ngữ cảnh static.

## 11. Tại sao type erasure làm quy tắc dễ hiểu hơn?

Java generics thường được thực hiện bằng **type erasure**: kiểm tra tham số kiểu lúc biên dịch, sau đó compiler dùng bound tương ứng trong biểu diễn runtime thông thường. Vì vậy, `Box<String>` và `Box<Integer>` dùng cùng lớp runtime `Box`:

```java
// Mảnh minh họa, giả sử Box<T> có constructor Box(T).
Class<?> a = new Box<>("Java").getClass();
Class<?> b = new Box<>(123).getClass();
boolean same = a == b; // true.
```

Runtime không tạo một `Class` riêng cho từng type argument thông thường. Điều này nhất quán với việc các trường `static` thuộc về lớp chung và không được tham số hóa bởi `T` của mỗi instance.

Cũng vì `T` thường không phải kiểu *reifiable*, không thể viết:

```java
class ErasureLimits<T> {
    // T value = new T();      // Không thể khởi tạo kiểu T trực tiếp.
    // Class<T> c = T.class;   // Không có T.class.
    // T[] items = new T[10]; // Không được tạo mảng T trực tiếp.
}
```

Nếu logic static cần làm việc với một kiểu cụ thể ở runtime, truyền `Class<U>` hoặc factory `Supplier<? extends U>` (tùy mục đích) vào static generic method. Ví dụ:

```java
import java.util.function.Supplier;

class Creator<T> {
    static <U> U create(Supplier<? extends U> factory) {
        return factory.get();
    }
}

// StringBuilder b = Creator.create(StringBuilder::new);
```

Tham số `U` của `create` được suy luận từ factory/lời gọi; không cần và không được lấy `T` của `Creator<T>`.

**Lưu ý:** Không nên diễn giải type erasure như toàn bộ metadata generic luôn biến mất. Reflection vẫn có thể đọc một số khai báo type parameter/bound trong metadata, nhưng điều đó **không** biến static field thành dữ liệu riêng của `Box<String>` hoặc cho phép sử dụng `T` lớp trong static context.

## 12. Chương trình hoàn chỉnh: xác nhận sự khác nhau trong một lần chạy

Lưu đoạn sau thành tệp **`StaticTypeScopeDemo.java`**. Đây là chương trình độc lập có thể biên dịch/chạy trên Java 17+. Lớp `Box<T>` ở mức top-level giữ dữ liệu instance, bộ đếm static dùng chung, static generic methods, static nested class và non-static inner class.

```java
import java.util.List;
import java.util.Objects;

final class Box<T> {
    private final T value;
    private static int created;
    static final String KIND = "Box";
    static final List<String> TAGS = List.of("shared", "metadata");

    Box(T value) {
        this.value = Objects.requireNonNull(value);
        created++;
    }

    T get() {
        return value;
    }

    static int createdCount() {
        return created;
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }

    static <U extends Number> double twice(U number) {
        return number.doubleValue() * 2;
    }

    static final class Pair<A, B> {
        private final A key;
        private final B value;

        Pair(A key, B value) {
            this.key = key;
            this.value = value;
        }

        A key() { return key; }
        B value() { return value; }
    }

    final class View {
        T read() { return value; }
    }
}

public class StaticTypeScopeDemo {
    public static void main(String[] args) {
        Box<String> name = Box.of("Java");
        Box<Integer> count = Box.of(21);

        System.out.println("instance: " + name.get() + " / " + count.get());
        System.out.println("created: " + Box.createdCount());
        System.out.println("twice: " + Box.twice(2.5));

        Box.Pair<String, Integer> pair = new Box.Pair<>("age", 21);
        System.out.println("pair: " + pair.key() + "=" + pair.value());

        Box<String>.View view = name.new View();
        System.out.println("inner: " + view.read());
        System.out.println("kind: " + Box.KIND);
        System.out.println("tags: " + Box.TAGS);
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all StaticTypeScopeDemo.java
java StaticTypeScopeDemo
```

Kết quả stdout chính xác (đã kiểm chứng bằng compiler Java 24 ở chế độ `--release 17`, không có cảnh báo `-Xlint:all`):

```text
instance: Java / 21
created: 2
twice: 5.0
pair: age=21
inner: Java
kind: Box
tags: [shared, metadata]
```

### Diễn giải theo từng thành phần

1. `Box.of("Java")` suy luận `U = String`, tạo `Box<String>`. `Box.of(21)` suy luận `U = Integer`, tạo `Box<Integer>`. Factory static không cần truy cập `T` của lớp.
2. Hai constructor làm bộ đếm `created` tăng hai lần. `Box.createdCount()` in `2` vì cả hai kiểu đối tượng cùng chia sẻ trường static.
3. `name.get()` trả `String`; `count.get()` trả `Integer` theo tham số kiểu của mỗi đối tượng.
4. `Box.twice(2.5)` suy luận `U = Double` và gọi `doubleValue()` nhờ bound `extends Number`, cho kết quả `5.0`.
5. `Box.Pair<A,B>` là một **static nested generic class** có tham số kiểu `A`/`B` riêng và không sử dụng `T` của `Box<T>`.
6. `Box<String>.View` là lớp inner gắn với đối tượng `name`, nên `read()` được kiểm tra kiểu trả về là `String`.
7. `KIND` và `TAGS` là các trường static kiểu cụ thể, dùng chung cho mọi `Box<T>`. Việc chúng có kiểu tham số hóa `List<String>` không vi phạm quy tắc, vì không dùng `T` lớp.

Mỗi kiểu dữ liệu trong luồng đọc/ghi đều được diễn đạt bằng generic type hoặc kiểu cụ thể; không cần raw type, unchecked cast hay thao tác runtime không an toàn.

## 13. Các lỗi thường gặp và cách giải quyết

| Mã hoặc tình huống | Lý do sai | Cách sửa |
| --- | --- | --- |
| `static T last;` trong `class Box<T>` | Trường static không được tham chiếu `T` lớp | Dùng kiểu cụ thể, hoặc chuyển dữ liệu thành field instance `T last`. |
| `static List<T> shared;` | `T` nằm sâu trong tham số kiểu nhưng vẫn là `T` của lớp | Dùng `List<String>` nếu hợp đồng chung thật sự là String, hoặc thiết kế kho lưu riêng theo kiểu. |
| `static final T DEFAULT = ...;` | `final` không thay đổi ngữ cảnh static | Đổi thành kiểu cụ thể hoặc tạo instance field. |
| `static T echo(T x)` | Phương thức không có `T` lớp | Khai báo `static <U> U echo(U x)` khi cần hành vi độc lập. |
| `static <T> T echo(T x)` được hiểu là dùng `T` lớp | `<T>` mới **che khuất** tham số kiểu lớp | Đặt tên `<U>` để thể hiện tham số thuộc phương thức. |
| `static void show() { System.out.println(value); }` | Trường `value` là instance member | Nhận một `Box<U>` làm tham số, hoặc chuyển `show` thành instance method. |
| `static void show() { System.out.println(this); }` | Không có `this` trong static context | Gọi qua đối tượng rõ ràng. |
| `static class Nested { T data; }` bên trong `Outer<T>` | Static nested class không dùng `T` của Outer | Tạo `Nested<U>` với type parameter riêng hoặc dùng non-static inner class. |
| `Outer<String>.Nested<Integer>` | Static nested class không thuộc một `Outer<String>` cụ thể | Dùng `Outer.Nested<Integer>`. |
| Chờ bộ đếm static riêng cho `Box<String>` và `Box<Integer>` | Cả hai sử dụng cùng lớp runtime | Truyền khóa phân nhóm riêng hoặc lưu state trong đối tượng. |
| Dùng `new T()`, `T.class` trong static generic method | Type parameter thường không reifiable | Truyền factory hoặc type token phù hợp. |
| Dùng raw `Box` chỉ để gọi static method | Raw type làm mất kiểm tra generic ở những phần khác | Gọi `Box.of(...)` hoặc `Box.createdCount()` qua tên lớp. |

### Quy tắc sửa theo mục đích

Nếu hành vi cần đọc/sửa trạng thái của một đối tượng `Box<T>`, hãy viết **instance method**: `T get()`, `void set(T item)`. Nếu hành vi độc lập và chỉ cần xử lý kiểu do mỗi lần gọi quyết định, hãy viết **static generic method**: `static <U> U identity(U item)`. Nếu dữ liệu cần chia sẻ thật sự giữa tất cả đối tượng, hãy dùng **static field có kiểu cụ thể** và xác định rõ cơ chế đồng bộ nếu có truy cập đa luồng.

Đừng giải quyết lỗi compiler bằng cách xóa hết type arguments hoặc ép kiểu từ `Object`. Những cách đó thường làm mất tính an toàn kiểu mà generics đang bảo vệ.

## 14. Câu hỏi tự kiểm tra

**Câu 1 — Phân loại.** Với `class Cache<T>`, đánh dấu những khai báo nào hợp lệ và giải thích:

```java
class Cache<T> {
    T latest;                      // A
    static int hits;               // B
    // static T shared;            // C: cố tình comment.
    static <U> U echo(U value) {    // D
        return value;
    }
}
```

Đáp án định hướng: A hợp lệ (instance field), B hợp lệ (static với kiểu cụ thể), C không hợp lệ (static sử dụng `T` lớp), D hợp lệ (`U` thuộc phương thức static).

**Câu 2 — Kết quả bộ đếm.** Một lớp generic có `static int instances` tăng mỗi lần tạo đối tượng. Sau khi tạo hai `Box<String>` và ba `Box<Integer>`, số bộ đếm là bao nhiêu? Đáp án: `5` nếu không có đối tượng khác hay lần khởi tạo nào khác làm tăng bộ đếm; tham số kiểu không chia tách static field.

**Câu 3 — Sửa lỗi kiểu.** Chuyển phương thức bị comment sang phiên bản đúng mà vẫn giữ quan hệ đầu vào–đầu ra:

```java
class Factory<T> {
    // static T create(T input) { return input; } // Sai.

    static <U> Factory<U> create(U input) {
        return new Factory<>(input);
    }

    private final T value;
    Factory(T value) { this.value = value; }
    T get() { return value; }
}
```

Giải thích vì sao type parameter của `create` phải là `U` riêng và kết quả là `Factory<U>`.

**Câu 4 — Nested và inner.** Viết `Outer<T>` có `static class Nested<U>` và `class Inner`. Lớp nào được dùng `T` của `Outer<T>`? Tại sao `Outer<String>.Inner` cần một instance `Outer<String>` để tạo ra?

**Câu 5 — Factory có bound.** Viết `static <N extends Number> Box<Double> doubleBox(N number)` trong một lớp generic. Dùng `number.doubleValue()` để tạo kết quả; giải thích tại sao `N` thuộc về phương thức và `Box<Double>` là kiểu kết quả cụ thể.

**Câu 6 — Tư duy thiết kế.** Bạn muốn cache chung cho mọi đối tượng nhưng mỗi kiểu dữ liệu có danh sách riêng. Tại sao `static List<T> values` không hợp lệ? Đề xuất một API có khóa kiểu (`Class<?>`) và thảo luận sự cần thiết của kiểm tra kiểu khi lấy dữ liệu từ một map lưu trữ dị thể. Không được giả định rằng type token tự làm phép ép kiểu generic container an toàn tuyệt đối.

## 15. Checklist ghi nhớ

- `T` khai báo ở `class Name<T>` thuộc về **lớp generic**, được sử dụng trong trường, constructor và phương thức **instance**.
- Thành viên `static` không có một `T` của lớp để dùng; `static T field`, `static T method(T input)` và `static List<T> field` đều không hợp lệ.
- `static <U> U method(U input)` hoàn toàn hợp lệ vì `U` được khai báo bởi **chính phương thức**.
- Trường `static String`, `static int` và `static List<String>` hợp lệ vì đó là các kiểu cụ thể, không phụ thuộc `T` của lớp.
- Trường `static` được chia sẻ giữa mọi cách tham số hóa `Box<T>`; Java không tạo một bộ static data cho từng `T`.
- Static nested class có thể generic bằng tham số **riêng** `<U>`; non-static inner class mới có thể dùng `T` của enclosing generic instance.
- Dùng instance method khi thao tác thuộc trạng thái đối tượng; dùng static generic method hoặc static factory khi thao tác độc lập với đối tượng.

Khi gặp lỗi compiler về tham chiếu `T` trong static context, hãy xác định **nơi `T` được khai báo** và **thành viên có gắn với đối tượng hay không**. Chỉ cần phân biệt hai phạm vi này là có thể sửa đúng nhiều lỗi cú pháp generics mà vẫn giữ kiểm tra kiểu ngay từ lúc biên dịch.

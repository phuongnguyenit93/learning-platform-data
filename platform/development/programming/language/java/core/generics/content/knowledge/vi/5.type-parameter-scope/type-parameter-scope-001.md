# Phạm vi tham số kiểu của lớp, giao diện và phương thức trong Java Generics

Khi nhìn thấy `T` trong mã Java, ta cần xác định **`T` được khai báo ở đâu và dùng được trong phạm vi nào**. Ví dụ `class Box<T>` khai báo một tham số kiểu của lớp; `interface Source<T>` khai báo tham số kiểu của giao diện; còn `static <T> T identity(T value)` khai báo tham số kiểu **riêng của phương thức**. Những tên này có thể trông giống nhau nhưng không đương nhiên là cùng một tham số kiểu.

Phạm vi (*scope*) giúp trình biên dịch giải quyết một tên kiểu thành đúng khai báo, từ đó kiểm tra chữ ký phương thức, constructor, kiểu trường, kế thừa và lời gọi. Hiểu đúng phạm vi đặc biệt quan trọng khi dùng `static`, viết phương thức generic bên trong lớp generic, khai báo lớp lồng nhau hoặc đặt tên tham số kiểu trùng nhau.

## 1. Phạm vi tham số kiểu nghĩa là gì?

**Tham số kiểu** (*type parameter*) là một tên kiểu được giới thiệu bởi một khai báo generic, thường viết trong dấu `<...>`:

```java
class Box<T> { ... }

interface Reader<T> { ... }

static <T> T identity(T value) { ... }
```

Ba dòng trên là **phác thảo cú pháp độc lập**, trong đó `...` không phải Java hoàn chỉnh để biên dịch. Ở cả ba nơi, `<T>` khai báo một tên mới. Trình biên dịch tìm đúng khai báo tương ứng mỗi khi nó gặp một lần sử dụng `T`.

Trong nội dung này, cần tách ba câu hỏi:

1. **Phạm vi tên**: vị trí mã nguồn nào có thể tham chiếu tới tham số kiểu đã khai báo?
2. **Ngữ cảnh hợp lệ**: kể cả khi ở trong cùng lớp, có được dùng tham số kiểu của lớp ở thành phần `static` hay không?
3. **Kiểu tại nơi sử dụng**: khi tạo `Box<String>`, trình biên dịch hiểu `T` theo `String` trong hợp đồng của lần sử dụng đó như thế nào?

Ba câu hỏi liên quan nhưng không trùng nhau. Một khai báo lớp có thể bao gồm phương thức `static` về mặt cấu trúc, nhưng phương thức `static` **không thể dùng trực tiếp tham số kiểu của lớp**. Đồng thời, khai báo `T` chỉ tồn tại theo quy tắc kiểm tra kiểu ở mã nguồn; không đồng nghĩa JVM lưu đối số kiểu của từng đối tượng như một kiểu runtime tách biệt.

| Khai báo | Ai sở hữu tham số kiểu? | Những vị trí thường dùng được | Giới hạn đáng chú ý |
|---|---|---|---|
| `class Box<T>` | Khai báo lớp `Box` | Trường instance, constructor, phương thức instance, thành phần trong instance context | Thành phần `static` không được dùng trực tiếp `T` của lớp. |
| `interface Source<T>` | Khai báo interface `Source` | Chữ ký phương thức instance, phương thức `default` và phương thức instance `private` | Trường trong interface là `static final`; phương thức `static` không được dùng trực tiếp `T` của interface. |
| `<T> T method(T value)` | Riêng khai báo phương thức | Kiểu trả về, tham số, bound và thân phương thức đó | `T` không tự mở rộng sang các phương thức khác. |
| `<U> Constructor(U x)` | Riêng constructor generic | Chữ ký và thân constructor đó | `U` của constructor độc lập với tham số kiểu của lớp. |

Các phần sau sẽ đi lần lượt từ lớp, giao diện đến phương thức và đối chiếu trong một chương trình chạy được.

## 2. Tham số kiểu của lớp: `class Box<T>`

Xét khai báo:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void printWith(T other) {
        System.out.println(value + " / " + other);
    }
}
```

Ở đây `T` được khai báo tại `class Box<T>`. Những lần dùng `T` ở trường `value`, tham số constructor, kết quả `get()` và tham số `printWith(T other)` đều tham chiếu tới **cùng tham số kiểu của lớp**.

Nếu sử dụng:

```java
Box<String> words = new Box<>("Java");
String value = words.get();
words.printWith("Generics");
```

thì đối số kiểu `String` được áp vào các vị trí vốn dùng `T` trong hợp đồng của `Box<String>`. `words.printWith(123)` không được chấp nhận vì `123` không phù hợp `String`.

Trong một phương thức **instance** của `Box<T>`, ta có thể khai báo biến cục bộ mang kiểu `T`:

```java
T copy() {
    T result = value;
    return result;
}
```

Đây là **phương thức minh họa đặt bên trong `Box<T>`**, không phải chương trình chạy độc lập. `T` vẫn có ý nghĩa dù phương thức `copy` không tự khai báo `<T>`, vì phương thức instance đang dùng tham số kiểu của lớp bao quanh.

### Vì sao `static` là ngoại lệ quan trọng?

Một thành phần `static` thuộc về chính lớp `Box` chứ không gắn với một instance `Box<String>` hoặc `Box<Integer>` cụ thể. Vì vậy mã sau **sai**:

```java
class WrongBox<T> {
    // static T shared;                  // Sai: tham chiếu T của lớp từ static field
    // static T getShared() { ... }      // Sai: T của lớp trong static method
}
```

Ngay cả khi các dòng bị chú thích nằm trong phạm vi khai báo của lớp, chúng không hợp lệ trong ngữ cảnh `static`. Điều này thường được gọi là lỗi **“non-static type variable T cannot be referenced from a static context”**.

Cách sửa là sử dụng một kiểu cụ thể hoặc để phương thức `static` khai báo **tham số kiểu riêng**:

```java
static <U> Box<U> of(U value) {
    return new Box<>(value);
}
```

Đoạn trên là một **phương thức đặt trong lớp `Box<T>`**. `U` thuộc riêng phương thức `of`; nó không phải `T` của lớp. Khi gọi `Box.of("Java")`, Java có thể suy luận `U = String` và trả `Box<String>`.

## 3. Ví dụ chạy được: lớp generic, phương thức instance và phương thức static

Tạo tệp **`ClassScopeDemo.java`**:

```java
public class ClassScopeDemo {
    static final class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        <U> String describe(U label) {
            return label + ":" + value;
        }

        static <U> Holder<U> of(U value) {
            return new Holder<>(value);
        }

        final class Reader {
            T read() {
                return value;
            }
        }

        static final class Info {
            static String name() {
                return "Holder";
            }
        }
    }

    public static void main(String[] args) {
        Holder<String> text = Holder.of("Java");
        Holder<Integer> number = Holder.of(21);

        System.out.println(text.get());
        System.out.println(text.describe(17));
        System.out.println(text.new Reader().read());
        System.out.println(number.get() + 1);
        System.out.println(Holder.Info.name());
    }
}
```

Biên dịch và chạy trên Java 17 trở lên:

```bash
javac -encoding UTF-8 ClassScopeDemo.java
java ClassScopeDemo
```

Kết quả `stdout`:

```text
Java
17:Java
Java
22
Holder
```

Phân tích từng phạm vi:

- `Holder<T>` giới thiệu tham số kiểu của **lớp**.
- `T get()` sử dụng `T` của lớp, không cần khai báo tham số kiểu mới ở phương thức.
- `<U> String describe(U label)` khai báo `U` của **phương thức instance**, đồng thời vẫn dùng trường `value` có kiểu `T` của lớp. Khi gọi `text.describe(17)`, `U` có thể là `Integer` trong khi `T` của `text` vẫn là `String`.
- `static <U> Holder<U> of(U value)` không phụ thuộc `T` của một instance; nó có tham số kiểu `U` riêng.
- Lớp **inner không static** `Reader` có thể dùng `T` của `Holder<T>` bao quanh. Vì cần một đối tượng bao ngoài, ta tạo bằng `text.new Reader()`.
- Lớp lồng **static** `Info` không dùng `T` của lớp bao ngoài; nó hoạt động độc lập và có thể được gọi qua `Holder.Info.name()`.

Ví dụ cho thấy một lớp generic có thể chứa nhiều tên tham số kiểu thuộc những khai báo độc lập. Không cần để tất cả phương thức đều dùng cùng tên `T`.

## 4. Tham số kiểu của giao diện: `interface Source<T>`

Một interface generic giới thiệu tham số kiểu để các phương thức instance cùng tuân theo một hợp đồng:

```java
interface Source<T> {
    T read();

    void accept(T value);

    default boolean sameReference(T value) {
        return read() == value;
    }
}
```

`T` ở `read()`, `accept(T value)` và `sameReference(T value)` thuộc **khai báo interface `Source<T>`**. Phương thức `default` vẫn là phương thức instance, vì vậy có thể dùng `T` của interface và gọi phương thức instance khác như `read()`.

Một lớp triển khai có thể **chốt đối số kiểu**:

```java
final class StringSource implements Source<String> {
    private String value = "";

    @Override
    public String read() {
        return value;
    }

    @Override
    public void accept(String value) {
        this.value = value;
    }
}
```

Ở đây `StringSource` **không khai báo tham số kiểu** cho chính nó. Nó chọn `String` làm đối số cho `Source<T>`, nên các phương thức thực hiện interface phải nhận/trả kiểu tương ứng.

Lớp triển khai cũng có thể tiếp tục generic:

```java
final class MemorySource<E> implements Source<E> {
    private E value;

    @Override
    public E read() {
        return value;
    }

    @Override
    public void accept(E value) {
        this.value = value;
    }
}
```

Trong trường hợp này, `E` của `MemorySource<E>` là tham số kiểu **mới của lớp**, được truyền vào lần sử dụng `Source<E>`. Tên `E` không bắt buộc trùng với `T` ở khai báo interface gốc.

### Thành phần `static` bên trong interface

Một interface có thể có phương thức `static`, nhưng phương thức đó **không thể dùng trực tiếp tham số kiểu `T` của interface**:

```java
interface Factory<T> {
    // static T create() { return null; } // Sai: dùng T của interface ở static context

    static <U> U identity(U value) {
        return value;
    }
}
```

`<U>` ở `identity` là tham số kiểu riêng của phương thức. Gọi bằng `Factory.identity("Java")` hoặc `Factory.<String>identity("Java")`.

Các **trường của interface** mặc định là `public static final`, nên cũng không thể có trường instance kiểu `T` trong một interface. Trường hợp cần lưu trạng thái kiểu `T`, ta đặt trường trong **lớp triển khai**.

## 5. Ví dụ hoàn chỉnh về phạm vi kiểu trong interface

Lưu tệp **`InterfaceScopeDemo.java`**:

```java
public class InterfaceScopeDemo {
    interface Repository<T> {
        void save(T value);
        T latest();

        default String describe() {
            return "latest=" + latest();
        }

        static <U> U identity(U value) {
            return value;
        }
    }

    static final class MemoryRepository<T> implements Repository<T> {
        private T value;

        @Override
        public void save(T value) {
            this.value = value;
        }

        @Override
        public T latest() {
            return value;
        }
    }

    public static void main(String[] args) {
        Repository<String> words = new MemoryRepository<>();
        words.save("generics");

        System.out.println(words.describe());
        System.out.println(Repository.identity(17) + 1);
        System.out.println(
                Repository.<String>identity("Java").toUpperCase());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 InterfaceScopeDemo.java
java InterfaceScopeDemo
```

`stdout`:

```text
latest=generics
18
JAVA
```

`Repository<T>` có hợp đồng instance dùng `T`. `MemoryRepository<T>` khai báo tham số kiểu riêng cho lớp triển khai và truyền tham số đó sang `Repository<T>`. Phương thức `Repository.identity` lại khai báo `<U>` riêng vì là thành phần `static` của interface.

Lưu ý `Repository<T>` ở ví dụ chỉ mô tả một kho dữ liệu trong bộ nhớ để học generic; không có nghĩa API này tự thực hiện truy cập cơ sở dữ liệu. Phần quan trọng là **phạm vi và quan hệ kiểu** giữa khai báo interface, lớp triển khai và lời gọi phương thức.

## 6. Tham số kiểu của phương thức: `<T>` có phạm vi riêng

Một phương thức generic tự khai báo danh sách tham số kiểu của nó **ngay trước kiểu trả về**:

```java
static <T> T first(T a, T b) {
    return a;
}
```

Trong chữ ký này, `<T>` thuộc riêng phương thức `first`. Nó dùng được ở kiểu tham số `a`, `b`, kiểu trả về và trong thân phương thức. Các phương thức khác không tự động biết tên `T` đó.

Một phương thức instance cũng có thể khai báo tham số kiểu riêng:

```java
<U> String format(U prefix) {
    return prefix.toString();
}
```

Đây là **phương thức minh họa trong một lớp**. Nó không cần `static` mới được gọi là generic: dấu hiệu quyết định là nó khai báo `<U>`.

Khác biệt:

| Phương thức | Có tự khai báo tham số kiểu? | Nguồn tham số kiểu |
|---|---|---|
| `T get()` trong `class Box<T>` | Không | `T` thuộc lớp `Box<T>`. |
| `<U> U echo(U value)` | Có | `U` thuộc riêng phương thức `echo`. |
| `static <U> U identity(U value)` | Có | `U` thuộc riêng phương thức `static`. |
| `void set(T value)` trong `class Box<T>` | Không | `T` thuộc lớp; phương thức dùng lại. |
| `<K,V> V choose(K key,V value)` | Có | `K` và `V` đều thuộc phương thức. |

**Một phương thức generic có thể nằm trong lớp không generic.** Chẳng hạn một lớp tiện ích bình thường có thể khai báo `static <T> T identity(T value)`.

### Lời gọi khác nhau có thể suy luận kiểu khác nhau

```java
String text = Utils.identity("Java");
Integer version = Utils.identity(17);
```

Đây là **đoạn minh họa** giả sử `Utils` có phương thức `static <T> T identity(T value)`. Trình biên dịch suy luận `T` ở từng lời gọi, chứ không thay đổi hay khai báo lại phương thức trong mã nguồn.

Có thể chỉ định đối số kiểu tường minh:

```java
String text = Utils.<String>identity("Java");
```

Dấu `<String>` nằm trước tên phương thức là **đối số kiểu lúc gọi**. Còn `<T>` trong khai báo phương thức là **tham số kiểu được khai báo**.

## 7. Ví dụ chạy được: nhiều phương thức generic độc lập

Lưu tệp **`MethodScopeDemo.java`**:

```java
public class MethodScopeDemo {
    static <T> T first(T left, T right) {
        return left;
    }

    static <T extends Comparable<? super T>> T larger(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    static <K, V> String label(K key, V value) {
        return key + "=" + value;
    }

    static final class Folder<T> {
        private final T item;

        Folder(T item) {
            this.item = item;
        }

        <U> String describe(U prefix) {
            return prefix + ":" + item;
        }

        static <U> Folder<U> of(U item) {
            return new Folder<>(item);
        }
    }

    public static void main(String[] args) {
        System.out.println(first("A", "B"));
        System.out.println(larger(5, 9));
        System.out.println(label("id", 42));

        Folder<Integer> folder = Folder.of(7);
        System.out.println(folder.describe("number"));
        System.out.println(Folder.of("X").describe(2026));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 MethodScopeDemo.java
java MethodScopeDemo
```

`stdout`:

```text
A
9
id=42
number:7
2026:X
```

Hai phương thức `first` và `larger` đều đặt tên tham số kiểu là `T`, nhưng đó là **hai khai báo độc lập**. Giới hạn `T extends Comparable<? super T>` của `larger` không áp dụng cho `first`. Tương tự, `T` của `Folder<T>` và `U` của `describe` không phải một tham số kiểu.

Việc dùng tên `T` nhiều lần ở các phạm vi khác nhau là hợp lệ. Tuy nhiên, khi các khai báo lồng nhau quá sâu, nên dùng tên rõ ràng để tránh hiểu nhầm.

## 8. Đặt tên trùng nhau và hiện tượng che khuất (*shadowing*)

Một phương thức generic **có thể** khai báo tham số kiểu cùng tên với tham số kiểu của lớp bao quanh:

```java
class Envelope<T> {
    private final T data;

    Envelope(T data) {
        this.data = data;
    }

    T get() {
        return data;
    }

    <T> T echo(T value) {
        return value;
    }
}
```

Trong phương thức `echo`, `T` ở `<T> T echo(T value)` thuộc **phương thức** và che khuất tham số kiểu cũng tên của lớp `Envelope<T>`. Nó **không phải** loại dữ liệu đang được lưu trong `data`.

Chạy ví dụ hoàn chỉnh **`ShadowingDemo.java`**:

```java
public class ShadowingDemo {
    static final class Envelope<T> {
        private final T data;

        Envelope(T data) {
            this.data = data;
        }

        T get() {
            return data;
        }

        <T> T echo(T input) {
            return input;
        }

        <U> String describe(U label) {
            return label + ":" + data;
        }
    }

    public static void main(String[] args) {
        Envelope<String> envelope = new Envelope<>("Java");
        Integer result = envelope.echo(10);

        System.out.println(envelope.get());
        System.out.println(result + 1);
        System.out.println(envelope.describe("item"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ShadowingDemo.java
java ShadowingDemo
```

`stdout`:

```text
Java
11
item:Java
```

`Envelope<String>` lưu chuỗi, nhưng `envelope.echo(10)` vẫn trả về `Integer` vì phương thức này có **`<T>` riêng che khuất `T` của lớp**.

Thiết kế như vậy hợp lệ nhưng dễ gây nhầm lẫn. Thông thường nên tránh khai báo trùng tên ở phạm vi lồng nhau. Viết `<U> U echo(U input)` làm rõ đây là một tham số kiểu khác, đồng thời giữ tên `T` của lớp cho phần dữ liệu lưu trữ.

**Không thể giả định hai chữ `T` là cùng tham số kiểu chỉ vì viết giống nhau.** Phải tìm vị trí khai báo gần nhất được phép nhìn thấy trong phạm vi hiện tại.

## 9. Lớp lồng nhau: `inner class` và `static nested class`

Giả sử:

```java
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    class Inner {
        T read() {
            return value;
        }
    }

    static class Nested<U> {
        private final U item;

        Nested(U item) {
            this.item = item;
        }

        U read() {
            return item;
        }
    }
}
```

Đây là **khai báo lớp minh họa độc lập**. Hai lớp lồng khác nhau:

- `Inner` là **non-static inner class**. Mỗi đối tượng `Inner` có liên hệ với một đối tượng `Outer<T>` bao ngoài, nên phương thức instance của `Inner` có thể dùng tham số kiểu `T` và trường `value` của đối tượng bao ngoài.
- `Nested<U>` là **static nested class**, có tham số kiểu `U` của **chính nó**. Nó không được dùng trực tiếp `T` của `Outer<T>`, vì bản thân `Nested` không gắn với đối tượng `Outer<T>` cụ thể.

Cách tạo tương ứng (đặt trong một phương thức):

```java
Outer<String> outer = new Outer<>("Java");
Outer<String>.Inner inner = outer.new Inner();
String a = inner.read();

Outer.Nested<Integer> nested = new Outer.Nested<>(5);
Integer b = nested.read();
```

`Outer<String>.Inner` biểu thị kiểu inner class gắn với cách tham số hóa `Outer<String>`. `Outer.Nested<Integer>` dùng tham số kiểu `U` của static nested class, không phụ thuộc `T` của lớp bao.

Không viết `Outer<String>.Nested<Integer>`: static nested class được truy cập qua tên của lớp bao ở dạng không tham số hóa, vì bản thân nó không thuộc một đối tượng `Outer<String>`.

Nếu inner class tự khai báo một tham số kiểu cùng tên `T` thì có thể xuất hiện che khuất, tương tự trường hợp phương thức ở phần trước. Vì vậy cách đặt tên tham số kiểu của các lớp lồng nhau ảnh hưởng trực tiếp tới khả năng đọc mã.

## 10. Constructor generic cũng có phạm vi riêng

Một constructor có thể khai báo tham số kiểu **khác với tham số kiểu của lớp**. Ví dụ sau sử dụng đầu vào kiểu `U` và hàm chuyển đổi để tạo giá trị kiểu `T` của lớp:

```java
import java.util.function.Function;

final class ConvertedBox<T> {
    private final T value;

    <U> ConvertedBox(
            U input,
            Function<? super U, ? extends T> converter) {
        this.value = converter.apply(input);
    }

    T get() {
        return value;
    }
}
```

Đây là **khai báo lớp minh họa**; nó cần import như ở đầu đoạn. `T` thuộc lớp `ConvertedBox<T>`, còn `U` chỉ thuộc constructor. Với ví dụ sử dụng bên trong phương thức:

```java
ConvertedBox<Integer> parsed =
        new ConvertedBox<>("123", Integer::parseInt);
System.out.println(parsed.get()); // 123
```

Constructor nhìn thấy cả `T` của lớp (trong kiểu đích `Function<? super U, ? extends T>`) lẫn `U` của chính constructor. Điều này giúp diễn đạt hai vai trò kiểu khác nhau: kiểu dữ liệu ban đầu và kiểu dữ liệu được lưu giữ.

Việc constructor generic có thể khai báo tham số kiểu riêng không làm thay đổi quy tắc: kiểu instance cuối cùng vẫn được mô tả bởi đối số kiểu của **lớp**, ví dụ `ConvertedBox<Integer>`.

## 11. Phạm vi trong giới hạn kiểu (*bounds*)

Tham số kiểu còn có thể được sử dụng ngay trong giới hạn kiểu của chính nó:

```java
static <T extends Comparable<T>> T max(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Đây là **phương thức minh họa bên trong một lớp**. `T` được khai báo trong `<T extends Comparable<T>>` và có thể tham chiếu trong giới hạn `Comparable<T>`. Đây là một mẫu **self-referential bound** hợp lệ, dùng khi muốn các giá trị kiểu `T` hỗ trợ so sánh với nhau.

Một dạng linh hoạt hơn thường gặp là:

```java
static <T extends Comparable<? super T>> T max(
        T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

`? super T` cho phép hợp đồng so sánh nhận `T` hoặc một kiểu cha thích hợp. Vẫn chỉ có **một khai báo `T` cho phương thức `max`**; những lần xuất hiện tiếp theo của `T` trong bound, tham số và kiểu trả về đều thuộc khai báo này.

Nếu viết `class Numeric<T extends Number>`, giới hạn ấy thuộc **tham số kiểu của lớp**, nên ràng buộc mọi cách sử dụng `Numeric<Integer>` hay `Numeric<Double>`. Nó không tự động áp vào một phương thức generic riêng khai báo `<U>`, trừ khi phương thức đó cũng có ràng buộc thích hợp.

## 12. Phạm vi kiểu không đồng nghĩa thông tin kiểu luôn tồn tại ở runtime

Một tên `T` hợp lệ trong phạm vi của lớp hoặc phương thức giúp **trình biên dịch** kiểm tra kiểu. Tuy nhiên, Java dùng **type erasure** cho phần lớn generics: khi biên dịch, tham số kiểu được xóa thành giới hạn phù hợp (hoặc `Object` khi không có bound), đồng thời compiler có thể thêm cast và bridge method để giữ hành vi kiểu.

Ví dụ:

```java
static <T> void showClass(T value) {
    System.out.println(value.getClass().getSimpleName());
}
```

Phương thức này có thể đọc **lớp runtime của đối tượng `value`** qua `getClass()`, nếu `value` không phải `null`. Nhưng điều đó **không** có nghĩa ta có thể lấy `T.class`:

```java
// Sai ngay cả khi T đã được khai báo trong phạm vi:
// Class<?> token = T.class;
// T instance = new T();
```

`T.class` và `new T()` không hợp lệ do tham số kiểu không tự cung cấp class literal hay constructor runtime có thể gọi theo cách này.

Nếu thuật toán cần biết kiểu runtime, hãy nhận một **type token** từ người gọi:

```java
static <T> boolean matches(Class<T> type, Object value) {
    return type.isInstance(value);
}
```

Đoạn này là **phương thức minh họa trong một lớp**; `String.class` có thể được truyền cho `Class<String>`:

```java
boolean yes = matches(String.class, "Java"); // true
boolean no = matches(String.class, 42);       // false
```

Hai lời gọi nằm trong một phương thức chứa hoặc tham chiếu tới `matches`. Tham số kiểu `T` vẫn có phạm vi riêng ở phương thức; đối tượng `Class<T>` được truyền vào mang thông tin runtime cần thiết để kiểm tra bằng `isInstance`.

Điều quan trọng là **lỗi dùng một tên ngoài phạm vi** và **hạn chế do type erasure** là hai loại vấn đề khác nhau. Chẳng hạn `static T get()` trong `class Box<T>` vi phạm quy tắc ngữ cảnh static; còn `new T()` không hợp lệ ngay cả bên trong phương thức instance đang nhìn thấy `T`.

## 13. Những sai lầm phổ biến về phạm vi

| Tình huống | Vì sao sai hoặc dễ nhầm? | Cách sửa |
|---|---|---|
| `class Box<T> { static T value; }` | Thành phần static không thể dùng `T` của lớp. | Dùng trường instance `T value` hoặc kiểu cụ thể cho trường static. |
| `class Box<T> { static T of(...) { ... } }` | Phương thức static không kế thừa `T` của lớp theo cách đó. | Khai báo `static <U> Box<U> of(U value)` nếu cần factory generic. |
| `interface Source<T> { static T get() { ... } }` | Phương thức static của interface không thể dùng `T` của interface. | Khai báo tham số kiểu riêng của phương thức hoặc chọn kiểu cụ thể. |
| `<T> T identity(T x)` được hiểu là dùng `T` của mọi lớp | `<T>` tự tạo một tham số kiểu của riêng phương thức. | Xem chính xác nơi khai báo và phạm vi. |
| Phương thức cùng tên `T` trong `class Box<T>` | Tham số kiểu phương thức che khuất tham số kiểu lớp. | Chọn tên `<U>` để biểu đạt sự độc lập. |
| Viết `T value;` trong một lớp không có khai báo `T` | Không tồn tại tên `T` trong phạm vi hợp lệ. | Dùng kiểu cụ thể hoặc khai báo tham số kiểu trên lớp/phương thức thích hợp. |
| `Outer<String>.Nested<Integer>` cho static nested class | Static nested class không thuộc một tham số hóa instance cụ thể của `Outer`. | Dùng `Outer.Nested<Integer>`. |
| Nghĩ `Inner` và `Nested` đều nhìn thấy `T` của `Outer<T>` | Chỉ inner class không static có thể dùng trực tiếp `T` của lớp bao trong ngữ cảnh phù hợp. | Với static nested class, khai báo tham số kiểu riêng nếu cần. |
| Dùng `new T()` khi `T` có trong phạm vi | Type erasure không cung cấp constructor của `T`. | Truyền `Supplier<T>` hoặc factory phù hợp. |
| Dùng `T.class` | Tham số kiểu không thể làm class literal. | Truyền `Class<T>` khi cần kiểm tra runtime. |
| Nghĩ hai `<T>` ở hai phương thức là cùng một biến kiểu | Mỗi danh sách tham số kiểu là khai báo riêng. | Xem từng chữ ký độc lập. |

### Cách đọc nhanh một đoạn mã generic

Khi gặp tên kiểu như `T`, `E`, `K` hoặc `V`, kiểm tra theo thứ tự:

1. Tìm **khai báo gần nhất** giới thiệu tên đó: `class X<T>`, `interface X<T>`, `<T> method(...)` hoặc constructor generic.
2. Xác định vị trí hiện tại là **instance** hay **static**. Nếu là static, không được dùng trực tiếp tham số kiểu của lớp/interface bao.
3. Xem có **tham số kiểu cùng tên** ở một phạm vi bên trong che khuất khai báo ngoài không.
4. Nếu đang trong **inner class**, kiểm tra khả năng truy cập kiểu từ lớp bao; nếu là **static nested class**, nó không được dùng trực tiếp tham số kiểu của lớp bao.
5. Phân biệt tên tham số kiểu trong **khai báo** và đối số kiểu ở **nơi sử dụng** như `Box<String>`.
6. Nếu gặp `new T()`, `T.class` hoặc kiểm tra loại tham số hóa tại runtime, xem lại giới hạn của type erasure.

## 14. Tự kiểm tra

**Câu 1.** Trong `class Store<T>`, vì sao `T get()` hợp lệ nhưng `static T getDefault()` không hợp lệ?

**Câu 2.** Với đoạn sau, chữ `T` ở `echo` thuộc khai báo nào?

```java
class Store<T> {
    <T> T echo(T value) {
        return value;
    }
}
```

**Câu 3.** `interface Mapper<I,O> { O map(I value); }` có thể khai báo `static I defaultInput()` không? Nếu cần một generic static method, phải làm gì?

**Câu 4.** Trong `class Outer<T>`, vì sao `class Inner` có thể dùng `T`, còn `static class Nested` không thể dùng trực tiếp `T` của `Outer<T>`?

**Câu 5.** Hai phương thức `static <T> T left(T x)` và `static <T> T right(T x)` có chia sẻ cùng một tham số kiểu `T` không?

**Câu 6.** `T.class` không hợp lệ trong phương thức đã khai báo `<T>` là do thiếu phạm vi hay do cách Java thực thi generics?

**Đáp án định hướng:**

1. `get()` là phương thức instance nên dùng được `T` của lớp; `getDefault()` là phương thức static, không gắn với cách tham số hóa instance.
2. `<T>` của phương thức `echo` tạo tham số mới che khuất `T` của lớp `Store<T>`.
3. Không, vì `I` thuộc interface. Hãy khai báo tham số kiểu riêng như `static <U> U identity(U value)`.
4. Inner class không static gắn với đối tượng lớp bao; static nested class độc lập với tham số kiểu của lớp bao.
5. Không. Mỗi phương thức khai báo `<T>` riêng.
6. Do hạn chế liên quan đến type erasure/reifiability tại runtime, không phải do `T` nằm ngoài phạm vi.

**Ghi nhớ:** Phạm vi tham số kiểu được xác định bởi **nơi nó được khai báo**. Tham số kiểu của lớp/interface dùng được trong những hợp đồng instance phù hợp; phương thức generic và constructor generic có tham số kiểu riêng; thành phần `static` không lấy trực tiếp tham số kiểu của lớp hoặc interface; khai báo lồng nhau có thể che khuất tên bên ngoài. Phân biệt rõ các quy tắc này sẽ giúp đọc và viết Java Generics chính xác, đặc biệt trong code có nhiều lớp, interface và utility method.

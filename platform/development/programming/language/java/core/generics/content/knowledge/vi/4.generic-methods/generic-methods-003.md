# Phân biệt phương thức có tham số kiểu riêng với phương thức dùng `T` của lớp

Java cho phép khai báo **tham số kiểu trên lớp** và **tham số kiểu riêng trên phương thức**. Hai cách có thể xuất hiện trong cùng một class, nhưng có phạm vi và ý nghĩa khác nhau. Trong `class Box<T>`, phương thức `T get()` **dùng `T` của lớp** nên không tự khai báo type parameter. Còn phương thức `<U> U echo(U input)` **là generic method**, tự khai báo `U` và có thể suy luận một kiểu `U` mới cho từng lời gọi.

Mục tiêu của bài học: đọc đúng hai dạng chữ ký, chọn nơi khai báo type parameter, hiểu kiểu được xác định lúc sử dụng, dùng phương thức `static` hợp lệ, kết hợp `T` của lớp với `R` của method, và tránh lỗi che khuất tên type parameter. Các ví dụ theo Java 17 trở lên.

## 1. Khác biệt nằm ở nơi khai báo

```java
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

    <U> U echo(U input) {
        return input;
    }
}
```

`<T>` ngay sau `Box` **khai báo một tham số kiểu thuộc class**. Field `T value`, constructor `Box(T)`, `get()` và `set(T)` đều sử dụng `T` ấy. `get()` và `set()` **không phải generic method theo nghĩa tự khai báo type parameter**: không có `<...>` riêng trước kiểu trả về.

Ngược lại, `<U>` đứng trước kiểu trả về `U` trong `<U> U echo(U input)` là phần khai báo type parameter **của chính method**. `U` độc lập với `T`: khi một `Box<String>` gọi `echo(42)`, trình biên dịch có thể suy luận `U = Integer` mà không đổi `T = String`.

```java
Box<String> text = new Box<>("Java");
String a = text.get();           // T của lớp = String.
text.set("Generics");            // Phải truyền String.
// text.set(42);                 // Lỗi biên dịch: set đòi String.

Integer b = text.echo(42);       // U của lần gọi này = Integer.
Boolean c = text.echo(true);     // U của lần gọi khác = Boolean.
```

Các đoạn code ngắn này là minh họa trong cùng ngữ cảnh khai báo `Box<T>`; ví dụ `Main.java` hoàn chỉnh nằm ở phần 5.

| Tiêu chí | Dùng `T` của lớp | Tự khai báo type parameter của method |
| --- | --- | --- |
| Vị trí khai báo | `class Box<T>` | `<U>` trước kiểu trả về |
| Ví dụ | `T get()`, `void set(T)` | `<U> U echo(U input)` |
| Phạm vi kiểu | Dùng chung trong các instance member của `Box<T>` | Chỉ trong chữ ký và thân method khai báo nó |
| Chọn kiểu như thế nào? | Theo `Box<String>`, `Box<Integer>`… | Thường suy luận tại **mỗi lời gọi** |
| Có thể là static? | Không được tham chiếu `T` class trực tiếp từ static member | Có, nếu static method tự khai báo `<U>` |
| Quan hệ với state của object | Có thể đọc/ghi field `T` | Chỉ liên hệ với state khi chữ ký/thân method biểu diễn rõ quan hệ |

**Tiêu chí nhận biết nhanh:** nhìn phần khai báo ngay trước kiểu trả về. Việc xuất hiện một chữ `T` trong kiểu trả về hoặc tham số **chưa đủ** để kết luận method tự generic.

## 2. Phương thức sử dụng `T` của lớp

```java
final class Holder<T> {
    private T current;

    Holder(T initial) {
        this.current = initial;
    }

    T read() {
        return current;
    }

    void replace(T next) {
        current = next;
    }
}
```

Tại nơi sử dụng:

```java
Holder<String> name = new Holder<>("An");
String old = name.read();
name.replace("Bình");
// name.replace(18); // Sai: kiểu T của tham chiếu là String.

Holder<Integer> age = new Holder<>(18);
Integer value = age.read();
age.replace(21);
```

Cùng một định nghĩa `Holder<T>` tái sử dụng cho cả chuỗi và số, nhưng bên gọi được kiểm tra theo **đối số kiểu của từng tham chiếu**. Tham số kiểu `T` gắn với hợp đồng của `Holder<T>`: `replace` phải nhận đúng kiểu mà `read` trả về.

Tình huống nhiều type parameter cũng tương tự:

```java
class Pair<K, V> {
    private final K key;
    private final V value;

    Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() {
        return key;
    }

    V value() {
        return value;
    }
}
```

Cả `key()` và `value()` dùng type parameter được khai báo trên `Pair<K,V>`, **không tự khai báo generic type parameter**. Đối với `Pair<String,Integer>`, kiểu trả về lần lượt là `String` và `Integer`.

Một constructor thông thường của generic class có thể nhận `T` của lớp mà **không phải constructor generic riêng**. Constructor chỉ là generic constructor nếu chính nó khai báo danh sách type parameter riêng trước tên constructor.

## 3. Phương thức tự generic dù lớp không generic

Lớp thông thường không cần khai báo type parameter để chứa generic method:

```java
class ArrayTools {
    static <E> E first(java.util.List<E> xs) {
        return xs.get(0);
    }
}
```

Ở đây `E` chỉ tồn tại trong `first`. Khi truyền `List<String>`, kết quả có kiểu tĩnh `String`; khi truyền `List<Integer>`, kết quả có thể là `Integer`. Bài này dùng ví dụ để **đối chiếu với `T get()` của generic class**, chứ không yêu cầu class `ArrayTools` phải có `<E>` ở tên lớp.

## 4. Kết hợp `T` của class với `<R>` riêng của method

Nhiều API cần giữ kiểu dữ liệu đang lưu trong object nhưng trả một kiểu khác sau khi biến đổi:

```java
import java.util.function.Function;

final class TransformBox<T> {
    private final T value;

    TransformBox(T value) {
        this.value = value;
    }

    <R> R transform(Function<? super T, ? extends R> converter) {
        return converter.apply(value);
    }
}
```

`T` khai báo ở **class**: đầu vào của converter phải xử lý được đối tượng `T` đang lưu. `<R>` khai báo ở **method**: kết quả có thể thay đổi tùy lần gọi.

```java
TransformBox<String> box = new TransformBox<>("Java");
String upper = box.transform(String::toUpperCase);
Integer length = box.transform(String::length);
```

`T` luôn là `String` trong hai lời gọi, còn `R` lần lượt là `String` và `Integer`. `String::length` trả `int`, và boxing giúp kết quả phù hợp với `Integer`.

Trong chữ ký `Function<? super T, ? extends R>`:

- `? super T` cho phép converter chấp nhận `T` hoặc một kiểu cha phù hợp, nghĩa là có thể **tiêu thụ** giá trị đang lưu.
- `? extends R` cho phép converter trả `R` hoặc subtype của `R`, nghĩa là có thể **sản xuất** kết quả tương thích.
- `R transform(...)` liên kết đầu ra với method-level type parameter; không thay đổi type argument `T` của object.

Một ví dụ khác là kết hợp `T` và `U` trong kiểu trả về:

```java
record Tuple<A, B>(A first, B second) {}

class TupleMaker<T> {
    private final T saved;

    TupleMaker(T saved) {
        this.saved = saved;
    }

    <U> Tuple<T, U> pairWith(U extra) {
        return new Tuple<>(saved, extra);
    }
}
```

`TupleMaker<String>.pairWith(7)` suy luận `U = Integer`, trả `Tuple<String,Integer>`. Đây là mối quan hệ kiểu hữu ích: phần thứ nhất có kiểu `T` của object, phần thứ hai có kiểu riêng của lời gọi. Đoạn minh họa không phải chương trình chạy độc lập.

## 5. Ví dụ hoàn chỉnh: một class có cả hai kiểu phương thức

Tạo tệp tên chính xác **`Main.java`** với toàn bộ code bên dưới. Chương trình minh họa phương thức dùng `T` của class, method `<R>` dùng cả `T` và `R`, method `<U>` độc lập với `T`, cùng một static generic method `<E>`.

```java
import java.util.List;
import java.util.function.Function;

public class Main {
    record Pair<L, R>(L left, R right) {}

    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T replacement) {
            this.value = replacement;
        }

        <R> R map(Function<? super T, ? extends R> mapper) {
            return mapper.apply(value);
        }

        <U> Pair<T, U> pairWith(U extra) {
            return new Pair<>(value, extra);
        }

        <U> U echo(U arg) {
            return arg;
        }

        static <E> E first(List<E> items) {
            if (items.isEmpty()) {
                throw new IllegalArgumentException("empty");
            }
            return items.get(0);
        }
    }

    public static void main(String[] args) {
        Box<String> text = new Box<>("Java");

        System.out.println("initial: " + text.get());
        System.out.println("upper: " + text.map(String::toUpperCase));
        System.out.println("length: " + text.map(String::length));

        Pair<String, Integer> pair = text.pairWith(7);
        System.out.println("pair: " + pair.left() + "/" + pair.right());

        System.out.println("echo: " + text.<Boolean>echo(true));
        System.out.println("first: " + Box.first(List.of(10, 20)));

        text.set("Generics");
        System.out.println("updated: " + text.get());

        Box<Integer> number = new Box<>(25);
        System.out.println("formatted: " + number.map(n -> "N=" + n));

        // text.set(42); // Không biên dịch: T của text là String.
    }
}
```

Biên dịch và chạy trên **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Stdout:

```text
initial: Java
upper: JAVA
length: 4
pair: Java/7
echo: true
first: 10
updated: Generics
formatted: N=25
```

### Đọc từng chữ ký trong ví dụ

| Phương thức | Nguồn của type parameter | Ý nghĩa đối với `Box<String> text` |
| --- | --- | --- |
| `T get()` | `T` thuộc class | Trả `String` |
| `void set(T)` | `T` thuộc class | Nhận `String`; không nhận `Integer` |
| `<R> R map(Function<? super T, ? extends R>)` | `T` thuộc class, `R` thuộc method | Đầu vào converter tương thích `String`, còn đầu ra theo `R` |
| `<U> Pair<T,U> pairWith(U)` | `T` thuộc class, `U` thuộc method | Trả cặp `String` và kiểu bổ sung |
| `<U> U echo(U)` | Chỉ `U` thuộc method | Cho phép `Boolean`, `Integer`... |
| `static <E> E first(List<E>)` | Chỉ `E` thuộc static method | Không phụ thuộc type argument của bất kỳ `Box` nào |

`text.<Boolean>echo(true)` minh họa **chỉ định type argument cho một instance generic method**, khác với `new Box<String>(...)` là chọn type argument của class. Phần `<Boolean>` sau dấu chấm không thay đổi `text` thành `Box<Boolean>`.

Dòng `text.set("Generics")` cập nhật field qua method dùng `T` của class. Ngược lại, `echo` chỉ trả nguyên đối số mà nó nhận: `text.echo(42)` không khiến `text` đổi kiểu hay trở thành `Box<Integer>`.

## 6. Static method và phạm vi `T`

Một method `static` thuộc class, nên không được truy cập trực tiếp type variable `T` của `class Box<T>` như thể đó là tham số kiểu sẵn có cho static context:

```java
class Box<T> {
    // static T bad(T input) { return input; } // Không hợp lệ.
    static <U> U ok(U input) { return input; } // Hợp lệ.
}
```

`U` được khai báo bởi chính static method; nó không phụ thuộc vào type argument của một instance `Box<String>` hoặc `Box<Integer>`.

## 7. Che khuất tên: `<T>` trên method không phải `T` class

Java **cho phép** một method khai báo tham số kiểu tên `T` ngay trong `class Container<T>`. Khi đó `T` trên method **che khuất** `T` của class trong phạm vi method:

```java
class ShadowDemo<T> {
    private T stored;

    ShadowDemo(T stored) {
        this.stored = stored;
    }

    <T> T echo(T value) {
        return value;
    }
}
```

Giả sử:

```java
ShadowDemo<String> demo = new ShadowDemo<>("Java");
Integer n = demo.echo(42); // Hợp lệ: T của echo = Integer.
```

Ở đây, kiểu của `stored` là `String` còn `T` trong `echo` là `Integer`. Hai tham số kiểu chỉ tình cờ **trùng tên**, không đồng nhất.

Tác hại tiềm ẩn: nếu người đọc tưởng `echo(T)` nhận kiểu của field `stored`, họ có thể viết caller sai hoặc implementation cần cast không an toàn. Nên đặt tên method-level parameter khác, ví dụ `<U> U echo(U value)`. Nếu mong method nhận đúng kiểu của field, **bỏ khai báo `<T>` trên method** và chỉ viết `T echo(T value)`.

Không cố gắng trả `stored` từ một method có `<T> T echo(...)` nếu chưa có ràng buộc thích hợp: `T` của field và `T` của method là hai biến kiểu khác nhau.

## 8. Type inference xảy ra ở hai điểm khác nhau

**Class-level inference:** `Box<String> x = new Box<>("Java")` dùng diamond `<>` để suy luận type argument của **class** từ ngữ cảnh. Khi gọi `x.get()`, `T` của class đã có ý nghĩa `String` trong kiểu của `x`.

**Method-level inference:** `x.echo(10)` suy luận type parameter riêng của `echo` tại **lời gọi ấy**, có thể thành `Integer` dù `x` là `Box<String>`. Nếu caller chọn `x.<Long>echo(10L)`, đó là explicit type argument của method, không đổi type argument của class.

Cơ chế type inference là phần của compiler, **không tạo specialized runtime class** cho mỗi cách dùng.

## 9. Bound của class và bound của method cũng độc lập

Nếu mọi object `NumberBox<T>` phải chứa số:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

Bound `T extends Number` khai báo ở **class**. `asDouble()` sử dụng khả năng `doubleValue()` do bound bảo đảm, nhưng nó vẫn **không là một generic method tự khai báo tham số mới**.

Nếu một phương thức độc lập chỉ cần đối số có `length()`:

```java
class TextTools {
    static <S extends CharSequence> int length(S value) {
        return value.length();
    }
}
```

Bound `<S extends CharSequence>` là **của method**, không đòi `TextTools` generic. Hai loại bound còn có thể kết hợp:

```java
class NumberBox<T extends Number> {
    private final T saved;

    NumberBox(T saved) {
        this.saved = saved;
    }

    <U extends CharSequence> String join(U suffix) {
        return saved + ":" + suffix;
    }
}
```

Ở đây `T` được cố định theo mỗi `NumberBox<T>`, còn `U` được chọn ở lời gọi `join`, nhưng phải là kiểu đáp ứng `CharSequence`.

## 10. Lỗi thường gặp và cách sửa

**Lỗi 1 — nhầm phương thức sử dụng `T` thành generic method:** `T get()` trong `Box<T>` dùng type parameter từ class; chỉ khi method tự viết `<U>` hoặc `<R>` trước kiểu trả về thì nó mới khai báo type parameter riêng.

**Lỗi 2 — viết `static T` với `T` chỉ thuộc class:** static method không có instance `T`. Hãy biến nó thành instance method nếu dùng state `T`, hoặc tự khai báo `static <U> U...` nếu thuật toán độc lập.

**Lỗi 3 — vô tình che khuất tên `T`:** viết `<T> T echo(T)` trong `class Box<T>` tạo type parameter **riêng**; ưu tiên `<U>` để dễ phân biệt hoặc bỏ `<T>` nếu muốn dùng type parameter lớp.

**Lỗi 4 — phương thức không có cơ chế bảo đảm kiểu đầu ra:** `<R> R read()` nếu chỉ ép từ `Object` mà không kiểm chứng có thể sinh unchecked warning và `ClassCastException`. Generics không biến dữ liệu thực thành kiểu caller kỳ vọng.

**Lỗi 5 — hai overload trùng erasure:** trong `class Clash<T>` với `T` không bound, hai method `void use(T value)` và `<U> void use(U value)` cùng bị xóa về `use(Object)`; chúng **không thể cùng tồn tại** với chữ ký như vậy. Cần chọn hợp đồng khác hoặc đổi tên method theo ý nghĩa.

**Lỗi 6 — dùng `U` ngoài phạm vi:** một method khai báo `<U>` không khiến field hay method khác được dùng `U`; nếu nhiều thành viên cần giữ cùng quan hệ kiểu, hãy khai báo tham số ở class hoặc interface.

**Lỗi 7 — tưởng type argument method đổi type của object:** `text.echo(42)` không đổi `Box<String>` thành `Box<Integer>`. Field `T` và method parameter `U` vẫn độc lập trừ khi chữ ký ràng buộc rõ.

**Lỗi 8 — nhầm generics với validation:** `Box<String>` vẫn có thể giữ `null` nếu code cho phép; `first(List<E>)` vẫn cần kiểm tra rỗng. Kiểm tra kiểu không thay thế ràng buộc dữ liệu nghiệp vụ.

**Lỗi 9 — cho rằng mỗi type argument tạo class runtime riêng:** Java dùng cơ chế *type erasure* cho phần lớn generics. `Box<String>` và `Box<Integer>` không tạo hai class runtime mới; method `<U>` cũng không được nhân bản một bytecode cho mỗi `U`.

## 11. Tự kiểm tra

**Câu 1:** `class Box<T> { T get() { ... } }` có generic method `get` không?

**Đáp án:** Không. `get()` chỉ sử dụng `T` của class. Nó không tự khai báo danh sách type parameter nào.

**Câu 2:** Trong `Box<String> text`, vì sao `text.set(10)` sai nhưng `Integer x = text.echo(10)` hợp lệ?

**Đáp án:** `set(T)` yêu cầu `String` theo class-level `T`; `echo` khai báo `<U>` riêng và suy luận `U = Integer`. Lời gọi `echo` không thay kiểu của object.

**Câu 3:** `<R> R map(Function<? super T, ? extends R>)` sử dụng bao nhiêu tham số kiểu và ở đâu?

**Đáp án:** Có `T` của class và `R` của method. Tương ứng, input của converter liên hệ kiểu dữ liệu đang lưu, output được xác định theo từng lời gọi.

**Câu 4:** Có thể khai báo `static <U> U identity(U value)` trong class không generic không?

**Đáp án:** Có. Type parameter `U` đã được method tự khai báo; class không cần `<U>`.

**Câu 5:** `class ShadowDemo<T> { <T> T echo(T x) { return x; } }` có dùng `T` class bên trong `echo` không?

**Đáp án:** Không. `T` method che khuất `T` class. Hãy đổi tên type parameter của method nếu muốn giữ rõ quan hệ.

**Câu 6:** Trong `Box<String> text`, lời gọi nào hợp lệ?

```java
// A: text.set(9);
// B: text.<Integer>echo(9);
// C: text.<Integer>echo("9");
```

**Đáp án:** B hợp lệ. A sai vì `set` yêu cầu `String`; C sai vì đã chỉ định `U = Integer` nhưng truyền `String`.

## Kết luận

**Phương thức sử dụng `T` của class** lấy quan hệ kiểu từ khai báo như `class Box<T>`; ví dụ `T get()` và `void set(T)`. **Generic method có tham số kiểu riêng** khai báo trực tiếp `<U>` hoặc `<R>` trước kiểu trả về; kiểu ấy có thể được suy luận cho mỗi lần gọi, kể cả khi class không generic. Khi cần biến đổi dữ liệu đang lưu, một method có thể kết hợp **`T` của class** và **`R` của method** trong cùng chữ ký. Đặt type parameter ở đúng phạm vi giúp hợp đồng kiểu rõ ràng, tránh lỗi static, shadowing và cast không an toàn.
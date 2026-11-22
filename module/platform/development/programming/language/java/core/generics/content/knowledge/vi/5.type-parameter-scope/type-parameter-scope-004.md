# Phương thức static khai báo tham số kiểu riêng trong Java Generics

Khi một lớp Java có dạng `class Container<T>`, tham số kiểu `T` thuộc **cách sử dụng lớp generic** như `Container<String>` hoặc `Container<Integer>`. Nhưng một phương thức `static` thuộc **lớp**, được gọi mà không cần chọn một đối tượng `Container<T>` cụ thể. Vì thế, phương thức static **không thể trực tiếp sử dụng tham số kiểu `T` khai báo ở mức lớp**. Nếu phương thức static cần làm việc tổng quát với các kiểu dữ liệu, nó phải **tự khai báo tham số kiểu riêng**, chẳng hạn:

```java
class Container<T> {
    static <U> U identity(U value) {
        return value;
    }
}
```

Ở đây `T` là tham số kiểu của **lớp**, còn `U` là tham số kiểu của **phương thức static**. Chúng có phạm vi khác nhau và không bị ràng buộc với nhau. Cú pháp then chốt là **`static <U> ReturnType methodName(...)`**, tức đặt phần khai báo `<U>` sau modifier `static` và trước kiểu trả về.

## 1. Hai loại tham số kiểu có phạm vi khác nhau

Xét đoạn khai báo lớp sau:

```java
class Holder<T> {
    private final T stored;

    Holder(T stored) {
        this.stored = stored;
    }

    T get() {
        return stored;
    }

    static <U> U echo(U value) {
        return value;
    }
}
```

Đây là **định nghĩa lớp độc lập để minh họa**; nếu dùng trong tệp chạy khác, hãy đặt nó cùng package hoặc trong một lớp bao cho phù hợp.

- `class Holder<T>`: lớp khai báo tham số kiểu `T`. Trường instance `stored`, constructor và phương thức instance `get()` đều có thể sử dụng `T`.
- `static <U> U echo(U value)`: phương thức static **tự khai báo** tham số kiểu `U`. Nó có thể được gọi như `Holder.echo("hello")` hoặc `Holder.echo(123)`.
- `U` chỉ có hiệu lực trong chữ ký và thân của phương thức `echo`; không tự xuất hiện trong trường, constructor hay những phương thức khác của `Holder`.
- Khi có `Holder<String> textHolder`, `T = String` thuộc về kiểu của đối tượng đó. Nó **không ép** `U` ở `Holder.echo(123)` trở thành `String`.
- Một phương thức instance cũng có thể tự khai báo `<U>`; khác biệt cốt lõi là phương thức instance có quyền dùng **cả** tham số kiểu lớp `T` lẫn tham số kiểu riêng của method `U`.

Bảng đối chiếu:

| Vị trí khai báo | Ví dụ | Phạm vi sử dụng hợp lệ |
|---|---|---|
| Tham số kiểu lớp | `class Holder<T>` | Trường và phương thức **instance**, constructor, các khai báo được phép trong ngữ cảnh của kiểu generic |
| Tham số kiểu phương thức static | `static <U> U echo(U x)` | Chữ ký và thân **chính phương thức static đó** |
| Tham số kiểu phương thức instance | `<U> U change(U x)` | Chữ ký và thân method; cũng có thể dùng `T` của lớp nếu phù hợp |
| Tham số kiểu của static factory | `static <U> Holder<U> of(U x)` | `U` thuộc factory; kết quả là một đối tượng `Holder<U>` |
| Tham số kiểu của static nested class | `static class Node<U>` | `U` thuộc `Node`, không lấy `T` từ instance của lớp bao |

Điểm dễ nhớ: **`static` thuộc cấp lớp, còn type argument `T` của `Holder<T>` được chọn cho một kiểu tham số hóa khi sử dụng**. Không có một giá trị `T` duy nhất áp dụng cho tất cả `Holder<String>`, `Holder<Integer>` cùng tồn tại.

## 2. Vì sao phương thức static không sử dụng trực tiếp `T` của lớp?

Một generic class có thể được sử dụng với nhiều kiểu:

```java
Holder<String> words = new Holder<>("Java");
Holder<Integer> count = new Holder<>(7);
```

Các dòng trên là **ví dụ sử dụng** lớp `Holder<T>`; cần đặt chúng trong method hoặc ngữ cảnh khai báo biến hợp lệ.

Cùng một lớp `Holder` có các cách tham số hóa `Holder<String>` và `Holder<Integer>`. Nếu có phương thức `static T current()`, thì khi gọi `Holder.current()`, Java sẽ không có **đối tượng nào** để xác định `T` là `String` hay `Integer`. Do đó Java cấm dùng trực tiếp tham số kiểu cấp lớp trong ngữ cảnh static.

Ví dụ **không biên dịch**:

```java
class InvalidBox<T> {
    // static T last;              // Sai: static field dùng T của class.
    // static T getLast() {        // Sai: static method dùng T của class.
    //     return null;
    // }
    // static void save(T value) { // Sai: tham số dùng T của class.
    // }
}
```

Các dòng gây lỗi được comment để trình bày; nếu bỏ comment, các khai báo đó sẽ bị compiler từ chối vì tham chiếu tới type variable của generic class từ static context.

Giải pháp đúng là **khai báo type parameter ngay ở phương thức**:

```java
class ValidBox<T> {
    static <U> U identity(U value) {
        return value;
    }

    static <U> ValidBox<U> of(U value) {
        return new ValidBox<>();
    }
}
```

**Lưu ý:** phiên bản `ValidBox` vừa nêu chỉ minh họa **cú pháp**; vì `ValidBox` không định nghĩa constructor nhận giá trị hay trường lưu dữ liệu, `of(U value)` trả một hộp rỗng. Trong thiết kế thực tế, nên có trường lưu và constructor nhận `U`; ví dụ đầy đủ ở phần sau triển khai đầy đủ hành vi đó.

Bạn không cần biến **cả lớp** thành generic để có phương thức static generic. Một lớp thường cũng có thể viết `static <T> T identity(T value)`. Cơ chế này độc lập với việc lớp bao có `<T>` hay không.

## 3. Cú pháp chuẩn: khai báo `<U>` trước kiểu trả về

Khuôn dạng tổng quát của một static generic method:

```java
[annotations] [access modifier] static <TypeParameters> ReturnType methodName(
        Parameters) {
    // Thân phương thức
}
```

Các dấu ngoặc vuông và tên mô tả trên **chỉ là ký pháp diễn giải**, không phải một đoạn Java biên dịch độc lập. Ví dụ cú pháp thực:

```java
public static <T> T identity(T input) {
    return input;
}

public static <E> java.util.List<E> twice(E element) {
    return java.util.List.of(element, element);
}

private static <N extends Number> double doubled(N number) {
    return number.doubleValue() * 2;
}
```

Ba method là **các đoạn minh họa cần đặt trong một class**.

Đọc phương thức `public static <T> T identity(T input)`:

1. `public static`: modifier; phương thức thuộc lớp.
2. `<T>`: **khai báo** một tham số kiểu cấp phương thức.
3. `T`: kiểu trả về, đang **sử dụng** tham số kiểu mới khai báo.
4. `identity`: tên phương thức.
5. `T input`: kiểu tham số và tên biến đầu vào, ràng buộc đầu vào và đầu ra có cùng `T`.

Type parameter của method có thể xuất hiện trong kiểu trả về, kiểu tham số, bounds hoặc thân method. Kiểu trả về **không bắt buộc là `T`**: `void`, `int`, `double`, `List<T>` đều có thể là kiểu trả về của generic method.

Một vài lỗi cú pháp:

```java
// static T <T> identity(T input) { return input; } // Sai thứ tự.
// static T identity(T input) { return input; }     // Sai nếu T chưa được khai báo.
// static T identity<T>(T input) { return input; }  // Java không khai báo <T> sau tên method.
```

Cần phân biệt `static <T> T method(T value)` **ở khai báo** với `ClassName.<String>method("x")` **ở lời gọi tường minh**. Phần thứ nhất đặt tên tham số kiểu, phần thứ hai cung cấp đối số kiểu.

## 4. Ví dụ Java 17 chạy độc lập: generic class, static factory, static generic method

Lưu toàn bộ chương trình sau thành **`StaticGenericScopeDemo.java`**:

```java
import java.util.List;
import java.util.Map;

public class StaticGenericScopeDemo {

    static final class Container<T> {
        private final T value;

        private Container(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        static <U> Container<U> of(U input) {
            return new Container<>(input);
        }

        static <U> U identity(U input) {
            return input;
        }

        static <K, V> Map.Entry<K, V> entry(K key, V value) {
            return Map.entry(key, value);
        }

        <U> Map.Entry<T, U> combineWith(U other) {
            return Map.entry(value, other);
        }
    }

    static <E> List<E> repeat(E element) {
        return List.of(element, element);
    }

    static <N extends Number> double doubled(N number) {
        return number.doubleValue() * 2;
    }

    public static void main(String[] args) {
        Container<String> text = Container.of("Java");
        Container<Integer> count = Container.of(8);

        System.out.println("text: " + text.get());
        System.out.println("number: " + count.get());

        Integer inferred = Container.identity(42);
        System.out.println("inferred: " + inferred);

        Number wide = Container.<Number>identity(12);
        System.out.println("explicit: " + wide);

        Map.Entry<String, Integer> data =
                Container.<String, Integer>entry("age", 20);
        System.out.println("entry: " + data.getKey()
                + "=" + data.getValue());

        Map.Entry<String, Boolean> pair = text.combineWith(true);
        System.out.println("instance: " + pair.getKey()
                + "," + pair.getValue());

        System.out.println("repeat: " + repeat("go"));
        System.out.println("doubled: " + doubled(2.5));

        Container<String> created = Container.<String>of("OK");
        System.out.println("factory: " + created.get());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp với Java 17 hoặc mới hơn:

```bash
javac StaticGenericScopeDemo.java
java StaticGenericScopeDemo
```

Kết quả stdout:

```text
text: Java
number: 8
inferred: 42
explicit: 12
entry: age=20
instance: Java,true
repeat: [go, go]
doubled: 5.0
factory: OK
```

Giải thích kỹ từng điểm:

- `Container<T>` là **generic class**. `get()` trả về `T` thuộc một cách tham số hóa cụ thể, nên `text.get()` có kiểu tĩnh `String` và `count.get()` có kiểu `Integer`.
- `static <U> Container<U> of(U input)` là **static generic factory method**. `U` do method tự khai báo; `Container.of("Java")` tạo `Container<String>`, `Container.of(8)` tạo `Container<Integer>`. Literal `8` được boxing thành `Integer` khi cần.
- `static <U> U identity(U input)` không dùng đến `T` của class. `Container.identity(42)` suy luận `U = Integer`, dù không có một biến `Container<Integer>` nào tham gia lời gọi.
- `Container.<Number>identity(12)` chỉ định **type argument `Number` cho chính static method**. Object đầu vào vẫn là `Integer` sau boxing; kết quả được nhìn qua kiểu tĩnh `Number`.
- `static <K, V> Map.Entry<K, V> entry(...)` khai báo **hai** type parameter; `Container.<String, Integer>entry("age", 20)` cung cấp cả hai theo thứ tự. `Map.entry` không chấp nhận giá trị `null` và trả entry không hỗ trợ `setValue`.
- `<U> Map.Entry<T,U> combineWith(U other)` là **instance generic method**. Nó có quyền dùng `T` của `Container<T>` **và** `U` của chính method. Với `text` là `Container<String>` và đối số `true` (boxing thành `Boolean`), kết quả có kiểu `Map.Entry<String, Boolean>`.
- `static <E> List<E> repeat(E element)` được khai báo trong lớp `StaticGenericScopeDemo` **không generic**. Điều đó cho thấy phương thức static generic không bắt buộc nằm trong một generic class. `List.of` tạo danh sách không sửa được; cũng không nhận `null`.
- `static <N extends Number> double doubled(N number)` dùng bound `N extends Number`, nên có thể gọi `doubleValue()`. `doubled(2.5)` boxing giá trị `double` thành `Double` và in `5.0`.
- `Container.<String>of("OK")` chỉ định `U = String` cho factory. Không có khái niệm “gán `T = String` cho cả lớp `Container` tại runtime”; kiểu `Container<String>` của kết quả được kiểm tra lúc biên dịch.

## 5. Static factory: ứng dụng quan trọng nhất của phương thức static generic

Một mẫu phổ biến khi xây generic class là constructor không public, còn factory công khai tự suy luận type parameter cho object mới:

```java
class Box<T> {
    private final T value;

    private Box(T value) {
        this.value = value;
    }

    public static <U> Box<U> of(U value) {
        return new Box<>(value);
    }

    public T get() {
        return value;
    }
}
```

Đây là **một lớp minh họa khác**, độc lập với `Container` của chương trình đã chạy. Có thể sử dụng:

```java
Box<String> name = Box.of("Ada");
Box<Integer> points = Box.of(100);
```

Tại sao chữ ký factory phải là `static <U> Box<U> of(U value)`?

1. Method static không được dùng `T` của lớp để viết `static Box<T> of(T value)`.
2. Khai báo `<U>` cung cấp type parameter mới, có phạm vi trong phương thức factory.
3. `Box<U>` ở kiểu trả về liên kết **kiểu đối số factory** với **kiểu của object Box được tạo**.
4. Trình biên dịch dùng `U` để kiểm tra `new Box<>(value)` và kiểu kết quả.
5. Việc tên phương thức là `of` chỉ là lựa chọn API; cũng có thể dùng `from`, `create` hoặc tên diễn đạt hợp đồng.

Một chữ ký như `static <U> Box<Object> of(U value)` vẫn là static generic method hợp lệ, nhưng nó **đánh mất** kiểu `U` trong kiểu trả về, thường không phải hợp đồng mong muốn. Thiết kế `Box<U>` mới giữ được an toàn kiểu.

Những factory phổ biến trong Java API (ví dụ `List.of(...)`, `Map.entry(...)`, `Optional.of(...)`) đều minh họa lợi ích của các static method liên quan đến tham số kiểu. Cần đọc **chữ ký thực tế** của từng API để biết method có tham số kiểu nào, quy tắc xử lý null ra sao và kết quả có mutable hay không; không suy ra mọi factory hoạt động giống nhau chỉ từ tên `of`.

## 6. Suy luận kiểu và đối số kiểu tường minh của static method

Java thường suy luận type argument từ đối số và kiểu đích:

```java
String word = Container.identity("hello");
Integer size = Container.identity(5);
Number number = Container.<Number>identity(5);
```

Các dòng trên sử dụng lớp `Container` của chương trình chạy độc lập và cần đặt trong một method hợp lệ.

- `Container.identity("hello")`: kiểu đối số `String` tạo ràng buộc đủ để suy luận `U = String`.
- `Container.identity(5)`: giá trị primitive `int` được boxing thích hợp; `U` được suy luận là `Integer`.
- `Container.<Number>identity(5)`: chọn `U = Number` tường minh; boxing tạo `Integer`, là subtype của `Number`.
- Type witness **không phải cast** và không chuyển đổi tùy ý. `Container.<String>identity(5)` không biên dịch vì `int` không thể truyền vào vị trí yêu cầu `String`.

Cú pháp của lời gọi static với đối số kiểu tường minh là:

```java
ClassName.<ConcreteType>method(arguments);
ClassName.<FirstType, SecondType>method(arguments);
```

Đây là **mẫu cú pháp mô tả**, cần thay tên lớp, kiểu, phương thức và đối số trước khi dùng. Không viết `ClassName.method<ConcreteType>(...)` theo thói quen từ ngôn ngữ khác.

Một ví dụ thường gặp về target typing với method không nhận đầu vào:

```java
static <T> List<T> empty() {
    return List.of();
}
```

Với phương thức `empty()` được đặt trong một lớp `CollectionsHelper`, người gọi có thể viết:

```java
List<String> texts = CollectionsHelper.empty();
var explicit = CollectionsHelper.<String>empty();
```

Hai lời gọi đều cho kiểu tĩnh `List<String>`; dòng đầu suy luận nhờ target type, dòng sau nhờ type witness. Nếu viết `var inferred = CollectionsHelper.empty();` trong một ngữ cảnh không đủ thông tin, kiểu thường được suy luận rộng như `List<Object>`. Phần `<T>` thuộc method `empty` và không dựa vào generic class bao.

## 7. Phương thức static với nhiều type parameter và ràng buộc

Một phương thức static có thể khai báo nhiều type parameter:

```java
public static <K, V> java.util.Map.Entry<K, V> entry(K key, V value) {
    return java.util.Map.entry(key, value);
}
```

`K` và `V` có phạm vi **trong cùng một method**; chúng độc lập với nhau. Có thể gọi `ClassName.<String, Integer>entry("age", 20)`, hoặc để compiler tự suy luận. Khi chỉ định tường minh, phải cung cấp đủ các type argument theo đúng thứ tự.

Một tham số kiểu cũng có thể có bound:

```java
public static <N extends Number> double doubled(N value) {
    return value.doubleValue() * 2;
}
```

Phần `<N extends Number>` yêu cầu type argument là `Number` hoặc subtype phù hợp. `doubled(4)` hợp lệ qua `Integer`; `doubled("4")` bị loại ở compile time. Bound `extends` **không làm phương thức trở thành instance method** và không cấp cho static method quyền dùng `T` ở mức lớp.

Có thể liên kết nhiều bound:

```java
public static <T extends Number & Comparable<T>> T larger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

Phương thức trên là **mẫu minh họa**, cần đặt trong class. `Integer` thỏa cả `Number` lẫn `Comparable<Integer>`. Trong cú pháp nhiều bound, nếu có bound là class thì nó phải đứng đầu, tiếp theo là các interface phân tách bằng `&`. Không khai báo lower bound `<T super Number>`; `? super T` là cú pháp wildcard ở vị trí sử dụng type, không phải tên tham số kiểu mới.

## 8. Phân biệt static generic method với instance method dùng kiểu của lớp

Giả sử một lớp generic khai báo:

```java
class Shelf<T> {
    private T item;

    Shelf(T item) {
        this.item = item;
    }

    T get() {
        return item;
    }

    void set(T next) {
        this.item = next;
    }

    <U> String describeWith(U label) {
        return label + "=" + item;
    }

    static <U> U echo(U input) {
        return input;
    }
}
```

Đây là **một lớp minh họa độc lập**.

| Thành viên | Có tự khai báo type parameter không? | Có dùng `T` của lớp không? | Ý nghĩa |
|---|---|---|---|
| `T get()` | Không | Có | Đọc phần tử theo kiểu của `Shelf<T>` |
| `void set(T next)` | Không | Có | Thay phần tử theo kiểu của instance |
| `<U> String describeWith(U label)` | Có (`U`) | Có, thông qua `item` | Method instance phối hợp cả kiểu lớp và kiểu method |
| `static <U> U echo(U input)` | Có (`U`) | Không | Method static có tham số kiểu độc lập |

Từ `Shelf<String> shelf = new Shelf<>("book")`:

- `shelf.set("new book")` hợp lệ, vì `T = String` trong kiểu instance.
- `shelf.describeWith(42)` hợp lệ, vì method instance tự suy luận `U = Integer`, trong khi trường `item` vẫn là `String`.
- `Shelf.echo(42)` hợp lệ. **Không cần** một đối tượng `Shelf<Integer>` để chọn `U = Integer`.
- `shelf.set(42)` không hợp lệ: `set` dùng `T = String` từ lớp, không có type parameter mới.
- Không nên gọi static method bằng biểu thức instance (`shelf.echo(...)`) dù một số cú pháp Java có thể cho phép: nó khiến người đọc tưởng method phụ thuộc vào trạng thái đối tượng. Hãy dùng tên lớp.

Điểm phân biệt quan trọng: `get()` **không phải một generic method tự khai báo type parameter**, mặc dù kiểu trả về của nó là `T`; nó sử dụng type parameter **do class khai báo**. Trong khi đó `static <U> U echo(U input)` là một generic method thực sự.

## 9. Static nested class: cùng quy tắc static, nhưng type parameter ở cấp lớp lồng

Một `static nested class` có thể tự generic mà **không mang tham số kiểu của outer**. Chẳng hạn:

~~~java
class Outer<T> {
    static final class Nested<U> {
        private final U data;
        Nested(U data) { this.data = data; }
        U get() { return data; }
    }
}
~~~

`Outer.Nested<String>` hợp lệ; `Outer<String>.Nested<Integer>` không phải cú pháp tham số hóa đúng của static member type. `U` thuộc chính lớp `Nested`, trong khi `T` không được dùng trực tiếp trong ngữ cảnh static đó.

Phương thức static **bên trong** `Nested<U>` cũng phải khai báo type parameter riêng nếu muốn generic, như `static <X> X identity(X input)`; nó không được dùng trực tiếp `U` của `Nested`. Đây là điểm tiếp nối quy tắc của phương thức static; chi tiết về inner class, nested factory, bounds và enclosing instance thuộc chủ đề lớp lồng.

## 10. Tránh che tên `T` của class bằng type parameter mới

Java cho phép viết `class Wrapper<T> { static <T> T echo(T input) { return input; } }`. Tuy hợp lệ, **`T` của method không phải `T` của class**; tên trùng gây ảo giác method phụ thuộc một `Wrapper<T>` instance.

Nếu hai phạm vi độc lập, nên viết `static <U> U echo(U input)`. Đổi tên không thay runtime behavior nhưng giúp phân biệt ngay nơi khai báo. Nếu method thật sự cần giá trị trong một `Wrapper<T>`, hãy nhận `Wrapper<U>` làm tham số hoặc chuyển thành instance method; đừng dùng unchecked cast để nối hai `T` không liên quan.

Cơ chế shadowing, bounds khác nhau giữa hai khai báo và các lỗi setter/return type do reuse tên `T` cần được phân tích riêng; mục đích ở đây chỉ là thiết kế chữ ký **static generic method** rõ ràng.

## 11. Vì sao type erasure không xóa khả năng kiểm tra kiểu khi biên dịch?

Generic static method tham gia vào cơ chế **type erasure** của Java giống các generic method khác:

```java
static <U> U identity(U value) {
    return value;
}
```

Với `U` không bound, kiểu đại diện sau erasure thường là `Object`. Compiler kiểm tra các lời gọi như `String s = identity("x")` và có thể chèn cast thích hợp trong bytecode. Điều này giải thích tại sao cùng một method static có thể xử lý `String`, `Integer` và các reference type khác mà không cần runtime tạo nhiều phiên bản khác nhau.

Hệ quả:

- Không thể dùng `new U()` chỉ vì method khai báo `<U>`: không có constructor runtime được suy ra từ type parameter.
- Không thể dùng trực tiếp `U.class` hoặc `obj instanceof U` cho một type variable thông thường không reifiable.
- Không thể truyền primitive như `<int>`; `<Integer>` hoặc autoboxing là cách thích hợp với Java 17.
- Một lời gọi `Container.<String>identity("x")` không tạo ra một đối tượng `Container<String>` hay thay đổi state của bất kỳ `Container` nào; chỉ lời gọi factory có trả về `Container<U>` mới tạo object theo thân factory.
- Có thể sinh bridge method khi cần bảo toàn semantics override trong những trường hợp generics và kế thừa, nhưng sự tồn tại của `<U>` ở static method **không tự tạo dynamic dispatch**.

Nếu cần **tạo đối tượng U**, thiết kế một factory rõ ràng bằng `Supplier<U>`:

```java
static <U> U create(java.util.function.Supplier<U> factory) {
    return java.util.Objects.requireNonNull(factory).get();
}
```

Đây là **method minh họa** cần đặt trong class. Lời gọi `create(StringBuilder::new)` có thể trả `StringBuilder`; thông tin cách tạo được cung cấp bởi `Supplier<U>`, không phải do `U` tự chứa một constructor.

## 12. Lỗi hay gặp với static và generic type parameter

**Lỗi 1 — Static method dùng `T` của class.** Trong `class Box<T>`, khai báo `static T identity(T x)` là sai vì `T` thuộc phạm vi instance của generic class. Sửa thành `static <U> U identity(U x)` nếu method độc lập kiểu lớp.

**Lỗi 2 — Static field mang kiểu `T` của class.** `static T lastValue;` không hợp lệ. Nếu dữ liệu thực sự thuộc về mỗi object, dùng trường instance `private T lastValue;`. Nếu dữ liệu là chung toàn lớp, chọn một kiểu static cụ thể hoặc thiết kế lưu trữ phù hợp.

**Lỗi 3 — Quên `<U>` trước return type.** `static U echo(U input)` không biên dịch nếu `U` chưa được khai báo đúng phạm vi. Viết `static <U> U echo(U input)`.

**Lỗi 4 — Đặt `<U>` ở vị trí sau tên method.** `static U echo<U>(U input)` là sai cú pháp Java. Đặt `<U>` sau modifier và trước kiểu trả về.

**Lỗi 5 — Tưởng `Container<String>` quyết định `U` cho static method.** `Container.identity(7)` được suy luận từ lời gọi; không cần tạo `Container<Integer>`. Lời gọi static được viết bằng tên lớp để làm rõ điều đó.

**Lỗi 6 — Không phân biệt static factory với instance method.** `static <U> Box<U> of(U value)` tạo `Box<U>` mới; `T get()` đọc giá trị của một instance `Box<T>`. Hai chữ ký sử dụng type parameter từ hai phạm vi khác nhau.

**Lỗi 7 — Dùng `<U>` nhưng trả về `Box<Object>`.** Nếu hợp đồng yêu cầu giữ kiểu của đối số, trả `Box<U>`. Trả về `Box<Object>` đánh mất thông tin kiểu cần thiết, dù có thể vẫn biên dịch.

**Lỗi 8 — Cho rằng static generic method là một bản riêng theo `U` ở runtime.** Thông thường Java dùng erasure. `identity("x")` và `identity(1)` gọi cùng định nghĩa method static, không tạo mã nguồn/bytecode chuyên biệt theo type argument.

**Lỗi 9 — Dùng cùng tên `T` ở class và method mà không nhận ra che khuất.** `static <T> T echo(T x)` có `T` riêng; nên chọn `U` khi cần phân biệt với `class Wrapper<T>`.

**Lỗi 10 — Hiểu nhầm static nested class kế thừa kiểu của outer class.** `static class Nested<U>` có `U` độc lập, không được dùng trực tiếp `T` của `Outer<T>`. Không dùng `Outer<String>.Nested<Integer>` như cách khai báo inner class.

**Lỗi 11 — Lạm dụng generic method khi không cần quan hệ kiểu.** Nếu chỉ in dữ liệu, `static void print(Object x)` có thể đủ rõ; `static <T> void print(T x)` hợp lệ nhưng không tự tạo lợi ích an toàn kiểu khi `T` không ràng buộc với vị trí khác.

**Lỗi 12 — Nhầm `static <T>` với phép chuyển đổi tùy ý.** `Container.<String>identity(123)` vẫn không biên dịch; method bị ràng buộc theo type argument đã chỉ định. Type witness không có chức năng tự biến số nguyên thành chuỗi.

## 13. Tự kiểm tra với đáp án

**Câu 1.** Vì sao `class Box<T> { static T get(); }` sai?  
**Đáp án:** Static method không có một cách tham số hóa instance cụ thể để sử dụng `T` của class; cần kiểu cụ thể hoặc type parameter riêng của method.

**Câu 2.** `class Box<T> { static <U> U echo(U x) { return x; } }` hợp lệ không?  
**Đáp án:** Hợp lệ; `U` thuộc phương thức static.

**Câu 3.** Nếu có `Box<String> b`, gọi `Box.echo(10)` thì `U` là gì?  
**Đáp án:** Có thể suy luận `U = Integer` qua boxing của `10`; việc `b` có `T = String` không ảnh hưởng.

**Câu 4.** `static <U> Box<U> of(U value)` mang lợi ích gì so với trả `Box<Object>`?  
**Đáp án:** Bảo toàn mối liên hệ kiểu giữa đối số truyền vào và đối tượng `Box<U>` trả về.

**Câu 5.** `static <U> void log(U x)` có phải generic method không, dù trả `void`?  
**Đáp án:** Có. Phương thức generic được nhận diện từ việc tự khai báo type parameter `<U>`, không phụ thuộc kiểu trả về.

**Câu 6.** `static <N extends Number> double doubled(N n)` có chấp nhận `String` không?  
**Đáp án:** Không. `String` không thỏa bound `Number`.

**Câu 7.** Phương thức instance có thể sử dụng đồng thời kiểu của class và kiểu tự khai báo không?  
**Đáp án:** Có, ví dụ `<U> Map.Entry<T, U> combineWith(U value)` trong `Container<T>`.

**Câu 8.** `Outer<T>.Nested<U>` là cú pháp cần dùng khi `Nested` được khai báo static không?  
**Đáp án:** Không. Static nested class không phụ thuộc một outer instance đã tham số hóa; dùng `Outer.Nested<U>`.

**Câu 9.** Một static generic method có thể khai báo hai kiểu độc lập không?  
**Đáp án:** Có: `static <K,V> Map.Entry<K,V> entry(K k,V v)`.

**Câu 10.** `Container.<Integer>identity(7)` khác `Container.identity(7)` ở đâu?  
**Đáp án:** Lời gọi thứ nhất chỉ định type argument tường minh; lời gọi thứ hai để compiler suy luận. Trong ví dụ, cả hai đều hợp lệ và trả giá trị `7` với kiểu tĩnh phù hợp.

**Câu 11.** Vì sao `new U()` không được phép chỉ nhờ khai báo `static <U>`?  
**Đáp án:** Tham số kiểu bị erasure và không cung cấp constructor runtime; cần factory/`Supplier<U>` nếu muốn tạo đối tượng.

**Câu 12.** Khi nào không cần viết `<U>` cho method trong generic class?  
**Đáp án:** Nếu method instance chỉ cần sử dụng `T` của class, ví dụ `T get()`; hoặc nếu static method chỉ xử lý kiểu cụ thể và không cần tham số kiểu độc lập.

**Câu 13.** Vì sao `static <T> T echo(T value)` trong `class Box<T>` dễ gây hiểu nhầm dù có thể hợp lệ?  
**Đáp án:** `T` của method che khuất `T` của class; nên cân nhắc dùng `<U>` để thể hiện hai phạm vi rõ ràng.

**Câu 14.** Nếu `static <U> List<U> repeat(U value)` nhận một `String`, kết quả có kiểu gì?  
**Đáp án:** Khi `U = String`, kết quả là `List<String>`; lời gọi `repeat("hi")` có thể suy luận điều đó khi biên dịch.

Quy tắc cốt lõi: **type parameter của generic class gắn với kiểu instance, còn type parameter của static generic method được khai báo ngay trên method và độc lập với instance**. Hãy đọc chữ ký `static <U> ...` như một hợp đồng mới, không phải một cách “mượn” `T` từ `class Container<T>`. Khi hiểu đúng phạm vi, bạn có thể viết static factory, hàm tiện ích và API generic an toàn mà không mắc lỗi `non-static type variable cannot be referenced from a static context`.

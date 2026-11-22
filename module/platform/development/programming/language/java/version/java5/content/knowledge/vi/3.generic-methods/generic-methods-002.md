# Phương thức generic static và phương thức của lớp generic

## 1. Khái niệm: generic thuộc lớp hay thuộc phương thức?

Khi thấy chữ `T` trong một phương thức, hãy tìm nơi đã khai báo nó. Có hai tình huống khác nhau:

```java
// Khai báo minh họa; chưa phải chương trình chạy độc lập.
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Ở đây `T` thuộc khai báo `Box<T>`. `get()` là phương thức của lớp generic, nhưng bản thân nó **không phải phương thức generic**: nó không có danh sách tham số kiểu riêng.

So sánh với:

```java
// Phương thức minh họa, đặt bên trong một lớp.
static <U> U identity(U value) {
    return value;
}
```

`<U>` do chính phương thức khai báo, nên đây là một **phương thức generic**. Từ khóa `static` cho biết phương thức thuộc lớp và không cần một đối tượng nhận lời gọi.

Hai đặc điểm “generic” và “static” trả lời hai câu hỏi độc lập:

- **Generic ở cấp nào?** Ai khai báo tham số kiểu: lớp hay phương thức?
- **Phương thức thuộc lớp hay đối tượng?** Có `static` hay không?

Các nguyên tắc này xuất hiện từ Java 5 và vẫn dùng trên Java hiện đại. Phần thực hành dùng Java 17 trở lên để có thể viết ví dụ ngắn với các API chuẩn đang sử dụng.

## 2. Vì sao cần phân biệt?

Nếu không tách hai cấp khai báo, rất dễ mắc các lỗi:

- Cho rằng mọi phương thức nằm trong `Box<T>` đều là phương thức generic.
- Cho rằng phương thức `static` có thể tự dùng `T` của `Box<T>`.
- Thêm `<T>` trước một phương thức nhưng tưởng vẫn dùng đúng `T` của lớp.
- Cho rằng gọi hàm tạo tĩnh qua một đối tượng `Box<String>` sẽ làm tham số phương thức cố định thành `String`.
- Muốn trả về một kiểu mới nhưng lại sửa phương thức đang cố định theo kiểu của đối tượng.

Phân biệt đúng giúp thiết kế chữ ký thể hiện được quan hệ: kiểu nào ổn định theo đối tượng, kiểu nào do từng lời gọi quyết định, và kiểu nào được biến đổi từ đầu vào sang đầu ra.

## 3. Bảng phân loại các dạng phương thức

Giả sử các khai báo dưới đây nằm trong `class Box<T>`:

| Chữ ký | Phương thức generic? | Static? | Tham số kiểu đang dùng |
| --- | --- | --- | --- |
| `T get()` | Không | Không | `T` do lớp khai báo |
| `Box<T> with(T value)` | Không | Không | `T` do lớp khai báo |
| `<U> Box<U> map(Function<? super T, ? extends U> f)` | Có | Không | `T` của lớp và `U` của phương thức |
| `static <U> Box<U> of(U value)` | Có | Có | `U` do phương thức khai báo |
| `static String category()` | Không | Có | Không dùng tham số kiểu |
| `static T getDefault()` | Không hợp lệ | Có | Cố dùng `T` của lớp ở ngữ cảnh tĩnh |

Dấu hiệu nhận diện phương thức generic nằm ở danh sách `<...>` của **khai báo phương thức**, đặt trước kiểu trả về. Chỉ có `List<T>`, `Box<T>` hoặc `T` ở tham số/kiểu trả về chưa đủ để kết luận.

Lớp không generic vẫn có thể chứa phương thức generic. Ngược lại, lớp generic có thể có nhiều phương thức thông thường không tự khai báo tham số kiểu.

## 4. Phương thức của lớp generic: dùng kiểu đã chọn cho đối tượng

Với lớp `Box<T>` ở đầu bài:

```java
// Các câu lệnh minh họa bên trong một phương thức.
Box<String> text = new Box<>("Java");
String value = text.get();

Box<Integer> number = new Box<>(42);
Integer count = number.get();
```

Cùng một khai báo `get()`, nhưng kiểu kết quả được xác định theo kiểu của đối tượng nhận lời gọi:

- Qua `Box<String>`, kết quả có kiểu `String`.
- Qua `Box<Integer>`, kết quả có kiểu `Integer`.

Đối tượng không tự đổi đối số kiểu sau mỗi lời gọi `get()`. Khi đã có biến `Box<String>`, các phương thức dùng `T` của lớp phải tôn trọng hợp đồng `String` của cách nhìn đó.

Ví dụ một phương thức tạo hộp mới cùng kiểu:

```java
// Thành viên minh họa đặt trong Box<T>.
Box<T> with(T next) {
    return new Box<>(next);
}
```

Nếu `text` là `Box<String>`, `text.with("JVM")` hợp lệ. `text.with(123)` không hợp lệ vì `with` cần `String` ở cách sử dụng này.

`with` không phải một phương thức generic chỉ vì trả về `Box<T>`. Nó dùng lại tham số đã thuộc lớp; không tự giới thiệu một kiểu mới cho từng lời gọi.

Constructor `Box(T value)` ở ví dụ cũng dùng `T` của lớp. Không gọi nó là constructor generic chỉ vì lớp chứa nó là generic; constructor generic phải có danh sách tham số kiểu riêng.

## 5. Phương thức generic static: kiểu được xác định cho từng lời gọi

Một lớp không generic có thể cung cấp tiện ích generic:

```java
// Khai báo minh họa; cần import java.util.List.
class ListTools {
    static <U> U first(List<U> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("empty list");
        }
        return values.get(0);
    }
}
```

`ListTools` không có tham số kiểu. `first` tự khai báo `U` để nối kiểu phần tử đầu vào với kiểu kết quả:

```java
// Các câu lệnh minh họa bên trong một phương thức.
String word = ListTools.first(List.of("alpha", "beta"));
Integer number = ListTools.first(List.of(10, 20));
```

Hai lời gọi có thể dùng hai đối số kiểu khác nhau mà không cần tạo hai đối tượng `ListTools`.

“Kiểu được xác định cho từng lời gọi” là việc kiểm tra/suy luận kiểu khi biên dịch. Không nên hiểu rằng JVM sinh một lớp hoặc một bản phương thức chuyên biệt mới cho mỗi lần gọi.

Tham số kiểu thường được suy luận, nhưng có thể chỉ định tường minh:

```java
// Câu lệnh minh họa.
Integer number = ListTools.<Integer>first(List.of(10, 20));
```

Vị trí `<Integer>` ở ngay trước tên phương thức thể hiện nó là đối số kiểu của phương thức, không phải tham số của lớp `ListTools`.

## 6. Phương thức generic static nằm trong lớp generic

Một hàm tạo tĩnh thường trả về đối tượng generic:

```java
// Thành viên minh họa đặt trong Box<T>.
static <U> Box<U> of(U value) {
    return new Box<>(value);
}
```

Phương thức `of` nằm trong `Box<T>`, nhưng `U` thuộc riêng phương thức. Không có quan hệ mặc định nào khiến `U` bằng `T` của lớp.

Cách gọi:

```java
// Các câu lệnh minh họa.
Box<String> text = Box.of("Java");
Box<Integer> number = Box.of(42);
Box<Number> widened = Box.<Number>of(5);
```

Với lời gọi cuối, `U` được chỉ định là `Number`. Giá trị `5` được boxing và chấp nhận qua kiểu tham chiếu phù hợp; kiểu hộp kết quả là `Box<Number>`.

Gọi phương thức tĩnh qua tên lớp `Box.of(...)` thể hiện đúng quyền sở hữu. Không dùng cú pháp `Box<String>.of(...)` để chuyên biệt thành viên tĩnh.

### Vì sao static T of(T value) không hợp lệ?

```java
// Minh họa lỗi; không biên dịch.
class BadBox<T> {
    static T identity(T value) {
        return value;
    }
}
```

`T` đang thuộc lớp `BadBox<T>`. Thành viên tĩnh không nhận một đối tượng `BadBox<T>` để gắn với đối số kiểu đó; Java không cho phép tham chiếu tham số lớp theo cách này.

Sửa bằng một tham số phương thức riêng:

```java
// Khai báo minh họa hợp lệ.
class Utilities {
    static <U> U identity(U value) {
        return value;
    }
}
```

Nếu lớp kết quả có giới hạn, phương thức tĩnh cũng phải khai báo giới hạn cần thiết để kết quả hợp lệ. Ví dụ, với `NumericBox<N extends Number>`, một hàm tạo tĩnh nhận kiểu mới thường cần dạng `static <U extends Number> NumericBox<U> of(U value)`; giới hạn của tham số lớp không tự gắn vào một `U` mới.

### Có tham số phương thức không đồng nghĩa được dùng trạng thái đối tượng

```java
// Minh họa lỗi; không biên dịch.
class BadAccess<T> {
    private T value;

    static <U> U read() {
        return value;
    }
}
```

`U` được khai báo hợp lệ, nhưng `value` là trường đối tượng. Phương thức tĩnh không có một đối tượng nhận lời gọi ngầm định để truy cập trường đó.

Nếu cần đọc một hộp được cung cấp rõ ràng, có thể dùng:

```java
// Phương thức minh họa, đặt trong một lớp có định nghĩa Box.
static <U> U read(Box<U> source) {
    return source.get();
}
```

Ở đây tham số `source` cung cấp cả đối tượng cần đọc lẫn mối liên hệ kiểu.

## 7. Phương thức đối tượng cũng có thể generic

Không phải mọi phương thức generic đều là `static`. Một thao tác biến đổi dữ liệu có thể cần đồng thời:

- `T` của đối tượng hiện tại để mô tả đầu vào.
- Một `U` mới của phương thức để mô tả kết quả.

Ví dụ:

```java
// Thành viên minh họa đặt trong Box<T>.
// Cần import java.util.function.Function.
<U> Box<U> map(Function<? super T, ? extends U> mapper) {
    return new Box<>(mapper.apply(value));
}
```

`map` là phương thức đối tượng vì nó dùng `value` của hộp hiện tại. Nó cũng là phương thức generic vì tự khai báo `U`.

`Function` biểu diễn một phép biến đổi có một đầu vào và một kết quả. Trong chữ ký này, `? super T` cho phép hàm nhận giá trị `T`; `? extends U` cho phép kết quả của hàm được dùng qua kiểu `U`. Mục đích ở đây là giữ quan hệ giữa kiểu đầu vào của đối tượng và kiểu đầu ra mới; không cần học toàn bộ wildcard để nhận diện hai cấp tham số.

```java
// Các câu lệnh minh họa.
Box<String> text = Box.of("Java");
Box<Integer> length = text.map(String::length);
```

`String::length` là tham chiếu tới thao tác lấy độ dài chuỗi. Với `text`, `T` là `String`; kết quả độ dài được boxing thành `Integer`, nên `U` được chọn phù hợp cho `Box<Integer>`.

`map` tạo một hộp kết quả có kiểu khác mà không đổi kiểu của hộp ban đầu. Đây là hợp đồng khác với `with(T next)`, vốn tạo hộp mới cùng `T`.

## 8. Che khuất tên: thêm <T> có thể tạo một T khác

Khai báo sau dễ gây nhầm:

```java
// Khai báo minh họa hợp lệ nhưng tên tham số không rõ.
class Confusing<T> {
    static <T> T identity(T value) {
        return value;
    }
}
```

`T` trước `identity` là tham số mới của phương thức, che khuất tên `T` của lớp trong phạm vi tương ứng. Mã không có nghĩa là thành viên tĩnh đã được phép dùng tham số lớp.

Đổi thành `static <U> U identity(U value)` sẽ thể hiện đúng tính độc lập.

Lỗi nghiêm trọng hơn có thể xuất hiện trong phương thức đối tượng:

```java
// Minh họa lỗi; không biên dịch.
class ConfusingSetter<T> {
    private T value;

    <T> void set(T next) {
        this.value = next;
    }
}
```

Hai tên `T` thuộc hai khai báo khác nhau. `next` mang kiểu của phương thức; trường `value` mang kiểu của lớp. Không có hợp đồng bảo đảm gán được từ một kiểu sang kiểu còn lại.

Nếu mục đích là đặt giá trị cùng kiểu với đối tượng, chữ ký cần là `void set(T next)`, không thêm `<T>`.

## 9. Chương trình đầy đủ

Lưu vào `GenericMethodKindsDemo.java`:

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class GenericMethodKindsDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        Box<T> with(T next) {
            return new Box<>(next);
        }

        <U> Box<U> map(Function<? super T, ? extends U> mapper) {
            Objects.requireNonNull(mapper);
            return new Box<>(mapper.apply(value));
        }

        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }

        static String category() {
            return "box";
        }
    }

    static <U> U first(List<U> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("empty list");
        }
        return values.get(0);
    }

    public static void main(String[] args) {
        Box<String> text = Box.of("Java");
        System.out.println(text.get());

        Box<String> changed = text.with("JVM");
        System.out.println(changed.get());
        System.out.println(text.get());

        Box<Integer> length = text.map(String::length);
        System.out.println(length.get());

        String word = GenericMethodKindsDemo.first(
                List.of("alpha", "beta"));
        System.out.println(word);

        Integer number = GenericMethodKindsDemo.<Integer>first(
                List.of(10, 20));
        System.out.println(number);

        Box<Number> numeric = Box.<Number>of(5);
        System.out.println(numeric.get());

        System.out.println(Box.category());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 GenericMethodKindsDemo.java
java GenericMethodKindsDemo
```

Stdout chính xác:

```text
Java
JVM
Java
4
alpha
10
5
box
```

Cách đọc kết quả:

1. `get()` dùng `T = String` của đối tượng `text`.
2. `with` nhận một `String` và tạo hộp mới cùng kiểu.
3. Hộp ban đầu vẫn giữ `"Java"`; `with` không sửa trường `final` của nó.
4. `map` kết hợp `T` của lớp với `U` mới để tạo `Box<Integer>`.
5. `first` là phương thức tĩnh generic trong một lớp không generic; lần này kết quả là `String`.
6. Một lời gọi khác của `first` chỉ định `U = Integer`.
7. `of` là phương thức tĩnh generic bên trong lớp generic, với đối số kiểu phương thức `Number`.
8. `category` là phương thức tĩnh thông thường, không generic.

Phương thức `first` chủ động từ chối danh sách rỗng; chương trình chỉ truyền danh sách có phần tử. Ví dụ cho phép hộp chứa `null`, nhưng các phép biến đổi như `String::length` vẫn cần giá trị phù hợp để thực thi. Hợp đồng kiểu không tự thay thế chính sách xử lý dữ liệu thiếu.

## 10. Cách chọn dạng phương thức

Dùng phương thức thông thường của lớp generic khi thao tác phải tuân theo kiểu đã chọn cho đối tượng, như `T get()` hoặc `void set(T value)`.

Dùng phương thức đối tượng generic khi thao tác vừa cần trạng thái/kiểu của đối tượng vừa cần thêm một kiểu cho riêng lần gọi, như `<U> Box<U> map(...)`.

Dùng phương thức tĩnh generic khi thao tác không cần đối tượng nhận lời gọi và quan hệ kiểu có thể được xác định từ đầu vào, ngữ cảnh kết quả hoặc đối số kiểu tường minh. Hàm tạo đối tượng và tiện ích xử lý dữ liệu là những ví dụ thường gặp.

Không đưa tham số kiểu lên cấp lớp chỉ để một hàm tiện ích sử dụng nó. Ngược lại, không thêm tham số mới vào phương thức nếu ý định là dùng đúng tham số của đối tượng.

Tính `static` cũng không tự bảo đảm phương thức thuần, an toàn đa luồng hay không có tác dụng phụ. Đó là các thuộc tính khác, phải xét triển khai cụ thể.

## 11. Tự kiểm tra

- Phân loại `get`, `with`, `map`, `of`, `first` và `category` trong chương trình: phương thức nào tự khai báo tham số kiểu?
- Vì sao `text.with(123)` không biên dịch, trong khi `text.map(String::length)` có thể tạo `Box<Integer>`?
- Viết `static <U> U read(Box<U> source)` và gọi với hai kiểu hộp khác nhau mà không ép kiểu.
- Đổi tên `U` của `of` thành `R` ở tất cả vị trí. Giải thích vì sao hợp đồng không đổi.
- Nếu bỏ `<U>` của `of`, lỗi xuất hiện do đâu? Nếu thay bằng `T` của lớp, vì sao vẫn không hợp lệ?
- Giải thích vì sao `static <T> T identity(T value)` trong `class Box<T>` không dùng cùng tham số kiểu với trường `T value` của lớp.

Khi đọc một API lạ, bắt đầu bằng cách đánh dấu từng danh sách `<...>` và chủ sở hữu của nó. Sau đó mới xét cách suy luận kiểu của lời gọi cụ thể.

## Tài liệu đối chiếu

- [Java Language Specification — Generic Methods (§8.4.4)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.4): khai báo tham số kiểu riêng của phương thức.
- [Java Language Specification — static Methods (§8.4.3.2)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.3.2): đặc điểm phương thức tĩnh.
- [Java Language Specification — Generic Classes (§8.1.2)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.2): tham số kiểu thuộc lớp.
- [Java API — Function<T,R>](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html): hợp đồng phép biến đổi dùng trong ví dụ `map`.

# Phạm vi tham số kiểu và giới hạn trong ngữ cảnh static

## 1. Khái niệm: mỗi tham số kiểu thuộc về một khai báo

Tham số kiểu là một tên do khai báo generic giới thiệu. Trong `class Box<T>`, lớp khai báo `T`; trong `static <U> U identity(U value)`, phương thức khai báo `U`.

Hai câu hỏi cần tách riêng:

1. **Phạm vi tên (scope):** tên tham số kiểu được nhận diện ở những phần nào của mã nguồn?
2. **Quy tắc sử dụng:** tại vị trí đó, Java có cho phép dùng tham số thuộc khai báo ấy hay không?

Tên tham số kiểu của lớp có phạm vi từ vựng bao gồm thân lớp, nhưng Java vẫn cấm tham chiếu tham số ấy trong những ngữ cảnh `static` liên quan. Vì vậy, nói đơn giản “`static` không có `T`” dễ gây hiểu nhầm: một phương thức `static` hoàn toàn có thể khai báo và dùng tham số kiểu riêng.

Điểm quyết định là **tham số kiểu đang thuộc lớp nào hoặc phương thức nào**, không phải nó được đặt tên bằng chữ `T` hay chữ `U`.

Các quy tắc dưới đây vẫn áp dụng trên Java hiện đại. Chương trình thực hành dùng Java 17 trở lên và không phụ thuộc thư viện ngoài.

## 2. Vì sao tham số kiểu của lớp gắn với cách nhìn đối tượng?

Xét lớp chứa một giá trị:

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

Với `Box<String>`, người dùng nhìn `get()` như phương thức trả về `String`. Với `Box<Integer>`, kết quả được nhìn qua `Integer`.

`T` giúp kiểm tra kiểu của các thành viên gắn với đối tượng. Tuy nhiên, Java không tạo một bản sao thành viên `static` riêng cho `Box<String>`, một bản khác cho `Box<Integer>`. Thành viên `static` thuộc lớp; các đối số kiểu khác nhau không tạo những lớp runtime riêng biệt.

Nếu cho phép một trường `static T defaultValue`, cùng một trường sẽ bị yêu cầu có kiểu `String` khi nhìn từ một chỗ và `Integer` khi nhìn từ chỗ khác. Java không cung cấp hợp đồng như vậy và bác bỏ khai báo.

Đây là cách hiểu thiết kế để nhớ quy tắc. Khi sửa lỗi, vẫn phải dựa vào chủ sở hữu tham số và ngữ cảnh khai báo, thay vì chỉ tìm một đối tượng để gọi phương thức.

## 3. Phạm vi của tham số kiểu lớp và phương thức

### 3.1. Tham số do lớp khai báo

Trong `class Box<T>`, `T` có thể tham gia phần khai báo giới hạn của lớp, các đối số kiểu ở phần kế thừa/thực hiện interface, và thân lớp theo quy tắc phạm vi của Java.

Những chỗ dùng phổ biến hợp lệ:

```java
// Khai báo minh họa.
class Container<T> {
    private T value;            // Trường gắn với đối tượng.

    Container(T initial) {      // Tham số của constructor.
        this.value = initial;
    }

    T get() {                  // Kiểu trả về.
        T result = value;      // Biến cục bộ trong phương thức đối tượng.
        return result;
    }

    void set(T next) {         // Tham số của phương thức đối tượng.
        value = next;
    }
}
```

Không cần thêm `<T>` trước mỗi phương thức trong `Container<T>`. `get()` và `set()` đang dùng tham số đã được lớp khai báo, không tự trở thành phương thức generic chỉ vì có chữ `T` trong chữ ký.

### 3.2. Tham số do phương thức khai báo

```java
// Phương thức minh họa, đặt bên trong một lớp.
static <U> U identity(U value) {
    U result = value;
    return result;
}
```

`U` được khai báo giữa dấu `<...>` trước kiểu trả về. Nó dùng được trong phần khai báo phương thức và phần thân theo quy tắc phạm vi; không trở thành một tham số của toàn bộ lớp hay của phương thức bên cạnh.

```java
// Minh họa lỗi trong cùng một lớp; không biên dịch.
static <U> U identity(U value) {
    return value;
}

U other;  // U của identity không có phạm vi tại trường này.
```

Một constructor cũng có thể tự khai báo tham số kiểu; tham số đó thuộc constructor, không tự mở rộng thành tham số của cả lớp. Khi đọc mã, luôn tìm đúng danh sách `<...>` đã giới thiệu tên.

## 4. Các vị trí static không được dùng trực tiếp tham số của lớp bao ngoài

Xét `T` do `Box<T>` khai báo, không có một khai báo `T` khác che khuất nó.

| Vị trí | Dùng trực tiếp `T` của `Box<T>`? | Ghi chú |
| --- | --- | --- |
| Trường đối tượng `T value` | Có | Kiểu thuộc hợp đồng của đối tượng |
| Constructor `Box(T value)` | Có | Nhận giá trị theo đối số kiểu của lớp |
| Phương thức đối tượng `T get()` | Có | Không cần khai báo lại `T` |
| Trường `static T shared` | Không | Trường tĩnh không chuyên biệt theo đối số kiểu |
| Phương thức `static T getDefault()` | Không | Đang dùng tham số của lớp |
| Biến cục bộ `T x` trong khối `static` | Không | Nằm trong ngữ cảnh tĩnh |
| Thành viên của lớp lồng `static` dùng `T` ngoài | Không | Lớp lồng cần tham số riêng nếu muốn generic |
| Phương thức `static <U> U identity(U x)` | Có với `U` | `U` do chính phương thức khai báo |

### 4.1. Thêm final không làm trường tĩnh hợp lệ

```java
// Minh họa lỗi; cả hai trường đều không hợp lệ.
class BadDefaults<T> {
    static T shared;
    static final T EMPTY = null;
}
```

`final` giới hạn việc gán lại trường; nó không đổi chủ sở hữu của `T`. Việc khởi tạo bằng `null` cũng không làm kiểu khai báo trở nên hợp lệ.

Một hằng không phụ thuộc `T` vẫn được phép:

```java
// Khai báo minh họa hợp lệ.
class LabeledBox<T> {
    static final String LABEL = "box";
    private T value;
}
```

### 4.2. Sai ở chữ ký và sai trong thân đều bị cấm

```java
// Minh họa lỗi; không biên dịch.
class BadOperations<T> {
    static T identity(T value) {
        return value;
    }

    static void prepare() {
        T temporary = null;
    }

    static {
        T temporary = null;
    }
}
```

Không chỉ việc truy cập một trường đối tượng mới gây lỗi. Chỉ riêng dùng tên `T` của lớp trong những vị trí tĩnh này đã không hợp lệ.

## 5. Phương thức static generic: khai báo tham số riêng

Một phương thức tĩnh có thể tự đưa vào tham số kiểu:

```java
// Khai báo minh họa hợp lệ.
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
```

Đọc chữ ký `static <U> Box<U> of(U value)`:

- `static`: không cần đối tượng `Box` làm đối tượng nhận lời gọi.
- `<U>`: phương thức tự khai báo một tham số kiểu.
- `Box<U>`: kiểu trả về dùng đúng `U` đó.
- `U value`: đối số đầu vào liên hệ với kiểu của `Box` kết quả.

Lời gọi minh họa:

```java
// Các câu lệnh bên trong một phương thức.
Box<String> text = Box.of("Java");
Box<Integer> number = Box.of(42);
Box<Number> widened = Box.<Number>of(Integer.valueOf(42));
```

`U` có thể được suy luận từ đối số và ngữ cảnh. Khi chỉ định tường minh, `<Number>` nằm trước tên phương thức: `Box.<Number>of(...)`.

Không viết `Box<String>.of(...)` để chuyên biệt một phương thức tĩnh theo tham số của lớp. Gọi thành viên tĩnh qua tên lớp giúp thể hiện đúng quyền sở hữu: `Box.of(...)`.

Phương thức tĩnh cũng có thể làm việc với một đối tượng generic được truyền vào:

```java
// Phương thức minh họa, đặt trong một lớp có định nghĩa Box.
static <U> U read(Box<U> box) {
    return box.get();
}
```

`read` không dùng `T` của lớp bao ngoài; nó dùng `U` của chính mình và đọc đối tượng `box` được truyền rõ ràng. Thông tin kiểu được nối qua tham số đầu vào, không qua một đối tượng nhận lời gọi ngầm định.

## 6. Giới hạn của lớp không tự trở thành giới hạn của phương thức static

Giả sử kiểu chứa chỉ chấp nhận các kiểu số:

```java
// Khai báo minh họa hợp lệ.
class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    static <U extends Number> NumericBox<U> of(U value) {
        return new NumericBox<>(value);
    }
}
```

Phương thức cần tự khai báo `U extends Number` để `NumericBox<U>` thỏa giới hạn của lớp.

Cách sau không hợp lệ:

```java
// Minh họa lỗi, đặt trong lớp NumericBox<T extends Number>.
static <U> NumericBox<U> wrong(U value) {
    return new NumericBox<>(value);
}
```

`U` không có giới hạn số nên có thể là `String`; trình biên dịch không thể chấp nhận `NumericBox<U>`.

Cũng không được nối phương thức tĩnh với tham số của lớp bằng cách viết:

```java
// Minh họa lỗi, đặt trong lớp NumericBox<T extends Number>.
static <U extends T> NumericBox<U> wrong(U value) {
    return new NumericBox<>(value);
}
```

Dù `U` do phương thức khai báo, giới hạn của nó vẫn tham chiếu `T` của lớp tại vị trí không được phép. Hãy khai báo giới hạn cần thiết từ một kiểu hợp lệ, như `Number`, hoặc dùng phương thức đối tượng nếu hợp đồng phải phụ thuộc vào đúng `T` của đối tượng hiện có.

## 7. Lớp lồng static và lớp bên trong gắn với đối tượng

### 7.1. Lớp lồng static tự khai báo tham số

```java
// Khai báo minh họa.
class Outer<T> {
    static class Node<U> {
        private final U value;

        Node(U value) {
            this.value = value;
        }

        U get() {
            return value;
        }
    }
}
```

`Node<U>` có tham số riêng nên hợp lệ. `U` không tự bằng `T`; người dùng chọn đối số kiểu cho `Node` độc lập.

Cách sử dụng:

```java
// Câu lệnh minh họa trong một phương thức.
Outer.Node<Integer> node = new Outer.Node<>(7);
```

Không cần tạo một đối tượng `Outer`, cũng không viết `Outer<String>.Node<Integer>` để truy cập lớp lồng `static`.

Nếu bỏ `<U>` và khai báo trường `T value` trong `static class Node`, mã không hợp lệ vì nó dùng tham số của `Outer`.

### 7.2. Lớp bên trong không static có thể dùng T của đối tượng ngoài

```java
// Khai báo minh họa.
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    class Reader {
        T read() {
            return value;
        }
    }
}
```

`Reader` gắn với một đối tượng `Outer<T>`; phương thức đối tượng của nó có thể dùng `T` và đọc `value` của đối tượng ngoài.

Ví dụ:

```java
// Các câu lệnh minh họa trong một phương thức.
Outer<String> outer = new Outer<>("Java");
Outer<String>.Reader reader = outer.new Reader();
String value = reader.read();
```

Sự khác nhau cần học ở đây là mối liên hệ với đối tượng ngoài và khả năng dùng tham số kiểu tương ứng. Không cần chuyển mọi lớp lồng thành lớp bên trong chỉ để khắc phục lỗi generic; nếu không cần đối tượng ngoài, lớp lồng `static` có tham số riêng thường biểu đạt đúng ý định hơn.

## 8. Che khuất tên: cùng chữ T nhưng là hai tham số khác nhau

Khai báo sau hợp lệ nhưng dễ đọc nhầm:

```java
// Khai báo minh họa; không khuyến khích đặt tên như vậy.
class ConfusingBox<T> {
    <T> T echo(T input) {
        return input;
    }
}
```

`T` của phương thức che khuất tên `T` của lớp trong phạm vi phương thức. Vì vậy, với đối tượng `ConfusingBox<String>`, lời gọi `box.echo(7)` vẫn có thể trả về `Integer`: phương thức đang dùng tham số của chính nó.

Nên đổi tên để chỉ rõ hai vai trò:

```java
// Khai báo minh họa rõ hơn.
class ClearBox<T> {
    private T value;

    T get() {
        return value;
    }

    <U> U echo(U input) {
        return input;
    }
}
```

`get()` dùng `T` của lớp. `echo()` có một tham số độc lập `U`; phương thức đối tượng cũng có thể generic.

Tương tự, `static <T> T identity(T value)` bên trong `Box<T>` có thể hợp lệ vì nó khai báo một `T` mới. Đừng hiểu đó là cách “lấy lại `T` của lớp” trong `static`. Đổi tên phương thức thành `<U>` sẽ làm bản chất rõ hơn.

## 9. Thực hành: chương trình chạy đầy đủ

Lưu vào tệp `TypeParameterScopeDemo.java`:

```java
public class TypeParameterScopeDemo {
    static final class Box<T> {
        static final String LABEL = "box";
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        <U> U echo(U input) {
            return input;
        }

        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }

        static final class Holder<U> {
            private final U value;

            Holder(U value) {
                this.value = value;
            }

            U get() {
                return value;
            }
        }

        final class Reader {
            T read() {
                return value;
            }
        }
    }

    static <N extends Number> double twice(N value) {
        return value.doubleValue() * 2;
    }

    public static void main(String[] args) {
        Box<String> text = Box.of("Java");
        Box<Integer> number = Box.of(42);

        System.out.println(text.get());
        System.out.println(number.get());

        Integer echoed = text.echo(7);
        System.out.println(echoed);

        Box.Holder<Double> holder = new Box.Holder<>(2.5);
        System.out.println(holder.get());

        Box<String>.Reader reader = text.new Reader();
        System.out.println(reader.read());

        System.out.println(text.getClass().equals(number.getClass()));
        System.out.println(Box.LABEL);
        System.out.println(twice(4));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TypeParameterScopeDemo.java
java TypeParameterScopeDemo
```

Stdout chính xác:

```text
Java
42
7
2.5
Java
true
box
8.0
```

Các điểm cần quan sát:

- Hai đối tượng chọn hai đối số kiểu khác nhau cho `Box<T>`.
- `text.echo(7)` trả về `Integer` dù `text` là `Box<String>`: `U` của phương thức độc lập với `T`.
- `Holder<Double>` là lớp lồng `static` có tham số riêng; không cần một đối tượng `Box`.
- `Reader` gắn với `text`, nên kết quả đọc có kiểu `String`.
- `getClass()` của hai đối tượng trả về cùng đối tượng lớp. Đối số generic không tạo hai lớp runtime riêng trong ví dụ này.
- `LABEL` được truy cập qua `Box`, thể hiện đây là thành viên lớp.
- `twice` dùng tham số `N` của chính phương thức tĩnh, với giới hạn `Number`, để gọi `doubleValue()`.

`Box` tự nó được khai báo `static` vì là lớp lồng của `TypeParameterScopeDemo`. Nó vẫn được phép có tham số `T` riêng. Điều bị cấm là dùng tham số của lớp bao ngoài qua ranh giới tĩnh, không phải việc một lớp lồng tĩnh tự khai báo generics.

## 10. Những cách sửa lỗi dễ làm sai hợp đồng

### Thêm <T> nhưng tưởng đang dùng T cũ

```java
// Khai báo minh họa hợp lệ nhưng T của create là một tham số mới.
class FactoryBox<T> {
    static <T> FactoryBox<T> create(T value) {
        return new FactoryBox<T>();
    }
}
```

Phương thức chọn kiểu riêng cho từng lời gọi; không có mối liên hệ với một đối tượng `FactoryBox<T>` đã tồn tại. Trong thiết kế thực tế, tên `U` làm điều này dễ nhận ra hơn.

### Thay T bằng Object ở mọi nơi

Đổi kiểu thành `Object` có thể làm mất lỗi biên dịch nhưng cũng làm mất mối liên hệ kiểu mà API cần bảo toàn. Với hàm tạo đối tượng tĩnh, `static <U> Box<U> of(U value)` giữ được quan hệ đầu vào–đầu ra tốt hơn một hàm trả về `Box<Object>`.

### Gọi static qua đối tượng để mong truyền kiểu của đối tượng

Dù Java cho phép nhiều trường hợp gọi phương thức tĩnh qua biểu thức đối tượng, cách gọi đó không biến nó thành phương thức đối tượng và không truyền `T` của đối tượng làm tham số kiểu ngầm định. Hãy gọi qua tên lớp và khai báo hợp đồng generic rõ ràng.

### Nhầm lỗi static với mọi giới hạn khác của generics

Ngay trong phương thức đối tượng có quyền dùng `T`, biểu thức `T.class` vẫn không hợp lệ. Nếu cần một đối tượng `Class<T>`, có thể truyền nó từ ngoài vào. Đây là giới hạn về biểu diễn kiểu lúc runtime, khác với lỗi dùng `T` của lớp trong ngữ cảnh tĩnh.

Không nên chữa mọi lỗi generic bằng phép ép kiểu hoặc chuyển toàn bộ dữ liệu sang trường tĩnh. Trước hết cần xác định dữ liệu thuộc từng đối tượng hay thuộc lớp.

## 11. Quy trình tự kiểm tra và bài tập

Khi gặp lỗi liên quan tham số kiểu:

1. Tìm khai báo `<...>` đã giới thiệu tên đang dùng.
2. Xác định tên có nằm trong phạm vi khai báo đó hay không.
3. Kiểm tra có đi qua một ranh giới `static` khiến việc dùng tham số của lớp bao ngoài bị cấm hay không.
4. Nếu thao tác độc lập với đối tượng, tự khai báo tham số phương thức và các giới hạn cần thiết.
5. Nếu thao tác phụ thuộc đúng kiểu của đối tượng hiện có, cân nhắc phương thức đối tượng hoặc truyền một đối tượng generic tường minh.
6. Đổi tên tham số bị che khuất để tránh suy luận nhầm quan hệ.

Bài tập:

- Trong chương trình đầy đủ, thử thêm `static T cached;` vào `Box<T>`. Giải thích vì sao lỗi vẫn tồn tại nếu thêm `final` và khởi tạo bằng `null`.
- Viết `static <U> U read(Box<U> box)`, rồi gọi với `Box<String>` và `Box<Integer>`. Kiểm tra các kiểu trả về bằng phép gán.
- Đổi `Holder<U>` thành `Holder<V>`. Giải thích vì sao việc đổi tên nhất quán không đổi hợp đồng.
- Xóa `<U>` của `echo`. Dự đoán lỗi do thiếu khai báo tên, rồi so sánh với lỗi dùng tham số lớp trong một phương thức tĩnh.
- Với `NumericBox<T extends Number>`, viết hàm tạo tĩnh chấp nhận một kiểu số và kiểm tra rằng lời gọi truyền `String` bị trình biên dịch từ chối.

## Tài liệu đối chiếu

- [Java Language Specification — Scope of a Declaration (§6.3)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3): phạm vi tham số kiểu lớp, phương thức và constructor.
- [Java Language Specification — Generic Classes and Type Parameters (§8.1.2)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.2): khai báo lớp generic và các ràng buộc liên quan.
- [Java Language Specification — Generic Methods (§8.4.4)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.4): tham số kiểu riêng của phương thức.
- [Java Language Specification — static Fields (§8.3.1.1)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.3.1.1): quyền sở hữu trường tĩnh.

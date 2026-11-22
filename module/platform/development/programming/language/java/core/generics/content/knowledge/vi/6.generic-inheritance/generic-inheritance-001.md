# Kế thừa lớp generic với đối số kiểu cố định trong Java

## 1. Bài toán và ý tưởng cốt lõi

Một lớp generic khai báo tham số kiểu, chẳng hạn `Storage<T>`, để cùng một cấu trúc lưu trữ phục vụ nhiều loại dữ liệu. Khi tạo **lớp con**, Java cho phép chọn một kiểu cụ thể cho tham số của lớp cha ngay trong mệnh đề `extends`:

```java
// Ví dụ cú pháp; các khai báo nằm trong một tệp Java thích hợp.
class Storage<T> {
    private final T value;

    Storage(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class TextStorage extends Storage<String> {
    TextStorage(String text) {
        super(text);
    }
}
```

`TextStorage extends Storage<String>` nói rằng:

- `Storage<T>` là **lớp cha generic**.
- `TextStorage` là **lớp con không generic**, vì tên lớp không khai báo `<...>`.
- `String` là **đối số kiểu cố định** (*fixed type argument*) được gắn vào `T` của lớp cha.
- Từ góc nhìn của `TextStorage`, phương thức kế thừa `get()` có kiểu trả về **`String`**; constructor cha `Storage(T)` nhận dữ liệu tương ứng **`String`**.
- Mọi lần tạo `new TextStorage(...)` đều tuân theo cùng hợp đồng `Storage<String>`. Người gọi không thể biến nó thành `Storage<Integer>` bằng cách thêm type arguments.

Mục đích của kiểu kế thừa này là biến một abstraction chung thành **một subtype có vai trò cụ thể**: ví dụ lưu chuỗi, dữ liệu số nguyên, danh sách tên hoặc bản ghi một loại domain nhất định. Trình biên dịch giữ quan hệ kiểu giữa cha và con, nên người dùng không phải ép kiểu thủ công từ `Object`.

Bài viết sử dụng Java **17+**, từ cú pháp và cơ chế kiểm tra kiểu tới override, constructor chaining, polymorphism, wildcard và lỗi phổ biến. Mục 12 có tệp Java độc lập đã được biên dịch và chạy kiểm chứng.

## 2. Khai báo lớp cha generic và lớp con cố định kiểu

Cú pháp tổng quát:

```java
class Parent<T> {
    // T có thể xuất hiện trong trường instance, constructor, phương thức...
}

class Child extends Parent<ConcreteType> {
    // Không còn khai báo type parameter T cho chính Child.
}
```

`ConcreteType` phải là kiểu tham chiếu hợp lệ và đáp ứng các **bound** của tham số kiểu lớp cha. Ví dụ `String`, `Integer`, `User`, `List<String>` đều có thể là type argument nếu không vi phạm bound; `int`, `boolean` không thể làm generic type argument trực tiếp.

Một ví dụ lớp cha có getter và setter:

```java
class Cell<T> {
    private T data;

    Cell(T data) {
        this.data = data;
    }

    T read() {
        return data;
    }

    void replace(T next) {
        data = next;
    }
}

final class StringCell extends Cell<String> {
    StringCell(String text) {
        super(text);
    }
}

// Trong một phương thức Java:
StringCell cell = new StringCell("Java");
String value = cell.read();
cell.replace("Generics");
// cell.replace(100); // Lỗi biên dịch: StringCell kế thừa Cell<String>.
```

`StringCell` không cần tự khai báo `read()` hay `replace(...)`: sau khi `T` được cố định thành `String` trong mệnh đề `extends`, compiler kiểm tra các phương thức kế thừa theo kiểu tương ứng.

**Ghi nhớ:** Trong khai báo lớp con, `extends Cell<String>` nghĩa là cố định type argument của **lớp cha**. Đây không phải cú pháp khai báo một tham số kiểu mới. So sánh:

```java
class A extends Cell<String> { // A không generic.
    A() { super("fixed"); }
}

class B<U> extends Cell<U> {    // B vẫn generic và truyền U lên cha.
    B(U initial) { super(initial); }
}
```

`A` có một hợp đồng duy nhất `Cell<String>`. `B<Integer>` dùng `Cell<Integer>`, còn `B<String>` dùng `Cell<String>`, tùy đối số kiểu ở lúc sử dụng `B<U>`.

## 3. Bảng ánh xạ tham số kiểu qua kế thừa

Khi gặp `class Child extends Parent<String>`, nên kiểm tra toàn bộ các vị trí sử dụng `T` trong API lớp cha, không chỉ một getter:

| Thành viên khai báo trong `Parent<T>` | Góc nhìn từ `Child extends Parent<String>` |
| --- | --- |
| `private T value;` | Dữ liệu bên trong cha chịu ràng buộc `String` |
| `Parent(T initial)` | Constructor cha cần dữ liệu tương thích `String` |
| `T get()` | Khi gọi trên `Child`, kết quả là `String` |
| `void set(T item)` | Khi gọi trên `Child`, đối số phải tương thích `String` |
| `List<T> all()` | Khi gọi trên `Child`, kết quả có kiểu `List<String>` |
| `Optional<T> find()` | Khi gọi trên `Child`, kết quả có kiểu `Optional<String>` |
| `<R> R map(Function<? super T,? extends R> f)` | Tham số đầu vào của hàm phù hợp `String`, còn `R` vẫn được phương thức suy luận riêng |
| `static <U> U echo(U value)` | `U` thuộc phương thức static; không bị cố định thành `String` |

Không phải mọi API của lớp cha đều bị thay tất cả tham số kiểu thành `String`. Chỉ **những lần tham chiếu `T` của lớp cha** được ánh xạ theo `extends Parent<String>`. Tham số kiểu riêng của một generic method, ví dụ `<R>`, vẫn độc lập.

Đặc biệt, lớp con **không thể trực tiếp truy cập trường `private T value`** của cha, dù đã cố định `T` thành `String`. Generics không thay đổi quy tắc truy cập `private`/`protected`. Hãy dùng getter, phương thức được bảo vệ hoặc constructor cha thay vì phá vỡ encapsulation.

## 4. Constructor lớp con và lời gọi `super(...)`

Constructor **không được kế thừa**. Dù lớp con cố định type argument, nó vẫn cần constructor của riêng mình để khởi tạo phần cha. Nếu lớp cha không có constructor không tham số có thể truy cập, lớp con phải gọi constructor thích hợp bằng `super(...)`:

```java
class Parent<T> {
    private final T data;

    Parent(T data) {
        this.data = java.util.Objects.requireNonNull(data);
    }

    T get() {
        return data;
    }
}

final class EmailValue extends Parent<String> {
    EmailValue(String email) {
        super(email); // T của Parent<T> được cố định thành String.
    }
}
```

Ở Java 17, lời gọi `super(email)` phải là câu lệnh đầu tiên của constructor (trừ trường hợp cú pháp bổ sung được các phiên bản Java mới hơn cho phép). Lời gọi tới `Parent(T)` thực chất được compiler kiểm tra với `T = String` khi đi qua kiểu `Parent<String>`.

Một lỗi thường gặp:

```java
final class Wrong extends Parent<String> {
    // Wrong() {} // Lỗi nếu Parent<T> không có constructor no-arg khả dụng.
    Wrong(String text) {
        super(text);
    }
}
```

Không ghi `super<String>(text)` để chỉ định type argument của lớp cha. Kiểu `String` đã được chọn ở **mệnh đề extends**. `super(text)` là lời gọi constructor, không phải nơi lặp lại `Parent<String>`.

### Tái sử dụng kiểm tra invariant của lớp cha

Một lớp cha có thể chặn null hoặc xác thực dữ liệu ngay trong constructor:

```java
class NonNullValue<T> {
    private final T value;

    NonNullValue(T value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    T get() { return value; }
}

final class NonNullTitle extends NonNullValue<String> {
    NonNullTitle(String title) {
        super(title);
    }
}
```

`NonNullTitle` kế thừa quy tắc không cho phép `null` của cha. Tuy nhiên, generics **không tự cấm null**: nếu constructor cha không kiểm tra, truyền `null` có thể hợp lệ về mặt kiểu. Phân biệt **type safety** với **data validation**.

## 5. Ghi đè phương thức sau khi cố định type argument

Nếu cha có phương thức `T get()`, lớp con `extends Parent<String>` có thể override bằng phương thức trả `String`:

```java
import java.util.Locale;

class Base<T> {
    private final T value;

    Base(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }
}

final class UppercaseText extends Base<String> {
    UppercaseText(String value) {
        super(value);
    }

    @Override
    public String get() {
        return super.get().toUpperCase(Locale.ROOT);
    }
}
```

Tại `UppercaseText`, `T` của `Base<T>` đã được cố định thành `String`, vì vậy `@Override public String get()` khớp hợp đồng. `@Override` giúp compiler phát hiện lỗi tên/chữ ký khi người viết tưởng đang override nhưng thực tế lại overload.

Ví dụ nếu lớp cha có setter `void set(T value)` thì lớp con cố định kiểu phải override bằng `void set(String value)` tương ứng (với cùng hoặc độ truy cập rộng hơn, cùng quy tắc checked exception). Một overload nhận `Object` thường là phương thức khác, hoặc tạo xung đột erasure tùy chữ ký: không dùng `Object` để né ràng buộc generic.

### Bridge method và type erasure

Trong ví dụ `Base<T>.get()`, type erasure làm chữ ký JVM cơ bản của getter cha tương ứng với kiểu trả `Object` (khi `T` không bound). Getter được override trong `UppercaseText` có kiểu trả `String`. Compiler có thể sinh thêm **bridge method** để giữ đa hình ở mức bytecode. Bridge là chi tiết triển khai do compiler xử lý; người học **không nên tự viết** bridge.

Kết quả ở mã nguồn vẫn bảo đảm:

```java
Base<String> base = new UppercaseText("java");
String text = base.get(); // "JAVA" nhờ dispatch động.
```

Kiểu của biến `base` là `Base<String>`; phương thức được chọn lúc chạy là implementation override trong `UppercaseText`. Generic type checking và dynamic dispatch cùng phối hợp.

## 6. Đa hình: lớp con có thể được tham chiếu bằng kiểu cha đã cố định

Quan hệ kế thừa đúng là:

```java
class Parent<T> {
    Parent(T value) {}
}

class TextChild extends Parent<String> {
    TextChild() {
        super("text");
    }
}

// Parent<String> one = new TextChild(); // Hợp lệ.
// Parent<Integer> two = new TextChild(); // Lỗi biên dịch.
```

`TextChild` là subtype của `Parent<String>`, **không phải** subtype của `Parent<Integer>` hoặc `Parent<Object>`.

Một nguyên lý rất quan trọng: dù `String extends Object`, kiểu `Parent<String>` **không kế thừa** `Parent<Object>`. Generics Java là **invariant**. Ví dụ compiler phải từ chối:

```java
Parent<String> s = new TextChild();
// Parent<Object> o = s; // Sai: không tương thích về type argument.
```

Nếu phép gán này được phép, các API nhận `Parent<Object>` có thể đưa một kiểu khác `String` vào cấu trúc đã cam kết lưu chuỗi. Java giữ ràng buộc bằng cách từ chối chuyển đổi kiểu này.

### Tham chiếu wildcard khi chưa cần biết type argument

Nếu chỉ muốn duyệt các đối tượng thuộc nhiều kiểu cha generic, hãy dùng wildcard:

```java
// Ví dụ trong một phương thức, giả sử cha có get().
Parent<?> a = new TextChild();
Object value = a.get();
```

`Parent<?>` chấp nhận một `Parent<String>`, `Parent<Integer>`, v.v. Tuy nhiên `get()` lúc này chỉ có thể coi là trả `Object` ở compile-time (trừ khi bound cung cấp kiểu cụ thể), và các thao tác ghi vào tham số chưa biết sẽ bị hạn chế.

Khi thiết kế API, **giữ `Parent<String>` nếu cần biết chính xác kiểu dữ liệu**; dùng `Parent<?>` nếu chỉ cần xử lý đối tượng như một thể hiện bất kỳ của abstraction.

## 7. Lớp con không generic khác lớp con generic thế nào?

Ba chiến lược thường gặp:

```java
class Holder<T> {
    private final T value;

    Holder(T value) { this.value = value; }

    T get() { return value; }
}

// (1) Cố định T thành String.
class StringHolder extends Holder<String> {
    StringHolder(String value) { super(value); }
}

// (2) Giữ type parameter U cho lớp con, chuyển U lên cha.
class ForwardHolder<U> extends Holder<U> {
    ForwardHolder(U value) { super(value); }
}

// (3) Lớp con generic nhưng cha cố định String.
class TaggedStringHolder<K> extends Holder<String> {
    private final K tag;

    TaggedStringHolder(K tag, String value) {
        super(value);
        this.tag = tag;
    }

    K tag() { return tag; }
}
```

Bảng so sánh:

| Kiểu lớp con | Kiểu của lớp cha | Kiểu getter kế thừa | Ý nghĩa |
| --- | --- | --- | --- |
| `StringHolder` | `Holder<String>` | `String` | Lớp con cố định hoàn toàn kiểu giá trị. |
| `ForwardHolder<Integer>` | `Holder<Integer>` | `Integer` | Lớp con tiếp tục generic theo `U`. |
| `TaggedStringHolder<Long>` | `Holder<String>` | `String` | Dữ liệu cha vẫn là chuỗi, còn `K` chỉ dành cho nhãn của lớp con. |

Lớp con **có thể generic** nhưng vẫn dùng đối số kiểu cố định ở cha. Đừng suy luận "lớp con có `<K>` nên type argument của cha phải là `K`": hai quyết định độc lập.

### Cố định một số tham số và giữ lại số khác

Với lớp cha có hai type parameters:

```java
class Pair<A, B> {
    private final A first;
    private final B second;

    Pair(A first, B second) {
        this.first = first;
        this.second = second;
    }

    A first() { return first; }
    B second() { return second; }
}

// Cố định A, giữ B do lớp con khai báo.
class NamedPair<V> extends Pair<String, V> {
    NamedPair(String name, V value) {
        super(name, value);
    }
}

// NamedPair<Integer> score = new NamedPair<>("Lan", 9);
// score.first() là String; score.second() là Integer.
```

`NamedPair<V> extends Pair<String,V>` là ví dụ **cố định một phần** của generic superclass. `String` được cố định cho tham số `A`; `V` của lớp con truyền tiếp vào tham số `B` của cha.

## 8. Kế thừa qua nhiều cấp

Cố định type argument có thể diễn ra ở một mức trung gian và tiếp tục duy trì ở các mức sau:

```java
class Base<T> {
    private final T value;
    Base(T value) { this.value = value; }
    T get() { return value; }
}

class TextBase extends Base<String> {
    TextBase(String value) { super(value); }
}

final class LocalizedText extends TextBase {
    LocalizedText(String value) { super(value); }
}

// String s = new LocalizedText("Xin chào").get();
```

`LocalizedText` không viết `extends Base<String>` trực tiếp, nhưng thông qua `TextBase`, nó vẫn kế thừa getter theo kiểu `String`. Type argument cố định ở một nhánh kế thừa tiếp tục ràng buộc các lớp con bên dưới.

Các lớp con cũng có thể triển khai thêm interface hoặc phương thức mới, nhưng không thể "đổi" kiểu đã cố định ở cha thành một kiểu khác chỉ bằng khai báo mới:

```java
// Không có nghĩa vụ và cũng không có cú pháp hợp lệ để viết:
// class Broken extends TextBase<Integer> {}
// TextBase vốn không phải generic class.
```

Nếu cần một phiên bản chứa `Integer`, hãy tạo một lớp con khác trực tiếp từ `Base<Integer>`, hoặc thiết kế một lớp con tiếp tục generic như `ForwardHolder<U>`.

## 9. Cố định kiểu khi kế thừa lớp có bound

Lớp cha có thể giới hạn type argument:

```java
class NumericHolder<T extends Number> {
    private final T number;

    NumericHolder(T number) {
        this.number = number;
    }

    T get() { return number; }

    double asDouble() {
        return number.doubleValue();
    }
}

class IntegerHolder extends NumericHolder<Integer> {
    IntegerHolder(Integer value) {
        super(value);
    }
}

// IntegerHolder ok = new IntegerHolder(7);
// class Bad extends NumericHolder<String> { } // Sai bound Number.
```

`Integer` kế thừa `Number`, nên `NumericHolder<Integer>` hợp lệ. `String` không kế thừa `Number`, nên `NumericHolder<String>` không biên dịch.

Một bound kiểu interface hoạt động tương tự:

```java
class SortedValue<T extends Comparable<T>> {
    private final T value;

    SortedValue(T value) {
        this.value = value;
    }

    boolean before(T other) {
        return value.compareTo(other) < 0;
    }
}

class TextOrder extends SortedValue<String> {
    TextOrder(String value) {
        super(value);
    }
}
```

`String` triển khai `Comparable<String>`, vì vậy đáp ứng ràng buộc của `SortedValue<T>`. Bound yêu cầu **kiểu cố định của lớp con** phải thỏa các API mà superclass sử dụng.

Khi chọn type argument, hãy kiểm tra các bound từ chữ ký cha trước; đừng dùng raw type hoặc unchecked cast nhằm vượt qua lỗi compiler.

## 10. Đối số kiểu cố định có thể là một generic type khác

`ConcreteType` trong `extends Parent<ConcreteType>` không nhất thiết phải là kiểu đơn giản như `String`; nó có thể là kiểu đã tham số hóa đầy đủ:

```java
import java.util.*;

class Value<T> {
    private final T value;
    Value(T value) { this.value = value; }
    T get() { return value; }
}

final class NameListValue extends Value<List<String>> {
    NameListValue(Collection<String> names) {
        super(List.copyOf(names));
    }
}

// NameListValue people = new NameListValue(List.of("Lan", "Mai"));
// List<String> names = people.get();
```

Với `NameListValue`, type argument `T` của cha được cố định thành **`List<String>`**, không chỉ `String`. Getter của cha có kiểu trả `List<String>`.

Ở đây `List.copyOf` chủ đích tạo danh sách không sửa được và không chứa `null`. Tính chất này đến từ factory, **không tự động được bảo đảm bởi generic inheritance**. Nếu lớp cần kiểm soát dữ liệu mutable được chia sẻ qua alias, hãy thiết kế defensive copy hoặc một chính sách sở hữu dữ liệu rõ ràng.

Có thể mở rộng mẫu này cho `Map<String, Integer>`, `Optional<User>` hoặc một record domain. Tuy nhiên, làm lớp con chỉ để đặt alias ngắn hơn có thể khiến hệ thống lớp phình to; hãy cân nhắc liệu lớp con có thêm ngữ nghĩa, validation hoặc hành vi thật sự không.

## 11. Kết hợp lớp con cố định kiểu với interface generic

Một lớp con có thể cố định superclass đồng thời triển khai một interface generic. Hai quan hệ phải được kiểm tra riêng:

```java
interface Formatter<T> {
    String format(T value);
}

class Box<T> {
    private final T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}

final class PrintableText extends Box<String> implements Formatter<String> {
    PrintableText(String value) {
        super(value);
    }

    @Override
    public String format(String value) {
        return "[" + value + "]";
    }
}
```

`Box<String>` bảo đảm dữ liệu kế thừa là `String`. `Formatter<String>` bảo đảm chữ ký `format(String)` phù hợp với hợp đồng interface. Đó là hai cách sử dụng type argument cố định, có thể phối hợp trên cùng một lớp con.

Ngược lại, khai báo `implements Formatter<Integer>` sẽ yêu cầu implementation của `format(Integer)`, chứ không tự đổi kiểu cha `Box<String>`. Java cho phép các type arguments khác nhau khi hai abstraction diễn đạt những vai trò độc lập, miễn là các chữ ký và quan hệ kế thừa không xung đột.

**Hạn chế:** một lớp không thể kế thừa cùng một generic interface theo hai type arguments khác nhau qua hai đường kế thừa xung đột (ví dụ cố đạt đồng thời `Comparable<String>` và `Comparable<Integer>`). Sự trùng nhau sau type erasure và ràng buộc kế thừa ngăn kiểu thiết kế đó.

## 12. Chương trình Java 17+ hoàn chỉnh và kiểm chứng

Tạo tệp **`FixedTypeInheritanceDemo.java`** đúng nội dung dưới đây. Tệp gom các ví dụ về superclass generic, lớp con cố định type argument, lớp con tiếp tục generic, override và interface cố định kiểu. Mã không có lỗi cố ý hoặc phụ thuộc thư viện ngoài JDK.

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class FixedTypeInheritanceDemo {
    static abstract class Storage<T> {
        private final T value;

        protected Storage(T value) {
            this.value = Objects.requireNonNull(value);
        }

        public T get() {
            return value;
        }

        public abstract String describe();
    }

    static final class TextStorage extends Storage<String> {
        TextStorage(String text) {
            super(text);
        }

        @Override
        public String get() {
            return super.get().toUpperCase(Locale.ROOT);
        }

        @Override
        public String describe() {
            return "Text(" + get() + ")";
        }
    }

    static final class NumberStorage extends Storage<Integer> {
        NumberStorage(Integer number) {
            super(number);
        }

        @Override
        public String describe() {
            return "Integer(" + get() + ")";
        }
    }

    static final class GenericStorage<U> extends Storage<U> {
        GenericStorage(U value) {
            super(value);
        }

        @Override
        public String describe() {
            return "Generic(" + get() + ")";
        }
    }

    interface Formatter<T> {
        String format(T value);
    }

    static final class TextFormatter implements Formatter<String> {
        @Override
        public String format(String value) {
            return value + "!";
        }
    }

    static void display(Storage<?> storage) {
        System.out.println(storage.describe());
    }

    public static void main(String[] args) {
        Storage<String> text = new TextStorage("java");
        Storage<Integer> count = new NumberStorage(7);
        Storage<Double> pi = new GenericStorage<>(3.14);

        System.out.println("get: " + text.get());
        System.out.println("count: " + count.get());
        System.out.println("pi: " + pi.get());

        for (Storage<?> item : List.of(text, count, pi)) {
            display(item);
        }

        Formatter<String> formatter = new TextFormatter();
        System.out.println("format: " + formatter.format("hello"));
        System.out.println("same class: " +
                (new GenericStorage<>("x").getClass()
                        == new GenericStorage<>(10).getClass()));
    }
}
```

Lưu tệp bằng UTF-8. Biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all FixedTypeInheritanceDemo.java
java FixedTypeInheritanceDemo
```

Kết quả **stdout chính xác** (đã biên dịch với chế độ `--release 17` và chạy thành công):

```text
get: JAVA
count: 7
pi: 3.14
Text(JAVA)
Integer(7)
Generic(3.14)
format: hello!
same class: true
```

**Diễn giải luồng chạy:**

1. `TextStorage extends Storage<String>` cố định type argument, nên biến `Storage<String> text` nhận được instance `TextStorage`. Override `get()` trả chuỗi viết hoa `JAVA`.
2. `NumberStorage extends Storage<Integer>` là một lớp con cố định kiểu khác của cùng superclass; `count.get()` được compiler hiểu là `Integer`.
3. `GenericStorage<U> extends Storage<U>` **không cố định type argument ở khai báo lớp**, vì `U` tiếp tục được lựa chọn cho từng cách dùng `GenericStorage<U>`. `new GenericStorage<>(3.14)` tạo `GenericStorage<Double>` tương thích `Storage<Double>`.
4. `List.of(text, count, pi)` và vòng lặp dùng `Storage<?>` để đi qua các đối tượng có type arguments khác nhau. Phương thức `display` chỉ gọi `describe()`, không cần biết kiểu dữ liệu của từng đối tượng.
5. `TextFormatter implements Formatter<String>` minh họa interface generic được cố định thành `String`; compiler kiểm tra `format(String)`.
6. Hai cách tham số hóa `GenericStorage<String>` và `GenericStorage<Integer>` có cùng `Class` runtime vì type erasure; do đó dòng cuối in `true`. Điều này không làm mất kiểm tra generic tại compile-time.

Trong chương trình, các lớp lồng được khai báo `static` để tệp độc lập và dễ chạy. Type arguments của `Storage<T>` vẫn được kiểm tra tại các trường/method instance; từ khóa `static` ở đây chỉ mô tả **vị trí lồng của lớp** trong `FixedTypeInheritanceDemo`.

## 13. Những hiểu nhầm và lỗi compiler phổ biến

| Sai lầm / tình huống | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `class Child extends Parent` | Dùng **raw superclass**, đánh mất thông tin type argument | Khai báo `extends Parent<String>` hoặc một type argument phù hợp. |
| `class Child extends Parent<>` | Diamond `<>` không dùng trong mệnh đề `extends` | Ghi type argument cụ thể: `extends Parent<String>`. |
| `class Child<T> extends Parent<T>` nhưng mong cha luôn giữ `String` | `T` vẫn do người sử dụng Child lựa chọn | Nếu muốn cố định: `class Child extends Parent<String>`. |
| `class Child extends Parent<String>` rồi truyền `Integer` vào `super(...)` | Constructor cha yêu cầu `String` | Chuyển đổi đầu vào có chủ đích trước khi gọi `super(...)`. |
| Lớp cha không có constructor no-arg, con bỏ `super(...)` | Không có constructor cha phù hợp để gọi ngầm | Khai báo constructor con và gọi `super(value)`. |
| Override `T get()` bằng kiểu không tương thích sau khi cố định `T` | Chữ ký override không khớp kiểu trả về | Với `Parent<String>`, trả `String` hoặc kiểu trả về covariant hợp lệ. |
| Gán `Parent<String>` sang `Parent<Object>` | Generics Java invariant | Giữ type argument chính xác hoặc dùng `Parent<?>` nếu chỉ cần đọc chung. |
| Tạo `extends Parent<int>` | Primitive không là generic type argument | Sử dụng `Integer`. |
| `extends NumericParent<String>` với `T extends Number` | Không đạt bound của superclass | Chọn `Integer`/`Double` hoặc kiểu số thỏa bound. |
| Trong lớp con, cố truy cập `private T value` của cha | `private` không đổi vì generic inheritance | Dùng accessor hoặc API được thiết kế rõ ràng. |
| Kế thừa cùng generic interface qua hai type arguments xung đột | Java không cho kiểu kế thừa không nhất quán | Phân tách abstraction hoặc thống nhất hợp đồng. |
| `instanceof Parent<String>` | Type argument `String` không được kiểm tra bằng `instanceof` thông thường | Dùng `instanceof Parent<?>` rồi xác thực nội dung nếu cần. |
| Nghĩ `extends Parent<String>` tạo lớp runtime riêng cho `Parent<String>` | Generic type arguments phần lớn bị erase | Phân biệt kiểu nguồn compile-time và `Class` runtime. |
| Dùng raw type hoặc unchecked cast để qua lỗi compiler | Có nguy cơ heap pollution và `ClassCastException` | Thiết kế lại quan hệ kiểu, dùng wildcard/bound đúng vai trò. |

### Dùng `@Override` để nhận ra lỗi sớm

Luôn cân nhắc đặt `@Override` khi lớp con cố định kiểu ghi đè phương thức từ cha:

```java
class Parent<T> {
    public T get() { return null; }
}

class Child extends Parent<String> {
    @Override
    public String get() {
        return "ok";
    }
}
```

Nếu vô tình viết `get(String arg)`, annotation `@Override` sẽ giúp phát hiện rằng đó không phải override của `get()`. Đây là cách thực hành tốt khi generic substitution làm chữ ký inherited dễ nhìn nhầm.

## 14. Khi nào nên cố định kiểu, khi nào giữ lớp con generic?

**Cố định kiểu trong `extends` khi** lớp con mang một ý nghĩa chuyên biệt và mọi instance hợp lệ của nó cần cùng một loại dữ liệu. Ví dụ `TextStorage` cần thao tác trên chuỗi, `IntegerHolder` cung cấp logic cho giá trị số nguyên. Lớp con có thể bổ sung validation, định dạng, method domain hoặc tối ưu hóa mà vẫn tái sử dụng abstraction chung.

**Tiếp tục generic** với `class ForwardStorage<U> extends Storage<U>` khi hành vi mới vẫn áp dụng được cho nhiều loại dữ liệu. Đừng tạo các lớp con cố định kiểu nếu việc duy nhất của chúng là gọi `super(...)` mà không tạo thêm giá trị về mặt mô hình hay API.

Nếu chỉ muốn gán một cái tên cho một tổ hợp generic phổ biến như `List<String>`, hãy cân nhắc giữ nguyên type rõ ràng trong API, dùng record/domain object có ý nghĩa hoặc composition. Kế thừa implementation collection như `HashMap<String,Integer>` chỉ để tạo tên ngắn đôi khi khiến lớp khó bảo trì, nhất là khi đối tượng không thật sự là một subtype có hành vi riêng.

Ví dụ thiết kế domain phù hợp:

```java
record UserId(String value) {
    UserId {
        java.util.Objects.requireNonNull(value);
    }
}

class Identifier<T> {
    private final T value;

    Identifier(T value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    T get() { return value; }
}

final class UserIdentifier extends Identifier<UserId> {
    UserIdentifier(UserId id) {
        super(id);
    }
}
```

`UserIdentifier` cố định kiểu của cha thành một record domain cụ thể `UserId`. Cách thiết kế này có ý nghĩa nếu API của hệ thống muốn phân biệt ID người dùng với các ID khác và áp dụng hành vi/validation riêng.

## 15. Bài tập và tiêu chí tự đánh giá

**Bài 1 — Getter có kiểu cố định.** Viết `class Box<T>` giữ `T value` và getter `T get()`. Tạo `class LongBox extends Box<Long>`; thiết kế constructor gọi `super(Long)`. Thử gán `LongBox` cho `Box<Long>`, sau đó thử gán cho `Box<Number>` và giải thích vì sao phép gán thứ hai thất bại.

**Bài 2 — Override.** Viết `class MessageBox extends Box<String>`, override getter để thêm tiền tố `"Message: "`. Dùng `Box<String> ref = new MessageBox("Hi")` và gọi `ref.get()`; giải thích sự phối hợp của type checking và dynamic dispatch.

**Bài 3 — Giữ type parameter.** Viết `class History<T> extends Box<List<T>>`. Vì sao lớp con **vẫn generic**, dù kiểu của cha là `Box<List<T>>`? Kiểm tra `History<Integer>` có getter trả `List<Integer>`. Nếu thay `T` bằng `String`, hãy mô tả lớp con cố định thành `Box<List<String>>`.

**Bài 4 — Bound.** Viết `class PositiveInteger extends NumericHolder<Integer>` chỉ chấp nhận số dương. Đưa validation vào constructor hoặc một factory có tên rõ. Kiểm tra caller không thể tạo đối tượng chứa `String` và giải thích hai lớp bảo vệ độc lập: **bound generic** và **ràng buộc nghiệp vụ giá trị dương**.

**Bài 5 — Chuỗi kế thừa.** Tạo `Base<T> → FixedBase extends Base<String> → FinalText extends FixedBase`. Phương thức getter ở `FinalText` trả kiểu gì? Có được khai báo `FinalText extends FixedBase<Integer>` không? Vì sao?

**Bài 6 — Interface generic.** Tạo `interface Serializer<T>` có `String serialize(T item)`. Viết `UserSerializer implements Serializer<User>` với record `User(String name)`; nêu kiểu tham số bắt buộc của phương thức override. Nếu đồng thời kế thừa `Box<String>`, hai ràng buộc generic có vai trò gì?

**Bài 7 — Reflection và runtime.** Dự đoán kết quả kiểm tra `new GenericStorage<>("a").getClass() == new GenericStorage<>(1).getClass()`. Vì sao kết quả không có nghĩa Java cho phép gán `GenericStorage<String>` sang `GenericStorage<Integer>`?

**Bài 8 — Thiết kế API.** Một nhóm chỉ cần hàm `display(Storage<?> storage)` để in mô tả. Khi nào nên nhận wildcard `Storage<?>`, khi nào cần giữ `Storage<String>` để gọi phương thức dành cho chuỗi? Hãy liên hệ mục đích của API với độ an toàn của thao tác.

Bạn đã nắm bài khi có thể trả lời: **lớp con khai báo type parameter mới hay không; tham số nào của superclass được cố định; kiểu của constructor/getter/setter sau khi cố định là gì; và vì sao `Parent<String>` không đồng nghĩa `Parent<Object>`**. Việc nắm chính xác phép ánh xạ kiểu qua `extends` giúp xây dựng cây kế thừa tái sử dụng được mà vẫn bảo đảm an toàn kiểu tại thời điểm biên dịch.

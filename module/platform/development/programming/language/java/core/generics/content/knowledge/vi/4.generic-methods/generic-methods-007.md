# Constructor generic và phân biệt với constructor của lớp generic trong Java

## 1. Mục tiêu và câu hỏi trung tâm

Trong Java, **lớp generic** và **constructor generic** đều dùng tham số kiểu nhưng chúng khai báo tham số ấy ở **hai phạm vi khác nhau**:

- `class Box<T>`: `T` là tham số kiểu **của lớp**, được lựa chọn khi sử dụng kiểu `Box<String>`, `Box<Integer>`...
- `<U> Box(U input)`: `U` là tham số kiểu **riêng của constructor**, được suy luận hoặc chỉ định theo **lần tạo đối tượng**.
- `class Box<T> { Box(T value) { ... } }`: constructor dùng `T` của lớp nhưng **không phải generic constructor theo nghĩa khai báo tham số kiểu riêng**.
- Một **lớp thông thường** không có `<T>` vẫn có thể khai báo **constructor generic**.

Sự khác biệt này quan trọng khi đối tượng cần lưu một kiểu `T`, nhưng dữ liệu khởi tạo đến từ kiểu `U` khác và cần chuyển đổi thành `T`. Nó cũng giúp hiểu vì sao có thể kết hợp `new Holder<>(...)` với phương thức chuyển đổi, không cần ép kiểu thủ công.

Bài học tập trung vào **cú pháp constructor**, phạm vi type parameter, type inference, bound, overload và cách ứng dụng. Ví dụ độc lập cuối bài tương thích **Java 17+**.

## 2. Trước hết: constructor của lớp generic chưa chắc là generic constructor

Xét một lớp tổng quát chỉ giữ một giá trị:

```java
// Mảnh mã minh họa, cần đặt trong tệp Java phù hợp.
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

Box<String> greeting = new Box<>("Xin chào");
Box<Integer> quantity = new Box<>(5);
```

Có hai tầng cần tách bạch:

1. `<T>` sau `Box` **khai báo tham số kiểu của lớp**.
2. Constructor `Box(T value)` **dùng tham số `T` đã có**, không tự khai báo tham số kiểu nào khác.

`Box<String>` xác lập `T = String`, vì vậy constructor nhận `String`, getter trả `String`. `Box<Integer>` tương tự với `Integer`. Nếu truyền kiểu không phù hợp, compiler từ chối:

```java
// Box<Integer> wrong = new Box<Integer>("hello"); // Lỗi biên dịch.
```

Diamond `<>` trong `new Box<>("Xin chào")` chỉ là ký hiệu **suy luận type argument của lớp** từ ngữ cảnh và đối số constructor. **Có diamond không đồng nghĩa constructor generic.**

So sánh với một lớp không generic:

```java
final class NameTag {
    private final String name;

    NameTag(String name) {
        this.name = name;
    }
}
```

`NameTag(String)` không khai báo tham số kiểu riêng; `NameTag` cũng không có tham số kiểu. Cả hai trường hợp `Box(T)` và `NameTag(String)` đều là những constructor thông thường theo tiêu chí "constructor có khai báo type parameter riêng hay không".

## 3. Cú pháp chính xác của generic constructor

Một constructor được gọi là **generic constructor** khi ngay trên constructor có danh sách khai báo tham số kiểu, ví dụ `<U>` hoặc `<S extends Number>`, **đứng trước tên constructor**:

```java
import java.util.function.Function;

// Mảnh mã minh họa.
final class ConvertedBox<T> {
    private final T value;

    <S> ConvertedBox(S source, Function<? super S, ? extends T> converter) {
        this.value = converter.apply(source);
    }

    T get() {
        return value;
    }
}
```

Trong mã trên:

- `T` thuộc về `ConvertedBox<T>`: nó là kiểu của dữ liệu được lưu và giá trị getter.
- `S` thuộc về constructor `<S> ConvertedBox(...)`: nó là kiểu của **nguồn** ở một lần khởi tạo.
- `Function<? super S, ? extends T>` biểu diễn phép chuyển từ nguồn `S` sang dữ liệu tương thích `T`.
- Sau khi constructor kết thúc, đối tượng vẫn là `ConvertedBox<T>`; nó **không mang thêm tham số lớp `S`**.

Cách sử dụng:

```java
ConvertedBox<Integer> length =
        new ConvertedBox<>("Java", String::length);
Integer n = length.get(); // 4.

ConvertedBox<String> numberText =
        new ConvertedBox<>(42, Object::toString);
String text = numberText.get(); // "42".
```

Ở lời gọi thứ nhất, compiler phải làm cho `T = Integer` phù hợp với kiểu đích của biến, đồng thời suy luận `S = String` cho đối số `"Java"`. Ở lời gọi thứ hai, `T = String` và `S = Integer`. Thay đổi nguồn đầu vào **không thay đổi nghĩa của kiểu đích**.

Cú pháp tổng quát của constructor:

```java
// modifiers <type-parameters> ClassName(parameter-list) throws ExceptionType {
//     // thân constructor
// }
```

**Không khai báo kiểu trả về cho constructor**, kể cả `void`. Trường hợp `<U> Box(U source)` vẫn là constructor vì sau `<U>` là **tên lớp** `Box`, không có kiểu trả về.

## 4. Lớp bình thường vẫn có constructor generic

Lớp không cần khai báo `<T>` mới được phép khai báo constructor có `<U>`. Ví dụ, một lớp chỉ muốn giữ chuỗi mô tả từ nhiều loại nguồn khác nhau:

```java
import java.util.function.Function;

// Mảnh mã minh họa.
final class DisplayText {
    private final String content;

    <S> DisplayText(S source, Function<? super S, String> formatter) {
        this.content = formatter.apply(source);
    }

    String content() {
        return content;
    }
}

// Trong một phương thức Java:
DisplayText count = new DisplayText(123, Object::toString);
DisplayText upper = new DisplayText("java", String::toUpperCase);
```

`DisplayText` là **lớp thông thường**, không có type parameter trên tên lớp. `S` chỉ tồn tại trong khai báo constructor. Vì `formatter` tạo `String`, dữ liệu cuối cùng vẫn luôn được lưu ở trường `String content`.

Điểm ứng dụng: constructor nhận **nhiều nguồn có kiểu khác nhau**, nhưng đối tượng thành phẩm có cấu trúc cố định. Trong một số API, static factory hoặc method generic có tên rõ ràng có thể dễ đọc hơn một constructor chung; chọn dựa trên hợp đồng khởi tạo thực tế.

### Một constructor có thể dùng nhiều tham số kiểu

```java
import java.util.function.BiFunction;

final class RenderedText {
    private final String rendered;

    <A, B> RenderedText(
            A first,
            B second,
            BiFunction<? super A, ? super B, String> format) {
        rendered = format.apply(first, second);
    }

    String value() {
        return rendered;
    }
}

// RenderedText view = new RenderedText("Lan", 9,
//         (name, score) -> name + ": " + score);
// view.value() là "Lan: 9".
```

`A` và `B` là hai tham số kiểu **của constructor**; chúng có thể khác nhau. Vì vậy, `<A,B>` diễn đạt chính xác hơn việc ép cả hai đối số thành cùng một `T`. Với converter, `? super A` và `? super B` cho phép hàm nhận kiểu cha thích hợp, đồng thời đầu ra của `BiFunction` là `String`.

## 5. Lớp generic có thể vừa có constructor thường vừa có constructor generic

Một lớp có thể khai báo hai constructor khác nhau, mỗi constructor phục vụ một đường khởi tạo riêng:

```java
import java.util.Objects;
import java.util.function.Function;

final class Holder<T> {
    private final T value;

    // Constructor thường: chỉ dùng T của lớp.
    Holder(T initial) {
        this.value = Objects.requireNonNull(initial);
    }

    // Constructor generic: khai báo thêm S của riêng constructor.
    <S> Holder(S source, Function<? super S, ? extends T> mapper) {
        this.value = Objects.requireNonNull(mapper.apply(source));
    }

    T get() {
        return value;
    }
}
```

Gọi hai overload:

```java
Holder<String> simple = new Holder<>("Lan");

Holder<Integer> transformed =
        new Holder<>("Spring", String::length);

String a = simple.get();        // "Lan".
Integer b = transformed.get();  // 6.
```

Với overload `Holder(T initial)`, dữ liệu đầu vào đã có kiểu phù hợp `T` nên không cần converter. Với `<S> Holder(S, Function<...>)`, nguồn có thể khác kiểu đích và cần một hàm chuyển đổi tường minh.

Constructor generic **không biến cả lớp thành generic theo một tham số mới**. Lớp chỉ có `T`; `S` của constructor không được truy cập ở getter hay phương thức khác, trừ khi chúng tự khai báo tham số kiểu phù hợp.

### Vì sao không nên khai báo `<T>` trùng tên của lớp?

Cú pháp sau có thể hợp lệ nhưng gây nhầm lẫn:

```java
class Confusing<T> {
    private final T value;

    // <T> ở constructor là T MỚI, che T của lớp trong chữ ký này.
    <T> Confusing(T input) {
        // this.value = input; // Không hợp lệ: hai T không được đảm bảo giống nhau.
        this.value = null; // Chỉ minh họa lỗi thiết kế.
    }
}
```

Hai tên `T` giống nhau không đồng nghĩa chúng cùng một type parameter. `<T>` được constructor khai báo **che khuất** tham số kiểu `T` của lớp bên trong phạm vi constructor, làm mất quan hệ an toàn giữa `input` và trường `value`. Trong thực tế **không nên viết** constructor kiểu này; hãy dùng `<S>` nếu cần một tham số riêng, hoặc bỏ `<...>` nếu đầu vào phải đúng kiểu `T` của lớp.

## 6. Cách compiler suy luận kiểu của lớp và kiểu của constructor

Khi gặp:

```java
Holder<Integer> result = new Holder<>("Java", String::length);
```

Compiler có hai nhiệm vụ liên quan nhưng riêng biệt:

1. Tìm type argument cho **lớp** `Holder<T>`, phù hợp với ngữ cảnh đích `Holder<Integer>`, nghĩa là `T = Integer`.
2. Tìm type argument cho **constructor generic** `<S> Holder(S, Function<? super S, ? extends T>)`, phù hợp với chuỗi nguồn và mapper, nghĩa là `S = String`.

Compiler kiểm tra `String::length` có thể dùng để tạo kết quả kiểu `Integer` cho phương thức `Function.apply` hay không. `String.length()` trả primitive `int`, được boxing thành `Integer` khi cần.

### Diamond `<>` áp dụng cho tham số kiểu của lớp

```java
Holder<String> first = new Holder<>("Hi");
Holder<String> second = new Holder<String>("Hi");
```

`new Holder<>()` bỏ việc lặp lại `String` bên phải khi compiler có đủ ngữ cảnh. Đây là **diamond operator**, không phải danh sách type parameter của constructor. Dù chọn overload generic hay overload thường, biểu thức `new` vẫn tạo đối tượng của kiểu lớp `Holder<T>`.

### Khi dùng `var`, phải xem kiểu suy luận là gì

```java
var text = new Holder<>("Java");
var length = new Holder<>("Java", String::length);
```

Ở dòng đầu, compiler có thể suy luận `Holder<String>` từ constructor nhận giá trị `"Java"`. Dòng thứ hai, chữ ký mapper và target type không tường minh tạo bài toán suy luận phức tạp hơn; đừng mặc định compiler luôn suy luận đúng kiểu cuối cùng mà bạn muốn. Để thể hiện hợp đồng dữ liệu mong muốn, khai báo đích rõ:

```java
Holder<Integer> length = new Holder<>("Java", String::length);
```

Nếu inference trở nên khó đọc hoặc compiler báo không giải được type constraints, có thể truyền type argument tường minh cho lớp hoặc thiết kế factory method có chữ ký rõ hơn.

### Chỉ định type argument của constructor tường minh

Constructor generic hỗ trợ **explicit constructor type arguments** ở dạng sau:

```java
// Giả sử class Holder<T> có generic constructor <S> Holder(S, Function<...>).
Holder<Integer> length =
        new <String> Holder<Integer>("Java", String::length);
```

`<String>` **đặt sau `new` và trước tên lớp** là đối số kiểu **của constructor** `S`. `<Integer>` đi sau `Holder` là đối số kiểu **của lớp** `T`. Đây là cú pháp khác với lời gọi **generic method** `Collections.<String>emptyList()`. Thông thường hãy để Java tự suy luận constructor type arguments cho ngắn gọn; chỉ ghi tường minh khi thực sự giúp chẩn đoán hoặc làm rõ chữ ký.

Không dùng dạng `new Holder<String><Integer>(...)`: Java không đặt danh sách type arguments của constructor sau tên kiểu. Khi chỉ định constructor type arguments tường minh, chọn cú pháp hợp lệ như ví dụ `new <String> Holder<Integer>(...)`.

## 7. Constructor generic có bounded type parameter

Khi quá trình tạo đối tượng cần thao tác chỉ có trên một số loại dữ liệu, thêm upper bound ngay tại type parameter của constructor:

```java
import java.util.Collection;

final class NumericSummary {
    private final double total;

    <N extends Number> NumericSummary(Collection<N> values) {
        double result = 0;
        for (N value : values) {
            result += value.doubleValue();
        }
        this.total = result;
    }

    double total() {
        return total;
    }
}

// NumericSummary ints = new NumericSummary(List.of(1, 2, 3));
// NumericSummary doubles = new NumericSummary(List.of(1.5, 2.5));
// new NumericSummary(List.of("a", "b")); // Không đạt bound Number.
```

`<N extends Number>` nghĩa là **chỉ constructor** yêu cầu nguồn thuộc `Number` hoặc kiểu con; lớp `NumericSummary` không phải lớp generic. Compiler cho phép gọi `doubleValue()` vì bound đã bảo đảm thao tác đó tồn tại. Bound interface cũng dùng từ khóa `extends`, ví dụ `<S extends CharSequence>`.

Nếu cần nhiều bound, dùng `<N extends Number & Comparable<N>>`; bound lớp, nếu có, phải đứng trước các interface. Hãy chọn bound đủ đáp ứng thao tác của constructor, tránh ép kiểu có thể gây lỗi.

### Bounded constructor không phải lớp có bound

Hai thiết kế có khác biệt:

```java
// Lớp giữ nguyên kiểu số T xuyên suốt đời đối tượng.
final class NumberHolder<T extends Number> {
    private final T value;
    NumberHolder(T value) { this.value = value; }
    T get() { return value; }
}

// Lớp không generic, constructor tạm dùng N để đọc giá trị số.
final class DoubleSnapshot {
    private final double value;
    <N extends Number> DoubleSnapshot(N source) {
        value = source.doubleValue();
    }
    double get() { return value; }
}
```

`NumberHolder<Integer>.get()` trả `Integer` theo hợp đồng generic của lớp. `DoubleSnapshot.get()` luôn trả `double`; tham số `N` chỉ có ý nghĩa **trong lúc khởi tạo**. Constructor generic thích hợp nếu dữ liệu từ nhiều kiểu được chuẩn hóa về một representation duy nhất.

## 8. Constructor chaining: `this(...)` và `super(...)`

Một constructor có thể gọi constructor khác của chính lớp bằng `this(...)` hoặc constructor của lớp cha bằng `super(...)`. Với lớp generic, kiểu truyền giữa các bước phải được compiler kiểm tra.

```java
import java.util.function.Function;

class BaseBox<T> {
    private final T value;
    BaseBox(T value) { this.value = value; }
    T get() { return value; }
}

final class ConvertedChild<T> extends BaseBox<T> {
    <S> ConvertedChild(S source, Function<? super S, ? extends T> converter) {
        super(converter.apply(source));
    }
}

// ConvertedChild<Integer> c =
//         new ConvertedChild<>("hello", String::length);
```

Ở đây `T` đến từ lớp con và đi tiếp vào lớp cha `BaseBox<T>`; `S` chỉ thuộc constructor, dùng để chuyển nguồn. Lời gọi `super(...)` là câu lệnh đầu tiên của constructor trên Java 17, đúng cú pháp chuẩn.

Một ví dụ chuyển hướng giữa các overload:

```java
import java.util.function.Function;

final class Payload<T> {
    private final T value;

    Payload(T direct) {
        this.value = direct;
    }

    <S> Payload(S source, Function<? super S, ? extends T> converter) {
        this(converter.apply(source));
    }

    T get() { return value; }
}
```

Constructor generic gọi constructor thường sau khi có dữ liệu `T`. Điều này tránh lặp logic thiết lập trường và kiểm tra invariant; nếu muốn chặn `null`, kiểm tra tại constructor chính, ví dụ `this.value = Objects.requireNonNull(direct)`.

Cần nhớ: mỗi constructor phải kết thúc với toàn bộ trường `final` được gán đúng một lần theo các đường khởi tạo hợp lệ. Việc dùng generic không thay đổi quy tắc definite assignment của Java.

## 9. Khi nào nên dùng static generic factory thay constructor generic?

Constructor generic hợp lý khi mục đích tạo đối tượng có thể biểu diễn rõ qua chữ ký. Nhưng compiler đôi khi khó suy luận quan hệ giữa kiểu nguồn và kiểu đích với diamond, đặc biệt khi có nhiều overload. **Static factory method generic** là lựa chọn thường dễ đọc hơn:

```java
import java.util.function.Function;

final class Result<T> {
    private final T value;

    private Result(T value) {
        this.value = value;
    }

    static <T> Result<T> of(T value) {
        return new Result<>(value);
    }

    static <S, T> Result<T> from(
            S source,
            Function<? super S, ? extends T> converter) {
        return new Result<>(converter.apply(source));
    }

    T get() { return value; }
}

// Result<Integer> length = Result.from("Java", String::length);
// Result<String> rawValue = Result.of("Java");
```

Ở `Result.from`, cả `S` và `T` đều là tham số kiểu **của factory method**. Trong constructor generic của `ConvertedBox<T>`, `T` thuộc lớp còn `S` thuộc constructor. Cả hai cách đều có thể an toàn kiểu; tên phương thức `from` nêu rõ thao tác **chuyển đổi** và giúp API dễ mở rộng hoặc ghi chú chính sách validation.

Factory cũng cho phép trả về subtype, instance cache, object singleton hoặc loại cụ thể khác khi hợp đồng cho phép; constructor luôn khởi tạo lớp cụ thể được viết sau `new`.

### Phân biệt factory generic với diamond

```java
Result<String> one = Result.of("abc");    // Generic method inference.
Result<String> two = new Result<>("abc"); // Chỉ hợp lệ nếu constructor accessible.
```

Nếu constructor là `private` như ví dụ `Result` ở trên, dòng thứ hai **không hợp lệ bên ngoài lớp**. Nó chỉ minh họa rằng có hai cơ chế khác nhau: `of` là method generic, còn `new Result<>(...)` là biểu thức khởi tạo có diamond và bị kiểm soát bởi access modifier. Không thêm mã có lỗi vào chương trình runnable.

## 10. Generic constructor trong record và quy tắc gọi constructor

Với `record` generic, tham số kiểu lớp vẫn thuộc về record:

```java
record Item<T>(T value) {
    // Constructor thông thường tương đương canonical constructor ở góc độ kiểu T.
}
```

Một constructor khác canonical trong record phải **ủy quyền trực tiếp hoặc gián tiếp cho canonical constructor bằng `this(...)`**. Nó cũng có thể khai báo tham số kiểu riêng:

```java
import java.util.function.Function;

record ValueRecord<T>(T value) {
    <S> ValueRecord(S source, Function<? super S, ? extends T> converter) {
        this(converter.apply(source));
    }
}

// ValueRecord<Integer> n = new ValueRecord<>("Java", String::length);
// n.value() trả Integer 4.
```

`T` thuộc record, `S` thuộc constructor bổ sung. Đây là cách áp dụng tương tự lớp generic thông thường, nhưng phải tuân thủ quy tắc constructor của `record`. Không nên tạo một constructor mang kiểu nguồn tùy ý khi một static factory đặt tên rõ hơn và tránh nhập nhằng overload.

## 11. Tham số kiểu không tồn tại như một giá trị runtime

Java generics chủ yếu dùng **type erasure**: type parameter được kiểm tra lúc biên dịch rồi bị thay bằng bound thích hợp trong biểu diễn runtime thông thường. Điều này đúng cả với generic constructor.

```java
// Mảnh minh họa trong một constructor <S> hoặc phương thức <S>:
// S instance = new S();       // Sai: không biết constructor thực sự của S.
// Class<S> clazz = S.class;    // Sai: không có S.class.
// boolean ok = source instanceof S; // Sai với type parameter không reifiable.
```

Nếu cần **tạo mới một `S`** bên trong constructor, truyền factory hoặc thông tin kiểu phù hợp:

```java
import java.util.function.Supplier;

final class ProducedText {
    private final String text;

    <S> ProducedText(Supplier<S> factory) {
        S source = factory.get();
        this.text = String.valueOf(source);
    }

    String text() { return text; }
}

// ProducedText view = new ProducedText(StringBuilder::new);
```

Việc tạo đối tượng được giao cho `Supplier<S>` thay vì cố gọi `new S()`. `String.valueOf(null)` trả chuỗi `"null"`, khác với `Objects.requireNonNull` sẽ ném `NullPointerException`; chọn chính sách rõ ràng theo yêu cầu API.

### Overload theo type parameter có thể đụng erasure

Hai constructor sau **không được khai báo đồng thời**:

```java
// Ví dụ cố ý không biên dịch.
class Invalid {
    <S> Invalid(java.util.List<S> items) {}
    Invalid(java.util.List<String> items) {}
}
// Hai chữ ký sau erasure cùng nhận List nên name clash.
```

Tương tự, `<S> Invalid(S item)` sau erasure thường có parameter `Object` nếu `S` không bound; đừng dựa vào generic parameter để phân biệt overload vốn có chữ ký erasure giống nhau.

## 12. Chương trình Java 17+ chạy độc lập

Tạo tệp **`GenericConstructorDemo.java`** với nội dung sau. Chương trình minh họa constructor thường nhận `T` của lớp, constructor generic nhận `S` riêng, constructor generic trong lớp thông thường, bound và constructor chaining.

```java
import java.util.*;
import java.util.function.Function;

public class GenericConstructorDemo {
    static final class Holder<T> {
        private final T value;

        Holder(T direct) {
            this.value = Objects.requireNonNull(direct);
        }

        <S> Holder(S source, Function<? super S, ? extends T> mapper) {
            this(mapper.apply(source));
        }

        T get() {
            return value;
        }
    }

    static final class DisplayText {
        private final String text;

        <S> DisplayText(S source, Function<? super S, String> format) {
            text = Objects.requireNonNull(format.apply(source));
        }

        String value() {
            return text;
        }
    }

    static final class NumericSummary {
        private final double total;

        <N extends Number> NumericSummary(Collection<N> numbers) {
            double sum = 0;
            for (N number : numbers) {
                sum += number.doubleValue();
            }
            total = sum;
        }

        double total() {
            return total;
        }
    }

    static class BaseBox<T> {
        private final T value;

        BaseBox(T value) {
            this.value = Objects.requireNonNull(value);
        }

        T get() {
            return value;
        }
    }

    static final class ChildBox<T> extends BaseBox<T> {
        <S> ChildBox(S source, Function<? super S, ? extends T> mapper) {
            super(mapper.apply(source));
        }
    }

    record RecordValue<T>(T value) {
        <S> RecordValue(S source, Function<? super S, ? extends T> mapper) {
            this(mapper.apply(source));
        }
    }

    public static void main(String[] args) {
        Holder<String> direct = new Holder<>("Lan");
        Holder<Integer> converted = new Holder<>("Generics", String::length);
        Holder<String> explicit =
                new <Integer> Holder<String>(42, Object::toString);
        System.out.println("direct: " + direct.get());
        System.out.println("converted: " + converted.get());
        System.out.println("explicit: " + explicit.get());

        DisplayText label = new DisplayText(2026, n -> "Year-" + n);
        System.out.println("display: " + label.value());

        NumericSummary numbers = new NumericSummary(List.of(1, 2, 3));
        System.out.println("sum: " + numbers.total());

        ChildBox<Integer> child =
                new ChildBox<>("Java", String::length);
        System.out.println("child: " + child.get());

        RecordValue<Integer> record =
                new RecordValue<>("Spring", String::length);
        System.out.println("record: " + record.value());
    }
}
```

Lệnh biên dịch và thực thi (trong thư mục chứa tệp):

```bash
javac -Xlint:all GenericConstructorDemo.java
java GenericConstructorDemo
```

Stdout của chương trình:

```text
direct: Lan
converted: 8
explicit: 42
display: Year-2026
sum: 6.0
child: 4
record: 6
```

Giải thích kết quả:

1. `direct` gọi constructor thường `Holder(T)`; `T = String` được chọn từ kiểu `Holder<String>`.
2. `converted` gọi generic constructor `<S> Holder(S, Function<...>)`; `S = String` của đầu vào khác `T = Integer` của đối tượng. `"Generics".length()` bằng `8`.
3. `explicit` chỉ định tường minh `S = Integer` qua `new <Integer> Holder<String>(...)`; `T = String` vẫn thuộc về lớp.
4. `DisplayText` không generic nhưng constructor `<S> DisplayText(...)` suy luận `S = Integer` rồi chuyển thành chuỗi.
5. `NumericSummary` nhận dữ liệu có bound `N extends Number` để cộng qua `doubleValue()`.
6. `ChildBox<T>` dùng `S` riêng trong constructor rồi đưa giá trị `T` cho `super(...)` của lớp cha.
7. `RecordValue<T>` có constructor generic và phải ủy quyền tới canonical constructor bằng `this(...)`.

Các ví dụ lỗi biên dịch trong bài được comment riêng; không phải lời gọi cần chạy trong chương trình hoàn chỉnh.

## 13. Cách lựa chọn giữa constructor thường, generic constructor và factory

| Tình huống | Cách diễn đạt phù hợp | Lý do |
| --- | --- | --- |
| Đối tượng lưu đúng giá trị `T` truyền vào | `class Box<T> { Box(T value) {} }` | Constructor thường, quan hệ kiểu trực tiếp, dễ hiểu |
| Đầu vào là `S` khác kiểu `T` nhưng có converter để tạo `T` | `<S> Box(S source, Function<? super S, ? extends T> f)` | Generic constructor nối kiểu nguồn tạm thời với kiểu kết quả |
| Lớp không generic nhưng dữ liệu nguồn có thể mang nhiều kiểu | `class Label { <S> Label(S source, Function<? super S, String> f) {} }` | `S` chỉ cần khi khởi tạo |
| Muốn diễn đạt thao tác `from`/`parse`/`of` rõ ràng, tránh overload khó hiểu | `static <S,T> Result<T> from(S, Function<...>)` | Static generic factory có tên mô tả ý nghĩa |
| Chỉ nhận `Number` và chuyển về `double` | `<N extends Number> Summary(N value)` | Bound bảo đảm API cần thiết khi chuyển |
| Cần tạo dữ liệu kiểu `S` bên trong | Truyền `Supplier<S>` hoặc factory | Erasure không cho phép `new S()` |
| Dữ liệu đầu vào đã cùng kiểu lưu trữ | Constructor `Box(T)` | Không cần thêm tham số kiểu thứ hai |

Một nguyên tắc thiết kế: đừng khai báo constructor generic chỉ để tránh viết `Object`. Nếu `S` không liên kết các vị trí đầu vào hoặc không được bound/callback sử dụng để mang lại kiểm tra kiểu hữu ích, một constructor nhận kiểu phù hợp hoặc một static factory đơn giản hơn có thể rõ ràng hơn.

## 14. Những lỗi thường gặp

| Sai lầm | Điều xảy ra | Cách sửa |
| --- | --- | --- |
| Nghĩ `Box(T)` là generic constructor vì `Box<T>` generic | Nhầm phạm vi type parameter | Constructor chỉ generic khi **tự khai báo** `<S>` hoặc type parameter tương tự |
| Viết `Box<T>(T input)` làm tên constructor | Không phải cú pháp constructor Java | Khai báo `Box(T input)` |
| Viết `<S> void Box(S input)` và tưởng là constructor | Có kiểu trả về `void`, đây là **method**, không phải constructor | Bỏ kiểu trả về: `<S> Box(S input)` |
| Dùng `<T> Box(T input)` trong `class Box<T>` và nghĩ là cùng `T` | `T` của constructor che khuất `T` của lớp | Dùng `Box(T)` hoặc đặt tham số riêng `<S>` |
| Không phân biệt `new Box<>()` với `<S> Box(...)` | Diamond dành cho type arguments của lớp trong lời gọi, `<S>` khai báo tham số của constructor | Xác định rõ vị trí đặt ký hiệu |
| Gọi `new T()` hoặc `new S()` bên trong constructor | Không có thông tin constructor runtime từ type parameter | Truyền `Supplier<T>` hoặc factory |
| Constructor `<N extends Number>` nhận dữ liệu `String` | Không đạt upper bound | Dùng nguồn thuộc `Number` hoặc đổi API chuyển đổi |
| Overload constructor theo `List<String>` và `List<Integer>` | Name clash sau type erasure | Đổi chữ ký thực sự, dùng factory có tên hoặc một constructor generic |
| Constructor generic dùng raw type và unchecked cast | Có thể làm hỏng type safety của đối tượng sau tạo | Giữ tham số hóa ở cả nguồn và converter; xác thực dữ liệu legacy |
| Constructor ghi trường `final` qua đường không nhất quán | Lỗi definite assignment hoặc lỗi logic | Ủy quyền `this(...)` hoặc gán trường đúng một lần trên mỗi đường |
| Record có constructor bổ sung nhưng không gọi `this(...)` | Vi phạm quy tắc non-canonical record constructor | Dùng `this(converted)` |
| Compiler không suy luận được với quá nhiều overload | Các ràng buộc kiểu không xác định hoặc nhập nhằng | Chỉ định kiểu đích rõ, đổi API, thêm type witness nếu phù hợp |

### Đọc một chữ ký không bị nhầm

Với:

```java
class Result<T> {
    <S extends CharSequence> Result(
            S input,
            Function<? super S, ? extends T> transformer) {
        // ...
    }
}
```

Hãy hỏi:

1. **Kiểu lớp là gì?** `T` sau tên `Result<T>`, được xác định bởi `Result<Integer>`, `Result<String>`...
2. **Kiểu riêng của constructor là gì?** `S` trong `<S extends CharSequence>`.
3. **Bound bảo đảm điều gì?** `S` có các hành vi của `CharSequence`.
4. **Nguồn và đích nối nhau ra sao?** `transformer` nhận `S` và trả một giá trị tương thích `T`.
5. **Dữ liệu tồn tại sau khi constructor kết thúc ở kiểu nào?** Trường của đối tượng sẽ mang hợp đồng `T`; tham số `S` chỉ tham gia quá trình tạo.

## 15. Bài tập thực hành

**Bài 1 — Phân loại constructor.** Cho mã:

```java
class Sample<T> {
    Sample(T input) {}
    <U> Sample(U input, java.util.function.Function<U, T> convert) {}
}
```

Hãy chỉ ra constructor nào generic theo định nghĩa khai báo type parameter riêng. Phân biệt `T` của lớp với `U` của constructor.

**Bài 2 — Lớp không generic.** Thiết kế `CsvText` chỉ giữ một `String`. Tạo generic constructor `<S> CsvText(S source, Function<? super S,String> encoder)`. Dùng nó với `Integer` và với một record `Person(String name)`. Kiểm tra kiểu của nguồn được suy luận từng lời gọi.

**Bài 3 — Bound.** Viết `RangeSummary` có `double min` và `double max`. Constructor generic `<N extends Number> RangeSummary(Collection<N> values)` phải kiểm tra collection không rỗng và dùng `doubleValue()` để tính kết quả. Mô tả hợp đồng đối với `NaN` và `null` nếu bạn muốn hỗ trợ dữ liệu dấu phẩy động.

**Bài 4 — Constructor chaining.** Viết `Box<T>` có constructor `Box(T direct)` và constructor `<S> Box(S source, Function<? super S, ? extends T> mapper)`. Sử dụng `this(mapper.apply(source))`, kiểm tra nguồn chuỗi `"123"` và hàm `Integer::parseInt` để tạo `Box<Integer>`. Thử bỏ converter khi nguồn không phù hợp và quan sát thông báo lỗi biên dịch.

**Bài 5 — Chuyển sang factory.** Chuyển `<S> Box(S source, Function<...>)` thành static factory `static <S,T> Box<T> from(S source, Function<? super S,? extends T> mapper)`. So sánh khả năng đọc của lời gọi `Box.from("123", Integer::parseInt)` với lời gọi `new Box<>("123", Integer::parseInt)`.

**Bài 6 — Giải thích hai chữ `String` và `Integer`.** Phân tích:

```java
Holder<Integer> h =
        new <String> Holder<Integer>("Java", String::length);
```

Chữ `String` sau `new` chỉ type argument của **constructor**; chữ `Integer` sau `Holder` chỉ type argument của **lớp**. Giải thích tại sao `h.get()` trả `Integer`.

Sau khi học, hãy tự kiểm chứng bằng cách tìm **nơi khai báo** type parameter: sau tên lớp là kiểu của **đối tượng**, còn ngay trước tên constructor là kiểu **chỉ thuộc lần khởi tạo**. Khi cùng xuất hiện, hai tham số có thể được ràng buộc với nhau bằng converter nhưng vẫn mang phạm vi riêng biệt. Đây là cơ sở để đọc và xây dựng API constructor generic rõ ràng, an toàn kiểu trong Java.

# Kiểu đích của lambda và method reference trong Java 8

## 1. Tổng quan: vì sao cùng một lambda có thể mang nhiều kiểu?

Trong Java, lambda expression và method reference không phải là những giá trị "hàm độc lập" với một kiểu cố định được suy ra chỉ từ nội dung biểu thức. Chúng được **kiểm tra theo kiểu đích** (*target type*): compiler cần biết biểu thức dự kiến được dùng như **functional interface** nào, từ đó biết chữ ký phương thức trừu tượng cần đáp ứng. Cơ chế này được gọi là **target typing** và là một phần quan trọng của **suy luận kiểu** (*type inference*) trong Java 8.

Ví dụ:

```java
java.util.function.Function<String, Integer> length =
        text -> text.length();

java.util.function.ToIntFunction<String> primitiveLength =
        text -> text.length();
```

Hai lambda có cùng phần thân nhưng được kiểm tra theo hai **target type** khác nhau:

- `Function<String,Integer>` yêu cầu SAM `Integer apply(String)`. Giá trị `int` của `length()` được boxing thành `Integer`.
- `ToIntFunction<String>` yêu cầu SAM `int applyAsInt(String)`. Kết quả `int` đi thẳng, không phải boxing để đáp ứng kiểu trả về.

Đây là đoạn **minh họa trong method**, với tên class được viết đủ nên không cần import. Lambda có thể biểu diễn cùng một phép tính dưới các hợp đồng functional interface khác nhau, nếu chữ ký tương thích.

Sau bài này, bạn sẽ có thể:

1. Xác định target type của lambda/method reference trong phép gán, đối số method, return và cast.
2. Hiểu **functional interface**, **SAM descriptor**, parameter type và return compatibility.
3. Phân biệt target typing với kiểu của biểu thức Java thông thường.
4. Hiểu compiler suy luận tham số lambda kiểu ngầm định hay khai báo tường minh.
5. Sử dụng đúng các method reference `Type::staticMethod`, `object::instanceMethod`, `Type::instanceMethod`, `Type::new` và `Type[]::new`.
6. Xử lý overload ambiguity, generic method inference, wildcard và những trường hợp cần làm rõ kiểu đích.
7. Nhận ra các sai lầm như `var x = s -> s`, chọn nhầm reference overload hoặc hiểu sai bản chất compile-time/run-time.
8. Áp dụng các quy tắc **vẫn hiện hành trong Java hiện đại**, không dùng API bị loại bỏ hay kiến thức legacy.

## 2. Functional interface và chữ ký SAM

Target của lambda/method reference thường là một **functional interface**. Functional interface có một phương thức trừu tượng theo quy tắc của Java (*single abstract method*, SAM), dù nó có thể có thêm default method, static method hoặc các abstract declaration tương ứng với public method của `Object` theo quy tắc JLS.

Ví dụ:

```java
@FunctionalInterface
interface Converter<T, R> {
    R convert(T source);

    default R requireResult(T source) {
        R result = convert(source);
        return java.util.Objects.requireNonNull(result);
    }
}
```

Interface này vẫn là functional interface: `convert(T)` là SAM; `requireResult(T)` có phần thân nên không tạo abstract operation thứ hai.

Khi khai báo:

```java
Converter<String, Integer> parse = Integer::parseInt;
```

compiler biết target descriptor là **`Integer convert(String)`**. Nó kiểm tra `Integer::parseInt` có thể cung cấp một callable nhận `String` và trả kết quả chuyển được thành `Integer`. Phương thức `Integer.parseInt(String)` trả `int`; boxing giúp kết quả tương thích.

**Lưu ý:** đoạn code trong mục này là **mảnh khai báo hợp lệ**, không phải chương trình độc lập có `main`. Ví dụ đầy đủ ở mục 7 có thể biên dịch/chạy riêng.

`@FunctionalInterface` giúp compiler báo lỗi khi interface vô tình không còn là functional interface. Annotation **không bắt buộc** để lambda sử dụng một interface có SAM hợp lệ; khi thiết kế API, nên dùng để thể hiện ý định.

## 3. Kiểu đích xuất hiện ở đâu?

Compiler lấy target type từ **ngữ cảnh biểu thức**. Những vị trí thường gặp:

| Ngữ cảnh | Ví dụ | Target type |
| --- | --- | --- |
| Gán cho biến | `Predicate<String> p = s -> s.isEmpty();` | `Predicate<String>` |
| Truyền cho method | `names.forEach(s -> print(s));` | Kiểu tham số `Consumer<? super String>` (và inference liên quan) |
| Trả về từ method | `return text -> text.trim();` trong method trả `UnaryOperator<String>` | `UnaryOperator<String>` |
| Ép kiểu tường minh | `(Runnable) () -> doWork()` | `Runnable` |
| Conditional expression ở poly context | `flag ? (x -> x.trim()) : (x -> x.toUpperCase())` khi gán `UnaryOperator<String>` | `UnaryOperator<String>` cho từng nhánh |
| Khởi tạo phần tử mảng functional interface | `new Runnable[] { () -> task() }` | `Runnable` cho phần tử |

Các ví dụ `print`, `doWork`, `task` là tên method **giả định do ứng dụng tự định nghĩa**; mục đích là minh họa target context chứ không phải chương trình độc lập.

Điểm quan trọng: một target type có thể được hình thành qua **suy luận generic của method chứa nó**, chứ không phải luôn xuất hiện nguyên văn ở ngay bên trái lambda.

### Gán là trường hợp đơn giản nhất

```java
java.util.function.Supplier<String> greeting = () -> "hello";
java.util.function.Predicate<String> blank = String::isEmpty;
java.util.function.Function<String, Integer> count = String::length;
```

- `Supplier<String>`: SAM không có tham số, trả `String`.
- `Predicate<String>`: SAM nhận `String`, trả `boolean`.
- `Function<String,Integer>`: SAM nhận `String`, trả `Integer`.

Nếu viết `var f = x -> x;` trên Java hiện đại, compiler **không thể suy luận target functional interface từ lambda trần**: không có kiểu đích để xác định `x`. `var` được giới thiệu sau Java 8, nhưng quy tắc này vẫn đúng; dùng khai báo kiểu rõ ràng, ví dụ `UnaryOperator<String> f = x -> x;`.

## 4. Lambda: suy luận parameter type và return type

### 4.1. Parameter kiểu ngầm định

```java
java.util.function.Function<String, Integer> f = s -> s.length();
```

Vì target SAM nhận `String`, `s` có kiểu `String`. Compiler xác minh `s.length()` hợp lệ và kết quả có thể chuyển thành `Integer`. Người viết không cần lặp lại tên kiểu parameter.

Với nhiều tham số:

```java
java.util.function.BiFunction<Integer, Integer, Integer> sum =
        (a, b) -> a + b;
```

`a` và `b` được suy luận là `Integer`; phép cộng dùng unboxing rồi boxing kết quả thành `Integer`.

### 4.2. Parameter kiểu tường minh

```java
java.util.function.Function<String, Integer> f =
        (String s) -> s.length();
```

Khai báo tường minh có thể làm ý nghĩa rõ ràng hoặc hỗ trợ lựa chọn overload trong một số trường hợp. Nhưng kiểu đó phải **phù hợp descriptor**. Không thể thay `String` bằng `Object` tùy ý khi target là `Function<String,Integer>` chỉ vì `String` là subtype của `Object`.

Không trộn tham số có kiểu tường minh và ngầm định trong cùng lambda, ví dụ `(String a, b) -> ...` là sai cú pháp. Dùng `(String a, String b)` hoặc `(a, b)`.

### 4.3. Body expression và block

Target SAM quyết định liệu lambda cần tạo giá trị:

```java
java.util.function.Function<Integer, Integer> square = n -> n * n;
java.util.function.Consumer<Integer> show = n -> System.out.println(n);
```

- `Function` cần kết quả, nên `n * n` có thể dùng như expression body trả về giá trị.
- `Consumer` có SAM trả `void`, nên `System.out.println(n)` là statement expression hợp lệ cho void-compatible lambda.

Với block body cần `return` tương thích kiểu đích nếu SAM trả giá trị:

```java
java.util.function.Function<Integer, Integer> squared = n -> {
    int value = n * n;
    return value;
};
```

Đừng hiểu sai rằng mọi biểu thức có giá trị đều dùng được cho mọi target `void`. Quy tắc **void-compatible** của Java áp dụng với **statement expressions** thích hợp, không phải mọi expression. Lambda `() -> 42` không phù hợp với `Runnable.run()` trả `void`, vì literal `42` không phải statement expression.

Tương tự, lambda dùng block có một `return value` không thể gán cho `Consumer` có descriptor `void`.

### 4.4. Exception và descriptor

Một lambda/method reference có thể ném checked exception chỉ khi điều đó tương thích với **throws clause của SAM**. Ví dụ `Runnable.run()` không khai báo checked exception, nên code trong `Runnable` không thể trực tiếp ném `IOException` mà không xử lý.

Đây là giới hạn của **target descriptor**, không phải cú pháp đặc biệt của lambda. Khi cần callback có checked exception, định nghĩa một functional interface với `throws` rõ ràng hoặc xử lý lỗi ở adapter thích hợp; không dùng cast để "né" luật exception.

## 5. Method reference cũng cần target type

Method reference dùng cú pháp `::` và trông như chỉ rõ method đã tồn tại. Tuy nhiên, compiler vẫn cần target functional interface để xác định **đầu vào**, **đầu ra**, overload và binding receiver.

### Bốn dạng chính

| Dạng | Ví dụ | Ví dụ target type | SAM có nghĩa gì? |
| --- | --- | --- | --- |
| Static method | `Integer::parseInt` | `Function<String,Integer>` | `apply(s)` gọi `Integer.parseInt(s)`. |
| Bound instance method | `"hello"::length` | `Supplier<Integer>` | `get()` gọi `length()` trên receiver đã ràng buộc. |
| Unbound instance method | `String::length` | `Function<String,Integer>` | `apply(s)` gọi `s.length()`. |
| Constructor | `User::new` | `Function<String,User>` | `apply(s)` tạo `new User(s)`. |
| Array constructor | `String[]::new` | `IntFunction<String[]>` | `apply(n)` tạo `new String[n]`. |

Với bound reference `"hello"::length`, receiver được xác định khi expression được đánh giá; lời gọi method diễn ra khi SAM thực thi. Với unbound reference `String::length`, receiver chính là một đối số SAM. Không được tự gán `String::length` cho `Supplier<Integer>` vì không có `String` instance nào được cung cấp làm receiver.

### `Type::instanceMethod` không phải static method

Cú pháp `String::length` nhìn giống `Type::staticMethod` nhưng không có nghĩa `length` là static. Compiler kiểm tra các dạng lookup cho phép theo ngữ cảnh và target descriptor: `Function<String,Integer>` diễn đạt rằng **đối số đầu tiên trở thành receiver** của method instance.

Ví dụ:

```java
java.util.function.Function<String, Integer> unbound = String::length;
java.util.function.Supplier<Integer> bound = "Java"::length;

System.out.println(unbound.apply("abc")); // 3
System.out.println(bound.get());          // 4
```

Đây là đoạn code runnable **bên trong một method**. Đừng gọi `unbound.apply(null)` mà mong mặc định trả 0: receiver null gây `NullPointerException` khi thực thi.

### Constructor reference và overload

`User::new` không tự chỉ một constructor cố định. `Supplier<User>`, `Function<String,User>` hoặc `BiFunction<String,Integer,User>` có thể chọn các constructor tương ứng khi class có overload phù hợp và được phép truy cập. Tương tự `ArrayList::new` dưới `Supplier<ArrayList<String>>` chọn constructor không tham số, còn dưới `IntFunction<ArrayList<String>>` có thể chọn constructor nhận `int initialCapacity`. **Capacity không phải size.**

### Method reference có thể tường minh hoặc cần disambiguation

Nếu một class có nhiều method cùng tên, target descriptor được dùng để chọn overload phù hợp. Khi nhiều ứng viên thích hợp không có một lựa chọn duy nhất theo luật Java, compiler báo ambiguous. Lúc đó bạn có thể:

- Gán trước vào biến có functional interface cụ thể.
- Dùng kiểu parameter tường minh trong lambda: `(String s) -> ...`.
- Chuyển sang lambda gọi overload một cách rõ ràng: `s -> Type.method((String) s)` khi thật cần.
- Định nghĩa method có tên nghiệp vụ riêng thay vì overload quá dày.

Không nên sửa bằng unchecked cast hoặc raw type vì làm mất type safety.

## 6. Generic method inference và target typing phối hợp

Với một method generic nhận callback, compiler phải **suy luận cả type parameters của method lẫn target descriptor của lambda/method reference**.

Ví dụ:

```java
static <T, R> java.util.List<R> convert(
        java.util.List<T> values,
        java.util.function.Function<? super T, ? extends R> mapper) {
    return values.stream().map(mapper)
            .collect(java.util.stream.Collectors.toList());
}
```

Đây là method minh họa **phải đặt trong một class**. Khi gọi:

```java
java.util.List<Integer> lengths =
        convert(java.util.Arrays.asList("a", "bb", "ccc"),
                String::length);
```

Compiler ràng buộc `T` với `String`, chọn method reference `String::length` theo target function nhận String, rồi xác định kết quả tương thích với `R = Integer`. Nhờ đó `lengths` có kiểu `List<Integer>` mà không cần cast.

### Vì sao wildcard trong callback giúp suy luận kiểu linh hoạt?

`Function<? super T, ? extends R>` cho phép callback **nhận một kiểu rộng hơn T** và **trả một kiểu hẹp hơn R**. Dòng dữ liệu là:

- Input đi **vào** callback: `? super T`.
- Output đi **ra khỏi** callback: `? extends R`.

Đó là quy tắc PECS áp dụng vào hợp đồng nhận hàm. Nhưng Java generic vẫn **invariant**: `Function<Number,String>` không tự động là subtype của `Function<Integer,String>`. Wildcard ở **vị trí sử dụng** mới cho phép sự tương thích có kiểm soát.

Với một lời gọi generic phức tạp, đôi khi compiler cần thêm ngữ cảnh: một biến nhận kết quả có kiểu cụ thể, type witness như `ClassName.<T,R>method(...)`, hoặc tách pipeline thành các bước đặt tên. Hãy ưu tiên mã rõ hơn thay vì cast không an toàn.

## 7. Chương trình độc lập: kiểm tra target typing trong Java

Tạo tệp **`TargetTypingDemo.java`**. Ví dụ có lambda, static/bound/unbound method reference, constructor/array reference, generic inference và overload disambiguation.

```java
import java.util.Arrays;
import java.util.List;
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.Supplier;
import java.util.function.ToIntFunction;
import java.util.stream.Collectors;

public class TargetTypingDemo {
    static class User {
        private final String name;
        User(String name) { this.name = name; }
        String name() { return name; }
    }

    static <T, R> List<R> convert(
            List<T> values,
            Function<? super T, ? extends R> mapper) {
        return values.stream().map(mapper).collect(Collectors.toList());
    }

    static String select(Function<String, Integer> function) {
        return "boxed:" + function.apply("abcd");
    }
    static String select(ToIntFunction<String> function) {
        return "primitive:" + function.applyAsInt("abcd");
    }

    public static void main(String[] args) {
        Function<String, Integer> length = text -> text.length();
        System.out.println("lambda=" + length.apply("Java"));

        Function<String, Integer> unbound = String::length;
        Supplier<Integer> bound = "hello"::length;
        Function<String, Integer> parsed = Integer::parseInt;
        System.out.println("refs=" + unbound.apply("abc")
                + "," + bound.get() + "," + parsed.apply("42"));

        Function<String, User> create = User::new;
        System.out.println("user=" + create.apply("Mai").name());

        List<Integer> sizes = convert(Arrays.asList("a", "bb", "ccc"),
                String::length);
        System.out.println("sizes=" + sizes);

        System.out.println("overload="
                + select((ToIntFunction<String>) String::length));

        IntFunction<String[]> arrays = String[]::new;
        System.out.println("arrayLength=" + arrays.apply(3).length);

        Supplier<String> choose = () -> "done";
        System.out.println("supplier=" + choose.get());
    }
}
```

Biên dịch và chạy với JDK 17+ (các tính năng trong ví dụ đã khả dụng từ Java 8):

```bash
javac TargetTypingDemo.java
java TargetTypingDemo
```

**Stdout chính xác:**

```text
lambda=4
refs=3,5,42
user=Mai
sizes=[1, 2, 3]
overload=primitive:4
arrayLength=3
supplier=done
```

### Giải thích theo từng dòng output

1. `length` nhận `String` và trả `Integer`; `"Java"` có bốn ký tự nên in `lambda=4`.
2. `unbound` nhận `"abc"` làm receiver để gọi `length()` (3); `bound` có receiver `"hello"` cố định (5); `parsed` gọi static method `Integer.parseInt("42")` (42).
3. `User::new` được chọn theo `Function<String,User>` và gọi constructor `User(String)` khi `apply` thực thi, trả object có tên `Mai`.
4. `convert` nhận `List<String>` và `String::length`, compiler suy luận kiểu đầu ra `Integer`; kết quả `[1,2,3]`.
5. Có **hai overload `select`** nhận `Function<String,Integer>` hoặc `ToIntFunction<String>`. Cast `(ToIntFunction<String>) String::length` dùng **target type cụ thể** để chọn overload trả chuỗi bắt đầu `primitive:`. Đây là cast lên functional interface có kiểu đã biết, **không phải unchecked cast**.
6. `String[]::new` được kiểm tra theo `IntFunction<String[]>`, nhận `int` 3 và tạo mảng có length 3.
7. `Supplier<String>` có SAM `get()` không nhận tham số; lambda trả `"done"`.

Chương trình chỉ dùng API tiêu chuẩn còn được duy trì. Nó cho thấy **target type là một phần của ý nghĩa biểu thức**, không chỉ là thông tin trang trí ở bên trái dấu `=`.

## 8. Overload resolution: khi có nhiều target type phù hợp

Giả sử có hai overload:

```java
static String select(Function<String, Integer> fn) { /* ... */ }
static String select(ToIntFunction<String> fn) { /* ... */ }
```

Đây chỉ là **minh họa chữ ký**; hai thân `/* ... */` thiếu `return` nên không phải code biên dịch độc lập. Chương trình ở mục 7 có định nghĩa chạy được của chúng.

Với lời gọi `select(String::length)`, có khả năng cả hai functional interface đều nhận một String và tạo giá trị length tương ứng (boxed/primitive). Trường hợp có nhiều overload thích hợp có thể dẫn đến **ambiguity** nếu không có overload cụ thể nhất theo luật Java. Để làm ý định rõ ràng:

```java
select((ToIntFunction<String>) String::length);
```

Một lựa chọn khác:

```java
ToIntFunction<String> length = String::length;
select(length);
```

Đây là đoạn minh họa ở trong class có hai overload `select` như chương trình chính.

### Lambda implicit và explicit có thể ảnh hưởng việc chọn overload

Với lambda viết tham số không có kiểu `x -> ...`, compiler cần target type để suy luận `x`. Khi overload có nhiều target type, compiler sẽ xem những phần có thể xác định trong quá trình overload resolution; đôi khi cần loại thông tin bổ sung. Viết parameter type tường minh như `(String x) -> ...` có thể giải quyết một số tình huống, nhưng **không bảo đảm** mọi overload trở nên không nhập nhằng nếu các descriptor vẫn tương tự. Khi đó khai báo biến functional interface cụ thể là cách rõ nhất.

Đừng dựa vào kết quả chọn overload như một chi tiết ngẫu nhiên để triển khai nghiệp vụ. Nếu API có nhiều overload chỉ khác chức năng callback, thiết kế tên method chuyên biệt đôi khi dễ dùng và ít mơ hồ hơn.

### Return type của lambda cũng tham gia kiểm tra tương thích

Một lambda trả giá trị có thể thích hợp với functional interface trả `void` nếu phần thân là **statement expression** hợp lệ, trong khi những biểu thức khác chỉ phù hợp với kiểu trả về không void. Java có những quy tắc chi tiết để phân biệt **void-compatible**, **value-compatible** và trường hợp body block vừa phù hợp cả hai. Vì vậy overload resolution liên quan lambda không chỉ là đếm số tham số.

Nếu gặp lỗi khó hiểu, hãy xem **SAM return type**, kiểu của body expression và dạng block; đổi thành một biến được khai báo với target type mong muốn thường giúp compiler lẫn người đọc.

## 9. Method reference: bound, unbound, static và constructor khác nhau thế nào?

Bảng so sánh cách target type **phân bổ đối số SAM**:

| Cách viết | Functional interface | Lời gọi tương đương về ý tưởng |
| --- | --- | --- |
| `Integer::parseInt` | `Function<String,Integer>` | `s -> Integer.parseInt(s)` |
| `String::length` | `Function<String,Integer>` | `s -> s.length()` |
| `"Java"::length` | `Supplier<Integer>` | `() -> "Java".length()` |
| `User::new` | `Function<String,User>` | `s -> new User(s)` |
| `String[]::new` | `IntFunction<String[]>` | `n -> new String[n]` |

Đối với `Type::instanceMethod`, một target descriptor có thể cung cấp receiver như đối số đầu tiên. Với `someObject::method`, receiver đã được xác định trong expression; SAM chỉ cần các tham số còn lại của method. Sự khác biệt này ảnh hưởng số tham số của functional interface.

**Đặc biệt:** bound method reference có bước **đánh giá receiver expression ngay khi reference được tạo**. Nếu receiver expression là `null`, Java có thể ném `NullPointerException` ngay tại thời điểm tạo bound reference, trước khi gọi SAM. Khi receiver không null, method thực thi khi SAM được gọi. Vì vậy `obj::method` không phải lúc nào cũng hoàn toàn giống `() -> obj.method()` về thời điểm đánh giá tham chiếu `obj`, nhất là khi expression có side effect hoặc có thể null.

Ví dụ minh họa:

```java
String text = "Hi";
Supplier<Integer> lengthNow = text::length;
Supplier<Integer> lengthLater = () -> text.length();
```

Trong tình huống `text` không bị gán lại, cả hai trả 2. Nhưng với receiver expression phức tạp, bound method reference **đánh giá expression receiver khi tạo**, còn lambda `() -> receiverExpression.method()` có thể đánh giá nó lúc thực thi `get()`. Đừng coi mọi phép thay thế là semantics-preserving nếu receiver expression có I/O, mutation hoặc exception.

## 10. Target typing trong conditional expression và return statement

Một lambda có thể được truyền qua những biểu thức lớn hơn mà target type nằm ở ngoài:

```java
static java.util.function.UnaryOperator<String> strategy(boolean upper) {
    return upper ? s -> s.toUpperCase() : s -> s.trim();
}
```

Đây là method **hợp lệ trong class**. Return type `UnaryOperator<String>` là target context của conditional expression, từ đó compiler kiểm tra cả hai nhánh lambda.

Tương tự, phương thức:

```java
static java.util.function.Predicate<String> nonEmpty() {
    return s -> !s.isEmpty();
}
```

dùng kiểu trả về của method làm target type.

Khi callback được truyền vào generic method, target có thể dựa trên sự kết hợp giữa tham số method, kiểu của đối số khác và kiểu nhận kết quả. Không nên cho rằng compiler luôn suy luận từ trái sang phải theo một bước đơn giản; thuật toán suy luận kiểu trong JLS giải các ràng buộc tùy ngữ cảnh.

## 11. Cast tới functional interface và intersection target type

Một cast tường minh đôi khi có ích khi bạn muốn một lambda thuộc một functional interface nhất định:

```java
Runnable task = (Runnable) () -> System.out.println("run");
```

Đoạn trên là code minh họa trong method. Cast `Runnable` cung cấp target type, không biến lambda thành "function object" có kiểu không kiểm tra.

Java cũng cho phép những **intersection type** trong ngữ cảnh cast được quy định, ví dụ:

```java
Runnable serializableTask =
        (Runnable & java.io.Serializable) () -> System.out.println("ok");
```

Ý tưởng: kết quả phải đáp ứng cả `Runnable` và `Serializable`, và intersection đó phải có functional descriptor hợp lệ. Tuy nhiên **không nên dùng serialization của lambda để lưu logic nghiệp vụ dài hạn**: identity/implementation class và dạng serialized representation của lambda không phải hợp đồng bền vững cho việc lưu trữ qua các phiên bản ứng dụng. Khi cần dữ liệu bền, lưu **dữ liệu**, rồi dựng lại hành vi qua API ổn định.

Intersection cast là trường hợp nâng cao; phần lớn code dùng `Function`, `Predicate`, `Consumer`, `Supplier` khai báo rõ đã đủ.

## 12. Những lỗi biên dịch và hiểu nhầm phổ biến

### 12.1. Thiếu target type

```java
// Không biên dịch nếu dùng Java 10+:
// var identity = x -> x;
```

`var` không tự phát minh một functional interface cho lambda. Cách đúng là:

```java
java.util.function.UnaryOperator<String> identity = x -> x;
```

### 12.2. Dùng sai arity của descriptor

```java
// Lỗi nếu mở comment: Runnable.run() không có tham số.
// Runnable invalid = name -> System.out.println(name);
Runnable ok = () -> System.out.println("hello");
```

Các đoạn ví dụ trong method. Một lambda có một parameter không thể thỏa SAM không có parameter.

### 12.3. Sai kiểu trả về

```java
// Lỗi nếu mở comment: Supplier<Integer> phải tạo Integer.
// Supplier<Integer> invalid = () -> "abc";
java.util.function.Supplier<Integer> good = () -> 3;
```

Đừng mong compiler tự đổi `String` sang `Integer`; boxing/unboxing và những conversion hợp lệ **không phải** phép chuyển đổi mọi kiểu.

### 12.4. Nhầm receiver của unbound reference

```java
java.util.function.Function<String, Integer> f = String::length;
// java.util.function.Supplier<Integer> wrong = String::length;
```

Dòng `wrong` sẽ lỗi vì không có String receiver cho instance method; hãy dùng `"literal"::length` hoặc `() -> someString.length()` với instance phù hợp.

### 12.5. Mất target qua raw type hoặc cast không an toàn

Dùng `Function` không type arguments làm mất thông tin generic. Với callback API, hãy giữ type arguments và dùng wildcard theo hướng vào/ra thay vì ép kiểu unchecked. Raw type có thể khiến lỗi xuất hiện muộn ở runtime và làm code khó bảo trì.

### 12.6. Nghĩ `String::length` được gọi khi khai báo

Method reference chỉ chuẩn bị hành vi; method instance thực thi khi SAM được gọi. Với `String[]::new`, mảng được cấp phát khi `IntFunction.apply(n)` chạy. Với constructor reference, object được khởi tạo khi functional method thực thi. Ngoại lệ quan trọng về thời điểm **đánh giá bound receiver expression** đã nêu ở mục 9.

### 12.7. Đoán overload bằng số tham số mà bỏ qua loại

Hai functional interface có cùng arity vẫn có thể khác input/output, boxing, primitive specialization, throws, generic bounds. Xem **toàn bộ functional descriptor** và luật overload resolution thay vì chỉ xem biểu thức lambda nhìn ngắn.

### 12.8. Nhầm captured variable với type inference

Biến local/parameter được lambda dùng từ scope ngoài phải `final` hoặc **effectively final** theo luật Java. Đây là quy tắc **capture**, khác với **target typing**. Dù compiler biết kiểu tham số của lambda, một local variable bị gán lại vẫn không được capture hợp lệ.

```java
String prefix = "ID:";
java.util.function.Function<Integer, String> label =
        n -> prefix + n; // prefix effectively final.
```

Nếu gán lại `prefix` trong cùng scope sau đó, đoạn lambda sẽ không còn hợp lệ. Trạng thái mutable của object do một biến effectively final tham chiếu vẫn là vấn đề khác: type inference không làm object immutable hay thread-safe.

## 13. Cách thiết kế API dễ dùng với lambda/method reference

Một API thuận tiện cho caller nên có **functional interface đích rõ ràng**:

```java
static <T, R> java.util.List<R> transform(
        java.util.List<T> source,
        java.util.function.Function<? super T, ? extends R> mapper) {
    return source.stream().map(mapper)
            .collect(java.util.stream.Collectors.toList());
}
```

Đây là method độc lập về mặt khai báo nhưng **phải nằm trong một class**. Kiểu `Function<? super T, ? extends R>` cho caller dùng callback nhận kiểu rộng hơn hoặc trả kiểu hẹp hơn. Ví dụ `transform(names, String::trim)` hoặc `transform(names, String::length)` làm lộ rõ ý nghĩa của target từ dữ liệu nguồn.

Khuyến nghị:

1. Chọn tên method và type parameters thể hiện rõ input/output. `Function<T,R>` thích hợp khi có kết quả; `Consumer<T>` cho hành động `void`.
2. Tránh overload cùng tên chỉ khác functional interface có cùng arity/loại kết quả gần nhau nếu dễ làm lambda nhập nhằng.
3. Dùng primitive specialization (`ToIntFunction<T>`, `IntPredicate`, `IntUnaryOperator`...) nếu hợp đồng thực sự hướng tới primitive và có lợi ích rõ ràng; các API này vẫn được dùng trong Java hiện đại.
4. Cho phép callback nhận supertype hoặc trả subtype bằng wildcard ở vị trí appropriate; giữ dữ liệu trả về kiểu cụ thể khi có thể.
5. Khi inference khó đọc, khai báo biến callback có kiểu rõ ràng hoặc tách generic call thành bước nhỏ. Điều này giúp cả compiler lẫn người bảo trì.
6. Đừng phụ thuộc identity hoặc class runtime của lambda để xử lý nghiệp vụ. Đây là mô hình callable theo functional interface, không phải tên lớp triển khai bền vững.
7. Tài liệu hóa exception, null, side effects, thread safety và lifecycle của callback **ngoài** những gì generic descriptor bảo đảm.
8. Chạy compile tests với những cách gọi tiêu biểu, đặc biệt khi sửa API hoặc thêm overload; cùng một lambda có thể được phân giải khác do thay đổi tập overload.

## 14. Bài tập tự kiểm tra

**Câu 1.** `Function<String,Integer> f = String::length` hợp lệ không? **Có.** Đầu vào String trở thành receiver, kết quả `int` được boxing thành Integer.

**Câu 2.** `Supplier<Integer> f = String::length` hợp lệ không? **Không.** `String::length` ở dạng unbound cần một receiver String nhưng `Supplier.get()` không nhận tham số.

**Câu 3.** `Supplier<Integer> f = "Java"::length` trả bao nhiêu khi gọi `get()`? **4.** Receiver "Java" đã ràng buộc trong reference.

**Câu 4.** `var f = x -> x` có tự suy ra `Function<Object,Object>` không? **Không.** Lambda cần target functional interface; compiler không chọn một interface tùy ý chỉ từ biểu thức đó.

**Câu 5.** Một method trả `Predicate<String>` có thể `return s -> !s.isEmpty();` không? **Có.** Kiểu trả về method tạo target type.

**Câu 6.** `Function<String,User> f = User::new` gọi constructor ở lúc khai báo không? **Không.** Constructor chạy khi `f.apply(s)` được gọi.

**Câu 7.** Vì sao `select((ToIntFunction<String>) String::length)` giải quyết overload? **Vì cast chỉ rõ functional interface đích**, compiler chọn overload nhận `ToIntFunction<String>`.

**Câu 8.** `String[]::new` có phải gọi constructor của `String` không? **Không.** Nó tạo mảng String[] theo độ dài được cung cấp bởi `IntFunction`.

**Câu 9.** Nếu callback generic nhận `Function<? super T, ? extends R>`, một `Function<Number,String>` dùng được khi `T=Integer`, `R=CharSequence`? **Có.** Nó nhận được Integer như Number và trả String như CharSequence.

**Câu 10.** Vì sao `objectExpression::method` đôi khi khác `() -> objectExpression.method()`? **Vì bound receiver expression được đánh giá khi tạo reference**, còn lambda có thể đánh giá expression đó khi SAM thực thi.

## 15. Tổng kết và tài liệu tham khảo

**Kiểu đích quyết định cách compiler hiểu lambda và method reference**: SAM descriptor xác định số, kiểu tham số, kiểu trả về và giới hạn exception; generic inference, overload resolution và wildcard có thể tham gia để xác định descriptor phù hợp. Với method reference, target type còn quyết định sự khác nhau giữa static, bound/unbound instance và constructor reference.

Một quy trình debug đơn giản:

1. Xác định biểu thức đang xuất hiện trong **ngữ cảnh nào** (gán, truyền đối số, return, cast, conditional).
2. Viết rõ target functional interface và **chữ ký SAM**.
3. So sánh parameter count/types, return conversion và checked exceptions.
4. Với method reference, xác định receiver lấy từ đâu, có overload không.
5. Nếu generic inference hoặc overload mơ hồ, thử khai báo biến functional interface cụ thể hay viết lambda tường minh để làm rõ.
6. Biên dịch ví dụ nhỏ để kiểm chứng thay vì dùng raw type/cast không an toàn.

Những quy tắc trên **vẫn còn áp dụng trên Java hiện đại**, đặc biệt trong Stream, callback API, method reference và generic library code.

Nguồn chính thức để tra cứu khi cần kiểm tra trường hợp nâng cao:

- [Java Language Specification §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27).
- [JLS §15.13 — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.13).
- [JLS §15.12 — Method Invocation Expressions (overload resolution)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12).
- [JLS §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se25/html/jls-18.html).
- [java.util.function package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/package-summary.html).

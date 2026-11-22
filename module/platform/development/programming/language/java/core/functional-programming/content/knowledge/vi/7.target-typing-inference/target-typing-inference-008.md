# Dùng kiểu tham số hoặc ép kiểu tường minh để giải quyết suy luận kiểu của lambda trong Java

## 1. Vấn đề: vì sao lambda đôi khi cần thêm thông tin kiểu?

Lambda trong Java có dạng `(tham số) -> thân`. Nó **không có kiểu độc lập hoàn chỉnh** như một đối tượng `Function` hay `Predicate` cho đến khi được đặt vào một ngữ cảnh có **kiểu đích** (*target type*). Java sử dụng kiểu đích để xác định functional interface, kiểu tham số và kiểu trả về của phương thức trừu tượng duy nhất (SAM) mà lambda phải triển khai.

Ở trường hợp đơn giản:

~~~java
Function<String, Integer> length = text -> text.length();
~~~

Compiler biết `text` là `String` vì kiểu đích `Function<String,Integer>` có SAM `Integer apply(String)`. Nhưng khi kiểu đích không đủ rõ, có nhiều phương thức overload hợp lệ, hoặc các ràng buộc generic không thể thống nhất, có thể gặp lỗi suy luận.

**Hai công cụ trực tiếp của bài học:**

1. **Khai báo kiểu tham số lambda tường minh**, ví dụ `(String text) -> text.length()`. Việc này cho trình biên dịch một ràng buộc về kiểu đầu vào; đặc biệt hữu ích khi các overload có kiểu tham số SAM khác nhau.
2. **Ép kiểu lambda hoặc method reference sang một functional interface cụ thể**, ví dụ `(Predicate<String>) (text -> !text.isBlank())`. Cast cung cấp kiểu đích rõ ràng cho toàn biểu thức, giúp chọn overload khi các interface cùng có thể nhận lambda.

Ngoài ra, có thể cung cấp kiểu cho biến đích, truyền **type witness** cho lời gọi phương thức generic, hoặc tách biểu thức thành biến trung gian có kiểu. Mục tiêu là làm rõ **ý định API**, không ép trình biên dịch chấp nhận một phép chuyển kiểu sai.

Sau bài này, bạn cần đọc được thông báo lỗi suy luận, phân biệt kiểu tham số lambda với kiểu đích functional interface, giải quyết overload bằng đúng cách, và biết khi nào nên thiết kế lại API thay vì chồng thêm cast.

Các ví dụ chạy độc lập sử dụng **Java 17+**.

## 2. Ôn tập: kiểu đích, SAM và suy luận

Một lambda chỉ tương thích với functional interface có đúng một phương thức trừu tượng theo quy tắc SAM của Java. Một số kiểu thường dùng thuộc `java.util.function`:

| Kiểu đích | SAM khái quát | Ý nghĩa |
| --- | --- | --- |
| `Function<T,R>` | `R apply(T value)` | Biến đổi dữ liệu |
| `Predicate<T>` | `boolean test(T value)` | Kiểm tra điều kiện |
| `Consumer<T>` | `void accept(T value)` | Thực hiện hành động |
| `Supplier<T>` | `T get()` | Tạo/cung cấp giá trị |
| `BiFunction<T,U,R>` | `R apply(T a, U b)` | Biến đổi hai đầu vào |
| `Comparator<T>` | `int compare(T a, T b)` | So sánh hai giá trị |

Ví dụ:

~~~java
Predicate<String> notBlank = text -> !text.isBlank();
Function<String, Integer> length = text -> text.length();
Consumer<String> print = text -> System.out.println(text);
Supplier<String> hello = () -> "Xin chào";
~~~

Đây là các khai báo **bên trong phương thức** với import phù hợp. `text` được suy luận từ SAM tương ứng, còn kiểu trả về/kiểu thân lambda phải thỏa hợp đồng SAM. Việc hai lambda có cùng tên tham số hoặc biểu thức tương tự không làm chúng cùng kiểu.

### 2.1. Những ngữ cảnh cung cấp kiểu đích

Kiểu đích có thể xuất hiện qua:

- **Khai báo hoặc gán:** `Function<String,Integer> f = s -> s.length();`.
- **Đối số phương thức:** `list.removeIf(s -> s.isBlank())`, khi chữ ký `removeIf(Predicate<? super E>)` cung cấp ngữ cảnh.
- **Giá trị trả về:** một phương thức khai báo trả `Predicate<String>` có thể `return s -> s.startsWith("A");`.
- **Cast:** `(Predicate<String>) (s -> s.isEmpty())`.
- **Biểu thức điều kiện phù hợp:** ngữ cảnh bao ngoài có thể cung cấp target type cho các nhánh `?:` theo quy tắc poly expression.

Ngược lại:

~~~java
// Không biên dịch: thiếu target type cho lambda.
var f = s -> s.length();
~~~

`var` cần suy luận kiểu từ initializer, nhưng một lambda không có target type độc lập để suy ra kiểu functional interface. Thay bằng `Function<String,Integer> f = s -> s.length();` hoặc cung cấp cast có kiểu cụ thể trước khi gán cho `var`.

### 2.2. Một lambda không mặc định là một `Function`

Ví dụ `s -> s.isEmpty()` có thể dùng cho `Predicate<String>` hoặc `Function<String,Boolean>`: cả hai có một tham số `String` và một phép kiểm tra boolean tương thích (ở `Function` kết quả `boolean` được boxing thành `Boolean`). Java không tự động chọn interface theo tên "có vẻ hợp lý". Khi lời gọi overload chấp nhận cả hai, compiler có thể phải báo **ambiguous**.

## 3. Cách 1 — Khai báo kiểu tham số lambda tường minh

### 3.1. Từ suy luận ngầm sang kiểu rõ ràng

Hai khai báo sau đều hợp lệ, nếu đặt độc lập:

~~~java
Function<String, Integer> implicit = text -> text.length();
Function<String, Integer> explicit = (String text) -> text.length();
~~~

Dạng `(String text)` cung cấp kiểu tham số trực tiếp. Khi lambda có một tham số, **dạng khai báo kiểu tường minh cần ngoặc tròn**; `String text -> ...` không hợp lệ.

Ví dụ hai tham số:

~~~java
BiFunction<Integer, Integer, Integer> add =
        (Integer left, Integer right) -> left + right;
~~~

Đây là khai báo với import `java.util.function.BiFunction`. Dạng suy luận ngầm có thể viết `(left, right) -> left + right` nếu target type đã đủ rõ. Dù khai báo kiểu tường minh, compiler vẫn phải kiểm tra chúng tương thích với tham số SAM và kiểu trả về.

### 3.2. Giải quyết overload khác kiểu tham số

Giả sử có hai functional interface:

~~~java
@FunctionalInterface
interface StringCheck {
    boolean check(String value);
}

@FunctionalInterface
interface IntegerCheck {
    boolean check(Integer value);
}
~~~

Và hai overload:

~~~java
static String choose(StringCheck rule) {
    return "string:" + rule.check("Java");
}

static String choose(IntegerCheck rule) {
    return "integer:" + rule.check(4);
}
~~~

Các khối trên là **mảnh mã của cùng một class**. Lời gọi `choose(x -> ...)` có thể khó xác định nếu thân không đủ thông tin, đặc biệt với biểu thức dùng được cho nhiều kiểu.

Khi chủ đích là xử lý chuỗi:

~~~java
String result = choose((String s) -> s.length() >= 4);
~~~

Khi chủ đích là xử lý số:

~~~java
String result = choose((Integer n) -> n % 2 == 0);
~~~

Compiler thấy kiểu tham số lambda `String` hoặc `Integer` và chọn overload có SAM tương thích. Ví dụ đầy đủ ở phần 7 chứng minh cả hai lời gọi.

**Giới hạn:** nếu hai overload đều nhận SAM có cùng kiểu đầu vào, việc viết rõ `(String s)` **không tự giải quyết** mơ hồ. Khi đó cần kiểu đích của toàn bộ lambda hoặc một thiết kế overload khác.

### 3.3. Quy tắc không trộn kiểu tham số

Trong một lambda nhiều tham số, không được vừa để compiler suy luận một tham số vừa khai báo kiểu tường minh cho tham số khác:

~~~java
// Không hợp lệ: trộn explicit và implicit parameter type.
BiFunction<String, String, String> combine =
        (String a, b) -> a + b;
~~~

Cách hợp lệ:

~~~java
BiFunction<String, String, String> explicit =
        (String a, String b) -> a + b;

BiFunction<String, String, String> inferred =
        (a, b) -> a + b;
~~~

Từ **Java 11**, có thể dùng `var` cho **tất cả** tham số lambda:

~~~java
BiFunction<String, String, String> withVar =
        (var a, var b) -> a + b;
~~~

`var` ở đây vẫn dựa vào target type, không có nghĩa là compiler tự tìm functional interface bất kỳ. Không trộn `var` với kiểu tường minh hoặc tham số không ghi kiểu trong cùng danh sách; ví dụ `(var a, b) -> ...` và `(var a, String b) -> ...` đều không hợp lệ.

### 3.4. Explicit type phải chính xác theo SAM

Không thể ép kiểu tham số thành một subtype tùy ý nếu functional interface mong kiểu khác:

~~~java
// Không hợp lệ: Function<Number,Integer> nhận Number, không phải Integer.
Function<Number, Integer> wrong =
        (Integer number) -> number.intValue();
~~~

Đây không phải phép **override có tham số hiệp biến**: lambda phải phù hợp kiểu tham số của SAM. Sửa:

~~~java
Function<Number, Integer> right =
        (Number number) -> number.intValue();
~~~

Hoặc đổi hẳn target type thành `Function<Integer,Integer>` nếu yêu cầu xử lý `Integer`.

## 4. Cách 2 — Cast toàn bộ lambda sang functional interface mong muốn

### 4.1. Đặt kiểu đích cho biểu thức lambda

Cú pháp thường rõ nhất:

~~~java
Predicate<String> rule =
        (Predicate<String>) (s -> !s.isBlank());
~~~

Thực tế, khi biến bên trái đã khai báo `Predicate<String>`, cast này **thường không cần**. Nhưng trong lời gọi overload hoặc ngữ cảnh không có target type duy nhất, cast trở thành cách chỉ rõ ý định.

Ví dụ overload:

~~~java
static String evaluate(Predicate<String> rule) {
    return "predicate:" + rule.test("Java");
}

static String evaluate(Function<String, Boolean> rule) {
    return "function:" + rule.apply("Java");
}
~~~

Lời gọi sau có thể **mơ hồ**:

~~~java
// Không biên dịch: hai overload đều chấp nhận lambda này.
String result = evaluate(s -> s.startsWith("J"));
~~~

Ngay cả `evaluate((String s) -> s.startsWith("J"))` cũng không đủ, vì **cả hai SAM đều nhận `String`**. Dùng cast để cung cấp target type của toàn biểu thức:

~~~java
String a = evaluate(
        (Predicate<String>) (s -> s.startsWith("J")));

String b = evaluate(
        (Function<String, Boolean>) (s -> s.startsWith("J")));
~~~

Bản `a` chọn overload `Predicate`, bản `b` chọn overload `Function`. Chú ý cast tạo kiểu đích **trong lúc lambda được kiểm tra**; nó không "chuyển" một đối tượng Function đã được tạo sang Predicate bất kỳ.

### 4.2. Vì sao cast khác khai báo kiểu tham số?

- `(String s) -> ...` mô tả **kiểu đầu vào của SAM**, nhưng chưa chắc xác định **đó là interface nào**.
- `(Predicate<String>) (s -> ...)` xác định **toàn bộ functional interface**, bao gồm chữ ký SAM và hợp đồng trả về.
- Cast hợp lệ chỉ khi lambda có thể triển khai SAM được chỉ định. Compiler vẫn kiểm tra số tham số, kiểu trả về, exception và các quy tắc ngôn ngữ.

Ví dụ không hợp lệ:

~~~java
// Không hợp lệ: Predicate.test phải trả boolean.
Predicate<String> invalid =
        (Predicate<String>) (s -> s.length());
~~~

Cast không biến giá trị `int` thành `boolean`. Cần thân như `s -> s.length() > 3`.

### 4.3. Cast giúp `var` có initializer có kiểu

~~~java
var longName =
        (Predicate<String>) (s -> s.length() > 4);
boolean value = longName.test("Java"); // false
~~~

`var` nhận kiểu từ **biểu thức cast**, là `Predicate<String>`. Điều này khác với `var longName = s -> ...` bị thiếu target type. Tuy nhiên, trong code thông thường, `Predicate<String> longName = s -> ...` thường ngắn, đơn giản và dễ đọc hơn.

### 4.4. Không nhầm cast lambda với cast đối tượng đã tạo

Có khác biệt giữa:

~~~java
Predicate<String> p =
        (Predicate<String>) (s -> !s.isBlank());
~~~

và ý định không hợp lệ sau:

~~~java
Function<String, Boolean> f = s -> !s.isBlank();
// Không nên coi f là Predicate: hai interface độc lập.
Predicate<String> p = (Predicate<String>) f;
~~~

Ở đoạn thứ hai, compiler có thể chấp nhận một số kiểu cast tham chiếu tùy quan hệ kiểu, nhưng một đối tượng chỉ triển khai `Function` không tự triển khai `Predicate`; phép ép kiểu có thể ném `ClassCastException`. Cách đúng là **tạo adapter**:

~~~java
Function<String, Boolean> f = s -> !s.isBlank();
Predicate<String> p = f::apply;
~~~

`p` là một lambda/method reference mới có SAM của `Predicate`, gọi lại hành vi của `f` và nhận kết quả boolean qua unboxing phù hợp. Nếu `f.apply` có thể trả `null`, adapter có nguy cơ `NullPointerException` khi unboxing; cần xác định hợp đồng dữ liệu.

## 5. Cách 3 — Khai báo biến trung gian có kiểu rõ ràng

Cast nội tuyến không phải lựa chọn duy nhất. Nếu overload phức tạp, chia biểu thức thành hai câu lệnh giúp compiler và người đọc xác định trách nhiệm:

~~~java
Predicate<String> validName = name -> name.startsWith("J");
String result = evaluate(validName);
~~~

Compiler chọn overload `evaluate(Predicate<String>)` nhờ **kiểu tĩnh của biến `validName`**. Cách này đặc biệt phù hợp khi logic được tái sử dụng hoặc cần đặt breakpoint, đặt tên nghiệp vụ.

Nếu dùng method reference cũng tương tự:

~~~java
Function<String, Integer> length = String::length;
Integer n = length.apply("Java"); // 4
~~~

Không nên đưa cast vào mọi lambda theo thói quen. Ưu tiên đặt **kiểu đích rõ ràng ở chữ ký API hoặc biến** trước; dùng cast khi biểu thức vẫn mơ hồ và cast thể hiện rõ ý định.

### 5.1. Explicit type arguments cho phương thức generic

Đôi khi vấn đề không nằm ở overload mà ở **tham số kiểu của phương thức generic**:

~~~java
static <T> String convert(T value, Function<T, String> mapper) {
    return mapper.apply(value);
}
~~~

Cách gọi thường tự suy luận được `T` từ `value` và `mapper`:

~~~java
String result = convert("java", s -> s.toUpperCase());
~~~

Khi cần ép compiler xét một `T` cụ thể, Java hỗ trợ **type witness** trên phương thức generic:

~~~java
String result = MyClass.<String>convert(
        "java", s -> s.toUpperCase());
~~~

Đây là **mảnh mã**: `MyClass` tượng trưng cho class thật sự định nghĩa static method `convert`. Ví dụ đầy đủ sử dụng `LambdaInferenceDemo.<String>convert(...)`.

Type witness điều chỉnh **tham số kiểu generic của phương thức**, không phải ép bừa một `Object` thành `String` và không phải phương thức giải quyết mọi overload mơ hồ. Compiler vẫn kiểm tra tính tương thích của đối số.

### 5.2. Explicit type arguments của generic factory

Ví dụ:

~~~java
Function<String, String> identity = Function.identity();
~~~

Đây là lời gọi static generic method `Function.identity()`; compiler có thể suy luận `T=String` từ biến đích. Có thể khai báo tường minh:

~~~java
Function<String, String> identity =
        Function.<String>identity();
~~~

Cách tường minh có ích khi một lời gọi lồng nhau có nhiều ràng buộc generic khiến thông điệp lỗi khó đọc. Nó không đồng nghĩa casting và không phải luôn cần thiết.

### 5.3. Vì sao `<?>` và raw type làm suy luận khó hơn?

Khi dùng `Function<?,?>` hoặc raw `Function`, thông tin về tham số/đầu ra đã bị che hoặc mất, nên bạn có thể không gọi `apply` với kiểu dữ liệu mong muốn, hoặc bị cảnh báo unchecked. Trong API nhận lambda, hãy truyền kiểu generic cụ thể và dùng wildcard có chủ đích (`? extends T`, `? super T`) theo chiều đọc/ghi phù hợp.

Ví dụ khai báo `Function<String,Integer>` làm rõ đầu vào/đầu ra hơn raw `Function`. Đừng chữa lỗi suy luận bằng cách chuyển hết về `Object` hoặc raw type: chương trình có thể mất type safety và chỉ báo lỗi khi chạy.

## 6. Bảng chọn giải pháp theo dấu hiệu lỗi

| Triệu chứng | Nguyên nhân thường gặp | Cách giải quyết phù hợp |
| --- | --- | --- |
| `var f = x -> ...` không biên dịch | Lambda chưa có target type | Khai báo `Function<T,R>` / `Predicate<T>`, hoặc cast toàn lambda |
| Overload có SAM nhận tham số khác kiểu | Kiểu đầu vào của lambda chưa đủ rõ | Ghi tường minh `(String s)` / `(Integer n)` |
| Overload có SAM cùng kiểu tham số | Ghi kiểu tham số vẫn khớp nhiều interface | Cast toàn lambda hoặc dùng biến functional interface có kiểu |
| Method reference mơ hồ | Nhiều chữ ký/overload phù hợp | Gán cho biến đích cụ thể, dùng lambda có kiểu hoặc cast phù hợp |
| Compiler không suy luận được tham số generic method | Thiếu hoặc xung đột ràng buộc `T` | Làm rõ biến đích, lambda, hoặc dùng `ClassName.<Type>method(...)` |
| Cast vẫn báo lỗi incompatible types | Lambda không phù hợp SAM đã chỉ định | Sửa tham số, kiểu trả về, checked exception; không dùng raw cast |
| Hai overload trả kiểu khác nhưng cùng nhận lambda | Không thể dựa vào ý định người gọi để chọn | Cung cấp kiểu đích/biến hoặc thiết kế lại overload |
| Sau cast đối tượng có `ClassCastException` | Đối tượng thật không triển khai interface đích | Tạo adapter lambda/method reference, đừng cast đối tượng tùy tiện |

**Quy trình chẩn đoán:**

1. Xác định **điểm tạo lambda/method reference** và các overload có thể được gọi.
2. Đọc chữ ký SAM của từng functional interface (kiểu tham số, kiểu trả về, checked exception).
3. Xem có thiếu **target type** không; thử khai báo biến trung gian với đúng functional interface.
4. Nếu các overload khác **kiểu tham số**, thử ghi kiểu tham số lambda tường minh.
5. Nếu vẫn có nhiều interface phù hợp, cast **toàn bộ lambda** hoặc method reference sang interface cần chọn; xác minh đây là ý định nghiệp vụ.
6. Nếu lỗi thuộc **generic inference**, xem lại kiểu generic của phương thức và đưa type witness khi cần.
7. Biên dịch và kiểm thử trên dữ liệu cụ thể. Nếu yêu cầu nhiều cast khó hiểu, cân nhắc đặt tên phương thức khác nhau hoặc đơn giản hóa overload.

## 7. Ví dụ Java 17 hoàn chỉnh: ba cách làm rõ suy luận

Tạo tệp **`LambdaInferenceDemo.java`**:

~~~java
import java.util.Locale;
import java.util.function.Function;
import java.util.function.Predicate;

public class LambdaInferenceDemo {

    @FunctionalInterface
    interface StringCheck {
        boolean check(String value);
    }

    @FunctionalInterface
    interface IntegerCheck {
        boolean check(Integer value);
    }

    // Hai overload khác kiểu tham số SAM.
    static String choose(StringCheck rule) {
        return "string:" + rule.check("Java");
    }

    static String choose(IntegerCheck rule) {
        return "integer:" + rule.check(4);
    }

    // Hai overload có SAM cùng đầu vào String.
    static String evaluate(Predicate<String> rule) {
        return "predicate:" + rule.test("Java");
    }

    static String evaluate(Function<String, Boolean> rule) {
        return "function:" + rule.apply("Java");
    }

    static <T> String convert(T value, Function<T, String> mapper) {
        return mapper.apply(value);
    }

    public static void main(String[] args) {
        // Cách 1: kiểu tham số lambda rõ ràng.
        System.out.println(
                choose((String s) -> s.length() >= 4));
        System.out.println(
                choose((Integer n) -> n % 2 == 0));

        // Cách 2: cast toàn lambda để chọn đúng overload.
        System.out.println(
                evaluate((Predicate<String>)
                        (s -> s.startsWith("J"))));
        System.out.println(
                evaluate((Function<String, Boolean>)
                        (s -> s.startsWith("J"))));

        // Kiểu biến đích cũng cung cấp đầy đủ target type.
        Function<String, Integer> length =
                (String s) -> s.length();
        System.out.println(length.apply("lambda"));

        // Cách 3: type witness cho generic method.
        System.out.println(
                LambdaInferenceDemo.<String>convert(
                        "java", s -> s.toUpperCase(Locale.ROOT)));

        // Cast giúp dùng var vì initializer có kiểu rõ ràng.
        var longerThanTwo =
                (Predicate<String>) (s -> s.length() > 2);
        System.out.println(longerThanTwo.test("Go"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 LambdaInferenceDemo.java
java LambdaInferenceDemo
~~~

**Stdout chính xác:**

~~~text
string:true
integer:true
predicate:true
function:true
6
JAVA
false
~~~

Giải thích theo thứ tự:

1. `choose((String s) -> ...)` chỉ phù hợp `StringCheck`; `"Java"` có 4 ký tự nên trả `string:true`.
2. `choose((Integer n) -> ...)` phù hợp `IntegerCheck`; `4` chia hết cho 2 nên trả `integer:true`.
3. Cast `Predicate<String>` làm Java chọn `evaluate(Predicate<String>)`; chữ `"Java"` bắt đầu bằng `"J"` nên trả `predicate:true`.
4. Cast `Function<String,Boolean>` chọn overload tương ứng; kết quả boolean được boxing phù hợp `Boolean` nên trả `function:true`.
5. `length.apply("lambda")` bằng 6.
6. `<String>convert(...)` cố định `T=String` trong lời gọi generic; `toUpperCase(Locale.ROOT)` trả `"JAVA"`.
7. `var` suy ra `Predicate<String>` từ cast; `"Go"` dài 2 ký tự, nên trả `false`.

Chương trình minh họa tách hai tình huống quan trọng: **kiểu tham số** giúp phân biệt overload khác input; **kiểu đích cast** giúp phân biệt hai functional interface cùng input. Type witness là cơ chế khác, giải quyết tham số generic khi cần.

## 8. Những trường hợp cần cảnh giác

### 8.1. Không cho rằng explicit parameter type luôn giải quyết được overload

Đoạn này vẫn mơ hồ khi có hai overload `evaluate` như phần 7:

~~~java
// Không biên dịch: cả Predicate<String> và Function<String,Boolean>
// đều có thể nhận lambda với tham số String và kết quả boolean.
evaluate((String s) -> s.startsWith("J"));
~~~

Sửa bằng cast `(Predicate<String>) (s -> ...)`, tạo biến `Predicate<String>`, hoặc đổi tên API để chỉ rõ ý định.

### 8.2. Cast không sửa sai chữ ký

~~~java
// Lỗi: Consumer.accept trả void; block lại return một giá trị.
Consumer<String> bad =
        (Consumer<String>) (s -> { return s.length(); });
~~~

Muốn trả độ dài, chọn `Function<String,Integer>`; muốn in độ dài, dùng `Consumer<String> printer = s -> System.out.println(s.length());`. Cast không thay đổi quy tắc kiểu trả về của SAM.

### 8.3. Method reference cũng cần target type

~~~java
Function<String, Integer> length = String::length;
Predicate<String> empty = String::isEmpty;
~~~

Các method reference trên có chữ ký phù hợp nhờ kiểu đích. Nếu truyền một method reference vào nhiều overload cùng phù hợp, cần cung cấp kiểu đích (biến trung gian hoặc cast) để tránh mơ hồ; việc thay bằng lambda không luôn giải quyết nếu các interface vẫn có cùng chữ ký đầu vào/đầu ra.

### 8.4. Generic inference phụ thuộc cả ngữ cảnh

Phương thức generic sử dụng một hoặc nhiều tham số kiểu có thể được suy luận từ đối số và ngữ cảnh sử dụng. Cung cấp type witness giúp rõ ràng nhưng cũng có thể làm lộ sự không tương thích:

~~~java
// Không hợp lệ: yêu cầu T=String nhưng truyền số nguyên.
LambdaInferenceDemo.<String>convert(
        123, s -> s.toUpperCase());
~~~

Đừng thêm cast cưỡng ép để hợp thức hóa dữ liệu không đúng hợp đồng. Hãy sửa kiểu đối số, generic constraint hoặc lựa chọn đúng overload.

### 8.5. Boxing, primitive và overload

`Predicate<Integer>` dùng một `Integer` được unboxing nếu thân viết `n > 0`. `IntPredicate` nhận `int` nguyên thủy, khác kiểu SAM và có thể khác lựa chọn overload. Nếu mã chạy nhiều phép toán số nguyên, dùng biến đích `IntPredicate` khi hợp lý; không dựa vào boxing/unboxing để suy ra overload sẽ được chọn như mong muốn.

Ví dụ:

~~~java
java.util.function.IntPredicate positive = n -> n > 0;
System.out.println(positive.test(3)); // true
~~~

Đây là mảnh mã nằm trong phương thức, không phải chương trình độc lập.

### 8.6. Checked exception và kiểu đích

Lambda chỉ được ném checked exception theo hợp đồng SAM. Việc ghi tường minh `(String s)` hay cast sang `Function<String,String>` không cho phép tùy ý ném `IOException`. Nếu gọi API có checked exception, cần bắt/đóng gói hợp lý hoặc chọn functional interface khác có khai báo throws phù hợp. Nếu compiler báo "unreported exception", đó là vấn đề **hợp đồng exception**, không nên chữa bằng ép kiểu mù quáng.

### 8.7. Cast sang kiểu phù hợp chứ không dùng raw type

Tránh:

~~~java
// Không nên: raw type làm mất thông tin generic.
Function raw = value -> value;
~~~

`raw` khiến tham số và kết quả trở thành `Object` về mặt kiểu tĩnh, dễ dẫn đến unchecked operations hoặc ép kiểu rủi ro khi sử dụng. Thay bằng `Function<String,String>` hay một kiểu cụ thể phù hợp. Chỉ dùng wildcard khi có chủ đích API và hiểu giới hạn sử dụng.

## 9. Thiết kế API để giảm lỗi suy luận

Một API có quá nhiều overload chỉ khác functional interface đôi khi khiến người gọi phải cast liên tục. Ví dụ:

~~~java
static void handle(Predicate<String> p) { /* ... */ }
static void handle(Function<String, Boolean> f) { /* ... */ }
~~~

Hai overload cùng nhận một giá trị `String` và tạo kết quả boolean tương thích, khiến nhiều lời gọi lambda có thể mơ hồ. Việc đổi tên thành `filterWith(Predicate<String>)` và `mapWith(Function<String,Boolean>)` nếu đúng nghiệp vụ sẽ giúp code phía gọi rõ hơn.

Khi không có quyền thay API thư viện, hãy đặt kiểu ở **biến trung gian**:

~~~java
Predicate<String> active = s -> s.startsWith("A");
handle(active);
~~~

Đoạn này chỉ minh họa trong ngữ cảnh có overload `handle` nói trên. Compiler chọn theo kiểu `Predicate<String>` của biến. Các team có thể thống nhất cách đặt tên `isValid`, `toLabel` hoặc `onEvent` để thể hiện loại hành động và kiểu trả về.

Không thêm cast vào tất cả lambda để "an toàn": cast thừa che giấu chỗ API đã rõ ràng và có thể làm khó bảo trì. Ngược lại, một cast cần thiết ở ranh giới overload đôi khi là cách ngắn nhất để nói rõ ý định.

## 10. Bài tập thực hành

**Bài 1 — Thêm kiểu tham số.** Có hai overload `choose(StringCheck)` và `choose(IntegerCheck)` như chương trình phần 7. Viết lambda kiểm tra chuỗi dài ít nhất 5 ký tự; sau đó kiểm tra số chẵn. Hãy ghi `(String s)` và `(Integer n)` để chọn đúng overload.

**Bài 2 — Sửa overload mơ hồ.** Với hai overload `evaluate(Predicate<String>)` và `evaluate(Function<String,Boolean>)`, thử `evaluate(s -> s.isEmpty())`. Sau đó viết hai lời gọi có cast riêng; giải thích vì sao chỉ thêm `(String s)` không đủ.

**Bài 3 — Bỏ `var` thiếu ngữ cảnh.** Sửa đoạn lỗi `var length = s -> s.length();` bằng hai cách: (a) `Function<String,Integer> length = s -> s.length();`; (b) `var length = (Function<String,Integer>) (s -> s.length());`. Chọn cách dễ đọc hơn cho code dự án.

**Bài 4 — Generic type witness.** Với `static <T> T echo(T value) { return value; }`, thử gọi `echo("Java")` và `MyClass.<String>echo("Java")` trong class tương ứng; giải thích type witness tác động lên tham số kiểu generic của phương thức, không phải biến lambda.

**Bài 5 — Không ép sai SAM.** Thử cung cấp `(String s) -> s.length()` cho `Predicate<String>`. Quan sát lỗi kiểu trả về và sửa thành `s -> s.length() > 0`. Giải thích vì sao cast `(Predicate<String>)` không thể đổi `int` thành `boolean`.

**Bài 6 — Method reference.** Gán `String::length` cho `Function<String,Integer>`, gán `String::isBlank` cho `Predicate<String>`. Sau đó thử đưa vào API có overload tương ứng và sử dụng biến trung gian để chọn overload đúng.

**Bài 7 — Refactor API.** Cho hai phương thức `process(Predicate<String>)` và `process(Function<String,Boolean>)`. Đề xuất tên phương thức phân biệt mục đích lọc dữ liệu và chuyển đổi giá trị. So sánh code phía gọi trước và sau khi đổi API.

## 11. Câu hỏi tự kiểm tra

1. **Vì sao `var f = x -> x + 1` không hợp lệ?** Vì lambda cần target type, còn `var` không có thông tin đủ để xác định functional interface chỉ từ lambda.
2. **Khai báo `(String s)` xác định được gì?** Kiểu tham số lambda; compiler vẫn cần xác định SAM/functional interface của toàn biểu thức.
3. **Khi nào cast toàn bộ lambda cần thiết?** Khi nhiều functional interface vẫn cùng phù hợp, thường do overload mơ hồ.
4. **`(Predicate<String>) (s -> ...)` có phải cast một `Function` đã tạo không?** Không. Đó là cast expression dùng để cung cấp target type ngay khi lambda được kiểm tra.
5. **Type witness `Class.<String>method(...)` giúp gì?** Chỉ rõ tham số kiểu của generic method; compiler vẫn kiểm tra các đối số.
6. **Có thể trộn `(String a, b)` trong lambda không?** Không. Các tham số phải nhất quán về dạng khai báo.
7. **Có thể dùng `(var a, var b)` không?** Có từ Java 11 nếu target type rõ ràng; không dùng `var` để tự tạo target type từ hư vô.
8. **Cast có thể đổi lambda trả `int` thành `Predicate` trả `boolean` không?** Không. Chữ ký SAM vẫn phải tương thích.
9. **Vì sao một biến trung gian giúp overload rõ hơn?** Vì kiểu tĩnh được khai báo của biến lựa chọn một interface cụ thể.
10. **Khi nào nên thay đổi thiết kế API?** Khi nhiều overload tương tự khiến người gọi cast lặp lại và khó phân biệt ý nghĩa.

## 12. Ghi nhớ và nguồn tra cứu

**Khai báo kiểu tham số tường minh** giúp làm rõ dữ liệu đầu vào của lambda, đặc biệt với overload có các SAM khác kiểu tham số. **Cast lambda sang functional interface cụ thể** cung cấp target type cho toàn bộ biểu thức, cần thiết khi cùng một lambda phù hợp nhiều overload dù kiểu tham số đã rõ. **Biến trung gian có kiểu rõ ràng** thường là giải pháp dễ đọc; **type witness** giải quyết việc chọn tham số kiểu của phương thức generic khi cần.

Mọi cách trên đều phải tôn trọng hợp đồng SAM: số lượng/kiểu tham số, kiểu trả về, ngoại lệ, generic và tính hợp lệ của lambda. Nếu compiler báo mơ hồ vì API thiết kế chồng chéo, hãy cân nhắc dùng tên phương thức thể hiện ý định thay vì dựa lâu dài vào nhiều cast.

Tham khảo: *Java Language Specification* **`15.27 Lambda Expressions**, **`15.13 Method Reference Expressions**, **`15.12 Method Invocation Expressions**, **`18 Type Inference**; Javadoc **`java.util.function.Function`**, **`Predicate`** và **`java.util.Comparator`**. Dùng JDK 17+ để biên dịch các ví dụ.

# Khai báo kiểu tham số tường minh hoặc để suy luận trong lambda Java

## Mục tiêu

Lambda trong Java cho phép khai báo kiểu của tham số trực tiếp hoặc để trình biên dịch suy luận từ **functional interface đích** (*target type*). Viết gọn không có nghĩa là tham số không có kiểu: Java vẫn kiểm tra kiểu ở thời điểm biên dịch.

Sau bài này, bạn có thể:

- Phân biệt lambda **khai báo kiểu tường minh**, **kiểu suy luận ngầm** và dùng `var` cho tham số.
- Nhận diện cú pháp hợp lệ cho lambda có 0, 1 hoặc nhiều tham số.
- Giải thích trình biên dịch lấy kiểu từ assignment, đối số phương thức, phương thức generic và các ngữ cảnh target typing khác.
- Chọn cách khai báo hợp lý, xử lý lỗi do trộn cách viết hoặc khai báo kiểu không khớp.
- Hiểu phạm vi tên biến, giới hạn của biến capture và ảnh hưởng của kiểu primitive, generic, overloaded method.
- Biên dịch/chạy ví dụ Java 17 và tự kiểm tra các tình huống thường gặp.

## 1. Lambda không có kiểu độc lập nếu thiếu ngữ cảnh đích

Java là ngôn ngữ kiểm tra kiểu tĩnh. Một lambda thể hiện hành vi, nhưng để kiểm tra biểu thức ấy, trình biên dịch cần biết **functional interface** mà nó sẽ triển khai. Interface có đúng một phương thức trừu tượng hữu hiệu (SAM, *single abstract method*) cung cấp function descriptor gồm kiểu và số lượng tham số, kiểu kết quả, và các ngoại lệ checked cho phép.

Ví dụ:

```java
import java.util.function.Function;

Function<String, Integer> length = text -> text.length();
```

`Function<T,R>` có phương thức `R apply(T value)`. Khi thế `T = String` và `R = Integer`, descriptor của `length` là:

```text
(String) -> Integer
```

Vì thế, trong `text -> text.length()`, tham số `text` được hiểu là `String`; `String.length()` trả `int` và có thể được boxing thành `Integer`. Người viết không cần ghi `String` trong lambda vì target type đã cung cấp thông tin cần thiết.

Điều quan trọng: **lambda là poly expression**. Không thể viết:

```java
// Không biên dịch: lambda cần target functional interface.
var length = text -> text.length();
```

Ngay cả khi viết `(String text) -> text.length()` thay cho phần lambda trên, `var` của **biến cục bộ** vẫn không tự cung cấp functional interface đích cho một lambda trần. `var` dùng để suy luận kiểu biến cục bộ và `var` dùng trong **danh sách tham số lambda** là hai cú pháp có vai trò khác nhau.

Khi được đặt trong một ngữ cảnh cung cấp target type hợp lệ, lambda có thể triển khai interface mà không cần tạo lớp ẩn danh:

```java
// Hai biểu thức dưới đều gán được cho cùng một kiểu đích.
Function<String, Integer> inferred = text -> text.length();
Function<String, Integer> explicit =
        (String text) -> text.length();
```

Hai biến này đều có descriptor `(String) -> Integer`. Việc ghi kiểu tường minh thay đổi cú pháp và có thể tăng độ rõ ràng, nhưng không làm thay đổi hợp đồng của `Function.apply`.

## 2. Ba cách viết tham số lambda

### 2.1. Để Java suy luận kiểu

```java
Function<String, Integer> length = text -> text.length();
Function<String, Integer> alsoLength = (text) -> text.length();

java.util.function.BiFunction<Integer, Integer, Integer> add =
        (a, b) -> a + b;
```

Đây là **implicitly typed lambda parameters**: Java lấy kiểu từng tham số từ function descriptor.

- Với **một tham số** có kiểu ngầm định, có thể bỏ cặp dấu ngoặc tròn: `text -> ...`.
- Với **nhiều tham số**, bắt buộc có dấu ngoặc: `(a, b) -> ...`.
- Với **không tham số**, bắt buộc dùng `()`, ví dụ `() -> "Hello"`.

Các kiểu suy luận ở ví dụ lần lượt là `String`, `String` và hai `Integer` (được unboxing khi thực hiện phép cộng nếu cần). Không phải vì tham số viết ngắn mà nó có kiểu `Object` hoặc là biến dynamic.

### 2.2. Ghi kiểu tham số tường minh

```java
Function<String, Integer> length = (String text) -> text.length();

java.util.function.BiFunction<Integer, Integer, Integer> add =
        (Integer a, Integer b) -> a + b;

java.util.function.IntBinaryOperator sum =
        (int a, int b) -> a + b;
```

Đây là **explicitly typed lambda parameters**. Cách viết có thể có lợi khi lambda dài, khó đọc, khi cần làm rõ sự khác nhau giữa primitive và wrapper, hoặc khi phân tích sự tương thích với target type.

Khi ghi kiểu, **phải dùng dấu ngoặc** ngay cả với một tham số: `(String text) -> ...` là hợp lệ; `String text -> ...` là không hợp lệ. Mỗi tham số được khai báo kiểu tương thích với descriptor, không tùy ý đổi `String` thành `Object` nếu target đòi `String`.

Một trường hợp sai:

```java
// Không biên dịch: IntUnaryOperator có descriptor (int) -> int,
// nhưng lambda khai báo tham số String.
java.util.function.IntUnaryOperator wrong =
        (String number) -> number.length();
```

Cách sửa:

```java
java.util.function.IntUnaryOperator doubleValue =
        (int number) -> number * 2;
```

### 2.3. Dùng var cho tham số lambda — Java 11+

Từ Java 11, có thể viết:

```java
Function<String, Integer> length = (var text) -> text.length();

java.util.function.BiFunction<String, Integer, String> repeat =
        (var text, var times) -> text.repeat(times);
```

Ở đây, `var` yêu cầu compiler **suy luận kiểu tham số từ target descriptor**. Trong ví dụ trên, `text` có kiểu `String`, `times` có kiểu `Integer`. `var` không mang nghĩa “kiểu bất kỳ” hay tự động chuyển tham số sang `Object`.

`var` cần ngoặc: `(var text) -> ...` hợp lệ; `var text -> ...` không hợp lệ. Lợi ích đáng chú ý của dạng `var` là có thể gắn annotation lên tham số mà vẫn để compiler suy luận kiểu, nếu annotation đó có target phù hợp:

```java
Function<String, String> normalize =
        (@Deprecated var text) -> text.trim();
```

`@Deprecated` ở đây chỉ minh họa cú pháp annotation trên tham số, không phải lý do nghiệp vụ thông thường để đánh dấu tham số deprecated. Trong ứng dụng thực tế, dùng annotation có ngữ nghĩa phù hợp (như annotation nullability được hỗ trợ bởi công cụ dự án). Không cần `var` khi không có lý do rõ ràng; viết ngầm định `text -> ...` thường ngắn hơn.

## 3. Quy tắc tất cả tham số phải nhất quán

Trong cùng một lambda, Java không cho phép trộn tùy ý ba cách viết: tham số ngầm định, kiểu khai báo tường minh và `var`.

| Cú pháp | Kết quả | Lý do |
| --- | --- | --- |
| `(a, b) -> a + b` | Hợp lệ với target hai tham số số thích hợp | Cả hai tham số đều ngầm định |
| `(int a, int b) -> a + b` | Hợp lệ với target `(int,int) -> int` | Cả hai tham số tường minh |
| `(var a, var b) -> a + b` | Hợp lệ với target số thích hợp, Java 11+ | Cả hai dùng `var` |
| `(int a, b) -> a + b` | Không hợp lệ | Trộn kiểu tường minh với ngầm định |
| `(var a, int b) -> a + b` | Không hợp lệ | Trộn `var` với kiểu tường minh |
| `(a, var b) -> a + b` | Không hợp lệ | Trộn ngầm định với `var` |
| `(String s) -> s.trim()` | Hợp lệ với target `(String) -> String` | Đúng kiểu, có ngoặc |
| `String s -> s.trim()` | Không hợp lệ | Thiếu ngoặc khi có kiểu khai báo |

Lưu ý bảng này nói về **cú pháp** và tính tương thích với target type đã nêu. Nếu target khác hoặc phép toán không có nghĩa đối với các kiểu đã suy luận, một lambda cú pháp đúng vẫn có thể không biên dịch.

Thực hành: nếu lambda hai tham số đã được viết `(a, b)` và bạn muốn làm rõ kiểu, hãy chuyển **cả hai** thành `(String a, int b)` (khi đúng với descriptor), hoặc `(var a, var b)` trong Java 11+, thay vì chỉ sửa một tham số.

## 4. Cách target type cung cấp kiểu tham số

Compiler lấy thông tin kiểu từ **ngữ cảnh sử dụng lambda**, không chỉ từ phần thân của lambda.

### 4.1. Phép gán vào biến hoặc field

```java
java.util.function.Predicate<String> nonBlank =
        s -> !s.isBlank();

java.util.function.Consumer<String> print =
        s -> System.out.println(s);
```

`Predicate<String>` cho `s` kiểu `String` và yêu cầu trả `boolean`. `Consumer<String>` cũng cho tham số kiểu `String` nhưng có descriptor `(String) -> void`; body in thông báo và không trả giá trị cần dùng.

### 4.2. Đối số của một phương thức

Giả sử có phương thức:

```java
static String applyTo(
        String input,
        java.util.function.UnaryOperator<String> action) {
    return action.apply(input);
}
```

Khi gọi:

```java
String cleaned = applyTo("  Java  ", text -> text.trim());
```

Tham số thứ hai của `applyTo` có kiểu `UnaryOperator<String>` với descriptor `(String) -> String`. Vì vậy `text` của lambda được suy luận là `String` ngay trong biểu thức gọi. Không cần định nghĩa biến lambda trung gian.

### 4.3. API generic và suy luận type argument

```java
static <T, R> R transform(
        T input,
        java.util.function.Function<T, R> mapper) {
    return mapper.apply(input);
}
```

Gọi:

```java
int size = transform("Lambda", value -> value.length());
```

Đối số đầu `"Lambda"` góp phần xác định `T` là `String`. Target `Function<T,R>` của lambda cùng ràng buộc kiểu kết quả góp phần suy luận `R` phù hợp; `value` được hiểu là `String`, có thể gọi `length()`. Ở đây phép gọi trả giá trị `Integer`/`int` phù hợp với phép gán vào `int` qua unboxing khi cần.

Suy luận kiểu của phương thức generic thực tế tuân theo nhiều ràng buộc; không nên xem nó như thao tác compiler chỉ đọc một biến ở bên trái. Khi compiler không đủ ngữ cảnh, hãy chỉ rõ type argument, tạo biến trung gian có target type hoặc ghi kiểu tham số tường minh.

### 4.4. Ngữ cảnh Stream

```java
java.util.List<Integer> lengths =
        java.util.List.of("Java", "Go", "")
                .stream()
                .map(text -> text.length())
                .toList();
```

Nguồn Stream có phần tử `String`, nên `Stream.map(Function<? super String, ? extends R>)` cho compiler ngữ cảnh `text` là `String` và biểu thức trả `int` có thể trở thành phần tử `Integer`. Kết quả là `[4, 2, 0]`. Việc dùng Stream không làm mất kiểm tra kiểu, kể cả khi viết lambda mà không ghi kiểu tường minh.

## 5. Tham số kiểu ngầm định không có nghĩa là Object

Đôi khi người học tưởng rằng viết `value -> value.length()` thì `value` có kiểu không xác định hoặc mặc định `Object`. Thực tế, Java kiểm tra phương thức được gọi dựa trên **kiểu được target cung cấp**.

```java
java.util.function.Function<String, Integer> a =
        value -> value.length(); // hợp lệ

java.util.function.Function<Object, Integer> b =
        value -> value.length(); // không biên dịch: Object không có length()
```

Phần thân giống nhau nhưng `value` ở trường hợp thứ nhất là `String`, trường hợp thứ hai là `Object`. Compiler không tự đoán `String` chỉ vì bạn viết `length()`.

Nếu thực sự nhận `Object` và cần hành vi theo loại dữ liệu, phải kiểm tra và chuyển kiểu một cách có chủ đích:

```java
java.util.function.Function<Object, Integer> describe = value -> {
    if (value instanceof String text) {
        return text.length();
    }
    return 0;
};
```

Pattern matching `instanceof` dạng `String text` dùng được trong Java 17. Đây là vấn đề thiết kế kiểu đầu vào: nên khai báo target `Function<String,Integer>` khi nghiệp vụ thực sự chỉ nhận chuỗi, thay vì làm yếu hợp đồng thành `Function<Object,Integer>`.

### Primitive, wrapper và phép chuyển kiểu

```java
java.util.function.IntUnaryOperator square = x -> x * x;
java.util.function.Function<Integer, Integer> boxed =
        x -> x * x;
```

Trong `IntUnaryOperator`, `x` là primitive `int`; trong `Function<Integer,Integer>`, `x` là `Integer` được unboxing khi nhân. Cả hai có thể cho cùng kết quả số học ở trường hợp thông thường, nhưng kiểu tham số và cơ chế boxing khác nhau. Nếu `Integer` là `null`, phép unboxing có thể ném `NullPointerException`; primitive không biểu diễn `null`.

Khai báo kiểu tường minh phải phù hợp descriptor:

```java
java.util.function.IntUnaryOperator a =
        (int x) -> x * x; // hợp lệ

java.util.function.Function<Integer, Integer> b =
        (Integer x) -> x * x; // hợp lệ

// Không biên dịch: target nhận Integer, khai báo lambda nhận int.
// Trình biên dịch không coi (int x) và (Integer x) là cùng
// khai báo tham số tường minh.
java.util.function.Function<Integer, Integer> wrong =
        (int x) -> x * x;
```

Khi cần tối ưu xử lý primitive, chọn `IntUnaryOperator`, `ToIntFunction<T>`, `IntPredicate` hoặc interface primitive thích hợp. Việc bỏ kiểu tường minh không loại bỏ boxing nếu target vẫn là `Function<Integer,Integer>`.

## 6. Method overload và chỗ dễ nhầm khi suy luận

Giả sử một lớp có hai overload:

```java
@FunctionalInterface
interface TextToText {
    String map(String text);
}

@FunctionalInterface
interface TextToNumber {
    int map(String text);
}

static void execute(TextToText mapper) { /* ... */ }
static void execute(TextToNumber mapper) { /* ... */ }
```

Khi truyền lambda mà không có target rõ ràng, overload resolution có thể không chọn được một phương thức duy nhất:

```java
// Có thể gây mơ hồ trong overload resolution.
execute(text -> text.length());
```

Không nên trông chờ thêm `String` vào tham số lambda sẽ giải quyết mọi mơ hồ, vì cả hai descriptor đều nhận `String`. Cách rõ ràng và ổn định là gán lambda cho interface cụ thể rồi gọi overload:

```java
TextToNumber lengthRule = text -> text.length();
execute(lengthRule);
```

Với lambda tương tự nhưng trả `String`, dùng `TextToText`. Nếu API có overload khó phân biệt, có thể dùng ép kiểu tường minh vào functional interface, nhưng thường biến có tên hoặc API với tên phương thức rõ ràng dễ đọc hơn.

Một lỗi khác là nghĩ rằng viết `(String s) -> ...` luôn buộc compiler chọn một overload bất kỳ mong muốn. Kiểu tham số chỉ là **một phần** của descriptor; kiểu trả về, tính tương thích của body và toàn bộ quy tắc overload cũng có vai trò.

## 7. Vùng tên tham số và biến capture

Tên tham số lambda phải là tên biến hợp lệ; không được trùng tên với một biến cục bộ đã khai báo trong cùng phạm vi bao quanh theo quy tắc của Java.

```java
String text = "outside";

// Không biên dịch vì tham số lambda trùng tên biến cục bộ text.
java.util.function.Function<String, String> bad =
        text -> text.trim();
```

Cách sửa là đổi tên tham số:

```java
String text = "outside";
java.util.function.Function<String, String> good =
        value -> value.trim();
```

Đặt tên `value`, `item`, `number` theo ý nghĩa dữ liệu. Ghi kiểu tường minh không cho phép vượt qua quy tắc vùng tên.

Lambda cũng có thể **capture** biến cục bộ từ phạm vi ngoài khi biến đó là `final` hoặc *effectively final*, nghĩa là sau khi được khởi tạo nó không bị gán lại:

```java
String prefix = "ID-";
java.util.function.Function<Integer, String> makeId =
        number -> prefix + number;

System.out.println(makeId.apply(7)); // ID-7
```

Nếu sau đó gán `prefix = "NEW-"` trong cùng phương thức, trình biên dịch từ chối lambda capture `prefix` do biến không còn effectively final. Quy tắc này áp dụng dù tham số lambda viết `number`, `(Integer number)` hay `(var number)`.

**Effectively final không đồng nghĩa dữ liệu bất biến.** Nếu capture một `ArrayList` rồi thêm phần tử, tham chiếu list có thể không đổi nhưng nội dung đổi; việc này còn tạo tác dụng phụ và có thể không an toàn khi chạy song song. Suy luận kiểu và tính bất biến là hai chủ đề tách biệt.

## 8. Ví dụ Java 17 đầy đủ

Chương trình sau cho cùng kết quả với ba kiểu khai báo tham số của `Function<String,Integer>`. Nó đồng thời minh họa lambda hai tham số, target typing qua phương thức nhận hàm, generic method, Stream và interface có kết quả `void`.

Tạo file **`LambdaParameterTypesDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.function.BiFunction;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.UnaryOperator;

public class LambdaParameterTypesDemo {
    @FunctionalInterface
    interface Formatter {
        String repeat(String text, int times);
    }

    static String applyTo(String value, UnaryOperator<String> action) {
        return action.apply(value);
    }

    static <T, R> R transform(T input, Function<T, R> action) {
        return action.apply(input);
    }

    public static void main(String[] args) {
        Function<String, Integer> inferred = text -> text.length();
        Function<String, Integer> explicit =
                (String text) -> text.length();
        Function<String, Integer> withVar =
                (var text) -> text.length();

        Formatter repetition =
                (String text, int count) -> text.repeat(count);
        BiFunction<String, Integer, String> upper =
                (text, times) ->
                        text.toUpperCase(Locale.ROOT).repeat(times);

        Predicate<String> nonBlank = text -> !text.isBlank();
        Consumer<String> show = (String text) ->
                System.out.println("Consumer: " + text);

        List<Integer> lengths = List.of("Java", "Go", "")
                .stream()
                .map(s -> s.length())
                .toList();

        String trimmed = applyTo("  Java  ", value -> value.trim());
        int genericSize = transform("Lambda", String::length);

        System.out.println("Suy luận: " + inferred.apply("Java"));
        System.out.println("Tường minh: " + explicit.apply("Java"));
        System.out.println("var: " + withVar.apply("Java"));
        System.out.println("Hai tham số: " + repetition.repeat("Hi", 2));
        System.out.println("BiFunction: " + upper.apply("java", 2));
        System.out.println("Predicate: " + nonBlank.test(""));
        System.out.println("Stream: " + lengths);
        System.out.println("Từ lời gọi: " + trimmed);
        System.out.println("Generic: " + genericSize);
        show.accept("OK");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac LambdaParameterTypesDemo.java
java LambdaParameterTypesDemo
```

**Đầu ra:**

```text
Suy luận: 4
Tường minh: 4
var: 4
Hai tham số: HiHi
BiFunction: JAVAJAVA
Predicate: false
Stream: [4, 2, 0]
Từ lời gọi: Java
Generic: 6
Consumer: OK
```

**Vì sao output như vậy?**

- `inferred`, `explicit` và `withVar` đều triển khai `Function<String,Integer>` nên cùng nhận `String`, trả độ dài dạng `Integer`. `"Java".length()` là `4`.
- `Formatter.repeat` nhận `String` và `int`. Cặp tham số được khai báo tường minh, `"Hi".repeat(2)` trả `"HiHi"`.
- `BiFunction` nhận `String` và `Integer`; `"java"` thành `"JAVA"` theo `Locale.ROOT` rồi lặp hai lần, ra `"JAVAJAVA"`.
- `Predicate<String>` có kiểu kết quả `boolean`; chuỗi rỗng không thỏa `!text.isBlank()` nên in `false`.
- Stream từ ba chuỗi tạo độ dài `4`, `2`, `0`; phép `toList()` trả danh sách theo thứ tự encounter order trong pipeline tuần tự này.
- `applyTo` khai báo tham số `UnaryOperator<String>` nên lambda `value -> value.trim()` suy luận `value` là `String`; kết quả `"Java"`.
- `transform` dùng generic `T,R`; với `"Lambda"` và `String::length`, `genericSize` là `6`.
- `Consumer<String>` không trả kết quả, chỉ in `Consumer: OK`.

Tất cả các lambda trong chương trình có **target type tường minh ở vị trí phù hợp**; việc suy luận ở từng lambda dựa trên hợp đồng API, kể cả khi kiểu generic chỉ được xác định trong quá trình kiểm tra lời gọi.

## 9. Cách đọc lỗi compiler và sửa đúng vấn đề

**Sai cú pháp dấu ngoặc.** Viết `String text -> text.trim()` làm parser lỗi; sửa thành `(String text) -> text.trim()` hoặc `text -> text.trim()`.

**Trộn kiểu với `var` hoặc kiểu ngầm định.** `(String text, count)` và `(var text, int count)` sai; sửa đồng nhất theo một trong ba kiểu `(text, count)`, `(String text, int count)` hoặc `(var text, var count)`.

**Sai kiểu tham số so với descriptor.** `IntUnaryOperator op = (String x) -> x.length()` sai vì target nhận `int`; thay `(int x) -> x * 2` hoặc chọn `Function<String,Integer>` theo mục tiêu.

**Tưởng compiler suy luận dựa vào phép gọi trong body.** `Function<Object,Integer> f = x -> x.length()` không biên dịch; `Object` không có phương thức `length()`. Sửa kiểu target thành `Function<String,Integer>` nếu nghiệp vụ chỉ nhận chuỗi.

**Không có target type.** `var fn = x -> x + 1` sai vì compiler chưa biết interface đích. Khai báo `IntUnaryOperator fn = x -> x + 1` hoặc tạo interface riêng khi cần.

**Sai số tham số.** `BiFunction<String,Integer,String>` đòi hai tham số; lambda `text -> text` chỉ có một. Dùng `(text, times) -> text.repeat(times)`.

**Sai kiểu kết quả.** `Predicate<String> p = s -> s.length()` sai vì descriptor yêu cầu `boolean`. Sửa thành `s -> s.length() > 0`; đây là lỗi result type, dù tham số đã được suy luận đúng.

**Biến capture bị gán lại.** Nếu lambda dùng `prefix` từ scope ngoài rồi chương trình thay đổi `prefix`, compiler không cho phép capture. Dùng một biến local không bị gán lại, hoặc nếu thật sự cần trạng thái thay đổi thì thiết kế một đối tượng quản lý trạng thái rõ ràng.

**Checked exception.** `Function<Path,String>` không khai báo `throws IOException` trong `apply`; dù lambda ghi kiểu tham số tường minh hay ngầm định, cũng không được ném `IOException` ra ngoài nếu không xử lý. Cần bắt/chuyển ngoại lệ có chủ đích hoặc dùng functional interface riêng có `throws`. Việc đổi `path -> ...` thành `(Path path) -> ...` không giải quyết vấn đề này.

**Method overload khó chọn.** Đặt lambda vào biến có kiểu interface cụ thể, hoặc điều chỉnh thiết kế API để caller nhìn thấy rõ target type. Đừng dựa hoàn toàn vào suy luận khi nhiều overload có hợp đồng gần giống nhau.

## 10. Khi nào nên tường minh và khi nào nên suy luận?

| Tình huống | Gợi ý | Lý do |
| --- | --- | --- |
| `list.stream().map(item -> item.name())`, kiểu rõ từ nguồn | Suy luận ngầm định | Ít lặp, vẫn được kiểm tra kiểu |
| Lambda hai tham số dài, kiểu dễ nhầm | Xem xét tường minh | Giúp người đọc nhanh hiểu thứ tự và kiểu dữ liệu |
| Target là primitive functional interface | Suy luận hoặc tường minh đều được | Quan trọng nhất là chọn đúng interface để tránh boxing ngoài ý muốn |
| Muốn gắn annotation lên tham số lambda mà vẫn suy luận | Dùng `(var x)`, Java 11+ | Hỗ trợ annotation tại tham số với cú pháp suy luận |
| Gặp overload/generic khiến target không rõ | Tạo biến trung gian có kiểu rõ hoặc điều chỉnh API | Làm target type minh bạch hơn |
| Đang chữa lỗi checked exception, result type hay capture | Sửa hợp đồng/logic tương ứng | Chỉ thêm tên kiểu tham số chưa chắc giải quyết lỗi |

Nguyên tắc thực dụng: **để suy luận khi ngữ cảnh đã nói rõ kiểu; ghi tường minh khi giúp làm rõ hợp đồng hoặc phục vụ một nhu cầu cú pháp cụ thể**. Không cần ép toàn bộ dự án theo một kiểu trình bày duy nhất, nhưng nên tuân thủ quy ước chung để mã dễ đọc.

## 11. Bài tập tự kiểm tra

1. Cho `Function<String,Integer> f = text -> text.length();`. Kiểu thực tế của `text` là gì, dù không ghi trong lambda? Viết lại cùng logic bằng tham số tường minh và `var`.
2. Cho `BiFunction<String,Integer,String> f`. Viết lambda lặp chuỗi `n` lần bằng cả ba kiểu khai báo tham số.
3. Trong `Function<Object,Integer> f = x -> x.length();`, vì sao compiler báo lỗi? Có nên ép `x` sang `String` ngay trong body hay sửa target interface?
4. Phân loại cú pháp `(x, y) -> x + y`, `(int x, y) -> x + y`, `(var x, var y) -> x + y`, `(x, var y) -> x + y`. Với target phù hợp, biểu thức nào hợp lệ?
5. Tại sao `var f = (String s) -> s.trim();` không biên dịch? `var` biến cục bộ khác gì `(var s)` trong lambda?
6. Một phương thức nhận `UnaryOperator<String>`. Compiler biết kiểu của tham số `s` như thế nào trong lời gọi `process(s -> s.trim())`?
7. Cho `String prefix = "ID-"; Function<Integer,String> f = n -> prefix + n;`. Điều gì xảy ra nếu ngay sau đó gán lại `prefix`? Vì sao?
8. Trong ví dụ chạy được, thử viết lại `Formatter repetition` bằng `(text, count) -> text.repeat(count)`. Dự đoán kết quả có đổi không.

**Gợi ý đáp án:** (1) `String`; `(String text) -> text.length()`; `(var text) -> text.length()`. (2) `(s,n) -> s.repeat(n)`, `(String s,Integer n) -> s.repeat(n)`, `(var s,var n) -> s.repeat(n)`. (3) `Object` không có `length()`; sửa target thành `Function<String,Integer>` nếu đầu vào thực tế phải là String. (4) Hợp lệ: dạng đầu và dạng dùng hai `var`; hai dạng trộn không hợp lệ. (5) Lambda cần target functional interface; `var` trên tham số không thay target. (6) Từ `UnaryOperator<String>` có descriptor `(String)->String`. (7) Lỗi không effectively final. (8) Không đổi vì target type và logic vẫn như cũ.

## Kết luận

Trong Java, khai báo kiểu tham số lambda **tường minh** (`(String text)`), **ngầm định** (`text`) hay dùng **`var`** (`(var text)`) đều phải tương thích với cùng functional interface đích. Trình biên dịch suy luận dựa trên ngữ cảnh target typing, không đoán kiểu từ cú pháp lambda một cách độc lập. Nắm chắc quy tắc dấu ngoặc, tính nhất quán khi khai báo nhiều tham số và hợp đồng generic/primitive giúp viết lambda ngắn gọn nhưng vẫn an toàn kiểu.

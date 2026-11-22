# Kiểu tham số tường minh hoặc được suy luận trong lambda Java

## Mục tiêu

Lambda expression, được giới thiệu từ Java 8 và vẫn sử dụng rộng rãi trong Java hiện hành, có hai cách khai báo tham số: **ghi kiểu tường minh** (explicitly typed) hoặc **để trình biên dịch suy luận kiểu** (implicitly typed). Chọn cách nào phụ thuộc vào kiểu đích, độ rõ ràng và phiên bản Java cần hỗ trợ.

Sau bài này, bạn sẽ hiểu kiểu tham số lambda lấy từ đâu; viết đúng cú pháp một, nhiều và không tham số; phân biệt các trường hợp hợp lệ/bị lỗi; đọc ảnh hưởng của generic và overload; đồng thời biết khi nào dùng cú pháp `var` bổ sung từ Java 11.

## 1. Compiler biết kiểu tham số từ đâu?

Lambda là cách viết phần triển khai cho **phương thức trừu tượng duy nhất** (single abstract method, SAM) của một **functional interface**. Ví dụ:

~~~java
@FunctionalInterface
interface TextLength {
    int lengthOf(String text);
}
~~~

Khi gán một lambda cho functional interface:

~~~java
TextLength length = text -> text.length();
~~~

Compiler biết từ phương thức `lengthOf(String)` rằng `text` trong lambda có kiểu `String` và body phải cho ra giá trị tương thích với `int`. Việc xác định kiểu theo **ngữ cảnh mà lambda được đặt vào** gọi là **target typing**.

~~~text
TextLength (functional interface)
  -> int lengthOf(String text) (SAM)
  -> text -> text.length() (lambda)
  -> text có kiểu String tại compile time
~~~

Kiểu được suy luận ở **thời điểm biên dịch**, không phải kiểu động được lựa chọn khi chạy. Compiler dựa vào target type, không suy kiểu chỉ từ tên biến hay chỉ từ phép toán bên trong body.

Target type có thể đến từ khai báo biến, tham số phương thức, kiểu trả về, phép ép kiểu hoặc ngữ cảnh biểu thức mà Java cho phép target typing. Ví dụ:

~~~java
java.util.function.Function<String, Integer> length =
        s -> s.length();

java.util.function.Predicate<String> nonEmpty =
        s -> !s.isEmpty();

java.util.function.BiFunction<Integer, Integer, Integer> sum =
        (left, right) -> left + right;
~~~

Trong hai lambda đầu, `s` là `String`. Trong lambda thứ ba, `left` và `right` là `Integer` theo kiểu đích `BiFunction<Integer, Integer, Integer>`.

Một lambda **không tự có kiểu đích** chỉ vì trông giống một hàm. Dòng sau không hợp lệ ngay cả trên JDK mới:

~~~java
// Không hợp lệ: compiler chưa biết functional interface mục tiêu
// var length = s -> s.length();
~~~

Cần khai báo kiểu đích rõ ràng, chẳng hạn `Function<String, Integer>` như trên. `var` cho biến cục bộ không thể tự xác định functional interface chỉ từ lambda.

## 2. Tham số suy luận kiểu (implicitly typed)

Khi target type đã rõ, có thể bỏ khai báo kiểu của tham số:

| Số tham số | Cú pháp hợp lệ | Vì sao |
| --- | --- | --- |
| Không tham số | `() -> "ready"` | Bắt buộc có cặp ngoặc rỗng |
| Một tham số | `value -> value.length()` | Có thể bỏ ngoặc nếu chỉ viết tên tham số |
| Một tham số | `(value) -> value.length()` | Giữ ngoặc cũng hợp lệ |
| Nhiều tham số | `(left, right) -> left + right` | Cần ngoặc và dấu phẩy |

Ví dụ:

~~~java
java.util.function.Function<String, String> upper =
        word -> word.toUpperCase();

java.util.Comparator<String> byLength =
        (left, right) ->
                Integer.compare(left.length(), right.length());
~~~

`Comparator<String>` có phương thức SAM `int compare(String, String)`. Vì vậy compiler hiểu `left` và `right` là `String` và kiểm tra body trả về `int`.

Không thể viết `left, right -> ...` mà bỏ ngoặc: việc bỏ ngoặc chỉ áp dụng với **một tham số đơn giản, không ghi kiểu**.

## 3. Tham số ghi kiểu tường minh (explicitly typed)

Nếu muốn nhìn thấy kiểu ngay trong lambda, khai báo như tham số phương thức:

~~~java
java.util.function.Function<String, Integer> length =
        (String word) -> word.length();

java.util.function.BiFunction<Integer, Integer, Integer> sum =
        (Integer left, Integer right) -> left + right;
~~~

Quy tắc:

1. **Có kiểu thì phải có ngoặc:** `(String word) -> ...` là đúng; `String word -> ...` là sai.
2. **Với nhiều tham số, tất cả phải có kiểu cụ thể**, ví dụ `(String first, String second) -> ...`.
3. Kiểu được ghi phải khớp kiểu tham số trong function type của functional interface mục tiêu theo quy tắc Java, không tự ý đổi sang kiểu cha/con.
4. Tên tham số được chọn theo ý nghĩa sử dụng, không cần trùng tên ở khai báo SAM; nhưng không được xung đột với tên biến cục bộ đã có trong phạm vi bao ngoài.

Ví dụ `Function<String, Integer>` không nhận lambda khai báo tham số `Object` thay vì `String`:

~~~java
java.util.function.Function<String, Integer> correct =
        (String word) -> word.length();

// Sai: parameter type Object không khớp String của SAM.
// java.util.function.Function<String, Integer> wrong =
//         (Object word) -> word.toString().length();
~~~

Cách ghi tường minh thường hữu ích khi kiểu khó nhận ra, cần bổ sung annotation/modifier trên tham số, hoặc cần giúp compiler chọn đúng overload. Khi target type đã rõ và body ngắn, viết suy luận thường dễ đọc hơn.

## 4. Không được trộn cách viết trong cùng một lambda

Với nhiều tham số, bạn phải chọn **một cách thống nhất**:

~~~java
// Đúng: tất cả suy luận từ BiFunction<String, String, String>
java.util.function.BiFunction<String, String, String> a =
        (left, right) -> left + right;

// Đúng: tất cả ghi kiểu tường minh
java.util.function.BiFunction<String, String, String> b =
        (String left, String right) -> left + right;

// Sai: trộn kiểu tường minh với kiểu suy luận
// java.util.function.BiFunction<String, String, String> c =
//         (String left, right) -> left + right;

// Sai: trộn kiểu suy luận với kiểu tường minh
// java.util.function.BiFunction<String, String, String> d =
//         (left, String right) -> left + right;
~~~

Hai dòng sai sẽ bị từ chối ở **compile time**; đây không chỉ là quy tắc style. Nếu đổi một tham số sang kiểu tường minh thì phải đổi các tham số còn lại của cùng lambda.

Riêng lambda không tham số vẫn viết `() -> ...`; theo định nghĩa của Java Language Specification, lambda không có tham số được phân loại là **explicitly typed** dù thực tế không có kiểu tham số nào để khai báo.

## 5. Ví dụ hoàn chỉnh chạy được trên JDK 17+, tương thích cú pháp và API Java 8

Lưu thành tệp **`LambdaParameterTypesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class LambdaParameterTypesDemo {
    public static void main(String[] args) {
        Function<String, Integer> lengthInferred =
                text -> text.length();

        Function<String, Integer> lengthExplicit =
                (String text) -> text.length();

        BiFunction<Integer, Integer, Integer> sumInferred =
                (left, right) -> left + right;

        BiFunction<Integer, Integer, Integer> sumExplicit =
                (Integer left, Integer right) -> left + right;

        Predicate<String> nonEmpty =
                (String text) -> !text.isEmpty();

        List<String> names =
                new ArrayList<>(Arrays.asList("Binh", "An", "Chi"));

        names.sort((left, right) ->
                Integer.compare(left.length(), right.length()));

        List<String> filtered = names.stream()
                .filter(name -> name.length() >= 3)
                .collect(Collectors.toList());

        System.out.println("inferred=" + lengthInferred.apply("Java"));
        System.out.println("explicit=" + lengthExplicit.apply("Lambda"));
        System.out.println("sum-inferred=" + sumInferred.apply(2, 3));
        System.out.println("sum-explicit=" + sumExplicit.apply(2, 3));
        System.out.println("non-empty=" + nonEmpty.test("OK"));
        System.out.println("sorted=" + names);
        System.out.println("filtered=" + filtered);
    }
}
~~~

Dùng JDK 17 hoặc bản mới hơn có hỗ trợ `--release 8`:

~~~bash
javac --release 8 LambdaParameterTypesDemo.java
java LambdaParameterTypesDemo
~~~

Stdout chính xác:

~~~text
inferred=4
explicit=6
sum-inferred=5
sum-explicit=5
non-empty=true
sorted=[An, Chi, Binh]
filtered=[Chi, Binh]
~~~

Giải thích theo target type:

- `Function<String, Integer>` quy định tham số là `String`, kết quả là `Integer`. `String.length()` trả về `int` và được boxing để phù hợp `Integer`.
- `BiFunction<Integer, Integer, Integer>` quy định hai tham số `Integer`; phép cộng trong body sử dụng unboxing rồi boxing kết quả.
- `List.sort` nhận comparator cho phần tử `String`, nên `left` và `right` được suy ra phù hợp với `String`.
- `Stream<String>.filter` nhận predicate trên `String`, nên `name` là `String`.
- Dòng `lengthInferred` và `lengthExplicit` khác cú pháp khai báo tham số; **không khác hợp đồng của `Function`**.

Ví dụ nhắm baseline Java 8 để minh họa khả năng tương thích; khi triển khai phần mềm thực tế hãy dùng JDK còn được hỗ trợ. Không cần chạy một runtime đã cũ chỉ để học cú pháp Java 8.

## 6. Target type khi lambda là đối số phương thức

Target type không bắt buộc nằm ngay bên trái toán tử gán `=`. Có thể lấy từ kiểu tham số của phương thức nhận lambda.

Lưu thành tệp **`LambdaTargetExample.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.function.Predicate;

public class LambdaTargetExample {
    static long countMatching(List<String> values,
                              Predicate<String> condition) {
        return values.stream().filter(condition).count();
    }

    public static void main(String[] args) {
        List<String> words = Arrays.asList("java", "a", "lambda");
        long count = countMatching(
                words, word -> word.length() >= 4);
        System.out.println(count);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 8 LambdaTargetExample.java
java LambdaTargetExample
~~~

Stdout:

~~~text
2
~~~

Compiler xác định `word` là `String` vì tham số thứ hai của `countMatching` có kiểu `Predicate<String>`, có SAM `boolean test(String)`. Nhờ target type, một lambda có thể truyền thẳng vào API generic mà không phải gõ lại toàn bộ tên kiểu.

**Phân biệt hai cơ chế liên quan:** compiler có thể **suy luận tham số kiểu generic** của một lời gọi và cũng có thể **suy luận kiểu tham số lambda** từ functional interface sau khi áp dụng các ràng buộc kiểu. Chúng tương tác với nhau, nhưng không nên kết luận kiểu lambda chỉ từ tên của tham số hoặc từ kiểu trả về.

## 7. Overload và lỗi mơ hồ

Khi nhiều overload nhận các functional interface khác nhau, một lambda suy luận có thể tương thích với hơn một lựa chọn. Ví dụ sau là **mã minh họa**, chưa phải chương trình độc lập:

~~~java
@FunctionalInterface
interface StringRule {
    boolean test(String text);
}

@FunctionalInterface
interface IntegerRule {
    boolean test(Integer value);
}

// Giả sử có hai overload:
// void check(StringRule rule) { ... }
// void check(IntegerRule rule) { ... }

// Không hợp lệ: body true phù hợp cả hai target
// check(value -> true);

// Tham số tường minh giúp chọn StringRule
// check((String value) -> true);

// Hoặc ép kiểu để nêu đúng target type
// check((StringRule) value -> true);
~~~

Với `value -> true`, body không cung cấp thông tin để loại trừ một trong hai interface. Khi khai báo `(String value)`, overload nhận `IntegerRule` không còn tương thích vì tham số SAM của nó là `Integer`. Trong các trường hợp khó hơn, ghi kiểu tường minh chưa chắc giải quyết được mơ hồ: cần xem chính xác các chữ ký overload hoặc gán lambda vào biến có kiểu cụ thể trước khi truyền vào.

Lỗi `reference to ... is ambiguous` là vấn đề **overload resolution/target typing**. Không nên sửa bằng cách ép kiểu tùy tiện mà không kiểm tra hợp đồng API thực sự mong muốn.

## 8. Java 11 bổ sung `var` vào tham số lambda

Từ **Java 11**, có thêm cú pháp:

~~~java
java.util.function.BiFunction<String, String, String> join =
        (var first, var second) -> first + second;
~~~

`var` ở đây vẫn nhận kiểu từ functional interface: `first` và `second` là `String` tại compile time. Nó **không phải kiểu động** và không thay thế target type.

| Cách khai báo | Phiên bản đầu tiên hỗ trợ | Kiểu tham số |
| --- | --- | --- |
| `(first, second) -> first + second` | Java 8 | Suy luận |
| `(String first, String second) -> first + second` | Java 8 | Tường minh |
| `(var first, var second) -> first + second` | Java 11 | Vẫn suy luận |

Quy tắc `var`:

- Nếu một tham số dùng `var` thì **mọi tham số khác** trong cùng lambda cũng phải dùng `var`.
- `(var first, second)` và `(var first, String second)` đều không hợp lệ.
- Ngay cả một tham số `var` cũng phải nằm trong ngoặc: `(var text) -> ...` đúng; `var text -> ...` sai.
- Có thể thêm modifier phù hợp như `final var`; một lợi ích của cú pháp này là hỗ trợ annotation/modifier khi vẫn suy luận kiểu.
- Đừng nhầm mốc **Java 10** của `var` cho **biến cục bộ** với mốc **Java 11** của `var` cho **tham số lambda**.

### Ví dụ Java 11+ chạy được

Lưu thành **`LambdaVarDemo.java`**:

~~~java
import java.util.function.BiFunction;
import java.util.function.Predicate;

public class LambdaVarDemo {
    public static void main(String[] args) {
        BiFunction<String, String, String> join =
                (var first, var second) ->
                        first.strip() + " " + second.strip();

        Predicate<String> hasText =
                (final var value) -> !value.isBlank();

        System.out.println(join.apply(" java ", " lambda "));
        System.out.println(hasText.test("  "));
    }
}
~~~

Dùng JDK 17+ để biên dịch theo API Java 11:

~~~bash
javac --release 11 LambdaVarDemo.java
java LambdaVarDemo
~~~

Stdout chính xác:

~~~text
java lambda
false
~~~

Ví dụ này dùng `var` ở tham số lambda cùng `String.strip()` và `String.isBlank()`, đều được hỗ trợ từ Java 11. Nếu đổi thành `--release 8`, mã sẽ **không biên dịch**. Khi dự án cần tương thích Java 8, tiếp tục dùng dạng `text -> ...` hoặc `(String text) -> ...` và những API có trong baseline đó.

Không nên coi cú pháp không có `var` là lỗi thời: `text -> ...` vẫn là cách viết hợp lệ và được dùng rộng rãi trong Java hiện đại.

## 9. Phạm vi tên và biến bên ngoài được capture

Tên tham số lambda không được xung đột với biến cục bộ đã được khai báo trong phạm vi bao ngoài:

~~~java
String label = "Java";

// Không hợp lệ: tham số lambda trùng tên biến local bên ngoài
// java.util.function.Function<String, String> bad =
//         label -> label.toUpperCase();

// Hợp lệ: dùng tên tham số khác
java.util.function.Function<String, String> good =
        text -> label + " " + text;
~~~

Biến cục bộ từ ngoài được lambda sử dụng như `label` phải là `final` hoặc **effectively final**, nghĩa là không bị gán lại sau lần khởi tạo. Quy tắc này giống nhau dù bạn dùng tham số suy luận, tường minh hay `var`. Đừng nhầm nó với khả năng gán lại tham số **bên trong** lambda; trong thực hành nên tránh gán lại tham số nếu không thật cần thiết.

## 10. Nên dùng cách viết nào?

| Tình huống | Cách viết nên cân nhắc | Lý do |
| --- | --- | --- |
| Lambda ngắn, target type rõ | `item -> item.getName()` | Ít lặp kiểu, dễ đọc |
| Comparator có generic rõ | `(left, right) -> ...` | Tham số đã được SAM quyết định |
| Muốn thể hiện ngay kiểu dữ liệu | `(String text) -> ...` | Rõ ở điểm đọc lambda |
| Compiler báo overload ambiguous | `(String text) -> ...` hoặc target cast | Có thể làm rõ function type |
| Dùng modifier/annotation với suy luận, Java 11+ | `(final var text) -> ...` | Hỗ trợ cú pháp khai báo vẫn suy luận |
| Cần tương thích `--release 8` | `text -> ...` hoặc `(String text) -> ...` | `var` lambda chưa tồn tại |

Ưu tiên làm **target type dễ nhận ra**. Nếu một lambda dài hoặc khó hiểu, có thể tách ra biến có kiểu `Predicate<String>`/`Function<String, R>`/`Comparator<T>` rõ ràng, đặt tên biến theo ý nghĩa và chỉ ghi kiểu tường minh khi điều đó giúp người đọc.

## 11. Lỗi phổ biến và hướng sửa

1. **Quên ngoặc khi ghi kiểu:** `String text -> ...` sai; viết `(String text) -> ...`.
2. **Trộn tham số typed và inferred:** `(String a, b)` sai; chọn `(a, b)` hoặc `(String a, String b)`.
3. **Nhầm `var` là tính năng Java 8:** `(var a, var b)` chỉ có từ Java 11.
4. **Trộn `var` với kiểu khác:** `(var a, String b)` và `(var a, b)` đều không biên dịch.
5. **Không có kiểu đích:** `var fn = x -> ...` thiếu functional interface mà compiler cần.
6. **Kiểu tường minh không khớp SAM:** `(Object x)` không thay được `(String x)` cho `Function<String, ...>`.
7. **Dùng raw generic:** `Function` không khai báo `<T, R>` khiến thông tin kiểu bị mất; dùng generic cụ thể.
8. **Nhiều overload phù hợp:** compiler có thể không tự chọn; kiểm tra chữ ký và làm rõ target type.
9. **Nhầm capture với inference:** effectively final kiểm soát biến local ở ngoài được lambda dùng, không phải cách suy luận kiểu tham số.

Khi gặp lỗi biên dịch, kiểm tra theo thứ tự: functional interface mục tiêu → chữ ký SAM → số lượng và cách khai báo tham số → kiểu dữ liệu thực tế → nội dung body → mức Java của `--release`.

## 12. Bài tập tự kiểm tra

1. Đổi `Predicate<String> valid = text -> text.length() > 2;` thành dạng có kiểu tham số tường minh.
2. Với `BiFunction<Integer, Integer, Integer> multiply = (a, b) -> a * b;`, compiler suy ra kiểu của `a` và `b` từ đâu?
3. Vì sao `(String left, right) -> left + right` không hợp lệ? Viết phiên bản đúng cho cả hai cách.
4. Có dùng được `(var text) -> text.length()` với `--release 8` không? Vì sao?
5. Vì sao `value -> true` có thể mơ hồ khi truyền cho hai overload `StringRule` và `IntegerRule`? Viết cách chỉ rõ target type.
6. Tại sao `var formatter = x -> x.toString();` không hợp lệ? Khai báo `Function<String, String>` sẽ giải quyết như thế nào?

**Tiêu chí đạt:** Bạn diễn giải được target typing, viết đúng tham số typed và inferred, nhận biết cú pháp Java 11 của `var`, xác định được lỗi compile time và lựa chọn cách viết phù hợp phiên bản Java dự án.

## Tài liệu chính thức

- Java Language Specification (Java SE 26), `15.27 Lambda Expressions`, đặc biệt `15.27.1` và `15.27.3`: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html
- Oracle Java Language Changes for Java SE 11 và JEP 323: https://docs.oracle.com/en/java/javase/11/language/java-language-changes-release.html
- Oracle Local Variable Type Inference (quy tắc `var` với lambda): https://docs.oracle.com/en/java/javase/20/language/local-variable-type-inference.html
- Oracle Java 8 tutorial, Lambda Expressions và Target Typing (tài liệu nguồn về tính năng Java 8): https://docs.oracle.com/javase/tutorial/java/javaOO/lambdaexpressions.html

Khi xây dựng phần mềm mới, đọc đặc tả JDK còn được hỗ trợ; chỉ dùng nguồn Java 8 để xác nhận **mốc lịch sử và mức tương thích** của cú pháp gốc. Hai cách khai báo tham số này đều tiếp tục có giá trị trong Java hiện đại.
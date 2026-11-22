# Phân biệt `var` cục bộ của Java 10 và `var` trong tham số lambda từ Java 11

**Chủ đề:** Vị trí dùng `var`. Bài học tập trung vào hai tính năng hiện còn được hỗ trợ trong Java hiện đại: *local-variable type inference* từ Java 10 (JEP 286) và cú pháp `var` cho tham số lambda từ Java 11 (JEP 323). Những ví dụ hoàn chỉnh cuối bài được kiểm tra bằng trình biên dịch Java với `--release 10`, `--release 11` hoặc `--release 17` tương ứng.

## 1. Cùng viết `var` nhưng có hai vai trò khác nhau

Trong cả hai trường hợp, `var` là cách biểu diễn một kiểu **được trình biên dịch xác định tại thời điểm biên dịch**, không tạo ra biến có kiểu thay đổi tùy ý lúc chạy. Sự khác biệt quan trọng là **vị trí khai báo và nguồn dùng để suy luận kiểu**.

| Tiêu chí | `var` cho biến cục bộ (Java 10+) | `var` trong danh sách tham số lambda (Java 11+) |
| --- | --- | --- |
| Nơi xuất hiện | Khai báo biến cục bộ trong khối, vòng lặp `for`/`for-each`, khai báo tài nguyên `try-with-resources` | Danh sách tham số của biểu thức lambda |
| Dạng tiêu biểu | `var size = names.size();` | `(var name) -> name.length()` |
| Kiểu lấy từ đâu? | Từ **biểu thức khởi tạo** ở bên phải phép gán khi khai báo (hoặc biểu thức nguồn của `for-each`) | Từ **kiểu đích** (*target type*) là functional interface, cụ thể là chữ ký phương thức trừu tượng duy nhất |
| Có cần biểu thức khởi tạo tại chỗ? | Có, đối với khai báo biến cục bộ thông thường: `var n = 3;` | Không viết giá trị khởi tạo cho tham số; giá trị được truyền khi lambda được gọi |
| Điểm bắt đầu hỗ trợ | Java 10 | Java 11 |
| Hành vi thời gian chạy | Giống hệt biến cục bộ khai báo bằng kiểu tường minh | Giống hệt lambda khai báo tham số bằng kiểu suy luận thông thường |
| Giá trị sử dụng | Giảm lặp tên kiểu rõ ràng từ initializer | Giữ cú pháp tham số thống nhất, cho phép gắn annotation hoặc modifier như `final` khi muốn suy luận kiểu |

Ví dụ đối chiếu:

~~~java
var count = 3;  // biến cục bộ; compiler suy ra int từ 3

java.util.function.Function<String, Integer> length =
        (var text) -> text.length();
// text là tham số lambda; compiler suy ra String từ Function<String, Integer>
~~~

Đây là **hai dòng minh họa đặt trong một phương thức**. Dòng đầu tiên hợp lệ từ Java 10; dòng thứ hai cần Java 11 trở lên. `var` trong dòng thứ hai không suy luận kiểu từ `text.length()` để quyết định kiểu của `text`; kiểu `String` đã do `Function<String, Integer>` xác định.

## 2. Java 10: `var` khai báo biến cục bộ

### Các vị trí hợp lệ

~~~java
var total = 10;                    // biến cục bộ; kiểu int
var title = "Java";                // biến cục bộ; kiểu String
var names = java.util.List.of("An", "Binh"); // kiểu List<String>

for (var i = 0; i < 3; i++) {     // biến khởi tạo của vòng for
    System.out.println(i);
}
for (var name : names) {           // biến lặp của for-each
    System.out.println(name);
}
~~~

Đây là **đoạn minh họa** có thể đặt bên trong phương thức. Java 10 cũng hỗ trợ `var` khi **khai báo** tài nguyên trong `try-with-resources`, ví dụ `try (var reader = Files.newBufferedReader(path)) { ... }` khi kiểu và các exception cần thiết đã được xử lý phù hợp. Với `var`, kiểu suy ra vẫn là kiểu tĩnh và không thể đổi giữa các phép gán.

### Ví dụ chạy được ở mức ngôn ngữ Java 10

Lưu đúng tên **`Java10LocalDemo.java`**:

~~~java
import java.util.function.Function;

public class Java10LocalDemo {
    public static void main(String[] args) {
        var base = 10;

        Function<String, Integer> measure = text -> {
            var length = text.length();
            return length + base;
        };

        System.out.println(measure.apply("abc"));
    }
}
~~~

Biên dịch và chạy bằng JDK hiện đại có hỗ trợ `--release 10`:

~~~bash
javac --release 10 Java10LocalDemo.java
java Java10LocalDemo
~~~

Stdout:

~~~text
13
~~~

Ở đây `base` và `length` đều là **biến cục bộ** khai báo bằng `var`; `length` nằm trong **thân lambda**. Điều này đã hợp lệ từ Java 10 vì `length` không phải *tham số lambda*. Tham số `text` được viết bằng cú pháp suy luận kiểu `text -> ...`, vốn đã tồn tại trước Java 10.

`base` được lambda sử dụng từ phạm vi bao quanh (capture). Nó không bị gán lại nên là *effectively final*; viết `var` không thay đổi quy tắc này.

### Những giới hạn vẫn áp dụng

- Không dùng `var` làm kiểu field, kiểu trả về của phương thức, kiểu tham số phương thức thông thường hoặc kiểu tham số constructor.
- Khai báo `var item;` không có initializer là không hợp lệ; `var item = null;` cũng không hợp lệ vì không suy ra được kiểu phù hợp.
- Một biểu thức lambda đứng riêng không cung cấp target type cho `var f = x -> x + 1;` hoặc `var f = (var x) -> x + 1;`. Phải cung cấp functional interface, ví dụ `java.util.function.IntUnaryOperator f = x -> x + 1;`.
- `var total = 10;` được suy ra là `int`. Câu lệnh `total = "mười";` gây lỗi kiểu khi biên dịch.

## 3. Java 11: `var` cho tham số lambda

Java 11 mở rộng cú pháp **tham số lambda có kiểu suy luận** để có thể viết `var` ngay tại tham số. Cách viết này không tạo ra một biến cục bộ theo cơ chế suy luận từ initializer giống Java 10.

Với functional interface:

~~~java
java.util.function.BiFunction<Integer, Integer, Integer> add =
        (var a, var b) -> a + b;
~~~

Trình biên dịch suy ra `a` và `b` là `Integer` dựa trên chữ ký `BiFunction<Integer, Integer, Integer>`. Giá trị hai tham số chỉ được truyền khi gọi `add.apply(...)`. `var` là cách biểu diễn **kiểu tham số được suy luận**, không phải kiểu mới và cũng không làm lambda trở thành kiểu động.

Ba cách khai báo dưới đây có ý nghĩa tương đương đối với lambda này:

~~~java
java.util.function.BiFunction<Integer, Integer, Integer> sum1 =
        (a, b) -> a + b;                         // suy luận, không viết var
java.util.function.BiFunction<Integer, Integer, Integer> sum2 =
        (var a, var b) -> a + b;                 // Java 11+
java.util.function.BiFunction<Integer, Integer, Integer> sum3 =
        (Integer a, Integer b) -> a + b;         // khai báo kiểu tường minh
~~~

Đây là **đoạn minh họa** có thể đặt trong phương thức. `sum1` và `sum2` là hai cách dùng tham số suy luận kiểu. Ở `sum3`, kiểu được ghi tường minh. Các lựa chọn trên không thay đổi kết quả tính toán trong ví dụ.

**Cú pháp bắt buộc khi dùng `var`:** danh sách tham số phải đặt trong ngoặc đơn, kể cả chỉ có một tham số: `(var text) -> text.length()`. Cú pháp `var text -> ...` không hợp lệ.

### Ví dụ chạy được ở mức ngôn ngữ Java 11

Lưu đúng tên **`Java11LambdaDemo.java`**:

~~~java
import java.util.function.BiFunction;

public class Java11LambdaDemo {
    public static void main(String[] args) {
        var offset = 10;
        BiFunction<Integer, Integer, Integer> add =
                (var a, var b) -> a + b + offset;

        System.out.println(add.apply(2, 3));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 11 Java11LambdaDemo.java
java Java11LambdaDemo
~~~

Stdout:

~~~text
15
~~~

`offset` là `var` **cục bộ kiểu Java 10**; `a` và `b` là `var` **tham số lambda kiểu Java 11**. Một chương trình có thể dùng cả hai khi biên dịch với Java 11 trở lên. `offset` là *effectively final* nên lambda được phép capture.

Nếu biên dịch chính mã trên bằng `javac --release 10 Java11LambdaDemo.java`, trình biên dịch từ chối `var` trong **tham số lambda** vì khả năng này chưa tồn tại ở Java 10. Kết luận chỉ liên quan đến cú pháp ở vị trí tham số; `var offset = 10;` vẫn là mã Java 10 hợp lệ.

## 4. Vì sao cần `var` ở tham số lambda nếu đã suy luận được kiểu?

Khi không cần annotation hoặc modifier, `text -> text.length()` thường gọn và rõ. Java 11 bổ sung `var` để tham số **vừa được suy luận kiểu, vừa có thể mang annotation hoặc modifier** theo cú pháp khai báo tham số có kiểu. Ví dụ, `(@Tagged var text) -> ...` và `(final var text) -> ...` đều hợp lệ khi annotation `Tagged` được định nghĩa và sử dụng đúng mục tiêu.

Lưu **`VarVsLambdaDemo.java`** để xem cả hai loại `var` trong một chương trình Java 17+:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Function;

public class VarVsLambdaDemo {
    @Target(ElementType.PARAMETER)
    @interface Tagged {}

    public static void main(String[] args) {
        var words = List.of("Java", "var", "lambda");
        var total = words.size();
        System.out.println("local-size=" + total);

        for (var word : words) {
            if (word.length() == 3) {
                System.out.println("local-item=" + word);
            }
        }

        Function<String, Integer> length = (var text) -> text.length();
        System.out.println("len=" + length.apply("Java"));

        BiFunction<Integer, Integer, Integer> add =
                (@Tagged var left, @Tagged var right) -> left + right;
        System.out.println("sum=" + add.apply(2, 5));

        Function<String, String> decorate =
                (final var value) -> "[" + value + "]";
        System.out.println("decorated=" + decorate.apply("ok"));

        Function<String, Integer> bodyLocal = text -> {
            var n = text.length();
            return n * 2;
        };
        System.out.println("body-local=" + bodyLocal.apply("abc"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 VarVsLambdaDemo.java
java VarVsLambdaDemo
~~~

Stdout:

~~~text
local-size=3
local-item=var
len=4
sum=7
decorated=[ok]
body-local=6
~~~

Diễn giải từng nhóm:

1. `words`, `total`, `word` và `n` được suy luận từ initializer hoặc nguồn lặp: **`var` cục bộ** (khả năng có từ Java 10). `n` nằm trong thân lambda nhưng vẫn là biến cục bộ.
2. `text` trong `(var text)`, `left` và `right` trong `(@Tagged var ...)`, và `value` trong `(final var value)` là **tham số lambda** (cú pháp `var` có từ Java 11). Kiểu đến từ `Function` hoặc `BiFunction`.
3. `@Tagged` là annotation minh họa do chương trình khai báo với `@Target(ElementType.PARAMETER)`. Annotation ở tham số không tự tạo kiểm tra null, thay đổi kiểu hoặc thay đổi kết quả chạy.
4. `final var value` minh họa một modifier hợp lệ. Với lambda thông thường, không cần `final` nếu không có lý do rõ ràng; từ khóa này cấm gán lại tham số trong thân lambda.

Ví dụ dùng Java 17 làm mức biên dịch để bảo đảm chạy được trên môi trường Java hiện đại; bản thân cú pháp `var` tham số lambda ở đây đã xuất hiện từ Java 11.

## 5. Các quy tắc không được trộn và các lỗi biên dịch

### Quy tắc thống nhất danh sách tham số

Khi một lambda có nhiều tham số, **không trộn** cách viết `var` với tham số kiểu tường minh hoặc tham số không ghi kiểu. Các đoạn sau **cố ý không hợp lệ** và chỉ dùng để nhận diện lỗi:

~~~java
// BiFunction<Integer, Integer, Integer> bad1 = (var a, Integer b) -> a + b;
// BiFunction<Integer, Integer, Integer> bad2 = (var a, b) -> a + b;
// Function<String, Integer> bad3 = var text -> text.length();
// var bad4 = (var text) -> text.length();
~~~

- `bad1`: không được trộn `var` với kiểu `Integer` tường minh trong cùng danh sách tham số.
- `bad2`: không được trộn tham số có `var` với tham số không ghi kiểu.
- `bad3`: tham số có `var` phải được đặt trong ngoặc đơn.
- `bad4`: biến cục bộ `var` cần một initializer có kiểu xác định, còn lambda đứng riêng cần functional interface làm target type.

Cách sửa tương ứng (đoạn minh họa bên trong phương thức, giả sử đã import `Function` và `BiFunction`):

~~~java
BiFunction<Integer, Integer, Integer> ok1 = (var a, var b) -> a + b;
BiFunction<Integer, Integer, Integer> ok2 = (a, b) -> a + b;
Function<String, Integer> ok3 = (var text) -> text.length();
Function<String, Integer> ok4 = text -> text.length();
~~~

Cũng có thể viết tất cả tham số bằng kiểu tường minh nếu thật sự cần, chẳng hạn `(Integer a, Integer b) -> a + b`.

### Những điểm dễ hiểu nhầm

| Ngộ nhận | Thực tế |
| --- | --- |
| `var` trong lambda có từ Java 10 vì `var` được giới thiệu ở Java 10 | `var` trong **thân lambda** dưới dạng biến cục bộ hợp lệ từ Java 10; `var` trong **danh sách tham số** cần Java 11+ |
| `(var x)` tự suy ra kiểu từ cách sử dụng `x` trong thân lambda, không cần ngữ cảnh | Lambda phải có **target functional interface**; chữ ký interface cung cấp kiểu tham số |
| `var` khiến `x` có thể đổi kiểu khi lambda chạy | Kiểu tĩnh cố định; lỗi kiểu vẫn được bắt lúc biên dịch |
| `var` trong lambda thay cho `var` ở tham số phương thức thông thường | Tham số phương thức thường phải ghi kiểu; ngoại lệ là cú pháp riêng của lambda từ Java 11 |
| Phải dùng `var` trong mọi lambda mới | `x -> ...` hoặc `(x, y) -> ...` vẫn hợp lệ và thường là lựa chọn đơn giản |
| Có thể trộn `var`, kiểu cụ thể và kiểu suy luận trong một lambda | Phải thống nhất cú pháp theo các dạng hợp lệ, không trộn như ví dụ `bad1`/`bad2` |
| `var` tự cho phép lambda capture biến bị gán lại | Capture vẫn yêu cầu biến cục bộ bên ngoài phải là `final` hoặc *effectively final* |

## 6. Chọn cách viết phù hợp trong dự án thực tế

- **Dùng `var` cục bộ** khi biểu thức khởi tạo thể hiện rõ kiểu hoặc kiểu dài gây lặp không cần thiết. Nếu kiểu suy luận bất ngờ, dùng kiểu tường minh để mã dễ đọc hơn.
- **Dùng tham số lambda không ghi kiểu** như `name -> name.trim()` khi ngắn, rõ và không cần annotation hoặc modifier.
- **Dùng `(var name)` ở tham số lambda** khi cần annotation, `final`, hoặc nhất quán theo quy ước của nhóm. Không có lợi ích về hiệu năng chỉ do thêm `var`.
- **Dùng kiểu tham số lambda tường minh** khi nó hỗ trợ đọc hiểu hoặc giải quyết một tình huống mà khai báo suy luận không phù hợp.
- **Kiểm tra mức Java của dự án:** nếu cấu hình ngôn ngữ là Java 10, được dùng `var` cục bộ nhưng phải tránh `(var x) -> ...`; từ Java 11 trở lên, cả hai dạng đều được hỗ trợ. Với codebase Java 17+, các ví dụ của bài vẫn áp dụng.

Một quy tắc nhớ nhanh: **`var` cục bộ đọc kiểu từ giá trị khởi tạo; `var` trong tham số lambda đọc kiểu từ functional interface đích**. Tên giống nhau nhưng vị trí hợp lệ và thời điểm được Java hỗ trợ khác nhau.

## 7. Tự kiểm tra

1. Vì sao `var length = text.length();` trong thân lambda có thể chạy ở Java 10, trong khi `(var text) -> text.length()` phải chờ Java 11?
2. Với `Function<String, Integer> f = (var s) -> s.length();`, kiểu `s` đến từ đâu?
3. Vì sao `(var a, Integer b) -> a + b` không hợp lệ?
4. Cần làm gì để khai báo `var operation = x -> x + 1;` hợp lệ?
5. Annotation hoặc `final` ở tham số lambda có bắt buộc không?

**Đáp án:** (1) `length` là biến cục bộ, còn `text` là tham số lambda; (2) từ tham số kiểu `String` của `Function<String, Integer>`; (3) trộn hai kiểu khai báo tham số; (4) cung cấp kiểu functional interface đích, ví dụ `IntUnaryOperator operation = x -> x + 1;`; (5) không, chúng chỉ dùng khi có nhu cầu cụ thể.
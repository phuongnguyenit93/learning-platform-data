# `var` và `final` trong Java: suy luận kiểu, kiểm soát phép gán

`var` giúp Java **suy luận kiểu của biến cục bộ từ biểu thức khởi tạo**; `final` giúp ràng buộc rằng **một biến chỉ được gán một lần**. Khi kết hợp thành `final var`, ta vừa viết gọn khai báo vừa thể hiện rõ ý định không gán lại biến. Đây đều là cơ chế hiện còn được hỗ trợ trong các phiên bản Java hiện đại.

Bài học thuộc nền tảng Java 10: suy luận kiểu biến cục bộ bằng `var` xuất hiện từ **Java 10**; cú pháp `var` cho tham số lambda được bổ sung từ **Java 11**. Các ví dụ chính tương thích Java 17 trở lên và cũng dùng được trong Java 10, trừ phần lambda được ghi rõ phiên bản.

## 1. `var` suy luận kiểu ở lúc biên dịch

Hai khai báo sau có cùng kiểu biến:

~~~java
String message = "Xin chào";
var greeting = "Xin chào"; // Trình biên dịch suy luận String
~~~

Tại thời điểm biên dịch, Java xác định kiểu tĩnh của `greeting` là `String`. Sau đó, biến chịu các quy tắc kiểm tra kiểu như một biến khai báo tường minh. `var` **không** tạo kiểu động, không biến Java thành JavaScript và không có nghĩa là biến có thể đổi sang kiểu khác trong khi chạy.

~~~java
var count = 10;       // int
count = 12;           // Hợp lệ: vẫn là int
// count = "mười";    // Lỗi biên dịch: String không thể gán cho int

var price = 10.5;     // double
var title = "Java";   // String
var enabled = true;   // boolean
~~~

`var` là tên kiểu bị hạn chế dùng trong một số vị trí cú pháp (restricted type name), không phải kiểu dữ liệu `Var`, và **không** có phép suy luận lại kiểu sau khi biến đã được khai báo.

### Dùng `var` ở đâu?

| Vị trí | Hợp lệ? | Ví dụ/giải thích |
| --- | --- | --- |
| Biến cục bộ có biểu thức khởi tạo | Có, Java 10+ | `var age = 20;` |
| Biến khởi tạo của vòng `for` | Có, Java 10+ | `for (var i = 0; i < 3; i++)` |
| Biến trong vòng `for-each` | Có, Java 10+ | `for (var item : items)` |
| Tài nguyên trong `try-with-resources` | Có, Java 10+ | `try (var reader = Files.newBufferedReader(path))` |
| Tham số lambda | Có, **Java 11+**, theo quy tắc riêng | `(var a, var b) -> a + b` khi có kiểu đích phù hợp |
| Trường (field) của lớp, kể cả `static` | Không | Phải ghi kiểu tường minh |
| Tham số phương thức/constructor, kiểu trả về phương thức | Không | Phải ghi kiểu tường minh |
| Biến cục bộ không có biểu thức khởi tạo | Không | Không có cơ sở suy luận kiểu |

Ví dụ với vòng lặp:

~~~java
for (var i = 0; i < 3; i++) {
    System.out.println(i);
}
// Các dòng in ra: 0, 1, 2
~~~

Cú pháp `var` trong một khai báo cục bộ chỉ đi với **một biến và một biểu thức khởi tạo**. Ví dụ `var a = 1, b = 2;` không hợp lệ; hãy khai báo hai biến riêng.

## 2. `final` ràng buộc điều gì?

Đối với biến, từ khóa `final` có nghĩa là **không thể gán lại biến sau khi nó đã được gán giá trị hợp lệ**. `final` không quyết định kiểu biến; kiểu vẫn có thể khai báo tường minh hoặc suy luận bằng `var`.

~~~java
final int maxRetries = 3;
// maxRetries = 4; // Lỗi biên dịch: không thể gán lại biến final

final var port = 8080; // Java suy luận int, đồng thời cấm gán lại port
// port = 9090;        // Lỗi biên dịch
~~~

Viết đúng là `final var name = expression;`, trong đó `final` là modifier và `var` cho phép suy luận kiểu. Không thể viết `var final name = ...`. Vì `var` cần biểu thức khởi tạo để suy luận kiểu, `final var` cũng phải khởi tạo ngay khi khai báo.

Một biến cục bộ có **kiểu tường minh** có thể khai báo `final` trước rồi gán chính xác một lần theo các nhánh điều khiển hợp lệ:

~~~java
final int result;
if (args.length > 0) {
    result = 1;
} else {
    result = 0;
}
// result = 2; // Không hợp lệ: result đã được gán
~~~

Đoạn trên là **mã minh họa đặt bên trong phương thức có tham số `String[] args`**; không phải chương trình độc lập. Không thể thay `final int result;` bằng `final var result;` vì thiếu biểu thức khởi tạo.

### `final` với tham chiếu đối tượng: không đồng nghĩa bất biến

Khi `final` gắn với biến tham chiếu, Java khóa **việc gán lại tham chiếu**, chứ không tự khóa trạng thái của đối tượng.

~~~java
final var names = new java.util.ArrayList<String>();
names.add("An");                  // Hợp lệ: sửa nội dung đối tượng
names.add("Bình");                // Hợp lệ
// names = new java.util.ArrayList<>(); // Lỗi: gán lại biến final
~~~

Điều tương tự đúng với mảng: `final var numbers = new int[] {1, 2};` vẫn cho phép `numbers[0] = 9;`. Nếu cần một tập hợp không cho thêm/xóa/thay phần tử qua API của nó, hãy chọn cấu trúc phù hợp, ví dụ `List.of("An", "Bình")`; tính không sửa đổi của danh sách đến từ API `List.of`, **không** đến từ `final`. `final` một mình cũng không bảo đảm tính bất biến sâu hay an toàn luồng.

`final` còn dùng được với field, tham số phương thức, phương thức và lớp, nhưng ý nghĩa theo ngữ cảnh khác nhau: field `final` chỉ được gán theo quy tắc khởi tạo của field; phương thức `final` không thể bị override; lớp `final` không thể bị kế thừa. Trọng tâm của `final var` ở bài này là **biến cục bộ**.

## 3. Chương trình đầy đủ: kết hợp `var`, `final var` và `for-each`

Lưu mã sau vào tệp **`VarFinalDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class VarFinalDemo {
    public static void main(String[] args) {
        var total = 10;                      // int
        total += 5;                          // var không ngăn gán lại
        final var limit = 20;                // int, không thể gán lại

        final var names = new ArrayList<String>();
        names.add("An");
        names.add("Bình");                   // final không khóa nội dung List

        var numbers = List.of(1, 2, 3);      // List<Integer>
        var sum = 0;
        for (final var number : numbers) {   // number không gán lại trong lượt lặp
            sum += number;
        }

        System.out.println("total=" + total);
        System.out.println("limit=" + limit);
        System.out.println("names=" + names);
        System.out.println("sum=" + sum);
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 17+:

~~~bash
javac VarFinalDemo.java
java VarFinalDemo
~~~

Kết quả chuẩn:

~~~text
total=15
limit=20
names=[An, Bình]
sum=6
~~~

Giải thích: `total` được suy luận là `int` nên tăng từ 10 lên 15; `limit` cũng là `int` nhưng `final` cấm gán lại. `names` có kiểu suy luận `ArrayList<String>` và tham chiếu của nó là `final`, song gọi `add` vẫn làm danh sách thay đổi. `numbers` được suy luận là `List<Integer>`; từng `number` là một biến `final` riêng cho mỗi lượt lặp, còn `sum` là biến thường nên được cộng dồn.

## 4. Những trường hợp suy luận kiểu cần để ý

### Kiểu đến từ biểu thức bên phải, không đến từ ý định của người viết

~~~java
var index = 1;          // int, không tự chuyển thành long
var ratio = 1.0;        // double
var text = "hello";     // String

// index = 2L;          // Lỗi biên dịch: long không gán cho int nếu không chuyển kiểu
~~~

Biểu thức bên phải có thể là lời gọi phương thức. Khi đó, trình biên dịch dựa trên **kiểu trả về được khai báo của phương thức** và các quy tắc suy luận generic; nó không đợi đến lúc chạy để đoán kiểu đối tượng.

### Dùng toán tử diamond `<>` cẩn thận

~~~java
var items = new java.util.ArrayList<String>();
// Kiểu của items: ArrayList<String>

var unknown = new java.util.ArrayList<>();
// Kiểu của unknown: ArrayList<Object> trong ngữ cảnh này

java.util.List<String> names = new java.util.ArrayList<>();
// Kiểu biến names: List<String>, theo kiểu tường minh bên trái
~~~

Khi viết `var unknown = new ArrayList<>();`, không có thông tin kiểu phần tử bên trái để suy luận `String`. Nếu ý định là `String`, hãy viết rõ `new ArrayList<String>()` hoặc dùng kiểu khai báo tường minh. Cũng cần phân biệt kiểu triển khai với kiểu giao diện: `var items = new ArrayList<String>()` cho biến kiểu `ArrayList<String>`; nếu hợp đồng lập trình mong đợi `List<String>`, khai báo `List<String> items = new ArrayList<>();` làm ý định rõ hơn.

### Các khai báo không hợp lệ

Các dòng sau là **ví dụ lỗi biên dịch có chủ đích**, không ghép vào chương trình chạy:

~~~java
// var missing;                 // Thiếu biểu thức khởi tạo
// var unknown = null;          // Không thể suy luận kiểu chỉ từ null
// var data = {1, 2, 3};        // Cần new int[] {1, 2, 3}
// var a = 1, b = 2;            // Không khai báo nhiều biến bằng một var
// final var late;              // final var vẫn phải khởi tạo ngay
// var action = () -> 42;       // Lambda cần kiểu đích (functional interface)
~~~

Với mảng, cách đúng là `var data = new int[] {1, 2, 3};`. Với lambda, có thể viết `java.util.function.Supplier<Integer> action = () -> 42;` để cung cấp kiểu đích. Các hạn chế này vẫn có ý nghĩa trong Java hiện đại.

## 5. `var` trong lambda và quy tắc `effectively final`

Từ **Java 11**, tham số lambda được phép khai báo bằng `var` nếu lambda có kiểu đích phù hợp. Khi viết kiểu `var` tường minh cho các tham số, phải dùng `var` nhất quán cho **tất cả** tham số của lambda; không trộn `(var a, b)`.

~~~java
// Đoạn minh họa Java 11+; đặt trong phương thức và import BiFunction.
java.util.function.BiFunction<String, String, String> join =
        (var first, var second) -> first + " " + second;

System.out.println(join.apply("Xin", "chào")); // Xin chào
~~~

`final` cũng liên quan đến lambda theo một quy tắc quan trọng: biến cục bộ được lambda sử dụng từ phạm vi bên ngoài phải là **final hoặc effectively final**. *Effectively final* nghĩa là biến không mang từ khóa `final` nhưng trên thực tế không bị gán lại sau lần khởi tạo.

~~~java
// Đoạn minh họa; đặt trong phương thức.
var prefix = "Chào ";
java.util.List.of("An", "Bình")
        .forEach(name -> System.out.println(prefix + name));

// prefix = "Xin chào "; // Nếu thêm phép gán này, đoạn lambda không biên dịch
~~~

Nếu muốn thể hiện cam kết đó ngay trong mã, hãy viết `final var prefix = "Chào ";`. Dù là `var` hay `final var`, lambda không làm kiểu của `prefix` thay đổi.

## 6. Khi nào nên dùng kiểu tường minh, `var` hoặc `final var`?

| Tình huống | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Biểu thức khởi tạo đã nêu rõ kiểu, tên biến có ý nghĩa | `var service = new PaymentService();` | Tránh lặp tên kiểu khi mục đích rõ |
| Biến cục bộ không cần gán lại | `final var timeout = Duration.ofSeconds(5);` | Ngắn gọn và ràng buộc phép gán |
| Muốn lập trình theo giao diện trừu tượng | `List<String> users = new ArrayList<>();` | Giữ rõ hợp đồng `List<String>` |
| Biểu thức trả về phức tạp, kiểu suy luận khó đoán | Kiểu tường minh | Người đọc thấy được ý định mà không cần lần theo API |
| Field, chữ ký phương thức, tham số thông thường | Kiểu tường minh | `var` không hợp lệ ở các vị trí này |
| Giá trị có thể thay đổi qua các bước tính toán | `var total = 0;` hoặc `int total = 0;` | Không nên dùng `final` nếu cần gán lại |

Đừng chọn `var` chỉ để làm mã ngắn hơn: **khả năng đọc được kiểu và ý nghĩa biến quan trọng hơn số ký tự tiết kiệm**. `final var` có ích khi bạn thực sự muốn cố định phép gán; đừng dùng nó như một lời hứa rằng toàn bộ đối tượng bất biến.

## 7. Tự kiểm tra nhanh

Xét các khai báo sau, hãy xác định kiểu của biến và khả năng gán lại:

~~~java
var a = 100L;
final var b = "Java";
var c = new java.util.ArrayList<Integer>();
final var d = new int[] {2, 4};
~~~

Đáp án:

1. `a` có kiểu `long`, được phép gán lại bằng giá trị tương thích `long`.
2. `b` có kiểu `String`, không thể gán lại. Bản thân `String` cũng là kiểu đối tượng bất biến.
3. `c` có kiểu `ArrayList<Integer>`; có thể gán lại tham chiếu và thêm/xóa phần tử nếu API cho phép.
4. `d` có kiểu `int[]`; không thể gán lại tham chiếu, nhưng có thể sửa phần tử như `d[0] = 8;`.

Ghi nhớ: **`var` quyết định cách khai báo kiểu tĩnh; `final` quyết định có được gán lại biến hay không.** Kết hợp hai từ này không thay đổi quy tắc kiểu của Java và không tự tạo bất biến cho đối tượng.

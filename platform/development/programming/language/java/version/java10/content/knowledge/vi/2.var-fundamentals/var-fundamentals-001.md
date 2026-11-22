# Suy luận kiểu biến cục bộ và mục đích của `var` (Java 10+)

## 1. `var` là gì và giải quyết vấn đề nào?

Từ Java 10, ta có thể dùng `var` trong **khai báo biến cục bộ** để trình biên dịch tự xác định kiểu của biến dựa trên **biểu thức khởi tạo** ở bên phải dấu `=`. Tính năng này gọi là *local-variable type inference* (suy luận kiểu biến cục bộ).

Ví dụ, hai cách khai báo sau có cùng kiểu biến là `ArrayList<String>`:

```java
ArrayList<String> names1 = new ArrayList<String>();
var names2 = new ArrayList<String>();
```

Với `names2`, trình biên dịch thấy biểu thức `new ArrayList<String>()` có kiểu `ArrayList<String>` và dùng chính kiểu đó cho biến. Mục tiêu của `var` là **giảm phần lặp lại không cần thiết, giúp người đọc chú ý vào tên biến và giá trị khởi tạo**, nhất là khi kiểu đã rõ ngay ở dòng khai báo.

Điểm cốt lõi: Java **vẫn là ngôn ngữ kiểm tra kiểu tĩnh**. `var` không phải một kiểu dữ liệu mới, không biến Java thành ngôn ngữ kiểu động và không làm biến có thể tự đổi kiểu sau này. Kiểu được quyết định **lúc biên dịch**; trình biên dịch vẫn kiểm tra phép gán, gọi phương thức và các ràng buộc kiểu như khi ta viết kiểu tường minh.

`var` là **tên kiểu bị hạn chế (*restricted type name*)**, không phải từ khóa dành riêng hoàn toàn (*reserved keyword*). Vì thế, đừng hiểu nó như một đối tượng hay lớp có tên `var`: nó chỉ là cú pháp yêu cầu suy luận kiểu ở các vị trí hợp lệ.

## 2. Cách trình biên dịch xác định kiểu

Quy tắc thực hành: trong `var tenBien = bieuThuc;`, hãy nhìn **kiểu tĩnh của biểu thức khởi tạo**. Trình biên dịch suy ra một kiểu cụ thể, không đoán theo ý nghĩa tên biến và cũng không chờ xem những giá trị được gán sau đó.

| Khai báo | Kiểu tĩnh được suy ra | Ý nghĩa |
| --- | --- | --- |
| `var count = 10;` | `int` | Literal số nguyên mặc định có kiểu `int` nếu nằm trong phạm vi của `int`. |
| `var total = 10L;` | `long` | Hậu tố `L` làm literal có kiểu `long`. |
| `var rate = 2.5;` | `double` | Literal số thực mặc định là `double`. |
| `var active = true;` | `boolean` | Kiểu suy ra từ literal Boolean. |
| `var label = "Java";` | `String` | Kiểu suy ra từ literal chuỗi. |
| `var codes = new int[] {1, 2};` | `int[]` | Biểu thức tạo mảng cung cấp kiểu rõ ràng. |
| `var words = List.of("a", "b");` | `List<String>` | Kiểu trả về tĩnh của lời gọi `List.of`. |
| `var names = new ArrayList<String>();` | `ArrayList<String>` | Kiểu cụ thể của biểu thức `new`. |

Trong bảng, `List` và `ArrayList` là các kiểu trong `java.util`. Bảng diễn tả kiểu tĩnh của từng khai báo độc lập; không yêu cầu chạy chương trình.

Sau khi suy luận, việc kiểm tra kiểu diễn ra bình thường:

```java
var quantity = 5;  // quantity có kiểu int
quantity = 8;      // Hợp lệ: int -> int
// quantity = "8"; // Lỗi biên dịch: String không thể gán cho int
// quantity = 8L;  // Lỗi biên dịch: long không thể gán cho int nếu không ép kiểu
```

Với kiểu tham chiếu, giá trị vẫn có thể là `null` **sau khi** kiểu đã được xác định:

```java
var message = "Xin chao"; // message có kiểu String
message = null;           // Hợp lệ về mặt kiểu, nhưng phải xét nguy cơ NullPointerException
```

Ngược lại, `var message = null;` không hợp lệ: riêng literal `null` không cung cấp kiểu để suy luận.

### Kiểu tĩnh không nhất thiết là kiểu của đối tượng lúc chạy

`var` dựa vào **kiểu khai báo/trả về tĩnh của biểu thức**, chứ không tự chọn lớp con cụ thể đang nằm trong biến:

```java
List<String> source = new ArrayList<>();
var copy = source; // copy có kiểu List<String>, không phải ArrayList<String>
```

Nếu viết `var list = new ArrayList<String>();` thì `list` được suy ra là `ArrayList<String>`, không tự động “nâng” thành giao diện `List<String>`. Khi muốn thể hiện rõ hợp đồng lập trình với giao diện, hãy khai báo tường minh `List<String> list = new ArrayList<>();`.

## 3. Các vị trí dùng `var` trong khai báo biến cục bộ

### 3.1. Biến trong khối lệnh

Có thể dùng trong thân phương thức, constructor hoặc khối khởi tạo, miễn là có biểu thức khởi tạo hợp lệ:

```java
var userName = "An";                   // String
var scores = List.of(8, 9, 10);        // List<Integer>
var average = 9.0;                     // double
```

Tên biến nên mang ý nghĩa rõ ràng. `var result = compute();` có thể khó đọc nếu không biết `compute()` trả về gì; `var scores = List.of(8, 9, 10);` rõ hơn nhiều nhờ biểu thức bên phải.

### 3.2. Vòng lặp `for` thông thường

```java
for (var index = 0; index < 3; index++) {
    System.out.println(index);
}
```

`index` có kiểu `int`. Đây là trường hợp kiểu đã quá rõ, nên `var` thường làm cú pháp gọn hơn.

### 3.3. Vòng lặp `for-each`

```java
List<String> languages = List.of("Java", "Kotlin");
for (var language : languages) {
    System.out.println(language);
}
```

`language` có kiểu `String` vì phần tử của `languages` có kiểu `String`. Ở `for-each`, kiểu phần tử được suy ra từ mảng/`Iterable`, không cần viết biểu thức khởi tạo `= ...` riêng cho biến vòng lặp.

### 3.4. Biến tài nguyên của `try-with-resources`

```java
try (var reader = new java.io.StringReader("OK")) {
    System.out.println((char) reader.read());
}
```

`reader` có kiểu `StringReader`; tài nguyên vẫn phải thỏa điều kiện `AutoCloseable` của `try-with-resources` và vẫn được đóng tự động khi rời khối.

### 3.5. Kết hợp `final`

```java
final var maxRetries = 3;  // int, không thể gán lại maxRetries
```

`final` với `var` mang **đúng ý nghĩa thông thường của `final`**: không thể gán lại biến. Nếu biến chứa tham chiếu tới đối tượng có thể thay đổi, `final` không tự làm trạng thái bên trong đối tượng trở thành bất biến.

## 4. Những trường hợp không hợp lệ và cách sửa

Các ví dụ dưới đây **cố ý không biên dịch**, dùng để nhận diện lỗi cú pháp/kiểu:

```java
// var a;                          // Thiếu biểu thức khởi tạo
// var n = null;                   // Không suy ra được kiểu từ null
// var x = 1, y = 2;               // Một khai báo var không được khai báo nhiều biến
// var items = {1, 2, 3};          // Array initializer cần kiểu đích
// var numbers[] = new int[3];     // Không đặt [] sau tên biến khai báo bằng var
// var self = self + 1;            // Không tự tham chiếu biến trong initializer
// var operation = s -> s.trim();  // Lambda cần kiểu đích (target type)
// var length = String::length;    // Method reference cũng cần kiểu đích
```

Cách viết hợp lệ tương ứng:

```java
int a;                            // Khai báo tường minh, gán giá trị trước khi sử dụng
String n = null;                  // Có kiểu khai báo tường minh
var x = 1;
var y = 2;
var items = new int[] {1, 2, 3};
var numbers = new int[3];
var self = 1;                     // Khởi tạo từ giá trị đã xác định
java.util.function.Function<String, String> operation = s -> s.trim();
java.util.function.Function<String, Integer> length = String::length;
```

**Không dùng `var` làm kiểu của field, tham số phương thức/constructor hoặc kiểu trả về của phương thức:**

```java
class InvalidExamples {
    // var age = 20;                    // Sai: field
    // void update(var value) {}         // Sai: tham số phương thức
    // var getAge() { return 20; }       // Sai: kiểu trả về
}
```

Tại những vị trí mô tả hợp đồng của lớp/phương thức, Java cần kiểu được khai báo tường minh. Riêng **tham số lambda** có một cú pháp `var` được bổ sung từ **Java 11** và vẫn hợp lệ trong Java hiện nay, ví dụ:

```java
java.util.function.BiFunction<Integer, Integer, Integer> add =
        (var left, var right) -> left + right;
```

Trong một danh sách tham số lambda, không được trộn `var` với tham số không ghi kiểu hoặc với kiểu khai báo tường minh: `(var a, b) -> ...` và `(var a, int b) -> ...` đều sai. Đây là mở rộng cho cú pháp lambda, **khác** với chủ đề `var` của biến cục bộ xuất hiện từ Java 10.

## 5. Những bẫy thường gặp khi suy luận kiểu

### 5.1. Diamond `<>` thiếu ngữ cảnh kiểu

```java
var values = new ArrayList<>(); // ArrayList<Object>, KHÔNG phải ArrayList<String>
values.add("Java");
values.add(42);                 // Cũng hợp lệ vì phần tử có kiểu Object
```

Khi cần danh sách chuỗi, hãy cung cấp đủ thông tin về phần tử:

```java
var values = new ArrayList<String>(); // ArrayList<String>
// Hoặc ưu tiên thể hiện hợp đồng giao diện:
List<String> strings = new ArrayList<>();
```

Tên biến `values` hay `strings` không tham gia vào thuật toán suy luận kiểu. `var` cũng không suy ra tham số generic từ các lệnh `add` xuất hiện **sau** khai báo.

### 5.2. Literal số quyết định kiểu ngay từ đầu

```java
var timeout = 1000;    // int
var largeTimeout = 1000L; // long
var ratio = 1.0;       // double
```

Nếu cần `long`, hãy dùng hậu tố `L` hoặc khai báo `long` ngay từ đầu. Không nên trông đợi phép gán về sau khiến biến đổi kiểu.

### 5.3. Kiểu cụ thể có thể làm mất ý đồ thiết kế

```java
var items = new ArrayList<String>(); // Kiểu tĩnh là ArrayList<String>
List<String> itemsByContract = new ArrayList<>(); // Kiểu tĩnh là List<String>
```

Cả hai cùng tạo `ArrayList`, nhưng dòng thứ hai nói rõ người dùng biến chỉ cần hợp đồng `List`. Điều này hữu ích khi muốn mã phụ thuộc vào giao diện thay vì lớp triển khai.

### 5.4. `var` không làm giá trị thành “bất kỳ kiểu gì”

```java
var name = "An";  // String
// name = 123;    // Lỗi biên dịch: int không thể gán cho String
```

Kiểu vẫn cố định; `var` cũng không thêm khả năng chuyển kiểu tự động hay chi phí xử lý kiểu động khi chạy.

### 5.5. `var` có thể giảm tính dễ đọc

So sánh hai khai báo:

```java
var customer = repository.findById(id);
Customer customer = repository.findById(id);
```

Đây là **đoạn mã minh họa** (giả định có `repository`, `id` và kiểu `Customer`). Nếu người đọc không biết kiểu trả về của `findById`, dòng thứ hai dễ hiểu hơn. Hãy ưu tiên tính rõ ràng thay vì bắt buộc dùng `var` ở mọi nơi.

## 6. Ví dụ đầy đủ, chạy được với Java 17+

Lưu toàn bộ chương trình sau vào tệp **`VarBasicsDemo.java`**. Chương trình dùng `var` cho kiểu chuỗi, số, danh sách, biến vòng lặp, tài nguyên và `final`.

```java
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;

public class VarBasicsDemo {
    public static void main(String[] args) throws Exception {
        var title = "Java";                  // String
        var count = 2;                       // int
        var score = 4.5;                     // double
        var tags = List.of("var", "typing");  // List<String>

        var names = new ArrayList<String>(); // ArrayList<String>
        names.add("An");
        names.add("Binh");

        System.out.println(title + " " + count);
        System.out.println(score);
        System.out.println(tags.get(0));

        for (var name : names) {             // String
            System.out.println(name);
        }

        for (var index = 0; index < count; index++) { // int
            System.out.println("index=" + index);
        }

        try (var reader = new StringReader("OK")) {    // StringReader
            System.out.println((char) reader.read());
        }

        final var limit = 3;                 // int và final
        System.out.println(limit);
    }
}
```

Biên dịch và chạy (JDK 17 hoặc mới hơn):

```bash
javac -encoding UTF-8 VarBasicsDemo.java
java VarBasicsDemo
```

Kết quả chính xác:

```text
Java 2
4.5
var
An
Binh
index=0
index=1
O
3
```

Giải thích: `title` có kiểu `String` nên nối với `count` thành `Java 2`; `tags.get(0)` là `"var"`; vòng `for-each` in hai tên; vòng `for` thường in hai chỉ số; `reader.read()` đọc ký tự đầu `'O'`, được ép từ giá trị mã ký tự thành `char`; `limit` là biến `final int`.

## 7. Khi nào nên dùng `var`, khi nào nên ghi kiểu?

Dùng `var` khi **biểu thức khởi tạo nói rõ kiểu** và biến có phạm vi ngắn, ví dụ `var index = 0;`, `var path = Path.of("input.txt");` hay `var names = new ArrayList<String>();`. Trong các trường hợp này, việc lặp tên kiểu ít thêm thông tin.

Ưu tiên kiểu tường minh khi người đọc khó nhận ra kiểu từ biểu thức, khi kiểu là một phần quan trọng của thiết kế (đặc biệt `interface` so với lớp triển khai), khi literal số dễ gây nhầm (`int`/`long`/`double`), hoặc khi giá trị có thể là `null`. Ví dụ `List<String> names = new ArrayList<>();` thể hiện rõ hợp đồng `List`, còn `var names = new ArrayList<>();` lại suy ra `ArrayList<Object>`.

Có thể tự kiểm tra nhanh bằng ba câu hỏi:

1. **Tôi có xác định ngay được kiểu tĩnh của vế phải không?** Nếu không, ghi kiểu tường minh.
2. **Kiểu suy ra có đúng ý định không?** Chú ý literal số, generics và việc suy ra lớp triển khai.
3. **Dùng `var` có làm đoạn mã dễ đọc hơn không?** Nếu chỉ tiết kiệm vài ký tự nhưng che mất thông tin quan trọng, không cần dùng.

## 8. Tự kiểm tra kiến thức

**Câu 1.** `var price = 19.5;` tạo biến kiểu gì? Có thể gán `price = "19.5";` không?  
**Đáp án:** `double`; không, vì `String` không thể gán cho `double`.

**Câu 2.** Vì sao `var names = new ArrayList<>();` dễ gây lỗi thiết kế?  
**Đáp án:** Khi không có ngữ cảnh kiểu phần tử, `<>` ở đây suy ra `Object`, nên biến có kiểu `ArrayList<Object>`. Hãy chỉ rõ `new ArrayList<String>()` hoặc khai báo `List<String> names = new ArrayList<>();` nếu cần danh sách chuỗi.

**Câu 3.** `var text = null;` và `var text = "Hi"; text = null;` khác nhau ở đâu?  
**Đáp án:** Trường hợp đầu không có kiểu khởi tạo để suy luận nên lỗi biên dịch; trường hợp sau suy ra `String` trước, rồi phép gán `null` hợp lệ với kiểu tham chiếu `String`.

## 9. Ghi nhớ

- `var` suy luận **kiểu tĩnh từ biểu thức khởi tạo**, ngay tại lúc biên dịch.
- Lợi ích chính là loại thông tin kiểu lặp lại và giữ mã cục bộ dễ đọc.
- Trong phạm vi biến cục bộ, `var` dùng được ở khối lệnh, biến của vòng lặp và biến tài nguyên `try-with-resources`; không thay thế kiểu của field, tham số phương thức hay kiểu trả về.
- Không khởi tạo `var` trực tiếp bằng `null`, lambda, method reference hoặc array initializer trần; không khai báo nhiều biến trong cùng một khai báo `var`.
- Chọn giữa `var` và kiểu tường minh dựa trên **độ rõ ràng của kiểu suy ra và ý đồ thiết kế**.

## Nguồn tham khảo chính thức

- OpenJDK, JEP 286 — Local-Variable Type Inference: https://openjdk.org/jeps/286
- Java Language Specification, `14.4 — Local Variable Declarations: https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4
- Dev.java — Using the Var Type Identifier: https://dev.java/learn/language-basics/using-var/
- OpenJDK, JEP 323 — Local-Variable Syntax for Lambda Parameters (Java 11): https://openjdk.org/jeps/323

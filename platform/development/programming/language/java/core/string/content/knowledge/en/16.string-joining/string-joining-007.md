# So sánh String.join(), StringJoiner, StringBuilder và phép nối `+` trong Java

## 1. Bốn cách ghép chuỗi giải quyết những nhu cầu khác nhau

Trong Java, `String` là **bất biến (immutable)**: sau khi một chuỗi được tạo, nội dung của nó không thay đổi. Việc ghép chuỗi tạo ra giá trị `String` mới; cách tổ chức thao tác ghép sẽ ảnh hưởng đến mức độ rõ ràng, khả năng kiểm soát dấu phân cách và lượng công việc khi ghép nhiều phần.

- **Phép `+`**: diễn đạt phép nối trực tiếp, rất tiện cho một biểu thức ngắn hoặc một vài thành phần cố định.
- **`String.join()`**: ghép một dãy phần tử bằng **cùng một delimiter**; phù hợp khi đã có mảng hoặc `Iterable` và chỉ cần chuỗi kết quả.
- **`StringJoiner`**: tích lũy các phần tử với delimiter và hỗ trợ **prefix/suffix**, giá trị khi rỗng và `merge()`; phù hợp khi thêm từng phần tử theo thời gian.
- **`StringBuilder`**: bộ đệm ký tự có thể thay đổi, cho phép `append()`, `insert()`, `delete()`, `replace()` và tự xây dựng quy tắc định dạng; phù hợp khi ghép trong vòng lặp hoặc cần kiểm soát chi tiết.

Ví dụ cùng dữ liệu `["Java", "Spring", "SQL"]`:

~~~java
String a = "Java" + " | " + "Spring" + " | " + "SQL";
String b = String.join(" | ", "Java", "Spring", "SQL");

StringJoiner joiner = new StringJoiner(" | ", "[", "]");
joiner.add("Java").add("Spring").add("SQL");
String c = joiner.toString(); // [Java | Spring | SQL]

StringBuilder builder = new StringBuilder();
builder.append("Java").append(" | ").append("Spring").append(" | ").append("SQL");
String d = builder.toString();
~~~

`a`, `b` và `d` có cùng nội dung `Java | Spring | SQL`. `c` khác vì được yêu cầu thêm ngoặc vuông. Các cách này không phải bốn kiểu dữ liệu tương đương: `+` là toán tử; `String.join()` trả về `String`; `StringJoiner` và `StringBuilder` là các đối tượng giữ trạng thái trong quá trình tạo kết quả.

## 2. Phép nối `+`: rõ ràng cho biểu thức ngắn

Khi **một toán hạng là `String`**, toán tử `+` thực hiện nối chuỗi. Các toán hạng còn lại được chuyển thành biểu diễn chuỗi theo quy tắc chuyển đổi chuỗi của Java. Với các hằng chuỗi, trình biên dịch có thể gộp ngay khi biên dịch (constant folding):

~~~java
String fixed = "Hello" + " " + "Java"; // Hằng "Hello Java"
String name = "Lan";
String greeting = "Hello, " + name + "!"; // Ghép lúc chạy
~~~

Cần phân biệt phép cộng số và phép nối chuỗi, vì biểu thức được đánh giá từ trái sang phải:

~~~java
System.out.println(1 + 2 + " người"); // 3 người
System.out.println("Số người: " + 1 + 2); // Số người: 12
System.out.println("Số người: " + (1 + 2)); // Số người: 3
~~~

**Không kết luận rằng mỗi dấu `+` luôn tạo một `StringBuilder` riêng hoặc luôn chậm.** Trình biên dịch/JVM tối ưu phép ghép một biểu thức; từ Java 9, các biểu thức nối chuỗi thông thường thường dùng cơ chế `invokedynamic` với `StringConcatFactory`. Chi tiết thực thi phụ thuộc trình biên dịch và JVM. Vì vậy, viết `"Xin chào " + name` là hợp lý và dễ đọc.

Điểm cần tránh là **cập nhật chuỗi đang lớn lên trong vòng lặp**:

~~~java
String result = "";
for (String item : items) {
    result += item;
}
~~~

Mỗi lần cập nhật về mặt ngữ nghĩa cần một giá trị `String` mới để lưu kết quả dài hơn; việc lặp lại sao chép phần đã ghép có thể gây nhiều cấp phát và tổng công việc gần bậc hai khi số lượng/độ dài phần tử tăng. Với khối lượng đủ lớn, `StringBuilder` phù hợp hơn. Đây là hướng dẫn về mẫu sử dụng, không phải khẳng định mọi `+` đều kém hiệu năng trong mọi JVM.

Ngoài ra, Java ghép giá trị `null` vào chuỗi thành chữ `"null"` (ví dụ `"x=" + (Object) null` thành `x=null`). Nếu muốn bỏ qua hoặc thay giá trị vắng mặt, hãy xử lý `null` trước.

## 3. `String.join()`: ghép một tập phần tử với delimiter chung

Các overload phổ biến:

~~~java
String.join(CharSequence delimiter, CharSequence... elements)
String.join(CharSequence delimiter, Iterable<? extends CharSequence> elements)
~~~

Ví dụ:

~~~java
String csvLike = String.join(",", "A", "B", "C");
// A,B,C

List<String> paths = List.of("users", "42", "orders");
String path = String.join("/", paths);
// users/42/orders

String empty = String.join(", ", List.<String>of());
// "" (chuỗi rỗng)
~~~

`String.join()` **không tự thêm delimiter ở đầu hoặc cuối** và **không tự lọc phần tử rỗng hay null**. Delimiter chỉ được đặt *giữa* các phần tử:

~~~java
System.out.println(String.join("-", "A", "", "C"));    // A--C
System.out.println(String.join(",", "A", null, "C")); // A,null,C
~~~

Những quy tắc quan trọng:

- Delimiter `null` gây `NullPointerException`; đối số mảng/`Iterable` chứa danh sách phần tử cũng phải là tham chiếu hợp lệ.
- Một **phần tử** `null` được biểu diễn bằng chuỗi `"null"`, chứ không tự biến mất.
- Một dãy có 0 phần tử cho kết quả `""`. Một dãy có một phần tử cho đúng biểu diễn phần tử đó, không có delimiter.
- Phương thức trả về một `String` mới; không làm thay đổi mảng/danh sách đầu vào.
- Tên `csvLike` ở ví dụ chỉ mô tả dấu phẩy: đây **không phải bộ ghi CSV chuẩn**, vì `String.join()` không quote/escape dấu phẩy, dấu nháy hay xuống dòng nằm trong dữ liệu.

Nếu cần loại bỏ chuỗi trắng/null trước khi nối, hãy chuẩn hóa đầu vào. Ví dụ với Stream:

~~~java
List<String> raw = Arrays.asList("Java", null, " ", "Spring");
String result = raw.stream()
        .filter(s -> s != null && !s.isBlank())
        .collect(Collectors.joining(", "));
// Java, Spring
~~~

`Collectors.joining()` thích hợp khi dữ liệu đã đi qua chuỗi thao tác `Stream` (lọc, ánh xạ, sắp xếp). Còn với một mảng hoặc `List` đã sẵn sàng, `String.join()` thường là lựa chọn ít mã nhất.

## 4. `StringJoiner`: thêm từng phần tử, tự quản lý dấu phân cách

`StringJoiner` thuộc `java.util`. Có hai constructor:

~~~java
new StringJoiner(delimiter)
new StringJoiner(delimiter, prefix, suffix)
~~~

Ví dụ:

~~~java
StringJoiner j = new StringJoiner(", ", "[", "]");
j.add("red");
j.add("green");
j.add("blue");
System.out.println(j); // [red, green, blue]
~~~

`StringJoiner` thêm delimiter **giữa các lần `add()`**; người viết không phải kiểm tra xem đây có phải phần tử đầu tiên. `add()` trả về chính joiner để có thể gọi nối tiếp. `toString()` tạo ra chuỗi kết quả ở trạng thái hiện tại; các lần `add()` tiếp theo vẫn làm thay đổi joiner.

### 4.1. Khi chưa có phần tử và `setEmptyValue()`

Với prefix và suffix, khi chưa `add()`, biểu diễn mặc định là `prefix + suffix`. Có thể thay bằng `setEmptyValue()`:

~~~java
StringJoiner j = new StringJoiner(", ", "[", "]");
System.out.println(j); // []

j.setEmptyValue("(không có phần tử)");
System.out.println(j); // (không có phần tử)

j.add("A");
System.out.println(j); // [A]
~~~

`setEmptyValue()` chỉ ảnh hưởng **trạng thái chưa được thêm phần tử**. Sau khi `add()`, kể cả `add("")`, joiner không còn được xem là chưa thêm phần tử.

### 4.2. `merge()` khi kết hợp các nhóm

`merge(other)` thêm nội dung các phần tử của `other` như một nhóm, dùng delimiter của joiner đích ở ranh giới. Prefix/suffix của `other` không được chèn nguyên vào kết quả:

~~~java
StringJoiner left = new StringJoiner(" | ", "<", ">");
left.add("A").add("B");

StringJoiner right = new StringJoiner(", ", "(", ")");
right.add("C").add("D");

left.merge(right);
System.out.println(left); // <A | B | C, D>
System.out.println(right); // (C, D)
~~~

Trong phần nội dung nhóm nguồn, dấu `", "` được giữ nguyên; vì vậy kết quả có dấu cách sau dấu phẩy. `merge()` không xóa dữ liệu của `right`; joiner nguồn vẫn sử dụng được.

Khi sử dụng `merge()`, cần hiểu delimiter bên trong nhóm nguồn và delimiter phân nhóm của đích có thể khác nhau. Đừng giả định merge sẽ đổi mọi dấu phân cách của nguồn thành dấu phân cách đích.

### 4.3. Những giới hạn cần nhớ

- `StringJoiner` tập trung vào `add()`, delimiter, prefix/suffix, empty value và merge; nó **không phải trình sửa ký tự tùy ý** như `StringBuilder`.
- Gọi `add(null)` thêm chữ `"null"`; `null` không tự bị loại bỏ.
- `length()` trả về độ dài biểu diễn hiện tại (bao gồm prefix/suffix nếu có), không phải số phần tử đã thêm.
- Nếu bài toán chỉ là `String.join(", ", list)`, tạo joiner thủ công có thể khiến mã dài thêm không cần thiết.

## 5. `StringBuilder`: kiểm soát từng thao tác tạo chuỗi

`StringBuilder` thuộc `java.lang`, chứa một dãy ký tự có thể thay đổi. `append()` có nhiều overload cho chuỗi, số, boolean, ký tự, mảng ký tự và đối tượng. Nó không tự biết cần đặt delimiter ở đâu:

~~~java
List<String> names = List.of("An", "Bình", "Chi");
StringBuilder sb = new StringBuilder();

for (String name : names) {
    if (sb.length() > 0) {
        sb.append(", ");
    }
    sb.append(name);
}

String output = sb.toString(); // An, Bình, Chi
~~~

Mẫu trên đúng khi không có phần tử rỗng. Nếu phần tử có thể là `""`, dùng chỉ số hoặc biến `first` sẽ an toàn hơn cho mục đích đếm phần tử, vì `sb.length() == 0` không đồng nghĩa “chưa xử lý phần tử nào”:

~~~java
StringBuilder sb = new StringBuilder();
boolean first = true;

for (String item : List.of("", "B")) {
    if (!first) {
        sb.append("|");
    }
    sb.append(item);
    first = false;
}
System.out.println(sb); // |B
~~~

Trường hợp này `String.join("|", List.of("", "B"))` cũng trả `"|B"` và ngắn hơn; mẫu `StringBuilder` hữu ích khi mỗi phần tử còn cần định dạng hoặc thao tác bổ sung.

Các thao tác bổ sung mà `String.join()`/`StringJoiner` không trực tiếp cung cấp:

~~~java
StringBuilder sb = new StringBuilder("abc");
sb.append("de");          // abcde
sb.insert(3, "-");        // abc-de
sb.replace(0, 3, "XYZ");  // XYZ-de
sb.deleteCharAt(3);       // XYZde
sb.reverse();             // edZYX
String result = sb.toString();
~~~

Phân biệt:

- `length()` là số ký tự hiện có.
- `capacity()` là dung lượng bộ đệm hiện được cấp để lưu ký tự; thường lớn hơn hoặc bằng `length()`, và có thể tự tăng.
- `new StringBuilder(estimatedCapacity)` có thể giảm lần mở rộng bộ đệm nếu có ước lượng đáng tin. Đó là tối ưu tùy tình huống, không bắt buộc.
- `toString()` tạo `String` kết quả; nên gọi khi cần kết quả cuối thay vì lặp lại trong từng vòng ghép.
- `append((String) null)` thêm chữ `"null"`; nếu muốn bỏ qua `null`, phải kiểm tra trước.

`StringBuilder` **không đồng bộ hóa các thao tác để dùng chung một instance cho nhiều luồng**. `StringJoiner` cũng không nên được dùng chung rồi cùng sửa từ nhiều luồng nếu không có phối hợp an toàn. `StringBuffer` là lựa chọn có các phương thức được đồng bộ hóa, nhưng điều đó không tự bảo đảm toàn bộ quy trình ghép nhiều bước là một thao tác nguyên tử; nhiều trường hợp tốt hơn là mỗi luồng dùng builder riêng.

## 6. Ví dụ hoàn chỉnh Java 17+

Lưu chương trình dưới tên **`StringJoiningDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.Collectors;

public class StringJoiningDemo {
    public static void main(String[] args) {
        List<String> tags = List.of("Java", "Spring", "SQL");

        String viaPlus = tags.get(0) + " | "
                + tags.get(1) + " | " + tags.get(2);

        String viaJoin = String.join(" | ", tags);

        StringJoiner joiner = new StringJoiner(" | ", "[", "]");
        for (String tag : tags) {
            joiner.add(tag);
        }
        String viaJoiner = joiner.toString();

        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < tags.size(); i++) {
            if (i > 0) {
                builder.append(" | ");
            }
            builder.append(tags.get(i));
        }
        String viaBuilder = builder.toString();

        System.out.println("plus   : " + viaPlus);
        System.out.println("join   : " + viaJoin);
        System.out.println("joiner : " + viaJoiner);
        System.out.println("builder: " + viaBuilder);

        StringJoiner empty = new StringJoiner(", ", "[", "]");
        empty.setEmptyValue("(trống)");
        System.out.println("empty  : " + empty);

        List<String> raw = Arrays.asList("A", null, "", "B");
        String filtered = raw.stream()
                .filter(s -> s != null && !s.isEmpty())
                .collect(Collectors.joining(", "));
        System.out.println("filter : " + filtered);
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac StringJoiningDemo.java
java StringJoiningDemo
~~~

Đầu ra:

~~~text
plus   : Java | Spring | SQL
join   : Java | Spring | SQL
joiner : [Java | Spring | SQL]
builder: Java | Spring | SQL
empty  : (trống)
filter : A, B
~~~

Giải thích:

1. `+` nối ba phần tử biết trước vị trí; mã sẽ kém linh hoạt nếu danh sách thay đổi độ dài.
2. `String.join()` nhận trực tiếp `List`, tự chèn `" | "` giữa các mục và không thêm dấu ở hai đầu.
3. `StringJoiner` nhận từng phần tử, đồng thời bao kết quả bằng `[` và `]`.
4. `StringBuilder` chèn delimiter khi `i > 0`, rồi chuyển bộ đệm thành `String`.
5. `setEmptyValue()` xử lý joiner chưa có mục; ví dụ Stream chủ động loại bỏ null và chuỗi rỗng trước khi ghép.

## 7. So sánh theo yêu cầu sử dụng

| Tiêu chí | Toán tử `+` | `String.join()` | `StringJoiner` | `StringBuilder` |
|---|---|---|---|---|
| Loại API | Toán tử biểu thức | Phương thức tĩnh trả `String` | Đối tượng tích lũy | Bộ đệm ký tự thay đổi |
| Hợp với | Một vài phần đã biết | Mảng/`Iterable` có delimiter chung | Thêm dần, prefix/suffix, merge | Vòng lặp, định dạng phức tạp, sửa ký tự |
| Tự chèn delimiter | Không | Có | Có | Không |
| Prefix/suffix tự động | Không | Không | Có | Phải tự viết |
| Xử lý kết quả rỗng | Tùy biểu thức | `""` khi 0 phần tử | Prefix+suffix hoặc `setEmptyValue()` | `""` nếu builder rỗng |
| Chèn/xóa/sửa ký tự tùy ý | Không | Không | Không | Có |
| Đầu ra cuối | `String` | `String` | `toString()` | `toString()` |

### 7.1. Khía cạnh hiệu năng và bộ nhớ

Giả sử có `n` phần tử với tổng độ dài ký tự `L` và delimiter độ dài `d`. Một thuật toán ghép tốt cần xử lý xấp xỉ `L + (n - 1) × d` ký tự đầu ra (chưa tính prefix/suffix). Do đó:

- **Một lần `String.join()` hoặc dùng `StringJoiner` rồi gọi `toString()`** thường thích hợp cho nhiều phần tử cần dấu phân cách; tránh công việc tự kiểm tra phần tử đầu tiên.
- **Một `StringBuilder` được tái sử dụng xuyên suốt vòng lặp** có thể ghép tuyến tính theo tổng lượng dữ liệu với chi phí mở rộng bộ đệm được phân bổ qua nhiều lần `append()`.
- **Một biểu thức `+` đơn lẻ** có thể được JVM tối ưu tốt; chọn dựa trên độ rõ ràng trước khi tối ưu sớm.
- **`result += piece` trong vòng lặp dài** là dấu hiệu cần xem lại vì liên tục hình thành `String` trung gian. Đừng suy diễn chỉ từ số dấu `+` trong source code.

Các đặc điểm cấp phát, chi phí thực tế và ngưỡng chênh lệch phụ thuộc phiên bản JDK, JVM, JIT, dữ liệu và cách viết mã. Nếu hiệu năng quan trọng, đo với **JMH**, có warm-up và dữ liệu đại diện; tránh kết luận từ phép đo thủ công chỉ chạy một lần hoặc từ việc in log trong vòng đo.

### 7.2. Chọn nhanh qua tình huống

- Tạo thông báo `"Xin chào, " + userName` → **`+`** vì ngắn, trực quan.
- Tạo danh sách `a,b,c` từ một `List<String>` có sẵn → **`String.join(",", list)`**.
- Tạo chuỗi dạng `[a, b, c]` bằng cách `add()` từng mục → **`StringJoiner(", ", "[", "]")`**.
- Tạo báo cáo nhiều dòng với số, điều kiện, đoạn văn và chèn/sửa vị trí → **`StringBuilder`**.
- Ghép dữ liệu sau `filter()`/`map()` của Stream → **`Collectors.joining(delimiter)`** thường gọn nhất.

## 8. Những lỗi và ngộ nhận thường gặp

**1. Ghép hai phần tử bằng delimiter nhưng tự thêm delimiter sau mọi phần tử.**

~~~java
StringBuilder sb = new StringBuilder();
for (String s : List.of("A", "B")) {
    sb.append(s).append(","); // A,B, (dư dấu phẩy)
}
~~~

Nếu chỉ cần nối danh sách: `String.join(",", List.of("A", "B"))` trả `A,B`. Nếu dùng builder, thêm delimiter **trước các phần tử từ thứ hai** hoặc dựa vào chỉ số.

**2. Cho rằng `join()` lọc null/rỗng.** Thực tế `String.join("-", "A", "", "C")` thành `A--C`; `String.join("-", "A", null, "C")` thành `A-null-C`. Hãy quyết định trước liệu muốn giữ, bỏ qua hay thay thế các giá trị này.

**3. Cho rằng `StringJoiner.setEmptyValue()` có hiệu lực ngay cả sau `add("")`.** Một chuỗi rỗng vẫn là một phần tử đã được thêm; joiner không còn ở trạng thái rỗng theo nghĩa API.

**4. Nhầm `StringBuilder.length()` với số phần tử.** Nó đếm ký tự; khi phần tử đầu tiên là chuỗi rỗng, `length() == 0` vẫn đúng. Dùng biến `first` hoặc chỉ số để quản lý dấu phân cách nếu dữ liệu có thể có chuỗi rỗng.

**5. Nhầm `String.join()` với encoder định dạng dữ liệu.** Đầu vào `"Ho, Ten"` chứa dấu phẩy vẫn giữ dấu phẩy đó trong đầu ra. Với CSV, JSON, SQL hay URL, phải dùng formatter/encoder/API phù hợp; riêng SQL cần truy vấn tham số thay vì tự nối input.

**6. Dùng `+` để tích lũy lượng dữ liệu lớn và cho rằng cách đó luôn nhanh như một biểu thức đơn lẻ.** Tối ưu một biểu thức nối không đồng nghĩa JVM loại bỏ được mọi `String` trung gian giữa các lần gán `+=` trong vòng lặp.

**7. Dùng chung một `StringBuilder` mutable giữa nhiều luồng.** Nếu các luồng sửa cùng đối tượng mà không có đồng bộ phù hợp, nội dung có thể sai. Thường nên tạo bộ đệm trong phạm vi một phương thức/tác vụ.

## 9. Ghi nhớ khi áp dụng

Hãy bắt đầu từ **hình dạng đầu vào** và **quy tắc đầu ra**. Với vài phần cố định, dùng `+`. Với một dãy đã có và một delimiter, dùng `String.join()`. Với quá trình thêm dần cần prefix/suffix, dùng `StringJoiner`. Với việc xây dựng chuỗi phức tạp hoặc cập nhật lặp nhiều lần, dùng `StringBuilder`. Sau đó xác định rõ cách xử lý null, chuỗi rỗng, escaping và phạm vi sử dụng giữa các luồng; các yếu tố này ảnh hưởng tính đúng đắn hơn nhiều so với việc chọn API ngắn nhất.

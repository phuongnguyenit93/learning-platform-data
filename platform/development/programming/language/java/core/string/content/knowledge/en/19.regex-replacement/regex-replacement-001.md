# replaceFirst và replaceAll: thay thế bằng regex trong Java

Trong Java, lớp **String** có hai phương thức thay thế nội dung theo **biểu thức chính quy (regular expression, regex)**: **replaceFirst** và **replaceAll**. Cả hai tìm đoạn văn bản khớp mẫu rồi tạo một String kết quả; khác biệt cốt lõi là thay **lần khớp đầu tiên** hay **mọi lần khớp**.

## 1. Cú pháp và cách hoạt động

~~~java
String replaceFirst(String regex, String replacement)
String replaceAll(String regex, String replacement)
~~~

| Phương thức | Ý nghĩa | Ví dụ kết quả |
| --- | --- | --- |
| **replaceFirst** | Thay lần khớp đầu tiên từ trái sang phải | "a1 b2".replaceFirst("\\d+", "#") → "a# b2" |
| **replaceAll** | Thay mọi lần khớp không chồng lấn | "a1 b2".replaceAll("\\d+", "#") → "a# b#" |

- **regex** là mẫu tìm kiếm theo cú pháp regex của **java.util.regex.Pattern**.
- **replacement** là chuỗi thay thế theo cú pháp của **java.util.regex.Matcher**. Trong đó, **$** và dấu gạch chéo ngược có ý nghĩa riêng; không phải lúc nào cũng được xem là ký tự thường.
- Hai phương thức **không sửa String gốc**, vì String bất biến. Cần dùng giá trị trả về nếu muốn giữ thay đổi.
- Nếu regex không khớp đoạn nào, kết quả có cùng nội dung với chuỗi đầu vào.
- Bộ máy xét các đoạn khớp từ trái sang phải; kết quả mới chèn vào không bị tìm kiếm lại trong cùng lượt.
- Không cần regex khớp toàn bộ chuỗi: một đoạn con khớp cũng đủ để được thay thế.

Có thể hình dung cách triển khai về mặt ngữ nghĩa:

~~~java
Pattern.compile(regex).matcher(input).replaceFirst(replacement);
Pattern.compile(regex).matcher(input).replaceAll(replacement);
~~~

Đoạn này minh họa cơ chế; để chạy cần khai báo các biến và import **java.util.regex.Pattern**. Với nhu cầu xử lý nhiều chuỗi theo cùng mẫu, có thể tự giữ đối tượng Pattern để tái sử dụng (xem phần 8).

## 2. Chương trình Java 17+ chạy được

Lưu tệp **ReplaceRegexDemo.java**:

~~~java
public class ReplaceRegexDemo {
    public static void main(String[] args) {
        String original = "Mã A12, B345 và C6";

        System.out.println(original.replaceFirst("\\d+", "#"));
        System.out.println(original.replaceAll("\\d+", "#"));
        System.out.println("a.b.c".replaceAll("\\.", "-"));
        System.out.println("Java JAVA java".replaceAll("(?i)java", "JVM"));
        System.out.println(
                "2026-10-23".replaceFirst(
                        "(\\d{4})-(\\d{2})-(\\d{2})", "$3/$2/$1"));
        System.out.println("ababa".replaceAll("aba", "X"));
        System.out.println(
                "  Xin   chào   Java  ".replaceAll("\\s+", " ").trim());
    }
}
~~~

Chạy bằng:

~~~bash
javac ReplaceRegexDemo.java
java ReplaceRegexDemo
~~~

Stdout:

~~~text
Mã A#, B345 và C6
Mã A#, B# và C#
a-b-c
JVM JVM JVM
23/10/2026
Xba
Xin chào Java
~~~

Giải thích lần lượt: **\\d+** khớp một cụm chữ số; **\\.** khớp dấu chấm thật; **(?i)** bật so khớp không phân biệt hoa/thường; **$3/$2/$1** sắp xếp lại dữ liệu của ba nhóm bắt giữ; **"ababa"** chỉ có một lần khớp "aba" không chồng lấn khi quét từ trái sang phải; **\\s+** gộp cụm khoảng trắng, còn **trim()** bỏ khoảng trắng hai đầu.

## 3. Hai lớp escaping: Java String và regex

Chuỗi regex đi qua **hai bộ phân tích**: trình biên dịch Java đọc String literal trước, sau đó Pattern diễn giải chuỗi nhận được thành regex. Vì thế, nhiều dấu gạch chéo ngược phải viết đôi trong mã Java.

| Muốn tìm | Mẫu regex | String literal trong Java |
| --- | --- | --- |
| Một hay nhiều chữ số | \d+ | "\\d+" |
| Một hay nhiều khoảng trắng | \s+ | "\\s+" |
| Dấu chấm thật | \. | "\\." |
| Dấu gạch chéo ngược thật | \\ | "\\\\" |
| Chữ hoa từ A đến Z | [A-Z] | "[A-Z]" |
| Chuỗi bắt đầu bằng ID- | ^ID- | "^ID-" |

Một số cú pháp regex thường dùng:

- **.**: bất kỳ ký tự nào trừ một số ký tự kết thúc dòng theo chế độ mặc định.
- **[0-9]**, **[A-Z]**, **[^,]**: lớp ký tự.
- **+**: ít nhất một lần; **\***: không hoặc nhiều lần; **?**: có hoặc không; **{n}**: đúng n lần.
- **^** và **$**: neo đầu và cuối chuỗi (có thể thay đổi theo chế độ MULTILINE).
- **(...)**: nhóm bắt giữ; **(?:...)**: nhóm không bắt giữ.
- **(?i)**: cờ bỏ qua khác biệt chữ hoa/thường; **(?m)**: cho ^/$ hoạt động theo từng dòng.
- **\\s+**: gom các ký tự khoảng trắng; **\\d{4}**: đúng bốn chữ số.

Ví dụ chỉ xóa khoảng trắng **ở đầu**:

~~~java
String input = "   Java   regex   ";
String first = input.replaceFirst("^\\s+", ""); // "Java   regex   "
String all   = input.replaceAll("\\s+", " ");   // " Java regex "
~~~

Hai dòng khác mục tiêu: dùng **^** để chỉ chọn phần đầu chuỗi, hoặc chuẩn hóa mọi cụm khoảng trắng. Nếu muốn cả chuỗi khớp đúng định dạng, dùng neo đầu/cuối thích hợp thay vì mặc định rằng replaceAll kiểm tra toàn bộ chuỗi.

## 4. Nhóm bắt: tái sử dụng phần đã tìm thấy

Regex **(...)** đặt nhóm bắt theo thứ tự ngoặc mở. Replacement dùng **$1**, **$2**... để lấy từng nhóm, **$0** để lấy toàn bộ lần khớp và **${name}** để lấy nhóm đặt tên bởi **(?<name>...)**. Ví dụ đổi ngày bằng **$3/$2/$1** ở mục 2: nhóm thứ ba chứa ngày, nhóm thứ hai chứa tháng và nhóm thứ nhất chứa năm.

Khi chỉ cần gom nhánh regex mà không muốn thay đổi số nhóm, dùng **(?:...)**. Nhóm tùy chọn đã khai báo nhưng không tham gia một match được thay bằng chuỗi rỗng; tham chiếu tới nhóm không tồn tại lại là lỗi. Bài kế tiếp đào sâu nhóm lồng nhau, nhóm có tên và quy tắc tham chiếu.

## 5. Tìm và chèn văn bản nguyên văn

Với văn bản cần tìm do người dùng nhập như **a.b**, **Pattern.quote(needle)** khiến dấu chấm được hiểu theo nghĩa đen thay vì wildcard. Với văn bản muốn chèn như **$5\backup**, **Matcher.quoteReplacement(value)** giữ nguyên dấu đô la và dấu gạch chéo ngược, tránh nhầm **$5** thành tham chiếu nhóm.

Hai API quote bảo vệ **hai tham số độc lập**; không dùng chúng hoán đổi cho nhau. Nếu cả phần tìm và phần thay đều là chuỗi literal, **String.replace(target, replacement)** đơn giản hơn. Các bài về ký tự đặc biệt và quoteReplacement tiếp tục làm rõ từng trường hợp và cách kiểm thử.

## 6. So sánh với String.replace

**String.replace** hoạt động theo nghĩa literal, không phân tích regex:

~~~java
String input = "a.b 1.2";

System.out.println(input.replace(".", "-"));      // a-b 1-2
System.out.println(input.replaceAll("\\.", "-")); // a-b 1-2
System.out.println(input.replaceAll(".", "-"));    // -------
~~~

- **replace(CharSequence, CharSequence)** thay tất cả lần xuất hiện của văn bản cố định.
- **replace(char, char)** thay tất cả lần xuất hiện của ký tự cố định.
- **replaceAll(regex, replacement)** thay mọi đoạn khớp biểu thức chính quy.
- **replaceFirst(regex, replacement)** chỉ thay đoạn khớp đầu tiên.

Với nhu cầu thay literal thông thường, dùng **replace** để tránh viết regex và tránh quy tắc đặc biệt của replacement. Ví dụ, **"a$b".replace("$", "$$")** trả về **"a$$b"** mà không cần quote replacement.

## 7. Hành vi ở các trường hợp biên

**Không có đoạn khớp:** "abc".replaceAll("\\d+", "#") cho nội dung "abc"; đây là hành vi bình thường.

**Khớp độ dài bằng 0:** regex có neo hoặc lookahead có thể khớp ở vị trí giữa các ký tự mà không tiêu thụ ký tự:

~~~java
System.out.println("abc".replaceFirst("^", ">>"));  // >>abc
System.out.println("abc".replaceAll("(?=b)", "|")); // a|bc
~~~

**Các lần khớp không chồng lấn:** "ababa".replaceAll("aba", "X") là **"Xba"**, không phải kết quả của việc thay tất cả các vị trí bắt đầu có thể chồng lên nhau.

**Nhiều dòng:** dấu chấm **.** mặc định không khớp một số ký tự kết thúc dòng. Nếu muốn dấu chấm bao gồm cả xuống dòng, cân nhắc chế độ **DOTALL**, ví dụ tiền tố **(?s)**. Cờ **(?m)** phục vụ cách hiểu ^ và $ theo dòng; hai cờ không thay thế nhau.

**Lỗi regex/replacement:** regex không hợp lệ như **[** gây **PatternSyntaxException**; tham chiếu nhóm không hợp lệ hay cú pháp **$**/**\\** sai trong replacement có thể gây **IllegalArgumentException** hoặc **IndexOutOfBoundsException**. Tham số null có thể dẫn đến **NullPointerException**. Cần validate đầu vào và thông báo lỗi rõ ràng cho người sử dụng.

**String bất biến:**

~~~java
String original = "a1 b2";
String updated = original.replaceAll("\\d", "#");

System.out.println(original); // a1 b2
System.out.println(updated);  // a# b#
~~~

Gọi replaceAll mà bỏ qua giá trị trả về thì biến **original** không hề thay đổi.

## 8. Tái sử dụng Pattern và thay thế động

Nếu xử lý nhiều chuỗi với cùng regex, biên dịch Pattern một lần:

~~~java
import java.util.List;
import java.util.regex.Pattern;

public class ReusePatternDemo {
    public static void main(String[] args) {
        Pattern digits = Pattern.compile("\\d+");

        for (String value : List.of("A12", "B345", "C6")) {
            System.out.println(digits.matcher(value).replaceAll("#"));
        }
    }
}
~~~

Lưu thành **ReusePatternDemo.java**, chạy:

~~~bash
javac ReusePatternDemo.java
java ReusePatternDemo
~~~

Stdout:

~~~text
A#
B#
C#
~~~

**Pattern** là đối tượng bất biến và có thể dùng chung giữa các luồng. **Matcher** lưu trạng thái của một lượt tìm kiếm và không nên chia sẻ để thao tác đồng thời giữa các luồng.

Từ Java 9, **Matcher.replaceAll(Function<MatchResult, String>)** cho phép tính replacement khác nhau cho từng match. Chuỗi hàm trả về vẫn được diễn giải theo cú pháp replacement; nếu muốn chèn nguyên văn nội dung tính được có **$** hoặc dấu gạch chéo ngược, dùng **Matcher.quoteReplacement**. Bài chuyên sâu về callback phân tích cách đọc nhóm, quản lý trạng thái và xử lý lỗi.

## 9. Lỗi hay gặp, cách phòng tránh

| Lỗi | Nguyên nhân | Cách giải quyết |
| --- | --- | --- |
| replaceAll(".", "") làm mất gần hết văn bản | Dấu chấm là wildcard | Dùng "\\." hoặc Pattern.quote(".") |
| Viết "\d" khiến Java báo lỗi escape | Java String cần escape dấu gạch chéo ngược | Dùng "\\d" trong mã Java |
| Replacement chứa "$" dẫn đến lỗi nhóm | $ được phân tích theo tham chiếu nhóm | Dùng Matcher.quoteReplacement |
| Chỉ thay được lần đầu trong khi muốn thay mọi lần | Đang dùng replaceFirst | Dùng replaceAll |
| Muốn tìm văn bản cố định nhưng regex khớp quá rộng | Dữ liệu literal bị hiểu là regex | Dùng replace hoặc Pattern.quote |
| Kết quả không thay đổi trên biến gốc | String bất biến | Gán biến bằng giá trị trả về |
| Xử lý lặp nhiều chuỗi gây tốn thời gian | Regex được biên dịch lại nhiều lần | Tạo một Pattern và dùng matcher riêng cho từng chuỗi |

Các regex có lượng từ lồng nhau hoặc cấu trúc backtracking phức tạp có thể xử lý rất chậm trên đầu vào đặc biệt dài. Với dữ liệu ngoài, nên giới hạn kích thước hợp lý, kiểm soát regex được chấp nhận và ưu tiên tìm kiếm literal khi bài toán chỉ cần khớp ký tự chính xác.

## 10. Tự kiểm tra và cách lựa chọn

Cho chuỗi **"x9 y88 z777"**, hãy dự đoán:

~~~java
String s = "x9 y88 z777";
System.out.println(s.replaceFirst("\\d+", "?"));
System.out.println(s.replaceAll("\\d+", "?"));
~~~

Đáp án stdout:

~~~text
x? y88 z777
x? y? z?
~~~

Khi chỉ muốn thay **một** đoạn khớp đầu tiên, chọn **replaceFirst**. Khi muốn thay **tất cả** đoạn khớp, chọn **replaceAll**. Khi không cần biểu thức chính quy, dùng **replace**. Nếu phải thay nhiều chuỗi theo cùng mẫu, có thể dùng **Pattern** tái sử dụng; nếu dữ liệu phải được hiểu theo nghĩa literal, dùng đúng **Pattern.quote** và **Matcher.quoteReplacement** cho từng phía.

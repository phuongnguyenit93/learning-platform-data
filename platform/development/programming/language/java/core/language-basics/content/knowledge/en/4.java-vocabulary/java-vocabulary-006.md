# Khoảng trắng, xuống dòng và phân tách token trong Java

> **Java core — language-basics / Từ vựng Java**  
> **Môi trường thực hành:** JDK 17 trở lên, không cần thư viện ngoài.  
> **Mục tiêu:** Hiểu Java xử lý khoảng trắng, tab, xuống dòng và chú thích ra sao trước khi phân tích cú pháp; biết khi nào hai token cần được tách, khi nào xuống dòng không thay thế dấu chấm phẩy; giải thích quy tắc nhận token dài nhất; phân biệt khoảng trắng ở bên ngoài với nội dung bên trong chuỗi hoặc text block. Có thể tự biên dịch, chạy và dự đoán đầu ra ví dụ.

## 1. Từ ký tự nguồn tới dãy token

Mã nguồn Java được viết bằng các ký tự. Trước khi kiểm tra xem một dòng có tạo thành biểu thức hoặc câu lệnh hợp lệ hay không, compiler phải nhận ra những **đơn vị từ vựng (token)**.

Ví dụ:

~~~java
int total = unitPrice * quantity;
~~~

Bộ phân tích từ vựng nhận những token: `int`, `total`, `=`, `unitPrice`, `*`, `quantity`, `;`. Khoảng trắng giữa chúng giúp nhận ranh giới, nhưng **không phải token** trong năm nhóm identifier/keyword/literal/operator/separator.

~~~mermaid
flowchart LR
    A["Ký tự trong file .java"] --> B["Xử lý Unicode escape và ký tự dòng"]
    B --> C["Nhận biết token, whitespace, comment"]
    C --> D["Dãy token"]
    D --> E["Phân tích cú pháp Java"]
~~~

Từ một dãy token hợp lệ, Java **chưa chắc tạo được câu lệnh hợp lệ**. Ví dụ `int = 2;` vẫn gồm các token nhận ra được nhưng sai ngữ pháp khai báo biến.

**Điểm chính:** khoảng trắng và xuống dòng chủ yếu điều khiển **ranh giới lexical**, chứ không phải tín hiệu mặc định để chương trình “chạy sang lệnh tiếp theo”.

## 2. Java công nhận những loại khoảng trắng nào?

Ở cấp xử lý từ vựng thông thường, Java nhận diện các loại ký tự khoảng trắng và dấu hết dòng quan trọng sau:

| Ký tự | Cách gọi | Tình huống thường gặp |
| --- | --- | --- |
| Space `U+0020` | Dấu cách | Giữa `int` và tên biến |
| Horizontal tab `U+0009` | Tab ngang | Thụt lề trong trình soạn thảo |
| Form feed `U+000C` | Ngắt trang | Ít gặp trong mã nguồn hiện đại |
| LF `U+000A` | Line feed | Xuống dòng trên nhiều hệ thống Unix |
| CR `U+000D` | Carriage return | Dấu dòng từ các định dạng cũ |
| CRLF | Cặp carriage return + line feed | Kết thúc dòng phổ biến trong tệp Windows |

Với Java, **CRLF được nhận như một dấu kết thúc dòng**, không phải hai lần ngắt dòng độc lập. Sự khác nhau LF/CRLF thường không thay đổi ngữ nghĩa một câu lệnh Java hợp lệ; nhưng có thể ảnh hưởng comment dòng, vị trí báo lỗi và nội dung literal ở những vị trí đặc biệt.

Không được giả định **mọi ký tự trông giống khoảng trắng Unicode đều được lexer Java xử lý như dấu cách ASCII**. Chẳng hạn, một ký tự khoảng trắng không ngắt (*non-breaking space*) sao chép từ trang web có thể gây kết quả khác thường hoặc lỗi từ vựng. Khi mã nhìn đúng nhưng compiler báo ký tự không hợp lệ, hãy kiểm tra các ký tự vô hình.

## 3. Khi nào khoảng trắng là bắt buộc?

Một số cặp token là chữ/tên sẽ dính thành **một token khác** nếu viết liền.

| Ý định đúng | Viết liền | Điều xảy ra |
| --- | --- | --- |
| `int count = 1;` | `intcount = 1;` | `intcount` là một identifier, **không** còn keyword `int` cộng tên `count` |
| `long total = 2L;` | `longtotal = 2L;` | Lexer nhận `longtotal` là identifier |
| `new Example()` | `newExample()` | Một identifier `newExample`, không còn keyword `new` |
| `return result;` | `returnresult;` | `returnresult` là tên identifier, không phải câu lệnh `return` |

Để tách token không nhất thiết chỉ dùng dấu cách. Dòng mới và **chú thích block** cũng có thể làm ranh giới:

~~~java
int
count = 1;

int /* chú thích giữa hai token */ total = 2;

int/**/other = 3;
~~~

Ba biến `count`, `total`, `other` được khai báo hợp lệ khi những dòng trên nằm **trong một phương thức hoặc block được phép khai báo biến cục bộ**. Trong dòng `int/**/other`, chú thích được xử lý như khoảng phân cách từ vựng giữa từ khóa và identifier.

Ngược lại, nhiều token có thể chạm nhau mà vẫn phân biệt rõ:

~~~java
int x=1;
x++;
System.out.println(x);
~~~

Dấu `=`, `;`, `(`, `)` và `.` đã tự tạo ranh giới phù hợp. Thêm dấu cách nhằm dễ đọc là tốt, nhưng **không có quy tắc phải đặt dấu cách quanh mọi dấu câu**.

## 4. Xuống dòng không tự kết thúc câu lệnh Java

Java không dùng “xuống dòng là dấu chấm phẩy tự động” cho các statement thông thường. Ví dụ dưới đây hợp lệ bên trong một phương thức:

~~~java
int value
        =
        10
        +
        5
        ;
System.out.println
        (
            value
        )
        ;
~~~

Đoạn đó tương đương về ý nghĩa với:

~~~java
int value = 10 + 5;
System.out.println(value);
~~~

Cả hai in `15`. Compiler quan tâm tới dãy token và ngữ pháp, **không phải cách code được chia thành nhiều dòng**.

Những trường hợp cần nhớ:

- `int value = 10` rồi xuống dòng **không** tự hoàn thành một khai báo; thông thường vẫn cần dấu `;`.
- `if (ready)` rồi xuống dòng trước `{ ... }` là hợp lệ; block vẫn là thân của `if`.
- Có thể đặt nhiều statement trên cùng dòng, chẳng hạn `int a = 1; int b = 2;`.
- Với dấu `;` đứng riêng sau `if` hoặc `while`, bạn có thể vô tình tạo một **empty statement**: đây là một token có ý nghĩa cú pháp, không liên quan đến việc xuống dòng.

**Tách biệt:** Dấu kết thúc dòng vẫn quan trọng để **kết thúc chú thích `//`** và đối với cách viết literal chuỗi; điều đó **không** biến xuống dòng thành token kết thúc statement.

## 5. Chú thích có thể phân tách token

Java nhận diện `//` tới hết dòng và `/* ... */` tới dấu đóng đầu tiên; `/** ... */` là dạng chú thích tài liệu được công cụ Javadoc xử lý. **Nội dung chú thích không trở thành token chương trình**, nhưng dấu kết thúc của chúng quyết định phần mã nào còn được phân tích.

~~~java
int count // Chú thích dòng kết thúc ở đây.
        = 3;

int /* Chú thích khối nằm giữa các token */ total = count * 2;
~~~

Cả hai khai báo đều hợp lệ trong một phương thức: sau khi bỏ nội dung chú thích, lexer vẫn nhận các token tương ứng với `int count = 3;` và `int total = count * 2;`. Ngược lại, `// int count = 3;` **không tạo biến** vì cả khai báo nằm trong comment.

Bài về các loại chú thích sẽ giải thích riêng việc dùng `//`, `/* ... */`, `/** ... */`, giới hạn không lồng block comment và cách tạo tài liệu Javadoc.

## 6. Quy tắc nhận token dài nhất: khoảng trắng có thể đổi ý nghĩa

Khi một chuỗi ký tự có thể tạo thành nhiều token, lexer Java ưu tiên token dài nhất có thể nhận hợp lệ ở vị trí đó (*maximal munch*). Đây là lý do các toán tử dài cần được nhận diện nguyên khối.

| Chuỗi mã | Phân tích quan trọng | Ý nghĩa hoặc hệ quả |
| --- | --- | --- |
| `count++;` | `count`, `++`, `;` | `++` là một toán tử tăng hậu tố |
| `total += 2;` | `total`, `+=`, `2`, `;` | `+=` là toán tử gán kết hợp |
| `x >= 3` | `x`, `>=`, `3` | `>=` là một toán tử so sánh |
| `x > = 3` | `x`, `>`, `=`, `3` | Không tương đương `x >= 3` và không hợp lệ trong ngữ cảnh này |
| `x+++y` | `x`, `++`, `+`, `y` | Được phân tích như `x++ + y`, **không** phải `x + ++y` |
| `x + ++y` | `x`, `+`, `++`, `y` | Tăng `y` trước khi cộng với `x` |

Ví dụ với `int x = 4; int y = 3;`:

- `int result = x+++y;` tạo `result = 7` và sau đó `x = 5`, `y = 3`.
- `int result = x + ++y;` (nếu bắt đầu lại với cùng `x = 4`, `y = 3`) tạo `result = 8` và `y = 4`.

**Khoảng trắng có thể thay đổi token được nhận**, nhưng không phải mọi cách chèn khoảng trắng đều có thể biến thành mã hợp lệ. Ví dụ cố viết `a + + b` là hai toán tử `+` liên tiếp theo ngữ pháp *binary plus* rồi *unary plus*, khác với toán tử `++`.

Quy tắc này xảy ra **trước** khi compiler quyết định phép toán nào được tính trước hoặc sau. Đó là hai tầng khác nhau: nhận token và đánh giá biểu thức.

## 7. Khoảng trắng trong chuỗi và ký tự thoát

Ngoài các chuỗi literal, khoảng trắng thường chỉ phân tách hoặc trình bày mã. **Bên trong một string literal**, dấu cách là dữ liệu và được giữ nguyên:

~~~java
String one = "A B";
String two = "A  B";
System.out.println(one.length()); // 3
System.out.println(two.length()); // 4
~~~

Hai giá trị khác nhau vì `two` có **hai dấu cách giữa A và B**.

**Xuống dòng thật** không được phép xuất hiện ngay giữa một literal chuỗi thông thường:

~~~java
// Mảnh ví dụ CỐ Ý KHÔNG HỢP LỆ:
// String invalid = "Dong 1
// Dong 2";
~~~

Nếu bỏ dấu comment ở hai dòng để tạo một literal chuỗi vỡ qua dòng theo cách đó, compiler sẽ báo lỗi. Cách hợp lệ để chứa newline trong một chuỗi là dùng escape sequence:

~~~java
String valid = "Dong 1\nDong 2";
System.out.println(valid.lines().count()); // 2
~~~

Các ký tự `\` và `n` trong `"Dong 1\nDong 2"` tạo biểu diễn escape của newline trong chuỗi khi chương trình chạy; đó **không** phải việc gõ Enter làm vỡ chuỗi trong file source.

### Text block trong Java 17

Java 17 hỗ trợ *text block* bằng ba dấu nháy kép. Dòng đầu phải có dấu kết thúc dòng sau `"""` mở:

~~~java
String text = """
        First
        Second
        """;
System.out.println(text.replace("\n", "|")); // First|Second|
~~~

Java sẽ xử lý thụt lề chung và nội dung newline của text block theo các quy tắc riêng. Với cấu trúc trên, chuỗi giữ dấu xuống dòng **sau cả dòng `Second`**, nên kết quả có dấu `|` cuối. Đừng suy ra mọi khoảng trắng trong text block được giữ nguyên từng byte: indentation chung thường bị loại bỏ khi dựng giá trị chuỗi.

## 8. Cẩn thận với Unicode escape và ký tự vô hình

Việc xử lý Unicode escape của Java xảy ra **rất sớm**, trước khi nhận biết comment và các token. Vì vậy các chuỗi escape hợp lệ có thể tác động tới ranh giới dòng hoặc cú pháp ngay cả khi chúng xuất hiện trong phần nguồn trông giống comment.

Ví dụ, dạng Unicode escape viết bằng dấu gạch chéo ngược, chữ `u` và bốn chữ số hex để tạo **LF** có thể trở thành một dấu kết thúc dòng trước khi compiler nhận diện một chú thích `//`. Đây là trường hợp biên để hiểu quy trình từ vựng, **không phải kỹ thuật nên sử dụng** để xuống dòng trong code.

Khi gặp lỗi kỳ lạ:

- Kiểm tra dấu tab, dấu cách không ngắt (*NBSP*) và các ký tự vô hình do copy/paste.
- Kiểm tra rằng file được lưu bằng mã hóa nhất quán; với `javac` có thể truyền `-encoding UTF-8`.
- Kiểm tra Unicode escape trong source thay vì đoán rằng mọi ký tự trong comment đều hoàn toàn bị bỏ qua ở bước đầu tiên.
- Không dùng việc xuống dòng hoặc chèn comment để “chữa” một lỗi ngữ pháp chưa được hiểu.

## 9. Chương trình Java 17+ tự chạy: WhitespaceDemo.java

Tạo file **WhitespaceDemo.java** (đúng tên `public class`) và nhập:

~~~java
public final class WhitespaceDemo {
    public static void main(String[] args) {
        int base = 7;
        int extra // Chú thích kết thúc ở hết dòng.
                = 5;

        int sum = base
                + extra;
        int/**/factor = 2; // Block comment tách int và factor.

        boolean ready = sum >= 10
                && factor > 0;

        int x = 4;
        int y = 3;
        int glued = x+++y; // Lexer: x++ + y.

        String spaces = "A  B";
        String escaped = "first\nsecond";
        String block = """
                one
                two
                """;

        System.out.println("sum=" + sum);
        System.out.println("ready=" + ready);
        System.out.println("glued=" + glued + ", x=" + x + ", y=" + y);
        System.out.println("literalLength=" + spaces.length());
        System.out.println("escapedLines=" + escaped.lines().count());
        System.out.println("textBlock=" + block.replace("\n", "|"));
    }
}
~~~

**Biên dịch và chạy** trong terminal tại thư mục chứa file, áp dụng cho Bash, PowerShell và Command Prompt:

~~~bash
javac -encoding UTF-8 WhitespaceDemo.java
java WhitespaceDemo
~~~

**Kết quả mong đợi chính xác:**

~~~text
sum=12
ready=true
glued=7, x=5, y=3
literalLength=4
escapedLines=2
textBlock=one|two|
~~~

### Giải thích kết quả

1. `int extra` bị tách qua một dòng comment, nhưng vẫn là khai báo hợp lệ; `extra = 5`.
2. `sum` bằng `7 + 5 = 12` dù biểu thức trải qua nhiều dòng; xuống dòng không ngầm chèn `;`.
3. `int/**/factor` tương đương đặt khoảng phân tách giữa `int` và `factor`; `factor = 2` nên điều kiện `ready` đúng.
4. `x+++y` được nhận thành `x++ + y`; `glued` nhận `4 + 3 = 7`, `x` sau đó bằng `5`, `y` giữ `3`.
5. Literal `"A  B"` có hai dấu cách nên độ dài bằng `4`.
6. Literal `"first\nsecond"` có một newline escape nên `lines().count()` trả `2`.
7. Text block có hai dòng nội dung và newline ở cuối; sau khi thay newline bằng `|`, kết quả là `one|two|`.

**Phạm vi ví dụ:** mã này minh họa lexical rules bằng kết quả quan sát được. Java compiler không in danh sách token ra console; để phân tích token chi tiết cần công cụ/parser chuyên dụng, không phải `javac` thông thường.

## 10. Những lỗi thường gặp và hướng kiểm tra

| Hiện tượng | Nguyên nhân có khả năng | Cách giải quyết |
| --- | --- | --- |
| `cannot find symbol` với `intcount` | Viết dính keyword và identifier nên thành một tên khác | Tách `int count` |
| `';' expected` sau khai báo bị chia dòng | Quên dấu `;`, không phải Java “tự hiểu xuống dòng” | Thêm `;` vào đúng vị trí kết thúc |
| `unclosed string literal` | Chuỗi `"..."` bị ngắt dòng thật hoặc thiếu nháy kép đóng | Dùng `\n` trong chuỗi hoặc text block phù hợp |
| `illegal character` | Có ký tự Unicode không được phép ở vị trí từ vựng, ví dụ khoảng trắng lạ | Kiểm tra byte/ký tự vô hình, gõ lại ký tự đúng |
| `x+++y` cho kết quả không như dự kiến | Lexer nhận `x++` trước rồi `+ y` | Thêm khoảng trắng hoặc ngoặc để thể hiện rõ ý định |
| Đặt `//` nhưng phần sau cùng dòng “mất” | `//` bắt đầu comment tới hết dòng | Đặt phần mã cần chạy trên dòng khác hoặc sửa comment |
| Chú thích `/* ... */` không đóng | Comment block thiếu `*/` | Đóng comment đúng cặp, không lồng block comment |
| Text block thụt lề/xuống dòng sai kết quả | Có quy tắc indentation và trailing newline | In ra chuỗi thực tế, xem vị trí dấu `"""` đóng |

**Lưu ý:** Một lỗi trỏ tới dòng sau chỗ sai thường liên quan việc lexer/parser đang chờ một token còn thiếu. Đọc cả dòng trước đó, đặc biệt dấu nháy, dấu `;` và điểm kết thúc comment.

## 11. Bài tập tự luyện

**Bài 1 — Phân tách tên.** Giả sử bạn muốn khai báo biến `count` kiểu `int`. Vì sao `intcount=3;` không tương đương `int count=3;`? Hãy thử dạng `int/**/count=3;` trong một phương thức để tự xác nhận.

**Bài 2 — Dự đoán biểu thức.** Bắt đầu với `int x=4, y=3;`. So sánh `int a=x+++y;` với `int a=x+ ++y;` sau khi **khởi tạo lại x và y** cho từng trường hợp. Ghi lại kết quả `a` và giá trị cuối của từng biến.

**Bài 3 — Xuống dòng.** Viết một câu lệnh khai báo số và một lời gọi `println` trải qua ít nhất ba dòng. Xác định token `;` nào thực sự kết thúc statement.

**Bài 4 — Comment.** Viết `int number // comment` rồi đặt `= 10;` ở dòng tiếp theo; giải thích vì sao compiler vẫn chấp nhận. Thử thay bằng chú thích block.

**Bài 5 — Chuỗi.** Dự đoán `"a b".length()` và `"a  b".length()`; giải thích vì sao khoảng trắng trong literal có tác dụng khác với khoảng trắng giữa token.

**Bài 6 — Text block.** Thay text block trong `WhitespaceDemo` bằng ba dòng. In bằng `replace("\n", "|")` để xác định chỗ nào có newline. Thử thay đổi vị trí dấu `"""` đóng để quan sát cách xử lý indentation.

## 12. Tổng kết

- **Khoảng trắng** có thể cần để tách keyword/identifier; ở nhiều vị trí khác chỉ giúp mã dễ đọc.
- **Xuống dòng** không phải dấu kết thúc statement chung của Java, nhưng có vai trò rõ ràng với `//` comment và cú pháp literal.
- **Comment** không sinh ra token cho parser thông thường và có thể nằm giữa hai token.
- **Token dài nhất** giải thích vì sao `++`, `>=` được nhận nguyên khối và `x+++y` khác `x + ++y`.
- **Trong literal**, khoảng trắng và escape có thể là dữ liệu; **text block** có quy tắc newline/indentation riêng.

**Tự kiểm tra:** Bạn có thể giải thích vì sao `intcount` khác `int count`, vì sao `x+++y` được đọc theo cách cụ thể, và vì sao một chuỗi bị ngắt dòng trực tiếp có thể lỗi dù câu lệnh Java thông thường có thể trải nhiều dòng.

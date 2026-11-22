# Vị trí dấu đóng và dòng mới cuối chuỗi của Java text block

## 1. Ý nghĩa của vị trí `"""` đóng

**Text block** là một cách viết literal kiểu `String` có thể trải trên nhiều dòng, giúp biểu diễn SQL, JSON, HTML, văn bản mẫu và các chuỗi nhiều dòng mà không cần nối nhiều string literal. Vị trí của **dấu đóng ba dấu nháy kép** (`"""`) ảnh hưởng trực tiếp tới nội dung `String` được tạo ra.

Ví dụ thường gặp:

~~~java
String lines = """
    red
    green
    blue
    """;
~~~

Nội dung của `lines` tương đương:

~~~java
String lines = "red\ngreen\nblue\n";
~~~

Có **một ký tự xuống dòng cuối chuỗi** ngay sau `blue`. Nó không phải là xuống dòng do `System.out.println` tạo ra, mà đã nằm **trong giá trị String**.

Đặt dấu đóng ở cuối dòng cuối cùng của nội dung:

~~~java
String lines = """
    red
    green
    blue""";
~~~

thì chuỗi tương đương:

~~~java
String lines = "red\ngreen\nblue";
~~~

**Không còn `\n` ở cuối.** Hai cách viết đều hợp lệ trên Java hiện đại nhưng **không cho cùng một giá trị String**.

Text blocks trở thành tính năng chính thức từ **Java 15 (JEP 378)**. Vì vậy, dù bài nằm trong lộ trình Java 14, kiến thức và ví dụ ở đây dùng ngữ nghĩa đã ổn định của **Java 17+**, không sử dụng cách bật preview cũ.

## 2. Quy tắc cú pháp: dấu mở bắt buộc có xuống dòng, dấu đóng thì linh hoạt

Cú pháp tổng quát:

~~~java
String message = """
    Dòng thứ nhất
    Dòng thứ hai
    """;
~~~

- **Dấu mở `"""`:** phải đi kèm ký tự kết thúc dòng sau dấu mở (có thể có khoảng trắng được cho phép trước xuống dòng). Dấu xuống dòng ngay sau dấu mở **không được đưa vào phần đầu của chuỗi**.
- **Nội dung:** bắt đầu ngay **sau** dấu xuống dòng của opening delimiter và kết thúc **ngay trước** dấu nháy đầu tiên của closing delimiter.
- **Dấu đóng `"""`:** có thể nằm **trên dòng riêng** hoặc ở **cuối dòng chứa ký tự nội dung**. Dấu đóng không phải là ba ký tự được thêm vào String.
- **Dấu `;` sau dấu đóng:** kết thúc câu lệnh gán/return; nó không nằm trong nội dung String.

Mã cố ý **không biên dịch**:

~~~java
// Sai: không có xuống dòng bắt buộc sau dấu mở.
String invalid = """hello""";
~~~

Mã hợp lệ dù giá trị chỉ chứa một dòng:

~~~java
String valid = """
    hello""";
~~~

Giá trị của `valid` là `"hello"` (không có `\n` cuối). Tuy nhiên, nếu nội dung chỉ dài một dòng thì literal thường `"hello"` có thể đơn giản và dễ đọc hơn.

### Dòng đầu tiên không bắt đầu bằng một `\\n` tự động

Mã:

~~~java
String title = """
    Welcome
    """;
~~~

cho `"Welcome\n"`, **không phải** `"\nWelcome\n"`. Dấu xuống dòng đầu tiên đóng vai trò **phân cách opening delimiter với nội dung**, nên không trở thành ký tự đầu của giá trị.

Nếu muốn có một dòng trống ở đầu, hãy chủ động thêm **một dòng trống nội dung**:

~~~java
String title = """

    Welcome
    """;
~~~

Kết quả là `"\nWelcome\n"`. Điều này hữu ích khi kiểm thử số dòng: phân biệt **dấu xuống dòng cú pháp** và **dấu xuống dòng thuộc nội dung**.

## 3. So sánh hai vị trí dấu đóng

Đặt các chuỗi cạnh nhau (các ví dụ độc lập có thể dùng trong phương thức):

~~~java
String keepFinalLf = """
    alpha
    beta
    """;

String omitFinalLf = """
    alpha
    beta""";
~~~

| Thuộc tính | Dấu đóng trên dòng riêng | Dấu đóng ngay sau chữ cuối |
| --- | --- | --- |
| Hình thức dòng cuối | `beta` rồi xuống dòng, sau đó `"""` | `beta"""` cùng một dòng |
| Giá trị String | `"alpha\nbeta\n"` | `"alpha\nbeta"` |
| `endsWith("\n")` | `true` | `false` |
| `length()` | `11` | `10` |
| Dùng khi | Muốn nội dung kết thúc bằng LF | Muốn dòng cuối kết thúc ngay tại chữ cuối |

Tính độ dài: `"alpha"` = 5 ký tự, `\n` = 1, `"beta"` = 4. Chuỗi không có `\n` cuối có `5 + 1 + 4 = 10` ký tự; chuỗi còn `\n` cuối có **11**.

Đây là khác biệt **dữ liệu thực**:

~~~java
System.out.println(keepFinalLf.equals(omitFinalLf)); // false
System.out.println(keepFinalLf.length() - omitFinalLf.length()); // 1
~~~

Nếu chuỗi được dùng làm đầu vào cho chữ ký số, so sánh snapshot chính xác, xuất tệp hay giao thức kiểm tra byte, `\n` thừa/thiếu có thể làm kết quả khác hẳn.

## 4. Ví dụ Java 17+ đầy đủ và đầu ra kiểm chứng

Chương trình dưới đây tập trung vào **dấu xuống dòng cuối**, **vị trí dấu đóng**, **dòng trống thật** và **lề thụt đầu dòng**.

Lưu với tên **`TextBlockClosingDemo.java`**, mã hóa UTF-8:

~~~java
public class TextBlockClosingDemo {

    static String visible(String text) {
        return "[" + text.replace("\n", "\\n") + "]";
    }

    public static void main(String[] args) {
        String keep = """
            red
            green
            blue
            """;

        String inline = """
            red
            green
            blue""";

        String continued = """
            red
            green
            blue\
            """;

        String blank = """
            red

            """;

        String margin = """
            red
            green
        """;

        System.out.println("keep=" + visible(keep));
        System.out.println("inline=" + visible(inline));
        System.out.println("continued=" + visible(continued));
        System.out.println("blank=" + visible(blank));
        System.out.println("margin=" + visible(margin));

        System.out.println("keep-final-lf=" + keep.endsWith("\n"));
        System.out.println("inline-final-lf=" + inline.endsWith("\n"));
        System.out.println(
                "continued-final-lf=" + continued.endsWith("\n")
        );
        System.out.println("inline-equals-continued="
                + inline.equals(continued));
        System.out.println(
                "length-difference=" + (keep.length() - inline.length())
        );
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 TextBlockClosingDemo.java
java TextBlockClosingDemo
~~~

Kết quả chính xác:

~~~text
keep=[red\ngreen\nblue\n]
inline=[red\ngreen\nblue]
continued=[red\ngreen\nblue]
blank=[red\n\n]
margin=[    red\n    green\n]
keep-final-lf=true
inline-final-lf=false
continued-final-lf=false
inline-equals-continued=true
length-difference=1
~~~

**Diễn giải:**

1. `keep`: dấu đóng ở dòng riêng, dòng `blue` có dấu xuống dòng trước dấu đóng; LF cuối **được giữ**.
2. `inline`: dấu đóng đặt ngay sau `blue`, nên không tồn tại line terminator giữa chữ cuối và dấu đóng; **không có LF cuối**.
3. `continued`: dấu đóng vẫn trên dòng riêng, nhưng ký tự escape **backslash ngay trước line terminator** (`` ở cuối dòng `blue`) làm LF đó **không được đưa vào String**. Kết quả bằng `inline`.
4. `blank`: thêm một dòng trống **thực sự** trước dấu đóng dẫn đến **hai LF cuối**: một sau `red`, một sau dòng trống.
5. `margin`: dấu đóng được đưa sang trái 4 cột so với các dòng nội dung, nên quy tắc tước khoảng trắng ngẫu nhiên (incidental indentation) **giữ lại 4 dấu cách ở đầu mỗi dòng**.
6. `visible` biến mỗi LF thành hai ký tự dễ nhìn `` và `n`. Vì bản thân các giá trị của ví dụ không chứa dấu backslash thực, output hiển thị không mơ hồ.
7. `System.out.println(...)` **luôn tự tạo xuống dòng sau phần nó in**. Dùng `visible`, `equals`, `endsWith` hoặc `length` để kiểm tra nội dung String, tránh dựa vào số khoảng trống nhìn được trong console.

Các dòng được đặt theo đúng số cột thụt đầu dòng trong đoạn Java mẫu; nếu thay đổi **vị trí thụt của dấu đóng** hoặc thụt nội dung không nhất quán, giá trị `margin` cũng có thể thay đổi theo quy tắc xử lý indentation.

## 5. Dấu đóng trên dòng riêng: điều gì quyết định LF cuối?

Với cách viết điển hình:

~~~java
String message = """
    one
    two
    """;
~~~

văn bản mã nguồn có dấu xuống dòng **sau chữ `two` và trước dấu đóng**. Dấu xuống dòng đó thuộc **content** của text block, vì nội dung được tính tới ngay trước dấu đóng. Sau chuẩn hóa, nó trở thành `\n` ở cuối String.

Nhưng **không** phải mọi trường hợp có dấu đóng nằm trên dòng riêng đều tự động tạo thêm một LF. Hãy xét rõ các ngoại lệ:

- Nếu dòng nội dung trước dấu đóng kết thúc bằng escape nối dòng ``, line terminator bị lược đi theo quy tắc escape.
- Nếu text block không có ký tự nội dung nào trước closing delimiter thì không nên suy ra có LF cuối chỉ từ việc dấu đóng xuất hiện trên một dòng riêng.
- Một dòng **trống** có chủ đích trước dấu đóng thêm một line terminator nữa, không phải chỉ đổi vị trí dấu đóng.

**Cách nói chính xác:** giá trị String chứa LF cuối khi **nội dung sau xử lý** còn một LF ngay trước vị trí closing delimiter. Trong trường hợp thông thường, đặt dấu đóng ở dòng riêng giữ LF của dòng nội dung cuối; đặt dấu đóng ngay sau ký tự cuối loại bỏ LF đó.

## 6. Một cách khác để bỏ LF cuối: escape backslash + line terminator

Nếu muốn các dấu đóng của nhiều text blocks nhất quán trên **dòng riêng** nhưng không muốn ký tự LF cuối, có thể viết:

~~~java
String noLastLf = """
    first
    second\
    """;
~~~

Giá trị là `"first\nsecond"`.

Đây là **line-continuation escape**: một dấu `` được đặt **ngay trước line terminator trong mã nguồn**. Khi escape được xử lý, dấu `` cùng line terminator đó không còn trong giá trị String.

Cần phân biệt:

~~~java
String explicitLf = """
    first
    second\n""";
~~~

Giá trị ở đây là `"first\nsecond\n"`, vì `\n` là **escape tạo LF** ngay trước dấu đóng trên cùng dòng.

| Trường hợp | Vị trí/cú pháp | Giá trị |
| --- | --- | --- |
| LF tự nhiên cuối dòng | `second` rồi xuống dòng, đóng riêng | `"first\nsecond\n"` |
| Không có LF cuối | `second"""` | `"first\nsecond"` |
| Nối dòng, bỏ LF cuối | `second` rồi xuống dòng, đóng riêng | `"first\nsecond"` |
| LF tường minh | `second\n"""` | `"first\nsecond\n"` |

**Tránh lỗi khó nhận ra:** dấu backslash để nối dòng phải ở **ngay trước** line terminator; thêm dấu cách sau `` hoặc thêm ký tự khác sẽ thay đổi cú pháp và có thể khiến source không biên dịch. Khi review, nên bật hiển thị trailing spaces của editor nếu dùng kiểu viết này.

Line continuation cũng có thể được dùng ở các dòng giữa text block. Khi nối các dòng, hãy nhớ rằng ký tự xuống dòng của source bị bỏ đi, nên hai đoạn chữ có thể dính sát nếu không có dấu cách có chủ đích.

## 7. Vị trí dấu đóng còn ảnh hưởng indentation

Ngoài LF cuối, vị trí **ngang** của closing delimiter trên một dòng riêng có thể quyết định **khoảng trắng đầu dòng nào được giữ lại**.

Text block có bước loại bỏ **incidental white space** để source code có thể thụt vào theo cấu trúc class/method mà không đưa toàn bộ khoảng trắng thụt đó vào dữ liệu. Trình biên dịch sử dụng mức thụt chung dựa trên các dòng nội dung không trống và, khi dấu đóng ở dòng riêng, cả lề của dòng dấu đóng.

Ví dụ:

~~~java
String aligned = """
        A
          B
        """;
~~~

Kết quả là `"A\n  B\n"`, trong đó dòng `B` còn **hai khoảng trắng có ý nghĩa** so với dòng `A`. Dấu đóng cùng lề với `A` nên phần lề chung được tước bỏ.

Dời dấu đóng sang trái 4 cột:

~~~java
String preserved = """
        A
          B
    """;
~~~

Kết quả là `"    A\n      B\n"`: mỗi dòng giữ thêm 4 khoảng trắng. Điều này khác với việc đặt dấu đóng ở **cuối dòng `B`**, vì khi đó **không có dòng closing-delimiter riêng** để tham gia xác định lề thụt chung.

### Minh họa lề với dấu phân cách

Nếu chỉ dùng `println(aligned)` thì khó quan sát khoảng trắng đầu dòng. Có thể thay mỗi khoảng trắng bằng `·` khi kiểm thử:

~~~java
System.out.println(aligned.replace(" ", "·")
                          .replace("\n", "\\n"));
System.out.println(preserved.replace(" ", "·")
                            .replace("\n", "\\n"));
~~~

Đầu ra:

~~~text
A\n··B\n
····A\n······B\n
~~~

**Lưu ý:** trong đoạn này ký tự `·` chỉ là ký hiệu **hiển thị** khoảng trắng; nội dung thật của chuỗi vẫn chứa các dấu cách thông thường. Đừng thay khoảng trắng bằng dấu chấm khi tạo payload thực.

### Quy tắc thực hành cho dấu đóng và lề

- Nếu muốn lề của nội dung được tước sạch và **giữ LF cuối**, đặt dấu đóng trên dòng riêng cùng lề với nội dung ít thụt nhất.
- Nếu muốn giữ một phần khoảng trắng **đầu dòng** như dữ liệu, đặt dấu đóng trên dòng riêng **ít thụt hơn** nội dung theo số cột muốn giữ, hoặc thiết kế chuỗi/bước biến đổi có chủ đích.
- Nếu đóng ngay sau ký tự cuối của dòng cuối, đoạn cuối đó không có line terminator tự nhiên; theo hướng dẫn của Oracle, kỹ thuật dùng dòng dấu đóng để điều khiển mức thụt **không áp dụng theo cùng cách** khi dòng cuối không kết thúc bằng newline. Khi thật sự cần lề cố định không có LF cuối, cân nhắc `String.indent(...)` sau khi tạo text block hoặc bố trí nội dung khác cho dễ kiểm soát.
- Tốt nhất giữ thụt lề bằng **spaces nhất quán** và tránh trộn tabs với spaces ở các dòng nguồn; editor có thể làm chúng hiển thị tương đương nhưng thuật toán whitespace của Java xử lý ký tự thật.

Từng dòng có thể giữ **khoảng trắng tương đối** theo ý đồ, như phần thân HTML hoặc cây dữ liệu. Text blocks không tự căn lại cấu trúc HTML/JSON/SQL; chúng chỉ xử lý whitespace theo quy tắc literal.

## 8. Thứ tự xử lý line terminator, whitespace và escape

Java xử lý nội dung text block theo ba giai đoạn có ảnh hưởng trực tiếp tới chủ đề này:

1. **Chuẩn hóa line terminators**: các kiểu kết thúc dòng của mã nguồn (LF, CR, CRLF) trong text block được chuẩn hóa thành **LF `\n`**.
2. **Loại bỏ incidental white space**: phần indentation chung và trailing spaces ngẫu nhiên được xử lý theo quy tắc text block.
3. **Dịch escape sequences**: chẳng hạn `\n` tạo một LF, `\s` biểu diễn dấu cách và `` ngay trước line terminator nối dòng.

Bởi vậy:

- Text block mã nguồn đang dùng CRLF trên Windows **không đồng nghĩa** String kết thúc bằng CRLF; mặc định line terminators của text block được chuẩn hóa thành `\n`.
- `\n` được viết rõ trong source là một escape tạo LF ở bước cuối, khác với LF thực tế tách hai dòng nguồn nhưng cho cùng ký tự LF trong String.
- `` ngay trước line terminator **bỏ** line terminator tương ứng trong String, do xử lý escape sau giai đoạn chuẩn hóa.
- Muốn giữ dấu cách cuối dòng có ý nghĩa, không nên dựa vào trailing spaces vô hình của source. Có thể dùng escape `\s` (được xử lý sau bước xóa trailing whitespace), hoặc cách tạo dữ liệu khác.

Ví dụ riêng cho một dấu cách cuối dòng:

~~~java
String line = """
    hello\s
    """;
~~~

Giá trị là `"hello \n"`: có một dấu cách sau chữ `hello` rồi tới LF. Nếu ký tự space nằm trực tiếp ở cuối dòng nguồn trước line terminator mà không được bảo vệ, nó có thể bị tước đi theo quy tắc incidental trailing whitespace.

**Điểm quan trọng:** `\s` giúp bảo toàn một dấu cách có chủ đích, không phải công cụ để bỏ LF cuối. Bỏ LF cuối cần đóng inline, dùng line-continuation escape, hoặc xử lý String sau khi tạo.

## 9. Thực hành kiểm tra LF cuối đáng tin cậy

Dấu xuống dòng là ký tự điều khiển nên khó nhìn trực tiếp. Dùng các phép kiểm tra có mục tiêu:

~~~java
String payload = """
    {"ok":true}
    """;

System.out.println(payload.endsWith("\n")); // true
System.out.println(payload.equals("{\"ok\":true}\n")); // true
System.out.println(payload.length());        // 12
~~~

Tính độ dài: `{"ok":true}` có **11** ký tự gồm dấu ngoặc và dấu nháy; thêm `\n` cuối thành **12**. Đừng nhầm dấu nháy bên trong JSON là dấu đóng text block: chỉ **ba dấu nháy kép liên tiếp** có thể là closing delimiter, các dấu `"` đơn trong JSON dùng bình thường.

Để in ký tự đặc biệt theo dạng nhìn được:

~~~java
static String showLf(String text) {
    return text.replace("\\", "\\\\")
               .replace("\r", "\\r")
               .replace("\n", "\\n");
}
~~~

Đây là mảnh phương thức dùng để hỗ trợ debug. Nó hiển thị `\n` bằng hai ký tự `` và `n`, phân biệt với dấu backslash thật và `\r`. Khác với `println(payload)`, phương thức này cho thấy LF thuộc nội dung.

### Không dùng riêng `println` để phán đoán

~~~java
String value = """
    hi
    """;

System.out.println(value);
~~~

Có **LF trong `value`**, rồi `println` bổ sung một **line separator của hệ thống**. Có thể thấy một dòng trống trên terminal, nhưng điều đó không có nghĩa String chứa hai LF cuối. Kiểm tra `value.endsWith("\n")` hoặc so sánh trực tiếp là cách chắc chắn hơn.

### `lines()` không phải phép thử LF cuối

`String.lines()` tách chuỗi thành các dòng theo cách không nhất thiết tạo phần tử rỗng riêng cho **chỉ một line terminator cuối**. Do vậy, dựa vào `lines().count()` không đủ để xác định chắc chắn text block có `\n` cuối hay không. Để kiểm tra LF cuối, dùng `endsWith("\n")`, hoặc xét ký tự cuối nếu String không rỗng.

### Test snapshot/golden file

Khi test dữ liệu text block, hãy khẳng định **giá trị String mong muốn**, không chỉ số dòng:

~~~java
String expected = "red\ngreen\nblue\n";
String actual = """
    red
    green
    blue
    """;

if (!expected.equals(actual)) {
    throw new AssertionError("Text block differs");
}
~~~

Trong thực tế, nếu hệ thống chuẩn hóa whitespace khi so sánh thì cần quyết định chính sách đó **một cách tường minh**. Đừng tự `strip()` hoặc `trim()` trong phép thử nếu hợp đồng yêu cầu bảo toàn dấu xuống dòng cuối.

## 10. Chọn vị trí dấu đóng theo mục đích dữ liệu

| Tình huống | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| HTML/SQL/template nhiều dòng và yêu cầu chuỗi kết thúc LF | Dấu đóng trên dòng riêng, cùng lề với nội dung | Dễ đọc, LF cuối rõ ràng |
| JSON payload phải khớp byte-for-byte với mẫu không có LF cuối | Dấu đóng inline ở cuối ký tự cuối | Không thêm ký tự LF vào giá trị |
| Muốn đặt tất cả dấu đóng riêng nhưng bỏ LF cuối | `` cuối dòng nội dung trước dấu đóng | Giữ layout source thống nhất, cần thận trọng trailing spaces |
| Cần bảo toàn 4 dấu cách đầu mỗi dòng nội dung | Đặt closing delimiter trên dòng riêng ít thụt hơn 4 cột | Biểu đạt lề theo quy tắc incidental whitespace |
| Cần một dòng trống thực sự ở cuối | Thêm một dòng trống nội dung trước dấu đóng | Có thêm một LF trong String |
| Đầu ra file yêu cầu CRLF | Tạo String có quy tắc line ending rõ và chuyển đổi khi xuất | Text block tự chuẩn hóa line terminator nguồn thành LF |
| Chuỗi chỉ có một dòng ngắn | Dùng literal thường `"text"` | Gọn và ít rủi ro vị trí dấu đóng |

**Quy tắc thiết kế:** thứ tự ưu tiên là **giá trị String cần tạo** → **cách đặt closing delimiter** → **kiểm thử chính xác**. Đừng chọn vị trí dấu đóng chỉ để code trông đẹp mà không kiểm tra hợp đồng dữ liệu.

Với SQL và JSON, parser thường bỏ qua một số whitespace ngoài nội dung cú pháp, nhưng điều đó không có nghĩa mọi hệ thống đều không quan tâm LF: hash, chữ ký số, checksum, cache key, snapshot test và body của HTTP vẫn có thể phân biệt hai chuỗi.

## 11. Những lỗi phổ biến

| Hiểu nhầm | Thực tế và cách xử lý |
| --- | --- |
| “Text block tự thêm newline ở cuối.” | Không phải lúc nào cũng có: nó phụ thuộc nội dung trước closing delimiter và escape. |
| “Dấu đóng trên dòng riêng không ảnh hưởng dữ liệu.” | Thông thường nó giữ lại LF của dòng cuối; còn có thể ảnh hưởng incidental indentation. |
| “Dấu mở tạo LF ở đầu String.” | Line terminator sau opening delimiter là bắt buộc về cú pháp nhưng không nằm ở đầu nội dung. |
| “Thụt dấu đóng sâu hay nông chỉ thay format source.” | Trên dòng riêng, nó có thể thay đổi số khoảng trắng đầu mỗi dòng trong giá trị String. |
| “CRLF trong file nguồn thì String chắc chắn là CRLF.” | Text block chuẩn hóa line terminator nguồn về LF. |
| “`println` cho thấy chính xác số LF cuối trong String.” | `println` tự thêm line separator. Dùng `endsWith` hoặc hiển thị escape. |
| “`\s` bỏ ký tự LF cuối.” | `\s` tạo khoảng trắng, không bỏ LF. |
| “`\n` và dấu `` cuối dòng giống nhau.” | `\n` tạo LF; `` + line terminator nguồn loại bỏ line terminator. |
| “Chỉ đổi vị trí `"""` mà giá trị vẫn nguyên.” | Có thể đổi LF cuối, thụt lề hoặc cả hai; phải test. |
| “`String.lines().count()` chứng minh có LF cuối.” | Không phải phép thử xác định LF cuối; dùng `endsWith("\n")`. |
| “`strip()`/`trim()` luôn là cách xử lý tốt.” | Chúng có thể bỏ whitespace hợp lệ; chỉ dùng khi hợp đồng cho phép chuẩn hóa. |

## 12. Checklist review text block

1. Dấu mở `"""` có line terminator bắt buộc phía sau chưa? Có vô tình viết text block trên một dòng không?
2. Giá trị cần **có hay không có `\n` cuối**? Dấu đóng đang ở dòng riêng hay cùng dòng ký tự cuối?
3. Có `` ngay trước line terminator hoặc `\n` tường minh nào làm thay đổi kết quả mong muốn không?
4. Có dòng trống có chủ đích ngay trước dấu đóng khiến chuỗi có **nhiều LF cuối** không?
5. Dấu đóng trên dòng riêng đặt ở cột nào? Mức thụt đó có làm thay đổi nội dung mong muốn không?
6. Source có trộn tabs/spaces hoặc trailing spaces khiến kết quả khó dự đoán không?
7. Có khác biệt line ending giữa hệ điều hành hay yêu cầu xuất file không?
8. Đã kiểm tra `equals`, `endsWith("\n")` và độ dài ở những chỗ byte/character quan trọng chưa?
9. Có vô tình tin vào kết quả trực quan của `println` hoặc whitespace normalization của parser không?
10. Nếu chỉ là một chuỗi một dòng đơn giản, liệu dùng literal `"..."` có phù hợp hơn?

## 13. Bài tập có đáp án

### Bài 1 — Dự đoán hai kết quả

~~~java
String a = """
    A
    B
    """;

String b = """
    A
    B""";
~~~

**Câu hỏi:** `a.equals(b)` bằng bao nhiêu, và `a.length() - b.length()` bằng bao nhiêu?

**Đáp án:** `false` và `1`. Hai chuỗi khác đúng một LF cuối: `a` là `"A\nB\n"`, `b` là `"A\nB"`.

### Bài 2 — Có một hay hai LF cuối?

~~~java
String a = """
    x
    """;

String b = """
    x

    """;
~~~

**Đáp án:** `a` = `"x\n"`; `b` = `"x\n\n"`. Dòng trống nội dung ngay trước dấu đóng là một dòng thực sự, không phải ký tự trang trí.

### Bài 3 — So sánh inline và nối dòng

~~~java
String inline = """
    hello""";

String continuation = """
    hello\
    """;
~~~

**Đáp án:** cả hai đều là `"hello"`; `inline.equals(continuation)` bằng `true`. Chúng khác cách viết source nhưng giống kết quả sau xử lý.

### Bài 4 — Lề giữ lại

~~~java
String value = """
        one
          two
    """;
~~~

**Câu hỏi:** `value` có còn dấu cách ở đầu các dòng không?

**Đáp án:** có. Dấu đóng ít thụt hơn dòng nội dung 4 spaces, nên giá trị là `"    one\n      two\n"`. Cách kiểm tra: `value.replace(" ", "·").replace("\n", "\\n")`.

### Bài 5 — Tại sao test sai?

Một người viết:

~~~java
String expected = "{\"ok\":true}";
String actual = """
    {"ok":true}
    """;
System.out.println(expected.equals(actual));
~~~

**Đáp án:** in `false` vì `actual` là `"{\"ok\":true}\n"` còn `expected` không có LF cuối. Có thể sửa bằng cách đưa dấu đóng lên cùng dòng với dấu `}` cuối, hoặc sửa expected nếu LF cuối là một phần hợp đồng. Không nên tự `trim()` chỉ để ép test pass khi cần so sánh chính xác.

### Bài 6 — Kết quả khác nhau trên Windows?

Text block trong mã nguồn dùng CRLF, nhưng test mong đợi `"a\nb\n"`. Đây có nhất thiết là lỗi không?

**Đáp án:** không. Compiler chuẩn hóa line terminator trong text block thành LF. Nếu output file phải có CRLF, chuyển đổi ở biên ghi file theo chính sách định dạng; không phụ thuộc line terminators trong editor.

## 14. Tài liệu chính thức còn áp dụng

- [Oracle — Text Blocks (Java 26)](https://docs.oracle.com/en/java/javase/26/language/text-blocks.html): cú pháp, vị trí dấu đóng, “That Final New Line”, incidental whitespace, normalize line terminators và escape.
- [Oracle — Programmer's Guide to Text Blocks (Java 17)](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): hướng dẫn sử dụng text block và các ví dụ thực tế.
- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): đặc tả thiết kế tính năng chính thức từ Java 15, gồm cách xử lý newline và indentation.
- [Java Language Specification, §3.10.6 — Text Blocks (Java 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): phạm vi nội dung giữa opening/closing delimiter và các quy tắc lexical của text block.

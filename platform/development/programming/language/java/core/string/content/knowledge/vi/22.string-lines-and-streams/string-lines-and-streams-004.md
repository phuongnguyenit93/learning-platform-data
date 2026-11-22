# String.indent(int): thay đổi lề và chuẩn hóa kết thúc dòng trong Java

## 1. Mục tiêu bài học

Khi ghép văn bản nhiều dòng để hiển thị log, sinh nội dung hoặc trình bày dữ liệu, ta thường muốn tăng hoặc giảm số ký tự trắng ở **đầu từng dòng**. Java cung cấp **String.indent(int n)** (từ **Java 12**) để thực hiện thao tác này, đồng thời **chuẩn hóa ký tự kết thúc dòng về LF**.

Sau bài học, bạn có thể:

- Giải thích tác dụng của **n > 0**, **n < 0** và **n = 0**.
- Dự đoán chính xác kết quả với dấu cách, tab, dòng trống, CR, LF, CRLF và chuỗi không có newline.
- Phân biệt **indent()** với **lines()**, **stripLeading()**, **stripIndent()** và cách ghép thủ công.
- Tránh các lỗi thường gặp khi xử lý văn bản từ Windows, Unix, text block và dữ liệu có định dạng cố định.

Điểm quan trọng: **indent() không chỉ thay đổi khoảng trắng ở đầu dòng**. Một lời gọi **indent(0)** cũng có thể thay đổi chuỗi vì ký tự kết thúc dòng được chuẩn hóa và dòng cuối có thể được thêm LF.

## 2. Chữ ký phương thức và cơ chế tổng quát

~~~java
public String indent(int n)
~~~

Đây là phương thức của **java.lang.String**. String bất biến: phương thức trả về một String kết quả, không sửa đối tượng nguồn.

Về mặt khái niệm, Java thực hiện:

1. Tách chuỗi đầu vào thành các dòng theo quy tắc tương tự **String.lines()**.
2. Điều chỉnh các ký tự trắng **ở đầu mỗi dòng** theo tham số **n**.
3. Ghép các dòng đã điều chỉnh, **mỗi dòng theo sau bằng LF** (ký tự **\n**, U+000A).

Quy tắc theo tham số:

| Giá trị n | Tác động lên từng dòng | Lưu ý |
| --- | --- | --- |
| **n > 0** | Thêm đúng **n dấu cách ASCII U+0020** ở đầu dòng | Không phải thêm n tab; áp dụng cả dòng rỗng |
| **n = 0** | Không đổi nội dung của từng dòng | Vẫn chuẩn hóa kết thúc dòng và có thể thêm LF cuối |
| **n < 0** | Bỏ tối đa **\|n\| ký tự whitespace** ở đầu mỗi dòng | Nếu có ít hơn \|n\| ký tự trắng thì bỏ hết; phần nội dung còn lại được giữ |
| **Chuỗi rỗng** | Trả về chuỗi rỗng | Không tự tạo một dòng hoặc newline |

Phương thức xử lý **từng dòng độc lập**. Nó không tìm “lề chung” rồi chỉ bỏ đúng mức lề tối thiểu của toàn khối. Đó là điểm khác biệt quan trọng với **stripIndent()**.

## 3. Thế nào là một dòng và ký tự kết thúc dòng?

**String.lines()** nhận diện ba kiểu dấu kết thúc dòng sau:

| Ký tự | Ký hiệu | Thường gặp |
| --- | --- | --- |
| Line Feed | **\n** (LF, U+000A) | Linux/Unix và nhiều API |
| Carriage Return | **\r** (CR, U+000D) | Dữ liệu cũ hoặc một số nguồn |
| CR rồi LF | **\r\n** (CRLF) | Văn bản Windows |

**indent()** chuẩn hóa tất cả những kiểu kết thúc dòng đó thành **\n**.

Một dòng là phần ký tự **không bao gồm dấu kết thúc dòng** của nó. Nếu chuỗi đã kết thúc bằng một dấu xuống dòng, **lines() không tạo thêm một dòng rỗng ảo sau dấu cuối cùng**.

Ví dụ:

~~~text
Input khái niệm:  A\r\nB\rC\n
Các dòng:         "A", "B", "C"
Sau indent(0):    A\nB\nC\n
~~~

Hai hệ quả dễ bất ngờ:

- Với input **"A"** (không có ký tự xuống dòng), **"A".indent(0)** trả **"A\n"**.
- Với input **"A\n"**, **"A\n".indent(0)** vẫn là **"A\n"**, không biến thành **"A\n\n"**.

Chuỗi **""** không có dòng nào nên **"".indent(0)** và **"".indent(2)** đều là **""**.

**Phạm vi chuẩn hóa của indent() là ba loại line terminator nói trên.** Không nên suy diễn rằng nó nhận diện và đổi mọi ký tự Unicode có thể trông giống xuống dòng, ví dụ Unicode line separator U+2028. Đừng nhầm với quy tắc rộng hơn của regex **\R**.

## 4. Ví dụ Java 17+ chạy độc lập, hiển thị rõ khoảng trắng

Khi dùng **System.out.println()**, khoảng trắng ở đầu dòng thường khó nhìn và **println()** còn thêm newline của chính nó. Ví dụ sau chuyển dấu cách thành dấu **_**, tab thành **<TAB>**, LF thành chữ **\n** và CR thành chữ **\r** trước khi in. Dấu gạch dưới chỉ là **ký hiệu hiển thị**, không phải ký tự mà **indent()** chèn vào chuỗi thật.

Tạo tệp **IndentDemo.java**:

~~~java
public class IndentDemo {
    private static String visible(String text) {
        return text.replace(" ", "_")
                .replace("\t", "<TAB>")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    private static void show(String label, String text) {
        System.out.println(label + ": [" + visible(text) + "]");
    }

    public static void main(String[] args) {
        String mixed = "A\r\n  B\rC\n";

        show("origin", mixed);
        show("indent(+2)", mixed.indent(2));
        show("indent(-2)", mixed.indent(-2));
        show("indent(0)", mixed.indent(0));

        show("blank line", "X\n\nY".indent(2));
        show("tab", "  X\n\tY\nZ".indent(-1));
        show("empty", "".indent(2));
        show("one line", "X".indent(0));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac IndentDemo.java
java IndentDemo
~~~

Kết quả:

~~~text
origin: [A\r\n__B\rC\n]
indent(+2): [__A\n____B\n__C\n]
indent(-2): [A\nB\nC\n]
indent(0): [A\n__B\nC\n]
blank line: [__X\n__\n__Y\n]
tab: [_X\nY\nZ\n]
empty: []
one line: [X\n]
~~~

Giải thích cụ thể:

1. Input **mixed** gồm ba dòng. Dòng **B** vốn đã có hai dấu cách đầu dòng.
2. **indent(2)** thêm hai dấu cách vào **mọi dòng**, nên B có tổng cộng bốn dấu cách. Đồng thời CRLF và CR đều trở thành LF.
3. **indent(-2)** bỏ hai dấu cách của B, còn A/C không có dấu cách đầu nên giữ nguyên phần chữ.
4. **indent(0)** giữ đúng hai dấu cách trước B nhưng vẫn đổi ba loại kết thúc dòng về LF.
5. Với dòng trống nằm giữa X và Y, **indent(2)** vẫn thêm hai dấu cách vào dòng trống, khiến dòng đó không còn là chuỗi có độ dài 0 nếu xét nội dung ký tự.
6. **indent(-1)** bỏ một ký tự trắng đầu dòng: từ hai dấu cách của X còn một, còn tab đứng đầu Y bị bỏ hoàn toàn.
7. Chuỗi rỗng vẫn rỗng; chuỗi **"X"** có một dòng nên được thêm LF ở cuối sau **indent(0)**.

## 5. n dương: thêm dấu cách vào đầu mỗi dòng

Khi **n > 0**, Java tạo đúng **n ký tự space U+0020** và đặt ở đầu mỗi dòng.

~~~java
String data = "first\nsecond";
String result = data.indent(4);

System.out.println(result.equals("    first\n    second\n")); // true
~~~

Không quan trọng dòng đã có lề hay chưa; **indent(4)** không căn chỉnh các dòng về một cột tuyệt đối mà **tăng thêm 4 dấu cách cho mỗi dòng**.

Với chuỗi:

~~~text
first
  second
~~~

sau **indent(2)**, mức lề tương đối vẫn chênh nhau hai dấu cách:

~~~text
  first
    second
~~~

Cần phân biệt:

- **indent(2)** tăng mức lề của **từng dòng** lên hai dấu cách.
- **String.repeat(2)** lặp lại **toàn bộ chuỗi** hai lần; không liên quan đến quy tắc tăng lề.
- Gọi **indent(2)** hai lần thường thêm tổng cộng bốn dấu cách vào mỗi dòng không rỗng về mặt tách dòng; phương thức không tự nhận biết “đã thụt lề trước đó”.

**Dòng trống:** nếu đầu vào có dòng trống thật sự giữa hai terminator, **indent(n > 0)** cũng chèn dấu cách vào dòng trống ấy:

~~~java
String input = "A\n\nB";
String result = input.indent(2);
System.out.println(result.equals("  A\n  \n  B\n")); // true
~~~

Nếu một hệ thống cần dòng trống có độ dài đúng 0 hoặc cấm trailing whitespace, cần cân nhắc bước xử lý khác. **indent() không tự động loại khoảng trắng ở dòng rỗng**.

## 6. n âm: bỏ tối đa |n| ký tự trắng ở đầu từng dòng

Khi **n < 0**, Java loại bỏ từ 0 đến **|n|** ký tự whitespace ở **đầu mỗi dòng**, tùy lượng ký tự có thật.

~~~java
String text = "    A\n B\nC";
String result = text.indent(-3);

System.out.println(result.equals(" A\nB\nC\n")); // true
~~~

- Dòng A có bốn dấu cách: bỏ ba, còn một.
- Dòng B có một dấu cách: bỏ một, còn không.
- Dòng C không có dấu cách: không bỏ gì.

Nếu đầu dòng có ít hơn **|n|** ký tự trắng, phương thức **không xóa lấn sang ký tự không phải whitespace**. Ví dụ **" A".indent(-5)** vẫn có phần chữ **A**, rồi LF.

### 6.1. Tab tính là một ký tự, không phải một độ rộng hiển thị

Java dùng khái niệm whitespace theo **Character.isWhitespace** cho việc bỏ lề âm. Ký tự tab **\t** được tính là **một ký tự trắng**, không tự mở thành 4 hay 8 cột:

~~~java
String source = "\t  A";
System.out.println(source.indent(-1).equals("  A\n")); // true
System.out.println(source.indent(-2).equals(" A\n"));  // true
~~~

Độ rộng hiển thị thực tế của tab còn tùy tab stop trong terminal/editor. Vì vậy, **indent(-2)** nghĩa là bỏ tối đa **hai ký tự whitespace**, không bảo đảm lùi trái hai **cột thị giác**.

Java không chỉ xem dấu cách ASCII là whitespace. Nhưng cũng không phải **mọi ký tự Unicode trông giống dấu cách** đều thỏa **Character.isWhitespace**. Nếu nhập liệu chứa Unicode đặc biệt, hãy kiểm tra loại ký tự và quy tắc mong muốn.

### 6.2. indent(-n) khác với bỏ một mức lề chung

Xét ba dòng:

~~~text
    A
  B
      C
~~~

Dùng **indent(-2)** sẽ bỏ hai ký tự trắng ở đầu mỗi dòng, cho:

~~~text
  A
B
    C
~~~

Không có bước nào phân tích toàn khối để suy ra “lề chuẩn”. Nếu cần loại **common/incidental indentation**, hãy xem **stripIndent()** thay vì giả định **indent(-n)** hoạt động như nó.

## 7. n bằng 0: tại sao kết quả vẫn thay đổi?

**indent(0)** không thay đổi ký tự của từng dòng đã được tách, nhưng **nó vẫn xây dựng lại chuỗi với LF kết thúc mỗi dòng**.

~~~java
String input = "red\r\ngreen\rblue";
String output = input.indent(0);

System.out.println(output.equals("red\ngreen\nblue\n")); // true
System.out.println(input.equals(output));               // false
~~~

Input có CRLF, CR và không có terminator cuối. Output gồm ba dòng đều kết thúc bằng LF.

Điều này hữu ích khi bạn muốn chuyển văn bản nhiều dòng từ các nền tảng khác nhau về **dạng LF thống nhất** mà giữ nguyên các ký tự đầu mỗi dòng.

Tuy nhiên, có hai giới hạn cần nhớ:

- **Thêm LF ở cuối:** nếu input không rỗng và dòng cuối chưa có terminator, **indent(0)** thêm LF. Vì vậy đây không phải bộ chuẩn hóa chỉ thay CRLF/CR thành LF rồi giữ nguyên hoàn toàn sự có/mất newline cuối.
- **Dòng trống có trước:** các dòng trống thật sự vẫn được giữ theo quy tắc **lines()**, với các terminator đầu ra là LF. Không có dòng rỗng ảo mới được sinh ra *sau* terminator cuối của input.

Ví dụ về khác biệt dấu kết thúc:

| Input là Java String literal | Kết quả sau **indent(0)** |
| --- | --- |
| **""** | **""** |
| **"A"** | **"A\n"** |
| **"A\n"** | **"A\n"** |
| **"A\r"** | **"A\n"** |
| **"A\r\n"** | **"A\n"** |
| **"A\n\n"** | **"A\n\n"** |
| **"\n"** | **"\n"** |

Bảng dùng **ký hiệu Java String literal**: chẳng hạn **"A\n"** chứa một ký tự A và một ký tự LF, không chứa hai ký tự dấu gạch chéo ngược và n.

## 8. Dòng rỗng, whitespace cuối dòng và các trường hợp biên

### 8.1. indent() chỉ sửa phần đầu mỗi dòng

**indent() không cắt whitespace ở cuối nội dung dòng**:

~~~java
String input = "A  \n B  ";
String out = input.indent(-1);

System.out.println(out.equals("A  \nB  \n")); // true
~~~

Hai dấu cách sau A và hai dấu cách sau B vẫn tồn tại. Muốn cắt khoảng trắng cuối dòng, cần xử lý riêng theo nghiệp vụ.

### 8.2. Chuỗi có nhiều terminator liên tiếp

~~~java
String input = "A\r\n\r\nB";
System.out.println(input.indent(0).equals("A\n\nB\n")); // true
~~~

CRLF là một terminator; CRLF tiếp theo biểu diễn một **dòng rỗng thực sự** giữa A và B. Sau chuẩn hóa, vẫn có một dòng rỗng ở giữa.

### 8.3. Chuỗi chỉ chứa dấu cách

~~~java
String spaces = "   ";
System.out.println(spaces.indent(-2).equals(" \n"));  // true
System.out.println(spaces.indent(-5).equals("\n"));   // true
System.out.println(spaces.indent(2).equals("     \n")); // true
~~~

Đây là **một dòng có nội dung chỉ gồm khoảng trắng**, không phải chuỗi rỗng. Kết quả vẫn có LF cuối dòng. Nếu nghiệp vụ muốn xóa bỏ toàn bộ các dòng trắng, cần quyết định quy tắc rõ ràng; **indent() không mặc định lọc dòng**.

### 8.4. Giá trị n cực lớn

Tránh gọi **indent(n)** với giá trị dương khổng lồ lấy trực tiếp từ người dùng: phép thêm ký tự diễn ra **theo mỗi dòng**, có thể làm bộ nhớ cần thiết tăng mạnh hoặc vượt giới hạn String/heap. Số lượng ký tự được thêm xấp xỉ **n × số dòng**.

Với **n âm**, hành vi là bỏ tối đa số ký tự trắng hiện có, không thể xóa ký tự nội dung. Java xử lý được cả trường hợp **Integer.MIN_VALUE** mà không cần bạn tự lấy **Math.abs(n)**; tự tính **Math.abs(Integer.MIN_VALUE)** trong mã phụ trợ có thể tràn số nguyên nên cần tránh.

## 9. So sánh với các phương thức String liên quan

| API | Mục đích | Điểm khác so với **indent(int)** |
| --- | --- | --- |
| **lines()** (Java 11+) | Trả một Stream các dòng, bỏ terminator | Không tự thêm/bớt lề hay trả String đã ghép |
| **stripLeading()** (Java 11+) | Bỏ whitespace ở **đầu toàn bộ String** | Không lặp qua mọi dòng |
| **stripTrailing()** (Java 11+) | Bỏ whitespace ở **cuối toàn bộ String** | Có thể ảnh hưởng newline cuối, không phải đổi lề từng dòng |
| **strip()** (Java 11+) | Bỏ whitespace hai đầu toàn bộ String | Không giữ nguyên cấu trúc nhiều dòng theo cùng cách |
| **stripIndent()** (Java 15+) | Loại common/incidental indentation, xử lý dòng trắng và trailing whitespace | Tính lề tối thiểu từ các dòng phù hợp; không đơn giản là bỏ n ký tự từng dòng |
| **repeat(int)** (Java 11+) | Lặp toàn bộ String n lần | Không thụt lề theo dòng |
| **indent(int)** (Java 12+) | Thêm hoặc bỏ tối đa số ký tự trắng đầu **mỗi dòng**, chuẩn hóa LF | Có tham số số lượng và luôn tái tạo terminator dạng LF |

### 9.1. indent(-2) khác stripLeading()

~~~java
String input = "  A\n  B";

System.out.println(input.indent(-2).equals("A\nB\n"));   // true
System.out.println(input.stripLeading().equals("A\n  B")); // true
~~~

**stripLeading()** chỉ loại dấu cách ở trước A, vì nó xử lý phần đầu của **toàn bộ chuỗi**; dấu cách trước B nằm sau newline nên vẫn tồn tại.

### 9.2. indent(-n) khác stripIndent()

**stripIndent()** (Java 15+) nhằm xử lý common/incidental indentation, đặc biệt phù hợp với text block. Nó xác định mức lề tối thiểu theo quy tắc riêng, loại mức lề ấy ở các dòng thích hợp và loại trailing whitespace theo định nghĩa của phương thức.

Ví dụ:

~~~java
String input = "    A\n  B\n      C";
String fixed = input.indent(-2);

System.out.println(fixed.equals("  A\nB\n    C\n")); // true
~~~

Trong ví dụ này, nếu mục tiêu là dịch toàn khối để dòng ít thụt nhất chạm lề trái, **stripIndent()** diễn đạt mục tiêu đó tự nhiên hơn. Đừng hoán đổi hai phương thức trong code nếu chưa kiểm tra dòng trống, dòng cuối, trailing whitespace và thay đổi line terminator, vì chúng có quy tắc khác nhau.

### 9.3. Text block và indent()

Text block (Java 15+) loại incidental indentation theo quy tắc riêng tại thời điểm tạo giá trị String. Sau đó bạn vẫn có thể gọi **indent()** lên giá trị ấy:

~~~java
String message = """
        hello
        world
        """;

System.out.println(message.indent(2).equals("  hello\n  world\n")); // true
~~~

Trong ví dụ này, text block gốc đã được xử lý lề chung, rồi **indent(2)** tăng thêm đúng hai dấu cách mỗi dòng.

Đừng đếm lề dựa chỉ vào vị trí dấu ngoặc text block trong source code: giá trị String thực tế sau khi Java áp dụng text block mới là đầu vào của **indent()**.

## 10. Ứng dụng thực tế

### 10.1. Thụt lề văn bản nhiều dòng trong báo cáo

~~~java
String detail = "name: Alice\nrole: developer";
String report = "User:\n" + detail.indent(2);

System.out.print(report);
~~~

Kết quả:

~~~text
User:
  name: Alice
  role: developer
~~~

Chọn **print()** để không thêm một newline ngoài ý muốn: **indent(2)** đã đặt LF ở cuối mỗi dòng của **detail**.

### 10.2. Chuẩn hóa kết thúc dòng từ nguồn khác nhau

~~~java
String imported = "first\r\nsecond\rthird";
String normalized = imported.indent(0);

System.out.println(normalized.equals("first\nsecond\nthird\n")); // true
~~~

Dạng LF thống nhất hữu ích khi so sánh nội dung text theo từng dòng hoặc đưa vào pipeline chỉ chấp nhận LF. Tuy nhiên, nếu checksum/file format yêu cầu giữ nguyên byte hay phân biệt rõ có/không có LF cuối, **indent(0)** là phép biến đổi có ý nghĩa, cần lựa chọn có chủ đích.

### 10.3. Giảm lề trong đoạn đã có lề cố định

~~~java
String source = "    GET /users\n    Accept: application/json";
String compact = source.indent(-4);

System.out.println(
        compact.equals("GET /users\nAccept: application/json\n")); // true
~~~

Nếu mỗi dòng có ít nhất bốn whitespace đầu dòng, **indent(-4)** loại đúng tối đa bốn ký tự. Nếu có dòng không đủ lề, nó chỉ bỏ phần có thể, không ném lỗi vì thiếu khoảng trắng.

## 11. Lỗi thường gặp và cách kiểm tra

1. **Nghĩ indent(0) sẽ giữ nguyên String.** Nó chuẩn hóa CR/CRLF thành LF và thêm LF cuối cho chuỗi không rỗng chưa có terminator. Kiểm tra bằng **equals()**, **length()** hoặc biểu diễn escape.
2. **Cho rằng n âm sẽ xóa đúng n cột hiển thị.** Tab được tính là một ký tự whitespace, không mở rộng theo tab stop; độ rộng thị giác có thể khác.
3. **Cho rằng indent(-n) tính common indentation của toàn khối.** Nó xóa tối đa |n| ký tự trên từng dòng độc lập. Khi muốn loại incidental indentation, cân nhắc **stripIndent()**.
4. **Bỏ qua dòng trống khi n dương.** Dòng trống cũng nhận n dấu cách; có thể trở thành dòng chỉ có whitespace.
5. **Dùng println() rồi tưởng indent() sinh hai newline.** Nếu String kết quả đã kết thúc bằng LF, **println()** có thể thêm một terminator nữa; dùng **print()** hoặc kiểm soát dấu xuống dòng khi ghép.
6. **Nghĩ indent() xóa dấu cách cuối dòng.** Nó chỉ chỉnh phần đầu; khoảng trắng ở cuối phần chữ vẫn còn.
7. **Cho rằng indent() xử lý mọi kiểu Unicode line separator.** Quy tắc tách dòng của **String.lines()** tập trung vào CR, LF, CRLF. Với định dạng dữ liệu khác cần phương án phân tích tương ứng.
8. **Đem indent(0) vào pipeline nhạy cảm byte mà không cân nhắc.** CRLF sang LF và thêm LF cuối là thay đổi nội dung; có thể làm khác checksum hoặc kết quả so sánh byte.
9. **Đọc text block như đúng số dấu cách trong source.** Text block đã có xử lý incidental indentation; nên xác minh giá trị String thực tế.
10. **Dùng n dương không giới hạn với input dài.** Có nguy cơ tăng kích thước dữ liệu và chi phí bộ nhớ rất lớn; ràng buộc độ dài và tham số theo bài toán.

## 12. Tự kiểm tra nhanh

Dự đoán kết quả rồi chạy các lệnh sau trong Java 17+:

~~~java
System.out.println("A".indent(0).equals("A\n"));
System.out.println("A\r\nB".indent(0).equals("A\nB\n"));
System.out.println("  A\n B".indent(-2).equals("A\nB\n"));
System.out.println("A\n\nB".indent(1).equals(" A\n \n B\n"));
System.out.println("\tX".indent(-1).equals("X\n"));
System.out.println("".indent(3).equals(""));
~~~

**Cả sáu dòng đều in true.** Nếu một kết quả gây bất ngờ, hãy xác định:

- Chuỗi gồm bao nhiêu dòng theo **lines()**?
- Mỗi dòng có bao nhiêu ký tự whitespace ở đầu?
- Phần đó bị **cộng n space** hay **trừ tối đa |n| whitespace**?
- Sau cùng, từng dòng có được nối bằng LF hay không?

## 13. Ghi nhớ

**String.indent(int n)** là thao tác **theo dòng**:

- **n dương:** thêm n dấu cách đầu **mọi dòng**, kể cả dòng trống.
- **n âm:** xóa tối đa |n| ký tự whitespace đầu từng dòng; tab được tính là một ký tự.
- **n bằng 0:** không đổi nội dung từng dòng, nhưng vẫn chuẩn hóa **CR/CRLF/LF → LF**.
- **Input rỗng:** output rỗng; **input không rỗng:** kết quả có LF sau dòng cuối.
- **Whitespace cuối dòng:** không bị xóa bởi **indent()**.

Khi lựa chọn API, hãy phân biệt rõ ba nhu cầu: **đổi lề theo số lượng xác định** (**indent**), **loại lề chung của khối** (**stripIndent**) và **chỉ xử lý đầu/cuối toàn bộ String** (**stripLeading/stripTrailing/strip**).

### Tài liệu tham khảo chính thức

- Java SE 17, **String.indent(int)**, **String.lines()** và **String.stripIndent()**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Java SE 17, **Character.isWhitespace(int)**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html

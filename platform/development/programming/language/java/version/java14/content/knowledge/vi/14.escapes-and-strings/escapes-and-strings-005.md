# String.stripIndent() trong xử lý văn bản nhiều dòng

## 1. Mục tiêu và ngữ cảnh

Trong Java, dữ liệu nhiều dòng có thể đến từ file, form, HTTP, cấu hình, log hoặc một chuỗi được ghép ở runtime. Mã nguồn cũng có thể chứa **text block** (cú pháp `"""`). Các dòng thường mang khoảng trắng để căn lề. Nếu muốn đưa toàn bộ khối văn bản sang trái mà vẫn **giữ thụt lề tương đối giữa các dòng**, Java cung cấp:

~~~java
String normalized = original.stripIndent();
~~~

`String.stripIndent()` là **phương thức instance trên `java.lang.String`**, trả về chuỗi đã bỏ phần thụt lề phụ (incidental indentation). Nó **không sửa chuỗi gốc**, bởi `String` bất biến. Phương thức được bổ sung từ **Java 15**, tiếp tục được hỗ trợ trong Java 17 và các phiên bản hiện đại. Các chương trình trong bài được kiểm chứng với `javac --release 17`.

Ví dụ với chuỗi **không có newline ở cuối**:

~~~java
String raw = "    alpha\n      beta\n    gamma";
String normalized = raw.stripIndent();
~~~

Giá trị `normalized` là:

~~~text
alpha
  beta
gamma
~~~

Java bỏ **bốn khoảng trắng chung** trước các dòng có nội dung; hai khoảng trắng bổ sung trước `beta` vẫn được giữ. Đây không phải thao tác xóa toàn bộ khoảng trắng đầu của **từng dòng**: nó cố bảo toàn cấu trúc tương đối của cả khối.

**Phân biệt phiên bản:** text blocks từng tồn tại dưới dạng preview trong Java 13/14, sau đó trở thành tính năng ổn định trong **Java 15**; bài học chỉ trình bày hành vi chuẩn hóa vẫn được hỗ trợ hiện nay. Không yêu cầu bật preview và không tuyên bố rằng `stripIndent()` có trong Java 14.

## 2. Quy tắc xử lý theo Java API hiện hành

Javadoc của `String.stripIndent()` nêu các bước quan trọng:

1. **Tách chuỗi thành các dòng.** Nhận biết LF (`\n`), CR (`\r`), hoặc cặp CRLF (`\r\n`) là line terminators. Mỗi dòng được xét không kèm ký tự kết thúc dòng.
2. **Tính độ thụt lề tối thiểu `min`.** Đếm số ký tự whitespace ở đầu **mỗi dòng không trắng** (theo `String.isBlank()`). **Dòng cuối cùng cũng góp phần vào phép tính, kể cả khi dòng đó trắng/rỗng**. Lấy số nhỏ nhất.
3. **Xử lý các dòng có nội dung.** Bỏ `min` ký tự whitespace ở đầu; đồng thời bỏ mọi whitespace ở cuối mỗi dòng.
4. **Xử lý dòng chỉ chứa whitespace.** Thay toàn bộ nội dung dòng trắng bằng chuỗi rỗng. Dòng trắng ở giữa vẫn được giữ dưới dạng *một dòng trống*.
5. **Nối lại các dòng** bằng LF (`\n`), chuẩn hóa mọi kiểu line terminators thành LF và **giữ nguyên số lượng line terminators**. Nếu ban đầu chuỗi kết thúc bằng line terminator thì kết quả cũng kết thúc bằng line terminator.

Đây là các quy tắc ở cấp **giá trị `String` tại runtime**, không phải thao tác sửa trực tiếp những dấu cách trong file mã nguồn.

### Ví dụ đếm indentation

~~~text
Dòng 1: "    alpha"          -> 4 whitespace đầu
Dòng 2: "      beta"         -> 6 whitespace đầu
Dòng 3: "    gamma"          -> 4 whitespace đầu
min = 4
~~~

Mỗi dòng có nội dung bị bỏ 4 ký tự đầu, còn độ thụt lề tương đối của beta là `6 - 4 = 2`. Những dòng trống trong khối **không** được tính là một dòng có nội dung với indentation 0, ngoại trừ **quy tắc đặc biệt dành cho dòng cuối** đã nêu ở bước 2.

**Whitespace là ký tự, không phải số cột màn hình.** Một dấu tab `\t` ở đầu dòng được tính là **một ký tự whitespace**, không được tự mở rộng thành 4 hoặc 8 cột. Nếu indentation trộn tabs và spaces không nhất quán, kết quả có thể không thẳng hàng về mặt hiển thị. Muốn nhất quán, hãy chuẩn hóa quy ước thụt lề ở nguồn.

## 3. Điểm dễ sai nhất: newline cuối khiến `min` bằng 0

Xét chuỗi:

~~~java
String endLF = "    alpha \n      beta \n";
String result = endLF.stripIndent();
~~~

Chuỗi kết thúc ngay sau `\n`. Do đó **dòng cuối sau LF là dòng rỗng**, có 0 whitespace đầu. Theo hợp đồng API, dòng cuối đó vẫn tham gia khi tính `min`; vậy **`min = 0`** dù hai dòng nội dung có 4 và 6 dấu cách ở đầu.

Kết quả **không bỏ** indentation ở đầu hai dòng, nhưng **vẫn bỏ** một dấu cách cuối mỗi dòng:

~~~text
"    alpha\n      beta\n"
~~~

Điều này là hợp lệ theo đặc tả, không phải lỗi của `stripIndent()`. Ví dụ trên là tình huống thường gặp khi đọc file văn bản có newline cuối.

So sánh với chuỗi:

~~~java
String closingIndent = "    alpha  \n      beta  \n    ";
String result = closingIndent.stripIndent();
~~~

Lần này dòng cuối cùng chứa **4 dấu cách** và được tính vào `min` như một dòng trắng cuối có indentation 4. Hai dòng nội dung có 4 và 6 dấu cách ở đầu, nên `min=4`. Dòng cuối bị chuyển thành rỗng, và kết quả:

~~~text
"alpha\n  beta\n"
~~~

**Cách ghi nhớ:** `stripIndent()` xem **dòng cuối** là một yếu tố khi xác định mức thụt lề, ngay cả khi dòng cuối là dòng trắng. Vì thế, chỉ nhìn các dòng có chữ mà suy ra `min` có thể sai. Không nên tuyên bố “`stripIndent` luôn xóa hết indentation nhỏ nhất của các dòng có chữ” nếu chưa xét dòng cuối.

### Muốn bỏ indentation nhưng vẫn giữ LF cuối phải làm gì?

Nếu **biết chắc đầu vào kết thúc bằng đúng một LF** và muốn giữ LF đó, có thể:

~~~java
String raw = "    alpha \n      beta \n";
String normalized = raw.substring(0, raw.length() - 1)
        .stripIndent() + "\n";
~~~

Kết quả là `"alpha\n  beta\n"`. Ta tạm bỏ LF cuối để phép tính `min` không bị dòng rỗng cuối ép bằng 0, sau đó thêm lại LF. Đoạn trên là ví dụ trong phương thức, không phải chương trình độc lập.

**Giới hạn:** ví dụ này dành cho chuỗi đã biết kết thúc bằng LF. Với CRLF, CR, nhiều newline cuối hoặc hợp đồng cần giữ dòng trắng đặc biệt, phải định nghĩa rõ chính sách chuẩn hóa và kiểm thử riêng. Đừng áp dụng `substring(length - 1)` vô điều kiện cho chuỗi rỗng hoặc chuỗi không kết thúc bằng LF. Một lựa chọn khác là điều chỉnh indentation có số ký tự xác định bằng `indent(-n)`, nhưng API đó có ngữ nghĩa khác, xem phần 7.

## 4. Chương trình Java 17+: các ca biên của `stripIndent()`

Tạo tệp **`StripIndentCases.java`**:

~~~java
public class StripIndentCases {
    static String visible(String input) {
        return input.replace("\\", "\\\\")
                .replace(" ", "<sp>")
                .replace("\t", "\\t")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    static void show(String label, String value) {
        System.out.println(label + ": \"" + visible(value)
                + "\" length=" + value.length());
    }

    public static void main(String[] args) {
        String noFinal = "    alpha  \r\n      beta \r\n    gamma";
        show("raw", noFinal);
        show("stripped", noFinal.stripIndent());

        String endsNewline = "    alpha \n      beta \n";
        show("endLF_raw", endsNewline);
        show("endLF_strip", endsNewline.stripIndent());

        String closingIndent = "    alpha  \n      beta  \n    ";
        show("closing_indent_strip", closingIndent.stripIndent());

        String interiorBlank = "   \n    alpha  \n      beta\t \n    gamma ";
        show("blank_strip", interiorBlank.stripIndent());

        String tabIndent = "\talpha\n\t\tbeta";
        show("tab_strip", tabIndent.stripIndent());

        String allBlank = "  \n \t \n";
        show("all_blank_strip", allBlank.stripIndent());

        String fixed = endsNewline
                .substring(0, endsNewline.length() - 1)
                .stripIndent() + "\n";
        show("preserve_final_newline_with_dedent", fixed);

        System.out.println("rawStillOriginal="
                + noFinal.startsWith("    alpha"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 StripIndentCases.java
java StripIndentCases
~~~

Stdout **đã kiểm tra trực tiếp**, với `<sp>` đại diện cho một dấu cách, `\n` là LF, `\r` là CR và `\t` là tab:

~~~text
raw: "<sp><sp><sp><sp>alpha<sp><sp>\r\n<sp><sp><sp><sp><sp><sp>beta<sp>\r\n<sp><sp><sp><sp>gamma" length=35
stripped: "alpha\n<sp><sp>beta\ngamma" length=18
endLF_raw: "<sp><sp><sp><sp>alpha<sp>\n<sp><sp><sp><sp><sp><sp>beta<sp>\n" length=23
endLF_strip: "<sp><sp><sp><sp>alpha\n<sp><sp><sp><sp><sp><sp>beta\n" length=21
closing_indent_strip: "alpha\n<sp><sp>beta\n" length=13
blank_strip: "\nalpha\n<sp><sp>beta\ngamma" length=19
tab_strip: "alpha\n\tbeta" length=11
all_blank_strip: "\n\n" length=2
preserve_final_newline_with_dedent: "alpha\n<sp><sp>beta\n" length=13
rawStillOriginal=true
~~~

Giải thích từng tình huống:

- **`raw → stripped`:** `stripIndent()` vừa xóa bốn ký tự indentation chung, vừa xóa trailing spaces ở dòng alpha/beta, vừa chuẩn hóa `\r\n` thành `\n`. Đây là thay đổi nội dung thực sự, không chỉ thay đổi cách hiển thị.
- **`endLF_strip`:** như phần 3, LF cuối tạo dòng rỗng cuối khiến `min=0`; độ thụt lề **vẫn còn** dù trailing space bị xóa. Dễ bị lầm tưởng là API không hoạt động.
- **`closing_indent_strip`:** dòng trắng cuối có 4 dấu cách cho phép tính `min=4`; kết quả mất phần thụt chung, vẫn có LF cuối.
- **`blank_strip`:** dòng đầu chỉ có spaces biến thành dòng rỗng, được giữ như một dòng trống đầu chuỗi (thể hiện bằng `\n` ở đầu). Dòng beta giữ hai dấu cách tương đối; tab và dấu cách ở cuối beta bị xóa.
- **`tab_strip`:** có một tab chung ở đầu, nên mỗi dòng bị bỏ một ký tự tab; dòng thứ hai vẫn còn một tab. Không có chuyện một tab tự chuyển thành các dấu cách.
- **`all_blank_strip`:** mọi dòng chỉ có whitespace được rút về rỗng nhưng hai line terminators vẫn được giữ, nên kết quả là `"\n\n"`, không phải chuỗi rỗng.
- **`preserve_final_newline_with_dedent`:** chứng minh cách xử lý tình huống biết trước một LF cuối và muốn lùi indentation cả khối.
- **`rawStillOriginal=true`:** `String` ban đầu không bị thay đổi bởi `stripIndent()`.

Hàm `visible` được viết để xem dữ liệu không nhìn thấy: nếu chỉ in chuỗi đã xử lý bằng `System.out.println(value)`, rất khó nhận biết tab, dấu cách cuối và LF cuối.

## 5. Liên hệ giữa text block và `String.stripIndent()` runtime

Có hai giai đoạn hoàn toàn khác nhau:

**A. Biên dịch text block trong mã nguồn**

~~~java
String markup = """
        <root>
          <item>ok</item>
        </root>
        """;
~~~

Compiler đã áp dụng các quy tắc xử lý text block (chuẩn hóa line terminators, bỏ indentation incidental và trailing whitespace, rồi diễn giải escape) **khi tạo chuỗi từ cú pháp `"""`**. Giá trị `markup` sau biên dịch đã là:

~~~text
<root>
  <item>ok</item>
</root>
~~~

với LF cuối nếu dấu đóng ở dòng riêng.

**B. Gọi một phương thức trên chuỗi đã tồn tại ở runtime**

~~~java
String normalizedAgain = markup.stripIndent();
~~~

Đây là **lần xử lý mới trên giá trị hiện có**, áp dụng các quy tắc runtime của `String.stripIndent()`. Không nên mặc định cho rằng gọi nó lên mọi text block luôn cần thiết hoặc luôn vô hại. Nếu text block đã được compiler điều chỉnh đúng, gọi thêm có thể dư thừa; nếu text block có khoảng trắng cuối dòng được giữ **có chủ đích** bằng `\s`, gọi thêm `stripIndent()` có thể làm mất dấu cách đó.

**Một khác biệt quan trọng:** khi tính indentation cho text block, vị trí dấu đóng `"""` và indentation của dòng dấu đóng là thành phần trong xử lý tại compile time. Khi một `String` đã được tạo và kết thúc bằng LF, dữ liệu của dòng dấu đóng **không còn nằm trong String**; `stripIndent()` runtime tính lại dựa trên các dòng **thực sự có trong String**, bao gồm dòng cuối rỗng. Vì vậy việc áp dụng `stripIndent()` sau text block **không tương đương** với biên dịch lại text block.

### Chương trình Java 17+: so sánh với `strip()` và `indent(-n)`

Tạo tệp **`StripIndentTextBlockDemo.java`**:

~~~java
public class StripIndentTextBlockDemo {
    static String visible(String text) {
        return text.replace(" ", "<sp>")
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\t", "\\t");
    }

    public static void main(String[] args) {
        String textBlock = """
                <root>
                  <item>ok</item>
                </root>
                """;
        System.out.println("block=" + visible(textBlock));
        System.out.println("blockStripIndent="
                + visible(textBlock.stripIndent()));
        System.out.println("same="
                + textBlock.equals(textBlock.stripIndent()));

        String withIntentionalIndent = """
                    A
                      B
                """;
        System.out.println("withIndent=" + visible(withIntentionalIndent));
        System.out.println("withIndentStripped="
                + visible(withIntentionalIndent.stripIndent()));

        String source = "    A\n      B\n";
        System.out.println("source=" + visible(source));
        System.out.println("sourceStrip=" + visible(source.strip()));
        System.out.println("sourceStripIndent="
                + visible(source.stripIndent()));
        System.out.println("sourceIndentMinus4="
                + visible(source.indent(-4)));
        System.out.println("empty=" + visible("".stripIndent()));
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 StripIndentTextBlockDemo.java
java StripIndentTextBlockDemo
~~~

Stdout đã xác minh:

~~~text
block=<root>\n<sp><sp><item>ok</item>\n</root>\n
blockStripIndent=<root>\n<sp><sp><item>ok</item>\n</root>\n
same=true
withIndent=<sp><sp><sp><sp>A\n<sp><sp><sp><sp><sp><sp>B\n
withIndentStripped=<sp><sp><sp><sp>A\n<sp><sp><sp><sp><sp><sp>B\n
source=<sp><sp><sp><sp>A\n<sp><sp><sp><sp><sp><sp>B\n
sourceStrip=A\n<sp><sp><sp><sp><sp><sp>B
sourceStripIndent=<sp><sp><sp><sp>A\n<sp><sp><sp><sp><sp><sp>B\n
sourceIndentMinus4=A\n<sp><sp>B\n
empty=
~~~

Ý nghĩa:

- Text block `textBlock` đã có cấu trúc như ý; gọi `stripIndent()` lên nó cho cùng giá trị.
- Text block `withIntentionalIndent` cố ý giữ bốn spaces trước A và sáu trước B do vị trí dấu đóng. Vì giá trị runtime kết thúc LF, `stripIndent()` **không tự động xóa** các khoảng trắng đó.
- `source.strip()` loại whitespace ở **đầu và cuối toàn chuỗi**, nhưng không làm giảm riêng phần indentation bên trong dòng B. Nó cũng bỏ LF cuối.
- `source.stripIndent()` trong trường hợp này xóa trailing spaces nếu có và chuẩn hóa newline, nhưng do dòng cuối rỗng nên vẫn giữ indentation.
- `source.indent(-4)` cố gắng bỏ tối đa bốn ký tự whitespace **ở đầu mỗi dòng**, tạo kết quả `"A\n  B\n"`. Nó khác với `stripIndent()` vì `-4` là một số chỉ định, không tự tính `min` từ toàn khối.
- `"".stripIndent()` vẫn là chuỗi rỗng; không có dòng nào để chuẩn hóa.

## 6. Khi nào `stripIndent()` có thể xóa khoảng trắng có chủ đích?

Trong text block, escape `\s` có thể được dùng để giữ **một dấu cách ở cuối dòng** tại thời điểm compiler xử lý text block. Ví dụ:

~~~java
String block = """
        X\s
        """;
// Giá trị ngay sau khi tạo: "X \n"
~~~

Nếu gọi `block.stripIndent()` ở runtime, method xử lý **trailing whitespace của từng dòng** mà không biết dấu cách đó trước đây được tạo bởi `\s` hay là một dấu cách gõ bình thường. Vì vậy kết quả thành `"X\n"`, **mất dấu cách trước LF**.

Điều này đã được kiểm thử bằng Java 17:

~~~java
System.out.println(block.equals("X \n"));               // true
System.out.println(block.stripIndent().equals("X\n"));  // true
~~~

Hai dòng trên là **mã minh họa đặt trong phương thức** có biến `block` đã tạo ở ví dụ, không phải một chương trình độc lập. Chúng minh họa khác biệt giữa *giữ trailing spaces trong quá trình tạo text block* và *loại trailing spaces khi gọi method trên String đã có*.

**Hệ quả nghiệp vụ:** nếu trailing whitespace có ý nghĩa trong dữ liệu (ví dụ văn bản cố định chiều rộng, kiểm thử so khớp byte/ký tự, hoặc một định dạng nhạy khoảng trắng), không nên tự ý gọi `stripIndent()`. Phải xác định rõ hợp đồng dữ liệu trước khi chuẩn hóa.

## 7. `stripIndent()` khác gì `strip()`, `trim()`, `indent()` và `lines()`?

| API | Tác dụng chính | Điều cần chú ý |
| --- | --- | --- |
| `stripIndent()` | Tính `min` chung, bỏ indentation có tính tương đối, bỏ trailing whitespace mỗi dòng, chuẩn hóa line terminators | **Dòng cuối** (kể cả rỗng) ảnh hưởng `min`; giữ số lượng line terminators |
| `strip()` | Bỏ whitespace ở **hai đầu toàn bộ chuỗi** | Không bỏ indentation chung của từng dòng trong khối; có thể bỏ LF đầu/cuối |
| `stripLeading()` | Bỏ whitespace ở đầu **toàn chuỗi** | Không phải bộ chuẩn hóa indentation nhiều dòng |
| `stripTrailing()` | Bỏ whitespace ở cuối **toàn chuỗi** | Có thể làm mất LF cuối |
| `trim()` | Bỏ một nhóm ký tự khoảng trắng/điều khiển cũ ở hai đầu toàn chuỗi | Không nên coi tương đương Unicode-aware `strip()`; không xử lý thụt lề nhiều dòng |
| `indent(int n)` | Thêm `n` spaces vào đầu **mỗi dòng** nếu dương, hoặc bỏ tối đa `-n` ký tự whitespace đầu dòng nếu âm | Số lượng là chỉ định, không tự tính mức chung; chuẩn hóa line endings và tạo LF cho mỗi dòng lấy từ `lines()` |
| `lines()` | Trả stream các dòng không chứa line terminators | Không tự bỏ indentation; cần quyết định cách ghép lại nếu muốn giữ newline gốc |
| `replaceAll(...)` | Thay bằng regex | Regex có thể khó an toàn với tabs, blank lines, CRLF và khoảng trắng đặc biệt; không nên thay `stripIndent()` bằng regex tùy tiện |

Ví dụ, `"    A\n      B\n".strip()` trở thành `"A\n      B"`: chỉ xóa ở rìa toàn chuỗi. Trong khi `indent(-4)` làm cả hai dòng giảm tối đa bốn ký tự đầu và giữ đường xuống dòng theo cơ chế riêng. Các API đều hợp lệ nhưng phục vụ **mục đích khác nhau**.

Khi muốn điều chỉnh thụt lề do nội dung động (chẳng hạn block SQL/HTML nhiều dòng được xây dựng tại runtime), `stripIndent()` thường phù hợp **nếu hợp đồng cho phép** loại trailing whitespace và bạn đã xử lý chính xác trường hợp dòng cuối.

## 8. Khoảng trắng, tabs, dòng trống và line terminators

### 8.1. Tabs và spaces được tính theo ký tự

`stripIndent()` đếm **ký tự whitespace đầu dòng**. Một tab `\t` là một ký tự, không có phép toán chuyển một tab thành tám spaces. Ví dụ:

~~~java
String input = "\talpha\n\t\tbeta";
String output = input.stripIndent();
// output có giá trị: "alpha\n\tbeta"
~~~

Ở đây mức chung là **một tab**, nên tab đầu bị loại khỏi cả hai dòng. Nếu hai dòng dùng tổ hợp tabs/spaces khác nhau, code unit bị xóa có thể khiến việc căn cột hiển thị không như mong đợi. Để dữ liệu có tính ổn định, nên thống nhất tabs hoặc spaces trước khi định dạng.

### 8.2. Dòng trống được giữ về mặt vị trí

Với input:

~~~java
String input = "   \n    alpha\n      beta\n    gamma";
String output = input.stripIndent();
~~~

Dòng đầu chỉ chứa spaces nên chuyển thành **dòng rỗng**, không biến mất; kết quả vẫn bắt đầu bằng `\n`, sau đó là `alpha`, `  beta`, `gamma`. Khác với việc loại hẳn các dòng trống bằng filter. Số line terminators vẫn được giữ.

### 8.3. CRLF/CR trở thành LF trong kết quả

Nếu chuỗi runtime chứa:

~~~java
String input = "    alpha\r\n      beta\r\n    gamma";
String result = input.stripIndent();
~~~

phần line terminators được chuẩn hóa thành LF, cho kết quả `"alpha\n  beta\ngamma"` (sau khi bỏ indentation). Với dữ liệu văn bản được yêu cầu chính xác CRLF (ví dụ một giao thức hoặc tệp đầu ra có quy tắc dòng riêng), cần quyết định rõ có được chuẩn hóa thành LF hay không trước khi áp dụng `stripIndent()`.

Điều này khác với việc **chỉ** hiển thị xuống dòng trên console: nơi in có thể dùng line ending của hệ điều hành, còn `stripIndent()` trả `String` có LF code unit cụ thể.

### 8.4. Các dòng chỉ chứa whitespace

Nếu dữ liệu ban đầu là `"  \n \t \n"`, nó có **hai line terminators** và mọi dòng đều trắng/rỗng. `stripIndent()` trả đúng `"\n\n"`, dài 2 code units. Đây không phải lỗi: phương thức giữ số lượng line terminators và chỉ bỏ các ký tự whitespace bên trong dòng.

## 9. Cách áp dụng an toàn trong chương trình thực tế

### Bước 1: xác định ý định

Hãy phân biệt **“loại indentation chung”** với **“loại mọi whitespace thừa”**. `stripIndent()` giữ thụt lề tương đối, nhưng xóa trailing whitespace của từng dòng; nếu trailing whitespace là dữ liệu, không dùng method này.

### Bước 2: xác định kiểu kết thúc chuỗi

Kiểm tra đầu vào có LF, CRLF, CR hay không có newline cuối. Với LF cuối, nhớ rằng một **dòng rỗng cuối** có thể khiến `min=0`. Nếu cần vừa dedent vừa giữ LF cuối, thiết kế quy tắc riêng như ví dụ chỉ dành cho một LF ở phần 3; không xử lý bừa bằng việc gọi `stripIndent()` liên tục.

### Bước 3: kiểm tra ký tự không nhìn thấy

Khi debug, không nên chỉ dùng `println(result)` vì trailing spaces và tabs rất khó nhìn. Hàm `visible(...)` ở phần 4 biểu diễn spaces bằng `<sp>` và các ký tự dòng bằng ký hiệu `\n`, `\r`. Khi cần kiểm tra chính xác, có thể dùng `equals(expected)` hoặc duyệt `charAt(i)`, in mã hex để phân biệt tabs với spaces.

### Bước 4: không áp dụng thêm nếu text block đã đúng

Một text block được compiler xử lý indentation khi biên dịch. Nếu giá trị sau compile đã có ý nghĩa chính xác (đặc biệt khi giữ trailing spaces với `\s`), tránh `stripIndent()` thêm lần nữa. Gọi thêm có thể không đổi độ thụt lề nhưng vẫn xóa trailing spaces.

### Bước 5: viết test giá trị cuối cùng

Ưu tiên so sánh **toàn bộ chuỗi** thay vì kiểm tra một phần. Ví dụ:

~~~java
String source = "    alpha  \r\n      beta \r\n    gamma";
String expected = "alpha\n  beta\ngamma";
if (!source.stripIndent().equals(expected)) {
    throw new AssertionError("Unexpected indentation");
}
~~~

Đây là đoạn mã minh họa đặt trong một phương thức. Nó kiểm tra đúng cả số spaces, nội dung và newline. Bài kiểm tra riêng nên thêm các tình huống: có/không LF cuối, blank lines, tabs, CRLF, chuỗi rỗng, chuỗi toàn whitespace và trailing spaces có ý nghĩa.

## 10. Những hiểu lầm thường gặp

1. **“`stripIndent()` luôn xóa indentation chung ở mọi đoạn text.”** Không hẳn: nếu chuỗi kết thúc ngay bằng newline, dòng cuối rỗng có indentation 0 và có thể ngăn việc bỏ indentation ở đầu các dòng khác.
2. **“Dòng trắng nào cũng phải tính là indentation 0.”** Không đúng với thuật toán: các dòng trắng thông thường không tham gia xác định `min`, nhưng **dòng cuối** thì có.
3. **“`stripIndent()` xóa mọi khoảng trắng đầu mỗi dòng.”** Sai: nó bỏ phần chung được xác định bởi `min`, **giữ phần thụt tương đối**.
4. **“Khoảng trắng cuối dòng luôn được giữ.”** Sai: trailing whitespace ở mỗi dòng có nội dung bị xóa, ngay cả khi ký tự đó từng đến từ `\s` trong text block.
5. **“Tabs được xem như 4 hoặc 8 spaces.”** Sai: API đếm một tab là một ký tự whitespace, không biết tab stop khi hiển thị.
6. **“Mọi text block đều nên gọi `stripIndent()` ở runtime.”** Sai: text block đã được compiler xử lý; gọi lại có thể thừa hoặc làm mất dữ liệu whitespace có ý nghĩa.
7. **“`stripIndent()` tương đương `strip()`.”** Sai: `strip()` xử lý hai đầu của **toàn chuỗi**, `stripIndent()` xử lý thụt lề và trailing whitespace **theo từng dòng**, đồng thời chuẩn hóa line endings.
8. **“`stripIndent()` giữ nguyên CRLF trong dữ liệu.”** Sai: output chuẩn hóa các line terminators thành LF.
9. **“Dòng trống bị xóa hoàn toàn.”** Sai: nội dung whitespace của dòng trắng được bỏ, nhưng **số line terminators** được giữ.
10. **“String gốc bị chỉnh sửa.”** Sai: `String` bất biến; `stripIndent()` trả giá trị kết quả và không đổi `original`.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Chuỗi `"    a\n      b"` không có LF cuối. Sau `stripIndent()`, còn bao nhiêu spaces trước b?  
**Đáp án:** Hai spaces. `min=4`, kết quả là `"a\n  b"`.

**Câu 2.** Chuỗi `"    a\n      b\n"` kết thúc bằng LF. Có chắc kết quả là `"a\n  b\n"` không?  
**Đáp án:** Không. Dòng cuối rỗng làm `min=0` nên các spaces đầu dòng vẫn còn. Kết quả là `"    a\n      b\n"`, nếu không có trailing spaces khác.

**Câu 3.** Chuỗi `"    a\n      b\n    "` có dòng cuối bốn spaces. Kết quả sau `stripIndent()`?  
**Đáp án:** `"a\n  b\n"`, vì `min=4` và dòng trắng cuối chuyển thành rỗng.

**Câu 4.** `stripIndent()` có giữ `\r\n` như cũ không?  
**Đáp án:** Không. CRLF được chuẩn hóa thành LF.

**Câu 5.** `"\ta\n\t\tb".stripIndent()` có biến tab thành dấu cách không?  
**Đáp án:** Không. Kết quả là `"a\n\tb"`; mỗi tab được đếm như một ký tự whitespace.

**Câu 6.** Tại sao `stripIndent()` có thể xóa một dấu cách do `\s` tạo ra trong text block?  
**Đáp án:** Vì khi chạy ở runtime, API chỉ nhìn **dấu cách thực** ở cuối dòng và xóa trailing whitespace; nó không còn biết nguồn gốc của ký tự đó.

**Câu 7.** Khi cần giữ indentation tương đối nhưng không cần giữ khoảng trắng cuối dòng, `stripIndent()` có phù hợp không?  
**Đáp án:** Có, với điều kiện đã kiểm tra trường hợp dòng cuối và việc chuẩn hóa line terminators là chấp nhận được.

## Tài liệu Java chính thức

- **Java SE 17 — `String.stripIndent()`**: quy tắc `min` (dòng cuối kể cả trắng), xóa leading/trailing whitespace theo dòng, giữ số line terminators, chuẩn hóa LF. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#stripIndent()
- **Java SE 26 — `String.stripIndent()`**: đặc tả ở Java hiện đại, xác nhận hành vi vẫn còn áp dụng. https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#stripIndent()
- **Java SE 17 — `String.indent(int)` / `String.lines()`**: sự khác biệt khi lùi số ký tự cố định và chia dòng. https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#indent(int)
- **Java Language Specification 17 §3.10.6 — Text Blocks**: quy tắc xử lý line terminators, incidental indentation, escape tại compile time. https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6
- **OpenJDK JEP 378 — Text Blocks**: tính năng ổn định từ Java 15 và cơ chế xử lý nội dung text block. https://openjdk.org/jeps/378
# Dòng trống, tab và khoảng trắng ở cuối dòng trong Java Text Blocks

## 1. Mục tiêu và phiên bản Java áp dụng

Text block là một dạng literal kiểu `String` dùng dấu ba nháy kép `"""` để viết văn bản nhiều dòng. Java **không giữ nguyên từng dấu cách, tab và dấu xuống dòng trong source**: compiler thực hiện một số bước chuẩn hóa. Bài học tập trung vào ba vấn đề:

1. **Dòng trống:** Dòng trắng ở giữa, đầu và cuối text block được giữ hay loại thế nào?
2. **Tab:** Ký tự tab vật lý trong file Java khác gì escape `\t`? Trộn tab và space trong phần thụt lề gây ra điều gì?
3. **Khoảng trắng cuối dòng:** Vì sao dấu cách hoặc tab vô hình ở cuối source line bị loại, và làm sao giữ những ký tự trắng thực sự là dữ liệu?

Ví dụ cơ bản:

~~~java
String greeting = """
    Xin chào,
    Java!
    """;
~~~

Kết quả tương đương với `"Xin chào,\nJava!\n"`. Các khoảng trắng đầu dòng dùng để trình bày code bị loại; newline trước dấu đóng trở thành một phần của chuỗi.

**Ghi chú về phiên bản:** Text blocks đã là tính năng **chính thức từ Java 15 (JEP 378)**. Java 14 từng có text blocks ở dạng preview, nhưng đó chỉ là lịch sử phát triển. Tất cả mã chạy trong bài sử dụng **Java 17+**, không cần `--enable-preview`, chỉ dạy cú pháp còn sử dụng trong Java hiện đại.

## 2. Thứ tự xử lý là chìa khóa

Theo Java Language Specification `3.10.6, compiler tạo giá trị text block theo **ba bước tuần tự**:

| Bước | Compiler làm gì? | Hệ quả |
| --- | --- | --- |
| 1. Chuẩn hóa line terminator | Chuyển CRLF và CR vật lý thành LF (`\n`) | Nội dung không phụ thuộc cách xuống dòng của editor hoặc hệ điều hành |
| 2. Bỏ incidental whitespace | Bỏ phần thụt lề chung không cần thiết và khoảng trắng vật lý cuối dòng, như `String.stripIndent()` | Text block không chứa nguyên những khoảng trắng dùng để căn code |
| 3. Giải mã escape | Xử lý `\t`, `\s`, `\n` và escape nối dòng | Escape được dịch sau bước bỏ khoảng trắng nên có thể tạo tab/space có chủ đích |

~~~text
Nội dung text block trong file .java
          |
          v
   CRLF / CR  --> LF
          |
          v
   Xóa thụt lề phụ và trailing whitespace
          |
          v
   Giải mã escape sequences (\t, \s, \n, \ + xuống dòng)
          |
          v
    Giá trị String lúc chạy
~~~

**Điểm dễ nhầm nhất:** Trong source, `\t` gồm ký tự backslash và chữ `t`; ở bước xử lý thụt lề nó **chưa phải tab thật**. Tương tự `\s` chưa phải space thật khi compiler đang loại trailing whitespace. Đến bước cuối hai escape này mới biến thành ký tự trắng.

### Cú pháp mở text block

Text block phải có một line terminator sau dấu mở `"""`:

~~~java
// Hợp lệ:
String s = """
    A
    """;

// Không hợp lệ: dấu mở và nội dung nằm trên cùng dòng.
// String wrong = """A""";
~~~

LF bắt buộc **ngay sau dấu mở** chỉ dùng để phân cách cú pháp, **không tự làm chuỗi bắt đầu bằng `\n`**. Nếu cần dòng trống ở đầu giá trị, phải thêm một dòng trống thật sự sau dòng mở.

## 3. Dòng trống ở giữa nội dung

~~~java
String lines = """
    alpha

    beta
    """;
~~~

Giá trị có biểu diễn escape chính xác:

~~~text
alpha\n\nbeta\n
~~~

Ở đây `\n` trong phần giải thích là **ký hiệu hiển thị** của một LF, không phải hai ký tự được lưu trong chuỗi. Dòng trống giữa `alpha` và `beta` được giữ lại:

- LF thứ nhất kết thúc dòng `alpha`.
- LF thứ hai biểu diễn dòng trống ở giữa.
- LF cuối đứng sau `beta` vì dấu đóng `"""` nằm ở dòng riêng.
- `lines.length()` bằng `12`: `alpha` (5) + hai LF (2) + `beta` (4) + LF (1).

**Dòng trống không bị xóa chỉ vì compiler xóa khoảng trắng phụ.** Các dấu cách/tab nằm riêng trên một dòng trắng có thể bị loại, nhưng ký tự xuống dòng tạo ra dòng trắng đó vẫn được giữ.

### 3.1. Dòng trống chỉ chứa dấu cách hoặc tab

Trong editor, hai tình huống có thể trông giống nhau:

~~~text
alpha
[dòng hoàn toàn không có ký tự]
beta
~~~

và

~~~text
alpha
[dòng chứa 4 dấu cách và 1 tab]
beta
~~~

Các dấu `[ ... ]` trên là **chú thích sơ đồ**, không phải mã Java. Cả hai kiểu dòng có thể trở thành dòng rỗng trong giá trị text block: **khoảng trắng vật lý trên dòng trắng bị loại**, nhưng một LF vẫn biểu diễn ranh giới dòng đó.

Một dòng trống hoàn toàn **không được tính như dòng có 0 indent để phá mức thụt lề chung** của các dòng có nội dung. Nếu không, mỗi dòng trắng sẽ làm thuật toán xóa thụt lề bị vô hiệu; Java được thiết kế để tránh điều đó.

### 3.2. Dòng trống cuối

~~~java
String endBlank = """
    x

    """;
~~~

Kết quả là `"x\n\n"` và `endBlank.length() == 3`. Có hai LF: một kết thúc dòng chứa `x`, một đại diện dòng trống cuối.

Ngược lại:

~~~java
String noEnd = """
    x""";
~~~

`noEnd` chỉ là `"x"` và dài `1`. Dấu đóng cùng dòng với ký tự cuối không làm phát sinh LF cuối.

### 3.3. Dòng trống đầu

~~~java
String startBlank = """

    alpha
    """;
~~~

Chuỗi thực là `"\nalpha\n"`. LF bắt buộc của dấu mở không được tính vào nội dung; **dòng trống bổ sung sau đó** mới tạo LF đầu tiên trong giá trị.

## 4. Thụt lề chung (*incidental indentation*) liên quan thế nào?

Xét:

~~~java
String html = """
        <ul>
            <li>Java</li>
        </ul>
        """;
~~~

Dòng `<ul>` và `</ul>` có 8 dấu cách ở đầu source; dòng `<li>` có 12 dấu cách. Với dấu đóng căn ở 8 dấu cách, compiler bỏ mức indent chung, nên giá trị tương đương:

~~~text
<ul>
    <li>Java</li>
</ul>
~~~

Chỉ **4 dấu cách có ý nghĩa** trước `<li>` được giữ lại.

Compiler xét lượng khoảng trắng dẫn đầu ở các dòng có nội dung và dòng chứa **dấu đóng trên dòng riêng** khi tính mức thụt lề. Dòng trắng không khiến mức indent bị ép về zero.

### 4.1. Di chuyển dấu đóng để giữ thêm indent

~~~java
String indented = """
        first
            second
    """;
~~~

Với dấu đóng lùi về trái, một phần indent của các dòng nội dung được giữ trong chuỗi. Vì vậy thay đổi vị trí `"""` đóng có thể thay đổi giá trị `String`, chứ không chỉ thay đổi cách căn mã nguồn.

Trong trường hợp dấu đóng nằm **cùng dòng với nội dung cuối**, nó không tạo thêm dòng đóng để tính indent; đồng thời nội dung không có LF cuối. Khi chủ ý biểu diễn văn bản nhiều dòng có LF kết thúc, nên đặt dấu đóng trên dòng riêng và căn thống nhất.

## 5. Tab vật lý không tương đương với bốn hay tám dấu cách

Tab là ký tự U+0009. Editor có thể trình bày nó rộng bằng 2, 4, 8 hoặc một số cột khác; **Java không thể dựa vào thiết lập tab-width của từng editor**.

Khi tính incidental indentation của text block, **một tab vật lý được tính là một ký tự trắng**, giống như một dấu cách ở mức đếm ký tự, chứ không phải bằng số cột mà editor hiển thị.

Ví dụ sơ đồ, `·` là một space và `⇥` là một tab thật:

~~~text
Dòng A: ················wide    (16 dấu cách)
Dòng B: ⇥···short              (1 tab + 3 dấu cách = 4 ký tự trắng)
~~~

Nếu mức thụt lề nhỏ nhất trong text block là 4 ký tự, Java bỏ 4 ký tự trắng đầu dòng: `wide` vẫn còn 12 dấu cách phía trước, `short` không còn. Hai dòng có thể trông thẳng hàng trong một editor nhưng có **mức indent thực tế khác nhau**.

**Khuyến nghị:** Với text block lưu SQL, JSON, HTML, email hoặc văn bản cần căn lề, hãy dùng **một quy ước indent nhất quán** trong source; không trộn tab và space nếu có thể.

### 5.1. Escape `\t` an toàn hơn tab vật lý trong dữ liệu

~~~java
String table = """
    Name\tScore
    Lan\t10
    """;
~~~

Kết quả có thể biểu diễn:

~~~text
Name\tScore\nLan\t10\n
~~~

Ký hiệu `\t` trong sơ đồ đại diện **một tab thật**. Escape `\t` không tham gia phép tính incidental indentation vì compiler chỉ dịch escape ở bước cuối.

Dùng escape khi tab là **nội dung mong muốn**, thay vì dùng ký tự tab vật lý vô hình để căn trong code.

### 5.2. Tab cuối dòng

Tab vật lý ở cuối dòng nguồn được xem là **trailing whitespace** và bị strip. Nhưng:

~~~java
String s = """
    X\t
    """;
~~~

giữ được một tab thật trước LF, vì `\t` được giải mã sau bước strip. Giá trị `s` tương đương `"X\t\n"` và dài `3` ký tự (X, tab, LF). Chỉ thêm tab cuối dòng nếu định dạng đích thực sự yêu cầu.

## 6. Dấu cách và tab vật lý ở cuối dòng sẽ bị loại

Xét:

~~~java
String removed = """
    red  
    blue
    """;
~~~

**Lưu ý:** Dòng `red` trong đoạn mã vừa rồi có **hai dấu cách vật lý ngay sau chữ `d`**; chúng rất khó nhìn thấy và có thể bị editor xóa khi copy. Java loại chúng khỏi giá trị text block.

`removed` tương đương `"red\nblue\n"`, dài `9` ký tự. Không có dấu cách nào sau `red`.

Đây là xử lý **khi biên dịch text block**, không có nghĩa Java tự động bỏ trailing whitespace ở mọi `String`:

~~~java
String normal = "red  ";
System.out.println(normal.length()); // 5, vì hai space vẫn tồn tại.
~~~

Lý do xóa trailing whitespace nguồn: các dấu cách/tab cuối dòng vô hình, dễ bị editor hoặc formatter vô tình thay đổi, và thường chỉ là sản phẩm phụ khi chỉnh sửa mã.

### 6.1. Giữ dấu cách có chủ đích bằng `\s`

Java hỗ trợ escape `\s` để biểu diễn **một ký tự space**. Vì nó được giải mã sau bước xóa incidental whitespace, nó giúp duy trì trailing spaces:

~~~java
String kept = """
    red  \s
    green\s
    """;
~~~

Kết quả hiển thị với `·` đại diện một dấu cách và `\n` đại diện LF:

~~~text
red···\ngreen·\n
~~~

Diễn giải:

- Sau `red` có **hai dấu cách vật lý trước escape `\s`** cộng thêm **một dấu cách do `\s`** sinh ra → tổng **3 dấu cách**.
- Sau `green` chỉ có một `\s` → **1 dấu cách**.
- Dòng đóng ở dòng riêng → có LF cuối.
- `kept.length()` là `14`.

Hai dấu cách nguồn trước `\s` không bị xem là trailing whitespace vì dòng nguồn kết thúc bởi ký tự `s` trong escape, không phải bởi dấu cách. Compiler dịch `\s` thành một dấu cách **sau** bước strip.

Nếu muốn nhiều dấu cách mà không dùng dấu cách nguồn, có thể dùng nhiều escape `\s` liền nhau; ưu tiên một cách trình bày đủ rõ để người đọc biết độ dài mong muốn.

### 6.2. Những cách giữ trailing whitespace khác

- `\t` dùng khi **tab cuối dòng** là dữ liệu thật; escape dịch sau bước strip.
- `\040` vẫn là escape hợp lệ của dấu cách trong Java, nhưng `\s` thường rõ nghĩa hơn cho nhu cầu giữ space.
- Có thể thay ký tự đánh dấu rồi `replace` sau khi tạo text block, nhưng thường phức tạp hơn escape `\s` và phải đảm bảo marker không xuất hiện hợp lệ trong dữ liệu.

**Không dùng `\u0020` để né trailing whitespace stripping.** Unicode escape được Java dịch rất sớm khi đọc source, nên khoảng trắng nhận được vẫn có thể bị xử lý như khoảng trắng vật lý. `\s` khác ở chỗ nó được giải mã trong giai đoạn escape của text block.

### 6.3. Đừng sử dụng `trim()` để “sửa” mọi text block

Một lời gọi `trim()` hoặc `strip()` ở runtime có thể xóa luôn các LF hoặc dấu cách **có ý nghĩa** ở đầu/cuối toàn bộ chuỗi, chứ không chỉ incidental whitespace của source. Chỉ gọi chúng khi hợp đồng dữ liệu thực sự yêu cầu bỏ khoảng trắng đầu/cuối giá trị.

## 7. Kiểm soát ký tự LF cuối cùng

Khi dấu đóng trên dòng riêng:

~~~java
String withFinalLf = """
    red
    blue
    """;
~~~

kết quả có LF cuối: `"red\nblue\n"`.

Có hai cách tạo `"red\nblue"` **không có LF cuối**:

~~~java
String inlineClose = """
    red
    blue""";

String lineContinued = """
    red
    blue\
    """;
~~~

Ở `inlineClose`, dấu đóng `"""` đứng ngay sau `blue` nên không có line terminator cuối trong nội dung. Ở `lineContinued`, dấu backslash **ngay trước line terminator** tạo escape nối dòng; dấu `\` và line terminator đó không tạo ký tự trong giá trị.

Không được đặt các ký tự khác sau backslash nối dòng rồi nghĩ nó vẫn hợp lệ. Khi muốn backslash **thật** trong giá trị thì dùng escape `\\`, không phải backslash nối dòng.

## 8. Ví dụ Java 17+ chạy được và stdout chính xác

Để nhìn thấy ký tự trắng, chương trình chuyển:
- mỗi space thành `·`;
- tab thật thành chuỗi hiển thị `\t`;
- LF thật thành chuỗi hiển thị `\n`;
- dấu backslash thành `\\` để phân biệt với ký tự escape.

Lưu toàn bộ nội dung vào tệp **`TextBlockWhitespaceDemo.java`**:

~~~java
public final class TextBlockWhitespaceDemo {
    private static String visible(String text) {
        return text.replace("\\", "\\\\")
                   .replace(" ", "·")
                   .replace("\t", "\\t")
                   .replace("\n", "\\n");
    }

    private static void show(String label, String text) {
        System.out.println(label + ": [" + visible(text) + "] length=" + text.length());
    }

    public static void main(String[] args) {
        String blank = """
            alpha

            beta
            """;
        String blankEnd = """
            x

            """;
        String trailingRemoved = """
            red  
            blue
            """;
        String trailingKept = """
            red  \s
            green\s
            """;
        String escapedTabs = """
            A\tB
            C\tD
            """;
        String noFinal = """
            red
            blue""";
        String continued = """
            red
            blue\
            """;

        show("Blank", blank);
        show("Blank-end", blankEnd);
        show("Trailing removed", trailingRemoved);
        show("Trailing preserved", trailingKept);
        show("Tabs", escapedTabs);
        show("No final LF", noFinal);
        show("Backslash line continuation", continued);
        System.out.println("NoFinal equals Continued: " + noFinal.equals(continued));
    }
}
~~~

Dòng `red` trong `trailingRemoved` có **hai dấu cách cuối dòng cố ý**; editor có thể tự động trim chúng. Điều đó **không thay đổi kết quả chương trình** vì compiler vốn loại những space ấy.

Biên dịch/chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 --release 17 TextBlockWhitespaceDemo.java
java TextBlockWhitespaceDemo
~~~

**Stdout chính xác** đã kiểm chứng (các `\n` và `\t` ở output là hai ký tự hiển thị do `visible` tạo ra):

~~~text
Blank: [alpha\n\nbeta\n] length=12
Blank-end: [x\n\n] length=3
Trailing removed: [red\nblue\n] length=9
Trailing preserved: [red···\ngreen·\n] length=14
Tabs: [A\tB\nC\tD\n] length=8
No final LF: [red\nblue] length=8
Backslash line continuation: [red\nblue] length=8
NoFinal equals Continued: true
~~~

### 8.1. Giải thích các dòng output

1. `Blank`: Có **hai LF giữa `alpha` và `beta`**, cho thấy dòng trống được giữ; LF cuối do dấu đóng riêng dòng.
2. `Blank-end`: Dòng trống cuối tạo thêm một LF.
3. `Trailing removed`: Hai dấu cách cuối dòng `red` trong source bị loại.
4. `Trailing preserved`: `\s` giữ đúng số dấu cách có chủ đích; ký hiệu `·` giúp đếm được chúng.
5. `Tabs`: Hai escape `\t` đã trở thành tab thật. Mỗi tab có `length` bằng 1 đơn vị UTF-16, không phải nhiều dấu cách.
6. `No final LF`: Dấu đóng ngay sau `blue` làm chuỗi không có LF cuối.
7. `Backslash line continuation`: `\` cuối dòng `blue` ức chế LF, tạo cùng giá trị.
8. So sánh bằng `equals` cho `true` vì hai cách bỏ LF cuối tương đương nhau.

### 8.2. Lint giúp phát hiện whitespace khó nhìn

Nếu muốn compiler cảnh báo về cách trình bày text block:

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:text-blocks TextBlockWhitespaceDemo.java
~~~

Với source còn các dấu cách cuối dòng thật, compiler có thể cảnh báo `trailing white space will be removed`. Với các dòng indent trộn tab và space không nhất quán, cảnh báo có thể là `inconsistent white space indentation`.

Đây là **cảnh báo biên dịch**, không phải exception khi chạy; khi text block hợp lệ, chương trình vẫn có thể biên dịch thành công. Đừng dựa vào cảnh báo thay cho unit test trên nội dung `String`.

## 9. Kiểm thử chính xác khoảng trắng trong ứng dụng

### 9.1. Dùng `equals` so với chuỗi escape rõ ràng

~~~java
String actual = """
    one

    two
    """;

String expected = "one\n\ntwo\n";
System.out.println(actual.equals(expected)); // true
~~~

Đây là đoạn mã minh họa đặt trong một phương thức. So sánh trực tiếp giúp phát hiện LF thừa/thiếu mà terminal không biểu diễn rõ.

### 9.2. Dùng `length()` và `charAt()`

~~~java
String data = "A\tB\n";
System.out.println(data.length());        // 4
System.out.println((int) data.charAt(1));  // 9: tab U+0009
System.out.println((int) data.charAt(3));  // 10: LF U+000A
~~~

`String.length()` đếm các đơn vị mã UTF-16; ở ví dụ chỉ dùng ASCII, mỗi ký tự hiển thị hoặc điều khiển có độ dài 1. Vì vậy một tab thật **không** được tính là bốn hay tám dấu cách.

### 9.3. Tách dòng mà không làm mất đoạn rỗng ở cuối

~~~java
String data = "a\n\nb\n";
String[] parts = data.split("\n", -1);
System.out.println(java.util.Arrays.toString(parts));
// [a, , b, ]
~~~

Tham số `-1` giữ các phần tử rỗng cuối; nếu bỏ nó, bạn có thể vô tình làm mất dấu vết của LF cuối khi debug.

### 9.4. Phân biệt text block stripping với `stripTrailing()`

~~~java
String ordinary = "abc  ";
System.out.println(ordinary.length());                 // 5
System.out.println(ordinary.stripTrailing().length()); // 3
~~~

`stripTrailing()` là **method được gọi ở runtime**. Xử lý incidental whitespace của text block xảy ra **khi tạo literal**, không tác động lên mọi `String` hoặc những chuỗi được nối thêm sau đó.

## 10. Lỗi phổ biến

| Hiểu sai | Thực tế | Cách tránh |
| --- | --- | --- |
| Dòng trống trong text block luôn bị xóa | Số dòng trống được giữ, whitespace vật lý trên dòng trắng bị loại | Kiểm tra biểu diễn `\n\n` |
| LF sau `"""` mở là LF đầu của chuỗi | Nó là phần bắt buộc của cú pháp mở | Muốn LF đầu phải thêm dòng trống nội dung |
| Dấu đóng riêng dòng không thêm LF | LF trước dấu đóng là nội dung | Dùng `equals` để kiểm tra LF cuối |
| Dấu đóng cùng dòng chữ cuối vẫn thêm LF | Không có LF tự sinh sau ký tự cuối | Đặt dấu đóng đúng chỗ |
| Tab luôn bằng 4 dấu cách | Tab vật lý được tính là một ký tự khi xử lý indent | Không trộn tab/space |
| Tab vật lý cuối dòng luôn được giữ | Bị coi là trailing whitespace | Dùng `\t` khi tab là dữ liệu |
| Dấu cách vật lý cuối dòng vẫn còn | Bị compiler bỏ trong text block | Dùng `\s` để giữ |
| `\s` bị bỏ như space thật | Escape được dịch sau bước stripping | Giữ số space cần thiết |
| `\u0020` thay cho `\s` để giữ space | Unicode escape xử lý sớm | Dùng `\s` |
| `trim()` sẽ chỉ xóa incidental indent | Nó có thể xóa ký tự dữ liệu đầu/cuối | Chỉ trim theo hợp đồng đầu vào |
| `println` là đủ kiểm tra số space | Terminal che giấu trailing whitespace | Dùng `visible` và `length` |
| Phải bật preview của Java 14 | Text blocks chính thức từ Java 15 | Dùng Java 17+ bình thường |

## 11. Bài tập và đáp án

### Bài 1 — Đếm ký tự xuống dòng

~~~java
String s = """
    A

    B

    """;
~~~

**Hỏi:** Giá trị và độ dài?

**Đáp án:** `"A\n\nB\n\n"`, có hai chữ cái và bốn LF, tổng độ dài **6**.

### Bài 2 — Giữ đúng ba dấu cách cuối dòng

Trong source text block, cần tạo dòng `ID: 1` theo sau bởi **ba dấu cách** và LF. Không dùng dấu cách vật lý đơn độc ở cuối.

**Đáp án:**

~~~java
String s = """
    ID: 1  \s
    """;
~~~

Sau `ID: 1` là hai dấu cách đứng trước escape và một dấu cách do `\s` tạo ra: `"ID: 1   \n"`.

### Bài 3 — Tab có độ dài bao nhiêu?

~~~java
String s = """
    A\tB
    """;
~~~

**Đáp án:** `s.length() == 4` vì có `A`, tab, `B`, LF. `s.charAt(1) == '\t'` là `true`.

### Bài 4 — Viết hai kiểu không có LF cuối

Yêu cầu chuỗi đúng `"red\nblue"`.

**Đáp án:**

~~~java
String first = """
    red
    blue""";

String second = """
    red
    blue\
    """;
~~~

Hai biến có cùng nội dung; cách thứ hai cho phép giữ dấu đóng trên dòng riêng.

### Bài 5 — Vì sao dòng trắng không phá mức indent?

Một text block có các dòng `<p>`, dòng trống, rồi `</p>`; các dòng nội dung đều có tám space chung trong source. 

**Đáp án:** Dòng trắng không được coi là dòng có indent zero để quyết định lượng incidental whitespace. Compiler vẫn xóa tám space chung, nhưng **giữ LF** của dòng trống. Giá trị có hai LF giữa `<p>` và `</p>`.

## 12. Tóm tắt

- **Dòng trống**: giữ số LF, nhưng bỏ các dấu cách/tab vật lý không cần thiết trên dòng trắng.
- **Thụt lề**: xóa phần indent chung của source; vị trí dấu đóng ảnh hưởng đến kết quả.
- **Tab vật lý**: tính theo từng ký tự, không theo bề rộng hiển thị của editor; tránh trộn với space.
- **Trailing whitespace vật lý**: được bỏ; muốn giữ space/tab dữ liệu thì dùng **`\s` / `\t`**.
- **Thứ tự rất quan trọng**: chuẩn hóa CR/LF → strip incidental whitespace → giải mã escape.
- **LF cuối**: dấu đóng cùng dòng, dấu đóng riêng dòng và escape nối dòng cho ra kết quả khác nhau.
- Kiểm tra bằng `equals`, `length`, `charAt` và công cụ hiển thị ký tự ẩn khi dữ liệu cần chính xác tuyệt đối.
- Mọi quy tắc nêu trong bài đã là **Java 15+ chính thức** và dùng ổn định trên Java 17+.

**Tài liệu chính thức:**
- [Java SE 17 Language Specification — `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6).
- [Java SE 17 Language Specification — `3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.7).
- [Oracle Java SE 17 — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html).
- [OpenJDK JEP 378 — Text Blocks (Java 15)](https://openjdk.org/jeps/378).

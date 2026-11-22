# Quy tắc mở và đóng dấu ba nháy kép trong Java Text Block

**Text block** là cách khai báo một giá trị `String` nhiều dòng trong Java bằng cặp dấu phân định **ba nháy kép** `"""`. Cú pháp này giúp đặt HTML, JSON, SQL hoặc đoạn văn dài trực tiếp vào mã nguồn mà không phải ghép nhiều chuỗi và viết `\n` liên tục. Text block là tính năng chính thức từ **Java 15**; các chương trình thực hành dưới đây dùng Java 17 trở lên.

Điểm phải nhớ ngay từ đầu: dấu **mở** có quy tắc xuống dòng bắt buộc; dấu **đóng** linh hoạt hơn. Vị trí dấu đóng ảnh hưởng đến cả **ký tự xuống dòng cuối** và cách Java **loại bỏ thụt đầu dòng dư thừa**. Chúng ta cần phân biệt ký tự nằm trong *mã nguồn* với giá trị `String` thực sự được tạo ra.

## 1. Cấu trúc của một text block

Một text block có dạng:

~~~java
String message = """
    Dòng thứ nhất
    Dòng thứ hai
    """;
~~~

Ba thành phần là:

1. **Dấu mở `"""`**: đúng ba nháy kép, sau đó có thể có khoảng trắng ngang rồi **bắt buộc có ký tự kết thúc dòng**.
2. **Phần nội dung**: bắt đầu **ngay sau** ký tự kết thúc dòng của dấu mở; có thể chứa nhiều dòng, dấu `"` đơn lẻ và các escape hợp lệ.
3. **Dấu đóng `"""`**: ba nháy kép kết thúc nội dung, không bắt buộc ở một dòng riêng. Dấu `;` trong ví dụ là dấu kết thúc câu lệnh Java, **không phải** một phần của text block.

Theo cú pháp Java, dấu mở gồm `"""`, **0 hoặc nhiều** ký tự space, tab hoặc form feed, rồi một line terminator (`LF`, `CR` hoặc `CRLF`). Các khoảng trắng ngang ngay sau dấu mở và ký tự xuống dòng bắt buộc của dấu mở **không thuộc nội dung chuỗi**. Một text block có thể chứa giá trị một dòng hoặc chuỗi rỗng, nhưng **cách viết dấu mở trong mã nguồn vẫn phải xuống dòng**.

### Ví dụ hợp lệ và không hợp lệ

**Hợp lệ:**

~~~java
// Đúng: nội dung bắt đầu từ dòng sau dấu mở.
String greeting = """
    Xin chào!
    """;

// Đúng: dấu đóng có thể ở cuối dòng cuối cùng của nội dung.
String shortText = """
    Xin chào!""";

// Đúng: không có ký tự nội dung nào giữa dấu mở và dấu đóng.
String empty = """
    """;
~~~

**Không hợp lệ; các ví dụ sau chỉ minh họa lỗi cú pháp, không thể biên dịch:**

~~~java
// Sai: thiếu xuống dòng ngay sau dấu mở.
String invalid1 = """Xin chào!""";

// Sai: có nội dung cùng dòng với dấu mở.
String invalid2 = """Dòng đầu
    Dòng sau
    """;

// Sai: chỉ có hai nháy kép để mở, tạo chuỗi thông thường bị lỗi.
String invalid3 = ""
    Xin chào
    """;
~~~

Đặt `"""` mở ở cuối dòng khai báo, thêm một lần xuống dòng rồi mới viết nội dung. Dù về mặt ngôn ngữ có thể thêm khoảng trắng sau `"""` mở, cách dễ đọc nhất là **không thêm dấu cách vô hình trên dòng mở**.

## 2. Quy tắc dấu đóng và ký tự xuống dòng cuối

Dấu **đóng** `"""` có hai vị trí thường dùng, và chúng tạo ra **hai giá trị khác nhau**.

### Trường hợp A: dấu đóng trên dòng riêng

~~~java
String withNewline = """
    red
    green
    """;
~~~

Giá trị sau khi Java xử lý tương đương chuỗi truyền thống `"red\ngreen\n"`.

- Dòng `red` kết thúc bằng `\n`.
- Dòng `green` cũng kết thúc bằng `\n` vì trong mã nguồn **có xuống dòng trước dấu đóng**.
- Dấu đóng tự nó **không sinh ký tự xuống dòng**; ký tự xuống dòng cuối xuất phát từ dòng nội dung trước dấu đóng.

### Trường hợp B: dấu đóng nằm ngay sau ký tự cuối nội dung

~~~java
String withoutNewline = """
    red
    green""";
~~~

Giá trị tương đương `"red\ngreen"`, **không** có `\n` ở cuối. Nội dung vẫn có hai dòng dù dấu đóng ở cuối dòng `green`. Tương tự:

~~~java
String oneLine = """
    hello""";
~~~

Giá trị là đúng `"hello"`. Về **giá trị**, chuỗi này chỉ có một dòng; về **cú pháp**, dòng trống ngay sau `"""` mở vẫn là điều bắt buộc.

### Chương trình chạy được: kiểm tra chính xác dấu xuống dòng

~~~java
// TextBlockDelimitersDemo.java
public class TextBlockDelimitersDemo {
    static String visible(String value) {
        if (value.isEmpty()) {
            return "(empty)";
        }
        return value.replace("\n", "\\n");
    }

    public static void main(String[] args) {
        String withNewline = """
            red
            green
            """;

        String withoutNewline = """
            red
            green""";

        String oneLine = """
            hello""";

        String empty = """
            """;

        System.out.println("with = [" + visible(withNewline) + "]");
        System.out.println("without = [" + visible(withoutNewline) + "]");
        System.out.println("one = [" + visible(oneLine) + "]");
        System.out.println("empty = [" + visible(empty) + "]");
    }
}
~~~

Lưu thành `TextBlockDelimitersDemo.java`, chạy:

~~~bash
javac --release 17 TextBlockDelimitersDemo.java
java TextBlockDelimitersDemo
~~~

**Kết quả chuẩn** (ký tự `\` và `n` trong kết quả biểu diễn **một** xuống dòng đã được `visible()` chuyển thành hai ký tự dễ nhìn):

~~~text
with = [red\ngreen\n]
without = [red\ngreen]
one = [hello]
empty = [(empty)]
~~~

Không nên chỉ nhìn `System.out.println(withNewline)` để suy ra có `\n` cuối hay không: bản thân `println` cũng thêm xuống dòng khi in. Dùng `equals(...)`, `length()` hoặc hàm hiển thị escape như trên để kiểm tra chính xác.

## 3. Dấu đóng có thể nằm ở đâu?

Bảng sau lấy dấu mở ở dòng trước nội dung, và giả định khoảng thụt đầu dòng được Java xử lý như quy định:

| Cách đặt `"""` đóng | Có hợp lệ? | Hệ quả chính |
| --- | --- | --- |
| Dòng riêng sau dòng nội dung cuối | Có | Thường có `\n` ở cuối giá trị; cột của dấu đóng tham gia xác định thụt đầu dòng |
| Ngay sau chữ cuối của dòng nội dung | Có | Không có `\n` cuối, trừ khi nội dung chủ động tạo bằng escape |
| Sau khoảng trắng trên dòng nội dung cuối | Có | Những khoảng trắng trước dấu đóng nằm trong phần nguồn; kết quả còn phụ thuộc quy tắc loại khoảng trắng cuối dòng |
| Ở đầu một dòng riêng, sát lề trái | Có | Có thể bảo toàn khoảng trắng đầu dòng của các dòng nội dung |
| Trong phần nội dung mà không được escape và tạo thành ba nháy kép liên tiếp | Kết thúc text block sớm | Phần mã sau đó có thể bị lỗi cú pháp hoặc chuỗi bị cắt ngoài ý muốn |

**Dấu đóng là ba dấu `"` liền nhau**; không được chèn khoảng trắng giữa chúng. Java không bắt buộc dấu mở và dấu đóng thẳng cột. Trong thực tế, kiểu dễ đọc là đặt dấu mở ở cuối dòng khai báo, nội dung bên dưới, còn dấu đóng trên một dòng riêng thẳng với lề nội dung; khi cần bỏ `\n` cuối, cân nhắc đưa dấu đóng sát cuối nội dung.

Ví dụ dấu đóng sau một khoảng trắng thật:

~~~java
String value = """
    Hi """; // Có một dấu cách ngay trước ba nháy kép đóng.
~~~

Khoảng trắng trước dấu đóng ở dòng nội dung cuối là phần dữ liệu nguồn; nhưng dấu cách cuối dòng rất dễ bị công cụ format hoặc trình soạn thảo xóa. Nếu cần giữ chính xác khoảng trắng, hãy dùng escape `\s` như phần 5.

## 4. Vị trí dấu đóng điều khiển thụt đầu dòng

Khi dấu đóng đứng **trên dòng riêng**, số khoảng trắng trước nó tham gia vào việc tính indentation chung cùng các dòng nội dung không trống. Vì vậy, dấu đóng dịch sang trái có thể làm tăng khoảng trắng được giữ ở đầu chuỗi. Ví dụ:

~~~java
String aligned = """
        alpha
          beta
        """;
String preservedIndent = """
        alpha
          beta
    """;
System.out.println(aligned.equals("alpha\n  beta\n")); // true
System.out.println(preservedIndent.equals("    alpha\n      beta\n")); // true
~~~

Ở biến thứ nhất, mức thụt chung là tám dấu cách; ở biến thứ hai, dấu đóng chỉ thụt bốn dấu cách nên mỗi dòng giữ lại thêm bốn. Khi dấu đóng sát nội dung cuối, không có dòng dấu đóng riêng làm mốc thụt lề. Bài **Khoảng trắng thụt lề ngẫu nhiên và vị trí dấu đóng** đi sâu vào thuật toán, dấu cách còn lại, tab và các trường hợp kiểm chứng.

## 5. Nội dung có dấu ngoặc kép và dấu ba nháy kép

Trong text block, dấu `"` đơn lẻ và cặp `""` **thường không cần escape**. Ví dụ:

~~~java
String json = """
    {"name": "Lan", "active": true}
    """;
~~~

Giá trị chuỗi có JSON trên kèm `\n` cuối. Đây chỉ là `String`: trình biên dịch Java **không tự phân tích hay kiểm tra JSON**.

Ngược lại, **ba dấu nháy kép liền nhau trong nội dung** có thể bị hiểu là **dấu đóng**. Để biểu diễn chúng như dữ liệu, hãy escape ít nhất một dấu `"` bằng `\"`, hoặc escape cả ba cho rõ:

~~~java
String literalTripleQuotes = """
    \"\"\"
    """;
~~~

Giá trị kết quả là **ba dấu nháy kép** rồi `\n`. Các dấu `\` phía trước `"` chỉ là cú pháp escape của mã nguồn, **không xuất hiện trong kết quả**.

Ví dụ khi cần giữ một đoạn Java chứa ký hiệu ba nháy kép, phải đánh dấu escape tại đúng nơi có khả năng kết thúc text block sớm. Không giải quyết bằng cách chèn khoảng trắng giả giữa ba dấu nháy nếu dữ liệu đầu ra yêu cầu chúng liền nhau.

## 6. Xuống dòng, khoảng trắng cuối dòng và escape quanh dấu đóng

Trước khi tạo giá trị `String`, Java chuẩn hóa line terminator trong text block thành `\n`, loại thụt đầu dòng dư thừa và khoảng trắng cuối dòng, rồi mới xử lý escape. Một vài escape có ích:

| Cú pháp trong nội dung text block | Tác dụng |
| --- | --- |
| `\n` | Chủ động chèn ký tự LF |
| `\t` | Chèn tab |
| `\s` | Chèn một dấu cách, thường dùng để **giữ khoảng trắng cuối dòng** |
| `\\` | Chèn một dấu backslash |
| `\"` | Chèn dấu nháy kép, cần khi tránh dấu đóng ba nháy kép |
| Dấu `\` ngay trước line terminator | **Nối dòng**: loại bỏ line terminator đó trong kết quả |

Ví dụ dùng dấu `\` cuối dòng để nối hai dòng nội dung:

~~~java
String joined = """
    first\
    second""";
~~~

Giá trị bằng `"firstsecond"`: dấu `\` cuối dòng loại bỏ xuống dòng vật lý giữa hai phần, và dấu đóng nằm sát `second` nên không còn `\n` cuối.

Ví dụ giữ dấu cách ở cuối dòng bằng `\s`:

~~~java
String withTrailingSpace = """
    A\s
    B""";
~~~

Giá trị tương đương `"A \nB"`: sau `A` có **một dấu cách**, rồi xuống dòng, rồi `B`. Khoảng trắng vô hình do nhấn phím space ngay trước xuống dòng có thể bị xóa trong bước xử lý text block; escape `\s` diễn đạt ý định ổn định hơn.

Nếu muốn chắc chắn kết quả **không** có xuống dòng cuối, có thể chọn đóng sát nội dung như ở phần 2, hoặc sử dụng escape nối dòng trước dấu đóng riêng khi cách trình bày dễ hiểu hơn:

~~~java
String noFinalNewline = """
    red
    green\
    """;
~~~

Giá trị bằng `"red\ngreen"`. Các hình thức này hữu ích khi SQL/JSON/template phía nhận phân biệt chính xác dấu xuống dòng.

## 7. Quy tắc thực hành: chọn nơi đặt dấu đóng

**Ưu tiên dấu đóng trên dòng riêng** nếu chuỗi là tài liệu, đoạn SQL hoặc HTML nhiều dòng mà một dấu `\n` cuối không gây vấn đề. Giữ indent của dấu đóng thẳng với phần nội dung bắt đầu, sau khi xét mức thụt mong muốn. Kiểu này dễ đọc và dễ thêm dòng.

**Đóng sát ký tự cuối nội dung** khi bạn muốn bỏ dấu `\n` cuối một cách trực quan, ví dụ giá trị một dòng hoặc đoạn ngắn. Lưu ý cách này có thể ảnh hưởng đến thụt lề khi phần nội dung có nhiều dòng.

**Không di chuyển tùy tiện dấu đóng lúc format code**. Cấu trúc hiển thị của text block có thể thay đổi dữ liệu khi dấu đóng chuyển cột, khác với thao tác chỉ căn lề biểu thức Java thông thường. Với chuỗi mà khoảng trắng có ý nghĩa (snapshot, giao thức văn bản, dữ liệu test), nên khẳng định giá trị bằng phép so sánh:

~~~java
String expected = "red\ngreen\n";
String actual = """
    red
    green
    """;
System.out.println(expected.equals(actual)); // true
~~~

Ở đây `equals` giúp phát hiện cả những sai khác không nhìn thấy trong IDE; kết quả dự kiến là `true`.

## 8. Lỗi phổ biến

1. **Đặt chữ ngay sau `"""` mở**: `"""hello` không hợp lệ. Dấu mở bắt buộc kết thúc bằng một line terminator trước nội dung.
2. **Hiểu nhầm xuống dòng mở thành ký tự `\n` đầu chuỗi**: ký tự xuống dòng ngay sau dấu mở là một phần của **dấu phân định**, không phải dữ liệu. Chuỗi không tự bắt đầu bằng dòng trống.
3. **Nghĩ dấu đóng lúc nào cũng phải trên dòng riêng**: dấu đóng được phép sát nội dung cuối; điều này thường dùng để bỏ `\n` cuối.
4. **Nghĩ dấu đóng tự tạo `\n`**: ký tự xuống dòng cuối đến từ phần nội dung ngay trước dấu đóng. Đổi vị trí dấu đóng có thể làm nó biến mất.
5. **Căn lại dấu đóng mà không kiểm tra dữ liệu**: cột dấu đóng riêng có thể quyết định mức thụt lề bị loại bỏ; nội dung thu được đổi dù các chữ vẫn giống nhau.
6. **Đưa `"""` nguyên văn vào dữ liệu**: ba nháy kép không escape có thể đóng text block ngoài ý muốn. Escape ít nhất một nháy kép.
7. **Giữ dấu cách cuối dòng bằng khoảng trắng gõ tay**: compiler loại bỏ trailing whitespace dư thừa. Dùng `\s` nếu dấu cách đó thực sự có ý nghĩa.
8. **Lẫn text block với template hay parser**: Java text block là `String` thường, không tự nội suy biến, không kiểm chứng JSON/HTML/SQL và không tự bảo vệ dữ liệu khi ghép vào truy vấn SQL.
9. **Tưởng `"""x"""` là text block một dòng hợp lệ**: dù kết quả có thể chỉ một dòng, hình thức khai báo vẫn cần xuống dòng sau ba nháy kép mở.
10. **Đọc output của `println` như nội dung gốc**: `println` luôn thêm dấu xuống dòng riêng khi in, khiến ta khó phân biệt chuỗi có `\n` cuối hay không.

## 9. Bài luyện tập tự kiểm tra

**Bài 1.** Xác định hai khai báo sau có hợp lệ không, và nêu giá trị chính xác:

~~~java
String a = """
    one
    two
    """;
String b = """
    one
    two""";
~~~

**Đáp án:** Cả hai hợp lệ. `a` bằng `"one\ntwo\n"`, `b` bằng `"one\ntwo"`. Hai giá trị khác nhau vì `a` có xuống dòng trước dấu đóng.

**Bài 2.** Vì sao khai báo này báo lỗi?

~~~java
String c = """hello
    world
    """;
~~~

**Đáp án:** Dấu mở không được theo sau trực tiếp bởi chữ `hello`. Cần xuống dòng ngay sau `"""` mở trước khi viết chữ đầu tiên.

**Bài 3.** Muốn tạo đúng `String` gồm ba dấu nháy kép liền nhau, theo sau bởi `\n`, bạn viết thế nào?

**Đáp án mẫu:**

~~~java
String d = """
    \"\"\"
    """;
~~~

**Bài 4.** Một người chỉ di chuyển dấu `"""` đóng sang trái trong khối có nhiều dòng. Có thể gây khác biệt gì?

**Đáp án:** Mức thụt đầu dòng bị Java loại bỏ có thể giảm; chuỗi kết quả sẽ có **thêm dấu cách đầu dòng** dù chữ không đổi. Hãy so sánh `equals(...)` hoặc dùng hàm biểu diễn khoảng trắng để kiểm tra.

## 10. Ghi nhớ và tài liệu tra cứu

- **Mở:** `"""` + tùy chọn khoảng trắng ngang + **bắt buộc xuống dòng**; nội dung bắt đầu ở dòng sau.
- **Đóng:** `"""` **có thể ở dòng riêng hoặc cùng dòng với nội dung cuối**.
- **Dòng riêng:** thường tạo giá trị chứa `\n` cuối vì phần nội dung có xuống dòng trước dấu đóng.
- **Cùng dòng:** thường không có `\n` cuối; cột dấu đóng riêng không tham gia phép tính thụt đầu dòng.
- **Ba nháy kép trong dữ liệu:** dùng escape, chẳng hạn `\"\"\"`.
- **Khoảng trắng:** vị trí dấu đóng có thể ảnh hưởng indentation; `\s` giữ dấu cách cuối dòng, dấu `\` ngay trước line terminator có thể nối hai dòng.

Tham khảo thêm: [Java Language Specification, §3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6) và [Oracle Programmer’s Guide to Text Blocks](https://docs.oracle.com/en/java/javase/21/text-blocks/index.html). Hai tài liệu mô tả chính xác các dấu phân định và quy tắc xử lý khoảng trắng khi cần kiểm tra tình huống biên.

# Dấu phân cách ba dấu nháy kép trong Java text blocks

## Mục tiêu

**Text block** là cách viết một giá trị `String` bằng **ba dấu nháy kép liên tiếp** (`"""`) ở đầu và ở cuối. Cú pháp này đặc biệt hữu ích khi mã nguồn cần chứa nhiều dòng văn bản, HTML, JSON, SQL hoặc một đoạn mã khác với nhiều dấu `"`, thay vì nối nhiều string literals bằng `+` và `\n`.

Điểm quan trọng nhất: **ba dấu nháy kép mở và ba dấu nháy kép đóng có vai trò khác nhau**, nhất là với dấu xuống dòng đầu tiên, dấu xuống dòng cuối cùng và khoảng trắng thụt lề. Hiểu đúng các dấu phân cách sẽ giúp bạn kiểm soát chính xác giá trị `String` mà Java tạo ra.

Sau bài học, bạn có thể:

- Nhận diện **opening delimiter** `"""` và **closing delimiter** `"""`, bao gồm quy tắc bắt buộc xuống dòng sau bộ mở.
- Phân biệt vị trí dấu đóng **trên dòng riêng** và **ngay sau ký tự nội dung cuối cùng**, từ đó dự đoán chính xác `\n` kết thúc.
- Hiểu vì sao dấu `"` đơn lẻ hoặc cặp `""` được viết trực tiếp bên trong text block, còn **ba dấu `"""` liên tiếp** trong nội dung cần escape phù hợp.
- Phân tích tác động của vị trí dấu đóng tới **incidental indentation**, dấu cách cuối dòng, và giá trị chuỗi thực tế.
- Biên dịch/chạy các ví dụ **Java 17+** và tránh những lỗi cú pháp thường gặp.

**Phiên bản Java:** Text blocks được chuẩn hóa từ **Java 15** theo [JEP 378](https://openjdk.org/jeps/378). Dù chủ đề nằm trong lộ trình Java 14, kiến thức được trình bày theo **cú pháp chuẩn đang áp dụng cho Java hiện đại**. Các ví dụ chạy với `javac --release 17`; không cần `--enable-preview` và không dùng quy tắc riêng của bản preview.

## 1. Cấu trúc đầy đủ của một text block

Hình thức điển hình:

~~~java
String message = """
    Hello,
    Java!
    """;
~~~

Đây là một biểu thức Java hợp lệ; nó có **kiểu `String`**. Có ba phần:

1. **Opening delimiter**: bộ ba dấu `"""` ngay sau `=`.
2. **Content**: các ký tự sau ký tự kết thúc dòng của opening delimiter, gồm nhiều dòng nội dung.
3. **Closing delimiter**: bộ ba dấu `"""` ở cuối, theo sau là dấu `;` của câu lệnh.

Tài liệu JLS có thể được tóm tắt bằng cấu trúc:

~~~text
""" [khoảng trắng được phép] <line terminator>
<nội dung, có thể gồm ký tự xuống dòng>
"""
~~~

Các ký tự `<line terminator>` và `<nội dung>` ở khối trên chỉ là **ký hiệu giải thích**, không phải source code Java để copy nguyên văn.

### Dấu mở: ba dấu nháy kép + xuống dòng bắt buộc

Định nghĩa chính xác của **opening delimiter**:

- Bắt đầu bằng **đúng ba dấu `"` liên tiếp**.
- Có thể theo sau bởi **0 hoặc nhiều khoảng trắng được phép** trước khi xuống dòng (space, tab, form feed).
- **Bắt buộc kết thúc bằng line terminator**: LF, CR hoặc CRLF. Không được đặt ký tự nội dung ngay sau `"""` trên cùng dòng mở.
- **Line terminator sau dấu mở không tự trở thành ký tự `\n` đầu tiên của nội dung**. Nội dung bắt đầu **sau** ký tự kết thúc dòng đó.

Ví dụ hợp lệ:

~~~java
// HỢP LỆ: bắt đầu nội dung từ dòng kế tiếp.
String ok = """
    first
    second
    """;
~~~

Các ví dụ sau **không hợp lệ**, được đưa ra để phân biệt quy tắc, **không** đưa vào chương trình Java 17 thực thi ở phần sau:

~~~java
// SAI: không có dấu xuống dòng sau opening delimiter.
String wrong1 = """Hello""";

// SAI: nội dung "Hello" nằm trên dòng mở.
String wrong2 = """Hello
    world
    """;

// SAI: comment ngay sau dấu mở không phải whitespace được phép.
String wrong3 = """ // ghi chú
    Hello
    """;
~~~

Trường hợp source code có một vài dấu cách sau `"""` rồi mới xuống dòng **vẫn hợp lệ**. Tuy nhiên, để nhất quán và tránh các dấu cách vô hình, nên viết opening delimiter **ở cuối dòng khai báo** rồi xuống dòng ngay.

> **Cần nhớ:** Không có chuyện `"""Hello"""` là một text block một dòng hợp lệ. Nếu chỉ cần chuỗi một dòng ngắn, hãy dùng string literal thường: `"Hello"`.

## 2. Dấu đóng: ba dấu nháy kép xác định điểm kết thúc nội dung

**Closing delimiter** là bộ ba `"""`. Nội dung dừng **ngay trước dấu nháy kép đầu tiên của bộ đóng**. Vì vị trí đặt dấu đóng quyết định ký tự nào nằm trong nội dung, hai đoạn mã trông tương tự có thể cho ra hai chuỗi khác nhau.

### 2.1. Dấu đóng trên dòng riêng: giữ `\n` cuối

~~~java
String withNewline = """
    A
    B
    """;
~~~

Giá trị thực tế, sau khi bỏ các khoảng trắng thụt lề phụ do mã nguồn, tương đương:

~~~java
String withNewline = "A\nB\n";
~~~

Cả hai dòng `A` và `B` đều có ký tự xuống dòng sau chúng. Ký tự xuống dòng sau `B` thuộc **content**, vì dấu đóng nằm trên dòng tiếp theo.

Trong tình huống muốn tạo JSON/HTML/SQL đa dòng, cách viết này thường dễ đọc vì giữ dấu đóng thẳng hàng với lề nội dung; hãy **chủ động** chấp nhận `\n` cuối hoặc loại bỏ khi contract yêu cầu.

### 2.2. Dấu đóng ngay sau ký tự cuối: không có `\n` cuối

~~~java
String withoutNewline = """
    A
    B""";
~~~

Tương đương:

~~~java
String withoutNewline = "A\nB";
~~~

Ở đây dấu đóng xuất hiện ngay sau chữ `B`, vì vậy không có line terminator giữa `B` và closing delimiter. Điều này **không xóa** dấu xuống dòng giữa `A` và `B`; nó chỉ tránh đưa dấu xuống dòng **cuối cùng** vào chuỗi.

So sánh:

| Source text block | Giá trị `String` sau khi xử lý | Có ký tự LF cuối? |
|---|---|---|
| `"""` mở, dòng `A`, dòng `B`, dòng `"""` đóng riêng | `"A\nB\n"` | **Có** |
| `"""` mở, dòng `A`, `B"""` đóng cùng dòng `B` | `"A\nB"` | **Không** |
| `"""` mở, ngay dòng tiếp theo là `"""` đóng | `""` | **Không** |

Bảng mô tả **vị trí dấu phân cách**, không phải một đoạn Java có thể biên dịch nguyên dạng khi đặt trong ô bảng.

### 2.3. Text block rỗng cũng hợp lệ

~~~java
String empty = """
    """;
~~~

Giá trị của `empty` là `""`, có độ dài `0`. Opening delimiter vẫn phải kết thúc bằng newline; không có một dòng nội dung nào nằm giữa dòng mở và dòng đóng.

Nếu thêm một **dòng trống thực sự** trước closing delimiter, số ký tự xuống dòng được đưa vào kết quả sẽ thay đổi. Không nên chỉ nhìn số dòng trông thấy trong trình soạn thảo; hãy kiểm tra chuỗi bằng `length()` hoặc phép so sánh với `"\n"`.

### 2.4. Đóng text block chưa phải kết thúc câu lệnh Java

Trong `String text = """ ... """;`, bộ `"""` đóng **chỉ kết thúc literal**, còn `;` kết thúc câu lệnh Java. Khi text block xuất hiện trong một lời gọi phương thức, dấu `)` hoặc dấu phẩy ở ngoài literal thuộc cú pháp của lời gọi, không phải nội dung chuỗi.

~~~java
String name = """
    demo
    """.stripTrailing();

System.out.println(name);
~~~

Đoạn trên hợp lệ vì text block là một `String`, nên có thể gọi phương thức `String` ngay sau closing delimiter. Tuy nhiên, **`stripTrailing()` có thể thay đổi dấu xuống dòng cuối**, nên không nên dùng nó để thay thế cho việc hiểu đúng vị trí dấu đóng.

## 3. Các dấu nháy kép bên trong nội dung

### 3.1. Một hoặc hai dấu `"` không cần escape

Trong string literal thường, dấu `"` phải được viết là `\"`. Trong text block, các dấu nháy kép thông thường không cần escape:

~~~java
String json = """
    {
      "id": "A-1",
      "active": true
    }
    """;
~~~

Những dấu `"` bao quanh tên thuộc tính và giá trị JSON **là nội dung**, không làm kết thúc text block. Điều này giúp JSON, HTML attribute và đoạn mã Java nhúng trong `String` dễ đọc hơn nhiều so với chuỗi ghép cũ.

Ví dụ tương đương nhưng khó đọc hơn:

~~~java
String json = "{\n" +
        "  \"id\": \"A-1\",\n" +
        "  \"active\": true\n" +
        "}\n";
~~~

Hai cách đều cho một `String` chứa JSON; text block **không tự parse, validate hoặc escape JSON theo dữ liệu đầu vào**. Nó chỉ tạo ra nội dung ký tự.

### 3.2. Ba dấu `"""` liên tiếp trong nội dung: phải phân biệt dấu đóng

Nếu bạn muốn văn bản bên trong chứa **ba dấu nháy kép liên tiếp**, không thể viết thẳng `"""` một cách tùy ý: trình phân tích cú pháp Java có thể hiểu chúng là **closing delimiter**.

Giải pháp là escape **ít nhất một dấu `"` trong bộ ba nội dung**. Ví dụ dưới đây đã được biên dịch/chạy trên Java 17:

~~~java
String tripleQuote = """
    token: \"""
    """;
~~~

Kết quả thực tế:

~~~text
token: """
~~~

và có thêm `\n` cuối vì closing delimiter đặt trên một dòng riêng.

**Giải thích cách đếm:** `\"""` trong nội dung source code biểu diễn **ba dấu `"` như dữ liệu**: dấu đầu được viết bằng escape `\"`, hai dấu sau đứng trực tiếp. Nhờ escape, ba dấu này không bị nhận nhầm là closing delimiter.

Cách trình bày khác nếu muốn tất cả đều rõ ràng là dùng một số escape `\"` thích hợp, nhưng đừng tự động escape mọi dấu nháy kép đơn lẻ trong text block nếu không cần. Điều quan trọng là **không để ba dấu `"` liên tiếp của nội dung bị hiểu là ranh giới kết thúc literal**.

### 3.3. Text block chứa ví dụ cú pháp text block khác

Khi muốn lưu một đoạn Java source chứa `"""` trong một text block, phải escape các bộ ba dấu nháy kép nằm **trong nội dung**. Đó là trường hợp hay gặp khi viết tài liệu, công cụ sinh mã hoặc ví dụ giáo dục.

~~~java
// Đoạn minh họa, không phải một chương trình độc lập.
String source = """
    String nested = \"""
        hello
        \""";
    """;
~~~

Chuỗi `source` chứa **văn bản mã Java**; nó không tự tạo “text block lồng nhau” ở runtime. Java source phía ngoài vẫn chỉ có một text block, và các bộ ba dấu nháy kép của mã được chứa trong giá trị `String` cần được escape.

## 4. Vị trí closing delimiter và thụt lề (incidental whitespace)

Java xử lý **incidental indentation** để bạn có thể thụt lề code cho đẹp mà không bắt buộc đưa toàn bộ lề ấy vào `String`. Vị trí dòng đóng giúp xác định lề nào được coi là **phụ trợ** và lề nào là **nội dung thực sự**.

Ví dụ:

~~~java
String indent = """
        A
          B
      """;
~~~

Ở đây:

- Dòng `A` được thụt lề nhiều hơn dòng closing delimiter **2 dấu cách**.
- Dòng `B` thụt thêm **2 dấu cách** nữa so với dòng `A`.
- Sau khi Java loại khoảng trắng thụt lề phụ, chuỗi giữ lại hai dấu cách trước `A` và bốn dấu trước `B`.

Để thấy khoảng trắng, có thể thay dấu cách bằng ký hiệu `·` khi in:

~~~text
··A
····B
~~~

Dòng hiển thị trên là **giá trị nhìn thấy của khoảng trắng**, không phải nguyên văn gồm các ký tự `·`.

### Vì sao đặt dấu đóng quan trọng?

Khi closing delimiter nằm **trên dòng riêng**, mức indent của dòng đó có thể ảnh hưởng đến lượng whitespace phụ được loại bỏ. Nếu đẩy closing delimiter về sát trái hơn, bạn có thể giữ lại nhiều khoảng trắng hơn trong nội dung.

Khi closing delimiter nằm **ngay sau nội dung cuối cùng**, không còn một dòng closing delimiter riêng để tham gia vào việc xác định lượng indent cần bỏ. Vì thế, đừng coi cách dịch dấu đóng là thao tác “chỉ làm đẹp”; nó có thể làm thay đổi giá trị `String`.

### Lời khuyên định dạng

Thông thường, hãy đặt:

- Opening delimiter ở cuối dòng khai báo/lời gọi.
- Nội dung text block thụt lề tương ứng với cấu trúc mã.
- Closing delimiter **trên dòng riêng** thẳng hàng với lề mong muốn của văn bản, nếu bạn muốn giữ newline cuối.

Nếu **không** muốn newline cuối, đặt closing delimiter ngay sau ký tự nội dung cuối. Luôn kiểm tra giá trị chuỗi khi căn lề có ý nghĩa (ví dụ snapshot test, định dạng file có ý nghĩa whitespace).

## 5. Dấu phân cách, ký tự xuống dòng và escape không phải cùng một thứ

### 5.1. Java chuẩn hóa line terminators trong nội dung

Nguồn Java có thể dùng LF (`\n`) hoặc CRLF (`\r\n`) tùy hệ điều hành và editor. Với text block, line terminators trong phần nội dung được **chuẩn hóa về LF `\n`** theo quy tắc ngôn ngữ.

Điều này không có nghĩa kết quả luôn có `\n` ở cuối; điều đó còn phụ thuộc **vị trí closing delimiter** như phần 2. Nếu phải xuất file với quy tắc xuống dòng riêng của giao thức/hệ điều hành, hãy xử lý ở ranh giới I/O thay vì ngầm tin source code định dạng sẵn.

### 5.2. Dấu cách ở cuối dòng và escape `\s`

Java mặc định loại **incidental trailing whitespace** trong text block. Nếu một dấu cách cuối dòng thực sự có ý nghĩa, dùng escape `\s` để biểu diễn chính xác một dấu cách sau khi bước xử lý lề kết thúc:

~~~java
String trailing = """
    X\s
    """;
~~~

Giá trị chuỗi gồm chữ `X`, **một dấu cách**, sau đó là `\n`. Không phải chữ `X` theo sau bởi hai ký tự `\` và `s`.

Trong ví dụ thực thi ở phần 7, dấu cách này được hiển thị thành `·` để dễ nhìn:

~~~text
trailing=[X·\n]
~~~

Lưu ý: `\s` ở đây là **Java string escape** được hỗ trợ trong text blocks, không phải ký hiệu whitespace của một regex đang được parse.

### 5.3. Dấu `\` cuối dòng để nối nội dung

Text block hỗ trợ **line continuation**: khi `\` là ký tự cuối của dòng nguồn thuộc nội dung, ký tự xuống dòng sau nó được loại khỏi kết quả:

~~~java
String joined = """
    first \
    second
    """;
~~~

Với các dòng trên, `joined` bằng `"first second\n"`: dấu cách trước `\` vẫn tồn tại, nhưng **không** có newline giữa `first` và `second`.

Thao tác này **khác** việc đặt closing delimiter ngay sau chữ `second`:

- Nối dòng bằng `\` có thể loại newline **ở giữa** nội dung.
- Đặt `"""` đóng cùng dòng cuối loại newline **sau ký tự nội dung cuối**.

Cả hai đều là cú pháp hiện đại; chỉ dùng khi bạn thực sự muốn kiểm soát kết quả chuỗi.

### 5.4. Text block không phải raw string tuyệt đối

Text block giảm nhu cầu escape dấu `"` và newline, nhưng **vẫn diễn giải các escape hợp lệ** như `\n`, `\t`, `\"`, `\\`, `\s` và line continuation. Nếu nội dung là biểu thức regex hoặc đường dẫn chứa nhiều `\`, cần đếm lại escape như với String thông thường.

Ví dụ:

~~~java
String path = """
    C:\\temp\\file.txt
    """;
~~~

Kết quả chứa các dấu gạch chéo ngược của đường dẫn Windows, nhưng vẫn có newline cuối vì dấu đóng ở dòng riêng. Khi viết literal regex, giữ đúng số lớp escape (Java source → `String` → regex engine); text block không loại bỏ nhu cầu đó.

## 6. Ví dụ Java 17 hoàn chỉnh, đối chiếu chính xác đầu ra

Tạo tệp **`TextBlockDelimiterDemo.java`** với nội dung:

~~~java
public final class TextBlockDelimiterDemo {

    private static String show(String input) {
        return "[" + input.replace(" ", "·").replace("\n", "\\n") + "]";
    }

    public static void main(String[] args) {
        String withNewline = """
            A
            B
            """;

        String withoutNewline = """
            A
            B""";

        String empty = """
            """;

        String quotes = """
            value: "Hi"
            """;

        String tripleQuote = """
            token: \"""
            """;

        String indent = """
                A
                  B
              """;

        String trailing = """
            X\s
            """;

        String joined = """
            first \
            second
            """;

        System.out.println("withNewline=" + show(withNewline));
        System.out.println("withoutNewline=" + show(withoutNewline));
        System.out.println("emptyLength=" + empty.length());
        System.out.println("quotes=" + show(quotes));
        System.out.println("tripleQuote=" + show(tripleQuote));
        System.out.println("indent=" + show(indent));
        System.out.println("trailing=" + show(trailing));
        System.out.println("joined=" + show(joined));
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 17 -encoding UTF-8 TextBlockDelimiterDemo.java
java TextBlockDelimiterDemo
~~~

**Đầu ra chính xác đã được kiểm tra bằng trình biên dịch Java 17 target và chương trình chạy thực tế:**

~~~text
withNewline=[A\nB\n]
withoutNewline=[A\nB]
emptyLength=0
quotes=[value:·"Hi"\n]
tripleQuote=[token:·"""\n]
indent=[··A\n····B\n]
trailing=[X·\n]
joined=[first·second\n]
~~~

**Cách đọc biểu diễn ở output:**

- `show(...)` **không in dấu xuống dòng gốc**; nó biến mỗi ký tự LF thật thành **hai ký tự** `\` và `n`, mỗi dấu cách thường thành `·`, sau đó bao bằng `[ ]`.
- Vì vậy `withNewline=[A\nB\n]` chứa **hai LF** trong chuỗi gốc, còn `withoutNewline=[A\nB]` chỉ có **một LF**.
- `quotes` cho thấy các dấu `"` đơn lẻ trong text block vẫn là dữ liệu.
- `tripleQuote` chứng minh `\"""` trong Java source tạo bộ `"""` thật trong kết quả.
- `indent` xác nhận hai và bốn dấu cách **có ý nghĩa** còn lại sau khi loại incidental indentation.
- `trailing` xác nhận `\s` tạo dấu cách thực ở cuối dòng.
- `joined` chứng minh line continuation loại newline giữa `first` và `second` nhưng vẫn có newline cuối do dấu đóng trên dòng riêng.

**Một phép kiểm tra tương đương có thể thêm vào `main`:** `withNewline.equals("A\nB\n")` trả `true` và `withoutNewline.equals("A\nB")` cũng trả `true`. Không cần in các kiểm tra này vì chương trình đã hiển thị đúng ký tự xuống dòng dưới dạng nhìn thấy.

## 7. Các lỗi phổ biến với dấu `"""`

| Lỗi | Triệu chứng / nguyên nhân | Cách sửa |
|---|---|---|
| Viết `"""Hello"""` | Không có line terminator sau opening delimiter → lỗi biên dịch | Dùng `"Hello"` cho chuỗi một dòng hoặc mở text block rồi xuống dòng |
| Đặt JSON hoặc HTML ngay sau ba dấu mở | Opening delimiter đòi xuống dòng trước nội dung | Chuyển nội dung xuống dòng kế tiếp |
| Viết comment `// ...` sau dấu mở trên cùng dòng | `//` không thuộc whitespace được phép của opening delimiter | Đặt comment ngoài text block |
| Quên bộ ba dấu đóng | Literal chưa kết thúc → lỗi phân tích cú pháp | Thêm đúng `"""` tại vị trí muốn dừng nội dung |
| Đổi dấu đóng từ dòng riêng sang cuối dòng nội dung mà không xem output | Mất `\n` cuối, có thể ảnh hưởng snapshot/test hoặc file output | Quyết định có cần newline cuối hay không và đặt dấu đóng đúng |
| Dời closing delimiter về trái/phải mà coi là thay đổi trình bày vô hại | Có thể thay đổi incidental indentation | Dùng test hiển thị khoảng trắng, so sánh `String` chính xác |
| Escape mọi dấu `"` trong JSON | Mã rối, mất lợi ích của text block | Giữ dấu `"` đơn/cặp trực tiếp; escape khi cần chứa `"""` liên tiếp |
| Muốn chứa `"""` nhưng gõ thẳng không escape | Có thể kết thúc text block sớm | Escape ít nhất một dấu, ví dụ `\"""` |
| Cho rằng text block giữ nguyên mọi dấu cách cuối dòng | Compiler loại incidental trailing whitespace | Dùng `\s` hoặc cơ chế khác có chủ đích |
| Dùng `\` cuối dòng nhưng muốn giữ newline | Line continuation loại newline đó | Bỏ `\` nếu muốn dòng mới thật |
| Cho rằng text block không xử lý escape | `\n`, `\t`, `\\`… vẫn được xử lý | Đếm đúng escape của Java source |
| Dùng text block để xây SQL hoặc JSON bằng nối chuỗi dữ liệu người dùng | Dữ liệu chưa được escape/validate đúng giao thức | Với SQL dùng prepared statements; với JSON dùng serializer/mapping library |
| Đòi code Java 17 dùng flag preview để bật text blocks | Tính năng đã chuẩn từ Java 15 | Dùng Java 17+ bình thường, không cần preview |

**Mẹo tránh nhầm lẫn:** Khi lỗi do dấu phân cách, trước tiên đếm **ba dấu nháy kép**, kiểm tra **dòng mở có kết thúc bằng newline không**, rồi nhìn **nơi dấu đóng xuất hiện**. Sau đó mới xét các escape và khoảng trắng.

## 8. Khi nào nên dùng text block thay string literal thường?

**Nên dùng** khi dữ liệu là văn bản nhiều dòng hoặc có nhiều dấu `"`: JSON mẫu, HTML, SQL được viết tĩnh, đoạn thông báo dài, tài liệu hay đoạn mã nguồn trong test.

**Chưa chắc nên dùng** cho chuỗi rất ngắn, nhất là khi bạn phải tạo một dòng text block bằng một dòng mở riêng và đặt dấu đóng cạnh ký tự cuối. Ví dụ `String greeting = "Hi";` thường gọn và rõ hơn một text block có nhiều dòng mã nguồn.

**Cần cân nhắc tính chính xác byte/ký tự** khi làm protocol, chữ ký số, golden file, hash hoặc so sánh snapshot. Text block có các bước chuẩn hóa lề và line terminators; những thay đổi nhìn như “chỉnh format Java” có thể thay đổi giá trị đầu ra. Lúc đó nên có test so sánh chính xác chuỗi hoặc dùng tài nguyên ngoài mã nguồn khi định dạng phải bảo toàn tuyệt đối.

## 9. Bài tự kiểm tra

**Câu 1.** Đoạn này có hợp lệ không?

~~~java
String s = """hello""";
~~~

**Đáp án:** Không. Sau opening delimiter `"""` phải có line terminator. Nếu chỉ cần `hello`, dùng `"hello"`.

**Câu 2.** Hai đoạn dưới đây cho ra các `String` khác nhau thế nào?

~~~java
String a = """
    x
    y
    """;

String b = """
    x
    y""";
~~~

**Đáp án:** `a.equals("x\ny\n")` là `true`; `b.equals("x\ny")` là `true`. Khác biệt là LF cuối chuỗi.

**Câu 3.** Trong text block chứa JSON, có phải viết `\"id\"` thay cho `"id"` không?

**Đáp án:** Không. Một dấu `"` hoặc cặp `""` đơn thuần có thể xuất hiện trực tiếp. Chỉ khi tạo **bộ `"""` liên tiếp** bên trong nội dung mới cần escape để không bị hiểu là dấu đóng.

**Câu 4.** Đoạn `String t = """` rồi xuống dòng và ngay dòng kế tiếp là `""";` có độ dài bao nhiêu?

**Đáp án:** `0`. Line terminator của opening delimiter là một phần của cú pháp mở, không tự trở thành nội dung.

**Câu 5.** Tại sao `String s = """` có dấu đóng trên dòng riêng lại có thể tạo khoảng trắng đầu dòng khác với khi dấu đóng nằm ngay cuối dòng cuối?

**Đáp án:** Khi dấu đóng nằm trên dòng riêng, lề của dòng đó tham gia quy tắc xác định incidental indentation; khi nằm ở cuối dòng nội dung, quy tắc xét lề theo các dòng nội dung. Vì thế vừa có khác biệt ở LF cuối vừa có thể khác ở số dấu cách được giữ lại.

**Câu 6.** Muốn lưu chính xác ký tự `"""` như văn bản bên trong text block, nên làm gì?

**Đáp án:** Escape ít nhất một dấu `"` thuộc bộ ba, ví dụ `\"""` trong Java source; kiểm tra đầu ra để chắc chắn nhận ba dấu `"`.

**Câu 7.** `\s` và `\` cuối dòng khác nhau thế nào?

**Đáp án:** `\s` tạo một dấu cách trong `String`, còn `\` ở cuối một dòng source text block tạo line continuation và **bỏ newline** sau nó. Cả hai không thay thế quy tắc bắt buộc xuống dòng sau opening delimiter.

## 10. Tài liệu tham khảo chính thức

- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): mốc chuẩn hóa text blocks từ Java 15; cú pháp, ví dụ và xử lý khoảng trắng.
- [Java Language Specification SE 17 — `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): opening delimiter, closing delimiter và ranh giới chính xác của nội dung.
- [Java Language Specification SE 17 — `3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.7): `\s`, line continuation và các escape trong string/text block.
- [Oracle — Programmer's Guide to Text Blocks (Java 17)](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): vị trí dấu đóng, newline cuối, indent, dấu nháy kép và hướng dẫn định dạng.
- [Oracle — Java 17 Text Blocks language guide](https://docs.oracle.com/en/java/javase/17/language/text-blocks.html): các quy tắc ngôn ngữ cơ bản và ví dụ thực tế.

**Ghi nhớ:** Opening delimiter là `"""` **cộng với dấu kết thúc dòng bắt buộc**; closing delimiter là `"""` tại vị trí bạn muốn dừng nội dung. Đặt dấu đóng **trên dòng riêng** thường giữ `\n` cuối; đặt nó **ngay sau ký tự cuối** sẽ không thêm newline cuối. Dấu `"` thông thường là nội dung, còn bộ `"""` cần escape nếu phải xuất hiện như dữ liệu bên trong.
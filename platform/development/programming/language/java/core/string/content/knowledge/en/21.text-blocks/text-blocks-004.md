# Khoảng trắng thụt lề ngẫu nhiên và vị trí dấu đóng trong Java text block

## 1. Vì sao cùng một text block có thể cho ra chuỗi khác nhau?

**Text block** là cú pháp chuỗi nhiều dòng của Java (chuẩn từ Java 15). Nó bắt đầu bằng ba dấu nháy kép `"""`, theo sau bắt buộc là một dấu kết thúc dòng, và kết thúc bằng ba dấu nháy kép `"""`. Mục tiêu là giúp nhúng văn bản nhiều dòng (SQL, JSON, HTML, thông báo...) dễ đọc mà không phải ghép nhiều string literal.

Tuy nhiên, có hai loại khoảng trắng rất dễ nhầm:

- **Khoảng trắng thụt lề ngẫu nhiên** (*incidental whitespace*): phần thụt vào chỉ nhằm làm mã nguồn Java đẹp, thường sẽ được tự động bỏ khỏi giá trị `String`.
- **Khoảng trắng mang ý nghĩa nội dung** (*essential whitespace*): phần thụt lề cần được giữ lại vì thuộc chính văn bản, ví dụ hai khoảng trắng trước một dòng YAML hoặc bốn khoảng trắng trước một khối code.

Vị trí của **dấu đóng `"""`** tham gia trực tiếp vào cách Java xác định cần loại bỏ bao nhiêu khoảng trắng ở đầu mỗi dòng. Thay đổi vị trí dấu đóng, ngay cả khi không sửa nội dung chữ, có thể làm **thay đổi giá trị chuỗi runtime**. Đây là một phần ngữ nghĩa Java, không đơn thuần là chuyện định dạng trình soạn thảo.

## 2. Cú pháp và quy tắc dòng đầu tiên

```java
String message = """
        Xin chào,
        Đây là Java text block.
        """;
```

Đây là đoạn mã minh họa bên trong một phương thức hoặc initializer. Sau dấu mở `"""`, Java yêu cầu một line terminator: không được đặt ngay phần nội dung lên cùng dòng với dấu mở. Dấu xuống dòng **ngay sau dấu mở** là thành phần cú pháp, không tự trở thành một dòng trống ở đầu giá trị.

Với bố cục trên, nội dung runtime tương đương:

```text
Xin chào,\n
Đây là Java text block.\n
```

Trong khối `text` này, ký hiệu `\n` biểu thị một ký tự LF ở cuối mỗi dòng; nó không có nghĩa hai ký tự nguyên văn `\` và `n`. Text block thông thường **có ký tự xuống dòng cuối** khi dấu đóng nằm trên dòng riêng sau dòng nội dung cuối.

Viết như sau là không hợp lệ vì thiếu line terminator sau dấu mở:

```java
// Không hợp lệ: nội dung xuất hiện ngay sau dấu mở.
// String bad = """hello""";
```

Mặc dù dùng ba dấu nháy, kết quả vẫn là một đối tượng `String` bình thường: có thể gọi `length()`, `equals()`, `lines()`, `formatted()`, v.v. Text block không tự thêm indentation cho mục đích hiển thị; nó tạo đúng các ký tự theo quy tắc Java.

## 3. Java xác định và loại bỏ indentation ngẫu nhiên như thế nào?

Trước khi xử lý escape sequence, Java chuẩn hóa các dấu kết thúc dòng của text block thành LF, rồi loại bỏ indentation ngẫu nhiên. Có thể hình dung thuật toán quan trọng nhất như sau:

1. Xét lượng whitespace đầu dòng của **các dòng nội dung không trống**.
2. Nếu dấu đóng `"""` nằm trên **dòng riêng**, khoảng trắng trước dấu đóng cũng là một mốc để xác định indentation.
3. Lấy mức thụt đầu dòng **nhỏ nhất** trong các mốc kể trên; loại bỏ tối đa lượng whitespace chung đó ở đầu mỗi dòng.
4. Whitespace vô nghĩa ở cuối dòng bị loại bỏ trong bước xử lý indentation; xử lý escape sequence được thực hiện sau đó.

Dòng trống không nên dùng làm mốc để đo indentation đầu dòng; ý nghĩa của dòng trống và khoảng trắng ở cuối dòng cần được xét riêng. Khi dùng tab, mỗi ký tự whitespace có ý nghĩa theo nội dung chuỗi; không nên dựa vào độ rộng hiển thị tab của IDE để dự đoán chính xác số ký tự bị loại bỏ.

**Lưu ý quan trọng:** Java không “xóa hết tất cả dấu cách đầu dòng”. Nó bỏ **phần thụt chung nhỏ nhất**, nên phần thụt lề chênh lệch giữa các dòng được giữ lại.

Ví dụ:

```java
String block = """
        first
          second
        third
        """;
```

Các dòng `first` và `third` cùng có tám dấu cách trong mã nguồn, còn `second` nhiều hơn hai dấu. Dấu đóng cũng thụt tám dấu cách. Sau khi bỏ phần thụt chung, giá trị tương đương:

```text
first\n
··second\n
third\n
```

Trong minh họa kết quả này, `·` dùng để **nhìn thấy một dấu cách**: `second` vẫn giữ đúng hai dấu cách có ý nghĩa so với các dòng còn lại.

## 4. Vị trí dấu đóng thay đổi indentation thực tế

Hãy so sánh ba text block chứa đúng hai dòng nội dung `red` và `blue`.

### Trường hợp A: Dấu đóng thẳng hàng với nội dung

```java
String aligned = """
        red
        blue
        """;
```

Cả các dòng nội dung và dòng dấu đóng đều có tám dấu cách đầu dòng trong mã nguồn. Mức thụt chung là tám; tất cả được gỡ bỏ:

```text
red\n
blue\n
```

### Trường hợp B: Dấu đóng lùi sang trái

```java
String closingLeft = """
        red
        blue
    """;
```

Dấu đóng chỉ có bốn dấu cách đầu dòng. Mức thụt chung nhỏ nhất giờ là **bốn**. Do đó mỗi dòng nội dung còn **bốn dấu cách ở đầu**:

```text
····red\n
····blue\n
```

Đây là nguồn gốc phổ biến của indentation ngoài ý muốn khi người viết di chuyển dấu đóng về bên trái để “căn cho đẹp”. Cùng một phần nội dung chữ, nhưng kết quả chuỗi có thêm khoảng trắng ở đầu mỗi dòng.

### Trường hợp C: Dấu đóng tiến sang phải

```java
String closingRight = """
        red
        blue
            """;
```

Dấu đóng có mười hai dấu cách đầu dòng, nhưng hai dòng nội dung chỉ có tám. Mức nhỏ nhất vẫn là **tám**, nên kết quả giống trường hợp A:

```text
red\n
blue\n
```

Dịch dấu đóng sang phải **không thể tự động loại bỏ quá phần indentation chung của các dòng nội dung**. Các con số trên được tính từ đúng số dấu cách thể hiện trong ví dụ, không phải độ rộng tab hoặc tuỳ chọn format của IDE.

## 5. Dấu đóng cùng dòng với nội dung cuối: ký tự xuống dòng cuối

Hai cách đặt dấu đóng sau đây khác nhau:

```java
String withFinalLF = """
        red
        blue
        """;

String withoutFinalLF = """
        red
        blue""";
```

- `withFinalLF` có giá trị tương đương `"red\nblue\n"`: sau `blue` còn một LF.
- `withoutFinalLF` có giá trị tương đương `"red\nblue"`: không có LF cuối vì dấu đóng đứng **ngay sau chữ `blue`** trên cùng dòng.

Việc đặt dấu đóng chung dòng với nội dung cuối là cách hợp lệ để chủ động bỏ LF cuối. Không nên nhầm với việc bỏ line terminator sau dấu **mở**: dấu mở luôn cần theo sau bởi line terminator theo cú pháp text block.

Nếu chèn thêm dấu cách trước dấu đóng ở cùng dòng, các dấu cách đó có thể ảnh hưởng đến nội dung; muốn giữ/bỏ dấu cách một cách có chủ đích, hãy kiểm tra giá trị thực bằng phép so sánh hoặc bằng một hàm in ký tự hữu hình, không dựa vào mắt thường.

## 6. Chương trình Java 17+ kiểm chứng từng trường hợp

Tạo file `TextBlockIndentDemo.java` với nội dung sau. Đây là một chương trình độc lập có thể biên dịch và chạy:

```java
public class TextBlockIndentDemo {
    static void show(String name, String value) {
        String visible = value.replace(" ", "·")
                .replace("\n", "\\n")
                .replace("\t", "\\t");
        System.out.println(name + ": [" + visible + "] len=" + value.length());
    }

    public static void main(String[] args) {
        String aligned = """
                red
                blue
                """;

        String closingLeft = """
                red
                blue
            """;

        String closingRight = """
                red
                blue
                    """;

        String noFinalNewline = """
                red
                blue""";

        String uneven = """
                red
                  blue
                """;

        String preservedSpace = """
                hi\s\s
                """;

        show("aligned", aligned);
        show("closingLeft", closingLeft);
        show("closingRight", closingRight);
        show("noFinalNewline", noFinalNewline);
        show("uneven", uneven);
        show("preservedSpace", preservedSpace);
    }
}
```

Lệnh chạy:

```bash
javac --release 17 -encoding UTF-8 TextBlockIndentDemo.java
java TextBlockIndentDemo
```

Kết quả đã kiểm chứng bằng JDK ở chế độ `--release 17`:

```text
aligned: [red\nblue\n] len=9
closingLeft: [····red\n····blue\n] len=17
closingRight: [red\nblue\n] len=9
noFinalNewline: [red\nblue] len=8
uneven: [red\n··blue\n] len=11
preservedSpace: [hi··\n] len=5
```

Quy ước đọc output: mỗi ký tự `·` là **một dấu cách U+0020**; `\n` trong output là hai ký tự hiển thị biểu diễn **một LF thực** trong chuỗi. `len` là độ dài `String` tính theo đơn vị UTF-16; trong những ví dụ chỉ dùng chữ ASCII, khoảng trắng và LF này, mỗi ký tự tương ứng một đơn vị độ dài.

Quan sát:

- `aligned` và `closingRight` đều cho `red\nblue\n`, độ dài 9.
- `closingLeft` giữ bốn dấu cách trước **mỗi** dòng nội dung; độ dài tăng từ 9 lên 17.
- `noFinalNewline` ngắn hơn `aligned` đúng một ký tự LF.
- `uneven` giữ hai dấu cách trước `blue` vì đó là phần thụt lề chênh lệch.
- `preservedSpace` giữ **hai dấu cách ở cuối chữ `hi`** nhờ `\s\s`; cách xử lý này được giải thích ở phần tiếp theo.

Dùng `String.equals` khi muốn kiểm tra nội dung thực tế. Ví dụ `aligned.equals("red\nblue\n")` bằng `true`, nhưng `aligned.equals("red\nblue")` bằng `false` vì khác LF cuối.

## 7. Khoảng trắng cuối dòng, dòng trống và escape `\s`

Text block tự động loại bỏ whitespace thừa **ở cuối dòng** trong quá trình xử lý indentation. Nếu chủ động gõ một vài dấu cách sau chữ cuối dòng trong source, các dấu cách đó có thể bị loại bỏ và rất khó nhận ra trong review.

Trong Java text block, viết escape `\s` để bảo toàn **một dấu cách thường** ở một vị trí mong muốn, nhất là cuối dòng:

```java
String preserved = """
        hi\s\s
        """;
```

Sau khi xử lý, `preserved` tương đương `"hi  \n"`, gồm hai dấu cách sau `hi` rồi mới đến LF. Điều này hoạt động vì Java thực hiện xử lý escape sequence **sau bước loại bỏ indentation và whitespace cuối dòng**.

Các dòng trống thực sự cũng là một phần nội dung:

```java
String paragraph = """
        Đoạn một.

        Đoạn hai.
        """;
```

Kết quả có **một dòng trống** giữa hai đoạn: sau `Đoạn một.` là hai LF liên tiếp (một để kết thúc dòng và một đại diện cho dòng trống). Dòng trống không mang văn bản để dự đoán mức thụt chung; khi dữ liệu yêu cầu giữ space trên dòng trống, nên dùng escape rõ ràng thay vì khoảng trắng vô hình.

Một escape đặc biệt khác trong text block là dấu backslash `\` ngay trước line terminator: nó có thể **nối hai dòng mà không đưa LF vào chuỗi**. Ví dụ:

```java
String joined = """
        micro\
        service
        """;
```

Nội dung tương đương `"microservice\n"`. Đây là hành vi có chủ đích, **khác** với đặt dấu đóng cùng dòng cuối để bỏ riêng LF cuối của toàn bộ chuỗi.

## 8. Liên hệ với `stripIndent()` và `indent()`

Java còn cung cấp các phương thức thao tác indentation trên `String`:

- `stripIndent()` loại bỏ indentation chung và whitespace cuối dòng theo các quy tắc của API. Text block dùng ý tưởng này để chuẩn hóa indentation; tuy nhiên khi viết text block, **vị trí của dòng dấu đóng** cũng tham gia quyết định mức thụt của nội dung nguồn.
- `indent(int n)` điều chỉnh indentation của các dòng trong một chuỗi đã có; với `n > 0`, nó thêm khoảng trắng đầu mỗi dòng, còn `n < 0` thì giảm mức thụt có thể bỏ. Phương thức này còn chuẩn hóa line terminator và bảo đảm kết quả theo quy ước dòng của API, nên cần kiểm thử nếu giữ nguyên newline cuối là yêu cầu.

Đừng mặc định có thể thay đổi vị trí dấu đóng rồi “bù” bằng một lệnh format mà chuỗi vẫn giữ nguyên. Nếu chuỗi mang nội dung nhạy cảm với khoảng trắng (YAML, Python, Markdown, chữ ký/hash, template hoặc output snapshot), mỗi khoảng trắng và ký tự xuống dòng đều có thể ảnh hưởng đến kết quả.

## 9. Những lỗi thường gặp khi format text block

1. **Đưa dấu đóng về quá trái:** làm mức thụt nhỏ nhất giảm và vô tình giữ thêm dấu cách ở mỗi dòng nội dung.
2. **Nghĩ dấu đóng càng sang phải càng xóa thêm indentation:** thực tế phần thụt chung còn bị giới hạn bởi các dòng nội dung ít thụt nhất.
3. **Quên LF cuối:** dấu đóng trên dòng riêng thường tạo LF cuối; đặt dấu đóng ngay sau nội dung cuối để bỏ nó một cách chủ đích.
4. **Tưởng thụt lề ở mọi dòng đều bị xóa hoàn toàn:** Java chỉ bỏ phần indentation chung. Các dòng thụt sâu hơn giữ phần chênh lệch.
5. **Cố lưu space cuối dòng bằng cách gõ space trần:** whitespace cuối dòng thường bị xóa; dùng `\s` khi thật sự phải giữ.
6. **Trộn tab và space:** độ rộng hiển thị tab trong editor không phải thước đo đáng tin cho ký tự trong `String`. Chọn một quy ước indentation thống nhất và kiểm tra kết quả nếu dữ liệu nhạy cảm.
7. **Nhầm ký hiệu hiển thị với ký tự runtime:** chuỗi hiển thị `\n` trong công cụ debug có thể đại diện cho một LF; cần phân biệt chữ escape được in ra với newline thật.
8. **Chỉ xem code mà không kiểm tra giá trị:** đặt test `equals` hoặc in độ dài cùng marker ký tự trắng cho template mà whitespace quyết định ý nghĩa.

### Checklist trước khi sửa hoặc review

- Xác định **dấu đóng `"""`** đang nằm trên dòng riêng hay cùng dòng cuối.
- Đếm indentation của các dòng **không trống** và của dòng dấu đóng (nếu riêng).
- Xác định phần thụt chung được loại bỏ và phần chênh lệch sẽ giữ lại.
- Kiểm tra có LF cuối, dòng trống và whitespace cuối dòng hay không.
- Với nội dung có ý nghĩa về whitespace, kiểm tra `length()`, `equals()` hoặc chương trình in dấu cách thành marker, thay vì chỉ nhìn vào IDE.

**Ghi nhớ:** text block làm mã nguồn gọn hơn nhưng vẫn phải tạo ra `String` chính xác. Khi dấu đóng trên dòng riêng, **indentation của nó có thể quyết định lượng khoảng trắng bị loại bỏ**; khi dấu đóng nằm sát chữ cuối, **LF cuối có thể biến mất**. Java chỉ bỏ phần thụt chung, nên phần thụt lề chênh lệch và các escape có chủ đích vẫn ảnh hưởng đến nội dung.

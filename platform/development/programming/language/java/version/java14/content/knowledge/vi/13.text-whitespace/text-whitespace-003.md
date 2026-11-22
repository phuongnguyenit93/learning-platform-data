# Xác định khoảng trắng chung được loại bỏ trong Java text block

**Text block** là cách viết chuỗi nhiều dòng trong Java bằng cặp dấu phân định `"""`. Khi dùng text block trong mã nguồn có thụt lề, Java không giữ nguyên tất cả khoảng trắng nhìn thấy trong editor: trình biên dịch tự loại bỏ **incidental whitespace** (khoảng trắng phát sinh do căn lề mã nguồn), đồng thời giữ lại **essential whitespace** (phần thụt lề có chủ đích bên trong văn bản). Hiểu chính xác cách tìm **khoảng trắng chung cần loại bỏ** là rất quan trọng khi lưu HTML, JSON, SQL, mẫu thông báo hoặc đoạn mã dưới dạng chuỗi.

Ví dụ, hai dòng HTML có thể thụt lề 12 và 16 ký tự trong file Java, nhưng giá trị chuỗi thực tế có mức thụt lề tương đối là **0 và 4**. Khi dịch chuyển dấu `"""` đóng sang trái hoặc phải, số ký tự bị loại bỏ cũng có thể thay đổi.

Text block được chuẩn hóa thành tính năng chính thức từ **Java 15** (JEP 378) và vẫn dùng trong Java 17+ và các phiên bản hiện đại. Bài này tập trung vào ngữ nghĩa còn áp dụng hiện nay; các ví dụ chạy với Java 17 trở lên, không sử dụng cú pháp preview.

## 1. Hiểu text block trước khi tính độ thụt lề

Cú pháp cơ bản:

~~~java
String html = """
        <section>
            <p>Hello</p>
        </section>
        """;
~~~

Trong một chương trình Java, sau dấu mở `"""` phải có dấu kết thúc dòng; không viết toàn bộ nội dung text block ngay trên cùng dòng với dấu mở. Dấu đóng `"""` có thể đặt ở dòng riêng hoặc ngay sau ký tự cuối của dòng nội dung.

Điểm cần phân biệt:

- **Khoảng trắng trong mã nguồn:** các ký tự khoảng trắng và tab đứng trước những dòng của text block trong file `.java`.
- **Khoảng trắng chung bị loại bỏ:** số ký tự đầu dòng tối thiểu mà thuật toán xác định là *incidental*.
- **Khoảng trắng giữ lại:** phần thụt lề còn dư so với mức chung; nó biểu thị cấu trúc tương đối của văn bản.
- **Khoảng trắng cuối dòng:** dấu cách/tab nằm sau ký tự nội dung trước khi xuống dòng; thường bị xóa như incidental whitespace.
- **Ký tự xuống dòng:** text block nhiều dòng thường chứa ký tự `\n`; nếu dấu đóng nằm trên dòng riêng, chuỗi thường có `\n` cuối cùng.

Kết quả tương đương của ví dụ trên là chuỗi:

~~~java
"<section>\n    <p>Hello</p>\n</section>\n"
~~~

Đây là **biểu thức chuỗi minh họa**, không phải một chương trình độc lập. Hai dòng mở/đóng `<section>` sau xử lý không còn thụt lề, nhưng dòng `<p>` vẫn giữ **4 dấu cách** trước nó.

## 2. Quy tắc chuẩn: lấy mức thụt lề nhỏ nhất ở các dòng phù hợp

Quy trình xử lý của Java được mô tả trong Java Language Specification (JLS `3.10.6) theo thứ tự:

1. **Chuẩn hóa line terminators:** các kết thúc dòng CRLF và CR trong nội dung được chuẩn hóa về ký tự LF (`\n`).
2. **Loại bỏ incidental whitespace:** áp dụng ngữ nghĩa tương đương `String.stripIndent()` lên nội dung đã chuẩn hóa.
3. **Diễn giải escape sequences:** chỉ ở bước cuối, các escape như `\s`, `\040`, `\n`, hoặc ký hiệu tiếp dòng mới được xử lý.

Để **xác định độ thụt lề chung**, có thể đọc thuật toán theo các bước sau:

1. Chia nội dung thành từng dòng.
2. Với **mỗi dòng không trống**, đếm số ký tự whitespace liên tiếp từ đầu dòng đến ký tự không phải whitespace đầu tiên.
3. **Dòng cuối của nội dung** cũng được xét ngay cả nếu nó chỉ gồm whitespace. Khi dấu `"""` đóng đứng ở dòng riêng, các dấu cách đứng trước nó tạo thành dòng cuối loại này và **có thể quyết định mức thụt lề chung**.
4. Lấy **giá trị nhỏ nhất** trong các số đếm ở bước 2–3: đó là **common indent**.
5. Loại bỏ tối đa số ký tự common indent khỏi đầu mỗi dòng không trống, đồng thời bỏ whitespace ở cuối dòng.
6. Dòng chỉ chứa whitespace được chuyển thành dòng trống; cấu trúc số lượng dấu xuống dòng được giữ.

**Định nghĩa thực dụng:**

~~~text
commonIndent = min(
    số ký tự whitespace đầu dòng của mọi dòng không trống,
    số ký tự whitespace đầu dòng của dòng cuối (nếu dòng cuối trống)
)
~~~

Công thức này là **mô tả khái niệm**, không phải biểu thức Java chạy trực tiếp. Nếu dấu đóng nằm trên dòng riêng, bạn không thể bỏ qua độ thụt lề của dòng chứa dấu đóng: đó là nguyên nhân nhiều trường hợp “text block tự dư thêm khoảng trắng”.

### Ví dụ tính tay

Giả sử các dòng nguồn có số dấu cách ở đầu như sau:

| Thành phần của text block | Dấu cách đầu dòng trong mã nguồn |
|---|---:|
| `<main>` | 12 |
| `<p>Hello</p>` | 16 |
| `</main>` | 12 |
| Dấu đóng `"""` trên dòng riêng | 12 |

Mức chung là `min(12, 16, 12, 12) = 12`. Sau khi loại bỏ 12 dấu cách:

| Dòng kết quả | Số dấu cách còn lại |
|---|---:|
| `<main>` | 0 |
| `<p>Hello</p>` | 4 |
| `</main>` | 0 |

Khi giải thích một text block, hãy luôn ghi hai con số: **số ký tự đầu dòng trong mã nguồn** và **số ký tự còn lại trong String thực tế**. Đừng đánh giá chỉ bằng giao diện editor, vì tab và space có thể được hiển thị với độ rộng khác nhau.

## 3. Dấu phân định đóng quyết định lề trái như thế nào?

### 3.1. Dấu đóng thẳng hàng với dòng ít thụt lề nhất

~~~java
String text = """
        red
          blue
        """;
~~~

Mức thụt lề nhỏ nhất là độ thụt lề của `red` và dấu đóng. Kết quả tương đương:

~~~java
"red\n  blue\n"
~~~

`red` bắt đầu tại cột 0 của **chuỗi**, còn `blue` giữ 2 dấu cách. Đây là cách trình bày thường gặp nhất.

### 3.2. Dấu đóng dịch sang trái: giữ thêm khoảng trắng trong chuỗi

~~~java
String text = """
            red
              blue
        """;
~~~

Ở ví dụ này, dòng `red` thụt lề **nhiều hơn** dấu đóng 4 dấu cách, còn `blue` nhiều hơn 6 dấu cách. Vì dòng cuối chứa dấu đóng có mức thụt lề nhỏ nhất, Java chỉ loại bỏ số dấu cách tương ứng dấu đóng. Kết quả:

~~~java
"    red\n      blue\n"
~~~

**Tại sao hữu ích?** Bạn có thể bảo toàn một lượng thụt lề có chủ đích, ví dụ muốn chuỗi JSON/HTML khi in ra vẫn có khoảng trắng đầu dòng. Giữ dấu đóng ở mức thụt lề thấp hơn nội dung là cách xác định rõ lề trái cần giữ.

### 3.3. Dấu đóng ở đầu dòng nguồn: không loại bỏ thụt lề đầu dòng

Ví dụ sơ đồ sau dùng `·` để đại diện **một dấu cách**; các dấu chấm **không xuất hiện trong Java source thực**:

~~~text
String text = """
········red
··········blue
""";
~~~

Dấu đóng nằm ở cột 0 nên common indent bằng 0: các dấu cách đứng trước `red` và `blue` sẽ **được giữ lại**. Đây là một cách chủ động giữ toàn bộ thụt lề, nhưng thường làm mã nguồn kém gọn hơn; chỉ dùng khi yêu cầu chuỗi thực sự đòi hỏi đúng các dấu cách đó.

### 3.4. Dấu đóng thụt lề sâu hơn nội dung

~~~java
String text = """
        red
          blue
            """;
~~~

Dòng `red` có ít dấu cách hơn dòng chứa dấu đóng. Mức chung vẫn do `red` quyết định; kết quả vẫn là:

~~~java
"red\n  blue\n"
~~~

Dấu đóng không thể ép thuật toán xóa nhiều khoảng trắng hơn mức thụt lề nhỏ nhất của các dòng nội dung không trống.

### 3.5. Dấu đóng nằm ngay sau nội dung cuối

~~~java
String text = """
        red
          blue""";
~~~

Kết quả tương đương:

~~~java
"red\n  blue"
~~~

Ở trường hợp này **không có ký tự `\n` cuối chuỗi** vì giữa `blue` và dấu đóng không có xuống dòng. Không còn dòng riêng chứa dấu đóng để kéo mức chung xuống thấp; mức tối thiểu được xác định từ các dòng nội dung không trống. Nếu muốn giữ lề trái mà bỏ ký tự xuống dòng cuối, có thể dùng thiết kế chuỗi khác hoặc cân nhắc `String.indent(...)`/các thao tác chuỗi rõ ràng thay vì suy đoán tác động của dấu đóng.

**Ghi nhớ:** Thay đổi vị trí của dấu `"""` đóng là thay đổi **dữ liệu chuỗi**, không chỉ là định dạng file Java.

## 4. Dòng trống có ảnh hưởng thế nào?

Một dòng trống ở **giữa** text block không nên được coi như dòng nội dung có độ thụt lề 0 rồi suy ra common indent bằng 0. Thuật toán loại bỏ incidental whitespace **bỏ qua các dòng trống thông thường khi chọn mức thụt lề tối thiểu**; các dòng chỉ chứa whitespace trở thành dòng trống trong kết quả.

Ví dụ:

~~~java
String text = """
        red

          blue
        """;
~~~

Kết quả tương đương:

~~~java
"red\n\n  blue\n"
~~~

Lần lượt là dòng `red`, một dòng trống, dòng `blue` thụt lề 2 dấu cách, rồi ký tự xuống dòng cuối. Dòng trống ở giữa **không làm mất khả năng khử common indent**.

Nếu giữa nội dung có dòng chỉ toàn dấu cách/tab, dòng đó cũng được chuẩn hóa thành dòng trống khi loại incidental whitespace. Tuy nhiên, **dòng cuối riêng dành cho dấu đóng** được xét khi tính mức thụt lề chung ngay cả khi nó chỉ gồm whitespace; đây là trường hợp đặc biệt cần phân biệt.

### Tự tính bằng một bảng

| Dòng | Số dấu cách đầu dòng | Có tham gia tìm min? |
|---|---:|---|
| Dòng 1 chứa `red` | 8 | Có |
| Dòng 2 rỗng ở giữa | 0 | Không |
| Dòng 3 chứa `blue` | 10 | Có |
| Dòng cuối trước `"""` | 8 | Có |
| **Common indent** | **8** | Giá trị nhỏ nhất trong các dòng được xét |

Sau khử lề, `red` có 0 dấu cách trước nội dung, `blue` còn 2 dấu cách, dòng trống vẫn trống.

## 5. Khoảng trắng cuối dòng và thứ tự xử lý escape

Dấu cách hoặc tab nằm **sau nội dung của một dòng** thường bị coi là *incidental trailing whitespace* và được xóa. Đây là chủ đích: nhiều trình biên tập tự xóa dấu cách cuối dòng, và text block không nên âm thầm phụ thuộc vào chúng.

Nếu dữ liệu cần **dấu cách cuối dòng thực sự**, hãy dùng escape sau khi thuật toán khử khoảng trắng đã chạy:

~~~java
String text = """
        red\s
        blue\040
        """;
~~~

- `\s` là escape đại diện dấu cách.
- `\040` là escape bát phân tương ứng với dấu cách.
- Hai escape này **được diễn giải sau** bước loại bỏ incidental whitespace, nên dấu cách được tạo ra từ escape không bị xóa ngay trong bước đó.

Kết quả tương đương:

~~~java
"red \nblue \n"
~~~

Chuỗi trên có **một dấu cách trước mỗi `\n`**. Nếu chỉ viết dấu cách vật lý cuối dòng trong text block nguồn, chúng thường sẽ bị xóa.

### Ba pha theo đúng thứ tự

~~~text
(1) Normalize line endings về LF
         ↓
(2) strip incidental indentation và trailing whitespace
         ↓
(3) Diễn giải escape sequences (\s, \040, \n, \t, ...)
         ↓
    Giá trị String cuối cùng
~~~

Tránh nhầm `\s` với `\u0020`. Unicode escape được xử lý rất sớm trong quá trình đọc mã nguồn; `\u0020` có thể trở thành một dấu cách vật lý trước khi bước loại bỏ incidental whitespace chạy, nên nó **không** phải giải pháp tương đương `\s` để bảo toàn khoảng trắng cuối dòng.

Với việc nối dòng bằng một backslash ngay trước line terminator, escape tiếp dòng được xử lý ở bước cuối để bỏ một ký tự xuống dòng có chủ đích. Đây là cơ chế khác với tính thụt lề; không dùng nó như mẹo tính common indent.

## 6. Ví dụ Java 17+ chạy được: nhìn thấy từng dấu cách còn lại

Để tránh việc giao diện terminal tự che khoảng trắng và ký tự xuống dòng, chương trình dưới đây hiển thị:

- Mỗi **space** thành ký hiệu `·`.
- Mỗi **line feed** thành hai ký tự hiển thị `\n`.
- Tab không được dùng trong các literal mẫu, để kết quả đếm ổn định và dễ kiểm tra.

Tạo file **`TextBlockWhitespaceDemo.java`**:

~~~java
public class TextBlockWhitespaceDemo {

    private static String visible(String value) {
        return value.replace(" ", "·")
                .replace("\n", "\\n");
    }

    public static void main(String[] args) {
        String aligned = """
                <main>
                    <p>Hello</p>
                </main>
                """;

        String preserved = """
                    red
                      blue
                """;

        String inlineClose = """
                red
                  blue""";

        String withBlank = """
                red

                  blue
                """;

        String trailing = """
                red\s
                blue\040
                """;

        System.out.println("aligned=" + visible(aligned));
        System.out.println("preserved=" + visible(preserved));
        System.out.println("inline=" + visible(inlineClose));
        System.out.println("blank=" + visible(withBlank));
        System.out.println("trailing=" + visible(trailing));

        String expected = "<main>\n    <p>Hello</p>\n</main>\n";
        System.out.println("matches=" + aligned.equals(expected));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 TextBlockWhitespaceDemo.java
java TextBlockWhitespaceDemo
~~~

**Standard output chính xác:** các chuỗi `\n` bên dưới là **hai ký tự được in ra**, không phải ký tự xuống dòng thật.

~~~text
aligned=<main>\n····<p>Hello</p>\n</main>\n
preserved=····red\n······blue\n
inline=red\n··blue
blank=red\n\n··blue\n
trailing=red·\nblue·\n
matches=true
~~~

### Cách kiểm chứng

1. **`aligned`:** ba dòng không trống và dòng chứa dấu đóng có mức indent thấp nhất bằng nhau; dòng `<p>` có thêm 4 dấu cách tương đối. Giá trị kết thúc bằng LF vì dấu đóng nằm trên dòng riêng.
2. **`preserved`:** hai dòng nội dung đứng **xa hơn** dấu đóng 4 và 6 dấu cách; số dấu cách đó còn lại trong kết quả.
3. **`inlineClose`:** dấu đóng ngay sau chữ `blue`; do đó chuỗi không có `\n` cuối. Dòng `blue` vẫn thụt lề hơn `red` 2 dấu cách.
4. **`withBlank`:** dòng trống giữa `red` và `blue` không tạo mức indent 0 cho phép tính min. Dòng trống vẫn được thể hiện bằng hai `\n` liền nhau.
5. **`trailing`:** sau khi khử khoảng trắng vật lý, `\s` và `\040` tạo ra một dấu cách cuối mỗi dòng; hàm `visible` hiển thị chúng bằng `·`.
6. **`matches=true`:** so sánh trực tiếp với chuỗi thường có `\n` xác nhận chính xác giá trị của text block `aligned`.

Dùng hàm `visible` khi viết unit test để hiểu chuỗi thực tế, thay vì chỉ in String ra console rồi đoán khoảng trắng bằng mắt.

## 7. Space khác tab và cạm bẫy thụt lề không đồng nhất

Một tab (`\t` khi biểu diễn bằng escape) có thể trông như 2, 4 hoặc 8 cột trong editor, tùy cấu hình. Nhưng thuật toán xác định incidental whitespace xử lý **mỗi ký tự whitespace ở đầu dòng như một đơn vị**; một tab không được quy đổi thành “4 dấu cách” hay “8 dấu cách” dựa trên độ rộng hiển thị của editor.

Ví dụ minh họa, `·` là space và `⇥` là tab, **không phải mã Java thật**:

~~~text
········alpha       (8 space đầu dòng)
⇥⇥⇥⇥beta          (4 tab đầu dòng)
········gamma       (8 space đầu dòng)
~~~

Nếu các dòng này cùng nằm trong text block và không có dòng dấu đóng với mức indent thấp hơn, giá trị nhỏ nhất theo **số ký tự** có thể là `4` từ dòng chứa 4 tab. Khi xóa 4 ký tự đầu mỗi dòng, dòng dùng space vẫn còn 4 space, còn dòng tab không còn tab nào. Kết quả nhìn thấy có thể bị lệch bất ngờ.

Để tránh nhầm lẫn:

1. Dùng một quy ước nhất quán cho việc thụt lề trong text block, ưu tiên **space** nếu đội ngũ cần output có bố cục dự đoán được.
2. Không tính common indent bằng **độ rộng cột trực quan**.
3. Bật cảnh báo compiler khi hữu ích:

~~~bash
javac --release 17 -Xlint:text-blocks TextBlockWhitespaceDemo.java
~~~

Lựa chọn `-Xlint:text-blocks` giúp phát hiện một số vấn đề như thụt lề không nhất quán giữa whitespace characters hoặc trailing whitespace vật lý có nguy cơ bị loại. Không phải mọi cách căn lề khó hiểu đều sinh cảnh báo; unit test so sánh chuỗi thực tế vẫn hữu ích.

## 8. Khi nào nên dùng String.stripIndent() và String.indent()?

- **Khử lề khi biên dịch:** text block xử lý incidental whitespace như một phần ngữ nghĩa literal, **không cần** gọi `stripIndent()` thủ công.
- **Khử lề ở runtime:** `String.stripIndent()` là phương thức Java dùng để xử lý văn bản đã có dạng String (từ file, user input, nguồn động, v.v.). Nó có thể có hành vi khác tùy việc chuỗi **đã** chứa line terminator cuối hay chưa, nên không nên mặc định “gọi thêm một lần luôn giống compiler”.
- **Thêm hoặc điều chỉnh lề:** `String.indent(int)` có thể được dùng khi ứng dụng muốn thao tác rõ ràng với mức indent của một String. Ví dụ cấu hình thụt lề ở runtime thay vì cố điều khiển bằng vị trí dấu đóng trong mã nguồn.

Ví dụ:

~~~java
String text = """
        red
          blue
        """;
String shifted = text.indent(2);
~~~

Đây là đoạn minh họa trong phương thức hoặc class. `text` đã được compiler khử incidental whitespace; `indent(2)` thêm 2 dấu cách đầu mỗi dòng trong String kết quả. Chỉ dùng `indent` nếu lề thêm vào là **một phần dữ liệu mong muốn**, không dùng nó để che giấu hiểu nhầm về common indent.

### Có nên viết mọi chuỗi nhiều dòng thành text block?

Không nhất thiết. Text block rất phù hợp khi cấu trúc nhiều dòng và thụt lề tương đối là quan trọng. Chuỗi một dòng, dữ liệu nhỏ hoặc nội dung cần kiểm soát chính xác từng ký tự qua escape đôi khi dễ đọc hơn dưới dạng string literal thông thường. Điều quan trọng là người bảo trì hiểu **giá trị String cuối**, không chỉ nhìn một đoạn Java source đẹp mắt.

## 9. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| Tính lề chung từ dòng ngắn nhất theo số ký tự nội dung | Đếm sai; thuật toán xét **whitespace đầu dòng**, không xét độ dài chữ | Đếm khoảng trắng/tab ở đầu dòng |
| Bỏ qua mức indent của dòng chứa dấu đóng ở dòng riêng | Có thể khử quá nhiều whitespace và đoán sai output | Tính cả dòng cuối trước dấu `"""` đóng |
| Cho rằng dòng trống giữa text block có indent 0, nên không khử lề | Kết quả dự đoán bị lệch | Dòng trống thông thường không tham gia tìm min |
| Dịch dấu đóng sang trái chỉ để định dạng Java đẹp hơn | Có thể tăng số space giữ lại trong String | Coi vị trí dấu đóng là quyết định về nội dung |
| Dấu đóng ngay sau nội dung nhưng vẫn giả định có LF cuối | Sai dấu xuống dòng cuối chuỗi | Phân biệt dấu đóng ở dòng riêng và dấu đóng inline |
| Giữ space vật lý cuối dòng để tạo output | Dấu space đó thường bị xóa | Dùng `\s`, `\040` hoặc giải pháp rõ ràng tương đương |
| Dùng `\u0020` để cố giữ space cuối dòng | Unicode escape được xử lý sớm, space vẫn có thể bị xóa | Dùng escape thông thường được diễn giải sau khử lề |
| Trộn tab và space rồi đếm bằng cột hiển thị | Compiler đếm ký tự whitespace, không tính tab stop | Thống nhất cách thụt lề hoặc kiểm thử cụ thể |
| Gọi `stripIndent()` vô điều kiện lên text block đã xử lý | Có thể tạo thay đổi không mong muốn với văn bản khác | Chỉ áp dụng khi thật sự muốn biến đổi String runtime |
| Dùng preview flags lịch sử của Java 14 để viết code mới | Không cần thiết và dễ lệ thuộc phiên bản | Dùng Java 17+ với text block đã chính thức từ Java 15 |

## 10. Quy trình kiểm tra text block trong code review

Với một text block cần khớp đầu ra chính xác:

1. **Xác định cú pháp:** dấu mở `"""` có xuống dòng ngay sau đó không? Dấu đóng ở dòng riêng hay inline?
2. **Đếm indent thực:** đọc số ký tự whitespace đầu dòng, không đếm độ rộng mà editor hiển thị.
3. **Tìm common indent:** dùng min của các dòng không trống và dòng cuối (khi áp dụng).
4. **Tính phần giữ lại:** lấy indent từng dòng trừ common indent; những dòng nội dung ít thụt nhất sẽ bắt đầu ở cột 0 của String.
5. **Kiểm tra dòng trống:** bảo đảm số dòng rỗng và các LF cần thiết không bị nhầm.
6. **Kiểm tra cuối dòng:** xem dấu cách/tab vật lý có bị khử và escape nào tạo whitespace thật sau đó.
7. **Xác nhận thứ tự biến đổi:** line ending normalization → strip incidental whitespace → translate escapes.
8. **So sánh chuỗi:** dùng `equals` hoặc unit test thể hiện rõ whitespace, nhất là với JSON, HTML, SQL, Markdown hoặc thông điệp dùng làm snapshot.
9. **Kiểm tra editor/formatter:** việc di chuyển riêng dấu đóng, thay tab bằng space hoặc căn lại từng dòng có thể đổi giá trị chuỗi.
10. **Chốt chính sách định dạng:** code formatter nên giữ tương quan giữa nội dung và dấu đóng nếu cần bảo toàn dữ liệu String.

### Checklist định lượng nhanh

| Câu hỏi | Điều cần trả lời |
|---|---|
| Dòng không trống có indent thấp nhất bao nhiêu? | Ví dụ 8 ký tự |
| Dòng cuối chứa dấu đóng có bao nhiêu ký tự indent? | Ví dụ 4 ký tự |
| **Common indent** là bao nhiêu? | `min(8, 4) = 4` |
| Dòng nội dung indent 8 còn bao nhiêu? | `8 - 4 = 4` |
| Dòng nội dung indent 12 còn bao nhiêu? | `12 - 4 = 8` |
| Có LF cuối chuỗi không? | Có nếu dấu đóng nằm riêng sau line terminator |
| Có trailing whitespace cần giữ không? | Nếu có, dùng escape/phương án phù hợp |

## 11. Tự kiểm tra

**Câu 1.** Một text block có các dòng nội dung lần lượt thụt lề 10, 14 và 10 space. Dòng chứa dấu đóng ở dòng riêng thụt lề 8 space. Mức chung là bao nhiêu?

**Đáp án:** `8` space. Các dòng nội dung sau xử lý còn lần lượt 2, 6 và 2 space.

**Câu 2.** Hai dòng nội dung có indent 6 và 10 space; dấu đóng ở dòng riêng thụt 12 space. Mức chung là bao nhiêu?

**Đáp án:** `6` space vì dòng nội dung ít thụt hơn dấu đóng. Hai dòng sau xử lý còn 0 và 4 space.

**Câu 3.** Một dòng rỗng nằm giữa hai dòng nội dung có indent 8 và 12 space. Dấu đóng thụt 8. Dòng rỗng có làm common indent thành 0 không?

**Đáp án:** Không. Dòng rỗng không tham gia phép chọn min thông thường; mức chung là 8. Dòng thứ hai còn 4 space.

**Câu 4.** Viết `String s = """` rồi có xuống dòng và dòng nội dung cuối là `blue""";`, có tự thêm LF cuối chuỗi không?

**Đáp án:** Không. Vì dấu đóng nằm **ngay sau `blue`** nên trước nó không có ký tự xuống dòng cuối.

**Câu 5.** Một dòng trong text block chứa ký tự space vật lý sau chữ `red`, rồi xuống dòng. Space này có được bảo đảm giữ lại không?

**Đáp án:** Không. Incidental trailing whitespace thường bị bỏ. Nếu cần space cuối dòng thật sự, dùng `\s` hoặc `\040` trong nguồn text block.

**Câu 6.** Một tab ở đầu dòng được tính bằng mấy đơn vị whitespace trong phép tính min, nếu editor hiển thị tab rộng 8 cột?

**Đáp án:** **Một ký tự whitespace**, không phải 8. Kết quả hiển thị có thể khác nhau giữa các editor, nhưng quy tắc compiler không dựa vào tab stop.

**Câu 7.** Tại sao `\s` bảo toàn được space cuối dòng nhưng `\u0020` không đáng tin cho mục đích này?

**Đáp án:** `\s` là escape được diễn giải **sau** bước khử incidental whitespace; Unicode escape như `\u0020` được xử lý sớm thành dấu cách nguồn và có thể bị xóa trong bước khử lề.

**Câu 8.** Một đoạn text block Java đã được căn lại toàn bộ source, bao gồm cả nội dung và dấu đóng, cùng tăng 4 dấu cách. Giá trị String có nhất thiết thay đổi không?

**Đáp án:** Không nhất thiết. Nếu các mức indent liên quan cùng tăng đều và ký tự nội dung/line endings không đổi, common indent thường tăng tương ứng nên thụt lề tương đối được giữ nguyên. Nhưng nếu **chỉ** nội dung hoặc **chỉ** dấu đóng dịch chuyển, kết quả có thể khác; cần tính lại để khẳng định.

## 12. Tài liệu tham khảo

- [Java Language Specification 17, `3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): ba pha xử lý nội dung, thứ tự chuẩn hóa dòng, khử incidental whitespace và giải mã escape.
- [Oracle Java 17 — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): vị trí dấu đóng, xử lý thụt lề, dòng cuối, trailing whitespace và escape.
- [Java SE 17 API — String.stripIndent()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#stripIndent()): quy tắc đếm min indentation, dòng trống và khử whitespace.
- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): tính năng text block chính thức từ Java 15.

**Ghi nhớ:** **Độ thụt lề chung bị loại bỏ bằng mức nhỏ nhất của các dòng nội dung không trống và dòng cuối chứa dấu đóng khi nó đứng riêng.** Dấu đóng là một phần ảnh hưởng đến cách tính lề; dòng trống thông thường không kéo mức chung xuống 0; trailing whitespace vật lý thường bị xóa; escape được xử lý sau cùng. Khi cần kết quả chính xác, hãy tính bằng số ký tự và kiểm chứng String thực tế.
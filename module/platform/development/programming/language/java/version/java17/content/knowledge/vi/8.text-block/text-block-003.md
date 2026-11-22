# Loại bỏ thụt lề ngẫu nhiên và vị trí dấu đóng trong Java 17 Text Block

> **Chủ đề:** Java 17  
> **Chương:** Text block  
> **Trọng tâm:** Cách trình biên dịch bỏ khoảng trắng thụt lề không chủ ý (*incidental indentation*), cách dấu đóng `"""` quyết định lề chung và ký tự xuống dòng cuối, cùng các kỹ thuật giữ lại khoảng trắng có chủ đích.

## 1. Vì sao Java cần tự loại bỏ thụt lề của text block?

Trước khi có **text block**, một chuỗi HTML nhiều dòng thường phải ghép bằng các literal có dấu `\n` và dấu `+`:

```java
String html = "<main>\n" +
              "    <h1>Java 17</h1>\n" +
              "    <p>Xin chào!</p>\n" +
              "</main>\n";
```

Với text block, từ Java 15 trở đi (đã là tính năng chính thức), chúng ta có thể viết gần giống nội dung cần biểu diễn:

```java
String html = """
        <main>
            <h1>Java 17</h1>
            <p>Xin chào!</p>
        </main>
        """;
```

Trong file Java, các dòng nội dung được đẩy vào bên phải để căn theo mức thụt lề của mã nguồn. Nhưng thông thường chúng ta **không muốn** tám dấu cách ở đầu mỗi dòng xuất hiện trong chuỗi thực tế. Java tự động loại bỏ phần thụt lề được xem là *ngẫu nhiên*: khoảng trắng chỉ phục vụ việc trình bày mã nguồn.

Ở ví dụ trên, giá trị `html` tương đương:

```java
"<main>\n" +
"    <h1>Java 17</h1>\n" +
"    <p>Xin chào!</p>\n" +
"</main>\n"
```

Các dấu cách trước `<h1>` và `<p>` vẫn được giữ vì chúng biểu diễn **cấu trúc tương đối** của HTML. Mức căn lề chung của mã nguồn được xóa đi.

**Điểm mấu chốt:** Đừng suy đoán giá trị text block chỉ dựa vào vị trí dấu mở `"""`. **Dấu đóng `"""`, lề của các dòng nội dung và việc dòng cuối có xuống dòng hay không** đều ảnh hưởng đến kết quả.

## 2. Cú pháp text block và hai vị trí có thể đặt dấu đóng

Text block có kiểu `String`, bắt đầu bằng ba dấu nháy kép `"""`, tiếp theo là khoảng trắng tùy chọn rồi **bắt buộc có dấu xuống dòng** trước nội dung.

### 2.1. Dấu đóng trên một dòng riêng

```java
String message = """
        Xin chào
        Java 17
        """;
```

Đây là cách trình bày thông dụng. Giá trị tương đương:

```java
String message = "Xin chào\nJava 17\n";
```

Dấu xuống dòng **trước dấu đóng** là một phần của nội dung, vì thế chuỗi kết thúc bằng `\n`.

### 2.2. Dấu đóng ngay sau ký tự cuối cùng

```java
String message = """
        Xin chào
        Java 17""";
```

Giá trị tương đương:

```java
String message = "Xin chào\nJava 17";
```

Ở đây **không có `\n` cuối**, vì dấu đóng xuất hiện ngay sau chữ `17`. Việc đặt dấu đóng trên cùng dòng cuối cũng ảnh hưởng cách trình biên dịch xác định lề cần loại bỏ, được giải thích ở mục 5.

### 2.3. Những dạng không hợp lệ

```java
// Sai: thiếu xuống dòng sau dấu mở.
// String s = """Một dòng""";

// Sai: nội dung xuất hiện ngay trên dòng dấu mở.
// String s = """dòng đầu
//             dòng tiếp
//             """;
```

Nếu chỉ cần một chuỗi ngắn trên một dòng, dùng string literal thường:

```java
String name = "Java 17";
```

Text block không phải một kiểu dữ liệu khác với `String`. Nó chỉ là cú pháp biểu diễn chuỗi nhiều dòng thuận tiện, với quy tắc xử lý whitespace riêng.

## 3. Phân biệt incidental indentation và essential indentation

**Incidental indentation** là số ký tự trắng ở đầu các dòng được trình biên dịch xem như phần căn lề do vị trí của mã nguồn, nên tự động loại bỏ.

**Essential indentation** là phần thụt lề còn lại sau khi trừ lề chung; nó biểu diễn cấu trúc dữ liệu như HTML, JSON, SQL hoặc đoạn văn có thụt đầu dòng.

Ví dụ:

```java
String html = """
        <section>
            <h2>Tiêu đề</h2>
            <p>Nội dung</p>
        </section>
        """;
```

Giả sử khoảng trắng ở đầu các dòng nội dung lần lượt là **8, 12, 12, 8** dấu cách, còn dòng chứa dấu đóng `"""` cũng có **8** dấu cách. Khi ấy mức lề chung bị loại bỏ là **8**:

| Dòng | Số dấu cách đầu dòng trong mã nguồn | Bị loại bỏ | Còn trong chuỗi |
|---|---:|---:|---:|
| `<section>` | 8 | 8 | 0 |
| `<h2>...` | 12 | 8 | 4 |
| `<p>...` | 12 | 8 | 4 |
| `</section>` | 8 | 8 | 0 |
| Dòng dấu đóng `"""` | 8 | Tham gia xác định lề | Không trở thành nội dung có thể nhìn thấy |

Kết quả có dạng:

```html
<section>
    <h2>Tiêu đề</h2>
    <p>Nội dung</p>
</section>
```

Kết quả này vẫn **có `\n` ở cuối** vì dấu đóng nằm trên một dòng riêng.

### Quan sát lề bằng ký hiệu hiển thị

Khi cần hình dung những dấu cách vốn không nhìn thấy, ta dùng ký hiệu **`·` = một dấu cách** trong phần minh họa dưới đây. Đây là ký hiệu để giải thích, **không phải nội dung để sao chép vào Java**.

```text
Trong mã nguồn:
········<section>
············<h2>Tiêu đề</h2>
········</section>
········"""              ← lề dấu đóng = 8

Sau khi xóa 8 ký tự trắng chung:
<section>
····<h2>Tiêu đề</h2>
</section>
```

Lề tương đối bốn dấu cách của `<h2>` là chủ đích, nên được giữ.

## 4. Java 17 tính phần thụt lề ngẫu nhiên như thế nào?

Trình biên dịch xử lý nội dung text block về bản chất theo ba giai đoạn, theo thứ tự:

1. **Chuẩn hóa dấu kết thúc dòng:** Các kiểu CR (`\r`), LF (`\n`) và CRLF (`\r\n`) trong *nội dung nguồn* được chuẩn hóa thành LF (`\n`).
2. **Loại bỏ whitespace ngẫu nhiên:** Tính lề chung theo các dòng quyết định, bỏ phần thụt lề chung và bỏ whitespace cuối mỗi dòng.
3. **Diễn giải các escape sequence:** Chẳng hạn `\s` trở thành một dấu cách, còn dấu `\` đặt ngay trước kết thúc dòng có thể nối hai dòng lại.

Thứ tự này rất quan trọng: một escape `\s` dùng để giữ khoảng trắng ở cuối dòng chỉ trở thành dấu cách **sau** bước xóa whitespace ngẫu nhiên.

### 4.1. Các bước xác định lề chung

Quy tắc xác định *incidental indentation* có thể hiểu như sau:

1. Chia nội dung thành các dòng theo LF.
2. Lấy **các dòng không trống** làm tập dòng quyết định. Dòng chỉ chứa khoảng trắng thông thường không quyết định lề.
3. Nếu **dòng cuối** (dòng trước dấu đóng, khi dấu đóng nằm riêng) là dòng trống, **vẫn đưa dòng cuối này vào tập quyết định**. Nhờ vậy vị trí thụt lề của dấu đóng ảnh hưởng đến lề chung.
4. Đếm số ký tự trắng liên tiếp ở đầu từng dòng quyết định và chọn **số nhỏ nhất**.
5. Xóa số ký tự trắng chung đó khỏi đầu các dòng không trống; thay các dòng trống bằng dòng rỗng, đồng thời xóa whitespace cuối dòng.

**Lưu ý về dấu đóng:** Dấu đóng `"""` không tự trở thành ba ký tự trong `String`. Khi nằm riêng một dòng, **những dấu cách đứng trước nó** chính là nội dung của dòng cuối, và dòng này tham gia xác định lề. Khi dấu đóng nằm ngay sau nội dung, không có dòng chứa chỉ dấu cách trước dấu đóng để giới hạn lề theo cách đó.

### 4.2. Ví dụ: Dòng ít thụt lề nhất quyết định kết quả

```java
String value = """
        alpha
          beta
            gamma
        """;
```

Số dấu cách đầu dòng của ba dòng là `8, 10, 12`, còn lề dấu đóng là `8`. Mức xóa là `min(8, 10, 12, 8) = 8`.

Giá trị `value` chính xác là:

```java
"alpha\n  beta\n    gamma\n"
```

Kết quả nhìn thấy:

```text
alpha
  beta
    gamma
```

### 4.3. Dòng trống thông thường không làm lề chung về 0

```java
String note = """
        Dòng đầu

          Dòng sau
        """;
```

Dòng rỗng giữa hai dòng có chữ **không** buộc trình biên dịch giữ lề bằng không. Trong trường hợp này, kết quả tương đương:

```java
"Dòng đầu\n\n  Dòng sau\n"
```

Điểm đặc biệt là **dòng cuối ngay trước dấu đóng**, nếu chỉ có khoảng trắng, lại được tính để người lập trình có thể điều khiển phần lề cần giữ.

### 4.4. Dòng không thụt lề làm phần xóa chung bằng 0

```java
String value = """
        có thụt lề
không thụt lề
        """;
```

Vì dòng thứ hai bắt đầu ngay cột đầu tiên, số ký tự trắng đầu dòng nhỏ nhất là **0**. Java không thể loại bỏ tám dấu cách từ dòng thứ nhất mà vẫn giữ nguyên lề tương đối đã được mô tả. Kết quả vẫn có tám dấu cách trước dòng “có thụt lề”.

Tình huống này hay xảy ra nếu một dòng trong khối JSON hoặc SQL vô tình bị đưa sát mép trái.

## 5. Vị trí dấu đóng `"""` quyết định lượng thụt lề được giữ

Đây là điểm quan trọng nhất khi căn chỉnh text block trong Java 17. Hãy so sánh **cùng hai dòng nội dung** nhưng đặt dấu đóng ở vị trí khác nhau.

### 5.1. Dấu đóng ngang với các dòng nội dung ngoài cùng: xóa hết lề chung

```java
String a = """
        first
          second
        """;
```

Mức lề: `first = 8`, `second = 10`, dấu đóng `= 8`. Java xóa 8 ký tự trắng đầu dòng.

Giá trị:

```java
"first\n  second\n"
```

Đây là cách căn lề nên dùng cho phần lớn text block vì dễ đoán và giúp nội dung nằm tự nhiên trong mã nguồn.

### 5.2. Dấu đóng lùi sang trái: giữ lại một phần lề

```java
String b = """
        first
          second
    """;
```

Ở đây dấu đóng nằm sau **4** dấu cách, ít hơn lề **8** của dòng `first`. Trình biên dịch chọn mức xóa là **4**.

Giá trị:

```java
"    first\n      second\n"
```

Như vậy chỉ riêng việc chuyển dấu đóng sang trái đã giữ thêm **4 dấu cách đầu mỗi dòng nội dung**. Điều này hữu ích nếu bạn thật sự muốn các dòng trong kết quả có một lề cố định.

### 5.3. Dấu đóng ở cột đầu tiên: giữ toàn bộ lề nguồn

```java
String c = """
        first
          second
""";
```

Dấu đóng ở đầu dòng có mức thụt lề **0**, làm phần lề chung bằng **0**.

Giá trị:

```java
"        first\n          second\n"
```

Đây là cách **không xóa lề đầu dòng** khi text block có dòng cuối kết thúc bằng LF. Nên dùng có chủ đích vì dấu đóng lệch khỏi thân mã Java có thể làm khó đọc source.

### 5.4. Dấu đóng thụt sâu hơn nội dung không tự thêm khoảng trắng

```java
String d = """
        first
          second
            """;
```

Đếm: `first = 8`, `second = 10`, dấu đóng `= 12`. Giá trị nhỏ nhất **vẫn là 8** nên kết quả giống `a`:

```java
"first\n  second\n"
```

Dời dấu đóng **sang phải** không tự thêm lề vào nội dung. Mức xóa không thể lớn hơn lề của dòng nội dung ít thụt lề nhất.

### 5.5. Bảng tổng hợp bốn cách đặt dấu đóng

| Vị trí dấu đóng ở dòng riêng | Lề dòng `first` | Lề dấu đóng | Lề bị xóa | Lề còn lại trước `first` |
|---|---:|---:|---:|---:|
| Ngang với `first` | 8 | 8 | 8 | 0 |
| Lùi trái bốn dấu cách | 8 | 4 | 4 | 4 |
| Ở đầu dòng | 8 | 0 | 0 | 8 |
| Sang phải bốn dấu cách | 8 | 12 | 8 | 0 |

**Công thức tư duy:** Khi dấu đóng nằm riêng một dòng, lấy số ký tự trắng nhỏ nhất trong các dòng không trống **và dòng dấu đóng**, rồi xóa mức lề đó. Tránh chỉ nhìn lề của dấu mở.

## 6. Dấu đóng đặt ngay sau dòng cuối: thay đổi cả `\n` và cách xóa lề

Vị trí `"""` cùng dòng nội dung là trường hợp riêng cần chú ý.

### 6.1. Không có ký tự xuống dòng cuối

```java
String text = """
        one
          two""";
```

Giá trị:

```java
"one\n  two"
```

Không có `\n` sau `two`. Đồng thời, dòng kết thúc bằng `two"""` **không tạo ra dòng cuối trống chứa lề dấu đóng**.

Vì vậy mức xóa được xác định bởi các dòng nội dung (trong ví dụ là 8 ký tự trắng), không bởi vị trí của ba dấu nháy kép trên một dòng riêng.

### 6.2. Không thể dùng “dấu đóng lùi trái” để giữ lề nếu nó nằm ngay sau chữ

So sánh:

```java
String a = """
        red
        blue""";

String b = """
        red
        blue
    """;
```

Giá trị:

```java
// a: "red\nblue"
// b: "    red\n    blue\n"
```

`a` không có dòng trống cuối giúp định lề bằng 4; `b` có dòng dấu đóng thụt 4 dấu cách nên giữ được 4 dấu cách trước nội dung.

**Điểm thường nhầm:** Hai text block này khác nhau về **cả lề đầu dòng và xuống dòng cuối**. Không nên chuyển vị trí dấu đóng chỉ để “làm đẹp” nếu chuỗi được dùng để so sánh chính xác, ghi snapshot hoặc gửi giao thức cần đúng từng byte.

### 6.3. Cách vừa giữ lề mong muốn vừa bỏ xuống dòng cuối

Java 17 hỗ trợ escape **backslash ngay trước line terminator** để nối dòng:

```java
String text = """
            red
            blue\
        """;
```

Giải thích:

- Hai dòng nội dung có **12** dấu cách đầu dòng.
- Dấu đóng có **8** dấu cách đầu dòng.
- Trình biên dịch loại bỏ **8** dấu cách chung nên mỗi dòng nội dung giữ **4** dấu cách.
- Dấu `\` ngay trước xuống dòng sau `blue` loại bỏ dấu xuống dòng đó khỏi kết quả.

Giá trị:

```java
"    red\n    blue"
```

Cách này vừa giữ dấu đóng trên dòng riêng, vừa thể hiện lề có chủ đích, vừa tránh ký tự `\n` cuối. Nên dùng khi điều này thực sự quan trọng với dữ liệu.

**Không nhầm:** Dấu `\` trước xuống dòng là escape **line continuation**. Dấu `\n` là hai ký tự trong mã nguồn được diễn giải thành ký tự LF; hai cách viết khác nhau.

### 6.4. Dùng `String.indent` khi muốn thêm lề sau khi tạo chuỗi

```java
String content = """
        red
        green
        """;

String indented = content.indent(4);
```

`String.indent(4)` thêm bốn dấu cách vào **đầu từng dòng**. Nó phù hợp khi mức lề muốn thêm đến từ logic chương trình, thay vì căn lề của Java source.

**Lưu ý:** `String.indent(int)` chuẩn hóa dấu xuống dòng và tạo LF ở cuối các dòng của chuỗi kết quả, kể cả khi đầu vào không có LF cuối; đừng dùng nó để thay thế cách đặt dấu đóng nếu bạn cần tuyệt đối không có newline cuối.

## 7. Ví dụ Java 17 đầy đủ: Nhìn chính xác kết quả của nhiều vị trí dấu đóng

Để biết whitespace thực tế, không nên chỉ dùng `System.out.println(text)` rồi nhìn bằng mắt. Ví dụ sau thay dấu cách bằng `·`, tab bằng ký hiệu `⇥` và LF bằng `⏎` trước khi hiển thị.

Tạo file `TextBlockIndentDemo.java`:

```java
public class TextBlockIndentDemo {

    private static String visible(String text) {
        return text.replace(" ", "·")
                   .replace("\t", "⇥")
                   .replace("\n", "⏎\n");
    }

    private static void show(String label, String text) {
        System.out.println(label + " = [" + visible(text) + "]");
        System.out.println("  length = " + text.length()
                + ", endsWithLF = " + text.endsWith("\n"));
    }

    public static void main(String[] args) {
        String aligned = """
                first
                  second
                """;

        String movedLeft = """
                first
                  second
            """;

        String inlineClosing = """
                first
                  second""";

        String preservedNoFinalLF = """
                    first
                      second\
                """;

        show("aligned", aligned);
        show("movedLeft", movedLeft);
        show("inlineClosing", inlineClosing);
        show("preservedNoFinalLF", preservedNoFinalLF);
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 TextBlockIndentDemo.java
java TextBlockIndentDemo
```

Để tiện đọc, kết quả dự kiến được mô tả theo giá trị literal:

| Biến | Giá trị chuỗi chính xác | Kết thúc bằng `\n`? |
|---|---|---|
| `aligned` | `"first\n  second\n"` | Có |
| `movedLeft` | `"    first\n      second\n"` | Có |
| `inlineClosing` | `"first\n  second"` | Không |
| `preservedNoFinalLF` | `"    first\n      second"` | Không |

Điểm đáng xem là `aligned` và `movedLeft` chỉ khác **vị trí dấu đóng**; còn `inlineClosing` và `preservedNoFinalLF` đều không có LF cuối nhưng có **lề được giữ khác nhau**.

Chương trình cố ý dùng những số dấu cách căn lề lớn hơn ở trong thân `main`, nhưng kết quả vẫn tuân theo cách tính lề tương đối như các ví dụ ngắn hơn ở trên.

## 8. Khoảng trắng cuối dòng cũng bị loại bỏ

Bên cạnh thụt lề đầu dòng, Java 17 còn loại bỏ **whitespace ở cuối mỗi dòng** trong nội dung text block. Điều này giúp file Java không phụ thuộc vào việc editor tự xóa trailing spaces.

Ví dụ sau chỉ dùng để minh họa; ký hiệu `·` biểu diễn dấu cách **sau chữ**:

```text
Trong mã nguồn:
········alpha···
········beta·
········"""

Giá trị sau xử lý:
alpha\nbeta\n
```

Nếu ứng dụng cần giữ những dấu cách cuối dòng (chẳng hạn dữ liệu dạng fixed-width, thông điệp theo giao thức riêng), phải biểu diễn chúng **có chủ đích**.

### 8.1. Dùng escape `\s` để giữ một dấu cách

```java
String padded = """
        red  \s
        blue\s
        """;
```

Vì escape được diễn giải **sau** bước xóa trailing whitespace:

- Dòng `red  \s` giữ **ba** dấu cách sau chữ `red` (hai dấu cách có trong source, cộng một từ `\s`).
- Dòng `blue\s` giữ **một** dấu cách sau chữ `blue`.

Giá trị:

```java
"red   \nblue \n"
```

Đây là ví dụ cho thấy `\s` hoạt động như **hàng rào** giữ các dấu cách đứng trước nó ở cuối dòng.

### 8.2. Dùng octal escape `\040`

```java
String padded = """
        red\040\040
        blue\040
        """;
```

Escape `\040` tương ứng một dấu cách; nội dung kết quả là:

```java
"red  \nblue \n"
```

Trong mã Java mới, `\s` thường dễ đọc hơn khi mục đích chỉ là giữ dấu cách. Cả hai đều được hỗ trợ bởi Java 17.

### 8.3. Không thay `\s` bằng `\u0020`

`\u0020` là **Unicode escape**; Java xử lý Unicode escapes rất sớm khi đọc mã nguồn, trước khi phân tích text block và loại bỏ whitespace. Vì vậy, nó có thể trở thành dấu cách thật trong source và tiếp tục bị xóa ở cuối dòng.

Muốn giữ whitespace qua bước xử lý text block, dùng `\s` hoặc `\040` thay vì dựa vào `\u0020`.

### 8.4. Một dòng chỉ có khoảng trắng sẽ trở thành dòng trống

```java
String text = """
        first

        second
        """;
```

Giá trị tương đương:

```java
"first\n\nsecond\n"
```

Nếu dòng giữa có một số dấu cách vô hình nhưng không có ký tự nào khác, nó vẫn được xem là dòng trắng và phần whitespace đó bị xóa. Đừng dùng số dấu cách trên một dòng trống để kỳ vọng tạo một dòng “có padding” trong chuỗi.

## 9. Dấu tab, khoảng trắng và lint phát hiện sai lề

Đối với tính lề, Java đếm **số ký tự whitespace**, không giả định một tab bằng bốn hoặc tám dấu cách hiển thị.

Ví dụ, nếu một dòng có bốn dấu tab đầu dòng còn dòng khác có tám dấu cách đầu dòng, Java không coi hai lề này bằng nhau theo chiều rộng trên editor. Một tab được đếm là **một ký tự** khi áp dụng quy tắc loại bỏ lề.

Đó là lý do nên **dùng nhất quán spaces hoặc tabs** cho toàn bộ phần thụt lề của một text block. Pha trộn hai loại có thể khiến chuỗi đầu ra mất cân đối mà khó nhận thấy bằng mắt.

Java 17 có cảnh báo dành cho text blocks:

```bash
javac --release 17 -Xlint:text-blocks TextBlockIndentDemo.java
```

Tùy nội dung source, bộ kiểm tra có thể phát cảnh báo chẳng hạn:

- `inconsistent white space indentation` — trộn cách thụt lề khiến kết quả khó dự đoán.
- `trailing white space will be removed` — có dấu cách cuối dòng sắp bị loại bỏ.

Lệnh trên là công cụ hữu ích để **phát hiện vấn đề whitespace khi phát triển**, không làm thay đổi quy tắc giá trị chuỗi mà Java 17 sử dụng. Cảnh báo không nhất thiết xuất hiện nếu mã đã được căn chỉnh nhất quán.

## 10. Phân biệt ba vấn đề: Lề, newline cuối và newline trong chuỗi

Khi xử lý text block, ba mục tiêu khác nhau cần quyết định riêng.

| Mục tiêu | Cách điều khiển | Ví dụ |
|---|---|---|
| Xóa lề do định dạng source | Đặt dấu đóng ngang lề ngoài cùng của nội dung | `<xml>` ở cùng mức thụt lề với `"""` |
| Giữ thêm lề đầu từng dòng | Dời dấu đóng sang trái so với các dòng nội dung | Nội dung 12 spaces, dấu đóng 8 spaces → giữ 4 |
| Không có `\n` cuối | Đặt dấu đóng ngay sau ký tự cuối, hoặc dùng `\` trước xuống dòng cuối | `text"""` hoặc `text\` rồi dấu đóng ở dòng kế |
| Giữ dấu cách cuối dòng | Dùng `\s`/`\040` trong text block | `value\s` |
| Không có newline giữa hai dòng source | Dùng `\` ngay trước line terminator ở dòng cần nối | `Hello \` rồi `world` |
| Thêm hoặc bớt lề bằng phép biến đổi ở runtime | Dùng `String.indent(int)` với hiểu biết về LF cuối | `text.indent(4)` |

### 10.1. Dùng line continuation khi mã nguồn cần xuống dòng nhưng chuỗi thì không

```java
String longLine = """
        Đây là một câu dài cần chia\
         thành hai dòng trong source\
         nhưng khi chạy chỉ là một dòng.
        """;
```

Giá trị thu được không có LF tại hai vị trí dùng dấu `\` nối dòng. Tuy nhiên, **khoảng trắng thực tế** còn phụ thuộc vào phần trước và sau dấu nối. Nếu muốn có đúng một dấu cách giữa hai từ, nên đặt dấu cách ở vị trí được giữ bằng escape `\s` hoặc viết nội dung sao cho ý định rõ ràng.

Ví dụ chính xác hơn:

```java
String sentence = """
        Hello\s\
        world\
        """;
```

Giá trị:

```java
"Hello world"
```

`\s` thêm một dấu cách trước `world`, còn các line continuation loại bỏ LF ngay sau chúng. Khi dùng cú pháp này, chỉ nên đặt nó ở nơi thật sự cần một chuỗi dài hiển thị trên nhiều dòng source.

### 10.2. Dấu mở không tạo thêm một dòng rỗng đầu chuỗi

```java
String value = """
        one
        two
        """;
```

Mặc dù trong Java source dấu mở `"""` phải được theo sau bằng xuống dòng, **dấu xuống dòng bắt buộc sau dấu mở không trở thành ký tự `\n` đầu chuỗi**. Giá trị bắt đầu trực tiếp bằng chữ `o` của `one`.

Muốn chuỗi bắt đầu bằng một dòng rỗng, phải chủ động để thêm một dòng trống sau dấu mở:

```java
String value = """

        one
        """;
```

Giá trị tương đương:

```java
"\none\n"
```

## 11. Ví dụ thực tế: HTML, SQL và JSON

Text block đặc biệt hữu ích cho những cấu trúc cần giữ **thụt lề tương đối**.

### 11.1. HTML — giữ cấu trúc thẻ

```java
String html = """
        <article>
            <h1>Thông báo</h1>
            <p>Đã gửi thành công.</p>
        </article>
        """;
```

Kết quả giữ bốn dấu cách trước `<h1>` và `<p>`, nhưng không giữ phần căn lề chung của mã Java. Nếu nội dung được gửi theo giao thức hoặc snapshot phải giống từng byte, quyết định rõ có cần `\n` cuối hay không.

### 11.2. SQL — tránh khoảng trắng ngẫu nhiên trong query

```java
String sql = """
        SELECT id, name
        FROM customers
        WHERE active = ?
        ORDER BY name
        """;
```

Ở đây, lề chung bị xóa và mỗi dòng bắt đầu đúng vị trí. Text block giúp query dễ đọc, nhưng **không thay thế parameterized queries**: dữ liệu người dùng vẫn cần truyền bằng `PreparedStatement`/tham số của thư viện, không ghép trực tiếp vào chuỗi SQL.

### 11.3. JSON — không làm thay đổi cấu trúc qua lề source

```java
String json = """
        {
            "success": true,
            "data": {
                "id": 42
            }
        }
        """;
```

Các dấu nháy kép đơn lẻ trong JSON không phải escape. Phần lề bên ngoài mất đi, phần lề trong đối tượng được giữ. Nếu lưu snapshot hoặc so sánh chuỗi chính xác, vị trí dấu đóng vẫn có thể ảnh hưởng vì trailing newline hoặc lề được giữ lại.

### 11.4. Dữ liệu mà lề có ngữ nghĩa

Không phải định dạng nào cũng bỏ qua khoảng trắng. Ví dụ, một số dữ liệu fixed-width, ví dụ code mẫu hoặc nội dung Markdown có khối code phụ thuộc lề:

```java
String markdown = """
            - Mục chính
                - Mục con
        """;
```

Dấu đóng nằm sau tám dấu cách, trong khi dòng nội dung đầu tiên có mười hai dấu cách, nên giá trị giữ **bốn dấu cách** trước `- Mục chính` và **tám dấu cách** trước `- Mục con`. Đó là lựa chọn có chủ đích; nếu căn dấu đóng thẳng với nội dung, phần lề được giữ sẽ khác.

## 12. `String.stripIndent()` liên quan ra sao?

Java 17 cung cấp phương thức:

```java
String stripIndent()
```

trên `String`. Nó loại bỏ thụt lề ngẫu nhiên trong một **chuỗi đã tồn tại tại runtime**, dựa trên các dòng và khoảng trắng đầu/cuối dòng. Cách xử lý này rất gần với ý tưởng của compiler khi đọc text block.

Ví dụ độc lập với text block:

```java
String raw = "    alpha\n      beta";
String normalized = raw.stripIndent();

System.out.println(normalized.equals("alpha\n  beta")); // true
```

Tuy nhiên, cần phân biệt:

- **Text block:** Trình biên dịch xử lý lề **ngay trong quá trình tạo literal**, khi vị trí dòng dấu đóng vẫn có ảnh hưởng. Bản thân `String` nhận được đã là giá trị sau xử lý.
- **`stripIndent()`:** Xử lý một `String` runtime; nó không thể nhìn thấy vị trí dấu `"""` trong Java source nếu thông tin đó đã bị loại bỏ.

**Không nên tự động gọi `.stripIndent()` trên mọi text block.** Một text block đã được xử lý lề khi biên dịch; gọi lại có thể làm mất thêm thụt lề có chủ đích.

Chẳng hạn:

```java
String indented = """
            first
              second
        """;

// Giá trị indented có 4 dấu cách trước "first".
// Việc gọi stripIndent() lần nữa trên một String kết thúc bằng LF
// cần xem xét quy tắc dòng cuối của phương thức, không nên
// mặc định nó giống việc dời dấu đóng trong source.
```

Khi cần định dạng bổ sung ở runtime, chọn đúng thao tác: `stripIndent()` để chuẩn hóa lề trong một chuỗi nhiều dòng; `indent(n)` để thay đổi lề có chủ đích; hoặc thao tác trên từng dòng nếu cần giữ nguyên kết thúc dòng/whitespace chính xác.

## 13. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chuỗi mất phần thụt lề dự định | Dấu đóng căn cùng lề với các dòng nội dung, nên lề chung bị xóa | Dời dấu đóng sang trái hoặc thiết kế lề trong nội dung rõ ràng |
| Chuỗi xuất hiện thêm dấu cách ở đầu mọi dòng | Dấu đóng bị lùi trái so với nội dung, nên Java xóa ít dấu cách hơn | Đưa dấu đóng về đúng lề mong muốn |
| Chuỗi có `\n` cuối ngoài dự kiến | Dấu đóng đứng trên dòng riêng sau dòng nội dung | Đặt dấu đóng sau ký tự cuối hoặc dùng line continuation |
| Chuỗi mất `\n` cuối | Dấu đóng đặt sát nội dung dòng cuối | Đặt dấu đóng trên dòng riêng nếu cần LF |
| Dòng bất kỳ có lề lệch hẳn | Một dòng ít thụt lề hơn các dòng còn lại đã quyết định mức xóa | Kiểm tra lề các dòng có nội dung |
| Khoảng trắng ở cuối dòng bị mất | Java tự bỏ trailing whitespace | Dùng `\s` hoặc escape `\040` có chủ đích |
| Tab và spaces cho ra lề kỳ lạ | Java đếm ký tự whitespace, không tính độ rộng hiển thị | Chuẩn hóa cách thụt lề, bật `-Xlint:text-blocks` |
| Dòng trống có nhiều dấu cách vẫn thành dòng rỗng | Blank lines không giữ nội dung whitespace riêng | Không dùng spaces trần để tạo padding; biểu diễn rõ mục đích |
| Dùng `\u0020` nhưng vẫn mất dấu cách | Unicode escape xử lý sớm, trở thành whitespace trước bước strip | Dùng `\s`/`\040` |
| Chuỗi bị lệch khi chuyển code trong IDE | Reindent thay đổi riêng vị trí dấu đóng hoặc chỉ một vài dòng | Căn lại cả nội dung và dấu đóng; kiểm tra giá trị thực |
| SQL/JSON hiển thị đẹp nhưng so sánh chuỗi thất bại | Khác newline cuối hoặc lề giữ lại | So sánh giá trị đã chuẩn hóa hoặc điều chỉnh dấu đóng theo yêu cầu |
| Gọi `stripIndent()` để “sửa” tất cả | Text block đã tự xử lý lề, lần xử lý runtime có ngữ nghĩa riêng | Chỉ gọi khi có chủ đích và biết trạng thái chuỗi đầu vào |

## 14. Bài tập thực hành

### Bài 1 — Dự đoán lề bị xóa

Cho mã:

```java
String s = """
        A
            B
        C
    """;
```

Hỏi giá trị `s` có bao nhiêu dấu cách trước `A`, `B` và `C`? Có LF cuối không?

**Đáp án:** Dấu đóng ở mức 4 dấu cách, còn ba dòng lần lượt có 8, 12 và 8; Java xóa 4. Vậy `A` còn 4 dấu cách, `B` còn 8, `C` còn 4, và có LF cuối:

```java
"    A\n        B\n    C\n"
```

### Bài 2 — Dời dấu đóng không đổi nội dung chữ

Hãy dự đoán kết quả:

```java
String a = """
        x
        y
        """;

String b = """
        x
        y
""";
```

**Đáp án:**

```java
// a = "x\ny\n"
// b = "        x\n        y\n"
```

Chỉ vị trí `"""` trên dòng riêng thay đổi mà mức lề trong `String` đã thay đổi.

### Bài 3 — Bỏ newline cuối nhưng vẫn giữ lề bốn dấu cách

Hãy viết text block có giá trị chính xác:

```java
"    first\n    second"
```

Không dùng nối literal bằng `+`, không gọi `trim()`/`strip()` để chữa sau.

**Gợi ý đáp án:**

```java
String s = """
            first
            second\
        """;
```

Nội dung 12 dấu cách, dấu đóng 8 dấu cách, vì thế giữ 4; dấu `\` trước LF ở dòng `second` giúp không có newline cuối.

### Bài 4 — Giữ hai dấu cách cuối dòng

Cho chuỗi `"A  \nB\n"`, hãy biểu diễn bằng text block mà không phụ thuộc vào khoảng trắng vô hình cuối dòng trong editor.

**Gợi ý:**

```java
String s = """
        A \s
        B
        """;
```

Trước `\s` có một dấu cách viết rõ trong mã, escape đóng góp thêm một dấu cách, nên kết quả có đúng hai dấu cách sau `A`.

### Bài 5 — Phát hiện lỗi trộn tab và dấu cách

Nếu một dòng được thụt bằng bốn tab còn dòng khác bằng tám dấu cách, Java có tự xem chúng có cùng mức thụt lề vì editor hiển thị hai lề bằng nhau không?

**Đáp án:** Không. Một tab là một ký tự trắng, không phải luôn tương đương bốn hoặc tám dấu cách. Hãy thống nhất cách thụt lề của các dòng text block và dùng `javac -Xlint:text-blocks` khi cần phát hiện cách căn lề không nhất quán.

### Bài 6 — Chuỗi có LF đầu hay không?

Cho:

```java
String first = """
        Hello
        """;

String second = """

        Hello
        """;
```

**Đáp án:** `first` bằng `"Hello\n"`. `second` bằng `"\nHello\n"`. Dấu xuống dòng bắt buộc ngay sau delimiter mở không tạo LF đầu tiên; dòng trống được đặt **thêm** sau dấu mở mới tạo LF ở đầu.

## 15. Quy tắc thực hành nên áp dụng trong Java 17

1. **Mặc định đặt dấu đóng `"""` trên một dòng riêng, cùng mức lề với các dòng nội dung ngoài cùng** để xóa incidental indentation nhưng giữ cấu trúc tương đối.
2. Nếu chuỗi cần lề trái có chủ đích, **căn nội dung sâu hơn dấu đóng** theo số dấu cách muốn giữ; đừng thay đổi lề tùy tiện sau khi đã dùng chuỗi trong snapshot hoặc giao thức.
3. Quyết định rõ **có cần ký tự `\n` cuối** hay không. Khi cần giữ dấu đóng trên dòng riêng nhưng không muốn LF cuối, dùng escape `\` ở cuối dòng nội dung.
4. Đừng dựa vào dấu cách cuối dòng vô hình; dùng `\s` hoặc escape khác khi khoảng trắng ấy là một phần thực sự của dữ liệu.
5. Tránh trộn tab và dấu cách trong cùng text block. Có thể bật `-Xlint:text-blocks` để nhận cảnh báo liên quan whitespace.
6. Khi giá trị chuỗi cần chính xác tuyệt đối, hãy mô tả/kiểm tra theo **giá trị `String`** gồm dấu cách và LF, thay vì chỉ xem chuỗi được in ra trên terminal.
7. Text block là tính năng chính thức từ **Java 15** và dùng được ổn định trong **Java 17**; các ví dụ ở đây không yêu cầu preview hoặc cú pháp của Java mới hơn.

## 16. Tài liệu tra cứu chính thức

- [Oracle — Programmer's Guide to Text Blocks (Java 17)](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): cú pháp, incidental white space, vị trí dấu đóng, newline cuối, escape `\s` và `-Xlint:text-blocks`.
- [JEP 378 — Text Blocks](https://openjdk.org/jeps/378): thiết kế và thuật toán xử lý text block được hoàn thiện trong Java 15, tiếp tục áp dụng cho Java 17.
- [Java Language Specification 17 — `3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6): quy định cú pháp và quá trình xử lý nội dung text block.
- [Java Language Specification 17 — `3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.7): thứ tự diễn giải escape và các chuỗi đặc biệt.
- [Java SE 17 API — String.stripIndent() và String.indent()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): phương thức xử lý indentation trên chuỗi runtime.

**Ghi nhớ:** Trong Java 17, khoảng trắng thụt lề bị xóa theo **lề nhỏ nhất của những dòng quyết định**, trong đó dòng chứa dấu đóng `"""` cũng tham gia nếu dấu đóng đứng riêng. Dời dấu đóng có thể thay đổi số dấu cách đầu dòng được giữ; đưa dấu đóng sát ký tự cuối có thể loại bỏ LF cuối. Hiểu rõ ba điều này giúp text block vừa dễ đọc trong Java source vừa tạo ra chuỗi đúng với nội dung cần sử dụng.

# Giữ thụt lề tương đối của HTML, JSON hoặc mã nguồn bằng text block Java

> **Bối cảnh:** Java 15 chuẩn hóa **text block** (JEP 378). Tính năng này vẫn được hỗ trợ trong các phiên bản Java hiện đại, bao gồm Java 17+. Bài học tập trung vào cách giữ các khoảng trắng *có ý nghĩa* trong nội dung HTML, JSON và mã nguồn được nhúng vào `String`.

## 1. Vấn đề: thụt lề của mã Java và thụt lề của nội dung khác nhau

Khi nhúng HTML, JSON hoặc đoạn mã nguồn trong Java, thường tồn tại hai loại thụt lề:

1. **Thụt lề của file `.java`:** giúp lập trình viên đọc cấu trúc `class`, phương thức, khối `if` và vị trí biến.
2. **Thụt lề bên trong chuỗi:** thể hiện quan hệ cha–con của thẻ HTML, các thuộc tính JSON hay những khối lệnh được nhúng.

Ví dụ HTML có cấu trúc phân cấp:

~~~html
<section>
  <h2>Java 15</h2>
  <p>Hello</p>
</section>
~~~

Ta muốn giữ **hai dấu cách** trước `<h2>` và `<p>` so với `<section>`. Tuy nhiên, khi đặt HTML vào bên trong một phương thức Java, mọi dòng HTML có thể cần thêm tám hoặc nhiều dấu cách để dễ đọc trong file nguồn. Nếu tám dấu cách đó cũng đi vào chuỗi, kết quả in ra sẽ bị lệch lề một cách không cần thiết.

**Text block** giải quyết vấn đề bằng cách tự bỏ **incidental indentation** (thụt lề phụ thuộc vào vị trí của chuỗi trong file Java), nhưng vẫn giữ **relative indentation** (chênh lệch thụt lề giữa các dòng nội dung).

### Text block không phải cú pháp chỉ để trình bày

`"""` tạo ra một giá trị `String` thông thường. Nó không tự parse HTML, JSON hay Java; những định dạng đó vẫn chỉ là nội dung ký tự. Tính năng của Java 15 là **cách biểu diễn literal** và quy tắc chuyển đổi khoảng trắng của literal.

## 2. Cú pháp text block và giá trị thực nhận được

Cú pháp:

~~~java
String html = """
        <section>
          <h2>Java 15</h2>
        </section>
        """;
~~~

Đây là **đoạn mã nằm trong một phương thức**, chưa phải một chương trình Java độc lập.

Các quy tắc:

- Mở đầu bằng ba dấu nháy kép `"""` và bắt buộc có **xuống dòng** sau dấu mở; không được viết toàn bộ text block trên một dòng.
- Nội dung có thể chứa dấu nháy kép `"` thông thường (rất tiện cho thuộc tính HTML và JSON) mà không cần escape từng dấu.
- Dấu đóng `"""` có thể đặt trên dòng riêng hoặc sau ký tự cuối cùng của nội dung. Vị trí đó ảnh hưởng đến kết quả.
- Text block tạo ra `String`, không phải một kiểu dữ liệu mới.
- Compiler **chuẩn hóa dấu xuống dòng thành LF** (`\n`), loại bỏ khoảng trắng phụ và cuối cùng mới xử lý các escape sequence.

Với dấu đóng trên dòng riêng như trên, chuỗi nhận được là:

~~~text
<section>
  <h2>Java 15</h2>
</section>
~~~

Kết quả còn **một ký tự `\n` ở cuối chuỗi**. Code fence chỉ biểu diễn phần nhìn thấy được; có thể xác nhận bằng biểu thức sau:

~~~java
boolean exact = html.equals("<section>\n  <h2>Java 15</h2>\n</section>\n");
~~~

Giá trị `exact` là `true`.

Nếu đặt dấu đóng cùng dòng cuối:

~~~java
String withoutFinalNewline = """
        <section>
          <h2>Java 15</h2>
        </section>""";
~~~

thì giá trị sẽ kết thúc ngay sau `</section>`, **không có `\n` cuối cùng**. Đây là lựa chọn có chủ đích khi định dạng đầu ra yêu cầu chính xác.

## 3. Cơ chế loại bỏ thụt lề phụ: tại sao “tương đối” vẫn còn?

Xét chuỗi:

~~~java
String html = """
            <ul>
              <li>A</li>
              <li>B</li>
            </ul>
            """;
~~~

Ở ví dụ này, các dòng `<ul>` và `</ul>` có cùng lề nguồn. Hai dòng `<li>` được thụt vào **thêm hai dấu cách**.

Để nhìn rõ, ký hiệu **`·` = một dấu cách trong file nguồn**, chỉ dùng cho sơ đồ (không phải mã Java hợp lệ):

~~~text
············<ul>
············  <li>A</li>
············  <li>B</li>
············</ul>
············"""
~~~

**Kết quả của `String`:**

~~~html
<ul>
  <li>A</li>
  <li>B</li>
</ul>
~~~

Diễn giải:

1. Compiler chuẩn hóa line terminator.
2. Xác định mức lề chung cần loại bỏ từ các **dòng nội dung không trống** và vị trí dòng dấu đóng `"""` khi dấu đóng nằm trên dòng riêng. Dòng nội dung trống không được dùng để kéo mức lề chung về 0.
3. Loại bỏ số ký tự khoảng trắng đầu dòng tương ứng với lề chung; **phần thụt sâu hơn mức đó vẫn còn**.
4. Bỏ khoảng trắng cuối dòng không có ý nghĩa rồi xử lý escape sequence.

Trong sơ đồ, mức lề chung là **12 dấu cách**. Sau bước loại bỏ, dòng `<ul>` còn 0; mỗi dòng `<li>` còn 2; dòng `</ul>` còn 0.

Về mặt tư duy:

~~~text
Thụt lề còn lại = thụt lề của dòng nội dung - lề phụ được loại bỏ

<ul>       : 12 - 12 = 0
  <li>A>   : 14 - 12 = 2
  <li>B>   : 14 - 12 = 2
</ul>      : 12 - 12 = 0
~~~

Các số ở đây là **số dấu cách của ví dụ**, không phải “số cột hiển thị” nếu dùng tab. Thụt lề thực tế phụ thuộc vị trí các ký tự whitespace trong source.

**Ý nghĩa quan trọng:** khi di chuyển cả text block sâu hơn vào một khối `if` hay phương thức, nếu dịch các dòng nội dung **và dấu đóng** sang phải cùng một lượng, chuỗi kết quả thường không đổi. Đây chính là lợi ích của việc giữ *thụt lề tương đối*.

## 4. Thực hành với HTML

HTML thường có cấu trúc lồng nhau. Dùng text block giúp giữ quan hệ cha–con mà không phải ghép từng dòng bằng toán tử `+`.

~~~java
String html = """
        <main>
          <article>
            <h1>Giới thiệu</h1>
            <p>Text block trong Java</p>
          </article>
        </main>
        """;
~~~

Nội dung có cấu trúc:

~~~html
<main>
  <article>
    <h1>Giới thiệu</h1>
    <p>Text block trong Java</p>
  </article>
</main>
~~~

Phần `<main>` và `</main>` trở về cột đầu tiên; `<article>` còn 2 dấu cách, `<h1>` và `<p>` còn 4 dấu cách.

### Lưu ý về whitespace có ý nghĩa trong HTML

Không phải mọi khoảng trắng trong HTML đều chỉ để đẹp mắt. Bên trong một số phần tử, đặc biệt `<pre>`, thụt lề là **dữ liệu hiển thị**.

~~~java
String html = """
        <pre>
          line one
            line two
        </pre>
        """;
~~~

Sau khi bỏ lề phụ, khoảng trắng trước `line one` và `line two` **vẫn còn**. Trình duyệt xử lý khoảng trắng của phần tử `<pre>` khác với văn bản HTML thông thường; vì vậy cần kiểm tra chuỗi thực tế, không dựa duy nhất vào cách trình soạn thảo căn lề.

Text block cũng **không thực hiện HTML escaping**. Nếu đưa dữ liệu không tin cậy vào HTML động, hãy dùng cơ chế escape hoặc template engine thích hợp; text block chỉ giải quyết tính dễ đọc của literal và whitespace.

## 5. Thực hành với JSON

Dấu nháy kép bên trong JSON có thể được đặt trực tiếp trong text block, giúp mẫu JSON rõ ràng hơn.

~~~java
String json = """
        {
          "module": "Java 15",
          "enabled": true,
          "lesson": {
            "topic": "Text blocks",
            "level": 2
          }
        }
        """;
~~~

Giá trị chuỗi sau khi xử lý lề:

~~~json
{
  "module": "Java 15",
  "enabled": true,
  "lesson": {
    "topic": "Text blocks",
    "level": 2
  }
}
~~~

Với JSON, thụt lề thường nhằm tăng khả năng đọc; ý nghĩa dữ liệu JSON thông thường không phụ thuộc vào việc dùng 2 hay 4 dấu cách giữa các token. Tuy nhiên, nếu cần **so sánh chuỗi chính xác**, tạo snapshot, test output hoặc gửi dữ liệu theo một giao ước định dạng, whitespace có thể là một phần của hợp đồng kiểm thử.

### Phân biệt chuỗi Java và escape của JSON

Text block **không phải raw string**. Java vẫn xử lý escape sequence. Nếu muốn giá trị JSON thực sự chứa hai ký tự `\` và `n` trong nội dung của một JSON string, hãy viết **`\\n` trong mã nguồn Java**:

~~~java
String jsonWithEscapedNewline = """
        {"message": "dong 1\\ndong 2"}
        """;
~~~

Khi đưa cho JSON parser, phần `\\n` được Java chuyển thành hai ký tự `\` và `n`, sau đó JSON parser mới diễn giải thành newline **trong giá trị trường**. Ngược lại, viết `\n` trực tiếp trong Java text block sẽ tạo ký tự xuống dòng thật ở bên trong cặp nháy của JSON string và khiến JSON đó không hợp lệ theo cú pháp JSON.

Tương tự, nếu nội dung JSON có nhiều ký tự cần escape hoặc dữ liệu thay đổi tại runtime, hãy dùng một **JSON serializer** để tạo JSON đúng. Text block phù hợp để viết **mẫu JSON tĩnh**, không thay thế thư viện JSON.

## 6. Thực hành với đoạn mã nguồn Java

Khi đưa một đoạn mã nguồn Java vào chuỗi (làm ví dụ, test fixture hay tạo file mẫu), điều quan trọng là giữ dấu ngoặc và độ sâu thụt lề của các khối lồng nhau.

~~~java
String source = """
        class Greeter {
            void hello() {
                System.out.println("Hi");
            }
        }
        """;
~~~

Giá trị nhận được:

~~~java
class Greeter {
    void hello() {
        System.out.println("Hi");
    }
}
~~~

Hãy phân biệt **mã Java chứa text block** với **mã Java được lưu bên trong text block**. Compiler biên dịch nội dung ngoài như một biểu thức `String`; nó **không biên dịch đoạn `class Greeter` bên trong chuỗi**. Đoạn nguồn đó chỉ được xử lý như Java khi bạn chủ động lưu thành file, dùng compiler API, hoặc đưa cho một công cụ thích hợp.

Nếu nhúng một text block *bên trong một text block khác* (mã Java chứa dấu `"""`), cần xử lý dấu phân cách/escape cẩn thận để không vô tình kết thúc chuỗi ngoài.

## 7. Chương trình đầy đủ: kiểm tra HTML, JSON và Java source

Lưu đúng tên file **`RelativeIndentDemo.java`**:

~~~java
public class RelativeIndentDemo {
    public static void main(String[] args) {
        String html = """
                <section>
                  <h2>Java 15</h2>
                  <p>Hello</p>
                </section>
                """;

        String json = """
                {
                  "name": "Java",
                  "active": true
                }
                """;

        String javaSource = """
                class Greeter {
                    void hello() {
                        System.out.println("Hi");
                    }
                }
                """;

        System.out.print("HTML:\n" + html);
        System.out.print("JSON:\n" + json);
        System.out.print("JAVA:\n" + javaSource);

        System.out.println("CHECK HTML: "
                + html.contains("\n  <h2>"));
        System.out.println("CHECK JSON: "
                + json.contains("\n  \"name\""));
        System.out.println("CHECK JAVA: "
                + javaSource.contains("\n    void hello()"));
    }
}
~~~

Biên dịch/chạy với **JDK 17+**:

~~~bash
javac RelativeIndentDemo.java
java RelativeIndentDemo
~~~

**Stdout chính xác:**

~~~text
HTML:
<section>
  <h2>Java 15</h2>
  <p>Hello</p>
</section>
JSON:
{
  "name": "Java",
  "active": true
}
JAVA:
class Greeter {
    void hello() {
        System.out.println("Hi");
    }
}
CHECK HTML: true
CHECK JSON: true
CHECK JAVA: true
~~~

### Giải thích kết quả

- Dù cả ba literal nằm sâu bên trong `main`, không có khoảng trắng phụ của **file Java** trước các dòng gốc `<section>`, `{` và `class Greeter`.
- Các dòng con trong HTML và JSON vẫn thụt vào 2 dấu cách; các dòng con của mã Java vẫn được thụt vào 4 hoặc 8 dấu cách theo mức lồng.
- Dùng `System.out.print` vì mỗi text block ở đây **đã có `\n` cuối**. Nếu thay thành `println`, sẽ xuất hiện thêm một dòng trống sau từng khối.
- Các kiểm tra `contains` dùng chuỗi `\n` và số dấu cách cụ thể nên cho `true`; chúng xác nhận **giá trị thực**, không chỉ hình thức trong IDE.

Có thể kiểm tra khả năng biên dịch cho Java 15 trên một JDK hiện đại vẫn hỗ trợ mức release này:

~~~bash
javac --release 15 RelativeIndentDemo.java
~~~

Text block đã hoàn thiện trong Java 15, nên ví dụ không cần `--enable-preview`. Khi triển khai, nên sử dụng JDK đang được dự án hỗ trợ và cập nhật bảo mật; không cần giữ môi trường runtime Java 15 cũ chỉ để học cú pháp này.

## 8. Vị trí dấu đóng quyết định lề chung

Đây là điểm dễ gây lỗi nhất. Khi dấu đóng `"""` nằm trên **dòng riêng**, vị trí thụt lề của nó tham gia xác định phần lề phụ cần loại bỏ.

### Trường hợp A: dấu đóng cùng lề với dòng nội dung ngoài cùng

~~~java
String aligned = """
        A
          B
        """;
~~~

Giá trị đúng: `"A\n  B\n"` — không còn khoảng trắng trước `A`, nhưng vẫn còn hai dấu cách trước `B`.

### Trường hợp B: dấu đóng lệch sang trái để **chủ động giữ khoảng trắng đầu dòng**

~~~java
String preserved = """
        A
          B
    """;
~~~

Ở đây dấu đóng lệch trái **4 dấu cách** so với dòng `A`. Lề phụ bị loại ít hơn; giá trị là `"    A\n      B\n"`.

Vì vậy, **căn lề dấu đóng không chỉ là thẩm mỹ**. Nó có thể là một phần của giá trị literal.

Chương trình độc lập **`ClosingMarginDemo.java`** giúp đối chiếu:

~~~java
public class ClosingMarginDemo {
    public static void main(String[] args) {
        String aligned = """
                A
                  B
                """;

        String shiftedTogether = """
                  A
                    B
                  """;

        String intentionallyIndented = """
                A
                  B
            """;

        System.out.println(aligned.equals("A\n  B\n"));
        System.out.println(aligned.equals(shiftedTogether));
        System.out.println(
                intentionallyIndented.equals("    A\n      B\n"));
    }
}
~~~

Chạy:

~~~bash
javac ClosingMarginDemo.java
java ClosingMarginDemo
~~~

**Stdout chính xác:**

~~~text
true
true
true
~~~

Ba kết luận:

1. Dấu đóng thẳng với dòng `A` tạo lề tương đối mong đợi.
2. Dịch **cả nội dung và dấu đóng** sang phải cùng lượng không thay đổi chuỗi.
3. Cố ý đặt dấu đóng lệch trái có thể dùng để **giữ thêm lề** trong chuỗi.

### Nếu dấu đóng nằm cùng dòng cuối

~~~java
String singleLastLine = """
        A
          B""";
~~~

Trường hợp này **không có newline cuối** và không có một dòng dấu đóng riêng để dùng làm mốc lề. Nếu cần giữ lề đầu dòng một cách chủ động, hãy cân nhắc đặt dấu đóng trên dòng riêng hoặc dùng các thao tác trên `String` với phép kiểm tra giá trị rõ ràng.

## 9. Những khoảng trắng khác không được nhầm với thụt lề

### 9.1. Dòng trống và khoảng trắng cuối dòng

Trong text block, các khoảng trắng cuối dòng thông thường (trailing whitespace) được compiler loại bỏ. Nếu một giao thức hay tài liệu thực sự cần một dấu cách ở cuối dòng, có thể dùng **`\s`**:

~~~java
String oneTrailingSpace = """
        x\s
        """;
boolean correct = oneTrailingSpace.equals("x \n");
~~~

`correct` là `true`: trong literal có một dấu cách **sau** chữ `x` và **trước** `\n`. `\s` được xử lý sau bước loại bỏ incidental whitespace, nên giúp giữ dấu cách có chủ đích. Khi không cần trailing space, hãy bỏ nó đi để dữ liệu đơn giản hơn.

Dòng trống trong một mẫu HTML/JSON/source code cũng có thể là chủ ý trình bày. Hãy kiểm tra cả số lượng dòng trống và ký tự xuống dòng cuối chuỗi trong các bài test cần so sánh chính xác.

### 9.2. Xuống dòng và nối dòng

Dấu mở `"""` bắt buộc có một line terminator, nhưng line terminator này **không phải** một ký tự đầu tiên của giá trị. Nội dung bắt đầu ở dòng sau.

Muốn loại bỏ newline cuối: đặt dấu đóng sau ký tự nội dung cuối cùng, hoặc dùng cách tạo chuỗi khác phù hợp.

Text block cũng hỗ trợ ký hiệu `\` ở cuối một dòng nội dung để **nối dòng** (không đưa line terminator đó vào kết quả). Đây là một công cụ đặc biệt; nên dùng có chủ đích và kiểm tra chuỗi vì nó thay đổi whitespace thực, có thể làm hai token dính nhau.

### 9.3. Tab và dấu cách

Tab (`\t`) và space không giống nhau:

- Editor có thể hiển thị một tab rộng 2, 4 hoặc 8 cột; thuật toán xử lý whitespace của Java không suy ra độ rộng tab theo cài đặt IDE của người đọc.
- Không trộn tab và space một cách tùy tiện ở đầu các dòng HTML/JSON/source trong text block. Dạng hiển thị có thể đánh lừa người viết về mức thụt thực sự.
- Với ví dụ chia sẻ cho nhiều người, ưu tiên dùng **space thống nhất** (chẳng hạn 2 dấu cách cho HTML/JSON, 4 dấu cách cho mã Java).
- Nếu dữ liệu thực sự phải chứa tab, dùng escape `\t` có chủ đích và kiểm tra ký tự đầu ra.

### 9.4. Di chuyển hoặc định dạng lại source code

Việc format lại file Java thông thường an toàn **nếu** formatter giữ quan hệ giữa lề của nội dung và lề của dấu đóng. Nhưng nếu formatter chỉ dịch dấu đóng, hoặc chỉ dịch một dòng nội dung ra ngoài mép trái, chuỗi có thể thay đổi.

Điều này đặc biệt đáng chú ý khi HTML chứa `<pre>`, khi test so sánh snapshot, hoặc khi đoạn mã nguồn nhúng cần định dạng chính xác.

## 10. Các lỗi hay gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt dấu đóng `"""` quá xa bên trái so với nội dung mà không chủ ý | Chuỗi còn nhiều dấu cách đầu dòng | Căn dấu đóng theo lề của dòng ngoài cùng nếu muốn bỏ hết lề phụ |
| Một dòng không trống bị lệch trái so với các dòng còn lại | Mức lề chung giảm; các dòng khác giữ thêm whitespace | Tìm dòng có ít whitespace đầu nhất và chỉnh lại |
| Chỉ di chuyển nội dung, không di chuyển dấu đóng | Giá trị `String` có thể thay đổi | Khi chỉnh format, xem nội dung và dấu đóng như một khối |
| Dùng tab lẫn space | Khó suy ra số ký tự thụt lề thực | Dùng space nhất quán, hoặc test chính xác chuỗi |
| Nghĩ rằng dấu nháy kép bên trong JSON phải escape như string literal một dòng | Mã rối và khó đọc không cần thiết | Trong text block, nháy kép đơn thông thường có thể viết trực tiếp |
| Nghĩ text block là raw string, nên `\n` hoặc `\t` sẽ giữ nguyên dấu `\` | JSON/source nhúng có thể đổi nghĩa hoặc không hợp lệ | Escape dấu `\` khi cần ký tự backslash thật; ví dụ `\\n` cho JSON |
| Dùng `println` với text block đã có `\n` cuối | Thêm một dòng trống ngoài ý muốn | Dùng `print` hoặc kiểm soát newline cuối |
| Mong compiler tự hiểu/kiểm tra JSON, HTML hay Java bên trong literal | Nội dung có thể sai cú pháp của định dạng đích | Dùng parser, validator hoặc compiler phù hợp khi cần |
| Cho rằng text block tự động giải quyết escaping dữ liệu động | Dữ liệu chứa ký tự đặc biệt có thể phá định dạng | Dùng thư viện serializer, template engine hoặc escaping đúng ngữ cảnh |

## 11. Quy trình thực tế để giữ thụt lề tương đối

Khi viết hoặc review một literal nhiều dòng:

1. **Viết nội dung đích trước:** hình dung HTML, JSON hoặc mã Java phải trông như thế nào sau khi rời file `.java`.
2. **Chọn chuẩn thụt lề:** 2 dấu cách cho HTML/JSON, 4 dấu cách cho mã Java là những lựa chọn dễ đọc; có thể theo chuẩn của dự án.
3. **Đặt nội dung vào text block:** thụt toàn bộ nội dung theo vị trí biến trong Java, nhưng giữ chênh lệch 2/4 dấu cách giữa các dòng con.
4. **Căn dấu đóng theo lề gốc:** nếu muốn dòng root bắt đầu ở cột đầu tiên của chuỗi, đặt `"""` thẳng với dòng root. Muốn giữ thêm lề, dịch dấu đóng sang trái có chủ đích.
5. **Quyết định newline cuối:** dấu đóng ở dòng riêng thường cho newline cuối; dấu đóng cuối dòng nội dung thì không.
6. **Kiểm tra giá trị:** dùng `equals`, `startsWith`, `contains` hoặc test chuỗi đầy đủ; với JSON/HTML/source cần tính đúng cú pháp, đưa nội dung cho parser/validator tương ứng.
7. **Sau khi auto-format:** nếu chỉnh nhiều dòng, chạy lại test chuỗi tại các chỗ có hợp đồng whitespace quan trọng.

### Checklist khi review

- [ ] Thứ tự và mức thụt lề của các dòng con được giữ như trong nội dung mong đợi.
- [ ] Dòng root không có lề vô tình xuất hiện do vị trí `"""`.
- [ ] Dấu xuống dòng cuối và dòng trống đã được xác định.
- [ ] JSON/source có các dấu `\`, dấu nháy và escape sequence chính xác.
- [ ] Không dựa vào tab width của editor để đo “hai dấu cách”.
- [ ] Nếu cần whitespace chính xác (ví dụ snapshot/`<pre>`), đã có test so sánh giá trị chuỗi.

## 12. Bài tập áp dụng

**Bài 1 — HTML.** Dựng text block sao cho giá trị chứa:

~~~html
<div>
  <span>A</span>
  <span>B</span>
</div>
~~~

**Gợi ý:** hai dòng `<span>` thụt thêm 2 dấu cách so với `<div>`. Căn dấu đóng theo dòng `<div>` và `</div>`.

**Đáp án minh họa (đặt trong một phương thức Java):**

~~~java
String html = """
        <div>
          <span>A</span>
          <span>B</span>
        </div>
        """;
~~~

**Bài 2 — JSON.** Nhìn vào đoạn sau, giải thích vì sao hai thuộc tính còn 2 dấu cách khi đưa ra khỏi Java:

~~~java
String json = """
            {
              "id": 42,
              "active": false
            }
            """;
~~~

**Đáp án:** lề chung của các dòng root và dấu đóng bị loại; hai dòng thuộc tính vẫn sâu hơn root 2 dấu cách. Hai dấu cách này là **thụt lề tương đối**.

**Bài 3 — Dấu đóng.** Khi nào hai text block có nội dung cùng chữ cái nhưng khác cách căn dấu đóng có thể tạo ra hai chuỗi khác nhau?

**Đáp án:** nếu dấu đóng nằm ở lề khác và tham gia xác định mức lề chung, số dấu cách bị loại ở đầu các dòng thay đổi. Vì vậy phải so sánh **giá trị thực** (`equals`), không chỉ nhìn các dòng chữ.

**Bài 4 — JSON escape.** Trong Java text block, muốn lưu một JSON string có escape `\n` (hai ký tự backslash và chữ `n` trong văn bản JSON), nên viết gì?

**Đáp án:** viết `\\n` trong mã nguồn Java để Java tạo ra `\n` dưới dạng hai ký tự trong JSON. Có thể đưa chuỗi cho JSON parser để kiểm chứng.

## 13. Tài liệu chính thức vẫn áp dụng

- **JEP 378 — Text Blocks (chuẩn hóa trong Java 15):** https://openjdk.org/jeps/378
- **Oracle — Programmer's Guide to Text Blocks:** https://docs.oracle.com/en/java/javase/17/text-blocks/index.html
- **Oracle — Text Blocks (tài liệu các JDK hiện đại):** https://docs.oracle.com/en/java/javase/25/language/text-blocks.html
- **Java Language Specification — Text Blocks:** https://docs.oracle.com/javase/specs/

**Điểm cần nhớ:** text block không “xóa mọi thụt lề”. Nó loại bỏ phần whitespace phụ để chuỗi không lệ thuộc vào vị trí của nó trong file `.java`, đồng thời **giữ độ chênh lệch thụt lề có ý nghĩa** giữa các dòng HTML, JSON và mã nguồn. Để có kết quả ổn định, kiểm soát dòng dấu đóng, newline cuối, dấu escape và kiểm tra chính xác chuỗi khi whitespace là một phần của yêu cầu.

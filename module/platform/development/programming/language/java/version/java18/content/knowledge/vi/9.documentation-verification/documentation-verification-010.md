# Kiểm tra HTML thực tế để xác nhận thụt lề, ký tự đặc biệt, highlight và liên kết

## 1. Vì sao phải kiểm tra trang HTML đã sinh?

Một thẻ Javadoc có thể đúng cú pháp nhưng kết quả người đọc nhìn thấy vẫn chưa đúng ý định. Đoạn mã có thể mất thụt lề, ký tự `<`, `>` hoặc `&` hiển thị thành markup, phần cần nhấn mạnh không có kiểu trình bày, hoặc liên kết trong snippet trỏ tới sai phần tử API. Các lỗi này chỉ lộ rõ khi xem **HTML được Standard Doclet sinh ra** và mở trang bằng trình duyệt.

Từ Java 18, `{@snippet}` cung cấp cách trình bày ví dụ mã có vùng, markup và liên kết. Trên JDK hiện đại, Standard Doclet sinh snippet dưới dạng HTML, có các lớp CSS được mô tả trong đặc tả đầu ra. Tuy nhiên, không nên suy luận toàn bộ giao diện từ source comment: cần kiểm tra cả nội dung HTML, DOM sau khi trình duyệt phân tích, stylesheet và hành vi của nút sao chép.

Bài này thuộc phần **Kiểm chứng tài liệu** của mô-đun **JAVA_VERSION_JAVA18**. Ta sẽ tạo một trang Javadoc có snippet chứa ký tự đặc biệt, nhấn mạnh một đoạn mã và liên kết tới phương thức API; sau đó kiểm tra HTML nguồn, phần hiển thị trên trình duyệt và nội dung được sao chép. Các tính năng được dùng vẫn được hỗ trợ trên JDK hiện đại.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Kiểm tra thụt lề của snippet inline và giải thích ảnh hưởng của `String.stripIndent`.
- Phân biệt ký tự gốc trong snippet với entity được ghi trong HTML.
- Xác minh thuộc tính `lang`, lớp CSS `language-LANG` và markup `@highlight`.
- Kiểm tra liên kết do `@link` trong snippet tạo ra bằng `href` và đích thực tế.
- Dùng View Source, DevTools và chức năng Copy to Clipboard để đối chiếu đầu ra.
- Chẩn đoán lỗi do CSS, JavaScript, encoding, cache hoặc cấu hình build.

## 2. Tạo ví dụ Javadoc có đủ bốn yếu tố cần kiểm tra

Tạo file `src/main/java/com/example/docs/SnippetRenderingApi.java` và lưu bằng UTF-8:

```java
package com.example.docs;

/**
 * Minh họa cách trình bày snippet trong tài liệu API.
 *
 * <p>Ví dụ bên dưới chứa ký tự HTML, tiếng Việt, phần được nhấn mạnh
 * và liên kết tới phương thức {@link #normalize(String)}.</p>
 *
 * {@snippet id="html-audit" lang="java" :
 *     String input = "  <node attr=\"a&b\">Chào bạn</node>  ";
 *     String normalized = normalize(input); // @highlight substring="normalize" type=bold @link substring="normalize" target="SnippetRenderingApi#normalize(String)"
 *     System.out.println(normalized); // @highlight substring="normalized" type=highlighted
 * }
 */
public final class SnippetRenderingApi {
    private SnippetRenderingApi() {
    }

    /**
     * Loại bỏ khoảng trắng ở đầu và cuối chuỗi.
     *
     * @param input chuỗi đầu vào
     * @return chuỗi đã loại bỏ khoảng trắng ở hai đầu
     */
    public static String normalize(String input) {
        return input.strip();
    }
}
```

Snippet được thiết kế để kiểm tra:

| Thành phần | Vị trí trong ví dụ | Điều cần thấy ở HTML/trình duyệt |
| --- | --- | --- |
| Thụt lề | Các dòng trong `{@snippet ... : ... }` | Các dòng giữ quan hệ thụt lề mong muốn. |
| Ký tự đặc biệt | Chuỗi chứa `<node ...>`, `&` và dấu nháy kép | HTML nguồn escape ký tự cần thiết; trình duyệt vẫn hiển thị ký tự gốc. |
| Highlight | `@highlight ... type=bold` và `type=highlighted` | Phần `normalize` và `normalized` có kiểu trình bày tương ứng. |
| Liên kết | `@link ... target="SnippetRenderingApi#normalize(String)"` | Từ `normalize` trong snippet có hyperlink tới phần mô tả phương thức. |

Các markup comment bắt đầu bằng `// @...` là chỉ thị cho Standard Doclet. Chúng không xuất hiện như comment trong snippet được hiển thị. Thẻ `id="html-audit"` đặt một định danh trên phần tử ngoài cùng đại diện cho snippet, giúp tìm và liên kết trực tiếp tới snippet đó.

## 3. Sinh Javadoc và xác định đúng file HTML

Từ thư mục project root `demo/`, chạy trên JDK 18 trở lên:

```bash
mkdir -p build/classes build/docs

javac --release 18 -encoding UTF-8 -d build/classes \
  src/main/java/com/example/docs/SnippetRenderingApi.java

javadoc --release 18 -encoding UTF-8 -charset UTF-8 \
  -Xdoclint:all -Werror \
  -d build/docs \
  src/main/java/com/example/docs/SnippetRenderingApi.java
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force build\classes, build\docs | Out-Null

javac --release 18 -encoding UTF-8 -d build\classes src\main\java\com\example\docs\SnippetRenderingApi.java

javadoc --release 18 -encoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -d build\docs src\main\java\com\example\docs\SnippetRenderingApi.java
```

Với package không thuộc named module, trang lớp được sinh tại:

`build/docs/com/example/docs/SnippetRenderingApi.html`

Mở file này trực tiếp bằng trình duyệt hoặc phục vụ thư mục `build/docs` qua một HTTP server cục bộ. Khi kiểm tra qua HTTP, response header `Content-Type` cũng cần khai báo charset phù hợp, thường là UTF-8. Nếu dùng JDK khác hoặc cấu trúc module khác, đường dẫn HTML có thể thay đổi; hãy tìm trang lớp theo package và tên lớp trong output directory.

## 4. Xác nhận thụt lề của snippet

### 4.1. Snippet inline loại bỏ khoảng trắng thụt lề chung

Nội dung inline nằm giữa dòng xuống hàng sau dấu `:` và dấu `}` đóng thẻ. Standard Doclet loại bỏ khoảng trắng thụt lề chung theo cùng nguyên tắc với `String.stripIndent()`. Vì vậy, vị trí thụt lề của dấu `}` cuối cùng có thể làm thay đổi lề trái của đoạn mã hiển thị.

Ví dụ thứ nhất, dấu `}` đóng snippet ở lề trái:

```java
/**
 * {@snippet :
 *     first();
 *         second();
 * }
 */
```

Khoảng trắng chung tối thiểu là phần lề trước dấu `}` cuối. Kết quả vẫn giữ bốn khoảng trắng trước `first()` và tám khoảng trắng trước `second()`.

Ví dụ thứ hai, đưa dấu `}` đóng snippet vào sâu thêm bốn khoảng trắng:

```java
/**
 * {@snippet :
 *     first();
 *         second();
 *     }
 */
```

Khoảng trắng chung được loại bỏ nhiều hơn, vì vậy `first()` có thể bắt đầu ngay ở cột đầu tiên trong output còn `second()` vẫn thụt vào bốn khoảng trắng. Khi muốn sửa lề hiển thị của snippet inline, kiểm tra vị trí dấu `}` đóng thẻ và khoảng trắng sau dấu `*` của comment.

### 4.2. Đối chiếu source, HTML và trình duyệt

Kiểm tra theo thứ tự:

1. Đọc source Java và đếm khoảng trắng đầu mỗi dòng trong phần snippet.
2. Mở HTML nguồn, tìm phần tử có `id="html-audit"` và đọc nội dung bên trong `pre.snippet`.
3. Mở cùng trang trong trình duyệt, xác nhận khoảng cách giữa các dòng và mức thụt lề tương đối.
4. Dùng nút Copy to Clipboard của snippet, dán vào editor dạng text và so sánh khoảng trắng với kết quả mong muốn.

Phần tử `pre` giữ khoảng trắng và xuống dòng của mã. Nếu HTML có nội dung đúng nhưng trình duyệt làm mất lề hoặc gộp dòng, kiểm tra CSS áp dụng cho `pre.snippet`, đặc biệt thuộc tính `white-space`, `font-family`, `tab-size`, `overflow` và các rule ghi đè từ stylesheet tùy chỉnh.

Với external snippet, nội dung đến từ file ngoài hoặc region được chọn trong file. Hãy so sánh đúng region với phần được hiển thị; đừng áp dụng quy tắc `stripIndent` của inline snippet một cách máy móc cho mọi trường hợp.

## 5. Kiểm tra ký tự đặc biệt và Unicode

### 5.1. HTML nguồn và nội dung trình duyệt là hai cách biểu diễn

Trong snippet, có thể viết trực tiếp các ký tự `<`, `>` và `&`; không cần đổi chúng thành HTML entity trước khi đưa vào `{@snippet}`. Khi sinh HTML, Standard Doclet phải escape các ký tự có ý nghĩa đặc biệt đối với HTML để chúng được hiển thị như văn bản.

Với chuỗi ví dụ:

```java
String input = "<node attr=\"a&b\">Chào bạn</node>";
```

HTML nguồn có thể biểu diễn các ký tự như sau:

| Ký tự trong mã | Biểu diễn entity trong HTML |
| --- | --- |
| `<` | `&lt;` |
| `>` | `&gt;` hoặc ký tự `>` tùy cách serialize |
| `&` | `&amp;` |

Khi trình duyệt phân tích HTML, các entity được giải mã và người đọc nhìn thấy lại `<node attr="a&b">Chào bạn</node>` trong khối mã. Vì vậy, **không kết luận lỗi chỉ vì View Source hiển thị `&lt;` hoặc `&amp;`**; đó là cách HTML bảo toàn nội dung văn bản.

Không escape hai lần. Nếu nội dung thực sự của chương trình là chuỗi `"&lt;"`, HTML phải giữ để trình duyệt hiển thị đúng văn bản `&lt;`, chứ không biến nó thành dấu `<`.

### 5.2. Phân biệt snippet với văn bản Javadoc thông thường

Quy tắc của snippet khác với văn bản HTML thông thường trong documentation comment:

- Trong `{@snippet}`, có thể viết `<`, `>` và `&` trực tiếp; Standard Doclet xử lý chúng như nội dung mã.
- Trong văn bản comment thông thường, dùng HTML entity hoặc `{@code ...}` / `{@literal ...}` để tránh trình phân tích hiểu nhầm dấu ngoặc nhọn là HTML.
- `{@code List<String>}` hiển thị văn bản trong font mã và không diễn giải `<String>` thành HTML.

### 5.3. Kiểm tra tiếng Việt và charset

Lưu source bằng UTF-8, dùng `javadoc -encoding UTF-8` để đọc source và chọn output charset phù hợp, ví dụ `-charset UTF-8`. Sau khi sinh tài liệu:

- Kiểm tra HTML nguồn có giữ đúng chuỗi `Chào bạn`.
- Kiểm tra phần hiển thị trong browser không biến thành chuỗi ký tự lỗi.
- Nếu mở từ server, kiểm tra HTTP `Content-Type` không khai báo charset khác với byte thực tế.
- Nếu HTML nguồn đúng nhưng browser sai, kiểm tra metadata, response header, cache và encoding của file.

## 6. Xác nhận highlight và thông tin ngôn ngữ

### 6.1. Thuộc tính `lang` không đồng nghĩa với tô màu mọi token

Thuộc tính `lang="java"` nhận diện ngôn ngữ snippet. Standard Doclet nhận diện các giá trị `java` và `properties`; với external snippet, nếu không chỉ định `lang`, ngôn ngữ có thể được suy ra từ phần mở rộng file. Giá trị ngôn ngữ được chuyển vào HTML; phần output của snippet có thể dùng lớp `language-LANG`, chẳng hạn `language-java` hoặc `language-properties`.

Lớp ngôn ngữ, nếu được sinh ra, giúp stylesheet hoặc thư viện JavaScript nhận diện loại nội dung. Không nên mặc định rằng chỉ cần đặt `lang="java"` thì Standard Doclet sẽ tự tô màu từng keyword, string và comment như một IDE. Nếu dự án dùng bộ syntax highlighter như Prism, hãy xác nhận script và CSS của bộ đó được tải, chạy trên đúng phần tử snippet và không bị CSP hoặc đường dẫn asset chặn.

### 6.2. `@highlight` tạo điểm nhấn có chủ đích

Markup `@highlight` có thể áp dụng cho cả dòng hoặc một phần dòng:

```java
String normalized = normalize(input); // @highlight substring="normalize" type=bold
System.out.println(normalized);        // @highlight substring="normalized" type=highlighted
```

Các kiểu được Standard Doclet hỗ trợ gồm:

| `type` | Lớp CSS đầu ra | Ý nghĩa |
| --- | --- | --- |
| `bold` | `bold` | Nhấn mạnh bằng kiểu chữ đậm. |
| `italic` | `italic` | Nhấn mạnh bằng kiểu chữ nghiêng. |
| `highlighted` | `highlighted` | Nhấn mạnh bằng kiểu highlight của stylesheet. |

Có thể chọn nội dung bằng `substring` hoặc `regex`; nếu không chỉ định, toàn bộ dòng hoặc vùng được áp dụng. Markup comment có thể kết hợp với `@link` và không xuất hiện trong phần mã được render.

### 6.3. Kiểm tra lớp CSS và hiệu ứng thực tế

Đặc tả đầu ra Standard Doclet JDK 25 mô tả các lớp liên quan:

- `snippet-container`: phần tử `div` bao quanh snippet.
- `snippet`: phần tử `pre` trình bày snippet.
- `snippet-copy`: thành phần giao diện sao chép snippet.
- `language-LANG`: lớp ngôn ngữ có thể được dùng trong phần output của snippet, ví dụ `language-java`.
- `bold`, `italic`, `highlighted`: lớp của phần nội dung được markup nhấn mạnh.

Trong DevTools, chọn phần tử có `id="html-audit"` rồi lần theo phần tử `pre.snippet`. Kiểm tra lớp `language-java` nếu output có sinh lớp này, các lớp highlight và stylesheet tương ứng. Tiếp theo xem Computed Styles để chắc chắn CSS không vô hiệu hóa `font-weight`, `font-style`, màu chữ hoặc màu nền của vùng được nhấn mạnh.

Nếu lớp `highlighted` đã có trong DOM nhưng không thấy khác biệt, vấn đề thường nằm ở CSS hoặc theme. Javadoc có thể bổ sung stylesheet bằng `--add-stylesheet`; tùy chọn này giữ stylesheet mặc định và cho phép ghi đè chọn lọc. `--main-stylesheet` thay thế stylesheet mặc định, do đó file CSS tùy chỉnh phải tự cung cấp những kiểu mà trang cần.

## 7. Xác minh liên kết trong snippet

### 7.1. Liên kết được tạo từ markup `@link`

Trong ví dụ:

```java
String normalized = normalize(input); // @link substring="normalize" target="SnippetRenderingApi#normalize(String)"
```

`@link` chọn đoạn văn bản bằng `substring` hoặc `regex`, sau đó dùng `target` theo cú pháp tham chiếu API tương tự `{@link ...}` trong Javadoc. Với ví dụ trên, `normalize` phải trở thành liên kết tới phần mô tả phương thức `SnippetRenderingApi#normalize(String)`.

Có thể dùng `type=linkplain` nếu muốn kiểu liên kết văn bản thường; mặc định là `link`. Không tạo nhiều `@link` chồng lấn trên cùng văn bản vì Javadoc sẽ báo lỗi.

### 7.2. Kiểm tra `href`, không chỉ màu chữ hoặc gạch chân

Trong HTML/DevTools:

1. Chọn đoạn `normalize` trong snippet.
2. Xác nhận nó nằm trong một phần tử liên kết `<a>`.
3. Đọc giá trị `href`; nó phải dẫn tới trang và anchor của phương thức được chỉ định.
4. Mở liên kết và xác nhận trang đích đúng lớp, đúng phương thức, đúng overload.
5. Kiểm tra liên kết vẫn hoạt động khi tài liệu được triển khai ở đường dẫn thực tế.

Một liên kết có màu xanh hoặc gạch chân chưa chứng minh đích chính xác. Ngược lại, nếu `href` đúng nhưng người dùng không nhận ra đây là liên kết, kiểm tra CSS của trạng thái link, hover và focus.

`id="html-audit"` của snippet cũng có thể được dùng làm anchor tới chính khối mã. Khi kiểm tra, xác nhận định danh tồn tại một lần trên phần tử ngoài cùng đại diện cho snippet và URL có fragment tương ứng mở đúng vị trí.

## 8. Quy trình kiểm tra HTML thực tế

### 8.1. Tìm dấu hiệu trong HTML nguồn bằng PowerShell

Từ project root:

```powershell
$htmlPath = 'build\docs\com\example\docs\SnippetRenderingApi.html'
Select-String -Path $htmlPath -Pattern 'html-audit','snippet-container','snippet-copy','language-java','highlighted','bold','href=','&lt;','&gt;','&amp;' -Context 1,1
```

Các chuỗi cần kiểm tra:

- `html-audit`: định danh snippet.
- `snippet-container` và `snippet`: vùng chứa và khối mã.
- `language-java`: thông tin ngôn ngữ.
- `bold`, `highlighted`: markup nhấn mạnh.
- `href=`: đích liên kết.
- `&lt;`, `&gt;`, `&amp;`: escape HTML của ký tự đặc biệt.

### 8.2. Tìm dấu hiệu bằng Bash

```bash
grep -nE 'html-audit|snippet-container|snippet-copy|language-java|highlighted|bold|href=|&lt;|&gt;|&amp;' \
  build/docs/com/example/docs/SnippetRenderingApi.html
```

Lệnh tìm chuỗi chỉ là bước định vị. Nếu cần kiểm tra cấu trúc thẻ lồng nhau hoặc giá trị `textContent`, hãy dùng DevTools/DOM inspector hoặc một HTML parser; không nên dùng regex để khẳng định toàn bộ cấu trúc HTML hợp lệ.

### 8.3. Kiểm tra trên trình duyệt

Mở `SnippetRenderingApi.html`, rồi kiểm tra lần lượt:

1. **Nội dung:** đoạn mã hiển thị đầy đủ, không mất ký tự hoặc bị chèn markup lạ.
2. **Thụt lề:** các dòng có lề trái và mức lồng nhau như source mong muốn.
3. **Ký tự đặc biệt:** dấu `<`, `>` và `&` xuất hiện như văn bản trong code.
4. **Highlight:** phần được đánh dấu có kiểu chữ hoặc nền khác theo theme.
5. **Liên kết:** di chuột, xem URL đích, mở liên kết và kiểm tra anchor.
6. **Copy:** dùng nút sao chép của snippet, dán vào editor và so sánh nội dung với đoạn mã kỳ vọng.
7. **Responsive:** thu nhỏ cửa sổ để kiểm tra đoạn mã dài có thể cuộn ngang mà không phá vỡ trang.

### 8.4. Đọc DOM và CSS bằng DevTools

Trong tab Elements/Inspector:

- Tìm `id="html-audit"`.
- Xem phần tử `pre.snippet` và `div.snippet-container`.
- Xem các phần tử con chứa `bold`, `italic`, `highlighted`.
- Chọn liên kết trong snippet và đọc `href`.
- Trong tab Styles/Computed, xem rule nào quyết định `white-space`, `font-family`, màu và kiểu chữ.
- Trong Network/Console, kiểm tra CSS hoặc JavaScript highlighter có tải thành công không.

Không phụ thuộc vào toàn bộ cấu trúc DOM nội bộ của một phiên bản JDK. Đặc tả Standard Doclet công bố các lớp CSS hữu ích cho việc tùy chỉnh, nhưng cũng lưu ý một số chi tiết đầu ra có thể thay đổi giữa các release. Hãy kiểm tra các đặc điểm cấp cao và hành vi nhìn thấy được, thay vì viết test khóa chặt vào mọi `span` hoặc thứ tự thuộc tính HTML.

## 9. Chẩn đoán khi HTML khác với kỳ vọng

| Triệu chứng | Tầng cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Snippet bị lệch lề ngay trong HTML | Source snippet và quy tắc stripIndent | Kiểm tra khoảng trắng sau dấu `*`, lề chung và vị trí `}` đóng snippet inline. |
| HTML có lề đúng nhưng browser gộp dòng | CSS | Kiểm tra `white-space` của `pre.snippet` và stylesheet tùy chỉnh. |
| `<` hoặc `&` hiển thị thành entity nguyên văn | Nội dung bị escape hai lần | Bỏ entity thủ công khỏi nội dung snippet; để Javadoc escape HTML một lần. |
| Ký tự tiếng Việt thành mojibake | Encoding đầu vào/đầu ra hoặc HTTP header | Lưu source UTF-8, cấu hình `-encoding UTF-8`, output charset và `Content-Type`. |
| Có `language-java` nhưng không có màu keyword | Highlighter | `lang` chỉ nhận diện ngôn ngữ; kiểm tra script/CSS tô màu token hoặc dùng `@highlight` rõ ràng. |
| Markup comment xuất hiện trong snippet | Cú pháp markup hoặc loại comment | Kiểm tra đúng comment cuối dòng và tên markup tag được Standard Doclet nhận diện. |
| `@highlight` có trong source nhưng không có hiệu ứng | Region, substring/regex hoặc CSS | Kiểm tra phạm vi áp dụng, chuỗi khớp và lớp `bold`/`italic`/`highlighted`. |
| Chữ có vẻ là link nhưng mở sai trang | `target` hoặc `href` | Đối chiếu `target` với `href`, kiểm tra tên lớp, chữ ký và overload. |
| Link đúng trong local nhưng hỏng sau deploy | Đường dẫn tương đối/base URL | Kiểm tra cấu trúc thư mục xuất bản, context path và URL cuối cùng. |
| Nút Copy không hoạt động | JavaScript hoặc browser permissions | Kiểm tra Console, script tải và thao tác clipboard trên trang được phục vụ qua HTTP/HTTPS. |
| Trang cũ vẫn hiện sau khi build lại | Cache hoặc mở nhầm output directory | Mở đúng file mới, hard reload và kiểm tra thời gian cập nhật của HTML/CSS. |

Standard Doclet không tự sửa các lỗi HTML được viết trong documentation comment. DocLint có thể phát hiện một số vấn đề ở source, nhưng vẫn phải xem và proofreading HTML đã sinh để xác nhận kết quả đúng như dự định.

## 10. Quy trình kiểm chứng trong CI

Có thể đưa các bước sau vào pipeline tài liệu:

```text
Source UTF-8
    |
    v
javac / javadoc với DocLint
    |
    v
HTML output được sinh
    |
    +--> Kiểm tra snippet id và class CSS
    |
    +--> Kiểm tra entity và Unicode
    |
    +--> Kiểm tra href và anchor
    |
    v
HTML validator + link checker
    |
    v
Kiểm tra browser / screenshot trên trang đại diện
```

Tối thiểu, CI nên:

1. Chạy Javadoc với encoding đã quy định và `-Xdoclint:all -Werror`.
2. Kiểm tra tiến trình Javadoc trả exit code `0`.
3. Xác nhận HTML lớp có chứa snippet id và các dấu hiệu mong đợi.
4. Kiểm tra liên kết nội bộ/ngoài bằng link checker.
5. Chạy HTML validator hoặc accessibility checker trên HTML đầu ra nếu dự án có yêu cầu chất lượng tương ứng.
6. Có bước kiểm tra trực quan định kỳ để phát hiện thay đổi giao diện do JDK, CSS hoặc JavaScript.

Không nên chỉ assert rằng file HTML tồn tại. Một file có thể được tạo ra nhưng snippet sai nội dung, link sai đích hoặc stylesheet không được tải.

### Bài tự luyện

1. Di chuyển dấu `}` đóng snippet inline sâu thêm bốn khoảng trắng. So sánh lề trái của HTML trước và sau thay đổi.
2. Thay `<node attr=\"a&b\">` bằng `&lt;node attr=\"a&amp;b\"&gt;`. Quan sát vì sao browser có thể hiển thị entity như văn bản thay vì ký tự gốc.
3. Bỏ `lang="java"`. Kiểm tra lớp ngôn ngữ trong HTML thay đổi thế nào.
4. Đổi `type=highlighted` thành `type=italic`. Xác nhận lớp CSS và hiệu ứng hiển thị.
5. Đổi target của `@link` sang một overload khác. Dùng `href` xác nhận đích thực tế.
6. Thêm stylesheet ghi đè `pre.snippet { white-space: normal; }`. Quan sát lỗi thụt lề/xuống dòng và sửa lại rule.
7. Tạm chặn file JavaScript highlighter. Phân biệt lớp `language-java` còn tồn tại với token coloring do script tạo.
8. Mở cùng HTML bằng `file://` và HTTP server. Kiểm tra sự khác nhau về charset, script và thao tác clipboard.

## 11. Tài liệu tham khảo chính thức

- [JavaDoc Guide — Snippets (JDK 25)](https://docs.oracle.com/en/java/javase/25/javadoc/javadoc-guide.pdf): thụt lề inline snippet, markup `@highlight`/`@link`, external snippet, nút Copy to Clipboard và giới hạn của việc kiểm tra snippet.
- [JavaDoc Documentation Comment Specification for the Standard Doclet (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): cú pháp snippet, xử lý ký tự, region, markup và liên kết.
- [JavaDoc Output Generated by the Standard Doclet (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/std-doclet-output.html): các lớp `snippet`, `snippet-container`, `snippet-copy`, `language-LANG`, `bold`, `italic` và `highlighted`.
- [The javadoc Command (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html): tùy chọn encoding, stylesheet và script của Javadoc.
- [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): tính năng snippet được đưa vào Java 18.

**Ghi nhớ:** Source comment chỉ là đầu vào. Hãy kiểm tra HTML nguồn để xác nhận entity, id, lớp CSS và `href`; sau đó mở trang trong trình duyệt để xác nhận thụt lề, ký tự hiển thị, highlight, liên kết và chức năng Copy. `lang` nhận diện ngôn ngữ snippet, còn markup `@highlight` tạo điểm nhấn cụ thể; chúng không tự thay thế việc kiểm tra stylesheet và JavaScript của trang đã xuất bản.

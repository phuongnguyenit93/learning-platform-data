# HTML encoding

## 1. Mục tiêu và phạm vi

HTML encoding là cách biểu diễn các ký tự có ý nghĩa cú pháp trong HTML thành những tham chiếu ký tự phù hợp để trình duyệt hiển thị chúng như dữ liệu. Khi một tên sản phẩm chứa dấu `<`, ứng dụng thường cần hiển thị dấu đó, không cần cho phép tên sản phẩm mở một thẻ HTML mới.

Trong thiết kế yêu cầu bảo mật, câu “ứng dụng phải chống XSS” chưa chỉ rõ đội phát triển cần làm gì và đội kiểm thử cần quan sát điều gì. Với HTML encoding, yêu cầu cần xác định được dữ liệu nào đi vào HTML, vị trí chèn dữ liệu, cơ chế bảo vệ tại vị trí đó và bằng chứng xác nhận dữ liệu không trở thành cấu trúc hoặc mã thực thi ngoài ý muốn.

Sau bài này, người học có thể:

- Giải thích vì sao dữ liệu hợp lệ về nghiệp vụ vẫn cần HTML encoding khi được hiển thị.
- Phân biệt văn bản HTML, giá trị thuộc tính và các ngữ cảnh có quy tắc riêng như URL hoặc JavaScript.
- Đặc tả yêu cầu encoding có phạm vi, chủ sở hữu và tiêu chí nghiệm thu rõ ràng.
- Nhận biết các lỗi do nối chuỗi HTML, bỏ qua auto-escaping hoặc encode nhiều lần.
- Áp dụng nguyên tắc vào ứng dụng Java và mã giao diện mà vẫn giữ nguyên ý nghĩa dữ liệu gốc.

Bài tập trung vào dữ liệu được hiển thị dưới dạng văn bản trong tài liệu HTML và một số thuộc tính văn bản thông thường. Nội dung HTML do người dùng chủ động soạn cần thêm chính sách sanitization; dữ liệu trong JavaScript, CSS và URL cần xử lý theo ngữ cảnh riêng.

## 2. Rủi ro xuất hiện tại nơi dữ liệu được đưa vào HTML

### 2.1. Cùng một chuỗi có thể là dữ liệu hoặc cú pháp

Một hệ thống quản lý yêu cầu bảo mật cho phép người dùng nhập tiêu đề:

```text
Kiểm tra <quyền truy cập> & "vai trò quản trị"
```

Về nghiệp vụ, đây có thể là tiêu đề hoàn toàn hợp lệ. Nhưng khi máy chủ dựng trang bằng cách nối trực tiếp dữ liệu vào chuỗi HTML:

```java
String html = "<h2>" + requirementTitle + "</h2>";
```

trình duyệt không biết phần nào đến từ mẫu giao diện và phần nào đến từ người dùng. Nó phân tích toàn bộ kết quả theo cú pháp HTML. Dấu `<` trong tiêu đề có thể bắt đầu markup; dữ liệu mang cấu trúc khác còn có thể làm xuất hiện phần tử hoặc thuộc tính ngoài thiết kế.

Đường đi của dữ liệu có thể rất dài:

```text
Biểu mẫu → API → cơ sở dữ liệu → API quản trị → template HTML → trình duyệt
```

Việc dữ liệu đã được lưu trong cơ sở dữ liệu, nhập từ tệp nội bộ hoặc trả về từ một dịch vụ khác không làm nó tự nhiên an toàn cho HTML. Điểm cần bảo vệ là nơi dữ liệu đi vào bộ phân tích HTML.

### 2.2. Encoding giữ ranh giới giữa dữ liệu và cấu trúc

Nếu tiêu đề trên được encode cho vùng văn bản HTML, nguồn trang có thể chứa:

```html
<h2>Kiểm tra &lt;quyền truy cập&gt; &amp; &quot;vai trò quản trị&quot;</h2>
```

Trình duyệt hiển thị nội dung người dùng mong muốn:

```text
Kiểm tra <quyền truy cập> & "vai trò quản trị"
```

Các ký tự được tạo ra từ tham chiếu ký tự trong vùng văn bản này không bị đọc lại như một đoạn markup mới. Vì vậy, `&lt;` tạo ra ký tự `<` để hiển thị, thay vì mở một thẻ do người dùng điều khiển.

Đây là bảo đảm có phạm vi. Nếu mã giao diện lấy lại nội dung văn bản rồi truyền vào `innerHTML`, một lần phân tích HTML mới có thể xuất hiện. Encoding ở lần render đầu không cho phép bỏ qua việc đánh giá nơi sử dụng tiếp theo.

### 2.3. Không đồng nhất encoding với validation hoặc mã hóa bí mật

Validation trả lời “giá trị này có đáp ứng hợp đồng dữ liệu và nghiệp vụ không?”. Encoding trả lời “biểu diễn giá trị này như thế nào ở vị trí đầu ra đang dùng?”. Hai câu hỏi bổ sung cho nhau.

Ví dụ, tên người dùng có giới hạn 100 ký tự vẫn có thể chứa dấu nháy hoặc dấu `&`. Cấm mọi ký tự đặc biệt sẽ làm hỏng những tên hợp lệ và không tạo ra cơ chế bảo vệ theo ngữ cảnh. Ngược lại, encoding đúng không thay thế giới hạn độ dài hoặc kiểm tra quyền sửa tên.

HTML encoding cũng không phải encryption. Nó không che giấu nội dung, không bảo vệ bí mật và không ngăn người đã có quyền xem trang đọc dữ liệu. Đây là một cách biểu diễn dữ liệu dành cho cú pháp HTML.

## 3. Xác định đúng ngữ cảnh trước khi chọn encoder

Một trang HTML có nhiều vùng với cách diễn giải khác nhau. Tên gọi chung “escape HTML” không đủ để bảo vệ mọi vị trí.

| Vị trí chèn dữ liệu | Ví dụ | Cách tiếp cận phù hợp |
| --- | --- | --- |
| Văn bản trong phần tử HTML thông thường | `<p>GIÁ_TRỊ</p>` | HTML text encoding hoặc API tạo text node |
| Thuộc tính văn bản có tên cố định, giá trị được đặt trong dấu nháy | `<span title="GIÁ_TRỊ">` | Encoding phù hợp cho thuộc tính và luôn giữ dấu nháy bao giá trị |
| URL trong thuộc tính | `<a href="GIÁ_TRỊ">` | Kiểm tra chính sách URL, xử lý thành phần URL khi cần, sau đó bảo vệ ngữ cảnh thuộc tính HTML |
| Mã JavaScript hoặc thuộc tính sự kiện | `<script>...</script>`, `onclick="..."` | Tránh chèn dữ liệu trực tiếp; HTML encoding không phải biện pháp đủ |
| CSS hoặc thuộc tính `style` | `<style>...</style>`, `style="..."` | Thiết kế dữ liệu có cấu trúc và xử lý riêng cho CSS |
| Tên thẻ, tên thuộc tính, HTML comment | `<GIÁ_TRỊ>`, `<!-- GIÁ_TRỊ -->` | Không cho dữ liệu không tin cậy quyết định cấu trúc này |

### 3.1. Văn bản HTML

Đây là trường hợp phù hợp nhất cho HTML text encoding:

```html
<p class="requirement-title">GIÁ_TRỊ</p>
```

Thẻ `p`, tên class và cấu trúc trang do ứng dụng xác định. Người dùng chỉ điều khiển phần văn bản nằm bên trong.

Nếu dữ liệu là `<strong>Quan trọng</strong>` nhưng trường dữ liệu được định nghĩa là văn bản thuần, người dùng phải thấy nguyên chuỗi đó. Không được tạo thêm phần tử `strong` từ đầu vào.

### 3.2. Thuộc tính văn bản được đặt trong dấu nháy

Với thuộc tính như `title`, một dấu nháy không được xử lý có thể kết thúc giá trị sớm:

```html
<span title="GIÁ_TRỊ">Chi tiết</span>
```

Yêu cầu phải giữ tên thuộc tính cố định, đặt toàn bộ giá trị trong dấu nháy và encode theo ngữ cảnh thuộc tính. Không cho phép dữ liệu người dùng tạo ra tên thuộc tính, chọn dấu phân cách hoặc bổ sung một đoạn thuộc tính tùy ý.

Một thuộc tính chứa văn bản không tương đương thuộc tính chứa chương trình. `title`, `onclick`, `style`, `href` và `srcdoc` có ý nghĩa khác nhau; không áp dụng một quy tắc cho toàn bộ chúng chỉ vì đều nằm trong dấu `<...>`.

### 3.3. Ngữ cảnh lồng nhau

Trong liên kết dưới đây, tham số tìm kiếm nằm trong URL, URL lại nằm trong một thuộc tính HTML:

```html
<a href="/search?q=GIÁ_TRỊ">Tìm kiếm</a>
```

HTML encoding không thay thế việc dựng đúng tham số URL. Tương tự, một URL hoàn chỉnh được HTML-encode vẫn có thể vi phạm chính sách điều hướng nếu ứng dụng cho phép một scheme nguy hiểm hoặc một đích ngoài phạm vi được phép.

Vì vậy, một yêu cầu bảo mật tốt sẽ tách hai quyết định: URL nào được chấp nhận và URL hợp lệ đó được biểu diễn thế nào trong HTML. Với các ngữ cảnh phức tạp hơn như JavaScript nằm trong thuộc tính HTML, lựa chọn ưu tiên là thiết kế lại để không chèn dữ liệu trực tiếp vào mã.

## 4. Các ký tự thường được encode

Những ký tự dưới đây thường xuất hiện trong các cơ chế HTML escaping:

| Ký tự gốc | Biểu diễn thường dùng | Ý nghĩa đối với cú pháp |
| --- | --- | --- |
| `&` | `&amp;` | Có thể bắt đầu một tham chiếu ký tự |
| `<` | `&lt;` | Có thể bắt đầu markup |
| `>` | `&gt;` | Tham gia dấu phân cách của markup |
| `"` | `&quot;` hoặc `&#34;` | Có thể đóng giá trị thuộc tính dùng nháy kép |
| `'` | `&#39;` hoặc `&#x27;` | Có thể đóng giá trị thuộc tính dùng nháy đơn |

Không phải encoder hợp lệ nào cũng tạo đúng cùng một chuỗi byte. Một thư viện có thể dùng tham chiếu số, thư viện khác dùng tên; encoder cho văn bản HTML có thể giữ một dấu nháy vốn không mang ý nghĩa cấu trúc ở vị trí đó.

Tiêu chí bảo mật cần tập trung vào ngữ cảnh sử dụng và cây DOM tạo ra. Khi chọn một encoder cụ thể, kiểm thử đơn vị có thể kiểm tra kết quả chính xác theo hợp đồng thư viện; nhưng yêu cầu toàn hệ thống không nên nhầm “đúng một dạng entity” với “an toàn”.

### 4.1. Không viết chuỗi thay thế tùy tiện

Một đoạn code thay `<` trước, sau đó thay `&` có thể biến:

```text
< → &lt; → &amp;lt;
```

Kết quả là người dùng thấy `&lt;` thay vì `<`. Đây là lỗi biểu diễn do encode lại phần output vừa tạo.

Các cách “chặn từ khóa nguy hiểm” như xóa `script`, `onerror` hoặc dấu ngoặc cũng không tạo thành HTML encoder. HTML có quy tắc phân tích cụ thể; dữ liệu cần được biểu diễn an toàn theo ngữ cảnh thay vì được sửa bằng một danh sách từ cấm.

### 4.2. Encoding không có nghĩa là cấm Unicode

Một yêu cầu HTML encoding không nên bắt hệ thống chuyển toàn bộ tiếng Việt thành ký tự ASCII. Các chuỗi như `Nguyễn Ánh`, `quyền sở hữu` và biểu tượng cảm xúc vẫn phải được hiển thị đúng theo hợp đồng dữ liệu.

Việc dùng UTF-8 nhất quán ở lớp HTTP, template và dữ liệu giúp tránh lỗi diễn giải ký tự. Charset và encoding cho HTML giải quyết những vấn đề khác nhau: một cơ chế xác định cách đọc byte, cơ chế kia giữ ký tự dữ liệu không trở thành cú pháp ngoài ý muốn.

## 5. Từ rủi ro đến yêu cầu bảo mật có thể kiểm chứng

### 5.1. Mô tả tình huống đe dọa

Xét một hệ thống lưu các yêu cầu bảo mật. Một cộng tác viên có thể sửa tiêu đề yêu cầu nhưng không có quyền quản trị. Quản trị viên thường mở danh sách yêu cầu để duyệt nội dung.

Nếu tiêu đề được chèn trực tiếp vào HTML, quyền nhập văn bản có thể trở thành khả năng tác động đến trang mà quản trị viên xem. Thiệt hại tiềm tàng không chỉ là giao diện xấu đi: nội dung có thể làm thay đổi cấu trúc DOM hoặc tạo cơ hội chạy mã trong phiên của người xem.

Yêu cầu HTML encoding cần bảo vệ đúng ranh giới giữa quyền cung cấp dữ liệu và quyền quyết định cấu trúc trang.

### 5.2. Một đặc tả còn thiếu

```text
Hệ thống phải escape các input để an toàn.
```

Câu này bỏ ngỏ nhiều điều: escape ở lúc nhận dữ liệu hay lúc render; escape cho HTML hay cho URL; có bao gồm dữ liệu từ cơ sở dữ liệu không; trang quản trị và trang lỗi có nằm trong phạm vi không; rich text được xử lý ra sao.

### 5.3. Một đặc tả rõ hơn

```text
REQ-HTML-ENC-01

Tại mọi vị trí hiển thị văn bản thuần trong phần nội dung của trang HTML,
hệ thống phải đưa dữ liệu có nguồn gốc ngoài template qua cơ chế HTML text
encoding của lớp hiển thị hoặc qua API tạo text node có tác dụng tương đương.

Phạm vi bao gồm dữ liệu từ người dùng, cơ sở dữ liệu, tệp nhập và dịch vụ
tích hợp, trên cả giao diện thông thường, quản trị và trang thông báo lỗi.

Dữ liệu đầu vào không được tạo thêm phần tử, thuộc tính hoặc mã thực thi
ngoài cấu trúc được định nghĩa trong template. Nội dung văn bản hợp lệ
phải được hiển thị đúng sau khi trình duyệt phân tích tài liệu.
```

“Ngoài template” ở đây là nguồn dữ liệu, không đồng nghĩa mọi dữ liệu đều độc hại. Việc áp dụng mặc định cho dữ liệu động giúp đội phát triển không phải đoán một chuỗi đã đi qua đủ bao nhiêu hệ thống để được xem là đáng tin.

### 5.4. Các yêu cầu hỗ trợ

| Mã yêu cầu | Nội dung | Bằng chứng nghiệm thu |
| --- | --- | --- |
| REQ-HTML-ENC-02 | Auto-escaping phải được bật cho template HTML sử dụng trong các luồng thuộc phạm vi | Cấu hình template và kết quả render đại diện |
| REQ-HTML-ENC-03 | Dữ liệu động trong thuộc tính văn bản phải dùng tên thuộc tính cố định, giá trị đặt trong dấu nháy và encoder phù hợp | Template cùng cây DOM sau render |
| REQ-HTML-ENC-04 | Các chỗ bỏ qua escaping phải được liệt kê, có chủ sở hữu và mô tả nguồn gốc giá trị được đưa vào | Danh mục điểm render HTML có chủ ý và quyết định thiết kế |
| REQ-HTML-ENC-05 | Không lưu bản HTML-encoded thay cho dữ liệu nghiệp vụ gốc của các trường văn bản thuần | Hợp đồng lưu trữ và kết quả đọc dữ liệu gốc |
| REQ-HTML-ENC-06 | Mã giao diện phải đưa văn bản thuần vào DOM bằng API phù hợp thay vì truyền trực tiếp vào HTML sink | Các vị trí cập nhật DOM và kiểm thử hành vi |
| REQ-HTML-ENC-07 | Hệ thống phải bảo toàn tiếng Việt và các ký tự Unicode được hợp đồng dữ liệu cho phép | Kết quả hiển thị và dữ liệu khôi phục từ DOM |

Số lượng yêu cầu phụ thuộc kiến trúc. Không cần tạo nhiều mã chỉ để đủ danh sách; mỗi yêu cầu nên bảo vệ một điều kiện mà một đội cụ thể có thể triển khai và chứng minh.

## 6. Ví dụ Java: minh họa cơ chế cho văn bản HTML

Trong ứng dụng thực tế, ưu tiên cơ chế auto-escaping của template hoặc thư viện encoder được dự án lựa chọn. Một helper tự viết dễ bị dùng sai sang thuộc tính URL, JavaScript hoặc các ngữ cảnh không thuộc thiết kế ban đầu.

Ví dụ sau chỉ minh họa nguyên lý cho văn bản trong phần tử HTML thông thường. Nó duyệt đầu vào một lần nên không encode lại entity vừa sinh ra:

```java
public final class HtmlTextExample {
    private HtmlTextExample() {
    }

    public static String encodeText(String value) {
        if (value == null) {
            throw new IllegalArgumentException("value must not be null");
        }

        StringBuilder result = new StringBuilder();

        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);

            switch (ch) {
                case '&':
                    result.append("&amp;");
                    break;
                case '<':
                    result.append("&lt;");
                    break;
                case '>':
                    result.append("&gt;");
                    break;
                case '"':
                    result.append("&quot;");
                    break;
                case '\'':
                    result.append("&#39;");
                    break;
                default:
                    result.append(ch);
            }
        }

        return result.toString();
    }

    public static String renderTitle(String title) {
        return "<h2>" + encodeText(title) + "</h2>";
    }
}
```

Với đầu vào:

```text
R&D <Admin> "A" 'B'
```

`renderTitle` tạo ra:

```html
<h2>R&amp;D &lt;Admin&gt; &quot;A&quot; &#39;B&#39;</h2>
```

Trình duyệt hiển thị lại chuỗi gốc bên trong `h2`. Phần tử `Admin` không xuất hiện trong DOM.

Giới hạn của ví dụ phải được hiểu cùng với mã nguồn:

- Hợp đồng phương thức từ chối `null`; ứng dụng cần quyết định riêng cách biểu diễn dữ liệu thiếu.
- Đầu vào là văn bản đã đáp ứng hợp đồng ký tự và độ dài của ứng dụng. Helper không thay validation.
- Mã giữ nguyên các ký tự khác; nó không xác thực URL, lọc HTML có chủ ý hoặc tạo chuỗi JavaScript.
- Tên phương thức nói rõ `encodeText` để giảm nguy cơ coi nó là một bộ bảo vệ cho mọi đầu ra.

Không nên dùng helper này như biện pháp chung cho toàn bộ response. Một response có thể chứa nhiều ngữ cảnh hoặc là JSON, tệp tải về và dữ liệu nhị phân; encoding toàn bộ sẽ làm hỏng giao thức hoặc để sót ngữ cảnh cần cơ chế khác.

## 7. Template và DOM: dùng cơ chế đúng tại nơi render

### 7.1. Auto-escaping của template

Một template engine có cơ chế escaping giúp giảm số điểm phải gọi encoder thủ công. Ví dụ với một template HTML dùng Thymeleaf:

```html
<h2 th:text="${requirement.title}">Tiêu đề yêu cầu</h2>
<span th:title="${requirement.title}">Xem chi tiết</span>
```

Trong cách dùng này, ứng dụng cung cấp dữ liệu gốc; template chịu trách nhiệm biểu diễn dữ liệu ở vị trí đầu ra tương ứng. Khi triển khai, đội phát triển cần xác nhận chế độ template và hành vi escaping thực tế của engine đang dùng.

Một thao tác render nội dung không escape có ý nghĩa khác:

```html
<div th:utext="${requirement.description}"></div>
```

Nếu `description` được định nghĩa là văn bản thuần, cách render trên phá vỡ hợp đồng: nội dung có thể được phân tích như HTML. Việc đổi sang render không escape để “sửa lỗi hiển thị entity” còn có thể che giấu lỗi double encoding và tạo rủi ro mới.

Đối với trường được thiết kế là HTML, đội phát triển phải xác định riêng chính sách nội dung được phép, cơ chế sanitization và nguồn giá trị đã qua chính sách đó. Tên trường hoặc tên biến như `safeHtml` không phải bằng chứng nó đã an toàn.

### 7.2. Chèn văn bản bằng DOM API

Khi API trả về dữ liệu JSON và trình duyệt tự dựng phần giao diện, có thể dùng:

```javascript
const titleElement = document.querySelector("#requirement-title");
titleElement.textContent = requirement.title;
```

`textContent` tạo hoặc thay nội dung văn bản; nó không yêu cầu ứng dụng dựng một chuỗi HTML chứa giá trị động. Đầu vào như `<b>Quản trị</b>` được hiển thị nguyên văn, không tạo thêm thẻ `b`.

Không HTML-encode chuỗi trước khi gán vào `textContent`. API đã nhận dữ liệu như văn bản; nếu truyền `&lt;b&gt;`, người dùng sẽ thấy chính chuỗi entity đó. Mục tiêu là đưa dữ liệu vào đúng API, không phải tăng số lần encode.

Ngược lại, đoạn sau yêu cầu trình duyệt phân tích chuỗi thành HTML:

```javascript
titleElement.innerHTML = requirement.title;
```

Với trường văn bản thuần, đây là điểm sử dụng cần thay đổi. Không thể suy ra an toàn từ việc API JSON trước đó đã serialize dữ liệu hợp lệ; JSON serialization và HTML parsing là hai lớp khác nhau.

### 7.3. Không ghép tên cấu trúc từ dữ liệu

Ngay cả khi giá trị được encode đúng, dữ liệu không nên quyết định tên thẻ, tên thuộc tính hoặc chuỗi template. Ví dụ, cho người dùng nhập tên thuộc tính rồi gán giá trị không tạo ra cùng mức bảo đảm với thuộc tính `title` cố định.

Đặc tả nên yêu cầu ứng dụng chọn cấu trúc từ tập lựa chọn do mã nguồn kiểm soát, còn dữ liệu động chỉ đi vào các vị trí dữ liệu đã xác định. Đây là cách làm giảm số ngữ cảnh mà đội phát triển phải chứng minh an toàn.

## 8. Lưu dữ liệu gốc, encode tại ranh giới đầu ra

### 8.1. Vì sao không encode trước khi lưu

Một trường `displayName` có thể được dùng trong trang HTML, API JSON, thông báo văn bản hoặc tệp xuất. Nếu lưu sẵn bản HTML-encoded, mọi nơi sử dụng sau đó đều phải hiểu một quyết định dành riêng cho HTML.

Ví dụ:

```text
Dữ liệu nghiệp vụ:       R&D <Ops>
Bản lưu sai mục đích:    R&amp;D &lt;Ops&gt;
```

Khi template tiếp tục escape bản lưu thứ hai, nguồn HTML trở thành:

```html
R&amp;amp;D &amp;lt;Ops&amp;gt;
```

Người xem thấy entity thay vì chuỗi nghiệp vụ. Một lập trình viên có thể tắt escaping để chữa triệu chứng; khi dữ liệu mới chưa encode đi vào cùng luồng, ranh giới bảo mật bị mất.

Thiết kế thông thường nên giữ dữ liệu gốc theo hợp đồng nghiệp vụ, rồi áp dụng biểu diễn phù hợp ở từng đầu ra. Nếu hệ thống thực sự lưu một loại dữ liệu HTML đã xử lý, loại dữ liệu đó phải được phân biệt rõ với văn bản thuần.

### 8.2. “Encode một lần” phải gắn với một lần diễn giải

Không nên viết yêu cầu “mỗi chuỗi chỉ được encode một lần trong suốt vòng đời”. Một chuỗi có thể được đưa ra nhiều đầu ra khác nhau. Vấn đề là mỗi ranh giới phân tích cần đúng cách biểu diễn, không phải đếm tổng số lần gọi hàm.

Ví dụ:

- Chuỗi gốc đưa vào template HTML: template escape theo vị trí HTML.
- Cùng chuỗi gốc đưa vào `textContent`: truyền trực tiếp như văn bản.
- Cùng chuỗi gốc làm giá trị tham số URL: dựng tham số theo quy tắc URL, rồi xử lý vị trí chứa URL nếu render trong HTML.

Không gọi decoder để đoán một chuỗi “đã an toàn” hay “đã encode”. Chuỗi literal `&lt;` có thể chính là nội dung người dùng muốn thảo luận trong tài liệu kỹ thuật. Tự động decode nó sẽ đổi ý nghĩa dữ liệu.

### 8.3. Tránh mô hình đánh dấu an toàn bằng chuỗi thường

Một ứng dụng có thể cần phân biệt văn bản thuần với HTML đã được tạo từ nguồn kiểm soát. Nếu chỉ dùng `String` cho mọi thứ và một cờ `isSafe`, các nơi gọi dễ truyền nhầm.

Ở mức yêu cầu thiết kế, có thể quy định đường render HTML có chủ ý phải nhận một loại dữ liệu riêng hoặc một API riêng do thành phần chịu trách nhiệm tạo ra. Cơ chế cụ thể tùy nền tảng, nhưng phải tránh để bất kỳ chuỗi nào cũng có thể tự khai là an toàn mà không qua điều kiện rõ ràng.

## 9. Văn bản thuần và rich text là hai hợp đồng khác nhau

Xét hai trường trong cùng biểu mẫu:

| Trường | Hợp đồng sản phẩm | Hành vi mong muốn với `<strong>Gấp</strong>` |
| --- | --- | --- |
| Tiêu đề yêu cầu | Văn bản thuần | Hiển thị nguyên chuỗi, bao gồm dấu `<` và `>` |
| Nội dung mô tả định dạng | Chỉ cho phép một tập HTML được xác định | Có thể hiển thị chữ đậm nếu `strong` thuộc chính sách được phép |

HTML encoding toàn bộ nội dung rich text sẽ làm mất hiệu ứng định dạng; render raw toàn bộ lại cho người gửi quyền cung cấp cấu trúc không giới hạn. Vì vậy, rich text cần một chính sách sanitization phù hợp với sản phẩm: thẻ nào, thuộc tính nào, URL nào được giữ lại và thành phần nào chịu trách nhiệm xử lý.

Khi chuyển một giá trị giữa hai loại trường, cần xét lại hợp đồng. Một đoạn HTML đã được chấp nhận để hiển thị trong phần nội dung không tự nhiên an toàn khi đưa vào thuộc tính, JavaScript, CSS hoặc một tài liệu có cấu trúc khác.

Trong phạm vi bài này, quyết định quan trọng là nhận diện đúng các trường văn bản thuần và buộc chúng đi qua cơ chế render văn bản. Không mở đường render HTML chỉ để đáp ứng nhu cầu nhập dấu ngoặc nhọn hoặc dấu nháy.

## 10. Tiêu chí nghiệm thu và dữ liệu kiểm thử đại diện

### 10.1. Xác minh kết quả mà người dùng và trình duyệt nhận được

Một kiểm thử hữu ích cần quan sát cả nội dung hiển thị và cấu trúc DOM. Chỉ tìm chuỗi `&lt;` trong response chưa đủ: có thể dữ liệu ở sai ngữ cảnh, bị encode hai lần hoặc được mã giao diện parse lại sau đó.

Với một trường văn bản thuần được render trong phần tử `p`, có thể xác định các điều kiện:

1. `textContent` của phần tử đích khớp giá trị đầu vào theo hợp đồng chuẩn hóa đã công bố.
2. Đầu vào không làm xuất hiện phần tử hay thuộc tính ngoài cấu trúc template.
3. Các ký tự nháy không thoát khỏi một thuộc tính văn bản được quote.
4. Luồng cập nhật giao diện sau khi gọi API vẫn giữ cùng hành vi.
5. Các ký tự Unicode hợp lệ được giữ nguyên theo hợp đồng dữ liệu.

Đối với HTML, một số ký tự như ký tự xuống dòng có thể chịu quy tắc chuẩn hóa của parser; do đó cần dùng giá trị mong đợi đã định nghĩa cho những trường hợp đó, thay vì giả định mọi chuỗi byte đều được bảo toàn tuyệt đối.

### 10.2. Bộ dữ liệu mẫu

| Dữ liệu | Điều cần quan sát khi hiển thị như văn bản |
| --- | --- |
| `Nguyễn Ánh` | Tiếng Việt đúng, không xuất hiện ký tự thay thế |
| `R&D` | Dấu `&` hiển thị đúng |
| `<strong>Gấp</strong>` | Không tạo phần tử `strong` từ đầu vào |
| `"Vai trò" và 'quyền'` | Dấu nháy hiển thị đúng; không phá thuộc tính văn bản |
| `&lt;đã nhập nguyên văn&gt;` | Giữ nguyên ý nghĩa chuỗi literal, không tự decode thành nội dung khác |
| Chuỗi rỗng | Hành vi trống đúng thiết kế |
| Chuỗi ở giới hạn độ dài hợp lệ | Không bị cắt khiến dữ liệu hoặc output sai hợp đồng |
| `Phê duyệt 🔐` | Ký tự ngoài ASCII vẫn hiển thị đúng |

Không đưa mọi dữ liệu mẫu vào mọi ngữ cảnh rồi mong một encoder bảo vệ tất cả. Bộ kiểm thử cần tách vùng văn bản HTML, thuộc tính văn bản, URL và các đường render khác theo đúng yêu cầu thiết kế.

### 10.3. Kịch bản nghiệm thu cho dữ liệu đã lưu

```text
Given:
  Người dùng A có quyền nhập tiêu đề yêu cầu dưới dạng văn bản thuần.
  Người dùng B có quyền xem danh sách yêu cầu.

When:
  A lưu tiêu đề chứa <strong>Gấp</strong> và các dấu nháy.
  B mở trang danh sách bằng luồng render ban đầu.
  B tiếp tục tải hoặc lọc dữ liệu bằng luồng cập nhật giao diện.

Then:
  Cả hai luồng hiển thị nguyên tiêu đề theo hợp đồng văn bản.
  Không xuất hiện phần tử strong hay thuộc tính mới do tiêu đề tạo ra.
  Dữ liệu lưu trữ vẫn là giá trị nghiệp vụ gốc.
```

Kịch bản này quan trọng vì rủi ro thường nằm ở trang của người xem khác, không chỉ ở phản hồi tức thời cho người nhập. Nếu có trang quản trị, trang in hoặc HTML email, cần lập các tiêu chí riêng cho những đầu ra thuộc phạm vi sản phẩm đó.

### 10.4. Bằng chứng cần gắn với yêu cầu

Bằng chứng có thể gồm template áp dụng escaping, vị trí cập nhật DOM, kết quả render đầu ra và kiểm thử hành vi theo các luồng đại diện. Mỗi bằng chứng phải chỉ được nó xác nhận yêu cầu nào.

Một kiểm thử đơn vị cho hàm encoder chứng minh quy tắc chuyển đổi ký tự của hàm; nó chưa chứng minh mọi template gọi đúng hàm. Một kiểm thử đầu cuối cho trang danh sách chứng minh luồng đó; nó chưa bao phủ trang chi tiết hoặc trang lỗi. Độ bao phủ cần được theo dõi theo các vị trí render đã nhận diện.

## 11. Phân công trách nhiệm trong kiến trúc

HTML encoding hiệu quả khi được đặt vào thành phần có đủ thông tin về đầu ra. Một bộ lọc ở đầu API thường không biết chuỗi cuối cùng sẽ được đặt trong văn bản HTML, thuộc tính, URL hay một tệp xuất.

| Thành phần | Trách nhiệm liên quan |
| --- | --- |
| Nhóm đặc tả và thiết kế bảo mật | Phân loại trường dữ liệu, nhận diện vị trí render, đặt tiêu chí nghiệm thu |
| Lớp nghiệp vụ và lưu trữ | Bảo toàn giá trị theo hợp đồng dữ liệu, kiểm tra quyền và validation nghiệp vụ |
| Lớp template phía máy chủ | Bật escaping mặc định, đặt dữ liệu vào ngữ cảnh đã xác định |
| Mã giao diện phía trình duyệt | Dùng text sink cho văn bản và kiểm soát HTML sink |
| Thành phần rich text | Áp dụng chính sách HTML có chủ ý đã được phê duyệt |
| Nhóm kiểm thử | Xác minh cấu trúc DOM và nội dung qua các đường hiển thị đại diện |

Một dịch vụ trả JSON không nhất thiết phải HTML-encode mọi giá trị trong JSON. Nó cần tuân thủ hợp đồng JSON và cơ chế phân phối response; thành phần đưa giá trị vào HTML chịu trách nhiệm xử lý ngữ cảnh HTML đó.

Khi thay đổi giao diện từ render phía máy chủ sang dựng DOM phía trình duyệt, hoặc thêm một trang xuất báo cáo, các vị trí đầu ra thay đổi. Đây là thời điểm cần rà lại yêu cầu encoding, kể cả khi schema cơ sở dữ liệu và API không đổi.

## 12. Những lỗi thiết kế cần tránh

### 12.1. Tin dữ liệu chỉ vì nguồn mang nhãn nội bộ

Dữ liệu nội bộ có thể chứa nội dung nhập từ người dùng, đồng bộ từ nguồn ngoài hoặc dữ liệu đã lưu từ lâu. Nguồn nội bộ không thay cho việc đánh giá ngữ cảnh đầu ra.

### 12.2. Chỉ thay dấu `<`

Thay một ký tự không giải quyết tất cả vị trí chèn dữ liệu. Một dấu nháy có thể quan trọng trong thuộc tính dù không có dấu `<` nào. Cần chọn cơ chế theo ngữ cảnh, không theo ký tự được nghĩ đến đầu tiên.

### 12.3. Dùng URL encoding thay cho HTML encoding

Hai cơ chế phục vụ hai cú pháp khác nhau. Chuyển dữ liệu thành dạng phần trăm không phải hợp đồng hiển thị văn bản HTML; HTML-encode một URL cũng không xác nhận đích điều hướng được phép.

### 12.4. Tắt escaping vì giao diện hiển thị entity

Đây có thể là dấu hiệu dữ liệu đã encode trước khi đi vào template hoặc được encode rồi truyền vào `textContent`. Cần xác định lại hợp đồng dữ liệu và vị trí encode, thay vì bỏ lớp bảo vệ trên toàn bộ màn hình.

### 12.5. Dựa hoàn toàn vào CSP hoặc bộ lọc ở biên

Chính sách trình duyệt và bộ lọc có thể bổ sung khả năng phòng thủ nhưng không thay trách nhiệm giữ dữ liệu ở đúng vị trí. HTML không mong muốn vẫn có thể làm sai nội dung, liên kết hoặc cấu trúc trang ngay cả khi một hành vi thực thi bị chặn.

### 12.6. Cho rằng không chạy một mẫu script nghĩa là đã an toàn

Quan sát một hành vi không xảy ra không chứng minh đầu vào không làm đổi DOM. Kiểm thử cần xác nhận các thuộc tính tích cực của hợp đồng: nội dung được giữ như văn bản, cấu trúc không bị điều khiển và mọi đường render thuộc phạm vi áp dụng cơ chế đúng.

## 13. Áp dụng vào một quyết định thiết kế cụ thể

Đối với màn hình danh sách yêu cầu bảo mật, một quyết định có thể ghi:

```text
Dữ liệu: requirement.title.
Loại nội dung: văn bản thuần theo hợp đồng nghiệp vụ.
Nguồn: người dùng có quyền tạo hoặc sửa yêu cầu; dữ liệu được lưu và đọc lại.
Đầu ra: phần nội dung h2 ở trang danh sách và title của nút xem chi tiết.

Cách triển khai:
  - Template máy chủ escape theo từng vị trí đầu ra.
  - Luồng cập nhật phía trình duyệt dùng textContent cho nội dung tiêu đề.
  - Không dùng đường render raw HTML cho trường này.

Nghiệm thu:
  - Chuỗi có dấu <, >, &, nháy và tiếng Việt hiển thị đúng.
  - Dữ liệu không tạo thêm phần tử hay thuộc tính trong DOM.
  - Render lần đầu và cập nhật sau API có cùng bảo đảm.
  - Giá trị trong lưu trữ giữ đúng nội dung nghiệp vụ gốc.
```

Nếu sau này sản phẩm muốn tiêu đề hỗ trợ định dạng, đó là thay đổi hợp đồng nội dung cần được thiết kế lại. Không nên thực hiện bằng việc âm thầm đổi text sink thành HTML sink.

HTML encoding đạt mục đích khi người dùng có thể nhập và đọc các ký tự hợp lệ mà vẫn chỉ điều khiển dữ liệu của mình. Yêu cầu bảo mật phải giữ được ranh giới đó tại từng nơi dữ liệu đi vào HTML, đồng thời tạo bằng chứng đủ cụ thể để xác minh trong vòng đời phát triển.

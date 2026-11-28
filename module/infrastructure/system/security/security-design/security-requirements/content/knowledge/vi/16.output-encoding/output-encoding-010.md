# Reflected XSS

## 1. Mục tiêu và phạm vi

Reflected Cross-Site Scripting, thường gọi là reflected XSS, xảy ra khi dữ liệu do một request cung cấp được đưa trở lại đầu ra mà trình duyệt diễn giải thành nội dung có khả năng thực thi trong ngữ cảnh của ứng dụng. Dữ liệu thường xuất hiện trong cùng một lượt xử lý request và response, thay vì cần được lưu thành nội dung bền vững trước khi người khác xem.

Một ví dụ điển hình là trang tìm kiếm hiển thị lại từ khóa. Nếu ứng dụng ghép trực tiếp từ khóa vào HTML, người gửi có thể điều khiển không chỉ văn bản được hiển thị mà còn một phần cấu trúc hoặc mã của trang.

Trong module yêu cầu bảo mật, mục tiêu không dừng ở việc nhận biết một chuỗi đầu vào nguy hiểm. Cần chuyển rủi ro thành các yêu cầu cụ thể: nguồn dữ liệu nào có thể bị điều khiển, đầu ra nào tiếp nhận dữ liệu, ngữ cảnh phân tích là gì, thành phần nào chịu trách nhiệm bảo vệ và bằng chứng nào chứng minh yêu cầu đã được đáp ứng.

Sau bài này, người học có thể:

- Mô tả đường đi của một đầu vào phản chiếu từ request đến trình duyệt của người xem.
- Phân biệt reflected XSS với việc chỉ hiển thị lại dữ liệu hoặc chỉ tạo thêm markup.
- Xác định các điểm phản chiếu thường bị bỏ sót như trang lỗi và màn hình quản trị.
- Đặc tả yêu cầu encoding theo ngữ cảnh, lựa chọn text sink và kiểm soát đường render HTML.
- Thiết kế tiêu chí nghiệm thu cho cả render phía máy chủ và cập nhật DOM phía trình duyệt.

Phạm vi bài là ứng dụng web có đầu ra được trình duyệt diễn giải. Các mẫu dữ liệu kiểm chứng trong bài chỉ dùng cho môi trường kiểm thử được phép; chúng sử dụng dấu đánh dấu cục bộ, không thu thập hoặc gửi dữ liệu của người dùng.

## 2. Từ một tính năng bình thường đến ranh giới bảo mật

### 2.1. Chức năng tìm kiếm

Giả sử một nền tảng quản lý yêu cầu bảo mật có đường dẫn:

```text
GET /requirements/search?q=phân quyền
```

Trang kết quả hiển thị:

```text
Kết quả tìm kiếm cho: phân quyền
```

Việc hiển thị lại từ khóa giúp người dùng hiểu kết quả đang xem. Đây là hành vi hợp lệ và không cần bị loại bỏ để phòng chống XSS.

Rủi ro xuất hiện nếu mã dựng response như sau:

```java
String html = "<p>Kết quả tìm kiếm cho: " + query + "</p>";
```

Khi `query` là văn bản thông thường, lỗi khó nhận thấy. Nhưng nếu nó chứa cấu trúc HTML, trình duyệt không có thông tin để phân biệt cấu trúc do ứng dụng viết với cấu trúc đến từ request.

### 2.2. Những điều kiện tạo thành reflected XSS

Một luồng reflected XSS thường có các yếu tố:

1. Một bên có thể điều khiển dữ liệu của request mà người xem sẽ gửi.
2. Ứng dụng đưa dữ liệu đó vào đầu ra có thể được trình duyệt diễn giải.
3. Cách đưa dữ liệu vào đầu ra không giữ được ranh giới giữa dữ liệu và cú pháp thực thi.
4. Người xem mở hoặc kích hoạt luồng làm trình duyệt xử lý đầu ra đó.

Ứng dụng không cần lưu đầu vào vào cơ sở dữ liệu để các điều kiện này xuất hiện. Một trang tìm kiếm, trang lỗi hoặc màn hình xem trước có thể phản chiếu dữ liệu ngay trong response.

Một đường dẫn có sẵn dữ liệu đầu vào có thể khiến người xem gửi request chỉ bằng việc mở liên kết. Tuy nhiên, reflected XSS không chỉ giới hạn ở query parameter hoặc phương thức GET. Dữ liệu từ biểu mẫu POST và các nguồn request khác cũng cần được xét theo khả năng điều khiển và khả năng đưa request đến trình duyệt người xem.

### 2.3. Tài sản bị ảnh hưởng

Mã chạy trong ngữ cảnh của ứng dụng có thể tác động đến nội dung trang và những hành động mà phiên người dùng đang được phép thực hiện. Phạm vi thực tế phụ thuộc quyền của người xem, cấu hình trình duyệt, kiến trúc ứng dụng và các lớp bảo vệ khác.

Không nên mặc định tác động luôn là đọc cookie. Cookie có thể được cấu hình `HttpOnly`, nhưng mã trong trang vẫn có thể tương tác với DOM hoặc gửi các request cùng nguồn theo quyền của người dùng. Vì vậy, yêu cầu bảo mật cần bảo vệ ranh giới thực thi, thay vì chỉ bảo vệ một thuộc tính cookie.

## 3. Theo dõi nguồn, đường biến đổi và nơi sử dụng

### 3.1. Nguồn dữ liệu có thể bị điều khiển

Các nguồn cần xem xét gồm:

| Nguồn | Ví dụ phản chiếu hợp lệ | Điều cần xác định |
| --- | --- | --- |
| Query parameter | Từ khóa tìm kiếm, mã thông báo lỗi | Ai có thể tạo giá trị và đưa liên kết tới người xem |
| Trường biểu mẫu | Dữ liệu nhập lại sau khi validation thất bại | Giá trị có xuất hiện trong nội dung hoặc thuộc tính HTML không |
| Thành phần đường dẫn | Mã tài nguyên không tồn tại trên trang 404 | Dữ liệu có được hiển thị trong template lỗi không |
| Header hoặc cookie | Một giá trị được dùng trong trang chẩn đoán | Mức độ điều khiển thực tế và người nào sẽ xem response |
| Dữ liệu trình duyệt đọc từ URL | Giao diện hiển thị lại bộ lọc hoặc thông báo | Giá trị đi vào text sink hay HTML sink |

Không phải mọi header đều có thể được một website khác tùy ý gán trong trình duyệt người xem. Việc đánh giá nguồn phải dựa trên khả năng điều khiển thực tế; không suy ra một kịch bản khai thác hoàn chỉnh chỉ vì giá trị đi qua đối tượng request.

### 3.2. Dữ liệu có thể đi qua nhiều phép biến đổi

Một luồng đơn giản có thể là:

```text
Request parameter
    → giải mã tham số theo giao thức
    → kiểm tra nghiệp vụ
    → model của trang
    → template hoặc mã cập nhật DOM
    → trình duyệt phân tích đầu ra
```

Các phép xử lý như trim, đổi chữ hoa, giới hạn độ dài hoặc URL decoding không tự tạo bảo đảm an toàn cho HTML. Chúng có thể cần cho nghiệp vụ hoặc giao thức, nhưng chưa trả lời cách chuỗi được đưa vào ngữ cảnh đầu ra.

Ví dụ, một query được giới hạn 200 ký tự vẫn có thể làm thay đổi cấu trúc HTML. Giới hạn độ dài giảm phạm vi đầu vào và chi phí xử lý; nó không phải HTML encoder.

### 3.3. Nơi sử dụng quyết định yêu cầu bảo vệ

Một giá trị `query` có thể xuất hiện nhiều lần trên cùng trang:

```html
<p>Kết quả cho: GIÁ_TRỊ</p>
<input name="q" value="GIÁ_TRỊ">
<a href="/requirements/search?q=GIÁ_TRỊ">Tìm lại</a>
```

Ba vị trí có yêu cầu khác nhau. Vị trí thứ nhất là văn bản HTML. Vị trí thứ hai là thuộc tính văn bản có dấu nháy. Vị trí thứ ba chứa tham số URL trong thuộc tính HTML.

Yêu cầu “encode query” không cho biết vị trí nào đã được bảo vệ. Cần lập bản đồ từ mỗi nguồn dữ liệu tới từng nơi sử dụng cụ thể và quy định cơ chế theo ngữ cảnh đó.

## 4. Phân biệt các hiện tượng dễ nhầm

### 4.1. Phản chiếu dữ liệu không đồng nghĩa có lỗ hổng

Một trang hiển thị nguyên văn:

```text
Bạn đã tìm: <strong>phân quyền</strong>
```

trong khi DOM không tạo phần tử `strong` từ giá trị tìm kiếm có thể đang hoạt động đúng. Dữ liệu được phản chiếu nhưng vẫn giữ vai trò văn bản.

Muốn đánh giá an toàn, phải xem trình duyệt diễn giải dữ liệu thế nào, không chỉ tìm xem response có chứa lại đầu vào hay không.

### 4.2. HTML injection và XSS có liên quan nhưng không hoàn toàn đồng nhất

Nếu đầu vào `<em>kiểm tra</em>` làm xuất hiện một phần tử `em`, có bằng chứng dữ liệu đã trở thành markup ngoài hợp đồng văn bản thuần. Đây là lỗi đáng xử lý.

Tuy nhiên, chỉ có thêm thẻ `em` chưa tự chứng minh mã JavaScript có thể chạy. Khi báo cáo, cần phân biệt bằng chứng thay đổi cấu trúc HTML với bằng chứng thực thi mã. Cách phân biệt này giúp tránh cả đánh giá quá mức lẫn bỏ sót lỗi hợp đồng đầu ra.

### 4.3. Reflected, stored và DOM-based mô tả những khía cạnh khác nhau

| Khái niệm | Điểm nhận diện | Ví dụ |
| --- | --- | --- |
| Reflected XSS | Dữ liệu của request được đưa trở lại đầu ra, thường trong cùng lượt xử lý | Trang lỗi phản chiếu tham số của request |
| Stored XSS | Dữ liệu được lưu rồi đi tới người xem qua một luồng hiển thị sau đó | Bình luận đã lưu được render không an toàn |
| DOM-based XSS | Lỗi nằm trong luồng xử lý phía trình duyệt đưa dữ liệu tới nơi diễn giải nguy hiểm | Mã giao diện đọc URL rồi gán trực tiếp vào `innerHTML` |

Đây không phải các nhãn loại trừ nhau trong mọi cách phân tích. Một luồng có dữ liệu phản chiếu từ response vẫn có thể chỉ trở nên nguy hiểm khi mã phía trình duyệt đưa giá trị đó vào DOM sai cách.

Khi một giao diện tự đọc URL mà máy chủ không phản chiếu giá trị vào response, cần mô tả rõ đó là luồng phía trình duyệt. Không nên ép mọi lỗi liên quan URL vào cùng một cơ chế reflected phía máy chủ.

## 5. Chiến lược phòng vệ theo ngữ cảnh

### 5.1. Với nội dung văn bản HTML

Dữ liệu phải đi qua HTML text encoding hoặc được đưa vào một text node bằng API phù hợp. Ví dụ, nguồn HTML an toàn cho một query có markup có thể là:

```html
<p>Kết quả cho: &lt;em&gt;phân quyền&lt;/em&gt;</p>
```

Trình duyệt hiển thị các dấu `<` và `>` như ký tự, không tạo phần tử `em` từ đầu vào.

Đội phát triển nên ưu tiên auto-escaping của template để bảo vệ được áp dụng mặc định, thay vì phụ thuộc từng người nhớ gọi một hàm trước mỗi phép nối chuỗi.

### 5.2. Với thuộc tính văn bản

Tên thuộc tính phải do ứng dụng quyết định, giá trị phải nằm trong dấu nháy và được encode phù hợp với ngữ cảnh thuộc tính.

```html
<input name="q" value="GIÁ_TRỊ_ĐƯỢC_BIỂU_DIỄN_PHÙ_HỢP">
```

Không áp dụng quy tắc thuộc tính văn bản cho `onclick`, `style`, `srcdoc` hoặc URL tùy ý. Các thuộc tính này có thêm ngữ nghĩa có thể dẫn tới xử lý mã, HTML hoặc điều hướng.

### 5.3. Với URL

Cần dựng tham số URL bằng cơ chế dành cho URL, kiểm tra chính sách đối với đích điều hướng khi có dữ liệu điều khiển URL, rồi bảo vệ vị trí chứa URL trong HTML.

URL encoding không phải HTML encoding. Một giá trị được URL-encode trên đường truyền có thể được máy chủ decode trước khi render; nếu ứng dụng ghép trực tiếp kết quả decode vào HTML, rủi ro đầu ra vẫn còn.

### 5.4. Với JavaScript và CSS

Tránh đưa trực tiếp đầu vào request vào chuỗi mã, thuộc tính sự kiện hoặc CSS. Có thể thay bằng dữ liệu có cấu trúc qua một kênh phù hợp và sử dụng nó bằng API dữ liệu.

Một JSON serializer tạo JSON hợp lệ không tự bảo đảm chuỗi đó an toàn khi được nhúng trực tiếp vào mọi vị trí trong tài liệu HTML. Nếu cần nhúng dữ liệu, phải xác định đồng thời các lớp phân tích liên quan và dùng cơ chế được framework hỗ trợ cho vị trí đó.

Để giảm số giả định, nhiều luồng có thể trả dữ liệu qua API JSON riêng rồi để giao diện đưa trường văn bản vào text sink. Dù dùng cách nào, điểm đưa dữ liệu vào HTML vẫn cần được kiểm soát.

### 5.5. Với thao tác cập nhật DOM

Khi chỉ muốn hiển thị văn bản, dùng API nhận văn bản:

```javascript
const output = document.querySelector("#query-label");
output.textContent = query;
```

Không cần HTML-encode chuỗi trước khi gán vào `textContent`; làm vậy có thể khiến người dùng nhìn thấy entity thay vì văn bản gốc.

Ngược lại, ví dụ dưới đây yêu cầu trình duyệt phân tích chuỗi thành HTML:

```javascript
output.innerHTML = query;
```

Đối với một nhãn hiển thị query dạng văn bản thuần, việc đổi sang text sink loại bỏ nhu cầu dựng HTML động ở vị trí đó. Nếu sản phẩm thực sự cho phép HTML, cần một hợp đồng khác với chính sách sanitization được xác định rõ.

## 6. Đặc tả một bộ yêu cầu bảo mật cho luồng phản chiếu

### 6.1. Bắt đầu từ tình huống đe dọa

```text
Tác nhân có thể tạo một request chứa giá trị tìm kiếm do họ chọn và đưa
người dùng đã đăng nhập tới trang kết quả.

Ứng dụng cần hiển thị lại giá trị tìm kiếm. Giá trị này không được mở rộng
quyền của người tạo request thành quyền quyết định markup hoặc mã của trang
trong phiên người xem.
```

Mô tả này chỉ ra ranh giới cần giữ: được cung cấp dữ liệu tìm kiếm không đồng nghĩa được cung cấp chương trình chạy trong trang kết quả.

### 6.2. Yêu cầu nền tảng

```text
REQ-RXSS-01 — Bảo vệ dữ liệu phản chiếu tại đầu ra

Mọi dữ liệu có nguồn gốc từ request được đưa vào đầu ra HTML phải được
biểu diễn theo ngữ cảnh của từng vị trí sử dụng, hoặc được đưa qua API
an toàn dành cho kiểu dữ liệu đó.

Đối với trường được đặc tả là văn bản thuần, đầu vào không được tạo thêm
phần tử, thuộc tính hoặc mã thực thi ngoài cấu trúc do ứng dụng xác định.

Phạm vi bao gồm phản hồi thành công, validation thất bại, không tìm thấy
tài nguyên và các trang lỗi thuộc quyền kiểm soát của ứng dụng.
```

Một câu như “lọc các tham số XSS ở đầu request” không thay thế yêu cầu này. Cùng một giá trị có thể được dùng trong nhiều ngữ cảnh; thành phần nhận request thường không biết tất cả vị trí đầu ra về sau.

### 6.3. Các yêu cầu hỗ trợ theo kiến trúc

| Mã | Yêu cầu | Bằng chứng phù hợp |
| --- | --- | --- |
| REQ-RXSS-02 | Template HTML phải dùng escaping mặc định cho dữ liệu động và liệt kê các điểm bỏ qua escaping | Cấu hình template, danh mục điểm render raw và quyết định thiết kế |
| REQ-RXSS-03 | Nội dung văn bản phản chiếu được cập nhật bằng JavaScript phải dùng text sink hoặc cơ chế tương đương của framework | Vị trí cập nhật DOM và kết quả hiển thị |
| REQ-RXSS-04 | Thuộc tính văn bản nhận dữ liệu request phải có tên cố định, giá trị được quote và encode đúng ngữ cảnh | Template và cấu trúc DOM sau render |
| REQ-RXSS-05 | Luồng lỗi và middleware tạo response phải tuân thủ cùng hợp đồng đầu ra với luồng thành công | Các response lỗi đại diện và mã tạo response |
| REQ-RXSS-06 | Không lưu hoặc truyền bản HTML-encoded như thể đó là dữ liệu nghiệp vụ gốc dùng chung cho mọi đầu ra | Hợp đồng dữ liệu và đường đi tới các đầu ra |
| REQ-RXSS-07 | Mọi thay đổi tạo vị trí phản chiếu mới phải xác định nguồn, ngữ cảnh, thành phần bảo vệ và tiêu chí nghiệm thu | Hồ sơ thiết kế hoặc thay đổi của tính năng |

Mỗi yêu cầu nên có đội chịu trách nhiệm và phạm vi kiểm chứng. Nếu chưa xác định được nơi thực hiện, yêu cầu có nguy cơ trở thành một câu khuyến cáo mà không ai triển khai đầy đủ.

### 6.4. Các điều kiện không nên gộp vào một chỉ tiêu

Không dùng một chỉ tiêu duy nhất như “100% input đã escape”. Không phải mọi input đều đi vào HTML và không phải mọi vị trí HTML dùng cùng encoder.

Một chỉ tiêu có ý nghĩa hơn là tất cả vị trí phản chiếu đã được kiểm kê trong phạm vi chức năng đều có cơ chế xử lý phù hợp và bằng chứng nghiệm thu. Danh mục này phải được cập nhật khi thêm trang, template, trang lỗi hoặc mã dựng DOM.

## 7. Ví dụ Java với model và template

### 7.1. Tách dữ liệu khỏi quá trình tạo HTML

Ví dụ dưới đây minh họa controller Spring MVC nhận query và đưa dữ liệu gốc vào model. Nó chỉ phục vụ minh họa luồng hiển thị, chưa thực hiện nghiệp vụ tìm kiếm:

```java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class RequirementSearchController {

    @GetMapping("/requirements/search")
    public String search(
            @RequestParam(name = "q", defaultValue = "") String query,
            Model model) {

        model.addAttribute("query", query);
        return "requirement-search";
    }
}
```

Controller không tự nối `query` vào một chuỗi HTML và không HTML-encode trước khi đưa vào model. Ngữ cảnh đầu ra được xác định ở template.

Với template HTML dùng Thymeleaf, phần hiển thị có thể là:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Tìm yêu cầu bảo mật</title>
</head>
<body>
  <form method="get" th:action="@{/requirements/search}">
    <label for="q">Từ khóa</label>
    <input id="q" name="q" type="text" th:value="${query}">
    <button type="submit">Tìm</button>
  </form>

  <p>Kết quả cho: <span id="query-label" th:text="${query}"></span></p>
</body>
</html>
```

`th:text` được dùng để hiển thị văn bản; giá trị thuộc tính được đưa qua cơ chế xử lý thuộc tính của template. Đội triển khai phải giữ đúng chế độ template HTML và hành vi escaping của engine đang dùng.

Đổi `th:text` thành một đường render không escape làm thay đổi bảo đảm của trường. Việc đó không phải một thao tác định dạng vô hại khi dữ liệu đến từ request.

### 7.2. Validation vẫn có vai trò riêng

Một chức năng tìm kiếm có thể giới hạn độ dài query, chuẩn hóa khoảng trắng hoặc từ chối định dạng không đáp ứng nghiệp vụ. Các quy tắc này cần thiết cho tính đúng đắn và khả năng vận hành nhưng không thay escaping của template.

Nếu validation thất bại và trang nhập lại hiển thị chính giá trị bị từ chối, vị trí hiển thị đó vẫn phải được bảo vệ. Không được coi đầu vào là an toàn chỉ vì nó nằm trong trang thông báo lỗi.

### 7.3. Không dùng cơ chế encode toàn bộ response

Một HTML response chứa cả markup cố định lẫn dữ liệu động. HTML-encode toàn bộ response sẽ làm markup của ứng dụng biến thành văn bản. Nếu chỉ áp dụng một bộ lọc chung cho mọi chuỗi trong API, ứng dụng lại thiếu thông tin để biết chuỗi nào sẽ đi vào HTML, URL hoặc JSON.

Cách thiết kế phù hợp là gắn cơ chế bảo vệ với vị trí render hoặc API dựng đầu ra. Nhờ đó, mỗi thành phần chịu trách nhiệm cho ngữ cảnh mà nó thực sự biết.

## 8. Những đường phản chiếu thường bị bỏ sót

### 8.1. Trang không tìm thấy tài nguyên

Một trang 404 có thể hiển thị lại đường dẫn người dùng yêu cầu:

```text
Không tìm thấy tài nguyên: /requirements/giá-trị-từ-request
```

Nếu middleware hoặc máy chủ dựng phần này bằng nối chuỗi HTML, trang lỗi trở thành một điểm phản chiếu. Template chính của ứng dụng đã escaping đúng không bảo vệ được một trang lỗi được tạo bởi cơ chế khác.

### 8.2. Validation và thông báo lỗi

Các câu như “giá trị X không hợp lệ” thường chèn lại đầu vào. Một input bị từ chối ở lớp nghiệp vụ vẫn có thể gây rủi ro nếu thông báo lỗi render nó như HTML.

Yêu cầu phải bao gồm cả thông báo do ứng dụng tạo, thông báo được chuyển qua redirect và phần hiển thị lỗi ở giao diện. Cách chuyển thông báo không làm mất trách nhiệm xử lý ngữ cảnh cuối cùng.

### 8.3. Trang chẩn đoán hoặc quản trị

Việc người xem là nhân viên nội bộ không khiến dữ liệu request trở thành đáng tin. Những trang này có thể hiển thị đường dẫn, header hoặc tham số để hỗ trợ vận hành; từng giá trị vẫn cần được giữ dưới dạng dữ liệu.

Một màn hình quản trị có quyền cao còn có thể làm tăng tác động khi ranh giới thực thi bị phá vỡ. Phạm vi kiểm kê cần dựa vào nơi dữ liệu xuất hiện, không chỉ vào đối tượng người dùng được phép mở trang.

### 8.4. Hai đường render của cùng một tính năng

Trang tải lần đầu có thể được bảo vệ bởi template máy chủ, trong khi thao tác lọc sau đó gọi API và dựng DOM bằng JavaScript. Nếu chỉ nghiệm thu render lần đầu, đội phát triển có thể bỏ sót đường cập nhật phía trình duyệt.

Ngược lại, một giao diện dùng text sink đúng sau khi tải API chưa chứng minh template ban đầu đã xử lý đúng dữ liệu nhúng sẵn. Hai luồng cần được nhận diện theo kiến trúc thực tế.

## 9. Thiết kế kiểm chứng có thể quan sát

### 9.1. Không chỉ tìm chuỗi trong response

Một công cụ thấy tham số xuất hiện lại trong response mới chỉ phát hiện điểm phản chiếu. Cần biết chuỗi nằm trong văn bản HTML, thuộc tính, script, dữ liệu JSON hay nội dung được trả dưới một kiểu khác.

Một response JSON được serialize đúng và phân phối đúng loại nội dung không trở thành reflected XSS chỉ vì chứa ký tự `<`. Tuy nhiên, nếu giao diện lấy trường đó và đưa vào HTML sink, nguy cơ xuất hiện ở bước sử dụng tiếp theo.

Vì vậy, bộ tiêu chí phải quan sát cả response và kết quả trình duyệt khi luồng chức năng có xử lý phía client.

### 9.2. Các mức bằng chứng

| Mức quan sát | Chứng minh được | Chưa tự chứng minh được |
| --- | --- | --- |
| Response chứa đầu vào | Có điểm phản chiếu dữ liệu | Trình duyệt sẽ thực thi mã |
| Đầu vào tạo thêm phần tử hoặc thuộc tính | Hợp đồng dữ liệu và cấu trúc đã bị phá vỡ | Mọi dạng mã sẽ thực thi trong mọi cấu hình |
| Dấu đánh dấu kiểm thử được tạo bởi mã trong ngữ cảnh trang | Có thực thi trong điều kiện kiểm thử đã mô tả | Mọi tài khoản hoặc cấu hình triển khai có tác động giống nhau |
| Kiểm thử đầu ra đúng trên các đường render đã liệt kê | Các yêu cầu tương ứng có bằng chứng đạt | Những đường render chưa kiểm kê cũng an toàn |

Sự phân biệt này giúp báo cáo đúng phạm vi bằng chứng. Nó cũng giúp nghiệm thu phòng vệ mà không phụ thuộc vào một payload duy nhất.

### 9.3. Dữ liệu kiểm thử đại diện

| Dữ liệu | Kỳ vọng đối với trường văn bản thuần |
| --- | --- |
| `phân quyền` | Hiển thị đúng tiếng Việt |
| `R&D <Ops>` | Giữ nguyên ý nghĩa ký tự; không tạo phần tử từ đầu vào |
| `"kiểm tra" và 'vai trò'` | Không thoát khỏi giá trị thuộc tính được quote |
| `<em>kiểm tra</em>` | Hiển thị nguyên văn thay vì tạo thẻ `em` |
| `&lt;em&gt;` | Giữ đúng chuỗi literal do người dùng nhập; không tự decode thành một hợp đồng nội dung khác |
| Chuỗi rỗng | Hiển thị hoặc bỏ phần nhãn theo thiết kế sản phẩm |
| Chuỗi tại giới hạn độ dài hợp lệ | Không bị cắt sai hoặc làm hỏng output |
| `Quyền truy cập 🔐` | Giữ Unicode hợp lệ theo hợp đồng dữ liệu |

Các giá trị trên kiểm tra đặc tính đầu ra và tính đúng đắn. Nếu cần chứng minh khả năng thực thi trong một môi trường kiểm thử cô lập, có thể dùng một dấu đánh dấu cục bộ thay cho hành vi đọc cookie hoặc gửi request ra bên ngoài:

```html
<script>window.__reflectedXssProbe = "rfx-01";</script>
```

Đây là một giá trị thử nghiệm cho ngữ cảnh mà đầu vào có thể đi vào bộ phân tích tài liệu HTML. Nó không phải payload dùng chung cho mọi ngữ cảnh, và việc nó không chạy trong một luồng không chứng minh luồng đó đã an toàn.

Đối với trường văn bản thuần được bảo vệ đúng, chuỗi trên phải được giữ như dữ liệu: không tạo phần tử script từ đầu vào và không thiết lập dấu đánh dấu. Trước mỗi trường hợp cần làm sạch trạng thái kiểm thử để tránh nhầm dấu đánh dấu cũ với kết quả của request hiện tại.

### 9.4. Ví dụ tiêu chí nghiệm thu theo luồng

```text
Given:
  Trang tìm kiếm nhận q từ request.
  q được đặc tả là văn bản thuần và được hiển thị trong nhãn kết quả.

When:
  Người dùng mở trang bằng q chứa dấu ngoặc, nháy, dấu & và markup mẫu.

Then:
  Nội dung văn bản của nhãn khớp q theo hợp đồng chuẩn hóa đã công bố.
  Không có phần tử hoặc thuộc tính mới do q tạo ra.
  Giá trị trong ô tìm kiếm vẫn đúng theo hợp đồng của trường.
  Không có mã từ q được thực thi trong trang.
```

Nếu tính năng cập nhật không tải lại trang, cần bổ sung cùng điều kiện cho thao tác đó. Nếu validation thất bại và có trang nhập lại, trang đó cũng cần tiêu chí riêng.

Không đặt kỳ vọng mọi chuỗi byte phải giữ nguyên qua mọi parser. Một số ký tự có quy tắc chuẩn hóa hoặc bị hợp đồng dữ liệu từ chối. Tiêu chí cần chỉ rõ giá trị hợp lệ và kết quả chuẩn hóa dự kiến, thay vì để hành vi này ngầm định.

## 10. Tại sao những biện pháp quen thuộc chưa đủ

### 10.1. Chặn từ khóa nguy hiểm

Một blacklist tìm các từ như `script` không xác định được toàn bộ cấu trúc mà trình duyệt có thể diễn giải. Nó còn có thể chặn nội dung hợp lệ của tài liệu kỹ thuật mà vẫn không bảo vệ đúng ngữ cảnh thuộc tính hoặc các vị trí khác.

Nếu nghiệp vụ yêu cầu một tập đầu vào hẹp, allowlist có thể là validation hữu ích. Nhưng dữ liệu đã vượt validation vẫn cần được đưa vào đầu ra đúng cách.

### 10.2. Dùng POST thay cho GET

Phương thức POST có thể thay đổi cách request được tạo và chia sẻ nhưng không làm HTML parser an toàn hơn. Nếu response phản chiếu dữ liệu không đúng ngữ cảnh, lỗi đầu ra vẫn tồn tại.

Yêu cầu cần bảo vệ nơi phản chiếu thay vì coi một HTTP method là cơ chế encoding.

### 10.3. Chỉ dùng HttpOnly hoặc SameSite

`HttpOnly` giúp hạn chế việc JavaScript đọc cookie được gắn thuộc tính này. `SameSite` liên quan việc trình duyệt gửi cookie trong các tình huống giữa site. Chúng không xác định một chuỗi có trở thành mã trong tài liệu HTML hay không.

Các thuộc tính cookie vẫn cần được thiết kế theo mục tiêu của chúng, nhưng không thay yêu cầu phòng vệ XSS tại đầu ra.

### 10.4. Dựa hoàn toàn vào CSP hoặc bộ lọc ở biên

Một Content Security Policy phù hợp có thể hạn chế một số đường thực thi và giảm tác động. Bộ lọc ở biên cũng có thể hỗ trợ phát hiện hoặc chặn một số mẫu request.

Các biện pháp này không làm cho phép nối chuỗi HTML sai ngữ cảnh trở nên đúng. Nếu một mẫu kiểm thử không chạy do CSP, cần ghi nhận lớp bảo vệ đó đồng thời xác định liệu dữ liệu vẫn có tạo markup ngoài hợp đồng hay không.

Yêu cầu encoding và text sink phải có bằng chứng riêng. Một cấu hình chính sách có thể thay đổi giữa môi trường hoặc theo chức năng; không nên dùng nó làm bằng chứng duy nhất cho mọi vị trí phản chiếu.

### 10.5. Coi URL encoding trên liên kết là đã xử lý xong

Một liên kết có thể mang dữ liệu dưới dạng percent-encoding hợp lệ. Sau khi framework đọc tham số, ứng dụng nhận lại chuỗi ký tự dùng trong nghiệp vụ. Chính chuỗi này mới đi tới template.

Việc encode để truyền trên URL và việc biểu diễn khi render là hai ranh giới khác nhau. Không tự decode nhiều lần hoặc sửa dữ liệu tùy ý để đoán xem người gửi đã encode những gì; hãy xác định hợp đồng giao thức và ngữ cảnh sử dụng cuối cùng.

### 10.6. Đánh giá chỉ bằng một lần kiểm tra thủ công

Một trường hợp không tái hiện có thể do sai ngữ cảnh, trạng thái phiên, chính sách trình duyệt hoặc cách đưa dữ liệu vào trang. Nó chưa chứng minh mọi điểm phản chiếu đã được bảo vệ.

Nghiệm thu nên kết hợp kiểm kê luồng, cơ chế triển khai và quan sát đầu ra. Khi một mẫu thử thất bại, cần hiểu nguyên nhân thay vì diễn giải mọi kết quả âm tính thành an toàn.

## 11. Quản lý yêu cầu trong vòng đời phát triển

### 11.1. Gắn yêu cầu với tài sản và điểm phản chiếu

Một bản ghi ngắn cho trang tìm kiếm có thể gồm:

```text
Tài sản: phiên làm việc và tính toàn vẹn của giao diện người xem.
Nguồn dữ liệu: query parameter q.
Người có thể điều khiển: người tạo request hoặc liên kết tới trang tìm kiếm.
Điểm phản chiếu: nhãn kết quả và thuộc tính value của ô nhập.
Ngữ cảnh: văn bản HTML và thuộc tính văn bản được quote.
Biện pháp: escaping của template; text sink cho cập nhật phía trình duyệt.
Bằng chứng: template, vị trí cập nhật DOM và kết quả nghiệm thu theo luồng.
```

Từ đây có thể truy vết yêu cầu tới thành phần thực hiện và trường hợp kiểm chứng. Khi bổ sung một liên kết “tìm lại”, bản ghi phải thêm vị trí chứa URL và cơ chế xử lý tương ứng.

### 11.2. Xác định chủ sở hữu của các response ngoài luồng chính

Trang lỗi có thể do nhóm nền tảng, middleware hoặc dịch vụ biên quản lý. Nếu không giao trách nhiệm rõ, đội giao diện có thể cho rằng lỗi thuộc backend, còn backend lại cho rằng mọi HTML đều thuộc frontend.

Yêu cầu nên chỉ rõ thành phần nào tạo response và nhóm nào cung cấp bằng chứng. Các lớp khác nhau có thể dùng cơ chế triển khai khác nhau nhưng phải đáp ứng cùng hợp đồng giữ dữ liệu ở vị trí dữ liệu.

### 11.3. Quản lý ngoại lệ render HTML có chủ ý

Một tính năng xem trước HTML có thể cho phép markup theo thiết kế. Nó không nên được đánh giá bằng đúng hợp đồng văn bản thuần của query tìm kiếm.

Ngoại lệ cần mô tả nguồn nội dung, tập HTML được phép, cách sanitization hoặc cách cô lập được chọn và phạm vi quyền mà nội dung có thể tiếp cận. Một tên biến như `trustedHtml` hoặc một lời chú thích “đã kiểm tra” không đủ để cấp quyền render raw.

Nếu chưa có hợp đồng nội dung được phê duyệt, lựa chọn mặc định cho dữ liệu phản chiếu là hiển thị như văn bản tại những vị trí phù hợp.

### 11.4. Duy trì bằng chứng khi thay đổi kiến trúc

Những thay đổi như chuyển template engine, thêm tìm kiếm tức thời, dùng một thành phần rich text hoặc thay bộ xử lý lỗi có thể tạo vị trí phân tích mới mà API nghiệp vụ không thay đổi.

Do đó, tiêu chí hoàn thành thay đổi cần bao gồm việc cập nhật bản đồ nguồn và nơi sử dụng. Bằng chứng cũ chỉ còn giá trị trong phạm vi cơ chế render và ngữ cảnh mà nó đã xác nhận.

## 12. Đặc tả hoàn chỉnh cho một tính năng mẫu

Một đặc tả gọn cho trang tìm yêu cầu bảo mật có thể viết:

```text
Chức năng:
  Người dùng tìm yêu cầu bằng từ khóa q và xem lại từ khóa đã nhập.

Hợp đồng dữ liệu:
  q là văn bản thuần. Quy tắc độ dài và chuẩn hóa được định nghĩa bởi
  nghiệp vụ. Markup trong q không được hiểu là yêu cầu định dạng.

Phạm vi đầu ra:
  - Nhãn hiển thị từ khóa của trang kết quả.
  - Giá trị ô nhập trên trang kết quả và trang validation thất bại.
  - Luồng cập nhật kết quả không tải lại trang, nếu có.

Yêu cầu bảo mật:
  - Mỗi vị trí dùng cơ chế biểu diễn phù hợp với ngữ cảnh của nó.
  - Không đưa q vào đường render raw HTML hoặc chuỗi mã thực thi.
  - Cấu trúc phần tử và tên thuộc tính do ứng dụng quyết định.
  - Dữ liệu hợp lệ phải hiển thị đúng theo hợp đồng, gồm tiếng Việt.

Nghiệm thu:
  - Các ký tự có ý nghĩa HTML và dấu nháy không phá vỡ cấu trúc DOM.
  - Không có mã từ q được thực thi trong ngữ cảnh ứng dụng.
  - Render ban đầu, validation thất bại và cập nhật giao diện đều đạt.
  - Bằng chứng chỉ rõ template hoặc API DOM đang bảo vệ từng vị trí.
```

Reflected XSS được kiểm soát khi quyền cung cấp dữ liệu request không trở thành quyền cung cấp cấu trúc hay chương trình cho trang của người xem. Một yêu cầu bảo mật có thể kiểm chứng phải nối được nguồn dữ liệu, ngữ cảnh đầu ra, cơ chế bảo vệ và bằng chứng của từng luồng hiển thị.

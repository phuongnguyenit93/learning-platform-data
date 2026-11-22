# Tùy chỉnh bảng trong Asciidoctor

## 1. Vì sao cần tùy chỉnh bảng trong tài liệu REST API?

Spring REST Docs tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Ngoài request và response snippets, framework còn có thể tạo các bảng mô tả request fields, response fields, headers, parameters và hypermedia links. Những bảng này được viết dưới dạng AsciiDoc table, sau đó Asciidoctor xử lý để tạo HTML, PDF hoặc output khác.

Bảng mặc định thường đủ dùng, nhưng tài liệu API có thể cần điều chỉnh để dễ đọc hơn: cột mô tả rộng hơn cột tên field, nội dung code không bị xuống dòng quá nhiều, header nổi bật, viền bảng đồng nhất hoặc bảng dài có màu sọc xen kẽ. Asciidoctor cung cấp table attributes để định dạng các bảng đó.

Ví dụ một bảng response fields sinh từ REST Docs:

```asciidoc
|===
|Path |Type |Description

|id
|Number
|Mã sách

|title
|String
|Tên sách hiển thị cho người dùng
|===
```

Khi render, Asciidoctor chuyển cấu trúc bảng thành HTML hoặc PDF. Thuộc tính bảng có thể kiểm soát độ rộng cột, căn chỉnh, đường viền, header/footer và cách hiển thị nội dung.

## 2. Cấu trúc cơ bản của một table block

AsciiDoc dùng delimiter `|===` để mở và đóng bảng. Các thuộc tính đặt trong block attribute list ngay trước delimiter:

```asciidoc
[cols="1,3", options="header", stripes="even"]
|===
|Field |Description

|id
|Mã sách

|title
|Tên sách
|===
```

Các thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| `[cols="..."]` | Khai báo số cột và quy tắc độ rộng/kiểu cột. |
| `options="header"` | Đánh dấu hàng đầu là header. |
| `stripes="even"` | Áp dụng nền sọc cho các hàng theo lựa chọn. |
| `|===` | Delimiter bắt đầu/kết thúc table block. |
| `|Field` | Nội dung một cell; ký tự `|` bắt đầu cell. |

Trong snippet REST Docs, hàng đầu thường đã được tạo làm header. Khi include snippet sẵn có, không tự thêm một hàng header thứ hai nếu file đã chứa header.

## 3. Điều chỉnh độ rộng cột với `cols`

`cols` xác định số cột và độ rộng tương đối hoặc phần trăm. Với bảng REST Docs thường có cột tên, kiểu và mô tả, nên dành nhiều không gian cho cột mô tả.

### Độ rộng tương đối

```asciidoc
[cols="1,1,3", options="header"]
|===
|Path |Type |Description
|id |Number |Mã định danh duy nhất của sách
|title |String |Tên sách hiển thị trong danh sách và trang chi tiết
|===
```

Các số `1,1,3` là trọng số tương đối, không phải số ký tự. Cột thứ ba được phân bổ nhiều không gian hơn hai cột đầu.

### Độ rộng theo phần trăm

```asciidoc
[cols="20%,20%,60%", options="header"]
|===
|Path |Type |Description
|id |Number |Mã định danh duy nhất của sách
|title |String |Tên sách hiển thị cho người dùng
|===
```

Tỷ lệ phần trăm hữu ích khi muốn bố cục dễ dự đoán. Tổng tỷ lệ thường nên bằng 100% để tránh kết quả ngoài mong đợi.

### Kết hợp độ rộng và style của cột

Có thể gắn style cho từng cột trong column spec:

```asciidoc
[cols="1m,1,3", options="header"]
|===
|Path |Type |Description
|`id` |Number |Mã sách
|`publishedAt` |String |Thời điểm phát hành theo ISO-8601
|===
```

Style `m` thường dùng cho monospace. Các cột có thể có style khác như `a` (Asciidoc content) hoặc `l` (literal), tùy nội dung. Dùng style phù hợp để code/path dễ phân biệt với prose.

## 4. Chọn bảng tự co theo nội dung hay chiếm toàn chiều rộng

Asciidoctor hỗ trợ các tùy chọn liên quan cách bảng sử dụng không gian:

| Thuộc tính | Mục đích |
| --- | --- |
| `autowidth` | Để độ rộng bảng và cột dựa nhiều hơn vào nội dung, thay vì mặc định giãn hết vùng có thể dùng. |
| `width="100%"` | Yêu cầu bảng chiếm toàn bộ chiều rộng khả dụng. |
| `fit-content` | Tùy chọn bố cục cho bảng vừa với nội dung trong các backend hỗ trợ. |

Ví dụ bảng rộng toàn vùng:

```asciidoc
[cols="1,3", width="100%", options="header"]
|===
|Header |Description
|Authorization |Bearer token dùng để xác thực request
|If-None-Match |ETag client đang lưu để kiểm tra representation có thay đổi không
|===
```

Ví dụ bảng nhỏ gọn:

```asciidoc
[cols="1,1", options="header", autowidth]
|===
|Status |Meaning
|200 |OK
|404 |Not Found
|===
```

Không nên ép `autowidth` cho mọi bảng. Một cột chứa mô tả dài hoặc JSON path có thể khiến bảng rộng hơn trang, đặc biệt khi xuất PDF. Với bảng fields nhiều nội dung, phân bổ độ rộng tương đối và giữ mô tả xuống dòng thường dễ đọc hơn.

## 5. Header, footer và caption

Các thuộc tính bảng điều khiển hàng đầu, hàng cuối hoặc caption:

```asciidoc
.[Bảng 1] Các response fields của sách
[cols="1,1,3", options="header,footer"]
|===
|Path |Type |Description
|id |Number |Mã sách
|title |String |Tên sách
|Tổng |2 trường |Các field được document trong ví dụ này
|===
```

Một số lưu ý:

- `options="header"` cho biết hàng đầu là header.
- `options="footer"` đánh dấu hàng cuối là footer.
- Dòng caption có dạng `.[Nội dung caption]` và được đặt ngay trước block attributes/table.
- Không thêm `header` nếu snippet đã có cấu trúc header đúng; hãy kiểm tra nội dung file sinh ra trước khi bọc/định dạng.

Với các bảng do Spring REST Docs sinh, header thường chứa tên cột như `Path`, `Type`, `Description`. Nếu muốn đổi nhãn hoặc ngôn ngữ header, nên xem xét custom snippet template thay vì thêm header trùng lặp từ file tài liệu chính.

## 6. Định dạng đường viền và sọc hàng

Các thuộc tính `frame`, `grid` và `stripes` giúp bảng có thứ bậc thị giác nhất quán:

```asciidoc
[cols="1,1,3", options="header", frame="topbot", grid="rows", stripes="even"]
|===
|Path |Type |Description
|id |Number |Mã sách
|title |String |Tên sách
|publishedAt |String |Ngày phát hành
|===
```

| Thuộc tính | Giá trị thường dùng | Ý nghĩa |
| --- | --- | --- |
| `frame` | `all`, `topbot`, `sides`, `none` | Viền ngoài của bảng. |
| `grid` | `all`, `cols`, `rows`, `none` | Đường phân cách giữa các cell. |
| `stripes` | `none`, `even`, `odd`, `all` | Nền sọc cho các hàng. |

Chọn một kiểu nhẹ và nhất quán trên toàn bộ tài liệu. Ví dụ `frame="topbot"`, `grid="rows"` và `stripes="even"` có thể giúp bảng dài dễ theo dõi mà không quá nhiều đường kẻ. Cách render cụ thể còn phụ thuộc backend và stylesheet.

## 7. Căn chỉnh nội dung trong cột và cell

Có thể căn ngang theo cột với các ký hiệu trong column spec:

```asciidoc
[cols="^1,>1,<3", options="header"]
|===
|Status |Code |Description
|OK |200 |Request đã được xử lý thành công
|Created |201 |Tài nguyên mới đã được tạo
|===
```

Các ký hiệu căn chỉnh thường dùng:

| Ký hiệu | Căn chỉnh |
| --- | --- |
| `<` | Trái |
| `^` | Giữa |
| `>` | Phải |

Có thể đặt căn chỉnh dọc bằng `.`/`<`/`^`/`>` kết hợp với style ở cấp cột hoặc cell theo cú pháp AsciiDoc. Ví dụ cell có thể dùng cell specifier `.^|` hoặc `^|` để căn giữa theo chiều dọc, tùy trường hợp.

Đối với bảng API:

- Path, header name và JSON field thường căn trái.
- Status code hoặc giá trị ngắn có thể căn giữa hoặc phải.
- Cột mô tả dài nên căn trái để dễ đọc.

Không nên căn giữa toàn bộ mô tả dài vì mắt phải di chuyển khó hơn khi so sánh các hàng.

## 8. Áp dụng thuộc tính bảng cho snippet được include

Spring REST Docs sinh các snippet như `response-fields.adoc`, `request-fields.adoc`, `request-headers.adoc`, `path-parameters.adoc` và `links.adoc`. Các file này thường chứa AsciiDoc table hoàn chỉnh. Có thể thử đặt block attributes ngay trước include để áp dụng style cho bảng được include:

```asciidoc
=== Response fields
[cols="1m,1,3", options="header", frame="topbot", grid="rows"]
include::{snippets}/books-get/response-fields.adoc[]
```

Với một bảng query parameters:

```asciidoc
=== Query parameters
[cols="1m,1,3", options="header", stripes="even"]
include::{snippets}/books-list/query-parameters.adoc[]
```

Asciidoctor xử lý include trong bước tiền xử lý, vì vậy cần kiểm tra HTML/PDF sau render để xác nhận thuộc tính gắn với table block như mong muốn. Nếu snippet được sinh thành nội dung có cấu trúc block khác hoặc một phiên bản processor không áp dụng attributes qua vị trí include như dự kiến, hãy kiểm tra source sau expansion hoặc chuyển sang custom snippet template.

**Không sửa trực tiếp file trong `build/generated-snippets` hoặc `target/generated-snippets`.** Các file đó sẽ được tạo lại ở lần test tiếp theo. Nếu cần format mặc định riêng cho một loại snippet trong toàn dự án, giải pháp bền vững là custom snippet template hoặc bước hậu xử lý do build quản lý.

## 9. Tạo custom snippet template khi cần kiểm soát hoàn toàn

Khi thuộc tính đặt trước include chưa đủ đáp ứng, có thể tùy biến template snippet của Spring REST Docs để kiểm soát markup được sinh. Ví dụ muốn đổi nhãn cột, thêm caption, đổi thứ tự cột hoặc gắn table attributes thống nhất cho tất cả response-fields snippets.

Quy trình khái quát:

1. Xác định snippet cần tùy biến, chẳng hạn `response-fields`.
2. Sao chép template mặc định tương ứng từ đúng phiên bản Spring REST Docs đang dùng.
3. Đặt template trong thư mục tài nguyên test theo cơ chế template customization của module.
4. Thay đổi markup/attributes nhưng giữ nguyên các model values và escaping mà template cần render.
5. Chạy test để sinh snippet và kiểm tra file output.
6. Render Asciidoctor HTML/PDF để xác nhận bảng hiển thị đúng trên backend thực tế.

Không nên tự viết lại template chỉ để thay một thuộc tính trình bày đơn giản. Tùy biến template tăng trách nhiệm bảo trì khi nâng version Spring REST Docs; chỉ sử dụng khi cần format nhất quán mà include attributes không giải quyết được.

## 10. Ví dụ hoàn chỉnh cho API fields và headers

File `books-get.adoc` có thể trình bày:

```asciidoc
== Lấy sách theo ID

=== HTTP request
include::{snippets}/books-get/http-request.adoc[]

=== Path parameters
[cols="1m,1,3", options="header", stripes="even"]
include::{snippets}/books-get/path-parameters.adoc[]

=== HTTP response
include::{snippets}/books-get/http-response.adoc[]

=== Response fields
[cols="1m,1,3", options="header", frame="topbot", grid="rows"]
include::{snippets}/books-get/response-fields.adoc[]
```

Ví dụ này đặt style khác nhau cho bảng parameters và response fields. Bảng path parameters thường ngắn, còn response fields có mô tả dài nên dành nhiều độ rộng hơn cho cột cuối.

Với headers:

```asciidoc
=== Request headers
[cols="1m,1,3", options="header", stripes="even"]
include::{snippets}/books-create/request-headers.adoc[]

=== Response headers
[cols="1m,1,3", options="header", stripes="even"]
include::{snippets}/books-create/response-headers.adoc[]
```

Hãy chỉ include bảng đã được test sinh ra. Nếu không có header descriptor trong test, không có file tương ứng để include.

## 11. Khác biệt giữa HTML và PDF

Asciidoctor có thể render cùng một table block sang các backend khác nhau. HTML thường có thể sử dụng CSS để xử lý responsive layout, màu sọc và đường viền. PDF có giới hạn về khổ giấy, font và khả năng ngắt trang; một bảng có cột mô tả quá rộng hoặc nội dung code dài có thể bị tràn.

| Vấn đề | HTML | PDF |
| --- | --- | --- |
| Bảng rộng | Có thể cuộn hoặc điều chỉnh bằng CSS của site. | Có thể tràn lề hoặc co chữ quá nhỏ. |
| Nội dung dài | Trình duyệt có thể wrap text theo CSS. | Cần kiểm tra wrap và ngắt trang. |
| Màu sọc | Phụ thuộc stylesheet/theme. | Phụ thuộc PDF theme/backend. |
| Cột monospace | CSS có thể định dạng font code. | Cần font monospace có glyph phù hợp. |

Vì vậy, không chỉ nhìn source AsciiDoc để kết luận bảng đã đẹp. Hãy render output thực tế và kiểm tra các bảng dài, URI dài, JSON path dài và mô tả nhiều dòng.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Các cột có độ rộng không như mong muốn | `cols` dùng trọng số hoặc phần trăm chưa hợp lý. | Điều chỉnh tỉ lệ, render lại và kiểm tra nội dung dài. |
| Bảng bị tràn trang | `autowidth`, URI/path dài hoặc cột không được phân bổ phù hợp. | Dùng `width="100%"`, đặt lại `cols`, cân nhắc giảm nội dung hoặc chia bảng. |
| Header xuất hiện hai lần | Đã thêm header trong wrapper trong khi snippet đã có header. | Kiểm tra file snippet; chỉ dùng một hàng header. |
| Attributes không áp dụng cho snippet include | Include không được parse như table block tại vị trí đó hoặc snippet markup khác dự kiến. | Kiểm tra expanded source/output; dùng template tùy chỉnh nếu cần. |
| Sọc hàng không xuất hiện trong HTML | Theme/CSS ghi đè hoặc backend không thể hiện style như mong đợi. | Kiểm tra class/style HTML và stylesheet đang dùng. |
| PDF chữ bị nhỏ | Bảng quá rộng hoặc cột tỷ lệ không phù hợp. | Chỉnh `cols`, giảm cột hoặc dùng landscape/page layout khi hợp lý. |
| Chỉnh file generated nhưng lần sau mất | Snippet bị ghi đè khi test chạy. | Chỉnh test template hoặc file AsciiDoc nguồn, không sửa output generated. |
| Dùng sai column spec | Số spec không khớp số cột hoặc cú pháp style không đúng. | Đếm số cột và kiểm tra cú pháp AsciiDoc. |

## 13. Checklist thực hành

- [ ] Đã xác định bảng thuộc snippet nào: fields, headers, parameters hay links.
- [ ] Đã kiểm tra snippet nguồn để biết hàng header và số cột.
- [ ] `cols` có số cột khớp và phân bổ độ rộng phù hợp nội dung.
- [ ] Đã chọn width/autowidth phù hợp với HTML/PDF đích.
- [ ] Frame, grid và stripes được dùng nhất quán, không gây rối mắt.
- [ ] Header/footer/caption không bị lặp với nội dung snippet có sẵn.
- [ ] Căn chỉnh path/type/status/description giúp người đọc so sánh dễ dàng.
- [ ] Thuộc tính đặt trước include đã được kiểm tra trên output render thực tế.
- [ ] Nếu cần format ổn định hơn, đã cân nhắc custom snippet template thay vì sửa generated file.
- [ ] HTML/PDF cuối không có bảng tràn lề, cột quá hẹp hoặc nội dung khó đọc.

Asciidoctor cho phép điều chỉnh bảng bằng `cols`, `width`, `autowidth`, `frame`, `grid`, `stripes`, alignment và các thuộc tính header/footer. Với Spring REST Docs, hãy bắt đầu bằng việc áp dụng table attributes cho snippet được include và kiểm tra output render; chỉ tùy biến snippet template khi cần kiểm soát markup sâu hơn. Không sửa trực tiếp generated snippets, vì chúng là output được tạo lại từ HTTP tests.

## Tài liệu tham khảo

- [Asciidoctor – Tables](https://docs.asciidoctor.org/asciidoc/latest/tables/build-a-basic-table/)
- [Asciidoctor – Column Widths and Styles](https://docs.asciidoctor.org/asciidoc/latest/tables/assign-columns/)
- [Asciidoctor – Table Attributes](https://docs.asciidoctor.org/asciidoc/latest/tables/format-table/)
- [Spring REST Docs – Customizing Snippets](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)

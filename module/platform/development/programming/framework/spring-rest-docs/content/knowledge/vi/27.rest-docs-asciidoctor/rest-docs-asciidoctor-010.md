# Định dạng cột và tránh lỗi bảng

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Viết bảng AsciiDoc bằng table delimiter và column specification (colspec).
- Chọn tỷ lệ độ rộng cột bằng thuộc tính cols.
- Căn trái, giữa, phải và chọn kiểu hiển thị phù hợp cho từng cột.
- Cấu hình header, footer, frame, grid, width và autowidth.
- Xử lý ô dài, ô nhiều dòng, danh sách, code và ký tự pipe trong nội dung.
- Nhận diện lỗi số lượng ô, delimiter, cell span và nội dung làm vỡ cấu trúc bảng.
- Điều chỉnh bảng snippet Spring REST Docs bằng custom snippet template khi cần.

## 1. Bảng trong AsciiDoc dùng để làm gì?

Tài liệu REST API thường có bảng mô tả path parameter, query parameter, request/response header, JSON field, error code và media type. Bảng giúp người đọc so sánh nhanh các thuộc tính có cùng cấu trúc.

Ví dụ bảng query parameter:

```asciidoc
[options="header"]
|===
|Tên |Kiểu |Bắt buộc |Mô tả

|page
|integer
|Không
|Số trang bắt đầu từ 0.

|size
|integer
|Không
|Số phần tử tối đa trong một trang.

|sort
|string
|Không
|Trường và hướng sắp xếp, ví dụ createdAt,desc.
|===
```

Trong ví dụ:

- options="header" đánh dấu dòng đầu là header row.
- |=== mở và đóng table block.
- Mỗi dấu pipe ở đầu dòng bắt đầu một cell.
- Dòng trống giúp source dễ đọc và phân tách row; nó không tự tạo row rỗng.

## 2. Cấu hình độ rộng cột bằng cols

Thuộc tính cols xác định cấu trúc và tỷ lệ các cột:

```asciidoc
[cols="1,2,3",options="header"]
|===
|Field |Type |Description

|id
|integer
|Mã định danh duy nhất của đơn hàng.

|status
|string
|Trạng thái hiện tại, ví dụ PENDING hoặc COMPLETED.

|createdAt
|string
|Thời điểm tạo theo định dạng ISO 8601.
|===
```

Các số 1, 2 và 3 biểu thị tỷ lệ tương đối. Cột thứ ba được phân bổ rộng gấp ba lần cột thứ nhất và rộng gấp 1,5 lần cột thứ hai, trong phạm vi chiều rộng bảng. Chúng không phải số pixel hay phần trăm tuyệt đối.

### 2.1. Chọn tỷ lệ theo nội dung

| Loại nội dung | Tỷ lệ gợi ý | Lý do |
| --- | --- | --- |
| Tên field ngắn, type ngắn, description dài | 1,1,3 | Dành nhiều không gian cho mô tả |
| Mã lỗi, HTTP status, ý nghĩa | 1,1,3 | Cột ý nghĩa thường chứa câu dài |
| Tên header và quy tắc | 1,3 | Header ngắn, phần giải thích dài |
| Bước, hành động, kết quả | 1,2,3 | Cột kết quả thường cần nhiều chữ |
| Các cột có nội dung tương đương | 1,1,1 | Phân bổ đều để so sánh |

Đây là điểm khởi đầu. Hãy render bảng ở kích thước trang thực tế và điều chỉnh theo nội dung dài nhất, không chỉ dựa trên số ký tự trung bình.

### 2.2. cols với phần trăm

```asciidoc
[cols="20%,25%,55%",options="header"]
|===
|Field |Type |Description
|id |integer |Mã định danh.
|createdAt |string |Thời điểm tạo theo ISO 8601.
|===
```

Khi dùng phần trăm, tổng độ rộng nên phù hợp với chiều rộng bảng. Tỷ lệ tương đối như 1,2,3 thường linh hoạt hơn khi bảng được render ở nhiều kích thước; phần trăm hữu ích khi cần kiểm soát bố cục rõ ràng.

## 3. Căn lề cột

Colspec có thể bổ sung ký hiệu căn lề:

- Dấu nhỏ hơn căn trái.
- Dấu mũ căn giữa.
- Dấu lớn hơn căn phải.

Ví dụ:

```asciidoc
[cols="<1,^1,>2",options="header"]
|===
|Field |Required |Description
|id |Yes |Mã định danh.
|page |No |Số trang.
|total |Yes |Tổng số phần tử.
|===
```

Cột đầu căn trái, cột thứ hai căn giữa và cột cuối căn phải. Phần số vẫn thể hiện tỷ lệ tương đối.

| Nội dung | Căn lề thường phù hợp |
| --- | --- |
| Tên field, tên header, description | Trái |
| HTTP status, mã ngắn, Yes/No | Giữa hoặc trái |
| Số lượng, phần trăm, thời lượng | Phải |
| JSON path hoặc code | Trái, có thể dùng monospace |

Không căn giữa toàn bộ bảng chỉ để tạo cảm giác cân đối. Nội dung kỹ thuật thường dễ quét hơn khi văn bản căn trái và số căn phải.

## 4. Chiều rộng bảng, frame và grid

```asciidoc
[cols="1,3",options="header",width="100%",frame="topbot",grid="rows"]
|===
|Header |Description
|Authorization |Bearer token của caller.
|X-Request-Id |Mã truy vết request.
|===
```

| Thuộc tính | Ý nghĩa |
| --- | --- |
| width | Chiều rộng bảng, thường dùng phần trăm |
| frame | Đường viền ngoài: all, sides, topbot hoặc none |
| grid | Đường phân cách cell/row: all, cols, rows hoặc none |
| options="header" | Dòng đầu là header |
| options="footer" | Dòng cuối là footer |
| options="autowidth" | Bảng tự co theo nội dung |
| options="stretch" | Bảng kéo giãn theo vùng chứa trong môi trường hỗ trợ |

Giá trị frame/grid có thể được theme hoặc converter diễn giải khác nhau. Hãy xác minh trên output HTML/PDF mà dự án phát hành.

### 4.1. Khi nào dùng autowidth?

autowidth phù hợp với bảng nhỏ:

```asciidoc
[options="header,autowidth"]
|===
|Status |Ý nghĩa
|200 |Thành công
|404 |Không tìm thấy
|===
```

Bảng có mô tả dài thường không phù hợp autowidth vì các cột có thể bị nén hoặc giãn theo nội dung. Với bảng field/description, hãy đặt cols và width có chủ đích.

## 5. Cấu hình kiểu hiển thị của cột và cell

Colspec có thể điều khiển kiểu nội dung:

| Style | Mục đích |
| --- | --- |
| a | AsciiDoc cell, cho phép nội dung AsciiDoc và block |
| e | Emphasis, nhấn mạnh nội dung cell |
| s | Strong, hiển thị nội dung đậm |
| m | Monospaced, phù hợp code/identifier |
| l | Literal, hiển thị nội dung dạng nguyên văn |
| v | Verse, giữ cách ngắt dòng dạng verse |

Ví dụ cột đầu hiển thị monospace:

```asciidoc
[cols="1m,3",options="header"]
|===
|Field path |Description
|customer.id |Mã khách hàng.
|createdAt |Thời điểm tạo.
|===
```

Có thể kết hợp tỷ lệ, căn lề và style:

```asciidoc
[cols="<1m,^1,3",options="header"]
|===
|Field |Required |Description
|id |Yes |Mã định danh.
|updatedAt |No |Thời điểm cập nhật.
|===
```

Cột đầu căn trái và dùng monospace; cột thứ hai căn giữa; cột mô tả dùng phần không gian lớn hơn. Không lạm dụng style cho mọi cell.

## 6. Cell nhiều dòng và nội dung dài

Một cell có thể chứa nội dung nhiều dòng. Với nội dung đơn giản, tiếp tục cùng cell đến khi gặp dấu pipe mở cell mới ở đầu dòng:

```asciidoc
[cols="1,3",options="header"]
|===
|Header |Description
|Authorization
|Bearer access token của caller.
Token phải được gửi qua TLS và không ghi vào log.

|X-Request-Id
|Mã truy vết dùng để đối chiếu log.
|===
```

Khi cell cần nhiều đoạn, danh sách hoặc block, dùng AsciiDoc cell với prefix a|:

```asciidoc
[cols="1,3",options="header"]
|===
|Field |Description

|Authorization
a|
Header xác thực của request.

* Scheme: Bearer.
* Bắt buộc với endpoint được bảo vệ.
* Không chia sẻ token thật trong log.

|X-Request-Id
a|
Mã truy vết request.

Có thể dùng mã này khi liên hệ đội hỗ trợ.
|===
```

Cell kiểu a| cho phép block AsciiDoc như paragraph và list. Nó hữu ích khi nội dung cell không còn là một dòng văn bản đơn giản.

### 6.1. Nội dung code trong cell

Với code ngắn, dùng inline formatting hoặc monospace cell:

```asciidoc
[cols="1,3",options="header"]
|===
|Header |Ví dụ
|Authorization |`Bearer <access-token>`
|Accept |`application/json`
|Content-Type |`application/problem+json`
|===
```

Nếu cell cần code block nhiều dòng, dùng AsciiDoc cell:

```asciidoc
[cols="1,3",options="header"]
|===
|Trường |Ví dụ request

|Authorization
a|
----
Authorization: Bearer <access-token>
----

|Content-Type
a|
----
Content-Type: application/json
----
|===
```

Giữ code block trong cell ngắn và có mục đích. Với ví dụ request/response dài, đặt snippet bên ngoài bảng thay vì tạo bảng chứa toàn bộ HTTP exchange.

## 7. Escape dấu gạch đứng trong nội dung

Dấu pipe là ký tự cấu trúc để bắt đầu cell. Nếu nội dung cần chứa chính ký tự này, phải escape để Asciidoctor không hiểu nó là ranh giới cell mới.

Ví dụ mô tả biểu thức logic:

```asciidoc
[cols="1,3",options="header"]
|===
|Field |Description
|filter
|Có thể dùng toán tử status \| priority theo cú pháp minh họa của API.
|===
```

Trong nội dung bảng, viết dấu gạch chéo ngược trước pipe để biểu diễn ký tự đó. Kiểm tra output nếu bảng có nhiều tầng include hoặc cell chứa literal/code block.

Một cách khác là dùng entity HTML &#124; khi nội dung đang được xử lý như text và cần biểu diễn pipe. Ưu tiên escape theo cú pháp AsciiDoc trong source để người bảo trì nhận ra ý định.

### 7.1. Dấu pipe trong regex hoặc code

Một regex có pipe bên trong:

```text
^(GET|POST|DELETE)$
```

Khi đặt trong cell, escape các pipe:

```asciidoc
[cols="1,3",options="header"]
|===
|Pattern |Ý nghĩa
|`^(GET\|POST\|DELETE)$` |Chỉ chấp nhận một trong ba HTTP method.
|===
```

## 8. Gộp và tách cell

AsciiDoc hỗ trợ cell span theo hàng hoặc cột. Ví dụ một cell trải qua hai cột:

```asciidoc
[cols="1,1,2",options="header"]
|===
|Field |Type |Description
2+|Request metadata
|id |integer |Mã định danh.
|status |string |Trạng thái.
|===
```

Cell 2+| chiếm hai cột trên cùng row. Điều này hữu ích cho nhóm nội dung hoặc tiêu đề phụ, nhưng không nên lạm dụng.

Một cell có thể span nhiều row:

```asciidoc
[cols="1,1,2",options="header"]
|===
|Resource |Method |Purpose
.2+|Orders
|GET
|Đọc đơn hàng.
|POST
|Tạo đơn hàng.
|Users
|GET
|Đọc hồ sơ người dùng.
|===
```

Cell span làm số cell được khai báo trong row không còn giống số cột vật lý. Kiểm tra kỹ cấu trúc và HTML output; row thiếu hoặc thừa cell có thể làm dữ liệu lệch cột.

## 9. Header, footer và hàng tiêu đề

Bảng có thể có header row:

```asciidoc
[options="header"]
|===
|HTTP status |Meaning
|200 |Success
|400 |Invalid request
|404 |Resource not found
|===
```

Có thể có footer row khi cần tổng kết:

```asciidoc
[options="header,footer"]
|===
|Metric |Value
|Endpoints |12
|Documented scenarios |28
|Total |40
|===
```

Footer hữu ích cho dòng tổng, nhưng không nên dùng để lặp lại header hoặc chèn kết luận dài. Với bảng mô tả API, header row rõ ràng thường quan trọng hơn footer.

## 10. Tổ chức bảng cho tài liệu REST API

| Bảng | Cột gợi ý | Lưu ý |
| --- | --- | --- |
| Path/query parameters | Name, Type, Required, Description | Mô tả default, format và ví dụ |
| Request/response headers | Header, Required, Description | Phân biệt header client gửi và server trả |
| JSON fields | Path, Type, Optional, Description | Phân biệt optional với nullable |
| Error catalog | Status, Code, Description | Tên code phải khớp response thực tế |
| Multipart parts | Part, Media type, Required, Description | Phân biệt file part với JSON metadata |
| Links | Relation, Target, Description | Mô tả quan hệ điều hướng |

Không nhồi mọi thông tin vào một bảng nhiều cột. Nếu mô tả quá dài, tách bảng định danh và đoạn giải thích riêng.

### 10.1. Bảng field có description dài

```asciidoc
[cols="2,1,1,4",options="header",width="100%"]
|===
|JSON path |Type |Required |Description
|id |integer |Yes |Mã đơn hàng do server cấp. Client không tự tạo hoặc sửa giá trị này.
|status |string |Yes |Trạng thái vòng đời đơn hàng. Giá trị hợp lệ được liệt kê trong phần Order status.
|note |string |No |Ghi chú tùy chọn của người tạo. Độ dài tối đa và quy tắc ký tự cần theo validation của API.
|===
```

Nếu description là đoạn nhiều câu, dùng AsciiDoc cell a| để tạo paragraph hoặc list. Không ép bảng thành một hàng cực rộng nếu tài liệu được đọc trên màn hình nhỏ.

## 11. Bảng snippet do Spring REST Docs sinh

Spring REST Docs sinh nhiều snippet dạng AsciiDoc, ví dụ request-fields, response-fields, request-headers, response-headers và bảng parameter. Các snippet này thường có table markup do template mặc định tạo ra.

Tác giả có thể include trực tiếp:

```asciidoc
=== Response fields
include::{snippets}/orders-get/response-fields.adoc[]
```

Bảng snippet được tạo từ descriptor trong test. Không chỉnh file generated-snippets sau mỗi lần test vì file sẽ được sinh lại.

Nếu bảng mặc định không phù hợp, có hai hướng:

1. Điều chỉnh layout trang xung quanh snippet, đặt đoạn giải thích trước/sau bảng.
2. Cấu hình custom snippet template để kiểm soát table markup mà REST Docs sinh ra.

### 11.1. Custom snippet template

Spring REST Docs cho phép tùy biến template snippet theo cơ chế template engine của integration. Với snippet dạng bảng, template có thể định nghĩa cols, options, frame, grid và cấu trúc cell.

Một phần template AsciiDoc minh họa:

```asciidoc
[cols="2,1,4",options="header",width="100%"]
|===
|Path |Type |Description

// Các dòng cell được render từ model của snippet template.
|id |integer |Mã định danh.
|status |string |Trạng thái hiện tại.
|===
```

Đây chỉ là ví dụ layout tĩnh. Template thực tế phải lặp qua model của snippet, escape nội dung cell và xử lý cell thiếu/null đúng cách. Không copy ví dụ tĩnh làm template hoạt động nếu chưa thêm phần render dữ liệu.

Khi tùy biến template:

- Giữ tên file snippet mà trang AsciiDoc đang include hoặc cập nhật include đồng bộ.
- Giữ dữ liệu lấy từ descriptor, không hard-code nội dung field.
- Escape ký tự có ý nghĩa cú pháp AsciiDoc, đặc biệt dấu pipe.
- Kiểm tra description nhiều dòng và code path.
- Chạy documentation test để sinh lại snippet từ template.

## 12. Những lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Cột bị lệch | Số cell trong row không khớp cấu trúc cols | Kiểm tra delimiter và cell span ở từng row |
| Dấu pipe làm vỡ bảng | Nội dung chưa escape pipe | Viết dấu gạch chéo ngược trước pipe hoặc dùng cách biểu diễn literal |
| Cột description quá hẹp | Tỷ lệ cols chưa phù hợp | Tăng weight của cột mô tả hoặc dùng width phù hợp |
| Bảng tràn trang | Có chuỗi dài không ngắt hoặc quá nhiều cột | Giảm cột, tăng vùng mô tả, ngắt nội dung hoặc tách bảng |
| Nội dung nhiều dòng bị biến thành cell khác | Dòng tiếp diễn bắt đầu bằng pipe | Chỉ đặt pipe ở đầu cell mới; dùng a| cho block |
| Danh sách trong cell không render | Cell không dùng AsciiDoc style | Dùng a| cho cell chứa block |
| Code trong cell bị diễn giải | Cell dùng kiểu mặc định và inline syntax không phù hợp | Dùng monospace/literal cell hoặc delimit code rõ |
| Bảng snippet bị ghi đè sau build | Sửa trực tiếp generated-snippets | Sửa custom template hoặc AsciiDoc source |
| Include đúng nhưng bảng vẫn xấu | Template mặc định không kiểm soát layout | Dùng custom snippet template và render lại |

## 13. Quy trình kiểm tra bảng

Khi một bảng bị vỡ layout, kiểm tra từ cấu trúc đến giao diện:

1. Đếm số cột trong cols và số cell thực tế trên từng row.
2. Kiểm tra cell span có làm thay đổi số cell vật lý không.
3. Tìm dấu pipe trong description, regex, code hoặc URL.
4. Kiểm tra cell nhiều dòng: dòng tiếp diễn không được mở cell mới ngoài ý muốn.
5. Đổi cell thành a| nếu cần list hoặc block AsciiDoc.
6. Điều chỉnh tỷ lệ cols và width theo cột có nội dung dài nhất.
7. Render HTML/PDF ở kích thước trang dự kiến và xem bảng có tràn hoặc chữ quá nhỏ không.
8. Nếu bảng được sinh từ REST Docs, xác định file là generated output hay custom template trước khi sửa.

Không chỉ kiểm tra source AsciiDoc. Một bảng có thể hợp lệ về cú pháp nhưng vẫn khó đọc ở PDF hoặc màn hình hẹp.

## 14. Checklist định dạng bảng

- [ ] Table block mở và đóng bằng delimiter chính xác.
- [ ] Header row được khai báo nếu bảng cần tiêu đề cột.
- [ ] Colspec phản ánh số cột và tỷ lệ nội dung.
- [ ] Cột description có đủ độ rộng cho câu dài.
- [ ] Căn trái/giữa/phải theo kiểu dữ liệu.
- [ ] Width, frame và grid phù hợp với theme.
- [ ] Pipe trong nội dung đã escape.
- [ ] Cell nhiều đoạn/list/code block dùng AsciiDoc cell khi cần.
- [ ] Row span/col span có số cell hợp lệ.
- [ ] Không ép file binary hoặc HTTP exchange dài vào table cell.
- [ ] Snippet generated được tùy biến qua template, không sửa output tạm.
- [ ] HTML/PDF được render và kiểm tra trước khi phát hành.

## 15. Bài tập thực hành

Bạn cần tài liệu hóa response của endpoint GET /api/orders/{id}. Response có các field id, status, createdAt, customer và items. Description của customer và items dài hơn các field còn lại.

Hãy thực hiện:

1. Tạo bảng bốn cột: JSON path, Type, Required và Description.
2. Đặt tỷ lệ cột sao cho description rộng nhất; render và điều chỉnh lại.
3. Căn trái path/type, căn giữa required nếu kết quả vẫn dễ quét.
4. Dùng một AsciiDoc cell chứa danh sách cho mô tả items.
5. Thêm dòng header và kiểm tra heading/TOC xung quanh bảng.
6. Đưa biểu thức có dấu pipe vào description và escape chính xác.
7. Include response-fields snippet do REST Docs sinh; so sánh layout mặc định với custom template.
8. Build HTML/PDF và kiểm tra bảng ở kích thước trang thực tế.

**Câu hỏi tự kiểm tra:** Nếu bảng AsciiDoc render thành công nhưng cột Description chỉ rộng bằng cột Type, nên sửa snippet output sau khi build hay điều chỉnh nguồn tạo bảng? Với bảng tự viết, sửa cols trong AsciiDoc. Với bảng Spring REST Docs sinh, điều chỉnh custom snippet template hoặc layout trang. Không sửa generated-snippets thủ công vì lần build sau sẽ ghi đè.

## Kết luận

Định dạng cột tốt giúp người đọc tra cứu parameter, header, JSON field và error catalog nhanh hơn. Dùng cols để kiểm soát tỷ lệ hoặc phần trăm, ký hiệu căn lề theo kiểu dữ liệu, và width/frame/grid/options để hoàn thiện bố cục. Với ô dài hoặc có danh sách/code, chuyển sang AsciiDoc cell để nội dung được phân tích đúng; escape dấu pipe để không làm vỡ row. Các bảng do Spring REST Docs sinh cần được điều chỉnh qua custom snippet template hoặc layout Asciidoctor, không sửa output tạm. Cuối cùng, render HTML/PDF ở kích thước thực tế và kiểm tra độ rộng, xuống dòng, cell span cùng các liên kết include trước khi phát hành.

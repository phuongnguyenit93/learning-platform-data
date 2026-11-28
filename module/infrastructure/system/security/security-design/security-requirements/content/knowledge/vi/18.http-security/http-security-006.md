# X-Content-Type-Options

## 1. Mục tiêu bảo mật: nội dung không được dùng sai vai trò

Một hệ thống web trả nhiều loại nội dung: trang HTML, JavaScript, CSS, JSON, tệp tải xuống và văn bản do người dùng tạo. Nếu metadata và cách trình duyệt sử dụng nội dung không phù hợp, dữ liệu dự kiến chỉ để đọc có thể bị đưa vào một ngữ cảnh thực thi.

**`X-Content-Type-Options`** là HTTP response header có giá trị chuẩn dùng trong thực tế là:

```http
X-Content-Type-Options: nosniff
```

Header này tham gia việc trình duyệt kiểm tra kiểu nội dung thay vì tùy tiện sử dụng tài nguyên như một kiểu khác. Trong thiết kế yêu cầu bảo mật, cần đặt nó cùng yêu cầu **trả `Content-Type` chính xác**, chứ không coi sự hiện diện của một chuỗi header là bằng chứng mọi nội dung đã an toàn.

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Content-Type-Options: nosniff

{"status":"ready"}
```

Response này mô tả dữ liệu JSON. Thêm `nosniff` không thực hiện xác thực, kiểm tra quyền đọc dữ liệu hoặc bảo vệ cách JavaScript của ứng dụng sử dụng giá trị sau khi parse.

Một yêu cầu tốt cần nói rõ tài nguyên nào được bao phủ, ai chịu trách nhiệm đặt MIME type, header phải có ở response nào và cách kiểm chứng hành vi trên trình duyệt được hỗ trợ. [OWASP HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html#x-content-type-options) khuyến nghị đặt đúng `Content-Type` và sử dụng `X-Content-Type-Options: nosniff`.

## 2. MIME type, sniffing và ngữ cảnh sử dụng

### 2.1. `Content-Type` mô tả biểu diễn được trả về

Các response thường gặp:

| Nội dung do hệ thống cung cấp | Ví dụ `Content-Type` |
| --- | --- |
| Trang HTML của ứng dụng | `text/html; charset=UTF-8` |
| JavaScript do ứng dụng phát hành | `text/javascript` |
| Stylesheet | `text/css` |
| Dữ liệu JSON | `application/json` |
| Ghi chú văn bản thuần | `text/plain; charset=UTF-8` |
| Tệp nhị phân tải xuống theo hợp đồng | Media type được phê duyệt hoặc `application/octet-stream` khi phù hợp |

Đây là ví dụ thiết kế, không phải danh sách duy nhất mọi MIME type hợp lệ. Đặc biệt, trình duyệt nhận diện một tập JavaScript MIME type; không kết luận mọi giá trị khác `text/javascript` đều sai chỉ từ bảng này.

`charset` và MIME type giải quyết hai câu hỏi khác nhau: nội dung thuộc loại gì và ký tự được biểu diễn thế nào. Không gắn `charset` tùy ý cho mọi định dạng hoặc mọi tệp nhị phân. Metadata phải phù hợp định dạng và byte thực tế.

### 2.2. MIME sniffing là hành vi của bên nhận

Trong lịch sử, trình duyệt có thể xem xét byte nội dung bên cạnh metadata để suy ra cách xử lý tài nguyên. Những khác biệt giữa kiểu server cung cấp và kiểu bên nhận sử dụng có thể gây vấn đề bảo mật. Bối cảnh và thuật toán liên quan được mô tả trong [WHATWG MIME Sniffing Standard](https://mimesniff.spec.whatwg.org/).

Ứng dụng không nên dựa vào việc trình duyệt “đoán đúng” để sửa một deployment bị gán sai MIME. Một bundle JavaScript trả như `text/plain` có thể bị chặn; cách sửa phù hợp là sửa pipeline phát hành hoặc mapping media type, không bỏ kiểm soát để tài nguyên lại chạy bằng cơ chế tương thích.

### 2.3. Cùng URL có thể được yêu cầu trong ngữ cảnh khác nhau

Một tài nguyên có thể được mở trực tiếp, tải bằng `fetch()`, dùng làm script hoặc dùng làm stylesheet. Những ngữ cảnh này không có cùng thuật toán xử lý.

Ví dụ:

```html
<script src="/user-content/note"></script>
<link rel="stylesheet" href="/user-content/note">
```

Nếu `/user-content/note` vốn là văn bản của người dùng, việc một trang khác tham chiếu nó không được làm hệ thống đổi response thành JavaScript hoặc CSS. Nguồn dữ liệu, MIME type và ngữ cảnh sử dụng phải được phân biệt trong mô hình đe dọa.

## 3. Hiểu đúng phạm vi của `nosniff`

### 3.1. Quy tắc chặn trong Fetch

Theo [WHATWG Fetch Standard, X-Content-Type-Options](https://fetch.spec.whatwg.org/#x-content-type-options-header), với `nosniff`, response bị chặn khi đích là script-like nhưng MIME type không phải JavaScript hoặc không xác định được; đích `style` yêu cầu MIME type có essence là `text/css`.

| Đích sử dụng | MIME type của response | Kết quả theo kiểm tra `nosniff` này |
| --- | --- | --- |
| Script-like | JavaScript MIME type hợp lệ | Không bị chặn chỉ bởi kiểm tra này |
| Script-like | `text/plain` | Bị chặn |
| Stylesheet | `text/css` | Không bị chặn chỉ bởi kiểm tra này |
| Stylesheet | `application/json` hoặc thiếu MIME phù hợp | Bị chặn |

“Không bị chặn bởi kiểm tra này” không đồng nghĩa chắc chắn tài nguyên sẽ chạy. CSP, CORS, các quy tắc của module script, lỗi cú pháp và nhiều điều kiện khác vẫn có thể ngăn tải hoặc thực thi.

Không suy rộng bảng thành một quy tắc chặn giống nhau cho mọi ảnh, tài liệu điều hướng hoặc mọi nội dung tải xuống. Yêu cầu đối với các ngữ cảnh đó cần dựa trên hành vi được hỗ trợ và được kiểm chứng riêng.

### 3.2. Header không sửa nội dung hoặc MIME type sai

Giả sử server trả nội dung HTML không đáng tin với:

```http
Content-Type: text/html; charset=UTF-8
X-Content-Type-Options: nosniff
```

Metadata vẫn nói đó là HTML. Header không biến nó thành văn bản thuần và không loại thẻ nguy hiểm. Nếu nghiệp vụ chỉ cho phép hiển thị ghi chú dạng text, phải trả và sử dụng nó như text; nếu cho phép HTML do người dùng tạo, cần chính sách sanitization và cô lập phù hợp.

Tương tự, nếu một endpoint không đáng tin có thể trả nội dung tùy ý dưới JavaScript MIME type, `nosniff` không biết nội dung đó do ai tạo. Không được coi giá trị `nosniff` là bằng chứng rằng chỉ mã do ứng dụng kiểm soát mới được thực thi.

### 3.3. Đây là response header

Client tự thêm:

```http
X-Content-Type-Options: nosniff
```

vào request không thay trách nhiệm của server đối với response. Header cũng không phải thuộc tính cookie, tham số của `Content-Type` hoặc một thiết lập được thay thế bằng thẻ HTML tùy ý.

Ứng dụng phải phát giá trị trên phản hồi mà trình duyệt thực sự nhận. Header nằm trong cấu hình nhưng bị proxy loại bỏ chưa đáp ứng yêu cầu.

## 4. Chuyển kiểm soát thành yêu cầu có thể nghiệm thu

### 4.1. Xác định tập response trong phạm vi

Với một nền tảng giả định, có thể chọn phạm vi:

- Response HTML và API được cung cấp cho trình duyệt.
- JavaScript, CSS và tài nguyên tĩnh do hệ thống phát hành.
- Văn bản hoặc tệp người dùng được hệ thống phục vụ.
- Response lỗi có nội dung do ứng dụng, gateway hoặc CDN tạo.
- Các đường cache và phân phối được client thực sự sử dụng.

Đây là profile của ví dụ, không phải tuyên bố mọi response HTTP đều phải có cùng `Content-Type`. Response không có body, chẳng hạn một số response 204 hoặc 304, cần được xử lý theo semantics của chúng; không ép thêm một loại nội dung giả chỉ để công cụ kiểm tra có trường để đọc.

Một tổ chức có thể chọn phát `nosniff` đồng nhất trên cả các response không có body để đơn giản vận hành. Tiêu chí về MIME của một biểu diễn vẫn phải phân biệt response có nội dung và trường hợp dùng metadata từ cache.

### 4.2. Bộ yêu cầu minh họa

| Mã | Yêu cầu | Bằng chứng nghiệm thu dự kiến |
| --- | --- | --- |
| XCTO-01 | Response trong profile phải có giá trị chuẩn `nosniff` tại biên client | Kiểm tra header response qua các đường phân phối |
| XCTO-02 | Response mang nội dung phải có MIME type đúng hợp đồng và dữ liệu | Đối chiếu endpoint, header, body và loại tài nguyên |
| XCTO-03 | Dữ liệu không đáng tin không được tự chọn MIME type có khả năng thực thi | Thử thay metadata upload hoặc đầu vào chọn định dạng |
| XCTO-04 | Script và CSS hợp lệ của ứng dụng vẫn hoạt động với `nosniff` | Ca dương trên tập trình duyệt được hỗ trợ |
| XCTO-05 | Tài nguyên text dùng trong ngữ cảnh script/style bị chặn theo kỳ vọng | Ca âm trong trình duyệt với fixture kiểm soát |
| XCTO-06 | Response lỗi và đường cache không làm mất profile | Các ca 4xx, 5xx, cache hit và revalidation |
| XCTO-07 | Các tầng không phát header trùng hoặc mâu thuẫn ngoài chính sách | Đọc toàn bộ header tại response cuối cùng |
| XCTO-08 | Thay đổi loại tài nguyên hoặc đường phân phối phải cập nhật bằng chứng | Kiểm tra sau thay đổi mapping, gateway hoặc CDN |

Yêu cầu chưa đủ rõ:

> Website phải chống MIME sniffing.

Yêu cầu cụ thể hơn:

> Mọi response mang nội dung trong profile HTTP của ứng dụng phải có `X-Content-Type-Options: nosniff` và media type đúng hợp đồng. Văn bản người dùng phải không được phục vụ dưới JavaScript hoặc stylesheet MIME type chỉ từ metadata client cung cấp. Tài nguyên hợp lệ phải tiếp tục hoạt động; tài nguyên text được tải trong ngữ cảnh script/style phải có kết quả chặn theo bộ trình duyệt hỗ trợ.

Điều kiện này liên kết mục tiêu bảo mật với cả kiểm tra cấu hình và hành vi người dùng. Nó cũng tránh nghiệm thu một deployment chặn nhầm toàn bộ JavaScript nhưng vẫn được đánh dấu đạt chỉ vì header có mặt.

## 5. Chọn MIME type từ nguồn được kiểm soát

### 5.1. Không tin trực tiếp metadata từ client

Giả sử hệ thống lưu một ghi chú text. Nếu client có thể gửi:

```json
{
  "content": "window.exampleMarker = true;",
  "responseContentType": "text/javascript"
}
```

và server phản chiếu `responseContentType` khi phục vụ ghi chú, header `nosniff` không khắc phục thiết kế đó. Server đã tự khai báo nội dung là JavaScript.

Yêu cầu phải quy định một trong những cách kiểm soát phù hợp: kiểu response cố định theo endpoint, mapping từ một danh sách định dạng cho phép hoặc quy trình xác định kiểu tệp theo chức năng. Không để query parameter, tên tệp hoặc header upload tự quyết định kiểu nội dung có quyền cao.

Tên phần mở rộng là một đầu vào có thể thay đổi. `/files/note.js` không tự chứng minh dữ liệu là mã do ứng dụng phát hành. Tương tự, một URL không có đuôi `.js` vẫn có thể phục vụ JavaScript hợp lệ nếu nó thuộc endpoint mã được kiểm soát và có media type phù hợp.

### 5.2. Tệp upload, preview và download cần hợp đồng riêng

Một nền tảng có thể cho phép tải xuống tệp nhị phân, preview ảnh hoặc hiển thị HTML đã được xử lý. Những tính năng này cần phân loại nội dung, chính sách hiển thị và quyền truy cập riêng.

Với tệp chỉ dành để tải xuống, có thể phối hợp media type phù hợp và `Content-Disposition: attachment` theo hợp đồng. Với nội dung chủ động không đáng tin, cần xem xét origin riêng, sanitization hoặc sandbox. Không dùng `nosniff` thay cho tất cả các lựa chọn đó.

Mẫu phản hồi tải xuống minh họa:

```http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="report-export.bin"
X-Content-Type-Options: nosniff
```

Đây không phải khuyến nghị đổi mọi tài nguyên thành `application/octet-stream`. Nếu ứng dụng cần chạy JavaScript hoặc áp dụng CSS, chúng phải được phục vụ đúng kiểu thay vì ép thành tải xuống.

## 6. Cú pháp và giá trị tại biên HTTP

Giá trị triển khai chuẩn hóa nên là:

```http
X-Content-Type-Options: nosniff
```

Tên header trong HTTP không phân biệt hoa thường; việc HTTP/2 hiển thị tên dạng chữ thường không phải lỗi. Giá trị `nosniff` cũng được kiểm tra không phân biệt hoa thường theo đặc tả, nhưng chọn một dạng chuẩn giúp vận hành và đối chiếu dễ hơn.

Các cấu hình sau không phải cách biểu đạt chính sách chuẩn của ví dụ:

```http
X-Content-Type-Options: true
X-Content-Type-Options: no-sniff
Content-Type: text/plain; nosniff
```

Không chỉ tìm substring `nosniff` trong một response. Ví dụ, nó có thể xuất hiện trong body hoặc trong một giá trị bị ghép không đúng chính sách.

Nếu ứng dụng và proxy cùng thêm header, client có thể thấy nhiều field hoặc một giá trị đã được ghép. Không kết luận mọi header trùng đều làm trình duyệt bỏ bảo vệ theo cùng cách; cách parse có quy tắc cụ thể. Tuy nhiên, profile triển khai có thể yêu cầu một giá trị rõ ràng, không trùng và không mâu thuẫn để tránh phụ thuộc vào thứ tự xử lý giữa các tầng.

Tiêu chí kiểm tra nên tách hai ý: giá trị có được user agent nhận diện theo chuẩn không, và response có tuân thủ quy tắc chuẩn hóa chặt hơn của sản phẩm không. Không gọi một vi phạm nội bộ về chuẩn hóa là bằng chứng trình duyệt chắc chắn đã thực thi mã trái phép.

## 7. Phân công trách nhiệm giữa ứng dụng và tầng phân phối

### 7.1. `Content-Type` và `nosniff` có thể do các tầng khác nhau quản lý

| Thành phần | Trách nhiệm minh họa |
| --- | --- |
| Ứng dụng | Chọn media type theo chức năng và nội dung thực tế |
| Kho tài nguyên tĩnh | Mapping MIME đúng với artifact được phát hành |
| Gateway hoặc reverse proxy | Giữ hoặc chuẩn hóa header theo profile tại biên |
| CDN | Phân phối đúng metadata cùng phiên bản body và biến thể cache |
| Thành phần tạo trang lỗi | Trả body lỗi và metadata nhất quán |
| Nhóm kiểm thử | Xác minh response client nhận và hành vi trình duyệt |

Không để proxy gán `Content-Type: text/html` cho mọi response chỉ để có một header thống nhất. MIME type phải phản ánh biểu diễn; JSON, CSS và tệp nhị phân không thể dùng chung một giá trị tùy tiện.

Một quyết định triển khai có thể chọn ứng dụng là nơi phát `nosniff`, hoặc chọn tầng biên làm nơi chuẩn hóa cho nhiều nguồn. Dù chọn cách nào, phải có người chịu trách nhiệm về response cuối cùng và các đường không đi qua tầng đó.

### 7.2. Response do proxy tạo có thể không qua ứng dụng

Các lỗi như body quá lớn, backend không sẵn sàng hoặc giới hạn tần suất có thể được tạo trước khi ứng dụng nhận request. Một filter trong Java không bao phủ những response này.

Vì vậy, danh mục nghiệm thu nên có response ứng dụng và response tại biên. Không suy rằng một ca `200 OK` từ controller chứng minh mọi response lỗi đã có header.

Tài nguyên tĩnh cũng có thể được CDN hoặc object storage phục vụ trực tiếp. Chính sách ở application server không tự thay đổi metadata của các đối tượng đã nằm ở nơi khác.

### 7.3. Tránh việc mất header khi sửa cấu hình cục bộ

Một thay đổi thêm header cache hoặc tạo location mới có thể ảnh hưởng kế thừa header bảo mật. Cần đánh giá cấu hình có hiệu lực, không chỉ tìm một directive ở block cha.

Khi nhiều nhóm quản lý nhiều tầng, nên ghi rõ tầng nào thêm, tầng nào giữ nguyên và tầng nào được phép thay thế. “Mỗi tầng đều thêm cho chắc” có thể tạo giá trị trùng khó đối chiếu mà vẫn không sửa lỗi MIME của body.

## 8. Ví dụ Java và Spring Security

### 8.1. Đặt đúng kiểu văn bản trước khi ghi body

Với Servlet, đoạn sau minh họa việc phục vụ một ghi chú đã qua kiểm tra quyền dưới dạng text:

```java
// Được đặt trong luồng xử lý đã xác minh quyền đọc ghi chú.
// Biến note là dữ liệu nghiệp vụ, không phải HTML đã được tin cậy.
response.setHeader("X-Content-Type-Options", "nosniff");
response.setContentType("text/plain");
response.setCharacterEncoding("UTF-8");
response.getWriter().write(note);
```

Cần đặt metadata trước khi response đã commit và trước khi lấy writer theo hợp đồng encoding của Servlet. Ví dụ chỉ minh họa phản hồi text; không cung cấp xác thực, phân quyền, giới hạn dung lượng hoặc toàn bộ xử lý lỗi.

Nếu endpoint thật sự trả JSON, nên dùng serializer JSON phù hợp và media type JSON thay vì nối chuỗi hoặc gắn nhãn text để né lỗi. Nếu dữ liệu này về sau được đưa vào giao diện HTML, phía sử dụng vẫn phải dùng cơ chế hiển thị text hoặc bảo vệ theo ngữ cảnh đích.

### 8.2. Header writer trong security filter chain

Spring Security Servlet có hỗ trợ Content Type Options trong hệ thống response header. Có thể biểu đạt cấu hình trong chain hiện có như sau:

```java
import org.springframework.security.config.Customizer;

// Trích đoạn trong cấu hình HttpSecurity hiện có.
http.headers(headers -> headers
        .contentTypeOptions(Customizer.withDefaults()));
```

Đây là trích đoạn cấu hình header, không phải một security configuration hoàn chỉnh. Cần đối chiếu phiên bản sử dụng và các chain thực tế của ứng dụng. Tài liệu về hỗ trợ này nằm tại [Spring Security Servlet: Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html#servlet-headers-content-type-options).

Một route không chạy qua chain chứa header writer sẽ không được bao phủ bởi writer đó. Cấu hình nhiều chain, bỏ qua tài nguyên hoặc tắt default headers có thể làm kết quả khác kỳ vọng. Không sửa bằng cách bỏ kiểm tra quyền của một route chỉ để header xuất hiện; cần giải quyết đúng phạm vi cấu hình.

Nếu endpoint và filter cùng quản lý header, phải kiểm tra kết quả hợp nhất tại response cuối cùng. Chọn trách nhiệm rõ ràng thay vì mặc định mọi cách thêm header đều tương đương.

## 9. Ví dụ NGINX và kế thừa cấu hình

Một directive minh họa trong block phù hợp:

```nginx
add_header X-Content-Type-Options nosniff always;
```

`always` giúp áp dụng việc thêm header không phụ thuộc vào tập status code giới hạn của `add_header` khi không dùng tham số này. Quy tắc kế thừa còn phụ thuộc các directive ở cấp con và cấu hình phiên bản đang chạy. Xem [NGINX ngx_http_headers_module](https://nginx.org/en/docs/http/ngx_http_headers_module.html#add_header).

Ví dụ một location có header riêng theo mô hình kế thừa thông thường cần được kiểm tra cùng header bảo mật:

```nginx
location /assets/ {
    add_header X-Content-Type-Options nosniff always;
    add_header Cache-Control "public, max-age=3600";
    # Các directive phục vụ tài nguyên thuộc cấu hình ứng dụng thực tế.
}
```

Không áp dụng đoạn cấu hình rời này như một cấu hình server hoàn chỉnh. Nó chưa xác định nguồn tài nguyên, TLS, mapping MIME hoặc chính sách proxy. Các phiên bản có cơ chế điều chỉnh kế thừa cần được đọc theo cấu hình có hiệu lực thay vì giả định cùng một hành vi ở mọi hệ thống.

`add_header` là thao tác thêm header, không phải bằng chứng tự động xóa một giá trị từ upstream. Nếu tầng biên được chọn làm nơi chuẩn hóa, cần thiết kế cách xử lý giá trị đã có và kiểm tra cả response do upstream lẫn proxy tạo.

Vấn đề MIME của `/assets/app.js` vẫn phải được sửa tại nơi xác định media type. Thêm `nosniff` chỉ có thể làm sự không tương thích trở nên rõ ràng hơn, chứ không biến một response HTML fallback thành JavaScript hợp lệ.

## 10. Cache, redirect và các response dễ bị bỏ sót

### 10.1. Cache phải gắn đúng metadata với đúng body

Một asset có body mới nhưng metadata cũ có thể bị chặn dù origin đã sửa. Khi thay media type hoặc chính sách phân phối, cần xem xét cache key, biến thể, thời hạn và cách cập nhật nội dung đã lưu.

Không chỉ kiểm tra cache miss. Cache hit ở CDN và dữ liệu được browser dùng lại có thể đi qua đường khác. Bằng chứng phải cho biết đang quan sát origin hay response thực sự được phân phối tới client.

Với response 304, trình duyệt dùng biểu diễn đã lưu và cập nhật metadata theo cơ chế cache. Không yêu cầu 304 phải chứa body hoặc media type giả như một response 200 mới. Ca kiểm thử nên quan sát kết quả tải thực tế sau revalidation, gồm thông tin của biểu diễn được dùng lại.

### 10.2. Redirect không truyền chính sách cho đích cuối

Một response 302 có `nosniff` không chứng minh tài nguyên cuối cùng cũng có. Nếu `/assets/app.js` chuyển hướng sang host CDN hoặc sang trang đăng nhập, cần kiểm tra response sau chuyển hướng.

Trường hợp phổ biến là một request script nhận HTML đăng nhập hoặc trang SPA fallback. Nếu bị chặn do MIME, cần xác định vì sao route tài nguyên trả sai nội dung; bỏ header có thể che một triệu chứng nhưng không sửa đường đi dữ liệu.

### 10.3. Lỗi có body cũng cần được phân loại

Một endpoint JSON khi thành công có thể trả JSON nhưng khi lỗi lại trả một trang HTML do tầng khác tạo. Điều này cần được công bố hoặc chuẩn hóa theo hợp đồng, nhất là với tài nguyên script/style.

Không bắt mọi body lỗi dùng cùng media type của response thành công nếu thực tế không cùng định dạng. Body lỗi HTML phải có kiểu phù hợp; đồng thời đường tải asset không được coi HTML lỗi là mã ứng dụng hợp lệ.

Nếu ứng dụng có service worker tạo hoặc biến đổi response, đường đó cũng cần được xem xét theo phạm vi. Kiểm tra chỉ tại origin không chứng minh mọi response được cung cấp từ cache ứng dụng có cùng metadata.

## 11. Nghiệm thu bằng HTTP và bằng hành vi trình duyệt

### 11.1. Hai lớp kiểm chứng khác nhau

Kiểm tra HTTP trả lời các câu hỏi: header có xuất hiện, giá trị là gì, Content-Type có đúng và tầng nào tạo response. Kiểm tra trình duyệt trả lời: một tài nguyên được dùng trong ngữ cảnh cụ thể có bị chặn hoặc hoạt động như kỳ vọng không.

Cả hai đều cần thiết. Một ảnh chụp DevTools có header không chứng minh mọi route đã được bao phủ. Một ca script không chạy cũng chưa chứng minh nguyên nhân là `nosniff`, vì CSP, lỗi mạng hoặc lỗi cú pháp có thể tạo cùng biểu hiện.

Không chỉ dùng request HEAD để đại diện mọi GET. Server hoặc lớp phân phối có thể tạo metadata khác nhau; khi kiểm tra tài nguyên, cần xác minh đường GET và body phù hợp, đồng thời xử lý các semantics không có body đúng cách.

### 11.2. Fixture script an toàn và có đối chứng

Trong môi trường kiểm thử được phép, có thể dùng nội dung vô hại:

```javascript
window.mimeProbeRuns = (window.mimeProbeRuns || 0) + 1;
```

Tạo hai response fixture có cùng body:

```text
Fixture A:
  Content-Type: text/javascript
  X-Content-Type-Options: nosniff

Fixture B:
  Content-Type: text/plain
  X-Content-Type-Options: nosniff
```

Khi tải như classic script trong một trang kiểm thử với điều kiện khác được kiểm soát, A là ca dương và B là ca âm. Cần quan sát header thực tế, lỗi tải hoặc thông báo MIME và biến đánh dấu trong từng ngữ cảnh sạch.

Không dùng việc module script bị chặn sai MIME để kết luận riêng tác dụng của header: module có các quy tắc MIME nghiêm ngặt của chính nó. Cũng không yêu cầu fixture bỏ header chắc chắn phải chạy trên mọi trình duyệt, vì các kiểm soát khác và hành vi hiện tại có thể vẫn ngăn nó.

Fixture không cần đọc cookie, gửi dữ liệu ra ngoài hoặc thực hiện hành vi nguy hiểm. Mục tiêu là chứng minh tài nguyên được dùng hay bị chặn trong đúng ngữ cảnh.

### 11.3. Fixture stylesheet

Có thể dùng một quy tắc CSS đơn giản làm đổi màu một phần tử đánh dấu. Response `text/css` là ca dương; cùng body được gắn `text/plain` và `nosniff` là ca âm khi tải như stylesheet.

Kiểm tra computed style và đường tải tài nguyên thay vì chỉ nhìn trang bằng mắt. Điều kiện trang kiểm thử phải cho phép stylesheet hợp lệ, tránh một CSP hoặc lỗi đường dẫn vô tình làm cả hai ca đều thất bại.

### 11.4. Ma trận nghiệm thu minh họa

Các ca sau là kế hoạch kiểm chứng, không phải báo cáo đã chạy trên một sản phẩm cụ thể:

| Ca | Điều kiện | Kết quả cần quan sát |
| --- | --- | --- |
| JSON đúng kiểu | API thành công trả JSON | Media type đúng và header chuẩn tại biên |
| Text do người dùng tạo | Ghi chú chứa chuỗi trông giống script | Phục vụ như text, không tự đổi thành mã |
| Script hợp lệ | Artifact do ứng dụng phát hành | Đúng JavaScript MIME type, tải được khi các điều kiện khác hợp lệ |
| Script sai kiểu | Fixture text được dùng làm classic script | Bị chặn theo kiểm tra MIME với `nosniff` |
| CSS hợp lệ | Stylesheet `text/css` | Style được áp dụng theo kỳ vọng |
| CSS sai kiểu | Cùng body nhưng `text/plain` | Không được áp dụng như stylesheet trong ca kiểm thử |
| Header sai giá trị | Giá trị `true` hoặc `no-sniff` | Phát hiện vi phạm profile, không chỉ kiểm tra tên header |
| Metadata do client điều khiển | Upload khai báo loại thực thi ngoài chính sách | Server không phản chiếu thành response có quyền thực thi |
| Lỗi ứng dụng | Response 4xx/5xx có body | MIME của body lỗi và header đúng profile |
| Lỗi tại biên | Proxy/CDN tạo body lỗi | Không mất chính sách do bỏ qua ứng dụng |
| Cache hit | Tài nguyên được trả từ cache | Metadata đúng với body được dùng |
| Revalidation | Browser nhận 304 và dùng lại body | Biểu diễn hiệu lực vẫn nhất quán |
| Redirect | Tài nguyên đi qua chuyển hướng | Đối chiếu response cuối, không chỉ hop đầu |
| Nhiều giá trị | App và proxy cùng phát header | Phát hiện trùng/mâu thuẫn theo quy tắc triển khai |
| Không có body | Response có semantics không mang nội dung | Không bị ép một Content-Type giả để vượt kiểm tra |

Tập trình duyệt và phiên bản được hỗ trợ cần được ghi trong bằng chứng. Hành vi được chứng minh ở một phiên bản không nên được mô tả như bảo đảm tuyệt đối cho mọi user agent, thư viện HTTP hoặc ứng dụng ngoài trình duyệt.

## 12. Các kiểm soát liên quan không được đánh đồng

| Kiểm soát | Câu hỏi chính |
| --- | --- |
| `Content-Type` | Biểu diễn này được công bố thuộc loại gì? |
| `X-Content-Type-Options` | Việc dùng tài nguyên theo kiểu MIME trong ngữ cảnh liên quan có được ràng buộc không? |
| Output encoding / sanitization | Dữ liệu không đáng tin có được biểu diễn hoặc làm sạch đúng ngữ cảnh không? |
| CSP | Trang được phép tải hoặc thực thi những nguồn nội dung nào theo chính sách? |
| CORS | Một số truy cập chéo origin từ trình duyệt có được phép đọc response không? |
| `Content-Disposition` | Nội dung được trình bày inline hay theo luồng tải xuống được chỉ định? |
| Xác thực và phân quyền | Chủ thể có được nhận hoặc thao tác với dữ liệu này không? |

Không dùng `nosniff` thay CORS hoặc phân quyền cho dữ liệu nhạy cảm. Một client không thực thi quy tắc trình duyệt vẫn có thể nhận byte nếu server cho phép. Header không mã hóa nội dung và không hạn chế một người đã tải được tệp lưu hoặc phân tích nó bằng công cụ khác.

Header cũng không ngăn mã ứng dụng tự diễn giải dữ liệu. Nếu một chuỗi lấy từ API được chuyển vào `eval()` hoặc đưa vào HTML bằng một sink không an toàn, đó là ranh giới sử dụng mới cần bảo vệ riêng.

Mục tiêu thiết kế là phối hợp các kiểm soát theo chức năng, không dùng một header làm nhãn “đã chống XSS” cho toàn hệ thống.

## 13. Triển khai và xử lý khi bật header làm hỏng chức năng

Nếu bật `nosniff` khiến JavaScript hoặc CSS không tải, nên điều tra media type và body thực tế. Các nguyên nhân có thể là mapping static resource sai, proxy trả trang lỗi, chuyển hướng đăng nhập, asset cũ trong cache hoặc route SPA fallback bắt nhầm đường tài nguyên.

Một quy trình xử lý theo yêu cầu đã thiết kế:

```text
Xác định tài nguyên và response cuối cùng
    -> đối chiếu body thực tế với Content-Type
    -> xác định thành phần tạo hoặc sửa metadata
    -> sửa mapping / route / artifact / cache theo nguyên nhân
    -> kiểm chứng ca dương và ca âm trong phạm vi bị ảnh hưởng
```

Không sửa bằng cách gắn `text/javascript` cho mọi nội dung đang bị chặn. Cách đó có thể cấp vai trò thực thi cho một response text hoặc lỗi không đáng tin. Nếu cần ngoại lệ tạm, phải giới hạn route, owner, thời hạn và biện pháp bù theo quy trình của sản phẩm.

Khi chuyển CDN, thêm loại tệp hoặc thay pipeline build, cần đánh giá lại cặp body–metadata tại đường phân phối. Bản vá ở origin chưa đủ nếu client vẫn nhận một biến thể cũ.

Theo dõi lỗi MIME có thể hỗ trợ phát hiện sai cấu hình, nhưng chỉ số “không có báo lỗi” không chứng minh header luôn có mặt. Cần các ca kiểm tra chủ động có phạm vi và dữ liệu inventory của tài nguyên, host và route liên quan.

## 14. Một hồ sơ yêu cầu gọn cho thiết kế HTTP

```text
ID: HTTP-XCTO-001
Tài sản: cách trình duyệt diễn giải nội dung do hệ thống phục vụ.

Đe dọa:
  Dữ liệu hoặc response sai MIME được dùng trong vai trò script/style;
  chính sách mất tại proxy, lỗi, cache hoặc đường phân phối khác.

Yêu cầu:
  - Response trong profile phải có giá trị nosniff tại biên client.
  - Nội dung phải có media type đúng và được server kiểm soát.
  - Client không tự chọn media type có khả năng thực thi cho dữ liệu
    vốn chỉ được phép dùng như text hoặc download.
  - Script/CSS hợp lệ tiếp tục hoạt động; ca sai kiểu bị chặn theo
    ngữ cảnh và tập trình duyệt đã xác định.

Phạm vi kiểm chứng:
  - Ứng dụng, static resource, nội dung người dùng và response lỗi.
  - Proxy/CDN, cache hit, revalidation và response sau redirect.
  - Header đầy đủ, MIME/body phù hợp và hành vi trình duyệt.

Giới hạn:
  Không thay thế phân quyền, output encoding, sanitization, CSP,
  bảo vệ upload hoặc chính sách cô lập nội dung chủ động.
```

Giá trị của `X-Content-Type-Options` đến từ việc ràng buộc cách dùng nội dung cùng với một hợp đồng MIME đúng. Khi yêu cầu nêu được phạm vi response, nguồn quyết định media type và bằng chứng hành vi, `nosniff` trở thành một phần kiểm soát HTTP có thể nghiệm thu thay vì một header chỉ được thêm để hoàn thành checklist.

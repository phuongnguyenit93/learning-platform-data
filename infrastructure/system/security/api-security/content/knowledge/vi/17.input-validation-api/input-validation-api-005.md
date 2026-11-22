# Validate header, content type và encoding

## 1. Vì sao phải kiểm tra header, content type và encoding?

HTTP request đi vào API không chỉ có body. Trước khi ứng dụng đọc JSON hoặc gọi service nghiệp vụ, nó đã nhận header, thông tin framing của HTTP, media type, content coding và các byte cần giải mã. Nếu gateway, proxy, web server và application diễn giải request khác nhau, attacker có thể khai thác sự không nhất quán để vượt qua kiểm soát bảo mật.

Validation ở lớp này giúp xác định request có đúng giao thức, đúng định dạng và nằm trong giới hạn mà API hỗ trợ hay không. Những lỗi phổ biến gồm:

- Header bị thiếu, lặp lại, quá dài, chứa ký tự không hợp lệ hoặc có giá trị mâu thuẫn.
- Client gửi Content-Type không được endpoint hỗ trợ nhưng server vẫn cố parse body.
- Request khai báo một charset nhưng body được mã hóa theo charset khác.
- Content-Encoding không được hỗ trợ hoặc payload nén giải nén thành dữ liệu khổng lồ.
- Proxy và backend hiểu khác nhau về Content-Length hoặc Transfer-Encoding.
- Dữ liệu Unicode có nhiều cách biểu diễn khiến validation, authorization, chữ ký và lưu trữ không nhất quán.
- Header định danh, tenant hoặc IP do caller tự khai được ứng dụng tin như dữ liệu đã xác minh.

Trong phạm vi **SECURITY_API_SECURITY**, kiểm tra header, content type và encoding là một phần của validation theo từng endpoint. HTTPS bảo vệ dữ liệu trên đường truyền nhưng không bảo đảm request có cấu trúc hợp lệ hoặc phù hợp với contract. Authentication xác minh caller nhưng không làm cho header tùy ý trở nên đáng tin cậy.

Sau bài học này, người học có thể:

1. Xác định header nào cần có, được phép, có thể lặp và phải có giới hạn.
2. Kiểm tra Content-Type, Accept và Content-Encoding theo contract của endpoint.
3. Phân biệt HTTP message framing với content coding.
4. Xử lý UTF-8, Unicode, percent-encoding và canonicalization nhất quán.
5. Giảm rủi ro request smuggling, parser differential và decompression bomb.
6. Thiết kế validation, phản hồi lỗi và negative tests cho các trường hợp header/body bất thường.

## 2. Phân biệt các lớp dữ liệu của HTTP request

Một request có nhiều lớp và mỗi lớp có quy tắc riêng:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Request line hoặc pseudo-headers | Xác định method, target và phiên bản/giao thức | POST /v1/orders |
| Header fields | Metadata và điều khiển request | Authorization, Content-Type |
| Message framing | Xác định ranh giới message/body trong giao thức | Content-Length, Transfer-Encoding |
| Content coding | Biến đổi biểu diễn body để truyền tải | Content-Encoding: gzip |
| Media type | Mô tả định dạng nội dung sau khi giải mã content coding | application/json |
| Character encoding | Ánh xạ byte thành ký tự trong một số định dạng văn bản | UTF-8 |
| Application schema | Cấu trúc dữ liệu và quy tắc trường | JSON Schema/DTO |

Cần tránh nhầm lẫn:

- Content-Type nói body thuộc định dạng nào.
- Content-Encoding nói body đã được mã hóa/nén bằng content coding nào.
- Transfer-Encoding trong HTTP/1.1 liên quan đến cách message được truyền/framing giữa các hop.
- Charset quy định cách giải mã byte thành ký tự trong một số media type.
- Schema quy định cấu trúc dữ liệu sau khi parser đã đọc đúng định dạng.

Ví dụ:

```http
POST /v1/orders HTTP/1.1
Host: api.example.com
Content-Type: application/json
Content-Encoding: gzip
Content-Length: 128

<compressed bytes>
```

Trong ví dụ, body được nén gzip; sau khi giải nén, nội dung là JSON. Content-Length ở HTTP/1.1 mô tả độ dài message content theo quy tắc framing của request đó, không phải số ký tự JSON sau giải nén.

Không nên cố xử lý body bằng JSON parser trước khi xác định framing, content coding và media type. Mỗi bước phải có giới hạn và một cách diễn giải thống nhất giữa các tầng.

## 3. Xác định contract header cho từng endpoint

Header có thể là bắt buộc, tùy chọn, do proxy thêm hoặc chỉ có ý nghĩa với một số operation. API cần định nghĩa rõ thay vì chấp nhận mọi giá trị rồi để từng controller tự suy đoán.

### 3.1. Phân loại header

| Nhóm | Ví dụ | Cách xử lý |
|---|---|---|
| Authentication | Authorization, X-API-Key | Xác minh bằng cơ chế bảo mật; không log giá trị |
| Content metadata | Content-Type, Content-Encoding | Kiểm tra theo media type/coding được hỗ trợ |
| Negotiation | Accept, Accept-Encoding | Chọn response representation phù hợp |
| Conditional request | If-Match, If-None-Match | Parse theo semantics của HTTP và endpoint |
| Idempotency | Idempotency-Key | Kiểm tra format, độ dài, scope và thời gian lưu |
| Correlation/tracing | traceparent, request ID | Parse theo chuẩn; giới hạn độ dài; không dùng làm identity |
| Proxy/network | Forwarded, X-Forwarded-For | Chỉ tin từ proxy đã cấu hình |
| Application-specific | X-Client-Version | Định nghĩa format, độ dài và ý nghĩa |
| Hop-by-hop | Connection, Transfer-Encoding | Để HTTP stack/proxy xử lý đúng giao thức; không tự chuyển tiếp tùy tiện |

### 3.2. Header bắt buộc và tùy chọn

Mỗi endpoint nên quy định header nào cần thiết. Ví dụ:

- Endpoint nhận JSON yêu cầu Content-Type: application/json.
- Endpoint upload yêu cầu media type multipart đã được hỗ trợ.
- Endpoint ghi có thể yêu cầu Idempotency-Key.
- Endpoint có optimistic locking có thể yêu cầu If-Match.
- Endpoint xác thực yêu cầu đúng credential scheme.

Nếu thiếu header bắt buộc, server trả lỗi phù hợp theo contract. Không tự đoán content type từ body hoặc từ phần mở rộng tên file khi API yêu cầu một định dạng cụ thể.

### 3.3. Allowlist có chủ đích

Không nhất thiết phải từ chối mọi header không biết đến vì proxy, tracing hoặc client library có thể thêm metadata hợp lệ. Tuy nhiên, endpoint cần allowlist cho các header ảnh hưởng đến bảo mật và nghiệp vụ.

Nên:

- Chỉ đọc các header mà endpoint thực sự sử dụng.
- Định nghĩa rõ header nội bộ nào được gateway thêm.
- Loại bỏ header identity do public client tự gửi trước khi tạo trusted context.
- Từ chối hoặc bỏ qua header application-specific không hợp lệ theo policy đã công bố.
- Không để một header lạ vô tình điều khiển role, tenant, routing, feature flag hoặc chế độ debug.

Header X-User-Id không phải bằng chứng danh tính. Nếu hệ thống dùng header nội bộ để truyền identity, gateway phải xác thực nguồn, xóa giá trị caller gửi và ghi đè bằng thông tin lấy từ token/session đã xác minh. Backend chỉ được tin header đó trên một trust boundary được bảo vệ.

## 4. Kiểm tra cú pháp, số lượng và kích thước header

Header là dữ liệu đầu vào không tin cậy. Trước khi sử dụng, cần áp dụng giới hạn ở ingress và application.

Các giới hạn thường cần xác định:

- Tổng kích thước header của một request.
- Số lượng header fields.
- Độ dài tối đa của từng field name và value.
- Độ dài riêng cho Authorization, cookie và application-specific header.
- Số lần xuất hiện của một header.
- Kích thước request target, path và query string.
- Kích thước trailer nếu giao thức và hạ tầng cho phép.

Ngưỡng phải phù hợp với gateway, web server, framework và nghiệp vụ. Nếu ingress cho phép 64 KB nhưng backend chỉ xử lý 16 KB, request có thể bị từ chối ở các tầng khác nhau hoặc tạo ra khác biệt parser. Cần đồng bộ giới hạn và kiểm thử qua toàn bộ đường đi.

### 4.1. Tên header và giá trị header

Tên header HTTP không phân biệt chữ hoa/chữ thường. Vì vậy, Content-Type, content-type và CONTENT-TYPE phải được xử lý như cùng một field name.

Không nên dùng so sánh chuỗi có phân biệt hoa/thường để tạo nhiều policy khác nhau cho cùng một header. Hãy chuẩn hóa tên theo quy tắc của HTTP stack hoặc dùng API header chuẩn của framework.

Giá trị header có cú pháp riêng. Không tự tách bằng dấu phẩy hoặc dấu chấm phẩy nếu grammar của header có thể chứa quoted string hoặc cấu trúc phức tạp. Dùng parser phù hợp với từng header chuẩn.

### 4.2. Header lặp và giá trị mâu thuẫn

Một số header có semantics cho phép nhiều field line hoặc danh sách giá trị; một số header không thể gộp tùy tiện. Ví dụ Set-Cookie không thể xử lý như một danh sách comma-separated thông thường. Các header nhạy cảm như Content-Length, Host, Authorization hoặc header định danh nội bộ cần policy rõ ràng nếu xuất hiện nhiều lần.

Không mặc định rằng framework luôn trả đúng giá trị đầu tiên hoặc cuối cùng theo cách mọi proxy đều thống nhất. Cần xác định:

- Header nào cho phép lặp.
- Header nào được phép kết hợp theo grammar.
- Header nào phải xuất hiện đúng một lần.
- Hành vi khi có giá trị trùng hoặc mâu thuẫn.
- Hành vi khi proxy và backend diễn giải khác nhau.

Với header quan trọng có nhiều giá trị mâu thuẫn, lựa chọn an toàn thường là từ chối request ở tầng HTTP edge và bảo đảm các tầng sau có cùng cách xử lý.

### 4.3. Ký tự điều khiển và CRLF

Không chấp nhận ký tự CR (\r), LF (\n), NUL hoặc các control character không được phép trong header value. Nếu dữ liệu header được nối vào response, log hoặc downstream protocol mà không kiểm soát, attacker có thể gây header injection hoặc log injection.

HTTP field values có grammar cụ thể; không tự trim hoặc sửa mọi ký tự sai rồi tiếp tục xử lý. Từ chối input không hợp lệ giúp tránh hai tầng hiểu cùng một chuỗi theo cách khác nhau.

### 4.4. Không tự phân tích raw header khi framework đã xử lý

Ứng dụng nên dùng API HTTP của framework để đọc header đã được parser xử lý. Không tự lấy raw socket bytes rồi viết parser header đơn giản trong controller. Parser tự viết dễ sai về whitespace, quoted values, duplicate fields, line endings và protocol version.

Ở tầng edge, web server/proxy cần được cập nhật và cấu hình nhất quán. Ở tầng ứng dụng, chỉ xử lý các header đã được HTTP stack cung cấp và tiếp tục validate semantics theo endpoint.

## 5. Request smuggling và sự không nhất quán về framing

HTTP request smuggling có thể xảy ra khi hai thành phần trên cùng đường request diễn giải ranh giới message khác nhau. Attacker khai thác sự bất đồng giữa frontend proxy/load balancer và backend để làm một phần dữ liệu được hiểu thành request khác.

### 5.1. Content-Length và Transfer-Encoding

Trong HTTP/1.1, Content-Length có thể xác định độ dài message body. Transfer-Encoding: chunked là một cơ chế framing khác. Nếu một request chứa cả hai hoặc các giá trị mâu thuẫn, proxy và backend có thể chọn cách diễn giải khác nhau.

Không tự viết logic ưu tiên Content-Length hoặc Transfer-Encoding ở ứng dụng. HTTP parser và proxy phải tuân thủ RFC 9112 và chính sách triển khai thống nhất. Request có framing mơ hồ hoặc sai cú pháp cần bị từ chối, kết nối được xử lý theo cách an toàn và không được chuyển tiếp như một request bình thường.

Các nguyên tắc:

- Không để frontend và backend có cách diễn giải khác nhau về framing.
- Từ chối request có Content-Length lặp hoặc mâu thuẫn theo policy parser.
- Xử lý Transfer-Encoding đúng grammar và chỉ cho phép coding được hỗ trợ.
- Không chuyển tiếp nguyên header hop-by-hop sang hop tiếp theo.
- Không cho ứng dụng tự sửa framing header sau khi HTTP server đã parse.
- Cập nhật proxy, load balancer và framework để xử lý các biến thể request smuggling đã biết.

### 5.2. Transfer-Encoding không phải Content-Encoding

Hai field có tên gần nhau nhưng mục đích khác:

- Transfer-Encoding điều khiển cách message được đóng khung hoặc biến đổi khi truyền trong HTTP/1.1.
- Content-Encoding mô tả coding áp dụng lên representation body, chẳng hạn gzip.

Transfer-Encoding: chunked không có nghĩa body là gzip hoặc JSON. Content-Encoding: gzip không xác định ranh giới HTTP message.

Không dùng một validator cho cả hai. Framing thuộc trách nhiệm HTTP stack/proxy; content coding thuộc pipeline xử lý representation của ứng dụng hoặc middleware.

### 5.3. HTTP/2 và HTTP/3

HTTP/2 và HTTP/3 dùng framing khác HTTP/1.1. Header block có pseudo-header như :method, :scheme, :authority, :path; các quy tắc của HTTP/1.1 không được áp dụng máy móc.

Cần để HTTP stack xử lý pseudo-header và protocol constraints. Ví dụ, Host và :authority phải được xử lý nhất quán theo quy tắc chuyển đổi protocol; không để proxy và backend định tuyến đến hai authority khác nhau. Không chấp nhận connection-specific header trái quy định của HTTP/2. Khi gateway chuyển HTTP/2 xuống HTTP/1.1, phải kiểm tra việc chuyển đổi không tạo ra framing ambiguity.

## 6. Validate Content-Type

Content-Type mô tả media type của representation trong request body. Server dùng nó để chọn parser và validation pipeline.

Ví dụ:

- application/json
- application/problem+json
- application/xml
- multipart/form-data; boundary=...
- application/octet-stream
- text/csv; charset=utf-8

### 6.1. So sánh media type đúng cách

Media type gồm type và subtype; tên type/subtype không phân biệt hoa thường. Parameter có grammar riêng và có thể có quoted value. Không nên so sánh toàn bộ header bằng một phép equals đơn giản nếu endpoint cho phép parameter hợp lệ.

Ví dụ application/json; charset=utf-8 và application/json có thể được xử lý như cùng một JSON media type nếu contract cho phép parameter đó. Nhưng server không nên bỏ qua parameter không hỗ trợ hoặc chấp nhận mọi media type chỉ vì chuỗi bắt đầu bằng application/json.

Nên parse thành cấu trúc media type bằng thư viện chuẩn, sau đó kiểm tra:

1. Type/subtype có nằm trong allowlist của endpoint không?
2. Parameter có hợp lệ và được hỗ trợ không?
3. Boundary có bắt buộc không nếu là multipart?
4. Charset có được media type và contract cho phép không?
5. Body có thực sự parse được theo media type đã khai báo không?

### 6.2. Không tin phần mở rộng file hoặc nội dung tự khai

Tên file report.json không chứng minh nội dung là JSON. Header Content-Type: application/pdf cũng không chứng minh bytes là PDF hợp lệ.

Với upload, cần kiểm tra nhiều lớp:

- Media type được khai báo có được phép không?
- File signature/magic bytes có phù hợp không?
- Parser chuyên biệt có đọc được file không?
- Kích thước, số trang, số entry, độ sâu archive và thời gian xử lý có giới hạn không?
- File có được lưu ở vùng cách ly trước khi scan hoặc xử lý không?

Magic bytes chỉ là một tín hiệu, không phải bằng chứng hoàn chỉnh. File có thể chứa payload đa định dạng hoặc khai báo type giả. Không dùng một phép kiểm tra MIME duy nhất để cho phép file nguy hiểm.

### 6.3. Thiếu Content-Type

Với endpoint có body, cần quy định rõ có chấp nhận thiếu Content-Type không. Nếu endpoint yêu cầu JSON, thông thường nên từ chối khi header thiếu thay vì đoán body là JSON.

Một số request không có body hoặc dùng media type mặc định theo giao thức có thể không cần Content-Type. Policy cần phân biệt endpoint có body bắt buộc, body tùy chọn và request không có body.

### 6.4. Media type không hỗ trợ

Nếu endpoint không hỗ trợ media type được gửi, trả lỗi 415 Unsupported Media Type. Response nên nêu định dạng được chấp nhận ở mức phù hợp, không tiết lộ parser nội bộ hoặc stack trace.

Không cố parse XML như JSON hoặc JSON như text chỉ để “cứu” request. Fallback parser làm tăng bề mặt tấn công và có thể tạo cách diễn giải khác nhau giữa các thành phần.

## 7. Phân biệt Content-Type, Accept và Content-Encoding

Ba header này thường bị nhầm lẫn:

| Header | Hướng và ý nghĩa | Ví dụ |
|---|---|---|
| Content-Type | Media type của body request hoặc response | application/json |
| Accept | Media type client muốn nhận trong response | application/json, application/problem+json |
| Content-Encoding | Coding được áp dụng lên body representation | gzip |
| Accept-Encoding | Content coding client có thể nhận trong response | gzip, br |

### 7.1. Accept không xác định request body

Client gửi Accept: application/json nghĩa là client ưu tiên hoặc chấp nhận JSON trong response. Nó không có nghĩa request body là JSON. Content-Type mới mô tả request body.

Nếu server không thể tạo representation phù hợp với Accept, có thể trả 406 Not Acceptable theo negotiation policy. Nếu request body dùng media type không hỗ trợ, phản hồi thường là 415 Unsupported Media Type.

### 7.2. Content negotiation phải có quy tắc

Khi endpoint hỗ trợ nhiều response media type, server cần xử lý Accept và quality value (q) đúng grammar. Không tự tách header bằng dấu phẩy rồi chọn phần tử đầu tiên nếu chưa xử lý wildcard, quality và parameter.

Nếu API chỉ hỗ trợ JSON, có thể công bố rõ response luôn là JSON và quyết định policy khi Accept không tương thích. Dù chọn cách nào, hành vi cần nhất quán giữa gateway và application.

### 7.3. Không nhầm Accept-Encoding với request Content-Encoding

Accept-Encoding: gzip thường cho biết client có thể nhận response nén gzip. Content-Encoding: gzip cho biết body request hiện tại đã được nén gzip. Một endpoint có thể hỗ trợ response compression nhưng không hỗ trợ compressed request body.

Chỉ bật request decompression khi có nhu cầu và đã đặt giới hạn. Không tự động giải nén mọi coding mà thư viện hoặc server có thể nhận.

## 8. Validate Content-Encoding và chống decompression bomb

Content coding có thể giảm băng thông nhưng cũng làm tăng chi phí CPU và bộ nhớ. Một payload nhỏ sau nén có thể giải nén thành dữ liệu rất lớn.

### 8.1. Allowlist coding

Endpoint nên xác định rõ coding được hỗ trợ, ví dụ không hỗ trợ request compression hoặc chỉ cho phép gzip. Nếu nhận coding khác, từ chối theo policy, thường bằng 415 Unsupported Media Type.

Không bật nhiều thuật toán nén chỉ vì framework hỗ trợ. Mỗi decoder bổ sung là một bề mặt xử lý input phức tạp cần cập nhật và kiểm thử.

### 8.2. Giới hạn cả compressed và decompressed size

Cần đặt ít nhất:

- Giới hạn byte truyền vào trước giải nén.
- Giới hạn byte sau giải nén.
- Giới hạn tỷ lệ expansion nếu phù hợp.
- Giới hạn thời gian CPU và thời gian đọc.
- Giới hạn số layer coding và số lần giải nén.
- Giới hạn concurrency của tác vụ giải nén.

Không chỉ kiểm tra Content-Length, vì request có thể dùng streaming hoặc framing khác. Bộ đếm byte phải theo dõi dữ liệu thực tế đi qua pipeline.

### 8.3. Giải nén theo streaming

Tránh đọc toàn bộ compressed body vào memory rồi giải nén thành một mảng byte không giới hạn. Dùng streaming parser và giới hạn số byte output. Khi vượt ngưỡng, dừng xử lý, đóng stream đúng cách và trả lỗi phù hợp.

Cần kiểm tra decoder có xử lý trailing data, concatenated members hoặc malformed stream theo cách nào. Hành vi cần thống nhất và không để một tầng bỏ qua phần bytes mà tầng khác diễn giải.

### 8.4. Nén nhiều lớp

Không cho phép chuỗi coding lồng nhau tùy ý như nhiều lớp gzip/deflate nếu API không có yêu cầu. Nếu hỗ trợ nhiều coding, quy định thứ tự giải mã và giới hạn số lớp. Nếu không, từ chối request có chuỗi coding không nằm trong allowlist.

## 9. Charset, UTF-8 và JSON

### 9.1. JSON dùng UTF-8

JSON trao đổi giữa các hệ thống theo RFC 8259 phải được mã hóa UTF-8. Với JSON qua network, không cần gửi charset parameter; server nên xử lý UTF-8 nhất quán.

Nếu client gửi Content-Type: application/json; charset=... với charset khác UTF-8, endpoint có thể từ chối theo contract thay vì âm thầm giải mã theo charset tùy ý. Không dùng platform default charset vì kết quả có thể khác giữa máy phát triển và production.

### 9.2. Giải mã byte nghiêm ngặt

Không dùng decoder thay thế byte sai bằng ký tự replacement rồi tiếp tục xử lý dữ liệu nhạy cảm. Ví dụ UTF-8 decoder có thể được cấu hình để báo lỗi khi gặp byte sequence không hợp lệ.

Nếu dữ liệu là JSON, parser phải nhận đúng chuỗi đã được giải mã theo encoding được cho phép. Malformed UTF-8 nên bị từ chối với lỗi client, không âm thầm sửa nội dung.

### 9.3. BOM và byte order mark

UTF-8 BOM không cần thiết trong JSON network. Cần xác định parser có chấp nhận BOM hay không và bảo đảm mọi tầng có cùng hành vi. Nếu gateway bỏ BOM nhưng backend giữ BOM, signature, logging hoặc validation có thể thấy dữ liệu khác nhau.

Một policy rõ ràng có thể từ chối BOM ở request JSON hoặc chấp nhận theo parser đã được kiểm thử; không để các tầng tự xử lý khác nhau.

### 9.4. Charset của media type khác

Không phải mọi media type văn bản đều có cùng quy tắc. Một số media type có thể dùng charset parameter; một số định dạng có encoding mặc định riêng. Hãy đọc contract và đặc tả của media type được hỗ trợ, thay vì áp dụng một quy tắc charset chung cho mọi body.

Nếu API chỉ cần JSON, giới hạn media type còn giúp giảm số parser và encoding path cần bảo vệ.

## 10. Unicode và canonicalization

Unicode cho phép cùng một nội dung nhìn giống nhau nhưng có thể có chuỗi code point khác nhau. Ví dụ một ký tự có thể được biểu diễn bằng code point dựng sẵn hoặc một ký tự cơ sở kết hợp dấu.

Điều này có thể ảnh hưởng:

- So sánh username hoặc tên tài nguyên.
- Kiểm tra allowlist/blocklist.
- Tìm kiếm và uniqueness constraint.
- Chữ ký số hoặc HMAC trên nội dung.
- Đường dẫn file và object key.
- Log, audit và phát hiện giả mạo.

### 10.1. Normalize theo mục đích

Nếu nghiệp vụ cần so sánh chuỗi văn bản người dùng theo dạng tương đương, có thể chuẩn hóa Unicode, thường cân nhắc NFC ở một ranh giới xác định. Nhưng không nên tự động normalize mọi dữ liệu.

Không normalize tùy tiện:

- API key, token hoặc secret.
- Chữ ký và dữ liệu đã ký.
- Opaque identifier do hệ thống khác cấp.
- Byte sequence mà protocol yêu cầu giữ nguyên.
- Password, trừ khi authentication protocol và policy đã định nghĩa rõ.

Quy tắc là phải thống nhất nơi canonicalize và nơi xác minh chữ ký. Nếu signer ký bytes gốc nhưng verifier normalize trước khi kiểm tra, chữ ký sẽ không còn xác minh trên cùng dữ liệu.

### 10.2. Tránh double decoding

Một giá trị URL-encoded có thể bị decode nhiều lần ở proxy, router và ứng dụng. Ví dụ %252e%252e sau một lần decode thành %2e%2e, sau lần nữa mới thành ...

Cần xác định rõ tầng nào chịu trách nhiệm decode path/query. Không decode lại giá trị đã được framework parse. Kiểm thử các trường hợp percent-encoding kép, encoded slash, encoded NUL và dấu phân cách để tránh bypass validation hoặc path traversal.

### 10.3. Identifier nên có grammar rõ

Với ID nội bộ, mã giao dịch hoặc slug, nên định nghĩa alphabet, độ dài và quy tắc canonical. Ví dụ UUID nên parse thành UUID thay vì chỉ kiểm tra chuỗi “trông giống UUID”. Với identifier không cần Unicode, allowlist ASCII thường giảm ambiguity.

Với tên hiển thị tự do, cho phép Unicode nhưng cần giới hạn code point/byte length, xử lý control characters và áp dụng normalization policy nhất quán. Không nên dùng regex đơn giản để tự kiểm tra toàn bộ Unicode security.

### 10.4. Confusable và bidirectional controls

Một số ký tự Unicode trông gần giống Latin hoặc có thể thay đổi thứ tự hiển thị bằng bidirectional control. Điều này có thể gây nhầm lẫn trong tên tài khoản, domain, log và màn hình quản trị.

Với identifier nhạy cảm, cân nhắc hạn chế script được chấp nhận hoặc dùng profile xử lý identifier phù hợp. Với nội dung hiển thị tự do, có thể giữ Unicode nhưng cần escape/control display trong log và giao diện quản trị. Không xóa ký tự một cách âm thầm nếu điều đó làm thay đổi nội dung nghiệp vụ.

## 11. Validate các header bảo mật và nghiệp vụ quan trọng

### 11.1. Authorization

- Chỉ chấp nhận authentication scheme đã công bố.
- Parse token theo grammar phù hợp.
- Không chấp nhận nhiều Authorization header mâu thuẫn.
- Không log bearer token hoặc API key.
- Xác minh chữ ký, issuer, audience, thời hạn và scope ở lớp authentication.
- Không dùng token chỉ vì header có mặt.

Nếu API hỗ trợ nhiều cơ chế credential, quy định rõ cách xử lý khi client gửi đồng thời Authorization và X-API-Key. Không để gateway chọn một credential còn backend chọn credential khác.

### 11.2. Host và authority

Host trong HTTP/1.1 và :authority trong HTTP/2/3 ảnh hưởng routing và virtual host. Không dùng giá trị do caller gửi để tạo absolute URL, password reset link hoặc redirect mà không kiểm tra against allowlist host.

Cần cấu hình trusted host list ở ingress/application. Nếu có proxy chuyển đổi protocol, bảo đảm authority được xử lý nhất quán. Host header injection có thể ảnh hưởng cache, link generation và routing nội bộ.

### 11.3. Origin và Referer

Origin và Referer có thể hỗ trợ chính sách CORS/CSRF hoặc audit, nhưng không phải bằng chứng authentication. Không cho phép một request chỉ vì Origin có domain tin cậy nếu token/session không hợp lệ.

CORS là cơ chế browser kiểm soát việc JavaScript đọc response; nó không thay thế authorization và không ngăn mọi client ngoài browser gọi API.

### 11.4. Forwarded và X-Forwarded-*

Chỉ tin các header forwarding từ proxy nằm trong trust configuration. Không để public caller tự đặt X-Forwarded-Host, X-Forwarded-Proto hoặc X-Forwarded-For rồi ứng dụng dùng để tạo link, xác định HTTPS hoặc quyết định access policy.

Proxy cần xóa giá trị caller gửi và tạo lại header từ thông tin mà nó quan sát được. Ứng dụng phải biết chính xác proxy nào được phép gửi metadata này.

### 11.5. Idempotency-Key và trace headers

Idempotency-Key nên có độ dài và alphabet giới hạn, gắn với đúng principal/tenant và operation, có thời hạn lưu phù hợp. Không dùng key tùy ý làm đường dẫn hoặc tên file.

traceparent và request ID cần được parse theo grammar, giới hạn độ dài và không được dùng làm authorization identity. Trace context do caller gửi có thể hỗ trợ correlation nhưng không phải bằng chứng caller đáng tin.

## 12. Multipart và upload

multipart/form-data có boundary để phân tách các part. Parser cần xử lý boundary đúng grammar và giới hạn tài nguyên.

Các giới hạn nên có:

- Tổng kích thước request.
- Số part tối đa.
- Kích thước tối đa của mỗi part.
- Độ dài header trong mỗi part.
- Kích thước tên field và filename.
- Số file upload đồng thời.
- Thời gian upload và xử lý.
- Kích thước sau giải nén nếu file là archive.

### 12.1. Filename là dữ liệu không tin cậy

Không dùng filename do client gửi làm đường dẫn lưu trực tiếp. Filename có thể chứa path separator, Unicode bất thường, control character hoặc tên trùng. Tạo tên lưu nội bộ ngẫu nhiên, lưu filename gốc dưới dạng metadata đã được làm sạch và escape khi hiển thị.

Không dựa vào phần mở rộng file để quyết định parser. Kết hợp media type, signature, parser thực tế và scan phù hợp với loại file.

### 12.2. Nested archive và file bomb

Nếu cho phép ZIP hoặc định dạng archive, cần giới hạn:

- Tổng kích thước giải nén.
- Số entry.
- Độ sâu thư mục.
- Tỷ lệ nén.
- Kích thước từng entry.
- Path traversal trong tên entry.
- Thời gian giải nén và scan.

Giải nén vào thư mục cách ly, chuẩn hóa path và xác minh đích nằm trong vùng cho phép. Không cho archive ghi ra ngoài thư mục làm việc qua ../, absolute path hoặc symlink.

### 12.3. Lưu file và xử lý bất đồng bộ

File mới upload nên ở trạng thái quarantine/pending cho đến khi validation và scan hoàn tất. Không cho client truy cập trực tiếp file theo URL dự đoán được. Signed URL cần thời hạn, phạm vi object và quyền phù hợp.

Nếu chuyển file sang worker xử lý, message phải tham chiếu object ID nội bộ và metadata đã xác minh; không đưa credential vào queue.

## 13. Ánh xạ lỗi validation sang HTTP status

Response lỗi cần ổn định, không lộ parser detail, stack trace hoặc nội dung nhạy cảm.

| Tình huống | Status thường dùng | Ghi chú |
|---|---|---|
| Header sai cú pháp hoặc thiếu field bắt buộc | 400 Bad Request | Nêu field/code ở mức an toàn |
| Header hoặc request body vượt giới hạn | 431 Request Header Fields Too Large hoặc 413 Content Too Large | Chọn theo phần bị vượt |
| Media type không được hỗ trợ | 415 Unsupported Media Type | Có thể mô tả media type được chấp nhận |
| Content coding không được hỗ trợ | 415 Unsupported Media Type | Không thử decoder tùy ý |
| Byte sequence/JSON sai cú pháp | 400 Bad Request | Không trả stack trace |
| Request hợp lệ về cú pháp nhưng sai quy tắc nghiệp vụ | 422 Unprocessable Content hoặc 400 theo contract | Giữ semantics nhất quán |
| Accept không có representation phù hợp | 406 Not Acceptable | Áp dụng content negotiation |
| Request vượt rate limit | 429 Too Many Requests | Có thể kèm Retry-After |

Không dùng một status code duy nhất cho mọi lỗi. Client cần phân biệt request sai format, media type không hỗ trợ, payload quá lớn và vượt giới hạn tốc độ để có thể xử lý đúng.

### 13.1. Error body

Có thể dùng một cấu trúc lỗi ổn định, ví dụ:

```json
{
  "type": "about:blank",
  "title": "Unsupported Media Type",
  "status": 415,
  "code": "UNSUPPORTED_CONTENT_TYPE",
  "detail": "This endpoint accepts application/json.",
  "traceId": "trc-91a2"
}
```

Không đưa raw header, token, cookie, body hoặc exception message vào detail. Với request smuggling hoặc lỗi framing ở tầng proxy, có thể connection bị đóng trước khi application tạo error body; đây là hành vi có thể cần thiết để tránh tiếp tục xử lý message mơ hồ.

## 14. Ví dụ validation trong Java và Spring

### 14.1. Kiểm tra media type theo allowlist

Ví dụ khái niệm với Spring:

```java
@PostMapping(
    path = "/v1/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public OrderResponse createOrder(
        @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
```

Khai báo consumes giúp Spring chọn handler theo media type. Tuy nhiên, cần kiểm tra cách framework xử lý thiếu Content-Type, media type có parameter, duplicate header và lỗi parser ở phiên bản đang dùng. Cấu hình gateway và web server cũng phải có giới hạn tương ứng.

### 14.2. Kiểm tra charset JSON nghiêm ngặt

Với JSON, nên quy định UTF-8 theo contract và dùng parser/decoder có thể báo lỗi khi byte sequence không hợp lệ. Không lấy charset từ platform default hoặc tự chuyển đổi qua một charset khác để cố đọc request.

Pseudo-code:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String json = decoder.decode(ByteBuffer.wrap(bodyBytes)).toString();
```

Đoạn này chỉ minh họa bước decode. Trong ứng dụng thực tế, cần đọc body theo streaming với giới hạn byte, để HTTP framework quản lý lifecycle và không giữ toàn bộ body lớn trong memory. JSON parser sau đó phải có giới hạn độ sâu, số phần tử và kích thước chuỗi phù hợp.

### 14.3. Không tự đọc header forwarding

Không nên viết:

```java
String clientIp = request.getHeader("X-Forwarded-For").split(",")[0];
```

Cách này tin header caller có thể giả mạo và không xác minh proxy chain. Hãy dùng cấu hình trusted proxy của ingress/framework hoặc một resolver biết rõ proxy nào được tin cậy và cách chuẩn hóa chuỗi.

### 14.4. Đặt giới hạn ở nhiều tầng

Ví dụ một hệ thống có thể cấu hình:

- Gateway: giới hạn tổng header, request target, body size và timeout.
- HTTP server: giới hạn header count/size, request line và framing.
- Middleware: kiểm tra content coding, media type và identity header.
- Controller/parser: schema, độ sâu JSON và giới hạn field.
- File service: multipart, file signature, archive expansion và scan.
- Business service: tenant, object authorization và trạng thái nghiệp vụ.

Không nên đặt toàn bộ trách nhiệm ở controller vì request có thể đã tiêu tốn tài nguyên hoặc bị parse không an toàn trước khi controller được gọi.

## 15. Kiểm thử header, content type và encoding

Kiểm thử cần bao phủ cả request hợp lệ, malformed input, parser differential và giới hạn tài nguyên.

### 15.1. Header syntax và cardinality

- Header bắt buộc bị thiếu.
- Header lạ hoặc không được endpoint hỗ trợ.
- Tên header viết hoa/thường khác nhau.
- Header lặp với giá trị giống nhau.
- Header lặp với giá trị mâu thuẫn.
- Header value chứa CR, LF, NUL hoặc control character.
- Header tổng thể quá lớn.
- Quá nhiều header fields.
- Cookie hoặc Authorization vượt giới hạn.
- Header có quoted parameter hoặc comma list được parse đúng grammar.

### 15.2. Content-Type và negotiation

- Content-Type hợp lệ.
- Thiếu Content-Type ở endpoint bắt buộc body.
- Media type sai hoặc không hỗ trợ.
- Media type có parameter hợp lệ.
- Charset không được hỗ trợ.
- Multipart thiếu hoặc sai boundary.
- Accept không tương thích với response.
- Accept có wildcard và quality value.
- Content-Type khai báo JSON nhưng body không phải JSON.
- File extension và MIME header không khớp file signature.

### 15.3. Content-Encoding và resource limits

- Coding được hỗ trợ và body giải nén hợp lệ.
- Coding không được hỗ trợ.
- Gzip stream bị cắt hoặc checksum sai.
- Compressed body vượt giới hạn.
- Decompressed body vượt giới hạn.
- Expansion ratio bất thường.
- Coding lồng nhiều lớp.
- Giải nén kéo dài hoặc tiêu tốn CPU quá mức.
- Streaming bị ngắt giữa chừng.
- Decoder lỗi nhưng application không tiếp tục parse dữ liệu một phần.

### 15.4. Encoding và Unicode

- UTF-8 hợp lệ.
- UTF-8 malformed hoặc byte sequence không đầy đủ.
- BOM theo đúng policy.
- Ký tự Unicode kết hợp và dạng NFC/NFD.
- Control character và bidirectional controls.
- Percent-encoding kép.
- Encoded slash, NUL và path separator.
- Ký tự confusable trong identifier.
- Signature verification với bytes gốc, không normalize ngoài protocol.

### 15.5. Protocol differential và request smuggling

Các bài kiểm thử framing cần được thực hiện trong môi trường kiểm thử được kiểm soát, qua đúng ingress/proxy/backend path:

- Content-Length lặp hoặc mâu thuẫn.
- Content-Length kết hợp với Transfer-Encoding.
- Chunked body sai cú pháp.
- Header whitespace/line ending bất thường.
- HTTP/2 pseudo-header không hợp lệ.
- Host và :authority không nhất quán.
- Proxy chuyển HTTP/2 sang HTTP/1.1.
- Kết nối keep-alive sau request lỗi framing.

Mục tiêu là xác nhận các tầng từ chối hoặc chuẩn hóa request theo cùng một quy tắc. Không chỉ test controller trực tiếp vì lỗi parser có thể xảy ra trước application.

### 15.6. Kiểm thử không rò rỉ dữ liệu

- Token và API key không xuất hiện trong access log.
- Header nhạy cảm không xuất hiện trong exception hoặc trace.
- Error body không chứa raw request.
- Filename không được dùng trực tiếp làm path.
- Request bị từ chối không tạo side effect nghiệp vụ.
- Body quá lớn hoặc decompression bomb không làm cạn memory/CPU.

## 16. Logging, monitoring và vận hành

Theo dõi validation giúp phát hiện tấn công và cấu hình client sai. Tuy nhiên, log phải tránh lưu credential và dữ liệu nhạy cảm.

Metric hữu ích:

- Số request bị từ chối theo error code và endpoint.
- Tỷ lệ header malformed hoặc duplicate quan trọng.
- Số request có media type/coding không được hỗ trợ.
- Số byte compressed và decompressed.
- Decompression ratio và thời gian giải nén.
- Số lỗi UTF-8/JSON parser.
- Tỷ lệ 400, 413, 415, 431 và 406.
- Số lỗi framing ở gateway/proxy.
- Số upload bị từ chối theo loại file và lý do.
- p95/p99 thời gian parse, decode và validate.

### 16.1. Không log raw header hoặc body nhạy cảm

Không ghi toàn bộ Authorization, Cookie, X-API-Key, session token hoặc request body chứa dữ liệu cá nhân. Nếu cần điều tra, ghi tên header, validation result, endpoint, trace ID và một định danh đã được che hoặc pseudonymize.

Đối với IP, tuân theo chính sách retention và quyền riêng tư. Với metric, tránh dùng user ID, key ID hoặc tenant ID có cardinality cao làm label không giới hạn.

### 16.2. Phân biệt lỗi client và sự cố hạ tầng

Một đợt tăng 415 có thể do client release sai Content-Type. Một đợt 431 có thể do cookie/session phình to. Một đợt malformed framing có thể chỉ ra proxy misconfiguration hoặc request smuggling attempt.

Dashboard nên kết hợp status code, endpoint, client version, gateway instance và thời điểm triển khai. Alert cần phân biệt lỗi phân tán trên nhiều client với lỗi tập trung ở một integration hoặc một proxy.

### 16.3. Quản lý thay đổi parser và gateway

Nâng phiên bản framework, proxy, compression library hoặc JSON parser có thể thay đổi hành vi với malformed input. Trước khi rollout:

- Kiểm thử contract và negative cases.
- So sánh behavior giữa gateway và backend.
- Kiểm tra giới hạn header/body có tương thích.
- Kiểm tra log và metric sau triển khai.
- Có khả năng rollback hoặc tắt coding không cần thiết nếu phát hiện lỗi.

## 17. Những lỗi thiết kế thường gặp

1. **Tin mọi header caller gửi.** Header identity hoặc proxy có thể bị giả mạo.
2. **Chỉ so sánh Content-Type bằng chuỗi.** Parameter, case và grammar có thể bị xử lý sai.
3. **Đoán media type từ body hoặc filename.** Parser fallback mở rộng bề mặt tấn công.
4. **Nhầm Accept với Content-Type.** Server đọc sai định dạng request hoặc trả representation không phù hợp.
5. **Nhầm Transfer-Encoding với Content-Encoding.** Framing và compression bị xử lý sai tầng.
6. **Không giới hạn header size/count.** Attacker có thể tiêu tốn memory và CPU trước business logic.
7. **Chấp nhận duplicate header mâu thuẫn.** Proxy và backend có thể chọn giá trị khác nhau.
8. **Tự viết HTTP parser.** Khác biệt grammar và normalization có thể tạo lỗ hổng.
9. **Không đồng bộ proxy và backend.** Có nguy cơ request smuggling.
10. **Giải nén không giới hạn.** Payload nhỏ có thể trở thành dữ liệu rất lớn.
11. **Dùng platform default charset.** Kết quả phụ thuộc môi trường runtime.
12. **Thay byte UTF-8 lỗi bằng replacement character.** Validation và signature có thể thấy nội dung khác nhau.
13. **Decode URL nhiều lần.** Có thể bypass path validation hoặc tạo traversal.
14. **Normalize mọi chuỗi.** Token, signature và opaque identifier có thể bị thay đổi.
15. **Tin MIME header hoặc phần mở rộng file.** File thực tế có thể thuộc định dạng khác.
16. **Dùng filename trực tiếp làm path.** Có nguy cơ path traversal và overwrite.
17. **Log toàn bộ header/body.** Credential và dữ liệu nhạy cảm có thể bị lộ.
18. **Chỉ test controller.** Không phát hiện được lỗi parser ở gateway, proxy hoặc HTTP server.

## 18. Checklist thiết kế và triển khai

Trước khi phát hành endpoint, hãy xác nhận:

- [ ] Contract xác định header bắt buộc, tùy chọn, lặp và header nội bộ.
- [ ] Có giới hạn tổng header size, số lượng field và độ dài value.
- [ ] Header name được xử lý không phân biệt hoa/thường theo HTTP.
- [ ] Header quan trọng có policy rõ khi lặp hoặc mâu thuẫn.
- [ ] CR/LF, NUL và control character không hợp lệ bị từ chối.
- [ ] Proxy chỉ chuyển tiếp header forwarding đã được xác minh.
- [ ] Host/:authority và routing được xử lý nhất quán.
- [ ] Gateway và backend có cách xử lý framing tương thích.
- [ ] Request framing mơ hồ hoặc sai cú pháp bị từ chối.
- [ ] Content-Type được parse và so với allowlist của endpoint.
- [ ] Accept được xử lý riêng cho response negotiation.
- [ ] Content-Encoding chỉ cho phép coding đã được hỗ trợ.
- [ ] Có giới hạn compressed/decompressed bytes, ratio, CPU và thời gian.
- [ ] JSON được giải mã UTF-8 theo policy rõ ràng.
- [ ] Byte sequence sai encoding bị từ chối, không âm thầm thay thế.
- [ ] Unicode normalization chỉ diễn ra tại ranh giới được xác định.
- [ ] URL không bị decode nhiều lần.
- [ ] Multipart boundary, số part, file size và archive expansion có giới hạn.
- [ ] Filename không được dùng trực tiếp làm đường dẫn lưu file.
- [ ] Status 400, 413, 415, 431, 406 và 429 được dùng nhất quán.
- [ ] Có negative tests qua toàn bộ gateway/proxy/application path.
- [ ] Log không chứa token, API key, cookie hoặc raw body nhạy cảm.
- [ ] Có metric và alert cho malformed header, parser errors và decompression behavior.

## 19. Kết luận

Validate header, content type và encoding giúp API hiểu request theo một cách thống nhất trước khi xử lý nghiệp vụ. Header cần được kiểm tra cú pháp, số lượng, kích thước, giá trị lặp và nguồn tin cậy. Content-Type cần được parse theo media type được endpoint cho phép; Accept và Content-Encoding phải được xử lý theo đúng vai trò riêng. HTTP framing cần do các parser/proxy chuẩn xử lý nhất quán để giảm nguy cơ request smuggling.

Với body văn bản, UTF-8 và Unicode cần có policy rõ về decode, malformed input, BOM, normalization và percent-encoding. Với payload nén hoặc multipart, phải giới hạn cả dữ liệu đầu vào lẫn chi phí sau giải nén và xử lý. Không dựa vào header MIME hoặc filename để kết luận nội dung an toàn.

Một quy trình đáng tin cậy đặt giới hạn ở gateway, HTTP server và application; trả lỗi có semantics ổn định; kiểm thử cả malformed input lẫn parser differential; và log kết quả mà không làm lộ credential. Khi các bước này được thực hiện nhất quán, validation ở tầng giao thức sẽ giảm rủi ro trước khi dữ liệu đi vào logic phân quyền và nghiệp vụ.


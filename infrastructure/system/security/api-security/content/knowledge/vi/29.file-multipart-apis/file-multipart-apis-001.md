# Giới hạn kích thước và số phần upload

## 1. Vì sao API upload cần giới hạn nhiều chiều?

Upload file là một luồng nhận dữ liệu từ bên ngoài và thường tiêu tốn nhiều tài nguyên hơn một request JSON thông thường. Một request multipart có thể chứa file lớn, nhiều file nhỏ, nhiều field văn bản, header riêng cho từng part và phần boundary. Nếu API chỉ kiểm tra kích thước từng file, attacker vẫn có thể gửi hàng nghìn part nhỏ, field rất dài hoặc nhiều request đồng thời để làm cạn CPU, memory, disk và connection.

Các lỗi thường gặp:

- Chỉ đặt giới hạn ở controller sau khi framework đã parse và ghi file tạm ra disk.
- Chỉ giới hạn từng file, không giới hạn tổng kích thước request.
- Không giới hạn số file hoặc tổng số part.
- Cho phép quá nhiều field văn bản hoặc field có giá trị rất dài.
- Tin Content-Length và bỏ sót request streaming/chunked không có độ dài khai báo.
- Gateway cho phép body lớn hơn giới hạn của application hoặc ngược lại.
- Multipart parser giữ quá nhiều dữ liệu trong memory hoặc thư mục tạm.
- Nhiều upload đồng thời làm đầy disk dù mỗi request đều nằm dưới giới hạn.
- Retry hoặc upload resumable tạo ra nhiều session và chunk không được thu hồi.
- File nén nhỏ nhưng khi giải nén tạo ra dữ liệu khổng lồ.

Trong phạm vi **SECURITY_API_SECURITY**, giới hạn upload là một phần của validation và resource-consumption control. API cần giới hạn ở nhiều cấp: toàn bộ request, từng file, số part, từng field, kích thước header, thời gian nhận dữ liệu, concurrency và quota theo principal/tenant.

Sau bài học này, người học có thể:

1. Phân biệt tổng request size với per-file size và multipart part count.
2. Thiết kế giới hạn cho file part, text field, part header và boundary.
3. Enforce byte limit khi request được truyền theo streaming.
4. Đặt giới hạn ở gateway, HTTP server, multipart parser và application.
5. Kiểm soát memory, temporary disk, concurrency và tenant quota.
6. Thiết kế upload chunked/resumable có giới hạn tổng.
7. Kiểm thử các trường hợp upload quá lớn, quá nhiều part và slow upload.

## 2. Multipart request gồm những gì?

Một request multipart thường dùng media type `multipart/form-data`. Body được chia thành các part; mỗi part có header riêng, một dòng trống và nội dung. Boundary được khai báo trong Content-Type để parser nhận biết ranh giới giữa các part.

Ví dụ:

```http
POST /v1/documents HTTP/1.1
Host: api.example.test
Content-Type: multipart/form-data; boundary=----upload-boundary
Content-Length: 348

------upload-boundary
Content-Disposition: form-data; name="title"

Quarterly report
------upload-boundary
Content-Disposition: form-data; name="attachment"; filename="report.pdf"
Content-Type: application/pdf

<file bytes>
------upload-boundary--
```

Request trên có hai part: một text field tên title và một file part tên attachment. Vì vậy, khi nói số part, cần tính cả field văn bản lẫn file, không chỉ số file.

### 2.1. Các thành phần cần giới hạn

| Thành phần | Ý nghĩa | Rủi ro nếu không giới hạn |
|---|---|---|
| Request body | Toàn bộ bytes của multipart request | Chiếm băng thông, memory, disk và thời gian |
| File part | Nội dung của từng file | File lớn gây đầy disk hoặc xử lý quá tải |
| Part count | Tổng số file part và form field | Parser/CPU tốn tài nguyên vì quá nhiều part |
| Field count | Số field văn bản | Tạo nhiều object và validation work |
| Field value | Nội dung của từng field | Giá trị lớn gây memory/DB/log amplification |
| Part header | Header trong mỗi part | Parser phải xử lý header dài hoặc nhiều field |
| Boundary | Dấu phân tách part | Giá trị bất thường làm parser tốn công hoặc lỗi |
| Concurrent uploads | Số request upload đang xử lý cùng lúc | Cạn connection, memory và temporary storage |
| Upload duration | Thời gian gửi body | Giữ socket, worker và upload slot quá lâu |

### 2.2. Kích thước multipart không bằng tổng kích thước file

Tổng request body gồm:

- Nội dung tất cả file.
- Giá trị các text field.
- Boundary và CRLF phân tách.
- Part headers như Content-Disposition và Content-Type.
- Các byte framing của request theo HTTP.

Do đó, giới hạn tổng request phải lớn hơn tổng file size được phép một khoảng đủ cho multipart overhead. Nhưng không nên đặt overhead quá rộng hoặc dùng một request limit khổng lồ để tránh lỗi client.

Ví dụ endpoint nhận tối đa hai file, mỗi file 10 MiB, có một số field metadata nhỏ. Request limit có thể đặt khoảng 22 MiB để dành chỗ cho overhead và metadata. Con số thực tế phải được đo theo contract và parser.

## 3. Định nghĩa upload policy theo endpoint

Mỗi endpoint upload cần có policy rõ ràng thay vì dùng một ngưỡng chung cho toàn hệ thống.

Một policy nên xác định:

- Tổng request body tối đa.
- Kích thước tối đa của mỗi file.
- Số file tối đa.
- Tổng số multipart part tối đa.
- Số text field tối đa.
- Kích thước tối đa của mỗi text field.
- Tổng kích thước text field.
- Số lượng và tổng kích thước part header.
- Boundary length tối đa nếu parser cho phép cấu hình.
- Thời gian nhận request và thời gian xử lý.
- Số upload đồng thời theo service, principal và tenant.
- Quota lưu trữ theo user/tenant.
- Chính sách đối với file rỗng, file trùng và upload chưa hoàn tất.

Ví dụ:

| Endpoint | File tối đa | File size | Request size | Part count |
|---|---:|---:|---:|---:|
| Avatar | 1 | 5 MiB | 6 MiB | 3 |
| Attachments | 5 | 10 MiB/file | 52 MiB | 12 |
| CSV import | 1 | 25 MiB | 26 MiB | 4 |
| Bulk document upload | 20 | 20 MiB/file | 405 MiB | 30 |

Đây là các giá trị minh họa, không phải mặc định an toàn cho mọi ứng dụng. Cần chọn theo loại dữ liệu, user journey, năng lực hạ tầng và SLA.

### 3.1. Tách file count và part count

Một request có thể chứa một file nhưng hàng nghìn field văn bản. Nếu chỉ giới hạn số file, parser vẫn phải xử lý hàng nghìn part.

Ngược lại, nếu giới hạn part count quá thấp nhưng không giới hạn số file riêng, một endpoint có thể cho phép nhiều file lớn hơn dự kiến nếu policy bị cấu hình sai.

Nên có cả:

- Max files.
- Max total parts.
- Max text fields.
- Max file size per part.
- Max aggregate file bytes.
- Max aggregate text bytes.

### 3.2. Quy tắc tổng và riêng phải nhất quán

Giả sử endpoint cho phép 5 file, mỗi file tối đa 10 MiB, thì tổng file bytes tối đa về mặt lý thuyết là 50 MiB. Nếu request limit chỉ là 20 MiB, contract thực tế không thể đáp ứng cấu hình 5 file tối đa cùng lúc.

Cần tính mối quan hệ giữa các giới hạn và viết rõ contract. Nếu muốn giới hạn tổng file bytes thấp hơn tổng các per-file maximum, hãy công bố đó là một giới hạn riêng.

### 3.3. Dùng đơn vị thống nhất

Phân biệt:

- 1 MB = 1.000.000 bytes.
- 1 MiB = 1.048.576 bytes.

Nhiều thư viện dùng MB theo decimal hoặc suffix riêng. Cần thống nhất đơn vị trong API documentation, gateway config, application config, quota và error response. Không để gateway hiểu 10 MB còn application hiểu 10 MiB mà không biết sai số.

## 4. Giới hạn tổng request body

Tổng request limit là lớp bảo vệ đầu tiên để chặn request có body lớn hơn contract. Nó cần được enforce trước khi ứng dụng parse multipart và cấp phát tài nguyên cho từng part.

### 4.1. Đặt giới hạn ở ingress/gateway

Gateway hoặc reverse proxy có thể từ chối request quá lớn trước khi chuyển tới application. Điều này giảm tải cho server và bảo vệ các parser phía sau.

Cần xác minh:

- Request body limit có áp dụng cho mọi route upload không?
- Limit có tính cả multipart boundary và header không?
- Proxy có buffer toàn bộ request xuống disk không?
- Khi vượt limit, proxy trả status nào?
- Request bị từ chối có được forward một phần body không?
- Limit có nhất quán giữa các gateway/region không?

Không chỉ cấu hình một global limit nếu các endpoint có nhu cầu khác nhau. Route upload lớn cần policy riêng và quota riêng.

### 4.2. Đặt giới hạn ở HTTP server và application

Gateway có thể bị bypass qua private route hoặc direct service access. Vì vậy HTTP server và application cũng cần giới hạn body. Các lớp này cần có giá trị tương thích để không tạo đường vào rộng hơn ở một tầng.

Nếu gateway cho phép 100 MiB nhưng application chỉ cho 20 MiB, client có thể upload 100 MiB vào gateway trước khi bị backend từ chối, gây tốn băng thông và buffer. Nếu gateway chỉ cho 10 MiB còn API contract là 20 MiB, request hợp lệ sẽ bị từ chối sớm ngoài dự kiến.

### 4.3. Request không có Content-Length

Không phải request nào cũng có Content-Length đáng tin hoặc có thể biết trước. HTTP/1.1 có thể dùng chunked transfer coding; HTTP/2/HTTP/3 dùng framing riêng và body có thể được stream.

Không dùng Content-Length làm cơ chế duy nhất. Bộ đếm byte thực tế phải dừng việc đọc khi tổng body vượt giới hạn. Với multipart parser, cấu hình parser/container và gateway để giới hạn ngay trong quá trình nhận, trước khi body được lưu đầy đủ.

### 4.4. Không đọc hết body rồi mới kiểm tra

Một anti-pattern là đọc toàn bộ request vào byte array, sau đó kiểm tra độ dài. Lúc kiểm tra xảy ra, memory đã bị tiêu tốn.

Hãy dùng parser có giới hạn hoặc bounded streaming. Khi vượt ngưỡng, dừng đọc theo semantics của server, dọn temporary resource và trả lỗi phù hợp.

## 5. Giới hạn kích thước từng file

Per-file size limit ngăn một part duy nhất chiếm quá nhiều storage hoặc chi phí xử lý.

Cần quy định:

- Kích thước tối đa của mỗi file.
- File rỗng có được phép không.
- Kích thước tối thiểu nếu nghiệp vụ yêu cầu.
- File size được tính bằng bytes thực nhận.
- Hành vi khi vượt ngưỡng giữa stream.
- File có được giữ tạm khi upload lỗi hay phải xóa ngay.

### 5.1. Không chỉ dựa vào metadata

Filename, Content-Type và client-provided file size không chứng minh kích thước thực tế. Browser có thể hiển thị file size trước khi upload, nhưng server phải đếm bytes nhận được.

Nếu parser đã tạo MultipartFile, giá trị size của nó có thể dùng cho validation nghiệp vụ, nhưng giới hạn đó thường được kiểm tra sau khi container đã parse và spool nội dung. Vì vậy nó không thay thế parser-level size limit.

### 5.2. Giới hạn file riêng và tổng file bytes

Một request có thể chứa nhiều file dưới per-file limit nhưng tổng lại quá lớn. Cần một aggregate file bytes limit bên cạnh request limit.

Ví dụ:

- Tối đa 5 file.
- Mỗi file tối đa 10 MiB.
- Tổng bytes của tất cả file tối đa 30 MiB.
- Toàn bộ request tối đa 32 MiB.

Với cấu hình này, năm file 10 MiB không thể cùng được chấp nhận vì aggregate limit là 30 MiB. Contract phải nói rõ điều đó.

### 5.3. File upload dở dang

Nếu client ngắt kết nối khi file đang được ghi, server cần cleanup temporary file và release quota reservation. Cần có cơ chế thu hồi file tạm quá hạn sau crash hoặc process restart.

Không giữ file partial vô thời hạn. Nếu cần resume, quản lý upload session và chunk theo state machine có expiry rõ ràng.

## 6. Giới hạn số lượng part và field

Số part là một giới hạn độc lập với byte size. Một request nhỏ có thể chứa hàng chục nghìn part rỗng hoặc rất nhỏ nhưng vẫn tạo nhiều object, parser invocation và validation work.

### 6.1. Giới hạn tổng part count

Đặt max total parts cho mỗi request. Tổng này bao gồm:

- File parts.
- Text fields.
- Các part có tên trùng.
- Part rỗng nếu parser chấp nhận.

Không chỉ đếm file part. Nếu API hỗ trợ nested multipart, cần giới hạn depth hoặc từ chối nested multipart nếu không có use case.

### 6.2. Giới hạn số text fields

Text field có thể được dùng cho metadata như title, description, category hoặc JSON metadata. Cần đặt:

- Max field count.
- Max bytes per field.
- Max aggregate field bytes.
- Max field name length.
- Allowlist tên field theo endpoint.
- Quy tắc đối với field trùng.

Nếu endpoint chỉ cần title và category, không nên chấp nhận hàng nghìn field tùy ý. Không tự động map mọi field vào object hoặc dynamic map mà không có giới hạn.

### 6.3. Field trùng và ambiguity

Multipart có thể chứa nhiều part cùng tên. Ví dụ tenantId xuất hiện hai lần với giá trị khác nhau. Framework có thể trả giá trị đầu tiên, cuối cùng hoặc danh sách tùy API.

Với field nhạy cảm hoặc điều khiển authorization, không nên cho phép duplicate mơ hồ. Tốt nhất derive tenant/principal từ authenticated context; nếu contract cần field đó, validate đúng một giá trị và đối chiếu với quyền đã xác minh.

### 6.4. Giới hạn part header

Mỗi part có thể chứa Content-Disposition, filename, Content-Type và header bổ sung. Cần giới hạn:

- Số part header.
- Tổng bytes của part headers.
- Độ dài field name.
- Độ dài filename.
- Độ dài Content-Type và parameter.
- Ký tự điều khiển và syntax sai.

Parser/container cần thực hiện các giới hạn này trước khi tạo object part. Không dựa vào controller để phát hiện header quá dài sau khi parser đã xử lý.

## 7. Boundary và multipart parser limits

Boundary được gửi trong Content-Type và xuất hiện trong body để tách các part. Parser phải tìm boundary trong stream và xử lý đúng CRLF, delimiter cuối và các trường hợp malformed.

Nên giới hạn:

- Boundary parameter có mặt và đúng syntax.
- Boundary length nằm trong giới hạn parser.
- Content-Type không có nhiều boundary mâu thuẫn.
- Multipart body có delimiter mở đầu và kết thúc hợp lệ.
- Số lần xuất hiện và tổng số part trong giới hạn.
- Nested multipart bị từ chối hoặc có depth limit.
- Parser không tiếp tục scan vô hạn khi body malformed.

Không tự viết multipart parser bằng regex hoặc split toàn bộ body thành chuỗi. File có thể chứa byte giống boundary; parser cần thực hiện đúng grammar và streaming semantics của multipart.

### 7.1. Giới hạn parser phải có hiệu lực trước controller

Trong nhiều framework, multipart body được parse bởi servlet container hoặc framework resolver trước khi controller được gọi. Nếu controller mới đếm số part, parser đã phải tạo part object và có thể ghi file tạm.

Do đó, max part count, part header size, file size và request size cần được đặt ở container/parser hoặc gateway hỗ trợ. Controller chỉ bổ sung kiểm tra contract và nghiệp vụ.

### 7.2. Không cho nested multipart tùy ý

Nếu API không cần multipart lồng nhau, từ chối hoặc không hỗ trợ. Nếu có use case, giới hạn số tầng và tổng số part trên toàn cây, không chỉ từng cấp riêng.

## 8. Memory, disk và temporary storage

Multipart parser có thể giữ một phần dữ liệu trong memory và spool phần còn lại ra temporary disk. Threshold, file count và concurrency ảnh hưởng trực tiếp đến tài nguyên.

### 8.1. Memory threshold

Một số parser giữ part nhỏ trong memory đến một threshold, sau đó ghi xuống disk. Nếu threshold quá lớn, nhiều upload đồng thời có thể làm heap tăng mạnh.

Ví dụ 100 request đồng thời, mỗi request có 10 part và parser giữ tối đa 1 MiB/part trong memory: mức memory tiềm năng có thể lên tới hàng gigabyte nếu mọi part chạm threshold. Đây chỉ là phép ước lượng; implementation thực tế có thể buffer theo cách khác.

Đặt threshold nhỏ vừa đủ và kiểm tra behavior của container. Không giả định file-size-threshold có nghĩa mọi byte dưới ngưỡng luôn nằm trong heap mà không có overhead.

### 8.2. Temporary disk

Temporary file cần được ghi vào vùng riêng:

- Không nằm trong web root.
- Không được public serve.
- Permission chỉ dành cho process cần thiết.
- Có quota và monitoring dung lượng.
- Có cleanup khi success, failure, timeout và process restart.
- Không dùng tên file do client cung cấp làm path.
- Có encryption hoặc storage control phù hợp với dữ liệu nhạy cảm.

Thư mục tạm nên nằm trên volume có giới hạn. Nếu dùng disk chung với log hoặc database, upload storm có thể làm hỏng các workload khác.

### 8.3. Disk quota và inode

Không chỉ theo dõi dung lượng bytes. Hàng triệu file tạm nhỏ có thể làm cạn inode hoặc metadata filesystem trước khi hết dung lượng. Giới hạn part count, upload concurrency và cleanup frequency giúp giảm rủi ro này.

### 8.4. Cleanup khi lỗi

Khi request bị từ chối giữa chừng:

- Hủy parser/stream nếu framework hỗ trợ.
- Xóa file tạm đã tạo.
- Release reservation/quota.
- Đóng file descriptor.
- Không để worker tiếp tục scan file partial.
- Ghi nhận reason code, không log nội dung file.

Cần kiểm thử cleanup khi client disconnect, timeout, process restart và parser exception.

## 9. Giới hạn concurrency và quota theo principal/tenant

Một user có thể gửi nhiều request đồng thời, mỗi request đều dưới giới hạn. Tổng tài nguyên vẫn có thể bị chiếm hết.

Nên có các lớp quota:

| Scope | Ví dụ giới hạn |
|---|---|
| Global service | Tổng upload đang hoạt động và tổng bytes đang nhận |
| Instance/pod | Concurrent parser, temp disk và file descriptors |
| Tenant | Tổng bytes/ngày, số file và storage quota |
| User/principal | Số upload đồng thời và request rate |
| API key/client | Quota tích hợp và burst |
| Upload session | Chunk count, total size, expiry và active session |
| Destination bucket | Storage quota và object count |

### 9.1. Reservation trước upload

Với upload lớn hoặc resumable, có thể tạo upload session trước khi truyền bytes. Server xác thực principal, kiểm tra quota và reserve một phần dung lượng dự kiến.

Reservation cần:

- Gắn với user/tenant đã xác minh.
- Có expiry.
- Có giới hạn số session.
- Không thể tăng total size tùy ý sau khi tạo.
- Được release khi cancel, timeout hoặc hoàn tất.
- Được reconcile nếu process chết.

Không tin tenant ID do form field tự khai. Lấy tenant từ authenticated principal và kiểm tra quyền trên destination object.

### 9.2. Quota phải chống race condition

Hai request đồng thời có thể cùng đọc quota còn trống rồi đều được chấp nhận, khiến tổng vượt giới hạn. Reservation và cập nhật usage cần atomic hoặc có cơ chế locking/transaction phù hợp.

Không tính quota chỉ bằng cách cộng file sau khi upload xong nếu hệ thống cần bảo vệ dung lượng ngay trong lúc nhận dữ liệu.

### 9.3. Fairness và noisy tenant

Một tenant có thể chiếm toàn bộ upload slot hoặc temporary disk. Dùng per-tenant concurrency, rate limit và storage quota để một tenant không làm gián đoạn tenant khác.

Nếu tenant vượt quota, trả lỗi có thể xử lý được và cung cấp thông tin quota an toàn. Không tiết lộ usage của tenant khác.

## 10. Streaming và byte counting

Streaming giúp xử lý dữ liệu theo từng phần thay vì giữ toàn bộ body trong memory. Tuy nhiên, streaming chỉ an toàn khi mọi bước có byte limit và backpressure.

### 10.1. Đếm bytes thực tế

Khi đọc stream, tăng bộ đếm theo số byte thực nhận. Nếu vượt giới hạn, dừng đọc và hủy operation.

Pseudo-code:

```java
long copied = 0;
byte[] buffer = new byte[8192];

while (true) {
    int count = input.read(buffer);
    if (count == -1) {
        break;
    }

    copied += count;
    if (copied > maxBytes) {
        throw new UploadTooLargeException();
    }

    output.write(buffer, 0, count);
}
```

Đây là ví dụ cho một stream đã được tách đúng khỏi multipart parser. Với multipart request, cần giới hạn tổng request ở parser/container và giới hạn từng file part trong quá trình parser ghi part. Không dùng vòng lặp trên để tự parse raw multipart body.

### 10.2. Backpressure

Nếu downstream storage chậm, upload reader không nên tiếp tục buffer vô hạn. Dùng bounded buffer, async backpressure hoặc giới hạn concurrency. Khi downstream không thể nhận dữ liệu, dừng hoặc pause đọc theo khả năng của server.

### 10.3. Streaming không có nghĩa không dùng disk

Framework có thể stream request vào temporary file trước khi controller xử lý. Cần biết dữ liệu đang được buffer ở proxy, HTTP server, multipart parser hay application. Kiểm tra toàn bộ pipeline, không chỉ API của controller.

### 10.4. Đếm bytes sau content decoding nếu có

Nếu hệ thống chấp nhận compressed request body, cần giới hạn cả bytes truyền vào và bytes sau giải nén. Một payload nén nhỏ có thể tạo ra body lớn. Nếu không có nhu cầu, từ chối request Content-Encoding không hỗ trợ.

## 11. Content-Length, chunked transfer và HTTP protocol

Content-Length hữu ích để từ chối sớm request vượt giới hạn, nhưng không thể là nguồn kiểm soát duy nhất.

### 11.1. Content-Length

Nếu Content-Length lớn hơn request limit, gateway/server có thể từ chối sớm. Nhưng vẫn cần đếm bytes thực tế vì:

- Header có thể không tồn tại trong streaming request.
- Request có thể dùng framing khác.
- Client có thể ngắt giữa chừng.
- Hệ thống có thể có nhiều hop với cách buffer khác nhau.

HTTP parser phải xử lý framing đúng chuẩn. Không tự viết logic ưu tiên Content-Length hoặc Transfer-Encoding trong controller.

### 11.2. Chunked request và HTTP/2/3

HTTP/1.1 có thể dùng Transfer-Encoding: chunked. HTTP/2 và HTTP/3 có framing riêng và không dùng chunked transfer coding theo cách HTTP/1.1.

Body limit cần được enforce dựa trên byte stream thực tế bất kể protocol version. Test phải bao gồm các protocol mà production hỗ trợ và đường proxy chuyển đổi protocol nếu có.

### 11.3. Expect: 100-continue

Client có thể gửi Expect: 100-continue để hỏi server trước khi truyền body lớn. Server/proxy có thể kiểm tra một số điều kiện và từ chối sớm. Đây là tối ưu giúp giảm băng thông, không thay thế body byte limit khi dữ liệu đã bắt đầu truyền.

## 12. Slow upload và timeout

Attacker không nhất thiết gửi file lớn. Một request nhỏ nhưng truyền cực chậm có thể giữ connection, upload slot và state trong thời gian dài.

Cần giới hạn:

- Thời gian chờ header.
- Thời gian chờ body bắt đầu.
- Tổng thời gian nhận body.
- Idle timeout giữa các lần nhận bytes.
- Minimum data rate nếu hạ tầng hỗ trợ.
- Thời gian parser xử lý từng part.
- Thời gian chờ storage.
- Total upload deadline.

Không chỉ dùng một timeout rất dài cho toàn bộ upload. Nếu cho phép file lớn, deadline cần dựa trên kích thước và tốc độ tối thiểu hợp lý, nhưng vẫn có giới hạn cứng.

### 12.1. Phân biệt idle timeout và total deadline

Idle timeout ngăn client giữ connection mà không gửi dữ liệu. Total deadline ngăn client gửi từng byte nhỏ đủ để reset idle timer nhưng giữ request quá lâu.

Nếu proxy, load balancer và application có timeout khác nhau, cần hiểu tầng nào đóng kết nối trước và application có cleanup được temporary resource không.

### 12.2. Timeout khi ghi storage

Storage chậm có thể làm upload giữ buffer và slot. Đặt deadline cho ghi object/file, giới hạn retry và hủy stream khi operation hết hạn.

Không retry ghi file từ đầu vô hạn. Với multipart object storage hoặc resumable upload, quản lý từng part bằng upload ID và có lifecycle cleanup cho session dở dang.

## 13. Cấu hình Spring Boot và Servlet container

Spring Boot cung cấp cấu hình multipart cơ bản. Ví dụ minh họa:

```yaml
spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 22MB
      file-size-threshold: 1MB
      location: /var/app/upload-tmp
```

Ý nghĩa:

- max-file-size: giới hạn kích thước một file.
- max-request-size: giới hạn toàn bộ multipart request.
- file-size-threshold: ngưỡng parser dùng để quyết định buffering/spooling theo implementation.
- location: thư mục tạm cho multipart processing.

Các giá trị trên chỉ là ví dụ. Chọn threshold và thư mục theo memory/disk budget, container và deployment. Đảm bảo thư mục tồn tại, có permission phù hợp, không public và nằm trên volume có quota.

### 13.1. Controller validation là lớp bổ sung

Ví dụ:

```java
@PostMapping(
    path = "/v1/documents",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ResponseEntity<Void> upload(
        @RequestPart("files") List<MultipartFile> files
) {
    if (files.size() > 5) {
        throw new TooManyFilesException();
    }

    long totalBytes = 0;
    for (MultipartFile file : files) {
        if (file.getSize() > MAX_FILE_BYTES) {
            throw new UploadTooLargeException();
        }
        totalBytes += file.getSize();
    }

    if (totalBytes > MAX_TOTAL_FILE_BYTES) {
        throw new UploadTooLargeException();
    }

    documentService.store(files);
    return ResponseEntity.accepted().build();
}
```

Đoạn code minh họa validation contract sau khi framework đã parse multipart. Nó không thay thế giới hạn max part count, header size, request body và per-file size ở parser/container/gateway. Với request có quá nhiều part, controller có thể chưa được gọi hoặc tài nguyên đã bị tiêu tốn trước khi vào method.

Trong code production, cần xử lý file rỗng, tên field, duplicate part, authorization theo tenant, cleanup và storage failure. Tránh đọc file vào byte array bằng getBytes() nếu file có thể lớn.

### 13.2. Giới hạn part count theo container

Không phải mọi phiên bản Servlet container hoặc framework đều có một property chuẩn chung để giới hạn tổng multipart part count. Kiểm tra tài liệu đúng phiên bản container đang chạy và cấu hình giới hạn parser tương ứng, chẳng hạn max part count và part header size nếu container hỗ trợ.

Không cho rằng max-file-size cũng giới hạn số part. Nếu container không có giới hạn phù hợp, dùng gateway/parser khác có hỗ trợ hoặc thiết kế upload protocol có giới hạn rõ.

### 13.3. Giới hạn tại gateway và container phải khớp

Ví dụ:

| Tầng | Giới hạn minh họa |
|---|---:|
| API gateway request body | 22 MiB |
| Servlet multipart max request | 22 MiB |
| Per-file parser limit | 10 MiB |
| Part count | 12 |
| Controller max files | 5 |
| Aggregate file bytes | 20 MiB |
| Tenant concurrent uploads | 3 |

Các giới hạn này cần được đồng bộ với API contract. Gateway có thể có overhead/buffering khác với parser; cần test thực tế thay vì chỉ so sánh con số cấu hình.

## 14. Upload trực tiếp lên object storage

Với file lớn, hệ thống có thể cấp upload session hoặc signed URL để client gửi trực tiếp đến object storage. Cách này giảm tải data plane cho application nhưng không loại bỏ yêu cầu bảo mật.

Cần kiểm soát:

- Principal/tenant được phép tạo upload session.
- Object key được server tạo hoặc ràng buộc với tenant.
- Signed URL có thời hạn ngắn và quyền chỉ upload vào một object/session.
- Content length/range hoặc policy upload được giới hạn nếu provider hỗ trợ.
- Multipart object upload có giới hạn part count và part size theo provider.
- Tổng object size được xác minh sau khi upload hoàn tất.
- Upload session chưa hoàn tất được abort/cleanup sau expiry.
- Client không thể ghi đè object của tenant khác.
- File chưa được validate/scan không được public hoặc dùng trong nghiệp vụ.

### 14.1. Không tin client báo upload hoàn tất

Client có thể khai báo upload thành công dù object thiếu part, sai kích thước hoặc chưa hoàn tất multipart storage upload. Server cần xác minh object metadata, size, checksum hoặc provider completion result trước khi chuyển trạng thái sang available.

### 14.2. Quota phải tính cả object đang upload

Nếu quota chỉ tăng sau khi upload complete, user có thể tạo nhiều session và chiếm storage tạm vượt mức. Reserve quota khi tạo session và release khi abort/expire. Reconcile định kỳ để xử lý session bị bỏ dở.

## 15. Resumable/chunked upload

Chunked upload chia file thành nhiều phần để có thể resume khi mạng gián đoạn. Nó tạo thêm state và cần giới hạn riêng.

Một upload session nên có:

- Upload ID ngẫu nhiên, không thể đoán.
- Principal và tenant owner đã xác minh.
- Tổng file size tối đa.
- Chunk size tối đa và tối thiểu nếu cần.
- Tổng chunk count tối đa.
- Tổng bytes đã nhận.
- Danh sách chunk ID/index đã nhận.
- Expiry và cleanup policy.
- Checksum hoặc integrity validation.
- Trạng thái created, uploading, completed, aborted, expired.

### 15.1. Kiểm tra tổng bytes

Không chỉ giới hạn từng chunk. Tổng bytes sau khi cộng tất cả chunk không được vượt declared total và server-side maximum. Khi hoàn tất, xác minh số chunk, thứ tự hoặc offset, tổng bytes và checksum theo protocol.

### 15.2. Chống duplicate và chunk overwrite

Chunk retry có thể gửi lại cùng index. Cần semantics rõ: idempotent replace cùng checksum, hoặc từ chối duplicate. Không để một client ghi đè chunk đã xác nhận bằng bytes khác mà không có version/authorization check.

### 15.3. Cleanup session hết hạn

Upload session bị bỏ dở phải tự hết hạn. Cleanup job cần xóa chunk và release quota reservation một cách an toàn. Job cleanup phải kiểm tra owner/state để không xóa nhầm session đang active.

## 16. Giới hạn tài nguyên sau upload

Kích thước file trên wire không phản ánh toàn bộ chi phí xử lý sau upload.

Ví dụ:

- File ZIP nhỏ có thể giải nén thành hàng chục gigabyte.
- PDF có thể chứa rất nhiều trang hoặc object phức tạp.
- Ảnh có kích thước nén nhỏ nhưng pixel dimensions cực lớn.
- CSV có thể có hàng triệu row hoặc một dòng rất dài.
- Office document có thể chứa nhiều embedded object.
- File media có thể làm decoder tiêu tốn CPU và memory.

Cần giới hạn riêng cho bước scan, parse, preview, thumbnail, OCR và archive extraction. Có thể xử lý bất đồng bộ trong worker pool có quota, timeout và concurrency limit.

### 16.1. Archive expansion

Nếu cho phép archive, giới hạn:

- Compressed input size.
- Decompressed total size.
- Số entry.
- Kích thước mỗi entry.
- Độ sâu thư mục.
- Expansion ratio.
- Thời gian giải nén.
- Path traversal và symlink behavior.

Không giải nén archive trực tiếp vào web root hoặc path do client kiểm soát.

### 16.2. Quarantine trước khi xử lý

File upload mới nên có trạng thái pending/quarantine. Sau khi kiểm tra size, type, signature, malware scan và policy, mới chuyển sang trạng thái được sử dụng. Không cho người dùng khác tải hoặc xử lý file chưa qua kiểm tra chỉ vì upload request trả thành công.

## 17. HTTP status và error contract cho upload limit

Response cần cho client biết request bị từ chối vì giới hạn nào ở mức an toàn.

| Tình huống | Status thường dùng | Ý nghĩa |
|---|---|---|
| Tổng request body quá lớn | 413 Content Too Large | Request vượt giới hạn tổng |
| File part quá lớn | 413 Content Too Large | Một file vượt per-file limit |
| Số part vượt ngưỡng | 400 Bad Request hoặc 413 theo contract/parser | Multipart không đáp ứng giới hạn |
| Multipart syntax sai | 400 Bad Request | Boundary/part malformed |
| Media type không hỗ trợ | 415 Unsupported Media Type | Endpoint không nhận định dạng này |
| Tenant/user vượt quota | 413 hoặc 429 theo semantics đã công bố | Không đủ quota hoặc vượt tốc độ |
| Quá nhiều upload đồng thời | 429 Too Many Requests hoặc 503 | Backpressure/capacity limit |
| Upload session hết hạn | 410 Gone hoặc 404 theo contract | Session không còn hợp lệ |
| User không có quyền upload | 403 Forbidden | Authorization thất bại |

Không dùng 413 cho mọi lỗi nếu client cần phân biệt quota, concurrency và malformed request. Error code trong body có thể cụ thể hơn status.

Ví dụ response:

```json
{
  "type": "about:blank",
  "title": "Content Too Large",
  "status": 413,
  "code": "FILE_SIZE_LIMIT_EXCEEDED",
  "detail": "A file exceeds the maximum allowed size.",
  "maxFileBytes": 10485760,
  "traceId": "req-7f31"
}
```

Không đưa path temporary file, stack trace, storage bucket nội bộ hoặc nội dung file vào error response.

## 18. Logging và monitoring upload

Cần theo dõi upload để phát hiện abuse và capacity issue, nhưng không ghi nội dung file hoặc credential.

Metric hữu ích:

- Request bytes nhận được.
- Số file và tổng part count.
- Per-file size và aggregate file bytes.
- Số request bị từ chối theo limit code.
- Upload duration và tốc độ nhận bytes.
- Concurrent uploads theo service/tenant.
- Temporary disk bytes và inode usage.
- Multipart parser error và cleanup failure.
- Upload session active/expired/aborted.
- Quota reserved, consumed và released.
- Object storage multipart upload chưa hoàn tất.
- Worker queue depth và processing duration.

### 18.1. Tránh metric cardinality cao

Không dùng raw user ID, API key hoặc tenant ID làm label không giới hạn. Dùng metric tổng hợp theo endpoint, policy, status và tier; dùng log có kiểm soát để điều tra principal cụ thể.

### 18.2. Không log file content hoặc secret

Không ghi raw multipart body, file bytes, Authorization header, signed URL hoặc credential. Có thể ghi:

- Request ID.
- Principal/client ID đã xác minh.
- Tenant ID theo policy.
- Endpoint và result code.
- Số bytes và part count.
- Upload session ID.
- Storage object reference không nhạy cảm.
- Thời gian xử lý và cleanup outcome.

Filename cũng có thể chứa dữ liệu cá nhân hoặc ký tự điều khiển. Redact/normalize khi log và escape khi hiển thị.

## 19. Kiểm thử giới hạn upload

Kiểm thử phải bao gồm cả request hợp lệ và các biên giới ngay dưới, đúng bằng và vượt ngưỡng.

### 19.1. Request và file size

- Request nhỏ hơn giới hạn.
- Request đúng bằng giới hạn.
- Request vượt một byte.
- Một file đúng per-file maximum.
- Một file vượt per-file maximum.
- Nhiều file mỗi file hợp lệ nhưng aggregate vượt limit.
- Content-Length lớn hơn limit bị từ chối sớm.
- Request streaming không có Content-Length vẫn bị giới hạn.
- Client disconnect giữa chừng.
- Multipart overhead làm tổng request vượt dù file bytes còn trong giới hạn.

### 19.2. Part và field count

- Số file đúng maximum và vượt maximum.
- Tổng part đúng maximum và vượt maximum.
- Nhiều text field nhỏ.
- Một text field vượt byte limit.
- Tổng text bytes vượt limit.
- Duplicate field nhạy cảm.
- Part rỗng.
- Filename/header rất dài.
- Part header count hoặc bytes vượt limit.
- Boundary thiếu, sai hoặc quá dài.
- Nested multipart khi không được hỗ trợ.

### 19.3. Resource và concurrency

- Nhiều upload đồng thời cùng user.
- Nhiều user cùng tenant.
- Nhiều tenant đồng thời.
- Temporary disk gần đầy.
- Inode usage cao.
- Storage chậm hoặc lỗi.
- Parser timeout.
- Slow upload gửi byte nhỏ giọt.
- Cleanup sau timeout, disconnect và process restart.
- Quota reservation race giữa nhiều request.

### 19.4. Chunked và resumable upload

- Chunk đúng size và vượt size.
- Tổng chunk bytes vượt declared total.
- Quá nhiều chunk.
- Chunk duplicate cùng checksum.
- Chunk duplicate khác checksum.
- Session hết hạn.
- Client resume sau disconnect.
- Hai client cùng thao tác một upload ID.
- Abort và cleanup.
- Final object size/checksum không khớp.

### 19.5. Kiểm thử qua toàn bộ pipeline

Chạy test qua gateway/reverse proxy, HTTP server, multipart parser và application. Unit test controller không phát hiện được limit bị áp dụng quá muộn hoặc proxy đã buffer body quá lớn.

Kiểm tra cả browser/client, upload trực tiếp object storage nếu có và đường private/internal. Xác minh request bị từ chối không để lại temporary file, quota reservation hoặc object orphan.

## 20. Những lỗi thiết kế thường gặp

1. **Chỉ giới hạn file size.** Hàng nghìn part nhỏ vẫn làm parser quá tải.
2. **Chỉ giới hạn request size.** Một file có thể chiếm gần hết body hoặc số part vẫn quá lớn.
3. **Chỉ giới hạn file count.** Text field và part header vẫn không bị kiểm soát.
4. **Kiểm tra trong controller.** Parser có thể đã ghi file tạm trước khi controller chạy.
5. **Tin Content-Length.** Streaming/chunked body vẫn cần byte counting thực tế.
6. **Buffer toàn bộ body vào memory.** Request hợp lệ nhưng concurrency cao có thể gây OOM.
7. **Không giới hạn temporary disk.** Upload đồng thời làm đầy volume hoặc inode.
8. **Không cleanup file partial.** Disconnect và parser exception để lại file rác.
9. **Không giới hạn upload duration.** Slow upload giữ connection và worker.
10. **Không có per-tenant quota.** Một tenant có thể chiếm hết capacity.
11. **Quota không atomic.** Request đồng thời vượt mức đã cấp.
12. **Không giới hạn multipart header/boundary.** Parser phải xử lý metadata bất thường.
13. **Nhầm max-file-size với max-part-count.** Đây là các giới hạn độc lập.
14. **Không tính multipart overhead.** Client gửi đủ file bytes nhưng request vẫn vượt tổng limit.
15. **Cho resumable session vô hạn.** Chunk và reservation bị bỏ lại.
16. **Tin client báo upload hoàn tất.** Object storage có thể chưa có đủ bytes.
17. **Không giới hạn giải nén và xử lý hậu upload.** File nhỏ gây chi phí xử lý lớn.
18. **Gateway và application limit lệch nhau.** Tạo lỗi khó chẩn đoán hoặc buffer không cần thiết.
19. **Chỉ test một browser hoặc một route.** Bỏ sót private path và upload client khác.
20. **Log raw multipart body.** Có thể làm lộ dữ liệu và credential.

## 21. Checklist thiết kế và triển khai

Trước khi phát hành endpoint upload, hãy xác nhận:

- [ ] Có request body maximum.
- [ ] Có per-file maximum.
- [ ] Có aggregate file bytes maximum.
- [ ] Có max file count và max total part count.
- [ ] Có max text field count, bytes per field và aggregate field bytes.
- [ ] Có part header count/size và filename length limit.
- [ ] Boundary được parse bằng multipart parser chuẩn và có giới hạn.
- [ ] Gateway, HTTP server và multipart parser có giới hạn tương thích.
- [ ] Request không có Content-Length vẫn bị giới hạn bằng byte counting.
- [ ] Body không bị đọc toàn bộ vào memory trước khi kiểm tra.
- [ ] Memory threshold, temporary directory, disk quota và inode được quản lý.
- [ ] File partial được cleanup khi lỗi, timeout hoặc disconnect.
- [ ] Có timeout nhận body, idle timeout và total upload deadline.
- [ ] Có global, per-instance, per-user và per-tenant concurrency/quota.
- [ ] Quota reservation và usage update có atomicity phù hợp.
- [ ] Upload session/resumable có size, chunk count, expiry và cleanup.
- [ ] Object storage upload được xác minh size/checksum khi finalize.
- [ ] Archive extraction và hậu xử lý có resource limits riêng.
- [ ] File mới ở quarantine/pending cho tới khi validation hoàn tất.
- [ ] Error status/code phân biệt request too large, malformed, quota và concurrency.
- [ ] Log không chứa file content, raw credential hoặc signed URL.
- [ ] Có metric cho bytes, parts, duration, disk, concurrency và cleanup.
- [ ] Test boundary values, malformed multipart, slow upload và concurrent upload.
- [ ] Test qua gateway, server, parser và storage path thực tế.

## 22. Kết luận

Giới hạn upload an toàn cần bao phủ cả kích thước lẫn số lượng. Tổng request size bảo vệ toàn bộ body; per-file size bảo vệ từng file; part count, field count và part header limits bảo vệ multipart parser khỏi request có quá nhiều cấu trúc nhỏ hoặc metadata bất thường. Các giới hạn này cần được enforce trước khi parser tiêu tốn memory hoặc temporary disk.

Một thiết kế tốt kết hợp gateway/server/parser limits, byte counting khi streaming, quota và concurrency theo principal/tenant, timeout và cleanup. Với upload trực tiếp object storage hoặc resumable upload, server vẫn phải kiểm soát session, tổng bytes, số chunk, expiry và kết quả finalize. File sau upload còn cần giới hạn xử lý như giải nén, scan và preview.

Kiểm thử phải chạy qua toàn bộ pipeline, bao gồm request đúng ngưỡng, vượt ngưỡng, nhiều part, slow upload, concurrent upload và cleanup. Khi các giới hạn được định nghĩa rõ theo từng endpoint và được quan sát trong production, API có thể nhận file đúng nhu cầu mà vẫn kiểm soát được memory, disk, network và chi phí xử lý.


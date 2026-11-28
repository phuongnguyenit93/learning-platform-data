# Giới hạn kích thước request tại proxy: Chính sách, thực thi và bảo vệ dịch vụ phía sau

## 1. Tổng quan và mục tiêu học tập

**Giới hạn kích thước request tại proxy** là cơ chế kiểm soát lượng dữ liệu mà một **forward proxy, reverse proxy, API gateway hoặc load balancer lớp ứng dụng (L7)** chấp nhận từ client trước khi xử lý hay chuyển tiếp đến backend. Với một reverse proxy HTTP, giới hạn thường bao gồm kích thước **request body**, nhưng một hệ thống an toàn còn phải kiểm soát riêng **request line/URI, header, phần dữ liệu tải lên, kích thước sau giải nén và số request hoặc kết nối đồng thời**.

Trong chương **Proxy reverse proxy và cân bằng tải** thuộc học phần **SECURITY_NETWORK_SECURITY**, đây là một điểm phòng vệ quan trọng của kiến trúc mạng nhiều lớp. Một client có thể gửi request hợp lệ về cú pháp nhưng quá lớn, khiến proxy phải dùng bộ nhớ, vùng đệm đĩa, băng thông, kết nối upstream hoặc tài nguyên ứng dụng vượt công suất. Giới hạn đúng chỗ giúp **từ chối sớm**, giảm tải phía sau, đồng thời cung cấp lỗi rõ ràng để ứng dụng/client điều chỉnh.

**Ví dụ thực tế:** một API nhận JSON nhỏ, một đường dẫn upload ảnh có thể nhận vài MiB, và endpoint nhập dữ liệu hàng loạt có thể xử lý tệp lớn hơn. Nếu proxy đặt mức 1 MiB cho mọi route, upload hợp lệ bị trả 413; nếu đặt 500 MiB cho tất cả route, endpoint đăng nhập có thể phải đối mặt với payload quá lớn không cần thiết. **Chính sách theo đường dẫn và loại nghiệp vụ** thường hợp lý hơn một ngưỡng duy nhất.

### Sau bài học, bạn có thể

1. Phân biệt giới hạn **request body**, **request line/URI**, **HTTP headers**, **file upload**, **kích thước sau giải mã** và **tổng tài nguyên xử lý**.
2. Giải thích cách reverse proxy thực thi giới hạn với **Content-Length**, **chunked transfer**, HTTP/2, HTTP/3 và request body streaming.
3. Hiểu sự khác nhau giữa **từ chối trước khi nhận body** với **phát hiện vượt ngưỡng khi đang nhận hoặc chuyển tiếp**.
4. Cấu hình và đọc đúng ý nghĩa những directive Nginx như **client_max_body_size**, **proxy_request_buffering**, **client_body_buffer_size** và **client_body_timeout**.
5. Phối hợp hạn mức qua **CDN/WAF → ingress/proxy → API gateway → ứng dụng/storage**, không tạo lỗ hổng bypass hoặc trả lỗi khó hiểu.
6. Thiết kế thử nghiệm có kiểm soát, phân tích HTTP **413**, giám sát tài nguyên proxy và phân biệt chặn nhầm với traffic độc hại.

## 2. Proxy nào thực sự có thể giới hạn request?

**Proxy** là trung gian nhận, xử lý hoặc chuyển tiếp traffic giữa client và dịch vụ. Khả năng quan sát kích thước request phụ thuộc vào việc nó có **hiểu giao thức ứng dụng và nhìn được dữ liệu cần kiểm tra** không.

| Thành phần | Vai trò | Khả năng áp request size limit |
| --- | --- | --- |
| **Reverse proxy HTTP** | Nhận HTTP(S) trước backend, route/cân bằng tải, TLS termination nếu được cấu hình | Thường có thể giới hạn HTTP request body/header/URI theo policy |
| **API gateway** | Xác thực, định tuyến API, quota, transform và kiểm soát request | Có thể có giới hạn theo API/route, schema, size hoặc parser |
| **WAF** | Kiểm tra HTTP, áp quy tắc bảo vệ ứng dụng | Có thể kiểm tra body và kích thước, nhưng cần phân biệt inspection limit và hard enforcement |
| **CDN / edge HTTP service** | Điểm tiếp nhận và cache/giảm tải ở biên mạng | Có thể từ chối body lớn trước khi traffic tới origin; phụ thuộc dịch vụ/tier |
| **Load balancer L7** | Phân phối request dựa trên HTTP host/path/header | Có thể có giới hạn HTTP hoặc cần bộ lọc/chính sách bổ sung |
| **Load balancer L4 / TCP passthrough** | Chuyển TCP/UDP dựa trên địa chỉ/cổng | Thường **không tự hiểu body HTTP** nếu không giải mã và xử lý L7 |
| **Forward proxy** | Trung gian truy cập từ client ra ngoài | Có thể giới hạn request tải lên theo policy nếu thấy được HTTP cần xét |
| **Backend application** | Phân tích, giải mã, lưu hoặc xử lý nghiệp vụ | Phải có giới hạn riêng cho body, cấu trúc dữ liệu và chi phí xử lý |

**Điểm cốt lõi:** một thiết bị nhận traffic TLS passthrough mà không giải mã/parse HTTP **không thể áp giới hạn chính xác theo JSON body hay URI** chỉ bằng cách nhìn độ dài packet. Nó có thể giới hạn kết nối, tốc độ, băng thông hoặc dữ liệu theo dòng kết nối ở lớp khác, nhưng không đồng nghĩa với HTTP request body limit.

### 2.1. Giới hạn kích thước không đồng nghĩa giới hạn tốc độ

- **Size limit:** mỗi request được phép chứa tối đa bao nhiêu byte theo định nghĩa bộ đếm.
- **Rate limit:** một định danh được gửi bao nhiêu request/giây hoặc request/phút.
- **Connection limit:** có bao nhiêu kết nối đang mở đồng thời.
- **In-flight request limit:** bao nhiêu request đang được xử lý.
- **Bandwidth limit:** bao nhiêu bit/byte truyền trong mỗi đơn vị thời gian.
- **Timeout:** mỗi pha nhận header/body/chờ upstream được kéo dài bao lâu.

Một client có thể gửi **một request 100 MiB** khiến proxy tốn nhiều tài nguyên nhưng không vượt rate limit 10 RPS. Ngược lại, 10.000 request 100 byte có thể vượt rate limit nhưng mỗi request vẫn nằm dưới size limit.

## 3. Hiểu đúng những “kích thước” khác nhau

### 3.1. Cấu trúc HTTP/1.1 ở mức khái niệm

~~~http
POST /api/orders HTTP/1.1
Host: api.lab.example
Content-Type: application/json
Content-Length: 37

{"items":[{"sku":"A1","quantity":1}]}
~~~

Ví dụ trên có body JSON ASCII **37 byte**. Đây không phải toàn bộ số byte đi qua kết nối: ngoài body còn có request line, headers, các ký tự phân cách và framing giao thức. **Content-Length: 37** mô tả kích thước phần nội dung theo quy tắc của HTTP framing ở thông điệp này; nó không đồng nghĩa proxy dùng 37 byte bộ nhớ hoặc request đầy đủ chỉ có 37 byte.

### 3.2. Bảng phân biệt các loại giới hạn

| Đại lượng | Dữ liệu được đo | Rủi ro nếu bỏ sót |
| --- | --- | --- |
| **Request target / URI** | Đường dẫn và query trong request-target | Query quá dài, log lớn, parser xử lý tốn tài nguyên |
| **Header line/field** | Mỗi field hoặc dòng header theo giao thức | Cookie/token/header lớn làm cạn vùng đệm |
| **Aggregate headers** | Tổng header hoặc header block đã giải mã | Rất nhiều header nhỏ hoặc một block quá lớn |
| **Request body** | Nội dung thông điệp HTTP mà proxy nhận | Bộ nhớ/đĩa/băng thông, đẩy tải lớn tới backend |
| **Per-file upload** | Kích thước từng file trong multipart/form-data | Một file quá lớn dù tổng request chưa vượt hạn |
| **Total multipart body** | Tổng bytes của tất cả part, field, boundary và metadata | Nhiều part cộng dồn hoặc nhiều file nhỏ |
| **Per-field / field count** | Kích thước và số lượng form field | Parser/schema và bộ nhớ ứng dụng |
| **Compressed/encoded size** | Số byte body ở dạng biểu diễn có nén khi nhận | Body nén nhỏ vượt qua limit dựa trên bytes trên dây |
| **Decoded/decompressed size** | Nội dung sau giải nén/giải mã theo lớp xử lý | Decompression bomb và bộ nhớ/CPU |
| **Parsed object / workload cost** | Số phần tử JSON, độ sâu XML, số thao tác GraphQL, DB cost | Payload nhỏ nhưng tác vụ xử lý rất nặng |
| **Concurrent buffered bytes** | Tổng dung lượng request đang được đệm đồng thời | Cạn RAM hoặc đĩa dù từng request dưới hạn |

**Định nghĩa bộ đếm phải theo sản phẩm và từng tầng.** Ví dụ một proxy có thể kiểm tra kích thước **HTTP message body** trước khi ứng dụng giải mã **Content-Encoding: gzip**; một tầng khác có thể giới hạn dữ liệu sau giải nén. Không tự suy ra body limit tại proxy đồng thời xử lý mọi biến thể nén.

### 3.3. Đơn vị byte, KiB, MiB

Trong bài, sử dụng:

~~~text
1 KiB = 1.024 byte
1 MiB = 1.048.576 byte

128 KiB = 131.072 byte
1 MiB   = 1.048.576 byte
20 MiB  = 20.971.520 byte
~~~

Một số hệ thống hiển thị **KB/MB** theo hệ thập phân hoặc dùng ký hiệu k/m với quy ước khác nhau. Trước khi chốt ngưỡng, hãy đọc tài liệu sản phẩm và **thử tại ranh giới bằng số byte thực tế** thay vì chỉ nhìn tên đơn vị trong cấu hình.

### 3.4. Multipart có overhead

Với **multipart/form-data**, kích thước body gồm **dữ liệu file + các field khác + boundary và header của từng part**. Một file đúng 20 MiB trong request multipart có thể khiến **tổng body lớn hơn 20 MiB** và bị chặn nếu proxy đặt body limit đúng 20 MiB.

Ví dụ:

~~~text
File:                   10.000.000 byte
Form fields:                  500 byte
Multipart boundaries/
per-part metadata:           700 byte (minh họa)
Total HTTP message body: 10.001.200 byte
~~~

Các con số overhead chỉ là ví dụ; thay đổi theo tên field, filename, Content-Type và nội dung form. Nếu yêu cầu sản phẩm là “tệp không quá 20 MiB”, cần đặt **per-file limit tại ứng dụng/storage** và **total request limit ở proxy có khoảng dư hợp lý** cho framing/form fields, đồng thời giới hạn số part.

### 3.5. Kích thước header khác body

Một request có body 100 byte vẫn có thể mang cookie hoặc JWT/header khổng lồ. **client_max_body_size** của Nginx không phải cơ chế xử lý các header quá lớn. Các hạn mức **request line, header field và tổng decoded headers** thường có directive/setting khác nhau và có thể dẫn tới lỗi HTTP **400, 414 hoặc 431**, tùy loại lỗi và triển khai.

## 4. Threat model của request quá lớn tại proxy

### 4.1. Những tài nguyên có thể bị tiêu thụ

| Tài nguyên | Cách request lớn tạo áp lực | Biện pháp bổ sung |
| --- | --- | --- |
| RAM proxy | Body buffering, parse hoặc lưu metadata | Size limit, vùng đệm hợp lý, concurrency cap |
| Đĩa tạm | Buffer tràn bộ nhớ rồi ghi file tạm | Giám sát free disk, quota, đường dẫn temp và cleanup |
| Socket và FD | Upload chậm hoặc nhiều kết nối giữ lâu | Timeout, concurrency/connection limits |
| CPU | Giải nén, kiểm tra WAF, xử lý JSON/XML | Giới hạn decoded/parsed size, parser limits |
| Băng thông mạng | Tải request lớn qua CDN, proxy và upstream | Edge enforcement, bandwidth control và upstream capacity |
| Backend workers | Request lớn làm giữ thread/task, xử lý lâu | In-flight limit, queue cap, backpressure |
| Database/storage | Ghi tệp hoặc đối tượng quá lớn | Quota, schema/object size limits, cleanup |
| Log/observability | Ghi nguyên header/body gây tăng dữ liệu nhạy cảm và chi phí | Chỉ log metadata an toàn, không log toàn body |

**Một body limit riêng lẻ không ngăn được DoS.** Nhiều request nhỏ có thể làm quá tải CPU hoặc connection pool, còn một đường Internet bão hòa bởi volumetric attack phải được bảo vệ ở **upstream/CDN/ISP**, không chỉ tại reverse proxy ở origin.

### 4.2. Kịch bản sai chính sách

1. **API JSON:** client gửi body vài chục MiB tới endpoint chỉ cần vài KiB, gây parse tốn RAM/CPU.
2. **Upload hợp lệ:** người dùng tải tệp 12 MiB nhưng proxy đặt limit 1 MiB và backend chấp nhận 20 MiB; request bị chặn trước backend.
3. **Multipart nhiều file:** từng file nhỏ nhưng tổng body hoặc số part lớn vượt công suất.
4. **Nén mạnh:** body trên dây nhỏ nhưng dữ liệu giải nén rất lớn, vượt khả năng parser.
5. **Slow upload:** client gửi chậm làm giữ kết nối; size limit có thể chưa bị chạm nhưng tài nguyên bị sử dụng lâu.
6. **Origin bypass:** CDN áp limit nhưng origin có IP công khai và cho truy cập trực tiếp.
7. **Streaming không kiểm soát:** proxy chuyển dữ liệu đến backend trước khi biết tổng kích thước; backend đã bắt đầu xử lý/ghi một phần.

### 4.3. Mục tiêu thiết kế

Chính sách phải đồng thời:

- **Từ chối sớm** request vượt ngưỡng, ưu tiên trước điểm nghẽn.
- **Cho phép nghiệp vụ hợp lệ**, gồm upload và các định dạng có overhead.
- **Không tạo đường bypass** qua hostname, route, method, ingress hoặc origin khác.
- **Có giới hạn bổ sung** cho decoded size, parser complexity, timeout, concurrency và storage.
- **Quan sát được**, xác định chính xác lớp chặn khi có 413 hoặc lỗi khác.
- **Vận hành được**, có cấu hình versioned, thử nghiệm ranh giới, rollout và rollback.

## 5. Kiến trúc kiểm soát nhiều lớp

~~~mermaid
flowchart LR
    C["Client / Browser / SDK"] --> E["CDN / Edge WAF<br/>Lọc sớm, hạn mức dịch vụ"]
    E --> LB["Load balancer L7<br/>Định tuyến TLS/HTTP"]
    LB --> P["Reverse proxy / Ingress<br/>Body, header, timeout, buffer"]
    P --> G["API Gateway<br/>Route, auth, quota, schema"]
    G --> A["Application<br/>Decoded/parsed/body/file checks"]
    A --> ST["Storage / Database<br/>Object quota, cleanup"]
    P -. "413 khi vượt body limit" .-> C
    A -. "400/413/422 tùy lỗi" .-> C
~~~

Đây là **sơ đồ chức năng**: thực tế CDN và WAF có thể cùng dịch vụ, gateway và ingress có thể cùng một proxy, hoặc ứng dụng đứng ngay sau load balancer. Không cần thêm nhiều hop chỉ để có nhiều lớp; cần hiểu **điểm nào thực thi hạn mức nào**.

### 5.1. Tầng nào phải làm gì?

| Tầng | Chính sách kích thước điển hình | Lý do |
| --- | --- | --- |
| CDN/Edge | Body/HTTP request maximum do nền tảng hỗ trợ | Tránh traffic lớn tới mạng origin |
| WAF | Body inspection/enforcement theo khả năng sản phẩm | Chặn payload vượt giới hạn hoặc dấu hiệu độc hại |
| Reverse proxy/Ingress | Global/route body cap; header/URI cap; buffer/timeout | Bảo vệ trước backend, điều phối upload |
| API gateway | Route/method-specific size, schema/quota | Phù hợp hợp đồng API và auth |
| Ứng dụng | Decoded bytes, multipart file/field count, JSON/XML depth | Bảo vệ parser và logic nghiệp vụ |
| Storage / DB | File/object size, quota, access policy, lifecycle | Bảo vệ lưu trữ và tài nguyên lâu dài |

**Đừng trông đợi proxy L7 hiểu toàn bộ ngữ nghĩa ứng dụng.** Proxy có thể biết tổng số byte body nhưng không biết file nào là hình ảnh hợp lệ hoặc dữ liệu JSON có một triệu phần tử lồng sâu. Các điều kiện đó phải được kiểm tra ở tầng hiểu dữ liệu hoặc bằng mô-đun chuyên dụng được kiểm chứng.

### 5.2. Đường bypass phải được chặn

Nếu website yêu cầu mọi HTTP request qua CDN/WAF/proxy, địa chỉ origin không nên truy cập tùy tiện từ Internet. Có thể dùng firewall/security group chỉ cho nguồn đã phê duyệt, kết nối riêng hoặc xác thực giữa các tầng tùy kiến trúc. Ngoài ra cần xét:

- IPv4 và IPv6 có đi cùng chính sách không?
- Có hostname/API phụ, cổng admin hoặc ingress thứ hai không?
- Request qua VPN, peering nội bộ hoặc service mesh có bỏ qua lớp giới hạn không?
- Các route proxy thực sự match location/virtual host nào?
- Có một load balancer node chưa nhận cấu hình mới không?

**Một rule 413 trên public hostname không chứng minh mọi lối vào backend đều được bảo vệ.**

## 6. Thiết kế hạn mức theo route và hợp đồng API

Mức dưới đây chỉ **để minh họa cách phân tầng**, không phải giá trị chuẩn hoặc khuyến nghị có thể áp ngay cho production.

| Route / nhóm nghiệp vụ | Kích thước body ví dụ | Điều kiện bổ sung |
| --- | --- | --- |
| **POST /auth/login** | 16 KiB | Rate limit, auth lockout phù hợp, validate JSON |
| **POST /api/orders** | 128 KiB | JSON schema, số dòng hàng, idempotency |
| **POST /api/search** | 64 KiB | Query cost/complexity, timeout, concurrency |
| **POST /hooks/payment** | 1 MiB | Kiểm tra chữ ký webhook, chống replay, queue |
| **POST /upload/avatar** | 8 MiB request | Per-file 5 MiB, MIME/content validation, malware scan |
| **POST /upload/document** | 24 MiB request | Per-file 20 MiB, số file, định dạng, scan và storage quota |
| **POST /reports/import** | 32 MiB hoặc upload ngoài ứng dụng | Streaming/batch parser limit, job quota |
| **GET /health** | 0 hoặc body rất nhỏ theo hợp đồng | Chặn body không mong đợi nếu tầng xử lý hỗ trợ |

Nếu một request upload có thể chứa **nhiều file**, cần tính tổng kích thước phù hợp; một body limit 24 MiB không có nghĩa cho phép tải lên hai file 20 MiB trong một request.

### 6.1. Quy tắc xác định ngưỡng

1. Đo **p50/p95/p99 và cực đại hợp lệ** của body theo route/tenant trong một khoảng đại diện.
2. Xem hợp đồng API, định dạng, overhead multipart và giới hạn của client SDK.
3. Tính công suất proxy RAM/đĩa, worker, đường tới backend, quota storage.
4. Đặt **hard limit** cao hơn mức hợp lệ cần thiết nhưng không mở vô hạn.
5. Đặt **decoded/parsed/field count limits** ở lớp hiểu dữ liệu.
6. Có exception chỉ cho route/định danh đã được phê duyệt; ghi owner và ngày hết hạn.
7. Xem lại khi sản phẩm tăng file size, xuất báo cáo lớn hoặc thay architecture upload.

Không suy ra rằng “p99 là 2 MiB thì chọn 2 MiB” luôn đúng: một số tác vụ hiếm nhưng hợp lệ có thể lớn hơn. Cần kết hợp dữ liệu với **hợp đồng nghiệp vụ và biên độ dung lượng**.

### 6.2. Lợi ích của tách endpoint upload

Thay vì tăng limit của toàn ứng dụng, có thể tách:

- API JSON với body nhỏ, bảo vệ nghiêm.
- Upload route với hạn mức lớn hơn, tách pool/worker/storage.
- Endpoint báo trạng thái upload/job, yêu cầu nhỏ.
- Dịch vụ object storage nhận file trực tiếp bằng **URL/token upload có thời hạn và phạm vi**, nếu nền tảng hỗ trợ.

Việc upload trực tiếp vào storage có thể giảm tải reverse proxy, nhưng cần kiểm soát **quyền upload, object key, content-size/type policy, scanning, trạng thái hoàn tất và lifecycle**. Không đưa presigned URL ra rồi mặc định đã chặn được file lớn hoặc nội dung độc hại.

## 7. HTTP framing: Proxy biết request lớn thế nào?

### 7.1. Content-Length cho phép phát hiện sớm

Với HTTP/1.1 có **Content-Length** hợp lệ, proxy có thể dựa vào độ dài được khai báo để biết body **dự kiến** trước khi nhận toàn bộ. Nếu Content-Length vượt hạn mức áp dụng, một proxy HTTP phù hợp có thể **phản hồi lỗi sớm**, tránh tải cả body vào bộ nhớ hoặc ổ đĩa.

Tuy nhiên:

- **Content-Length do phía gửi khai báo**, không phải phép đo độc lập toàn bộ dữ liệu đã nhận.
- Proxy cần xử lý framing theo chuẩn, phát hiện trường hợp thiếu, sai, không nhất quán hoặc mâu thuẫn.
- Khi request không có chiều dài biết trước, vẫn phải **đếm byte thực nhận** và áp giới hạn trong quá trình xử lý.
- Khi body quá lớn và connection có thể tái sử dụng, proxy phải xử lý tình trạng còn dữ liệu chưa đọc đúng cách để tránh nhầm phần body thành request tiếp theo.

Do đó, không thiết kế size limit chỉ dựa trên việc kiểm tra giá trị header theo biểu thức chuỗi mà **không kiểm soát framing và số byte thực tế**.

### 7.2. HTTP/1.1 với Transfer-Encoding: chunked

Ở HTTP/1.1, **Transfer-Encoding: chunked** cho phép truyền nội dung theo nhiều chunk mà không cần biết toàn bộ body ngay từ đầu. Proxy phải **parse framing đúng chuẩn**, cộng dồn kích thước nội dung và thực thi hạn mức trong khi nhận.

~~~text
Minh họa:
  Request body limit = 128 KiB
  Dữ liệu nội dung chunk nhận được:
    60 KiB + 50 KiB + 30 KiB
  Tổng nội dung = 140 KiB > 128 KiB

Kết luận:
  Không thể chỉ xem có hay không Content-Length.
  Proxy phải phát hiện vượt ngưỡng khi tổng dữ liệu nhận tăng.
~~~

Ví dụ trên chỉ mô tả phép cộng byte; **chunked framing** còn có chunk-size lines, CRLF, trailer fields theo giao thức, và các giới hạn framing/trailer riêng. Không tự coi toàn bộ overhead chunked là “nội dung file” nếu sản phẩm định nghĩa body limit khác.

**Phân tích bảo mật:** các trường hợp Content-Length/Transfer-Encoding mâu thuẫn, request framing không nhất quán giữa proxy và backend có thể dẫn đến rủi ro **HTTP request smuggling/desynchronization**. Cần sử dụng parser tuân chuẩn, loại request framing mơ hồ và giữ proxy–backend đồng nhất; **size limit không thay thế việc xử lý framing đúng**.

### 7.3. HTTP/2 và HTTP/3

HTTP/2 và HTTP/3 sử dụng framing theo **stream**, không dùng HTTP/1.1 chunked transfer coding trong cùng cách thức. Một connection có thể phục vụ **nhiều HTTP requests/streams đồng thời**, nên giới hạn cần áp cho **mỗi request/stream** theo semantics của proxy, đồng thời giới hạn tổng tài nguyên nhiều stream.

**Content-Length** nếu xuất hiện vẫn chịu quy tắc nhất quán với lượng nội dung theo giao thức, nhưng không nên suy ra rằng một connection tương đương một request. Ngoài body size, HTTP/2/3 có các giới hạn độc lập với **header block đã giải mã, streams đồng thời, flow control, buffering và tài nguyên connection**.

**HPACK/QPACK** nén biểu diễn header trên đường truyền, vì thế một **header block nhỏ khi mã hóa** vẫn có thể tạo lượng thông tin header lớn sau giải mã. Cần quan tâm giới hạn header của **HTTP stack sau giải mã**, không nhầm với HTTP body cap.

### 7.4. Content-Encoding và giải nén

~~~text
Client gửi:
  Content-Encoding: gzip
  Body trên dây:          200 KiB
  Body sau giải nén:       12 MiB

Proxy giới hạn 1 MiB trên kích thước body nhận được:
  Có thể không chặn 200 KiB nếu không giải nén/kiểm tra decoded size.

Application hoặc WAF giải nén:
  Cần giới hạn decoded bytes, CPU, depth/ratio và thời gian.
~~~

**Transfer-Encoding** và **Content-Encoding** không phải cùng một khái niệm. Transfer-Encoding mô tả cơ chế framing/transfer ở HTTP/1.1, còn Content-Encoding liên quan đến biểu diễn nội dung (ví dụ gzip). Những giới hạn của **HTTP body nhận được** và **nội dung sau giải nén** có thể nằm ở các tầng khác nhau.

### 7.5. Request line, header và trailer

Các hạn mức sau thường tách rời:

- Độ dài URI/request-target và query string.
- Tổng kích thước field/header và số field.
- Tổng decoded header size của HTTP/2/3.
- Trailer fields ở nơi protocol và proxy chấp nhận.
- Kích thước request body.

Một phản hồi 413 không thể dùng làm bằng chứng mọi loại header và URI đều được giới hạn đầy đủ. Khi thiết kế API nhận cookie hoặc Authorization token lớn, phải kiểm tra **giới hạn header riêng**; chỉ tăng body limit sẽ không xử lý lỗi từ header.

## 8. Từ chối sớm, buffering và streaming

### 8.1. Buffered request processing

Khi **request buffering** được bật, proxy thường nhận trước một phần hoặc toàn bộ request body, lưu tạm ở bộ nhớ/đĩa theo cấu hình, rồi mới chuyển tới upstream theo cách triển khai.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Reverse proxy
    participant A as Backend
    C->>P: Headers + body
    Note over P: Kiểm tra Content-Length / đếm byte
    alt Body không vượt hạn và hợp lệ
        Note over P: Buffer trong RAM/đĩa nếu cần
        P->>A: Chuyển request đã nhận
        A-->>P: Response
        P-->>C: Response
    else Body vượt hạn
        P-->>C: HTTP 413 / đóng kết nối theo policy
        Note over A: Tránh nhận toàn bộ body từ request bị chặn
    end
~~~

**Ưu điểm:** proxy có thể hạn chế lượng dữ liệu lớn đi vào backend và quản lý việc đọc body trước khi mở/chuyển request lên upstream. **Nhược điểm:** RAM/đĩa temp và thời gian chờ tăng, đặc biệt khi nhiều upload đồng thời.

Việc proxy có giữ **toàn bộ body**, ghi file tạm hay chuyển dần phụ thuộc loại request, cấu hình, phiên bản và module được sử dụng. Không mặc định rằng mọi proxy luôn buffer trọn body trước upstream.

### 8.2. Streaming request processing

Với **streaming**, proxy có thể chuyển từng phần body tới backend trong khi vẫn đang nhận dữ liệu từ client. Phương án này phù hợp upload lớn, xử lý theo luồng, ứng dụng cần độ trễ thấp hoặc khi không muốn ghi nhiều dữ liệu vào temp disk.

**Trade-off quan trọng:** nếu chưa biết tổng kích thước và proxy chỉ phát hiện request vượt limit sau khi nhận một lượng dữ liệu, backend **có thể đã thấy và xử lý một phần body** trước khi proxy từ chối. Vì vậy:

1. Backend phải tự giới hạn body và chịu được việc kết nối bị cắt giữa chừng.
2. Không commit dữ liệu/giao dịch quan trọng chỉ vì đã nhận vài chunk đầu.
3. Sử dụng upload session, transaction boundary hoặc **temporary object + finalize sau kiểm tra** nếu cần.
4. Có cleanup cho file tạm và upload không hoàn tất.
5. Giám sát bytes đã forward, thời gian và lỗi bị ngắt.

**Bật streaming không phải cách tự động bỏ qua request size limit.** Ngược lại, “không buffering” cũng không bảo đảm backend an toàn nếu không có các cơ chế kiểm tra và rollback thích hợp.

### 8.3. Ví dụ minh họa về sự khác biệt

| Trường hợp | Buffered | Streaming |
| --- | --- | --- |
| Body size biết ngay từ Content-Length | Proxy có thể reject sớm | Proxy cũng có thể reject sớm khi parser/checker hỗ trợ |
| Kích thước chưa biết trước | Có thể đếm đủ trước khi forward | Có thể forward một phần rồi mới chạm hạn |
| Proxy RAM/đĩa temp | Có thể tăng theo số upload đồng thời | Thường ít đệm toàn body hơn |
| Backend nhận dữ liệu trước khi proxy nhận xong | Thường ít hơn khi full buffering | Có thể nhận sớm |
| Upload chậm | Giữ client connection/đệm lâu | Có thể giữ upstream connection lâu |
| Xử lý lỗi giữa chừng | Có thể từ chối trước khi gửi lên backend | Cần thiết kế xử lý partial state |

### 8.4. Backpressure và quá nhiều upload đồng thời

Một body cap **20 MiB** và 1.000 upload đồng thời không có nghĩa proxy chỉ cần 20 MiB RAM/đĩa. Nếu mỗi request được đệm, tổng **working set** có thể rất lớn, cộng với buffers, headers, connection state và hoạt động của backend.

~~~text
Minh họa giới hạn trên về dữ liệu payload đồng thời:
  100 request cùng lúc × 20 MiB/request = 2.000 MiB

Đây không phải dự báo RAM thực tế:
  Một số bytes có thể ở socket, RAM, temp disk hoặc upstream.
  Cấu hình buffering/streaming quyết định cách phân bổ.
~~~

Vì vậy cần cả **concurrent upload cap, bandwidth shaping, queue limit, temp disk budget, timeouts** và monitoring. Không tăng ngưỡng request lớn mà bỏ qua khả năng chịu tải của proxy.

### 8.5. Slow upload và timeout

Size limit chỉ đo **lượng dữ liệu**, không đo **thời gian**. Một client gửi body rất chậm có thể giữ kết nối dài mà chưa chạm hạn. Hạ tầng cần kiểm soát timeout đọc header/body, connection/stream concurrency và giới hạn tốc độ tối thiểu nếu sản phẩm hỗ trợ.

Tuy nhiên, timeout quá ngắn có thể chặn nhầm người dùng qua mạng di động hoặc upload hợp lệ. Đọc rõ semantics: một số **body read timeout** được tính **giữa hai lần đọc** thay vì tổng thời gian hoàn tất request.

## 9. Ví dụ cấu hình Nginx: Body cap theo route

Trong Nginx HTTP module, directive **client_max_body_size** được dùng để đặt **kích thước body tối đa của client request**. Khi kích thước request body vượt ngưỡng, Nginx có thể trả **HTTP 413 Content Too Large**. Theo tài liệu Nginx, directive này có thể đặt ở cấp **http**, **server**, hoặc **location**; giá trị mặc định thông dụng là **1m**, và **0** có nghĩa vô hiệu hóa kiểm tra kích thước bằng directive này.

**Không đặt 0 cho toàn bộ service** như một cách xử lý chung khi người dùng gặp 413. Hãy hiểu yêu cầu nghiệp vụ, tăng đúng route và giữ giới hạn ở những lớp còn lại.

### 9.1. Cấu hình lab minh họa

Giả định backend lab đang nghe tại **127.0.0.1:8080** và Nginx lab nghe tại **127.0.0.1:8088**:

~~~nginx
# Ví dụ đặt trong nginx.conf có ngữ cảnh http.
# Không chép thêm một khối http bên trong http đã tồn tại.
http {
    upstream lab_backend {
        server 127.0.0.1:8080;
    }

    server {
        listen 127.0.0.1:8088;
        server_name proxy.lab.example;

        # Mức chung cho route không được khai báo riêng.
        client_max_body_size 1m;

        # JSON API: giới hạn nhỏ hơn mức toàn server.
        location /api/ {
            client_max_body_size 128k;
            proxy_pass http://lab_backend;
        }

        # Tải file: giới hạn lớn hơn và nhận body theo buffering.
        location /upload/ {
            client_max_body_size 24m;
            proxy_request_buffering on;
            proxy_pass http://lab_backend;
        }
    }
}
~~~

**Ý nghĩa các con số trong ví dụ:**

- **128k** là hạn mức body cho request khớp location **/api/**; không phải 128.000 request hoặc 128 KB/giây.
- **24m** là body cap minh họa cho **/upload/**; có thể phải dành chỗ cho multipart overhead nếu per-file max là 20 MiB.
- **1m** là mặc định tại server này cho location không override.
- **proxy_request_buffering on** kiểm soát cách Nginx nhận/chuyển request body; **không phải** directive đặt tổng dung lượng tối đa.
- Nếu Nginx được đặt sau CDN hoặc load balancer khác, **tầng phía trước có thể trả 413 trước** khi Nginx nhận request.
- Cấu hình ví dụ chỉ nghe loopback, chưa có TLS, log vận hành, upstream resilience hay authn/authz của sản phẩm.

### 9.2. Một location streaming khác

Nếu backend đã được thiết kế để xử lý upload theo luồng và cleanup phần dữ liệu chưa hoàn tất, có thể cân nhắc:

~~~nginx
location /stream-upload/ {
    client_max_body_size 24m;
    proxy_request_buffering off;
    proxy_http_version 1.1;
    proxy_pass http://lab_backend;
}
~~~

Đây là **đoạn location bổ sung** phải đặt trong server có upstream phù hợp; không phải cấu hình Nginx đầy đủ. Với **proxy_request_buffering off**, Nginx có thể gửi body tới upstream khi đang nhận từ client, nên ứng dụng phải xử lý việc **stream bị cắt khi size limit bị vượt**.

**Điểm dễ bỏ sót:** Nginx có các điều kiện buộc phải buffer dữ liệu, ví dụ cách xử lý **HTTP/1.1 chunked body khi proxying với phiên bản giao thức upstream không phù hợp**. Vì vậy nên kiểm tra tài liệu phiên bản, **proxy_http_version**, nguồn traffic và hành vi thực nghiệm. Không hứa rằng chỉ thêm một directive **off** sẽ loại mọi file tạm hoặc mọi buffering.

### 9.3. Những directive thường bị nhầm

| Directive / nhóm | Chức năng | Không phải |
| --- | --- | --- |
| **client_max_body_size** | Giới hạn body nhận từ client | Rate limit hoặc giới hạn số file trong form |
| **client_body_buffer_size** | Kích thước buffer dùng khi đọc request body, liên quan khả năng dùng file tạm | Hard cap của request body |
| **client_body_temp_path** | Vị trí file tạm lưu request body khi Nginx cần | Hạn mức dung lượng request |
| **client_body_timeout** | Timeout khi đọc body từ client theo semantics Nginx | Thời gian tối đa cho toàn bộ upload trong mọi tình huống |
| **proxy_request_buffering** | Quyết định buffering request body trước/upstream | Response buffering hoặc bật/tắt size limit |
| **proxy_buffering** | Buffer **response từ upstream** theo cấu hình | Kiểm soát kích thước request client |
| **limit_req** | Giới hạn request rate | Giới hạn bytes của mỗi body |
| **limit_conn** | Giới hạn connection theo semantics module | Giới hạn bytes/request |
| **large_client_header_buffers** | Dùng cho nhận request line/header lớn theo giới hạn/semantics Nginx | Body limit |
| **proxy_read_timeout** | Timeout đọc phản hồi từ upstream | Giới hạn request body |

Mỗi directive có phạm vi ngữ cảnh và hành vi riêng theo phiên bản Nginx. **Không tự đặt các giá trị rất lớn chỉ để hết lỗi**, đặc biệt khi backend và đĩa temp chưa được đo công suất.

### 9.4. Validate cấu hình Nginx

Trong lab có Nginx đã cài và quyền quản trị phù hợp:

~~~bash
# Chỉ kiểm tra cú pháp/cấu hình, không tự triển khai.
nginx -t

# Khi thay đổi đã được phê duyệt, thao tác reload
# phải theo runbook của môi trường cụ thể.
~~~

**nginx -t thành công chưa chứng minh policy body cap hoạt động đúng**: location matching, reverse proxy chain, cấu hình đã reload hay chưa, route exception, và số byte body thực nhận vẫn cần được kiểm thử.

## 10. Nginx không phải lựa chọn duy nhất

| Nền tảng | Cách tiếp cận | Lưu ý quan trọng |
| --- | --- | --- |
| **Apache HTTP Server (httpd)** | Có cơ chế như **LimitRequestBody** để giới hạn HTTP request body theo ngữ cảnh hỗ trợ | Đừng nhầm với giới hạn request line/header; kiểm tra module/version và scope |
| **HAProxy** | Có thể xử lý HTTP L7, các ACL/rules và buffering theo cấu hình | **tune.bufsize** là kích thước buffer HTTP, không phải một hard body size policy hoàn chỉnh |
| **Envoy** | Có thể dùng bộ lọc/body buffering hoặc policy ở API gateway/route để áp giới hạn | Kiểm tra filter có thực sự được gắn vào các tuyến HTTP và hệ quả full buffering |
| **Kubernetes Ingress controller** | Thường có annotation/ConfigMap/CRD tùy loại controller | **Ingress là API/khuôn mẫu**; không có một annotation size limit chuẩn dùng chung cho mọi controller |
| **Cloud API gateway / managed L7 LB** | Có thể có giới hạn body do platform cố định và/hoặc policy người dùng | Một số hard platform caps không thể tăng bằng config ứng dụng |
| **CDN/WAF** | Có ngưỡng HTTP/body inspection và có thể có enforcement riêng | **Inspection limit** không nhất thiết là **reject limit** |

Trong một kiến trúc nhiều tầng, hãy tra tài liệu **đúng nền tảng, phiên bản, mode TLS và route**. Không xem các tên như “buffer size”, “max payload”, “request body”, “max inspection” là đồng nghĩa nếu chưa biết chúng đếm những byte nào và hành động khi vượt ngưỡng.

### 10.1. Bộ đệm của HAProxy không tự là giới hạn toàn body

Một cấu hình buffer vài chục KiB có thể ảnh hưởng dữ liệu HTTP mà HAProxy lưu khi thực thi ACL/filter, nhưng **body streaming có thể vượt dung lượng buffer trong quá trình truyền**. Nếu cần chặn tổng request body vượt 20 MiB, phải dùng cơ chế có khả năng **đếm/từ chối toàn bộ body theo semantics sản phẩm**, hoặc đặt giới hạn tại gateway/backend khác. Tránh viết ACL chỉ nhìn phần body đang có trong buffer rồi tuyên bố đã bảo vệ mọi request.

### 10.2. Bộ lọc buffering của Envoy

Một buffer filter ở L7 có thể giới hạn **kích thước request body được giữ trong buffer** theo tham số hỗ trợ. Nó có thể cần đọc và buffer body trước khi chuyển tiếp, dẫn đến tăng memory/latency theo concurrency. Cần kiểm tra cách filter được cài vào HTTP filter chain, limit trên từng route và ảnh hưởng tới các API streaming, gRPC hoặc long-running uploads.

Không mặc định có bộ lọc buffering chỉ vì Envoy được dùng làm ingress; đó là một **chính sách phải được cấu hình và kiểm chứng**.

## 11. Trạng thái HTTP khi request không được chấp nhận

### 11.1. HTTP 413 Content Too Large

Theo HTTP semantics hiện đại, **413 Content Too Large** cho biết server không muốn hoặc không thể xử lý request vì **nội dung request lớn hơn giới hạn mà server chấp nhận**. Đây là trạng thái thường thấy khi reverse proxy thực thi request body limit. Tên cũ **Payload Too Large** hoặc **Request Entity Too Large** vẫn có thể xuất hiện trong log/giao diện, nhưng mã **413** là thành phần có ý nghĩa giao thức.

Một phản hồi mô phỏng:

~~~http
HTTP/1.1 413 Content Too Large
Content-Type: application/json
Cache-Control: no-store

{"error":"request_body_too_large","max_bytes":131072}
~~~

**Không phải mọi proxy tự động trả JSON nêu rõ max_bytes**. Mẫu phản hồi chỉ là **gợi ý hợp đồng API** khi hệ thống có cơ chế trả lỗi được kiểm soát. Nếu muốn hiển thị hạn mức, phải bảo đảm giá trị lấy đúng từ cấu hình policy đang hiệu lực để tránh tài liệu phản hồi sai.

### 11.2. Phân biệt 413 với những lỗi gần giống

| HTTP status | Ý nghĩa thường gặp | Liên hệ với size limit |
| --- | --- | --- |
| **413** | Content Too Large | Request body vượt mức mà tầng xử lý chấp nhận |
| **414** | URI Too Long | Request target/URI quá dài; không đồng nghĩa body lớn |
| **431** | Request Header Fields Too Large | Header fields quá lớn; chỉ xuất hiện nếu implementation chọn/trả mã này |
| **400** | Bad Request | Framing hoặc cú pháp request sai; một proxy có thể trả 400 cho một số lỗi header |
| **408** | Request Timeout | Server không nhận request kịp theo policy thời gian |
| **415** | Unsupported Media Type | Dạng nội dung/encoding không được ứng dụng chấp nhận |
| **422** | Unprocessable Content | Nội dung có cú pháp nhận được nhưng không xử lý theo ngữ nghĩa |
| **429** | Too Many Requests | Vượt rate/quota theo thời gian, không nhất thiết vượt bytes/request |
| **502** | Bad Gateway | Proxy gặp phản hồi upstream không phù hợp hoặc lỗi proxying cụ thể |
| **503** | Service Unavailable | Dịch vụ quá tải/tạm thời không sẵn sàng |
| **504** | Gateway Timeout | Proxy không nhận được phản hồi upstream kịp thời |

Không quy mọi 413 cho WAF và mọi 502 cho backend: status có thể do **bất kỳ hop** có khả năng trả response tạo ra. Phải xác định tầng thực thi bằng **log, response metadata được kiểm soát và correlation ID**.

### 11.3. Hành vi khi đã gửi body một phần

Nếu request quá lớn bị phát hiện sau khi truyền được nhiều byte:

- Proxy có thể phản hồi 413 và **ngừng nhận/đóng kết nối** tùy giao thức/trạng thái.
- Client đang upload có thể thấy lỗi mạng, reset hoặc 413 tùy client và timing.
- Với streaming, backend có thể đã nhận một phần body trước khi proxy ngắt.
- Không nên mặc định có thể tái sử dụng kết nối HTTP/1.1 nếu còn dữ liệu của body bị từ chối mà framing chưa được xử lý an toàn.

**Ứng dụng phải xử lý partial upload và cleanup.** Đối với các thao tác không idempotent, cần phân biệt “server chưa nhận request”, “server đã nhận một phần”, và “server đã commit nhưng response bị mất”.

### 11.4. Expect: 100-continue

Một HTTP/1.1 client có thể dùng **Expect: 100-continue** để đợi server đồng ý tiếp nhận phần body sau khi gửi header. Nếu thông tin Content-Length hoặc policy cho phép chặn sớm, proxy có thể phản hồi một lỗi cuối như 413 trước khi client gửi một body lớn.

Tuy nhiên, không phải mọi client, proxy và backend xử lý Expect theo cùng một cách. Đây là **cơ chế tối ưu giao tiếp có điều kiện**, không phải ranh giới bảo mật duy nhất. Hãy thử đúng end-to-end path nếu dùng trong thiết kế upload.

## 12. Kiểm thử request size limit trong lab được phép

Không cần gửi request hàng trăm MiB hoặc tạo tải DDoS để kiểm tra chính sách. Một bộ **request nhỏ quanh ngưỡng** đã đủ xác nhận nhiều lỗi cấu hình. Mọi endpoint dùng trong kiểm thử phải thuộc môi trường bạn được quyền quản trị, có kịch bản rollback và logging.

### 12.1. Điều kiện tiền đề

Giả sử lab có cấu hình Nginx:

~~~text
Proxy:             http://127.0.0.1:8088
Route:             /api/test-upload
Body cap:          128 KiB = 131.072 byte
Backend:           Một test endpoint chấp nhận octet-stream trong phạm vi cho phép
Hành vi mong đợi:  Request <= 131.072 byte không bị chặn bởi size limit
                  Request > 131.072 byte được proxy trả 413
~~~

**Chú ý:** một request dưới size limit có thể vẫn được trả **400, 401, 403, 404 hoặc 415** vì lý do khác. Kết quả đúng ở đây là **không bị rule size limit chặn**, không nhất thiết mọi request đều nhận 200.

### 12.2. Tạo dữ liệu kiểm thử nhỏ

Ví dụ trên máy Linux/macOS có lệnh **dd** và quyền ghi vào thư mục lab:

~~~bash
# Tạo hai file chứa byte 0 dùng cho kiểm tra ở gần ngưỡng.
# Tổng kích thước chỉ khoảng vài trăm KiB.
dd if=/dev/zero of=body-128k.bin bs=1024 count=128
dd if=/dev/zero of=body-129k.bin bs=1024 count=129

# Xác minh kích thước byte.
wc -c body-128k.bin body-129k.bin
~~~

Kỳ vọng:

~~~text
body-128k.bin = 131072 bytes
body-129k.bin = 132096 bytes
~~~

Đây là dữ liệu **octet-stream**, không phải JSON hợp lệ. Nếu endpoint yêu cầu JSON hoặc chống file binary, cần tạo fixture **đúng Content-Type và schema** của endpoint lab hoặc chọn endpoint chuyên nhận binary. Không gán lỗi 415 của ứng dụng cho size limit.

### 12.3. Gửi request có kích thước xác định

~~~bash
# Request đúng ngưỡng; có thể được proxy cho qua.
curl -i --max-time 10 \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @body-128k.bin \
  http://127.0.0.1:8088/api/test-upload

# Request vượt ngưỡng 1 KiB; mong đợi 413 ở proxy.
curl -i --max-time 10 \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @body-129k.bin \
  http://127.0.0.1:8088/api/test-upload
~~~

**Không kết luận chỉ từ mã trả về.** Cần kiểm tra access/error logs để xác nhận lớp nào tạo 413. Một backend có thể cũng trả 413 độc lập; trong trường hợp đó, chỉ status HTTP là chưa đủ để khẳng định rule proxy hoạt động.

### 12.4. Bộ kiểm thử ranh giới tổng quát

Với hạn mức giả định **L byte**:

| Test case | Dung lượng body | Kỳ vọng khi quy tắc là “không quá L byte” |
| --- | --- | --- |
| T0 | 0 byte | Không chặn bởi size limit nếu endpoint chấp nhận empty body |
| T1 | L − 1 byte | Không chặn bởi size limit |
| T2 | **L byte** | Không chặn bởi size limit |
| T3 | **L + 1 byte** | Bị chặn theo size limit |
| T4 | L + một mức nhỏ | Bị chặn và có log/metric hợp lệ |
| T5 | Chunked/streamed đạt L + 1 | Bị chặn dù không biết tổng size từ đầu |
| T6 | Multipart: file ≤ per-file nhưng body > L | Bị chặn bởi total body cap |
| T7 | Body nén ≤ L, decoded > app limit | Lớp decoded-size/app phải xử lý |
| T8 | Body nhỏ, header/URI quá lớn | Rule header/URI riêng phản ứng đúng |
| T9 | IPv4 và IPv6, nhiều hostname | Đều gặp policy đúng, không có bypass |
| T10 | Nhiều proxy node | Cùng policy, logging và response hợp đồng |

Một số proxy tính kích thước hoặc xử lý ngưỡng theo đặc tính riêng, vì thế **bài kiểm thử thực tế** là nguồn xác minh semantics sau khi đọc tài liệu nền tảng.

### 12.5. Content-Length, chunked và request streaming

Để kiểm tra đúng cách với chunked hoặc streaming, nên dùng **bộ test HTTP hợp chuẩn** của tổ chức hoặc framework tích hợp đã được kiểm soát. Không cần tạo **header framing mâu thuẫn hoặc giao thức sai** trên dịch vụ production.

Các quan sát cần ghi:

1. Proxy có trả 413 ngay khi thấy Content-Length vượt L không?
2. Nếu không có Content-Length, proxy có đếm được số byte body và chặn sau L không?
3. Request bị chặn trước khi backend nhận hay backend đã nhận một phần?
4. Dữ liệu tạm có được cleanup khi client ngắt không?
5. Những hop khác có thay đổi Content-Encoding/framing trước khi proxy kiểm tra không?
6. HTTP/2/HTTP/3 request/stream có cùng hạn mức và trạng thái lỗi mong đợi không?

### 12.6. Lỗi thường gặp khi test không đúng ngữ cảnh

- Gửi **JSON không hợp lệ** và nhìn thấy 400 trước khi kiểm được rule size.
- Dùng **multipart** nhưng so file bytes với body limit mà bỏ overhead.
- Gửi request đến **hostname/backend trực tiếp**, bỏ qua proxy cần kiểm thử.
- Chỉ test một ingress node, không test các node khác.
- Không reload Nginx sau khi thay đổi cấu hình có phê duyệt, nhưng tưởng policy mới đã hiệu lực.
- Proxy trả 413 từ một tầng trước đó, khiến tưởng Nginx bên trong đã thực thi.
- Dùng sample nhỏ quá mức nên không chạm ngưỡng cần test.
- Giới hạn **request body** được tăng nhưng lỗi thực tế là **header hoặc URI limit**.

## 13. Theo dõi log và xác định lớp chặn request

### 13.1. Những thông số nên ghi

Một proxy/gateway có thể ghi các trường:

- **Timestamp** chuẩn, request/correlation ID và service/site.
- Host, route, method và **HTTP version**.
- Chính sách áp dụng: body cap, scope, rule ID và version.
- Content-Length khai báo nếu an toàn, **bytes thực nhận** và bytes forward khi có số liệu tin cậy.
- HTTP status mà tầng này trả, upstream status nếu thực sự có upstream.
- Request time, upstream time, tình trạng buffering/temp disk nếu được giám sát.
- Loại body/encoding, client identity hoặc IP nguồn đã xác thực qua chuỗi proxy tin cậy.
- Chỉ số về RAM/đĩa tạm/connection/queue, tỷ lệ 413 theo route.

**Không log nguyên request body, Authorization/cookie hoặc token nhạy cảm** chỉ vì muốn điều tra 413. Dữ liệu metadata đã đủ cho phần lớn tình huống; cần retention, access control và masking phù hợp.

### 13.2. Mẫu sự kiện giả lập

~~~text
time=2026-11-28T11:00:00Z
service=api-lab
component=reverse-proxy-01
route=/api/test-upload
method=POST
body_limit_bytes=131072
declared_content_length=132096
observed_body_bytes=0
action=REJECT_EARLY
http_status=413
upstream_status=-
request_id=req-lab-0042
~~~

Trong ví dụ, proxy **đã chặn theo header trước khi đọc body**, nên observed_body_bytes=0 là một khả năng hợp lý. Đây là log **do bài học minh họa**, không phải format có sẵn trên mọi proxy. Không nhầm số byte **Content-Length khai báo** với **bytes thực tế đã được chuyển tới upstream**.

### 13.3. Khi upstream trả 413

Một request dưới hạn của proxy có thể vượt hạn của backend:

~~~text
Client → Proxy:
  POST /upload, 12 MiB
Proxy limit:
  24 MiB, request được chuyển tiếp
Backend limit:
  10 MiB, backend trả 413

Client nhận 413,
nhưng tăng client_max_body_size ở proxy KHÔNG giải quyết lỗi.
~~~

Cần phân biệt **proxy-generated 413** với **upstream-generated 413** bằng log trên đúng hop; một số tầng có thể rewrite response hoặc cache/convert lỗi, khiến chỉ dựa vào response body không đủ.

### 13.4. Chỉ số cảnh báo

| Metric | Câu hỏi giải đáp | Lưu ý |
| --- | --- | --- |
| Tổng 413 theo host/route/layer | Request nào bị chặn, tại đâu? | Không tự chứng minh tất cả đều là tấn công |
| Tỷ lệ 413 / tổng request theo route | Policy có gây chặn nhầm diện rộng không? | Cần biết traffic mix và thời điểm deploy |
| Max/p95/p99 body size đã nhận | Hạn mức có sát nhu cầu thực tế không? | Chỉ tính được phần nhận/quan sát |
| Temp disk usage, write failures | Proxy có bị cạn đĩa do buffering? | Disk cạn có thể gây lỗi khác ngoài 413 |
| Peak concurrent uploads | Hard cap per request có đủ bảo vệ tổng tài nguyên không? | Phải kết hợp concurrency |
| Upload duration và rate | Có client quá chậm hoặc queue dài? | Phân biệt kết nối kém với lạm dụng |
| Upstream latency/5xx | Backend có quá tải dù proxy chặn? | Cần xét route cost, rate và buffer mode |
| CDN/WAF inspection/truncation events | Có giới hạn kiểm tra khác enforcement? | Một payload không được kiểm tra hết có thể không bị reject |
| False positive appeals/tickets | Người dùng hợp lệ có bị chặn? | Kết hợp user journey và thay đổi nghiệp vụ |

### 13.5. Không nhầm “đã kiểm tra một phần” với “đã chặn toàn bộ”

Một WAF hoặc proxy có thể **chỉ inspection** đến N KiB body, trong khi tổng request body được gửi tới ứng dụng có thể lớn hơn. Nếu chế độ là **partial inspection / process partial**, body quá lớn không nhất thiết bị chặn. Điều đó khác với **enforcement** chặn request vượt tổng body limit.

Khi đánh giá một sản phẩm, luôn tìm câu trả lời rõ:

1. Giới hạn là **inspection cap** hay **hard reject cap**?
2. Khi vượt thì request bị **reject, truncate, buffer, pass through hay log-only**?
3. Tầng nào tiếp tục nhận dữ liệu và có thể chuyển tiếp tới backend?
4. Áp cho các mode **DetectionOnly, WAF blocking, HTTP/2, upload streaming** như thế nào?

Nếu không biết hành vi khi vượt hạn, không nên viết chính sách “đã ngăn mọi request body quá lớn” chỉ dựa trên trường cấu hình có chữ **limit**.

## 14. Chẩn đoán HTTP 413 và lỗi upload không hoàn tất

Một lỗi “request quá lớn” có thể bắt nguồn từ **CDN, WAF, reverse proxy, ingress, API gateway, application framework hoặc storage service**. Sửa sai tầng có thể khiến người dùng vẫn gặp lỗi trong khi proxy bị nới giới hạn không cần thiết.

~~~mermaid
flowchart TD
    A["Client thấy 413 hoặc upload thất bại"] --> B{"Đang đi qua hostname / endpoint / path nào?"}
    B --> C["Tra correlation ID ở CDN/WAF và proxy"]
    C --> D{"Tầng nào tạo lỗi?"}
    D -->|Edge/WAF| E["Kiểm tra platform caps, inspection/enforcement, policy edge"]
    D -->|Reverse proxy| F["Kiểm tra body cap, location match, buffering, headers"]
    D -->|Backend/application| G["Kiểm tra middleware/parser/file/quota/decoded size"]
    D -->|Chưa xác định| H["Đối chiếu status, upstream status, logs mọi hop"]
    E --> I["Kiểm tra size thực tế và hợp đồng route"]
    F --> I
    G --> I
    H --> I
    I --> J{"Đây có phải request hợp lệ?"}
    J -->|Có| K["Điều chỉnh đúng tầng/route, thử ranh giới và rollout"]
    J -->|Không| L["Giữ giới hạn, trả lỗi rõ và theo dõi abuse"]
    K --> M["Xác minh backend, upload success và tài nguyên"]
    L --> M
~~~

### 14.1. Triệu chứng: 413 ngay khi gửi request

**Khả năng:** một tầng nhìn **Content-Length** vượt ngưỡng và từ chối sớm; client upload chưa bắt đầu hoặc chỉ gửi rất ít body.

**Kiểm tra:** host/path, Content-Length, size limit đang hiệu lực, log proxy và upstream. Phân biệt response trực tiếp từ edge/proxy với backend. Nếu request hợp lệ nhưng file lớn hơn hợp đồng API, có thể cần **đường upload riêng** thay vì nới mọi endpoint.

### 14.2. Triệu chứng: Upload chạy một lúc rồi thất bại

**Khả năng:**

- Body không có độ dài biết trước; proxy đếm byte và chỉ phát hiện vượt ngưỡng trong lúc đọc.
- Streaming chuyển một phần tới backend rồi ngắt.
- Temp disk hết dung lượng hoặc lỗi quyền ghi file tạm.
- Client body read timeout, upstream timeout hoặc kết nối mạng không ổn định.
- Ứng dụng/storage có limit thấp hơn proxy hoặc không xử lý partial upload.

**Kiểm tra:** bytes received/sent, duration, proxy error log, temp disk, backend request log, transport và retry behavior. Không kết luận “đã thấy upload bắt đầu thì không thể là size limit”.

### 14.3. Triệu chứng: Chỉ lỗi ở một node/site

**Khả năng:** CDN edge node, Nginx ingress replica hoặc gateway ở chi nhánh có **cấu hình chưa đồng bộ**; ingress controller chưa áp annotation; hostname được route sang virtual host khác; HTTP/2/3 có semantics khác mode đang test.

**Kiểm tra:** versioned config, upstream path, hostname/SNI, IPv4/IPv6, build/version của proxy, node identity trong log và kết quả request theo đúng điểm kiểm tra. Không thay cấu hình ngẫu nhiên trên một máy nếu hệ thống dùng controller/GitOps.

### 14.4. Triệu chứng: File 20 MiB bị chặn dù body limit là 20 MiB

Nếu request là **multipart/form-data**, tổng body có thể vượt 20 MiB bởi boundary, field và part headers. Nếu file được encode trong JSON như Base64, biểu diễn text thường **lớn hơn dữ liệu nhị phân gốc**.

**Kiểm tra:** format upload thật, tổng body được gửi trên dây, số file/field, Content-Encoding và cơ chế tính size của proxy. Chọn total body cap dựa trên **dữ liệu hợp lệ và overhead**, đồng thời giữ per-file cap ở lớp xử lý file.

### 14.5. Triệu chứng: Đã tăng limit proxy nhưng vẫn trả 413

**Khả năng:** request bị edge/gateway chặn trước, ứng dụng còn giới hạn riêng, rule chỉ đặt ở location khác, controller ghi đè config, proxy chưa reload hoặc client đang gửi lớn hơn mức mới.

**Hướng xử lý:** đi theo **chuỗi hop** từ client tới backend, kiểm tra mỗi lớp có nhận request không, tầng nào trả status, limit nào và policy version nào. Không tiếp tục tăng con số ở những nơi chưa được chứng minh gây lỗi.

### 14.6. Triệu chứng: Body nhỏ nhưng request vẫn thất bại

Khả năng không nằm ở body size:

- URI/query quá dài.
- Cookie hoặc Authorization header quá lớn.
- Request framing/Content-Length sai, trùng/mâu thuẫn.
- Backend không hỗ trợ Content-Type/encoding.
- Too many requests (429), auth failure (401/403) hoặc timeout.
- JSON/XML parser depth/field limits thấp hơn body bytes.

**Điều tra theo mã lỗi và log cụ thể**, không dùng “tăng client_max_body_size” như phương án mặc định cho mọi lỗi HTTP.

## 15. Vận hành, rollout và rollback an toàn

### 15.1. Quy trình thay đổi chính sách

1. **Xác định owner và hợp đồng API:** route/method nào cần thay, bao nhiêu file, per-file limit, tổng multipart, client nào và dữ liệu đầu vào kiểu gì.
2. **Kiểm kê các hop:** CDN/WAF/LB L7, reverse proxy/ingress, gateway, framework, app, storage và đường đi đặc biệt.
3. **Đo lưu lượng hợp lệ:** mức cực đại hợp lệ, p95/p99, burst, upload duration và concurrency.
4. **Chọn chính sách theo lớp:** hard body cap, decoded size, file count, schema complexity, timeouts, queue và resource budget.
5. **Kiểm tra tác động bảo mật:** lỗ hổng bypass, streaming partial state, Content-Length vs chunked, DoS, log nhạy cảm và origin exposure.
6. **Viết test ranh giới:** L − 1, L, L + 1, multipart, chunked, compressed, IPv4/IPv6, node/site và đường bypass.
7. **Rollout có giới hạn:** lab/staging, canary node/route, giám sát 413/5xx, temp disk, latency và business success.
8. **Theo dõi phản hồi:** không chỉ nhìn số 413 giảm, cần kiểm tra backend có bị quá tải hoặc storage quota vượt không.
9. **Rollback có điều kiện:** lưu version policy cũ và biết khi nào cần hạ lại limit hoặc tách upload route.
10. **Định kỳ rà soát ngoại lệ:** xóa chính sách “tạm” đã quá hạn, cập nhật sau thay đổi API và capacity.

### 15.2. Không tự nới hạn mức trong sự cố

Khi có lượng lớn HTTP 413:

- Có thể là phiên bản client mới gửi payload lớn **hợp lệ**.
- Có thể là bên tích hợp dùng sai API hoặc tự retry không giới hạn.
- Có thể là traffic tự động độc hại hoặc test tải ngoài kế hoạch.
- Có thể là cấu hình edge vừa đổi, ảnh hưởng nhiều khách cùng lúc.

Quyết định thay đổi phải dựa trên **dữ liệu**, không chỉ số lỗi. Nếu cần tạm nới, chỉ áp ở **route và nhóm được phép**, có thời gian kết thúc, giám sát công suất và phương án rollback rõ ràng.

### 15.3. Khi proxy có nhiều instance

Với load balancing, mỗi instance có thể buffer request ở RAM/đĩa khác nhau. Điều cần kiểm tra:

- Tất cả instance dùng **cùng policy** theo virtual host/path.
- Mức body limit và request timeout có đúng ở gateway/ingress trước từng instance.
- Temp disk và quota từng node đủ công suất.
- Autoscaling không tạo node mới với cấu hình mặc định thấp hơn.
- Correlation ID cho phép xác định **node đã xử lý/chặn**.
- Nếu một node trả 413 và node khác trả 200 cho cùng request hợp lệ, deployment cần được điều tra.

**Cân bằng tải không tự phân tán dung lượng một request thành nhiều backend.** Một request body 20 MiB vẫn được xử lý qua đường đã chọn; việc có nhiều node chỉ giúp chia tổng traffic khi được phân phối hợp lý.

### 15.4. Cân bằng an toàn và trải nghiệm người dùng

Khi request bị 413, phản hồi API nên giúp client biết **hạn mức và phương án phù hợp** nếu hợp đồng cho phép. Với upload lớn:

- Định nghĩa lỗi rõ ràng và thông báo dung lượng file được phép.
- Hỗ trợ chunked/resumable upload ở **mức ứng dụng** nếu cần, có session/quota/finalize.
- Tránh retry request quá lớn y nguyên liên tục.
- Theo dõi upload thất bại, partial object và chi phí storage.
- Bảo vệ URL upload có thời hạn và quyền hạn khi dùng direct-to-storage.

**Chunked transfer của HTTP/1.1** và **resumable multipart upload ở mức ứng dụng** là hai khái niệm khác nhau. Một request được truyền thành chunk ở giao thức vẫn có thể là **một request body** và phải chịu hard cap; còn upload chia thành nhiều request/parts có thể cần kiểm soát **tổng kích thước file logic**, không chỉ giới hạn từng request độc lập.

## 16. Tình huống thiết kế tổng hợp

**Bối cảnh:** một nền tảng nội bộ có:

- **POST /api/orders** nhận JSON, thường rất nhỏ.
- **POST /upload/documents** nhận tối đa **20 MiB mỗi file**.
- **POST /reports/import** nhận một gói dữ liệu theo lô, có thể lớn hơn JSON thông thường.
- Hạ tầng **CDN/WAF → Nginx reverse proxy → hai application instances → object storage/DB**.

Nhóm vận hành ghi nhận:

1. Người dùng upload file 20 MiB bị trả 413.
2. API orders đôi lúc bị gửi body nhiều MiB nhưng không có nhu cầu.
3. Trong giờ cao điểm, temp disk của một Nginx node tăng nhanh.
4. Một số request 413 xuất hiện trên CDN nhưng không có trong log Nginx.

### 16.1. Phân tích nguyên nhân

| Quan sát | Nhận định hợp lý | Kiểm tra tiếp |
| --- | --- | --- |
| File 20 MiB bị 413 | Total multipart > 20 MiB, hoặc một hop có limit thấp hơn | Size body thật, CDN/proxy/app limits |
| Orders nhận body quá lớn | Chưa có route-specific cap hoặc hợp đồng quá rộng | Cấu hình /api/, JSON parser, request stats |
| Temp disk tăng | Buffering và concurrency tạo nhu cầu đĩa | body temp path, concurrent upload, disk metrics |
| CDN có 413, Nginx không có | Edge đã từ chối trước origin | Edge logs, policy/hard cap, request ID |

### 16.2. Kiến trúc chính sách đề xuất để thảo luận

| Điểm kiểm soát | Policy ở mức chức năng | Mục tiêu |
| --- | --- | --- |
| CDN/WAF | Hard limit/inspection policy theo khả năng dịch vụ | Chặn sớm traffic vượt ngưỡng, tránh origin overload |
| Nginx /api/ | Body cap nhỏ, ví dụ 128 KiB | Bảo vệ JSON API |
| Nginx /upload/ | Body cap có overhead, ví dụ 24 MiB | Cho phép file 20 MiB trong multipart có margin |
| Application upload handler | **Per-file 20 MiB**, MIME/magic bytes, số part và quota | Bảo vệ nghiệp vụ và file parser |
| Report import | Route riêng, giới hạn rõ, concurrency và job queue | Không làm cạn worker/DB |
| Object storage | Object quota, permission, malware scan/quarantine, cleanup | Bảo vệ tài nguyên lâu dài |
| Observability | Route/body limit, source layer, request ID, temp disk, upload success | Phát hiện chặn nhầm hoặc quá tải |

**24 MiB ở proxy cho file 20 MiB chỉ là ví dụ về margin**, không phải một mức tối ưu cố định. Overhead thực tế còn phụ thuộc số field/file và protocol; cần đo theo hợp đồng upload.

### 16.3. Kế hoạch nghiệm thu

1. Upload file 19 MiB và 20 MiB bằng **định dạng multipart thực tế**, ghi total body bytes và kết quả.
2. Upload file 20 MiB + nhiều part khác: xác minh **per-file** và **total body cap** phối hợp.
3. Thử JSON body trên/dưới 128 KiB ở đúng API route.
4. Kiểm tra CDN và Nginx response source, không nới Nginx khi lỗi nằm ở CDN.
5. Đo RAM/temp disk ở số upload đồng thời đã được phê duyệt và theo dõi clean-up.
6. Thử khi backend ngắt giữa chừng, kiểm tra không để object tạm tồn tại mãi.
7. Xác minh request không đi vòng edge/proxy qua origin hoặc ingress phụ.
8. Kiểm tra IPv4/IPv6 và toàn bộ Nginx instances sau rollout.
9. Có rollback nếu backend latency/5xx tăng hoặc temp disk vượt ngưỡng.

### 16.4. Điều không nên làm

Không giải quyết bằng cách đặt **client_max_body_size 0** cho mọi route; không lấy số 413 giảm làm bằng chứng an toàn; không cho rằng nâng giới hạn body sẽ tự nâng giới hạn framework hoặc storage; và không chấp nhận upload lớn mà thiếu các bước kiểm tra nội dung, quyền hạn và cleanup.

## 17. Câu hỏi tự kiểm tra

**1. Vì sao một load balancer L4 TCP passthrough không tự áp được hạn mức JSON body chính xác?**

Vì nó không parse HTTP body ở lớp ứng dụng và có thể không nhìn plaintext khi TLS được passthrough. Cần L7 termination/parser hoặc một điểm kiểm soát phù hợp.

**2. client_max_body_size khác client_body_buffer_size ra sao?**

Directive đầu tiên giới hạn kích thước body request; directive thứ hai quy định kích thước buffer trong cơ chế đọc body, **không phải** body size cap.

**3. File đúng 20 MiB có thể bị 413 khi proxy đặt body limit 20 MiB không?**

Có, nếu request multipart gồm boundary và field metadata, tổng body vượt 20 MiB.

**4. Khi Content-Length lớn hơn hạn, proxy có thể reject trước khi nhận body không?**

Có, nếu proxy xử lý framing và policy như thiết kế. Nhưng vẫn phải đếm bytes thực với request không có tổng chiều dài biết trước.

**5. Vì sao Transfer-Encoding: chunked không được dùng để bỏ qua body limit?**

Nội dung vẫn phải được giới hạn theo **tổng body được nhận**, dù tổng size không biết ngay lúc đọc header.

**6. Bật proxy_request_buffering off có nghĩa không có body limit và không có rủi ro gì ở backend?**

Không. Proxy vẫn có thể kiểm soát size theo semantics, và backend có thể đã nhận dữ liệu một phần trước khi bị ngắt.

**7. Body nén 200 KiB, giải nén 12 MiB: body cap 1 MiB tại proxy đã đủ bảo vệ ứng dụng chưa?**

Chưa chắc. Cần kiểm soát **decoded bytes**, CPU và parser/resources tại tầng giải nén.

**8. Vì sao request dưới body limit vẫn có thể lỗi 414 hoặc 431?**

Request target hoặc header vượt **giới hạn riêng**, độc lập với body.

**9. Vì sao người dùng thấy HTTP 413 nhưng log Nginx không có request?**

Một tầng phía trước (CDN/WAF/API gateway) có thể đã trả 413 trước khi Nginx nhận được.

**10. Vì sao một request 20 MiB × 100 request đồng thời nguy hiểm dù từng request đều hợp lệ?**

Tổng dung lượng đệm, socket và tài nguyên upstream có thể rất lớn; cần concurrent/queue/bandwidth limits và đo công suất.

**11. Tại sao một WAF inspection limit 8 KiB không mặc nhiên là hard body cap 8 KiB?**

Inspection limit chỉ giới hạn lượng dữ liệu được phân tích; sản phẩm có thể tiếp tục chuyển phần còn lại nếu không cấu hình enforcement.

**12. Vì sao không nên tăng body cap toàn hệ thống khi chỉ một endpoint upload cần file lớn?**

Vì những route không cần payload lớn vẫn bị tăng bề mặt rủi ro về buffering, parsing và tiêu thụ tài nguyên.

**13. Giới hạn mỗi request 10 MiB có tự giới hạn tổng một resumable upload gồm 50 parts không?**

Không. Cần quản lý tổng file/object size và session quota ở mức upload logic.

**14. Nếu proxy trả 413 trước khi forward, ứng dụng có chắc tạo log cho request không?**

Không; ứng dụng chưa từng nhận request. Cần quan sát proxy/edge logs.

**15. Làm sao phân biệt 413 do proxy với 413 do backend?**

Đối chiếu request ID, proxy error/access logs, upstream status/trace và bằng chứng request đã tới backend.

## 18. Các hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Giới hạn request size là rate limiting.” | Size cap theo byte/request; rate cap theo số request/thời gian. |
| “Đặt 1 MiB ở proxy thì mọi thành phần phía sau an toàn.” | Còn decoded size, parser complexity, concurrency và backend limits. |
| “Content-Length luôn phản ánh dữ liệu thực và không cần đếm body.” | Cần parse framing đúng và giới hạn bytes thực tế. |
| “Chunked transfer không có Content-Length nên vượt size cap được.” | Proxy HTTP đúng phải kiểm tra tổng body trong quá trình nhận. |
| “HTTP/2 một connection tương đương một request.” | Một connection có thể có nhiều request streams. |
| “Header lớn xử lý bằng client_max_body_size.” | Header/URI có giới hạn riêng. |
| “client_body_buffer_size là tổng body cap.” | Đó là buffer size, không phải hard maximum. |
| “proxy_buffering là buffering request.” | Trong Nginx proxy_buffering chủ yếu liên quan response từ upstream. |
| “Tắt request buffering luôn an toàn hơn.” | Streaming có rủi ro partial processing ở backend và khác biệt timeout. |
| “Proxy trả 413 nghĩa là WAF phát hiện tấn công.” | Có thể là upload hợp lệ hoặc sai hợp đồng/cấu hình. |
| “Tất cả 413 xuất phát từ ứng dụng.” | CDN/proxy có thể chặn trước khi ứng dụng nhận. |
| “WAF đã inspect N KiB nghĩa là request > N KiB chắc chắn bị reject.” | Inspection cap khác hard enforcement cap. |
| “Upload file 20 MiB, proxy 20 MiB chắc chắn qua.” | Multipart và encoding có overhead. |
| “Đặt body cap tại CDN là không cần bảo vệ origin.” | Có thể bypass origin, route nội bộ khác hoặc giới hạn phía app. |
| “Đặt size cap lớn rồi tăng worker là đủ.” | Phải đo RAM/đĩa/đồng thời, timeout, hậu xử lý và storage. |
| “Direct upload vào storage không cần kiểm tra file.” | Vẫn cần authz, size/quota, content validation, scanning và cleanup. |
| “Chỉ cần thử một request đến VIP là các node đều đúng.” | Phải kiểm tra policy consistency và đường ingress thực. |

## 19. Tổng kết

**Giới hạn kích thước request tại proxy** là biện pháp giảm tiêu thụ tài nguyên và ngăn payload vượt khả năng xử lý tiến vào các tầng phía sau. Một thiết kế đúng phải xác định **proxy thực thi ở lớp nào, body/header/URI được đo thế nào, request có Content-Length hay truyền theo stream, proxy buffer hay forward sớm, và tầng nào đưa ra phản hồi 413**.

Trong **Proxy reverse proxy và cân bằng tải**, không nên chỉ đặt một con số rồi coi là hoàn tất. Cần **body cap theo route, hard enforcement rõ ràng, decoded/parsed/file caps ở backend, timeouts, concurrency/resource budget, logging và kiểm thử ranh giới**. Đối với nhiều proxy hop, phải tránh bypass, đồng bộ policy và có phương án xử lý upload lớn bằng luồng hoặc object storage an toàn.

Trong học phần **SECURITY_NETWORK_SECURITY**, size limit bổ sung cho WAF, firewall, phân đoạn, IDS/IPS, bảo vệ DNS, chống DDoS và kiến trúc mạng nhiều lớp. Cơ chế này giúp **giảm blast radius và bảo vệ tính sẵn sàng**, nhưng không tự giải quyết mọi kiểu DoS hay làm cho nội dung request trở nên an toàn. Giá trị của nó được xác minh bằng **test có kiểm soát, số liệu vận hành và trải nghiệm người dùng hợp lệ**, không chỉ bằng việc xuất hiện một HTTP 413.

### Tài liệu tham khảo

- **RFC 9110 — HTTP Semantics:** ý nghĩa HTTP status **413 Content Too Large**, **414 URI Too Long**, **431 Request Header Fields Too Large** và các mã trạng thái liên quan.
- **RFC 9112 — HTTP/1.1:** framing, Content-Length và Transfer-Encoding.
- **RFC 9113 — HTTP/2:** stream framing, headers và cơ chế trao đổi HTTP/2.
- **RFC 9114 — HTTP/3:** trao đổi HTTP qua QUIC và stream semantics.
- **NGINX Documentation — ngx_http_core_module:** **client_max_body_size**, **client_body_buffer_size**, **client_body_timeout**, **client_body_temp_path** và giới hạn header.
- **NGINX Documentation — ngx_http_proxy_module:** **proxy_request_buffering**, **proxy_http_version** và **proxy_buffering**.
- **Apache HTTP Server — Core Directives:** **LimitRequestBody** và các giới hạn request khác.
- **Envoy Proxy Documentation — HTTP buffer filter:** buffering/maximum request bytes theo cấu hình cụ thể.
- **OWASP File Upload Cheat Sheet:** kiểm soát kích thước/loại file, quyền, scanning và storage isolation.
- **OWASP Denial of Service Cheat Sheet:** quản trị tài nguyên, giới hạn concurrency/timeout và giảm tác động DoS.
- **OWASP HTTP Request Smuggling Cheat Sheet:** nguy cơ parse/framing không nhất quán giữa các HTTP hop.

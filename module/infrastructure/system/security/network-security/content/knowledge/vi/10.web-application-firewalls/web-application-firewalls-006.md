# Request size limit trong Web Application Firewall: Giới hạn kích thước yêu cầu HTTP

## 1. Request size limit là gì?

**Request size limit** là cơ chế đặt ngưỡng cho kích thước của **yêu cầu HTTP** mà một lớp bảo vệ hoặc máy chủ được phép tiếp nhận, lưu đệm, phân tích hay chuyển tiếp. Giới hạn có thể áp dụng cho dòng yêu cầu và URI, các HTTP header, phần thân (request body), tệp tải lên, dữ liệu biểu mẫu hoặc kích thước dữ liệu sau khi giải nén/giải mã. Từng thiết bị có thể hỗ trợ những loại giới hạn khác nhau.

Trong chương **Web application firewall** của học phần **SECURITY_NETWORK_SECURITY**, request size limit là một thành phần của phòng vệ nhiều lớp trước tình trạng tiêu thụ tài nguyên quá mức, xử lý yêu cầu bất thường và điểm mù kiểm tra nội dung. Nó cần được phối hợp với firewall, phân đoạn mạng, xác thực, giám sát IDS/IPS, reverse proxy, giới hạn tốc độ và kiểm soát ở ứng dụng. WAF chỉ kiểm soát lưu lượng HTTP mà nó nhìn thấy; một VPN, firewall L3/L4 hay hệ thống lọc DNS không tự thực thi giới hạn kích thước nội dung HTTP tương đương.

Ví dụ: API nhận các đơn hàng JSON thông thường nhỏ hơn vài chục KiB, trong khi một endpoint tải tệp có thể cần cho phép hàng chục MiB. Nếu áp dụng một ngưỡng duy nhất cho mọi đường dẫn, hệ thống dễ gặp một trong hai vấn đề: ngưỡng quá lớn khiến API thường phải tiếp xúc với payload không cần thiết, hoặc ngưỡng quá nhỏ làm người dùng không thể tải tệp hợp lệ.

**Mục tiêu học tập:**

1. Phân biệt giới hạn kích thước HTTP request với giới hạn tốc độ, thời gian xử lý và giới hạn bộ nhớ.
2. Xác định đúng phần nào của yêu cầu đang được đo, kể cả upload, multipart, streaming, dữ liệu nén và HTTP/2, HTTP/3.
3. Hiểu sự khác nhau giữa **giới hạn tiếp nhận/chặn** và **giới hạn nội dung mà WAF thực sự kiểm tra**.
4. Xây dựng ngưỡng dựa trên đặc điểm API, nghiệp vụ, tài nguyên và ma trận rủi ro.
5. Chẩn đoán lỗi 413, 414, 431 và sự không nhất quán giữa CDN, WAF, reverse proxy, ingress và ứng dụng.
6. Kiểm tra hiệu lực chính sách trong lab và giám sát false positive trước khi triển khai rộng.

## 2. Vì sao giới hạn kích thước yêu cầu là biện pháp bảo vệ?

Mỗi HTTP request tiêu thụ tài nguyên để nhận dữ liệu qua mạng, quản lý kết nối, cấp phát bộ nhớ, ghi buffer hoặc file tạm, giải nén, phân tích định dạng, kiểm tra quy tắc bảo mật và chuyển tiếp đến ứng dụng.

| Nguy cơ | Tác động có thể xảy ra | Vai trò của request size limit |
| --- | --- | --- |
| Body quá lớn so với chức năng API | Tăng bộ nhớ, I/O, CPU, độ trễ và chi phí vận hành | Chặn trước khi tầng xử lý nghiệp vụ phải nhận toàn bộ dữ liệu |
| Header hoặc URI bất thường | Tăng chi phí phân tích cú pháp, áp lực buffer hoặc gây lỗi parser | Giới hạn header/URI bằng ngưỡng và quy tắc thích hợp |
| Tệp tải lên quá lớn | Tiêu tốn băng thông, bộ nhớ đệm, lưu trữ tạm và hệ thống quét tệp | Kiểm soát kích thước yêu cầu, số tệp và kích thước từng tệp |
| Dữ liệu nén nở rất lớn khi xử lý | Dữ liệu sau giải nén tiêu tốn tài nguyên hơn nhiều so với dữ liệu trên đường truyền | Xét ngưỡng dữ liệu sau giải nén và hạn mức tài nguyên của tầng giải nén |
| WAF chỉ phân tích một phần body | Nội dung vượt vùng kiểm tra có thể không được đánh giá bởi các quy tắc phụ thuộc body | Định nghĩa hành động khi body vượt giới hạn kiểm tra; tránh mặc định cho qua |
| Lượng lớn request nhỏ | Có thể làm cạn giới hạn kết nối hoặc khả năng xử lý | Kết hợp rate limiting, concurrency limit, timeout; size limit đơn lẻ chưa đủ |

**Ví dụ tính dung lượng minh họa:** nếu một thành phần lưu toàn bộ body 4 MiB trong RAM và có 200 yêu cầu tương tự đồng thời, riêng bản sao dữ liệu body đã tương đương **800 MiB** (4 × 200), chưa kể header, kết nối, dữ liệu đã giải nén, bộ đệm nhiều lớp và chi phí của ứng dụng. Không phải hệ thống nào cũng giữ trọn body trong RAM; streaming hoặc lưu file tạm có mô hình tài nguyên khác. Con số này dùng để giải thích vì sao **kích thước × số yêu cầu đồng thời × số bản sao dữ liệu** đều quan trọng.

Request size limit giúp giảm bề mặt tiêu thụ tài nguyên, nhưng **không phải bảo đảm chống mọi DoS/DDoS**. Kẻ tấn công có thể gửi nhiều request rất nhỏ, giữ kết nối chậm, hoặc khai thác nghiệp vụ vốn đòi hỏi xử lý tốn kém. Cần các lớp giới hạn khác và giám sát theo bối cảnh.

## 3. Một yêu cầu HTTP có những kích thước nào?

Một request đơn giản có thể được hình dung như sau:

~~~http
POST /api/orders HTTP/1.1
Host: app.lab.test
Content-Type: application/json
Content-Length: 37
Authorization: Bearer [redacted]

{"items":[{"sku":"A1","quantity":1}]}
~~~

Đây là **dữ liệu minh họa**, không phải yêu cầu thực tế. Các ví dụ về địa chỉ trong bài dùng tên miền dành cho tài liệu và phòng lab; không đưa token thật vào tài liệu hoặc log.

Các vùng cần phân biệt:

| Thành phần | Cần giới hạn gì? | Ví dụ tình huống |
| --- | --- | --- |
| Request line / request target | Độ dài đường dẫn, query string, request target | URL có query chứa dữ liệu rất dài |
| Một header field | Kích thước của từng trường | Cookie hoặc Authorization header bất thường |
| Toàn bộ header section | Tổng kích thước header | Nhiều header nhỏ cộng lại thành lượng lớn |
| Request body | Số byte nội dung được nhận | JSON, XML, biểu mẫu, dữ liệu nhị phân |
| Phần không phải tệp trong multipart | Trường text hoặc metadata | Nhiều tham số lớn đi cùng file upload |
| Tệp và toàn bộ multipart | Kích thước từng file, số file, tổng body gồm boundary/metadata | Upload nhiều file trong một request |
| Nội dung sau giải nén/giải mã | Dung lượng được mở rộng khi xử lý | Payload nén có kích thước nhỏ trên đường truyền |
| Số thành phần bên trong body | Số key, phần tử, độ sâu, độ dài từng trường | JSON có rất nhiều đối tượng lồng nhau |

**Header và body là hai loại giới hạn khác nhau.** Giới hạn body 10 MiB không có nghĩa hệ thống cho phép header lớn 10 MiB. Và việc có giới hạn kích thước tệp không tự giới hạn tổng số tệp trong một request.

### 3.1. Các đơn vị thường gặp

- **Byte (B):** đơn vị cơ bản; **KiB = 1.024 byte**, **MiB = 1.048.576 byte**.
- **KB/MB:** đôi khi được dùng theo cơ số 1.000; tài liệu sản phẩm có thể dùng cách ký hiệu khác.
- Một số lệnh cấu hình dùng hậu tố **k**, **m** theo quy ước riêng của phần mềm; không tự suy ra từ chữ “MB” trong tài liệu nghiệp vụ.
- Mỗi lớp cần nêu rõ giới hạn tính theo **wire bytes**, **body bytes**, **decoded bytes** hay **giá trị đã phân tích cú pháp**.

Ví dụ một file 20 MiB được đưa vào biểu mẫu multipart có thể khiến tổng HTTP body **lớn hơn 20 MiB** do boundary, tiêu đề từng phần và các trường khác. Nếu giới hạn tổng body đúng 20 MiB, file 20 MiB có thể bị từ chối dù file tự thân không vượt yêu cầu nghiệp vụ.

### 3.2. Content-Length và Transfer-Encoding

Với HTTP/1.1, client có thể khai báo kích thước body qua **Content-Length** hoặc dùng cơ chế truyền theo chunk khi phù hợp. **Không coi giá trị Content-Length là bằng chứng đáng tin duy nhất**: thiết bị phải bảo đảm framing hợp lệ và theo dõi lượng dữ liệu nhận thực tế.

Với HTTP/2 và HTTP/3, dữ liệu được mang trong các frame/stream theo cơ chế khác HTTP/1.1. Một yêu cầu ở mức ứng dụng vẫn có body và vẫn cần ngưỡng, nhưng **kích thước từng frame không phải kích thước toàn bộ request**. Nếu các lớp trung gian chuyển đổi phiên bản HTTP, cách diễn giải ranh giới request phải nhất quán để tránh sai khác khi kiểm tra và chuyển tiếp.

Việc xử lý mâu thuẫn header định ranh giới dữ liệu, chuyển đổi protocol và request normalization phải tuân thủ chuẩn HTTP và quy tắc parser chặt chẽ. Không “chữa” sai lệch parser bằng cách chỉ tăng giới hạn body.

### 3.3. Compression, encoding và dạng dữ liệu

Body nén có thể rất nhỏ trên đường truyền nhưng trở nên lớn sau khi ứng dụng giải nén. Vì vậy nên xem xét:

1. **Giới hạn dữ liệu nhận được** trước khi giải nén.
2. **Giới hạn kích thước đầu ra sau giải nén** khi ứng dụng hoặc gateway hỗ trợ.
3. Giới hạn **tỉ lệ giải nén, độ sâu lồng nhau, thời gian và CPU** tại thành phần xử lý file/định dạng khi thích hợp.
4. Kiểm tra cùng định dạng dữ liệu mà ứng dụng thực sự sử dụng, để tránh trường hợp WAF chỉ thấy bản nén còn backend phân tích bản đã giải nén.

Đối với JSON, XML hay multipart, chỉ kiểm tra tổng số byte cũng không đủ: một payload dưới ngưỡng vẫn có thể chứa quá nhiều phần tử, trường lồng nhau hoặc cấu trúc phức tạp. Parser và ứng dụng cần thêm **schema validation** và hạn mức theo cấu trúc.

## 4. Vị trí áp dụng giới hạn trong một kiến trúc web

~~~mermaid
flowchart LR
    C[Client] --> CDN[CDN / Edge]
    CDN --> WAF[WAF]
    WAF --> RP[Reverse proxy / Ingress]
    RP --> APP[API / Web app]
    APP --> STORE[Object storage / Database]
~~~

Trong thực tế, WAF có thể nằm **ngay trong CDN, reverse proxy, ingress hoặc một dịch vụ cloud**, không nhất thiết là một hộp mạng riêng. Sơ đồ minh họa các **chức năng** để phân tích giới hạn ở từng lớp.

| Lớp | Có thể kiểm soát | Câu hỏi vận hành |
| --- | --- | --- |
| CDN/edge | Ngưỡng upload, header, thời gian chờ, số kết nối, rate limiting tùy dịch vụ | Request bị từ chối từ edge hay đã đến origin? |
| WAF | Giới hạn request, giới hạn vùng body kiểm tra, quy tắc theo đường dẫn nếu hỗ trợ | Khi quá giới hạn, WAF chặn, bỏ qua, hay chỉ phân tích một phần? |
| Reverse proxy/ingress | Body size, buffering, timeout, header size | Phần proxy đang reject trước khi WAF có cơ hội quan sát? |
| API gateway | Giới hạn theo route, client, API, quota và xác thực nếu có | Endpoint upload khác endpoint JSON ra sao? |
| Ứng dụng | Giới hạn body thực nhận, schema, số mục, kích thước từng trường/tệp | Nếu proxy bị bypass, app có tự bảo vệ được không? |
| Storage/worker | Giới hạn loại file, dung lượng lưu, xử lý hậu kỳ | File lớn đã qua mạng có tiếp tục gây áp lực khi xử lý không? |

**Nguyên tắc triển khai:** đặt giới hạn ở **điểm sớm có thể chặn hiệu quả**, đồng thời giữ kiểm tra tại backend vì yêu cầu có thể đến qua đường khác, proxy khác hoặc trong một biến thể triển khai mới. Một lớp giới hạn quá cao không thể bù cho tầng sau có bộ nhớ hoặc parser yếu; một lớp quá thấp có thể làm chức năng hợp lệ không thể sử dụng.

### 4.1. Giới hạn tiếp nhận và giới hạn kiểm tra của WAF

Hai khái niệm rất dễ nhầm:

- **Enforcement/request body maximum:** ngưỡng mà hệ thống **cho phép hoặc từ chối** một request vì quá kích thước.
- **Inspection/body processing limit:** lượng nội dung tối đa WAF **đọc và phân tích bằng các quy tắc**; có thể nhỏ hơn ngưỡng hệ thống thực sự tiếp nhận.

Giả sử một WAF chỉ phân tích 128 KiB đầu của một body 5 MiB. Tùy cấu hình và sản phẩm, nó có thể **từ chối** body vượt ngưỡng hoặc **chỉ quét phần đầu rồi cho request đi tiếp**. Trường hợp thứ hai có nguy cơ tạo **điểm mù bảo mật**: một rule phát hiện mẫu bất thường ở body sẽ không đánh giá phần chưa được đọc.

Do đó, khi xem cấu hình, đừng chỉ hỏi “giới hạn WAF bao nhiêu MiB?”; phải hỏi:

1. Thiết bị **chặn** vượt ngưỡng nào?
2. Thiết bị **kiểm tra đầy đủ** đến bao nhiêu byte?
3. Với body vượt giới hạn kiểm tra, hành động là **reject, partial inspection, bypass hay chỉ ghi log**?
4. Có ngoại lệ cho **file upload**, **multipart**, **streaming** hoặc một số content type hay không?
5. Trong **detection-only/monitor mode**, hành vi có khác enforcement mode không?

Chỉ khi nắm rõ cả năm điểm mới có thể đánh giá rằng body lớn đã được bảo vệ theo mục tiêu thiết kế.

### 4.2. Ranh giới WAF và ứng dụng

Giới hạn của WAF không nên trở thành căn cứ để ứng dụng bỏ kiểm tra dữ liệu. API vẫn phải xác minh quyền người dùng, Content-Type, cấu trúc JSON, độ dài trường, số phần tử, quota theo tài khoản, loại file được phép, virus/malware scanning khi cần và tổng dung lượng lưu trữ.

Ngược lại, đặt mọi kiểm tra tại ứng dụng có thể buộc backend tốn tài nguyên nhận và xử lý request bất thường trước khi quyết định từ chối. Vì vậy **proxy/WAF chịu trách nhiệm giới hạn sớm; ứng dụng chịu trách nhiệm xác thực dữ liệu và chính sách nghiệp vụ**.

## 5. Những mã phản hồi HTTP thường gặp

| Trạng thái | Tên theo HTTP hiện đại | Điều thường gợi ý | Lưu ý |
| --- | --- | --- | --- |
| **413** | Content Too Large | Body/request content lớn hơn mức server chấp nhận | Tên cũ thường được gọi là Payload Too Large |
| **414** | URI Too Long | Request target/URI vượt giới hạn mà server hỗ trợ | Không phải lỗi file upload lớn |
| **431** | Request Header Fields Too Large | Header riêng lẻ hoặc tổng header quá lớn | Cần kiểm tra cookie, token và proxy |
| **400** | Bad Request | Cú pháp, framing hoặc yêu cầu không hợp lệ | Không chứng minh lỗi chỉ do kích thước |
| **429** | Too Many Requests | Tần suất gửi request vượt chính sách | Đây là **rate limit**, không phải size limit |
| **502/503/504** | Các lỗi gateway/service | Thành phần trung gian hoặc backend thất bại | Không nên tự kết luận kích thước là nguyên nhân |

Theo **RFC 9110**, 413 chỉ ra rằng server từ chối xử lý vì nội dung yêu cầu lớn hơn mức sẵn sàng hoặc có thể xử lý. Nếu giới hạn chỉ mang tính tạm thời, server có thể gửi **Retry-After** trong các trường hợp thích hợp. Tuy nhiên không phải sản phẩm WAF nào cũng trả đúng 413 cho mọi quy tắc kích thước: một rule tùy chỉnh có thể dùng 403 hoặc một mã khác. Khi phân tích phải kết hợp **status, response header, request ID và log rule**.

Về trải nghiệm người dùng, phản hồi 413 nên đi kèm thông báo rõ giới hạn upload hoặc kích thước được chấp nhận, tránh làm lộ cấu hình nhạy cảm. Nếu yêu cầu đã bị chặn ở edge, frontend có thể hiển thị thông báo phù hợp mà không tự động gửi lại cùng payload lớn vô hạn.

## 6. Thiết kế ngưỡng dựa trên nghiệp vụ

### 6.1. Phân nhóm endpoint

Thay vì dùng một ngưỡng rất rộng cho toàn bộ site, phân loại chức năng và thiết kế ngưỡng cho mỗi nhóm **nếu nền tảng có hỗ trợ chính sách theo route**:

| Nhóm endpoint | Dữ liệu thông thường | Giới hạn minh họa | Kiểm soát bổ sung |
| --- | --- | --- | --- |
| API giao dịch JSON | Object JSON tương đối nhỏ | 64 KiB body | Schema, số dòng hàng, độ sâu JSON |
| Webhook tích hợp | JSON có chữ ký, đôi khi lớn hơn API chính | 1 MiB body | Xác minh chữ ký, chống phát lại, quota |
| Upload ảnh | Multipart/file nhị phân | 20 MiB **tổng body** | Giới hạn từng file, loại file, số file, quét nội dung |
| Upload PDF chứng từ | Multipart/file nhị phân | 25 MiB **tổng body** | Giới hạn loại file, hậu xử lý và lưu trữ |
| Trang chỉ đọc | GET/HEAD thường không cần body | Hạn chế body theo cấu hình hỗ trợ | Giới hạn URL/query/header |
| Endpoint nội bộ quản trị | Metadata nhỏ | Nhỏ, theo API contract | Xác thực mạnh, mạng nguồn, audit |

Các con số trong bảng **chỉ là ví dụ**, không phải ngưỡng mặc định hay khuyến nghị áp dụng cho mọi hệ thống. Với API trả nhận dữ liệu nhị phân, streaming, camera, sao lưu hoặc upload nhiều phần, hợp đồng API sẽ khác đáng kể.

### 6.2. Cách chọn ngưỡng có căn cứ

1. **Lấy yêu cầu sản phẩm:** kích thước file tối đa công bố, số tệp mỗi lần, số mục trong một đơn hàng, giới hạn payload của webhook và hợp đồng API.
2. **Quan sát lưu lượng hợp lệ:** thống kê kích thước request theo route, phương thức, client và môi trường; xem phân vị cao như p95/p99 cùng các trường hợp hiếm như sao lưu và cuối tháng.
3. **Xác định giới hạn cứng:** ngưỡng mà backend, parser, tài nguyên lưu trữ và upstream có thể xử lý an toàn khi có nhiều request đồng thời.
4. **Tính phần overhead hợp lệ:** multipart boundary, metadata, chữ ký, encoding, các header cần thiết và sai khác giữa MiB/MB.
5. **Chọn ngưỡng theo route:** vừa đủ cho nhu cầu được phê duyệt, có biên độ hợp lý; xem xét ngoại lệ có thời hạn.
6. **Đối chiếu mọi lớp:** CDN, WAF, proxy, ingress, API gateway, app, serverless runtime và nơi lưu file.
7. **Thử positive/negative:** ở mức dưới, bằng và vượt ngưỡng; kiểm tra mã HTTP và điểm chặn thực sự.
8. **Giám sát sau triển khai:** phân tích 413/431/414, số lỗi upload hợp lệ, latency và tải tài nguyên.

Ngưỡng phải là một **quyết định kỹ thuật có owner và điều kiện kiểm thử**, thay vì một giá trị được sao chép từ cấu hình mẫu.

### 6.3. Tính đến tải đồng thời

Một ngưỡng 20 MiB có thể phù hợp với một lần upload nhưng không có nghĩa hệ thống xử lý được số lượng upload đồng thời không giới hạn. Cần cân nhắc số kết nối, lượng buffer trên RAM/disk, tốc độ mạng, dung lượng file tạm, timeout, tác vụ quét file và tốc độ xử lý backend.

Với endpoint upload lớn, có thể dùng streaming hoặc **upload trực tiếp đến object storage qua URL cấp quyền ngắn hạn** nếu kiến trúc hỗ trợ. Cách đó giảm việc truyền toàn bộ file qua API server, nhưng yêu cầu thiết kế an toàn riêng: phạm vi URL, kích thước/loại file, quyền sở hữu object, thời hạn, quét hậu tải lên và kiểm soát tải xuống. Không coi việc tránh WAF trên tuyến upload là tự động an toàn.

## 7. Ví dụ cấu hình tại reverse proxy: Nginx

Nginx có directive **client_max_body_size** để giới hạn kích thước body được chấp nhận, có thể khai báo ở phạm vi http, server hoặc location. Khi request vượt giới hạn thực thi, Nginx thường trả HTTP **413**. Cấu hình phải được áp dụng ở đúng virtual host, location và phiên bản phần mềm đang dùng.

Ví dụ dưới đây **chỉ dùng trong phòng lab hoặc làm tài liệu tham khảo**, với server_name và backend giả định:

~~~nginx
server {
    listen 443 ssl;
    server_name app.lab.test;

    # Ngưỡng mặc định cho body ở site này.
    client_max_body_size 64k;

    location /api/ {
        proxy_pass http://api_backend;
    }

    # Chỉ endpoint upload được phép nhận body lớn hơn.
    location /upload/ {
        client_max_body_size 20m;
        proxy_pass http://upload_backend;
    }
}
~~~

**Cách đọc:**

- Request vào các location kế thừa giá trị server sẽ có body limit 64k, trừ khi có cấu hình ghi đè khác.
- Location upload dùng giới hạn riêng 20m (theo cú pháp kích thước của Nginx), áp dụng cho **tổng request body**, không phải chỉ bytes của file.
- Đây **chưa phải cấu hình server hoàn chỉnh**: certificate/key, các upstream, routing, cấu hình an toàn và cơ chế quản lý config chưa được trình bày.
- Một request qua proxy còn có thể bị từ chối bởi edge/WAF, gateway, runtime hoặc ứng dụng trước/sau lớp Nginx.

### 7.1. Giới hạn body và giới hạn header là các directive khác nhau

**client_max_body_size** không phải công cụ tổng quát để giới hạn mọi thành phần HTTP. HTTP header có các giới hạn và cấu hình xử lý buffer riêng; tên directive và hiệu lực phụ thuộc phiên bản Nginx cũng như giao thức HTTP. Hãy kiểm tra tài liệu Nginx tương ứng khi cấu hình request line, cookie hoặc header lớn.

Nếu log ghi lỗi header quá dài, tăng body limit sẽ không xử lý nguyên nhân. Ngược lại, upload 413 do body lớn không nên giải quyết bằng cách nới header buffer.

### 7.2. Kiểm tra cấu hình và log

Trên **môi trường lab có quyền quản trị**, có thể kiểm tra cú pháp file Nginx trước khi triển khai:

~~~bash
# Chỉ kiểm tra cú pháp và khả năng đọc các tệp cấu hình.
sudo nginx -t

# Quan sát log bằng công cụ vận hành của lab.
# Đối chiếu thời điểm, request ID và status 413 với endpoint thực tế.
~~~

Kết quả kiểm tra cú pháp thành công **không chứng minh** rằng request đã được chặn đúng ngưỡng. Sau khi cấu hình có hiệu lực, phải thử từ client qua **đúng hostname, đường đi và các lớp trung gian**, đồng thời đối chiếu access/error logs.

## 8. Ví dụ với ModSecurity và WAF kiểm tra body

Một WAF dựa trên **ModSecurity** có các cấu hình liên quan đến request body. Tên directive và semantics có thể khác giữa phiên bản/connector; cần đọc tài liệu đúng phiên bản được triển khai.

~~~apache
# Minh họa cho môi trường lab dùng ModSecurity tương thích.
SecRequestBodyAccess On

# Giới hạn tổng request body được xử lý/chấp nhận theo cấu hình WAF.
SecRequestBodyLimit 10485760

# Giới hạn phần body không phải file trong các trường hợp được hỗ trợ.
SecRequestBodyNoFilesLimit 131072

# Từ chối khi vượt giới hạn thay vì chỉ xử lý một phần.
SecRequestBodyLimitAction Reject
~~~

Trong ví dụ, 10.485.760 byte tương ứng 10 MiB và 131.072 byte tương ứng 128 KiB. Phần cấu hình **không đủ để tạo chính sách WAF hoàn chỉnh**; nó không trình bày rule engine, connector, cấu hình parser, ngoại lệ và các chế độ phát hiện/chặn khác.

Đặc biệt cần kiểm tra:

- **SecRequestBodyLimit** và **SecRequestBodyNoFilesLimit** không phải hai cách viết của cùng một giới hạn. Thành phần multipart là tệp và phần không phải tệp có thể được tính/kiểm tra khác nhau.
- **SecRequestBodyLimitAction Reject** hướng tới từ chối request vượt ngưỡng, còn **ProcessPartial** có thể tiếp tục xử lý một phần body và tạo ra điểm mù nếu policy kỳ vọng quét toàn bộ.
- Trong **DetectionOnly** hoặc một số mode triển khai, hành vi chặn có thể bị thay đổi so với cấu hình enforcement. Không được chỉ đọc directive rồi khẳng định chắc chắn request đã bị từ chối.
- Khi một thành phần phía trước có ngưỡng nhỏ hơn, request có thể bị chặn **trước khi đến ModSecurity**; log WAF có thể không có sự kiện tương ứng.
- Dù WAF kiểm tra body đầy đủ trong giới hạn đã định, ứng dụng vẫn cần kiểm tra schema, quyền truy cập và yêu cầu nghiệp vụ.

**Không sao chép trực tiếp** giá trị 10 MiB vào một ứng dụng thực tế nếu có endpoint upload lớn hơn. Ngưỡng cần tương thích với contract, phương thức xử lý dữ liệu và mức bảo vệ mong muốn.

## 9. Multipart upload, streaming và các trường hợp đặc biệt

### 9.1. Multipart/form-data

Một request multipart có thể gồm file, tên file, field text, boundary và nhiều metadata. Cần phân biệt:

| Loại ngưỡng | Mục tiêu |
| --- | --- |
| Tổng HTTP request body | Chặn request vượt sức chịu đựng của đường xử lý |
| Tổng dung lượng các file | Tránh upload nhiều file làm vượt quota |
| Dung lượng mỗi file | Ràng buộc nghiệp vụ cho từng file |
| Số file và số phần | Tránh quá nhiều phần nhỏ tạo áp lực parser |
| Tên file, metadata, text fields | Tránh field bất thường, xử lý sai định dạng |
| Dung lượng sau giải mã/xử lý | Phòng ngừa áp lực từ file nén, ảnh, PDF hoặc tài liệu phức tạp |

Giới hạn multipart cần được thực hiện ở tầng có khả năng hiểu multipart; một WAF chỉ lọc tổng số byte không nhất thiết có thể kiểm soát **từng file**. Tên tệp và loại MIME từ client chỉ là tín hiệu, không đủ để xác minh loại file.

### 9.2. Streaming, chunked body và upload nhiều phần

Với request body truyền dần, hệ thống phải theo dõi **lượng dữ liệu cộng dồn khi tiếp nhận**. Không được bỏ kiểm tra chỉ vì chưa biết trước tổng kích thước. Cần hiểu buffer, disk-spooling, timeout và việc hủy luồng sau khi vượt ngưỡng có hoạt động đúng không.

Một hệ thống upload nhiều phần có thể chia file thành các request riêng. Giới hạn **mỗi request** khi đó không còn tương đương với giới hạn **tổng dung lượng của một phiên upload hoặc một đối tượng file**. Ứng dụng/storage cần kiểm soát quota, số phần, tổng kích thước và thời hạn của phiên upload.

### 9.3. JSON, GraphQL, XML

Một payload nhỏ về số byte vẫn có thể chứa cấu trúc có chi phí xử lý lớn. Bổ sung các kiểm tra như:

- Độ dài tối đa của từng trường và số lượng phần tử danh sách.
- Độ sâu đối tượng, số lượng node và giới hạn parser.
- Với GraphQL, đánh giá độ phức tạp truy vấn, độ sâu và lượng dữ liệu mà truy vấn có thể yêu cầu.
- Với XML, cấu hình parser an toàn, giới hạn tài nguyên và tránh xử lý thực thể/nguồn bên ngoài ngoài dự kiến.
- Timeout hợp lý và hạn mức CPU/bộ nhớ tại tầng ứng dụng.

Đó là những lớp bảo vệ **bổ sung**, không thể thay thế bằng một con số request body limit.

## 10. Mô hình hóa mối đe dọa cho request size limit

Khi xây threat model, hãy xác định **tài sản cần bảo vệ, nơi có thể tiêu tốn tài nguyên, đường đưa request vào và nơi thực thi quyết định từ chối**.

~~~mermaid
flowchart TD
    R[HTTP request từ client] --> E{Giới hạn ở edge?}
    E -->|Vượt và block| X[Phản hồi lỗi, ghi log có kiểm soát]
    E -->|Được nhận| W{WAF kiểm tra toàn body?}
    W -->|Vượt giới hạn kiểm tra| P{Chính sách vượt ngưỡng?}
    P -->|Reject| X
    P -->|Partial/bypass| A[Khoảng kiểm tra có thể bị thiếu]
    W -->|Trong ngưỡng| Q[Rule WAF / Phân tích HTTP]
    Q --> B[Proxy / API gateway]
    A --> B
    B --> C[Ứng dụng: schema + quota + xác thực]
~~~

**Câu hỏi kiểm soát trọng tâm:** Điều gì xảy ra khi request không thể được WAF kiểm tra đầy đủ? Với endpoint nhạy cảm, thường cần thiết kế để request không vượt vùng kiểm tra hoặc có cơ chế từ chối/chuyển sang luồng xử lý chuyên dụng được kiểm soát.

| Kịch bản | Điểm yếu có thể có | Biện pháp phòng vệ |
| --- | --- | --- |
| Body lớn làm backend quá tải | Proxy hoặc WAF cho phép lớn hơn khả năng backend | Thống nhất giới hạn; quota và concurrency control |
| File upload hợp lệ bị chặn | Một lớp ở edge đặt ngưỡng nhỏ hơn contract | Thiết lập ngưỡng theo route; kiểm thử end-to-end |
| WAF chỉ kiểm tra prefix body | Chế độ partial/bypass bị hiểu lầm là bảo vệ toàn bộ | Định nghĩa hành động khi vượt inspection limit và giám sát |
| Header lớn hoặc URI dài | Nhầm lẫn giữa header/URI limit với body limit | Giới hạn riêng; phân tích lỗi 414/431 |
| Body nén mở rộng quá mức | Chỉ giới hạn kích thước trên đường truyền | Giới hạn dữ liệu giải nén và tài nguyên xử lý |
| Nhiều request nhỏ liên tục | Chỉ giới hạn size, không giới hạn tốc độ/đồng thời | Rate limit, connection/time quotas, DDoS protection |
| Request tới origin qua đường khác edge | Chính sách chỉ có tại CDN/WAF công cộng | Chặn truy cập trực tiếp origin; tự bảo vệ ở proxy/backend |
| Các lớp diễn giải request khác nhau | Framing/normalization không nhất quán | Parser nghiêm ngặt, kiểm tra chuẩn HTTP, đồng nhất cấu hình |

### 10.1. Hạn chế truy cập trực tiếp backend

Nếu edge WAF chặn body quá lớn nhưng origin vẫn truy cập trực tiếp từ Internet hoặc mạng khác, client có thể đi qua đường không chịu chính sách edge. Cần quản lý DNS, routing, firewall/security group, xác thực tại origin và chỉ cho những nguồn upstream hợp lệ, đồng thời giữ giới hạn ở backend.

Trong môi trường microservices, ingress hoặc API gateway nội bộ có thể là điểm thực thi bổ sung cho lưu lượng east-west. Nếu một dịch vụ được gọi trực tiếp từ dịch vụ khác, giới hạn ở WAF công cộng không nhất thiết có tác dụng trên luồng đó.

### 10.2. Giám sát xâm nhập và lưu lượng

WAF log có thể cho thấy request bị chặn do kích thước; IDS/IPS hoặc NDR có thể bổ sung metadata dòng lưu lượng. Tuy nhiên với HTTPS, thiết bị không kết thúc TLS thường không đọc được body HTTP. Việc một network sensor nhìn thấy kết nối TCP lớn **không đủ** để biết rule request body đã áp dụng.

Không nên tự động coi mọi phản hồi 413 là tấn công. Người dùng tải nhầm file lớn, client tích hợp sai contract hoặc thay đổi sản phẩm chưa cập nhật chính sách đều có thể tạo lỗi hợp lệ. Cần phân biệt **misconfiguration, false positive và hoạt động bất thường** bằng log, tần suất và ngữ cảnh.

## 11. Kiểm thử request size limit trong môi trường lab

Giả sử lab có hostname **app.lab.test**, một API JSON và một endpoint upload. Các ví dụ dùng file thử **không chứa dữ liệu nhạy cảm** đã chuẩn bị trước, với quyền kiểm thử và ngưỡng đã được phê duyệt.

### 11.1. Ma trận kiểm thử

| Kịch bản | Kích thước / dữ liệu | Kỳ vọng |
| --- | --- | --- |
| API JSON hợp lệ, nhỏ | Dưới 64 KiB và đúng schema | Được xử lý theo logic ứng dụng |
| API JSON sát ngưỡng | Gần 64 KiB, hợp lệ | Xác minh chính xác cách tính và làm tròn |
| API JSON vượt ngưỡng | Trên giới hạn được công bố | Bị từ chối ở lớp đã định; thường là 413 |
| Upload hợp lệ | Tổng body nhỏ hơn giới hạn upload, tệp đúng quy định | Được tiếp nhận |
| Upload vượt tổng body | Tổng multipart vượt giới hạn | Bị từ chối, không tạo đối tượng lưu trữ hoàn chỉnh |
| Cookie/header bất thường | Vượt header limit | Bị từ chối tại lớp kiểm soát header; có thể là 431 |
| URI quá dài | Vượt giới hạn request target | Bị từ chối; có thể là 414 |
| Body truyền nhiều chunk | Tổng cộng vượt ngưỡng | Hệ thống vẫn thực thi giới hạn khi nhận luồng |
| Body nén mở rộng lớn | Trên giới hạn xử lý sau giải nén | Tầng giải nén/parser bảo vệ đúng |
| Upload nhiều phần | Mỗi request nhỏ nhưng tổng file vượt quota | Hệ thống upload/storage từ chối tổng dung lượng |

Không cần tạo ra lưu lượng lớn cực đoan để kiểm thử chức năng. Chỉ cần những trường hợp **ngay dưới, tại và ngay trên** ngưỡng trong lab, kèm một số loại dữ liệu được hỗ trợ. Tránh quét/thử tải đến các máy không thuộc phạm vi đánh giá.

### 11.2. Ví dụ curl để gửi tệp thử

~~~bash
# Gửi JSON nhỏ đã chuẩn bị sẵn trong lab.
curl -i --max-time 10 \
  -H 'Content-Type: application/json' \
  --data-binary @sample-small.json \
  https://app.lab.test/api/orders

# Kiểm tra một request JSON vượt ngưỡng bằng tệp thử riêng.
curl -i --max-time 10 \
  -H 'Content-Type: application/json' \
  --data-binary @sample-over-limit.json \
  https://app.lab.test/api/orders

# Thử upload dạng multipart vào endpoint được cấp phép.
curl -i --max-time 30 \
  -F 'file=@sample-document.pdf' \
  https://app.lab.test/upload/
~~~

Lệnh trên là ví dụ thao tác trên **lab**; các file cần tồn tại trước khi chạy và hostname phải trỏ đến endpoint được phê duyệt. Đừng đưa API key, cookie phiên thật hoặc dữ liệu khách hàng vào file thử. Quan sát status code, response headers, thời gian, response body đã làm sạch và request ID; sau đó kiểm tra log trên edge, WAF, proxy và backend.

### 11.3. Cách xác định lớp nào đã từ chối

Nếu nhận 413:

1. Kiểm tra hostname và tuyến: client đang qua CDN/WAF hay gọi thẳng origin?
2. Đối chiếu request ID/correlation ID nếu có, cùng thời điểm ở access log các lớp.
3. Xem WAF có sự kiện **size limit exceeded** hay chỉ có reverse proxy ghi 413.
4. Nếu không thấy request ở backend, xác định lớp upstream đã chặn và kiểm tra đây có phải kết quả dự kiến.
5. Nếu thấy backend vẫn phải nhận/xử lý nhiều dữ liệu, kiểm tra đường streaming, buffer, thứ tự thực thi và policy.
6. Với multipart, tính **tổng body** gồm cả metadata; với body nén, xác minh tầng nào đo dữ liệu trước/sau giải nén.
7. Lặp lại bằng request hợp lệ dưới ngưỡng để chắc chắn chức năng bình thường vẫn hoạt động.

**Tiêu chí đạt:** request hợp lệ theo hợp đồng vẫn hoạt động; request vượt giới hạn bị từ chối đúng lớp; WAF không âm thầm bỏ qua phần cần kiểm tra; backend không nhận dữ liệu trái giới hạn; logs đủ để truy tìm nguyên nhân.

## 12. Giám sát, tinh chỉnh và quản trị thay đổi

### 12.1. Những tín hiệu cần theo dõi

| Tín hiệu | Ý nghĩa thực tế |
| --- | --- |
| Số lần 413 theo route, client và thời gian | Tìm endpoint có nhiều request vượt ngưỡng |
| 414 và 431 | Tách vấn đề request target/header khỏi body |
| WAF event: body limit / inspection limit | Phát hiện nguy cơ WAF chỉ kiểm tra một phần hoặc bỏ qua body |
| p50/p95/p99 request body size theo route | Đo nhu cầu hợp lệ để tinh chỉnh |
| Upload success/failure và phản hồi từ người dùng | Xác định false positive ảnh hưởng sản phẩm |
| Proxy buffer memory, temp disk, CPU, latency | Kiểm tra tác động tài nguyên của body lớn |
| Tần suất và số lượng request đồng thời | Xem size limit có cần kết hợp rate/concurrency limit |
| Thay đổi rule, ngoại lệ và owner | Phát hiện policy drift và ngoại lệ không còn hợp lý |

Ví dụ log **minh họa** đã loại thông tin cá nhân:

~~~text
timestamp=2026-11-28T09:30:00Z
edge_request_id=req-lab-1042
path=/api/orders method=POST
action=BLOCK reason=REQUEST_BODY_LIMIT
observed_body_bytes=81920 configured_limit_bytes=65536
http_status=413
~~~

Đọc log: request bị chặn vì body 81.920 byte vượt ngưỡng 65.536 byte trong ví dụ. Nó **không tự chứng minh** hành vi tấn công. Nếu endpoint dự kiến nhận JSON dưới 64 KiB, hãy kiểm tra client và contract; nếu đây là thay đổi sản phẩm hợp lệ, cần cập nhật thiết kế, kiểm tra toàn bộ lớp và ghi lại phê duyệt.

### 12.2. Cách xử lý false positive

Khi người dùng hợp lệ bị chặn:

1. Thu thập request ID, endpoint, kiểu dữ liệu và kích thước, tránh lưu payload chứa bí mật.
2. Xác minh đúng giới hạn nào gây lỗi: body, header, URI, tổng multipart, size sau giải nén hay rule WAF riêng.
3. Kiểm tra contract API, thay đổi client, proxy và sản phẩm.
4. Nếu cần thay đổi ngưỡng, ưu tiên điều chỉnh **phạm vi hẹp đúng endpoint**, có owner và giới hạn cứng phù hợp tài nguyên.
5. Kiểm tra lại luồng hợp lệ lẫn luồng vượt ngưỡng; đối chiếu WAF inspection limit và backend capacity.
6. Ghi lại thay đổi, thời hạn ngoại lệ, người phê duyệt và tiêu chí khôi phục.

Không nên vô hiệu hóa toàn bộ body inspection của WAF chỉ để một loại file tải lên thành công. Nếu upload cần luồng chuyên dụng, hãy thiết kế một đường xử lý có **kiểm soát kích thước, quyền truy cập, loại file, quét nội dung và quota** riêng.

## 13. Những hiểu lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Request size limit là tối đa kích thước tệp.” | Có thể đo toàn body gồm nhiều file và metadata; giới hạn file đơn lẻ là điều kiện riêng. |
| “WAF cho phép body 20 MiB nghĩa là kiểm tra đầy đủ 20 MiB.” | Giới hạn kiểm tra có thể thấp hơn; phải xem hành động khi vượt ngưỡng. |
| “Có Content-Length hợp lệ nên không cần đếm byte nhận.” | Phải kiểm tra framing và thực tế dữ liệu trên đường tiếp nhận. |
| “Một request lớn chỉ tốn tài nguyên bằng đúng kích thước trên dây.” | Bộ đệm, giải nén, parser, bản sao dữ liệu và xử lý hậu kỳ có thể tốn hơn. |
| “413 giống 429.” | 413 liên quan kích thước nội dung; 429 liên quan tần suất request. |
| “Tăng header limit sẽ sửa lỗi upload body 413.” | Header/URI/body có các giới hạn và mã lỗi khác nhau. |
| “Đã giới hạn ở CDN nên backend không cần giới hạn.” | Có thể có đường đi khác, cấu hình thay đổi hoặc request nội bộ. |
| “Bật WAF là mọi request HTTPS đều được kiểm tra.” | Phải xác minh điểm kết thúc TLS, vùng quan sát và chế độ enforcement. |
| “Chặn body lớn là đủ phòng chống DDoS.” | Cần thêm rate limiting, concurrency limit, timeout và kiểm soát tài nguyên. |
| “Chỉ cần chạy curl thành công dưới ngưỡng.” | Cần thử cả trường hợp vượt ngưỡng và kiểm tra lớp nào thực thi. |

## 14. Bài tập tình huống

**Bối cảnh:** một dịch vụ có API xử lý đơn hàng và endpoint upload hóa đơn. Contract quy định API JSON tối đa **64 KiB**, upload hóa đơn **20 MiB tổng body**, header section ở mức hạn chế riêng. Hệ thống đi qua CDN → WAF → reverse proxy → app. Các kết quả trong bảng là **giả định để học**, chưa phải đo đạc thực tế.

| Thành phần | Cấu hình giả định |
| --- | --- |
| CDN | Tổng body tối đa 25 MiB |
| WAF | Body inspection limit 128 KiB; khi vượt ngưỡng có thể ProcessPartial theo policy hiện tại |
| Reverse proxy | Mặc định 64 KiB; riêng upload 20 MiB |
| API app | JSON schema tối đa 64 KiB; upload kiểm tra file và tổng body |

**Câu hỏi:**

1. Một JSON 80 KiB gửi vào API nên bị từ chối ở đâu và vì sao?
2. Một upload multipart tổng 19 MiB có thể được proxy chấp nhận, nhưng WAF với inspection limit 128 KiB sẽ kiểm tra đầy đủ được hay không?
3. Nếu WAF ProcessPartial và vẫn cho upload 19 MiB đi tiếp, rủi ro giám sát nào xuất hiện?
4. Một tệp đơn lẻ đúng 20 MiB được gửi bằng multipart có chắc đi qua proxy đang giới hạn tổng body 20 MiB không?
5. Khi client nhận 413 mà WAF không có log, nên kiểm tra thành phần nào và vì sao?
6. Nếu số lượng upload đồng thời tăng mạnh nhưng mỗi file đều dưới ngưỡng, cần thêm những kiểm soát nào?
7. Nếu một API nén payload trước khi gửi, vì sao giới hạn 64 KiB ở đường truyền chưa chắc bảo vệ parser backend?

**Gợi ý đáp án:** (1) API JSON vượt contract; reverse proxy có giới hạn 64 KiB và có thể từ chối trước khi app xử lý, song cần kiểm tra đường đi thực tế. (2) Không, khi WAF chỉ phân tích 128 KiB theo cấu hình giả định. (3) Phần body không được kiểm tra có thể tạo điểm mù cho rule phụ thuộc nội dung. (4) Không, metadata và boundary làm tổng multipart lớn hơn file. (5) CDN hoặc reverse proxy có thể chặn trước, hoặc WAF không ghi log; cần đối chiếu request ID. (6) Giới hạn đồng thời/tốc độ, buffer, temp disk, storage quota và timeout. (7) Sau giải nén, dữ liệu có thể lớn hơn đáng kể, cần giới hạn ở tầng xử lý decoded content.

## 15. Tổng kết

**Request size limit** giúp WAF và các lớp xử lý HTTP kiểm soát lượng dữ liệu được tiếp nhận, kiểm tra và chuyển tiếp. Muốn sử dụng hiệu quả, cần phân biệt **body, header, URI, file upload, dữ liệu nén và giới hạn vùng inspection**, chọn ngưỡng theo contract của từng endpoint, đối chiếu giữa edge/WAF/proxy/backend và kiểm thử từ đúng đường đi. Quan trọng nhất là phải biết **request vượt giới hạn sẽ bị chặn hay chỉ được kiểm tra một phần**.

Trong **SECURITY_NETWORK_SECURITY**, request size limit là một phần của kiến trúc phòng vệ nhiều lớp cùng phân đoạn, firewall, xác thực, VPN, IDS/IPS và giám sát. Nó giảm tác động của lưu lượng bất thường khi được kết hợp với kiểm soát tốc độ, kết nối, tài nguyên, xác thực và kiểm tra dữ liệu ở tầng ứng dụng.

### Tài liệu tra cứu

- **RFC 9110 — HTTP Semantics:** ý nghĩa status 413, 414, 431 và các thuộc tính của HTTP request.
- **RFC 9112 — HTTP/1.1:** message framing và quy tắc xử lý Content-Length/Transfer-Encoding.
- **RFC 9113 — HTTP/2** và **RFC 9114 — HTTP/3:** mô hình request qua stream và các đặc điểm giao thức.
- **OWASP Web Application Firewall / ModSecurity Reference Manual:** các khái niệm kiểm tra request body và hành động khi vượt giới hạn.
- **OWASP Core Rule Set Documentation:** cách quản trị chính sách WAF, kiểm soát false positive và khả năng kiểm tra.
- **Nginx Documentation — client_max_body_size:** giới hạn body ở cấu hình http/server/location.
- **OWASP File Upload Cheat Sheet:** giới hạn file, phân loại nội dung, lưu trữ và bảo vệ luồng upload.

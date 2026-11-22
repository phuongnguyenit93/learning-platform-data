# Cache, proxy và intermediary ảnh hưởng đến security

## 1. Vì sao cache và intermediary là một phần của mô hình bảo mật?

Một API hiếm khi giao tiếp trực tiếp từ client đến ứng dụng. Request có thể đi qua CDN, reverse proxy, load balancer, API gateway, WAF, service mesh và nhiều cache trước khi tới application service. Response cũng có thể được lưu, biến đổi, nén, giải nén, chuyển tiếp hoặc phục vụ lại bởi các thành phần này.

Mỗi intermediary có thể thay đổi cách hệ thống hiểu danh tính người gọi, địa chỉ đích, scheme, đường dẫn, header, trạng thái kết nối và nội dung response. Cache còn có thể trả dữ liệu đã lưu mà không gọi lại ứng dụng. Vì vậy, một quyết định phân quyền đúng ở application vẫn có thể bị vô hiệu hóa nếu cache phục vụ nhầm response của người dùng khác; một giới hạn theo IP có thể sai nếu proxy chuyển tiếp địa chỉ không đáng tin; một WAF có thể kiểm tra request theo cách khác với backend và tạo ra lỗ hổng parsing.

Các rủi ro thường gặp gồm:

- Dữ liệu cá nhân, token hoặc response theo tenant bị lưu trong shared cache rồi phục vụ cho người khác.
- Cache key thiếu một tham số quan trọng, khiến hai request khác nhau nhận cùng một response.
- Kẻ tấn công đầu độc cache bằng Host, header hoặc tham số không được đưa vào cache key.
- Proxy ghi đè hoặc tin nhầm Forwarded, X-Forwarded-For, X-Forwarded-Proto hay Host, làm sai IP nguồn, scheme hoặc địa chỉ ứng dụng tin cậy.
- CDN, WAF và backend diễn giải độ dài body, đường dẫn hoặc header khác nhau, tạo request smuggling hoặc bypass kiểm soát.
- TLS chỉ được bảo vệ đến proxy đầu tiên, trong khi đoạn mạng nội bộ sau đó truyền dữ liệu nhạy cảm không được mã hóa.
- Proxy tự retry một request có side effect, khiến đơn hàng, giao dịch hoặc thông báo được thực hiện nhiều lần.

Trong thiết kế bảo mật API, cần lập bản đồ toàn bộ đường đi của request và response. Với mỗi hop, xác định dữ liệu nào được tin cậy, thành phần nào có quyền sửa header, cache nào được phép lưu dữ liệu, và kiểm soát nào phải được thực thi lại ở phía ứng dụng.

## 2. Các loại intermediary và ranh giới tin cậy

| Thành phần | Vai trò thường gặp | Rủi ro bảo mật cần xét |
|---|---|---|
| Forward proxy | Đại diện client truy cập mạng ngoài | Rò rỉ thông tin xác thực, kiểm soát đích đến và nhật ký truy cập |
| Reverse proxy | Nhận request công khai và chuyển đến backend | Tin sai Host/Forwarded header, path rewrite, TLS termination |
| Load balancer | Phân phối request tới nhiều instance | Sai affinity, retry trùng, lộ địa chỉ backend, giới hạn không đồng nhất |
| CDN / edge cache | Phân phối nội dung gần client và cache response | Rò rỉ response cá nhân, cache poisoning, cache key thiếu |
| API gateway | Định tuyến, xác thực sơ bộ, quota và chuyển đổi protocol | Chính sách khác application, header bị sửa hoặc bỏ qua |
| WAF | Phát hiện hoặc chặn request đáng ngờ | Khác biệt parser với backend, false negative/positive, bypass |
| Service mesh / sidecar | Mã hóa, định tuyến và quan sát traffic nội bộ | Danh tính workload sai, policy lệch giữa các service |
| Browser cache | Lưu response phía client | Dữ liệu nhạy cảm tồn tại trên thiết bị dùng chung hoặc sau logout |

Không phải intermediary nào cũng đáng tin như nhau. CDN có thể là bên thứ ba; proxy nội bộ có thể do nhóm khác vận hành; thiết bị của người dùng có thể bị chia sẻ hoặc bị kiểm soát. Hãy xác định rõ:

1. Ai vận hành thành phần và ai có quyền thay đổi cấu hình?
2. Thành phần có thể đọc body, cookie, Authorization hoặc dữ liệu cá nhân không?
3. Nó có thể thêm, sửa, xóa header hay thay đổi đường dẫn không?
4. Nó có lưu request/response, log body hoặc tạo bản sao dữ liệu không?
5. Backend xác thực được intermediary bằng cách nào: mạng riêng, mTLS, workload identity hay chữ ký?
6. Khi thành phần lỗi hoặc bị bỏ qua, backend có còn thực thi xác thực, phân quyền và giới hạn tài nguyên không?

Mô hình tin cậy nên thể hiện cả các hop bên ngoài và nội bộ. Không coi một request là đáng tin chỉ vì nó đến từ địa chỉ IP private hoặc từ một subnet của cluster.

## 3. HTTP cache hoạt động như thế nào?

HTTP cache lưu một response để có thể dùng lại cho request phù hợp trong tương lai. Cache có thể ở browser, reverse proxy, CDN hoặc gateway. Việc response có được lưu và có thể dùng lại hay không phụ thuộc method, status, header điều khiển cache, validator và chính sách riêng của cache.

Một cache thường thực hiện các bước:

1. Xác định cache key từ request, thường bắt đầu bằng method và target URI; các header được nêu trong Vary có thể bổ sung vào khóa.
2. Tìm response đã lưu phù hợp với cache key.
3. Kiểm tra response còn fresh hay đã stale dựa trên freshness lifetime và tuổi response.
4. Nếu còn fresh và được phép dùng lại, trả response đã lưu.
5. Nếu stale, có thể gửi conditional request tới origin bằng If-None-Match hoặc If-Modified-Since.
6. Nếu origin trả 304 Not Modified, cache có thể dùng body đã lưu và cập nhật metadata; nếu origin trả response mới, cache cập nhật bản lưu theo chính sách.

Điểm quan trọng về bảo mật: khi cache trả response, application có thể không được gọi. Do đó, kiểm tra quyền chỉ nằm trong code của application không đủ để bảo vệ một response đã được cache. Cache key và chỉ thị cache phải bảo đảm response chỉ được dùng lại trong đúng phạm vi danh tính và ngữ cảnh.

### 3.1 Phân biệt các chỉ thị Cache-Control

| Chỉ thị | Ý nghĩa | Lưu ý bảo mật |
|---|---|---|
| no-store | Cache tuân thủ không được lưu request/response tương ứng | Dùng cho dữ liệu nhạy cảm cần tránh lưu ở cache; không xóa bản sao đã lưu trước đó |
| no-cache | Có thể lưu nhưng phải xác thực lại trước khi dùng lại | Không đồng nghĩa với “không lưu” |
| private | Response chỉ dành cho private cache, không dành cho shared cache | Hữu ích cho response cá nhân có thể cache ở browser |
| public | Cho phép shared cache lưu response trong những điều kiện phù hợp | Không dùng tùy tiện cho dữ liệu phụ thuộc người dùng |
| max-age=N | Freshness lifetime tối đa theo giây cho cache | Chọn thời gian phù hợp với độ nhạy và tốc độ thay đổi dữ liệu |
| s-maxage=N | Freshness lifetime cho shared cache; ưu tiên hơn max-age tại shared cache | Cần kiểm soát CDN/reverse proxy có dùng shared cache |
| must-revalidate | Khi stale, phải xác thực lại trước khi dùng lại | Hạn chế dùng response cũ khi không liên hệ được origin |
| proxy-revalidate | Yêu cầu shared cache xác thực lại response stale | Áp dụng cho shared cache |
| no-transform | Cấm intermediary biến đổi nội dung khi chỉ thị được tuân thủ | Hữu ích khi biến đổi nội dung có thể làm hỏng chữ ký hoặc kiểm soát toàn vẹn |

Ví dụ response không nên được lưu:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json
~~~

Ví dụ response cá nhân được phép cache riêng ở browser nhưng không ở shared cache:

~~~http
HTTP/1.1 200 OK
Cache-Control: private, max-age=60
Vary: Accept-Language
Content-Type: application/json
~~~

Ví dụ response công khai có thể được CDN cache trong thời gian ngắn:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=30, s-maxage=120
ETag: "catalog-v42"
Content-Type: application/json
~~~

Các ví dụ chỉ minh họa. Chính sách thực tế phải xét dữ liệu, danh tính, khả năng thay đổi, cấu hình CDN và hợp đồng dịch vụ. no-store là chỉ thị cho cache tuân thủ HTTP; nó không thể ngăn mọi thành phần độc hại, công cụ debug hoặc hệ thống log cố ý sao chép dữ liệu.

### 3.2 no-cache khác no-store

Hai chỉ thị thường bị nhầm lẫn:

- Cache-Control: no-cache cho phép cache lưu response nhưng buộc phải xác thực lại trước khi dùng response đó.
- Cache-Control: no-store yêu cầu cache không lưu response.

Nếu response chứa thông tin cá nhân hoặc bí mật mà không muốn browser hay shared cache lưu lại, hãy dùng no-store. Nếu muốn browser giữ bản sao nhưng phải hỏi server trước mỗi lần dùng lại, có thể cân nhắc no-cache kết hợp validator và kiểm tra quyền phù hợp.

Không nên chỉ dựa vào tên chỉ thị để suy ra chính sách. Hãy kiểm tra cả header thực tế sau khi qua CDN/gateway, vì intermediary có thể ghi đè, gộp hoặc loại bỏ header.

## 4. Phân loại dữ liệu trước khi bật cache

Không phải mọi response đều có cùng yêu cầu bảo mật. Có thể phân loại như sau:

| Loại response | Ví dụ | Chính sách khởi điểm |
|---|---|---|
| Công khai, không cá nhân hóa | Danh mục công khai, metadata phiên bản | Có thể dùng shared cache với TTL và validator |
| Công khai nhưng thay đổi thường xuyên | Tỷ giá hiển thị, trạng thái công khai | TTL ngắn, revalidation hoặc purge có kiểm soát |
| Cá nhân hóa | Hồ sơ người dùng, giỏ hàng, lịch sử giao dịch | Thường dùng private; cân nhắc no-store tùy độ nhạy |
| Nhạy cảm | Token, dữ liệu thanh toán, hồ sơ định danh | no-store; kiểm soát cả log và bản sao tại intermediary |
| Nội dung theo tenant | Báo cáo, cấu hình, dữ liệu dự án | Không đưa vào shared cache trừ khi khóa phân vùng tenant được chứng minh an toàn |
| Response lỗi có ngữ cảnh | 401, 403, 404, 429 | Tránh cache chung nếu kết quả phụ thuộc principal, quota hoặc trạng thái hiện tại |

Đây là hướng dẫn khởi điểm, không phải luật áp dụng tuyệt đối cho mọi status code. Cần đánh giá body, header, cookie và quyền truy cập của response. Ví dụ một trang 404 có thể tiết lộ sự tồn tại của đối tượng; một response 429 có thể phản ánh quota riêng của tenant; một response 401 có thể chứa challenge hoặc thông tin xác thực.

Đối với API có đăng nhập, lựa chọn an toàn thường là đặt chính sách cache tường minh ở từng loại endpoint. Đừng để CDN tự suy đoán rằng mọi GET đều công khai. GET có thể trả dữ liệu cá nhân; ngược lại, một số dữ liệu công khai có thể cache an toàn nếu cache key và chính sách được thiết kế đúng.

## 5. Cache key, Vary và nguy cơ rò rỉ dữ liệu

Cache key quyết định response nào được coi là có thể dùng lại cho request nào. Nếu hai request khác nhau về quyền truy cập nhưng cache xem chúng là cùng một key, response có thể bị phục vụ sai người.

Ví dụ một endpoint:

~~~http
GET /api/me HTTP/1.1
Authorization: Bearer token-cua-A
~~~

Nếu CDN cấu hình cache chỉ theo URL và bỏ qua danh tính, response của A có thể bị trả cho B. Đặt Vary: Authorization không phải biện pháp mặc định tốt để sửa lỗi thiết kế này: token tạo cardinality lớn, có nguy cơ bị đưa vào cache key/log và chính sách shared cache quanh Authorization có quy tắc riêng. Với endpoint cá nhân, thường nên tránh shared caching và trả Cache-Control: private hoặc no-store tùy yêu cầu.

### 5.1 Vary dùng khi nào?

Vary khai báo những request header có ảnh hưởng đến biểu diễn response. Ví dụ:

~~~http
Vary: Accept-Encoding, Accept-Language
~~~

Cache cần phân biệt response nén gzip với response không nén, hoặc nội dung tiếng Việt với nội dung tiếng Anh. Nếu origin chọn response theo một header nhưng cache không đưa header đó vào biến thể, client có thể nhận sai nội dung.

Các lưu ý:

- Chỉ đưa vào Vary những header thực sự ảnh hưởng đến biểu diễn.
- Không dùng Vary như một cơ chế phân quyền.
- Vary: Cookie hoặc Vary: Authorization có thể tạo rất nhiều biến thể và làm tăng rủi ro vận hành; hãy cân nhắc không cache shared.
- Nếu response phụ thuộc tenant, vai trò hoặc quyền, cần kiểm soát ở tầng application và tránh cache dùng chung theo URL đơn thuần.
- Kiểm tra cách CDN chuẩn hóa header và cache key; một số nhà cung cấp cho phép cấu hình key riêng ngoài Vary.

### 5.2 Đưa danh tính vào cache key có phải luôn an toàn?

Không. Thêm user ID hoặc tenant ID vào cache key có thể tách response giữa người dùng, nhưng chỉ an toàn khi giá trị đó được suy ra từ danh tính đã xác thực ở một lớp đáng tin. Không dùng X-Tenant-ID, X-User-ID hoặc query parameter do client tự đặt làm bằng chứng danh tính. Nếu proxy tạo cache key từ header không được xác minh, kẻ tấn công có thể giả mạo giá trị hoặc tạo lượng lớn cache entry.

Nếu thật sự cần cache response cá nhân ở một lớp trung gian, cần thiết kế key dựa trên principal đã được xác minh, quyền hiện tại, phiên bản dữ liệu và mọi yếu tố ảnh hưởng nội dung. Cần có kiểm thử chéo tenant/user, invalidation khi quyền thay đổi và kiểm soát không để token thô xuất hiện trong key hoặc log.

## 6. Cache poisoning và cache deception

### 6.1 Cache poisoning

Cache poisoning xảy ra khi kẻ tấn công khiến cache lưu một response không an toàn rồi phục vụ response đó cho người dùng khác. Một nguyên nhân phổ biến là origin sử dụng một header hoặc giá trị request để tạo nội dung nhưng cache không đưa giá trị đó vào cache key.

Ví dụ ứng dụng tạo liên kết tuyệt đối từ Host hoặc X-Forwarded-Host. Kẻ tấn công gửi request với Host tùy ý; origin phản chiếu giá trị đó trong response; CDN lưu response theo URL chuẩn mà không phân biệt header bị sửa. Người dùng khác nhận nội dung đã bị đầu độc.

Biện pháp:

- Chỉ chấp nhận Host thuộc danh sách domain hợp lệ; từ chối host không mong đợi ở edge và application.
- Không xây dựng URL tuyệt đối, redirect hoặc liên kết nhạy cảm từ header do client tùy ý cung cấp.
- Chỉ tin Forwarded/X-Forwarded-* khi request đến từ proxy được xác thực và proxy đã xóa giá trị do client gửi.
- Kiểm tra mọi header có ảnh hưởng nội dung; đưa vào cache key một cách có chủ đích hoặc tắt shared cache.
- Không phản chiếu input chưa kiểm tra vào response có thể được cache.
- Xóa cache đã bị đầu độc khi phát hiện; sửa cả nguyên nhân và phạm vi cache key.

### 6.2 Web cache deception

Web cache deception xảy ra khi cache hiểu một URL là tài nguyên tĩnh có thể cache, còn application hiểu đó là endpoint cá nhân. Ví dụ một ứng dụng trả hồ sơ người dùng tại /account/profile; một quy tắc CDN quá rộng coi đường dẫn kết thúc bằng .css hoặc .jpg là tài nguyên tĩnh. Nếu đường dẫn được định tuyến hoặc chuẩn hóa khiến request vẫn tới endpoint hồ sơ nhưng CDN cache response, dữ liệu cá nhân có thể bị lộ.

Biện pháp:

- Chỉ cache allowlist các đường dẫn/tài nguyên tĩnh đã xác định; tránh quy tắc mở rộng dựa đơn thuần vào phần đuôi file.
- Đồng bộ cách chuẩn hóa path giữa CDN, proxy và application.
- Endpoint cá nhân luôn trả chỉ thị cache rõ ràng; cấu hình CDN tôn trọng hoặc có rule bảo vệ tương đương.
- Kiểm thử đường dẫn có dấu chấm, encoded slash, tham số, dấu gạch chéo cuối và các biến thể path.
- Không để route fallback trả nội dung cá nhân cho URL được CDN coi là asset công khai.

### 6.3 Invalidation và thay đổi quyền

TTL ngắn không giải quyết mọi trường hợp. Nếu người dùng vừa bị thu hồi quyền, response cũ vẫn có thể được cache phục vụ cho đến khi hết hạn. Với dữ liệu có thay đổi quyền truy cập, cần quyết định:

- Có nên cache shared hay không?
- Sự kiện nào phải purge/invalidate: cập nhật dữ liệu, đổi tenant, thu hồi quyền, khóa tài khoản, logout hoặc xóa đối tượng?
- Purge có đảm bảo tới mọi edge location không, và độ trễ tối đa là bao lâu?
- Trong thời gian purge chưa hoàn tất, có thể tạm chuyển endpoint sang no-store hoặc tăng cường kiểm tra tại origin không?

Cache invalidation là một phần của quy trình thay đổi quyền và vòng đời dữ liệu. Không giả định rằng logout ở application tự động xóa browser cache hoặc CDN cache.

## 7. Conditional request, ETag và rủi ro xác thực lại

ETag và Last-Modified giúp giảm băng thông bằng cách cho phép client/cache hỏi response có thay đổi hay chưa:

~~~http
GET /api/reports/123 HTTP/1.1
If-None-Match: "report-v7"
~~~

Nếu representation không thay đổi, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "report-v7"
Cache-Control: private, no-cache
~~~

Client/cache dùng lại body đã lưu. Vì vậy, response 304 cũng có ý nghĩa bảo mật: nó cho biết representation tương ứng vẫn được xem là hợp lệ để dùng lại.

Các quy tắc cần tuân thủ:

1. Xác thực người gọi và kiểm tra quyền truy cập đối tượng trước khi trả 304.
2. Không coi việc client biết ETag là bằng chứng họ có quyền đọc dữ liệu.
3. Khi quyền thay đổi, bảo đảm validator và cache entry cũ không cho phép tiếp tục dùng body.
4. Không tạo ETag dễ suy ra từ dữ liệu nhạy cảm nếu việc so sánh có thể tiết lộ nội dung hoặc trạng thái.
5. Cân nhắc ETag yếu (W/) khi chỉ cần so sánh ngữ nghĩa; ETag mạnh phù hợp khi cần xác nhận byte representation tương đương.
6. Đảm bảo ETag được tính theo representation đúng, gồm biến thể ngôn ngữ/nén nếu cần.

Last-Modified cũng không thay thế phân quyền. Một mốc thời gian có thể không đủ chính xác hoặc không phản ánh thay đổi quyền. Luôn thực hiện kiểm tra authorization theo principal hiện tại.

## 8. Proxy header và xác định danh tính nguồn

Reverse proxy thường kết thúc kết nối client rồi mở kết nối mới đến backend. Backend khi đó nhìn thấy IP của proxy thay vì IP gốc. Proxy có thể truyền thông tin qua:

- Forwarded theo chuẩn RFC 7239.
- X-Forwarded-For cho địa chỉ client/proxy.
- X-Forwarded-Proto cho scheme gốc, ví dụ https.
- X-Forwarded-Host cho host ban đầu.
- X-Forwarded-Port cho cổng bên ngoài.
- Một số header riêng như X-Real-IP hoặc X-Original-URI.

Các header này không tự động đáng tin. Client có thể gửi chúng trực tiếp. Nếu proxy chỉ nối thêm giá trị vào header do client gửi mà backend lấy phần tử đầu tiên, kẻ tấn công có thể giả mạo IP nguồn, vượt allowlist hoặc né rate limit.

### 8.1 Mẫu xử lý an toàn

- Chỉ backend nhận traffic từ các proxy được xác định; dùng firewall, network policy hoặc mTLS/workload identity để giới hạn nguồn.
- Proxy biên phải xóa header forwarding do client gửi trước khi tự tạo giá trị mới.
- Cấu hình application framework chỉ tin đúng số hop hoặc dải IP proxy đã biết.
- Khi phân tích chuỗi X-Forwarded-For, hiểu rõ thứ tự proxy và chọn địa chỉ dựa trên danh sách proxy tin cậy; không mù quáng lấy phần tử đầu hoặc cuối.
- Không dùng header forwarding để cấp quyền nghiệp vụ; IP chỉ nên là tín hiệu cho logging, phát hiện bất thường hoặc chính sách mạng.
- Ghi log cả địa chỉ kết nối trực tiếp tới backend và địa chỉ client đã suy ra, kèm nguồn suy luận nếu cần điều tra.

Ví dụ chuỗi:

~~~text
Client -> Edge proxy -> Internal load balancer -> API

TCP peer tại API: 10.0.4.12 (load balancer)
X-Forwarded-For: 198.51.100.27, 10.0.2.8
~~~

Nếu 10.0.4.12 và 10.0.2.8 thuộc danh sách proxy tin cậy và proxy biên đã ghi đè header đầu vào, địa chỉ client có thể được suy ra là 198.51.100.27. Nếu không biết chuỗi này do ai tạo, không được dùng nó làm cơ sở chặn/mở quyền.

### 8.2 Scheme và Host sau TLS termination

Proxy có thể nhận HTTPS từ client rồi chuyển HTTP nội bộ. Nếu backend không biết scheme gốc, ứng dụng có thể:

- Tạo redirect về HTTP, làm lộ dữ liệu hoặc gây vòng lặp redirect.
- Phát cookie thiếu thuộc tính Secure.
- Sinh absolute URL với host sai.
- Tạo callback hoặc link reset password trỏ đến domain do kẻ tấn công kiểm soát.

Chỉ tin X-Forwarded-Proto và X-Forwarded-Host từ proxy đáng tin. Đặt canonical host ở cấu hình ứng dụng khi có thể; kiểm tra host allowlist trước khi tạo redirect, URL email hoặc callback. Cookie phiên nên được cấu hình Secure, HttpOnly và SameSite phù hợp ngay cả khi TLS kết thúc ở edge.

## 9. TLS termination và bảo vệ hop nội bộ

TLS termination ở CDN hoặc load balancer có thể hợp lý để giảm tải và quản lý chứng thư. Tuy nhiên, TLS từ client đến edge không tự bảo vệ đoạn edge đến backend.

Đánh giá từng đoạn:

| Đoạn kết nối | Câu hỏi bảo mật |
|---|---|
| Client → CDN/edge | Chứng thư đúng domain? TLS version/cipher phù hợp? Có HSTS? |
| CDN → load balancer | Có mã hóa? Xác thực origin? Có thể bị truy cập trực tiếp bỏ qua CDN? |
| Load balancer → service | Có TLS hoặc mTLS? Danh tính workload được xác minh? |
| Service → service | Có xác thực hai chiều, policy mạng và kiểm soát audience/identity? |
| Proxy → dependency bên ngoài | Có xác minh chứng thư, hostname và egress policy? |

Với dữ liệu nhạy cảm hoặc môi trường có nhiều vùng mạng, nên mã hóa cả hop nội bộ và xác thực peer bằng mTLS hoặc cơ chế workload identity phù hợp. Nếu dùng HTTP nội bộ, cần có đánh giá rủi ro rõ ràng về mạng, tenant hạ tầng, khả năng sniffing và kiểm soát truy cập.

Backend nên giới hạn truy cập trực tiếp nếu kiến trúc yêu cầu mọi request đi qua edge đã kiểm soát. Nếu backend vẫn có thể truy cập từ Internet, kẻ tấn công có thể bỏ qua WAF, rate limit và header sanitization ở proxy. Không dùng địa chỉ private như bằng chứng duy nhất cho danh tính service.

## 10. Khác biệt parsing giữa proxy và backend

Một request có thể được nhiều thành phần phân tích theo các quy tắc khác nhau. Nếu proxy và backend không thống nhất về ranh giới message, đường dẫn hoặc header, kẻ tấn công có thể khiến chúng nhìn thấy hai request khác nhau.

### 10.1 HTTP request smuggling

Request smuggling thường liên quan đến bất đồng trong cách các hop xác định độ dài body, đặc biệt khi request có các chỉ thị mâu thuẫn như Content-Length và Transfer-Encoding. Một thành phần có thể dùng header này, thành phần khác dùng header kia, khiến phần byte còn lại bị hiểu thành request kế tiếp trên kết nối được tái sử dụng.

Các biện pháp:

- Dùng proxy và backend đã được cập nhật, cấu hình theo cùng cách xử lý HTTP framing.
- Từ chối request có framing mơ hồ hoặc header độ dài mâu thuẫn; không cố “sửa” theo các cách khác nhau giữa các hop.
- Chuẩn hóa và loại bỏ header hop-by-hop theo đúng quy tắc HTTP trước khi chuyển tiếp.
- Hạn chế hoặc tắt connection reuse nếu một thành phần không thể bảo đảm xử lý framing an toàn.
- Kiểm thử đường đi HTTP/1.1, HTTP/2 và HTTP/3; chú ý downgrade từ HTTP/2 ở edge sang HTTP/1.1 ở origin.
- Theo dõi bất thường như response lệch request, request treo, 400 không nhất quán hoặc kết nối bị đóng bất thường.

Không tự viết HTTP parser nếu có thể dùng thư viện và proxy được duy trì. Khi cấu hình nhiều sản phẩm, phải kiểm thử toàn bộ chuỗi thay vì chỉ kiểm thử riêng từng thành phần.

### 10.2 Header hop-by-hop

Một số header chỉ có ý nghĩa trên một kết nối cụ thể, không được chuyển tiếp nguyên trạng qua mọi hop. Header Connection có thể liệt kê những header hop-by-hop bổ sung. Proxy cần xử lý các header này đúng chuẩn, tránh để header dành cho hop trước ảnh hưởng tới hop sau.

Không chuyển tiếp mù quáng mọi header từ client tới backend. Xác định allowlist header nghiệp vụ cần giữ, loại bỏ header nội bộ do client giả mạo, rồi thêm metadata do proxy có thẩm quyền tạo. Những header như Connection, Keep-Alive, Transfer-Encoding, TE, Trailer, Upgrade và Proxy-Authorization cần được xử lý theo ngữ nghĩa hop-by-hop tương ứng.

### 10.3 Path normalization và định tuyến

Proxy, WAF và framework có thể khác nhau trong việc giải mã %2F, xử lý dấu chấm . và .., dấu gạch chéo kép, dấu gạch chéo cuối, chữ hoa/thường hoặc ký tự Unicode. Nếu WAF kiểm tra /public/../admin theo một cách nhưng backend chuẩn hóa thành /admin, request có thể đi qua policy sai.

Biện pháp:

- Chọn một quy tắc canonical path và áp dụng nhất quán ở edge, gateway và application.
- Không thực hiện authorization trên một dạng path rồi định tuyến trên dạng đã chuẩn hóa khác.
- Từ chối path có encoding mơ hồ hoặc không cần thiết.
- Kiểm thử encoded slash, double encoding, dot segment, duplicate slash, trailing slash và Unicode normalization.
- Ưu tiên route theo cấu trúc đã khai báo; không ghép path tùy ý từ input vào đường dẫn nội bộ.

## 11. Proxy retry, timeout và side effect

Reverse proxy hoặc load balancer có thể tự retry khi upstream lỗi, kết nối bị reset hoặc timeout. Điều này hữu ích cho tính sẵn sàng nhưng có thể làm thao tác được thực hiện nhiều lần.

Ví dụ client gửi POST /payments; backend đã tạo giao dịch nhưng response bị mất trước khi proxy nhận được. Proxy retry sang instance khác và giao dịch thứ hai được tạo. Client chỉ thấy một lần gửi request nhưng hệ thống ghi nhận hai side effect.

Quy tắc thiết kế:

- Chỉ retry tự động các method/thao tác có ngữ nghĩa an toàn hoặc idempotent, trừ khi ứng dụng có cơ chế bảo đảm khác.
- Với thao tác tạo đơn, thanh toán, gửi thông báo hoặc cấp tài nguyên, dùng idempotency key được kiểm tra ở tầng nghiệp vụ và lưu bền vững.
- Định nghĩa timeout nhất quán giữa client, proxy, gateway và service; timeout ngoài phải đủ dài cho timeout trong cộng thêm thời gian xử lý phản hồi.
- Không để nhiều tầng retry độc lập nhân số lần thử. Đặt retry budget tổng và giới hạn số lần retry tại một tầng có đủ ngữ cảnh.
- Khi timeout tạo kết quả không rõ, cung cấp API tra cứu trạng thái bằng idempotency key hoặc operation ID thay vì gửi lại thao tác mù quáng.
- Theo dõi request ID và attempt ID để phân biệt request gốc với lần thử lại.

Proxy có thể buffer request body trước khi gửi backend. Cần giới hạn kích thước buffer, thời gian nhận body, số kết nối và số request đồng thời để tránh chiếm bộ nhớ hoặc giữ kết nối quá lâu. Giới hạn ở edge không thay thế kiểm tra lại ở application.

## 12. Cache, xác thực và phân quyền trong API nhiều tenant

Trong hệ thống multi-tenant, cache cần giữ đúng ranh giới tenant và quyền. Một response có thể phụ thuộc vào:

- Tenant hiện tại.
- Người dùng và vai trò.
- Quyền trên đối tượng cụ thể.
- Trạng thái nghiệp vụ, ví dụ đơn hàng đang ở bước nào.
- Feature flag hoặc gói dịch vụ.
- Ngôn ngữ, định dạng và vùng dữ liệu.

Nếu cache key không thể hiện các yếu tố ảnh hưởng response, hoặc cache không xác thực lại trước khi phục vụ, có thể xảy ra rò rỉ dữ liệu chéo tenant. Không phải mọi yếu tố đều nên đưa vào cache key; với response cá nhân, tắt shared cache thường đơn giản và an toàn hơn.

Các nguyên tắc:

1. Xác thực và phân quyền tại application cho mọi request có thể tới origin.
2. Không coi cache hit là bằng chứng người gọi có quyền.
3. Không dùng ID do client gửi để phân vùng cache nếu chưa đối chiếu với principal.
4. Với dữ liệu công khai, chỉ cache khi response thực sự không phụ thuộc quyền hoặc danh tính.
5. Với dữ liệu riêng, dùng private cache hoặc no-store theo độ nhạy; cấu hình CDN không cache bất chấp header.
6. Khi đổi quyền, xóa hoặc chuyển tenant, có cơ chế invalidation phù hợp.
7. Kiểm thử hai user và hai tenant có cùng URL nhưng quyền khác nhau.

Nếu application dùng cache nội bộ (Redis, in-memory cache), các nguyên tắc tương tự vẫn áp dụng. Cache nội bộ không phải lý do để bỏ qua tenant scoping, authorization hoặc TTL.

## 13. Các header bảo mật qua intermediary

Proxy có thể thêm, xóa hoặc ghi đè header response. Cần quyết định thành phần nào là nơi chịu trách nhiệm cuối cùng cho từng header:

| Header | Mục đích | Lưu ý khi có proxy |
|---|---|---|
| Strict-Transport-Security | Yêu cầu browser ưu tiên HTTPS | Chỉ phát từ host HTTPS hợp lệ; cân nhắc phạm vi includeSubDomains |
| Content-Security-Policy | Giới hạn nguồn nội dung browser được tải | Tránh proxy ghi đè policy theo cách làm yếu bảo vệ |
| X-Content-Type-Options: nosniff | Ngăn một số kiểu MIME sniffing | Đảm bảo không bị loại bỏ trên response cuối |
| Referrer-Policy | Giới hạn thông tin referrer gửi đi | Kiểm tra response qua CDN và redirect |
| Permissions-Policy | Giới hạn tính năng browser | Đồng bộ với chính sách ứng dụng |
| Cache-Control | Điều khiển lưu và dùng lại response | CDN có thể có rule override; cần kiểm thử header thực tế |
| Set-Cookie | Tạo hoặc cập nhật cookie | Không gộp sai nhiều Set-Cookie; bảo toàn Secure/HttpOnly/SameSite |

Không giả định header do application phát ra sẽ tới client nguyên vẹn. Hãy kiểm tra response tại edge và từ client thực tế. Nếu proxy thêm security header, cần quản lý cấu hình tập trung, tránh hai lớp phát các giá trị mâu thuẫn. Với cookie, bảo đảm proxy không vô tình bỏ thuộc tính Secure hoặc làm sai Domain/Path.

## 14. Thiết kế chính sách cache và proxy theo endpoint

Một ma trận endpoint giúp tránh cấu hình chung quá rộng:

| Endpoint | Dữ liệu/side effect | Cache | Proxy/gateway |
|---|---|---|---|
| GET /catalog | Danh mục công khai | Shared cache, TTL ngắn, ETag | Host allowlist, giới hạn request |
| GET /me | Hồ sơ cá nhân | private hoặc no-store; không shared cache | Xác thực; forwarding header chỉ từ proxy tin cậy |
| GET /orders/{id} | Dữ liệu theo quyền đối tượng | Thường không shared cache; kiểm tra quyền trước 304 | Không cho bypass gateway; giới hạn body/timeout |
| POST /payments | Side effect tài chính | Không cache | Idempotency, không retry mù, audit |
| GET /reports/{id}/download | Tệp theo tenant | Chính sách riêng; URL ký có hạn nếu dùng CDN | Kiểm tra quyền khi cấp URL; giới hạn egress |
| GET /health | Trạng thái vận hành | Thường không public; chỉ expose tối thiểu | Chỉ mạng giám sát được phép truy cập |

Với download qua CDN, có thể dùng signed URL hoặc token ngắn hạn để cấp quyền truy cập. Token phải có thời hạn, phạm vi tài nguyên và quyền tối thiểu; tránh đưa token vào log hoặc referrer. Khi quyền bị thu hồi, cân nhắc TTL ngắn, revoke list hoặc cơ chế kiểm tra origin tùy yêu cầu.

## 15. Ví dụ: cấu hình response cho API hồ sơ và danh mục

Giả sử hệ thống có hai endpoint:

- GET /api/me: trả hồ sơ của người đang đăng nhập.
- GET /api/catalog: trả danh mục công khai.

Response hồ sơ:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json
Vary: Accept
~~~

Application xác thực token, lấy user ID từ principal, kiểm tra trạng thái tài khoản và trả đúng hồ sơ của user. CDN được cấu hình bypass cache cho /api/me; browser không được yêu cầu lưu response. Không dùng X-User-ID do client gửi để chọn hồ sơ.

Response danh mục:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=30, s-maxage=120
ETag: "catalog-v42"
Vary: Accept-Language, Accept-Encoding
Content-Type: application/json
~~~

CDN có thể cache response danh mục theo URL và các biến thể ngôn ngữ/nén. Origin kiểm soát canonical host và chỉ phát response công khai. Khi danh mục thay đổi, hệ thống cập nhật ETag và purge cache theo quy trình đã định.

Nếu một request /api/catalog mang cookie đăng nhập nhưng nội dung vẫn hoàn toàn công khai, cần xác nhận cookie không làm thay đổi response và CDN không dùng cookie để cá nhân hóa. Nếu nội dung phụ thuộc gói thuê bao hoặc tenant, endpoint không còn là response công khai đơn giản và cần chính sách khác.

## 16. Kiểm thử bảo mật cache và intermediary

Kiểm thử phải chạy qua toàn bộ đường đi thực tế, không chỉ gọi thẳng application.

| Nhóm kiểm thử | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Cache isolation | User A gọi trước, user B gọi cùng URL sau | B không nhận response riêng của A |
| Tenant isolation | Hai tenant cùng gọi endpoint có cùng resource ID | Không có dữ liệu chéo tenant |
| Cache directive | Kiểm tra response nhạy cảm qua browser/CDN | Không có shared cache entry ngoài chính sách |
| Conditional request | User mất quyền nhưng gửi ETag cũ | Server kiểm tra quyền và không xác nhận 304 trái phép |
| Vary | Thay Accept-Language/Accept-Encoding | Nhận đúng biến thể, không trộn response |
| Cache poisoning | Thay Host, Forwarded, query hoặc header không được key | Không đầu độc response phục vụ người khác |
| Cache deception | Thêm suffix/encoded path vào endpoint cá nhân | CDN không cache response cá nhân |
| Forwarded header | Client tự gửi X-Forwarded-For giả | Proxy biên xóa và tạo metadata tin cậy |
| Direct origin | Gọi backend bỏ qua CDN/gateway | Bị chặn hoặc vẫn được bảo vệ đầy đủ |
| TLS hop | Quan sát cấu hình edge-to-origin và service-to-service | Mã hóa/xác thực theo yêu cầu |
| Parser differential | Gửi framing mơ hồ và path encoding khác nhau | Bị từ chối nhất quán; không smuggle/bypass |
| Retry | Upstream timeout sau khi xử lý POST | Không tạo side effect trùng |
| Header integrity | Kiểm tra response cuối sau CDN/proxy | Security header và Set-Cookie được bảo toàn |

Trong môi trường kiểm thử, dùng hai tài khoản và hai tenant riêng biệt; không dùng dữ liệu thật. Với cache poisoning và request smuggling, chỉ kiểm thử trong môi trường được phép và có khả năng quan sát cả edge lẫn backend.

## 17. Giám sát và điều tra

Ghi nhận đường đi request bằng correlation ID hoặc trace ID xuyên qua proxy, gateway và service. Các trường hữu ích gồm:

- Client IP đã xác minh, peer IP kết nối trực tiếp và chuỗi proxy tin cậy.
- Host/scheme sau khi canonicalize, route cuối cùng và upstream được chọn.
- Cache status: HIT, MISS, BYPASS, REVALIDATED hoặc trạng thái tương đương của nhà cung cấp.
- Cache key ở dạng đã loại bỏ bí mật; không log token, cookie hoặc dữ liệu nhạy cảm.
- Response status, Age, ETag, Cache-Control và Vary cuối cùng.
- Số lần retry, upstream attempt, timeout và lỗi parsing.
- Phiên bản cấu hình CDN/gateway/WAF và thời điểm thay đổi.

Theo dõi các dấu hiệu:

- Cache HIT cho endpoint vốn được phân loại là cá nhân hoặc nhạy cảm.
- Tỷ lệ cache hit tăng bất thường sau thay đổi rule.
- Nhiều request có Host hoặc Forwarded header không thuộc allowlist.
- Client IP suy ra khác thường so với peer IP hoặc thay đổi đột ngột.
- Response 304 tăng mạnh, đặc biệt ở endpoint có quyền thay đổi thường xuyên.
- Request bị edge chấp nhận nhưng backend từ chối theo cách lặp lại.
- Retry tăng, nhiều attempt cho cùng operation ID hoặc POST bị thực hiện lặp.
- Header bảo mật biến mất hoặc Cache-Control khác giữa origin và edge.

Log phải tránh chứa Authorization, cookie phiên, signed URL đầy đủ hoặc body nhạy cảm. Khi cần điều tra cache key, dùng fingerprint hoặc giá trị đã che. Giới hạn quyền truy cập log và thời gian lưu vì log của proxy thường có thể chứa URL, query string và metadata nhạy cảm.

Khi cấu hình CDN/proxy thay đổi, quản lý như thay đổi bảo mật: review, kiểm thử staging, rollout có kiểm soát, theo dõi metric và có phương án rollback. Một rule cache sai có thể làm rò rỉ dữ liệu ngay cả khi code application không thay đổi.

## 18. Các lỗi thiết kế thường gặp

1. **Cache mọi GET:** bỏ qua việc GET có thể trả dữ liệu cá nhân hoặc phụ thuộc tenant.
2. **Nhầm no-cache với no-store:** response vẫn có thể được lưu.
3. **Chỉ dựa vào Vary: Authorization:** biến header thành cache key không thay thế thiết kế phân quyền và cache scope.
4. **Tin X-Forwarded-For từ mọi nguồn:** cho phép giả mạo IP, né rate limit hoặc vượt allowlist.
5. **Backend truy cập trực tiếp được:** request có thể bỏ qua WAF, gateway và header sanitization.
6. **Host không được allowlist:** tạo redirect, reset link hoặc response poisoning qua Host header.
7. **Proxy và backend chuẩn hóa path khác nhau:** tạo bypass route hoặc authorization.
8. **Không kiểm tra quyền trước 304:** xác nhận lại response đã cache cho người đã mất quyền.
9. **Retry POST tự động:** tạo side effect hoặc giao dịch trùng.
10. **Chỉ mã hóa client-to-edge:** dữ liệu có thể đi rõ trên mạng nội bộ.
11. **Không kiểm thử header response cuối:** security header hoặc Cache-Control bị proxy ghi đè.
12. **Không purge khi đổi quyền/dữ liệu:** response cũ tiếp tục tồn tại sau khi chính sách thay đổi.

## 19. Quy trình rà soát cache và intermediary cho một API

Khi thiết kế hoặc thay đổi endpoint, thực hiện lần lượt:

1. Vẽ request path từ client qua CDN, proxy, gateway, WAF, load balancer đến service; vẽ cả đường response.
2. Xác định trust boundary, chủ sở hữu từng intermediary và header mà mỗi hop được phép tạo hoặc sửa.
3. Phân loại response là công khai, cá nhân, theo tenant hay nhạy cảm; xác định browser cache và shared cache có được phép lưu không.
4. Đặt Cache-Control, validator, Vary và cache key dựa trên các yếu tố thực sự ảnh hưởng response.
5. Kiểm tra Host, Forwarded header, path normalization và HTTP framing đồng nhất giữa các hop.
6. Quy định TLS termination và mã hóa/xác thực trên từng hop nội bộ.
7. Kiểm soát retry, timeout, buffering, body size và concurrency tại proxy lẫn application.
8. Xác định purge/invalidation khi dữ liệu hoặc quyền thay đổi.
9. Kiểm thử cross-user, cross-tenant, cache poisoning/deception, parser differential và direct-origin access.
10. Thiết lập log/metric an toàn, quản lý thay đổi cấu hình và diễn tập rollback.

## 20. Checklist rà soát

- [ ] Đã lập bản đồ tất cả CDN, proxy, gateway, WAF, load balancer, mesh và cache liên quan.
- [ ] Đã xác định trust boundary và nguồn đáng tin cho từng forwarding header.
- [ ] Host và scheme được canonicalize; redirect và URL tuyệt đối không phụ thuộc input tùy ý.
- [ ] Endpoint cá nhân/nhạy cảm có Cache-Control tường minh và không bị shared cache ghi đè.
- [ ] Cache key/Vary bao phủ mọi yếu tố ảnh hưởng representation; không dùng cache làm cơ chế phân quyền.
- [ ] Đã kiểm thử cross-user, cross-tenant, conditional request và invalidation khi thu hồi quyền.
- [ ] Proxy xóa header do client giả mạo và chỉ backend nhận traffic từ nguồn được phép.
- [ ] Parsing framing, path và header nhất quán giữa intermediary và origin.
- [ ] TLS và xác thực được đánh giá trên từng hop, gồm edge-to-origin.
- [ ] Retry có giới hạn và side effect được bảo vệ bằng idempotency.
- [ ] Security header, cookie và Cache-Control được kiểm tra ở response cuối.
- [ ] Log/metric không làm lộ token, cookie, signed URL hoặc dữ liệu cá nhân.

Cache và intermediary có thể cải thiện hiệu năng, khả năng sẵn sàng và khả năng bảo vệ ở biên. Chúng cũng trở thành một phần của ranh giới tin cậy và luồng dữ liệu. Khi cache scope, header forwarding, TLS, parsing và retry được thiết kế nhất quán với xác thực, phân quyền và nghiệp vụ của API, các lớp trung gian sẽ hỗ trợ bảo mật thay vì vô tình tạo ra đường vòng.

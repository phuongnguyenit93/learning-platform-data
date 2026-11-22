# Giới hạn kích thước header, cookie và hành vi của hạ tầng trung gian

## 1. Vì sao kích thước JWT có thể làm request thất bại?

JWT thường được gửi trong HTTP request bằng một trong hai cách:

- Header `Authorization`, thường có dạng `Bearer <token>`.
- Cookie, nếu ứng dụng chọn lưu credential trong cookie và gửi cookie theo quy tắc của trình duyệt.

JWT có thể hợp lệ về chữ ký, issuer, audience và thời hạn nhưng request vẫn bị từ chối trước khi tới logic xác minh token. Nguyên nhân có thể là header quá lớn, cookie vượt giới hạn lưu trữ của trình duyệt hoặc một thành phần trung gian không chấp nhận kích thước request headers.

Một request đi qua nhiều lớp: trình duyệt hoặc client, CDN, Web Application Firewall (WAF), load balancer, reverse proxy, API gateway, máy chủ HTTP và ứng dụng. Mỗi lớp có thể áp dụng giới hạn riêng cho:

- Tổng kích thước header của request.
- Kích thước một header field, ví dụ `Authorization` hoặc `Cookie`.
- Số lượng header fields.
- Kích thước header của response, trong đó có `Set-Cookie`.
- Request target/URL và body, vốn có giới hạn riêng.

**Giới hạn thực tế của một request là giới hạn chặt nhất trên toàn bộ đường đi.** Tăng giới hạn ở ứng dụng không giúp ích nếu CDN hoặc reverse proxy đã từ chối request trước đó.

Bài này tập trung vào kích thước HTTP header và cookie khi truyền JWT. Cần phân biệt chúng với **JOSE Protected Header** bên trong JWT: Protected Header là JSON được mã hóa Base64url thành một segment của token; `Authorization`, `Cookie` và `Set-Cookie` là các HTTP header fields mang token hoặc cookie qua mạng.

## 2. JWT được đặt trong HTTP header có kích thước ra sao?

Với JWS Compact, token có ba segment:

~~~text
base64url(protected-header).base64url(payload).base64url(signature)
~~~

Với JWE Compact, token có năm segment:

~~~text
base64url(protected-header).
base64url(encrypted-key).
base64url(iv).
base64url(ciphertext).
base64url(authentication-tag)
~~~

Các segment Base64url dùng ký tự ASCII. Base64url làm dữ liệu dài hơn so với byte ban đầu. Với một đầu vào có `N` byte, độ dài Base64url không padding xấp xỉ:

~~~text
encodedLength = ceil(4 * N / 3)
~~~

Vì vậy, payload có nhiều claim, mảng quyền dài, danh sách nhóm hoặc dữ liệu hồ sơ nhúng có thể làm token tăng nhanh. JWE thường còn có thêm segment quản lý khóa, IV và authentication tag; JWT lồng nhau có thể tăng kích thước đáng kể.

Khi đặt JWT vào header:

~~~http
Authorization: Bearer <jwt>
~~~

kích thước thực tế còn bao gồm tên field, dấu phân cách, tiền tố `Bearer ` và các header khác. Khi đặt vào cookie, còn có tên cookie, dấu bằng, các cookie khác và thuộc tính cookie ở response.

### Ví dụ cách tính sơ bộ

Giả sử JWT Compact có độ dài 3.200 ký tự ASCII. Giá trị của header `Authorization` là:

~~~text
Bearer <3200-character-token>
~~~

Độ dài giá trị header là 7 + 3.200 = 3.207 byte vì tiền tố `Bearer ` có 7 ký tự ASCII. Phần này chưa tính tên header, các field khác, framing HTTP/1.1 hoặc overhead được dùng trong cách tính header-list của HTTP/2 và HTTP/3.

Đây chỉ là phép tính cho riêng field Authorization. Một request còn có Cookie, User-Agent, Accept, tracing headers và nhiều field khác. Không nên lấy độ dài JWT làm tổng kích thước request headers.

## 3. HTTP có một giới hạn header chung cho mọi hệ thống không?

**Không có một con số tối đa duy nhất áp dụng cho mọi HTTP server, proxy và trình duyệt.** Các triển khai có thể đặt giới hạn khác nhau và còn có thể đặt nhiều giới hạn đồng thời.

Ví dụ, một hạ tầng có thể kiểm tra riêng:

| Loại giới hạn | Nội dung |
| --- | --- |
| Tổng header section | Tổng kích thước các header fields trong request |
| Một header field | Kích thước riêng của `Authorization`, `Cookie` hoặc field khác |
| Số lượng fields | Tổng số header fields được phép |
| Request target | Độ dài đường dẫn và query string |
| Response headers | Kích thước headers trả về, bao gồm `Set-Cookie` |
| Body | Kích thước nội dung request; đây là giới hạn khác với header |

Giới hạn có thể được cấu hình theo byte, không nhất thiết theo số ký tự hiển thị. Với ASCII, số byte thường bằng số ký tự; với dữ liệu Unicode hoặc encoding/escaping, số byte có thể lớn hơn số ký tự mà người dùng nhìn thấy.

### Các mã trạng thái thường gặp

| Mã HTTP | Ý nghĩa | Liên hệ với JWT/header |
| --- | --- | --- |
| **400 Bad Request** | Request không hợp lệ | Một số server/proxy dùng mã này khi header vượt giới hạn hoặc sai định dạng |
| **431 Request Header Fields Too Large** | Server từ chối vì header fields quá lớn | Mã trạng thái được định nghĩa cho trường hợp header quá lớn |
| **414 URI Too Long** | Request target/URI quá dài | Thường liên quan URL hoặc query string, không phải trực tiếp kích thước `Authorization` |
| **413 Content Too Large** | Nội dung request quá lớn | Liên quan body, không nên nhầm với header quá lớn |
| **502 Bad Gateway** | Gateway nhận phản hồi không hợp lệ từ upstream | Có thể xuất hiện trong một số lỗi proxy/upstream, nhưng không phải mã chuyên biệt cho JWT quá lớn |

RFC 6585 định nghĩa `431 Request Header Fields Too Large`. Tuy nhiên, không phải mọi thành phần đều trả 431. Một số triển khai có thể trả 400, đóng kết nối hoặc ghi lỗi riêng trong log. Vì vậy cần xem log tại từng hop thay vì kết luận chỉ dựa vào mã trạng thái phía client nhìn thấy.

### Request target và header là hai giới hạn khác nhau

Không nên chuyển JWT sang query string để tránh giới hạn header. URL có thể bị giới hạn riêng, thường dễ xuất hiện trong lịch sử trình duyệt, access log, analytics và header `Referer`. Bearer token trong URL còn làm tăng nguy cơ rò rỉ credential.

Nếu lỗi là 414, hãy kiểm tra request target. Nếu lỗi là 431 hoặc lỗi header-size ở proxy, hãy kiểm tra tổng header fields và các field lớn như Cookie/Authorization.

## 4. Giới hạn cookie của trình duyệt

Cookie có giới hạn lưu trữ riêng ở phía user agent. RFC 6265, mục 6.1, đưa ra các mức tối thiểu mà user agent được khuyến nghị hỗ trợ, bao gồm:

- Ít nhất **4.096 byte cho một cookie**, đo trên tổng độ dài tên, giá trị và thuộc tính cookie.
- Ít nhất **50 cookie cho mỗi domain**.
- Ít nhất **3.000 cookie tổng cộng**.

Đây là các mức hỗ trợ tối thiểu được RFC nêu, **không phải cam kết rằng mọi trình duyệt, phiên bản, nền tảng hoặc ngữ cảnh đều chấp nhận chính xác cùng một giới hạn**. Trình duyệt có thể áp dụng giới hạn khác, chính sách eviction và giới hạn tổng theo domain/site.

### 4 KB không phải ngân sách riêng cho JWT

Nếu một cookie chứa JWT dài gần 4 KB, phần tên cookie và thuộc tính như `Path`, `Domain`, `Secure`, `HttpOnly`, `SameSite`, `Expires` hoặc `Max-Age` cũng có thể được tính vào giới hạn lưu trữ cookie của user agent.

Ví dụ response:

~~~http
Set-Cookie: access_token=<jwt>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Giá trị JWT có thể nhỏ hơn 4.096 byte nhưng tổng cookie sau khi tính tên và thuộc tính vẫn có thể vượt giới hạn mà một trình duyệt áp dụng.

Đừng thiết kế cookie JWT sát ngưỡng 4 KB. Cần để khoảng dự phòng cho tên cookie, thuộc tính, thay đổi token, cookie khác và khác biệt giữa trình duyệt.

### Thuộc tính Set-Cookie không được gửi lại trong Cookie request

Khi server gửi:

~~~http
Set-Cookie: access_token=<jwt>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Trình duyệt lưu cookie theo thuộc tính và sau đó có thể gửi request header:

~~~http
Cookie: access_token=<jwt>
~~~

Các thuộc tính `Path`, `Secure`, `HttpOnly`, `SameSite`, `Expires` và `Max-Age` không được gửi lại như một phần của request `Cookie`. Chúng là metadata điều khiển cách trình duyệt lưu và gửi cookie. Tuy vậy, chúng có thể góp phần vào kích thước cookie mà trình duyệt đánh giá khi nhận `Set-Cookie`.

## 5. Cookie request có thể lớn hơn một cookie riêng lẻ

Một request thường gửi nhiều cookie phù hợp với domain, path và chính sách của trình duyệt:

~~~http
Cookie: session=<value>; access_token=<jwt>; preferences=<value>; csrf_token=<value>
~~~

Dù mỗi cookie riêng lẻ đều nằm trong giới hạn của trình duyệt, tổng giá trị `Cookie` vẫn có thể lớn. Các cookie khác do ứng dụng, analytics hoặc dịch vụ cùng domain đặt cũng góp vào request header.

Một số hệ quả:

- Một JWT cookie nhỏ có thể đi cùng nhiều cookie cũ và làm tổng header vượt giới hạn.
- Cookie được gửi tự động trên nhiều request phù hợp phạm vi domain/path, làm tăng băng thông cho cả endpoint không cần xác thực nếu phạm vi cookie quá rộng.
- Cookie trùng tên nhưng khác path hoặc domain có thể tạo ra nhiều cặp cùng tên trong request.
- Trình duyệt có thể từ chối lưu cookie mới hoặc xóa cookie cũ theo chính sách giới hạn/eviction.

### Xóa cookie cũ cần đúng phạm vi

Nếu đã thay đổi cookie name, path hoặc domain trong quá trình triển khai, cookie cũ có thể vẫn tồn tại. Để xóa, server thường gửi cookie cùng tên và phạm vi domain/path tương ứng với thời hạn hết hạn trong quá khứ hoặc `Max-Age=0`.

Không nên chỉ tạo cookie mới cùng tên rồi giả định cookie cũ đã biến mất. Cookie cùng tên nhưng path/domain khác nhau có thể cùng tồn tại và được gửi trong một request.

## 6. Hạ tầng trung gian có thể giới hạn header ở từng hop

Một request có thể đi qua nhiều thành phần trước khi đến ứng dụng:

~~~mermaid
flowchart LR
    A["Browser / Client"] --> B["CDN / WAF"]
    B --> C["Load Balancer"]
    C --> D["Reverse Proxy / Gateway"]
    D --> E["HTTP Server"]
    E --> F["Application"]
~~~

Mỗi thành phần có thể:

- Giới hạn tổng header size.
- Giới hạn kích thước riêng của một field.
- Giới hạn số field hoặc số cookie.
- Từ chối header không đúng cú pháp hoặc trùng lặp theo quy tắc riêng.
- Chuẩn hóa, gộp hoặc chuyển tiếp header theo giao thức.
- Có giới hạn riêng cho request headers và response headers.

Ví dụ, trình duyệt có thể gửi request thành công tới CDN, nhưng CDN từ chối trước khi request đến load balancer. Hoặc CDN chấp nhận nhưng reverse proxy phía sau từ chối. Khi đó ứng dụng không có access log cho request vì request chưa tới ứng dụng.

**Không thể suy ra giới hạn của toàn hệ thống chỉ từ cấu hình của một máy chủ.** Cần kiểm tra đường đi thực tế của request và response.

### Giới hạn response cũng quan trọng

JWT cookie thường được tạo qua response `Set-Cookie`. Nếu response header quá lớn, một proxy có thể từ chối response upstream hoặc trình duyệt có thể không lưu cookie. Request kế tiếp vì vậy không có cookie mong đợi và ứng dụng có thể rơi vào vòng lặp đăng nhập.

Cần đo cả:

- Kích thước request header khi client gửi JWT.
- Kích thước response header khi server đặt hoặc làm mới cookie.
- Kích thước tổng của response headers khi có nhiều `Set-Cookie` fields.

## 7. HTTP/2 và HTTP/3 nén header nhưng không loại bỏ giới hạn

HTTP/2 dùng HPACK và HTTP/3 dùng QPACK để nén header fields. Việc nén giúp giảm lượng dữ liệu truyền trên mạng, nhưng **không có nghĩa ứng dụng có thể gửi header không giới hạn**.

Bên nhận vẫn có thể đặt giới hạn kích thước header list/field section sau khi giải nén. Các giới hạn này được tính theo quy tắc giao thức và cấu hình của endpoint; kích thước dữ liệu nén trên dây không phải con số duy nhất cần quan tâm.

Trong HTTP/2, `SETTINGS_MAX_HEADER_LIST_SIZE` cho phép endpoint thông báo kích thước header list tối đa mà nó sẵn sàng nhận. Cách tính kích thước header list theo RFC 9113 bao gồm độ dài tên field, giá trị field và phần cộng thêm 32 byte cho mỗi field.

HTTP/3 có `SETTINGS_MAX_FIELD_SECTION_SIZE` với cách tính tương tự theo RFC 9114. Đây là giới hạn mà endpoint công bố; các triển khai cũng có thể áp dụng giới hạn nội bộ riêng.

Hệ quả thực tế:

- Một header có thể nén tốt nhưng vẫn vượt giới hạn logic sau giải nén.
- Header động hoặc cookie dài vẫn tiêu thụ bộ nhớ và tài nguyên xử lý.
- Thay đổi HTTP/1.1 sang HTTP/2 hoặc HTTP/3 không tự động giải quyết lỗi header quá lớn.
- Cần kiểm tra cấu hình và hành vi của từng hop, vì CDN, proxy và upstream có thể dùng giao thức khác nhau.

## 8. Cách tính và đo kích thước cần quan tâm

Khi chẩn đoán, cần đo ít nhất ba mức:

1. **JWT Compact string:** số byte của chính token.
2. **Header field chứa token:** ví dụ `Authorization` hoặc `Cookie`, tính cả tên field và giá trị.
3. **Tổng header section:** tất cả fields được gửi trong request.

### Công thức cho Authorization

Nếu token có `T` byte ASCII, giá trị Authorization dạng Bearer có độ dài:

~~~text
authorizationValueBytes = 7 + T
~~~

Theo cách tính header-list của HTTP/2 và HTTP/3, phần đóng góp của field này xấp xỉ:

~~~text
fieldContribution = nameBytes + valueBytes + 32
                  = 13 + (7 + T) + 32
                  = T + 52
~~~

Trong đó `authorization` có 13 byte ASCII. Công thức này dùng để hiểu quy tắc header-list của HTTP/2/3, không thay thế cách đo wire bytes của HTTP/1.1 hoặc giới hạn riêng của một proxy.

### Công thức cho Cookie

Giá trị Cookie có thể gồm nhiều cặp `name=value`, phân tách bằng `; `:

~~~text
cookieValue =
    name1=value1; name2=value2; name3=value3
~~~

Kích thước cần đo gồm tất cả tên, giá trị và dấu phân cách thực tế. Với HTTP/2/3, nếu Cookie được chia thành nhiều field lines theo quy tắc giao thức, cần đo header list theo cách endpoint tính sau khi xử lý các field đó.

### Không đo chỉ bằng số ký tự hiển thị trong DevTools

DevTools hữu ích để xem tên và giá trị header, nhưng việc đo chính xác nên dựa trên byte sau encoding và cách giao thức/hạ tầng tính kích thước. Một chuỗi Unicode có thể có số byte khác số ký tự. JWT Compact thường là ASCII, nhưng cookie hoặc header khác có thể được encode hoặc percent-encode.

## 9. Vì sao JWT lớn gây tác động ngoài lỗi 431?

Kích thước token ảnh hưởng đến cả tài nguyên và khả năng vận hành:

- **Băng thông:** token được gửi lại trên nhiều request, đặc biệt khi đặt trong cookie phạm vi rộng.
- **Độ trễ:** header lớn cần truyền và xử lý nhiều byte hơn.
- **Bộ nhớ:** proxy và server phải buffer hoặc parse header.
- **CPU:** token lớn làm tăng công việc Base64url decode, parse JSON và xác minh mật mã.
- **Khả năng tương thích:** một số client, CDN, WAF hoặc gateway có giới hạn thấp hơn môi trường phát triển.
- **Quan sát hệ thống:** log có thể bị cắt cụt hoặc từ chối ghi header dài.
- **Bề mặt DoS:** kẻ tấn công có thể gửi nhiều request với header lớn để tiêu thụ tài nguyên.

Đừng tăng giới hạn vô điều kiện. Giới hạn kích thước là một lớp bảo vệ tài nguyên và cần phù hợp với kích thước token tối đa được thiết kế.

## 10. Giảm kích thước JWT đúng cách

Cách bền vững nhất là giảm lượng dữ liệu cần mang trong token.

### Chỉ đưa claims cần thiết

- Chỉ giữ claim mà Resource Server thực sự cần để xác thực hoặc ra quyết định.
- Tránh nhúng hồ sơ người dùng, địa chỉ, danh sách đơn hàng hoặc dữ liệu nghiệp vụ lớn.
- Tránh đưa toàn bộ nhóm, role hoặc permission nếu danh sách có thể tăng không kiểm soát.
- Không lặp lại thông tin có thể xác định từ issuer, subject hoặc cấu hình phía server.

### Dùng token tham chiếu hoặc session phía server khi phù hợp

Nếu ứng dụng cần mang lượng trạng thái lớn, có thể cân nhắc opaque/reference token hoặc session identifier. Server tra cứu trạng thái trong kho dữ liệu và chỉ gửi một định danh ngắn qua mạng.

Đánh đổi cần xem xét:

| Cách tiếp cận | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| JWT tự chứa | Resource Server có thể kiểm tra claims mà không tra cứu trạng thái trung tâm trong mỗi request | Token có thể lớn; khó thu hồi tức thời nếu không có cơ chế bổ sung |
| Opaque/reference token | Credential gửi qua mạng thường ngắn; trạng thái có thể quản lý tập trung | Cần introspection hoặc tra cứu session, phụ thuộc vào dịch vụ trạng thái |
| Session cookie | Cookie có thể chỉ chứa session ID nhỏ | Cần lưu và quản lý session phía server |

Không nên chuyển toàn bộ claims lớn thành nhiều cookie nhỏ để né giới hạn. Cách này vẫn làm tăng tổng Cookie header, tăng số lượng cookie và tạo phức tạp khi cập nhật/xóa.

### Tránh nén như giải pháp mặc định

Nén có thể làm payload nhỏ hơn trong một số trường hợp, nhưng không phải giải pháp mặc định cho JWT header/cookie:

- JWS không định nghĩa cơ chế nén payload tổng quát cho mọi JWT profile.
- JWE có tham số `zip` trong một số profile, nhưng chỉ được dùng khi hai bên thống nhất và thư viện hỗ trợ đúng.
- Nén trước mã hóa có thể tạo rủi ro side-channel khi dữ liệu bí mật và dữ liệu do attacker kiểm soát cùng tham gia một luồng nén.
- Kích thước sau nén không loại bỏ giới hạn header/cookie ở mọi thành phần.
- Cần tính đến CPU, giải nén, giới hạn kích thước sau giải nén và nguy cơ dữ liệu phình lớn.

Hãy ưu tiên thiết kế token gọn thay vì dựa vào nén để vượt giới hạn hạ tầng.

## 11. Cookie bảo vệ JWT và các tác động liên quan

Nếu lưu JWT trong cookie, cần cân bằng kích thước với các thuộc tính bảo vệ:

~~~http
Set-Cookie: access_token=<jwt>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `Secure`: chỉ gửi cookie qua kênh HTTPS.
- `HttpOnly`: không cho JavaScript phía trình duyệt đọc cookie qua API cookie thông thường.
- `SameSite`: kiểm soát một phần việc gửi cookie trong ngữ cảnh cross-site; giá trị phù hợp phụ thuộc luồng đăng nhập và kiến trúc.
- `Path` và `Domain`: giới hạn phạm vi gửi cookie; nên tránh phạm vi rộng không cần thiết.
- `Max-Age` hoặc `Expires`: xác định thời gian lưu cookie.

Cookie được trình duyệt tự động đính kèm theo quy tắc domain/path/SameSite, vì vậy ứng dụng dùng cookie để xác thực cần đánh giá CSRF và triển khai biện pháp phù hợp. `HttpOnly` giảm khả năng JavaScript đọc token, nhưng không tự ngăn request giả mạo được trình duyệt gửi kèm cookie.

Các thuộc tính bảo mật không làm JWT nhỏ đi đáng kể và một số thuộc tính còn góp vào kích thước cookie được lưu. Không nên bỏ `Secure`, `HttpOnly` hoặc `SameSite` chỉ để tiết kiệm vài byte.

### Giữ cookie trong phạm vi cần thiết

Cookie có `Path=/` thường được gửi đến nhiều endpoint trên host. Nếu token chỉ cần cho một phạm vi hẹp, hãy xem xét path phù hợp và host-only cookie khi có thể. Cookie domain rộng có thể được gửi đến nhiều subdomain phù hợp; không dùng cookie domain rộng nếu không cần.

Không xem `Path` là ranh giới bảo mật mạnh giữa các ứng dụng cùng host. Phạm vi cookie giúp giảm gửi thừa, nhưng việc phân tách ứng dụng và bảo vệ credential vẫn cần thiết kế phù hợp.

## 12. Chẩn đoán lỗi header/cookie quá lớn

Khi client gặp lỗi sau khi đăng nhập hoặc gọi API, hãy xác định lỗi xảy ra ở đâu.

~~~mermaid
flowchart TD
    A["Request có JWT thất bại"] --> B{"Client có gửi token không?"}
    B -- "Không" --> C["Kiểm tra cookie bị từ chối, hết hạn hoặc sai domain/path"]
    B -- "Có" --> D{"Có lỗi 431/400 hoặc header-size ở hop nào?"}
    D -- "Có" --> E["Đo Authorization, Cookie và tổng header"]
    D -- "Không" --> F["Kiểm tra xác minh JWT và lỗi ứng dụng"]
    E --> G["Xác định CDN/WAF/LB/proxy/server từ log"]
    G --> H["So sánh giới hạn từng hop"]
    H --> I["Giảm token/cookie hoặc điều chỉnh giới hạn có kiểm soát"]
    C --> J["Xóa cookie cũ đúng domain/path và thử lại"]
    I --> K["Kiểm thử lại toàn bộ đường đi"]
    J --> K
~~~

### Các dấu hiệu thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| Đăng nhập thành công nhưng request kế tiếp không có cookie | Trình duyệt không lưu `Set-Cookie` do cookie quá lớn hoặc bị chính sách từ chối | Kiểm tra response headers và cookie storage của trình duyệt |
| Request trả 431 | Tổng header fields hoặc một field vượt giới hạn | Kiểm tra log của CDN/proxy/server và đo byte |
| Request trả 400 chỉ ở một môi trường | Giới hạn hạ tầng khác nhau giữa môi trường | So sánh cấu hình và đường đi request |
| Chỉ một số người dùng gặp lỗi | Người dùng có nhiều cookie cũ hoặc token có claims lớn hơn | Đo tổng Cookie header, kiểm tra cookie trùng tên/path |
| Chỉ lỗi khi gọi qua CDN/WAF | Thành phần trung gian có giới hạn riêng | So sánh log tại CDN/WAF với upstream |
| Redirect đăng nhập lặp lại | Cookie không được lưu hoặc không được gửi lại | Kiểm tra Set-Cookie, domain/path, SameSite và kích thước |
| 414 | URL/request target quá dài | Kiểm tra query string và đường dẫn; không nhầm với header |

Không ghi toàn bộ JWT hoặc Cookie header vào log chỉ để đo kích thước. Có thể ghi số byte, tên field, hop, mã lỗi, route, phiên bản token profile và `kid` nếu phù hợp. Giá trị token là bearer credential và phải được che khỏi log, tracing và hệ thống phân tích.

## 13. Kế hoạch kiểm thử giới hạn trên toàn đường đi

Kiểm thử cần chạy qua đúng browser/client, CDN, WAF, load balancer, proxy và server sẽ dùng ở production.

| Ca kiểm thử | Điều cần quan sát |
| --- | --- |
| Token nhỏ, một cookie | Baseline request thành công |
| Token gần giới hạn dự kiến | Xác định biên thực tế và khoảng dự phòng |
| Token lớn hơn giới hạn dự kiến | Thành phần nào từ chối và mã lỗi gì |
| Nhiều cookie hợp lệ cộng lại | Tổng Cookie header có vượt giới hạn không |
| Cookie cũ cùng tên nhưng path khác | Trình duyệt gửi những cặp nào |
| Response có nhiều Set-Cookie | Server/proxy/browser có chấp nhận đầy đủ không |
| HTTP/1.1 so với HTTP/2 hoặc HTTP/3 | Khác biệt cấu hình và header-list limit |
| Gọi trực tiếp upstream so với qua CDN | Xác định hop gây lỗi |
| Nhiều request đồng thời với header lớn | CPU, bộ nhớ và khả năng chống DoS |
| Token sau rotation hoặc thay đổi claims | Kích thước có tăng vượt ngân sách không |

Nên kiểm thử cả trường hợp bình thường và biên. Đặt giới hạn tối đa cho JWT ở client, gateway và verifier theo cùng profile; để một khoảng dự phòng cho các header khác và cookie mà hệ thống có thể thêm trong tương lai.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đo kích thước JWT | Bỏ qua prefix, tên field và các header khác | Đo field chứa token và tổng header section |
| Cho rằng HTTP có giới hạn header chung | Cấu hình sai kỳ vọng giữa các môi trường | Xác định giới hạn từng thành phần và giao thức |
| Cho rằng HTTP/2/3 nén nên không có giới hạn | Header vẫn có thể vượt giới hạn sau giải nén | Kiểm tra header-list/field-section size |
| Đưa toàn bộ hồ sơ và quyền vào JWT | Token lớn, request tốn băng thông | Giữ claims tối thiểu hoặc dùng reference token |
| Đặt JWT sát ngưỡng cookie 4 KB | Trình duyệt có thể từ chối lưu cookie | Chừa khoảng dự phòng và kiểm tra browser thực tế |
| Chỉ kiểm tra từng cookie, bỏ qua tổng Cookie header | Nhiều cookie nhỏ vẫn làm request quá lớn | Đo tổng Cookie header |
| Tăng giới hạn ở ứng dụng nhưng quên proxy | Request vẫn bị từ chối trước khi đến ứng dụng | Kiểm tra tất cả hop |
| Dùng query string để né giới hạn header | Rò rỉ token qua URL, log và Referer | Dùng header/cookie theo profile an toàn |
| Tách JWT thành nhiều cookie | Tổng header và quản lý cookie phức tạp hơn | Giảm claims hoặc dùng session/reference token |
| Bỏ thuộc tính cookie bảo mật để giảm byte | Tăng rủi ro đánh cắp hoặc CSRF | Giữ thuộc tính phù hợp và tối ưu thiết kế |
| Log nguyên Authorization/Cookie | Bearer credential có thể bị lộ | Redact giá trị; chỉ ghi kích thước và metadata an toàn |

## 15. Checklist thiết kế và vận hành

- Xác định JWT được gửi qua Authorization header hay cookie.
- Đặt ngân sách kích thước tối đa cho token theo profile.
- Đo byte của token, field chứa token và tổng request header.
- Kiểm tra giới hạn cookie của các trình duyệt mục tiêu; không coi 4 KB là ngân sách dành riêng cho JWT.
- Tính cả cookie khác, tên cookie và thuộc tính khi kiểm tra giới hạn lưu trữ.
- Kiểm tra giới hạn request/response header tại CDN, WAF, load balancer, proxy, gateway và HTTP server.
- Kiểm thử HTTP/1.1, HTTP/2 và HTTP/3 nếu hệ thống hỗ trợ.
- Chừa khoảng dự phòng; không vận hành sát ngưỡng.
- Giữ JWT gọn, tránh dữ liệu hồ sơ và danh sách quyền lớn.
- Cân nhắc opaque/reference token hoặc session phía server nếu trạng thái lớn.
- Không chuyển bearer token sang URL/query string.
- Giữ thuộc tính cookie bảo mật phù hợp; đánh giá CSRF nếu browser tự gửi cookie xác thực.
- Giới hạn kích thước header ở server để bảo vệ tài nguyên và chống DoS.
- Redact Authorization, Cookie, Set-Cookie và assertion khỏi log/tracing.
- Theo dõi lỗi 431, 400, lỗi cookie storage và kích thước header theo môi trường.
- Kiểm thử lại toàn bộ đường đi sau khi thay đổi claims, token profile, cookie hoặc cấu hình hạ tầng.

**Ghi nhớ:** JWT hợp lệ vẫn có thể bị chặn vì HTTP header hoặc cookie quá lớn. Trình duyệt có giới hạn cookie riêng; hạ tầng HTTP có thể giới hạn từng field và tổng header section. HTTP/2/3 nén header nhưng vẫn áp dụng giới hạn sau giải nén. Hãy đo kích thước ở từng lớp, kiểm thử toàn bộ đường đi và giữ token nhỏ bằng cách chỉ mang claims cần thiết. Khi cần lưu trạng thái lớn, hãy cân nhắc reference token hoặc session phía server thay vì tăng kích thước cookie/header vô hạn.

### Tài liệu chuẩn để tra cứu

- **RFC 6265 — HTTP State Management Mechanism:** cookie, `Set-Cookie`, `Cookie` và giới hạn lưu trữ tối thiểu của user agent.
- **RFC 6585 — Additional HTTP Status Codes:** `431 Request Header Fields Too Large`.
- **RFC 9110 — HTTP Semantics:** HTTP fields, request target và các status code liên quan.
- **RFC 9113 — HTTP/2:** header compression và `SETTINGS_MAX_HEADER_LIST_SIZE`.
- **RFC 9114 — HTTP/3:** field section size và `SETTINGS_MAX_FIELD_SECTION_SIZE`.
- **RFC 7519 — JSON Web Token (JWT):** JWT Compact Serialization và claims.
- **RFC 8725 — JSON Web Token Best Current Practices:** thực hành an toàn khi phát hành và xử lý JWT.

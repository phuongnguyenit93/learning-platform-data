# Reverse proxy và ranh giới tin cậy của Forwarded, X-Forwarded-*

## 1. Mục tiêu và vấn đề thực tế

Trong hệ thống web thực tế, HTTP request thường không đi thẳng từ trình duyệt đến ứng dụng Spring Boot. Nó có thể qua CDN, WAF, load balancer, API gateway hoặc reverse proxy trước khi tới Tomcat và Spring Security.

Ví dụ, trình duyệt gửi yêu cầu **HTTPS đến shop.example.test**, nhưng reverse proxy kết thúc TLS rồi chuyển tiếp bằng **HTTP đến ứng dụng nội bộ** tại cổng 8080. Nhìn từ kết nối trực tiếp của ứng dụng, request có thể mang scheme **http**, host nội bộ và địa chỉ IP của proxy. Trong khi đó, người dùng thật đang truy cập bằng **https** ở host công khai.

Các header **Forwarded** và **X-Forwarded-*** được dùng để chuyển tiếp thông tin về request ở phía client, ví dụ địa chỉ IP ban đầu, protocol, host và port. Vấn đề bảo mật quan trọng là: **header HTTP tự nó không chứng minh thông tin bên trong đáng tin**. Nếu ứng dụng tin các giá trị do client tùy ý gửi, nó có thể xác định sai địa chỉ người dùng, sinh redirect đến domain độc hại hoặc đưa ra quyết định bảo mật trên dữ liệu giả.

Sau bài này, bạn có thể:

1. Giải thích reverse proxy thay đổi những thuộc tính nào của HTTP request.
2. Phân biệt header chuẩn **Forwarded (RFC 7239)** với nhóm **X-Forwarded-***.
3. Đọc một chuỗi proxy nhiều hop mà không nhầm địa chỉ kết nối trực tiếp với client IP.
4. Xác định **trust boundary**: ai được quyền đưa forwarded headers, ai phải xóa dữ liệu bên ngoài.
5. Hiểu tác động lên URL/redirect, Secure cookie, OAuth2 redirect, logging, rate limiting và các quyết định trong Spring Security.
6. Cấu hình **server.forward-headers-strategy** phù hợp cho ứng dụng Spring Boot MVC/Servlet.
7. Kiểm thử luồng proxy thật, request giả mạo và đường truy cập trực tiếp đến backend.

## 2. Reverse proxy làm gì với HTTP request?

**Reverse proxy** là server đứng phía trước ứng dụng, nhận request thay cho backend và chuyển request tới một hoặc nhiều dịch vụ nội bộ. Nó thường được dùng để:

- Kết thúc TLS/HTTPS và quản lý chứng chỉ.
- Định tuyến nhiều domain hoặc đường dẫn đến các service.
- Cân bằng tải, health check, caching và giới hạn lưu lượng.
- Thực hiện một phần kiểm soát như WAF, IP filtering hoặc authentication gateway.
- Ẩn địa chỉ mạng của backend khỏi người dùng Internet.

Một topology đơn giản:

~~~text
Browser                    Reverse proxy                 Spring Boot
198.51.100.24              192.0.2.10                   10.0.0.20:8080
     |                          |                               |
     | GET https://shop.example.test/profile                      |
     |---------- TLS ---------->|                               |
     |                          | GET http://10.0.0.20:8080/profile
     |                          |------------------------------>|
     |                          |  Host: backend.internal       |
     |                          |  X-Forwarded-Proto: https    |
     |                          |  X-Forwarded-Host: shop.example.test
     |                          |  X-Forwarded-For: 198.51.100.24
     |                          |                               |
     |<--------------------- HTTP response qua proxy ------------|
~~~

Các địa chỉ IP trong sơ đồ dùng dải dành cho tài liệu minh họa. Tên domain **shop.example.test** cũng là tên minh họa.

Nếu không xử lý forwarded headers, các API của Servlet thường phản ánh kết nối **proxy → backend**:

| Thuộc tính Servlet | Có thể thấy ở backend | Góc nhìn của trình duyệt |
| --- | --- | --- |
| request.getScheme() | http | https |
| request.isSecure() | false | true ở kết nối browser → proxy |
| request.getServerName() | backend.internal | shop.example.test |
| request.getServerPort() | 8080 | 443 |
| request.getRemoteAddr() | IP reverse proxy | IP client mà proxy đã quan sát |
| request.getRequestURL() | URL theo kết nối vào backend | URL ngoài Internet |

Giá trị thực tế tùy cách proxy ghi lại **Host**, cách connector/server được cấu hình và liệu Spring đã diễn giải forwarded headers hay chưa. Bảng mô tả lý do cần có cơ chế này, không phải lời cam kết mọi môi trường đều trả đúng các giá trị trên.

### 2.1. Ba địa chỉ dễ bị nhầm

- **Peer/socket IP:** Địa chỉ IP của bên đang kết nối TCP trực tiếp với backend. Đằng sau reverse proxy, đó thường là địa chỉ proxy cuối cùng.
- **Forwarded client IP:** Địa chỉ được proxy khai báo là bên gửi yêu cầu vào nó hoặc vào chuỗi proxy. Đây là **thông tin được khai báo**, cần xác minh nguồn.
- **Danh tính người dùng:** Principal sau authentication, ví dụ một tài khoản hoặc chủ thể trong access token. IP không thay thế danh tính này; nhiều user có thể dùng chung NAT, VPN hoặc mạng doanh nghiệp.

Không thể suy ra “người dùng đã xác thực” chỉ vì một IP hoặc X-Forwarded-For trông quen thuộc.

## 3. Hai họ header chính

### 3.1. Header chuẩn Forwarded theo RFC 7239

**Forwarded** là header được chuẩn hóa trong **RFC 7239**. Mỗi phần tử chứa những cặp **tên=giá trị**, ngăn cách nhau bởi dấu chấm phẩy; nhiều hop có thể biểu diễn bằng các phần tử cách nhau bằng dấu phẩy.

~~~http
Forwarded: for=198.51.100.24;proto=https;host=shop.example.test
~~~

Các tham số quan trọng:

| Tham số | Ý nghĩa |
| --- | --- |
| for | Node gửi request **tới proxy đang ghi thông tin**; thường dùng để mô tả client/hop trước đó |
| by | Giao diện phía nhận request của proxy, có thể là identifier đã được làm mờ |
| host | Host mà proxy nhận được từ request vào |
| proto | Scheme/protocol mà proxy thấy ở phía request vào, thường http hoặc https |

Nếu nhiều proxy cùng bổ sung header, có thể thấy:

~~~http
Forwarded: for=198.51.100.24;proto=https;host=shop.example.test, for=192.0.2.10;proto=http
~~~

Ví dụ này mô tả một phần tử về request ở edge và một phần tử tại hop tiếp theo. **proto=http** ở hop nội bộ không phủ nhận trình duyệt đã dùng HTTPS ở hop ngoài cùng. Muốn hiểu chính xác phải biết từng proxy có ghi hoặc bảo toàn header như thế nào.

RFC cho phép **for=unknown**, identifier được làm mờ và địa chỉ IPv6 trong dấu ngoặc kép, ví dụ:

~~~http
Forwarded: for="[2001:db8::42]";proto=https;host=shop.example.test
~~~

Không thể xử lý đúng RFC 7239 bằng cách lấy một chuỗi tùy tiện rồi cắt trước dấu hai chấm: IPv6 có nhiều dấu hai chấm, và giá trị quoted-string còn có quy tắc riêng. Trong ứng dụng thực tế hãy dùng thành phần đã hỗ trợ chuẩn và được cấu hình đúng.

### 3.2. Nhóm X-Forwarded-* phổ biến

**X-Forwarded-*** là cách làm xuất hiện trước khi RFC 7239 ra đời và vẫn rất phổ biến. Đây là nhiều header độc lập, không có một đặc tả RFC duy nhất áp dụng thống nhất cho mọi biến thể.

| Header | Nội dung thường mang | Cần kiểm tra |
| --- | --- | --- |
| X-Forwarded-For | Danh sách địa chỉ client/hop, thường cách nhau bằng dấu phẩy | Các mục trước trust boundary có thể do client tự gửi |
| X-Forwarded-Proto | Scheme mà client dùng ở phía ngoài, ví dụ https | Dễ bị giả nếu proxy không ghi đè hoặc backend nhận trực tiếp |
| X-Forwarded-Host | Host của request ở phía ngoài | Host có thể bị giả; cần canonical host/allowlist |
| X-Forwarded-Port | Port bên ngoài, ví dụ 443 | Chỉ đúng khi nguồn tin cậy |
| X-Forwarded-Prefix | Prefix công khai khi proxy đổi đường dẫn | Không phải mọi server/phiên bản xử lý giống nhau |
| X-Real-IP | Một header riêng do một số proxy cung cấp | Không phải header chuẩn chung; cũng phải qua trust boundary |

Ví dụ:

~~~http
X-Forwarded-For: 198.51.100.24, 192.0.2.10
X-Forwarded-Proto: https
X-Forwarded-Host: shop.example.test
X-Forwarded-Port: 443
~~~

Đây là **lời khai** của các hệ thống trung gian, không phải bằng chứng mã hóa rằng client thực sự có IP 198.51.100.24 hoặc đã truy cập bằng HTTPS. Trình duyệt và HTTP client có thể tự đặt nhiều header này trước khi gửi request, trừ khi có thành phần mạng đáng tin ngăn chặn hoặc viết lại chúng.

### 3.3. Forwarded và X-Forwarded-* có tương đương hoàn toàn?

Không. Forwarded nhóm các tham số theo từng phần tử/hop; X-Forwarded-* tách chúng thành nhiều header, khiến việc khớp cùng hop giữa các thuộc tính có thể khó hoặc mơ hồ. Các proxy và framework cũng khác nhau trong hỗ trợ, ưu tiên và cách diễn giải.

**Quy tắc vận hành:** Chọn **một hợp đồng forwarded headers rõ ràng** giữa các proxy và backend. Ở ranh giới tin cậy, xóa cả header chuẩn lẫn các header X-Forwarded từ nguồn ngoài, sau đó chỉ phát hành họ header mà hệ thống nội bộ thực sự dùng. Không dựa vào một quy tắc ưu tiên bất thành văn khi có hai bộ header mâu thuẫn.

## 4. Trust boundary nằm ở đâu?

**Ranh giới tin cậy (trust boundary)** là vị trí thông tin chuyển từ môi trường không kiểm soát được sang môi trường có quy tắc và cơ chế xác thực rõ ràng. Với forwarded headers, ranh giới điển hình là **edge proxy hoặc load balancer được quản trị**.

~~~text
BÊN NGOÀI KHÔNG TIN CẬY       RANH GIỚI TIN CẬY         BÊN TRONG ĐƯỢC QUẢN LÝ
Client / Internet           Edge proxy                  App / private services
      |                         |                              |
      | Forwarded: for=fake     |                              |
      | X-Forwarded-Host: evil  |                              |
      |------------------------>|                              |
      |                         | 1. Xóa forwarded từ bên ngoài|
      |                         | 2. Xác định peer, TLS, host  |
      |                         | 3. Tạo header đã được chọn   |
      |                         |----------------------------->|
      |                         |       Chỉ app từ đây mới      |
      |                         |       diễn giải header       |
~~~

**Một header không tự trở thành đáng tin khi nó đi qua proxy.** Nếu edge proxy chỉ chuyển tiếp nguyên văn header do client cung cấp, backend vẫn nhận thông tin do client tự khai. Edge phải **xóa, ghi đè hoặc chuẩn hóa** đúng chính sách; các proxy nội bộ phải biết nguồn upstream nào đáng tin.

### 4.1. Bốn điều kiện để dùng forwarded headers an toàn

1. **Có nguồn đáng tin:** Backend chỉ nhận traffic từ các reverse proxy thực sự được phép. Chặn đường Internet hoặc network nội bộ không được phép truy cập backend trực tiếp.
2. **Xóa header từ client ở edge:** Bao gồm **Forwarded** và toàn bộ các header **X-Forwarded-*** mà ứng dụng/stack có thể hiểu. Chỉ phát hành thông tin do proxy xác định.
3. **Định nghĩa thứ tự và hop được tin:** Với nhiều proxy, biết chính xác proxy nào thêm, ghi đè hoặc giữ nguyên từng header. Cấu hình trust list/CIDR đúng; không mở rộng vô hạn cho mọi IP.
4. **Bảo vệ kết nối trong vùng tin cậy:** Kiểm soát mạng giữa proxy và backend; dùng TLS/mTLS khi rủi ro yêu cầu. Một proxy đáng tin không bảo vệ được header nếu đường truyền nội bộ bị sửa bởi bên không có quyền.

Không có những điều kiện này thì bật chế độ đọc Forwarded trong Spring Boot **có thể làm ứng dụng dễ bị header spoofing**.

### 4.2. Tại sao phải xóa cả hai họ header?

Giả sử edge chỉ xóa X-Forwarded-For nhưng vẫn cho client gửi:

~~~http
Forwarded: for=203.0.113.250;proto=https;host=attacker.example.test
~~~

Một bộ phận trong stack có thể đọc header **Forwarded**, trong khi hệ thống log hoặc proxy khác lại đọc **X-Forwarded-***. Nếu mỗi thành phần diễn giải một nguồn khác nhau, chúng có thể bất đồng về **client IP, scheme, host**. Vì vậy cần strip/reset cả hai họ ở **điểm nhận traffic không tin cậy**, sau đó chỉ chọn giá trị đã kiểm chứng.

### 4.3. Ranh giới nằm ở mạng, không chỉ ở Java

Đoạn code kiểm tra một header trông hợp lệ không chứng minh request đã thực sự đi qua proxy. Một kẻ có quyền gửi request trực tiếp tới backend có thể tự đặt header giống hệt proxy.

Chính sách sản xuất thường cần kết hợp:

- Firewall/security group/network policy chặn kết nối trực tiếp không được phép đến cổng backend.
- Proxy nhận từ Internet và loại bỏ thông tin do client tự khai.
- Các hop nội bộ chỉ nhận upstream được ủy quyền; có thể dùng TLS/mTLS phù hợp.
- Spring Boot chỉ bật chiến lược đọc header sau khi đã xác minh các điều kiện trên.
- Quyền truy cập API vẫn dựa trên authentication và authorization, không chỉ dựa trên IP forwarded.

## 5. Đọc chuỗi X-Forwarded-For nhiều proxy đúng cách

Xét ba bên sau:

~~~text
Client 198.51.100.24
    |
    v
Edge proxy 192.0.2.10
    |
    v
Internal proxy 10.0.0.10
    |
    v
Application 10.0.0.20:8080
~~~

Nếu **edge đã xóa X-Forwarded-For từ client** và ghi lại địa chỉ nó quan sát, sau đó proxy nội bộ append địa chỉ peer mà nó quan sát, app có thể nhận:

~~~http
X-Forwarded-For: 198.51.100.24, 192.0.2.10
~~~

Đồng thời socket peer ở app là **10.0.0.10**. Theo quy ước thông dụng, danh sách X-Forwarded-For từ trái sang phải là các địa chỉ được ghi qua những hop trước. Tuy nhiên, **địa chỉ bên trái nhất không mặc nhiên là IP client thật**, vì:

- Client có thể đã tự gửi giá trị ở đầu danh sách.
- Một proxy có thể append mà không xóa phần do client cung cấp.
- Một hoặc nhiều proxy có thể không ghi header, hoặc dùng header khác.
- Có NAT, CDN, VPN, các cơ chế ẩn địa chỉ và địa chỉ không đủ xác minh danh tính.

### 5.1. Ví dụ spoof nếu edge chỉ append

Client cố ý gửi:

~~~http
X-Forwarded-For: 203.0.113.99
~~~

Nếu edge dùng cơ chế append mà không làm sạch trước, header cuối có thể thành:

~~~http
X-Forwarded-For: 203.0.113.99, 198.51.100.24, 192.0.2.10
~~~

Trong topology này, **203.0.113.99** là giá trị do client tự nhập, không có bằng chứng là địa chỉ của người gọi. Một ứng dụng lấy phần tử **đầu tiên** làm IP thật sẽ bị lừa.

### 5.2. Quy tắc phân tích khi phải xử lý nhiều hop

Bắt đầu từ **peer TCP trực tiếp** mà backend thực sự nhìn thấy, sau đó dựa vào danh sách proxy tin cậy **được xác định bằng cấu hình ngoài request**:

1. Xác nhận peer trực tiếp là proxy được phép kết nối vào backend. Nếu không, không tin các forwarded headers của request đó.
2. Biết proxy gần app đã kiểm tra hoặc bảo toàn header theo hợp đồng nào.
3. Nếu phải duyệt chuỗi IP, đánh giá từ **phía gần app (bên phải)** về phía client, chỉ đi qua những hop thực sự được tin và đã được cấu hình chính xác.
4. Khi gặp một hop không tin cậy, không xem các mục nằm sâu hơn ở phía client là bằng chứng đáng tin.
5. Nếu không thể chứng minh chuỗi, dùng IP peer đã quan sát hoặc đánh dấu client IP là không xác định; đừng đoán.

Đây là **nguyên tắc thiết kế**, không phải hướng dẫn tự viết parser từ split(",") để triển khai bảo mật production. Cấu hình tin cậy của Tomcat, ingress hoặc gateway cần được thử nghiệm theo đúng topology.

### 5.3. Nếu phía trước còn CDN thì sao?

Khi CDN nằm trước edge, kết nối TCP mà edge quan sát thường đến từ **IP của CDN**, không phải IP người dùng cuối. Việc lấy trực tiếp remote_addr từ socket ở edge khi đó có thể chỉ lưu IP CDN.

Muốn khôi phục client IP phải tuân theo **cơ chế trusted proxy của CDN và ingress**: chỉ nhận dữ liệu từ danh sách IP upstream đã được phép, xác minh header đặc thù của CDN theo tài liệu nhà cung cấp, làm sạch thông tin từ request ngoài và cập nhật danh sách CIDR khi cần. Không chọn một header “client IP” chỉ vì giá trị của nó có vẻ giống IP thật.

## 6. X-Forwarded-Proto, Host, Port, Prefix và hệ quả bảo mật

### 6.1. Protocol/scheme và Secure cookie

Khi trình duyệt truy cập HTTPS tới proxy nhưng proxy nói chuyện HTTP với backend, request.getScheme() ở backend có thể là **http** nếu ứng dụng không biết HTTPS ở bên ngoài.

Từ đó phát sinh các vấn đề:

- Tạo absolute link hoặc redirect từ backend có thể thành http:// thay vì https://.
- Một số logic dựng URL callback có thể dùng sai scheme.
- Mã ứng dụng dựa trên request.isSecure() có thể đưa ra quyết định sai.
- Các chính sách cookie cần **Secure** phải được cấu hình rõ ràng theo TLS ở browser và nguyên tắc triển khai. Không suy ra chắc chắn mọi cookie sẽ tự có thuộc tính Secure chỉ vì có X-Forwarded-Proto.

Nếu ứng dụng mù quáng tin **X-Forwarded-Proto: https** của client trực tiếp, request.isSecure() lại có thể cho **true** dù kết nối từ client tới backend không có TLS. Do đó **header không chứng minh đã có TLS**; TLS phải được kiểm soát tại edge và trong topology đúng.

### 6.2. Host và tấn công host header poisoning

Một hệ thống có thể tạo URL tuyệt đối cho redirect, link xác thực email, reset password, hoặc callback OAuth2. Nếu ứng dụng dùng **X-Forwarded-Host** giả làm hostname công khai, có nguy cơ sinh URL đến domain do kẻ tấn công chỉ định.

Ví dụ request giả:

~~~http
X-Forwarded-Host: attacker.example.test
X-Forwarded-Proto: https
~~~

Nếu server tạo link nhạy cảm bằng giá trị này mà không kiểm tra nguồn và canonical host, link có thể bị đưa sang domain không mong muốn. Cần:

- Chỉ chấp nhận **hostname công khai đã định nghĩa hoặc allowlist rõ ràng**.
- Edge proxy từ chối host không thuộc virtual host hợp lệ.
- Không cho client bên ngoài đặt X-Forwarded-Host có ảnh hưởng đến backend.
- Với link bảo mật quan trọng, ưu tiên **base URL được cấu hình cố định** hoặc được chọn từ một tập domain hợp lệ.
- Không xây OAuth2 redirect URI hay đường dẫn reset password dựa trên host không tin cậy.

### 6.3. X-Forwarded-Prefix

Proxy có thể nhận **https://shop.example.test/api/orders** rồi chuyển tới backend **/orders**. Khi đó có thể dùng X-Forwarded-Prefix để thông báo prefix **/api** của URL công khai.

Tuy nhiên, không phải mọi container, Spring Framework version hoặc chiến lược forwarded headers đều xử lý prefix giống nhau. Cần xác minh cụ thể cách **context path, redirect, absolute URL và resource URL** được dựng trong ứng dụng; không dùng prefix từ client như bằng chứng về routing thật.

### 6.4. Authentication và Spring Security chịu ảnh hưởng gì?

- **Authorization theo URL:** Bộ lọc bảo mật kiểm tra request trong bối cảnh đường dẫn mà ứng dụng quan sát. Rewrite path ở proxy có thể làm matcher khác URL công khai; cần kiểm thử path sau rewrite và prefix.
- **OAuth2/OIDC login:** Redirect URI và callback phải khớp cấu hình cho phép ở authorization server. Scheme/host/port sai có thể khiến login thất bại; host giả có thể tạo rủi ro redirect.
- **SecurityContext và session:** Cookie và session cần nhất quán với domain, scheme, path, TLS termination và chính sách cookie.
- **IP-based controls:** Audit, rate limit, allowlist và fraud rules có thể sai nếu dùng một XFF giả.
- **CSRF/CORS:** Origin, host, scheme và browser behavior cần được xét thống nhất. CORS không xác minh IP; forwarded headers không thay thế CSRF protection.
- **Redirects:** Link tuyệt đối và phản hồi Location phải không chứa hostname nội bộ hoặc domain do client tùy ý đưa vào.

## 7. Cấu hình Spring Boot 3.x sau reverse proxy

Với Spring Boot 3.x, thuộc tính quan trọng là **server.forward-headers-strategy**:

| Giá trị | Ý nghĩa | Dùng khi nào |
| --- | --- | --- |
| none | Không yêu cầu Boot áp dụng chiến lược forwarded headers riêng; mặc định cụ thể còn phụ thuộc nền tảng | Khi chưa có proxy đáng tin hoặc không cần diễn giải forwarded headers |
| native | Dùng cơ chế native của embedded web server/container, ví dụ Tomcat RemoteIpValve | Khi container hỗ trợ các header bạn cần và đã cấu hình trusted proxies |
| framework | Dùng cơ chế của Spring Framework, như ForwardedHeaderFilter với Servlet hoặc ForwardedHeaderTransformer với WebFlux | Khi cần các khả năng xử lý của Framework phù hợp với ứng dụng |

Ví dụ khi **topology đã được bảo vệ** và proxy đưa vào các header đúng chuẩn mà app định dùng:

~~~properties
server.forward-headers-strategy=framework
~~~

Nếu dùng Tomcat và cách native phù hợp, có thể chọn:

~~~properties
server.forward-headers-strategy=native
~~~

**Không bật một trong hai giá trị chỉ vì backend cần hiển thị scheme https.** Chúng giúp **diễn giải** thông tin, không tự chứng minh header đến từ proxy đáng tin. Trên một số cloud platform, Boot có thể tự chọn native; vì vậy hãy kiểm tra giá trị thực tế ở deployment thay vì đoán default.

### 7.1. ForwardedHeaderFilter làm gì?

Trong stack **Spring MVC/Servlet**, ForwardedHeaderFilter có thể điều chỉnh góc nhìn của request dựa trên header đã nhận, để downstream code thấy scheme, host, port, request URL hoặc remote address tương ứng và để redirect tạo đúng URL bên ngoài. Nó cũng có cơ chế **removeOnly** nhằm bỏ forwarded headers mà **không sử dụng các giá trị đó**.

**removeOnly không phải bộ kiểm định tính đúng/sai của header**. Đây là một lựa chọn loại bỏ metadata khi app không muốn sử dụng nó. Nếu app cần đọc forwarded headers để dựng URL, phải thiết lập trust boundary phía mạng trước.

Trong **WebFlux**, cơ chế tương ứng thường là ForwardedHeaderTransformer; đừng mang cấu hình HttpSecurity, servlet filter hay sự bảo đảm về ThreadLocal sang stack reactive.

### 7.2. Khi dùng native ở Tomcat

Tomcat có thể dùng **RemoteIpValve** để diễn giải địa chỉ và protocol từ proxy. Với Spring Boot, một số thuộc tính thường gặp là **server.tomcat.remoteip.remote-ip-header**, **server.tomcat.remoteip.protocol-header** và **server.tomcat.remoteip.internal-proxies**.

Điều cần học ở đây là **internal-proxies là cấu hình tin cậy, không phải danh sách lấy từ request**. Cần đặt đúng phạm vi proxy thật trong hệ thống và kiểm thử hành vi khi request đến từ IP ngoài phạm vi. Không đặt trust list trống theo kiểu tin mọi proxy trong production; trong tài liệu Spring Boot cũng có cảnh báo cho tình huống này.

### 7.3. Đừng xử lý hai lần

Không cấu hình đồng thời nhiều bộ xử lý forwarded headers ở proxy, Tomcat và Spring theo cách khiến cùng metadata bị áp dụng hai lần hoặc mỗi nơi dùng một kiểu ưu tiên khác. Chọn một pipeline rõ ràng, biết tầng nào chuẩn hóa host/scheme/remote IP, và kiểm chứng kết quả bằng request thật qua edge.

## 8. Ví dụ ở ranh giới: cấu hình proxy có chủ đích

Đoạn NGINX sau **chỉ minh họa phần location/proxy headers** bên trong một TLS virtual host đã được cấu hình chứng chỉ, hostname hợp lệ và chỉ phục vụ **shop.example.test**. Nó không phải file NGINX hoàn chỉnh:

~~~nginx
location / {
    proxy_pass http://127.0.0.1:8080;

    proxy_set_header Host shop.example.test;
    proxy_set_header Forwarded "";

    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host shop.example.test;
    proxy_set_header X-Forwarded-Port 443;
}
~~~

Cần hiểu từng dòng:

1. **Forwarded ""** không chuyển tiếp header Forwarded của client.
2. **X-Forwarded-For $remote_addr** thay phần client gửi bằng IP peer **do NGINX trực tiếp quan sát**; ví dụ chỉ đúng khi NGINX thực sự là edge nhận client, không có CDN chưa được khôi phục địa chỉ.
3. **X-Forwarded-Proto https** phản ánh virtual host TLS của ví dụ, không lấy giá trị ngẫu nhiên từ header client.
4. **Host và X-Forwarded-Host cố định** theo domain công khai đã được cấu hình, tránh dùng một Host ngoài allowlist để dựng link.
5. Backend chỉ lắng nghe loopback **127.0.0.1:8080** trong ví dụ một máy. Với nhiều máy hoặc container, cần firewall/network policy tương đương để chặn đường direct bypass.

Đây không phải cấu hình copy-paste cho mọi topology. Nếu còn CDN phía trước, phải khôi phục client IP qua cơ chế **chỉ tin IP của CDN** tại edge; nếu còn proxy nội bộ, phải quy định rõ hop nào append XFF và cách duy trì scheme của browser. Trong kiến trúc nhiều hop, đừng ghi đè **X-Forwarded-Proto** bằng **http** ở hop nội bộ rồi làm mất scheme HTTPS của phía client.

### 8.1. Tại sao không dùng append ở mọi nơi?

Một cấu hình NGINX thường thấy dùng **$proxy_add_x_forwarded_for**, nghĩa là lấy giá trị X-Forwarded-For hiện có rồi nối thêm IP peer. Điều này hữu ích **sau khi upstream đáng tin đã làm sạch header**, nhưng nếu dùng ngay tại edge với input chưa được làm sạch, các mục do client giả mạo vẫn ở trong danh sách.

Cần phân biệt **append** và **reset** bằng mục đích của từng proxy. Không dùng một mẫu cấu hình cho mọi hop mà không phân tích trust boundary.

## 9. Thực hành Spring Boot: quan sát request trước/sau xử lý header

Ví dụ phục vụ **môi trường local cô lập** để thấy request thay đổi như thế nào. Không triển khai endpoint trả thông tin mạng/headers này ra Internet trong production.

**Yêu cầu:** Dự án Spring Boot 3.x dùng Java 17+ và Gradle Wrapper, có dependencies sau trong file build.gradle (Groovy DSL); Spring Boot plugin và các phần còn lại của project đã được tạo:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Tạo file **src/main/java/com/example/forwardeddemo/ForwardedDemoApplication.java** với nội dung hoàn chỉnh:

~~~java
package com.example.forwardeddemo;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@SpringBootApplication
public class ForwardedDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ForwardedDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/probe").permitAll()
                .anyRequest().denyAll()
            )
            .build();
    }
}

@RestController
class ProbeController {

    @GetMapping("/probe")
    Map<String, Object> probe(HttpServletRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();

        result.put("scheme", request.getScheme());
        result.put("secure", request.isSecure());
        result.put("serverName", request.getServerName());
        result.put("serverPort", request.getServerPort());
        result.put("requestURL", request.getRequestURL().toString());
        result.put("remoteAddr", request.getRemoteAddr());

        result.put("rawForwarded", request.getHeader("Forwarded"));
        result.put("rawXForwardedFor", request.getHeader("X-Forwarded-For"));
        return result;
    }
}
~~~

**Giải thích cấu trúc:** Class public trùng tên file, có main chạy Spring Boot. Class package-private **ProbeController** cùng package nên được component scan. Spring MVC inject HttpServletRequest và Jackson chuyển Map thành JSON. Bean **SecurityFilterChain** cho phép duy nhất GET /probe để dễ thử; các endpoint khác bị denyAll. Đây là endpoint quan sát dành cho máy local, không phải API nghiệp vụ hay một thiết kế security production.

### 9.1. Lần chạy 1: không xử lý forwarded headers

Trong **src/main/resources/application.properties**, đặt:

~~~properties
server.forward-headers-strategy=none
server.address=127.0.0.1
~~~

Chạy bằng Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên PowerShell Windows có thể dùng **.\gradlew.bat bootRun**. Từ máy local, gửi request thử:

~~~bash
curl -i http://127.0.0.1:8080/probe
curl -i -H "X-Forwarded-Proto: https" -H "X-Forwarded-Host: attacker.example.test" -H "X-Forwarded-For: 198.51.100.77" http://127.0.0.1:8080/probe
~~~

**Điều cần quan sát:** Với chiến lược none và kết nối HTTP trực tiếp, các thuộc tính của Servlet thường cho biết **http**, **secure=false**, **serverName=127.0.0.1** và remoteAddr tương ứng với socket local. Các raw headers có thể vẫn đọc được qua request.getHeader(), vì **none không tự làm sạch mọi header cho ứng dụng**. Đừng sử dụng raw header đó để ra quyết định IP allowlist.

### 9.2. Lần chạy 2: minh họa rủi ro nếu bật FRAMEWORK sai chỗ

Đổi chỉ thuộc tính sau trong application.properties rồi khởi động lại:

~~~properties
server.forward-headers-strategy=framework
server.address=127.0.0.1
~~~

Gửi lại request có X-Forwarded-Proto, X-Forwarded-Host và X-Forwarded-For tự khai như trên. **Một số trường trong JSON có thể đổi** theo metadata giả (scheme, host, URL và có thể remote address), vì ForwardedHeaderFilter đang diễn giải forwarded headers. Trong chế độ xử lý Framework, header gốc có thể bị ẩn đối với mã downstream, do filter đã dùng và loại chúng ra khỏi request.

**Đây là phép thử nhằm thấy sự nguy hiểm của việc tin header trên đường direct**, chỉ làm trên localhost. Trong hệ thống thật, phải **cấm đường direct** từ nguồn không tin cậy và buộc request đi qua proxy đã làm sạch header rồi mới sử dụng chế độ framework/native.

Không dùng kết quả thí nghiệm này làm bằng chứng client thật đã truy cập bằng HTTPS. Những trường do header chi phối **không thay đổi trạng thái TLS của kết nối thật**.

### 9.3. Bảng kiểm tra cho một deployment qua reverse proxy

| Luồng kiểm thử | Điều kiện cần đạt |
| --- | --- |
| Browser truy cập HTTPS ở host công khai | App dựng link và redirect theo đúng scheme/host công khai đã cho phép |
| Client gửi Forwarded giả tại edge | Edge xóa, app không chịu ảnh hưởng bởi giá trị client tự khai |
| Client gửi X-Forwarded-* giả tại edge | Edge reset, chỉ dùng giá trị do proxy kiểm soát |
| Client cố gọi backend trực tiếp | Network không cho phép, hoặc backend không tin header và từ chối theo policy |
| Có hai proxy nội bộ | XFF được xây đúng từ các hop đáng tin; schema/host nhất quán |
| Thêm CDN phía trước | Xác định IP client theo cấu hình upstream tin cậy, không lấy mù quáng XFF đầu tiên |
| Gửi Host ngoài danh sách | Proxy từ chối hoặc canonicalize, không dựng URL đến domain lạ |
| Kiểm tra OAuth2 callback/login | Redirect URI đúng host, scheme, port và đường dẫn được đăng ký |
| Truy cập qua prefix /api | URL, redirect và Spring Security request matcher khớp path thực của topology |
| API yêu cầu CSRF/session | Cookie và chính sách CSRF hoạt động đúng qua TLS termination |
| Audit/rate limit theo IP | IP được dẫn xuất từ chuỗi tin cậy, không thể tùy ý giả bằng request header |

Cần kiểm tra **qua đường edge/proxy thật**. MockMvc hoặc một request local tự gắn header chỉ thử cơ chế đọc header, **không kiểm chứng** rằng firewall, CDN, ingress hay chuỗi proxy đang làm sạch header đúng.

## 10. Các lỗi cấu hình thường gặp

### Lỗi 1: Lấy phần tử đầu tiên của X-Forwarded-For làm IP chắc chắn

Đó có thể là giá trị client tự đặt. Cần trust boundary, proxy chain có hợp đồng và thuật toán xử lý đúng với topology. Không dùng chuỗi raw header làm danh tính.

### Lỗi 2: Bật framework/native trong khi backend mở trực tiếp ra Internet

Đây là chỗ dễ xuất hiện header spoofing: client gửi X-Forwarded-Proto hoặc Host giả và ứng dụng diễn giải như sự thật. Giải pháp chính nằm ở **mạng và proxy**, không chỉ trong Java.

### Lỗi 3: Chỉ xóa X-Forwarded-For mà quên Forwarded hoặc X-Forwarded-Host

Các thư viện khác nhau có thể đọc các header khác nhau. Dữ liệu mâu thuẫn có thể ảnh hưởng logging, redirect, link bảo mật hoặc access control. Xóa toàn bộ header ngoài trust boundary, sau đó tạo lại một họ header thống nhất.

### Lỗi 4: Tưởng HTTPS ở proxy đồng nghĩa HTTPS đến backend

TLS termination ở proxy nghĩa là hop **browser → proxy** dùng HTTPS; hop **proxy → backend** có thể dùng HTTP hoặc HTTPS. Phải đánh giá bảo vệ đường nội bộ và tách biệt điều này với scheme mà browser đã thấy.

### Lỗi 5: Dùng X-Forwarded-Host không kiểm tra để tạo reset-password URL

Nếu host do client kiểm soát, server có thể phát hành link tới domain lạ. Hãy canonicalize/allowlist host từ edge và ưu tiên base URL cấu hình cho link bảo mật.

### Lỗi 6: Dùng IP làm phương pháp authentication chính

IP có thể là NAT, mobile network, VPN, CDN hoặc địa chỉ bị giả trong header. IP-based policy có thể là lớp bổ sung khi nguồn được xác minh, nhưng không thay thế authentication/authorization cho user và tài nguyên.

### Lỗi 7: Tin toàn bộ dải mạng nội bộ là proxy đáng tin

Một mạng private có thể chứa nhiều service hoặc workload không được ủy quyền. Chỉ tin đúng ingress/load balancer được phép, network policies phù hợp và cập nhật danh sách khi triển khai thay đổi.

### Lỗi 8: Hiểu sai URL rewrite và context path

Proxy công khai /api nhưng backend nhận / có thể gây sai login redirect, cookie path hoặc request matcher. Xác minh X-Forwarded-Prefix theo phiên bản framework và bộ xử lý đang dùng.

### Lỗi 9: Dùng raw forwarded headers trong audit dù Framework đã chuẩn hóa request

Mã downstream có thể không còn thấy raw headers sau khi filter xử lý. Phải thiết kế observability phù hợp để biết **IP peer tin cậy, client IP đã chuẩn hóa và cơ sở xác định**, đồng thời giảm thu thập dữ liệu nhạy cảm.

### Lỗi 10: Sửa lỗi redirect bằng cách disable kiểm tra bảo mật

Ví dụ OAuth2 login callback sai scheme nên tắt CSRF, bỏ xác minh redirect URI hoặc permitAll rộng. Những thay đổi này không sửa nguyên nhân gốc là **trust boundary / forwarded scheme-host** và có thể tạo lỗ hổng mới.

## 11. Cách tư duy khi thiết kế reverse proxy và Spring Security

Hãy tách câu hỏi thành ba tầng:

**Tầng kết nối:** Request đi qua những proxy nào? Ai là peer trực tiếp? Có TLS ở hop nào? Backend có được gọi trực tiếp không?

**Tầng metadata:** Ai phát hành Forwarded/X-Forwarded-*? Header nào được xóa ở edge? Proxy nào được phép append? Host/scheme/port/prefix nào được coi là canonical? Địa chỉ nào là thông tin quan sát được, địa chỉ nào chỉ được khai báo?

**Tầng ứng dụng:** Spring Boot diễn giải header bằng native hay framework? Spring Security dùng URL và scheme nào để phân quyền, tạo redirect/cookie? Dịch vụ nghiệp vụ có kiểm tra chính xác role, resource ownership và token không?

Không đảo thứ tự bằng cách bật server.forward-headers-strategy trước rồi mới tìm cách xác định proxy nào đáng tin. **Khả năng đọc metadata** và **độ tin cậy của metadata** là hai vấn đề riêng biệt.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Backend nhận kết nối TCP từ 10.0.0.10, X-Forwarded-For là 203.0.113.99, 198.51.100.24, 192.0.2.10. Có chắc 203.0.113.99 là client thật không?

**Đáp:** Không. Nếu edge chỉ append, 203.0.113.99 có thể do client tự nhập. Phải biết các proxy được tin và cách chúng reset/append header.

**Câu 2.** Spring Boot được cấu hình framework và nhận X-Forwarded-Proto: https. Điều đó có xác minh được client đã thiết lập TLS không?

**Đáp:** Không. Framework diễn giải header; TLS phải được xác nhận ở edge và trong topology đáng tin. Nếu backend mở trực tiếp, client có thể giả header này.

**Câu 3.** Vì sao phải xóa cả Forwarded lẫn X-Forwarded-* ở edge?

**Đáp:** Các thành phần có thể đọc những họ header khác nhau; để tránh dùng thông tin do client tự khai và tránh mâu thuẫn, edge phải reset cả hai rồi tạo metadata đáng tin theo hợp đồng thống nhất.

**Câu 4.** Backend sinh link reset password dựa trên X-Forwarded-Host do client chọn. Rủi ro gì?

**Đáp:** Host header poisoning, link bị tạo đến domain không mong muốn. Phải canonicalize và allowlist host hoặc dùng base URL cố định.

**Câu 5.** Đằng sau CDN, edge chỉ dùng địa chỉ socket remote_addr để xác định IP người dùng. Kết quả có thể là gì?

**Đáp:** IP CDN. Muốn có IP client phải xử lý thông tin CDN qua danh sách upstream đáng tin, kiểm tra cấu hình ingress và làm sạch headers tại ranh giới.

**Câu 6.** Nếu app không dùng forwarded headers, có cần xóa chúng không?

**Đáp:** Vẫn cần xem toàn bộ stack và các thành phần có thể dùng chúng. Có thể chọn cấu hình bỏ headers ở edge và chế độ removeOnly hoặc không diễn giải tại app. Không nên để những header không đáng tin vô tình ảnh hưởng đến thư viện khác.

**Câu 7.** Tại sao test bằng curl thêm X-Forwarded-For trên localhost chưa chứng minh hệ thống production an toàn?

**Đáp:** Nó chỉ chứng minh cách framework xử lý chuỗi header ở một kết nối giả lập. Trust boundary thực nằm ở firewall, CDN, load balancer, proxy rewrite và đường truy cập backend.

## 13. Tài liệu chính thức

- IETF RFC 7239 — Forwarded HTTP Extension: https://www.rfc-editor.org/rfc/rfc7239.html
- Spring Framework — Forwarded Headers / ForwardedHeaderFilter: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Boot 3.3 — Running Behind a Front-end Proxy Server: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html

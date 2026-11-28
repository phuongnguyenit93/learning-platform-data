# Kiểm thử cấu hình TLS trong môi trường thật: từ chứng chỉ đến đường truyền end-to-end

Một website có biểu tượng ổ khóa trong trình duyệt vẫn có thể tồn tại nhiều lỗi: chứng chỉ chỉ đúng cho một hostname nhưng sai ở hostname khác, máy chủ quên gửi intermediate certificate, một endpoint phụ vẫn chấp nhận TLS lỗi thời, API gateway kết thúc HTTPS rồi gọi origin bằng HTTP, hoặc ứng dụng dùng mutual TLS nhưng lớp xác thực client bị bỏ qua trên tuyến dự phòng. Vì vậy, kiểm thử Transport Layer Security (TLS) không chỉ là xác nhận “mở HTTPS thành công”.

**Kiểm thử cấu hình TLS trong môi trường thật** là quá trình đánh giá có kiểm soát những kết nối TLS đang phục vụ người dùng và dịch vụ: **đúng tên đích, đúng danh tính máy chủ, chain đáng tin, phiên bản/bộ mật mã phù hợp, chính sách truy cập nhất quán, khả năng vận hành và bằng chứng có thể kiểm tra lại**. Một kết quả tin cậy phải trả lời: **đã kiểm tra endpoint nào, từ vị trí mạng nào, vào thời điểm nào, bằng client nào, kết quả gì và còn điều gì chưa được quan sát**.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, TLS là lớp bảo vệ kênh truyền bổ sung cho VPN, phân đoạn mạng, firewall, WAF, IDS/IPS, bảo vệ DNS và xác thực kết nối. Bài học đặt TLS trong kiến trúc thực tế có CDN/reverse proxy, application gateway, workload cloud, mạng nội bộ và API máy–máy; đồng thời nhấn mạnh **kiểm thử có phép, ưu tiên phương pháp ít tác động, bảo vệ bí mật và kế hoạch rollback**.

> **Nguyên tắc vận hành:** Chỉ kiểm thử hệ thống thuộc quyền quản trị hoặc có phạm vi phê duyệt rõ ràng. Các lệnh dưới đây minh họa cách quan sát hoặc tạo **một số kết nối TLS thông thường** tới endpoint được chỉ định; không phải giấy phép quét Internet, tạo tải, thử đăng nhập hàng loạt, tắt xác minh chứng chỉ hoặc thay đổi production.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Xác định **điểm kết thúc TLS** và phân biệt bảo vệ kênh client–edge, edge–origin, service-to-service và remote access.
2. Kiểm tra **chứng chỉ X.509, Subject Alternative Name (SAN), thời hạn, chain, trust store, hostname verification và SNI**.
3. Đánh giá hỗ trợ **TLS 1.2/TLS 1.3**, thuật toán và nhóm trao đổi khóa theo chính sách của tổ chức, không kết luận chỉ bằng tên cipher.
4. Dùng những phép kiểm tra có phép với **OpenSSL, curl, trình duyệt và telemetry ứng dụng**; lưu bằng chứng mà không tiết lộ khóa.
5. Hiểu vai trò của **ALPN, HTTP/2, HTTP/3/QUIC, HSTS, mTLS, session resumption và TLS 1.3 early data**.
6. Xây **test matrix theo hostname, cổng, IP, môi trường, đường đi, phiên bản client và vị trí quan sát**.
7. Phân biệt sự cố TLS với lỗi **DNS, firewall, VPN, load balancer, proxy, routing, xác thực hoặc logic ứng dụng**.
8. Lập quy trình **thay đổi, giám sát, gia hạn chứng chỉ, kiểm thử hồi quy và rollback** cho dịch vụ thật.

## 2. TLS bảo vệ điều gì và có giới hạn gì?

TLS cung cấp cơ chế **xác thực danh tính endpoint, bảo mật và bảo vệ tính toàn vẹn dữ liệu ứng dụng** khi được thiết kế/cấu hình thích hợp. Đối với HTTPS thông thường, client xác thực máy chủ bằng chứng chỉ và quy tắc hostname/trust chain; sau handshake, request và response HTTP được mã hóa trên đoạn TLS đó.

~~~text
                  Client
                    |
       1. DNS, route, TCP hoặc QUIC
                    |
       2. TLS handshake + server identity
                    |
       3. Khóa phiên được thiết lập
                    |
       4. HTTP application data đã bảo vệ
                    |
                 TLS Server
                    |
                Application
~~~

Những điều **TLS không tự đảm bảo**:

- Người dùng có **quyền ứng dụng**: cần đăng nhập, authorization và kiểm soát phiên riêng.
- Mọi hệ thống trung gian đều an toàn: proxy được ủy quyền có thể kết thúc TLS và đọc request.
- Tên miền không bị quan sát: IP/port và một số handshake metadata có thể vẫn hiển thị; ECH thay đổi một phần mức quan sát tùy cấu hình.
- Nội dung được bảo vệ ở mọi hop: dữ liệu sau điểm kết thúc TLS cần kết nối được bảo vệ riêng nếu cần.
- Dịch vụ có availability tốt: chứng chỉ đúng vẫn có thể đi cùng lỗi route, DDoS, DNS, HTTP 500 hay database.
- Các máy tính không bị xâm nhập: endpoint malware có thể đọc dữ liệu trước mã hóa hoặc sau giải mã.

### TLS là bảo vệ một đoạn kết nối

~~~text
 Browser === TLS A ===> CDN/WAF === TLS B ===> Origin App
                            |
                    Có thể đọc HTTP
                    sau khi kết thúc TLS A
~~~

**TLS A và TLS B là hai kết nối khác nhau.** Chứng chỉ của CDN có thể hợp lệ trong khi chứng chỉ origin đã hết hạn; việc trình duyệt thấy khóa HTTPS **không chứng minh** CDN–origin đang xác minh danh tính server đúng.

## 3. Quy tắc kiểm thử an toàn trên hệ thống thật

Trước khi chạy công cụ, cần xác định **phạm vi, hành vi được phép và giới hạn tác động**.

| Cần xác nhận | Ví dụ quyết định |
|---|---|
| **Chủ sở hữu** | Nhóm phụ trách hostname, CDN, gateway, origin và chứng chỉ |
| **Đích được phép** | FQDN, cổng, IP hoặc môi trường lab/staging thuộc quyền kiểm tra |
| **Nguồn kiểm thử** | Mạng công ty, máy cloud test, đường VPN và client hợp lệ |
| **Mức tác động** | Chỉ đọc cấu hình, kết nối handshake đơn lẻ, HTTP HEAD/GET an toàn; không flood |
| **Khoảng thời gian** | Trong giờ hoạt động hoặc maintenance tùy mức kiểm thử |
| **Dữ liệu nhạy cảm** | Không log private key, access token, session cookie, mật khẩu hay mTLS client key |
| **Ngưỡng dừng** | Dừng nếu latency/error rate, WAF/IDS alert hoặc backend load bất thường |
| **Phê duyệt** | Change/test ticket và người liên hệ ứng cứu |
| **Bằng chứng** | Command, version, timestamp, endpoint, kết quả đã ẩn dữ liệu |

**Phân loại mức kiểm thử:**

1. **Quan sát thụ động:** đọc cấu hình, telemetry, certificate inventory và log hiện có.
2. **Kết nối thủ công ít tác động:** một vài handshake, HEAD request hoặc health request đã được duyệt.
3. **Kiểm thử tương thích nhiều biến thể:** nhiều hostname/client/version/cipher; nên lên lịch, giới hạn tần suất, giám sát.
4. **Scanner tự động diện rộng, stress/fuzz hoặc failover:** chỉ sau khi có phê duyệt riêng, thử ở lab/staging trước và thiết kế stop conditions.

Một **TLS handshake thường không cần đăng nhập ứng dụng**, nhưng vẫn tạo lưu lượng tới hệ thống thật. Không mặc định được phép thử mọi IP cùng subnet hay mọi hostname chỉ vì một dịch vụ công khai.

## 4. Bước đầu tiên: kiểm kê những điểm kết thúc TLS

Hệ thống thực tế thường có nhiều endpoint hơn tên miền chính:

- Website public, tên miền chuyển hướng, API và webhook.
- CDN/edge ở nhiều POP, reverse proxy, load balancer và WAF.
- Gateway cho internal apps qua VPN hoặc Zero Trust access.
- Service mesh, mTLS giữa microservices và API management.
- Cổng quản trị, monitoring, registry, database có TLS.
- IPv4 và IPv6, region, môi trường blue/green hoặc disaster recovery.
- Đường origin trực tiếp, nếu được phép truy cập và có chính sách bảo vệ riêng.

### Bảng kiểm kê mẫu

| Tài sản | Endpoint logic | TLS termination | Luồng tiếp theo | Chủ quản |
|---|---|---|---|---|
| Website | www.example.test:443 | CDN/WAF | CDN → origin qua TLS riêng | Web platform |
| Public API | api.example.test:443 | Application gateway | Gateway → container services | API team |
| Internal portal | portal.corp.example.test:443 | Internal reverse proxy | Proxy → application | Infrastructure |
| Service-to-service | payments.internal.example.test:8443 | Workload/service mesh | mTLS tới service đích | Platform |
| VPN portal | vpn.corp.example.test:443 | Remote-access gateway | Tunnel theo chính sách user | Network/IAM |

Các domain **example.test** là ví dụ không hoạt động trên Internet; khi dùng lệnh phải thay bằng **hostname thuộc phạm vi được phê duyệt**.

### Mỗi phép thử phải xác định được đối tượng

Tối thiểu ghi:

~~~text
Test reference:       TLS-REAL-001
Timestamp/timezone:   [giờ có múi giờ]
Hostname:             [FQDN được duyệt]
Port / transport:     [443 TCP / 443 UDP / cổng khác]
Resolved IP:          [IPv4/IPv6 thực tế]
Source location:      [văn phòng / VPN / cloud region]
SNI used:             [tên đã gửi hoặc none]
HTTP Host:            [nếu có yêu cầu HTTP]
Expected TLS owner:   [CDN / proxy / workload]
Client and version:   [OpenSSL / curl / browser, phiên bản]
Expected policy:      [bản policy hoặc change ticket]
Observed result:      [thành công / lỗi / chưa xác minh]
~~~

Nếu không có những dữ liệu này, việc “TLS test PASS” rất dễ che giấu khác biệt giữa nhiều endpoint, DNS answer hoặc cấu hình edge.

## 5. Hiểu chuỗi xác minh: DNS, TCP, TLS, HTTP và ứng dụng

Khi client kết nối HTTPS, những bước chính cần phân biệt:

~~~text
Client
  |
  +-- DNS: hostname -> address
  |
  +-- Network: route/firewall/VPN/proxy
  |
  +-- Transport: TCP 3-way handshake
  |              hoặc QUIC qua UDP
  |
  +-- TLS: handshake, certificate, hostname,
  |        chain, negotiated version/algorithm
  |
  +-- HTTP: ALPN, request, redirect, status
  |
  +-- App: authentication, authorization,
  |        business transaction
  |
  +-- Response + telemetry
~~~

| Triệu chứng | Lớp cần ưu tiên xác minh |
|---|---|
| Không phân giải được tên | DNS, split DNS, DNSSEC nếu liên quan, resolver policy |
| Timeout trước TLS | IP route, firewall, TCP/UDP reachability, VPN, CDN |
| Lỗi chứng chỉ hoặc hostname | TLS certificate, SNI, trust store, thời gian client |
| Handshake failure / protocol alert | Version, cipher/group, mTLS, gateway policy hoặc middlebox |
| TLS thành công nhưng HTTP 403 | WAF, authorization, gateway, application |
| TLS thành công nhưng HTTP 502/503 | Reverse proxy, upstream, backend, health/route |
| Kết nối nhỏ chạy, tải lớn lỗi | MTU/PMTUD, proxy timeout, buffer hoặc ứng dụng |
| Chỉ một số client lỗi | Trust store, OS/library, ALPN, SNI/ECH, TLS version hoặc client certificate |

**TLS failure không đồng nghĩa hệ thống bị tấn công.** Nhiều lỗi là sai cấu hình, hết hạn chứng chỉ hoặc khác biệt triển khai. Ngược lại, handshake thành công không chứng minh application authorization đúng.

## 6. Chứng chỉ máy chủ: SAN, thời hạn và trust chain

Với HTTPS dựa trên chứng chỉ X.509, client cần đánh giá ít nhất:

1. **Hostname:** tên truy cập phải khớp danh tính DNS/IP trong SAN theo quy tắc xác minh được áp dụng.
2. **Validity:** thời gian hiện tại nằm trong khoảng **Not Before / Not After** của chứng chỉ.
3. **Chain:** có đường xác thực hợp lệ từ chứng chỉ server qua intermediate thích hợp tới **trust anchor** client tin cậy.
4. **Key usage và Extended Key Usage:** tương thích cách sử dụng server authentication theo policy.
5. **Signature/key strength:** phù hợp yêu cầu tổ chức và khả năng client.
6. **Revocation/status và chính sách bổ trợ:** cần hiểu cách client thực tế xử lý, không dựa vào một cờ đơn lẻ.

### SAN quan trọng hơn CN

Trong kiểm tra hostname hiện đại, **Subject Alternative Name (SAN)** là nguồn định danh chính. Không nên dựa vào **Common Name (CN)** như phương án thay thế khi SAN không có hoặc không khớp. Việc dùng wildcard cũng có quy tắc giới hạn, không phải dấu sao thay thế mọi cấp hostname.

| Chứng chỉ có SAN | Truy cập | Đánh giá định danh theo ví dụ |
|---|---|---|
| DNS: api.example.test | api.example.test | Có thể khớp, còn phải xác minh chain và policy |
| DNS: api.example.test | admin.example.test | Không khớp |
| DNS: *.example.test | shop.example.test | Có thể khớp một nhãn theo quy tắc wildcard phù hợp |
| DNS: *.example.test | a.b.example.test | Không mặc nhiên khớp nhiều cấp |
| DNS: api.example.test | Kết nối qua IP literal | Không đủ nếu client kiểm tra theo **IP** mà SAN không chứa IP phù hợp |

**SNI và hostname verification khác nhau:** SNI giúp server chọn cấu hình/chứng chỉ; bước hostname verification là client kiểm tra tên đích đối với chứng chỉ được trình bày.

### Chuỗi chứng chỉ: server gửi gì, client tin gì?

~~~text
Leaf certificate: api.example.test
          |
          v
Intermediate CA certificate(s)
          |
          v
Root CA / trust anchor trong trust store của client
~~~

Server thường gửi **leaf và intermediate cần thiết**. Root CA không nhất thiết được gửi trong handshake; client đã có trust anchor trong trust store. **Không gửi root không phải lỗi mặc định.** Ngược lại, thiếu intermediate có thể khiến một số client xây chain thất bại, dù máy khác tìm được intermediate từ cache hoặc cơ chế khác.

### Vì sao máy A thành công nhưng máy B báo untrusted?

- Trust store khác nhau: OS, browser, JVM, container hoặc runtime.
- Intermediate không được server gửi đủ; một client có thể đã cache, client khác chưa.
- CA nội bộ chỉ được cài trên một nhóm máy được quản lý.
- Đồng hồ hệ thống sai, certificate chưa có hiệu lực hoặc đã hết hạn.
- Root/algorithm bị chính sách của client mới từ chối.
- Proxy hoặc phần mềm kiểm tra TLS đang trả chứng chỉ của một CA khác.

**Không khắc phục bằng cách tắt verify**. Phải sửa chain/trust policy hoặc server identity tại đúng lớp.

## 7. Quan sát TLS với OpenSSL s_client một cách an toàn

Những lệnh này minh họa cách tạo **một kết nối** đến máy chủ được phép kiểm tra. Công cụ và option có thể khác giữa **OpenSSL 1.1.1, OpenSSL 3.x và bản build của hệ điều hành**; trước khi kết luận cần ghi phiên bản.

~~~bash
openssl version
openssl s_client -help
~~~

### 7.1. Bắt tay có SNI và xác minh hostname

~~~bash
openssl s_client \
  -connect api.example.test:443 \
  -servername api.example.test \
  -verify_hostname api.example.test \
  -verify_return_error \
  -brief
~~~

**Ý nghĩa tham số:**

- **-connect:** host và port network được phép.
- **-servername:** SNI mà client gửi tới server để chọn virtual host/chứng chỉ.
- **-verify_hostname:** yêu cầu OpenSSL kiểm tra hostname của peer certificate.
- **-verify_return_error:** không tiếp tục bỏ qua lỗi xác minh chain trong quá trình bắt tay.
- **-brief:** rút gọn báo cáo nếu phiên bản hỗ trợ.

**Lưu ý:** Xác minh có thành công hay không còn phụ thuộc **CA trust store và cấu hình OpenSSL của máy chạy lệnh**. Nếu dịch vụ dùng CA nội bộ, cần dùng tập CA đã được tổ chức phê duyệt; không mặc định tải bất kỳ certificate nào trên mạng rồi đánh dấu là đáng tin.

Đầu ra có thể cho biết phiên bản TLS được thương lượng, cipher suite, peer certificate và kết quả xác minh. Một dòng **Verification: OK** chỉ nói về phép xác minh do chính lệnh và môi trường tin cậy đó thực hiện; nó **không chứng minh** mọi thiết bị/người dùng tin chứng chỉ.

### 7.2. Xem chuỗi chứng chỉ do peer gửi

~~~bash
openssl s_client \
  -connect api.example.test:443 \
  -servername api.example.test \
  -showcerts \
  -verify_hostname api.example.test \
  -verify_return_error
~~~

**-showcerts** giúp nhìn những chứng chỉ peer **gửi trong handshake**, không phải bảo đảm đã liệt kê toàn bộ trust chain cuối cùng client xây được. Trong báo cáo, cần phân biệt **certificates presented** với **validation outcome**.

Nếu có một **bản chứng chỉ công khai đã được xuất riêng và được phép sử dụng**, có thể đọc metadata:

~~~bash
openssl x509 -in server-public-cert.pem -noout -subject -issuer -dates
openssl x509 -in server-public-cert.pem -noout -ext subjectAltName
openssl x509 -in server-public-cert.pem -noout -fingerprint -sha256
~~~

Không chạy những lệnh này trên private key hoặc đưa key vào báo cáo. File **server-public-cert.pem** ở đây là chứng chỉ public X.509, không chứa khóa bí mật.

### 7.3. Kiểm tra qua một IP cụ thể nhưng giữ hostname đúng

Khi có nhiều load balancer/edge và quyền kiểm tra từng IP, có thể kiểm tra IP cụ thể trong khi giữ **SNI** và **hostname verification** cho dịch vụ:

~~~bash
openssl s_client \
  -connect 192.0.2.10:443 \
  -servername api.example.test \
  -verify_hostname api.example.test \
  -verify_return_error \
  -brief
~~~

**192.0.2.10** thuộc dải địa chỉ dành cho tài liệu, chỉ để minh họa. Không chạy lệnh với địa chỉ này như một endpoint thật. SNI khác với địa chỉ kết nối không có nghĩa là giả mạo: nó là cơ chế thông thường của virtual hosting, nhưng chỉ kiểm tra IP mà mình được phép.

### Những sai lầm khi dùng s_client

- Kết nối theo IP nhưng không gửi SNI, rồi kết luận dịch vụ “sai chứng chỉ” khi server trả certificate mặc định.
- Chỉ nhìn certificate subject/CN mà không kiểm tra SAN.
- Thấy handshake hoàn tất nhưng **không bật hostname verification**; việc này có thể bỏ sót lỗi tên.
- Dùng một trust store tùy ý rồi tuyên bố tất cả client đều tin.
- Chạy nhiều biến thể kết nối không giới hạn trên production hoặc đưa toàn bộ log chứa thông tin nhạy cảm ra ngoài.

## 8. Dùng curl để kết hợp TLS với kiểm thử HTTP

**curl** giúp kiểm tra TLS cùng phản hồi HTTP, phù hợp các dịch vụ cho phép HEAD/GET không thay đổi trạng thái. Trên Windows PowerShell đời cũ, lệnh **curl** có thể là alias khác; có thể dùng **curl.exe** nếu bản cài có executable tương ứng.

### Kiểm tra một endpoint HTTPS được phép

~~~bash
curl -vI https://api.example.test/
~~~

**-I** gửi HTTP HEAD. Không phải API nào cũng triển khai HEAD; nếu nhận **405 Method Not Allowed**, TLS có thể vẫn hoàn toàn đúng. Chỉ dùng GET tới endpoint health/read-only đã được chủ ứng dụng cho phép nếu HEAD không được hỗ trợ.

Ghi nhận:

- Địa chỉ và cổng thực kết nối.
- TLS version/cipher được client báo, nếu bản build hỗ trợ hiển thị.
- Certificate verification và SNI/hostname.
- ALPN hoặc HTTP version được thương lượng khi hiển thị.
- HTTP status và header cần thiết.

**HTTP 401/403 không tự là lỗi TLS**: có thể chứng tỏ handshake và kênh HTTP đã hoạt động, còn quyền truy cập bị từ chối đúng chính sách.

### Kiểm tra IP/edge cụ thể bằng curl --resolve

~~~bash
curl -vI \
  --resolve "api.example.test:443:192.0.2.10" \
  https://api.example.test/
~~~

Tùy chọn này dùng **địa chỉ đã chỉ định cho hostname/port** trong phép thử mà vẫn giữ URL hostname, cho phép đánh giá certificate/SNI/HTTP Host theo tên đích. Nó khác với đổi URL thành **https://192.0.2.10/** rồi kiểm tra theo IP literal.

**Không dùng --insecure hoặc -k làm tiêu chí PASS.** Tùy chọn bỏ qua xác minh chứng chỉ có thể che đúng loại lỗi mà bài đang kiểm tra. Nếu sử dụng làm chẩn đoán cô lập trong lab theo phê duyệt, phải đánh dấu rõ rằng **kết quả không chứng minh TLS identity đúng** và không đưa vào ứng dụng production.

## 9. Kiểm tra phiên bản TLS được phép và bị từ chối

Với HTTPS hiện đại, thông thường nên ưu tiên **TLS 1.3** và duy trì **TLS 1.2 với cấu hình mạnh khi cần tương thích**, theo chính sách, nền tảng và nhóm client hỗ trợ. **SSLv2, SSLv3, TLS 1.0 và TLS 1.1** là các giao thức lỗi thời, không phù hợp làm chuẩn phục vụ dịch vụ hiện đại.

### Kiểm tra từng phiên bản theo phạm vi được phép

Ví dụ OpenSSL:

~~~bash
openssl s_client -connect api.example.test:443 \
  -servername api.example.test -tls1_3 -brief

openssl s_client -connect api.example.test:443 \
  -servername api.example.test -tls1_2 -brief
~~~

Kết quả nên được đối chiếu với **những phiên bản client thực sự hỗ trợ**. Một lệnh thất bại có thể do **OpenSSL client build, cipher/group tương thích, chính sách local hoặc proxy**, chứ không đủ tự kết luận server không hỗ trợ một protocol.

Ví dụ giới hạn cả phiên bản tối thiểu và tối đa bằng curl khi bản build hỗ trợ:

~~~bash
curl -vI --tlsv1.2 --tls-max 1.2 https://api.example.test/
~~~

Trong curl, **--tlsv1.2 chỉ xác định phiên bản tối thiểu** trên nhiều phiên bản; dùng thêm **--tls-max 1.2** khi muốn giới hạn thử nghiệm đúng TLS 1.2. Phải kiểm tra **curl --version** hoặc **curl -V** và tài liệu của bản build đang dùng.

### Phân biệt “không hỗ trợ” và “không kết nối được”

| Quan sát | Có thể giải thích |
|---|---|
| TLS 1.3 thành công; TLS 1.2 thành công | Endpoint có thể hỗ trợ hai phiên bản theo điều kiện client |
| TLS 1.3 thất bại; TLS 1.2 thành công | Client/server/proxy chưa tương thích TLS 1.3 hoặc policy chỉ cho 1.2 |
| TLS 1.2 thất bại; TLS 1.3 thành công | Có thể server giới hạn 1.3 hoặc client 1.2 không có bộ mã tương thích |
| Mọi kết nối thất bại trước handshake | Có thể DNS, route, firewall, VPN, cổng không mở |
| Chỉ một hostname trên cùng IP lỗi | SNI/vhost/certificate/routing theo Host cần kiểm tra |

Không kiểm thử giao thức lỗi thời trên production bằng công cụ tạo hàng loạt handshake hoặc giải pháp tải cao; với môi trường thật nên dùng **số lượng nhỏ kết nối, thời gian và quyền đã phê duyệt**. Nếu cần kiểm chứng đầy đủ các bộ mã/giao thức cũ, ưu tiên staging/lab và scanner có giới hạn.

## 10. Cipher suite, key exchange và forward secrecy

Khi đánh giá cấu hình mật mã, cần phân biệt **TLS version, cipher suite, nhóm trao đổi khóa, thuật toán chứng chỉ và chữ ký handshake**.

| Hạng mục | TLS 1.2 | TLS 1.3 |
|---|---|---|
| Cipher suite | Trong tên suite có thể thể hiện key exchange/auth và thuật toán symmetric | Tên suite chủ yếu chỉ AEAD cipher và hash liên quan |
| Key exchange | Có nhiều phương án; một số cơ chế cũ không cung cấp forward secrecy | Handshake thông thường dùng (EC)DHE/PSK theo cơ chế TLS 1.3 |
| Encryption | GCM/ChaCha20-Poly1305 là ví dụ AEAD hiện đại khi hỗ trợ | AEAD là nền tảng của các suite chuẩn |
| Legacy RSA key transport | Có thể tồn tại ở cấu hình TLS 1.2 cũ | Không được TLS 1.3 sử dụng |
| Server certificate | Thường được nhìn thấy trong handshake đầy đủ | Certificate được mã hóa sau ServerHello |
| Renegotiation | Có cơ chế TLS 1.2 và các yêu cầu bảo vệ liên quan | Không dùng cơ chế renegotiation kiểu TLS 1.2 |

### Forward secrecy là gì?

**Forward secrecy** trong những kết nối được cấu hình phù hợp giúp giảm nguy cơ một **server long-term private key** bị lộ về sau làm giải mã được các phiên quá khứ đã ghi lại. Tuy nhiên, tuyên bố forward secrecy chỉ đúng với cách bắt tay, PSK/resumption và xử lý khóa phiên cụ thể; **không phải lời hứa tuyệt đối rằng dữ liệu quá khứ không bao giờ bị lộ trong mọi tình huống**.

### Những sai lầm khi đánh giá cipher

- Thấy chứng chỉ RSA rồi kết luận TLS 1.3 không có forward secrecy; **RSA certificate có thể dùng để ký/xác thực**, không đồng nghĩa RSA key transport.
- Thấy tên cipher chứa AES rồi tự kết luận mạnh; cần xem **mode/AEAD, key exchange, policy và protocol**.
- Ép chỉ một suite quá đặc thù trên production, khiến nhiều client hợp lệ mất tương thích mà chưa đánh giá nhu cầu.
- Đánh giá bằng danh sách cipher do **client hỗ trợ**, nhưng lại tưởng đó là danh sách server sẽ chấp nhận.
- Tự kích hoạt những tùy chọn OpenSSL test khác thường mà không hiểu ảnh hưởng.

**Thiết kế tiêu chí:** duy trì danh sách chuẩn/khuyến nghị được tổ chức phê duyệt, liên kết với hệ điều hành/client được hỗ trợ và vòng đời cập nhật. Không hardcode một lựa chọn “tốt nhất cho mọi trường hợp” khi môi trường có yêu cầu khác nhau.

## 11. SNI, ALPN và virtual hosting

Trên cùng một IP:443 có thể có nhiều website hoặc API. **Server Name Indication (SNI)** cho phép client báo tên mong muốn trong quá trình TLS handshake, để server chọn certificate/policy phù hợp. **Application-Layer Protocol Negotiation (ALPN)** giúp hai phía thương lượng protocol ứng dụng như **h2** hoặc **http/1.1**, tùy stack.

~~~text
Client
  |
  +-- Connect: 192.0.2.10:443
  |
  +-- ClientHello:
       SNI  = api.example.test
       ALPN = h2, http/1.1
  |
  v
Edge server chọn TLS vhost/cert và ALPN phù hợp
  |
  v
Encrypted HTTP connection
~~~

### Quan sát ALPN với OpenSSL

~~~bash
openssl s_client \
  -connect api.example.test:443 \
  -servername api.example.test \
  -alpn h2,http/1.1 \
  -verify_hostname api.example.test \
  -verify_return_error \
  -brief
~~~

Kết quả giúp biết lựa chọn được thương lượng **trong phiên thử cụ thể**. Không thấy **h2** không tự là lỗ hổng; đó có thể là chủ ý hỗ trợ HTTP/1.1. Ngược lại, có ALPN h2 không tự chứng minh tất cả chức năng HTTP/2 đều an toàn hoặc đúng.

### ECH và giới hạn quan sát

**Encrypted ClientHello (ECH)** có thể ẩn tên server thật và một phần thông tin ClientHello trong những triển khai hỗ trợ. NIDS/IPS thụ động có thể nhìn thấy ít metadata hơn. Nhưng ECH **không thay thế xác minh certificate và hostname ở client**, cũng không có nghĩa mọi kết nối HTTPS hiện nay đều dùng ECH.

Để kiểm thử ECH phải có **client/server/DNS và công cụ hỗ trợ**, không nên suy sự hiện diện ECH chỉ từ việc SNI không hiện rõ trong một PCAP.

## 12. HTTP và HSTS: nằm trên TLS nhưng vẫn cần kiểm thử

**HTTP Strict Transport Security (HSTS)** cho phép một website hướng dẫn browser tương thích chỉ sử dụng HTTPS đối với host và thời hạn nhất định. HSTS là cơ chế **HTTP/browser policy**, không phải thuật toán mã hóa của TLS.

Ví dụ header:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

**Ý nghĩa:**

- **max-age:** khoảng thời gian chính sách được browser ghi nhớ.
- **includeSubDomains:** mở rộng phạm vi lên các subdomain.
- **preload:** cơ chế liên quan danh sách preload của browser, có điều kiện và quản trị riêng; không nên tự bật chỉ để “được điểm cao”.

### Điều cần kiểm tra

1. Endpoint HTTP trên cổng 80 (nếu có) có chuyển hướng đúng sang HTTPS không?
2. Website HTTPS có trả header HSTS khi được phê duyệt không?
3. **includeSubDomains** có làm hỏng những hostname con chưa có HTTPS không?
4. Chính sách áp dụng đúng hostname, không vô tình áp vào môi trường cũ?
5. Trình duyệt mới/chưa từng nhận HSTS và browser đã cache HSTS có hành vi khác nhau không?
6. Nếu cân nhắc preload, toàn bộ các điều kiện và kế hoạch duy trì HTTPS dài hạn đã được đáp ứng chưa?

**HSTS chỉ được browser tin nhận từ phản hồi HTTPS hợp lệ theo quy tắc triển khai.** Một redirect từ HTTP sang HTTPS là hữu ích, nhưng tự nó **không thay thế HSTS** khi mục tiêu là chống downgrade trong những lần truy cập sau. HSTS cũng không sửa lỗi certificate; với một số trường hợp, chính sách chặt hơn có thể khiến người dùng không thể bypass cảnh báo chứng chỉ.

### Header bảo mật khác không đồng nghĩa cấu hình TLS

Content-Security-Policy (CSP), X-Content-Type-Options và SameSite cookie là những kiểm soát hữu ích ở tầng web, nhưng **không phải tham số thương lượng TLS**. Báo cáo nên tách **TLS transport posture** khỏi **HTTP application hardening** để sửa đúng owner.

## 13. Mutual TLS (mTLS): xác thực client và server

**Mutual TLS** thêm bước server yêu cầu và xác minh **client certificate**. Nó phù hợp nhiều API máy–máy, service mesh hoặc kết nối quản trị có nhu cầu định danh thiết bị/workload. mTLS **không tự cấp quyền nghiệp vụ**; authorization vẫn phải ràng buộc danh tính đã xác minh với quyền cụ thể.

~~~text
             API Client
                 |
      Verify server certificate
                 |
      Present client certificate
                 |
          [mTLS Gateway]
                 |
       Validate client identity
                 |
       Map identity to policy
                 |
             [Backend API]
~~~

### Cần kiểm thử những gì?

| Trường hợp | Kỳ vọng |
|---|---|
| Client không có chứng chỉ, endpoint yêu cầu mTLS | Không được truy cập API bảo vệ |
| Client có chứng chỉ không thuộc trust policy | Bị từ chối theo cơ chế xác thực |
| Chứng chỉ client hết hạn/không còn được chấp nhận | Không vượt kiểm soát khi policy yêu cầu |
| Client hợp lệ, đúng service identity | Bắt tay và ứng dụng hoạt động theo quyền |
| Client hợp lệ nhưng **không có authorization cho API** | TLS có thể thành công, ứng dụng vẫn trả lỗi quyền |
| Kết nối đi qua ingress/proxy khác | Danh tính client không bị mất hoặc bị tin từ header không xác thực |

**Chỉ kiểm thử mTLS bằng chứng chỉ test được phép sử dụng**, quản lý private key bằng công cụ/secret store của tổ chức. Không đưa khóa vào lệnh, log chia sẻ hoặc bài thực hành nếu không có quy trình bảo vệ tương ứng.

### Tránh lỗi danh tính qua proxy

Nếu TLS client được kết thúc tại reverse proxy, backend có thể nhận danh tính từ **header hoặc metadata do proxy truyền tiếp**. Backend **không được tin tùy ý header client tự gửi** để giả làm chứng chỉ đã được xác thực. Cần có trust boundary, xác thực proxy–backend và cơ chế xóa/ghi đè header tại ingress theo thiết kế.

## 14. Kiểm tra từng hop trong kiến trúc CDN, WAF và cloud

Một dịch vụ public thường có ít nhất hai đoạn:

~~~text
Client              Edge CDN/WAF                Origin
   |                     |                        |
   |--- TLS A ---------->|                        |
   |                     |--- TLS B -------------->|
   |                     |                        |
   |<-- HTTP response qua các đoạn kết nối -------|
~~~

Đánh giá cần có bằng chứng riêng cho:

- **Client–edge:** public SAN/chain, hostname, TLS policy, SNI/ALPN, HSTS và client compatibility.
- **Edge–origin:** endpoint và certificate origin, hostname mà edge dùng để xác minh, trust store, TLS versions/ciphers và chính sách peer validation.
- **Origin–backend:** nếu có service mesh/mTLS, phải xác minh tiếp đường và danh tính workload.
- **Failover:** origin thứ hai/region khác phải có policy tương đương, không chỉ endpoint đang active.
- **Direct-to-origin access:** origin có được chặn truy cập trực tiếp theo kiến trúc và firewall không?

### Ba cấu hình dễ nhầm

1. **TLS termination rồi HTTP đến origin:** có thể được chấp nhận trong một phạm vi kiểm soát nhất định, nhưng **không phải mã hóa end-to-end theo nghĩa có TLS cho cả đường edge–origin**.
2. **TLS tới origin nhưng không verify hostname/chain:** traffic được mã hóa trong một phiên TLS, nhưng **rủi ro xác thực nhầm peer** vẫn tồn tại.
3. **TLS tới origin và verify đúng danh tính:** có kiểm soát xác thực origin theo thiết kế; vẫn phải xét authorization/firewall và các đoạn kết nối khác.

Một chế độ được sản phẩm đặt tên hấp dẫn không thay thế bằng chứng **cert validation và trust policy** ở từng hop.

### Nên kiểm tra cả môi trường không phải public

Internal APIs, database TLS, service mesh và VPN portal thường sử dụng private CA và DNS nội bộ. Kiểm thử phải được thực hiện từ **đường network hợp lệ**, sử dụng CA trust đúng của tổ chức, và báo cáo riêng nếu client không thể tiếp cận do firewall/VPN.

## 15. TLS 1.3 session resumption, tickets và early data

TLS có các cơ chế **session resumption** giúp giảm chi phí handshake khi hai bên tái sử dụng trạng thái được phép. TLS 1.3 có thể dùng **PSK/resumption tickets**; một số cấu hình hỗ trợ **0-RTT early data** cho phép gửi dữ liệu ứng dụng sớm hơn trong phiên nối lại.

### Vì sao 0-RTT cần đánh giá riêng?

Early data **có nguy cơ replay ở những điều kiện nhất định**; ứng dụng và edge cần xử lý theo chính sách, đặc biệt với request thay đổi trạng thái như thanh toán, cấp quyền hoặc cập nhật dữ liệu.

| Khía cạnh | Điều cần xác minh |
|---|---|
| Có bật 0-RTT không? | Xem cấu hình và telemetry của TLS terminator, không suy từ tên protocol |
| Endpoint nào có thể nhận? | Tách GET/HEAD idempotent theo thiết kế khỏi thao tác nhạy cảm |
| Chống replay | Hỗ trợ của sản phẩm và cách ứng dụng xử lý lặp |
| Quan sát | Log phân biệt early data accepted/rejected nếu có |
| Failover/resumption | Session/ticket keys, rotation và hành vi client khi chuyển node |
| Tính tương thích | Không tự mở 0-RTT chỉ để giảm latency mà chưa đánh giá rủi ro |

**0-RTT không đồng nghĩa mọi request TLS 1.3 đều có thể bị replay**, và không phải triển khai nào cũng bật chức năng này. Trong kiểm thử thông thường, có thể chỉ cần xác minh **policy/observability**; bài thử replay chủ động cần môi trường lab và phê duyệt riêng.

## 16. HTTPS qua QUIC/HTTP/3

**HTTP/3** chạy trên **QUIC**, thường dùng **UDP/443** và tích hợp bắt tay dựa trên TLS 1.3. Vì vậy không thể kết luận hỗ trợ HTTP/3 chỉ bằng việc kiểm tra TLS trên TCP/443.

~~~text
HTTPS dùng TCP:
  IP -> TCP/443 -> TLS -> HTTP/1.1 hoặc HTTP/2

HTTPS dùng QUIC:
  IP -> UDP/443 -> QUIC/TLS 1.3 -> HTTP/3
~~~

### Ma trận kiểm tra HTTP/3

| Lớp | Câu hỏi |
|---|---|
| DNS/advertisement | Dịch vụ có công bố đường HTTP/3 phù hợp không? |
| Network | UDP/443 có được phép qua firewall, VPN, proxy và load balancer không? |
| Edge | CDN/WAF có bật HTTP/3 ở hostname đúng không? |
| TLS/QUIC | Client/server hỗ trợ phiên bản/giao thức và bảo vệ danh tính thế nào? |
| App | Request được xử lý và log/trace có tương quan với HTTP/2/1.1 không? |
| Fallback | Khi HTTP/3 không khả dụng, client có đường fallback phù hợp không? |

Khi curl build có HTTP/3, có thể dùng tùy chọn hỗ trợ giao thức theo phiên bản, ví dụ **--http3** để yêu cầu thử theo cách curl hỗ trợ. **Không mặc định mọi bản curl có HTTP/3**. Cần đọc **curl -V** và tài liệu phiên bản; nếu cần kiểm thử cụ thể hãy dùng client đã được phê duyệt.

**Một HTTP/3 request thành công vẫn cần xác minh hostname/certificate**, nhưng cách quan sát/giải mã bắt tay QUIC khác s_client qua TCP. Cũng không nên chặn UDP/443 chỉ để ép fallback nếu chưa đánh giá ảnh hưởng đến người dùng và policy network.

## 17. DNS, IPv4/IPv6 và khác biệt điểm nhìn

Một hostname có thể trả nhiều địa chỉ **A/AAAA**, được phân phối qua CDN hoặc DNS có định tuyến theo vùng. Chỉ kiểm tra từ một mạng hoặc một IP không đảm bảo mọi điểm phục vụ giống nhau.

### Những biến phải ghi lại

1. **Hostname, port và SNI** chính xác.
2. IPv4 hay IPv6, địa chỉ được kết nối.
3. Nguồn kiểm tra: nội bộ, VPN, Internet hoặc cloud region.
4. DNS resolver, split-horizon, proxy và VPN routes.
5. Edge POP/region/node được xác định qua telemetry khi có.
6. Có session resumption hay kết nối mới không, nếu ảnh hưởng kết quả.
7. Client trust store và version.

### Một số hiện tượng thực tế

- **IPv4 PASS, IPv6 FAIL:** AAAA trỏ tới edge chưa cài chứng chỉ hoặc firewall IPv6 khác policy.
- **Internal PASS, Internet FAIL:** split DNS tới origin khác hoặc public CDN thiếu chain.
- **Region A PASS, Region B FAIL:** triển khai chứng chỉ chưa đồng bộ giữa các edge/gateway.
- **VPN PASS, guest network FAIL:** captive portal/proxy DNS có thể can thiệp hoặc dịch vụ nội bộ không mở cho Guest.
- **Một vhost PASS, vhost khác FAIL:** cùng IP nhưng SNI khác dẫn đến certificate/policy khác.

Không gọi tất cả trường hợp này là lỗ hổng TLS; cần xác định **endpoint thật** và ngữ cảnh đường đi.

## 18. Revocation, Certificate Transparency và vòng đời chứng chỉ

Một chứng chỉ hợp lệ về chữ ký và thời gian **không có nghĩa luôn còn được phép sử dụng** nếu private key bị lộ hoặc quyền kiểm soát tên miền thay đổi. Cơ chế revocation và giám sát vòng đời bổ sung cho kiểm tra cơ bản.

### OCSP, CRL và OCSP stapling

- **CRL:** danh sách chứng chỉ bị thu hồi do CA phát hành theo cơ chế tương ứng.
- **OCSP:** giao thức kiểm tra trạng thái chứng chỉ trong những triển khai có hỗ trợ.
- **OCSP stapling:** server có thể gửi phản hồi OCSP được ký/ủy quyền kèm handshake khi áp dụng, giảm nhu cầu client truy vấn trực tiếp.

**Không thể kết luận “certificate chưa bị thu hồi” chỉ vì một công cụ không hiển thị OCSP hoặc không truy cập được responder.** Trình duyệt/client có chính sách revocation khác nhau; TLS 1.3 và đường truyền mã hóa cũng làm thay đổi visibility của sensor thụ động. Phải đánh giá theo **chính sách client thực tế, khả năng CA và nền tảng**.

### Certificate Transparency (CT)

Với nhiều chứng chỉ public TLS, **Certificate Transparency** hỗ trợ ghi nhận/công bố việc phát hành nhằm phát hiện cert bất thường cho domain của tổ chức. CT **không tự chứng minh certificate đang triển khai đúng**, không thay thế hostname verification và không áp dụng giống nhau cho PKI nội bộ.

### Quản lý vòng đời để tránh outage

| Rủi ro | Kiểm soát |
|---|---|
| Chứng chỉ sắp hết hạn | Alert theo số ngày còn lại; owner, escalation và kiểm tra sau gia hạn |
| Thiếu intermediate | Kiểm tra full chain đã trình bày ở từng gateway/edge |
| Gia hạn nhưng chỉ cập nhật một node | Kiểm kê LB/CDN POP/region/failover và kiểm thử sau deploy |
| Private key bị lộ | Quy trình incident response, thu hồi, phát hành lại, bảo vệ secret |
| CA/trust policy thay đổi | Kiểm thử client trust stores, container/JVM/runtime |
| DNS/SAN thay đổi | So sánh certificate danh tính mới với mọi hostname còn phục vụ |
| Reload không thành công | Health checks, reload monitoring và rollback được phê duyệt |

Không lưu private key trong repo, tài liệu học tập, ticket hoặc hệ thống log. **Certificate public** có thể được kiểm tra về metadata; **private key** cần secret store/quyền quản trị riêng.

## 19. Giám sát TLS production: không chỉ chờ người dùng báo lỗi

Tùy mức khả năng nền tảng, nên kết hợp:

- **TLS gateway/reverse proxy logs:** handshake failures, protocol/cipher, SNI, certificate selection và response outcome.
- **Certificate inventory:** SAN, issuer, expiry, fingerprint, điểm triển khai, owner, rotation history.
- **Client telemetry:** loại OS/library, trust errors và failure rate theo phiên bản.
- **Synthetic monitoring:** kết nối từ nhiều network region, IPv4/IPv6 và hành trình ứng dụng được phép.
- **Application tracing:** request ID, login, API success và latency.
- **Network/IDS/NDR:** flow metadata, packet loss, rate limit và số lần handshake bất thường.
- **Change/audit logs:** deployment, secret update, load balancer config, DNS và firewall policy.

### Chỉ số hữu ích

| Chỉ số | Ý nghĩa | Không được suy diễn |
|---|---|---|
| Certificate days to expiry | Thời hạn trước khi certificate hết hiệu lực | Không bảo đảm chain/SAN đúng |
| TLS handshake success rate | Tỷ lệ phiên TLS được thiết lập | Không đồng nghĩa application authorization success |
| TLS failure reason by client | Tìm lỗi trust, version, cipher, mTLS | Không mọi failure đều có nguyên nhân rõ từ server |
| TLS version distribution | Hiểu mức tương thích client và tiến độ bỏ giao thức cũ | Không biết danh tính người dùng chỉ từ version |
| Cipher/group distribution | Phát hiện cấu hình lệch theo hostname/node | Không tự chứng minh mọi suite đều được server chấp nhận |
| HTTP/2/3 adoption | Đánh giá hỗ trợ ALPN/QUIC theo traffic thật | HTTP/3 tỷ lệ thấp có thể do client/path, không phải lỗi |
| p95/p99 handshake latency | Theo dõi độ trễ điều khiển phiên | Có thể phụ thuộc mạng/RTT, không riêng CPU crypto |
| Application success rate | Xác minh user thực sự dùng được dịch vụ | HTTP 200 không luôn đồng nghĩa nghiệp vụ hoàn tất |

**Đồng bộ timestamp và phân nhóm theo hostname/edge/client version** để không che mất sự cố ở một số điểm phục vụ. Việc giám sát cũng cần bảo vệ quyền riêng tư: log TLS có thể chứa IP, hostname, danh tính client cert hoặc token ứng dụng nếu hệ thống ghi quá mức.

## 20. Thiết kế ma trận kiểm thử cấu hình TLS

Một ma trận kiểm thử đáng tin cậy không chỉ chạy một lệnh lên domain chính. Nên bao phủ các biến ảnh hưởng thực tế nhưng giữ quy mô phù hợp, có phép và có lịch.

| Test ID | Lớp/điều kiện | Kỳ vọng |
|---|---|---|
| **TLS-01** | HTTPS FQDN chuẩn, client được hỗ trợ | Handshake OK, hostname/chain hợp lệ, ứng dụng trả kết quả phù hợp |
| **TLS-02** | Mỗi SAN/hostname quan trọng | Không trả chứng chỉ sai hostname vì cấu hình SNI |
| **TLS-03** | IPv4 và IPv6 nếu dịch vụ công bố | Policy và certificate nhất quán |
| **TLS-04** | Edge/region/load balancer node dự phòng trong phạm vi được phép | Không có node dùng cert cũ/hết hạn |
| **TLS-05** | TLS 1.3 từ client hỗ trợ | Thương lượng thành công nếu policy yêu cầu |
| **TLS-06** | TLS 1.2 từ client hỗ trợ | Chỉ bộ mã/phương thức được chấp nhận theo policy |
| **TLS-07** | Giao thức lỗi thời trong lab/phạm vi được duyệt | Bị từ chối theo chính sách, không ảnh hưởng production |
| **TLS-08** | Certificate trust chain | Có thể xác minh từ trust store của các nhóm client đại diện |
| **TLS-09** | Chứng chỉ sai hostname/CA trong lab | Client từ chối, không tự bỏ qua xác minh |
| **TLS-10** | HTTP → HTTPS và HSTS nếu áp dụng | Redirect/header đúng phạm vi, không phá hostname con |
| **TLS-11** | ALPN h2/http1.1 | Thương lượng và ứng dụng hoạt động theo phiên bản được hỗ trợ |
| **TLS-12** | HTTP/3 qua QUIC nếu được bật | Có kết nối hợp lệ và fallback phù hợp theo thiết kế |
| **TLS-13** | mTLS client hợp lệ | Danh tính được xác minh và API xử lý theo quyền |
| **TLS-14** | mTLS client không được cấp quyền trong lab | Không vượt policy; lỗi rõ ràng |
| **TLS-15** | CDN/WAF → origin | Verify origin certificate, hostname và phiên bản phù hợp |
| **TLS-16** | Origin/failover thứ hai | Chính sách tương đương và có giám sát |
| **TLS-17** | Remote VPN/internal service | DNS/private CA và TLS đúng với client thuộc quyền |
| **TLS-18** | TLS resumption/0-RTT policy | Không chấp nhận early data không phù hợp nghiệp vụ |
| **TLS-19** | Sau rotation cert/key | Không xảy ra mismatch, có rollback, synthetic success |
| **TLS-20** | Không có quyền ứng dụng | TLS có thể thành công nhưng authorization vẫn từ chối |
| **TLS-21** | Đường qua proxy/inspection hợp pháp | Chứng chỉ/tên server/trust phù hợp chính sách riêng |
| **TLS-22** | Endpoint từ nhiều nguồn mạng đã được duyệt | Không có sai khác không giải thích được do CDN/DNS/region |

Đánh dấu **PASS/FAIL/INCONCLUSIVE/NOT_APPLICABLE** theo điều kiện được định nghĩa. Ví dụ không có HTTP/3 thì **TLS-12 có thể là NOT_APPLICABLE**, không tự là lỗi; nếu chưa kiểm tra được origin thì **TLS-15 là INCONCLUSIVE**, không ghi PASS từ kết quả client–edge.

## 21. Biên bản kiểm thử đủ để người khác tái hiện

~~~text
Test ID:               TLS-01
Timestamp/timezone:    [thời gian chính xác]
Environment:           [lab / staging / approved production]
Owner/change ticket:   [người quản lý, phê duyệt]
Source location:       [site/VPN/cloud region]
Hostname / port:       [FQDN : port]
Connected IP:          [IPv4/IPv6 đã quan sát]
SNI / ALPN offered:    [giá trị chính xác]
Client tool/version:   [openssl/curl/browser, OS/trust store]
TLS version:           [negotiated]
Cipher / group:        [nếu quan sát được]
Leaf SAN/expiry:       [metadata chứng chỉ]
Chain verification:    [result and trust basis]
Hostname verification: [result]
Revocation check:      [policy/tool or NOT_TESTED]
Edge/origin scope:     [TLS hop được quan sát]
HTTP/app outcome:      [status, request ID, transaction]
Expected behavior:     [policy cụ thể]
Observed behavior:     [kết quả thật]
Impact:                [none / client class affected / ...]
Result:                [PASS / FAIL / INCONCLUSIVE / N/A]
Evidence links:        [đường dẫn nội bộ do owner phê duyệt]
Rollback:              [phương án nếu có thay đổi]
Reviewer:              [người kiểm tra]
~~~

### Điều gì không được đưa vào báo cáo?

- Private key, PEM chứa khóa bí mật, PSK hoặc mật khẩu.
- Access token, bearer header, session cookie và body request có dữ liệu thật.
- Thông tin định danh cá nhân không cần thiết để tái hiện lỗi.
- Kết quả “PASS” không có endpoint, timestamp hoặc command/version.
- Khẳng định “end-to-end TLS” khi chỉ chứng minh được client–edge.

Khi cần chia sẻ nội bộ, dùng **trích yếu đã che dữ liệu** và giữ bản bằng chứng chi tiết theo quyền/retention được phê duyệt.

## 22. Troubleshooting: từ TLS alert đến nguyên nhân thực

| Dấu hiệu | Giả thuyết ưu tiên | Cách xác minh không phá hoại |
|---|---|---|
| **Certificate expired** | Node chưa được gia hạn hoặc thời gian máy sai | Đọc Not After/Not Before, đồng hồ client, inventory node |
| **Hostname mismatch** | SNI/vhost/SAN, DNS chuyển sang IP/node khác | Ghi hostname/SNI, IP được kết nối, SAN |
| **Unknown CA / unable to get issuer** | Chain thiếu, trust store khác, CA nội bộ | Xem presented certs và trust anchor của client |
| **Handshake failure** | TLS version/cipher/group, client cert, policy | Ghi client version, error log gateway, thử client được hỗ trợ |
| **Only old clients fail** | Client không hỗ trợ bộ giao thức/CA mới | Xem matrix phiên bản; cân nhắc nâng cấp client |
| **Only IPv6 fails** | AAAA/node IPv6/cert/policy khác | Kết nối tới IPv6 đã được duyệt và so với IPv4 |
| **mTLS failure** | Client cert không có/hết hạn, CA hoặc identity map sai | PKI, policy, server log và client logs |
| **HTTP 403 after TLS** | WAF/authorization, không nhất thiết lỗi TLS | Correlate request ID với WAF/app |
| **HTTP 502 after cert update** | Edge không tin origin hoặc origin app lỗi | Edge→origin TLS/route/app logs |
| **Only HTTP/3 fails** | UDP/443, QUIC policy, edge config hoặc client support | Kiểm tra giao thức/transport và fallback |
| **Intermittent errors** | Một node/CDN POP có cert khác, rotation lỗi, HA | Phân nhóm IP/region/instance/time |
| **Large transfers fail** | MTU, timeout, app bottleneck; TLS vẫn OK | Flow, PMTUD, proxy/app metrics và request sizes |

### Phân biệt thông báo lỗi từ đâu

Một câu “SSL connection error” do client hiển thị có thể che nhiều nguyên nhân. Nên ghi **error code đầy đủ**, thời gian, IP/SNI và version. Lỗi ở client có thể được phát hiện **trước** khi HTTP request đến ứng dụng, vì vậy app log trống chưa chứng minh hệ thống không nhận kết nối TCP.

Với HTTP/3/QUIC, một số lỗi vận chuyển không xuất hiện trong TCP gateway log. Với TLS qua VPN, lỗi có thể do mạng underlay hoặc proxy; phải đối chiếu telemetry ở **điểm thực tế có traffic**.

## 23. Quy trình thay đổi cấu hình TLS có thể rollback

Một thay đổi tưởng như nhỏ — cài lại chứng chỉ hoặc tắt TLS 1.2 — có thể làm gián đoạn API đối tác, thiết bị cũ, mTLS, monitoring hoặc đường CDN→origin. Quy trình đề xuất:

### Trước thay đổi

1. Xác định **owner**, hostname, SAN, IP, endpoint và hop cần sửa.
2. Chụp cấu hình đã phê duyệt, certificate fingerprint/expiry và baseline traffic/client version.
3. Lập test matrix gồm **client hợp lệ, đường dự phòng, CA nội bộ, mTLS và origin**.
4. Đánh giá nguy cơ với các client cũ; ưu tiên nâng cấp client trước khi siết chính sách nếu có thể.
5. Chuẩn bị certificate/secret trong hệ thống quản lý an toàn, không gửi qua kênh cá nhân.
6. Đặt maintenance window, stop conditions, người phê duyệt và rollback.

### Trong thay đổi

1. Triển khai theo **staging/canary/rolling** nếu nền tảng hỗ trợ.
2. Xác minh TLS handshake + chain + hostname từ client đại diện.
3. Kiểm tra **edge–origin** và mTLS service-to-service, không chỉ public HTTPS.
4. Theo dõi 4xx/5xx, handshake failures, latency, certificate selection, DNS và WAF/IDS alerts.
5. Nếu một nhóm client hợp lệ mất truy cập, kích hoạt điều kiện dừng hoặc rollback đã phê duyệt.

### Sau thay đổi

1. Kiểm tra toàn bộ hostname, vùng cloud và node/đường failover đã liệt kê.
2. So sánh actual state với cấu hình/secret inventory và IaC.
3. Xác minh **lưu lượng hợp lệ thành công** và **client không hợp lệ bị từ chối đúng chính sách**.
4. Lưu biên bản kết quả và lịch xem xét/tự động gia hạn trước khi hết hạn.
5. Thu hồi cấu hình/bí mật cũ theo quy trình an toàn khi không còn cần.

**Rollback không phải mặc nhiên quay lại thuật toán yếu hoặc cert đã bị thu hồi.** Nếu thay đổi xuất phát từ sự cố lộ khóa, phương án phục hồi phải giữ được yêu cầu bảo mật và có thể cần triển khai một certificate mới thay thế.

## 24. Case study: HTTPS public tốt nhưng API gọi qua cloud origin bị lỗi

**Bối cảnh giả định:** Dịch vụ **api.example.test** được phục vụ qua CDN. Trình duyệt người dùng xác minh TLS thành công. Sau khi nhóm platform gia hạn chứng chỉ origin, một phần request API trả **HTTP 502**; dashboard CDN vẫn báo client–edge TLS handshake ổn định.

~~~text
Public FQDN:           api.example.test
Client -> CDN:         TLS 1.3; certificate hợp lệ
CDN -> Origin:         TLS riêng
Change:               Origin certificate rotation
Symptom:              HTTP 502 ở một số edge/region
Observed:             Client TLS OK
Missing evidence:     Origin hostname/trust verification ở từng edge
Security verdict:     Chưa thể kết luận nguyên nhân
~~~

### Những giả thuyết cần phân biệt

1. Certificate origin mới thiếu **SAN** mà CDN dùng để kết nối.
2. CDN và origin dùng **SNI khác tên** dẫn tới chọn certificate sai.
3. Chain origin thiếu intermediate hoặc CA mới chưa có trong trust store của CDN.
4. Origin chỉ bật TLS/cipher mà một số connector/edge chưa hỗ trợ.
5. Origin ứng dụng hoặc load balancer bị lỗi độc lập với TLS.
6. DNS/route giữa CDN và origin ở một vùng đi tới node chưa được cập nhật.

### Quy trình kiểm chứng

1. Xem log edge **upstream TLS error** cùng request ID/timestamp.
2. Ghi **origin hostname, connected IP, SNI, certificate SAN/chain và expected trust** của CDN.
3. Nếu được phép, kiểm tra trực tiếp **origin từ một nguồn quản trị có quyền**, dùng hostname verification thay vì bỏ qua CA.
4. Đối chiếu các node/region còn hoạt động và những node lỗi, certificate fingerprint và deployment time.
5. Kiểm tra upstream health/app logs để tránh nhầm 502 do ứng dụng với lỗi handshake.
6. Sửa đúng cấu hình hoặc triển khai lại certificate theo change được phê duyệt, có rollback an toàn.
7. Chạy test public, edge→origin, API transaction và failover trước khi đóng sự cố.

**Kết luận chỉ được gọi là “lỗi origin TLS đã xác nhận” khi có bằng chứng cụ thể từ handshake/trust/hostname và phép kiểm tra sau sửa.** Public certificate PASS không chứng minh hop CDN–origin PASS.

## 25. Bài thực hành được phép: kiểm tra HTTPS trong lab

### Mục đích

Người học tạo biên bản từ một dịch vụ **lab/staging thuộc quyền sử dụng**, với những phép kết nối bình thường, không sửa chính sách server và không yêu cầu private key.

### Chuẩn bị

- Chọn một FQDN do nhóm học hoặc đội quản trị kiểm soát.
- Đọc phê duyệt, giới hạn nguồn, số kết nối và thời gian.
- Xác định server có phải public endpoint, internal proxy hay một origin riêng.
- Chuẩn bị môi trường có OpenSSL/curl đáng tin cậy, ghi phiên bản và CA trust store.
- Dùng tài khoản test và endpoint HTTP GET/HEAD read-only khi cần.

### Bước 1 — Xác định công cụ

~~~bash
openssl version
curl -V
~~~

Trên Windows PowerShell, có thể chạy **curl.exe -V** để tránh alias ở những môi trường cũ.

### Bước 2 — Ghi hostname, DNS và đường đi

~~~text
Hostname:      [FQDN lab]
Port:          [443 hoặc port được phép]
Resolved IP:   [A/AAAA]
Source:        [vị trí, VPN hay direct]
Network path:  [CDN/reverse proxy/origin nếu biết]
~~~

Có thể đọc DNS bằng công cụ hệ điều hành phù hợp như **nslookup** hoặc **Resolve-DnsName** khi được phép; kết quả DNS không tự xác minh certificate.

### Bước 3 — Xác minh TLS identity

~~~bash
openssl s_client \
  -connect api.example.test:443 \
  -servername api.example.test \
  -verify_hostname api.example.test \
  -verify_return_error \
  -brief
~~~

**Thay hostname trước khi chạy.** Ghi TLS version, cipher, certificate/chain validation và thông báo lỗi nếu có.

### Bước 4 — Kiểm tra HTTP đã được bảo vệ

~~~bash
curl -vI https://api.example.test/
~~~

Nếu HEAD không hỗ trợ, dùng endpoint GET chỉ đọc đã được phê duyệt. Ghi HTTP status và những header có ý nghĩa như HSTS, không lưu cookie/token.

### Bước 5 — So sánh ngữ cảnh kiểm thử

Nếu trong phạm vi cho phép, lặp lại phép kiểm tra với:

- Client thuộc hai trust store khác nhau (chẳng hạn OS và runtime/container).
- IPv4 và IPv6 khi cả hai được công bố.
- Hostname có SNI khác nhau cùng IP, nhưng chỉ các hostname được duyệt.
- Kết nối từ mạng trong VPN và mạng ngoài theo chính sách.
- TLS 1.2 và 1.3 theo năng lực client/server.

Không cần chạy scanner hàng loạt để hoàn thành bài. Với kiểm thử nhiều điểm, lập lịch đủ để không ảnh hưởng gateway/WAF hoặc quota.

### Bước 6 — Kết luận theo bằng chứng

~~~text
Result: PASS / FAIL / INCONCLUSIVE
TLS identity:          [hostname verified? trust chain?]
TLS policy:            [version/cipher thuộc policy?]
HTTP/app:              [status/transaction]
Coverage:              [client, network, IPv4/IPv6, edge/origin]
Not tested:            [mTLS, QUIC, failover hoặc nhóm khác]
Operational impact:    [none / observed]
Next action:           [change ticket, monitor, retest]
Reviewer:              [người xác minh]
~~~

**PASS có điều kiện phải nói rõ phạm vi.** Nếu chỉ thử client–edge từ một mạng, kết luận là “client–edge TLS PASS cho FQDN và nguồn đo đã ghi”, không phải “toàn hệ thống TLS an toàn”.

## 26. Những hiểu nhầm thường gặp

| Nhận định sai | Lý do sai hoặc thiếu | Cách hiểu đúng |
|---|---|---|
| “Có HTTPS là TLS đã cấu hình an toàn” | SAN, trust, phiên bản, policy và upstream có thể sai | Kiểm tra từng điều kiện |
| “S_client kết nối được là certificate OK” | Cần hostname verification và trust validation | Sử dụng SNI, verify hostname và chain theo policy |
| “CN khớp là đủ” | SAN là thành phần chính trong xác minh hostname hiện đại | Kiểm tra SAN DNS/IP |
| “Server phải gửi root CA” | Trust anchor thường nằm trong client trust store | Xem chain và cách client xây trust path |
| “Không có OCSP stapling nghĩa cert đã bị thu hồi” | Tùy CA/client/server policy; không đồng nghĩa revoked | Phân biệt không quan sát và revocation status |
| “RSA certificate nghĩa TLS 1.3 không PFS” | Cert authentication khác key exchange | Đánh giá giao thức và handshake |
| “Client hỗ trợ cipher X nghĩa server cũng hỗ trợ” | Client offer và server selected khác nhau | Xem negotiated/accepted theo test thực |
| “HTTP 403 chứng minh TLS lỗi” | 403 thường là kết quả HTTP/policy sau handshake | Ghép WAF/app log |
| “TLS tại CDN đồng nghĩa origin được bảo vệ” | Edge–origin là TLS hop riêng | Xác minh cert/hostname/trust riêng |
| “TLS 1.3 mặc nhiên bật 0-RTT” | Early data là cấu hình/khả năng riêng | Xem chính sách và replay risk |
| “HSTS sửa được chứng chỉ sai” | HSTS điều khiển browser dùng HTTPS, không sửa trust | Khắc phục SAN/chain/cert trước |
| “HTTP/3 được kiểm bằng s_client TCP/443” | HTTP/3 dùng QUIC trên UDP | Kiểm tra đúng transport/client |
| “Có mTLS thì ứng dụng khỏi cần authorization” | Cert xác thực một danh tính, không cấp mọi quyền | Kiểm soát role/scope/service identity |
| “Một điểm kiểm thử đại diện mọi CDN POP” | Edge/region/node có thể khác cấu hình | Phân nhóm IP, vùng, node và thời gian |
| “Dùng curl -k rồi PASS là được” | -k bỏ qua một phần cốt lõi của bảo mật TLS | Không dùng làm bằng chứng identity đúng |
| “TLS handshake OK nghĩa ứng dụng healthy” | DNS/HTTP/backend/DB có thể vẫn lỗi | Đo giao dịch end-to-end |
| “Đổi cấu hình TLS là việc không cần rollback” | Có thể làm client cũ hoặc origin hết tương thích | Canary, regression, monitoring và rollback |

## 27. Câu hỏi tự kiểm tra

1. TLS bảo vệ những thuộc tính nào? Vì sao handshake thành công chưa đủ xác nhận authorization?
2. Khi URL là **api.example.test** nhưng kết nối qua IP cụ thể, cần dùng SNI và hostname verification như thế nào?
3. **SAN** và **CN** khác vai trò gì trong xác minh certificate của HTTPS hiện đại?
4. Vì sao thiếu intermediate certificate có thể gây lỗi ở một nhóm client nhưng không gây lỗi ở nhóm khác?
5. Lệnh **openssl s_client** cần có những tùy chọn nào để vừa gửi SNI vừa kiểm tra hostname/trust?
6. Vì sao **curl -k** không phù hợp làm tiêu chí PASS cho kiểm thử TLS production?
7. TLS 1.2 và TLS 1.3 khác nhau thế nào về cipher naming, RSA key transport và visibility chứng chỉ?
8. Một website có **TLS 1.3 PASS** nhưng origin dùng certificate hết hạn. Vì sao trình duyệt vẫn có thể thấy chứng chỉ hợp lệ?
9. HSTS có giải quyết được lỗi trust chain hoặc ngăn browser truy cập subdomain chưa có HTTPS không?
10. **ALPN** dùng để làm gì? HTTP/3 khác HTTP/2 ở transport và cách kiểm thử ra sao?
11. Vì sao một TLS cipher được client hỗ trợ không tự chứng minh server cũng cho phép?
12. Khi dùng mTLS qua proxy, cần chống tin tưởng sai client identity header như thế nào?
13. **0-RTT early data** tạo rủi ro nào và nên tránh áp dụng với nhóm request gì khi chưa có xử lý phù hợp?
14. Vì sao cùng hostname có thể PASS trên IPv4 nhưng FAIL trên IPv6 hoặc một CDN region?
15. Chứng chỉ còn hạn và chain OK có chứng minh mọi client xử lý revocation giống nhau không?
16. Những nguyên nhân nào khiến OpenSSL báo verify OK trên máy kiểm thử, nhưng JVM container production vẫn không kết nối được?
17. Khi đổi chứng chỉ origin, những log và phép thử nào phân biệt lỗi edge–origin TLS với lỗi ứng dụng?
18. Một API từ chối request với HTTP 403 sau handshake mTLS hợp lệ. Có phải cấu hình TLS sai không?
19. Test matrix cần bao phủ những biến nào để kết luận có căn cứ về TLS ở môi trường hybrid cloud?
20. Khi cập nhật TLS policy, cần điều kiện dừng, rollback, giám sát và bằng chứng sau thay đổi gì?

## 28. Ghi nhớ trọng tâm

**Kiểm thử cấu hình TLS trong môi trường thật phải xác minh danh tính và độ tin cậy của từng điểm kết thúc TLS, không chỉ sự tồn tại của HTTPS.** Cần đối chiếu **SNI, SAN, certificate chain, thời hạn, trust store, TLS versions, cipher/group, ALPN, HTTP behavior và mTLS khi áp dụng**; nhớ rằng **TLS tại CDN/edge và TLS tới origin là những kết nối riêng**, với chính sách và lỗi có thể khác nhau.

Quy trình tốt bắt đầu từ **kiểm kê endpoint, phạm vi được cấp quyền, cách thu bằng chứng có thể tái hiện**, rồi kiểm tra ít tác động bằng OpenSSL/curl hoặc công cụ đã được duyệt. Các kết quả phải phân biệt **TLS, DNS, network/VPN, HTTP/WAF và application authorization**; xem cả IPv4/IPv6, QUIC/HTTP/3, session resumption và các đường failover phù hợp. Cuối cùng, vận hành TLS an toàn cần **certificate lifecycle/rotation, monitoring đa nguồn, test matrix có PASS/FAIL/INCONCLUSIVE, change control và rollback**. Một kết luận có giá trị phải nói rõ **điều đã kiểm chứng, phạm vi của nó và những phần chưa được kiểm thử**.

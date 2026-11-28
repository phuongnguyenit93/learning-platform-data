# Reverse proxy như một trust boundary

**Reverse proxy** là thành phần đứng trước một hoặc nhiều dịch vụ backend, tiếp nhận kết nối từ client rồi thay mặt client chuyển tiếp yêu cầu tới dịch vụ phù hợp. Trong kiến trúc mạng an toàn, reverse proxy không chỉ là công cụ cân bằng tải: nó thường là một **trust boundary** (*ranh giới tin cậy*) giữa vùng ít tin cậy, chẳng hạn Internet, và những vùng nội bộ có chính sách truy cập nghiêm ngặt hơn.

Một ranh giới tin cậy là nơi hệ thống **không được tự động tin những dữ liệu hoặc quyền mang từ vùng trước sang vùng sau**. Tại reverse proxy, ranh giới này xuất hiện ở nhiều điểm: kết nối TLS, HTTP request, header nhận diện client, token phiên, tên host, URL/path, chính sách routing, rate limiting và đường truyền tới backend. Proxy cần quyết định **nội dung gì được nhận, biến đổi, chuyển tiếp hoặc từ chối**, đồng thời phải truyền cho backend một ngữ cảnh mà backend có thể sử dụng an toàn.

Ví dụ, backend không nên tin một header **X-User-Role: admin** do Internet client tự gửi. Nếu một gateway xác thực có quyền phát hành thông tin danh tính, proxy phải **xóa dữ liệu không tin cậy, xác minh danh tính và chỉ tạo lại header nội bộ qua kênh được bảo vệ**. Tương tự, một header **X-Forwarded-For** do client tự khai không tự chứng minh địa chỉ IP thật của họ.

Trong chương **Proxy reverse proxy và cân bằng tải** thuộc module **SECURITY_NETWORK_SECURITY**, chủ đề này kết nối trực tiếp với phân đoạn mạng, firewall, VPN, IDS/IPS, WAF, TLS, bảo vệ DNS và hạ tầng cloud. Thiết kế đúng phải kết hợp **lọc và xác thực tại biên, giới hạn đường đến backend, xác thực TLS cho từng chặng và phân quyền tại ứng dụng**.

> **Nguyên tắc:** Một request được reverse proxy chuyển tiếp **không tự trở thành đáng tin**. Backend chỉ nên tin những thuộc tính được một thành phần được ủy quyền xác minh, truyền qua đường không thể dễ dàng bị giả mạo, và vẫn phải thực hiện kiểm tra quyền nghiệp vụ của chính nó.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **reverse proxy**, **forward proxy**, **load balancer**, **API gateway** và WAF theo vai trò; hiểu vì sao có thể có nhiều vai trò trong cùng một sản phẩm.
2. Xác định **trusted/untrusted zones**, những dữ liệu vượt qua ranh giới và thành phần thực thi chính sách tại mỗi điểm.
3. Giải thích **TLS termination**, **re-encryption**, upstream certificate validation và mTLS giữa proxy với backend.
4. Phân tích việc giả mạo hoặc xử lý sai **X-Forwarded-For, Forwarded, X-Real-IP, X-Forwarded-Proto** và header danh tính.
5. Thiết kế cách xác thực **Host/:authority**, SNI, URL/path, HTTP method và request body trước khi định tuyến.
6. Hiểu rủi ro **HTTP request desynchronization/smuggling** ở ranh giới parser và cách giảm thiểu theo hướng phòng vệ.
7. Áp dụng bảo vệ **authentication, authorization, CORS, cookies, cache, rate limiting, WAF và request size** mà không tạo cảm giác an toàn giả.
8. Tránh **bypass reverse proxy** qua IP backend, route nội bộ, cloud origin, service hoặc cấu hình DNS sai.
9. Thiết kế telemetry, kiểm thử tích cực/tiêu cực và runbook ứng phó khi phát hiện ranh giới tin cậy bị vượt qua.

## 2. Reverse proxy và trust boundary là gì?

### 2.1. Reverse proxy khác forward proxy

| Thành phần | Đứng về phía nào? | Mục đích thường gặp | Ranh giới cần quan tâm |
| --- | --- | --- | --- |
| **Forward proxy** | Đại diện client truy cập dịch vụ bên ngoài | Egress control, lọc nội dung, quản lý truy cập Internet | Client nội bộ → proxy → Internet |
| **Reverse proxy** | Đại diện một hoặc nhiều server tiếp nhận client | TLS termination, routing, load balancing, kiểm soát biên | Internet/đối tác → proxy → backend |
| **Layer 4 load balancer** | Phân phối kết nối theo thông tin vận chuyển | TCP/UDP balancing, HA | Kết nối và IP/port, ít hoặc không đọc HTTP |
| **Layer 7 load balancer** | Phân phối theo thông tin ứng dụng | Host/path/header routing, TLS, policy HTTP | Nội dung HTTP và quyết định route |
| **API gateway** | Điểm vào các API | AuthN/AuthZ, quota, API routing, logging | Client/API identity → dịch vụ |
| **WAF** | Lọc HTTP theo quy tắc ứng dụng | Giảm một số kiểu request độc hại | HTTP parser/inspection → ứng dụng |

Một nền tảng như CDN, ingress controller, gateway hoặc reverse proxy thương mại có thể **đồng thời cung cấp nhiều chức năng**. Tên sản phẩm không đủ để biết nó có thực hiện TLS verification, authorization, WAF hay identity propagation đúng cách.

### 2.2. “Trust boundary” không có nghĩa backend được phép tin tất cả

Khi request đi vào từ Internet, hầu hết dữ liệu HTTP ban đầu phải được xem là **do client kiểm soát**, kể cả tên header, cookie, query string và nhiều thuộc tính URL. Reverse proxy có thể áp dụng xác thực, biến đổi và kiểm soát nguồn gốc. Nhưng backend vẫn phải kiểm tra những thuộc tính quan trọng cho quyết định nghiệp vụ.

Ví dụ: proxy xác định người dùng đã đăng nhập, nhưng ứng dụng vẫn phải quyết định người đó **có quyền đọc đơn hàng số 42 hay không**. Việc proxy chuyển tiếp request không chứng minh quyền đọc bản ghi đó.

### 2.3. Một request có thể qua nhiều trust boundary

~~~mermaid
flowchart LR
    U["Internet / Client<br/>Untrusted"] -->|"TLS 1"| EDGE["CDN / Edge Proxy"]
    EDGE -->|"TLS 2"| RP["Reverse proxy / API gateway<br/>Policy enforcement"]
    RP -->|"TLS 3 / mTLS"| APP["Application<br/>Private network"]
    APP -->|"Service identity"| DATA[("Data zone")]
    EDGE -. "Edge identity/headers" .-> RP
    RP -. "Verified context only" .-> APP
    APP -. "App authorization" .-> DATA
~~~

Mỗi đường TLS là một kênh và mỗi điểm **terminate rồi tạo kết nối mới** là một ranh giới riêng. Không được suy rằng HTTPS ở trình duyệt chứng minh kết nối CDN → proxy → backend cũng được mã hóa và xác minh danh tính.

## 3. Xác định tài sản, nguồn dữ liệu và mức tin cậy

Một mô hình đe dọa reverse proxy cần nhận diện:

| Đối tượng | Tài sản / dữ liệu | Nguồn tin cậy ban đầu | Rủi ro nếu tin sai |
| --- | --- | --- | --- |
| Internet client | URL, header, cookie, body | **Untrusted** cho đến khi được kiểm tra | Host spoofing, header injection, request bất thường |
| Client IP | IP peer trực tiếp ở kết nối tới proxy | Do transport quan sát, nhưng có thể là IP của CDN/NAT | Dùng sai trong rate limit, allowlist, audit |
| Forwarded IP chain | X-Forwarded-For / Forwarded | Có thể hoàn toàn do client gửi nếu không kiểm soát | Giả mạo “IP nội bộ”, bỏ qua policy |
| User identity | JWT, session, client cert, internal identity headers | Chỉ tin sau khi nguồn phát hành và nội dung được xác minh | Mạo danh user/admin |
| Requested hostname | Host hoặc HTTP/2 :authority | Client có thể lựa chọn giá trị | Định tuyến nhầm tenant, password-reset link sai |
| TLS server identity | Chứng thư server upstream | Do TLS verifier xác nhận theo CA/tên kỳ vọng | Proxy kết nối sai backend |
| Route configuration | Host/path → upstream pool | Hệ thống quản trị đã phê duyệt | Chuyển dữ liệu đến dịch vụ không được phép |
| Backend response | Body, cache-control, Set-Cookie, redirect | Đến từ backend cụ thể; chưa mặc nhiên an toàn cho mọi user | Lộ dữ liệu qua cache hoặc header |
| Management plane | API cấu hình proxy, secrets và certificate | Chỉ tài khoản/quy trình quản trị được phép | Chiếm quyền cấu hình toàn bộ đường vào |

**Cần phân biệt dữ liệu do transport quan sát với thông tin do HTTP client tự khai.** Địa chỉ socket peer trực tiếp có thể là một CDN hợp lệ; nó không tự là địa chỉ IP người dùng cuối. Một header “Client-IP” lại càng không thể được tin chỉ vì tên nghe đáng tin.

## 4. Thiết kế các vùng mạng và đường đi được phép

Một kiến trúc phòng vệ hợp lý thường phân biệt:

- **Internet/External zone:** mọi client công khai và lưu lượng từ mạng ngoài.
- **Edge/DMZ zone:** reverse proxy, CDN ingress, WAF hoặc load balancer tại biên.
- **Application zone:** dịch vụ backend, không công khai trực tiếp.
- **Data zone:** database, cache nội bộ, message broker có policy riêng.
- **Management zone:** quyền cấu hình proxy, certificate/secret manager và monitoring.

~~~mermaid
flowchart TB
    INTERNET["Internet / đối tác"] -->|"Chỉ endpoint công khai đã duyệt"| EDGE["Reverse proxy ở Edge / DMZ"]
    EDGE -->|"Đúng upstream/port<br/>mTLS/TLS nếu yêu cầu"| API["API / App zone"]
    API -->|"Service account và policy riêng"| DB[("Data zone")]
    MG["Management zone"] -->|"IAM/MFA/audit"| EDGE
    EDGE -. "Không được route trực tiếp" .-> DB
    INTERNET -. "Deny bypass" .-> API
    INTERNET -. "Deny" .-> MG
    EDGE -. "Logs, metrics, alerts" .-> SOC["SOC / SIEM"]
    API -. "App auth/audit" .-> SOC
~~~

**Điểm quan trọng:** reverse proxy không được là cách duy nhất chặn truy cập tới backend nếu backend vẫn có một public IP hoặc security group cho phép Internet vào trực tiếp. Phải kiểm tra cả **network ACL, firewall, cloud security group, DNS, public endpoint và đường quản trị**.

### 4.1. Quy tắc kết nối theo chiều

| Nguồn | Đích | Chính sách gợi ý |
| --- | --- | --- |
| Internet | Public VIP / reverse proxy | Chỉ giao thức/cổng được công bố, thường HTTPS theo thiết kế |
| Internet | Backend private IP | **Deny** |
| Reverse proxy | Backend pool | Chỉ đích và port ứng dụng cần thiết |
| Reverse proxy | Database | **Deny** nếu proxy không có nhiệm vụ truy cập dữ liệu |
| Backend | Database | Allow tối thiểu theo service identity và nhu cầu |
| Admin được cấp phép | Proxy management | Qua management network, IAM/MFA, audit |
| Proxy | PKI/DNS/telemetry | Chỉ endpoint cần cho xác minh và vận hành |

Lưu ý đây là **mô hình chính sách**, không phải firewall rule hoàn chỉnh. Chế độ triển khai, mạng ảo, IPv6, failover, service discovery và điểm TLS termination thực tế có thể cần luồng bổ sung đã phê duyệt.

## 5. TLS termination: một kết nối an toàn hay nhiều kết nối?

### 5.1. Kết thúc TLS tại proxy

Khi reverse proxy làm **TLS termination**, client xác minh chứng thư của proxy cho hostname công khai. Proxy giải mã HTTP để định tuyến, kiểm tra rule, áp dụng WAF/rate limit hoặc thêm header. Sau đó proxy gửi request tới backend bằng một kết nối khác.

**Điều này tạo hai trách nhiệm:**

1. **Client → Proxy:** client xác minh chứng thư, SAN/hostname, chuỗi CA, thời hạn và handshake của endpoint công khai.
2. **Proxy → Backend:** nếu dùng TLS upstream, proxy là TLS client và phải xác minh **tên dịch vụ backend** cùng chain/trust anchor phù hợp.

Một hệ thống có **HTTPS phía ngoài nhưng HTTP plaintext phía trong** có thể được thiết kế theo yêu cầu cụ thể, nhưng nó tạo một vùng mạng có HTTP không mã hóa. Cần đánh giá mức tin cậy, compliance và khả năng quan sát/can thiệp ở chặng nội bộ. Với dịch vụ nhạy cảm, **TLS upstream có xác minh đầy đủ hoặc mTLS** thường là lựa chọn đáng xem xét.

### 5.2. Re-encryption không có nghĩa đã xác minh backend

Đôi khi proxy tạo TLS đến backend nhưng cấu hình bỏ qua certificate validation. Khi đó nội dung chặng proxy–backend được mã hóa theo kênh đã thương lượng, **nhưng proxy chưa có bằng chứng đủ mạnh rằng endpoint là backend mong muốn**.

Một chính sách an toàn cần xác định:

- Backend CA/trust store được phê duyệt.
- **SNI** và tên host/service identity mà proxy mong đợi.
- Kiểm tra SAN/hostname, certificate validity, EKU và các ràng buộc PKI.
- Hành vi khi verification thất bại: từ chối hoặc fallback nào được phép.
- Cách gia hạn, xoay chứng thư và giám sát theo từng upstream pool.

### 5.3. mTLS giữa proxy và backend

**mTLS** cho phép hai đầu xác minh chứng thư của nhau theo chính sách. Backend có thể chỉ nhận kết nối từ proxy/gateway có client certificate được phép; proxy xác minh backend theo danh tính dịch vụ.

Tuy nhiên **mTLS không tự truyền danh tính người dùng cuối**. Backend biết “kết nối đến từ proxy đáng tin” nhưng vẫn cần nhận và xác minh user context theo thiết kế. Mặt khác, việc proxy được xác thực mTLS cũng không cho phép nó bỏ qua **application authorization**.

### 5.4. TLS passthrough có khác gì?

Trong **TLS passthrough**, load balancer hoặc proxy có thể chuyển tiếp kết nối mã hóa ở mức TCP mà không giải mã HTTP; backend kết thúc TLS. Khi đó các kiểm soát L7 phụ thuộc nơi kết thúc TLS, và thiết bị passthrough thường không nhìn thấy đầy đủ method, path hoặc HTTP header.

**Không nói một thiết bị passthrough đã thực hiện kiểm tra WAF nội dung HTTPS** nếu không có cơ chế giải mã phù hợp. Mọi sơ đồ phòng vệ phải đánh dấu rõ **TLS chấm dứt tại đâu**.

## 6. Địa chỉ IP gốc và những header được chuyển tiếp

### 6.1. Vì sao backend nhìn thấy IP proxy?

Khi reverse proxy mở một kết nối mới tới backend, **source IP của kết nối TCP** tại backend thường là IP của proxy hoặc một địa chỉ SNAT liên quan. Nếu ứng dụng cần biết IP client cuối, proxy có thể truyền thêm metadata theo giao thức, nhưng thông tin này chỉ đáng tin trong **một chuỗi proxy được quản lý**.

Một số header thường gặp:

| Header | Ý nghĩa thông dụng | Vấn đề cần chú ý |
| --- | --- | --- |
| **X-Forwarded-For** | Danh sách địa chỉ client/proxy theo convention triển khai | Có thể được client tự cung cấp và bị nối thêm không đúng |
| **Forwarded** | Header theo RFC 7239 có tham số như for, by, host, proto | Cần parser tin cậy và kiểm tra nguồn gửi |
| **X-Real-IP** | Header không chuẩn phổ quát, thường chứa một IP được proxy gán | Không tin nếu đi trực tiếp từ Internet |
| **X-Forwarded-Proto** | Scheme được client dùng ở chặng ban đầu theo định nghĩa chuỗi proxy | Bị giả có thể gây lỗi redirect, secure cookie hoặc logic chính sách |
| **X-Forwarded-Host** | Host được proxy chuyển cho backend | Có thể gây nhầm absolute URL hoặc tenant nếu không chuẩn hóa |
| **PROXY protocol** | Mang metadata transport giữa các proxy/LB có hỗ trợ | Chỉ chấp nhận trên listener dành cho peer tin cậy, không phải từ Internet bất kỳ |

### 6.2. Kịch bản giả mạo X-Forwarded-For

Giả sử một client có IP do proxy quan sát là **198.51.100.40** nhưng tự gửi:

~~~http
GET /reports HTTP/1.1
Host: app.example.test
X-Forwarded-For: 10.0.0.5
~~~

Nếu ứng dụng lấy IP đầu tiên trong X-Forwarded-For rồi kết luận **10.0.0.5 là mạng quản trị được phép**, nó có thể chấp nhận một giá trị **do client tự khai**. Đây là lỗi về **nguồn tin cậy của metadata**, không phải bằng chứng client thật sự dùng IP 10.0.0.5.

Ví dụ này chỉ minh họa một header trong HTTP, không phải quy trình khai thác hay kiểm thử bên ngoài phạm vi được phép.

### 6.3. Thiết kế trusted proxy chain

Để đọc IP gốc an toàn:

1. **Xác định từng hop**: client → CDN → edge proxy → gateway → backend.
2. Liệt kê **địa chỉ/mạng của những proxy thật sự đáng tin**; không mặc nhiên tin mọi IP private hoặc mọi đầu vào từ Internet.
3. Tại ingress đầu tiên do tổ chức kiểm soát, **xóa hoặc chuẩn hóa các forwarding header do client tự gửi** theo policy.
4. Chỉ **nhận metadata từ immediate upstream** nằm trong tập proxy tin cậy, qua kênh và listener được bảo vệ.
5. Nếu hệ thống dùng danh sách nhiều hop, áp dụng **thuật toán chọn client IP theo chuỗi trusted hops** đúng với sản phẩm; không lấy phần tử đầu tiên hoặc cuối cùng một cách mù quáng.
6. Đồng bộ quy tắc với backend, WAF, rate limiter và log; tránh mỗi lớp suy luận một IP khác nhau.
7. Kiểm thử thay đổi CDN/edge, IPv4/IPv6, NAT và những hop dự phòng.

**Cần bảo vệ cả đường mạng tới proxy.** Nếu ai cũng có thể kết nối trực tiếp vào listener chỉ dành cho CDN và tự gửi header giống CDN, việc chọn trusted proxy bằng header sẽ không còn đáng tin.

### 6.4. PROXY protocol không tự xác thực nguồn

PROXY protocol có thể bảo toàn metadata nguồn ở chặng vận chuyển giữa các thành phần hỗ trợ, nhưng **không tự là cơ chế xác thực mật mã**. Listener hỗ trợ PROXY protocol nên chỉ được truy cập bởi những load balancer được phê duyệt, kết hợp firewall, private networking hoặc xác thực kênh phù hợp.

**Không bật nhận PROXY protocol trên cổng mà client Internet bất kỳ được tự kết nối**, nếu thiết bị và kiến trúc chưa có cơ chế xác thực/giới hạn nguồn tương ứng.

## 7. Host, SNI, :authority và định tuyến theo tên

### 7.1. Client có thể chọn Host header

Trong HTTP/1.1, **Host** thường cho biết tên tài nguyên yêu cầu; trong HTTP/2 và HTTP/3, **:authority** đóng vai trò liên quan tới authority của request. Giá trị này ảnh hưởng virtual hosting và routing nhưng **có thể xuất phát từ client**.

Reverse proxy cần kiểm tra hostname có thuộc tập được công bố và mapping của nó có dẫn tới backend được phê duyệt hay không. Không nên dùng một **default backend có quyền quá rộng** để xử lý mọi Host không nhận diện được.

### 7.2. SNI khác Host

**TLS SNI** giúp endpoint TLS chọn chứng thư hoặc chính sách phù hợp. **HTTP Host/:authority** giúp ứng dụng định tuyến request sau bước TLS. Hai giá trị có thể **khác nhau** nếu cấu hình client/proxy hoặc các trường hợp đặc biệt.

Mọi hệ thống phục vụ đa domain/multi-tenant cần đánh giá cách xử lý khi:

- SNI thuộc tenant A nhưng HTTP authority thuộc tenant B.
- Host không được cấu hình nhưng request vẫn đi vào default server.
- Host có port, chữ hoa/thường, dấu chấm kết thúc hoặc định dạng không được chấp nhận.
- Cùng tên được phục vụ trên IPv4 và IPv6 nhưng cấu hình TLS/routing khác nhau.

**Không suy rằng chứng thư hợp lệ ở TLS tự chứng minh Host HTTP bên trong đã được phê duyệt**. Chứng thư có thể chứa nhiều SAN, và backend routing vẫn cần kiểm tra tenant/service mapping.

### 7.3. Host header injection và URL generation

Một ứng dụng có thể dùng Host hoặc X-Forwarded-Host để tạo đường dẫn tuyệt đối trong email, reset password, callback OAuth hoặc redirect. Nếu tin giá trị client tự khai, ứng dụng có nguy cơ tạo URL trỏ sai domain.

Biện pháp phòng vệ: dùng **public base URL đã cấu hình**, allowlist hostname, chuẩn hóa authority tại proxy và không sử dụng forwarded host không xác thực làm nguồn duy nhất khi tạo đường dẫn nhạy cảm.

## 8. Path, query, method và URL normalization

Reverse proxy thường định tuyến theo đường dẫn, ví dụ:

- **/api/** tới API service.
- **/admin/** tới management UI qua chính sách bổ sung.
- **/static/** tới dịch vụ tài nguyên tĩnh.

Nhưng **URL path có thể có nhiều dạng biểu diễn tương đương hoặc không tương đương** tùy parser: percent-encoding, dấu gạch chéo lặp, dấu chấm trong đường dẫn, chữ hoa/thường, ký tự Unicode hoặc các dấu phân tách đặc biệt.

### 8.1. Rủi ro do proxy và backend hiểu path khác nhau

Nếu reverse proxy chặn một path nhưng backend giải mã, chuẩn hóa hoặc định tuyến path theo quy tắc khác, một request có thể vượt qua dự định ban đầu. Cùng loại sai lệch có thể xuất hiện khi proxy rewrite URL mà backend lại áp dụng ACL dựa trên path ban đầu.

**Nguyên tắc:** cùng một request phải được hiểu một cách nhất quán bởi các lớp thực thi security policy, hoặc phải bị từ chối nếu dạng biểu diễn mơ hồ.

### 8.2. Method và request body

Không tự cho rằng GET là an toàn về mặt authorization hoặc POST luôn là độc hại. HTTP method giúp xác định thao tác nhưng **quyền nghiệp vụ và kiểm tra dữ liệu vẫn ở ứng dụng**.

Proxy cần đặt giới hạn về:

- **Request line/headers/body size** theo nhu cầu dịch vụ.
- Thời gian đọc header/body, request timeout và số kết nối đồng thời.
- Các method được ứng dụng sử dụng; từ chối những method không được hỗ trợ khi phù hợp.
- Header trùng lặp/không hợp lệ và quy tắc canonicalization.
- Upload, streaming và trường hợp body lớn cần xử lý có kiểm soát.

Một policy kiểm tra kích thước cần phối hợp với backend: proxy không nên chấp nhận payload mà backend không thể xử lý một cách an toàn hoặc ngược lại gây lỗi bất ngờ cho client hợp lệ.

## 9. Authentication và authorization tại ranh giới proxy

### 9.1. Xác thực tại gateway có ích gì?

Reverse proxy hoặc API gateway có thể kiểm tra **session cookie, access token, client certificate hoặc kết quả từ IdP** trước khi route request. Nhờ vậy những request không xác thực bị chặn sớm, giảm tải backend và đặt được chính sách nhất quán.

Nhưng cần kiểm tra chính xác:

1. Credential đến từ đâu và đã được xác minh chưa?
2. Token có đúng **issuer, audience, signature, expiry** và những claim bắt buộc không?
3. Proxy có áp dụng policy cho **mọi route nhạy cảm**, kể cả route lỗi, default route, WebSocket/gRPC và đường bypass?
4. Backend có kiểm tra **quyền theo tài nguyên/nghiệp vụ** hay chỉ tin proxy?

### 9.2. Internal identity headers

Một số kiến trúc đưa user ID/role từ proxy tới backend bằng header nội bộ. Nếu làm như vậy:

- Proxy phải **loại bỏ hoặc ghi đè những header cùng tên do client gửi**.
- Chỉ đưa dữ liệu sau khi **AuthN/claim validation** thành công.
- Phải bảo vệ **proxy → backend** bằng private network, ACL, TLS/mTLS và chống đường bypass.
- Backend phải nhận biết chỉ những proxy được ủy quyền mới có quyền cấp ngữ cảnh này.
- Không gửi bí mật hoặc toàn bộ token khi không cần thiết; hạn chế dữ liệu nhạy cảm.

Ví dụ, header nội bộ **X-Verified-User: user-42** chỉ đáng tin nếu backend không cho client Internet trực tiếp gửi header đó và có cơ chế ràng buộc nguồn phù hợp.

### 9.3. Service identity khác user identity

Một backend dùng mTLS có thể xác minh **gateway-service** là client TLS. Điều đó chứng minh kết nối tới từ một thành phần đã được cấp chứng thư, **không tự chứng minh người dùng cuối là user-42**.

Mô hình hoàn chỉnh thường cần **service-to-service authentication** và **user-context propagation** được xác minh độc lập. Chỉ khi ứng dụng hiểu cả hai, nó mới có thể thực hiện quyền nghiệp vụ an toàn.

### 9.4. Tránh nhầm access policy với business logic

Cho phép một người gọi **GET /orders/42** qua gateway không đảm bảo họ được phép đọc đơn hàng 42. Gateway có thể giới hạn dịch vụ/route, nhưng ứng dụng cần kiểm tra **ownership, tenant, vai trò và quyền trên bản ghi** để tránh lỗi BOLA/IDOR.

## 10. Header, cookie, redirect và chính sách trình duyệt

Reverse proxy có thể bổ sung hoặc biến đổi các HTTP response headers, nhưng phải rõ **ai là chủ sở hữu từng chính sách**.

| Kiểm soát | Mục tiêu | Lỗi thường gặp |
| --- | --- | --- |
| **Strict-Transport-Security (HSTS)** | Hướng browser dùng HTTPS cho hostname theo quy tắc | Bật phạm vi includeSubDomains không đánh giá tác động các subdomain |
| **Content-Security-Policy (CSP)** | Giảm một số kiểu tải/thi hành nội dung không mong muốn | Rule quá rộng hoặc khác chức năng ứng dụng |
| **X-Content-Type-Options** | Hạn chế MIME sniffing trong tình huống được hỗ trợ | Coi header này là giải pháp thay việc phục vụ MIME đúng |
| **Cookie Secure** | Chỉ gửi cookie qua kênh được browser xem là bảo mật | Backend dùng sai X-Forwarded-Proto tạo cookie không như dự kiến |
| **Cookie HttpOnly** | Giảm truy cập cookie bằng JavaScript | Không bảo vệ khỏi mọi kiểu chiếm phiên |
| **SameSite / CSRF defenses** | Hạn chế một số cross-site request | Coi SameSite thay thế mọi kiểm tra CSRF/authorization |
| **CORS** | Điều khiển browser cho phép trang ở origin khác đọc response trong một số trường hợp | Nhầm CORS là firewall hoặc xác thực API |
| **Redirect Location** | Đưa client tới URL đúng | Dùng Host/X-Forwarded-Host không tin cậy tạo open redirect |

### 10.1. CORS không phải kiểm soát mạng truy cập

CORS là cơ chế áp dụng chủ yếu trong **trình duyệt** khi script muốn đọc response cross-origin. Nó **không ngăn một HTTP client ngoài browser gửi request đến API**, cũng không thay thế authentication/authorization.

Nếu reverse proxy trả **Access-Control-Allow-Origin** dựa trên header Origin mà không kiểm soát danh sách được phép, có thể vô tình cho phép trang không mong muốn đọc dữ liệu của người dùng trong một số bối cảnh. Quy tắc credentials và wildcard phải được áp dụng đúng theo chuẩn/cấu hình.

### 10.2. Cookie và scheme

Nếu browser kết nối HTTPS đến proxy nhưng backend nhận HTTP và tự suy rằng scheme là HTTP, ứng dụng có thể tạo redirect hoặc cookie flags sai. Cần một cách **chuẩn hóa scheme đáng tin** tại proxy, để backend không phải tin X-Forwarded-Proto do Internet client tự gửi.

### 10.3. Đừng làm mất security headers khi xử lý lỗi

Proxy có thể tự tạo 4xx/5xx, redirect hoặc cache response; những response này cũng cần được xem xét đối với header bảo mật, nội dung lỗi và dữ liệu nhạy cảm. Không chỉ kiểm tra security headers của trang thành công 200.

## 11. HTTP parsing và request desynchronization

### 11.1. Vì sao nhiều parser có thể là vấn đề?

Reverse proxy và backend có thể dùng **những bộ phân tích HTTP khác nhau**. Nếu hai thành phần không đồng ý về ranh giới một request, kích thước body, header framing hoặc cách chuyển đổi giữa HTTP/1.1 và HTTP/2, có thể xảy ra **HTTP request desynchronization**, trong đó một chuỗi dữ liệu được hiểu khác nhau ở hai đầu.

Nhóm rủi ro này thường được nhắc cùng thuật ngữ **HTTP request smuggling**, nhưng không nên coi mọi lỗi parse là một cuộc tấn công. Những sai lệch cũng có thể gây 400/502, đóng kết nối hoặc ứng dụng đọc body sai.

### 11.2. Các điểm bất nhất cần phòng vệ

- Phân tích **Content-Length, Transfer-Encoding** và framing của HTTP/1.1.
- Header trùng lặp, dấu cách hoặc ký tự không hợp lệ.
- Chuyển đổi HTTP/2/HTTP/3 sang HTTP/1.1 ở gateway.
- Cách xử lý connection reuse, keep-alive, chunked encoding và body streaming.
- Không nhất quán giữa WAF parser, proxy parser và backend framework.

### 11.3. Nguyên tắc giảm thiểu

1. Dùng phiên bản proxy/backend được bảo trì và đã cập nhật bản vá.
2. **Từ chối request mơ hồ hoặc không đúng chuẩn**, thay vì cố đoán cách diễn giải có lợi cho client.
3. Chuẩn hóa header/framing theo khả năng sản phẩm và tuân thủ HTTP specifications.
4. Kiểm thử những biến thể giao thức được hệ thống **thật sự hỗ trợ**: HTTP/1.1, HTTP/2, HTTP/3, WebSocket, gRPC.
5. Hạn chế đường backend trực tiếp; kiểm tra timeout, connection reuse và trường hợp hủy giữa chừng.
6. Theo dõi bất thường về 400/431/502, parser errors, request count và log theo request ID.

**Không dùng các payload gây desynchronization để thử trên mạng sản xuất/bên thứ ba khi chưa có phạm vi kiểm thử được phê duyệt.** Với đào tạo phòng vệ, có thể sử dụng nhật ký giả lập và unit/integration tests trong lab cô lập.

## 12. WAF, IDS/IPS và giới hạn kiểm tra HTTP

**Web Application Firewall (WAF)** thường hoạt động sau khi có thể nhìn thấy HTTP request ở lớp ứng dụng. WAF hỗ trợ phát hiện/chặn một số mẫu đầu vào bất thường nhưng **không thay thế** xác thực nguồn của header, truy cập theo user/tenant hoặc kiểm tra quyền trong backend.

| Lớp | Nhìn thấy gì? | Đóng góp |
| --- | --- | --- |
| Network firewall | IP, port, zone và những thuộc tính phù hợp thiết bị | Giới hạn đường tới proxy/backend |
| Reverse proxy/API gateway | TLS, HTTP path, header, routing, identity nếu được cấu hình | Áp chính sách tại điểm vào |
| WAF | HTTP request/response tùy triển khai và giải mã | Phát hiện/chặn một số mẫu đầu vào không an toàn |
| IDS/IPS | Lưu lượng hoặc sự kiện tùy điểm quan sát | Cảnh báo/chặn một số dấu hiệu xâm nhập |
| Application | Người dùng, tenant, bản ghi và logic nghiệp vụ | Kiểm tra authorization và validation theo ngữ cảnh |
| SOC/SIEM | Sự kiện tổng hợp nhiều lớp | Điều tra, tương quan và phản ứng |

### 12.1. TLS làm thay đổi điểm quan sát

Một IDS trên đoạn Internet → reverse proxy có thể không thấy payload HTTPS nếu không có quyền giải mã. Trong khi đó WAF tích hợp tại TLS termination có thể xem request rõ hơn. **Không mặc định mọi thiết bị bảo mật mạng nhìn thấy cùng một nội dung**.

### 12.2. WAF false positive

Một quy tắc WAF quá chặt có thể từ chối request hợp lệ, ví dụ API gửi JSON lớn hoặc ký tự đặc biệt đúng nghiệp vụ. Do đó cần **bật quan sát trước**, điều chỉnh theo endpoint và có cơ chế rollback. Không vì một false positive mà tắt toàn bộ bảo vệ.

## 13. Rate limiting và chống lạm dụng tại trust boundary

Reverse proxy thường là vị trí thuận lợi để giới hạn **tốc độ request, số kết nối đồng thời, dung lượng dữ liệu và những hành vi lặp lại** trước khi chúng đến backend. Nhưng một chính sách rate limit kém thiết kế có thể làm gián đoạn người dùng hợp lệ hoặc dễ bị vượt qua.

### 13.1. Chọn khóa định danh để giới hạn

Các khóa thường gặp:

| Khóa giới hạn | Ưu điểm | Rủi ro / lưu ý |
| --- | --- | --- |
| **IP của peer trực tiếp** | Dễ quan sát ở socket của proxy | Nếu có CDN, đây là IP CDN; nhiều client có thể chung một IP |
| **Client IP đã xác minh theo trusted proxy chain** | Gần với nguồn client hơn khi hạ tầng có nhiều hop | Cần chống giả mạo header, xử lý NAT/CGNAT và IPv6 |
| **User ID đã xác thực** | Giới hạn theo người dùng | Không áp dụng cho request chưa đăng nhập; cần bảo đảm user ID không do client tự khai |
| **API key / client identity** | Hữu ích với API và service-to-service | Phải được xác minh, có cơ chế thu hồi và tránh đưa key vào log |
| **Endpoint hoặc route** | Phân biệt login, upload, public API và health endpoint | Nên kết hợp với identity để tránh chặn nhầm |
| **Global pool / service capacity** | Bảo vệ backend khỏi quá tải tổng thể | Không thay thế per-client fairness |

**Không áp dụng “một IP = một người dùng”** trong mọi trường hợp. Nhiều người ở cùng doanh nghiệp, nhà mạng di động hoặc mạng khách có thể chia sẻ NAT; một người cũng có thể đổi IP theo kết nối.

### 13.2. Cơ chế thường dùng

- **Token bucket/leaky bucket** hoặc những thuật toán tương đương để quản lý tốc độ.
- **Connection limit** cho mỗi nguồn/nhóm hoặc toàn dịch vụ.
- **Concurrency limit** cho những endpoint tốn tài nguyên.
- **Request body size, header size và timeout** phù hợp với nghiệp vụ.
- **Queue/backpressure** để backend không bị nhận vượt năng lực.
- **Circuit breaker, retry budget và load shedding** trong hệ thống có hỗ trợ.

Những khái niệm trên không đồng nghĩa cùng một thuật toán trên mọi proxy. Cần đo đặc tính thật, nhất là dịch vụ có long polling, file upload, streaming hoặc WebSocket.

### 13.3. Lỗi do retry storm

Khi backend chậm, proxy, API client và service mesh có thể **đồng thời retry**, làm số request tăng thêm thay vì giảm tải. Nếu mỗi lớp retry không giới hạn, sự cố nhỏ có thể biến thành quá tải lớn.

Cần xác định:

1. Request **idempotent** hay có tác dụng phụ? Không retry tùy tiện thao tác thanh toán hoặc ghi dữ liệu.
2. Có **timeout tổng** và giới hạn số lần retry không?
3. Có exponential backoff/jitter theo năng lực sản phẩm không?
4. Circuit breaker có mở đúng mức khi backend suy giảm không?
5. Log có thể phân biệt request ban đầu với retry không?

### 13.4. DDoS protection cần nhiều tầng

Reverse proxy có thể hỗ trợ giảm HTTP flood ở lớp ứng dụng, nhưng không thể tự chống một cuộc tấn công bão hòa băng thông **trước khi traffic tới được proxy**. Cần phối hợp upstream/CDN DDoS protection, network firewall, capacity, anycast hoặc giải pháp khác theo kiến trúc.

Nếu hệ thống dùng CDN, phải bảo vệ origin để tránh việc client gửi trực tiếp tới proxy/backend và **đi vòng qua rate limit/WAF ở CDN**.

## 14. Cân bằng tải, health checks và chọn backend

Reverse proxy có thể phân phối request giữa nhiều instance backend để tăng khả dụng. Các thuật toán thường gặp gồm **round robin, least connections, weighted routing, hashing** và nhiều biến thể.

### 14.1. Load balancing không tự là authorization

Một pool chỉ nên chứa backend **cùng vai trò và cùng mức tin cậy dữ liệu**. Nếu nhầm một instance quản trị vào pool public API hoặc route giữa tenant A và tenant B, traffic có thể đến sai tài nguyên dù kết nối TLS và load balancing hoạt động.

| Khái niệm | Mục tiêu | Liên quan ranh giới tin cậy |
| --- | --- | --- |
| **Pool membership** | Xác định backend được phép phục vụ dịch vụ | Không cho endpoint lạ tự thêm vào pool |
| **Health check** | Phát hiện backend có thể nhận traffic | Health check pass không chứng minh backend đáng tin |
| **Weights** | Phân phối lưu lượng theo capacity/chiến lược | Sai weight có thể làm quá tải hoặc đưa traffic tới môi trường thử nghiệm |
| **Session affinity/sticky sessions** | Giữ một số client với một backend trong thời gian nhất định | Không được dùng cookie affinity làm bằng chứng xác thực danh tính |
| **Failover** | Chuyển khi backend lỗi | Backend dự phòng phải có cùng policy, cert và dữ liệu phù hợp |
| **Service discovery** | Cập nhật endpoint động | Phải xác thực nguồn danh sách endpoint và bảo vệ quyền thay đổi |

### 14.2. Health check là kiểm tra sức khỏe, không phải bằng chứng an toàn

Một HTTP **200 OK** ở đường **/health** có thể chứng minh process còn phản hồi, nhưng không chứng minh nó đã được cập nhật bản vá, có chứng thư đúng hoặc không bị chiếm quyền. Health check cũng cần được giới hạn thông tin trả ra, tránh lộ trạng thái cơ sở dữ liệu, secret hoặc cấu trúc hạ tầng.

Một số hệ thống phân biệt **liveness** và **readiness**; backend có thể còn sống nhưng chưa sẵn sàng nhận request. Quy trình failover nên dựa trên khả năng phục vụ thật và có thời gian chờ tránh flapping.

### 14.3. Retry, sticky sessions và dữ liệu người dùng

Nếu reverse proxy retry request tới một backend khác sau timeout, request ghi dữ liệu có thể đã được backend đầu xử lý dù client chưa nhận response. **Retry không có cơ chế idempotency có thể tạo tác dụng phụ trùng lặp.**

Sticky sessions giúp một số ứng dụng kế thừa trạng thái nhưng không thay thế cơ chế quản lý session an toàn. Một cookie do proxy dùng để định tuyến không nên được hiểu là bằng chứng quyền truy cập đến dữ liệu.

### 14.4. Lỗi fail-open trong upstream routing

Khi một upstream không còn healthy, proxy không nên âm thầm gửi request tới **dịch vụ không cùng chức năng hoặc môi trường khác** chỉ để tránh 503. Một lỗi khả dụng có thể ít nghiêm trọng hơn việc vô tình gửi dữ liệu production tới backend thử nghiệm.

## 15. Caching là một trust boundary riêng

Reverse proxy hoặc CDN có thể cache response để tăng hiệu năng. Cache tạo một ranh giới mới: **response được tạo cho request/user này có được phép phục vụ cho request/user khác không?**

### 15.1. Những tình huống lộ dữ liệu

- Response cá nhân chứa thông tin người dùng bị cache như một trang công khai.
- Cache key không phân biệt **Host/tenant** trong hệ thống nhiều domain.
- Backend gửi response phụ thuộc **Authorization/Cookie** nhưng proxy cấu hình cache quá rộng.
- Một request với header/query khác biệt bị chuẩn hóa sai dẫn đến cache poisoning.
- Redirect hoặc 404/500 chứa thông tin nhạy cảm bị lưu lại không mong muốn.
- CDN và reverse proxy dùng quy tắc **Vary/Cache-Control** không nhất quán.

### 15.2. Mô hình cache key

Một cache key có thể phụ thuộc **scheme, hostname, path, query** và các yếu tố khác do ứng dụng yêu cầu. Không có một công thức cache key chung an toàn cho mọi ứng dụng. Đặc biệt, nếu nội dung khác nhau theo người dùng, tenant hoặc permission, cần có chính sách **không cache ở shared cache** hoặc thiết kế phân vùng/cache key được kiểm chứng.

**Đừng xem việc cache key có username là đủ** nếu identity đó đến từ header chưa được xác minh, hoặc nếu một người có nhiều mức quyền thay đổi theo thời gian.

### 15.3. Nguyên tắc phòng vệ

| Loại nội dung | Chính sách thường phù hợp | Lưu ý |
| --- | --- | --- |
| Static assets công khai, có version | Cache có thời hạn rõ | Bảo đảm không chứa dữ liệu người dùng hoặc token |
| Tài nguyên động công khai | Cache theo quy tắc ứng dụng, xác minh cache key | Kiểm tra Host/query/Vary và invalidation |
| API trả thông tin cá nhân | Thường không cho shared cache lưu nếu không có thiết kế riêng | Authorization/Cookie và quyền có thể thay đổi |
| Trang quản trị | Giới hạn cache mạnh, đặc biệt shared cache | Không lưu credential hoặc response nhạy cảm |
| Redirect và response lỗi | Xác định rõ có cache hay không | Tránh cache URL sai hoặc thông tin nhạy cảm |

### 15.4. Vì sao WAF không đủ bảo vệ cache?

Một WAF có thể thấy request không có mẫu tấn công rõ ràng, nhưng cache vẫn phục vụ dữ liệu cho sai người vì **khác biệt về cache key hoặc response headers**. Cần kiểm thử trực tiếp việc response giữa hai user/tenant **không bị trộn lẫn**.

## 16. WebSocket, gRPC, HTTP/2 và các loại kết nối đặc biệt

Không phải mọi traffic qua reverse proxy đều là request-response HTTP/1.1 đơn giản.

### 16.1. WebSocket

WebSocket thường bắt đầu bằng cơ chế handshake HTTP rồi chuyển sang một kết nối hai chiều kéo dài. Proxy cần xử lý upgrade/routing và timeout phù hợp.

Những rủi ro:

- Xác thực ở lúc mở kết nối nhưng **token/quyền thay đổi** trong khi socket còn hoạt động.
- Dùng **Origin** như thể nó là bằng chứng xác thực người dùng; Origin là tín hiệu hữu ích với browser nhưng không phải authentication.
- Bỏ kiểm tra authorization ở từng hành động/message nhạy cảm trong ứng dụng.
- Mở timeout vô hạn hoặc thiếu giới hạn số kết nối, dễ gây kiệt tài nguyên.

### 16.2. gRPC và HTTP/2

gRPC thường sử dụng HTTP/2 và những khái niệm như **service/method**, metadata và streaming. Nếu một gateway chuyển đổi giao thức, cần xác minh:

- Mapping **:authority, :path, content-type và metadata** đúng backend.
- Header danh tính đã được chuẩn hóa và kiểm tra nguồn.
- Timeout/deadline, max message size, flow control và retry được kiểm soát.
- Các RPC methods nhạy cảm có authorization phù hợp, không chỉ chặn theo URL path ở HTTP/1.1.

### 16.3. HTTP/3 và QUIC

HTTP/3 dùng QUIC qua UDP, còn HTTP/1.1/HTTP/2 thường qua TCP/TLS theo mô hình liên quan. Nếu CDN nhận HTTP/3 rồi chuyển HTTP/2 hoặc HTTP/1.1 vào origin, **ranh giới chuyển đổi giao thức** cần được kiểm thử về header, authority, body framing, cache và logging.

Không suy rằng chỉ cấu hình kiểm tra ở TCP 443 đã bao phủ toàn bộ traffic nếu hệ thống còn phục vụ **UDP 443/HTTP/3**.

### 16.4. Streaming/upload

Streaming hoặc upload lớn đòi hỏi timeout và buffer khác request nhỏ. Một rule body size quá chặt có thể gây false positive; quá rộng có thể gây áp lực bộ nhớ/đĩa. Cần có quota theo service, request type và identity, đồng thời bảo vệ đường tới backend.

## 17. CDN, cloud load balancer và Kubernetes ingress

### 17.1. Nhiều lớp reverse proxy

Một triển khai cloud có thể có **CDN → public load balancer → ingress controller → service mesh gateway → application**. Mỗi hop có thể thêm forwarding headers, tạo kết nối TLS mới và áp dụng policy riêng.

~~~mermaid
flowchart LR
    CLIENT["External client"] --> CDN["CDN / WAF"]
    CDN --> ALB["Cloud Load Balancer"]
    ALB --> ING["Kubernetes Ingress / Gateway"]
    ING --> SVC["Service mesh / backend"]
    CDN -. "Trusted IP chain" .-> ALB
    ALB -. "Identity + route metadata" .-> ING
    ING -. "Service authn + authz" .-> SVC
    K["IAM / GitOps / Change Control"] --> CDN
    K --> ALB
    K --> ING
~~~

Không nên mặc định CDN/WAF là lớp duy nhất có thẩm quyền; nếu cloud load balancer có public IP độc lập mà Internet có thể truy cập, client có thể **bỏ qua CDN**. Cần đánh giá origin protection qua **private connectivity, firewall/source restrictions, mTLS hoặc cơ chế xác minh nguồn được nhà cung cấp hỗ trợ**.

### 17.2. Ingress và Gateway API

Trong Kubernetes, Ingress/Gateway có thể route theo hostname/path tới Service. Một lỗi cấu hình có thể mở public route tới service vốn chỉ dành cho nội bộ.

Điểm cần kiểm soát:

- Quyền tạo/sửa **Ingress, Gateway, HTTPRoute hoặc cấu hình tương đương**.
- Tên host hợp lệ và quyền sở hữu route; nhiều team/namespace có thể cùng tham gia.
- **Reference grants/route attachment** và những giới hạn liên namespace theo phiên bản sản phẩm.
- TLS secrets và quyền đọc/sửa chứng thư.
- NetworkPolicy, service mesh authorization và backend service exposure.
- Chế độ mặc định khi route không khớp host/path.

**Có Kubernetes NetworkPolicy hoặc Ingress rule không tự chứng minh đường backend đã kín**; tính năng thực thi và behavior phụ thuộc CNI/controller, cloud LB và cấu hình cụ thể.

### 17.3. Dynamic service discovery

Nếu pool backend lấy từ DNS, registry hoặc orchestrator, cần xác minh **ai có quyền sửa bản ghi/discovery data** và endpoint đó có thực sự thuộc workload cần phục vụ. TLS/mTLS với service identity góp phần giảm nguy cơ gửi traffic tới backend không được phê duyệt nếu dữ liệu discovery bị sai.

### 17.4. Multi-tenant boundary

Trong môi trường SaaS, Host/path có thể quyết định tenant. Không chỉ dựa vào **hostname được client gửi** để cấp quyền đọc dữ liệu; backend cần ràng buộc tenant theo identity/token hoặc mapping server-side. Một client của tenant A không được phép đổi Host hoặc tham số URL để truy cập dữ liệu tenant B.

## 18. DNS, IPv4/IPv6 và tránh đường bypass

### 18.1. DNS không phải chính sách bảo mật

Ẩn hostname backend khỏi DNS công khai hoặc đặt tên “internal” **không đủ** để ngăn truy cập. IP, load balancer khác hoặc route từ đối tác vẫn có thể dẫn tới backend.

Phải bảo vệ bằng firewall/security groups, network policy, authentication và kiểm soát cụ thể tại origin. DNSSEC có thể xác thực dữ liệu DNS được ký theo chuỗi tin cậy, **không thay thế kiểm soát vào backend**.

### 18.2. IPv6 bypass

Một backend được khóa public IPv4 nhưng vẫn có public IPv6 và rule mở có thể tạo đường bypass. Kiểm thử cần bao gồm:

- DNS A/AAAA cho hostname public và origin.
- Firewall/security group cho cả IPv4 và IPv6.
- Listener và route trên từng address family.
- TLS, Host routing, IP allowlist và mTLS trên từng đường.

Không kết luận backend không thể truy cập từ Internet chỉ vì một phép thử IPv4 không thành công.

### 18.3. Side doors và alternate endpoints

Những đường đi phụ cần xem:

- Load balancer cũ chưa gỡ.
- NodePort hoặc service type public ngoài ý định trong container platform.
- VPN/bastion/partner network có quyền rộng tới backend.
- Health/debug/admin endpoint được public ngoài kế hoạch.
- HTTP origin port vẫn mở dù HTTPS public route đã được bảo vệ.
- Disaster recovery site hoặc failover region có policy yếu hơn.

**Một control plane thay đổi có thể tạo đường bypass mà không cần tấn công vào reverse proxy.** Vì vậy hạ tầng cần inventory và kiểm soát cấu hình như code (IaC) hoặc phương pháp tương đương.

## 19. Kiểm soát quản trị reverse proxy

Khi reverse proxy định tuyến và xác thực traffic của nhiều dịch vụ, quyền sửa cấu hình proxy trở thành **quyền bảo mật có phạm vi rộng**.

### 19.1. Những tài sản nhạy cảm

- **Private keys và TLS certificates** của public endpoints và upstream mTLS.
- API tokens để truy cập CDN, cloud LB, controller hoặc certificate manager.
- File cấu hình virtual host, route map, access policy và WAF rules.
- Danh sách trusted proxy ranges, nguồn metadata và IP allowlists.
- Secrets dùng để xác minh session, ký token hoặc kết nối IdP.
- Hệ thống log có chứa metadata người dùng, truy cập và audit.

### 19.2. Quy tắc quản trị

1. **Least privilege** cho người có thể đổi route, trust headers và certificate.
2. Dùng SSO/MFA cho dashboard hoặc API quản trị khi hỗ trợ.
3. Có review và change ticket cho thay đổi Host/path, trusted sources, origin pool và authentication exemptions.
4. Bảo vệ secrets trong secret manager/hệ thống được duyệt, không đưa private key vào repository, log hoặc ticket.
5. Tự động kiểm tra syntax/config test, routing behavior và policy trước khi triển khai.
6. Ghi **policy/config version** vào telemetry để truy ngược sự kiện.
7. Tách môi trường test/production, có canary hoặc staged rollout và rollback.

### 19.3. Vì sao “reload thành công” chưa đủ?

Proxy có thể reload cấu hình mà không lỗi cú pháp nhưng vẫn **route /admin tới backend public**, đặt mọi trusted proxies thành all-addresses hoặc tắt xác minh TLS upstream. Thành công về mặt cú pháp không chứng minh đúng **mục tiêu bảo mật**.

## 20. Mẫu chính sách trust boundary trung lập với sản phẩm

Đoạn YAML dưới đây mô tả **ý định bảo mật**, không phải cấu hình có thể áp dụng trực tiếp lên Nginx, Envoy, HAProxy, Apache, Traefik, API gateway, cloud LB hoặc Kubernetes.

~~~yaml
reverseProxyTrustBoundary:
  name: public-api-edge
  environment: isolated-training
  publicEntry:
    allowedHosts:
      - app.example.test
      - api.example.test
    allowedSchemes: [https]
    unknownHostAction: reject
    defaultRouteAction: reject
    requireValidTlsServerCertificate: true
  trustedProxyChain:
    topology: client-to-cdn-to-edge-to-backend
    ingressPeerAllowlist: managed-by-network-team
    acceptForwardingHeadersOnlyFrom: verified-upstream-proxies
    discardUntrustedIncomingIdentityHeaders: true
    normalizeForwardedFor: using-product-specific-trusted-hop-algorithm
    normalizeOriginalSchemeAndHost: true
    denyDirectOriginAccess: true
  requestValidation:
    rejectMalformedOrAmbiguousHttp: true
    normalizeHostAndPathConsistently: true
    restrictUnsupportedMethods: true
    limitHeaderAndBodySize: per-service-baseline
    protectHttpProtocolConversion: true
  authentication:
    approvedIdentitySource: enterprise-idp
    validateTokenSignatureIssuerAudienceExpiry: true
    failClosedForProtectedRoutes: true
    requireApplicationAuthorization: true
    verifiedUserHeader:
      enabled: only-after-authentication
      overwriteClientSuppliedValue: true
      channelToBackend: private-network-plus-tls-or-mtls
  upstream:
    allowedBackends: service-registry-with-change-control
    requireTlsWhenPolicyRequires: true
    verifyBackendCertificate: true
    verifyBackendServiceName: true
    allowDirectDatabaseRouting: false
    verifyFailoverPolicyConsistency: true
  abuseControls:
    rateLimitKey: verified-client-context
    separateLoginAndGeneralApiLimits: true
    enforceConcurrencyAndSizeLimits: true
    protectRetryBudget: true
  caching:
    publicAssets: approved-only
    sensitiveResponses: no-shared-cache
    verifyTenantAndHostIsolation: true
    honorApplicableCacheControl: true
  observability:
    recordRequestAndTraceIds: true
    recordVerifiedAndPeerIpSeparately: true
    recordRouteAndPolicyVersion: true
    monitorUpstreamTlsErrors: true
    redactSecretsAndPersonalData: true
  governance:
    requireApprovedChanges: true
    verifyIpv4AndIpv6Exposure: true
    testNegativeRoutesAndHeaderSpoofing: true
    keepRollbackPlan: true
~~~

Các trường như **normalizeForwardedFor** chỉ thể hiện yêu cầu. Một hệ thống thực tế phải định nghĩa **cụ thể mạng proxy đáng tin, thuật toán chọn IP thật, hành vi với header mơ hồ và nơi thực thi**. Nếu đặt nhầm một tập IP quá rộng vào trusted sources, chính sách có thể suy yếu thay vì được bảo vệ.

## 21. Ví dụ xử lý request ở mức giả mã phòng vệ

Giả mã sau dùng để giải thích **thứ tự ra quyết định**, không phải mã cấu hình triển khai hoặc logic thay thế một HTTP parser đã được kiểm thử:

~~~text
function handleIncomingRequest(connection, request):
    require connection.entrypoint in ApprovedPublicListeners
    require request.protocol is supported and unambiguous

    tlsIdentity = validatedPublicEndpointIdentity(connection)
    require tlsIdentity matches approvedPublicHostPolicy

    requestedHost = normalizeAndValidateAuthority(request)
    require requestedHost in ApprovedHosts

    peer = connection.immediatePeerAddress
    if peer is an authenticated, configured upstream proxy:
        clientContext = extractClientContextUsingTrustedProxyPolicy(request)
    else:
        clientContext = contextFromDirectConnection(peer)

    removeClientSuppliedInternalIdentityHeaders(request)
    removeOrNormalizeUntrustedForwardingHeaders(request)

    route = authorizeHostPathMethodRouting(requestedHost, request.path, request.method)
    require route exists and route is approved

    if route.requiresLogin:
        user = validateIdentityCredential(request)
        require user authenticated and authorized for gateway policy
        attachVerifiedIdentityContextForBackend(user)

    applyRateLimitAndResourceBounds(route, clientContext)
    selectHealthyApprovedBackend(route)
    connectUpstreamWithRequiredTlsAndServiceIdentityValidation()
    forwardNormalizedRequest()

    enforceResponseAndCachePolicy(route)
    emitStructuredAuditEventWithoutSecrets()
~~~

**Những kiểm tra trong giả mã không luôn chạy tuyến tính như vậy.** Ví dụ TLS handshake xảy ra trước khi HTTP request được đọc; rate limiting có thể áp dụng trước xác thực để bảo vệ login endpoint; kiểm tra ứng dụng tiếp tục sau khi backend nhận request. Điều phải giữ là **nguồn nào có thẩm quyền quyết định dữ liệu nào**, không phải vị trí của từng dòng giả mã.

### 21.1. Cách đọc giả mã

**immediatePeerAddress** là địa chỉ phía kết nối trực tiếp tới reverse proxy; không phải “IP người dùng cuối” trong mọi topology. **validatedPublicEndpointIdentity** là chứng thư/danh tính TLS được trình bày trên điểm vào phù hợp. **ApprovedHosts** là danh sách chính thức đã được cấu hình, không lấy từ Host do client tự gửi.

### 21.2. Khi proxy nằm sau CDN

Nếu CDN là upstream duy nhất được phép, proxy cần nhận diện kết nối đến từ **đường CDN thật sự được quản lý**. IP/CDN token hoặc dữ liệu mTLS cần được cấu hình theo năng lực nhà cung cấp và cập nhật khi dải IP/kiến trúc thay đổi. Không đơn giản lấy toàn bộ địa chỉ công cộng thành “trusted CDN” rồi tin header.

## 22. Logging, metrics và observability xuyên proxy–backend

### 22.1. Các trường log nên có

| Nhóm | Trường hữu ích | Ý nghĩa |
| --- | --- | --- |
| Request metadata | Timestamp, request ID, trace ID, method, normalized route | Liên kết sự kiện nhiều tầng |
| Network | Peer IP, verified client IP, protocol, TLS version | Phân biệt peer với IP từ forwarding headers |
| Routing | Requested Host, effective host, upstream pool, backend instance | Xem request đi đúng dịch vụ không |
| Security policy | AuthN result, gateway role, rule ID, WAF/rate-limit decision | Biết lớp nào allow/deny |
| TLS upstream | Backend SNI/service identity, verify result, certificate expiry | Phát hiện bỏ xác minh hoặc cert lỗi |
| HTTP processing | Parser errors, 400/431/502, body/header bounds | Phát hiện không tương thích hoặc đầu vào bất thường |
| Availability | Upstream status, latency, retries, queue depth | Khoanh vùng overload/retry storm |
| Cache | Cache hit/miss, cache class, tenant isolation check | Điều tra response serving không đúng |
| Governance | Config version, change ticket, deployment timestamp | Liên hệ lỗi với thay đổi |

### 22.2. Log giả lập về header không tin cậy

~~~json
{
  "timestamp": "2026-11-28T17:10:00+07:00",
  "environment": "synthetic-training",
  "request_id": "edge-lab-req-002",
  "public_host": "api.example.test",
  "route": "/internal/metrics",
  "immediate_peer_ip": "198.51.100.40",
  "client_supplied_x_forwarded_for": "10.0.0.5",
  "verified_client_ip": "198.51.100.40",
  "upstream_peer_trusted": false,
  "gateway_policy": "deny-external-internal-metrics",
  "decision": "deny",
  "http_status": 403,
  "backend_reached": false,
  "dataset": "synthetic-training-event"
}
~~~

Log ghi rõ **IP client tự khai** không được chọn làm nguồn tin cậy. Trong môi trường thật, có thể cần **không lưu nguyên văn những header không tin cậy** nếu chúng chứa PII hoặc dữ liệu nhạy cảm; log ví dụ chỉ dùng dữ liệu giả lập.

### 22.3. Log giả lập về backend TLS

~~~json
{
  "timestamp": "2026-11-28T17:15:00+07:00",
  "environment": "synthetic-training",
  "request_id": "edge-lab-req-003",
  "backend_pool": "billing-service",
  "expected_backend_identity": "billing.internal.example.test",
  "presented_backend_identity": "other.internal.example.test",
  "tls_certificate_chain": "trusted-in-lab-pki",
  "backend_hostname_validation": "failed",
  "policy_action": "reject-upstream-connection",
  "client_status": 502,
  "application_request_forwarded": false,
  "dataset": "synthetic-training-event"
}
~~~

Trường hợp này minh họa **chứng thư có chuỗi CA được tin nhưng sai tên backend**. Việc từ chối chặng upstream là hành vi đúng theo policy; không tự chứng minh có kẻ tấn công, vì có thể do route hoặc certificate deployment sai.

### 22.4. Các cảnh báo có giá trị

- Bất thường **Host/:authority** ngoài danh sách được phép hoặc định tuyến default tăng.
- Tỷ lệ request có **forwarding headers đến từ untrusted peers** tăng.
- Thay đổi đột ngột tập **trusted proxy ranges** hoặc identity header mapping.
- Tăng lỗi upstream certificate validation sau đợt thay chứng thư.
- Gia tăng rate-limit violations đồng thời backend latency, queue/retries tăng.
- Phát hiện **direct origin access** không đi qua WAF/CDN theo đường dự kiến.
- Nhiều 400/431/502 liên quan malformed headers hoặc protocol conversion.
- Response cache bị phục vụ không đúng Host/tenant hoặc chứa dữ liệu cá nhân.

**Không coi một cảnh báo đơn lẻ là tấn công được xác nhận**; cần đối chiếu config, thay đổi có phê duyệt, backend logs và vị trí quan sát.

## 23. Quy trình triển khai reverse proxy như một ranh giới tin cậy

### Bước 1 – Kiểm kê nguồn/đích và quyền thay đổi

Liệt kê hostnames, public VIP, CDN, LB, ingress, backend pools, service identities, API routes, TLS endpoints, certificate owners và admin APIs. Xác định ai có quyền thay đổi **Host/path routing, nguồn trusted headers, upstream TLS verification** và WAF/rate limits.

### Bước 2 – Vẽ dữ liệu qua từng hop

Với mỗi hop, ghi:

- **TLS terminate hay passthrough?** Ai xác minh danh tính ai?
- Nguồn socket peer là gì? Ai có quyền gửi metadata IP?
- Header nào được nhận, xóa, tạo lại hoặc chuyển tiếp?
- Chính sách AuthN/AuthZ nằm ở đâu?
- Backend được chọn theo dữ liệu nào và ai có thể sửa mapping?
- Cổng/protocol nào được firewall cho phép?

### Bước 3 – Xác định các bất biến bảo mật

Ví dụ các yêu cầu phải luôn đúng:

1. Internet không thể truy cập **backend trực tiếp**.
2. Unknown Host không route tới một backend nhạy cảm.
3. Client tự khai **X-User-Role** hoặc **X-Forwarded-For** không được tin như dữ liệu đã xác minh.
4. Proxy chỉ kết nối **backend TLS đúng danh tính** theo policy.
5. Route nhạy cảm không được mặc định bỏ AuthN/AuthZ khi lỗi IdP.
6. Shared cache không phục vụ dữ liệu cá nhân giữa hai tài khoản/tenant.
7. IPv6 và failover region phải có policy tương đương với IPv4/primary.

### Bước 4 – Triển khai cấu hình tối thiểu trong lab

Kiểm tra certificate, route allowlist, header normalization, backend mTLS/TLS, firewall, auth gateway và basic telemetry. Đặt ngưỡng request/rate limit theo **baseline từ lưu lượng hợp lệ**, không suy đoán.

### Bước 5 – Kiểm thử cả đường allow và deny

Xác minh request hợp lệ đi qua đúng backend và request không hợp lệ **bị từ chối tại đúng layer**. Đặc biệt thử unknown Host, forged identity headers, backend TLS sai tên và trực tiếp truy cập origin trong lab.

### Bước 6 – Triển khai canary, giám sát và rollback

Thay đổi theo nhóm host, backend hoặc vùng. Có người chịu trách nhiệm, change ticket, config diff, bản sao chính sách cũ và phép thử nghiệp vụ sau reload. Không triển khai đồng loạt một rule không có đường rollback cho mọi dịch vụ.

### Bước 7 – Kiểm tra định kỳ

Đánh giá lại khi thêm CDN, thay cloud LB, di chuyển Kubernetes namespace, đổi mTLS CA, thêm tenant, cập nhật API route hoặc đổi proxy software. Một trust boundary đúng hôm nay có thể sai sau khi topology thay đổi.

## 24. Ma trận kiểm thử an toàn trong lab

Các phép thử dưới đây dành cho **proxy, client, backend và mạng thử nghiệm được cấp phép**; không nhắm vào hệ thống thật của người khác và không dùng kỹ thuật gây gián đoạn ngoài phạm vi. Mục tiêu là **xác minh chính sách và hành vi từ chối**, không khai thác.

| Mã | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| T-01 | Client dùng hostname hợp lệ và TLS hợp lệ, route public được phép | Đúng backend, response đúng, có request ID |
| T-02 | Request tới **unknown Host** trên listener public | Từ chối, không đưa tới default backend nhạy cảm |
| T-03 | Client lab tự đặt X-Forwarded-For thành IP nội bộ | Proxy không tin IP giả; IP dùng cho policy vẫn đúng |
| T-04 | Client lab tự đặt header X-Verified-User/X-User-Role | Proxy xóa/ghi đè, không tạo quyền admin |
| T-05 | Request vào protected route không có credential | Gateway deny, backend không xử lý nội dung nhạy cảm |
| T-06 | Credential hợp lệ nhưng user không có quyền đọc bản ghi khác | Application authorization deny |
| T-07 | Backend đưa chứng thư CA tin cậy nhưng SAN sai tên | Proxy từ chối TLS upstream |
| T-08 | Backend thiếu CA/trust anchor hoặc hết hạn cert | Chặng upstream bị từ chối theo policy |
| T-09 | Client thử đi **trực tiếp tới origin IP** trong lab | Firewall/ACL/chính sách origin deny |
| T-10 | CDN và edge proxy dùng trusted ranges đúng, cả IPv4/IPv6 | Client IP xác minh đúng, không tin header sai nguồn |
| T-11 | Một reverse proxy khác trong chuỗi bị gỡ hoặc thêm | Trusted proxy chain được cập nhật/kiểm tra trước rollout |
| T-12 | Path/method không thuộc routing allowlist | Từ chối, không tự đưa đến backend quản trị |
| T-13 | Request HTTP malformed/ambiguous trong bộ dữ liệu kiểm thử nội bộ | Bị từ chối nhất quán, parser không lệch giữa các lớp |
| T-14 | Login endpoint nhận burst request **được mô phỏng có giới hạn** | Rate-limit đúng, user lab hợp lệ không mất mạng rộng |
| T-15 | Một backend unhealthy, pool có instance dự phòng đúng policy | Failover đến backend hợp lệ, không đổi tenant |
| T-16 | Backend tất cả unhealthy | Trả lỗi có kiểm soát, không fallback tới dịch vụ khác chức năng |
| T-17 | Hai tài khoản/tenant truy cập response động cần phân quyền | Shared cache không trộn dữ liệu |
| T-18 | Static asset public có cache policy đúng | Cache hoạt động mà không lưu token hoặc dữ liệu riêng |
| T-19 | WebSocket/gRPC lab với method/resource nhạy cảm | AuthN/AuthZ và timeout áp dụng theo thiết kế |
| T-20 | HTTP/3/IPv6 và fallback edge | Chính sách route/TLS/Host tương đương những đường còn lại |
| T-21 | Proxy reload sau đổi CA/secret manager | Backend TLS verify vẫn hoạt động, không mở bypass |
| T-22 | Một thay đổi sai mapping Host → service trong lab | Phát hiện qua test, rollback đúng config version |

### 24.1. Cách ghi bằng chứng

Mỗi ca kiểm thử nên có:

1. **Topology**, môi trường và quyền sử dụng.
2. **Client, immediate peer, Host/SNI, protocol, headers liên quan** đã được làm sạch dữ liệu nhạy cảm.
3. **Policy/rule ID**, phiên bản cấu hình, route và upstream pool.
4. Trạng thái TLS public/upstream, identity mapping và kết quả AuthN/AuthZ.
5. Kết quả tại proxy, firewall và backend; không chỉ dựa HTTP status.
6. Tác động tới client hợp lệ, độ trễ và yêu cầu retry.
7. Kế hoạch rollback và tiêu chí pass/fail.

### 24.2. Vì sao một HTTP 403 chưa đủ chứng minh an toàn?

403 có thể đến từ WAF, gateway hoặc backend. Nếu muốn kiểm chứng proxy **chặn trước backend**, cần xác minh **backend không nhận request** bằng log/trace phù hợp. Tương tự, 502 khi upstream TLS lỗi chưa chứng minh kiểm tra hostname đúng nếu nguyên nhân thật là mất kết nối mạng.

### 24.3. Kiểm thử mà không gây xáo trộn dịch vụ

Những trường hợp như protocol parsing, retry storm hoặc rate-limit burst nên sử dụng **request mẫu, mô phỏng và môi trường cô lập**. Không thực hiện flood, phá kết nối hoặc thử các biến thể mơ hồ trên dịch vụ production nếu không có quy trình đánh giá và quyền được cấp.

## 25. Runbook: nghi ngờ reverse proxy bị vượt qua

Giả sử SOC nhận thấy backend API có request trực tiếp từ một địa chỉ ngoài danh sách gateway, đồng thời log ứng dụng ghi một user role lạ do header HTTP truyền vào.

### Giai đoạn 1 – Xác minh nguồn và tác động

1. Xác định **backend instance, IP đích, cổng, source IP**, thời gian và request ID.
2. So với topology: backend có **public endpoint, alternate LB, IPv6 listener, VPN/partner route hoặc service exposure** ngoài ý định không?
3. Kiểm tra request có thật đi qua reverse proxy hay không bằng trace/log hai bên.
4. Đọc policy/identity mapping: backend đang tin header nào và ai có quyền phát hành?
5. Đối chiếu change ticket/CDN migration/cloud routing gần nhất.
6. Xác định **dữ liệu hoặc quyền thực sự đã bị ảnh hưởng**, không suy đoán từ một header bất thường.

### Giai đoạn 2 – Khoanh vùng

- Hạn chế đường **trực tiếp tới backend** tại firewall/security group/network policy nếu được xác nhận không cần thiết.
- Thay đổi cấu hình backend để **không tin header danh tính do nguồn chưa xác thực gửi**.
- Kiểm tra TLS/mTLS proxy → backend, dịch vụ có quyền khác và các đường failover.
- Nếu nghi tài khoản quản trị proxy bị xâm nhập, thu hồi credential và giới hạn quyền theo quy trình incident response.
- Tránh chặn toàn bộ gateway nếu vẫn cần traffic hợp lệ; ưu tiên rule hẹp theo bằng chứng.

### Giai đoạn 3 – Sửa chính sách và kiểm thử

1. Thiết lập **trusted proxy list cụ thể** và xóa/ghi đè headers đến từ untrusted clients.
2. Cấu hình **unknown Host = reject**, không route đến default backend có dữ liệu.
3. Xác minh proxy không bỏ backend certificate verification.
4. Kiểm thử IPv4/IPv6, CDN bypass và alternate endpoints.
5. Dùng tài khoản lab để thử **allow đúng dịch vụ** và **deny đúng quyền**.
6. Kiểm tra ứng dụng còn bảo vệ user/tenant resource authorization.

### Giai đoạn 4 – Xác minh phục hồi

- Chỉ request từ các đường ingress được phép mới đến backend.
- Header giả từ Internet không tạo quyền và không làm sai log client IP.
- TLS upstream xác minh đúng danh tính.
- Các route/tenant và shared cache không bị trộn.
- Người dùng hợp lệ vẫn sử dụng được các chức năng quan trọng.
- Cấu hình đã được version hóa, có chủ sở hữu, audit và cảnh báo khi vi phạm trở lại.

**Không kết luận incident đã xử lý chỉ vì một WAF rule mới chặn được request mẫu.** Phải chứng minh không còn đường bypass hoặc điểm tin cậy metadata bị sai ở những vùng mạng khác.

## 26. Tình huống tổng hợp: proxy sau CDN và lỗ hổng logic dựa trên IP

Một doanh nghiệp có luồng **Internet → CDN/WAF → reverse proxy → Admin Dashboard**. Đội vận hành muốn dashboard chỉ cho nhóm quản trị; trước đây họ dùng quy tắc IP allowlist tại backend.

Sau lần chuyển CDN, backend vẫn kiểm tra IP lấy từ **X-Forwarded-For**. Reverse proxy được cấu hình nối thêm X-Forwarded-For nhưng **không phân biệt header từ client và header được CDN xác nhận**. Đồng thời backend còn có một public IP tạm thời được mở cho kiểm tra sức khỏe.

### 26.1. Những điểm sai về trust boundary

1. **X-Forwarded-For là dữ liệu có thể do client gửi**, không phải bằng chứng xác thực danh tính mạng nếu không có chuỗi proxy đáng tin.
2. **CDN/WAF không phải đường duy nhất** nếu origin public IP vẫn mở.
3. Dashboard có thể đang dựa chủ yếu vào **IP allowlist**, thay vì xác thực người quản trị và phân quyền ứng dụng.
4. Backend có thể suy luận client IP khác với WAF/rate limiter, làm log và hành động an ninh không nhất quán.

### 26.2. Thiết kế lại

~~~mermaid
flowchart TD
    C["External client"] --> CDN["CDN / WAF"]
    CDN -->|"Allowed origin connectivity"| RP["Reverse proxy"]
    RP -->|"TLS/mTLS; verified context"| BE["Admin dashboard"]
    IDP["IdP / MFA"] --> RP
    BE -->|"Application authorization"| ADMIN["Admin functions"]
    C -. "Direct origin path denied" .-> BE
    RP -. "Unverified forwarded/role headers discarded" .-> DROP["Normalize / reject"]
~~~

Các biện pháp:

- Khóa origin theo **nguồn/đường CDN được phê duyệt** hoặc private connectivity/mTLS theo khả năng nền tảng, không chỉ ẩn DNS.
- Gateway xác thực admin qua IdP/MFA và yêu cầu **role admin** theo chính sách.
- Chuẩn hóa forwarded headers dựa trên **trusted immediate peers**; backend không tự tin header từ nguồn lạ.
- Backend tiếp tục xác minh quyền nghiệp vụ và không cho truy cập từ mạng ngoài đường đã phê duyệt.
- Cảnh báo khi client cố truy cập origin, khi Host lạ hoặc khi policy trusted ranges bị đổi.

### 26.3. Cách xác nhận

Trong lab:

1. Admin hợp lệ qua CDN → proxy → dashboard: **allow**.
2. User không có role admin qua đường chuẩn: **deny**.
3. Một request có header **X-Forwarded-For: 10.0.0.5** do client tự khai: **không tự được xem là từ IP quản trị**.
4. Truy cập origin IP trực tiếp từ ngoài mạng lab: **deny**.
5. Mạng dự phòng và IPv6: cùng kết quả.

**Bài học:** đặt reverse proxy ở trước backend chỉ có giá trị như một ranh giới tin cậy khi **mọi đường vào đều đi qua kiểm soát và mọi metadata được phân loại theo nguồn đáng tin**.

## 27. Những sai lầm thường gặp

| Sai lầm | Tác động | Cách phòng tránh |
| --- | --- | --- |
| “Có reverse proxy là backend đã an toàn” | Backend còn đường bypass hoặc quyền rộng | Firewall/private networking, auth tại backend |
| Tin X-Forwarded-For từ mọi client | Có thể giả mạo client IP | Trusted proxies, sanitize và thuật toán chọn IP đúng |
| Tin X-User-Role do client tự gửi | Mạo danh/leo thang quyền | Strip/overwrite, verified context, mTLS và app authorization |
| Forwarded headers khác nhau ở CDN/proxy/backend | Log, rate limit và ACL nhận IP khác nhau | Một policy trust chain thống nhất |
| Backend TLS bật nhưng verify=false | Mã hóa tới endpoint chưa được xác minh | Xác minh CA, SAN, SNI và đúng service |
| Chỉ bảo vệ HTTPS public mà quên origin HTTP | Có đường nội bộ/plaintext hoặc direct access ngoài dự kiến | Bảo vệ từng chặng, khóa đường bypass |
| Unknown Host route vào ứng dụng mặc định | Cross-tenant/confused routing | Explicit virtual hosts, default reject |
| Dùng Host để tạo link reset password mà không kiểm tra | URL có thể trỏ sai domain | Canonical public base URL, host allowlist |
| Proxy và backend hiểu HTTP khác nhau | Parser desynchronization | Chuẩn hóa, reject malformed requests, cập nhật bản vá |
| WAF được xem là thay application authorization | Người dùng vẫn truy cập dữ liệu không thuộc quyền | Bảo vệ resource/tenant trong ứng dụng |
| Rate limit dựa trực tiếp trên IP CDN | Có thể chặn rất nhiều người hợp lệ | Verified client identity, nhiều tầng giới hạn |
| Rate limit quá chặt với AP/NAT/API clients | False positive và giảm khả dụng | Baseline theo endpoint/identity, canary |
| Cache chung API có dữ liệu cá nhân | Cross-user/tenant disclosure | No-shared-cache hoặc thiết kế key được xác minh |
| Failover sang backend thử nghiệm | Dữ liệu production tới sai môi trường | Pool membership và trust policy giống nhau |
| Chỉ giám sát BGP/DNS mà không kiểm tra origin IP | Không nhận ra direct origin access | Inventory public endpoints, IPv4/IPv6 audit |
| WebSocket không có authz theo message | Quyền thay đổi sau khi mở phiên | Session lifecycle, app authorization |
| Chỉ kiểm tra thành công 200 | Không thấy 4xx/5xx, cache và redirect bất thường | Test positive/negative, lỗi và các giao thức |
| Không kiểm soát quyền sửa proxy | Một thay đổi route có thể tác động nhiều ứng dụng | IAM/MFA, code review, audit, rollback |

## 28. Câu hỏi và bài tập tự kiểm tra

### Câu hỏi 1

Tại sao reverse proxy được gọi là một **trust boundary** chứ không chỉ là thành phần cân bằng tải?

**Gợi ý:** nó nhận dữ liệu từ miền ít tin cậy, xác minh/biến đổi và quyết định request nào được đến backend, đồng thời tạo những thuộc tính mà backend có thể sử dụng trong giới hạn rõ ràng.

### Câu hỏi 2

Nếu client trực tiếp gửi X-Forwarded-For chứa IP quản trị, backend có nên dùng giá trị đó để cấp quyền không?

**Gợi ý:** không. Header do client kiểm soát không chứng minh nguồn; cần trusted proxy chain và không sử dụng IP làm yếu tố ủy quyền duy nhất cho dashboard nhạy cảm.

### Câu hỏi 3

Client đã xác minh HTTPS với CDN. Điều này có bảo đảm CDN → backend sử dụng TLS có xác minh server không?

**Gợi ý:** không. Mỗi chặng TLS cần có chính sách và certificate validation riêng.

### Câu hỏi 4

Một proxy có thể đọc request HTTPS để làm WAF trong chế độ TLS passthrough thuần túy không?

**Gợi ý:** thông thường không có đủ nội dung HTTP rõ nếu không kết thúc/giải mã TLS ở điểm phù hợp.

### Câu hỏi 5

SNI và Host/:authority có giống nhau hoàn toàn và có tự chứng minh tenant không?

**Gợi ý:** SNI phục vụ chọn cấu hình TLS, Host/:authority phục vụ authority HTTP; vẫn phải xác minh route/tenant và danh tính người dùng.

### Câu hỏi 6

Vì sao thêm CDN rồi vẫn phải kiểm tra public IPv4 và IPv6 của origin?

**Gợi ý:** nếu origin còn mở, người dùng có thể đi vòng qua WAF/rate limit tại CDN.

### Câu hỏi 7

Khi dùng X-Verified-User do gateway phát hành, hai điều kiện quan trọng nhất để backend có thể tin header là gì?

**Gợi ý:** gateway phải xác minh danh tính và xóa header do client tự gửi; backend chỉ nhận từ nguồn gateway được chứng thực/giới hạn đường truy cập.

### Câu hỏi 8

Vì sao kết nối TCP/HTTP 200 từ health check không chứng minh backend có thể nhận traffic nhạy cảm?

**Gợi ý:** health check không tự kiểm tra danh tính, bản vá, quyền/tenant hoặc service authorization.

### Câu hỏi 9

Một API trả dữ liệu riêng theo tài khoản. Cache chung trên proxy cần đặc biệt xem xét điều gì?

**Gợi ý:** cache key và chính sách không cache response chứa dữ liệu cá nhân/token, tránh phục vụ response cho user/tenant khác.

### Câu hỏi 10

Vì sao một HTTP 403 trên client chưa chứng minh proxy đã chặn trước backend?

**Gợi ý:** 403 có thể do backend/WAF; cần log/trace ở đúng điểm enforcement.

### Câu hỏi 11

HTTP/2 hoặc HTTP/3 chuyển đổi sang HTTP/1.1 ở proxy tạo thêm rủi ro gì?

**Gợi ý:** sai lệch cách phân tích header, request framing hoặc route; cần kiểm thử tính nhất quán và từ chối dữ liệu mơ hồ.

### Câu hỏi 12

Sau khi admin bị gỡ quyền ở IdP, một WebSocket cũ vẫn hoạt động. Cần xem những lớp nào?

**Gợi ý:** thời hạn phiên, reauthorization, AuthZ theo message, token và cơ chế ngắt kết nối có kiểm soát.

### Bài tập thiết kế

Một doanh nghiệp có **CDN/WAF → cloud load balancer → Kubernetes ingress → API service**, phục vụ hai tenant và có **Admin Dashboard** riêng. Hãy:

1. Vẽ sơ đồ trust zone và đánh dấu **mọi TLS termination**, nơi xác minh chứng thư backend.
2. Lập danh sách **thành phần nào được quyền phát hành X-Forwarded-For, Forwarded và user identity header**; nêu cách xóa input không đáng tin.
3. Định nghĩa host allowlist và policy unknown Host, default backend, path/method routing.
4. Thiết kế ma trận **nguồn → đích → cổng → quyền** để không thể đi trực tiếp tới backend từ Internet, kể cả IPv6.
5. Xây dựng policy gateway authentication cho Admin Dashboard và application authorization cho từng tenant.
6. Đề xuất caching policy sao cho không thể phục vụ dữ liệu tenant A cho tenant B.
7. Đề xuất rate limiting dựa trên identity/client context và bảo vệ login endpoint mà không chặn nhầm NAT/CGNAT.
8. Xây dựng ít nhất **tám positive/negative test**, bao gồm spoofed forwarding headers, wrong backend certificate, direct origin, malformed requests, WebSocket và failover.
9. Thiết kế log correlation xuyên CDN/LB/ingress/backend với request ID, verified client IP, policy version và route.
10. Viết runbook khắc phục khi SOC phát hiện một endpoint backend đang được truy cập trực tiếp không qua CDN.

**Tiêu chí đạt:** mọi đường vào đều có chính sách được phê duyệt, metadata chỉ được tin theo đúng nguồn, backend có xác thực riêng và kết quả được xác minh cả ở **luồng được phép** lẫn **luồng phải bị từ chối**.

## 29. Những điều cần ghi nhớ

- **Reverse proxy là một trust boundary** khi nó xác minh, chuẩn hóa và giới hạn dữ liệu từ client trước khi chuyển tới backend; chỉ dùng để cân bằng tải chưa đủ bảo vệ.
- **Client IP và forwarding headers phải được diễn giải theo trusted proxy chain**, không tin X-Forwarded-For, X-Real-IP, Forwarded hoặc identity headers do Internet client tự khai.
- **TLS termination tạo các chặng tin cậy riêng**; proxy đóng vai TLS client tới backend phải xác minh đúng CA, SAN, SNI và service identity theo chính sách.
- **Host/:authority, URL/path, method và HTTP framing là dữ liệu không tin cậy**; phải xử lý nhất quán giữa WAF/proxy/backend, từ chối request mơ hồ và unknown Host.
- **Authentication ở gateway không thay application authorization**, đặc biệt với quyền user, tenant và từng bản ghi dữ liệu.
- **Caching, rate limiting, retries, WebSocket, gRPC, HTTP/2/3 và failover** đều có thể tạo điểm vượt ranh giới nếu thiết kế thiếu nhất quán.
- **CDN/WAF không bảo vệ được backend bị truy cập trực tiếp**; cần kiểm tra public origin, IPv4/IPv6, firewall, mTLS, cloud và đường quản trị.
- **Log phải phân biệt peer IP, verified client IP, identity, route, config version và enforcement outcome**, đồng thời bảo vệ bí mật và quyền riêng tư.
- **Đánh giá bằng positive và negative tests trong lab được phép**, kiểm chứng request đúng tới đúng backend và request trái chính sách bị chặn tại đúng lớp.
- **Phòng vệ nhiều tầng vẫn cần thiết:** reverse proxy phối hợp với segmentation, TLS, IAM, firewall, IDS/IPS, DNS, VPN, cloud policy và giám sát ứng dụng.


# WAF trước reverse proxy: kiến trúc, chính sách và vận hành an toàn

**Web Application Firewall (WAF)** là lớp kiểm soát lưu lượng HTTP/HTTPS nhằm phát hiện, ghi nhận hoặc ngăn chặn những yêu cầu có dấu hiệu vi phạm chính sách bảo vệ ứng dụng Web/API. **Reverse proxy** là thành phần nhận request thay cho các server ứng dụng, sau đó định tuyến, cân bằng tải hoặc chuyển tiếp tới backend. Khi đặt **WAF trước reverse proxy** trên đường đi của người dùng, WAF kiểm tra yêu cầu ở biên trước khi request được chuyển tới tầng proxy và ứng dụng.

Bài học thuộc chương **Web application firewall** của module **SECURITY_NETWORK_SECURITY**. Việc bố trí WAF cần kết hợp với phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, mạng không dây và hạ tầng cloud; đồng thời vận dụng phân tích lưu lượng, threat modeling, giám sát xâm nhập và thiết kế kiến trúc mạng an toàn. Một WAF đặt đúng vị trí nhưng để lộ đường truy cập trực tiếp tới origin, tin nhầm header do client gửi hoặc làm gián đoạn luồng hợp lệ vẫn là một triển khai chưa đạt mục tiêu.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Vẽ đường đi **client → WAF → reverse proxy → backend** và xác định ranh giới tin cậy tại từng chặng.
2. Phân biệt vai trò WAF với reverse proxy, firewall tầng mạng, CDN, IDS/IPS và cơ chế bảo mật tại ứng dụng.
3. Giải thích nơi **TLS kết thúc**, cách bảo vệ chặng WAF–reverse proxy, và vì sao WAF phải đọc được HTTP để kiểm tra nội dung.
4. Bảo vệ **origin** khỏi truy cập đi vòng WAF; xác định IP client và xử lý các header chuyển tiếp đáng tin.
5. Thiết kế quy tắc WAF, quản lý ngoại lệ, rate limit, bot control và chế độ phát hiện trước khi chặn.
6. Đánh giá giới hạn khi xử lý HTTP/2, HTTP/3, WebSocket, upload, API và các trường hợp nhiều proxy.
7. Xây dựng bộ kiểm thử, giám sát và quy trình xử lý sự cố/rollback cho WAF nằm trước reverse proxy.

## 2. WAF và reverse proxy khác nhau như thế nào?

| Thành phần | Nhiệm vụ chính | Nhìn thấy gì? | Giới hạn |
| --- | --- | --- | --- |
| **WAF** | Áp chính sách an ninh cho HTTP request, và có thể response tùy sản phẩm; chặn hoặc ghi nhận rủi ro tại tầng ứng dụng | Method, path, header, query, body nếu lưu lượng được giải mã và công cụ hỗ trợ phân tích | Không thay logic phân quyền của ứng dụng hoặc bảo đảm phát hiện mọi khai thác |
| **Reverse proxy** | Tiếp nhận kết nối phía client, chuyển tiếp request, chọn backend, cân bằng tải, timeout và đôi khi cache/TLS termination | HTTP tại điểm proxy được giải mã; thông tin upstream và downstream | Không mặc nhiên là WAF dù có thể cấu hình một số bộ lọc |
| **Firewall L3/L4** | Hạn chế nguồn/đích, giao thức, cổng, luồng vào/ra | Chủ yếu IP, port, trạng thái kết nối | Thường không hiểu đường dẫn API và dữ liệu JSON nằm trong TLS |
| **IDS/IPS** | Phát hiện hoặc ngăn một số tín hiệu xâm nhập dựa trên lưu lượng quan sát được | Tùy vị trí cảm biến và khả năng giải mã | Không bảo đảm nhìn thấy nội dung HTTPS đầu cuối |
| **CDN** | Phân phối và cache nội dung gần người dùng, có thể có DDoS/WAF | Các request đi qua edge và nội dung được phép cache | CDN không phải lúc nào cũng bật WAF hoặc bảo vệ origin mặc định |
| **Ứng dụng/API** | Xác thực, phân quyền từng tài nguyên, xử lý nghiệp vụ, bảo vệ dữ liệu | Ngữ cảnh người dùng, tài nguyên và hành động nghiệp vụ | Không nên tự gánh mọi nhiệm vụ lọc và hấp thụ lưu lượng bất thường tại edge |

Một nền tảng có thể **kết hợp WAF và reverse proxy trong cùng sản phẩm hoặc cùng tiến trình**. Tên các thành phần mô tả **vai trò xử lý**, không bắt buộc luôn là hai máy vật lý khác nhau. Điều kiện cốt lõi của đề bài là **logic kiểm tra WAF nằm trước logic chuyển tiếp vào origin** trên đường request.

WAF có thể hỗ trợ các tập quy tắc cho hành vi thường gặp như SQL injection, cross-site scripting (XSS), khai thác đường dẫn, request bất thường, bot hoặc giới hạn tốc độ. Khả năng, phạm vi kiểm tra và mức hiệu quả khác nhau theo sản phẩm và cấu hình; không nên coi việc bật một bộ quy tắc mặc định là đã bảo vệ ứng dụng toàn diện.

## 3. Sơ đồ kiến trúc WAF trước reverse proxy

Giả sử hệ thống cung cấp API đơn hàng công khai tại tên miền api.example.test:

~~~mermaid
flowchart LR
    C["Trình duyệt / API client"] -->|"HTTPS"| W["WAF ở edge"]
    W -->|"HTTPS riêng tới origin"| P["Reverse proxy / Load balancer"]
    P -->|"TLS nội bộ nếu cần"| A["Order API"]
    A -->|"Kết nối DB có bảo vệ"| D[("Database")]
    W -->|"Sự kiện WAF đã lọc"| L["Security logs / SOC"]
    P -->|"Access log đã lọc"| L
    subgraph Untrusted["Vùng Internet / client"]
      C
    end
    subgraph Edge["Vùng edge hoặc CDN"]
      W
    end
    subgraph DMZ["Vùng reverse proxy / origin"]
      P
    end
    subgraph Internal["Vùng ứng dụng và dữ liệu"]
      A
      D
    end
~~~

Các ranh giới trong sơ đồ cần được ghi rõ:

- **Client → WAF:** client không đáng tin cậy; WAF tiếp nhận request ở biên Internet và là điểm đầu tiên có thể đọc HTTP nếu kết thúc TLS.
- **WAF → reverse proxy:** là luồng giữa hai hệ thống được tổ chức cho phép, nhưng vẫn cần bảo vệ nguồn gọi, TLS và tính xác thực đầu cuối; không mặc nhiên tin cậy chỉ vì ở mạng nội bộ.
- **Reverse proxy → API:** là chặng kết nối riêng; phải xác định proxy có kết thúc TLS, tạo kết nối mới, thêm header nào và backend chấp nhận những nguồn nào.
- **API → database/telemetry:** phải có kiểm soát mạng và quyền tài nguyên độc lập; WAF không thay những cơ chế này.

### 3.1. Đường đi của một request

~~~mermaid
sequenceDiagram
    participant U as Client
    participant D as DNS
    participant W as WAF
    participant P as Reverse proxy
    participant A as API
    U->>D: Phân giải api.example.test
    D-->>U: Endpoint của WAF / CDN
    U->>W: TLS handshake và HTTPS request
    Note over W: Giải mã HTTP nếu WAF kết thúc TLS
    W->>W: Xác định policy, rule, rate limit
    alt Request được phép
      W->>P: Kết nối origin và HTTP request qua TLS
      P->>A: Chuyển request theo route được cấu hình
      A-->>P: HTTP response
      P-->>W: Response
      W-->>U: Response qua kết nối HTTPS của client
    else Request bị chặn
      W-->>U: Block / challenge / rate-limit response
    end
~~~

DNS chỉ giúp client tìm điểm kết nối; **DNS trỏ về WAF không tự ngăn được client truy cập IP origin trực tiếp**. Cần chặn đường bỏ qua WAF bằng network policy/firewall và cơ chế xác thực origin phù hợp.

### 3.2. Các biến thể triển khai

| Biến thể | Đường đi | Điều cần kiểm tra |
| --- | --- | --- |
| Cloud WAF/CDN → reverse proxy tại doanh nghiệp | Internet → edge của nhà cung cấp → origin công ty | IP nguồn của WAF, kết nối origin, chứng chỉ, chính sách allowlist, vùng địa lý, HA |
| Cloud WAF → cloud load balancer/reverse proxy | Internet → WAF → load balancer → workload | Security group/NSG, private/public origin, đường ra vào VPC/VNet, WAF bypass |
| WAF appliance → reverse proxy nội bộ | Firewall biên → WAF → proxy → API | HA, tuyến đối xứng, TLS termination, điểm quản trị và log |
| Reverse proxy tích hợp WAF | Client → proxy có bộ lọc WAF → upstream | Thứ tự bộ lọc, phạm vi route được bảo vệ, policy theo host/path |
| API gateway có tính năng WAF | Client → gateway/WAF → backend | Khác biệt policy của gateway và WAF, authentication, giới hạn body và phiên bản HTTP |

Không chọn công nghệ chỉ theo tên gọi. Cần xác minh **mọi hostname, API route, port và địa chỉ công khai** thực sự đi qua WAF trước khi tới reverse proxy; môi trường thử nghiệm, admin endpoint hoặc cổng phụ là những đường dễ bị bỏ sót.

## 4. TLS và khả năng kiểm tra nội dung HTTP

### 4.1. Vì sao WAF cần giải mã HTTPS?

Một WAF muốn đọc method, URL path, header và request body của HTTPS thường phải nằm **tại một điểm kết thúc TLS được phép**, hoặc có cơ chế giải mã hợp lệ tương đương. Nếu lưu lượng chỉ đi xuyên qua WAF ở dạng TLS pass-through và WAF không có khóa/khả năng giải mã, nó không thể tự kiểm tra đầy đủ nội dung HTTP bị mã hóa; khi đó nó chỉ có thể áp các chính sách dựa trên metadata hoặc khả năng sản phẩm hỗ trợ.

Mô hình hai chặng phổ biến:

~~~text
Client ----- HTTPS / TLS A -----> WAF
WAF    ----- HTTPS / TLS B -----> Reverse proxy / origin
Reverse proxy --- TLS C hoặc kết nối riêng được bảo vệ ---> API
~~~

**TLS A và TLS B là hai kết nối riêng**. WAF đọc nội dung HTTP sau khi giải mã kết nối A, thực thi policy, sau đó gửi dữ liệu được phép tới reverse proxy qua kết nối B. Việc client thấy biểu tượng khóa HTTPS **không chứng minh** kết nối B hoặc C cũng có TLS, hoặc chứng chỉ ở chặng sau được xác minh đúng.

### 4.2. Bảo vệ chặng WAF → reverse proxy

- **HTTPS từ WAF đến origin:** dùng TLS hiện đại, xác minh chứng chỉ/hostname đúng theo khả năng và chính sách của sản phẩm; tránh chế độ bỏ qua lỗi chứng chỉ chỉ để kết nối được.
- **Xác thực origin và WAF:** có thể sử dụng mTLS, origin authentication hoặc cơ chế xác thực kết nối tương đương nếu được nền tảng hỗ trợ. Cần quản lý vòng đời khóa, chứng chỉ và quyền cấp phát.
- **Hostname/SNI:** xác định WAF gửi tên máy chủ nào khi TLS handshake với origin và header Host nào khi chuyển HTTP. Hostname sai có thể làm reverse proxy trả website khác hoặc chứng chỉ không khớp.
- **Giới hạn nguồn:** tại reverse proxy hoặc firewall trước origin, chỉ cho phép đường kết nối từ các endpoint WAF được duyệt hoặc hệ thống health check có điều kiện rõ ràng.
- **Quản lý bí mật:** private key/chứng chỉ và credential của WAF, proxy hoặc API phải được bảo vệ, xoay/gia hạn và theo dõi hết hạn.
- **Đường riêng:** private link, tunnel hoặc mạng nội bộ chỉ giảm bề mặt tiếp xúc nếu được cấu hình chính xác; việc đi qua mạng riêng không thay xác thực và chính sách truy cập.

Một số hệ thống hỗ trợ HTTP/3 với client nhưng dùng HTTP/2 hoặc HTTP/1.1 ở kết nối tới origin. Việc thay đổi phiên bản giao thức giữa hai chặng **không tự làm mất khả năng bảo vệ bằng TLS**, nhưng làm tăng yêu cầu thống nhất cách diễn giải request và header.

### 4.3. Sơ đồ phân định trách nhiệm TLS

| Chặng | Bên kết thúc TLS | Nơi dữ liệu HTTP ở dạng rõ | Cần xác minh |
| --- | --- | --- | --- |
| Client → WAF | WAF/edge hoặc dịch vụ thay nó | Bên trong điểm kiểm tra WAF | Hostname, chứng chỉ, cấu hình TLS, chống chuyển hướng về HTTP ngoài ý muốn |
| WAF → reverse proxy | Reverse proxy/origin | WAF trước khi gửi; reverse proxy sau khi giải mã | TLS tới origin, chứng chỉ, nguồn WAF, danh tính peer nếu dùng mTLS |
| Reverse proxy → backend | Backend hoặc proxy tùy kiến trúc | Reverse proxy và điểm xử lý của backend | TLS nội bộ nếu cần, ACL, mTLS/identity, logging |

Nội dung đã giải mã tại WAF hoặc reverse proxy là **dữ liệu nhạy cảm có thể được ghi log hoặc quan sát bởi người vận hành có quyền**. Cần quản lý truy cập, bảo vệ bộ nhớ/chứng chỉ, hạn chế body logging và chọn nhà cung cấp phù hợp với yêu cầu dữ liệu.

## 5. Chặn đường truy cập đi vòng WAF đến origin

Đây là một rủi ro đặc biệt quan trọng của kiến trúc **WAF đứng trước reverse proxy**. Nếu reverse proxy vẫn có public IP mở từ toàn Internet, một client có thể bỏ qua DNS endpoint của WAF và kết nối trực tiếp tới origin. Lúc đó rule WAF không được thực thi trên đường bị bỏ qua.

### 5.1. Các đường bypass thường gặp

| Đường đi | Nguyên nhân | Biện pháp |
| --- | --- | --- |
| Client → public IP origin | Origin mở inbound trực tiếp | Đưa origin về private network nếu phù hợp hoặc chỉ allow nguồn WAF tại firewall/SG |
| DNS phụ hoặc hostname cũ → origin | Bản ghi cũ, host thử nghiệm, DNS lịch sử | Kiểm kê tất cả tên miền và endpoint, đóng đường cũ |
| Cổng phụ 8080/8443 trên reverse proxy | Policy chỉ bảo vệ 443, còn cổng khác mở | Giới hạn port và nguồn tại điểm thực thi gần origin |
| Đường IPv6 trực tiếp | WAF áp cho IPv4, AAAA hoặc địa chỉ IPv6 origin vẫn được công bố | Kiểm kê A/AAAA, IPv4/IPv6 firewall, DNS và route |
| CDN/WAF bị tạm bypass trong vận hành | Khôi phục traffic trực tiếp rồi không đóng lại | Thay đổi có owner, expiry, log và kiểm thử sau rollback |
| Nguồn WAF được giả định từ header | Origin tin giá trị X-Forwarded-For do client tự gửi | Chỉ tin header từ kết nối WAF/proxy đã được xác thực |

### 5.2. Biện pháp bảo vệ origin

1. Chọn cấu trúc **origin không nhận kết nối công khai không cần thiết** nếu nền tảng hỗ trợ.
2. Nếu cần kết nối public từ WAF tới origin, dùng **allowlist các dải nguồn thực của WAF** tại firewall/security group; có cơ chế cập nhật theo thay đổi danh sách của nhà cung cấp.
3. Bổ sung **mTLS hoặc xác thực origin** để phân biệt lưu lượng từ edge được cấp quyền với đối tượng khác có thể nằm trong cùng dải IP hạ tầng chia sẻ.
4. Kiểm tra đầy đủ **DNS A/AAAA, port khác, hostname admin, hostname kiểm thử, route VPN và endpoint dự phòng**.
5. Áp chính sách ở **cả reverse proxy và backend** khi cần; reverse proxy không nên cho phép client trực tiếp bỏ qua WAF thông qua một listener khác.
6. Thực hiện phép thử kết nối từ nguồn **không** nằm trong allowlist ở môi trường được phép; kết quả mong đợi là **không lập được kết nối tới origin** trong khi truy cập qua WAF vẫn thành công.

Không dùng mỗi một header tùy ý như X-Origin-Secret làm bằng chứng duy nhất để xác thực WAF: header có thể bị giả nếu đường origin trực tiếp còn mở hoặc bí mật bị lộ. Nếu phải dùng token ở origin, cần bảo vệ kênh truyền, giữ bí mật và kết hợp hạn chế nguồn.

## 6. Xác định IP client và tin cậy các header chuyển tiếp

Khi WAF tạo kết nối mới tới reverse proxy, **IP nguồn TCP mà reverse proxy nhìn thấy thường là IP của WAF**. Để ứng dụng và bộ giới hạn tốc độ biết IP client bên ngoài, chuỗi proxy có thể truyền metadata qua các header như **X-Forwarded-For**, **Forwarded** hoặc thông tin tương đương theo nền tảng.

Ví dụ logic:

~~~text
Client thực:          198.51.100.25
WAF nguồn tới origin: 203.0.113.20
Reverse proxy:        10.30.20.10

WAF gửi metadata về client tới reverse proxy:
X-Forwarded-For: 198.51.100.25
X-Forwarded-Proto: https
Host: api.example.test
~~~

Trong thực tế, **client có thể tự gửi header cùng tên**. Nếu reverse proxy/app tin mọi giá trị X-Forwarded-For bất kể nguồn, kẻ tấn công có thể giả danh địa chỉ client để né rate limit dựa trên IP, làm sai log hoặc vượt một số rule kiểm soát chỉ dựa vào IP.

### 6.1. Thiết kế chuỗi proxy đáng tin

- Xác định chính xác **địa chỉ hoặc danh tính của proxy upstream đáng tin**: WAF, CDN hoặc load balancer; không dùng allowlist rộng cho mọi IP từ Internet.
- Tại trust boundary, **loại bỏ hoặc chuẩn hóa các header client tự gửi** liên quan tới IP, scheme, host và forwarding metadata theo khả năng của edge.
- Reverse proxy chỉ trích xuất IP client từ header khi **kết nối trực tiếp tới nó đến từ proxy được tin cậy**; nếu từ nguồn khác phải coi header là không đáng tin.
- Nếu có nhiều proxy, định nghĩa rõ chuỗi hop và quy tắc chọn địa chỉ client (thường duyệt từ bên phải qua các hop đã tin đến IP không tin đầu tiên, theo cơ chế triển khai), không mặc định phần tử đầu của danh sách luôn đáng tin.
- Ghi cả **IP kết nối tới reverse proxy**, **IP client đã xác minh**, **WAF request ID** và lý do quyết định để điều tra; tránh dùng dữ liệu giả mạo trong access log hoặc policy.
- Kiểm tra riêng **IPv6**, địa chỉ qua NAT/CGNAT và các header tương đương được nhà cung cấp sử dụng.

### 6.2. Forwarded scheme, Host và redirect

Khi TLS kết thúc ở WAF nhưng reverse proxy nhận request từ WAF theo một chặng riêng, ứng dụng có thể cần biết **scheme gốc** là HTTPS để tạo redirect, URL tuyệt đối hoặc cookie Secure đúng. Các header như X-Forwarded-Proto và Forwarded có thể cung cấp thông tin đó **nếu được đặt bởi proxy đáng tin**.

Tin nhầm Host hoặc X-Forwarded-Host do client tự gửi có thể dẫn tới **host header injection**, tạo liên kết reset mật khẩu tới hostname không mong muốn hoặc redirect sai. Cần kiểm soát **hostname được phép**, quy tắc chuyển tiếp và giá trị scheme mà ứng dụng sử dụng.

### 6.3. Ví dụ khái niệm về trust policy

~~~yaml
trusted_proxy_policy:
  accepted_direct_sources:
    - approved-waf-endpoints
  forwarded_client_ip:
    source: edge-managed-header
    trust_only_from: accepted_direct_sources
    reject_or_ignore_untrusted_forwarding_headers: true
  forwarded_scheme:
    expected_public_scheme: https
  allowed_hostnames:
    - api.example.test
  audit:
    include: [waf_request_id, trusted_client_ip, direct_peer_ip, matched_policy]
    redact: [authorization, cookie, sensitive_query_and_body]
~~~

Đây là **pseudo-YAML mô tả yêu cầu thiết kế**, không phải cấu hình chạy trực tiếp trên Nginx, Envoy, HAProxy hoặc nền tảng cloud. Cấu hình thực tế phụ thuộc cú pháp, module xử lý real IP, thứ tự proxy và thiết lập trust chain của sản phẩm.

## 7. Thiết kế chính sách WAF ở phía trước reverse proxy

Chính sách WAF nên phản ánh **cấu trúc ứng dụng và rủi ro của từng endpoint**, thay vì chỉ dựa vào một bộ chữ ký chung. Đường dẫn public, API thanh toán, endpoint upload, đường quản trị và webhook từ đối tác có mô hình lưu lượng rất khác nhau.

### 7.1. Nhóm kiểm soát thường dùng

| Kiểm soát WAF | Mục tiêu | Cách cấu hình và giới hạn |
| --- | --- | --- |
| Managed rules / tập quy tắc bảo mật | Phát hiện các mẫu request liên quan tới SQL injection, XSS, path traversal hoặc khai thác phổ biến | Cập nhật phiên bản, giám sát false positive; bộ quy tắc không thay kiểm tra dữ liệu và truy vấn tham số ở backend |
| Positive security / allowlist | Chỉ nhận method, content type, hostname và route mong muốn | Chỉ áp khi đã hiểu hợp đồng API và luồng hợp lệ, tránh chặn chức năng mới |
| Custom rule | Áp chính sách cụ thể cho ứng dụng hoặc đối tác | Dựa trên host/path, nguồn đáng tin, identity hoặc thuộc tính được hỗ trợ; luôn ghi lý do và owner |
| Rate limiting | Giới hạn tần suất request theo IP, token, route hoặc tiêu chí hỗ trợ | Client có thể dùng chung IP qua NAT; rate limit theo IP đơn thuần có thể gây chặn nhầm |
| Bot management / challenge | Phát hiện, thử thách hoặc hạn chế một số hoạt động tự động | Challenge cần tương thích với API máy-máy, thiết bị trợ năng và client không có trình duyệt |
| Geo/IP reputation | Giảm tiếp xúc với nguồn rủi ro theo tín hiệu địa lý/uy tín | IP qua VPN, CDN, roaming hoặc NAT không là bằng chứng danh tính hay vị trí chính xác |
| Request size/body inspection | Hạn chế request quá lớn hoặc kiểm tra payload trong giới hạn hỗ trợ | WAF có giới hạn body/buffer, định dạng, giải nén và khả năng streaming; phải xác định khi vượt giới hạn sẽ xử lý thế nào |
| Protocol validation | Nhận diện một số request sai định dạng hoặc mâu thuẫn | Không thay cho parser an toàn, giới hạn header và cấu hình thống nhất của reverse proxy/backend |
| Response inspection / data leakage controls | Một số sản phẩm có thể phân tích response hoặc loại thông tin nhạy cảm | Không phải WAF nào cũng hỗ trợ; không xem đây là giải pháp DLP hoàn chỉnh |

**WAF không hiểu đầy đủ quyền nghiệp vụ**. Với lỗi Broken Object Level Authorization (BOLA/IDOR), một request HTTP hoàn toàn hợp lệ có thể đọc dữ liệu của người khác nếu backend thiếu kiểm tra quyền theo đối tượng. Với CSRF, XSS lưu trữ hoặc lỗi logic đặt hàng, WAF có thể hỗ trợ giảm một số đường tấn công nhưng vẫn cần cơ chế chống CSRF, mã hóa đầu ra, quản lý session và authorization trong ứng dụng.

### 7.2. Ưu tiên policy theo route

Ví dụ hệ thống bán hàng:

| Host/path | Chức năng | Kiểm soát đề xuất | Cảnh báo false positive |
| --- | --- | --- | --- |
| api.example.test/v1/products | Tìm kiếm/sản phẩm công khai | Managed rules, giới hạn request bất thường, quota hợp lý | Query search chứa ký tự đặc biệt hợp lệ |
| api.example.test/v1/orders | Tạo/xem đơn hàng | Managed rules, giới hạn method/body, rate limit dựa trên danh tính sau khi xác thực phù hợp | Tải cao theo mùa, yêu cầu JSON phức tạp |
| api.example.test/v1/payments | Thanh toán | Kiểm soát chặt method, kích thước, rate limit, telemetry; xác thực ở API | Retry của hệ thống thanh toán có thể hợp lệ |
| api.example.test/v1/uploads | Upload tài liệu | Giới hạn loại file/kích thước phù hợp và quét nội dung ở hệ thống chuyên trách | Multipart upload, file lớn hoặc chunked request |
| api.example.test/webhooks/vendor | Webhook từ đối tác | Nguồn mạng nếu ổn định, xác thực chữ ký webhook hoặc mTLS, quy tắc riêng | Không dùng browser challenge cho webhook |
| admin.example.test | Quản trị | Phân tách hostname, kiểm soát mạng/VPN/ZTNA và xác thực mạnh | Không coi IP allowlist hoặc WAF là đủ thay MFA |

Những đường dẫn chỉ là **ví dụ**. Cần xác minh tài liệu API thực tế và nguồn traffic trước khi áp dụng. Nếu route chứa thông tin người dùng, hãy tránh ghi đầy đủ path/query nhạy cảm vào log.

### 7.3. Thứ tự đánh giá và ngoại lệ

Các nền tảng WAF có thể đánh giá **rule priority, group, managed rule, custom rule, allow, block, count, challenge** theo thứ tự và ngữ nghĩa khác nhau. Một rule ALLOW rộng có thể khiến các kiểm soát phía sau không còn được áp dụng trong một số sản phẩm; trên sản phẩm khác việc kết hợp luật lại khác.

Trước khi tạo ngoại lệ, cần trả lời:

1. **Rule nào khớp** và request nào bị chặn? Đọc rule ID, path, method, tín hiệu khớp và request ID đã lọc dữ liệu nhạy cảm.
2. **False positive có thật không?** Kiểm tra request từ ứng dụng được phép, không chỉ dựa vào lời báo “WAF chặn”.
3. Có thể **điều chỉnh điều kiện cụ thể** theo route, parameter, cấu trúc dữ liệu hoặc rule ID không?
4. Ngoại lệ có áp dụng cho **đúng hostname, path, phương thức và đối tượng được duyệt** không?
5. Khi nào ngoại lệ hết hạn và ai chịu trách nhiệm đánh giá lại?

Ví dụ: nếu rule phát hiện bất thường trong một tham số tìm kiếm có dữ liệu hợp lệ, nên điều chỉnh **đúng điều kiện gây false positive** sau khi phân tích; không nên tạo ALLOW toàn bộ lưu lượng từ cùng một IP hoặc tắt toàn bộ managed rules.

### 7.4. Rate limiting và nhận diện người dùng

Nếu nhiều người dùng sau một công ty, VPN hoặc CGNAT dùng cùng IP nguồn, đặt quota quá thấp theo IP có thể chặn cả nhóm. Ngược lại, kẻ xấu có thể phân tán request qua nhiều IP. Hãy lựa chọn tín hiệu phù hợp với khả năng WAF:

- IP client đã được xác minh từ chuỗi proxy đáng tin.
- Danh tính phiên/tài khoản hoặc token **được kiểm chứng ở lớp phù hợp**, nếu WAF có tích hợp và có thể bảo vệ dữ liệu đó.
- Route hoặc nhóm endpoint, phương thức, kiểu request, thông số hoạt động cho API.
- Kết hợp giới hạn ở edge với quota theo tài khoản tại API gateway/ứng dụng.

Không sử dụng một chuỗi client tự khai trong header làm khóa rate limit tin cậy. Cần xem cả **response trả về khi vượt ngưỡng** (thường là 429, nhưng cấu hình sản phẩm có thể khác), Retry-After nếu có, cơ chế backoff/retry ở client và khả năng làm tăng tải khi client thử lại dồn dập.

### 7.5. Bot challenge không phù hợp cho mọi client

JavaScript challenge hoặc CAPTCHA có thể dành cho tương tác trình duyệt nhưng gây lỗi cho CLI, mobile SDK, webhook, service-to-service và một số người dùng trợ năng. Đối với API máy-máy, ưu tiên xác thực danh tính, chữ ký request/webhook, mTLS hoặc quota phù hợp theo hợp đồng; chọn policy WAF không yêu cầu hành vi trình duyệt mà client không hỗ trợ.

## 8. Những khác biệt giao thức và xử lý request dễ gây sai lệch

### 8.1. HTTP/1.1, HTTP/2 và HTTP/3

| Luồng | Thực tế có thể gặp | Điều phải kiểm tra |
| --- | --- | --- |
| Client → WAF dùng HTTP/1.1 | Bản tin HTTP dạng văn bản trên TCP; HTTPS thêm TLS | Request line, Host, header, body, keep-alive, timeout |
| Client → WAF dùng HTTP/2 | Frame nhị phân, nhiều stream trên một TCP; thường bảo vệ bằng TLS | Chuyển đổi pseudo-header, giá trị authority, giới hạn stream, parser |
| Client → WAF dùng HTTP/3 | QUIC trên UDP/443, tích hợp TLS 1.3 | Chính sách UDP/443, WAF có hỗ trợ và kiểm tra được HTTP/3 hay không |
| WAF → reverse proxy dùng HTTP/1.1 hoặc HTTP/2 | WAF có thể sử dụng phiên bản HTTP khác phía client | Chuẩn hóa method, host, header, body và xử lý protocol conversion |

Khi WAF đổi HTTP/2 thành HTTP/1.1 để gửi origin, hai thành phần phải **diễn giải nhất quán ranh giới bản tin, header và độ dài body**. Sự khác biệt parser, quy tắc ưu tiên header hoặc cách xử lý request framing có thể làm phát sinh **HTTP request smuggling/desynchronization**. Cần dùng bản vá được hỗ trợ, loại bỏ header mâu thuẫn, cấu hình giới hạn hợp lý và kiểm thử tương thích giữa WAF với reverse proxy theo hướng dẫn nhà cung cấp.

Không giả định WAF nhận HTTP/3 ở edge thì reverse proxy phía sau cũng phải dùng HTTP/3; mỗi chặng có thể thương lượng độc lập. Nếu WAF không hỗ trợ một giao thức đang được công bố, cần có chính sách fallback hoặc tắt giao thức đó ở edge theo quyết định kiến trúc.

### 8.2. Encoding, normalization và đường dẫn

WAF và reverse proxy có thể chuẩn hóa URL, percent-encoding, Unicode, đường dẫn, dấu gạch chéo, query string hoặc header theo những quy tắc không hoàn toàn giống nhau. Nếu WAF đánh giá một dạng request nhưng origin diễn giải thành một tài nguyên khác, chính sách dựa trên **path** có thể sai mục tiêu.

Các bước kiểm soát gồm: giới hạn phương thức/định dạng được phép, cấu hình xử lý URL và header nhất quán, xác minh request sau chuẩn hóa, kiểm tra route có phân biệt chữ hoa/chữ thường, và áp authorization ở chính backend. Chỉ thực hiện kiểm thử lỗi parser hoặc bypass trên hệ thống được cấp phép và trong kế hoạch kiểm thử an toàn.

### 8.3. Request body, upload và API JSON

Một WAF có thể giới hạn số byte kiểm tra trong request body, chỉ phân tích một số content type hoặc hoạt động khác nhau với body được nén, stream/chunked, multipart form, GraphQL hay JSON có cấu trúc sâu. Vì vậy cần xem:

- **Giới hạn kiểm tra body** và hành vi khi body vượt ngưỡng: block, allow, inspect một phần hay ghi nhận, tùy sản phẩm.
- **Giới hạn kích thước request/header**, timeout và cơ chế chống gửi request quá chậm.
- **File upload**: WAF không thay máy quét file, xác thực loại nội dung và xử lý an toàn trên server.
- **GraphQL/API JSON**: policy cần hiểu route và hợp đồng dữ liệu; query hợp lệ có thể chứa các chuỗi mà rule chữ ký nhận nhầm.
- **Webhook**: phải kiểm tra chữ ký hoặc xác thực peer tại lớp ứng dụng; chỉ lọc theo path không đủ.

Khi bật rule mới, cần kiểm thử các request hợp lệ có payload lớn, ký tự Unicode, phân trang, lặp retry và hình thức upload thực tế. Không chỉ dùng một request GET đơn giản để tuyên bố an toàn.

### 8.4. WebSocket, SSE và kết nối dài

WebSocket khởi đầu bằng cơ chế nâng cấp hoặc thiết lập kết nối tùy phiên bản HTTP, sau đó mang dữ liệu theo một cách khác request–response HTTP thường gặp. Một WAF có thể chỉ kiểm tra phần handshake, hoặc có thêm hỗ trợ kiểm tra frame tùy sản phẩm. Với **Server-Sent Events (SSE)** và các kết nối dài, cần chú ý buffering, idle timeout, keepalive và rate limit.

Nếu WAF chỉ kiểm tra handshake, **không** kết luận payload ứng dụng của WebSocket đã được phân tích toàn diện. Backend vẫn cần xác thực phiên, phân quyền từng thông điệp và giới hạn tài nguyên.

### 8.5. Cache và CDN

Khi WAF đi kèm CDN, cần xác định request nào được xử lý ngay ở edge cache, request nào đi qua WAF inspection và request nào tới reverse proxy. Quy tắc cache key, biến thể theo header/cookie, TTL và cache-control có thể ảnh hưởng tới dữ liệu riêng tư. Không cache phản hồi cá nhân như phản hồi công khai khi chưa có chính sách đúng; WAF không tự ngăn cache poisoning hoặc lộ dữ liệu do cấu hình cache sai.

## 9. Mô hình hóa mối đe dọa cho WAF trước reverse proxy

Đặt câu hỏi: **Tài sản nào cần bảo vệ? Ai có thể đi đến điểm đó? Tại điểm nào dữ liệu được giải mã, lọc, chuyển tiếp và ghi lại?** Lập threat model theo đường thực tế của request.

| ID | Đe dọa / thất bại | Điều kiện | Tác động | Giảm thiểu và phép thử |
| --- | --- | --- | --- | --- |
| T01 | Bypass WAF qua IP origin | Origin vẫn mở inbound từ Internet | Request không chịu policy WAF | Firewall/SG chỉ cho WAF được duyệt; thử direct-origin từ nguồn không được cấp phép |
| T02 | Giả IP client qua header | Proxy tin X-Forwarded-For của mọi nguồn | Log sai, rate limit có thể bị né hoặc gây chặn nhầm | Trust chain, header sanitization; thử header giả bằng dữ liệu lab |
| T03 | WAF → origin không kiểm tra TLS | WAF bỏ qua hostname/chứng chỉ | Tăng nguy cơ giả mạo/chèn sửa trên chặng origin | TLS verification, mTLS khi phù hợp; kiểm thử chứng chỉ sai ở lab |
| T04 | WAF và reverse proxy parse HTTP khác nhau | Phiên bản hoặc framing chuyển đổi không nhất quán | Request có thể bị diễn giải sai hoặc bypass một số chính sách | Vá parser, cấu hình thống nhất, kiểm thử tương thích |
| T05 | False positive đối với request hợp lệ | Managed rule quá rộng, body phức tạp | Gián đoạn giao dịch | Chế độ count, rà log theo rule ID và route; ngoại lệ hẹp |
| T06 | False negative với logic API | Request hợp lệ về cú pháp nhưng không có quyền | Rò rỉ hoặc thay đổi dữ liệu | Authorization tại API, kiểm thử quyền đối tượng |
| T07 | Rate limit nhầm theo IP NAT | Nhiều người dùng chia sẻ một public IP | Người dùng hợp lệ bị chặn | Chọn tín hiệu đáng tin, quota theo route/identity, theo dõi phân bố lỗi |
| T08 | Rule bỏ qua HTTP/3 hoặc hostname phụ | WAF không áp policy đồng nhất | Một nhóm luồng không được kiểm tra | Kiểm kê endpoint và HTTP versions, thử IPv4/IPv6/TCP/UDP |
| T09 | Log WAF lưu token/payload nhạy cảm | Bật full body/header logging không kiểm soát | Rò rỉ bí mật từ SOC/SIEM | Redaction, RBAC, retention, export policy, thử token giả |
| T10 | WAF lỗi hoặc upstream hết phiên | HA không đầy đủ, timeout/buffer sai | Gián đoạn dịch vụ | Failover, health check, năng lực xử lý, chế độ fail-open/closed được xác định rõ |

### 9.1. STRIDE trong kiến trúc

- **Spoofing:** giả IP client trong forwarded header, giả mạo origin hoặc peer không được xác thực.
- **Tampering:** sửa request trên chặng WAF–origin nếu kết nối không được bảo vệ; xử lý bất nhất dẫn đến request được diễn giải sai.
- **Repudiation:** không tương quan được WAF request ID, proxy trace ID và API log, khiến không thể xác minh nguồn phát một sự kiện.
- **Information disclosure:** log WAF lộ Authorization/Cookie hoặc dữ liệu cá nhân; kết nối sau WAF truyền rõ qua một vùng không đáng tin.
- **Denial of Service:** lưu lượng bất thường hoặc policy quá gắt làm nghẽn WAF/reverse proxy, khiến request hợp lệ bị chặn.
- **Elevation of privilege:** một request đã qua WAF khai thác quyền ứng dụng nếu API không kiểm tra quyền; WAF không thể thay cơ chế authorization.

### 9.2. Threat record mẫu: bypass trực tiếp origin

| Trường | Giá trị minh họa |
| --- | --- |
| Asset | API đơn hàng và thông tin khách hàng |
| Điểm yếu | Reverse proxy có IP origin công khai, cho phép nguồn Internet bất kỳ |
| Điều kiện | Tác nhân biết địa chỉ origin hoặc một hostname phụ |
| Đường lộ | Client → origin trực tiếp, không qua WAF |
| Tác động | WAF không ghi nhận/chặn request đi đường trực tiếp; tăng nguy cơ khai thác backend |
| Biện pháp | Hạn chế inbound tới WAF được duyệt, mTLS/origin auth nếu hỗ trợ, đóng port phụ và IPv6 path không cần thiết |
| Xác minh | Qua WAF hoạt động; truy cập trực tiếp origin từ nguồn ngoài allowlist thất bại; log chứng minh rule đúng |
| Owner | Nhóm mạng/edge phối hợp ứng dụng |
| Rủi ro còn lại | Tấn công trên đường được phép vẫn có thể xảy ra; backend cần bảo mật và phân quyền |

Việc bảo vệ origin nên được quản lý như một **kiểm soát độc lập** của WAF: WAF có thể phát hiện dấu hiệu rủi ro tốt nhưng vô nghĩa đối với request không đi qua nó.

## 10. Quy trình triển khai WAF trước reverse proxy

Triển khai WAF trong đường request chính có thể ảnh hưởng trực tiếp tới khách hàng. Một chính sách tốt cần kết hợp bảo vệ với **tính sẵn sàng và khả năng giải thích quyết định chặn**.

### Bước 1 — Kiểm kê đường vào và phụ thuộc

Trước khi chuyển DNS hoặc route qua WAF, ghi lại:

- Tên miền và API version: website, admin, API đối tác, staging và endpoint đặc biệt.
- Tất cả port và giao thức: TCP/443, HTTP redirect ở 80 nếu có, UDP/443 cho HTTP/3, WebSocket, health check.
- Điểm kết thúc TLS: client–WAF, WAF–origin, reverse proxy–backend; chứng chỉ và hostname của mỗi chặng.
- Dải IP nguồn được mong đợi từ WAF, đường quản trị được phê duyệt, nơi thiết lập trust header.
- Timeout, giới hạn body/header, cỡ file upload, reverse proxy buffering và kết nối dài.
- Phụ thuộc ngoài: DNS, identity provider, webhook đối tác, CDN, cloud load balancer và SOC.

Kết quả cần có là **sơ đồ luồng và danh sách endpoint** được bảo vệ cùng chủ sở hữu từng dịch vụ.

### Bước 2 — Baseline lưu lượng hợp lệ

Thu thập thống kê trong một giai đoạn đại diện (bao gồm giờ cao điểm và các tác vụ định kỳ): method, route, content type, kích thước request, tốc độ gọi, tỷ lệ lỗi theo client/region, lưu lượng bot hợp lệ và các trường hợp upload. Dùng log đã loại bỏ thông tin cá nhân hoặc credential không cần thiết.

Không tự coi một request đã xảy ra trước đây là an toàn. Mục đích baseline là **hiểu hành vi của ứng dụng**, sau đó đối chiếu với tài liệu API và mô hình đe dọa để quyết định điều gì thực sự nên được cho phép.

### Bước 3 — Bật chế độ quan sát / count

Nếu nền tảng hỗ trợ, bắt đầu managed rules ở chế độ **log/count/detection-only** để đánh giá tác động mà chưa chặn request nghiệp vụ. So sánh tín hiệu rule với log của reverse proxy và API theo request ID, thời điểm và route.

**Chế độ log/count không đảm bảo dữ liệu được bảo vệ khỏi cuộc tấn công đang xảy ra**. Với hệ thống đã có đe dọa nghiêm trọng hoặc endpoint nhạy cảm, chọn chính sách phòng vệ tương xứng sau khi đánh giá rủi ro; không kéo dài quan sát vô thời hạn.

### Bước 4 — Áp chính sách theo phạm vi nhỏ

Ưu tiên hostname/route có rủi ro và hợp đồng request rõ. Cấu hình các hành động cụ thể:

~~~yaml
# Policy minh họa; không phải cấu hình thực thi của sản phẩm WAF.
site: api.example.test
default_action: inspect_then_forward
rules:
  - name: managed-common-threats
    scope: host
    mode: count_first_then_block_after_review
    owner: security
  - name: order-api-methods
    scope: /v1/orders
    allowed_methods: [GET, POST]
    action_on_unexpected_method: block
    owner: orders-team
  - name: partner-webhook
    scope: /webhooks/vendor
    required_application_auth: webhook-signature-verified-by-backend
    browser_challenge: disabled
    owner: integration-team
  - name: temporary-rule-exception
    scope: /v1/products
    condition: reviewed-false-positive-only
    expiry: require-review-date
    owner: security-and-web-team
origin:
  require_approved_waf_path: true
  require_valid_tls_certificate: true
  enable_request_id_correlation: true
~~~

Chính sách minh họa nhấn mạnh **phạm vi, hành động, người phụ trách và điều kiện kiểm chứng**. Phần xác thực chữ ký webhook vẫn phải được triển khai tại backend hoặc thành phần thực sự có năng lực xác minh chữ ký. Không giả định WAF hiểu các khóa YAML minh họa ở trên.

### Bước 5 — Chuyển dần sang block có kiểm soát

Chuyển những rule đã đánh giá từ count sang block, có thể theo endpoint, nhóm client hoặc tỷ lệ traffic khi công nghệ hỗ trợ. Trước mỗi bước, chuẩn bị:

1. **Test allow**: đăng nhập, gọi API, upload, checkout, webhook, WebSocket và traffic cao điểm giả lập.
2. **Test deny**: các điều kiện bị từ chối theo chính sách an toàn, nguồn không được phép tới origin và rate limit được kiểm thử trong lab.
3. **Tín hiệu rollback**: ngưỡng lỗi 4xx/5xx, suy giảm giao dịch hoặc thay đổi latency vượt giới hạn đã thống nhất.
4. **Người phụ trách**: ứng dụng, edge/network, bảo mật và đơn vị giám sát theo quy trình tổ chức.
5. **Phương án khôi phục**: hoàn tác rule WAF gây lỗi theo phiên bản, giữ đường kết nối qua WAF và tiếp tục bảo vệ origin trong điều kiện có thể.

Đối với rule chặn nhầm, **tắt hoặc thu hẹp rule cụ thể** thường tốt hơn chuyển toàn bộ người dùng đi trực tiếp tới origin. Một thay đổi khẩn cấp vẫn cần log, thời hạn ngoại lệ và người chịu trách nhiệm.

### Bước 6 — Duy trì, cập nhật và quản lý thay đổi

WAF policy là cấu hình cần vòng đời như mã nguồn: lưu phiên bản, diff, reviewer, owner, rollback, log thay đổi và ngày kiểm tra lại. Khi ứng dụng thêm API, thay JSON schema, bật HTTP/3, chuyển CDN, thay reverse proxy hoặc mở endpoint đối tác, cần rà soát WAF và origin policy.

Các **managed rule** cũng có thể thay đổi hành vi khi nhà cung cấp cập nhật: cần theo dõi phiên bản/quy tắc mới, tần suất false positive và các ngoại lệ cũ không còn thích hợp.

## 11. Quan sát, log và tiêu chí đánh giá

### 11.1. Tương quan WAF, reverse proxy và backend

Một yêu cầu được cho phép có thể đi qua nhiều hệ thống và tạo nhiều bản ghi:

~~~text
Client -> WAF -> Reverse proxy -> App API -> Database

WAF event:       event_time, request_id, host, route, rule_id, action
Reverse proxy:   request_id, direct_peer_ip, verified_client_ip, upstream, status
App telemetry:   request_id/trace_id, principal_id (pseudonymized), route, result
Network logs:    src/dst IP:port, protocol, allow/deny, interface/zone
~~~

WAF có thể chặn request **trước khi reverse proxy thấy nó**. Vì vậy không xuất hiện request trong access log của reverse proxy là điều bình thường với một event bị block tại edge. Ngược lại, một response 403 do API trả về có thể đã đi qua WAF hoàn toàn hợp lệ.

Tạo hoặc chuyển tiếp một **request ID đáng tin** và liên kết với trace ID ở backend. Nếu client tự gửi một request ID, cần kiểm tra định dạng/độ dài và tránh để nó gây xung đột hoặc chèn dữ liệu log. Timestamp, timezone và đồng bộ thời gian quan trọng khi tương quan các hệ thống.

### 11.2. Log đủ để xử lý sự cố nhưng không lộ bí mật

| Nên ghi | Cần hạn chế hoặc che |
| --- | --- |
| Thời điểm, hostname, route mẫu, method, mã phản hồi | Access token, password, session cookie, Authorization header |
| Rule ID, action: allow/count/block/challenge | Full request/response body có dữ liệu cá nhân hoặc thanh toán |
| Request/trace ID, upstream service, latency | Query parameter nhạy cảm, nội dung file upload |
| IP peer và IP client đã xác minh theo nhu cầu | Header do client tự khai chưa được xác minh và có thể gây log injection |
| Phiên bản policy, owner và lý do ngoại lệ | Private key, credential từ hệ thống tích hợp |

Hệ thống **WAF, reverse proxy, SIEM, APM và packet capture** đều có thể trở thành kho dữ liệu nhạy cảm. Cần redaction ngay từ nguồn khi có thể, quyền xem log tối thiểu, mã hóa lưu trữ/truyền, retention phù hợp và kiểm soát export. Khi thử khả năng redaction, chỉ dùng **token giả trong lab**.

### 11.3. Chỉ số đánh giá

| Chỉ số | Cách sử dụng | Điều không nên suy diễn |
| --- | --- | --- |
| Số request WAF cho phép/chặn/challenge | Theo dõi thay đổi chính sách và bất thường theo route | Nhiều block không tự động chứng minh hiệu quả an ninh cao |
| False-positive rate có xác minh | Giảm gián đoạn request hợp lệ | Không kết luận mọi 403 đều là false positive |
| 4xx/5xx và tỷ lệ giao dịch thành công | Đánh giá tác động tới khách hàng | 403 từ API không nhất thiết do WAF |
| Latency p50/p95/p99 qua WAF và origin | Theo dõi hiệu năng và nghẽn | Không quy nguyên nhân cho WAF nếu chưa tách từng chặng |
| Origin direct access denied | Bằng chứng đường bypass bị chặn | Một phép thử IPv4 không chứng minh IPv6/cổng phụ đã an toàn |
| Rate-limit 429, challenge pass/fail | Điều chỉnh quota và trải nghiệm client | Client sau CGNAT có thể chia sẻ IP |
| Rule coverage theo host/path/protocol | Phát hiện endpoint chưa chịu policy | WAF coverage không thay API authorization |
| TLS handshake/cert errors chặng origin | Giám sát kết nối WAF–proxy | HTTPS client hoạt động không bảo đảm mọi origin upstream an toàn |

Cần có baseline trước khi thay đổi và theo dõi sau khi áp rule. Khi hệ thống đa vùng hoặc có failover, tổng hợp theo **đúng WAF instance/edge location và origin pool** để tránh bỏ sót một khu vực cấu hình khác.

## 12. Thực hành kiểm thử có kiểm soát

Chỉ thực hiện trên hệ thống lab hoặc dịch vụ được phép kiểm thử. Tên miền **api.example.test** và các dải **192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24** là địa chỉ dùng cho tài liệu; thay bằng domain/IP của môi trường lab trước khi chạy. Không gửi payload khai thác hoặc quét ngoài phạm vi.

### 12.1. Kiểm tra đường đi qua WAF và TLS

Trong lab có DNS và chứng chỉ hợp lệ:

~~~bash
curl -vI https://api.example.test/health
curl --http1.1 -I https://api.example.test/health
curl --http2 -I https://api.example.test/health
~~~

Quan sát phiên bản HTTP được thương lượng (nếu bản build curl hỗ trợ), chứng chỉ của kết nối phía client, status, response headers và thời gian phản hồi. Gói tin phía client chỉ cho thấy **TLS client–WAF**, không trực tiếp chứng minh WAF–origin đã được mã hóa; cần bằng chứng từ cấu hình và log/telemetry chặng sau.

Nếu có hỗ trợ HTTP/3, kiểm tra riêng **UDP/443 và QUIC** bằng client phù hợp. Không hỗ trợ HTTP/3 ở client không chứng minh WAF hoặc origin có lỗi.

### 12.2. Thử điều kiện chặn an toàn bằng rule lab

Để kiểm chứng đường chặn mà không sử dụng payload tấn công, tạo một **custom WAF rule chỉ trong lab**: từ chối request mang header thử nghiệm có giá trị cố định. Ví dụ về logic:

~~~text
Rule LAB-ONLY:
  IF hostname == api.example.test
     AND header X-Lab-WAF-Test == deny-demo
  THEN BLOCK
  ELSE continue with normal inspection
~~~

Sau khi rule được áp dụng trong lab:

~~~bash
curl -i https://api.example.test/health
curl -i -H "X-Lab-WAF-Test: deny-demo" https://api.example.test/health
~~~

Request bình thường phải tiếp tục đến backend nếu các điều kiện còn lại cho phép. Request mang header thử nghiệm phải bị WAF từ chối theo **hành động/status đã cấu hình**, và có WAF event tương ứng; nó thường **không** có access log backend nếu chặn trước proxy. Không giả định mọi sản phẩm trả đúng 403 hoặc có cùng cơ chế rule; gỡ rule demo sau khi hoàn thành kiểm thử.

### 12.3. Xác minh không đi vòng WAF

Trong lab, kiểm tra từ một client **không nằm trong danh sách nguồn WAF được phép**:

1. Gọi domain chuẩn qua WAF: đường đi hợp lệ phải hoạt động.
2. Gọi trực tiếp IP/port origin theo cấu hình lab: kết nối phải bị từ chối ở ranh giới origin nếu thiết kế cấm direct-origin.
3. Lặp lại theo hostname phụ, cổng phụ, IPv4/IPv6 và vùng dự phòng nếu tồn tại.
4. Kiểm tra firewall/SG/flow log để chứng minh request trực tiếp đã gặp đúng rule deny, không chỉ timeout vì backend chưa chạy.
5. Với mTLS ở chặng origin, thử client test không có chứng chỉ được cấp quyền; kết nối phải không được xác thực.

Không sử dụng public IP lạ lấy từ một dịch vụ thực để “thử bypass”. Hãy dùng địa chỉ origin được quản trị viên cung cấp và quyền kiểm thử rõ ràng.

### 12.4. Xác minh header chuyển tiếp

Trong lab, gửi một request thử có **X-Forwarded-For giả** và so sánh log:

~~~bash
curl -i -H "X-Forwarded-For: 192.0.2.123" \
  https://api.example.test/health
~~~

Hệ thống phải xác định IP client đáng tin theo kết nối tới WAF/chuỗi proxy, không coi 192.0.2.123 là IP client thực chỉ vì người dùng gửi header đó. Kết quả cần được kiểm tra ở reverse proxy và ứng dụng, nhất là nếu rate limit sử dụng IP client đã chuẩn hóa.

### 12.5. Ma trận kiểm thử

| ID | Luồng / kịch bản | Kỳ vọng | Bằng chứng cần thu |
| --- | --- | --- | --- |
| T01 | Client hợp lệ → WAF → proxy → API | ALLOW | WAF request ID, proxy log, API response |
| T02 | Request có marker của rule lab | BLOCK | WAF rule hit, backend không xử lý |
| T03 | Client không được phép → IP origin trực tiếp | DENY tại origin boundary | Firewall/SG deny log, không có phiên tới origin |
| T04 | WAF → proxy qua TLS hợp lệ | ALLOW | Chứng chỉ origin được xác minh, session log |
| T05 | Kết nối không có origin authentication được yêu cầu | DENY | TLS/mTLS failure hoặc policy deny theo thiết kế |
| T06 | Client gửi X-Forwarded-For giả | Không làm sai IP client đã xác minh | WAF/proxy/app correlation |
| T07 | API JSON hợp lệ với ký tự đặc biệt | ALLOW | Tỷ lệ thành công, không false positive |
| T08 | Upload hợp lệ theo giới hạn | ALLOW | Route, size, MIME, backend success |
| T09 | Webhook được xác thực | ALLOW, không browser challenge | Request ID, backend signature check |
| T10 | Rate limit lab vượt ngưỡng cấu hình | Giới hạn request theo policy | Rule/action, timing, phản hồi client |
| T11 | WebSocket/SSE hợp lệ | Hoạt động trong timeout/chính sách | Handshake, kết nối dài và app telemetry |
| T12 | HTTP/2 hoặc HTTP/3 nếu được hỗ trợ | Chính sách nhất quán theo đường công bố | Negotiation, rule hit, đường origin |
| T13 | API không có quyền với đối tượng | Ứng dụng trả từ chối phù hợp | App authorization log, không coi WAF thay quyền |
| T14 | DNS/hostname phụ và IPv6 origin | Không có đường bypass ngoài phạm vi | A/AAAA, route, origin deny log |

**Kết quả kỳ vọng** phải được so sánh với kết quả thực tế. Với test deny, timeout đơn lẻ chưa phải bằng chứng vì có thể do route, listener hoặc DNS hỏng. Các phép thử cần ghi thời điểm, nguồn, WAF policy version, rule ID, đường network và người kiểm tra.

## 13. Khắc phục sự cố khi WAF nằm trước reverse proxy

### 13.1. Phân biệt lỗi tại WAF, reverse proxy và ứng dụng

| Triệu chứng | Khả năng gây ra | Cách kiểm tra |
| --- | --- | --- |
| Client nhận phản hồi chặn 403 | WAF, reverse proxy hoặc API đều có thể trả 403 | Request ID, response headers đã xác minh, rule hit và log từng điểm |
| 429 sau khi tải tăng | Rate limit tại WAF, gateway hoặc API | Quota, client IP đáng tin, route, retry và thời điểm |
| WAF cho phép nhưng origin trả 502/504 | Backend không sẵn sàng, lỗi DNS/route/TLS/timeout từ WAF hoặc proxy | Upstream connection status, TLS handshake, health check, log origin |
| Client báo chứng chỉ đúng nhưng WAF không kết nối origin | Chứng chỉ/SNI/hostname ở chặng WAF–origin sai | Xác minh chứng chỉ riêng của origin và cấu hình WAF |
| Chỉ một nhóm IP bị chặn | Reputation/geolocation, rule nguồn, IPv6 hoặc rate limit | Rule ID, IP đã xác minh, chính sách theo đối tượng |
| API máy-máy bị yêu cầu CAPTCHA | Bot challenge áp quá rộng | Loại client/route, xác thực API và ngoại lệ hẹp |
| Upload lớn thất bại | Body inspection limit, proxy max-body-size, buffering/timeout | Giới hạn tại cả WAF, reverse proxy, backend |
| WebSocket ngắt sau một thời gian | Idle timeout, handshake rule, thiết lập upgrade, gateway | Log kết nối dài và khả năng WebSocket của từng điểm |
| Client gửi header X-Forwarded-For vẫn “đổi IP” ở log | Proxy tin header từ nguồn không được tin cậy | Trust list, header overwrite, log peer trực tiếp |
| Gọi domain đúng qua WAF bị block nhưng IP origin vẫn chạy | Origin chưa bị giới hạn nguồn | SG/firewall origin, IPv4/IPv6, cổng và hostname phụ |
| 200 từ API nhưng dữ liệu vượt quyền | Lỗi authorization ứng dụng | API authorization và bài test đối tượng, không phụ thuộc WAF |
| Một vùng cloud vẫn chạy policy cũ | Drift cấu hình, failover qua edge khác | Phiên bản policy và route từng edge/origin |

### 13.2. Sơ đồ chẩn đoán theo request ID

~~~mermaid
flowchart TD
    A["Request không đạt kỳ vọng"] --> B{"Có WAF event tương ứng?"}
    B -- "Không" --> B1["Kiểm tra DNS, endpoint, TLS trước WAF và đường bypass"]
    B -- "Có" --> C{"WAF action: block/challenge?"}
    C -- "Có" --> C1["Đọc rule ID, điều kiện khớp, route, policy version"]
    C -- "Không" --> D{"Reverse proxy có request?"}
    D -- "Không" --> D1["Kiểm tra WAF-origin route, TLS, DNS và firewall"]
    D -- "Có" --> E{"Backend có request?"}
    E -- "Không" --> E1["Kiểm tra proxy routing, header, upstream và timeout"]
    E -- "Có" --> F{"Ứng dụng xử lý và phân quyền đúng?"}
    F -- "Không" --> F1["Xem authn/authz, API log, dữ liệu và nghiệp vụ"]
    F -- "Có" --> G["So sánh response, latency và telemetry các chặng"]
~~~

Trước khi thay đổi rule, hãy xác định **yêu cầu nào, tại thời điểm nào, qua hostname nào, từ nguồn nào và bị thành phần nào từ chối**. Các status code chỉ là gợi ý ban đầu. Một lỗi 403 từ backend thường cần nhóm ứng dụng phân tích quyền; một request bị WAF block không nhất thiết đã tới backend.

### 13.3. Xử lý false positive

Ví dụ người dùng tìm kiếm sản phẩm có dấu ngoặc hoặc ký tự SQL thông thường trong tên mặt hàng. Managed rule coi request là nghi vấn và chặn, khiến giao dịch thất bại.

Quy trình:

1. Xác minh request **hợp lệ và thuộc hoạt động được cấp quyền**; ghi WAF request ID, rule ID, host/path và mẫu dữ liệu đã ẩn nhạy cảm.
2. Đối chiếu với tài liệu input/API và backend logs; xác định rule khớp vì tham số nào.
3. Thử nghiệm ngoại lệ **chỉ với rule/parameter/route liên quan**, không mở toàn bộ endpoint cho mọi kiểm soát.
4. Kiểm tra lại request hợp lệ và trường hợp cần bị chặn trong môi trường thử.
5. Ghi owner, lý do, phiên bản rule, thời hạn review và mức rủi ro còn lại.

Nếu ứng dụng thay hợp đồng API, có thể cần sửa parser hoặc xác thực dữ liệu tại backend thay vì dựa hoàn toàn vào WAF exclusion.

### 13.4. Khi origin bị từ chối nhầm

Nếu WAF đã được cấu hình đúng nhưng reverse proxy từ chối kết nối từ edge, kiểm tra danh sách endpoint WAF được phép, bản cập nhật IP của nhà cung cấp, mTLS/chứng chỉ, route và quy tắc firewall. Đừng mở reverse proxy từ **0.0.0.0/0** để “sửa nhanh” rồi quên thu hẹp; giải pháp phù hợp là xác định chính xác nguồn WAF và điều kiện xác thực, triển khai, kiểm chứng và lưu lại thay đổi.

### 13.5. Fail-open, fail-closed và tính sẵn sàng

Khi WAF hoặc chặng origin gặp lỗi, một số kiến trúc cho phép cấu hình **fail-open** (bỏ qua một số kiểm soát để duy trì dịch vụ) hoặc **fail-closed** (ngừng nhận traffic khi không bảo đảm kiểm soát). Khả năng cụ thể khác nhau theo sản phẩm.

| Lựa chọn | Lợi ích | Rủi ro | Phạm vi cân nhắc |
| --- | --- | --- | --- |
| Fail-closed | Giữ ranh giới bảo vệ theo chính sách | Có thể gián đoạn dịch vụ | Dữ liệu/ứng dụng có rủi ro cao, không cho bỏ qua kiểm soát |
| Fail-open có điều kiện | Có thể duy trì một phần dịch vụ | Có thể tạo cửa sổ traffic không được WAF phân tích | Chỉ khi được đánh giá/phê duyệt, có giới hạn, cảnh báo và phương án phục hồi |
| Chuyển sang WAF/edge dự phòng | Giữ kiểm soát và nâng availability nếu thiết kế tốt | Rủi ro policy khác biệt giữa các vùng | HA đa vùng, đồng bộ chính sách, kiểm thử failover |

Lựa chọn phải dựa trên mục tiêu **Confidentiality, Integrity, Availability**, khả năng phát hiện thay đổi và quy trình ứng cứu. Tránh dùng đường bypass origin như cơ chế mặc định khi WAF quá tải, vì nó vô hiệu hóa kiểm soát đang được thiết kế để bảo vệ ứng dụng.

## 14. Tình huống kiến trúc tổng hợp

Một doanh nghiệp triển khai:

~~~text
Người dùng Internet
        |
        v
Cloud WAF/CDN (public endpoint, TLS)
        |
        v
Reverse proxy (DMZ, HTTPS từ WAF)
        |
        v
API Gateway / Order API
        |
        v
Database nội bộ
~~~

Trong đợt review, nhóm bảo mật phát hiện:

- DNS chuẩn đã trỏ tới WAF nhưng reverse proxy còn một IP public dùng khi triển khai.
- Reverse proxy lấy phần tử đầu tiên trong X-Forwarded-For làm client IP, không kiểm tra source kết nối.
- Webhook từ đối tác đôi khi bị bot challenge, khiến giao dịch hợp lệ không đến ứng dụng.
- WAF ghi request header đầy đủ vào SIEM, bao gồm Authorization của API.
- TLS client–WAF đã hợp lệ nhưng WAF–reverse proxy tạm bật bỏ qua xác minh chứng chỉ origin.

### 14.1. Phân tích theo thứ tự ưu tiên

| Phát hiện | Nguy cơ chính | Việc xử lý cụ thể | Xác minh |
| --- | --- | --- | --- |
| Origin công khai trực tiếp | WAF bị bypass | Chặn nguồn Internet trực tiếp, chỉ nhận WAF đáng tin; cân nhắc origin mTLS | Domain qua WAF còn hoạt động, direct origin bị từ chối trên IPv4/IPv6 |
| Tin X-Forwarded-For tùy ý | Giả IP nguồn, làm sai rate limit và log | Cấu hình trusted proxies, loại bỏ header không tin cậy, chọn client IP đúng | Header giả không thay đổi verified client IP |
| Bot challenge chặn webhook | Gián đoạn giao dịch | Policy riêng cho route webhook, xác thực chữ ký/mTLS và quota theo hợp đồng | Webhook hợp lệ hoạt động, request sai xác thực bị backend từ chối |
| Log Authorization nguyên văn | Lộ bí mật xác thực | Redact header từ nguồn, thu hẹp quyền xem/export, xử lý log lịch sử theo chính sách | Token giả không có trong log mới; truy cập log được kiểm soát |
| WAF bỏ xác minh chứng chỉ origin | Không xác thực đúng kết nối tới reverse proxy | Bật verify hostname/chứng chỉ, quản lý CA/SNI và mTLS nếu phù hợp | TLS hợp lệ hoạt động; chứng chỉ sai thất bại trong lab |

Giải pháp cần liên kết **đường mạng**, **cấu hình WAF**, **reverse proxy**, **authorization ứng dụng**, **lưu trữ log** và **quy trình thay đổi**. Chỉ bật thêm một rule chữ ký sẽ không xử lý được các rủi ro về origin bypass, TLS hoặc thông tin header không đáng tin.

### 14.2. Kế hoạch kiểm chứng sau thay đổi

1. Kiểm tra bản đồ DNS/IPv4/IPv6 và mọi hostname trước, sau WAF.
2. Xác thực hai chặng TLS, chứng chỉ, hostname, SNI và quyền truy cập origin.
3. Từ client được phép và client nằm ngoài nguồn được phép, kiểm tra đường qua WAF và direct-origin.
4. Phát request với forwarded header giả trong lab, đối chiếu IP đã xác minh ở edge/proxy/API.
5. Kiểm tra webhook hợp lệ, request có chữ ký không hợp lệ và điều kiện rate limit.
6. Dùng token giả rà log tại WAF, SIEM, reverse proxy và APM.
7. Xem transaction success, 4xx/5xx, p95 latency và WAF rule hit sau rollout.
8. Lưu bằng chứng, owner, phiên bản policy và rủi ro còn lại cho lần review tiếp theo.

## 15. Bài tập thiết kế và câu hỏi ôn tập

### 15.1. Bài tập thiết kế

Hãy thiết kế một hệ thống **WAF trước reverse proxy** cho website và API đơn hàng có thêm cổng quản trị, upload tài liệu, webhook đối tác, CDN cache, HTTP/3 cho trình duyệt và API nội bộ xử lý thanh toán.

Yêu cầu nộp:

1. **Sơ đồ kiến trúc** có WAF, DNS, reverse proxy, API, database, log/SOC và các vùng tin cậy; đánh dấu nơi TLS kết thúc.
2. **Ma trận ít nhất 10 luồng** với nguồn, đích, giao thức/cổng, đường qua WAF hoặc kết nối nội bộ và quyết định allow/deny.
3. **Kế hoạch bảo vệ origin** bằng firewall/SG, TLS xác thực, hostname, IPv4/IPv6, port phụ và đường truy cập quản trị.
4. **Policy theo route** cho API công khai, upload, webhook và cổng quản trị; có phân biệt managed rule, rate limit, challenge và xác thực backend.
5. **Quy trình xử lý forwarded headers** khi hệ thống có hai proxy và client có thể tự gửi X-Forwarded-For.
6. **Bộ 5 test allow và 5 test deny** gồm trường hợp bypass origin, header giả, rule lab, API thiếu quyền và payload hợp lệ gây false positive.
7. **Quy trình rollout** từ quan sát đến chặn, telemetry theo request ID, owner, exception expiry và rollback.

Tiêu chí đạt: không có đường direct-origin ngoài phạm vi được duyệt; TLS và identity được kiểm tra tại đúng chặng; WAF không được coi là giải pháp thay authorization; log không lưu secret không cần thiết; các ngoại lệ có lý do và bằng chứng.

### 15.2. Câu hỏi tự kiểm tra

**Câu 1.** Nếu DNS tên miền đã trỏ tới Cloud WAF, liệu mọi request tới origin đều qua WAF?

*Gợi ý:* Không nhất thiết. IP origin, cổng phụ, bản ghi DNS cũ hoặc IPv6 có thể tạo đường trực tiếp; phải chặn bằng network policy và xác thực origin phù hợp.

**Câu 2.** Vì sao client có HTTPS hợp lệ vẫn chưa chứng minh WAF–reverse proxy an toàn?

*Gợi ý:* Đây là hai kết nối TLS riêng. Phải xác minh mã hóa, chứng chỉ, hostname và peer tại chặng từ WAF đến origin.

**Câu 3.** Reverse proxy thấy IP nguồn TCP của WAF. Có thể tin X-Forwarded-For đầu tiên để lấy IP client không?

*Gợi ý:* Chỉ được trích xuất thông tin theo quy tắc chuỗi proxy đáng tin. Header do client tự gửi phải được làm sạch/chuẩn hóa; không mặc định phần tử đầu luôn xác thực.

**Câu 4.** WAF đã cho phép request TCP/443, vậy API có cần kiểm tra quyền xem đơn hàng không?

*Gợi ý:* Có. WAF không biết đầy đủ quyền nghiệp vụ của từng người dùng và từng đơn hàng.

**Câu 5.** Vì sao cần phân biệt WAF trả 403 với API trả 403?

*Gợi ý:* Vị trí từ chối khác nhau dẫn đến cách xử lý khác nhau. Cần WAF event, request ID và access log proxy/backend để xác định nơi quyết định.

**Câu 6.** Một webhook bị CAPTCHA dù có chữ ký hợp lệ. Nên tắt WAF cho mọi URL của ứng dụng?

*Gợi ý:* Không. Thiết kế policy theo route cho webhook, xác thực chữ ký ở backend, quota thích hợp và tránh challenge đòi trình duyệt trên API máy-máy.

**Câu 7.** WAF kiểm tra HTTP/3 ở edge nhưng gửi HTTP/1.1 tới reverse proxy có thể gây vấn đề gì?

*Gợi ý:* Cần kiểm soát việc chuyển giao thức và tính nhất quán của cách xử lý header, path, request framing và các giới hạn tại mỗi chặng.

**Câu 8.** Vì sao việc log toàn bộ body request để “phân tích bảo mật tốt hơn” có thể nguy hiểm?

*Gợi ý:* Body/header có thể chứa mật khẩu, token, dữ liệu cá nhân hoặc thanh toán. Cần thu thập tối thiểu, redaction và quyền đọc/export chặt chẽ.

## 16. Những điểm cần ghi nhớ

- **WAF trước reverse proxy** có nghĩa request Internet được đánh giá theo chính sách WAF trước khi vào proxy và backend; đây là quyết định về **thứ tự xử lý và ranh giới tin cậy**.
- Nếu WAF cần phân tích nội dung HTTPS, nó phải có khả năng **đọc HTTP đã giải mã** tại điểm phù hợp. TLS client–WAF và TLS WAF–origin là các kết nối riêng cần bảo vệ.
- **Bảo vệ origin khỏi đường bypass** là yêu cầu then chốt: DNS trỏ vào WAF chưa đủ, cần mạng/firewall, xác thực peer, kiểm tra IPv4/IPv6, hostname và cổng phụ.
- Chỉ tin **IP client và forwarded headers** sau khi xác minh chuỗi proxy; header do client tự khai không được dùng làm bằng chứng danh tính hoặc khóa rate limit tin cậy.
- **Managed rules, custom rules, rate limits và bot control** phải được điều chỉnh theo endpoint, loại client và lưu lượng hợp lệ; tránh ngoại lệ rộng và false positive gây gián đoạn.
- **HTTP/2, HTTP/3, JSON, multipart upload, WebSocket và chuyển đổi protocol** đòi hỏi kiểm thử đúng đường đi; phạm vi inspect thực tế tùy WAF và proxy.
- WAF bổ trợ cho **firewall, IDS/IPS, phân đoạn, TLS/mTLS và bảo mật ứng dụng**. Nó không thay xác thực, authorization, bảo vệ dữ liệu và kiểm soát quyền ở backend.
- Đưa WAF vào vận hành cần **baseline, log/count, rollout theo giai đoạn, test allow/deny, request ID, redaction, cảnh báo, owner và phương án rollback**.

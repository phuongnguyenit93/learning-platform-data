# Header forwarding và kiểm soát X-Forwarded-For: Xác định đúng client sau reverse proxy

## 1. Tại sao header forwarding là vấn đề bảo mật?

Trong hạ tầng hiện đại, request hiếm khi đi trực tiếp từ trình duyệt đến ứng dụng. Nó thường qua **CDN, WAF, reverse proxy, load balancer, ingress controller, API gateway hoặc service mesh**. Mỗi thành phần có thể kết thúc TLS, chọn backend, thực thi chính sách và chuyển tiếp thông tin của request bằng **HTTP headers**.

Khi TCP connection tới ứng dụng xuất phát từ reverse proxy, địa chỉ IP mà ứng dụng quan sát ở **socket peer** là IP của proxy, không còn là địa chỉ IP client kết nối vào ranh giới đầu tiên. Vì vậy, các triển khai thường dùng `X-Forwarded-For` (XFF) để truyền thông tin về những địa chỉ đã đi qua. Nhưng **HTTP request headers có thể được client tự tạo**. Nếu ứng dụng tin mọi giá trị XFF mà không xác minh đường đi, attacker có thể giả mạo “IP client” trên log, vượt qua chính sách giới hạn tốc độ hoặc cố gây nhầm lẫn trong kiểm soát truy cập.

Ví dụ, client trực tiếp gửi:

~~~http
GET /api/orders HTTP/1.1
Host: shop.example.test
X-Forwarded-For: 10.9.9.9
~~~

`10.9.9.9` chỉ là **văn bản trong header**, không chứng minh request đến từ máy sở hữu IP đó. Ứng dụng chỉ có thể coi thông tin forward là đáng tin **nếu đường truyền thực tế và các proxy trung gian được kiểm soát đúng cách**.

Chủ đề thuộc chương **Proxy reverse proxy và cân bằng tải**, module **SECURITY_NETWORK_SECURITY**. Kiểm soát header forwarding liên quan trực tiếp tới firewall và segmentation, VPN, IDS/IPS, NAC, DNS, TLS termination, load balancing và giám sát truy cập: đường mạng xác định ai có thể nối tới proxy; proxy phải xử lý header đúng; ứng dụng cần dùng **danh tính client đã chuẩn hóa** một cách nhất quán.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích sự khác biệt giữa **socket peer IP**, **client IP đã xác minh**, **X-Forwarded-For** và chuỗi proxy hops.
2. Đọc được các header `X-Forwarded-For`, `X-Real-IP`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `Forwarded` và hiểu những giới hạn của chúng.
3. Mô tả **trust boundary**: edge tin cậy tạo header, proxy trung gian nối chuỗi, backend chỉ tin các hop được ủy quyền.
4. Nhận diện các lỗi như **spoof XFF, direct-to-origin bypass, host/proto header poisoning, trust proxy quá rộng và log sai**.
5. Hiểu những tùy chọn Nginx `proxy_set_header`, `$proxy_add_x_forwarded_for`, `real_ip_header`, `set_real_ip_from`, `real_ip_recursive`.
6. Áp dụng nguyên tắc tương đương vào ứng dụng/framework, CDN, Kubernetes ingress và load balancer mà không đồng nhất các nhà cung cấp.
7. Xây ma trận kiểm thử header hợp lệ/giả mạo, đo tác động lên rate limiting, WAF, audit và các chức năng ứng dụng.

> **Giới hạn thực hành:** các tên miền `example.test` và IP `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` chỉ để minh họa. Những bài test gửi header tùy chỉnh chỉ được thực hiện trên **lab hoặc dịch vụ được cấp quyền**. Không dùng các ví dụ để thử vượt rate limit, bypass IP allowlist hoặc làm sai log của dịch vụ bên thứ ba.

## 2. Từ TCP peer đến địa chỉ client được tin cậy

### 2.1. Mô hình có nhiều hop

~~~mermaid
flowchart LR
    C["Client<br/>198.51.100.24"] --> E["CDN/WAF edge<br/>203.0.113.10"]
    E --> L["Load balancer<br/>10.20.0.10"]
    L --> P["Reverse proxy<br/>10.20.0.20"]
    P --> A["Application<br/>10.30.0.30"]
    F["Firewall / origin ACL"] -. "Chỉ cho trusted hops truy cập" .-> P
    P -. "Header đã chuẩn hóa" .-> A
~~~

Trong sơ đồ:

- **Client thực:** `198.51.100.24`, chỉ là địa chỉ mà edge quan sát trong kịch bản giả định, chưa nhất thiết là người dùng cuối duy nhất vì còn NAT, CGNAT hoặc corporate proxy.
- **Edge:** nhận kết nối từ bên ngoài và là điểm bắt đầu **chuỗi tin cậy**. Edge phải xác định địa chỉ nguồn kết nối thật và xử lý header đến từ vùng không tin cậy.
- **Load balancer:** nhận request từ edge; có thể thêm thông tin peer mà nó trực tiếp nhìn thấy.
- **Reverse proxy:** tiếp tục chuyển request và các thông tin đã kiểm soát về ứng dụng.
- **Application:** thấy socket peer là reverse proxy; không nên sử dụng một header tùy ý làm danh tính mạng nếu chưa có chính sách xác minh hop.

### 2.2. Những giá trị dễ bị nhầm lẫn

| Giá trị | Nguồn thông tin | Có thể tin ngay? | Dùng để làm gì? |
|---|---|---|---|
| **TCP peer IP / remote address** | Địa chỉ của kết nối đến ở tầng vận chuyển | Là địa chỉ peer của kết nối đang quan sát, **không chắc là người dùng cuối** | Kiểm tra nguồn kết nối, trust boundary |
| **`X-Forwarded-For`** | Header do client/proxy có thể gửi | **Không**, khi chưa kiểm soát nguồn và chuỗi hop | Chuyển thông tin IP qua proxy |
| **`X-Real-IP`** | Header triển khai riêng, thường chứa một IP | **Không** nếu nhận từ vùng không tin cậy | Thông tin client do proxy trusted cung cấp |
| **`Forwarded`** | Header chuẩn hóa theo RFC 7239 | **Không** nếu không có chính sách tin cậy tương ứng | Truyền `for`, `by`, `proto`, `host` theo cú pháp chuẩn |
| **IP đã được hệ thống xác minh** | Kết quả của thuật toán trust proxy và kết nối thật | Có thể dùng cho mục tiêu được thiết kế, trong giới hạn NAT/proxy | Log, abuse detection, một số rate limit |
| **User/service identity** | Login session, token, mTLS hoặc cơ chế định danh khác | Theo cơ chế authentication/authorization riêng | Phân quyền nghiệp vụ |

**Điểm then chốt:** IP là một **tín hiệu mạng**, không phải danh tính người dùng có độ đảm bảo như authentication. Nhiều người dùng có thể chia sẻ một public IP qua NAT; người dùng di động có thể đổi IP; VPN/proxy có thể che địa chỉ thiết bị gốc một cách hợp pháp.

### 2.3. Điều gì xảy ra khi không có header?

Nếu ứng dụng chỉ thấy socket peer `10.20.0.20` và không có cơ chế cung cấp original client address, nó chỉ biết **proxy đã kết nối đến mình**. Trong một số triển khai, L4 load balancer có thể dùng **PROXY protocol** để truyền peer information bằng một cơ chế **khác HTTP header**; hoặc có cách bảo toàn source IP ở tầng mạng.

Không nên **tự đoán** client IP từ các trường HTTP rời rạc. Nếu trust chain chưa được thiết kế, lựa chọn an toàn là ghi nhận peer thật, đánh dấu client IP **unknown/unverified**, đồng thời sửa kiến trúc để có nguồn dữ liệu đáng tin.

## 3. X-Forwarded-For là gì?

### 3.1. Cú pháp phổ biến

`X-Forwarded-For` là một **de facto HTTP header**, không phải một định nghĩa cú pháp được chuẩn hóa trong cùng cách như `Forwarded` của RFC 7239. Dạng thông dụng là danh sách địa chỉ IP phân tách bằng dấu phẩy:

~~~http
X-Forwarded-For: 198.51.100.24, 203.0.113.10, 10.20.0.10
~~~

Trong một pipeline **được triển khai và xác minh theo quy tắc append**, mỗi proxy thường nối thêm IP của **peer mà nó trực tiếp quan sát** vào cuối danh sách. Vì vậy:

- Bên trái thường là IP client ban đầu mà proxy đầu tiên chấp nhận/ghi nhận.
- Bên phải là các IP proxy trung gian được thêm sau.
- Tuy nhiên, **client có thể tự viết phần đầu header**, và proxy có thể **overwrite, append, chuẩn hóa hoặc không gửi** tùy cấu hình.

**Không áp dụng quy tắc “phần tử đầu tiên luôn là IP thật”**. Câu đúng phải là: IP được chấp nhận phụ thuộc **nguồn kết nối trực tiếp, danh sách trusted proxies và cách từng hop xử lý header**.

### 3.2. Một chuỗi được hình thành đúng

~~~text
Kịch bản: client không dùng proxy riêng và tất cả hop tin cậy hoạt động đúng.

1. Client 198.51.100.24 -> Edge 203.0.113.10
   Edge ghi đè/chuẩn hóa XFF thành:
     X-Forwarded-For: 198.51.100.24

2. Edge -> Load balancer 10.20.0.10
   LB quan sát peer 203.0.113.10 và nối thêm:
     X-Forwarded-For: 198.51.100.24, 203.0.113.10

3. LB -> Reverse proxy 10.20.0.20
   Reverse proxy quan sát peer 10.20.0.10, nối thêm:
     X-Forwarded-For: 198.51.100.24, 203.0.113.10, 10.20.0.10

4. Reverse proxy -> Application
   Socket peer tại application: 10.20.0.20
   XFF nhận được: 198.51.100.24, 203.0.113.10, 10.20.0.10
~~~

Đây là **ví dụ lý tưởng**, giả định edge loại bỏ header không tin cậy và danh sách trusted hops đã được khai báo chính xác. Trong thực tế còn có IPv6, NAT, proxy của khách hàng, service mesh hoặc gateway khác, nên không tự suy từ số dấu phẩy mà ra danh tính chắc chắn.

### 3.3. Client có thể chèn một địa chỉ giả ở bên trái

~~~http
GET /api/orders HTTP/1.1
Host: shop.example.test
X-Forwarded-For: 10.9.9.9
~~~

Nếu edge **chỉ nối** `198.51.100.24` mà không xử lý giá trị đầu vào, một downstream proxy có thể thấy:

~~~text
10.9.9.9, 198.51.100.24, 203.0.113.10, 10.20.0.10
~~~

Ứng dụng đọc **bên trái nhất** sẽ nhầm `10.9.9.9` thành client IP, dù đó là chuỗi được người gửi tự khai báo. Thuật toán dựa trên **trusted chain** có thể xác định `198.51.100.24` là điểm ngoài chuỗi trusted ở bên phải; tốt hơn nữa là để **edge loại bỏ XFF do client gửi** khi không có nhu cầu bảo tồn một upstream đáng tin.

### 3.4. Duplicated headers và giá trị không hợp lệ

HTTP có thể mang nhiều trường cùng tên hoặc giá trị phân tách bằng dấu phẩy; cách proxy/framework gộp chúng phụ thuộc HTTP version và triển khai. Các đầu vào như:

~~~http
X-Forwarded-For: 198.51.100.24
X-Forwarded-For: 10.9.9.9
~~~

hoặc giá trị chứa khoảng trắng, dấu ngoặc IPv6, token bất thường, chuỗi trống, nhiều phần tử, địa chỉ không hợp lệ cần được xử lý **theo parser đã được thử nghiệm và chính sách rõ ràng**. Không tự viết hàm tách bằng dấu phẩy rồi chọn phần tử đầu tiên mà bỏ giới hạn độ dài/số hops. Nếu input không hợp lệ, có thể từ chối request hoặc gắn trạng thái **untrusted** tùy security policy; tuyệt đối không “fallback” về giá trị tùy ý do client tự khai báo.

## 4. Trust boundary: chỉ tin header từ những proxy mình kiểm soát

### 4.1. Nguyên tắc “trust the hop, not the string”

Xác thực một XFF chain không phải kiểm tra “chuỗi trông giống IP hợp lệ”. Câu hỏi đầu tiên phải là: **socket peer nào đang gửi thông tin này?** Nếu peer không thuộc danh sách/trust boundary được chấp nhận, ứng dụng/proxy không nên dùng giá trị XFF do peer gửi làm client identity.

Sau đó, nếu socket peer là proxy tin cậy, mới kiểm tra **quy tắc mà hop đó đảm bảo**: nó có xóa XFF từ nguồn không đáng tin? Có append địa chỉ peer chính xác? Có giới hạn nguồn kết nối và bảo vệ TLS/mTLS? Có dùng `Forwarded` thay cho XFF? Có một cơ chế identity độc lập không?

~~~mermaid
flowchart TD
    A["Request tới backend"] --> B["Lấy socket peer thật"]
    B --> C{"Peer thuộc trusted proxy set?"}
    C -- "Không" --> D["Bỏ qua forwarded IP từ request"]
    C -- "Có" --> E["Kiểm tra header theo hợp đồng proxy"]
    E --> F{"Định dạng và chuỗi hop hợp lệ?"}
    F -- "Không" --> G["Reject hoặc đánh dấu untrusted theo policy"]
    F -- "Có" --> H["Duyệt chuỗi từ phải sang trái qua trusted hops"]
    H --> I["Chọn địa chỉ ngoài trusted chain gần nhất nếu có"]
    I --> J["Log peer + client IP có provenance"]
    D --> J
~~~

### 4.2. Duyệt từ phải qua trái: mô hình có điều kiện

Một cách xác định địa chỉ **gần nhất nằm ngoài chuỗi trusted proxies** là:

1. Bắt đầu từ **IP của socket peer thực** tới backend.
2. Nếu peer không tin cậy: **không dùng XFF để quyết định client IP**.
3. Nếu peer tin cậy: xem các hop trong XFF **từ phải sang trái**.
4. Bỏ qua các hop mà mạng của mình xác minh là **trusted proxies**.
5. Gặp IP **không được tin cậy đầu tiên** thì coi đây là **điểm ngoài trust boundary gần nhất**, với điều kiện proxy đầu vào đã duy trì đúng quy tắc.
6. Nếu toàn bộ chuỗi là trusted hoặc parser không xác định được, cần chính sách **fallback rõ**, không đoán rằng địa chỉ bất kỳ trong header là người dùng cuối.

Trong ví dụ mục 3.3, nếu tin `10.20.0.20`, `10.20.0.10` và `203.0.113.10` **vì chúng thật sự là hạ tầng do mình quản lý**, kết quả có thể là `198.51.100.24` thay vì chuỗi giả `10.9.9.9`.

> Thuật toán này **không tự chứng minh danh tính cá nhân**. Nếu có một HTTP proxy do người dùng điều khiển ở phía ngoài edge, IP gần nhất ngoài trust boundary có thể là IP proxy đó. Địa chỉ trước proxy do người dùng cung cấp vẫn không được tin nếu không có một hợp đồng tin cậy khác.

### 4.3. CIDR tin cậy không được là “toàn Internet”

Một lỗi nguy hiểm là cấu hình trusted proxies bằng `0.0.0.0/0`, `::/0` hoặc tin mọi request chỉ vì server “đặt phía sau load balancer”. Khi đó, **client có thể tự tạo XFF và được ứng dụng chấp nhận** nếu đường vào không bị khóa.

Trusted ranges phải phản ánh **địa chỉ egress của những proxy thực sự được kiểm soát**, và cần cập nhật khi topology thay đổi. Không chỉ dựa vào việc IP thuộc RFC1918: một client VPN, pod hoặc máy nội bộ **không mặc nhiên là proxy đáng tin**.

### 4.4. Network enforcement và application validation phải đi cùng nhau

Hai lớp bảo vệ bổ sung cho nhau:

- **Mạng:** chỉ edge/CDN/LB/proxy được phép kết nối trực tiếp tới backend bằng firewall, security group, ACL, mTLS hoặc mechanism thích hợp; hạn chế truy cập trực tiếp vào origin.
- **Ứng dụng:** vẫn chỉ tin header khi **socket peer hợp lệ**, parser đúng, số hop phù hợp và được xử lý theo hợp đồng.

Chỉ whitelist XFF ở ứng dụng nhưng bỏ mở origin công khai dễ tạo **direct-to-origin bypass**. Chỉ chặn origin bằng firewall nhưng để app tin chuỗi giả từ edge lại tạo rủi ro **spoofed client identity**.

## 5. Quyết định quan trọng tại edge: overwrite, append hay preserve?

### 5.1. Edge nhận trực tiếp từ Internet không tin XFF đầu vào

Với edge đầu tiên nhận kết nối từ Internet, nếu không có upstream proxy tin cậy đã được thỏa thuận, chính sách đơn giản và an toàn thường là:

1. Xóa/ghi đè mọi header biểu thị client IP đến từ phía **untrusted client**.
2. Tạo XFF từ **địa chỉ nguồn kết nối edge thực quan sát**.
3. Ghi các giá trị nguồn không tin cậy vào một vùng log chẩn đoán **được kiểm soát**, nếu thật sự cần và đã xử lý privacy/log injection.
4. Chỉ forward qua những kênh và hostname được phép đến backend.

~~~text
Client gửi:
  Source socket IP  = 198.51.100.24
  X-Forwarded-For   = 10.9.9.9  (untrusted)

Edge tạo lại:
  X-Forwarded-For   = 198.51.100.24
~~~

Nếu doanh nghiệp dùng một CDN phía trước edge và **cần giữ IP client ban đầu**, edge phải có cơ chế **xác minh socket peer thực sự đến từ CDN được duyệt**, đọc trường client IP do CDN cam kết cung cấp, kiểm tra format rồi **tái phát hành** dữ liệu đã xác minh. Không đơn giản tin `CF-Connecting-IP`, `True-Client-IP`, `X-Real-IP` hoặc bất kỳ tên header vendor nào khi nó đến từ một request Internet bất kỳ.

### 5.2. Proxy trung gian có thể append

Sau khi đi qua edge đã chuẩn hóa, một proxy downstream có thể nối thêm **socket peer IP** của chính kết nối đến, miễn nó thực sự ở phía sau đường trusted và biết rõ các proxy trước đó xử lý header thế nào.

Không nên **append mù** một chuỗi client-supplied rồi truyền tới app nếu app có code `xff.split(',')[0]`. Cấu hình ở nhiều lớp phải hợp thành một **hợp đồng thống nhất**, không để mỗi hop đặt ra định nghĩa client IP riêng.

### 5.3. Overwrite có thể làm mất thông tin nếu đặt sai vị trí

Nếu một LB ở giữa pipeline **ghi đè XFF bằng IP của CDN**, ứng dụng sẽ không còn biết IP client ban đầu (trừ khi dùng trường đã xác minh khác). Đây thường là lỗi observability/định danh rate limit, không nhất thiết là lỗi mật mã. Cần tài liệu hóa **hop nào tạo gốc, hop nào append, hop nào có quyền chuẩn hóa lại**.

## 6. Các forwarded headers liên quan ngoài XFF

### 6.1. `X-Forwarded-Proto`

`X-Forwarded-Proto` thường biểu thị protocol/scheme phía client dùng với proxy ở ranh giới, ví dụ `https`:

~~~http
X-Forwarded-Proto: https
~~~

Khi reverse proxy giải mã TLS và nói chuyện với backend bằng HTTP, ứng dụng có thể thấy socket nội bộ không mã hóa nhưng cần biết **external request scheme** để tạo HTTPS redirects/absolute URLs và xử lý secure cookies theo đúng kiến trúc.

**Rủi ro:** tin một `X-Forwarded-Proto: https` do client tự gửi có thể làm app hiểu sai mức an toàn của kết nối hoặc xây redirect/cookie không đúng. Proxy tin cậy phải **thiết lập từ trạng thái kết nối thực tại ranh giới**, không chấp nhận giá trị tùy ý.

### 6.2. `X-Forwarded-Host` và `X-Forwarded-Port`

~~~http
X-Forwarded-Host: shop.example.test
X-Forwarded-Port: 443
~~~

Các trường này có thể giúp backend dựng URL public khi nằm sau ingress. Nhưng chúng có thể ảnh hưởng tới **absolute links, email reset password, OAuth redirect URIs, callback URLs và cache keys**. Nếu ứng dụng tin host do client tự khai, có thể xảy ra **host header poisoning, open redirect hoặc cache confusion** tùy chức năng.

Chỉ chấp nhận **hostname có trong allowlist**, chuẩn hóa tại trusted proxy và kiểm tra đồng nhất với route được thiết kế. Không xây URL chứa token nhạy cảm dựa trên một forwarded host chưa xác thực.

### 6.3. `X-Real-IP`

`X-Real-IP` thường mang một địa chỉ đơn lẻ do proxy thiết lập:

~~~http
X-Real-IP: 198.51.100.24
~~~

Nó không chứa được toàn bộ provenance của chuỗi hop như XFF dạng danh sách. **Tên header không làm dữ liệu đáng tin**; nên xem đây là một trường do trusted proxy **chủ động tạo** sau khi tính toán client IP. Nếu cả `X-Real-IP` và XFF cùng có, cần định nghĩa nguồn chuẩn và chính sách khi chúng khác nhau.

### 6.4. `Forwarded` chuẩn hóa theo RFC 7239

RFC 7239 định nghĩa header chuẩn `Forwarded` với các tham số như `for`, `by`, `proto`, `host`:

~~~http
Forwarded: for=198.51.100.24;proto=https;host=shop.example.test
~~~

Ví dụ nhiều phần tử:

~~~http
Forwarded: for=198.51.100.24;proto=https, for=203.0.113.10;by=10.20.0.10
~~~

**Lưu ý kỹ thuật:** cú pháp RFC 7239 có quy tắc riêng về dấu ngoặc kép, địa chỉ IPv6, cổng, token, `unknown` và obfuscated identifiers. Một số thiết bị không hỗ trợ hoặc diễn giải khác, vì vậy cần **parser đúng chuẩn**, kiểm tra độ dài và trust chain; không trộn `Forwarded` với XFF bằng cách nối chuỗi tùy tiện.

`Forwarded` chuẩn hóa **hình thức trao đổi thông tin**, không tự làm mọi proxy thành đáng tin hoặc chống spoofing. Nếu client được phép gửi `Forwarded` trực tiếp, nó cũng có thể giả mạo giá trị. Cần chọn **nguồn dữ liệu canonical** tại ranh giới và xử lý mâu thuẫn theo policy.

## 7. Nginx: ghi đè XFF tại Internet-facing edge

### 7.1. Mẫu cấu hình minh họa

Khi Nginx đóng vai trò **edge trực tiếp nhận TCP connections từ client không tin cậy**, và không có CDN/trusted proxy phía trước, có thể thiết kế để **ghi đè** XFF bằng `$remote_addr` thay vì dùng `$proxy_add_x_forwarded_for` tại hop đầu tiên.

~~~nginx
# LAB ONLY — minh họa một edge trực tiếp nhận client.
# Đặt trong ngữ cảnh http{} đã có TLS certificate/secret hợp lệ.
server {
    listen 443 ssl;
    server_name shop.example.test;

    ssl_certificate     /etc/tls-lab/shop-chain.pem;
    ssl_certificate_key /etc/tls-lab/shop-key.pem;

    location / {
        # Nếu public hostname cố định, không chuyển Host không kiểm soát.
        proxy_set_header Host shop.example.test;

        # ĐẶC BIỆT: không dùng header XFF mà client Internet tự gửi.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Real-IP       $remote_addr;

        # Scheme của kết nối mà chính edge quan sát.
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  shop.example.test;
        proxy_set_header X-Forwarded-Port  443;

        # Không chuyển tiếp Forwarded do client không tin cậy gửi.
        proxy_set_header Forwarded "";

        proxy_pass http://10.20.0.10:8080;
    }
}
~~~

**Giải thích:**

- `$remote_addr` là địa chỉ peer mà Nginx nhìn thấy, **trừ khi trước đó module realip hoặc cấu hình khác đã thay thế địa chỉ hiệu lực**. Ví dụ này giả định edge không bật realip với nguồn không tin cậy.
- `$proxy_add_x_forwarded_for` thường lấy **XFF hiện có** rồi nối thêm `$remote_addr`; dùng ngay ở Internet-facing edge mà không chuẩn hóa input có thể làm header giả tiếp tục tồn tại.
- `$scheme` là scheme mà Nginx nhận trên hop **này**. Nếu Nginx nằm sau một TLS terminator khác và chỉ nhận HTTP, `$scheme` là `http`, không đại diện cho scheme public. Muốn giữ scheme public phải xây **hợp đồng trusted headers** riêng.
- `proxy_set_header Forwarded ""` là cách minh họa loại bỏ header được forward khi không có giá trị; các header/proxy vendor khác cũng cần inventory và kiểm soát.
- Ví dụ chuyển tiếp tới upstream HTTP để tập trung vào header. Nếu trust boundary yêu cầu **mã hóa nội bộ**, phải bổ sung TLS tới backend và **xác minh certificate** chứ không coi cấu hình này đã đủ an toàn.

**Không copy thẳng cấu hình vào production.** Cần có TLS hardening, Host allowlist hoặc default-server rejection, hạn chế origin network, timeout/body limits, WAF, logging, rate limiting và test theo phiên bản Nginx đang triển khai.

### 7.2. Khi Nginx không phải edge đầu tiên

Giả sử Nginx đứng sau CDN/LB: `$remote_addr` khi đó có thể là IP **CDN/LB**, không phải client. Nếu cứ overwrite bằng `$remote_addr`, backend chỉ thấy địa chỉ proxy và mất thông tin client có giá trị. Một thiết kế khác là **tin một trường client IP được CDN/LB đã xác minh, sau khi peer được chứng minh thuộc đúng provider/trust range**, rồi tái phát hành XFF sạch.

Các nhà cung cấp có thể định nghĩa những header khác nhau, thậm chí có hành vi riêng với IPv6, worker/edge requests hoặc proxy chaining. Trước khi cấu hình cần xác nhận:

1. Nguồn IP của **socket peer** tới Nginx phải thuộc danh sách egress CDN/LB đáng tin, được chặn đường bypass.
2. Header vendor nào chứa địa chỉ client và điều kiện nó được điền như thế nào.
3. CDN có xóa XFF/Forwarded client-supplied ở edge không.
4. Nếu header vendor bị thiếu hoặc sai định dạng, ứng dụng dùng chính sách nào để **không tin dữ liệu giả**.
5. Cách cập nhật provider CIDR, rotation và test khi provider thay đổi egress ranges.

## 8. Nginx ở hop trung gian: append và realip

### 8.1. `$proxy_add_x_forwarded_for` dùng khi nào?

Một Nginx downstream có thể dùng:

~~~nginx
# LAB: Nginx downstream chỉ nhận từ load balancer 10.20.0.10.
# Phải có firewall / network policy giới hạn direct-to-origin.
server {
    listen 8080;
    server_name internal-proxy.example.test;

    location / {
        allow 10.20.0.10;
        deny all;

        # Chỉ append nếu upstream LB đã đảm bảo XFF đầu vào an toàn.
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host shop.example.test;
        proxy_pass http://10.30.0.30:8080;
    }
}
~~~

Trong pipeline ví dụ, XFF từ LB là `198.51.100.24, 203.0.113.10`; Nginx thấy peer `10.20.0.10`, rồi nối thêm `10.20.0.10`. Nhưng nếu LB đã cho phép header XFF giả đi vào, việc append **không biến chuỗi giả thành đúng**.

Đây là minh họa lớp HTTP. `allow/deny` giới hạn theo IP như Nginx quan sát, nhưng **không thay thế firewall và không phải authentication mạnh**; trong mạng có NAT, service mesh hoặc proxy khác, phải xem địa chỉ peer thực tế. Nếu cấu hình realip cùng instance, `$remote_addr` có thể bị thay đổi trước khi áp dụng rule và append: **không suy nguyên xi snippet này cho hệ thống có realip**.

### 8.2. `ngx_http_realip_module`: thay đổi remote address theo nguồn tin cậy

Nginx có các directive thường gặp:

- `set_real_ip_from`: khai báo địa chỉ/CIDR của nguồn **được phép cung cấp** thông tin client IP.
- `real_ip_header`: tên header chứa thông tin địa chỉ thay thế, ví dụ `X-Forwarded-For`.
- `real_ip_recursive on`: khi có chuỗi XFF và nguồn trực tiếp đáng tin, chọn **địa chỉ cuối cùng không thuộc trusted ranges** trong danh sách (theo ngữ nghĩa của module).
- `$realip_remote_addr`: giữ địa chỉ remote ban đầu trước khi realip thay đổi, hữu ích để so sánh socket peer với địa chỉ đã chuẩn hóa khi module được bật.

Ví dụ ở một proxy lab nhận từ LB `10.20.0.10`, với CDN `203.0.113.10` cũng là hop **do chính tổ chức quản lý và đã được xác minh**:

~~~nginx
# LAB ONLY — phạm vi tin cậy dựa trên topology minh họa.
# Tránh đặt 0.0.0.0/0 hoặc ::/0 ở đây.
set_real_ip_from 10.20.0.10;
set_real_ip_from 203.0.113.10;

real_ip_header X-Forwarded-For;
real_ip_recursive on;

# Có thể ghi log đồng thời:
# $remote_addr          = client IP được realip xác định theo cấu hình
# $realip_remote_addr   = địa chỉ peer trước khi thay thế (nếu có)
# $http_x_forwarded_for = header XFF nhận được, vẫn là dữ liệu cần kiểm soát
~~~

**Điều kiện bắt buộc:**

- **Đúng peer**: request phải thực sự tới từ một trusted peer; nếu có đường public bypass thì cấu hình không mang lại ranh giới an toàn như mong muốn.
- **Đúng chuỗi**: edge/CDN đã loại bỏ input không đáng tin; LB append như hợp đồng; trusted ranges không chứa khách hàng hoặc bất kỳ IP tùy ý.
- **Đúng ngữ cảnh**: nếu có thêm hop bên trong nhưng không khai báo, kết quả có thể là IP của một proxy thay vì client.
- **Đúng logging**: sau realip, `$remote_addr` có thể không còn là transport peer; giữ thêm trường peer ban đầu và trạng thái xử lý để điều tra.

Không bật `set_real_ip_from` cho toàn bộ mạng private chỉ vì “proxy chạy trong data center”: một workload khác trong CIDR đó có thể kết nối vào và làm giả header. Phạm vi CIDR nên nhỏ nhất có thể, kết hợp network enforcement.

### 8.3. Cẩn thận khi dùng realip và append trên cùng một hop

Nếu Nginx đã thay `$remote_addr` bằng client IP thông qua realip, `$proxy_add_x_forwarded_for` có thể append **giá trị đã thay thế**, không nhất thiết là IP socket peer của Nginx trước khi rewrite. Hệ quả là XFF downstream có thể có **địa chỉ lặp lại hoặc khác kỳ vọng chuỗi hop**.

Vì vậy cần chọn rõ một trong những kiến trúc:

- Proxy A chỉ chuẩn hóa XFF, proxy B chỉ append IP peer thật rồi chuyển tiếp;
- Một ingress đã resolve client IP, sau đó **phát hành một trường canonical mới** cho downstream, kèm bảo đảm downstream chỉ nhận từ ingress;
- Sử dụng cơ chế provider/controller hỗ trợ để giữ **raw peer + normalized client IP** riêng, thay vì để mọi hop tự viết lại.

**Không kết luận đúng chỉ vì log cuối có vẻ là public IP**. Hãy dùng test có XFF giả, nhiều proxy và bypass để xem địa chỉ nào được dùng thực sự.

## 9. Trust proxy ở tầng ứng dụng

### 9.1. Lỗi phổ biến: đọc trực tiếp phần tử đầu tiên

Pseudocode sau **không an toàn** nếu request có thể đến từ client không tin cậy:

~~~javascript
// Ví dụ PHẢN DIỆN — không triển khai để ra quyết định bảo mật.
const clientIp = request.headers["x-forwarded-for"]?.split(",")[0]
  ?? request.socket.remoteAddress;
~~~

Nó không kiểm tra socket peer, không biết proxy nào append, không phân biệt header giả và không bảo đảm parser chấp nhận đúng IP.

Một app chỉ nên nhận **client IP đã chuẩn hóa từ middleware/framework được cấu hình trusted proxies** hoặc một tầng ingress mà nó xác thực theo mạng/mTLS.

### 9.2. Pseudocode có trust boundary

~~~text
function resolveClientIp(socketPeer, rawXff, trustedProxySet):
    if socketPeer not in trustedProxySet:
        return { ip: socketPeer, source: "socket-peer", headerTrusted: false }

    chain = strictlyParseAndLimit(rawXff)
    if chain invalid:
        return { ip: null, source: "unverified", error: "invalid-chain" }

    for hop from rightmost(chain) to leftmost(chain):
        if hop in trustedProxySet:
            continue
        return { ip: hop, source: "trusted-chain", headerTrusted: true }

    return { ip: null, source: "unverified", error: "no-boundary-client" }
~~~

**Đây là thuật toán học tập**, chưa phải parser HTTP/IP chuẩn sản xuất. Phải có thêm xác thực hợp đồng của từng upstream, xử lý header trùng, IPv6, port, định dạng, giới hạn số hop, canonicalization, proxy protocol và trường hợp thiếu header. Các ứng dụng nên **dùng middleware phổ biến và đã được kiểm thử**, không tự triển khai logic mới chỉ từ ví dụ.

### 9.3. Express / Node.js: `trust proxy`

Express hỗ trợ cấu hình `trust proxy` để xác định cách xử lý proxy headers cho các thuộc tính như `req.ip`, `req.ips`, `req.protocol`, `req.hostname` tùy phiên bản:

~~~javascript
// Ví dụ định hướng trong lab, CIDR phải phản ánh đúng peer thực tế.
app.set("trust proxy", [
  "loopback",
  "10.20.0.10/32",
  "10.20.0.20/32",
  "203.0.113.10/32"
]);

app.get("/health", (req, res) => {
  // Không phản hồi các thông tin IP/headers nhạy cảm ra public API.
  res.status(200).send("ok");
});
~~~

**Giới hạn và điều kiện:** giá trị `trust proxy` cần phù hợp topology thật và định nghĩa của phiên bản Express. Đặc biệt, **đừng bật `app.set('trust proxy', true)` một cách mù quáng** khi client có thể đi qua đường khác nhau hoặc kết nối trực tiếp; ứng dụng có thể tin dữ liệu forward do client chèn. Kiểm tra hành vi từ **từng ingress path** thay vì chỉ thử một đường cân bằng tải.

Các thuộc tính `req.protocol`/`req.hostname` cũng có thể phụ thuộc `X-Forwarded-Proto`/`X-Forwarded-Host`; phải bảo đảm ingress đã **ghi đè và allowlist** các trường đó, không chỉ bảo vệ XFF.

### 9.4. Java/Spring Boot và reverse proxy

Trong hệ sinh thái Java, servlet container hoặc framework có thể có cơ chế xử lý forwarded headers và cấu hình strategy tương ứng. Các lựa chọn cụ thể khác nhau theo **Spring Boot version, embedded Tomcat/Jetty/Undertow, Spring MVC/WebFlux, cloud platform**:

- Servlet/container có thể dùng cơ chế kiểu **RemoteIpValve** hoặc cấu hình tương đương.
- Framework có thể dùng **ForwardedHeaderFilter** hoặc cơ chế forwarded-header handling.
- Reverse proxy phải **xóa/ghi đè headers không đáng tin** trước khi framework diễn giải chúng.
- Ứng dụng cần thống nhất nguồn canonical IP/scheme/host thay vì mỗi filter, interceptor và security component dùng một tiêu chí.

**Quan trọng:** bật xử lý forwarded headers trong Spring **không tự tạo trusted proxy network boundary**. Một request trực tiếp có khả năng gửi header tùy ý vẫn nguy hiểm nếu không được chặn hoặc không được middleware kiểm tra. Cần xác minh behavior bằng test và tài liệu của đúng phiên bản đang sử dụng.

### 9.5. Khi ứng dụng ở sau nhiều ingress paths

Một ứng dụng có thể nhận request từ:

1. Internet → CDN → LB → ingress.
2. VPN → internal LB → ingress.
3. Service mesh → sidecar → ingress.
4. Admin/batch jobs → private API.

Các đường có **số hop khác nhau**, nên cấu hình trust proxy dựa trên **số hop cố định** có thể sai nếu có đường ngắn hơn mà attacker điều khiển. Ưu tiên **trust danh sách địa chỉ/CIDR proxy cụ thể và chặn đường bypass**, sau đó kiểm tra từng đường với sơ đồ thực và log.

## 10. Header forwarding với TLS, Host và URL generation

### 10.1. TLS termination làm thay đổi scheme app quan sát

Kịch bản:

~~~text
Browser --> HTTPS --> Edge/LB --> HTTP --> Application

Browser URL: https://shop.example.test/checkout
Edge thấy scheme: https
Application thấy upstream hop: http
~~~

Nếu ứng dụng cần xây redirect tuyệt đối hoặc đặt cookie `Secure`, nó có thể cần thông tin **external scheme** từ ingress. Nhưng trường đó phải do **edge tin cậy tạo**; nếu lấy `X-Forwarded-Proto` từ bất kỳ request trực tiếp nào, một attacker có thể tác động cách app quyết định redirect/secure context.

Giải pháp phụ thuộc framework: sử dụng **public base URL đã cấu hình**, trusted-proxy middleware, HSTS và kiểm tra rằng app luôn xử lý HTTPS theo yêu cầu; không dùng một header chưa xác thực để quyết định tính an toàn của request.

### 10.2. `Host` và `X-Forwarded-Host` có thể gây lỗi bảo mật

Các header có thể được app dùng để tạo:

- URL trong email khôi phục mật khẩu;
- Redirect của OAuth/OIDC hoặc SSO;
- Link signed download;
- Absolute asset URLs và canonical links;
- Cache keys hoặc multi-tenant routing.

Nếu ingress giữ nguyên `Host` hoặc `X-Forwarded-Host` do attacker kiểm soát và backend dựng URL từ đó, app có thể tạo link trỏ sang hostname do attacker chọn. **Đây là lỗi phân quyền dữ liệu đầu vào, không chỉ lỗi định dạng header**.

**Nguyên tắc:** xác định public hostname từ cấu hình/tập **allowlist**; tại edge chỉ route những host được phục vụ, ghi đè forwarded host, và ở app xác thực hostname trước khi đưa vào bất kỳ workflow nhạy cảm nào. Nếu nhiều tenant, mapping **tenant ↔ hostname** phải dựa trên dữ liệu đáng tin.

### 10.3. Phân biệt `X-Forwarded-Proto` với chứng minh TLS

`X-Forwarded-Proto: https` là **một khẳng định do proxy gửi**, không phải bằng chứng mật mã rằng ứng dụng đã trực tiếp thực hiện TLS. Với một hop nội bộ HTTP, ứng dụng chỉ có thể tin assertion đó nếu:

1. Đường đến app chỉ cho trusted proxy;
2. Proxy thực sự đo scheme của kết nối public;
3. Header client-supplied được loại bỏ;
4. Proxy và đường truyền tới backend được bảo vệ theo threat model;
5. App đã xác minh hop là trusted trước khi tiêu thụ header.

Nếu yêu cầu bảo vệ dữ liệu nội bộ, cần **re-encrypt hoặc mTLS cho upstream**, không coi có forwarded proto là dữ liệu đã được mã hóa trên mọi hop.

## 11. Dùng verified client IP trong WAF, rate limiting và access control

### 11.1. Rate limiting cần đầu vào đúng

Nếu backend rate limit bằng **phần tử đầu tiên của XFF** do client tự gửi, đối phương có thể đưa thông tin IP giả vào trường header và làm sai việc nhóm request theo IP. Ngược lại, nếu backend chỉ dùng socket peer IP của proxy, mọi client đi qua cùng một LB có thể bị gom vào một bucket và bị chặn nhầm.

Chọn khóa giới hạn theo mục đích:

| Mục đích | Nguồn chính sách phù hợp | Giới hạn |
|---|---|---|
| DDoS/abuse tại edge | Socket peer IP và các tín hiệu WAF/bot ở edge | Peer có thể là NAT, VPN hoặc proxy doanh nghiệp |
| Rate limit API không đăng nhập | Verified client IP từ trusted chain, path, loại request | Không có tính duy nhất theo cá nhân |
| Rate limit người dùng xác thực | Account/user ID/API credential đã xác thực, kết hợp verified IP nếu cần | Tránh khóa cả NAT vì một tài khoản |
| Phòng chống lạm dụng tài nguyên | Identity + endpoint + hành vi và rủi ro | Phải tránh false positive và ảnh hưởng availability |
| Forensic và audit | Verified IP kèm socket peer, user identity, request ID | Không được dùng raw XFF để quy kết cá nhân |

**IP không phải danh tính người dùng.** Nhiều người có thể chia sẻ một địa chỉ qua NAT/CGNAT, trong khi một thiết bị di động hoặc IPv6 client có thể thay đổi địa chỉ. IP allowlist chỉ nên là lớp kiểm soát bổ sung; các API quan trọng vẫn cần authentication, authorization và phân đoạn.

### 11.2. WAF phía CDN và WAF phía backend

WAF ở Internet edge thường thấy địa chỉ source socket public. WAF phía sau CDN có thể thấy egress IP của CDN và phải dùng **nguồn thông tin client được xác minh theo hợp đồng CDN**. Nếu hai WAF sử dụng những định nghĩa IP khác nhau, rate limit, geo-policy và log có thể trái ngược nhau.

Hãy chọn một **canonical client IP field** và ghi provenance: từ edge hoặc từ parser trusted chain nào, những hop nào tin cậy và điều kiện fallback khi thiếu header. Không để WAF tin `X-Real-IP`, app tin leftmost XFF, còn hệ thống log tin `Forwarded` vô điều kiện.

### 11.3. IP allowlist cho API quản trị

Một lỗi nghiêm trọng là cho phép truy cập endpoint quản trị khi XFF chứa địa chỉ nội bộ, ví dụ `10.9.9.9`, nhưng không kiểm tra header có đến từ trusted proxy hay không. Nếu code tin chuỗi client-supplied, IP allowlist có thể bị bỏ qua.

Thiết kế nên dùng **private endpoint/VPN, firewall, mTLS hoặc xác thực nguồn**, sau đó mới kết hợp verified IP như một tín hiệu phụ. Phân quyền user/service theo vai trò và hành động vẫn là bước riêng. Trong test, phải thử cả đường hợp lệ và **direct-to-origin path**, không chỉ gửi request từ một browser bình thường.

## 12. Direct-to-origin bypass và sai cấu hình trust

### 12.1. Đường đi vòng qua CDN/WAF

~~~mermaid
flowchart LR
    C["Client ngoài Internet"] --> E["CDN/WAF"]
    E --> LB["Origin Load Balancer"]
    LB --> APP["Application"]
    C -. "Đường bypass nếu origin mở public" .-> LB
~~~

Nếu backend còn được truy cập trực tiếp từ Internet, client có thể đi **bỏ qua CDN, WAF, edge sanitization và chính sách rate limit**. App vẫn có thể nhận XFF giả nếu trust proxy được bật quá rộng.

Biện pháp: chỉ cho origin nhận từ edge đã xác thực, dùng security groups/ACL/firewall/mTLS hoặc origin authentication theo khả năng sản phẩm. App cũng phải xử lý **socket peer không trusted** bằng cách không tin forwarded headers. Khi provider IP ranges thay đổi, cập nhật theo quy trình thay vì mở origin toàn Internet.

### 12.2. Địa chỉ RFC1918 không đồng nghĩa proxy tin cậy

Các dải `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` có thể chứa **máy người dùng VPN, pod, máy phát triển hoặc workload không tin cậy**. Nếu khai báo toàn bộ các dải đó là trusted proxies, một máy nội bộ không đáng tin có thể được đối xử như ingress hợp lệ.

Phạm vi tin cậy nên chỉ gồm **IP/CIDR cụ thể của trusted proxy egress**. Thêm kiểm soát network ingress và mTLS khi phù hợp.

### 12.3. Nhiều đường ingress và hop count

~~~text
Path A: Client -> CDN -> LB -> App
Path B: Client -> Internal LB -> App
Path C: Client -> App (đường bypass ngoài thiết kế)
~~~

Nếu framework chỉ cấu hình “tin đúng N hop” mà các đường đi có số hop khác nhau, app có thể vô tình chọn một phần tử XFF mà client tự điều khiển. Chỉ dùng hop count khi đã **chứng minh mọi đường có cùng cấu trúc**, hoặc dùng trusted proxy IP/CIDR và chặn path rút gọn.

### 12.4. Parser differences và input khó

Các trường hợp cần thử gồm duplicated XFF headers, whitespace, phần tử trống, IPv6, giá trị cực dài, địa chỉ không hợp lệ, số hop bất thường, XFF mâu thuẫn với vendor header và `Forwarded` với `for="..."`, `unknown` hoặc obfuscated identifier. HTTP/1.1, HTTP/2 và HTTP/3 có thể được proxy chuyển đổi với hành vi parser khác nhau.

Dùng parser được kiểm thử, giới hạn độ dài và số hop, không tự cắt chuỗi rồi “làm sạch” thành một IP trông có vẻ hợp lệ. Khi input không nhất quán, cần quy tắc reject hoặc **unverified**, không làm theo dữ liệu attacker gửi.

## 13. PROXY protocol, CDN và Kubernetes ingress

### 13.1. PROXY protocol khác với XFF

**PROXY protocol** cho phép một load balancer/proxy truyền metadata về kết nối đến backend theo định dạng riêng, thường ở đầu luồng TCP hoặc transport được hỗ trợ. Đây **không phải một HTTP header**. PROXY protocol có phiên bản và các trường bổ sung tùy khả năng của LB, proxy và server.

~~~text
Client -> L4 Load balancer -> Backend
                             ^
                             |
                  PROXY protocol metadata
                  trước dữ liệu ứng dụng
~~~

**Không tự tin chỉ vì dùng PROXY protocol.** Một listener chấp nhận PROXY metadata từ nguồn không tin cậy cũng có thể nhận dữ liệu địa chỉ giả. Backend phải giới hạn những socket peers có quyền cung cấp metadata; đồng thời cả hai đầu phải bật chế độ tương thích. Nếu server không chờ PROXY protocol nhưng LB gửi preamble, handshake TLS hoặc HTTP có thể hỏng.

Khi hệ thống dùng cả PROXY protocol và XFF, hãy xác định một **nguồn canonical** và xử lý mismatch theo policy. Không tùy ý chọn “IP nhìn giống IP thật hơn”.

### 13.2. Header riêng của CDN

Một số CDN phát hành header client IP chuyên biệt. Giá trị chỉ được coi là có provenance nếu:

1. Request được nhận từ socket peer là **đúng CDN egress** đã kiểm soát.
2. Origin không có đường bypass hoặc có xác thực nguồn tương đương.
3. CDN có cam kết rõ về cách **tạo, ghi đè và xử lý header đến từ client**.
4. IP và định dạng nhận được được parser xác minh.
5. Egress CIDR, IPv6 support, CDN Workers và các tuyến multi-CDN được kiểm thử thường xuyên.

Không tin một header có tên quen thuộc chỉ vì nó trông giống do provider tạo. Client cũng có thể viết cùng tên khi nó không đi qua CDN.

### 13.3. Kubernetes, ingress controllers và service mesh

~~~mermaid
flowchart LR
    U["Client"] --> LB["Cloud LB"]
    LB --> IG["Ingress controller"]
    IG --> S["Kubernetes Service"]
    S --> P["Application Pod"]
    M["NetworkPolicy / Firewall"] -. "Chặn đường bypass" .-> P
~~~

Những câu hỏi cần trả lời theo từng hạ tầng:

- LB có bảo toàn source IP hay ứng dụng sẽ chỉ thấy địa chỉ LB/node?
- LB truyền original client address bằng XFF, header riêng hay PROXY protocol?
- Ingress có tính năng trusted CIDRs/real-ip và **overwrite** ở ranh giới không?
- NetworkPolicy, security group hoặc service mesh có ngăn kết nối trực tiếp từ workload khác tới backend không?
- Sidecar có **thêm hop**, rewrite `Forwarded` hay tạo request nội bộ?
- App framework có cùng định nghĩa `verified_client_ip` như ingress hay không?

Các cấu hình như `externalTrafficPolicy`, cloud LB annotations, forwarded-header settings và source-IP preservation phụ thuộc cloud, CNI, loại Service và phiên bản ingress. **Không áp dụng một file YAML tham số chung cho mọi nhà cung cấp** mà không xác minh mạng thực.

### 13.4. IPv6, NAT và proxy của người dùng

Địa chỉ trong header có thể là IPv4, IPv6 hoặc xuất hiện dưới dạng biểu diễn khác nhau. RFC 7239 có cú pháp riêng cho IPv6, cổng và quoted strings. XFF không có một tiêu chuẩn cú pháp chặt tương đương.

Khi chuẩn hóa để log/rate limit:

- Dùng IP parser đủ khả năng IPv4/IPv6 và canonicalization.
- Không tự loại mọi địa chỉ có dấu hai chấm, không cắt chuỗi bằng regex đơn giản.
- Xem IPv4-mapped IPv6, NAT64, CGNAT và privacy addresses theo đặc tính nền tảng.
- Đánh giá giới hạn theo IPv6 address/prefix có phù hợp threat model và ảnh hưởng người dùng không.
- Chấp nhận rằng **IP phía ngoài trusted chain có thể là một VPN hoặc HTTP proxy hợp pháp**, không nhất thiết IP thiết bị cuối.

## 14. Audit log: lưu cả transport peer và nguồn suy luận

### 14.1. Một trường `client_ip` là không đủ

Trong điều tra bảo mật cần phân biệt **địa chỉ quan sát từ mạng** và **địa chỉ suy luận từ header**:

| Trường | Ý nghĩa | Nguồn |
|---|---|---|
| `socket_peer_ip` | IP kết nối đến thành phần log | Transport/socket trước thay thế realip nếu có |
| `verified_client_ip` | IP được xác định theo hợp đồng trusted chain | Ingress/verified middleware |
| `client_ip_source` | Mức nguồn tin cậy: `socket`, `trusted-chain`, `unverified` | Chính sách hệ thống |
| `raw_xff` | Giá trị raw XFF nếu cần lưu để điều tra | **Dữ liệu người gửi có thể làm giả** |
| `ingress_id` | Edge/LB/proxy path | Cấu hình mạng đã duyệt |
| `request_id` | Mã tương quan logs nhiều hop | Nên chuẩn hóa tại edge hoặc dùng trace policy |
| `authenticated_identity` | User/service identity được xác thực | IAM, token, mTLS, ứng dụng |
| `policy_action` | Allow/deny/challenge/rate-limit | Nơi thực thi chính sách |

~~~json
{
  "timestamp_utc": "2026-11-28T09:00:00Z",
  "request_id": "req-lab-001",
  "ingress_id": "edge-a",
  "socket_peer_ip": "10.20.0.20",
  "verified_client_ip": "198.51.100.24",
  "client_ip_source": "trusted-chain",
  "trusted_hop_count": 3,
  "external_scheme": "https",
  "external_host": "shop.example.test",
  "request_path": "/api/orders",
  "policy_action": "allow",
  "status_code": 200
}
~~~

Đây là dữ liệu **giả định**, không phải log của người dùng thật. Trong môi trường production cần chuẩn hóa timestamp, request ID, kết quả thực thi và cách ẩn dữ liệu nhạy cảm.

### 14.2. Log injection và quyền riêng tư

Vì XFF là input, không nối raw value trực tiếp vào dòng log thiếu escaping. Hãy:

- Giới hạn độ dài header và số IP; escape control characters, newline và ký tự đặc biệt khi lưu.
- Lưu log có cấu trúc, phân biệt **raw untrusted** và **verified normalized**.
- Không ghi credential, cookie/session token, mật khẩu hoặc private key.
- Không nhận `X-Request-ID` của client là ID có quyền cao nếu chưa kiểm soát; ingress có thể phát hành ID chuẩn và lưu ID client ở trường khác.
- Áp dụng quyền truy cập, retention và chính sách xử lý dữ liệu cá nhân cho IP, thời gian, user identity.

### 14.3. SOC cần gì khi điều tra header spoofing?

1. Xác định thời gian UTC, request ID, user identity nếu có và endpoint bị ảnh hưởng.
2. Đối chiếu **socket peer** ở edge, LB, reverse proxy và app.
3. So sánh raw XFF, normalized XFF và địa chỉ canonical sau từng hop.
4. Kiểm tra direct-to-origin access, trusted CIDRs, network ACL và thay đổi cấu hình gần đây.
5. Xem hệ thống nào đã dùng **raw header** cho WAF, rate limiting, auditing hoặc authorization.
6. Phân loại tác động thực tế và khôi phục chính sách tin cậy trước khi quy kết client IP.

Không dựa một mình vào leftmost XFF để khẳng định cá nhân hoặc máy nào đã thực hiện hành động.

## 15. Thiết kế end-to-end cho một chuỗi forwarding đáng tin

### 15.1. Quyết định rõ “nguồn sự thật” ở từng lớp

Một kiến trúc nhất quán nên xác định:

~~~text
Edge:
  - Peer là client/VPN/proxy bên ngoài; không tin raw incoming XFF.
  - Chuẩn hóa client IP theo nguồn kết nối hợp lệ.
  - Phát hành XFF và forwarded proto/host theo public ingress.
  - Ghi edge request ID và provenance.

Middle proxies:
  - Chỉ nhận từ những hop đã được duyệt.
  - Append hoặc preserve theo một hợp đồng duy nhất.
  - Không tự suy danh tính nếu input không thỏa điều kiện.

Backend:
  - Chỉ nhận trusted immediate peer qua mạng/mTLS.
  - Dùng middleware verified-client-IP; không parse raw XFF trong controller.
  - Dùng public base URL/host allowlist cho redirect và link nhạy cảm.
  - Ghi cả peer IP, verified IP, request ID và authentication identity.
~~~

### 15.2. Bảy bước triển khai

1. **Lập sơ đồ hop:** client, ISP/VPN, CDN, WAF, L4/L7 LB, ingress, proxy, app, service mesh; ghi rõ kết nối HTTP/TLS/PROXY protocol.
2. **Đánh dấu trust boundary:** hop Internet-facing và các điểm có thể tạo, overwrite, append, bỏ header.
3. **Khóa đường backend:** private networking, network policy, ACL/security group, origin authentication hoặc mTLS.
4. **Chọn canonical client identity:** một thuật toán trusted chain, danh sách proxy CIDRs thực, xử lý header trùng/sai, IPv6.
5. **Chuẩn hóa proto/host:** chỉ hostname có trong allowlist và external scheme xác định từ kết nối trusted; tránh tự tạo absolute link từ header tùy ý.
6. **Cập nhật WAF/app/log:** cùng dùng verified IP và provenance, phối hợp với authentication/authorization thực.
7. **Thử hồi quy và giám sát:** test header giả, direct-to-origin, thiếu header, IPv6, nhiều ingress paths, CDN failover và thay đổi provider ranges.

### 15.3. Khả năng phục hồi khi thay đổi topology

Khi thêm CDN mới, chuyển LB, bật service mesh hay thay ingress controller, danh sách trusted proxies và số hops có thể đổi. Phải thực hiện **change control cho forwarding policy** như với firewall và TLS:

- Cấu hình hiện hành và thay đổi được review dưới version control.
- Có người sở hữu danh sách CDN/LB CIDRs; tự động cập nhật có bước xác minh.
- Có canary hoặc test ở môi trường gần production, không chỉ unit test parser.
- Có rollback bảo toàn security boundary, không mở public origin để tránh outage.
- Alert nếu IP suy ra đột nhiên thành IP của proxy cho mọi request, hoặc số lượng IP giả/invalid tăng bất thường.

## 16. Thực hành quan sát header forwarding an toàn

### 16.1. Chuẩn bị môi trường

Để thực hành, giả sử có **một lab được phép** gồm:

| Thành phần | Địa chỉ ví dụ | Nhiệm vụ |
|---|---|---|
| Client test | `198.51.100.24` | Tạo request có kiểm soát |
| Edge test | `192.0.2.10` | Nhận HTTPS, ghi đè XFF |
| Load balancer test | `10.20.0.10` | Append địa chỉ peer của edge |
| Reverse proxy test | `10.20.0.20` | Append theo hợp đồng |
| Application test | `10.30.0.30` | Chỉ ghi nhận/quan sát verified IP qua log nội bộ |
| Hostname public lab | `shop.example.test` | Tên URL và certificate identity |

Các IP/tên trên chỉ là dữ liệu tài liệu; lab cần cấu hình thực nếu muốn lệnh có kết quả. **Không phát hiện bằng cách đoán IP ngoài phạm vi quản trị**.

### 16.2. Một HEAD request bình thường

~~~bash
# Một request HTTPS; chỉ thành công khi lab có route, DNS/TLS và endpoint phù hợp.
curl --head --verbose \
  --connect-timeout 3 --max-time 10 \
  https://shop.example.test/health

# Nếu muốn thử endpoint ở IP cụ thể nhưng vẫn giữ hostname/TLS SNI,
# dùng --resolve thay cho việc sửa URL thành địa chỉ IP.
curl --head --verbose \
  --resolve shop.example.test:443:192.0.2.10 \
  --connect-timeout 3 --max-time 10 \
  https://shop.example.test/health
~~~

Kết quả HTTP `200` hoặc `204` tùy endpoint chỉ chứng minh **đường kiểm tra ứng dụng hoạt động**, chưa chứng minh client IP logging đúng. Cần đọc **edge/app log từ người có quyền** để biết socket peer, XFF sau normalization và verified client IP.

### 16.3. Kiểm thử XFF giả trên endpoint do mình quản lý

~~~bash
# CHỈ lab được phép: gửi đúng một request với header tự khai báo.
# Chỉ quan sát log/server state; KHÔNG dùng như một cách vượt rate limit.
curl --head --verbose \
  --resolve shop.example.test:443:192.0.2.10 \
  --header "X-Forwarded-For: 10.9.9.9" \
  --connect-timeout 3 --max-time 10 \
  https://shop.example.test/health
~~~

**PASS khi:** edge không nhận `10.9.9.9` làm client IP, app không dùng chuỗi giả làm policy key; verified client IP tương ứng với nguồn được edge xác minh hoặc được báo không xác minh theo hợp đồng lab.

**Không coi chỉ một response code là bằng chứng PASS.** Cần đối chiếu log/cấu hình của chính điểm ingress. Một client có thể nằm sau NAT nên source IP do edge quan sát khác IP mà người vận hành nghĩ là “IP thiết bị”.

### 16.4. Kiểm tra X-Forwarded-Proto/Host theo positive và negative cases

~~~bash
# Chỉ dùng trên endpoint lab đã phê duyệt: quan sát xem ingress có
# bỏ qua/ghi đè forwarded proto và host do client tự khai báo không.
curl --head --verbose \
  --resolve shop.example.test:443:192.0.2.10 \
  --header "X-Forwarded-Proto: http" \
  --header "X-Forwarded-Host: unexpected.example.test" \
  --connect-timeout 3 --max-time 10 \
  https://shop.example.test/health
~~~

**Kỳ vọng:** application vẫn hiểu public scheme/hostname theo nguồn trusted, không tạo redirect hoặc absolute link tới `unexpected.example.test`, không thay đổi secure-cookie policy từ input giả. Kiểm tra cả HTTP response và ứng dụng/log có giới hạn; không thử gửi token hoặc làm password reset thực ở môi trường ngoài lab.

### 16.5. Kiểm tra trạng thái Nginx và raw peer

~~~bash
# Thực hiện ở Nginx lab nơi bạn có quyền quản trị.
# Kiểm tra cú pháp cấu hình, không ghi đè hoặc reload.
nginx -t

# Chỉ xem cấu hình hiệu lực nếu được phép; đầu ra có thể chứa
# thông tin nhạy cảm như upstream names, paths, CIDRs.
nginx -T
~~~

Khi cấu hình `real_ip_header`, đối chiếu các log có `$remote_addr`, `$realip_remote_addr` và `$http_x_forwarded_for` khi được phép. Nếu log hiện không có các trường này, hãy lên kế hoạch bổ sung **structured logging theo quy trình thay đổi**; không tự thay đổi cấu hình production trong một phép thử read-only.

### 16.6. Không dùng tcpdump để thay cho phân tích HTTP/TLS

Packet capture trong lab có thể giúp xác minh nguồn **socket peer**, nhưng khi proxy giao tiếp qua TLS, nội dung header có thể **không hiển thị** trong capture ở bên ngoài TLS endpoint. Khi cần xác nhận XFF, ưu tiên log tại proxy đã xử lý header theo chính sách và hệ thống tracing phù hợp, không chủ động thu tràn lan payload/credentials.

## 17. Bài toán suy luận IP qua các trường hợp

### 17.1. Trust list và cách đọc

Giả định:

~~~text
Trusted proxies:
  10.20.0.20   (Reverse proxy tới application)
  10.20.0.10   (Load balancer)
  203.0.113.10 (CDN edge do tổ chức kiểm soát)

Client ngoài:
  198.51.100.24
~~~

Đối với các dòng có trusted peer, thuật toán minh họa đọc XFF từ phải sang trái để lấy **địa chỉ đầu tiên không nằm trong tập trusted**. Với peer không trusted, bỏ qua XFF.

| Trường hợp | Socket peer ứng dụng thấy | XFF nhận | Kết quả hợp lý |
|---|---|---|---|
| A: pipeline bình thường | `10.20.0.20` | `198.51.100.24, 203.0.113.10, 10.20.0.10` | `198.51.100.24` nếu hợp đồng được đảm bảo |
| B: client chèn prefix giả, edge chỉ append | `10.20.0.20` | `10.9.9.9, 198.51.100.24, 203.0.113.10, 10.20.0.10` | `198.51.100.24`; **không** chọn leftmost |
| C: client nối trực tiếp tới app | `198.51.100.24` | `10.9.9.9` | Chỉ tin **socket peer**; bỏ XFF |
| D: XFF không hợp lệ | `10.20.0.20` | `not-an-ip, ???` | Reject hoặc **unverified** theo policy |
| E: mọi phần tử đều thuộc trusted list | `10.20.0.20` | `203.0.113.10, 10.20.0.10` | Không đoán một client IP ngoài boundary |
| F: thiếu khai báo CDN là trusted | `10.20.0.20` | `198.51.100.24, 203.0.113.10, 10.20.0.10` | Kết quả có thể là **IP CDN**, cần sửa trust config |
| G: edge overwrite sạch input | `10.20.0.20` | `198.51.100.24, 203.0.113.10, 10.20.0.10` | `198.51.100.24` theo thiết kế |

**Cảnh báo:** kết quả của bảng không phải một khẳng định rằng mọi thư viện/proxy sẽ xử lý y hệt. Một framework có thể chọn thuật toán khác hoặc cần extra trust settings. Muốn đạt yêu cầu phải **kiểm thử chính implementation đang triển khai** và chứng minh tính đúng của upstream normalization.

### 17.2. Phân biệt “không xác minh được” với một IP không mong muốn

Nếu không biết chắc một hop có phải trusted, một phương án an toàn là:

- Giữ socket peer thực ở log;
- Đặt `verified_client_ip = null` hoặc trạng thái riêng tương đương;
- Không áp dụng allowlist đặc quyền dựa trên header;
- Áp dụng rate limit an toàn ở edge hoặc fallback đã được thiết kế;
- Gửi sự kiện tới telemetry để điều tra sai lệch.

Không được **ép một chuỗi không hợp lệ thành IP hợp lệ** chỉ để dashboard có đủ cột.

## 18. Case study: API bị sai rate limit vì tin leftmost XFF

### 18.1. Bối cảnh giả định

Một API quản lý phiên đăng nhập được triển khai qua một CDN và LB:

~~~text
Client -> CDN/WAF -> LB -> Application
~~~

Ở frontend, WAF tính giới hạn theo source IP mà edge quan sát. Nhưng application dùng middleware tự viết:

~~~javascript
// CODE PHẢN DIỆN: tin giá trị người gửi có thể điều khiển.
const ip = req.headers["x-forwarded-for"]?.split(",")[0];
// ip sau đó được dùng làm rate-limit bucket.
~~~

CDN/lớp trung gian chưa được thiết lập chính sách thống nhất để **xóa header XFF do client gửi từ Internet**. Trong lab giả định, application ghi nhận nhiều client IP không tương ứng edge telemetry, khiến rate limiting ở app không còn phân nhóm đúng và log điều tra mất nhất quán.

### 18.2. Điều tra theo các lớp

| Bằng chứng cần có | Điều muốn xác minh |
|---|---|
| Socket peer IP mà CDN thấy | Nguồn kết nối Internet thực đến edge |
| Header XFF client gửi vào lab | Giá trị nào do vùng không tin cậy tạo |
| XFF sau CDN và sau LB | Hop nào append hoặc overwrite |
| `req.ip`/normalized address ở app | App đang chọn địa chỉ nào, theo policy nào |
| Rate-limit key / WAF action | Quyết định chặn được áp dụng theo trường nào |
| Origin network policy | Có direct-to-origin path hay không |
| Authentication/session logs | IP có bị nhầm thành identity hay không |

**Không kết luận lỗi chỉ vì app log hiển thị IP khác browser.** NAT và VPN có thể làm IP khác hợp lý. Cần kiểm tra **provenance và trust rules** để xác định giá trị nào được tính từ một nguồn đáng tin.

### 18.3. Cách khắc phục

1. Quy định edge **overwrite** XFF từ socket peer hoặc nguồn CDN identity đã xác minh; không tin header Internet.
2. Chỉ cho LB/backend nhận từ trusted edge; hạn chế direct origin.
3. Downstream append đúng theo hợp đồng và cấu hình trusted CIDRs tối thiểu.
4. Ứng dụng bỏ parser `split(',')[0]`, chuyển sang middleware trusted proxy đã kiểm thử.
5. Chọn khóa rate-limit phù hợp: verified IP cho traffic chưa xác thực, identity hoặc API key cho traffic đã xác thực, cộng tín hiệu hành vi.
6. Ghi cả socket peer, normalized client IP, source/provenance, user ID khi có và request ID.
7. Thử positive/negative, sai header, thiếu header, route bypass và trường hợp NAT/IPv6.

### 18.4. Bảng before/after (chỉ là mục tiêu thử)

~~~text
BEFORE (lab giả định):
  Incoming client-supplied XFF: 10.9.9.9
  Application rate-limit key: 10.9.9.9
  Actual observed edge peer: 198.51.100.24
  Result: FAIL - rate-limit key derives from untrusted header

AFTER (mục tiêu cấu hình):
  Edge normalized XFF: 198.51.100.24
  Application verified client IP: 198.51.100.24
  Application rate-limit key: derived from verified source / identity policy
  Direct-to-origin: denied by network enforcement
  Result: PENDING authorized validation
~~~

**Bài học:** việc các thành phần **đều đọc một header tên XFF** không chứng minh chúng có cùng định nghĩa đáng tin. Chỉ khi **trust boundary + edge normalization + downstream enforcement + application policy** nhất quán, client IP mới phù hợp làm tín hiệu chống abuse và giám sát.

## 19. Ma trận kiểm thử forwarding và trust boundary

Một hệ thống phải chứng minh cả **địa chỉ IP được suy ra đúng** lẫn **chính sách sử dụng địa chỉ đó không bị làm sai**. Các phép thử dưới đây chỉ dành cho lab hoặc cửa sổ kiểm thử được phê duyệt.

| Test ID | Mục tiêu | Phương pháp | PASS khi |
|---|---|---|---|
| **BASE-01** | Request bình thường qua pipeline | Quan sát request ID, peer và XFF ở các hop | Verified IP phản ánh nguồn ngoài trusted chain; app hoạt động |
| **XFF-01** | Edge không tin XFF client-supplied | Gửi một request lab có XFF giả | Edge overwrite hoặc loại bỏ dữ liệu giả theo policy |
| **XFF-02** | Proxy trung gian append đúng | So log XFF trước/sau LB | Chỉ thêm địa chỉ peer thực được quan sát |
| **XFF-03** | Không chọn leftmost một cách mù | Request lab có chuỗi nhiều hop và prefix giả | Thuật toán trusted-chain chọn điểm ngoài trust boundary hợp lệ |
| **XFF-04** | Request thiếu XFF được xử lý an toàn | Gửi request khi edge/lab đã hỗ trợ tình huống thiếu header | Ghi socket/unverified, không cấp đặc quyền |
| **XFF-05** | Header sai định dạng được xử lý rõ | Một request lab với dữ liệu malformed đã chuẩn bị | Reject hoặc unverified; không suy ra IP giả |
| **XFF-06** | Duplicate headers không tạo parser confusion | Thử trường cùng tên theo HTTP version lab | Kết quả thống nhất với policy parser, không lẫn giữa WAF/app |
| **TRUST-01** | Chỉ immediate peers được tin | Kết nối trong lab từ peer không thuộc allowlist | Bỏ qua forwarded headers hoặc từ chối theo policy |
| **TRUST-02** | Không tin toàn mạng private | Kiểm thử host lab cùng RFC1918 nhưng không phải trusted proxy | Host đó không thể cung cấp trusted client IP |
| **BYPASS-01** | Không có direct-to-origin bypass | Kiểm tra ACL/network flow trong lab | Origin chỉ nhận từ nguồn được duyệt; đường khác bị chặn |
| **PROTO-01** | Scheme phản ánh external TLS | Gửi `X-Forwarded-Proto` sai trong lab | App giữ scheme trusted; không tạo redirect/cookie sai |
| **HOST-01** | Không có host poisoning | Gửi `X-Forwarded-Host` lạ vào endpoint lab | Host không được duyệt không ảnh hưởng absolute links/redirect |
| **FWD-01** | `Forwarded` và XFF không mâu thuẫn | So nhiều kiểu header được parser hỗ trợ | Canonical source rõ; xung đột bị xử lý an toàn |
| **IPV6-01** | IPv6 được xử lý nhất quán | Lab client IPv6, proxy IPv4/IPv6 | Không mất/thay địa chỉ sai vì cú pháp IPv6 |
| **CDN-01** | Header provider chỉ đáng tin từ CDN | Tạo đường thử qua CDN và trực tiếp theo quyền | Request không qua CDN không thể mạo danh CDN |
| **MULTI-01** | Nhiều ingress paths không tạo short-path exploit | So CDN path, VPN path, private ingress path | Mỗi path có trust policy đúng, không tin hop giả |
| **RATE-01** | Rate-limit key không lấy từ input giả | So log khóa giới hạn từ một request lab | Khóa lấy từ verified IP hoặc auth identity |
| **LOG-01** | Log lưu provenance chính xác | So peer, verified IP, request ID và source | Không nhầm raw XFF với trusted identity |
| **REG-01** | Sau đổi CDN/LB config không có hồi quy | Chạy lại bộ test trước/sau thay đổi | Không xuất hiện false trust hoặc mất header hợp lệ |

### 19.1. Điều kiện PASS / FAIL / INCONCLUSIVE

- **PASS:** có bằng chứng từ cả điểm ingress và app chứng minh địa chỉ canonical được suy ra theo hợp đồng, chính sách truy cập không bị header không tin cậy tác động.
- **FAIL:** có bằng chứng raw header giả ảnh hưởng client IP dùng cho allowlist/rate-limit, hoặc direct-to-origin bypass WAF, hoặc forwarded host lạ ảnh hưởng redirect/token link.
- **INCONCLUSIVE:** không có log đúng hop, test bị lỗi DNS/TLS/route, origin không phản hồi, parser version khác hoặc chưa biết chính sách của CDN. **Một HTTP 200/403 đơn lẻ không đủ** để chứng minh xử lý XFF đúng/sai.

### 19.2. Mẫu test evidence

~~~yaml
test_id: XFF-SPOOF-LAB-01
environment: authorized-isolated-lab
url: https://shop.example.test/health
client_supplied_xff: 10.9.9.9
observed_edge_peer: 198.51.100.24
expected:
  edge_overwrites_untrusted_header: true
  verified_client_ip: 198.51.100.24
  backend_direct_access: denied
  rate_limit_uses_verified_source: true
evidence_required:
  - timestamp-utc
  - edge-normalized-request-log
  - lb-and-proxy-hop-log
  - app-client-ip-source
  - network-allowlist-result
  - rate-limit-policy-key
result: pending-execution
~~~

Mẫu trên **không khẳng định bài test đã được chạy**. Trên production không nên xuất header giả để thử nghiệm khi chưa có authorization, và cần quản lý việc ghi log IP theo chính sách riêng tư.

## 20. Troubleshooting: vì sao client IP trong log không khớp?

| Triệu chứng | Giả thuyết | Cần kiểm tra |
|---|---|---|
| Mọi request đều ghi IP reverse proxy | App chỉ dùng socket peer; LB không gửi header; realip chưa đúng | RIB/connection path, header tại từng hop, app middleware |
| App ghi IP nội bộ do client tự khai | App tin leftmost XFF hoặc trust all | So raw input/verified output, trust configuration |
| CDN nhìn public IP nhưng app ghi CDN IP | Thiếu khai báo trusted CDN hop hoặc edge overwrite sai | CDN egress list, XFF chain, `real_ip_recursive` |
| XFF có IP lặp lại | realip thay `$remote_addr` trước append, nhiều hop append sai | `$remote_addr`, `$realip_remote_addr`, config mỗi Nginx |
| Một vài user bị rate limit tập thể | NAT/CGNAT hoặc app bucket theo LB IP | Rate-limit key, auth identity, provider topology |
| Một số user khác vượt giới hạn | XFF hoặc API key không được xác minh; policy key thay đổi | WAF/app logs, source IP derivation |
| Truy cập URL public đúng, backend tạo link `http://` | External scheme bị mất tại TLS terminator | `X-Forwarded-Proto`, proxy trust, public base URL |
| Email reset password dẫn sang host lạ | X-Forwarded-Host/Host chưa allowlist | Public hostname policy, absolute link generator |
| IP sai chỉ trên IPv6 | IPv6 parsing, PROXY protocol mapping, trusted ranges | IPv6 chain, parser, v4-mapped behavior |
| Đường CDN hợp lệ nhưng VPN lỗi | Khác ingress hop count, trusted CIDR không bao phủ | Trusted paths, socket peers và middleware |
| Sau nâng ingress, mọi log ghi node IP | LB/source-IP preservation thay đổi | Cloud LB settings, Service/ingress topology |
| Đột nhiên xuất hiện hàng nghìn client IP khác thường | Raw XFF được tin, log ingestion lỗi hoặc thay đổi provider | Raw vs normalized log, edge policy, change ticket |
| HTTP health OK nhưng app security middleware sai | Health bypass middleware hoặc chưa đi qua ingress thật | Path test, policy point, trace hop |
| Backend chấp nhận request không qua WAF | Origin mở hoặc trust all private range | Firewall/security group và direct-path verification |
| `Forwarded` và XFF khác nhau | Các proxy tạo hai header với quy tắc khác | Canonical source, provider implementation, parser |

### 20.1. Trình tự chẩn đoán một request

1. **Định danh request:** timestamp UTC, URL/host, source network, request ID, client đã xác thực nếu có.
2. **Vẽ đường transport thực:** client → CDN/WAF → LB → ingress → backend; xác định socket peer ở từng chặng.
3. **Thu header có kiểm soát:** raw XFF/Forwarded/vendor headers, không tin chúng trước khi xác minh.
4. **Xác nhận hợp đồng hop:** thành phần nào overwrite, append, pass-through hoặc xóa từng header.
5. **Kiểm tra trusted CIDRs:** có quá rộng, thiếu provider IP mới hoặc bao gồm host không đáng tin không?
6. **Đối chiếu app:** framework trust-proxy settings, middleware order, IPv6 parser, nguồn rate-limit key, chính sách Host/Proto.
7. **Kiểm tra network bypass:** origin direct path, service mesh/ingress thay đổi, VPN hoặc internal endpoint.
8. **Chạy regression tests:** positive/negative, thiếu header, malformed header, app behavior, log provenance.
9. **Đánh giá tác động:** WAF rules, audit trail, rate limits, authz hoặc redirect nào đã dùng IP/header sai.
10. **Khôi phục và lưu bằng chứng:** rollback hoặc sửa cấu hình theo approval, cập nhật runbook, cảnh báo và config inventory.

### 20.2. Tách vấn đề header với vấn đề TLS và routing

Khi HTTPS request không đến được app, nguyên nhân có thể là **DNS, TLS certificate, SNI, firewall, route, upstream health hoặc connection timeout**. `X-Forwarded-For` chỉ là dữ liệu HTTP được xử lý **sau khi kết nối tới tầng HTTP thích hợp đã được thiết lập**.

Vì vậy, không kết luận “XFF bị chặn” chỉ vì một `curl` timeout. Hãy xác minh path và TLS trước, sau đó đối chiếu header/decision trong log. Các forwarded headers không sửa được route bị blackhole hay một certificate không khớp hostname.

## 21. Bài tập tự kiểm tra

### Bài 1 — XFF đầu vào

Client có socket IP `198.51.100.24` gửi `X-Forwarded-For: 10.9.9.9` trực tiếp tới edge. Edge nên xử lý thế nào khi không có upstream trusted proxy?

**Gợi ý:** bỏ hoặc overwrite giá trị do client gửi; tạo thông tin client IP từ socket peer đã quan sát.

### Bài 2 — Chọn IP qua nhiều hop

App thấy socket peer `10.20.0.20`, XFF `10.9.9.9, 198.51.100.24, 203.0.113.10, 10.20.0.10`; trusted hops là `10.20.0.20`, `10.20.0.10`, `203.0.113.10`. IP nào nên được coi là điểm ngoài trusted chain?

**Đáp án gợi ý:** `198.51.100.24` theo mô hình duyệt từ phải sang trái và hợp đồng upstream đúng. `10.9.9.9` có thể là giá trị client khai giả.

### Bài 3 — Trust all

Một kỹ sư đặt `trust proxy = true` vì “backend chỉ chạy sau load balancer”. Điều gì phải được chứng minh trước khi kết luận cấu hình an toàn?

**Gợi ý:** mọi ingress path bắt buộc qua proxy đã chuẩn hóa header, không có direct-to-origin/short paths, peer source được xác thực; tốt hơn thường dùng danh sách trusted CIDRs cụ thể.

### Bài 4 — NAT

Hàng trăm người dùng chung một public IP từ mạng doanh nghiệp bị chặn khi rate limit theo IP. Hệ thống có thể cải tiến gì?

**Gợi ý:** xét account/API key đã xác thực, behavior, endpoint sensitivity, rate-limit nhiều lớp, phù hợp với NAT; không cố dùng IP làm identity duy nhất.

### Bài 5 — X-Forwarded-Proto

Ứng dụng sau TLS terminator nhận HTTP nội bộ và cần tạo URL HTTPS public. Có nên tin `X-Forwarded-Proto` đến trực tiếp từ mọi client không?

**Đáp án:** không. Chỉ tin thông tin do ingress đáng tin tạo từ kết nối ngoài và đã chuẩn hóa; hoặc dùng public base URL cố định.

### Bài 6 — X-Forwarded-Host

Một email reset password có hostname lạ dù domain dịch vụ không đổi. Những headers và điểm kiểm soát nào cần kiểm tra?

**Gợi ý:** `Host`, `X-Forwarded-Host`, `Forwarded;host=...`, routing/default virtual host, trusted-proxy settings, public hostname allowlist và URL generator.

### Bài 7 — CDN và origin

Ứng dụng tin header client IP do CDN gửi nhưng origin vẫn công khai. Nguy cơ là gì?

**Gợi ý:** direct request có thể bypass CDN normalization/WAF và tự gửi header giống CDN. Khóa origin và xác minh immediate peer.

### Bài 8 — PROXY protocol

PROXY protocol có tự bảo đảm địa chỉ client là chính xác khi listener mở cho Internet không?

**Đáp án:** không. Cần chỉ cho trusted peers gửi metadata và đồng bộ cấu hình giữa LB/backend.

### Bài 9 — Nginx realip

Vì sao bật `real_ip_recursive on` mà thiếu danh sách trusted CDN có thể khiến app nhận IP CDN thay vì client?

**Gợi ý:** thuật toán duyệt XFF từ phải sang trái có thể dừng ở hop không được đánh dấu trusted; cần đối chiếu topology và source validation.

### Bài 10 — Ứng dụng Java

Spring Boot có cơ chế forwarded header handling. Vì sao bật feature này chưa đủ bảo vệ khỏi spoofing?

**Gợi ý:** framework diễn giải header nhưng không tự chứng minh socket peer và edge sanitization an toàn; cần network boundary, trusted proxy policy và integration test.

### Bài 11 — Đọc log

Log chỉ có `client_ip=10.20.0.20`. Có thể khẳng định người dùng thật đến từ `10.20.0.20` không?

**Đáp án:** không; có thể đó là reverse proxy. Cần socket peer ở nhiều hop, verified client IP cùng provenance, và user identity nếu có.

### Bài 12 — Bài thực hành tổng hợp

Thiết kế một kiểm thử chứng minh XFF giả **không làm thay đổi policy rate limit** của API trong lab.

**Gợi ý:** chuẩn bị request hợp lệ và một request có `X-Forwarded-For` giả, giữ nguyên nguồn/đường ingress, đối chiếu edge normalization, app canonical IP, policy key, log và kết quả; không cần tạo lưu lượng lớn hoặc tìm cách vượt giới hạn.

## 22. Checklist triển khai Header Forwarding và XFF

- [ ] Có sơ đồ **toàn bộ proxy hops**, nguồn socket IP, TLS termination, kênh nội bộ và ingress paths.
- [ ] Xác định **edge nào nhận input không tin cậy**, nơi XFF được overwrite/loại bỏ và nơi được append.
- [ ] `X-Forwarded-For` do client tự gửi **không được coi là danh tính đáng tin**.
- [ ] Trusted proxy ranges là **IP/CIDR nhỏ nhất và có owner**, không cấu hình trust all hoặc toàn bộ RFC1918 vô điều kiện.
- [ ] Origin/backend bị hạn chế kết nối trực tiếp bằng **firewall/security group/network policy/mTLS** theo threat model.
- [ ] Mỗi downstream hop dùng **một hợp đồng header nhất quán** và biết cách xử lý duplicated/malformed values.
- [ ] `Forwarded`, `X-Real-IP`, vendor headers và PROXY protocol có **nguồn canonical**, không dùng tùy ý khi mâu thuẫn.
- [ ] Bảo đảm **IPv4/IPv6, NAT/CGNAT, CDN changes, VPN và multiple ingress paths** được kiểm tra.
- [ ] Ứng dụng dùng **trusted proxy middleware** phù hợp framework, không tự lấy `xff.split(',')[0]`.
- [ ] WAF, rate limiting, logging và abuse detection dùng **verified client IP**, kết hợp identity khi phù hợp.
- [ ] IP allowlist không thay thế **authentication, authorization, firewall và phân đoạn**.
- [ ] `X-Forwarded-Proto`, `X-Forwarded-Host`, `Host` và port đã được chuẩn hóa/allowlist tại trusted ingress.
- [ ] HSTS, TLS backend và absolute URL/cookie policy được xác minh theo **TLS termination topology**.
- [ ] Log có **socket peer + verified IP + provenance + request ID**, không ghi credentials hoặc raw header không kiểm soát.
- [ ] Có **negative tests** về XFF giả, host giả, direct origin, malformed header, missing header, CDN/VPN short path.
- [ ] Có positive control chứng minh request hợp lệ vẫn hoạt động, tránh coi timeout là tín hiệu bảo mật PASS.
- [ ] Những thay đổi CDN/LB/ingress/mesh có **change review, regression tests, rollback và cảnh báo sau triển khai**.

**Kết luận:** `X-Forwarded-For` hữu ích để bảo toàn thông tin địa chỉ qua các lớp proxy, nhưng **giá trị header không có độ tin cậy mặc định**. Một hệ thống an toàn cần tin **đúng socket peer**, kiểm soát **ai có quyền viết header**, chuẩn hóa ở **edge**, xác minh **toàn bộ trust chain**, chặn đường bypass và dùng client IP đã xác minh theo đúng mục đích. Đây là nền tảng để rate limit, WAF, audit và chính sách ứng dụng hoạt động nhất quán trong kiến trúc proxy và cân bằng tải.

### Tài liệu tham khảo

- [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239): cú pháp `Forwarded`, tham số `for`, `by`, `proto`, `host` và cảnh báo về độ tin cậy.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ý nghĩa các trường HTTP và cách diễn giải request/response.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): các quy tắc HTTP/1.1 liên quan field parsing/connection handling.
- [NGINX — ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html): `proxy_set_header` và `$proxy_add_x_forwarded_for`.
- [NGINX — ngx_http_realip_module](https://nginx.org/en/docs/http/ngx_http_realip_module.html): `set_real_ip_from`, `real_ip_header`, `real_ip_recursive`.
- [Express — Express behind proxies](https://expressjs.com/en/guide/behind-proxies.html): cấu hình `trust proxy` và yêu cầu sanitization.
- [MDN — X-Forwarded-For](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Forwarded-For): cách dùng header và rủi ro bảo mật khi tin client-supplied input.
- [HAProxy — PROXY protocol specification](https://www.haproxy.org/download/2.8/doc/proxy-protocol.txt): khái niệm truyền metadata kết nối ngoài HTTP header.
- [OWASP — HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): thực hành quản lý các HTTP headers liên quan bảo mật.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): ghi log có cấu trúc và hạn chế dữ liệu không tin cậy.






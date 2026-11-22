# Chặn loopback, link-local và metadata service

## 1. Vì sao phải chặn các địa chỉ này?

Server-side request forgery (SSRF) xảy ra khi API nhận một URL hoặc đích mạng do người gọi kiểm soát rồi server tự kết nối tới đó. Request từ server thường có quyền truy cập mạng rộng hơn browser của người dùng: nó có thể nhìn thấy loopback, mạng private, dịch vụ nội bộ, control plane hoặc endpoint cấp credential của cloud.

Một endpoint tải ảnh, import dữ liệu, preview URL, kiểm tra webhook hoặc lấy nội dung từ địa chỉ do người dùng cung cấp có thể trở thành điểm vào mạng nội bộ. Nếu kẻ tấn công khiến server truy cập:

- **Loopback:** dịch vụ chỉ lắng nghe trên 127.0.0.1 hoặc ::1, chẳng hạn admin console, debug endpoint hay agent nội bộ.
- **Link-local:** địa chỉ chỉ có ý nghĩa trên liên kết mạng cục bộ, bao gồm các endpoint hạ tầng thường dùng để cung cấp metadata.
- **Metadata service:** dịch vụ cung cấp thông tin instance, cấu hình và credential tạm thời cho workload.
- **Mạng private hoặc internal:** database proxy, Kubernetes API, service mesh, cache, dashboard, control plane hoặc service khác.

Hậu quả có thể là đọc credential, lấy token của workload, truy cập dữ liệu nội bộ, gọi thao tác quản trị, dò dịch vụ hoặc dùng server làm điểm pivot vào mạng. Chặn riêng chuỗi localhost hay địa chỉ 169.254.169.254 là chưa đủ: cùng một đích có thể được biểu diễn bằng IPv6, địa chỉ số, hostname, CNAME, redirect hoặc DNS rebinding.

Nguyên tắc là **kiểm tra địa chỉ IP thực tế mà kết nối sẽ sử dụng**, sau khi parse URL và resolve DNS, rồi bảo đảm HTTP client kết nối đúng địa chỉ đã kiểm tra. Mỗi redirect và mỗi kết nối mới phải đi qua cùng chính sách. Network egress control tiếp tục là lớp bảo vệ độc lập ở bên ngoài ứng dụng.

## 2. Xác định bề mặt SSRF trong API

SSRF không chỉ xuất hiện ở endpoint có tên fetchUrl. Hãy tìm mọi luồng khiến backend tạo kết nối outbound dựa trên input hoặc dữ liệu có thể bị người dùng tác động:

| Chức năng | Input có thể bị kiểm soát | Tài nguyên có nguy cơ |
|---|---|---|
| Import từ URL | URL nguồn, redirect | Website nội bộ, metadata, file service |
| Preview link / unfurl | URL trong bài viết hoặc chat | Loopback, admin UI, dịch vụ nội bộ |
| Tải avatar/ảnh | URL ảnh | Metadata, private storage, internal API |
| Webhook | URL callback của tenant | Internal service, cloud metadata, control plane |
| Kiểm tra URL | Host, port, path | Port scan, service discovery |
| Chuyển đổi tài liệu | URL hoặc reference từ file | Storage nội bộ, endpoint xử lý |
| Proxy/fetch API | URL đích và header | Bất kỳ mạng nào server truy cập được |
| OAuth/JWKS discovery | Issuer, metadata URL nếu cấu hình động | Endpoint nội bộ hoặc nguồn khóa không tin cậy |
| Media processing | Playlist, manifest, subtitle, external resource | SSRF gián tiếp qua parser media |

Đặc biệt kiểm tra các luồng gián tiếp. Một URL được lưu vào database hôm nay có thể được worker tải xuống vào ngày mai. Việc người dùng không trực tiếp gọi HTTP client không làm mất rủi ro SSRF.

Nếu nghiệp vụ không cần nhận URL tùy ý, hãy nhận một ID tài nguyên, file upload hoặc tên nguồn đã đăng ký trước. Nếu phải nhận URL, áp dụng allowlist theo use case và giới hạn đích đến ngay trong thành phần thực hiện kết nối.

## 3. Phân biệt các nhóm địa chỉ cần chặn

Chính sách cho tính năng tải URL công khai thường chỉ cho phép địa chỉ unicast toàn cầu có thể định tuyến công khai, trên scheme và port được phê duyệt. Các nhóm sau cần bị từ chối, trừ khi có use case nội bộ được thiết kế riêng:

| Nhóm | IPv4 ví dụ | IPv6 ví dụ | Nguy cơ |
|---|---|---|---|
| Unspecified / this network | 0.0.0.0/8 | ::/128 | Địa chỉ không xác định hoặc mang ngữ nghĩa đặc biệt |
| Loopback | 127.0.0.0/8 | ::1/128 | Truy cập dịch vụ trên chính host/container |
| Private / unique-local | 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 | fc00::/7 | Truy cập mạng nội bộ |
| Link-local | 169.254.0.0/16 | fe80::/10 | Metadata, discovery và dịch vụ trên link |
| Shared address space | 100.64.0.0/10 | Không có dải tương đương trực tiếp | Hạ tầng CGNAT hoặc mạng dùng chung |
| Multicast | 224.0.0.0/4 | ff00::/8 | Địa chỉ nhóm, không phải đích fetch thông thường |
| Reserved / special-use | Một số dải trong 192.0.0.0/24, 240.0.0.0/4 và các dải đặc biệt khác | Các dải special-purpose theo IANA | Ngữ nghĩa phụ thuộc giao thức/hạ tầng |
| Documentation / benchmark | 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24, 198.18.0.0/15 | 2001:db8::/32 | Không phải đích Internet production thông thường |

Bảng trên là ví dụ để hiểu nhóm địa chỉ, không phải danh sách deny hoàn chỉnh. IANA duy trì các IPv4/IPv6 Special-Purpose Address Registries; phạm vi và cờ Globally Reachable có thể khác theo từng prefix và cập nhật theo thời gian. Hãy dùng thư viện IP được duy trì cùng dữ liệu phân loại phù hợp, hoặc sinh danh sách policy từ registry đã được kiểm soát. Không tự duy trì vài regex hoặc một danh sách ngắn rồi coi đó là đầy đủ.

Với URL fetch công khai, cách tiếp cận bảo thủ là chỉ cho phép đích được xác định là global unicast theo chính sách hiện hành, đồng thời chặn các dải nội bộ riêng của tổ chức và nhà cung cấp cloud. Một địa chỉ không nằm trong RFC1918 vẫn chưa chắc là đích Internet hợp lệ.

## 4. Loopback: bảo vệ chính host và container

Loopback là dải địa chỉ trỏ về chính network namespace của tiến trình:

- IPv4: toàn bộ 127.0.0.0/8; 127.0.0.1 chỉ là một địa chỉ phổ biến.
- IPv6: ::1/128.

Không chỉ chặn chuỗi localhost. Các hostname sau có thể phân giải về loopback hoặc được resolver xử lý đặc biệt:

- localhost và các subdomain theo policy của hệ thống.
- localhost. có dấu chấm cuối.
- Tên host nội bộ trong file hosts hoặc DNS riêng.
- Tên miền công khai có bản ghi A/AAAA trỏ về loopback.

Địa chỉ loopback có thể được truy cập qua nhiều biểu diễn IPv4 không chuẩn như số nguyên, dạng rút gọn, octal hoặc hexadecimal ở một số parser cũ. Ví dụ một số biểu diễn số có thể được thư viện legacy diễn giải thành 127.0.0.1. Không tự parse IP bằng regex hoặc phép chuyển số thủ công; dùng parser nghiêm ngặt chỉ chấp nhận cú pháp IP chuẩn mà hệ thống hỗ trợ.

### 4.1 Vì sao loopback nguy hiểm trong container?

127.0.0.1 bên trong container thường trỏ tới container đó, không nhất thiết là host vật lý. Tuy nhiên, container có thể chạy:

- Admin/debug endpoint.
- Metrics hoặc profiling server.
- Sidecar agent.
- Proxy nội bộ.
- Local database hoặc cache.
- Control socket được expose qua TCP.

localhost của host, sidecar và container có thể khác nhau theo network namespace. Vì vậy, không được cho rằng loopback chỉ là máy của ứng dụng nên vô hại. Hãy chặn loopback ở tầng URL fetch và giới hạn listener nội bộ chỉ bind vào interface cần thiết.

### 4.2 Tên localhost và resolver

Không chỉ so sánh hostname bằng equals localhost. Hãy:

1. Parse hostname từ URI.
2. Chuẩn hóa IDNA, chữ hoa/thường và trailing dot theo policy.
3. Từ chối tên localhost và các alias cục bộ theo policy.
4. Resolve A/AAAA và kiểm tra địa chỉ trả về.
5. Áp dụng egress firewall để chặn loopback ở network namespace thực thi.

Chặn hostname chỉ là lớp bổ sung. Một domain bất kỳ có thể resolve về 127.0.0.1, vì vậy quyết định cuối cùng phải dựa trên địa chỉ được resolve.

## 5. Link-local và các endpoint hạ tầng

Link-local là địa chỉ có phạm vi trên một liên kết mạng, không được định tuyến như địa chỉ Internet thông thường. Hai dải quan trọng:

- IPv4 169.254.0.0/16.
- IPv6 fe80::/10.

Một số dịch vụ hạ tầng sử dụng link-local để workload truy cập metadata, credential hoặc dịch vụ nền tảng. Ví dụ thường gặp là 169.254.169.254 cho instance metadata trên nhiều cloud và 169.254.170.2 trong một số luồng credential/task metadata của AWS container. Không nên hardcode chỉ hai địa chỉ này; endpoint có thể khác theo cloud, region, runtime, container platform hoặc cấu hình.

Link-local IPv6 có thể đi kèm zone identifier, ví dụ dạng %eth0 hoặc URI-encoded %25eth0. Zone ID chỉ định interface và có thể làm thay đổi nơi gói tin được gửi. Với tính năng fetch URL công khai, từ chối IPv6 zone identifier và toàn bộ địa chỉ link-local.

Một số địa chỉ link-local không phải metadata service nhưng vẫn có thể truy cập agent, service discovery hoặc thiết bị trên cùng mạng. Chặn cả prefix giúp tránh phải đoán dịch vụ nào đang lắng nghe.

## 6. Cloud metadata service và credential endpoint

Metadata service cung cấp thông tin cho máy ảo hoặc workload đang chạy trên cloud. Tùy nền tảng, nó có thể trả về:

- Instance ID, hostname, zone, network interface và thông tin triển khai.
- User data hoặc startup configuration.
- Identity của workload và access token tạm thời.
- Credential để gọi object storage, queue, database hoặc control plane.
- Thông tin về role/service account và endpoint quản lý.

Nếu SSRF đọc được credential, kẻ tấn công có thể chuyển từ một lỗi fetch URL thành chiếm quyền cloud. Phạm vi tác động phụ thuộc IAM role, thời hạn credential, quyền network và những dịch vụ credential có thể truy cập.

### 6.1 Các endpoint thường gặp

| Nền tảng / loại dịch vụ | Ví dụ endpoint | Ghi chú |
|---|---|---|
| Cloud instance metadata | http://169.254.169.254/ | Địa chỉ phổ biến trên AWS EC2, Azure VM và Google Compute Engine; API path/header khác nhau |
| AWS container credential endpoint | 169.254.170.2 trong một số môi trường ECS | Có thể cấp credential theo task role |
| Google metadata hostname | metadata.google.internal | Hostname có thể được resolver nội bộ ánh xạ tới metadata service |
| Metadata/identity endpoint khác | Địa chỉ hoặc hostname riêng của nền tảng | Phải lấy danh sách từ tài liệu cloud/runtime đang dùng |

Danh sách này chỉ giúp nhận diện. Không được dựa vào hostname hoặc IP ví dụ để xây một denylist cố định rồi bỏ qua phân loại IP, DNS và egress. Các nền tảng có thể bổ sung endpoint IPv6 hoặc cơ chế credential mới.

### 6.2 Không dựa vào header bảo vệ metadata

Một số metadata service có cơ chế yêu cầu header hoặc token, ví dụ AWS IMDSv2 dùng token phiên, Google metadata server yêu cầu header nhận diện và Azure IMDS yêu cầu header Metadata: true. Các cơ chế này giảm khả năng truy cập vô tình và là lớp hardening quan trọng.

Tuy nhiên, không được coi chúng là biện pháp chống SSRF duy nhất:

- Một endpoint có thể còn bật chế độ tương thích cũ.
- SSRF có thể cho phép attacker kiểm soát header hoặc thực hiện nhiều request.
- Một số credential endpoint khác không có cùng yêu cầu.
- SSRF có thể dùng metadata để dò thông tin dù không lấy được credential.

Ứng dụng fetch URL phải chặn địa chỉ metadata và vùng link-local trước khi kết nối. Chủ workload đồng thời phải cấu hình metadata service theo khuyến nghị của nền tảng, tắt chế độ cũ nếu có thể và cấp IAM quyền tối thiểu.

### 6.3 Hardening metadata service

- Bắt buộc cơ chế phiên/token của metadata service khi nền tảng hỗ trợ.
- Giới hạn hop/network path tới metadata endpoint theo khả năng cloud.
- Không cấp role có quyền quản trị rộng cho instance hoặc container.
- Tách workload xử lý URL không tin cậy khỏi workload mang credential nhạy cảm.
- Chặn egress tới metadata từ worker không có nhu cầu hợp lệ.
- Không ghi metadata response hoặc credential vào log, trace, cache hay queue.
- Theo dõi request bất thường tới endpoint metadata và các lần sử dụng credential ngoài hành vi dự kiến.

Nếu workload cần metadata để hoạt động, không thể chặn tùy tiện ở mức toàn máy. Hãy dùng network policy/identity policy để chỉ tiến trình hoặc workload được phép mới truy cập; SSRF fetcher nên chạy trong môi trường không có quyền đó.

## 7. IPv4, IPv6 và các biểu diễn dễ bỏ sót

### 7.1 IPv4 dạng không chuẩn

Một số thư viện hoặc stack cũ chấp nhận địa chỉ IPv4 dưới dạng:

- Số nguyên 32-bit.
- Dạng rút gọn thiếu octet.
- Octal hoặc hexadecimal.
- Dạng có leading zero với cách diễn giải khác nhau.

Các dạng này có thể đại diện cho loopback hoặc private IP nhưng không giống chuỗi dotted-decimal thông thường. Parser URL và resolver có thể không thống nhất cách diễn giải.

Đối với IP literal, chỉ chấp nhận định dạng IPv4 dotted-decimal chuẩn và IPv6 chuẩn theo parser được duy trì. Nếu input trông như một IP nhưng không parse nghiêm ngặt được, từ chối thay vì coi nó là hostname rồi gửi DNS query.

### 7.2 IPv6 và IPv4-mapped IPv6

IPv6 cho phép rút gọn nhiều cách viết. Cùng một địa chỉ có thể có chữ hoa/thường, nhóm zero bị lược bỏ hoặc có dạng IPv4-mapped như ::ffff:127.0.0.1.

Nếu chỉ kiểm tra IPv4, attacker có thể dùng IPv4-mapped IPv6 để biểu diễn địa chỉ loopback/private. Khi gặp IPv4-mapped address, trích xuất IPv4 nhúng và áp dụng cùng policy IPv4. Không chỉ kiểm tra prefix textual.

### 7.3 IPv6 zone identifier

Zone identifier gắn địa chỉ link-local với interface cụ thể. Một URL có zone ID có thể không được thư viện URI, proxy và socket xử lý giống nhau. Với public URL fetch, từ chối mọi zone ID. Không xóa zone ID rồi tiếp tục kết nối vì thao tác đó có thể làm thay đổi đích mạng dự định.

### 7.4 NAT64 và cơ chế chuyển tiếp

Trong một số mạng IPv6-only, NAT64/DNS64 có thể ánh xạ IPv4 vào prefix IPv6, thường dùng một prefix well-known hoặc prefix riêng của tổ chức. Một địa chỉ IPv6 có vẻ không thuộc RFC1918 có thể được dịch tới IPv4 private ở phía sau.

Nếu môi trường sử dụng NAT64, cần biết các prefix được cấu hình và đánh giá địa chỉ IPv4 nhúng trước khi cho phép kết nối. Cũng cân nhắc chặn các cơ chế chuyển tiếp như 6to4/Teredo nếu ứng dụng không cần, vì chúng có thể che địa chỉ đích hoặc tạo đường định tuyến khác với policy mong đợi.

## 8. Không dùng chuỗi để phân loại địa chỉ IP

Các kiểm tra như:

~~~java
if (host.startsWith("127.") || host.equals("localhost")) {
    reject();
}
~~~

không đủ an toàn. Chúng bỏ sót IPv6, dạng IPv4 khác, hostname resolve về private IP và các dải special-use khác.

Tương tự, không chỉ dựa vào các hàm tiện ích có phạm vi hẹp như isLoopbackAddress() hoặc isSiteLocalAddress() rồi kết luận địa chỉ còn lại là public. Các API này hữu ích cho một số phân loại nhưng không nhất thiết bao phủ toàn bộ special-purpose prefix, CGNAT, multicast, reserved, NAT64 hoặc dải riêng của tổ chức.

Hãy dùng thư viện IP address được duy trì để:

1. Parse địa chỉ thành kiểu IPv4/IPv6.
2. Chuẩn hóa biểu diễn nhị phân.
3. Phân loại prefix theo IANA Special-Purpose Address Registries và policy mạng của tổ chức.
4. Xử lý IPv4-mapped IPv6 và các prefix chuyển đổi được môi trường sử dụng.
5. So sánh subnet bằng CIDR, không dùng string prefix.

Danh sách prefix cần có phiên bản, nguồn cập nhật và test. Khi IANA hoặc nhà cung cấp thay đổi phân loại, quy trình cập nhật policy phải có review và rollout.

## 9. DNS resolution: kiểm tra mọi địa chỉ được trả về

Hostname không phải địa chỉ đích cuối cùng. Trước khi kết nối, resolver có thể trả một hoặc nhiều bản ghi:

- A: địa chỉ IPv4.
- AAAA: địa chỉ IPv6.
- CNAME: alias trỏ tới tên khác, có thể có nhiều bước.

Một hostname có thể trả nhiều IP, trong đó một IP public và một IP private. Nếu HTTP client tự chọn một địa chỉ khác với địa chỉ ứng dụng đã kiểm tra, policy có thể bị bypass.

Quy trình DNS an toàn:

1. Canonicalize hostname theo IDNA và policy domain.
2. Từ chối hostname nội bộ hoặc special-use không được phép như localhost, .local, .internal theo môi trường.
3. Resolve toàn bộ CNAME chain và các bản ghi A/AAAA có liên quan bằng resolver được kiểm soát.
4. Từ chối nếu resolution lỗi, không có địa chỉ, vượt giới hạn chain hoặc có câu trả lời bất thường.
5. Phân loại mọi địa chỉ trả về; với public fetch, từ chối hostname nếu có bất kỳ địa chỉ nào thuộc vùng bị cấm.
6. Chỉ kết nối tới một địa chỉ đã kiểm tra và ràng buộc socket tới địa chỉ đó.
7. Giữ nguyên hostname hợp lệ cho TLS SNI và certificate hostname verification.

Không chỉ kiểm tra một bản ghi A đầu tiên. Không bỏ qua AAAA vì môi trường hoặc HTTP client có thể ưu tiên IPv6. Không coi CNAME tới hostname khác là an toàn chỉ vì tên ban đầu nằm trong allowlist.

### 9.1 Vì sao nên từ chối hostname có câu trả lời hỗn hợp?

Ví dụ:

~~~text
fetch.example.test
  A     203.0.113.20
  AAAA  ::1
~~~

Nếu ứng dụng kiểm tra IPv4 rồi HTTP client chọn IPv6, request có thể đi tới loopback. Với URL fetch chỉ dành cho Internet công khai, cách đơn giản và an toàn là từ chối toàn bộ hostname nếu bất kỳ A/AAAA nào không đạt policy. Nếu sản phẩm cần hỗ trợ nhiều địa chỉ, chỉ chọn từ tập đã xác minh và bảo đảm client không thể tự chọn địa chỉ ngoài tập đó.

Ví dụ trên dùng dải documentation để minh họa một địa chỉ không được phép; không phải IP production.

## 10. DNS rebinding và TOCTOU

DNS rebinding xảy ra khi cùng một hostname trả về địa chỉ khác nhau theo thời gian. Kẻ tấn công có thể làm bước kiểm tra nhận IP public, sau đó làm bước kết nối nhận IP private hoặc loopback.

Ví dụ:

~~~text
Lần resolve khi validate: attacker.example -> 203.0.113.10
Lần resolve khi HTTP client kết nối: attacker.example -> 127.0.0.1
~~~

Nếu ứng dụng chỉ resolve để kiểm tra rồi truyền hostname gốc cho HTTP client, client có thể resolve lại và kết nối tới địa chỉ mới. Đây là lỗi time-of-check to time-of-use (TOCTOU).

### 10.1 Ràng buộc kết nối với IP đã kiểm tra

Sau khi resolve và phân loại địa chỉ:

- Chọn một IP từ tập đã được xác minh.
- Mở socket trực tiếp tới IP đó hoặc dùng resolver/transport có khả năng pin địa chỉ.
- Với HTTPS, vẫn gửi SNI theo hostname hợp lệ và xác minh certificate cho hostname đó.
- Không tắt TLS hostname verification chỉ để kết nối bằng IP.
- Bảo đảm HTTP Host hoặc :authority là hostname đã xác minh, không phải giá trị do client tự đặt.
- Không để thư viện resolve lại hostname trong lúc mở socket.

Đây là điểm triển khai khó và phụ thuộc HTTP client. Nếu client không hỗ trợ pinning đúng cách, dùng một egress proxy có khả năng resolve, kiểm tra và kết nối tới cùng IP trong một luồng được kiểm soát.

### 10.2 DNS cache và connection pool

DNS cache không tự giải quyết rebinding. Nếu cache giữ IP cũ, policy vẫn phải kiểm tra IP thực tế được dùng khi mở kết nối. Nếu pool tái sử dụng connection, key pool phải gắn đúng authority, TLS identity và địa chỉ peer; không chia sẻ connection giữa host không tương thích.

Khi tạo connection mới sau khi DNS TTL hết hoặc policy thay đổi, resolve và kiểm tra lại. Không dùng một lần kiểm tra từ lúc đăng ký URL để cho phép mọi lần giao hàng trong tương lai.

## 11. Redirect: mỗi hop là một URL mới

Một URL public có thể trả redirect tới:

- http://127.0.0.1/...
- http://169.254.169.254/...
- http://[::1]/...
- Hostname resolve về private IP.
- Scheme hoặc port không được phép.

Nếu HTTP client tự động theo redirect, bước kiểm tra URL ban đầu không bảo vệ đích cuối.

Chính sách khuyến nghị:

1. Tắt automatic redirect cho tính năng fetch URL không tin cậy.
2. Nếu cần hỗ trợ redirect, đọc Location và parse thành URL mới.
3. Kiểm tra scheme, userinfo, hostname, port và path theo policy.
4. Resolve lại toàn bộ DNS chain và kiểm tra mọi A/AAAA.
5. Pin kết nối tới IP đã kiểm tra cho hop mới.
6. Giới hạn số redirect và phát hiện loop.
7. Không chuyển tiếp Authorization, Cookie, Proxy-Authorization hoặc header nội bộ sang host khác.
8. Không cho redirect hạ từ HTTPS xuống HTTP nếu use case yêu cầu TLS.

Không dùng một cờ followRedirects=true mà không có hook kiểm tra từng hop. Redirect tương đối cũng phải được resolve dựa trên URL hiện tại rồi kiểm tra như URL mới.

## 12. Scheme, port và cú pháp URL

Nếu tính năng chỉ cần tải nội dung web, allowlist scheme thường chỉ gồm https; có thể cho phép http nếu có yêu cầu rõ và chấp nhận rủi ro tương ứng. Từ chối scheme không cần thiết như:

- file: để đọc file hệ thống.
- gopher: hoặc các scheme có khả năng tạo request tùy ý.
- ftp: nếu không có use case và parser an toàn.
- data: nếu có thể gây xử lý payload lớn hoặc bypass luồng fetch.
- Scheme tùy chỉnh do thư viện/plugin đăng ký.

Parse URL bằng URI parser chuẩn. Từ chối userinfo như https://trusted.example@127.0.0.1/, vì phần trước @ là thông tin user chứ không phải hostname. Không tự parse bằng regex hoặc split("://").

Port nên được allowlist. Với public web fetch, thường chỉ cần 443 và có thể 80 nếu thật sự hỗ trợ HTTP. Không cho phép mọi port vì điều đó biến endpoint fetch thành công cụ dò cổng dịch vụ nội bộ hoặc public.

Từ chối URL có hostname rỗng, port bất thường, authority mơ hồ, ký tự control hoặc cú pháp không được parser hỗ trợ. Fragment không được gửi trong HTTP request nhưng nên được loại bỏ khỏi logic cache/signature theo đúng semantics; không để parser khác diễn giải fragment thành một phần đích.

## 13. Proxy và egress gateway

Nhiều HTTP client dùng biến môi trường hoặc cấu hình hệ thống như HTTP_PROXY, HTTPS_PROXY và NO_PROXY. Khi dùng proxy:

- Ứng dụng có thể resolve DNS, còn proxy lại resolve hostname lần nữa.
- Proxy có thể tự theo redirect.
- Proxy có thể cho phép CONNECT tới port bất kỳ.
- NO_PROXY có thể khiến một số hostname bỏ qua lớp kiểm soát.
- Proxy có thể thêm hoặc thay header.

Nếu SSRF policy chỉ nằm trong ứng dụng nhưng kết nối thực tế do proxy thực hiện, phải bảo đảm proxy thực thi cùng chính sách. Một mô hình tốt là dùng egress proxy chuyên dụng:

- Chỉ cho phép workload đã xác thực gọi proxy.
- Allowlist scheme, port và domain theo use case.
- Resolve và phân loại A/AAAA tại proxy.
- Pin kết nối tới địa chỉ đã kiểm tra.
- Chặn loopback, link-local, private, metadata và dải nội bộ.
- Kiểm tra từng redirect.
- Ghi log destination đã chuẩn hóa, peer IP và quyết định allow/deny.
- Có giới hạn request, byte, timeout và concurrency.

Không để người dùng điều khiển địa chỉ proxy hoặc các header làm proxy đổi đích. Không cho phép proxy CONNECT tới metadata hoặc cổng quản trị.

## 14. Network egress control: lớp bảo vệ độc lập

Application validation có thể có bug hoặc bị bypass bởi thư viện. Network policy giúp giới hạn đích mà process thực sự có thể kết nối.

Các biện pháp:

- Deny outbound tới loopback, link-local, metadata và mạng nội bộ không cần thiết.
- Dùng firewall/security group/network policy ở host, container, subnet hoặc workload identity.
- Chỉ cho SSRF fetcher ra Internet qua egress proxy đã kiểm soát.
- Tách network namespace hoặc workload cho chức năng fetch URL không tin cậy.
- Chặn truy cập trực tiếp tới database, control plane, Kubernetes API và service quản trị từ worker không cần chúng.
- Quản lý DNS egress; không cho workload tự dùng resolver ngoài policy nếu cần kiểm soát.
- Kiểm thử IPv4 và IPv6; không chỉ cấu hình firewall cho một họ địa chỉ.

Nếu hệ thống cần gọi một service nội bộ hợp lệ, tạo allowlist cụ thể theo service identity, hostname, port và workload. Không mở toàn bộ RFC1918 chỉ vì một integration cần truy cập một endpoint nội bộ.

## 15. Tách workload fetch URL khỏi workload có credential

Một kiến trúc giảm tác động của SSRF là tách thành phần thực hiện fetch:

~~~text
Public API
   |
   | URL + job ID đã validate schema
   v
Queue bền vững
   |
   v
Isolated fetch worker
   |  không có cloud admin credential
   |  không có route tới DB/control plane
   |  chỉ outbound qua egress policy
   v
Public Internet / allowlisted destinations
   |
   v
Object storage quarantine
   |
   v
Scanner / content validation
   |
   v
Approved storage
~~~

Worker fetch nên có:

- Service account riêng với quyền tối thiểu.
- Không gắn credential cloud không cần thiết.
- Network policy chỉ cho DNS và outbound proxy cần thiết.
- Filesystem tạm thời, giới hạn dung lượng và không chứa secret.
- Timeout, byte limit, redirect limit và concurrency limit.
- Không chia sẻ cookie hoặc Authorization của người dùng với host đích.
- Không xử lý nội dung tải về như HTML/script trong cùng trust boundary với ứng dụng chính.

Tách workload không thay thế kiểm tra URL; nó giảm blast radius khi một lớp kiểm soát bị lỗi.

## 16. Mẫu kiểm tra destination trước khi kết nối

Một hàm kiểm tra an toàn không nên chỉ trả về boolean cho hostname thô. Nên tạo một đối tượng destination đã được xác minh, chứa hostname canonical, scheme, port và tập IP được phép:

~~~java
record ApprovedDestination(
    URI uri,
    String canonicalHost,
    int port,
    List<InetAddress> approvedAddresses
) {}
~~~

Luồng khái niệm:

~~~java
ApprovedDestination validateDestination(URI input) {
    requireAllowedScheme(input.getScheme());
    rejectUserInfo(input);
    rejectUnexpectedPort(input);

    String host = canonicalizeAndValidateHost(input.getHost());
    List<InetAddress> addresses = resolver.resolveAll(host);

    if (addresses.isEmpty()) {
        throw new DestinationRejectedException();
    }

    for (InetAddress address : addresses) {
        if (!ipPolicy.isGloballyReachable(address)) {
            throw new DestinationRejectedException();
        }
    }

    return new ApprovedDestination(
        input,
        host,
        effectivePort(input),
        addresses
    );
}
~~~

Đây là pseudocode, không phải implementation hoàn chỉnh. isGloballyReachable phải dùng bộ phân loại IP đầy đủ theo policy, không chỉ gọi một hàm isSiteLocalAddress(). resolver.resolveAll cần xử lý CNAME, A và AAAA; ApprovedDestination phải được HTTP transport sử dụng để pin socket tới một địa chỉ trong tập đã xác minh.

Khi thực hiện request:

1. Chọn IP đã duyệt và kết nối socket tới IP đó.
2. Với HTTPS, gửi SNI và xác minh certificate theo canonicalHost.
3. Gửi Host/:authority theo URL đã xác minh.
4. Không để transport tự resolve lại hostname.
5. Tắt redirect tự động; mỗi hop gọi lại validateDestination.
6. Giới hạn response bytes, thời gian và số lần redirect.

Nếu không thể ràng buộc socket tới IP đã kiểm tra, dùng egress proxy chịu trách nhiệm resolve, kiểm tra và kết nối trong cùng một boundary. Không coi bước validate DNS tách rời là đủ.

## 17. Ví dụ: API preview URL

Giả sử API:

~~~http
POST /api/previews
Content-Type: application/json
Authorization: Bearer <access-token>
~~~

~~~json
{
  "url": "https://docs.example.org/article/42"
}
~~~

Luồng xử lý:

1. Xác thực người gọi và kiểm tra quota preview.
2. Validate schema: URL là string, độ dài giới hạn, không có field header tùy ý.
3. Parse URI; chỉ cho phép HTTPS, port 443, không userinfo.
4. Canonicalize hostname và áp dụng domain policy.
5. Resolve CNAME, A và AAAA; từ chối mọi địa chỉ không global hoặc thuộc denylist nội bộ.
6. Pin kết nối tới IP đã kiểm tra, giữ TLS verification theo hostname.
7. Không gửi cookie, Authorization hoặc header nội bộ của người dùng.
8. Không tự theo redirect; nếu hỗ trợ, kiểm tra lại từng hop.
9. Giới hạn response 2 MB, timeout, số redirect và loại content.
10. Chỉ parse content type được hỗ trợ trong sandbox; không thực thi script.
11. Lưu kết quả vào cache theo URL canonical và policy scope phù hợp.
12. Ghi audit metadata và kết quả allow/deny, không log token hoặc body nhạy cảm.

Nếu URL trỏ tới 127.0.0.1, ::1, 169.254.169.254, hostname resolve tới private IP hoặc redirect tới metadata endpoint, API phải từ chối trước khi gửi request tới đích đó.

## 18. Phản hồi lỗi và không tiết lộ thông tin nội bộ

Khi URL hoặc đích đến bị từ chối, trả lỗi đủ để client sửa request nhưng không tiết lộ cấu trúc mạng:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
~~~

~~~json
{
  "code": "DESTINATION_NOT_ALLOWED",
  "message": "Địa chỉ đích không được phép."
}
~~~

Không trả chi tiết như:

- Đã tìm thấy Redis tại 10.0.4.12:6379.
- Metadata endpoint trả về token nhưng thiếu header.
- Danh sách toàn bộ IP private hoặc hostname nội bộ.
- DNS answer, route table hoặc tên service trong exception.

Thông tin chi tiết nên nằm trong security log có kiểm soát truy cập, với URL đã redact và IP/hostname ở dạng phù hợp cho điều tra. Không ghi query chứa token, signed URL hoặc credential.

## 19. Kiểm thử SSRF cho loopback, link-local và metadata

Kiểm thử phải chứng minh request không tạo kết nối tới địa chỉ bị cấm, không chỉ chứng minh API trả 400. Dùng mock DNS, HTTP server và network sandbox để quan sát địa chỉ peer thực tế.

| Nhóm test | Đầu vào/tình huống | Kết quả mong đợi |
|---|---|---|
| IPv4 loopback | 127.0.0.1, địa chỉ trong 127/8 | Bị từ chối |
| IPv6 loopback | [::1], dạng viết đầy đủ/rút gọn | Bị từ chối |
| Hostname local | localhost, localhost. | Bị từ chối |
| DNS-to-loopback | Domain public giả lập resolve về 127.0.0.1 | Bị từ chối |
| IPv4 link-local | 169.254.1.1, 169.254.169.254 | Bị từ chối |
| Container metadata | 169.254.170.2 và endpoint platform tương ứng | Bị từ chối |
| IPv6 link-local | fe80::/10, có/không zone ID | Bị từ chối |
| Private IPv4 | RFC1918 | Bị từ chối với public fetch |
| IPv6 ULA | fc00::/7 | Bị từ chối với public fetch |
| IPv4-mapped IPv6 | ::ffff:127.0.0.1 | Phân loại theo IPv4 và bị từ chối |
| Special-use | CGNAT, multicast, reserved, benchmark | Bị từ chối theo policy |
| Mixed DNS answer | Một A public, một AAAA private | Từ chối hostname |
| CNAME chain | CNAME cuối trỏ tới private IP | Bị từ chối |
| DNS rebinding | Resolve lần đầu public, lần kết nối private | Socket không kết nối private |
| Redirect | Public URL redirect tới loopback/metadata | Hop mới bị từ chối |
| Scheme/port | file:, gopher:, port không allowlist | Bị từ chối |
| URL userinfo | https://trusted.example@127.0.0.1/ | Bị parse đúng và từ chối |
| Proxy | Proxy tự resolve hoặc redirect | Egress proxy áp dụng cùng policy |
| IPv6/NAT64 | Prefix chuyển đổi chứa đích IPv4 bị cấm | Bị từ chối theo policy môi trường |
| Connection pool | Tái sử dụng connection giữa host khác nhau | Không có cross-authority reuse sai |

### 19.1 Kiểm thử qua network thật

Trong staging, dùng network namespace hoặc container sandbox có các listener giả lập tại loopback/link-local/private. Ghi nhận socket peer IP ở server nhận để chứng minh không có kết nối. Không gửi payload thử nghiệm tới metadata production hoặc hệ thống không thuộc quyền kiểm soát.

### 19.2 Regression test cho từng thư viện

Khi nâng cấp URI parser, DNS resolver, HTTP client, proxy hoặc runtime, chạy lại bộ test:

- URL IPv4/IPv6 literal.
- Redirect và Location tương đối.
- DNS A/AAAA/CNAME.
- Proxy environment variables.
- TLS SNI/hostname verification.
- Connection pool và DNS cache.

Hành vi phân giải và redirect có thể thay đổi theo phiên bản thư viện; test phải phản ánh đúng stack production.

## 20. Giám sát và ứng phó

Theo dõi các sự kiện:

- Request bị từ chối vì loopback, link-local, private hoặc metadata.
- Hostname resolve ra nhiều IP hoặc mixed public/private.
- CNAME chain bất thường, DNS rebinding suspicion hoặc thay đổi IP liên tục.
- Redirect bị từ chối do đích mới không hợp lệ.
- Outbound connection tới port/ASN/dải mạng không nằm trong policy.
- Worker fetch URL cố truy cập metadata hoặc internal service.
- Metadata endpoint được gọi bất thường bởi workload không có nhu cầu.
- Credential của workload được sử dụng từ service hoặc vị trí khác thường.

Security log nên chứa request ID, principal/tenant, hostname canonical đã redact phù hợp, IP phân loại, redirect count, quyết định policy và egress proxy result. Không ghi token metadata, response body hoặc signed URL đầy đủ.

Khi phát hiện SSRF thành công hoặc nghi ngờ:

1. Chặn egress của worker/endpoint bị ảnh hưởng hoặc tắt tính năng fetch.
2. Xác định hostname, IP peer, redirect chain, thời gian và workload đã kết nối.
3. Kiểm tra metadata access log và audit cloud; xác định credential/role có thể đã bị lộ.
4. Thu hồi hoặc xoay credential liên quan; giảm IAM scope nếu cần.
5. Tìm các hành động đã thực hiện bằng credential đó.
6. Xóa dữ liệu tải về, cache và artifact có thể chứa secret.
7. Sửa URL validation, DNS pinning, redirect policy và egress firewall.
8. Thêm regression test và theo dõi sau khi mở lại tính năng.

## 21. Các lỗi thiết kế thường gặp

1. **Chỉ chặn chuỗi localhost:** bỏ sót IP literal, IPv6 và hostname resolve về loopback.
2. **Chỉ chặn 127.0.0.1:** bỏ sót toàn bộ 127/8, ::1 và địa chỉ tương đương.
3. **Chỉ chặn RFC1918:** bỏ sót link-local, CGNAT, multicast, reserved và metadata.
4. **Chỉ kiểm tra A record:** bỏ sót AAAA hoặc lựa chọn IPv6 của HTTP client.
5. **Resolve để kiểm tra rồi resolve lại khi kết nối:** tạo DNS rebinding/TOCTOU.
6. **Tự động theo redirect:** request đầu public nhưng redirect vào mạng nội bộ.
7. **Tin header metadata bảo vệ cloud:** SSRF có thể kiểm soát header hoặc gặp endpoint không có cùng yêu cầu.
8. **Dùng regex để parse URL/IP:** xử lý sai userinfo, IPv6, encoding hoặc địa chỉ số.
9. **Chỉ kiểm tra trong application:** proxy, worker hoặc route khác vẫn có thể đi tới mạng nội bộ.
10. **Cho phép mọi port và scheme:** biến API fetch thành công cụ dò dịch vụ.
11. **Forward Authorization/Cookie tới host đích:** làm lộ credential của người dùng.
12. **Dùng một allowlist domain nhưng không pin IP:** DNS có thể thay đổi sau khi kiểm tra.
13. **Không kiểm tra redirect từng hop:** đích cuối vượt khỏi policy ban đầu.
14. **Worker fetch dùng chung credential với API chính:** một SSRF có thể chiếm quyền rộng hơn.

## 22. Quy trình thiết kế kiểm soát SSRF

Với mỗi endpoint hoặc worker có outbound fetch:

1. Xác định use case có thực sự cần URL tùy ý hay có thể dùng ID/nguồn đăng ký trước.
2. Xác định scheme, port, domain và loại nội dung được phép.
3. Parse URI nghiêm ngặt; từ chối userinfo, cú pháp mơ hồ và scheme không hỗ trợ.
4. Canonicalize hostname và IP literal; từ chối localhost/alias và zone identifier.
5. Resolve toàn bộ CNAME, A và AAAA; từ chối mọi địa chỉ không global hoặc nằm trong denylist tổ chức.
6. Pin socket tới IP đã xác minh; giữ TLS SNI và certificate verification theo hostname.
7. Tắt redirect tự động; kiểm tra lại mọi hop.
8. Kiểm soát proxy, DNS resolver, connection pool và NO_PROXY.
9. Giới hạn timeout, byte, port, redirect, concurrency và chi phí.
10. Chạy fetcher trong workload/network riêng, không có credential không cần thiết.
11. Áp dụng egress firewall/network policy cho IPv4 và IPv6.
12. Kiểm thử peer IP thực tế, DNS rebinding, redirect và metadata endpoint.
13. Giám sát outbound bất thường và có quy trình thu hồi credential khi sự cố.

## 23. Checklist rà soát

- [ ] Đã xác định mọi endpoint, worker và parser có thể tạo outbound request từ dữ liệu người dùng.
- [ ] URL được parse bằng URI parser chuẩn; chỉ cho phép scheme/port cần thiết.
- [ ] Từ chối loopback IPv4 toàn 127/8, IPv6 ::1 và hostname local.
- [ ] Từ chối link-local IPv4 169.254/16, IPv6 fe80::/10 và zone identifier.
- [ ] Chặn metadata endpoint và credential endpoint theo cloud/runtime đang sử dụng.
- [ ] Phân loại private, ULA, CGNAT, multicast, reserved và special-purpose theo policy cập nhật.
- [ ] Xử lý IPv4-mapped IPv6, IP literal không chuẩn và prefix NAT64/transition phù hợp môi trường.
- [ ] Resolve CNAME, A và AAAA; từ chối câu trả lời hỗn hợp public/private.
- [ ] Pin kết nối tới IP đã kiểm tra; TLS vẫn xác minh hostname.
- [ ] Tắt auto redirect hoặc kiểm tra lại scheme/host/IP/port ở mọi hop.
- [ ] Proxy/egress gateway thực thi cùng policy và không cho bypass qua NO_PROXY.
- [ ] Egress firewall chặn loopback, link-local, metadata và mạng nội bộ không cần thiết trên cả IPv4/IPv6.
- [ ] Fetcher không có cloud credential hoặc quyền nội bộ không cần thiết.
- [ ] Có giới hạn byte, timeout, redirect, concurrency và response content.
- [ ] Có test chứng minh socket không kết nối tới IP bị cấm, không chỉ kiểm tra status code.
- [ ] Có metric, audit và quy trình ứng phó credential exposure.

Chặn loopback, link-local và metadata service đòi hỏi kiểm soát địa chỉ thực tế tại thời điểm kết nối. Parse URL nghiêm ngặt, resolve toàn bộ DNS, phân loại IPv4/IPv6, pin socket, kiểm tra từng redirect và giới hạn egress tạo thành các lớp bảo vệ bổ sung. Khi SSRF fetcher không có credential rộng và không có đường mạng tới control plane, một lỗi kiểm tra đơn lẻ cũng khó biến thành sự cố chiếm quyền toàn bộ hạ tầng.

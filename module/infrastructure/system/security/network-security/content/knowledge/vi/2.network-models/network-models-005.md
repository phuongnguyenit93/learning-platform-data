# DMZ và vùng dịch vụ công khai

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **DMZ (Demilitarized Zone)** là gì, vì sao dịch vụ công khai cần được tách khỏi mạng nội bộ và giới hạn mà DMZ có thể bảo vệ.
- Đọc và thiết kế sơ đồ phân vùng mạng có Internet, vùng biên, DMZ, mạng ứng dụng, mạng dữ liệu và mạng quản trị.
- Xác định đúng luồng truy cập cần thiết, áp dụng nguyên tắc **mặc định từ chối (default deny)** và **đặc quyền tối thiểu (least privilege)** cho firewall.
- Phân tích các rủi ro như xâm nhập máy chủ web, di chuyển ngang, lạm dụng quyền quản trị, rò rỉ dữ liệu và truy cập ra ngoài từ DMZ.
- Đề xuất biện pháp bảo vệ và cách kiểm chứng DMZ trong hạ tầng tại chỗ, đám mây hoặc Kubernetes.

Bài này thuộc phạm vi `SECURITY_NETWORK_SECURITY`: xây dựng kiến trúc mạng an toàn bằng phân đoạn mạng, firewall, xác thực kết nối, giám sát xâm nhập và phân tích luồng lưu lượng. **DMZ là một ranh giới kiểm soát**, không phải một mạng mặc nhiên an toàn.

## 2. DMZ là gì?

**DMZ** là vùng mạng được tách riêng để đặt các thành phần cần giao tiếp với bên ngoài, chẳng hạn reverse proxy, web gateway, mail relay, DNS authoritative công khai hoặc cổng API. DMZ nằm giữa các nguồn có mức tin cậy khác nhau, thường là Internet và mạng ứng dụng nội bộ.

Nếu đưa máy chủ web có cổng công khai vào cùng mạng với cơ sở dữ liệu và hệ thống nhân sự, kẻ tấn công khai thác được web có thể dễ dàng tìm đường tới tài nguyên nhạy cảm. Đưa điểm tiếp nhận truy cập công khai vào DMZ giúp giới hạn phạm vi của một sự cố: từ DMZ chỉ có các đường kết nối đã được phê duyệt đi sâu hơn vào hệ thống.

Ba nguyên tắc cốt lõi:

1. **Phân vùng rõ ràng:** thiết bị DMZ không cùng vùng tin cậy với ứng dụng và dữ liệu nội bộ; sự phân tách phải được thực thi qua routing, firewall, ACL hoặc cơ chế tương đương.
2. **Kiểm soát mọi ranh giới:** chỉ mở đúng nguồn, đích, giao thức và cổng cần dùng; việc cho một cổng đi qua không đồng nghĩa dịch vụ phía sau đã an toàn.
3. **Giả định DMZ có thể bị xâm nhập:** thiết kế sao cho một máy trong DMZ bị chiếm quyền vẫn không thể tự do truy cập mạng ứng dụng, dữ liệu hay quản trị.

DMZ **không** đồng nghĩa với việc chỉ gán một VLAN tên `dmz`, mở NAT port-forward hay cài WAF. VLAN tổ chức lưu lượng ở lớp 2; NAT chuyển đổi địa chỉ; WAF lọc một số tấn công lớp ứng dụng. Để phân đoạn có hiệu lực, cần kiểm soát đường đi giữa các vùng và quyền truy cập ở cả lớp mạng lẫn ứng dụng.

## 3. Các vùng trong một kiến trúc điển hình

| Vùng | Thành phần thường gặp | Mức tiếp xúc và chính sách |
|---|---|---|
| Internet / mạng không tin cậy | Người dùng, bot, đối tác bên ngoài | Không cho đi trực tiếp vào ứng dụng hoặc cơ sở dữ liệu nội bộ. |
| Biên công khai (edge) | CDN, chống DDoS, WAF, public load balancer | Nhận kết nối công khai; lọc và chuyển đúng dịch vụ vào DMZ hoặc đích private được quy định. |
| DMZ | Reverse proxy, web gateway, mail relay, bastion dành riêng nếu có | Tiếp xúc với lưu lượng bên ngoài; bị hạn chế đường đi vào private và đường đi ra Internet. |
| Ứng dụng nội bộ (application/private) | API, service xử lý nghiệp vụ, worker | Chỉ nhận yêu cầu từ thành phần DMZ hoặc dịch vụ được phép; xác thực từng yêu cầu. |
| Dữ liệu (data) | Database, cache nhạy cảm, kho bí mật | Không nhận kết nối trực tiếp từ Internet hay DMZ; chỉ phục vụ danh tính ứng dụng được duyệt. |
| Quản trị (management) | VPN/ZTNA, bastion, giám sát, công cụ triển khai | Luồng tách biệt, xác thực mạnh, ghi nhật ký và giới hạn theo vai trò. |

Không phải hệ thống nào cũng có đủ sáu subnet vật lý. Một kiến trúc nhỏ có thể gộp một số thành phần, nhưng **ranh giới quyền truy cập** giữa luồng công khai, ứng dụng, dữ liệu và quản trị vẫn phải rõ.

### Sơ đồ tham chiếu

~~~mermaid
flowchart LR
    U["Người dùng Internet"] --> EDGE["CDN / DDoS / WAF"]
    EDGE --> F1["Firewall biên"]
    F1 --> RP["Reverse proxy / Gateway<br/>DMZ"]
    RP --> F2["Firewall nội bộ"]
    F2 --> APP["Ứng dụng API<br/>Mạng private"]
    APP --> PDB["Kiểm soát phân đoạn"]
    PDB --> DB[("Database<br/>Vùng dữ liệu")]
    ADMIN["Quản trị viên"] --> ACCESS["VPN hoặc ZTNA<br/>MFA"]
    ACCESS --> BASTION["Bastion quản trị"]
    BASTION -. "Quyền quản trị giới hạn" .-> RP
    BASTION -. "Theo phê duyệt" .-> APP
~~~

**Giải thích:** người dùng truy cập dịch vụ qua lớp bảo vệ biên và gateway DMZ. Gateway mới được phép chuyển yêu cầu sang một API cụ thể trong mạng private. API cần quyền riêng để đọc/ghi dữ liệu. Nhánh quản trị đi qua VPN hoặc ZTNA và bastion; không mở cổng quản trị cho toàn Internet. Sơ đồ là mô hình logic; trong triển khai cloud, WAF và load balancer có thể tích hợp với nhau.

## 4. Các kiểu triển khai DMZ

### 4.1. Firewall ba chân (three-legged firewall)

Một firewall có ít nhất ba giao diện hoặc vùng logic: `outside`, `dmz` và `inside`. Firewall quyết định luồng nào được chuyển giữa các vùng. Mô hình này đơn giản, dễ kiểm soát tập trung nhưng firewall trở thành điểm trọng yếu: sai chính sách hoặc hỏng thiết bị có thể ảnh hưởng nhiều vùng.

### 4.2. Screened subnet với hai lớp firewall

Firewall biên kiểm soát Internet ↔ DMZ; firewall nội bộ kiểm soát DMZ ↔ mạng ứng dụng. Cách này tách trách nhiệm, có thể tạo thêm chiều sâu phòng vệ và giảm tác động khi một cấu hình sai. Tuy nhiên, hai thiết bị không tự động an toàn hơn nếu chính sách bị mở quá rộng, thiếu giám sát hoặc cả hai phụ thuộc cùng hệ thống quản trị yếu.

### 4.3. Reverse proxy hoặc gateway làm điểm vào

Một public load balancer / reverse proxy nằm ở vùng biên hoặc DMZ nhận HTTPS rồi chuyển tiếp tới dịch vụ riêng. Đây là mô hình phổ biến cho website và API. Gateway có thể thực hiện định tuyến, giới hạn kích thước yêu cầu, rate limit và kiểm tra một số header. **Mỗi API vẫn cần xác thực và phân quyền riêng**; reverse proxy không thay thế kiểm tra quyền nghiệp vụ.

### 4.4. DMZ logic trong cloud và Kubernetes

Trong cloud, mô hình tương đương thường gồm public load balancer, subnet public cho điểm vào nếu cần, subnet private cho ứng dụng và subnet dữ liệu tách biệt. Security group, firewall, bảng định tuyến và kiểm soát danh tính cùng tạo ranh giới.

Trong Kubernetes, ingress controller / gateway xử lý lưu lượng từ ngoài vào; pod ứng dụng và database cần được giới hạn bằng `NetworkPolicy` hoặc cơ chế mạng phù hợp. **Namespace đơn thuần không tạo ra cô lập lưu lượng.** Chính sách chỉ có hiệu lực khi thành phần mạng (CNI) hỗ trợ và thực thi.

## 5. Thiết kế luồng lưu lượng: ai được nói chuyện với ai?

Giả sử một công ty cung cấp trang mua hàng công khai và API xử lý đơn. Dải địa chỉ minh họa:

- Public VIP: `203.0.113.10` (địa chỉ dành cho tài liệu, không phải địa chỉ triển khai thực tế).
- DMZ: `10.20.10.0/24`, reverse proxy `10.20.10.10`.
- Ứng dụng private: `10.20.20.0/24`, API `10.20.20.20`.
- Dữ liệu: `10.20.30.0/24`, PostgreSQL `10.20.30.30`.
- Quản trị: `10.20.40.0/24`, bastion `10.20.40.10`.

Khi viết yêu cầu firewall, luôn mô tả **nguồn → đích → giao thức/cổng → lý do → hành động**. Nếu có thể, dùng danh tính của workload hoặc nhóm bảo mật thay cho dải địa chỉ quá rộng.

| Luồng | Giao thức / cổng | Quyết định | Lý do |
|---|---|---|---|
| Internet → public VIP HTTPS | TCP 443 | Cho phép qua lớp bảo vệ biên | Tiếp nhận yêu cầu của người dùng. |
| Edge/WAF → reverse proxy DMZ | TCP 443 | Chỉ cho phép từ địa chỉ hoặc danh tính edge đã tin cậy | Không để client bỏ qua lớp edge. |
| Reverse proxy DMZ → API private | TCP 8443 | Chỉ `10.20.10.10` → `10.20.20.20` | Gửi yêu cầu đã định tuyến tới API. |
| API private → PostgreSQL | TCP 5432 | Chỉ `10.20.20.20` → `10.20.30.30` | Truy cập dữ liệu của ứng dụng. |
| VPN/ZTNA → bastion | HTTPS hoặc giao thức truy cập đã quản lý | Cho phép người dùng, thiết bị và vai trò hợp lệ | Thiết lập phiên quản trị có kiểm soát. |
| Bastion → máy cần quản trị trong DMZ | SSH TCP 22, khi thật sự cần | Cho phép theo đối tượng và thời hạn | Bảo trì có xác thực, ghi log. |
| Máy DMZ → resolver dành cho DMZ | UDP/TCP 53 | Chỉ resolver được chỉ định | Phân giải tên miền có kiểm soát. |
| Máy DMZ → egress proxy | TCP 443 | Chỉ proxy và đích cập nhật được duyệt | Cập nhật hệ thống hoặc gọi API cần thiết. |
| Internet → database, máy private, SSH/RDP DMZ | Mọi cổng không được công bố | Từ chối | Không phơi bày dịch vụ nội bộ hoặc quản trị. |
| DMZ → mọi hệ thống private khác | Mặc định mọi cổng | Từ chối và ghi nhận phù hợp | Ngăn quét mạng và di chuyển ngang. |

Trong bảng, luồng đầu tiên mô tả điểm vào công khai; luồng thứ hai mô tả bước chuyển tiếp sau edge. Nếu kiến trúc không dùng CDN/WAF tách riêng, các thành phần và quy tắc được điều chỉnh tương ứng.

### Quy tắc mẫu ở dạng giả mã

~~~text
DEFAULT_POLICY = DENY

ALLOW Internet      -> Public_VIP        TCP/443   # HTTPS công khai
ALLOW Trusted_Edge  -> DMZ_Reverse_Proxy TCP/443   # Chỉ qua WAF/edge
ALLOW DMZ_Proxy     -> Private_API       TCP/8443  # Đúng dịch vụ
ALLOW Private_API   -> Database          TCP/5432  # Chỉ workload API
ALLOW Bastion       -> Approved_DMZ_Host TCP/22    # Quyền và thời hạn riêng
ALLOW DMZ_Hosts     -> DMZ_DNS_Resolver  UDP,TCP/53
ALLOW DMZ_Hosts     -> Egress_Proxy      TCP/443

DENY  DMZ           -> Other_Private_Networks      LOG
DENY  Internet      -> Management_Or_Data          LOG
DENY  Any           -> Any                         LOG_RATE_LIMITED
~~~

Đây là **giả mã chính sách**, không phải cú pháp cấu hình dùng nguyên văn cho một firewall cụ thể. Thực tế cần xét thứ tự rule, chiều trả lời, NAT, định tuyến, các rule hệ thống và khả năng ghi log. Với firewall **stateful**, gói trả lời thuộc kết nối đã được phép thường được nhận diện theo trạng thái; với ACL/firewall **stateless**, phải cấu hình chiều về một cách phù hợp.

## 6. Sáu quyết định thiết kế thường dễ bị bỏ sót

### 6.1. Luồng vào (ingress)

Chỉ công bố đúng hostname và dịch vụ cần truy cập từ ngoài. Ưu tiên HTTPS với cấu hình TLS hiện hành, quản lý vòng đời chứng chỉ và giới hạn giao thức cũ. Nếu có CDN/WAF phía trước, ngăn client truy cập thẳng IP origin nếu yêu cầu kiến trúc là tất cả lưu lượng phải qua edge.

WAF giúp phát hiện hoặc chặn một số mẫu tấn công HTTP, nhưng không thể thay thế sửa lỗi ứng dụng như SQL injection, phân quyền thiếu kiểm soát hay logic nghiệp vụ sai.

### 6.2. Luồng từ DMZ vào private (east–west)

Đây là ranh giới quan trọng nhất để hạn chế tác động khi DMZ bị xâm nhập. Chỉ gateway được định danh mới được phép truy cập API đích; không mở cả subnet DMZ tới cả subnet private.

Mỗi yêu cầu đi sâu vào hệ thống cần được xác thực và phân quyền theo vai trò, phiên hoặc danh tính máy. Có thể dùng mTLS cho kết nối giữa các dịch vụ, song mTLS **xác thực hai đầu và bảo vệ kênh**, không tự quyết định người dùng có quyền xem đơn hàng nào.

### 6.3. Luồng từ DMZ ra ngoài (egress)

Máy DMZ cũng có thể khởi tạo kết nối ra Internet: tải gói cập nhật, gọi dịch vụ đối tác hoặc gửi dữ liệu cho kẻ tấn công sau khi bị chiếm quyền. Vì vậy, đừng mặc định mở outbound toàn bộ.

Nên cho phép các đích cụ thể qua egress proxy, resolver DNS được duyệt và dịch vụ thời gian nếu cần. Ghi nhận lưu lượng bất thường, ví dụ nhiều truy vấn DNS lạ, lưu lượng tải lên đột biến hoặc kết nối đến đích chưa từng thấy.

### 6.4. DNS và định tuyến

DNS public trỏ hostname dịch vụ tới địa chỉ công khai của edge hoặc load balancer; DNS private trả lời tên dịch vụ nội bộ theo quyền và nhu cầu truy cập. Không đưa tên, địa chỉ nội bộ hoặc bản ghi quản trị không cần thiết ra DNS public.

Cần kiểm tra **đường đi hai chiều** qua firewall và các thiết bị định tuyến. Định tuyến bất đối xứng có thể làm lưu lượng bị từ chối bởi firewall stateful. NAT/port-forward chỉ biến đổi địa chỉ, **không phải** ranh giới bảo mật độc lập.

### 6.5. Đường quản trị

Không mở SSH, RDP, bảng điều khiển database hoặc giao diện quản trị ra Internet chỉ vì máy nằm trong DMZ. Ưu tiên ZTNA/VPN, MFA, kiểm tra danh tính thiết bị, bastion, phân quyền theo nhiệm vụ và quyền tạm thời. Tài khoản dịch vụ DMZ không được mang quyền quản trị đối với toàn bộ mạng nội bộ.

Nhật ký quản trị cần thể hiện ai truy cập, khi nào, máy đích nào, quyền gì; nên gửi đến hệ thống log ngoài vùng có thể bị xâm nhập để hạn chế xóa dấu vết.

### 6.6. Tính sẵn sàng và cập nhật

Gateway hoặc firewall là đường đi trọng yếu, vì vậy phải thiết kế giám sát sức khỏe dịch vụ, dự phòng phù hợp, sao lưu cấu hình, quản lý thay đổi và phương án khôi phục. Triển khai bản vá có kiểm soát, kiểm tra lại rule sau khi thêm/bớt dịch vụ và xóa rule tạm đã hết hạn.

Một chính sách chặn quá mức có thể gây gián đoạn sản phẩm; chính sách mở quá mức làm suy yếu phân đoạn. Quản lý rule theo vòng đời giúp cân bằng hai yêu cầu này.

## 7. Phòng vệ nhiều lớp quanh DMZ

| Lớp kiểm soát | Vai trò | Giới hạn cần hiểu |
|---|---|---|
| Firewall/ACL/segmentation | Giới hạn nguồn, đích, cổng và hướng lưu lượng | Không phân biệt toàn bộ nội dung hay quyền nghiệp vụ. |
| WAF/API gateway | Lọc, định tuyến, hạn chế tốc độ và xác thực một số luồng HTTP | Không bảo đảm ứng dụng không có lỗ hổng. |
| IDS/IPS | IDS quan sát và cảnh báo; IPS có thể chủ động chặn dựa trên chính sách phát hiện | Cần hiệu chỉnh để tránh bỏ sót hoặc chặn nhầm. |
| DDoS protection/CDN | Hấp thụ hoặc lọc lưu lượng quá tải tại biên | Không xử lý lỗi phân quyền hay dữ liệu phía trong. |
| TLS/mTLS và quản lý chứng chỉ | Bảo vệ dữ liệu trên đường truyền; mTLS xác thực cả hai đầu | Không thay kiểm soát quyền dữ liệu. |
| EDR/hardening trên máy DMZ | Giảm bề mặt tấn công, phát hiện mã độc và hành vi bất thường | Không thay phân đoạn mạng. |
| Log tập trung/SIEM | Liên kết firewall, proxy, ứng dụng và danh tính để phát hiện sự cố | Chỉ hiệu quả khi log đầy đủ, đồng bộ thời gian và có quy trình xử lý. |

Khi phân tích lưu lượng, có thể quan sát các dấu hiệu: DMZ bắt đầu quét nhiều địa chỉ private, lượng truy vấn DNS tăng bất thường, gateway gửi dữ liệu ra đích mới, số lỗi xác thực tăng mạnh, hoặc backend nhận kết nối từ nguồn không nằm trong danh sách cho phép. Cần gắn **request ID / trace ID** qua các tầng và đồng bộ thời gian để điều tra đúng một phiên.

## 8. Mô hình hóa mối đe dọa: giả sử web gateway đã bị chiếm quyền

Hãy bắt đầu từ tài sản cần bảo vệ (dữ liệu khách hàng, khóa API, cơ sở dữ liệu), điểm vào (HTTPS public, giao diện quản trị, API đối tác), ranh giới tin cậy và quyền mỗi thành phần được cấp.

| Kịch bản | Điều gì có thể xảy ra? | Kiểm soát giảm thiểu |
|---|---|---|
| Khai thác lỗ hổng web hoặc reverse proxy | Kẻ tấn công chạy mã trên máy DMZ rồi thử kết nối vào mạng private | Vá lỗi, hardening, EDR; firewall chỉ mở gateway → đúng API; phân quyền ứng dụng. |
| Di chuyển ngang sau xâm nhập DMZ | Quét SMB, SSH, database, service discovery | Phân đoạn chặt, default deny, không dùng chung thông tin xác thực quản trị. |
| SSRF từ ứng dụng/gateway | Server bị lợi dụng gọi endpoint nội bộ hoặc dịch vụ metadata cloud | Kiểm soát egress, chặn các đích nhạy cảm, cấu hình an toàn metadata service, kiểm tra URL đầu vào. |
| Đánh cắp khóa API hoặc tài khoản dịch vụ | Sử dụng danh tính hợp lệ để gọi backend quá quyền | Bí mật lưu trong hệ thống quản lý secrets, xoay vòng, quyền tối thiểu, theo dõi hành vi bất thường. |
| DDoS hoặc bot làm nghẽn tầng công khai | Mất khả dụng gateway và ảnh hưởng dịch vụ phía sau | Chống DDoS, rate limit, giới hạn kết nối, autoscaling có giới hạn và cơ chế dự phòng. |
| Lạm dụng DNS hoặc kết nối outbound | Kết nối C2, tải mã độc hoặc rò rỉ dữ liệu | Resolver riêng, lọc đích DNS/HTTP, proxy egress, cảnh báo upload bất thường. |
| Chiếm phiên quản trị | Thay đổi firewall hoặc triển khai mã độc sâu hơn | MFA, phân quyền tách biệt, duyệt quyền tạm, log phiên và kiểm soát thiết bị. |

Một cách kiểm tra thiết kế hữu ích là hỏi: **“Nếu máy reverse proxy trong DMZ bị chiếm hoàn toàn, kẻ tấn công có thể truy cập trực tiếp cơ sở dữ liệu không?”** Kiến trúc trong ví dụ phải trả lời **không** ở mức đường mạng: chỉ API được phép kết nối database. Dù vậy, nếu API có lỗ hổng phân quyền, kẻ tấn công vẫn có thể lạm dụng API; vì vậy kiểm soát ở ứng dụng luôn cần thiết.

## 9. Truy vết một yêu cầu HTTPS hợp lệ

Ví dụ khách hàng gọi `https://shop.example.com/api/orders`:

1. DNS public trả về điểm vào edge hoặc public load balancer đã công bố.
2. Người dùng bắt tay TLS với endpoint được thiết kế để kết thúc TLS. Nếu dùng CDN/WAF, lớp này áp dụng chính sách lưu lượng và chuyển tiếp tới origin được cho phép.
3. Firewall/route đưa kết nối HTTPS từ edge tới reverse proxy DMZ; rule không cho client trực tiếp bỏ qua edge.
4. Reverse proxy chọn tuyến API, chuyển yêu cầu tới `10.20.20.20:8443` qua kết nối riêng có xác thực khi thích hợp.
5. API kiểm tra token, quyền của người dùng đối với đơn hàng và tính hợp lệ của dữ liệu.
6. Chỉ service API được truy cập PostgreSQL `10.20.30.30:5432` với danh tính database có quyền phù hợp.
7. Dữ liệu trả về theo những kết nối đã được phép; gateway ghi request ID, trạng thái và thời gian xử lý mà không lộ token hoặc dữ liệu nhạy cảm trong log.
8. Nhân viên vận hành đối chiếu log proxy, ứng dụng và firewall khi cần điều tra.

Có thể có nhiều chặng TLS độc lập: client ↔ edge, edge ↔ DMZ và DMZ ↔ API. **TLS bị kết thúc tại một proxy không có nghĩa chặng tiếp theo tự động được mã hóa**; từng chặng phải được cấu hình và kiểm tra.

## 10. DMZ trên hạ tầng đám mây: ví dụ tham chiếu

Với một hệ thống dùng VPC/VNet, có thể bố trí:

- **Public entry:** WAF gắn với CDN hoặc public application load balancer; các thành phần cần public reachability nằm trong cấu hình mạng tương ứng.
- **Private application subnet:** máy ảo/container chạy API chỉ nhận cổng backend từ security group hoặc endpoint của load balancer/gateway.
- **Private data subnet:** database chỉ nhận kết nối từ nhóm ứng dụng hợp lệ; không cấp public endpoint nếu không có nhu cầu đã duyệt.
- **Management plane:** ưu tiên truy cập quản trị qua dịch vụ quản lý danh tính/phiên từ xa, VPN hoặc ZTNA; theo dõi audit log.
- **Controlled outbound:** ứng dụng hoặc DMZ dùng NAT gateway/egress proxy khi cần kết nối outbound, kèm giới hạn đích phù hợp.

Trong AWS, **security group thường stateful**, còn **network ACL (NACL) stateless**. Subnet có tuyến tới Internet Gateway không tự làm cho mọi máy trong đó được Internet truy cập: còn phụ thuộc địa chỉ công khai, endpoint, security group, NACL và route thực tế. NAT gateway chủ yếu hỗ trợ outbound cho private subnet; không biến database thành dịch vụ public inbound.

Với Kubernetes, hãy kiểm tra thêm ingress/gateway, chính sách `NetworkPolicy` (bao gồm ingress *và* egress), tài khoản dịch vụ, secrets, quyền của ingress controller và khả năng CNI thực thi chính sách. Đừng dựa vào việc “pod ở namespace khác” để coi như đã có DMZ.

## 11. Triển khai, kiểm thử và vận hành

### Bước 1 — Lập danh mục dịch vụ và luồng

Ghi từng tài sản, chủ sở hữu, mức nhạy cảm, cổng phục vụ, nguồn được phép, dữ liệu truy cập và lý do nghiệp vụ. Vẽ đường đi của **người dùng**, **service-to-service**, **quản trị** và **kết nối outbound**; bốn nhóm này thường có quyền rất khác nhau.

### Bước 2 — Thực thi phân đoạn

Tạo zone/subnet và routing theo thiết kế, áp dụng firewall/ACL hoặc chính sách phân đoạn bằng cấu hình có quản lý phiên bản. Khởi đầu bằng deny mặc định và thêm các rule cần thiết, đủ hẹp về nguồn/đích, cổng và môi trường. Với dịch vụ động, ưu tiên nhóm bảo mật hoặc danh tính workload.

### Bước 3 — Bảo vệ ứng dụng và danh tính

Bật TLS, xác thực/ủy quyền ở API, chính sách tài khoản dịch vụ, lưu secrets đúng chỗ, hạn chế đặc quyền tiến trình và quản lý bản vá. WAF, IDS/IPS, EDR và chống DDoS bổ sung tùy mức rủi ro.

### Bước 4 — Kiểm tra cả đường hợp lệ và đường bị chặn

Trên hệ thống bạn có quyền kiểm thử, thực hiện bảng kiểm sau:

| Phép thử | Kỳ vọng |
|---|---|
| Người dùng ngoài truy cập hostname HTTPS hợp lệ | Truy cập thành công qua điểm vào chính thức, chứng chỉ hợp lệ. |
| Client ngoài thử đến port DB hoặc SSH/RDP | Không kết nối được; log/chính sách thể hiện đúng lý do. |
| Reverse proxy DMZ gọi đúng API/cổng | Thành công và có dấu vết request ID. |
| Máy khác trong DMZ thử truy cập database | Bị chặn. |
| Máy DMZ gọi ra địa chỉ Internet không được duyệt | Bị chặn hoặc buộc qua egress proxy được kiểm soát. |
| Quản trị viên hợp lệ qua VPN/ZTNA và bastion | Thành công với MFA và quyền đúng phạm vi. |
| Tài khoản không có quyền hoặc phiên hết hạn | Bị từ chối, có audit log. |
| Một node gateway hỏng | Cơ chế dự phòng/khôi phục hoạt động theo mục tiêu sẵn sàng đã thống nhất. |

Ví dụ kiểm tra HTTPS với tài nguyên được phép:

~~~bash
curl -I https://shop.example.com
~~~

Để kiểm tra rule firewall, cần nhìn **cả kết quả kết nối từ đúng vùng nguồn** và log tương ứng; một lệnh `curl` thành công từ máy cá nhân không chứng minh ranh giới DMZ ↔ private đã được khóa đúng. Kiểm tra định kỳ sau mỗi thay đổi route, WAF, gateway, autoscaling hoặc cấu hình mạng.

### Bước 5 — Quan sát và phản ứng sự cố

Tập trung log firewall, proxy, DNS, VPN/ZTNA, EDR và ứng dụng với thời gian đồng bộ; giới hạn thông tin nhạy cảm được ghi. Tạo cảnh báo theo mẫu như DMZ → database bị từ chối hàng loạt, kết nối outbound tới đích lạ, thay đổi firewall ngoài kế hoạch hoặc thất bại MFA tăng vọt.

Khi nghi ngờ máy DMZ bị xâm nhập, cần có quy trình cô lập workload/host, thu thập bằng chứng, thu hồi token, xác định luồng đã đi qua ranh giới, khôi phục từ bản tin cậy và điều chỉnh chính sách trước khi phục hồi dịch vụ.

## 12. Lỗi thiết kế phổ biến

| Sai lầm | Vì sao nguy hiểm? | Cách sửa |
|---|---|---|
| Đặt web, API và database chung một subnet “cho tiện” | Xâm nhập web có đường mạng thuận lợi tới dữ liệu | Tách zone và chặn trực tiếp DMZ → database. |
| Đặt tên VLAN là DMZ nhưng routing giữa các VLAN mở rộng | Nhãn VLAN không có tác dụng kiểm soát quyền | Đặt và kiểm thử ACL/firewall giữa các VLAN. |
| Mở `DMZ → LAN: ANY` để ứng dụng “chạy được” | Một máy DMZ bị chiếm có thể quét mạng nội bộ | Chỉ mở đúng nguồn, đích và cổng cần dùng. |
| Chỉ kiểm soát ingress, cho DMZ outbound tự do | Tạo đường tải mã độc hoặc rò rỉ dữ liệu | Dùng lọc egress, resolver riêng và giám sát kết nối. |
| Cho truy cập trực tiếp origin để thử lỗi | Bỏ qua WAF/rate limit và làm lộ origin | Dùng kênh quản trị riêng; giới hạn origin chỉ nhận từ edge. |
| Mở SSH/RDP public với mật khẩu | Gia tăng rủi ro dò quét, đánh cắp danh tính | VPN/ZTNA, MFA, bastion, quyền tối thiểu. |
| Tin toàn bộ lưu lượng từ DMZ là an toàn | DMZ là nơi dễ tiếp xúc nguồn tấn công | Xác thực backend, phân quyền API, mTLS khi phù hợp. |
| Dùng NAT như biện pháp bảo mật duy nhất | NAT không kiểm soát đầy đủ quyền hoặc lưu lượng ứng dụng | Áp dụng firewall, phân đoạn và xác thực. |
| Không thu hồi rule tạm và secrets cũ | Quyền tích lũy theo thời gian | Quy định chủ sở hữu, hạn dùng, review và xoay vòng. |

## 13. Bài tập tình huống

**Tình huống:** doanh nghiệp công bố website qua reverse proxy trong DMZ. Firewall hiện cho phép `10.20.10.0/24 → 10.20.0.0/16 : ANY`. Website phải đọc đơn hàng từ API và API cần truy cập PostgreSQL.

**Câu hỏi 1:** Rule hiện tại có vấn đề gì?

**Gợi ý trả lời:** cả subnet DMZ có thể truy cập một dải private lớn qua mọi cổng. Nếu một máy DMZ bị chiếm quyền, kẻ tấn công có thể kết nối tới nhiều máy nội bộ, bao gồm dịch vụ chưa công bố. Rule quá rộng và đi ngược nguyên tắc đặc quyền tối thiểu.

**Câu hỏi 2:** Nên thay rule bằng những luồng nào?

**Gợi ý trả lời:** chỉ reverse proxy `10.20.10.10 → API 10.20.20.20:8443`; chỉ API `10.20.20.20 → PostgreSQL 10.20.30.30:5432`. Phần còn lại từ DMZ đến private bị từ chối; tách thêm quản trị và DNS/egress theo nhu cầu. API vẫn kiểm tra quyền từng người dùng.

**Câu hỏi 3:** Những phép thử tối thiểu sau khi thay rule?

**Gợi ý trả lời:** xác nhận HTTPS public và API xử lý đơn hàng còn hoạt động; xác nhận DMZ không thể gọi trực tiếp database hoặc máy private khác; xác nhận quản trị có MFA và log; kiểm tra kết nối outbound và log firewall; kiểm tra khả năng phục hồi khi gateway gặp sự cố.

## 14. Checklist trước khi công bố một dịch vụ từ DMZ

- [ ] Đã xác định chính xác public hostname, điểm kết thúc TLS, đường đi qua edge và backend.
- [ ] Đã vẽ trust boundary giữa Internet, DMZ, application, data và management.
- [ ] Tất cả rule đều có nguồn/đích/cổng/lý do/chủ sở hữu; mặc định deny.
- [ ] Không có Internet → database hay DMZ → private rộng không có kiểm soát.
- [ ] Đã giới hạn outbound, DNS resolver, route, NAT và nguồn được phép truy cập origin.
- [ ] Backend xác thực và phân quyền; secrets và quyền máy dịch vụ được giới hạn.
- [ ] Giao diện quản trị chỉ đi qua kênh quản lý có xác thực mạnh và audit log.
- [ ] Có giám sát firewall, gateway, ứng dụng; có cảnh báo và quy trình sự cố.
- [ ] Có phép thử cho luồng được phép, luồng bị chặn và khả năng phục hồi.
- [ ] Có lịch review rule, cập nhật và thu hồi quyền tạm.

### Ghi nhớ

DMZ giúp công khai dịch vụ mà vẫn **giữ ranh giới kiểm soát với mạng nội bộ**. Thiết kế đúng không dừng ở chỗ đặt reverse proxy trong một subnet riêng: phải xác định luồng cần thiết, thực thi phân đoạn, bảo vệ danh tính, kiểm soát ingress/egress và chứng minh các đường truy cập không được phép thực sự bị chặn.

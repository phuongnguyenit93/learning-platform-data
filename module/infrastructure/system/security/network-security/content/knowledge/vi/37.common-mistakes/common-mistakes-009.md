# Sai lầm: Cho phép egress không giới hạn

**Chương:** Sai lầm thường gặp  
**Chủ đề:** Cho phép egress không giới hạn  
**Phạm vi:** Thiết kế và vận hành kiểm soát lưu lượng đi ra (outbound/egress) ở mạng doanh nghiệp, trung tâm dữ liệu, VPN, cloud và môi trường container.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích egress là gì, tại sao kiểm soát inbound chặt nhưng outbound tự do vẫn tạo rủi ro.
2. Nhận biết các cấu hình cho phép egress quá rộng, bao gồm `0.0.0.0/0`, `::/0`, `any service`, truy cập trực tiếp ra Internet và đường đi vòng qua proxy.
3. Phân tích rủi ro command-and-control (C2), rò rỉ dữ liệu, tải mã độc, truy cập API ngoài ý muốn và di chuyển giữa các vùng tin cậy.
4. Thiết kế chính sách outbound theo danh tính workload, mục đích nghiệp vụ, đích kết nối và loại giao thức; duy trì DNS, NTP, xác thực, backup và đường phục hồi cần thiết.
5. Hiểu giới hạn của firewall, NAT, VPN, DNS filtering, TLS inspection, egress proxy, IDS/IPS, cloud security groups và Kubernetes NetworkPolicy.
6. Di chuyển từ `allow all` sang kiểm soát có đo lường, thử nghiệm, giám sát, phê duyệt, rollback và xử lý ngoại lệ.

Trong module `SECURITY_NETWORK_SECURITY`, sai lầm này minh họa vì sao phòng vệ mạng phải kết hợp **segmentation, firewall, VPN, IDS/IPS, kiểm soát danh tính, DNS, hạ tầng không dây và cloud, giám sát lưu lượng cùng threat modeling**. Không lớp nào tự mình thay thế được chính sách outbound hợp lý.

## 2. Egress là gì và vì sao “cho phép tất cả” nguy hiểm?

**Egress** là lưu lượng khởi tạo từ một hệ thống/vùng mạng đi tới đích khác bên ngoài ranh giới đang xét. Ví dụ:

- Máy trạm doanh nghiệp truy cập Internet qua proxy hoặc firewall.
- Máy chủ ứng dụng gọi API thanh toán của đối tác.
- Workload cloud gửi dữ liệu tới kho lưu trữ hoặc dịch vụ SaaS.
- Pod trong Kubernetes gọi API ở mạng ngoài cluster.
- Máy chủ ở VLAN ứng dụng kết nối qua VPN tới mạng đối tác.
- Hệ thống giám sát chuyển log tới nền tảng phân tích từ xa.

Một kết nối **ra khỏi vùng tin cậy** không nhất thiết đi ra Internet: lưu lượng từ vùng ứng dụng sang vùng quản trị hoặc sang cloud account/region khác cũng có thể là egress đối với nguồn. Ranh giới và chính sách phải được ghi rõ.

Sai lầm điển hình là suy luận:

> “Chúng ta đã chặn hết inbound từ Internet; outbound cho phép tất cả sẽ không có vấn đề.”

Với firewall **stateful**, một phiên được nguồn nội bộ khởi tạo và cho phép đi ra thường cho phép các gói phản hồi thuộc phiên đi ngược vào. Nếu máy trạm hoặc ứng dụng đã bị xâm nhập, nó có thể thiết lập kết nối đến máy chủ ngoài tổ chức. NAT có thể che IP riêng của máy nguồn nhưng **không ngăn hành vi gửi dữ liệu hoặc liên lạc ra ngoài**. Chính sách inbound tốt vẫn quan trọng, song không giải quyết trọn vẹn rủi ro từ phiên outbound.

### Hệ quả thường gặp

| Tình huống | Điều outbound tự do tạo điều kiện | Tác động có thể xảy ra |
|---|---|---|
| Endpoint bị nhiễm phần mềm độc hại | Liên lạc tới máy chủ điều khiển hoặc tải thành phần bổ sung | Duy trì hoạt động xâm nhập, mở rộng phạm vi |
| Ứng dụng web có lỗ hổng SSRF | Máy chủ kết nối tới đích nội bộ/bên ngoài không thuộc chức năng được phép | Truy cập dịch vụ nhạy cảm hoặc làm lộ thông tin |
| Tài khoản dịch vụ bị lạm dụng | Gửi dữ liệu đến dịch vụ lưu trữ do bên khác kiểm soát | Rò rỉ dữ liệu, khó truy vết |
| Máy build/CI bị chiếm quyền | Truy cập kho phần mềm hoặc endpoint không được duyệt | Rủi ro chuỗi cung ứng và artifact |
| Máy chủ được phép dùng DNS tùy ý | Dùng resolver không quản lý hoặc một số kênh vượt kiểm soát DNS | Thiếu telemetry, mất chính sách phân giải tên |
| Mạng khách/IoT không phân vùng outbound | Thiết bị gọi đích và dịch vụ tùy ý | Lạm dụng tài nguyên và kết nối bất thường |

**Giảm quyền egress không bảo đảm ngăn được mọi cuộc tấn công.** Kẻ tấn công có thể lợi dụng đích hợp lệ hoặc giao thức phổ biến; chính sách cần đi cùng quản lý endpoint, ứng dụng, danh tính, quan sát và phản ứng sự cố.

## 3. Nhận diện những biểu hiện cấu hình sai

| Biểu hiện | Nguy cơ | Điều cần xác minh |
|---|---|---|
| Allow source `any` → destination `0.0.0.0/0`, service `any` | Bất kỳ máy IPv4 trong phạm vi có thể khởi tạo nhiều loại kết nối | Đối tượng nguồn thực tế, thứ tự rule, route và NAT |
| Egress IPv6 `::/0` rộng dù chỉ quản trị IPv4 | Bỏ sót đường IPv6 hoặc dual-stack | IPv6 routing, RA/DHCPv6, policy tương ứng |
| Máy chủ sản xuất truy cập Internet trực tiếp | Bỏ qua proxy, lọc domain, xác thực và audit tập trung | Đường mặc định, public IP, NAT và đường dự phòng |
| Cho phép TCP/443 tới mọi IP | HTTPS có thể mang nhiều loại payload, kể cả lưu lượng ngoài nghiệp vụ | Proxy, domain/app allowlist, TLS metadata và hạn chế trực tiếp |
| Proxy được triển khai nhưng firewall vẫn cho direct egress | Client có thể đi vòng proxy | Chỉ cho phép proxy/gateway ra ngoài theo vai trò |
| Tất cả subnet dùng một outbound policy | Không phân biệt máy trạm, ứng dụng, database, quản trị | Luồng nghiệp vụ của từng lớp tài sản |
| Mở toàn bộ UDP vì “cần DNS” | Mở rộng kênh outbound ngoài UDP/53 | Resolver thực tế, QUIC, VPN, NTP và giao thức khác |
| Mở đường qua VPN/peering không giới hạn | Lệch ranh giới giữa tổ chức, đối tác và cloud | Route, chính sách liên vùng, quyền người dùng/workload |
| Policy chỉ áp dụng trên firewall trung tâm | Cloud/local path hoặc IPv6 có thể đi ngoài điểm kiểm soát | Sơ đồ tuyến end-to-end và điểm thực thi chính sách |

`0.0.0.0/0` và `::/0` trong bảng là các dải đích bao phủ mọi địa chỉ IPv4/IPv6 tương ứng. Bản thân việc chúng xuất hiện trong **route table** không tự khẳng định rule bảo mật cho phép mọi lưu lượng: cần phân biệt **tuyến có thể đi** và **chính sách nào cho phép đi**.

## 4. Mô hình hóa đường tấn công và điểm kiểm soát

Giả sử máy chủ ứng dụng chỉ cần gọi một API thanh toán đã được phê duyệt. Nhưng policy lại cho phép nó kết nối đến bất kỳ host Internet nào qua TCP/443.

~~~mermaid
flowchart LR
    U["Người dùng"]
    WA["Web/API<br/>vùng ứng dụng"]
    DB["CSDL<br/>vùng dữ liệu"]
    FW["Firewall / egress gateway"]
    PARTNER["API đối tác<br/>được duyệt"]
    EXT["Đích Internet khác<br/>không thuộc nhu cầu"]

    U -->|"HTTPS hợp lệ"| WA
    WA -->|"DB protocol được cấp quyền"| DB
    WA -->|"Outbound HTTPS"| FW
    FW -->|"Cần được phép"| PARTNER
    FW -.->|"Allow all khiến đường này mở"| EXT
~~~

Nếu xảy ra lỗ hổng ứng dụng hoặc thông tin xác thực bị lạm dụng, đường chấm là khả năng liên lạc bổ sung mà attacker có thể khai thác. Trong một thiết kế tối thiểu quyền, chỉ kết nối phục vụ mục đích được duyệt mới được phép; luồng khác bị từ chối và ghi nhận ở điểm thích hợp.

### Diễn giải đúng về phòng vệ nhiều lớp

- **Ingress control** giới hạn ai có thể kết nối vào ứng dụng. Nó không tự giới hạn kết nối được ứng dụng khởi tạo.
- **Segmentation và host firewall** giới hạn luồng từ một zone/workload sang zone khác, bao gồm tài nguyên nhạy cảm nội bộ.
- **Egress policy, proxy và DNS control** điều chỉnh đường ra đích ngoài vùng tin cậy theo mục đích.
- **Identity và quyền ứng dụng** giới hạn điều workload được phép làm trên dịch vụ đích; IP/port không thay thế được xác thực.
- **EDR, IDS/IPS, NDR và SIEM** giúp phát hiện hành vi bất thường và điều tra các ngoại lệ vượt khả năng ngăn chặn của policy.

Đường phòng vệ phải hoạt động cả khi ứng dụng dùng kết nối mã hóa hoặc chuyển qua region/ISP dự phòng.

## 5. Vì sao outbound TCP/443 không đồng nghĩa an toàn?

HTTPS phổ biến, vì vậy nhiều tổ chức chọn mở `TCP/443 → Internet` để tránh lỗi nghiệp vụ. Tuy nhiên, cổng 443 chỉ là thông tin về transport; nó **không bảo đảm đích, giao thức ứng dụng, danh tính hoặc nội dung được phép**.

| Dữ liệu mà thiết bị có thể thấy | Có thể kết luận | Hạn chế |
|---|---|---|
| Destination IP/port và khối lượng lưu lượng | Máy nguồn kết nối đến địa chỉ, cổng nào; tần suất và hướng byte | Shared hosting/CDN có nhiều dịch vụ chung IP |
| DNS request từ resolver doanh nghiệp | Tên miền nào được truy vấn qua resolver đó | Không chứng minh rằng kết nối sau đó đến đúng dịch vụ; cache/DoH có thể làm thiếu log |
| TLS SNI khi có thể quan sát | Hostname được client khai báo trong quá trình handshake | ECH có thể che tên; SNI không phải chứng cứ xác thực danh tính đích |
| Chứng chỉ TLS trong một số kiến trúc | Thông tin về chứng chỉ/chuỗi tin cậy tùy ngữ cảnh quan sát | TLS 1.3 và kiến trúc mạng ảnh hưởng khả năng nhìn thấy; chứng chỉ hợp lệ không bảo đảm nội dung an toàn |
| HTTP request qua proxy được ủy quyền | Host, URL hoặc phương thức ở mức phù hợp với proxy | Với HTTPS CONNECT không giải mã, proxy thường không nhìn thấy toàn bộ nội dung request |
| TLS inspection được phê duyệt | Có thể áp chính sách lớp 7 ở một số luồng | Có yêu cầu riêng về quyền riêng tư, tương thích, quản lý CA và loại trừ dịch vụ nhạy cảm |

Với **HTTP/3/QUIC qua UDP/443**, chính sách chỉ xem TCP/443 sẽ không bao phủ hết luồng. Cần quyết định có cho phép QUIC và dùng điểm kiểm soát tương thích hay không. Việc chặn UDP/443 có thể khiến một số client rơi về TCP, nhưng không nên xem đó là bảo đảm tất cả hành vi được giám sát.

**SNI hoặc domain allowlist một mình không đủ để chứng thực ứng dụng đích.** Trong các mô hình có độ tin cậy cao, nên kết hợp identity của workload, proxy nhận biết protocol, xác thực TLS đúng hostname, chính sách phía dịch vụ đích và telemetry.

## 6. Ba quyết định quan trọng của chính sách egress

### 6.1. Ai được phép đi ra?

Phân loại theo **vai trò của nguồn**:

- User endpoint: duyệt web qua secure web gateway/proxy, chính sách theo người dùng và thiết bị.
- Application service: chỉ truy cập API và dependency đã khai báo, theo service identity/workload identity.
- Database: thông thường không cần Internet trực tiếp; chỉ các luồng replication, backup, update hoặc monitoring thật sự cần.
- Build agent: truy cập registry, kho package và dịch vụ CI có kiểm soát; dùng cache/mirror nội bộ nếu hợp lý.
- Management/bastion: đường cập nhật hệ điều hành, xác thực và quản trị có audit, tách vai trò khỏi app.
- IoT/OT và wireless guest: phân đoạn riêng, hạn chế giao thức/destination theo chức năng thiết bị.

Kết hợp **nguồn theo identity/tag/namespace** với network zone/địa chỉ nếu nền tảng hỗ trợ. IP-based policy vẫn cần cho nhiều thiết bị, nhưng một IP có thể thay đổi hoặc được tái sử dụng.

### 6.2. Được đi đâu và làm gì?

Một rule phải nêu:

| Thuộc tính | Câu hỏi |
|---|---|
| Source | Máy, nhóm dịch vụ hoặc danh tính workload nào? |
| Destination | IP/CIDR, FQDN, domain, private endpoint hoặc dịch vụ cụ thể nào? |
| Protocol/port | TCP/UDP/ICMP nào, ứng dụng nào, có TLS/mTLS không? |
| Purpose | Luồng thuộc nghiệp vụ, cập nhật phần mềm, DNS, monitoring hay DR? |
| Owner | Ai chịu trách nhiệm xác nhận nhu cầu và đánh giá lại? |
| Lifetime | Quyền vĩnh viễn, theo kỳ hay là ngoại lệ hết hạn? |
| Inspection/log | Đi qua proxy/firewall nào, ghi telemetry ở đâu? |
| Failure mode | Khi đích không sẵn sàng hoặc egress gateway lỗi, hệ thống xử lý ra sao? |

**Deny-by-default** là định hướng tốt cho vùng nhạy cảm khi có kế hoạch triển khai phù hợp. Nó không có nghĩa bật “deny all” trên production khi chưa biết phụ thuộc; làm vậy có thể làm hỏng cấp token, kiểm tra chứng chỉ, khởi động container, sao lưu hoặc ứng cứu.

### 6.3. Đi qua điểm kiểm soát nào?

Luồng Internet nên có đường ra được quản lý, ví dụ:

~~~mermaid
flowchart TB
    APP["Ứng dụng vùng private"]
    RES["Resolver DNS được quản lý"]
    EG["Egress firewall / proxy<br/>policy + audit"]
    NAT["NAT / public egress"]
    API["Endpoint ngoài được duyệt"]
    BLOCK["Đích không được duyệt"]

    APP -->|"DNS theo policy"| RES
    APP -->|"Outbound theo rule"| EG
    EG --> NAT
    NAT --> API
    EG -.->|"Deny + log khi phù hợp"| BLOCK
~~~

**NAT không phải là bộ lọc nội dung hoặc danh tính.** NAT chuyển đổi địa chỉ; việc cho phép hoặc từ chối phải đến từ firewall, security group, proxy hoặc kiểm soát tương đương. Cần chặn đường bypass khi ứng dụng có public IP trực tiếp, đường transit thứ hai hoặc policy VPN khác.

## 7. Xây ma trận outbound tối thiểu theo nghiệp vụ

Ví dụ một dịch vụ `order-api` trong môi trường doanh nghiệp, các endpoint dưới đây đều là giả lập:

| Source | Destination | Dịch vụ | Mục đích | Kỳ vọng |
|---|---|---|---|---|
| `order-api` | `api.payments.example` | HTTPS/TCP 443 | Gọi API thanh toán được duyệt | Allow qua kiểm soát egress; xác thực TLS và API |
| `order-api` | Resolver doanh nghiệp `10.66.0.53` | DNS UDP/TCP 53 | Phân giải tên theo chính sách | Allow, có DNS query log phù hợp |
| `order-api` | IdP endpoint được duyệt | HTTPS/TCP 443 | Lấy khóa xác minh/refresh token khi cần | Allow theo danh sách dependency đã đo |
| `order-api` | Collector telemetry đã duyệt | TLS/TCP 443 hoặc giao thức agent | Gửi metrics/log | Allow, kiểm tra lưu trữ khi collector lỗi |
| `order-api` | `10.66.30.10` | DB port theo công nghệ | Truy vấn DB qua phân đoạn nội bộ | Allow theo quyền tối thiểu |
| `order-api` | Internet any | All | Không có nhu cầu khai báo | Deny; cảnh báo theo ngưỡng |
| DB service | Internet any | All | Không có nhu cầu trực tiếp | Deny; dùng luồng cập nhật/backup cụ thể nếu cần |
| Máy quản trị | NTP/patch mirror nội bộ | Giao thức đã duyệt | Đồng bộ thời gian, cập nhật | Allow theo policy riêng |

Tên miền `.example` được dùng cho minh họa, không phải API thật. Một số nhà cung cấp sử dụng nhiều hostname và địa chỉ CDN thay đổi thường xuyên; hãy lấy danh sách dependency được hãng công bố và kiểm chứng thực tế. Tránh mở toàn bộ cloud provider IP range nếu nhu cầu chỉ là một dịch vụ cụ thể.

### Phân biệt endpoint chức năng và endpoint hỗ trợ

Ứng dụng có thể cần các đường phụ thuộc ít thấy trong log API:

- **DNS:** resolver nội bộ và forwarder đã được kiểm soát.
- **NTP:** đồng bộ thời gian để xác thực, ghi log, Kerberos/TLS hoạt động đúng.
- **PKI:** kiểm tra OCSP/CRL hoặc cơ chế trạng thái chứng chỉ theo ứng dụng.
- **Identity:** OIDC discovery, JWKS, token endpoints, MFA hoặc hệ thống directory.
- **Observability:** exporter, remote logging, SIEM, health monitoring.
- **Deployment:** registry container, artifact store, package mirror, license activation.
- **Business continuity:** backup/restore, DR replication, secondary-region endpoints.
- **External integrations:** cổng thanh toán, email gateway, dịch vụ đối tác và webhook.

Trước khi siết policy, phải phân biệt **kết nối thật đang sử dụng**, **đường cần cho phục hồi nhưng ít dùng** và **đường đã hết nhu cầu**.

## 8. Kiểm soát DNS để giảm đường vòng

Đặt resolver được quản lý là điểm phân giải tên chính cho workload; giới hạn truy cập DNS công cộng trực tiếp nếu chính sách yêu cầu. DNS filtering có thể chặn domain độc hại, domain mới đăng ký hoặc đích ngoài allowlist theo khả năng sản phẩm.

Tuy vậy:

1. Chặn DNS/UDP 53 ra Internet **không tự ngăn** mọi phương thức phân giải tên: DNS-over-HTTPS (DoH) qua TCP/443 và DNS-over-TLS (DoT) qua TCP/853 có thể xuất hiện.
2. Một ứng dụng có thể dùng **IP cố định**, cached DNS result hoặc kết nối tới đích được hard-code.
3. DNS query thành công không đồng nghĩa kết nối thực sự được thiết lập; cần ghép với flow/proxy log.
4. Domain có thể chia sẻ IP với nhiều tenant; policy chỉ theo IP hoặc suffix quá rộng có thể cho phép đích khác.
5. Domain allowlist cần lifecycle và owner; wildcard rộng như `*.example.net` có thể cho phép nhiều dịch vụ không thuộc nhu cầu.

Đối với hệ thống nhạy cảm, kết hợp DNS control với **egress enforcement trên đường IP/HTTP thực tế**. Sự kiện bất thường như truy vấn tên rất dài, entropy cao, tần suất khác baseline hoặc query tới resolver trái phép cần được phân tích trong SOC; không tự kết luận mọi chuỗi domain lạ là exfiltration.

## 9. Cloud, container, VPN và mạng không dây

### 9.1. Cloud VPC/VNet

Nhiều môi trường có security group mặc định cho outbound rộng, hoặc rule `0.0.0.0/0:all` được sao chép trong template. Cần kiểm tra:

- Security group/NSG/NACL đang áp dụng **thực tế** cho subnet, NIC và workload.
- Internet gateway, NAT gateway, private endpoints, transit gateway, peering và routing.
- Public IP, elastic IP, serverless connector hoặc đường riêng có thể bypass egress gateway.
- IPv6 egress riêng, firewall policy, WAF và policy ở từng account/project/region.
- IAM cho việc sửa route/firewall và audit control plane; kẻ tấn công có quyền cloud đủ lớn có thể thay đổi cả đường kiểm soát.

Trong nhiều cloud, security group là **stateful allow-list** và không có deny rule tương đương firewall đầy đủ; Network ACL có thể **stateless**. Flow logs cũng không nhất thiết chỉ ra trực tiếp *rule cụ thể* đã quyết định luồng. Cần kiểm tra đúng hành vi của nền tảng đang sử dụng.

**Private endpoint/service endpoint** có thể giúp tránh kết nối qua Internet cho dịch vụ cloud, nhưng vẫn phải giới hạn **ai** được truy cập tài nguyên **nào** và quyền API ở lớp dịch vụ. Một đường private rộng không tự bảo đảm least privilege.

### 9.2. Kubernetes

Kubernetes `NetworkPolicy` có thể giới hạn ingress/egress cho các Pod được chọn khi CNI triển khai thực sự hỗ trợ enforcement. Nếu không có NetworkPolicy chọn Pod theo hướng egress, mặc định ở nhiều cluster sẽ không có isolation theo NetworkPolicy cho hướng đó.

Ví dụ chính sách **default-deny egress** trong namespace lab, dùng để minh họa nguyên tắc:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: demo-egress-lab
spec:
  podSelector: {}
  policyTypes:
    - Egress
~~~

**Không áp dụng thẳng lên production.** Chính sách này chọn mọi Pod trong namespace và mặc định chặn egress theo mô hình NetworkPolicy, trừ khi có NetworkPolicy khác cho phép những luồng cần thiết. NetworkPolicy có tính **cộng dồn** các quy tắc cho phép của những policy cùng chọn Pod; ví dụ trên không tự chứng minh egress đã bị chặn nếu policy khác đang allow. Cần tạo allow rules cho DNS, service-to-service, registry/telemetry khi phù hợp, và kiểm tra bằng phép thử thực tế.

NetworkPolicy API chuẩn **không có bộ lọc FQDN/HTTP path gốc**; nếu cần kiểm soát domain, dùng giải pháp egress proxy/gateway hoặc khả năng mở rộng của CNI được chọn. Đừng cho rằng policy Pod sẽ chặn traffic của node, hostNetwork hoặc mọi tuyến ở cấp hạ tầng.

### 9.3. VPN và SD-WAN

**Split tunneling** có thể khiến lưu lượng Internet đi thẳng từ endpoint ra ISP, ngoài firewall trung tâm. Full tunneling đưa nhiều traffic về điểm kiểm soát nhưng cần băng thông, định tuyến và HA phù hợp. Với VPN đối tác/site-to-site, kiểm tra prefix quảng bá, chiều lưu lượng, ACL hai đầu và các tuyến dự phòng; đừng cấp quyền `any-any` cho toàn bộ mạng đối tác chỉ vì “tunnel đã mã hóa”.

### 9.4. Wireless, IoT và OT

Mạng khách nên tách khỏi mạng nhân viên, máy quản trị và tài nguyên nhạy cảm. IoT/OT thường chỉ cần một số endpoint update/telemetry đã duyệt; nhưng chặn ngay mọi egress có thể ảnh hưởng vận hành hoặc cập nhật bảo mật. Cần inventory giao thức, chu kỳ thiết bị, thời gian bảo trì và đường support theo ủy quyền.

## 10. Đưa chính sách vào chu trình phát triển và vận hành

### 10.1. Egress contract của một dịch vụ

Mỗi ứng dụng nên khai báo **các outbound dependency** trước khi triển khai:

~~~yaml
# Khai báo ý định để review/policy-as-code; không phải schema mặc định của cloud.
service: order-api
environment: production
owner: payments-platform
egress:
  - destination: api.payments.example
    protocol: HTTPS
    port: 443
    purpose: third-party-payment-api
    traffic_via: approved-egress-proxy
  - destination: corporate-dns
    protocol: DNS
    ports: [53]
    purpose: name-resolution
  - destination: corporate-telemetry
    protocol: TLS
    port: 443
    purpose: app-metrics-and-logs
default_action: deny
review_period: quarterly
~~~

Tài liệu khai báo là **nguồn yêu cầu thiết kế**, cần chuyển thành firewall/IaC đúng nền tảng và kiểm chứng rằng path triển khai thực sự thực thi. Mỗi mục có owner, hạn review và tiêu chí khi dịch vụ đối tác thay đổi địa chỉ.

### 10.2. Policy-as-code và bảo vệ control plane

Khi có nhiều zone, cluster, region hoặc cloud account:

- Sinh rule từ contract và template đã review; tránh dùng `allow any outbound` để “sửa tạm” deployment.
- Kiểm tra drift giữa trạng thái mong muốn và thực tế, bao gồm đường egress phụ và IPv6.
- Yêu cầu phê duyệt khi mở rộng đích, mở cổng quản trị, thay đổi default route hoặc bypass proxy.
- Áp dụng IAM tối thiểu cho tài khoản sửa network policy, lưu audit và cảnh báo thay đổi đột ngột.
- Triển khai dần theo canary/workload để phát hiện dependency chưa khai báo.
- Duy trì quy trình ngoại lệ có hạn dùng và chủ sở hữu, thay vì để rule tạm tồn tại vô thời hạn.

## 11. Quy trình chuyển từ allow-all sang egress tối thiểu

~~~mermaid
flowchart TD
    I["Inventory tài sản / owner / tuyến"]
    O["Observe flow, DNS, proxy, app logs"]
    M["Map luồng thành dependency"]
    R{"Có nhu cầu nghiệp vụ<br/>hoặc DR được xác minh?"}
    A["Đưa vào allowlist theo phạm vi nhỏ"]
    Q["Đánh dấu UNKNOWN / xác minh owner"]
    D["Thiết kế deny-by-default + logging"]
    C["Canary / staging / shadow review"]
    T{"Kiểm thử nghiệp vụ<br/>và bảo mật đạt?"}
    B["Rollback thay đổi và bổ sung dependency"]
    P["Rollout theo đợt + theo dõi"]
    X["Hết hạn ngoại lệ / review định kỳ"]
    I --> O --> M --> R
    R -- "Có" --> A --> D
    R -- "Chưa rõ" --> Q --> M
    R -- "Không" --> D
    D --> C --> T
    T -- "Không" --> B --> M
    T -- "Có" --> P --> X
~~~

### Bước 1 — Xác định scope và baseline

Liệt kê subnet/zone, workload, tài khoản cloud, cluster, egress gateway, public IP, tuyến VPN/SD-WAN, các nút dự phòng và người sở hữu. Ghi policy version, thời gian, trạng thái logging, route table, NAT/proxy config. Đo các SLI trước thay đổi: tỷ lệ API thành công, DNS error, timeout, latency, authentication failure, backup status.

### Bước 2 — Quan sát traffic và nhu cầu ẩn

Thu flow/firewall/proxy/DNS logs theo khoảng thời gian đủ bao phủ tác vụ ngày, tuần, tháng, quý và kịch bản DR khi có liên quan. Đối chiếu ứng dụng, CMDB, lịch bảo trì và người sở hữu. Cẩn thận với log bị sampling, retention ngắn, source IP thay đổi sau NAT và những luồng ít phát sinh.

Tách **observed flow** khỏi **approved dependency**: traffic đang có có thể do phần mềm độc hại hoặc cấu hình sai, không nên tự động chuyển toàn bộ thành allowlist.

### Bước 3 — Thiết kế policy theo từng nhóm

Ưu tiên rule có mục đích rõ, giới hạn source/destination/service, đường quản trị egress, điều kiện log và hạn xem xét. Với nguồn không được phép ra Internet, chọn deny-by-default. Khi đích là SaaS/CDN thường thay đổi, cân nhắc proxy có kiểm soát domain/URL và khả năng theo dõi policy, thay vì hard-code một tập IP dễ lỗi thời.

### Bước 4 — Phê duyệt và rollout có kiểm soát

Thử ở lab/staging nếu có, sau đó canary một nhóm máy/workload ít rủi ro, theo dõi số request fail, DNS error, API 4xx/5xx, timeout, thông tin proxy deny, các đường quản trị, backup và khả năng recover. Chỉ tăng phạm vi rollout khi kết quả phù hợp với tiêu chí.

### Bước 5 — Theo dõi, rollback và duy trì

Có kế hoạch khôi phục cấu hình cụ thể, owner trực, cửa sổ thay đổi và ngưỡng dừng. Khi lỗi xảy ra, xác minh log và dependency rồi **rollback đúng phần thay đổi gây lỗi**; không chuyển cả môi trường về `any-any` lâu dài. Đóng ticket kèm bằng chứng, cập nhật contract và lên lịch review các ngoại lệ.

## 12. Giám sát và phát hiện egress bất thường

### 12.1. Nguồn telemetry cần kết hợp

| Nguồn | Tín hiệu gợi ý | Giới hạn |
|---|---|---|
| Firewall/egress gateway | Policy allow/deny, cổng, địa chỉ, byte, session | Không luôn nhận biết danh tính hay nội dung trong TLS |
| Proxy/SWG | Host, URL, user/workload identity, phân loại đích tùy khả năng | CONNECT tunnel có thể thiếu chi tiết; có đường bypass nếu routing cho phép |
| DNS resolver | FQDN, source, thời gian, query type | Thiếu kết nối theo IP, cache hoặc encrypted DNS ngoài resolver |
| VPC/NSG flow log | Source/destination, bytes, accept/reject theo nền tảng | Thường không chứa URL, rule ID chính xác hoặc payload |
| EDR/host telemetry | Process nào tạo kết nối; executable signer/path nếu được thu | Không tự khẳng định đích hợp lệ về nghiệp vụ |
| App/APM | Gọi API nào, tỷ lệ lỗi, trace/transaction | Có thể không quan sát các kết nối ngoài ứng dụng |
| Cloud audit | Ai sửa security group, route, gateway, IAM | Ghi hành động control plane; không thay thế flow log |
| IDS/IPS/NDR | Mẫu lưu lượng/đích và hành vi nghi vấn | Phát hiện phụ thuộc chữ ký, khả năng giải mã và baseline |

Các sự kiện cần chuẩn hóa tối thiểu `timestamp_utc, workload_id, source_ip, destination_ip, destination_port, protocol, action, bytes_out, device/context, policy_id`. Bổ sung DNS/hostname, user/process và change ticket nếu nguồn hỗ trợ. IP sau NAT chỉ là một góc nhìn; phải có mapping để quy về máy tạo kết nối.

### 12.2. Truy vấn giả lập phát hiện đích chưa được phê duyệt

Giả sử SIEM đã chuẩn hóa bảng `NetworkFlows`, trường `ApprovedDestination` được tạo bằng cách đối chiếu inventory policy theo vai trò ứng dụng. Đây là **schema minh họa**, không phải bảng mặc định của một sản phẩm:

~~~kusto
NetworkFlows
| where TimeGenerated > ago(24h)
| where Direction == "Egress"
| where SourceZone == "application"
| where Decision == "Allow"
| where ApprovedDestination == false
| summarize Sessions = count(),
            TotalBytesOut = sum(BytesOut),
            LastSeenUtc = max(TimeGenerated)
    by WorkloadId, DestinationIP, DestinationPort, Protocol
| order by TotalBytesOut desc
~~~

Kết quả là các **ứng viên cần điều tra**: có thể là dependency hợp lệ chưa được khai báo, lỗi đối chiếu object/IP hoặc hành vi bất thường. Kiểm tra log gốc, asset owner, DNS, proxy, process và thời điểm thay đổi trước khi kết luận.

### 12.3. Ví dụ quy tắc cảnh báo theo hành vi

- Ứng dụng bình thường chỉ truy cập một tập API nhưng đột ngột có nhiều đích mới.
- Tốc độ gửi dữ liệu ra ngoài tăng bất thường, đặc biệt từ zone không có nhu cầu truyền dữ liệu lớn.
- Máy chủ database hoặc máy quản trị khởi tạo kết nối Internet không thuộc policy.
- Client liên tục bị deny khi truy cập một miền/địa chỉ khác baseline.
- Xuất hiện dịch vụ phân giải tên không được quản lý hoặc traffic DoH/DoT ngoài policy.
- Security group/route/NAT bị sửa mở quyền egress trong lúc không có change được phê duyệt.

Cảnh báo dựa trên hành vi cần kết hợp **ngữ cảnh workload và cửa sổ bảo trì** để tránh nhiều false positive. Một lần proxy deny không đồng nghĩa hệ thống đang bị xâm nhập.

## 13. Sai lầm khi khắc phục sai lầm egress

| Biện pháp tưởng đúng | Vì sao có thể chưa đủ hoặc gây lỗi | Cách làm có kiểm chứng |
|---|---|---|
| Chặn tất cả outbound tức thì | Hỏng DNS, NTP, PKI, token, backup, telemetry và API | Inventory, staging, canary, rollout theo đợt và rollback |
| Chỉ chặn port “nguy hiểm” | Kênh không mong muốn vẫn có thể dùng HTTPS 443 | Kiểm soát đích/ứng dụng, identity, proxy và phát hiện |
| Dùng NAT gateway làm “egress firewall” | NAT không tự phân loại và ngăn đích độc hại | Egress policy thực sự và log trên đường ra |
| Chỉ allow IP của CDN/SaaS | Địa chỉ có thể đổi và được chia sẻ cho nhiều tenant | Kiểm soát dịch vụ/domain ở lớp phù hợp và quyền API |
| Chỉ allow theo hostname do client gửi | SNI/DNS có thể không thể quan sát đầy đủ hoặc bị khai báo sai | Xác thực đích, proxy, TLS validation và kiểm soát theo identity |
| Dùng DNS filtering mà bỏ firewall | Client có thể kết nối thẳng IP hoặc dùng cơ chế phân giải khác | Ghép DNS policy với enforcement đường mạng |
| Ghi toàn bộ packet/payload | Nguy cơ lộ bí mật, chi phí cao, luật riêng tư và vận hành khó | Thu metadata tối thiểu cần thiết, kiểm soát quyền và retention |
| Mở ngoại lệ `any-any` “để xử lý sự cố” | Tạo lỗ hổng lâu dài, khó kiểm toán | Ngoại lệ có scope, owner, TTL/expiry, audit và review |
| Chỉ bảo vệ IPv4 | Đường IPv6 có thể đi ngoài policy | Đánh giá dual-stack hoặc tắt IPv6 có kiểm soát nếu không dùng |
| Chỉ kiểm tra môi trường chính | Region DR hoặc VPN dự phòng có thể bypass kiểm soát | Kiểm thử failover/backup path và policy parity |
| Tin rằng chặn Internet sẽ ngăn SSRF | SSRF còn có thể gọi dịch vụ nội bộ/metadata | Chặn theo phân đoạn và bảo vệ metadata endpoint, input validation |

**Đường metadata của cloud** thường là tài nguyên nội bộ theo nền tảng và có cơ chế bảo vệ riêng; vì vậy chỉ chặn Internet outbound không đủ để giảm toàn bộ rủi ro SSRF/credential exposure.

## 14. Kịch bản thực tế: ứng dụng SaaS vượt quyền outbound

**Bối cảnh giả định:** doanh nghiệp có vùng ứng dụng `app-prod`. Một API xử lý đơn hàng chỉ cần gọi cổng thanh toán `api.payments.example`, IdP và dịch vụ telemetry. Security group cloud đang allow mọi outbound IPv4, còn firewall trung tâm tập trung ở luồng inbound.

**Chuỗi sự kiện:** sau một đợt deploy, máy chủ bắt đầu gửi kết nối HTTPS tới một nhóm hostname không nằm trong danh sách dependency. SOC chỉ có VPC flow logs, thấy IP và bytes tăng nhưng khó biết tiến trình, owner và domain thực tế. Chưa có bằng chứng xác nhận hoạt động độc hại; cũng chưa thể nói đây là thay đổi nghiệp vụ hợp lệ.

**Phân tích:**

1. Security group outbound `0.0.0.0/0` tạo quyền truy cập vượt nhu cầu đã biết.
2. NAT/proxy routing thiếu enforcement khiến mọi kết nối TCP/443 được cho phép.
3. Danh sách dependency của ứng dụng không được cập nhật vào policy và không có identity-level attribution.
4. Thiếu proxy/EDR/DNS correlation khiến thời gian điều tra tăng.
5. Nếu siết ngay mọi kết nối HTTPS, các luồng IdP/OCSP/telemetry có thể lỗi.

**Hướng xử lý:** xác minh chính xác các đích mới bằng log gốc, process/trace và chủ hệ thống; giữ nguyên chứng cứ nếu đang điều tra sự cố. Đồng thời xây proxy/gateway có allowlist cho dependency hợp lệ, giới hạn đường trực tiếp ra Internet, triển khai canary và dùng log để đánh giá tác động. Tách bài toán security incident nếu có dấu hiệu xâm nhập, không chỉ xem là lỗi rule.

### Kết quả mong đợi của đợt cải tiến

| Tiêu chí | Trước | Sau khi triển khai và kiểm thử |
|---|---|---|
| Quyền outbound của `order-api` | Mọi IPv4/port được phép qua một số đường | Chỉ các đích/giao thức đã phê duyệt |
| Luồng API thanh toán | Không có rule/owner cụ thể | Có owner, policy, audit và kiểm thử end-to-end |
| Đích Internet ngoài nhu cầu | Có thể thiết lập kết nối | Bị deny trên đường được quản lý; sinh telemetry phù hợp |
| DNS và IdP | Phụ thuộc ẩn, dễ lỗi khi thay policy | Khai báo đầy đủ, test trong canary/failover |
| Quan sát | Flow IP/bytes khó quy kết | Kết hợp proxy/DNS/EDR/app với workload ID |
| Vận hành | Ngoại lệ phát sinh tùy lúc | Có change, expiry, owner và phương án rollback |

## 15. Kiểm thử chính sách egress

Thiết kế test nên bao gồm cả **positive test** (những gì được phép phải hoạt động) và **negative test** (những gì không được phép phải bị chặn), trong phạm vi lab/staging được cấp phép.

### 15.1. Ma trận kiểm thử

| Kiểm thử | Phép kiểm tra | Kỳ vọng và chứng cứ |
|---|---|---|
| API được duyệt | Gọi endpoint thử nghiệm của đối tác | TLS/auth hợp lệ, ứng dụng xử lý thành công, log policy allow |
| DNS nội bộ | Phân giải tên qua resolver quản lý | Kết quả đúng và DNS log phù hợp |
| Đích không được duyệt | Kết nối tới endpoint lab ngoài allowlist | Không thiết lập được phiên; kiểm tra deny log nếu nền tảng hỗ trợ |
| Bypass proxy | Thử kết nối trực tiếp tới cùng đích ngoài qua route khác | Bị chặn khi policy yêu cầu phải qua proxy |
| IPv6 | Kiểm tra một địa chỉ IPv6 trong lab không được duyệt | Bị chặn tương đương IPv4 |
| Ứng dụng sau restart | Restart workload test có dependency đã khai báo | Khởi động thành công, token/secret/cert hợp lệ |
| Backup và DR | Diễn tập đường phục hồi đã được duyệt | Không mất đường egress quan trọng ở chế độ dự phòng |
| Egress gateway lỗi | Tắt giả lập thành phần trong lab | Hành vi fail-safe/fail-closed đúng policy; cảnh báo và rollback |

Một ví dụ đơn giản trên Windows:

~~~powershell
# Chạy ở máy lab thuộc phạm vi cho phép, với địa chỉ/test host của lab.
# Chỉ kiểm tra khả năng thiết lập kết nối TCP; không chứng minh an toàn ứng dụng.
Test-NetConnection -ComputerName allowed-api.demo.example -Port 443
Test-NetConnection -ComputerName blocked-host.demo.example -Port 443
~~~

Với Linux:

~~~bash
# Chỉ chạy đối với endpoint lab được phê duyệt.
# -I gửi yêu cầu HEAD; thất bại có thể do TLS, DNS, HTTP hoặc proxy policy.
curl -I --max-time 10 https://allowed-api.demo.example/
~~~

Các hostname `.demo.example` trong ví dụ là chỗ điền minh họa, phải thay bằng endpoint do đội lab sở hữu/cấu hình; chúng không bảo đảm phân giải được. **Không suy ra firewall deny chỉ từ timeout**: còn có thể do DNS, TLS, HTTP, server down hoặc route lỗi. Cần đối chiếu flow/firewall/proxy logs và ứng dụng.

### 15.2. Tiêu chí dừng

Dừng hoặc rollback thay đổi khi xuất hiện giao dịch quan trọng lỗi vượt ngưỡng đã thống nhất, authentication/certificate validation hỏng, backup/restore thất bại, proxy/gateway quá tải, thiếu telemetry bắt buộc hoặc traffic đi đường ngoài kiểm soát. Ghi chính xác rule/policy version trước và sau, thời điểm triển khai và kịch bản đã thử.

## 16. Đo hiệu quả vận hành

Không nên lấy “số lượng deny log” làm chỉ số thành công duy nhất. Có thể đo:

| KPI | Định nghĩa | Ý nghĩa |
|---|---|---|
| `Egress policy coverage` | Workload trong scope có policy outbound cụ thể / tổng workload trong scope | Mức phủ kiểm soát |
| `Dependency ownership` | Dependency có owner và purpose / tổng dependency đã biết | Độ rõ trách nhiệm |
| `Direct-egress exposure` | Workload còn đường Internet không qua enforcement / tổng workload cần kiểm soát | Khả năng bypass |
| `Unknown egress ratio` | Flow không map được vào dependency/owner / flow quan sát | Chất lượng inventory và telemetry |
| `Exception aging` | Ngoại lệ quá hạn review / tổng ngoại lệ | Rủi ro tích lũy từ temporary allow |
| `Post-change failure rate` | Change egress gây lỗi dịch vụ / tổng change egress | Chất lượng triển khai và kiểm thử |
| `Detection time` | Thời gian từ dấu hiệu outbound bất thường đến alert có điều tra | Hiệu quả giám sát |
| `DR egress readiness` | Luồng dự phòng được kiểm thử đạt / tổng luồng DR cần kiểm thử | Tính sẵn sàng thực tế |

Tách số liệu theo vùng mạng, môi trường (lab/staging/production), region, IPv4/IPv6 và nhóm owner. Giảm số kết nối được phép không luôn đồng nghĩa giảm rủi ro nếu đã chuyển phần lớn kết nối sang một allowlist wildcard quá rộng.

## 17. Bài tập tình huống và câu hỏi tự kiểm tra

**Tình huống:** mạng doanh nghiệp có ba nhóm tài sản:

- **Web app:** chỉ gọi API thanh toán, IdP và collector log; nhưng security group cho outbound `any → any`.
- **Database:** không có nhu cầu Internet thường xuyên, nhưng cần một đường backup đã lên lịch.
- **Máy trạm người dùng:** sử dụng secure web gateway, tuy nhiên VPN split tunnel cho phép một số luồng đi thẳng qua mạng nhà.

**Yêu cầu:**

1. Chỉ ra ba loại rủi ro chính của outbound không giới hạn trong tình huống.
2. Lập ma trận rule theo source, destination, protocol, owner, logging và thời hạn review.
3. Vì sao nên phân biệt policy egress của web app, database và máy trạm?
4. Tại sao chỉ chặn outbound TCP/22 và TCP/25 vẫn không giải quyết đầy đủ rủi ro?
5. Xây hai kiểm thử “được phép” và hai kiểm thử “bị chặn” cho web app, có telemetry tương ứng.
6. Làm gì để tránh ảnh hưởng đường backup của database hoặc luồng VPN split tunnel khi chuyển policy?

**Gợi ý trả lời:** Web app bị mở rộng bề mặt C2/exfiltration/SSRF; database có thể ra ngoài quá nhu cầu; máy trạm có đường bypass gateway. Policy cần khác nhau theo vai trò, với web app chỉ được gọi API/IdP/log, database chỉ có backup và dependency rõ ràng, máy trạm qua SWG hoặc kiểm soát endpoint thích hợp. Chặn vài cổng không hạn chế được lưu lượng qua HTTPS; cần kiểm soát destination/app/identity. Kiểm thử bao gồm gọi API và DNS được duyệt; thử kết nối tới endpoint lab ngoài allowlist và đường direct bypass; kiểm tra log gateway, DNS, host và trạng thái ứng dụng. Trước thay đổi phải thực hiện baseline/owner sign-off, backup/DR test, VPN route audit, rollout theo nhóm và rollback.

### Tự kiểm tra nhanh

1. NAT gateway có phải là egress firewall không? Vì sao?
2. Egress policy chỉ dùng IP allowlist gặp vấn đề gì khi nhà cung cấp dùng CDN?
3. Điều gì có thể xảy ra khi deny outbound ngay lập tức mà chưa liệt kê luồng xác thực và PKI?
4. Nếu máy chủ có cả IPv4 và IPv6, cần kiểm tra gì trước khi tuyên bố “egress đã bị khóa”?
5. Vì sao một flow outbound bị deny là tín hiệu đáng xem, nhưng không đủ để kết luận có tấn công?

**Đáp án trọng tâm:** (1) NAT chuyển địa chỉ và có thể hỗ trợ chuyển lưu lượng, không tự quyết định đích hợp lệ. (2) IP thay đổi/chia sẻ, dễ bypass hoặc chặn nhầm. (3) Lỗi token/OCSP/CRL/khởi động và gián đoạn ứng dụng. (4) Route và enforcement cho cả hai stack, gồm failover path. (5) Có thể là dependency thiếu khai báo, chương trình lỗi hoặc kết nối vô hại; phải ghép ngữ cảnh.

## 18. Checklist dùng khi review một kiến trúc

- [ ] Xác định ranh giới egress cho từng zone/workload; có bản đồ đường ra thực tế.
- [ ] Không có allow `any-any` không có owner và lý do được duyệt.
- [ ] Kiểm tra cả IPv4 `0.0.0.0/0` và IPv6 `::/0` cùng các đường NAT, public IP, VPN và transit.
- [ ] Workload production có danh sách outbound dependency, owner và hạn review.
- [ ] DNS, NTP, identity, PKI, update, registry, telemetry, backup/DR đã được khai báo.
- [ ] Proxy/firewall enforcement có cơ chế ngăn direct bypass.
- [ ] Hạn chế egress theo destination, dịch vụ, danh tính và mức tin cậy phù hợp; không chỉ dựa vào port.
- [ ] Có lưu log đủ điều tra, với quyền truy cập và retention thích hợp; phân biệt thiếu log với không có traffic.
- [ ] Thay đổi policy có canary, positive/negative tests, điều kiện dừng và rollback đã kiểm chứng.
- [ ] Ngoại lệ có owner, phạm vi tối thiểu, thời hạn và lịch xem xét lại.
- [ ] Mạng cloud, Kubernetes, VPN, wireless/IoT và region DR được kiểm thử theo failure mode thật.
- [ ] SOC có cảnh báo thay đổi control plane và kết nối ra đích trái baseline.

## 19. Ghi nhớ

**Egress không giới hạn là mở quyền cho mọi hệ thống đã được phép chạy bên trong tự do khởi tạo thêm quan hệ tin cậy với các đích bên ngoài.** Điều đó làm tăng khả năng kết nối không mong muốn, cản trở kiểm soát dữ liệu và khiến việc điều tra xâm nhập phức tạp. Kiến trúc tốt dùng nguyên tắc **chỉ cho phép những luồng outbound có mục đích, danh tính và bằng chứng rõ**, cưỡng chế tại đường mạng thực tế, duy trì các phụ thuộc hợp lệ và có quy trình thay đổi an toàn. Firewall, DNS, proxy, segmentation, IAM, IDS/IPS, EDR cùng giám sát phải phối hợp để hạn chế khả năng lạm dụng mà vẫn giữ được tính sẵn sàng của hệ thống.

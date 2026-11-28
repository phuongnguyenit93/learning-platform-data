# Encrypted traffic visibility: IDS/IPS nhìn thấy gì khi lưu lượng được mã hóa?

Khi người dùng truy cập một website qua HTTPS, ứng dụng gọi API qua mTLS hoặc chi nhánh kết nối qua VPN, dữ liệu trên đường truyền có thể được **mã hóa**. Mã hóa giúp bảo vệ bí mật và tính toàn vẹn thông tin, nhưng đồng thời làm giảm khả năng đọc trực tiếp nội dung gói tin của hệ thống **Intrusion Detection System (IDS)** và **Intrusion Prevention System (IPS)** đặt ở giữa đường truyền. Bài toán **encrypted traffic visibility** là tìm cách có đủ tín hiệu để phát hiện, điều tra và ngăn chặn rủi ro **mà không phá vỡ mục đích bảo vệ của mã hóa**.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, hiểu giới hạn quan sát của IDS/IPS giúp thiết kế firewall, phân đoạn mạng, VPN, bảo vệ DNS, Wi-Fi và môi trường cloud một cách nhất quán. Một kiến trúc giám sát tốt phải biết **sensor đang nhìn thấy lớp giao thức nào, tại điểm nào, có được giải mã hợp pháp hay không, và còn nguồn telemetry nào bổ trợ**.

> **Nguyên tắc:** Không mặc định giải mã mọi kết nối là cần thiết hoặc phù hợp. Ưu tiên xác định mục tiêu phát hiện, dữ liệu tối thiểu, quyền truy cập, phương án kiểm soát tại endpoint hoặc điểm kết thúc TLS và yêu cầu bảo vệ quyền riêng tư. Chỉ thực hiện kiểm thử hoặc thu thập gói trên hạ tầng đã được cấp quyền.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **metadata mạng**, **thông tin bắt tay** và **payload ứng dụng** trong lưu lượng mã hóa.
2. Giải thích những gì sensor có thể và không thể quan sát với **TLS 1.2, TLS 1.3, HTTPS, QUIC/HTTP/3, ECH, DoH/DoT, SSH và IPsec**.
3. So sánh visibility từ **network IDS/NDR, IPS inline, reverse proxy/WAF, endpoint EDR, DNS resolver và telemetry cloud**.
4. Thiết kế chiến lược phát hiện **không giải mã**, **giải mã tại điểm kết thúc được ủy quyền** và **ghép tín hiệu đa nguồn**.
5. Xác định các rủi ro của TLS inspection: quyền riêng tư, quản lý chứng chỉ/khóa, khả năng tương thích, hiệu năng và false positive.
6. Xây dựng ma trận kiểm thử có bằng chứng để đo **coverage và blind spot** thay vì cho rằng IDS/IPS nhìn thấy toàn bộ lưu lượng.

## 2. Visibility là gì và không phải là gì?

**Visibility** là khả năng quan sát những thông tin đủ hữu ích để trả lời câu hỏi vận hành hoặc bảo mật. Một cảm biến thấy có kết nối tới một địa chỉ IP khác rất nhiều so với việc biết nội dung HTTP request, người dùng thực hiện thao tác nào hoặc payload có chứa mẫu khai thác hay không.

Có thể chia thông tin thành ba lớp:

| Lớp thông tin | Ví dụ | Có thể hữu ích cho việc gì? |
|---|---|---|
| **Network/flow metadata** | IP nguồn/đích, cổng, protocol, thời gian, số byte/gói, hướng, thời lượng phiên | Phát hiện thay đổi đường kết nối, lưu lượng bất thường, quét mạng, egress không mong muốn |
| **Protocol/handshake metadata** | Một số trường ClientHello, phiên bản giao thức, ALPN, SNI khi hiển thị, đặc điểm QUIC | Phân loại loại kết nối, phát hiện client bất thường, kiểm tra thay đổi chính sách |
| **Application content** | URL path, query/body HTTP, header nghiệp vụ, dữ liệu API, lệnh ứng dụng | Kiểm tra signature tầng ứng dụng, phân tích payload cụ thể, điều tra hoạt động nghiệp vụ |

**Không có một sensor nào mặc nhiên nhìn thấy đủ cả ba lớp.** Khả năng quan sát phụ thuộc vị trí bắt gói, cơ chế mã hóa, giao thức, điểm kết thúc TLS, quyền xem log, kiến trúc proxy và cách tải trọng được bảo vệ.

Ví dụ một sensor giữa laptop và máy chủ HTTPS có thể ghi nhận **10.10.10.25 → 10.20.20.10:443/TCP**, số byte và một phần handshake. Nó **không mặc nhiên đọc được** đường dẫn **/api/payments**, mã HTTP hoặc body giao dịch. Một reverse proxy kết thúc TLS ở phía server có thể xem request HTTP sau giải mã, nhưng không nhất thiết biết mọi thao tác xảy ra ở database phía sau.

### Phân biệt IDS, IPS và NDR trong luồng mã hóa

- **Network IDS (NIDS):** thường nhận bản sao lưu lượng qua SPAN/TAP hoặc sensor ảo; phân tích và tạo cảnh báo. Đường giám sát không nhất thiết có quyền chặn gói.
- **Network IPS (NIPS):** nằm trên đường đi hoặc tại điểm thực thi chính sách, có thể quyết định cho qua/chặn theo khả năng sản phẩm. Đặt inline **không đồng nghĩa** tự đọc được nội dung TLS.
- **Network Detection and Response (NDR):** thường kết hợp flow, metadata, phân tích hành vi và telemetry để điều tra hoạt động mạng; thuật ngữ này bao gồm nhiều kiến trúc sản phẩm khác nhau.
- **Host IDS/EDR và application monitoring:** quan sát tại endpoint hoặc tiến trình, nơi có thể thấy hành vi trước mã hóa hoặc sau giải mã nếu được cấu hình và có quyền.

Không nên dùng nhãn **“Deep Packet Inspection”** để khẳng định thiết bị đã giải mã được kết nối; “kiểm tra sâu” vẫn có thể bị giới hạn ở những byte thực sự có thể quan sát.

## 3. Bắt gói ở đâu quyết định nhìn thấy gì

Sơ đồ khái niệm:

~~~text
             Client / Endpoint
             ├── EDR, tiến trình, DNS client
             └── Dữ liệu ứng dụng trước mã hóa
                        |
                        | TLS/QUIC/IPsec đã mã hóa
                        v
                 [Switch / Router]
                        |
                  [NIDS / NDR TAP]
                  Metadata và handshake
                        |
                   [Firewall / IPS]
                  L3/L4, flow, policy
                        |
               [Reverse Proxy / WAF]
                  Kết thúc TLS nếu có
                  HTTP và access log
                        |
                   [Ứng dụng]
                Tracing, authorization
                        |
                   [Database]
                   Audit / query log
~~~

Mỗi lớp trả lời một nhóm câu hỏi:

| Điểm thu thập | Thường có thể thấy | Thường không tự thấy |
|---|---|---|
| TAP/SPAN giữa client và edge | Header IP/TCP/UDP, flow, một phần bắt tay TLS/QUIC, thời gian/kích thước | URL path hoặc body được TLS bảo vệ; danh tính ứng dụng đã xác thực |
| Firewall/IPS mạng | Flow, trạng thái phiên, policy hit, địa chỉ trước/sau NAT tùy cấu hình | Payload HTTPS/IPsec khi không có bước giải mã thích hợp |
| Reverse proxy/CDN/WAF kết thúc TLS | HTTP method, path, status, header, rule WAF, request ID tùy logging | Nội dung của một tunnel mã hóa độc lập phía sau mà proxy không kết thúc |
| Endpoint/EDR | Tiến trình, kết nối, hành vi file, hoạt động hệ điều hành | Mọi nội dung của thiết bị khác; nhiều chi tiết phụ thuộc OS/agent |
| DNS resolver được quản lý | Tên được truy vấn qua resolver đó, kết quả, client hoặc danh tính theo cấu hình | Truy vấn dùng resolver khác hoặc kênh mã hóa không đi qua resolver |
| Workload/service mesh | Danh tính service, mTLS policy, kết nối service-to-service, trace | Toàn bộ payload của các phiên không đi qua proxy/agent tương ứng |
| Cloud flow logs | IP, cổng, chiều, trạng thái flow và thống kê tùy nền tảng | Payload ứng dụng, các byte TLS hoặc mọi gói một cách đầy đủ |

Một **NIDS đặt ở Internet edge** có thể không thấy traffic **east–west** giữa hai máy cùng VLAN, pod trong cluster hoặc workload trong cùng mạng ảo. Ngược lại, một sensor đặt ở subnet ứng dụng có thể thấy traffic nội bộ nhưng không biết địa chỉ client gốc nếu có NAT/proxy phía trước. Cần mô hình hóa **đường đi thật**, không chỉ sơ đồ mong muốn.

## 4. TLS 1.2 và TLS 1.3: handshake có thay đổi visibility

### 4.1. TLS bảo vệ phần nào?

**Transport Layer Security (TLS)** bảo vệ dữ liệu ứng dụng trong phiên bằng các khóa được thương lượng khi bắt tay. TLS không mã hóa toàn bộ header IP và TCP/UDP của gói trên mạng thông thường; các thành phần trung gian vẫn cần các trường đó để định tuyến.

Ví dụ kết nối HTTP/2 qua TLS/TCP:

~~~text
Ethernet / IP / TCP
        |
        +-- Thông tin để định tuyến và vận chuyển
        |
        +-- TLS records
              |
              +-- Handshake: một số trường hiển thị tùy phiên bản
              |
              +-- Application data: HTTP được bảo vệ bằng TLS
~~~

Không nên nói mọi handshake TLS đều hoàn toàn trong suốt hoặc hoàn toàn ẩn. **Phiên bản, kiểu kết nối, cơ chế ECH và trạng thái resume** quyết định dữ liệu nào còn quan sát được.

### 4.2. So sánh TLS 1.2 và TLS 1.3

| Thành phần | TLS 1.2 thông thường | TLS 1.3 thông thường |
|---|---|---|
| IP và TCP/UDP header ngoài TLS | Quan sát được tại điểm bắt gói | Quan sát được |
| ClientHello ban đầu | Thường có thể đọc ở dạng không mã hóa | Thường có thể đọc ở dạng không mã hóa, trừ phần bị ECH bảo vệ |
| SNI trong ClientHello | Thường thấy nếu client gửi SNI dạng rõ | Có thể thấy nếu dùng SNI rõ; **ECH có thể ẩn tên thật** |
| ALPN phía client | Có thể thấy trong ClientHello nếu được gửi | Có thể thấy ở ClientHello ngoài, nhưng ECH có thể che giá trị thực |
| Server certificate | Thường quan sát được ở bắt tay đầy đủ không có cơ chế đặc biệt | **Được mã hóa** trong phần bắt tay sau ServerHello, sensor thụ động không tự đọc được |
| HTTP path/body và dữ liệu ứng dụng | Được mã hóa | Được mã hóa |
| Thông tin phiên đã nối lại | Có thể khác handshake đầy đủ | Có thể hạn chế dữ liệu quan sát; cần xét resumption/PSK |

**Nhận định quan trọng:** Với **TLS 1.3**, chỉ có bản sao gói và private key của chứng chỉ máy chủ **không đủ** để giải mã lưu lượng dùng key exchange hiện đại. Đọc payload cần quyền truy cập hợp lệ tới khóa phiên hoặc dữ liệu đã giải mã tại một điểm kiểm soát. Không được giả định các kỹ thuật giải mã passive TLS 1.2 kiểu cũ còn áp dụng cho mọi phiên.

### 4.3. SNI là gì và vì sao không đáng tin như một định danh tuyệt đối?

**Server Name Indication (SNI)** là extension giúp client thông báo tên server dự kiến trong quá trình thiết lập TLS. Khi SNI được gửi dưới dạng rõ, NIDS có thể dùng làm **tín hiệu** phân loại kết nối. Nhưng:

- Client có thể không gửi SNI hoặc sử dụng cấu hình khác.
- Một IP có thể phục vụ nhiều hostname qua CDN/reverse proxy.
- SNI do client cung cấp, không phải chứng cứ xác thực độc lập về đích cuối.
- **Encrypted ClientHello (ECH)** có thể che tên máy chủ thật và nhiều phần ClientHello; trường quan sát bên ngoài không nhất thiết là tên dịch vụ cuối cùng.
- Dữ liệu bắt tay có thể không đầy đủ tại sensor do mất gói, resume hoặc điểm bắt đầu capture.

Do đó, **SNI hiển thị không đồng nghĩa với nội dung HTTP**, và thiếu SNI không đồng nghĩa kết nối xấu.

## 5. QUIC/HTTP/3 thay đổi dữ liệu có thể nhìn thấy

**QUIC** thường chạy trên **UDP**, và **HTTP/3** sử dụng QUIC thay vì TCP. QUIC tích hợp bảo vệ mật mã vào giao thức vận chuyển và sử dụng bắt tay dựa trên TLS 1.3. Một thiết bị chỉ theo dõi TCP/443 sẽ **không quan sát đầy đủ** HTTP/3 qua UDP/443.

~~~text
HTTPS qua TCP:
  IP -> TCP/443 -> TLS -> HTTP/1.1 hoặc HTTP/2

HTTPS qua QUIC:
  IP -> UDP/443 -> QUIC (TLS 1.3) -> HTTP/3
~~~

Các điểm cần hiểu:

1. Header IP/UDP và một số trường QUIC vẫn có thể quan sát được. Không phải toàn bộ byte QUIC luôn có thể diễn giải giống nhau.
2. QUIC **Initial packets** có cơ chế bảo vệ mà một analyzer phù hợp có thể giải mã phần Initial trong những điều kiện nhất định, nên một số thông tin ClientHello có thể được phân tích. Điều này **không đồng nghĩa** khả năng giải mã toàn bộ dữ liệu ứng dụng QUIC.
3. Sau giai đoạn Initial, phần lớn nội dung vận chuyển và ứng dụng được bảo vệ bằng khóa phiên; sensor thụ động không tự đọc được request HTTP/3.
4. **Connection ID, connection migration, NAT rebinding** và đặc điểm UDP có thể làm cơ chế chỉ ghép theo 5-tuple thiếu ổn định; cách hoạt động phụ thuộc triển khai.
5. **ECH** và các thay đổi privacy có thể tiếp tục giảm metadata tên đích quan sát được.

Không nên kết luận rằng mọi lưu lượng UDP/443 đều là QUIC hoặc rằng chặn UDP/443 chắc chắn loại bỏ mọi rủi ro. Chặn QUIC để ép client về TCP có thể ảnh hưởng hiệu năng/chức năng, không phải phương án mặc định để tạo visibility. Nếu cần kiểm soát giao thức, phải đánh giá chính sách vận hành và khả năng ứng dụng.

## 6. DNS được mã hóa: DoH, DoT và blind spot

DNS truyền thống qua UDP/TCP 53 thường để lộ tên truy vấn tại những vị trí mạng thấy được gói DNS. **DNS over HTTPS (DoH)** và **DNS over TLS (DoT)** bảo vệ truy vấn DNS trong một kênh mã hóa; các sensor bên ngoài kênh thường không đọc được tên truy vấn trực tiếp.

| Cơ chế | Vận chuyển thường gặp | Visibility từ NIDS trên đường | Nơi có thể lấy telemetry phù hợp |
|---|---|---|---|
| DNS truyền thống | UDP/TCP 53 | Có thể thấy query/response nếu traffic không bị mã hóa và đi qua sensor | Resolver log, network DNS analyzer |
| **DoT** | TLS trên TCP 853 (thường gặp) | Thấy flow, không mặc nhiên đọc tên DNS | Resolver được tổ chức quản lý, endpoint, cấu hình client |
| **DoH** | HTTPS, thường trên 443 | Có thể giống traffic HTTPS khác; không mặc nhiên đọc câu hỏi DNS | Resolver được quản lý, client telemetry, policy browser/OS |
| DNS nội bộ qua tunnel VPN/IPsec | Đi trong đường truyền được bảo vệ | Sensor ngoài tunnel không đọc được payload DNS | Sensor sau kết thúc tunnel, resolver nội bộ và log ứng dụng |

**Không nên phân loại mọi HTTPS tới một IP nổi tiếng là DoH chỉ từ cổng 443.** IP/CDN có thể phục vụ nhiều dịch vụ, còn việc đổi địa chỉ hoặc proxy có thể làm suy luận theo IP sai lệch. Phòng vệ nên chú trọng chính sách resolver được phép, thiết bị quản lý, log DNS tại resolver và phân quyền truy cập phù hợp.

DNS visibility cũng không phải bản ghi đầy đủ mọi kết nối: ứng dụng có thể dùng IP trực tiếp, cache DNS, kết quả đã có hoặc resolver khác. **DNS log là nguồn bằng chứng bổ trợ, không phải phép chứng minh tuyệt đối về mọi hostname client đã truy cập.**

## 7. SSH, VPN, IPsec và lưu lượng được bọc trong tunnel

Khi lưu lượng nằm trong một kênh được mã hóa, khả năng quan sát phụ thuộc sensor ở **bên ngoài** hay **bên trong** điểm kết thúc tunnel.

### 7.1. IPsec và VPN

Một sensor nằm bên ngoài tunnel IPsec ESP thường thấy **outer IP header**, giao thức/tunnel metadata và đặc điểm flow, nhưng không tự đọc được **inner packet** được mã hóa. Với NAT traversal, ESP có thể được đóng gói qua UDP/4500 tùy cấu hình. Sensor ở phía **sau khi VPN gateway giải mã** có thể quan sát các gói IP bên trong nếu traffic đi qua vị trí đó.

~~~text
Chi nhánh A                     Internet                     Data center
 [Client]                                                       [App]
    |                                                            ^
 [VPN GW A] == Outer IP / IPsec ESP (encrypted) == [VPN GW B] ---|
                     |
               [Internet NIDS]
               Thường chỉ thấy outer flow

                                             [Internal NIDS]
                                             Có thể thấy inner IP flow
                                             nếu tuyến đi qua sensor
~~~

**Sau khi giải mã IPsec, payload bên trong vẫn có thể là TLS/HTTPS.** Tháo một lớp tunnel **không** đồng nghĩa đọc được mọi ứng dụng. Ngược lại, sensor trong mạng chi nhánh trước khi gói vào IPsec có thể thấy inner traffic nhưng vẫn chịu giới hạn của TLS.

### 7.2. SSH và các kênh mã hóa khác

SSH mã hóa nội dung phiên làm việc sau khi hoàn tất quá trình thương lượng, trong khi sensor có thể thấy metadata của kết nối và một số thông tin ban đầu tùy phiên bản/cấu hình. Một phiên TCP/22 không đủ chứng minh đây là truy cập quản trị được phép hoặc nội dung bên trong không nguy hiểm. Hệ thống cần thêm:

- Identity và authorization trên máy đích hoặc gateway quản trị.
- Nhật ký phiên, tài khoản, endpoint/EDR và thay đổi hệ thống.
- Kiểm soát nguồn truy cập qua firewall/NAC/VPN.
- Giám sát sai lệch hành vi và khả năng thu hồi phiên khi có sự cố.

Không nên thiết kế cơ chế phát hiện dựa vào việc đọc lệnh SSH trực tiếp từ NIDS trên đường mạng.

## 8. Phát hiện không cần giải mã: metadata, flow và hành vi

**Non-decrypting visibility** là cách dùng các tín hiệu còn quan sát được để phát hiện bất thường mà không lấy nội dung ứng dụng trong TLS. Các nhóm tín hiệu:

| Nhóm | Tín hiệu ví dụ | Cách sử dụng và giới hạn |
|---|---|---|
| **Flow/NetFlow/IPFIX** | IP, port, thời điểm, byte/packet, duration, hướng flow | Nhận diện kết nối hiếm, egress mới, traffic tăng bất thường; thiếu ngữ nghĩa ứng dụng |
| **TLS/QUIC handshake metadata** | Version, cipher suites, extensions, ALPN/SNI khi khả dụng | Phân loại client và thay đổi cấu hình; ECH/QUIC có thể che hoặc thay đổi trường |
| **TLS client fingerprint** | Những đặc trưng như JA3/JA4 hoặc fingerprint do công cụ xây dựng | Hỗ trợ tìm nhóm client; **không phải danh tính mật mã**, có thể trùng hoặc thay đổi |
| **Đặc điểm lưu lượng** | Chu kỳ kết nối, số byte lên/xuống, burst, nhiều đích trong thời gian ngắn | Hỗ trợ phát hiện beaconing hoặc exfiltration giả thuyết; dễ trùng với tác vụ hợp lệ |
| **Destination context** | ASN, danh mục IP, asset inventory, reputation được cập nhật | Giúp ưu tiên điều tra; IP CDN/shared hosting không đồng nhất một dịch vụ |
| **Firewall/NAC/VPN logs** | Rule hit, action, user/device mapping, phiên và zone | Cho biết quyền/trạng thái truy cập; không chứng minh payload an toàn |
| **EDR/endpoint telemetry** | Tiến trình tạo kết nối, parent process, file action | Gắn luồng mạng với ngữ cảnh trên máy; phụ thuộc quyền và mức thu thập của agent |
| **DNS/resolver logs** | Tên truy vấn, danh tính client, response | Có ích nếu sử dụng resolver được giám sát; không bao phủ mọi truy cập |

### 8.1. Fingerprint không phải bằng chứng kết tội

Fingerprint TLS như **JA3/JA4** được xây dựng từ những đặc điểm mà công cụ có thể đọc hoặc suy ra trong bắt tay. Nhiều trình duyệt, thư viện hoặc phần mềm hợp lệ có thể chia sẻ fingerprint; một ứng dụng có thể đổi fingerprint sau cập nhật. ECH và các kỹ thuật bảo vệ metadata cũng làm thay đổi tập dữ liệu đầu vào.

Do đó, **fingerprint trùng với mẫu từng thấy trong lưu lượng độc hại không tự chứng minh client bị nhiễm mã độc**. Cần thêm bằng chứng như tiến trình nguồn, quan hệ với tài sản, kết nối bất thường, danh tính đích và hoạt động endpoint.

### 8.2. Ví dụ cảnh báo cần điều tra

Một máy kế toán bắt đầu tạo **nhiều kết nối TLS ra Internet vào ban đêm**, với upload bytes tăng mạnh và đích chưa thấy trong baseline. Sensor mạng không đọc được nội dung TLS, nhưng có thể:

1. Xác nhận thay đổi so với baseline theo vai trò và lịch vận hành.
2. Đối chiếu địa chỉ đích, thời điểm, route, VPN/NAT và chính sách firewall.
3. Kết hợp EDR để xác định tiến trình thực hiện, chữ ký phần mềm và lịch chạy.
4. Kiểm tra log hệ thống DLP/proxy hoặc ứng dụng nếu đang có nguồn được phép quan sát.
5. Phân biệt tác vụ backup/sync hợp lệ với hành vi đáng ngờ trước khi ra quyết định xử lý.

**Không thể kết luận “rò rỉ dữ liệu” chỉ dựa trên upload bytes**. Kích thước, thời gian và IP là tín hiệu ưu tiên điều tra; cần bằng chứng bổ sung về nội dung hoặc hành vi bất thường.

## 9. Khi nào cần quan sát sau giải mã?

Một số mục tiêu phát hiện thực sự cần biết **HTTP method/path, header, nội dung API hoặc quy tắc ứng dụng**. Với các trường hợp ấy, có thể thu thập thông tin tại **điểm kết thúc mã hóa do tổ chức kiểm soát** hoặc thông qua telemetry có cấu trúc từ ứng dụng.

### 9.1. Inbound TLS termination tại reverse proxy/WAF

Ví dụ website tổ chức được công bố qua một reverse proxy do chính tổ chức vận hành:

~~~text
Internet Client
      |
      | HTTPS (TLS ngoài)
      v
[Reverse Proxy / WAF]
      | Kết thúc TLS đã được cấp quyền
      | Kiểm tra HTTP request, rule, access log
      v
      | HTTPS/mTLS mới tới backend nếu cấu hình
      v
 [Application Server]
      |
  App/trace/audit logs
~~~

Ở đây reverse proxy có thể quan sát HTTP **sau khi kết thúc TLS của chính nó**. Nếu upstream dùng kết nối TLS mới, dữ liệu từ proxy tới backend lại được mã hóa trên đường mạng. IDS bên ngoài cả hai điểm TLS chỉ thấy các đường truyền được bảo vệ, nhưng WAF/proxy và app log có thể cung cấp tín hiệu hữu ích.

**Bảo vệ cần có:** quản lý khóa riêng/chứng chỉ, ciphers và phiên bản TLS phù hợp, xác thực upstream nếu cần, kiểm soát log nhạy cảm, hạn chế truy cập quản trị và tính sẵn sàng của proxy.

### 9.2. Outbound TLS inspection tại proxy được ủy quyền

Trong một số mạng doanh nghiệp, **forward proxy** có thể giải mã HTTPS từ thiết bị được quản lý theo chính sách đã thông báo và được phép. Cơ chế này thường yêu cầu thiết bị client tin cậy chứng chỉ do hạ tầng proxy phát hành cho quá trình kết nối, và proxy thiết lập kết nối TLS riêng tới đích thực.

~~~text
Managed Client == TLS A ==> [Authorized TLS Inspection Proxy]
                                   |
                          Security inspection
                                   |
                                   +== TLS B ==> External Service
~~~

Đây là **hai phiên TLS khác nhau**, với một điểm truy cập nội dung rõ ở giữa. Vì thế cần xem xét:

- **Pháp lý, quyền riêng tư và sự minh bạch:** ai được kiểm tra, loại dữ liệu nào, mục đích, thời gian lưu, ai được truy cập.
- **Quản lý khóa/CA:** private key của CA proxy rất nhạy cảm; giới hạn quyền, lưu trữ an toàn, xoay/thu hồi theo vòng đời.
- **Xác thực chứng chỉ server thật:** proxy phải kiểm chứng phía đích, tránh biến kiểm tra TLS thành cơ chế làm yếu xác minh máy chủ.
- **Certificate pinning/mTLS:** một số ứng dụng không tương thích hoặc cần xác thực client end-to-end, không phù hợp với interception.
- **Hiệu năng và tính sẵn sàng:** tăng tải, độ trễ, giới hạn phiên và rủi ro sự cố tập trung.
- **Ngoại lệ:** dịch vụ nhạy cảm hoặc không tương thích có thể cần chính sách bypass có kiểm soát, không phải nới bừa cho mọi nguồn.

**Không được triển khai TLS interception bí mật hoặc trên thiết bị/tài khoản không được ủy quyền.** Giải mã mang lại visibility nhưng tạo trách nhiệm bảo vệ dữ liệu và khóa lớn hơn.

### 9.3. Không cần giải mã nếu có telemetry tầng ứng dụng

Một API có thể ghi **route, HTTP status, request ID, user/service identity, policy decision, error class và latency** mà không cần lưu body. Đây thường là phương án ít xâm lấn hơn full packet decryption khi mục tiêu là phát hiện lạm dụng tài khoản, lỗi phân quyền hoặc hành vi bất thường.

Tương tự, service mesh có thể cung cấp **mTLS identity**, thống kê gọi service-to-service và log proxy tại điểm xử lý. Tuy nhiên, cần phân biệt quyền xem metadata và quyền đọc nội dung; không phải mọi service mesh đều xuất toàn bộ HTTP body hoặc cung cấp thông tin cho những luồng không đi qua sidecar/gateway.

## 10. Những giới hạn và rủi ro của decryption-based inspection

| Rủi ro | Vì sao quan trọng? | Cách kiểm soát |
|---|---|---|
| **Lộ dữ liệu riêng tư** | Proxy/log có thể thấy thông tin nhạy cảm vốn được TLS bảo vệ | Data minimization, redaction, RBAC, audit và thời hạn lưu |
| **Mất an toàn khóa/chứng chỉ** | Khóa CA hoặc TLS key bị lộ có thể gây hậu quả lớn | PKI/secret management, phân quyền, xoay/thu hồi và giám sát |
| **Ứng dụng không tương thích** | Certificate pinning, mTLS, QUIC hoặc giao thức riêng có thể lỗi | Kiểm kê ứng dụng, thử nghiệm, ngoại lệ theo dịch vụ và kế hoạch fallback |
| **Hiệu năng và độ trễ** | Giải mã, inspect và mã hóa lại tốn tài nguyên | Sizing, capacity planning, đo latency/throughput |
| **Mất tính toàn vẹn đường xác thực** | Proxy có thể đóng vai endpoint TLS trung gian | Xác thực upstream chặt chẽ, vận hành proxy được tin cậy và kiểm toán |
| **Blind spot vẫn tồn tại** | Một số traffic bypass proxy hoặc có lớp mã hóa ứng dụng bổ sung | Inventory đường đi, enforce egress, kết hợp endpoint/app logs |
| **False positive/false block** | Rule kiểm tra nội dung có thể chặn dữ liệu nghiệp vụ hợp lệ | Tuning theo phạm vi, kiểm thử regression, rollback |
| **Rủi ro availability** | Proxy inspection là điểm phụ thuộc tập trung | HA, giám sát, quy trình khi proxy lỗi, chính sách fail-open/closed có đánh giá |

**TLS inspection không phải luôn giải mã được mọi thứ:** một tunnel VPN bên trong TLS, nội dung mã hóa end-to-end ở tầng ứng dụng hoặc session dùng cơ chế pinning/mTLS có thể vẫn không thể kiểm tra toàn bộ theo cách mong muốn. Phải kiểm chứng khả năng của nền tảng và chính sách quyền riêng tư thay vì tuyên bố “100% HTTPS visibility”.

## 11. Thiết kế IDS/IPS trên mạng nhiều vùng

Một mạng doanh nghiệp có thể tách:

- **Internet/DMZ:** dịch vụ công khai được kết thúc TLS tại WAF/reverse proxy.
- **Employee/VPN:** endpoint có EDR, firewall stateful và định danh user/device.
- **Application:** API nội bộ và gateway cung cấp structured logs.
- **Database:** chỉ các workload được phép kết nối; audit log ở máy chủ dữ liệu.
- **Management:** jump host, NAC/VPN với kiểm soát danh tính.
- **Cloud/Kubernetes:** flow logs, security groups, CNI policy, workload identity và telemetry được cấu hình.

~~~text
                          Internet
                             |
                      [Edge FW / IPS]
                             |
                   [WAF / TLS termination]
                             |
                       [Application]
                        /         \
                 [Service A]     [Service B]
                    |                |
                [Database]      [Logging]

        [Employee] -- VPN -- [Internal FW] -- [App]
            |
          [EDR]

 Sensors:
   Edge:     flow + handshake metadata
   Proxy:    HTTP/response metadata, WAF decision
   Host:     process + session identity
   Internal: east-west flow nếu điểm đặt quan sát được
   Cloud:    workload/flow log theo nền tảng
~~~

### Nguyên tắc đặt sensor

1. **Vẽ luồng thật:** Internet → DMZ, VPN → app, app → DB, pod ↔ pod, các đường dự phòng và đường admin.
2. **Đánh dấu điểm mã hóa/giải mã:** TLS, mTLS, IPsec, QUIC và có proxy nào chấm dứt phiên hay không.
3. **Nêu rõ yêu cầu phát hiện:** cần nội dung HTTP, hành vi process, DNS tên miền hay chỉ flow anomaly?
4. **Chọn điểm thu thập:** đặt NIDS nơi có packet, IPS nơi thực thi chính sách, app/EDR logs tại điểm có ngữ cảnh.
5. **Kiểm soát khả năng bao phủ:** xác định những đường traffic không đi qua sensor, đặc biệt east–west trong cloud và container.
6. **Thiết kế quyền truy cập telemetry:** giữ log có ích cho điều tra nhưng tránh lưu bí mật không cần thiết.
7. **Kiểm thử bằng luồng được ủy quyền:** xác minh đúng dữ liệu được nhìn thấy và đúng alert/decision phát ra.

**Đặt IPS inline không đồng nghĩa nó nhìn thấy mọi đường đi.** Nếu một subnet định tuyến trực tiếp qua switch L3 hoặc service mesh không đi qua IPS, việc đặt thiết bị ở Internet edge không kiểm soát được luồng đó.

## 12. Detection engineering với dữ liệu không có plaintext

Ví dụ mục tiêu: phát hiện endpoint bất thường liên hệ đích lạ qua TLS hoặc QUIC. Có thể xây dựng phát hiện theo nhiều nguồn:

| Tín hiệu | Điều kiện ví dụ | Cảnh báo về diễn giải |
|---|---|---|
| Flow bất thường | Kết nối tới nhiều đích mới trong khung giờ không bình thường của host | Backup, update, CDN hoặc thay đổi ứng dụng có thể hợp lệ |
| Egress bytes tăng | Tổng byte outbound cao so với baseline của cùng role | Không tự chứng minh exfiltration hoặc nội dung gì bị gửi |
| DNS/resolver | Host truy vấn domain chưa từng thấy, sau đó có kết nối liên quan | DNS cache, DoH hoặc shared IP làm tương quan không tuyệt đối |
| Endpoint process | Tiến trình chưa được phê duyệt tạo kết nối ra ngoài | Tiến trình hợp lệ được cập nhật có thể thay đổi tên hoặc hành vi |
| TLS/QUIC metadata | Mẫu handshake thay đổi, tần suất phiên tăng hoặc fingerprint hiếm | Fingerprint không phải danh tính; QUIC/ECH làm giảm chi tiết |
| Firewall policy | Kết nối ra ngoài trái ma trận truy cập | Cần phân biệt cấu hình sai, rule ngoại lệ và đường bypass |

Một rule tốt có **điều kiện giới hạn phạm vi, ngưỡng dựa trên baseline, nguồn dữ liệu được xác định, cách triage và tiêu chí điều chỉnh false positive**. Ví dụ:

~~~text
Detection hypothesis:
  Máy trong nhóm văn phòng có nhiều phiên ra đích mới
  + upload bytes tăng bất thường
  + tiến trình nguồn không thuộc danh sách được quản lý.

Evidence:
  Flow log + endpoint event + policy decision + asset owner.

Output:
  Alert để điều tra; KHÔNG kết luận tự động là rò rỉ dữ liệu.

Response:
  Analyst xác minh nghiệp vụ, thay đổi phần mềm, log ứng dụng
  rồi áp dụng biện pháp hạn chế nếu đủ bằng chứng.
~~~

**Anomaly detection không thay thế điều tra.** Khi giao thức ngày càng bảo vệ metadata, khả năng kết luận chỉ từ network fingerprint càng hạn chế; ưu tiên gắn telemetry với danh tính thiết bị, ứng dụng và chủ sở hữu.

## 13. Ví dụ thực hành trong lab được ủy quyền

Bài thực hành này giúp quan sát khác biệt giữa **gói TLS trên đường mạng** và **log ở điểm kết thúc**, không yêu cầu giải mã traffic của người khác.

### Bước 1. Chuẩn bị

Sử dụng máy và dịch vụ **do người học sở hữu hoặc được phép thử nghiệm**, có HTTPS hoặc HTTP/3 nếu phù hợp. Biết rõ địa chỉ/interface, thời điểm và quy trình lưu/xóa PCAP. Khi có thể, sử dụng dữ liệu thử nghiệm không chứa token hoặc nội dung nhạy cảm.

Chỉ chạy các lệnh quan sát được phép trong lab. Nếu không có quyền packet capture, có thể dùng **PCAP mẫu do đội giảng dạy cung cấp hợp pháp**, hoặc dùng log kết nối/ứng dụng để so sánh.

### Bước 2. Quan sát socket và route trên endpoint

**Linux:**

~~~bash
ip -br addr
ip route
ss -nt
~~~

**Windows:**

~~~text
ipconfig /all
route print
netstat -ano
~~~

Những lệnh trên đọc thông tin mạng/sockets, không tự hiển thị nội dung HTTPS. Cần đối chiếu kết quả với danh tính tiến trình và quyền sở hữu hệ thống khi phân tích.

### Bước 3. Dùng Wireshark để xem metadata PCAP

Với PCAP được thu thập hợp lệ, có thể dùng những **display filter**:

~~~text
tcp.port == 443
udp.port == 443
tls
quic
tls.handshake.type == 1
dns
icmp || icmpv6
~~~

Các filter này **không phải cách giải mã TLS**; kết quả phụ thuộc phiên bản Wireshark, protocol dissector, dữ liệu PCAP và giao thức thực. Một gói UDP/443 chưa chắc là QUIC; một phiên TLS không nhất thiết cung cấp ClientHello trong capture nếu sensor bắt giữa phiên.

Quan sát và ghi lại:

1. IP/port nguồn và đích, TCP hay UDP, số gói và lượng byte.
2. Có nhìn thấy ClientHello hoặc handshake tương ứng không?
3. SNI/ALPN có hiện ra không, hay bị thiếu/ẩn theo giao thức và ECH?
4. HTTP path/body có đọc được không, và vì sao?
5. Có log tương ứng từ reverse proxy hoặc ứng dụng được quản lý không?

### Bước 4. Đối chiếu với log ứng dụng hoặc proxy

~~~text
Traffic ID:          LAB-ENC-01
Source / destination:[địa chỉ và cổng được phép]
Sensor location:     [edge / inside VPN / proxy / endpoint]
Transport:           [TCP/TLS / UDP/QUIC / VPN tunnel]
Visible metadata:    [IP, port, time, bytes, handshake fields...]
Hidden data:         [HTTP path/body hoặc inner tunnel nếu mã hóa]
Proxy/app request ID:[nếu có]
App observation:     [HTTP route/status, nghiệp vụ được xác minh]
Correlation:         [time, flow, request ID]
Conclusion:          [điều quan sát được, điều chưa thể kết luận]
~~~

Không cần thu mật khẩu, token, private key hoặc plaintext nhạy cảm để hoàn thành bài. **Bài tập về visibility không phải lời khuyến khích phá mã hóa**.

### Bước 5. Kiểm tra giả thuyết

Ví dụ, nếu PCAP cho thấy **TCP/443 và TLS ClientHello** nhưng không có HTTP path, còn reverse proxy log ghi **GET /health** cùng khung thời gian, có thể kết luận:

- Sensor trên đường mạng đã quan sát **một phiên TLS**, không chứng minh được path từ nội dung gói mã hóa.
- Proxy kết thúc TLS và ghi nhận **GET /health** cho request tương ứng.
- Muốn liên kết chính xác hai bản ghi cần **request ID, flow/connection ID hoặc dữ liệu tương quan phù hợp**, không chỉ dựa vào IP và thời gian gần nhau nếu có nhiều phiên đồng thời.

## 14. Case study: nghi ngờ kết nối mã hóa ra ngoài từ máy chủ ứng dụng

**Bối cảnh giả định:** NDR trong data center phát hiện một máy chủ API gửi nhiều dữ liệu TLS ra một địa chỉ chưa từng xuất hiện trong baseline. Firewall cho phép TCP/443 theo một ngoại lệ cũ. Sensor mạng không đọc được payload.

~~~text
Time window:      02:10 - 02:25 (lab timeline)
Source:           application-server-07
Destination:      external-service (IP chưa được xác minh owner)
Transport:        TCP/443, TLS
Observation:      outbound bytes tăng, đích chưa thấy trong baseline
NDR status:       ANOMALOUS, chưa xác nhận tấn công
Firewall action:  ALLOW
TLS payload:      Không thể đọc tại sensor hiện có
~~~

### Các giả thuyết cần kiểm tra

1. **Luồng được phê duyệt:** máy chủ đang backup, sync log hoặc gọi API đối tác theo lịch mới.
2. **Thay đổi phần mềm:** bản cập nhật hoặc tính năng mới tạo kết nối chưa được cập nhật inventory.
3. **Sai chính sách egress:** rule TCP/443 quá rộng, cho phép liên lạc ngoài ma trận truy cập.
4. **Endpoint bị xâm nhập:** tiến trình bất thường dùng HTTPS để liên lạc hoặc chuyển dữ liệu.
5. **Sai điểm nhìn:** NAT/proxy khiến địa chỉ nguồn hoặc đích bị hiểu nhầm.

### Quy trình phân tích an toàn

1. Đối chiếu **asset owner, lịch backup, deployment, change ticket và inventory**.
2. Xem flow log, firewall rule/zone, địa chỉ trước/sau NAT, thời gian và mức byte tăng.
3. Kết hợp EDR hoặc host audit để tìm **tiến trình nguồn, tài khoản thực thi, binary/signature và lịch tác vụ**.
4. Đối chiếu resolver/DNS logs nếu được phép, nhưng không coi thiếu DNS là bằng chứng độc hại.
5. Dùng application/proxy logs có cấu trúc, nếu luồng đi qua điểm do tổ chức kiểm soát.
6. Nếu đủ bằng chứng rủi ro, áp dụng quy trình ứng cứu: giới hạn egress theo quyền, bảo toàn log, xem xét endpoint và thay đổi chính sách có rollback.
7. Cập nhật detection để nhận diện kiểu hành vi tương tự nhưng giảm false positive cho backup/sync hợp lệ.

**Kết luận phù hợp tại thời điểm chỉ có NDR alert:** “Kết nối mã hóa bất thường cần điều tra” chứ chưa phải “đã xác nhận exfiltration”. Không nên tuyên bố đã biết dữ liệu gì bị gửi khi payload không quan sát được.

## 15. Chỉ số đánh giá coverage và chất lượng cảnh báo

| Chỉ số | Cách đo | Điểm cần tránh |
|---|---|---|
| **Flow visibility coverage** | Tỷ lệ luồng mục tiêu có telemetry từ điểm đo dự kiến | Không lấy tỷ lệ này làm tỷ lệ payload giải mã |
| **TLS/QUIC classification coverage** | Số luồng được phân loại protocol/handshake đủ chất lượng | Không suy mọi UDP/443 đều QUIC |
| **Endpoint/asset correlation rate** | Tỷ lệ sự kiện mạng ghép được với thiết bị hoặc workload owner | NAT, IP động và cloud scaling có thể gây sai mapping |
| **Detection precision trên tập có nhãn** | TP / (TP + FP) | Nhãn từ rule tự động không phải ground truth độc lập |
| **False positive rate trên tập có nhãn** | FP / (FP + TN) | Khó có TN chính xác trong toàn bộ production |
| **Mean time to triage** | Thời gian từ alert đến kết quả phân loại có căn cứ | Phải tính cả khả năng thiếu dữ liệu và chuyển nhóm phụ trách |
| **Inspection latency / error rate** | Độ trễ và lỗi do proxy/IPS gây ra | Có visibility nhưng phá ứng dụng là thiết kế kém |
| **Sensitive data collection** | Số nguồn log/field nhạy cảm và thời hạn lưu | Thu càng nhiều không có nghĩa càng an toàn |

Đặt mục tiêu coverage theo **bề mặt cần bảo vệ**: hệ thống trọng yếu, luồng có rủi ro cao, truy cập quản trị, kết nối egress và trao đổi east–west quan trọng. Không có nghĩa phải giữ toàn bộ PCAP hoặc giải mã mọi request.

### Ma trận xác minh visibility

| Luồng | Sensor | Kỳ vọng quan sát | Kiểm thử |
|---|---|---|---|
| Laptop → HTTPS API | NIDS giữa client và edge | Flow/TLS metadata; không mặc nhiên thấy body | So PCAP với log WAF |
| Internet → Web qua reverse proxy | WAF/proxy | HTTP method/path/status khi TLS kết thúc tại proxy | Dùng request test và request ID |
| Branch → data center qua IPsec | NIDS ngoài tunnel | Outer flow, không thấy inner IP payload | So với sensor sau VPN termination |
| Workload A → B qua mTLS | Sensor east–west | Flow/TLS; không mặc nhiên đọc body | So với service mesh/app telemetry |
| Client → DNS qua DoH | NIDS ngoài TLS | HTTPS flow, không mặc nhiên thấy DNS query | Đối chiếu log resolver quản lý nếu có |
| HTTP/3 qua QUIC | QUIC-capable sensor | UDP flow và phần handshake tùy điều kiện | Kiểm tra dissector và đối chiếu access log |

## 16. Sai lầm phổ biến

| Nhận định sai | Vấn đề | Cách hiểu đúng |
|---|---|---|
| “IDS/IPS đặt inline thì đọc được HTTPS” | Inline không tự giải mã TLS | Cần điểm giải mã có quyền hoặc telemetry ứng dụng |
| “TLS 1.3 lộ đầy đủ chứng chỉ trong PCAP” | Chứng chỉ server của handshake TLS 1.3 được mã hóa | Dựa vào nguồn được phép khác, không suy từ TLS 1.2 |
| “Có private key chứng chỉ là luôn giải mã được TLS 1.3” | Không đúng với cơ chế trao đổi khóa TLS 1.3 hiện đại | Không giả định giải mã thụ động được |
| “Không có SNI thì chắc là mã độc” | ECH, loại client, handshake thiếu hoặc chính sách privacy đều có thể gây thiếu | Kết hợp nhiều tín hiệu có ngữ cảnh |
| “UDP/443 luôn là QUIC” | Có thể có traffic khác; parser có giới hạn | Dùng xác nhận protocol/handshake khi có thể |
| “TLS fingerprint là định danh ứng dụng duy nhất” | Nhiều client trùng fingerprint, phiên bản thay đổi | Chỉ dùng làm tín hiệu hỗ trợ |
| “VPN đã kết thúc thì có thể đọc mọi payload” | Inner traffic vẫn có thể dùng TLS/mTLS | Xác định từng lớp mã hóa |
| “DoH khiến mọi DNS hoàn toàn vô hình” | Resolver được quản lý vẫn có thể ghi truy vấn của mình | Dùng resolver/endpoint telemetry trong phạm vi quyền |
| “Mã hóa tức không thể phát hiện bất thường” | Flow, endpoint, application logs vẫn hữu ích | Thiết kế correlation và phát hiện dựa ngữ cảnh |
| “Giải mã mọi traffic là cách an toàn nhất” | Tăng rủi ro privacy/khóa/availability và không đảm bảo bao phủ | Ưu tiên mục tiêu phát hiện và dữ liệu tối thiểu |
| “Không thấy gói tại NIDS tức là không có traffic” | Sensor có thể không nằm trên đường đi hoặc bỏ gói | Xác minh route, TAP/SPAN, drop counters |
| “Alert lưu lượng tăng chứng minh exfiltration” | Backup/sync hợp lệ có thể giống bất thường | Điều tra tiến trình và nghiệp vụ |

## 17. Câu hỏi tự kiểm tra

1. NIDS nằm trên đường Internet có thể thấy những trường nào của một phiên HTTPS/TLS 1.3 thông thường? Những thông tin nào không tự đọc được?
2. Vì sao chứng chỉ server trong TLS 1.3 không có tính hiển thị giống nhiều phiên TLS 1.2?
3. **ECH** làm thay đổi khả năng dùng SNI để phân loại domain như thế nào?
4. QUIC khác TCP+TLS trong vận chuyển HTTP/3 ra sao, và vì sao chỉ giám sát TCP/443 là thiếu?
5. Một sensor bên ngoài IPsec tunnel và một sensor phía sau VPN gateway có thể nhìn thấy gì khác nhau?
6. Vì sao đọc được inner IP packet sau VPN termination vẫn chưa chắc đọc được HTTP body?
7. Cách nào giúp điều tra DNS khi client sử dụng DoH nhưng tổ chức có resolver được quản lý?
8. TLS fingerprint có nên được dùng làm bằng chứng duy nhất để cô lập máy không? Vì sao?
9. Trong trường hợp nào reverse proxy access log hữu ích hơn việc cố giải mã toàn bộ PCAP?
10. Những nguy cơ privacy, chứng chỉ và availability nào cần đánh giá khi cân nhắc forward proxy TLS inspection?
11. Một alert outbound bytes tăng cao cần thêm dữ liệu gì để phân biệt backup hợp lệ với rủi ro bị xâm nhập?
12. Làm cách nào chứng minh một network IDS thực sự thấy lưu lượng east–west mà đội bảo mật quan tâm?

## 18. Ghi nhớ trọng tâm

**Encrypted traffic visibility** không đồng nghĩa với giải mã toàn bộ traffic. Khi HTTPS/TLS, QUIC, mTLS hoặc VPN bảo vệ payload, **IDS/IPS trên đường truyền thường vẫn thấy flow, một số thông tin mạng và một phần bắt tay**, nhưng không tự đọc được nội dung ứng dụng. **TLS 1.3, ECH, DoH/DoT và QUIC** làm thay đổi những trường có thể quan sát; khả năng hiển thị phải được xác định theo phiên bản giao thức và điểm đặt sensor, không phỏng đoán.

Một kiến trúc phòng vệ hiệu quả kết hợp **flow/handshake metadata, firewall/NAC/VPN logs, DNS resolver telemetry, endpoint/EDR, WAF/reverse proxy và application logs**. Chỉ thu thập plaintext sau giải mã khi có **điểm kết thúc được ủy quyền, mục tiêu rõ ràng, quản trị khóa, giới hạn dữ liệu và bảo vệ quyền riêng tư**. Chất lượng phát hiện cần được xác minh qua **ma trận coverage, kiểm thử lab, khả năng tương quan, false positive và bằng chứng điều tra**, đồng thời luôn phân biệt giữa **điều đã quan sát**, **giả thuyết** và **kết luận được chứng minh**.

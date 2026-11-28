# SYN flood

**SYN flood** là một dạng tấn công từ chối dịch vụ nhắm vào quá trình **thiết lập kết nối TCP**. Đối tượng tấn công gửi hoặc khiến hệ thống nhận một lượng lớn yêu cầu bắt đầu kết nối (**TCP SYN**) nhưng nhiều yêu cầu không hoàn tất quá trình bắt tay. Tùy cấu hình và điểm bị nhắm tới, điều này có thể làm đầy hàng đợi kết nối chưa hoàn tất, tiêu hao trạng thái mà firewall/load balancer phải lưu, làm tăng tải xử lý hoặc gây nghẽn đường truyền. Hậu quả là người dùng hợp lệ khó thiết lập phiên mới, dù ứng dụng phía sau chưa chắc đã hết CPU hay bộ nhớ.

**DDoS** (*Distributed Denial of Service*) là tấn công từ chối dịch vụ có nguồn phát phân tán. SYN flood có thể được thực hiện từ một nguồn hoặc nhiều nguồn; chỉ khi có tính phân tán mới nên gọi cụ thể là **DDoS SYN flood**. Trong module **SECURITY_NETWORK_SECURITY**, hiểu cơ chế và biện pháp giảm thiểu SYN flood giúp thiết kế firewall, phân đoạn mạng, IDS/IPS, VPN, bảo vệ DNS, mạng không dây, cloud, giám sát lưu lượng và kiến trúc mạng có khả năng chịu sự cố.

> Trọng tâm của bài là **phát hiện, giảm thiểu và vận hành phòng vệ**. Các ví dụ sử dụng số liệu và nhật ký giả lập; không hướng dẫn tạo lưu lượng flood đối với hệ thống thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả chính xác TCP three-way handshake và vị trí phát sinh các kết nối ở trạng thái chưa hoàn tất.
2. Giải thích tại sao SYN flood có thể ảnh hưởng tới backlog, tài nguyên kết nối và khả năng phục vụ người dùng.
3. Phân biệt SYN flood với tăng tải hợp lệ, quét dịch vụ, lỗi mạng và các kiểu DDoS khác.
4. Nhận diện tín hiệu qua TCP flags, tỷ lệ SYN/ACK, queue, retransmission, firewall/IPS và log hệ thống.
5. So sánh SYN cookies, SYN proxy, rate limiting, lọc nguồn, bảo vệ upstream và tuning máy chủ.
6. Thiết kế phòng vệ nhiều lớp có xem xét tải mạng, tải thiết bị và tính sẵn sàng.
7. Lập quy trình phản ứng sự cố và kế hoạch kiểm thử không làm gián đoạn sản xuất.

## 2. TCP three-way handshake: nền tảng cần nắm

TCP là giao thức hướng kết nối. Trước khi trao đổi dữ liệu ứng dụng thông thường, hai đầu cần thiết lập phiên bằng **ba bước**:

1. **SYN:** client gửi yêu cầu bắt đầu kết nối đến server, kèm thông số khởi tạo của TCP.
2. **SYN-ACK:** server trả lời xác nhận SYN và đề xuất thông số kết nối phía server.
3. **ACK:** client xác nhận phản hồi của server; sau đó kết nối có thể chuyển sang trạng thái đã thiết lập.

~~~mermaid
sequenceDiagram
    participant C as Client hợp lệ
    participant S as TCP Server
    C->>S: SYN
    Note over S: Xử lý yêu cầu mở kết nối
    S-->>C: SYN-ACK
    C->>S: ACK
    Note over C,S: Kết nối được thiết lập
    C->>S: Dữ liệu ứng dụng
~~~

Trong nhiều TCP stack, server tạm theo dõi yêu cầu chưa hoàn tất để chờ ACK cuối. Trên Linux, có thể quan sát một số kết nối ở trạng thái **SYN-RECV** khi hệ thống đang đợi hoàn tất bắt tay. Tuy nhiên, các tối ưu như SYN cookies hoặc SYN proxy có thể thay đổi lượng trạng thái cần lưu, vì vậy **không thể suy số kết nối đang bị tấn công chỉ từ một loại trạng thái**.

### 2.1. Hai hàng đợi không nên đánh đồng

Ở nhiều triển khai TCP server, có thể phân biệt:

- **Hàng đợi yêu cầu chưa hoàn tất** (*SYN backlog*, request queue): giữ thông tin cho các kết nối chưa hoàn thành handshake, theo cách thức của TCP stack.
- **Hàng đợi kết nối đã hoàn tất chờ ứng dụng nhận** (*accept queue*): giữ các kết nối đã hoàn tất bắt tay nhưng ứng dụng chưa nhận qua cơ chế accept.

SYN flood điển hình tạo áp lực lên giai đoạn **chưa hoàn tất**, nhưng quá tải ở accept queue, tải CPU, giới hạn file descriptor, bảng trạng thái firewall, load balancer hay băng thông cũng có thể làm kết nối thất bại. Không nên nói mọi trường hợp “SYN nhiều” đều chỉ do SYN backlog đầy.

### 2.2. Thông số và cờ TCP

| Thành phần | Vai trò |
| --- | --- |
| SYN | Yêu cầu đồng bộ số thứ tự và khởi tạo kết nối |
| SYN-ACK | Phản hồi khởi tạo từ server |
| ACK | Xác nhận một phần của trao đổi TCP; ACK cuối hoàn tất handshake trong trường hợp chuẩn |
| SYN-RECV | Trạng thái liên quan yêu cầu đến đang chờ hoàn tất trên nhiều hệ thống |
| ESTABLISHED | Trạng thái kết nối TCP đã được thiết lập |
| Retransmission | Việc gửi lại khi chưa nhận xác nhận phù hợp; có thể tăng khi mạng mất gói hoặc server quá tải |
| Connection tracking | Bảng trạng thái luồng tại firewall/NAT, có thể bị tiêu thụ tài nguyên riêng với TCP server |

**TCP SYN** không phải HTTP request và cũng không phải đăng nhập vào ứng dụng. Một kết nối TCP chưa hoàn tất thường chưa đến bước xử lý nội dung HTTP. Vì vậy WAF L7 chỉ quan sát HTTP request có thể **không phải lớp bảo vệ chính** trước một SYN flood thuần túy ở lớp TCP.

## 3. SYN flood gây quá tải như thế nào?

Một server hoặc thành phần trung gian có ngân sách tài nguyên hữu hạn để xử lý yêu cầu TCP. Nếu nhiều SYN được nhận mà một tỷ lệ lớn không hoàn tất handshake, các bản ghi trạng thái, bộ đếm thời gian, lần truyền lại SYN-ACK hoặc cơ chế bảo vệ tại điểm vào có thể chịu áp lực. Khi tài nguyên cần thiết bị thiếu, **kết nối mới của người dùng hợp lệ có thể chậm, timeout hoặc bị từ chối**.

~~~mermaid
flowchart TD
    A["Lượng lớn yêu cầu TCP SYN"] --> B["Server / firewall / LB xử lý kết nối mới"]
    B --> C{"Có nhiều phiên không hoàn tất?"}
    C -->|Có| D["Áp lực lên queue, trạng thái, CPU hoặc link"]
    C -->|Không| E["Kết nối hợp lệ được thiết lập bình thường"]
    D --> F["SYN-ACK retransmission / timeout / drop tăng"]
    F --> G["Người dùng hợp lệ khó thiết lập TCP"]
    D --> H["Bật/điều chỉnh phòng vệ tại edge, upstream hoặc server"]
    H --> I["Theo dõi thành công và tác động phụ"]
~~~

Không phải mọi SYN đều gây tốn cùng lượng tài nguyên. Các implementation có thể quản lý trạng thái, hạn ngạch và timeout khác nhau; cơ chế **SYN cookies** được thiết kế để giảm phụ thuộc vào lưu trạng thái cho những kết nối chưa được xác nhận. Mức độ ảnh hưởng còn phụ thuộc băng thông đầu vào, hiệu năng thiết bị trung gian và tải ứng dụng.

### 3.1. SYN flood phân tán và nguồn IP

Trong các cuộc tấn công DDoS, lưu lượng có thể đến từ nhiều nguồn. Một số tình huống sử dụng địa chỉ nguồn bị giả mạo (*source IP spoofing*); ở trường hợp khác, nhiều thiết bị thực tạo kết nối tới đích. Vì vậy:

- Một địa chỉ nguồn đơn lẻ **không phải căn cứ đủ** để xác định người thực hiện.
- Chặn từng IP có thể kém hiệu quả khi lưu lượng đến từ nhiều IP hoặc qua mạng dùng chung.
- Giới hạn theo IP có thể chặn nhầm nhiều người dùng hợp lệ sau cùng một NAT hoặc proxy.
- Việc xác nhận được đường nhận phản hồi SYN-ACK giúp phân biệt một số yêu cầu giả mạo, nhưng không chứng minh ý định của client là hợp lệ.

### 3.2. Những điểm có thể trở thành nút nghẽn

| Điểm trên đường mạng | Tài nguyên có thể chịu áp lực | Dấu hiệu quan sát |
| --- | --- | --- |
| Đường Internet vào | Băng thông, tốc độ gói trên interface | Link utilization, packet drops tăng |
| Router/firewall | CPU/ASIC, session table, conntrack, queue | New flows/sec, state usage, drop counters |
| Load balancer / TCP proxy | Số kết nối mới, trạng thái, CPU và bộ nhớ | Frontend TCP errors, latency, queue |
| TCP server | SYN backlog, xử lý handshake, retransmission | SYN-RECV, syncookies, ListenDrops/overflows khi có |
| Ứng dụng | Accept queue hoặc khả năng xử lý kết nối đã hoàn tất | TCP established nhưng ứng dụng timeout/chậm |

**Đường vào nghẽn trước khi gói đến firewall nội bộ** thì tăng cấu hình máy chủ có thể không giải quyết được. Đây là lý do kiến trúc chống DDoS cần xem cả upstream provider và khả năng bảo vệ trước điểm nghẽn.

## 4. Phân biệt SYN flood với các sự cố tương tự

SYN flood thuộc nhóm tấn công **lớp giao vận/trạng thái kết nối**. Nó khác với:

| Hiện tượng | Bản chất | Điểm khác với SYN flood |
| --- | --- | --- |
| HTTP request flood | Lượng lớn yêu cầu ứng dụng đã đủ điều kiện đến HTTP endpoint | Nhắm vào năng lực xử lý L7, không chỉ handshake TCP |
| UDP flood | Lượng lớn datagram UDP | UDP không có TCP three-way handshake |
| Tấn công làm nghẽn băng thông | Đẩy lưu lượng làm đầy link | Có thể thuộc nhiều giao thức; SYN flood đôi khi gây nghẽn link nhưng không bắt buộc |
| Quét cổng | Khảo sát nhiều đích/cổng để xác định dịch vụ | Có thể phát sinh SYN nhưng pattern/mục tiêu và bối cảnh khác |
| Tăng truy cập hợp lệ | Nhiều client thật truy cập sau chiến dịch, giờ cao điểm | Phần lớn client có thể hoàn tất handshake và yêu cầu nghiệp vụ |
| Lỗi đường truyền | Mất gói, định tuyến bất đối xứng, firewall cấu hình sai | SYN-ACK hoặc ACK có thể thất lạc mà không có tác nhân cố ý |
| Server/LB quá tải vì ứng dụng | Luồng TCP đã thiết lập nhưng request được xử lý chậm | Nguyên nhân chính có thể nằm ở DB, thread pool hoặc logic nghiệp vụ |

**Một đồ thị SYN tăng không tự chứng minh tấn công**. SOC phải xem thêm tỷ lệ handshake hoàn tất, số máy nguồn, phân bố đích, tình trạng đường truyền, lịch thay đổi và dữ liệu ứng dụng.

## 5. Những tín hiệu quan sát quan trọng

Để nhận diện một đợt SYN flood hoặc áp lực handshake, có thể phối hợp:

- **SYN packets per second:** số gói SYN tới một dịch vụ trong đơn vị thời gian.
- **New connection attempts/sec:** tốc độ yêu cầu mở phiên, đo đúng tại điểm ingress.
- **Handshake completion ratio:** tỷ lệ kết nối hoàn tất ba bước trong một khoảng đo, với cách tính nhất quán.
- **SYN-ACK retransmissions:** số lần server hoặc thiết bị trung gian phải gửi lại phản hồi.
- **SYN backlog / request queue:** mức sử dụng hoặc số sự kiện tràn hàng đợi, nếu được stack hỗ trợ đo.
- **TCP listen drops/overflows:** sự kiện liên quan quá tải ở đường nhận kết nối, cần diễn giải theo hệ điều hành.
- **Firewall connection tracking:** mức sử dụng state table, số luồng mới, số drop và loại timeout.
- **Độ thành công của kết nối thật:** TCP connect success, TLS handshake success, HTTP availability và độ trễ từ bên ngoài.
- **Tải hạ tầng:** CPU, bộ nhớ, pps, bps, lưu lượng bị bỏ gói trên NIC, router, LB và provider.

### 5.1. Lưu ý về tỷ lệ SYN/ACK

Tỷ lệ SYN nhiều hơn ACK có thể là dấu hiệu hữu ích nhưng không tự quyết định có tấn công. TCP có retransmission, gói ACK có thể đi qua một đường khác, cảm biến có thể bỏ mất bản sao gói hoặc chỉ quan sát một chiều. Nếu hệ thống sử dụng SYN cookies/SYN proxy, số trạng thái tại server cũng không phản ánh trực tiếp số yêu cầu ban đầu.

**Khi phân tích phải xác định điểm nhìn**: tại phía Internet, phía sau load balancer hay ngay trên host? Một luồng đã được proxy kiểm tra sẽ có dấu hiệu khác luồng đi trực tiếp đến server.

### 5.2. Bảng chỉ báo: không kết luận từ một chỉ số

| Dấu hiệu | Giả thuyết cần xem xét | Kiểm tra bổ sung |
| --- | --- | --- |
| SYN/sec tăng đột biến, established/sec gần như không tăng | Nhiều yêu cầu chưa hoàn tất | SYN-ACK/ACK, lỗi đường truyền, tải link và LB |
| SYN-ACK retransmission tăng | Server thiếu ACK phản hồi | Packet loss, routing, timeout, lưu lượng nguồn |
| Syncookies được sử dụng thường xuyên | Hệ thống có áp lực lên cơ chế xử lý SYN hoặc chính sách kích hoạt | Counter backlog, queue, thời điểm tải, kernel settings |
| SYN-RECV tăng | Nhiều kết nối chờ hoàn tất trên stack có theo dõi trạng thái | Thời gian tồn tại, nguồn, phần trăm hoàn tất; lưu ý syncookies |
| Connection tracking gần cạn | Firewall/NAT đang giữ nhiều trạng thái | Loại state, timeout, rule và khả năng thiết bị |
| HTTP request vẫn thấp nhưng TCP connect timeout tăng | Vấn đề có thể nằm trước tầng ứng dụng | Chẩn đoán edge/L4 trước khi chỉ tối ưu WAF |
| Bps cao nhưng pps không đặc biệt cao | Link có thể nghẽn bởi gói lớn hoặc tải khác | Phân tích phân bố giao thức và utilization |

## 6. Kiến trúc phòng vệ nhiều lớp

Một mô hình bảo vệ dịch vụ TCP có thể gồm lớp upstream, edge, TCP protection và bảo vệ ứng dụng:

~~~mermaid
flowchart LR
    U["Internet / người dùng"] --> P["ISP / DDoS mitigation upstream"]
    P --> E["Edge router + firewall"]
    E --> S["SYN proxy hoặc TCP protection khi phù hợp"]
    S --> L["Load balancer"]
    L --> A["Web / API server"]
    A --> D[("Database")]
    P -. "Flow / attack telemetry" .-> M["SOC / quan sát"]
    E -. "Counters / deny logs" .-> M
    S -. "Handshake metrics" .-> M
    L -. "Availability / error logs" .-> M
    A -. "Application logs" .-> M
~~~

Không bắt buộc hệ thống nào cũng có đủ từng hộp vật lý. CDN, cloud load balancer hoặc dịch vụ DDoS managed có thể gom nhiều vai trò. **Điểm thiết kế là chọn chỗ ngăn chặn trước tài nguyên dễ bị cạn**, và bảo đảm người dùng hợp lệ vẫn kết nối được.

### 6.1. Phân vai các lớp

| Lớp | Vai trò chính | Giới hạn |
| --- | --- | --- |
| Upstream/ISP/scrubbing | Hấp thụ hoặc lọc lưu lượng trước khi vào đường truyền thuê bao | Phụ thuộc dịch vụ, vị trí, tuyến và cơ chế kích hoạt |
| Router và firewall biên | Chỉ công bố dịch vụ cần thiết, lọc nguồn và chính sách | Nếu link đã nghẽn trước thiết bị, firewall nội bộ khó xử lý |
| SYN cookies/SYN proxy | Giảm áp lực tài nguyên handshake hoặc kiểm tra khả năng hoàn tất bắt tay | Không thay thế bảo vệ băng thông hoặc quyền ứng dụng |
| Load balancer | Phân phối kết nối và điều khiển tải backend | Bản thân load balancer cũng có giới hạn tài nguyên |
| IDS/IPS | Phát hiện hoặc ngăn một số pattern phù hợp, tạo log | Cần đứng đúng tuyến, điều chỉnh để tránh báo động giả |
| WAF | Kiểm soát rủi ro HTTP sau khi kết nối đủ để xử lý L7 | Không phải biện pháp chính với SYN chưa hoàn thành |
| Server & application | Cấu hình TCP, timeout, giới hạn, hiệu năng, ứng dụng | Không xử lý được link upstream đã bị bão hòa |

## 7. Các biện pháp giảm thiểu trọng yếu

### 7.1. SYN cookies

**SYN cookies** là kỹ thuật cho phép TCP server **giảm nhu cầu lưu trạng thái cho một số kết nối chưa hoàn tất**, bằng cách mã hóa thông tin cần thiết vào giá trị được gửi trong phản hồi SYN-ACK và kiểm tra lại khi nhận ACK cuối.

Khái niệm:

1. Server nhận SYN.
2. Khi chính sách hoặc điều kiện hệ thống yêu cầu, server tạo SYN-ACK theo cơ chế cookie mà không cần lưu trạng thái chờ theo cách thông thường cho từng SYN.
3. Nếu client phản hồi ACK hợp lệ, server xác thực cookie và có thể tạo kết nối.

**Lợi ích:** hạn chế cạn tài nguyên gắn với những yêu cầu chỉ gửi SYN mà không hoàn tất. **Giới hạn:** không giảm tổng số gói đến đường truyền và vẫn cần tài nguyên xử lý; cách mã hóa thông tin, tùy chọn TCP hỗ trợ và thời điểm kích hoạt phụ thuộc hệ điều hành/implementation. Không mặc định luôn bật hoặc tăng backlog là đủ để bảo vệ mọi tình huống.

### 7.2. SYN proxy

**SYN proxy** là cơ chế đặt tại một điểm trung gian để xử lý bước bắt tay ban đầu với phía client. Chỉ khi client thể hiện được khả năng hoàn tất handshake theo chính sách, proxy mới tạo hoặc cho đi tiếp kết nối tới server phía sau.

**Lợi ích:** giảm lượng yêu cầu chưa xác nhận mà backend phải xử lý, đặc biệt khi dùng cùng lọc tại biên. **Đánh đổi:** thiết bị proxy trở thành điểm tiêu thụ tài nguyên và cần xử lý trạng thái, hiệu năng, failover, NAT và tính tương thích giao thức. Khả năng hoàn tất handshake không tự chứng minh client là người dùng hợp lệ, và SYN proxy không thay thế kiểm soát L7.

### 7.3. Rate limiting và connection limiting

Cơ chế giới hạn có thể được áp dụng với **tốc độ SYN**, số phiên mới, số phiên đồng thời hoặc mức tải theo dịch vụ/đích, tùy tính năng nền tảng. Đây là công cụ phòng vệ hữu ích nhưng cần baseline đúng.

**Không dùng một ngưỡng tùy ý cho mọi dịch vụ.** Các trường hợp sau dễ gây chặn nhầm:

- Nhiều người dùng qua NAT chung, ví dụ khu ký túc xá hoặc mạng di động.
- Đợt khuyến mại khiến yêu cầu đăng nhập/kết nối tăng đột biến.
- Kiểm tra sức khỏe của load balancer và hoạt động deploy.
- Client hoặc mạng mất gói khiến SYN được gửi lại.

Nên theo dõi tỷ lệ hoàn tất handshake và trạng thái kết nối, ưu tiên chính sách phù hợp đích và cân nhắc hành vi drop/challenge/proxy thực tế. Chặn theo IP nguồn chỉ là một tín hiệu, không phải bảo đảm xác minh danh tính.

### 7.4. Bảo vệ tại upstream và định tuyến phân tán

Khi lưu lượng tấn công vượt băng thông đường truyền Internet, **bảo vệ bên trong datacenter không thể làm thông đường vào đã bão hòa**. Các phương án có thể gồm dịch vụ chống DDoS ở ISP/cloud, scrubbing center hoặc kiến trúc phân phối lưu lượng như anycast khi phù hợp.

**Anycast** có thể giúp phân phối truy cập giữa nhiều điểm hiện diện theo định tuyến mạng, nhưng không tự phân biệt request hợp lệ và tấn công. Nó cần kết hợp năng lực lọc, capacity planning và điều phối lưu lượng.

Blackholing hoặc chuyển hướng lưu lượng có thể được nhà mạng dùng trong tình huống khẩn cấp, nhưng **chặn toàn bộ đích cũng làm người dùng hợp lệ mất dịch vụ**. Chỉ áp dụng theo runbook và thỏa thuận vận hành khi rủi ro được cân nhắc.

### 7.5. Source address validation và anti-spoofing

Kiểm soát nguồn theo hướng dẫn thực hành mạng như **source address validation/ingress filtering** giúp hạn chế một số dạng giả mạo IP nguồn. Các cơ chế như uRPF có thể hữu ích trong kiến trúc phù hợp, nhưng cần chú ý định tuyến bất đối xứng và ngoại lệ hợp lệ.

**Đội sở hữu dịch vụ bị tấn công không thể tự chặn hoàn toàn spoofing ở Internet**; hiệu quả phụ thuộc việc các mạng trung gian và mạng xuất phát thực thi kiểm soát nguồn. Đây là biện pháp cải thiện hệ sinh thái cùng với lọc, chống DDoS và xác thực kết nối.

### 7.6. Tuning TCP backlog và tài nguyên

Điều chỉnh backlog, timeout và năng lực xử lý kết nối có thể giúp **tăng khả năng chịu tải** trong giới hạn hệ thống. Tuy nhiên:

- Có thể làm tăng tiêu thụ bộ nhớ/trạng thái nếu chỉ mở rộng queue mà không xử lý nguồn tải.
- Giá trị tối ưu phụ thuộc hệ điều hành, application listener, load balancer, NIC, phiên bản kernel và traffic profile.
- Việc cạn backlog chưa chắc là nút nghẽn duy nhất.
- Cần thay đổi có kiểm thử, theo dõi counters và phương án rollback.

**Không xem tăng backlog hoặc bật SYN cookies là cách chữa duy nhất** cho một DDoS có thể làm nghẽn uplink, firewall hoặc load balancer.

## 8. Mẫu chính sách phòng vệ trung lập với sản phẩm

Đoạn YAML sau là **mô tả nguyên tắc**, không phải cấu hình nạp trực tiếp vào router, firewall, Linux kernel hoặc cloud provider:

~~~yaml
synFloodDefense:
  service: customer-api
  owner: platform-and-security
  protectedEndpoint: public-tcp-service
  baseline:
    collect:
      - syn_packets_per_second
      - completed_tcp_handshakes_per_second
      - handshake_completion_ratio
      - tcp_retransmissions
      - syn_queue_pressure
      - firewall_connection_state_usage
      - client_connection_success_rate
    compareBy:
      - hour_of_day
      - service_release_or_campaign
  controls:
    upstreamMitigation:
      enabled: true
      trigger: validated-traffic-and-capacity-risk
    tcpProtection:
      synCookies: platform-reviewed
      synProxy: enable-only-if-tested
    connectionPolicy:
      action: adaptive-protection
      thresholds: based-on-baseline-and-capacity
      avoidBlindGlobalSourceIpBlocks: true
  operations:
    detectionModeBeforeBlock: true
    contact: on-call-security-and-network
    recordChangesAndRollback: true
    protectSensitiveLogFields: true
    verifyLegitimateClientSuccess: true
~~~

Điều kiện **based-on-baseline-and-capacity** có nghĩa số ngưỡng phải lấy từ đo đạc thực tế và tài liệu sản phẩm. Chính sách mô tả không tự triển khai giải pháp; cần chuyển thành cấu hình được kiểm thử trên từng nền tảng và bảo đảm không mở quá rộng các đường quản trị.

## 9. Phát hiện trên firewall, IDS/IPS và máy chủ

### 9.1. Tại firewall và network sensor

Thu thập lưu lượng theo **đích và dịch vụ**: tốc độ SYN, số luồng mới, số gói drop theo rule, mức sử dụng bảng trạng thái, kết quả lọc của ISP và sự kiện IPS. Một cảnh báo “SYN flood suspected” nên kèm số liệu và điểm quan sát rõ ràng.

Khi sensor chỉ nhìn một chiều của luồng, không thể tính chính xác tỷ lệ handshake hoàn tất. Nếu NAT hoặc load balancer thay đổi nguồn/đích, phải ghép các log tương ứng để tránh đếm trùng hoặc gán nhầm dịch vụ.

### 9.2. Tại server TCP

Trên những hệ điều hành có hỗ trợ, có thể dùng các counters về:

- Số socket chờ hoàn tất bắt tay và biến động theo thời gian.
- Sự kiện listen overflow/drop liên quan backlog.
- SYN cookies sent/received/failed theo định nghĩa của implementation.
- TCP retransmission, timeout và connection establishment failure.
- Mức dùng CPU, IRQ, bộ nhớ, NIC drops và trạng thái listener.

Tên counter, thời điểm cập nhật và cách diễn giải khác nhau theo hệ điều hành. **Một số SYN cookie được phát ra không tự chứng minh có tấn công**: có thể do tải đột biến hoặc cấu hình backlog khác với nhu cầu thực tế.

### 9.3. Tại load balancer và ứng dụng

Đo tỷ lệ kết nối thành công, thời gian thiết lập TLS và số lỗi ở phía frontend/backend. Nếu người dùng không hoàn tất được TCP handshake, log HTTP có thể **không tăng tương ứng** vì request chưa tới ứng dụng.

Đối chiếu sức khỏe dịch vụ từ nhiều vị trí mạng giúp phân biệt lỗi cục bộ, ảnh hưởng đến một tuyến ISP và sự cố diện rộng.

## 10. Dữ liệu giả lập: đọc đồ thị sự cố

Giả sử một dịch vụ TCP có số liệu ở cùng điểm ingress, được tổng hợp theo từng cửa sổ một phút. Dữ liệu dưới đây **hoàn toàn giả lập để học cách phân tích**, không phải phép đo của một hệ thống hay ngưỡng nhận diện chuẩn:

| Mốc đo | SYN mới/giây (ước tính) | Handshake hoàn tất/giây | Hoàn tất / SYN (ước tính) | Kết nối người dùng thành công |
| --- | ---: | ---: | ---: | ---: |
| 09:00 (bình thường) | 400 | 380 | 95% | 99,9% |
| 09:05 (tăng tải) | 620 | 570 | 91,9% | 99,7% |
| 09:10 (bất thường) | 5.000 | 420 | 8,4% | 73% |
| 09:15 (chưa xử lý đủ) | 7.200 | 390 | 5,4% | 48% |
| 09:20 (sau phòng vệ giả lập) | 4.800 | 410 | 8,5% | 96% |

**Cách đọc:** từ 09:10, số yêu cầu SYN tăng mạnh nhưng tốc độ handshake hoàn tất không tăng tương ứng, đồng thời kết nối hợp lệ thất bại nhiều. Đây là dấu hiệu cần điều tra áp lực kết nối hoặc sự cố mạng; **chưa đủ kết luận nguồn tấn công hoặc cơ chế chính xác**.

Ở 09:20, tỷ lệ hoàn tất tính trên **toàn bộ SYN tại điểm đo** vẫn thấp, nhưng kết nối của người dùng hợp lệ được cải thiện. Kịch bản này có thể xảy ra khi một lớp lọc trung gian loại bỏ phần lớn yêu cầu không hợp lệ trước backend. Cần làm rõ **điểm đo trước/sau lọc**: không so sánh trực tiếp các bộ đếm ở hai điểm khác nhau hoặc coi tỷ lệ thô là KPI duy nhất.

### 10.1. Ví dụ nhật ký tổng hợp

~~~json
{
  "timestamp": "2026-11-28T09:15:00+07:00",
  "service": "customer-api",
  "measurement_point": "edge-ingress-before-filtering",
  "window_seconds": 60,
  "syn_attempts_per_second_estimate": 7200,
  "completed_handshakes_per_second_estimate": 390,
  "client_connect_success_percent": 48.0,
  "firewall_state_pressure": "elevated",
  "tcp_retransmission_trend": "increasing",
  "classification": "possible-syn-flood-or-network-impairment",
  "status": "investigating",
  "note": "Synthetic training data, not a real incident"
}
~~~

Log minh họa chỉ nêu số đo và **giả thuyết điều tra**. Đừng gắn nhãn “confirmed attacker” hay “blocked attack” khi chưa đối chiếu nguồn, điểm quan sát, hiệu quả của biện pháp phòng vệ và tình trạng dịch vụ.

## 11. Quy trình ứng phó sự cố SYN flood

Một runbook thực tế cần rõ người phụ trách, điều kiện kích hoạt, cách chuyển hướng lưu lượng, tiêu chí thành công và phương án quay lại trạng thái bình thường.

### Giai đoạn 1 – Xác minh và đánh giá ảnh hưởng

1. Ghi thời điểm, dịch vụ, public endpoint, zone, IP/VIP và những nơi người dùng bị ảnh hưởng.
2. Kiểm tra báo động từ firewall/IPS/ISP cùng số SYN, handshake, retransmission, link utilization và tình trạng API.
3. Loại trừ các thay đổi vừa triển khai, sự cố mạng, lỗi DNS hoặc tăng truy cập hợp lệ.
4. Xác định nút nghẽn chính: đường truyền, firewall conntrack, LB, TCP server hay ứng dụng.

### Giai đoạn 2 – Bảo vệ đường vào và dịch vụ

1. Nếu uplink có nguy cơ nghẽn, phối hợp ISP/cloud DDoS protection để xử lý ở upstream.
2. Áp dụng/chỉnh biện pháp SYN cookies, SYN proxy hoặc connection limiting **theo cấu hình đã thử nghiệm và hỗ trợ**.
3. Tăng mức quan sát các rule drop, tình trạng queue, lỗi kết nối hợp lệ và tài nguyên bảo vệ.
4. Hạn chế thay đổi nhiều chính sách cùng lúc; mỗi thay đổi cần có thời điểm, người duyệt và phương án rollback.
5. Nếu phải chuyển tuyến hoặc giới hạn mạnh, ưu tiên những dịch vụ thiết yếu theo kế hoạch duy trì hoạt động.

### Giai đoạn 3 – Xác minh người dùng hợp lệ

1. Kiểm tra TCP connect success và độ trễ từ những vị trí mạng ngoài hệ thống.
2. Kiểm tra tỷ lệ TLS handshake, yêu cầu API hợp lệ và lỗi người dùng trên ứng dụng.
3. Đối chiếu kết quả với log IPS, firewall và các thay đổi vừa áp dụng.
4. Giám sát trường hợp NAT/proxy chia sẻ IP bị giới hạn nhầm.

### Giai đoạn 4 – Khôi phục và rút kinh nghiệm

1. Hạ dần những kiểm soát khẩn cấp khi rủi ro đã giảm, theo quy trình được duyệt.
2. Xác nhận trạng thái routing, policy, HA và các ngoại lệ trở về mức mong muốn.
3. Lưu bằng chứng, số đo ảnh hưởng, thời điểm ứng phó và kết quả dịch vụ.
4. Cập nhật baseline, năng lực tải, hợp đồng hỗ trợ DDoS, kịch bản diễn tập và backlog cải thiện.

**Không tự động tắt logging hoặc mở allow-all** để “tăng hiệu năng” trong lúc chưa rõ nguyên nhân. Việc giảm quan sát hoặc nới rộng quyền mạng có thể làm mất dấu vết và tăng rủi ro khác.

## 12. False positive, false negative và tác động nghiệp vụ

Một hệ thống chống SYN flood hiệu quả không chỉ giảm SYN đến backend; nó phải **duy trì kết nối của người dùng hợp lệ**.

| Rủi ro | Ví dụ | Hậu quả | Cách giảm |
| --- | --- | --- | --- |
| False positive | Người dùng di động từ cùng carrier NAT bị giới hạn theo IP | Đăng nhập/kết nối hợp lệ thất bại | Đánh giá nhiều tín hiệu, ngưỡng theo đích/tải và tỷ lệ handshake |
| False positive | Đợt phát hành sản phẩm tạo kết nối mới đột ngột | Hệ thống tự chặn khách thật | Baseline theo mùa/sự kiện, thông báo thay đổi |
| False negative | Lưu lượng từ nhiều nguồn dưới ngưỡng từng IP | Áp lực tổng hợp vẫn vượt năng lực đích | Theo dõi aggregate theo dịch vụ và upstream |
| False negative | Đường phụ không qua điểm bảo vệ | Backend vẫn nhận SYN không mong muốn | Kiểm kê mọi public endpoint/tunnel/IPv6 |
| Mất sẵn sàng của biện pháp | SYN proxy hoặc LB quá tải | Biện pháp bảo vệ thành nút nghẽn mới | Capacity, HA, cảnh báo, thử nghiệm |
| Không đồng bộ dữ liệu | So sánh counter trước và sau filtering như cùng một mẫu | Chẩn đoán sai | Gắn nhãn measurement point và thời gian |

**Không có “ngưỡng SYN flood” cố định cho mọi mạng.** 1.000 SYN/giây có thể là bình thường ở dịch vụ lớn nhưng quá tải ở thiết bị nhỏ; kết luận phải dựa trên năng lực, baseline và tác động thực tế.

## 13. Lưu ý khi triển khai IPv6, VPN, Wi-Fi và cloud

### 13.1. IPv6 và mạng dual stack

SYN flood có thể nhắm vào TCP chạy trên **IPv4 hoặc IPv6**. Nếu firewall và chống DDoS chỉ áp dụng trên IPv4, endpoint IPv6 có thể trở thành đường nhận traffic khác. Cần kiểm kê bản ghi AAAA, route IPv6, chính sách tại edge, các VIP và hỗ trợ tính năng SYN protection cho cả hai họ địa chỉ.

### 13.2. VPN

Đường VPN có thể mang TCP bên trong tunnel. Bên ngoài tunnel, thiết bị chỉ nhìn thấy giao thức/vận chuyển VPN tùy công nghệ, không nhất thiết thấy SYN của dịch vụ bên trong. Việc phân tích và giới hạn SYN nội bộ phải thực hiện **tại điểm sau giải mã hoặc tại endpoint** phù hợp.

VPN cũng có thể chịu ảnh hưởng nếu cổng TCP của một dịch vụ VPN dựa trên TCP bị áp lực kết nối; cần phân biệt rủi ro ở đầu vào VPN và rủi ro của các ứng dụng đi trong tunnel.

### 13.3. Mạng không dây và IoT

Thiết bị IoT hoặc guest Wi-Fi có thể tạo nhiều kết nối, có khi do lỗi phần mềm hoặc bị xâm nhập. Phân đoạn Wi-Fi/IoT, chặn đường tới management zone và giới hạn theo gateway giúp giảm phạm vi ảnh hưởng. Tuy nhiên, IPS ở cổng Internet không nhìn thấy mọi lưu lượng giữa client trong cùng phân đoạn.

Đối với nguồn lưu lượng bất thường nội bộ, cần xem cả DHCP/NAC, danh tính thiết bị, switch port hoặc access point logs trước khi quy kết IP.

### 13.4. Cloud và CDN

Cloud load balancer, CDN, anycast và managed DDoS protection có thể giải quyết một phần áp lực trước khi traffic tới máy chủ. Cần hiểu **nơi kết thúc TCP**: metric SYN của origin sau proxy có thể không phản ánh tổng số yêu cầu SYN ngoài Internet.

Đừng dùng một subnet hoặc security group làm bằng chứng hệ thống đã chống được DDoS. Security group thường lọc quyền kết nối; chống DDoS quy mô lớn đòi hỏi capacity, observability và hỗ trợ hạ tầng bên ngoài. Quyền quản trị cloud và việc bật/tắt dịch vụ bảo vệ cũng phải được kiểm soát bằng IAM và audit log.

## 14. Mối quan hệ với IDS/IPS, firewall, WAF và phân đoạn mạng

- **Firewall/ACL:** chỉ công bố cổng TCP cần thiết và giới hạn nguồn–đích theo nghiệp vụ. Tuy nhiên, dịch vụ công khai vẫn phải tiếp nhận kết nối mới của khách, nên rule allow cổng không tự chống được SYN flood.
- **IDS:** cảnh báo tốc độ SYN tăng, nhiều kết nối chưa hoàn tất hoặc pattern tương quan. Sensor chỉ nhận SPAN có thể không thấy đủ hai chiều và không trực tiếp chặn.
- **IPS:** có thể chặn hoặc giới hạn traffic khi đặt đúng tuyến và có năng lực; phải tránh false positive gây ngắt người dùng hợp lệ.
- **WAF:** có giá trị với các lớp tấn công HTTP sau bước kết nối; không thể mặc nhiên xem là nơi xử lý chính cho một flood chưa hoàn tất TCP handshake.
- **Phân đoạn mạng:** ngăn thiết bị khách/IoT đi thẳng vào data/management zone, giảm đường tấn công nội bộ.
- **Xác thực ứng dụng:** vẫn cần thiết cho những kết nối đã hoàn tất; SYN cookie/proxy không biết người dùng có quyền xem dữ liệu nào.
- **Quan sát tập trung:** ghép flow log, firewall/IPS counters, metrics máy chủ, TLS và HTTP monitoring để đánh giá đúng tác động.

SYN flood được giải quyết hiệu quả bằng **năng lực phòng vệ ở nơi phù hợp với nút nghẽn**, không phải chỉ thêm một chữ ký IDS hoặc nâng cấp máy chủ.

## 15. Kiểm thử và diễn tập phòng vệ an toàn

Để đánh giá khả năng chịu tải, doanh nghiệp nên dùng môi trường thử nghiệm, dữ liệu tổng hợp hoặc phương án diễn tập được chủ hạ tầng và nhà cung cấp chấp thuận. **Không tự thực hiện flood trên Internet hoặc sản xuất** chỉ để đo giới hạn; hành vi đó có thể ảnh hưởng dịch vụ và các bên dùng chung hạ tầng.

### 15.1. Bộ kiểm thử không tạo lưu lượng tấn công

| Mã | Phương pháp an toàn | Mục tiêu |
| --- | --- | --- |
| T-01 | Phân tích log TCP giả lập chứa giai đoạn bình thường và bất thường | Xác định chỉ số có thể gợi ý SYN flood |
| T-02 | Kiểm tra cấu hình, tài liệu và counter read-only | Xác nhận SYN cookies/proxy hoặc chính sách bảo vệ đã được đánh giá |
| T-03 | Kiểm tra người dùng hợp lệ bằng số lượng kết nối thấp theo kế hoạch | Xác minh dịch vụ vẫn khả dụng sau thay đổi policy |
| T-04 | Mô phỏng bước kích hoạt DDoS response trong tabletop exercise | Đánh giá liên hệ giữa NOC, SOC, ISP/cloud |
| T-05 | Rà soát tuyến IPv4/IPv6, public VIP, CDN và VPN | Phát hiện đường bypass chính sách |
| T-06 | Diễn tập failover trên môi trường đại diện đã được cấp quyền | Kiểm tra HA và khả năng rollback |
| T-07 | Đối chiếu log ở trước/sau load balancer bằng dữ liệu có sẵn | Tránh kết luận sai từ các điểm đo khác nhau |

### 15.2. Checklist trước và sau thay đổi

Trước khi bật hoặc điều chỉnh một cơ chế giảm SYN flood:

1. Xác định chủ dịch vụ, vùng, các public VIP và tài nguyên có thể bị ảnh hưởng.
2. Lưu baseline TCP connect success, latency, request success, pps, bps và counters queue.
3. Ghi rõ chế độ hiện hành, đề xuất thay đổi, ticket phê duyệt và phương án rollback.
4. Xác nhận ISP/cloud provider hoặc load balancer không có chính sách mâu thuẫn.
5. Xác định ai theo dõi người dùng thật và ai có quyền thực hiện thay đổi.

Sau thay đổi, kiểm tra kết nối hợp lệ, tỷ lệ lỗi, log chặn, tài nguyên của edge/LB/server và ảnh hưởng lên các nhóm người dùng sau NAT. Nếu giảm SYN tới server nhưng khách thật không kết nối được, biện pháp chưa đạt mục tiêu availability.

### 15.3. Mẫu ghi nhận kết quả diễn tập

~~~yaml
exercise:
  id: SYN-DEFENSE-TABLETOP-004
  environment: isolated-lab-and-synthetic-telemetry
  activity: detection-and-incident-response-drill
  participants:
    - soc
    - noc
    - application-owner
  successCriteria:
    - detect-abnormal-handshake-trend
    - distinguish-link-saturation-from-server-queue-pressure
    - identify-upstream-escalation-contact
    - preserve-legitimate-client-connectivity
    - document-change-and-rollback-decisions
  prohibitedActions:
    - unapproved-production-load-generation
    - external-network-flooding
  evidence:
    - metrics-at-labeled-measurement-points
    - incident-timeline
    - decisions-and-approvals
~~~

## 16. Tình huống tổng hợp: API khó thiết lập kết nối

Một nền tảng bán hàng có public API thông qua CDN/load balancer. Trong một khoảng thời gian, đội vận hành thấy tỷ lệ thành công của khách giảm đáng kể. Firewall báo lượng SYN tới VIP tăng; application logs không tăng tương ứng.

### 16.1. Những giả thuyết đầu tiên

- Có áp lực SYN khiến nhiều kết nối không hoàn tất.
- Có packet loss hoặc vấn đề định tuyến khiến gói SYN-ACK/ACK thất lạc.
- Load balancer hoặc firewall state table đang đầy.
- Có sự kiện truy cập hợp lệ khiến số kết nối mới tăng, nhưng backend bị quá tải.
- Có thay đổi firewall, TLS hoặc routing vừa làm giảm tỷ lệ kết nối thành công.

Không kết luận ngay “bị DDoS” chỉ từ số SYN cao.

### 16.2. Bằng chứng cần đối chiếu

NOC đối chiếu link utilization và interface drops ở upstream. Đội mạng kiểm tra SYN/sec, state usage và policy drops tại edge. Đội nền tảng đo frontend/backend connection success và các sự kiện SYN cookies. Đội ứng dụng kiểm tra TLS/HTTP error, latency và những thay đổi phát hành gần nhất.

Nếu uplink đã bão hòa, ưu tiên phối hợp upstream. Nếu link vẫn còn dư nhưng server đang gặp áp lực với yêu cầu chưa hoàn tất, xem xét những biện pháp bảo vệ tại TCP layer theo runbook đã duyệt. Nếu phần lớn handshake hoàn tất nhưng API vẫn lỗi, cần điều tra backend và lớp ứng dụng thay vì chỉ tinh chỉnh SYN protection.

### 16.3. Xác nhận khôi phục

Sau các thay đổi có kiểm soát, đừng chỉ đo số gói bị drop. Hãy xác minh **người dùng từ nhiều mạng thực sự kết nối được**, độ trễ và lỗi giảm, log an ninh còn đầy đủ và không xuất hiện hiện tượng chặn nhầm các client chia sẻ NAT.

**Bài học:** chỉ số hạ tầng giúp phát hiện nút nghẽn; trải nghiệm kết nối hợp lệ mới phản ánh mục tiêu phòng vệ có đạt hay không.

## 17. Câu hỏi tự kiểm tra

1. Ba bước TCP handshake là gì? Server thường chờ điều gì sau khi gửi SYN-ACK?
2. Vì sao SYN flood có thể gây gián đoạn ngay cả khi số lượng HTTP request không tăng mạnh?
3. SYN backlog và accept queue khác nhau thế nào? SYN cookies có làm biến mất mọi điểm nghẽn TCP không?
4. SYN proxy khác SYN cookies ở đâu về vị trí và cách giảm áp lực lên backend?
5. Nếu uplink bị nghẽn trước khi tới firewall nội bộ, nên ưu tiên xem xét biện pháp ở đâu?
6. Vì sao rate limit chỉ dựa trên một IP có thể gây ảnh hưởng tới các người dùng hợp lệ sau NAT?
7. Vì sao không nên kết luận có tấn công khi chỉ thấy SYN-ACK retransmission tăng?
8. Một dịch vụ có IPv4 và IPv6: tại sao policy chống SYN flood chỉ bật trên IPv4 là thiếu?
9. IDS/IPS, firewall và WAF đóng vai trò khác nhau thế nào trong phòng vệ SYN flood?
10. Vì sao log trước CDN/load balancer và log trên origin có thể ghi số SYN rất khác nhau?

**Gợi ý:** (1) SYN, SYN-ACK, ACK; (2) phiên chưa tới HTTP; (3) queue chờ ACK và queue chờ ứng dụng nhận, cookies chỉ giảm một lớp trạng thái; (4) proxy xử lý handshake ở trung gian, cookies giảm trạng thái tại server; (5) upstream/ISP/cloud mitigation; (6) nhiều khách chia một địa chỉ; (7) lỗi mạng cũng gây mất ACK; (8) đường IPv6 vẫn có thể chịu áp lực; (9) lọc kết nối, phát hiện/ngăn lưu lượng và bảo vệ HTTP; (10) TCP được kết thúc/lọc ở nhiều điểm khác nhau.

### Bài tập thiết kế

Hãy xây dựng kế hoạch phòng vệ cho một API công khai có **firewall, load balancer, hai máy ứng dụng, kết nối cloud và VPN quản trị**:

1. Vẽ đường đi TCP từ người dùng tới điểm kết thúc kết nối, ghi rõ nơi NAT hoặc proxy có thể thay đổi nguồn/đích.
2. Liệt kê tối thiểu **năm chỉ số** để phân biệt flood với tải hợp lệ, nêu điểm đo của từng chỉ số.
3. Xác định trường hợp chọn upstream mitigation, SYN cookies, SYN proxy hoặc giới hạn kết nối và những rủi ro tương ứng.
4. Đề xuất hai phép kiểm thử không gây flood và hai điều kiện dừng nếu tổ chức thực hiện diễn tập tải được cấp quyền.
5. Viết runbook ngắn gồm phát hiện, xác minh, phân công, giảm thiểu, kiểm tra người dùng và hoàn nguyên.
6. Nêu cách bảo vệ IPv6, mạng quản trị và đường VPN khỏi việc trở thành đường bỏ qua điểm kiểm soát dự kiến.

Bài đạt yêu cầu khi **mỗi biện pháp gắn với một nút nghẽn cụ thể, có bằng chứng đo lường và không đánh đổi hoàn toàn kết nối của người dùng hợp lệ**.

## 18. Ghi nhớ

- **SYN flood tạo áp lực lên giai đoạn thiết lập TCP** bằng nhiều yêu cầu SYN không hoàn tất handshake; nó có thể là DoS hoặc DDoS tùy nguồn phát.
- **Không chỉ SYN backlog có thể quá tải.** Link, firewall connection tracking, load balancer, CPU, accept queue và ứng dụng có những điểm nghẽn riêng.
- **Một đột biến SYN không đủ kết luận tấn công.** Phải kết hợp tỷ lệ hoàn tất, retransmission, tài nguyên, đường đi và kết nối người dùng hợp lệ.
- **SYN cookies và SYN proxy xử lý áp lực handshake theo cơ chế khác nhau**, nhưng không thay thế bảo vệ băng thông upstream hay xác thực/phân quyền.
- **Rate limiting và rule chặn cần hiệu chỉnh theo dịch vụ, baseline và tác động người dùng**, tránh chặn nhầm những client chung NAT.
- **Phòng vệ hiệu quả cần nhiều lớp:** ISP/cloud mitigation, edge firewall, TCP protection, IDS/IPS, giám sát và ứng dụng có năng lực phù hợp.
- **Đừng bỏ quên IPv6, VPN, Wi-Fi/IoT, cloud/CDN và đường thay thế**, vì các điểm quan sát và điểm lọc có thể khác nhau.
- **Chỉ số thành công là duy trì được dịch vụ cho người dùng hợp lệ** với bằng chứng log/metrics đáng tin cậy, không phải chỉ số lượng gói bị chặn.

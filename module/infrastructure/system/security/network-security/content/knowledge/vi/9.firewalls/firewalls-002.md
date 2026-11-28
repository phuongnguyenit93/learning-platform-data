# Stateful firewall: kiểm soát kết nối dựa trên trạng thái phiên

**Stateful firewall** là tường lửa theo dõi ngữ cảnh của những luồng kết nối đã đi qua nó để quyết định gói tin tiếp theo có thuộc một trao đổi hợp lệ hay không. Thay vì chỉ so khớp từng gói độc lập với địa chỉ IP, giao thức và cổng, thiết bị duy trì một **bảng trạng thái kết nối (state table/connection tracking table)**. Nhờ vậy, nó có thể cho phép lưu lượng phản hồi của một kết nối đã được chấp nhận mà không cần mở một quy tắc cho phép vô điều kiện đối với toàn bộ các cổng phản hồi.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, stateful firewall là một lớp phòng vệ quan trọng khi xây dựng phân đoạn mạng, quản lý kết nối qua VPN, bảo vệ DNS, kiểm soát mạng Wi-Fi và cloud, cũng như cung cấp log để phân tích lưu lượng và hỗ trợ IDS/IPS. Tuy nhiên, tường lửa có trạng thái không tự chứng minh danh tính người dùng, tính an toàn của ứng dụng hay tính vô hại của nội dung được mã hóa. Bài học tập trung vào cách nó hoạt động, các chính sách có thể thiết kế và những giả định cần kiểm tra.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. So sánh **stateless packet filtering**, **stateful inspection** và các khả năng phân tích ứng dụng mở rộng.
2. Giải thích cách firewall tạo, tra cứu, cập nhật và xóa bản ghi trong **connection tracking table**.
3. Diễn giải lưu lượng hai chiều của **TCP**, cơ chế theo dõi UDP không có bắt tay và các thông điệp ICMP liên quan.
4. Thiết kế quy tắc **cho phép kết nối mới từ nguồn được ủy quyền và chỉ cho phản hồi tương ứng đi ngược lại**.
5. Nhận diện ảnh hưởng của **NAT, phân mảnh IP, IPv6, định tuyến bất đối xứng, HA và timeout**.
6. Sử dụng log và phép thử được phép để phân biệt lỗi định tuyến, lỗi chính sách và lỗi trạng thái phiên.

## 2. Stateless và stateful khác nhau ở quyết định nào?

Một **stateless firewall** thường áp dụng các quy tắc cho từng gói, chẳng hạn địa chỉ nguồn/đích, protocol, cổng nguồn/đích, hướng và giao diện. Nó không dựa vào bản ghi trạng thái của một trao đổi trước đó để xác định gói mới có phải phản hồi hợp lệ hay không.

Một **stateful firewall** cũng cần chính sách cho phép hoặc từ chối luồng **khởi tạo**, nhưng sau khi luồng được chấp nhận, nó có thể nhận diện các gói **thuộc cùng trao đổi** thông qua connection tracking và áp dụng chính sách dành cho lưu lượng phản hồi.

| Tiêu chí | Stateless packet filter | Stateful firewall |
|---|---|---|
| Dữ liệu dùng ra quyết định | Thông tin của gói hiện tại và quy tắc ACL | Thông tin gói, quy tắc và trạng thái luồng đã ghi nhớ |
| Kết nối TCP trả lời | Thường cần quy tắc riêng cho lưu lượng ngược hoặc quy tắc phù hợp ở từng hướng | Có thể tự động cho phép gói thuộc phiên đã được cấp quyền |
| UDP | So khớp riêng từng datagram | Có thể theo dõi một trao đổi UDP bằng địa chỉ/cổng và timeout |
| Bảng trạng thái phiên | Không cần bảng theo dõi cho phép | Cần tài nguyên lưu trạng thái và cơ chế hết hạn |
| Lỗi/rủi ro điển hình | ACL quá rộng cho cổng nguồn tạm thời; khó gắn phản hồi với yêu cầu | Bảng trạng thái đầy, mất đồng bộ HA, timeout, định tuyến bất đối xứng |
| Khả năng nhìn nội dung ứng dụng | Không mặc nhiên có | Cũng **không mặc nhiên** giải mã hay hiểu tầng ứng dụng |

**Ví dụ:** Máy nhân viên tại **10.10.10.25** mở kết nối HTTPS tới **10.20.20.10:443**. Máy nhân viên dùng một cổng nguồn tạm thời, ví dụ **51524**. Nếu chính sách cho phép kết nối TCP mới từ mạng nhân viên tới TCP/443 của ứng dụng, firewall stateful có thể cho phản hồi từ **10.20.20.10:443** về **10.10.10.25:51524** đi qua vì thuộc kết nối được phép. Không cần tạo quy tắc cho phép mọi máy ở server zone khởi tạo lưu lượng tới toàn bộ cổng cao trên mạng nhân viên.

**Cần phân biệt:** “Được phép phản hồi” không có nghĩa firewall mặc định cho phép **server khởi tạo mọi phiên ngược về client**. Đó là một hướng kết nối mới, phải qua chính sách riêng.

## 3. Connection tracking table lưu những gì?

Tùy hệ điều hành và nhà sản xuất, một bản ghi có thể lưu:

- Giao thức tầng vận chuyển, ví dụ TCP hoặc UDP, cùng địa chỉ IP nguồn/đích và cổng nguồn/đích.
- Thông tin về hai chiều của luồng để nhận biết gói yêu cầu và gói phản hồi.
- Giao diện, zone, ngữ cảnh định tuyến, rule/policy đã áp dụng hoặc các thuộc tính gắn với phiên.
- Tiến triển TCP hoặc trạng thái trừu tượng của cơ chế connection tracking, timeout và thời điểm hoạt động gần nhất.
- Thông tin NAT nếu thiết bị có dịch địa chỉ/cổng, bao gồm ánh xạ trước và sau khi dịch.
- Bộ đếm gói/byte, logging hoặc metadata khác nếu nền tảng hỗ trợ.

Với TCP và UDP, một luồng thường được nhận diện ban đầu bằng bộ thông tin tương đương **5-tuple**:

~~~text
(
  Source IP,
  Source port,
  Destination IP,
  Destination port,
  Transport protocol
)
~~~

**Ví dụ bản ghi TCP (minh họa, không phải định dạng log chuẩn của thiết bị):**

~~~text
Original:
  10.10.10.25:51524  ->  10.20.20.10:443 / TCP
Reply:
  10.20.20.10:443     ->  10.10.10.25:51524 / TCP
Policy:
  employee-to-app-https = ALLOW
Tracking:
  Luồng đã nhận phản hồi; timer tiếp tục cập nhật theo hoạt động
~~~

Các giao thức không có cổng TCP/UDP, chẳng hạn ICMP, sử dụng thêm thông tin riêng phù hợp giao thức (ví dụ loại thông điệp và identifier khi áp dụng). Vì thế **không nên khẳng định mọi bản ghi firewall đều có 5-tuple TCP/UDP giống nhau**. Hai luồng có các trường giống nhau trong từng ngữ cảnh nhưng khác VRF, network namespace hoặc zone cũng có thể được hệ thống xử lý độc lập tùy nền tảng.

**Bảng trạng thái không phải nhật ký lịch sử vĩnh viễn.** Khi phiên đóng, bị reset, không hoạt động quá timeout, hết hạn hoặc bị người quản trị xóa, bản ghi có thể biến mất. Log và connection tracking table khác nhau: bảng theo dõi trạng thái đang hoạt động, còn nhật ký được ghi theo chính sách và cấu hình lưu trữ.

## 4. Firewall theo dõi vòng đời kết nối TCP ra sao?

TCP có cơ chế thiết lập kết nối ba bước **SYN → SYN-ACK → ACK**, sau đó trao đổi dữ liệu, rồi đóng bằng FIN hoặc RST tùy tình huống. Một stateful firewall có thể dùng tín hiệu TCP này để kiểm tra mức hợp lệ của gói theo trạng thái quan sát.

~~~text
Máy khách                            Firewall                         Server HTTPS
10.10.10.25                         stateful                        10.20.20.10:443
     |                                  |                                   |
     |  SYN (51524 -> 443)              |                                   |
     |--------------------------------->|  Kiểm tra rule NEW                |
     |                                  |  ALLOW, tạo trạng thái            |
     |                                  |---------------------------------->|
     |                                  |          SYN-ACK (443 -> 51524)   |
     |                                  |<----------------------------------|
     |<---------------------------------|  Khớp phản hồi của phiên          |
     |  ACK                             |                                   |
     |--------------------------------->|---------------------------------->|
     |        Trao đổi HTTPS            |         Gói cùng phiên           |
     |<================================>|<=================================>|
     |                                  |                                   |
     | FIN/RST, idle timeout hoặc chính sách thu hồi -> xóa trạng thái      |
~~~

Một quy trình khái quát:

1. **Gói khởi tạo đến firewall:** xác định nguồn/đích, zone, giao thức, cổng và chính sách áp dụng.
2. **Nếu được phép:** tạo hoặc cập nhật bản ghi để nhận diện các gói thuộc cùng trao đổi; trong một số triển khai còn thiết lập ánh xạ NAT.
3. **Gói chiều về:** đối chiếu khóa luồng/ánh xạ và tiến triển giao thức, rồi áp dụng quy tắc cho lưu lượng phản hồi.
4. **Gói tiếp theo:** cập nhật thông tin trạng thái, bộ đếm và timer tùy cấu hình.
5. **Kết thúc:** sau đóng phiên, timeout hoặc tác động quản trị, trạng thái được giải phóng.

Không phải mọi firewall đều kiểm tra TCP với cùng mức chặt chẽ. Một số theo dõi trình tự bắt tay, cờ TCP và cửa sổ sequence; một số có chế độ kiểm tra lỏng hơn để xử lý luồng có điểm bắt đầu đã diễn ra trước khi firewall thấy gói. Những khác biệt này làm thay đổi cả độ an toàn và khả năng tương thích.

### “ESTABLISHED” của connection tracking khác trạng thái TCP ở endpoint

Trong các hệ thống như Linux conntrack, trạng thái **ESTABLISHED** của công cụ theo dõi luồng mang ý nghĩa **đã quan sát được lưu lượng phản hồi phù hợp**, không phải luôn tương đương với TCP socket state **ESTABLISHED** của hệ điều hành. Nó cũng có thể áp dụng cho trao đổi UDP hoặc ICMP được theo dõi. Khi đọc rule và log cần phân biệt loại trạng thái mà công cụ đang báo.

Ví dụ, một TCP SYN mới thường được phân loại **NEW**. Khi firewall nhận phản hồi SYN-ACK phù hợp, hệ thống theo dõi có thể xem đó là luồng đã có phản hồi, dù phía client chưa hoàn tất mọi bước của bắt tay TCP. Vì vậy không suy diễn chính xác trạng thái socket của hai máy chỉ từ nhãn conntrack.

## 5. UDP không bắt tay: stateful firewall theo dõi thế nào?

**UDP** không có SYN, FIN hay trạng thái kết nối như TCP. Tuy vậy, firewall vẫn có thể tạo một **bản ghi trao đổi UDP tạm thời** khi nó cho phép gói khởi tạo. Phản hồi được ghép theo địa chỉ/cổng và thời gian hợp lệ.

~~~text
Client 10.10.10.25:53000                    DNS resolver 10.20.30.53:53
        |                                              |
        |  UDP query -> 53                             |
        |------ Firewall cho phép, tạo UDP state ------>|
        |                                              |
        |  UDP response:53 -> 53000                    |
        |<----- Khớp UDP state đang còn hiệu lực -------|
        |                                              |
        |             Idle timeout -> xóa state         |
~~~

Cơ chế này có giới hạn:

- Firewall không thể dựa vào TCP handshake để xác nhận một UDP peer đã thiết lập phiên.
- UDP **timeout** thường ngắn hơn kết nối TCP đã thiết lập, nhưng con số cụ thể do nền tảng và cấu hình quyết định.
- **DNS, VoIP, video, game và QUIC** có hành vi UDP khác nhau; không thể chọn một timeout tối ưu cho mọi ứng dụng.
- Chỉ có bản ghi UDP không chứng minh nội dung phản hồi đúng nghiệp vụ hoặc server đã được xác thực. Với DNS, cần thêm bảo vệ resolver/DNSSEC phù hợp; với QUIC, cần xác thực TLS trong giao thức.

**ICMP** cũng có thể được theo dõi theo cặp yêu cầu/phản hồi, ví dụ Echo Request/Echo Reply. Một số thông báo lỗi ICMP/ICMPv6 được liên hệ với phiên khác, chẳng hạn thông báo không tới được đích hoặc **Packet Too Big** phục vụ Path MTU Discovery. Chặn toàn bộ ICMP/ICMPv6 vì cho rằng “không phải phiên đã thiết lập” có thể gây lỗi kết nối, đặc biệt trong IPv6.

## 6. Các trạng thái NEW, ESTABLISHED, RELATED và INVALID

Nhiều tài liệu về Linux connection tracking và tường lửa dựa trên conntrack sử dụng bốn trạng thái phổ biến:

| Trạng thái | Cách hiểu khi áp chính sách | Ví dụ |
|---|---|---|
| **NEW** | Gói thuộc một trao đổi mới hoặc chưa thấy phản hồi phù hợp theo bộ theo dõi | TCP SYN từ client đến server; yêu cầu UDP đầu tiên |
| **ESTABLISHED** | Lưu lượng thuộc trao đổi đã có phản hồi phù hợp trong bảng tracking | Gói phản hồi TCP/UDP của kết nối được chấp nhận |
| **RELATED** | Lưu lượng không phải bản thân trao đổi ban đầu nhưng được tracker xác định là liên quan | Một số thông báo lỗi ICMP/ICMPv6 cho phiên đang theo dõi |
| **INVALID** | Gói không thể được xếp hợp lệ vào phiên theo cơ chế tracking đang dùng | Gói lỗi, thiếu ngữ cảnh hoặc không phù hợp trạng thái quan sát |

Đây là **thuật ngữ cụ thể của hệ thống tracking phổ biến**, không phải hệ thống nhãn thống nhất cho mọi sản phẩm firewall. Ngoài ra, phân loại INVALID có thể xuất hiện do **định tuyến bất đối xứng, mất state hoặc timeout**, chứ không nhất thiết do hành vi tấn công. Khi điều tra phải xét bối cảnh.

Một chính sách thường có cấu trúc:

~~~text
1. Drop những gói INVALID theo chính sách và ngữ cảnh phù hợp.
2. Accept những gói ESTABLISHED, RELATED hợp lệ.
3. Với luồng NEW: áp allowlist theo nguồn, đích, dịch vụ, zone.
4. Nếu không khớp quy tắc cho phép: deny/drop theo chính sách mặc định.
5. Ghi log và theo dõi các quyết định cần điều tra.
~~~

**Thứ tự và vị trí áp dụng cực kỳ quan trọng.** Một quy tắc cho phép mọi kết nối mới trước quy tắc hạn chế sẽ làm hỏng mục tiêu phân đoạn. Ngược lại, quy tắc deny bao trùm đặt quá sớm có thể chặn cả lưu lượng cần thiết, tùy semantics của platform.

## 7. Ví dụ chính sách stateful cho ba vùng mạng

Giả sử có ba security zone:

- **Employee:** subnet **10.10.10.0/24**, máy người dùng.
- **Application:** subnet **10.20.20.0/24**, API nội bộ với máy chủ **10.20.20.10**.
- **Database:** subnet **10.30.30.0/24**, database **10.30.30.10**.

Ứng dụng được thiết kế để nhận HTTPS từ người dùng và kết nối database trên TCP/5432. Máy nhân viên **không** được mở kết nối tới database trực tiếp.

~~~text
                    [Employee 10.10.10.0/24]
                                |
                     NEW TCP/443: Allow
                                |
                          [Stateful FW]
                         /             \
                        /               \
       [Application 10.20.20.10]    [Database 10.30.30.10]
                        |               ^
                        +-- TCP/5432 ---+
                          NEW: Allow theo
                          nguồn ứng dụng

       Employee -> Database TCP/5432: DENY
       Các gói phản hồi của luồng hợp lệ: tra state table
~~~

### Ma trận các phiên được phép khởi tạo

| Nguồn khởi tạo | Đích | Dịch vụ | Quyết định cho NEW | Phản hồi |
|---|---|---|---|---|
| Employee | API **10.20.20.10** | TCP/443 | Allow | Được nhận theo state nếu hợp lệ |
| Application **10.20.20.10** | DB **10.30.30.10** | TCP/5432 | Allow | Được nhận theo state nếu hợp lệ |
| Employee | DB **10.30.30.10** | TCP/5432 | Deny | Không tạo phiên được phép |
| Database | Employee | TCP/51524 khởi tạo mới | Deny | Không tự được phép vì trùng cổng tạm của client |
| Zone khác | API/DB | Mọi dịch vụ không khai báo | Deny theo mặc định | Không tạo phiên |

Ví dụ **TCP/51524** là cổng tạm mang tính minh họa, không phải cổng cố định của nhân viên. Khi một luồng đã được chấp nhận, thiết bị có thể quản lý phản hồi theo trạng thái thay vì tạo ACL cho mọi cổng nguồn tạm.

### Pseudocode chính sách

~~~text
IF packet matches invalid tracking state:
    DROP (sau khi tính các trường hợp ngoại lệ theo nền tảng)
ELSE IF packet matches established or related state:
    ACCEPT
ELSE IF packet starts a new flow AND
        source_zone == employee AND
        destination_ip == 10.20.20.10 AND
        protocol == TCP AND destination_port == 443:
    ACCEPT and TRACK
ELSE IF packet starts a new flow AND
        source_ip == 10.20.20.10 AND
        destination_ip == 10.30.30.10 AND
        protocol == TCP AND destination_port == 5432:
    ACCEPT and TRACK
ELSE:
    DROP or REJECT according to policy
~~~

Pseudocode chỉ minh họa **logic quyết định**, chưa bao gồm tất cả thông tin interface, zone, IPv6, NAT, IPsec, quản trị, DNS, NTP, health check hoặc ngoại lệ của hệ thống thật. Không dùng trực tiếp để thay thế một rule set đang chạy.

## 8. Thực hành đọc chính sách bằng Linux nftables

Linux có cơ chế **netfilter/conntrack**, thường được điều khiển bằng **nftables**. Đoạn dưới đây mô tả cú pháp của một rule set đơn giản để học cách kết hợp trạng thái với địa chỉ và cổng. Đây là **ví dụ minh họa**, không phải cấu hình hoàn chỉnh để triển khai vào gateway production.

~~~nft
table inet learning_filter {
    chain forward {
        type filter hook forward priority filter; policy drop;

        ct state invalid drop
        ct state established,related accept

        ip saddr 10.10.10.0/24 ip daddr 10.20.20.10 \
            tcp dport 443 ct state new accept

        ip saddr 10.20.20.10 ip daddr 10.30.30.10 \
            tcp dport 5432 ct state new accept
    }
}
~~~

Ý nghĩa:

- **table inet:** trong nftables, họ bảng inet có thể phục vụ quy tắc IPv4 và IPv6; các điều kiện **ip saddr/ip daddr** trong ví dụ chỉ khớp **IPv4**, không tạo tương đương IPv6.
- **hook forward:** xử lý gói được chuyển tiếp giữa các giao diện qua máy Linux làm router/firewall; **không tự áp dụng cho lưu lượng đến tiến trình của chính máy firewall** (đó là input) hoặc lưu lượng máy firewall tự gửi (output).
- **policy drop:** các gói chuyển tiếp không được cho phép theo rule sẽ bị chặn.
- **ct state established,related accept:** cho phép những gói có trạng thái phù hợp đã được ghi nhận; cần xem chính sách toàn hệ thống để hiểu nguồn tạo phiên.
- **ct state new** cộng nguồn/đích/cổng: giới hạn việc khởi tạo phiên mới.

Trong môi trường thực tế, phải đánh giá thêm **thứ tự các base chain**, NAT, anti-spoofing, địa chỉ/giao diện thực, logging, ICMP/ICMPv6, dịch vụ phụ trợ và chính sách IPv6 tương ứng. Chỉ với đoạn trên, DNS hoặc cập nhật phần mềm cần thiết có thể bị chặn; vì vậy không nên sao chép và áp dụng ngay trên gateway đang vận hành.

**Các lệnh quan sát chỉ đọc trên Linux được phép quản trị:**

~~~bash
sudo nft list ruleset
sudo conntrack -L
ss -nt
~~~

Tùy hệ thống, cần cài tiện ích **conntrack** và có quyền phù hợp để xem bảng; trên máy không sử dụng nftables/netfilter hoặc chạy trong container có namespace khác, kết quả có thể thiếu hoặc không phản ánh firewall biên thực sự. Không nên dùng các lệnh thay đổi state table trên hệ thống đang chạy khi chưa đánh giá ảnh hưởng.

## 9. Stateful firewall và NAT có mối quan hệ gì?

**Network Address Translation (NAT)** thay đổi địa chỉ IP hoặc cổng theo quy tắc. Trong nhiều hệ thống, NAT và connection tracking phối hợp để nhận diện phản hồi và áp ánh xạ ngược.

Ví dụ máy nhân viên dùng địa chỉ private **10.10.10.25:51524**, truy cập dịch vụ Internet **198.51.100.20:443** qua thiết bị NAT với IP công khai giả định **203.0.113.5**:

~~~text
Trước khi qua NAT:
  10.10.10.25:51524  ->  198.51.100.20:443  TCP

Sau khi qua SNAT/PAT:
  203.0.113.5:62001 ->  198.51.100.20:443  TCP

Phản hồi trở về:
  198.51.100.20:443 -> 203.0.113.5:62001

NAT state khớp -> dịch về 10.10.10.25:51524
Firewall state -> kiểm tra phản hồi thuộc phiên được phép
~~~

Các dải **198.51.100.0/24** và **203.0.113.0/24** ở đây được dành cho tài liệu, **không phải địa chỉ Internet để thực hành kết nối**. Giá trị cổng NAT là ví dụ; thực tế thiết bị có thể giữ nguyên hoặc đổi cổng dựa trên cấu hình và xung đột.

**NAT và stateful firewall là hai chức năng khác nhau.** Một NAT có thể sử dụng tracking mà không tạo chính sách hạn chế quyền đủ mạnh; một stateful firewall cũng có thể hoạt động **không NAT**, chẳng hạn giữa VLAN hoặc với IPv6. **NAT không phải cơ chế mã hóa, xác thực hoặc phân quyền ứng dụng**. Chính sách firewall phải được kiểm tra độc lập với việc địa chỉ có bị dịch hay không.

Khi phân tích log trên thiết bị có NAT, cần xác định log ghi địa chỉ **trước hay sau dịch**, và có mã phiên/ánh xạ giúp đối chiếu hay không. Nhầm địa chỉ trong log có thể dẫn tới nhận định sai nguồn kết nối hoặc vị trí áp dụng rule.

## 10. Định tuyến bất đối xứng và tính sẵn sàng cao

Stateful firewall cần thấy **đủ gói cần thiết của phiên** để duy trì trạng thái phù hợp. Khi gói đi và gói về qua các thiết bị khác nhau, một firewall chỉ thấy phản hồi có thể không có bản ghi của yêu cầu ban đầu.

~~~text
                         [Client]
                         /      \
                        v        ^
                       FW-A     FW-B
                         \      /
                          v    ^
                         [Server]

    FW-A thấy hướng đi; FW-B thấy hướng về.
    Nếu không chia sẻ state và chính sách phù hợp,
    FW-B có thể đánh giá gói phản hồi là không thuộc phiên đã biết.
~~~

**Asymmetric routing** có thể đến từ định tuyến nhiều đường, load balancing, policy-based routing, đường dự phòng, SD-WAN hoặc một số thiết kế kết nối cloud/VPN. Cần phân biệt:

- **Một firewall quan sát hai chiều:** khả năng theo dõi trạng thái thường đơn giản hơn.
- **Một cụm HA có state synchronization:** các thiết bị có thể chia sẻ thông tin phiên tùy sản phẩm và cấu hình; không đảm bảo đồng bộ mọi trạng thái hoặc mọi giao thức trong tất cả tình huống.
- **Hai firewall độc lập không chia sẻ state:** gói chiều về có thể bị coi là NEW/INVALID hoặc bị từ chối theo chính sách.

Trong quá trình failover, các kết nối đang tồn tại **có thể** bị gián đoạn nếu trạng thái chưa đồng bộ, NAT mapping đổi, hoặc đường đi khác đi. Không nên mặc định “có HA” tương đương “mọi phiên được giữ nguyên” mà không thử các kịch bản lỗi.

### Khi trạng thái hết hạn trước ứng dụng

Ứng dụng có thể giữ kết nối TCP/UDP lâu nhưng ít gửi dữ liệu. Nếu idle timeout của firewall ngắn hơn khoảng im lặng, bản ghi bị xóa; gói tiếp theo có thể không phù hợp với chính sách dành cho phiên mới, dẫn tới mất kết nối.

Khi điều tra cần đối chiếu **timeout ứng dụng, TCP keepalive/heartbeat, timeout conntrack, NAT timeout và thời gian thực tế giữa các gói**. Tăng timeout quá cao cũng có thể làm bảng trạng thái giữ nhiều phiên không còn cần thiết, tăng áp lực tài nguyên; cần lựa chọn theo loại ứng dụng và năng lực thiết bị.

## 11. Bảng trạng thái có giới hạn: hiệu năng và các rủi ro

Vì firewall phải ghi nhớ phiên, **tài nguyên CPU, bộ nhớ và số mục conntrack** giới hạn khả năng xử lý lưu lượng. Rủi ro đáng chú ý:

| Rủi ro | Biểu hiện | Hướng xử lý |
|---|---|---|
| **State table exhaustion** | Không thể thêm phiên mới, kết nối bị lỗi dù rule allow | Theo dõi số phiên hiện tại và giới hạn, phân tích tăng đột biến, điều chỉnh công suất/chính sách |
| **SYN flood / nhiều nửa phiên TCP** | Nhiều phiên khởi tạo nhưng không hoàn tất đúng mức mong đợi | Giới hạn tốc độ phù hợp, SYN proxy/cơ chế chống flood nếu nền tảng hỗ trợ, bảo vệ DDoS theo kiến trúc |
| **UDP flow churn** | Hàng loạt trao đổi UDP ngắn tạo/xóa state liên tục | Theo dõi loại traffic, timeout, giới hạn nguồn và khả năng xử lý |
| **Timeout không phù hợp** | Ứng dụng idle bị ngắt, NAT mapping mất; hoặc state tồn quá lâu | Điều chỉnh theo ứng dụng, kiểm tra heartbeat/keepalive và cấu hình HA |
| **Rule stateful quá rộng** | Phiên không cần thiết vẫn được khởi tạo rồi cho phản hồi qua | Thu hẹp nguồn/đích/dịch vụ của **NEW**, không chỉ nhìn quy tắc ESTABLISHED |
| **Không thấy đủ lưu lượng** | Phản hồi bị chặn do route asymmetry hoặc luồng đi đường khác | Kiểm tra tuyến hai chiều, state sync hoặc kiến trúc thực thi |
| **IP fragmentation/extension headers** | Khó phân loại L4 hoặc mất ngữ cảnh trước khi tái lắp ghép | Kiểm tra khả năng xử lý fragment, IPv6 extension header, PMTUD và chính sách |
| **Thiếu log/giới hạn log** | Khó biết rule nào cho phép/chặn; ghi quá nhiều gây mất hiệu năng | Logging chọn lọc, lưu thông tin phiên, giám sát sức khỏe và dung lượng |

**Đừng lấy việc cho phép trạng thái ESTABLISHED làm chứng cứ tuyệt đối về an toàn.** Nếu một máy đã bị xâm nhập khởi tạo kết nối tới đích mà policy cho phép, firewall có thể tiếp tục cho gói phản hồi đi qua. Để phát hiện hành vi xấu bên trong luồng đã được phép cần các lớp bảo vệ bổ sung như IDS/IPS, EDR, kiểm soát DNS, proxy, TLS kiểm chứng danh tính và log ứng dụng.

## 12. Vai trò trong thiết kế phòng vệ nhiều lớp

| Thành phần | Vai trò phối hợp với stateful firewall | Giới hạn của firewall |
|---|---|---|
| **Phân đoạn VLAN/VRF/zone** | Quy định tài sản nào có thể khởi tạo phiên giữa các miền | Nếu traffic không đi qua điểm đặt firewall, rule không kiểm soát được luồng đó |
| **Network Access Control / 802.1X** | Xác thực và xếp thiết bị/người dùng vào role/VLAN ban đầu | Chỉ dựa IP chưa chắc xác minh được ai đang dùng thiết bị |
| **VPN/IPsec** | Bảo vệ kênh truyền và xác thực các peer theo cấu hình | Tunnel mã hóa không tự giới hạn mọi dịch vụ được phép trong tunnel |
| **IDS/IPS** | Giám sát hoặc chặn dấu hiệu xâm nhập trong lưu lượng thấy được | Stateful inspection L3/L4 không mặc nhiên phát hiện hành vi ứng dụng độc hại |
| **DNS security** | Giảm rủi ro phân giải sai hoặc truy vấn tới resolver không được phép | Cho phép DNS theo state không chứng minh bản ghi DNS chính xác |
| **Wi-Fi/guest isolation** | Kết hợp SSID/role với policy kết nối ra ngoài hoặc tới nội bộ | Cùng SSID hoặc VLAN không tự bảo đảm mọi thiết bị đều an toàn |
| **Cloud security groups** | Nhiều nền tảng áp dụng quy tắc có trạng thái tại interface/workload | Mô hình cụ thể, nguồn log, timeout và quy tắc khác nhau giữa nhà cung cấp |
| **TLS/mTLS/identity-aware gateway** | Xác thực ứng dụng hoặc workload và bảo vệ dữ liệu | Firewall thấy phiên TCP/UDP hợp lệ không đồng nghĩa xác minh nội dung TLS hoặc danh tính ứng dụng |

Một sai lầm thường gặp là cho rằng firewall có trạng thái đồng nghĩa với **Next-Generation Firewall (NGFW)**. NGFW là tên nhóm khả năng thương mại có thể gồm nhận diện ứng dụng, phân tích nội dung, threat intelligence, ngăn xâm nhập và kiểm soát chính sách nâng cao. **Stateful inspection là một khả năng**, không tự bao gồm toàn bộ tính năng của NGFW.

### Lưu lượng mã hóa

Với HTTPS hoặc VPN, firewall có thể thấy một phần metadata mạng như IP, port, giao thức, kích thước và thời gian lưu lượng, tùy vị trí, tunnel và công nghệ sử dụng. Firewall **không mặc nhiên thấy nội dung HTTP bên trong TLS hoặc payload của IPsec**. Muốn thực hiện kiểm soát sâu hơn cần thiết kế điểm giải mã hoặc phân tích ở lớp tương ứng, xem xét bảo vệ khóa, quyền riêng tư, hiệu năng và chính sách của tổ chức.

## 13. Cách kiểm tra chính sách stateful trong lab

Mục tiêu bài thực hành là **quan sát chiều khởi tạo và chiều phản hồi** của kết nối được phép, rồi kiểm tra một kết nối mới trái chính sách có bị chặn hay không. Dùng lab được phép, tránh thử lên hạ tầng đang phục vụ sản xuất khi chưa có kế hoạch thay đổi.

### 13.1. Xác định sơ đồ và kỳ vọng

Giả sử lab đã có firewall giữa hai vùng thử nghiệm:

~~~text
Client: 10.10.10.25
App:    10.20.20.10:443
DB:     10.30.30.10:5432

Expected:
  Client -> App  TCP/443  ALLOW
  App -> Client  response to allowed session ALLOW
  Client -> DB   TCP/5432 DENY
  DB -> Client   new TCP session DENY
~~~

Đây là địa chỉ nội bộ **giả định** cho lab, cần thay bằng sơ đồ được quản trị cho phép. Đầu tiên phải bảo đảm dịch vụ đích thực sự đang lắng nghe và có định tuyến hai chiều; nếu ứng dụng không chạy, một kết nối thất bại không chứng minh firewall đang chặn đúng rule.

### 13.2. Quan sát gói và trạng thái

Trên máy Linux được phép bắt gói, có thể xem lưu lượng liên quan tới app:

~~~bash
sudo tcpdump -nni any 'host 10.20.20.10 and tcp port 443'
~~~

Trên máy Linux đóng vai firewall có sử dụng conntrack và có quyền xem bảng:

~~~bash
sudo conntrack -L -p tcp
sudo nft list ruleset
~~~

**Chỉ đọc, không xóa state hay thay rule** trong bước quan sát. Khi hệ thống đã có nhiều luồng, có thể cần lọc dữ liệu xuất ra theo IP/port được phép xem và tránh ghi thông tin nhạy cảm vào báo cáo.

Các bộ lọc **Wireshark** phù hợp cho file PCAP hợp lệ:

~~~text
ip.addr == 10.20.20.10
tcp.port == 443
tcp.flags.syn == 1
tcp.flags.reset == 1
icmp || icmpv6
~~~

Bắt được **SYN và SYN-ACK** là bằng chứng về lưu lượng đã được nhìn thấy tại **điểm bắt gói**, không đủ để suy ra mọi hop trên đường đi cũng đã nhận. Nếu ứng dụng nằm sau proxy, cần xác định vị trí bắt gói so với proxy/NAT.

### 13.3. Kiểm chứng có hệ thống

| Test ID | Luồng cần thử | Expected | Cần đối chiếu |
|---|---|---|---|
| FW-01 | Client → API TCP/443 | Allow | TCP handshake, TLS/app success, rule allow và state được tạo |
| FW-02 | API → Client, phản hồi của FW-01 | Allow theo state | Bản ghi conntrack, hướng phản hồi, rule/metric phù hợp |
| FW-03 | Client → DB TCP/5432 | Deny | Log rule deny tại firewall và service/route đã xác minh |
| FW-04 | DB → Client, phiên khởi tạo mới | Deny | Không nhầm với phản hồi cũ; rule cho NEW |
| FW-05 | Ngắt/khôi phục đường dự phòng trong lab | Phù hợp thiết kế HA | State sync, route hai chiều, tác động lên phiên |

**Kết quả “timeout” không tự chứng minh FW-03 được chặn đúng chính sách.** Cần đọc log tại điểm thực thi, bảng định tuyến và trạng thái server. Nếu host không có dịch vụ hoặc sai route thì phép thử cần được đánh dấu **INCONCLUSIVE**, thay vì PASS.

### Mẫu biên bản

~~~text
Test ID:             [FW-01..FW-05]
Time / timezone:     [thời gian thực tế]
Source zone / IP:    [giá trị xác minh]
Destination / port:  [giá trị xác minh]
Protocol:            [TCP / UDP / ICMP]
Expected:            [ALLOW / DENY]
Observed:            [kết quả thu được]
Connection state:    [bản ghi trạng thái nếu có]
Policy / rule ID:    [ID thực thi]
NAT mapping:         [trước / sau NAT nếu có]
Evidence:            [PCAP/log/route/app check]
Result:              [PASS / FAIL / INCONCLUSIVE]
~~~

## 14. Tình huống xử lý sự cố: HTTPS đi được một lúc rồi treo

**Bối cảnh giả định:** Một nhân viên kết nối qua VPN vào ứng dụng nội bộ. Firewall cho phép TCP/443. Kết nối HTTPS đầu tiên thành công, nhưng nếu người dùng để tab trình duyệt không hoạt động lâu, lần gửi yêu cầu tiếp theo có thể treo hoặc phải kết nối lại.

**Các giả thuyết cần kiểm tra:**

1. **Idle timeout của firewall/NAT:** trạng thái bị xóa trong khi phía ứng dụng tin kết nối vẫn còn.
2. **Đường đi chiều về đổi:** gói phản hồi từ server qua firewall khác, không nhìn thấy state của yêu cầu.
3. **VPN reconnect/đổi IP nguồn:** tunnel được thiết lập lại, IP hoặc cổng NAT thay đổi khiến luồng cũ không còn khớp.
4. **Ứng dụng/proxy/server timeout:** API gateway, load balancer hoặc server chủ động đóng phiên; không nhất thiết do firewall.
5. **MTU/PMTUD, mất gói:** tunnel overhead hoặc ICMP thiết yếu bị chặn làm một số gói không truyền được, có thể tạo biểu hiện tương tự.

**Quy trình điều tra:**

- Ghi lại timestamp, IP/cổng trước và sau NAT, VPN session và log của firewall/ứng dụng.
- Quan sát ở cả hai phía firewall xem gói nào được gửi, gói nào bị chặn và trạng thái phiên còn hay đã mất.
- Kiểm tra conntrack timeout của giao thức liên quan, log HA/failover và tuyến đường hai chiều.
- Đối chiếu ứng dụng/proxy trước khi thay đổi firewall; nếu xác nhận timeout, điều chỉnh theo yêu cầu ứng dụng và năng lực bảng trạng thái.
- Kiểm tra lại một phiên hoạt động lâu với đúng thời gian nghỉ từng gây lỗi, đồng thời theo dõi số lượng state và tác động hệ thống.

**Điều không nên làm:** mở rộng một rule thành allow-any-any chỉ vì ứng dụng bị timeout. Cách này có thể che dấu nguyên nhân, làm tăng bề mặt tấn công mà chưa sửa được vấn đề trạng thái.

## 15. Sai lầm phổ biến

| Nhận định sai | Vì sao không chính xác | Cách tiếp cận đúng |
|---|---|---|
| Có stateful firewall thì không cần xác thực ứng dụng | Theo dõi luồng không xác thực người dùng/peer ở cấp ứng dụng | Kết hợp TLS/mTLS, IAM, phân quyền và chính sách mạng |
| Cho phép ESTABLISHED đồng nghĩa cho phép mọi chiều | Phản hồi phải liên hệ tới phiên đã được theo dõi | Chỉ cho phép NEW theo nguồn/đích/dịch vụ, kiểm tra state |
| UDP không có kết nối nên firewall không thể có state | Firewall có thể ghi nhớ trao đổi UDP bằng khóa luồng và timeout | Hiểu cơ chế pseudo-state và giới hạn của UDP |
| TCP conntrack ESTABLISHED luôn bằng TCP socket ESTABLISHED | Hai khái niệm theo dõi khác nhau | Đọc trạng thái theo ngữ nghĩa của nền tảng |
| NAT tự chặn các kết nối trái phép | NAT là dịch địa chỉ/cổng, không thay thế policy | Cấu hình explicit allow/deny và kiểm thử |
| Tăng timeout càng cao càng tốt | Giữ state lâu gây tốn tài nguyên và ảnh hưởng khi tải lớn | Đặt timeout theo loại ứng dụng và quan sát thực tế |
| Firewall HA chắc chắn giữ nguyên mọi phiên | State sync và NAT/routing có thể chưa đầy đủ | Thử failover, kiểm tra đồng bộ và xử lý phiên |
| IPv4 rule sẽ tự bảo vệ IPv6 | IPv6 có địa chỉ, route và yêu cầu ICMPv6 riêng | Tạo chính sách dual-stack được kiểm chứng |
| Không kết nối được nghĩa là firewall chặn đúng | Có thể thiếu route hoặc dịch vụ không lắng nghe | Dùng log, bắt gói và kiểm tra server để xác minh |
| IDS/IPS chỉ cần đặt ở Internet edge | Lưu lượng east–west có thể không qua edge | Xác định điểm quan sát theo luồng thực tế |

## 16. Câu hỏi tự kiểm tra

1. Một TCP SYN mới từ mạng nhân viên đến API thường được phân loại **NEW**. Vì sao firewall có thể cho phép SYN-ACK quay về mà không mở quyền để API khởi tạo bất kỳ kết nối nào tới client?
2. Một stateful firewall lưu những thông tin gì để ghép gói TCP/UDP vào đúng luồng?
3. Vì sao một phản hồi UDP không đủ chứng minh DNS resolver trả dữ liệu tin cậy?
4. Trong Linux conntrack, **ESTABLISHED** khác gì với TCP socket state ESTABLISHED?
5. Nếu một đường truyền đi qua FW-A và quay về qua FW-B, rủi ro nào xảy ra khi chúng không đồng bộ trạng thái?
6. NAT có phải một hình thức xác thực hoặc mã hóa không? Tại sao?
7. Vì sao không nên chặn mọi ICMPv6 khi xây dựng rule set cho IPv6?
8. Khi một ứng dụng HTTPS idle lâu rồi bị ngắt, cần kiểm tra ít nhất ba nguồn bằng chứng nào trước khi tăng timeout?
9. Một kết nối được stateful firewall cho qua đã đủ chứng minh ứng dụng và dữ liệu an toàn chưa?
10. Làm cách nào để xác minh một luồng DENY bị chặn đúng rule thay vì thất bại do route hoặc server?

## 17. Ghi nhớ trọng tâm

**Stateful firewall** kiểm soát các luồng bằng cách kết hợp **chính sách cho phép kết nối mới** với **connection tracking** cho các gói thuộc trao đổi đã được chấp nhận. Với TCP, thiết bị có thể quan sát tiến triển bắt tay và đóng kết nối; với UDP/ICMP, nó dùng cơ chế theo dõi theo ngữ cảnh và thời hạn thích hợp. Nhờ vậy, việc cho phép traffic phản hồi không đồng nghĩa với mở toàn bộ kết nối ngược chiều.

Thiết kế hiệu quả cần **rule NEW theo quyền tối thiểu**, xử lý trạng thái ESTABLISHED/RELATED/INVALID phù hợp nền tảng, xác minh tuyến đường hai chiều, NAT, timeout, IPv6, phân mảnh và khả năng HA. **Một phiên hợp lệ về mặt mạng chưa chắc hợp lệ về mặt ứng dụng**; firewall stateful phải phối hợp với phân đoạn, NAC, VPN, DNS security, IDS/IPS, TLS và xác thực ứng dụng. Kết luận chính sách hoạt động đúng chỉ nên đưa ra sau khi có **bằng chứng từ rule, bảng trạng thái, route và lưu lượng thực tế**.

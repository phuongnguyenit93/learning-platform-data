# Management Frame Protection (PMF): bảo vệ khung quản lý trong mạng Wi-Fi

Trong chương **Wireless security** của module **SECURITY_NETWORK_SECURITY**, **Management Frame Protection (MFP)**, thường được gọi là **Protected Management Frames (PMF)**, là cơ chế bảo vệ những **khung quản lý 802.11 quan trọng** khỏi việc bị giả mạo hoặc sửa đổi trên đường truyền vô tuyến. Cơ chế này xuất phát từ **IEEE 802.11w**, về sau được tích hợp vào các phiên bản tiêu chuẩn IEEE 802.11.

Khi người dùng kết nối Wi-Fi, quá trình kết nối không chỉ gồm truyền dữ liệu qua IP. Access point (AP) và thiết bị đầu cuối còn dùng **management frames** để phát hiện mạng, thiết lập liên kết, duy trì trạng thái và ngắt liên kết. Nếu một số khung quản lý không được xác thực, đối tượng ở trong vùng phủ sóng có thể tìm cách giả mạo thông báo ngắt kết nối hoặc tác động đến hoạt động của client.

**PMF thu hẹp bề mặt tấn công đó**, nhưng không bảo vệ toàn bộ khung Wi-Fi, không ngăn mọi kiểu gây nhiễu sóng và không thay thế xác thực mạng, phân đoạn VLAN, firewall, VPN, IDS/IPS, bảo vệ DNS hay kiểm soát danh tính. Muốn đánh giá hiệu quả cần biết **khung nào được bảo vệ, khóa được thiết lập ở giai đoạn nào, client có thương lượng PMF hay không và AP áp chế độ optional/required như thế nào**.

Sau bài học, bạn có thể:

- Phân biệt **management, control và data frames** trong IEEE 802.11.
- Xác định vai trò của PMF đối với **deauthentication, disassociation** và những **robust action frames**.
- Giải thích các khả năng **MFPC** và **MFPR** trong RSN, phân biệt chế độ PMF disabled, capable/optional và required.
- Hiểu ở mức hệ thống cách PMF sử dụng bảo vệ khóa theo phiên, **BIP/IGTK**, kiểm tra tính toàn vẹn/chống phát lại và **SA Query**.
- Đánh giá tương thích của **WPA2, WPA3, Wi-Fi doanh nghiệp, guest và IoT**, kể cả rủi ro cấu hình chế độ chuyển tiếp.
- Xây dựng bộ kiểm chứng bằng **AP/WLC logs, RSN Information Element, 802.11 packet capture và thống kê chất lượng sóng**.
- Nhận biết giới hạn của PMF trước **evil twin, RF jamming, rogue AP, lỗi roaming và tấn công ngoài lớp liên kết**.

## 1. Management frames đóng vai trò gì trong Wi-Fi?

IEEE 802.11 chia các khung vô tuyến thành những nhóm chính:

| Nhóm khung | Ví dụ | Chức năng |
| --- | --- | --- |
| **Management** | Beacon, Probe Request/Response, Authentication, Association, Reassociation, Deauthentication, Disassociation, Action | Khám phá SSID/AP, thiết lập và điều phối trạng thái liên kết |
| **Control** | ACK, RTS/CTS, Block Ack và các khung điều khiển theo chuẩn/tính năng | Điều phối truy cập môi trường truyền và xác nhận ở lớp MAC |
| **Data** | 802.11 data frames mang IP, ARP hoặc dữ liệu khác | Vận chuyển dữ liệu người dùng/ứng dụng |

Khi một laptop vào mạng, nó có thể quan sát beacon, gửi probe, thực hiện xác thực 802.11 phù hợp với phương thức bảo mật, association, bắt tay thiết lập khóa và sau đó truyền data frames.

~~~mermaid
sequenceDiagram
    participant C as Wi-Fi client (STA)
    participant A as Access Point (AP)
    A-->>C: Beacon / thông tin mạng
    C->>A: Authentication và Association
    A-->>C: Association Response
    C->>A: Thiết lập khóa theo RSN/WPA
    A-->>C: Hoàn tất thiết lập khóa
    Note over C,A: PMF đã được thương lượng và khóa thích hợp đã sẵn sàng
    C->>A: Data frames / protected robust management
    A-->>C: Data frames / protected robust management
~~~

Sơ đồ thể hiện các giai đoạn **khái niệm**, không mô tả đầy đủ mọi biến thể WPA2-Enterprise, WPA3-SAE, roaming hay 802.1X. Đặc biệt, **PMF không mặc định bảo vệ mọi thông điệp ngay từ khi client mới nhìn thấy beacon**: cơ chế xác thực tính toàn vẹn của các robust management frames phụ thuộc vào trạng thái liên kết an toàn và khóa được thiết lập.

### 1.1. Deauthentication và disassociation khác nhau thế nào?

- **Deauthentication** thông báo rằng quan hệ xác thực 802.11 không còn hiệu lực; client thường phải thực hiện lại các bước cần thiết để tham gia mạng.
- **Disassociation** thông báo rằng quan hệ association không còn hiệu lực; tác động và quá trình phục hồi chi tiết tùy trạng thái và implementation.
- **Action frames** phục vụ nhiều chức năng quản lý bổ sung. Chỉ những loại được tiêu chuẩn phân loại là **robust management frames** mới thuộc phạm vi bảo vệ cơ bản của PMF.

Một AP có lý do chính đáng để ngắt client, chẳng hạn thay đổi policy, lỗi phiên hoặc yêu cầu vận hành. Vấn đề an ninh là **khung ngắt kết nối không được xác thực có thể bị giả mạo** nếu hệ thống không bật hoặc không thương lượng PMF đúng cách.

### 1.2. Vì sao khung quản lý không được bảo vệ là rủi ro?

Trong môi trường vô tuyến, đối tượng ở gần có thể quan sát các tín hiệu phát sóng mà không cần cắm dây vào switch. Một khung quản lý không có xác thực mật mã có thể chứa địa chỉ MAC nguồn/đích và thông tin trông giống khung do AP hoặc client phát ra.

Nếu client/AP tin một khung **deauthentication/disassociation** giả mạo, một số hậu quả có thể gồm:

1. **Gián đoạn dịch vụ:** client bị ngắt Wi-Fi, cuộc gọi hoặc phiên ứng dụng mất ổn định.
2. **Kết nối lại liên tục:** tiêu tốn thời gian roaming, xác thực và thiết lập khóa; gây trải nghiệm chập chờn.
3. **Tạo điều kiện cho kịch bản tấn công khác:** thúc đẩy client tìm AP khác hoặc thử lại quy trình kết nối. Tác động tiếp theo phụ thuộc cấu hình xác thực, chính sách client và bảo vệ tầng khác.
4. **Nhiễu tín hiệu điều tra:** log ghi nhiều sự kiện ngắt/kết nối, dễ bị nhầm với vấn đề RF, firmware, DHCP hoặc roaming.

Đây không phải bằng chứng rằng kẻ tấn công đã đọc được nội dung HTTPS hay chiếm tài khoản. **Ngắt kết nối ở lớp liên kết** và **xâm nhập dữ liệu ứng dụng** là hai kết quả khác nhau.

## 2. PMF/802.11w bảo vệ điều gì?

**Protected Management Frames** nhằm tăng cường **xác thực nguồn phát, tính toàn vẹn và bảo vệ chống phát lại** đối với một tập **robust management frames** được định nghĩa trong 802.11. Một số loại khung unicast còn được bảo vệ bí mật nội dung bằng cơ chế mã hóa đã thương lượng.

### 2.1. Những khung nào thường được PMF bảo vệ?

| Loại khung | PMF cơ bản xử lý ra sao? | Lưu ý |
| --- | --- | --- |
| **Deauthentication** sau khi đã có liên kết PMF phù hợp | Robust management; cần bảo vệ/xác minh theo cơ chế PMF | Khung giả mạo không có bảo vệ hợp lệ không được xem như lệnh ngắt phiên đáng tin |
| **Disassociation** sau khi đã có liên kết PMF phù hợp | Robust management; cần bảo vệ/xác minh | Không đồng nghĩa client sẽ không bao giờ rớt mạng vì lý do khác |
| **Một số Action frames** thuộc loại robust | Bảo vệ khi thuộc phạm vi chuẩn và điều kiện PMF | Không phải mọi Action frame đều thuộc loại robust |
| **Beacon** thông thường | **Không được bảo vệ bởi PMF cơ bản 802.11w** | Các cơ chế beacon protection hiện đại, nếu có, là tính năng cần kiểm tra riêng |
| **Probe Request/Response** | Không thuộc tập robust frames PMF cơ bản | Thông tin SSID/khả năng quảng bá vẫn cần được xem như dữ liệu chưa xác thực ban đầu |
| **Authentication/Association ban đầu** | Không mặc định có bảo vệ PMF của một liên kết đã hoàn tất | Thiết kế chống giả mạo giai đoạn đầu phụ thuộc các cơ chế khác và cách xử lý của chuẩn |
| **Control frames / nhiễu RF** | Không phải đối tượng bảo vệ trực tiếp của PMF | Tắc nghẽn kênh, jamming và vấn đề vật lý cần biện pháp khác |
| **Data frames** | Được bảo vệ bằng cơ chế mã hóa/bảo mật dữ liệu tương ứng của kết nối | Không gọi đó là PMF; hai phạm vi có quan hệ nhưng khác mục đích |

**Robust management frame** là thuật ngữ kỹ thuật của chuẩn, không đồng nghĩa “bất kỳ management frame nào có vẻ quan trọng”. Khi cần phân tích một subtype cụ thể, phải xem phân loại của phiên bản IEEE 802.11 và khả năng thực thi của thiết bị/AP.

### 2.2. Unicast và broadcast/multicast khác nhau

Đối với **robust management frames gửi unicast**, AP và client có thể dùng cơ chế bảo vệ theo khóa của kết nối đã thương lượng (ví dụ họ cơ chế dựa trên CCMP/GCMP tương ứng).

Với **robust management frames gửi theo nhóm**, không thể áp mô hình unicast đơn giản cho từng client. Cơ chế **Broadcast/Multicast Integrity Protocol (BIP)** cùng **Integrity Group Temporal Key (IGTK)**, hoặc các phương thức/khóa tương ứng theo chuẩn và cipher suite, giúp thiết bị nhận kiểm tra tính toàn vẹn/xác thực và chống phát lại cho khung nhóm phù hợp.

Điểm phân biệt quan trọng:

- **Bảo vệ tính toàn vẹn** giúp nhận biết khung bị sửa hoặc không được tạo bởi bên nắm khóa hợp lệ.
- **Chống phát lại** giúp hạn chế việc gửi lại một khung đã được chấp nhận để gây tác động trái phép.
- **Bảo mật nội dung** của một loại khung phụ thuộc phương thức bảo vệ; không mặc định rằng mọi khung nhóm được PMF bảo vệ đều bị mã hóa nội dung.
- Việc một packet hiển thị bit **Protected** hoặc có trường kiểm tra mật mã trong bản capture phải được đánh giá theo **loại khung, cipher và trạng thái phiên**.

PMF **không phải giấy chứng nhận rằng AP hay hệ điều hành không có lỗi**. Một thiết bị đã nắm khóa hoặc hệ thống bị chiếm quyền vẫn có thể tạo khung hợp lệ về mặt mật mã; cơ chế này chỉ kiểm tra quyền tạo/sửa khung theo ngữ cảnh khóa.

## 3. PMF được thương lượng giữa AP và client như thế nào?

AP và client thông báo khả năng PMF qua các thông tin **Robust Security Network (RSN)**, trong đó có những bit khả năng thường được gọi là:

- **MFPC (Management Frame Protection Capable):** thiết bị báo rằng nó **có khả năng** hỗ trợ PMF.
- **MFPR (Management Frame Protection Required):** chính sách của thiết bị/yêu cầu kết nối quy định PMF **phải được sử dụng**.

Các trường này nằm trong ngữ cảnh **RSN Capabilities** của thông tin bảo mật kết nối. Không được hiểu rằng chỉ vì beacon quảng bá một bit khả năng là toàn bộ trao đổi với client đã được xác thực.

### 3.1. Disabled, optional và required

| Chế độ được quản trị viên chọn trên SSID | Khả năng/định hướng | Client không hỗ trợ PMF | Client hỗ trợ PMF |
| --- | --- | --- | --- |
| **Disabled** | SSID không dùng PMF cho các liên kết của nó | Có thể kết nối nếu các điều kiện bảo mật khác tương thích | Kết nối có thể hoạt động nhưng không được hưởng PMF tại SSID này |
| **Capable / Optional** | AP hỗ trợ PMF nhưng không bắt mọi client sử dụng | Có thể kết nối theo mode bảo mật được cho phép, không có PMF | Có thể thương lượng và sử dụng PMF nếu tương thích |
| **Required / Mandatory** | AP yêu cầu PMF cho liên kết thuộc SSID này | **Không thể hoàn tất kết nối tương thích** do thiếu PMF | Có thể kết nối nếu phương thức xác thực, cipher và các điều kiện khác đều phù hợp |

Đây là bảng **khái niệm**. Kết quả còn phụ thuộc cấu hình WPA2/WPA3, cipher, phiên bản driver/firmware và cách controller ánh xạ tên tùy chọn. Một số giao diện dùng tên “Protected Management Frames: Disabled/Capable/Required”, hệ thống khác dùng “Optional/Mandatory”.

**MFPR mà không có khả năng MFPC tương ứng là trạng thái không nhất quán**; không coi đây là một cấu hình sử dụng hợp lệ.

### 3.2. Ví dụ negotiation

~~~text
SSID CORP (WPA2-Enterprise, ví dụ):
  AP: PMF Capable = true, PMF Required = true

Client A: PMF Capable = true
  => PMF requirement tương thích, còn phải vượt qua xác thực bảo mật khác.

Client B: PMF Capable = false
  => Không đáp ứng yêu cầu PMF của SSID CORP.

SSID LEGACY (ví dụ):
  AP: PMF Capable = true, PMF Required = false
  Client B: PMF Capable = false
  => Có thể được chấp nhận theo các điều kiện khác,
     nhưng liên kết của Client B không có PMF.
~~~

Một client không tham gia được SSID required **không chứng minh** client bị tấn công. Đó có thể là kết quả **không tương thích tính năng**. Cần xem log lý do association/rejection trên AP/WLC và trạng thái driver client thay vì mở ngoại lệ an ninh ngay.

### 3.3. Trình tự khái niệm

~~~mermaid
sequenceDiagram
    participant C as Client / STA
    participant A as AP / WLC
    A-->>C: Beacon có thông tin RSN/PMF
    C->>A: Association với RSN capabilities
    A-->>C: Kiểm tra policy và khả năng
    alt PMF required nhưng client không hỗ trợ
        A-->>C: Association không được chấp nhận
    else Phương thức bảo mật tương thích
        C->>A: Xác thực và key establishment phù hợp
        A-->>C: Hoàn tất thiết lập khóa cần thiết
        Note over C,A: Robust management frames được bảo vệ theo PMF
        A-->>C: Protected disassociation nếu thật sự cần ngắt
    end
~~~

Sơ đồ rút gọn các bước. Trong WPA2-Enterprise, quá trình 802.1X/EAP và key establishment có thứ tự cụ thể; trong WPA3-Personal dùng SAE. Thông tin RSN của association không được xem như một chữ ký số riêng lẻ; **bảo vệ các robust frames sau thiết lập khóa** là mục tiêu trọng tâm của PMF.

## 4. Cơ chế khóa và xác minh khung được bảo vệ

### 4.1. PMF không tạo ra một “mật khẩu Wi-Fi” khác

PMF dựa vào cơ chế RSN và những khóa phù hợp **đã được thiết lập trong phiên bảo mật của AP–client**. Người dùng không cần nhập thêm một mật khẩu tên “PMF”; điều cần thiết là AP, client và phương thức bảo mật hỗ trợ đúng các cipher/khóa.

Trong mô hình WPA2/WPA3 bảo mật thông dụng, việc thiết lập khóa cho kết nối dẫn đến các khóa phục vụ dữ liệu và những loại khung quản lý được bảo vệ. **Cấu trúc khóa và thuật toán cụ thể** phụ thuộc phiên bản chuẩn, cipher suite và cách triển khai.

### 4.2. Cơ chế unicast robust management

Đối với một khung robust management gửi **riêng tới client đã thương lượng PMF**, bên nhận có thể kiểm tra:

1. Khung có thuộc loại cần được bảo vệ trong trạng thái phiên hiện tại không?
2. Khung có sử dụng phương thức bảo vệ phù hợp với bảo mật đã thương lượng không?
3. Kiểm tra mật mã và **tính tươi/chống phát lại** có đạt không?
4. Khung có hợp lệ với trạng thái association/peer hiện tại không?

Nếu các điều kiện bảo vệ không đạt, một **unprotected hoặc forged deauthentication frame** không được phép làm client ngắt phiên như một thông báo hợp lệ trong trạng thái PMF đang có hiệu lực.

Một số dạng **packet loss** vẫn xảy ra do sóng yếu hoặc thiết bị reset, dù attacker không thể gửi một deauth frame hợp lệ. Vì vậy, **PMF bảo vệ quyết định tin một khung quản lý**, chứ không bảo đảm duy trì liên kết vô tuyến bằng mọi giá.

### 4.3. BIP và khóa dành cho group-addressed frames

**BIP** được dùng cho khung robust management gửi theo nhóm khi thích hợp. Nội dung khung mang thông tin kiểm tra toàn vẹn như MIC cùng dữ kiện kiểm soát phát lại theo cipher suite; **IGTK** là một khóa nhóm phục vụ bảo vệ loại khung đó trong các cấu hình PMF tương ứng.

Cần lưu ý:

- Một **group key** không phải bằng chứng danh tính người dùng riêng biệt; nó được quản lý trong ngữ cảnh AP và nhóm client có quyền nhận.
- Việc quản lý/chuyển đổi khóa nhóm phải đồng bộ với trạng thái phiên, key rotation và roaming.
- Thuật toán kiểm tra có thể thuộc các họ **BIP-CMAC hoặc BIP-GMAC** tùy môi trường/cipher; không được giả định mọi thiết bị cùng một thuật toán.
- **Beacon protection** của các thế hệ Wi-Fi mới hơn có thể sử dụng các cơ chế riêng; không gộp mọi beacon vào “BIP đã bảo vệ” chỉ vì SSID bật 802.11w PMF.

### 4.4. SA Query là gì?

**Security Association (SA) Query** là cơ chế trong họ bảo vệ quản lý 802.11 giúp xác minh rằng một peer **đang duy trì liên kết bảo mật đã được thiết lập** trong các tình huống cần kiểm tra trạng thái association, ví dụ khi xuất hiện yêu cầu (re)association có khả năng xung đột với một association đã có PMF.

Thay vì tin ngay một sự kiện có thể làm mất liên kết hiện tại, thiết bị có thể dùng trao đổi SA Query được bảo vệ phù hợp, có **transaction identifier và giới hạn thời gian**, để kiểm tra peer hiện hữu. Cách kích hoạt, timeout và các thông điệp cụ thể phụ thuộc chuẩn và triển khai.

Không nên mô tả SA Query như **một cơ chế chạy trước mọi gói deauth** hoặc như biện pháp chống mọi kiểu DoS. PMF và SA Query cùng hướng tới độ tin cậy của trạng thái kết nối, nhưng vẫn không xử lý được tắc nghẽn sóng, mất nguồn AP hay firmware bị lỗi.

## 5. Quan hệ giữa PMF, WPA2 và WPA3

### 5.1. WPA2 có thể dùng PMF

**PMF không đồng nghĩa WPA3.** Một mạng **WPA2-Personal** hoặc **WPA2-Enterprise** với phần cứng/firmware/client tương thích có thể hỗ trợ PMF, thậm chí cấu hình **PMF required** nếu toàn bộ thiết bị cần kết nối đáp ứng yêu cầu.

Không nên suy luận “mạng đang dùng WPA2 thì không có PMF”. Đồng thời, việc mạng dùng AES-CCMP cho **data frames** không tự chứng minh robust management frames đã được bảo vệ; cần kiểm tra **PMF negotiation thực tế của từng client**.

### 5.2. WPA3 và PMF

Trong các profile **Wi-Fi CERTIFIED WPA3**, PMF là một yêu cầu bảo mật quan trọng. Vì vậy, mạng WPA3 thuần và thiết bị tuân thủ đúng profile được thiết kế để dùng PMF; khả năng kết nối thực tế còn phụ thuộc client, firmware, chế độ Personal/Enterprise và bộ cipher.

Những khái niệm dễ nhầm:

- **SAE** trong WPA3-Personal là phương thức thiết lập/xác thực khóa bằng mật khẩu với đặc tính bảo mật phù hợp; **SAE không phải PMF**.
- **802.1X/EAP-TLS** có thể cung cấp xác thực danh tính mạng trong môi trường Enterprise; **EAP-TLS không phải PMF**.
- **PMF** bảo vệ nhóm robust management frames sau khi bảo mật liên kết thích hợp được thiết lập; nó **không tự xác nhận chứng chỉ RADIUS** hoặc bảo vệ dữ liệu ứng dụng khỏi mọi threat.

Một WLAN bảo mật tốt kết hợp **định danh mạng đúng, xác thực phù hợp, mã hóa data frames, PMF, policy truy cập sau association và giám sát**.

### 5.3. WPA2/WPA3 transition mode và bài toán tương thích

Trong một **transition mode** cho phép cả thiết bị WPA2 và WPA3, các thiết bị có thể sử dụng **những phương thức bảo mật khác nhau** trong cùng một môi trường quảng bá tương thích. Một số cấu hình chuyển tiếp cho phép PMF optional đối với liên kết WPA2, trong khi phía WPA3 yêu cầu bảo vệ theo profile.

Hệ quả:

1. **Không được suy từ nhãn SSID “WPA2/WPA3” rằng mọi client đang dùng PMF.**
2. Một client cũ có thể tham gia bằng liên kết không PMF nếu AP cho phép để tương thích.
3. Chế độ chuyển tiếp có bề mặt **downgrade/compatibility** cần đánh giá; các khả năng chống downgrade tùy thuộc chuẩn, firmware và policy client.
4. Nếu thiết bị đều hỗ trợ, **WPA3-only với PMF required** thường giúp chính sách dễ kiểm chứng hơn cho nhóm thiết bị tương thích.
5. Nếu phải giữ legacy, nên **tách nhóm và hạn chế quyền**, thay vì làm yếu toàn bộ SSID doanh nghiệp.

Đừng bật hoặc tắt transition mode chỉ theo một chỉ số “kết nối thành công”; cần đo cả **security mode thật của session**, tỷ lệ thiết bị không tương thích, tác động roaming và rủi ro dữ liệu.

## 6. Threat model: PMF chặn được gì và chưa chặn được gì?

| Threat / tình huống | PMF giúp giảm rủi ro thế nào? | Phần việc vẫn cần control khác |
| --- | --- | --- |
| **Forged deauthentication** tới một STA đã có PMF | Khung robust không được bảo vệ/xác thực hợp lệ sẽ không thể được xem là lệnh ngắt phiên đáng tin | RF jamming, lỗi thiết bị, thời điểm chưa có khóa vẫn cần xét |
| **Forged disassociation** sau liên kết PMF | Bảo vệ tương tự cho disassociation đúng phạm vi | Hành vi legitimate disconnect hoặc session timeout vẫn có thể xảy ra |
| **Giả mạo một số robust Action frames** | Xác minh nguồn, toàn vẹn và replay theo loại khung/cipher | Khung không thuộc loại robust có thể không nằm trong phạm vi PMF |
| **Replay protected management frame** | Kiểm tra tính tươi/counter có thể loại khung phát lại không hợp lệ | Không bảo vệ mọi logic/firmware flaw hoặc dữ liệu ứng dụng |
| **Evil twin / rogue AP** | Không tự phát hiện hoặc xác minh mọi AP mạo danh | 802.1X và xác minh chứng chỉ, WPA3/SAE phù hợp, WIDS/WIPS, inventory AP |
| **Giả mạo beacon/probe ban đầu** | PMF cơ bản không xác thực mọi thông điệp trước liên kết | Hỗ trợ beacon protection nếu có; cấu hình client/SSID và giám sát RF |
| **RF jamming / interference** | Không ngăn tắc nghẽn hoặc gây nhiễu kênh vô tuyến | RF monitoring, thiết kế kênh/công suất, vị trí AP và xử lý nhiễu |
| **Rogue DHCP, DNS redirection** | Không kiểm soát địa chỉ IP, gateway hoặc resolver sau association | DHCP snooping, RA Guard, DNS protection, VLAN segmentation, firewall |
| **Lateral movement trong Wi-Fi** | Không trực tiếp giới hạn quyền truy cập giữa client và service | 802.1X/NAC, dynamic VLAN, client isolation, firewall/ZTNA |
| **Credential phishing hoặc ứng dụng yếu** | Không thay xác thực tầng ứng dụng hay TLS | MFA, certificate validation, EDR, WAF và bảo vệ ứng dụng |

### 6.1. PMF không phải công nghệ chống jamming

Jamming hoặc nhiễu môi trường có thể khiến sóng bị chiếm dụng, client không nghe được AP hoặc ACK thất bại. **Không có khung deauthentication giả mạo nào cần được chấp nhận** để kết nối vẫn bị rớt do chất lượng kênh. Vì vậy, một báo cáo “đã bật PMF nhưng Wi-Fi vẫn gián đoạn” không tự chứng minh PMF bị vượt qua.

Các metric liên quan gồm **RSSI, SNR, channel utilization, retransmissions, radio errors, AP reboot/roam events** và cả lượng khung management đáng ngờ được nhận. Nếu chỉ có log “client disconnected”, chưa thể gán nguyên nhân là một khung giả mạo.

### 6.2. PMF không xác thực toàn bộ giai đoạn khám phá mạng

Các **beacon** và **probe responses** thông thường mang thông tin SSID, BSSID và khả năng bảo mật; phần lớn trao đổi khám phá xảy ra **trước khi client đã thiết lập khóa phiên**. Một rogue AP có thể quảng bá cùng tên SSID hoặc thông số nhìn giống mạng chính thức.

Việc chọn mạng đáng tin phải dựa vào **xác thực đúng phương thức**, đặc biệt:

- **WPA2/WPA3-Enterprise:** thiết bị phải kiểm tra đúng **chứng chỉ server EAP/RADIUS và domain/tên server dự kiến** theo policy quản trị; tránh cho phép “trust any certificate”.
- **WPA3-Personal/SAE:** dùng cấu hình bảo mật đúng, mật khẩu đủ mạnh và tránh profile tự động chọn phương thức yếu hơn không mong muốn.
- **Managed endpoints:** triển khai cấu hình Wi-Fi qua MDM/management, hạn chế tự động kết nối SSID lạ và quản lý danh sách mạng được phép.
- **WIDS/WIPS:** phát hiện AP/BSSID lạ, SSID impersonation và biến động vùng phủ sóng bằng giám sát RF.

PMF là một **lớp bảo vệ trạng thái liên kết**, không phải cơ chế xác thực tin cậy tuyệt đối cho beacon.

## 7. Kiến trúc Wi-Fi doanh nghiệp: thiết kế SSID và chính sách PMF

Giả sử tổ chức có bốn nhóm sử dụng:

~~~mermaid
flowchart TD
    U["Laptop & smartphone quản lý"] --> C["SSID CORP / WPA3-Enterprise hoặc WPA2-Enterprise phù hợp"]
    I["Thiết bị IoT đời cũ"] --> T["SSID IoT riêng / policy tương thích có kiểm soát"]
    G["Khách vãng lai"] --> V["SSID GUEST / yêu cầu bảo vệ theo khả năng client"]
    M["Nhân viên vận hành"] --> O["SSID ADMIN hoặc đường quản trị được phê duyệt"]
    C --> A["AP / WLC / WLAN policy"]
    T --> A
    V --> A
    O --> A
    A --> F["Segmentation / Firewall / NAC"]
    F --> S["Application / DNS / Internet theo quyền"]
    A -. "PMF, association, RF, reason codes" .-> L["Wireless monitoring / SOC"]
    F -. "Session / DNS / traffic logs" .-> L
~~~

SSID, VLAN và địa chỉ trong mô hình được đặt **theo threat model**, không có nghĩa mỗi SSID bắt buộc ánh xạ một VLAN hoặc mọi nhà cung cấp đều cung cấp cùng tính năng. Điểm cốt lõi là không để yêu cầu tương thích của một nhóm thiết bị làm suy yếu toàn bộ chính sách truy cập.

### 7.1. CORP: ưu tiên bắt buộc PMF khi khả thi

Nếu toàn bộ laptop/điện thoại doanh nghiệp đã được kiểm kê là tương thích, chính sách mục tiêu có thể là:

- Phương thức xác thực **WPA3-Enterprise**, hoặc **WPA2-Enterprise với cơ chế mã hóa và PMF phù hợp** theo năng lực thiết bị.
- **PMF required** trên SSID hoặc profile bảo mật áp dụng.
- **EAP server certificate validation**, quản trị thiết bị, thu hồi quyền truy cập khi offboarding.
- **Dynamic VLAN/role-based access** và firewall giữa user–app–management.
- Log association/roaming, PMF negotiation, authentication và dấu hiệu bất thường.

Khi chưa đạt độ tương thích cần thiết, phải lập kế hoạch thay thiết bị/firmware và chọn lộ trình migration; không nên đặt “PMF optional mãi mãi” mà không có thời hạn hoặc owner.

### 7.2. GUEST: chính sách bảo vệ tương xứng

Wi-Fi guest phục vụ thiết bị ngoài phạm vi quản lý nên có thể có phân bố khả năng hỗ trợ PMF đa dạng. Một số lựa chọn gồm:

- Dùng **WPA3-Personal/Enhanced Open hoặc profile bảo mật phù hợp** với thiết bị khi có thể, kiểm tra yêu cầu PMF cụ thể của profile.
- Với môi trường cần hỗ trợ legacy, áp **chế độ tương thích có ràng buộc**, đo tỷ lệ session thực sự có PMF và đưa kế hoạch nâng cấp.
- **Client isolation**, captive portal/guest access nếu cần, firewall không cho truy cập nội bộ, DNS/egress policy và rate controls hợp lý.

PMF không thay thế chính sách cô lập guest khỏi dữ liệu doanh nghiệp. Mạng guest có PMF required nhưng cho phép truy cập management subnet vẫn là kiến trúc sai.

### 7.3. IoT/OT: không hy sinh security cho compatibility mà không kiểm soát

Một thiết bị IoT cũ có thể không hỗ trợ PMF hoặc chỉ hỗ trợ một số phương thức WPA. Nếu nó là thiết bị thiết yếu chưa thể nâng cấp:

1. Ghi rõ **model, firmware, chuẩn Wi-Fi và mức độ PMF support** từ kiểm thử.
2. Tạo **SSID/VLAN hoặc microsegment riêng**, giới hạn chỉ các đích/cổng cần thiết.
3. Chặn IoT truy cập trực tiếp **USER, DATA, MANAGEMENT** khi không có lý do nghiệp vụ.
4. Dùng NAC/inventory và log luồng; kiểm soát DNS, mDNS/Bonjour gateway nếu kiến trúc có sử dụng.
5. Bổ sung cơ chế chống gián đoạn ở mức hệ thống, giám sát RF và kế hoạch thay thiết bị.
6. Đặt **owner, ngày rà soát và thời hạn ngoại lệ** cho phần không thể dùng PMF.

Đặt một thiết bị không hỗ trợ PMF vào VLAN riêng **không biến liên kết vô tuyến của nó thành có PMF**; đây là biện pháp giảm tác động nếu bị lợi dụng hoặc mất kết nối.

## 8. PMF trong roaming, multi-AP và mạng có nhiều controller

Một client di chuyển giữa hai AP cùng SSID có thể thực hiện **roaming/reassociation**. Quá trình này kết hợp RF, lựa chọn BSSID, chính sách bảo mật, key management và trạng thái phiên.

~~~text
Client nối AP-A (PMF negotiated)
      |
      | Di chuyển / điều kiện RF thay đổi
      v
Client cân nhắc AP-B trong cùng ESS
      |
      +-> Kiểm tra khả năng bảo mật, PMF, cipher, policy
      +-> Roaming / reassociation / key management thích hợp
      |
      v
Client nối AP-B (PMF negotiated nếu policy yêu cầu)
~~~

**Một session đã có PMF trên AP-A không chứng minh mọi association tiếp theo tới AP-B tự động có bảo vệ giống nhau**; cần kiểm tra policy và kết quả thương lượng tại AP đích.

### 8.1. Những yếu tố cần kiểm thử

- **Cấu hình SSID/WLAN profile đồng nhất:** AP/controller có cùng policy WPA/PMF/cipher, ngoại lệ và firmware tương thích.
- **802.11r Fast Transition (nếu dùng):** khả năng FT và PMF của client/AP phải tương thích, không gây lặp authentication hoặc association failure.
- **802.11k/v và steering:** các khung/đề xuất tối ưu roaming không tự bảo đảm security; các action frames cần được đánh giá theo loại và trạng thái PMF.
- **Multi-controller/mesh:** đồng bộ policy/key management và log roaming, xác định nơi session chuyển giao.
- **Chất lượng RF:** điểm chết sóng hoặc channel congestion có thể làm tăng roam và disconnect dù PMF hoạt động đúng.

Đừng biến việc giảm lỗi roaming thành “tắt PMF cho tất cả”; trước tiên cần tách **PMF negotiation failure** khỏi **802.1X/EAP failure, DHCP delay, RF loss hoặc firmware incompatibility**.

## 9. Giám sát PMF: đọc log AP/WLC và dữ liệu RF

### 9.1. Nguồn evidence cần thu thập

| Nguồn | Dữ kiện nên có | Giới hạn |
| --- | --- | --- |
| **AP/WLC association log** | SSID, BSSID, client ID/MAC, thời gian, RSN/PMF capable/required/negotiated, reason/status code | Log vendor có thể bỏ bớt trường; text “PMF enabled” ở SSID chưa phải trạng thái từng client |
| **RADIUS/802.1X log** | Auth result, identity đã được bảo vệ, EAP method, certificate validation failure nếu có | Thành công 802.1X không tự chứng minh PMF đã negotiated nếu không có WLAN/session context |
| **802.11 monitor capture** | Beacon/probe/association RSN IE, deauth/disassoc/action, Protected bit, thời điểm, BSSID và channel | Capture có thể bỏ frame, không thấy mọi kênh và không mặc định giải mã payload |
| **Wireless IDS/IPS / RF telemetry** | Nhóm BSSID/SSID lạ, số management frames đáng ngờ, channel utilization, interference | Alert dựa trên mẫu không tự chứng minh một cuộc tấn công thành công |
| **Client event logs** | Nguyên nhân disconnect, roaming, driver/firmware, trạng thái mạng | Reason code có thể bắt nguồn từ nhiều lớp; không tự xác nhận spoofing |
| **DHCP/DNS/firewall logs** | Thời điểm client lấy IP, DNS, quyền mạng, request bị chặn | Lỗi sau association có thể bị nhầm là lỗi PMF |
| **Inventory/change log** | Model AP, client firmware, WLAN profile version, thay đổi PMF policy | Cần đối chiếu thời điểm; snapshot hiện tại không đủ cho sự cố quá khứ |

### 9.2. Những câu hỏi khi xem một “deauth flood” alert

1. Sensor ở **channel nào**, quan sát BSSID/STA nào và khoảng thời gian nào?
2. Khung được thấy là **unprotected** hay **protected**? Nó xuất hiện **trước hay sau** khi liên kết PMF được thiết lập?
3. AP và client của session đó **đã thương lượng PMF thực sự chưa**?
4. Client có **thực sự bị ngắt** và kết nối lại không, hay tiếp tục truyền data frames bình thường?
5. Có **nhiễu RF, roaming, AP restart, RADIUS timeout hoặc DHCP issue** cùng thời điểm không?
6. Có log/capture trên **nhiều sensor hoặc endpoint** xác nhận diễn biến tương ứng không?

Nhiều khung management bất thường **không đồng nghĩa** dữ liệu đã bị lộ. Một báo cáo có giá trị phải chỉ rõ **detection**, **kết quả liên kết** và **mức chắc chắn của bằng chứng**.

### 9.3. Packet capture Wi-Fi khác packet capture Ethernet

Một capture trên interface Ethernet phía sau AP thường chỉ thấy **lưu lượng đã được bridge/tunnel hoặc chuyển đổi sang Ethernet/IP**. Nó **không mặc định chứa khung 802.11 management** trên không trung.

Muốn quan sát PMF tại lớp radio, cần:

- Card/adapter có **monitor mode hoặc capture radio chuyên dụng**, phần mềm/driver tương thích.
- Đặt **đúng kênh/băng tần** nơi AP và client đang trao đổi; roaming hoặc channel switching có thể làm mất một phần chứng cứ.
- Timestamp và metadata như channel, RSSI, BSSID, MAC, subtype, frame control khi capture có cung cấp.
- Quyền thu thập trong môi trường được quản lý; 802.11 captures có thể chứa định danh thiết bị và dữ liệu nhạy cảm.
- Kết hợp log AP/WLC và client, vì capture một phía **không tự chứng minh** khung đã được bên nhận chấp nhận hoặc từ chối.

Các display filter **minh họa** trong Wireshark:

~~~text
# Khung management theo type của IEEE 802.11.
wlan.fc.type == 0

# Deauthentication (management subtype 12).
wlan.fc.type_subtype == 0x0c

# Disassociation (management subtype 10).
wlan.fc.type_subtype == 0x0a

# Những khung mang bit Protected.
wlan.fc.protected == 1
~~~

Tên field/filter có thể thay đổi theo phiên bản Wireshark. Hãy kiểm tra **RSN Information Element** trong các khung quảng bá/association, quan sát **MFPC/MFPR**, rồi tương quan với session log. Bit Protected hoặc một RSN flag đơn lẻ **không đủ xác nhận end-to-end PMF hoạt động đúng**.

**Không thực hiện phát giả mạo khung deauthentication hoặc gây nhiễu trên mạng đang có người sử dụng**. Những tình huống tiêu cực có thể kiểm chứng bằng **packet trace đã được cấp phép, mô phỏng/offline PCAP, thiết bị lab cô lập hoặc tính năng kiểm thử của vendor** theo quy trình an toàn.

## 10. Quy trình chẩn đoán khi client không kết nối hoặc bị rớt Wi-Fi

### 10.1. Phân biệt các giai đoạn thất bại

~~~mermaid
flowchart TD
    A["Client thấy SSID?"] -->|Không| R["Kiểm tra radio, band, channel, beacon, range"]
    A -->|Có| B["Authentication / Association thành công?"]
    B -->|Không| C["Kiểm tra WPA mode, RSN, PMF required/MFPC, status code"]
    B -->|Có| D["Key establishment & 802.1X/SAE thành công?"]
    D -->|Không| E["Kiểm tra EAP/cert, SAE, cipher, controller/client logs"]
    D -->|Có| F["Đã có PMF negotiation/session ổn định?"]
    F -->|Không rõ| G["Đối chiếu AP/WLC session và WLAN policy"]
    F -->|Có| H["IP/DHCP/DNS và quyền truy cập hoạt động?"]
    H -->|Không| I["Kiểm tra DHCP, DNS, VLAN, firewall, route"]
    H -->|Có| J["Theo dõi roaming, RF, reason codes và ứng dụng"]
~~~

Sơ đồ là checklist; thứ tự bước cụ thể thay đổi theo phương thức WPA và implementation. Nếu một client báo không có Internet, không được suy ngược rằng PMF chặn kết nối khi **association và key establishment đã thành công**; phải kiểm tra DHCP, DNS, VLAN, NAT, firewall và route.

### 10.2. Một số triệu chứng thường gặp

| Triệu chứng | Khả năng liên quan PMF | Những nguyên nhân khác cần kiểm tra |
| --- | --- | --- |
| Client cũ không vào được sau khi SSID chuyển PMF required | Client/driver không hỗ trợ PMF hoặc cipher không tương thích | WPA/802.1X/cert, firmware, thời điểm thay policy |
| Chỉ một model điện thoại rớt khi roaming | Bug FT/PMF/firmware hoặc mismatch WLAN profile giữa AP | RF coverage, steering, controller roam state |
| Log có nhiều deauth frames nhưng PMF client vẫn online | Khung giả mạo không được tin; PMF có thể đang giúp hạn chế tác động | Sensor trùng lặp, traffic hợp lệ, noise RF |
| Client hỗ trợ PMF nhưng không thấy negotiated | AP để optional/disabled, khác SSID/BSSID, transition mode | Khả năng driver, policy security mode, session log |
| Connection reset sau khi AP reboot | PMF không bảo vệ khỏi AP mất nguồn/reset state | HA, hardware, firmware, RF và mạng backhaul |
| Client liên kết được nhưng không có IP | Không phải triệu chứng đặc trưng của PMF | DHCP relay/snooping, VLAN, IP pool, NAC, firewall |
| Client báo “unsafe network” | Có thể liên quan chính sách bảo mật hoặc PMF | Certificate, security mode mismatch, SSID giả, user configuration |

### 10.3. Hướng xử lý khi thay policy gây gián đoạn

1. **Thu evidence trước khi đổi:** SSID, BSSID, AP, client model/OS/driver, security profile, MFPC/MFPR, session logs, timestamp.
2. **Kiểm tra nhóm chịu ảnh hưởng:** một model, toàn bộ IoT hay nhiều loại client? Có firmware upgrade khả thi không?
3. **Tái hiện trong lab hoặc SSID pilot:** xác nhận client có thể tham gia với PMF required, đúng cipher và xác thực.
4. **Đánh giá cách ly ngoại lệ:** nếu buộc phải giữ client cũ, chọn **SSID riêng/VLAN hẹp** có kiểm soát thay vì tắt PMF cho mọi client.
5. **Theo dõi sau thay đổi:** association success, auth time, roam latency, disconnect count, helpdesk tickets và security posture.
6. **Rollback có điều kiện:** chỉ áp dụng thay đổi đã đánh giá rủi ro, có chủ sở hữu và thời hạn; không biến ngoại lệ tạm thành mặc định vĩnh viễn.

## 11. Case study: cảnh báo deauthentication nhưng mạng CORP vẫn ổn định

### 11.1. Bối cảnh

Một doanh nghiệp quản lý SSID **CORP** dùng phương thức bảo mật phù hợp và đặt **PMF required**. Wireless IDS phát cảnh báo nhiều khung deauthentication có BSSID trông giống AP-CORP-07 trên kênh đang sử dụng. Helpdesk nhận một vài yêu cầu hỗ trợ kết nối nhưng không có bằng chứng rằng toàn bộ tầng Wi-Fi ngừng hoạt động.

Mục tiêu điều tra: **khung nào đang xuất hiện**, **thiết bị nào đã thương lượng PMF**, và **có client nào thực sự bị ngắt bởi khung không được xác thực không**.

### 11.2. Evidence giả định

| Evidence | Quan sát | Có thể suy ra | Chưa thể kết luận |
| --- | --- | --- | --- |
| **E1 – WLAN config** | SSID CORP đặt PMF required; policy revision ghi nhận trong change log | AP được cấu hình yêu cầu PMF | Chưa chứng minh mọi session đã negotiated |
| **E2 – Session log** | Client A hỗ trợ PMF và liên kết bảo mật đã hoàn tất | Client A có ngữ cảnh PMF hợp lệ | Chưa biết tác động của mọi frame được quan sát |
| **E3 – RF capture** | Có nhiều khung deauth không có bảo vệ hợp lệ, MAC nguồn trông giống BSSID AP | Khung đáng nghi, cần xem integrity/sequence và thời điểm | MAC trùng AP không chứng minh AP thật gửi |
| **E4 – Client/AP log** | Client A tiếp tục truyền data và không có deassociation event tương ứng | Chưa thấy khung nghi vấn làm ngắt Client A | Không chứng minh toàn bộ client khác an toàn |
| **E5 – RF metrics** | Channel utilization tăng nhưng RSSI của A ổn định | Có thể có tác động RF ở mức nào đó | Chưa đủ để kết luận jamming chủ đích |
| **E6 – Client B log** | Client B thuộc SSID legacy optional, mất kết nối cùng khoảng thời gian | Client B cần kiểm tra posture khác với A | Chưa chứng minh cảnh báo RF là nguyên nhân duy nhất |

**Nhận định có giới hạn:** evidence hỗ trợ việc client A đã dùng PMF và không bị ngắt bởi các khung nghi vấn trong khoảng quan sát. Client B không có điều kiện bảo vệ tương đương nên cần điều tra riêng. Không thể kết luận “đã chặn toàn bộ tấn công” hoặc “đã xảy ra xâm nhập ứng dụng” từ một báo cáo này.

### 11.3. Quy trình điều tra

1. **Định danh đúng session:** map SSID, BSSID, AP radio, MAC client, channel, thời gian và status PMF negotiation.
2. **Ghép khung và kết quả:** quan sát deauth/disassoc/action frames, Protected flag/cryptographic context và event session tại AP/client.
3. **Kiểm tra RF:** sử dụng metric channel utilization, interference, roaming, AP resets và frame loss để loại trừ nguyên nhân phi tấn công.
4. **Xem các WLAN khác:** SSID optional/legacy có client không PMF? Có sự cố chung DHCP/RADIUS/roaming không?
5. **Phân loại event:** suspicious management traffic, verified disconnect, confirmed misconfiguration hoặc inconclusive; ghi độ tin cậy.
6. **Ứng phó theo policy:** giữ PMF required cho CORP nếu kiểm thử xác nhận tương thích, xử lý legacy/rogue AP hoặc nhiễu trong phạm vi phù hợp, bổ sung monitoring.
7. **Bảo quản chứng cứ:** lưu log và capture có kiểm soát, che thông tin thiết bị/người dùng, ghi phương pháp thu thập và giới hạn sensor.

### 11.4. Mẫu báo cáo case học tập

~~~yaml
case_id: WLAN-PMF-009
title: "Unprotected deauthentication frames observed near managed SSID"
environment:
  ssid: "CORP"
  security_profile: "Enterprise with PMF required"
  ap_id: "AP-CORP-07"
  channel: "Observed from authorized RF sensor"
evidence:
  - id: "E-01"
    source: "WLC client session"
    finding: "Client A negotiated PMF"
  - id: "E-02"
    source: "Authorized 802.11 capture"
    finding: "Unprotected deauth-like frames near observed BSSID"
  - id: "E-03"
    source: "Client and AP event logs"
    finding: "No matching disconnect for Client A in time window"
  - id: "E-04"
    source: "RF health telemetry"
    finding: "Interference and roaming review pending"
conclusion: "No confirmed session disruption for Client A in inspected interval"
open_questions:
  - "Impact on non-PMF clients in nearby SSIDs"
  - "Source and intent of suspicious frames"
  - "Other RF or firmware-related causes"
owner: "Wireless Network Operations / SOC"
review_trigger: "Repeated events, client outage or WLAN policy change"
~~~

Đây là bản mô tả **giả định** để luyện cách trình bày evidence, không phải sự cố thật.

## 12. Chính sách PMF, change control và rollout

### 12.1. Mẫu yêu cầu kỹ thuật

~~~yaml
# Mẫu policy phục vụ review, không phải cú pháp cấu hình của hãng AP/WLC.
control_id: WLAN-PMF-009
objective: "Protect robust management frames for corporate clients"
service: "SECURITY_NETWORK_SECURITY"
scope:
  ssid: "CORP"
  ap_groups: ["Managed campus AP group"]
  client_groups: ["Managed laptops and smartphones"]
security:
  authentication: "Approved Enterprise profile"
  pmf_mode: "required"
  allowed_legacy_exception: "None on CORP"
  eap_server_validation: "Required for managed clients"
adjacent_controls:
  - "Approved AP and rogue AP monitoring"
  - "NAC and client identity"
  - "VLAN/role segmentation"
  - "Firewall and DNS egress policy"
  - "RF health and roaming monitoring"
validation:
  - "Compatible client associates and negotiates PMF"
  - "Unsupported client is rejected by required policy"
  - "Unprotected robust frame is not accepted as valid disconnect"
  - "Legitimate protected management operations still work"
  - "Roaming and 802.1X/SAE remain functional"
logging:
  - "WLAN profile revision and enforcement mode"
  - "Per-client negotiated security and PMF state"
  - "Association status, deauth/disassoc and RF events"
owner: "Wireless Network / Information Security"
review_trigger:
  - "AP/client firmware or security mode upgrade"
  - "New IoT onboarding or SSID policy change"
  - "New WIDS alert or unexpected disconnection trend"
~~~

### 12.2. Triển khai theo giai đoạn

1. **Inventory:** lập danh sách AP, WLC, SSID, model/driver client, chính sách WPA, hỗ trợ PMF và ứng dụng nhạy cảm với roaming.
2. **Baseline:** đo association success, roaming time, disconnect rate, RADIUS failures, số client đang không có PMF và vùng RF hay lỗi.
3. **Pilot:** bật required trên SSID thử nghiệm/nhóm AP và client được quản lý, xác nhận tương thích thực tế.
4. **Đánh giá legacy:** phân loại thiết bị không nâng cấp được, cô lập và đặt chính sách ngoại lệ có thời hạn.
5. **Triển khai có kiểm soát:** dùng maintenance window/rollback khi thay đổi ảnh hưởng lớn; đồng bộ profile giữa AP/controller.
6. **Kiểm chứng:** đo negotiated PMF theo client, success/failure, roaming, kết quả bảo vệ khung và ứng dụng sau association.
7. **Vận hành liên tục:** phát hiện AP rogue/SSID impersonation, giám sát disconnect bất thường, định kỳ rà soát chính sách optional và firmware.

**Không dùng “SSID vẫn phát beacon” hoặc “client thấy Wi-Fi” làm tiêu chí PMF thành công.** Bằng chứng cần ở **association/session bảo mật và kết quả thực tế**.

## 13. Bộ kiểm thử PMF có kiểm soát

Các kiểm thử sau áp dụng cho **lab cô lập, staging WLAN hoặc mạng có ủy quyền rõ**. Không tự ý phát frame giả mạo hoặc gây nhiễu ảnh hưởng người dùng ngoài phạm vi. Có thể xác minh một số test bằng capture/log có sẵn, simulator và chế độ kiểm thử của vendor mà không cần phát traffic nguy hiểm.

| Test | Điều kiện | Kỳ vọng | Evidence |
| --- | --- | --- | --- |
| **P1 – client tương thích** | SSID PMF required, client hỗ trợ PMF và security profile | Association/key establishment thành công, session có PMF | AP/WLC log, RSN IE, client status |
| **N1 – client không hỗ trợ** | Client thử nghiệm không có PMF kết nối SSID required | Association không được chấp nhận vì không đáp ứng yêu cầu | Status/reason code, AP log; không nhầm với lỗi password |
| **P2 – protected management hợp lệ** | AP thực hiện thao tác quản lý hợp lệ trong môi trường lab | Client/AP xử lý theo kết nối PMF và log đúng | Session log/capture có phạm vi, reason code |
| **N2 – unprotected robust frame** | Phân tích **offline trace/fixture** khung không có bảo vệ hợp lệ tới liên kết PMF | Engine/behavior theo tiêu chuẩn không coi khung này là lệnh ngắt tin cậy | Parser/test harness, event và session state |
| **P3 – roaming** | Client PMF đi giữa hai AP có cấu hình đúng | Roaming hoạt động, session mới dùng posture mong muốn | WLC roaming logs, auth time, connectivity |
| **P4 – WPA3-only** | Thiết bị tương thích kết nối profile WPA3-only | Xác thực và PMF phù hợp với profile | Connection details, AP security logs |
| **N3 – legacy isolation** | Client thiếu PMF thử vào CORP, sau đó dùng mạng legacy đã phê duyệt | CORP bảo vệ vẫn required; legacy bị giới hạn quyền | WLAN logs, VLAN/role, firewall tests |
| **O1 – giám sát** | Có khung deauth đáng ngờ trong PCAP đã được cấp quyền | SOC phân biệt alert với disconnect thành công và nêu giới hạn | RF log, client log, case ID |
| **P5 – nghiệp vụ** | Kết nối thành công, truy cập DNS/API/VPN hợp lệ | Không bị lỗi DHCP/DNS/firewall sau thay PMF policy | App synthetic test, DHCP/DNS/flow logs |
| **R1 – rollback** | Pilot phát hiện thiết bị cần hỗ trợ đặc biệt | Có khả năng phục hồi theo quy trình, không mở rộng ngoại lệ vô thời hạn | Ticket, policy revision, retest |

### 13.1. Acceptance criteria thực tế

Không nên chỉ đặt một ngưỡng “0 disconnect” vì roaming, reboot và nhiễu sóng hợp lệ vẫn xảy ra. Một bộ tiêu chí có thể là:

- **Tất cả client quản lý trong phạm vi CORP đều có PMF negotiated** khi policy bắt buộc, được kiểm tra từ session state.
- Client không đáp ứng required **bị từ chối có lý do rõ ràng**, không lén tham gia ở mode yếu hơn trên cùng policy.
- Tỷ lệ **association thành công, roaming latency, application availability** không suy giảm vượt giới hạn được đội vận hành chấp nhận.
- Alert management frames có **SSID/BSSID/channel/timestamp**, log AP/client tương ứng, không coi một cảnh báo là một cuộc tấn công thành công.
- Các ngoại lệ legacy được ghi **owner, phạm vi, controls bù và ngày rà soát**.

Nếu AP/WLC không hiển thị cờ negotiated PMF rõ ràng, cần tìm **phương pháp xác minh tương đương do vendor hỗ trợ**, chẳng hạn session diagnostics hoặc trace RSN; không suy ra “đã bảo vệ” chỉ từ trạng thái checkbox ở giao diện cấu hình.

## 14. Các sai lầm thường gặp

1. **“PMF mã hóa tất cả management frames.”** PMF cơ bản bảo vệ **robust management frames**, không phải mọi beacon, probe hay exchange ban đầu.
2. **“Có WPA2-AES tức chắc chắn đã có PMF.”** Bảo mật data frames và PMF negotiation là các thuộc tính khác nhau.
3. **“Bật PMF capable có nghĩa mọi client đều được bảo vệ.”** Optional cho phép client không PMF nếu profile cho phép; phải kiểm tra từng session.
4. **“Mạng WPA3/WPA2 transition bảo đảm mọi máy dùng WPA3.”** Một client có thể dùng WPA2 theo điều kiện transition; cần xem security mode thực tế.
5. **“PMF chống được mọi kiểu deauth DoS và RF jamming.”** PMF giảm giả mạo một số robust frames nhưng không khắc phục mất sóng/thiết bị lỗi.
6. **“PMF phát hiện mọi rogue AP/evil twin.”** Xác thực mạng, xác minh EAP server, profile SSID và WIDS/WIPS vẫn cần thiết.
7. **“MAC nguồn giống BSSID là bằng chứng AP thật gửi deauth.”** MAC address trong frame có thể bị giả mạo; phải xét bảo vệ mật mã và ngữ cảnh.
8. **“Nếu AP hỗ trợ PMF thì client chắc chắn hỗ trợ.”** Khả năng phụ thuộc model, OS, driver, firmware và profile.
9. **“Client không nối SSID required là đang bị tấn công.”** Có thể đơn giản là PMF/cipher không tương thích.
10. **“Capture Ethernet đủ xem deauth frame.”** Cần điểm quan sát 802.11 phù hợp, thường là monitor mode hoặc RF sensor.
11. **“BSSID hiện cùng SSID nghĩa cùng mức bảo mật.”** WLAN profile/firmware của các AP có thể khác; cần kiểm tra theo BSSID và session.
12. **“Tắt PMF sẽ sửa tất cả lỗi roaming.”** Nhiều lỗi đến từ RF, 802.1X, FT, DHCP hoặc controller; thay bảo mật có thể tạo rủi ro lớn hơn.
13. **“BIP bảo đảm tính bí mật của mọi khung broadcast management.”** BIP tập trung vào integrity/authenticity/replay cho khung nhóm phù hợp; không mặc định mã hóa nội dung.
14. **“Client có EAP authentication thành công là đã chống evil twin đầy đủ.”** Cần xác minh chứng chỉ EAP server và chính sách trust; PMF riêng không giải quyết bước nhận diện mạng giả.
15. **“Không có deauth frame thì không thể rớt Wi-Fi.”** AP reboot, RF interference, timeout hoặc lỗi phần mềm vẫn làm liên kết mất.
16. **“SSID guest bật PMF thì có thể bỏ client isolation.”** PMF không thay thế phân đoạn và quyền truy cập phía sau AP.

## 15. Bài tập vận dụng và gợi ý

### Bài 1 — Chọn PMF mode

Mạng CORP có 98% client hỗ trợ PMF, còn 2% là thiết bị scanner đời cũ. Đội vận hành đề xuất chuyển **toàn bộ CORP sang PMF optional** để scanner vẫn hoạt động. Phương án nào giúp giữ posture tốt hơn?

**Gợi ý:** xác minh scanner không thể nâng firmware; cân nhắc **SSID/VLAN riêng với quyền tối thiểu và kế hoạch thay thiết bị**, giữ PMF required trên CORP cho client tương thích. Nếu phải sử dụng ngoại lệ, ghi owner, thời hạn và test, không chấp nhận optional vĩnh viễn mà không đánh giá rủi ro.

### Bài 2 — Đọc khả năng RSN

Một AP quảng bá **MFPC=1, MFPR=1**. Client A có **MFPC=1** và client B không hỗ trợ PMF. Với các điều kiện xác thực/cipher khác tương thích, kết quả association dự kiến ra sao?

**Gợi ý:** AP có khả năng và yêu cầu PMF; A có thể đáp ứng yêu cầu, B không thể tham gia thành công vào policy required. Kết quả thực tế vẫn cần xem log và xác thực phù hợp.

### Bài 3 — Alert deauthentication chưa gây mất kết nối

Wireless IDS nhận nhiều khung deauth không có bảo vệ hợp lệ trong khi WLC xác nhận Client A **đã có PMF** và client tiếp tục gửi dữ liệu. Có thể báo “đã có khai thác thành công” không?

**Gợi ý:** không. Có dấu hiệu traffic quản lý đáng nghi; trong khoảng dữ liệu quan sát, chưa thấy Client A bị ngắt vì khung này. Nên đối chiếu capture, BSSID, thời gian, RF, session log và phạm vi các client không PMF trước khi kết luận.

### Bài 4 — Laptop mất mạng sau cập nhật controller

Sau khi bật required, một số laptop không vào được SSID, còn các máy mới vẫn kết nối. Hãy đề xuất tối thiểu năm thông tin cần thu thập trước khi rollback.

**Gợi ý:** model/driver/OS, SSID/BSSID/AP, WPA cipher và RSN MFPC/MFPR, association/status reason, WLC policy revision, 802.1X/SAE logs, kết quả trên AP khác, ảnh hưởng roaming và phiên firmware. Xác minh lỗi do PMF thay vì DHCP/DNS khi association đã thành công.

### Bài 5 — PMF và evil twin

Một kẻ xấu quảng bá SSID giống CORP. Thiết bị có hỗ trợ PMF đã an toàn tuyệt đối trước AP giả chưa?

**Gợi ý:** chưa. PMF không xác thực beacon ban đầu hay toàn bộ danh tính AP. Cần phương thức WPA phù hợp, xác minh chứng chỉ EAP/RADIUS trên client Enterprise, cấu hình mạng được quản lý và giám sát rogue AP; tránh profile chuyển xuống phương thức yếu ngoài ý muốn.

### Bài 6 — Lập ma trận threat → control → evidence

Cho mạng gồm **CORP, GUEST, IoT** và một số AP thuộc hai controller, hãy xác định:

- SSID nào có thể đặt **PMF required** ngay, SSID nào cần đánh giá legacy?
- Rủi ro nào PMF giải quyết, rủi ro nào cần **802.1X/NAC, VLAN, firewall, DNS protection, WIDS/WIPS**?
- Những nguồn log và capture nào chứng minh **PMF negotiated** và khung nghi vấn **có/không** làm ngắt session?
- Làm thế nào kiểm thử **roaming** mà không phát management frames trái phép vào mạng sản xuất?
- Khi một client không tương thích, phương án ngoại lệ nào có chủ sở hữu, phạm vi và thời hạn rõ ràng?

**Gợi ý:** dùng bảng so sánh thiết bị/SSID, cấu hình RSN và session log, rồi kiểm thử trên staging WLAN. Đánh giá cả **mức bảo vệ và khả dụng ứng dụng** sau khi đổi policy.

## 16. Checklist nhanh dành cho kiến trúc sư và người vận hành WLAN

| Câu hỏi cần trả lời | Bằng chứng mong đợi |
| --- | --- |
| Có kiểm kê khả năng PMF của AP và client chưa? | Inventory model, OS/driver/firmware và kết quả pilot |
| Chính sách PMF ở mỗi SSID là disabled, optional hay required? | Running WLAN profile/revision |
| AP quảng bá đúng RSN MFPC/MFPR chưa? | RSN IE từ trace/diagnostic được cấp quyền |
| Client có thật sự thương lượng PMF không? | AP/WLC per-client session security state |
| WPA2/WPA3 transition có làm yếu policy không? | Security mode và PMF negotiated theo client |
| Có legacy exception không và đã cô lập đủ chưa? | SSID/VLAN/role, firewall rules, owner và hạn rà soát |
| Sự kiện deauth/disassoc có đáng tin không? | Protected status, session context, AP/client logs và timeline |
| Có theo dõi lỗi roaming/802.1X/RF độc lập không? | RADIUS logs, roam timers, RSSI/SNR/channel metrics |
| Có bảo vệ chống evil twin ngoài PMF không? | Certificate policy, managed profiles, WIDS/WIPS rogue AP monitoring |
| Đổi policy có ảnh hưởng DHCP/DNS/API không? | Connectivity tests và flow/DNS logs sau association |
| Có rollback mà không tắt bảo mật toàn hệ thống không? | Change plan, pilot scope, SSID riêng cho ngoại lệ |

## 17. Tổng kết

**Management Frame Protection (PMF)** là lớp bảo vệ quan trọng cho **robust management frames** của 802.11, đặc biệt khi kẻ xấu cố giả mạo **deauthentication hoặc disassociation** nhằm làm gián đoạn phiên Wi-Fi đã có bảo vệ. PMF sử dụng cơ chế bảo vệ mật mã phù hợp với khóa phiên, hỗ trợ **kiểm tra tính toàn vẹn và chống phát lại**, cùng những thành phần như **BIP/IGTK và SA Query** trong các tình huống được chuẩn quy định.

Trong triển khai, phải phân biệt **AP có khả năng PMF**, **SSID yêu cầu PMF** và **một client thực sự đã thương lượng PMF**. WPA3 và mạng doanh nghiệp hiện đại giúp nâng posture, nhưng **optional/transition mode**, thiết bị IoT cũ, roaming và sự khác nhau giữa AP/controller có thể tạo khoảng trống. PMF cũng không thay thế chống nhiễu RF, xác thực chống evil twin, DHCP/DNS protection, phân đoạn và firewall.

Một kiến trúc **SECURITY_NETWORK_SECURITY** an toàn cần đặt PMF đúng ở **ranh giới vô tuyến**, kết hợp **NAC/802.1X, WPA3 hoặc WPA2-Enterprise phù hợp, chứng chỉ EAP được xác minh, segmentation, WIDS/WIPS, VPN/ZTNA khi cần và giám sát end-to-end**. Chỉ nên kết luận control hoạt động tốt sau khi đã **đọc kết quả thương lượng theo client, kiểm tra các robust frames phù hợp, đối chiếu RF/session evidence và chứng minh lưu lượng nghiệp vụ hợp lệ vẫn hoạt động**.

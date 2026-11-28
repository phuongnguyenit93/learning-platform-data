# Wireless encryption: Bảo vệ lưu lượng và danh tính trên mạng Wi-Fi

## 1. Wireless encryption là gì và bảo vệ được điều gì?

**Wireless encryption (mã hóa mạng không dây)** trong Wi-Fi là việc sử dụng các cơ chế mật mã của IEEE 802.11 và hệ sinh thái Wi-Fi để bảo vệ các khung dữ liệu truyền qua môi trường vô tuyến giữa **thiết bị khách (station/STA)** và **điểm truy cập (access point/AP)**. Sóng Wi-Fi lan truyền trong không gian, nên người ngoài phạm vi vật lý của một ổ cắm mạng vẫn có thể thu được tín hiệu nếu ở vùng phủ sóng. Điều này làm bảo vệ nội dung, tính toàn vẹn và quyền tham gia mạng trở nên đặc biệt quan trọng.

Ba mục tiêu cần phân biệt:

1. **Confidentiality:** người không có khóa phù hợp khó đọc được nội dung dữ liệu trên chặng vô tuyến.
2. **Integrity và chống phát lại:** phát hiện các thay đổi không được phép đối với dữ liệu được bảo vệ và sử dụng số thứ tự/packet number để hạn chế replay.
3. **Authentication / access control:** xác định thiết bị hoặc người dùng có quyền tham gia mạng hay không. Đây là chức năng liên quan mật thiết nhưng **không đồng nghĩa với mã hóa**.

Ví dụ, hai người dùng cùng kết nối một Wi-Fi công cộng không sử dụng bảo vệ đường truyền có nguy cơ bị người khác quan sát traffic không mã hóa ở chặng vô tuyến. Nếu website đã dùng HTTPS/TLS hợp lệ, phần nội dung ứng dụng được TLS bảo vệ độc lập với mã hóa Wi-Fi; tuy nhiên, điều đó **không thay thế** an toàn của hạ tầng wireless, chính sách phân đoạn, xác thực mạng và bảo vệ trước access point giả mạo.

Trong module **SECURITY_NETWORK_SECURITY**, chủ đề này liên hệ với **phòng vệ theo lớp**, bao gồm segmentation giữa khách/nhân viên/IoT, firewall và NAC, VPN, IDS/IPS/WIDS, DNS security, xác thực kết nối và vận hành cloud. Một mạng sử dụng WPA3 có thể bảo vệ đường vô tuyến tốt nhưng vẫn **không an toàn tổng thể** nếu khách Wi-Fi được route trực tiếp đến database hoặc người dùng bị lừa đăng nhập vào cổng giả.

**Sau bài học, người học có thể:**

- Phân biệt WEP, WPA/TKIP, WPA2-CCMP, WPA3-SAE, WPA3-Enterprise và OWE.
- Hiểu vai trò của SSID/BSSID, RSN, AKM, cipher suite, PMK/PTK/GTK và 4-way handshake ở mức kiến trúc.
- Giải thích tại sao **WPA2-Personal**, **WPA2/WPA3-Enterprise** và **Enhanced Open** có mô hình tin cậy khác nhau.
- Đánh giá lợi ích và giới hạn của **Protected Management Frames (PMF/802.11w)**.
- Thiết kế chính sách mã hóa theo đối tượng: nhân viên, khách, thiết bị BYOD và IoT.
- Xác minh an toàn cấu hình không dây bằng lệnh chỉ đọc, log và test kết nối trong môi trường được phép.

> **Nguyên tắc:** mã hóa vô tuyến chỉ bảo vệ một **chặng liên lạc**. Khi dữ liệu rời AP và đi qua LAN, VPN, Internet hoặc hệ thống dịch vụ, cần tiếp tục áp dụng TLS/mTLS, phân quyền, phân đoạn, giám sát và bảo vệ ứng dụng.

## 2. Vị trí bảo vệ của mã hóa Wi-Fi trong kiến trúc mạng

~~~mermaid
flowchart LR
    C["Laptop / điện thoại"] <-->|"Liên kết 802.11: WPA2/WPA3/OWE"| AP["Access point"]
    AP --> SW["Switch / VLAN"]
    SW --> FW["Segmentation firewall"]
    FW --> WEB["Web / API"]
    WEB --> DB["Database"]
    C -. "HTTPS / TLS end-to-end theo ứng dụng" .-> WEB
    AP -. "802.1X / RADIUS khi dùng Enterprise" .-> AA["AAA / RADIUS / PKI"]
~~~

Mã hóa Wi-Fi thường bảo vệ **khung dữ liệu trên chặng giữa client và AP**. AP giải mã/chuyển tiếp theo cách triển khai và sau đó dữ liệu đi vào hệ thống mạng phía sau. Khi người dùng roaming sang AP khác, hệ thống có thể dùng cơ chế roaming/key management phù hợp để duy trì trải nghiệm và tính bảo mật.

### 2.1. Thuật ngữ nền tảng

| Thuật ngữ | Ý nghĩa | Vì sao quan trọng? |
|---|---|---|
| **SSID** | Tên mạng Wi-Fi được quảng bá/cấu hình | Không phải bằng chứng danh tính AP; nhiều AP có thể cùng SSID |
| **BSSID** | Định danh thường là địa chỉ MAC của một basic service set/AP radio | Có thể quan sát AP cụ thể; MAC/BSSID có thể bị giả mạo |
| **STA / supplicant** | Thiết bị khách tham gia kết nối | Chứa thông tin cấu hình, chứng chỉ hoặc credential |
| **AP / authenticator** | Thiết bị cung cấp kết nối và điều phối cơ chế xác thực | Có thể liên hệ với RADIUS/AAA để xác minh quyền truy cập |
| **RSN** | Robust Security Network: tập cơ chế bảo vệ của 802.11 | Liên quan quảng bá AKM, cipher, PMF và thiết lập khóa |
| **AKM** | Authentication and Key Management suite | Xác định cách xác thực/thiết lập vật liệu khóa, ví dụ PSK, SAE, 802.1X |
| **Pairwise cipher** | Mật mã bảo vệ traffic unicast giữa STA và AP | Thường là CCMP hoặc GCMP ở cấu hình hiện đại |
| **Group cipher** | Mật mã bảo vệ một số khung multicast/broadcast gửi tới nhóm | Được quản lý bằng group key tương ứng |
| **PMF** | Protected Management Frames | Bảo vệ một tập khung quản lý robust; không chặn mọi hình thức gây nhiễu |
| **RADIUS / AAA** | Hạ tầng xác thực, phân quyền, ghi nhận truy cập | Dùng phổ biến trong WPA-Enterprise qua 802.1X |

**Không nhầm SSID với cơ chế bảo mật.** Hai SSID có tên khác nhau có thể dùng cùng một loại mật mã; một SSID có thể quảng bá các lựa chọn tương thích khác nhau, nhất là trong chế độ chuyển đổi WPA2/WPA3.

### 2.2. Các giai đoạn kết nối (mô hình đơn giản)

~~~mermaid
flowchart TD
    D["Tìm AP/SSID và khả năng RSN"] --> A["Association và chọn AKM/cipher"]
    A --> K["Xác thực / thiết lập khóa: PSK, SAE hoặc 802.1X"]
    K --> H["Trao đổi 4-way handshake khi áp dụng"]
    H --> E["Truyền khung dữ liệu được mã hóa và kiểm tra tính toàn vẹn"]
    E --> N["DHCP / DNS / routing / application TLS"]
~~~

Đây là sơ đồ học tập: trạng thái 802.11 thực tế có nhiều bước hơn, và các cơ chế như **OWE** có quy trình trao đổi khóa riêng. Đăng nhập web qua một **captive portal** sau khi có địa chỉ IP **không tương đương** xác thực mật mã ở lớp liên kết.

## 3. Lịch sử WEP, WPA và lý do phải loại bỏ cơ chế cũ

### 3.1. WEP: không đáp ứng an toàn hiện đại

**WEP (Wired Equivalent Privacy)** là cơ chế bảo vệ Wi-Fi đời đầu sử dụng RC4 và IV có giới hạn. Những yếu kém mang tính thiết kế trong quản lý khóa và bảo vệ tính toàn vẹn khiến WEP **không còn phù hợp** để bảo vệ mạng. Không dùng WEP chỉ vì một thiết bị cũ không hỗ trợ lựa chọn mới.

### 3.2. WPA thế hệ đầu và TKIP

**WPA (trước WPA2)** đưa vào **TKIP** để cải thiện một số vấn đề so với WEP trên phần cứng cũ. Tuy nhiên, TKIP kế thừa giới hạn và không phải lựa chọn mật mã mạnh phù hợp với thiết kế mạng hiện đại. Các chính sách Wi-Fi an toàn nên **tắt WEP, WPA/TKIP và những lựa chọn mixed legacy không cần thiết**.

### 3.3. WPA2 và WPA3

**WPA2** gắn liền với cơ chế bảo vệ mạnh hơn thông qua **AES-CCMP**, cùng hai mô hình xác thực phổ biến là Personal (PSK) và Enterprise (802.1X/EAP). **WPA3** bổ sung các yêu cầu và cơ chế hiện đại hơn, nổi bật là **SAE** ở Personal, yêu cầu PMF thích hợp và những bộ mật mã mạnh trong các chế độ chứng nhận tương ứng.

| Cơ chế | Xác thực / key management | Mức khuyến nghị |
|---|---|---|
| **Open truyền thống** | Không xác thực/mã hóa dữ liệu ở lớp Wi-Fi | Tránh với lưu lượng nhạy cảm; bảo vệ bổ sung bằng TLS và phân đoạn |
| **WEP** | Cơ chế đời đầu sử dụng khóa chung yếu | Không sử dụng |
| **WPA/TKIP** | Cơ chế tương thích đời cũ | Không sử dụng |
| **WPA2-Personal** | PSK, dùng AES-CCMP khi cấu hình hiện đại | Có thể phù hợp cho thiết bị cần tương thích, mật khẩu mạnh và phân đoạn |
| **WPA2-Enterprise** | 802.1X/EAP, thường dùng AES-CCMP | Phù hợp doanh nghiệp khi EAP và xác thực server được triển khai đúng |
| **WPA3-Personal** | SAE, bảo vệ liên kết hiện đại | Ưu tiên khi client/AP hỗ trợ đầy đủ |
| **WPA3-Enterprise** | 802.1X/EAP với yêu cầu bảo mật WPA3 | Ưu tiên cho WLAN tổ chức có hạ tầng AAA phù hợp |
| **WPA3-Enterprise 192-bit security mode** | Bộ yêu cầu mật mã mạnh hơn cho môi trường đặc biệt | Chọn nếu có yêu cầu và toàn bộ client/AP/AAA hỗ trợ |
| **Enhanced Open / OWE** | Thiết lập khóa cho mỗi kết nối, không yêu cầu mật khẩu người dùng | Phù hợp guest/open khi cần mã hóa đường vô tuyến nhưng không xác thực AP bằng chứng chỉ |

**Không dùng bảng này như “thang điểm một chiều”.** WPA2-Enterprise với EAP-TLS, xác thực certificate chặt và quản lý truy cập tốt có thể phù hợp hơn một SSID WPA3-Personal sử dụng mật khẩu chung được chia sẻ bừa bãi. Cần xét **bảo vệ mật mã, danh tính, thiết bị, đường mạng và vận hành** cùng nhau.

## 4. Mật mã dữ liệu: CCMP, GCMP và quản lý khóa

### 4.1. CCMP và GCMP

- **CCMP** sử dụng AES với chế độ bảo vệ phù hợp cơ chế 802.11 để cung cấp **mã hóa và xác thực tính toàn vẹn** của khung dữ liệu.
- **GCMP** sử dụng AES-GCM trong các bộ mật mã được hỗ trợ, cũng cung cấp bảo mật dữ liệu và xác thực tính toàn vẹn, với các biến thể về kích thước khóa và tag theo bộ tiêu chuẩn.

Cả hai đều cần **khóa phù hợp, nonce/packet number được quản lý đúng, chống replay và triển khai firmware/driver chính xác**. Không chọn cipher chỉ dựa trên tên “AES” vì mức an toàn còn phụ thuộc bộ giao thức, chính sách key management và lỗi triển khai.

### 4.2. Pairwise và group traffic

Traffic **unicast** từ STA tới AP hoặc ngược lại dùng khóa và trạng thái bảo vệ phù hợp với liên kết/peer. Traffic **multicast/broadcast** do AP gửi tới nhiều client có cơ chế dùng **group temporal key (GTK)**, nên cần quản lý group key và luân chuyển thành viên nhóm. Không nên nhầm group key với mật khẩu Wi-Fi chia sẻ cho người dùng.

### 4.3. Tại sao replay protection quan trọng?

Một attacker có thể thu một khung Wi-Fi đã mã hóa mà không đọc được payload. Nếu cơ chế nhận dữ liệu không kiểm tra tính hợp lệ của **packet number/replay state**, việc phát lại có thể gây hành vi không mong muốn. Các chế độ bảo vệ hiện đại kết hợp tính toàn vẹn và chống replay, nhưng vẫn phụ thuộc việc cấu hình và triển khai đúng.

**Khuyến nghị:** không bật cipher legacy để “sửa kết nối” khi lỗi thực nằm ở driver, association, certificate hay RADIUS. Kiểm tra các thông báo lỗi và khả năng hỗ trợ trước khi thay đổi chính sách mật mã.

## 5. WPA2-Personal: Pre-Shared Key

### 5.1. Nguyên lý

Trong **WPA2-Personal**, người dùng cung cấp một passphrase hoặc thông tin PSK cho SSID. Với cơ chế passphrase thông thường, vật liệu khóa gốc được tạo từ **passphrase và SSID**; sau đó quá trình thiết lập liên kết sử dụng các giá trị nonce, địa chỉ thiết bị và key derivation để tạo khóa phiên.

~~~mermaid
flowchart LR
    P["Passphrase + SSID"] --> PMK["Vật liệu khóa gốc / PMK"]
    PMK --> H["4-way handshake + nonces + peer addresses"]
    H --> PTK["Pairwise key material"]
    H --> GTK["Group key installation"]
    PTK --> C["Khung unicast được bảo vệ"]
~~~

4-way handshake chứng minh hai phía có vật liệu khóa phù hợp và thương lượng/thiết lập khóa phiên, **không truyền passphrase ở dạng rõ trong các khung bắt tay**.

### 5.2. Rủi ro chủ yếu

- **Mật khẩu yếu hoặc dễ đoán:** bản ghi bắt tay/metadata phù hợp có thể tạo điều kiện kiểm tra phỏng đoán mật khẩu **offline** đối với cơ chế PSK khi có đủ dữ liệu, không cần gửi nhiều lần đăng nhập đến AP.
- **Một mật khẩu dùng cho nhiều người:** khó thu hồi quyền của một cá nhân mà không đổi mật khẩu chung trên nhiều thiết bị.
- **Rò rỉ mật khẩu:** khách cũ, thiết bị bị mất hoặc người ngoài có mật khẩu có thể tham gia mạng cho đến khi có cơ chế thu hồi/đổi credential.
- **Khó gắn attribution:** chỉ một shared secret không cho biết rõ từng người dùng nào đã truy cập, dù vẫn có thể kết hợp identity/NAC/log bổ sung.
- **WPS thiếu kiểm soát:** các cách đơn giản hóa ghép nối, đặc biệt biến thể PIN hoặc cấu hình không an toàn, có thể tăng rủi ro; tổ chức nên tắt WPS khi không có nhu cầu và dùng onboarding có kiểm soát.

### 5.3. Khi nào WPA2-Personal còn có thể chấp nhận?

Một WLAN nhỏ, thiết bị legacy không hỗ trợ WPA3 hoặc không có PKI/AAA có thể cần WPA2-Personal với **AES-CCMP only**, passphrase ngẫu nhiên dài, phạm vi người biết hạn chế, cập nhật firmware và **segmentation**. Không nên dùng cùng mật khẩu này cho Wi-Fi nhân viên, IoT và khách.

Nếu tổ chức có nhiều người hoặc yêu cầu thu hồi quyền theo cá nhân, cân nhắc **Enterprise/802.1X** thay vì tiếp tục chia sẻ PSK.

## 6. WPA2-Enterprise và xác thực 802.1X/EAP

### 6.1. Mô hình ba thành phần

**WPA2-Enterprise** thường kết hợp chuẩn **IEEE 802.1X** với một phương pháp **EAP (Extensible Authentication Protocol)**. Ba vai trò chính là:

- **Supplicant:** phần mềm trên laptop/thiết bị có credential hoặc chứng chỉ.
- **Authenticator:** AP hoặc controller quản lý truy cập đường Wi-Fi, chuyển thông điệp xác thực và chỉ cho traffic phù hợp sau khi thành công.
- **Authentication server:** dịch vụ AAA/RADIUS phối hợp với hệ thống danh tính và chính sách truy cập.

~~~mermaid
sequenceDiagram
    participant S as Client / Supplicant
    participant A as AP / Authenticator
    participant R as RADIUS / AAA
    S->>A: Kết nối và bắt đầu 802.1X/EAP
    A->>R: Chuyển tiếp thông tin EAP theo cơ chế AAA
    R-->>A: EAP challenge / yêu cầu tiếp theo
    A-->>S: Chuyển thông điệp EAP
    S->>A: Phản hồi EAP / chứng chỉ nếu EAP-TLS
    A->>R: Chuyển tiếp phản hồi
    R-->>A: Thành công / thất bại + chính sách và vật liệu khóa khi phù hợp
    A-->>S: Kết quả xác thực
    S->>A: 4-way handshake và thiết lập khóa link
    A-->>S: Kết nối dữ liệu theo chính sách
~~~

Sơ đồ đơn giản hóa nhiều vòng trao đổi EAP và thủ tục RADIUS. **Mật khẩu tài khoản hoặc private key không được gửi tùy tiện cho AP** chỉ vì AP làm authenticator. Việc bảo vệ vật liệu khóa và kênh AAA là trách nhiệm riêng trong thiết kế hệ thống.

### 6.2. EAP-TLS và xác thực hai phía

**EAP-TLS** sử dụng TLS trong EAP, thường triển khai với **chứng chỉ phía client và xác thực chứng chỉ phía authentication server**. Khi triển khai đúng:

- Thiết bị xác minh server đang sở hữu chứng chỉ hợp lệ thuộc CA và **tên server/identity mong đợi**.
- Authentication server kiểm tra chứng chỉ client, hạn dùng, chuỗi tin cậy và chính sách gắn với người dùng/thiết bị.
- Hệ thống có thể quản lý cấp, gia hạn và thu hồi credential **theo từng thiết bị/người dùng**.
- Không phải phân phát một mật khẩu Wi-Fi chung cho toàn bộ nhân viên.

**Giới hạn:** có chứng chỉ không có nghĩa là “an toàn tự động”. Nếu client chấp nhận bất kỳ CA hoặc server name nào, hoặc private key bị lộ, lớp xác thực vẫn có thể bị tấn công. Cần thiết kế PKI, enrollment, revocation, kiểm tra trạng thái chứng chỉ và chính sách cho thiết bị không được quản lý.

### 6.3. Các kiểu EAP khác

Một số mạng dùng phương pháp dựa trên username/password được bảo vệ trong một tunnel TLS, chẳng hạn PEAP. Mức an toàn phụ thuộc **EAP method, chuẩn giao thức, chính sách credential và đặc biệt việc xác thực chứng chỉ server**. Không khuyến khích bỏ bước server certificate validation chỉ để người dùng kết nối nhanh hơn.

**WPA2-Enterprise + EAP-TLS** có thể đem lại quản trị danh tính tốt hơn **WPA3-Personal dùng chung passphrase**, dù WPA3-Personal có cải tiến mật mã ở phương pháp xác thực Personal. Cần đánh giá cả **khả năng xác thực danh tính và bảo vệ liên kết**, không dùng tên phiên bản WPA như tiêu chí duy nhất.

### 6.4. Bảo vệ đường AP–AAA

Xác thực người dùng qua EAP không có nghĩa đường **RADIUS/AAA** đương nhiên được bảo vệ bằng TLS từ đầu đến cuối. Cần kiểm tra phương thức bảo vệ các thông điệp, phân đoạn mạng quản trị, quyền truy cập RADIUS, shared secrets hoặc **RADIUS over TLS** khi kiến trúc hỗ trợ, lưu lượng vận hành và khả năng HA.

Khi AAA mất kết nối, tổ chức phải có chính sách rõ: từ chối thiết bị chưa được xác thực, cơ chế duy trì phiên đã có và xử lý guest/IoT. **Không tự động chuyển về SSID mở hoặc bỏ xác thực** để chữa sự cố.

## 7. WPA3-Personal: SAE thay thế cách xác thực PSK truyền thống

### 7.1. SAE là gì?

**SAE (Simultaneous Authentication of Equals)** là phương thức thiết lập khóa dựa trên mật khẩu, dùng trong **WPA3-Personal**. Thay vì dùng đúng cơ chế PSK truyền thống của WPA2-Personal, SAE có trao đổi mật mã nhằm xác nhận các bên chia sẻ thông tin bí mật phù hợp và tạo vật liệu khóa riêng cho phiên.

Những cải thiện đáng chú ý:

- **Hạn chế khả năng phỏng đoán mật khẩu offline từ việc chỉ ghi lại một trao đổi xác thực** theo mô hình mật mã của SAE, khác với rủi ro phổ biến của WPA2-PSK yếu.
- **Forward secrecy** trong phạm vi các giả định và triển khai SAE phù hợp: việc biết mật khẩu sau đó không mặc nhiên đủ để giải mã traffic cũ đã được bảo vệ bằng khóa phiên riêng.
- Không bắt buộc chia sẻ một key derivation cố định giữa mọi kết nối theo cách WPA2-PSK truyền thống.
- Khi triển khai WPA3 đúng chuẩn, PMF là một phần quan trọng của yêu cầu bảo vệ.

**Không có nghĩa:** SAE làm mật khẩu yếu trở nên chấp nhận được, bảo vệ hoàn toàn nếu AP/client bị xâm phạm, tự xác thực danh tính doanh nghiệp hay phòng chống mọi rogue AP/phishing. Nếu một người khác biết mật khẩu, họ vẫn có thể **cố gắng tham gia SSID** như người dùng được cấp mật khẩu. Nên tiếp tục dùng passphrase dài, ngẫu nhiên và phân đoạn theo vai trò.

### 7.2. WPA2-PSK và WPA3-SAE khác nhau thế nào?

| Tiêu chí | WPA2-Personal PSK | WPA3-Personal SAE |
|---|---|---|
| Thiết lập vật liệu khóa gốc | Passphrase/PSK được sử dụng theo cơ chế PSK | Password-authenticated key exchange qua SAE |
| Rủi ro password guessing từ dữ liệu ghi lại | PSK yếu có nguy cơ đoán offline khi có dữ liệu trao đổi phù hợp | SAE được thiết kế để chống kiểu đoán offline thụ động đó |
| Forward secrecy | Không có cùng thuộc tính forward secrecy của SAE | Có thuộc tính bảo vệ phiên cũ theo mô hình SAE đúng |
| PMF | Tùy hỗ trợ/chính sách, có thể optional | Yêu cầu trong chế độ WPA3 phù hợp |
| Khả năng tương thích | Rộng với thiết bị đời cũ | Cần client, driver, firmware và AP hỗ trợ SAE |
| Quyền truy cập theo danh tính cá nhân | Không phải bản chất của PSK chia sẻ | Không phải bản chất của mật khẩu Personal |

### 7.3. Vì sao transition mode cần cẩn trọng?

Một SSID có thể bật **WPA2/WPA3 transition mode** để phục vụ cả client chỉ biết PSK và client hỗ trợ SAE. Đây là giải pháp di chuyển nhưng **không biến toàn SSID thành WPA3-only**:

- Một số client cũ có thể tiếp tục dùng **WPA2-PSK** và chịu rủi ro tương ứng.
- Khả năng thương lượng/nhận diện chuẩn của client và AP phải được xác minh, tránh hạ mức bảo vệ ngoài ý định.
- PMF và cipher negotiation cần được kiểm tra thực tế theo từng loại client.
- Không để transition mode vô thời hạn nếu yêu cầu bảo mật cần WPA3-only.

Tốt hơn nên dùng **danh mục thiết bị hỗ trợ, rollout theo nhóm và chính sách kết thúc giai đoạn tương thích**, thay vì chỉ đổi tên cấu hình rồi coi nhiệm vụ nâng cấp đã hoàn tất.

## 8. WPA3-Enterprise và chế độ 192-bit

**WPA3-Enterprise** kế thừa mô hình xác thực theo danh tính với 802.1X/EAP và bổ sung các yêu cầu bảo vệ Wi-Fi của thế hệ WPA3. Hệ thống vẫn phải quản lý chính xác chứng chỉ server, EAP method, credential, RADIUS/AAA và các phiên roaming.

**WPA3-Enterprise 192-bit security mode** là một hồ sơ bảo mật riêng với các yêu cầu mật mã/khóa mạnh hơn, phù hợp môi trường có yêu cầu đảm bảo cao. Không phải mọi mạng được gắn nhãn “WPA3-Enterprise” đều chạy chế độ 192-bit. Muốn sử dụng cần kiểm tra khả năng tương thích **toàn bộ AP, client, driver, authentication server và chứng chỉ/bộ thuật toán** theo hồ sơ được chọn.

### 8.1. Nên chọn phương án nào cho tổ chức?

| Nhu cầu | Lựa chọn thường phù hợp | Cần kiểm soát thêm |
|---|---|---|
| Nhân viên với laptop được quản lý | WPA2/WPA3-Enterprise + EAP-TLS theo khả năng hỗ trợ | PKI, enrollment, revocation, MDM, RADIUS HA |
| Tổ chức yêu cầu cấu hình WPA3 nghiêm ngặt | WPA3-Enterprise với PMF và bộ mật mã phù hợp | Khả năng hỗ trợ toàn client, chính sách roaming, audit |
| Hệ thống có yêu cầu mật mã nâng cao | WPA3-Enterprise 192-bit mode nếu được hỗ trợ đầy đủ | Hồ sơ cryptographic suite end-to-end và vận hành PKI |
| Nhóm nhỏ thiếu AAA nhưng thiết bị hiện đại | WPA3-Personal SAE | Passphrase ngẫu nhiên mạnh, giới hạn phạm vi chia sẻ |
| Thiết bị không hỗ trợ WPA3 nhưng vẫn cần | WPA2-Enterprise/Personal dùng AES-CCMP | Phân đoạn và kế hoạch thay thế thiết bị |

Không nên “nâng cấp” bằng cách bật WPA3-Enterprise 192-bit mà thiếu kiểm tra khả năng EAP/certificate hoặc khiến một nhóm thiết bị quan trọng bị ngắt kết nối hàng loạt.

## 9. Enhanced Open / OWE: mã hóa không đồng nghĩa xác thực

### 9.1. OWE là gì?

**Opportunistic Wireless Encryption (OWE)**, được dùng cho **Wi-Fi Enhanced Open**, giúp tạo khóa bảo vệ dữ liệu của từng liên kết mà **không yêu cầu người dùng nhập mật khẩu Wi-Fi**. Nó giảm rủi ro người quan sát thụ động thu đọc trực tiếp traffic vô tuyến của người khác so với open Wi-Fi truyền thống.

**Giới hạn quan trọng:** OWE **không xác thực danh tính AP** bằng cơ chế cấp chứng chỉ như EAP-TLS; vì vậy, một mạng OWE không tự phòng chống kẻ giả danh điểm truy cập hoặc cuộc tấn công chủ động kiểu man-in-the-middle. Dữ liệu ứng dụng nhạy cảm vẫn cần HTTPS/TLS hợp lệ, còn mạng khách vẫn cần phân đoạn và chính sách truy cập riêng.

~~~mermaid
flowchart LR
    G["Guest device"] <-->|"OWE: encrypted Wi-Fi link"| A["Guest AP"]
    A --> FW["Guest firewall / isolation"]
    FW --> I["Internet"]
    G -. "TLS để bảo vệ ứng dụng" .-> I
    R["Rogue AP"] -. "OWE không tự xác thực AP như PKI" .-> G
~~~

### 9.2. Open, captive portal và OWE

| Kiểu mạng | Bảo vệ đường vô tuyến | Xác thực ở lớp Wi-Fi | Ghi nhớ |
|---|---|---|---|
| Open truyền thống | Không mã hóa dữ liệu link theo WPA/OWE | Không | TLS ứng dụng và guest isolation càng quan trọng |
| Open + captive portal | Thường vẫn không mã hóa link trước/sau portal nếu là open truyền thống | Portal là lớp kiểm soát ứng dụng, không thay thế 802.11 link security | Đừng nhầm trang đăng nhập với WPA |
| Enhanced Open / OWE | Mã hóa riêng mỗi liên kết theo OWE | Không có xác thực AP/người dùng như EAP-TLS | Bảo vệ tốt hơn trước nghe lén thụ động, vẫn cần TLS |
| WPA3-Personal | Mã hóa link với SAE và bộ mật mã phù hợp | Xác thực qua mật khẩu dùng chung | Ai biết mật khẩu có thể tham gia, không tự định danh cá nhân |
| WPA-Enterprise EAP-TLS | Mã hóa link và xác thực danh tính bằng chứng chỉ phù hợp | Có, khi PKI được triển khai đúng | Phù hợp chính sách doanh nghiệp |

### 9.3. OWE transition

Một số môi trường quảng bá **OWE transition** để tương thích thiết bị chỉ hỗ trợ open Wi-Fi. Cần hiểu rằng một thiết bị đời cũ vẫn có thể kết nối qua **mạng open không mã hóa**, nên trải nghiệm và bảo vệ không giống OWE-only. Với mạng khách mới hỗ trợ đầy đủ, cân nhắc OWE-only và công bố rõ yêu cầu client.

## 10. Protected Management Frames (PMF / 802.11w)

### 10.1. PMF bảo vệ những gì?

Trước đây, một số **khung quản lý 802.11** không được bảo vệ theo cách tương tự khung dữ liệu, làm tăng rủi ro giả mạo một số thông điệp điều khiển. **PMF** bổ sung bảo vệ tính toàn vẹn/nguồn gốc đối với **những robust management frames thuộc phạm vi**, trong đó có các khung **deauthentication và disassociation** khi bảo vệ đã được thương lượng/thiết lập phù hợp.

PMF giúp giảm tác động của một số hành vi giả mạo thông điệp quản lý ở những thiết bị hỗ trợ. Nhưng:

- **Không bảo vệ tất cả management/control frames** trong mọi giai đoạn.
- **Không ngăn radio jamming** hoặc một thiết bị gây nhiễu vật lý.
- **Không thay thế** WPA authentication, certificate validation hay phân đoạn mạng.
- **Không bảo đảm** người dùng không thể bị lừa chọn AP giả qua SSID trùng tên.

### 10.2. Optional, capable và required

Một AP có thể công bố chính sách PMF tùy chế độ và khả năng hỗ trợ: **capable/optional** hoặc **required**. Khi PMF required, client không hỗ trợ sẽ không thể tham gia theo cách thông thường. Khi optional, có thể có client sử dụng hoặc không sử dụng PMF.

Ở **WPA3** đúng chế độ chứng nhận, PMF là yêu cầu quan trọng; nhưng trong **transition mode**, phải xác minh **cấu hình cho từng kết nối** thay vì giả định mọi client đều đang sử dụng PMF do thấy tên WPA3 trong giao diện AP.

### 10.3. Vận hành và kiểm thử PMF

Đội vận hành nên thu:

- Tỷ lệ client hỗ trợ và đã thương lượng PMF.
- Bản ghi association failures do PMF mismatch.
- Firmware/driver phiên bản thiết bị không kết nối được khi PMF required.
- Sự kiện deauth/disassoc theo thời gian và theo AP/BSSID.
- Dấu hiệu **gây nhiễu RF, roaming hoặc signal yếu** để không nhầm mọi ngắt kết nối thành tấn công.

Không cố tình gửi hàng loạt khung deauth hoặc thực hiện gây nhiễu để thử PMF ở mạng đang hoạt động. Thay vào đó, dùng **các phép thử đã được nhà sản xuất hỗ trợ hoặc lab cô lập được phê duyệt**, kiểm tra kết quả thương lượng và log.

## 11. Handshake, khóa phiên và lifecycle

### 11.1. PMK, PTK và GTK

Trong các mô hình RSN phổ biến, cần hiểu các thành phần:

- **PMK (Pairwise Master Key):** vật liệu khóa làm đầu vào cho việc thiết lập khóa liên kết, hình thành từ PSK/SAE hoặc quy trình xác thực Enterprise tương ứng.
- **PTK (Pairwise Transient Key):** vật liệu khóa theo cặp cho phiên STA–AP, được tạo thông qua thông tin và quá trình trao đổi phù hợp.
- **GTK (Group Temporal Key):** khóa được AP phân phối/bảo vệ để client nhận khung group-addressed từ AP.
- **IGTK (Integrity Group Temporal Key):** liên quan bảo vệ tính toàn vẹn một số robust group-addressed management frames khi PMF áp dụng.

Trong cấu hình RSN điển hình, **4-way handshake** dùng PMK và những giá trị trao đổi (nonce) để xác lập khả năng sở hữu keying material và cài đặt khóa liên kết. Việc diễn giải chính xác thuật toán và key hierarchy phụ thuộc AKM/cipher đã chọn. **Không chia sẻ hoặc ghi log key material ở dạng rõ** để chẩn đoán sự cố.

### 11.2. 4-way handshake ở mức khái niệm

~~~mermaid
sequenceDiagram
    participant A as AP
    participant C as Client
    Note over A,C: Hai bên đã có cơ sở keying material phù hợp
    A->>C: Thông tin handshake và nonce từ AP
    C->>A: Nonce từ client + xác thực thông điệp
    A->>C: Xác nhận và vật liệu group key được bảo vệ khi phù hợp
    C->>A: Xác nhận cài đặt / hoàn thành
    Note over A,C: Dùng khóa liên kết để bảo vệ dữ liệu sau đó
~~~

Trình tự này phục vụ học tập; không thay thế đặc tả giao thức. Những lỗi triển khai trong **quản lý cài đặt lại khóa/replay** đã từng dẫn tới lỗ hổng nghiêm trọng; vì thế cập nhật firmware, driver và hệ điều hành là một phần của bảo mật mã hóa, không chỉ chọn đúng tên WPA.

### 11.3. Roaming và tái sử dụng keying material

Trong doanh nghiệp có nhiều AP cùng SSID, client roaming giữa AP có thể sử dụng các cơ chế tối ưu xác thực/khóa như **PMK caching hoặc 802.11r Fast Transition**, nếu được thiết kế và hỗ trợ phù hợp. Mục đích là giảm gián đoạn ứng dụng thoại/video khi di chuyển.

**Đánh đổi:** cơ chế roaming cần đảm bảo **ràng buộc đúng miền tin cậy, chính sách bảo vệ management frames, khóa và firmware**. Không kích hoạt mọi tùy chọn roaming cho toàn bộ thiết bị IoT cũ nếu chưa thử tương thích và đánh giá security posture.

### 11.4. Rekey và thu hồi truy cập

Đổi group key theo chính sách và quản lý phiên giúp giới hạn một số rủi ro của key lifecycle, nhưng **không đồng nghĩa đã thu hồi một người biết PSK chung**. Với Personal, muốn thu hồi quyền người cũ thường cần đổi mật khẩu và cập nhật các thiết bị được phép. Với Enterprise, có thể thu hồi cert/account riêng, đồng thời quản lý **session hiện tại, cache và thời điểm thực thi chính sách**; việc disable account không nhất thiết cắt ngay mọi session đã được kết nối.

## 12. Threat modeling: mã hóa Wi-Fi không giải quyết mọi rủi ro

### 12.1. Tài sản và ranh giới tin cậy

Các tài sản cần bảo vệ gồm **dữ liệu trên không trung, tài khoản và private key, laptop và IoT, AP/controller, RADIUS/AAA, PKI, các VLAN nội bộ, DNS và mạng quản trị**. Ranh giới tin cậy không kết thúc ở sóng vô tuyến: sau AP còn có switch, gateway, firewall, Internet và hệ thống ứng dụng.

Ví dụ một thiết bị thấy SSID `CORP` ở nơi làm việc. Một AP không được quản lý có thể quảng bá cùng SSID, vì **tên mạng không phải bằng chứng danh tính**. Với EAP-TLS và cấu hình client kiểm tra đúng CA cùng tên authentication server, AP/server giả không thể dễ dàng đáp ứng yêu cầu xác thực. Nếu người dùng được phép bỏ qua cảnh báo chứng chỉ, lợi ích này suy giảm nghiêm trọng.

### 12.2. Các tình huống cần phân tích

| Tình huống | Rủi ro | Biện pháp giảm thiểu | Giới hạn |
|---|---|---|---|
| Nghe lén thụ động | Quan sát traffic không được mã hóa | WPA2-CCMP, WPA3, OWE; TLS ứng dụng | Metadata và traffic sau AP có thể vẫn bị quan sát |
| WPA2-PSK yếu | Phỏng đoán credential từ dữ liệu phù hợp | Mật khẩu ngẫu nhiên mạnh; SAE hoặc Enterprise | Shared password vẫn khó thu hồi từng người |
| Evil twin / rogue AP | Dụ client chọn AP giả | EAP-TLS, pin CA/server name, MDM, WIDS | SSID và BSSID có thể bị giả mạo |
| Server EAP giả | Lừa thiết bị chấp nhận danh tính sai | Kiểm tra chuỗi chứng chỉ và tên server bắt buộc | Cấu hình client sai làm vô hiệu hóa bảo vệ |
| Deauth/disassoc giả | Ngắt một số phiên Wi-Fi | PMF required khi client hỗ trợ | Không chặn mọi RF jamming |
| Gây nhiễu vô tuyến | Cản trở tính sẵn sàng | Khảo sát RF, thiết kế kênh, dự phòng | Mã hóa không giải quyết việc gây nhiễu |
| Mất thiết bị có credential | Truy cập mạng trái phép bằng credential còn hiệu lực | MDM, certificate riêng, revocation, NAC | Cần xét phiên hiện có và thời gian thu hồi |
| Rogue AP nối vào LAN | Mở điểm truy cập ngoài chính sách | NAC, switch port security, phát hiện AP lạ | WPA ở SSID hợp lệ không bảo vệ mọi cổng LAN |
| Can thiệp sau AP | Quan sát/sửa lưu lượng ở wired/Internet | HTTPS/mTLS, DNS protection, firewall | Link encryption không phải end-to-end |
| WPA transition cấu hình sai | Client dùng chế độ yếu hơn dự định | Kiểm tra negotiated AKM/cipher/PMF; lộ trình WPA3-only | Một số client legacy không tương thích |
| Lỗi driver/firmware | Hỏng bảo vệ khóa/handshake | Patch, firmware inventory, vendor advisories | Một profile WPA đúng vẫn có thể chứa lỗi triển khai |

### 12.3. Vì sao hidden SSID và MAC filtering không thay thế mã hóa?

**Ẩn SSID** không tạo ra một bí mật mật mã; thông tin tên mạng có thể xuất hiện trong trao đổi kết nối hoặc từ thiết bị đã biết mạng. **MAC allowlist** có thể hỗ trợ inventory và chính sách phụ nhưng MAC có thể bị thay đổi/giả mạo, và nhiều thiết bị hiện đại còn dùng **MAC randomization** để bảo vệ riêng tư.

Không sử dụng “hidden SSID + MAC filter” để thay cho WPA2/WPA3, EAP-TLS hoặc phân đoạn mạng.

## 13. Kiến trúc nhiều lớp cho CORP, GUEST, IoT và MGMT

| WLAN | Phương án bảo vệ | Mục tiêu truy cập | Kiểm soát mạng bổ sung |
|---|---|---|---|
| **CORP** | WPA3-Enterprise hoặc WPA2-Enterprise EAP-TLS phù hợp client | Nhân viên/thiết bị quản lý vào ứng dụng được duyệt | NAC, MDM, VLAN/role, firewall, PKI, RADIUS HA |
| **GUEST** | OWE nếu thiết bị hỗ trợ; hoặc chế độ guest được duyệt | Internet, dịch vụ công khai | Client isolation, chặn LAN nội bộ, captive portal nếu cần |
| **IoT** | WPA3-Personal hoặc WPA2-AES-CCMP legacy khi buộc phải dùng | Chỉ IoT controller/broker/endpoint | VLAN riêng, allowlist, device inventory, lịch thay credential |
| **MGMT** | Ưu tiên mạng quản trị được cô lập; nếu phải dùng Wi-Fi thì xác thực Enterprise mạnh | Quản trị AP/controller | Bastion, MFA, RBAC, ACL, logging, tách đường quản trị |

~~~mermaid
flowchart TD
    E["Nhân viên"] --> C["CORP / Enterprise EAP-TLS"]
    G["Khách"] --> W["GUEST / OWE hoặc guest policy"]
    I["IoT"] --> T["IOT / SSID riêng"]
    C --> R["AAA/RADIUS + PKI"]
    C --> VC["CORP VLAN / role"]
    W --> VG["GUEST VLAN"]
    T --> VI["IOT VLAN"]
    VC --> F["Firewall / microsegmentation"]
    VG --> F
    VI --> F
    F --> A["Ứng dụng theo allowlist"]
    F --> N["Internet"]
    VG -. "DENY tới tài sản nội bộ" .-> A
~~~

Sơ đồ mô tả chính sách mong muốn; chỉ có **kết quả kiểm thử luồng thực từ từng mạng** mới xác nhận segmentation được áp dụng. Một SSID đặt tên `GUEST` không tự bảo đảm guest bị chặn đến DATA.

### 13.1. Client isolation

Client isolation của một WLAN có thể ngăn một số thiết bị cùng mạng Wi-Fi liên lạc trực tiếp với nhau, nhưng hiệu lực phụ thuộc topology và AP/controller. Nó **không thay thế** firewall giữa các VLAN/zone hoặc bảo vệ các đường đi vòng khác.

### 13.2. Các dịch vụ phụ thuộc

Enterprise WLAN cần **RADIUS/AAA, PKI/CA, DNS, DHCP, NTP, directory, MDM và đôi khi cloud controller**. Một AP cấu hình WPA3 đúng vẫn không xác thực được client nếu RADIUS mất kết nối, certificate hết hạn hoặc thời gian thiết bị sai. Cần giám sát sức khỏe và đường mạng tới các thành phần phụ thuộc, có phương án hoạt động khi hệ thống xác thực lỗi mà **không tự hạ xuống SSID mở**.

## 14. Chọn cấu hình và tương thích thiết bị

### 14.1. Ma trận quyết định

| Câu hỏi | Hướng xử lý |
|---|---|
| Client/AP hỗ trợ WPA3 đầy đủ? | Ưu tiên WPA3 đúng mô hình xác thực; thử firmware/driver |
| Có PKI/AAA và cần thu hồi quyền theo cá nhân? | Ưu tiên Enterprise EAP-TLS cho CORP |
| Thiết bị cũ chỉ hỗ trợ WPA2? | Khoanh vào SSID/phân đoạn riêng dùng AES-CCMP, có kế hoạch thay thế |
| Mạng khách không dùng mật khẩu? | Cân nhắc OWE, không đồng nhất với xác thực AP |
| Có WPA2/WPA3 transition? | Có thời hạn, xác minh negotiated AKM và PMF của từng nhóm client |
| Cần bảo vệ management frames? | PMF required khi cấu hình và thiết bị cho phép |
| Có ứng dụng nhạy cảm? | Duy trì TLS/mTLS, DNS security, firewall, identity và monitoring |

### 14.2. 6 GHz và thế hệ radio mới

Hệ sinh thái **Wi-Fi 6E trên băng 6 GHz** sử dụng yêu cầu bảo mật hiện đại, bao gồm **WPA3 hoặc Enhanced Open/OWE và PMF** theo chế độ triển khai/chứng nhận; không thể đơn giản đem một SSID WPA2-Personal legacy lên 6 GHz. Cần xác minh năng lực từng radio, AP, driver và quy định của nhà cung cấp.

**Wi-Fi 6, 6E hay Wi-Fi 7 là chỉ dấu thế hệ kết nối, không phải bằng chứng thiết bị đang thương lượng WPA3**. Với mạng dual-band/multi-band, cần xem AKM/cipher/PMF hiệu lực cho mỗi phiên.

### 14.3. WPS và onboarding

Trên WLAN tổ chức, nên **tắt WPS nếu không dùng**, đặc biệt các chế độ ghép nối thiếu kiểm soát. Ưu tiên provisioning bởi MDM, hồ sơ Enterprise, PKI và hệ thống quản lý bí mật. Không gửi PSK/private key ở dạng rõ qua ticket hoặc chat hỗ trợ.

## 15. Quy trình triển khai Wireless Encryption an toàn

1. **Inventory:** kiểm kê AP, SSID, radio, client OS/driver, loại cipher/AKM/PMF hiện dùng, firmware và nhóm IoT legacy.
2. **Phân loại:** gắn owner, độ nhạy dữ liệu và tài sản cần truy cập cho nhân viên, khách, IoT, thiết bị quản trị.
3. **Security policy:** xác định WPA2/WPA3, 802.1X, EAP, PKI, danh tính RADIUS, PMF, guest policy và lộ trình loại bỏ WEP/TKIP.
4. **AAA và segmentation:** dựng RADIUS redundancy, CA/server cert, cấp cert client, DNS/DHCP/NTP, vai trò/VLAN và firewall giữa các zone.
5. **Pilot:** thử với thiết bị đại diện ở 2,4/5/6 GHz khi có, roaming, sleep/reconnect, PMF negotiation và EAP-TLS.
6. **Kiểm tra bảo mật:** kết nối hợp lệ thành công, credential/certificate sai bị từ chối, guest không tới DATA, IoT chỉ có quyền tối thiểu.
7. **Rollout:** cập nhật theo nhóm có rollback an toàn, thống kê hỗ trợ helpdesk, client dùng mode cũ và rate xác thực thất bại.
8. **Duy trì:** rà soát firmware, rogue AP, certificates, PSK rotation, user/device lifecycle và role mapping sau thay đổi mạng.

**Điểm đặc biệt:** khi hệ thống AAA tạm lỗi, phải biết chính xác chính sách đối với **phiên đã xác thực** và **thiết bị kết nối mới**. Không bật “fail-open toàn mạng” như biện pháp mặc định để giữ kết nối.

## 16. Giám sát và bằng chứng về mã hóa

| Nguồn dữ liệu | Trường hữu ích | Cần tránh |
|---|---|---|
| AP/controller | SSID, BSSID, negotiated AKM/cipher/PMF, association errors | Coi khả năng quảng bá bằng chứng mọi client đã dùng cùng cipher |
| RADIUS/AAA | EAP method, auth result, server health, policy/role | Ghi mật khẩu, key material hoặc token rõ |
| PKI/MDM | Tuổi thọ cert, enrollment/revocation, device posture | Chỉ nhìn cert hợp lệ mà bỏ qua tình trạng thiết bị |
| Wireless IDS/WIPS | AP mới, SSID giả, RF/association anomalies | Kết luận “tấn công” chỉ vì trùng SSID |
| Firewall/flow | Segment, nguồn/đích, luồng bị cấm/được phép | Suy ra WPA cipher chỉ từ IP traffic |
| Endpoint supplicant | Negotiated security, certificate validation, lỗi handshake | Công khai SSID, user ID, MAC hoặc credential |

Chỉ số nên đo theo từng SSID và nhóm thiết bị: **số phiên WPA3-SAE thực tế, tỷ lệ EAP-TLS/PMF, số client còn dùng WPA2 hoặc cipher legacy, lỗi certificate/RADIUS, thời gian roaming, tỉ lệ kết nối thành công và độ phủ firmware**.

Log Wi-Fi có thể tiết lộ vị trí của con người theo AP/BSSID và thời điểm. Cần bảo vệ quyền truy cập, giảm thiểu dữ liệu cá nhân và ẩn danh khi chia sẻ báo cáo.

## 17. Kiểm tra read-only từ thiết bị khách

Các lệnh dưới đây giúp quan sát mạng do bạn sở hữu hoặc được phép quản trị, **không tạo traffic tấn công và không xuất khóa rõ**.

### 17.1. Linux với NetworkManager

~~~bash
# Danh sách Wi-Fi phát hiện được và khả năng bảo mật quảng bá.
nmcli -f IN-USE,SSID,SECURITY,SIGNAL device wifi list

# Trạng thái interface, ví dụ wlan0; đổi theo thiết bị thật.
nmcli -f GENERAL.STATE,GENERAL.CONNECTION device show wlan0

# Kết nối AP hiện tại nếu có iw.
iw dev wlan0 link
~~~

Thông tin quảng bá về SECURITY trong danh sách scan **không tự chứng minh cipher/AKM đã thương lượng trên phiên hiện tại**; cần kiểm tra từ client supplicant và AP/controller.

### 17.2. Linux với wpa_supplicant

~~~bash
# Trạng thái phiên đang dùng nếu máy quản lý Wi-Fi qua wpa_supplicant.
wpa_cli -i wlan0 status
~~~

Tùy driver và phiên bản, kết quả có thể có SSID, BSSID, **key_mgmt, pairwise_cipher, group_cipher và trạng thái association**. Nếu hệ thống dùng iwd hoặc cơ chế khác, phải dùng công cụ tương ứng.

### 17.3. Windows

~~~powershell
# Thông tin kết nối, gồm Authentication và Cipher khi driver cung cấp.
netsh wlan show interfaces

# Các mạng nhìn thấy tại vị trí kiểm tra.
netsh wlan show networks mode=bssid
~~~

Không dùng tùy chọn xuất **saved key ở dạng cleartext** trong quá trình kiểm tra. Khi báo cáo phải che SSID nội bộ, BSSID/MAC, user ID hoặc dữ liệu nhạy cảm. Chỉ ghi “WPA3” trên màn hình Windows chưa xác nhận thiết bị đã vào đúng role/VLAN hoặc EAP server được xác thực đúng.

## 18. Ma trận kiểm thử cấu hình và luồng truy cập Wi-Fi

Kiểm tra chỉ thuộc phạm vi **mạng thử nghiệm hoặc môi trường được phê duyệt**; dùng thiết bị kiểm thử hợp lệ. Không cần tạo rogue AP ngoài vùng kiểm soát, không gửi traffic gây nhiễu và không thực hiện tấn công vào mạng người khác.

| Test ID | Mục tiêu | Cách kiểm tra | Kỳ vọng |
|---|---|---|---|
| **AUTH-01** | Client CORP có chứng chỉ hợp lệ kết nối được | Xem kết quả supplicant/RADIUS và AP logs | EAP-TLS thành công, đúng role/VLAN |
| **AUTH-02** | Client có certificate chưa được tin cậy bị từ chối | Dùng cấu hình client test không tin CA hoặc sai server identity trong lab | Không bỏ qua lỗi certificate; association/auth thất bại theo chính sách |
| **AUTH-03** | Credential/chứng chỉ đã thu hồi không tạo quyền mới | Thực hiện test trên account/cert lab có phê duyệt | Phiên kết nối mới bị từ chối theo chính sách; phiên cũ được xử lý theo kế hoạch |
| **CIPHER-01** | WPA3-Personal dùng SAE thực tế | Đọc negotiated key management ở client/AP | Thấy SAE, cipher phù hợp, không âm thầm về WPA2-PSK |
| **CIPHER-02** | Không chấp nhận WEP/TKIP | Kiểm kê cấu hình AP/controller và thử client legacy trong lab | Không thể thương lượng cipher bị cấm |
| **PMF-01** | PMF được yêu cầu tại SSID mục tiêu | Đọc cấu hình và trạng thái kết nối | Client tương thích thương lượng PMF; client không tương thích bị xử lý đúng policy |
| **OWE-01** | Guest dùng OWE đúng thiết kế | Quan sát negotiated AKM/cipher, không chỉ tên SSID | OWE link được mã hóa, không gắn nhãn nhầm là mạng xác thực người dùng |
| **GUEST-01** | Guest không vào DATA/MGMT | Kết nối thử giới hạn tới dịch vụ lab trên vùng cấm | Firewall deny đúng luồng, không có session |
| **IOT-01** | IoT chỉ tới controller/broker | Tạo request hợp lệ và thử một đích cấm trong lab | Luồng allow/deny đúng ma trận |
| **CORP-01** | CORP tới ứng dụng cho phép | TCP/TLS/ứng dụng trong lab với danh tính hợp lệ | Kết nối thành công, đúng quyền ứng dụng |
| **ROAM-01** | Roaming không làm mất bảo mật/phiên ngoài ngưỡng | Di chuyển thiết bị test giữa AP trong phạm vi cho phép | AKM/PMF vẫn đúng, SLA roaming phù hợp |
| **AAA-01** | RADIUS HA hoặc xử lý lỗi | Diễn tập lỗi trong lab | Chính sách với phiên mới/cũ đúng thiết kế, không mở SSID công cộng |
| **CERT-01** | Chứng chỉ server đúng tên và chưa hết hạn | Đối chiếu client validation logs và hồ sơ CA | Không chấp nhận server sai tên/CA |
| **IPV6-01** | Segmentation có hiệu lực cả IPv6 | Kiểm tra IPv4/IPv6 từ từng VLAN/SSID | Không có đường IPv6 đi vòng firewall |
| **REG-01** | Sau nâng firmware/SSID/AAA không có hồi quy | Chạy lại các test quan trọng | Không phát sinh client mặc định dùng mode yếu hơn |

### 18.1. Tiêu chí PASS, FAIL và INCONCLUSIVE

- **PASS:** có bằng chứng độc lập phù hợp kỳ vọng, ví dụ client EAP-TLS kết nối qua đúng RADIUS, server cert hợp lệ, được gán đúng role và chỉ truy cập dịch vụ cho phép.
- **FAIL:** bằng chứng trái chính sách, ví dụ SSID CORP chấp nhận TKIP hoặc client không có cert hợp lệ vẫn kết nối được vào mạng nội bộ.
- **INCONCLUSIVE:** thiếu dữ liệu hoặc phép thử sai điều kiện, ví dụ AP không có log negotiated cipher, máy client đang dùng mạng di động thay Wi-Fi thử, DNS đích lỗi hoặc không biết firewall nào xử lý gói.

**Không lấy một biểu tượng ổ khóa cạnh SSID hoặc một lần ping timeout làm kết luận đạt bảo mật.** Cần kết hợp trạng thái liên kết, log xác thực và kết quả kiểm thử đường mạng.

### 18.2. Mẫu biên bản một phép thử

~~~yaml
test_id: CORP-EAPTLS-LAB-01
environment: authorized-isolated-lab
ssid: CORP-LAB
mode_expected: WPA3-Enterprise
eap_method_expected: EAP-TLS
server_identity_expected: radius.example.test
client_role_expected: CORP
evidence_required:
  - client-supplicant-state
  - ap-negotiated-akm-cipher-pmf
  - radius-authentication-result
  - server-certificate-validation
  - vlan-role-and-firewall-path
  - allowed-and-denied-flow-tests
result: pending
~~~

Các thông tin trên đều **giả định**, không khẳng định đã thực thi. Không lưu private key hoặc passphrase thật vào bản ghi kết quả.

## 19. Troubleshooting: lỗi kết nối có phải do mã hóa?

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần xem |
|---|---|---|
| Thấy SSID nhưng không kết nối được | AKM/cipher/PMF mismatch; lỗi association | AP/client capabilities, association reason code |
| WPA3-Personal chỉ lỗi trên một mẫu máy | Driver/firmware thiếu SAE hoặc bug roaming | Thiết bị, firmware, negotiated AKM, logs |
| Chỉ máy cũ vào được WPA2, không vào WPA3-only | Không hỗ trợ SAE hoặc PMF bắt buộc | Ma trận client compatibility, AP security profile |
| EAP-TLS báo chứng chỉ không tin cậy | Thiếu CA, sai server name, cert hết hạn, đồng hồ sai | Client validation, CA path, thời gian, cert metadata |
| RADIUS trả reject | Cert/client identity/role/chính sách không phù hợp | RADIUS reason, MDM enrollment, trạng thái tài khoản |
| RADIUS không phản hồi | Route, firewall, dịch vụ AAA, DNS hoặc HA | Timeout, RADIUS health, AP–AAA network path |
| Đã xác thực nhưng không lấy được IP | DHCP/VLAN/ACL lỗi | Role mapping, DHCP lease, VLAN, gateway logs |
| Có IP nhưng không vào ứng dụng nội bộ | DNS, segmentation, proxy, TLS, VPN hoặc firewall | DNS query, route, 5-tuple, firewall logs |
| Mất kết nối khi roaming | 802.11r/PMK caching, RF coverage, AP/controller, reauth | Roam timeline, AP changes, RADIUS events |
| Deauth tăng bất thường | RF yếu/nhiễu, client roaming, lỗi driver hoặc hành vi đáng nghi | RF telemetry, signal, reason code, PMF status |
| Guest thấy Internet nhưng vào được DATA | Guest segmentation/ACL bị sai hoặc có đường bypass | Source role, gateway, firewall deny/allow, IPv6 |
| Nhiều người dùng bị chặn sau đổi PSK | Chưa cập nhật credential, thiết bị tự nối SSID cũ | Credential distribution, client config, rollout records |
| Controller báo WPA3 nhưng client dùng PSK | Transition mode hoặc cấu hình band khác | Negotiated AKM theo từng client, AP profile |
| Ứng dụng báo timeout sau khi kết nối Wi-Fi | DNS/DHCP/route/firewall/ứng dụng lỗi | Positive control, packet flow, dịch vụ đích |

### 19.1. Quy trình điều tra theo thứ tự

1. **Xác định đúng SSID, BSSID, radio/band và client cụ thể** ở thời điểm gặp lỗi.
2. Kiểm tra client/AP có hỗ trợ cùng **AKM/cipher/PMF** không.
3. Với Enterprise, xem **EAP state, CA, server identity, client certificate và RADIUS response**.
4. Nếu association/auth thành công, xem **role/VLAN, DHCP, DNS, routing, firewall và application TLS**.
5. Với sự cố roaming, so timeline AP, 802.11r/cache và dữ liệu RF; không chỉ nhìn RADIUS reject.
6. So sánh một client **positive control** đã hoạt động cùng cấu hình với thiết bị lỗi.
7. Chỉ hạ hoặc thay đổi chính sách bảo mật sau khi đã có bằng chứng và **phương án rollback**; không tắt server certificate validation hoặc PMF bừa bãi để “sửa lỗi nhanh”.

## 20. Case study: nâng cấp Wi-Fi doanh nghiệp có thiết bị IoT cũ

### 20.1. Bối cảnh giả định

Một công ty có ba nhóm kết nối:

- **Nhân viên** dùng SSID `OFFICE`, trước đây dùng WPA2-Personal với một passphrase được chia sẻ nhiều năm.
- **Máy in/camera IoT** chỉ hỗ trợ WPA2-CCMP ở firmware hiện tại.
- **Khách** sử dụng mạng open và captive portal.

Đội Security muốn giảm rủi ro lộ PSK, tách truy cập, bổ sung PMF và tăng độ an toàn trước nghe lén thụ động. Đội IT muốn người dùng không mất kết nối đồng loạt và không phải thay toàn bộ IoT ngay.

### 20.2. Đề xuất kiến trúc mục tiêu

| Nhóm | Trạng thái cũ | Trạng thái mục tiêu | Lý do |
|---|---|---|---|
| Nhân viên | WPA2-Personal, shared PSK | WPA3-Enterprise hoặc WPA2-Enterprise EAP-TLS trong giai đoạn tương thích | Credential riêng, certificate validation, thu hồi theo user/device |
| IoT | Chung PSK với nhân viên | SSID/VLAN IoT riêng, WPA2-AES-CCMP nếu buộc phải dùng | Giới hạn thiệt hại và luồng nội bộ, chờ thay thiết bị |
| Khách | Open + captive portal | OWE khi client hỗ trợ, guest isolation và firewall | Mã hóa link thụ động mà không đòi mật khẩu |
| Quản trị AP | Lẫn trong mạng người dùng | VLAN quản trị riêng, RBAC/bastion | Bảo vệ management plane |

### 20.3. Các bước thực hiện

**Bước 1:** inventory AP, số thiết bị, firmware, driver, hỗ trợ PMF/SAE/EAP-TLS và các luồng ứng dụng. Kiểm tra những thiết bị chỉ hỗ trợ cipher legacy WEP/TKIP: cần có **kế hoạch thay thế hoặc cô lập không cho tham gia WLAN chính**, không giữ WPA/TKIP mở chung.

**Bước 2:** xây PKI/AAA và cấp certificate cho laptop quản lý qua MDM. Bật chính sách xác thực **đúng server name/CA** trên client thay vì yêu cầu người dùng tự chọn “Trust this server”.

**Bước 3:** tạo pilot SSID `CORP-LAB` theo chế độ Enterprise, kiểm tra PMF, roaming và chứng chỉ. Không tái sử dụng passphrase cũ cho IoT/guest. Xác nhận RADIUS authentication success/failure, role mapping và quy tắc firewall.

**Bước 4:** chuyển nhóm laptop sang SSID chính. Cấp IoT SSID riêng với quyền chỉ tới controller và dịch vụ DNS/NTP cần thiết. Dùng guest OWE khi thiết bị hỗ trợ, giữ guest isolation và chặn guest đến CORP/DATA.

**Bước 5:** xác minh negotiated mode của **client thực**, không chỉ nhìn cấu hình broadcast. Test CORP → ứng dụng (ALLOW), GUEST → DATA (DENY), IoT → controller (ALLOW), IoT → management (DENY), IPv6 và các kết nối đặc biệt khi roaming.

**Bước 6:** khi các nhóm thiết bị đã chuyển xong, thu hồi SSID/PSK cũ, bật cấu hình PMF thích hợp và ghi lịch rà soát IoT chưa được nâng cấp.

### 20.4. Mẫu kết quả cần thu thập

~~~text
LAB EXERCISE: Wi-Fi hardening migration (giả định)

Expected:
  Corporate clients: Enterprise auth + correct server identity
  Guest clients: encrypted OWE where supported, internal access DENIED
  IoT clients: CCMP only, narrow allowlist
  WEP/TKIP: unavailable on production SSIDs
  PMF: negotiated per policy and device capability

Evidence:
  AP/controller security and client state
  RADIUS success/reject and certificate validation
  Segmentation firewall logs + application checks
  Roaming, firmware and service health metrics

Outcome: PENDING LAB VALIDATION
~~~

**Bài học:** việc chọn WPA3 và EAP-TLS là cải thiện đáng kể, nhưng **thành công** phải được đo bằng khả năng thu hồi quyền, phân đoạn đúng, chống chặn nhầm người dùng và bằng chứng liên kết thực tế.

## 21. Bài tập vận dụng

### Bài 1 — Chọn phương thức

Một nhóm nhỏ có toàn bộ điện thoại/laptop hiện đại, không có RADIUS/PKI. Nên ưu tiên WPA2-PSK hay WPA3-SAE? Vì sao?

*Gợi ý:* WPA3-Personal SAE khi tất cả thiết bị hỗ trợ, cùng passphrase đủ mạnh và chính sách phân đoạn; nếu sau này cần quyền theo từng cá nhân, xem xét Enterprise.

### Bài 2 — Xác thực doanh nghiệp

Tổ chức có 1.000 laptop quản lý được qua MDM và cần thu hồi quyền mỗi nhân viên. Dùng cùng một WPA3-Personal passphrase cho tất cả có đạt mục tiêu không?

*Gợi ý:* không tối ưu cho attribution/revocation. Dùng 802.1X/EAP-TLS với certificate và role per-device/per-user phù hợp.

### Bài 3 — Evil twin

Client thấy hai AP cùng tên `CORP`. Vì sao chỉ kiểm tra SSID là không đủ? Điều gì trên client làm giảm nguy cơ chấp nhận server giả?

*Gợi ý:* SSID có thể bị sao chép; với EAP-TLS cần xác thực CA và **tên authentication server chính xác**, cấu hình cố định bởi MDM.

### Bài 4 — OWE

Mạng khách dùng OWE thay cho open. Có thể kết luận đã xác thực AP và chống mọi MITM không?

*Đáp án:* không. OWE giúp mã hóa đường vô tuyến mà không có xác thực AP như EAP-TLS; HTTPS/TLS và chính sách mạng vẫn cần thiết.

### Bài 5 — PMF

AP bật PMF required nhưng một camera đời cũ không kết nối. Giải pháp nào tránh hạ bảo mật toàn mạng nhân viên?

*Gợi ý:* kiểm tra hỗ trợ/firmware, thay camera nếu có thể; nếu buộc phải dùng, bố trí mạng IoT riêng có giới hạn quyền và kế hoạch loại bỏ thiết bị cũ.

### Bài 6 — WPA2 handshake

WPA2-Personal với PSK ngắn, dễ đoán có rủi ro gì khi người ngoài thu được dữ liệu handshake phù hợp?

*Gợi ý:* có nguy cơ kiểm tra phỏng đoán mật khẩu offline. Khuyến nghị passphrase ngẫu nhiên dài và chuyển SAE/Enterprise khi khả thi, không cung cấp quy trình khai thác.

### Bài 7 — Wi-Fi vs HTTPS

Người dùng kết nối WPA3 rồi truy cập một dịch vụ HTTP plaintext ở Internet. WPA3 có bảo đảm dữ liệu được mã hóa suốt đường đến server không?

*Đáp án:* không. WPA3 bảo vệ chặng Wi-Fi; cần HTTPS/TLS để bảo vệ dữ liệu ứng dụng qua mạng sau AP.

### Bài 8 — Enterprise certificate

Sau khi RADIUS đổi certificate, client không thể xác thực EAP-TLS và báo sai server identity. Có nên tắt server certificate validation?

*Đáp án:* không. Xác minh tên server, chain CA, hiệu lực, đồng hồ và hồ sơ MDM, rồi cập nhật cấu hình đúng theo quy trình.

### Bài 9 — Guest segmentation

Guest OWE đã mã hóa thành công nhưng vẫn kết nối được TCP/5432 tới database nội bộ. Kết luận gì?

*Gợi ý:* link encryption đạt mục tiêu riêng, nhưng **network segmentation FAIL**. Cần sửa ACL/firewall/route và kiểm tra các đường khác, bao gồm IPv6.

### Bài 10 — Chẩn đoán theo tầng

Thiết bị báo đã xác thực WPA3-Enterprise nhưng không truy cập được ứng dụng. Liệt kê thứ tự bước điều tra.

*Gợi ý:* negotiated AKM/PMF → EAP/RADIUS → role/VLAN → DHCP/DNS → route/firewall → TLS/ứng dụng. Không coi mọi lỗi sau khi kết nối là lỗi WPA3.

## 22. Checklist triển khai Wireless Encryption

- Đã loại bỏ **WEP/WPA-TKIP** khỏi WLAN sản xuất và có kế hoạch thay client không tương thích.
- Đã chọn **WPA3-SAE hoặc WPA2/WPA3-Enterprise** phù hợp năng lực thiết bị và yêu cầu định danh.
- Với Enterprise, client **kiểm tra CA, tên RADIUS server và certificate**; không có tùy chọn bỏ qua xác thực server tùy tiện.
- Có **PKI, MDM, chứng chỉ riêng, revocation và RADIUS/AAA redundancy** khi dùng EAP-TLS.
- Đã xác minh **negotiated AKM/cipher/PMF** trên thiết bị thực, không chỉ cấu hình SSID phát quảng bá.
- WPA2/WPA3 transition và OWE transition có **giới hạn phạm vi, thời hạn và kế hoạch loại bỏ**.
- PMF được bật/required theo chế độ và khả năng client; đã thử xử lý tình huống không tương thích.
- Wi-Fi khách/IoT/CORP/MGMT có **role/VLAN riêng, firewall allowlist/deny và IPv4/IPv6 kiểm chứng**.
- Hạ tầng có **TLS/mTLS, DNS security, bảo vệ ứng dụng, firmware update và phát hiện rogue AP** ở các lớp phù hợp.
- Các lệnh kiểm tra và log **không tiết lộ mật khẩu, private key, token hoặc dữ liệu cá nhân ngoài nhu cầu**.
- Có bộ test **ALLOW/DENY, certificate validation, roaming, RADIUS failure, WEP/TKIP rejection và rollback**.
- Mỗi thay đổi có **owner, thời điểm, cấu hình trước/sau, trạng thái kiểm thử và chu kỳ rà soát**.

**Kết luận:** bảo vệ Wi-Fi không chỉ là chọn một nhãn “WPA2” hoặc “WPA3”. An toàn thật sự phụ thuộc **AKM/cipher được thương lượng, cách quản lý danh tính và khóa, PMF, chất lượng triển khai, quy tắc phân đoạn và TLS ứng dụng**. Thiết kế phù hợp là thiết kế có thể giải thích **ai kết nối, được xác thực bằng gì, lưu lượng được mã hóa đến đâu, quyền mạng ra sao và bằng chứng nào xác nhận điều đó**.

### Tài liệu tham khảo

- [NIST SP 800-153 — Guidelines for Securing Wireless Local Area Networks (WLANs)](https://csrc.nist.gov/pubs/sp/800/153/final): các nguyên tắc thiết kế và vận hành mạng Wi-Fi an toàn.
- [NIST SP 800-97 — Establishing Wireless Robust Security Networks: A Guide to IEEE 802.11i](https://csrc.nist.gov/pubs/sp/800/97/final): nền tảng RSN, 802.11i và cơ chế mã hóa/xác thực.
- [IEEE 802.11 Wireless LAN standards](https://standards.ieee.org/ieee/802.11/): họ tiêu chuẩn IEEE 802.11 và các cập nhật.
- [Wi-Fi Alliance — Wi-Fi Security](https://www.wi-fi.org/discover-wi-fi/security): các thế hệ WPA2/WPA3, Enhanced Open và yêu cầu chứng nhận.
- [RFC 3748 — Extensible Authentication Protocol (EAP)](https://www.rfc-editor.org/rfc/rfc3748): nền tảng EAP.
- [RFC 5216 — The EAP-TLS Authentication Protocol](https://www.rfc-editor.org/rfc/rfc5216): EAP-TLS và vai trò của TLS/certificate trong xác thực.
- [RFC 9190 — EAP-TLS 1.3: Using the Extensible Authentication Protocol with TLS 1.3](https://www.rfc-editor.org/rfc/rfc9190): EAP-TLS 1.3.
- [RFC 8110 — Opportunistic Wireless Encryption](https://www.rfc-editor.org/rfc/rfc8110): mô hình OWE và những giới hạn về xác thực.
- [RFC 6614 — Transport Layer Security (TLS) Encryption for RADIUS](https://www.rfc-editor.org/rfc/rfc6614): bảo vệ đường truyền RADIUS khi hạ tầng hỗ trợ.




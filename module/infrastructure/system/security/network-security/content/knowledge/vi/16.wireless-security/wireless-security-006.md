# Evil twin

**Evil twin** là một kiểu **điểm truy cập Wi-Fi giả mạo có chủ đích**: thiết bị hoặc mạng không được tin cậy cố làm cho người dùng nhận nhầm nó là một mạng Wi-Fi hợp pháp. Kẻ tấn công có thể bắt chước tên mạng (**SSID**), hình thức trang đăng nhập, đặc điểm quảng bá hoặc một số thông số khác để dụ thiết bị kết nối, từ đó tìm cách lừa lấy thông tin đăng nhập, làm sai lệch đường truy cập hoặc quan sát các dữ liệu không được bảo vệ đầy đủ.

Rủi ro cốt lõi không nằm ở việc “có hai điểm truy cập cùng tên”: nhiều mạng doanh nghiệp chủ động dùng cùng SSID trên hàng chục access point. Vấn đề là **một điểm truy cập không được ủy quyền đang mạo nhận vai trò của mạng tin cậy** và người dùng hoặc thiết bị có thể không xác minh được sự khác biệt.

Trong chương **Wireless security** của module **SECURITY_NETWORK_SECURITY**, Evil twin liên quan trực tiếp tới xác thực kết nối, phân đoạn mạng, firewall, VPN, bảo vệ DNS, IDS/IPS, giám sát xâm nhập và kiến trúc Wi-Fi/cloud an toàn. Bài học tập trung vào **nhận diện, thiết kế phòng vệ và ứng phó**; các tình huống tấn công được diễn giải ở mức mô hình đe dọa, không hướng dẫn dựng điểm truy cập giả để nhắm vào người dùng thực.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích Evil twin, phân biệt nó với **rogue AP**, mạng khách công cộng và roaming hợp lệ giữa nhiều AP cùng SSID.
2. Hiểu vai trò của **SSID, BSSID, radio, beacon, association**, chính sách bảo mật và quá trình xác thực khi thiết bị kết nối Wi-Fi.
3. Phân tích những rủi ro khác nhau giữa mạng open, WPA2/WPA3-Personal, WPA2/WPA3-Enterprise, OWE và captive portal.
4. Giải thích vì sao **xác minh chứng thư máy chủ EAP/802.1X** là kiểm soát trọng yếu đối với Wi-Fi Enterprise.
5. Nêu những điều **Protected Management Frames (PMF)**, HTTPS, VPN, DNS bảo mật và phân đoạn mạng có thể hoặc không thể bảo vệ.
6. Đề xuất cơ chế quan sát bằng wireless IDS/IPS, danh mục AP hợp lệ, cấu hình thiết bị do MDM quản lý và nhật ký RADIUS/controller.
7. Thiết kế checklist phát hiện, triage, ứng phó và bài kiểm thử trong lab **không can thiệp mạng của bên thứ ba**.

## 2. Những thành phần cơ bản của một mạng Wi-Fi

Để hiểu Evil twin, trước hết phải phân biệt **tên mạng người dùng nhìn thấy** với **danh tính và thông số thực tế của điểm truy cập**.

| Thành phần | Ý nghĩa | Lưu ý bảo mật |
| --- | --- | --- |
| **SSID** | Tên mạng Wi-Fi được quảng bá hoặc cấu hình, ví dụ `Office-Secure` | Không phải định danh duy nhất hay bằng chứng sở hữu mạng |
| **BSSID** | Định danh của một Basic Service Set, thường thể hiện bằng địa chỉ MAC của giao diện Wi-Fi | Nhiều AP cùng SSID có thể có BSSID khác nhau; BSSID cũng có thể bị giả mạo |
| **AP** (*Access Point*) | Thiết bị cung cấp khả năng kết nối Wi-Fi | Cần được doanh nghiệp quản lý, cập nhật và đặt đúng trust zone |
| **Station / client** | Laptop, điện thoại, thiết bị IoT kết nối tới AP | Có thể lưu profile mạng và kết nối lại tự động tùy cấu hình |
| **Beacon / Probe** | Những khung 802.11 phục vụ quảng bá hoặc tìm kiếm mạng | Có thể hữu ích cho quan sát, không tự chứng minh điểm truy cập đáng tin |
| **Association** | Bước thiết bị tham gia BSS ở mức 802.11 | Chưa đồng nghĩa đã hoàn tất xác thực/cấp quyền truy cập mạng |
| **802.1X / EAP** | Cơ chế xác thực dùng phổ biến ở Wi-Fi Enterprise | Cần cấu hình kiểm tra danh tính máy chủ EAP đúng cách |
| **WLAN controller / cloud manager** | Quản lý nhiều AP, SSID, policy và telemetry | Cung cấp danh mục AP hợp lệ và sự kiện đáng tin hơn chỉ quét tên SSID |

Ví dụ, một văn phòng có ba AP phát cùng SSID **Office-Secure** để thiết bị di chuyển giữa các khu vực mà không cần chọn mạng mới. BSSID, kênh và cường độ tín hiệu có thể khác nhau hoàn toàn **theo thiết kế**. Vì vậy, nhìn thấy ba BSSID có cùng tên không phải bằng chứng Evil twin.

### 2.1. Thiết bị thường quyết định kết nối như thế nào?

Tùy hệ điều hành, cấu hình người dùng và khả năng của mạng, thiết bị có thể xem xét:

- SSID cùng với **loại bảo mật đã được lưu**.
- Thông số RSN, chính sách WPA2/WPA3 và phương thức xác thực hỗ trợ.
- Tín hiệu vô tuyến, môi trường roaming, lịch sử kết nối và chính sách MDM.
- Chứng thư và danh tính máy chủ xác thực khi dùng Wi-Fi Enterprise.
- Những thông tin bổ trợ như cấu hình Passpoint/Hotspot 2.0 khi thiết bị và mạng hỗ trợ.

**Không có một thuật toán chọn AP áp dụng giống nhau cho mọi thiết bị.** Không nên khẳng định client sẽ luôn chọn AP mạnh tín hiệu nhất hoặc cứ thấy SSID trùng là tự kết nối, vì cơ chế bảo mật và chính sách profile có thể ngăn kết nối.

## 3. Evil twin vận hành theo mô hình đe dọa nào?

Ở mức khái niệm, một tình huống Evil twin thường có các thành phần:

1. **Mạng hợp lệ có thể được người dùng nhận ra**, chẳng hạn SSID của công ty hoặc mạng khách tại một địa điểm.
2. **Một điểm truy cập không được tin cậy mạo nhận đặc điểm nhận diện**, có thể là cùng tên mạng hoặc trang giới thiệu/đăng nhập trông quen thuộc.
3. **Thiết bị hoặc người dùng lựa chọn kết nối** vì nhầm lẫn, cài đặt tự kết nối yếu hoặc cảnh báo xác thực bị bỏ qua.
4. Nếu kết nối diễn ra, đường mạng và trang đăng nhập có thể nằm dưới quyền kiểm soát của điểm không đáng tin.
5. **Hậu quả phụ thuộc những lớp bảo vệ còn lại**: HTTPS, xác minh chứng thư, VPN, 802.1X, MFA và chính sách ứng dụng.

~~~mermaid
flowchart TD
    U["Người dùng chọn mạng Wi-Fi có tên quen thuộc"] --> Q{"Thiết bị có kiểm tra danh tính và policy bảo mật?"}
    Q -->|"Có, cấu hình chặt"| S["Xác thực và chỉ kết nối khi policy hợp lệ"]
    Q -->|"Không đủ / người dùng bỏ cảnh báo"| R["Có nguy cơ vào AP không đáng tin"]
    R --> H{"Ứng dụng dùng HTTPS/VPN và xác minh đúng?"}
    H -->|"Có"| P["Dữ liệu ứng dụng được bảo vệ trên kênh phù hợp"]
    H -->|"Không / bị lừa nhập thông tin"| I["Nguy cơ lộ dữ liệu, điều hướng hoặc phishing"]
    S --> V["Ghi nhận telemetry / xác minh AP hợp lệ"]
    R --> V
~~~

**Mạo nhận SSID không tự đảm bảo kẻ tấn công đọc được HTTPS hoặc giải mã các kết nối an toàn.** Người đứng giữa mạng có thể quan sát một số metadata, gây gián đoạn hoặc đưa người dùng tới nội dung lừa đảo trong những tình huống cụ thể; việc đọc được dữ liệu bên trong TLS hợp lệ còn đòi hỏi phá vỡ hoặc khiến client bỏ qua cơ chế xác thực kênh.

### 3.1. Hậu quả có thể xảy ra

| Hậu quả | Điều kiện khiến rủi ro tăng | Giới hạn cần hiểu |
| --- | --- | --- |
| **Phishing qua captive portal** | Người dùng nhập mật khẩu công ty vào trang giả | Trang đăng nhập Wi-Fi không phải bằng chứng quyền sở hữu SSID |
| **Lộ dữ liệu không mã hóa** | Ứng dụng dùng giao thức plaintext | HTTPS/TLS hoặc VPN đúng cấu hình bảo vệ nội dung của kênh được mã hóa |
| **Sai lệch DNS/gateway** | Client chấp nhận DHCP/DNS từ mạng không đáng tin | TLS và xác minh tên miền giúp giảm nguy cơ truy cập nhầm máy chủ |
| **Từ chối dịch vụ** | Kết nối không ổn định, xác thực thất bại hoặc sai cấu hình | Mất mạng chưa tự chứng minh có Evil twin |
| **Rủi ro thông tin đăng nhập Wi-Fi Enterprise** | Client không kiểm tra đúng chứng thư máy chủ EAP | EAP-TLS và xác minh chứng thư đúng cấu hình giảm đáng kể rủi ro |
| **Theo dõi metadata** | Client truy cập qua mạng ngoài tổ chức | Nội dung ứng dụng mã hóa vẫn có thể để lộ một số thông tin về lưu lượng |

## 4. Evil twin khác rogue AP và roaming hợp lệ ra sao?

Các khái niệm dễ bị đánh đồng:

| Khái niệm | Đặc điểm | Cần đánh giá |
| --- | --- | --- |
| **Evil twin** | AP không đáng tin cố **mạo nhận** một mạng được tin cậy | Ý định/phương thức mạo nhận và tác động thực tế |
| **Rogue AP** | AP không được tổ chức phê duyệt trong hoặc gần phạm vi mạng quản lý | Có thể chỉ là thiết bị cắm nhầm, không nhất thiết giả mạng khác |
| **Neighbor AP** | AP hợp pháp của bên cạnh có tín hiệu đi vào vùng quan sát | Có thuộc danh mục/mạng tổ chức không, có dấu hiệu mạo nhận không |
| **Roaming hợp lệ** | Nhiều AP do tổ chức quản lý quảng bá cùng SSID, nhiều BSSID | Có khớp inventory, controller và cấu hình an ninh không |
| **Hotspot công cộng** | Wi-Fi cung cấp cho nhiều khách, có thể open/captive portal | Danh tính nhà cung cấp, rủi ro đường mạng, điều khoản sử dụng |

Một thiết bị phát cùng tên **Office-Secure** chưa chắc là Evil twin. Một AP lạ phát SSID riêng **Office-Test** cũng chưa chắc mạo nhận mạng công ty. Cần kết hợp danh mục tài sản, dữ liệu controller, địa điểm, radio và bối cảnh sự kiện.

### 4.1. SSID/BSSID có thể hỗ trợ phát hiện nhưng không đủ xác thực

- **SSID** là chuỗi tên do hệ thống quảng bá/cấu hình; mạng khác có thể dùng cùng tên.
- **BSSID** là định danh hữu ích cho kiểm kê radio, nhưng địa chỉ MAC có thể thay đổi do cấu hình, thay thiết bị, multi-BSSID hoặc bị giả mạo.
- **OUI của MAC** có thể gợi ý nhà sản xuất trong một số trường hợp, nhưng không phải bằng chứng chắc chắn về thiết bị.
- **Tín hiệu mạnh/yếu** thay đổi theo khoảng cách, vật cản, kênh, công suất và nhiễu; không tự chứng minh AP là giả.
- **Chứng thư EAP** và chính sách truy cập được quản lý có giá trị xác thực mạnh hơn danh sách tên/BSSID đơn lẻ khi triển khai đúng.

## 5. Rủi ro theo chế độ bảo mật Wi-Fi

Evil twin có mức tác động khác nhau đáng kể tùy **phương thức bảo mật mà client thực sự thương lượng và chấp nhận**.

| Chế độ | Đặc điểm | Điều cần hiểu về Evil twin |
| --- | --- | --- |
| **Open Wi-Fi** | Không xác thực và không mã hóa ở liên kết Wi-Fi theo mô hình open truyền thống | SSID dễ bị bắt chước; ứng dụng phải dùng TLS/VPN khi thích hợp |
| **WPA2-Personal (PSK)** | Các thiết bị biết cùng mật khẩu dùng để thiết lập khóa bảo vệ liên kết | AP giả không biết mật khẩu không thể hoàn tất đúng cơ chế bảo mật chỉ nhờ sao chép SSID; nhưng mật khẩu chia sẻ không xác thực duy nhất một AP cụ thể |
| **WPA3-Personal (SAE)** | Xác thực dựa trên mật khẩu và cơ chế SAE, cải thiện khả năng chống một số tấn công mật khẩu ngoại tuyến | Không phải danh tính mật mã riêng của từng AP nếu nhiều AP dùng cùng mật khẩu; cần quản lý mật khẩu và chính sách chuyển đổi |
| **WPA2/WPA3-Enterprise (802.1X/EAP)** | Xác thực dựa trên EAP và hạ tầng máy chủ xác thực | Bảo vệ phụ thuộc **client kiểm tra danh tính/chứng thư máy chủ EAP** và phương thức EAP đúng |
| **Enhanced Open / OWE** | Mã hóa lưu lượng liên kết riêng cho từng kết nối mà không cần mật khẩu chung | Không cung cấp xác thực AP theo danh tính tổ chức; không ngăn hoàn toàn Evil twin |
| **Passpoint/Hotspot 2.0** | Cơ chế khám phá/lựa chọn mạng và xác thực có thể dựa trên danh tính nhà cung cấp | Chất lượng bảo vệ phụ thuộc profile và xác minh nhà cung cấp/cert; không chỉ dựa vào SSID |

### 5.1. WPA2/WPA3-Personal không phải “SSID là danh tính”

Trong mạng Personal, thiết bị phải hoàn tất quá trình xác thực/thiết lập khóa phù hợp với mật khẩu đã cấu hình. **Một AP chỉ đổi tên cho giống SSID an toàn không tự vượt qua được bước này** nếu không sở hữu thông tin khóa cần thiết.

Tuy nhiên, nếu nhiều thiết bị biết **cùng mật khẩu Wi-Fi**, mật khẩu đó không phân biệt được AP nào do tổ chức cấp phép. Việc một AP hoàn tất được bước xác thực mật khẩu **không đồng nghĩa** nó là AP trong inventory. Cần bảo vệ bí mật mật khẩu, kiểm soát thiết bị được phép và giám sát radio.

Với các triển khai có **transition mode**, cần đánh giá loại bảo mật mà client thực sự dùng. Đừng suy rằng chỉ cần cấu hình tên profile “WPA3” là mọi client đều sử dụng đầy đủ chính sách WPA3; khả năng hỗ trợ và fallback có thể khác nhau.

### 5.2. Enterprise ưu tiên danh tính thay vì mật khẩu Wi-Fi chung

Wi-Fi Enterprise dùng mô hình **802.1X/EAP**, trong đó AP là thành phần chuyển tiếp yêu cầu xác thực giữa client và hệ thống xác thực (thường là RADIUS). Client cần được cấu hình tin cậy **đúng máy chủ xác thực**, và server cần xác định client theo chính sách của phương thức EAP.

Nếu thiết bị chấp nhận một máy chủ EAP không được phép, nó có thể gặp nguy cơ lộ bí mật hoặc bị dẫn tới quy trình xác thực không đúng. Ngược lại, cấu hình chứng thư và phương thức EAP chặt chẽ có thể ngăn hoặc làm lộ sự mạo nhận ngay tại bước xác thực.

## 6. Wi-Fi Enterprise: kiểm tra chứng thư máy chủ là điểm then chốt

### 6.1. Mô hình 802.1X/EAP

~~~mermaid
sequenceDiagram
    participant C as Thiết bị đã quản lý
    participant A as AP / Authenticator
    participant R as RADIUS / EAP server được duyệt
    C->>A: Yêu cầu truy cập Wi-Fi Enterprise
    A->>R: Chuyển tiếp trao đổi EAP
    R-->>A: Thông tin EAP và danh tính máy chủ theo phương thức
    A-->>C: Chuyển tiếp để client xác minh
    Note over C: Kiểm tra CA, danh tính máy chủ và chính sách EAP
    C->>A: Tiếp tục chỉ khi xác minh hợp lệ
    A->>R: Hoàn tất xác thực theo chính sách
    Note over C,A: Chỉ sau xác thực/thiết lập khóa hợp lệ mới cấp quyền truy cập
~~~

Sơ đồ mô tả logic: quy trình cụ thể tùy EAP-TLS, PEAP hoặc EAP-TTLS, phiên bản giao thức và cách AP/controller vận hành. Một AP lạ không đơn giản được xem là hợp pháp chỉ vì phát đúng SSID.

### 6.2. EAP-TLS

**EAP-TLS** sử dụng TLS trong xác thực EAP, thường với chứng thư của **cả máy chủ và client**. Khi được cấu hình đúng, thiết bị kiểm tra chứng thư máy chủ và danh tính mong đợi, còn máy chủ xác minh chứng thư client và quyền truy cập.

Ưu điểm thường gặp:

- Không phải gửi mật khẩu người dùng theo phương thức chia sẻ bí mật truyền thống trong lúc xác thực Wi-Fi.
- Danh tính thiết bị/người dùng có thể gắn với chứng thư, hệ thống cấp phát và chính sách thu hồi.
- Hạn chế rủi ro từ việc thiết bị chấp nhận bừa máy chủ xác thực không đúng.

**EAP-TLS không tự thành công nếu quản lý chứng thư sai.** Cần quản lý CA tin cậy, tên server, thời hạn, private key client, thu hồi, enrollment, quyền thiết bị và cấu hình MDM.

### 6.3. PEAP/EAP-TTLS và lỗi “không kiểm tra certificate”

Các phương thức EAP tạo đường TLS để bảo vệ bước xác thực bên trong chỉ an toàn theo kỳ vọng khi **client xác thực chính xác máy chủ TLS**. Nếu cấu hình profile cho phép bỏ qua bước kiểm tra chứng thư hoặc người dùng tự chấp nhận server lạ, nguy cơ kết nối nhầm máy chủ xác thực tăng lên.

Đừng coi thông báo “certificate warning” là bước bình thường phải bỏ qua để có mạng. Đó có thể là:

- Chứng thư đã hết hạn hoặc tên server sai do lỗi quản trị.
- Client thiếu CA/profile hợp lệ.
- Máy chủ xác thực không nằm trong danh sách được phép.
- Dấu hiệu nghi vấn về việc giả mạo hệ thống xác thực.

Trong mọi trường hợp, phải **xác minh với IT/NOC qua kênh đã biết**, không hướng dẫn người dùng tự tắt kiểm tra chứng thư.

### 6.4. Checklist profile Wi-Fi Enterprise

| Kiểm soát | Mục tiêu |
| --- | --- |
| EAP method được duyệt | Tránh fallback sang phương thức yếu hoặc ngoài chính sách |
| CA tin cậy được quản lý | Chỉ chấp nhận chuỗi chứng thư dự kiến |
| Tên máy chủ RADIUS/EAP mong đợi | Ràng buộc danh tính server, không tin mọi máy chủ có chứng thư công khai |
| Không cho bỏ qua certificate validation | Giảm nguy cơ bị dụ xác thực với server mạo nhận |
| Phân phối profile bằng MDM | Cấu hình nhất quán và hạn chế sửa sai thủ công |
| Chứng thư client nếu dùng EAP-TLS | Kiểm soát danh tính và vòng đời thiết bị |
| Cảnh báo khi xác thực bất thường | Phân biệt lỗi cấu hình, hết hạn chứng thư và nghi vấn tấn công |
| Kiểm thử trước khi xoay CA/cert | Tránh vô tình làm mất kết nối diện rộng |

## 7. Captive portal và phishing qua Wi-Fi

**Captive portal** là trang web hoặc quy trình tương tác yêu cầu người dùng chấp nhận điều khoản, đăng nhập hoặc thực hiện một bước trước khi có quyền truy cập Internet theo chính sách của mạng.

Một Evil twin có thể cố bắt chước giao diện portal để khiến người dùng tin đây là bước bình thường của mạng doanh nghiệp hoặc địa điểm. **Đây là rủi ro lừa đảo**, không phải bằng chứng rằng cơ chế Wi-Fi đã giải mã được mật khẩu hay lưu lượng HTTPS.

### 7.1. Những dấu hiệu cần thận trọng

- Mạng công ty trước đây dùng Enterprise/802.1X nhưng nay lại yêu cầu nhập mật khẩu công ty vào một trang web không được IT công bố.
- Trang yêu cầu nhập OTP, mật khẩu tài khoản hay cài chứng thư/ứng dụng không nằm trong quy trình onboarding chính thức.
- Tên miền trong thanh địa chỉ khác với domain portal đã được tổ chức xác nhận, có chứng thư lỗi hoặc trình duyệt đưa cảnh báo bảo mật.
- Thiết bị đột ngột yêu cầu cấu hình lại profile Wi-Fi hoặc tắt certificate validation để “khôi phục kết nối”.
- Nhiều người cùng khu vực gặp prompt đăng nhập bất thường, trong khi controller/RADIUS không ghi nhận kịch bản thay đổi được phép.

**Không dùng riêng giao diện đẹp, logo, SSID hoặc tín hiệu Wi-Fi mạnh để xác thực portal.** Trang thật cũng có thể xuất hiện trên mạng hợp lệ, vì vậy cần so sánh với quy trình chính thức.

### 7.2. HTTPS, HSTS và MFA giúp gì?

HTTPS/TLS với **kiểm tra chứng thư và tên máy chủ đúng** bảo vệ nội dung giữa client và dịch vụ ứng dụng, kể cả khi mạng truy cập không đáng tin. **HSTS** trên những website có áp dụng giúp trình duyệt không hạ cấp sang HTTP trong các điều kiện được bảo vệ.

Nhưng HTTPS không tự ngăn việc người dùng nhập thông tin vào **một website giả có HTTPS hợp lệ cho chính domain giả đó**. MFA có thể giảm tác động của một số kiểu đánh cắp mật khẩu, nhưng **không loại bỏ mọi loại phishing**; nên kết hợp phương thức MFA chống lừa đảo, xác minh tên miền và chính sách danh tính.

## 8. Protected Management Frames (PMF) và giới hạn của nó

**Protected Management Frames (PMF)**, liên quan tới khả năng bảo vệ khung quản lý 802.11, giúp bảo vệ một số **robust management frames** sau khi các bên đã thương lượng và thiết lập khóa phù hợp. Đây là biện pháp quan trọng để giảm khả năng giả mạo một số khung quản lý gây gián đoạn.

### 8.1. PMF bảo vệ điều gì?

Theo khả năng và chế độ triển khai, PMF giúp bảo vệ tính toàn vẹn và nguồn phát đối với một số khung quản lý đã được bảo vệ, ví dụ những khung hủy kết nối (*deauthentication*) và ngắt association (*disassociation*) trong phạm vi áp dụng.

**PMF không mã hóa hoặc xác thực mọi beacon/probe response trước khi association**, cũng **không chứng minh bằng mật mã rằng tên SSID là của một tổ chức cụ thể**. Vì vậy, bật PMF là biện pháp hữu ích chống một số hành vi ở lớp quản lý nhưng **không thể coi là giải pháp duy nhất cho Evil twin**.

### 8.2. PMF trong các chế độ WPA

WPA3 yêu cầu PMF theo mô hình bảo mật WPA3 được áp dụng, nhưng khả năng của client và cấu hình thiết bị trong môi trường có transition mode cần được xác minh. Nếu thiết bị IoT cũ không hỗ trợ PMF đúng yêu cầu, hãy phân đoạn và quản lý ngoại lệ, không nới toàn bộ chính sách Wi-Fi doanh nghiệp chỉ để một thiết bị kết nối.

### 8.3. Vì sao Wi-Fi vẫn có thể bị gián đoạn?

Ngay cả khi PMF hoạt động, chất lượng kết nối vẫn bị ảnh hưởng bởi nhiễu vô tuyến, mất sóng, cấu hình AP, lỗi phần mềm và các loại frame không nằm trong phạm vi bảo vệ của PMF. Một client mất kết nối hoặc đổi BSSID **không tự là bằng chứng có deauthentication attack**.

## 9. WIDS/WIPS phát hiện Evil twin ra sao?

**Wireless Intrusion Detection System (WIDS)** quan sát các sự kiện 802.11 để phát hiện những dấu hiệu bất thường trong vùng phủ sóng. **Wireless Intrusion Prevention System (WIPS)** có thể bổ sung khả năng phản ứng theo nền tảng, nhưng phương thức can thiệp cần tuân thủ quy định, phạm vi sở hữu và chính sách của tổ chức.

Một số dữ liệu có ích:

- SSID và BSSID được nhìn thấy ở nhiều vị trí đo.
- Kênh/tần số, kiểu bảo mật, RSN information và trạng thái PMF được quảng bá.
- Tương quan với **inventory AP hợp pháp**, controller/cloud manager và danh mục thay đổi.
- AP lạ quảng bá SSID được bảo vệ nhưng có cấu hình bảo mật khác với baseline.
- Mẫu di chuyển/roaming và sự kiện kết nối bất thường trên thiết bị đã quản lý.
- Nhật ký RADIUS/EAP về máy chủ xác thực, thất bại chứng thư và thay đổi profile.
- Tín hiệu RF lặp lại ở nhiều cảm biến và thời điểm, thay vì một lần quét duy nhất.

### 9.1. Pipeline phát hiện

~~~mermaid
flowchart TD
    RF["WIDS / controller quan sát beacon và telemetry"] --> C["Chuẩn hóa SSID, BSSID, security profile, vị trí, thời gian"]
    C --> M{"Khớp AP inventory và cấu hình kỳ vọng?"}
    M -->|Có| OK["Quan sát vận hành bình thường"]
    M -->|"Chưa rõ hoặc không khớp"| A["Cảnh báo candidate / unknown AP"]
    A --> V["Đối chiếu thay đổi, RADIUS, thiết bị, RF sensors"]
    V --> D{"Bằng chứng mạo nhận đã đủ?"}
    D -->|Không| N["Ghi nhận, tiếp tục quan sát, không quy kết"]
    D -->|Có| I["Ứng phó: bảo vệ client, cô lập tài sản thuộc quyền quản lý, điều tra"]
~~~

**Một BSSID không có trong inventory là dấu hiệu cần xác minh**, không phải kết luận tấn công. AP mới chưa cập nhật dữ liệu, thiết bị khách hợp lệ, môi trường đa BSSID hoặc thay đổi phần cứng đều có thể tạo cảnh báo nhầm.

### 9.2. Passive detection và active containment

**Passive detection** thu thập beacon, telemetry/controller và sự kiện xác thực mà không chủ động can thiệp phiên người khác. Đây là điểm khởi đầu phù hợp cho giám sát và lab an toàn.

**Active containment** là nhóm biện pháp chủ động ngăn hoạt động AP hoặc client theo khả năng của WIPS. Một số kỹ thuật tác động lên môi trường vô tuyến của người khác có thể gây gián đoạn hoặc vi phạm quy định. Không tự bật chức năng gây mất kết nối cho AP lạ chỉ dựa trên cảnh báo SSID trùng; phải có **xác minh sở hữu, phê duyệt, phạm vi và phương án thay thế ít gây tác động hơn**.

### 9.3. Cảnh báo theo mức độ bằng chứng

| Mức | Dấu hiệu | Kết luận nên dùng |
| --- | --- | --- |
| Thấp | SSID trùng tên trong vùng RF | Mạng cùng tên, **chưa xác định giả mạo** |
| Trung bình | SSID thuộc tổ chức xuất hiện với security mode hoặc BSSID bất thường | **Suspected impersonation**, cần đối chiếu inventory |
| Cao hơn | Có dữ liệu từ nhiều cảm biến, profile client bất thường, xác thực tới endpoint không được phép và không có change ticket | Nghi vấn có cơ sở, cần điều tra ưu tiên |
| Đã xác minh | Bằng chứng cụ thể của AP mạo nhận trong phạm vi được quản lý, kèm hoạt động lừa người dùng hoặc cấu hình trái phép | Incident được xác nhận theo quy trình tổ chức |

Không dùng địa chỉ MAC hoặc RSSI đơn lẻ để quy kết cá nhân, vị trí chính xác hoặc ý định tấn công.

## 10. Cách nhận diện và kiểm tra trên thiết bị được phép

Kỹ thuật viên có thể thu thập thông tin **trên thiết bị do mình quản lý** để đối chiếu với bộ phận mạng, không cần thử đăng nhập vào AP nghi vấn.

### 10.1. Windows: xem kết nối đang sử dụng

Trong PowerShell hoặc Command Prompt:

~~~powershell
netsh wlan show interfaces
~~~

Kết quả có thể hiển thị SSID, BSSID, radio type, channel, authentication, cipher và tín hiệu tùy phiên bản Windows/driver. Nếu thiết bị không có card Wi-Fi hoặc bị chính sách quản trị giới hạn, một số trường có thể không tồn tại.

Để xem những mạng Wi-Fi có thể nhìn thấy:

~~~powershell
netsh wlan show networks mode=bssid
~~~

**Đây là thao tác quan sát trên máy đã được phép quản lý**, không tự kết nối hay khai thác mạng khác. Thông tin quét tại một thời điểm chỉ phản ánh radio đang nghe thấy; nó không chứng minh AP là hợp pháp hoặc độc hại.

### 10.2. Linux với NetworkManager

Trên máy Linux có NetworkManager và card Wi-Fi phù hợp:

~~~bash
nmcli -f IN-USE,SSID,BSSID,SECURITY,SIGNAL device wifi list
~~~

Lệnh đọc danh sách mạng đang được NetworkManager ghi nhận. Dữ liệu có thể khác giữa driver, trạng thái scan, quyền và phiên bản công cụ. **Không sử dụng danh sách SSID/BSSID thu được để kết luận tấn công** nếu chưa đối chiếu inventory và cấu hình của tổ chức.

### 10.3. Kết quả cần ghi lại

| Trường | Ví dụ giả lập | Cách dùng |
| --- | --- | --- |
| Timestamp | 2026-11-28 14:30 +07 | Liên kết với thay đổi và log controller |
| SSID | Office-Secure | Xác định profile mà người dùng đang tìm |
| BSSID | 02:00:00:00:16:06 | So với danh mục AP; địa chỉ giả lập |
| Authentication | WPA2-Enterprise | So với chính sách bảo mật dự kiến |
| Channel | 36 | Hỗ trợ tương quan RF, không xác định sở hữu |
| Client profile | MDM-managed | Biết thiết bị có policy cert/server hay không |
| Controller membership | unknown/verified | Đối chiếu hệ thống quản trị AP |
| EAP result | server certificate mismatch | Bằng chứng hữu ích cần điều tra riêng |

Không thu thập mật khẩu, private key, cookie phiên hoặc token người dùng để “kiểm tra AP giả”.

## 11. Xây dựng baseline Wi-Fi doanh nghiệp

Phòng vệ Evil twin hiệu quả bắt đầu từ **biết rõ mạng hợp lệ trông như thế nào**. Nếu không có baseline, WIDS sẽ khó phân biệt AP lạ với thay đổi được phép.

### 11.1. Danh mục cần quản lý

| Hạng mục | Ví dụ dữ liệu | Chủ sở hữu |
| --- | --- | --- |
| SSID được cấp phép | Office-Secure, Office-Guest, IoT-Managed | Network / Security |
| Security mode | WPA3-Enterprise hoặc WPA2-Enterprise theo lộ trình | Network / Endpoint |
| EAP method và server identity | EAP-TLS, CA và tên RADIUS server mong đợi | Identity / PKI |
| AP inventory | AP ID, serial, radio/BSSID, địa điểm, controller | Wireless operations |
| Guest portal được duyệt | Domain và cách đăng nhập công bố chính thức | Guest network owner |
| Phân vùng VLAN/role | Employee, Guest, IoT, Management | Network / Security |
| Quản lý thiết bị | MDM profile, chứng thư client, compliance | Endpoint / IAM |
| Monitoring | WIDS/WIPS, RADIUS, DHCP/DNS, controller log | SOC / NOC |
| Quy trình thay đổi | Thêm AP, đổi SSID, thay cert, firmware | Change management |

**BSSID có thể thay đổi khi thêm AP, thay radio hoặc thay firmware/cấu hình.** Danh mục nên có cơ chế đồng bộ với controller thay vì hard-code một danh sách vĩnh viễn.

### 11.2. Chọn những kiểm soát ưu tiên

1. **SSID Enterprise riêng cho tài sản quản lý:** dùng 802.1X và phương thức EAP được duyệt, ưu tiên EAP-TLS khi hạ tầng hỗ trợ.
2. **MDM cấp profile xác thực máy chủ:** CA và server name chặt, không cho người dùng bỏ qua bước kiểm tra.
3. **Guest Wi-Fi tách biệt:** có portal/domain công bố rõ ràng và không yêu cầu mật khẩu tài khoản nội bộ ngoài quy trình chính thức.
4. **IoT không hỗ trợ Enterprise:** đưa vào SSID/VLAN riêng, mật khẩu riêng hoặc cơ chế định danh phù hợp, kiểm soát quyền tối thiểu.
5. **WIDS/WIPS và inventory:** quan sát AP lạ, thay đổi security mode và xác thực bất thường.
6. **Phân đoạn mạng và firewall:** giới hạn đường kết nối sau khi client được cấp quyền; một thiết bị trên Guest không tự có đường tới Management/Data.
7. **Cập nhật và đào tạo người dùng:** đặc biệt cảnh báo chứng thư Wi-Fi và trang yêu cầu nhập mật khẩu trái quy trình.

## 12. Phân đoạn và bảo vệ lưu lượng sau khi kết nối

Giả sử doanh nghiệp có ba mạng Wi-Fi:

| Mạng | Đối tượng | Kiểm soát chính | Quyền mạng dự kiến |
| --- | --- | --- | --- |
| **Office-Secure** | Laptop đã quản lý | Enterprise/802.1X, EAP-TLS, cert validation, MDM | Chỉ ứng dụng doanh nghiệp theo quyền |
| **Office-Guest** | Khách, đối tác tạm thời | Portal được phê duyệt hoặc chế độ bảo mật guest phù hợp | Internet, không vào management/data |
| **Office-IoT** | Thiết bị IoT được đăng ký | Cơ chế xác thực hỗ trợ bởi thiết bị + NAC/ACL | Chỉ DNS/NTP/backend IoT cần thiết |

~~~mermaid
flowchart TD
    C["Laptop đã quản lý"] --> S["Office-Secure / Enterprise EAP-TLS"]
    G["Khách"] --> GS["Office-Guest"]
    I["IoT"] --> IS["Office-IoT"]
    S --> NAC["Identity / NAC / role policy"]
    NAC --> FW["Firewall / segmentation"]
    GS --> GF["Guest firewall: chỉ Internet theo policy"]
    IS --> IF["IoT firewall: dịch vụ tối thiểu"]
    FW --> APP["Application services"]
    FW -. "Chỉ quản trị được phép" .-> MG["Management zone"]
    GS -. "Deny" .-> MG
    IS -. "Deny" .-> MG
    S -. "RADIUS/EAP logs" .-> SOC["SOC / WIDS / SIEM"]
    GS -. "Portal/controller logs" .-> SOC
    IS -. "Client inventory" .-> SOC
~~~

Sơ đồ mô tả **kiến trúc hợp lệ**; không giả định mọi Wi-Fi Enterprise đều có mạng nội bộ rộng. Việc xác thực được thiết bị chỉ là một bước: truy cập dữ liệu còn cần phân quyền người dùng/ứng dụng, firewall, TLS và kiểm toán.

### 12.1. DNS, DHCP và kết nối Internet

Sau khi client kết nối vào một mạng không tin cậy, nó có thể nhận thông tin gateway/DNS theo hạ tầng của mạng đó. Các biện pháp bảo vệ như DNSSEC validation tại resolver tin cậy, DoH/DoT và HTTPS/TLS có vai trò riêng; **DNSSEC không xác thực danh tính AP** và **DoH không làm portal giả trở thành thật**.

Trong mạng doanh nghiệp, DHCP snooping, DAI, IP Source Guard, RA Guard và egress policy góp phần giảm một số kiểu cấu hình trái phép **trên những đoạn mạng mà thiết bị thực thi quan sát được**. Nhưng nếu người dùng đã kết nối vào một AP ngoài quyền quản lý, switch của doanh nghiệp có thể hoàn toàn không thấy traffic đó.

### 12.2. VPN có ích nhưng không phải thuốc chữa mọi rủi ro

VPN sử dụng cơ chế bảo vệ mật mã phù hợp có thể bảo vệ dữ liệu đi qua tunnel khi người dùng ở mạng Wi-Fi không tin cậy. Tuy nhiên, một trang phishing có thể xuất hiện **trước khi VPN hoạt động**, hoặc người dùng tự nhập thông tin vào domain giả ngay cả khi VPN đã bật.

Vì vậy VPN là **lớp bổ sung**, không thay thế kiểm tra chứng thư Wi-Fi Enterprise, xác thực HTTPS, bảo vệ danh tính và hướng dẫn người dùng.

## 13. Mẫu chính sách vận hành trung lập với nhà cung cấp

Đây là ví dụ **YAML mô tả chính sách** để nhóm Network, IAM, SOC và Endpoint thống nhất mục tiêu, **không phải cấu hình có thể áp dụng trực tiếp lên controller, MDM hoặc WIPS**.

~~~yaml
wirelessEvilTwinDefense:
  environment: managed-enterprise-and-training-lab
  protectedNetworks:
    - ssid: Office-Secure
      classification: managed-enterprise
      requiredSecurity: approved-enterprise-eap-profile
      preferredEapMethod: EAP-TLS
      requireServerCertificateValidation: true
      approvedEapServers: managed-by-identity-team
      profileDistribution: MDM
      allowUserCertificateBypass: false
    - ssid: Office-Guest
      classification: guest
      portalDomain: managed-and-verified-by-network-team
      allowInternalPasswordCollection: false
      segmentation: guest-to-internet-only
    - ssid: Office-IoT
      classification: restricted-devices
      segmentation: approved-iot-services-only
  monitoring:
    sources:
      - wlan-controller-inventory
      - wireless-ids
      - radius-eap-events
      - managed-endpoint-wifi-events
      - guest-portal-events
    suspiciousSignals:
      - protected-ssid-with-unapproved-security-mode
      - unexpected-eap-server-certificate
      - unexplained-radio-identity-changes
      - unexpected-credential-portal
    requiredEvidence:
      - timestamp-and-location-context
      - authorized-ap-inventory-check
      - policy-or-change-ticket-correlation
  response:
    preferPassiveVerification: true
    prohibitUnapprovedRadioDisruption: true
    isolateOnlyAssetsUnderOwnAdministration: true
    requireIncidentOwner: true
    redactSensitiveClientData: true
~~~

Những khóa như **approvedEapServers** chỉ định **yêu cầu quản trị**, không định nghĩa cơ chế kỹ thuật tự xác minh của mọi OS. Triển khai thật phải kiểm tra cách Windows, macOS, iOS, Android, Linux hoặc thiết bị IoT áp dụng profile/cert qua MDM và những ngoại lệ tương thích.

## 14. Log và telemetry hữu ích cho SOC

Một báo động Evil twin tốt không chỉ có SSID/BSSID; nó phải mô tả **vì sao mạng được đánh giá bất thường và đã có tác động đến client nào hay chưa**.

| Trường | Vì sao cần |
| --- | --- |
| Event time và sensor ID | Biết cảm biến nào quan sát, tại thời điểm nào |
| SSID/BSSID/channel/security mode | Tìm đúng radio/profile liên quan |
| AP inventory match | Phân biệt AP được quản lý với AP chưa có trong hệ thống |
| EAP/certificate validation result | Phát hiện cấu hình hoặc danh tính máy chủ bất thường |
| Endpoint policy/profile version | Đối chiếu xem client đã nhận cấu hình MDM mới chưa |
| Wi-Fi association/disassociation | Xem biến động kết nối, nhưng không tự kết luận tấn công |
| RADIUS/NAC logs | Biết xác thực hợp lệ có xảy ra không |
| DHCP/DNS/portal metadata | Tìm khác biệt về cấu hình hoặc trang đăng nhập |
| Related change ticket | Tránh false positive trong đợt thêm AP/đổi cert |
| Response action và kết quả | Phân biệt cảnh báo, cô lập có phép và đã xác minh khôi phục |

### 14.1. Log giả lập

~~~json
{
  "timestamp": "2026-11-28T14:30:00+07:00",
  "event": "wireless_ap_impersonation_candidate",
  "sensor_id": "wids-floor-2-lab",
  "ssid": "Office-Secure",
  "observed_bssid": "02:00:00:00:16:06",
  "channel": 36,
  "advertised_security": "open",
  "expected_security": "managed-enterprise-eap",
  "ap_inventory_match": false,
  "endpoint_connection_verified": false,
  "radius_event_correlation": "not-yet-available",
  "decision": "investigate",
  "classification": "synthetic-training-event"
}
~~~

Trong ví dụ, một AP phát **Office-Secure** ở chế độ **open**, khác với chính sách Enterprise. Đây là dấu hiệu ưu tiên điều tra, **chưa chứng minh thiết bị nào đã kết nối hoặc có dữ liệu bị lộ**. Một SSID trùng và security mode khác có thể là mạng mạo nhận, nhưng vẫn cần dữ liệu bổ sung để xác minh.

### 14.2. Nguyên tắc bảo vệ dữ liệu người dùng

Wi-Fi telemetry có thể chứa định danh thiết bị, vị trí tương đối hoặc dữ liệu hành vi. Hãy chỉ thu thập thông tin cần cho sự cố, đặt thời hạn lưu giữ, phân quyền truy cập và che dữ liệu nhạy cảm khi chia sẻ log. Không yêu cầu người dùng cung cấp mật khẩu, khóa riêng/chứng thư client hoặc toàn bộ lưu lượng cá nhân để “chứng minh” Evil twin.

## 15. Quy trình triage khi nghi có Evil twin

### Giai đoạn 1 – Tiếp nhận và xác minh sơ bộ

1. Ghi **SSID, thời điểm, khu vực quan sát, loại security mode** và nguồn cảnh báo.
2. Đối chiếu AP inventory/controller, kế hoạch thêm AP, thay firmware, đổi BSSID hoặc triển khai SSID mới.
3. Kiểm tra nhiều nguồn nếu có: WIDS sensors, controller logs, endpoint profile và RADIUS/EAP validation errors.
4. Xác định **có client nào đang kết nối tới AP nghi vấn hay không** dựa trên thông tin hợp pháp có sẵn; không ép client kết nối để thử.
5. Đánh giá tính chất bất thường: cùng SSID nhưng security khác, prompt đăng nhập mới hay chứng thư máy chủ không mong đợi.

### Giai đoạn 2 – Bảo vệ người dùng và hệ thống

1. Gửi thông báo rõ ràng: dùng **profile Wi-Fi doanh nghiệp do MDM cấp**, không bỏ qua cảnh báo cert và không nhập thông tin vào portal lạ.
2. Nếu thiết bị quản lý đang kết nối mạng nghi vấn, hướng dẫn **ngắt kết nối và chuyển sang mạng đã xác minh** theo runbook.
3. Với AP nằm trên hạ tầng **do tổ chức sở hữu**, kiểm tra switch port, controller, NAC và cân nhắc cô lập ở điểm mạng được phép sau khi xác minh.
4. Không tự ngắt radio, gây nhiễu hoặc tác động tới AP của bên thứ ba chỉ vì SSID trùng; phải theo quy định và quy trình phê duyệt.
5. Nếu có bằng chứng người dùng đã nhập thông tin vào portal giả, kích hoạt quy trình ứng phó danh tính và đánh giá phiên đăng nhập bị ảnh hưởng.

### Giai đoạn 3 – Điều tra tác động

- Kiểm tra dấu hiệu giả mạo xác thực EAP và tình trạng certificate validation trên client.
- Đối chiếu portal/domain với hệ thống guest thực và log đăng nhập thuộc quyền quản trị.
- Xem có dấu hiệu kết nối đến domain không được phép, sự kiện proxy/TLS hay ứng dụng cảnh báo không.
- Xác định dữ liệu nào **thực sự có thể bị phơi lộ** dựa vào giao thức sử dụng, không khẳng định mọi HTTPS đã bị đọc.
- Phân loại mức độ bằng chứng: candidate, suspicious, confirmed impersonation, confirmed credential exposure.

### Giai đoạn 4 – Khôi phục và cải tiến

1. Xác minh thiết bị quay lại đúng profile và EAP server.
2. Kiểm tra chứng thư, CA, server name, trạng thái revocation và chính sách MDM.
3. Rà soát AP inventory, WIDS rule, các ngoại lệ do thay đổi hợp lệ.
4. Phân đoạn lại hoặc nâng cấp thiết bị yếu không hỗ trợ bảo mật phù hợp.
5. Cập nhật runbook, tài liệu guest portal và truyền thông người dùng.

**Đừng kết luận đã khắc phục chỉ vì SSID lạ biến mất khỏi một lần scan.** Radio có thể ra ngoài vùng phủ hoặc tạm dừng; phải xác minh client an toàn, policy đã được khôi phục và không còn dấu hiệu xác thực trái phép trên những nguồn quan sát có liên quan.

## 16. Điều tra false positive và false negative

### 16.1. False positive

**False positive** là trường hợp hệ thống báo Evil twin nhưng thực tế không có AP mạo nhận trong sự kiện được đánh giá. Một số nguyên nhân:

- Controller mới triển khai AP hợp lệ nhưng inventory chưa cập nhật.
- Cùng SSID doanh nghiệp xuất hiện trên nhiều radio/BSSID là thiết kế bình thường.
- Tính năng multi-BSSID, thay phần cứng hoặc firmware làm định danh radio thay đổi.
- WIDS quan sát AP từ doanh nghiệp bên cạnh dùng tên SSID phổ biến.
- Nhân viên dùng mạng lab được cấp phép có SSID giống bản production trong vùng cách ly.
- Client báo lỗi chứng thư do **chứng thư máy chủ hợp lệ hết hạn**, không phải Evil twin.

**Cách xử lý:** xác minh asset, change ticket, controller membership và danh tính EAP; sau đó điều chỉnh ngưỡng hoặc ngoại lệ **có phạm vi**, không tắt toàn bộ cảnh báo mạo nhận SSID.

### 16.2. False negative

**False negative** là trường hợp AP mạo nhận hoặc hoạt động lừa đảo không được nhận diện:

- WIDS không phủ sóng khu vực xảy ra sự kiện.
- AP xuất hiện ngắn, di chuyển hoặc chỉ hoạt động ở thời điểm ngoài lịch giám sát.
- WIDS dựa chủ yếu vào BSSID whitelist và thiếu kiểm tra security mode/cert.
- Người dùng kết nối một mạng ngoài khuôn viên, ngoài phạm vi cảm biến.
- Client có cấu hình chấp nhận chứng thư máy chủ bất kỳ và không chuyển lỗi về hệ thống quản trị.

**Cách giảm:** bổ sung telemetry từ endpoint được quản lý, EAP/RADIUS, MDM, hướng dẫn người dùng báo sự kiện và kiểm tra các lớp phòng vệ độc lập. WIDS không thay thế xác thực đúng của client.

## 17. Kiểm thử phòng vệ trong lab được ủy quyền

Thực hành nên diễn ra trong **mạng thử nghiệm cô lập hoặc môi trường RF được phép**, không mô phỏng lấy thông tin đăng nhập người dùng thật và không gây gián đoạn tới các Wi-Fi lân cận.

### 17.1. Ma trận kiểm thử

| Mã | Kiểm thử | Kỳ vọng |
| --- | --- | --- |
| T-01 | Laptop dùng profile Enterprise đã cấp qua MDM kết nối AP hợp lệ | Xác thực EAP đúng chứng thư và vào VLAN/role được duyệt |
| T-02 | Thay đổi chứng thư máy chủ EAP ở lab sang chứng thư **không nằm trong trust policy** | Client từ chối xác thực; có log để điều tra |
| T-03 | Quan sát một SSID trùng tên trong bộ dữ liệu RF **giả lập** | Hệ thống chỉ tạo candidate, không tự quy kết attack |
| T-04 | Dữ liệu giả lập có cùng SSID nhưng security mode đổi Enterprise → Open | WIDS cảnh báo khác cấu hình và yêu cầu xác minh |
| T-05 | AP hợp lệ mới được đưa vào inventory theo change ticket | Không tạo incident giả sau khi dữ liệu đồng bộ |
| T-06 | Guest portal lab ở domain đã duyệt | Người dùng xác minh domain, không bị đòi mật khẩu công ty trái quy trình |
| T-07 | Người dùng thử truy cập ứng dụng HTTPS qua Wi-Fi guest lab | Kết nối dùng TLS hợp lệ, không bỏ qua cảnh báo chứng thư |
| T-08 | Client IoT cũ không hỗ trợ profile mới | Xử lý qua vùng/SSID có giới hạn, không nới policy toàn công ty |
| T-09 | Cảm biến không quan sát được một vị trí trong sơ đồ RF | Báo rõ khoảng trống bao phủ, không kết luận không có AP giả |
| T-10 | Diễn tập nghi vấn portal giả bằng **ảnh chụp hoặc kịch bản giấy** | Helpdesk/SOC kích hoạt đúng playbook danh tính, không thu thập mật khẩu |
| T-11 | PMF được bật theo policy trên lab AP/client | Xác nhận cấu hình hỗ trợ, không kết luận đã chống mọi mạo nhận SSID |
| T-12 | MDM cập nhật CA/server name có kế hoạch | Client vẫn xác thực với server được duyệt, có đường rollback |

### 17.2. Bằng chứng cần thu thập

- Mô hình lab và quyền sử dụng AP, thiết bị, phổ RF được thỏa thuận.
- SSID, security mode, CA/server identity kỳ vọng và profile MDM.
- Sự kiện RADIUS/EAP và controller liên quan đến client lab.
- Kết quả kết nối thành công/thất bại theo từng case, không chỉ kết quả scan.
- Cảnh báo WIDS, lý do rule khớp và các điều kiện false positive.
- Trạng thái VLAN/role, đường truy cập ứng dụng, kết quả TLS.
- Thay đổi, người duyệt, timestamp và phương án hoàn nguyên.

Không cần thu thập mật khẩu thật hoặc dựng cổng đăng nhập giả để đạt mục tiêu **kiểm chứng client từ chối endpoint xác thực không được tin cậy**.

## 18. Kịch bản tổng hợp: cùng SSID nhưng chế độ bảo mật khác

Một nhân viên thấy hai mạng tên **Office-Secure** tại khu vực chờ:

- Mạng A: thiết bị kết nối theo profile MDM, dùng **WPA2-Enterprise/EAP-TLS**, chứng thư RADIUS đúng danh tính được duyệt, BSSID thuộc inventory.
- Mạng B: quảng bá cùng SSID nhưng hiển thị là **Open**, BSSID chưa có trong inventory và không có change ticket. Một người dùng nhìn thấy trang yêu cầu nhập tài khoản công ty để “kích hoạt Wi-Fi”.

### 18.1. Phân tích ban đầu

Mạng B có **nhiều dấu hiệu đáng ngờ**: security mode không khớp baseline, nguồn radio không được kiểm chứng và portal có yêu cầu nhạy cảm ngoài quy trình. Tuy nhiên, chỉ từ bản scan không thể chứng minh ai sở hữu thiết bị hoặc đã có dữ liệu bị đánh cắp.

### 18.2. Kiểm soát nào có giá trị?

1. **MDM + EAP-TLS:** thiết bị quản lý chỉ hoàn tất xác thực khi server/cert phù hợp; không tự hạ xuống mạng Open như profile Enterprise.
2. **WIDS/controller:** đối chiếu BSSID, radio profile, khu vực và danh mục thay đổi.
3. **Quy trình portal:** người dùng biết chỉ dùng domain được IT công bố; không nhập mật khẩu công ty vào trang không xác minh.
4. **HTTPS/TLS/VPN:** giảm rủi ro dữ liệu ứng dụng khi ở mạng ngoài tin cậy, nhưng không thay thế phòng phishing.
5. **SOC/NOC:** kết hợp log và bằng chứng trước khi công bố một sự cố đã xác nhận.

### 18.3. Hành động phù hợp

Thông báo người dùng không kết nối mạng B; thu thập telemetry hợp pháp từ thiết bị quản lý; kiểm tra inventory/controller và chứng thư EAP; điều tra portal/domain qua bộ phận có quyền; xử lý thông tin đăng nhập nếu có bằng chứng đã bị nhập vào hệ thống giả. **Không tự tìm cách ngắt kết nối mạng B bằng các thao tác vô tuyến ảnh hưởng bên thứ ba.**

### 18.4. Kết luận

Mức độ nguy hiểm của Evil twin phụ thuộc **người dùng có thực sự kết nối hay bị lừa cung cấp thông tin hay không** và các cơ chế bảo vệ độc lập đã hoạt động ra sao. Một Wi-Fi Enterprise có profile xác thực server đúng, cộng với giám sát và truyền thông phù hợp, giúp giảm đáng kể rủi ro nhầm mạng.

## 19. Những sai lầm thường gặp

| Sai lầm | Vì sao không đúng | Cách làm phù hợp |
| --- | --- | --- |
| “Hai BSSID trùng SSID là Evil twin” | Roaming doanh nghiệp thường có nhiều BSSID | So với inventory/controller và security mode |
| “BSSID là danh tính mật mã không thể giả mạo” | Địa chỉ MAC không chứng minh sở hữu AP | Xác thực EAP/cert, dữ liệu quản trị nhiều nguồn |
| “AP có SSID và mật khẩu giống là AP chính hãng” | Mật khẩu chung không phân biệt duy nhất một AP | Quản lý khóa và inventory; Enterprise khi phù hợp |
| “WPA3 luôn loại bỏ Evil twin” | Chế độ/khóa và danh tính AP còn phụ thuộc cấu hình | Xác minh cơ chế, dùng Enterprise với validation đúng |
| “PMF xác thực toàn bộ beacon nên không còn AP giả” | PMF bảo vệ tập khung quản lý theo điều kiện, không xác thực mọi quảng bá | Dùng kết hợp EAP/cert/WIDS |
| “Mạng Open có OWE nghĩa là biết chắc AP thật” | OWE bảo vệ mã hóa liên kết, không định danh tổ chức | Đánh giá danh tính mạng và TLS/portal |
| “Chỉ cần bật VPN là an toàn với trang đăng nhập giả” | Phishing có thể xảy ra trước hoặc ngoài tunnel | Kiểm tra domain, MFA chống phishing và hướng dẫn người dùng |
| “Chứng thư EAP lỗi thì bấm tiếp tục” | Có thể làm mất ràng buộc xác thực máy chủ | Kiểm tra với IT, không tự bỏ validation |
| “Rogue AP nào cũng là attacker” | Có thể là cấu hình nhầm hoặc thiết bị bên cạnh | Triage dựa trên bằng chứng và quyền quản lý |
| “Cứ bật WIPS containment với AP lạ” | Có thể gây gián đoạn vô tuyến ngoài quyền sở hữu | Passive detection, xác minh, phê duyệt trước hành động |
| “Không có alert nghĩa là không có Evil twin” | Cảm biến có thể không phủ sóng hoặc client ở ngoài cơ sở | Telemetry endpoint, đào tạo, EAP validation và kiểm tra coverage |
| “Bảo vệ Wi-Fi đủ thì khỏi cần firewall/DNS/TLS” | Rủi ro nhiều lớp vẫn tồn tại sau association | Phân đoạn, mã hóa ứng dụng, DNS và giám sát |

## 20. Câu hỏi và bài tập tự kiểm tra

### Câu hỏi 1

SSID có phải định danh duy nhất của một mạng Wi-Fi hợp pháp không? Vì sao nhiều AP cùng SSID có thể là hành vi bình thường?

**Gợi ý:** SSID là tên mạng dùng chung; nhiều AP do tổ chức quản lý cùng phát một SSID cho roaming, có BSSID riêng.

### Câu hỏi 2

Evil twin và rogue AP khác nhau ở đâu? Vì sao không nên gọi mọi rogue AP là Evil twin?

**Gợi ý:** Evil twin có yếu tố mạo nhận mạng tin cậy; rogue AP chỉ nói chưa được tổ chức phê duyệt và có thể do cắm nhầm.

### Câu hỏi 3

Tại sao mạng WPA2-Personal có mật khẩu không tự chứng minh mỗi AP là AP do tổ chức quản lý?

**Gợi ý:** mật khẩu chia sẻ giúp thiết lập khóa với những bên biết khóa; không cung cấp danh tính riêng cho từng AP trong inventory.

### Câu hỏi 4

Khi dùng Wi-Fi Enterprise, điều gì xảy ra nếu client được cấu hình chấp nhận mọi chứng thư máy chủ EAP?

**Gợi ý:** ràng buộc danh tính server bị suy yếu, tăng rủi ro xác thực với endpoint không được duyệt.

### Câu hỏi 5

PMF giúp giảm rủi ro gì và tại sao không thể chỉ bật PMF để giải quyết mọi Evil twin?

**Gợi ý:** PMF bảo vệ một số robust management frames theo điều kiện; không xác thực toàn bộ beacon hoặc quyền sở hữu SSID.

### Câu hỏi 6

Vì sao một captive portal giả có thể nguy hiểm ngay cả khi những ứng dụng khác vẫn dùng HTTPS?

**Gợi ý:** người dùng có thể bị lừa tự nhập thông tin vào domain giả; TLS có thể hợp lệ cho chính domain giả.

### Câu hỏi 7

Một WIDS phát hiện BSSID mới với SSID Office-Secure. Đội SOC cần thêm bằng chứng nào trước khi kết luận là Evil twin?

**Gợi ý:** inventory, security mode, địa điểm, thay đổi đã được phê duyệt, chứng thư EAP và telemetry client.

### Câu hỏi 8

Vì sao AP ở mạng lân cận có thể gây false positive và WIDS đặt trong một tòa nhà không bảo đảm phát hiện Evil twin ở quán cà phê?

**Gợi ý:** vùng phủ sóng vô tuyến vượt ranh giới sở hữu và cảm biến chỉ thấy phần RF tại vị trí quan sát.

### Bài tập thiết kế

Một công ty có **Office-Secure (802.1X)**, **Office-Guest** và **IoT-Lab**. Có các AP do controller quản lý, một RADIUS server, thiết bị Windows/macOS qua MDM và cảm biến WIDS. Hãy:

1. Vẽ đường kết nối từ laptop tới AP và RADIUS server; chỉ rõ bước **client kiểm tra danh tính EAP server**.
2. Lập danh sách các trường AP/radio/profile tối thiểu cần trong inventory.
3. Viết chính sách cho một AP mới cùng SSID nhưng chưa có trong inventory và một AP lạ có security mode khác.
4. Đề xuất hai negative test về chứng thư EAP và portal không đúng domain bằng **lab/giả lập**, không dùng mật khẩu thật.
5. Nêu vai trò và giới hạn của PMF, WPA3-Personal, EAP-TLS, HTTPS, VPN và WIDS trong bài toán này.
6. Thiết kế ma trận phân đoạn giữa Employee, Guest, IoT, Management và Data.
7. Viết runbook khi người dùng báo “Wi-Fi công ty yêu cầu nhập lại mật khẩu vào một website lạ”.

**Tiêu chí đạt:** không dựa riêng vào SSID/BSSID, biết cách xác minh EAP server, duy trì kết nối hợp lệ và chỉ kết luận sự cố theo mức bằng chứng thực tế.

## 21. Những điều cần ghi nhớ

- **Evil twin là hành vi mạo nhận mạng Wi-Fi đáng tin**, không phải mọi AP cùng tên hay mọi BSSID lạ.
- **SSID và BSSID hỗ trợ nhận diện/giám sát, nhưng không tự là chứng cứ xác thực danh tính AP.**
- **Mức rủi ro phụ thuộc chế độ bảo mật.** Open/portal, Personal và Enterprise cần những biện pháp khác nhau; không khẳng định sao chép SSID đủ vượt qua WPA2/WPA3.
- **Wi-Fi Enterprise phải xác minh đúng chứng thư và tên máy chủ EAP**; EAP-TLS và MDM quản lý profile giúp giảm rủi ro giả mạo hệ thống xác thực.
- **PMF bảo vệ một phần khung quản lý; OWE mã hóa kết nối open; VPN/HTTPS bảo vệ kênh ứng dụng**, nhưng không lớp nào tự xác thực mọi trang portal hoặc loại trừ mọi Evil twin.
- **WIDS/WIPS hiệu quả cần baseline AP hợp lệ, nhiều nguồn telemetry và triage**, tránh false positive hoặc can thiệp vô tuyến không được phép.
- **Phân đoạn Wi-Fi, firewall, DNS, NAC, IAM và bảo vệ ứng dụng** vẫn cần thiết sau khi thiết bị kết nối.
- **Ứng phó dựa trên bằng chứng, bảo vệ người dùng và kiểm thử an toàn**, không lấy số lượng SSID trùng hoặc cảnh báo đơn lẻ làm kết luận tấn công.

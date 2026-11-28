# Tampering trên đường truyền: mô hình hóa nguy cơ và thiết kế phòng vệ

## 1. Tampering trên đường truyền là gì?

Trong **threat modeling mạng**, **tampering** là hành vi sửa đổi dữ liệu hoặc trạng thái ngoài ý muốn của bên có thẩm quyền. **Tampering trên đường truyền (in-transit tampering)** tập trung vào việc kẻ tấn công làm thay đổi nội dung, thứ tự, đích đến hoặc ngữ nghĩa của thông điệp khi nó di chuyển giữa các thành phần của hệ thống. Đối tượng cần bảo vệ có thể là một gói tin, bản ghi giao thức, yêu cầu API, thông điệp giữa hai dịch vụ hoặc dữ liệu điều khiển mạng.

Trong mô hình **STRIDE**, chữ **T – Tampering** nhấn mạnh thuộc tính **integrity (tính toàn vẹn)**. Đích của phòng vệ là để người nhận **phát hiện hoặc ngăn chặn sự thay đổi trái phép**, và trong nhiều trường hợp phải xác minh **ai là bên gửi hợp lệ**. Đường truyền còn phải bảo vệ tính mới của thông điệp (freshness) nếu việc phát lại một thông điệp cũ gây ra tác dụng không mong muốn.

Ví dụ đơn giản:

> Dịch vụ A gửi thông điệp “chuyển 100.000 VND tới tài khoản X”. Nếu một thành phần trung gian thay số tiền thành 1.000.000 VND hoặc thay tài khoản nhận trước khi dịch vụ B xử lý, đây là nguy cơ tampering. Nếu B không kiểm chứng tính toàn vẹn và quyền thực hiện nghiệp vụ, hậu quả có thể là sai lệch giao dịch.

Không phải mọi sự cố trong mạng đều là tampering:

| Hiện tượng | Phân loại / quan hệ với tampering |
| --- | --- |
| Nghe lén lưu lượng nhưng không sửa nội dung | Chủ yếu là **Information Disclosure** (lộ thông tin) trong STRIDE |
| Giả danh máy chủ hoặc giả địa chỉ MAC | Chủ yếu là **Spoofing**; có thể tạo điều kiện để sửa dữ liệu |
| Sửa giá trị trường JSON, header HTTP hoặc bản ghi DNS | **Tampering** nếu sự thay đổi vượt ngoài hành vi được cho phép |
| Chặn hoặc làm rớt mọi gói tin | Chủ yếu là **Denial of Service**; có thể đi kèm hành vi chặn/sửa có chọn lọc |
| Gửi lại một yêu cầu đã hợp lệ để tạo giao dịch lần hai | **Replay**: vi phạm tính mới và ngữ nghĩa nghiệp vụ; cần phòng vệ bổ sung ngoài tính toàn vẹn của từng thông điệp |
| Proxy hợp lệ chuẩn hóa header theo thiết kế | Có thể là biến đổi **được phép**; threat modeling phải xác định ai được sửa trường nào |

Trong module **SECURITY_NETWORK_SECURITY**, chủ đề này kết nối kiến thức về phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, Wi-Fi và bảo mật đám mây. Một kiến trúc an toàn cần biết **nơi nào có thể sửa thông điệp, bên nào được phép sửa, cách phát hiện sửa đổi trái phép và phạm vi mà mỗi cơ chế bảo vệ thực sự bao phủ**.

## 2. Tampering xảy ra ở đâu trên hành trình dữ liệu?

Xét luồng điển hình:

~~~mermaid
flowchart LR
    C["Thiết bị người dùng"] -->|"HTTPS qua Internet"| E["Load balancer / API gateway"]
    E -->|"Kết nối nội bộ"| A["Dịch vụ ứng dụng"]
    A -->|"Kết nối dịch vụ"| B["Dịch vụ xử lý giao dịch"]
    B -->|"Kết nối tới dữ liệu"| D[("Cơ sở dữ liệu")]
~~~

Mỗi đoạn kết nối (*hop*) có thể có phương thức bảo vệ khác nhau:

1. **Từ thiết bị đến mạng truy cập:** Wi-Fi giả mạo, switch không được quản lý, kẻ nghe lén cùng mạng hoặc cấu hình cổng sai có thể tạo cơ hội can thiệp. WPA2/WPA3, 802.1X hoặc MACsec bảo vệ những phạm vi khác nhau.
2. **Mạng nội bộ, ISP và Internet:** Định tuyến sai, DNS bị can thiệp, thiết bị trung gian hoặc đường truyền plaintext có thể ảnh hưởng tới tính toàn vẹn của dữ liệu.
3. **Điểm kết thúc TLS:** Load balancer hoặc API gateway có thể giải mã HTTPS hợp lệ để áp dụng chính sách. Kết nối **sau điểm kết thúc TLS** cần được đánh giá riêng; TLS từ trình duyệt tới gateway không tự bảo vệ đoạn gateway → backend.
4. **Các dịch vụ nội bộ:** Service mesh, proxy, hàng đợi và các dịch vụ bên thứ ba có thể chuyển đổi thông điệp. Cần xác định ranh giới tin cậy, quyền sửa dữ liệu và cách kiểm tra lại tính toàn vẹn.
5. **Tầng ứng dụng:** Dữ liệu vẫn có thể bị sửa bởi người dùng không có quyền, dịch vụ bị chiếm quyền hoặc logic nghiệp vụ thiếu kiểm tra, ngay cả khi mọi hop đều dùng TLS.

**Phân biệt quan trọng:** Kẻ tấn công kiểm soát tuyến đường hoặc nghe được gói tin chưa chắc đã sửa được thông điệp mà không bị phát hiện. Nếu client thực sự xác minh chứng chỉ và máy chủ dùng TLS được cấu hình đúng, cơ chế xác thực và kiểm tra toàn vẹn của TLS sẽ ngăn việc sửa bản ghi TLS một cách âm thầm bởi kẻ đứng giữa. Ngược lại, một endpoint hợp lệ nhưng bị xâm nhập vẫn có thể tự tạo hoặc sửa thông điệp trước khi mã hóa.

### Ranh giới tin cậy (trust boundary)

**Trust boundary** là vị trí mà giả định về danh tính, quyền hạn hoặc cơ chế bảo vệ thay đổi, ví dụ:

- Thiết bị không được quản lý → mạng doanh nghiệp.
- Internet → vùng DMZ/API gateway.
- API gateway → mạng dịch vụ nội bộ.
- Dịch vụ đơn hàng → dịch vụ thanh toán.
- Mạng công ty → nhà cung cấp dịch vụ đám mây.

Đừng giả định “đã ở trong mạng nội bộ thì dữ liệu đáng tin”. Hãy xét **danh tính của từng bên**, quyền tạo/sửa thông điệp và khả năng kiểm chứng ở điểm nhận.

## 3. Các đường tấn công liên quan đến sửa đổi dữ liệu khi truyền

| Bề mặt | Cách nguy cơ hình thành | Dấu hiệu / tác động | Giới hạn cần hiểu |
| --- | --- | --- | --- |
| **ARP spoofing / ARP poisoning** trên IPv4 LAN | Kẻ tấn công làm sai ánh xạ IP–MAC để chuyển lưu lượng qua thiết bị của mình | Lưu lượng đi sai MAC/port; nguy cơ nghe lén hoặc can thiệp dữ liệu không được bảo vệ | Thao túng ARP **không tự phá được TLS** đã xác minh đúng |
| **DHCP giả mạo** | Cấp gateway/DNS độc hại cho thiết bị | Máy gửi lưu lượng qua điểm trung gian ngoài ý muốn | Cần đánh giá mức độ tin cậy của cấu hình mạng và cơ chế xác thực tầng cao |
| **DNS poisoning / giả mạo DNS** | Trả bản ghi DNS sai làm người dùng đến địa chỉ không mong muốn | Kết nối tới IP lạ, máy chủ giả, thất bại xác minh TLS | DNS bị đổi **không có nghĩa** client TLS sẽ chấp nhận máy chủ giả |
| **Plaintext HTTP hoặc giao thức không xác thực toàn vẹn** | Thiết bị giữa đường thay đổi body, URL, header, mã lệnh hoặc phản hồi | Nội dung trả về sai, chuyển hướng bất thường, dữ liệu nghiệp vụ bị sửa | Mã hóa đường truyền cùng xác minh danh tính là kiểm soát quan trọng |
| **TLS cấu hình sai** | Client bỏ qua kiểm tra certificate/hostname, cho phép fallback xuống HTTP hoặc tin CA không phù hợp | Endpoint giả có thể được chấp nhận và giải mã/sửa dữ liệu | Chỉ “thấy biểu tượng HTTPS” là chưa đủ để kết luận toàn bộ luồng an toàn |
| **Proxy/gateway hoặc sidecar bị chiếm quyền** | Thành phần có quyền giải mã và chuyển tiếp sửa request/response | Chênh lệch giữa bản gốc và dữ liệu backend nhận, giao dịch sai | TLS hop-to-hop không tự bảo vệ dữ liệu khỏi chính endpoint trung gian hợp lệ |
| **Chuyển hướng định tuyến / BGP hijack** | Dữ liệu bị đưa qua tuyến đường hoặc mạng ngoài ý muốn | Route bất thường, tăng độ trễ, lưu lượng bị chuyển hướng | RPKI giúp xác thực nguồn gốc route trong phạm vi hỗ trợ; không bảo đảm mọi đường đi và không thay TLS |
| **Replay / thay đổi thứ tự thông điệp** | Bản tin hợp lệ cũ được gửi lại hoặc hai thao tác hợp lệ bị thực hiện sai trình tự | Trừ tiền hai lần, trạng thái cập nhật không đúng | MAC/chữ ký chỉ xác nhận nội dung và khóa; cần nonce, thời hạn, số thứ tự, idempotency phù hợp |

Các kỹ thuật có thể kết hợp. Ví dụ, DNS bị can thiệp có thể dẫn client đến máy chủ giả; nếu client tiếp tục kiểm tra đúng tên miền và chuỗi chứng chỉ TLS, việc kết nối tới máy chủ giả thường bị chặn. Đánh giá phải theo **chuỗi điều kiện tấn công**, tránh suy đoán rằng kiểm soát được một tầng đồng nghĩa kiểm soát mọi tầng.

### “Sửa frame” và “sửa dữ liệu ứng dụng” không giống nhau

Ở Ethernet, **FCS/CRC** phát hiện phần lớn lỗi bit ngẫu nhiên trong frame nhưng **không phải mã xác thực mật mã**. Một bên tự tạo frame mới có thể tính ra FCS hợp lệ. Ở TCP, checksum giúp phát hiện lỗi truyền dẫn; nó cũng không xác thực danh tính hay ngăn can thiệp chủ ý.

Ngược lại, **TLS**, **IPsec ESP**, **MACsec** và các giao thức mã hóa có xác thực sử dụng bí mật mật mã để phát hiện sửa đổi trái phép trong **phạm vi được thiết lập**. Dù vậy, cơ chế bảo vệ tính toàn vẹn của bản ghi trên một kết nối không tự kiểm chứng rằng số tiền, vai trò người dùng hoặc trạng thái nghiệp vụ là hợp lệ.

## 4. Quy trình threat modeling cho tampering trên đường truyền

Một phiên phân tích nên trả lời năm câu hỏi: **đang bảo vệ dữ liệu gì; dữ liệu đi qua đâu; ai có khả năng thay đổi; có thể gây hậu quả gì; điểm nhận xác minh điều gì?**

### Bước 1. Xác định tài sản và tính đúng đắn

Không chỉ liệt kê “API” hoặc “database”. Hãy nêu **giá trị cần giữ nguyên**, ví dụ:

- Số tiền, đơn vị tiền tệ, tài khoản nhận và mã giao dịch.
- Danh tính người dùng, tenant ID, vai trò và phạm vi được phép.
- Kết quả phân giải DNS cho tên miền dịch vụ.
- Phản hồi cấu hình từ control plane hoặc thông điệp điều khiển mạng.
- Sự kiện audit, cảnh báo IDS/IPS và kết quả kiểm tra chính sách.

Với mỗi tài sản, định nghĩa **bên có quyền tạo**, **bên có quyền sửa**, **điểm kiểm chứng** và **hậu quả nếu bị sửa**. Chẳng hạn dịch vụ thanh toán chỉ chấp nhận số tiền do dịch vụ đơn hàng có quyền sinh ra sau khi kiểm tra bảng giá; trình duyệt không phải nguồn tin cậy cho giá cuối cùng.

### Bước 2. Vẽ Data Flow Diagram (DFD)

DFD phải thể hiện thực thể bên ngoài, tiến trình, kho dữ liệu, luồng thông điệp và **trust boundary**. Ghi rõ những chặng được bảo vệ bằng HTTPS, mTLS, VPN, MACsec hay vẫn là plaintext. Đánh dấu chính xác nơi TLS kết thúc.

### Bước 3. Xác định khả năng của tác nhân đe dọa

Không gộp mọi kẻ tấn công thành một nhóm có quyền tối đa. Phân biệt:

| Tác nhân giả định | Khả năng cần kiểm tra | Ví dụ giả định an ninh |
| --- | --- | --- |
| Người cùng mạng truy cập | Quan sát, gây nhiễu hoặc tìm cách chuyển hướng lưu lượng cục bộ | Có quản lý switch, DHCP snooping, bảo vệ Wi-Fi hay không? |
| Thiết bị trung gian không tin cậy | Có thể chặn, thay thế hoặc phát lại lưu lượng không được xác thực | Dữ liệu có được xác thực toàn vẹn giữa các endpoint thực sự không? |
| Người dùng API không đủ quyền | Tự tạo request hợp lệ về mặt giao thức nhưng chứa giá trị trái phép | Server có tự kiểm tra quyền và tính nhất quán nghiệp vụ không? |
| Dịch vụ/proxy nội bộ bị xâm nhập | Có thể đọc/sửa plaintext tại nơi kết thúc TLS | Thông điệp có ràng buộc với nguồn đáng tin, phạm vi quyền và điểm nhận không? |
| Bên quản trị hoặc nhà cung cấp bị cấp quyền quá rộng | Có thể đổi cấu hình định tuyến, proxy, DNS hoặc chính sách bảo mật | Có tách quyền, phê duyệt thay đổi và nhật ký kiểm toán không? |

### Bước 4. Viết threat scenario có điều kiện

Mẫu sử dụng trong review:

~~~text
Mã: T-<số>
Tài sản: <trường/thông điệp cần bảo vệ>
Luồng: <nguồn -> trung gian -> đích>
Ranh giới: <điểm thay đổi mức tin cậy>
Khả năng tác nhân: <quan sát / chuyển hướng / sửa / phát lại>
Điều kiện: <plaintext, TLS xác minh sai, proxy bị chiếm quyền, ...>
Hành vi ngoài quyền: <trường nào có thể bị sửa>
Tác động: <thiệt hại về tính toàn vẹn / nghiệp vụ>
Kiểm soát hiện tại: <cơ chế đã xác minh>
Biện pháp đề xuất: <cơ chế ngăn chặn / phát hiện>
Bằng chứng kiểm thử: <test, cấu hình, log, trace>
~~~

Viết rõ điều kiện là yếu tố quan trọng: “kẻ đứng giữa sửa được HTTPS” là nhận định thiếu cơ sở nếu chưa chỉ ra client bỏ kiểm tra chứng chỉ, endpoint bị chiếm quyền, hoặc điểm TLS kết thúc ở nơi không được tin cậy.

### Bước 5. Xếp hạng rủi ro và chọn kiểm soát

Một cách thực hành là chấm **likelihood (khả năng xảy ra)** và **impact (mức độ ảnh hưởng)** trên thang 1–3; nhân hai điểm để ưu tiên **trong phạm vi bài tập**:

| Điểm | Likelihood | Impact |
| --- | --- | --- |
| 1 | Cần nhiều điều kiện khó xảy ra | Tác động cục bộ, phục hồi dễ |
| 2 | Có điều kiện khai thác đáng kể, khả thi trong môi trường | Ảnh hưởng một nhóm dịch vụ/người dùng |
| 3 | Có đường tấn công thực tế hoặc kiểm soát rất yếu | Thiệt hại tài chính, dữ liệu quan trọng hoặc gián đoạn lớn |

Thang **1–9** này chỉ dùng để **so sánh tương đối**, không phải xác suất thực hoặc chuẩn rủi ro thống nhất. Ưu tiên cao trước các luồng tài chính, kiểm soát truy cập và điều khiển hạ tầng; sau khi bổ sung kiểm soát, đánh giá lại **rủi ro còn lại**.

## 5. Case study: sửa nội dung giao dịch sau khi HTTPS kết thúc

Giả sử hệ thống bán hàng gồm:

~~~mermaid
flowchart LR
    U["Ứng dụng người dùng"] -->|"HTTPS"| G["API Gateway"]
    G -->|"mTLS"| O["Order Service"]
    O -->|"mTLS + kiểm tra tính toàn vẹn thông điệp"| P["Payment Service"]
    O -->|"Truy vấn dữ liệu"| DB[("Bảng giá / đơn hàng")]
~~~

**Giả định hệ thống ban đầu:** HTTPS từ trình duyệt kết thúc ở gateway, kết nối từ gateway đến Order Service chưa mã hóa; Order Service chuyển giá trị thanh toán qua kết nối nội bộ không xác thực; Payment Service tin toàn bộ nội dung nhận được. Có nhiều điểm cho phép sửa sai mà chỉ có TLS bên ngoài sẽ không đủ ngăn chặn.

### Các tài sản và ranh giới

| Tài sản / thông điệp | Chủ thể được quyền quyết định | Ranh giới cần bảo vệ |
| --- | --- | --- |
| Danh sách sản phẩm và số lượng khách chọn | Người dùng được xác thực, trong phạm vi tài khoản | Trình duyệt → gateway → Order Service |
| Đơn giá, giảm giá đủ điều kiện, tổng tiền | Logic và dữ liệu đáng tin của Order Service | Order Service ↔ nguồn bảng giá |
| Lệnh tạo thanh toán với amount, currency, order_id, payee | Order Service sau khi kiểm tra nghiệp vụ | Order Service → Payment Service |
| Kết quả thanh toán, transaction ID, trạng thái | Payment Service hoặc nhà cung cấp thanh toán được xác minh | Payment Service → Order Service |

**Đường tấn công T-01: kết nối nội bộ không được bảo vệ.** Một tác nhân có quyền can thiệp vào mạng giữa gateway và Order Service có thể tìm cách thay body của request plaintext. Nếu backend tin dữ liệu đầu vào, thuộc tính nghiệp vụ có thể bị sai. **Biện pháp:** mTLS cho gateway ↔ service, xác thực và phân quyền từng service, giới hạn mạng và server tự kiểm tra tất cả trường nhạy cảm.

**Đường tấn công T-02: thay amount trên chặng tới Payment Service.** Nếu thông điệp không có bảo vệ tính toàn vẹn, tác nhân có quyền can thiệp trên đường truyền có thể đổi amount hoặc payee. **Biện pháp:** mTLS trực tiếp giữa hai dịch vụ; kiểm tra danh tính peer; nếu qua bên trung gian có thể giải mã/biến đổi, dùng chữ ký hoặc MAC thông điệp giữa hai bên tin cậy với khóa không cấp cho trung gian.

**Đường tấn công T-03: người dùng tự sửa amount từ client.** TLS bảo vệ chính thông điệp người dùng gửi, nhưng không khiến **giá do client đề xuất** trở nên đáng tin. **Biện pháp:** Order Service tính lại đơn giá và tổng tiền từ nguồn dữ liệu server, kiểm tra quyền của người dùng và đối chiếu payment amount với order ID đã lưu.

**Đường tấn công T-04: yêu cầu thanh toán hợp lệ bị gửi lặp lại.** Ngay cả khi yêu cầu dùng mTLS/HMAC, việc hai request hợp lệ có cùng nội dung có thể dẫn đến xử lý hai lần nếu ứng dụng không kiểm soát nghiệp vụ. **Biện pháp:** idempotency key gắn chặt với giao dịch và phạm vi người gọi, trạng thái giao dịch bền vững, xử lý nguyên tử và phát hiện yêu cầu trùng.

### Bảng đánh giá mẫu

| Mã | Điều kiện chính | Tác động | Rủi ro trước kiểm soát (minh họa) | Kiểm soát ưu tiên |
| --- | --- | --- | ---: | --- |
| T-01 | Gateway → Order Service dùng plaintext trên mạng có tác nhân can thiệp | Đơn hàng bị sửa | 2 × 3 = **6** | mTLS, mạng riêng và xác minh dữ liệu |
| T-02 | Order → Payment không bảo đảm tính toàn vẹn | Sai amount/payee | 2 × 3 = **6** | mTLS; MAC/chữ ký thông điệp khi phù hợp |
| T-03 | Server tin trường amount do client quyết định | Gian lận giá | 3 × 3 = **9** | Tính giá server-side, kiểm soát quyền và trạng thái |
| T-04 | Thiếu kiểm soát request trùng | Thanh toán lặp | 2 × 3 = **6** | Idempotency, chống replay và transaction state |

Các điểm trên là **giả định phục vụ học tập**, không đại diện cho bất kỳ sản phẩm đang vận hành nào. Trong môi trường thực tế cần thu thập cấu hình, diagram, khả năng tấn công và dữ liệu tác động để chấm điểm.

## 6. Lựa chọn cơ chế bảo vệ đúng phạm vi

**Integrity, authenticity, confidentiality và freshness là các tính chất khác nhau**. Một giải pháp có thể bảo vệ một số tính chất nhưng không tự động cung cấp tất cả.

| Cơ chế | Bảo vệ trong phạm vi nào? | Điểm cần chú ý đối với tampering |
| --- | --- | --- |
| Ethernet FCS, TCP/UDP checksum | Phát hiện lỗi dữ liệu do truyền dẫn | Không có khóa bí mật; **không** bảo vệ trước sửa đổi có chủ ý |
| WPA2/WPA3 cho Wi-Fi | Bảo vệ liên kết vô tuyến theo chế độ và cấu hình được chọn | Phạm vi thường kết thúc tại hạ tầng Wi-Fi; vẫn cần cơ chế tầng cao |
| IEEE 802.1X/EAP | Kiểm soát xác thực truy cập mạng | Không đồng nghĩa mọi dữ liệu sau khi truy cập đều được mã hóa và xác thực toàn vẹn |
| MACsec (IEEE 802.1AE) | Tính toàn vẹn, xác thực nguồn trên liên kết Ethernet được thiết lập; có thể mã hóa | Phạm vi **hop-by-hop / liên kết**; phải quản lý khóa và thiết bị tương thích |
| IPsec ESP | Bảo vệ gói IP giữa các endpoint/tunnel được cấu hình với xác thực toàn vẹn | Kiểm tra đúng tunnel, peer, thuật toán, phạm vi traffic selector và đường đi khác |
| WireGuard | VPN sử dụng mật mã hiện đại, xác thực peer và bảo vệ dữ liệu trong tunnel | Tin cậy phụ thuộc quản lý khóa, peer được phép và phạm vi định tuyến tunnel |
| TLS 1.2/1.3, ưu tiên TLS 1.3 | Bảo vệ kết nối giữa các TLS endpoint với cơ chế xác thực, mật mã và kiểm tra toàn vẹn | Phải xác minh chứng chỉ và hostname; **TLS kết thúc ở đâu thì phạm vi đó dừng ở đó** |
| mTLS | Hai bên cùng trình chứng chỉ và xác thực trong quá trình TLS handshake | Cần quản lý danh tính, PKI và quyền; mTLS không thay kiểm tra nghiệp vụ |
| HMAC (ví dụ HMAC-SHA-256) | Phát hiện thay đổi thông điệp giữa các bên **cùng biết khóa bí mật** | Không mã hóa; mọi bên có khóa đều có khả năng tạo MAC; không chống replay nếu thiếu ngữ cảnh |
| Chữ ký số | Kiểm tra tính toàn vẹn và nguồn ký dựa trên khóa công khai/riêng | Phải kiểm tra danh tính khóa, phạm vi dữ liệu được ký, thời hạn và chống replay |
| DNSSEC | Xác thực nguồn gốc và tính toàn vẹn của **dữ liệu DNS có chữ ký** khi validator kiểm tra chuỗi tin cậy | Không mã hóa truy vấn DNS và không xác thực bản thân website |
| DoT/DoH | Mã hóa và xác thực kết nối DNS giữa client với resolver theo cấu hình | Không thay việc DNSSEC xác minh chữ ký dữ liệu có nguồn gốc từ vùng DNS |
| IDS/IPS | Phát hiện/ngăn lưu lượng hoặc hành vi đáng ngờ theo khả năng quan sát | Không tự cung cấp integrity; TLS có thể hạn chế việc quan sát payload trên đường truyền |

### 6.1. TLS phải xác minh đúng đầu cuối

Khi xây dựng ứng dụng hoặc cấu hình HTTP client:

1. **Bật kiểm tra chứng chỉ** do CA phù hợp cấp; kiểm tra tên máy chủ (hostname) mà ứng dụng thực sự định kết nối.
2. Dùng TLS hiện đại, ưu tiên **TLS 1.3** và giữ TLS 1.2 nếu thực sự cần tương thích theo chính sách; không cho fallback sang HTTP đối với dữ liệu cần bảo vệ.
3. Quản lý chứng chỉ, khóa riêng, chu kỳ gia hạn và CA tin cậy; cảnh báo khi chứng chỉ sắp hết hạn hoặc lỗi chain.
4. Đánh dấu rõ endpoint kết thúc TLS và bảo vệ cả chặng backend. Nếu một dịch vụ nội bộ có quyền kết thúc TLS, hãy đưa dịch vụ đó vào threat model như một bên có thể thấy plaintext.
5. Xác thực **quyền** của tài khoản/service sau khi xác thực **danh tính**. Không suy từ “TLS thành công” ra “mọi thao tác đều được cho phép”.

Tránh những đường tắt như tắt kiểm tra chứng chỉ, chấp nhận mọi hostname hoặc bỏ qua lỗi xác thực để khắc phục kết nối. Với mTLS, cần xác định danh tính service trong certificate/SAN và ánh xạ nó vào chính sách phân quyền; không chấp nhận mọi chứng chỉ của cùng một CA như bằng chứng đủ để truy cập mọi API.

### 6.2. Khi nào cần HMAC hoặc chữ ký cho chính thông điệp?

TLS bảo vệ **đường kết nối** giữa hai endpoint TLS. Nếu thông điệp đi qua nhiều hệ thống có quyền giải mã, được lưu vào queue, được xử lý bất đồng bộ hoặc cần xác minh lại ở điểm nhận cuối, có thể cần **message-level integrity**.

Thiết kế tối thiểu phải trả lời:

- **Chính xác byte/trường nào được xác thực?** Thông thường gồm payload và metadata quan trọng như method, path, order ID, amount, currency, tenant ID hoặc recipient.
- **Ai giữ khóa?** Không cấp khóa tạo MAC/chữ ký cho proxy không được phép tạo nội dung thay mặt người gửi.
- **Có thể phát lại không?** Gắn request ID/nonce, thời gian hết hiệu lực và cơ chế phát hiện sử dụng lại; idempotency là yêu cầu riêng của nghiệp vụ.
- **Thứ tự/canonicalization có ổn định không?** Hai bên phải ký/kiểm tra cùng một chuỗi byte; với JSON cần thống nhất cách mã hóa hoặc ký **raw body bytes** đã được định nghĩa rõ.
- **Có kiểm tra quyền và trạng thái không?** Một thông điệp có MAC đúng vẫn có thể vi phạm quy tắc nghiệp vụ nếu người gửi có quyền tạo MAC nhưng không có quyền làm thao tác đó.

**HMAC dùng khóa đối xứng**: nếu cả hai bên cùng giữ khóa, HMAC không chứng minh được bên nào trong số các bên giữ khóa đã tạo thông điệp. Khi cần phân biệt người ký, thiết kế chữ ký số với khóa riêng tách biệt và cơ chế phân phối khóa công khai phù hợp.

### 6.3. Chống replay và kiểm tra ngữ nghĩa

Một thông điệp đã được ký hợp lệ vẫn có thể bị gửi lại ở **ngữ cảnh sai**. Vì thế, ngoài MAC hoặc chữ ký:

- Áp dụng **thời hạn hiệu lực** và kiểm tra đồng hồ theo dung sai đã xác định; không coi timestamp đơn lẻ là biện pháp chống replay đầy đủ.
- Sử dụng **nonce/request ID** không lặp và ghi nhận đã sử dụng ở kho trạng thái có khả năng chia sẻ giữa các instance, với thời gian sống thích hợp.
- Ràng buộc xác thực với **đích đến, phương thức, đường dẫn, phiên, tenant và hành động** để tránh dùng lại một chữ ký cho thao tác khác.
- Với lệnh thanh toán/ghi dữ liệu, dùng **idempotency** và kiểm tra trạng thái giao dịch bền vững để không thực hiện hai lần.

Nếu các dịch vụ xử lý hàng đợi và có thể nhận lại thông điệp hợp lệ do cơ chế retry, không mặc định mọi bản sao là tấn công. Phân biệt retry đúng thiết kế, duplicate delivery và replay độc hại bằng trạng thái nghiệp vụ.

## 7. Thực hành an toàn: mô phỏng phát hiện sửa đổi bằng HMAC

Bài lab sau chỉ chạy trên dữ liệu mẫu tại máy cục bộ. Nó **không** tạo lưu lượng tấn công, không giả mạo lưu lượng mạng và không gửi dữ liệu đến dịch vụ bên ngoài.

~~~python
import hashlib
import hmac
import json

# Khóa CHỈ dùng để học; trong hệ thống thật lấy từ kho bí mật được quản lý.
lab_key = b"training-key-do-not-use-in-production"


def canonical_bytes(message: dict) -> bytes:
    # Thống nhất cách chuyển JSON thành byte cho hai phía của bài lab.
    return json.dumps(
        message,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def calculate_mac(message: dict) -> str:
    return hmac.new(
        lab_key,
        canonical_bytes(message),
        hashlib.sha256,
    ).hexdigest()


def verify_mac(message: dict, received_mac: str) -> bool:
    expected_mac = calculate_mac(message)
    return hmac.compare_digest(expected_mac, received_mac)


original = {
    "order_id": "ORDER-100",
    "amount_vnd": 250000,
    "currency": "VND",
    "recipient": "merchant-A",
}

sent_mac = calculate_mac(original)
print("Nguyên vẹn:", verify_mac(original, sent_mac))

changed = dict(original)
changed["amount_vnd"] = 2500000
print("Bị sửa amount:", verify_mac(changed, sent_mac))

changed_recipient = dict(original)
changed_recipient["recipient"] = "merchant-B"
print("Bị sửa recipient:", verify_mac(changed_recipient, sent_mac))
~~~

Kết quả dự kiến:

~~~text
Nguyên vẹn: True
Bị sửa amount: False
Bị sửa recipient: False
~~~

Giải thích: HMAC của dữ liệu đã sửa không bằng HMAC do bên tạo thông điệp ban đầu tính với cùng khóa. Hàm **hmac.compare_digest** dùng để so sánh giá trị xác thực và tránh một lớp rò rỉ thời gian so sánh thông thường.

**Giới hạn của ví dụ:**

- HMAC **không mã hóa** nội dung; người quan sát vẫn có thể đọc request nếu không có TLS/VPN tương ứng.
- Một bên biết **lab_key** có thể tạo MAC mới cho dữ liệu tùy ý; do đó việc cấp và bảo vệ khóa quyết định mức an toàn.
- Bản demo **chưa có** timestamp, nonce, request ID, kiểm soát replay hay xác thực quyền nghiệp vụ.
- Canonical JSON trong ví dụ chỉ phù hợp khi **hai phía hoàn toàn thống nhất** cách tạo chuỗi byte. Trong hệ thống thật phải định nghĩa chuẩn hóa chắc chắn, xử lý duplicate JSON keys, kiểu dữ liệu và thay đổi encoding; nhiều giao thức ưu tiên xác thực đúng chuỗi raw bytes đã phát đi.
- Cần xác thực danh tính người gọi và kiểm tra tại server rằng amount/recipient/order_id được phép, kể cả khi MAC hợp lệ.

### Bài tập mở rộng

Hãy mô tả (không cần phát lưu lượng thật) cách bổ sung hai trường **request_id** và **expires_at** vào dữ liệu được ký. Khi verify, ngoài kiểm tra HMAC còn phải bác bỏ thông điệp hết hạn và request_id đã xử lý; với nhiều instance phải lưu trạng thái chống trùng trong kho nhất quán phù hợp. Sau đó giải thích vì sao idempotency vẫn quan trọng nếu cùng một yêu cầu hợp lệ được hệ thống retry.

## 8. Kiểm soát theo từng lớp mạng

Phòng vệ theo chiều sâu giúp hạn chế khả năng chiếm vị trí trung gian, đồng thời phát hiện sửa đổi nếu một lớp phòng thủ bị vượt qua.

### 8.1. Mạng LAN và Wi-Fi

- Dùng kiểm soát truy cập cổng phù hợp như **802.1X**, quản lý thiết bị và chứng chỉ người dùng/thiết bị khi có hạ tầng.
- Trên switch hỗ trợ, dùng **DHCP Snooping** kết hợp **Dynamic ARP Inspection** (DAI) để giảm rủi ro ARP poisoning. Cần cấu hình đúng cổng trusted/untrusted và các thiết bị IP tĩnh.
- Cấu hình VLAN, trunk, port security, ACL và phân đoạn để hạn chế miền ảnh hưởng; VLAN **không phải** cơ chế mã hóa.
- Với các liên kết Ethernet cần bảo vệ ở tầng 2 và thiết bị tương thích, đánh giá **MACsec**; không suy rằng MACsec của một hop tự bảo vệ mọi hop sau.
- Với Wi-Fi, dùng phương thức xác thực và mã hóa phù hợp như WPA3-Enterprise ở môi trường doanh nghiệp, kiểm soát điểm truy cập giả và giữ đường truyền ứng dụng có TLS.

### 8.2. Internet, DNS và VPN

- Dùng **TLS** có kiểm tra danh tính đầu cuối cho ứng dụng; mTLS giữa các dịch vụ khi cần xác thực lẫn nhau.
- Dùng **IPsec ESP/WireGuard** khi cần đường hầm VPN giữa các site/thiết bị, nhưng vẫn xem các endpoint tunnel là ranh giới tin cậy.
- Với DNS, đánh giá **DNSSEC validation** cho tính xác thực của dữ liệu đã ký; **DoT/DoH** bảo vệ kênh client → resolver theo cấu hình. HTTPS vẫn phải kiểm tra chứng chỉ máy chủ đích.
- Quản lý cấu hình routing, BGP và giám sát thay đổi đường đi; cân nhắc **RPKI route origin validation** trong môi trường có BGP, đồng thời hiểu phạm vi và giới hạn của nó.

### 8.3. Cloud, service mesh và proxy

- Liệt kê điểm TLS termination ở load balancer, ingress controller, API gateway, sidecar và egress proxy; xác minh bảo vệ từng chặng.
- Giới hạn danh tính và quyền của service account, workload identity, private key và quyền thay đổi cấu hình proxy/routing.
- Áp dụng network policy/security group/firewall rules để chỉ cho phép những luồng bắt buộc; **phân đoạn giảm khả năng tiếp cận**, không thay xác thực dữ liệu.
- Đối với thao tác nhạy cảm, kiểm tra authorization và tính toàn vẹn ở **điểm tiêu thụ cuối**; nếu cần tránh sửa đổi bởi trung gian hợp lệ, dùng message-level MAC/chữ ký với khóa không cấp cho trung gian.
- Bật audit cho thay đổi chính sách, certificate, cấu hình ingress/service mesh, quyền truy cập secrets và triển khai workload.

## 9. Giám sát và điều tra khi nghi ngờ tampering

IDS/IPS, nhật ký DNS, flow logs, proxy logs, telemetry từ switch/router và application logs cung cấp bằng chứng ở các lớp khác nhau. Cần đối chiếu theo cùng **request ID, timestamp, source/destination, service identity và trust boundary**.

| Tín hiệu | Nơi quan sát | Diễn giải thận trọng |
| --- | --- | --- |
| MAC flapping, ARP mapping đổi bất thường | Switch, ARP table, NDR | Có thể do loop, roaming, thay đổi topo hoặc hành vi giả mạo; cần điều tra ngữ cảnh |
| DNS answer thay đổi ngoài dự kiến | Resolver logs, DNS monitor | Có thể là CDN/load balancing hợp lệ hoặc cấu hình sai; kiểm tra nguồn và DNSSEC khi phù hợp |
| Lỗi xác minh TLS, hostname mismatch, certificate chain fail | Client, reverse proxy, service mesh | Có thể do certificate hết hạn/cấu hình sai; cũng có thể gợi ý endpoint bị thay thế |
| HTTP/JSON digest hoặc HMAC verify fail | API/server ứng dụng | Nội dung/metadata không khớp khóa hoặc định dạng; cũng có thể do lỗi canonicalization |
| Cùng transaction/request ID được xử lý nhiều lần | Giao dịch, payment audit, queue consumers | Kiểm tra retry hợp lệ, idempotency và replay |
| Route hoặc TLS termination thay đổi bất thường | Router, BGP monitor, cloud audit | Xác minh thay đổi được phê duyệt và phạm vi luồng ảnh hưởng |
| Dữ liệu ở upstream và downstream không nhất quán | Distributed tracing, audit log theo sự kiện | Có thể do proxy transform hợp lệ, ứng dụng lỗi hoặc sửa đổi trái phép |

### Luồng điều tra thực tế

1. **Xác định sự thật bị sai:** Ví dụ amount mà Payment Service nhận khác amount được Order Service phê duyệt; ghi rõ transaction ID, thời điểm và trường dữ liệu.
2. **Lập lại đường đi của thông điệp:** Dựa trên trace và cấu hình để tìm các hop, proxy, queue và điểm TLS termination liên quan.
3. **Tìm bước biến đổi đầu tiên:** So sánh sự kiện có kiểm soát ở nguồn và điểm nhận (không đưa secrets, số thẻ hay dữ liệu cá nhân vào log). Xác định biến đổi hợp lệ hay trái phép.
4. **Kiểm tra bằng chứng xác thực:** Chứng chỉ peer, kết quả mTLS, HMAC/chữ ký, nonce/idempotency, quyền của service, nhật ký thay đổi cấu hình.
5. **Khoanh vùng và xử lý:** Thu hồi/đổi khóa nghi lộ, sửa routing hoặc cấu hình, cô lập dịch vụ bị xâm nhập, khóa API nguy hiểm khi cần và kiểm tra giao dịch đã ảnh hưởng theo quy trình ứng phó sự cố.
6. **Khắc phục lâu dài:** Bổ sung invariant nghiệp vụ, kiểm thử phòng ngừa, telemetry và alert phù hợp; đánh giá lại threat model.

**Giới hạn thu thập gói:** Trên đường truyền dùng TLS, packet capture thường chỉ thấy metadata và bản ghi mã hóa, không thấy HTTP body. Để kiểm chứng nội dung giữa các điểm, sử dụng audit/tracing có chủ đích tại endpoint được ủy quyền. Khi ghi log, cần bảo vệ thông tin riêng tư và bí mật.

## 10. Thiết kế các phép kiểm chứng có thể thực hiện

Để một threat model có giá trị, mỗi biện pháp phòng vệ cần **bằng chứng kiểm chứng**. Tập trung vào môi trường lab/staging đã được phép kiểm thử.

| Mục tiêu | Kịch bản kiểm chứng an toàn | Kết quả đạt |
| --- | --- | --- |
| Không chấp nhận máy chủ TLS giả | Cấu hình client kết nối đến endpoint thử nghiệm có chứng chỉ không khớp hostname | Kết nối thất bại với lỗi xác thực chứng chỉ rõ ràng |
| Bảo vệ mọi hop nhạy cảm | Kiểm kê cấu hình ingress/gateway/service và kiểm tra chính sách mTLS | Không còn chặng plaintext ngoài phạm vi chấp nhận được |
| Phát hiện sửa body | Thay một trường trong **bản dữ liệu thử nghiệm cục bộ** trước khi verify HMAC | HMAC thất bại, thao tác nghiệp vụ bị từ chối |
| Không tin giá do client cung cấp | Gửi request test với amount khác giá server tính | Server không dùng amount client để quyết định giao dịch |
| Chống request trùng | Gửi lại cùng request ID thử nghiệm nhiều lần theo API được cho phép | Không tạo nhiều hiệu ứng nghiệp vụ; phản hồi theo hợp đồng idempotency |
| Không dùng sai khóa giữa dịch vụ | Kiểm thử service B sử dụng danh tính/khóa không được phép gửi lệnh của service A | Request bị từ chối tại điểm nhận |
| Phát hiện cấu hình bị đổi | Thay đổi được phê duyệt trong lab trên gateway hoặc ingress | Có audit event xác định được người/phiên và thời điểm thay đổi |

Trong kiểm thử tích hợp nên đo thêm: tỷ lệ xác thực lỗi, nguyên nhân lỗi (hết hạn, sai chữ ký, sai quyền, duplicate), độ trễ của cơ chế kiểm tra, số request bị từ chối nhầm và tác động đến retry. Tránh đưa bí mật khóa vào test report hoặc log.

## 11. Những nhận định sai thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Đã dùng HTTPS nên không thể xảy ra tampering.” | HTTPS/TLS bảo vệ đến **endpoint TLS**. Dữ liệu ở endpoint, chặng sau TLS termination hoặc các thao tác trái quyền vẫn cần kiểm soát riêng. |
| “Firewall hoặc VLAN bảo đảm tính toàn vẹn.” | Chúng giúp hạn chế đường truy cập và vùng lan truyền, nhưng **không** xác thực nội dung của mọi thông điệp. |
| “CRC/checksum hợp lệ chứng minh gói tin chưa bị tấn công.” | Checksum không dùng bí mật mật mã và không chống sửa đổi có chủ ý. |
| “Có MAC/chữ ký hợp lệ nghĩa là hành động nghiệp vụ hợp lệ.” | Còn phải kiểm tra danh tính được phép, trạng thái và quy tắc nghiệp vụ. |
| “Mã hóa đã tự chống replay.” | Cần xét tính mới, thứ tự, idempotency và cơ chế chống replay ở **đúng tầng**; tính toàn vẹn của một thông điệp không tự bảo đảm yêu cầu xử lý một lần. |
| “mTLS ở service mesh chứng minh mọi dữ liệu đều do người dùng hợp lệ tạo.” | mTLS xác thực workload ở một kết nối; service vẫn phải xác thực/ủy quyền request và nguồn dữ liệu. |
| “DNSSEC làm DNS trở nên riêng tư.” | DNSSEC xác thực dữ liệu DNS được ký; tính riêng tư của truy vấn là một vấn đề khác. |
| “Chỉ cần giám sát gói tin là đọc được nội dung HTTPS.” | Không thể suy ra plaintext từ bản ghi TLS mã hóa thông thường; cần telemetry ở endpoint được phép hoặc dữ liệu phù hợp khác. |

## 12. Câu hỏi tự kiểm tra và bài tập thiết kế

1. **Tampering khác Spoofing ở điểm nào?** Tampering nhắm vào tính toàn vẹn của dữ liệu/trạng thái; Spoofing nhắm vào việc giả danh. Spoofing có thể là một điều kiện mở đường cho tampering.
2. **Vì sao một cuộc tấn công ARP poisoning không mặc nhiên sửa được nội dung HTTPS?** Vì TLS với xác minh danh tính và tính toàn vẹn đúng có thể phát hiện thao túng bản ghi/endpoint, dù lưu lượng bị chuyển hướng.
3. **HTTPS từ Internet đến gateway bảo vệ backend đến đâu?** Chỉ tới gateway nếu TLS kết thúc ở đó; cần đánh giá và bảo vệ gateway → backend bằng cơ chế riêng.
4. **HMAC đúng có đủ để duyệt lệnh chuyển tiền không?** Không. Phải xác định khóa thuộc về chủ thể được phép, dữ liệu đã ký có đúng ngữ cảnh, tính mới, hạn mức, tài khoản và trạng thái giao dịch.
5. **Trong một mạng có nhiều VLAN, vì sao vẫn cần TLS hoặc MACsec/IPsec tùy đoạn?** Vì phân đoạn kiểm soát đường đi và miền truy cập, còn tính toàn vẹn cần cơ chế xác thực thích hợp trên chính luồng dữ liệu.
6. **Nếu ứng dụng xử lý hai lần một request hợp lệ, lỗi nằm ở đâu?** Có thể nằm ở logic nghiệp vụ và kiểm soát idempotency/chống replay, dù nội dung mỗi request đều còn nguyên.

**Bài tập tình huống:** Một API công bố HTTPS nhưng request đi từ gateway đến backend bằng HTTP; backend chấp nhận trường **user_role** trong JSON do client gửi. Hãy vẽ DFD hai hop, chỉ ra ít nhất **hai đường tampering/giả mạo quyền**, đề xuất kiểm soát ở cả gateway và backend, sau đó nêu bằng chứng kiểm thử để chứng minh kết quả. Gợi ý: bảo vệ gateway → backend bằng mTLS và kiểm tra quyền người dùng ở backend từ nguồn danh tính đáng tin thay vì tin trường user_role do client tự khai.

Khi hoàn thành threat modeling cho một đường truyền, tài liệu cần thể hiện rõ **dữ liệu quan trọng, mỗi trust boundary, nơi giải mã/tái mã hóa, bên được quyền sửa, cơ chế integrity/authentication, cách chống replay và cách kiểm chứng bằng chứng**. Chỉ khi xác định đúng phạm vi bảo vệ, nhóm vận hành mới có thể chọn thiết kế phân đoạn, VPN, TLS/mTLS, MACsec, DNS, IDS/IPS và kiểm soát tầng ứng dụng phù hợp.

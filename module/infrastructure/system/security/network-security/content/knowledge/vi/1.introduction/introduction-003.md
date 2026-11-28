# Confidentiality, integrity và availability trên đường truyền

Khi một ứng dụng gửi yêu cầu đăng nhập, thông tin thanh toán hoặc dữ liệu nội bộ qua mạng, việc **gửi được gói tin đến đích** chưa đủ để gọi là an toàn. Dữ liệu có thể bị đọc trộm, thay đổi hoặc không đến được dịch vụ đúng lúc. Ba thuộc tính cốt lõi của an toàn thông tin — **confidentiality (tính bí mật), integrity (tính toàn vẹn) và availability (tính sẵn sàng)**, gọi tắt là **CIA triad** — giúp xác định cần bảo vệ điều gì trên đường truyền và chọn biện pháp phù hợp.

Trong bảo mật mạng, CIA không chỉ áp dụng cho một gói tin riêng lẻ. Ta cần xem toàn bộ hành trình: thiết bị người dùng, Wi-Fi/LAN, bộ định tuyến, Internet, DNS, load balancer, proxy, các dịch vụ nội bộ và đích nhận dữ liệu. Mỗi điểm chuyển tiếp hoặc điểm kết thúc mã hóa đều tạo ra một ranh giới cần đánh giá.

## 1. CIA trên đường truyền nghĩa là gì?

| Thuộc tính | Câu hỏi cần trả lời | Sự cố minh họa | Mục tiêu kiểm soát |
| --- | --- | --- | --- |
| **Confidentiality — Bí mật** | Ai có thể **đọc** nội dung đang truyền? | Người cùng mạng Wi-Fi thu được mật khẩu gửi bằng HTTP. | Chỉ các đầu mút và thành phần được cho phép mới đọc được nội dung cần bảo vệ. |
| **Integrity — Toàn vẹn** | Ai có thể **sửa, chèn, thay thế hoặc phát lại** dữ liệu mà bên nhận không phát hiện? | Kẻ tấn công thay đổi số tài khoản trong một thông điệp trên đường truyền. | Bên nhận phát hiện dữ liệu bị can thiệp và xác minh đúng nguồn truyền trong phạm vi cơ chế sử dụng. |
| **Availability — Sẵn sàng** | Dịch vụ và đường truyền có **hoạt động đúng lúc, đủ khả năng đáp ứng** không? | Lưu lượng DDoS làm cạn băng thông, khiến yêu cầu hợp lệ bị timeout. | Người dùng hợp lệ tiếp cận được dịch vụ trong ngưỡng thời gian và độ tin cậy đã đặt. |

Ba thuộc tính liên quan nhưng không thay thế nhau. Một kết nối được mã hóa có thể giữ bí mật và toàn vẹn nội dung, nhưng vẫn bị cắt mạng. Một hệ thống có dự phòng tốt có thể rất sẵn sàng, nhưng dữ liệu vẫn bị lộ nếu truyền qua kênh không mã hóa.

**Dữ liệu trên đường truyền (data in transit)** là thông tin đang được trao đổi giữa hai điểm qua giao thức mạng. Khái niệm này khác với dữ liệu **đang lưu trữ (at rest)** và dữ liệu **đang xử lý tại đầu mút (in use)**. TLS có thể bảo vệ nội dung lúc truyền nhưng không tự bảo vệ thông tin sau khi máy chủ đã giải mã để xử lý.

## 2. Đường đi của một yêu cầu và các ranh giới tin cậy

Xét ứng dụng đặt hàng gửi yêu cầu HTTPS đến API:

~~~mermaid
flowchart LR
    C["Ứng dụng khách"] -->|"HTTPS / TLS"| G["API Gateway / WAF"]
    G -->|"mTLS nếu được cấu hình"| S["Dịch vụ đặt hàng"]
    S -->|"TLS nếu được cấu hình"| D[("Cơ sở dữ liệu")]
~~~

Giả sử gateway kết thúc TLS để đọc và định tuyến yêu cầu:

1. **Từ ứng dụng khách tới gateway:** TLS bảo vệ nội dung trước người quan sát trung gian nếu khách kiểm tra chứng chỉ và kết nối được thiết lập đúng.
2. **Tại gateway:** nội dung được giải mã để xử lý. Đây là đầu mút tin cậy của chặng TLS đầu tiên; phân quyền, nhật ký, bộ nhớ và cấu hình của gateway đều có ý nghĩa với bảo mật.
3. **Từ gateway tới dịch vụ nội bộ:** cần **một kết nối được bảo vệ riêng** nếu muốn bảo vệ chặng này. Có HTTPS giữa khách và gateway không có nghĩa chặng nội bộ tự động được mã hóa.
4. **Từ dịch vụ tới cơ sở dữ liệu:** cần đánh giá giao thức, xác thực máy chủ, quyền truy cập, mạng chứa cơ sở dữ liệu và nhu cầu mã hóa của chính chặng đó.

Không nên mặc định rằng cùng một đường hầm mật mã tồn tại xuyên suốt mọi thành phần. Để thiết kế đúng, hãy vẽ **từng chặng (hop)**, xác định **điểm dữ liệu ở dạng rõ (plaintext)** và ghi rõ **thực thể nào được phép đọc hoặc sửa nội dung**.

Trong mạng thực tế, các nút chuyển tiếp vẫn có thể nhìn thấy một số **metadata** như địa chỉ IP, kích thước gói, thời điểm gửi và nhịp lưu lượng, dù phần tải ứng dụng đã được mã hóa. Mức che giấu tên miền, truy vấn DNS và thông tin phiên còn phụ thuộc giao thức, cấu hình và đường truyền cụ thể.

## 3. Confidentiality: không để người ngoài đọc nội dung

### 3.1. Rủi ro điển hình

- **Nghe lén thụ động:** một người có quyền quan sát lưu lượng ở mạng Wi-Fi, thiết bị trung gian hoặc tuyến mạng ghi lại gói tin.
- **Truy cập trái phép tại điểm trung gian:** proxy, gateway hoặc thiết bị giám sát có khả năng giải mã dữ liệu nhưng bị cấu hình quyền quá rộng.
- **Truyền nhầm chặng không mã hóa:** HTTPS ở phía Internet nhưng HTTP giữa reverse proxy và ứng dụng nội bộ.
- **Rò rỉ ngoài nội dung mã hóa:** DNS không được bảo vệ, URL chứa bí mật bị ghi vào log, hoặc lưu lượng tiết lộ thời điểm và kích thước trao đổi.

### 3.2. Những cơ chế thường dùng

**TLS (Transport Layer Security)** tạo kênh truyền được mã hóa giữa các đầu mút tham gia TLS, phổ biến nhất trong HTTPS. Trong TLS hiện đại, xác thực máy chủ thường dựa trên chứng chỉ và kiểm tra tên miền; khóa phiên được thiết lập qua quá trình bắt tay. Dữ liệu ứng dụng sau đó được mã hóa bằng thuật toán mã hóa có xác thực (AEAD).

**IPsec/VPN** có thể bảo vệ lưu lượng qua đường hầm hoặc giữa các host ở lớp mạng, tùy cách triển khai. **MACsec** có thể bảo vệ các khung mạng trên những liên kết Ethernet được hỗ trợ. **WPA2/WPA3** hỗ trợ bảo vệ liên kết vô tuyến Wi-Fi. Mỗi giải pháp có **ranh giới bảo vệ khác nhau**; ví dụ mã hóa Wi-Fi chỉ bảo vệ một đoạn liên kết và không thay thế TLS đến máy chủ đích.

**Mã hóa dữ liệu ở tầng ứng dụng** có thể hữu ích khi nội dung phải đi qua các trung gian được phép chuyển tiếp nhưng không được phép đọc. Việc này cần thiết kế riêng cơ chế quản lý khóa, người nhận và xác thực thông điệp; mã hóa thêm một lớp không tự giải quyết các vấn đề đó.

**Điều kiện quan trọng:** mã hóa chỉ có ý nghĩa chống giả mạo máy chủ khi ứng dụng xác minh danh tính đầu mút đúng cách. Nếu ứng dụng bỏ kiểm tra chứng chỉ hoặc bỏ kiểm tra hostname, kẻ tấn công có thể dựng một đầu mút giả và phá vỡ mục tiêu bí mật của kết nối.

### 3.3. Bảo mật nội dung không đồng nghĩa che giấu toàn bộ lưu lượng

Ngay cả khi dùng HTTPS đúng cách, người quan sát trên tuyến có thể biết hai địa chỉ IP đang giao tiếp, lượng dữ liệu trao đổi và thời điểm trao đổi. Truy vấn DNS dùng giao thức truyền thống có thể lộ tên miền cho bên quan sát; DNS over HTTPS (DoH) hoặc DNS over TLS (DoT) bảo vệ trao đổi với resolver trong phạm vi kết nối đó, nhưng không ẩn mọi metadata. **DNSSEC** xác thực nguồn gốc và toàn vẹn dữ liệu DNS được ký; nó **không phải cơ chế mã hóa truy vấn DNS**.

Vì vậy, trước khi khẳng định "dữ liệu không bị lộ", phải nêu rõ đang nói về **nội dung ứng dụng**, **danh tính đích**, **metadata** hay **dữ liệu tại các trung gian**.

## 4. Integrity: phát hiện thay đổi và giả mạo

### 4.1. Các dạng vi phạm tính toàn vẹn

- **Tampering:** sửa nội dung yêu cầu hoặc phản hồi trong lúc truyền.
- **Injection:** chèn thêm lệnh, thông điệp hoặc gói tin giả.
- **Impersonation:** giả danh máy chủ, thiết bị hoặc dịch vụ gửi dữ liệu.
- **Replay:** thu lại một yêu cầu từng hợp lệ rồi gửi lại ở thời điểm khác, ví dụ lặp một lệnh chuyển tiền.

Trong TLS hiện đại, các bản ghi dữ liệu được bảo vệ bằng **AEAD**: bên nhận có thể kiểm tra rằng bản ghi nhận được không bị sửa mà vẫn vượt qua xác thực mật mã. TLS còn xác thực quá trình bắt tay trong phạm vi mô hình tin cậy của nó. **Chứng chỉ hợp lệ và kiểm tra hostname** giúp khách xác định đang trao đổi với máy chủ có danh tính dự kiến, thay vì một máy chủ giả trên đường truyền.

**Hash đơn thuần chưa đủ để bảo vệ khỏi kẻ tấn công chủ động.** Nếu cả thông điệp lẫn giá trị hash cùng đi qua kênh mà kẻ tấn công kiểm soát, họ có thể sửa nội dung và tính lại hash. Để xác thực tính toàn vẹn cần cơ chế gắn với **bí mật hoặc khóa tin cậy**, chẳng hạn MAC/HMAC, chữ ký số hoặc AEAD cùng quy trình xác thực khóa phù hợp.

### 4.2. Giới hạn của TLS và mTLS

TLS bảo vệ những byte được trao đổi **giữa hai đầu mút TLS**, không bảo đảm rằng dữ liệu do người dùng nhập là đúng, chương trình phía máy chủ không bị chiếm quyền hoặc một thành phần tin cậy không cố ý sửa dữ liệu.

**mTLS (mutual TLS)** cho phép hai phía xác thực chứng chỉ của nhau, thường hữu ích cho giao tiếp giữa dịch vụ. Tuy nhiên, việc một dịch vụ có danh tính hợp lệ không có nghĩa nó được phép thực hiện mọi nghiệp vụ. Hệ thống vẫn cần **ủy quyền (authorization)** và kiểm tra dữ liệu đầu vào.

**Chống phát lại ở tầng nghiệp vụ** là trách nhiệm riêng. Giao thức TLS có cơ chế xử lý thứ tự và bảo vệ bản ghi trong phiên, nhưng ứng dụng vẫn cần xác định một yêu cầu thanh toán đã được xử lý chưa, đặc biệt khi khách tự gửi lại, mạng tự retry hoặc có thông điệp đi qua hàng đợi. Một cách phổ biến là dùng **idempotency key**, giới hạn thời gian hiệu lực và lưu kết quả xử lý để tránh tạo giao dịch trùng.

Ví dụ: khách gửi yêu cầu mua hàng trị giá 500.000 đồng. TLS giúp chống người đi đường sửa yêu cầu thành 5.000.000 đồng. Nhưng dịch vụ vẫn phải **tự tính tổng tiền từ dữ liệu đáng tin cậy**, xác minh quyền mua và ngăn xử lý lặp; nếu tin hoàn toàn vào trường giá từ khách, nghiệp vụ vẫn có thể bị lợi dụng dù đường truyền có TLS.

## 5. Availability: giữ đường truyền và dịch vụ hoạt động

Bí mật và toàn vẹn chủ yếu bảo vệ **nội dung trao đổi**. Tính sẵn sàng còn phụ thuộc **năng lực xử lý, băng thông, định tuyến, DNS, kết nối đến các phụ thuộc và khả năng phục hồi**.

### 5.1. Những cách dịch vụ mất sẵn sàng

- **DDoS/DoS:** lượng truy cập bất thường chiếm băng thông hoặc làm cạn kết nối, CPU, bộ nhớ và hàng đợi.
- **Sự cố hạ tầng:** hỏng thiết bị mạng, đứt tuyến, định tuyến sai, lỗi cân bằng tải hoặc gián đoạn DNS.
- **Lỗi cấu hình và phụ thuộc:** chứng chỉ hết hạn, firewall chặn nhầm, cấu hình MTU gây rớt gói, dịch vụ xác thực hoặc cơ sở dữ liệu ngừng hoạt động.
- **Lạm dụng yêu cầu hợp lệ:** yêu cầu tốn tài nguyên được gửi liên tục khiến dịch vụ chậm hoặc quá tải dù không sửa gói tin.

### 5.2. Bảo vệ theo nhiều lớp

| Lớp | Biện pháp | Tác dụng và giới hạn |
| --- | --- | --- |
| Biên Internet | Dịch vụ giảm thiểu DDoS, CDN, lọc lưu lượng ở nhà cung cấp mạng | Giảm tải trước khi lưu lượng lớn tới hạ tầng; không thay thế kiểm soát ứng dụng. |
| Gateway/ứng dụng | Rate limiting, quota, giới hạn kết nối, timeout hợp lý, circuit breaker | Giới hạn lạm dụng và hiệu ứng lan truyền; cần tránh chặn nhầm người dùng hợp lệ. |
| Hạ tầng | Load balancing, nhiều instance, dự phòng tuyến/khu vực, tự phục hồi | Giảm tác động của một điểm lỗi; cần kiểm tra việc chuyển đổi dự phòng thực tế. |
| Vận hành | Giám sát, cảnh báo, capacity planning, kiểm thử sự cố | Phát hiện sớm, xác định nút nghẽn và rút ngắn thời gian khôi phục. |

**TLS không bảo đảm availability**: gói tin mã hóa vẫn có thể bị bỏ, đường truyền vẫn có thể bị nghẽn và máy chủ vẫn có thể ngừng phản hồi. Một số biện pháp bảo mật còn có chi phí xử lý; vì thế phải chọn giới hạn kết nối, thời gian chờ và tài nguyên phù hợp với tải thực tế.

Ví dụ, một API có mục tiêu đáp ứng **99,9% số phút hoạt động theo tháng** cần định nghĩa rõ thế nào là "hoạt động", đo từ đâu và trong khoảng nào. Đo trạng thái máy chủ "đang chạy" là chưa đủ: khách có thể vẫn không phân giải được DNS hoặc không hoàn thành được yêu cầu.

## 6. Phân tích các tình huống thường gặp

| Tình huống | C bị ảnh hưởng? | I bị ảnh hưởng? | A bị ảnh hưởng? | Cách suy luận |
| --- | --- | --- | --- | --- |
| Gửi mật khẩu qua HTTP trên Wi-Fi công cộng | **Có** | **Có thể** | Chưa chắc | Người quan sát có thể đọc nội dung; kẻ trung gian chủ động còn có thể sửa. |
| Chặn DNS và trả về địa chỉ IP giả | **Có nguy cơ** | **Có nguy cơ** | **Có nguy cơ** | Nếu ứng dụng kiểm tra TLS đúng cách, máy chủ giả thường không thể vượt qua xác thực; yêu cầu vẫn có thể bị từ chối hoặc gián đoạn. |
| Kẻ tấn công sửa gói TLS đã được xác thực | Thông thường không | **Có ý định tấn công** | **Có thể** | Kiểm tra xác thực bản ghi sẽ phát hiện can thiệp; bản ghi bị loại bỏ có thể làm phiên lỗi, ảnh hưởng sẵn sàng. |
| HTTPS dừng ở load balancer, chặng sau dùng HTTP | **Có nguy cơ ở chặng sau** | **Có nguy cơ ở chặng sau** | Chưa chắc | Chỉ chặng đầu có bảo đảm của TLS; cần đánh giá ranh giới và mạng nội bộ. |
| DDoS làm nghẽn tuyến Internet | Chưa chắc | Chưa chắc | **Có** | Kẻ tấn công có thể ngăn trao đổi dù không đọc hoặc sửa nội dung. |
| Chứng chỉ máy chủ hết hạn | Không trực tiếp | Không trực tiếp | **Có thể** | Khách xác minh đúng sẽ từ chối kết nối; không nên tắt xác minh để "khôi phục" dịch vụ. |
| Máy chủ hợp lệ trả sai tổng tiền do lỗi nghiệp vụ | Không nhất thiết | **Có ở cấp nghiệp vụ** | Chưa chắc | Kênh truyền toàn vẹn không đồng nghĩa nội dung được tính toán chính xác. |

Các ô "có nguy cơ" phụ thuộc quyền của kẻ tấn công, giao thức sử dụng và cách hệ thống xác thực. Phân tích CIA nên bắt đầu bằng **mô hình mối đe dọa**, không kết luận chỉ từ tên công nghệ.

## 7. Áp dụng CIA vào thiết kế một API đặt hàng

Giả sử luồng chính là **ứng dụng khách → gateway → order-service → database**. Ứng dụng truyền token xác thực, mã sản phẩm, số lượng và địa chỉ nhận hàng. Doanh nghiệp muốn người ngoài không đọc dữ liệu, không sửa được yêu cầu và khách vẫn đặt hàng khi một instance bị lỗi.

**Bước 1 — Liệt kê tài sản và đầu mút.** Xác định nội dung nhạy cảm (token, địa chỉ, dữ liệu khách hàng), các dịch vụ được phép nhận nội dung và nơi TLS bắt đầu/kết thúc. Ghi rõ gateway có giải mã yêu cầu hay chỉ chuyển tiếp.

**Bước 2 — Thiết kế confidentiality.** Dùng HTTPS với xác minh chứng chỉ và tên miền từ khách tới gateway. Nếu rủi ro yêu cầu, dùng TLS/mTLS trên chặng gateway–order-service và TLS tới database. Hạn chế truy cập dữ liệu đã giải mã, tránh để token hoặc dữ liệu nhạy cảm trong log, URL và thông báo lỗi.

**Bước 3 — Thiết kế integrity.** Không cho phép bỏ kiểm tra chứng chỉ. Xác thực danh tính giữa các dịch vụ, cấp quyền theo hành động, kiểm tra yêu cầu tại order-service và tính giá trên máy chủ. Dùng idempotency key cho thao tác tạo đơn để xử lý retry an toàn. Nếu cần bảo vệ thông điệp xuyên qua nhiều trung gian độc lập, xem xét thêm chữ ký số ở tầng ứng dụng.

**Bước 4 — Thiết kế availability.** Đặt rate limit thích hợp cho luồng tạo đơn, giới hạn hàng đợi, phân phối lưu lượng tới nhiều instance và giám sát phụ thuộc database. Với API công khai, xem xét cơ chế giảm thiểu DDoS ở biên; kiểm tra phương án failover trước khi coi là sẵn sàng.

**Bước 5 — Ghi rõ trách nhiệm.** Nhóm nền tảng quản lý cấu hình mạng, gateway và chứng chỉ; nhóm phát triển quản lý xác thực, phân quyền, kiểm tra đầu vào và idempotency; nhóm vận hành theo dõi chất lượng dịch vụ và diễn tập sự cố. Các vai trò có thể khác nhau giữa tổ chức, nhưng mỗi ranh giới phải có người chịu trách nhiệm.

### Ma trận kiểm soát tối thiểu

| Chặng/đối tượng | C | I | A |
| --- | --- | --- | --- |
| Khách ↔ gateway | HTTPS, xác minh chứng chỉ, không ghi log bí mật | Xác minh hostname, bảo vệ phiên, kiểm tra yêu cầu | DNS đáng tin cậy, giới hạn tải và bảo vệ DDoS |
| Gateway ↔ order-service | TLS/mTLS khi phù hợp, giới hạn quyền trung gian | Xác thực danh tính dịch vụ, phân quyền | Timeout, cân bằng tải, health check |
| Order-service ↔ database | TLS cho kết nối, phân quyền DB | Ràng buộc dữ liệu, transaction và kiểm tra nghiệp vụ | Connection pool, giám sát, phương án phục hồi |
| Vận hành toàn tuyến | Quản lý khóa/chứng chỉ và truy cập log | Kiểm soát thay đổi, giám sát cấu hình | Theo dõi lỗi, độ trễ, tỷ lệ thành công và khôi phục |

Ma trận này chỉ là điểm khởi đầu. Có dùng mTLS, VPN, segmentation hay một thiết bị bảo mật cụ thể hay không phải dựa trên mô hình tin cậy, rủi ro, yêu cầu hiệu năng và môi trường triển khai.

## 8. Kiểm chứng trên hệ thống và trong phòng lab

Đừng kết luận an toàn chỉ vì biểu tượng ổ khóa xuất hiện trong trình duyệt. Kiểm thử cần bám theo từng thuộc tính CIA và từng chặng đã vẽ.

### 8.1. Quan sát kết nối TLS

Có thể xem thông tin bắt tay và phản hồi bằng các lệnh chỉ đọc trên một điểm cuối công khai:

~~~bash
# Quan sát kết nối HTTPS, chứng chỉ và phản hồi header
curl -Iv https://example.com/

# Kiểm tra chứng chỉ/tên miền máy chủ qua OpenSSL
openssl s_client -connect example.com:443 -servername example.com \
  -verify_hostname example.com -verify_return_error
~~~

Lệnh OpenSSL minh họa cho shell hỗ trợ nối dòng bằng dấu gạch chéo ngược; trên Windows có thể viết toàn bộ tham số trên một dòng. Thực hiện kiểm tra tương tự với **hostname thực của từng chặng** trong môi trường được phép kiểm thử.

Cần xác nhận chứng chỉ hợp lệ, hostname khớp, đường xác thực chứng chỉ đáng tin cậy, giao thức và cấu hình mã hóa đáp ứng chính sách của hệ thống. Kết quả phía khách **không chứng minh** kết nối từ gateway tới upstream đã được mã hóa; phải kiểm tra cấu hình và kết nối ở chặng upstream riêng.

### 8.2. Phân biệt các phép kiểm tra C, I và A

| Thuộc tính | Câu hỏi kiểm chứng | Bằng chứng nên thu thập |
| --- | --- | --- |
| **C** | Trên từng chặng, có thể đọc được payload nhạy cảm khi quan sát lưu lượng không? Có điểm nào giải mã và ghi log dữ liệu quá mức? | Sơ đồ TLS termination, cấu hình kết nối, quan sát gói tin trong lab được phép, chính sách log. |
| **I** | Kết nối tới máy chủ sai hostname hoặc chứng chỉ không hợp lệ có bị từ chối? Thao tác bị retry có gây trùng giao dịch? | Kết quả kiểm tra xác minh chứng chỉ, kiểm thử nghiệp vụ và nhật ký audit. |
| **A** | Dịch vụ phản hồi thế nào khi một instance lỗi, DNS chập chờn hoặc tải tăng trong ngưỡng đã cho phép? | Tỷ lệ yêu cầu thành công, latency p95/p99, timeout, packet loss, thời gian failover và diễn tập phục hồi. |

Trong thử nghiệm integrity, việc cố sửa nội dung TLS thường dẫn tới **lỗi xác thực và loại bỏ dữ liệu**, không phải gói tin sai vẫn được giao nguyên cho ứng dụng. Điều này là hành vi mong muốn của cơ chế phát hiện, dù sự cố vẫn có thể làm giảm availability.

Khi đánh giá availability, theo dõi ít nhất **tỷ lệ yêu cầu thành công từ góc nhìn khách**, **độ trễ**, **số kết nối lỗi/timeout**, **tài nguyên gateway và ứng dụng**, **tình trạng DNS** và **thời gian khôi phục**. Chỉ số của một thiết bị riêng lẻ không đại diện cho trải nghiệm đầu cuối.

## 9. Những nhầm lẫn cần tránh

1. **"Có VPN thì không cần HTTPS."** VPN bảo vệ lưu lượng trong phạm vi đường hầm đã xác định; thông tin có thể tiếp tục qua các chặng khác. HTTPS vẫn hữu ích cho xác thực máy chủ và bảo vệ kênh ứng dụng.
2. **"Dùng HTTPS là an toàn từ khách đến database."** HTTPS chỉ bảo vệ các đầu mút TLS tương ứng; proxy và backend có thể sử dụng kết nối khác.
3. **"Có mã hóa là có toàn vẹn."** Phải dùng cơ chế mã hóa có xác thực hoặc cơ chế xác thực thông điệp phù hợp; mã hóa thuần túy không tự chứng minh dữ liệu chưa bị sửa.
4. **"TLS ngăn DDoS."** TLS không giữ cho mạng, DNS và máy chủ luôn khả dụng trước nghẽn hoặc cạn tài nguyên.
5. **"Kiểm tra chứng chỉ bị lỗi thì tạm tắt xác minh."** Làm vậy mở đường cho giả mạo máy chủ. Cần sửa nguyên nhân: tên miền, thời hạn, chuỗi tin cậy, đồng hồ hoặc cấu hình chứng chỉ.
6. **"Network segmentation hoặc firewall đồng nghĩa dữ liệu được mã hóa."** Các công cụ này kiểm soát đường đi và quyền truy cập; cần cơ chế riêng để bảo vệ nội dung trên chặng truyền.
7. **"TLS bảo đảm mọi yêu cầu đều đúng."** TLS xác thực kênh truyền, không xác nhận sự chính xác của giá hàng, quyền thao tác hay tính duy nhất của giao dịch.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Một ứng dụng dùng HTTPS từ điện thoại đến reverse proxy, sau đó proxy dùng HTTP tới service trong cùng VPC. Có thể khẳng định nội dung luôn bí mật trên mọi chặng không?

**Trả lời:** Không. TLS bảo vệ chặng điện thoại–proxy. Chặng proxy–service cần đánh giá quyền quan sát, mức độ tin cậy của mạng và cơ chế bảo vệ riêng; nếu yêu cầu bảo mật cần mã hóa thì phải cấu hình TLS hoặc giải pháp tương đương cho chặng này.

**Câu 2.** Một yêu cầu có nội dung đúng và được bảo vệ bằng TLS nhưng dịch vụ bị DDoS khiến khách không nhận được phản hồi. Thuộc tính nào bị ảnh hưởng trực tiếp?

**Trả lời:** Availability. Việc nội dung chưa bị đọc hay sửa không giúp kết nối hoạt động khi đường truyền hoặc dịch vụ bị nghẽn.

**Câu 3.** API nhận giá tiền từ khách qua HTTPS. Kẻ tấn công là chính người gửi yêu cầu và tự đặt giá thấp hơn. TLS có chặn được không?

**Trả lời:** Không. TLS bảo vệ việc truyền dữ liệu giữa các đầu mút nhưng không xác định dữ liệu do khách cung cấp có hợp lệ về nghiệp vụ hay không. Máy chủ phải tự tính giá, xác thực quyền và kiểm tra ràng buộc.

**Câu 4.** Bên gửi kèm một giá trị SHA-256 của thông điệp trong cùng gói HTTP không mã hóa. Điều này đủ chống kẻ trung gian sửa nội dung không?

**Trả lời:** Không. Nếu sửa được thông điệp thì đối thủ cũng có thể tính lại SHA-256. Cần xác thực thông điệp với một khóa bí mật, chữ ký số hoặc kênh TLS được xác minh phù hợp.

## 11. Ghi nhớ khi thiết kế bảo mật mạng

Khi đánh giá bất kỳ luồng truyền nào, hãy trả lời lần lượt:

1. **Bảo vệ cái gì?** Nội dung, danh tính hai đầu mút, metadata hay khả năng hoàn thành yêu cầu?
2. **Bảo vệ ở chặng nào?** Chỉ từ người dùng đến gateway, hay cả các kết nối nội bộ, DNS và phụ thuộc?
3. **Chống ai và chống cách tấn công nào?** Người nghe lén, kẻ trung gian sửa gói, dịch vụ nội bộ bị xâm nhập, hay đối thủ gây gián đoạn?
4. **Kiểm chứng bằng chứng gì?** Cấu hình bảo vệ từng chặng, xác thực chứng chỉ, kiểm tra nghiệp vụ, đo chất lượng dịch vụ và kiểm thử sự cố.

**Confidentiality bảo vệ khỏi việc đọc trái phép; integrity bảo vệ khỏi sửa đổi không được phát hiện; availability bảo vệ khả năng sử dụng.** Thiết kế mạng an toàn cần phối hợp các biện pháp mật mã, xác thực, phân quyền, kiểm soát lưu lượng, phân đoạn, dự phòng và giám sát. Đánh giá theo từng chặng và theo mối đe dọa cụ thể sẽ tránh được cả hai cực đoan: tin rằng một công nghệ giải quyết toàn bộ CIA, hoặc bổ sung quá nhiều thiết bị mà vẫn bỏ sót ranh giới truyền dữ liệu quan trọng.

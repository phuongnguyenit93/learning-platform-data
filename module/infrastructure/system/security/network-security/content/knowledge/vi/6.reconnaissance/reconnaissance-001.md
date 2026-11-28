# Passive reconnaissance

Trong bảo mật mạng, **reconnaissance** (trinh sát, thu thập thông tin ban đầu) là quá trình tìm hiểu một hệ thống trước khi đánh giá rủi ro hoặc thiết kế biện pháp phòng vệ. Thông tin thu được có thể giúp nhận diện miền Internet, địa chỉ IP, nhà cung cấp hạ tầng, các dịch vụ đã công bố, mối quan hệ giữa tài sản và những dấu hiệu phơi lộ ngoài ý muốn.

**Passive reconnaissance** (trinh sát thụ động) tập trung thu thập và phân tích thông tin **không cần gửi lưu lượng thăm dò trực tiếp tới hệ thống mục tiêu**. Thay vào đó, người phân tích sử dụng dữ liệu đã được công bố, lưu trữ hoặc quan sát bởi những nguồn khác: cơ sở dữ liệu đăng ký tên miền, Certificate Transparency, hồ sơ định tuyến công khai, chỉ mục tìm kiếm, kho mã nguồn được công khai hợp pháp hoặc dữ liệu DNS lịch sử do bên thứ ba cung cấp.

Với module **SECURITY_NETWORK_SECURITY**, kỹ thuật này có giá trị thực tế trong **quản lý bề mặt tấn công**, kiểm tra phạm vi trust zone, mô hình hóa mối đe dọa và ưu tiên bảo vệ DNS, firewall, VPN, mạng không dây và hạ tầng đám mây. Nó cung cấp **giả thuyết có bằng chứng** về những gì có thể bị nhìn thấy từ bên ngoài, chứ không tự chứng minh một hệ thống đang tồn tại, mở cổng hay có lỗ hổng ở thời điểm hiện tại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích passive reconnaissance và phân biệt với active reconnaissance.
2. Lựa chọn nguồn OSINT phù hợp để tìm hiểu tên miền, IP, ASN, chứng thư TLS, DNS và dấu vết dịch vụ.
3. Ghi nhận nguồn gốc, thời điểm và mức độ tin cậy của từng thông tin, tránh suy luận quá mức.
4. Lập danh mục tài sản có khả năng thuộc tổ chức, phân biệt tài sản đã xác nhận với ứng viên cần xác minh.
5. Chuyển kết quả trinh sát thành câu hỏi phòng vệ cụ thể về phân đoạn mạng, quản trị, VPN, DNS và đám mây.
6. Thiết kế một quy trình rà soát có giới hạn phạm vi, bảo vệ dữ liệu và báo cáo có thể kiểm chứng.

## 2. “Thụ động” được hiểu như thế nào?

**Đặc điểm phân biệt là quan hệ với mục tiêu:** người phân tích không chủ động gửi gói tin, yêu cầu HTTP, truy vấn dịch vụ hay lưu lượng thử nghiệm đến hạ tầng mục tiêu để khám phá nó.

| Hành động | Phân loại thường dùng | Giải thích |
| --- | --- | --- |
| Đọc kết quả từ công cụ tìm kiếm đã lập chỉ mục | Thụ động đối với hệ thống đích | Truy cập công cụ tìm kiếm, không trực tiếp gọi máy chủ đích |
| Xem dữ liệu chứng thư đã có trong Certificate Transparency (CT) log qua dịch vụ tra cứu | Thụ động đối với hệ thống đích | Dữ liệu công khai được ghi nhận trước đó |
| Tra cứu bản ghi đăng ký tên miền hoặc ASN qua RDAP của đơn vị đăng ký | Thụ động đối với hệ thống đích | Gửi yêu cầu đến nguồn dữ liệu đăng ký, không thăm dò máy chủ của tổ chức |
| Đọc passive DNS hoặc lịch sử IP–hostname của nhà cung cấp dữ liệu | Thụ động đối với hệ thống đích | Dùng quan sát đã được bên thứ ba thu thập |
| Xem chỉ mục dịch vụ do một nền tảng Internet scanning đã tạo sẵn | Thụ động đối với hệ thống đích đối với người xem | **Việc nền tảng tạo chỉ mục có thể đã dùng quét chủ động** |
| Tự gửi truy vấn DNS để phân giải hostname của mục tiêu | Có thể tạo tương tác chủ động hoặc gián tiếp với hạ tầng đích | Resolver có thể liên hệ máy chủ DNS authoritative của đích nếu chưa có cache |
| Trực tiếp truy cập website, tải robots.txt hoặc gọi API mục tiêu | Chủ động | Máy chủ đích nhận yêu cầu HTTP và có thể ghi log |
| Tự thực hiện TCP connect, ping, traceroute hay quét cổng | Chủ động | Gửi lưu lượng thăm dò đến hạ tầng hoặc đường mạng tới đích |

Khái niệm “passive” luôn cần ghi rõ **thụ động đối với ai**. Việc truy cập một dịch vụ CT hoặc công cụ tìm kiếm vẫn tạo yêu cầu đến **nhà cung cấp dữ liệu**, có thể bị ghi log, giới hạn tốc độ hoặc yêu cầu tài khoản. “Thụ động” không đồng nghĩa ẩn danh, không để lại dấu vết ở mọi nơi, không có rủi ro pháp lý, hay không cần xem xét quyền sử dụng dữ liệu.

### 2.1. Passive reconnaissance và OSINT

**OSINT** (*Open Source Intelligence*) là hoạt động khai thác thông tin từ các nguồn có thể tiếp cận hợp pháp, gồm dữ liệu công khai và các dịch vụ dữ liệu được cấp phép. OSINT không tự động luôn thụ động: nếu người thực hiện dùng kết quả tìm kiếm để trực tiếp tải nội dung từ máy chủ đích, thao tác tải đó đã tạo tương tác trực tiếp.

Trong thực hành, một đợt passive reconnaissance thường sử dụng OSINT. Tuy nhiên, nên đánh giá **từng thao tác thu thập**, không gắn nhãn “thụ động” cho toàn bộ quy trình chỉ vì đã dùng công cụ OSINT.

## 3. Quy trình thực hiện có cấu trúc

Một quy trình hữu ích bắt đầu bằng câu hỏi phòng vệ và kết thúc bằng danh sách cần xác minh hoặc xử lý.

~~~mermaid
flowchart TD
    A["Xác định phạm vi và câu hỏi phòng vệ"] --> B["Chọn nguồn thông tin bên thứ ba"]
    B --> C["Thu thập bằng chứng và thời điểm"]
    C --> D["Chuẩn hóa tên, IP, ASN, chứng thư"]
    D --> E["Liên kết tài sản và đánh giá độ tin cậy"]
    E --> F["Đối chiếu danh mục tài sản nội bộ"]
    F --> G["Ưu tiên giả thuyết rủi ro và kiến nghị"]
    G --> H["Cập nhật danh mục, theo dõi biến động"]
~~~

**Bước 1 – Xác định phạm vi.** Ví dụ, nhóm bảo mật cần rà soát những miền con của một tên miền **do tổ chức sở hữu**, những tài sản từng xuất hiện trong CT log hoặc những dải địa chỉ được đăng ký dưới ASN của tổ chức. Ghi rõ tên miền gốc, tổ chức pháp lý và nguồn dữ liệu được phép dùng.

**Bước 2 – Chọn nguồn theo câu hỏi.** CT hỗ trợ phát hiện tên DNS xuất hiện trong chứng thư; RDAP và hồ sơ BGP hỗ trợ nhận diện quyền đăng ký và thông tin định tuyến; passive DNS giúp nghiên cứu liên hệ lịch sử giữa tên và địa chỉ; dữ liệu kho mã nguồn công khai có thể hé lộ tên môi trường hoặc endpoint đã được nhắc tới.

**Bước 3 – Thu thập có dấu vết.** Mỗi phát hiện cần lưu **giá trị gốc, đường dẫn hoặc mã nguồn dữ liệu, thời điểm quan sát, thời điểm thu thập và ghi chú**. Không trộn dữ liệu lịch sử với dữ liệu hiện tại mà bỏ mốc thời gian.

**Bước 4 – Chuẩn hóa và khử trùng lặp.** Chuẩn hóa chữ hoa/chữ thường của tên DNS, loại bỏ trùng lặp, tách các tên wildcard, giữ nguyên địa chỉ IPv4/IPv6, tránh nhập nhằng tên miền với URL và giữ thông tin về nguồn.

**Bước 5 – Kiểm chứng mức độ liên quan.** Một tên chứa thương hiệu của tổ chức chưa chắc thuộc tổ chức. IP có thể thuộc CDN, dịch vụ chia sẻ hoặc đã được chuyển nhượng. Hãy đánh dấu “ứng viên” cho tới khi có bằng chứng quyền sở hữu hoặc sự xác nhận từ đội phụ trách.

**Bước 6 – Chuyển thành hành động phòng vệ.** Đối chiếu với asset inventory, CMDB, DNS được quản lý, danh sách ứng dụng, cloud account và quy trình cấp chứng thư; chỉ thực hiện kiểm thử chủ động khi có phạm vi, thời gian và quyền phù hợp.

## 4. Nguồn dữ liệu phổ biến và giới hạn

### 4.1. Thông tin tên miền, đăng ký và RDAP

RDAP (*Registration Data Access Protocol*) cung cấp dữ liệu đăng ký có cấu trúc đối với tên miền và tài nguyên Internet khi các nhà đăng ký hoặc registry hỗ trợ. Kết quả có thể gồm đơn vị đăng ký, trạng thái, máy chủ tên, các mốc thời gian và thông tin liên hệ đã được công khai hoặc che giấu theo chính sách.

**Giá trị:** xác định tên miền ứng viên, mối liên hệ đăng ký hoặc đặc điểm cần xác minh.

**Giới hạn:** thông tin người đăng ký có thể bị ẩn; dịch vụ proxy bảo vệ quyền riêng tư hoặc bên thứ ba quản lý tên miền có thể làm việc suy ra chủ sở hữu không chắc chắn. Hai tên miền dùng cùng nhà đăng ký hoặc nameserver **không đủ** để kết luận cùng chủ sở hữu.

### 4.2. Certificate Transparency (CT)

CT là cơ chế ghi nhận công khai thông tin về chứng thư TLS được phát hành và những sự kiện liên quan. Khi một tổ chức xin chứng thư cho các hostname, các tên xuất hiện trong chứng thư hoặc phần dữ liệu được ghi nhận có thể trở thành dấu vết hữu ích.

**Giá trị:** có thể phát hiện các hostname từng được ghi trong chứng thư, kể cả tên môi trường thử nghiệm, cổng truy cập hoặc tên đã ngừng sử dụng.

**Giới hạn cần nhớ:**

- Chứng thư được ghi nhận **không chứng minh** hostname còn phân giải DNS hay còn máy chủ hoạt động.
- Một bản ghi CT có thể đại diện chứng thư đã hết hạn, bị thu hồi hoặc đã được thay thế.
- Chứng thư wildcard như *.example.com không liệt kê toàn bộ tên miền con nằm dưới nó.
- Tên xuất hiện trong chứng thư không xác minh rằng toàn bộ hạ tầng tương ứng thuộc cùng một đơn vị vận hành.

### 4.3. Passive DNS và lịch sử phân giải

Nguồn passive DNS lưu những cặp tên–bản ghi mà hệ thống thu thập đã quan sát theo thời gian, ví dụ liên hệ giữa một hostname và địa chỉ A/AAAA, CNAME, MX hoặc NS.

**Giá trị:** hỗ trợ tìm các đích IP từng được liên kết, nhận diện chuyển đổi nhà cung cấp, thay đổi CDN và dấu vết dịch vụ cũ.

**Giới hạn:** mỗi nhà cung cấp có phạm vi cảm biến, độ trễ và chính sách dữ liệu khác nhau. Không thấy hostname trong một nguồn **không có nghĩa** hostname không tồn tại. Bản ghi cũ không chứng minh đường đi mạng hiện tại.

### 4.4. Đăng ký IP, ASN và thông tin định tuyến công khai

Các registry khu vực và những nguồn tổng hợp BGP cung cấp thông tin về phân bổ địa chỉ, số hiệu hệ thống tự trị (*Autonomous System Number* – ASN) và các prefix từng được quảng bá.

**Giá trị:** hỗ trợ tìm bối cảnh nhà mạng, chủ thể đăng ký tài nguyên, phạm vi mạng cần rà soát và những phụ thuộc kết nối.

**Giới hạn:** sở hữu hoặc đăng ký prefix không đồng nghĩa một dịch vụ cụ thể chạy trên địa chỉ đó. Đối với hạ tầng cloud/CDN, địa chỉ IP có thể thuộc nhà cung cấp trong khi ứng dụng do khách hàng khác vận hành; thông tin định tuyến cũng thay đổi theo thời gian.

### 4.5. Công cụ tìm kiếm và bản lưu nội dung

Chỉ mục tìm kiếm, tài liệu được công khai và bản lưu của bên thứ ba có thể chứa danh sách hostname, đường dẫn endpoint, tài liệu kiến trúc hoặc thông báo vận hành.

**Giá trị:** giúp nhận diện thông tin mà tổ chức đã công khai và có thể bị người khác tiếp cận.

**Giới hạn:** kết quả có thể cũ, bị trích sai, nằm ngoài phạm vi hoặc không còn truy cập được. **Không suy đoán hệ thống đích đang mở chỉ vì công cụ tìm kiếm có URL của nó.** Truy cập trực tiếp URL mục tiêu là bước chủ động riêng.

### 4.6. Kho mã nguồn và tài liệu công khai

README, tài liệu SDK, cấu hình mẫu, issue tracker hoặc ví dụ triển khai được công khai có thể chứa hostname, môi trường triển khai và kiến trúc kết nối.

**Giá trị:** giúp chủ sở hữu nhận ra thông tin cấu hình hoặc định danh hạ tầng vô tình được công bố.

**Giới hạn và xử lý:** không thử dùng khóa truy cập hoặc bí mật nếu phát hiện; không sao chép lại giá trị nhạy cảm vào báo cáo chia sẻ rộng. Chỉ ghi loại thông tin, vị trí nguồn đã kiểm soát quyền truy cập và đề nghị đội sở hữu kiểm tra, thu hồi hoặc thay thế bí mật theo quy trình.

### 4.7. Dữ liệu chỉ mục dịch vụ do bên thứ ba thu thập

Một số nhà cung cấp duy trì ảnh chụp về dịch vụ Internet, chứng thư hoặc banner đã quan sát từ trước. Việc **đọc kết quả có sẵn** có thể được xem là thụ động đối với hạ tầng mục tiêu, dù hoạt động thu thập của nhà cung cấp có thể đã là quét chủ động.

**Giá trị:** đặt giả thuyết về cổng, sản phẩm hoặc phiên bản từng được quan sát.

**Giới hạn:** banner có thể bị làm giả, che giấu qua proxy, bị lưu từ thời điểm cũ hoặc trỏ tới hệ thống đã chuyển chủ. Không lấy “cổng mở trong chỉ mục” làm bằng chứng kết luận hiện trạng, và càng không kết luận có lỗ hổng chỉ dựa trên chuỗi phiên bản.

## 5. Nhận diện thông tin mạng từ dấu vết thụ động

### 5.1. DNS: nhìn thấy tên và vai trò có thể có

Các loại bản ghi DNS được bên thứ ba lưu lại có thể gợi ý:

| Loại dữ liệu | Điều có thể suy ra | Điều chưa thể kết luận |
| --- | --- | --- |
| A/AAAA lịch sử | Tên từng liên hệ với một IP | IP đó còn được dùng; cổng nào đang mở |
| CNAME | Tên từng trỏ qua bí danh hoặc nhà cung cấp dịch vụ | Quyền sở hữu và tình trạng cấu hình hiện tại |
| MX | Hạ tầng nhận email được công bố hoặc quan sát | Cơ chế chống giả mạo email đã cấu hình đúng |
| NS | Nameserver phục vụ vùng DNS tại thời điểm quan sát | Mọi hostname con hay dịch vụ bên trong |
| TXT (SPF, DMARC hoặc dữ liệu xác minh dịch vụ) | Có dấu hiệu sử dụng nhà cung cấp và chính sách được công bố | Chính sách đã được áp dụng đúng trên toàn hệ thống |
| CT chứa SAN của chứng thư | Hostname từng xuất hiện trong yêu cầu cấp chứng thư | Hostname đang hoạt động hoặc còn thuộc cùng môi trường |

Khi khảo sát **bảo vệ DNS**, các dấu vết này có thể dẫn tới câu hỏi: Có miền cũ chưa thu hồi? Có bản ghi trỏ tới dịch vụ cloud không còn được quản lý? Tên môi trường quản trị có được đặt công khai ngoài chủ đích? Để trả lời dứt điểm phải đối chiếu với vùng DNS do tổ chức quản lý và có thể cần kiểm tra chủ động được phê duyệt.

### 5.2. VPN, truy cập từ xa và mặt phẳng quản trị

Một tên như vpn.example.com, remote.example.com hoặc admin.example.com trong bộ dữ liệu **giả định** chỉ là dấu hiệu đặt tên. Không nên suy luận có VPN hoạt động, cổng quản trị đang mở hay người ngoài truy cập được.

Đối với nhóm bảo mật, dấu hiệu đó là lý do rà soát:

- Đường truy cập từ xa có được gắn với hệ thống xác thực mạnh và MFA?
- Có phân quyền theo người dùng, thiết bị và tài nguyên đích thay vì cấp quyền toàn mạng?
- Giao diện quản trị có nằm sau bastion, VPN/ZTNA hoặc kiểm soát phù hợp?
- Firewall có ngăn đường đi trực tiếp từ Internet tới vùng dữ liệu hoặc thiết bị mạng?

### 5.3. Hạ tầng cloud, CDN và dịch vụ dùng chung

Hostname hoặc dữ liệu đăng ký có thể cho thấy dấu vết sử dụng nhà cung cấp cloud, CDN, dịch vụ email hoặc nền tảng SaaS. Hãy ghi nhận **mối phụ thuộc** thay vì quy toàn bộ IP hay ASN của nhà cung cấp thành tài sản thuộc tổ chức.

Ví dụ, nếu tên DNS cũ trong passive DNS từng trỏ tới endpoint cloud, đội cloud cần kiểm tra tài nguyên tương ứng còn thuộc account được quản lý hay không, có còn bản ghi DNS không và có cơ chế phát hiện tài nguyên bỏ quên. Không cần thử truy cập endpoint hoặc chiếm tên/tài nguyên để xác nhận giả thuyết ở giai đoạn thụ động.

### 5.4. Mạng không dây và thiết bị biên

Thông tin công khai về địa điểm, mô hình thiết bị, sơ đồ triển khai hoặc tên SSID trong tài liệu có thể giúp tạo danh sách câu hỏi kiểm tra Wi-Fi. Chúng không chứng minh một điểm truy cập còn phát sóng, có thể kết nối từ xa hay dùng cấu hình xác thực nào.

Việc thu bắt khung vô tuyến ở hiện trường là kỹ thuật quan sát khác, có thể thụ động về phát sóng nhưng liên quan đến dữ liệu người dùng và phạm vi tiếp cận vật lý; không được đánh đồng với passive reconnaissance chỉ dựa trên nguồn công khai.

## 6. Mức độ tin cậy: điều gì là bằng chứng, điều gì chỉ là giả thuyết?

Một bài phân tích tốt phải phân biệt:

- **Quan sát trực tiếp từ nguồn:** “Một bản ghi CT được công bố có chứa tên host A, theo dữ liệu truy xuất ngày X.”
- **Diễn giải có điều kiện:** “Tên host A có thể liên quan đến một dịch vụ dành cho quản trị.”
- **Khẳng định chưa đủ cơ sở:** “Dịch vụ quản trị A đang mở cổng trên Internet và dễ bị khai thác.”

Hai suy luận sau không tự động xuất phát từ quan sát đầu tiên. Cần xác minh quyền sở hữu, thời điểm, loại dữ liệu và cấu hình hiện tại trước khi báo cáo rủi ro như một sự thật.

### 6.1. Các tiêu chí đánh giá

| Tiêu chí | Câu hỏi cần trả lời |
| --- | --- |
| Độ tin cậy của nguồn | Dữ liệu từ registry, CT, hệ thống công bố chính thức hay bản sao không rõ nguồn? |
| Thời gian | Bản ghi được tạo khi nào? Quan sát cuối cùng cách đây bao lâu? |
| Tính liên quan | Tên, IP hoặc tài khoản có thật sự thuộc tổ chức được đánh giá? |
| Chứng cứ độc lập | Có nguồn thứ hai hoặc xác nhận từ đội sở hữu hỗ trợ không? |
| Mức biến động | Tài sản ổn định hay IP/container/endpoint thường xuyên thay đổi? |
| Giới hạn của phương pháp | Nguồn có đo được tính khả dụng thực tế, cổng mở hay quyền truy cập không? |

Có thể dùng nhãn đơn giản:

| Nhãn | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| **Đã xác nhận** | Được chủ tài sản, inventory hoặc nguồn nội bộ đáng tin cậy xác nhận | Dùng để cập nhật danh mục hoặc lập kế hoạch bảo vệ |
| **Có khả năng liên quan** | Có nhiều dấu vết phù hợp nhưng chưa đủ bằng chứng sở hữu/hiện trạng | Chuyển cho người phụ trách xác minh |
| **Chưa rõ** | Dữ liệu cũ, mâu thuẫn, thiếu liên hệ hoặc có thể thuộc bên thứ ba | Giữ thành giả thuyết; không quy kết lỗ hổng |
| **Không liên quan/đã loại trừ** | Có bằng chứng tài sản không thuộc phạm vi | Loại khỏi danh sách ưu tiên, lưu lý do |

“Có hai nguồn” không luôn bằng “hai bằng chứng độc lập”: hai trang có thể sao chép từ cùng một bộ dữ liệu. Cần ghi **nguồn gốc thực sự** của bản ghi khi có thể.

## 7. Ví dụ thực hành trên dữ liệu giả lập

Giả sử nhóm an ninh của **Công ty Ví Dụ** được giao rà soát bề mặt Internet liên quan đến tên miền dành cho tài liệu, **example.com**. Tất cả tên host và quan hệ dưới đây đều là **dữ liệu giả lập**, không phải kết quả tra cứu thực tế hay khẳng định về tên miền đó.

### 7.1. Bộ bằng chứng giả lập

| Mã | Nguồn ghi nhận | Dữ liệu minh họa | Thời điểm được nguồn ghi nhận | Nhận định ban đầu |
| --- | --- | --- | --- | --- |
| E-01 | CT log qua dịch vụ tra cứu | cert SAN: api.example.com | 2026-03-10 | Có tên host gợi ý API |
| E-02 | CT log qua dịch vụ tra cứu | cert SAN: vpn.example.com | 2025-10-04 | Có tên host gợi ý điểm truy cập từ xa |
| E-03 | Passive DNS | old-dev.example.com → 192.0.2.18 | 2024-11-22 | Có liên hệ DNS lịch sử cần rà soát |
| E-04 | Tài liệu cấu hình được công khai | Nhắc đến api.example.com | 2026-04-15 | Có dấu vết bổ sung về tên API |
| E-05 | Dữ liệu đăng ký | example.com được ghi trong hồ sơ tên miền | 2026-04-15 | Cần đối chiếu với thông tin sở hữu nội bộ |

Dải **192.0.2.0/24** được dành cho tài liệu và ví dụ, không đại diện địa chỉ của một hệ thống thực. Các mốc thời gian nêu trên chỉ minh họa cho cách lập hồ sơ bằng chứng.

### 7.2. Phân tích từng phát hiện

**E-01 và E-04:** Hai nguồn cùng nhắc đến api.example.com, tăng lý do để điều tra đây có phải endpoint nghiệp vụ hay không. Tuy nhiên, chứng thư và tài liệu vẫn chưa chứng minh endpoint đang hoạt động, dùng cổng nào, hoặc đã áp dụng xác thực/phân quyền phù hợp.

**E-02:** vpn.example.com có thể liên quan truy cập từ xa. Báo cáo nên đề nghị chủ hệ thống kiểm tra inventory VPN/ZTNA, MFA, danh sách quyền vào vùng quản trị và log truy cập. Không được viết “VPN bị công khai và có lỗ hổng” khi chỉ có tên trong CT.

**E-03:** old-dev.example.com có dấu vết DNS từ năm 2024. Phần việc tiếp theo là hỏi đội quản trị DNS/cloud liệu tên cũ đã được thu hồi và có còn tài nguyên hoặc CNAME chưa được dọn dẹp. Chưa có bằng chứng dịch vụ tồn tại trong năm 2026.

**E-05:** Dữ liệu đăng ký giúp xác định đầu mối để đối chiếu; quyền sở hữu cần được xác minh theo thông tin tổ chức. Không mở rộng tất cả IP cùng nhà cung cấp thành phạm vi kiểm thử.

### 7.3. Mẫu hồ sơ phát hiện

~~~yaml
findingId: PASSIVE-001
scope: example.com
assetCandidate: vpn.example.com
category: possible-remote-access
status: needs-owner-verification
evidence:
  - sourceType: certificate-transparency
    observedAt: "2025-10-04"
    collectedAt: "2026-11-28"
    description: "Hostname xuất hiện trong dữ liệu chứng thư giả lập"
inference: "Tên gợi ý điểm truy cập từ xa"
limitations:
  - "Không chứng minh dịch vụ còn hoạt động"
  - "Không chứng minh cổng hoặc cơ chế xác thực"
suggestedOwnerCheck:
  - "Đối chiếu inventory dịch vụ truy cập từ xa"
  - "Kiểm tra MFA và chính sách truy cập tối thiểu"
  - "Kiểm tra luồng quản trị qua VPN/ZTNA"
~~~

Mẫu này cố ý tách **bằng chứng** khỏi **suy luận** và **bước xác minh**. Trong hệ thống báo cáo thật, có thể bổ sung mã ticket, chủ sở hữu, đường dẫn tới nguồn và hạn hoàn thành. Tránh đưa dữ liệu cá nhân hoặc bí mật truy cập vào các trường mô tả.

## 8. Dùng kết quả passive reconnaissance trong thiết kế phòng vệ

### 8.1. Quản lý bề mặt tấn công bên ngoài

Đối chiếu tập hostname, tên miền, IP và dịch vụ ứng viên với danh mục đã được tổ chức phê duyệt. Chênh lệch có thể là:

- Tài sản đang hoạt động nhưng chưa được đưa vào inventory.
- Tài sản đã ngừng hoạt động nhưng dấu vết DNS/chứng thư vẫn còn.
- Tài sản thuộc nhà cung cấp hoặc đối tác, chưa được gắn đúng chủ sở hữu.
- Kết quả cũ, sai hoặc không thuộc phạm vi.

Mỗi nhóm dẫn tới hành động khác nhau. Không nên gọi mọi tên “lạ” là shadow IT khi chưa kiểm chứng.

### 8.2. Phân đoạn mạng và trust zone

Nếu dữ liệu công khai gợi ý có trang quản trị, điểm VPN hoặc cơ sở dữ liệu từng được đặt tên trên Internet, đội mạng cần kiểm tra **đường truy cập thực tế**:

1. Tài nguyên được phép xuất hiện ở trust zone nào?
2. Có luồng trực tiếp Internet → management/data zone không?
3. Truy cập quản trị có đi qua kênh kiểm soát, xác thực mạnh và được ghi log không?
4. Firewall, security group hoặc host firewall có quy tắc quá rộng không?

Passive reconnaissance chỉ phát hiện **điều đáng hỏi**; việc xác thực rule và tuyến kết nối cần dùng dữ liệu cấu hình nội bộ hoặc kiểm thử được phép.

### 8.3. DNS, chứng thư và miền con

Kết quả CT và passive DNS có thể hỗ trợ kiểm kê chứng thư, thu hồi tên không dùng, bảo vệ quản lý vùng DNS, rà soát bản ghi trỏ tới dịch vụ ngừng hoạt động và kiểm tra cấu hình email. Cần chú ý khả năng **subdomain takeover** khi tên DNS vẫn trỏ tới tài nguyên do bên thứ ba quản lý nhưng tổ chức không còn sở hữu tài nguyên đó. Kết quả passive chỉ là tín hiệu để chủ sở hữu kiểm tra cấu hình và khắc phục, không xác nhận đã có takeover.

### 8.4. Hạ tầng đám mây

Đối chiếu tài sản ứng viên với cloud inventory, tài khoản/subscription/project, DNS zone, load balancer, gateway và hệ thống quản lý bí mật. Một IP thuộc cloud provider có thể phục vụ nhiều khách hàng; do đó nên ưu tiên ánh xạ theo **tài khoản và định danh tài nguyên được tổ chức xác nhận** thay vì suy từ IP đơn lẻ.

### 8.5. Mô hình hóa mối đe dọa

Sử dụng những phát hiện có độ tin cậy cao để bổ sung câu hỏi vào threat model:

| Dấu hiệu thụ động | Giả thuyết rủi ro cần kiểm chứng | Biện pháp có thể được rà soát |
| --- | --- | --- |
| Hostname gợi ý VPN | Lộ bề mặt truy cập từ xa | MFA, điều kiện thiết bị, phân quyền theo ứng dụng, log |
| Hostname gợi ý trang quản trị | Giao diện đặc quyền có thể bị công bố sai | Phân đoạn, bastion/ZTNA, IAM, giới hạn nguồn |
| Bản ghi DNS cũ trỏ tới cloud | Có tài nguyên bỏ quên hoặc DNS không được quản lý | Vòng đời DNS/tài nguyên, ownership, kiểm tra cấu hình |
| Danh sách hostname từ CT vượt inventory | Chứng thư hoặc môi trường chưa được kiểm kê | Certificate inventory, quy trình phát hành và dọn dẹp |
| Tài liệu công khai nói về môi trường nội bộ | Thông tin kiến trúc có thể bị tiết lộ quá mức | Kiểm soát tài liệu, đánh giá dữ liệu được phép công bố |

Phân tích này giúp ưu tiên rà soát, nhưng không thay thế đánh giá khả năng khai thác, mức độ nhạy cảm của dữ liệu hoặc tính khả thi của đường tấn công.

## 9. Giám sát, IDS/IPS và giới hạn phát hiện

Vì trinh sát thụ động thường chỉ truy vấn dữ liệu ở **dịch vụ bên thứ ba**, firewall và IDS/IPS đặt ở mạng mục tiêu có thể **không thấy lưu lượng từ người thực hiện**. Không nên đánh giá năng lực phát hiện xâm nhập bằng cách kỳ vọng IDS sẽ cảnh báo mọi lượt xem CT log hoặc kết quả tìm kiếm.

Thay vào đó, đội phòng vệ có thể:

- Rà soát định kỳ các tên mới trong CT log và danh sách chứng thư được cấp cho các miền do mình sở hữu.
- Theo dõi sự thay đổi trong inventory, DNS, cấu hình cloud và các tài sản có công bố Internet.
- Phát hiện hoạt động **active reconnaissance** nhắm trực tiếp vào hệ thống qua firewall, WAF, IDS/IPS, NetFlow và log ứng dụng khi phù hợp.
- Giám sát hoạt động quản trị DNS, cấp chứng thư, thay đổi tài nguyên cloud và sự kiện xác thực liên quan.
- Phát hiện tài liệu hoặc bí mật vô tình được công khai qua quy trình quản lý mã nguồn và thông tin.

Mọi cảnh báo phải được đối chiếu bối cảnh: một chứng thư mới có thể là triển khai hợp lệ, một bản ghi DNS cũ có thể đã được thu hồi, và kết quả Internet indexing có thể chậm hàng tuần hoặc lâu hơn so với hiện trạng.

## 10. Nguyên tắc quản lý phạm vi và dữ liệu

Passive reconnaissance thường ít gây tác động kỹ thuật trực tiếp lên mục tiêu hơn quét chủ động, nhưng vẫn phải quản trị quá trình thu thập:

1. **Xác định quyền và mục tiêu.** Chỉ phân tích tài sản, đơn vị hoặc phạm vi có lý do công việc phù hợp; tuân thủ điều khoản sử dụng dữ liệu của từng nguồn.
2. **Giới hạn dữ liệu cá nhân.** Không mở rộng thu thập hồ sơ cá nhân ngoài mục tiêu bảo mật; không công khai thông tin liên hệ hoặc dữ liệu nhạy cảm không cần thiết.
3. **Không thử sử dụng bí mật phát hiện được.** Nếu nguồn công khai chứa khóa/tài khoản, chuyển cho bộ phận có thẩm quyền theo kênh bảo mật.
4. **Giữ nguồn và thời gian.** Phân biệt ngày thu thập, ngày quan sát và thời điểm hiệu lực của thông tin.
5. **Không tự chuyển sang kiểm thử chủ động.** Kết quả từ bên thứ ba là cơ sở lập kế hoạch; truy cập trực tiếp dịch vụ hoặc kiểm chứng cấu hình từ bên ngoài cần phạm vi được duyệt.
6. **Có vòng đời dữ liệu.** Quy định ai được xem báo cáo, dữ liệu được lưu bao lâu và khi nào xóa thông tin không còn cần thiết.

Trong điều tra nội bộ, ưu tiên gửi chủ sở hữu câu hỏi cụ thể như “Tên này còn thuộc inventory không?” hoặc “Chính sách MFA đã áp dụng cho điểm truy cập này chưa?” thay vì chuyển một giả thuyết chưa kiểm chứng thành cáo buộc.

## 11. Các sai lầm phổ biến

| Sai lầm | Vì sao không chính xác | Cách làm tốt hơn |
| --- | --- | --- |
| Có bản ghi CT nghĩa là server đang chạy | CT chứng minh dữ liệu chứng thư từng được ghi nhận | Đánh dấu ứng viên và đối chiếu inventory/hiện trạng |
| IP thuộc ASN của nhà cung cấp cloud nghĩa là IP thuộc tổ chức | Nhà cung cấp có thể vận hành tài nguyên của nhiều khách hàng | Xác minh bằng cloud account và định danh tài nguyên |
| Thấy URL trên kết quả tìm kiếm tức là URL còn công khai | Chỉ mục có thể đã cũ hoặc được lưu ở bộ nhớ đệm | Ghi thời gian và phân biệt kết quả tìm kiếm với trạng thái hiện tại |
| Không có kết quả passive DNS tức là hostname không tồn tại | Nguồn có phạm vi quan sát hạn chế | Dùng nhiều nguồn và ghi nhận độ bao phủ |
| Một trang indexing ghi “dịch vụ có cổng mở” nghĩa là hiện tại còn mở | Thông tin là ảnh chụp lịch sử | Kiểm tra thời gian; xác minh trong phạm vi được phép |
| Passive reconnaissance hoàn toàn không thể bị phát hiện | Bên cung cấp dữ liệu vẫn có thể ghi nhận truy vấn | Chỉ tuyên bố “không chủ động thăm dò hệ thống đích” |
| Mọi hostname có từ “admin” đều là trang quản trị | Tên chỉ là gợi ý, có thể là nhãn cũ hoặc hệ thống khác | Xác nhận chức năng, sở hữu và chính sách truy cập |
| Dùng luôn kết quả OSINT để kết luận lỗ hổng | Thiếu kiểm chứng về cấu hình, phiên bản và tác động | Tách rõ phát hiện, giả thuyết và kết quả kiểm thử |

## 12. Bài tập vận dụng

### Bài tập 1: Phân loại thao tác

Cho các hành động sau, xác định hành động nào là passive reconnaissance **đối với hệ thống đích** và nêu lý do:

1. Xem bản ghi CT đã được một dịch vụ bên thứ ba lập chỉ mục.
2. Gửi HTTP GET trực tiếp tới đường dẫn đăng nhập của mục tiêu.
3. Đọc dữ liệu passive DNS đã được lưu sẵn.
4. Tự dùng công cụ quét cổng để xác định cổng SSH đang mở.
5. Đọc thông tin ASN từ hồ sơ đăng ký công khai.

**Gợi ý:** (1), (3), (5) không yêu cầu trực tiếp thăm dò dịch vụ của mục tiêu; (2), (4) tạo lưu lượng chủ động. Việc tra cứu ở nguồn thứ ba vẫn tạo yêu cầu tới nhà cung cấp.

### Bài tập 2: Viết kết luận có bằng chứng

Một CT log đã ghi nhận tên **admin.example.com** từ hai năm trước. Một bộ dữ liệu passive DNS có liên hệ tên này với IP thuộc CDN ở cùng thời kỳ. Hãy viết hai câu: câu thứ nhất mô tả bằng chứng; câu thứ hai nêu việc cần xác minh.

**Gợi ý:** “Có dấu vết lịch sử của tên admin.example.com trong CT và passive DNS, chưa xác nhận còn hoạt động.” “Đề nghị chủ sở hữu kiểm tra inventory, DNS hiện tại và chính sách bảo vệ giao diện quản trị nếu tài sản vẫn được sử dụng.”

### Bài tập 3: Lập kế hoạch bảo vệ

Bạn là người phụ trách bảo mật mạng, phát hiện ba hostname ứng viên: một tên gợi ý VPN, một tên gợi ý API nghiệp vụ và một tên gợi ý môi trường thử nghiệm đã cũ. Hãy ghi **mỗi tên một câu hỏi xác minh, một loại kiểm soát cần rà soát và một nguồn nội bộ có thể xác nhận**.

**Gợi ý:** VPN → rà soát IAM/MFA và inventory truy cập từ xa; API → rà soát authentication/authorization cùng API inventory; môi trường cũ → rà soát DNS/cloud inventory và lịch sử thu hồi.

### Bài tập 4: Thiết kế báo cáo

Với một bằng chứng từ nguồn công khai, hãy điền mẫu: **mã phát hiện, phạm vi, loại nguồn, dữ liệu quan sát, thời gian ghi nhận, thời gian thu thập, độ tin cậy, giới hạn, tài sản ứng viên, chủ sở hữu cần xác nhận và hành động đề xuất**. Bài đạt yêu cầu khi người đọc nhận ra rõ nội dung nào đã quan sát được và nội dung nào chưa kiểm chứng.

## 13. Ghi nhớ

- **Passive reconnaissance thu thập dữ liệu mà không chủ động thăm dò hệ thống đích**; việc truy cập nguồn bên thứ ba vẫn có thể được ghi nhận.
- **OSINT là nguồn dữ liệu và phương pháp khai thác thông tin; tính thụ động phụ thuộc vào thao tác thực tế.**
- **Một dấu vết lịch sử không phải trạng thái hiện tại.** Đặc biệt thận trọng với chứng thư cũ, DNS cũ, IP cloud/CDN và chỉ mục dịch vụ.
- **Kết quả tốt nhất là giả thuyết có nguồn, thời gian và độ tin cậy**, kèm người phụ trách và bước xác minh.
- **Giá trị phòng vệ đến từ hành động tiếp theo:** hoàn thiện inventory, kiểm tra DNS/chứng thư, phân đoạn mạng, bảo vệ điểm VPN/quản trị, rà soát IAM/cloud và phát hiện thay đổi bề mặt tấn công.

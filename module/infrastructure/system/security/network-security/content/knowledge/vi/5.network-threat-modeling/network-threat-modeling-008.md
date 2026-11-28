# Information disclosure trong threat modeling mạng

**Information disclosure** (lộ lọt thông tin) là tình huống dữ liệu được tiết lộ cho chủ thể không có quyền biết. Trong **STRIDE**, đây là nhóm đe dọa chữ **I**, chủ yếu tác động tới thuộc tính **Confidentiality (tính bí mật)** của bộ ba CIA (Confidentiality – Integrity – Availability). Đối với hệ thống mạng, thông tin có thể bị lộ ngay trên đường truyền, tại thiết bị trung gian, trong log giám sát, qua giao thức quản trị, từ cấu hình đám mây hoặc thông qua metadata tưởng như vô hại.

Bài học thuộc chương **Threat modeling mạng**, trong phạm vi **SECURITY_NETWORK_SECURITY**: phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, DNS, mạng không dây và hạ tầng đám mây. Mục tiêu là nhận diện đường rò rỉ, phân tích luồng dữ liệu và ranh giới tin cậy, ưu tiên biện pháp bảo vệ và xác minh hiệu quả của kiến trúc mạng an toàn.

## 1. Mục tiêu học tập

Hoàn thành bài này, người học có thể:

1. Giải thích Information disclosure và phân biệt nó với các nhóm đe dọa STRIDE khác.
2. Xác định tài sản cần bảo vệ, đối tượng có thể quan sát dữ liệu, đường truyền và **trust boundary** (ranh giới tin cậy).
3. Mô hình hóa nguy cơ lộ **nội dung**, **bí mật xác thực**, **thông tin vận hành** và **metadata** qua các thành phần mạng.
4. Lập một threat record mô tả điều kiện, hậu quả, biện pháp giảm thiểu, cách kiểm chứng và rủi ro còn lại.
5. Áp dụng phòng vệ nhiều lớp với mã hóa, xác thực, phân đoạn, chính sách egress, bảo vệ log và giám sát hợp lệ.

## 2. Bản chất của Information disclosure

Thông tin được coi là bị lộ khi một đối tượng không có quyền truy cập vẫn có thể **đọc, suy ra hoặc thu thập** thông tin cần được giữ kín. Đối tượng đó có thể là người nghe lén trên mạng công cộng, tài khoản nội bộ vượt phạm vi được cấp, thiết bị mạng bị chiếm quyền, nhà cung cấp dịch vụ không nằm trong phạm vi được phép, hoặc một ứng dụng khác trong cùng hạ tầng.

### 2.1. Những dạng thông tin dễ bị lộ

| Nhóm tài sản | Ví dụ | Hậu quả nếu lộ |
| --- | --- | --- |
| Dữ liệu cá nhân và nghiệp vụ | Thông tin khách hàng, số đơn hàng, hồ sơ nội bộ, báo cáo | Vi phạm quyền riêng tư, mất uy tín, thiệt hại tài chính |
| Thông tin xác thực | Mật khẩu, API key, OAuth token, session cookie, khóa riêng | Chiếm tài khoản, truy cập dịch vụ trái phép, mở rộng phạm vi sự cố |
| Bí mật hạ tầng | Cấu hình VPN, private key TLS, thông tin quản trị, kết nối cơ sở dữ liệu | Giả mạo danh tính, tấn công hệ thống nội bộ |
| Dữ liệu ứng dụng | Request/response body, file đính kèm, bản sao lưu | Lộ nội dung dù ứng dụng có phân quyền trên giao diện |
| Thông tin cấu trúc mạng | Hostname nội bộ, IP riêng, phiên bản phần mềm, topology, quy tắc firewall | Hỗ trợ trinh sát và lựa chọn mục tiêu |
| Metadata | Địa chỉ IP, thời điểm, tần suất, kích thước gói, tên miền truy vấn | Suy đoán hành vi người dùng, quan hệ giữa dịch vụ hoặc sự kiện nhạy cảm |

Không phải mọi dữ liệu kỹ thuật đều là bí mật. **Mức độ nhạy cảm phụ thuộc ngữ cảnh**: hostname công khai có thể vô hại, nhưng hostname mô tả hệ thống quản trị tài chính nội bộ có thể làm lộ cấu trúc và mục đích sử dụng. Khi threat modeling, cần ghi rõ *ai được phép xem* từng loại dữ liệu.

### 2.2. So sánh với STRIDE

| Nhóm STRIDE | Câu hỏi điển hình | Phân biệt với Information disclosure |
| --- | --- | --- |
| Spoofing | Ai có thể giả danh máy chủ hoặc người dùng? | Giả danh có thể dẫn tới rò rỉ, nhưng trọng tâm là danh tính |
| Tampering | Ai có thể sửa thông điệp? | Trọng tâm là tính toàn vẹn, dù cũng có thể phối hợp với lộ dữ liệu |
| Repudiation | Ai có thể phủ nhận một thao tác? | Trọng tâm là chứng cứ và khả năng quy trách nhiệm |
| **Information disclosure** | **Ai có thể biết dữ liệu mà họ không được phép biết?** | **Trọng tâm là tính bí mật** |
| Denial of service | Ai có thể làm dịch vụ không khả dụng? | Trọng tâm là tính sẵn sàng |
| Elevation of privilege | Ai có thể nhận quyền cao hơn quyền được cấp? | Leo thang đặc quyền có thể tạo điều kiện để đọc dữ liệu |

Một kịch bản có thể thuộc **nhiều** nhóm. Ví dụ, kẻ tấn công giả mạo một máy chủ nội bộ (**Spoofing**) để client gửi token tới nó (**Information disclosure**). Trong threat record, có thể ghi nhiều nhãn, nhưng vẫn phải mô tả cụ thể **thông tin gì bị lộ**.

## 3. Tư duy theo dữ liệu, luồng và ranh giới tin cậy

Không bắt đầu bằng câu hỏi chung chung “hệ thống có mã hóa chưa?”. Hãy lần theo **vòng đời dữ liệu** và các thực thể có thể tiếp cận dữ liệu ở mỗi bước:

1. **Tạo và thu thập:** người dùng nhập thông tin, thiết bị phát sinh telemetry, ứng dụng tạo token.
2. **Truyền:** dữ liệu đi qua Wi-Fi, router, VPN, firewall, load balancer, proxy và các mạng của nhà cung cấp.
3. **Xử lý:** dịch vụ giải mã, xác thực, phân quyền, định tuyến hoặc chuyển tiếp.
4. **Lưu trữ:** database, object storage, cache, snapshot, backup, hàng đợi và hệ thống phân tích.
5. **Ghi log, sao chép, chia sẻ, xóa:** truy cập từ SOC, hệ thống APM, dịch vụ hỗ trợ, đối tác hoặc công cụ debug.

Tại mỗi bước, đặt năm câu hỏi:

- **Tài sản:** Giá trị nào phải được giữ kín? Độ nhạy cảm và chủ sở hữu là ai?
- **Luồng:** Dữ liệu ở dạng rõ hay mã hóa? Ai có thể đọc nó tại nguồn, giữa đường và tại đích?
- **Ranh giới:** Dữ liệu có đi từ vùng tin cậy cao sang vùng kém tin cậy hoặc bên thứ ba không?
- **Điều kiện:** Cần đặc quyền, quyền truy cập mạng, cấu hình sai hay lỗi ứng dụng gì để dữ liệu lộ?
- **Kiểm soát:** Cơ chế nào ngăn, phát hiện và hạn chế thiệt hại? Kiểm chứng bằng cách nào?

### 3.1. Sơ đồ luồng dữ liệu (DFD) mẫu

Giả sử một cổng quản trị đơn hàng gồm trình duyệt nhân viên, edge, API, cơ sở dữ liệu và hệ thống giám sát:

~~~mermaid
flowchart LR
    U[Trình duyệt nhân viên] -->|HTTPS| E[Edge / WAF / Reverse proxy]
    E -->|TLS nội bộ| A[Order API]
    A -->|Kết nối DB được bảo vệ| DB[(Cơ sở dữ liệu)]
    A -->|Log / Trace đã lọc| L[(Hệ thống giám sát)]
    E -->|Access log đã lọc| L
    A -->|Tra cứu / Gọi dịch vụ| X[Dịch vụ phụ trợ]
    subgraph Public["Vùng thiết bị & Internet: tin cậy thấp"]
      U
    end
    subgraph DMZ["Vùng edge"]
      E
    end
    subgraph Internal["Vùng dịch vụ nội bộ"]
      A
      DB
      X
    end
    subgraph Operations["Vùng vận hành / SOC"]
      L
    end
~~~

Các vùng trong sơ đồ là **ranh giới logic để phân tích**, chưa khẳng định việc triển khai thực tế đã phân đoạn an toàn. Mỗi mũi tên là một luồng cần xác định dữ liệu, danh tính gửi/nhận, giao thức, thiết bị trung gian, nơi kết thúc mã hóa và bên được phép quan sát.

Ví dụ: HTTPS từ trình duyệt đến edge chỉ bảo vệ **chặng đó**. Nếu reverse proxy kết thúc TLS và gửi request chứa cookie qua HTTP đến API trên mạng dùng chung, có thêm bề mặt lộ dữ liệu. Nếu API ghi toàn bộ header Authorization vào log, rò rỉ xảy ra ở **điểm xử lý/ghi log** ngay cả khi hai chặng đều dùng TLS.

### 3.2. Lập bảng luồng dữ liệu

| ID | Nguồn → Đích | Dữ liệu | Ranh giới | Điểm cần kiểm tra |
| --- | --- | --- | --- | --- |
| F1 | Trình duyệt → Edge | Session cookie, yêu cầu API | Thiết bị người dùng → Internet/edge | TLS, hostname, chứng chỉ, HSTS, cookie Secure |
| F2 | Edge → API | Danh tính đã xác thực, payload yêu cầu | DMZ → mạng dịch vụ | TLS/mTLS nếu phù hợp, kiểm tra header chuyển tiếp, ACL |
| F3 | API → Database | Dữ liệu đơn hàng, câu truy vấn | Dịch vụ → vùng dữ liệu | Phân quyền tài khoản DB, bảo vệ kết nối, phân đoạn |
| F4 | API/Edge → Log | URL, mã lỗi, trace, thông tin người dùng | Sản xuất → vận hành | Redaction, quyền xem log, retention và export |
| F5 | API → Dịch vụ phụ trợ | ID khách hàng, token dịch vụ | Vùng ứng dụng → dịch vụ khác | Danh tính workload, allowlist egress, dữ liệu tối thiểu |

**Nguyên tắc quan trọng:** ranh giới tin cậy không tự động trùng với subnet. Một service account có quyền đọc log toàn hệ thống, một tài khoản quản trị cloud hoặc một agent quan sát trong container có thể vượt qua ranh giới logic dù không có đường kết nối trực tiếp giữa hai subnet.

## 4. Các bề mặt Information disclosure trong mạng

### 4.1. Nghe lén trên đường truyền và mã hóa từng chặng

Các nguy cơ điển hình:

- **HTTP, Telnet, FTP hoặc giao thức quản trị không mã hóa:** có thể để lộ thông tin trong dữ liệu truyền khi người khác có khả năng quan sát lưu lượng.
- **TLS cấu hình không an toàn:** cho phép phiên bản cũ, bỏ qua kiểm tra chứng chỉ, trust store bị thao túng hoặc sử dụng chứng chỉ không đúng tên đích.
- **TLS termination chưa được kiểm kê:** load balancer/WAF giải mã rồi gửi nội dung rõ qua một chặng khác.
- **TLS interception / SSL inspection:** một điểm trung gian có quyền giải mã để phục vụ chính sách bảo mật đồng thời trở thành nơi tập trung dữ liệu nhạy cảm cần bảo vệ và kiểm soát truy cập chặt.
- **Backend không kiểm tra định danh đối tác:** có mã hóa nhưng kết nối sai dịch vụ; mã hóa đường truyền không thay thế xác thực điểm cuối.

Giảm thiểu bằng **TLS 1.3** hoặc **TLS 1.2 cấu hình an toàn** theo yêu cầu tương thích, kiểm tra chứng chỉ/hostname đầy đủ, quản lý khóa riêng, chuyển giao thức quản trị sang SSH/SNMPv3 khi phù hợp, xác thực client bằng mTLS cho một số kết nối dịch vụ và mã hóa chặng sau reverse proxy nếu rủi ro yêu cầu.

Lưu ý: trong **HTTP/3**, QUIC dùng TLS 1.3 tích hợp; chính sách chỉ giám sát TCP/443 có thể không quan sát được các phiên chạy UDP/443.

### 4.2. DNS và metadata kết nối

Ngay cả khi nội dung ứng dụng đã được mã hóa, người quan sát vẫn có thể thấy hoặc suy ra:

- Địa chỉ IP nguồn/đích, thời điểm kết nối, lưu lượng và thời lượng phiên.
- Tên miền qua DNS không mã hóa; thông tin tên máy chủ trong một số cấu hình TLS.
- Mối quan hệ giữa máy chủ nội bộ và dịch vụ công cộng, lịch làm việc hoặc mức độ sử dụng hệ thống từ mẫu lưu lượng.

**DNS over HTTPS (DoH)** và **DNS over TLS (DoT)** có thể bảo vệ nội dung truy vấn DNS trên chặng đến resolver hỗ trợ, nhưng resolver vẫn nhìn thấy truy vấn, và địa chỉ IP đích cùng các metadata khác có thể còn lộ. **DNSSEC** giúp xác minh tính xác thực/toàn vẹn của câu trả lời DNS; nó **không mã hóa** truy vấn DNS. **Encrypted ClientHello (ECH)** có thể giảm lộ một số trường của TLS ClientHello khi được cả client và hạ tầng hỗ trợ, nhưng không tạo tính ẩn danh hoàn toàn.

Khi bảo vệ DNS, cần xác định **resolver tin cậy**, nơi ghi log truy vấn, chính sách retention, quyền xem dữ liệu và các đường đi DNS được ứng dụng dùng thực tế. Quy tắc egress DNS/DoH phải cân bằng quyền riêng tư với nhu cầu giám sát và quản trị mạng.

### 4.3. Mạng không dây, mạng khách và thiết bị đầu cuối

Wi-Fi mở hoặc giả mạo điểm truy cập có thể khiến lưu lượng dễ bị theo dõi và điều hướng. **WPA2-Enterprise/WPA3-Enterprise** với xác thực và cấu hình phù hợp giúp bảo vệ kết nối không dây và danh tính truy cập; **HTTPS/TLS** vẫn cần vì bảo vệ ở tầng Wi-Fi chỉ áp dụng trên một chặng liên kết. VPN có thể bổ sung một đường hầm bảo vệ tới điểm kết thúc VPN, nhưng dữ liệu phía sau điểm kết thúc vẫn phải được đánh giá độc lập.

Phân tách mạng nhân viên, khách và thiết bị IoT; kiểm soát truy cập vào dịch vụ nội bộ; sử dụng quản lý chứng chỉ/mật khẩu Wi-Fi phù hợp. Không mặc định rằng người dùng ở cùng mạng công ty đều được quyền đọc dữ liệu nhau.

### 4.4. Giao thức quản trị và thiết bị mạng

Router, switch, firewall, hypervisor và hệ thống giám sát có thể lộ:

- Mật khẩu hoặc khóa API trong file sao lưu cấu hình.
- Chuỗi cộng đồng SNMP v1/v2c; phiên quản trị Telnet/HTTP không mã hóa.
- Bảng định tuyến, ACL, thông tin interface, địa chỉ quản trị và danh sách tài khoản.
- Bản ghi sự cố chứa cấu hình, token, kết quả dump hoặc thông tin người dùng.

Biện pháp ưu tiên: **management plane tách biệt**, truy cập qua mạng quản trị/VPN được kiểm soát, SSH/HTTPS/SNMPv3, MFA cho bảng điều khiển phù hợp, cấp quyền tối thiểu và bảo vệ backup thiết bị. Chỉ cho phép hệ thống quản lý được phê duyệt truy cập cổng quản trị.

### 4.5. Phân đoạn mạng và chuyển động ngang

Trong mạng phẳng, một máy trạm hoặc workload bị xâm nhập có thể có tầm nhìn lớn hơn mức cần thiết đối với service discovery, share, lưu lượng nội bộ và giao thức quản trị. **Phân đoạn** (VLAN, subnet, firewall giữa các vùng, network policy và định danh workload) giới hạn số hệ thống mà mỗi điểm có thể tiếp cận.

Tuy nhiên, phân đoạn **không tự mã hóa** dữ liệu và không sửa lỗi phân quyền của API. Cần kết hợp phân đoạn với kiểm soát ứng dụng, xác thực kết nối và kiểm soát egress để giảm khả năng dữ liệu bị thu thập hoặc truyền ra ngoài sau khi một workload bị xâm nhập.

### 4.6. Log, IDS/IPS, APM và công cụ debug

Các thành phần giám sát cần đủ thông tin để phát hiện sự cố, nhưng việc ghi dữ liệu quá mức có thể tạo một kho dữ liệu nhạy cảm mới:

- HTTP access log lưu URL có token/query nhạy cảm.
- Reverse proxy/APM lưu header Authorization, Cookie, response body hoặc thông tin thanh toán.
- IDS/IPS hoặc packet capture lưu payload mạng trong một thời gian dài.
- Stack trace và thông báo lỗi lộ cấu hình, hostname, địa chỉ IP nội bộ, chuỗi kết nối hoặc thông tin người dùng.
- Dashboard hoặc công cụ tìm kiếm log bị cấp quyền quá rộng, chia sẻ nhầm ra ngoài.

**Giải pháp:** quy định loại trường được phép ghi, che/xóa token và dữ liệu cá nhân ngay khi thu thập, hạn chế packet capture, phân quyền truy cập, mã hóa lưu trữ, thiết lập retention, kiểm soát xuất dữ liệu và ghi audit cho việc đọc/tải log. Với hệ thống cần phục vụ điều tra, cân nhắc dữ liệu đã giảm nhạy cảm hoặc tập dữ liệu cách ly có quyền hạn chế.

### 4.7. Hạ tầng cloud, container và dịch vụ bên thứ ba

Trong cloud, Information disclosure có thể xuất hiện từ:

- Object storage hoặc snapshot bị công khai nhầm, danh sách kiểm soát truy cập sai, chia sẻ tài khoản quá rộng.
- Secret lưu trong environment variable, container image, file cấu hình hoặc pipeline log, sau đó vô tình bị đọc bởi người hoặc dịch vụ không có quyền.
- Metadata/identity của workload bị truy cập trái phép do cấu hình network và ranh giới ứng dụng không chặt.
- Security group, route, peering hoặc network policy mở kết nối tới vùng dữ liệu không cần thiết.
- Truyền dữ liệu sang dịch vụ SaaS, webhook hoặc hệ thống phân tích mà không kiểm tra phạm vi truy cập và retention.

Cloud security là **trách nhiệm chia sẻ**: nhà cung cấp bảo vệ một phần hạ tầng nền tảng, trong khi người sử dụng vẫn phải cấu hình danh tính, network policy, mã hóa, quyền truy cập, log và dữ liệu. Không coi “nằm trong private subnet” hoặc “dùng dịch vụ managed” là đủ để dữ liệu được bảo mật.

## 5. Mô hình hóa kịch bản lộ thông tin theo STRIDE

### 5.1. Công thức mô tả một đe dọa

Một threat record hữu ích thường có dạng:

> **Tại [thành phần/luồng], [tác nhân] với [điều kiện] có thể [hành vi/quan sát] khiến [tài sản] bị lộ cho [đối tượng không được phép], dẫn tới [hậu quả].**

Ví dụ:

> Tại luồng API → hệ thống log, tài khoản phân tích chỉ được quyền theo dõi hiệu năng nhưng có quyền đọc toàn bộ log có thể xem token trong header Authorization, từ đó sử dụng trái phép các phiên xác thực còn hiệu lực.

Ghi rõ nguyên nhân, nguồn dữ liệu, ranh giới, phạm vi ảnh hưởng và điều kiện tiên quyết giúp chuyển một nhận xét chung thành công việc có thể giao người phụ trách và kiểm chứng.

### 5.2. Sơ đồ cây đe dọa

~~~mermaid
flowchart TD
    I["Information disclosure: dữ liệu đơn hàng bị đọc trái phép"]
    I --> A["Dữ liệu lộ trên đường truyền"]
    I --> B["Dữ liệu lộ tại điểm xử lý"]
    I --> C["Dữ liệu lộ trong bản sao"]
    A --> A1["Chặng proxy–API không được bảo vệ"]
    A --> A2["Client không xác minh máy chủ"]
    B --> B1["API thiếu phân quyền đối tượng"]
    B --> B2["Proxy debug ghi header bí mật"]
    C --> C1["Log/trace chứa dữ liệu cá nhân"]
    C --> C2["Backup hoặc storage cấp quyền quá rộng"]
~~~

Sơ đồ trên giúp đặt câu hỏi tại từng nhánh: có thể xảy ra không, bằng chứng nào chứng minh điều kiện đó tồn tại, kiểm soát nào đang vận hành và ai chịu trách nhiệm. Các nhánh không phải chuỗi bước khai thác, cũng không có nghĩa mọi hệ thống đều tồn tại các lỗi đó.

### 5.3. Mẫu threat record

| Trường | Nội dung cần ghi |
| --- | --- |
| ID / STRIDE | Mã nhận diện duy nhất; nhãn **I – Information disclosure** |
| Tài sản / độ nhạy cảm | Dữ liệu cụ thể, chủ sở hữu, mức phân loại |
| Thành phần / flow | DFD node hoặc flow ID, giao thức, nơi kết thúc mã hóa |
| Tác nhân / điều kiện | Ai có thể quan sát? Quyền, vị trí và tiền đề cần có? |
| Kịch bản | Cơ chế lộ và đối tượng nhận thông tin |
| Tác động | Số người/tài sản có thể ảnh hưởng; tác động vận hành, tài chính, riêng tư |
| Kiểm soát hiện có | Mã hóa, identity, ACL, redaction, phân đoạn, monitoring |
| Biện pháp bổ sung | Thay đổi cụ thể và người phụ trách |
| Kiểm chứng | Bằng chứng cấu hình, test, truy vấn log, kết quả kiểm thử |
| Rủi ro còn lại | Phạm vi chưa khắc phục, giả định và người chấp thuận |

Ví dụ threat record cho **F4 (API/Edge → Log)**:

| Trường | Giá trị minh họa |
| --- | --- |
| Mã | NTM-I-008 |
| Tài sản | Token truy cập, session ID, dữ liệu cá nhân trong response |
| Ranh giới | Ứng dụng sản xuất → nền tảng logging/SOC |
| Điều kiện | Middleware ghi request header hoặc payload toàn bộ; người dùng logging có quyền đọc |
| Kịch bản | Bản sao token trong log được truy cập bởi người không có quyền với phiên gốc |
| Hậu quả | Lộ bí mật xác thực, tăng nguy cơ truy cập trái phép và mở rộng sự cố |
| Kiểm soát hiện có | Truyền log qua TLS, phân quyền dashboard theo nhóm |
| Việc cần làm | Chặn ghi Authorization/Cookie, giảm nội dung payload, rà quyền export, rút ngắn retention |
| Kiểm chứng | Request thử với **token giả**, tìm kiếm log/trace cho mẫu token; rà danh sách quyền đọc và tải dữ liệu |
| Rủi ro còn lại | Các bản log lịch sử có thể còn dữ liệu; cần kế hoạch xử lý theo khả năng và chính sách lưu giữ |

Điểm đáng chú ý: **TLS cho luồng gửi log không giải quyết việc nội dung log đã chứa bí mật**. Kiểm soát đúng là loại bỏ dữ liệu không cần lưu và quản lý quyền ở nơi ghi, lưu và truy vấn.

## 6. Đánh giá và ưu tiên rủi ro

Không phải mọi rò rỉ đều có cùng mức nghiêm trọng. Khi đánh giá, cần xác định:

- **Mức nhạy cảm:** khóa riêng và access token có tác động khác với thống kê tổng hợp đã được ẩn danh phù hợp.
- **Phạm vi lộ:** một tài khoản, một máy, toàn hệ thống, nhiều tổ chức hoặc nhiều năm dữ liệu.
- **Khả năng xảy ra:** điều kiện khai thác có sẵn hay phải có quyền/điểm đứng mạng đặc biệt? Dịch vụ có lộ ra Internet không?
- **Khả năng tồn tại và phát hiện:** rò rỉ chỉ trong thời gian ngắn hay lưu vĩnh viễn ở backup/log? Có giám sát truy cập và xuất dữ liệu không?
- **Kiểm soát thực tế:** biện pháp có được triển khai, kiểm thử và duy trì hay mới chỉ ghi trong tài liệu?

Có thể dùng ma trận đơn giản để **xếp thứ tự xử lý nội bộ**, không coi là xác suất thống kê chính xác:

| Điểm | Khả năng xảy ra (L) | Tác động (I) |
| --- | --- | --- |
| 1 | Hiếm, cần nhiều điều kiện đặc biệt | Tác động thấp, phạm vi rất hạn chế |
| 2 | Ít khả năng | Tác động nhỏ, dễ khoanh vùng |
| 3 | Có thể xảy ra | Ảnh hưởng nhiều dữ liệu hoặc một nhóm người dùng |
| 4 | Khả năng cao | Lộ dữ liệu quan trọng, ảnh hưởng nhiều chức năng |
| 5 | Rất dễ xảy ra hoặc đang quan sát thấy điều kiện | Lộ bí mật nghiêm trọng, ảnh hưởng diện rộng |

**Điểm ưu tiên minh họa = L × I** (1–25); tổ chức cần định nghĩa lại ngưỡng cho bối cảnh và yêu cầu pháp lý của mình. Ví dụ giả định:

| Rủi ro | L | I | Điểm | Hướng xử lý |
| --- | ---: | ---: | ---: | --- |
| API ghi token vào log mà nhiều nhóm có quyền đọc | 4 | 5 | 20 | Ưu tiên loại token khỏi log, thu hẹp quyền và xử lý dữ liệu lịch sử |
| Chặng nội bộ truyền dữ liệu đơn hàng rõ trên segment dùng chung | 3 | 4 | 12 | Đánh giá TLS/mTLS, phân đoạn và quyền quan sát trên segment |
| Metadata lưu lượng chỉ lộ trong phạm vi hạ tầng đã kiểm soát | 2 | 2 | 4 | Xem lại nhu cầu riêng tư và duy trì giám sát |

Các điểm là **giả định phục vụ bài tập**, không phải kết luận về một hệ thống thật. Rủi ro tác động rất cao hoặc liên quan bí mật xác thực có thể cần xử lý gấp dù giá trị L × I không đứng đầu; người phụ trách cần ghi quyết định và căn cứ.

## 7. Lựa chọn biện pháp phòng vệ theo đường rò rỉ

| Bề mặt rủi ro | Ngăn ngừa | Phát hiện / kiểm chứng |
| --- | --- | --- |
| Lộ payload khi truyền | TLS end-to-end theo các chặng thực tế, xác thực hostname, mTLS khi phù hợp, VPN cho luồng cần đường hầm | Kiểm tra cấu hình TLS, chứng chỉ và luồng bằng packet capture được phép |
| Lộ thông tin ở Wi-Fi và truy cập khách | WPA-Enterprise phù hợp, cô lập mạng khách/IoT, HTTPS và kiểm soát truy cập mạng | Kiểm tra VLAN, ACL, chính sách Wi-Fi và lưu lượng ngang |
| Lộ bí mật từ quản trị thiết bị | SSH/HTTPS, SNMPv3, MFA, management plane riêng, secret vault | Audit cấu hình, quyền truy cập và backup |
| Lộ hostname/truy vấn DNS | Resolver được quản lý, DoT/DoH khi phù hợp, giảm retention DNS, hạn chế chia sẻ dữ liệu | Xác minh đường đi DNS và quyền xem log của resolver |
| Truy cập ngang trái phép | Phân đoạn, chính sách east–west, network ACL, định danh workload và phân quyền ứng dụng | Kiểm thử từ phân vùng không được phép và rà firewall rule |
| Lộ qua proxy, APM và log | Giảm dữ liệu thu thập, redaction, RBAC, retention, mã hóa lưu trữ | Kiểm thử token giả, rà quyền truy vấn/xuất log |
| Lộ qua cloud storage, backup | Private-by-default, IAM ít quyền, mã hóa, khóa quản lý đúng, giới hạn chia sẻ | Kiểm tra cấu hình, access review, cảnh báo truy cập công khai |
| Truyền dữ liệu không cần thiết ra Internet | Egress allowlist theo nhu cầu, danh tính dịch vụ, kiểm soát upload/đối tác | Flow log, anomaly detection, giám sát xuất dữ liệu theo chính sách |

### 7.1. Vai trò của firewall, IDS/IPS và giám sát

**Firewall** chủ yếu giới hạn đường mạng có thể kết nối; **IDS/IPS** có thể phát hiện hoặc chặn một số dấu hiệu bất thường trên lưu lượng mà nó quan sát được; **WAF** bảo vệ một số lớp giao tiếp HTTP theo vị trí triển khai. Những công cụ này **không thay thế xác thực/phân quyền tại API** hoặc chính sách quyền với dữ liệu.

Khi lưu lượng được mã hóa, điểm quan sát ở giữa mạng thường chỉ thấy metadata (trừ khi có cơ chế giải mã hợp lệ). Bổ sung telemetry tại ứng dụng, reverse proxy, DNS resolver, identity provider hoặc hệ thống lưu trữ sẽ giúp phát hiện rủi ro mà network sensor không thấy. Việc thu thập telemetry phải tuân thủ mục tiêu **thu đủ để bảo vệ nhưng không lưu bí mật quá mức**.

### 7.2. Data minimization và giảm thời gian tồn tại của bí mật

Một nguyên tắc hiệu quả là **không chuyển, sao chép hoặc ghi dữ liệu nhạy cảm nếu không thật sự cần**. Chẳng hạn, thay vì chuyển toàn bộ hồ sơ khách hàng sang dịch vụ phân tích lưu lượng, chỉ gửi ID giả danh hoặc chỉ số tổng hợp đáp ứng mục tiêu. Khi bắt buộc dùng token, hãy quản lý thời hạn, phạm vi quyền, cơ chế xoay và thu hồi.

Ẩn dữ liệu bằng cách băm (hash) **không mặc nhiên** bảo đảm ẩn danh nếu giá trị gốc dễ đoán, có thể liên kết lại hoặc bị khôi phục qua từ điển. Với dữ liệu cá nhân, đánh giá khả năng liên kết danh tính ngay cả khi đã xóa tên trực tiếp.

## 8. Quy trình threat modeling Information disclosure

Một quy trình áp dụng được trong buổi review kiến trúc:

1. **Định phạm vi:** dịch vụ, môi trường (on-premises, hybrid, cloud), dữ liệu nhạy cảm, người dùng và bên thứ ba.
2. **Vẽ DFD:** liệt kê thành phần, data store, bên ngoài, luồng có hướng và trust boundary. Đánh dấu rõ **TLS termination** và nơi dữ liệu ở dạng rõ.
3. **Gắn nhãn dữ liệu:** nội dung nào là bí mật? Có mật khẩu, token, PII, khóa riêng, metadata nhạy cảm trong luồng hoặc bản sao không?
4. **Liệt kê tình huống:** thử suy nghĩ như người quan sát ở Wi-Fi, người đọc log, tài khoản vận hành, service bị xâm nhập và đối tác được cấp quyền hạn chế.
5. **Ghi threat record:** mô tả điều kiện, cơ chế lộ, tác động, kiểm soát và cách xác minh. Liên kết từng threat với node/flow của DFD.
6. **Ưu tiên và giao việc:** dựa trên tác động, tính khả thi và thời gian tồn tại của dữ liệu; chỉ định owner, hạn xử lý và tiêu chí đạt.
7. **Kiểm chứng:** thử nghiệm có kiểm soát, rà cấu hình và log, ghi bằng chứng đối chiếu; tính lại rủi ro còn lại.
8. **Cập nhật khi thay đổi:** thêm API, thay CDN/WAF, đưa workload sang cloud, bật HTTP/3, thay DNS resolver hoặc mở quyền giám sát đều có thể làm đổi đường lộ dữ liệu.

Kết quả tối thiểu của buổi threat modeling nên gồm **sơ đồ DFD có ranh giới**, **danh sách tài sản**, **các threat record có mức ưu tiên**, **kế hoạch giảm thiểu** và **bằng chứng kiểm chứng**.

### 8.1. Checklist rà soát

- [ ] Đã xác định tất cả luồng chứa dữ liệu nhạy cảm và bên nào có quyền đọc.
- [ ] Đã ghi nơi TLS/VPN kết thúc và độ tin cậy của từng chặng tiếp theo.
- [ ] Đã kiểm tra xác thực, phân quyền, quản lý khóa và thời hạn token.
- [ ] Đã xét DNS, Wi-Fi, HTTP/3/QUIC và rủi ro metadata.
- [ ] Đã đánh giá quản trị thiết bị, đường truy cập nội bộ, firewall và phân đoạn.
- [ ] Đã kiểm tra log, trace, packet capture, backup và quyền export.
- [ ] Đã xét cloud storage, IAM, bí mật workload và chia sẻ với bên thứ ba.
- [ ] Đã xác định người phụ trách, phép thử, bằng chứng và rủi ro còn lại.

## 9. Thực hành có kiểm soát

Chỉ thực hiện trên **hệ thống thử nghiệm của bạn hoặc môi trường được cho phép**; dùng dữ liệu và token giả. Các bài sau ưu tiên kiểm chứng cấu hình và bằng chứng, không yêu cầu lấy dữ liệu của người khác.

### Bài A — So sánh thông tin quan sát được từ HTTP và HTTPS

Tạo hoặc sử dụng một dịch vụ thử nghiệm trong lab. Phát request chỉ chứa chuỗi giả, ví dụ demo_order=123, qua HTTP trong mạng lab và qua HTTPS có xác minh chứng chỉ. Quan sát bằng công cụ bắt gói hợp lệ như Wireshark:

~~~text
http
tls
tcp.port == 80
tcp.port == 443
udp.port == 443
quic
~~~

Trả lời:

- Trong kịch bản HTTP, thành phần nào của request có thể xuất hiện dạng rõ trong packet capture?
- Trong kịch bản HTTPS, bạn vẫn nhìn thấy metadata nào? Có thể đọc trực tiếp path, cookie và body từ điểm quan sát mạng không?
- Nếu client và server dùng HTTP/3, bộ lọc chỉ tcp.port == 443 có còn đủ không?
- Đã xác minh chứng chỉ chưa? Điều gì thay đổi nếu request đi qua một proxy kết thúc TLS?

Chú ý: Developer Tools ở trình duyệt có thể hiển thị nội dung **sau khi đã giải mã tại client**. Điều đó không chứng minh người quan sát ở giữa đường đọc được payload TLS.

### Bài B — Kiểm tra có lộ token giả trong log hay không

Trong môi trường lab, cấu hình một endpoint đơn giản nhận một header **giả** như Authorization: Bearer DEMO_TOKEN_DO_NOT_USE. Gửi một request hợp lệ, sau đó kiểm tra log của ứng dụng, reverse proxy và APM:

1. Token giả có xuất hiện nguyên văn ở bất kỳ nơi nào không?
2. Request body/response body có chứa trường cá nhân không cần ghi không?
3. Vai trò chỉ được đọc thống kê hiệu năng có tìm hoặc export được log chứa bí mật không?
4. Sau khi bật redaction, các giá trị nhạy cảm có biến mất khỏi **log mới** không? Log cũ cần phương án xử lý nào?

Ghi bằng chứng bằng chuỗi giả; không dán credential thật vào báo cáo, hệ thống ticket hay công cụ AI.

### Bài C — Review sơ đồ kiến trúc

Với sơ đồ ở mục 3, giả sử hệ thống có thêm: nhân viên truy cập qua Wi-Fi công ty; edge gửi dữ liệu sang dịch vụ phân tích bên thứ ba; SOC lưu log 90 ngày; một dịch vụ mới dùng object storage làm cache. Hãy đánh dấu:

- Ba trust boundary mới hoặc đã thay đổi.
- Ít nhất năm đường có thể lộ thông tin, nêu rõ **ai được phép** và **ai không được phép** nhận dữ liệu.
- Biện pháp giảm thiểu cho từng đường; phân biệt **mã hóa**, **phân quyền**, **giảm dữ liệu thu thập** và **giám sát**.
- Phép thử có thể lặp lại để chứng minh việc khắc phục.

## 10. Tình huống tổng hợp: cổng quản trị với nguy cơ rò rỉ

Một doanh nghiệp có cổng quản trị truy cập qua HTTPS. Kết nối đến reverse proxy hợp lệ và không có cảnh báo chứng chỉ. Tuy nhiên, API gửi toàn bộ request header sang hệ thống APM. Đồng thời, bản xuất log được một nhóm hỗ trợ bên ngoài truy cập để phân tích hiệu năng.

**Phân tích STRIDE:**

1. **Tài sản:** session token và dữ liệu nghiệp vụ gắn với session.
2. **Luồng:** trình duyệt → reverse proxy → API → APM → nhóm hỗ trợ.
3. **Ranh giới:** dữ liệu được phép dùng trong phiên ứng dụng đi sang nền tảng giám sát và bên ngoài phạm vi ban đầu.
4. **Đe dọa:** Information disclosure tại luồng API → APM và tại quyền đọc/xuất dữ liệu APM; đường HTTPS phía người dùng vẫn hoạt động đúng.
5. **Tác động:** bên nhận log có thể biết bí mật xác thực hoặc nội dung khách hàng mà họ không được phép biết.
6. **Giảm thiểu:** dừng ghi Authorization/Cookie, lọc trường dữ liệu, áp dụng quyền ít nhất cho APM, kiểm soát export và retention; xác định cách thu hồi token bị lộ và xử lý dữ liệu lịch sử nếu có.
7. **Xác minh:** token giả không xuất hiện trong log mới; tài khoản hỗ trợ không đọc được dữ liệu ngoài phạm vi; việc tải và truy vấn dữ liệu nhạy cảm được audit theo chính sách.

Bài học là: **HTTPS an toàn không đồng nghĩa toàn bộ chuỗi xử lý dữ liệu an toàn**. Threat modeling phải kiểm tra cả bản sao, đích phụ trợ, quyền của bên thứ ba và luồng dữ liệu bên ngoài giao dịch chính.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Một API dùng TLS 1.3 nhưng backend ghi access token vào log. Đây có phải Information disclosure không?

*Đáp án gợi ý:* Có thể, nếu log được lưu/đọc bởi người không được phép biết token; TLS bảo vệ đường truyền, không loại token khỏi log.

**Câu 2.** DNSSEC có giúp ẩn tên miền truy vấn khỏi người nghe lén không?

*Đáp án gợi ý:* Không. DNSSEC xác thực dữ liệu DNS; DoT/DoH mới bảo vệ nội dung truy vấn trên chặng đến resolver khi triển khai đúng.

**Câu 3.** Một firewall chặn mọi kết nối giữa hai VLAN có đủ ngăn việc lộ dữ liệu qua dịch vụ SaaS đã được cho phép không?

*Đáp án gợi ý:* Không. Phải đánh giá luồng egress, quyền của tài khoản dịch vụ, dữ liệu chuyển ra ngoài và chính sách của đối tác.

**Câu 4.** Vì sao việc phát hiện tên miền hoặc IP đích vẫn có ý nghĩa trong threat modeling dù HTTPS mã hóa nội dung?

*Đáp án gợi ý:* Metadata có thể tiết lộ mối liên hệ giữa dịch vụ, thói quen truy cập, thời điểm hoạt động và cấu trúc hạ tầng.

**Câu 5.** Khi reverse proxy kết thúc TLS, cần ghi thêm gì vào DFD?

*Đáp án gợi ý:* Điểm kết thúc TLS, luồng proxy → backend, trạng thái mã hóa và xác thực của chặng sau, ai có thể quan sát/ghi log payload tại proxy.

**Bài tập cuối bài.** Tự thiết kế một threat record Information disclosure cho hệ thống có VPN, DNS resolver, IDS/IPS, WAF và hai subnet dữ liệu. Nêu rõ tài sản, luồng, trust boundary, tác nhân, điều kiện, hậu quả, kiểm soát, mức ưu tiên và phép kiểm chứng; đừng chỉ ghi nhận xét “cần bật HTTPS”.

## 12. Ghi nhớ

- Information disclosure trong STRIDE tập trung vào **tính bí mật**: dữ liệu bị đọc, suy ra hoặc thu thập bởi chủ thể không có quyền.
- Cần phân tích **cả nội dung và metadata**, trên đường truyền, tại điểm kết thúc mã hóa, trong log, backup và các dịch vụ bên thứ ba.
- **Mã hóa, xác thực, phân quyền, phân đoạn, egress control và data minimization** giải quyết các mắt xích khác nhau; không biện pháp đơn lẻ nào bảo vệ toàn bộ vòng đời dữ liệu.
- DFD và trust boundary giúp xác định chính xác nơi dữ liệu thay đổi chủ thể kiểm soát, thay vì dựa vào giả định “mạng nội bộ là an toàn”.
- Một threat record tốt chỉ ra **tài sản, điều kiện, đường lộ, tác động, biện pháp, người phụ trách và cách kiểm chứng**; sau triển khai phải đánh giá rủi ro còn lại.

# Network security là gì và bảo vệ tài sản nào?

Trong một hệ thống số, dữ liệu hiếm khi nằm yên tại một máy tính. Trình duyệt gửi yêu cầu đến máy chủ, ứng dụng truy vấn cơ sở dữ liệu, dịch vụ gọi API của nhau, nhân viên quản trị truy cập hệ thống từ xa và thiết bị liên tục hỏi DNS để tìm địa chỉ đích. Mỗi kết nối tạo ra một đường mà dữ liệu, danh tính và quyền truy cập có thể bị đánh cắp, thay đổi hoặc làm gián đoạn.

**Network security (an ninh mạng ở cấp độ kết nối và hạ tầng mạng)** là tập hợp kiến trúc, chính sách, quy trình và biện pháp kỹ thuật nhằm kiểm soát ai hoặc thiết bị nào được kết nối, được trao đổi thông tin gì, qua đường nào, trong điều kiện nào; đồng thời phát hiện, ngăn chặn và ứng phó với hoạt động bất thường trên mạng. Phạm vi này trải dài từ mạng nội bộ, mạng không dây, kết nối từ xa đến trung tâm dữ liệu và hạ tầng đám mây.

Bài học thuộc chương **Nhập môn** của lĩnh vực **SECURITY_NETWORK_SECURITY**. Đây là nền tảng để học cách thiết kế nhiều lớp phòng vệ: phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS và Wi-Fi, giám sát lưu lượng, mô hình hóa mối đe dọa và bảo vệ mạng cloud.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích mục tiêu của network security và vì sao một firewall đơn lẻ không đủ bảo vệ hệ thống.
2. Nhận diện **tài sản cần bảo vệ**: dữ liệu, dịch vụ, danh tính, thiết bị, hạ tầng, hệ thống quản trị, tính liên tục và bằng chứng giám sát.
3. Phân biệt tài sản, mối đe dọa, điểm yếu, rủi ro và biện pháp kiểm soát; chỉ ra ranh giới tin cậy trên một sơ đồ mạng.
4. Gắn các lớp phòng vệ phổ biến với loại rủi ro mà chúng giảm thiểu, và hiểu giới hạn của mỗi lớp.
5. Thực hiện bước đầu kiểm kê luồng kết nối, đọc dấu hiệu trong lưu lượng và đặt câu hỏi đúng khi thiết kế kiến trúc mạng an toàn.

## 1. Một hệ thống hoạt động thì mạng đã trở thành bề mặt tấn công

Hãy hình dung một nền tảng học trực tuyến:

- Học viên truy cập website bằng Wi-Fi công cộng hoặc mạng di động.
- Trình duyệt cần DNS để tìm địa chỉ dịch vụ, rồi thiết lập kết nối HTTPS đến API.
- API xử lý đăng nhập, đọc bài học, ghi tiến độ vào cơ sở dữ liệu và gọi dịch vụ lưu trữ.
- Nhân viên vận hành cần quản trị máy chủ, hệ thống triển khai và cơ sở dữ liệu qua một đường truy cập riêng.
- Nhật ký và số liệu theo dõi được chuyển đến hệ thống giám sát để phát hiện sự cố.

Nếu một thiết bị lạ truy cập trực tiếp được cổng quản trị cơ sở dữ liệu, bí mật nghiệp vụ có nguy cơ bị lộ. Nếu DNS dẫn người dùng đến địa chỉ giả, họ có thể bị lừa đăng nhập. Nếu kẻ tấn công làm nghẽn đường kết nối hoặc chiếm tài khoản quản trị cloud, dịch vụ có thể ngừng hoạt động dù mã nguồn ứng dụng không thay đổi.

Từ ví dụ trên, **network security không chỉ bảo vệ dây mạng và router**. Nó bảo vệ việc sử dụng các tài sản số thông qua mọi kết nối, bao gồm cả những kết nối *bên trong* hạ tầng vốn thường bị xem là an toàn.

## 2. Network security cố gắng bảo đảm điều gì?

Ba mục tiêu cơ bản thường được mô tả bằng mô hình **CIA**:

| Mục tiêu | Câu hỏi phải trả lời | Ví dụ trong hệ thống học trực tuyến |
|---|---|---|
| **Confidentiality – Tính bí mật** | Người không được phép có đọc được thông tin không? | Không để người nghe lén Wi-Fi đọc mật khẩu, token phiên hay dữ liệu cá nhân trong luồng truyền. |
| **Integrity – Tính toàn vẹn** | Dữ liệu và thông điệp có bị sửa trái phép không? | Ngăn việc thay đổi nội dung phản hồi API hoặc chuyển hướng bản cập nhật đến nguồn giả mạo. |
| **Availability – Tính sẵn sàng** | Dịch vụ có còn truy cập được khi cần không? | Giảm gián đoạn do lưu lượng quá tải, cấu hình định tuyến sai, lỗi firewall hay tấn công từ chối dịch vụ. |

CIA là điểm khởi đầu, nhưng việc bảo vệ kết nối còn đòi hỏi:

- **Xác thực (authentication):** kiểm tra thực thể đang kết nối là ai/cái gì, như người dùng, máy chủ hoặc workload. Chứng chỉ máy chủ, xác thực đa yếu tố (MFA) và danh tính workload giải quyết những vấn đề khác nhau.
- **Phân quyền (authorization):** sau khi đã xác thực, thực thể có được phép gọi dịch vụ, vào mạng quản trị hay truy cập dữ liệu cụ thể không?
- **Khả năng truy vết (accountability):** có lưu được bằng chứng về kết nối, hành động và thay đổi cấu hình để điều tra hoặc kiểm toán không?
- **Tính riêng tư và tính liên tục:** hạn chế lộ thông tin về người dùng, địa chỉ, mô hình sử dụng; có phương án phục hồi khi một thành phần mạng hỏng.

**Ví dụ:** HTTPS dùng TLS để bảo vệ nội dung trao đổi trên đường truyền và hỗ trợ xác thực máy chủ. HTTPS tự nó **không** quyết định học viên có quyền sửa điểm hay không; đó còn là trách nhiệm xác thực, phân quyền và logic phía ứng dụng. Ngược lại, kiểm tra quyền ứng dụng đúng cũng không bù được cho việc mở cổng quản trị cơ sở dữ liệu ra Internet.

### Phân biệt phạm vi

**Network security** tập trung vào kết nối, luồng truyền, đường đi, phân vùng tin cậy và thiết bị/dịch vụ điều khiển mạng. **Application security** tập trung vào logic và đầu vào của ứng dụng; **endpoint security** bảo vệ thiết bị đầu cuối; **data security** tập trung vào dữ liệu và vòng đời dữ liệu. Các lĩnh vực này chồng lấn và phải phối hợp. Một sự cố thực tế có thể bắt đầu từ thiết bị bị nhiễm mã độc, lan qua kết nối nội bộ rồi dẫn đến rò rỉ dữ liệu ứng dụng.

## 3. Network security bảo vệ những tài sản nào?

Trong bảo mật, **tài sản (asset)** là bất cứ thứ gì có giá trị mà tổ chức cần giữ bí mật, giữ nguyên vẹn hoặc duy trì khả năng sử dụng. Tài sản có thể hữu hình (thiết bị), vô hình (dữ liệu, uy tín) hoặc là năng lực vận hành (khả năng cấp dịch vụ). Không nên chỉ lập danh sách các địa chỉ IP: IP là một thông tin để định vị tài sản, không phải toàn bộ giá trị cần bảo vệ.

| Nhóm tài sản | Những gì cần kiểm kê | Điều gì có thể xảy ra nếu kết nối bị xâm phạm? | Bảo vệ mạng thường liên quan |
|---|---|---|---|
| **Dữ liệu và bí mật** | Thông tin cá nhân, hồ sơ học tập, dữ liệu thanh toán, token, khóa API, khóa mã hóa, bản sao lưu | Bị đọc lén, chuyển ra ngoài, sửa đổi hoặc mất khả năng truy cập | TLS, phân vùng dữ liệu, kiểm soát đường ra, giám sát luồng truyền |
| **Dịch vụ và API** | Website, backend, cổng đăng nhập, API nội bộ, hàng đợi, dịch vụ lưu trữ | Bị ngắt dịch vụ, gọi trái phép, vượt qua tầng kiểm soát | Firewall, reverse proxy, kiểm soát L7, giới hạn lưu lượng, mạng riêng |
| **Danh tính và phiên truy cập** | Tài khoản nhân viên, tài khoản dịch vụ, thông tin đăng nhập, chứng chỉ, phiên VPN, quyền IAM | Bị giả mạo người dùng hoặc workload; chiếm quyền quản trị | MFA, xác thực thiết bị, mTLS khi phù hợp, quản trị đặc quyền |
| **Thiết bị đầu cuối** | Laptop, điện thoại, máy trạm quản trị, thiết bị IoT, máy chủ | Thiết bị bị chiếm quyền trở thành điểm xuất phát cho di chuyển ngang | Phân đoạn, kiểm soát thiết bị truy cập, kiểm soát cổng mạng |
| **Thiết bị và cấu hình mạng** | Router, switch, firewall, access point, load balancer, route, ACL | Đường truyền bị chuyển hướng, chính sách bị nới lỏng, mạng bị chia cắt | Mạng quản trị riêng, tài khoản quản trị mạnh, sao lưu cấu hình |
| **Hạ tầng định danh và tìm đường** | DNS resolver, zone DNS, DHCP, PKI, chứng chỉ, đồng bộ thời gian | Người dùng bị dẫn sai đích, cấp địa chỉ sai, xác thực hoặc ghi log lỗi | Bảo vệ DNS, quản lý chứng chỉ, phân quyền thay đổi cấu hình |
| **Mạng không dây và truy cập từ xa** | SSID, bộ phát Wi-Fi, thiết bị kết nối, VPN/ZTNA gateway | Người lạ vào mạng nội bộ, nghe lén, lạm dụng kết nối từ xa | WPA3 phù hợp, mạng khách riêng, MFA, kiểm soát quyền sau kết nối |
| **Tài nguyên và control plane cloud** | VPC/VNet, subnet, security group, định tuyến, private endpoint, IAM, API quản trị | Một thay đổi quyền/cấu hình có thể mở rộng bề mặt tấn công trên nhiều dịch vụ | Phân tách mạng, chính sách tối thiểu, nhật ký quản trị, kiểm tra cấu hình |
| **Hệ thống giám sát và phục hồi** | Firewall log, DNS log, NetFlow, cảnh báo, log tập trung, backup | Không phát hiện xâm nhập, không biết phạm vi sự cố hoặc không thể phục hồi | Thu thập log bảo vệ khỏi sửa/xóa, giám sát, đường phục hồi dự phòng |
| **Con người và hoạt động kinh doanh** | Học viên, nhân viên, đối tác, quy trình đăng nhập, tiến trình cung cấp khóa học | Mất lòng tin, ảnh hưởng quyền riêng tư, gián đoạn việc học và vận hành | Bảo vệ thông tin, tiếp cận theo rủi ro, ứng phó và khôi phục |

Từ bảng trên có ba quan sát quan trọng.

**Thứ nhất: tài sản cần bảo vệ không chỉ nằm trong mạng nội bộ.** Điện thoại học viên, nhân viên làm việc từ xa, nhà cung cấp dịch vụ và môi trường cloud đều tham gia vào luồng tin cậy.

**Thứ hai: cùng một tài sản có nhiều cách bị ảnh hưởng.** Cơ sở dữ liệu có thể bị lộ thông tin (**bí mật**), bị chỉnh sửa kết quả học tập (**toàn vẹn**) hoặc bị cô lập vì lỗi định tuyến (**sẵn sàng**). Mỗi mục tiêu dẫn đến biện pháp khác nhau.

**Thứ ba: chính hệ thống bảo vệ cũng là tài sản.** Một người có thể thay quy tắc firewall, tắt bộ cảm biến IDS hay xóa log thì khả năng bảo vệ và điều tra đều suy giảm. Kênh quản trị, tài khoản đặc quyền, cấu hình và bằng chứng giám sát phải được bảo vệ.

### Tài sản, luồng dữ liệu và trạng thái của dữ liệu

Dữ liệu có ba trạng thái thường được xét:

- **Đang truyền (in transit):** thông điệp HTTP, truy vấn DNS, lưu lượng giữa API và database; đây là trọng tâm trực tiếp của network security.
- **Đang lưu trữ (at rest):** bản ghi database, tệp và backup; mạng giúp hạn chế ai kết nối được đến nơi lưu trữ, còn quyền dữ liệu và mã hóa lưu trữ cần cơ chế bổ sung.
- **Đang được xử lý (in use):** dữ liệu trong bộ nhớ và tiến trình; cần bảo vệ ứng dụng, hệ điều hành và môi trường thực thi, không thể trông chờ vào firewall.

Ngoài *nội dung* gói tin, **metadata** như địa chỉ nguồn/đích, thời gian, tên miền hoặc tần suất kết nối cũng có giá trị. Ngay cả khi nội dung được mã hóa, một phần metadata có thể vẫn quan sát được tùy giao thức và cấu hình.

## 4. Hiểu ranh giới tin cậy trước khi chọn công cụ

Một **trust boundary (ranh giới tin cậy)** là nơi một kết nối đi từ vùng có chính sách hoặc mức tin cậy này sang vùng khác. Ví dụ: Internet → cổng dịch vụ công khai; frontend → backend; ứng dụng → database; laptop nhân viên → mạng quản trị; workload → API quản trị cloud.

Mô hình tham khảo cho nền tảng học trực tuyến:

~~~mermaid
flowchart LR
    U["Người học trên Internet"] -->|"HTTPS"| EDGE["Cổng biên: CDN / reverse proxy / firewall"]
    EDGE -->|"Chỉ cổng dịch vụ"| APP["Mạng ứng dụng: API"]
    APP -->|"Chỉ cổng cơ sở dữ liệu"| DB[("Mạng dữ liệu: database")]
    ADMIN["Nhân viên vận hành"] -->|"MFA + kết nối bảo vệ"| GATE["Cổng truy cập quản trị"]
    GATE -->|"Quyền theo vai trò"| MGMT["Mạng quản trị"]
    MGMT -->|"Kênh quản trị giới hạn"| APP
    EDGE -.->|"Log"| LOG["Hệ thống giám sát tập trung"]
    APP -.->|"Log"| LOG
    GATE -.->|"Log"| LOG
~~~

Sơ đồ thể hiện **những luồng được phép dự kiến**, không có nghĩa kết nối tự động an toàn. Chính sách thực tế cần quy định rõ nguồn, đích, cổng/giao thức, danh tính khi áp dụng được, điều kiện truy cập và nơi ghi log.

| Luồng | Kỳ vọng chính sách | Điều cần tránh |
|---|---|---|
| Internet → cổng biên | Chỉ công khai dịch vụ thực sự cần thiết, thường HTTPS 443 | Đưa cổng quản trị hoặc database ra Internet |
| Cổng biên → API | Chỉ tới các đích và cổng ứng dụng đã đăng ký | Cho phép tùy ý đến toàn bộ mạng riêng |
| API → database | Chỉ workload ứng dụng cần thiết tới đúng dịch vụ database, ví dụ TCP 5432 nếu dùng PostgreSQL | Cho mọi subnet truy cập database |
| Nhân viên → môi trường quản trị | MFA, danh tính phù hợp, phiên truy cập được giám sát, tối thiểu đặc quyền | Coi “đã vào VPN” là có toàn quyền |
| Workload → DNS / dịch vụ ngoài | Qua resolver/đích đã được chấp thuận, ghi nhận khi cần | Cho mọi máy tự do chuyển dữ liệu đến bất kỳ đích nào |
| Các vùng → hệ thống ghi log | Chuyển log qua kênh được bảo vệ, chống sửa/xóa trái phép | Cho máy nguồn tự sửa hoặc xóa bằng chứng tập trung |

Trong thực tế, phản hồi của các kết nối được phép có thể được xử lý theo trạng thái kết nối (*stateful*); không nhất thiết mở hai chiều một cách vô điều kiện. Cần kiểm tra riêng luồng IPv4 và IPv6 nếu hạ tầng hỗ trợ cả hai.

### “Nội bộ” không đồng nghĩa “đáng tin”

Một laptop nhân viên có thể bị nhiễm mã độc; một container bị khai thác có thể tìm cách truy cập dịch vụ bên cạnh; một tài khoản cloud có thể bị lộ. Vì vậy, an toàn không dừng ở việc đặt mọi thứ sau một firewall biên. **Zero Trust** là nguyên tắc không tự động cấp quyền chỉ vì một thực thể đang ở bên trong mạng; truy cập cần được xác minh và giới hạn dựa trên danh tính, bối cảnh, chính sách, đồng thời được theo dõi liên tục.

## 5. Những loại rủi ro network security xử lý

Cần phân biệt năm khái niệm dễ nhầm:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Tài sản** | Thứ có giá trị cần bảo vệ | Cơ sở dữ liệu tiến độ học tập |
| **Mối đe dọa (threat)** | Tác nhân hoặc sự kiện có thể gây hại | Kẻ tấn công bên ngoài, tài khoản bị chiếm, lỗi cấu hình |
| **Điểm yếu (vulnerability/weakness)** | Điều kiện làm hành vi gây hại có thể thành công | Database mở cho mọi IP; tài khoản quản trị không có MFA |
| **Rủi ro (risk)** | Khả năng và hậu quả khi mối đe dọa tác động đến tài sản qua điểm yếu | Rò rỉ dữ liệu học viên hoặc gián đoạn toàn bộ khóa học |
| **Biện pháp kiểm soát (control)** | Cách giảm xác suất hoặc hậu quả của rủi ro | Chặn cổng không cần thiết, phân đoạn, giám sát, backup |

Những cách tấn công hoặc sự cố cần xét ở mức nhập môn:

- **Nghe lén hoặc can thiệp đường truyền:** dữ liệu truyền không mã hóa hoặc không xác thực đích có thể bị đọc, sửa hoặc chuyển hướng.
- **Truy cập trái phép:** cổng quản trị bị công khai, quy tắc firewall quá rộng, danh tính hoặc chứng chỉ bị lộ.
- **Di chuyển ngang (lateral movement):** sau khi chiếm một thiết bị/workload, kẻ tấn công thử kết nối tiếp đến các máy nội bộ.
- **Lạm dụng DNS hoặc hạ tầng tìm đường:** sửa bản ghi DNS, đầu độc kết quả phân giải trong một số điều kiện, thay đổi tuyến hoặc cấu hình mạng.
- **Tấn công và lỗi ảnh hưởng sẵn sàng:** DDoS, quá tải đường truyền, lỗi cấu hình định tuyến, sự cố đường truyền hoặc thành phần đơn lẻ.
- **Rò rỉ qua đường ra (egress):** máy chủ bị xâm nhập gửi dữ liệu đến nơi không được phép, đôi khi ẩn trong lưu lượng trông có vẻ bình thường.
- **Truy cập Wi-Fi hoặc từ xa không an toàn:** dùng thông tin xác thực yếu, điểm truy cập giả, thiết bị không được quản lý hoặc cấp quyền mạng quá rộng.
- **Sai cấu hình cloud:** security group quá mở, thiếu phân chia subnet, lộ endpoint riêng, quyền API quản trị quá lớn.

Không có biện pháp đơn lẻ loại bỏ tất cả các nguy cơ. Rủi ro cũng phụ thuộc vào **giá trị tài sản, mức phơi bày, khả năng khai thác và tác động**; tổ chức phải ưu tiên theo ngữ cảnh thực tế.

## 6. Các lớp phòng vệ làm việc cùng nhau như thế nào?

**Defense in depth (phòng vệ nhiều lớp)** nghĩa là đặt nhiều kiểm soát bổ trợ nhau trên đường tấn công có thể xảy ra. Nếu một lớp thất bại, các lớp khác vẫn có cơ hội hạn chế phạm vi và phát hiện sự cố.

| Lớp / công cụ | Vai trò chính | Giới hạn cần hiểu |
|---|---|---|
| **Phân đoạn mạng (segmentation)** | Chia mạng thành các vùng và kiểm soát kết nối giữa chúng, hạn chế di chuyển ngang | Phân đoạn vô nghĩa nếu mọi vùng đều được phép nói chuyện với nhau |
| **Firewall, ACL, security group** | Quyết định luồng nào được đi qua dựa trên địa chỉ, cổng, giao thức, trạng thái hoặc tiêu chí của công cụ | Luồng “được phép” vẫn có thể mang nội dung độc hại; luật quá rộng tạo lỗ hổng |
| **VPN / kênh mã hóa** | Bảo vệ đường truyền qua mạng không tin cậy, thường phục vụ kết nối từ xa hoặc giữa mạng | VPN không xác minh từng hành động của người dùng và không tự bảo đảm thiết bị sạch |
| **TLS, chứng chỉ, mTLS** | Mã hóa dữ liệu truyền, kiểm tra danh tính đầu cuối; mTLS cho phép hai phía xác thực bằng chứng chỉ | Không thay thế phân quyền ứng dụng, quản lý khóa/chứng chỉ hoặc bảo vệ dữ liệu tại nơi xử lý |
| **IDS / IPS** | IDS phát hiện và cảnh báo dấu hiệu đáng ngờ; IPS có thể chặn trực tiếp theo chính sách | Có cảnh báo nhầm/bỏ sót; lưu lượng mã hóa có thể hạn chế khả năng kiểm tra nội dung |
| **Bảo vệ DNS** | Kiểm soát resolver, nhật ký tên miền, chính sách phân giải, xác thực dữ liệu DNS khi phù hợp | DNSSEC xác thực nguồn gốc/tính toàn vẹn dữ liệu DNS có ký, **không** mã hóa truy vấn; DoH/DoT mã hóa đường truyền đến resolver, **không** thay DNSSEC |
| **Bảo vệ Wi-Fi** | Dùng chuẩn bảo mật phù hợp, xác thực người/thiết bị, tách mạng khách và thiết bị IoT | Mạng Wi-Fi được mã hóa vẫn cần kiểm soát truy cập tới ứng dụng và phân đoạn bên trong |
| **Cloud network controls** | Giới hạn lưu lượng bằng VPC/VNet, subnet, route, security group, private endpoint và chính sách cloud | Nhà cung cấp bảo vệ hạ tầng của họ; khách hàng vẫn chịu trách nhiệm cấu hình và quyền của phần mình quản lý |
| **Giám sát lưu lượng và log** | Nhìn thấy ai kết nối tới đâu, lúc nào, với đặc điểm gì; phát hiện lệch chuẩn và hỗ trợ điều tra | Log thiếu ngữ cảnh hoặc không được bảo vệ có thể dẫn tới kết luận sai |
| **Chống DDoS, dự phòng và khôi phục** | Giảm thiệt hại vì quá tải hoặc lỗi mạng; phục hồi khả năng cấp dịch vụ | Không xử lý thay cho bảo mật danh tính hay quyền truy cập dữ liệu |

### Các lớp tại vị trí nào?

Ở **biên Internet**, tổ chức thường công khai tối thiểu các dịch vụ cần truy cập, dùng lọc lưu lượng, reverse proxy và biện pháp chống DDoS phù hợp. Ở **mạng nội bộ**, phân đoạn ứng dụng, dữ liệu và quản trị, cùng quy tắc chỉ cho phép các luồng cần thiết, giúp giảm đường di chuyển ngang. Ở **đường kết nối**, TLS, VPN hoặc cơ chế xác thực workload bảo vệ thông điệp và danh tính. Ở **lớp quan sát**, cảm biến IDS/IPS, log firewall, DNS, flow log và cảnh báo cung cấp dấu hiệu điều tra. Ở **cloud**, các vùng mạng logic, danh tính quản trị và khả năng ghi nhật ký cần được cấu hình nhất quán.

Một số nguyên tắc xuyên suốt:

1. **Mặc định từ chối (default deny)** đối với kết nối không có nhu cầu nghiệp vụ được phê duyệt.
2. **Quyền tối thiểu (least privilege)** cho cả người, máy, workload, đường quản trị và luồng mạng.
3. **Giảm bề mặt tấn công:** không công khai dịch vụ quản trị, bỏ cổng/dịch vụ không dùng, kiểm soát đường ra.
4. **Xác minh tại ranh giới tin cậy:** mạng, thiết bị hoặc IP “quen” không thay thế danh tính và phân quyền.
5. **Có khả năng quan sát và phục hồi:** đo lường, cảnh báo, lưu bằng chứng, thử phương án khắc phục và phục hồi.

## 7. Minh họa phân tích một luồng kết nối

Giả sử trình duyệt học viên yêu cầu trang bài học qua HTTPS. Luồng có thể đi theo chuỗi:

1. **Phân giải tên miền:** trình duyệt/hệ điều hành cần địa chỉ IP của tên dịch vụ qua resolver. Cần bảo vệ quyền sửa bản ghi DNS và chính sách resolver; kết quả DNS hợp lệ không đồng nghĩa website sẽ tự động đáng tin.
2. **Thiết lập đường truyền:** thiết bị định tuyến gói tin đến địa chỉ đích. Firewall và các bộ lọc quyết định luồng TCP/UDP có được qua hay không.
3. **Bắt tay TLS:** client xác minh chứng chỉ và danh tính máy chủ theo tên miền, sau đó thiết lập phiên mã hóa nếu đàm phán thành công. Cần cấu hình TLS phù hợp và quản lý vòng đời chứng chỉ.
4. **Yêu cầu ứng dụng:** gateway/API tiếp nhận yêu cầu, xác thực phiên và kiểm tra quyền lấy bài học. Network security giảm khả năng truy cập sai đường, nhưng ứng dụng vẫn phải kiểm tra quyền đối với từng tài nguyên.
5. **Truy vấn dữ liệu:** API kết nối đến database qua luồng nội bộ đã cho phép. Database không cần nhận kết nối trực tiếp từ trình duyệt.
6. **Theo dõi:** log gateway, ứng dụng, firewall, DNS và môi trường cloud cho phép ghép lại chuỗi sự kiện khi có nghi vấn.

Người vận hành mạng thường quan sát một **5-tuple**: IP nguồn, cổng nguồn, IP đích, cổng đích và giao thức (TCP/UDP). Có thể kết hợp thời gian, khối lượng byte, trạng thái phiên, DNS và danh tính workload. **Port 443** gợi ý dịch vụ HTTPS thường gặp, nhưng chỉ nhìn cổng không đủ khẳng định lưu lượng an toàn hay nội dung thực tế là gì.

Ví dụ nhật ký giả định (địa chỉ dùng cho minh họa):

~~~text
2026-11-28T09:10:01Z action=ALLOW proto=TCP src=10.20.10.8:52314 dst=10.20.20.12:5432 rule=app-to-db
2026-11-28T09:10:04Z action=DENY  proto=TCP src=198.51.100.24:51022 dst=10.20.20.12:5432 rule=deny-public-to-db
2026-11-28T09:10:09Z action=DENY  proto=TCP src=10.20.30.15:49801 dst=10.20.20.12:5432 rule=deny-other-zone-to-db
~~~

Dòng thứ nhất phù hợp với chính sách giả định: máy ứng dụng kết nối database. Dòng thứ hai là một nỗ lực kết nối từ nguồn ngoài vùng riêng bị từ chối. Dòng thứ ba cho thấy một nguồn thuộc vùng khác cố tới database; cần xác minh đó là lỗi cấu hình, kiểm thử hay dấu hiệu bất thường. **Một lần bị chặn không đủ kết luận đã có xâm nhập**; điều tra cần đối chiếu tài sản, quyền, thời gian, các log liên quan và hành vi trước/sau.

### Quan sát cơ bản trong môi trường được phép quản trị

Ví dụ các lệnh xem thông tin trên Linux, chỉ chạy trên máy hoặc mạng bạn có quyền kiểm tra:

~~~bash
# Kiểm tra địa chỉ giao diện và bảng định tuyến
ip -br address
ip route

# Liệt kê cổng TCP đang lắng nghe và tiến trình nếu được phép xem
ss -lntp

# Quan sát tối đa 20 gói thuộc một luồng TCP 443 trên giao diện phù hợp
sudo tcpdump -i eth0 -nn -c 20 'tcp port 443'
~~~

Tên giao diện như **eth0** chỉ là ví dụ; máy thật có thể dùng tên khác. Bản chụp gói tin và log có thể chứa thông tin nhạy cảm, vì vậy cần giới hạn quyền truy cập, phạm vi thu thập và thời gian lưu trữ. Để hiểu một sự kiện, hãy hỏi: **nguồn là tài sản nào, đích là dịch vụ gì, lý do kinh doanh của luồng này là gì, được quy tắc nào cho phép và điều gì bất thường so với hành vi chuẩn?**

## 8. Mô hình hóa mối đe dọa bắt đầu từ tài sản

**Threat modeling (mô hình hóa mối đe dọa)** giúp chuyển câu hỏi chung “mạng có an toàn không?” thành những tình huống kiểm tra được. Một cách tiếp cận đơn giản cho người mới:

1. **Xác định phạm vi:** hệ thống, chủ sở hữu, môi trường (on-premises/cloud), người dùng và kết nối ngoài phạm vi.
2. **Kiểm kê tài sản:** dữ liệu quan trọng, dịch vụ thiết yếu, danh tính có đặc quyền, DNS, thiết bị mạng, kênh quản trị và bằng chứng log.
3. **Vẽ luồng và ranh giới tin cậy:** mô tả nguồn → đích → mục đích → giao thức/cổng → cơ chế xác thực → vùng mạng.
4. **Đặt tình huống gây hại:** nếu một nguồn bị chiếm, nếu DNS bị sửa, nếu đường kết nối đứt, nếu rule firewall bị mở rộng thì tài sản nào bị ảnh hưởng?
5. **Ưu tiên:** xét mức phơi bày, khả năng xảy ra và tác động lên bí mật/toàn vẹn/sẵn sàng; xem các biện pháp đã có.
6. **Chọn kiểm soát và người chịu trách nhiệm:** tránh chỉ ghi tên công cụ; mô tả luồng nào bị chặn, sự kiện nào được phát hiện và ai xử lý.
7. **Kiểm tra lại:** thử các luồng được phép và phải bị từ chối, giám sát thay đổi cấu hình, rà soát khi kiến trúc hoặc nghiệp vụ đổi.

Ví dụ cho nền tảng học trực tuyến:

| Tài sản ưu tiên | Tình huống cần mô hình hóa | Kiểm soát đề xuất | Cách kiểm tra |
|---|---|---|---|
| Database hồ sơ học viên | Container frontend bị chiếm rồi tìm đường vào database | Tách vùng; chỉ cho workload API cần thiết kết nối database; quyền DB tối thiểu | Kiểm tra ma trận luồng, xác minh kết nối sai vùng bị từ chối |
| Tài khoản quản trị | Thông tin đăng nhập bị lộ, kẻ lạ kết nối từ xa | MFA, cổng truy cập quản trị riêng, quyền theo vai trò, log phiên | Rà soát lịch sử đăng nhập, kiểm thử quyền truy cập theo vai trò |
| Tên miền và dịch vụ đăng nhập | Bản ghi DNS bị sửa hoặc truy cập nhầm đích | Bảo vệ tài khoản quản lý DNS, giám sát thay đổi, TLS/chứng chỉ hợp lệ | Kiểm tra phân quyền DNS và cảnh báo thay đổi bất thường |
| API phục vụ học viên | Lưu lượng tăng đột biến làm nghẽn dịch vụ | Giới hạn tốc độ ở tầng phù hợp, chống DDoS, dự phòng, cảnh báo | Diễn tập tải có kiểm soát, đo mức phục vụ và khả năng phục hồi |
| Bằng chứng sự cố | Workload bị xâm nhập tìm cách xóa log | Chuyển log đến nơi lưu tập trung, hạn chế quyền sửa/xóa | Kiểm thử quyền truy cập log và quy trình tra cứu sự kiện |

Ví dụ trên chỉ minh họa **cách phân tích**. Khi triển khai thật cần xác nhận công nghệ, đường truyền, chủ sở hữu, mức rủi ro chấp nhận được và biện pháp bảo vệ hiện hữu.

## 9. Một số quyết định kiến trúc thường gặp

### Có firewall rồi, có cần phân đoạn không?

**Có**, nếu tài sản có các mức nhạy cảm hoặc nhu cầu kết nối khác nhau. Firewall ở biên kiểm soát phần lớn lưu lượng vào/ra; phân đoạn và chính sách giữa các vùng còn kiểm soát luồng *east–west* (giữa máy/dịch vụ bên trong). Nếu một máy bị chiếm quyền, giới hạn kết nối tới database và hệ thống quản trị có thể giảm thiểu thiệt hại. Phân đoạn cần được kiểm chứng bằng hành vi thực tế, không chỉ bằng sơ đồ subnet.

### Có VPN rồi, có cần MFA và phân quyền tiếp không?

**Có.** VPN có thể thiết lập kênh truyền bảo vệ đến mạng hoặc cổng truy cập. Nó không bảo đảm mọi hành động sau kết nối đều được phép. Cần xác thực mạnh, cấp quyền theo người/thiết bị/vai trò, hạn chế phạm vi và theo dõi các hoạt động đặc quyền. Một số tổ chức dùng truy cập theo ứng dụng (chẳng hạn giải pháp Zero Trust Network Access) thay cho quyền vào cả mạng; lựa chọn phụ thuộc nhu cầu và khả năng quản lý.

### TLS có khiến IDS/IPS và phân tích lưu lượng vô dụng không?

**Không.** Mã hóa làm giảm khả năng nhìn thấy *nội dung* gói tin tại các điểm trung gian, nhưng nhiều tín hiệu như địa chỉ, thời gian, số lượng kết nối, khối lượng truyền, trạng thái và nhật ký từ endpoint/gateway vẫn hữu ích. Kiểm tra sâu nội dung lưu lượng mã hóa có thể đòi hỏi vị trí quan sát thích hợp và quyền truy cập hợp lệ, phải cân nhắc rủi ro bảo mật và quyền riêng tư.

### Dùng dịch vụ cloud thì nhà cung cấp đã bảo vệ hết mạng chưa?

**Chưa.** Trách nhiệm được chia sẻ tùy mô hình dịch vụ. Nhà cung cấp quản lý hạ tầng bên dưới theo cam kết, còn khách hàng thường vẫn phải cấu hình mạng ảo, quyền IAM, endpoint, bảo mật workload, kết nối với dịch vụ khác và giám sát. Đặc biệt phải xét **control plane** (API và quyền điều khiển tài nguyên cloud), vì thay đổi sai ở đây có thể ảnh hưởng hàng loạt hệ thống.

### DNS chỉ dùng để “đổi tên thành IP”?

**DNS còn là một điểm phụ thuộc về bảo mật và sẵn sàng.** Nếu kiểm soát tên miền, bản ghi hay resolver bị mất, người dùng có thể bị đưa sai đích hoặc dịch vụ mất khả năng truy cập. Cần quản lý quyền sửa bản ghi, theo dõi thay đổi, thiết kế resolver tin cậy và áp dụng cơ chế bảo vệ phù hợp. Không nên nhầm tính xác thực DNSSEC với tính riêng tư của DoH/DoT.

## 10. Checklist đầu tiên khi nhận một hệ thống cần bảo vệ

Trước khi cấu hình sản phẩm cụ thể, hãy ghi thành tài liệu trả lời được các câu hỏi:

- **Tài sản:** hệ thống chứa dữ liệu nhạy cảm ở đâu? Dịch vụ nào phải luôn sẵn sàng? Ai sở hữu và chịu trách nhiệm?
- **Luồng:** nguồn nào thật sự cần kết nối tới đích nào, bằng giao thức/cổng nào, với mục đích gì?
- **Điểm công khai:** những dịch vụ, IP, tên miền và cổng nào truy cập được từ Internet? Có hệ thống quản trị nào bị lộ không?
- **Ranh giới:** có phân tách người dùng, ứng dụng, database, mạng khách, quản trị và môi trường phát triển/production không?
- **Danh tính:** ai được cấp quyền từ xa, xác thực thế nào, quyền có hết hạn và có thể thu hồi không?
- **Kiểm soát:** những kết nối không khai báo có bị chặn? Truy cập ra ngoài có được theo dõi hoặc giới hạn khi cần?
- **Quan sát:** có log cho truy cập được phép/bị từ chối, truy vấn DNS, thay đổi mạng và quản trị cloud? Có thể ghép sự kiện theo thời gian không?
- **Phục hồi:** nếu cổng kết nối, DNS, firewall hoặc đường mạng lỗi, dịch vụ phản ứng thế nào? Có thử quy trình khôi phục chưa?

Một **bảng kiểm kê luồng kết nối** là đầu ra thực tế có giá trị ngay từ đầu:

| Nguồn / chủ sở hữu | Đích / tài sản | Mục đích | Giao thức / cổng | Ranh giới | Chính sách dự kiến |
|---|---|---|---|---|---|
| Người học | HTTPS gateway | Xem bài học, đăng nhập | HTTPS / TCP 443 | Internet → biên công khai | Cho phép, giới hạn và giám sát |
| Backend API | Database | Đọc/ghi tiến độ học | PostgreSQL / TCP 5432 (ví dụ) | Mạng ứng dụng → mạng dữ liệu | Chỉ workload API được phép |
| Quản trị viên | Cổng quản trị | Vận hành hệ thống | Giao thức quản trị theo thiết kế | Thiết bị quản trị → vùng quản trị | MFA, quyền tối thiểu, lưu log |
| Workload | Resolver DNS | Phân giải tên miền | DNS theo cấu hình | Vùng workload → dịch vụ hạ tầng | Chỉ resolver được duyệt |

Ma trận này cần chuyển thành chính sách cho **cả chiều vào, chiều ra và lưu lượng nội bộ**, rồi kiểm thử rằng các luồng cần thiết hoạt động và các luồng không được phép bị từ chối. Mỗi lần thêm dịch vụ hay thay đổi kiến trúc, cập nhật lại ma trận.

## 11. Những hiểu lầm cần tránh

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Ở trong LAN/VPC là an toàn.” | Máy nội bộ và workload cũng có thể bị xâm nhập; cần kiểm tra danh tính và giới hạn kết nối. |
| “Đóng hết cổng là đủ.” | Phải vừa cho phép luồng nghiệp vụ, vừa bảo vệ danh tính, nội dung truyền, cấu hình và khả năng phục hồi. |
| “HTTPS giải quyết mọi vấn đề bảo mật.” | HTTPS bảo vệ kênh truyền; không tự xử lý lỗi phân quyền, máy đầu cuối bị chiếm hay lộ dữ liệu trong database. |
| “Firewall chặn mọi cuộc tấn công.” | Lưu lượng được phép cũng có thể nguy hiểm, chính sách có thể bị sai hoặc bị thay đổi. |
| “IDS không báo gì nghĩa là không có xâm nhập.” | IDS phụ thuộc phạm vi quan sát, tín hiệu và quy tắc phát hiện; luôn có khả năng bỏ sót. |
| “Mọi gói bị từ chối đều là một cuộc tấn công.” | Nguồn có thể là cấu hình sai, lỗi dịch vụ, phép thử được phép hoặc hoạt động độc hại; cần điều tra theo ngữ cảnh. |
| “Bật VPN là được quyền vào toàn bộ mạng.” | VPN là phương tiện kết nối; quyền vào từng dịch vụ cần được cấp và kiểm tra riêng. |
| “Cloud tự động bảo mật mọi tài nguyên.” | Kiểm soát mạng ảo, danh tính, dữ liệu, tài nguyên công khai và giám sát còn phụ thuộc cách khách hàng cấu hình. |

## 12. Tự kiểm tra kiến thức

**Tình huống A:** Một cổng học trực tuyến đã dùng HTTPS nhưng cơ sở dữ liệu cho phép mọi địa chỉ Internet truy cập. Ba câu hỏi đầu tiên cần hỏi là gì?

Gợi ý: (1) Vì sao database cần công khai; có thể đặt sau mạng riêng không? (2) Những workload nào thực sự cần kết nối và cổng nào phải mở? (3) Có cơ chế xác thực, phân quyền, log và quy tắc chặn kết nối sai vùng không? HTTPS ở phía trình duyệt không giải quyết trực tiếp vấn đề cổng database.

**Tình huống B:** Một máy chủ ứng dụng bất ngờ kết nối liên tục đến nhiều máy ở mạng quản trị. Điều gì nên được xác minh trước khi kết luận bị tấn công?

Gợi ý: xác định máy nguồn, danh tính workload, công việc hợp lệ, chính sách luồng, thời điểm bắt đầu hành vi, những thay đổi triển khai gần đây và các log đi kèm. Nếu không có nhu cầu nghiệp vụ, cần điều tra và giới hạn kết nối theo quy trình ứng phó.

**Tình huống C:** Hãy phân loại từng đối tượng là tài sản, điểm yếu, mối đe dọa hay biện pháp kiểm soát: (a) khóa API, (b) rule cho phép toàn bộ Internet vào SSH, (c) tài khoản bị chiếm quyền, (d) MFA, (e) log DNS.

Đáp án tham khảo: (a) tài sản/bí mật; (b) điểm yếu cấu hình; (c) mối đe dọa hoặc sự kiện gây hại tùy ngữ cảnh; (d) biện pháp kiểm soát; (e) tài sản quan sát và nguồn bằng chứng phục vụ phát hiện.

## Ghi nhớ

**Network security bảo vệ giá trị kinh doanh thông qua việc bảo vệ kết nối.** Tài sản quan trọng gồm dữ liệu, dịch vụ, danh tính, thiết bị, hệ thống mạng, DNS, kênh quản trị, hạ tầng cloud, log và khả năng vận hành liên tục. Cách bắt đầu có hệ thống là **kiểm kê tài sản → vẽ luồng và ranh giới tin cậy → mô hình hóa rủi ro → áp dụng kiểm soát nhiều lớp → giám sát và kiểm tra lại**.

Khi đi sâu vào những bài tiếp theo, hãy luôn đặt một câu hỏi xuyên suốt: **“Luồng kết nối này phục vụ tài sản nào, ai được phép thực hiện, điều gì xảy ra nếu nó bị lạm dụng, và làm sao biết chính sách bảo vệ đang thực sự có hiệu lực?”**

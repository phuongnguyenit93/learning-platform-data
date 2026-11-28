# Tiêu chí mở rộng sự cố thành security incident

## 1. Vì sao cần tiêu chí phân loại rõ ràng?

Trong vận hành mạng, một cảnh báo IDS, một kết nối bị firewall chặn, hoặc một dịch vụ ngừng đáp ứng đều là dấu hiệu cần xem xét. Tuy nhiên, không phải cảnh báo nào cũng là **sự cố an ninh (security incident)**. Ngược lại, một kết nối bất thường chưa gây gián đoạn vẫn có thể là dấu hiệu đầu tiên của việc đánh cắp thông tin, chiếm quyền điều khiển hoặc di chuyển ngang trong mạng.

Bài học này tập trung vào thời điểm **nâng một hiện tượng mạng hoặc một sự cố vận hành thành vụ việc cần quy trình ứng phó an ninh**: dựa trên bằng chứng nào, ai quyết định, ghi nhận mức độ chắc chắn ra sao và phải hành động thế nào khi chưa đủ thông tin. Đây là mắt xích giữa giám sát lưu lượng, phân đoạn mạng, firewall, VPN, DNS, IDS/IPS, hạ tầng đám mây và quy trình điều tra, cô lập, khôi phục sau xâm nhập.

Mục tiêu sau bài học:

- Phân biệt sự kiện mạng, cảnh báo, sự cố vận hành, trường hợp nghi ngờ và security incident.
- Áp dụng tiêu chí dựa trên **hành vi, bằng chứng, tài sản bị ảnh hưởng và hậu quả tiềm tàng**.
- Tách biệt **độ tin cậy của nhận định** với **mức độ nghiêm trọng của hậu quả**.
- Thực hiện chuyển giao từ NOC/đội vận hành sang SOC/đội ứng phó đúng thời điểm mà vẫn giữ được bằng chứng.
- Tránh cả hai cực đoan: nâng cấp mọi cảnh báo và chờ đến khi thiệt hại đã được xác nhận mới xử lý.

## 2. Xác định đúng đối tượng đang phân loại

| Khái niệm | Ý nghĩa thực hành | Ví dụ trong mạng |
|---|---|---|
| **Sự kiện (event)** | Một hành động hoặc trạng thái được ghi lại; chưa hàm ý có vấn đề | Firewall ghi một kết nối TCP đến máy chủ |
| **Cảnh báo (alert)** | Quy tắc hoặc công cụ phát hiện dấu hiệu đáng chú ý; có thể sai | IDS phát cảnh báo quét cổng |
| **Sự cố vận hành (operational/network incident)** | Suy giảm hoặc gián đoạn dịch vụ, chưa có bằng chứng về nguyên nhân an ninh | Mất kết nối do lỗi cấu hình định tuyến |
| **Trường hợp cần phân tích an ninh (security triage/case)** | Có tín hiệu đáng tin cậy cần kiểm tra liệu đã có hành vi tấn công hay không | Đăng nhập VPN lạ trùng thời điểm lưu lượng ra ngoài tăng mạnh |
| **Security incident nghi ngờ (suspected)** | Có cơ sở hợp lý để cho rằng hệ thống, dữ liệu hoặc chính sách an ninh đang/bị đe dọa; cần kích hoạt luồng ứng phó dù chưa xác minh xong | Tài khoản quản trị đăng nhập từ nguồn bất thường, sau đó truy cập nhiều phân đoạn trái thông lệ |
| **Security incident đã xác nhận (confirmed)** | Đã đủ bằng chứng cho thấy có xâm nhập, thao tác trái phép, tấn công gây ảnh hưởng hoặc vi phạm chính sách an ninh | Nhật ký xác nhận tài khoản bị chiếm đã truy xuất dữ liệu không được phép |

Một sự cố có thể đồng thời thuộc cả hai loại: DDoS làm dịch vụ không khả dụng vừa là vấn đề vận hành, vừa là security incident. Việc mở luồng ứng phó an ninh **không yêu cầu** phải chứng minh đầy đủ danh tính kẻ tấn công hoặc thiệt hại; phân loại nghi ngờ cho phép điều tra kịp thời. Cách gọi và ngưỡng chính thức phải tuân theo quy định của tổ chức.

### Hai câu hỏi quyết định

1. **Có dấu hiệu đáng tin cậy của hành vi trái phép, ác ý hoặc vi phạm kiểm soát an ninh không?** Ví dụ: xác thực không được phép thành công, mã độc giao tiếp ra ngoài, DNS bị sửa trái thẩm quyền, hệ thống bị tấn công làm gián đoạn.
2. **Hành vi đó đã hoặc có khả năng đáng kể ảnh hưởng đến tính bí mật (Confidentiality), toàn vẹn (Integrity), sẵn sàng (Availability), hay chính sách bảo vệ hệ thống và dữ liệu không?**

Nếu câu trả lời cho cả hai có cơ sở, cần **nâng cấp để đội an ninh tiếp nhận**. Nếu hậu quả có thể rất lớn và bằng chứng ban đầu đủ đáng tin, có thể kích hoạt ứng phó dưới nhãn *suspected security incident* ngay cả khi chưa có bằng chứng kết luận.

## 3. Tiêu chí kích hoạt chuyển thành security incident

Những nhóm dưới đây là **tín hiệu kích hoạt**. Mức ưu tiên phụ thuộc vào độ tin cậy, phạm vi, loại tài sản, tính chủ động của tấn công và hậu quả dự kiến.

| Nhóm tiêu chí | Bằng chứng hoặc mẫu hành vi cần quan sát | Hướng xử lý |
|---|---|---|
| **Truy cập hoặc điều khiển trái phép** | Đăng nhập thành công bằng tài khoản bị lộ; truy cập trái quyền; thay đổi ACL, firewall, route, VPN, IAM ngoài quy trình đã phê duyệt | Mở security incident khi đã xác minh trái phép; mở *suspected* ngay nếu chuỗi dấu hiệu mạnh |
| **Mất bí mật dữ liệu / nghi rò rỉ** | Dữ liệu nhạy cảm được gửi tới đích không được phép; tải xuống bất thường sau truy cập trái quyền; kênh DNS/HTTPS đáng ngờ kết hợp bằng chứng từ máy chủ | Escalate khẩn nếu dữ liệu quan trọng đang rời hệ thống; đánh giá phạm vi và lưu bằng chứng |
| **Mất toàn vẹn** | DNS record, route/BGP, cấu hình bảo mật, log hoặc mã ứng dụng bị sửa ngoài thẩm quyền; kết quả phân giải bị đầu độc | Điều tra dấu vết thay đổi, xác định phạm vi và nguồn thao tác |
| **Tấn công tính sẵn sàng** | Flood traffic có đặc điểm DDoS, xóa phá dữ liệu, ransomware, phá hoại tài nguyên mạng hoặc cloud | Kích hoạt phối hợp giữa ứng phó an ninh và vận hành để bảo vệ dịch vụ |
| **Khai thác đang diễn ra** | Bằng chứng thực thi payload, khai thác lỗ hổng thành công, web shell, C2 beacon, di chuyển ngang hoặc leo thang đặc quyền | Escalate kể cả khi chưa thấy dữ liệu bị đánh cắp |
| **Vô hiệu hóa kiểm soát bảo vệ** | Tự ý tắt EDR/IDS, xóa log, tắt MFA, mở rule cho phép toàn bộ, vô hiệu hóa phân đoạn trong chuỗi hoạt động khả nghi | Xem như dấu hiệu xâm nhập có trọng số cao; kiểm tra thay đổi có phê duyệt hay không |
| **Tài sản hoặc đặc quyền trọng yếu** | Domain controller, hệ thống định danh, DNS lõi, gateway, VPN, PKI, nền tảng cloud hoặc hệ thống chứa dữ liệu nhạy cảm có dấu hiệu bị xâm phạm | Hạ ngưỡng chuyển xử lý an ninh vì phạm vi ảnh hưởng lớn và khả năng lan truyền nhanh |
| **Vi phạm chính sách bảo mật có bằng chứng** | Thiết bị hoặc tài khoản cố ý vượt phân đoạn bị cấm; chuyển bí mật qua kênh không được phép; hành vi nội gián được xác minh | Kích hoạt luồng an ninh theo chính sách nội bộ và phân quyền điều tra |

**Nguyên tắc quan trọng:** Chỉ số lưu lượng tăng, port scan bị chặn hoặc một chữ ký IDS khớp đơn lẻ **chưa đủ để kết luận** đã bị xâm nhập. Chúng có thể đủ để mở *triage case*. Ngược lại, bằng chứng mã độc đang mã hóa dữ liệu hoặc tài khoản bị chiếm đang thao tác trái phép đủ để mở incident mà không cần chờ tương quan nhiều nguồn.

### Tiêu chí để *chưa* mở security incident

Các hiện tượng sau thường cần xử lý theo vận hành hoặc theo dõi thêm, trừ khi xuất hiện bằng chứng tấn công:

- Đường truyền đứt do thiết bị hỏng; dịch vụ 5xx tăng sau bản phát hành được xác minh lỗi phần mềm.
- Firewall chặn số lượng lớn kết nối không được phép nhưng **không có dấu hiệu vượt qua kiểm soát**; lưu lại và tiếp tục giám sát xu hướng.
- Nhiều lần đăng nhập sai do mật khẩu ứng dụng hết hạn; cần kiểm tra nguồn để phân biệt với brute force.
- Công cụ quét lỗ hổng được phê duyệt gây nhiều cảnh báo; xác minh lịch quét và IP nguồn.
- Phát hiện lỗ hổng nghiêm trọng nhưng **chưa có tín hiệu khai thác**: xử lý theo quản lý lỗ hổng, đồng thời tăng giám sát và có thể mở triage nếu bối cảnh đe dọa cao.

Không coi các mục trên là danh sách loại trừ tuyệt đối. Một DDoS có thể bắt đầu giống lưu lượng người dùng tăng đột biến; mất mạng có thể là hậu quả của việc sửa route trái phép.

## 4. Hai trục đánh giá độc lập: độ tin cậy và tác động

**Độ tin cậy (confidence)** trả lời “chúng ta có bao nhiêu cơ sở để nhận định đây là hành vi an ninh?”. **Tác động (impact)** trả lời “nếu đúng, hệ thống và dữ liệu chịu hậu quả ở mức nào?”. Không dùng mức độ nghiêm trọng của một chữ ký IDS để thay thế cho mức độ thiệt hại của tổ chức.

| Độ tin cậy | Dấu hiệu đặc trưng | Cách ghi nhận |
|---|---|---|
| **Thấp** | Một alert chưa được kiểm chứng, mẫu lưu lượng có thể do hoạt động hợp lệ | Event/alert; tiếp tục thu thập thông tin |
| **Trung bình** | Có tương quan nhiều tín hiệu, hành vi ngoài baseline, chưa xác minh nguyên nhân hợp lệ | Security triage, hoặc *suspected incident* nếu rủi ro cao |
| **Cao** | Có dấu vết xác thực, endpoint, ứng dụng, lưu lượng hoặc thay đổi cấu hình củng cố giả thuyết tấn công | *Suspected incident* và thông báo đầu mối ứng phó |
| **Đã xác nhận** | Có bằng chứng đủ rõ về hoạt động trái phép/ác ý hoặc vi phạm chính sách | *Confirmed incident* |

Tác động cần xét đồng thời: độ nhạy dữ liệu; tài sản sản xuất/định danh/hạ tầng lõi; số máy và người dùng bị ảnh hưởng; khả năng lan sang vùng khác; mức gián đoạn; khả năng khôi phục; nghĩa vụ thông báo; nguy cơ mất kiểm soát kéo dài.

Có thể dùng ma trận hướng dẫn sau, sau đó đối chiếu với quy định nội bộ:

| Bằng chứng và tác động | Tác động hạn chế | Tác động đáng kể | Tác động nghiêm trọng / có thể lan rộng |
|---|---|---|---|
| **Tín hiệu yếu, chưa tương quan** | Ghi event và theo dõi | Mở triage | Mở triage khẩn, báo đầu mối an ninh |
| **Nghi ngờ có cơ sở** | Triage có thời hạn | Mở suspected incident | Mở suspected incident khẩn cấp |
| **Hành vi trái phép đã xác nhận** | Mở incident | Mở incident, điều phối nhiều nhóm | Mở incident nghiêm trọng và kích hoạt chỉ huy sự cố |

**Ví dụ:** Một flow egress lạ từ máy thử nghiệm, không có dấu hiệu dữ liệu nhạy cảm, có thể bắt đầu là triage. Cùng tín hiệu đó từ hệ thống quản lý định danh ngay sau đăng nhập trái phép sẽ cần mở suspected incident khẩn cấp. Cùng mức confidence nhưng hậu quả tiềm ẩn khác nhau dẫn đến cách ứng phó khác nhau.

### Mức ưu tiên mẫu, không phải ngưỡng bắt buộc

| Mức mẫu | Tình huống đặc trưng | Điều phối ban đầu |
|---|---|---|
| **P0 – Khủng hoảng** | Ransomware lan nhiều phân đoạn; đánh cắp dữ liệu nhạy cảm đang diễn ra quy mô lớn; hệ thống định danh lõi mất kiểm soát | Kích hoạt ngay chỉ huy sự cố, SOC/IR, vận hành, chủ hệ thống và đầu mối pháp lý khi liên quan |
| **P1 – Cao** | Xâm nhập thành công hệ thống trọng yếu; C2 hoạt động; DDoS gây gián đoạn lớn | Đội ứng phó tiếp nhận khẩn, cô lập theo đánh giá rủi ro |
| **P2 – Trung bình** | Xâm nhập được xác nhận phạm vi hẹp, chưa thấy lan rộng hoặc ảnh hưởng dữ liệu quan trọng | Chỉ định owner, điều tra phạm vi, ngăn chặn có kiểm soát |
| **P3 – Thấp** | Vi phạm an ninh giới hạn, đã ngăn chặn và ít tác động | Ghi nhận incident, xử lý và giám sát cải thiện |

Mã mức độ và thời hạn phản hồi thực tế phải được tổ chức ban hành; bảng này chỉ minh họa cách ra quyết định. **Mức độ ưu tiên có thể tăng hoặc giảm** khi phát hiện tài sản bị ảnh hưởng mới, bằng chứng mới hoặc khi giả thuyết ban đầu được bác bỏ. Ghi lại lý do thay đổi.

## 5. Quy trình quyết định ở điểm chuyển giao

~~~mermaid
flowchart TD
    A["Nhận event, alert hoặc sự cố mạng"] --> B["Xác minh nguồn, thời gian và bối cảnh thay đổi hợp lệ"]
    B --> C{"Có dấu hiệu trái phép hoặc tấn công đáng tin?"}
    C -->|Không| D["Xử lý vận hành / lưu alert / theo dõi"]
    C -->|Có hoặc chưa rõ| E["Tương quan log, đánh giá tài sản và tác động"]
    E --> F{"Đã xác nhận hành vi trái phép?"}
    F -->|Có| G["Mở confirmed security incident"]
    F -->|Chưa| H{"Nghi ngờ có cơ sở và hậu quả đáng kể?"}
    H -->|Có| I["Mở suspected security incident"]
    H -->|Chưa| J["Mở security triage có owner và hạn kiểm tra"]
    G --> K["Thông báo, bảo toàn bằng chứng, ứng phó"]
    I --> K
    J --> L["Bổ sung bằng chứng, đánh giá lại"]
    L --> E
    K --> M["Cập nhật mức độ, phạm vi, quyết định xử lý"]
~~~

Thực hiện theo thứ tự:

1. **Thu nhận tín hiệu:** Ghi thời gian phát hiện, nguồn cảnh báo, IP/hostname, tài khoản, tài sản, phạm vi, loại dịch vụ và người phát hiện. Tách rõ điều quan sát được khỏi suy luận.
2. **Đối chiếu bối cảnh hợp lệ:** Kiểm tra thay đổi được phê duyệt, lịch kiểm thử bảo mật, bảo trì, quét định kỳ, thay đổi tuyến/VPN và hệ thống giám sát. Không tự đóng cảnh báo chỉ vì thấy một vé thay đổi có vẻ liên quan.
3. **Tương quan tối thiểu:** Ghép firewall, IDS/IPS, VPN/IdP, DNS, proxy, NetFlow/Zeek, EDR, ứng dụng và cloud audit tùy môi trường. Chỉ sử dụng những nguồn thực sự có sẵn.
4. **Đánh giá tiêu chí kích hoạt:** Xác định hành vi trái phép, chuỗi khai thác, nguy cơ C/I/A, độ nhạy của tài sản và khả năng lan rộng. Phân biệt “được chặn hoàn toàn” với “đã thành công”.
5. **Mở/cập nhật hồ sơ:** Chọn *triage*, *suspected* hoặc *confirmed*; gán mức ưu tiên, người chịu trách nhiệm và thời điểm đánh giá lại. Nếu có nguy cơ khẩn cấp, thông báo và áp dụng biện pháp bảo vệ theo thẩm quyền ngay cả khi điều tra chưa kết thúc.
6. **Chuyển giao và cập nhật:** SOC/IR quyết định điều tra và biện pháp ứng phó; NOC/SRE hỗ trợ hiện trạng mạng, thay đổi routing/firewall, khôi phục dịch vụ. Ghi quyết định, bằng chứng, người phê duyệt và thời gian thực hiện.

Nếu còn thiếu thông tin để kết luận, **không để trường hợp bị treo vô thời hạn**. Giao owner, mốc kiểm tra tiếp theo và điều kiện nâng hoặc hạ phân loại rõ ràng.

## 6. Bằng chứng mạng cần thu thập và giới hạn của chúng

| Nguồn | Có thể trả lời | Không thể tự mình chứng minh |
|---|---|---|
| **Firewall / NAT / flow log** | Ai kết nối tới đâu, cổng nào, được cho phép hay chặn, số byte, thời gian, egress bất thường | Nội dung ứng dụng, ý định, hoặc dữ liệu cụ thể đã bị đánh cắp |
| **IDS/IPS** | Chữ ký hoặc hành vi nào được phát hiện, gói tin liên quan, quy tắc nào chặn | Xâm nhập thành công chỉ từ một chữ ký khớp |
| **DNS resolver log** | Truy vấn tên miền, tần suất, tên miền hiếm hoặc chuỗi truy vấn có cấu trúc bất thường | DNS tunneling chắc chắn nếu chưa tương quan thêm |
| **VPN / IAM / IdP** | Đăng nhập từ đâu, kết quả MFA, tài khoản, thiết bị, session, quyền sử dụng | Người thực sự cầm thiết bị nếu thông tin nhận dạng bị đánh cắp |
| **PCAP / TLS metadata** | Chi tiết phiên, đặc điểm giao thức, handshake, dấu hiệu payload khi có quyền xem | Toàn bộ nội dung của phiên đã mã hóa chỉ từ TLS handshake |
| **Endpoint / EDR / server log** | Tiến trình sinh kết nối, thực thi mã, thay đổi file, truy cập dữ liệu, tài khoản | Toàn cảnh mạng nếu thiết bị ghi thiếu hoặc đã bị can thiệp |
| **Cloud audit / VPC flow / control plane** | Thay đổi security group, IAM, route, tài nguyên public, hoạt động API | Nội dung ứng dụng bên trong phiên chỉ từ VPC flow |

Khi liên kết nhiều nguồn, đặc biệt chú ý:

- **Thời gian:** ghi múi giờ, đồng bộ đồng hồ, sai lệch timestamp, khoảng thời gian tìm kiếm và thời điểm bắt đầu/kết thúc.
- **Định danh:** NAT, proxy, IP động, DHCP lease, VPN address pool, container/pod và thay đổi máy chủ có thể làm sai phép gán một IP cho một người/máy.
- **Hướng lưu lượng:** phân biệt inbound, east-west, outbound; xác định nơi quan sát log và liệu có điểm mù TLS, overlay hoặc cloud.
- **Ý nghĩa của log:** HTTP 200 hay TCP established chứng minh kết nối/thao tác tương ứng, **không tự chứng minh** dữ liệu nhạy cảm đã rò rỉ. Số byte truyền lớn cũng chỉ là manh mối.
- **Tính toàn vẹn:** lưu bản gốc hoặc bản xuất có metadata, thời gian thu thập và người thực hiện; hạn chế thao tác làm mất vòng log hoặc mất chứng cứ.

Ví dụ dữ liệu nhật ký để mở triage (địa chỉ IP thuộc dải dành cho tài liệu, không phải IOC thật):

~~~json
{
  "observed_at": "2026-11-28T09:14:30+07:00",
  "source": "vpn-auth",
  "account": "ops-admin",
  "remote_ip": "203.0.113.24",
  "result": "success",
  "mfa_result": "success",
  "asset_role": "network-admin",
  "anomaly": "new_device_and_unusual_location"
}
~~~

Bản ghi này **chưa chứng minh tài khoản bị chiếm**: có thể là chuyến công tác hoặc thiết bị mới được cấp. Nếu sau đăng nhập xuất hiện các thay đổi firewall không có phê duyệt và truy cập vào phân đoạn nhạy cảm trái quyền, chuỗi bằng chứng đủ để mở *suspected incident*, rồi xác minh nguồn thao tác. MFA thành công không loại trừ hành vi dùng phiên hoặc tài khoản bị xâm phạm.

## 7. Tình huống thực tế: khi nào nâng cấp?

### Tình huống A — Quét cổng bị chặn tại biên

Firewall ghi hàng nghìn gói đến các cổng không mở từ nhiều IP Internet. IDS phát cảnh báo quét cổng. Không thấy kết nối thành công, không có thay đổi dịch vụ hoặc dấu vết khai thác trên đích.

- **Phân loại ban đầu:** alert/security triage theo ngưỡng nội bộ; chưa kết luận security incident thành công.
- **Nâng cấp nếu:** phát hiện đường truy cập vượt kiểm soát, khai thác thành công, tín hiệu tương quan trên máy đích, hoặc lượng traffic làm cạn tài nguyên thành DDoS.
- **Việc cần làm:** xác nhận rule thực tế, rà các kết nối được phép và theo dõi nguồn/đích bị nhắm tới.

### Tình huống B — Tài khoản VPN đáng nghi và di chuyển ngang

Một tài khoản quản trị VPN đăng nhập từ thiết bị chưa biết. Trong cùng khoảng thời gian, tài khoản truy cập nhiều máy ở VLAN quản trị mà trước đây không truy cập; hai thiết bị ghi nhận phiên điều khiển từ xa ngoài lịch bảo trì. Chủ tài khoản xác nhận không thực hiện.

- **Phân loại:** suspected security incident ngay; khi xác minh hành động trái phép thì chuyển confirmed.
- **Lý do:** bằng chứng tương quan giữa danh tính, mạng nội bộ và xác nhận từ chủ tài khoản; có nguy cơ lan rộng và mất quyền kiểm soát.
- **Việc cần làm:** giữ log VPN/IdP, thông tin NAT/DHCP, firewall east-west, EDR; phối hợp ứng phó để thu hồi phiên/quyền và giới hạn di chuyển ngang theo runbook.

### Tình huống C — Nghi truyền dữ liệu qua DNS

DNS log cho thấy máy chủ ứng dụng truy vấn liên tục các subdomain dài, thay đổi theo chu kỳ của một tên miền lạ. Flow log cho thấy lưu lượng ra ngoài tăng; máy chủ chứa dữ liệu nhạy cảm. Chưa xác minh được tiến trình tạo truy vấn và đích thực sự.

- **Phân loại:** security triage khẩn hoặc suspected incident nếu xuất hiện thêm dấu hiệu đáng tin về C2/exfiltration và hậu quả lớn.
- **Lý do:** mẫu DNS đáng nghi là tín hiệu mạnh để điều tra nhưng không tự chứng minh rò rỉ dữ liệu.
- **Việc cần làm:** kiểm tra resolver, thông tin đăng ký/tính hợp lệ của domain, tiến trình tại máy, payload nếu có thẩm quyền quan sát và dấu vết truy cập dữ liệu; bảo toàn dữ liệu trước khi chặn theo quy trình.

### Tình huống D — DDoS hay đột biến tải hợp lệ?

Một cổng ứng dụng tăng gấp nhiều lần lượng kết nối, latency và lỗi 503 tăng. Cùng lúc có chiến dịch quảng cáo lớn. Flow và reverse proxy cho thấy một nhóm nguồn gửi request lặp lại nhằm tiêu hao tài nguyên, độc lập với truy cập người dùng.

- **Phân loại:** mở operational incident để khôi phục dịch vụ ngay; khi có cơ sở về lưu lượng tấn công, mở thêm security incident.
- **Lý do:** **mất sẵn sàng** có thể do lỗi năng lực hoặc hành vi tấn công; cần đối chiếu hành vi, nguồn, đặc điểm request, thử thách chống bot và thay đổi cấu hình.
- **Việc cần làm:** NOC/SRE phối hợp SOC đánh giá chống DDoS, rate limiting, WAF/CDN; đo ảnh hưởng đến người dùng và ghi lại thay đổi có rủi ro.

### Tình huống E — Thay đổi cấu hình cloud ngoài phê duyệt

Cloud audit ghi một access key thay đổi security group để mở cổng quản trị ra Internet và tắt ghi log. Không có change ticket tương ứng. Kế đó xuất hiện phiên đăng nhập quản trị từ nguồn chưa từng thấy.

- **Phân loại:** suspected incident mức ưu tiên cao; xác nhận khi làm rõ chủ thể và tính trái phép.
- **Lý do:** chuỗi thay đổi làm suy yếu kiểm soát rồi sử dụng đường truy cập mới có thể chỉ ra xâm nhập, dù chưa có gián đoạn.
- **Việc cần làm:** giữ cloud audit/control-plane log, lịch sử key, cấu hình trước/sau, phiên quản trị; phối hợp vô hiệu hóa bí mật bị lộ và khôi phục kiểm soát theo thứ tự an toàn.

### Tình huống F — Phát hiện lỗ hổng nghiêm trọng

Máy chủ VPN được công bố có lỗ hổng nghiêm trọng. Quét nội bộ xác nhận phiên bản bị ảnh hưởng; chưa có log thể hiện khai thác hay truy cập lạ.

- **Phân loại:** quản lý lỗ hổng ưu tiên cao, tăng giám sát và triển khai giảm thiểu; không mặc nhiên ghi là confirmed security incident.
- **Nâng cấp nếu:** có exploit attempt đáng tin cần điều tra, dấu hiệu thực thi thành công, tài khoản/phiên bị chiếm hoặc bằng chứng kiểm soát bị vượt qua.
- **Lưu ý:** quy trình tổ chức có thể yêu cầu mở *suspected incident* sớm với tài sản cực kỳ trọng yếu, ngay cả khi xác nhận còn khó.

## 8. Nội dung tối thiểu khi mở hoặc nâng cấp hồ sơ

Một bản ghi chuyển giao nên đủ để người tiếp nhận hành động ngay, đồng thời phân biệt dữ kiện và giả thuyết.

~~~yaml
incident_id: SEC-EXAMPLE-014
detected_at: "2026-11-28T09:14:30+07:00"
reported_at: "2026-11-28T09:21:00+07:00"
state: suspected                # triage | suspected | confirmed | closed
priority: P1                    # mức minh họa; theo chuẩn nội bộ
confidence: high                # low | medium | high | confirmed
affected_assets:
  - "vpn-gateway-prod"
  - "management-vlan"
impact_hypothesis: "Nguy cơ chiếm tài khoản quản trị và di chuyển ngang"
observed_facts:
  - "VPN login thành công từ thiết bị chưa nhận diện"
  - "Có phiên truy cập chéo đến nhiều máy quản trị"
  - "Chủ tài khoản phủ nhận hoạt động trong khung giờ này"
evidence_refs:
  - "SIEM case 12345; bản log gốc trong kho chứng cứ"
open_questions:
  - "Tài khoản hoặc phiên đã bị chiếm theo cách nào?"
  - "Có thay đổi cấu hình hoặc truy cập dữ liệu trái phép không?"
decision: "Mở suspected security incident và thông báo SOC/IR"
decision_owner: "Incident commander hoặc đầu mối trực an ninh được ủy quyền"
next_review_at: "Theo SLA ứng phó nội bộ"
~~~

Nhật ký quyết định cần ghi rõ **ai** nâng cấp, **lúc nào**, **dựa trên bằng chứng nào**, **đã thông báo ai**, **hành động khẩn cấp nào** và **lý do điều chỉnh mức độ**. Liên kết chứng cứ tới kho lưu trữ có kiểm soát truy cập; trong hồ sơ chia sẻ rộng chỉ nên ghi tham chiếu thay vì dán token, bí mật hay dữ liệu cá nhân.

### Phân công vai trò khi nâng cấp

- **NOC/SRE/Vận hành:** phát hiện mất dịch vụ, cung cấp topology và thay đổi mạng, hỗ trợ giảm thiểu tác động và khôi phục.
- **SOC/Đội phân tích an ninh:** xác minh tín hiệu, đối chiếu IOC/TTP, đề xuất mở suspected/confirmed incident và mức độ ưu tiên.
- **Đội ứng phó sự cố/Incident commander:** chịu trách nhiệm điều phối ứng phó, quyết định cô lập, điều tra, khôi phục và kết thúc theo thẩm quyền.
- **Chủ hệ thống, IAM, cloud, pháp lý/bảo vệ dữ liệu:** tham gia tương ứng khi liên quan quyền truy cập, hệ thống trọng yếu, dữ liệu hoặc nghĩa vụ thông báo.

Những thay đổi có thể cắt kết nối hoặc hủy chứng cứ (xóa VM, reset máy, tắt log, thu hồi diện rộng) cần cân nhắc ảnh hưởng sản xuất và tuân theo thẩm quyền ứng phó. Trong trường hợp đang bị tấn công gây thiệt hại tức thời, kích hoạt biện pháp giảm thiểu khẩn cấp theo runbook đã phê duyệt, ghi lại đầy đủ thời gian và người thực hiện.

## 9. Các lỗi phân loại thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Coi mọi alert IDS là incident đã xác nhận | Quá tải, mất khả năng ưu tiên | Tách alert, triage, suspected và confirmed; kiểm tra dấu hiệu thành công |
| Chỉ báo incident sau khi có bằng chứng mất dữ liệu | Bỏ lỡ thời gian ngăn chặn tấn công | Dùng nhãn suspected khi có cơ sở và tác động có thể lớn |
| Đồng nhất severity của công cụ với mức ưu tiên ứng phó | Tài sản ít quan trọng lấn át hệ thống trọng yếu | Xét tài sản, hậu quả, phạm vi, độ tin cậy và tốc độ lan |
| Tin rằng firewall chặn hoặc MFA thành công là an toàn tuyệt đối | Bỏ sót đường khác, phiên bị chiếm hoặc truy cập hợp lệ bị lạm dụng | Tương quan nhiều nguồn và kiểm tra chuỗi hoạt động |
| Không kiểm tra thay đổi hợp lệ hoặc lỗi đồng hồ | False positive, gán nhầm IP/người dùng | Đối chiếu change ticket, NAT/DHCP, mốc thời gian, múi giờ |
| Chờ xác minh hoàn toàn rồi mới thông báo đội an ninh | Mất cơ hội ngăn chặn sớm | Thông báo khi có nghi ngờ đáng tin và hậu quả nghiêm trọng |
| Đóng case vì chưa đủ log, không có owner | Sự kiện bị quên dù điều kiện nguy hiểm còn tồn tại | Gán người xử lý, kỳ hạn bổ sung chứng cứ và mốc xem xét lại |

## 10. Checklist thực hành khi trực ca

Trước khi quyết định giữ ở mức cảnh báo hay nâng thành security incident, tự hỏi:

- [ ] Đã xác minh nguồn cảnh báo và thời gian, có bối cảnh cấu hình/bảo trì hợp lệ chưa?
- [ ] Có dấu hiệu truy cập trái phép, khai thác thành công, mã độc, rò rỉ, phá hoại hoặc thay đổi kiểm soát không?
- [ ] Đã phân biệt nỗ lực **bị chặn** với hoạt động **đã thành công** chưa?
- [ ] Có tài sản trọng yếu, dữ liệu nhạy cảm, tài khoản đặc quyền hoặc nhiều phân đoạn bị ảnh hưởng không?
- [ ] Độ tin cậy của nhận định và mức độ tác động đã được đánh giá riêng chưa?
- [ ] Nếu nghi ngờ có cơ sở và hậu quả lớn, đã thông báo đầu mối ứng phó để mở *suspected incident* chưa?
- [ ] Đã ghi log gốc/tham chiếu chứng cứ, mốc thời gian, người ra quyết định và hành động đang thực hiện chưa?
- [ ] Có người phụ trách, mốc đánh giá lại và điều kiện nâng/hạ mức phân loại chưa?

**Quy tắc ứng dụng:** Nâng cấp thành security incident khi bằng chứng cho thấy hành vi an ninh trái phép/ác ý hoặc khi nghi ngờ đủ đáng tin kết hợp với hậu quả có thể đáng kể cần kích hoạt ứng phó ngay. Tiếp tục triage khi chứng cứ chưa đủ, nhưng phải có người phụ trách và hạn đánh giá lại. Chất lượng quyết định nằm ở **bằng chứng được ghi nhận, đánh giá rủi ro và khả năng điều chỉnh theo thông tin mới**, không nằm ở số lượng cảnh báo.

## 11. Câu hỏi tự kiểm tra

1. IDS báo khai thác nghiêm trọng nhưng firewall ghi nhận tất cả kết nối đều bị chặn. Bạn cần bổ sung bằng chứng gì trước khi phân loại là *confirmed incident*?
2. Một đăng nhập VPN thành công với MFA từ thiết bị lạ có đủ để kết luận tài khoản bị chiếm không? Những tín hiệu nào khiến vụ việc phải được mở *suspected incident* ngay?
3. Vì sao hai sự kiện cùng độ tin cậy lại có thể được giao P1 và P3 khác nhau?
4. Khi phát hiện luồng DNS bất thường từ máy chủ chứa dữ liệu nhạy cảm, vì sao không thể kết luận “đã rò rỉ dữ liệu” chỉ dựa vào flow log?
5. Một sự cố routing làm mất dịch vụ 40 phút. Những bằng chứng nào cho phép chuyển từ sự cố vận hành sang security incident?

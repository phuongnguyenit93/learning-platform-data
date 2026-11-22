# Phân biệt tính sẵn sàng, phân bố địa lý và chủ quyền dữ liệu

Khi thiết kế kiến trúc cloud, ba câu hỏi thường xuất hiện cùng lúc:

1. **Hệ thống có tiếp tục phục vụ khi một thành phần hỏng không?** Đây là câu hỏi về **tính sẵn sàng** (*availability*).
2. **Người dùng, ứng dụng và dữ liệu cần hiện diện ở những vị trí địa lý nào?** Đây là câu hỏi về **phân bố địa lý** (*geographic distribution*).
3. **Dữ liệu chịu quyền tài phán và sự kiểm soát của ai; được phép lưu, xử lý và truy cập từ đâu?** Đây là câu hỏi về **chủ quyền dữ liệu** (*data sovereignty*).

Ba khái niệm có liên quan nhưng **không thay thế nhau**. Một hệ thống chạy ở hai vùng sẵn sàng trong cùng region có thể chịu lỗi hạ tầng tốt mà không phục vụ người dùng ở hai châu lục với độ trễ thấp. Một hệ thống có CDN toàn cầu có thể truy cập nhanh ở nhiều quốc gia nhưng vẫn chỉ có một cơ sở dữ liệu làm điểm lỗi đơn. Một hệ thống lưu dữ liệu trong một quốc gia chưa chắc đáp ứng đầy đủ yêu cầu về người được quyền truy cập, quyền tài phán, bản sao lưu, bản ghi log hoặc nhà thầu vận hành.

Bài học thuộc chương **Mô hình triển khai** của module **CLOUD_ARCHITECTURE**. Mục tiêu là lựa chọn mạng, compute, dữ liệu và cách triển khai dựa trên yêu cầu nghiệp vụ, đồng thời phân tích đánh đổi giữa độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

- Định nghĩa và phân biệt availability, geographic distribution, data residency, data localization và data sovereignty.
- Xác định **failure domain** (phạm vi cùng có thể hỏng), region, availability zone và các lớp hạ tầng cần phân tán.
- Chuyển yêu cầu nghiệp vụ thành SLI/SLO, RTO/RPO, yêu cầu độ trễ và ràng buộc vị trí/quyền truy cập dữ liệu.
- So sánh triển khai single-zone, multi-zone, multi-region, active-passive, active-active, hybrid và multi-cloud.
- Nhận diện các đường đi dữ liệu ít được chú ý như log, backup, cache, telemetry, hỗ trợ vận hành và hệ thống đối tác.
- Đề xuất thiết kế có thể kiểm thử, truy vết trách nhiệm và chứng minh được các ràng buộc dữ liệu.

## 2. Bản đồ khái niệm: ba trục thiết kế độc lập

| Trục | Câu hỏi chính | Thước đo hoặc bằng chứng | Ví dụ biện pháp |
|---|---|---|---|
| **Tính sẵn sàng** | Khi lỗi xảy ra, dịch vụ còn đáp ứng không và phục hồi nhanh thế nào? | Availability SLI/SLO; thời gian gián đoạn; RTO/RPO; kết quả diễn tập | Dự phòng, loại bỏ điểm lỗi đơn, health check, failover, backup và restore |
| **Phân bố địa lý** | Tài nguyên và lưu lượng được bố trí ở đâu để phục vụ người dùng và chịu lỗi? | Độ trễ theo khu vực, throughput, khoảng cách mạng, vị trí replica, lỗi theo vùng | Multi-region, CDN/edge, routing gần người dùng, replication, phân chia dữ liệu |
| **Chủ quyền dữ liệu** | Những ai và những hệ thống nào có thể kiểm soát, truy cập hoặc xử lý dữ liệu theo luật và hợp đồng áp dụng? | Data inventory; đường đi dữ liệu; địa điểm lưu/xử lý; hợp đồng; quyền operator; nhật ký truy cập; bằng chứng kiểm toán | Phân loại dữ liệu, ràng buộc vị trí, IAM, kiểm soát khóa, kiểm soát bên thứ ba, audit |

Một thiết kế có thể đạt yêu cầu của một trục nhưng không đạt hai trục còn lại. Ví dụ, sao chép toàn bộ cơ sở dữ liệu sang region nước ngoài có thể cải thiện khả năng khôi phục khi mất một region, nhưng làm phát sinh đường truyền dữ liệu xuyên biên giới cần được đánh giá. Ngược lại, giữ mọi dữ liệu ở một region có thể đơn giản hóa quản trị vị trí nhưng tạo rủi ro gián đoạn nếu region đó không sẵn sàng và chưa có phương án khôi phục khả thi.

## 3. Tính sẵn sàng: hệ thống phục vụ được bao lâu?

### 3.1. Availability, reliability và durability không đồng nghĩa

- **Availability (tính sẵn sàng):** khả năng cung cấp một chức năng hoặc dịch vụ khi được yêu cầu. Cần định nghĩa cụ thể “sẵn sàng” là gì: trang web tải được, API trả kết quả đúng, hay người dùng thực sự hoàn tất giao dịch.
- **Reliability (độ tin cậy):** khả năng hệ thống duy trì hành vi đúng theo yêu cầu trong một khoảng thời gian, bao gồm xử lý lỗi, phục hồi và duy trì chất lượng.
- **Durability (độ bền dữ liệu):** khả năng bảo toàn dữ liệu đã ghi hợp lệ qua thời gian. Một dịch vụ lưu trữ có durability cao vẫn có thể tạm thời không truy cập được; một API có uptime cao vẫn có thể làm mất dữ liệu khi thiết kế ghi sai.

Ví dụ: trang tìm kiếm đặt phòng vẫn mở được khi cơ sở dữ liệu thanh toán mất kết nối. Nếu người dùng không thể hoàn tất đặt phòng, việc chỉ đo phản hồi HTTP 200 của trang chủ sẽ khiến SLI che giấu lỗi nghiệp vụ.

### 3.2. SLI, SLO, SLA, RTO và RPO

| Thuật ngữ | Ý nghĩa | Cách áp dụng |
|---|---|---|
| **SLI – Service Level Indicator** | Chỉ số đo chất lượng dịch vụ đã định nghĩa | Tỷ lệ yêu cầu đặt phòng hợp lệ được xử lý thành công dưới ngưỡng độ trễ |
| **SLO – Service Level Objective** | Mục tiêu nội bộ cho SLI trên khoảng thời gian cụ thể | Ví dụ đặt mục tiêu 99,9% yêu cầu hợp lệ thành công trong cửa sổ 30 ngày |
| **SLA – Service Level Agreement** | Cam kết dịch vụ theo hợp đồng, kèm điều kiện/biện pháp xử lý vi phạm | Đọc rõ phạm vi, cách tính, loại trừ và quyền lợi khi CSP không đạt cam kết |
| **RTO – Recovery Time Objective** | Thời gian tối đa mục tiêu để phục hồi sau một sự cố được xác định | Ví dụ khôi phục chức năng đặt phòng trong 60 phút |
| **RPO – Recovery Point Objective** | Độ lùi dữ liệu tối đa chấp nhận được khi phục hồi | Ví dụ chấp nhận mất tối đa 5 phút dữ liệu đã ghi trước sự cố |

Trong cách đo đơn giản, có thể tính:

~~~text
Availability = Thời gian dịch vụ đạt điều kiện SLI / Tổng thời gian quan sát

RTO = Mục tiêu thời gian phục hồi kể từ mốc sự cố đã quy ước
RPO = Mục tiêu mức độ cũ tối đa của dữ liệu có thể phục hồi
~~~

Các ví dụ SLO, RTO, RPO trong bài là **giả định minh họa**. Không có công nghệ nào tự bảo đảm đạt các con số chỉ vì được quảng bá là highly available. Cần xây dựng phương pháp đo, thống nhất điểm bắt đầu/kết thúc sự cố và diễn tập để xác nhận.

**Phân biệt hai tình huống:** tự động chuyển sang instance dự phòng có thể giúp giảm gián đoạn, nhưng không chắc bảo vệ khỏi xóa nhầm dữ liệu; backup có thể phục hồi dữ liệu bị xóa nhưng không nhất thiết đáp ứng RTO ngắn nếu cần khôi phục và kiểm tra thủ công.

### 3.3. Failure domain và dự phòng ở đúng cấp

Một *failure domain* là tập hợp tài nguyên có thể cùng bị ảnh hưởng bởi một sự cố chung, chẳng hạn một tiến trình, một máy ảo, một node, một rack, một availability zone, một region hoặc một dịch vụ điều khiển chung. Tên gọi và mức độc lập của zone/region tùy từng CSP.

| Cấp triển khai | Loại lỗi có thể chịu được nếu thiết kế đúng | Giới hạn điển hình |
|---|---|---|
| Nhiều instance trên **một node** | Lỗi một tiến trình ứng dụng | Không chịu được lỗi node |
| Nhiều node trong **một zone** | Lỗi một node | Zone có thể là điểm lỗi chung |
| Nhiều zone trong **một region** | Lỗi một zone theo phạm vi dịch vụ và kiến trúc | Sự cố toàn region hoặc phụ thuộc dùng chung vẫn có thể làm ngừng dịch vụ |
| Nhiều region | Có thể chịu sự cố một region nếu dữ liệu, routing và dependency hỗ trợ | Chi phí cao hơn; quản lý trạng thái/nhất quán, độ trễ, failover và ràng buộc dữ liệu phức tạp hơn |
| Nhiều nhà cung cấp | Có thể giảm một số rủi ro phụ thuộc CSP | Không loại bỏ lỗi chung từ mã ứng dụng, DNS, danh tính, quy trình hoặc bên thứ ba; vận hành khó hơn |

**Đừng suy luận** “có hai instance” nghĩa là “high availability”: nếu cả hai phụ thuộc một database duy nhất, secret không truy cập được, một vùng mạng chung hoặc một cơ chế triển khai có thể phát tán cấu hình lỗi, hệ thống vẫn có điểm lỗi đơn.

### 3.4. High availability khác disaster recovery

**High availability (HA)** tập trung vào duy trì hoặc nhanh chóng tiếp tục dịch vụ khi những lỗi thường được dự đoán xảy ra. Thiết kế HA có thể sử dụng nhiều instance, load balancing, health check và dữ liệu dự phòng trên các zone.

**Disaster recovery (DR)** tập trung vào phục hồi sau sự cố nghiêm trọng làm mất một phạm vi hạ tầng hoặc gây hỏng trạng thái hệ thống; cần kế hoạch khôi phục ứng dụng, dữ liệu, danh tính, khóa, mạng, DNS, quy trình vận hành và kiểm chứng dữ liệu.

- **Active-passive:** môi trường dự phòng chờ kích hoạt hoặc duy trì một phần năng lực; thường giảm xung đột ghi nhưng thời gian khởi động và chuyển hướng quyết định RTO.
- **Active-active:** nhiều địa điểm đồng thời phục vụ; có thể giúp giảm độ trễ và gián đoạn nhưng cần xử lý trạng thái, giao dịch, ghi đồng thời và lỗi phân đoạn mạng.
- **Backup/restore:** có thể bảo vệ khỏi xóa nhầm hoặc hỏng dữ liệu logic; thời gian phục hồi thường phụ thuộc kích thước dữ liệu, quy trình và giới hạn dịch vụ.

Một bản sao đồng bộ hoặc bất đồng bộ **không tự động là backup**: lệnh xóa sai, dữ liệu bị mã hóa độc hại hoặc lỗi ứng dụng có thể được sao chép theo. Nên cân nhắc bản sao lưu độc lập, bất biến hoặc khả năng phục hồi tại thời điểm (PITR) tùy mục tiêu.

## 4. Phân bố địa lý: đặt compute, dữ liệu và đường đi mạng ở đâu?

### 4.1. Region, availability zone, edge và vị trí người dùng

- **Region:** khu vực địa lý của hạ tầng CSP; thường gồm nhiều zone. Region là đơn vị lựa chọn triển khai của nhiều dịch vụ, nhưng có dịch vụ mang tính toàn cầu và quy tắc lưu dữ liệu khác nhau.
- **Availability zone:** đơn vị hạ tầng được thiết kế để giảm ảnh hưởng của một số lỗi cục bộ trong region; độ độc lập thực tế cần theo tài liệu CSP.
- **Edge / CDN point of presence:** điểm xử lý hoặc lưu cache gần người dùng để giảm độ trễ cho nội dung hoặc chức năng cụ thể. Edge không nhất thiết là nơi dữ liệu nguồn được lưu dài hạn.
- **On-premises / private environment:** tài nguyên do tổ chức hoặc bên thứ ba vận hành tại vị trí riêng; có thể kết nối hybrid với region cloud.

**Phân bố địa lý không nhất thiết là phân bố toàn bộ hệ thống.** Có thể dùng CDN trên nhiều quốc gia cho ảnh công khai trong khi dữ liệu giao dịch và database chỉ ở một region được phép. Hoặc triển khai API ở hai region nhưng dữ liệu ghi tập trung ở một region.

### 4.2. Những mục tiêu khác nhau dẫn đến cách phân bố khác nhau

| Mục tiêu | Hướng triển khai có thể xem xét | Điều phải kiểm chứng |
|---|---|---|
 Giảm độ trễ tải ảnh và tài nguyên tĩnh | CDN với cache tại edge | Chính sách cache, dữ liệu được cache, thời gian vô hiệu hóa, vị trí lưu cache |
 Giảm độ trễ API cho người dùng xa | API tại nhiều region; routing theo khu vực | Vị trí database, độ trễ đi-về, lưu trạng thái phiên, consistency và chi phí egress |
 Chịu lỗi một availability zone | Cân bằng tải + compute và data layer đa zone | Không còn thành phần stateful hoặc mạng dùng chung gây lỗi toàn dịch vụ |
 Chịu lỗi toàn region | DR hoặc hoạt động song song nhiều region | RTO/RPO, failover, dữ liệu cần sao chép, khả năng phục hồi các dependency |
 Bảo vệ dữ liệu theo vị trí được phép | Giới hạn region, replica, backup, log và luồng xử lý theo chính sách | Kiểm toán luồng dữ liệu thực tế; kiểm soát quyền operator và bên thứ ba |

### 4.3. Độ trễ và tính nhất quán của dữ liệu

Các region càng xa nhau, giao tiếp đồng bộ thường chịu thêm độ trễ mạng và rủi ro phân đoạn kết nối. Đặt ứng dụng gần người dùng chưa chắc cải thiện độ trễ giao dịch nếu mọi truy vấn vẫn phải quay về database ở xa.

Hai cách sao chép thường gặp:

- **Đồng bộ:** xác nhận ghi có thể đòi hỏi nhiều nơi cùng xác nhận; có thể giảm rủi ro mất dữ liệu sau failover nhưng làm tăng độ trễ hoặc ảnh hưởng tính sẵn sàng khi mất liên lạc, tùy thuật toán và cấu hình.
- **Bất đồng bộ:** bên nhận nhận dữ liệu sau bên nguồn; thường giảm độ trễ đường ghi nhưng có nguy cơ mất phần ghi chưa kịp sao chép nếu nguồn lỗi. Cần đo replication lag và kiểm thử RPO thực tế.

Với active-active có ghi tại nhiều nơi, còn phải quyết định cách xử lý xung đột: ghi trùng, cập nhật đồng thời, giao dịch thanh toán, bộ đếm tồn kho hay phiên người dùng. Không dùng nguyên tắc “last write wins” một cách mặc định cho dữ liệu đặt chỗ hoặc tài chính nếu nghiệp vụ không chấp nhận mất cập nhật.

### 4.4. Những thành phần toàn cục vẫn có thể là điểm lỗi chung

Một kiến trúc multi-region vẫn cần đánh giá DNS, hệ thống đăng nhập, quản lý khóa, CI/CD, cấu hình, định tuyến toàn cầu, bộ phát hành chứng chỉ, nhà cung cấp thanh toán và các API thứ ba. Hai region dùng chung một thành phần không dự phòng có thể cùng thất bại. Chuyển hướng traffic cũng không tức thì: DNS cache, health check, kết nối tồn tại, session và dữ liệu trạng thái đều ảnh hưởng thời gian hồi phục.

## 5. Chủ quyền dữ liệu: rộng hơn nơi đặt máy chủ

### 5.1. Các thuật ngữ dễ bị trộn lẫn

| Khái niệm | Trọng tâm | Ví dụ |
|---|---|---|
| **Data residency – vị trí cư trú dữ liệu** | Dữ liệu thực tế được lưu hoặc xử lý ở địa điểm địa lý nào | Bản ghi chính nằm trong region được chỉ định |
| **Data localization – bản địa hóa dữ liệu** | Nghĩa vụ hoặc chính sách yêu cầu một số dữ liệu phải lưu/xử lý tại nơi xác định | Quy định áp dụng yêu cầu loại dữ liệu cụ thể được lưu tại một quốc gia |
| **Data sovereignty – chủ quyền dữ liệu** | Quyền tài phán, quyền kiểm soát và khả năng tiếp cận dữ liệu theo pháp luật, hợp đồng và mô hình vận hành | Đánh giá pháp nhân cung cấp, quyền operator, quyền truy cập từ xa, khóa và yêu cầu cung cấp dữ liệu |
| **Data privacy – quyền riêng tư dữ liệu** | Cách thu thập, sử dụng, chia sẻ, bảo vệ dữ liệu cá nhân và quyền của chủ thể dữ liệu | Giới hạn mục đích dùng, thời hạn lưu và phân quyền đọc dữ liệu cá nhân |
| **Data governance – quản trị dữ liệu** | Ai sở hữu dữ liệu, chính sách vòng đời, chất lượng, danh mục và kiểm soát | Chủ sở hữu tập dữ liệu phê duyệt vùng lưu, retention và quy tắc truy cập |

**Data residency là một yếu tố của việc đánh giá chủ quyền, nhưng không đủ để kết luận chủ quyền.** Một cơ sở dữ liệu có bản ghi chính ở đúng region yêu cầu vẫn có thể có log, backup, bản sao phân tích hoặc kênh hỗ trợ truy cập xuyên biên giới. Tương tự, mã hóa at-rest hữu ích nhưng không đủ bảo đảm không ai có thể truy cập dữ liệu khi dịch vụ đang xử lý và giải mã nó.

### 5.2. Cần xem xét yếu tố quyền tài phán và vận hành

Khi doanh nghiệp nói “dữ liệu phải ở trong nước” hoặc “phải bảo đảm chủ quyền dữ liệu”, hãy cụ thể hóa từng yêu cầu:

1. **Loại dữ liệu nào?** Dữ liệu cá nhân, hợp đồng, giao dịch, ảnh, log truy cập, metadata, mã hóa và bản sao đã biến đổi có thể bị áp dụng các quy tắc khác nhau.
2. **“Ở trong nước” nghĩa là gì?** Chỉ lưu trữ lâu dài, cả xử lý, cả backup, hay không cho phép bất kỳ luồng đọc/chia sẻ xuyên biên giới nào?
3. **Ai có quyền truy cập?** Nhà vận hành CSP, nhà thầu hỗ trợ, quản trị viên của doanh nghiệp, hệ thống giám sát và đối tác tích hợp ở vị trí nào?
4. **Ai kiểm soát khóa?** Khóa do CSP quản lý, khóa do khách hàng quản lý, HSM riêng hoặc cơ chế cho phép thu hồi? Ai thực tế có thể yêu cầu dịch vụ giải mã?
5. **Pháp nhân và hợp đồng nào áp dụng?** Đơn vị cung cấp dịch vụ, cơ chế xử lý yêu cầu của cơ quan có thẩm quyền, các nhà xử lý phụ và điều khoản chuyển dữ liệu.
6. **Bằng chứng nào có sẵn?** Báo cáo kiểm toán, phạm vi chứng nhận, hợp đồng, cấu hình vùng, log truy cập, kết quả kiểm thử và sơ đồ dòng dữ liệu.

Các yêu cầu pháp lý thay đổi theo quốc gia, ngành, loại dữ liệu và thời điểm. Khi triển khai thật, cần đối chiếu **quy định hiện hành và hợp đồng cụ thể với bộ phận pháp chế/tuân thủ**. Không suy ra tuân thủ chỉ từ tên region, nhãn “sovereign cloud”, hoặc tuyên bố marketing.

### 5.3. Theo dõi toàn bộ vòng đời và đường đi dữ liệu

Nên ghi nhận các bước **thu thập → truyền → xử lý → lưu trữ → sao chép → sao lưu → quan sát → xuất/chia sẻ → xóa**. Với mỗi bước, trả lời: dữ liệu gì, ở đâu, bên nào xử lý, ai có quyền, được giữ bao lâu và có bằng chứng gì.

Những đường đi thường bị bỏ sót:

- **Backup, snapshot, replica, DR:** nơi lưu bản sao có thể khác nơi lưu bản ghi chính; cần hiểu tính năng sao lưu tự động và quy tắc restore.
- **CDN và cache:** nội dung trả về và một phần metadata có thể được cache ở các địa điểm biên.
- **Log, trace, crash dump, support ticket:** payload, token, thông tin cá nhân hoặc truy vấn có thể xuất hiện trong log và công cụ hỗ trợ bên ngoài.
- **Analytics, monitoring và AI services:** hệ thống phân tích, thông báo, tìm kiếm hoặc suy luận có thể xử lý một bản sao dữ liệu ở địa điểm khác.
- **CI/CD và môi trường thử nghiệm:** dữ liệu production bị sao chép sang môi trường phát triển hoặc máy nhà thầu.
- **Email, thanh toán, bản đồ và đối tác SaaS:** dữ liệu được gửi tới nhà xử lý thứ ba với quyền hạn và vị trí khác nhau.
- **Tài khoản và metadata của control plane:** một số siêu dữ liệu quản trị có phạm vi lưu hoặc xử lý toàn cục, khác với dữ liệu nghiệp vụ.
- **Hỗ trợ truy cập từ xa:** dữ liệu đặt tại một quốc gia không mặc định ngăn người vận hành từ quốc gia khác truy cập.

Nếu CSP chỉ cam kết vị trí lưu của **dữ liệu thuộc một dịch vụ cụ thể**, không tự suy rộng cam kết đó cho mọi log, backup, dịch vụ phân tích hay hệ thống hỗ trợ.

### 5.4. Các biện pháp kiểm soát thường dùng

| Nhóm kiểm soát | Giải pháp tiêu biểu | Giới hạn cần hiểu |
|---|---|---|
 Lựa chọn vùng được phép | Policy giới hạn region, IaC và kiểm tra cấu hình | Có thể không áp dụng cho mọi global service hoặc tài nguyên bên thứ ba |
 Phân loại và tối thiểu hóa dữ liệu | Chỉ gửi thông tin cần thiết, tách dữ liệu nhạy cảm khỏi tài nguyên công khai | Dữ liệu phát sinh từ log/trace cũng phải kiểm soát |
 Danh tính và quyền | Least privilege, MFA, workload identity, tách quyền quản trị, access review | IAM nội bộ không nhất thiết kiểm soát toàn bộ quyền vận hành của CSP |
 Mã hóa và khóa | TLS, mã hóa at-rest, customer-managed key hoặc HSM theo rủi ro | Vị trí khóa khác vị trí dữ liệu; lúc xử lý dịch vụ có thể cần quyền giải mã |
 Mạng và kết nối riêng | Private endpoint, segmentation, chính sách egress | Kết nối riêng không tự quyết định vị trí xử lý của dịch vụ đích |
 Giám sát và chứng minh | Audit log, cấu hình policy, hợp đồng, kiểm thử truy cập và luồng dữ liệu | Bằng chứng phải phản ánh hệ thống thực tế, kiểm tra sau mỗi thay đổi |
 Vòng đời và xóa | Retention, lifecycle, chính sách backup, yêu cầu xóa tới đối tác | Bản sao, archive và thời gian xóa phải theo khả năng của từng dịch vụ |

## 6. Đối chiếu với các mô hình triển khai cloud

Public cloud, private cloud, hybrid cloud và multi-cloud mô tả **ai vận hành hạ tầng và hệ thống trải trên những môi trường nào**. Chúng không tự động xác định tính sẵn sàng, địa lý hay quyền kiểm soát dữ liệu. Tất cả đều cần lựa chọn cụ thể.

| Mô hình | Lợi thế có thể có | Rủi ro hoặc công việc cần thêm |
|---|---|---|
 **Public cloud, một region** | Đơn giản hóa độ trễ nội vùng, kết nối và vận hành | DR xuyên region cần phương án riêng; phải kiểm tra dịch vụ/tenant và ràng buộc dữ liệu |
 **Public cloud, nhiều region** | Có thể phục vụ nhiều khu vực và giảm phụ thuộc lỗi một region | Replication, routing, consistency, egress, điều phối sự cố và dữ liệu xuyên biên giới |
 **Private cloud / on-premises** | Có thể tăng mức trực tiếp kiểm soát máy chủ, mạng và một số quyền operator | Doanh nghiệp tự chịu phần lớn trách nhiệm HA, DR, bản vá, capacity và kiểm chứng; vị trí đặt máy không tự đồng nghĩa tuân thủ |
 **Hybrid cloud** | Có thể giữ dữ liệu nhạy cảm tại môi trường hạn chế và dùng cloud cho tác vụ phù hợp | Đường kết nối, độ trễ, phân quyền, theo dõi dữ liệu và thay đổi ranh giới tin cậy phức tạp |
 **Multi-cloud** | Có thể tránh một số dạng phụ thuộc nhà cung cấp và đáp ứng yêu cầu chức năng/địa lý | Hai bộ IAM, mạng, observability, incident response, chi phí và các rủi ro chung của phần mềm ứng dụng |

Một region của nhà cung cấp A và một region của nhà cung cấp B không nhất thiết là hai **failure domain độc lập hoàn toàn**. Chúng có thể cùng phụ thuộc Internet, DNS, định danh, công cụ triển khai, lỗi cấu hình hoặc thư viện dùng chung. Đánh giá theo chuỗi dependency thực tế.

## 7. Ví dụ kiến trúc: nền tảng đặt phòng phục vụ nhiều khu vực

Giả sử một sản phẩm đặt phòng có người dùng tại nhiều quốc gia. Bộ phận nghiệp vụ đưa ra ba nhóm yêu cầu **minh họa**:

- **Sẵn sàng:** chức năng tạo đặt phòng có SLO 99,9% mỗi 30 ngày; với kịch bản mất region phải hướng tới RTO 60 phút và RPO 5 phút.
- **Địa lý:** người dùng ở xa cần tải hình ảnh nhanh; không bắt buộc mọi giao dịch ghi dữ liệu phải xử lý tại region gần nhất.
- **Dữ liệu:** thông tin định danh và đặt phòng thuộc nhóm cần kiểm soát vị trí lưu/xử lý; danh sách region được phép sẽ do bộ phận pháp chế và chủ sở hữu dữ liệu phê duyệt. Ảnh quảng bá công khai có chính sách phân phối khác dữ liệu định danh.

### 7.1. Kiến trúc tham khảo

~~~mermaid
flowchart TB
    USERS[Người dùng ở nhiều khu vực] --> EDGE[CDN / WAF / Global routing]
    EDGE --> WEB[Ứng dụng web hoặc API]
    subgraph R1[Region chính trong phạm vi được phép]
        API1[API - nhiều zone]
        DB1[(Database chính - HA đa zone)]
        OBJ1[(Object storage)]
        API1 --> DB1
        API1 --> OBJ1
    end
    WEB --> API1
    DB1 --> REP{Chính sách cho phép sao chép?}
    REP -->|Có| R2[(Replica / backup tại region dự phòng được phép)]
    REP -->|Không| LOCAL[(Backup cách ly trong phạm vi được phép)]
    API1 --> OBS[Log / Metric / Trace có chính sách vị trí]
    API1 --> THIRD[Đối tác thanh toán - đánh giá luồng dữ liệu]
~~~

Sơ đồ cố ý tách câu hỏi **có được phép sao chép dữ liệu đến region thứ hai không** khỏi câu hỏi **có cần DR không**. Nếu địa điểm dự phòng dự kiến không nằm trong phạm vi được phép, không thể mặc nhiên bật tính năng cross-region replication. Phải lựa chọn địa điểm khác hoặc điều chỉnh chiến lược DR và xem xét rủi ro còn lại theo yêu cầu nghiệp vụ.

### 7.2. Phân lớp dữ liệu để ra quyết định

| Loại dữ liệu | Mục tiêu | Thiết kế có thể phù hợp | Kiểm chứng |
|---|---|---|---|
 Ảnh quảng bá công khai | Độ trễ thấp, chịu tải tốt | Object storage + CDN toàn cầu nếu chính sách cho phép | Cache policy, purge, địa điểm cache và chi phí egress |
 Thông tin định danh khách hàng | Quyền riêng tư và vị trí được kiểm soát | Lưu, xử lý, backup và phân quyền trong phạm vi được phê duyệt | Sơ đồ luồng dữ liệu, policy region, thử truy cập, log |
 Giao dịch đặt phòng | Tính đúng đắn, tránh đặt trùng, khả năng khôi phục | Database HA, giao dịch phù hợp, idempotency; DR theo RTO/RPO | Test lỗi zone, test restore và đối soát dữ liệu sau failover |
 Log và telemetry | Quan sát và điều tra sự cố | Loại bỏ dữ liệu nhạy cảm; chọn nơi lưu log tương ứng chính sách | Kiểm tra mẫu log, retention, quyền truy cập và nơi lưu thực tế |
 Token / bí mật | Bảo vệ quyền gọi dịch vụ | Secret manager, quyền tối thiểu, rotation, tránh ghi vào log | Diễn tập thu hồi secret, audit và kiểm tra pipeline |

### 7.3. Ba phương án và cách đánh đổi

**Phương án A — một region, nhiều zone.** Ứng dụng và database có HA trong region. CDN xử lý tài nguyên công khai. Đây có thể là lựa chọn tốt nếu yêu cầu chống lỗi zone cao nhưng DR toàn region chưa bắt buộc hoặc chưa khả thi. Nhược điểm: mất region hoặc sự cố control plane chung vẫn có thể gây gián đoạn lớn; cần tài liệu hóa và chấp nhận rủi ro này.

**Phương án B — hai region, active-passive.** Giữ hệ thống chính ở region được phép, đồng thời có môi trường dự phòng và cách đưa dữ liệu sang region DR được chấp thuận. Đổi lại là chi phí môi trường chờ, replication, runbook, kiểm thử failover, nguy cơ RPO khác 0 nếu sao chép bất đồng bộ và xử lý chuyển lại sau sự cố.

**Phương án C — nhiều region, active-active.** API và có thể cả dữ liệu được phân tán để phục vụ người dùng tại nhiều khu vực. Phù hợp khi yêu cầu độ trễ hoặc sẵn sàng đủ lớn để chấp nhận sự phức tạp. Khó khăn: duy trì tính nhất quán đặt phòng, tránh ghi trùng, giải quyết xung đột, định tuyến người dùng, chi phí và kiểm soát dữ liệu xuyên biên giới. Không chọn chỉ vì “nhiều region hơn là tốt hơn”.

Trong cả ba phương án, đội thiết kế phải kiểm tra liệu SLO/RTO/RPO đề xuất có thật sự khả thi. Không thể suy ra RPO 5 phút chỉ từ tính năng replica nếu lag có thể vượt quá mức đó khi tải cao hoặc lỗi mạng.

### 7.4. Ma trận quyết định mẫu

Cho mỗi phương án, nhóm kiến trúc nên chấm **đạt / không đạt / cần kiểm chứng** cho từng yêu cầu bắt buộc, sau đó mới so sánh chi phí và độ phức tạp.

| Tiêu chí | A: Multi-zone, một region | B: Active-passive hai region | C: Active-active hai region |
|---|---|---|---|
 Chịu lỗi một zone | Có thể đạt khi toàn bộ thành phần quan trọng được phân tán | Có thể đạt khi thiết kế cả nội bộ mỗi region | Có thể đạt khi thiết kế các dependency đúng |
 Chịu lỗi toàn region | Cần quy trình khôi phục khác; không tự đạt | Có thể đạt nếu failover và dữ liệu dự phòng hoạt động | Có thể đạt nếu ứng dụng vẫn hoạt động khi mất một region |
 Ghi giao dịch nhất quán | Thường dễ kiểm soát hơn | Phải xử lý trạng thái khi chuyển đổi | Phức tạp nhất nếu ghi đa region |
 Độ trễ toàn cầu | CDN giúp nội dung tĩnh; API vẫn đi một region | Có thể phục vụ đọc ở nơi khác nếu được thiết kế | Có nhiều lựa chọn phục vụ gần người dùng |
 Ràng buộc vị trí dữ liệu | Thường ít luồng sao chép hơn, nhưng vẫn phải kiểm tra log/backup | Chỉ phù hợp khi region DR và luồng dữ liệu được phép | Cần đánh giá kỹ nơi lưu, xử lý, routing và đồng bộ |
 Chi phí và vận hành | Thường thấp hơn khi xét cùng tải và dịch vụ | Cao hơn do dự phòng và diễn tập | Có thể cao nhất do nhân bản, vận hành và giải quyết xung đột |

Những nhận định “có thể đạt” là **khả năng thiết kế**, không phải kết quả kiểm thử hoặc cam kết của một CSP.

## 8. Quy trình thiết kế từ yêu cầu đến kiểm chứng

### Bước 1 — Tách yêu cầu thành ba bộ tiêu chí

Ghi một bộ tiêu chí đo được cho mỗi trục:

| Nhóm | Câu hỏi để lượng hóa |
|---|---|
 Sẵn sàng | SLI đo hành vi nào, SLO trong cửa sổ nào, lỗi nào phải chịu được, RTO/RPO cho từng nghiệp vụ là bao nhiêu? |
 Địa lý | Người dùng ở đâu, chức năng nào cần độ trễ thấp, read/write đi đâu, có giới hạn bandwidth và egress không? |
 Chủ quyền dữ liệu | Loại dữ liệu nào, lưu/xử lý/backup ở đâu, ai được truy cập, có được chuyển qua biên giới không, bằng chứng gì cần lưu? |

Nếu yêu cầu chỉ là “99,99% uptime”, “global”, hoặc “dữ liệu nội địa”, phải làm rõ ý nghĩa và phạm vi trước khi chọn mô hình.

### Bước 2 — Lập sơ đồ tài nguyên, dependency và luồng dữ liệu

Bao gồm người dùng, edge, API, queue, compute, database, cache, storage, identity, KMS, DNS, log, CI/CD, backup, đối tác và đội vận hành. Gắn region, zone, pháp nhân hoặc môi trường cho từng thành phần khi thông tin liên quan. Đánh dấu đường ghi chính, đường đọc, luồng replication và khả năng truy cập hỗ trợ.

### Bước 3 — Xác định failure domain và điểm lỗi đơn

Hỏi lần lượt: nếu một tiến trình, node, zone, region, nhà cung cấp mạng, control plane hoặc đối tác ngừng hoạt động thì chức năng nào mất? Thành phần nào tự phục hồi, thành phần nào cần thao tác tay, và dữ liệu nào có nguy cơ không nhất quán?

### Bước 4 — Chọn topology và chính sách dữ liệu cùng lúc

Đánh giá các lựa chọn one-region/multi-zone, multi-region, hybrid hoặc multi-cloud song song với quyền vị trí dữ liệu. Mỗi quyết định sao chép, cache, failover hay sử dụng một dịch vụ mới đều có thể thay đổi phạm vi xử lý dữ liệu.

### Bước 5 — Gắn chủ sở hữu và kiểm soát

Xác định ai cấu hình replication, ai quản trị region allowlist, ai phê duyệt luồng dữ liệu mới, ai xử lý sự cố, ai kiểm tra backup/restore và ai liên lạc với CSP. Phân biệt phần CSP vận hành với phần khách hàng chịu trách nhiệm cấu hình và bằng chứng.

### Bước 6 — Triển khai kiểm soát tự động

- Hạn chế vùng triển khai bằng policy và kiểm tra Infrastructure as Code khi dịch vụ hỗ trợ.
- Tách dữ liệu theo mức nhạy cảm; tối thiểu hóa payload gửi tới log, edge và đối tác.
- Kiểm tra backup, snapshot, replica, lifecycle, khóa và các đường truy cập ngoài ý muốn.
- Bảo vệ IAM, cấu hình kết nối riêng, secret và quyền vận hành giữa các môi trường.
- Đặt cảnh báo SLI, replication lag, lỗi backup, số lượng yêu cầu thất bại, chi phí, độ trễ theo khu vực và thay đổi policy nhạy cảm.

### Bước 7 — Thử nghiệm lỗi và kiểm toán đường đi dữ liệu

Thử lỗi instance, zone, mất kết nối dependency và failover toàn region trong giới hạn có thể; đo thời gian phát hiện, chuyển hướng, khôi phục và đối soát dữ liệu. Thử xóa nhầm, khôi phục một tập dữ liệu cũ, quyền truy cập sai và việc gửi dữ liệu nhạy cảm vào log. Kiểm tra nơi log/backup/cache thực sự được tạo ra, không chỉ nơi DB được cấu hình.

### Bước 8 — Rà soát khi thay đổi

Mỗi lần đổi region, bật CDN, thêm SaaS, chuyển chế độ HA, mở rộng sang thị trường mới hay nâng cấp dịch vụ, cập nhật ma trận yêu cầu, sơ đồ luồng dữ liệu, threat model, runbook và bằng chứng tuân thủ.

## 9. Đánh giá theo tư duy Well-Architected

| Góc nhìn | Điều cần đặt câu hỏi | Đánh đổi cần chấp nhận có chủ đích |
|---|---|---|
 **Reliability – Độ tin cậy** | Có chịu lỗi đúng failure domain và đo được RTO/RPO không? | Dự phòng nhiều vùng tăng khả năng phục hồi nhưng làm tăng phức tạp trạng thái |
 **Security – Bảo mật** | Dữ liệu, khóa, quyền operator và luồng xử lý có được kiểm soát đúng không? | Kiểm soát chặt vị trí có thể hạn chế lựa chọn dịch vụ và chiến lược DR |
 **Performance Efficiency – Hiệu năng** | Phần nào cần phục vụ gần người dùng; phần nào cần dữ liệu nhất quán? | Xử lý gần người dùng giảm latency nhưng ghi xuyên vùng có thể chậm hoặc xung đột |
 **Cost Optimization – Chi phí** | Bản sao dữ liệu, standby, inter-region traffic, egress và kiểm toán tốn bao nhiêu? | Multi-region tăng chi phí cố định và chi phí lưu lượng; một region có thể tăng rủi ro gián đoạn |
 **Operational Excellence – Vận hành** | Ai kích hoạt failover, ai xác nhận dữ liệu, ai quản lý chính sách vị trí? | Mô hình phức tạp đòi hỏi diễn tập, theo dõi và trách nhiệm rõ ràng |
 **Sustainability – Bền vững** | Có nhân bản tài nguyên, lưu cache hoặc dữ liệu vượt nhu cầu không? | Dự phòng cần thiết cho độ tin cậy nhưng cấp thừa làm tăng tài nguyên tiêu thụ |

Well-Architected không phải tên một cấu hình duy nhất. Đây là cách đánh giá quyết định qua nhiều mục tiêu, ghi nhận rủi ro còn lại và lựa chọn giải pháp phù hợp bối cảnh nghiệp vụ.

## 10. Sai lầm thường gặp

| Nhận định sai | Vì sao sai | Điều nên kiểm tra |
|---|---|---|
 “Có ba instance trong một zone là đủ HA.” | Lỗi zone có thể hạ cả ba instance | Placement, dependency và khả năng chịu lỗi zone |
 “Multi-zone nghĩa là chịu được lỗi cả region.” | Các zone vẫn nằm trong cùng region | DR topology, vùng khôi phục và quy trình failover |
 “Dùng multi-region thì không cần backup.” | Lỗi dữ liệu logic có thể được sao chép sang mọi region | Backup độc lập, PITR, retention, kiểm thử restore |
 “CDN toàn cầu nghĩa là ứng dụng active-active.” | CDN có thể chỉ cache nội dung tĩnh trong khi API và DB vẫn ở một region | Đường đi request đến origin, vị trí xử lý và dữ liệu |
 “Đặt data ở region nội địa là đủ chủ quyền.” | Log, replica, quyền operator, hợp đồng và hệ thống ngoài có thể vượt phạm vi | Inventory, data flow và quyền tài phán |
 “Mã hóa dữ liệu giải quyết mọi yêu cầu chuyển dữ liệu.” | Dịch vụ có thể cần xử lý dữ liệu đã giải mã; pháp luật có thể có yêu cầu khác | Mục đích xử lý, kiểm soát khóa, bên nhận và quy định áp dụng |
 “Hai CSP là không còn điểm lỗi đơn.” | Đăng nhập, DNS, mã ứng dụng và pipeline có thể là dependency chung | Dependency graph và diễn tập lỗi |
 “Có SLA cao là ứng dụng có SLO cao.” | SLA của một thành phần không bao quát cấu hình và toàn bộ luồng nghiệp vụ | SLI đầu cuối, error budget, test lỗi và giới hạn hợp đồng |

## 11. Bài tập tình huống

### Bài tập A — Ứng dụng thương mại một region

Một API có ba instance sau load balancer, tất cả nằm trong cùng zone. Database cũng ở zone đó. Chủ sản phẩm yêu cầu chịu lỗi một zone.

**Câu hỏi:** Có đạt không? Cần điều chỉnh gì?

**Hướng giải:** Chưa đạt. Cần phân bố compute trên nhiều zone, cân bằng tải và health check phù hợp, thiết kế database/các thành phần stateful có khả năng chịu lỗi zone, kiểm tra những dependency chung và diễn tập khi zone không truy cập được.

### Bài tập B — CDN ở nhiều quốc gia

Ứng dụng phân phối ảnh công khai qua CDN tại nhiều nơi. API và database ở một region. Người dùng phàn nàn việc đặt phòng vẫn chậm.

**Câu hỏi:** Có thể nói hệ thống đã được phân bố toàn cầu chưa?

**Hướng giải:** Chỉ lớp phân phối nội dung công khai được phân bố. Cần đo đường đi API, độ trễ tới database, xử lý đồng bộ và số lần gọi chéo vùng; cải thiện bằng cache phù hợp, giảm round-trip, tách xử lý đọc hoặc thêm vùng tính toán nếu nghiệp vụ và chính sách dữ liệu cho phép.

### Bài tập C — Bật replica ở nước ngoài

Một đội muốn bổ sung replica sang region ngoài quốc gia để tăng độ tin cậy. Chính sách yêu cầu dữ liệu khách hàng phải tuân theo giới hạn vị trí lưu và quyền truy cập nghiêm ngặt, nhưng chưa có danh sách region được phê duyệt.

**Câu hỏi:** Có nên bật replica ngay không?

**Hướng giải:** Trước tiên xác định loại dữ liệu, giới hạn lưu/xử lý/backup, các bên truy cập và quy định áp dụng; xin phê duyệt vị trí theo quy trình tổ chức. Song song, so sánh DR trong phạm vi được phép, backup cách ly, tối ưu multi-zone và công bố rủi ro region để chủ sở hữu nghiệp vụ quyết định. Không mặc định khả năng replication hợp lệ chỉ vì CSP cung cấp tính năng.

### Bài tập D — Hai region nhưng không đạt RPO

Một hệ thống active-passive tự động chuyển traffic sang region phụ. Trong diễn tập, API phục hồi sau 10 phút nhưng thiếu 25 phút dữ liệu ghi cuối cùng; mục tiêu RTO là 30 phút và RPO là 5 phút.

**Câu hỏi:** Mục tiêu nào đạt, mục tiêu nào không đạt; phải làm gì?

**Hướng giải:** Với số liệu giả định và mốc đo đã thống nhất, RTO đạt nhưng RPO không đạt. Cần đo replication lag, giới hạn ghi trong failover, lựa chọn cơ chế sao chép và xác nhận ghi phù hợp, thay đổi quy trình chuyển vùng hoặc điều chỉnh mục tiêu nếu được nghiệp vụ chấp thuận; diễn tập và đối soát lại.

## 12. Checklist trước khi phê duyệt kiến trúc

- [ ] SLI/SLO của chức năng nghiệp vụ, RTO/RPO và phạm vi kịch bản lỗi được định nghĩa rõ.
- [ ] Đã xác định failure domain ở cấp tiến trình, node, zone, region, mạng và dịch vụ dùng chung.
- [ ] Có chiến lược HA và DR, kế hoạch failover/failback, backup, restore cùng kết quả diễn tập.
- [ ] Đã đo hoặc ước lượng có cơ sở độ trễ của API, database, replication và lưu lượng liên vùng.
- [ ] Đã tách nội dung công khai, dữ liệu nhạy cảm, dữ liệu giao dịch, log, telemetry và backup.
- [ ] Có danh mục nơi lưu, xử lý, cache, backup và nơi bên thứ ba có thể truy cập dữ liệu.
- [ ] Các quy định và hợp đồng về vị trí/quyền dữ liệu được xác minh theo dịch vụ và phạm vi triển khai cụ thể.
- [ ] Chính sách IAM, mã hóa, khóa, region allowlist và quyền operator có owner cùng bằng chứng kiểm tra.
- [ ] Đã đánh giá tác động chi phí, egress, vận hành, consistency và rủi ro còn lại của các phương án.
- [ ] Có quy trình rà soát lại khi thêm region, chuyển mô hình triển khai hoặc thay đổi nhà cung cấp.

**Điểm cốt lõi:** tính sẵn sàng trả lời **dịch vụ có hoạt động khi lỗi xảy ra không**; phân bố địa lý trả lời **thành phần và dữ liệu nằm ở đâu, phục vụ ai**; chủ quyền dữ liệu trả lời **ai có thẩm quyền, quyền kiểm soát và quyền truy cập đối với dữ liệu**. Kiến trúc tốt phải giải được cả ba câu hỏi bằng yêu cầu cụ thể, thiết kế nhất quán và bằng chứng kiểm thử thực tế.

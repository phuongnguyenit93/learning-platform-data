# Phân tích tác động nghiệp vụ và lựa chọn RTO, RPO

## 1. Phục hồi thảm họa bắt đầu từ tác động nghiệp vụ

Disaster Recovery (DR) là khả năng khôi phục dịch vụ và dữ liệu sau một sự cố nghiêm trọng khiến hệ thống hoặc một miền hạ tầng không thể tiếp tục hoạt động bình thường. Sự cố có thể là mất một availability zone, lỗi region, hỏng dữ liệu, ransomware, lỗi cấu hình diện rộng, mất kết nối nhà cung cấp hoặc sự cố vận hành.

Một kế hoạch DR tốt không bắt đầu bằng câu hỏi “cần bao nhiêu replica?” hay “nên dùng active-active không?”. Nó bắt đầu bằng câu hỏi **dịch vụ nào quan trọng, doanh nghiệp chịu được gián đoạn bao lâu, có thể mất bao nhiêu dữ liệu và cần khôi phục những phụ thuộc nào để quy trình nghiệp vụ hoạt động trở lại?**

Hai chỉ số thường dùng:

- **RTO (Recovery Time Objective):** mục tiêu thời gian khôi phục dịch vụ sau gián đoạn. Đây là giới hạn thời gian mà tổ chức đặt ra cho việc khôi phục một chức năng ở mức dịch vụ đã định nghĩa.
- **RPO (Recovery Point Objective):** mục tiêu điểm khôi phục dữ liệu, thể hiện mức mất dữ liệu theo thời gian mà nghiệp vụ chấp nhận được khi phải phục hồi từ bản sao/backup/replica.

RTO và RPO là **mục tiêu nghiệp vụ**, không phải bảo đảm tự động của một tính năng cloud. Cấu hình backup mỗi giờ không tự chứng minh RPO một giờ; cần tính thời điểm bản backup thực sự nhất quán, thời gian phát hiện lỗi, phạm vi dữ liệu và quy trình restore. Tương tự, có standby region không tự chứng minh RTO đạt 15 phút nếu DNS, identity, quota, dữ liệu hoặc nhân sự vận hành cần nhiều giờ mới phục hồi.

Trong module **CLOUD_ARCHITECTURE**, việc lựa chọn RTO/RPO kết nối yêu cầu nghiệp vụ với mạng, compute, lưu trữ, database, bảo mật và mô hình triển khai. Quyết định cần cân bằng **độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

Ví dụ xuyên suốt: một nền tảng đặt chỗ có tìm kiếm property, giữ phòng, thanh toán, quản lý booking, gửi email và báo cáo. Tìm kiếm có thể suy giảm tạm thời; thanh toán và trạng thái booking cần bảo vệ chặt hơn; báo cáo phân tích có thể tái tạo từ dữ liệu giao dịch.

## 2. Các khái niệm thời gian cần phân biệt

RTO/RPO thường được dùng cùng nhiều khái niệm khác. Phải thống nhất cách định nghĩa với business owner, đội vận hành và nhà cung cấp:

| Khái niệm | Ý nghĩa | Câu hỏi chính |
| --- | --- | --- |
| **MTPD/MAO** | Maximum Tolerable Period of Disruption / Maximum Acceptable Outage: thời gian gián đoạn tối đa doanh nghiệp có thể chịu trước khi hậu quả không còn chấp nhận được | Dịch vụ có thể ngừng lâu nhất bao lâu? |
| **RTO** | Mục tiêu thời gian khôi phục chức năng/dịch vụ sau sự cố | Phải đưa dịch vụ trở lại trong bao lâu? |
| **RPO** | Mức mất dữ liệu theo thời gian chấp nhận được khi khôi phục | Có thể mất những thay đổi của bao lâu trước sự cố? |
| **WRT (Work Recovery Time)** | Thời gian cần sau khi hệ thống kỹ thuật phục hồi để kiểm tra, đối soát và hoàn tất công việc nghiệp vụ tồn đọng | Sau khi hệ thống lên, cần bao lâu để nhân viên và quy trình làm việc bình thường? |
| **MTTR** | Mean Time To Repair/Recover, một chỉ số quan sát thời gian sửa chữa/phục hồi trung bình theo định nghĩa tổ chức | Thực tế các sự cố trước đây mất bao lâu? |
| **MTBF** | Mean Time Between Failures, thời gian trung bình giữa các lần hỏng theo cách đo xác định | Sự cố xảy ra với tần suất nào? |

MTPD/MAO không phải một mục tiêu phục hồi. Nó biểu diễn ngưỡng gián đoạn cuối cùng mà nghiệp vụ có thể chịu. RTO nên ngắn hơn MTPD/MAO để còn thời gian cho WRT và xử lý tồn đọng.

Một quan hệ lập kế hoạch thường dùng:

~~~text
RTO + WRT < MTPD
~~~

Đây là cách diễn đạt đơn giản để đặt khoảng đệm. Một số tổ chức định nghĩa MTPD, MAO hoặc WRT hơi khác nhau; cần ghi rõ glossary và mốc bắt đầu/kết thúc trong BIA.

## 3. Business Impact Analysis (BIA)

**BIA** là quá trình phân tích các hoạt động nghiệp vụ, mức độ quan trọng và hậu quả khi chúng bị gián đoạn. BIA tạo bằng chứng để ưu tiên khôi phục và xác định RTO/RPO phù hợp.

Không nên hỏi business owner một câu chung chung như “dịch vụ này quan trọng đến mức nào?”. Hãy yêu cầu họ mô tả tác động theo thời gian, phạm vi khách hàng, doanh thu, pháp lý, an toàn, uy tín và phụ thuộc.

### 3.1. Các chiều tác động

| Chiều tác động | Ví dụ câu hỏi |
| --- | --- |
| Doanh thu/tài chính | Mỗi 15 phút, 1 giờ hoặc 1 ngày gián đoạn gây tổn thất trực tiếp/gián tiếp bao nhiêu? |
| Khách hàng | Bao nhiêu khách không thể đặt chỗ, truy cập booking hay nhận hỗ trợ? Có phương án thay thế không? |
| Pháp lý/hợp đồng | Có thời hạn báo cáo, nghĩa vụ lưu trữ hoặc SLA với đối tác bị vi phạm không? |
| Vận hành | Nhân viên có thể chuyển sang quy trình thủ công không? Backlog tăng nhanh đến mức nào? |
| An toàn và quyền riêng tư | Sự cố có làm sai trạng thái giao dịch, rò dữ liệu hoặc mất khả năng kiểm soát truy cập không? |
| Uy tín | Tác động đến niềm tin, thương hiệu và khả năng giữ khách hàng ra sao? |
| Chuỗi cung ứng/đối tác | Nhà cung cấp thanh toán, identity, DNS hay đối tác tích hợp có bị ảnh hưởng không? |

### 3.2. Phân tích theo thời gian

Tác động không nhất thiết tăng tuyến tính. Có thể gián đoạn 10 phút vẫn xử lý được bằng tồn kho hoặc hotline; nhưng sau 4 giờ, backlog, hoàn tiền, khiếu nại và nghĩa vụ đối soát tăng đột biến.

| Thời gian gián đoạn | Tác động minh họa với booking platform |
| --- | --- |
| 0–15 phút | Request lỗi, khách thử lại; đội trực xác định phạm vi và chuyển sang quy trình dự phòng |
| 15–60 phút | Tỷ lệ chuyển đổi giảm; CS nhận nhiều ticket; giao dịch đang xử lý cần đối soát |
| 1–4 giờ | Backlog tăng; đối tác và khách hàng doanh nghiệp cần thông báo; nguy cơ vi phạm cam kết |
| 4–24 giờ | Tác động tài chính/uy tín đáng kể; nhân sự dự phòng, quy trình thủ công và đối soát trở nên nặng |
| Trên 24 giờ | Có thể vượt ngưỡng chịu đựng; cần quyết định điều hành, thông báo pháp lý/hợp đồng và phục hồi dài hạn |

Đây chỉ là ví dụ minh họa. Mỗi doanh nghiệp phải định lượng bằng dữ liệu, hợp đồng và ý kiến của business owner.

### 3.3. Mẫu câu hỏi BIA

Với mỗi hoạt động, cần ghi:

1. Ai sử dụng và khách hàng/đối tác nào phụ thuộc?
2. Thời điểm nào hoạt động quan trọng nhất (giờ cao điểm, cuối tháng, mùa du lịch)?
3. Mức dịch vụ tối thiểu khi suy giảm là gì?
4. Có thể chuyển sang thủ công hay xử lý offline không? Bao lâu và với công suất bao nhiêu?
5. Tác động sau 15 phút, 1 giờ, 4 giờ, 1 ngày và nhiều ngày?
6. Dữ liệu nào mất đi sẽ gây thiệt hại không thể khôi phục hoặc phải đối soát thủ công?
7. Hậu quả nào có thể chấp nhận được, ai có quyền chấp thuận?
8. Thời gian cần để xử lý backlog sau khi hệ thống trở lại?

## 4. Phân tách nghiệp vụ thành dịch vụ và capability

Một tên ứng dụng có thể bao gồm nhiều capability với mức quan trọng khác nhau. Nếu gán một RTO/RPO cho toàn bộ nền tảng, tổ chức có thể đầu tư quá mức cho báo cáo hoặc bảo vệ chưa đủ cho thanh toán.

Ví dụ phân rã:

| Capability | Mức quan trọng minh họa | Khi gián đoạn |
| --- | --- | --- |
| Authentication/authorization | Rất cao | Người dùng không đăng nhập hoặc không thể xác minh quyền; nếu lỗi bảo mật, phải ưu tiên fail-safe |
| Booking/Inventory | Rất cao | Không thể giữ phòng/xác nhận giao dịch; nguy cơ đặt trùng và mất doanh thu |
| Payment integration | Rất cao | Trạng thái thanh toán không rõ; không được thu tiền hoặc xác nhận sai |
| Customer booking view | Cao | Khách không xem được giao dịch đã đặt; CS tăng tải |
| Property search | Trung bình–cao | Khách khó tìm kết quả; có thể dùng cache/dữ liệu stale có giới hạn |
| Notification | Trung bình | Email/SMS trễ; có thể gửi lại từ event/outbox |
| Analytics/report | Thấp hơn cho vận hành realtime | Có thể chậm hoặc tái tạo từ dữ liệu nguồn |
| Static media | Tùy sản phẩm | CDN/backup có thể phục vụ; khả năng thay thế phụ thuộc cache |

Mức quan trọng phải dựa trên BIA, không phải phán đoán của đội kỹ thuật. Một dịch vụ nhìn có vẻ “phụ trợ” như identity, DNS hoặc secrets có thể là dependency bắt buộc của nhiều dịch vụ critical.

## 5. Chọn RTO từ tác động nghiệp vụ

RTO được chọn để dịch vụ trở lại mức hoạt động được định nghĩa trước khi tác động vượt ngưỡng chấp nhận. Cần định nghĩa “phục hồi” là gì:

- Hệ thống process khởi động được?
- API health check trả 200?
- Người dùng đăng nhập được?
- Có thể tìm và giữ phòng?
- Có thể hoàn tất booking và xác minh thanh toán?
- Backlog đã được xử lý và SLO bình thường trở lại?

Một health check xanh không đồng nghĩa quy trình nghiệp vụ đã khôi phục. Nên định nghĩa **minimum viable service** và **full service restoration** riêng nếu có thể phục hồi từng phần.

### 5.1. RTO theo cấp dịch vụ

Ví dụ minh họa:

| Tier | Capability | RTO mục tiêu ví dụ | Điều kiện phục hồi |
| --- | --- | ---: | --- |
| Tier 0 – Critical | Identity, booking, payment status | 15 phút | Có thể xác thực, kiểm soát giao dịch và đối soát |
| Tier 1 – Essential | Search, customer booking view | 1 giờ | Khách tìm/tra cứu được; có thể giảm một số tính năng |
| Tier 2 – Important | Notification, partner sync | 4 giờ | Backlog được xử lý, không mất sự kiện |
| Tier 3 – Deferrable | Analytics, báo cáo lịch sử | 24 giờ | Có thể rebuild từ nguồn dữ liệu đã lưu |

Các con số không phải khuyến nghị chung cho mọi công ty. Hãy chọn từ MTPD, doanh thu, khách hàng, phương án thay thế, WRT và ngân sách.

### 5.2. Tính đủ cả thời gian con người

Thời gian phục hồi thực tế có thể gồm:

~~~text
T_detect       = thời gian phát hiện và xác nhận sự cố
T_decide       = thời gian tuyên bố DR và chọn runbook
T_provision    = thời gian cấp/đưa hạ tầng dự phòng sẵn sàng
T_data         = thời gian restore/replication catch-up
T_validate     = thời gian kiểm tra dữ liệu và chức năng
T_traffic      = thời gian chuyển routing và ổn định tải
T_operational  = thời gian để nghiệp vụ trở lại mức tối thiểu

RTO thực tế = tổng các khoảng thời gian liên quan theo đường phục hồi
~~~

Không phải thành phần nào cũng tuần tự; một số có thể chạy song song. Cần đo từ diễn tập để biết critical path, tránh chỉ cộng thời gian chạy script mà quên phát hiện, phê duyệt, DNS, chứng thư, quota hoặc kiểm thử nghiệp vụ.

## 6. Chọn RPO từ mức chấp nhận mất dữ liệu

RPO trả lời: **khi phải khôi phục, dữ liệu mới nhất có thể thiếu đi bao lâu mà doanh nghiệp vẫn chấp nhận được?**

Nếu RPO là 15 phút, tổ chức chấp nhận rằng ở kịch bản khôi phục được định nghĩa, những thay đổi chưa được bảo vệ trong khoảng tối đa tương ứng có thể bị mất. Đây không có nghĩa luôn mất đúng 15 phút, cũng không có nghĩa backup chạy 15 phút là đủ.

### 6.1. RPO khác với backup frequency

Giả sử:

- Backup được lên lịch mỗi 4 giờ.
- Backup bắt đầu lúc 10:00 nhưng hoàn tất và nhất quán lúc 10:25.
- Sự cố xảy ra lúc 12:10.
- Bản backup khả dụng gần nhất là snapshot 10:25.

Điểm dữ liệu gần nhất được bảo vệ là 10:25, nên khoảng mất dữ liệu tiềm năng tới lúc sự cố là 1 giờ 45 phút. Tần suất “mỗi 4 giờ” không phải RPO thực tế. Nếu transaction log được archive liên tục và có thể point-in-time restore tới 12:05, RPO có thể nhỏ hơn đáng kể; nhưng điều đó phụ thuộc log availability, tính nhất quán và khả năng restore đã kiểm chứng.

### 6.2. RPO theo loại dữ liệu

| Loại dữ liệu | Mức mất dữ liệu có thể chấp nhận | Lý do |
| --- | --- | --- |
| Booking đã xác nhận | RPO gần 0 hoặc rất thấp | Mất booking đã xác nhận gây tranh chấp với khách và đối tác |
| Payment ledger/status | RPO rất thấp, kèm đối soát | Cần tránh mất dấu tiền đã thu/ủy quyền |
| Search index | Có thể tái tạo; RPO theo event retention | Không phải nguồn có thẩm quyền |
| Notification queue | Có thể phát lại nếu event/outbox còn | Chấp nhận trễ nếu không mất sự kiện |
| Analytics projection | Có thể RPO cao hơn nếu rebuild được | Có thể tạo lại từ nguồn giao dịch |
| Ảnh property | Theo durability và backup/copy policy | Có thể upload lại trong một số trường hợp, nhưng cần đánh giá chi phí và quyền |

### 6.3. RPO không chỉ là dữ liệu database

Một quy trình nghiệp vụ có thể phụ thuộc vào nhiều loại trạng thái:

- Database transaction và transaction log.
- Object/document lưu ở object storage.
- Message broker, outbox, event log và consumer offset.
- Secret, key, certificate và cấu hình hạ tầng.
- DNS, identity, policy và metadata.
- Mapping/version của search index và cache generation.

Nếu database được khôi phục tới một thời điểm nhưng object storage hoặc event log không đồng bộ với thời điểm đó, ứng dụng có thể tham chiếu object không tồn tại hoặc xử lý lặp sự kiện. RPO phải được xác định cho **toàn bộ tập dữ liệu cần thiết để nghiệp vụ nhất quán**, không chỉ database chính.

## 7. Kết hợp RTO, RPO, MTPD và WRT

Mỗi capability cần ít nhất một bộ mục tiêu có giải thích:

| Capability | MTPD ví dụ | RTO ví dụ | WRT ví dụ | RPO ví dụ |
| --- | ---: | ---: | ---: | ---: |
| Booking | 2 giờ | 30 phút | 30 phút | 1 phút |
| Payment status | 1 giờ | 15 phút | 45 phút đối soát | Gần 0 |
| Search | 8 giờ | 2 giờ | 30 phút | 15 phút hoặc rebuild |
| Notification | 24 giờ | 8 giờ | 2 giờ backlog | 5 phút hoặc event replay |
| Analytics | 3 ngày | 24 giờ | 4 giờ kiểm tra số liệu | 24 giờ nếu nguồn lưu đầy đủ |

Giả sử Booking có MTPD 2 giờ. Chọn RTO 30 phút và WRT 30 phút để còn 1 giờ dự phòng cho sai lệch, sự cố tiếp theo và biến động vận hành. Nếu WRT cũng mất 2 giờ, mục tiêu RTO 30 phút không giúp doanh nghiệp quay lại hoạt động trong MTPD.

### 7.1. Không ép một mục tiêu cho toàn hệ thống

Một hệ thống có nhiều cấp:

- API có thể hoạt động sau 15 phút nhưng báo cáo chưa sẵn sàng.
- Booking có thể nhận giao dịch mới, trong khi đối soát thanh toán cũ vẫn đang chạy.
- Search có thể dùng index cũ có nhãn stale, trong khi booking vẫn xác minh trực tiếp.
- Notification có thể tích lũy backlog và xử lý sau mà không chặn giao dịch.

Hãy định nghĩa trạng thái phục hồi theo capability và phụ thuộc thay vì một checkbox “application restored”.

## 8. Lập dependency map và chuỗi phục hồi

BIA xác định hoạt động quan trọng; dependency mapping xác định hệ thống cần khôi phục để hoạt động đó chạy được.

~~~mermaid
flowchart TD
    USER["Khách hàng / nhân viên"]
    EDGE["DNS / CDN / WAF / Load balancer"]
    AUTH["Identity / Secrets"]
    API["Booking API / Compute"]
    DB["Booking DB"]
    PAY["Payment provider / Payment ledger"]
    QUEUE["Outbox / Event broker"]
    SEARCH["Search index"]
    NOTIFY["Notification worker"]
    USER --> EDGE --> API
    API --> AUTH
    API --> DB
    API --> PAY
    DB --> QUEUE
    QUEUE --> SEARCH
    QUEUE --> NOTIFY
~~~

Nếu API đã chạy nhưng DNS chưa trỏ đúng, identity không cấp token hoặc secrets không giải mã được, capability vẫn chưa phục hồi. Nếu database đã restore nhưng payment provider webhook endpoint vẫn trỏ tới region cũ, trạng thái giao dịch có thể bị thiếu cập nhật.

### 8.1. Phân loại dependency

| Loại dependency | Ví dụ | Cần làm rõ |
| --- | --- | --- |
| Critical path runtime | Database booking, identity, DNS | Phải có sẵn ngay để phục hồi minimum service |
| Data dependency | Object storage, event log, payment ledger | Tính nhất quán, RPO, restore order |
| Control plane | IAM, cloud console/API, deployment system | Có thể điều khiển hạ tầng khi region chính mất không? |
| External provider | Payment, SMS, identity federation | Có endpoint/credential/contract dự phòng không? |
| Human/process | On-call, approver, finance reconciliation | Ai có quyền tuyên bố DR và xử lý giao dịch không rõ? |
| Observability | Monitoring, logs, alerting | Có hoạt động độc lập với failure domain chính không? |

### 8.2. Single point of failure ngoài ứng dụng

Cần kiểm tra cả:

- DNS zone, registrar, certificate authority và quyền quản trị domain.
- Identity provider, KMS, secret manager và key recovery.
- Artifact registry, container image, package và IaC state.
- CI/CD, account/role và quyền triển khai ở region dự phòng.
- Monitoring, paging, chat/bridge và tài liệu runbook.
- Quota cloud, IP address, load balancer capacity và license.

Một kế hoạch DR có thể thất bại dù dữ liệu được replicate tốt, bởi đội vận hành không thể đăng nhập hoặc triển khai vào môi trường dự phòng.

## 9. Chọn chiến lược DR theo RTO/RPO và chi phí

Các chiến lược phổ biến tạo ra mức sẵn sàng và chi phí khác nhau. Tên gọi có thể khác giữa nhà cung cấp; điều quan trọng là mô tả trạng thái thực tế của compute, data và routing.

| Chiến lược | Mô tả | RTO/RPO tương đối | Chi phí/độ phức tạp |
| --- | --- | --- | --- |
| Backup and restore | Backup dữ liệu/cấu hình; khi sự cố mới cấp hạ tầng và restore | RTO dài hơn; RPO phụ thuộc backup/log | Chi phí standby thấp, restore có thể lâu |
| Pilot light | Một phần nền tảng tối thiểu luôn sẵn sàng, dữ liệu được replicate/backup | RTO trung bình; RPO phụ thuộc replication | Tốn ít hơn warm standby nhưng cần scale/provision khi failover |
| Warm standby | Hệ thống thu nhỏ chạy sẵn ở region dự phòng, dữ liệu đồng bộ | RTO ngắn hơn; RPO có thể thấp | Chi phí vận hành liên tục và capacity dự phòng |
| Active-active / multi-site | Nhiều site cùng phục vụ traffic | Có thể RTO rất thấp; RPO có thể rất thấp tùy dữ liệu | Chi phí, consistency, routing và vận hành phức tạp nhất |

Không có chiến lược nào tự động bảo đảm một con số RTO/RPO. Ví dụ backup and restore có thể đạt RTO vài giờ nếu dữ liệu nhỏ, IaC đầy đủ và restore đã tối ưu; warm standby vẫn có thể cần nhiều giờ nếu failover database hoặc identity chưa tự động.

### 9.1. Backup and restore

Phù hợp với capability có MTPD dài hơn hoặc có thể tái tạo. Cần:

- Backup tự động, mã hóa, quyền truy cập riêng và retention.
- Bản sao backup nằm ngoài failure domain cần bảo vệ.
- Point-in-time recovery nếu RPO yêu cầu.
- IaC và artifact đủ để dựng lại network/compute/identity/configuration.
- Runbook restore có bước xác minh dữ liệu và kiểm tra ứng dụng.

### 9.2. Pilot light

Giữ sẵn nền móng cần thiết: network, quyền, database replica hoặc dữ liệu backup, artifact và một số thành phần thiết yếu. Khi failover mới scale compute, worker và endpoint. Cần kiểm tra thời gian cấp quota/instance, image pull, autoscaling và phụ thuộc control plane.

### 9.3. Warm standby

Region dự phòng có stack gần đầy đủ với capacity nhỏ hơn, thường chạy health check và nhận replication. Failover gồm nâng capacity, chuyển traffic, kiểm tra dependency và xử lý backlog. Cần xác định standby có đủ năng lực khi phải phục vụ 100% tải hay không.

### 9.4. Active-active

Nhiều region cùng phục vụ. Cần giải quyết routing, data consistency, conflict resolution, write ownership, idempotency, session, cache, global rate limit và failback. Multi-region active-active không phù hợp chỉ vì muốn RTO thấp; nếu nghiệp vụ không chịu được conflict hoặc nhân lực chưa vận hành nổi, mô hình đơn giản hơn có thể an toàn hơn.

## 10. Chọn topology và replication cho dữ liệu

RPO thường bị chi phối bởi cách dữ liệu được replicate và cách khôi phục transaction:

| Phương pháp | Đặc điểm | Câu hỏi DR |
| --- | --- | --- |
| Periodic snapshot/backup | Chụp trạng thái tại các thời điểm | Backup gần nhất có nhất quán và restore được không? |
| Continuous log shipping | Gửi transaction log/WAL/binlog | Log có được bảo vệ ngoài region và replay tới thời điểm nào? |
| Asynchronous replication | Primary commit rồi gửi thay đổi tới replica | Replication lag tối đa là bao nhiêu; có thể mất giao dịch đã ack không? |
| Synchronous replication | Commit chờ điều kiện xác nhận từ replica theo cơ chế DB | Latency/availability đổi ra sao khi link liên vùng lỗi? |
| Object replication | Sao chép object/version giữa bucket/region | Delete, metadata, encryption key và replication status xử lý thế nào? |
| Event streaming replication | Replicate log/stream và offset | Ordering, retention, consumer position và replay có bảo toàn không? |

### 10.1. Replication không thay thế backup

Nếu dữ liệu bị xóa nhầm, mã độc mã hóa hoặc ghi sai hàng loạt, replication có thể sao chép lỗi sang region dự phòng. Backup có version/immutability và quyền xóa tách biệt giúp bảo vệ trước các lỗi logic hoặc hành động độc hại.

Một chiến lược dữ liệu tốt thường kết hợp replication để giảm thời gian failover và backup để phục hồi về điểm sạch trong lịch sử.

### 10.2. Replication lag và acknowledged writes

Với asynchronous replication, primary có thể trả thành công trước khi replica nhận bản ghi. Nếu primary mất đột ngột, giao dịch đã được xác nhận với người dùng có thể chưa tồn tại trên standby. Cần:

- Đo replication lag theo thời gian và byte/LSN/offset.
- Xác định RPO trong sự cố mất kết nối đột ngột, không chỉ lúc bình thường.
- Có chính sách chặn hoặc suy giảm write khi lag vượt ngưỡng nếu nghiệp vụ yêu cầu.
- Đối soát giao dịch không rõ sau failover.

Không diễn đạt “near-real-time replication” như RPO bằng 0 nếu chưa có bằng chứng về commit acknowledgment và failure semantics.

## 11. BIA và RTO/RPO bằng ví dụ định lượng

Giả sử business owner phân tích chức năng booking:

- MTPD: 2 giờ.
- Hệ thống cần 30 phút để nhân viên xác minh các booking đang xử lý, reconciliation và tiếp tục chăm sóc khách (WRT).
- Doanh nghiệp muốn còn khoảng đệm 30 phút cho sự cố kéo dài hơn dự kiến.
- Mỗi booking đã xác nhận không được mất; thay đổi tồn phòng chưa xác nhận có thể được tính lại từ giao dịch nguồn.

Có thể đề xuất mục tiêu ban đầu:

~~~text
RTO target = 30 minutes
WRT target = 30 minutes
Operational buffer = 60 minutes
MTPD = 120 minutes
RPO = 1 minute (subject to transaction and replication validation)
~~~

Đề xuất chỉ có giá trị sau khi kiểm tra khả năng thực hiện và được business owner chấp thuận. Nếu kiểm thử cho thấy RTO kỹ thuật là 90 phút, tổ chức phải đầu tư thêm hoặc thương lượng lại mục tiêu/biện pháp nghiệp vụ; không nên tự ý sửa RTO thành 90 phút để hợp thức hóa kiến trúc hiện tại.

### 11.1. Ước tính tác động tài chính

Một cách hỗ trợ thảo luận là định lượng tổn thất theo khoảng thời gian:

~~~text
Estimated impact =
  lost contribution margin
  + recovery and overtime cost
  + customer compensation
  + partner/contract penalties
  + expected regulatory/remediation cost
~~~

Tránh nhân doanh thu trung bình với thời gian một cách máy móc nếu lưu lượng có mùa vụ hoặc giao dịch có thể chuyển sang thời gian sau. Nên phân tích cả chi phí trực tiếp, chi phí khắc phục và hậu quả dài hạn.

## 12. Chuyển đổi mục tiêu thành yêu cầu kỹ thuật

Sau BIA, kiến trúc sư làm việc ngược từ RTO/RPO để xác định control:

| Mục tiêu | Yêu cầu kỹ thuật có thể phát sinh |
| --- | --- |
| RTO 15 phút | IaC sẵn sàng, standby capacity, failover automation, DNS/routing TTL phù hợp, access/runbook được thử |
| RTO 1 giờ | Pilot light/warm standby, quy trình scale rõ, restore đã đo |
| RPO gần 0 | Replication/commit semantics chặt, log shipping, transaction integrity, reconciliation |
| RPO 15 phút | Backup/log archive đủ thường xuyên, lag alert, PITR và kiểm thử restore |
| MTPD dài | Có thể cân nhắc backup/restore và phương án thủ công nếu chi phí thấp hơn |
| WRT ngắn | Đối soát tự động, audit trail, idempotent replay, dữ liệu trạng thái rõ |

Một mục tiêu kỹ thuật phải có bằng chứng: test result, measured recovery time, measured data loss, capacity, failover/failback và người chịu trách nhiệm. Số liệu do nhà cung cấp quảng bá không thay thế kiểm thử trong workload và cấu hình thật.

## 13. Kịch bản sự cố và mục tiêu không giống nhau

DR không chỉ là mất toàn bộ region. Mỗi kịch bản có phạm vi và cách phục hồi khác nhau:

| Kịch bản | Tác động | Điều cần đưa vào kế hoạch |
| --- | --- | --- |
| Mất một availability zone | Compute/network/storage trong zone không sẵn sàng | Multi-zone placement, database quorum/failover, capacity còn lại |
| Mất region | Nhiều dịch vụ và control plane region bị ảnh hưởng | Cross-region data, network, DNS, identity, quota và routing |
| Database corruption | Dữ liệu logic sai nhưng service vẫn chạy | PITR, immutable backup, điểm khôi phục sạch và reconciliation |
| Ransomware/credential compromise | Backup hoặc replica có thể bị xóa/mã hóa | Immutable/offline copy, quyền tách biệt, clean-room restore |
| Lỗi deploy/configuration | Thay đổi hợp lệ về mặt hạ tầng nhưng phá chức năng | Rollback, Git/IaC history, config version, blast radius |
| Nhà cung cấp thanh toán lỗi | Một dependency bên ngoài không hoạt động | Circuit breaker, trạng thái payment unknown, fallback và reconciliation |
| Mất DNS/identity/KMS | Ứng dụng có thể chạy nhưng không điều khiển/truy cập được | Dependency dự phòng, break-glass access, key recovery |

Một RTO/RPO có thể đạt với mất zone nhưng không đạt khi ransomware. Cần nêu rõ **scenario, failure domain, phạm vi dữ liệu và điều kiện sạch** cho mỗi mục tiêu.

## 14. Failover, failback và thứ tự phục hồi

Failover là chuyển hoạt động sang môi trường dự phòng. Failback là đưa hoạt động về môi trường ưu tiên sau khi đã sửa chữa. Failback thường rủi ro hơn vì phải đồng bộ dữ liệu phát sinh khi DR đang phục vụ.

### 14.1. Runbook failover

1. Phát hiện và xác minh sự cố; tránh tuyên bố DR chỉ vì một alert đơn lẻ.
2. Business/incident commander xác định phạm vi và kích hoạt runbook theo quyền được quy định.
3. Chặn ghi hoặc cô lập nguồn cũ nếu cần để tránh split-brain.
4. Chọn điểm dữ liệu/replica hợp lệ; ghi lại RPO thực tế có thể đạt.
5. Promote database/restore service theo thứ tự dependency.
6. Khôi phục identity, secrets, network, compute, queue và endpoint.
7. Kiểm tra health kỹ thuật và giao dịch nghiệp vụ mẫu.
8. Chuyển traffic theo từng bước/canary nếu phù hợp.
9. Mở traffic và theo dõi latency, error, data consistency, backlog và payment state.
10. Ghi nhận thời gian phục hồi thực tế, điểm dữ liệu và giao dịch cần đối soát.

### 14.2. Chống split-brain

Khi cả primary và standby đều có thể nhận ghi do network partition hoặc failover sai, dữ liệu có thể phân nhánh. Cần một cơ chế xác định write authority: fencing token, quorum/lease, promotion control hoặc quy trình cô lập primary cũ. Không chỉ dựa vào việc DNS đã đổi; client/worker có thể còn kết nối tới endpoint cũ.

### 14.3. Failback

- Xác nhận region/cụm cũ sạch và đủ capacity.
- Xác định nguồn dữ liệu hiện tại có thẩm quyền.
- Replicate/copy delta từ DR về môi trường chính.
- Kiểm tra consistency, schema/version và backlog.
- Chọn cửa sổ cutover, tạm dừng hoặc điều phối write theo runbook.
- Chuyển routing và xác minh không còn writer tại site cũ.
- Theo dõi sau chuyển đổi và giữ phương án rollback.

Không failback chỉ vì region chính đã “xanh”. Phải kiểm tra rủi ro tái phát và khả năng duy trì DR sau khi chuyển.

## 15. Kiểm thử DR và chứng minh RTO/RPO

Một tài liệu runbook chưa được kiểm thử không chứng minh hệ thống có thể phục hồi. Mỗi capability quan trọng cần lịch diễn tập và bằng chứng:

| Loại kiểm thử | Phạm vi | Bằng chứng cần lưu |
| --- | --- | --- |
| Backup restore test | Khôi phục database/object từ backup | Thời gian restore, checksum, dữ liệu thiếu, quyền và kết quả query |
| PITR test | Khôi phục về thời điểm trước sự cố | Recovery point thực tế, transaction boundary và RPO |
| Component failover | Database, cache, broker hoặc service | Failover time, lỗi client, replication lag |
| Zone/region exercise | Chuyển traffic sang failure domain khác | RTO end-to-end, capacity, dependency và business transaction |
| Cyber recovery/clean-room | Khôi phục từ bản sạch sau compromise | Tách quyền, clean image, credential/key rotation, dữ liệu sạch |
| Tabletop exercise | Diễn tập quyết định, liên lạc, vai trò | Khoảng trống runbook, quyền phê duyệt, thời gian quyết định |

### 15.1. Đo đúng mốc thời gian

Ghi các timestamp:

- T0: sự cố bắt đầu (nếu xác định được).
- T_detect: hệ thống/đội vận hành phát hiện.
- T_declared: DR được tuyên bố.
- T_data: dữ liệu đạt recovery point đã chọn.
- T_service: minimum viable service sẵn sàng.
- T_business: quy trình nghiệp vụ quan trọng hoàn tất giao dịch thử.
- T_full: dịch vụ và backlog trở lại mức đầy đủ.

RTO nên được đo từ mốc bắt đầu đã thống nhất tới mức phục hồi nghiệp vụ đã định nghĩa. Báo cáo riêng thời gian phát hiện, quyết định, phục hồi kỹ thuật và WRT giúp tìm bottleneck thay vì che khuất chúng trong một con số.

### 15.2. Kiểm thử có kiểm soát

Failure injection cần có phạm vi, môi trường, người chịu trách nhiệm, stop condition và kế hoạch rollback. Không làm mất dữ liệu production hoặc ngắt traffic khách hàng khi chưa có phê duyệt/kiểm soát phù hợp. Có thể bắt đầu bằng restore test và game day ở môi trường staging tương đồng production.

## 16. Quản trị, con người và kế hoạch truyền thông

DR là quy trình tổ chức, không chỉ là automation. Phải chỉ rõ:

- Ai có quyền tuyên bố disaster và kích hoạt failover?
- Ai quyết định recovery point khi phải chọn giữa dữ liệu gần nhất và dữ liệu sạch?
- Ai xác nhận giao dịch payment/booking cần reconciliation?
- Ai thông báo khách hàng, đối tác, nhà cung cấp và cơ quan liên quan?
- Ai giữ credential break-glass và cách audit việc sử dụng?
- Khi người chủ chốt không sẵn sàng, người thay thế là ai?
- Runbook, contact list và bản sao tài liệu nằm ở đâu nếu region chính không truy cập được?

Một hệ thống DR cần account/quyền quản trị dự phòng, danh sách liên lạc ngoài failure domain, tài liệu offline/immutable và diễn tập vai trò. Không để toàn bộ thông tin cần phục hồi chỉ tồn tại trong một wiki mà không truy cập được khi SSO hoặc region chính lỗi.

## 17. Chi phí và quyết định đầu tư

RTO càng ngắn và RPO càng thấp thường yêu cầu nhiều năng lực sẵn sàng, replication nhanh, automation, kiểm thử thường xuyên và nhân sự vận hành có kỹ năng. Nhưng không phải mọi capability đều cần mức tối đa.

| Chiến lược | Chi phí duy trì | Chi phí phục hồi/độ trễ | Rủi ro cần quản lý |
| --- | --- | --- | --- |
| Backup and restore | Thường thấp hơn | Cấp hạ tầng/restore lâu hơn | Backup không restore được, thiếu capacity hoặc tài liệu |
| Pilot light | Thấp–trung bình | Cần scale/provision | Quota, provisioning time, dependency chưa chạy |
| Warm standby | Trung bình–cao | Chuyển traffic/scale nhanh hơn | Replica lag, standby thiếu capacity |
| Active-active | Cao | Có thể giảm thời gian chuyển dịch | Conflict, split-brain, consistency, vận hành phức tạp |

### 17.1. Phân tích chi phí–tác động

So sánh tổng chi phí của chiến lược DR với tổn thất kỳ vọng:

~~~text
Expected annual disruption impact =
  sum over scenarios (
    annual scenario probability
    * business impact at achieved recovery time
  )

DR investment decision =
  compare expected impact reduction
  against standby, replication, backup, testing and operating cost
~~~

Không nên coi xác suất sự cố là chính xác nếu dữ liệu lịch sử ít. Dùng khoảng/giả định và phân tích độ nhạy. Một sự cố hiếm nhưng có hậu quả pháp lý hoặc an toàn lớn vẫn có thể yêu cầu kiểm soát bắt buộc thay vì chỉ tối ưu expected value.

## 18. Bài thực hành: xây dựng BIA và mục tiêu DR cho nền tảng đặt chỗ

**Bối cảnh giả định:** nền tảng vận hành tại một region chính với ba availability zone; database booking có backup và asynchronous replica ở region khác; search index có thể tái tạo; ảnh property nằm trong object storage; thanh toán thông qua đối tác; notification xử lý qua event queue.

### Nhiệm vụ

1. Liệt kê capability nghiệp vụ và owner: identity, search, booking, payment, notification, media, analytics.
2. Thực hiện BIA cho từng capability theo tác động tài chính, khách hàng, pháp lý, vận hành và uy tín ở các mốc thời gian.
3. Xác định MTPD/MAO, RTO, WRT và RPO có giải thích; nêu ai phê duyệt mục tiêu.
4. Vẽ dependency map gồm DNS, identity, KMS/secrets, network, compute, database, object storage, broker, search và payment provider.
5. Chọn chiến lược backup/restore, pilot light, warm standby hoặc active-active theo từng capability; không bắt buộc một chiến lược cho toàn hệ thống.
6. Xác định dữ liệu cần backup/replicate, retention, immutable copy, replication lag và cách đối soát.
7. Viết runbook failover/failback, thứ tự khôi phục, fencing/split-brain và điều kiện mở traffic.
8. Lập kế hoạch kiểm thử restore, PITR, mất zone, mất region và clean-room recovery.
9. Tính chi phí duy trì so với mức giảm thiệt hại kỳ vọng; nêu các giả định và khoảng bất định.
10. Ghi ADR tóm tắt các quyết định, rủi ro còn lại và ngày diễn tập tiếp theo.

### Mẫu BIA/DR worksheet

| Capability | Tác động khi gián đoạn | MTPD | RTO | WRT | RPO | Chiến lược sơ bộ |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Booking | Mất khả năng giữ/xác nhận chỗ | Business xác định | Business xác định | Đối soát booking | Rất thấp | Warm standby hoặc giải pháp tương đương |
| Payment | Trạng thái tiền không rõ | Business xác định | Business xác định | Reconciliation | Gần 0 hoặc theo ledger | Replication/log + quy trình đối soát |
| Search | Khó tìm property | Business xác định | Business xác định | Kiểm tra chất lượng index | Có thể rebuild | Reindex từ source |
| Notification | Thông báo trễ | Business xác định | Business xác định | Xử lý backlog | Theo event retention | Queue replication/replay |
| Analytics | Báo cáo chậm | Business xác định | Business xác định | Reconcile số liệu | Có thể cao hơn | Backup/rebuild |

### Tiêu chí hoàn thành

- Mục tiêu bắt nguồn từ BIA và được business owner chấp thuận.
- RTO, RPO, MTPD và WRT được phân biệt rõ và có mốc đo.
- Dependency map bao gồm cả control plane, identity, DNS, KMS, provider và con người.
- Chiến lược dữ liệu bảo vệ transaction, object, event và backup sạch.
- Có runbook failover/failback, chống split-brain và tiêu chí mở traffic.
- Kịch bản diễn tập chứng minh thời gian và điểm dữ liệu đạt mục tiêu.
- Chi phí và rủi ro còn lại được ghi vào ADR.

## 19. Checklist Well-Architected trước khi phê duyệt DR

- [ ] Đã hoàn thành BIA với business owner và phạm vi capability rõ ràng.
- [ ] Đã xác định MTPD/MAO, RTO, RPO và WRT; có glossary và mốc đo thống nhất.
- [ ] Mục tiêu được phân theo capability, không chỉ gán một con số cho toàn ứng dụng.
- [ ] Đã lập dependency map gồm data plane, control plane, external provider và con người.
- [ ] Đã phân tích các failure scenario: zone, region, corruption, ransomware, configuration và dependency outage.
- [ ] Backup được mã hóa, tách quyền/failure domain, có retention và immutable protection phù hợp.
- [ ] Replication lag, acknowledged writes, log retention và recovery point được đo.
- [ ] Có phương án khôi phục cả database, object, event, identity, secrets, key và configuration.
- [ ] Có capacity, quota, network, DNS, certificate, artifact và quyền truy cập ở môi trường dự phòng.
- [ ] Runbook có vai trò, điều kiện tuyên bố DR, thứ tự phục hồi và tiêu chí mở traffic.
- [ ] Có fencing/write authority để tránh split-brain; failback có kế hoạch riêng.
- [ ] Có reconciliation cho booking, payment, event và backlog sau khôi phục.
- [ ] Restore/PITR/failover/failback/cyber recovery được kiểm thử định kỳ và lưu bằng chứng.
- [ ] Đo RTO end-to-end và RPO thực tế, bao gồm thời gian quyết định và WRT.
- [ ] Có kênh liên lạc, tài liệu và break-glass access độc lập failure domain chính.
- [ ] Chi phí DR được so với tác động nghiệp vụ và rủi ro còn lại.
- [ ] ADR ghi rõ đánh đổi reliability, security, performance, cost và operations.

**Điểm cốt lõi:** BIA cho biết điều gì cần được bảo vệ và hậu quả của gián đoạn; MTPD/MAO thể hiện ngưỡng chịu đựng; RTO đặt mục tiêu khôi phục dịch vụ; RPO đặt giới hạn mất dữ liệu; WRT bao gồm phần công việc cần hoàn tất sau khi hệ thống kỹ thuật hoạt động lại. Khi các mục tiêu được gắn với capability, dependency, chiến lược dữ liệu và diễn tập có đo lường, DR mới trở thành năng lực đã được chứng minh thay vì chỉ là tài liệu dự phòng.

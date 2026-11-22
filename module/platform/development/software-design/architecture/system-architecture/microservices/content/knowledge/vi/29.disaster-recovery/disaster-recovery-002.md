# Xác định mục tiêu thời gian khôi phục và mức mất dữ liệu chấp nhận trong Microservices

Trong kiến trúc microservices, một sự cố có thể bắt đầu từ một database không truy cập được, một vùng cloud bị gián đoạn, một lỗi triển khai làm sai dữ liệu, mất khóa giải mã hoặc một thao tác vận hành xóa nhầm thông tin. Hệ thống có nhiều replica vẫn có thể mất dịch vụ hoặc mất dữ liệu nếu tất cả replica phụ thuộc cùng một vùng, cùng một kho lưu trữ, cùng cơ chế xác thực hoặc cùng bản sao dữ liệu đã hỏng.

Để thiết kế **Disaster Recovery (DR) – khôi phục thảm họa**, tổ chức cần trả lời hai câu hỏi có thể đo và kiểm chứng:

1. **Ngừng phục vụ bao lâu là chấp nhận được?** Đây là cơ sở xác định **Recovery Time Objective (RTO)**.
2. **Có thể mất bao nhiêu dữ liệu mới nhất là chấp nhận được?** Đây là cơ sở xác định **Recovery Point Objective (RPO)**.

RTO và RPO không phải những giá trị công nghệ chọn trước rồi áp đặt cho doanh nghiệp. Chúng phải được xác định qua **Business Impact Analysis (BIA)**, yêu cầu tính đúng đắn dữ liệu, phụ thuộc giữa các service, chi phí, rủi ro và khả năng vận hành. Sau đó nhóm kỹ thuật mới chọn backup, replication, failover, multi-region, event replay hoặc các phương án kết hợp để đạt mục tiêu.

Bài học tập trung vào cách diễn giải, xác định, phân bổ, thiết kế và kiểm thử RTO/RPO cho hệ thống microservices, đặc biệt với database, broker, API, giao dịch tài chính, cache, dữ liệu bất đồng bộ và dependency dùng chung.

## 1. Phân biệt RTO và RPO

**RTO – Recovery Time Objective** là **mục tiêu về thời gian tối đa được chấp nhận để khôi phục một chức năng hoặc dịch vụ sau sự cố**, theo điểm bắt đầu và tiêu chí “đã phục hồi” được xác định rõ trong kế hoạch.

**RPO – Recovery Point Objective** là **mục tiêu về mức mất dữ liệu tối đa được chấp nhận tính theo thời gian**, thường biểu diễn khoảng cách thời gian giữa thời điểm xảy ra sự cố và điểm dữ liệu nhất quán gần nhất có thể khôi phục.

Ví dụ:

~~~text
09:55 ──── 10:00 ──────────────────── 10:25
  ^           ^                           ^
  |           |                           |
Bản dữ liệu   Sự cố                  Dịch vụ đạt
khôi phục     bắt đầu                tiêu chí phục hồi

RPO thực tế trong ví dụ: 5 phút.
Thời gian khôi phục thực tế: 25 phút.

Nếu mục tiêu là RPO <= 10 phút, RTO <= 30 phút:
kịch bản này đáp ứng cả hai, với điều kiện
đã kiểm tra tính nhất quán và trạng thái nghiệp vụ.
~~~

Trong thực tế, thời điểm xảy ra lỗi có thể khó xác định và thời điểm phục hồi có thể được định nghĩa khác nhau. Phải thống nhất:

- Sự cố được tính từ khi nào: thời điểm mất khả năng phục vụ, thời điểm hỏng dữ liệu, hay thời điểm được phát hiện?
- Khi nào coi là phục hồi: health check xanh, API nhận được request, xử lý được giao dịch thật, hay đạt một mức SLO tối thiểu?
- Điểm dữ liệu phục hồi có nhất quán không, có thể đọc/ghi không, và còn thiếu những side effect nào?
- Mục tiêu áp dụng với toàn hệ thống, một chức năng, một tenant hay một lớp dịch vụ?
- Mục tiêu áp dụng cho sự cố nào: một Pod, một availability zone, một region, lỗi logic, hay ransomware?

**RTO/RPO là mục tiêu, không phải kết quả bảo đảm.** Phải đo **thời gian khôi phục thực tế** và **khoảng mất dữ liệu thực tế** sau thử nghiệm hoặc sự cố rồi so sánh với mục tiêu.

## 2. Mối quan hệ với availability, MTTR, MTTD và SLA

RTO và RPO liên quan đến độ tin cậy, nhưng không đồng nghĩa các chỉ số khác.

| Thuật ngữ | Câu hỏi | Ví dụ |
| --- | --- | --- |
| RTO | Sau thảm họa, mất bao lâu để phục hồi chức năng được định nghĩa? | Checkout trong 30 phút |
| RPO | Cho phép mất bao nhiêu dữ liệu mới nhất? | Không quá 5 phút dữ liệu catalog |
| Availability SLO | Trong một kỳ, dịch vụ có sẵn sàng bao nhiêu phần trăm thời gian? | 99,9% trong tháng |
| MTTD | Trung bình cần bao lâu để phát hiện sự cố? | 3 phút |
| MTTR | Trung bình cần bao lâu để sửa hoặc phục hồi sau các sự cố? | 20 phút |
| SLA | Cam kết với bên sử dụng, có điều khoản và cách đo riêng | Cam kết dịch vụ theo hợp đồng |
| Maximum Tolerable Downtime / MTPD | Ngừng lâu đến đâu sẽ gây tác động không thể chấp nhận? | Không thể dừng thu tiền quá một khoảng quy định |

Một hệ thống có availability SLO tốt chưa chắc có RTO tốt cho thảm họa vùng. MTTD và MTTR trung bình của các lỗi thường ngày không chứng minh được có thể khôi phục dữ liệu sau khi toàn bộ region bị mất.

Không dùng công thức “RTO bằng MTTR” như một quy tắc tuyệt đối. RTO thường hướng đến tình huống và trạng thái phục hồi cụ thể; MTTR là thống kê quan sát được trên tập sự cố đã xảy ra.

### 2.1. Mức ngừng phục vụ chấp nhận được không nhất thiết bằng mất dữ liệu chấp nhận được

Ví dụ Order Service có thể tạm dừng tạo đơn trong vài phút nhưng **không được tự động mất các đơn đã được xác nhận**. Khi đó RTO có thể là vài phút, trong khi RPO đối với sổ ghi nhận giao dịch đã xác nhận đòi hỏi rất nghiêm ngặt.

Ngược lại, hệ thống recommendation có thể dựng lại chỉ mục từ dữ liệu gốc trong một giờ và chấp nhận mất một phần tín hiệu click mới nhất. Nó có RTO/RPO rộng hơn so với luồng thanh toán.

## 3. Bắt đầu từ Business Impact Analysis, không bắt đầu từ công nghệ

**Business Impact Analysis (BIA)** xác định điều gì xảy ra nếu một chức năng không hoạt động hoặc dữ liệu bị mất. Đây là nền tảng để chọn RTO/RPO có ý nghĩa.

Các câu hỏi cần trả lời cho mỗi chức năng:

1. Người dùng bị ảnh hưởng là ai? Bao nhiêu tenant, đơn hàng, giao dịch, vùng hoặc đối tác?
2. Ngừng 5, 15, 60 phút hay một ngày gây thiệt hại gì về doanh thu, hợp đồng, vận hành và uy tín?
3. Dữ liệu nào có thể tạo lại từ nguồn khác, dữ liệu nào là nguồn sự thật duy nhất?
4. Dữ liệu có liên quan tiền, tồn kho, pháp lý, quyền truy cập hoặc thông tin cá nhân không?
5. Nếu mất 5 phút ghi mới, doanh nghiệp có thể đối soát hoặc nhập lại không?
6. Có một chế độ suy giảm chức năng đủ an toàn để phục vụ một phần nhu cầu không?
7. Hệ thống có phụ thuộc API đối tác, KMS, DNS, IAM, database hay broker dùng chung không?
8. Thời gian nào trong ngày/tuần có rủi ro cao nhất, như giờ cao điểm hoặc ngày chốt sổ?
9. Người nào có quyền chấp nhận rủi ro và phê duyệt mục tiêu?
10. Mục tiêu có yêu cầu kiểm thử định kỳ và bằng chứng đáp ứng không?

BIA nên có đại diện nghiệp vụ, kỹ thuật, vận hành, bảo mật và các bên chịu trách nhiệm hợp đồng. Không để một nhóm tự chọn RPO = 0 cho tất cả dữ liệu nếu chưa hiểu chi phí và hệ quả availability của yêu cầu đó.

### 3.1. Ví dụ phân loại theo nghiệp vụ

| Chức năng | Hệ quả nếu ngừng | Hệ quả nếu mất dữ liệu | Gợi ý cách phân tích |
| --- | --- | --- | --- |
| Payment ledger | Không thể ghi nhận hoặc đối soát tiền | Rất nghiêm trọng | Cần bất biến, định danh giao dịch và đối soát; mục tiêu dữ liệu nghiêm ngặt |
| Checkout / Order | Người dùng không thể đặt hàng | Có thể mất đơn đã xác nhận | Phân biệt đơn đã xác nhận, đơn nháp, trạng thái pending |
| Inventory reservation | Có thể bán quá tồn hoặc giữ hàng sai | Có thể tạo xung đột tồn kho | Cần chính sách hòa giải và chống oversell |
| Catalog read | Trải nghiệm tìm kiếm giảm | Có thể tái tạo từ nguồn dữ liệu gốc | Có thể cache/read-only trong DR |
| Recommendations | Gợi ý kém chất lượng | Tín hiệu hoặc model có thể tính lại | Có thể tạm tắt và khôi phục sau |
| Report/analytics | Báo cáo chậm | Có thể tái xử lý từ event history | Phân biệt dữ liệu nguồn với bảng tổng hợp |
| Notifications | Email/SMS đến trễ | Có thể cần gửi bù có idempotency | Theo dõi backlog, duplicate, deadline |
| Authentication / KMS | Người dùng không đăng nhập hoặc service không giải mã được | Mất khóa có thể làm dữ liệu không thể đọc | Cần đường phục hồi độc lập và bảo mật |

Bảng không đưa ra RTO/RPO bắt buộc cho từng ngành; cần phân loại đúng yêu cầu cụ thể của hệ thống.

## 4. Định nghĩa RTO đủ chính xác để kiểm thử

Một phát biểu mơ hồ như “hệ thống phục hồi trong 30 phút” chưa đủ. RTO cần chỉ rõ phạm vi và tiêu chí đo.

Ví dụ một phát biểu có thể kiểm thử:

> Sau khi mất hoàn toàn vùng triển khai chính, trong không quá 30 phút kể từ lúc các giao dịch checkout production bắt đầu không còn được phục vụ, hệ thống phải cho phép tạo đơn hàng mới tại vùng dự phòng; các giao dịch được nhận phải được lưu bền vững, có thể tra cứu và đáp ứng ngưỡng độ trễ đã định.

Cần xác định:

- **Điểm bắt đầu:** thời điểm mất chức năng được đo từ health/business synthetic hoặc bằng chứng quan sát.
- **Điểm kết thúc:** hệ thống xử lý được một tập giao dịch đại diện, có dữ liệu cần thiết và đạt mức tối thiểu đã định.
- **Phạm vi:** một region, một cluster, hay một service; tenant/region nào thuộc mục tiêu.
- **Tỷ lệ năng lực khi phục hồi:** 100% capacity hay 30% capacity phục vụ chức năng cốt lõi trong giai đoạn DR.
- **Phụ thuộc:** xác thực, secrets, KMS, DNS, database, broker, external payment API.
- **Tác vụ còn tồn:** backlog, đối soát, indexing hay báo cáo có cần hoàn tất trước khi tính là phục hồi không?

Có thể phân biệt hai mốc:

1. **Minimum Viable Recovery:** chức năng cốt lõi trở lại, đúng dữ liệu và đạt ngưỡng phục vụ tối thiểu.
2. **Full Restoration:** đã xử lý backlog, phục hồi capacity, dịch vụ tùy chọn và trở về trạng thái vận hành bình thường.

Không dùng “health endpoint trả 200” làm tiêu chí duy nhất nếu checkout thực vẫn lỗi vì không có dữ liệu hoặc không thể gọi Payment Service.

## 5. Phân rã ngân sách thời gian RTO

RTO không chỉ là thời gian chạy một lệnh failover. Nó bao gồm tất cả bước từ khi xảy ra sự cố đến khi khôi phục chức năng được định nghĩa.

Một ngân sách ví dụ cho RTO 30 phút:

| Bước | Ngân sách minh họa |
| --- | ---: |
| Phát hiện và xác nhận sự cố | 3 phút |
| Quyết định và kích hoạt DR | 4 phút |
| Chuyển/khởi tạo data services | 8 phút |
| Khởi tạo hoặc scale application | 5 phút |
| Routing/DNS/traffic cutover | 3 phút |
| Kiểm tra dữ liệu và giao dịch nghiệp vụ | 5 phút |
| Dự phòng sai lệch và chậm trễ | 2 phút |
| **Tổng** | **30 phút** |

Đây chỉ là một ví dụ hoạch định; thời gian thực tế phụ thuộc công nghệ, quá trình xác minh và sự cố đồng thời. Đối với kế hoạch recovery thủ công, thời gian liên hệ người trực, xin phê duyệt, mở quyền quản trị hoặc tạo credential cũng nằm trong ngân sách. Nếu tự động hóa, cần kiểm thử hành vi khi dependency hoặc control plane không khả dụng.

### 5.1. Đường găng khôi phục (recovery critical path)

Không phải mọi service phải khôi phục theo thứ tự. Một số việc có thể chạy song song; những việc khác phụ thuộc dữ liệu hoặc hạ tầng nền tảng.

~~~text
Incident detection
       |
       v
DR declaration
       |
       +---> Activate standby database ----+
       |                                    |
       +---> Activate IAM/KMS/secrets ------+--> Start critical APIs
       |                                    |          |
       +---> Restore broker/queues ---------+          v
       |                                          Business smoke test
       +---> Routing / DNS preparation -------------> Traffic cutover
                                                              |
                                                              v
                                                  RTO stop criterion
~~~

Cần tìm **critical path** thật qua diễn tập; cộng mọi thời gian một cách máy móc có thể thừa, nhưng bỏ sót phụ thuộc chung có thể làm ước tính quá lạc quan.

Nếu DNS TTL là 60 giây, không thể suy ra mọi client sẽ đổi endpoint sau đúng 60 giây. Resolver, client connection pooling, caching và chính sách mạng có thể kéo dài cutover. Đo thời gian route tới đích mới qua client đại diện.

## 6. Định nghĩa RPO và điểm dữ liệu khôi phục nhất quán

RPO là khoảng mất dữ liệu chấp nhận theo thời gian, không phải lượng MB mà storage có thể mất.

~~~text
11:00  Dữ liệu nhất quán được sao lưu/replicate
11:04  Giao dịch A đã commit
11:07  Giao dịch B đã commit
11:10  Sự cố làm mất primary
11:17  Mở database ở vùng dự phòng tại điểm 11:00

Khoảng cách dữ liệu = 10 phút.
Giao dịch A/B có thể cần phục hồi, replay hoặc đối soát.
~~~

Nếu mục tiêu RPO = 5 phút, tình huống này **không đạt**, dù RTO chỉ 7 phút. Mở dịch vụ nhanh trên dữ liệu quá cũ không phải khôi phục thành công toàn diện.

### 6.1. RPO không bằng lịch backup

Đặt backup mỗi 5 phút **không tự đảm bảo RPO 5 phút** vì:

- Job có thể chạy chậm hoặc thất bại.
- Backup có thể không được xác minh/không phục hồi được.
- Bản backup không nhất quán ở mức transaction.
- Data/log cần cho point-in-time recovery có thể thiếu.
- Backup và nguồn dữ liệu có thể bị mã hóa độc hại hoặc cùng bị xóa.
- Mất nguồn lưu backup hoặc khóa giải mã có thể khiến bản sao không dùng được.

Phải đo **điểm khôi phục nhất quán mới nhất có thể sử dụng** chứ không chỉ timestamp “backup started”.

### 6.2. RPO nên theo nhóm dữ liệu, không theo tên service một cách máy móc

Một Order Service có thể chứa:

- **Order ledger và trạng thái đã xác nhận:** dữ liệu quan trọng.
- **Draft carts:** có thể chấp nhận mất hoặc tái tạo một phần theo hợp đồng.
- **Cache tra cứu:** có thể làm nóng lại.
- **Materialized read model:** có thể dựng lại từ event/database nguồn.
- **Audit records:** có yêu cầu lưu và toàn vẹn riêng.
- **Search index:** có thể reindex sau.

Không nên cấp RPO như nhau cho mọi byte. Xác định **nguồn sự thật (system of record)** và khả năng tái tạo rồi chọn công nghệ tương ứng.

### 6.3. RPO bằng 0 có ý nghĩa gì?

**RPO = 0** thường biểu thị mục tiêu không mất những giao dịch đã được xác nhận trong phạm vi sự cố và điểm nhất quán được định nghĩa. Đây là mục tiêu khó, chi phí cao, cần làm rõ consistency, acknowledgment và failure model.

Replication đồng bộ có thể giảm nguy cơ mất giao dịch đã được xác nhận trong một số tình huống, nhưng thường làm tăng latency, phụ thuộc availability của replica/quorum và vẫn cần bảo vệ khỏi lỗi logic, xóa nhầm, lỗi đồng thời hoặc sự cố cùng miền.

Không tuyên bố “RPO 0 tuyệt đối” cho toàn hệ thống phân tán chỉ vì đã bật synchronous replication một database. Broker, cache, outbox, object storage và side effect đến đối tác có thể có trạng thái khác nhau.

## 7. Mối quan hệ giữa RTO và RPO

Hai mục tiêu độc lập nhưng thường có trade-off về chi phí, độ phức tạp và consistency.

| Phương án | Đặc tính RTO thường thấy | Đặc tính RPO thường thấy | Lưu ý |
| --- | --- | --- | --- |
| Backup định kỳ, dựng hạ tầng khi sự cố | Lâu hơn | Tùy tần suất và khả năng restore | Rẻ nhưng cần nhiều bước và phải kiểm thử |
| Pilot light | Trung bình | Phụ thuộc replication/backup | Dữ liệu nền tảng có sẵn, ứng dụng cần scale/khởi động |
| Warm standby | Ngắn hơn | Có thể thấp nếu replication kịp | Tốn tài nguyên chờ và có drift |
| Hot standby/active-passive | Có thể ngắn | Theo replication và promote process | Cần kiểm soát split-brain/fencing |
| Active-active nhiều vùng | Có thể rất ngắn với một số lớp | Phụ thuộc consistency/quorum | Xung đột ghi, routing và operational complexity |
| Async cross-region replication | Có thể khôi phục nhanh | Có khả năng mất phần chưa replicate | Đo replication lag tại thời điểm lỗi |
| Synchronous/quorum replication | Có thể giữ dữ liệu chặt hơn | Gần 0 cho phạm vi ack được định nghĩa | Tăng latency và nguy cơ write unavailability |

Đây là xu hướng khái niệm, **không phải SLA mặc định của các công nghệ**. Mọi kiến trúc đều phải kiểm thử với dữ liệu và sự cố tương ứng.

Một RTO 15 phút cùng RPO 1 giờ có thể khả thi với warm standby và backup/replication phù hợp. Một RTO 4 giờ cùng RPO 0 có thể cần giao thức ghi bền vững chặt chẽ dù việc khởi động ứng dụng được phép chậm. Tối ưu một mục tiêu không tự đạt mục tiêu kia.

## 8. Phân tầng dịch vụ và xác định mục tiêu thực tế

Có thể thiết kế các **recovery tiers** theo tác động, nhưng mọi số đều cần BIA phê duyệt.

| Tier minh họa | Dịch vụ | RTO mục tiêu ví dụ | RPO mục tiêu ví dụ | Hướng thiết kế |
| --- | --- | ---: | ---: | --- |
| Tier 0 | Ghi nhận giao dịch tài chính đã xác nhận | 15 phút | Không mất giao dịch đã được xác nhận trong phạm vi xác định | Transactional consistency, HA/DR, audit và reconciliation |
| Tier 1 | Checkout / Order creation | 30 phút | 5 phút, hoặc chặt hơn với dữ liệu đã xác nhận | Warm standby, failover, event reconciliation |
| Tier 2 | Catalog/Search | 2 giờ | 30 phút | Replication + cache, tái tạo index |
| Tier 3 | Reports/Analytics | 24 giờ | 24 giờ, nếu có nguồn replay | Backup + rebuild từ nguồn sự thật |

**Các số hoàn toàn minh họa**, không phải tiêu chuẩn bắt buộc. Ví dụ chính sách nghiêm ngặt với tiền có thể yêu cầu không mất giao dịch được xác nhận; nhưng vẫn phải xác minh khả năng đạt dưới failure mode đã chỉ định.

Không nên chỉ gắn tier cho tên microservice. Một service có nhiều nhóm dữ liệu và API, phải chỉ rõ chức năng nào thuộc tier nào. Nếu Report Service là nguồn duy nhất của sổ kiểm toán bắt buộc, nó không còn thuộc tier thấp chỉ vì tên chứa “Report”.

### 8.1. Mục tiêu cho hệ thống phụ thuộc nhau

Checkout có RTO 30 phút nhưng IAM, DNS, KMS hoặc Payment Service có RTO 4 giờ sẽ khó đạt mục tiêu đã công bố nếu các dependency đó bắt buộc phải sẵn sàng.

Tạo **dependency graph** và xác định minimum viable path:

~~~text
Checkout recovery
    |
    +--> API Gateway + routing
    +--> Authentication / Authorization
    +--> Order DB + consistent data
    +--> Payment state and provider connectivity
    +--> Inventory reservation mechanism
    +--> Key management / secrets
    +--> Event broker hoặc durable outbox
~~~

Dịch vụ tùy chọn như recommendation có thể bị tạm tắt. Dịch vụ liên quan tính đúng đắn tiền hoặc tồn kho không thể được thay bằng dữ liệu giả nếu làm sai giao dịch.

## 9. Xác định tập kịch bản thảm họa

RTO/RPO chỉ có nghĩa khi gắn với **phạm vi sự cố**.

| Kịch bản | Tác động | Vấn đề cần giải quyết |
| --- | --- | --- |
| Một Pod crash | Mất một replica | Readiness, replica, restart, tải còn lại |
| Một node/AZ lỗi | Mất nhóm Pod hoặc storage | Topology, quorum, zonal failover |
| Database primary lỗi | Write path gián đoạn | Replication, promotion, client reconnect |
| Mất toàn bộ region | Nhiều hạ tầng cùng mất | Cross-region data, KMS, DNS, cluster, network |
| Lỗi migration/xóa nhầm | Dữ liệu đã bị sửa sai | Point-in-time restore, logical recovery |
| Ransomware/credential compromise | Bản chính và một số backup bị phá | Immutable backup, quyền tách biệt, recovery sạch |
| Broker mất dữ liệu | Event/offset/queue không còn | Durability, replay, outbox, dedupe |
| Sự cố nhà cung cấp ngoài | Thanh toán/SMS không hoạt động | Degraded operation, pending state, alternative provider |
| Secret/KMS key bị xóa hoặc hết hiệu lực | Không giải mã/khởi động service | Key recovery, IAM, credential lifecycle |
| Lỗi triển khai đồng loạt | Mọi Pod cùng chạy code sai | Progressive delivery, rollback, dữ liệu tương thích |

Một kiến trúc chống lỗi node tốt chưa chắc chống mất region. Cơ chế tự động failover có thể còn làm tình hình tệ hơn nếu phát hiện sai và cho hai primary cùng ghi.

Cần ưu tiên kịch bản theo xác suất, mức thiệt hại và miền lỗi chung (failure domain). Mỗi kịch bản quan trọng cần mục tiêu, người chịu trách nhiệm và bước diễn tập riêng.

## 10. Kiến trúc backup: đặt RPO dựa trên bản có thể khôi phục

Backup không chỉ là sao chép file database. Cần bảo toàn tính nhất quán, khả năng truy xuất, mã hóa và chuỗi phục hồi đầy đủ.

Các hình thức:

- **Full backup:** ảnh/chụp toàn bộ dữ liệu ở một thời điểm nhất quán theo cơ chế công cụ.
- **Incremental/differential backup:** chỉ thay đổi so với mốc theo quy tắc, phụ thuộc chuỗi bản sao.
- **Transaction/WAL log archiving:** giúp point-in-time recovery trong phạm vi log được lưu và cơ chế DB hỗ trợ.
- **Snapshot storage:** có thể nhanh, nhưng phải xác định mức nhất quán (crash-consistent hay application-consistent).
- **Object/version backup:** bảo vệ files, object versions, attachments và metadata riêng.
- **Configuration/IaC backup:** cần có manifest, schema, secrets reference, policy và automation để dựng lại.
- **Key recovery:** backup có mã hóa nhưng không còn quyền/khóa để giải mã thì không hữu dụng.

### 10.1. Quy tắc 3-2-1 và khả năng bất biến

Một nguyên tắc thường gặp là có ít nhất ba bản dữ liệu, trên hai loại phương tiện/hệ thống, với một bản ở ngoài miền lỗi chính. Trong hệ cloud, cách diễn giải cụ thể có thể là live dataset, bản sao độc lập và backup ngoài region/account.

Cần đánh giá **immutable/WORM backup**, quyền xóa tách biệt, thời hạn giữ, audit, MFA/phê duyệt cho thao tác phá hủy và khả năng chống xóa đồng thời nhiều bản sao. Không coi “cross-region replication” là bản backup không thể sửa: nếu xóa nhầm được replicate sang nơi dự phòng, cả hai nơi có thể cùng mất dữ liệu.

### 10.2. Lịch backup không đủ để chứng minh RPO

Ví dụ policy:

~~~text
Full backup: 1 lần/ngày
WAL log archive: liên tục hoặc theo chu kỳ ngắn
Retention: 30 ngày
Cross-region copy: có

Mục tiêu: khôi phục tới điểm không quá 5 phút trước sự cố.
~~~

Muốn khẳng định đáp ứng, phải đo tuổi log được lưu **và** restore thử tới điểm nhất quán. Nếu WAL archive đứt 20 phút, RPO thực có thể tệ hơn mục tiêu dù full backup vẫn chạy đúng giờ.

Retention 30 ngày giải quyết câu hỏi “có thể quay về quá khứ bao xa”, khác với RPO “có thể mất bao nhiêu dữ liệu mới nhất”.

## 11. Replication: ít mất dữ liệu hơn nhưng có bẫy

### 11.1. Replication bất đồng bộ

Primary xác nhận write sau khi commit theo cơ chế của nó, replica nhận thay đổi sau.

~~~text
Primary region                   Standby region
  Commit T1
  Commit T2 ----- replication ---->
  Commit T3
  ACK cho client
  ... mất primary trước khi T3 tới standby ...

Failover tại standby:
  T3 có thể chưa tồn tại ở standby.
~~~

**Replication lag** trực tiếp ảnh hưởng RPO của dữ liệu được khôi phục. Đo lag theo mốc commit/LSN/sequence hoặc replay position phù hợp, không chỉ dựa vào latency mạng.

Khi tăng tải hoặc network nghẽn, lag có thể tăng mạnh đúng lúc cần DR nhất. Cần alert trước khi vượt RPO budget.

### 11.2. Replication đồng bộ/quorum

Primary có thể chờ số replica cần thiết xác nhận trước khi coi write hoàn tất theo cấu hình consistency. Cách này giảm nguy cơ mất dữ liệu đã được xác nhận trong **phạm vi failure model và acknowledgment đã định nghĩa**, nhưng có đánh đổi:

- Write latency tăng theo RTT và cơ chế xác nhận.
- Nếu replica/quorum không sẵn sàng, write có thể chậm hoặc không thể tiếp tục.
- Cần cơ chế leader election và fencing ngăn split-brain.
- Synchronous replication không tự bảo vệ khỏi logical corruption được nhân rộng.
- RPO của toàn workflow còn phụ thuộc broker, object storage và external side effects.

Không quảng bá đồng bộ như giải pháp RPO 0 toàn hệ thống mà không có bằng chứng đo/kiểm thử.

## 12. Split-brain và yêu cầu fencing

Trong failover, nguy cơ nguy hiểm là **primary cũ vẫn ghi** trong khi standby đã được promote và nhận write mới.

~~~text
Primary A ---- kết nối gián đoạn ---- Standby B

Hệ thống tưởng A đã mất và promote B.
Nhưng A vẫn có client đang ghi.

A và B đều nhận lệnh cập nhật
=> hai lịch sử dữ liệu khác nhau.
~~~

**Fencing** là cơ chế ngăn primary cũ tiếp tục ghi trước khi/đồng thời với việc chuyển quyền leader: dừng quyền truy cập storage, revoke token/lease, block traffic hoặc cơ chế quorum/epoch theo công nghệ. Việc chọn primary mới cần tránh trường hợp hai writer hợp lệ cùng tồn tại.

Failover “nhanh” mà không kiểm soát split-brain có thể gây mất dữ liệu nghiêm trọng hơn một khoảng outage ngắn có kiểm soát.

Kế hoạch DR phải mô tả cách xác nhận leader duy nhất và hành vi client khi DB endpoint thay đổi, connection pool còn giữ kết nối cũ hoặc DNS cache chưa hết.

## 13. RPO của toàn workflow event-driven

Microservices thường có dữ liệu nằm trên nhiều hệ thống. Ví dụ:

~~~text
Client
  |
  v
Order Service
  |
  +--> PostgreSQL: orders + outbox
  |
  +--> Outbox publisher --> Kafka/RabbitMQ
                                |
                                +--> Inventory Consumer --> Stock DB
                                |
                                +--> Payment Consumer --> Payment State
                                |
                                +--> Notification Consumer --> Email
~~~

Giả sử Order DB được khôi phục về 11:00 nhưng broker vẫn chứa events tới 11:04, còn Inventory DB ở 11:02. Các thành phần có thể mất cân bằng:

- Broker có event tham chiếu order không còn ở DB.
- Order DB có đơn đã ghi nhưng event chưa được replay.
- Payment provider đã thu tiền nhưng trạng thái nội bộ bị mất.
- Consumer nhận event lần hai sau khi offset/ack state bị khôi phục.
- Notification đã gửi email, replay có thể gửi lại nếu thiếu idempotency.

**RPO của một bảng riêng không bảo đảm consistency của toàn workflow.** Kế hoạch phải chỉ ra nguồn sự thật, checkpoint/transaction IDs, thứ tự phục hồi, cơ chế replay, idempotency và reconciliation.

### 13.1. Transactional Outbox

Một cách giảm khoảng trống DB–broker là ghi business record và outbox event **cùng một DB transaction**:

~~~text
BEGIN
  INSERT orders
  INSERT outbox_events
COMMIT

Sau đó publisher gửi event theo outbox.
Nếu publisher lỗi, event vẫn có thể được gửi lại.
~~~

Outbox giúp giữ ý định phát sự kiện sau commit; nó **không loại bỏ mọi duplicate**. Khi failover và replay, consumer vẫn phải idempotent.

### 13.2. Idempotency và reconciliation

- Gán stable event ID, payment idempotency key, order ID và transaction reference.
- Tạo unique constraint/processed-events record theo ranh giới tiêu thụ.
- Cho phép reprocess an toàn theo thiết kế.
- Đối chiếu với nguồn ngoài như payment gateway khi trạng thái UNKNOWN.
- Không suy ra “payment failed” chỉ vì timeout hoặc trạng thái nội bộ bị restore về quá khứ.
- Có quy trình xử lý xung đột và thao tác bù trừ nếu workflow đã tạo side effect.

Trong tài chính, một lỗi RPO có thể được bù bằng log và reconciliation với đối tác, nhưng điều đó không đồng nghĩa “không có mất dữ liệu”; phải định nghĩa rõ phạm vi dữ liệu cần phục hồi và tiêu chí chấp nhận rủi ro.

## 14. Giao dịch trong quá trình mất vùng: chặn ghi sai hoặc ghi trùng

Giả sử Payment Service gọi external provider, nhận timeout khi vùng đang mất kết nối. Không biết provider đã xử lý charge hay chưa.

Một phương án DR an toàn cần:

1. Giữ trạng thái giao dịch là PENDING/UNKNOWN thay vì tự đánh dấu FAILED.
2. Lưu idempotency key và external reference theo chính sách dữ liệu quan trọng.
3. Khi phục hồi, query/reconcile kết quả với provider.
4. Chỉ retry khi có căn cứ và sử dụng cùng idempotency key theo hợp đồng provider.
5. Đảm bảo không tạo side effect thanh toán kép khi client gửi lại request.
6. Kiểm tra integrity của ledger trước khi cho phép xử lý tiếp.

RTO không được tối ưu bằng cách bỏ qua tính đúng đắn tiền. Nếu chưa thể xác nhận transaction history, có thể cần đưa một phần hệ thống vào chế độ đọc hoặc tạm dừng thao tác rủi ro cao.

## 15. Active-passive, warm standby và active-active

### 15.1. Backup and restore

~~~text
Region A: Production
Region B: Backup files + IaC, chưa có ứng dụng đủ năng lực

Sự cố -> dựng hạ tầng -> restore data -> start services
       -> kiểm thử -> chuyển traffic
~~~

Ưu điểm: chi phí hạ tầng chờ thấp hơn. Nhược điểm: phải thử restore, nhiều bước có thể khiến RTO dài. Phù hợp chức năng RTO rộng nếu BIA chấp nhận.

### 15.2. Pilot light

Một số thành phần nền tảng như database/replication hoặc hạ tầng tối thiểu có sẵn; app tier có thể scale sau khi sự cố.

Ưu điểm: rút ngắn thời gian dựng data plane. Nhược: startup, scale, DNS và xác minh vẫn tốn thời gian; pilot light quá nhỏ có thể không đạt minimum viable capacity.

### 15.3. Warm standby

Vùng dự phòng có hệ thống chạy với capacity thấp hơn, dữ liệu được replicate liên tục, secrets/network/control plane đã chuẩn bị.

Ưu: RTO có thể ngắn hơn. Nhược: chi phí tăng, cần kiểm tra compatibility và data lag.

### 15.4. Active-passive hot standby

Vùng B sẵn sàng nhận traffic và có cơ chế promote/routing. Tốc độ failover phụ thuộc phát hiện, xác nhận leader, promote DB và cutover; không tự bằng 0.

### 15.5. Active-active

Hai hoặc nhiều vùng cùng phục vụ traffic. Có thể giảm failover time cho các chức năng stateless, nhưng dữ liệu ghi nhiều vùng cần quyết định consistency, xung đột, partition tolerance và sở hữu tenant/shard.

**Active-active không tự có RPO 0.** Khi network partition xảy ra, hệ thống phải chọn giữa tiếp tục ghi ở nhiều nơi với chính sách hòa giải, hoặc từ chối một phần write để bảo vệ tính nhất quán. Cần xác định rõ bảo đảm nghiệp vụ cho từng loại dữ liệu.

## 16. Thiết kế DR theo failure domain

**Failure domain** là tập thành phần có thể cùng lỗi bởi một nguyên nhân: một máy, rack, AZ, region, tài khoản cloud, IAM/control plane, KMS, mạng, nguồn cấu hình hoặc quy trình deploy.

Một kế hoạch multi-AZ không bao phủ mất toàn bộ region. Multi-region nhưng dùng chung một IAM credential bị thu hồi hoặc một kho secret bị xóa vẫn có single point of failure.

Cần kiểm kê:

- Runtime: container cluster, node pool, image registry, infrastructure as code.
- Network: DNS, traffic manager, WAF, ingress, certificate, routing.
- Identity: IAM, workload identity, authorization service.
- Key management: encryption keys, certificates, key rotation, access grants.
- Data: relational DB, object storage, cache, search, OLAP warehouse.
- Messaging: queues/topics, consumer offset/ack state, schema registry.
- Observability: logs, metrics, trace, incident alerting, runbooks.
- Dependencies: payment provider, email/SMS, fraud engine, third-party APIs.
- People/process: on-call, approval, access to console, credentials và kênh liên lạc.

Hệ thống có thể chạy ổn ở vùng dự phòng nhưng không phục vụ được request nếu KMS giải mã không khả dụng hoặc artifact image chỉ có tại region cũ.

## 17. Khả năng phục hồi dữ liệu phải xét cả logic corruption

Replication đưa dữ liệu mới đến vùng khác rất hữu ích cho lỗi vật lý, nhưng nó cũng có thể đưa **DELETE nhầm**, bug ghi sai hoặc ransomware-encrypted data sang replica.

Ví dụ:

~~~text
12:00  Database primary khỏe.
12:01  Migration lỗi xóa mất bảng quan trọng.
12:02  Replication chuyển DELETE sang standby.
12:03  Ứng dụng mất dữ liệu tại cả primary và standby.
~~~

Trong tình huống này, failover sang standby không giúp vì dữ liệu đã cùng bị phá hủy. Cần **point-in-time recovery** hoặc bản backup độc lập trước 12:01 và quy trình kiểm tra tính đúng.

Có thể phải chọn restore point **trước thời điểm bị corruption**, khiến mất nhiều dữ liệu hợp lệ mới hơn. Kế hoạch cần cách giữ hoặc replay các giao dịch hợp lệ sau restore point, dựa trên nguồn tin cậy. RPO thực của lỗi logic thường khó hơn lỗi mất primary đơn thuần.

## 18. Data retention, backup window và các bản sao quan trọng

Một hệ thống microservices có nhiều dữ liệu ngoài database chính:

- Files, hình ảnh sản phẩm, hóa đơn PDF và object metadata.
- API/worker config, secrets và certificate.
- Search index, cache, session.
- Event topics, queues, DLQ, consumer offsets.
- Outbox/inbox tables.
- Audit logs và security events.
- Database schema version và migration history.
- Docker/container image, Helm/Kubernetes manifests, Terraform state.
- Tenant routing/shard directory.
- Feature flag và entitlement configuration.

Mỗi loại cần xác định:

| Dữ liệu | Nguồn sự thật? | Khôi phục bằng gì? | Yêu cầu đặc biệt |
| --- | --- | --- | --- |
| Orders | Có | Backup, WAL, replication | Consistent commit, idempotency |
| Payment ledger | Có hoặc liên kết external | Ledger backup + provider reconciliation | Không tạo charge trùng |
| Search index | Thường là derived data | Reindex từ dữ liệu nguồn | Capacity rebuild, có thể chạy degraded |
| Cache | Thường là derived data | Rewarm/recompute | Tránh thundering herd |
| Event log | Có thể là nguồn replay | Replicated retained log/backup | Offset, schema, duplicate |
| Object attachments | Có thể là nguồn sự thật | Versioned object backups | Metadata/object consistency |
| Config/secrets | Bắt buộc để khởi động | IaC + secret/key recovery | RBAC, không lộ credential |
| Audit records | Theo yêu cầu tuân thủ | Immutable/log archive | Integrity và retention |

Không phải mọi cache cần RPO nghiêm ngặt, nhưng quá trình cache rewarm có thể làm RTO dài hơn vì DB bị quá tải. Đừng bỏ qua thời gian rebuild derived data nếu chức năng phục hồi phụ thuộc vào chúng.

## 19. Kế hoạch phục hồi thứ tự phụ thuộc

Một runbook thường cần có thứ tự ưu tiên, không nhất thiết khởi động mọi service đồng thời.

Ví dụ cho hệ thống commerce:

1. **Xác nhận phạm vi sự cố:** primary có thực sự mất quyền ghi, có data corruption hoặc security incident không?
2. **Kích hoạt DR:** ghi nhận decision, incident ID, người chỉ huy, quyền truy cập và thông tin cho bên liên quan.
3. **Fencing primary cũ:** ngăn split-brain trước khi promote nếu kiến trúc yêu cầu.
4. **Identity/KMS/secrets:** xác nhận service ở vùng dự phòng có quyền cần thiết và key material hợp lệ.
5. **Database/order ledger:** chọn recovery point, promote/restore, kiểm tra commit consistency và schema.
6. **Broker và outbox:** xác định sự kiện cần replay, offset, DLQ và tình trạng idempotency.
7. **Core APIs:** khởi động auth, order, inventory, payment theo phụ thuộc đã thống nhất.
8. **Routing:** chuyển traffic có kiểm soát, readiness và synthetic transaction xác minh.
9. **Business validation:** tạo và tra cứu đơn thử nghiệm, kiểm tra trạng thái thanh toán, inventory và tenant isolation.
10. **Hạn chế chức năng phụ:** recommendation/report được bật sau nếu dữ liệu hoặc capacity chưa đủ.
11. **Backlog/reconciliation:** xử lý giao dịch pending, event replay, index rebuild theo tốc độ an toàn.
12. **Giao tiếp và theo dõi:** cập nhật trạng thái, đo RTO/RPO thực và theo dõi lỗi tái phát.

Runbook phải nêu rõ: người thực hiện, precondition, lệnh/hành động, kết quả mong đợi, điều kiện dừng, phê duyệt, rollback của bước và kênh liên lạc. Không chỉ ghi “promote DB and restart services”.

## 20. Khi nào có thể dùng chế độ suy giảm tính năng?

DR không nhất thiết chờ mọi thành phần hoàn hảo mới phục hồi phần lõi.

Một số lựa chọn hợp lệ theo hợp đồng nghiệp vụ:

- Catalog có thể dùng bản đọc cache đã đánh dấu stale phù hợp, khi không ảnh hưởng giá hoặc tồn kho bắt buộc.
- Search có thể trả kết quả hạn chế hoặc tạm ẩn bộ lọc nâng cao.
- Recommendation có thể bị tắt.
- Report/export có thể tạm dừng và để queue chờ.
- Notification có thể được xử lý bù khi broker phục hồi.

Nhưng một số hành vi **không thể “hạ cấp” một cách tùy tiện**:

- Không tự nhận payment thành công nếu chưa biết trạng thái thực.
- Không tạo order confirmed khi chưa thể ghi bền vững hoặc giữ invariant theo hợp đồng.
- Không giải mã bằng key không được phép hoặc bỏ xác thực dữ liệu vì KMS lỗi.
- Không sửa số dư/tồn kho dựa trên snapshot cũ nếu có nguy cơ mất tính đúng đắn.

**Minimum viable recovery** nên giữ chức năng quan trọng với tính đúng đắn và mức SLO tối thiểu đã chấp nhận; không phải cho tất cả endpoint trả HTTP 200.

## 21. DR cho microservices: mục tiêu toàn workflow

Giả sử có mục tiêu: “Checkout RTO 30 phút, RPO 5 phút”.

Để áp dụng, cần làm rõ:

- Checkout API có hoạt động mà không có recommendation không? Nếu có, recommendation RTO có thể lớn hơn.
- Order DB có recovery point trong 5 phút không?
- Inventory DB và reservation state có cùng consistency boundary không?
- Broker có lưu event đủ để replay từ recovery point không?
- Payment provider đã xử lý những request nào khi primary hỏng?
- API client có retry với idempotency key không?
- Có cần trạng thái pending cho đơn chưa rõ kết quả không?
- Dữ liệu của tenant A/B có được định tuyến về đúng shard ở vùng dự phòng không?
- KMS, DNS, gateway, database credential có sẵn ở vùng B không?
- Nếu một consumer bị lùi offset, hệ thống có chống double charge và double notification không?

Nếu chỉ đo thời gian restart Order Service mà không xác nhận các điều trên, có thể báo “RTO đạt” sai lệch.

### 21.1. Định nghĩa phục hồi theo business transaction

Một synthetic test nên kiểm tra luồng có ý nghĩa:

~~~text
Authenticate test tenant
  -> Create order request with unique idempotency key
  -> Persist order
  -> Read back consistent order state
  -> Reserve inventory theo policy
  -> Process/record payment test outcome
  -> Observe event/outbox state
  -> Confirm result in expected deadline
~~~

Dùng tài khoản và dữ liệu thử nghiệm được kiểm soát, không tạo charge thật vô tình. Một số bước cần mock/sandbox provider theo thiết kế; khi mục tiêu là kiểm tra kết nối production thật, phải có cơ chế test an toàn được đối tác cho phép.

## 22. Observability cho RTO và RPO

Không đo thì không thể biết chiến lược có đạt mục tiêu.

### 22.1. Các tín hiệu RTO

- Thời điểm phát hiện outage của chức năng quan trọng.
- Thời gian đến khi sự cố được declare và bắt đầu DR.
- Thời gian promote/restore database.
- Thời gian khởi động/scale ứng dụng và phục hồi readiness.
- Thời gian DNS/routing chuyển đến vùng mới.
- Thời gian business synthetic transaction đầu tiên thành công.
- Thời gian đến khi đạt yêu cầu tối thiểu về throughput/latency/error rate.
- Số giao dịch bị treo hoặc cần đối soát sau failover.

### 22.2. Các tín hiệu RPO

- Tuổi của restore point nhất quán gần nhất.
- Last successful backup và last verified restore.
- DB replication/apply lag, WAL archive lag hoặc log sequence lag.
- Object storage replication lag và số object chưa replicate.
- Broker end offset/consumer offsets, data retention và backlog.
- Outbox oldest pending event age.
- Chênh lệch transaction IDs giữa primary/recovery target.
- Số giao dịch xác nhận bị thiếu và đã được reconcile.

Mốc thời gian phải dùng clock đáng tin cậy, có cùng timezone/UTC và xử lý skew. Khi cần xác định chính xác dữ liệu bị thiếu, sử dụng transaction/sequence identifiers thay vì dựa duy nhất vào timestamp.

### 22.3. Alert theo ngưỡng recovery objective

Ví dụ:

~~~text
Nếu RPO mục tiêu là 5 phút:
  Alert cảnh báo khi replication/recoverable lag tiến gần ngưỡng.
  Escalate khi không còn bảo đảm recoverable point trong 5 phút.

Nếu RTO mục tiêu là 30 phút:
  Alert sớm khi core journey outage.
  Đo từng bước detection/declare/failover/validate.
  Cảnh báo khi ngân sách còn lại nhỏ so với bước chưa hoàn thành.
~~~

Các ngưỡng cụ thể phải được chọn theo BIA, tải và giới hạn hệ thống. “Replication lag dưới 5 phút” chưa đủ nếu backup corrupt, consumer state thiếu hoặc có một nguồn dữ liệu quan trọng không được replicate.

## 23. RPO thực tế sau sự cố được xác định ra sao?

Một cách tính có thể kiểm chứng:

1. Xác định thời điểm cuối cùng chức năng ghi có thể nhận giao dịch hợp lệ trước sự cố (mốc theo policy).
2. Xác định recovery point cuối cùng **nhất quán và truy xuất được** tại nơi phục hồi.
3. So sánh các commit identifiers, offsets, objects hoặc transaction log positions.
4. Liệt kê giao dịch được xác nhận ở nguồn nhưng chưa có ở nơi phục hồi.
5. Đánh giá có thể tái tạo an toàn từ event log, outbox, provider hoặc audit trail không.
6. Chỉ sau reconciliation mới kết luận mức mất dữ liệu ròng và trạng thái business correctness.

Ví dụ không nên tuyên bố “RPO 0” chỉ vì timestamp bản sao là 12:00 khi sự cố bắt đầu 12:00. Có thể còn transaction được xác nhận tại primary nhưng chưa tới replica, hoặc dữ liệu xuất sang object storage/broker không cùng transaction boundary.

### 23.1. RPO dưới góc nhìn người dùng

Khi user nhận HTTP 201 Created với order ID, họ có kỳ vọng đơn hàng đã được ghi theo hợp đồng. Nếu sau DR đơn biến mất, đó là sự cố mất dữ liệu có tác động rõ ràng hơn việc mất một cart nháp chưa xác nhận.

Do đó RPO nên liên hệ với **điểm xác nhận giao dịch (acknowledgment boundary)**, không chỉ mốc ghi nội bộ. Với tác vụ async HTTP 202 Accepted, phải xác định “đã tiếp nhận bền vững” nghĩa là gì; nếu job chưa được lưu nhưng API đã trả 202, có thể đã vi phạm hợp đồng.

## 24. Chi phí và tính khả thi: chọn mục tiêu không quá tùy tiện

Mục tiêu càng nghiêm ngặt thường càng tốn:

- **RTO ngắn:** phải có hạ tầng sẵn, automation, runbook, dữ liệu và đội trực.
- **RPO ngắn:** replication/log shipping/consistent checkpoints thường xuyên, nhiều bản sao và bảo vệ điểm phục hồi.
- **RPO rất gần 0:** consistency chặt hơn, chi phí latency/write availability và phức tạp failover.
- **RTO ngắn cùng capacity cao:** cần dự trữ đủ node/DB throughput và khả năng chuyển traffic.
- **Phạm vi region-wide:** cần cô lập cross-region và kiểm thử độc lập cả control plane lẫn data plane.
- **Chống logical corruption:** cần backup lịch sử, immutable copies, không chỉ replica đồng bộ.

Một cách đánh giá kinh tế:

~~~text
Expected impact
≈ Xác suất sự cố × Thiệt hại khi không đạt mục tiêu

Chi phí giảm rủi ro
= Standby capacity + Backup/storage + Network egress
+ Automation + On-call + DR drills + Công vận hành
~~~

Đây là khung định tính/ước lượng, không phải phép tính chính xác mọi loại thiệt hại. Với tiền, an toàn người dùng hoặc dữ liệu chịu quy định, không được quyết định chỉ theo lợi nhuận dự kiến; phải tuân thủ các yêu cầu bắt buộc và quản trị rủi ro.

### 24.1. Ước lượng chi phí downtime

Giả sử doanh nghiệp đo được doanh thu xử lý ước tính 1.000 USD/phút vào giờ cao điểm; 30 phút outage có thể tương ứng 30.000 USD giá trị giao dịch bị ảnh hưởng, **không đồng nghĩa toàn bộ số đó là thiệt hại ròng** (có giao dịch quay lại, có chi phí chưa tính). Phải bổ sung tác động SLA, vận hành, tồn đọng, hỗ trợ và uy tín.

Một RTO 5 phút có thể đòi active-active phức tạp và chi phí cao hơn đáng kể so với RTO 30 phút. BIA giúp quyết định mức nào phù hợp.

## 25. Kế hoạch diễn tập DR

DR được thiết kế nhưng chưa diễn tập là một giả định chưa được chứng minh.

Các hình thức diễn tập tăng dần:

1. **Tabletop exercise:** các bên mô phỏng sự cố và đi qua runbook trên giấy.
2. **Backup restore drill:** khôi phục bản backup vào môi trường độc lập, kiểm tra schema/dữ liệu.
3. **Component failover drill:** mất primary database hoặc broker node có kiểm soát.
4. **AZ failure simulation:** mô phỏng một vùng sẵn sàng mất khả năng phục vụ.
5. **Regional disaster drill:** kích hoạt vùng dự phòng, data recovery, routing và business validation.
6. **Logical corruption drill:** khôi phục về mốc trước lỗi và replay giao dịch hợp lệ.
7. **Security recovery drill:** kiểm thử khả năng phục hồi với credential/secret/key hoặc backup bị thu hồi trong phạm vi kiểm soát.

Không nhất thiết diễn tập gây gián đoạn thực ở production ngay từ đầu. Cần môi trường cô lập, phê duyệt, phạm vi, thời gian, rollback và giới hạn an toàn. Khi đủ trưởng thành, có thể tổ chức production game day có kiểm soát với kế hoạch bảo vệ khách hàng.

### 25.1. Tiêu chí PASS của một DR drill

Một cuộc diễn tập chỉ đạt khi:

- Phát hiện đúng kịch bản và kích hoạt quy trình trong ngân sách.
- Dữ liệu restore có integrity và đúng schema/keys.
- Chỉ một primary ghi theo chính sách; không split-brain.
- Các dependency cần thiết phục hồi ở vùng đích.
- Business synthetic end-to-end thành công, không chỉ health check.
- Đạt RTO và RPO đã định nghĩa theo mốc đo rõ.
- Không tạo charge trùng, mất order confirmed hoặc sai tồn kho vượt điều kiện chấp nhận.
- Có logs, audit trail, timeline, evidence và công việc khắc phục sau diễn tập.

Nếu fail một điều kiện, ghi rõ **mục tiêu không đạt** và kế hoạch sửa; không điều chỉnh lại mục tiêu sau sự cố chỉ để ghi nhận một “PASS”.

## 26. Runbook và trách nhiệm khi vận hành

Một runbook phải đủ cụ thể để người trực không cần tác giả ban đầu có mặt.

| Trường | Nội dung cần có |
| --- | --- |
| Tên kịch bản | Mất region chính, primary DB unreachable |
| Trigger | Alert/business journey fail; điều kiện xác minh |
| Incident commander | Người được giao quyền ra quyết định DR |
| Data owner | Người xác nhận restore point và integrity |
| Platform owner | Người thực hiện network/cluster/DB failover |
| Security owner | Người xử lý KMS, credential, access policy |
| RTO/RPO | Mục tiêu, phạm vi và điểm bắt đầu/kết thúc |
| Preconditions | Fencing, backup status, replication lag, access |
| Steps | Lệnh/hoạt động có thứ tự, thời hạn, xác minh |
| Stop conditions | Bất thường dữ liệu, split-brain, thiếu quyền |
| Backout | Cách dừng cutover hoặc chuyển hướng an toàn |
| Communication | Kênh nội bộ/đối tác/khách hàng theo chính sách |
| Post-recovery | Reconciliation, backlog, performance, retrospective |

Không đặt toàn bộ quyền quản trị chỉ trong tài khoản hoặc vault ở region đang bị mất. Quy trình break-glass phải được kiểm thử và kiểm toán, không làm mất kiểm soát bảo mật.

### 26.1. Failover tự động hay thủ công?

**Tự động:** nhanh, giảm thao tác người, nhưng dễ tạo quyết định sai khi partition, dữ liệu chưa replicate hoặc lỗi logic. Phải có quorum/fencing, health detection và safety checks phù hợp.

**Thủ công có hỗ trợ tự động:** chậm hơn ở bước quyết định nhưng có thể an toàn cho dữ liệu có giá trị cao; vẫn nên tự động hóa thao tác lặp lại, kiểm tra preconditions và cung cấp bằng chứng.

Không đánh đồng “tự động failover” với “luôn đáng tin cậy”. Có những kịch bản nên ưu tiên bảo vệ tính đúng đắn thay vì cố đạt RTO cực ngắn bằng mọi giá.

## 27. Failback: trở lại primary sau khi đã DR

Chuyển sang vùng dự phòng không phải kết thúc vòng đời sự cố. Cần kế hoạch **failback** trở lại vùng ưu tiên hoặc chuyển vùng dự phòng thành vùng chính mới.

Các vấn đề:

- Primary cũ đã bị fencing chưa, có chứa giao dịch không nằm trong recovery target không?
- Dữ liệu mới ở DR region sẽ được đồng bộ ngược thế nào?
- Có thể chuyển traffic mà không mất write hoặc tạo hai writer?
- Các client/DNS cache và job async đang trỏ nơi nào?
- Broker offsets/consumer groups, outbox và DLQ có cần xử lý đặc biệt?
- Các backup/replica và key policies đã được thiết lập cho vùng mới chưa?
- Khả năng DR có trở lại sẵn sàng sau failback không?

Không tự động quay về vùng chính ngay khi nó “ping được” nếu dữ liệu đã phân kỳ hoặc secondary vẫn đang xử lý giao dịch. Failback là một kế hoạch migration có thể có RTO/RPO và rủi ro riêng.

## 28. Bẫy kỹ thuật thường gặp

**“Có ba replica nghĩa là đã có DR.”** Replica trên cùng node/AZ/region không bảo vệ khỏi toàn bộ miền lỗi chung.

**“Đặt RPO = 0 cho mọi service là an toàn nhất.”** Mục tiêu có chi phí và trade-off availability; chỉ phù hợp khi đã định nghĩa và kiểm chứng phạm vi.

**“Backup chạy mỗi 5 phút nghĩa là RPO 5 phút.”** Cần xác nhận restore point nhất quán, backup thành công, log đầy đủ và khả năng giải mã.

**“Replication đồng bộ bảo vệ cả dữ liệu bị xóa nhầm.”** Lỗi logic có thể được replicate; cần PITR/immutable backup và quy trình recovery phù hợp.

**“RTO là thời gian khởi động Pod.”** RTO gồm detect/declare, data, dependencies, routing và business validation.

**“RTO đạt nếu health check xanh.”** Có thể API chưa xử lý được giao dịch thật hoặc dữ liệu đang sai.

**“RPO của Order DB bằng RPO của checkout.”** Checkout còn broker, inventory, payment và các side effect khác.

**“Failover nhanh là tốt dù có hai primary.”** Split-brain làm hỏng dữ liệu, thường nguy hiểm hơn một khoảng downtime có kiểm soát.

**“Đã có DR region là đã hết single point of failure.”** IAM, KMS, DNS, registry, external APIs hoặc pipeline deploy có thể còn phụ thuộc chung.

**“Có thể replay message không giới hạn mà không bị trùng.”** Retry và replay có thể gây double side effect nếu thiếu idempotency.

**“Chuyển sang backup là xong.”** Còn reconciliation, backlog, kiểm tra performance, backup cho vùng mới và kế hoạch failback.

**“Tất cả dữ liệu có cùng RPO.”** Cache, read model, order confirmed và payment ledger có mức quan trọng khác nhau.

**“Không cần diễn tập vì runbook đã được viết.”** Chỉ diễn tập mới bộc lộ quyền thiếu, schema drift, restore chậm, khóa lỗi hoặc DNS không chuyển.

**“Tăng capacity ở DR là chuyện nhỏ.”** Quota, node image, capacity reservation, startup time và DB throughput có thể làm failover vượt RTO.

## 29. Ví dụ kế hoạch cho nền tảng bán hàng nhiều service

Giả định nền tảng có:

~~~text
Region A (primary)
  API Gateway
  Auth / Order / Inventory / Payment
  PostgreSQL primary
  Kafka hoặc RabbitMQ
  Object storage
  KMS + Secrets

Region B (disaster recovery)
  Traffic manager standby
  App images / IaC + minimal services
  Replicated database hoặc recoverable backups
  Broker DR / event replay
  Object copies, keys và secrets đã chuẩn bị
~~~

BIA có thể chia:

- **Tier 0:** đã xác nhận thanh toán và ledger; tính đúng đắn ưu tiên cao nhất, không bỏ qua đối soát.
- **Tier 1:** nhận đơn mới, hiển thị trạng thái đơn; RTO ngắn, có điều kiện giảm một số chức năng.
- **Tier 2:** search/catalog có thể dùng cache tạm thời.
- **Tier 3:** report/analytics có thể rebuild sau.

### 29.1. Tập mục tiêu minh họa

| Chức năng | RTO mục tiêu | RPO mục tiêu | Điều kiện “đã phục hồi” |
| --- | ---: | ---: | --- |
| Core checkout | 30 phút | 5 phút hoặc nghiêm ngặt hơn với confirmed orders | Tạo/đọc đơn thật, kiểm tra payment/inventory consistency |
| Catalog reads | 60 phút | 30 phút với nguồn product data | Query phục vụ được, chấp nhận cache theo policy |
| Notifications | 4 giờ | Không mất intent event đã được nhận bền vững | Queue/replay idempotent, backlog được quan sát |
| Analytics | 24 giờ | 24 giờ nếu event source còn đầy đủ | Báo cáo dựng lại theo kỳ chấp nhận |

Các con số **chỉ là ví dụ học tập**. Khi một chức năng phụ thuộc Tier 0, tier của dependency cần đáp ứng mục tiêu hệ thống; không lấy riêng RTO của từng service như thể độc lập.

### 29.2. Các phép đo phải có

- Cross-region DB replication lag và recoverable backup age.
- Thời gian database failover/restore.
- App startup/scale/ready ở region B.
- Router/DNS cutover và health của client ở vùng mới.
- Synthetic checkout với idempotency key thử nghiệm.
- Outbox backlog, event replay count, DLQ và duplicate prevention.
- Payment reconciliation queue, số transaction UNKNOWN.
- Lượng tenant bị lỗi hoặc mất dữ liệu so với business SLO.

## 30. Bài tập thực hành: chọn RTO/RPO theo tác động

Một nền tảng thương mại điện tử có bốn thành phần:

1. **Order Service:** lưu đơn đã xác nhận ở PostgreSQL.
2. **Payment Service:** gửi lệnh charge đến external provider và giữ transaction references.
3. **Catalog Service:** phục vụ sản phẩm từ cache/index có thể tái tạo.
4. **Reporting Service:** dựng báo cáo hằng ngày từ event log.

Thông tin giả định:

- Giờ cao điểm có 300 đơn/phút; một đơn có thể đã được khách hàng thanh toán khi phản hồi nội bộ bị mất.
- Công việc báo cáo có thể hoàn thành muộn 8 giờ mà không ảnh hưởng thanh toán.
- Order DB đang dùng async cross-region replication, có lúc lag đến 7 phút.
- Backup full mỗi ngày; WAL archive có thể phục hồi từng điểm nếu log đầy đủ.
- DR region có app instances nhưng chỉ chịu được 30% traffic bình thường nếu chưa scale.
- Broker có thể replay events nhưng consumer hiện tại chưa có idempotency đầy đủ.

**Yêu cầu:**

1. Xác định BIA và mức tác động khi checkout ngừng 5/30/120 phút.
2. Đề xuất mục tiêu RTO/RPO cho từng nhóm dữ liệu, nói rõ chúng là mục tiêu cần phê duyệt chứ không phải tiêu chuẩn chung.
3. Nếu muốn RPO 5 phút cho Order DB nhưng replication lag từng lên 7 phút, cần giám sát, thiết kế hoặc thay đổi mục tiêu thế nào?
4. Tính minh họa mức dữ liệu chịu rủi ro nếu mất 5 phút đơn mới ở tốc độ 300 đơn/phút.
5. Nêu vì sao Payment RPO không thể kết luận chỉ từ backup PostgreSQL.
6. Định nghĩa điều kiện phục hồi checkout hợp lệ thay vì chỉ kiểm tra HTTP 200.
7. Tính các bước RTO trong ngân sách 30 phút, gồm detect, declare, data, scale, routing và validate.
8. Đề xuất các tests để ngăn replay event làm double charge và duplicate order.
9. Nếu DR region chỉ có 30% capacity, cần load shedding, autoscaling và quota ra sao?
10. Thiết kế DR drill thử mất region, lỗi migration và mất khóa giải mã riêng biệt.
11. Mô tả cách chuyển về vùng chính sau khi đã tạo đơn mới ở vùng dự phòng.

**Gợi ý đáp án:** 5 phút ở 300 đơn/phút tương đương khoảng 1.500 đơn phát sinh trong cửa sổ thời gian, **không đồng nghĩa chắc chắn mất 1.500 đơn**; đó là lượng thao tác tiềm năng cần đánh giá và reconciliation. RPO 5 phút chưa được đảm bảo khi lag 7 phút. Payment cần idempotency và đối soát external provider. RTO phải được đo từ mất chức năng đến business journey phục hồi theo tiêu chí xác định. DR region cần năng lực đủ cho minimum viable capacity và lộ trình scale. Mỗi điểm khôi phục phải nhất quán; kiểm tra broker/outbox và reconciliation trước khi mở ghi toàn phần.

## 31. Checklist khi chốt mục tiêu RTO/RPO

### Business và governance

- Mỗi chức năng có chủ sở hữu nghiệp vụ và phân loại mức quan trọng?
- RTO/RPO phản ánh thiệt hại thực và yêu cầu hợp đồng/pháp lý?
- Đã xác định rõ data source of truth và phần có thể tái tạo?
- Có phân biệt giao dịch đã xác nhận với trạng thái nháp/pending?
- Các mục tiêu có chữ ký phê duyệt/chủ sở hữu và ngày rà soát?

### Technical architecture

- Có dependency map cho từng critical business journey?
- Các failure domains cần bao phủ đã được ghi rõ?
- Backup, replication, WAL/log và object storage tương thích mục tiêu?
- Có immutable/off-domain backups chống lỗi logic và phá hoại?
- Có key/secrets/IAM recovery để đọc dữ liệu ở vùng dự phòng?
- Có fencing/quorum ngăn split-brain?
- Có event replay/idempotency/reconciliation cho dữ liệu phân tán?
- DR region có đủ tối thiểu CPU/memory/network/DB capacity?
- Có thể triển khai app/config/schema phù hợp không phụ thuộc hoàn toàn primary region?
- Có kế hoạch xử lý in-flight payment và transaction UNKNOWN?

### Measurement và exercise

- Có đo last recoverable consistent point, không chỉ last backup start?
- Có alert replication lag tiến gần RPO?
- Có đo đầy đủ detect/declare/restore/route/validate theo RTO?
- Có synthetic journey kiểm thử nghiệp vụ?
- Có DR drill cả regional outage và logical corruption?
- Có tính RPO/RTO thực sau drill và ghi bằng chứng?
- Có runbook, phân quyền người trực và failback plan?
- Có công việc khắc phục khi không đạt mục tiêu và diễn tập lại?

---

**Điểm cốt lõi:** **RTO** xác định cần phục hồi một chức năng trong bao lâu; **RPO** xác định có thể mất tối đa bao nhiêu dữ liệu mới nhất. Hai giá trị phải xuất phát từ tác động nghiệp vụ, đi cùng failure scenario và tiêu chí đo cụ thể. Với microservices, không thể nhìn riêng một database hoặc một Pod: cần xét các dependency, dữ liệu phân tán, message broker, side effect, khóa mã hóa, routing, sự nhất quán và quy trình đối soát. Chỉ khi restore và failover được **diễn tập, đo đạc và chứng minh đạt mục tiêu**, RTO/RPO mới là cơ sở đáng tin cậy cho kế hoạch khôi phục thảm họa.

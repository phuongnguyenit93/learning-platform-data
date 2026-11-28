# Tính sẵn sàng (Availability) trong security assurance

## 1. Tính sẵn sàng là gì và vì sao là mục tiêu bảo mật?

**Tính sẵn sàng (availability)** là khả năng để người dùng, hệ thống hoặc quy trình **được phép** sử dụng đúng dữ liệu, chức năng và dịch vụ **khi cần**, trong điều kiện chất lượng và thời gian đáp ứng chấp nhận được. Trong bộ ba mục tiêu bảo mật **CIA** (*Confidentiality – Integrity – Availability*), tính sẵn sàng bổ sung cho:

- **Confidentiality – Tính bí mật:** thông tin không bị tiết lộ cho chủ thể không có quyền.
- **Integrity – Tính toàn vẹn:** thông tin và hoạt động xử lý không bị sửa đổi sai trái hoặc không được phát hiện.
- **Availability – Tính sẵn sàng:** chức năng và thông tin thiết yếu còn sử dụng được bởi chủ thể có quyền.

Một API có xác thực mạnh, dữ liệu được mã hóa và không bị sửa trái phép vẫn **không đạt mục tiêu bảo mật** nếu khách hàng hợp lệ không thể truy cập dịch vụ vào lúc cần giao dịch. Điều này đặc biệt quan trọng với hệ thống thanh toán, bệnh viện, đặt vé, danh tính, ứng cứu sự cố hoặc bất kỳ luồng nghiệp vụ có hậu quả đáng kể khi gián đoạn.

Trong module **SECURITY_SECURITY_ASSURANCE**, tính sẵn sàng được xem là **một mục tiêu cần chứng minh bằng bằng chứng**, không chỉ là khẩu hiệu “hệ thống chạy 24/7”. Để đánh giá có cơ sở, ta phải liên kết phân tích rủi ro, yêu cầu có thể đo lường, biện pháp bảo vệ (*security controls*), kiểm thử, giám sát, audit, khắc phục phát hiện và đánh giá lại trong suốt quá trình phát triển và vận hành.

### “Dịch vụ còn bật” chưa có nghĩa “dịch vụ sẵn sàng”

Những tình huống sau có thể đều là **mất hoặc suy giảm tính sẵn sàng** dù tiến trình ứng dụng vẫn đang chạy:

| Tình huống | Vì sao ảnh hưởng availability? |
| --- | --- |
| Trang health check trả HTTP 200 nhưng API đặt hàng luôn timeout. | Thành phần đang chạy nhưng chức năng người dùng cần không sử dụng được. |
| API trả kết quả sau 45 giây, trong khi khách phải hoàn tất trước 3 giây. | Chất lượng sử dụng không đáp ứng yêu cầu thời gian. |
| Một vùng địa lý không truy cập được, các vùng khác vẫn bình thường. | Availability bị suy giảm trong một nhóm người dùng cụ thể. |
| Ứng dụng mở được nhưng cơ sở dữ liệu bị khóa hoặc không đọc được. | Phụ thuộc quan trọng không đáp ứng nên nghiệp vụ không hoàn tất. |
| Hàng đợi nhận thông điệp nhưng không xử lý đơn trong thời hạn cam kết. | Điểm nhận yêu cầu hoạt động nhưng dịch vụ đầu cuối chưa đạt kết quả mong đợi. |
| Hệ thống dự phòng chạy được nhưng không thể phục hồi dữ liệu cần thiết. | Phục hồi công suất mà không phục hồi được trạng thái nghiệp vụ có thể vẫn không đáp ứng yêu cầu. |

Do đó, cần định nghĩa availability theo **luồng nghiệp vụ, đối tượng phục vụ, thời gian quan sát và điều kiện thành công**; không đánh đồng với trạng thái của một máy chủ hay một lần ping.

## 2. Xác định chính xác “cái gì phải sẵn sàng”

Trước khi mua giải pháp dự phòng hoặc đặt mục tiêu “bốn số chín”, cần hiểu hoạt động kinh doanh và các thành phần quan trọng.

### 2.1. Phân tích tác động nghiệp vụ (Business Impact Analysis – BIA)

Với mỗi dịch vụ hoặc quy trình trọng yếu, làm rõ:

1. **Ai cần sử dụng?** Khách hàng, nhân viên vận hành, dịch vụ nội bộ, đối tác hay tác vụ tự động.
2. **Dùng chức năng nào?** Đăng nhập, xem thông tin, tạo giao dịch, nhận cảnh báo, truy xuất hồ sơ hay khôi phục dữ liệu.
3. **Cần vào thời điểm nào?** Mọi lúc, giờ giao dịch, dịp cao điểm, trong sự cố hay một cửa sổ xử lý định kỳ.
4. **Gián đoạn gây hậu quả gì?** Mất doanh thu, chậm hỗ trợ, vi phạm nghĩa vụ, mất niềm tin, hậu quả an toàn hoặc ảnh hưởng dây chuyền.
5. **Gián đoạn bao lâu thì không thể chấp nhận?** Ngưỡng chấp nhận phải dựa vào ảnh hưởng thực tế và khả năng phục hồi.
6. **Phụ thuộc những gì?** DNS, danh tính, mạng, cơ sở dữ liệu, cache, hàng đợi, nhà cung cấp dịch vụ, hạ tầng và con người.

Ví dụ, việc xem báo cáo thống kê có thể chấp nhận chậm vài phút, nhưng xác nhận giao dịch thanh toán phải đáp ứng nhanh hơn nhiều. Hai chức năng ở cùng một hệ thống không nhất thiết có **cùng** mục tiêu availability.

### 2.2. Phân biệt trạng thái phục vụ và thành công của tác vụ

Có thể đánh giá nhiều lớp:

~~~mermaid
flowchart LR
    U["Người dùng hợp lệ"] --> N["DNS / Mạng / Edge"]
    N --> A["Ứng dụng / API"]
    A --> D["Dữ liệu / Hàng đợi"]
    D --> P["Dịch vụ phụ thuộc"]
    P --> B["Kết quả nghiệp vụ"]
~~~

- **Infrastructure availability:** máy chủ, mạng và nền tảng có hoạt động không?
- **Service availability:** endpoint và thành phần chính có nhận, xử lý yêu cầu hợp lệ không?
- **Business transaction availability:** người dùng có thực sự hoàn thành thao tác được cam kết không?

Một chỉ số lớp dưới có thể tốt trong khi lớp trên vẫn lỗi. Đối với security assurance, claim về khả năng phục vụ của người dùng phải có **bằng chứng phù hợp ở lớp nghiệp vụ**, bên cạnh các bằng chứng hạ tầng.

## 3. Biến tính sẵn sàng thành yêu cầu đo được

Mục tiêu “dịch vụ luôn sẵn sàng” không đủ rõ để thiết kế hay kiểm chứng. Trước tiên cần định nghĩa **SLI, SLO và SLA**:

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **SLI – Service Level Indicator** | Phép đo thực tế về chất lượng dịch vụ. | Tỷ lệ yêu cầu đặt hàng hợp lệ hoàn tất thành công trong 2 giây. |
| **SLO – Service Level Objective** | Mục tiêu nội bộ đặt trên SLI cho khoảng thời gian xác định. | SLI đó đạt ít nhất 99,9% trong mỗi cửa sổ 30 ngày. |
| **SLA – Service Level Agreement** | Cam kết với bên khác, có thể kèm điều khoản và hậu quả khi vi phạm. | Điều khoản dịch vụ ghi rõ ngưỡng, phương pháp đo, loại trừ và trách nhiệm. |

SLO và SLA có thể khác nhau. Một hệ thống cũng có thể có **nhiều SLI/SLO**: tỷ lệ thành công, độ trễ, dữ liệu được xử lý đúng hạn, khả năng truy cập theo khu vực hoặc theo nhóm người dùng.

### 3.1. Viết một yêu cầu rõ phạm vi

Ví dụ cho dịch vụ đặt hàng:

> “Trong mỗi cửa sổ 30 ngày, tối thiểu **99,9% yêu cầu tạo đơn hàng hợp lệ** từ người dùng được phép tại các vùng triển khai công bố phải được xác nhận tiếp nhận bền vững trong **không quá 2 giây**. Các lỗi do hệ thống, quá tải và timeout thuộc mẫu số; cách tính loại trừ yêu cầu không hợp lệ phải được định nghĩa và kiểm toán được.”

Để yêu cầu này hữu ích, nhóm còn phải thống nhất:

- Thế nào là **yêu cầu hợp lệ** và **hoàn thành**; không mặc định HTTP 200 là nghiệp vụ thành công.
- Tính SLI bằng tỷ lệ **yêu cầu** hay tỷ lệ **thời gian**; hai cách có ý nghĩa khác nhau.
- Cửa sổ cố định hay trượt, múi giờ, phạm vi người dùng, tenant, vùng địa lý và giai đoạn cao điểm.
- Xử lý các trường hợp người dùng hủy, lỗi nhập liệu, lỗi xác thực, timeout, retry, yêu cầu bị giới hạn lưu lượng và sự cố của bên thứ ba như thế nào.
- Định nghĩa và phê duyệt các khoảng bảo trì nếu có. Không được âm thầm bỏ thời gian xảy ra lỗi ra khỏi mẫu số để làm đẹp số liệu.

**Một cách tính cho SLI dựa trên yêu cầu:**

\[
\text{Availability SLI} = \frac{\text{Số yêu cầu hợp lệ đạt tiêu chí thành công}}{\text{Tổng số yêu cầu hợp lệ thuộc phạm vi đo}} \times 100\%
\]

Ví dụ trong cửa sổ đo có **1.000.000 yêu cầu hợp lệ**, trong đó **998.800** yêu cầu đáp ứng định nghĩa thành công. Khi đó availability SLI là **99,88%**, thấp hơn SLO **99,9%**. Với SLO 99,9%, *error budget* là 0,1% tổng yêu cầu hợp lệ, tương đương **1.000** yêu cầu không đạt trong ví dụ này. Thực tế có **1.200** yêu cầu không đạt nên đã vượt ngân sách lỗi **200** yêu cầu.

Lưu ý: 99,9% theo **yêu cầu** không đồng nghĩa chính xác với “thời gian ngừng tối đa 43,2 phút mỗi 30 ngày”. Con số 43,2 phút tương ứng 0,1% của 30 ngày **nếu dùng chỉ số availability theo thời gian**. Khi lưu lượng phân bố không đều, hai phép đo có thể khác đáng kể.

### 3.2. Các chỉ số liên quan đến phát hiện và phục hồi

| Chỉ số/khái niệm | Trả lời câu hỏi gì? | Phân biệt cần nhớ |
| --- | --- | --- |
| **MTTD – Mean Time To Detect** | Trung bình mất bao lâu để phát hiện sự cố? | Phát hiện nhanh chưa có nghĩa đã phục hồi. |
| **MTTR – Mean Time To Restore/Recover** | Trung bình mất bao lâu để phục hồi dịch vụ theo cách định nghĩa của đội? | Phải nói rõ cách tính, điểm bắt đầu/kết thúc và loại sự cố; MTTR là kết quả quan sát, không phải cam kết tối đa. |
| **RTO – Recovery Time Objective** | Mục tiêu thời gian tối đa để phục hồi một quy trình sau gián đoạn trong kịch bản đã xác định? | Mục tiêu thiết kế ứng cứu/phục hồi; không tự suy ra từ MTTR trung bình. |
| **RPO – Recovery Point Objective** | Mức dữ liệu hoặc khoảng thời gian mất dữ liệu tối đa chấp nhận được khi khôi phục? | Thuộc khả năng khôi phục trạng thái dữ liệu; khác với thời gian phục hồi dịch vụ RTO. |
| **Error budget** | Mức độ sai lệch khỏi mục tiêu SLO còn có thể chấp nhận trong cửa sổ đo? | Là cơ chế quản trị độ tin cậy, không phải giấy phép tùy ý gây lỗi. |

Ví dụ BIA quy định **RTO 30 phút** và **RPO 5 phút** cho hệ thống nhận đơn khi mất toàn bộ vùng triển khai. Tổ chức cần thiết kế khả năng khởi động dịch vụ trong phạm vi 30 phút và cách bảo vệ/phục hồi dữ liệu sao cho điểm phục hồi không lùi quá 5 phút theo kịch bản. Những con số chỉ là **minh họa**; mục tiêu thực tế phải được lựa chọn theo tác động và chi phí, sau đó kiểm tra bằng diễn tập.

## 4. Các mối đe dọa và nguyên nhân làm suy giảm availability

Tính sẵn sàng thuộc lĩnh vực bảo mật bởi gián đoạn có thể xuất phát từ **hành động cố ý** lẫn **sai sót, sự cố và thảm họa**. Assurance cần xem xét cả hai; chỉ tập trung vào tấn công DDoS sẽ bỏ sót nhiều nguyên nhân thực tế.

| Kịch bản | Ảnh hưởng cần phân tích | Hướng kiểm soát phù hợp |
| --- | --- | --- |
| **DDoS hoặc lạm dụng API** làm cạn tài nguyên mạng, CPU, kết nối hoặc hàng đợi. | Người dùng hợp lệ bị từ chối, timeout hoặc suy giảm độ trễ. | Bảo vệ ở edge, rate limiting có phân biệt đối tượng, kiểm soát tài nguyên, phối hợp nhà cung cấp, diễn tập ứng phó. |
| **Mã độc tống tiền/phá hoại** mã hóa hoặc xóa dữ liệu và bản sao. | Dịch vụ mất khả năng xử lý và phục hồi; có thể mất dữ liệu. | Phân quyền tối thiểu, bảo vệ bản sao lưu, khôi phục đã được kiểm chứng, phát hiện hành vi bất thường, kế hoạch cô lập. |
| **Sự cố triển khai/cấu hình** gây lỗi trên toàn cụm. | Lỗi diện rộng ngay sau release dù có nhiều máy dự phòng. | Canary, kiểm thử trước triển khai, rollback, kiểm soát cấu hình, tách biệt miền lỗi. |
| **Quá tải nội bộ** do tải tăng hoặc truy vấn tốn tài nguyên. | Nghẽn CPU, pool kết nối, cache hoặc database; lỗi dây chuyền. | Capacity planning, load testing, backpressure, quota, bulkhead, graceful degradation. |
| **Sự cố vùng, mạng, DNS hoặc nhà cung cấp.** | Một hoặc nhiều điểm phụ thuộc không sử dụng được. | Phân tích phụ thuộc, dự phòng phù hợp, failover được diễn tập và kiểm tra phụ thuộc chung. |
| **Hết hạn chứng chỉ, secret, quota hoặc dung lượng.** | Dịch vụ lỗi bất ngờ mặc dù mã ứng dụng không đổi. | Quản trị vòng đời chứng chỉ/secret, cảnh báo sớm, kiểm tra quota và dung lượng. |
| **Lỗi thao tác của con người hoặc thiếu nhân lực ứng cứu.** | Phục hồi chậm, quyết định sai hoặc mất khả năng phản ứng khi có sự cố. | Runbook, quyền truy cập khẩn cấp có kiểm soát, phân vai trực, diễn tập và đánh giá sau sự cố. |

Các yếu tố phụ thuộc có thể gây **common-cause failure**: hai máy chủ dự phòng cùng dùng một cơ sở dữ liệu, một DNS provider hoặc một tài khoản quản trị. Nhiều bản sao của cùng một thành phần **không** mặc nhiên loại bỏ điểm lỗi chung.

## 5. Security controls bảo vệ tính sẵn sàng

Chọn controls phải đi từ rủi ro và yêu cầu cụ thể. Có thể phân loại theo mục đích để tránh thiếu lớp phòng vệ.

### 5.1. Ngăn ngừa và giới hạn ảnh hưởng

- **Tách biệt miền lỗi:** phân bố thành phần quan trọng sang nhiều vùng khả dụng hoặc hạ tầng độc lập khi BIA yêu cầu, cùng với việc đánh giá phụ thuộc chung.
- **Giới hạn và cách ly tài nguyên:** timeout, rate limit, quota, bulkhead, giới hạn kết nối và hàng đợi để một loại tải không chiếm toàn bộ năng lực phục vụ.
- **Điều tiết tải:** backpressure và load shedding có chính sách ưu tiên luồng thiết yếu, bảo vệ người dùng hợp lệ khi khan hiếm tài nguyên.
- **Circuit breaker và retry có giới hạn:** ngăn lỗi phụ thuộc kéo dài thành lỗi dây chuyền. Retry nên có backoff, jitter và giới hạn số lần; thao tác có side effect cần thiết kế idempotency phù hợp để tránh giao dịch trùng.
- **Quản lý năng lực và thay đổi:** capacity planning, kiểm tra hiệu năng với tải có ý nghĩa, triển khai theo đợt, khả năng rollback, thử nghiệm cấu hình.
- **Giảm bề mặt tấn công:** vá lỗ hổng, phân quyền quản trị chặt chẽ, bảo vệ quản lý tài nguyên và chống lạm dụng theo mô hình đe dọa.

**Trade-off:** rate limiting có thể chặn nhầm khách hàng hợp lệ; caching có thể gây dữ liệu cũ; chuyển dự phòng có thể ảnh hưởng tính nhất quán; nhiều vùng triển khai tăng độ phức tạp và chi phí. Vì vậy phải định nghĩa **điều kiện kích hoạt, hành vi suy giảm chấp nhận được và bằng chứng kiểm thử** cho từng control.

### 5.2. Phát hiện suy giảm

- Theo dõi cả **hệ thống** và **giao dịch nghiệp vụ**: tỷ lệ thành công, độ trễ, lỗi theo nhóm người dùng, backlog, thời gian xử lý và độ tươi của dữ liệu.
- Dùng **synthetic transaction** hoặc kiểm tra đầu cuối có tài khoản và dữ liệu kiểm thử được quản lý; không chỉ theo dõi health endpoint.
- Cảnh báo gắn với SLO, mức tiêu thụ error budget và các tín hiệu sự cố sắp xảy ra như tăng thời gian chờ, backlog hoặc sắp hết dung lượng.
- Bảo vệ chất lượng telemetry: đồng bộ thời gian, quan sát theo khu vực/tenant, gắn bản phát hành; không để logging/monitoring tự tạo điểm lỗi hoặc làm lộ dữ liệu nhạy cảm.

### 5.3. Ứng phó, duy trì hoạt động tối thiểu và khôi phục

- **Incident response:** xác định ai trực, ai có quyền chuyển vùng, giới hạn lưu lượng, rollback và liên lạc với bên liên quan.
- **Graceful degradation:** giữ luồng thiết yếu trong khi tạm giảm chức năng phụ, theo chính sách đã được phê duyệt. Không được hy sinh kiểm soát bí mật/toàn vẹn một cách âm thầm để tăng uptime.
- **Business continuity:** duy trì khả năng vận hành quan trọng khi một phần hệ thống không có sẵn.
- **Disaster recovery:** bản sao lưu, quy trình phục hồi và chuyển đổi dự phòng, bao gồm việc kiểm tra dữ liệu sau phục hồi.
- **Post-incident review:** xác định nguyên nhân, tác động, thời gian phục hồi, điểm mù giám sát và hành động ngăn tái diễn; lưu vết kiểm tra hiệu quả của biện pháp sửa.

**Backup tồn tại chưa chứng minh khả năng phục hồi.** Cần có bằng chứng restore hoạt động trên một kịch bản phù hợp, dữ liệu dùng được và thời gian phục hồi thực tế đáp ứng mục tiêu RTO/RPO.

## 6. Chuyển mục tiêu availability thành lập luận assurance

Đối với security assurance, câu hỏi trọng tâm là: **“Chúng ta có đủ cơ sở để tin rằng dịch vụ đáp ứng mục tiêu sẵn sàng đã định nghĩa hay chưa?”**

Có thể tổ chức lập luận theo **Claim – Argument – Evidence (CAE)**:

1. **Claim:** tuyên bố cụ thể về availability trong phạm vi và điều kiện nhất định.
2. **Argument:** giải thích vì sao cấu trúc hệ thống, controls và khả năng vận hành có thể đáp ứng claim; nêu rõ giả định và điểm phụ thuộc.
3. **Evidence:** hiện vật giúp người khác kiểm chứng lập luận, kể cả bằng chứng trái chiều hoặc giới hạn chưa được giải quyết.

~~~mermaid
flowchart TD
    A["Rủi ro gián đoạn + BIA"] --> B["Claim: SLO / RTO / RPO / phạm vi"]
    B --> C["Argument: kiến trúc + controls + quy trình"]
    C --> D["Evidence: load test / failover / restore / telemetry"]
    D --> E{"Bằng chứng đủ và còn hiệu lực?"}
    E -- "Đạt trong phạm vi" --> F["Kết luận có giới hạn và quyết định"]
    E -- "Chưa đạt / phát hiện" --> G["Xử lý rủi ro + khắc phục + kiểm tra lại"]
    G --> D
    F --> H["Theo dõi thay đổi, sự cố, kiểm chứng định kỳ"]
    H --> A
~~~

### Ví dụ bảng liên kết rủi ro – control – evidence

| Claim nhỏ | Control/biện pháp | Bằng chứng cần thu thập | Giới hạn thường gặp |
| --- | --- | --- | --- |
| Luồng đặt đơn đáp ứng SLO trong tải dự kiến. | Tối ưu hiệu năng, autoscaling, backpressure, quản trị năng lực. | Load test theo workload đại diện; SLI production đủ bao phủ. | Tải kiểm thử không giống cao điểm thực; endpoint phụ bị bỏ qua. |
| Mất một instance không làm ngừng nhận đơn. | Nhiều instance, health-aware routing, tự động thay thế. | Thử tắt instance trong môi trường kiểm soát; log thời gian phục hồi và tỷ lệ lỗi. | Nhiều instance cùng phụ thuộc một database. |
| Khi vùng triển khai hỏng, có thể phục hồi theo RTO. | Kế hoạch failover, hạ tầng đích và runbook. | Diễn tập failover có đo thời gian và xác nhận giao dịch thực. | Chỉ diễn tập thành phần, không kiểm tra luồng nghiệp vụ đầu cuối. |
| Dữ liệu phục hồi đáp ứng RPO. | Replication, backup và restore có kiểm chứng. | Bản ghi điểm phục hồi, tính toàn vẹn của dữ liệu sau restore, kiểm tra quyền. | Sao lưu thành công nhưng bản sao hỏng, không giải mã được hoặc cùng miền lỗi. |
| DDoS không làm sụp toàn bộ luồng thiết yếu trong điều kiện đã xác định. | Lọc và giới hạn tải, phối hợp nhà cung cấp, ưu tiên luồng quan trọng. | Kết quả mô phỏng lưu lượng được phép trong môi trường kiểm soát; đánh giá ngưỡng và false positive. | Không thể suy rộng kết quả thử tới mọi quy mô và dạng tấn công. |
| Suy giảm được phát hiện và ứng cứu kịp thời. | Monitoring, alerting, on-call, runbook. | Kết quả kiểm thử cảnh báo, diễn tập on-call, timeline sự cố thực tế. | Chỉ giám sát CPU trong khi nghiệp vụ đã ngừng phục vụ. |

**Chất lượng bằng chứng** phụ thuộc vào nguồn gốc, phiên bản, môi trường, tải/kịch bản, thời điểm, tính lặp lại, độ bao phủ, độ độc lập của người đánh giá và tính toàn vẹn hiện vật. Một báo cáo “test passed” không có cấu hình, dữ liệu đầu vào, tiêu chí đạt và kết quả đo chi tiết rất khó hỗ trợ một claim quan trọng.

## 7. Tình huống thực hành: bảo đảm dịch vụ nhận đơn hàng

Giả sử một nền tảng thương mại có luồng:

~~~text
Khách hàng -> API Gateway -> Order API -> Order Database
                                |
                                +-> Event Queue -> Fulfillment Worker
~~~

Hệ thống cần nhận và xác nhận đơn hàng cả trong giờ cao điểm. Threat modeling chỉ ra các rủi ro: API bị lạm dụng gây quá tải, một instance chết, kết nối database cạn, hàng đợi tích tụ, lỗi triển khai và mất vùng triển khai.

### Bước 1: xác định đúng mục tiêu

Sau BIA, nhóm tạm đặt ra mục tiêu minh họa:

- **SLO nhận đơn:** ít nhất 99,9% yêu cầu hợp lệ được xác nhận đã ghi nhận bền vững trong tối đa 2 giây, trong mỗi cửa sổ 30 ngày.
- **RTO khi mất vùng triển khai:** 30 phút cho khả năng tiếp nhận đơn tối thiểu.
- **RPO cho dữ liệu đơn hàng:** tối đa 5 phút trong kịch bản khôi phục tương ứng.
- **Phạm vi:** API tạo đơn của người dùng ở các khu vực được công bố; xử lý giao hàng bất đồng bộ có SLO riêng.

Mốc “xác nhận đã ghi nhận bền vững” rất quan trọng: một response 202 trước khi thông tin đơn được lưu đáng tin cậy có thể tạo cảm giác thành công giả. Nhóm phải chọn điểm xác nhận hợp lý theo thiết kế và kiểm tra được trong điều kiện lỗi.

### Bước 2: lập luận vì sao thiết kế có thể đáp ứng

Giải pháp dự kiến có nhiều instance Order API, cân bằng tải theo tình trạng sức khỏe, quản trị pool kết nối, hạn chế yêu cầu quá mức, kiểm soát hàng đợi và kế hoạch khôi phục dữ liệu. Hệ thống sử dụng mã idempotency thích hợp để retry không tạo đơn trùng. Kịch bản mất một vùng có runbook chuyển sang vùng dự phòng.

Tuy nhiên, lập luận này chỉ có giá trị khi kiểm tra cả các giả định: cơ sở dữ liệu có đủ năng lực phục vụ sau failover không, tài khoản khẩn cấp có truy cập được không, DNS có chuyển hướng phù hợp không, và liệu vùng dự phòng có chung điểm lỗi với vùng chính?

### Bước 3: thu thập bằng chứng theo kịch bản

| Kịch bản cần chứng minh | Thực nghiệm có kiểm soát | Tiêu chí ghi nhận |
| --- | --- | --- |
| Tải cao nhưng còn trong năng lực thiết kế | Tạo workload đại diện gồm truy cập thông thường và giờ cao điểm. | Tỷ lệ giao dịch thành công, độ trễ, lỗi theo nguyên nhân, độ bao phủ các tuyến truy cập. |
| Một Order API instance bị lỗi | Ngắt một instance trên staging hoặc môi trường diễn tập có kiểm soát. | Tỷ lệ lỗi tạm thời, thời gian điều phối sang instance khác, khả năng hoàn tất đơn. |
| Database chậm hoặc pool kết nối cạn | Tiêm trễ/lỗi vào phụ thuộc trong phạm vi được phép. | Timeout, cách ly lỗi, không gây thác lỗi, hành vi retry và tính toàn vẹn đơn. |
| Lưu lượng bất thường | Mô phỏng hợp pháp ở môi trường test đã cho phép. | Khả năng giữ luồng chính, ngưỡng chặn, ảnh hưởng đến khách hàng hợp lệ. |
| Mất một vùng triển khai | Diễn tập chuyển dự phòng theo runbook, đo từ thời điểm sự cố đến khi luồng nhận đơn hoạt động. | RTO, khả năng xác thực, dữ liệu đầu vào và đầu ra, điểm lỗi phụ thuộc. |
| Khôi phục dữ liệu | Restore từ bản sao đã bảo vệ, kiểm tra mẫu dữ liệu và tính nhất quán. | Điểm phục hồi đo được so với RPO, tính toàn vẹn và khả năng dùng dữ liệu. |
| Gián đoạn có thật | Đối chiếu metrics, logs, alert, incident timeline và phạm vi người dùng. | SLI/SLO thực đo, MTTD/MTTR theo định nghĩa, bài học và hành động. |

Một ví dụ *evidence record* dùng để truy vết (cú pháp minh họa, không phải biểu mẫu bắt buộc):

~~~yaml
claim_id: AVAIL-ORDER-01
claim: "Order API dap ung SLO 99.9% trong cua so 30 ngay"
service: order-api
release: "2.8"
scope: "Tao don hang hop le tu cac vung phuc vu da cong bo"
sli:
  numerator: "Giao dich hop le duoc ghi nhan ben vung trong 2 giay"
  denominator: "Tong giao dich tao don hop le trong pham vi"
  window: "30 days"
  target: ">= 99.9%"
evidence:
  - id: "slo-dashboard-snapshot-2026-11"
    type: "production-metrics"
    verifies: "observed business-transaction SLI"
  - id: "load-test-order-release-2.8"
    type: "test-report"
    verifies: "behaviour under representative declared load"
  - id: "failover-drill-order-2.8"
    type: "drill-report"
    verifies: "recovery path and measured time"
limitations:
  - "Chua kiem chung quy mo tan cong DDoS ngoai kich ban dien tap"
decision: "Pending assurance review"
owner: "Order platform team"
~~~

Các chuỗi tên báo cáo trong ví dụ chỉ là **nhãn minh họa**, không phải bằng chứng có thật. Khi sử dụng thực tế, phải có liên kết tới hiện vật, kết quả đo, người thực hiện, phiên bản, thời điểm và môi trường chính xác.

### Bước 4: xử lý phát hiện

Giả sử diễn tập cho thấy chuyển vùng mất **47 phút**, vượt RTO **30 phút**. Kết quả đúng là **claim RTO chưa đạt** trong kịch bản được kiểm tra, dù các dashboard uptime khác vẫn tốt.

Nhóm cần ghi nhận phát hiện với mức tác động, owner, hạn xử lý; tìm nguyên nhân (chẳng hạn cập nhật DNS thủ công và thiếu quyền vận hành); sửa runbook hoặc tự động hóa phù hợp; **diễn tập lại** và lưu số đo mới. Nếu chưa xử lý được, người có thẩm quyền phải quyết định rủi ro còn lại và các biện pháp tạm thời. Không đánh dấu đạt chỉ vì “đã có kế hoạch khắc phục”.

## 8. Đưa assurance tính sẵn sàng vào phát triển và vận hành liên tục

Tính sẵn sàng thay đổi theo phiên bản, lưu lượng, cấu hình và phụ thuộc. Do đó, assurance phải tạo vòng lặp rõ ràng:

| Giai đoạn | Việc cần thực hiện | Bằng chứng/đầu ra |
| --- | --- | --- |
| **Thiết kế** | BIA, threat modeling, xác định SLI/SLO, RTO/RPO, phụ thuộc và điểm lỗi chung. | Hồ sơ rủi ro, kiến trúc, tiêu chí chấp nhận, owner. |
| **Phát triển** | Tạo timeout, retry phù hợp, idempotency, phân tách lỗi; kiểm thử đường xử lý thất bại. | Review code, test report, cấu hình, thay đổi đã phê duyệt. |
| **Trước release** | Load/soak test, đánh giá năng lực, kiểm tra rollback và các luồng trọng yếu có nguy cơ bị ảnh hưởng. | Báo cáo test gắn với bản phát hành, quyết định release. |
| **Trong production** | Theo dõi SLI theo nhu cầu người dùng, error budget, alert, capacity và phụ thuộc. | Dashboard, alert lịch sử, log có kiểm soát, bằng chứng vận hành. |
| **Ứng cứu/khôi phục** | Diễn tập failover, restore, mất phụ thuộc; xử lý sự cố thật theo runbook. | Timeline, đo RTO/RPO, kết quả restore, quyết định rủi ro. |
| **Sau thay đổi/sự cố** | Đánh giá lại các claim, khắc phục phát hiện, kiểm chứng lại và cập nhật rủi ro. | Retest, action tracking, phiên bản claim/evidence mới. |

### Những thay đổi cần xem lại bằng chứng

Ví dụ: thêm tính năng cần database, tăng lưu lượng, đổi cơ chế xác thực, di chuyển vùng, thay nhà cung cấp DNS, thêm batch job tiêu thụ tài nguyên, cập nhật chính sách rate limit, đổi chiến lược backup hoặc xuất hiện hình thức tấn công mới.

Không phải lần thay đổi nào cũng cần diễn tập thảm họa toàn diện. Nhưng phải **đánh giá ảnh hưởng đến claim**, chọn phép kiểm tra phù hợp và biết bằng chứng cũ còn đại diện cho hệ thống mới hay không.

### Độc lập và khả năng kiểm toán

Khi claim có tác động cao, nên có người hoặc nhóm không trực tiếp triển khai control tham gia review theo mức rủi ro. Hồ sơ phục vụ audit cần giữ **định nghĩa mục tiêu, phạm vi, phương pháp đo, kết quả gốc, ngoại lệ, người phê duyệt và thời hạn đánh giá lại**. Đánh giá độc lập tăng độ tin cậy, nhưng bản thân việc được audit không chứng minh availability trong mọi tình huống tương lai.

## 9. Những sai lầm phổ biến khi đánh giá tính sẵn sàng

| Nhận định sai | Cách đánh giá đúng |
| --- | --- |
| “Có nhiều server thì không thể downtime.” | Phải kiểm tra điểm lỗi chung, dữ liệu, mạng, IAM, DNS và quy trình failover. |
| “Health check 200 nghĩa là khách dùng được.” | Đo giao dịch đầu cuối và độ trễ theo yêu cầu nghiệp vụ. |
| “SLO 99,99% là tốt nhất cho mọi chức năng.” | Đặt ngưỡng theo BIA, rủi ro, chi phí, khả năng triển khai và nhu cầu thực. |
| “Đã cấu hình autoscaling nên chịu được mọi mức tải.” | Kiểm tra giới hạn quota, tốc độ scale, database, hàng đợi và tải đột biến. |
| “Có backup hằng ngày nghĩa là đạt RTO/RPO.” | Backup phải restore được; đo thời gian phục hồi và điểm dữ liệu có thể khôi phục theo kịch bản. |
| “SLO trung bình toàn hệ thống đạt thì mọi khách đều ổn.” | Phân tích theo khu vực, tenant, kênh sử dụng và luồng nghiệp vụ quan trọng. |
| “Có công cụ chống DDoS thì đảm bảo luôn truy cập được.” | Cần đánh giá ngưỡng, hành vi lọc nhầm, phụ thuộc và kịch bản tấn công; không có bảo vệ tuyệt đối. |
| “Mọi lần retry đều tăng độ tin cậy.” | Retry vô hạn có thể làm phụ thuộc quá tải và tạo hiệu ứng thác lỗi; cần giới hạn và thiết kế idempotency. |
| “Hết sự cố thì claim tự động đạt lại.” | Phải xác minh phục hồi, xem lại bằng chứng, đo tác động và xử lý nguyên nhân. |

## 10. Checklist xây dựng một claim về availability

Khi cần lập kế hoạch assurance cho một chức năng quan trọng, hãy trả lời lần lượt:

1. **Chức năng và nhóm người dùng nào** cần sẵn sàng, ở vùng và khoảng thời gian nào?
2. **Hậu quả gián đoạn** là gì; kịch bản rủi ro và phụ thuộc quan trọng đã được ghi nhận chưa?
3. **SLI, SLO và điều kiện thành công** có đo được, không bỏ sót yêu cầu lỗi/timeout/độ trễ không?
4. **RTO/RPO** có cần thiết theo BIA, được định nghĩa cho kịch bản phục hồi cụ thể chưa?
5. **Controls ngăn ngừa, phát hiện, ứng phó, khôi phục** đã được chọn theo rủi ro chưa; có điểm lỗi chung nào?
6. **Bằng chứng thử nghiệm và vận hành** có đúng môi trường, phiên bản, tải và phạm vi; có kết quả gốc truy xuất được không?
7. **Giới hạn và phát hiện chưa xử lý** đã có owner, mức ưu tiên, thời hạn, quyết định chấp nhận rủi ro chưa?
8. **Cơ chế đánh giá lại** sau thay đổi, sự cố và diễn tập định kỳ đã được xác lập chưa?

### Tự kiểm tra hiểu bài

**Tình huống A:** Hệ thống có uptime theo thời gian 99,99%, nhưng 15% người dùng của một vùng không thể hoàn tất thanh toán. Có thể kết luận tính sẵn sàng của chức năng thanh toán đạt không?

**Gợi ý:** Không thể chỉ dựa vào uptime máy chủ. Cần xác định claim và SLI của giao dịch thanh toán trong phạm vi vùng/người dùng, đo lỗi và tác động thực tế.

**Tình huống B:** Một diễn tập cho kết quả failover 20 phút, nhưng bản sao phục hồi thiếu giao dịch của 40 phút gần nhất. Nếu mục tiêu RTO là 30 phút và RPO là 5 phút, đánh giá thế nào?

**Gợi ý:** Phần thời gian phục hồi có thể đạt RTO theo điều kiện diễn tập, nhưng **không đạt RPO**. Không được công bố toàn bộ mục tiêu phục hồi đã đáp ứng.

**Tình huống C:** Có báo cáo stress test đạt từ sáu tháng trước, sau đó nhóm đổi database và triển khai endpoint export mới. Bằng chứng cũ có đủ cho claim availability hiện tại?

**Gợi ý:** Chưa đủ. Phải phân tích tác động của thay đổi, kiểm chứng lại các phụ thuộc và luồng bị ảnh hưởng, đồng thời đối chiếu số liệu vận hành hiện hành.

## Kết luận

Tính sẵn sàng là khả năng hệ thống **phục vụ được nhu cầu hợp lệ vào đúng thời điểm với chất lượng đáp ứng đã cam kết**. Để bảo đảm bằng chứng cho mục tiêu này, cần đi từ **tác động nghiệp vụ và rủi ro** đến **định nghĩa đo lường**, triển khai **controls**, thu thập **bằng chứng kiểm thử/vận hành**, đánh giá **giới hạn**, xử lý **phát hiện**, rồi **kiểm tra lại theo thay đổi**. Một hệ thống có nhiều lớp dự phòng nhưng thiếu phép đo đầu cuối, kế hoạch phục hồi được diễn tập và hồ sơ bằng chứng vẫn chưa có đủ cơ sở để tuyên bố rằng mục tiêu availability đã được đáp ứng.

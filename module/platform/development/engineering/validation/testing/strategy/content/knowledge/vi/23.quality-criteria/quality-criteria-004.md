# Đặt ngưỡng hiệu năng, độ tin cậy và bảo mật theo bối cảnh

Ngưỡng chất lượng là điều kiện cụ thể để xác định một hệ thống có đáp ứng nhu cầu vận hành và mức rủi ro đã chấp nhận hay không. Một API có thể phản hồi nhanh trong môi trường thử nghiệm nhưng chậm khi có tải thật; một dịch vụ có tỷ lệ hoạt động cao nhưng vẫn mất giao dịch; một bản dựng không có lỗ hổng mức nghiêm trọng theo công cụ quét nhưng vẫn cho phép người dùng truy cập dữ liệu ngoài quyền. Vì vậy, ngưỡng hiệu năng, độ tin cậy và bảo mật cần được đặt theo bối cảnh sử dụng, hậu quả khi thất bại và bằng chứng có thể thu thập.

Không có một bộ số liệu chung phù hợp cho mọi sản phẩm. Ngưỡng quá lỏng có thể để rủi ro quan trọng đi vào vận hành; ngưỡng quá chặt có thể làm pipeline chặn thường xuyên, tăng chi phí và khuyến khích nhóm tìm cách né kiểm soát. Cách làm phù hợp là xác định mục tiêu nghiệp vụ, phân loại mức quan trọng, chọn chỉ số phản ánh trải nghiệm hoặc rủi ro, thiết lập phương pháp đo và thống nhất ngưỡng trước khi kiểm thử.

## 1. Phân biệt yêu cầu, mục tiêu, ngưỡng và cam kết dịch vụ

Các khái niệm liên quan nhưng có vai trò khác nhau:

- **Yêu cầu chất lượng:** mô tả thuộc tính hệ thống cần đáp ứng, chẳng hạn giao dịch phải được xử lý chính xác và người dùng nhận được phản hồi trong thời gian phù hợp.
- **Chỉ số đo (metric):** giá trị được thu thập, như độ trễ, tỷ lệ lỗi, số lần gián đoạn, thời gian khôi phục hoặc số lỗ hổng theo mức độ.
- **SLI (Service Level Indicator):** chỉ số đại diện cho chất lượng dịch vụ mà người dùng hoặc hệ thống phụ thuộc trải nghiệm, ví dụ tỷ lệ request thành công hoặc độ trễ p95.
- **SLO (Service Level Objective):** mục tiêu nội bộ cho một SLI trong khoảng thời gian xác định.
- **SLA (Service Level Agreement):** cam kết dịch vụ với khách hàng hoặc đối tác, có thể kèm điều kiện, loại trừ và hệ quả khi không đạt.
- **Ngưỡng chấp nhận (acceptance threshold):** ranh giới dùng để đánh giá một phép kiểm tra hoặc một lần phát hành có đáp ứng yêu cầu đã thống nhất không.
- **Ngưỡng cảnh báo và ngưỡng dừng:** mức kích hoạt điều tra, giảm tải, rollback hoặc dừng thử nghiệm.

Một SLO không tự động trở thành SLA. Mục tiêu nội bộ có thể nghiêm ngặt hơn cam kết hợp đồng để nhóm có khoảng đệm xử lý trước khi ảnh hưởng khách hàng. Tương tự, một ngưỡng trong bài kiểm thử tải là điều kiện cho workload và môi trường cụ thể; nó không thể đại diện cho mọi điều kiện vận hành.

Khi ghi một ngưỡng, cần nêu chỉ số, phạm vi, điều kiện đo, cửa sổ thời gian, nguồn dữ liệu, ngưỡng đạt và hành động nếu không đạt. Một con số không có định nghĩa đo lường sẽ dễ bị hiểu khác nhau giữa nhóm phát triển, kiểm thử và vận hành.

## 2. Xác định bối cảnh trước khi chọn con số

Ngưỡng phải bắt nguồn từ tác động và nhu cầu thực tế. Trước khi chọn mục tiêu, hãy hiểu:

- **Mức quan trọng của nghiệp vụ:** chức năng có ảnh hưởng đến thanh toán, dữ liệu quan trọng, an toàn, nghĩa vụ pháp lý hoặc hoạt động cốt lõi không?
- **Người dùng và thời điểm sử dụng:** người dùng cần phản hồi ngay, có thể chờ xử lý nền hay chấp nhận bảo trì theo lịch?
- **Hậu quả khi thất bại:** mất doanh thu, giao dịch trùng, dữ liệu sai, lộ thông tin, gián đoạn nội bộ hay chỉ gây bất tiện nhỏ?
- **Mô hình tải:** số người dùng đồng thời, lưu lượng trung bình, đỉnh theo mùa, burst, kích thước dữ liệu và phân bố request.
- **Kiến trúc và phụ thuộc:** hệ thống đồng bộ hay bất đồng bộ, có queue, nhà cung cấp bên ngoài, database dùng chung hoặc vùng dự phòng không?
- **Khả năng phục hồi:** có retry, idempotency, backup, failover, rollback và quy trình vận hành không?
- **Môi trường triển khai:** cloud, thiết bị biên, mạng di động, khu vực địa lý, cấu hình tài nguyên và giới hạn nền tảng.
- **Nghĩa vụ và chính sách:** hợp đồng, quy định, tiêu chuẩn bảo mật, thời hạn lưu trữ hoặc yêu cầu kiểm toán.
- **Khả năng đo:** có telemetry đủ tin cậy, dữ liệu lịch sử và môi trường đại diện để xác minh không?

Cùng một chỉ số có thể cần ngưỡng khác nhau giữa các luồng. Trang xem danh mục có thể chấp nhận độ trễ cao hơn một bước xác nhận thanh toán. Một báo cáo nội bộ chạy ban đêm có thể ưu tiên tính hoàn tất và độ chính xác hơn phản hồi tức thời. Một hệ thống điều khiển thiết bị có thể có giới hạn thời gian nghiêm ngặt vì phản hồi chậm gây nguy hiểm.

Hãy phân loại luồng hoặc tài sản theo mức quan trọng trước, rồi mới đặt mục tiêu cho từng nhóm. Tránh gán cùng một ngưỡng cho toàn bộ ứng dụng nếu các chức năng có hậu quả và mô hình sử dụng khác nhau.

## 3. Phân tầng mức quan trọng và rủi ro

Một ma trận phân tầng giúp quyết định nơi cần ngưỡng nghiêm ngặt và bằng chứng sâu hơn.

| Mức | Đặc điểm bối cảnh | Cách đặt ngưỡng |
|---|---|---|
| Tối quan trọng | Thất bại có thể gây mất tiền, mất dữ liệu, lộ dữ liệu nhạy cảm, nguy cơ an toàn hoặc vi phạm nghĩa vụ lớn | Ngưỡng rõ, gate bắt buộc, kiểm thử nhiều điều kiện, giám sát và phương án phục hồi |
| Cao | Ảnh hưởng lớn đến hành trình chính hoặc nhiều khách hàng, có giới hạn workaround | Mục tiêu chặt theo luồng, kiểm thử hồi quy và kiểm tra vận hành trước release |
| Trung bình | Ảnh hưởng một nhóm chức năng hoặc có phương án thay thế | Ngưỡng dựa trên trải nghiệm và mức sử dụng, xác minh theo rủi ro |
| Thấp | Ít sử dụng, tác động nhỏ và dễ phục hồi | Mục tiêu phù hợp chi phí, kiểm tra định kỳ hoặc theo thay đổi |

Phân tầng không nên chỉ dựa vào tần suất. Một chức năng ít được dùng nhưng xử lý dữ liệu nhạy cảm có thể vẫn là rủi ro tối quan trọng. Một lỗi hiếm nhưng gây giao dịch trùng hoặc mất dữ liệu có thể cần ngưỡng kiểm soát nghiêm ngặt.

Ghi rõ lý do xếp hạng, người chịu trách nhiệm và sự kiện làm thay đổi mức quan trọng. Khi sản phẩm mở rộng sang khách hàng hoặc khu vực mới, mức rủi ro và nghĩa vụ có thể thay đổi; ngưỡng cần được xem xét lại.

## 4. Đặt ngưỡng hiệu năng dựa trên trải nghiệm và workload

Hiệu năng không chỉ là thời gian phản hồi trung bình. Cần xác định người dùng đang chờ điều gì, tải nào cần hỗ trợ và hệ thống còn đủ tài nguyên hay không.

### 4.1. Chọn chỉ số phù hợp

Các chỉ số thường dùng:

- **Latency:** thời gian từ lúc bắt đầu yêu cầu đến khi nhận kết quả. Với luồng bất đồng bộ, cần phân biệt thời gian nhận xác nhận và thời gian hoàn tất nghiệp vụ.
- **Percentile latency:** p50, p90, p95 hoặc p99 cho biết độ trễ tại các phân vị. p95 giúp quan sát trải nghiệm của phần lớn request, còn p99 làm lộ nhóm request rất chậm.
- **Throughput:** số request, giao dịch hoặc tác vụ hoàn tất trong một đơn vị thời gian.
- **Concurrency:** số yêu cầu hoặc phiên đang hoạt động cùng lúc.
- **Error rate:** tỷ lệ yêu cầu thất bại, timeout hoặc trả kết quả không hợp lệ.
- **Resource utilization:** CPU, memory, disk I/O, network, connection pool và thread.
- **Queue depth và processing lag:** số tác vụ đang chờ và độ trễ xử lý nền.
- **Saturation:** mức tài nguyên hoặc giới hạn đã gần cạn, khiến hiệu năng suy giảm nhanh khi tải tăng.

Chọn chỉ số gắn với hành trình nghiệp vụ. Ví dụ, API trả HTTP 200 rất nhanh nhưng giao dịch chưa được ghi bền vững thì không thể coi là hoàn tất. Cần đo đến điểm mà hệ thống đã đáp ứng cam kết thực sự.

### 4.2. Dùng phân vị thay cho chỉ số trung bình đơn lẻ

Trung bình có thể che khuất các request rất chậm. Giả sử đa số request phản hồi nhanh nhưng một nhóm nhỏ bị chờ lock database, người dùng gặp vấn đề vẫn có thể đáng kể dù trung bình đẹp.

Báo cáo nên ghi ít nhất phân vị phù hợp, số mẫu và cửa sổ đo. Với lưu lượng thấp, p99 có thể dao động mạnh do số mẫu ít; khi đó cần thêm thời lượng, số lần lặp hoặc phương pháp đo phù hợp.

### 4.3. Mô hình hóa tải thực tế

Workload nên phản ánh:

- Tỷ lệ các loại request và hành trình người dùng.
- Tải bình thường, giờ cao điểm và burst.
- Số người dùng đồng thời và tốc độ tăng tải.
- Kích thước payload và phân bố dữ liệu.
- Tác vụ nền, batch và truy vấn cạnh tranh tài nguyên.
- Hành vi retry, timeout và reconnect.
- Phụ thuộc bên ngoài và giới hạn quota.

Không nên đặt ngưỡng hiệu năng chỉ từ một bài benchmark với request lặp đơn giản nếu production có nhiều loại giao dịch và dữ liệu lớn. Ghi rõ workload nào đã được xác minh và phần nào chưa được mô phỏng.

## 5. Xác định ngưỡng hiệu năng từ baseline và mục tiêu nghiệp vụ

Có thể xây dựng ngưỡng theo quy trình:

1. Chọn luồng nghiệp vụ và chỉ số cần đo.
2. Thu thập baseline từ hệ thống hiện tại hoặc nguyên mẫu đại diện.
3. Xác định tải mục tiêu và điều kiện đỉnh dựa trên dự báo sử dụng.
4. Trao đổi với chủ sở hữu sản phẩm về trải nghiệm có thể chấp nhận.
5. Đánh giá năng lực tài nguyên và chi phí vận hành.
6. Đặt ngưỡng đạt, ngưỡng cảnh báo và ngưỡng dừng.
7. Chạy thử nhiều lần và đánh giá độ biến thiên.
8. Ghi rõ môi trường, dữ liệu, cấu hình và phương pháp đo.

Baseline không phải lúc nào cũng là mục tiêu. Nếu hệ thống hiện tại đã chậm, chỉ yêu cầu không kém baseline có thể giữ nguyên trải nghiệm kém. Ngược lại, đặt mục tiêu cải thiện quá lớn mà không có cơ sở về nhu cầu hoặc kiến trúc có thể làm tăng chi phí không cần thiết.

Nên tách mục tiêu hiệu năng theo loại tải. Ví dụ, tải bình thường cần đáp ứng trải nghiệm tương tác; tải đỉnh cần không vượt giới hạn suy giảm đã chấp nhận; stress test cần xác định điểm bão hòa và hành vi khi vượt công suất. Các mục tiêu này trả lời những câu hỏi khác nhau.

## 6. Đặt ngưỡng độ tin cậy theo cách dịch vụ thất bại và phục hồi

Độ tin cậy không chỉ là uptime. Một dịch vụ có thể luôn trả lời nhưng thường xuyên trả dữ liệu sai; có thể tự phục hồi nhanh nhưng làm mất giao dịch; hoặc có availability cao nhưng không thể khôi phục sau mất dữ liệu.

Các chiều cần xem xét:

- **Availability:** tỷ lệ thời gian hoặc yêu cầu mà dịch vụ có thể cung cấp chức năng đã cam kết.
- **Correctness:** kết quả và trạng thái nghiệp vụ có đúng không.
- **Reliability under load:** dịch vụ có duy trì hành vi đúng khi tải tăng không.
- **Fault tolerance:** hệ thống xử lý thế nào khi thành phần hoặc phụ thuộc gặp lỗi.
- **Recoverability:** thời gian và mức độ đầy đủ khi khôi phục dịch vụ hoặc dữ liệu.
- **Durability:** dữ liệu đã xác nhận có được giữ bền vững theo cam kết không.
- **Consistency:** trạng thái giữa các thành phần hội tụ theo quy tắc đã định không.
- **Idempotency:** retry hoặc gửi lặp có tạo tác dụng phụ ngoài dự kiến không.

Với từng chiều, hãy xác định SLI phù hợp. Ví dụ, availability có thể đo bằng tỷ lệ request hợp lệ thành công; correctness cần đối soát trạng thái và kết quả nghiệp vụ; recoverability cần diễn tập restore hoặc failover.

### 6.1. Availability và error budget

Nếu mục tiêu availability là \(A\), phần thời gian không khả dụng tối đa trong cùng cửa sổ được tính gần đúng là:

\[
\text{Downtime budget} = (1-A)\times \text{thời lượng cửa sổ}
\]

Ví dụ minh họa: mục tiêu 99,9% trong cửa sổ 30 ngày cho phép khoảng 0,1% thời gian không khả dụng trong cửa sổ đó. Con số này chỉ có ý nghĩa khi định nghĩa availability, cửa sổ đo, loại lỗi được tính và cách xử lý bảo trì đã được thống nhất.

Error budget là phần lỗi hoặc gián đoạn có thể xảy ra trong giới hạn SLO. Khi tiêu thụ ngân sách quá nhanh, nhóm có thể giảm tốc độ thay đổi, tập trung sửa độ tin cậy hoặc tăng kiểm soát release. Không dùng error budget để hợp thức hóa mất dữ liệu hoặc vi phạm bảo mật; những rủi ro này cần điều kiện riêng.

### 6.2. RPO và RTO

Với hệ thống cần khôi phục dữ liệu và dịch vụ, xác định:

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa có thể chấp nhận, tính theo khoảng thời gian dữ liệu có thể bị mất.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ về mức hoạt động đã định.

RPO/RTO phải dựa trên tác động nghiệp vụ, cơ chế backup, replication và khả năng vận hành. Chỉ cấu hình backup thành công không chứng minh RPO/RTO đạt; cần diễn tập restore và đo kết quả thực tế.

## 7. Đặt ngưỡng bảo mật theo tài sản, mối đe dọa và khả năng khai thác

Bảo mật không thể được rút gọn thành một con số lỗ hổng. Một phát hiện cần được đánh giá trong bối cảnh tài sản, đường truy cập, khả năng khai thác và hậu quả.

Các yếu tố cần xem xét:

- **Tài sản:** dữ liệu cá nhân, thông tin thanh toán, bí mật kinh doanh, tài khoản đặc quyền hoặc dịch vụ công khai.
- **Mối đe dọa:** ai có thể tấn công, động cơ và năng lực của họ.
- **Khả năng khai thác:** lỗ hổng có thể truy cập từ đâu, có cần xác thực hoặc điều kiện đặc biệt không.
- **Tác động:** lộ dữ liệu, sửa dữ liệu, chiếm quyền, gián đoạn hoặc ảnh hưởng dây chuyền.
- **Phơi nhiễm:** internet-facing, mạng nội bộ, môi trường cô lập hay thành phần chỉ chạy trong pipeline.
- **Biện pháp giảm thiểu:** phân đoạn mạng, quyền tối thiểu, WAF, mã hóa, giám sát hoặc kiểm soát khác.
- **Nghĩa vụ:** quy định, hợp đồng, tiêu chuẩn và chính sách nội bộ.

Có thể dùng CVSS hoặc hệ thống phân loại nội bộ để sàng lọc mức độ kỹ thuật, nhưng không nên dùng điểm số làm quyết định duy nhất. Một lỗ hổng điểm cao ở thành phần không thể truy cập có thể có rủi ro thực tế khác với lỗ hổng điểm thấp nhưng cho phép truy cập trái phép vào dữ liệu nhạy cảm trong luồng công khai.

### 7.1. Xác định điều kiện bảo mật bắt buộc

Một số điều kiện thường cần được định nghĩa như gate rõ ràng:

- Không để lộ secret, private key hoặc credential trong repository, log và artifact.
- Xác thực và phân quyền phải được kiểm tra ở phía máy chủ cho mọi thao tác nhạy cảm.
- Người dùng không được đọc hoặc sửa dữ liệu ngoài phạm vi tenant/role.
- Dữ liệu nhạy cảm được mã hóa và truy cập theo chính sách.
- Dependency và image được kiểm tra theo chính sách rủi ro.
- Các lỗ hổng vượt ngưỡng chặn phải được xử lý hoặc có ngoại lệ được phê duyệt.
- Audit log phải ghi nhận hành động đặc quyền và sự kiện quan trọng.
- Cơ chế bảo mật quan trọng phải được kiểm thử trong cấu hình gần thực tế.

Các ngưỡng cụ thể về mức độ lỗ hổng, thời hạn khắc phục và phạm vi kiểm tra phải tuân theo chính sách và nghĩa vụ của tổ chức. Không tự đặt thời hạn phổ quát nếu chưa có chủ sở hữu rủi ro xác nhận.

### 7.2. Đặt thời hạn xử lý theo rủi ro

Có thể phân loại phát hiện theo mức ưu tiên để gắn thời hạn phản hồi:

| Mức xử lý | Đặc điểm thường gặp | Hướng hành động |
|---|---|---|
| Khẩn cấp | Có dấu hiệu khai thác, lộ secret hoặc ảnh hưởng tài sản trọng yếu | Cô lập, thu hồi credential, giảm phơi nhiễm và kích hoạt quy trình incident |
| Cao | Có khả năng khai thác thực tế và tác động đáng kể | Ưu tiên điều tra, sửa và xác minh trước mốc release liên quan |
| Trung bình | Có điều kiện khai thác hạn chế hoặc biện pháp giảm thiểu đáng tin cậy | Lập kế hoạch khắc phục, theo dõi và đánh giá lại |
| Thấp | Tác động giới hạn hoặc khó khai thác trong bối cảnh hiện tại | Xử lý theo backlog và chính sách, giữ bằng chứng đánh giá |

Bảng này là khung phân loại; mức và thời hạn phải được điều chỉnh theo chính sách bảo mật, nghĩa vụ pháp lý và bối cảnh tài sản. Khi có dấu hiệu bị khai thác, ưu tiên ứng phó sự cố thay vì chờ lịch sửa thông thường.

## 8. Không dùng một ngưỡng chung cho mọi lớp và mọi môi trường

Ngưỡng ở unit test, pull request, staging và production có mục đích khác nhau.

- **Local và unit test:** ưu tiên tính xác định, phản hồi nhanh và kiểm tra logic.
- **Pull request:** chặn lỗi có thể phát hiện sớm, sai lệch hợp đồng, secret và rủi ro dependency theo chính sách.
- **Integration/staging:** xác minh tương tác, workload đại diện, cấu hình, phân quyền và hành vi phục hồi.
- **Pre-production:** xác minh gần điều kiện phát hành, kiểm tra tải, bảo mật và quy trình vận hành cần thiết.
- **Production:** theo dõi SLI/SLO, cảnh báo, error budget và tín hiệu thực tế; mọi thử nghiệm chủ động cần giới hạn và phê duyệt.

Một ngưỡng hiệu năng đo trên laptop không thể dùng làm cam kết production. Một kết quả quét staging không đủ để kết luận cấu hình production giống hệt nếu còn khác biệt IAM, network hoặc secret. Cần ghi rõ môi trường và giới hạn suy rộng của từng bằng chứng.

## 9. Kết hợp ngưỡng hiệu năng, độ tin cậy và bảo mật

Ba nhóm thuộc tính có thể xung đột. Ví dụ, tăng mã hóa, kiểm tra quyền hoặc ghi audit có thể làm tăng độ trễ và mức sử dụng CPU. Tăng retry có thể cải thiện tỷ lệ thành công tạm thời nhưng làm quá tải dịch vụ phụ thuộc. Giảm timeout có thể bảo vệ tài nguyên nhưng khiến người dùng thấy nhiều lỗi hơn.

Khi đặt ngưỡng, cần đánh giá các tác động đồng thời:

- Hiệu năng có đạt mục tiêu khi bật các kiểm soát bảo mật bắt buộc không?
- Retry và timeout có tạo request trùng hoặc khuếch đại tải không?
- Cơ chế dự phòng có bảo toàn dữ liệu và quyền truy cập không?
- Giám sát bảo mật có đủ tín hiệu mà không làm lộ dữ liệu nhạy cảm không?
- Mức mã hóa, logging và audit có ảnh hưởng đáng kể đến latency không?
- Khi giảm tải hoặc failover, hệ thống có giữ đúng ranh giới phân quyền không?

Không nên tối ưu một chỉ số bằng cách làm suy giảm thuộc tính quan trọng khác. Nếu không thể đáp ứng đồng thời, ghi rõ trade-off, rủi ro, biện pháp giảm thiểu và người có thẩm quyền quyết định.

## 10. Viết ngưỡng thành tiêu chí có thể kiểm chứng

Một ngưỡng tốt cần đủ cụ thể để hai nhóm độc lập có thể đo và đưa ra kết luận tương đương.

Mẫu mô tả:

| Thành phần | Nội dung cần xác định |
|---|---|
| Đối tượng | API, hành trình, dịch vụ, tài sản hoặc môi trường |
| Rủi ro/nghiệp vụ | Vì sao thuộc tính này quan trọng |
| SLI hoặc chỉ số | Đại lượng được đo và đơn vị |
| Điều kiện | Tải, dữ liệu, vai trò, cấu hình, cửa sổ thời gian |
| Phương pháp | Công cụ, nguồn telemetry, số lần chạy và cách tổng hợp |
| Ngưỡng đạt | Giá trị hoặc điều kiện chấp nhận |
| Ngưỡng cảnh báo/dừng | Khi nào cần điều tra, giảm tải hoặc dừng |
| Ngoại lệ | Người phê duyệt, lý do, giới hạn và thời hạn |
| Bằng chứng | Báo cáo, log, trace, kết quả test và phiên bản |
| Chủ sở hữu | Người chịu trách nhiệm duy trì mục tiêu |

Ví dụ diễn đạt tốt hơn:

- “Với workload gồm tỷ lệ request đã thống nhất, chạy trên staging có cấu hình tài nguyên được ghi nhận trong thời lượng quy định; độ trễ p95 của API tạo đơn phải nằm trong ngưỡng được chủ sở hữu sản phẩm phê duyệt và tỷ lệ lỗi không vượt giới hạn đã định.”
- “Trong cửa sổ đo SLO đã công bố, tỷ lệ request hợp lệ hoàn tất đúng nghiệp vụ phải đạt mục tiêu; request bị từ chối do validation của người dùng được phân loại riêng.”
- “Không có phát hiện bảo mật vượt ngưỡng chặn theo chính sách đối với thành phần có thể truy cập từ internet, trừ ngoại lệ được người có thẩm quyền phê duyệt và còn hiệu lực.”

Các câu này cần được điền ngưỡng và điều kiện cụ thể cho sản phẩm. Không nên để cụm “ngưỡng đã thống nhất” tồn tại trong tiêu chí cuối cùng mà không có giá trị hoặc liên kết đến nguồn quyết định.

## 11. Thiết kế phép đo và bằng chứng đáng tin cậy

Một ngưỡng chỉ có ý nghĩa nếu phương pháp đo phù hợp. Trước khi chạy kiểm thử, xác định:

- Môi trường và cấu hình có đại diện cho mục tiêu không?
- Dataset có đủ lớn và phản ánh phân bố thực tế không?
- Đồng hồ và timestamp có đồng bộ không?
- Công cụ tạo tải có đủ năng lực và không trở thành bottleneck?
- Có warm-up, cache state và thời gian ổn định phù hợp không?
- Số lần chạy và số mẫu có đủ để diễn giải phân vị không?
- Lỗi môi trường và request không hợp lệ có được phân loại riêng không?
- Có thể liên kết metric với build, commit, cấu hình và workload không?

Với reliability test, cần xác định cửa sổ quan sát và loại sự kiện được tính. Một lần chạy smoke test thành công không chứng minh availability hàng tháng. Với security test, cần ghi phạm vi, phiên bản công cụ, tài sản, quyền và giới hạn kiểm tra; một lần quét tự động không chứng minh không tồn tại lỗ hổng.

Bằng chứng nên gồm dữ liệu thô hoặc báo cáo đủ chi tiết, phương pháp, cấu hình, người thực hiện và kết luận. Khi có ngoại lệ hoặc sai lệch, lưu cả giới hạn để người xem xét không hiểu kết quả vượt quá phạm vi thực tế.

## 12. Xác định ngưỡng cảnh báo, ngưỡng dừng và hành động vận hành

Ngưỡng đạt trong kiểm thử không nhất thiết trùng với ngưỡng cảnh báo trong vận hành. Cần định nghĩa hành động tương ứng với từng mức.

Ví dụ:

- **Đạt mục tiêu:** tiếp tục quy trình và lưu bằng chứng.
- **Gần ngưỡng:** theo dõi thêm, phân tích xu hướng và xác định khả năng tăng tải.
- **Vượt ngưỡng cảnh báo:** mở điều tra, kiểm tra phụ thuộc và chuẩn bị biện pháp giảm thiểu.
- **Vượt ngưỡng dừng:** dừng tải hoặc rollout nếu tiếp tục có thể gây ảnh hưởng lớn.
- **Vi phạm điều kiện bảo mật bắt buộc:** chặn phát hành hoặc kích hoạt quy trình xử lý sự cố theo chính sách.

Với kiểm thử tải, cần có giới hạn request, thời gian và tài nguyên để không làm sập môi trường dùng chung. Với kiểm thử bảo mật, cần điều kiện dừng khi phát hiện tác động ngoài phạm vi. Với diễn tập phục hồi, cần người có quyền dừng và kế hoạch khôi phục.

Ngưỡng không có hành động đi kèm dễ trở thành con số chỉ để báo cáo. Hãy xác định ai nhận cảnh báo, ai quyết định, thời gian phản hồi và bằng chứng cần có sau khi xử lý.

## 13. Quản lý ngoại lệ và chấp nhận rủi ro có thời hạn

Có trường hợp hệ thống chưa đáp ứng một ngưỡng nhưng phát hành vẫn được xem xét, chẳng hạn phụ thuộc bên ngoài chưa thể cải thiện ngay hoặc một phát hiện có biện pháp giảm thiểu tạm thời. Ngoại lệ phải minh bạch và có thẩm quyền.

Một hồ sơ ngoại lệ cần ghi:

- Ngưỡng hoặc tiêu chí chưa đạt.
- Phiên bản, môi trường và phạm vi bị ảnh hưởng.
- Bằng chứng đo được và mức sai lệch.
- Tác động đối với người dùng, dữ liệu và hoạt động.
- Lý do chấp nhận tạm thời.
- Biện pháp giảm thiểu và kế hoạch giám sát.
- Người sở hữu rủi ro và người phê duyệt.
- Ngày hết hạn hoặc điều kiện xem xét lại.
- Hành động khắc phục và cách xác minh.

Không dùng ngoại lệ để bỏ qua yêu cầu pháp lý hoặc nghĩa vụ không thể miễn trừ. Không gia hạn tự động mà không xem xét bằng chứng mới. Nếu mức rủi ro thay đổi hoặc xuất hiện dấu hiệu khai thác, quyết định cần được đánh giá lại ngay.

## 14. Ví dụ: đặt ngưỡng cho API thanh toán

Giả sử một nền tảng có API tạo giao dịch, xác nhận thanh toán và nhận callback từ nhà cung cấp. Các luồng có mức quan trọng cao vì lỗi có thể gây mất giao dịch, ghi nhận sai trạng thái hoặc xử lý trùng.

Nhóm bắt đầu bằng việc xác định bối cảnh:

- API tạo giao dịch phục vụ hành trình người dùng trực tiếp.
- Callback có thể đến trễ hoặc lặp.
- Nhà cung cấp bên ngoài có giới hạn quota và thời gian phản hồi riêng.
- Giao dịch phải được truy vết và đối soát.
- Dữ liệu thanh toán cần kiểm soát quyền và audit.
- Hệ thống có retry, queue và cơ chế idempotency.

Sau đó nhóm chọn các chiều đo:

| Thuộc tính | Chỉ số và điều kiện cần thống nhất | Bằng chứng |
|---|---|---|
| Hiệu năng | Độ trễ p95/p99 của bước tạo giao dịch dưới workload đại diện; tách thời gian phản hồi API và thời gian nhà cung cấp xử lý | Báo cáo tải, trace và tài nguyên |
| Độ tin cậy | Tỷ lệ giao dịch hoàn tất đúng trạng thái; tỷ lệ lỗi hệ thống; số giao dịch trùng sau retry | Contract/integration test, đối soát và log |
| Phục hồi | RPO/RTO theo yêu cầu nghiệp vụ; thời gian xử lý queue sau gián đoạn | Diễn tập restore, failover và queue recovery |
| Bảo mật | Không có truy cập chéo tenant; token và secret không xuất hiện trong log; phát hiện vượt ngưỡng chính sách được xử lý | Kiểm thử phân quyền, secret scan và security assessment |
| Khả năng truy vết | Mỗi giao dịch có mã tương quan nối request, callback và bản ghi đối soát | Trace, audit log và báo cáo đối chiếu |

Các giá trị số cụ thể cần được xác định từ dữ liệu tải, trải nghiệm người dùng, hợp đồng nhà cung cấp và chính sách rủi ro. Nhóm không nên lấy một con số mẫu rồi áp dụng ngay cho mọi API.

Trong kiểm thử, nhóm chạy workload đã thống nhất, gửi callback lặp và mô phỏng timeout. Hệ thống phải giữ một giao dịch duy nhất theo idempotency key, cuối cùng hội tụ về trạng thái đúng và có thể đối soát. Nếu API phản hồi nhanh nhưng trạng thái giao dịch bị trùng, tiêu chí reliability vẫn không đạt. Nếu test bảo mật không chứng minh được ranh giới tenant, không thể kết luận an toàn chỉ vì công cụ quét không báo lỗi.

Khi một chỉ số vượt ngưỡng, nhóm ghi rõ điều kiện, bằng chứng, mức ảnh hưởng và hành động. Ví dụ, độ trễ tăng do quota nhà cung cấp có thể cần thay đổi cách điều phối hoặc thương lượng giới hạn; lỗi truy cập chéo tenant cần được xử lý như vấn đề bảo mật nghiêm trọng theo chính sách.

## 15. Rà soát và cập nhật ngưỡng theo vòng đời sản phẩm

Ngưỡng không nên được đặt một lần rồi giữ nguyên bất kể sản phẩm thay đổi. Cần rà soát khi:

- Số người dùng, lưu lượng hoặc kích thước dữ liệu thay đổi đáng kể.
- Thêm luồng nghiệp vụ hoặc nhóm khách hàng mới.
- Kiến trúc, database, runtime hoặc nhà cung cấp thay đổi.
- Có sự cố production hoặc xu hướng suy giảm SLI.
- Thay đổi nghĩa vụ hợp đồng, quy định hoặc chính sách bảo mật.
- Mục tiêu kinh doanh hoặc mức chấp nhận rủi ro thay đổi.
- Công cụ đo hoặc phương pháp kiểm thử thay đổi.

Khi cập nhật, lưu giá trị cũ, giá trị mới, lý do, bằng chứng, người phê duyệt và thời điểm hiệu lực. Không thay ngưỡng chỉ để làm cho dashboard xanh hoặc giảm số lần pipeline fail. Nếu ngưỡng không còn phù hợp, cần chứng minh bằng dữ liệu và đánh giá tác động trước khi thay đổi.

Sau release, so sánh kết quả kiểm thử với telemetry thực tế. Nếu staging đạt nhưng production liên tục vượt ngưỡng, cần kiểm tra tính đại diện của workload, cấu hình, dữ liệu và phụ thuộc. Đây là tín hiệu để cải thiện cả phương pháp đo lẫn kiến trúc.

## 16. Quy trình đặt ngưỡng theo bối cảnh

Có thể áp dụng quy trình sau:

1. **Xác định luồng và tài sản:** lập danh sách chức năng, dữ liệu và phụ thuộc quan trọng.
2. **Đánh giá tác động:** phân loại hậu quả về trải nghiệm, doanh thu, dữ liệu, an toàn và nghĩa vụ.
3. **Chọn thuộc tính cần kiểm soát:** hiệu năng, availability, correctness, phục hồi, bảo mật hoặc kết hợp.
4. **Chọn SLI và phương pháp đo:** định nghĩa đại lượng, đơn vị, phạm vi, cửa sổ và nguồn dữ liệu.
5. **Thu thập baseline:** đo hệ thống hiện tại hoặc workload đại diện.
6. **Thống nhất mục tiêu và ngưỡng:** xác định đạt, cảnh báo, dừng và ngoại lệ với đúng chủ sở hữu.
7. **Thiết kế kiểm thử:** chuẩn bị môi trường, dữ liệu, tải, quyền và điều kiện lỗi.
8. **Chạy và đánh giá bằng chứng:** kiểm tra tính đại diện, số mẫu và giới hạn.
9. **Quyết định:** chấp nhận, khắc phục, giảm thiểu hoặc hoãn phát hành.
10. **Theo dõi sau release:** đối chiếu telemetry với mục tiêu và rà soát khi bối cảnh thay đổi.

~~~mermaid
flowchart TD
    A["Luồng nghiệp vụ và tài sản"] --> B["Đánh giá tác động và mức quan trọng"]
    B --> C["Chọn thuộc tính: hiệu năng, reliability, security"]
    C --> D["Định nghĩa SLI và phương pháp đo"]
    D --> E["Thu thập baseline và mô hình workload"]
    E --> F["Thống nhất ngưỡng đạt, cảnh báo và dừng"]
    F --> G["Thiết kế môi trường và kiểm thử"]
    G --> H["Thu thập, đánh giá bằng chứng"]
    H --> I{"Đáp ứng ngưỡng?"}
    I -->|Có| J["Ghi nhận và xem xét phát hành"]
    I -->|Không| K["Khắc phục hoặc đánh giá ngoại lệ"]
    K --> H
    J --> L["Theo dõi SLI/SLO sau release"]
    L --> M["Rà soát ngưỡng khi bối cảnh đổi"]
    M --> B
~~~

## 17. Checklist đặt ngưỡng hiệu năng, độ tin cậy và bảo mật

Trước khi phê duyệt tiêu chí chất lượng hoặc kế hoạch kiểm thử, hãy kiểm tra:

- Bối cảnh nghiệp vụ, người dùng và hậu quả khi thất bại đã rõ chưa?
- Tài sản và luồng đã được phân tầng theo mức quan trọng chưa?
- Mỗi ngưỡng có chỉ số, đơn vị, phạm vi, điều kiện và cửa sổ đo không?
- Hiệu năng có workload, concurrency, percentile và tài nguyên đại diện không?
- Reliability có đo correctness, availability, retry, phục hồi và dữ liệu bền vững khi cần không?
- RPO/RTO có được xác định theo tác động nghiệp vụ và diễn tập thực tế không?
- Security threshold có xét tài sản, khả năng khai thác, phơi nhiễm và biện pháp giảm thiểu không?
- Ngưỡng có phân biệt mục tiêu nội bộ, acceptance gate và cam kết SLA không?
- Môi trường và phương pháp đo có đủ đại diện, có ghi nhận giới hạn không?
- Có ngưỡng cảnh báo, ngưỡng dừng và người chịu trách nhiệm hành động không?
- Ngoại lệ có căn cứ, biện pháp giảm thiểu, người phê duyệt và thời hạn không?
- Bằng chứng có gắn với build, cấu hình, workload và thời điểm không?
- Ngưỡng có được rà soát khi tải, kiến trúc, khách hàng hoặc nghĩa vụ thay đổi không?
- Kết quả kiểm thử có được đối chiếu với telemetry sau phát hành không?

Đặt ngưỡng hiệu năng, độ tin cậy và bảo mật theo bối cảnh giúp nhóm kiểm soát đúng những rủi ro quan trọng của sản phẩm. Ngưỡng có giá trị khi xuất phát từ nhu cầu nghiệp vụ, được diễn đạt bằng chỉ số và điều kiện đo rõ ràng, có phương pháp thu thập bằng chứng phù hợp và gắn với hành động cụ thể. Khi bối cảnh thay đổi, mục tiêu cũng cần được rà soát để quyết định chất lượng tiếp tục phản ánh trải nghiệm người dùng và mức rủi ro mà tổ chức chấp nhận.


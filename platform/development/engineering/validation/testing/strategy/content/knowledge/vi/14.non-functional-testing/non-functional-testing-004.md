# Lựa chọn bằng chứng về chịu lỗi, phục hồi và độ sẵn sàng

Một hệ thống có thể vượt qua kiểm thử chức năng nhưng vẫn không đáp ứng nhu cầu khi một dịch vụ phụ thuộc ngừng hoạt động, mạng bị gián đoạn, dữ liệu bị hỏng hoặc lưu lượng tăng đột biến. Người dùng quan tâm đến việc công việc có tiếp tục được thực hiện hay không, dữ liệu có được bảo toàn không và dịch vụ có trở lại trong thời gian chấp nhận được không. Vì vậy, kiểm thử phi chức năng cần thu thập bằng chứng trực tiếp về khả năng chịu lỗi, phục hồi và độ sẵn sàng.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, lựa chọn bằng chứng có nghĩa là xác định thuộc tính cần chứng minh, tình huống lỗi đại diện, tín hiệu quan sát, tiêu chí đạt và giới hạn của kết luận. Một lần khởi động lại thành công chưa chứng minh hệ thống có thể phục hồi sau mất vùng; một dashboard không có cảnh báo đỏ chưa chứng minh người dùng truy cập được dịch vụ. Nhóm cần kết hợp kết quả kiểm thử có kiểm soát với dữ liệu vận hành, thử nghiệm khôi phục và xác nhận hành trình nghiệp vụ.

## 1. Phân biệt chịu lỗi, phục hồi và độ sẵn sàng

### Khả năng chịu lỗi

Khả năng chịu lỗi (fault tolerance) là khả năng duy trì chức năng được xác định khi một hoặc nhiều thành phần gặp lỗi. Hệ thống có thể tiếp tục đầy đủ chức năng, giảm một phần chức năng hoặc chuyển sang thành phần dự phòng.

Ví dụ:

- Một instance ứng dụng dừng nhưng request mới được định tuyến đến instance khác.
- Một node cache không sẵn sàng nhưng ứng dụng vẫn đọc được dữ liệu từ nguồn chính trong giới hạn tải.
- Một consumer dừng giữa lúc xử lý nhưng thông điệp được giao lại mà không tạo tác dụng phụ trùng.
- Một vùng triển khai gặp sự cố nhưng lưu lượng được chuyển sang vùng khác theo quy trình đã thiết kế.

Chịu lỗi không đồng nghĩa mọi lỗi đều vô hình với người dùng. Một hệ thống có thể tạm thời chậm hơn hoặc từ chối một chức năng ít quan trọng để bảo vệ giao dịch cốt lõi. Điều cần xác thực là hành vi suy giảm có kiểm soát và không vi phạm các bất biến quan trọng.

### Khả năng phục hồi

Khả năng phục hồi (recoverability) là khả năng đưa hệ thống và dữ liệu trở lại trạng thái hoạt động phù hợp sau gián đoạn hoặc hư hỏng. Phục hồi có thể cần khởi động lại, chuyển đổi dự phòng, khôi phục bản sao lưu, phát lại sự kiện, đồng bộ dữ liệu hoặc thực hiện thao tác bù.

Ví dụ:

- Khôi phục database từ backup và áp dụng log giao dịch đến thời điểm cần thiết.
- Khởi động lại worker và tiếp tục xử lý các thông điệp chưa được xác nhận.
- Phục hồi dịch vụ sau khi cấu hình sai được rollback.
- Đối soát giao dịch có kết quả không xác định sau khi nhà cung cấp thanh toán gián đoạn.

Phục hồi cần được đánh giá cả về thời gian và tính đúng đắn. Dịch vụ có thể khởi động lại nhanh nhưng dữ liệu thiếu hoặc sai; ngược lại, dữ liệu có thể được bảo toàn nhưng thời gian phục hồi vượt mức mà nghiệp vụ chấp nhận.

### Độ sẵn sàng

Độ sẵn sàng (availability) mô tả mức độ dịch vụ có thể được sử dụng khi cần. Độ sẵn sàng thường được đo trong một khoảng thời gian bằng tỷ lệ thời gian hoặc số yêu cầu đáp ứng điều kiện phục vụ đã thống nhất.

Một dịch vụ có thể có uptime cao ở cấp hạ tầng nhưng vẫn không sẵn sàng với người dùng nếu đăng nhập, thanh toán hoặc truy vấn quan trọng không hoạt động. Vì vậy, cần đo từ góc nhìn hành trình và định nghĩa rõ thế nào là một yêu cầu thành công.

### Phân biệt các thuộc tính liên quan

| Thuộc tính | Câu hỏi trọng tâm | Bằng chứng điển hình |
|---|---|---|
| Chịu lỗi | Khi thành phần lỗi, chức năng nào vẫn tiếp tục? | Kiểm thử failover, cô lập lỗi, degraded mode |
| Phục hồi | Sau sự cố, hệ thống và dữ liệu trở lại trạng thái đúng trong bao lâu? | Diễn tập restore, RTO/RPO, đối soát dữ liệu |
| Độ sẵn sàng | Người dùng có thể hoàn thành tác vụ khi cần không? | SLI/SLO, synthetic journey, tỷ lệ yêu cầu thành công |
| Độ tin cậy | Hệ thống có duy trì hành vi đúng theo thời gian không? | Tỷ lệ lỗi, sự cố, tính nhất quán và xu hướng vận hành |
| Khả năng bảo trì | Nhóm có thể chẩn đoán và sửa đổi hệ thống an toàn không? | Runbook, thời gian khôi phục, chất lượng phát hành và rollback |

Các thuộc tính liên quan nhưng không thay thế nhau. Hệ thống có dự phòng tốt vẫn có thể phục hồi dữ liệu kém; backup tốt vẫn không bảo đảm dịch vụ sẵn sàng trong lúc database chính ngừng hoạt động.

## 2. Bắt đầu từ hành trình quan trọng và mục tiêu dịch vụ

### Xác định công việc người dùng cần tiếp tục

Trước khi chọn bài kiểm thử, hãy xác định chức năng nào cần duy trì khi có lỗi. Một sản phẩm có thể có nhiều mức quan trọng:

- Đăng nhập và xác thực danh tính.
- Đọc hoặc cập nhật dữ liệu cốt lõi.
- Tạo giao dịch, thanh toán hoặc thay đổi trạng thái nghiệp vụ.
- Xem lịch sử và trạng thái giao dịch.
- Gửi thông báo hoặc tạo báo cáo.
- Chức năng phân tích, tìm kiếm hoặc cá nhân hóa.

Không phải mọi chức năng đều cần cùng mức sẵn sàng. Một báo cáo có thể chấp nhận xử lý trễ; một thao tác ghi nhận thanh toán có thể cần tính đúng đắn và khả năng truy vết nghiêm ngặt hơn khả năng tiếp tục ngay lập tức.

Với từng hành trình, hãy ghi rõ:

1. Ai cần sử dụng và vào thời điểm nào?
2. Hành động nào là cốt lõi?
3. Kết quả nào phải được bảo toàn khi có lỗi?
4. Chức năng nào có thể tạm ngừng hoặc suy giảm?
5. Người dùng cần được thông báo điều gì?
6. Có thể tiếp tục hoặc hoàn tất công việc sau khi dịch vụ phục hồi không?

### Xác định mức dịch vụ cần đạt

Mục tiêu dịch vụ nên gắn với kết quả có ý nghĩa. Các chỉ tiêu có thể gồm:

- Tỷ lệ yêu cầu hợp lệ được xử lý thành công.
- Tỷ lệ hoàn thành hành trình trong khoảng thời gian xác định.
- Độ trễ phản hồi ở các phân vị p95 hoặc p99.
- Thời gian phát hiện sự cố.
- Thời gian khôi phục dịch vụ.
- Mức mất dữ liệu tối đa có thể chấp nhận.
- Thời gian tối đa để đồng bộ hoặc đối soát trạng thái sau phục hồi.

Không nên chọn ngưỡng chỉ vì công nghệ có thể đạt được. Ngưỡng phải xuất phát từ tác động đến người dùng, yêu cầu kinh doanh, cam kết dịch vụ và chi phí vận hành.

### Phân loại mức quan trọng của dịch vụ

Một cách đơn giản là nhóm hành trình theo mức hậu quả:

| Mức | Đặc điểm | Ví dụ định hướng |
|---|---|---|
| Tới hạn | Gián đoạn gây hậu quả nghiêm trọng hoặc chặn hoạt động thiết yếu | Xác thực giao dịch, ghi nhận thanh toán, truy cập dữ liệu cốt lõi |
| Cao | Gián đoạn ảnh hưởng đáng kể đến hoạt động hoặc trải nghiệm | Tạo đơn hàng, quản lý thành viên, cập nhật trạng thái công việc |
| Trung bình | Có thể trì hoãn hoặc dùng quy trình thay thế trong một khoảng thời gian | Báo cáo, đồng bộ tìm kiếm, gửi thông báo không khẩn cấp |
| Thấp | Có thể tạm ngừng mà ít ảnh hưởng đến hành trình cốt lõi | Phân tích phụ trợ hoặc tính năng tiện ích |

Đây là cách phân loại minh họa. Hãy xác định theo bối cảnh sản phẩm, hợp đồng và mức chấp nhận rủi ro. Một chức năng phụ trợ có thể trở thành quan trọng nếu nó là kênh duy nhất để người dùng nhận cảnh báo hoặc hoàn thành nghĩa vụ.

## 3. Xác định loại bằng chứng cần thu thập

### Bằng chứng về chịu lỗi

Bằng chứng chịu lỗi cho biết hệ thống phản ứng thế nào khi một thành phần không còn hoạt động bình thường. Có thể cần xác minh:

- Request được chuyển sang instance hoặc node dự phòng.
- Thành phần lỗi được cô lập và không làm cạn tài nguyên của các thành phần khác.
- Retry có giới hạn, có backoff và không tạo tải dây chuyền.
- Circuit breaker hoặc cơ chế tương đương ngăn request tiếp tục gọi một dịch vụ đang lỗi.
- Chức năng không thiết yếu được giảm hoặc tạm dừng có kiểm soát.
- Dữ liệu và giao dịch cốt lõi không bị mất hoặc xử lý trùng.
- Hệ thống phát tín hiệu để vận hành nhận biết sự suy giảm.

Kết quả nên bao gồm hành vi quan sát được, thời gian chuyển đổi, số request bị ảnh hưởng và trạng thái dữ liệu sau sự kiện.

### Bằng chứng về phục hồi

Bằng chứng phục hồi phải cho thấy hệ thống có thể trở lại hoạt động và giữ đúng dữ liệu. Các câu hỏi cần trả lời:

- Có thể khởi động lại hoặc thay thế thành phần bị lỗi không?
- Có thể khôi phục dữ liệu từ backup và log không?
- Các giao dịch hoặc thông điệp chưa hoàn tất được xử lý ra sao?
- Có phát hiện và sửa được dữ liệu lệch giữa các hệ thống không?
- Hành trình có thể tiếp tục mà không yêu cầu người dùng tạo lại giao dịch?
- Thời gian phục hồi có nằm trong mục tiêu đã thống nhất không?

Bài kiểm thử phục hồi cần xác minh dữ liệu sau phục hồi bằng các quy tắc nghiệp vụ, không chỉ kiểm tra tiến trình hoặc máy chủ đã chạy lại.

### Bằng chứng về độ sẵn sàng

Bằng chứng độ sẵn sàng cần thể hiện dịch vụ có thể thực hiện công việc trong khoảng thời gian đo. Có thể dùng:

- Synthetic monitoring thực hiện hành trình đại diện.
- Tỷ lệ request thành công từ log hoặc metric.
- Tỷ lệ hoàn thành giao dịch hoặc tác vụ.
- Thời gian phản hồi và tỷ lệ timeout.
- Tín hiệu từ nhiều vùng hoặc mạng khác nhau khi phù hợp.
- Báo cáo sự cố và thời gian gián đoạn có ảnh hưởng đến người dùng.

Health check của tiến trình chỉ chứng minh một mức rất hẹp. Một endpoint kiểm tra sức khỏe trả về thành công không nhất thiết chứng minh người dùng đăng nhập, đọc dữ liệu hoặc thanh toán được.

### Bằng chứng vận hành

Khả năng chịu lỗi và phục hồi phụ thuộc vào việc nhóm vận hành có thể phát hiện, chẩn đoán và hành động đúng. Bằng chứng vận hành có thể gồm:

- Cảnh báo được kích hoạt khi SLI vượt ngưỡng.
- Dashboard thể hiện tình trạng hành trình và phụ thuộc.
- Log và trace nối được các bước của giao dịch.
- Runbook có bước xử lý và điều kiện leo thang rõ.
- Người trực có thể thực hiện failover, rollback hoặc restore theo quyền được cấp.
- Diễn tập xác nhận các nhóm biết cách phối hợp.

Một hệ thống có cơ chế dự phòng nhưng không ai nhận biết khi dự phòng đã được sử dụng có thể tiếp tục chạy trong trạng thái dễ tổn thương.

## 4. Chọn tình huống lỗi đại diện

### Lập danh sách theo thành phần và ranh giới

Không nên chỉ kiểm thử trường hợp máy chủ dừng. Sự cố có thể xuất phát từ hạ tầng, mạng, dữ liệu, cấu hình, phụ thuộc hoặc quá tải.

| Nhóm lỗi | Ví dụ tình huống | Thuộc tính cần xác thực |
|---|---|---|
| Tiến trình hoặc instance | Ứng dụng hoặc worker bị dừng đột ngột | Chịu lỗi, khởi động lại, xử lý công việc dở dang |
| Hạ tầng hoặc vùng | Node, zone hoặc region không khả dụng | Failover, phân phối lưu lượng, phục hồi vùng |
| Mạng | Mất kết nối, packet loss, độ trễ cao, DNS lỗi | Timeout, retry, cô lập và kết nối lại |
| Database | Primary lỗi, replica trễ, connection pool cạn | Failover, tính nhất quán, khôi phục dữ liệu |
| Cache | Node cache lỗi, eviction tăng hoặc dữ liệu cũ | Fallback, invalidation và giới hạn tải |
| Queue hoặc broker | Broker ngừng, backlog tăng, consumer dừng | Lưu giữ, giao lại, retry và phát lại |
| Dịch vụ bên ngoài | Nhà cung cấp xác thực, thanh toán hoặc thông báo lỗi | Degraded mode, đối soát và retry |
| Cấu hình hoặc phát hành | Secret sai, feature flag sai, phiên bản mới lỗi | Rollback, khôi phục cấu hình và phát hiện |
| Dữ liệu | Bản ghi hỏng, xóa nhầm hoặc migration sai | Backup, restore, kiểm tra toàn vẹn |
| Năng lực xử lý | Lưu lượng tăng đột biến hoặc tài nguyên cạn | Điều tiết, mở rộng và duy trì mục tiêu dịch vụ |

### Chọn lỗi theo khả năng và hậu quả

Ưu tiên các tình huống có một hoặc nhiều đặc điểm:

- Ảnh hưởng hành trình có giá trị cao.
- Có khả năng xảy ra hoặc đã xuất hiện trong lịch sử.
- Có thể gây mất dữ liệu hoặc trạng thái không thể đối soát.
- Khó phát hiện bằng giám sát hiện tại.
- Có nhiều phụ thuộc hoặc điểm lỗi đơn.
- Có thể làm sự cố lan rộng qua retry, backlog hoặc cạn tài nguyên.
- Chưa từng được diễn tập phục hồi.

Đừng bỏ qua sự kiện ít xảy ra nhưng có hậu quả nghiêm trọng. Một lỗi vùng hiếm gặp có thể cần kiểm tra kế hoạch DR ngay cả khi kiểm thử thường ngày chưa từng tái hiện.

### Phân biệt lỗi đơn lẻ và lỗi kết hợp

Kiểm thử một thành phần lỗi giúp hiểu hành vi cơ bản. Sự cố thực tế có thể kết hợp nhiều điều kiện: database failover làm tăng độ trễ, worker retry làm backlog tăng, sau đó cache miss khiến tải database tăng thêm.

Sau khi kiểm tra các tình huống đơn lẻ, hãy chọn một số tổ hợp có cơ sở từ kiến trúc và lịch sử sự cố. Không cần tạo mọi tổ hợp có thể; hãy tập trung vào chuỗi lỗi có khả năng khuếch đại tác động hoặc làm mất phương án dự phòng.

## 5. Chọn phương pháp kiểm thử phù hợp

### Kiểm thử failover

Failover xác minh hệ thống chuyển sang thành phần dự phòng khi thành phần chính không còn đáp ứng. Có thể áp dụng cho instance ứng dụng, database, broker, vùng triển khai hoặc kết nối mạng.

Bằng chứng cần ghi nhận:

- Điều kiện kích hoạt failover.
- Thời gian phát hiện và thời gian chuyển đổi.
- Số request thất bại hoặc bị trì hoãn.
- Trạng thái phiên, kết nối và giao dịch đang xử lý.
- Dữ liệu nào được bảo toàn hoặc cần đồng bộ.
- Hành vi khi thành phần chính trở lại.
- Cách tránh split-brain hoặc hai phía cùng nhận quyền ghi.

Failover tự động không phải lúc nào cũng là lựa chọn đúng. Với một số hệ thống, chuyển đổi thủ công có kiểm soát giúp tránh ghi dữ liệu vào node không an toàn. Hãy kiểm tra đúng thiết kế và tiêu chí vận hành.

### Kiểm thử phục hồi từ backup

Backup chỉ có giá trị khi có thể khôi phục và dữ liệu khôi phục đáp ứng yêu cầu. Một bài kiểm thử restore nên xác minh:

1. Bản backup được tạo đúng lịch và có thể truy cập.
2. Bản backup có tính toàn vẹn và nguồn gốc rõ.
3. Quy trình restore có thể thực hiện trong môi trường cô lập.
4. Log giao dịch hoặc dữ liệu gia tăng được áp dụng đúng nếu cần.
5. Các ràng buộc, quan hệ và số liệu nghiệp vụ được xác minh sau restore.
6. Thời gian khôi phục được đo từ lúc bắt đầu đến khi hệ thống có thể phục vụ hành trình mục tiêu.
7. Quyền truy cập, secret và cấu hình sau restore được thiết lập an toàn.

Không chỉ xác minh file backup tồn tại hoặc công cụ báo lệnh thành công. Cần khôi phục thử và đọc/đối chiếu dữ liệu thực tế.

### Kiểm thử khả năng khởi động lại và tiếp tục công việc

Dừng hoặc khởi động lại một tiến trình trong môi trường kiểm thử để xác minh:

- Request đang xử lý có trạng thái rõ ràng.
- Transaction được commit hoặc rollback theo quy tắc.
- Thông điệp chưa ack được giao lại.
- Job có checkpoint hoặc có thể chạy lại an toàn.
- Tài nguyên và kết nối cũ được giải phóng.
- Hệ thống không phát sinh tác dụng phụ trùng.
- Worker có thể bắt kịp backlog sau khi phục hồi.

Chọn thời điểm dừng có chủ đích, ví dụ trước khi commit, sau commit nhưng trước ack hoặc sau khi gọi nhà cung cấp nhưng trước khi ghi nhận kết quả. Những điểm này thường làm lộ lỗi phục hồi quan trọng.

### Kiểm thử chịu tải và suy giảm

Tải cao có thể làm hệ thống chậm hoặc mất khả năng phục vụ dù không có thành phần nào dừng hoàn toàn. Hãy kiểm tra:

- Lưu lượng bình thường, cao điểm và đột biến.
- Hành vi khi một dịch vụ phụ thuộc chậm.
- Backpressure và giới hạn hàng đợi.
- Cơ chế từ chối sớm hoặc rate limit.
- Tự động mở rộng và thời gian để năng lực mới sẵn sàng.
- Tác động của retry đến tải tổng thể.
- Khả năng duy trì chức năng cốt lõi khi chức năng phụ trợ bị giảm.

Kết quả cần liên hệ với mục tiêu người dùng. Thông lượng cao không có ý nghĩa nếu tỷ lệ giao dịch sai hoặc timeout tăng vượt mức chấp nhận.

### Chaos engineering và fault injection

Chaos engineering là cách chủ động tạo điều kiện lỗi có kiểm soát để kiểm tra giả thuyết về khả năng chịu lỗi của hệ thống. Fault injection có thể mô phỏng mất kết nối, tăng độ trễ, dừng tiến trình, lỗi DNS hoặc giới hạn tài nguyên.

Một thử nghiệm nên có:

- Giả thuyết rõ ràng về hành vi mong đợi.
- Phạm vi tác động nhỏ và được kiểm soát.
- Baseline trước khi tạo lỗi.
- Tín hiệu quan sát và tiêu chí dừng.
- Người chịu trách nhiệm và kênh liên lạc.
- Quy trình khôi phục và xác minh sau thử nghiệm.

Không bắt đầu bằng việc gây lỗi diện rộng. Thử nghiệm cần chạy trong môi trường phù hợp, có giới hạn blast radius và được điều phối theo quy trình vận hành của tổ chức.

### Diễn tập khôi phục thảm họa

Diễn tập DR (disaster recovery) kiểm tra khả năng phục hồi sau sự kiện có phạm vi lớn như mất vùng, mất trung tâm dữ liệu, hỏng dữ liệu hoặc gián đoạn kéo dài của nhà cung cấp.

Diễn tập có thể ở mức tabletop (thảo luận quy trình), mô phỏng kỹ thuật, khôi phục trong môi trường riêng hoặc chuyển vùng có kiểm soát. Cấp độ càng gần sự cố thật càng cần chuẩn bị, quyền hạn, phương án quay lại và tiêu chí dừng rõ ràng.

## 6. Dùng SLI, SLO và SLA để xác định bằng chứng độ sẵn sàng

### Service Level Indicator (SLI)

SLI là chỉ số đo một khía cạnh cụ thể của dịch vụ. Ví dụ:

- Tỷ lệ request hợp lệ được xử lý thành công.
- Tỷ lệ hành trình đăng nhập hoàn tất.
- Độ trễ của thao tác đọc hoặc ghi.
- Tỷ lệ tác vụ bất đồng bộ hoàn tất trong thời hạn.
- Tỷ lệ giao dịch được xác nhận và đối soát thành công.

SLI phải có định nghĩa rõ về sự kiện được tính, tập request đủ điều kiện, cửa sổ thời gian và nguồn dữ liệu. Nếu mỗi dashboard tính “thành công” theo cách khác nhau, nhóm không thể dùng số liệu để ra quyết định nhất quán.

Ví dụ, SLI cho request được tính bằng số request hợp lệ thành công chia cho tổng số request hợp lệ. Cần xác định thế nào là request hợp lệ và thành công. Không nên loại bỏ request lỗi hoặc timeout khỏi mẫu số chỉ vì chúng làm chỉ số xấu đi.

### Service Level Objective (SLO)

SLO là mục tiêu nội bộ cho một SLI trong khoảng thời gian xác định. Ví dụ, nhóm có thể đặt mục tiêu 99,9% request hợp lệ của một hành trình đạt điều kiện thành công trong cửa sổ 30 ngày.

SLO cần dựa trên nhu cầu và chi phí. Mục tiêu cao hơn có thể yêu cầu dự phòng, giám sát và vận hành tốn kém hơn. Không phải mọi hành trình đều cần cùng một SLO.

### Service Level Agreement (SLA)

SLA là cam kết dịch vụ được thống nhất với khách hàng hoặc bên liên quan, thường có điều kiện, cách đo và hậu quả khi không đáp ứng. SLA có thể khác SLO nội bộ. Nhóm thường đặt SLO có khoảng đệm để có thời gian xử lý trước khi vi phạm SLA.

Không dùng thuật ngữ SLI, SLO và SLA thay thế cho nhau. Khi lựa chọn bằng chứng, hãy chỉ rõ chỉ số nào là phép đo, chỉ số nào là mục tiêu nội bộ và chỉ số nào là cam kết bên ngoài.

### Tính error budget

Error budget là phần không đạt mục tiêu được phép trong một cửa sổ SLO. Nếu SLO là 99,9% trong 30 ngày và đo theo thời gian, ngân sách gián đoạn tương ứng là 0,1% của cửa sổ đó.

Ví dụ minh họa với cửa sổ 30 ngày:

- Tổng thời gian: 30 × 24 × 60 = 43.200 phút.
- Mức không sẵn sàng tương ứng 0,1%: 43,2 phút.

Đây chỉ là phép quy đổi khi SLI đo theo thời gian. Nếu SLI đo theo request, error budget được tính theo tỷ lệ request lỗi, không thể chuyển trực tiếp thành số phút gián đoạn nếu chưa có giả định bổ sung.

Error budget giúp quyết định tốc độ phát hành và mức đầu tư ổn định. Khi ngân sách gần cạn, nhóm có thể giảm thay đổi rủi ro, ưu tiên sửa lỗi độ tin cậy và tăng kiểm chứng.

## 7. Xác định RTO và RPO cho kế hoạch phục hồi

### Recovery Time Objective (RTO)

RTO là khoảng thời gian mục tiêu để khôi phục dịch vụ hoặc một quy trình sau gián đoạn. RTO cần được đo theo hành trình và mức chức năng có thể phục vụ, không chỉ theo thời điểm tiến trình khởi động.

Ví dụ, database có thể đã chạy nhưng người dùng vẫn không thể hoàn tất giao dịch vì cache, queue hoặc xác thực chưa phục hồi. Khi đó dịch vụ chưa thực sự đạt trạng thái phục vụ như RTO yêu cầu.

### Recovery Point Objective (RPO)

RPO là mức mất dữ liệu tối đa có thể chấp nhận, thường được diễn đạt thành khoảng thời gian dữ liệu có thể bị mất khi khôi phục. RPO bằng 0 có nghĩa mục tiêu không mất dữ liệu trong phạm vi được xác định; điều này đòi hỏi thiết kế và chi phí phù hợp, không nên giả định có thể đạt được trong mọi kiến trúc.

Ví dụ, RPO 15 phút nghĩa là sau sự cố, tổ chức chấp nhận khả năng mất tối đa lượng dữ liệu được tạo trong khoảng 15 phút trước thời điểm gián đoạn, theo cách đo đã thống nhất.

### Phân biệt RTO, RPO và thời gian phát hiện

Các mốc này thường bị nhầm:

- **Thời gian phát hiện (MTTD):** từ lúc sự cố bắt đầu đến khi được phát hiện.
- **Thời gian khôi phục (recovery time):** thời gian thực tế để khôi phục chức năng.
- **RTO:** mục tiêu tối đa cho thời gian khôi phục theo định nghĩa đã thống nhất.
- **RPO:** giới hạn mất dữ liệu có thể chấp nhận.

Nếu quy trình chỉ bắt đầu khôi phục sau khi có người phát hiện, thời gian người dùng bị ảnh hưởng có thể gồm cả MTTD và thời gian khôi phục. Hãy xác định cách tổ chức đo tổng thời gian gián đoạn để tránh báo cáo RTO đạt trong khi người dùng vẫn bị ảnh hưởng lâu hơn.

### Đặt mục tiêu theo loại dữ liệu và quy trình

Một tổ chức có thể có nhiều RTO/RPO:

| Dịch vụ hoặc dữ liệu | RTO định hướng | RPO định hướng | Lý do cần xem xét |
|---|---|---|---|
| Ghi nhận giao dịch cốt lõi | Ngắn | Rất thấp | Tránh gián đoạn và mất trạng thái tài chính |
| Đăng nhập và phân quyền | Ngắn | Thấp | Người dùng cần truy cập an toàn |
| Báo cáo phân tích | Dài hơn | Có thể cao hơn | Có thể tái tạo từ dữ liệu nguồn |
| Search index | Theo nhu cầu | Có thể tái tạo | Dữ liệu có thể được xây dựng lại |
| Thông báo không khẩn cấp | Có thể xử lý trễ | Phụ thuộc hàng đợi và retention | Có thể gửi sau khi phục hồi |

Các mức trong bảng chỉ là định hướng, không phải giá trị khuyến nghị phổ quát. Chủ sở hữu nghiệp vụ, kỹ thuật và vận hành cần thống nhất mục tiêu theo hậu quả, nghĩa vụ và chi phí.

## 8. Đo lường độ sẵn sàng từ góc nhìn người dùng

### Định nghĩa yêu cầu thành công

Một request có thể trả HTTP 200 nhưng vẫn không đáp ứng công việc. Ví dụ, trang dashboard tải được nhưng dữ liệu trống hoặc sai tenant. Một SLI hướng người dùng cần xác định điều kiện thành công có ý nghĩa.

Có thể đo theo:

- Tỷ lệ người dùng đăng nhập và truy cập được trang cần thiết.
- Tỷ lệ tạo giao dịch hoàn tất với trạng thái đúng.
- Tỷ lệ tác vụ bất đồng bộ hoàn thành trong thời hạn.
- Tỷ lệ truy vấn trả dữ liệu chính xác trong ngưỡng độ trễ.
- Tỷ lệ người dùng hoàn thành một hành trình trọng yếu.

Đừng chỉ đo uptime của máy chủ hoặc số lần health check thành công.

### Kết hợp metric và synthetic monitoring

Metric tổng hợp từ traffic thật phản ánh trải nghiệm thực tế nhưng có thể bị ảnh hưởng bởi phân bố người dùng, thời gian cao điểm hoặc số lượng request thấp. Synthetic monitoring chủ động chạy hành trình mẫu theo lịch để phát hiện vấn đề ngay cả khi ít người dùng hoạt động.

Một chiến lược tốt có thể kết hợp:

- Metric từ request thực để hiểu mức độ ảnh hưởng.
- Synthetic journey để kiểm tra khả năng hoàn thành tác vụ đại diện.
- Dashboard theo dịch vụ, vùng và phụ thuộc.
- Log/trace để chẩn đoán nguyên nhân.
- Báo cáo sự cố để liên hệ metric với tác động thực tế.

Synthetic test cần dùng tài khoản và dữ liệu chuyên dụng, có giới hạn tác dụng phụ và được dọn dẹp. Không thực hiện thanh toán hoặc gửi thông báo thật trong phép đo định kỳ nếu không có sandbox phù hợp.

### Đo độ trễ và phân vị

Trung bình có thể che khuất một nhóm request rất chậm. Hãy xem xét p50, p95 và p99 cùng tỷ lệ timeout. Ví dụ, p95 là thời gian mà 95% request có độ trễ không vượt quá giá trị đó trong tập đo.

Đo riêng các bước quan trọng: xác thực, truy vấn dữ liệu, ghi giao dịch, xử lý queue và hoàn tất hành trình. Độ trễ đầu cuối có thể cao dù từng dịch vụ đều nằm trong ngưỡng riêng vì thời gian cộng dồn và chờ bất đồng bộ.

### Xác định cửa sổ đo và loại trừ

Khi tính độ sẵn sàng, cần xác định:

- Cửa sổ thời gian: ngày, tuần, tháng hoặc chu kỳ hợp đồng.
- Tập request được tính.
- Cách xử lý bảo trì đã thông báo.
- Cách tính lỗi do người dùng gửi dữ liệu không hợp lệ.
- Cách tính lỗi phụ thuộc và lỗi vùng.
- Ngưỡng độ trễ được xem là thành công.
- Cách xử lý khi hệ thống đo lường không hoạt động.

Không nên loại trừ sự cố chỉ vì nguyên nhân nằm ở nhà cung cấp nếu người dùng vẫn không thể dùng dịch vụ. Đối với SLI hướng người dùng, tác động thực tế thường quan trọng hơn ranh giới sở hữu kỹ thuật.

## 9. Kiểm tra suy giảm có kiểm soát và chức năng dự phòng

### Xác định chức năng nào được phép suy giảm

Khi phụ thuộc lỗi, hệ thống có thể cần giảm chức năng để bảo vệ phần cốt lõi. Ví dụ:

- Tạm ẩn báo cáo phân tích nhưng vẫn cho phép ghi giao dịch.
- Lưu yêu cầu thông báo vào queue để gửi sau.
- Hiển thị dữ liệu gần nhất với nhãn thời điểm cập nhật, nếu nghiệp vụ cho phép.
- Giới hạn tốc độ request hoặc từ chối sớm để bảo vệ database.
- Chuyển một số thao tác sang xử lý thủ công có kiểm soát.

Mỗi degraded mode cần nêu rõ chức năng còn hoạt động, chức năng bị hạn chế, dữ liệu có thể cũ đến mức nào và điều kiện quay lại bình thường.

### Kiểm tra fallback có an toàn

Fallback không được làm suy yếu bảo mật hoặc tính đúng đắn. Ví dụ, không dùng cache quyền cũ khi dịch vụ phân quyền ngừng hoạt động nếu điều đó có thể cấp quyền trái phép. Không đánh dấu thanh toán thành công chỉ vì không liên hệ được nhà cung cấp.

Hãy xác minh:

- Fallback chỉ áp dụng cho loại dữ liệu và hành động được phép.
- Người dùng nhận được trạng thái trung thực.
- Hệ thống ghi nhận công việc cần xử lý sau.
- Khi phụ thuộc phục hồi, dữ liệu được đồng bộ và đối soát.
- Fallback không tạo tải hoặc backlog vượt khả năng xử lý.

### Kiểm tra cơ chế bảo vệ khỏi lỗi dây chuyền

Một số cơ chế phổ biến:

- **Timeout:** giới hạn thời gian chờ để giải phóng tài nguyên.
- **Retry có backoff:** thử lại lỗi tạm thời theo giới hạn.
- **Circuit breaker:** tạm ngừng gọi phụ thuộc đang lỗi để tránh làm tình trạng xấu hơn.
- **Bulkhead:** cô lập tài nguyên để một luồng không làm cạn tài nguyên của luồng khác.
- **Rate limiting:** giới hạn lưu lượng theo người dùng hoặc dịch vụ.
- **Backpressure:** điều tiết tốc độ nhận công việc theo năng lực xử lý.
- **Queue buffering:** giữ công việc để xử lý sau khi phụ thuộc phục hồi.

Kiểm thử phải xác minh cả cơ chế và trạng thái nghiệp vụ. Circuit breaker mở có thể giảm lỗi dây chuyền nhưng cũng có thể chặn request hợp lệ quá lâu nếu không tự phục hồi theo chính sách.

## 10. Thiết kế thử nghiệm chịu lỗi an toàn

### Viết giả thuyết và kết quả mong đợi

Một thử nghiệm tốt nêu rõ:

> Khi [thành phần hoặc điều kiện lỗi] xảy ra, chúng tôi kỳ vọng [hành vi chịu lỗi hoặc phục hồi] để [hành trình và dữ liệu quan trọng] vẫn đáp ứng [tiêu chí]. Chúng tôi sẽ quan sát [SLI, log, trace và trạng thái dữ liệu] trong [khoảng thời gian].

Ví dụ: “Khi một instance ứng dụng bị dừng, lưu lượng mới được xử lý bởi instance còn lại trong vòng mục tiêu đã thống nhất; không có giao dịch đã commit bị mất hoặc ghi nhận trùng.”

Giả thuyết giúp nhóm xác định phép đo và giới hạn. Nếu không có tiêu chí quan sát được, thử nghiệm dễ trở thành thao tác gây lỗi mà không tạo bằng chứng.

### Kiểm soát phạm vi và blast radius

Trước khi tiêm lỗi, xác định:

- Môi trường và tài nguyên bị ảnh hưởng.
- Số lượng người dùng hoặc giao dịch có thể chịu tác động.
- Phụ thuộc dùng chung có thể bị ảnh hưởng.
- Thời gian thử nghiệm và điều kiện dừng.
- Người phê duyệt và người điều phối.
- Cách khôi phục nếu thử nghiệm không diễn ra như dự kiến.

Bắt đầu với môi trường cô lập hoặc một instance không phục vụ traffic thật. Chỉ mở rộng phạm vi khi đã có bằng chứng và quy trình phù hợp. Thử nghiệm trên production cần được quản lý theo chính sách vận hành, phạm vi và quyền được cấp.

### Xác định điều kiện dừng

Dừng thử nghiệm nếu xuất hiện dấu hiệu vượt giới hạn an toàn, ví dụ:

- Tỷ lệ lỗi hoặc độ trễ vượt ngưỡng dừng.
- Mất dữ liệu hoặc trạng thái không thể đối soát.
- Tác động lan sang tenant hoặc dịch vụ ngoài phạm vi.
- Không thể khôi phục thành phần theo quy trình.
- Cảnh báo hoặc kênh liên lạc cần thiết không hoạt động.
- Phạm vi thực tế khác phạm vi đã phê duyệt.

Điều kiện dừng phải được thống nhất trước khi chạy. Không tiếp tục chỉ để hoàn thành kịch bản khi hệ thống đang có dấu hiệu gây hại ngoài dự kiến.

### Ghi lại baseline, sự kiện và kết quả

Thu thập baseline trước thử nghiệm: tỷ lệ thành công, độ trễ, lưu lượng, backlog, tài nguyên, trạng thái dữ liệu và cảnh báo. Trong khi thử nghiệm, ghi thời điểm tạo lỗi, thời điểm phát hiện, thời điểm chuyển đổi và thời điểm phục hồi.

Sau thử nghiệm, so sánh với baseline và kiểm tra trạng thái nghiệp vụ. Bằng chứng cần có đủ ngữ cảnh để người khác tái hiện hoặc đánh giá kết luận.

## 11. Ví dụ: lựa chọn bằng chứng cho dịch vụ thuê bao SaaS

Giả sử một sản phẩm SaaS cung cấp đăng nhập, quản lý không gian làm việc, thanh toán thuê bao và thông báo. Các thành phần gồm ứng dụng đa instance, database có dự phòng, cache, queue, worker và nhà cung cấp thanh toán.

### Xác định hành trình và mức quan trọng

| Hành trình | Mức quan trọng | Điều cần bảo vệ |
|---|---|---|
| Đăng nhập và truy cập workspace | Cao | Người dùng hợp lệ có thể truy cập đúng tenant |
| Ghi nhận thanh toán và kích hoạt thuê bao | Tới hạn | Không mất hoặc ghi trùng giao dịch |
| Gửi email thông báo | Trung bình | Có thể gửi trễ nhưng không gửi sai hoặc trùng ngoài quy tắc |
| Báo cáo sử dụng | Thấp đến trung bình | Có thể chậm và tái tạo từ dữ liệu nguồn |

### Ma trận tình huống và bằng chứng

| Tình huống | Phương pháp | Bằng chứng cần thu thập |
|---|---|---|
| Một instance ứng dụng dừng | Failover có kiểm soát | Request thành công ở instance còn lại; số request bị ảnh hưởng; session và giao dịch |
| Database primary chuyển đổi | Diễn tập failover | Thời gian chuyển đổi; transaction; dữ liệu đã commit; lỗi kết nối |
| Cache không khả dụng | Fault injection trong staging | Fallback, tải database, độ trễ và tính đúng của dữ liệu |
| Queue broker gián đoạn | Dừng broker hoặc chặn kết nối trong môi trường thử nghiệm | Outbox/backlog, khả năng publish lại và tác dụng phụ trùng |
| Worker dừng giữa xử lý | Restart tại thời điểm xác định | Message được giao lại; trạng thái và idempotency |
| Nhà cung cấp thanh toán timeout | Sandbox hoặc test double có kiểm soát | Trạng thái không xác định, đối soát và không tạo giao dịch mới ngoài ý muốn |
| Khôi phục database | Restore backup vào môi trường riêng | RPO thực tế, RTO thực tế, tính toàn vẹn và hành trình đọc/ghi |
| Mất một vùng triển khai | Diễn tập DR theo phạm vi được phê duyệt | Thời gian chuyển vùng, dữ liệu, truy cập và điều kiện failback |

### Tiêu chí đánh giá mẫu

Trước khi chạy, chủ sở hữu dịch vụ có thể thống nhất các tiêu chí như:

- Hành trình đăng nhập vẫn hoạt động trong giới hạn gián đoạn đã định.
- Giao dịch đã commit không bị mất sau failover hoặc restore.
- Một event ID không tạo nhiều lần kích hoạt thuê bao.
- Email có thể gửi trễ trong thời hạn cho phép và không gửi nhầm người nhận.
- Backup khôi phục được và dữ liệu vượt qua kiểm tra toàn vẹn.
- RTO/RPO đo được đáp ứng mục tiêu đã phê duyệt.
- Cảnh báo phát hiện sự cố và runbook giúp nhóm xác định bước xử lý.

Các tiêu chí phải được thay bằng mục tiêu thực tế của tổ chức. Không dùng ví dụ này làm SLA hoặc cam kết mặc định.

## 12. Đánh giá kết quả và xử lý khoảng trống bằng chứng

### Phân biệt đạt, không đạt và chưa đủ bằng chứng

Kết quả kiểm thử nên được phân loại:

- **Đạt:** tình huống đã kiểm tra và bằng chứng đáp ứng tiêu chí đã định.
- **Không đạt:** hệ thống vi phạm tiêu chí hoặc tạo hậu quả không chấp nhận được.
- **Chưa đủ bằng chứng:** thử nghiệm không bao phủ điều kiện cần, dữ liệu không đáng tin cậy hoặc tín hiệu không đủ để kết luận.
- **Không áp dụng:** mục tiêu không liên quan đến thành phần hoặc hành trình đã xác định, kèm lý do.

Không gộp “chưa đủ bằng chứng” vào “đạt”. Nếu không thể kiểm tra mất vùng vì môi trường không hỗ trợ, hãy ghi rõ giới hạn và xác định cách xác minh khác.

### Đánh giá rủi ro còn lại

Sau thử nghiệm, xem xét:

- Tình huống nào đã được xác minh?
- Tình huống nào chưa được thử hoặc chỉ được mô phỏng?
- Mức tác động và khả năng xảy ra có thay đổi không?
- Biện pháp chịu lỗi hoặc phục hồi có hoạt động như thiết kế không?
- Có tác dụng phụ hoặc rủi ro mới được phát hiện không?
- Ai có thẩm quyền chấp nhận phần rủi ro còn lại?
- Khi nào cần thử lại?

Một bài failover thành công ở một vùng không tự chứng minh kế hoạch DR cho toàn bộ hệ thống. Hãy giới hạn kết luận theo đúng phạm vi thử nghiệm.

### Chuyển phát hiện thành hành động

Mỗi phát hiện cần có:

- Mô tả tình huống và hành trình bị ảnh hưởng.
- Tiêu chí đã vi phạm hoặc bằng chứng còn thiếu.
- Tác động đến người dùng, dữ liệu và mục tiêu dịch vụ.
- Chủ sở hữu xử lý.
- Biện pháp và thời hạn.
- Cách xác minh sau khi sửa.
- Quyết định về phát hành hoặc chấp nhận rủi ro.

Ưu tiên sửa nguyên nhân gốc. Ví dụ, backlog tăng sau khi worker restart có thể do concurrency, retry hoặc partition assignment; chỉ tăng số worker mà không hiểu nguyên nhân có thể làm lỗi cạnh tranh nặng hơn.

## 13. Những sai lầm thường gặp

- **Chỉ kiểm tra uptime của máy chủ:** bỏ qua việc người dùng có hoàn thành được hành trình hay không.
- **Coi health check là bằng chứng đầy đủ:** endpoint khỏe không chứng minh database, quyền hoặc giao dịch hoạt động đúng.
- **Chỉ dừng một tiến trình:** chưa bao phủ lỗi vùng, mạng, dữ liệu hoặc phụ thuộc.
- **Kiểm tra failover mà không kiểm tra trạng thái dữ liệu:** dịch vụ có thể hoạt động lại nhưng mất hoặc ghi trùng giao dịch.
- **Giả định backup dùng được:** chỉ tạo backup mà không restore thử không chứng minh khả năng phục hồi.
- **Nhầm RTO với thời gian khởi động máy:** người dùng có thể vẫn không hoàn thành công việc sau khi tiến trình chạy lại.
- **Đặt RPO/RTO không dựa trên nghiệp vụ:** mục tiêu có thể quá lỏng hoặc tốn kém không cần thiết.
- **Chỉ đo trung bình:** che giấu nhóm request có độ trễ rất cao.
- **Không phân biệt SLI, SLO và SLA:** dẫn đến cách đo và cách báo cáo thiếu nhất quán.
- **Tiêm lỗi không có điều kiện dừng:** có thể làm thử nghiệm lan rộng ngoài phạm vi.
- **Không kiểm tra degraded mode:** fallback có thể trả dữ liệu cũ, cấp quyền sai hoặc tạo giao dịch không chắc chắn.
- **Bỏ qua tác dụng phụ bất đồng bộ:** queue và worker có thể tiếp tục xử lý sau khi giao diện đã báo lỗi.
- **Không diễn tập runbook:** quy trình tồn tại trên tài liệu nhưng nhóm không thể thực hiện khi cần.
- **Kết luận vượt quá phạm vi thử nghiệm:** một kịch bản thành công không chứng minh mọi dạng sự cố đã được kiểm soát.

## 14. Đầu ra cần có trước khi chốt bằng chứng chịu lỗi và phục hồi

Một kế hoạch kiểm thử đủ dùng nên có:

1. **Danh sách hành trình quan trọng:** tác nhân, kết quả, mức tác động và chức năng cần duy trì.
2. **Mục tiêu dịch vụ:** SLI, SLO, SLA liên quan, cửa sổ đo và tiêu chí thành công.
3. **Mục tiêu phục hồi:** RTO, RPO, phạm vi dữ liệu và cách đo thời gian.
4. **Danh mục tình huống lỗi:** thành phần, nguyên nhân, tổ hợp lỗi và mức ưu tiên.
5. **Phương pháp kiểm thử:** failover, restore, restart, load, fault injection, chaos hoặc diễn tập DR.
6. **Giả thuyết và tiêu chí đạt:** hành vi dự kiến, tín hiệu quan sát và ngưỡng.
7. **Kiểm soát an toàn:** phạm vi, blast radius, người phê duyệt, điều kiện dừng và cách khôi phục.
8. **Kế hoạch dữ liệu:** nguồn có thẩm quyền, backup, dữ liệu kiểm thử và kiểm tra toàn vẹn.
9. **Kế hoạch quan sát:** metric, log, trace, dashboard, cảnh báo và runbook.
10. **Báo cáo kết quả:** thời gian phát hiện, chuyển đổi, phục hồi, dữ liệu mất hoặc lệch và tác động người dùng.
11. **Rủi ro còn lại:** giới hạn môi trường, tình huống chưa kiểm tra và người chấp nhận.
12. **Lịch kiểm chứng lại:** khi thay đổi kiến trúc, phụ thuộc, dữ liệu, mục tiêu dịch vụ hoặc sau sự cố.

Trước khi chốt, hãy rà soát:

- Bằng chứng có gắn với hành trình và kết quả người dùng cần bảo vệ không?
- Tình huống lỗi có đại diện cho các điểm lỗi quan trọng và phụ thuộc không?
- Đã kiểm tra cả chịu lỗi tức thời và phục hồi sau gián đoạn chưa?
- Backup đã được restore và dữ liệu đã được kiểm tra chưa?
- RTO/RPO có định nghĩa, phạm vi và phép đo rõ không?
- Độ sẵn sàng có được đo từ hành trình hoặc request có ý nghĩa không?
- SLI, SLO và SLA có được phân biệt và thống nhất không?
- Thử nghiệm có baseline, giới hạn tác động và điều kiện dừng không?
- Cảnh báo, runbook và trách nhiệm vận hành đã được xác minh chưa?
- Kết luận có nêu đúng phạm vi và những gì chưa được chứng minh không?

Lựa chọn đúng bằng chứng giúp nhóm biết hệ thống sẽ ứng xử thế nào khi thành phần lỗi, mất bao lâu để phục hồi và người dùng có tiếp tục hoàn thành công việc được hay không. Hãy xem lại kế hoạch khi kiến trúc, phụ thuộc, tải, dữ liệu hoặc mục tiêu dịch vụ thay đổi, đồng thời đưa bài học từ sự cố và diễn tập trở lại chiến lược xác thực.

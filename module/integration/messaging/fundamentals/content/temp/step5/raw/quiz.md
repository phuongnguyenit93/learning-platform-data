Câu 1. Điểm khác biệt quan trọng của messaging bất đồng bộ với gọi API đồng bộ là gì?
A. Producer luôn chờ consumer xử lý xong nghiệp vụ
B. Consumer luôn trả kết quả qua kết nối HTTP ban đầu
C. Producer có thể tiếp tục khi đã bàn giao message
D. Consumer phải dùng cùng runtime với producer đang gửi
Đáp án đúng: C

Câu 2. Vai trò cơ bản của producer trong kiến trúc message broker là gì?
A. Nhận thông điệp từ hàng đợi để thực thi công việc
B. Tạo và gửi thông điệp tới kênh được cấu hình
C. Giữ trạng thái transaction cho toàn bộ consumer
D. Phân phối thông điệp từ broker đến các subscription
Đáp án đúng: B

Câu 3. Một message broker thường đảm nhận nhiệm vụ nào trong tích hợp?
A. Triển khai toàn bộ logic nghiệp vụ của producer
B. Đảm bảo dữ liệu ở mọi dịch vụ luôn nhất quán tức thì
C. Tạo lớp API đồng bộ cho từng consumer riêng lẻ
D. Nhận, lưu và định tuyến message theo cấu hình
Đáp án đúng: D

Câu 4. Consumer trong một hệ thống messaging thường thực hiện thao tác nào?
A. Định nghĩa đường mạng cho tất cả producer đang gửi
B. Quyết định mọi thay đổi schema của các hệ thống
C. Nhận thông điệp và xử lý theo hợp đồng nghiệp vụ
D. Mở transaction DB chung cho mọi dịch vụ tích hợp
Đáp án đúng: C

Câu 5. Một command message khác event message chủ yếu ở điểm nào?
A. Command yêu cầu hành động, event báo điều đã xảy ra
B. Command báo trạng thái, event yêu cầu thực thi hành động
C. Command dành cho broker, event chỉ dùng với HTTP API
D. Command luôn phát cho nhiều bên, event chỉ cho một bên
Đáp án đúng: A

Câu 6. Mô hình competing consumers phù hợp với tình huống nào?
A. Mọi worker cùng xử lý từng message cho các mục đích khác
B. Mỗi message phải được xử lý nối tiếp bởi toàn bộ worker
C. Mỗi worker phải duy trì một bản sao đầy đủ của topic
D. Nhiều worker chia nhau xử lý tác vụ trong hàng đợi
Đáp án đúng: D

Câu 7. Khi nhiều ứng dụng độc lập cần nhận một sự kiện, mô hình nào phù hợp?
A. Một queue chung để các ứng dụng cạnh tranh đọc
B. Một consumer nhận rồi ghi đè message sau khi đọc
C. Một RPC đồng bộ buộc mọi bên hoàn tất trước khi trả
D. Publish-subscribe với các subscription nhận bản riêng
Đáp án đúng: D

Câu 8. Khái niệm topic trong messaging thường thể hiện điều gì?
A. Trường đánh dấu message đã commit vào database
B. Kênh phân loại thông điệp cho các bên đăng ký
C. Cơ chế xác thực client khi mở kết nối với broker
D. Một phiên bản riêng của schema cho từng producer
Đáp án đúng: B

Câu 9. Metadata trong message envelope hữu ích cho mục đích nào?
A. Thay thế toàn bộ dữ liệu nghiệp vụ trong payload
B. Mang message ID, loại nội dung và thông tin theo dấu
C. Bắt consumer sử dụng chung cấu trúc bảng nội bộ
D. Buộc broker tự xác minh nghiệp vụ của mọi trường
Đáp án đúng: B

Câu 10. Với message xử lý một đơn hàng, chọn message key ổn định theo orderId thường giúp gì?
A. Phân phối mọi sự kiện của đơn hàng đến các partition khác
B. Bắt mọi consumer hoàn tất giao dịch cùng thời điểm
C. Đưa message cùng đơn vào tuyến hoặc partition nhất quán
D. Đảm bảo mọi đơn hàng đều nhận số lần xử lý bằng nhau
Đáp án đúng: C

Câu 11. Ở broker dùng partition, thứ tự message thường được bảo đảm trong phạm vi nào?
A. Thứ tự tổng thể giữa mọi partition của cùng topic
B. Thứ tự hoàn thành xử lý của các worker song song
C. Thứ tự giao dịch giữa mọi service cùng sử dụng broker
D. Thứ tự ghi message trong từng partition riêng lẻ
Đáp án đúng: D

Câu 12. Vì sao tăng số consumer có thể không tăng throughput khi số partition đã cố định?
A. Broker buộc mọi consumer xử lý một message duy nhất
B. Số partition giới hạn số consumer chủ động trong nhóm
C. Schema registry chỉ cho phép một consumer trong hệ thống
D. Mọi partition luôn phải do cùng một consumer xử lý
Đáp án đúng: B

Câu 13. Trong broker kiểu log, consumer offset thường biểu thị điều gì?
A. Định danh khóa bí mật để xác thực với broker
B. Số lượng bản sao dữ liệu được ghi ra nhiều vùng
C. Giới hạn kích thước của từng trường trong payload
D. Vị trí đọc hoặc tiến độ xử lý trong một partition
Đáp án đúng: D

Câu 14. Với broker dạng log có retention, message đã đọc thường được xử lý thế nào?
A. Bị xóa ngay khi một consumer nhận thành công
B. Chuyển thẳng sang dead-letter queue sau khi đọc
C. Được gửi lại cho producer để xác nhận xóa
D. Vẫn giữ theo chính sách lưu trữ đã cấu hình
Đáp án đúng: D

Câu 15. Producer nhận publish confirmation từ broker thường có thể kết luận điều gì?
A. Broker đã tiếp nhận theo cơ chế xác nhận đã cấu hình
B. Consumer đã ghi thành công dữ liệu vào database
C. Mọi subscriber đã hoàn tất việc xử lý message
D. Mọi hệ thống liên quan đã đạt nhất quán tức thì
Đáp án đúng: A

Câu 16. Nếu yêu cầu phải khôi phục message sau sự cố broker, cần chú ý điều gì?
A. Chỉ tăng tốc độ xử lý của consumer đang hoạt động
B. Cấu hình lưu bền vững và mức xác nhận phù hợp
C. Chỉ thêm correlation ID cho mỗi message được gửi
D. Chỉ giảm kích thước payload trước khi publish
Đáp án đúng: B

Câu 17. Khi dùng manual acknowledgment, thời điểm ack phù hợp nhất thường là khi nào?
A. Ngay trước khi consumer bắt đầu mọi xử lý nghiệp vụ
B. Sau khi xử lý thành công các tác dụng phụ cần thiết
C. Ngay khi broker gửi message dù consumer chưa nhận
D. Khi producer kết thúc việc tạo message mới
Đáp án đúng: B

Câu 18. Consumer ghi DB xong nhưng chết trước khi ack; hệ quả nào có thể xảy ra?
A. Broker bảo đảm chỉ có một lần ghi database cuối cùng
B. Producer tự hủy mọi giao dịch đã ghi trước khi crash
C. Bản ghi DB tự rollback khi consumer mất kết nối broker
D. Broker phát lại và consumer xử lý trùng tác dụng phụ
Đáp án đúng: D

Câu 19. Bảo đảm giao nhận at-least-once thường đòi hỏi consumer chuẩn bị điều gì?
A. Message có thể đến lại và cần xử lý trùng an toàn
B. Mỗi message chắc chắn đến đúng một lần duy nhất
C. Broker không thể lưu lại message sau khi consumer đọc
D. Mọi message được xử lý theo thứ tự toàn hệ thống
Đáp án đúng: A

Câu 20. Đánh đổi chính của at-most-once khi xảy ra lỗi là gì?
A. Có thể nhân bản tác dụng phụ do phát lại vô hạn
B. Đảm bảo mọi message được xử lý đúng một lần ở DB
C. Có thể mất message vì không phát lại sau khi giao
D. Đảm bảo message không bị mất trong mọi sự cố mạng
Đáp án đúng: C

Câu 21. Vì sao exactly-once của một broker không tự đảm bảo exactly-once cho DB ngoài?
A. DB mặc định luôn tham gia transaction cùng broker
B. Consumer chỉ cần bỏ mọi khóa chống trùng nghiệp vụ
C. Broker luôn điều khiển được rollback của mọi ứng dụng
D. Giao dịch với DB có thể nằm ngoài phạm vi broker
Đáp án đúng: D

Câu 22. Một idempotent consumer cần duy trì đặc tính nào?
A. Nhận lại message thì luôn tạo giao dịch mới
B. Xử lý lại cùng message không lặp tác dụng phụ
C. Ghi dữ liệu rồi luôn bỏ qua trạng thái xử lý
D. Tăng số thread để mọi message được xử lý song song
Đáp án đúng: B

Câu 23. Khi chống trùng bằng message ID, cách làm nào đáng tin cậy hơn?
A. Lưu ID đã xử lý cùng thay đổi nghiệp vụ trong một transaction
B. Lưu ID chỉ trong bộ nhớ của process đang chạy
C. Dựa vào timestamp của log để phân biệt lần gửi
D. Tăng thời gian retry để giảm số message trùng
Đáp án đúng: A

Câu 24. Correlation ID trong luồng messaging nhiều service thường dùng để làm gì?
A. Đảm bảo schema cũ luôn giải mã được schema mới
B. Thay thế mã định danh của mọi đối tượng nghiệp vụ
C. Đảm bảo consumer group không cần ghi nhận offset
D. Liên kết các message thuộc cùng một luồng xử lý
Đáp án đúng: D

Câu 25. Schema registry trong hệ thống messaging thường hỗ trợ điều gì?
A. Tự chạy code nghiệp vụ mà consumer chưa triển khai
B. Quản lý phiên bản schema và kiểm tra quy tắc tương thích
C. Tự xóa message đã xử lý trong mọi loại broker
D. Thay thế mọi chính sách xác thực của producer
Đáp án đúng: B

Câu 26. Thay đổi payload nào thường dễ tương thích với consumer bỏ qua trường lạ?
A. Xóa thuộc tính bắt buộc mà consumer cũ đang đọc
B. Đổi kiểu thuộc tính định danh từ số thành đối tượng
C. Thêm thuộc tính tùy chọn mà consumer cũ không cần
D. Đổi tên trường dùng làm khóa liên kết dữ liệu
Đáp án đúng: C

Câu 27. Khi thêm một trường bắt buộc vào schema mới, rủi ro tương thích nào có thể phát sinh?
A. Consumer cũ tự sinh trường mới từ dữ liệu đã lưu trước
B. Broker tự sửa mọi message lịch sử sang định dạng mới
C. Producer cũ có thể không tạo payload hợp lệ theo schema mới
D. Mọi producer cũ luôn cập nhật schema ngay khi publish
Đáp án đúng: C

Câu 28. Khi payload hỗ trợ nhiều phiên bản, consumer nên tiếp cận thế nào?
A. Nhận diện schema/version rồi giải mã theo hợp đồng phù hợp
B. Luôn giả định mọi payload có cấu trúc từ phiên bản mới nhất
C. Bỏ kiểm tra cấu trúc vì broker đã chấp nhận message
D. Yêu cầu xóa toàn bộ message cũ khỏi kho lưu trữ
Đáp án đúng: A

Câu 29. Poison message trong hệ thống xử lý hàng đợi thường chỉ điều gì?
A. Message hợp lệ nhưng cần nhiều thời gian xử lý hơn
B. Message chứa dữ liệu đã được consumer ghi thành công
C. Message lỗi lặp đi lặp lại với cùng điều kiện xử lý
D. Message thuộc một partition có throughput rất cao
Đáp án đúng: C

Câu 30. Dead-letter queue được dùng chủ yếu cho mục đích nào?
A. Lưu mọi message thành công nhằm thay thế business log
B. Lưu token của producer cho các consumer đăng nhập
C. Lưu tất cả message vừa gửi để thay database nghiệp vụ
D. Lưu message không xử lý được để điều tra và khôi phục
Đáp án đúng: D

Câu 31. Khi gặp lỗi kết nối DB tạm thời, cách retry nào thường phù hợp?
A. Thử lại có giới hạn với backoff và jitter
B. Thử lại ngay liên tục mà không đặt số lần tối đa
C. Chuyển tất cả lỗi 4xx thành lỗi kết nối tạm thời
D. Bỏ qua bước ghi DB nhưng vẫn ack thành công
Đáp án đúng: A

Câu 32. Với payload sai schema không thể giải mã, chiến lược xử lý nào phù hợp?
A. Thử lại vô hạn với khoảng chờ ngày càng ngắn
B. Phân loại lỗi cố định và chuyển sang luồng xử lý lỗi
C. Xác nhận đã xử lý thành công dù chưa đọc được dữ liệu
D. Chờ producer tự sửa message đang nằm trong broker
Đáp án đúng: B

Câu 33. Exponential backoff kết hợp jitter giúp giảm rủi ro gì trong retry?
A. Nhiều consumer đồng loạt gửi lại và gây quá tải
B. Consumer nhận message thuộc quá nhiều schema khác nhau
C. Producer gửi message có kích thước payload quá lớn
D. Một message bị phân phối vào partition không mong muốn
Đáp án đúng: A

Câu 34. Vì sao cần giới hạn số lần retry hoặc tổng thời gian retry?
A. Đảm bảo mọi sự cố đều được khắc phục bằng retry
B. Bắt consumer bỏ qua mọi message có thể thành công
C. Tránh giữ tác vụ lỗi vô hạn và làm nghẽn năng lực xử lý
D. Cho phép broker tự thay đổi quy tắc schema hiện tại
Đáp án đúng: C

Câu 35. Khi một poison message chặn các message phía sau cùng queue, hướng xử lý nào hữu ích?
A. Phát lại ngay vô hạn trước khi nhận message tiếp
B. Chuyển sang DLQ theo chính sách để giải phóng luồng
C. Dừng tất cả producer đến khi có người sửa bằng tay
D. Xóa toàn bộ message còn lại để tránh chờ lâu
Đáp án đúng: B

Câu 36. Backpressure trong consumer pipeline nhằm giải quyết điều gì?
A. Điều tiết tốc độ nhận khi năng lực xử lý không theo kịp
B. Tăng số message phát ra dù bộ đệm đã gần đầy
C. Bỏ qua yêu cầu xác nhận để luôn giảm số lần gọi
D. Buộc producer dùng cùng kết nối mạng với consumer
Đáp án đúng: A

Câu 37. Khi tăng worker nhận message, giới hạn nào cần xem xét bên cạnh số worker?
A. Chỉ số lượng trường tùy chọn của schema message
B. Chỉ độ dài tên queue trong cấu hình routing
C. Số partition, quota broker và năng lực downstream
D. Chỉ số lượng consumer từng hoạt động trong lịch sử
Đáp án đúng: C

Câu 38. Transactional outbox giúp giải quyết tình huống nào giữa DB và broker?
A. DB đã commit nhưng event liên quan chưa được phát
B. Consumer đã nhận event nhưng không biết loại payload
C. Producer đã xác thực nhưng chưa có kết nối TLS
D. Broker phát lại message sau khi hết thời gian retry
Đáp án đúng: A

Câu 39. Trong outbox pattern, thao tác nào thường được ghi chung transaction?
A. Thay đổi nghiệp vụ và bản ghi sự kiện outbox
B. Gửi message đến broker và nhận ack từ consumer
C. Commit database của hai hệ thống ở hai vùng mạng
D. Đọc offset consumer và thay đổi schema registry
Đáp án đúng: A

Câu 40. Khi chuyển outbox event bằng CDC, thành phần đọc thường theo dõi nguồn nào?
A. HTTP access log của các API gateway bên ngoài
B. Nhật ký thay đổi DB để phát hiện bản ghi outbox
C. Trạng thái bộ nhớ đệm trong từng trình duyệt client
D. Bộ đếm kết nối mạng của consumer đang hoạt động
Đáp án đúng: B

Câu 41. Eventual consistency mô tả điều gì ở các hệ thống nhận event?
A. Mọi consumer luôn thấy dữ liệu mới cùng một thời điểm
B. Trạng thái có thể lệch tạm thời và hội tụ sau khi cập nhật
C. Mọi hệ thống dùng chung một transaction ACID duy nhất
D. Mọi bản sao cần được ghi xong trước khi producer trả
Đáp án đúng: B

Câu 42. Khi nghi ngờ bỏ sót sự kiện đồng bộ, reconciliation dùng để làm gì?
A. Tự tăng số lần retry bất kể lỗi thuộc loại nào
B. Bỏ qua các message có cùng correlation ID
C. Đối chiếu dữ liệu và khôi phục các sai lệch đã phát sinh
D. Tự chuyển hệ thống thành xử lý đồng bộ tức thời
Đáp án đúng: C

Câu 43. Sử dụng TLS cho kết nối với broker chủ yếu bảo vệ điều gì?
A. Đảm bảo message giữ thứ tự tuyệt đối giữa mọi topic
B. Tự động cấp quyền đọc toàn bộ queue cho consumer
C. Mã hóa truyền dẫn và xác minh danh tính endpoint
D. Bảo đảm tác vụ DB không thực hiện lặp sau retry
Đáp án đúng: C

Câu 44. Quyền của tài khoản producer và consumer nên được cấp như thế nào?
A. Cấp quyền quản trị toàn broker để tránh lỗi kết nối
B. Dùng một mật khẩu chung cho mọi service trong cụm
C. Cho mọi producer quyền đọc message của tất cả queue
D. Tách quyền publish và consume theo kênh cần truy cập
Đáp án đúng: D

Câu 45. Khi message chứa dữ liệu cá nhân, biện pháp log nào phù hợp hơn?
A. Che trường nhạy cảm và log ID phục vụ theo dõi
B. Ghi toàn bộ payload vào mọi log để dễ đối chiếu
C. Đưa dữ liệu cá nhân vào routing key công khai
D. Tắt toàn bộ ghi nhận message ID và mã lỗi
Đáp án đúng: A

Câu 46. Consumer lag trong broker dạng log thường được hiểu là gì?
A. Số broker bị tắt trong khoảng thời gian gần đây
B. Số lần schema được thay đổi từ khi triển khai
C. Khoảng cách giữa vị trí ghi và vị trí đã tiêu thụ
D. Khoảng trễ DNS khi producer khởi tạo kết nối
Đáp án đúng: C

Câu 47. Để phát hiện kẹt xử lý message, bộ chỉ số nào hữu ích nhất?
A. Lag, tuổi message, tỷ lệ lỗi và lượng vào DLQ
B. Chỉ số lượng file cấu hình của mỗi dịch vụ đang chạy
C. Chỉ số dòng code trong các lớp producer và consumer
D. Chỉ dung lượng trang tài liệu mô tả schema mới
Đáp án đúng: A

Câu 48. Integration test cho at-least-once nên bao gồm kịch bản nào?
A. Producer gửi một message thành công khi không xảy ra lỗi
B. Chỉ kiểm tra serialize/deserialize payload trong bộ nhớ
C. Chỉ kiểm tra một request HTTP trả về status 200
D. Consumer ghi DB rồi crash trước ack và nhận lại message
Đáp án đúng: D

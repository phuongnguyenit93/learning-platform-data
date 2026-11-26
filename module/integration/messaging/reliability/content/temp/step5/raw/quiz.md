Câu 1. Producer nhận xác nhận publish từ broker có thể kết luận điều gì?
A. Consumer đã commit mọi thay đổi vào cơ sở dữ liệu
B. Tất cả subscriber đã hoàn thành xử lý message
C. Broker đã nhận message theo mức ack được cấu hình
D. Các dịch vụ liên quan đã đồng bộ hoàn toàn dữ liệu
Đáp án đúng: C

Câu 2. Khi broker nhận message nhưng producer mất phản hồi xác nhận, producer nên làm gì?
A. Bỏ message vì broker chắc chắn chưa nhận được dữ liệu
B. Tạo ID mới cho từng lần thử mà không cần chống trùng
C. Đợi consumer báo thành công rồi mới gửi message lại
D. Thử lại với ID ổn định và có cơ chế xử lý trùng
Đáp án đúng: D

Câu 3. Nếu cần sống sót qua lần khởi động lại broker, cấu hình nào đáng chú ý?
A. Lưu message bền vững cùng chính sách xác nhận ghi
B. Chỉ dùng queue durable nhưng message vẫn transient
C. Chỉ tăng consumer dự phòng mà không ghi bền message
D. Chỉ bật producer retry mà không ghi bền message
Đáp án đúng: A

Câu 4. Khi broker có replication, publish ack từ nhiều bản sao giúp gì?
A. Bảo đảm mọi consumer hoàn tất các bước nghiệp vụ
B. Loại bỏ nhu cầu theo dõi các bản sao bị tụt hậu
C. Bảo đảm thao tác ghi vào DB ngoài là nguyên tử
D. Giảm rủi ro mất message khi một nút lưu trữ lỗi
Đáp án đúng: D

Câu 5. Manual acknowledgement thường được gửi khi nào để hạn chế mất tác vụ?
A. Ngay sau khi payload vượt qua kiểm tra schema đầu vào
B. Sau khi worker gửi lệnh ghi DB nhưng chưa commit
C. Sau khi tác dụng phụ cần thiết đã được xác nhận
D. Sau khi broker phân phối message tới consumer
Đáp án đúng: C

Câu 6. Consumer ack trước khi ghi DB rồi bị crash; rủi ro chính là gì?
A. Broker sẽ luôn gửi lại message cho consumer khác
B. DB tự động phục hồi message do consumer chưa xử lý
C. Broker xem message hoàn tất dù DB chưa được ghi
D. Producer sẽ tự rollback transaction của cơ sở dữ liệu
Đáp án đúng: C

Câu 7. Consumer commit DB rồi crash trước lúc ack; tình huống nào có thể xảy ra?
A. Message mất hẳn do đã commit thành công vào DB
B. Message được phát lại và thao tác có nguy cơ trùng
C. Broker tự rollback bản ghi đã được DB chấp nhận
D. Producer tự đánh dấu message đã xử lý đúng một lần
Đáp án đúng: B

Câu 8. Bảo đảm at-most-once có đánh đổi điển hình nào khi gặp lỗi?
A. Có thể xử lý trùng vì retry được bật mặc định
B. Bảo đảm ghi DB đúng một lần trên mọi downstream
C. Có thể mất message do không yêu cầu phát lại
D. Bảo đảm broker lưu message đến khi có consumer
Đáp án đúng: C

Câu 9. Bảo đảm at-least-once yêu cầu consumer lưu ý điều gì?
A. Message có thể được giao lại nên cần chống trùng
B. Message được gửi chính xác một lần trong mọi sự cố
C. Thứ tự toàn cục được duy trì trên mọi partition
D. Consumer không cần thông báo kết quả cho broker
Đáp án đúng: A

Câu 10. Vì sao exactly-once của broker chưa đủ cho DB nằm ngoài broker?
A. Broker luôn nắm quyền commit của từng DB ứng dụng
B. DB tự động hợp nhất tất cả giao dịch từ producer
C. Phạm vi giao dịch broker có thể không bao gồm DB
D. Message chỉ cần có event ID là đủ ngăn mọi side effect
Đáp án đúng: C

Câu 11. Ở queue có visibility timeout, timeout ngắn hơn thời gian xử lý gây gì?
A. Message chuyển ngay sang DLQ khi worker còn xử lý
B. Message có thể hiện lại khi worker chưa xử lý xong
C. Message luôn bị khóa cho worker đến khi có ack
D. Message bị xóa khỏi queue khi thời gian ẩn kết thúc
Đáp án đúng: B

Câu 12. Khi tác vụ dài hơn visibility timeout, consumer có thể làm gì?
A. Gia hạn thời gian ẩn message khi vẫn đang xử lý
B. Giảm prefetch để message không hết visibility timeout
C. Dùng producer retry để kéo dài visibility timeout
D. Ack message sớm rồi tiếp tục phần xử lý còn lại
Đáp án đúng: A

Câu 13. Khi DB tạm không kết nối được, cách xử lý phù hợp hơn là gì?
A. Chuyển ngay mọi message sang luồng xử lý vĩnh viễn
B. Ack thành công dù dữ liệu chưa lưu ở phía consumer
C. Retry có giới hạn và phân loại lỗi là tạm thời
D. Chạy lại vô hạn không có bất kỳ giới hạn thời gian
Đáp án đúng: C

Câu 14. Khi payload sai schema và không thể giải mã, hướng xử lý nào hợp lý?
A. Phân loại lỗi cố định rồi đưa vào luồng cách ly
B. Retry ngay liên tục để chờ schema tự đổi tại broker
C. Ack rồi xóa payload mà không lưu thông tin điều tra
D. Chuyển sang một partition khác với schema cũ hơn
Đáp án đúng: A

Câu 15. Exponential backoff kết hợp jitter giúp giảm điều gì?
A. Các message trùng được broker loại bỏ khi retry
B. Đợt retry đồng loạt gây áp lực lên dịch vụ đích
C. Thời gian chờ thử lại giống nhau ở mọi producer
D. Số lần retry của mỗi message bị giảm về một
Đáp án đúng: B

Câu 16. Tại sao cần retry budget hoặc giới hạn thời gian thử lại?
A. Ngăn tác vụ lỗi chiếm tài nguyên vô hạn
B. Tăng xác suất message được xử lý lại vô hạn
C. Giữ mọi request tồn tại sau khi deadline hết
D. Bắt broker lưu từng attempt vào cùng DB
Đáp án đúng: A

Câu 17. Dead-letter queue chủ yếu phục vụ mục đích nào?
A. Lưu message chờ lần retry tự động tiếp theo
B. Lưu offset đã commit cho các consumer group
C. Lưu bản sao mọi message đã xử lý thành công
D. Lưu message xử lý thất bại để điều tra và xử lý lại
Đáp án đúng: D

Câu 18. Khi đưa một message vào DLQ, metadata nào hữu ích nhất?
A. Message ID, nguồn, số lần thử và nguyên nhân lỗi
B. Message ID, partition và thời điểm gửi ban đầu
C. Tên topic, routing key và kích thước payload gốc
D. Consumer ID, lần nhận gần nhất và mã trạng thái ack
Đáp án đúng: A

Câu 19. Sau khi sửa nguyên nhân lỗi DLQ, cách replay nào an toàn hơn?
A. Phát lại có kiểm soát và giữ cơ chế chống trùng
B. Đổi message ID để buộc mọi side effect chạy lại
C. Bỏ bước kiểm tra schema vì payload từng bị lỗi
D. Gửi toàn bộ DLQ cùng lúc và không giới hạn tải
Đáp án đúng: A

Câu 20. Poison message thường được nhận biết bằng dấu hiệu nào?
A. Thông điệp được xử lý chậm nhưng luôn thành công
B. Cùng thông điệp liên tục thất bại qua các lần xử lý
C. Thông điệp lớn nhưng được giải mã và ack hợp lệ
D. Thông điệp được lưu bền vững ở nhiều broker
Đáp án đúng: B

Câu 21. Nếu retry xảy ra sau khi một phần tác dụng phụ đã thực hiện, nên ưu tiên gì?
A. Tăng số consumer để những bước trước tự rollback
B. Thay message ID ở lần retry để thành giao dịch mới
C. Thiết kế idempotent hoặc ghi nhận tiến độ nghiệp vụ
D. Bỏ trạng thái xử lý cũ và luôn tạo bản ghi mới
Đáp án đúng: C

Câu 22. Chọn idempotency key cho một thao tác tạo thanh toán nên thế nào?
A. Sinh một key khác nhau cho mỗi request retry
B. Ổn định giữa các lần thử của cùng một yêu cầu
C. Dựa duy nhất vào thời gian nhận ở mỗi worker
D. Dùng ID kết nối TCP của lần gửi hiện tại
Đáp án đúng: B

Câu 23. Trong DB quan hệ, cách chống trùng message bền vững hơn là gì?
A. Lưu ID đã xử lý chỉ trong RAM của một consumer
B. Lưu dấu xử lý và cập nhật nghiệp vụ trong một transaction
C. Đợi message hết thời hạn lưu rồi mới commit DB
D. Dùng timestamp xử lý để suy ra mọi bản ghi trùng
Đáp án đúng: B

Câu 24. Vì sao chỉ dùng bộ nhớ RAM để lưu ID đã xử lý không đủ tin cậy?
A. RAM tự chia sẻ danh sách ID cho mọi worker trong nhóm
B. Broker ghi nhận RAM là dấu xác nhận xử lý bền vững
C. Restart hoặc chuyển worker sẽ mất thông tin chống trùng
D. Offset của consumer thay thế hoàn toàn kho chống trùng
Đáp án đúng: C

Câu 25. Khi hai message của cùng entity được ghi vào cùng một partition, thứ tự nào được bảo đảm?
A. Thứ tự hoàn tất nghiệp vụ ở tất cả worker song song
B. Thứ tự bản ghi trong cùng một partition của topic
C. Thứ tự toàn hệ thống kể cả nhiều topic độc lập
D. Thứ tự commit của mọi cơ sở dữ liệu downstream
Đáp án đúng: B

Câu 26. Với hệ thống phân vùng, chọn key theo orderId thường để làm gì?
A. Phân phối từng event của cùng đơn qua nhiều partition
B. Đưa mọi orderId vào chung một partition duy nhất
C. Giữ thứ tự tuyệt đối giữa nhiều đơn khác nhau
D. Giữ event của cùng đơn ở một partition nhất quán
Đáp án đúng: D

Câu 27. Khi xử lý song song nhiều message trong một partition, điều gì cần lưu ý?
A. Thứ tự lưu trên broker thay đổi theo tốc độ xử lý
B. Thứ tự commit side effect có thể khác thứ tự nhận
C. Thứ tự nhận luôn bảo đảm thứ tự commit song song
D. Offset commit buộc mọi handler hoàn thành tuần tự
Đáp án đúng: B

Câu 28. Retry một message cũ theo hàng đợi riêng có thể làm phát sinh vấn đề nào?
A. Retry queue giữ nguyên offset của queue chính
B. Broker ưu tiên message cũ dù ở hai queue khác nhau
C. Message mới có thể xử lý trước message cũ
D. Delay ở retry queue không làm đổi thứ tự theo entity
Đáp án đúng: C

Câu 29. Khi event cập nhật có trường version, consumer nên làm gì với version cũ?
A. Ghi đè mọi trạng thái hiện có bằng payload cũ
B. Đặt version mới thành giá trị ngẫu nhiên để chống trùng
C. Retry vô hạn cho đến khi version cũ thành mới
D. Kiểm tra version rồi bỏ qua cập nhật đã lỗi thời
Đáp án đúng: D

Câu 30. Vì sao timestamp từ hai service không đủ để xác định chắc chắn thứ tự nghiệp vụ?
A. Đồng hồ có thể lệch và khác thứ tự commit
B. Broker loại bỏ timestamp trước khi chuyển cho consumer
C. Mọi service đồng bộ thời gian cũng đồng bộ thứ tự
D. Timestamp tự động là khóa duy nhất cho mọi giao dịch
Đáp án đúng: A

Câu 31. Khi cập nhật DB rồi publish event bằng hai thao tác độc lập, lỗi nào có thể xảy ra?
A. DB tự rollback khi broker không xác nhận publish
B. Ack broker bảo đảm dữ liệu hai hệ thống đã nhất quán
C. Consumer tự suy ra event thiếu từ transaction DB
D. DB commit thành công nhưng event không được phát
Đáp án đúng: D

Câu 32. Trong transactional outbox, thao tác nào được commit nguyên tử?
A. Đẩy message đến broker cùng ack của mọi consumer
B. Thay đổi dữ liệu nghiệp vụ cùng bản ghi outbox
C. Ghi DB dịch vụ A cùng ghi DB dịch vụ B độc lập
D. Commit tại broker cùng mọi cập nhật ở search index
Đáp án đúng: B

Câu 33. Outbox relay crash sau publish nhưng trước khi đánh dấu đã gửi có thể gây gì?
A. Consumer bỏ mọi bản sao nhờ dùng cùng partition
B. Broker ack tự đánh dấu outbox row là đã gửi
C. DB rollback event đã publish khi relay ngừng
D. Event được gửi lại nên downstream cần idempotency
Đáp án đúng: D

Câu 34. Dùng CDC để chuyển outbox event thường dựa trên nguồn nào?
A. Nhật ký thay đổi DB ghi nhận bản ghi outbox
B. Bảng outbox được quét định kỳ bằng truy vấn SQL
C. Log ack của consumer từ message broker
D. Webhook gửi trực tiếp từ dịch vụ nghiệp vụ
Đáp án đúng: A

Câu 35. Vì sao transactional outbox không tự đảm bảo consumer chỉ ghi một lần?
A. Outbox bảo đảm key mới cho từng lần relay retry
B. Relay có thể gửi trùng nên consumer cần dedup
C. Ack của consumer nằm cùng transaction với outbox
D. Broker không thể redeliver message đã publish
Đáp án đúng: B

Câu 36. Inbox pattern ở phía consumer có thể hỗ trợ mục tiêu nào?
A. Lưu offset broker thay cho dấu message đã xử lý
B. Ghi event chưa phát trong transaction của producer
C. Phát lại mọi message theo thứ tự của partition
D. Lưu định danh đã xử lý cùng kết quả thay đổi nghiệp vụ
Đáp án đúng: D

Câu 37. Retry queue có delay khác DLQ ở mục đích chính nào?
A. Retry dành cho lỗi tạm; DLQ giữ lỗi cần can thiệp
B. Retry chỉ cho lỗi schema; DLQ chỉ cho lỗi kết nối
C. Retry lưu bản ghi vĩnh viễn; DLQ tự xóa khi timeout
D. Retry luôn yêu cầu thao tác thủ công; DLQ tự xử lý
Đáp án đúng: A

Câu 38. Trong Saga, nếu một bước sau thất bại, cơ chế nào thường phù hợp?
A. Rollback một transaction ACID chung trên mọi service
B. Xóa mọi message trước đó khỏi broker rồi commit DB
C. Chạy nghiệp vụ bù trừ cho những bước đã thành công
D. Bỏ qua các bước đã xử lý và phát lại vô hạn
Đáp án đúng: C

Câu 39. Eventual consistency thể hiện điều gì trong hệ thống event-driven?
A. Các bản sao có thể lệch trước khi cập nhật được áp dụng
B. Các bản sao phải cùng cập nhật trước khi producer ack
C. Mọi subscriber luôn thấy dữ liệu tại cùng thời điểm
D. Mọi consumer chia sẻ một transaction với producer
Đáp án đúng: A

Câu 40. Để phát hiện dữ liệu lệch khi message bị bỏ sót, kỹ thuật nào hữu ích?
A. Reconciliation đối chiếu nguồn và khôi phục chênh lệch
B. Theo dõi số consumer đang hoạt động trên queue
C. Đo độ trễ xử lý trung bình của các consumer
D. Kiểm tra tỷ lệ publish ack thành công theo giờ
Đáp án đúng: A

Câu 41. Vì sao broker transaction chưa thay thế được ranh giới giao dịch nghiệp vụ?
A. Broker tự quản lý transaction của mọi hệ thống ngoài
B. Mọi service đều dùng một cơ sở dữ liệu giao dịch
C. Định danh message làm mọi thao tác thành nguyên tử
D. Các DB và side effect ngoài broker có commit riêng
Đáp án đúng: D

Câu 42. Khi broker tạm ngừng, producer nên tránh cách nào để bảo vệ hệ thống?
A. Giới hạn lượng tồn đọng và báo lỗi quá tải có kiểm soát
B. Đệm không giới hạn trong RAM khi broker chưa phục hồi
C. Đặt timeout và điều tiết tốc độ publish trở lại
D. Sử dụng outbox hoặc bộ đệm bền vững khi thích hợp
Đáp án đúng: B

Câu 43. Bộ chỉ số nào thường giúp phát hiện consumer không theo kịp?
A. Tốc độ publish, dung lượng broker và cache hit rate
B. Số consumer, retry count và thời gian phản hồi broker
C. Publish ack rate, lỗi kết nối và CPU tổng server
D. Lag, tuổi message chưa xử lý và throughput xử lý
Đáp án đúng: D

Câu 44. Khi DLQ tăng nhanh, thông tin nào nên có trong cảnh báo?
A. Số message publish, số partition và publish ack rate
B. Backlog queue chính, tuổi message và tốc độ publish
C. Tốc độ DLQ, loại lỗi và consumer liên quan
D. Retry count, throughput producer và thời gian kết nối
Đáp án đúng: C

Câu 45. Nếu DLQ chứa dữ liệu cá nhân, cách vận hành phù hợp hơn là gì?
A. Cho consumer nội bộ quyền đọc DLQ theo topic chung
B. Sao chép DLQ sang staging mà không khử thông tin cá nhân
C. Ghi payload lỗi vào log tập trung, chỉ giới hạn nhóm đọc
D. Giới hạn quyền truy cập và che dữ liệu nhạy cảm trong log
Đáp án đúng: D

Câu 46. Integration test cho at-least-once nên kiểm thử tình huống nào?
A. Producer phát một message thành công khi mạng ổn định
B. Ghi DB thành công rồi crash trước ack và nhận lại
C. Chỉ kiểm tra đọc ghi payload JSON trong một hàm
D. Chỉ kiểm tra kết nối broker mà không gọi consumer
Đáp án đúng: B

Câu 47. Kiểm thử độ bền broker nên bao gồm kịch bản nào?
A. Dừng consumer khi mọi node broker vẫn hoạt động
B. Đổi leader trong cụm khi queue chưa nhận message
C. Dừng node đã nhận publish rồi thử khôi phục
D. Đo throughput publish khi cả cụm broker khỏe mạnh
Đáp án đúng: C

Câu 48. Để xác minh hiệu quả idempotency từ đầu tới cuối, cần đo điều gì?
A. Message ID xuất hiện đúng một lần trong broker log
B. Các lần retry đều nhận cùng mã ack từ broker
C. Consumer xử lý tuần tự theo partition đã chọn
D. Nhiều lần giao cùng ID chỉ tạo một tác dụng phụ
Đáp án đúng: D

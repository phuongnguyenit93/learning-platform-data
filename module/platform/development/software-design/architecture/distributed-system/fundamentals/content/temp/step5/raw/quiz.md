Ví dụ nào thể hiện lỗi từng phần (partial failure) trong hệ phân tán?
A. Một node mất liên lạc trong khi node khác vẫn chạy
B. Cả cluster ngừng hoạt động khi mất nguồn điện
C. Mọi service đều trả về cùng lỗi ứng dụng
D. Một process đơn lẻ bị lỗi phép tính cục bộ
Đáp án đúng: A

Khi client bị timeout sau khi gửi yêu cầu ghi, điều nào vẫn chưa chắc chắn?
A. Kết nối hiện tại không trả phản hồi đúng hạn
B. Ứng dụng đã đến giới hạn thời gian chờ
C. Client đã phát sinh exception trong chương trình
D. Server đã xử lý yêu cầu hay phản hồi quá chậm
Đáp án đúng: D

Replication dữ liệu giữa nhiều node đem lại lợi ích và chi phí nào?
A. Mọi truy vấn đều nhận cùng dữ liệu ngay tức thì
B. Tăng khả dụng nhưng cần kiểm soát độ mới bản sao
C. Mọi bản sao luôn cập nhật nguyên tử trong mọi lỗi
D. Không còn cần thiết kế phân vùng hay điểm lưu trữ
Đáp án đúng: B

Với consistency tuyến tính, một đọc bắt đầu sau ghi thành công và không có ghi khác phải thấy gì?
A. Bất kỳ phiên bản cũ nào từ replica gần nhất
B. Giá trị ghi tạm chưa hoàn tất của node khác
C. Chỉ phiên bản được cache từ lần đọc trước
D. Trạng thái mới nhất của lần ghi đã hoàn tất
Đáp án đúng: D

Eventual consistency mong đợi điều gì khi ngừng ghi và đồng bộ tiếp tục thành công?
A. Mọi lần ghi chỉ được chấp nhận tại một node
B. Các phép đọc luôn thấy ghi gần nhất tức thời
C. Các replica cuối cùng hội tụ về cùng trạng thái
D. Mọi node trả cùng kết quả ngay trong lúc partition
Đáp án đúng: C

Theo CAP, khi mạng bị partition, điều gì cần đánh đổi trong cách phục vụ?
A. Chỉ throughput và dung lượng RAM của từng node
B. Mã hóa dữ liệu với dung lượng lưu trữ trên đĩa
C. Availability và consistency tuyến tính trong partition
D. Quyền truy cập với số lượng node trong cluster
Đáp án đúng: C

Chọn partition key mà phần lớn traffic dồn vào một khóa có nguy cơ nào?
A. Hot partition làm mất cân bằng tải giữa các shard
B. Mọi shard tự động nhận đều số lượng request
C. Replication không còn hoạt động sau khi sharding
D. Đọc dữ liệu luôn có độ trễ nhỏ hơn trước
Đáp án đúng: A

Raft dùng leader và majority chủ yếu để giải quyết vấn đề nào?
A. Cho mọi node ghi log độc lập không cần quorum
B. Đạt đồng thuận về thứ tự các bản ghi log
C. Đảm bảo mọi client luôn nhận phản hồi tức thì
D. Tự động tránh mọi loại network partition
Đáp án đúng: B

Với majority quorum, vì sao hai nhóm đa số của cùng tập node luôn giao nhau?
A. Mỗi nhóm chỉ cần một node đồng ý là đủ quorum
B. Mọi node luôn bỏ phiếu cho tất cả leader cùng lúc
C. Quorum có thể đạt được trong mọi vùng mạng cô lập
D. Hai quorum đa số luôn chia sẻ ít nhất một node
Đáp án đúng: D

Delivery at-least-once của broker có hệ quả nào cho consumer?
A. Message chỉ đến đúng một lần cho mỗi consumer
B. Một message có thể được nhận nhiều lần
C. Consumer luôn xử lý xong trước khi producer gửi
D. Broker tự rollback mọi tác động ngoài broker
Đáp án đúng: B

Retry yêu cầu thanh toán sau timeout cần phòng ngừa rủi ro gì?
A. Tạo transaction mới và bỏ qua lịch sử xử lý cũ
B. Giữ kết nối HTTP mở vô hạn để không cần retry
C. Ghi nhận cùng idempotency key để không thu tiền hai lần
D. Đổi mã yêu cầu mỗi retry để tránh bị nhận diện
Đáp án đúng: C

Nhiều client cùng retry ngay khi server phục hồi; cách nào giảm tải đột biến?
A. Tăng số lần retry không giới hạn cho mọi lỗi
B. Cho mọi client retry ngay trong cùng một mili giây
C. Exponential backoff kèm jitter giữa các lần thử
D. Tắt timeout ở mọi request để chờ server ổn định
Đáp án đúng: C

Circuit breaker giúp hạn chế lỗi dây chuyền bằng cách nào?
A. Tạm chặn lời gọi khi downstream liên tục thất bại
B. Khóa mọi node trong cluster bằng transaction chung
C. Tự chuyển mọi lỗi server thành kết quả thành công
D. Nhân bản request không giới hạn tới mọi replica
Đáp án đúng: A

Mẫu bulkhead giúp chống lan truyền lỗi theo hướng nào?
A. Xóa hàng đợi xử lý bất kỳ khi một request lỗi
B. Buộc tất cả service cùng chờ một semaphore
C. Cho mọi tác vụ dùng cùng một thread pool vô hạn
D. Tách nhóm tài nguyên để lỗi một luồng ít ảnh hưởng luồng khác
Đáp án đúng: D

Khi gọi dịch vụ mạng có thể treo, timeout giúp điều gì?
A. Loại bỏ hoàn toàn nhu cầu retry hoặc fallback
B. Giới hạn khoảng chờ để giải phóng nguồn lực
C. Phân biệt chắc chắn server chết với phản hồi chậm
D. Đảm bảo một request không bao giờ thất bại
Đáp án đúng: B

Transactional outbox hữu ích khi cập nhật DB đồng thời cần phát sự kiện vì sao?
A. Ghi state và outbox trong một transaction rồi phát sau
B. Đẩy message trước rồi giả định database sẽ commit
C. Gọi broker và database chung một transaction XA mặc định
D. Không cần quản lý event trùng trong consumer
Đáp án đúng: A

1. Trong Event Sourcing, nguồn sự thật để dựng trạng thái aggregate là gì?
A. Bản ghi mới nhất trong một bảng trạng thái hiện tại
B. Bản sao cache RAM của server đang xử lý command
C. Chuỗi event nghiệp vụ bất biến đã được lưu lại
D. Dữ liệu response từng gửi cho giao diện người dùng
Đáp án đúng: C

2. Tên event nào diễn đạt đúng một sự kiện nghiệp vụ đã xảy ra?
A. `ConfirmOrder` để yêu cầu xử lý một command
B. `GetOrderStatus` để thực hiện truy vấn read model
C. `ValidateOrder` để thực hiện kiểm tra đầu vào
D. `OrderConfirmed` sau khi đơn được xác nhận
Đáp án đúng: D

3. Trạng thái aggregate được tái dựng từ event stream ra sao?
A. Chỉ nạp event gần nhất rồi bỏ qua toàn bộ event cũ
B. Lần lượt áp dụng các event lên trạng thái ban đầu
C. Tính trung bình payload của mọi event trong stream
D. Dựa duy nhất vào timestamp của event mới nhất
Đáp án đúng: B

4. Khi nhận command, aggregate trong Event Sourcing thường làm gì?
A. Ghi command thẳng vào read model trước khi xác thực
B. Tái dựng state, kiểm invariant rồi tạo event phù hợp
C. Chỉ publish mọi command lên broker mà không đánh giá
D. Thay thế các event cũ bằng trạng thái của command mới
Đáp án đúng: B

5. Nếu hai writer sửa cùng aggregate, expected version giúp điều gì?
A. Tự chọn version event schema mới nhất khi ghi dữ liệu
B. Tăng số consumer có thể đọc đồng thời mọi projection
C. Phát hiện xung đột khi append event vào một stream
D. Buộc các event được publish đúng thứ tự trên mọi topic
Đáp án đúng: C

6. Để replay chính xác, thứ tự nào đáng tin hơn timestamp hệ thống?
A. Số thứ tự event được event store gán trong stream
B. Timestamp do từng client tự đưa vào payload request
C. Thứ tự các event được tải về qua các HTTP response
D. Thời gian server cuối cùng ghi log ra file cục bộ
Đáp án đúng: A

7. Trường nào thường dùng để gắn event với một aggregate cụ thể?
A. Aggregate ID hoặc stream ID nhất quán qua các event
B. Địa chỉ IP của consumer vừa đọc event gần nhất
C. Số lần retry của task đồng bộ read model hiện tại
D. Tên lớp giao diện mà client gọi trước khi đặt hàng
Đáp án đúng: A

8. Một command được gửi lại sau timeout có thể gây vấn đề gì?
A. Tự động loại bỏ event hợp lệ đã ghi từ command trước
B. Thay đổi thứ tự mọi stream khác dù chỉ ghi một aggregate
C. Làm event store bỏ qua mọi version kiểm tra đồng thời
D. Sinh event nghiệp vụ trùng nếu thiếu idempotency key
Đáp án đúng: D

9. Khi một event đã append thành công, thao tác nào phù hợp với tính bất biến?
A. Ghi đè payload event cũ rồi giữ nguyên event ID
B. Ghi event điều chỉnh mới thay vì sửa event lịch sử
C. Xóa event cũ để tạo lại cùng version cho stream
D. Chỉ đổi timestamp event cũ mà không cần audit
Đáp án đúng: B

10. Điểm phân biệt Event Sourcing với audit log thông thường là gì?
A. Audit log bắt buộc phát event ra message broker công cộng
B. Event Sourcing chỉ lưu bản snapshot cuối cùng của state
C. Audit log luôn đủ để tự động phục hồi mọi trạng thái
D. Event là nguồn dựng state, không chỉ lịch sử bổ sung
Đáp án đúng: D

11. Aggregate boundary trong Event Sourcing giúp kiểm soát điều gì?
A. Mọi query phải dùng một transaction trải nhiều dịch vụ
B. Mọi event phải được định tuyến đến chung một partition
C. Phạm vi invariant và ghi event theo từng aggregate
D. Tất cả aggregate phải có cùng trường và mã định danh
Đáp án đúng: C

12. Snapshot trong Event Sourcing chủ yếu giải quyết vấn đề nào?
A. Thay thế vĩnh viễn nhu cầu lưu toàn bộ event
B. Rút ngắn thời gian dựng state từ stream dài
C. Cho phép ghi đè event đã phát mà không gây lỗi
D. Bảo đảm consumer chỉ nhận được một event duy nhất
Đáp án đúng: B

13. Sau khi tải snapshot tại version N, để dựng state mới nhất cần làm gì?
A. Áp dụng các event của stream sau version N
B. Phát lại mọi event trước N rồi bỏ snapshot đã tải
C. Chỉ dùng snapshot vì luôn chứa đủ event mới nhất
D. Xóa tất cả event có version lớn hơn snapshot
Đáp án đúng: A

14. Vai trò của projection trong kiến trúc Event Sourcing là gì?
A. Kiểm tra invariant của aggregate trước khi ghi command
B. Biến chuỗi event thành read model phục vụ truy vấn
C. Thay thế event store thành nơi ghi dữ liệu nguồn
D. Chỉ tạo report tĩnh một lần khi ứng dụng khởi động
Đáp án đúng: B

15. Vì sao read projection có thể chậm hơn stream ghi một khoảng thời gian?
A. Mọi query phải chờ toàn bộ aggregate trên server khác
B. Snapshot chỉ cho phép đọc trạng thái vào cuối ngày
C. Event store tự xóa event mới cho tới khi được query
D. Projection thường cập nhật bất đồng bộ sau event được ghi
Đáp án đúng: D

16. Khi replay event để dựng lại projection, cần tránh hành động nào?
A. Áp dụng event theo thứ tự đã ghi trong event stream
B. Gửi lại email hoặc thu tiền như thể event vừa mới xảy ra
C. Đọc metadata version của event lịch sử để chuyển đổi
D. Theo dõi tiến độ replay và xác nhận bản ghi đã xử lý
Đáp án đúng: B

17. Consumer projection khởi động lại từ checkpoint, vì sao vẫn cần idempotent?
A. Vì checkpoint luôn chứa bản sao của mọi event đã ghi
B. Vì read model luôn được cập nhật trước khi event append
C. Có thể xử lý lại event đã đọc nhưng chưa lưu checkpoint
D. Vì mọi event sau checkpoint đều tự động bị hủy
Đáp án đúng: C

18. Khi đổi schema của event, nguyên tắc nào giảm vỡ dữ liệu lịch sử?
A. Đảm bảo mã đọc vẫn hiểu được event version cũ
B. Buộc event store sửa đồng loạt mọi event đã ghi
C. Xóa toàn bộ event có field không còn được sử dụng
D. Cho phép đổi nghĩa field cũ mà không cần mapping
Đáp án đúng: A

19. Upcaster trong Event Sourcing thường làm công việc nào?
A. Tự chuyển command lỗi thành event thành công mới
B. Thay đổi thứ tự append event đã lưu trong stream
C. Loại bỏ mọi event chưa được consumer xác nhận
D. Chuyển dạng event cũ thành cấu trúc mới khi đọc
Đáp án đúng: D

20. Cặp metadata correlation ID và causation ID hỗ trợ điều gì?
A. Theo dõi một luồng nghiệp vụ và nguyên nhân tạo event
B. Thay thế aggregate version trong mọi lệnh ghi event
C. Xác định dung lượng lưu trữ bắt buộc của snapshot
D. Đảm bảo mọi consumer cùng dùng một connection pool
Đáp án đúng: A

21. Nếu cần phát event từ event store sang broker, cần chú ý lỗi nào?
A. Broker luôn có quyền rollback sự kiện trong event store
B. Event append tự động bảo đảm mọi consumer đã đọc xong
C. Replay projection sẽ gửi mọi event mới lên broker
D. Event đã ghi nhưng publish broker không thành công
Đáp án đúng: D

22. Với event chứa dữ liệu cá nhân, rủi ro quản trị nào cần xét?
A. PII luôn an toàn vì đã ghi trong immutable event store
B. Chỉ cần ẩn PII trên UI thì event lịch sử sẽ tự xóa
C. Khó xóa PII trong log bất biến theo yêu cầu pháp lý
D. Có thể lưu toàn bộ dữ liệu nhạy cảm không giới hạn
Đáp án đúng: C

23. Khi thay đổi quy tắc invariant của aggregate, test replay nên xác minh gì?
A. Mọi event cũ buộc phải bị từ chối khi nâng version
B. Snapshot phải có đúng cùng số field với read model
C. Logic mới vẫn đọc và diễn giải được các event lịch sử
D. Tất cả command cũ phải được chạy lại như lệnh mới
Đáp án đúng: C

24. Khi đánh giá có nên dùng Event Sourcing, trade-off quan trọng nào?
A. Được truy vết và replay nhưng tốn chi phí vận hành phức tạp
B. Có trạng thái mới nhất mà không cần cơ chế concurrency
C. Luôn đơn giản hơn CRUD vì không cần quản lý event schema
D. Loại bỏ mọi nhu cầu backup vì event store tự khôi phục
Đáp án đúng: A

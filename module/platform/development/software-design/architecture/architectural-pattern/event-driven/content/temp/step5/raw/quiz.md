1. Trong kiến trúc hướng sự kiện, producer thường có trách nhiệm gì?
A. Phát sự kiện mô tả thay đổi đã xảy ra trong miền
B. Chờ consumer đồng ý rồi mới tạo request đồng bộ
C. Chỉnh sửa trực tiếp trạng thái nội bộ của consumer
D. Đọc dữ liệu từ mọi broker để cập nhật giao diện
Đáp án đúng: A

2. Vai trò chính của message broker giữa producer và consumer là gì?
A. Thay thế toàn bộ quy tắc nghiệp vụ của từng dịch vụ
B. Buộc các consumer chạy trong cùng một transaction DB
C. Lưu session của giao diện người dùng giữa các node
D. Phân phối message để các bên không cần gọi trực tiếp
Đáp án đúng: D

3. Điều gì phân biệt event 'OrderPlaced' với command 'PlaceOrder'?
A. Event buộc consumer phải trả lời đồng bộ cho producer
B. Command chỉ được gửi sau khi trạng thái đã commit
C. Command không thể mang định danh thực thể nghiệp vụ
D. Event báo việc đã xảy ra; command yêu cầu thực hiện
Đáp án đúng: D

4. Trong mô hình publish/subscribe, nhiều consumer độc lập có thể làm gì?
A. Cùng nhận một event và xử lý cho nhu cầu riêng
B. Buộc chỉ một consumer toàn hệ thống thấy mỗi event
C. Cùng chia sẻ một bảng nghiệp vụ để khóa trạng thái
D. Phải gửi response trực tiếp đến producer trước khi ack
Đáp án đúng: A

5. Khi thiết kế hợp đồng event, trường nào giúp nhận diện một lần phát?
A. Event ID ổn định dùng nhận diện sự kiện đã phát
B. Tên thread Java đang chạy ở thời điểm publish
C. Địa chỉ IP ngẫu nhiên của máy phát sự kiện
D. Số connection pool đang mở của ứng dụng
Đáp án đúng: A

6. Vì sao event nên thể hiện sự kiện nghiệp vụ thay vì hình dạng bảng DB?
A. Giúp consumer tự sửa schema bảng của producer
B. Cho phép mỗi event thay thế cơ chế phân quyền
C. Bảo đảm mọi bản tin luôn vừa đúng một phân vùng
D. Giảm phụ thuộc vào schema lưu trữ của producer
Đáp án đúng: D

7. Trong pub/sub, khác biệt giữa hai consumer độc lập và một consumer group là gì?
A. Mỗi subscription dùng chung một hàng đợi nhận duy nhất
B. Một consumer group bắt buộc phát nhiều bản sao event
C. Mỗi subscription nhận riêng; group chia việc xử lý
D. Mọi consumer độc lập luôn cùng sửa một record DB
Đáp án đúng: C

8. Trong broker phân vùng, chọn partition key theo orderId giúp gì?
A. Bảo đảm thứ tự tuyệt đối của mọi event trên toàn broker
B. Giữ thứ tự event cùng orderId trong một partition
C. Tự loại bỏ tất cả event trùng sau mỗi lần consumer lỗi
D. Bảo đảm mọi consumer luôn nhận event trong cùng mili giây
Đáp án đúng: B

9. Với delivery at-least-once, consumer cần chấp nhận điều gì?
A. Một thông điệp có thể được giao lại nhiều lần
B. Mọi thông điệp chỉ được giao chính xác một lần
C. Mọi thông điệp sẽ được giao trước khi được tạo
D. Broker sẽ loại bỏ tự động mọi thao tác ghi trùng
Đáp án đúng: A

10. Khi event thanh toán bị giao lặp, biện pháp nào ngăn ghi tiền hai lần?
A. Tăng số lần retry để event thứ hai hoàn thành sớm
B. Dùng timestamp của consumer thay cho mã giao dịch
C. Dedupe event ID trước khi ghi nhận giao dịch lặp
D. Bỏ mọi kiểm tra nghiệp vụ nếu payload có đủ field
Đáp án đúng: C

11. Retry với backoff và jitter chủ yếu giảm tình huống nào?
A. Các event được lưu cùng timestamp trên một topic
B. Tránh nhiều consumer gọi lại dependency cùng một lúc
C. Các message không được đánh số thứ tự ở broker
D. Các consumer dùng nhiều version payload cùng lúc
Đáp án đúng: B

12. Một event liên tục không xử lý được do dữ liệu lỗi nên được xử lý thế nào?
A. Retry vô hạn trên cùng một luồng mà không có giới hạn
B. Đánh dấu thành công rồi bỏ mọi dấu vết của event
C. Xóa toàn bộ event trong topic trước thời điểm bị lỗi
D. Đưa vào DLQ để điều tra và xử lý lại có kiểm soát
Đáp án đúng: D

13. Consumer lag tăng dù broker vẫn nhận đều cho thấy vấn đề gì?
A. Producer đã tự động dừng gửi mọi bản tin mới
B. Consumer xử lý chậm hơn tốc độ event mới đến
C. Tất cả event đã được consumer xử lý trước hạn
D. Broker chắc chắn hết dung lượng lưu trữ ngay lập tức
Đáp án đúng: B

14. Khi gửi event ngay sau ghi DB bằng hai thao tác độc lập, rủi ro gì?
A. DB tự động phát lại event chưa đến consumer
B. Broker luôn rollback transaction của DB khi bị lỗi
C. Ghi DB thành công nhưng phát event thất bại
D. Mọi consumer đều nhận trạng thái mới trước commit
Đáp án đúng: C

15. Transactional outbox giúp đồng bộ dữ liệu và event bằng cách nào?
A. Ghi thay đổi và outbox record trong cùng transaction
B. Bắt mọi consumer khóa bảng outbox trong suốt thời gian đọc
C. Đổi tất cả request HTTP thành event mà không lưu trạng thái
D. Bỏ kiểm tra tính hợp lệ của command để tăng tốc publish
Đáp án đúng: A

16. Vì sao relay đọc outbox vẫn cần khả năng gửi lặp an toàn?
A. Relay có thể publish rồi lỗi trước khi đánh dấu đã gửi
B. Ghi outbox luôn bảo đảm broker chỉ nhận một bản tin
C. Consumer không thể đọc message có chung mã định danh
D. Broker tự biến mọi event trùng thành một transaction mới
Đáp án đúng: A

17. Saga phù hợp khi xử lý quy trình qua nhiều dịch vụ vì lý do nào?
A. Tạo một ACID transaction trải qua mọi DB khác nhau
B. Yêu cầu mọi dịch vụ viết trên một bảng khóa duy nhất
C. Loại bỏ hoàn toàn sự kiện và cơ chế xác nhận từng bước
D. Điều phối local transaction và bước bù qua dịch vụ
Đáp án đúng: D

18. Trong Saga, compensation thường có ý nghĩa gì?
A. Quay ngược mọi transaction DB như chưa từng commit
B. Xóa toàn bộ lịch sử event của quy trình đã bị lỗi
C. Dừng mọi consumer vĩnh viễn khi một dịch vụ thất bại
D. Thực hiện thao tác bù cho bước đã hoàn thành
Đáp án đúng: D

19. Khác biệt nổi bật giữa Saga choreography và orchestration là gì?
A. Choreography chỉ dùng REST; orchestration chỉ dùng SQL
B. Choreography buộc có một DB chung cho mọi dịch vụ
C. Choreography theo event; orchestration có bộ điều phối
D. Orchestration không thể thực hiện bước bù khi có lỗi
Đáp án đúng: C

20. Eventual consistency trong hệ thống hướng sự kiện nghĩa là gì?
A. Mọi consumer phải commit cùng thời điểm với producer
B. Các bản sao có thể lệch tạm rồi hội tụ về sau
C. Mọi lượt đọc luôn thấy ghi mới nhất trên tất cả dịch vụ
D. Mọi message sẽ biến mất ngay khi bất kỳ consumer đọc
Đáp án đúng: B

21. Vì sao cần correlation ID xuyên qua một luồng event?
A. Thay thế event ID để ngăn mọi message trùng lặp
B. Gắn log và trace của các bước trong cùng luồng
C. Đảm bảo broker tự duy trì thứ tự toàn bộ request
D. Tự xác định thời hạn lưu trữ của mỗi partition
Đáp án đúng: B

22. Khi thay đổi schema event, cách nào an toàn hơn cho consumer cũ?
A. Xóa field mà mọi consumer đang dùng không cần thông báo
B. Đổi ý nghĩa của field cũ nhưng giữ nguyên tên và type
C. Thêm field tùy chọn và kiểm tra tương thích ngược
D. Buộc mọi consumer cập nhật cùng một thời điểm bất kỳ
Đáp án đúng: C

23. Khi replay event cho projection, cần tránh rủi ro nào?
A. Consumer nhận thông điệp theo trình tự đã lưu
B. Projection tự tạo trạng thái từ chuỗi event đầu vào
C. Gây lại tác động ngoài như gửi email hoặc thu tiền
D. Nhật ký replay chứa số event đã được xử lý
Đáp án đúng: C

24. Khi nào event-driven có thể kém phù hợp hơn lời gọi đồng bộ đơn giản?
A. Nhiều hệ thống cần phản ứng độc lập với cùng một thay đổi
B. Luồng nhỏ cần đáp ứng tức thì, event tăng chi phí vận hành
C. Quy trình cần hấp thụ lưu lượng đột biến qua hàng đợi
D. Các consumer có nhịp xử lý và vòng đời triển khai khác nhau
Đáp án đúng: B

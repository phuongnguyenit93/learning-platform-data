1. Ý tưởng cốt lõi của CQRS trong thiết kế hệ thống là gì?
A. Chỉ cho phép đọc dữ liệu trực tiếp từ một bảng nghiệp vụ
B. Gộp mọi thao tác đọc ghi vào một interface duy nhất
C. Tách mô hình lệnh ghi và mô hình truy vấn đọc riêng
D. Buộc mỗi lệnh nghiệp vụ phải tạo một bản sao database
Đáp án đúng: C

2. Command trong CQRS thường biểu diễn loại yêu cầu nào?
A. Ý định thay đổi trạng thái theo quy tắc nghiệp vụ
B. Yêu cầu đọc danh sách mà không thay đổi trạng thái
C. Yêu cầu tải toàn bộ projection vào RAM của server
D. Yêu cầu tạo index mới cho kho dữ liệu truy vấn
Đáp án đúng: A

3. Query trong CQRS thông thường nên có đặc tính nào?
A. Tạo ra event ghi mới cho mọi lần khách hàng đọc
B. Trả dữ liệu có sẵn, không làm thay đổi trạng thái miền
C. Tự đồng bộ tất cả aggregate trước khi trả dữ liệu
D. Bắt buộc chạy cùng transaction với lệnh ghi gần nhất
Đáp án đúng: B

4. Đối với trang tổng hợp đơn hàng, read model có thể tối ưu thế nào?
A. Buộc query luôn đọc từng aggregate và join ở client
B. Để client phát lệnh cập nhật trước mỗi lượt truy vấn
C. Chỉ lưu bản sao thô của toàn bộ command nhận được
D. Tiền tính dữ liệu và lưu cấu trúc phù hợp màn hình
Đáp án đúng: D

5. Vì sao read model và write model của CQRS có thể khác cấu trúc?
A. Hai mô hình buộc phải có đúng cùng schema vật lý
B. Mô hình đọc không thể chứa dữ liệu đã tính trước
C. Mỗi mô hình tối ưu cho tải và nhu cầu riêng
D. Mô hình ghi chỉ dùng được với định dạng tài liệu JSON
Đáp án đúng: C

6. Khi projection cập nhật sau command qua event bất đồng bộ, điều gì xảy ra?
A. Query có thể thấy dữ liệu cũ trong thời gian ngắn
B. Truy vấn luôn thấy giá trị mới ngay trước khi commit
C. Mọi command buộc phải bị từ chối khi consumer chậm
D. Dữ liệu mới không thể truy vấn cho tới khi deploy lại
Đáp án đúng: A

7. Ứng dụng vừa đổi địa chỉ nhưng màn hình đọc còn giá trị cũ. Giải pháp UX nào phù hợp?
A. Tự cho rằng lệnh ghi đã thất bại dù được xác nhận
B. Hiển thị trạng thái đang đồng bộ hoặc phản hồi ghi hợp lệ
C. Bỏ kiểm tra phản hồi command để cập nhật màn hình ngẫu nhiên
D. Bắt client phát lệnh ghi liên tục đến khi màn hình đổi
Đáp án đúng: B

8. CQRS có bắt buộc sử dụng hai hệ quản trị cơ sở dữ liệu không?
A. Có; write phải dùng SQL còn read bắt buộc dùng NoSQL
B. Có; mỗi query phải được xử lý trên một máy độc lập
C. Không; hai mô hình có thể cùng tồn tại trong một database
D. Không; cả hai mô hình phải cùng một bảng và schema
Đáp án đúng: C

9. Khi ghi trạng thái và phát event cho projection, rủi ro dual-write là gì?
A. Mọi event đến broker đều được xử lý đúng một lần
B. Database đã ghi nhưng event chưa được phát đi
C. Client sẽ luôn đọc được projection mới ngay lập tức
D. Dữ liệu nghiệp vụ tự được khôi phục khi broker lỗi
Đáp án đúng: B

10. Transactional outbox thường giải quyết dual-write bằng cách nào?
A. Lưu thay đổi và outbox record trong cùng transaction
B. Ghi database rồi gọi broker mà không cần xử lý lỗi
C. Cho client tự công bố event thay cho write service
D. Bỏ commit dữ liệu cho tới khi mọi read model phản hồi
Đáp án đúng: A

11. Vì sao consumer cập nhật projection cần xử lý idempotent?
A. Vì mọi event chắc chắn mang bản ghi duy nhất mới
B. Vì projection không thể sử dụng khóa định danh
C. Broker có thể gửi lại event sau lỗi hoặc retry
D. Vì event luôn được phát theo thứ tự ngược thời gian
Đáp án đúng: C

12. Để tránh cộng doanh thu hai lần khi event phát lặp, nên làm gì?
A. Chỉ tăng số luồng consumer khi thấy thông báo trùng
B. Dedupe event ID hoặc áp dụng phép cập nhật idempotent
C. Bỏ mọi lần cập nhật projection trong thời gian cao điểm
D. Tự đổi khóa đơn hàng để mỗi lượt xử lý thành bản ghi mới
Đáp án đúng: B

13. Khi event cho cùng một aggregate đến lệch thứ tự, cần kiểm soát gì?
A. Chỉ độ dài của payload trước khi cập nhật projection
B. Chỉ số lượng partition đang được đặt cho một topic
C. Chỉ tên tiến trình consumer vừa đọc event mới nhất
D. Version hoặc thứ tự event khi cập nhật projection
Đáp án đúng: D

14. Nếu command vi phạm quy tắc tồn kho không âm, nơi nào nên từ chối?
A. Read model trong lần tìm kiếm tiếp theo của người dùng
B. API gateway sau khi projection đã phát ra dữ liệu
C. Dashboard giám sát khi phát hiện truy vấn bị chậm
D. Write model kiểm tra và từ chối trước khi commit trạng thái
Đáp án đúng: D

15. Khi hai command cùng sửa một aggregate, kỹ thuật nào hữu ích?
A. Optimistic concurrency với version chống ghi đè
B. Cứ ghi lần lượt theo thời điểm response đến client
C. Chỉ kiểm tra cache của mô hình đọc trước mỗi lệnh
D. Bỏ transaction và để consumer tự sửa mọi xung đột
Đáp án đúng: A

16. Mối quan hệ giữa CQRS và Event Sourcing được hiểu đúng ra sao?
A. CQRS luôn bắt buộc lưu mỗi thay đổi thành event bất biến
B. Event Sourcing chỉ tồn tại khi mọi query dùng cùng bảng ghi
C. CQRS tự động thay thế mọi cơ chế event và transaction
D. Có thể kết hợp, CQRS không bắt buộc event store
Đáp án đúng: D

17. Khi read model lỗi và mất dữ liệu, điều kiện nào giúp xây dựng lại?
A. Chỉ có cache RAM của một node đã bị khởi động lại
B. Chỉ còn bản build frontend mà người dùng tải về
C. Chỉ biết số query thành công trước lúc xảy ra lỗi
D. Có nguồn dữ liệu hoặc event tin cậy để tái dựng
Đáp án đúng: D

18. Để giảm gián đoạn khi rebuild projection lớn, cách nào phù hợp?
A. Dựng bản mới song song và chuyển đọc sau khi sẵn sàng
B. Xóa read model đang phục vụ trước khi bắt đầu dựng lại
C. Tắt toàn bộ lệnh ghi cho đến khi mọi index được tạo
D. Chuyển thẳng các event chưa kiểm tra vào production
Đáp án đúng: A

19. Khi handler projection liên tục lỗi vì một event không hợp lệ, cần làm gì?
A. Retry vô hạn không giới hạn mà không ghi nhận nguyên nhân
B. Đánh dấu toàn bộ event sau nó đều đã xử lý thành công
C. Xóa các event trước đó để consumer được bắt đầu lại
D. Quarantine event lỗi, cảnh báo và cho phép xử lý lại
Đáp án đúng: D

20. Chỉ số nào phản ánh độ trễ đồng bộ của mô hình đọc?
A. Projection lag giữa event ghi và lúc read model cập nhật
B. Số lượng dòng Java trong module tiếp nhận command
C. Thời gian biên dịch package ở máy developer local
D. Tổng số session người dùng đã đăng nhập trong ngày
Đáp án đúng: A

21. Trong hệ thống CQRS tải đọc lớn hơn tải ghi, khả năng mở rộng nào đáng cân nhắc?
A. Tăng writer node mỗi khi số truy vấn tăng một chút
B. Thêm command cho mọi query để đều phân bố lên broker
C. Scale phần read riêng với dịch vụ xử lý command
D. Giữ cả đọc và ghi trên một luồng tuần tự cố định
Đáp án đúng: C

22. Kiểm thử tính đúng đắn của projection nên tập trung vào điều gì?
A. Chỉ đo thời gian HTTP handshake của trang danh sách
B. Đối chiếu event đầu vào với trạng thái đọc được kỳ vọng
C. Chỉ so số lượng field của read model và write model
D. Chỉ kiểm tra tên index không trùng nhau trên các node
Đáp án đúng: B

23. Khi nào CQRS có thể làm hệ thống phức tạp không cần thiết?
A. Tải đọc vượt trội và cần read model chuyên biệt rõ
B. Tải đọc ghi đơn giản, không có nhu cầu mô hình tách
C. Nhiều màn hình cần dữ liệu kết hợp phức tạp khác nhau
D. Hệ thống có yêu cầu mở rộng đọc độc lập với ghi
Đáp án đúng: B

24. Trước khi triển khai CQRS, nhóm nên đánh giá trade-off nào?
A. Chỉ số lượng file cấu hình phát sinh từ dự án Java
B. Chỉ màu sắc của công cụ quan sát message broker
C. Lợi ích đọc nhanh với chi phí đồng bộ và vận hành
D. Chỉ số người tham gia review của từng pull request
Đáp án đúng: C

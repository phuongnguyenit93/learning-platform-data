Bạn sẽ xác định yêu cầu về độ bền, tính nhất quán và khả năng truy vấn trước khi chọn giải pháp persistence cho một ứng dụng như thế nào?
Bạn sẽ so sánh lưu trữ quan hệ, document, key-value và tệp dựa trên mô hình truy cập dữ liệu ra sao?
Bạn sẽ chuyển các quy tắc nghiệp vụ thành thực thể, thuộc tính và quan hệ trong một mô hình dữ liệu như thế nào?
Bạn sẽ phân biệt mô hình dữ liệu logic và lược đồ lưu trữ vật lý khi thiết kế hệ thống ra sao?
Bạn sẽ quyết định khi nào chuẩn hóa dữ liệu và khi nào phi chuẩn hóa để tối ưu truy vấn như thế nào?
Bạn sẽ lựa chọn khóa tự nhiên hay khóa thay thế cho một thực thể dựa trên tính ổn định và khả năng tích hợp ra sao?
Bạn sẽ thiết kế các ràng buộc unique, check và not-null để bảo vệ bất biến nghiệp vụ như thế nào?
Bạn sẽ thiết lập khóa ngoại và chính sách xóa dữ liệu liên quan để tránh bản ghi mồ côi ra sao?
Bạn sẽ phân biệt null, giá trị mặc định và giá trị chưa được ghi nhận trong lược đồ dữ liệu như thế nào?
Bạn sẽ xây dựng mô hình lưu lịch sử chỉnh sửa khi yêu cầu truy xuất trạng thái tại một thời điểm cũ ra sao?
Bạn sẽ xác định ranh giới giữa domain model và persistence model trong kiến trúc Java như thế nào?
Bạn sẽ thiết kế repository hoặc cổng truy cập dữ liệu để mã nghiệp vụ ít phụ thuộc vào công nghệ lưu trữ ra sao?
Bạn sẽ lựa chọn dùng ORM, SQL trực tiếp hay công cụ truy vấn khác dựa trên mức độ kiểm soát và độ phức tạp như thế nào?
Bạn sẽ quản lý vòng đời entity và ngữ cảnh persistence để tránh cập nhật dữ liệu ngoài ý muốn ra sao?
Bạn sẽ quyết định một use case cần bao nhiêu giao dịch và đặt ranh giới giao dịch ở đâu như thế nào?
Bạn sẽ giải thích tính nguyên tử, nhất quán, cô lập và bền vững của giao dịch qua ví dụ chuyển tiền ra sao?
Bạn sẽ phân tích những trạng thái trung gian nào cần được ngăn chặn nếu một giao dịch thất bại giữa chừng như thế nào?
Bạn sẽ phân biệt dirty read, non-repeatable read và phantom read qua những tình huống truy vấn nào?
Bạn sẽ lựa chọn mức cô lập giao dịch phù hợp khi cân bằng tính chính xác, độ trễ và khả năng tranh chấp ra sao?
Bạn sẽ nhận diện và ngăn lost update khi hai yêu cầu cùng sửa một bản ghi như thế nào?
Bạn sẽ áp dụng optimistic locking cho dữ liệu ít tranh chấp và xử lý xung đột phiên bản ra sao?
Bạn sẽ sử dụng pessimistic locking trong trường hợp nào và hạn chế thời gian giữ khóa như thế nào?
Bạn sẽ điều tra nguyên nhân deadlock và thiết kế retry an toàn sau khi giao dịch bị hủy ra sao?
Bạn sẽ giải thích khác biệt giữa tính nhất quán tại một bản sao đọc và tính nhất quán của giao dịch ghi như thế nào?
Bạn sẽ thiết kế thao tác ghi có tính idempotent để retry sau timeout không tạo dữ liệu trùng như thế nào?
Bạn sẽ xác định điều kiện tạo chỉ mục dựa trên tần suất truy vấn, độ chọn lọc và kích thước bảng ra sao?
Bạn sẽ sắp xếp thứ tự cột trong chỉ mục kết hợp để phục vụ bộ lọc và sắp xếp dữ liệu như thế nào?
Bạn sẽ phân tích khi nào chỉ mục có thể giúp truy vấn bao phủ mà không phải đọc thêm bản ghi gốc ra sao?
Bạn sẽ đánh giá chi phí của quá nhiều chỉ mục đối với ghi dữ liệu, cập nhật và dung lượng lưu trữ như thế nào?
Bạn sẽ đọc execution plan và đối chiếu số hàng ước lượng với thực tế để tìm truy vấn chậm ra sao?
Bạn sẽ xử lý vấn đề N+1 query khi truy xuất quan hệ bằng ORM như thế nào?
Bạn sẽ lựa chọn phân trang bằng offset hay cursor khi dữ liệu liên tục thay đổi và lượng bản ghi tăng lớn ra sao?
Bạn sẽ thiết kế truy vấn tổng hợp và chiến lược gom lô để giảm số lần trao đổi với cơ sở dữ liệu ra sao?
Bạn sẽ quyết định dữ liệu nào có thể cache và thiết lập cơ chế vô hiệu hóa cache sau cập nhật như thế nào?
Bạn sẽ định kích thước connection pool theo tải, thời gian chờ và giới hạn kết nối của cơ sở dữ liệu ra sao?
Bạn sẽ phân biệt lỗi kết nối tạm thời, timeout và lỗi ràng buộc dữ liệu để lựa chọn cách xử lý phù hợp như thế nào?
Bạn sẽ xác định thao tác nào an toàn để retry và cách tránh nhân đôi tác dụng phụ khi trạng thái commit chưa rõ ra sao?
Bạn sẽ phối hợp thay đổi dữ liệu với việc phát sự kiện sang dịch vụ khác khi không thể dùng một giao dịch chung như thế nào?
Bạn sẽ phân tích giới hạn của giao dịch cục bộ khi ứng dụng ghi vào nhiều nguồn dữ liệu hoặc nhiều dịch vụ ra sao?
Bạn sẽ cân nhắc đồng bộ và nhất quán cuối cùng khi thiết kế các bản sao đọc hoặc hệ thống phân tán như thế nào?
Bạn sẽ lập kế hoạch nâng cấp schema mà phiên bản ứng dụng cũ và mới phải chạy đồng thời ra sao?
Bạn sẽ thiết kế migration thêm hoặc đổi tên cột theo các bước tương thích và có thể quay lui như thế nào?
Bạn sẽ thực hiện backfill dữ liệu lớn mà không khóa bảng kéo dài hoặc gây gián đoạn dịch vụ như thế nào?
Bạn sẽ xác minh dữ liệu sau migration bằng những kiểm tra tổng số, ràng buộc và đối chiếu giá trị như thế nào?
Bạn sẽ áp dụng nguyên tắc đặc quyền tối thiểu, xác thực và mã hóa để bảo vệ dữ liệu lưu trữ ra sao?
Bạn sẽ thiết kế chính sách lưu giữ, xóa và ghi log truy cập cho dữ liệu cá nhân hoặc dữ liệu nhạy cảm như thế nào?
Bạn sẽ xác định mục tiêu RPO và RTO để xây dựng lịch sao lưu và quy trình khôi phục dữ liệu như thế nào?
Bạn sẽ tổ chức diễn tập phục hồi sau sự cố để kiểm tra bản sao lưu, thứ tự khởi động và tính nhất quán dữ liệu ra sao?
Bạn sẽ xây dựng kiểm thử giao dịch đồng thời và đo hiệu năng dưới tải để phát hiện lỗi cô lập và điểm nghẽn như thế nào?
Bạn sẽ xử lý tình huống sau triển khai, truy vấn chậm tăng mạnh và bản migration mới đồng thời gây lỗi ghi dữ liệu như thế nào?

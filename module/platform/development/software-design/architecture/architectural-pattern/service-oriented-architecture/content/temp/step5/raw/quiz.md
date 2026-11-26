Khi tách hệ thống theo SOA, ranh giới service nên dựa vào gì?
A. Mỗi class Java thành một dịch vụ độc lập
B. Mỗi bảng dữ liệu thành một endpoint riêng
C. Mỗi giao diện web thành một cơ sở dữ liệu
D. Năng lực nghiệp vụ với hợp đồng rõ ràng
Đáp án đúng: D

Hợp đồng dịch vụ (service contract) cần công bố những gì?
A. Danh sách câu SQL được gọi trong mỗi operation
B. Operation, schema thông điệp và quy tắc lỗi
C. Cấu trúc folder source và tên framework server
D. Chi tiết thread pool và class triển khai bên trong
Đáp án đúng: B

Lựa chọn nào tăng loose coupling giữa consumer và service?
A. Consumer dựa vào hợp đồng thay vì code nội bộ
B. Consumer gắn vào phiên bản class Java nội bộ
C. Consumer đọc trực tiếp bảng của service khác
D. Consumer import adapter persistence của provider
Đáp án đúng: A

Trong hệ sinh thái SOAP, WSDL chủ yếu mô tả điều gì?
A. Các index vật lý và ràng buộc của database
B. Các operation, message và binding của service
C. Các Docker image cần cài cho phía consumer
D. Các sự kiện đã ghi trong hàng đợi nội bộ
Đáp án đúng: B

Khi thiết kế REST qua HTTP, cách tổ chức nào phù hợp?
A. Dồn mọi thao tác vào một phương thức GET
B. Bỏ HTTP status để chỉ dùng body tùy ý
C. Dùng URI resource và phương thức HTTP có nghĩa
D. Nhúng schema database thật vào từng URL
Đáp án đúng: C

Orchestration giữa nhiều dịch vụ có đặc điểm nào?
A. Một coordinator điều phối thứ tự các bước
B. Không có bên nào biết trạng thái workflow
C. Các service độc lập phản ứng sự kiện tự do
D. Mọi service phải cùng dùng một database
Đáp án đúng: A

Choreography phối hợp các service chủ yếu bằng cách nào?
A. Một central controller gọi tuần tự các service
B. Mọi service đọc biến global trong cùng process
C. Mỗi service phản ứng theo sự kiện đã công bố
D. Mỗi service gọi trực tiếp DB của service khác
Đáp án đúng: C

ESB có giá trị khi tích hợp nhiều hệ thống legacy vì điều gì?
A. Loại bỏ mọi chi phí truyền nhận thông điệp
B. Bắt từng ứng dụng phải dùng cùng ngôn ngữ
C. Thay hết mọi service contract bằng bảng chung
D. Hỗ trợ routing và chuyển đổi giao thức
Đáp án đúng: D

Nếu dồn mọi quy tắc nghiệp vụ vào ESB, rủi ro thường thấy là gì?
A. Không còn phải đo hiệu năng tích hợp
B. Tăng coupling và tạo nút cổ chai tại bus
C. Service tự chủ hơn mà không cần governance
D. Dịch vụ không còn cần thay đổi contract
Đáp án đúng: B

Khi tiến hóa API, cách nào giúp consumer cũ tiếp tục hoạt động?
A. Đổi tên required field mà không báo trước
B. Xóa operation cũ ngay sau khi phát hành
C. Giữ backward compatibility hoặc hỗ trợ version
D. Buộc client luôn đọc schema của server
Đáp án đúng: C

Một service có chức năng tạo giao dịch cần kiểm soát điều gì?
A. Tin tưởng mọi request trong mạng nội bộ
B. Ghi token truy cập nguyên văn ra log
C. Chỉ kiểm soát nút bấm ở phía giao diện
D. Xác thực caller và phân quyền thao tác
Đáp án đúng: D

Workflow gồm thanh toán và giao hàng ở hai service không có transaction chung nên làm gì?
A. Bỏ ghi lại bước đã hoàn thành trong workflow
B. Giả định database tự rollback cả hai service
C. Gọi retry vô hạn cho mọi lời gọi thất bại
D. Theo dõi trạng thái và hành động bù khi lỗi
Đáp án đúng: D

Consumer-driven contract test hữu ích để xác nhận điều gì?
A. Provider còn đáp ứng nhu cầu consumer đã công bố
B. Provider dùng đúng tên class private như trước
C. Consumer có thể đọc trực tiếp bảng của provider
D. Hai service bắt buộc dùng chung thư viện ORM
Đáp án đúng: A

Tách một nghiệp vụ thành quá nhiều service rất nhỏ có thể gây gì?
A. Không còn cần thiết kế contract giao tiếp
B. Loại bỏ chi phí quản trị phiên bản service
C. Tăng round-trip mạng và phụ thuộc giữa service
D. Giảm mọi lỗi partial failure của hệ thống
Đáp án đúng: C

Service A ghi trực tiếp bảng sở hữu của service B gây vấn đề gì?
A. Cho phép B tự đổi schema mà không ảnh hưởng A
B. Làm chặt coupling vào schema nội bộ của B
C. Tự bảo đảm hợp đồng API của B tương thích
D. Bảo đảm giao dịch phân tán trở nên nguyên tử
Đáp án đúng: B

Khi một request đi qua nhiều service, nên thu thập tín hiệu nào?
A. Correlation ID và trace theo luồng request
B. Chỉ số lượng phương thức public từng module
C. Chỉ log từ request đầu tiên tại gateway
D. Chỉ mức sử dụng RAM ở một server bất kỳ
Đáp án đúng: A

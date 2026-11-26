Nhóm kiểm thử service Java dùng database H2 trên laptop nhưng production chạy PostgreSQL; một truy vấn có cú pháp đặc thù PostgreSQL vượt qua unit test mà thất bại khi triển khai.
Đội backend dùng Docker Compose để khởi động PostgreSQL và Redis; test bắt đầu ngay sau khi container được tạo, trong khi database vẫn đang phục hồi dữ liệu nên kết nối ban đầu bị từ chối.
Trong bộ integration test JUnit, service HTTP phụ thuộc Kafka được khởi động trước broker; health check HTTP trả thành công dù tác vụ đăng ký consumer chưa sẵn sàng, khiến test nhận thiếu sự kiện.
Nhóm dùng Testcontainers tạo database tạm cho mỗi lượt test, nhưng lớp cấu hình Spring vẫn trỏ tới địa chỉ PostgreSQL trên máy phát triển nên CI đôi khi sửa nhầm database chia sẻ.
Một service chạy trong Docker Compose cố kết nối database qua localhost; ứng dụng chạy được khi khởi động trực tiếp trên host nhưng không kết nối được từ bên trong container.
Dự án Java dùng Testcontainers với cổng database được gán ngẫu nhiên; một phần cấu hình test lại cố định cổng 5432 và thất bại khi nhiều bộ test chạy song song.
Đội phát triển gắn image postgres:latest cho môi trường test; cùng commit cho kết quả khác sau khi registry cập nhật image, khiến lỗi xuất hiện mà không có thay đổi source.
Nhóm thay đổi bảng trong migration SQL, nhưng môi trường kiểm thử tận dụng volume cũ đã có schema; các bài test xanh trên máy một thành viên và đỏ khi chạy trên máy sạch.
Testcontainers khởi tạo database cho mỗi lớp JUnit, còn phần khởi tạo dữ liệu giả định schema được tạo một lần cho cả suite; lớp chạy sau bị lỗi vì bảng không tồn tại trong container mới.
Trong môi trường tích hợp, dữ liệu seed có email khách hàng trùng với khóa unique ở lần chạy trước; test đầu tiên PASS nhưng chạy lại toàn bộ suite lập tức gặp lỗi trùng khóa.
Nhóm đặt dữ liệu kiểm thử vào script khởi tạo container nhưng script chỉ chạy khi database hoàn toàn mới; lập trình viên giữ volume cũ nên thêm record seed không có hiệu lực.
Một bộ test tạo khách hàng, hóa đơn và khoản thanh toán liên quan, rồi chỉ xóa bảng hóa đơn sau khi kết thúc; test sau gặp khóa ngoại và dữ liệu trạng thái từ ca trước.
Trong JUnit, test ghi dữ liệu trong transaction thử nghiệm rồi rollback, nhưng yêu cầu HTTP chạy trên server và transaction khác vẫn commit bản ghi; lần chạy tiếp theo nhận dữ liệu thừa.
Đội tăng tốc suite bằng chạy JUnit song song, nhưng mọi test dùng chung accountId và cùng chỉnh sửa số dư; kết quả phụ thuộc vào thứ tự các ca đang chạy.
Trong Docker Compose, hai pipeline CI trên cùng host dùng cùng project name và tên container tĩnh; một pipeline dọn tài nguyên làm database của pipeline còn lại bị dừng.
Nhóm chạy Testcontainers song song trên cùng Docker daemon hạn chế CPU/RAM; một số test đợi startup quá hạn khi nhiều image nặng khởi động cùng lúc.
Một bộ test cần MongoDB và Redis đồng thời; mỗi fixture tạo hai container riêng cho từng phương thức JUnit khiến thời gian khởi động vượt quá thời gian cho phép của CI.
Đội bật tái sử dụng container để giảm thời gian test địa phương; khi một test thay đổi cấu hình server trong container, ca khác sử dụng lại cấu hình đó và trả kết quả bất thường.
Ứng dụng Java lấy JDBC URL từ biến môi trường; khi chạy test trong IDE, biến còn sót trỏ tới database staging và suite xóa các bản ghi thuộc môi trường dùng chung.
Testcontainers được khởi động trong JUnit extension nhưng một bean của ứng dụng đọc giá trị kết nối trước khi extension cập nhật cấu hình động; service khởi động với URL không hợp lệ.
Một dự án sử dụng nhiều profile Spring cho test, nhưng một lớp gắn nhầm profile production và khởi tạo connector gửi email thật trong khi kiểm thử quy trình đăng ký.
Nhóm dùng MockServer thay dịch vụ thanh toán, nhưng không đặt lại expectation sau mỗi bài test; test cho giao dịch thành công nhận phản hồi 500 còn sót lại từ ca thất bại.
Ứng dụng giao hàng cần xác minh tương tác với bản API đối tác thật ở môi trường sandbox, nhưng các bài CI thường xuyên lỗi do sandbox bị giới hạn số request và dữ liệu tự động hết hạn.
Trong bộ test Kafka, consumer group ID cố định giữa các lượt chạy; bài test mới không nhận sự kiện cũ như dự kiến vì offset đã được commit từ lần chạy trước.
Nhóm phát sự kiện vào topic Kafka dùng chung cho nhiều lớp kiểm thử; một consumer nhận cả dữ liệu từ lớp khác nên số sự kiện quan sát được cao hơn dữ liệu vừa gửi.
Ứng dụng xử lý công việc nền chạy ngay trong môi trường test; assertion thực hiện sau khi ghi hàng đợi nhưng trước khi worker hoàn tất, khiến bài test lúc PASS lúc FAIL.
Nhóm đang đợi asynchronous result bằng một khoảng sleep cố định hai giây; trên máy CI tải cao, tác vụ cần lâu hơn nên nhiều ca fail ngẫu nhiên dù nghiệp vụ đúng.
Trong service phân phối lịch, test dựa trên ngày giờ thực của hệ điều hành; khi pipeline chạy gần nửa đêm hoặc khác múi giờ, dữ liệu kỳ vọng không còn khớp.
Một ứng dụng tạo báo cáo theo locale của máy chạy; trên Windows developer nhận dấu phẩy thập phân, còn Linux CI xuất dấu chấm và assertion về nội dung file thất bại.
Nhóm tạo fixture bằng truy vấn SQL nhiều bước nhưng một bước thất bại giữa chừng; các bản ghi đã chèn vẫn còn và ca test tiếp theo không còn bắt đầu từ trạng thái sạch.
Bộ integration test phụ thuộc chứng chỉ HTTPS tự ký của dịch vụ mô phỏng; test chạy được trên máy có truststore đã chỉnh nhưng bị lỗi TLS trên runner mới của CI.
Trong pipeline kiểm thử, Testcontainers cần quyền truy cập Docker daemon; runner dùng môi trường không cung cấp daemon nên test báo lỗi khởi tạo container trước khi thực hiện assertion.
Đội kiểm thử tải một image lớn từ registry công khai cho mỗi run CI; khi registry giới hạn tốc độ hoặc đường truyền chậm, pipeline không khởi động được môi trường phụ thuộc.
Ứng dụng dùng Redis TTL để kiểm thử hết hạn phiên; sau khi restart Redis giữa suite, khóa thử nghiệm mất sớm và kết quả bị nhầm với hành vi hết hạn đúng thời gian.
Nhóm cần kiểm tra quy trình khôi phục khi database bị ngắt kết nối nhưng môi trường Docker Compose tự khởi động lại service quá nhanh; bài test khó phân biệt lỗi tạm thời với lỗi mất dữ liệu.
Trong một bài kiểm thử nhiều container, dịch vụ A khởi động và lập tức gọi dịch vụ B qua DNS nội bộ, trong khi B mới mở cổng nhưng chưa đăng ký dữ liệu; request đầu thất bại.
Nhóm chạy kiểm thử file upload với thư mục bind mount trên máy Windows; trên Linux CI quyền ghi và ký tự đường dẫn khác khiến tài liệu đã upload không đọc lại được.
Sau khi hoàn thành suite, một lớp test thất bại ở bước setup nên phương thức cleanup thông thường không được gọi; nhiều container và file tạm tiếp tục chiếm tài nguyên trên runner.
Đội phát triển muốn chụp log container khi test thất bại, nhưng pipeline xóa môi trường ngay lúc teardown; báo cáo chỉ có stack trace phía Java và thiếu bằng chứng từ dịch vụ phụ thuộc.
Một hệ thống nhiều service thử nghiệm deploy cục bộ với Docker Compose và Testcontainers ở các lớp khác nhau; mỗi nhóm tự định nghĩa dữ liệu và phiên bản phụ thuộc khiến cùng luồng nghiệp vụ cho kết quả khác nhau.

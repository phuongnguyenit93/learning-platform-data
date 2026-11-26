Bạn xác định mục tiêu và phạm vi được phép của một đợt kiểm thử bảo mật ứng dụng như thế nào?
Trước khi chạy công cụ kiểm thử, bạn cần thống nhất những quy tắc bảo vệ dữ liệu và giới hạn tác động nào?
Bạn lựa chọn tài sản, điểm vào và ranh giới tin cậy để xây dựng threat model ra sao?
Bạn sẽ biến một nguy cơ trong threat model thành ca kiểm thử có đầu vào và kết quả kỳ vọng như thế nào?
Những yếu tố nào giúp bạn ưu tiên ca kiểm thử bảo mật theo mức ảnh hưởng và khả năng khai thác?
Bạn xác định sự khác nhau giữa phát hiện lỗ hổng, xác minh lỗ hổng và đánh giá rủi ro như thế nào?
Bạn sẽ lập ma trận tài khoản thử nghiệm theo vai trò và mức đặc quyền để kiểm tra xác thực ra sao?
Khi một ứng dụng hỗ trợ đăng nhập nhiều yếu tố, bạn kiểm tra các nhánh đăng nhập và khôi phục tài khoản thế nào?
Bạn thiết kế ca kiểm thử xử lý thông báo lỗi đăng nhập để tránh tiết lộ sự tồn tại của tài khoản ra sao?
Bạn xác minh cơ chế khóa tạm thời hoặc giới hạn tốc độ đăng nhập có cân bằng giữa bảo mật và khả năng sử dụng như thế nào?
Bạn kiểm tra vòng đời session từ lúc tạo, làm mới, hết hạn đến đăng xuất bằng các tình huống nào?
Khi người dùng đổi mật khẩu hoặc bị thu hồi quyền, bạn xác minh token và session cũ được xử lý ra sao?
Bạn phân biệt kiểm tra xác thực với kiểm tra phân quyền qua ví dụ API nghiệp vụ nào?
Bạn thiết kế ma trận quyền cho các thao tác đọc, tạo, sửa và xóa tài nguyên theo vai trò như thế nào?
Khi hai tài khoản cùng vai trò sở hữu dữ liệu khác nhau, bạn kiểm thử phân quyền theo đối tượng ra sao?
Bạn xác minh giới hạn đặc quyền giữa người dùng thông thường và quản trị viên bằng những ca kiểm thử nào?
Trong ứng dụng đa tenant, bạn kiểm chứng request không thể truy cập dữ liệu thuộc tenant khác bằng cách nào?
Bạn sẽ kiểm tra phân quyền ở lớp API khi giao diện đã ẩn một chức năng khỏi người dùng không đủ quyền như thế nào?
Những trường hợp nào khiến việc tin vào trường userId hoặc role do client gửi lên trở nên nguy hiểm?
Bạn thiết kế ca kiểm thử kiểm soát input để phát hiện xử lý thiếu an toàn với dữ liệu bất thường như thế nào?
Khi ứng dụng ghép chuỗi vào truy vấn dữ liệu, bạn lựa chọn bằng chứng nào để đánh giá nguy cơ injection trong môi trường kiểm thử?
Bạn kiểm tra việc encode dữ liệu hiển thị trên trang web để giảm nguy cơ XSS bằng cách nào?
Bạn xác minh chức năng tải lên file áp dụng đúng quy tắc loại file, kích thước và vị trí lưu trữ ra sao?
Nếu API chấp nhận URL do người dùng cung cấp, bạn kiểm thử giới hạn truy cập tài nguyên nội bộ theo cách an toàn nào?
Bạn thiết kế kiểm thử giới hạn kích thước payload, số yêu cầu và timeout để đánh giá khả năng chống lạm dụng API ra sao?
Khi một thao tác thay đổi trạng thái được gửi lại nhiều lần, bạn kiểm tra chống replay và tính idempotent như thế nào?
Bạn sẽ đánh giá nguy cơ CSRF đối với chức năng dùng cookie xác thực qua các tình huống nào?
Bạn kiểm tra chính sách CORS có phù hợp với các origin và credential được phép như thế nào?
Bạn xác minh thông tin nhạy cảm không xuất hiện trong URL, response, log hoặc thông báo lỗi ra sao?
Bạn kiểm tra mã hóa khi truyền và xử lý chứng chỉ TLS trong môi trường thử nghiệm như thế nào?
Khi dữ liệu nhạy cảm được lưu trên database hoặc backup, bạn đánh giá yêu cầu mã hóa và quyền đọc như thế nào?
Bạn lựa chọn cách kiểm thử luồng quên mật khẩu mà không gửi thông tin tới tài khoản ngoài phạm vi ra sao?
Bạn kiểm tra secret, khóa API và thông tin xác thực trong cấu hình triển khai bằng những nguyên tắc nào?
Khi phát hiện quyền truy cập hạ tầng quá rộng, bạn xác minh tác động và đề xuất giới hạn đặc quyền như thế nào?
Bạn phân biệt vai trò của SAST, DAST và SCA trong quy trình phát hiện vấn đề bảo mật ra sao?
Bạn sẽ diễn giải một cảnh báo SAST để tìm đường dữ liệu và đánh giá khả năng xảy ra lỗi thực tế như thế nào?
Khi công cụ DAST tạo cảnh báo, bạn chọn bước xác minh thủ công an toàn nào trước khi lập báo cáo?
Bạn kiểm tra dependency bắc cầu và thông tin phiên bản để đánh giá một phát hiện SCA ra sao?
Một SBOM giúp bạn xác định thư viện bị ảnh hưởng và phạm vi ứng dụng cần kiểm tra lại như thế nào?
Bạn sẽ thiết kế fuzzing với giới hạn tài nguyên và tập dữ liệu kiểm thử để phát hiện lỗi xử lý đầu vào ra sao?
Khi fuzzing gây crash, bạn phân biệt lỗi do harness với lỗi của ứng dụng bằng bằng chứng nào?
Bạn tổ chức dữ liệu thử nghiệm để không đưa thông tin cá nhân thật vào các công cụ quét bảo mật như thế nào?
Bạn xác định mức nghiêm trọng của một phát hiện dựa trên điều kiện khai thác, tác động và biện pháp bảo vệ hiện có ra sao?
Bạn viết báo cáo phát hiện bảo mật để người sửa hiểu vị trí, bằng chứng, phạm vi và cách xác minh như thế nào?
Khi công cụ báo false positive, bạn ghi lại lý do bác bỏ và cách tránh lặp lại đánh giá không cần thiết ra sao?
Bạn xây dựng ca kiểm thử hồi quy sau bản vá để xác nhận lỗ hổng được sửa mà chức năng khác vẫn hoạt động như thế nào?
Bạn sẽ tích hợp kiểm tra SAST, SCA và các phép thử phù hợp vào CI/CD với tiêu chí chặn phát hành ra sao?
Khi một bản build có cảnh báo bảo mật mới nhưng chưa đủ bằng chứng, bạn tổ chức quy trình xác minh và quyết định xử lý như thế nào?
Bạn kiểm tra tính toàn vẹn, nguồn gốc và quyền phát hành của artifact trong chuỗi cung ứng phần mềm ra sao?
Sau khi phát hành, bạn đánh giá hiệu quả chương trình kiểm thử bảo mật qua tỷ lệ sửa, tái diễn lỗi và thời gian khắc phục như thế nào?

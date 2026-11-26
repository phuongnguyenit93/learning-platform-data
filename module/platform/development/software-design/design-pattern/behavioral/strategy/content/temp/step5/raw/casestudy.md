Trong hệ thống giao hàng, lớp tính phí có một chuỗi if-else theo đơn vị vận chuyển và loại hàng; mỗi lần ký thêm đối tác, nhóm phải sửa logic đang dùng cho các đối tác cũ dù quy trình đặt đơn không đổi.
Một cửa hàng trực tuyến áp dụng các cách tính chiết khấu cho hội viên, khách doanh nghiệp và khách có voucher; chính sách mới có hiệu lực giữa ngày nhưng service vẫn chọn công thức theo cấu hình lúc khởi động.
Ứng dụng tính thuế cho nhiều quốc gia dùng một phương thức khổng lồ chứa từng biểu thuế; khi một nước đổi ngưỡng thuế, regression ở thị trường khác cũng xuất hiện dù không liên quan.
Nền tảng thanh toán chọn cổng xử lý dựa trên loại thẻ, chi phí và tình trạng hoạt động; khi cổng mặc định ngừng phục vụ, Context vẫn tiếp tục gọi đúng một nhánh đã chọn từ đầu phiên.
Ứng dụng sao lưu hỗ trợ nén nhanh cho dữ liệu thời gian thực và nén tối đa cho lưu trữ dài hạn; đội phát triển buộc người dùng chọn lại toàn bộ quy trình sao lưu khi chỉ muốn đổi thuật toán nén.
Một công cụ tìm kiếm cho phép xếp hạng theo độ liên quan, thời gian và mức phổ biến; cùng truy vấn trả kết quả khác nhau khi người dùng đổi lựa chọn nhưng lớp xử lý vẫn lưu bộ so sánh của lần trước.
Dịch vụ chống gian lận vận hành nhiều mô hình chấm điểm theo nhóm giao dịch; những người bảo trì không biết điều kiện nào đang chọn mô hình nào vì quy tắc chọn bị rải trong các controller.
Hệ thống đồng bộ dữ liệu dùng chính sách thử lại khác nhau cho API thanh toán và API danh mục; một thay đổi để tăng số lần retry cho danh mục vô tình làm gửi lệnh thanh toán lặp nhiều lần.
Ứng dụng đăng nhập cần xác minh mật khẩu cũ và mật khẩu theo tiêu chuẩn mới; hai thuật toán tạo ra kết quả không thể so sánh trực tiếp trong khi phần điều khiển đăng nhập giả định một đầu ra giống nhau.
Nền tảng báo cáo cho phép xuất CSV, JSON và XML; mỗi nhánh tự xử lý bộ lọc dữ liệu và phân quyền trước khi chuyển định dạng, khiến một loại file bỏ sót điều kiện ẩn thông tin cá nhân.
Một dịch vụ thông báo gửi cùng thông điệp qua email, SMS hoặc ứng dụng di động; khi người dùng đổi kênh ưu tiên lúc chạy, hệ thống vẫn dùng kênh đã lựa chọn cho người dùng trước đó.
Nhóm tích hợp nhà cung cấp vận chuyển nhận trạng thái qua ba giao thức khác nhau; Context mong một kết quả vận chuyển thống nhất nhưng từng implementation trả ý nghĩa lỗi theo cách riêng.
Ứng dụng phân tích log phải chọn cách tách trường theo định dạng nguồn; bộ đọc mới được thêm vào nhưng nơi lựa chọn vẫn dùng danh sách cố định khiến định dạng hợp lệ rơi vào nhánh không được hỗ trợ.
Trong chương trình giới thiệu sản phẩm, chiến lược đề xuất dựa trên lịch sử và chiến lược theo sản phẩm phổ biến được thay đổi theo tỷ lệ thử nghiệm; cùng người dùng đôi khi thấy hai bộ gợi ý trong một phiên.
Đội tài chính sử dụng các phương pháp làm tròn khác nhau theo đồng tiền; một strategy làm tròn trước khi tính thuế còn strategy khác làm tròn sau, khiến tổng hóa đơn không đáp ứng hợp đồng chung.
Một hệ thống chấm điểm rủi ro muốn thay thuật toán theo mức giao dịch ngay lúc chạy; đối tượng Context được tạo từ đầu request nên không phản ánh điều kiện được cập nhật sau bước xác minh.
Dịch vụ đặt vé áp dụng chính sách tính phí hủy theo loại vé và thời gian còn lại; lớp giao diện chứa cả quy tắc chọn lẫn công thức và các luồng batch phải sao chép điều kiện này.
Trong ứng dụng đa tenant, từng khách hàng doanh nghiệp chọn cách xếp hạng ticket riêng; biến cấu hình toàn cục làm chiến lược của tenant vừa đăng nhập được dùng cho request của tenant khác.
Một bộ xử lý dữ liệu chọn chiến lược chuẩn hóa qua mã cấu hình; khi mã không tồn tại, chương trình âm thầm dùng thuật toán mặc định và dữ liệu đầu ra thay đổi mà không có cảnh báo.
Nhóm cấu hình chiến lược từ file ngoài, nhưng quá trình triển khai quên đăng ký implementation mới trong nơi lựa chọn; code biên dịch thành công mà yêu cầu mới chỉ lỗi khi chạy.
Ứng dụng sử dụng một instance chiến lược tính ưu đãi cho nhiều request song song; implementation lại giữ tổng tiền của request gần nhất trong field và làm kết quả khách hàng bị lẫn.
Một thuật toán sắp xếp có trạng thái cache kết quả giữa các lần gọi; Context dùng lại cùng strategy cho dữ liệu khác nhưng cache không gắn với khóa của tập dữ liệu hiện tại.
Trong Java, nhóm dùng lambda để biểu diễn công thức định giá nhưng lambda giữ tham chiếu đến Map tỷ giá có thể thay đổi; hai request chạy cùng mã nhưng tính tổng theo các thời điểm khác nhau.
Nhóm chọn enum để đại diện các cách tính phí nhưng một biến thể cần kết nối API cấu hình bên ngoài; cách tổ chức hiện tại khó xác định vòng đời và phụ thuộc của riêng biến thể đó.
Trong hệ thống xác minh hồ sơ, strategy A ném ngoại lệ khi thiếu giấy tờ còn strategy B trả kết quả từ chối; lớp gọi không phân biệt lỗi kỹ thuật và kết quả nghiệp vụ khi thay thế strategy.
Một hệ thống nhập dữ liệu định nghĩa hợp đồng xử lý bản ghi nhưng strategy của đối tác mới tự ghi xuống database; việc thay strategy làm xuất hiện tác dụng phụ ngoài dự kiến ở chế độ xem trước.
Phần mềm kế toán có hai cách tính khấu hao cùng dùng interface; một implementation trả giá trị theo tháng, implementation khác theo năm mà Context không nhận biết khác biệt về đơn vị.
Đội thiết kế một hợp đồng chiến lược với mười phương thức cho nhiều kiểu thanh toán; mỗi loại chỉ dùng vài phương thức nên các implementation liên tục ném lỗi không hỗ trợ ở runtime.
Một ứng dụng chấp nhận nhiều thuật toán xác thực chữ ký; strategy mới trả true khi thông tin khóa không có trong request, vi phạm kỳ vọng chung mà Context dựa vào.
Nhóm sản phẩm muốn dùng đồng thời hai chính sách ưu đãi thay vì chỉ chọn một; lớp Context hiện giả định đúng một thuật toán và chưa rõ cách phối hợp những phép tính có thể ảnh hưởng lẫn nhau.
Trong bộ lọc spam, các chiến lược dựa trên từ khóa, nguồn gửi và thống kê có thể cùng kết luận; nhóm thiếu một quy tắc rõ ràng để diễn giải các kết quả khác nhau khi chạy phối hợp.
Bộ test chỉ kiểm tra chính sách giảm giá cho hội viên Vàng; biến thể hội viên Bạc xử lý sai đúng ngưỡng nhưng không có bộ dữ liệu kiểm thử riêng dù cùng interface.
Nhóm dùng mock cho Context và xác minh strategy được gọi một lần, nhưng không kiểm tra số tiền do từng strategy tính ra; một implementation sai công thức vẫn vượt qua toàn bộ suite.
Ứng dụng cho phép đổi chiến lược phân bổ công việc trong khi các tác vụ đang chạy; một số tác vụ đã bắt đầu với lựa chọn cũ, số còn lại dùng lựa chọn mới và báo cáo tải không nhất quán.
Dịch vụ điều phối phương tiện chọn chiến lược tối ưu thời gian hoặc chi phí theo yêu cầu khách; đầu vào của hai strategy khác nhau khiến Context phải biết chi tiết đặc thù của từng thuật toán.
Trong ứng dụng tìm đường, thuật toán chính xác chạy quá lâu cho bản đồ lớn trong khi thuật toán gần đúng xử lý nhanh; quy tắc chọn strategy chưa xét giới hạn độ trễ của từng request.
Nhóm thử nghiệm thay strategy cân bằng tải qua feature flag; nếu thay đổi cờ giữa hai lời gọi trong cùng giao dịch, hai bước có thể chọn hai chính sách trái nhau.
Một plugin đối tác thêm chiến lược tính điểm qua JAR ngoài; Context khởi động được nhưng không có cách phân biệt plugin tương thích với phiên bản hợp đồng hiện tại.
Trong hệ thống đánh giá tín nhiệm, đội muốn ghi lại strategy nào đã tạo kết quả để giải thích sau kiểm toán; log chỉ ghi điểm cuối nên cùng dữ liệu lịch sử không thể tái hiện quyết định.
Một module Java có ba biến thể chiến lược nhưng Context vẫn chứa if-else để kiểm tra tên lớp concrete trước mỗi lần gọi; thêm biến thể làm lớp Context phải sửa dù đã có hợp đồng thuật toán chung.

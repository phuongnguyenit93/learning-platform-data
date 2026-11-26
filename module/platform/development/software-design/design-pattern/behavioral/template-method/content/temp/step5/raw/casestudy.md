Trong hệ thống nhập dữ liệu, ba bộ đọc CSV, XML và JSON đều phải xác minh file, chuyển bản ghi và ghi báo cáo; các lớp sao chép toàn bộ quy trình nên bản XML bỏ qua bước kiểm tra quyền truy cập mới được bổ sung.
Một hệ thống xử lý hóa đơn quy định thứ tự kiểm tra khách hàng, tính thuế, lưu chứng từ và gửi thông báo; lớp con dành cho khách doanh nghiệp tự thay đổi thứ tự và phát thông báo trước khi chứng từ được lưu.
Đội xây bộ xử lý yêu cầu có phương thức khung gọi validate, execute và audit; một lớp con override cả phương thức khung để bỏ kiểm tra validate, khiến hợp đồng luồng xử lý không còn được bảo đảm.
Ứng dụng tạo báo cáo tuần sử dụng lớp cơ sở để tải dữ liệu, tổng hợp và xuất file; một nhóm muốn chỉ đổi cách trình bày nhưng phải sao chép cả phần đọc dữ liệu và xử lý ngoại lệ.
Trong chương trình xuất chứng từ, lớp cơ sở định nghĩa hook gửi email mặc định không làm gì; lớp con dành cho hóa đơn bắt buộc phải gửi email nhưng quên override nên giao dịch vẫn được coi là thành công.
Một thư viện Java dùng phương thức trừu tượng để tạo thông điệp sau khi kiểm tra xác thực; một lớp con triển khai trả null, khiến bước ghi log của thuật toán khung gặp lỗi ở cuối tiến trình.
Hệ thống sao lưu có các bước khóa file, sao chép, xác minh và mở khóa; khi bước sao chép ném ngoại lệ, phương thức khung không chạy bước mở khóa và người dùng không thể sửa tệp nữa.
Đội phát triển dịch vụ ký số muốn bảo đảm kiểm tra chữ ký diễn ra trước lưu kết quả; lớp con cho đối tác mới tự gọi bước lưu bên trong hook và tạo bản ghi chưa được kiểm chứng.
Một chương trình xử lý đơn có hook onSuccess và onFailure; khi hook onSuccess ném lỗi, phương thức khung tiếp tục chạy onFailure rồi hoàn tác giao dịch đã được xác nhận thành công.
Trong ứng dụng xử lý giao dịch, bước mở transaction được lớp cơ sở quản lý còn một lớp con tự commit sớm trong phương thức tùy biến; bước hậu kiểm phía sau thất bại nhưng không thể rollback.
Nhóm dùng lớp cơ sở trừu tượng để nhập tài liệu từ nhiều loại kho lưu trữ; lớp con HTTP yêu cầu thêm token trước khi đọc, khiến API hook hiện tại không có chỗ biểu diễn điều kiện tiền đề mới.
Một quy trình thanh toán có bước tùy chọn thu thập mã khuyến mãi; lớp con dành cho giao dịch hoàn tiền không cần bước đó nhưng vẫn nhận dữ liệu khuyến mãi từ hook mặc định.
Thư viện phân tích log cho phép lớp con quyết định có bỏ qua dòng trống hay không; hook được gọi sau khi parser đã báo lỗi ở dòng trống nên lựa chọn của lớp con không có hiệu lực.
Trong hệ thống chấm bài trực tuyến, mọi bài đều phải xác minh thời hạn nộp trước khi chấm; một implementation lớp con thay hoàn toàn logic khung và chấm cả bài quá hạn.
Đội tạo một template cho quá trình gửi thông báo qua SMS và email; lớp con SMS đòi nhiều thông số trong khi lớp cơ sở chỉ lưu người nhận dạng email, khiến các phương thức hook lệ thuộc vào kiểu kênh.
Một ứng dụng nhập hàng có template ghi chung trạng thái phần trăm hoàn thành trong field của lớp cơ sở; nhiều thread cùng sử dụng một instance và tiến độ của hai lần nhập bị trộn lẫn.
Trong batch xử lý tệp, bộ khung lưu đường dẫn tạm trong instance rồi gọi các bước của lớp con; yêu cầu thứ hai ghi đè đường dẫn khi yêu cầu thứ nhất chưa chạy xong.
Một lớp trừu tượng gọi phương thức có thể override ngay trong constructor để lấy thông tin cấu hình; implementation con chưa hoàn tất khởi tạo field nên bộ khung nhận giá trị null.
Nhóm đưa nhiều tham số tùy chọn của từng đối tác vào lớp cơ sở chung; mỗi lần thêm biến thể, các lớp con không liên quan phải sửa constructor dù thuật toán khung không thay đổi.
Trong xử lý hồ sơ, bước ghi lịch sử là bắt buộc nhưng nhóm để lớp con override tùy ý; implementation mới ghi lịch sử trước khi xác nhận và dẫn tới nhật ký của hồ sơ bị từ chối.
Một framework quản lý tác vụ dùng template method để ghi trạng thái STARTED và COMPLETED; lớp con chạy bất đồng bộ và trả về ngay, khiến khung ghi COMPLETED khi công việc thực tế vẫn đang chạy.
Đội phát triển quy trình xử lý ảnh gồm đọc, tiền xử lý, phân tích và lưu; lớp con muốn lặp lại bước phân tích vài lần nhưng phương thức khung chỉ gọi bước đó đúng một lần.
Một hệ thống kiểm thử tự động có lớp cơ sở tạo dữ liệu, chạy test rồi dọn môi trường; khi khởi tạo fixture thất bại giữa chừng, teardown không biết tài nguyên nào đã được cấp.
Trong thư viện đồng bộ dữ liệu, template method bao lỗi của toàn bộ các bước và trả thành công nếu một hook phụ thất bại; nhóm không biết chính sách lỗi nào thuộc khung và lỗi nào thuộc từng nguồn.
Một ứng dụng gửi email có hook beforeSend để thêm chữ ký; một lớp con thay đổi cả người nhận và nội dung sau khi phương thức khung đã kiểm tra quyền, tạo ra thông điệp chưa được kiểm tra.
Nhóm muốn cho phép các lớp con bỏ qua bước lưu cache để tăng tốc, nhưng một số dịch vụ khác lại xem cache là nơi duy nhất ghi nhận tiến độ; ý nghĩa hook bỏ qua trở nên mâu thuẫn giữa các ngữ cảnh.
Phần mềm xuất bảng lương có khung xử lý chung và các lớp con theo quốc gia; một quy tắc tính thuế riêng chỉ được phép áp dụng sau khi làm tròn, còn khung cố định việc làm tròn ở bước cuối.
Trong hệ thống phê duyệt, lớp cơ sở đã có hook kiểm tra bổ sung không bắt buộc; một lớp con trả false để từ chối hồ sơ, nhưng bộ khung hiện diễn giải false là bỏ qua hook.
Đội kiểm thử một lớp cơ sở Template Method bằng lớp con thử nghiệm đơn giản; test PASS nhưng implementation thật có hook sửa trạng thái chung nên trình tự xử lý sinh ra kết quả khác.
Nhóm xây báo cáo PDF, CSV và Excel trên cùng lớp cơ sở; mỗi lớp con bị buộc triển khai hàng loạt abstract method không phù hợp với định dạng của mình và chứa các nhánh ném ngoại lệ.
Một thư viện Java dùng protected hook có tên và kiểu tham số ổn định qua nhiều phiên bản; thay đổi chữ ký hook để thêm ngữ cảnh làm các extension đã biên dịch của đối tác không còn tương thích.
Đội muốn áp dụng Template Method để chuẩn hóa các bước thanh toán nhưng thuật toán phải đổi linh hoạt theo nhà cung cấp ngay trong một request; mô hình lớp con cố định từ lúc khởi tạo không đáp ứng lựa chọn runtime.
Trong bộ tạo báo cáo, nhóm tranh luận giữa kế thừa một khung chung và truyền đối tượng xử lý từng bước; nhiều biến thể cần kết hợp cách đọc của nguồn A với cách xuất của nguồn B mà cây lớp con ngày càng lớn.
Ứng dụng sao chép dữ liệu có hai lớp con dùng chung bước lọc nhưng khác bước ghi; nhóm sao chép code lọc vào từng lớp do vị trí hook hiện không cho tái sử dụng riêng bước đó.
Trong pipeline video, lớp cơ sở quản lý cùng một giao dịch cho các bước của lớp con; một biến thể yêu cầu stream dữ liệu liên tục nhiều giờ, khiến transaction bị giữ mở quá lâu.
Một ứng dụng đăng ký tài khoản cho phép extension thêm bước xác minh KYC; khi một hook thực hiện gọi API rất chậm, toàn bộ thuật toán khung giữ khóa database trong thời gian chờ.
Đội phát triển cố định phương thức khung là final nhằm bảo vệ thứ tự các bước; khách hàng mở rộng thư viện lại cần thêm bước đối soát bắt buộc giữa hai bước mà hợp đồng hiện tại không cho phép.
Trong hệ thống ghi nhận điểm thưởng, lớp con triển khai phép tính điều chỉnh lại trả kết quả dựa trên trạng thái của lần gọi trước; cùng dữ liệu đầu vào cho kết quả khác khi chạy một mình hoặc sau test khác.
Một chương trình tạo tài khoản khách hàng có phương thức khung gọi hook báo cáo sau commit; lớp con coi hook báo cáo là nơi quyết định giao dịch thành công và trả thất bại dù tài khoản đã được lưu.
Nhóm phát triển một framework xử lý file mới nhưng chỉ test phương thức khung khi mọi bước thành công; nhánh lỗi ở các bước mở tài nguyên, phân tích và kết thúc chưa được kiểm chứng đối với từng lớp con.

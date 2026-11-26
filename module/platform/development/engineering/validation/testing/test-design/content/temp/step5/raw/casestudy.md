Đội phát triển cổng đăng ký thành viên nhận yêu cầu mật khẩu dài từ 8 đến 64 ký tự nhưng bộ kiểm thử chỉ dùng mật khẩu 12 ký tự, khiến lỗi ở đúng mốc giới hạn không được phát hiện trước khi phát hành.
Ứng dụng bán vé áp dụng phí dịch vụ khác nhau cho đơn dưới 500.000 đồng, từ 500.000 đến dưới 2 triệu và từ 2 triệu trở lên; nhóm chưa thống nhất các giá trị sát ngưỡng trong thiết kế test.
Một API rút tiền chỉ chấp nhận số tiền dương, không vượt số dư và là bội số 10.000 đồng; QA hiện kiểm tra từng điều kiện riêng lẻ nhưng chưa có ca thể hiện tương tác giữa các điều kiện.
Website tuyển dụng cho phép tải CV dạng PDF và DOCX tối đa 5 MB; nhà phân tích kiểm thử cần xác định các nhóm file hợp lệ và không hợp lệ khi tên file có phần mở rộng không khớp nội dung.
Quy trình xác minh tài khoản yêu cầu người dùng đủ 18 tuổi tại ngày đăng ký; logic tính tuổi gần ngày sinh nhật và năm nhuận khiến vài khách hàng ở đúng ranh giới được xét khác nhau.
Hệ thống tính thuế thu nhập có bốn bậc theo ngưỡng; tài liệu chỉ mô tả mức thuế từng bậc mà không xác định rõ ngưỡng trên thuộc bậc nào, khiến đội test chưa thể kết luận kết quả mong đợi.
Một biểu mẫu đăng ký khóa học cho phép số lượng học viên từ 1 đến 30; API nhận chuỗi từ giao diện, còn người kiểm thử chưa phân biệt các trường hợp số 0, số âm, số thập phân và ký tự chữ.
Ứng dụng logistics chấp nhận mã bưu chính khác nhau theo quốc gia; bộ kiểm thử hiện dùng cùng quy tắc sáu chữ số cho mọi nơi, làm dữ liệu hợp lệ ở vài thị trường bị từ chối.
Quy tắc miễn phí vận chuyển phụ thuộc cấp hội viên, tổng giỏ hàng và địa chỉ ngoại thành; khi thêm chương trình ưu đãi mới, nhiều nhánh điều kiện chưa có test tương ứng.
Ứng dụng phê duyệt khoản vay kết hợp thu nhập, lịch sử nợ và số tiền đề nghị; các quy tắc chồng lấp khiến cùng một hồ sơ có thể thuộc hai dòng trong bảng quyết định được QA soạn.
Trong chức năng hoàn tiền, khách VIP được ưu tiên xử lý nhanh trừ khi giao dịch có dấu hiệu gian lận; bộ test ban đầu bỏ sót ngoại lệ khi cả hai điều kiện đều đúng.
Hệ thống điểm danh cho phép điểm danh trực tuyến nếu học viên có tài khoản đang hoạt động và buổi học chưa kết thúc; người kiểm thử chỉ tạo ca thành công nên không phát hiện sai lệnh ưu tiên điều kiện.
Quy trình đặt phòng có các trạng thái Chờ thanh toán, Đã xác nhận, Đã hủy và Hoàn tất; ứng dụng cho phép chuyển thẳng từ Đã hủy sang Hoàn tất khi người dùng tải lại trang cũ.
Dịch vụ xử lý đơn hàng có thể nhận yêu cầu hủy khi đơn đang đóng gói hoặc đã giao vận chuyển; yêu cầu nghiệp vụ diễn đạt thiếu rõ các trạng thái nào còn được hủy và hoàn tiền.
Ví điện tử khóa tài khoản sau năm lần nhập PIN sai rồi mở lại sau 15 phút; bộ test chỉ kiểm tra sai lần thứ năm, không khảo sát bộ đếm sau một lần đăng nhập đúng hoặc sau khi hết hạn khóa.
Một giao diện quản trị cho phép duyệt phiếu trước khi xuất hóa đơn; người kiểm thử cần xác định hành vi khi nút Duyệt được bấm hai lần do mạng chậm và trạng thái đã đổi ở request đầu.
Tính năng đặt lịch hẹn cho phép đổi lịch trước giờ bắt đầu ít nhất 24 giờ; tài liệu và các ca test hiện không nói rõ mốc đúng 24 giờ theo múi giờ của khách hay của trung tâm.
Luồng yêu cầu cấp lại mật khẩu tạo liên kết có hiệu lực 10 phút và chỉ sử dụng một lần; QA chưa mô tả các đường đi khi liên kết hết hạn, bị dùng lại hoặc bị thu hồi sau lần gửi mới.
Trong hệ thống lương, người phụ trách nghiệp vụ báo lỗi sai tiền trợ cấp nhưng không cung cấp bộ dữ liệu đầu vào có thể tái lập; nhóm test thiếu dấu vết liên kết từ quy tắc đến ca kiểm thử.
Ứng dụng quản lý tồn kho có yêu cầu không cho xuất vượt số lượng hiện có; test catalog chỉ ghi 'kiểm thử xuất kho' mà không xác định tồn đầu kỳ, số yêu cầu và số tồn cuối mong đợi.
Một quy tắc tính chiết khấu vừa được sửa trong ticket nhưng đặc tả và bảng test cũ vẫn ghi phiên bản trước; người kiểm thử không rõ ca nào cần cập nhật và kết quả nào vẫn hợp lệ.
Nhóm dùng bảng tính lưu hàng trăm test case nhưng mỗi hàng chỉ chứa tên chức năng; khi chuyển QA sang thành viên khác, không thể biết điều kiện tiên quyết hoặc cách xác minh thành công.
Trong API chuyển khoản, cùng yêu cầu có thể bị gửi lại sau timeout; ca test không ghi rõ mã giao dịch và trạng thái trước/sau, nên không phân biệt được ghi nhận trùng với phản hồi trùng.
Một hệ thống thanh toán hỗ trợ ba loại tiền tệ và hai cách làm tròn; nhóm chưa chọn dữ liệu test đủ để phân biệt sai sót tại các giá trị nửa đơn vị nhỏ nhất.
Trình lập kế hoạch thi có 18 điều kiện ràng buộc; bộ phận QA muốn kiểm tra mọi tổ hợp nhưng số lượng ca vượt thời gian sprint và chưa có đánh giá rủi ro để lựa chọn.
Ứng dụng khách sạn có thể áp dụng nhiều mã khuyến mãi; đội kiểm thử đang tranh luận nên ưu tiên tổ hợp phổ biến hay trường hợp hiếm có thể gây mất tiền lớn khi chọn ca hồi quy.
Hệ thống y tế ghi nhật ký ai đã mở hồ sơ bệnh án; chức năng xem hồ sơ chạy đúng nhưng bộ test chỉ xét dữ liệu hiển thị, bỏ qua yêu cầu lưu dấu truy cập nhằm phục vụ kiểm toán.
Một ứng dụng ngân hàng vừa sửa logic phí chuyển quốc tế; nhóm cần xác định ca hồi quy nào có nguy cơ cao hơn khi thay đổi ảnh hưởng nhiều sản phẩm dùng chung công thức phí.
Đội phát hành ứng dụng mua sắm chỉ có bốn giờ kiểm thử thủ công trước release; danh sách hơn 200 ca chưa được gắn mức độ ảnh hưởng và tần suất sử dụng để chọn tập chạy phù hợp.
Trên màn hình cập nhật địa chỉ, trường tỉnh thay đổi danh sách huyện và xã; ca test hiện chỉ chọn giá trị theo đúng thứ tự, nên chưa bao phủ lúc người dùng đổi tỉnh sau khi đã chọn xã.
Một hệ thống báo cáo cho phép kết hợp bộ lọc ngày, chi nhánh, trạng thái và loại giao dịch; tester thử mỗi bộ lọc riêng nhưng khi dùng nhiều bộ lọc đồng thời kết quả có số hàng sai.
Trong chức năng tạo đơn, quy tắc chặn đơn rỗng có cả ở giao diện và API; kiểm thử UI đi qua bước validation, còn lệnh gọi API trực tiếp vẫn tạo được đơn không có sản phẩm.
Người quản lý muốn kiểm tra yêu cầu 'tìm kiếm nhanh' nhưng tài liệu không có thời gian phản hồi hoặc quy mô dữ liệu; đội test chưa xác định được oracle để đánh giá chức năng tìm kiếm đáp ứng yêu cầu.
Một tính năng tổng hợp doanh số cần loại các đơn đã hoàn trả; bộ test dùng dữ liệu một khách hàng và một đơn nên phép tính sai khi có nhiều khoản hoàn một phần vẫn không lộ ra.
Ứng dụng chấm công cho phép chỉnh sửa bản ghi trong kỳ còn mở; kỳ tháng trước vừa khóa và hệ thống chưa xác định phản hồi kỳ vọng với người dùng giữ form cũ đang chỉnh sửa.
Trong luồng đăng ký nhiều bước, người dùng nhập xong thông tin rồi quay lại sửa bước đầu; bảng test không có ca kiểm tra dữ liệu bước sau có được giữ hay đặt lại theo quy tắc mới.
Một dịch vụ nhận đồng thời hai yêu cầu đặt chỗ cuối cùng; test hiện tuần tự hóa mọi request và không mô tả cách nhận biết vi phạm giới hạn số chỗ trong kết quả cuối.
Nhóm phát triển đã bổ sung yêu cầu không tạo trùng mã phiếu khi user nhấn nút Gửi nhiều lần; test case không chỉ rõ số lần gửi, trạng thái ban đầu và số phiếu được phép tồn tại.
Một lỗi production xảy ra khi khách đặt hàng qua thiết bị di động lúc mạng gián đoạn; đội test cần tái hiện chuỗi sự kiện từ gửi đơn, mất kết nối đến thử lại nhưng chưa có bước quan sát độc lập.
Trong đợt rà soát chất lượng, đội phát hiện nhiều test case có thể chạy và đều PASS nhưng không gắn với bất kỳ yêu cầu nghiệp vụ nào; việc tuyên bố độ bao phủ hoàn chỉnh bị đặt dấu hỏi.

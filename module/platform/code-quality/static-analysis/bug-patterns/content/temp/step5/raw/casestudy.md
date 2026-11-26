SpotBugs cảnh báo nguy cơ null dereference trong service Java xử lý thanh toán vì phương thức tìm tài khoản có thể trả về null; unit test hiện tại chỉ dùng tài khoản hợp lệ.
Một luồng import dữ liệu chỉ kiểm tra null ở đầu phương thức, nhưng đối tượng được thay thế bằng kết quả tra cứu khác ở nhánh sau; cảnh báo phân tích tĩnh xuất hiện tại chỗ truy cập thuộc tính cuối cùng.
Trong API quản lý đơn hàng, lập trình viên lấy giá trị trực tiếp từ Optional sau một phép lọc; Error Prone nghi ngờ có trường hợp không tồn tại kết quả khi khách hàng mới đăng ký.
Một lớp dùng làm khóa của HashMap ghi đè equals để so sánh theo mã giao dịch nhưng không cung cấp hashCode tương ứng, khiến thao tác tìm lại khóa thất bại trong một số trường hợp.
Service tính phí sử dụng BigDecimal để biểu diễn tiền nhưng so sánh hai giá trị bằng phương thức phụ thuộc cả scale; các khoản tương đương về số học đôi khi được phân loại khác nhau.
Trong mô-đun xác thực, một nhánh so sánh chuỗi trạng thái bằng danh tính đối tượng; thử nghiệm với chuỗi literal thành công còn dữ liệu đọc từ database lại cho kết quả khác.
Chức năng tính tổng số sản phẩm lưu trung gian bằng số nguyên 32 bit; cảnh báo overflow xuất hiện khi nhân số lượng với đơn giá cho các đơn hàng doanh nghiệp rất lớn.
Một hệ thống ví điện tử cộng dồn tiền tệ bằng số thực nhị phân; kết quả đối soát lệch vài đơn vị nhỏ sau hàng nghìn giao dịch dù các phép tính đơn lẻ có vẻ đúng.
Ứng dụng Java web dùng chung một instance SimpleDateFormat giữa nhiều request; SpotBugs cảnh báo truy cập không an toàn trong khi lỗi parse ngày chỉ xuất hiện khi tải cao.
Trong service quản lý giỏ hàng, nhiều thread cập nhật một HashMap dùng chung không có cơ chế đồng bộ; dữ liệu mất ngẫu nhiên sau đợt tăng tải và công cụ phân tích tĩnh đưa ra cảnh báo đồng thời.
Một background worker dùng biến cờ thường để báo dừng cho thread khác; trình phân tích cảnh báo vấn đề khả năng nhìn thấy thay đổi khiến worker đôi khi không kết thúc như dự kiến.
Code sắp xếp phiên bản sản phẩm sử dụng comparator có kết quả không nhất quán giữa ba phần tử; bộ sắp xếp thỉnh thoảng ném exception với tập dữ liệu lớn.
Một đối tượng chứa mã khách hàng có thể thay đổi được dùng làm khóa trong HashSet; sau khi cập nhật mã, thao tác kiểm tra phần tử trả về kết quả không như mong đợi.
Batch job mở stream đọc file CSV rồi return sớm khi dữ liệu sai định dạng; SpotBugs chỉ ra một nhánh có nguy cơ không đóng resource khi pipeline chạy nhiều file.
Trong quy trình tạo báo cáo, PreparedStatement được mở trước vòng lặp nhưng nhánh xử lý exception không giải phóng tài nguyên JDBC; connection pool cạn dần trong ca chạy dài.
Người phát triển bắt một exception khi gọi dịch vụ đối tác rồi để trống khối xử lý để ứng dụng tiếp tục; PMD cảnh báo lỗi bị nuốt và dữ liệu nghiệp vụ có thể ở trạng thái không xác định.
Một worker xử lý hàng đợi bắt InterruptedException nhưng tiếp tục vòng lặp vô hạn; khi triển khai phiên bản mới, tiến trình không dừng đúng thời hạn mà hệ điều phối yêu cầu.
Trong API cập nhật dữ liệu, kết quả bất đồng bộ của thao tác ghi bị bỏ qua; Error Prone báo rằng một lỗi tương lai có thể không được quan sát dù HTTP response đã trả thành công.
Code đọc một cột số nguyên có thể null từ ResultSet rồi dùng ngay giá trị mặc định bằng không; khách hàng không nhập số lượng bị hiểu thành đã nhập số lượng bằng không.
Trình tải file nhị phân gọi đọc stream một lần và mặc định buffer đã được điền đủ; file lớn truyền qua mạng không ổn định đôi khi bị cắt ngắn nhưng kiểm tra kích thước cuối không phát hiện.
Trong tác vụ làm sạch cache, lập trình viên xóa phần tử khỏi ArrayList ngay khi duyệt bằng vòng lặp tăng cường; job chỉ gặp ConcurrentModificationException với một số tập dữ liệu.
Module tìm kiếm khách hàng lắp chuỗi điều kiện SQL từ tham số URL; PMD cảnh báo mẫu truy vấn nguy hiểm dù các ca thử thủ công chỉ gửi dữ liệu bình thường.
Dịch vụ upload ghép tên file do người dùng gửi vào đường dẫn lưu trữ trên máy chủ; bộ quét chỉ ra khả năng đọc hoặc ghi ngoài thư mục cho phép khi tên file chứa thành phần điều hướng.
API tạo mã đặt lại mật khẩu sử dụng bộ sinh số ngẫu nhiên phục vụ mô phỏng; cảnh báo bảo mật cho thấy mã có thể đoán được nếu đối tượng tấn công quan sát đủ lần phát hành.
Một service Java parse XML do đối tác gửi mà chưa giới hạn việc truy cập external entity; công cụ phân tích tĩnh nêu rủi ro khi gặp tài liệu XML không tin cậy.
Ứng dụng cũ nhận đối tượng Java được serialize qua hàng đợi nội bộ; bộ quét cảnh báo deserialization của dữ liệu không được xác thực khi tích hợp thêm đối tác mới.
PMD báo một phương thức factory dường như không được gọi trong mã nguồn, nhưng framework thực tế tìm và gọi nó qua reflection; nhóm cần phân biệt code chết với cảnh báo sai trước khi xóa.
SpotBugs cảnh báo dereference trên tham số có custom annotation đảm bảo non-null theo hợp đồng dự án; đội phân tích cần kiểm chứng hợp đồng và luồng dữ liệu trước khi suppress.
Sau khi nâng Java và phiên bản Error Prone, hàng chục cảnh báo mới xuất hiện ở code vốn chạy lâu năm; nhóm cần phân loại mức độ nguy hiểm thay vì sửa hàng loạt theo tên rule.
CI hiện chỉ thất bại khi tổng số cảnh báo SpotBugs vượt ngưỡng 100, trong khi một pull request vừa thêm lỗi null nghiêm trọng nhưng đồng thời xóa nhiều cảnh báo mức thấp nên tổng vẫn giảm.

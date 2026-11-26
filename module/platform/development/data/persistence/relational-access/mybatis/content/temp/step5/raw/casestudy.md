Một dịch vụ Spring Boot khởi động thành công nhưng khi gọi chức năng tìm đơn hàng mới báo không tìm thấy câu lệnh mapper; nhóm cần đối chiếu vị trí XML, package quét và tên phương thức Java với cấu hình MyBatis.
Hai nhóm phát triển các mapper XML có tên định danh câu lệnh giống nhau và vô tình dùng chung namespace; sau khi hợp nhất module, một thao tác truy vấn chạy câu SQL không thuộc chức năng dự kiến.
Một phương thức mapper nhận cả mã khách hàng, khoảng ngày và trạng thái, nhưng tệp SQL tham chiếu tên tham số không khớp với tên mà MyBatis nhận diện; lỗi chỉ xuất hiện khi người dùng chọn đủ bộ lọc.
Trang quản trị dùng SQL động MyBatis để thay cột sắp xếp từ yêu cầu HTTP và chèn trực tiếp tên cột vào câu lệnh; nhóm phát hiện sự khác biệt giữa giá trị ràng buộc tham số và nội dung SQL được thay thế nguyên văn.
Một bộ lọc đơn hàng có nhiều điều kiện tùy chọn và ghép các mệnh đề bằng tay; khi người dùng bỏ chọn trạng thái, câu SQL sinh ra bắt đầu bằng AND và truy vấn thất bại.
Ứng dụng tìm sản phẩm theo danh sách mã truyền vào mapper bằng một mệnh đề IN động; với danh sách rỗng, SQL được tạo không hợp lệ, còn với danh sách rất lớn số tham số vượt ngưỡng của hệ quản trị.
Một API cập nhật hồ sơ sử dụng SQL động để bỏ qua trường có giá trị null; khách hàng muốn xóa số điện thoại về NULL nhưng truy vấn lại giữ nguyên dữ liệu cũ, tạo mâu thuẫn giữa “không gửi” và “xóa giá trị”.
Một endpoint tìm kiếm tạo hàng chục tổ hợp SQL khác nhau từ nhiều cờ lựa chọn, khiến việc xem log, tối ưu chỉ mục và dự đoán thời gian truy vấn khó khăn; nhóm phải kiểm tra tính đúng đắn và khả năng bảo trì của SQL động.
Cơ sở dữ liệu dùng tên cột có dấu gạch dưới nhưng đối tượng Java dùng tên thuộc tính kiểu camelCase; sau khi thêm một cột mới, một số thuộc tính trả về null mà không có lỗi truy vấn.
Truy vấn JOIN đơn hàng và khách hàng lấy cả hai cột trạng thái cùng tên; resultMap hiện tại ánh xạ nhầm trạng thái khách hàng vào đối tượng đơn hàng khi không có tên cột phân biệt.
Một mapper tải đơn hàng và nhiều dòng chi tiết bằng JOIN, nhưng đối tượng kết quả chứa các chi tiết lặp hoặc bị gộp sai khi một đơn có nhiều sản phẩm trùng mã; nhóm cần xem lại cấu hình khóa nhận dạng trong resultMap.
Màn hình báo cáo đọc danh sách một trăm đơn hàng rồi truy vấn riêng từng khách hàng qua nested select; số câu SQL tăng theo số đơn và thời gian phản hồi xấu đi khi dữ liệu lớn.
Một API trả về đối tượng từ mapper rồi mới truy cập danh sách chi tiết được tải lười sau khi SqlSession đã đóng; chức năng chỉ phát sinh lỗi ở nhánh có yêu cầu xem chi tiết.
Nhóm chuyển lớp kết quả sang đối tượng bất biến chỉ có constructor nhưng resultMap cũ dựa vào setter; dữ liệu trả về không được khởi tạo đầy đủ dù câu SQL vẫn chạy thành công.
Một trường trạng thái thanh toán được lưu bằng số thứ tự enum thông qua ánh xạ kiểu; sau khi thêm một trạng thái mới vào giữa danh sách, các bản ghi lịch sử được hiểu thành trạng thái khác.
Dịch vụ lưu cấu hình sản phẩm dưới dạng JSON trong một cột quan hệ và đọc qua TypeHandler tùy chỉnh; sau khi thay cấu trúc JSON, một số bản ghi cũ không ánh xạ được về đối tượng Java.
Ứng dụng lưu thời điểm hết hạn theo UTC nhưng TypeHandler chuyển sang kiểu thời gian không gắn múi giờ ở một số môi trường; cùng bản ghi có thể bị coi là đã hết hạn hoặc chưa hết hạn tùy máy chủ.
Một nhóm chuyển lô nhập giao dịch sang chế độ thực thi batch của MyBatis nhưng vẫn kỳ vọng mỗi lệnh được ghi ngay khi gọi mapper; câu truy vấn kiểm tra sau đó không phản ánh đúng phần công việc đang chờ thực thi.
Ứng dụng nhập nhiều khách hàng bằng mapper batch và cần gắn khóa do cơ sở dữ liệu sinh vào từng đối tượng Java; sau khi đổi driver, một số đối tượng không nhận được khóa đúng vị trí.
Trong quy trình chuyển khoản, hai mapper cập nhật số dư được gọi bằng hai SqlSession tạo riêng rồi tự commit; một lần cập nhật thành công, lần còn lại thất bại và dữ liệu nghiệp vụ không còn cân bằng.
Một dịch vụ Spring Boot dùng mapper MyBatis và một thao tác JDBC trực tiếp trong cùng nghiệp vụ, nhưng hai phần sử dụng DataSource và ranh giới giao dịch không đồng nhất; khi rollback chỉ một phần thay đổi bị hủy.
Một phương thức của service Spring gọi phương thức khác trong cùng lớp có khai báo giao dịch trước khi chạy mapper; đội phát hiện hành vi commit khác với lúc phương thức được gọi từ bên ngoài bean.
Một lập trình viên lưu SqlSession trong biến dùng chung để tiết kiệm chi phí tạo đối tượng; khi hai yêu cầu HTTP đồng thời cập nhật dữ liệu, kết quả truy vấn và trạng thái transaction bị lẫn giữa các yêu cầu.
Trong một SqlSession kéo dài, mapper đọc cùng hồ sơ nhiều lần; sau khi một ứng dụng khác cập nhật cơ sở dữ liệu, lần đọc tiếp theo vẫn thấy đối tượng cũ, khiến nhóm phải xem xét phạm vi cache cấp một.
Một dự án bật cache cấp hai cho mapper đọc danh mục sản phẩm; dữ liệu được cập nhật qua công cụ quản trị riêng nhưng ứng dụng tiếp tục trả về danh mục cũ dù truy vấn mới đã hoàn tất bên hệ quản trị.
Một đối tượng kết quả lấy từ cache mapper bị sửa trực tiếp bởi tầng nghiệp vụ trước khi phản hồi; một yêu cầu khác sau đó nhận cùng thông tin đã thay đổi dù cơ sở dữ liệu không có lần ghi tương ứng.
Một tác vụ xuất báo cáo dùng mapper trả về toàn bộ vài triệu dòng thành List, khiến heap bị tràn trước khi viết xong tệp; đội phải đánh giá hình thức xử lý kết quả lớn và thời gian giữ kết nối.
Ứng dụng dùng tham số phân trang của MyBatis để lấy trang rất sâu của lịch sử giao dịch; thời gian truy vấn và lượng dữ liệu được đọc tăng mạnh, khiến nhóm phải xác minh cơ chế phân trang thực tế với driver và SQL sinh ra.
Một mapper dùng SQL động để lọc khách hàng theo số điện thoại sau khi chuẩn hóa chuỗi ngay trên cột; dù có chỉ mục, cơ sở dữ liệu quét nhiều dòng và API chậm khi bảng lớn.
Một mapper INSERT gặp lỗi ràng buộc duy nhất do người dùng tạo trùng mã, nhưng tầng service chỉ nhận thông báo lỗi cơ sở dữ liệu khó hiểu; nhóm cần phân biệt lỗi nghiệp vụ với lỗi truy cập dữ liệu có thể thử lại.
Các bài kiểm thử mapper chạy tốt trên cơ sở dữ liệu nhúng nhưng thất bại khi triển khai PostgreSQL vì cú pháp nối chuỗi và xử lý kiểu ngày khác nhau; nhóm cần xác định chiến lược kiểm thử SQL thực tế.
Sau khi đội dữ liệu đổi tên cột qua migration, một số mapper XML vẫn tham chiếu tên cũ và chỉ lỗi khi nhánh báo cáo hiếm được gọi; nhóm cần bảo đảm thay đổi schema và SQL mapper được kiểm tra nhất quán trong CI.

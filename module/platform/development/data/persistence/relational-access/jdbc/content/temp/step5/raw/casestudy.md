Một ứng dụng Java kết nối cơ sở dữ liệu thành công trên máy phát triển nhưng báo không tìm thấy driver khi triển khai lên máy chủ mới; đội cần kiểm tra cách đóng gói driver JDBC, cấu hình kết nối và môi trường chạy.
Sau khi chuyển từ tạo kết nối trực tiếp sang DataSource dùng pool, dịch vụ đặt hàng vẫn hết kết nối vào giờ cao điểm dù số truy vấn mỗi giây không tăng nhiều; nhóm cần tìm nguyên nhân các kết nối bị giữ quá lâu.
Một tác vụ xuất báo cáo giữ Connection trong suốt quá trình gọi dịch vụ bên ngoài và tạo tệp PDF, khiến những yêu cầu cập nhật ngắn phải chờ kết nối rảnh; nhóm phải xem lại ranh giới sử dụng tài nguyên JDBC.
Ứng dụng Java dùng mật khẩu cơ sở dữ liệu được khai báo cố định trong tệp cấu hình; sau đợt thay mật khẩu, một phần instance mới kết nối thất bại trong khi instance cũ vẫn chạy, đặt ra vấn đề quản lý thông tin xác thực và cấu hình DataSource.
Một dịch vụ có nhánh xử lý lỗi trả về sớm trước khi đóng Statement và ResultSet; sau nhiều giờ hoạt động, pool kết nối bị cạn dù truy vấn thường chỉ mất vài mili giây.
Chức năng tìm đơn hàng ghép trực tiếp số điện thoại do người dùng nhập vào chuỗi SQL, khiến một số giá trị chứa dấu nháy gây lỗi và tạo nguy cơ truy vấn bị thay đổi ngoài ý muốn.
Trang quản trị cho phép người dùng chọn cột sắp xếp và truyền nguyên tên cột vào truy vấn; nhóm nhận ra PreparedStatement chỉ xử lý giá trị tham số và cần đánh giá cách xây dựng phần định danh SQL được phép.
Một đối tượng PreparedStatement được dùng nhiều lần cho các bộ lọc khác nhau, nhưng một nhánh không đặt lại đầy đủ giá trị tham số; kết quả tìm kiếm đôi khi dùng giá trị của lần gọi trước.
Ứng dụng đặt lịch lưu thời điểm bằng kiểu ngày giờ từ Java, nhưng sau khi máy chủ chuyển múi giờ, cùng hồ sơ hiển thị lệch giờ trên hai môi trường; nhóm cần xem lại biểu diễn thời gian khi truyền qua JDBC.
Dịch vụ tính tiền hàng ghi số tiền có phần thập phân vào cột DECIMAL nhưng ở lớp Java lại chuyển qua số thực nhị phân, khiến tổng đối soát sai khác ở các trường hợp làm tròn.
Một quy trình tạo đơn hàng cần lấy khóa chính do cơ sở dữ liệu sinh để ghi chi tiết đơn; sau khi đổi driver, đoạn xử lý phụ thuộc vào một cách lấy khóa riêng của hệ quản trị cũ không còn hoạt động.
Báo cáo đọc cột số lượng có thể NULL bằng phương thức trả về kiểu số nguyên nguyên thủy, khiến số lượng chưa xác định bị hiển thị như số không và ảnh hưởng phân tích tồn kho.
Hai bảng có chung tên cột mã và trạng thái được JOIN để trả dữ liệu, nhưng lớp ánh xạ ResultSet đọc theo nhãn cột không rõ ràng; một số đối tượng nhận trạng thái từ bảng sai.
Một dịch vụ trích xuất vài triệu dòng dữ liệu bằng JDBC và giữ toàn bộ kết quả trong List trước khi ghi tệp, khiến heap Java tăng vọt và tác vụ thất bại khi báo cáo lớn.
Lớp truy cập dữ liệu trả trực tiếp ResultSet cho tầng web rồi đóng Connection trước khi dữ liệu được duyệt; chức năng hoạt động với một số bản ghi nhỏ nhưng lỗi khi phân trang và đọc nội dung sau đó.
API cập nhật thông tin khách hàng thông báo thành công dù câu lệnh UPDATE không sửa hàng nào vì mã khách hàng không tồn tại; nhóm cần đánh giá cách sử dụng số dòng bị ảnh hưởng để phản ánh kết quả CRUD.
Một nhân viên mở hai cửa sổ để sửa cùng hồ sơ, và lần lưu sau ghi đè các thay đổi của lần lưu trước mà không cảnh báo; đội JDBC cần xem xét điều kiện cập nhật dựa trên phiên bản dữ liệu.
Quy trình chuyển tiền thực hiện hai lệnh UPDATE số dư nhưng để chế độ tự động commit; lỗi xảy ra ở lần cập nhật tài khoản nhận khiến tổng tiền giữa hai tài khoản không còn khớp.
Một tác vụ đăng ký dịch vụ đã tắt auto-commit nhưng khi gặp SQLException chỉ ghi log rồi trả Connection về pool; yêu cầu tiếp theo nhận lại kết nối với trạng thái giao dịch không như mong đợi.
Trong lô nhập hóa đơn, một hóa đơn sai dữ liệu không nên làm hủy toàn bộ các hóa đơn đã kiểm tra hợp lệ trước đó; nhóm cân nhắc phạm vi transaction và điểm khôi phục trung gian cho quá trình nhập.
Hai yêu cầu mua hàng đồng thời đều đọc số lượng tồn bằng cùng một giá trị ban đầu rồi ghi lại kết quả đã trừ, dẫn đến bán vượt kho; nhóm cần xác định khả năng cô lập giao dịch và tính đúng đắn của kiểm tra rồi cập nhật.
Hai worker cập nhật bảng tài khoản và bảng hóa đơn theo thứ tự ngược nhau, làm cơ sở dữ liệu thỉnh thoảng phát hiện deadlock; ứng dụng hiện trả lỗi chung cho người dùng mà không phân biệt lỗi có thể thử lại.
Một màn hình thống kê đọc tổng số đơn và danh sách đơn trong hai câu SQL liên tiếp, nhưng có giao dịch khác chèn thêm đơn ở giữa nên số tổng và danh sách không khớp; nhóm cần đánh giá ảnh hưởng mức cô lập khi thực hiện báo cáo.
Đội phát triển chia sẻ một Connection JDBC duy nhất cho nhiều luồng xử lý HTTP để giảm chi phí tạo kết nối; khi một luồng rollback, kết quả của luồng khác cũng bị ảnh hưởng dù các yêu cầu độc lập.
Một ứng dụng nhập mười nghìn bản ghi bằng cách gửi riêng từng INSERT và đợi phản hồi, khiến thời gian hoàn tất tăng mạnh khi cơ sở dữ liệu nằm ở trung tâm dữ liệu xa.
Khi gửi một batch INSERT, một bản ghi vi phạm ràng buộc duy nhất và driver trả lỗi kèm thông tin các cập nhật đã thực hiện; nhóm phải xác định cách ghi nhận hàng thành công, hàng lỗi và trạng thái transaction.
Quy trình đồng bộ dữ liệu tạo một batch chứa hàng triệu thao tác trước khi thực thi, khiến ứng dụng chiếm nhiều bộ nhớ và khó xác định phần công việc đã được lưu khi kết nối bị ngắt.
Một lệnh INSERT bị timeout phía ứng dụng nhưng sau đó xuất hiện trong cơ sở dữ liệu; cơ chế retry mù quáng lại tạo thêm đơn hàng với mã mới, khiến nhóm cần phân biệt lỗi kết nối và kết quả giao dịch chưa rõ ràng.
Một truy vấn tìm kiếm thiếu điều kiện giới hạn chạy trong nhiều phút, chiếm một kết nối và làm chậm các yêu cầu khác; nhóm phải làm rõ giới hạn thời gian truy vấn và hành vi xử lý khi bị hủy.
Hệ thống có chỉ mục trên mã khách hàng nhưng câu SQL dùng phép biến đổi trên cột khi lọc; dưới tải lớn cơ sở dữ liệu vẫn quét nhiều dòng, buộc nhóm xem lại truy vấn, kế hoạch thực thi và chỉ mục.
Trang danh sách sử dụng phân trang bằng vị trí offset lớn; khi người dùng chuyển tới cuối lịch sử nhiều triệu dòng, thời gian phản hồi tăng và bản ghi có thể lặp nếu dữ liệu mới liên tục được chèn.
Ứng dụng Java cần chạy với hai hệ quản trị quan hệ khác nhau, nhưng câu SQL dùng cú pháp phân trang và kiểu khóa sinh đặc thù của một nhà cung cấp; nhóm cần đánh giá ranh giới giữa API JDBC chuẩn và khác biệt SQL của từng hệ.

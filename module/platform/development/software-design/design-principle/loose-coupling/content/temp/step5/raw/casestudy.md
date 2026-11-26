Trong hệ thống đặt hàng Java, OrderService trực tiếp tạo SmtpEmailSender bằng constructor; khi thay kênh xác nhận từ email sang thông báo đẩy, nhóm phải sửa cả luồng ghi nhận đơn hàng.
Ứng dụng ngân hàng gọi SDK của một cổng thanh toán ngay trong lớp tính phí; khi đối tác đổi phương thức xác thực, nhiều phép tính nghiệp vụ đang ổn định cũng phải được chỉnh sửa và chạy lại test.
Đội phát triển báo cáo doanh thu sử dụng trực tiếp EntityManager của JPA trong lớp giao diện; khi chuyển cơ chế truy vấn, cả phần tạo biểu đồ và thao tác database cùng phải thay đổi.
Trong dịch vụ giao hàng, lớp DispatchService phụ thuộc vào class concrete của ba nhà vận chuyển; thêm đối tác thứ tư buộc cập nhật constructor và mọi nơi tự tạo DispatchService.
Một library Java công bố interface lưu trữ nhưng trả về kiểu ResultSet đặc thù JDBC; consumer vẫn phải hiểu cursor và vòng đời kết nối dù chỉ cần một danh sách đơn hàng.
API quản lý khách hàng trả nguyên đối tượng ORM chứa các association nội bộ; thay đổi cách tải dữ liệu lazy làm client báo cáo nhận lỗi dù hợp đồng nghiệp vụ không thay đổi.
Đội tích hợp dịch vụ kiểm tra tín dụng truyền trực tiếp object response của nhà cung cấp sang use case phê duyệt khoản vay; nhà cung cấp đổi tên một trường khiến các quyết định nghiệp vụ không còn biên dịch.
Trong ứng dụng CRM, một lớp nghiệp vụ gọi method private của module khác thông qua reflection; bản refactor chỉ đổi tên method đã khiến luồng cập nhật khách hàng thất bại ở runtime.
Nhóm quản lý kho thay đổi một giá trị enum trạng thái nội bộ; nhiều module nhập trực tiếp enum này để hiển thị nhãn, ghi log và lọc đơn nên phải sửa đồng loạt.
Ứng dụng nhiều tenant lưu tenantId hiện tại trong singleton có setter; service của tenant A có thể đọc lại giá trị do request tenant B vừa cập nhật, khiến ranh giới cộng tác bị phá vỡ.
Một đội sử dụng Service Locator để lấy database client từ tên chuỗi bên trong các use case; unit test không biết các dependency thực tế cho tới khi chương trình chạy vào nhánh hiếm.
Trong Spring, cấu hình Dependency Injection cung cấp hai implementation của PaymentGateway mà không phân biệt phạm vi sử dụng; service thỉnh thoảng nhận cổng khác với môi trường được cấu hình.
Nhóm dựng lớp NotificationService có constructor nhận mười hai dependency, trong đó một số chỉ dùng ở nhánh SMS; khi chạy test email, vẫn phải cung cấp toàn bộ phụ thuộc của các nhánh khác.
Trong hệ thống đăng ký khóa học, ModuleEnrollment gọi trực tiếp ModuleBilling và ModuleBilling lại gọi về ModuleEnrollment để xác minh trạng thái; biểu đồ dependency tạo vòng và không thể khởi tạo khi tách module.
Đội xây phần mềm quản lý hồ sơ cho phép một module đọc trực tiếp bảng database của module khác; thay đổi schema lưu trữ của nhóm sở hữu bảng khiến chức năng bên ngoài dừng hoạt động.
Một hệ thống có ứng dụng mobile và web cùng gọi service tạo đơn; các client tự kiểm tra chi tiết class exception nội bộ thay vì một hợp đồng lỗi ổn định nên bất kỳ refactor server nào cũng ảnh hưởng client.
Nhóm định nghĩa cổng repository chứa cả lưu, phân trang theo framework và tạo báo cáo PDF; các use case chỉ cần tìm theo mã vẫn phụ thuộc vào toàn bộ giao diện và thư viện báo cáo.
Ứng dụng bán vé có lớp TicketController tự dựng URL API của đối tác bằng chuỗi hằng; khi đổi domain hoặc phiên bản API, hàng chục controller phải sửa theo.
Trong nền tảng xử lý sự kiện, producer phát event chứa toàn bộ cấu trúc entity Order; khi thêm trường quản trị vào database, nhiều consumer cũ phải cập nhật serializer không liên quan đến nghiệp vụ của họ.
Dịch vụ kho sử dụng mã trạng thái của hệ thống đặt hàng để điều khiển quy trình giữ hàng; nhóm đặt hàng thêm trạng thái chờ duyệt và dịch vụ kho vô tình diễn giải nó thành đã thanh toán.
Đội phát triển ba service dùng chung một thư viện domain chứa mọi entity; một phiên bản chỉ đổi cách biểu diễn địa chỉ khiến cả ba service phải nâng dependency cùng thời điểm.
Trong ứng dụng thanh toán, API gọi trực tiếp class Java của nhà cung cấp qua một module dùng chung; một khách hàng ngoài hệ thống cần tích hợp bằng HTTP nhưng không thể dùng hợp đồng đã công bố.
Một bộ xử lý tệp chọn parser từ tên class trong file cấu hình; khi chuyển từ parser tự viết sang thư viện khác, file cấu hình của hàng chục khách hàng không còn tham chiếu được class hợp lệ.
Nhóm cho phép plugin Java bên thứ ba truy cập trực tiếp Map cache mutable của ứng dụng; một plugin xóa khóa không thuộc trách nhiệm của mình và làm sai kết quả xử lý của plugin khác.
Trong hệ thống đặt lịch, lớp đặt hẹn tự lấy Clock.systemDefaultZone ở nhiều nơi; các test theo múi giờ khác nhau phải thay môi trường chạy thay vì kiểm soát phụ thuộc thời gian của riêng use case.
Ứng dụng bán hàng chỉ dùng một lớp SqlInventoryRepository cụ thể trong kiểm thử; khi cần mô phỏng lỗi hết hàng không có database, nhóm không có điểm thay thế phụ thuộc để kiểm tra quy tắc hủy đơn.
Đội đổi cổng vận chuyển thật thành stub trong CI bằng cách sửa code gọi đối tác; sau khi merge, một số môi trường production vẫn sử dụng nhầm endpoint mô phỏng vì lựa chọn implementation nằm rải trong mã.
Một dịch vụ cần tìm khách hàng qua interface CustomerLookup nhưng implementation lại trả exception chứa SDK response của bên thứ ba; client muốn xử lý 'không tìm thấy' phải import thư viện đối tác.
Trong giao diện quản trị, controller biết tên các bảng và cột database của service báo cáo; thêm một loại thống kê buộc cả đội UI và database cùng triển khai vào đúng một thời điểm.
Nhóm quản lý hệ thống thanh toán yêu cầu thay Redis bằng bộ nhớ cục bộ cho bài test; service cache đang được tạo qua static factory và giữ instance toàn cục, nên các ca test chạy song song cùng chia sẻ dữ liệu.
Ứng dụng xử lý đơn sử dụng hai implementation lưu trữ có ý nghĩa transaction khác nhau; use case dựa vào một trường hợp auto-commit của implementation cũ và mất tính nhất quán khi thay provider.
Đội backend thêm trường bắt buộc vào request của service Định danh nhưng chưa thông báo nhóm sử dụng API; consumer vẫn chạy đúng phiên bản cũ và bị từ chối toàn bộ yêu cầu khi rollout.
Trong một hệ thống nhiều module, module báo cáo import lớp helper nội bộ của module thanh toán chỉ để định dạng tiền; khi helper đổi quyền truy cập, việc build báo cáo thất bại dù hợp đồng công khai vẫn giữ nguyên.
Service thông báo yêu cầu caller tự cung cấp connection và timeout của SMTP; chuyển sang nhà cung cấp email dạng HTTP khiến mọi caller phải hiểu hạ tầng mới thay vì chỉ gửi yêu cầu thông báo.
Đội triển khai cùng một lớp điều phối cho UI và batch nhưng UI cần phản hồi nhanh còn batch cho phép retry dài; các tham số retry của dependency được truyền lên tận controller và gây khác biệt hành vi.
Một hệ thống đặt phòng có hai adapter truy cập kho dữ liệu; adapter thứ hai trả null thay vì Optional.empty cho trường hợp không có phòng, khiến cùng hợp đồng trừu tượng lại đòi hỏi nhánh xử lý riêng.
Trong pipeline phân tích dữ liệu, một component nhận trực tiếp Logger, MetricsRegistry và TransactionManager dù chỉ chuyển đổi giá trị; khi chạy công cụ đơn giản ngoài server, không thể khởi tạo component đó.
Đội chia chức năng phê duyệt thành nhiều service và truyền chuỗi callback tham chiếu phương thức nội bộ của nhau; thay đổi một nhánh yêu cầu sửa đồng thời cách callback được đăng ký ở nhiều nhóm.
Nhóm tạo adapter cho mọi phép gọi nội bộ kể cả những chức năng không có biến thể; số interface tăng nhanh, nhưng mỗi lần đổi payload mọi tầng vẫn sửa vì hợp đồng chỉ sao chép cấu trúc của implementation.
Trong dự án bảo trì lâu năm, nhóm muốn tách module tính giá khỏi web framework nhưng bản test chỉ tạo toàn bộ Spring context; một thay đổi nhỏ trong cấu hình web làm hơn trăm test tính giá thất bại dù công thức không đổi.

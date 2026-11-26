Trong ứng dụng đặt hàng Java, OrderController vừa xác thực người dùng, tính giảm giá, ghi database và gửi email; khi thay đổi mẫu thư xác nhận, nhóm phải chạy lại cả bộ kiểm thử quy tắc thanh toán.
Đội phát triển lớp CustomerProfile cho phép mọi module sửa trực tiếp trường creditLimit; một màn hình quản trị cập nhật hạn mức âm mà không đi qua kiểm tra nghiệp vụ của hồ sơ.
Hệ thống tính phí vận chuyển đặt công thức trong lớp hiển thị bảng giá; cùng đơn hàng cho số tiền khác khi được tính từ giao diện web và từ tác vụ nền.
Trong dịch vụ ngân hàng, chức năng chuyển khoản lưu số dư dưới dạng số thực rồi truyền trực tiếp cho lớp hiển thị; tiền lẻ bị sai sau nhiều giao dịch dù dữ liệu được dùng qua các lớp có trách nhiệm khác nhau.
Một API quản lý tài khoản trả trực tiếp entity ORM chứa trường nội bộ; khi database thêm thông tin kiểm toán, response công khai cũng thay đổi mà không có yêu cầu sản phẩm.
Đội tạo interface xử lý chung chỉ có phương thức execute nhận Object và trả Object; các service gọi nhau phải ép kiểu và lỗi sai cấu trúc dữ liệu chỉ xuất hiện tại runtime.
Trong mô-đun điểm thưởng, chính sách tính thưởng phụ thuộc trực tiếp vào HttpServletRequest để lấy mã khách hàng; luồng xử lý bằng batch không thể dùng chung quy tắc nếu thiếu web server.
Ứng dụng bán vé có cùng quy tắc xác minh thời hạn ở controller, repository và client; sửa ngưỡng thời gian ở một nơi khiến các luồng đồng bộ và bất đồng bộ chấp nhận vé khác nhau.
Nhóm viết lớp UserManager vừa quản lý thông tin hồ sơ, quyền truy cập, báo cáo hoạt động và mật khẩu; mỗi sprint lớp này nhận thay đổi từ bốn nhóm sản phẩm và liên tục phát sinh xung đột merge.
Trong chức năng đăng ký, validation email nằm bên trong adapter database; khi lưu bản đăng ký vào hàng đợi trước khi ghi database, các địa chỉ không hợp lệ vượt qua bước kiểm tra.
Một module thanh toán khởi tạo trực tiếp SDK của cổng đối tác và truy cập biến cấu hình toàn cục; các unit test về giới hạn số tiền cần môi trường mạng và secret dù không gọi thanh toán thật.
Nhóm thay PostgreSQL bằng một kho dữ liệu khác nhưng hàng chục use case dùng trực tiếp kiểu Page của thư viện ORM; thay đổi hạ tầng kéo theo sửa nhiều hợp đồng nghiệp vụ.
Ứng dụng quản lý đơn hàng cho phép thêm cách tính chiết khấu theo mùa; mỗi lần bổ sung chính sách, developer phải chỉnh nhiều chuỗi if-else trong lớp đang ổn định.
Trong một trình xuất tài liệu, chức năng PDF, Excel và CSV được chọn bằng tên lớp concrete; người bảo trì thêm định dạng mới nhưng các màn hình cũ không nhận nó nếu không cập nhật switch.
Đội có lớp BaseAccount cho phép rút tiền; lớp FixedDepositAccount kế thừa nhưng luôn ném lỗi khi rút sớm, khiến code xử lý Account chung không giữ được kỳ vọng về hành vi.
Phần mềm kế toán định nghĩa một interface ReportProcessor với mười hai phương thức từ in giấy tới gửi email; bộ xử lý chỉ xuất CSV vẫn bị buộc cung cấp các thao tác không hỗ trợ.
Trong hệ thống chăm sóc khách hàng, giao diện xử lý phản hồi phụ thuộc vào implementation gửi SMS cụ thể; chuyển kênh thông báo sang email làm thay đổi cả luồng quản lý ticket.
Nhóm sử dụng singleton mutable lưu tenantId hiện tại cho các dịch vụ; khi hai request thuộc hai doanh nghiệp chạy cùng lúc, dữ liệu đơn hàng có thể được lấy theo tenant không đúng.
Ứng dụng đặt lịch kiểm tra ngày hết hạn bằng cách gọi đồng hồ hệ điều hành trực tiếp ở nhiều lớp; unit test chạy gần nửa đêm cho kết quả khác nhau dù bộ dữ liệu đầu vào không đổi.
Đội kiểm thử phải tạo context Spring đầy đủ để kiểm tra phép tính hoa hồng đơn giản vì phương thức đang khởi tạo database, logger và HTTP client trong cùng constructor.
Trong module xuất hóa đơn, phương thức dài vài trăm dòng vừa lọc đơn, tính thuế, tạo PDF và gửi email; một lỗi trong phần gửi khiến toàn bộ quá trình bị chạy lại và xuất hóa đơn trùng.
Nhóm đưa hơn một trăm hàm không liên quan vào lớp CommonUtils; khi thay quy tắc chuẩn hóa địa chỉ, bản phát hành của cả những module chỉ dùng hàm định dạng ngày cũng bị ảnh hưởng.
Một hệ thống báo cáo có lớp OrderService gọi trực tiếp các lớp cụ thể của Kho và Thanh toán, còn hai lớp kia lại gọi ngược OrderService; việc khởi tạo dependency dẫn đến chu trình và khó tách test.
Trong nền tảng học tập, logic tính điểm sử dụng lại một hàm tiện ích của giao diện có tham số màu sắc và locale; thay đổi giao diện làm module chấm điểm phải biên dịch lại.
Ứng dụng quản lý sản phẩm cho phép thay đổi trạng thái bằng setter công khai mà không giới hạn chuyển trạng thái; một đường API trực tiếp đưa sản phẩm từ Đã xóa trở lại Đang bán.
Đội định nghĩa dữ liệu đầu vào bằng Map<String,Object> cho mọi nghiệp vụ; khi chức năng thêm trường số lượng bắt buộc, các client truyền kiểu chuỗi vẫn được biên dịch và gây lỗi giữa luồng.
Trong hệ thống vận chuyển, nhiều thuật toán tối ưu tuyến đường cùng kế thừa một lớp cha chứa cache và kết nối database; lỗi cache ảnh hưởng cả những thuật toán vốn không cần cache.
Nhóm tách từng phép gán trường thành một interface và hàng chục lớp chỉ có một dòng; khi thay đổi cấu trúc đơn hàng, số file cần mở và dependency phải cấu hình tăng mạnh dù nghiệp vụ không đổi.
Ứng dụng có hai module chênh lệch chỉ một ít ở cách tính phí; đội trích xuất abstraction chung quá sớm và thêm nhiều cờ boolean để bao phủ mọi ngoại lệ của hai bên.
Trong service tìm kiếm, lớp hiển thị tự xây SQL thay vì giao một yêu cầu trừu tượng; đổi cách đánh chỉ mục hoặc chuyển nguồn dữ liệu khiến phần giao diện cần viết lại.
Một ứng dụng hội viên có thể xác minh mã ưu đãi qua nhiều nhà cung cấp nhưng mỗi controller tạo dependency của riêng mình; cùng một cấu hình sinh ra cách xử lý lỗi khác nhau giữa các màn hình.
Đội QA chỉ kiểm tra private method của lớp tính thuế bằng reflection; sau khi refactor tách trách nhiệm mà giữ nguyên kết quả công khai, hàng trăm test bị hỏng dù hành vi người dùng không thay đổi.
Trong hệ thống thanh toán, một exception kỹ thuật bị bắt ở lớp repository rồi chuyển thành kết quả nghiệp vụ 'không đủ tiền'; người dùng nhận thông báo sai mỗi khi database mất kết nối.
Chức năng duyệt hồ sơ có nhiều điều kiện rủi ro nhưng controller chỉ xác minh rằng service được gọi; lỗi chấp thuận hồ sơ không đạt điều kiện vẫn không bị phát hiện bởi bộ test.
Nhóm chia các service thật nhỏ theo từng thao tác đọc/ghi mà không xét ranh giới trách nhiệm; quy trình đặt đơn đơn giản trở thành chuỗi gọi mạng dài và khó truy vết.
Ứng dụng kế toán muốn hỗ trợ batch và API online; phần kiểm tra quyền được đặt duy nhất ở web adapter, nên batch import đi trực tiếp vào use case có thể bỏ qua chính sách chung.
Trong một dự án nhiều nhóm, tên phương thức save mang ý nghĩa tạo mới, cập nhật và phê duyệt tùy chỗ gọi; người mới không phân biệt được hành vi vì hợp đồng abstraction không diễn đạt ý định.
Nhóm phát triển bỏ qua mọi lớp interface để tăng tốc MVP; khi đối tác thứ hai yêu cầu cách giao tiếp khác, toàn bộ logic xử lý giao dịch đã chứa các điều kiện đặc thù của đối tác đầu tiên.
Một lớp OrderSummary tính dữ liệu tạm thời nhưng có thể tự ghi vào kho lưu trữ qua một getter; khi tăng số lần render màn hình, số lần cập nhật database cũng tăng mà caller không hay biết.
Đội kiến trúc muốn giảm coupling bằng cách tạo hàng chục adapter và event nội bộ; khi thêm một trường đơn hàng, phải sửa cả chuỗi ánh xạ và không rõ chi phí trừu tượng mới có tương xứng độ ổn định nghiệp vụ.

Ứng dụng desktop Java cần hiển thị Button, Checkbox và Dialog nhất quán trên Windows và macOS; mỗi màn hình tự tạo widget theo hệ điều hành nên hộp thoại macOS đôi khi chứa nút mang giao diện Windows.
Trong trình quản lý giao diện sáng và tối, một form tạo TextField từ theme sáng nhưng PopupMenu từ theme tối; các thành phần đều hoạt động riêng lẻ nhưng màu nền và chữ không còn tương thích.
Đội xây ứng dụng nhiều thương hiệu, mỗi thương hiệu có một họ logo, phông chữ và thành phần điều hướng; khi thêm thương hiệu mới, hàng chục màn hình phải sửa nhiều lời gọi tạo đối tượng.
Một trò chơi có các họ nhân vật, vũ khí và hiệu ứng cho từng thế giới; người chơi chọn thế giới băng nhưng vật phẩm rơi lại mang hiệu ứng lửa do hai thành phần được tạo từ các bộ cấu hình khác nhau.
Phần mềm quản lý thiết bị IoT hỗ trợ hai nhà sản xuất cảm biến; một phiên giám sát dùng bộ đọc dữ liệu của hãng A với bộ hiệu chuẩn của hãng B và hiển thị nhiệt độ sai.
Trong bộ công cụ xuất tài liệu, các họ PDF, HTML và Markdown cùng cần tạo Heading, Table và Image; code giao diện gọi trực tiếp class concrete của từng định dạng nên không thể đổi toàn bộ kiểu xuất theo cấu hình.
Ứng dụng kết nối nhiều cloud provider cần các thành phần lưu tệp, hàng đợi và quản lý secret phù hợp từng nhà cung cấp; service lưu tệp lên provider A nhưng tạo URL truy cập bằng SDK provider B.
Một framework truy cập dữ liệu có dialect PostgreSQL và MySQL, mỗi dialect tạo đối tượng xây câu truy vấn và phân trang; bộ phân trang MySQL bị ghép với bộ quote identifier PostgreSQL khiến SQL không hợp lệ.
Đội tích hợp thanh toán có bộ tạo request, parser response và handler webhook cho từng cổng; một đợt deploy nhầm parser của cổng cũ với request mới làm giao dịch thành công nhưng không được ghi nhận.
Trong hệ thống vận chuyển đa đối tác, nhãn kiện, mã theo dõi và bộ đọc trạng thái phải thuộc cùng một chuẩn; bộ in nhãn của hãng A được dùng với mã theo dõi của hãng B nên nhân viên không tra cứu được.
Nhóm phát triển bộ giao diện đa nền tảng dùng abstract factory để sinh Menu và Toolbar; khi thêm widget DatePicker bắt buộc, mọi factory hiện hành thiếu cách tạo thành phần mới.
Ứng dụng hỗ trợ ba họ công cụ báo cáo khác nhau; khi triển khai một họ mới, nhóm chỉ muốn bổ sung implementation nhưng nơi tạo từng loại widget vẫn chứa nhiều if-else theo tên nhà cung cấp.
Trong ứng dụng thương mại, lớp Checkout gọi new trực tiếp bộ xử lý hóa đơn cụ thể mặc dù đã có factory cho bộ tính thuế và bộ gửi biên nhận; một biến thể cấu hình vẫn trộn hai họ phụ thuộc.
Nhóm đặt factory ở module giao diện nhưng lớp nghiệp vụ cần tạo bộ xác minh thanh toán cùng họ; module domain bắt đầu import framework UI chỉ để lựa chọn implementation.
Ứng dụng nhận tên giao diện từ biến cấu hình, nhưng mã theme không được nhận diện khiến factory trả null; lỗi chỉ xuất hiện nhiều bước sau khi tạo hàng loạt thành phần.
Trong một bộ phần mềm ngân hàng, các thành phần tính lãi, lập lịch trả nợ và xuất hợp đồng được đóng gói theo gói sản phẩm; service chọn factory theo khách hàng lúc đăng nhập nhưng dùng lại lựa chọn cho khách tiếp theo.
Đội bảo trì ứng dụng Windows và Linux tạo factory một lần ở thời điểm chạy test; khi suite mô phỏng thay đổi nền tảng trong cùng JVM, các đối tượng được tạo sau vẫn thuộc họ nền tảng ban đầu.
Một hệ thống in tem hỗ trợ khổ A4 và khổ cuộn, mỗi khổ có bộ căn lề, font và mã vạch; việc thay riêng font trong lúc in làm một loại tem vượt khỏi mép giấy.
Ứng dụng tìm kiếm sử dụng các họ engine có bộ indexer, analyzer và query builder riêng; index được tạo bằng analyzer của engine A nhưng truy vấn lại chạy với analyzer của engine B nên kết quả rỗng.
Đội xây môi trường test cho PostgreSQL và MongoDB, trong đó repository và bộ tạo dữ liệu cần đồng bộ; một test chọn fake repository PostgreSQL nhưng lại dùng bộ seed dữ liệu MongoDB.
Trong phần mềm quản lý trường học, mỗi hệ thống quốc gia có bộ tạo lịch học, báo cáo điểm và định dạng ngày; bộ phận triển khai trộn các thành phần của hai nước và báo cáo sai niên khóa.
Một hệ thống bảo mật hỗ trợ các bộ thuật toán mã hóa; đối tượng ký dữ liệu được tạo từ cấu hình phiên bản A còn đối tượng xác minh từ phiên bản B, khiến thông điệp hợp lệ bị từ chối.
Ứng dụng cho phép người dùng đổi ngôn ngữ ngay khi đang mở nhiều cửa sổ; một số Dialog mới tạo theo locale mới nhưng các MessageFormatter được lưu từ locale cũ tạo thông báo trộn ngôn ngữ.
Trong dự án Java, một factory tạo ra đối tượng kết nối mạng và parser theo cùng phiên bản giao thức; parser không thể dùng lại sau khi kết nối được nâng giao thức giữa phiên.
Đội phát triển đưa phụ thuộc cấu hình và kết nối database vào constructor của từng concrete factory; test muốn tạo giao diện giả phải khởi động các tài nguyên thật dù chỉ kiểm tra cách chọn họ sản phẩm.
Một thư viện plugin cho phép đăng ký factory cho nhà cung cấp mới; plugin được nạp thành công nhưng không đảm bảo mọi sản phẩm trong họ đều tuân theo phiên bản interface mà ứng dụng hiện tại yêu cầu.
Trong hệ thống bán vé, một bộ thành phần theo loại sự kiện gồm Ticket, QRRenderer và CheckInValidator; validator của loại sự kiện mới không chấp nhận QR do renderer cũ tạo.
Nhóm dùng factory chung cho ứng dụng di động để tạo thông báo, bộ điều hướng và hệ thống lưu trữ; một thành phần cần quyền thiết bị không có trên nền tảng chạy test và toàn bộ factory không khởi tạo được.
Trong trình phát media, các họ codec cần decoder âm thanh, decoder video và bộ đồng bộ thời gian tương ứng; sử dụng bộ đồng bộ của họ khác làm âm thanh và hình ảnh bị lệch dần.
Đội dự án chỉ cần tạo một loại client HTTP theo môi trường, nhưng đã xây nhiều lớp abstract factory không có họ sản phẩm liên quan; một thay đổi nhỏ buộc cập nhật nhiều interface mà không đem lại khả năng phối hợp mới.
Ứng dụng triển khai hai biến thể theme và hai biến thể nền tảng độc lập; số lượng factory concrete tăng theo mọi tổ hợp theme–OS dù không phải mọi cặp đều cần sản phẩm riêng.
Trong quá trình đổi nhận diện thương hiệu, nhóm cần chuyển cả bộ widget một cách nhất quán; factory được thay ngay giữa lúc dựng một màn hình nên nửa đầu và nửa sau thuộc hai họ khác nhau.
Một dịch vụ dùng nhiều thread chung một factory có cache widget mutable; object được tạo cho tenant A xuất hiện lại trong response của tenant B vì khóa cache không gồm tenant.
Trong hệ thống báo cáo, đối tượng tạo bởi factory mang cấu hình khổ giấy có thể thay đổi; một report đang render thì factory bị cập nhật khổ giấy cho report khác, làm bố cục bị lệch.
Nhóm viết unit test cho abstract factory chỉ xác minh sản phẩm không null; factory dành cho chế độ Dark trả đúng class nhưng chứa màu chữ khó đọc trên nền tối và suite vẫn PASS.
Đội phát triển muốn thử tính tương thích của từng họ sản phẩm; hiện test từng Button, Dialog và Menu độc lập nhưng không có kịch bản sử dụng ba thành phần cùng nhau trong một luồng.
Ứng dụng xuất hóa đơn hoạt động với factory cấu hình cho thị trường Việt Nam, nhưng lúc chạy batch quốc tế bộ cấu hình tiền tệ cũ được dùng lại dù ngày và thuế đã lấy theo thị trường mới.
Nhóm thêm một phương thức tạo thành phần mới vào interface factory; các package factory do bên thứ ba cung cấp chưa được cập nhật nên sản phẩm chính không thể khởi động sau nâng cấp.
Trong một công cụ xây dựng UI, abstract factory bị lộ ra ngoài qua class implementation cụ thể ở tầng nghiệp vụ; khi đổi thư viện widget, nhiều module phải sửa import dù chỉ kỳ vọng dùng các sản phẩm trừu tượng.
Một nền tảng xử lý dữ liệu hỗ trợ hai họ serializer và deserializer theo schema v1/v2; dữ liệu vừa được ghi bằng v2 nhưng service đọc dùng factory v1 vì bản cấu hình cũ được cache, gây lỗi sau rolling deploy.

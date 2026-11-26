Bạn sẽ mô tả vòng đời của một kết nối cơ sở dữ liệu từ lúc ứng dụng yêu cầu đến lúc tài nguyên được trả lại như thế nào?
Trong ứng dụng Java, bạn phân biệt vai trò của JDBC driver, DriverManager và DataSource như thế nào?
Bạn sẽ lựa chọn DriverManager hay DataSource cho một dịch vụ có nhiều yêu cầu đồng thời dựa trên các tiêu chí nào?
Một đối tượng Connection trong JDBC đại diện cho những tài nguyên và trạng thái nào ở phía ứng dụng và cơ sở dữ liệu?
Những bước mạng, xác thực và khởi tạo phiên nào có thể diễn ra trước khi một kết nối vật lý sẵn sàng chạy truy vấn?
Bạn sẽ xử lý các loại lỗi nào khi mở kết nối cơ sở dữ liệu và phân biệt chúng với lỗi khi thực thi câu lệnh ra sao?
Chi phí tạo mới kết nối vật lý ảnh hưởng thế nào đến độ trễ của ứng dụng dưới tải?
Trong JDBC, trách nhiệm đóng ResultSet, Statement và Connection nên được phân chia như thế nào?
Bạn sẽ dùng cơ chế quản lý tài nguyên của Java như thế nào để bảo đảm kết nối được giải phóng khi một thao tác ném ngoại lệ?
Khi ứng dụng gọi close() trên Connection lấy từ pool, điều gì cần xảy ra với kết nối logic và kết nối vật lý?
Bạn sẽ giải thích khác biệt giữa một kết nối đang được mượn, một kết nối nhàn rỗi và một kết nối đã bị loại khỏi pool như thế nào?
Bạn sẽ mô tả chuỗi thao tác mượn kết nối, chạy truy vấn và trả kết nối cho một HTTP request như thế nào?
Chế độ auto-commit của JDBC tác động thế nào đến ranh giới transaction và thời điểm thay đổi dữ liệu được ghi nhận?
Bạn sẽ xác định ranh giới transaction cho một nghiệp vụ gồm nhiều câu lệnh SQL dựa trên những yêu cầu nào?
Bạn sẽ chọn mức cô lập transaction như thế nào khi cân nhắc tính đúng đắn, hiện tượng đọc bất thường và hiệu năng?
Nếu hai request đồng thời cập nhật cùng một bản ghi, bạn sẽ phân tích tác động của transaction và khóa dữ liệu ra sao?
Một transaction cần commit hoặc rollback theo những nhánh thành công và lỗi nào để tránh giữ kết nối quá lâu?
Nếu thao tác thứ ba trong một transaction gồm bốn thao tác thất bại, bạn sẽ thiết kế đường xử lý và khôi phục trạng thái như thế nào?
Bạn sẽ kiểm soát thời gian giữ transaction khi luồng nghiệp vụ cần gọi API bên ngoài như thế nào?
Các transaction kéo dài ảnh hưởng ra sao đến khóa cơ sở dữ liệu, thời gian mượn kết nối và khả năng phục vụ request khác?
Khi nhiều tầng service cùng tham gia một nghiệp vụ, bạn sẽ xác định bên nào sở hữu transaction và quyền đóng kết nối ra sao?
Bạn sẽ xem xét điều gì khi một hàm con mở transaction mới hoặc thay đổi ngữ cảnh transaction của hàm gọi?
Trạng thái auto-commit, mức cô lập, read-only và schema có thể ảnh hưởng các lần tái sử dụng cùng kết nối ra sao?
Bạn sẽ xác minh pool khôi phục các thiết lập phiên về giá trị phù hợp trước khi giao kết nối cho request tiếp theo như thế nào?
Những rủi ro nào xuất hiện khi cùng một Connection được chia sẻ giữa nhiều thread hoặc tác vụ bất đồng bộ?
Bạn sẽ xử lý việc giữ kết nối trong một tác vụ nền hoặc luồng xử lý kéo dài khác với request ngắn như thế nào?
Pool thường khởi tạo, cấp phát thêm, kiểm tra và thu hồi các kết nối vật lý theo những sự kiện nào?
Các thông số số kết nối tối đa và số kết nối nhàn rỗi tối thiểu ảnh hưởng thế nào đến tài nguyên và khả năng chịu đột biến tải?
Bạn sẽ ước lượng kích thước pool ban đầu từ lưu lượng, thời gian giữ kết nối và khả năng của máy chủ cơ sở dữ liệu như thế nào?
Khi có nhiều instance ứng dụng, bạn sẽ tính tổng số kết nối tiềm năng để tránh vượt giới hạn kết nối của cơ sở dữ liệu ra sao?
Vì sao tăng kích thước pool có thể làm thông lượng giảm hoặc gây thêm tranh chấp dù ứng dụng đang chờ kết nối?
Bạn sẽ phân biệt thời gian chờ lấy kết nối từ pool với thời gian thiết lập kết nối vật lý như thế nào?
Bạn sẽ thiết kế phản hồi cho request khi hết thời gian chờ mượn kết nối để hệ thống không tiếp tục quá tải ra sao?
Các timeout khi kết nối mạng, đọc dữ liệu, thực thi truy vấn, chờ pool và chạy transaction khác nhau về phạm vi như thế nào?
Trong một request có giới hạn thời gian tổng thể, bạn sẽ phối hợp các timeout của ứng dụng và cơ sở dữ liệu thế nào?
Bạn sẽ lựa chọn thời gian nhàn rỗi tối đa và tuổi thọ tối đa của kết nối dựa trên những yếu tố vận hành nào?
Nếu máy chủ cơ sở dữ liệu hoặc thiết bị mạng đóng kết nối nhàn rỗi sớm hơn pool dự kiến, bạn sẽ điều chỉnh cấu hình ra sao?
Bạn sẽ dùng kiểm tra tính hợp lệ của kết nối vào những thời điểm nào và đánh giá chi phí kiểm tra ra sao?
Pool cần phát hiện và xử lý kết nối hỏng như thế nào sau khi cơ sở dữ liệu khởi động lại hoặc xảy ra failover?
Bạn sẽ phân tích các lần tạo và hủy kết nối liên tục để tìm nguyên nhân gây tăng độ trễ như thế nào?
Bạn định nghĩa rò rỉ kết nối trong ứng dụng dùng pool như thế nào và phân biệt nó với việc giữ kết nối lâu nhưng hợp lệ ra sao?
Những đường đi của chương trình nào dễ bỏ sót thao tác trả kết nối khi có ngoại lệ hoặc hủy tác vụ?
Bạn sẽ dùng ngưỡng phát hiện rò rỉ kết nối và thông tin call stack như thế nào để điều tra mà không gây báo động giả?
Khi một truy vấn chạy lâu kích hoạt cảnh báo rò rỉ, bạn sẽ xác minh nguyên nhân trước khi sửa mã như thế nào?
Bạn sẽ kiểm tra vòng đời của Statement, ResultSet và luồng đọc dữ liệu để xác định tài nguyên nào còn giữ kết nối ra sao?
Những chỉ số active, idle, total và pending của pool phản ánh sức khỏe hệ thống như thế nào khi quan sát cùng lúc?
Bạn sẽ đánh giá số lần chờ kết nối, thời gian chờ theo phân vị và số lần timeout của pool như thế nào?
Làm sao bạn tách thời gian chờ mượn kết nối, thời gian thực thi SQL và thời gian xử lý nghiệp vụ trong một request chậm?
Bạn sẽ liên kết log, trace và các số đo pool để tìm request hoặc transaction đang giữ kết nối lâu như thế nào?
Bạn sẽ thiết lập ngưỡng cảnh báo bão hòa pool như thế nào để phát hiện sớm mà không tạo nhiều cảnh báo nhiễu?
Khi ghi log lỗi kết nối, bạn sẽ giữ thông tin chẩn đoán hữu ích mà không làm lộ mật khẩu, chuỗi kết nối hoặc dữ liệu nhạy cảm ra sao?
Bạn sẽ quản lý thông tin đăng nhập cơ sở dữ liệu trong cấu hình triển khai và kho bí mật như thế nào?
Bạn sẽ giới hạn quyền của tài khoản ứng dụng trên cơ sở dữ liệu như thế nào để giảm thiểu hậu quả khi bị lộ thông tin đăng nhập?
Khi bật TLS cho kết nối cơ sở dữ liệu, bạn sẽ kiểm tra những điều gì về chứng chỉ và xác thực máy chủ?
Bạn sẽ thiết kế quy trình xoay vòng mật khẩu hoặc chứng chỉ để các kết nối cũ được thay thế mà không gián đoạn dịch vụ như thế nào?
Khi ứng dụng sử dụng proxy cơ sở dữ liệu hoặc pool ở tầng trung gian, bạn sẽ đánh giá tác động của nhiều tầng quản lý kết nối ra sao?
Bạn sẽ quyết định dùng chung hay tách pool cho tác vụ đọc, ghi và xử lý nền dựa trên đặc điểm tải như thế nào?
Trong mô hình nhiều tenant hoặc nhiều cơ sở dữ liệu, bạn sẽ kiểm soát số pool và tổng ngân sách kết nối thế nào?
Khi request đồng thời tăng mạnh, bạn sẽ áp dụng giới hạn đồng thời hoặc cơ chế giảm tải nào trước điểm mượn kết nối?
Bạn sẽ phân biệt tình trạng thiếu kết nối trong pool với deadlock transaction hoặc chờ khóa trong cơ sở dữ liệu như thế nào?
Khi pool luôn đầy nhưng CPU cơ sở dữ liệu thấp, bạn sẽ kiểm tra các giả thuyết về khóa, giao dịch dài và rò rỉ theo thứ tự nào?
Khi pool đầy và CPU cơ sở dữ liệu cao, bạn sẽ phân biệt vấn đề truy vấn kém hiệu quả với cấu hình pool chưa phù hợp ra sao?
Nếu chỉ số pool báo còn kết nối nhàn rỗi nhưng một nhóm request vẫn chờ lâu, bạn sẽ kiểm tra những khác biệt về pool hoặc luồng thực thi nào?
Khi xuất hiện lỗi chờ kết nối theo từng đợt trong giờ cao điểm, bạn sẽ thu thập dữ liệu gì để tái hiện và xác định nút nghẽn?
Sau một lần gián đoạn mạng ngắn, bạn sẽ quan sát và kiểm tra quá trình pool phục hồi như thế nào?
Khi cơ sở dữ liệu chuyển sang nút dự phòng, bạn sẽ bảo đảm ứng dụng không tiếp tục dùng kết nối đã mất hiệu lực ra sao?
Bạn sẽ dùng kiểm thử tăng tải để xác định ngưỡng bão hòa, độ trễ chờ pool và điểm giảm thông lượng như thế nào?
Trong bài kiểm thử, bạn sẽ mô phỏng việc không trả kết nối và xác minh khả năng phát hiện, cảnh báo, phục hồi ra sao?
Bạn sẽ đánh giá tác động của việc tăng số bản sao ứng dụng lên tổng kết nối và thời gian chờ cơ sở dữ liệu như thế nào?
Nếu thời gian phản hồi tăng sau khi tăng số kết nối tối đa, bạn sẽ kiểm tra bằng chứng nào trước khi thay đổi cấu hình lần nữa?
Bạn sẽ quyết định ưu tiên tối ưu câu lệnh SQL, rút ngắn transaction hay tăng giới hạn pool dựa trên số liệu nào?
Bạn sẽ xử lý các truy vấn đọc dữ liệu theo luồng hoặc tập kết quả rất lớn như thế nào để tránh chiếm kết nối quá lâu?
Trong quá trình tắt ứng dụng hoặc triển khai phiên bản mới, bạn sẽ ngừng nhận việc và đóng pool theo trình tự nào để tránh mất giao dịch?
Bạn sẽ xây dựng kịch bản ứng phó khi hết kết nối cơ sở dữ liệu trên toàn cụm ứng dụng như thế nào?
Nếu phải thiết lập dashboard vận hành pool cho một dịch vụ mới, bạn sẽ chọn những biểu đồ và câu hỏi chẩn đoán nào để hỗ trợ trực ca?
Bạn sẽ đặt các tiêu chí chấp nhận nào cho cấu hình pool trước khi triển khai chính thức dưới tải thực tế?

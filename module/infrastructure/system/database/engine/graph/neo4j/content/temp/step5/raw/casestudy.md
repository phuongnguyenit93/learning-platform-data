Một mạng xã hội lưu người dùng và mối quan hệ theo dõi trong Neo4j; truy vấn danh sách người mà tài khoản A đang theo dõi lại trả cả những người chỉ theo dõi A sau khi đội phát triển thay đổi cách mô hình hóa chiều relationship.
Ứng dụng quản lý chuỗi cung ứng cần biểu diễn nhà cung cấp, linh kiện, nhà máy và hợp đồng trong property graph; cùng một nhà cung cấp có nhiều hợp đồng với thời gian hiệu lực khác nhau nhưng mô hình hiện tại chỉ giữ một thuộc tính giá trên node nhà cung cấp.
Hệ thống quản lý nhân sự có một nhân viên đồng thời thuộc nhiều nhóm dự án và từng đổi người quản lý; báo cáo sơ đồ tổ chức ở thời điểm quá khứ bị sai vì relationship hiện tại ghi đè lịch sử.
Nền tảng học trực tuyến lưu học viên, khóa học và quan hệ đăng ký; nhóm đang cân nhắc đặt tiến độ học trên node khóa học hay trên relationship để phản ánh tiến độ riêng của từng học viên.
Ứng dụng tìm bạn chung chỉ muốn đề xuất các tài khoản cách người dùng hai bước kết nối và chưa kết bạn trực tiếp; kết quả Cypher có hàng loạt bản ghi trùng do hai người có nhiều bạn chung.
Một kho kiến thức lưu tài liệu, chủ đề và quan hệ trích dẫn; truy vấn đường đi liên quan từ tài liệu gốc vượt qua nhiều chủ đề trung gian khiến số đường đi trả về tăng đột biến khi dữ liệu lớn lên.
Dịch vụ giao hàng tìm lộ trình ít chặng nhất giữa hai điểm kho; kết quả Cypher chọn tuyến có ba chặng nhưng tổng thời gian di chuyển lại lâu hơn tuyến có bốn chặng vì thời lượng nằm trên từng relationship.
Ứng dụng chỉ đường cần tránh các đoạn đường đang bảo trì và chỉ đi qua tuyến hợp lệ theo loại phương tiện; kết quả tìm đường hiện tại vẫn bao gồm relationship đã bị đánh dấu ngừng sử dụng.
Nhóm phát hiện gian lận muốn tìm vòng chuyển tiền quay lại tài khoản ban đầu trong một khoảng thời gian, nhưng truy vấn đường đi không giới hạn số bước khiến thời gian chạy tăng mạnh trên nhóm tài khoản giao dịch dày đặc.
Hệ thống quan hệ đối tác coi hợp tác hai chiều là hai relationship có hướng; quá trình nhập dữ liệu đôi khi tạo cả hai chiều, đôi khi chỉ một chiều, khiến thống kê số đối tác giữa các đơn vị không thống nhất.
Báo cáo danh sách khách hàng cần hiển thị cả người chưa có đơn hàng; sau khi bổ sung điều kiện lọc thuộc tính của đơn hàng trong Cypher, các khách hàng không có quan hệ mua hàng biến mất khỏi kết quả.
Dashboard tính tổng doanh thu theo khu vực bằng cách nối khách hàng, đơn hàng và mặt hàng; một đơn hàng có nhiều dòng chi tiết làm doanh thu bị cộng lặp so với số liệu ở hệ thống nguồn.
Hai luồng đồng thời nhập cùng một khách hàng từ các hệ thống khác nhau; dù đều dùng MERGE, Neo4j xuất hiện nhiều node có cùng mã khách hàng vì cơ sở dữ liệu chưa áp dụng ràng buộc định danh phù hợp.
Dữ liệu sản phẩm có mã sản phẩm trùng hoặc thiếu ở một số bản ghi lịch sử; nhóm chuẩn bị thêm uniqueness constraint nhưng việc triển khai schema thất bại trên dữ liệu đang tồn tại.
Một lô nhập hàng triệu node có thuộc tính ngày tháng dưới nhiều kiểu dữ liệu và định dạng khác nhau; truy vấn lọc theo khoảng thời gian trả kết quả thiếu và không ổn định giữa các nguồn.
Trang tra cứu khách hàng thường lọc node theo mã tài khoản, nhưng profile truy vấn cho thấy quét phần lớn node trước khi trả một kết quả dù tập dữ liệu có hàng chục triệu bản ghi.
Đội vận hành đã tạo index cho thuộc tính trạng thái đơn hàng, song truy vấn vẫn chậm khi hầu hết đơn hàng có cùng trạng thái và phần tiếp theo phải mở rộng nhiều relationship.
Cổng tìm kiếm kiến thức yêu cầu tra cứu gần đúng theo tên bài viết tiếng Việt, còn truy vấn hiện tại dùng điều kiện chứa chuỗi trên hàng triệu node khiến độ trễ tăng theo kích thước kho dữ liệu.
Một node đại diện cho tài khoản quản trị được kết nối với hàng triệu sự kiện; truy vấn thống kê các sự kiện gần đây phải duyệt lượng relationship quá lớn và chậm hơn nhiều so với tài khoản thường.
Truy vấn gợi ý sản phẩm duyệt nhiều lớp khách hàng, lượt mua và sản phẩm; khi tăng độ sâu tìm kiếm từ hai lên năm bước, số kết quả trung gian và mức dùng bộ nhớ tăng mạnh dù chỉ lấy 20 gợi ý cuối cùng.
Ứng dụng tìm đường liên hệ giữa các cá nhân nhận nhiều lộ trình có node lặp lại và vòng quay về điểm cũ; người dùng kỳ vọng các đường đi hợp lệ chỉ đi qua mỗi người một lần.
Một truy vấn Cypher ghép hai tập node không có quan hệ liên kết rồi lọc ở phần sau; khi triển khai cho dữ liệu thật, bộ thực thi tạo tích Descartes rất lớn và thời gian phản hồi tăng hàng trăm lần so với dữ liệu thử nghiệm.
Nhóm phát triển tối ưu màn hình đề xuất bằng EXPLAIN và PROFILE; truy vấn được kỳ vọng đi từ một node tìm theo khóa duy nhất nhưng kế hoạch thực thi lại bắt đầu bằng quét nhãn có số lượng node rất lớn.
Một tác vụ phân tích cộng đồng gom hàng trăm nghìn đường đi vào một danh sách lớn trong Cypher; truy vấn hết bộ nhớ trong lúc dựng kết quả dù số dòng trả về cho API cuối cùng khá ít.
Pipeline dùng LOAD CSV nhập dữ liệu quan hệ giữa sản phẩm và danh mục; sau lần chạy lại vì mất mạng, số relationship tăng gấp đôi trong khi số node không đổi.
Hệ thống nạp dữ liệu từ nhiều bảng quan hệ cũ sang Neo4j; một số bản ghi liên kết tham chiếu đến node chưa được nhập, khiến các relationship tương ứng bị thiếu trong đồ thị sau khi đối soát.
Đội nhập dữ liệu chạy nhiều luồng MERGE cập nhật các node dùng chung, thấy transaction chờ khóa tăng và một số lô bị retry nhiều lần ngay trong giờ người dùng đang truy vấn.
Sản phẩm đang đổi mô hình từ relationship có thuộc tính sang node sự kiện trung gian để lưu lịch sử nhiều lần tương tác; API cũ và API mới cùng ghi dữ liệu trong giai đoạn chuyển đổi, khiến số liệu giữa hai kiểu truy vấn khác nhau.
Khi yêu cầu xóa hồ sơ người dùng theo quy định lưu trữ, thao tác xóa node thất bại vì node còn nhiều relationship; đội phát triển cần xác định phạm vi các liên kết và dữ liệu liên quan phải xử lý.
Một ứng dụng Java tạo Neo4j Driver mới cho mỗi request HTTP và không đóng session trong một số nhánh lỗi; sau giờ cao điểm, số kết nối và tài nguyên mạng tăng dù lượng request đã giảm.
API tìm kiếm xây câu Cypher bằng cách ghép trực tiếp giá trị tên người dùng nhận từ query string; một đầu vào chứa ký tự đặc biệt làm truy vấn lỗi và nhóm an ninh đặt câu hỏi về khả năng can thiệp cấu trúc truy vấn.
Một nghiệp vụ Java Driver thực hiện nhiều lần đọc và ghi có phụ thuộc nhau, nhưng mỗi lần dùng một session hoặc transaction riêng; khi bước cuối thất bại, đồ thị còn một phần thay đổi từ các bước trước.
Sau khi tạo relationship mới trên nút ghi của Neo4j cluster, API lập tức đọc qua nút khác và thỉnh thoảng chưa thấy dữ liệu vừa ghi; dịch vụ Java đang thực hiện nhiều request nối tiếp nhưng không truyền ngữ cảnh nhất quán giữa chúng.
Ứng dụng Spring Data Neo4j trả danh sách dự án kèm nhiều lớp quan hệ thành viên và nhiệm vụ; truy vấn generated cho màn hình danh sách trở nên nặng khi một dự án có hàng nghìn node liên quan.
Một dịch vụ Spring Boot kết nối tới Neo4j có nhiều database; repository Spring Data Neo4j trả tập dữ liệu trống trên production dù Cypher chạy thủ công ở database nghiệp vụ vẫn trả kết quả.
Khi cập nhật aggregate có nhiều quan hệ bằng Spring Data Neo4j, nhóm thấy một số relationship cũ không còn được lưu như kỳ vọng sau khi ghi lại thực thể gốc với tập quan hệ tải chưa đầy đủ.
Một API phân tích đồ thị thực thi Cypher có độ sâu biến đổi tùy đầu vào; ở mức yêu cầu bất thường, truy vấn kéo dài hàng phút và chiếm tài nguyên trong khi các API tra cứu cơ bản bị chậm theo.
Máy chủ Neo4j phục vụ nhiều truy vấn đọc có thời gian ổn định lúc đầu nhưng chậm dần khi dữ liệu vượt xa bộ nhớ; dashboard cho thấy hoạt động I/O đĩa tăng trong giờ cao điểm.
Trong đợt tạo index mới cho đồ thị lớn, bộ phận vận hành nhận thấy truy vấn vừa triển khai chưa hưởng lợi ngay và thời gian hoàn tất thay đổi theo khối lượng dữ liệu nền.
Một cụm Neo4j vừa được chuyển sang hạ tầng mới; kiểm thử khôi phục bản sao lưu cho thấy số node khớp nhưng một số relationship nghiệp vụ quan trọng chưa được kiểm chứng về tính toàn vẹn.
Ứng dụng Java mất kết nối sau đợt thay chứng chỉ TLS cho Neo4j; một số pod khởi động lại truy cập được trong khi các pod còn chạy báo lỗi xác thực máy chủ khi tạo kết nối.
Nền tảng phục vụ nhiều khách hàng doanh nghiệp trong cùng đồ thị; một báo cáo Cypher quên điều kiện phạm vi tenant làm xuất hiện đường đi nối dữ liệu của hai doanh nghiệp khác nhau.
Dashboard vận hành ghi nhận CPU tăng, số transaction đang mở cao và độ trễ Cypher tăng nhưng vẫn thiếu số liệu theo loại truy vấn; nhóm chưa xác định được liệu nghẽn đến từ truy vấn đường đi, nhập dữ liệu hay tranh chấp ghi.

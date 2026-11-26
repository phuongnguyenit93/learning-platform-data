Câu 01. Trong JDBC, khi khối try-with-resources quản lý Connection kết thúc thì điều gì xảy ra?
A. Tài nguyên được ghi log rồi giữ mở tới khi tiến trình dừng.
B. Lệnh close() được gọi tự động khi thoát khỏi khối try.
C. Giao dịch được tự động xác nhận bởi trình điều khiển JDBC.
D. Kết nối vật lý được mở thêm để phục vụ lệnh tiếp theo.
Đáp án đúng: B

Câu 02. Đặc điểm nào khiến DataSource phù hợp để tách việc cấp kết nối khỏi mã truy cập dữ liệu?
A. DriverManager tự duy trì hàng đợi chờ mượn khi pool hết chỗ.
B. DataSource tự xác nhận giao dịch sau mỗi truy vấn được gọi.
C. DataSource cung cấp điểm cấp kết nối qua cấu hình riêng.
D. DriverManager tự giới hạn số phiên kết nối rảnh của pool.
Đáp án đúng: C

Câu 03. Với pool kết nối thông dụng, gọi close() trên Connection đang mượn thường có nghĩa gì?
A. Đóng hoàn toàn TCP socket của kết nối nền mỗi lần gọi.
B. Tạo ngay một kết nối vật lý mới để thay thế handle.
C. Giữ handle cũ hoạt động để thực thi truy vấn tiếp theo.
D. Trả handle về pool theo cơ chế tái sử dụng của pool.
Đáp án đúng: D

Câu 04. Vì sao nên truyền tham số qua PreparedStatement thay vì ghép giá trị vào chuỗi SQL?
A. Để giao dịch có thể sử dụng nhiều kết nối cùng lúc.
B. Để driver bỏ qua toàn bộ bước phân tích cú pháp SQL.
C. Để giá trị được truyền như dữ liệu thay vì mã SQL.
D. Để pool tăng giới hạn kết nối theo số lượng tham số.
Đáp án đúng: C

Câu 05. Với autoCommit=true, một lệnh DML độc lập hoàn tất thành công được xử lý ra sao?
A. Lệnh chỉ được ghi nhận sau khi ứng dụng gọi commit().
B. Lệnh chờ được commit đến khi đối tượng Connection đóng.
C. Lệnh tự rollback khi ứng dụng mượn connection tiếp theo.
D. Lệnh được xác nhận như một giao dịch độc lập hoàn tất.
Đáp án đúng: D

Câu 06. Khi dùng setAutoCommit(false) và xử lý giao dịch gặp lỗi, ứng dụng cần làm gì?
A. Đóng ResultSet để driver tự động commit mọi thay đổi.
B. Gọi executeUpdate thêm lần nữa để tự hủy giao dịch.
C. Chủ động rollback giao dịch thất bại trước khi kết thúc.
D. Chuyển isolation level để driver tự xác nhận giao dịch.
Đáp án đúng: C

Câu 07. Để nhiều thao tác JDBC thuộc cùng một giao dịch cục bộ, cách làm nào phù hợp?
A. Chạy các thao tác trên cùng kết nối trong một giao dịch.
B. Chạy mỗi thao tác trên một kết nối mới để giảm giữ khóa.
C. Commit riêng sau từng thao tác để đảm bảo tính nguyên tử.
D. Đổi kết nối giữa các thao tác để tận dụng mọi phiên DB.
Đáp án đúng: A

Câu 08. Mức cô lập READ COMMITTED thường bảo đảm điều nào trong giao dịch?
A. Mỗi lần đọc cùng một dòng đều thấy đúng một giá trị.
B. Không đọc các thay đổi chưa commit từ giao dịch khác.
C. Mọi giao dịch được chạy nối tiếp theo thứ tự cấp phát.
D. Không có bản ghi mới xuất hiện trong truy vấn lặp lại.
Đáp án đúng: B

Câu 09. Vì sao nên đóng ResultSet và Statement đúng hạn, kể cả khi dùng connection pool?
A. Để driver tự tăng mức isolation cho giao dịch kế tiếp.
B. Để JDBC bỏ kiểm tra tính hợp lệ của connection trong pool.
C. Để DB phục hồi toàn bộ dữ liệu về lần commit trước.
D. Để giải phóng tài nguyên gắn với câu lệnh và cursor.
Đáp án đúng: D

Câu 10. Phân biệt nào chính xác giữa handle Connection và kết nối vật lý khi có pool?
A. Mỗi handle được cấp luôn sở hữu một phiên vật lý mới.
B. Pool chỉ lưu các chuỗi URL mà không duy trì phiên SQL.
C. Handle có thể dùng lại một phiên vật lý sau lượt mượn.
D. Phiên vật lý được tạo lại mỗi lần gọi getConnection().
Đáp án đúng: C

Câu 11. Trong cấu hình pool, maximumPoolSize chủ yếu giới hạn yếu tố nào?
A. Số kết nối vật lý mà pool được phép duy trì đồng thời.
B. Số luồng xử lý HTTP được phép tạo trong ứng dụng.
C. Số truy vấn SQL được phép thực thi trong một phút.
D. Số cơ sở dữ liệu được phép đăng ký trong một ứng dụng.
Đáp án đúng: A

Câu 12. Connection acquisition timeout đo khoảng thời gian nào?
A. Thời gian tối đa luồng chờ mượn một kết nối từ pool.
B. Thời gian tối đa DB thực thi một câu lệnh SQL cụ thể.
C. Thời gian tối đa socket chờ dữ liệu phản hồi từ DB.
D. Thời gian tối đa giao dịch có thể giữ khóa trước commit.
Đáp án đúng: A

Câu 13. Thuộc tính minimumIdle trong một pool thường biểu thị điều gì?
A. Số phiên đang chạy giao dịch phải luôn bằng ngưỡng đặt.
B. Số truy vấn chưa commit trên một kết nối đang rảnh.
C. Số kết nối rảnh mà pool cố duy trì khi điều kiện cho phép.
D. Số luồng đang chờ cấp kết nối được phép có trong pool.
Đáp án đúng: C

Câu 14. Idle timeout của pool thường được dùng để làm gì?
A. Giới hạn thời gian ứng dụng chờ mượn kết nối khi pool đầy.
B. Giới hạn thời gian SQL chờ khóa bảng từ giao dịch khác.
C. Thu hồi kết nối rảnh dư sau một khoảng thời gian nhất định.
D. Thu hồi giao dịch đang chạy sau khi vượt thời gian commit.
Đáp án đúng: C

Câu 15. Ý nghĩa chính của maxLifetime đối với kết nối vật lý trong pool là gì?
A. Giới hạn tổng số câu SQL được chạy trên mỗi kết nối.
B. Giới hạn thời gian CPU cho từng truy vấn bên database.
C. Giới hạn số kết nối mới được tạo trong một chu kỳ tải.
D. Giới hạn tuổi kết nối vật lý trước khi pool thay thế.
Đáp án đúng: D

Câu 16. Việc validation một connection trước khi cấp cho ứng dụng nhằm mục đích gì?
A. Kiểm tra truy vấn có dùng đúng chỉ mục trong database.
B. Xác minh connection vẫn hoạt động và có thể sử dụng.
C. Kiểm tra tài khoản có quyền truy cập mọi bảng của DB.
D. Xác minh mọi giao dịch trước đó đều đã được commit.
Đáp án đúng: B

Câu 17. Nếu database thường đóng các phiên nhàn rỗi, biện pháp nào giúp hạn chế cấp kết nối hỏng?
A. Tạo một pool mới cho từng lệnh SQL để tránh phiên cũ.
B. Đặt isolation cao nhất trên mọi transaction của hệ thống.
C. Phối hợp kiểm tra kết nối sống với thời hạn giữ phù hợp.
D. Tắt hoàn toàn mọi timeout phía server cho các phiên DB.
Đáp án đúng: C

Câu 18. Khi nhiều instance cùng truy cập một DB có giới hạn phiên, nên lập ngân sách kết nối ra sao?
A. Cho mỗi instance dùng toàn bộ hạn mức kết nối của DB.
B. Lấy số CPU mỗi instance làm số phiên tối đa của pool.
C. Bỏ qua các kết nối giám sát và tác vụ nền khi tính toán.
D. Tính tổng mức cấp cho các instance và phiên dành cho hệ khác.
Đáp án đúng: D

Câu 19. Điều gì có thể xảy ra nếu pool tạo quá nhiều kết nối so với năng lực DB?
A. Tăng tranh chấp tài nguyên do nhiều phiên SQL chạy đồng thời.
B. Giảm tranh chấp khóa vì mỗi truy vấn có phiên kết nối riêng.
C. Giảm hàng đợi vì DB tự mở thêm worker cho từng connection.
D. Tăng hiệu quả cache vì mỗi phiên có vùng dữ liệu tách biệt.
Đáp án đúng: A

Câu 20. Cách chọn kích thước pool ban đầu nào có cơ sở hơn?
A. Chọn số gần bằng lượng request HTTP mỗi giây của dịch vụ.
B. Đo nhu cầu kết nối đồng thời và giới hạn thực tế của DB.
C. Chọn số bằng tổng luồng xử lý của toàn bộ cụm ứng dụng.
D. Đặt bằng hạn mức kết nối DB và tăng dần theo số instance.
Đáp án đúng: B

Câu 21. Khi pool liên tục hết kết nối rảnh, nhận định nào là đúng?
A. Tăng minimumIdle sẽ làm các câu truy vấn DB chạy nhanh hơn.
B. Tăng thời gian chờ mượn sẽ rút ngắn giao dịch đang chạy.
C. Giảm idleTimeout sẽ ngắt các giao dịch đang giữ kết nối.
D. Giữ kết nối khi chờ API ngoài có thể làm cạn pool nhanh.
Đáp án đúng: D

Câu 22. Metrics cho thấy active bằng maximumPoolSize, idle bằng 0, pending lớn hơn 0. Điều này gợi ý gì?
A. Pool đã bão hòa và có yêu cầu đang chờ được cấp kết nối.
B. Pool đã tạo vượt ngưỡng tối đa nên đang hủy bớt kết nối.
C. DB vừa commit mọi giao dịch nên pool đang nhận phiên mới.
D. Luồng xử lý đang chờ CPU và chưa yêu cầu lấy connection.
Đáp án đúng: A

Câu 23. Nếu p95 thời gian mượn kết nối từ pool tăng, diễn giải nào sát nhất?
A. Nhiều yêu cầu phải chờ lâu hơn để lấy được connection.
B. Thời gian thực thi mỗi câu SQL trên DB đều tăng tương ứng.
C. Thời gian kết nối TCP của mỗi request đều tăng tương ứng.
D. Số hàng được trả trong mỗi ResultSet đều tăng tương ứng.
Đáp án đúng: A

Câu 24. Cấu hình leakDetectionThreshold của pool thông dụng chủ yếu dùng để làm gì?
A. Hủy transaction khi một câu SQL vượt thời gian cấu hình.
B. Rollback transaction khi số connection rảnh giảm quá thấp.
C. Cảnh báo khi connection bị giữ quá thời gian ngưỡng đặt.
D. Cảnh báo khi CPU database dùng vượt ngưỡng trong truy vấn.
Đáp án đúng: C

Câu 25. Vì sao một cảnh báo nghi rò rỉ kết nối chưa đủ kết luận có leak thật?
A. Cảnh báo tương tự cũng xuất hiện khi ứng dụng thiếu RAM.
B. Cảnh báo tương tự cũng xuất hiện khi database hết ổ đĩa.
C. Giao dịch hợp lệ chạy dài cũng có thể vượt ngưỡng cảnh báo.
D. Pool luôn xóa phiên vật lý ngay trước khi phát cảnh báo leak.
Đáp án đúng: C

Câu 26. Khi nghi ngờ connection leak, kiểm tra nào giúp xác định nguyên nhân trong ứng dụng?
A. Đo dung lượng bảng rồi tăng số kết nối trong pool lên.
B. Xóa toàn bộ kết nối idle sau mỗi lần phát sinh cảnh báo.
C. Tắt chức năng theo dõi leak rồi so sánh số request lỗi.
D. Đối chiếu đường mượn và trả kết nối ở các nhánh xử lý.
Đáp án đúng: D

Câu 27. Tình huống nào dễ gây rò rỉ handle kết nối trong ứng dụng JDBC?
A. Nhánh bắt ngoại lệ bỏ qua việc đóng connection đã mượn.
B. Lệnh SQL dùng PreparedStatement với tham số dạng bind.
C. Khối finally trả connection về pool sau khi xử lý xong.
D. Pool xác minh tính hợp lệ của connection trước lượt mượn.
Đáp án đúng: A

Câu 28. Nếu pool full, pending tăng và DB ghi nhận chờ khóa kéo dài, cần điều tra gì trước?
A. Tăng maximumPoolSize mà không kiểm tra giao dịch trên DB.
B. Tắt timeout mượn để các request chờ không bị báo lỗi.
C. Giảm maxLifetime để các phiên đang giữ khóa được thay sớm.
D. Kiểm tra transaction dài, truy vấn SQL và khóa đang chờ.
Đáp án đúng: D

Câu 29. Một transaction giữ connection trong lúc gọi dịch vụ HTTP chậm. Cách cải thiện nào hợp lý?
A. Tăng số lời gọi HTTP bên trong transaction đang thực hiện.
B. Đưa I/O bên ngoài ra khỏi khoảng thời gian giữ connection.
C. Mượn thêm connection dự phòng khi bắt đầu lời gọi HTTP.
D. Kéo dài timeout transaction để request có thêm thời gian.
Đáp án đúng: B

Câu 30. Khi một giao dịch JDBC thủ công thất bại mà connection vẫn sử dụng được, nên xử lý ra sao?
A. Trả kết nối về pool rồi chờ lần mượn kế tiếp rollback.
B. Rollback giao dịch và hoàn trả connection đúng cách.
C. Chỉ đóng Statement để transaction đang lỗi tự biến mất.
D. Bỏ qua lỗi và gọi commit để giải phóng khóa đang giữ.
Đáp án đúng: B

Câu 31. Với nhiều request xử lý đồng thời, mẫu dùng connection nào phù hợp?
A. Chia sẻ một handle Connection đang mở cho mọi request.
B. Dùng một transaction chung cho tất cả luồng xử lý.
C. Mỗi luồng mượn và trả handle trong phạm vi công việc.
D. Tạo một pool riêng cho từng request để tránh chờ đợi.
Đáp án đúng: C

Câu 32. Trong JDBC, Statement.setQueryTimeout chủ yếu giới hạn thời gian nào?
A. Thời gian một luồng chờ lấy kết nối từ connection pool.
B. Thời gian driver chờ lệnh SQL thực thi xong trên database.
C. Thời gian kết nối rảnh có thể tồn tại trong connection pool.
D. Thời gian một phiên vật lý được giữ trước lúc thay thế.
Đáp án đúng: B

Câu 33. Khi JDBC driver hỗ trợ socket read timeout, cấu hình này tác động chủ yếu đến gì?
A. Thời gian đọc toàn bộ ResultSet trong mã xử lý của ứng dụng.
B. Thời gian pool chờ cấp một handle Connection đang rảnh.
C. Thời gian tối đa transaction chờ tới lần gọi commit().
D. Thời gian chờ nhận dữ liệu qua socket kết nối database.
Đáp án đúng: D

Câu 34. Cách quản lý thông tin đăng nhập database nào an toàn hơn?
A. Lấy thông tin từ nơi quản lý secret và giới hạn quyền đọc.
B. Ghi thông tin vào git để các môi trường dùng cùng mật khẩu.
C. Ghi thông tin vào log debug mỗi khi pool tạo connection.
D. Nhúng thông tin vào URL công khai để tiện giám sát pool.
Đáp án đúng: A

Câu 35. Khi yêu cầu bảo vệ dữ liệu trên đường truyền tới database, cấu hình nào phù hợp?
A. Bật TLS nhưng vô hiệu hóa kiểm tra máy chủ ở mọi môi trường.
B. Chỉ mã hóa mật khẩu nhưng để dữ liệu truy vấn truyền dạng rõ.
C. Chỉ kiểm tra IP máy chủ rồi bỏ qua chuỗi chứng chỉ TLS.
D. Bật mã hóa TLS và xác minh chứng chỉ của máy chủ database.
Đáp án đúng: D

Câu 36. Nguyên tắc cấp quyền cho tài khoản ứng dụng truy cập database là gì?
A. Cấp quyền quản trị hệ thống để tránh lỗi thiếu quyền ở DB.
B. Chỉ cấp những quyền cần thiết cho các tác vụ ứng dụng.
C. Dùng chung tài khoản với quản trị viên để dễ luân chuyển.
D. Cấp quyền đọc mọi schema để tránh truy vấn bị từ chối.
Đáp án đúng: B

Câu 37. Khi xoay vòng mật khẩu database, cần xử lý pool thế nào để phiên mới dùng secret mới?
A. Chỉ đổi secret lưu trữ, các phiên DB hiện có tự đổi thông tin.
B. Cập nhật cấu hình xác thực rồi làm mới các phiên của pool.
C. Chỉ tăng maximumPoolSize, pool tự đọc secret mới từ server.
D. Chỉ giảm idleTimeout, phiên hiện có tự nhận mật khẩu mới.
Đáp án đúng: B

Câu 38. Vì sao tăng maximumPoolSize có thể phản tác dụng khi DB đã quá tải?
A. Nhiều phiên chạy thêm có thể tăng tranh chấp tài nguyên DB.
B. JDBC không cho tạo pool lớn hơn số CPU trên máy ứng dụng.
C. Pool lớn tự động chuyển mọi giao dịch sang mức SERIALIZABLE.
D. Database chỉ có thể thực thi một câu SQL ở mỗi thời điểm.
Đáp án đúng: A

Câu 39. Metric thời gian giữ connection trong pool đo khoảng nào?
A. Từ lúc DB nhận câu SQL đến lúc trả hàng dữ liệu cuối cùng.
B. Từ lúc ứng dụng mượn handle đến khi trả handle về pool.
C. Từ lúc request vào hàng đợi mượn đến khi được cấp handle.
D. Từ lúc DB mở phiên vật lý đến khi phiên đó bị đóng.
Đáp án đúng: B

Câu 40. Sau khi giảm thời gian giữ connection, pending về 0 nhưng p95 truy vấn SQL vẫn cao. Nên làm gì?
A. Phân tích execution plan và tài nguyên DB của truy vấn chậm.
B. Tăng connectionTimeout để request được phép chờ lâu hơn.
C. Tăng minimumIdle bằng maximumPoolSize để giữ nhiều phiên.
D. Tắt leak detection vì không còn request đứng chờ pool.
Đáp án đúng: A

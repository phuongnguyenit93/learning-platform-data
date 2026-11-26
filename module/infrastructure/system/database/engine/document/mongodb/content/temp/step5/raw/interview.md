Bạn sẽ giải thích mô hình document của MongoDB khác mô hình bảng quan hệ như thế nào khi thiết kế dữ liệu cho một ứng dụng thực tế?
BSON bổ sung những kiểu dữ liệu và khả năng biểu diễn nào so với JSON thông thường?
Bạn sẽ chọn kiểu BSON cho mã định danh, thời điểm, số tiền và giá trị có độ chính xác cao theo những tiêu chí nào?
Bạn sẽ phân tích đặc điểm của trường _id và các giả định cần tránh khi dùng ObjectId để sắp xếp dữ liệu như thế nào?
Bạn sẽ tổ chức collection và document cho hệ thống quản lý đơn hàng dựa trên cách ứng dụng đọc và ghi dữ liệu ra sao?
Bạn sẽ quyết định nhúng document hay lưu tham chiếu giữa các collection dựa trên tần suất truy cập và cập nhật như thế nào?
Trong trường hợp nào việc phi chuẩn hóa dữ liệu giúp giảm truy vấn, và bạn sẽ kiểm soát dữ liệu trùng lặp ra sao?
Bạn sẽ xử lý quan hệ một-nhiều có số phần tử tăng không giới hạn mà không tạo document quá lớn như thế nào?
Giới hạn kích thước document tác động ra sao đến cách lưu lịch sử sự kiện, log hoặc danh sách giao dịch?
Bạn sẽ thiết kế mô hình dữ liệu cho một thực thể có nhiều phiên bản và cần truy vết thay đổi như thế nào?
Bạn sẽ sử dụng các quy tắc xác thực schema trong MongoDB ra sao khi ứng dụng cần vừa linh hoạt vừa nhất quán?
Bạn sẽ tổ chức việc bổ sung, đổi tên hoặc loại bỏ trường dữ liệu qua nhiều phiên bản ứng dụng như thế nào?
Với một trường có thể vắng mặt, bằng null hoặc chứa giá trị rỗng, bạn sẽ phân biệt các trạng thái này khi truy vấn ra sao?
Bạn sẽ lựa chọn tên trường, cấu trúc lồng nhau và quy ước dữ liệu để tránh gây khó khăn cho truy vấn về sau như thế nào?
Bạn sẽ xác định các mẫu truy cập chủ đạo trước khi tạo collection và index như thế nào?
Bạn sẽ mô tả vòng đời của thao tác tạo, đọc, cập nhật và xóa document từ yêu cầu ứng dụng đến kết quả trả về ra sao?
Bạn sẽ xây dựng bộ lọc truy vấn theo nhiều điều kiện và kiểm soát lỗi do kiểu BSON không khớp như thế nào?
Bạn sẽ dùng projection để hạn chế dữ liệu trả về và đánh giá lợi ích của việc đó ra sao?
Bạn sẽ giải thích khác biệt giữa thay thế toàn bộ document và cập nhật từng trường trong các tình huống nghiệp vụ nào?
Bạn sẽ tận dụng tính nguyên tử của thao tác ghi trên một document để bảo vệ bất biến dữ liệu như thế nào?
Bạn sẽ thiết kế cập nhật có điều kiện để tránh ghi đè dữ liệu do hai người dùng sửa đồng thời ra sao?
Bạn sẽ lựa chọn các toán tử cập nhật cho giá trị số, trường lồng nhau và mảng dựa trên yêu cầu nào?
Bạn sẽ cập nhật một phần tử cụ thể trong mảng lồng nhau mà không làm thay đổi các phần tử khác như thế nào?
Bạn sẽ sử dụng upsert khi nào và kiểm soát nguy cơ tạo document trùng lặp trong các request đồng thời ra sao?
Bạn sẽ phân biệt hành vi ghi hàng loạt có thứ tự và không có thứ tự khi xảy ra lỗi như thế nào?
Bạn sẽ thiết kế thao tác xóa an toàn để tránh xóa nhầm nhiều document hoặc phá vỡ dữ liệu liên quan ra sao?
Khi ứng dụng thử lại một thao tác ghi sau lỗi mạng, bạn sẽ thiết kế tính idempotent như thế nào?
Bạn sẽ giải quyết lỗi trùng khóa duy nhất khi nhiều request cùng tạo một thực thể như thế nào?
Bạn sẽ kiểm soát sự khác biệt giữa dữ liệu thời gian UTC trong BSON và múi giờ hiển thị tại ứng dụng ra sao?
Bạn sẽ lựa chọn collation để so khớp và sắp xếp chuỗi có dấu, không dấu hoặc khác kiểu chữ như thế nào?
Bạn sẽ triển khai phân trang bằng skip và limit hay phân trang theo khóa dựa trên kích thước và biến động dữ liệu như thế nào?
Bạn sẽ bảo đảm thứ tự kết quả ổn định khi nhiều document có cùng giá trị trường sắp xếp ra sao?
Bạn sẽ đánh giá chi phí của truy vấn biểu thức chính quy hoặc bộ lọc không đủ chọn lọc như thế nào?
Bạn sẽ quản lý cursor và luồng dữ liệu trả về để tránh giữ tài nguyên quá lâu trong ứng dụng như thế nào?
Bạn sẽ mô tả các giai đoạn của một aggregation pipeline và cách document được biến đổi qua từng giai đoạn ra sao?
Bạn sẽ quyết định vị trí của các bước lọc, chọn trường và sắp xếp trong pipeline để giảm lượng dữ liệu xử lý như thế nào?
Bạn sẽ dùng nhóm và tính tổng hợp để xây dựng báo cáo doanh thu theo ngày, sản phẩm hoặc khu vực như thế nào?
Bạn sẽ xử lý các mảng bằng những giai đoạn aggregation phù hợp mà vẫn giữ được ý nghĩa của từng document như thế nào?
Bạn sẽ dùng phép kết hợp dữ liệu giữa hai collection trong aggregation khi nào và cân nhắc chi phí ra sao?
Bạn sẽ thiết kế một báo cáo có nhiều tập chỉ số xuất phát từ cùng dữ liệu đầu vào như thế nào?
Bạn sẽ phân biệt nhu cầu dùng aggregation với việc tổng hợp sẵn dữ liệu để phục vụ dashboard tải cao ra sao?
Bạn sẽ xác định nguyên nhân một pipeline tiêu thụ nhiều bộ nhớ hoặc cần ghi dữ liệu tạm như thế nào?
Bạn sẽ kiểm tra tính đúng đắn của kết quả aggregation trước những document thiếu trường, sai kiểu hoặc có mảng rỗng ra sao?
Bạn sẽ dùng các khả năng tính toán theo cửa sổ trong aggregation cho yêu cầu phân tích chuỗi thời gian như thế nào?
Index giúp truy vấn MongoDB tránh đọc những document không cần thiết bằng cơ chế nào?
Bạn sẽ lựa chọn giữa index một trường và index ghép theo bộ lọc, điều kiện sắp xếp và mẫu truy cập như thế nào?
Thứ tự các trường trong index ghép ảnh hưởng thế nào đến điều kiện bằng, điều kiện phạm vi và sắp xếp?
Bạn sẽ đánh giá độ chọn lọc của từng trường trước khi quyết định tạo index như thế nào?
Bạn sẽ thiết kế index cho truy vấn trên trường lồng nhau hoặc giá trị trong mảng như thế nào?
Đặc điểm của multikey index ảnh hưởng thế nào đến những truy vấn và cách sắp xếp có nhiều trường mảng?
Bạn sẽ lựa chọn partial index khi chỉ một phần document thường xuyên được truy vấn như thế nào?
Bạn sẽ phân biệt cách xử lý trường thiếu và giá trị null khi thiết kế unique index hoặc sparse index ra sao?
Bạn sẽ sử dụng TTL index cho dữ liệu hết hạn và kiểm tra kỳ vọng về thời điểm xóa thực tế như thế nào?
Bạn sẽ quyết định dùng index văn bản, khả năng tìm kiếm chuyên dụng hay một giải pháp tìm kiếm khác dựa trên loại truy vấn như thế nào?
Bạn sẽ thiết kế truy vấn và index địa lý để tìm vị trí gần nhất theo bán kính như thế nào?
Bạn sẽ xác định một truy vấn có thể được phục vụ từ index mà không cần đọc document đầy đủ ra sao?
Bạn sẽ đọc các số liệu từ explain và execution statistics để nhận diện collection scan, index scan và chi phí thực thi như thế nào?
Nếu truy vấn chậm dù có index, bạn sẽ kiểm tra kế hoạch truy vấn, số document được xét và cách lọc dữ liệu theo thứ tự nào?
Bạn sẽ đánh giá tác động của quá nhiều index đến tốc độ ghi, dung lượng lưu trữ và bộ nhớ như thế nào?
Bạn sẽ tổ chức xây dựng hoặc thay đổi index trên collection lớn với ảnh hưởng vận hành chấp nhận được ra sao?
Bạn sẽ phân tích một truy vấn có phân trang và sắp xếp chậm dần khi dữ liệu tăng để điều chỉnh index như thế nào?
Bạn sẽ mô tả các vai trò primary, secondary và cơ chế bầu chọn trong một MongoDB replica set ra sao?
Khi primary mất kết nối hoặc chuyển vai trò, bạn sẽ phân tích tác động đến các thao tác ghi và đọc như thế nào?
Replication oplog hỗ trợ đồng bộ dữ liệu giữa các thành viên và tác động thế nào đến khả năng bắt kịp của secondary?
Bạn sẽ đánh giá replication lag qua các chỉ số vận hành và phân biệt dữ liệu cũ với lỗi truy vấn như thế nào?
Bạn sẽ chọn read preference cho một hệ thống cần cân bằng độ mới dữ liệu và khả năng phân tải đọc ra sao?
Bạn sẽ phân biệt các mức read concern và hệ quả đối với tính nhất quán dữ liệu như thế nào?
Bạn sẽ lựa chọn write concern theo yêu cầu về độ bền, độ trễ và khả năng chịu lỗi của nghiệp vụ như thế nào?
Bạn sẽ giải thích tương tác giữa read concern, write concern và read preference trong một luồng ghi rồi đọc như thế nào?
Bạn sẽ thiết kế thử nghiệm failover để kiểm chứng tính sẵn sàng và cách ứng dụng khôi phục kết nối như thế nào?
Bạn sẽ xử lý các thao tác đọc và ghi bị gián đoạn hoặc trả về kết quả chưa rõ trong thời gian bầu chọn primary ra sao?
Bạn sẽ phân biệt replication để tăng khả năng sẵn sàng với sharding để phân phối dữ liệu và tải như thế nào?
Bạn sẽ mô tả vai trò của shard, router và máy chủ cấu hình trong cụm MongoDB phân mảnh ra sao?
Bạn sẽ chọn shard key cho collection lớn dựa trên độ phân bố, khả năng định tuyến và mẫu truy cập như thế nào?
Bạn sẽ so sánh shard key theo phạm vi với shard key băm trong trường hợp dữ liệu có tốc độ tăng nhanh như thế nào?
Bạn sẽ chẩn đoán một shard trở thành điểm nóng khi khóa phân mảnh có giá trị tăng tuần tự như thế nào?
Bạn sẽ nhận diện truy vấn có thể định tuyến đến shard đích và truy vấn phải phân tán đến nhiều shard ra sao?
Bạn sẽ đánh giá chi phí di chuyển dữ liệu và cân bằng phân mảnh đối với hiệu năng truy vấn như thế nào?
Bạn sẽ lên kế hoạch thay đổi shard key hoặc phân bố lại dữ liệu khi mẫu truy cập thay đổi như thế nào?
Bạn sẽ quyết định dùng thao tác nguyên tử trong một document hay transaction nhiều document dựa trên bất biến nghiệp vụ nào?
Bạn sẽ mô tả vai trò của session và vòng đời transaction trong MongoDB khi cập nhật nhiều collection như thế nào?
Bạn sẽ tổ chức commit, abort và giải phóng session khi transaction thành công hoặc ném ngoại lệ ra sao?
Bạn sẽ xử lý lỗi transaction tạm thời và kết quả commit chưa xác định bằng cách thử lại an toàn như thế nào?
Bạn sẽ đánh giá chi phí và giới hạn của transaction kéo dài, đặc biệt khi liên quan nhiều shard như thế nào?
Bạn sẽ thiết kế nghiệp vụ chuyển trạng thái đơn hàng và điều chỉnh tồn kho để bảo đảm tính nhất quán như thế nào?
Bạn sẽ lựa chọn chiến lược xác thực và phân quyền theo nguyên tắc tối thiểu quyền cho từng ứng dụng như thế nào?
Bạn sẽ cấu hình mã hóa kết nối và xác minh danh tính máy chủ MongoDB trong môi trường triển khai như thế nào?
Bạn sẽ bảo vệ thông tin nhạy cảm trong document và cân nhắc mã hóa ở tầng ứng dụng ra sao?
Bạn sẽ ngăn nguy cơ chèn toán tử truy vấn từ đầu vào không đáng tin cậy bằng cách xây dựng filter an toàn như thế nào?
Bạn sẽ quản lý bí mật kết nối, xoay vòng tài khoản và tránh ghi thông tin nhạy cảm vào log như thế nào?
Bạn sẽ sử dụng nhật ký kiểm toán và phân quyền truy cập để điều tra thao tác nhạy cảm như thế nào?
Bạn sẽ kết nối ứng dụng Java với MongoDB driver và cấu hình thời gian chờ cùng connection pool dựa trên tải như thế nào?
Bạn sẽ ánh xạ document BSON sang POJO trong Java và xử lý trường thiếu hoặc thay đổi kiểu dữ liệu như thế nào?
Bạn sẽ lựa chọn cách sử dụng MongoDB driver trực tiếp hay Spring Data MongoDB theo nhu cầu kiểm soát truy vấn như thế nào?
Bạn sẽ phân biệt phương pháp gọi đồng bộ với luồng xử lý bất đồng bộ hoặc reactive khi truy cập MongoDB trong Java ra sao?
Bạn sẽ thiết kế vòng đời MongoClient và cách tái sử dụng kết nối trong ứng dụng có nhiều request đồng thời như thế nào?
Bạn sẽ đặt timeout, giới hạn đồng thời và hành vi retry để tránh làm MongoDB quá tải khi lưu lượng tăng như thế nào?
Bạn sẽ theo dõi độ trễ truy vấn, tỷ lệ lỗi, áp lực pool kết nối, bộ nhớ và replication lag để phát hiện nút nghẽn ra sao?
Bạn sẽ kết hợp profiler, slow query log và explain để tìm nguyên nhân một API Java truy vấn MongoDB chậm như thế nào?
Bạn sẽ xây dựng bộ kiểm thử tích hợp để xác minh schema, aggregation, index, transaction và lỗi kết nối như thế nào?
Bạn sẽ tổ chức sao lưu và thử khôi phục dữ liệu khi hệ thống yêu cầu giới hạn thời gian mất dữ liệu như thế nào?
Bạn sẽ lập kế hoạch chuyển đổi schema và triển khai ứng dụng tương thích khi collection đã chứa hàng triệu document ra sao?
Bạn sẽ xử lý sự cố khi một secondary tụt lại, truy vấn phân tán tăng đột biến và pool kết nối ứng dụng bị bão hòa như thế nào?
Bạn sẽ xác định những tiêu chí kỹ thuật và phép đo nào trước khi đưa thiết kế MongoDB vào vận hành với tải sản xuất?

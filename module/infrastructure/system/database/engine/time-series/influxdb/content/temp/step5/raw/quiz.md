Câu 01. Dữ liệu chuỗi thời gian phù hợp nhất với mẫu thông tin nào?
A. Bảng danh mục sản phẩm với các khóa ngoại và phiên bản SKU.
B. Tài liệu hợp đồng chứa nhiều đoạn văn và tệp đính kèm.
C. Giá trị đo kèm thời điểm ghi nhận và thuộc tính nguồn đo.
D. Đồ thị người dùng liên kết nhau qua quan hệ nhiều cấp.
Đáp án đúng: C

Câu 02. Trong mô hình dữ liệu InfluxDB 1.x/2.x, measurement đại diện cho gì?
A. Nhóm các điểm đo cùng loại, tương tự tên tập hợp số liệu.
B. Khóa duy nhất được tự tăng mỗi lần ghi một điểm dữ liệu.
C. Đơn vị xác định khoảng cách thời gian giữa hai phép đo.
D. Chỉ số thống kê được tự tính theo tất cả tag của cơ sở dữ liệu.
Đáp án đúng: A

Câu 03. Trong InfluxDB 1.x/2.x, đặc trưng chính của tag là gì?
A. Được dùng làm dấu thời gian và phải tăng theo mỗi phép ghi.
B. Được lưu dưới dạng giá trị chuỗi và hỗ trợ lọc theo chỉ mục.
C. Được dùng để chứa nội dung nhị phân lớn và không thể lọc.
D. Được lưu như giá trị số để luôn tính trung bình bằng SQL.
Đáp án đúng: B

Câu 04. Vai trò của field trong điểm dữ liệu InfluxDB 1.x/2.x là gì?
A. Xác định tên bucket cùng chính sách giữ dữ liệu trên máy chủ.
B. Gắn một danh tính series toàn cục không phụ thuộc measurement.
C. Luôn là nhãn chuỗi được lập chỉ mục cho mọi phép truy vấn lọc.
D. Chứa giá trị đo như số, chuỗi hoặc boolean của một thời điểm.
Đáp án đúng: D

Câu 05. Timestamp trong một điểm dữ liệu InfluxDB biểu thị điều gì?
A. Thời điểm của quan sát được ghi, theo độ chính xác cấu hình.
B. Khoảng trễ mạng từ agent tới máy chủ lưu trữ dữ liệu.
C. Khoảng thời gian tự động giữ lại điểm đo trước khi bị xóa.
D. Thời điểm mở kết nối tới máy chủ để gửi lệnh truy vấn.
Đáp án đúng: A

Câu 06. Cú pháp cơ bản của một dòng InfluxDB line protocol theo thứ tự nào?
A. Field set và timestamp, tiếp theo measurement và tags.
B. Measurement và tags, tiếp theo field set, rồi timestamp.
C. Tags và timestamp, tiếp theo field set, rồi measurement.
D. Timestamp và tags, tiếp theo measurement, rồi field set.
Đáp án đúng: B

Câu 07. Khi ghi field chuỗi bằng line protocol, cú pháp giá trị nào phù hợp?
A. Đặt giá trị chuỗi trong dấu nháy kép sau tên field.
B. Đặt tên measurement trong dấu nháy kép sau tên field.
C. Đặt tất cả các tag trong dấu nháy kép cùng timestamp.
D. Đặt timestamp trong dấu nháy kép sau tên measurement.
Đáp án đúng: A

Câu 08. Khi client gửi timestamp bằng giây thay vì nano giây, cần làm gì?
A. Chuyển timestamp sang chuỗi không phân biệt đơn vị.
B. Đổi timestamp thành tag trước khi gửi dữ liệu vào bucket.
C. Cấu hình precision tương ứng để máy chủ diễn giải đúng.
D. Nhân timestamp bằng số lượng field trong một điểm đo.
Đáp án đúng: C

Câu 09. Trong InfluxDB 1.x/2.x, ghi cùng measurement, tag set và timestamp với field trùng tên thường ra sao?
A. Giá trị field trùng bị cộng dồn vào giá trị lưu trước.
B. Lệnh ghi bị từ chối chỉ vì timestamp đã tồn tại trong series.
C. Dòng ghi luôn tạo series mới có khóa độc lập với dữ liệu trước.
D. Giá trị field trùng được ghi mới đè lên giá trị cũ.
Đáp án đúng: D

Câu 10. Với dữ liệu cảm biến, lựa chọn nào nên làm tag khi giá trị ít biến đổi?
A. Vị trí trạm đo hoặc loại thiết bị được dùng thường xuyên để lọc.
B. Giá trị nhiệt độ đo liên tục theo từng giây của cảm biến.
C. Nội dung phản hồi lỗi có mã ngẫu nhiên sau mỗi request.
D. Giá trị bộ đếm byte được tăng khi mỗi gói dữ liệu đến.
Đáp án đúng: A

Câu 11. Vì sao đưa một ID duy nhất cho từng sự kiện vào tag có thể gây hại?
A. Những field dạng số sẽ mất khả năng hỗ trợ phép cộng và trung bình.
B. Các điểm đo sẽ bị tự chuyển sang định dạng document không nén.
C. Tất cả timestamp cùng tag được đồng bộ sang một nút duy nhất.
D. Số series khác nhau tăng mạnh, kéo theo chi phí bộ nhớ và index.
Đáp án đúng: D

Câu 12. Khi thiết kế series cho CPU theo máy chủ, tag nào thường hữu ích nhất?
A. Timestamp dạng chuỗi để tạo tag duy nhất cho mỗi điểm đo.
B. Số giây đã chạy được để tạo tag tăng liên tục theo thời gian.
C. Host và region để lọc hoặc nhóm nhiều chuỗi CPU theo nguồn.
D. Mức sử dụng CPU đo được để chia dữ liệu theo từng giá trị.
Đáp án đúng: C

Câu 13. Trong InfluxDB 1.x, retention policy được gắn với phạm vi nào?
A. Mỗi truy vấn SELECT và quy định số dòng tối đa trả cho client.
B. Một database và quy định khoảng thời gian lưu dữ liệu trong đó.
C. Một tiến trình Telegraf và quy định tần suất thu thập dữ liệu.
D. Mỗi dashboard và quy định thời gian tự làm mới kết quả hiển thị.
Đáp án đúng: B

Câu 14. Trong InfluxDB 2.x, bucket thông thường kết hợp thông tin nào?
A. Một bộ cảnh báo cùng các lịch chạy thông báo đến người dùng.
B. Không gian lưu trữ chuỗi thời gian và cấu hình retention.
C. Chỉ một dashboard cùng tập quyền truy cập biểu đồ.
D. Một plugin Telegraf cùng danh sách mọi input đang bật.
Đáp án đúng: B

Câu 15. Cách mô tả ngôn ngữ truy vấn InfluxDB qua các thế hệ nào chính xác?
A. 1.x dùng Flux mặc định; 2.x chỉ dùng Gremlin; 3.x dùng SPARQL.
B. 1.x dùng MongoQL; 2.x chỉ dùng PL/SQL; 3.x dùng HQL.
C. 1.x dùng InfluxQL; 2.x hỗ trợ Flux; 3.x hỗ trợ SQL.
D. 1.x dùng SQL chuẩn; 2.x chỉ hỗ trợ Cypher; 3.x dùng GraphQL.
Đáp án đúng: C

Câu 16. Trong InfluxQL, GROUP BY time(5m) thường nhằm mục đích nào?
A. Nhóm tất cả bản ghi theo năm phút đầu của tháng hiện tại.
B. Chia dữ liệu theo cửa sổ thời gian 5 phút để tổng hợp.
C. Giới hạn kết quả trả về tối đa năm dòng mỗi phút.
D. Gộp mọi measurement vào một bảng có đúng năm hàng.
Đáp án đúng: B

Câu 17. Trong Flux, hàm range(start: ...) được dùng chủ yếu để làm gì?
A. Chia kết quả truy vấn thành các trang có cùng kích thước.
B. Đổi precision của timestamp sau khi dữ liệu đã được ghi.
C. Giới hạn khoảng thời gian cần đọc trước bước xử lý tiếp.
D. Đặt hạn lưu dữ liệu của bucket trước khi chạy truy vấn.
Đáp án đúng: C

Câu 18. Trong Flux, aggregateWindow(every: 1m, fn: mean) hỗ trợ việc gì?
A. Xóa mọi điểm trong mỗi phút sau khi tính tổng một lần.
B. Chuyển tất cả timestamps sang cùng một mốc đầu ngày.
C. Chỉ lấy đúng một dòng dữ liệu đầu tiên mỗi phút hiện có.
D. Tính giá trị trung bình theo các cửa sổ dài một phút.
Đáp án đúng: D

Câu 19. Trong InfluxDB 3, SQL được sử dụng phù hợp nhất cho nhu cầu nào?
A. Thiết lập chính sách sao lưu hệ điều hành cho mọi node.
B. Cấu hình token của Telegraf trước khi tạo từng metric.
C. Truy vấn và tổng hợp số liệu chuỗi thời gian từ bảng dữ liệu.
D. Thay đổi đồng hồ hệ thống trên thiết bị phát dữ liệu.
Đáp án đúng: C

Câu 20. Khi truy vấn dữ liệu nhiều tháng để vẽ biểu đồ, chiến lược nào hợp lý?
A. Tạo mỗi biểu đồ một bản sao đầy đủ của dữ liệu gốc.
B. Đọc mọi điểm ở mức mili giây rồi gửi toàn bộ về trình duyệt.
C. Lọc khoảng thời gian và tổng hợp theo độ phân giải biểu đồ.
D. Bỏ lọc thời gian để optimizer tự giới hạn dữ liệu trả về.
Đáp án đúng: C

Câu 21. Vì sao nên làm rõ timezone khi hiển thị dữ liệu từ timestamp?
A. Để bảo đảm mọi cảm biến có cùng khoảng thời gian lấy mẫu.
B. Để diễn giải đúng giờ địa phương khi dữ liệu gốc dùng UTC.
C. Để tăng giới hạn lưu trữ dài hạn của mọi bucket hiện hữu.
D. Để tự biến các field đo thành tags được lập chỉ mục.
Đáp án đúng: B

Câu 22. Với dữ liệu metrics tăng nhanh, retention phù hợp mang lại điều gì?
A. Ngăn mọi truy vấn cần đọc dữ liệu trong thời gian gần nhất.
B. Giới hạn thời gian giữ dữ liệu thô theo nhu cầu và chi phí.
C. Đổi giá trị các field kiểu số thành chuỗi trước khi xóa.
D. Luôn đồng bộ tất cả điểm đo sang những bucket mới mặc định.
Đáp án đúng: B

Câu 23. Downsampling trong hệ thống time-series giải quyết bài toán nào?
A. Giảm số lượng dữ liệu trong kết quả nhưng giữ nguyên bản ghi.
B. Nhân bản mọi điểm đo ra nhiều series để truy vấn nhanh.
C. Chuyển tag thành timestamp để tránh dùng bộ nhớ index.
D. Lưu bản tổng hợp thưa hơn để phân tích dữ liệu lịch sử.
Đáp án đúng: D

Câu 24. Khi tổng hợp nhiệt độ mỗi giờ, vì sao nên lưu cả số điểm đếm nếu tính trung bình nhiều cấp?
A. Để loại bỏ nhu cầu lưu tổng giá trị đo của từng khoảng.
B. Để buộc các giá trị thiếu được thay bằng số không mặc định.
C. Để bảo đảm mọi khoảng thời gian có số cảm biến giống nhau.
D. Để tính trung bình có trọng số đúng khi gộp nhiều khoảng.
Đáp án đúng: D

Câu 25. Telegraf input plugin chủ yếu đảm nhiệm công việc nào?
A. Gửi truy vấn cảnh báo và tự điều chỉnh retention của bucket.
B. Vẽ biểu đồ trong trình duyệt theo tài khoản đang đăng nhập.
C. Thu thập metric từ hệ điều hành, dịch vụ hoặc thiết bị nguồn.
D. Tạo công cụ backup và phục hồi độc lập cho database server.
Đáp án đúng: C

Câu 26. Telegraf output plugin chịu trách nhiệm chính cho việc gì?
A. Gửi metrics đã xử lý tới đích như InfluxDB được cấu hình.
B. Loại bỏ trường nhạy cảm khỏi dữ liệu trước khi xuất sang đích.
C. Thu thập trực tiếp dữ liệu từ cổng SNMP của thiết bị nguồn.
D. Đổi tên metric trong bộ nhớ trước khi chạy phép tổng hợp.
Đáp án đúng: A

Câu 27. Khi muốn đổi tên field trước khi Telegraf ghi dữ liệu, nên dùng gì?
A. Input plugin để lưu điểm đo vào ổ đĩa theo chu kỳ dài hạn.
B. Dashboard plugin để thay đổi field gốc khi người dùng xem.
C. Output plugin để tự lấy dữ liệu từ hệ thống nguồn bên ngoài.
D. Processor plugin để biến đổi hoặc lọc metric trong pipeline.
Đáp án đúng: D

Câu 28. Telegraf aggregator plugin có tác dụng chủ yếu nào?
A. Tổng hợp nhiều metric trong khoảng thời gian được thiết lập.
B. Ghi thêm token xác thực cho mọi input theo tên measurement.
C. Tự tạo một bảng lưu vĩnh viễn cho từng dòng dữ liệu đầu vào.
D. Luân chuyển bản sao replica để không cần retention policy.
Đáp án đúng: A

Câu 29. Tại sao nên đồng bộ đồng hồ của các máy gửi time-series?
A. Giảm kích thước dữ liệu trường số bằng cách thay đơn vị đo.
B. Giảm mọi series cardinality ngay cả khi có nhiều tags khác.
C. Giảm sai lệch thời điểm khiến số liệu bị xếp sai trật tự.
D. Giảm thời gian khởi động máy chủ mà không cần thay đổi cấu hình.
Đáp án đúng: C

Câu 30. Khi điểm đo đến trễ, ứng dụng phân tích nên cân nhắc điều gì?
A. Chuyển mọi điểm đến trễ thành tag của measurement mới.
B. Thay timestamp gốc bằng thời gian dashboard hiển thị.
C. Loại toàn bộ điểm có timestamp cũ hơn thời điểm hiện tại.
D. Cho phép độ trễ dữ liệu phù hợp khi chọn cửa sổ và cảnh báo.
Đáp án đúng: D

Câu 31. Một cảnh báo khi CPU vượt ngưỡng cần tránh nhấp nháy liên tục bằng cách nào?
A. Đổi mọi field CPU thành string để dễ so sánh theo thứ tự.
B. Chỉ kiểm tra điểm đo mới nhất và gửi lại mỗi vài mili giây.
C. Gỡ retention của bucket để cảnh báo luôn dùng lịch sử cũ.
D. Yêu cầu vượt ngưỡng trong khoảng đủ dài hoặc có hysteresis.
Đáp án đúng: D

Câu 32. Trong hệ thống giám sát, vì sao phải có cảnh báo thiếu dữ liệu?
A. Cảm biến dừng gửi có thể khiến ngưỡng giá trị không bị kích hoạt.
B. Mọi truy vấn aggregation sẽ trả lỗi nếu không có điểm trong cửa sổ.
C. Mọi sensor sẽ tự gửi số không nếu InfluxDB không phản hồi.
D. Retention mặc định báo rõ nguyên nhân mọi lần không có dữ liệu.
Đáp án đúng: A

Câu 33. Khi dùng rate từ bộ đếm tăng dần, điều gì cần xử lý?
A. Bộ đếm phải lưu dưới dạng tag để tính trung bình theo thời gian.
B. Bộ đếm có thể reset nên phải nhận biết bước giảm bất thường.
C. Bộ đếm tự tăng chính xác một đơn vị mỗi lần Telegraf đọc.
D. Bộ đếm luôn cho số đo hợp lệ dù không có timestamp của mẫu.
Đáp án đúng: B

Câu 34. Khi ghi metric theo lô thay vì từng điểm, lợi ích thường thấy là gì?
A. Giảm số lượt gửi qua mạng và chi phí xử lý mỗi yêu cầu.
B. Loại bỏ hoàn toàn nhu cầu kiểm tra lỗi sau khi gửi dữ liệu.
C. Đảm bảo mọi điểm ghi trong lô luôn được lưu vĩnh viễn.
D. Buộc các measurement của lô dùng chung một timestamp.
Đáp án đúng: A

Câu 35. Nếu ghi nhiều điểm thất bại do HTTP 429, chiến lược nào thích hợp?
A. Bỏ xác thực cho yêu cầu tiếp theo để giảm độ trễ ghi.
B. Gửi lại liên tục không chờ để rút ngắn thời gian ghi.
C. Xóa toàn bộ timestamp cũ trước khi thử gửi dữ liệu tiếp.
D. Giảm tốc và thử lại có backoff để tránh tăng tải đột ngột.
Đáp án đúng: D

Câu 36. Để bảo vệ kênh Telegraf gửi dữ liệu lên InfluxDB, nên làm gì?
A. Dùng TLS và token được cấp đúng quyền ghi vào đích cần thiết.
B. Chỉ kiểm tra IP máy chủ và tắt xác minh chứng chỉ TLS.
C. Chia sẻ token quản trị toàn hệ thống cho mọi agent thu thập.
D. Truyền mật khẩu trong tham số URL công khai để dễ debug.
Đáp án đúng: A

Câu 37. Khi truy vấn một measurement rất chậm, bước điều tra nào hợp lý?
A. Chỉ tăng khoảng refresh dashboard mà không đo lại truy vấn.
B. Tạo tag mới duy nhất trên mỗi điểm để tách dữ liệu nhỏ hơn.
C. Xem dải thời gian, bộ lọc tags và khối lượng series quét.
D. Xóa bớt dữ liệu của các measurement khác mà không kiểm tra.
Đáp án đúng: C

Câu 38. Khi bộ nhớ tăng mạnh theo số thiết bị, nguyên nhân nào đáng kiểm tra?
A. Cardinality của tag set và số series khác nhau đang phát sinh.
B. Số lượng màu sắc được cấu hình trong giao diện biểu đồ.
C. Độ chính xác phép đo số thực của một field không được hiển thị.
D. Tần suất làm mới trình duyệt của từng tài khoản dashboard.
Đáp án đúng: A

Câu 39. Khi xây dựng dashboard latency, chỉ dùng trung bình có điểm yếu gì?
A. Không bao giờ có thể tính từ field số trong time-series.
B. Không bộc lộ rõ các request rất chậm ở phần đuôi phân phối.
C. Luôn phải đọc từ một measurement khác thay vì dữ liệu nguồn.
D. Luôn hiển thị giá trị lớn nhất của từng khoảng một cách chính xác.
Đáp án đúng: B

Câu 40. Khi cần khôi phục dữ liệu time-series sau lỗi lưu trữ, nên chuẩn bị gì?
A. Chỉ dùng TTL dài vì retention dài tự thay thế mọi backup.
B. Backup có thử khôi phục và xác định thời gian mất dữ liệu chấp nhận.
C. Chỉ đặt thêm tags cho bản ghi vì tags sẽ sao lưu từng thời điểm.
D. Chỉ tăng kích thước bucket để dữ liệu không bị mất khi hỏng đĩa.
Đáp án đúng: B

Một nền tảng bán hàng có 80% lưu lượng xem sản phẩm và chỉ 3% thanh toán, nhưng kịch bản phát tải hiện gửi mọi yêu cầu tới API thanh toán với tỷ lệ ngang nhau; kết quả đo không phản ánh mức sử dụng hệ thống trong một ngày bình thường.
Trong đợt mở bán vé, số yêu cầu mới mỗi giây tăng đột biến dù nhiều phiên trước vẫn đang chờ phản hồi; bộ kiểm thử chỉ dùng số lượng người dùng ảo cố định và giảm tốc khi server chậm, khiến nhóm cần xem lại mô hình phát tải.
Một công cụ phát tải gửi yêu cầu tìm kiếm liên tục không có thời gian đọc kết quả hoặc chọn bộ lọc, trong khi người dùng thật thường dừng vài giây giữa các thao tác; nhóm cần đánh giá ảnh hưởng của hành vi người dùng tới mức tải.
Hệ thống đăng nhập dùng token có thời hạn ngắn, nhưng test hiệu năng tái sử dụng một token cho toàn bộ giờ chạy; hàng nghìn phản hồi 401 được tính là request hoàn tất nhanh và làm chỉ số latency trông tốt bất thường.
Báo cáo kiểm thử API giỏ hàng có latency trung bình thấp, nhưng p99 vượt nhiều giây vào giờ cao điểm; đội sản phẩm cần phân tích mức độ ảnh hưởng tới nhóm người dùng phải chờ lâu nhất.
Hai lần đo cùng API có p95 gần bằng nhau nhưng một lần xuất hiện vài yêu cầu mất hơn một phút; nhóm đang chỉ báo cáo p95 và chưa xác định có cần xem thêm p99, timeout và phân bố đuôi hay không.
Khi tăng tải từ 200 lên 500 yêu cầu mỗi giây, throughput thành công gần như không tăng trong khi thời gian chờ và số lỗi bắt đầu leo thang; nhóm cần nhận diện giới hạn công suất từ các số liệu quan sát được.
Đội loại toàn bộ yêu cầu thất bại khỏi biểu đồ độ trễ, khiến lần chạy gây 20% timeout lại có latency đẹp hơn lần chạy ổn định; nhóm phải xác định cách báo cáo song song tốc độ, lỗi và độ trễ.
Một API giới hạn số yêu cầu mỗi tài khoản và trả về 429 dưới tải lớn; trình phát tải tiếp tục gửi không giới hạn nên nhóm nhầm cơ chế bảo vệ có chủ đích với sự cố hiệu năng máy chủ.
Trong thử nghiệm tải cao, CPU của máy phát tải đạt 100% và lưu lượng phát ra thấp hơn mục tiêu, nhưng dashboard vẫn kết luận ứng dụng đã chạm trần xử lý; nhóm cần phân định giới hạn công cụ và giới hạn hệ thống được đo.
Staging chỉ có một instance và cơ sở dữ liệu ít tài nguyên, trong khi production dùng nhiều instance cùng cache phân tán; đội định dùng số request tối đa trên staging làm kết luận trực tiếp về năng lực của production.
Một bài load test chạy sau khi cache sản phẩm đã được nạp đầy, nên kết quả rất nhanh; vào buổi sáng sau đợt triển khai, hàng nghìn yêu cầu đầu tiên lại chậm và thường vượt timeout.
Sau khi khởi động JVM mới, yêu cầu đầu tiên mất nhiều thời gian hơn các yêu cầu tiếp theo vì khởi tạo lớp và tối ưu runtime; nhóm cần xác định giai đoạn làm nóng trước khi đo latency ổn định.
Bộ kiểm thử cơ sở dữ liệu chỉ có vài trăm sản phẩm, trong khi hệ thống thật có hàng triệu bản ghi; một API tìm kiếm chạy nhanh ở môi trường thử nhưng chậm rõ rệt khi các bộ lọc có độ chọn lọc thấp.
Trong bài thử danh sách lịch sử đơn hàng, p95 tăng mạnh ở trang sâu dù CPU ứng dụng thấp; số liệu truy vấn cho thấy database đọc nhiều dòng hơn sau mỗi lần phân trang.
Một dịch vụ Spring Boot tăng thread xử lý để đáp ứng tải nhưng pool kết nối database không tăng; hàng loạt request chờ kết nối và throughput không cải thiện dù CPU còn dư.
Hệ thống tạo báo cáo liên tục cấp phát lượng đối tượng lớn, khiến đồ thị heap có nhiều lần thu gom bộ nhớ kéo dài trùng với các đỉnh p99; nhóm cần phân tích mối liên hệ giữa GC và độ trễ.
API upload tệp cho thấy CPU chỉ sử dụng 30% nhưng throughput không tăng, trong khi độ trễ ghi đĩa và số kết nối I/O đang cao; đội phải xác định tài nguyên nào mới là giới hạn chính.
Một request đặt hàng gọi đồng bộ dịch vụ kiểm tra địa chỉ ở khu vực khác; dưới tải nhiều người dùng, chỉ vài lần phản hồi chậm từ đối tác đã kéo dài đáng kể thời gian hoàn tất cả hành trình.
Khi gateway thanh toán chậm, các service tự động retry cùng lúc; công cụ đo ghi số lượt gọi nội bộ tăng gấp nhiều lần số yêu cầu người dùng và đội cần đánh giá tác động của tải được khuếch đại.
Ứng dụng nhận dữ liệu cảm biến trả phản hồi HTTP ngay sau khi đưa sự kiện vào hàng đợi, nhưng worker ghi dữ liệu phía sau chậm dần và backlog tăng liên tục; bài test hiện chỉ đo latency của endpoint nhận.
Một hệ thống tạo hóa đơn bất đồng bộ trả mã tác vụ trong vài mili giây; người dùng thực vẫn chờ vài chục giây mới tải được hóa đơn, nhưng báo cáo hiệu năng chỉ tính đến thời điểm API chấp nhận yêu cầu.
Khi tăng số worker Java gấp đôi, throughput giảm và thời gian chờ khóa tăng; đội từng dự đoán tăng worker luôn giúp xử lý nhanh hơn nhưng không theo dõi tranh chấp và chuyển ngữ cảnh.
Trong thử nghiệm tăng số replica dịch vụ, throughput gần như không đổi vì mọi replica cùng tranh chấp một bảng khóa ở database; nhóm cần đánh giá giới hạn mở rộng theo cấu trúc phụ thuộc.
Một hệ thống có tự động mở rộng số instance sau vài phút CPU cao; đợt truy cập tăng đột ngột kéo dài một phút đã kết thúc trước khi replica mới sẵn sàng, làm người dùng gặp lỗi dù số instance cuối cùng đủ lớn.
Trong đợt mở bán, lưu lượng tăng từ mức bình thường lên gấp mười trong vài giây; bài test hiện chỉ tăng tải đều đặn trong nửa giờ nên chưa quan sát được hành vi khi hệ thống chịu cú sốc ngắn.
Một thử nghiệm kéo dài 15 phút cho kết quả ổn định, nhưng sau nhiều giờ xử lý liên tục dịch vụ tăng dần số kết nối và mức dùng heap; đội cần xác định cách quan sát suy giảm tích lũy qua thời gian.
Trong khi chạy stress test, một instance xử lý đơn bị dừng rồi khởi động lại; nhiều yêu cầu gặp lỗi ngắn hạn nhưng hệ thống hồi phục, đặt ra yêu cầu đo thời gian phục hồi và ảnh hưởng đến người dùng.
Đội tối ưu một truy vấn và tuyên bố cải thiện 40%, nhưng lượt đo trước chạy với cache lạnh và dữ liệu lớn hơn, còn lượt sau dùng cache ấm cùng ít bản ghi; kết luận đang dựa trên hai điều kiện không tương đương.
Một thay đổi thuật toán làm latency median tốt hơn nhưng tăng số truy vấn database trên mỗi yêu cầu; với tải nhỏ kết quả có lợi, còn ở tải cao pool kết nối cạn nhanh hơn bản cũ.
Nhóm phát tải từ nhiều máy nhưng đồng hồ và cách gắn mã yêu cầu không thống nhất, khiến khó đối chiếu biểu đồ p99 với log ứng dụng, trace và thời điểm database bị nghẽn.
Một pipeline CI đặt tiêu chí pass nếu latency trung bình nhỏ hơn 200 ms, nhưng cùng build có p95 vượt 2 giây và lỗi tăng khi tải chạm mục tiêu; nhóm cần xem lại tiêu chí chất lượng, biến động giữa các lần đo và ngưỡng phát hành phù hợp.

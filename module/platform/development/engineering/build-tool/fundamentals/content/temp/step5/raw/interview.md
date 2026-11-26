Build tool đảm nhận những công việc nào để chuyển mã nguồn Java thành artifact có thể kiểm thử và phát hành?
Bạn sẽ mô tả luồng từ biên dịch Java, xử lý tài nguyên đến đóng gói JAR trong một bản build như thế nào?
Những đầu vào và đầu ra nào cần được khai báo để một bước build có thể kiểm tra và tái sử dụng kết quả?
Bạn phân biệt task, goal, target và lifecycle trong các công cụ build Java bằng cách nào?
Đồ thị phụ thuộc giữa các tác vụ quyết định thứ tự thực thi của build như thế nào?
Nếu hai tác vụ cần cùng một kết quả trung gian, bạn tổ chức quan hệ phụ thuộc để tránh tính toán lặp ra sao?
Bạn giải thích khác biệt giữa cấu hình build và thực thi build khi lập kế hoạch các bước xử lý như thế nào?
Khi nào bạn nên dùng quy ước build có sẵn thay vì tự định nghĩa quy trình biên dịch?
Một plugin có thể bổ sung tác vụ, cấu hình và quy tắc vòng đời vào build theo cơ chế nào?
Bạn sẽ đánh giá độ tin cậy của một plugin bên thứ ba trước khi đưa nó vào dự án như thế nào?
Bạn phân biệt dependency trực tiếp, dependency bắc cầu và dependency chỉ dùng khi kiểm thử ra sao?
Khi hai thư viện yêu cầu các phiên bản khác nhau của cùng một dependency, bạn truy tìm và xử lý xung đột thế nào?
Bạn kiểm soát phiên bản thư viện để các máy phát triển và CI giải quyết dependency nhất quán ra sao?
Những khác biệt nào giữa compile classpath, runtime classpath và test classpath có thể gây lỗi chỉ xuất hiện khi chạy?
Bạn sẽ thiết kế cấu hình repository công khai và repository nội bộ để quản lý artifact như thế nào?
Khi repository từ xa bị gián đoạn, bạn xác định phần nào của bản build vẫn có thể chạy từ cache ra sao?
Bạn quản lý thông tin xác thực của repository trong CI mà không đưa bí mật vào mã nguồn như thế nào?
Bạn đánh giá nguy cơ từ phiên bản động hoặc snapshot đối với khả năng tái lập build ra sao?
Bạn sẽ cố định phiên bản build tool và JDK cho cả nhóm thông qua Wrapper và toolchain như thế nào?
Những yếu tố môi trường nào như múi giờ, locale hoặc đường dẫn có thể khiến hai bản build khác nhau?
Bạn thiết kế bản build có thể tái lập bằng cách kiểm soát thứ tự file, timestamp và metadata khi đóng gói như thế nào?
Khi resource filtering thay thế biến môi trường vào file cấu hình, bạn ngăn việc đóng gói nhầm bí mật bằng cách nào?
Bạn phân biệt kiểm thử đơn vị, kiểm thử tích hợp và kiểm thử hệ thống khi sắp xếp các bước của pipeline ra sao?
Bạn sẽ cấu hình để bản build thất bại khi kiểm thử hoặc kiểm tra chất lượng mã không đạt như thế nào?
Khi kiểm thử không ổn định làm pipeline thất bại ngẫu nhiên, bạn điều tra nguyên nhân thay vì bỏ qua lỗi ra sao?
Bạn lựa chọn giữa JAR, WAR và bản phân phối có dependency kèm theo dựa trên yêu cầu triển khai như thế nào?
Bạn kiểm tra nội dung artifact và manifest để bảo đảm có thể chạy ở môi trường đích ra sao?
Việc gộp dependency vào fat JAR có thể làm thay đổi khả năng nạp class và xử lý tài nguyên như thế nào?
Trong dự án nhiều module, bạn phân chia phần dùng chung và phần nghiệp vụ để giảm ghép nối ra sao?
Build tool xác định thứ tự build các module có quan hệ phụ thuộc với nhau bằng cách nào?
Nếu hai module phụ thuộc vòng nhau, bạn sẽ phát hiện và tái cấu trúc ranh giới như thế nào?
Bạn chia sẻ quy ước plugin, phiên bản dependency và cấu hình kiểm thử giữa các module ra sao?
Bạn đánh giá khi nào nên tách một module thành thư viện phát hành riêng thay vì giữ trong cùng repository?
Khi annotation processor sinh mã Java, bạn khai báo đầu vào và đầu ra để build xử lý chính xác thế nào?
Bạn giải thích điều kiện để một tác vụ được bỏ qua nhờ incremental build ra sao?
Khi một file cấu hình thay đổi nhưng tác vụ vẫn báo up-to-date, bạn tìm lỗi trong khai báo đầu vào như thế nào?
Bạn phân biệt build cache cục bộ, cache từ xa và cache dependency ở những lớp nào?
Khi nào một tác vụ có side effect không phù hợp để lưu kết quả vào build cache?
Bạn sẽ đo thời gian cấu hình, biên dịch, kiểm thử và đóng gói để tìm nút thắt build như thế nào?
Bạn đánh giá lợi ích và rủi ro của thực thi song song các task đối với dữ liệu dùng chung ra sao?
Khi áp dụng build tăng dần, bạn kiểm chứng thay đổi mã thật sự dẫn tới artifact và test cần thiết được chạy lại như thế nào?
Bạn tổ chức pipeline CI để tận dụng cache nhưng vẫn kiểm tra sạch trên môi trường mới ra sao?
Nếu build trên laptop thành công nhưng CI thất bại, bạn sẽ đối chiếu JDK, OS, biến môi trường và lệnh chạy như thế nào?
Bạn thiết kế các bước publish artifact để chỉ bản đã kiểm thử mới được đưa vào repository phát hành ra sao?
Bạn sẽ gắn version, commit hash và checksum vào thông tin phát hành để truy xuất artifact như thế nào?
Bạn đánh giá nhu cầu ký artifact, tạo SBOM và kiểm tra dependency trong quy trình phát hành ra sao?
Khi bản build thất bại do tải dependency, bạn phân biệt sự cố mạng, xác thực và artifact không tồn tại thế nào?
Bạn thiết kế chiến lược rollback khi artifact mới đã được publish nhưng chưa đáp ứng tiêu chí triển khai ra sao?
Bạn lựa chọn những chỉ số nào để theo dõi thời gian build, cache hit, tỷ lệ thất bại và độ ổn định theo thời gian?
Nếu nhóm chuyển từ Ant sang Maven hoặc Gradle, bạn đánh giá công sức di chuyển và rủi ro thay đổi hành vi build như thế nào?

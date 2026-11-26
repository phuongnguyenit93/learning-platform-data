Gradle Wrapper giải quyết vấn đề nhất quán phiên bản công cụ build giữa máy phát triển và CI như thế nào?
Bạn phân biệt vai trò của settings.gradle và build.gradle trong cấu trúc một dự án Gradle ra sao?
Bạn sẽ lựa chọn Groovy DSL hay Kotlin DSL dựa trên nhu cầu bảo trì, kiểm tra kiểu và hỗ trợ IDE như thế nào?
Bạn giải thích các giai đoạn initialization, configuration và execution của Gradle qua một ví dụ cụ thể ra sao?
Khi chạy một task, Gradle xác định các task phụ thuộc và thứ tự thực hiện như thế nào?
Bạn phân biệt dependsOn, mustRunAfter và finalizedBy khi biểu diễn quan hệ giữa các task ra sao?
Bạn sẽ định nghĩa một task tùy biến có đầu vào và đầu ra rõ ràng như thế nào?
Vì sao đăng ký task theo cách lazy có thể cải thiện thời gian cấu hình ở một dự án lớn?
Bạn áp dụng Provider API để tránh đọc giá trị cấu hình quá sớm trong build script như thế nào?
Khi một task báo UP-TO-DATE nhưng sản phẩm sai, bạn truy tìm lỗi khai báo input hoặc output ra sao?
Bạn phân biệt kết quả UP-TO-DATE, FROM-CACHE và task bị SKIPPED trong nhật ký build như thế nào?
Những điều kiện nào khiến một task không thích hợp để lưu kết quả vào build cache?
Bạn sẽ cấu hình build cache cục bộ và từ xa để giảm thời gian chạy CI như thế nào?
Khi dùng remote build cache, bạn kiểm soát quyền ghi và độ tin cậy của kết quả build được chia sẻ ra sao?
Configuration cache giúp Gradle giảm chi phí khởi tạo build trong những điều kiện nào?
Bạn sẽ xử lý một plugin hoặc task không tương thích với configuration cache bằng cách nào?
Bạn phân biệt áp dụng plugin bằng plugins block với tổ chức cấu hình build theo convention plugin ra sao?
Trong nhiều module, bạn chia sẻ quy tắc biên dịch và kiểm thử bằng convention plugin như thế nào?
Bạn lựa chọn version catalog để tập trung phiên bản plugin và thư viện trong một repository ra sao?
Bạn sẽ khai báo repository công khai, nội bộ và thứ tự tìm artifact để tránh lấy nhầm dependency như thế nào?
Các configuration implementation, api, compileOnly và runtimeOnly ảnh hưởng tới classpath của thư viện Java ra sao?
Khi một dependency được đưa vào api thay vì implementation, bạn đánh giá tác động đến module sử dụng thư viện như thế nào?
Bạn phân biệt dependency trực tiếp với dependency bắc cầu khi Gradle giải quyết đồ thị phiên bản ra sao?
Bạn sử dụng platform hoặc BOM để thống nhất phiên bản nhóm dependency như thế nào?
Dependency constraints và dependency locking giải quyết những vấn đề khác nhau nào?
Khi một thư viện dùng version động hoặc changing module, bạn kiểm soát tính tái lập của bản build ra sao?
Bạn sử dụng dependencyInsight để điều tra lý do Gradle chọn một phiên bản không mong đợi như thế nào?
Bạn sẽ đánh giá ưu nhược điểm của việc force một dependency so với sửa constraint hoặc cập nhật thư viện ra sao?
Bạn dùng dependency verification để kiểm tra checksum hoặc chữ ký artifact được tải về như thế nào?
Variant-aware dependency resolution giúp Gradle chọn artifact phù hợp theo những thuộc tính nào?
Bạn thiết kế project dependency giữa các subproject để tránh vòng lặp và giảm ghép nối như thế nào?
Bạn so sánh multi-project build với composite build khi tái sử dụng một thư viện đang phát triển ra sao?
Bạn sẽ cấu hình Java toolchain để biên dịch và kiểm thử nhất quán trên nhiều máy như thế nào?
Khi thêm annotation processor, bạn quản lý dependency processor và mã Java được sinh ra ra sao?
Bạn sử dụng test task để cấu hình JUnit Platform, bộ lọc test và báo cáo kết quả như thế nào?
Bạn tổ chức một suite kiểm thử tích hợp tách biệt với unit test để CI chạy theo các giai đoạn ra sao?
Bạn sẽ kiểm tra nguyên nhân test task luôn chạy lại mặc dù mã không thay đổi như thế nào?
Bạn cấu hình processResources để xử lý tài nguyên mà không đưa bí mật vào JAR ra sao?
Bạn lựa chọn giữa jar, bản phân phối application và artifact đóng gói kèm dependency theo yêu cầu triển khai như thế nào?
Khi tạo JAR, bạn kiểm soát thứ tự tệp, timestamp và metadata để có đầu ra tái lập như thế nào?
Bạn sử dụng maven-publish để phát hành artifact kèm POM và thông tin phiên bản ra sao?
Bạn sẽ lấy thông tin xác thực của repository phát hành từ CI theo cách nào để tránh lộ trong source control?
Khi xây dựng nhiều subproject song song, bạn xác minh các task không ghi chung đầu ra và gây race condition ra sao?
Bạn đánh giá lợi ích của incremental compilation khi chỉ thay đổi phần triển khai so với thay đổi API công khai ra sao?
Bạn sẽ đọc build scan hoặc nhật ký --info để xác định điểm nghẽn thời gian cấu hình và kiểm thử như thế nào?
Bạn tổ chức pipeline CI sử dụng Wrapper, dependency cache và build cache với bước xác minh sạch ra sao?
Khi một bản build thành công tại máy cá nhân nhưng lỗi ở CI, bạn kiểm tra toolchain, Gradle property và biến môi trường ra sao?
Bạn kiểm soát quá trình nâng cấp Gradle và plugin để phát hiện API không còn được hỗ trợ bằng cách nào?
Bạn sẽ thiết kế cách xử lý lỗi tải dependency và chế độ offline khi repository tạm thời không truy cập được như thế nào?
Khi tối ưu build của repository nhiều module, bạn ưu tiên thay đổi nào và dùng chỉ số gì để chứng minh hiệu quả?

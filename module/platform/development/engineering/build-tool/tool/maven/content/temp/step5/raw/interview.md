Maven sử dụng POM và các quy ước thư mục để chuẩn hóa quy trình build Java như thế nào?
Bạn phân biệt groupId, artifactId, version và packaging khi định danh một sản phẩm Maven ra sao?
Bạn giải thích vai trò của parent POM, module aggregator và module con trong dự án nhiều module như thế nào?
Những thành phần nào trong effective POM được kế thừa từ parent, Super POM hoặc cấu hình hiện tại?
Bạn sẽ dùng lệnh nào để kiểm tra effective POM khi cấu hình plugin không hoạt động như mong đợi?
Bạn phân biệt ba vòng đời clean, default và site của Maven theo mục đích sử dụng ra sao?
Khi chạy mvn verify, Maven sẽ đi qua các phase và thực hiện các plugin goal đã gắn như thế nào?
Bạn sẽ giải thích khác biệt giữa phase, plugin và goal bằng ví dụ biên dịch Java ra sao?
Bạn quyết định gắn một goal tự định nghĩa vào phase nào để không phá vỡ trình tự kiểm thử như thế nào?
Bạn phân biệt plugins và pluginManagement khi chuẩn hóa phiên bản plugin cho nhiều module ra sao?
Khi khai báo một plugin ở parent, bạn sẽ kiểm tra tác động của cấu hình và execution lên module con như thế nào?
Bạn tổ chức các property trong POM để kiểm soát phiên bản Java, plugin và thư viện như thế nào?
Khi một profile được kích hoạt bởi property, JDK hoặc môi trường, bạn kiểm chứng profile đang hoạt động ra sao?
Bạn sẽ hạn chế cấu hình phụ thuộc vào profile để bản build trên máy cá nhân và CI nhất quán như thế nào?
Maven reactor quyết định thứ tự build các module dựa trên quan hệ phụ thuộc nào?
Bạn sử dụng tùy chọn -pl và -am để chỉ build một module cùng các dependency trong reactor như thế nào?
Khi một module của reactor phụ thuộc vòng vào module khác, bạn tìm và thay đổi ranh giới kiến trúc ra sao?
Các scope compile, provided, runtime và test ảnh hưởng đến classpath ở những giai đoạn nào?
Bạn phân biệt dependency có optional=true với dependency bị loại trừ bằng exclusions như thế nào?
Khi hai dependency bắc cầu yêu cầu cùng thư viện nhưng khác phiên bản, Maven chọn phiên bản theo quy tắc nào?
Bạn sẽ đọc kết quả mvn dependency:tree để truy vết nguồn gốc một xung đột thư viện như thế nào?
Bạn sử dụng dependencyManagement để kiểm soát phiên bản mà không tự động thêm dependency vào module ra sao?
Bạn sẽ import BOM trong dependencyManagement để đồng bộ phiên bản các thư viện liên quan như thế nào?
Khi parent và BOM khai báo những phiên bản khác nhau, bạn kiểm tra thứ tự ưu tiên và effective POM ra sao?
Bạn sẽ phân biệt artifact release với SNAPSHOT và đánh giá ảnh hưởng đến tính tái lập của build như thế nào?
Maven local repository lưu artifact theo cấu trúc nào và có thể dẫn tới lỗi cũ hoặc thiếu dependency ra sao?
Bạn cấu hình repository và mirror trong settings.xml để tải artifact qua kho nội bộ như thế nào?
Khi một artifact không tải được, bạn phân biệt nguyên nhân mạng, quyền truy cập, cache lỗi và tọa độ sai ra sao?
Bạn quản lý credentials cho repository trong settings.xml và biến môi trường CI như thế nào để tránh lộ bí mật?
Bạn giải thích vai trò của pluginRepositories và sự khác biệt với repositories trong Maven như thế nào?
Bạn sẽ dùng Maven Wrapper để đồng bộ phiên bản Maven giữa laptop và pipeline CI ra sao?
Bạn cấu hình Maven Compiler Plugin với release và đánh giá tác động của JDK đang chạy Maven như thế nào?
Khi cần nhiều phiên bản JDK trên một máy, bạn dùng Maven Toolchains để giải quyết vấn đề nào?
Bạn sẽ xử lý resource filtering và mã hóa UTF-8 để tránh thay thế nhầm token trong file cấu hình như thế nào?
Annotation processor tác động đến quá trình compile Java ra sao và cần được khai báo tách biệt khi nào?
Bạn sử dụng Maven Surefire Plugin để chọn unit test và xuất báo cáo phục vụ CI như thế nào?
Bạn phân biệt Maven Surefire và Failsafe trong cách chạy và xác minh integration test ra sao?
Khi có các ca kiểm thử không ổn định, bạn sẽ điều tra lỗi thay vì bật tùy chọn bỏ qua test như thế nào?
Bạn chọn cách đóng gói JAR, WAR, assembly hoặc shaded JAR dựa trên yêu cầu triển khai ra sao?
Khi dùng Maven Shade Plugin, bạn kiểm tra rủi ro trùng class, relocation và tài nguyên META-INF như thế nào?
Bạn sẽ tạo manifest và kiểm tra nội dung artifact sau phase package để bảo đảm có thể chạy đúng như thế nào?
Bạn cấu hình timestamp, thứ tự file và plugin phù hợp để nâng cao tính tái lập của JAR như thế nào?
Bạn đặt quy tắc Maven Enforcer nào để ngăn sử dụng phiên bản JDK, Maven hoặc dependency không hợp lệ?
Bạn tích hợp JaCoCo, Checkstyle hoặc kiểm tra dependency vào phase verify theo tiêu chí chặn build như thế nào?
Bạn sẽ sử dụng build cache của CI và thư mục .m2 như thế nào mà vẫn tránh dependency không đồng nhất?
Khi chạy Maven song song bằng -T, bạn đánh giá mức độ thread-safe của plugin và tài nguyên dùng chung ra sao?
Bạn thiết kế pipeline chạy Maven ở batch mode, lưu test report và dừng đúng khi bước verify thất bại như thế nào?
Bạn sử dụng install và deploy khác nhau ra sao khi chuẩn bị artifact cho module khác hoặc repository phát hành?
Bạn xây dựng quy trình quản lý phiên bản, ký artifact và xuất bản release để dễ truy vết hoặc rollback như thế nào?
Nếu một bản build chỉ lỗi trên CI nhưng thành công ở máy cá nhân, bạn sẽ thu thập những thông tin Maven nào để tái hiện và tìm nguyên nhân?

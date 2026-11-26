Apache Ant tổ chức quy trình build Java dựa trên target và task như thế nào?
Bạn giải thích các thành phần project, name, default và basedir của một file build.xml ra sao?
Bạn sẽ thiết kế các target clean, compile, test và package với quan hệ depends như thế nào?
Khi hai target cùng phụ thuộc một target chuẩn bị, Ant quyết định số lần chạy target đó ra sao?
Bạn so sánh cách mô tả build bằng các bước tường minh của Ant với mô hình vòng đời theo quy ước như thế nào?
Bạn quản lý các property dùng chung cho đường dẫn thư mục nguồn, kết quả biên dịch và artifact ra sao?
Tính chất không ghi đè giá trị property đã đặt trong Ant ảnh hưởng thế nào đến cấu hình môi trường?
Khi nhận property từ dòng lệnh và file cấu hình, bạn tổ chức mức ưu tiên để chạy build nhất quán như thế nào?
Bạn sử dụng target có điều kiện if hoặc unless để xử lý bước build tùy môi trường ra sao?
Bạn sẽ tạo các thư mục đầu ra bằng mkdir và xác định thứ tự trước khi chạy javac như thế nào?
Bạn cấu hình task javac để biên dịch nguồn Java theo phiên bản JDK và encoding yêu cầu ra sao?
Khi javac chạy thành công nhưng ứng dụng thiếu thư viện lúc chạy, bạn kiểm tra classpath bằng cách nào?
Bạn xây dựng Path và tham chiếu refid để chia sẻ classpath giữa biên dịch và kiểm thử như thế nào?
Bạn phân biệt FileSet, DirSet và Path khi lựa chọn tập file và thư mục cho một task ra sao?
Bạn sử dụng include và exclude pattern trong FileSet để chọn đúng tài nguyên đóng gói như thế nào?
Khi một quy tắc loại trừ quá rộng khiến thiếu file cấu hình, bạn sẽ tìm nguyên nhân bằng cách nào?
Bạn sử dụng copy và filter để đưa tài nguyên vào thư mục build mà không thay đổi file nguồn như thế nào?
Khi thay thế token trong tài nguyên, bạn ngăn bí mật môi trường bị ghi vào artifact ra sao?
Bạn sẽ đặt quy tắc xóa của target clean thế nào để tránh xóa nhầm dữ liệu bên ngoài thư mục build?
Bạn sử dụng task jar và manifest để tạo JAR có entry point phù hợp như thế nào?
Khi cần đóng gói thư viện và cấu hình vào một bản phân phối, bạn lựa chọn zip, tar hoặc task khác ra sao?
Một JAR chứa hai bản sao cùng tên tài nguyên có thể gây lỗi gì và bạn sẽ kiểm tra kết quả đóng gói thế nào?
Bạn thiết kế target junit để chạy unit test và lưu kết quả phục vụ CI như thế nào?
Bạn phân biệt điều kiện test thất bại với lỗi không thực thi được test trong quy trình Ant ra sao?
Bạn sẽ xuất báo cáo XML hoặc HTML từ kết quả kiểm thử để nhóm dễ xác định ca lỗi như thế nào?
Khi chỉ một số test cần chạy trước khi đóng gói, bạn quản lý tập test được chọn như thế nào?
Bạn sẽ phân biệt target compile và compile-tests về classpath, thư mục đầu ra và thứ tự thực thi ra sao?
Khi thay đổi một file Java mà Ant không biên dịch lại các file phụ thuộc cần thiết, bạn xác định giới hạn tăng dần ra sao?
Bạn sử dụng task uptodate và điều kiện về timestamp để tránh chạy bước tạo file không cần thiết như thế nào?
Những rủi ro nào xuất hiện khi dựa hoàn toàn vào thời gian sửa file để quyết định có build lại hay không?
Bạn dùng macrodef để tái sử dụng chuỗi task có tham số trong nhiều target như thế nào?
Bạn phân biệt macrodef và presetdef khi muốn chuẩn hóa cách dùng một task ra sao?
Khi gọi một target qua antcall, bạn cần chú ý điều gì về project con, property và tác vụ phụ thuộc?
Bạn sẽ dùng import hoặc include để chia sẻ cấu hình build giữa các dự án mà không tạo xung đột target ra sao?
Trong dự án nhiều module, bạn tổ chức build cha và lời gọi Ant con để kiểm soát thứ tự biên dịch như thế nào?
Bạn xây dựng custom task bằng Java cho một thao tác đặc thù khi task có sẵn chưa đáp ứng như thế nào?
Khi dùng exec để gọi công cụ ngoài, bạn xử lý đường dẫn, mã thoát và khác biệt hệ điều hành ra sao?
Bạn giải thích vai trò của Ivy trong việc bổ sung quản lý dependency cho Apache Ant như thế nào?
Bạn sẽ cấu hình Ivy resolve và retrieve để đưa dependency vào classpath của các target ra sao?
Các configuration và dependency bắc cầu trong Ivy giúp bạn tách thư viện compile, runtime và test như thế nào?
Khi hai dependency của Ivy yêu cầu phiên bản xung đột, bạn phân tích báo cáo resolution và chọn cách xử lý ra sao?
Bạn sẽ hạn chế version động của Ivy để bản build trên hai máy lấy cùng tập JAR như thế nào?
Khi cache Ivy có artifact cũ hoặc repository tạm thời lỗi, bạn kiểm tra kết quả resolve bằng cách nào?
Bạn thiết kế quy trình publish artifact với Ivy hoặc Ant để lưu đủ phiên bản và metadata như thế nào?
Bạn sẽ đặt công cụ Ant, phiên bản JDK và biến môi trường trong CI để kết quả build có thể lặp lại ra sao?
Khi build chạy tốt trên Windows nhưng lỗi trên Linux, bạn kiểm tra dấu phân cách đường dẫn và line ending như thế nào?
Bạn sử dụng các tùy chọn verbose, debug hoặc diagnostics của Ant để điều tra target thất bại ra sao?
Bạn đánh giá rủi ro khi dùng parallel task trong Ant nếu nhiều tác vụ cùng ghi vào một thư mục như thế nào?
Bạn xây dựng quy trình kiểm tra checksum và kiểm tra nội dung artifact trước khi đưa bản build vào phát hành ra sao?
Khi bảo trì một hệ thống Ant lâu năm, bạn ưu tiên đơn giản hóa target và bổ sung kiểm thử trước khi thay đổi công cụ build như thế nào?

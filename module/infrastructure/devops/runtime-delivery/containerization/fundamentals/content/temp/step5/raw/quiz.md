Trong cùng một máy Linux, điểm khác biệt chính về kernel giữa container và máy ảo thông dụng là gì?
A. Container luôn khởi động kernel riêng trước khi chạy ứng dụng.
B. Container chia sẻ kernel host; máy ảo thường có kernel guest.
C. Máy ảo dùng chung PID namespace với mọi tiến trình trên host.
D. Container cần hypervisor để mô phỏng thiết bị và kernel guest.
Đáp án đúng: B

Một tiến trình có PID 1 bên trong container nhưng PID khác khi xem từ host. Tính năng kernel nào lý giải trực tiếp điều này?
A. PID namespace tạo góc nhìn và hệ thống định danh tiến trình riêng.
B. Mount namespace cấp ngân sách CPU và RAM cho tập tiến trình.
C. Cgroup namespace thay đổi PID được hiển thị bên trong container.
D. Network namespace đặt lại ID tiến trình theo giao diện mạng.
Đáp án đúng: A

Container bị OOM kill dù host vẫn còn RAM trống; ứng dụng đã chạm ngưỡng bộ nhớ được cấp. Cơ chế nào giải thích chính xác?
A. PID namespace giới hạn RAM theo số tiến trình còn hoạt động.
B. Memory cgroup áp hạn mức riêng và có thể kích hoạt OOM.
C. Image layer buộc tổng bộ nhớ sử dụng không vượt kích cỡ image.
D. Network namespace tự thu hồi heap khi băng thông vượt giới hạn.
Đáp án đúng: B

Một ứng dụng ghi thêm tệp trong container nhưng digest image gốc không đổi. Giải thích nào phù hợp với cơ chế layer?
A. Digest image chỉ tính metadata mạng nên bỏ qua nội dung tệp.
B. Mọi thay đổi được ghi ngược vào registry mà không đổi digest.
C. Thay đổi nằm ở writable layer của container, tách khỏi image.
D. Tệp ghi mới chỉ nằm trong RAM và luôn mất khi tiến trình dừng.
Đáp án đúng: C

Build ứng dụng Go cần compiler và công cụ test, nhưng image chạy chỉ cần binary. Phương án Dockerfile nào phù hợp?
A. Build trong một stage rồi copy binary sang stage runtime tối giản.
B. Giữ compiler ở image chạy nhưng xóa source trước khi khởi động.
C. Sao chép toàn bộ source và thư mục cache vào image chạy cuối.
D. Đổi tag image chạy thành slim để engine tự bỏ các build tool.
Đáp án đúng: A

Dockerfile COPY toàn bộ source trước RUN cài dependencies; sửa một tệp ứng dụng làm bước cài dependencies chạy lại. Vì sao?
A. Docker không cache những lệnh RUN có truy cập hệ thống tệp.
B. Registry tự xóa cache khi phát hiện source code thay đổi.
C. Thay đổi ở lớp COPY trước đó làm mất cache của bước kế tiếp.
D. Docker runtime luôn build lại toàn bộ image mỗi lần container chạy.
Đáp án đúng: C

Container web ngừng rất chậm khi nhận SIGTERM; shell script là PID 1 và chạy server ở tiến trình con nhưng không chuyển tiếp tín hiệu. Điểm nào cần xem xét?
A. Network driver có thể chặn tín hiệu từ host tới container.
B. CPU quota thấp khiến SIGTERM không được kernel chuyển giao.
C. Healthcheck có thể thay thế việc xử lý signal khi dừng container.
D. Tiến trình chính cần nhận và xử lý tín hiệu dừng đúng cách.
Đáp án đúng: D

API và database nằm trong hai container cùng user-defined bridge; API gọi localhost:5432 nên không kết nối được database. Vì sao?
A. Localhost tham chiếu network namespace của container API.
B. Localhost mặc định trỏ tới gateway của bridge network.
C. Container chỉ kết nối nhau khi publish port lên host.
D. Bridge network buộc service dùng địa chỉ IP của host.
Đáp án đúng: A

Hai container cùng user-defined bridge network cần giao tiếp cổng 5432; không muốn mở cổng database ra host. Nhận định nào đúng?
A. Chỉ dùng được DNS service sau khi bind cổng database lên host.
B. Container phải gọi IP của host và cổng đã được publish.
C. Cần chung namespace mạng mới truy cập được cổng database.
D. Container cùng bridge có thể kết nối trực tiếp qua tên và cổng nội bộ.
Đáp án đúng: D

Cơ sở dữ liệu trong container cần giữ dữ liệu sau khi container bị xóa và tạo lại. Lựa chọn lưu trữ nào đáp ứng?
A. Writable layer của container, miễn là tên container không đổi.
B. Named volume gắn tại thư mục dữ liệu, có vòng đời riêng.
C. Image layer vì các lần ghi runtime tự cập nhật image gốc.
D. Tmpfs mount vì dữ liệu vẫn được giữ khi container kết thúc.
Đáp án đúng: B

Khi bind mount thư mục mã nguồn từ host vào /app, các tệp /app được COPY vào image lúc build dường như biến mất. Vì sao?
A. Cache build của image bị xóa khi engine tạo bind mount.
B. Bind mount che nội dung sẵn có tại điểm mount trong image.
C. Cgroup memory tự giải phóng file khi phát hiện mount mới.
D. Bridge network thay đổi quyền sở hữu tệp dưới đường dẫn.
Đáp án đúng: B

Tác vụ CPU-bound của container bị chậm khi chạm CPU quota nhưng không vượt memory limit. Điều gì thường xảy ra?
A. Kernel kích hoạt OOMKill ngay khi chạm giới hạn CPU.
B. Runtime tự mở rộng số core host cấp cho container.
C. CPU cgroup throttling tiến trình khi dùng hết quota.
D. Writable layer chuyển dữ liệu sang disk để giảm tải CPU.
Đáp án đúng: C

Một tag image trên registry có thể được trỏ sang bản build khác mà không đổi tên. Khi triển khai, cách xác định nội dung artifact nào đáng tin cậy hơn?
A. Dựa vào tên repository và thời gian push gần nhất.
B. Dựa vào container name được tạo ở máy triển khai.
C. Dựa vào tên nhánh Git được ghi trong thông báo release.
D. Dùng digest của manifest image đã được xác minh.
Đáp án đúng: D

Image chạy trên máy amd64 nhưng gặp exec format error khi chuyển sang arm64. Thông tin nào của artifact cần kiểm tra đầu tiên?
A. Lịch healthcheck có khác nhau giữa hai máy host hay không.
B. Volume driver có đồng bộ đường dẫn trên CPU arm64 hay không.
C. Manifest image có biến thể phù hợp kiến trúc arm64 hay không.
D. Bridge network có bật định tuyến cho phần cứng arm64 hay không.
Đáp án đúng: C

Một container chạy ứng dụng chỉ nghe cổng 8080 nhưng được cấp privileged và mount Docker socket; rủi ro lớn nhất là gì?
A. Quyền vượt nhu cầu có thể mở rộng tác động khi container bị xâm nhập.
B. Container không thể mở cổng 8080 nếu không chạy chế độ privileged.
C. Docker socket chỉ cho xem log nên không mở thêm quyền điều khiển host.
D. Network namespace sẽ vô hiệu nếu container có quyền truy cập Docker socket.
Đáp án đúng: A

Container còn trạng thái Running dù ứng dụng HTTP treo, healthcheck báo unhealthy. Nhận định nào đúng về restart policy?
A. Healthcheck lỗi luôn làm container tự restart ngay theo restart policy.
B. Restart policy luôn khởi tạo container mới khi HTTP healthcheck lỗi.
C. Trạng thái Running bảo đảm tiến trình đang phục vụ request bình thường.
D. Unhealthy không tự kích hoạt restart với restart policy mặc định.
Đáp án đúng: D

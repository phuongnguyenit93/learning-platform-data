Một tổ chức muốn quản lý nhiều repository trong cùng phạm vi cộng tác trên Bitbucket Cloud. Cách tổ chức nào phù hợp?
A. Đặt các repository vào workspace và cấp quyền theo nhóm phù hợp.
B. Tạo một branch chung để mọi repository dùng cùng cấu hình quyền.
C. Gom repository thành pull request cấp workspace để cùng review.
D. Dùng chung một deployment environment thay cho phân quyền kho mã.
Đáp án đúng: A

Nhóm muốn ngăn push trực tiếp lên main nhưng vẫn cho phép cộng tác qua pull request. Cơ chế nào nên cấu hình?
A. Bật webhook khi push để hệ thống tự từ chối commit mới.
B. Thêm quy định trong README nhưng giữ nguyên quyền ghi nhánh.
C. Chỉ đặt main làm default branch trong cài đặt repository.
D. Đặt branch restrictions cho main để giới hạn hành vi push.
Đáp án đúng: D

Một người đóng góp chỉ có quyền đọc repository chính và muốn sửa lỗi. Quy trình nào phù hợp?
A. Dùng repository webhook để ghi commit vào kho chính từ xa.
B. Tạo branch trong kho chính dù không được cấp quyền ghi mã.
C. Gửi patch bằng pipeline rồi tự merge vào nhánh main của kho.
D. Fork repository, tạo branch riêng và mở pull request về nguồn.
Đáp án đúng: D

Khi đánh giá thay đổi trước khi hợp nhất trong Bitbucket, lợi ích cốt lõi của pull request là gì?
A. Tạo bản release và tự gắn tag cho mọi commit của nhánh nguồn.
B. Xem diff, trao đổi với reviewer và kiểm chứng thay đổi trước merge.
C. Đồng bộ toàn bộ nhánh của các repository thuộc workspace.
D. Cấp quyền admin tạm thời cho tác giả sau khi build thành công.
Đáp án đúng: B

Nhánh release phải có hai phê duyệt và build thành công trước khi được merge. Cơ chế nào trực tiếp kiểm soát điều kiện này?
A. Thiết lập branch naming rule nhưng không kiểm tra trạng thái build.
B. Thêm mô tả trong pull request và cho tác giả tự đánh dấu hoàn tất.
C. Thiết lập merge checks yêu cầu approval và kết quả build đạt.
D. Thiết lập webhook gửi tin nhắn sau khi pull request được tạo.
Đáp án đúng: C

Repository muốn dùng Bitbucket Pipelines để chạy kiểm thử khi mã thay đổi. Khai báo pipeline nên nằm ở đâu?
A. Trong metadata của từng pull request thay vì tệp trong Git.
B. Trong Dockerfile của image ứng dụng ở thư mục công cụ build.
C. Trong bitbucket-pipelines.yml tại gốc repository được quản lý.
D. Trong cấu hình workspace group dùng để phân quyền repository.
Đáp án đúng: C

Một pipeline cần token để gọi dịch vụ phát hành mà không muốn đưa token vào source control. Cách nào phù hợp?
A. Lưu token bằng secured variable và giới hạn quyền sử dụng.
B. Ghi token vào Dockerfile rồi chỉ xóa ở bước build cuối cùng.
C. Commit token trong tệp .env và bổ sung nó vào .gitignore sau.
D. Đặt token trong tham số URL của webhook để truyền giữa các bước.
Đáp án đúng: A

Pipeline cần chạy kiểm thử trên máy có quyền truy cập mạng nội bộ của công ty. Lựa chọn nào phù hợp?
A. Dùng webhook để gửi mã nguồn đến registry rồi chờ phản hồi.
B. Dùng self-hosted runner có đường mạng và quyền phù hợp.
C. Cho phép mỗi reviewer chạy pipeline qua tài khoản admin.
D. Bắt buộc dùng cloud runner tiêu chuẩn mà không cấu hình kết nối.
Đáp án đúng: B

Pipeline tải dependency lặp lại và cần chuyển file build sang bước tiếp theo. Cách dùng cache và artifact nào đúng?
A. Cache và artifact chỉ áp dụng cho runner, không dùng trong pipeline.
B. Cache dependency để tái sử dụng, artifact để chuyển đầu ra.
C. Cache file đầu ra và dùng secrets để lưu dependency giữa bước.
D. Artifact chỉ dùng cho biến môi trường, cache chứa trạng thái PR.
Đáp án đúng: B

Nhóm cần bước triển khai production được kích hoạt thủ công với biến riêng cho môi trường đó. Thiết kế nào phù hợp?
A. Chỉ bảo vệ nhánh main, rồi dùng chung biến giữa mọi môi trường.
B. Tạo webhook cho mỗi lần push để tự deploy mà không xác nhận.
C. Yêu cầu developer SSH thủ công và bỏ lịch sử deploy của pipeline.
D. Dùng bước deploy thủ công và deployment variables của production.
Đáp án đúng: D

Một hệ thống bên ngoài cần nhận HTTP notification khi Bitbucket có push hoặc pull request mới. Nên cấu hình gì?
A. Tạo merge check mới để tự gửi thông điệp ra hệ thống bên ngoài.
B. Tăng quyền repository token nhằm kích hoạt callback khi có push.
C. Đăng ký repository webhook cho những loại sự kiện cần nhận.
D. Đặt cache trong Bitbucket Pipelines để chia sẻ các thay đổi Git.
Đáp án đúng: C

Một công cụ tích hợp chỉ cần đọc nội dung repository qua API. Cách cấp quyền nào an toàn nhất?
A. Chia sẻ thông tin đăng nhập cá nhân của thành viên với tích hợp.
B. Dùng tài khoản quản trị workspace để bảo đảm API luôn truy cập.
C. Dùng access token có phạm vi chỉ đọc cần thiết cho repository.
D. Dùng token có quyền ghi repository để tránh lỗi thiếu quyền API.
Đáp án đúng: C

Pull request từ fork không tin cậy yêu cầu chạy mã kiểm thử trong pipeline. Biện pháp nào bảo vệ tài khoản phát hành?
A. Không cấp secret nhạy cảm cho mã chưa tin cậy và giới hạn quyền.
B. Cấp mọi deployment secret để pipeline chạy giống nhánh main.
C. Dùng cùng credential production để kiểm thử kết nối ngay từ fork.
D. Bỏ bước review vì mã đã đi qua nhánh của người đóng góp.
Đáp án đúng: A

Reviewer đã phê duyệt pull request nhưng tác giả vừa đẩy thêm commit. Quy trình nào hợp lý trước khi merge?
A. Merge trước, chỉ đánh giá commit mới trong bản phát hành kế tiếp.
B. Đóng pull request và tạo lại branch để tránh kiểm tra thay đổi.
C. Dựa hoàn toàn vào phê duyệt cũ và bỏ qua lần push cuối cùng.
D. Xem lại diff mới và xác nhận các kiểm tra liên quan đã chạy.
Đáp án đúng: D

Dịch vụ nhận webhook có thể xử lý cùng một sự kiện hai lần do hệ thống gửi lại. Thiết kế nào giảm lỗi trùng lặp?
A. Xử lý idempotent theo sự kiện và xác thực nguồn thông báo.
B. Dùng tài khoản admin Bitbucket cho mọi lời gọi từ webhook.
C. Mỗi lần nhận đều tạo bản ghi mới và bỏ qua định danh sự kiện.
D. Tắt HTTPS để tránh retry khi xác minh kết nối quá chậm.
Đáp án đúng: A

Nhóm muốn truy vết artifact triển khai về đúng mã nguồn và pipeline đã kiểm thử. Cách làm nào phù hợp?
A. Luôn lấy nhánh main mới nhất mà không lưu phiên bản build.
B. Gắn tag cho commit phát hành và ghi mã định danh artifact.
C. Tự sao chép file triển khai nhưng không giữ thông tin commit.
D. Chỉ ghi tên môi trường đích mà không giữ kết quả pipeline.
Đáp án đúng: B

Một organization GitHub có nhiều repository riêng tư và các nhóm cần mức truy cập khác nhau; cách phân quyền nào dễ quản trị theo nguyên tắc tối thiểu nhất?
A. Đặt thành viên vào team và cấp quyền phù hợp cho từng repository cần truy cập.
B. Tạo một team quyền Write trên mọi repository rồi dùng review để giới hạn sửa.
C. Phân quyền bằng nhãn của issue để thành viên chỉ xem đúng repository liên quan.
D. Dùng yêu cầu review của pull request thay cho quyền truy cập repository riêng.
Đáp án đúng: A

Một lập trình viên bên ngoài muốn đóng góp sửa lỗi cho dự án mã nguồn mở nhưng không có quyền push vào repository gốc; cách mở pull request nào đúng?
A. Tạo nhánh trong fork rồi chọn nhánh fork làm base, nhánh upstream làm head.
B. Mở pull request trong fork để GitHub tự chuyển thay đổi sang upstream.
C. Tạo nhánh trong fork làm head và chọn nhánh đích của upstream làm base.
D. Đồng bộ fork rồi chờ maintainer cherry-pick, không cần tạo pull request.
Đáp án đúng: C

Nhóm cần ngăn push trực tiếp vào main, bắt buộc review và kiểm thử trước khi merge; cấu hình GitHub nào đáp ứng đầy đủ nhất?
A. Áp dụng branch ruleset yêu cầu pull request và status checks, hạn chế push.
B. Chỉ bật yêu cầu signed commits vì chữ ký bảo đảm mọi thay đổi đã review.
C. Chỉ bật Discussions để mọi thay đổi được thông qua trước khi đẩy lên main.
D. Dùng issue labels để đánh dấu thay đổi đủ điều kiện rồi merge thủ công.
Đáp án đúng: A

Một monorepo cần bắt buộc nhóm bảo mật duyệt những thay đổi trong thư mục cấu hình nhạy cảm; cơ chế GitHub nào phù hợp?
A. Gắn label security cho pull request và yêu cầu tác giả tự mời reviewer.
B. Khai báo CODEOWNERS theo đường dẫn và bật yêu cầu duyệt của code owner.
C. Đặt tên nhánh có tiền tố security để review được áp dụng khi merge.
D. Thêm thành viên bảo mật vào repository mà không đặt quy tắc duyệt.
Đáp án đúng: B

Hai pull request đều vượt qua CI riêng nhưng có thể không tương thích khi merge nối tiếp vào main; cách kiểm tra nào giảm rủi ro này?
A. Dùng merge queue để kiểm thử thay đổi trong ngữ cảnh hợp nhất dự kiến.
B. Chỉ kiểm tra trạng thái xanh của từng nhánh trước khi bấm merge tuần tự.
C. Buộc squash merge mọi pull request để loại bỏ xung đột về hành vi.
D. Tăng số reviewer cho từng pull request và bỏ kiểm thử sau khi hợp nhất.
Đáp án đúng: A

Nhóm muốn quản lý công việc từ Issue đến pull request và quan sát tiến độ theo sprint trên GitHub; cách tổ chức nào phù hợp nhất?
A. Dùng nhãn commit làm bảng tiến độ và cập nhật bằng tag sau mỗi lần merge.
B. Ghi mỗi sprint thành GitHub Release rồi gán issue vào release theo người sửa.
C. Liên kết Issue với pull request, dùng Projects có trường trạng thái và iteration.
D. Thay Issue bằng workflow run để mọi nhiệm vụ được hiển thị theo trạng thái CI.
Đáp án đúng: C

Một pull request đã được phê duyệt, sau đó tác giả bổ sung commit thay đổi logic phân quyền; chính sách nào giúp yêu cầu review lại nội dung mới?
A. Giữ approval cũ nếu tên pull request không đổi và CI vẫn chạy thành công.
B. Chỉ bật CODEOWNERS để GitHub tự từ chối mọi commit mới của tác giả PR.
C. Bật cơ chế loại bỏ approval cũ khi có commit mới cần đánh giá lại.
D. Chuyển pull request sang draft để lịch sử review trước đó được giữ nguyên.
Đáp án đúng: C

Một pull request bị báo merge conflict vì nhánh đích đã thay đổi cùng đoạn mã; bước xử lý đáng tin cậy nào nên thực hiện?
A. Cập nhật với nhánh đích, giải quyết xung đột rồi chạy lại kiểm thử liên quan.
B. Chuyển sang squash merge vì phương thức này bỏ qua xung đột trong tệp.
C. Chạy lại CI trên commit cũ rồi merge khi mọi job báo thành công.
D. Tắt tạm required reviews để GitHub tự lựa chọn nội dung cần giữ.
Đáp án đúng: A

Một repository công cộng nhận pull request từ fork chưa tin cậy và vẫn cần chạy CI; cách giữ an toàn cho secret và workflow là gì?
A. Dùng pull_request_target, checkout code của fork rồi sử dụng secret mặc định.
B. Cấp GITHUB_TOKEN quyền ghi cho mọi pull request để CI luôn chạy đầy đủ.
C. Sao chép repository secrets sang fork để chạy bài kiểm thử tích hợp gần thực tế.
D. Chạy code chưa tin cậy bằng pull_request không cấp secret hay quyền ghi thừa.
Đáp án đúng: D

Một workflow GitHub Actions phải triển khai lên cloud mà tổ chức muốn tránh lưu khóa truy cập dài hạn; cơ chế xác thực nào phù hợp nhất?
A. Lưu khóa của tài khoản cloud ở Actions secret và xoay thủ công mỗi quý.
B. Gắn khóa cloud cố định vào self-hosted runner rồi dùng chung qua workflow.
C. Chèn access key vào artifact build đã mã hóa để job deploy giải mã khi chạy.
D. Dùng OIDC liên kết danh tính workflow để nhận thông tin xác thực ngắn hạn.
Đáp án đúng: D

Đội vận hành muốn triển khai production từ GitHub Actions nhưng bắt buộc có người phê duyệt và giới hạn secret theo môi trường; cần dùng gì?
A. Chỉ yêu cầu review ở pull request vì approval tự áp dụng cho mỗi lần deploy.
B. Cấu hình GitHub Environment có required reviewers và environment secrets.
C. Dùng label production trên Issue rồi để workflow đọc label trước khi deploy.
D. Đặt workflow_dispatch làm trigger duy nhất, không cần kiểm soát môi trường.
Đáp án đúng: B

Khi công bố một phiên bản thư viện, nhóm muốn người dùng xem ghi chú thay đổi và tải artifact nhưng vẫn xác định đúng commit gốc; nhận định nào đúng?
A. Release tự tạo nhánh phát hành riêng; Git tag chỉ lưu nội dung ghi chú thay đổi.
B. Tag dùng để kích hoạt CI; Release mới là mã định danh duy nhất của commit.
C. Git tag tham chiếu commit, còn GitHub Release gắn ghi chú và asset vào tag.
D. Release thay thế Git commit trong lịch sử, nên có thể bỏ tag của phiên bản.
Đáp án đúng: C

GitHub báo một thư viện phụ thuộc trực tiếp có CVE và đã có bản sửa; bước nào kết hợp đúng phát hiện, cập nhật và kiểm chứng?
A. Chạy secret scanning để tìm CVE rồi tăng phiên bản mà không cần CI.
B. Dùng Dependabot alert và bản cập nhật bảo mật, sau đó chạy test của dự án.
C. Chạy Code Owners review để xác định phiên bản thư viện nào đang dễ bị tấn công.
D. Đóng alert khi package còn được cache vì bản mã nguồn không bị chỉnh sửa.
Đáp án đúng: B

Một dự án GitHub công khai muốn hướng dẫn người ngoài gửi pull request và cung cấp kênh báo lỗi bảo mật không công khai; bộ tệp nào phù hợp?
A. CODE_OF_CONDUCT.md cho quy trình build và LICENSE cho báo cáo lỗ hổng.
B. CONTRIBUTING.md cho cách đóng góp và SECURITY.md cho báo cáo lỗ hổng.
C. CODEOWNERS cho hướng dẫn lập PR và CHANGELOG.md cho báo cáo lỗ hổng.
D. README.md cho phân quyền reviewer và .gitignore cho báo cáo lỗ hổng.
Đáp án đúng: B

Một dịch vụ nội bộ cần tạo issue và đọc metadata của một số repository thuộc organization mà không phụ thuộc token cá nhân dài hạn; cách nào phù hợp?
A. Dùng classic PAT của tài khoản Owner và cấp quyền repo trên toàn organization.
B. Dùng GITHUB_TOKEN của workflow bất kỳ để tự động truy cập mọi repo riêng tư.
C. Dùng deploy key dùng chung vì quyền Git của key bao gồm ghi Issue qua REST API.
D. Tạo GitHub App, giới hạn installation permissions và dùng token ngắn hạn.
Đáp án đúng: D

Sau sự cố thay đổi quy tắc bảo vệ nhánh không được phê duyệt, nhóm cần xác định ai đã sửa quyền hoặc ruleset của organization; nguồn kiểm toán nào phù hợp nhất?
A. Đọc git log của main vì mọi thay đổi cấu hình organization đều tạo commit.
B. Đọc các pull request đã merge vì cập nhật quyền luôn cần tạo pull request.
C. Xem lịch sử GitHub Actions vì mọi thao tác cấu hình đều chạy workflow.
D. Tra organization audit log và đối chiếu thời điểm thay đổi quyền, ruleset.
Đáp án đúng: D

Sáu project GitLab cần dùng chung thành viên và quyền theo phòng ban. Cách tổ chức nào hỗ trợ quản trị tập trung nhất?
A. Tạo sáu project độc lập rồi gán thành viên riêng từng nơi.
B. Dùng chung nhãn issue ở mỗi project để đồng bộ quyền truy cập.
C. Tạo một project chỉ chứa đường dẫn liên kết tới các project khác.
D. Đặt các project vào cùng group và quản lý thành viên ở group.
Đáp án đúng: D

Merge request sửa lỗi liên quan Issue #42 sẽ được nhập vào nhánh mặc định. Cách nào giúp GitLab tự đóng issue khi merge?
A. Đặt từ khóa Closes #42 trong mô tả merge request tương ứng.
B. Gắn cùng một label cho issue và merge request đang thực hiện.
C. Đặt tên nhánh nguồn là issue-42 rồi xóa mô tả merge request.
D. Đánh dấu pipeline thành công sau khi merge mà không liên kết issue.
Đáp án đúng: A

Lập trình viên muốn mở merge request sớm để nhận góp ý nhưng mã chưa đủ điều kiện merge. Trạng thái nào phù hợp?
A. Đặt MR ở trạng thái Closed, rồi khôi phục khi viết xong mã.
B. Đặt MR ở trạng thái Approved trước để reviewer dễ theo dõi.
C. Đặt MR thành Draft và chuyển sang sẵn sàng khi hoàn tất.
D. Bật tự động merge ngay dù còn các bước kiểm thử chưa chạy.
Đáp án đúng: C

Nhóm muốn cấm push trực tiếp lên main nhưng vẫn cho merge qua người có thẩm quyền. Cấu hình GitLab nào phù hợp?
A. Chỉ giới hạn quyền xóa nhánh main, còn quyền push giữ nguyên.
B. Chỉ thêm phần hướng dẫn review trong template merge request.
C. Chặn pipeline trên nhánh main, nhưng để mọi Developer push.
D. Bảo vệ nhánh main và giới hạn quyền push, merge theo vai trò.
Đáp án đúng: D

Project đã yêu cầu phê duyệt Code Owner khi sửa thư mục billing trên protected branch. Ai cần tham gia phê duyệt thay đổi?
A. Một Developer bất kỳ được assign vào issue liên kết với MR.
B. Người tạo commit mới nhất trong thư mục billing đang được sửa.
C. Người thuộc danh sách Code Owner áp dụng cho đường dẫn sửa.
D. Bất kỳ người chạy pipeline thành công của merge request đó.
Đáp án đúng: C

Một merge request đã đủ approval và pipeline xanh nhưng không thể merge vì project yêu cầu giải quyết mọi discussion. Bước nào cần làm?
A. Tạo release tag để bỏ qua điều kiện merge request hiện tại.
B. Xử lý rồi đánh dấu resolved các discussion còn đang mở.
C. Chỉ đóng issue liên kết để tự xóa tất cả discussion trong MR.
D. Chạy lại pipeline cho đến khi GitLab bỏ qua yêu cầu review.
Đáp án đúng: B

Thành viên cần push lên nhánh thông thường của project nhưng không cần quản trị quyền hay protected branch. Vai trò thấp nhất phù hợp là gì?
A. Reporter, vì có quyền đọc repository và tải mã về máy.
B. Developer, vì có quyền push vào nhánh không được bảo vệ.
C. Maintainer, vì đây là vai trò thấp nhất được phép push mã.
D. Guest, vì được thêm vào project là có quyền push branch.
Đáp án đúng: B

Project bật điều kiện Pipelines must succeed. Một MR đã được duyệt nhưng pipeline mới nhất thất bại. Kết luận nào đúng?
A. MR vẫn có thể merge vì approval thay thế mọi kiểm tra CI.
B. MR vẫn có thể merge nếu source branch không bị bảo vệ.
C. MR sẽ được merge khi issue liên quan chuyển sang Closed.
D. MR phải đáp ứng điều kiện pipeline thành công trước khi merge.
Đáp án đúng: D

Pipeline trên nhánh nguồn luôn xanh nhưng khi kết hợp với các commit mới ở nhánh đích lại phát sinh lỗi. Cần kiểm tra gì trước khi merge?
A. Chạy merged results pipeline để kiểm thử trạng thái gộp dự kiến.
B. Chỉ chạy lại pipeline push trên commit mới nhất của nhánh nguồn.
C. Chỉ kiểm tra thủ công diff trên MR trước khi cho phép merge.
D. Tạo tag release trên nhánh nguồn trước khi gộp vào main.
Đáp án đúng: A

Một MR từ fork không tin cậy được đề nghị chạy pipeline trong project cha đang có token CI. Rủi ro quan trọng nhất là gì?
A. Mã fork chỉ sử dụng runner riêng và không thể chạy tại project cha.
B. Job từ fork sẽ tự được GitLab kiểm chứng là mã đã phê duyệt.
C. Chạy ở project cha chỉ thay đổi cache, không đổi phạm vi quyền.
D. Mã chưa tin cậy có thể chạy trong ngữ cảnh quyền của project cha.
Đáp án đúng: D

Một CI variable được đánh dấu protected và không xuất hiện khi pipeline chạy từ nhánh không được bảo vệ. Vì sao?
A. Biến protected chỉ hoạt động với pipeline theo lịch đã đặt.
B. Biến protected cần được khai báo lại trong mọi job chạy thử.
C. Biến protected không cấp cho pipeline từ ref không bảo vệ.
D. Biến protected chỉ được tải sau khi tất cả test đã thành công.
Đáp án đúng: C

Nhánh nguồn của MR có xung đột với nhánh đích sau nhiều commit mới. Thao tác nào giúp giải quyết xung đột trước khi merge?
A. Cập nhật nhánh nguồn theo nhánh đích rồi xử lý phần conflict.
B. Khởi chạy lại pipeline để GitLab tự chọn phiên bản các tệp.
C. Đổi nhãn của MR để GitLab bỏ qua các xung đột khi gộp mã.
D. Chỉ đóng issue liên kết để kích hoạt tính năng tự xử lý conflict.
Đáp án đúng: A

Nhóm muốn lịch sử nhánh đích chỉ nhận một commit tổng hợp từ MR nhưng vẫn giữ trao đổi review trong GitLab. Tính năng nào phù hợp?
A. Chọn Rebase, vì thao tác này gom toàn bộ commit thành một.
B. Chọn Fast-forward, vì nó xóa các commit nguồn trước khi merge.
C. Chọn Squash, vì có thể gộp các commit mà vẫn giữ lịch sử MR.
D. Chọn Cherry-pick, vì mọi bình luận review được chép vào commit.
Đáp án đúng: C

Một hệ thống tài liệu chỉ cần clone repository GitLab riêng tư, không push hay gọi API. Cách cấp quyền nào sát nguyên tắc tối thiểu?
A. Dùng personal access token có scope api của một Maintainer.
B. Dùng deploy token chỉ có quyền read_repository cần thiết.
C. Dùng project access token có quyền ghi repository để dễ mở rộng.
D. Dùng group token với quyền quản trị nhiều project trong group.
Đáp án đúng: B

Project thiết lập xóa các approval cũ khi MR được push thêm commit. Sau khi tác giả cập nhật mã, trạng thái review nên được hiểu thế nào?
A. Thay đổi mới cần được phê duyệt lại theo quy tắc đã cấu hình.
B. Approval vẫn có hiệu lực vì chỉ có phần diff mới được cập nhật.
C. Pipeline xanh có thể tự thay thế tất cả phê duyệt đã bị hủy.
D. Đổi tên source branch sẽ tự khôi phục các phê duyệt trước đó.
Đáp án đúng: A

Nhóm muốn theo dõi Issue qua các bước Ready, Doing và Review trên bảng GitLab, thay vì tạo một MR cho từng trạng thái. Cách nào phù hợp?
A. Dùng protected branch theo từng trạng thái và gán issue vào nhánh.
B. Dùng issue board với các danh sách dựa trên label phù hợp.
C. Dùng approval rule theo từng bước để di chuyển issue trên bảng.
D. Dùng pipeline stage Ready, Doing, Review để tự phân loại issue.
Đáp án đúng: B

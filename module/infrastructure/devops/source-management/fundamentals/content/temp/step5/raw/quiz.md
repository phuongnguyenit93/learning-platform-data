Câu 1: Kỹ sư đã sửa src/api.go và README.md (đều được theo dõi), nhưng commit kế tiếp chỉ được chứa phần thay đổi API. Thao tác nào phù hợp?
A. Chạy git commit -am 'api' để chỉ commit thay đổi của src/api.go.
B. Chạy git add src/api.go rồi git commit để lưu phần đã stage.
C. Chạy git add -A rồi git commit để tự loại thay đổi README.md.
D. Chạy git push origin main để chỉ commit thay đổi của src/api.go.
Đáp án đúng: B

Câu 2: Tệp .env đã được Git theo dõi; nhóm muốn ngừng theo dõi nó từ commit sau nhưng vẫn giữ tệp trên máy, chưa xử lý lịch sử cũ. Nên làm gì?
A. Chỉ thêm .env vào .gitignore rồi commit để Git tự bỏ theo dõi.
B. Chạy git rm --cached .env, thêm vào .gitignore rồi commit.
C. Chạy git rm .env rồi commit để tệp tiếp tục nằm trên máy.
D. Chạy git reset --hard HEAD rồi thêm tệp vào .gitignore.
Đáp án đúng: B

Câu 3: Commit mới nhất chưa được push đang thiếu tệp vừa được stage; muốn bổ sung tệp nhưng giữ nguyên commit message. Lệnh nào phù hợp?
A. Chạy git commit để tạo commit khác với phần vừa stage.
B. Chạy git reset --hard HEAD để thêm các tệp đã stage.
C. Chạy git cherry-pick HEAD để cập nhật commit cuối cùng.
D. Chạy git commit --amend --no-edit để sửa commit mới nhất.
Đáp án đúng: D

Câu 4: Từ nhánh main hiện tại, nhóm cần tạo nhánh feature/cart và chuyển ngay sang nhánh đó. Lệnh nào đáp ứng?
A. Chạy git switch -c feature/cart để tạo và chuyển nhánh.
B. Chạy git branch feature/cart để tạo rồi tự chuyển nhánh.
C. Chạy git switch feature/cart dù nhánh đó chưa tồn tại.
D. Chạy git checkout -- feature/cart để tạo nhánh mới.
Đáp án đúng: A

Câu 5: Nhánh main hiện là tổ tiên của feature/cart; khi tích hợp, nhóm chỉ cho phép fast-forward và không muốn merge commit. Lệnh nào đúng khi đang ở main?
A. Chạy git merge --no-ff feature/cart để giữ lịch sử tách nhánh.
B. Chạy git cherry-pick feature/cart để lấy toàn bộ lịch sử nhánh feature.
C. Chạy git merge --ff-only feature/cart để chỉ chấp nhận fast-forward.
D. Chạy git merge --squash feature/cart để tạo fast-forward.
Đáp án đúng: C

Câu 6: Lệnh git merge đang dừng vì hai nhánh sửa cùng đoạn cấu hình. Sau khi sửa tệp để giữ cả hai thay đổi, cần làm gì để hoàn tất merge?
A. Chạy git merge --abort để lưu kết quả đã giải quyết xung đột.
B. Chạy git checkout --ours rồi commit để nhận cả hai phía.
C. Chạy git checkout --theirs rồi commit để nhận cả hai phía.
D. Chạy git add các tệp đã sửa rồi git merge --continue.
Đáp án đúng: D

Câu 7: Trước khi tích hợp code của đồng đội, kỹ sư muốn cập nhật remote-tracking refs từ origin nhưng chưa thay đổi nhánh đang checkout. Lệnh nào phù hợp?
A. Chạy git fetch origin để tải ref và commit từ remote.
B. Chạy git pull origin main để tích hợp main vào nhánh hiện tại.
C. Chạy git reset --hard origin/main để đồng bộ cả working tree.
D. Chạy git switch --detach origin/main để đổi trạng thái checkout.
Đáp án đúng: A

Câu 8: Lần đầu đẩy nhánh local feature/report lên origin, kỹ sư muốn thiết lập luôn upstream để những lần sau chỉ cần git push. Lệnh nào đúng?
A. Chạy git fetch origin feature/report rồi gọi git push.
B. Chạy git push origin feature/report nhưng không đặt upstream.
C. Chạy git branch -u origin/main feature/report để gắn upstream.
D. Chạy git push -u origin feature/report để đặt upstream.
Đáp án đúng: D

Câu 9: Kỹ sư đang ở nhánh feature với các commit chưa chia sẻ, muốn đặt chúng lên đỉnh origin/main mới nhất mà không tạo merge commit. Quy trình nào đúng?
A. Chạy git fetch origin rồi git merge origin/main vào feature.
B. Chạy git reset --hard origin/main để loại các commit local.
C. Chạy git fetch origin rồi git rebase origin/main trên feature.
D. Chạy git push --force origin main để lấy nhánh mới nhất.
Đáp án đúng: C

Câu 10: Bản release/1.8 cần đúng một commit sửa lỗi từ main, không lấy các thay đổi main khác. Khi đã checkout release/1.8, nên dùng lệnh nào?
A. Chạy git merge main để mang cả lịch sử của main vào nhánh release.
B. Chạy git cherry-pick <sha> để áp dụng đúng commit được chọn.
C. Chạy git revert <sha> để áp dụng bản sửa từ nhánh main.
D. Chạy git reset --hard <sha> để nhập duy nhất bản sửa lỗi.
Đáp án đúng: B

Câu 11: Một commit lỗi đã được push lên nhánh main dùng chung; cần hoàn tác thay đổi mà không viết lại lịch sử của đồng đội. Cách nào an toàn?
A. Dùng git revert <sha> để tạo commit đảo ngược thay đổi.
B. Dùng git reset --hard HEAD~1 rồi force push nhánh main.
C. Dùng git rebase -i để xóa commit lỗi trên lịch sử đã chia sẻ.
D. Dùng git push --force để thay thế lịch sử của nhánh main.
Đáp án đúng: A

Câu 12: Sau git reset --hard HEAD~1, commit trước đó không còn được nhánh tham chiếu; repository chưa chạy garbage collection. Cách tìm và giữ lại commit?
A. Xem git log trên nhánh hiện tại rồi tự tạo lại nội dung commit.
B. Dùng git reflog tìm SHA cũ rồi tạo nhánh trỏ đến commit.
C. Dùng git clean -fd để khôi phục commit đã mất khỏi HEAD.
D. Dùng git fetch origin để phục hồi mọi commit chỉ tồn tại local.
Đáp án đúng: B

Câu 13: Repository yêu cầu mọi thay đổi vào main phải được review và vượt qua kiểm thử CI trước khi merge pull request. Thiết lập nào đáp ứng đầy đủ?
A. Bật branch protection/ruleset yêu cầu review và status checks.
B. Thêm CODEOWNERS nhưng không bật yêu cầu phê duyệt bắt buộc từ reviewer.
C. Chỉ yêu cầu status checks, cho phép merge không được review.
D. Chỉ yêu cầu một approval, không bắt buộc CI chạy thành công.
Đáp án đúng: A

Câu 14: Bản phát hành v2.4.0 cần gắn một annotated tag có thông điệp lên đúng commit SHA đã kiểm thử. Lệnh nào tạo loại tag đó?
A. Chạy git branch v2.4.0 <sha> để đánh dấu bản phát hành.
B. Chạy git tag v2.4.0 <sha> để lưu annotated tag có thông điệp.
C. Chạy git tag -a v2.4.0 <sha> -m 'release' để tạo annotated tag.
D. Chạy git tag -f v2.4.0 <sha> để tạo tag có thông điệp.
Đáp án đúng: C

Câu 15: Trong khoảng 80 commit, một thay đổi làm kiểm thử thất bại; nhóm có script trả về thành công khi commit tốt. Công cụ nào giúp khoanh vùng theo tìm kiếm nhị phân?
A. Dùng git blame trên file nghi ngờ để chạy lại mọi commit.
B. Dùng git log --grep để tự động kiểm thử từng commit.
C. Dùng git diff --stat để kiểm thử mọi commit trong phạm vi.
D. Dùng git bisect với mốc good/bad và git bisect run script.
Đáp án đúng: D

Câu 16: CI tạo image production; nhánh và tag có thể bị di chuyển về sau. Muốn truy vết image về đúng mã nguồn đã build, cần lưu gì?
A. Chỉ lưu tên nhánh main trong metadata của image phát hành.
B. Chỉ lưu thời điểm build và tên pipeline trong log triển khai của image.
C. Lưu full commit SHA cùng metadata build cho image đã phát hành.
D. Chỉ lưu tag latest để tìm phiên bản đang chạy trên cluster.
Đáp án đúng: C

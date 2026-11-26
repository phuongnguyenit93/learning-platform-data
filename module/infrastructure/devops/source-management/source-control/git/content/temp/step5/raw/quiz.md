Câu 1: Đã chạy git add cho App.java, sau đó sửa tiếp mà chưa stage lại. Muốn xem riêng phần đã stage so với HEAD, lệnh nào đúng?
A. git diff -- App.java
B. git show HEAD:App.java
C. git diff --cached -- App.java
D. git log -p -- App.java
Đáp án đúng: C

Câu 2: File Cart.java có ba hunk sửa đổi nhưng chỉ một hunk đã sẵn sàng commit. Lệnh nào cho phép chọn từng hunk để stage?
A. git add -- Cart.java
B. git add -p -- Cart.java
C. git commit -am "Cart"
D. git restore --staged Cart.java
Đáp án đúng: B

Câu 3: Đã git add App.java, rồi chỉnh sửa tiếp trong working tree nhưng chưa add lại. Khi chạy git commit, phiên bản nào được ghi vào commit?
A. Phiên bản trong index tại lần git add gần nhất.
B. Mọi sửa đổi đang nằm trong working tree hiện tại.
C. Phiên bản App.java đang ở remote origin/main.
D. Phiên bản App.java của lần build gần đây nhất.
Đáp án đúng: A

Câu 4: Đã stage nhầm config.yml, vẫn muốn giữ mọi thay đổi của nó trong working tree nhưng bỏ khỏi staging area. Lệnh nào phù hợp?
A. git restore --staged -- config.yml
B. git restore -- config.yml
C. git reset --hard HEAD~0
D. git clean -fd -- config.yml
Đáp án đúng: A

Câu 5: App.java đã stage một phần rồi được sửa thêm. Muốn hủy các sửa đổi chưa stage mà giữ nguyên nội dung trong index, nên làm gì?
A. Bỏ stage file bằng git restore --staged.
B. Cất thay đổi file bằng git stash push.
C. Reset mọi thay đổi về HEAD bằng git reset --hard.
D. Khôi phục worktree bằng git restore App.java.
Đáp án đúng: D

Câu 6: Đang ở nhánh main và muốn tạo nhánh feature/search từ HEAD hiện tại, đồng thời chuyển sang nhánh mới. Lệnh nào phù hợp?
A. git branch feature/search
B. git switch feature/search
C. git switch -c feature/search
D. git checkout -b feature/search HEAD~1
Đáp án đúng: C

Câu 7: Nhánh main chưa có commit mới kể từ khi tách feature, và feature đã tiến xa hơn. Git merge feature mặc định trên main có thể làm gì?
A. Tạo merge commit mới dù lịch sử chưa phân kỳ.
B. Dời main tới tip feature, không tạo merge commit.
C. Viết lại commit hash của mọi commit trên feature.
D. Xóa nhánh feature ngay sau khi hợp nhất thành công.
Đáp án đúng: B

Câu 8: Git merge báo conflict trong service.java; lập trình viên đã sửa file và kiểm thử xong. Bước nào hoàn tất merge đang dở?
A. Chạy git merge --abort để rời trạng thái merge.
B. Chạy git restore --ours để lấy một phía sửa đổi.
C. Chạy git rebase --continue để tiếp tục lịch sử.
D. Chạy git add rồi git merge --continue.
Đáp án đúng: D

Câu 9: Một nhánh đã push và đồng nghiệp đã dựa vào các commit của nó. Vì sao cần thận trọng khi rebase rồi force-push nhánh này?
A. Rebase luôn tự đổi HEAD của nhánh main trên remote.
B. Rebase đổi commit ID, làm lệch lịch sử chung.
C. Rebase tự xóa toàn bộ tag liên quan ở remote.
D. Rebase buộc mọi commit thành duy nhất một commit.
Đáp án đúng: B

Câu 10: Nhánh feature/cart mới chỉ có ở local. Muốn push lên origin và cấu hình upstream để lần sau chỉ cần git push, chọn lệnh nào?
A. git push -u origin feature/cart
B. git fetch origin feature/cart
C. git switch -c origin/feature/cart
D. git pull origin feature/cart
Đáp án đúng: A

Câu 11: Muốn cập nhật origin/main từ remote nhưng chưa merge hoặc rebase vào nhánh local đang checkout. Lệnh nào phù hợp?
A. git pull origin main
B. git merge origin/main
C. git fetch origin
D. git rebase origin/main
Đáp án đúng: C

Câu 12: Commit sai đã được đẩy lên main và nhiều người đang dùng nhánh đó. Cách nào đảo thay đổi mà vẫn giữ lịch sử commit công khai?
A. git reset --hard HEAD~1
B. git commit --amend
C. git revert <sha>
D. git rebase -i HEAD~3
Đáp án đúng: C

Câu 13: Sau git reset --hard, HEAD không còn trỏ tới commit chứa công việc cũ. Commit chưa bị dọn rác; nên tra cứu đâu để tìm lại mốc HEAD?
A. Dùng git log --all xem các nhánh hiện còn.
B. Dùng git blame để xem nguồn từng dòng mã.
C. Dùng git diff để đối chiếu hai commit.
D. Dùng git reflog tìm mốc HEAD cũ.
Đáp án đúng: D

Câu 14: Một lỗi xuất hiện giữa phiên bản tốt và phiên bản xấu, có hơn 100 commit ở giữa. Cách nào tìm commit đầu tiên gây lỗi hiệu quả?
A. Dùng git bisect để khoanh vùng commit lỗi.
B. Dùng git blame để xem tác giả từng dòng mã.
C. Dùng git show để đọc thay đổi của HEAD.
D. Dùng git tag để đánh dấu các commit tốt.
Đáp án đúng: A

Câu 15: Muốn biết commit và tác giả đã ghi các dòng 20–40 của file Parser.java hiện tại. Lệnh nào đúng với mục tiêu này?
A. git log --stat -- Parser.java
B. git show --format=fuller HEAD
C. git diff HEAD~1 HEAD -- Parser.java
D. git blame -L 20,40 -- Parser.java
Đáp án đúng: D

Câu 16: Bản phát hành v2.4.0 cần tag có message, người tạo và ngày tạo gắn vào commit HEAD hiện tại. Nên dùng lệnh nào?
A. git tag v2.4.0 trên HEAD hiện tại.
B. git tag -a v2.4.0 -m "Release"
C. git branch release/v2.4.0 tại HEAD.
D. git stash push -m "Release 2.4.0"
Đáp án đúng: B

# Vòng đời tệp: untracked, tracked, modified, staged và committed

Git không theo dõi tệp theo cách một trình quản lý tệp thông thường theo dõi thư mục trên đĩa. Git lưu các snapshot nội dung trong commit và dùng index (staging area) để chuẩn bị snapshot tiếp theo. Working tree là các tệp bạn đang nhìn thấy và chỉnh sửa trên máy.

Vì vậy, một tệp có thể chuyển qua nhiều trạng thái trong quá trình làm việc: mới tạo (untracked), được Git theo dõi (tracked), có nội dung thay đổi (modified), được chọn vào lần commit tiếp theo (staged), rồi được ghi vào commit (committed). Các nhãn này mô tả những khía cạnh khác nhau: tracked không đồng nghĩa với clean, và một tệp đã staged vẫn có thể tiếp tục bị modified nếu bạn sửa nó lần nữa.

Bài học này giải thích mối quan hệ giữa HEAD, index và working tree, cách đọc trạng thái tệp bằng git status, cách chuyển tệp qua từng giai đoạn bằng add/commit/restore/rm/mv, và cách tránh đưa nhầm nội dung vào commit.

## 1. Ba nơi quyết định trạng thái của tệp

### 1.1. HEAD — snapshot đã commit gần nhất

HEAD thường trỏ đến commit hiện tại của nhánh đang checkout. Cây tệp của commit đó là mốc Git dùng để so sánh trạng thái mới.

Kiểm tra HEAD:

~~~bash
git log -1 --oneline
git show --stat --oneline HEAD
~~~

Nếu đang ở trạng thái detached HEAD, HEAD trỏ trực tiếp đến một commit thay vì thông qua nhánh local. Khái niệm snapshot vẫn giống nhau: HEAD xác định commit hiện tại.

### 1.2. Index — snapshot chuẩn bị cho commit tiếp theo

Index còn được gọi là staging area. Khi chạy git add, Git cập nhật index với nội dung mà bạn chọn để đưa vào commit tiếp theo.

Kiểm tra thay đổi đã stage:

~~~bash
git diff --cached
~~~

Index không phải một bản sao đầy đủ của thư mục làm việc. Nó là cấu trúc Git dùng để ghi nhận snapshot dự kiến. Một tệp có thể được stage ở một phiên bản, rồi tiếp tục được sửa trên đĩa thành phiên bản khác.

### 1.3. Working tree — tệp trên đĩa

Working tree là các tệp và thư mục trong dự án mà bạn mở bằng editor hoặc công cụ dòng lệnh. Khi chỉnh sửa và lưu tệp, nội dung working tree thay đổi.

Xem thay đổi chưa stage so với index:

~~~bash
git diff
~~~

Git so sánh ba nơi để biết nội dung nào đã commit, nội dung nào đã chọn cho commit tiếp theo và nội dung nào vẫn chỉ nằm trên đĩa.

### 1.4. Mô hình ba lớp

~~~text
             git commit
HEAD  <------------------  Index
 |                           ^
 |                           |
 |                       git add
 |                           |
 +----------------------- Working tree
       so sánh trạng thái
~~~

Có thể hiểu các phép so sánh:

| Lệnh | So sánh | Ý nghĩa |
| --- | --- | --- |
| git diff | Working tree với index | Thay đổi chưa stage |
| git diff --cached | Index với HEAD | Thay đổi đã stage |
| git diff HEAD | Working tree với HEAD | Tổng thay đổi so với commit hiện tại |
| git status | HEAD, index và working tree | Tóm tắt trạng thái repository |

Nếu working tree và index giống nhau, git diff không hiển thị thay đổi. Nếu index và HEAD giống nhau, git diff --cached không hiển thị thay đổi staged.

## 2. Untracked — tệp mới chưa được Git theo dõi

### 2.1. Untracked là gì?

Một tệp là untracked khi nó chưa được Git ghi nhận trong index hoặc commit và không bị quy tắc ignore loại khỏi báo cáo trạng thái.

Ví dụ, bạn tạo tệp:

~~~bash
printf "Hello Git\n" > notes.txt
~~~

Kiểm tra:

~~~bash
git status
~~~

Git có thể hiển thị:

~~~text
Untracked files:
  notes.txt
~~~

Tệp tồn tại trên đĩa nhưng chưa thuộc snapshot mà Git chuẩn bị commit. Nếu commit ngay mà không thêm tệp vào index, notes.txt sẽ không được đưa vào commit.

### 2.2. Liệt kê tệp untracked

~~~bash
git ls-files --others --exclude-standard
~~~

Lệnh liệt kê các tệp không được index theo dõi và loại các đường dẫn bị ignore theo quy tắc thông thường.

Để xem trạng thái dạng ngắn:

~~~bash
git status --short
~~~

Ví dụ:

~~~text
?? notes.txt
~~~

Hai dấu hỏi cho biết đường dẫn chưa được theo dõi.

### 2.3. Chuyển untracked thành tracked bằng git add

Để stage một tệp mới:

~~~bash
git add notes.txt
~~~

Kiểm tra:

~~~bash
git status
git diff --cached
~~~

Tệp đã được đưa vào index và sẽ trở thành một phần của snapshot tiếp theo nếu bạn commit. Sau khi được thêm vào index, Git bắt đầu theo dõi đường dẫn đó.

Lưu ý: git add không tạo commit. Nó chỉ cập nhật index.

### 2.4. Untracked và ignored khác nhau

Tệp untracked có thể xuất hiện trong git status. Tệp ignored bị quy tắc ignore loại khỏi danh sách thông thường.

Ví dụ, file .env có thể được thêm vào .gitignore:

~~~gitignore
.env
*.log
build/
~~~

Sau đó, Git không còn liệt kê các đường dẫn khớp pattern như untracked trong trạng thái thông thường.

Kiểm tra quy tắc nào đang ignore một đường dẫn:

~~~bash
git check-ignore -v .env
~~~

Nếu một tệp bị ignore nhưng bạn thực sự muốn thêm nó, có thể dùng git add -f. Chỉ làm vậy khi đã xác nhận tệp không chứa bí mật, dữ liệu sinh tự động hoặc nội dung không nên commit.

### 2.5. Thư mục rỗng không được Git theo dõi

Git lưu file và các đối tượng cây thư mục, nhưng không lưu thư mục rỗng như một đối tượng độc lập. Nếu cần giữ một thư mục chưa có nội dung, nhóm thường đặt một tệp có mục đích rõ ràng như .gitkeep.

.gitkeep chỉ là quy ước tên tệp, không phải tính năng đặc biệt của Git.

## 3. Tracked — tệp đã được Git theo dõi

### 3.1. Tracked không có nghĩa là không thay đổi

Một đường dẫn tracked là đường dẫn Git đã biết thông qua commit hoặc index. Tệp tracked có thể đang clean, modified, staged, staged và modified, hoặc đã bị xóa khỏi working tree.

Ví dụ:

- README.md đã được commit ở HEAD: tracked.
- Bạn sửa README.md nhưng chưa stage: vẫn tracked, trạng thái modified.
- Bạn chạy git add README.md: vẫn tracked, có thay đổi staged.
- Bạn commit: nội dung mới trở thành một phần của HEAD.

Tracked mô tả quan hệ của đường dẫn với repository, không phải trạng thái nội dung hiện tại.

### 3.2. Xem các tệp tracked

~~~bash
git ls-files
~~~

Lệnh hiển thị các đường dẫn trong index. Trong trạng thái thông thường, đây là danh sách các tệp Git đang theo dõi và đã được đưa vào index.

Có thể lọc theo thư mục:

~~~bash
git ls-files -- src/
~~~

Lưu ý: trong lúc merge conflict, index có thể chứa các stage chưa hợp nhất. Khi đó, git ls-files --stage hoặc git ls-files -u giúp xem cấu trúc chi tiết hơn.

### 3.3. Trạng thái clean

Một tệp tracked ở trạng thái clean khi nội dung và metadata được Git theo dõi trong working tree khớp với index, đồng thời index khớp với HEAD cho đường dẫn đó.

Nếu repository không có thay đổi nào, git status thường báo:

~~~text
On branch main
nothing to commit, working tree clean
~~~

Clean là trạng thái so sánh tại thời điểm kiểm tra. Nếu bạn sửa tệp sau đó, nó chuyển sang modified.

## 4. Modified — tệp tracked đã thay đổi

### 4.1. Sửa tệp nhưng chưa stage

Giả sử README.md đã được commit. Bạn mở file và thay một dòng, sau đó lưu lại.

Kiểm tra:

~~~bash
git status
git diff -- README.md
~~~

Git báo README.md đã modified trong working tree. Nội dung mới chưa được đưa vào index, nên commit tiếp theo chưa bao gồm thay đổi đó.

### 4.2. Stage một phiên bản rồi tiếp tục sửa

Đây là tình huống quan trọng:

~~~bash
git add README.md
~~~

Tại thời điểm này, phiên bản hiện tại của README.md được lưu trong index. Sau đó bạn sửa file lần nữa và lưu.

Bây giờ có hai phiên bản khác nhau:

- Index: phiên bản đã stage.
- Working tree: phiên bản mới hơn, chưa stage.

Kiểm tra:

~~~bash
git status
git diff --cached -- README.md
git diff -- README.md
~~~

Git có thể hiển thị cùng một đường dẫn trong cả nhóm staged và nhóm unstaged. Điều đó không phải lỗi. Bạn đã chọn một phiên bản cho commit, rồi tiếp tục sửa tệp sau lần stage đó.

### 4.3. Stage lại phiên bản mới nhất

Nếu muốn đưa toàn bộ nội dung hiện tại vào commit tiếp theo:

~~~bash
git add README.md
~~~

Lệnh cập nhật entry trong index bằng nội dung working tree mới nhất. Sau đó:

~~~bash
git diff --cached -- README.md
git diff -- README.md
~~~

Nếu không còn chỉnh sửa sau lần add cuối, git diff sẽ trống cho tệp đó.

### 4.4. Modified không nhất thiết chỉ là nội dung văn bản

Git có thể nhận diện thay đổi ở:

- Nội dung file.
- Bit executable của file.
- Đường dẫn do rename hoặc delete.
- Symbolic link.
- Một số metadata liên quan đến kiểu đối tượng.

Vì vậy, khi git status báo modified, hãy xem diff hoặc thông tin mode nếu nội dung văn bản không có khác biệt rõ ràng.

## 5. Staged — thay đổi đã được chọn cho commit

### 5.1. Staging có ý nghĩa gì?

Staged nghĩa là thay đổi đã được ghi vào index. Nó là ứng viên cho snapshot của commit kế tiếp.

Lệnh stage phổ biến:

~~~bash
git add README.md
~~~

Kiểm tra nội dung staged:

~~~bash
git diff --cached
~~~

Chỉ các thay đổi trong index mới được đưa vào commit thông thường. Những thay đổi khác đang nằm trong working tree sẽ tiếp tục ở trạng thái unstaged.

### 5.2. Stage file mới, file đã sửa và file đã xóa

Các cách dùng thường gặp:

~~~bash
git add new-file.txt
git add src/PaymentService.java
git add -A
~~~

- git add file: stage đường dẫn cụ thể, bao gồm nội dung mới hoặc đã sửa.
- git add -A: cập nhật index cho mọi thay đổi trong working tree, gồm thêm, sửa và xóa. Nếu có pathspec, chỉ cập nhật trong phạm vi pathspec đó.
- git add -u: stage thay đổi của các đường dẫn đã được theo dõi, gồm sửa và xóa; không thêm tệp untracked mới. Nếu có pathspec, chỉ áp dụng trong phạm vi được chỉ định.

Nếu muốn giới hạn trong một thư mục:

~~~bash
git add -A -- src/
~~~

Khi chạy các lệnh này không kèm pathspec, Git cập nhật toàn bộ working tree. Hãy dùng pathspec như src/ nếu chỉ muốn stage một phần repository.

### 5.3. Stage từng phần bằng git add -p

Khi chỉ muốn đưa một số hunk vào commit:

~~~bash
git add -p
~~~

Git lần lượt hiển thị các phần thay đổi và hỏi có stage từng phần hay không. Các lựa chọn thường gặp:

- y: stage hunk hiện tại.
- n: bỏ qua hunk hiện tại.
- s: chia nhỏ hunk nếu có thể.
- e: chỉnh sửa patch.
- q: thoát.

Sau đó xem lại:

~~~bash
git diff --cached
git diff
~~~

Cách này hữu ích khi một tệp chứa cả thay đổi thuộc nhiều mục công việc.

### 5.4. Stage không khóa nội dung tệp

Index giữ snapshot đã stage, không khóa file trên đĩa. Bạn vẫn có thể tiếp tục sửa tệp, và phần sửa mới sẽ là unstaged.

Đây là lý do cần kiểm tra cả git diff --cached và git diff trước khi commit.

## 6. Committed — snapshot đã được ghi vào lịch sử

### 6.1. Commit chuyển index thành lịch sử

Khi chạy:

~~~bash
git commit -m "Update project documentation"
~~~

Git tạo commit từ nội dung index hiện tại. Commit tham chiếu đến một tree object mô tả snapshot; nó cũng chứa thông tin parent, author, committer và message.

Sau commit, các thay đổi đã commit trở thành một phần của HEAD. Nếu working tree không còn sửa đổi khác, repository sẽ trở lại trạng thái clean.

### 6.2. Kiểm tra nội dung commit

~~~bash
git show --stat --oneline HEAD
git show --format=fuller HEAD
git log -1 --oneline
~~~

Để xem một tệp trong commit:

~~~bash
git show HEAD:README.md
~~~

Lệnh này hiển thị phiên bản README.md được lưu trong commit HEAD, không phải nội dung working tree chưa commit.

### 6.3. Commit chỉ lấy nội dung staged

Ví dụ:

1. Bạn sửa A.java và B.java.
2. Chỉ chạy git add A.java.
3. Chạy git commit.

Commit chỉ chứa thay đổi đã stage của A.java. Thay đổi trong B.java vẫn ở working tree và tiếp tục được báo modified.

Kiểm tra trước khi commit:

~~~bash
git diff --cached --name-status
git diff --cached
git status
~~~

Đừng chỉ nhìn danh sách file trên đĩa để suy đoán commit sẽ chứa gì; hãy kiểm tra index.

### 6.4. Tùy chọn git commit -a

Có thể dùng:

~~~bash
git commit -am "Update tracked files"
~~~

Tùy chọn -a yêu cầu Git tự stage thay đổi và xóa của các tệp đã được theo dõi trước khi commit. Nó không tự thêm các tệp untracked mới.

Nếu vừa tạo file mới, bạn vẫn cần git add file đó trước khi commit.

### 6.5. Sửa commit gần nhất bằng --amend

Nếu vừa commit và muốn bổ sung thay đổi:

~~~bash
git add README.md
git commit --amend
~~~

Lệnh tạo lại commit cuối cùng với nội dung index mới và thông tin commit được chỉnh sửa. Commit ID sẽ thay đổi.

Chỉ dùng khi hiểu tác động lên lịch sử. Nếu commit đã được push và người khác dựa vào nó, amend có thể buộc nhóm phải xử lý lịch sử đã viết lại.

## 7. Chuyển đổi giữa các trạng thái bằng lệnh Git

### 7.1. Unstage một tệp nhưng giữ nội dung working tree

Nếu đã stage nhầm:

~~~bash
git restore --staged README.md
~~~

Lệnh đưa nội dung index của đường dẫn về trạng thái trong HEAD, nhưng giữ nội dung working tree. Nếu tệp mới chưa từng được commit, lệnh bỏ entry staged khỏi index và file vẫn nằm trên đĩa như untracked.

Kiểm tra:

~~~bash
git status
~~~

Trong Git cũ hơn, có thể gặp cách viết:

~~~bash
git reset HEAD -- README.md
~~~

Đây là cách bỏ staging một đường dẫn mà không xóa thay đổi working tree.

### 7.2. Bỏ thay đổi working tree chưa stage

Nếu muốn khôi phục tệp tracked từ index và loại bỏ phần chỉnh sửa chưa stage:

~~~bash
git restore README.md
~~~

Lệnh này có thể ghi đè nội dung local chưa stage. Hãy kiểm tra hoặc sao lưu phần cần giữ trước khi chạy.

Nếu file đã có thay đổi staged và bạn chạy restore không có --staged, Git khôi phục working tree theo index; phần staged vẫn được giữ.

### 7.3. Khôi phục cả index và working tree về HEAD

Nếu muốn loại bỏ cả staged và unstaged changes của một tệp tracked:

~~~bash
git restore --source=HEAD --staged --worktree -- README.md
~~~

Lệnh cập nhật cả index và working tree từ HEAD. Nó có thể làm mất toàn bộ thay đổi chưa commit của đường dẫn đó.

Chỉ chạy khi đã xác nhận đúng file và không cần giữ các thay đổi hiện tại.

### 7.4. Xóa file tracked

Để xóa một file và stage việc xóa:

~~~bash
git rm -- old-file.txt
~~~

Sau đó kiểm tra:

~~~bash
git status
git diff --cached
~~~

Khi commit, snapshot mới sẽ không còn đường dẫn đó. Commit cũ vẫn giữ nội dung của file trong lịch sử.

### 7.5. Ngừng theo dõi file nhưng giữ trên đĩa

Nếu muốn giữ file local nhưng xóa khỏi index và các commit tiếp theo:

~~~bash
git rm --cached -- .env
~~~

Thường kết hợp với .gitignore:

~~~gitignore
.env
~~~

Sau đó:

~~~bash
git add .gitignore
git commit -m "Stop tracking local environment file"
~~~

Lưu ý: nếu .env từng chứa secret đã commit, việc ngừng theo dõi không xóa bí mật khỏi lịch sử. Hãy thu hồi credential trước khi làm sạch lịch sử theo quy trình bảo mật.

### 7.6. Đổi tên file bằng git mv

~~~bash
git mv old-name.txt new-name.txt
~~~

Lệnh di chuyển file và cập nhật index. Git không lưu một loại đối tượng rename riêng; khi xem diff, Git suy luận rename dựa trên nội dung và đường dẫn giữa hai snapshot.

Có thể kiểm tra:

~~~bash
git status --short
git diff --cached --summary
~~~

Nếu đổi tên thủ công bằng trình quản lý tệp, Git vẫn có thể nhận diện rename khi so sánh nội dung, nhưng git mv làm thao tác cập nhật working tree và index rõ ràng hơn.

## 8. Đọc trạng thái bằng git status

### 8.1. Dạng đầy đủ

~~~bash
git status
~~~

Git thường chia đầu ra thành:

- Changes to be committed: thay đổi đã stage.
- Changes not staged for commit: thay đổi tracked nhưng chưa stage.
- Untracked files: tệp mới chưa được theo dõi.

Một tệp có thể xuất hiện ở cả nhóm staged và unstaged nếu bạn sửa nó sau khi stage.

### 8.2. Dạng ngắn

~~~bash
git status --short
~~~

Ví dụ:

~~~text
 M README.md
M  src/App.java
MM config/app.yml
A  notes.txt
?? scratch.txt
D  old.txt
~~~

Cột thứ nhất mô tả trạng thái index so với HEAD; cột thứ hai mô tả working tree so với index.

| Mã | Ý nghĩa thường gặp |
| --- | --- |
| M | Modified |
| A | Added |
| D | Deleted |
| R | Renamed |
| C | Copied |
| ?? | Untracked |
| !! | Ignored, khi yêu cầu hiển thị ignored bằng tùy chọn --ignored |

Ví dụ:

- ` M README.md`: tệp tracked đã sửa trong working tree, chưa stage.
- `M  src/App.java`: thay đổi đã stage, working tree không có sửa đổi bổ sung.
- `MM config/app.yml`: đã stage một phiên bản, sau đó sửa tiếp trong working tree.
- `A  notes.txt`: tệp mới đã stage.
- `?? scratch.txt`: tệp untracked.

Để hiển thị cả đường dẫn ignored:

~~~bash
git status --short --ignored
~~~

Với trạng thái phức tạp như rename hoặc conflict, đọc cả hai cột và thông báo đầy đủ để hiểu chính xác.

### 8.3. Porcelain output cho script

~~~bash
git status --porcelain=v1
~~~

Porcelain output có định dạng ổn định hơn dạng dành cho con người, phù hợp cho script và công cụ tự động. Nếu cần xử lý tên tệp có ký tự đặc biệt hoặc newline, dùng tùy chọn NUL:

~~~bash
git status --porcelain=v1 -z
~~~

Không nên phân tích output dạng thường bằng cách tách theo khoảng trắng, vì tên file có thể chứa khoảng trắng hoặc ký tự đặc biệt.

## 9. Ví dụ trọn vẹn về vòng đời một tệp

Giả sử repository đã có commit ban đầu và bạn muốn thêm tài liệu mới.

### Bước 1 — Tạo tệp

~~~bash
printf "Deployment notes\n" > deployment.md
git status --short
~~~

Kết quả có thể là:

~~~text
?? deployment.md
~~~

Tệp đang untracked.

### Bước 2 — Stage tệp

~~~bash
git add deployment.md
git status --short
~~~

Kết quả:

~~~text
A  deployment.md
~~~

Tệp đã được thêm vào index. Nó vẫn là tệp mới so với HEAD, nhưng đã được staged.

### Bước 3 — Sửa tệp sau khi stage

~~~bash
printf "Rollback procedure\n" >> deployment.md
git status --short
~~~

Có thể thấy:

~~~text
AM deployment.md
~~~

Index vẫn giữ phiên bản đã stage trước đó; working tree chứa nội dung mới hơn.

### Bước 4 — Xem hai phiên bản

~~~bash
git diff --cached -- deployment.md
git diff -- deployment.md
~~~

Lệnh đầu cho thấy nội dung đã stage; lệnh thứ hai cho thấy phần bổ sung chưa stage.

### Bước 5 — Stage phiên bản mới nhất

~~~bash
git add deployment.md
git diff --cached -- deployment.md
git diff -- deployment.md
~~~

Bây giờ toàn bộ nội dung mong muốn nằm trong index.

### Bước 6 — Commit

~~~bash
git commit -m "Add deployment notes"
~~~

Tệp đã được ghi vào commit mới.

### Bước 7 — Kiểm tra

~~~bash
git status
git show --stat --oneline HEAD
~~~

Nếu không còn thay đổi khác, working tree trở về trạng thái clean. deployment.md hiện được tracked và snapshot mới nhất đã committed.

## 10. Một số trường hợp đặc biệt cần nhớ

### 10.1. File bị xóa ngoài Git

Nếu bạn xóa một file tracked bằng File Explorer hoặc lệnh rm trên shell, Git nhận diện working tree thiếu file so với index.

~~~bash
git status
~~~

Để stage việc xóa:

~~~bash
git add -u -- path/to/file
~~~

Hoặc:

~~~bash
git rm -- path/to/file
~~~

Nếu muốn khôi phục file từ index:

~~~bash
git restore -- path/to/file
~~~

### 10.2. Tệp bị ignore nhưng cần thêm có chủ đích

Nếu file khớp quy tắc .gitignore, git add thông thường có thể từ chối hoặc bỏ qua nó. Có thể ép thêm:

~~~bash
git add -f path/to/file
~~~

Trước khi dùng -f, xác nhận file không chứa secret, dữ liệu build hoặc nội dung không được phép đưa vào repository.

### 10.3. File nhị phân

Với file nhị phân, git diff có thể chỉ báo rằng file khác mà không hiển thị nội dung có thể đọc được. Trạng thái tracked/modified/staged vẫn hoạt động tương tự.

Có thể xem thống kê:

~~~bash
git diff --stat
git diff --cached --stat
~~~

Với tệp lớn, cân nhắc Git LFS theo chính sách repository.

### 10.4. Rename được Git suy luận

Git không lưu một sự kiện rename độc lập trong commit. Khi so sánh hai tree, Git phát hiện khả năng rename dựa trên độ tương đồng nội dung.

Vì vậy, cùng một thao tác di chuyển có thể được hiển thị là rename hoặc delete + add nếu nội dung thay đổi quá nhiều hoặc ngưỡng phát hiện khác nhau.

### 10.5. Một thư mục có nhiều trạng thái

Nếu trong thư mục có tệp mới, tệp đã sửa và tệp đã xóa, git status có thể liệt kê từng đường dẫn với trạng thái riêng. Không nên suy luận trạng thái toàn thư mục chỉ từ một dòng.

Dùng:

~~~bash
git status --short -- src/
git diff --stat
git diff --cached --stat
~~~

## 11. Những sai lầm thường gặp

- **Nghĩ git add tạo commit:** git add chỉ cập nhật index; cần git commit để ghi snapshot vào lịch sử.
- **Nghĩ tracked luôn clean:** tracked chỉ có nghĩa Git đang quản lý đường dẫn; nội dung vẫn có thể modified.
- **Nghĩ staged là không thể sửa tiếp:** bạn có thể tiếp tục sửa tệp sau khi stage; phần sửa mới trở thành unstaged.
- **Dùng git commit mà không xem index:** commit lấy nội dung staged, không phải toàn bộ nội dung đang mở trong editor.
- **Cho rằng git add -A chỉ thêm file mới:** nó cập nhật cả thêm, sửa và xóa trong phạm vi.
- **Cho rằng git commit -a thêm file untracked:** -a chỉ áp dụng cho tệp đã được theo dõi.
- **Nghĩ .gitignore ngừng theo dõi file đã commit:** cần git rm --cached để bỏ file khỏi index; lịch sử cũ vẫn còn.
- **Dùng git restore mà không kiểm tra:** restore có thể ghi đè thay đổi local chưa được lưu ở nơi khác.
- **Nhầm ignored với untracked:** ignored file thường không xuất hiện trong danh sách untracked thông thường.
- **Nghĩ Git theo dõi thư mục rỗng:** Git cần ít nhất một tệp để lưu đường dẫn thư mục trong cây.

## 12. Bảng tra cứu nhanh

| Mục tiêu | Lệnh |
| --- | --- |
| Xem trạng thái repository | git status |
| Xem trạng thái ngắn | git status --short |
| Liệt kê tệp tracked trong index | git ls-files |
| Liệt kê tệp untracked | git ls-files --others --exclude-standard |
| Xem thay đổi chưa stage | git diff |
| Xem thay đổi đã stage | git diff --cached |
| Stage một tệp | git add path/to/file |
| Stage mọi thay đổi trong phạm vi | git add -A |
| Stage thay đổi của tệp tracked | git add -u |
| Stage từng hunk | git add -p |
| Commit index | git commit -m "message" |
| Unstage một tệp | git restore --staged path/to/file |
| Bỏ sửa đổi chưa stage | git restore path/to/file |
| Xóa tracked file và stage deletion | git rm path/to/file |
| Bỏ theo dõi nhưng giữ file local | git rm --cached path/to/file |
| Đổi tên và cập nhật index | git mv old-name new-name |
| Kiểm tra quy tắc ignore | git check-ignore -v path/to/file |
| Xem commit mới nhất | git log -1 --oneline |

## 13. Tổng kết

Vòng đời tệp trong Git được hiểu rõ nhất qua ba lớp: HEAD là snapshot đã commit, index là snapshot chuẩn bị cho commit tiếp theo, và working tree là nội dung trên đĩa. Một tệp mới có thể bắt đầu ở trạng thái untracked; sau git add, nó trở thành tracked và staged; sau git commit, nội dung được ghi vào lịch sử. Với tệp đã tracked, chỉnh sửa tạo trạng thái modified; stage chọn phiên bản vào index; commit ghi phiên bản đó vào snapshot mới.

Hãy dùng git status để quan sát tổng thể, git diff để xem phần chưa stage, git diff --cached để xem phần đã stage và git show để kiểm tra nội dung commit. Trước mỗi commit, xác nhận index chỉ chứa thay đổi dự định. Khi cần bỏ staging hoặc khôi phục nội dung, chọn đúng lệnh restore/rm và hiểu rõ dữ liệu nào sẽ bị thay đổi.

Nắm được các trạng thái này giúp bạn kiểm soát chính xác nội dung commit, tránh đưa nhầm file và làm việc an toàn hơn với repository Git.


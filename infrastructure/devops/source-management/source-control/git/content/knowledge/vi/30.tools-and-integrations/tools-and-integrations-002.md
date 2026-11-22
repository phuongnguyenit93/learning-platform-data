# Đối chiếu thao tác giao diện với status, diff và log

Các IDE và ứng dụng Git GUI giúp xem file thay đổi, stage từng phần, tạo commit, chuyển branch và đọc lịch sử bằng thao tác trực quan. Tuy nhiên, giao diện chỉ là một cách tương tác với repository. Đằng sau mỗi nút bấm vẫn là các trạng thái và thao tác Git cụ thể.

Khi hiểu cách đối chiếu giao diện với ba nhóm lệnh status, diff và log, bạn có thể kiểm tra chính xác điều gì đang xảy ra, phát hiện khác biệt giữa phần đã stage và chưa stage, xác nhận commit có chứa đúng nội dung hay không và điều tra lịch sử khi giao diện hiển thị chưa rõ.

Nguyên tắc quan trọng là luôn xác định trạng thái của HEAD, index và working tree trước khi kết luận. Một danh sách file có dấu chấm hoặc màu sắc trong IDE không thay thế được việc hiểu Git đang lưu thay đổi ở đâu.

## 1. Giao diện Git đang hiển thị điều gì?

Hầu hết IDE có các khu vực như Changes, Source Control, Commit, Branches, History hoặc Log. Tên gọi và cách bố trí khác nhau giữa công cụ, nhưng chúng thường phản ánh cùng một mô hình Git.

~~~text
                  HEAD
          commit hiện tại của branch
                    |
                    v
              ┌──────────┐
              │  Index   │  <- Staging area
              └──────────┘
                    |
                    v
              ┌──────────┐
              │ Working  │
              │  tree    │
              └──────────┘

HEAD so với Index: nội dung đã stage (git diff --cached)
Index so với Working tree: nội dung sửa nhưng chưa stage (git diff)
~~~

- **HEAD:** commit mà repository đang đứng tại đó, thường thông qua branch hiện tại.
- **Index (staging area):** snapshot kế tiếp sẽ được đưa vào commit.
- **Working tree:** file thực tế trên đĩa, có thể khác nội dung trong index hoặc commit.

Giao diện thường nhóm file thành Staged Changes và Changes. Nhóm Staged Changes tương ứng khác biệt giữa index và HEAD; nhóm Changes thường tương ứng khác biệt giữa working tree và index.

Một số công cụ gộp hoặc ẩn các nhóm này. Khi không chắc, dùng status và diff để xác nhận.

## 2. Bản đồ thao tác giao diện và lệnh Git

Bảng dưới đây đối chiếu các thao tác phổ biến. Tên nút có thể khác nhau giữa VS Code, Visual Studio, IntelliJ IDEA, Android Studio, GitKraken và các GUI khác.

| Thao tác trên giao diện | Ý nghĩa trong Git | Lệnh để kiểm tra hoặc thực hiện |
|---|---|---|
| Refresh / Refresh Changes | Đọc lại trạng thái repository | git status |
| Stage file | Đưa nội dung file vào index | git add &lt;path&gt; |
| Stage hunk / Stage selected lines | Chỉ stage một phần diff | git add -p |
| Unstage file | Bỏ nội dung khỏi index, giữ sửa đổi trong working tree | git restore --staged -- &lt;path&gt; |
| Unstage hunk | Bỏ một phần thay đổi khỏi index | git restore --staged -p -- &lt;path&gt; |
| Discard changes | Khôi phục file working tree theo index | git restore -- &lt;path&gt; |
| Discard selected hunk | Bỏ một phần sửa đổi chưa stage | git restore -p -- &lt;path&gt; |
| View staged diff | Xem nội dung sẽ được commit | git diff --cached |
| View unstaged diff | Xem nội dung chưa stage | git diff |
| Commit | Tạo commit từ index | git commit |
| View commit details | Xem metadata và patch của commit | git show &lt;commit&gt; |
| Open history / Log | Xem các commit có thể truy cập | git log |
| Compare branches | So sánh hai mốc hoặc hai branch | git diff &lt;base&gt;...&lt;branch&gt; |
| Create branch | Tạo branch mới | git branch &lt;name&gt; hoặc git switch -c &lt;name&gt; |
| Checkout / Switch branch | Chuyển branch | git switch &lt;name&gt; |
| Fetch | Lấy object và cập nhật remote-tracking refs | git fetch &lt;remote&gt; |
| Pull | Fetch rồi tích hợp vào branch hiện tại | git pull |

Đây là đối chiếu về ý nghĩa. Một nút Sync, Update hoặc Commit & Push có thể thực hiện nhiều lệnh liên tiếp. Hãy xem thông tin chi tiết hoặc output của công cụ nếu cần biết chính xác chuỗi thao tác.

## 3. Đọc trạng thái bằng git status

Khu vực Changes trong IDE thường được xây dựng từ trạng thái mà Git trả về. Khi cần kiểm tra độc lập, bắt đầu bằng:

~~~sh
git status
git status -sb
git status --short
~~~

- git status cho thông tin đầy đủ, gồm branch, trạng thái staging, thay đổi chưa stage, file chưa track và conflict.
- git status -sb hiển thị branch cùng trạng thái ngắn gọn.
- git status --short hiển thị dạng hai cột để dễ nhận biết thay đổi ở index và working tree.

### 3.1. Hiểu hai cột trong status --short

Mỗi dòng dạng ngắn có cấu trúc:

~~~text
XY path
~~~

- X mô tả trạng thái trong index (staging area).
- Y mô tả trạng thái trong working tree so với index.

Ví dụ:

| Ký hiệu | Ý nghĩa |
|---|---|
| M  file.txt | File đã stage thay đổi |
|  M file.txt | File sửa nhưng chưa stage |
| MM file.txt | Có thay đổi đã stage và sau đó lại sửa thêm trong working tree |
| A  file.txt | File mới đã stage |
| D  file.txt | File đã stage việc xóa |
|  D file.txt | File bị xóa trong working tree nhưng thay đổi chưa stage |
| ?? file.txt | File chưa được theo dõi |
| UU file.txt | File đang có conflict chưa được giải quyết |

Với rename hoặc copy, Git có thể hiển thị R hoặc C kèm đường dẫn nguồn/đích tùy format và cấu hình. Với conflict, hai ký tự ở hai cột thể hiện trạng thái của cả hai phía; hãy dùng git status đầy đủ để xem hướng dẫn xử lý.

Ví dụ:

~~~text
 M src/order-service.ts
M  README.md
MM package.json
?? notes.txt
~~~

Diễn giải:

- order-service.ts đang có sửa đổi chưa stage.
- README.md đã stage.
- package.json có nội dung đã stage và có sửa đổi mới chưa stage.
- notes.txt chưa được Git theo dõi.

### 3.2. Vì sao một file xuất hiện ở hai nhóm?

Giả sử bạn sửa package.json, stage nó trong IDE rồi tiếp tục sửa thêm. Index vẫn giữ snapshot tại thời điểm stage đầu tiên; working tree chứa nội dung mới hơn. Git hiển thị MM vì hai vùng đều khác nhau.

Kiểm tra:

~~~sh
git diff --cached -- package.json
git diff -- package.json
~~~

Lệnh đầu cho biết phần đã stage. Lệnh thứ hai cho biết phần sửa thêm sau khi stage. Hai phần có thể được đưa vào hai commit khác nhau nếu bạn muốn.

### 3.3. File untracked và ignored

File mới có thể xuất hiện trong IDE nhưng chưa được stage. Xác nhận bằng:

~~~sh
git status --short
~~~

File bị ignore thường không xuất hiện trong danh sách mặc định. Muốn xem:

~~~sh
git status --short --ignored
git check-ignore -v path/to/file
~~~

Nếu GUI không hiển thị file, đừng kết luận file không tồn tại. Có thể file đang bị ignore, bị bộ lọc của IDE ẩn hoặc nằm ngoài repository.

### 3.4. Xem trạng thái branch và remote

~~~sh
git status -sb
git branch -vv
git fetch origin
git status -sb
~~~

Status có thể cho biết branch hiện tại ahead hoặc behind upstream. Các con số này dựa trên remote-tracking ref đã fetch gần nhất. Nếu chưa fetch, số liệu trong GUI có thể cũ.

Fetch chỉ cập nhật thông tin từ remote; nó không tự merge hoặc rebase thay đổi vào branch hiện tại.

## 4. Đối chiếu Stage và Unstage

Nút Stage trong IDE thường tương ứng với git add. Stage không tạo commit; nó chọn nội dung sẽ được đưa vào commit tiếp theo.

### 4.1. Stage một file

Giao diện: chọn file trong Changes rồi bấm Stage.

CLI:

~~~sh
git add src/order-service.ts
git status --short
git diff --cached -- src/order-service.ts
~~~

Sau khi stage, file thường chuyển từ nhóm Changes sang Staged Changes. Diff đã stage phải phản ánh đúng nội dung bạn muốn commit.

### 4.2. Unstage một file

Giao diện: bấm Unstage hoặc chuyển file khỏi nhóm Staged Changes.

CLI:

~~~sh
git restore --staged -- src/order-service.ts
~~~

Lệnh này đưa nội dung trong index của file về trạng thái ở HEAD. Các sửa đổi trong working tree vẫn được giữ lại. Kiểm tra:

~~~sh
git status --short
git diff -- src/order-service.ts
~~~

### 4.3. Stage một phần thay đổi

Nhiều GUI cho phép stage từng hunk hoặc từng dòng. CLI tương đương là:

~~~sh
git add -p src/order-service.ts
~~~

Git hiển thị từng phần diff và hỏi có stage phần đó không. Đây là cách tạo commit nhỏ, tách biệt các mục đích thay đổi trong cùng file.

Kiểm tra sau khi stage một phần:

~~~sh
git diff --cached -- src/order-service.ts
git diff -- src/order-service.ts
~~~

Hai diff phải cho thấy phần staged và unstaged đúng như dự định. Không chỉ dựa vào màu sắc của từng dòng trong GUI.

### 4.4. Unstage một phần

Có thể dùng chế độ patch để chọn phần cần bỏ khỏi index:

~~~sh
git restore --staged -p -- src/order-service.ts
~~~

Lệnh này chỉ thay đổi index theo lựa chọn; phần sửa trong working tree vẫn được giữ. Sau đó xem lại cả staged diff và unstaged diff.

## 5. Đối chiếu Discard và Restore

Nút Discard thường có tác động xóa sửa đổi. Cần xác định GUI đang bỏ phần staged, unstaged hay cả hai.

### 5.1. Bỏ sửa đổi chưa stage

CLI:

~~~sh
git restore -- src/order-service.ts
~~~

Lệnh khôi phục working tree theo index. Nếu file có cả phần staged và unstaged, lệnh này bỏ phần unstaged và giữ nội dung staged.

### 5.2. Bỏ một phần sửa đổi chưa stage

~~~sh
git restore -p -- src/order-service.ts
~~~

Git cho chọn từng hunk cần khôi phục. Kiểm tra diff trước và sau để bảo đảm phần cần giữ không bị bỏ.

### 5.3. Hủy cả nội dung staged và unstaged?

Không dùng một nút Discard chung khi chưa biết phạm vi. Nếu mục tiêu là bỏ toàn bộ thay đổi của file về trạng thái commit hiện tại, thao tác cần xử lý cả index và working tree. Có thể dùng:

~~~sh
git restore --source=HEAD --staged --worktree -- src/order-service.ts
~~~

Lệnh này thay đổi cả index và working tree theo HEAD. Nội dung chưa commit của file có thể mất. Chỉ chạy sau khi đã kiểm tra và sao lưu phần cần giữ.

## 6. Đối chiếu Diff trong IDE với git diff

Diff là cách xem sự khác nhau giữa hai trạng thái. Khi mở tab diff của một file trong GUI, cần biết hai phía đang được so sánh là gì.

| Mục đích | Lệnh | Hai phía được so sánh |
|---|---|---|
| Xem sửa đổi chưa stage | git diff | Index với working tree |
| Xem nội dung đã stage | git diff --cached | HEAD với index |
| Xem tất cả thay đổi so với commit hiện tại | git diff HEAD | HEAD với working tree |
| Xem tên file thay đổi | git diff --name-only | Danh sách đường dẫn trong diff |
| Xem trạng thái file thay đổi | git diff --name-status | Trạng thái thêm/sửa/xóa/rename |
| Xem thống kê | git diff --stat | Số dòng thêm/xóa theo file |
| Kiểm tra whitespace | git diff --check | Lỗi whitespace trong diff |

### 6.1. Khi GUI hiển thị diff của file đang sửa

Một tab diff có thể so sánh:

- Bản trong HEAD với bản working tree.
- Bản trong index với bản working tree.
- Bản trong HEAD với bản index.
- Hai commit hoặc hai branch được chọn.

Nếu không rõ, chạy từng lệnh:

~~~sh
git diff -- path/to/file
git diff --cached -- path/to/file
git diff HEAD -- path/to/file
~~~

Đối chiếu nội dung hiển thị với tab diff. Không cho rằng mọi tab có tên Changes đều hiển thị cùng một phạm vi.

### 6.2. So sánh branch như khi xem pull request

Để xem thay đổi của branch feature kể từ điểm phân kỳ với main:

~~~sh
git diff main...feature/report
~~~

Với git diff, cú pháp ba chấm so sánh tip của nhánh thứ hai với merge-base của hai nhánh. Điều này thường gần với phần thay đổi được đề xuất trong pull request.

Để xem các commit có trên feature nhưng chưa có trên main:

~~~sh
git log --oneline main..feature/report
~~~

Hai lệnh trả lời hai câu hỏi khác nhau: diff cho biết nội dung thay đổi; log cho biết commit nào tạo ra thay đổi đó.

### 6.3. Xem diff theo từng loại đầu ra

~~~sh
git diff --stat
git diff --name-status
git diff --numstat
git diff --word-diff
~~~

Các tùy chọn này giúp kiểm tra nhanh phạm vi thay đổi trước khi mở patch đầy đủ. Tuy nhiên, chúng vẫn có thể tiết lộ tên file hoặc metadata nội bộ khi chia sẻ.

## 7. Đối chiếu Commit trong GUI với Git

Khu vực Commit thường cho phép nhập message, chọn file staged và bấm Commit. Git tạo commit từ nội dung trong index, không phải mọi thay đổi đang có trên working tree.

### 7.1. Xác nhận nội dung sẽ được commit

Trước khi bấm Commit:

~~~sh
git status
git diff --cached
git diff --cached --check
~~~

- Status xác nhận file nào đang staged.
- Diff xác nhận nội dung chính xác trong index.
- Diff check tìm lỗi whitespace phổ biến.

Nếu GUI có nút Commit All, hãy xác nhận nút đó có tự stage toàn bộ file hay không. Một số công cụ có thể stage mọi thay đổi trước khi commit; một số khác chỉ commit phần đã chọn.

### 7.2. Commit và kiểm tra kết quả

CLI:

~~~sh
git commit -m "feat(order): add order search"
git status -sb
git show --stat --oneline HEAD
~~~

Sau commit:

- HEAD trỏ tới commit mới.
- Index thường trở về trạng thái khớp với commit mới.
- Những thay đổi chưa stage vẫn có thể còn trong working tree.
- Những file chưa được chọn có thể vẫn xuất hiện trong status.

Nếu GUI báo commit thành công nhưng status vẫn còn file thay đổi, hãy kiểm tra xem đó là phần sửa mới sau khi stage, file chưa stage hay file mới chưa được track.

### 7.3. Xem nội dung commit

~~~sh
git show --format=fuller --stat HEAD
git show --format=fuller HEAD
~~~

Lệnh đầu hiển thị metadata và thống kê. Lệnh thứ hai hiển thị cả patch. Đây là cách xác nhận author, committer, message và nội dung thực sự đã được ghi vào commit.

## 8. Đọc lịch sử bằng git log

Màn hình History hoặc Log trong IDE thường hiển thị danh sách commit, graph branch, tag và metadata. Các thông tin đó đến từ lịch sử mà Git có thể truy cập qua refs.

### 8.1. Xem log cơ bản

~~~sh
git log
git log --oneline
git log --oneline --decorate --graph --all
~~~

- git log hiển thị chi tiết commit.
- --oneline rút gọn mỗi commit thành một dòng.
- --decorate hiển thị branch và tag đang trỏ tới commit.
- --graph vẽ quan hệ phân nhánh và merge.
- --all duyệt các commit có thể truy cập từ các ref được Git xét.

### 8.2. Xem một commit cụ thể

~~~sh
git show <commit-sha>
git show --stat <commit-sha>
git show --name-status <commit-sha>
~~~

Khi click một commit trong GUI, xem chi tiết patch và danh sách file. Dùng git show để xác nhận commit SHA và nội dung chính xác.

### 8.3. Lọc lịch sử

~~~sh
git log --author="An"
git log --since="2026-01-01" --until="2026-12-31"
git log --grep="order"
git log -- path/to/file
~~~

Các bộ lọc trong GUI thường tương ứng với những điều kiện này. Lưu ý author filter khớp metadata tác giả, không phải nội dung code; grep tìm trong commit message; lọc theo path giới hạn lịch sử liên quan tới đường dẫn.

### 8.4. Lịch sử của một file và rename

~~~sh
git log --follow --oneline -- path/to/file
git log -p --follow -- path/to/file
~~~

--follow cố gắng tiếp tục theo dõi lịch sử khi file được rename. Nó áp dụng cho một đường dẫn tại một thời điểm và có một số giới hạn với lịch sử phức tạp.

Một số IDE hiển thị lịch sử file nhưng có thể không nối được toàn bộ rename. Khi cần điều tra, dùng log --follow và xác minh commit cụ thể.

## 9. Đối chiếu branch graph và ahead/behind

Graph trong GUI giúp nhìn branch và merge. Để kiểm tra bằng CLI:

~~~sh
git log --oneline --graph --decorate --all
git branch -vv
git status -sb
~~~

Branch có thể được hiển thị:

- Ahead: có commit local chưa có trên upstream.
- Behind: upstream có commit mà branch local chưa tích hợp.
- Diverged: hai phía có commit riêng.

Các con số ahead/behind dựa trên remote-tracking refs đã fetch. Nếu chưa fetch, giao diện có thể hiển thị trạng thái cũ.

Để xem commit chỉ có trên một phía:

~~~sh
git log --oneline "HEAD..@{upstream}"
git log --oneline "@{upstream}..HEAD"
~~~

Lệnh đầu hiển thị commit ở upstream mà HEAD chưa có; lệnh thứ hai hiển thị commit local mà upstream chưa có. Nếu branch chưa cấu hình upstream, biểu thức @{upstream} không phân giải được.

## 10. Đối chiếu thao tác Fetch, Pull và Push

Một số GUI gom các thao tác đồng bộ thành nút Sync. Cần hiểu lệnh tương ứng:

| Thao tác | Lệnh | Tác động |
|---|---|---|
| Fetch | git fetch origin | Cập nhật object và remote-tracking refs |
| Pull mặc định | git pull | Fetch rồi tích hợp branch upstream theo cấu hình |
| Pull bằng rebase | git pull --rebase | Fetch rồi rebase commit local lên upstream |
| Push | git push | Gửi commit/ref local lên remote |

Trước khi Pull:

~~~sh
git status -sb
git fetch origin
git log --oneline --graph --decorate "HEAD...@{upstream}"
git diff "HEAD...@{upstream}"
~~~

Lệnh log với ba chấm hiển thị các commit chỉ có ở một trong hai phía. Lệnh diff ba chấm so sánh nội dung upstream với merge-base theo ngữ nghĩa của git diff; đừng nhầm hai cách dùng dấu ba chấm.

Sau Pull hoặc Push, kiểm tra lại:

~~~sh
git status -sb
git log --oneline --decorate -5
git branch -vv
~~~

Nếu GUI báo Sync thành công nhưng branch vẫn ahead/behind, xác định nó đã thực hiện fetch, pull, push hay chỉ một phần của chuỗi thao tác.

## 11. Đối chiếu xử lý conflict

Khi merge hoặc rebase gặp conflict, GUI thường đánh dấu file cần giải quyết và cung cấp lựa chọn giữ Current, Incoming hoặc Both. Những tên này phụ thuộc góc nhìn của công cụ và thao tác đang chạy.

Kiểm tra trạng thái:

~~~sh
git status
git diff
git diff --cc
~~~

Sau khi chỉnh sửa conflict, stage file đã giải quyết:

~~~sh
git add path/to/conflicted-file
git status
~~~

Nếu đang merge:

~~~sh
git merge --continue
~~~

Nếu đang rebase:

~~~sh
git rebase --continue
~~~

Không bấm Continue chỉ vì file đã hết dấu conflict. Hãy đọc diff, chạy test và kiểm tra logic của cả hai phía.

Nếu cần hủy:

~~~sh
git merge --abort
git rebase --abort
~~~

Chỉ chạy lệnh tương ứng với thao tác đang diễn ra. Abort có thể khôi phục trạng thái trước khi merge/rebase nhưng cần xem xét các thay đổi có từ trước.

## 12. Quy trình kiểm tra trước và sau một thao tác GUI

Một thói quen hữu ích là kiểm tra bằng CLI ở các điểm quan trọng.

### 12.1. Trước khi stage hoặc commit

~~~sh
git status -sb
git diff
git diff --cached
~~~

Mục tiêu là biết file nào mới, file nào đã stage và nội dung nào sẽ được commit.

### 12.2. Sau khi stage

~~~sh
git status --short
git diff --cached --stat
git diff --cached
~~~

Mục tiêu là xác nhận index chứa đúng phần thay đổi dự định.

### 12.3. Sau khi commit

~~~sh
git status -sb
git show --stat --oneline HEAD
git show --format=fuller --no-ext-diff HEAD
~~~

Mục tiêu là xác nhận commit mới và nội dung của nó, đồng thời phát hiện phần sửa còn sót lại.

### 12.4. Sau khi đồng bộ remote

~~~sh
git fetch origin
git status -sb
git branch -vv
git log --oneline --graph --decorate --all -20
~~~

Mục tiêu là xác nhận branch và remote-tracking ref đã ở trạng thái mong đợi.

## 13. Khi giao diện và CLI hiển thị khác nhau

Nếu IDE và lệnh Git dường như không khớp, hãy kiểm tra theo thứ tự:

1. **Repository đang mở:** IDE có thể đang mở một thư mục con hoặc một repository khác trong workspace.
2. **Refresh:** giao diện có thể chưa đọc lại filesystem sau khi thay đổi từ terminal hoặc công cụ khác.
3. **Index và working tree:** file có thể có cả thay đổi staged lẫn unstaged.
4. **Ignored và untracked:** bộ lọc của IDE có thể ẩn file.
5. **Submodule:** repository cha hiển thị gitlink, trong khi nội dung file nằm trong repository con.
6. **Rename detection:** GUI và Git có thể nhóm rename khác nhau dựa trên ngưỡng similarity.
7. **Whitespace và line endings:** bộ lọc hiển thị có thể ẩn khác biệt CRLF/LF hoặc whitespace.
8. **External diff tool:** IDE có thể dùng công cụ diff riêng với cách trình bày khác.
9. **Git executable và config:** IDE có thể dùng Git binary, environment hoặc config khác terminal.

Kiểm tra:

~~~sh
git rev-parse --show-toplevel
git rev-parse --git-dir
git --version
git config --show-origin --get core.autocrlf
git config --show-origin --get core.pager
~~~

Không mặc định CLI và IDE dùng cùng một môi trường nếu IDE có cấu hình Git executable hoặc environment riêng. Khi phát hiện khác biệt, kiểm tra repository root và cấu hình thực tế trước khi thay đổi file.

## 14. Các lệnh status, diff và log nên nhớ

| Nhu cầu | Lệnh |
|---|---|
| Xem tổng quan repository | git status -sb |
| Xem trạng thái ngắn | git status --short |
| Xem file ignored | git status --short --ignored |
| Xem sửa đổi chưa stage | git diff |
| Xem sửa đổi đã stage | git diff --cached |
| Xem mọi thay đổi so với HEAD | git diff HEAD |
| Xem tên file thay đổi | git diff --name-status |
| Xem thống kê thay đổi | git diff --stat |
| Kiểm tra whitespace | git diff --check |
| Xem log dạng graph | git log --oneline --graph --decorate --all |
| Xem commit mới nhất | git show --stat HEAD |
| Xem lịch sử một file | git log --follow -- path/to/file |
| Xem commit trên branch feature | git log --oneline main..feature |
| Xem diff của branch so với điểm phân kỳ | git diff main...feature |

Các lệnh này đủ để kiểm tra phần lớn thông tin thường xuất hiện trong Source Control, Changes, Diff và History của IDE.

## 15. Những nhầm lẫn thường gặp

**Thấy file trong Changes và nghĩ file đã stage.** Kiểm tra cột X/Y bằng git status --short. File có thể chỉ mới sửa trong working tree.

**Thấy file trong Staged Changes và nghĩ toàn bộ sửa đổi đã được stage.** File có thể có trạng thái MM nếu đã sửa thêm sau khi stage. Xem cả git diff --cached và git diff.

**Bấm Commit All mà không kiểm tra index.** Một số GUI tự stage mọi file; một số chỉ commit nội dung đã stage. Xem status và staged diff trước khi commit.

**Nghĩ Discard chỉ xóa phần đang nhìn thấy.** Nút này có thể bỏ toàn bộ file hoặc cả staged/unstaged tùy công cụ. Đọc xác nhận và kiểm tra phạm vi.

**So sánh hai branch bằng log rồi kết luận nội dung giống nhau.** Log cho biết commit; diff mới cho biết nội dung file khác nhau.

**Tin số ahead/behind khi chưa fetch.** Remote-tracking ref có thể cũ. Fetch rồi kiểm tra lại.

**Nghĩ GUI và terminal luôn dùng cùng Git.** IDE có thể dùng Git binary hoặc cấu hình khác. Kiểm tra repository root và config khi có sai lệch.

**Bỏ qua file ignored vì không thấy trong danh sách.** Dùng status --ignored hoặc check-ignore để xác định.

## 16. Checklist làm việc với Git GUI và CLI

**Trước khi thay đổi**

- [ ] Xác nhận repository root và branch hiện tại.
- [ ] Refresh trạng thái trong IDE.
- [ ] Chạy git status -sb.
- [ ] Phân biệt file staged, unstaged, untracked và ignored.

**Trước khi commit**

- [ ] Xem git diff.
- [ ] Xem git diff --cached.
- [ ] Xác nhận file và hunk được stage đúng.
- [ ] Chạy git diff --cached --check.
- [ ] Kiểm tra commit message.

**Sau khi commit**

- [ ] Xem git show --stat HEAD.
- [ ] Xác nhận nội dung commit.
- [ ] Chạy git status -sb để tìm thay đổi còn lại.

**Khi xem lịch sử hoặc đồng bộ**

- [ ] Dùng git log để xác nhận commit và branch.
- [ ] Fetch trước khi tin số ahead/behind.
- [ ] Dùng diff để so sánh nội dung, log để so sánh lịch sử.
- [ ] Kiểm tra conflict bằng status và diff trước khi tiếp tục.

## 17. Kết luận

Giao diện Git giúp thao tác trực quan, còn status, diff và log cung cấp cách kiểm chứng độc lập. Status cho biết thay đổi đang nằm trong index hay working tree; diff cho biết nội dung khác nhau giữa các trạng thái; log cho biết commit và quan hệ lịch sử.

Khi hiểu ba nhóm lệnh này, bạn có thể đối chiếu nút Stage, Unstage, Discard, Commit, History, Fetch và Sync với hành vi thực tế của Git. Hãy kiểm tra staged diff trước commit, xem lại commit sau khi tạo và fetch trước khi đánh giá trạng thái remote. Thói quen đó giúp tránh commit nhầm file, bỏ mất sửa đổi hoặc hiểu sai điều giao diện đang hiển thị.

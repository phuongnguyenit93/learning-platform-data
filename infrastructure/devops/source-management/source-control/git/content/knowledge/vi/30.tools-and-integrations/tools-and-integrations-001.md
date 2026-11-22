# Phối hợp dòng lệnh Git với giao diện đồ họa và IDE

## Vì sao nên phối hợp nhiều giao diện Git?

Git là hệ thống quản lý phiên bản. Dòng lệnh, ứng dụng giao diện đồ họa (GUI) và tính năng Git tích hợp trong IDE chỉ là những cách khác nhau để thao tác với cùng một repository.

Bạn có thể dùng terminal để xem chính xác trạng thái, kiểm tra lịch sử hoặc thực hiện thao tác ít gặp; sau đó dùng IDE để xem diff cạnh mã nguồn, stage từng phần thay đổi và giải quyết conflict bằng trình soạn thảo trực quan. Ngược lại, bạn có thể tạo nhánh và commit trong GUI rồi dùng lệnh Git để xác minh kết quả.

Phối hợp các giao diện có ích vì:

- Terminal cung cấp lệnh rõ ràng, có thể ghi lại và lặp lại trong tài liệu hoặc script.
- GUI trình bày branch, commit, diff và trạng thái file trực quan.
- IDE đặt thay đổi Git cạnh mã nguồn, cảnh báo lỗi cú pháp và hỗ trợ điều hướng giữa các file.
- Công cụ đồ họa thường giúp so sánh hai phiên bản và xử lý conflict dễ quan sát hơn.
- Dòng lệnh giúp kiểm tra những trường hợp giao diện đang ẩn bớt chi tiết hoặc không hỗ trợ đầy đủ.

Điểm quan trọng là các giao diện đang thao tác trên cùng working tree, index, repository và refs. Khi một giao diện stage file, giao diện khác sẽ nhìn thấy trạng thái staged đó sau khi làm mới hoặc đọc lại repository. Không có một bộ commit riêng cho IDE và một bộ commit riêng cho terminal.

## Hiểu các vùng trạng thái trước khi đổi giao diện

Để phối hợp chính xác, cần biết Git đang lưu thay đổi ở đâu:

~~~text
                ┌────────────────────┐
                │   Working tree     │
                │  File đang sửa     │
                └─────────┬──────────┘
                          │ git add
                          v
                ┌────────────────────┐
                │       Index        │
                │   Staging area     │
                └─────────┬──────────┘
                          │ git commit
                          v
                ┌────────────────────┐
                │     Repository     │
                │ Commit và lịch sử  │
                └────────────────────┘
~~~

- **Working tree:** các file bạn đang xem và sửa trong thư mục dự án.
- **Index (staging area):** nội dung đã chọn để đưa vào commit tiếp theo.
- **Repository:** các Git object và commit đã được tạo.
- **Refs:** các tên như branch và tag trỏ tới commit.
- **Remote-tracking refs:** thông tin local về trạng thái nhánh trên remote sau fetch.

GUI và IDE có thể gọi index bằng tên như Staged Changes, Index hoặc Staged Files. Những file chưa stage thường được hiển thị trong Changes, Unstaged Changes hoặc Local Changes. Tên cụ thể tùy công cụ.

Một file có thể xuất hiện đồng thời ở cả hai nhóm nếu bạn đã stage một phiên bản rồi tiếp tục sửa file đó. Phần staged là nội dung đã chọn cho commit; phần unstaged là thay đổi mới hơn chưa được stage.

Ví dụ:

1. Bạn sửa file `PaymentService.java`.
2. Stage thay đổi hiện tại.
3. Bạn sửa tiếp file đó.
4. Git có thể hiển thị file ở cả Staged và Unstaged.

Trong tình huống này, commit chỉ ghi nội dung đã stage. Nếu muốn đưa phần sửa mới vào cùng commit, cần stage lại phần đó.

## Một repository có thể được mở bằng nhiều công cụ

Ví dụ một dự án được mở đồng thời bằng:

- Terminal tại thư mục repository.
- IDE để chỉnh sửa mã nguồn.
- Git GUI để xem lịch sử và branch.

Cả ba cùng đọc và ghi dữ liệu trong một thư mục làm việc. Tuy nhiên, mỗi ứng dụng có thể giữ cache trạng thái trong bộ nhớ và chỉ làm mới theo chu kỳ hoặc khi có sự kiện file.

Vì vậy, sau khi thao tác trong một công cụ, nếu công cụ khác chưa cập nhật ngay:

- Làm mới Git Changes hoặc Source Control view.
- Chuyển tab rồi quay lại nếu ứng dụng cần đọc lại trạng thái.
- Chạy `git status` trong terminal để kiểm tra trạng thái thực tế.
- Tránh tiếp tục thao tác dựa trên một màn hình chưa được cập nhật.

Không mở cùng một repository trong nhiều cửa sổ rồi thực hiện các thao tác ghi đồng thời như commit, rebase hoặc checkout ở nhiều nơi. Một số thao tác dùng lock file hoặc thay đổi index và HEAD; chạy chồng nhau có thể khiến một tiến trình bị từ chối hoặc hiển thị trạng thái tạm thời khó hiểu.

### Xác định chính xác repository đang thao tác

Trong terminal, kiểm tra:

~~~bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git branch --show-current
git status --short --branch
~~~

Các lệnh này giúp xác nhận:

- Đường dẫn gốc của working tree.
- Git directory mà repository đang sử dụng.
- Nhánh hiện tại.
- Các thay đổi đang có.

Trong GUI hoặc IDE, kiểm tra đường dẫn repository ở thanh trạng thái, cửa sổ Git hoặc danh sách project. Đừng giả định thư mục project đang mở cũng chính là repository root; một workspace có thể chứa nhiều repository lồng nhau hoặc nhiều module.

Nếu IDE mở monorepo có nhiều repository con, kiểm tra repository selector trước khi commit hoặc push. Chọn nhầm repository có thể khiến thay đổi được commit vào một lịch sử khác với dự định.

## Bảng đối chiếu thao tác CLI và GUI/IDE

Tên nút và cách sắp xếp có thể khác giữa GitHub Desktop, Sourcetree, GitKraken, VS Code, IntelliJ IDEA và các IDE khác. Bảng dưới mô tả ý nghĩa thao tác tương đương, không phải vị trí menu cố định.

| Mục tiêu | Dòng lệnh Git | GUI hoặc IDE thường dùng |
|---|---|---|
| Xem trạng thái | `git status` | Mở Git Changes, Source Control hoặc Commit view |
| Xem thay đổi file | `git diff` | Chọn file trong nhóm Unstaged/Changes |
| Xem nội dung đã stage | `git diff --cached` | Mở nhóm Staged Changes |
| Stage một file | `git add <file>` | Chọn Stage hoặc dấu cộng cạnh file |
| Bỏ stage | `git restore --staged <file>` | Unstage hoặc chuyển file về nhóm Changes |
| Stage từng phần | `git add -p` | Stage hunk hoặc chọn dòng |
| Commit | `git commit` | Nhập message rồi chọn Commit |
| Xem lịch sử | `git log --graph --oneline --all` | Mở History hoặc Log |
| Tạo nhánh | `git switch -c <branch>` | New Branch |
| Chuyển nhánh | `git switch <branch>` | Chọn branch rồi Checkout/Switch |
| Fetch | `git fetch origin` | Fetch hoặc Refresh Remote |
| Pull | `git pull` | Pull |
| Push | `git push` | Push hoặc Publish Branch |
| Merge | `git merge <branch>` | Chọn Merge Into Current |
| Rebase | `git rebase <branch>` | Rebase Current onto Selected |
| Giải quyết conflict | Sửa file, rồi `git add <file>` | Merge Editor, Resolve, Mark Resolved/Stage |
| Xem remote | `git remote -v` | Repository Settings hoặc Remotes |
| Xem tag | `git tag --list` | Tags trong History hoặc Repository view |

Hãy hiểu lệnh Git tương ứng với thao tác GUI. Khi GUI đưa ra lựa chọn như Update, Sync, Commit & Push hoặc Pull with Rebase, cần đọc mô tả để biết công cụ sẽ thực hiện một lệnh hay chuỗi lệnh.

## Xem thay đổi và quyết định nội dung commit

### Kiểm tra trạng thái bằng CLI và IDE

Bắt đầu bằng:

~~~bash
git status
~~~

Ví dụ:

~~~text
On branch feature/payment
Changes to be committed:
  modified:   src/PaymentService.java

Changes not staged for commit:
  modified:   README.md

Untracked files:
  src/PaymentValidator.java
~~~

Cách đọc:

- `PaymentService.java` đã stage.
- `README.md` đang sửa nhưng chưa stage.
- `PaymentValidator.java` là file mới chưa được Git theo dõi.

GUI thường chia thành các nhóm tương ứng. Hãy kiểm tra cả nhóm Staged, Unstaged và Untracked trước khi commit.

Lệnh trạng thái rút gọn:

~~~bash
git status --short --branch
~~~

Ví dụ:

~~~text
## feature/payment
M  src/PaymentService.java
 M README.md
?? src/PaymentValidator.java
~~~

Hai cột trạng thái giúp phân biệt thay đổi trong index và working tree. GUI có thể dùng icon, màu hoặc nhãn để biểu diễn cùng thông tin.

### Xem diff đúng vùng

Các lệnh quan trọng:

~~~bash
# Thay đổi chưa stage
git diff

# Thay đổi đã stage
git diff --cached

# So sánh toàn bộ working tree với HEAD
git diff HEAD
~~~

Trong IDE, chọn từng file để xem diff. Hầu hết công cụ cho phép chuyển giữa hai phiên bản:

- HEAD so với Working Tree.
- HEAD so với Index.
- Index so với Working Tree.

Hãy chọn đúng cặp phiên bản. Một diff chỉ hiển thị HEAD với working tree có thể gộp cả thay đổi staged và unstaged; nếu muốn biết commit sắp ghi những gì, hãy xem Index/Staged Changes.

### Stage cả file hay stage từng phần?

Stage cả file:

~~~bash
git add src/PaymentService.java
~~~

Bỏ stage file:

~~~bash
git restore --staged src/PaymentService.java
~~~

Nếu file chứa nhiều thay đổi thuộc các mục đích khác nhau, có thể chỉ stage một số hunk:

~~~bash
git add -p src/PaymentService.java
~~~

GUI/IDE thường có chức năng Stage Hunk, Stage Selected Lines hoặc dấu cộng bên cạnh từng khối diff. Tên gọi phụ thuộc công cụ.

Ví dụ file `PaymentService.java` có hai thay đổi:

- Hunk 1: sửa lỗi kiểm tra số tiền.
- Hunk 2: thêm log debug tạm thời.

Nếu commit chỉ nên chứa sửa lỗi, hãy stage hunk 1 và để hunk 2 ở trạng thái unstaged. Trước commit, xác minh bằng:

~~~bash
git diff --cached
git diff
~~~

Không chọn Stage All một cách máy móc nếu working tree có file sinh tự động, log, cấu hình cá nhân hoặc thay đổi chưa sẵn sàng.

### Đọc diff trước khi commit

Một quy trình kiểm tra ngắn:

~~~bash
git status --short
git diff --check
git diff --cached --check
git diff --cached --stat
git diff --cached
~~~

- `git diff --check` kiểm tra whitespace trong phần chưa stage.
- `git diff --cached --check` kiểm tra phần đã stage.
- `--stat` cho biết phạm vi thay đổi.
- Diff đầy đủ giúp xem chính xác nội dung commit.

GUI có thể hiển thị dấu whitespace hoặc cảnh báo, nhưng khi cần xác minh trạng thái index và working tree, dùng CLI để đối chiếu.

## Commit trong IDE và xác minh bằng CLI

GUI thường cung cấp ô nhập commit message và nút Commit. Trước khi bấm, kiểm tra:

1. Đúng repository và branch.
2. Danh sách file staged đúng phạm vi.
3. Không có file bí mật, log hoặc artifact không mong muốn.
4. Diff staged đã được đọc.
5. Commit message mô tả đúng thay đổi.

Commit bằng terminal:

~~~bash
git commit -m "feat(payment): validate payment amount"
~~~

Commit bằng IDE tạo cùng loại commit object như khi chạy CLI. Sau commit, xác minh:

~~~bash
git status
git log -1 --oneline --decorate
git show --stat --oneline HEAD
git show --no-patch --pretty=fuller HEAD
~~~

Nếu GUI báo commit thành công nhưng terminal hiển thị trạng thái khác, kiểm tra xem hai ứng dụng có mở cùng repository và cùng working tree không. Cũng cần kiểm tra hook có sửa file hoặc từ chối một phần quy trình hay không.

### Commit và Push là hai hành động riêng

Một số GUI có nút Commit & Push hoặc Commit and Sync. Nút này thực hiện nhiều bước liên tiếp:

1. Tạo commit local.
2. Gửi commit lên remote.

Nếu push thất bại, commit local có thể đã được tạo thành công. Đừng tạo thêm commit giống hệt chỉ vì thông báo cuối cùng báo lỗi push.

Kiểm tra:

~~~bash
git log -1 --oneline
git status -sb
git branch -vv
~~~

Nếu commit đã tồn tại ở local nhưng chưa lên remote, xử lý nguyên nhân push rồi thử push lại:

~~~bash
git push
~~~

## Quản lý branch bằng GUI và CLI

### Tạo và chuyển nhánh

Tạo nhánh mới từ HEAD hiện tại:

~~~bash
git switch -c feature/payment
~~~

Chuyển sang nhánh đã có:

~~~bash
git switch main
~~~

GUI thường có danh sách branch và lựa chọn New Branch, Checkout hoặc Switch. Trước khi tạo nhánh, xác nhận nhánh gốc đúng. Nếu tạo nhánh từ một commit hoặc branch khác, chọn đúng điểm bắt đầu.

Kiểm tra sau khi chuyển:

~~~bash
git branch --show-current
git status -sb
git log -1 --oneline --decorate
~~~

### Thay đổi chưa commit khi chuyển nhánh

GUI có thể hiện hộp thoại hỏi có muốn:

- Carry/Bring Changes: mang thay đổi sang nhánh khác.
- Stash: cất thay đổi tạm thời.
- Force Checkout/Discard: bỏ thay đổi để chuyển nhánh.

Hãy hiểu hậu quả trước khi chọn. Lệnh CLI tương ứng có thể là:

~~~bash
git stash push -m "WIP before switching branch"
git switch main
~~~

Sau đó khôi phục khi cần:

~~~bash
git stash list
git stash pop
~~~

Không chọn Discard hoặc Force Checkout nếu chưa xác định thay đổi có thể bỏ được. Nếu không chắc, lưu commit tạm hoặc stash trước.

### Theo dõi branch và remote-tracking branch

Xem branch:

~~~bash
git branch -vv
git branch -avv
~~~

GUI thường phân nhóm Local Branches và Remote Branches. Remote branch hiển thị trong GUI thường là remote-tracking ref, ví dụ `origin/main`, được cập nhật sau fetch.

Fetch không tự động chuyển branch local. Nó tải object và cập nhật thông tin remote-tracking:

~~~bash
git fetch origin
git log --oneline --decorate --graph --all
~~~

Nếu GUI hiển thị một commit mới trên `origin/main`, điều đó không có nghĩa branch local `main` đã tự cập nhật. Muốn tích hợp, dùng pull, merge hoặc rebase theo quy ước nhóm.

## Fetch, Pull, Push và các nút Sync

### Fetch trước khi tích hợp

Fetch lấy thay đổi từ remote và cập nhật remote-tracking refs:

~~~bash
git fetch origin
~~~

Đây là thao tác hữu ích khi muốn xem remote có commit mới mà chưa thay đổi branch hoặc working tree hiện tại.

GUI có thể gọi nút Fetch, Fetch All hoặc Refresh. Sau fetch, mở History hoặc Graph để xem commit mới.

### Pull là Fetch cộng tích hợp

Pull thường thực hiện fetch rồi merge hoặc rebase tùy cấu hình và tùy chọn:

~~~bash
# Pull theo merge
git pull --no-rebase

# Pull theo rebase
git pull --rebase
~~~

Một nút Pull trong GUI có thể sử dụng cấu hình `pull.rebase`, `pull.ff` hoặc tùy chọn riêng của công cụ. Hãy xem cấu hình:

~~~bash
git config --show-origin --get pull.rebase
git config --show-origin --get pull.ff
git config --show-origin --get branch.main.rebase
~~~

Nếu không rõ GUI sẽ merge hay rebase, fetch trước, xem đồ thị và chọn thao tác tích hợp tường minh.

### Push nhánh

Push nhánh hiện tại lần đầu và thiết lập upstream:

~~~bash
git push -u origin feature/payment
~~~

Sau khi upstream đã được cấu hình, có thể dùng:

~~~bash
git push
~~~

GUI có thể hiển thị Publish Branch nếu branch chưa có remote-tracking branch hoặc chưa thiết lập upstream. Kiểm tra:

~~~bash
git branch -vv
git status -sb
~~~

Nếu push bị từ chối, đọc thông báo server. Nguyên nhân có thể là non-fast-forward, thiếu quyền ghi, branch protection hoặc required checks. Không lặp lại nút Push liên tục mà chưa hiểu nguyên nhân.

### Cẩn thận với Sync

Một số công cụ có nút Sync kết hợp Pull và Push. Tùy cấu hình, nó có thể fetch/pull trước rồi push local commit.

Trước khi dùng, kiểm tra:

- Nhánh local và upstream là nhánh nào.
- Pull sẽ merge hay rebase.
- Có thay đổi chưa commit không.
- Remote có commit mới không.
- Push có bị branch protection giới hạn không.

Nếu cần kiểm soát từng bước, dùng Fetch, kiểm tra lịch sử, Pull/Rebase rồi Push riêng biệt.

## Xem lịch sử và so sánh commit

CLI:

~~~bash
git log --oneline --graph --decorate --all
~~~

Xem một commit:

~~~bash
git show <commit-id>
~~~

So sánh hai commit:

~~~bash
git diff <base>..<target>
~~~

GUI/IDE thường có History, Log, Timeline hoặc Graph. Từ đó bạn có thể:

- Chọn commit để xem file đã thay đổi.
- So sánh hai commit hoặc hai branch.
- Xem parent và merge commit.
- Tìm commit theo message hoặc tác giả.
- Mở file ở phiên bản cũ.
- Xem blame/annotate để tìm commit đã sửa một dòng.

Nếu GUI chỉ hiển thị lịch sử của branch hiện tại, bật hiển thị All Branches hoặc kiểm tra bằng `git log --all`. Không kết luận commit đã mất chỉ vì nó không xuất hiện trong chế độ xem đang chọn.

### Dùng blame trong IDE và CLI

CLI:

~~~bash
git blame -L 20,45 src/PaymentService.java
~~~

Trong IDE, chức năng Annotate hoặc Git Blame thường hiển thị commit, tác giả và ngày sửa cạnh từng dòng.

Blame cho biết commit gần nhất thay đổi dòng theo cách Git nhận diện; nó không tự chứng minh ai chịu trách nhiệm nghiệp vụ hoặc vì sao thay đổi được thực hiện. Mở commit tương ứng và xem diff, message, review hoặc issue liên quan để hiểu bối cảnh.

## Giải quyết conflict bằng Merge Editor hoặc terminal

### Nhận diện trạng thái đang merge

Khi merge có conflict, Git giữ trạng thái merge đang diễn ra. GUI/IDE thường mở Merge Editor với ba vùng:

- **Current/Ours:** phiên bản từ nhánh hiện tại.
- **Incoming/Theirs:** phiên bản từ nhánh được merge vào.
- **Result:** nội dung kết quả bạn chọn hoặc chỉnh sửa.

Các tên gọi có thể khác nhau giữa công cụ. Trong terminal, kiểm tra:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Không dựa riêng vào màu đỏ/xanh của GUI; hãy đọc nội dung hai phía và bối cảnh thay đổi.

Lưu ý rằng tên Current/Ours và Incoming/Theirs có thể gây nhầm khi rebase. Rebase phát lại từng commit trên base mới nên cách Git đặt vai trò cho hai phía có thể ngược với trực giác rằng Ours luôn là nhánh feature của bạn. Hãy đọc nhãn và mô tả của Merge Editor, kiểm tra trạng thái bằng `git status`, rồi đối chiếu nội dung từng phía trước khi chọn.

### Hoàn tất conflict

Quy trình điển hình:

1. Mở từng file conflict trong Merge Editor.
2. So sánh Current và Incoming.
3. Kết hợp logic cần giữ vào Result.
4. Lưu file.
5. Mark Resolved hoặc Stage file.
6. Kiểm tra lại diff.
7. Tiếp tục merge commit.

Trong terminal, bước stage sau khi sửa là:

~~~bash
git add src/PaymentService.java
~~~

Kiểm tra không còn unmerged paths:

~~~bash
git diff --name-only --diff-filter=U
git status
~~~

Nếu đang merge, hoàn tất:

~~~bash
git commit
~~~

GUI có thể hiển thị nút Complete Merge hoặc Commit Merge. Nút đó tạo merge commit sau khi mọi conflict được giải quyết và stage.

### Phân biệt merge conflict với rebase conflict

Cả merge và rebase đều có thể yêu cầu giải quyết conflict, nhưng trạng thái và bước tiếp theo khác nhau.

| Trường hợp | Sau khi sửa và stage |
|---|---|
| Merge conflict | Tiếp tục bằng `git commit` nếu merge chưa tự commit |
| Rebase conflict | Chạy `git rebase --continue` |
| Cherry-pick conflict | Chạy `git cherry-pick --continue` |

Hủy thao tác đang diễn ra bằng lệnh tương ứng:

~~~bash
git merge --abort
git rebase --abort
git cherry-pick --abort
~~~

Một GUI có thể dùng nút Abort, Continue hoặc Skip. Trước khi chọn Skip trong rebase/cherry-pick, hiểu rằng thao tác đó bỏ commit đang được áp dụng; không dùng nó như nút Resolve.

### Nếu Merge Editor và terminal hiển thị khác nhau

Có thể IDE chưa lưu file Result, chưa mark resolved hoặc chưa refresh index. Kiểm tra:

~~~bash
git status
git ls-files -u
git diff
git diff --cached
~~~

Nếu `git ls-files -u` còn kết quả, index vẫn chứa conflict stages. Lưu file, stage lại và refresh GUI.

Không chỉnh sửa trực tiếp các marker conflict trong terminal rồi đồng thời tiếp tục bấm chọn phiên bản trong Merge Editor. Chọn một cách giải quyết tại một thời điểm, lưu kết quả, stage và kiểm tra lại.

## Sử dụng terminal tích hợp trong IDE

Hầu hết IDE có terminal tích hợp. Terminal này thường chạy shell tại thư mục project hoặc thư mục được cấu hình.

Trước khi chạy lệnh:

~~~bash
pwd
git rev-parse --show-toplevel
git status -sb
~~~

Trên PowerShell, dùng `Get-Location` thay cho `pwd` nếu muốn xem thông tin theo cách của PowerShell; lệnh Git vẫn hoạt động như bình thường.

Terminal tích hợp giúp:

- Chạy lệnh Git không có nút tương ứng trong giao diện.
- Xem thông báo lỗi nguyên bản.
- Chạy script, test và build.
- Kiểm tra cấu hình và remote.
- Sao chép lệnh tái hiện lỗi vào báo cáo.

Nhớ rằng terminal tích hợp có thể mở ở thư mục con. Git sẽ tìm repository cha gần nhất, nhưng trong workspace nhiều repository, hãy xác minh root trước khi chạy lệnh ghi.

## Thiết lập Git executable và credential trong IDE

Một IDE có thể dùng:

- Git cài trên hệ điều hành.
- Git đi kèm ứng dụng.
- Git được chọn trong cấu hình IDE.

Nếu CLI và IDE cho kết quả khác nhau, kiểm tra đường dẫn executable và phiên bản:

~~~bash
git --version
where.exe git
~~~

Trên Windows PowerShell hoặc CMD, `where.exe git` hiển thị các executable Git có trong PATH. Trên macOS/Linux, dùng `which git` để xem executable được shell tìm thấy. Trong IDE, mở phần Settings/Preferences về Version Control hoặc Git để xem đường dẫn Git được cấu hình.

Khác biệt phiên bản có thể làm một tùy chọn chưa được hỗ trợ hoặc cách hiển thị thay đổi. Đừng thay Git executable trong IDE chỉ để thử ngẫu nhiên trên repository đang có thao tác dở dang.

### Credential và SSH agent

Terminal và IDE có thể sử dụng cơ chế xác thực khác nhau. Ví dụ:

- Terminal dùng SSH agent đã nạp key.
- IDE dùng credential manager hoặc tài khoản đã đăng nhập.
- Git for Windows dùng credential helper riêng.
- Môi trường CI dùng token hoặc deploy key.

Kiểm tra remote URL:

~~~bash
git remote -v
~~~

Kiểm tra cấu hình credential helper mà không in secret:

~~~bash
git config --show-origin --get-all credential.helper
~~~

Không chia sẻ log chứa token, mật khẩu, private key hoặc HTTP authorization header. Nếu terminal push được nhưng IDE báo authentication failed, kiểm tra tài khoản và credential provider IDE đang sử dụng thay vì thay đổi remote URL bằng cách nhúng token.

## Hook và tự động hóa có thể chạy trong cả GUI lẫn CLI

Khi Git thực hiện commit, push hoặc thao tác có hook, hook có thể được gọi dù lệnh xuất phát từ terminal hay GUI, miễn là công cụ dùng Git và không bỏ qua hook.

Ví dụ pre-commit có thể chạy formatter hoặc test. Nếu commit từ IDE thất bại nhưng terminal thành công, hoặc ngược lại, hãy đọc output của hook và so sánh môi trường:

- PATH có chứa công cụ cần thiết không?
- Shell hoặc runtime có giống nhau không?
- IDE có mở đúng repository không?
- File đã được stage chưa?
- GUI có bật tùy chọn bỏ qua hook không?
- Git executable có trỏ tới cùng bản cài đặt không?

Một số ứng dụng có thể thực hiện commit qua thư viện riêng hoặc có tùy chọn bỏ qua hook. Vì vậy, hãy xác minh hành vi của công cụ đang dùng thay vì mặc định mọi nút Commit đều chạy cùng một chuỗi lệnh.

## Quy trình phối hợp mẫu cho một tính năng

Giả sử bạn phát triển tính năng kiểm tra thanh toán và muốn dùng terminal cùng IDE.

### Bước 1: Xác nhận repository và nhánh

Trong terminal tích hợp:

~~~bash
git rev-parse --show-toplevel
git status -sb
git switch -c feature/payment-validation
~~~

Trong IDE, xác nhận branch selector đang hiển thị `feature/payment-validation`.

### Bước 2: Chỉnh sửa trong IDE

Sửa `PaymentService.java` và thêm `PaymentValidator.java`. Dùng IDE để điều hướng mã nguồn, chạy test và xem lỗi biên dịch.

### Bước 3: Review thay đổi bằng GUI và CLI

Trong GUI, xem các file dưới Changes và đọc diff. Sau đó kiểm tra bằng terminal:

~~~bash
git status --short
git diff
git diff --check
~~~

Xác nhận không có log, file build sinh tự động hoặc cấu hình máy cá nhân.

### Bước 4: Stage có chọn lọc

Nếu cả hai file thuộc cùng tính năng:

~~~bash
git add src/PaymentService.java src/PaymentValidator.java
~~~

Nếu chỉ một phần file cần commit, dùng Stage Hunk trong IDE hoặc:

~~~bash
git add -p src/PaymentService.java
~~~

Kiểm tra:

~~~bash
git diff --cached
git diff
~~~

### Bước 5: Commit

Có thể commit trong IDE hoặc terminal:

~~~bash
git commit -m "feat(payment): validate payment amount"
~~~

Xác minh:

~~~bash
git show --stat --oneline HEAD
git status -sb
~~~

### Bước 6: Fetch, cập nhật và push

~~~bash
git fetch origin
git log --graph --oneline --decorate --all
~~~

Nếu nhóm yêu cầu cập nhật nhánh từ main bằng rebase:

~~~bash
git rebase origin/main
~~~

Giải quyết conflict bằng Merge Editor hoặc terminal. Sau khi rebase hoàn tất, kiểm tra test và lịch sử rồi push:

~~~bash
git push -u origin feature/payment-validation
~~~

Nếu nhánh đã được push trước khi rebase và lịch sử bị viết lại, cần làm theo quy ước nhóm; không force push nhánh đang được người khác sử dụng khi chưa phối hợp.

## Quy trình chẩn đoán khi GUI và CLI không đồng nhất

Khi trạng thái hiển thị khác nhau, kiểm tra theo thứ tự:

1. **Đúng repository chưa?** Xem đường dẫn project, repository selector và `git rev-parse --show-toplevel`.
2. **GUI đã refresh chưa?** Làm mới Git Changes hoặc History.
3. **Index có khác working tree không?** Chạy `git status`, `git diff` và `git diff --cached`.
4. **Có thao tác đang dang dở không?** Kiểm tra trạng thái merge, rebase hoặc cherry-pick trong `git status`.
5. **Git executable có giống nhau không?** So sánh phiên bản và đường dẫn.
6. **Có hook hoặc credential provider khác nhau không?** Đọc output và kiểm tra cấu hình.
7. **Có file bị ignore hoặc filter không?** Kiểm tra `git check-ignore -v <path>` và attributes nếu file không xuất hiện như mong đợi.

Một số lệnh kiểm tra bổ sung:

~~~bash
git status
git diff --name-status
git diff --cached --name-status
git branch -vv
git remote -v
git config --show-origin --show-scope --list
~~~

Trước khi chia sẻ output cấu hình, hãy che URL có thông tin xác thực và các giá trị nhạy cảm.

## Những lỗi thường gặp khi dùng nhiều giao diện

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| IDE không thấy commit vừa tạo trong terminal | Mở nhầm repository hoặc History chưa refresh | Kiểm tra repository root và làm mới |
| Terminal báo file staged nhưng GUI vẫn hiện Changes | IDE chưa cập nhật index hoặc file còn phần unstaged | Refresh và xem cả Staged/Unstaged |
| GUI commit nhiều file hơn dự định | Đã chọn Stage All hoặc bật commit cả file chưa review | Kiểm tra danh sách staged và diff trước commit |
| Nút Commit bị vô hiệu hóa | Chưa stage file hoặc thiếu commit message | Xem trạng thái và yêu cầu của công cụ |
| Commit thành công nhưng Push thất bại | Commit local đã tạo, remote từ chối push | Kiểm tra branch/upstream, quyền và lịch sử remote |
| IDE và terminal dùng phiên bản Git khác | IDE trỏ tới Git executable khác | Kiểm tra cấu hình executable và phiên bản |
| Hook chạy ở terminal nhưng lỗi trong IDE | PATH, shell hoặc runtime khác nhau | Chuẩn hóa môi trường và xem output hook |
| Merge Editor báo resolved nhưng Git còn conflict | File chưa stage hoặc index chưa cập nhật | Chạy `git ls-files -u`, stage lại file |
| Pull trong GUI tạo merge commit ngoài dự kiến | Pull dùng cấu hình merge thay vì rebase | Fetch trước và chọn chiến lược rõ ràng |
| Sync vừa pull vừa push ngoài dự kiến | Nút Sync thực hiện nhiều bước | Dùng Fetch, Pull và Push riêng khi cần kiểm soát |

## Thói quen an toàn khi phối hợp CLI, GUI và IDE

- Xác nhận repository root và branch trước thao tác ghi.
- Đọc diff staged trước mỗi commit.
- Hiểu sự khác nhau giữa Working Tree, Index và HEAD.
- Không bấm Stage All hoặc Commit & Push khi chưa xem phạm vi.
- Làm mới GUI sau thao tác trong terminal.
- Không chạy đồng thời merge, rebase, checkout hoặc commit ở nhiều ứng dụng.
- Dùng terminal để kiểm tra trạng thái khi giao diện chưa rõ.
- Đọc kỹ hộp thoại Stash, Discard, Force Checkout và Abort.
- Kiểm tra hook, Git executable và credential provider khi hành vi khác nhau.
- Dùng Fetch trước khi quyết định Pull/Rebase nếu cần xem remote thay đổi.
- Không chia sẻ log hoặc cấu hình có secret.
- Tuân thủ quy ước branch, review và push của nhóm.

## Ghi nhớ

Terminal, GUI và IDE là các giao diện cùng thao tác trên một repository Git. GUI giúp quan sát diff, stage hunk, lịch sử và conflict trực quan; IDE đặt Git cạnh mã nguồn và công cụ build; terminal cho phép kiểm tra trạng thái và thực hiện thao tác chính xác, có thể lặp lại. Muốn phối hợp an toàn, hãy luôn phân biệt working tree, index và commit, xác nhận đúng repository/branch, review staged diff trước commit, hiểu nút Pull/Sync sẽ thực hiện gì và dùng `git status` để kiểm chứng khi giao diện chưa rõ. Một giao diện tốt hỗ trợ thao tác; trạng thái Git và kết quả lệnh mới là căn cứ để xác nhận thay đổi đã được ghi nhận như mong muốn.


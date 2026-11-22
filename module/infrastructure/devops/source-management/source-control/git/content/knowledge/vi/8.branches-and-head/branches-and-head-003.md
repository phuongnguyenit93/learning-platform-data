# Chuyển nhánh bằng git switch và git checkout

Trong Git, branch là một tên tham chiếu tới commit, còn HEAD cho biết vị trí làm việc hiện tại. Khi chuyển sang branch khác, Git cập nhật HEAD và đồng bộ working tree cùng index theo snapshot của branch đích. Hai lệnh thường gặp cho thao tác này là `git switch` và `git checkout`.

`git switch` được thiết kế tập trung vào việc chuyển branch hoặc chuyển HEAD sang một commit. `git checkout` là lệnh lâu đời hơn, có thể chuyển branch, checkout commit, tạo branch và khôi phục nội dung file. Vì `git checkout` đảm nhiệm nhiều việc, người mới dễ nhầm cú pháp chuyển nhánh với cú pháp khôi phục file. Hiểu điểm khác nhau giúp chọn lệnh rõ mục đích và tránh vô tình ghi đè thay đổi trong working tree.

Sau bài này, bạn có thể:

- Chuyển branch bằng `git switch` và `git checkout`.
- Tạo branch mới đồng thời chuyển sang branch đó.
- Theo dõi remote branch khi chuyển branch.
- Chuyển sang commit cụ thể và hiểu trạng thái detached HEAD.
- Xử lý thay đổi local trước khi chuyển branch.
- Hiểu khi nào Git từ chối chuyển nhánh vì có nguy cơ ghi đè dữ liệu.
- Phân biệt cú pháp checkout branch với checkout path.
- Dùng `git restore` cho thao tác khôi phục file trong Git hiện đại.

## 1. HEAD và branch hiện tại

Một branch trong Git thường là một ref trỏ tới commit mới nhất của nhánh. HEAD thường trỏ gián tiếp tới branch hiện tại:

~~~text
HEAD
  |
  v
refs/heads/feature/search
  |
  v
commit C3
  |
  v
commit C2
~~~

Khi bạn tạo commit mới trên branch đang checkout, ref branch được cập nhật để trỏ tới commit mới và HEAD vẫn gắn với branch đó.

Kiểm tra branch hiện tại:

~~~bash
git branch --show-current
git status --short --branch
~~~

Kiểm tra HEAD:

~~~bash
git rev-parse --short HEAD
git log -1 --oneline
~~~

Khi chuyển branch, Git thay đổi branch mà HEAD đang theo dõi, rồi cập nhật index và working tree cho phù hợp với snapshot đích.

## 2. Chuyển branch bằng git switch

Từ Git 2.23, `git switch` được bổ sung để cung cấp giao diện rõ ràng hơn cho thao tác chuyển branch. Cú pháp cơ bản:

~~~bash
git switch main
~~~

Lệnh chuyển sang branch có tên `main`. Nếu branch tồn tại và thay đổi local không gây mất dữ liệu, Git cập nhật HEAD, index và working tree.

Chuyển sang branch tính năng:

~~~bash
git switch feature/search
~~~

Xem lại trạng thái:

~~~bash
git status --short --branch
git branch --show-current
~~~

Tên branch phải là ref branch hợp lệ. Nếu branch không tồn tại, Git sẽ báo lỗi trừ khi bạn dùng tùy chọn tạo branch mới hoặc cơ chế đoán branch từ remote phù hợp.

## 3. Chuyển branch bằng git checkout

Trước khi có `git switch`, cách phổ biến để chuyển branch là:

~~~bash
git checkout main
~~~

Lệnh này vẫn được hỗ trợ trong Git hiện đại. Nó thực hiện việc chuyển sang branch tương tự `git switch main`.

Ví dụ:

~~~bash
git checkout feature/search
git status --short --branch
~~~

`git checkout` còn hỗ trợ nhiều chế độ khác như checkout commit, tạo branch, khôi phục file hoặc lấy file từ tree-ish. Vì vậy, cùng một lệnh có thể mang ý nghĩa khác nhau tùy tham số.

Nếu mục đích chỉ là chuyển branch, `git switch` thường dễ đọc và dễ hiểu hơn. Trong repository hoặc script cũ, bạn vẫn có thể gặp `git checkout` và cần nhận diện đúng ngữ cảnh.

## 4. So sánh switch và checkout

| Nhu cầu | git switch | git checkout |
| --- | --- | --- |
| Chuyển sang branch có sẵn | `git switch branch-name` | `git checkout branch-name` |
| Tạo branch mới và chuyển sang đó | `git switch -c new-branch` | `git checkout -b new-branch` |
| Tạo hoặc reset branch rồi chuyển | `git switch -C branch start-point` | `git checkout -B branch start-point` |
| Chuyển sang commit cụ thể, detached HEAD | `git switch --detach commit` | `git checkout --detach commit` |
| Chuyển branch và hợp nhất local changes nếu có xung đột | `git switch --merge branch` | `git checkout -m branch` |
| Khôi phục file từ index hoặc tree | Không hỗ trợ chế độ path | Có, nhưng cú pháp dễ nhầm; Git hiện đại có `git restore` |

Khác biệt chính là phạm vi lệnh. `git switch` chỉ tập trung vào việc di chuyển HEAD giữa branch hoặc commit. `git checkout` vẫn hỗ trợ cả việc khôi phục file nên có nhiều dạng cú pháp hơn.

## 5. Tạo branch mới và chuyển sang branch đó

Nếu branch mới chưa tồn tại:

~~~bash
git switch -c feature/search
~~~

Tùy chọn `-c` tạo branch mới từ commit hiện tại rồi chuyển sang branch đó. Đây là thao tác tương đương với:

~~~bash
git branch feature/search
git switch feature/search
~~~

Cách cũ bằng checkout:

~~~bash
git checkout -b feature/search
~~~

Branch mới mặc định bắt đầu từ HEAD hiện tại, trừ khi bạn chỉ định start point:

~~~bash
git switch -c feature/search main
~~~

Lệnh tạo branch `feature/search` từ `main` rồi chuyển sang branch mới. Start point có thể là branch, tag hoặc commit hợp lệ.

### Tạo lại branch đã tồn tại bằng -C hoặc -B

`-C` của switch và `-B` của checkout có thể tạo branch mới hoặc reset branch đã tồn tại về start point rồi chuyển sang đó:

~~~bash
git switch -C feature/search main
~~~

Tương đương:

~~~bash
git checkout -B feature/search main
~~~

Đây là thao tác có thể di chuyển ref branch đã tồn tại và làm mất đường đi dễ thấy tới commit cũ nếu không còn ref nào giữ commit đó. Chỉ dùng khi bạn chủ động muốn reset branch. Trước khi chạy, kiểm tra branch hiện tại, log và các commit cần giữ.

## 6. Chuyển sang remote-tracking branch

Sau khi fetch, repository có thể có remote-tracking branch như `origin/feature/search`:

~~~bash
git fetch origin
git branch -r
~~~

Nếu muốn tạo local branch theo dõi remote branch:

~~~bash
git switch --track origin/feature/search
~~~

Git tạo local branch tương ứng và cấu hình upstream để biết branch local theo dõi remote branch nào.

Có thể chỉ định rõ tên local branch:

~~~bash
git switch --track -c feature/search origin/feature/search
~~~

Tương đương bằng checkout:

~~~bash
git checkout --track -b feature/search origin/feature/search
~~~

Sau khi chuyển:

~~~bash
git status --short --branch
git branch -vv
~~~

`git branch -vv` hiển thị upstream của từng local branch nếu có.

## 7. Tự động đoán branch từ remote

Khi nhập tên branch không tồn tại ở local nhưng có một remote-tracking branch phù hợp, Git có thể tự tạo local branch theo dõi remote branch đó:

~~~bash
git switch feature/search
~~~

Nếu chỉ có một remote branch phù hợp, Git có thể tạo local branch cùng tên và thiết lập tracking. Hành vi này phụ thuộc vào cấu hình đoán branch và sự mơ hồ giữa các remote.

Tùy chọn `--no-guess` tắt cơ chế đoán:

~~~bash
git switch --no-guess feature/search
~~~

Khi có nhiều remote branch trùng tên, chỉ định remote rõ ràng:

~~~bash
git switch --track origin/feature/search
~~~

Hoặc cấu hình remote mặc định cho việc đoán branch theo quy tắc của nhóm. Đừng phụ thuộc vào việc đoán tự động trong script quan trọng nếu remote hoặc tên branch có thể mơ hồ.

## 8. Chuyển sang commit cụ thể và detached HEAD

Bạn có thể chuyển HEAD tới một commit mà không gắn HEAD với branch:

~~~bash
git switch --detach a1b2c3d
~~~

Hoặc:

~~~bash
git checkout --detach a1b2c3d
~~~

Đây là trạng thái detached HEAD. HEAD trỏ trực tiếp tới commit thay vì trỏ tới một branch:

~~~text
HEAD
 |
 v
commit B

main ------> commit D
~~~

Bạn có thể đọc code, chạy thử hoặc tạo commit tạm trong trạng thái này. Tuy nhiên, commit mới không tự động được một branch giữ lại. Nếu rời detached HEAD và không có ref nào trỏ tới commit đó, commit có thể trở thành unreachable và cuối cùng bị garbage collection dọn.

Nếu muốn giữ thay đổi thử nghiệm, tạo branch trước khi rời:

~~~bash
git switch -c experiment/search
~~~

Lệnh này tạo branch tại commit hiện tại và gắn HEAD vào branch mới. Commit tiếp theo sẽ được giữ trong lịch sử của branch.

## 9. Chuyển branch khi working tree có thay đổi

Git thường cho phép chuyển branch nếu thay đổi local không bị branch đích ghi đè. Ví dụ, bạn sửa một file không khác nhau giữa hai branch; Git có thể giữ thay đổi đó khi chuyển branch.

Tuy nhiên, nếu branch đích cần cập nhật cùng file theo cách xung đột với thay đổi local, Git thường từ chối chuyển branch để bảo vệ dữ liệu.

Kiểm tra trước:

~~~bash
git status
git diff
git diff --cached
~~~

Nếu muốn chuyển branch an toàn, có ba lựa chọn thường gặp:

1. Commit thay đổi nếu chúng đã hoàn chỉnh.
2. Stash thay đổi nếu cần cất tạm.
3. Hoàn tác thay đổi nếu bạn chắc chắn không cần giữ.

### Commit trước khi chuyển

~~~bash
git add -A
git commit -m "Save current search work"
git switch main
~~~

### Stash trước khi chuyển

~~~bash
git stash push -m "WIP search changes"
git switch main
~~~

Khi quay lại branch cũ:

~~~bash
git switch feature/search
git stash list
git stash pop
~~~

`git stash pop` áp dụng stash và xóa stash entry nếu áp dụng thành công. Nếu muốn giữ stash để có thể áp dụng lại, dùng `git stash apply`.

### Hoàn tác thay đổi

Nếu thay đổi chưa stage và chắc chắn không cần giữ:

~~~bash
git restore --worktree -- src/Search.java
~~~

Nếu thay đổi đã stage:

~~~bash
git restore --staged --worktree -- src/Search.java
~~~

Lệnh thứ hai đưa cả index và working tree của file về trạng thái nguồn mặc định là HEAD. Hãy xem diff trước khi dùng vì thay đổi local có thể bị loại bỏ.

## 10. Khi Git từ chối chuyển branch

Ví dụ Git báo local changes sẽ bị ghi đè:

~~~text
error: Your local changes to the following files would be overwritten by checkout:
    src/Search.java
Please commit your changes or stash them before you switch branches.
Aborting
~~~

Đây là cơ chế bảo vệ. Git nhận thấy chuyển sang branch đích sẽ ghi nội dung khác lên file đang có thay đổi local.

Quy trình xử lý:

~~~bash
git status --short
git diff
git diff --cached
~~~

Sau đó chọn commit, stash hoặc restore tùy mục tiêu. Không nên cố vượt qua thông báo chỉ để hoàn tất việc chuyển branch nếu chưa biết thay đổi nào sẽ bị ghi đè.

## 11. Dùng --merge khi muốn mang thay đổi local sang branch đích

`git switch --merge` yêu cầu Git thử hợp nhất thay đổi local với nội dung branch đích:

~~~bash
git switch --merge main
~~~

Tùy chọn tương ứng trong checkout là:

~~~bash
git checkout -m main
~~~

Nếu không có xung đột, Git có thể chuyển branch và giữ thay đổi local bằng cách hợp nhất chúng vào working tree. Nếu có conflict, thao tác dừng lại để bạn giải quyết.

Kiểm tra:

~~~bash
git status
git diff
git diff --cached
git ls-files --unmerged
~~~

Sau khi giải quyết conflict, stage kết quả bằng `git add` và tiếp tục công việc trên branch đích. `--merge` không tạo commit tự động.

Chỉ dùng khi bạn chủ động muốn mang thay đổi local qua branch đích và hiểu nội dung cần hợp nhất. Nếu thay đổi chưa sẵn sàng hoặc khó phân biệt, stash thường dễ quản lý hơn.

## 12. Buộc chuyển branch và nguy cơ mất dữ liệu

`git switch --discard-changes` hoặc dạng ngắn `-f` cho phép bỏ thay đổi local đang cản trở chuyển branch:

~~~bash
git switch --discard-changes main
~~~

Trong checkout, có thể dùng:

~~~bash
git checkout -f main
~~~

Các tùy chọn này có thể làm mất thay đổi chưa commit trong working tree và index. Chúng không phải cách sửa lỗi thông thường. Chỉ sử dụng khi bạn đã xác nhận thay đổi local có thể bỏ hoặc đã có bản lưu an toàn.

Trước khi dùng, xem:

~~~bash
git status
git diff
git diff --cached
~~~

Nếu cần giữ bất kỳ phần nào, hãy commit hoặc stash trước. Đừng dùng force switch như một bước thử vận may.

## 13. Cú pháp checkout có thể khôi phục file

Đây là điểm dễ nhầm nhất của `git checkout`. Ngoài chuyển branch, checkout có thể lấy nội dung file từ index hoặc từ một tree-ish.

### Khôi phục file từ index vào working tree

~~~bash
git checkout -- src/Search.java
~~~

Lệnh lấy phiên bản file trong index và ghi vào working tree. Nó loại bỏ sửa đổi chưa stage của file đó. Index không bị thay đổi.

### Lấy file từ một commit vào index và working tree

~~~bash
git checkout HEAD~1 -- src/Search.java
~~~

Lệnh lấy nội dung file từ tree của `HEAD~1`, cập nhật index và working tree cho path đó. Sau đó file trở thành thay đổi staged so với HEAD hiện tại.

### Vì sao cần dấu --

Khi branch và file có tên giống nhau, Git cần phân biệt tên nào là branch và tên nào là path. Dấu `--` phân tách revision/options với path:

~~~bash
git checkout branch-name
git checkout -- branch-name
~~~

Lệnh đầu yêu cầu chuyển branch có tên `branch-name`; lệnh thứ hai yêu cầu khôi phục file có tên đó từ index. Dấu phân cách này giúp cú pháp rõ ràng và tránh diễn giải nhầm.

## 14. Dùng git restore cho thao tác khôi phục file

Git 2.23 bổ sung `git restore` để tách chức năng khôi phục file khỏi `git checkout`.

Khôi phục thay đổi chưa stage từ index:

~~~bash
git restore -- src/Search.java
~~~

Khôi phục file từ một commit cụ thể vào working tree:

~~~bash
git restore --source=HEAD~1 --worktree -- src/Search.java
~~~

Khôi phục index từ HEAD:

~~~bash
git restore --staged -- src/Search.java
~~~

Khôi phục cả index và working tree từ HEAD:

~~~bash
git restore --staged --worktree -- src/Search.java
~~~

`git restore` không chuyển branch và không di chuyển HEAD. Nếu mục tiêu là chuyển branch, dùng `git switch`; nếu mục tiêu là khôi phục file, `git restore` diễn đạt ý định rõ hơn.

## 15. Chuyển branch với tên có thể gây mơ hồ

Trong repository có thể tồn tại branch và file cùng tên. `git checkout` có nhiều chế độ nên việc phân giải tên có thể gây bất ngờ.

Ví dụ:

~~~bash
# Chuyển branch
git switch release

# Khôi phục path tên release từ index
git restore -- release
~~~

Nếu đang dùng checkout:

~~~bash
# Chuyển branch
git checkout release

# Khôi phục file/path
git checkout -- release
~~~

Với cú pháp revision cộng path, dùng dấu phân cách:

~~~bash
git checkout main -- docs/release.md
~~~

Khi viết script hoặc hướng dẫn cho người khác, hãy dùng cú pháp rõ ràng thay vì dựa vào việc Git tự đoán ý định.

## 16. Tạo branch không có lịch sử cha bằng --orphan

Trong một số quy trình đặc biệt, bạn cần tạo branch mới không có commit cha:

~~~bash
git switch --orphan gh-pages
~~~

Hoặc:

~~~bash
git checkout --orphan gh-pages
~~~

Branch orphan bắt đầu ở trạng thái chưa có commit (unborn branch). Index và working tree được chuẩn bị theo hành vi của lệnh và tùy chọn; cần kiểm tra trạng thái trước khi tạo snapshot mới.

~~~bash
git status
git log --oneline
~~~

`git log` có thể không hiển thị commit trên branch orphan cho tới khi bạn tạo commit đầu tiên. Đây không phải branch thông thường tách từ HEAD. Dùng khi cần một lịch sử độc lập, chẳng hạn một nhánh xuất bản chỉ chứa artifact, và phải hiểu rõ nội dung nào sẽ được commit đầu tiên.

## 17. Kiểm tra trước và sau khi chuyển

Một quy trình cơ bản:

~~~bash
# 1. Xác định branch và thay đổi hiện tại
git status --short --branch
git branch --show-current

# 2. Kiểm tra nội dung local
git diff
git diff --cached

# 3. Chuyển branch
git switch main

# 4. Xác nhận branch và working tree
git status --short --branch
git log -1 --oneline
~~~

Nếu cần tạo branch mới:

~~~bash
git switch -c feature/search
~~~

Nếu cần theo dõi remote:

~~~bash
git switch --track origin/feature/search
~~~

Nếu muốn kiểm tra commit cũ:

~~~bash
git switch --detach v1.2.0
~~~

Hãy chọn lệnh theo mục tiêu và xử lý thay đổi local trước khi chuyển.

## 18. Những lỗi thường gặp

### Dùng git checkout mà không biết đang chuyển branch hay khôi phục file

Checkout có nhiều chế độ. Nếu muốn chuyển branch, ưu tiên `git switch`. Nếu muốn khôi phục file, dùng `git restore` hoặc cú pháp checkout có dấu `--`.

### Chuyển branch khi đang có thay đổi chưa commit

Git có thể giữ thay đổi nếu không ghi đè file, nhưng sẽ từ chối nếu có nguy cơ mất dữ liệu. Kiểm tra `git status`, sau đó commit, stash hoặc restore có chủ đích.

### Nghĩ switch luôn xóa thay đổi local

Không đúng. Git thường giữ thay đổi local nếu chúng có thể mang sang branch đích an toàn. Nó từ chối khi cần ghi đè hoặc không thể chuyển trạng thái an toàn.

### Dùng --discard-changes hoặc -f để bỏ qua lỗi

Các tùy chọn này có thể loại bỏ thay đổi chưa commit. Hãy xem diff và lưu thay đổi trước khi dùng.

### Tạo commit trong detached HEAD rồi chuyển branch

Commit có thể không còn được branch nào giữ. Tạo branch bằng `git switch -c new-branch` trước khi rời detached HEAD nếu muốn giữ commit.

### Nhầm branch local với remote-tracking branch

`origin/feature/search` là remote-tracking ref, còn `feature/search` là local branch. Dùng `--track` để tạo local branch theo dõi remote branch.

### Dùng checkout path mà quên dấu --

Tên branch và path có thể trùng nhau. Dùng dấu `--` để phân tách path khỏi revision và option.

## 19. Ghi nhớ

- `git switch branch` là cách rõ ràng để chuyển branch; `git checkout branch` vẫn được hỗ trợ.
- `git switch -c` và `git checkout -b` tạo branch mới rồi chuyển sang đó.
- `-C` và `-B` có thể reset branch đã tồn tại về start point; kiểm tra ref và commit trước khi dùng.
- `--track` tạo local branch theo dõi remote-tracking branch.
- `--detach` chuyển HEAD trực tiếp tới commit; tạo branch nếu muốn giữ commit mới.
- Thay đổi local có thể được giữ khi chuyển branch nếu không bị ghi đè; commit hoặc stash nếu cần bảo toàn chắc chắn.
- `--merge` thử hợp nhất thay đổi local khi chuyển; conflict phải được giải quyết thủ công.
- `--discard-changes` và `-f` có thể làm mất thay đổi chưa commit.
- `git checkout -- path` khôi phục file từ index; `git checkout <tree-ish> -- path` lấy file từ tree vào index và working tree.
- `git restore` là giao diện riêng cho khôi phục file; nó không chuyển branch.
- Dùng `--` để phân tách tên path khỏi revision và option trong cú pháp checkout.

`git switch` giúp thao tác chuyển branch rõ ràng, còn `git checkout` vẫn cần thiết khi đọc hoặc duy trì quy trình Git cũ có nhiều chế độ. Khi phân biệt được việc di chuyển HEAD với việc khôi phục file, kiểm tra local changes trước khi chuyển và hiểu detached HEAD, bạn có thể chuyển ngữ cảnh làm việc an toàn mà không đánh mất thay đổi quan trọng.

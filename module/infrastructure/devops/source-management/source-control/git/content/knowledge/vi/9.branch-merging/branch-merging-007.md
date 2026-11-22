# Trạng thái đang hợp nhất: MERGE_HEAD, chỉ mục và thư mục làm việc

Khi một lệnh merge chưa hoàn tất, trạng thái của repository được thể hiện đồng thời ở nhiều nơi: các pseudo-ref và file trạng thái trong Git directory, index (staging area), working tree và thông tin mà `git status` tổng hợp. Hiểu các thành phần này giúp bạn biết Git đang hợp nhất commit nào, file nào đã được hợp nhất tự động, file nào còn xung đột và khi nào có thể tiếp tục hoặc hủy thao tác.

Một điểm dễ nhầm là “đang merge” không đồng nghĩa với “đang có conflict”. Git có thể đã hợp nhất tất cả file thành công nhưng vẫn chờ bạn tạo merge commit, chẳng hạn khi dùng `--no-commit`. Ngược lại, sau khi bạn giải quyết hết conflict và stage kết quả, repository vẫn ở trạng thái merge cho tới khi merge được hoàn tất.

Sau bài này, bạn có thể:

- Giải thích vai trò của `MERGE_HEAD` và các thông tin trạng thái liên quan.
- Xác định commit đang được merge vào HEAD.
- Đọc các stage trong index và phân biệt file đã hợp nhất với file chưa giải quyết.
- Hiểu nội dung trong working tree khi merge thành công hoặc có conflict.
- Kết hợp `git status`, `git ls-files`, `git diff` và `git rev-parse` để chẩn đoán.
- Hoàn tất merge bằng `git merge --continue` hoặc `git commit`.
- Phân biệt `--abort` với `--quit` và hiểu khác biệt của fast-forward.

## 1. Ba vùng trạng thái trong lúc merge

Một merge ảnh hưởng tới ba thành phần làm việc:

| Thành phần | Vai trò trong merge |
| --- | --- |
| HEAD và merge state | Xác định commit hiện tại và commit được đưa vào; lưu trạng thái để Git biết một merge đang dở. |
| Index | Lưu kết quả đã hợp nhất tự động và các phiên bản cần thiết để giải quyết conflict. |
| Working tree | Chứa nội dung file sau khi merge tự động hoặc nội dung có conflict markers để bạn chỉnh sửa. |

Trong merge hai nhánh thông thường, HEAD vẫn chỉ tới commit của nhánh hiện tại trong suốt lúc merge đang chờ hoàn tất. Commit ở nhánh được merge vào được ghi trong `MERGE_HEAD`. Khi tạo merge commit, commit mới thường có HEAD hiện tại làm parent thứ nhất và commit từ `MERGE_HEAD` làm parent thứ hai.

~~~text
                 merge feature
main:     A---B---C  (HEAD)
                  \
feature:           D---E

Trong lúc merge đang chờ:
HEAD       -> C
MERGE_HEAD -> E
Index      -> kết quả đã merge + các entry conflict
Working tree -> file đã merge hoặc file có conflict

Sau merge commit:
                 M  (HEAD)
                / \
main:     A---B---C   E
                  \ /
feature:           D
~~~

Sơ đồ chỉ minh họa merge hai nhánh. Với octopus merge, có thể có nhiều commit được ghi trong `MERGE_HEAD` và merge commit có nhiều hơn hai parent.

## 2. MERGE_HEAD là gì?

`MERGE_HEAD` là pseudo-ref được Git dùng trong quá trình merge để ghi lại object ID của commit hoặc các commit đang được merge vào HEAD. Với merge hai nhánh thông thường, file này chứa một OID của commit phía incoming.

Ví dụ bạn đang ở `main` và chạy:

~~~bash
git merge feature/search
~~~

Nếu Git bắt đầu một merge thực sự và chưa hoàn tất, `MERGE_HEAD` lưu commit ở đầu `feature/search` được đưa vào. HEAD vẫn trỏ tới commit hiện tại của `main` cho tới khi merge commit được tạo.

`MERGE_HEAD` chứa định danh commit, không phải tên branch. Tên `feature/search` là tên bạn truyền cho lệnh merge; trong quá trình xử lý, Git làm việc với commit mà ref đó phân giải tới.

Kiểm tra trạng thái:

~~~bash
git rev-parse --verify MERGE_HEAD
~~~

Nếu lệnh phân giải được `MERGE_HEAD`, repository có merge state tương ứng. Nếu không phân giải được, có thể không có merge đang chờ hoàn tất hoặc bạn đang ở một trạng thái thao tác khác.

Xem commit incoming:

~~~bash
git show --no-patch --oneline MERGE_HEAD
git show -s --format=fuller MERGE_HEAD
~~~

Để biết Git directory lưu file này ở đâu, dùng:

~~~bash
git rev-parse --git-path MERGE_HEAD
~~~

Không giả định đường dẫn luôn là `.git/MERGE_HEAD`. Linked worktree và các cấu trúc repository đặc biệt có thể đặt Git directory ở vị trí khác.

## 3. Các thông tin trạng thái liên quan

Trong một merge đang dở, bạn có thể gặp các file hoặc ref quản trị sau:

| Tên | Vai trò |
| --- | --- |
| `MERGE_HEAD` | Commit hoặc các commit đang được merge vào HEAD. |
| `MERGE_MSG` | Thông điệp merge được chuẩn bị để dùng khi tạo merge commit. |
| `MERGE_MODE` | Thông tin chế độ merge được Git sử dụng trong một số luồng xử lý. |
| `ORIG_HEAD` | Lưu vị trí HEAD trước một số thao tác làm thay đổi HEAD, trong đó có merge. |
| `AUTO_MERGE` | Ref có thể được tạo bởi merge strategy `ort` khi có conflict, trỏ tới cây kết quả tự động trước khi bạn giải quyết. |

Không phải mọi repository hoặc mọi kiểu merge đều có đủ các file/ref này. Chúng là chi tiết trạng thái do Git quản lý; hãy dùng lệnh Git để kiểm tra thay vì tự sửa hoặc xóa chúng.

### MERGE_MSG

Git có thể chuẩn bị sẵn thông điệp cho merge commit. Xem nội dung commit message sau khi merge được hoàn tất bằng:

~~~bash
git log -1 --format=%B
~~~

Nếu cần xác định vị trí file message trong lúc merge:

~~~bash
git rev-parse --git-path MERGE_MSG
~~~

Khi hoàn tất bằng `git commit`, Git thường mở editor với thông điệp merge mặc định nếu cấu hình và tùy chọn cho phép. Bạn có thể chỉnh sửa thông điệp để giải thích mục đích hợp nhất.

### ORIG_HEAD

`ORIG_HEAD` thường lưu commit mà HEAD trỏ tới trước khi thao tác merge bắt đầu:

~~~bash
git show -s --oneline ORIG_HEAD
~~~

Đây là mốc hữu ích để kiểm tra vị trí ban đầu. Tuy nhiên, `ORIG_HEAD` cũng được các thao tác khác sử dụng, nên không coi nó là bản sao lưu lâu dài hoặc luôn luôn là mốc merge nếu sau đó bạn chạy thêm lệnh làm thay đổi nó.

### AUTO_MERGE

Với merge strategy `ort`, khi có conflict, Git có thể tạo ref `AUTO_MERGE` trỏ tới cây working tree được tạo tự động tại thời điểm conflict. Có thể xem khác biệt giữa trạng thái tự động đó và working tree hiện tại bằng:

~~~bash
git diff AUTO_MERGE
~~~

Lệnh này có thể giúp xem phần bạn đã chỉnh sửa sau khi Git dừng ở conflict. `AUTO_MERGE` không phải ref được tạo trong mọi kiểu merge hoặc mọi phiên bản Git.

## 4. Index lưu kết quả merge như thế nào?

Index không chỉ chứa một phiên bản cho mỗi file trong mọi tình huống. Khi merge thành công tự động cho một path, Git thường ghi kết quả ở stage 0. Khi một path chưa được giải quyết, index có thể giữ nhiều entry ở stage 1, 2 và 3.

| Stage | Ý nghĩa trong merge hai nhánh |
| --- | --- |
| 0 | Phiên bản bình thường đã được stage, không còn unmerged entry cho path đó. |
| 1 | Phiên bản cơ sở chung (merge base). |
| 2 | Phiên bản phía hiện tại (ours), thường lấy từ HEAD trước merge. |
| 3 | Phiên bản phía incoming (theirs), từ commit được merge vào. |

Đối với path đang conflict, stage 0 thường chưa tồn tại. Thay vào đó, Git giữ các stage cần thiết để bạn có thể so sánh nội dung. Không phải conflict nào cũng có đủ stage 1, 2 và 3; ví dụ add/add có thể không có base stage.

Liệt kê các entry unmerged:

~~~bash
git ls-files --unmerged
~~~

Liệt kê toàn bộ index cùng mode, OID và stage:

~~~bash
git ls-files --stage
~~~

Ví dụ một path sửa/sửa:

~~~text
100644 111aaa... 1    src/Search.java
100644 222bbb... 2    src/Search.java
100644 333ccc... 3    src/Search.java
~~~

Kết quả cho biết Git giữ base, phiên bản hiện tại và phiên bản incoming cho `src/Search.java`.

## 5. File đã merge tự động và file còn conflict

Trong một merge có cả file sạch lẫn file xung đột:

- File Git hợp nhất được tự động thường có một entry stage 0 trong index.
- File chưa giải quyết có các entry unmerged ở stage 1/2/3 theo loại conflict.
- Working tree có nội dung kết quả merge cho file sạch.
- Working tree của file xung đột văn bản thường có conflict markers.

Ví dụ:

~~~text
<<<<<<< HEAD
return normalize(query);
=======
return sanitize(query);
>>>>>>> feature/search
~~~

Các marker giúp bạn chỉnh sửa nội dung cuối cùng. Chúng không phải dữ liệu stage 1/2/3; các phiên bản gốc vẫn được giữ trong index cho tới khi bạn stage kết quả giải quyết.

Với file binary hoặc một số conflict về rename/delete, Git không thể chèn marker văn bản theo cách trên. Bạn cần chọn hoặc tạo nội dung cuối cùng bằng công cụ phù hợp, rồi stage kết quả.

## 6. Trạng thái của working tree trong merge

Working tree là nơi bạn nhìn thấy kết quả để review và chỉnh sửa:

- File được merge tự động có nội dung kết hợp.
- File conflict văn bản thường chứa marker.
- File bị xóa ở một phía có thể không còn ở working tree hoặc được giữ lại tùy cách bạn giải quyết.
- File mới được tạo bởi một phía có thể xuất hiện trong working tree.

Xem trạng thái tổng quan:

~~~bash
git status
~~~

Xem thay đổi chưa stage trong working tree:

~~~bash
git diff
~~~

Xem các thay đổi đang có trong index so với HEAD:

~~~bash
git diff --cached
~~~

Với path unmerged, dùng thêm:

~~~bash
git ls-files -u
git diff --cc
~~~

`git diff --cc` hiển thị combined diff cho các file chưa hợp nhất, hữu ích khi muốn review phần conflict cùng các marker. Đọc trực tiếp file trong working tree vẫn cần thiết để hiểu nội dung mà bạn sẽ stage.

## 7. git status cho biết merge đang ở giai đoạn nào

Trong lúc merge, `git status` thường cho biết branch hiện tại, branch được merge và danh sách path cần giải quyết. Ví dụ:

~~~text
On branch main
You have unmerged paths.
  (fix conflicts and run "git commit")

Unmerged paths:
  both modified:   src/Search.java
~~~

Sau khi bạn giải quyết và stage tất cả path conflict, thông báo có thể chuyển thành:

~~~text
All conflicts fixed but you are still merging.
  (use "git commit" to conclude merge)
~~~

Thông báo thứ hai rất quan trọng: index không còn conflict, nhưng merge chưa hoàn tất. `MERGE_HEAD` vẫn tồn tại cho tới khi Git tạo merge commit hoặc bạn hủy/thoát merge state.

Có thể kiểm tra nhanh:

~~~bash
git status --short --branch
git ls-files --unmerged
git rev-parse --verify MERGE_HEAD
~~~

Ba lệnh trả lời ba câu hỏi:

1. Branch và trạng thái file hiện tại là gì?
2. Còn entry conflict trong index không?
3. Git có còn merge state với `MERGE_HEAD` không?

## 8. Merge đang dở không nhất thiết có conflict

Bạn có thể yêu cầu Git dừng trước khi tạo merge commit:

~~~bash
git merge --no-commit --no-ff feature/search
~~~

`--no-commit` yêu cầu dừng trước bước tạo commit để bạn kiểm tra kết quả. `--no-ff` buộc tạo merge commit thay vì fast-forward, vì một fast-forward không có merge commit để dừng trước đó.

Trong trường hợp này:

- Git có thể đã hợp nhất tất cả file tự động.
- `git ls-files --unmerged` có thể không trả kết quả.
- `MERGE_HEAD` vẫn tồn tại vì merge commit chưa được tạo.
- `git status` cho biết bạn vẫn đang trong một merge.

Vì vậy, không dùng riêng `git ls-files -u` để kết luận có merge state hay không. Lệnh đó chỉ cho biết còn unmerged entries hay không.

## 9. Fast-forward khác với merge đang chờ commit

Nếu branch hiện tại là tổ tiên trực tiếp của branch đích, Git có thể fast-forward:

~~~bash
git merge feature/search
~~~

Git chỉ di chuyển ref branch hiện tại tới commit mới hơn. Không cần tạo merge commit và thao tác thường hoàn tất ngay, nên sau khi lệnh kết thúc sẽ không còn `MERGE_HEAD` chờ xử lý.

Nếu muốn buộc tạo merge commit:

~~~bash
git merge --no-ff feature/search
~~~

Nếu muốn dừng trước commit để review:

~~~bash
git merge --no-ff --no-commit feature/search
~~~

| Kiểu merge | Kết quả | Merge state còn chờ sau khi lệnh trả về? |
| --- | --- | --- |
| Fast-forward | Di chuyển branch pointer, không tạo merge commit | Thường không |
| Non-fast-forward hoàn tất tự động | Tạo merge commit | Không |
| Non-fast-forward có `--no-commit` | Index/working tree đã merge, chờ commit | Có |
| Merge có conflict | Dừng để giải quyết | Có |

Đây là lý do cần phân biệt “merge command đã chạy” với “merge operation vẫn đang diễn ra”.

## 10. Kiểm tra commit incoming và mốc ban đầu

Khi đang merge:

~~~bash
# Commit hiện tại trước khi merge commit được tạo
git show -s --oneline HEAD

# Commit incoming
git show -s --oneline MERGE_HEAD

# Mốc HEAD trước thao tác
git show -s --oneline ORIG_HEAD
~~~

Trong merge hai nhánh, `HEAD` thường vẫn là phía current và `MERGE_HEAD` là phía incoming. Khi merge hoàn tất, commit mới sẽ chứa cả hai parent. Kiểm tra parent của commit merge:

~~~bash
git show -s --format=%P HEAD
~~~

Output liệt kê OID các parent của commit hiện tại. Với merge hai nhánh, thường có hai OID; với octopus merge, có thể có nhiều hơn.

Đừng nhầm `FETCH_HEAD` với `MERGE_HEAD`. `FETCH_HEAD` ghi các ref/commit nhận được từ lần fetch gần nhất; `MERGE_HEAD` biểu thị commit đang được merge vào HEAD trong một merge đang dở.

## 11. Đọc nội dung từng phiên bản từ index

Với path có đủ các stage:

~~~bash
# Base
git show :1:src/Search.java

# Ours: phía current
git show :2:src/Search.java

# Theirs: phía incoming
git show :3:src/Search.java
~~~

Nếu stage không tồn tại, lệnh tương ứng sẽ thất bại. Điều này bình thường trong các kiểu conflict không có phiên bản ở một phía.

Trong merge thông thường, stage 2 là phía current và stage 3 là phía incoming. Khi rebase, cách gọi ours/theirs có thể khác trực giác vì Git đang replay commit lên branch đích; bài này tập trung vào merge hai nhánh, vì vậy hãy xác định rõ thao tác đang chạy trước khi chọn nội dung.

## 12. Stage kết quả giải quyết conflict

Sau khi sửa nội dung file trong working tree:

~~~bash
git add src/Search.java
~~~

Git ghi nội dung cuối cùng vào index ở stage 0 và loại các entry unmerged của path đó. Với quyết định xóa file:

~~~bash
git rm -- src/Search.java
~~~

Sau đó kiểm tra:

~~~bash
git ls-files --unmerged
git ls-files --stage -- src/Search.java
git diff --cached
git status
~~~

Nếu `git ls-files --unmerged` không còn liệt kê path, conflict entries của path đó đã được giải quyết. Nếu mọi path đều được xử lý, status sẽ báo tất cả conflict đã được sửa nhưng merge vẫn chờ hoàn tất.

Stage kết quả không tự tạo merge commit. Nó chỉ cập nhật index để Git biết snapshot cuối cùng của từng path.

## 13. Hoàn tất merge

Khi tất cả conflict đã được giải quyết và bạn đã review index:

~~~bash
git status
git diff --cached
git ls-files --unmerged
~~~

Hoàn tất bằng:

~~~bash
git merge --continue
~~~

Hoặc tạo commit trực tiếp:

~~~bash
git commit
~~~

`git merge --continue` yêu cầu Git tiếp tục thao tác merge đang dở. Trong một merge thông thường, lệnh sẽ tạo merge commit sau khi index không còn conflict. `git commit` cũng có thể kết thúc merge bằng cách tạo commit từ index và merge metadata đang có.

Sau khi hoàn tất:

~~~bash
git status --short --branch
git log -1 --oneline --decorate
git show -s --format=%P HEAD
git rev-parse --verify MERGE_HEAD
~~~

Merge state đã được dọn khi commit thành công; `MERGE_HEAD` không còn phân giải được. Commit mới có các parent phản ánh lịch sử được hợp nhất.

## 14. Hủy merge bằng git merge --abort

Nếu muốn bỏ merge đang dở và quay lại trạng thái trước khi bắt đầu:

~~~bash
git merge --abort
~~~

Git cố gắng khôi phục index và working tree về trạng thái trước merge. Sau đó kiểm tra:

~~~bash
git status --short --branch
git log -1 --oneline
git rev-parse --verify MERGE_HEAD
~~~

Nếu merge bắt đầu khi working tree đã có thay đổi chưa commit, việc khôi phục có thể không tái tạo hoàn hảo các thay đổi đó trong mọi trường hợp. Vì vậy, nên commit hoặc stash công việc local trước khi merge nếu cần bảo toàn chắc chắn.

`--abort` là lựa chọn khi bạn muốn hủy kết quả merge và trở về trạng thái ban đầu. Không xóa thủ công `MERGE_HEAD` hoặc các file trạng thái để thay thế lệnh này.

## 15. Thoát merge state bằng git merge --quit

`git merge --quit` có mục đích khác:

~~~bash
git merge --quit
~~~

Lệnh quên trạng thái merge đang diễn ra nhưng giữ nguyên index và working tree. Nó không khôi phục file về trước merge và không tự giải quyết conflict.

Sau `--quit`, bạn có thể vẫn còn nội dung merge trong working tree hoặc unmerged entries trong index, nhưng Git không còn xem thao tác đó là merge đang chờ tiếp tục. Vì vậy:

| Lệnh | Tác động |
| --- | --- |
| `git merge --continue` | Tiếp tục và hoàn tất merge đang dở. |
| `git merge --abort` | Cố gắng quay về trạng thái trước khi merge. |
| `git merge --quit` | Xóa merge state, giữ nguyên index và working tree hiện tại. |

Chỉ dùng `--quit` khi bạn có chủ đích giữ nguyên trạng thái file nhưng không muốn tiếp tục phiên merge theo cơ chế merge hiện tại. Nó không phải cách dọn conflict thông thường.

## 16. Không tự sửa file trạng thái trong Git directory

Khi merge đang dở, tránh:

- Xóa `MERGE_HEAD` bằng công cụ hệ thống tệp.
- Tự sửa OID bên trong `MERGE_HEAD`.
- Xóa `MERGE_MSG`, `ORIG_HEAD` hoặc file index để “làm sạch” trạng thái.
- Chép file `.git/index` từ một repository khác.

Các file này phối hợp với nhau để Git hiểu trạng thái hiện tại. Can thiệp thủ công có thể làm Git mất khả năng tiếp tục hoặc hủy merge đúng cách.

Hãy dùng các lệnh cấp cao:

~~~bash
git status
git merge --continue
git merge --abort
git merge --quit
~~~

Nếu nghi ngờ repository hỏng, ghi lại output chẩn đoán và tạo bản sao an toàn trước khi thử sửa chữa.

## 17. Phân biệt merge với các thao tác đang dở khác

Git có nhiều pseudo-ref cho các thao tác khác nhau:

| Tên | Thao tác liên quan |
| --- | --- |
| `MERGE_HEAD` | Merge commit hoặc các commit đang được merge vào HEAD. |
| `CHERRY_PICK_HEAD` | Commit đang được cherry-pick. |
| `REVERT_HEAD` | Commit đang được revert. |
| `REBASE_HEAD` | Commit đang được replay trong một số trạng thái rebase. |

Khi `git status` báo một thao tác đang dở, hãy đọc thông báo cụ thể. Không suy luận mọi conflict đều là merge; cherry-pick, revert và rebase cũng có thể tạo unmerged entries trong index.

Kiểm tra merge state:

~~~bash
git rev-parse --verify -q MERGE_HEAD
~~~

Kiểm tra cherry-pick state:

~~~bash
git rev-parse --verify -q CHERRY_PICK_HEAD
~~~

Các lệnh có thể trả mã thoát khác 0 nếu pseudo-ref không tồn tại. Dùng exit code trong script thay vì chỉ kiểm tra chuỗi output.

## 18. Quy trình chẩn đoán merge đang dở

Khi Git dừng giữa merge, hãy kiểm tra theo thứ tự:

~~~bash
# 1. Tổng quan branch và file
git status --short --branch

# 2. Xác định merge state
git rev-parse --verify MERGE_HEAD

# 3. Xem commit incoming
git show -s --oneline MERGE_HEAD

# 4. Liệt kê path chưa giải quyết
git ls-files --unmerged

# 5. Xem các thay đổi trong index và working tree
git diff --cached
git diff

# 6. Kiểm tra file trạng thái nếu cần
git rev-parse --git-path MERGE_HEAD
git rev-parse --git-path MERGE_MSG
git rev-parse --git-path ORIG_HEAD
~~~

Sau đó chọn hướng xử lý:

- Còn conflict: chỉnh sửa working tree, `git add` hoặc `git rm`, rồi kiểm tra lại.
- Không còn conflict nhưng merge vẫn dở: review staged diff rồi `git merge --continue` hoặc `git commit`.
- Muốn quay lại trước merge: `git merge --abort`.
- Muốn giữ nguyên index/working tree nhưng bỏ merge state: chỉ dùng `git merge --quit` khi đã hiểu hệ quả.

Sau mỗi thao tác, chạy lại `git status` và kiểm tra `MERGE_HEAD` để xác nhận trạng thái thực tế.

## 19. Những lỗi thường gặp

### Thấy git ls-files -u rỗng và nghĩ merge đã hoàn tất

Lệnh chỉ cho biết index không còn unmerged entries. `MERGE_HEAD` vẫn có thể tồn tại nếu merge đang chờ commit, ví dụ sau `--no-commit`.

### Nghĩ MERGE_HEAD chứa tên branch

`MERGE_HEAD` chứa object ID của commit được merge vào, không phải tên branch người dùng đã nhập.

### Nghĩ mọi merge đều tạo MERGE_HEAD kéo dài sau lệnh

Fast-forward cập nhật branch pointer và thường kết thúc ngay, không để lại merge state chờ commit. Merge commit hoặc merge bị dừng giữa chừng mới có trạng thái đang chờ.

### Đã stage hết conflict nhưng vẫn thấy “still merging”

Đây là trạng thái bình thường. Bạn đã giải quyết conflict nhưng cần tạo merge commit bằng `git merge --continue` hoặc `git commit`.

### Dùng git merge --quit để hoàn tác merge

`--quit` chỉ quên merge state, không khôi phục index hoặc working tree. Dùng `--abort` nếu muốn hủy merge và quay lại trạng thái trước đó.

### Xóa MERGE_HEAD bằng tay

Điều này có thể làm trạng thái repository không nhất quán. Dùng `git merge --continue`, `--abort` hoặc `--quit`.

### Cho rằng stage 1/2/3 luôn có đủ

Các kiểu conflict add/add, modify/delete và rename có thể thiếu một hoặc nhiều stage. Đọc những entry thực tế trong `git ls-files --unmerged`.

## 20. Ghi nhớ

- `MERGE_HEAD` ghi object ID của commit hoặc các commit đang được merge vào HEAD.
- Trong merge hai nhánh đang dở, HEAD thường ở commit current; incoming commit được lưu trong `MERGE_HEAD`.
- `MERGE_MSG` giữ thông điệp merge được chuẩn bị; `ORIG_HEAD` thường lưu mốc HEAD trước thao tác; `AUTO_MERGE` có thể xuất hiện với strategy `ort`.
- Index dùng stage 0 cho entry bình thường và stage 1/2/3 cho các phiên bản liên quan tới conflict.
- File sạch được merge tự động thường có stage 0; file conflict có unmerged entries và working tree có thể chứa conflict markers.
- `git status` cho biết merge state; `git ls-files -u` chỉ kiểm tra conflict entries, không chứng minh merge đã hoàn tất.
- Merge có thể đang chờ commit dù không có conflict, chẳng hạn khi dùng `--no-commit --no-ff`.
- Fast-forward thường kết thúc ngay và không để lại `MERGE_HEAD` chờ xử lý.
- `git merge --continue` hoặc `git commit` hoàn tất merge; `git merge --abort` cố gắng khôi phục trạng thái trước merge; `git merge --quit` chỉ quên merge state và giữ nguyên index/working tree.
- Dùng `git rev-parse --git-path` để tìm file trạng thái, không hard-code `.git`.
- Không chỉnh sửa hoặc xóa file trạng thái merge thủ công.

Trạng thái merge là sự phối hợp giữa `MERGE_HEAD`, index và working tree. `MERGE_HEAD` cho biết commit incoming, index cho biết phiên bản nào đã được hợp nhất hoặc còn xung đột, còn working tree là nơi bạn review và hoàn thiện nội dung. Khi kiểm tra cả ba cùng với `git status`, bạn có thể biết chính xác merge đang ở giai đoạn nào và chọn cách tiếp tục, hủy hoặc thoát phù hợp.

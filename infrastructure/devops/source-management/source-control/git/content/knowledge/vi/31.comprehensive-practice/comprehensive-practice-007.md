# Chuyển bản sửa và hoàn tác an toàn trên lịch sử đã chia sẻ

Trong quá trình cộng tác, một bản sửa có thể được tạo ở nhánh chưa đúng, cần đưa sang nhánh phát hành hoặc đã được push lên branch dùng chung nhưng sau đó phát hiện lỗi. Cách xử lý phụ thuộc vào việc thay đổi đã thành commit chưa, commit đã được chia sẻ chưa và bạn muốn **chuyển thay đổi** hay **đảo ngược tác động** của nó.

Bài thực hành này kết hợp ba thao tác quan trọng:

- **Cherry-pick** để đưa thay đổi của một commit sang branch khác bằng cách tạo commit mới.
- **Revert** để hoàn tác tác động của commit đã chia sẻ mà vẫn giữ nguyên lịch sử cũ.
- **Reset/restore/stash** để xử lý thay đổi local trước khi chuyển branch hoặc sửa lịch sử riêng tư.

Nguyên tắc xuyên suốt là kiểm tra trạng thái và lịch sử trước khi thao tác, bảo toàn công việc local, rồi xác minh kết quả sau mỗi bước.

## 1. Bắt đầu bằng việc xác định trạng thái repository

Trước khi chuyển commit hoặc hoàn tác, hãy xác định branch hiện tại, thay đổi chưa commit và các commit gần nhất:

```bash
git status --short --branch
git branch --show-current
git log --oneline --decorate --graph --all -15
```

Ba lệnh trả lời những câu hỏi khác nhau:

- `git status` cho biết working tree và index có thay đổi hoặc conflict không.
- `git branch --show-current` cho biết branch local hiện tại; kết quả rỗng có thể là detached HEAD.
- `git log` cho thấy các commit gần đây và quan hệ branch/merge trong phạm vi refs đã fetch.

Cập nhật thông tin remote trước khi so sánh với branch dùng chung:

```bash
git fetch origin
```

`fetch` cập nhật remote-tracking refs như `origin/main`, không tự merge hoặc rebase branch hiện tại. Sau đó, xem các commit chỉ có ở một phía:

```bash
git log --oneline --left-right --graph origin/main...HEAD
```

Dấu `<` và `>` giúp phân biệt commit chỉ reachable từ phía trái và phía phải của phép so sánh. Thay `origin/main` bằng remote-tracking branch thực tế của nhóm.

Nếu working tree có thay đổi, đừng bắt đầu cherry-pick, revert hoặc chuyển branch một cách vội vàng. Hãy xem diff và quyết định commit, stash hoặc xử lý riêng những thay đổi đó trước.

## 2. Chọn cách chuyển hoặc hoàn tác phù hợp

Không phải mọi tình huống đều cần cùng một lệnh:

| Tình huống | Thao tác thường phù hợp | Tác động lên lịch sử |
|---|---|---|
| Commit đã có ở branch A, cần đưa bản sửa sang branch B | `git cherry-pick` | Tạo commit mới trên branch B |
| Commit sai đã push lên branch dùng chung | `git revert` | Tạo commit mới đảo ngược tác động |
| Muốn bỏ commit chưa chia sẻ trên branch riêng | `git reset` | Di chuyển branch ref; có thể thay đổi index/working tree |
| Muốn bỏ stage một file | `git restore --staged` | Không thay đổi commit |
| Muốn bỏ thay đổi chưa stage trong file | `git restore` | Ghi đè thay đổi local của file |
| Cần cất thay đổi chưa commit để đổi branch | `git stash` | Lưu tạm thay đổi trong repository local |

Một câu hỏi quan trọng là commit đã được chia sẻ chưa. Nếu commit đã push lên branch mà người khác đang dựa vào, ưu tiên revert để công bố một commit mới. Nếu commit chỉ nằm trên branch riêng và chưa chia sẻ, reset có thể phù hợp khi bạn muốn chỉnh lại lịch sử.

## 3. Chuyển một commit sang branch khác bằng cherry-pick

Giả sử bạn sửa lỗi đăng nhập trên branch `feature/login`, tạo commit `F1`, nhưng bản sửa cần được đưa sang branch bảo trì `release/2.x`.

Lịch sử ban đầu:

```text
main:        A --- B
                  \
feature/login:     C --- F1

release/2.x: R1 --- R2
```

Mục tiêu là đưa nội dung thay đổi của `F1` lên branch phát hành mà không merge toàn bộ branch `feature/login`.

Trước hết, xác định commit cần chuyển:

```bash
git log --oneline --decorate feature/login
git show --stat --oneline <fix-commit>
```

Thay `<fix-commit>` bằng OID thực tế của commit sửa lỗi. Đọc diff trước khi áp dụng để chắc chắn commit không chứa thay đổi ngoài phạm vi.

Fetch và tạo branch công việc từ branch phát hành mới nhất:

```bash
git fetch origin
git switch -c hotfix/login origin/release/2.x
```

Nếu branch `hotfix/login` đã tồn tại, không dùng `-c` để tạo lại. Hãy kiểm tra branch đó có đúng là branch bạn muốn tiếp tục hay không.

Áp dụng commit:

```bash
git cherry-pick -x <fix-commit>
```

`git cherry-pick` lấy thay đổi do commit nguồn giới thiệu và áp dụng lên HEAD hiện tại. Git tạo một commit mới có parent là commit hiện tại của branch đích. OID của commit mới khác OID nguồn vì parent và metadata commit có thể khác.

Tùy chọn `-x` thêm dòng tham chiếu OID commit nguồn vào commit message, hữu ích khi chuyển commit giữa các branch công khai để truy vết nguồn gốc.

Sau khi áp dụng, kiểm tra:

```bash
git status
git log --oneline --decorate -5
git show --stat --oneline HEAD
```

Chạy test phù hợp với branch phát hành rồi mới push branch hotfix:

```bash
git push -u origin hotfix/login
```

Nếu nhóm bảo vệ branch release, hãy mở pull request từ `hotfix/login` vào `release/2.x` theo quy trình của nhóm. Không cần push thẳng vào branch được bảo vệ.

## 4. Chuyển nhiều commit theo đúng thứ tự

Giả sử branch nguồn có ba commit liên tiếp:

```text
base --- C1 --- C2 --- C3
```

Nếu chuyển cả ba commit, cần áp dụng từ cũ tới mới để các commit sau có đủ nền tảng từ commit trước.

Xem danh sách:

```bash
git log --oneline --reverse <base>..<source-branch>
```

Range `<base>..<source-branch>` chọn commit reachable từ source branch nhưng không reachable từ base. Nó không nhất thiết là một đoạn tuyến tính nếu lịch sử có merge.

Sau khi xem danh sách, cherry-pick các OID theo thứ tự từ trên xuống:

```bash
git cherry-pick -x <oid-C1> <oid-C2> <oid-C3>
```

Không sao chép nguyên ví dụ nếu thứ tự hoặc OID thực tế khác. Nếu các commit có merge topology cần giữ, cherry-pick từng commit không tái tạo nguyên cấu trúc branch/merge; hãy cân nhắc merge hoặc phương thức chuyển lịch sử khác.

Có thể dùng `git cherry` để xem commit có thay đổi tương đương đã xuất hiện ở branch đích hay chưa:

```bash
git cherry -v <destination-branch> <source-branch>
```

Dấu `+` thường cho biết patch tương ứng chưa được tìm thấy ở phía đích; dấu `-` cho biết có patch tương đương. Đây là so sánh dựa trên patch equivalence, không khẳng định OID của hai commit giống nhau.

Không cherry-pick mù một commit đã có thay đổi tương đương ở branch đích. Làm vậy có thể tạo thay đổi trùng, conflict hoặc commit rỗng.

## 5. Chọn cherry-pick một phần thay đổi

Đôi khi commit nguồn chứa nhiều file nhưng branch đích chỉ cần một phần nội dung. Có thể dùng:

```bash
git cherry-pick --no-commit <fix-commit>
```

Tùy chọn `--no-commit` áp dụng thay đổi vào index và working tree mà chưa tạo commit. Sau đó xem:

```bash
git status --short
git diff
git diff --cached
```

Bạn có thể điều chỉnh nội dung, stage phần cần giữ và tạo commit theo mục tiêu của branch đích. Lưu ý trạng thái index có thể đã chứa các thay đổi được cherry-pick; hãy kiểm tra kỹ trước khi commit.

Nếu muốn hủy toàn bộ phần đang áp dụng và chưa tạo commit, cách xử lý phụ thuộc trạng thái sequencer và các thay đổi trước đó. Với một cherry-pick đơn đang dở, dùng `git cherry-pick --abort` để hủy thao tác. Nếu lệnh đã hoàn tất với `--no-commit`, hãy kiểm tra `git status` và hoàn nguyên có chọn lọc các thay đổi vừa áp dụng; đừng dùng reset/restore diện rộng khi index hoặc working tree còn chứa công việc khác.

## 6. Xử lý conflict khi cherry-pick

Cherry-pick có thể conflict nếu branch đích đã sửa cùng vùng code hoặc cấu trúc file khác với branch nguồn.

Khi conflict, Git dừng và đánh dấu các đường dẫn chưa hợp nhất. Kiểm tra:

```bash
git status
git diff --name-only --diff-filter=U
```

Mở từng file, đọc các marker conflict và kết hợp nội dung theo yêu cầu của branch đích. Sau đó stage các file đã giải quyết:

```bash
git add -- src/login/Authenticator.java
git status
```

Tiếp tục cherry-pick:

```bash
git cherry-pick --continue
```

Nếu xác định commit hiện tại không cần thiết vì thay đổi đã có hoặc được xử lý theo cách khác, có thể bỏ qua commit đang dừng:

```bash
git cherry-pick --skip
```

Chỉ skip sau khi xác nhận tác động của commit đã được xử lý. Nếu muốn hủy toàn bộ chuỗi cherry-pick đang diễn ra và quay về trạng thái trước khi bắt đầu:

```bash
git cherry-pick --abort
```

Sau khi tiếp tục hoặc abort, kiểm tra `git status` và `git log` để xác nhận sequencer đã kết thúc và branch đang ở đúng trạng thái.

## 7. Cherry-pick merge commit cần chọn mainline

Một merge commit có nhiều parent. Khi cherry-pick merge commit, Git cần biết parent nào được xem là đường cơ sở để xác định phần thay đổi cần áp dụng.

Xem parent:

```bash
git show --no-patch --pretty=raw <merge-commit>
```

Nếu muốn lấy thay đổi của merge commit so với parent thứ nhất, dùng:

```bash
git cherry-pick -m 1 <merge-commit>
```

`-m 1` chọn parent thứ nhất làm mainline. Nếu chọn sai parent, phần diff được áp dụng có thể không phải phần bạn mong muốn.

Trước khi cherry-pick merge commit, hãy kiểm tra graph, parent và diff so với từng parent:

```bash
git diff <merge-commit>^1 <merge-commit>
git diff <merge-commit>^2 <merge-commit>
```

Cherry-pick merge commit chỉ lấy thay đổi tương đối với parent được chọn; nó không tái tạo toàn bộ topology merge. Nếu mục tiêu là tích hợp cả branch với lịch sử của nó, merge branch thường phù hợp hơn.

## 8. Hoàn tác commit đã chia sẻ bằng git revert

Giả sử commit lỗi `B2` đã được push lên `main` và đồng đội có thể đã fetch hoặc tạo branch từ nó:

```text
main: A --- B1 --- B2 (lỗi) --- C
```

Không nên di chuyển branch `main` về `B1` bằng reset rồi force push như một thao tác thông thường. Những người đã lấy `B2` sẽ có lịch sử local không còn khớp với branch remote.

Thay vào đó, tạo một commit mới đảo ngược thay đổi của `B2`:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git revert <bad-commit>
```

Nếu `main` được bảo vệ và thay đổi phải đi qua pull request, tạo branch hoàn tác từ `main` đã cập nhật rồi mới revert:

```bash
git switch -c revert/bad-login
git revert <bad-commit>
git push -u origin revert/bad-login
```

Nếu chính sách cho phép commit trực tiếp trên branch local `main`, có thể revert tại đó rồi push theo quyền được cấp. Luôn tuân thủ quy trình bảo vệ branch của nhóm.

`git revert` không xóa commit cũ. Nó tính thay đổi ngược với commit được chọn và tạo commit mới trên branch hiện tại. Lịch sử có dạng:

```text
main: A --- B1 --- B2 --- C --- R
                                  ^
                         revert B2
```

Commit `R` giữ nguyên lịch sử đã chia sẻ và ghi nhận việc hoàn tác. Nếu branch `main` được bảo vệ, hãy tạo branch hoàn tác và mở pull request theo quy trình nhóm thay vì push trực tiếp.

Kiểm tra diff và test trước khi chia sẻ commit revert:

```bash
git show --stat --oneline HEAD
git show HEAD
git status
```

Sau khi xác nhận, push branch hoặc tạo pull request. Revert an toàn cho lịch sử dùng chung vì các commit cũ vẫn giữ nguyên OID và thứ tự.

## 9. Revert nhiều commit theo thứ tự an toàn

Nếu một chuỗi commit liên tiếp đều cần hoàn tác, nên hiểu quan hệ phụ thuộc giữa chúng. Với các commit `C1`, `C2`, `C3` được áp dụng theo thứ tự đó, thường hoàn tác từ mới nhất về cũ nhất:

```bash
git revert <oid-C3>
git revert <oid-C2>
git revert <oid-C1>
```

Thứ tự ngược giúp gỡ các thay đổi phụ thuộc vào nhau theo trình tự tự nhiên. Tuy nhiên, nếu các commit độc lập hoặc chỉ một phần cần hoàn tác, hãy xem diff và chọn phạm vi cụ thể.

Có thể dùng `--no-commit` để áp dụng các thay đổi ngược vào index/working tree mà chưa tạo commit ngay:

```bash
git revert --no-commit <bad-commit>
```

Sau đó xem và kiểm tra toàn bộ kết quả:

```bash
git status
git diff
git diff --cached
```

Khi nội dung đã đúng, tạo một commit hoàn tác có thông điệp rõ ràng. Cần nhớ `--no-commit` vẫn thay đổi index và working tree; nó không phải chế độ chỉ xem trước.

Không dùng một range revert lớn nếu chưa đọc danh sách commit mà range đó chọn. Trước khi revert hàng loạt, xem graph và xác nhận từng commit thuộc phạm vi thực sự cần đảo ngược.

## 10. Revert merge commit

Hoàn tác merge commit cần chỉ rõ mainline parent, tương tự yêu cầu của cherry-pick merge commit.

Xem các parent:

```bash
git show --no-patch --pretty=raw <merge-commit>
```

Nếu branch chính là parent thứ nhất và mục tiêu là đảo ngược phần thay đổi được đưa vào qua merge so với branch chính:

```bash
git revert -m 1 <merge-commit>
```

`-m 1` chọn parent thứ nhất làm mainline. Hãy xác minh thứ tự parent thay vì mặc định parent 1 luôn là branch mà bạn muốn giữ.

Revert merge commit tạo một commit mới đảo ngược diff giữa merge result và mainline được chọn. Nó không xóa các commit của branch đã merge khỏi lịch sử. Git ghi nhận rằng thay đổi của merge đã bị đảo ngược; nếu sau này merge lại cùng branch, các commit cũ vẫn là ancestor nên Git có thể không đưa lại các thay đổi đã revert. Khi cần áp dụng lại, nhóm thường phải revert commit revert hoặc tạo commit mới chứa phần sửa mong muốn.

Vì tác động này có thể ảnh hưởng những lần merge sau, hãy phối hợp với maintainer và kiểm tra kỹ trước khi revert merge trên branch dùng chung.

## 11. Phân biệt reset, revert và restore

Ba lệnh có tên gần nhau nhưng xử lý các vùng khác nhau:

| Lệnh | Mục đích | Ảnh hưởng lịch sử |
|---|---|---|
| `git reset` | Di chuyển HEAD/branch và tùy chế độ cập nhật index, working tree | Có thể viết lại lịch sử local |
| `git revert` | Tạo commit mới đảo ngược một commit cũ | Giữ nguyên commit đã chia sẻ |
| `git restore` | Khôi phục nội dung file trong index hoặc working tree | Không tạo commit và không di chuyển branch |

Các chế độ reset thường gặp:

```bash
git reset --soft HEAD~1
git reset --mixed HEAD~1
git reset --hard HEAD~1
```

- `--soft`: di chuyển branch/HEAD về commit trước, giữ thay đổi trong index và working tree.
- `--mixed`: di chuyển branch/HEAD và cập nhật index; giữ nội dung file trong working tree. Đây là chế độ mặc định nếu không chỉ định.
- `--hard`: di chuyển branch/HEAD, cập nhật index và ghi lại working tree theo commit đích. Thay đổi tracked chưa commit có thể bị mất; file untracked bị cản trở bởi đường dẫn được checkout cũng có thể bị ghi đè.

Reset phù hợp để chỉnh lịch sử riêng tư chưa chia sẻ, ví dụ gộp lại commit hoặc bỏ commit local chưa push. Không dùng reset để xóa commit đã được nhiều người lấy về branch dùng chung nếu chưa có kế hoạch phối hợp viết lại lịch sử.

`git restore` dùng cho file:

```bash
git restore --staged -- src/App.java
git restore --worktree -- src/App.java
```

Lệnh đầu bỏ stage nội dung của file nhưng giữ thay đổi trong working tree. Lệnh thứ hai khôi phục file trong working tree theo index hiện tại và có thể làm mất phần chỉnh sửa chưa stage của file đó.

Trước khi restore, xem `git diff` hoặc `git diff --cached` để biết nội dung nào sẽ bị thay đổi. Đừng nhầm restore file với revert commit.

## 12. Khi nào reset an toàn và khi nào không?

Có thể dùng reset trên branch local riêng khi commit chưa được chia sẻ và bạn chủ động muốn thay đổi lịch sử.

Ví dụ, bỏ commit cuối nhưng giữ nội dung đã stage để tạo commit mới:

```bash
git reset --soft HEAD~1
git status
```

Hoặc bỏ commit cuối, đưa thay đổi về working tree nhưng unstaged:

```bash
git reset --mixed HEAD~1
git status
```

Nếu commit đã push lên branch dùng chung, reset làm branch local lùi lại nhưng remote vẫn giữ commit cũ. Khi push bình thường, Git thường từ chối vì cập nhật không fast-forward. Dùng force push sẽ thay đổi lịch sử remote và có thể làm mất commit mà người khác đang dựa vào.

Với branch đã chia sẻ, lựa chọn thông thường là `git revert`. Nếu nhóm thật sự cần viết lại lịch sử của một branch riêng, cần thống nhất trước, kiểm tra remote đã cập nhật và dùng `--force-with-lease` thay vì `--force` trần:

```bash
git fetch origin
git push --force-with-lease origin feature/my-private-branch
```

`--force-with-lease` từ chối cập nhật nếu remote branch đã thay đổi khác với giá trị mà lease đang kỳ vọng. Nó giảm nguy cơ ghi đè commit mới của người khác, nhưng không biến việc rewrite branch dùng chung thành an toàn tự động. Chỉ dùng khi branch không phải lịch sử chung ổn định và mọi người liên quan đã phối hợp.

## 13. Bảo toàn thay đổi chưa commit trước khi chuyển branch

Nếu working tree còn thay đổi, bạn có thể commit tạm hoặc stash trước khi chuyển branch.

Kiểm tra trước:

```bash
git status --short
git diff
git diff --cached
```

Nếu cần cất thay đổi cả tracked và untracked:

```bash
git stash push -u -m "WIP before switching branch"
```

`-u` đưa file untracked vào stash; file ignored không được đưa vào stash theo tùy chọn này. Stash là dữ liệu local trong repository, không tự được chia sẻ với đồng đội.

Xem stash:

```bash
git stash list
git stash show --stat stash@{0}
```

Sau khi chuyển sang branch phù hợp, khôi phục:

```bash
git stash apply stash@{0}
```

`apply` giữ stash trong danh sách để bạn kiểm tra kết quả. Khi đã xác nhận nội dung phục hồi đầy đủ, mới xóa stash bằng `git stash drop`. `git stash pop` vừa áp dụng vừa xóa stash nếu áp dụng thành công, vì vậy `apply` thường dễ kiểm soát hơn khi đang bảo toàn công việc.

Nếu muốn tạo branch từ chính trạng thái nền mà stash được tạo và phục hồi thay đổi lên đó:

```bash
git stash branch rescue/wip stash@{0}
```

Lệnh tạo branch từ commit nền của stash, áp dụng thay đổi rồi xóa stash nếu thành công. Kiểm tra kỹ trước khi tiếp tục.

## 14. Khôi phục commit sau khi reset nhầm bằng reflog

Nếu reset nhầm làm branch lùi về commit cũ, commit trước đó thường vẫn có thể tìm qua reflog trong một khoảng thời gian.

Xem lịch sử cập nhật HEAD:

```bash
git reflog --date=local -n 15
```

Ví dụ:

```text
a1b2c3d HEAD@{0}: reset: moving to HEAD~1
e4f5a6b HEAD@{1}: commit: Add login validation
9a8b7c6 HEAD@{2}: checkout: moving from feature/login to main
```

Nếu `e4f5a6b` là commit cần khôi phục, tạo branch cứu hộ trỏ tới commit đó:

```bash
git branch rescue/login-before-reset e4f5a6b
```

Sau đó kiểm tra:

```bash
git log --oneline --decorate -5 rescue/login-before-reset
git show --stat rescue/login-before-reset
```

Reflog là nhật ký local, không được push lên remote và không phải nguồn lưu trữ vĩnh viễn. Các entry cũ có thể hết hạn và object không còn được ref nào giữ có thể bị garbage collection dọn. Khi tìm thấy commit cần giữ, hãy tạo branch hoặc ref cứu hộ ngay.

Nếu commit đã được push trước đó, remote hoặc clone của đồng đội có thể còn giữ OID. Tuy nhiên, không nên dựa vào clone của người khác như phương án backup mặc định.

## 15. Thực hành tích hợp: chuyển hotfix và hoàn tác commit lỗi đã chia sẻ

Tình huống: nhóm phát triển có một commit sửa lỗi đăng nhập trên branch `feature/login`. Branch `release/2.x` cần nhận riêng bản sửa đó. Sau đó, một commit khác đã được merge vào `main` nhưng gây lỗi production và cần được hoàn tác an toàn.

### Phần A — Chuyển hotfix sang branch phát hành

**Bước 1: Xác định commit sửa lỗi.**

```bash
git fetch origin
git log --oneline --decorate origin/feature/login
git show --stat --oneline <fix-commit>
```

Đọc diff để xác nhận commit chỉ chứa bản sửa cần chuyển.

**Bước 2: Tạo branch từ release mới nhất.**

```bash
git switch -c hotfix/login origin/release/2.x
```

**Bước 3: Cherry-pick commit.**

```bash
git cherry-pick -x <fix-commit>
```

Nếu có conflict, giải quyết trong branch hotfix rồi dùng `git cherry-pick --continue`.

**Bước 4: Kiểm tra và chia sẻ.**

```bash
git status
git log --oneline --decorate -5
git show --stat HEAD
git push -u origin hotfix/login
```

Chạy test và mở pull request vào `release/2.x` theo quy trình của nhóm.

### Phần B — Hoàn tác commit lỗi trên branch dùng chung

**Bước 1: Cập nhật branch main.**

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c revert/bad-commit
```

**Bước 2: Xác định commit gây lỗi.**

```bash
git show --stat --oneline <bad-commit>
git show <bad-commit>
```

Đảm bảo commit được chọn đúng là nguyên nhân cần hoàn tác và hiểu các commit sau có phụ thuộc vào nó không.

**Bước 3: Tạo commit revert.**

```bash
git revert <bad-commit>
```

Nếu conflict, giải quyết file, stage và tiếp tục bằng `git revert --continue`.

**Bước 4: Kiểm tra và chia sẻ.**

```bash
git status
git show --stat HEAD
git show HEAD
```

Chạy test, push branch `revert/bad-commit` và mở pull request vào `main` theo quy trình của nhóm.

Kết quả là commit lỗi vẫn còn trong lịch sử, nhưng một commit mới đảo ngược tác động của nó. Các thành viên khác có thể pull branch mà không phải xử lý việc lịch sử remote bị viết lại.

## 16. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Cherry-pick báo conflict | Branch đích có thay đổi không tương thích | Giải quyết file, stage rồi `--continue` |
| Cherry-pick tạo commit trùng | Patch tương đương đã có ở branch đích | Kiểm tra `git cherry`, log và diff trước khi tiếp tục |
| Cherry-pick merge commit báo cần mainline | Commit có nhiều parent | Xem parent và chọn `-m` đúng nếu thực sự cần cherry-pick merge |
| Revert báo conflict | Nội dung sau commit đã thay đổi | Giải quyết theo trạng thái hiện tại rồi `git revert --continue` |
| Push sau reset bị từ chối non-fast-forward | Branch local đã viết lại lịch sử khác remote | Với branch chia sẻ, dùng revert; không force push tùy tiện |
| Reset làm mất thay đổi local | Dùng `--hard` hoặc chế độ cập nhật index/working tree không phù hợp | Kiểm tra reflog, stash và backup ref; khôi phục commit tìm được |
| `git stash pop` có conflict | Branch hiện tại khác nền stash | Dùng `git stash apply`, giải quyết conflict và chỉ drop sau khi xác minh |
| Không tìm thấy commit sau reset | Commit không còn trên branch hiện tại | Kiểm tra `git reflog` và tạo rescue branch từ OID |
| Revert merge làm lần merge sau không mang thay đổi cũ trở lại | Git ghi nhận merge đã bị đảo ngược | Phối hợp maintainer; revert commit revert hoặc tạo commit mới phù hợp |

## 17. Checklist trước khi chuyển bản sửa hoặc hoàn tác

Trước khi chạy thao tác:

- [ ] Đã xác nhận repository, branch và trạng thái working tree.
- [ ] Đã fetch remote để xem lịch sử mới nhất.
- [ ] Đã xác định đúng OID và đọc diff của commit nguồn.
- [ ] Đã xác định commit có được chia sẻ lên branch remote chưa.
- [ ] Đã bảo toàn thay đổi chưa commit bằng commit hoặc stash.
- [ ] Đã chọn cherry-pick cho việc chuyển commit và revert cho việc hoàn tác lịch sử đã chia sẻ.
- [ ] Nếu xử lý merge commit, đã kiểm tra thứ tự parent và chọn mainline có chủ đích.
- [ ] Đã giải quyết conflict và kiểm tra `git status`.
- [ ] Đã chạy test phù hợp trước khi push hoặc mở pull request.
- [ ] Nếu cần rewrite branch riêng, đã thống nhất với người liên quan và kiểm tra remote trước khi dùng `--force-with-lease`.

Sau thao tác, kiểm tra lại graph và trạng thái:

```bash
git status --short --branch
git log --oneline --graph --decorate --all -15
git show --stat --oneline HEAD
```

Đừng chỉ dựa vào việc lệnh kết thúc thành công. Hãy xác minh commit mới nằm trên đúng branch và chứa đúng nội dung cần chuyển hoặc hoàn tác.

## Kết luận

Dùng `git cherry-pick` để chuyển thay đổi của commit sang branch khác và tạo commit mới; dùng `git revert` để đảo ngược tác động của commit đã chia sẻ mà không viết lại lịch sử. `git reset` phù hợp hơn với branch riêng chưa công bố, còn `git restore` xử lý nội dung file và `git stash` bảo toàn công việc chưa commit trong lúc chuyển ngữ cảnh. Khi thao tác sai, kiểm tra reflog và tạo ref cứu hộ ngay khi tìm được commit. Trước mọi thao tác, fetch remote, đọc diff, bảo toàn công việc local và xác minh kết quả bằng status cùng commit graph.

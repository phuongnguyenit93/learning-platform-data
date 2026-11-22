# Chọn nhánh đích và kiểm tra phạm vi trước khi git merge

Lệnh `git merge` tích hợp lịch sử của một nhánh vào nhánh hiện tại. Vì vậy, trước khi chạy lệnh, bạn phải xác định rõ **nhánh đích** (nơi nhận thay đổi) và **nhánh nguồn** (nhánh cung cấp commit). Git không tự suy ra nhánh đích từ tên đối số: nhánh đang được checkout, tức HEAD hiện tại, mới là nơi nhận merge.

Một thao tác thường gặp là đưa tính năng từ `feature/payment` vào `main`:

~~~bash
git switch main
git merge feature/payment
~~~

Nếu bạn đang đứng trên `feature/payment` rồi chạy `git merge main`, kết quả sẽ ngược lại: Git tích hợp `main` vào nhánh tính năng. Lỗi chọn nhầm hướng có thể làm lịch sử thay đổi ngoài dự định, đặc biệt khi merge được thực hiện trên branch dùng chung.

Bài học này hướng dẫn cách xác nhận target/source, kiểm tra trạng thái repository và độ mới của các ref, đọc commit cùng phạm vi thay đổi trước merge, hiểu fast-forward và merge commit ở mức cần thiết, rồi thực hiện merge có kiểm soát và xác minh kết quả.

## 1. Phân biệt nhánh đích và nhánh nguồn

### 1.1. Nhánh đích là nhánh đang được checkout

Cú pháp:

~~~bash
git merge <source>
~~~

Git tích hợp commit có thể truy cập từ `<source>` vào **nhánh hiện tại**. Nhánh hiện tại là nhánh mà HEAD đang trỏ tới.

Ví dụ muốn đưa tính năng vào main:

~~~bash
git switch main
git merge feature/payment
~~~

Trong ví dụ:

- Target: `main`.
- Source: `feature/payment`.
- HEAD trước merge: commit tip của `main`.
- Đối số của `git merge`: `feature/payment`.

Tên branch sau `git merge` là nguồn. Git không có cú pháp `git merge <target> <source>` để chỉ định hai phía theo cách đó.

### 1.2. Kiểm tra HEAD và branch trước khi merge

Dùng:

~~~bash
git branch --show-current
git status --short --branch
git log -1 --oneline --decorate
~~~

Ba lệnh giúp xác nhận:

- Tên branch hiện tại.
- Repository có thay đổi chưa commit hay không.
- HEAD đang trỏ tới commit nào và ref nào đang gắn với commit đó.

Nếu lệnh `git branch --show-current` không in tên branch, có thể bạn đang ở detached HEAD. Không nên merge khi chưa xác định rõ ref nào sẽ giữ commit kết quả.

### 1.3. Kiểm tra cả hai tên branch trước khi chạy lệnh

~~~bash
git branch --list
git show -s --oneline main
git show -s --oneline feature/payment
~~~

Nếu source là remote-tracking branch:

~~~bash
git show -s --oneline origin/feature/payment
~~~

Đừng dựa vào tên gần giống nhau như `main`, `master`, `release`, `origin/main` hoặc `origin/release`. Xác nhận chính xác ref mà bạn định dùng.

### 1.4. Sơ đồ hướng merge

~~~text
feature/payment  (source)
        |
        |  git merge feature/payment
        v
main             (target / current branch)
        |
        v
   HEAD sau merge
~~~

Lệnh merge được chạy khi đang checkout `main`. Commit của source được tích hợp vào lịch sử của target. Source branch không tự bị xóa sau merge.

### 1.5. Tên đối số không quyết định target

Ví dụ:

~~~bash
git switch feature/payment
git merge main
~~~

Lệnh trên đưa các commit của `main` vào `feature/payment`. Nó không đưa feature vào main.

Nếu muốn đảo hướng, hãy chuyển sang target trước rồi mới merge source:

~~~bash
git switch main
git merge feature/payment
~~~

Trước khi chạy, tự nói thành câu: "Tôi đang đứng trên nhánh ___ và muốn tích hợp nhánh ___ vào đây." Nếu không điền được hai tên rõ ràng, chưa nên chạy merge.

## 2. Xác nhận working tree sẵn sàng

### 2.1. Kiểm tra thay đổi local

~~~bash
git status
git status --short
~~~

Merge có thể bị Git từ chối nếu thay đổi chưa commit có nguy cơ bị ghi đè. Ngay cả khi Git cho phép, thay đổi local có thể làm kết quả khó hiểu khi phát sinh conflict.

Khuyến nghị bắt đầu merge với working tree và index sạch. Nếu có công việc cần giữ, hãy commit thành một commit phù hợp hoặc stash theo quy trình của nhóm.

### 2.2. Phân biệt staged, unstaged và untracked

~~~bash
git diff
git diff --cached
git ls-files --others --exclude-standard
~~~

- `git diff`: thay đổi trong working tree so với index.
- `git diff --cached`: thay đổi đã stage so với HEAD.
- `git ls-files --others --exclude-standard`: file untracked không bị ignore.

Đọc cả ba nhóm. Một file untracked có thể bị merge ghi đè nếu source thêm file cùng đường dẫn. Git thường bảo vệ file local và từ chối thao tác khi phát hiện nguy cơ mất dữ liệu, nhưng không nên dựa vào việc Git sẽ phát hiện mọi tình huống theo ý bạn.

### 2.3. Xử lý công việc chưa commit trước merge

Nếu thay đổi local thuộc một mục tiêu hoàn chỉnh, có thể commit:

~~~bash
git add -- path/to/file
git commit -m "Save current work"
~~~

Nếu cần tạm cất:

~~~bash
git stash push -u -m "Work before merging feature/payment"
~~~

Tùy chọn `-u` đưa cả file untracked vào stash. File ignored không được đưa vào nếu không dùng tùy chọn khác như `-a`; hãy hiểu rõ phạm vi trước khi dùng.

Sau khi merge xong, khôi phục:

~~~bash
git stash list
git stash pop
~~~

`stash pop` có thể gây conflict. Không xóa stash cho đến khi xác nhận các thay đổi đã được khôi phục đầy đủ.

### 2.4. Kiểm tra có thao tác Git khác đang dở không

~~~bash
git status
~~~

Nếu repository đang ở giữa merge, rebase, cherry-pick hoặc revert, hãy hoàn tất hoặc hủy thao tác đó theo đúng quy trình trước khi bắt đầu merge mới. Một repository không thể xử lý an toàn nhiều thao tác tích hợp cùng lúc trên cùng working tree.

Có thể kiểm tra các entry conflict:

~~~bash
git ls-files -u
~~~

Nếu có kết quả, index còn đường dẫn chưa hợp nhất. Giải quyết hoặc hủy thao tác hiện tại trước.

## 3. Cập nhật thông tin branch từ remote

### 3.1. Fetch trước để biết source và target mới nhất

Remote-tracking branch như `origin/main` chỉ phản ánh trạng thái ở lần fetch gần nhất.

Cập nhật refs:

~~~bash
git fetch origin --prune
~~~

Hoặc tất cả remote:

~~~bash
git fetch --all --prune
~~~

`fetch` tải commit và cập nhật remote-tracking refs theo cấu hình. Nó không tự merge các thay đổi vào branch hiện tại.

### 3.2. Phân biệt branch local và remote-tracking branch

Xem các branch cùng upstream:

~~~bash
git branch -vv
~~~

Ví dụ:

~~~text
* main             a12bc34 [origin/main: behind 2] Prepare release
  feature/payment  d45ef67 [origin/feature/payment] Add payment validation
~~~

Ở đây `main` local đang chậm hơn `origin/main` hai commit. Nếu bạn merge feature vào main khi main local chưa được cập nhật, target có thể không phản ánh trạng thái mới nhất của nhánh chính trên remote.

### 3.3. Cập nhật target local trước khi nhận source

Sau khi fetch, chuyển sang target:

~~~bash
git switch main
~~~

Kiểm tra quan hệ với remote:

~~~bash
git status -sb
git log --oneline main..origin/main
git log --oneline origin/main..main
~~~

- `main..origin/main`: commit có trên origin/main nhưng chưa có trong main local.
- `origin/main..main`: commit có trong main local nhưng chưa có trong origin/main.

Nếu target local chỉ đang behind và không có commit riêng, có thể fast-forward:

~~~bash
git merge --ff-only origin/main
~~~

`--ff-only` chỉ cập nhật khi có thể tiến thẳng theo ancestry; nếu hai nhánh đã phân kỳ, Git từ chối thay vì tự tạo merge commit.

Nếu local và remote đã diverge, dừng lại và theo quy trình đồng bộ của nhóm. Không dùng reset hoặc force update để làm cho hai nhánh trông giống nhau khi chưa hiểu các commit riêng.

### 3.4. Source là branch remote

Bạn có thể merge trực tiếp remote-tracking branch sau khi fetch:

~~~bash
git merge origin/feature/payment
~~~

Hoặc checkout source local nếu workflow yêu cầu:

~~~bash
git switch feature/payment
git pull --ff-only
git switch main
git merge feature/payment
~~~

Cách thứ hai cập nhật branch local feature trước, nhưng chỉ dùng khi branch local có upstream phù hợp và chính sách nhóm cho phép.

Không dùng `git pull` một cách mù quáng trên target nếu bạn muốn kiểm soát rõ remote nào và ref nào được tích hợp. Pull là fetch cộng với tích hợp theo cấu hình; đọc `git status -sb` và `git branch -vv` trước.

## 4. Kiểm tra quan hệ lịch sử giữa target và source

### 4.1. Xem đồ thị hai nhánh

~~~bash
git log --oneline --graph --decorate --all -20
~~~

Đồ thị giúp nhận ra:

- Source đi trước target.
- Target đi trước source.
- Hai nhánh đã phân kỳ.
- Có merge commit ở một trong hai phía.

Đừng chỉ nhìn tên branch; hãy kiểm tra commit graph.

### 4.2. Xác định merge base

~~~bash
git merge-base main feature/payment
~~~

Merge base là commit tổ tiên chung phù hợp mà Git dùng làm điểm bắt đầu cho phép hợp nhất ba chiều trong trường hợp thông thường.

Có thể xem thông tin commit:

~~~bash
git show -s --oneline $(git merge-base main feature/payment)
~~~

Trong PowerShell, nếu muốn tránh cú pháp command substitution khác shell, có thể chạy riêng lệnh `git merge-base`, sao chép hash rồi truyền vào `git show`.

Nếu không có merge base, hai repository hoặc lịch sử có thể không có quan hệ tổ tiên chung. Không thêm `--allow-unrelated-histories` chỉ để vượt lỗi; trước hết xác minh có đúng repository và đúng source không.

### 4.3. Kiểm tra source đã nằm trong target chưa

~~~bash
git merge-base --is-ancestor feature/payment main
~~~

Nếu exit code là 0, tip của source là tổ tiên của target; các commit của source đã có thể truy cập từ target. Nếu exit code là 1, source không phải tổ tiên của target.

Ngược lại:

~~~bash
git merge-base --is-ancestor main feature/payment
~~~

Nếu exit code là 0, target là tổ tiên của source. Khi merge source vào target, đây là điều kiện fast-forward có thể xảy ra nếu target vẫn ở commit đó.

Các lệnh `--is-ancestor` dùng exit code, thường không in nội dung. Trong shell, kiểm tra mã thoát ngay sau lệnh.

### 4.4. Xác định nhánh nào đang đi trước

Có thể dùng:

~~~bash
git rev-list --left-right --count main...feature/payment
~~~

Đầu ra có hai số:

~~~text
2    4
~~~

Với thứ tự `main...feature/payment`, số thứ nhất là commit chỉ reachable từ main; số thứ hai là commit chỉ reachable từ feature/payment. Ví dụ này cho biết main có 2 commit riêng và feature có 4 commit riêng.

Đây là cách nhanh để phát hiện hai nhánh đã phân kỳ.

## 5. Kiểm tra commit sẽ được đưa vào target

### 5.1. Liệt kê commit có ở source nhưng chưa có ở target

~~~bash
git log --oneline main..feature/payment
~~~

Khoảng `main..feature/payment` chọn commit reachable từ source nhưng không reachable từ target. Đây thường là danh sách commit bạn muốn review trước merge.

Xem chi tiết:

~~~bash
git log --format=fuller main..feature/payment
~~~

Kiểm tra subject, author, thời gian và nội dung commit. Nếu có commit thử nghiệm, commit debug hoặc thay đổi ngoài mục tiêu, dừng lại và trao đổi về việc làm sạch source branch trước merge.

### 5.2. Xem cả hai phía của lịch sử phân kỳ

~~~bash
git log --left-right --graph --oneline main...feature/payment
~~~

Dấu `<` thường đánh dấu commit chỉ có phía trái (main), còn `>` đánh dấu commit chỉ có phía phải (feature/payment). Đây là tập hợp đối xứng của hai nhánh, loại phần lịch sử chung.

Dùng lệnh này để hiểu cả target đã thay đổi gì kể từ điểm chung và source đã phát triển ra sao.

### 5.3. Bỏ qua commit có patch tương đương khi review

~~~bash
git log --left-right --cherry-pick --oneline main...feature/payment
~~~

`--cherry-pick` loại các commit có patch tương đương ở phía đối diện trong một số trường hợp, hữu ích khi có commit được cherry-pick giữa hai nhánh và hash khác nhau.

Đây là công cụ hỗ trợ review; không thay thế việc kiểm tra nội dung thực tế hoặc quy ước merge của nhóm.

### 5.4. Xem các file bị thay đổi trong source

~~~bash
git diff --name-status main...feature/payment
git diff --stat main...feature/payment
~~~

Với cú pháp ba chấm trong `git diff A...B`, Git so sánh merge base của A và B với B. Vì vậy, lệnh cho thấy những thay đổi phía source kể từ điểm chung.

Nó hữu ích để trả lời: "Source branch mang đến những thay đổi gì so với lúc hai nhánh tách nhau?"

### 5.5. Đọc patch dự kiến từ source

~~~bash
git diff main...feature/payment
~~~

Đọc các hunk để xác định:

- Logic nào được thêm hoặc thay đổi.
- File nào bị xóa hoặc đổi tên.
- API hoặc schema nào thay đổi.
- Có file cấu hình, secret hoặc dữ liệu sinh tự động không.
- Có thay đổi ngoài phạm vi tính năng không.

Đây là diff từ merge base đến source, không phải bản mô phỏng đầy đủ của kết quả merge.

### 5.6. Phân biệt diff ba chấm và hai chấm

Hai lệnh sau trả lời câu hỏi khác nhau:

~~~bash
git diff main...feature/payment
git diff main feature/payment
~~~

- `git diff main...feature/payment`: so sánh merge base với source, cho biết source đã thay đổi gì kể từ điểm chung.
- `git diff main feature/payment`: so sánh trực tiếp hai tree tip, cho biết trạng thái file hiện tại ở hai nhánh khác nhau ra sao.

Nếu main cũng có thay đổi riêng, diff hai chấm có thể bao gồm cả khác biệt phía target. Để review phần source đóng góp, thường bắt đầu bằng diff ba chấm.

### 5.7. Kiểm tra whitespace và file ngoài dự kiến

~~~bash
git diff --check main...feature/payment
git diff --name-only main...feature/payment
~~~

`--check` phát hiện một số lỗi whitespace trong patch. Danh sách file giúp đối chiếu phạm vi với ticket hoặc pull request.

Không có diff nào tự chứng minh rằng merge sẽ không conflict. Conflict còn phụ thuộc cách cả hai phía thay đổi cùng vùng nội dung và thuật toán merge.

## 6. Xác nhận target có đúng chính sách merge không

### 6.1. Kiểm tra quy ước của branch

Trước khi merge vào branch quan trọng như `main`, `release` hoặc `production`, xác nhận:

- Có yêu cầu pull request/code review không?
- Có cần CI xanh hoặc approval không?
- Có chính sách chỉ fast-forward hay luôn tạo merge commit không?
- Có yêu cầu ký commit hoặc kiểm tra chữ ký không?
- Có branch protection trên remote không?
- Có cần release note, migration hoặc cập nhật version không?

Git local không tự biết mọi chính sách của nền tảng hosting. Nếu repository yêu cầu merge qua pull request, hãy dùng quy trình đó thay vì merge trực tiếp để né kiểm soát.

### 6.2. Chọn đúng source ref đã được review

Pull request thường có source branch và target branch hiển thị rõ. Đối chiếu hai tên với local refs sau fetch.

Nếu PR nhắm vào `release/2.x` nhưng bạn đang đứng trên `main`, không tự ý đổi target chỉ vì main là branch quen thuộc.

### 6.3. Kiểm tra trạng thái CI và commit cuối source

~~~bash
git log -1 --format=fuller feature/payment
git show --stat --oneline feature/payment
~~~

Đảm bảo commit tip bạn định merge đúng là commit đã được review/test. Nếu source branch tiến thêm commit sau review, phạm vi thực tế có thể khác với pull request đã được phê duyệt.

## 7. Thực hiện merge sau khi preflight đạt

### 7.1. Chuyển sang target một lần nữa

~~~bash
git switch main
git status --short --branch
git branch --show-current
~~~

Xác nhận branch hiện tại là target. Kiểm tra HEAD chưa bị di chuyển bởi thao tác khác kể từ lúc review.

### 7.2. Merge source

~~~bash
git merge feature/payment
~~~

Git có thể:

- Fast-forward target nếu target là tổ tiên của source.
- Tạo merge commit nếu hai nhánh đã phân kỳ và merge tự động thành công.
- Dừng với conflict để bạn giải quyết.
- Báo Already up to date nếu source không mang commit mới vào target.

Kết quả phụ thuộc quan hệ ancestry, nội dung hai nhánh và cấu hình merge.

### 7.3. Chỉ cho phép fast-forward

Nếu chính sách yêu cầu target chỉ tiến thẳng mà không tạo merge commit:

~~~bash
git merge --ff-only feature/payment
~~~

Nếu hai nhánh đã phân kỳ, lệnh từ chối. Đây là tín hiệu cần xử lý lịch sử theo quy ước nhóm, không phải lý do để bỏ tùy chọn và merge tùy tiện.

### 7.4. Luôn tạo merge commit khi tích hợp

Nếu nhóm muốn giữ một commit đánh dấu sự kiện tích hợp:

~~~bash
git merge --no-ff feature/payment
~~~

Tùy chọn này yêu cầu tạo merge commit ngay cả khi fast-forward có thể thực hiện được, trừ trường hợp không có gì mới để tích hợp.

Chọn `--ff`, `--ff-only` hay `--no-ff` theo chính sách repository. Đây là quyết định lịch sử, không thay đổi vai trò target/source.

### 7.5. Xem trước kết quả merge bằng no-commit

Khi cần kiểm tra kết quả tích hợp trước khi tạo merge commit:

~~~bash
git merge --no-commit --no-ff feature/payment
~~~

Lệnh bắt đầu merge, cập nhật index và working tree, nhưng dừng trước bước tạo commit nếu có nội dung cần tích hợp. Kết hợp `--no-ff` để bảo đảm có điểm dừng ngay cả khi merge có thể fast-forward; `--no-commit` một mình không ngăn fast-forward.

Đây không phải dry run: repository đã bước vào trạng thái merge. Sau đó:

~~~bash
git status
git diff
git diff --cached
~~~

Chạy test, review nội dung. Nếu đồng ý, tạo merge commit:

~~~bash
git commit
~~~

Nếu hủy thao tác merge đang dở:

~~~bash
git merge --abort
~~~

Đảm bảo các thay đổi local đã được bảo toàn trước khi bắt đầu; abort không phải phương án sao lưu cho mọi dữ liệu local.

## 8. Nếu phát hiện chọn sai nhánh đích

### 8.1. Phát hiện trước khi chạy merge

Nếu đang đứng trên source thay vì target, chỉ cần chuyển sang target:

~~~bash
git switch main
git branch --show-current
~~~

Sau đó thực hiện preflight lại. Không cần tạo hoặc xóa branch chỉ để sửa hướng merge.

### 8.2. Merge đang dở và chưa commit

Nếu đã bắt đầu merge trên nhầm target và Git vẫn đang ở trạng thái merge, kiểm tra:

~~~bash
git status
~~~

Nếu xác nhận cần hủy:

~~~bash
git merge --abort
~~~

Sau khi abort:

~~~bash
git status --short --branch
git branch --show-current
~~~

Chuyển sang target đúng và thực hiện lại các bước kiểm tra.

### 8.3. Merge đã hoàn tất trên nhầm branch

Nếu merge đã hoàn tất, dừng lại trước khi chạy reset, revert hoặc force push. Xác định:

- Merge là fast-forward hay tạo merge commit?
- Branch sai đã được push chưa?
- Có ai đã fetch hoặc tạo commit dựa trên kết quả chưa?
- Target đúng có cần cùng thay đổi đó không?
- Có thay đổi local nào phát sinh sau merge không?

Với merge commit chưa chia sẻ, có thể có cách điều chỉnh lịch sử; với branch đã chia sẻ, revert hoặc một commit sửa chữa thường an toàn hơn viết lại lịch sử. Chọn thao tác dựa trên trạng thái thật và chính sách nhóm.

Không dùng `git reset --hard` chỉ vì muốn đưa branch về vị trí trước merge; lệnh đó có thể xóa thay đổi local không liên quan.

## 9. Kiểm tra conflict và kết quả merge

### 9.1. Conflict không có nghĩa là target/source bị đảo

Nếu Git báo conflict, merge vẫn đang được thực hiện trên target hiện tại. Xác nhận:

~~~bash
git branch --show-current
git status
git ls-files -u
~~~

HEAD thường vẫn ở commit target cho đến khi merge commit được tạo. Source được ghi nhận trong trạng thái merge và index chứa các phiên bản cần giải quyết.

### 9.2. Giải quyết conflict theo nội dung

Mở từng file conflict, so sánh thay đổi từ hai phía và chỉnh kết quả cuối cùng. Không chọn toàn bộ ours hoặc theirs nếu cả hai phía đều có logic cần giữ.

Sau khi giải quyết:

~~~bash
git add -- path/to/resolved-file
git status
git ls-files -u
~~~

Khi không còn entry unmerged, kiểm tra diff staged và chạy test.

### 9.3. Tiếp tục hoặc hủy merge

Khi mọi conflict đã giải quyết:

~~~bash
git diff --cached
git diff --check
git merge --continue
~~~

Với merge thường, Git có thể yêu cầu tạo commit bằng `git commit`; `git merge --continue` là cách diễn đạt rõ thao tác tiếp tục trong trạng thái merge.

Nếu quyết định hủy:

~~~bash
git merge --abort
~~~

Không xóa thủ công các file marker hoặc sửa .git/MERGE_HEAD để thoát trạng thái. Dùng lệnh Git tương ứng.

## 10. Xác minh sau khi merge

### 10.1. Kiểm tra branch và trạng thái

~~~bash
git status --short --branch
git branch --show-current
git log -1 --oneline --decorate
~~~

Đảm bảo bạn vẫn ở target mong muốn và repository không còn trạng thái merge dang dở.

### 10.2. Xem đồ thị sau merge

~~~bash
git log --graph --oneline --decorate --all -20
~~~

Đồ thị cho biết source đã được tích hợp theo fast-forward hay qua merge commit. Kiểm tra source commit có thể truy cập từ target.

### 10.3. Kiểm tra parent nếu tạo merge commit

~~~bash
git show -s --format="%H%n%P%n%s" HEAD
~~~

Một merge commit thông thường có nhiều parent. Parent thứ nhất thường là tip target trước merge; parent thứ hai thường là tip source được merge vào. Thứ tự parent quan trọng khi xem lịch sử và khi revert merge.

### 10.4. Xác nhận source đã được tích hợp

~~~bash
git merge-base --is-ancestor feature/payment main
~~~

Nếu exit code là 0, tip source hiện là tổ tiên của target. Đây là một kiểm tra ancestry hữu ích sau merge. Nếu source branch đã tiến lên sau merge, kiểm tra này có thể trả về 1 dù các commit cũ của source đã được tích hợp; khi đó kiểm tra commit hash đã review hoặc merge base cụ thể.

### 10.5. Chạy test và xem thay đổi còn lại

~~~bash
git diff
git diff --cached
git status
~~~

Chạy build/test phù hợp với dự án. Nếu merge tạo thay đổi không mong muốn hoặc test thất bại, đừng push ngay; xác định nguyên nhân và xử lý theo quy trình nhóm.

## 11. Ví dụ đầy đủ: đưa feature vào main

Giả sử nhóm cần đưa `feature/payment` vào `main`.

### Bước 1 — Fetch refs

~~~bash
git fetch origin --prune
~~~

### Bước 2 — Chọn target

~~~bash
git switch main
git status --short --branch
git branch --show-current
~~~

Xác nhận đang ở main và working tree sạch.

### Bước 3 — Đồng bộ target

~~~bash
git status -sb
git log --oneline main..origin/main
git log --oneline origin/main..main
~~~

Nếu main chỉ behind và không diverge:

~~~bash
git merge --ff-only origin/main
~~~

### Bước 4 — Kiểm tra source và lịch sử

~~~bash
git show -s --oneline feature/payment
git log --oneline main..feature/payment
git log --left-right --graph --oneline main...feature/payment
~~~

### Bước 5 — Review phạm vi source

~~~bash
git diff --stat main...feature/payment
git diff --name-status main...feature/payment
git diff --check main...feature/payment
~~~

Đọc patch đầy đủ và xác nhận các file thuộc tính năng thanh toán.

### Bước 6 — Chạy test trên source

Có thể chuyển sang source để kiểm tra riêng nếu cần, sau đó quay lại target và xác nhận trạng thái. Hoặc dùng CI/pull request theo quy trình nhóm. Đừng để thay đổi local phát sinh trong quá trình test bị mang nhầm sang target.

### Bước 7 — Merge vào target

~~~bash
git switch main
git status --short --branch
git merge --no-ff feature/payment
~~~

Chỉ dùng `--no-ff` nếu chính sách nhóm muốn giữ merge commit; nếu không, dùng chính sách merge mặc định hoặc `--ff-only` tương ứng.

### Bước 8 — Xác minh kết quả

~~~bash
git status --short --branch
git log --graph --oneline --decorate -15
git merge-base --is-ancestor feature/payment main
~~~

Chạy test sau merge. Khi mọi kiểm tra đạt và branch được phép cập nhật remote, push theo workflow của nhóm.

## 12. Những sai lầm thường gặp

- **Đứng trên source rồi chạy merge target:** thao tác sẽ tích hợp target vào source. Luôn xác nhận branch hiện tại trước.
- **Nghĩ đối số của git merge là target:** đối số là source; target là branch đang checkout.
- **Không fetch trước khi review:** local remote-tracking ref có thể cũ và không phản ánh commit mới nhất trên server.
- **Chỉ xem tên branch:** hai ref có thể cùng tên gần giống nhưng trỏ đến commit khác. Kiểm tra log và hash.
- **Bỏ qua thay đổi chưa commit:** local work có thể bị ghi đè hoặc trộn vào quá trình giải quyết conflict. Bảo toàn trước merge.
- **Dùng git diff A...B như diff trực tiếp hai tip:** với diff, ba chấm so sánh merge base với B; hai đối số so sánh trực tiếp hai tree.
- **Cho rằng diff sạch nghĩa là không conflict:** diff giúp review phạm vi nhưng không đảm bảo merge tự động.
- **Dùng pull mà không biết cấu hình:** pull có thể tích hợp theo cấu hình merge/rebase. Fetch rồi chọn ref và lệnh rõ ràng khi cần kiểm soát.
- **Bỏ qua commit riêng trên target:** source không phải phần duy nhất thay đổi; xem đồ thị và hai phía của lịch sử.
- **Dùng --no-commit như dry run:** merge đã thay đổi index/working tree. Kết hợp --no-ff để dừng trước commit khi cần review.
- **Chạy reset --hard khi merge nhầm:** có thể mất dữ liệu local. Kiểm tra trạng thái và chọn cách khôi phục phù hợp.
- **Push ngay sau merge mà chưa test:** kết quả merge cần được kiểm tra như một thay đổi mới.

## 13. Checklist trước khi chạy git merge

- [ ] Đã xác định rõ target và source.
- [ ] Đã xác nhận branch hiện tại chính là target.
- [ ] Không ở detached HEAD.
- [ ] Working tree và index sạch hoặc thay đổi local đã được bảo toàn.
- [ ] Không có merge/rebase/cherry-pick/revert đang dở.
- [ ] Đã fetch remote và kiểm tra độ mới của refs.
- [ ] Đã kiểm tra target local có diverge với upstream hay không.
- [ ] Đã xem commit source chưa có trong target.
- [ ] Đã xem đồ thị và merge base.
- [ ] Đã review diff ba chấm để hiểu thay đổi từ source.
- [ ] Đã kiểm tra file, whitespace, test và phạm vi ticket.
- [ ] Đã xác nhận chính sách merge của target branch.
- [ ] Đã chọn đúng tùy chọn fast-forward/merge commit theo quy ước.
- [ ] Đã biết cách abort nếu merge đang dở.

## 14. Bảng tra cứu nhanh

| Mục tiêu | Lệnh |
| --- | --- |
| Xác nhận branch hiện tại | `git branch --show-current` |
| Xem trạng thái và upstream | `git status -sb` |
| Xem branch và upstream | `git branch -vv` |
| Cập nhật remote-tracking refs | `git fetch --all --prune` |
| Chuyển sang target | `git switch main` |
| Xem commit mới nhất của source | `git show -s --oneline feature/payment` |
| Liệt kê commit source chưa có trong target | `git log --oneline main..feature/payment` |
| Xem lịch sử phân kỳ hai phía | `git log --left-right --graph --oneline main...feature/payment` |
| Đếm commit riêng mỗi phía | `git rev-list --left-right --count main...feature/payment` |
| Tìm merge base | `git merge-base main feature/payment` |
| Kiểm tra source đã là tổ tiên target | `git merge-base --is-ancestor feature/payment main` |
| Xem file source thay đổi | `git diff --name-status main...feature/payment` |
| Xem thống kê source thay đổi | `git diff --stat main...feature/payment` |
| Đọc patch source thay đổi | `git diff main...feature/payment` |
| Kiểm tra whitespace | `git diff --check main...feature/payment` |
| Merge source vào target hiện tại | `git merge feature/payment` |
| Chỉ cho phép fast-forward | `git merge --ff-only feature/payment` |
| Buộc tạo merge commit | `git merge --no-ff feature/payment` |
| Dừng trước commit để review | `git merge --no-commit --no-ff feature/payment` |
| Hủy merge đang dở | `git merge --abort` |
| Xem đồ thị sau merge | `git log --graph --oneline --decorate --all` |

## 15. Tổng kết

Trong Git, target là branch đang checkout; source là ref được truyền vào `git merge`. Muốn đưa `feature/payment` vào `main`, trước tiên phải checkout main, xác nhận HEAD và trạng thái working tree, rồi mới merge feature/payment.

Trước merge, fetch remote để cập nhật refs, kiểm tra target có diverge với upstream hay không, xem commit source chưa có trong target, đọc merge base, đồ thị và diff. `git log target..source` liệt kê commit chỉ có ở source; `git diff target...source` cho thấy thay đổi source kể từ merge base. Hai lệnh này giúp hiểu phạm vi, nhưng không dự đoán chắc chắn mọi conflict.

Sau khi preflight đạt, chọn chính sách fast-forward hoặc merge commit theo quy ước dự án, thực hiện merge, giải quyết conflict nếu có, chạy test và xác minh branch, commit graph cùng trạng thái repository. Việc kiểm tra hướng merge và phạm vi trước khi chạy lệnh giúp tránh tích hợp nhầm nhánh và giữ lịch sử dễ review, truy vết.


# Vai trò và giới hạn của ORIG_HEAD, FETCH_HEAD và MERGE_HEAD

Khi Git thực hiện fetch, merge, pull hoặc reset, đôi khi bạn cần biết commit nào vừa được tải về, commit nào đang được đưa vào merge và nhánh hiện tại đã ở đâu trước thao tác. Git lưu một số thông tin này bằng các pseudo-ref như `FETCH_HEAD`, `MERGE_HEAD` và `ORIG_HEAD`.

Ba tên này thường xuất hiện khi xử lý lỗi đồng bộ hoặc khôi phục sau thao tác nhầm. Tuy nhiên, chúng không phải ba nhánh dự phòng có thể dùng thay thế cho nhau. Mỗi tên phục vụ một thời điểm khác nhau, có vòng đời và giới hạn riêng. Hiểu đúng chúng giúp bạn điều tra trạng thái repository và chọn cách phục hồi phù hợp.

## 1. Pseudo-ref là gì?

Trong Git, branch thông thường là một tham chiếu có tên như `refs/heads/main`. Remote-tracking branch có tên như `refs/remotes/origin/main`. Chúng thường tồn tại lâu dài cho đến khi được di chuyển hoặc xóa.

Các tên `ORIG_HEAD`, `FETCH_HEAD` và `MERGE_HEAD` là những tham chiếu đặc biệt hoặc tệp metadata trong Git directory. Chúng được Git cập nhật để ghi lại thông tin phục vụ thao tác hiện tại hoặc thao tác vừa xảy ra.

Có thể xem đường dẫn Git directory và vị trí các tệp này bằng:

~~~bash
git rev-parse --git-dir
git rev-parse --git-path ORIG_HEAD
git rev-parse --git-path FETCH_HEAD
git rev-parse --git-path MERGE_HEAD
~~~

Dùng `git rev-parse --git-path` thay vì mặc định ghép đường dẫn `.git/...`, vì trong linked worktree, `.git` ở thư mục làm việc có thể là một tệp trỏ đến Git directory thực tế.

Ba pseudo-ref có vai trò khái quát:

| Tên | Ghi nhận điều gì? | Thường hữu ích khi |
| --- | --- | --- |
| `ORIG_HEAD` | Mốc HEAD trước một thao tác di chuyển lịch sử quan trọng | Xem lại hoặc khôi phục đầu nhánh trước merge/reset |
| `FETCH_HEAD` | Commit hoặc các commit được fetch trong lần fetch gần nhất | Kiểm tra nội dung vừa tải về trước khi tích hợp |
| `MERGE_HEAD` | Commit hoặc các commit đang được merge vào HEAD hiện tại | Điều tra một merge đang diễn ra hoặc xử lý conflict |

## 2. ORIG_HEAD — mốc HEAD trước thao tác

### 2.1. Vai trò của ORIG_HEAD

`ORIG_HEAD` thường lưu commit mà HEAD hoặc nhánh hiện tại trỏ tới trước một thao tác có thể thay đổi lịch sử đáng kể. Git sử dụng nó trong các thao tác như merge, reset và một số tình huống viết lại lịch sử để bạn có thể tham chiếu lại vị trí trước đó.

Ví dụ, nhánh hiện tại có lịch sử:

~~~text
A --- B --- C  (HEAD -> main)
~~~

Bạn bắt đầu merge một nhánh khác. Trước khi tích hợp, Git có thể ghi nhận commit `C` vào `ORIG_HEAD`. Nếu cần kiểm tra mốc cũ:

~~~bash
git show -s --oneline ORIG_HEAD
~~~

Lệnh hiển thị commit mà `ORIG_HEAD` đang tham chiếu. Có thể xác minh tên này có phân giải thành một commit hợp lệ hay không:

~~~bash
git rev-parse --verify 'ORIG_HEAD^{commit}'
~~~

Nếu lệnh không trả về mã commit, pseudo-ref có thể chưa tồn tại hoặc không còn trỏ đến một commit hợp lệ trong repository hiện tại.

### 2.2. Dùng ORIG_HEAD để điều tra merge vừa hoàn tất

Giả sử bạn vừa merge `feature/payment` vào `main`, sau đó nhận ra kết quả tích hợp không đúng. Trước khi thay đổi thêm, kiểm tra:

~~~bash
git status
git log --oneline --graph --decorate -8
git show -s --oneline ORIG_HEAD
~~~

Nếu merge vừa rồi là thao tác cập nhật HEAD gần nhất và `ORIG_HEAD` vẫn giữ mốc trước merge, bạn có thể so sánh mốc đó với lịch sử hiện tại để xác định phạm vi thay đổi.

`ORIG_HEAD` chỉ cung cấp một mốc tham chiếu; nó không tự hoàn tác thao tác. Cách xử lý phụ thuộc merge đã hoàn tất hay vẫn đang diễn ra, nhánh đã được chia sẻ hay chưa và working tree hiện có thay đổi nào.

### 2.3. Khôi phục đầu nhánh về ORIG_HEAD

Nếu merge đã hoàn tất, đang ở nhánh cá nhân, chưa có công việc mới cần giữ và đã xác nhận `ORIG_HEAD` đúng là commit trước merge, có thể đưa nhánh trở lại mốc đó:

~~~bash
git reset --hard ORIG_HEAD
~~~

Lệnh này có tính phá hủy: nó di chuyển nhánh, cập nhật index và ghi lại working tree. Các thay đổi chưa commit trên tệp được Git theo dõi có thể bị mất. Chỉ dùng khi bạn thực sự muốn loại bỏ trạng thái hiện tại và đã bảo toàn mọi nội dung cần giữ.

Trước khi reset, nên tạo nhánh backup nếu cần giữ mốc hiện tại:

~~~bash
git branch backup/after-unwanted-merge
git show -s --oneline ORIG_HEAD
~~~

Sau khi reset, kiểm tra lại:

~~~bash
git status
git log --oneline --graph --decorate -8
~~~

Nếu merge đã được push hoặc người khác đã dựa trên lịch sử đó, việc viết lại nhánh chung có thể làm các bản clone khác lệch lịch sử. Trong trường hợp này, thường nên tạo commit đảo ngược bằng `git revert` theo quy trình của nhóm thay vì reset rồi force push.

### 2.4. Giới hạn của ORIG_HEAD

- `ORIG_HEAD` không phải bản sao lưu có lịch sử riêng. Nó thường chỉ giữ một mốc trước thao tác gần nhất.
- Một thao tác Git tiếp theo có thể ghi đè giá trị này. Không nên giả định nó vẫn trỏ đến commit bạn cần sau nhiều lần reset, merge hoặc rebase.
- Nó không lưu working tree hoặc index. Nếu có thay đổi chưa commit trước thao tác, `ORIG_HEAD` không bảo toàn riêng những thay đổi đó.
- Nó không đảm bảo có thể khôi phục mọi thao tác. Nếu cần tìm các lần di chuyển HEAD trước đây, hãy kiểm tra reflog.
- Trước khi dùng làm đích reset, luôn xem commit thực tế bằng `git show` và so sánh với `git reflog`.

## 3. FETCH_HEAD — kết quả của lần fetch

### 3.1. Vai trò của FETCH_HEAD

Khi chạy `git fetch`, Git tải các đối tượng và cập nhật thông tin từ remote. Git ghi các commit vừa fetch vào tệp `FETCH_HEAD` trong Git directory. Tệp này cho biết những gì vừa được lấy về và có thể được dùng làm đầu vào cho thao tác merge hoặc pull tiếp theo.

Ví dụ:

~~~bash
git fetch origin main
~~~

Sau đó có thể xem commit vừa fetch:

~~~bash
git show -s --oneline FETCH_HEAD
~~~

Với một nhánh được fetch riêng, có thể xem các commit có ở phía vừa fetch nhưng chưa có trong HEAD:

~~~bash
git log --oneline HEAD..FETCH_HEAD
~~~

Các lệnh này giúp bạn kiểm tra nội dung trước khi tích hợp. Nếu fetch nhiều nhánh cùng lúc, `FETCH_HEAD` có thể chứa nhiều dòng và nhiều commit; một số dòng có thể được đánh dấu không dùng để merge. Hãy đọc danh sách kết quả fetch trước khi giả định nó đại diện cho duy nhất một nhánh. Ví dụ dùng `git show FETCH_HEAD` và `git log HEAD..FETCH_HEAD` ở trên giả định lần fetch chỉ lấy một nhánh cần tích hợp.

### 3.2. Dùng FETCH_HEAD để tích hợp commit vừa fetch

Một quy trình rõ ràng là fetch trước, kiểm tra sau, rồi mới merge:

~~~bash
git fetch origin main
git show -s --oneline FETCH_HEAD
git log --oneline HEAD..FETCH_HEAD
git merge FETCH_HEAD
~~~

Ở đây:

1. `git fetch origin main` lấy thông tin của nhánh `main` từ remote `origin`.
2. `git show` cho biết commit được ghi nhận trong `FETCH_HEAD`.
3. `git log` giúp xem các commit chưa có trong HEAD.
4. `git merge FETCH_HEAD` tích hợp commit vừa fetch vào nhánh hiện tại.

Trước khi merge, hãy xác nhận đang đứng trên nhánh đích mong muốn:

~~~bash
git branch --show-current
git status -sb
~~~

Không chạy merge chỉ vì `FETCH_HEAD` tồn tại. Tệp này có thể đến từ lần fetch trước và không còn đại diện cho dữ liệu bạn đang muốn tích hợp.

### 3.3. FETCH_HEAD khác remote-tracking branch

Hai khái niệm này thường bị nhầm:

- `FETCH_HEAD` ghi nhận các kết quả fetch gần nhất trong tệp metadata, phục vụ thao tác fetch/pull hiện tại.
- `origin/main` là remote-tracking branch dùng để theo dõi trạng thái nhánh `main` trên remote `origin`.

Remote-tracking branch thường được cập nhật theo refspec fetch đã cấu hình và có thể tiếp tục tồn tại qua nhiều lần fetch. `FETCH_HEAD` là thông tin tạm thời của lần fetch gần nhất và có thể bị ghi đè ở lần fetch tiếp theo.

Xem remote-tracking branch:

~~~bash
git branch -r
git log --oneline -5 origin/main
~~~

Xem kết quả fetch gần nhất:

~~~bash
git show -s --oneline FETCH_HEAD
~~~

Nếu cần theo dõi nhánh remote lâu dài, hãy dùng remote-tracking branch như `origin/main`, không coi `FETCH_HEAD` là nhánh.

### 3.4. Giới hạn của FETCH_HEAD

- Một lần fetch mới thường ghi đè nội dung `FETCH_HEAD` trước đó. Có tùy chọn `--append` để nối thêm thông tin, nhưng đây không phải cơ chế lưu lịch sử lâu dài.
- Tệp có thể chứa nhiều dòng từ nhiều ref, trong đó có dòng được đánh dấu không dùng để merge; không nên mặc định chỉ có một dòng hoặc một nhánh.
- `FETCH_HEAD` không phải branch và không phải remote-tracking branch.
- Nó không có nghĩa các commit đã được merge vào nhánh hiện tại.
- Fetch chỉ tải đối tượng và cập nhật tham chiếu theo cấu hình; nó không tự tích hợp thay đổi vào working tree.
- Nếu muốn xem dữ liệu remote mới nhất, hãy fetch lại đúng remote và ref trước khi kiểm tra.

## 4. MERGE_HEAD — commit đang được merge vào HEAD

### 4.1. Vai trò của MERGE_HEAD

Khi Git thực hiện một merge cần giữ trạng thái tích hợp để tạo merge commit, Git ghi commit được merge vào `MERGE_HEAD`. Trong merge thông thường, `HEAD` là nhánh hiện tại (phía đang nhận thay đổi), còn `MERGE_HEAD` là commit phía được đưa vào.

Ví dụ:

~~~text
main:    A --- B --- C  (HEAD)
feature: A --- D --- E  (MERGE_HEAD)
~~~

Khi đang merge `feature/payment` vào `main`:

- `HEAD` vẫn chỉ đến `C` trong lúc merge đang diễn ra.
- `MERGE_HEAD` ghi nhận commit `E` được tích hợp.
- Index có thể chứa các stage của những tệp đang xung đột.
- Working tree chứa nội dung đã được Git tự kết hợp và các dấu conflict cần người dùng xử lý.

Kiểm tra trạng thái:

~~~bash
git status
git show -s --oneline MERGE_HEAD
~~~

Nếu `MERGE_HEAD` không phân giải được, có thể không có merge đang diễn ra hoặc merge đã kết thúc/hủy.

### 4.2. MERGE_HEAD xuất hiện trong quá trình merge

Ví dụ bắt đầu merge:

~~~bash
git switch main
git merge feature/payment
~~~

Nếu Git không thể fast-forward và cần tạo merge commit, nó lưu trạng thái merge để bạn có thể giải quyết conflict rồi hoàn tất. Khi merge có xung đột:

~~~bash
git status
git ls-files -u
git show -s --oneline HEAD
git show -s --oneline MERGE_HEAD
~~~

- `HEAD` cho biết commit của nhánh hiện tại trước khi hoàn tất merge.
- `MERGE_HEAD` cho biết commit được đưa vào. Với octopus merge, tệp này có thể ghi nhiều commit đầu vào; ví dụ lệnh `git show MERGE_HEAD` trong bài giả định merge thông thường với một commit đầu vào.
- `git ls-files -u` cho biết các mục index chưa hợp nhất và các stage liên quan.

Khi xử lý xong các tệp xung đột:

~~~bash
git add src/PaymentService.java
git status
git merge --continue
~~~

Git tạo merge commit với các parent tương ứng và kết thúc trạng thái merge. Sau khi hoàn tất, `MERGE_HEAD` được xóa.

### 4.3. Hủy merge đang diễn ra

Nếu quyết định không tiếp tục merge, dùng:

~~~bash
git merge --abort
~~~

Lệnh yêu cầu Git hủy merge đang diễn ra và đưa working tree/index trở lại trạng thái trước khi bắt đầu merge trong phạm vi Git có thể khôi phục.

Sau khi abort:

~~~bash
git status
git show -s --oneline HEAD
~~~

`MERGE_HEAD` không còn đại diện cho một merge đang diễn ra. Nếu có thay đổi chưa commit trước khi bắt đầu merge, Git có thể không khôi phục chúng hoàn hảo trong mọi tình huống. Vì vậy, hãy commit hoặc stash thay đổi trước khi merge nếu chúng quan trọng.

### 4.4. MERGE_HEAD không phải lúc nào cũng tồn tại

Không phải mọi lệnh có chữ merge đều tạo `MERGE_HEAD`:

- Merge fast-forward chỉ di chuyển nhánh đến commit mới hơn, không cần giữ trạng thái chờ tạo merge commit.
- `git merge --squash` chuẩn bị nội dung trong index và working tree như một lần merge nhưng không ghi nhận merge theo cách thông thường và không tạo `MERGE_HEAD` để hoàn tất bằng merge commit.
- Sau khi merge commit hoàn tất hoặc merge bị abort, `MERGE_HEAD` được dọn khỏi trạng thái thao tác.

Do đó, không thể dùng sự tồn tại hay vắng mặt của `MERGE_HEAD` để kết luận mọi thay đổi đã được merge hay chưa. Hãy kết hợp `git status`, lịch sử commit và trạng thái nhánh.

## 5. Phân biệt ba pseudo-ref trong cùng một tình huống

Giả sử bạn đang ở `main`, muốn lấy thay đổi từ `origin/main` và tích hợp vào nhánh hiện tại. Sau đó phát sinh conflict.

Trình tự khái quát:

~~~text
Trước fetch:
HEAD -> commit A

Fetch:
FETCH_HEAD -> commit B (vừa lấy từ remote)

Bắt đầu merge:
HEAD -> commit A
MERGE_HEAD -> commit B

ORIG_HEAD:
commit A (mốc HEAD trước thao tác merge)
~~~

Vai trò trong từng thời điểm:

| Thời điểm | ORIG_HEAD | FETCH_HEAD | MERGE_HEAD |
| --- | --- | --- | --- |
| Trước fetch | Có thể giữ mốc từ thao tác trước; không nhất thiết mới | Có thể là kết quả fetch cũ hoặc chưa có | Thường không có nếu không merge |
| Sau fetch | Không phải mục tiêu chính của fetch | Ghi nhận commit/ref vừa fetch | Chưa có nếu chưa bắt đầu merge |
| Trong merge đang chờ xử lý | Thường giữ mốc HEAD trước merge | Vẫn ghi nhận kết quả fetch nếu chưa bị lần fetch khác ghi đè | Ghi nhận commit đang được merge |
| Sau merge commit | Có thể vẫn giữ mốc trước merge | Vẫn là kết quả fetch gần nhất cho đến lần fetch khác | Được dọn sau khi merge hoàn tất |
| Sau abort merge | Có thể vẫn tham chiếu mốc trước thao tác | Không tự trở thành backup | Được dọn khi merge bị hủy |

Đây là mô hình khái quát. Giá trị cụ thể phụ thuộc lệnh đã chạy và các thao tác tiếp theo. Không nên giả định ba tệp luôn cùng tồn tại hoặc cùng mô tả một lần tích hợp.

## 6. Quy trình điều tra khi pull hoặc merge gặp lỗi

Khi `git pull` báo conflict hoặc repository đang ở trạng thái merge dở, hãy kiểm tra theo trình tự.

### Bước 1 — Xác định thao tác hiện tại

~~~bash
git status
git branch --show-current
~~~

Thông báo của Git cho biết có merge đang diễn ra, các tệp chưa hợp nhất và hướng xử lý tiếp theo.

### Bước 2 — Xem mốc trước thao tác và commit được đưa vào

~~~bash
git show -s --oneline ORIG_HEAD
git show -s --oneline FETCH_HEAD
git show -s --oneline MERGE_HEAD
~~~

Một số lệnh có thể báo không tìm thấy tên pseudo-ref nếu thao tác tương ứng chưa xảy ra hoặc đã kết thúc. Đây là thông tin hữu ích, không phải lý do để tự tạo file hay sửa metadata thủ công.

### Bước 3 — Xem các commit và nội dung liên quan

~~~bash
git log --oneline --graph --decorate -10
git diff
git diff --cached
git ls-files -u
~~~

Dùng lịch sử để xác định nhánh hiện tại, commit đầu vào và các tệp đang xung đột. Nếu cần so sánh hai commit cụ thể, dùng `git diff <commit-a> <commit-b>`.

### Bước 4 — Chọn tiếp tục hay hủy

Nếu muốn tiếp tục:

~~~bash
git add <file-da-giai-quyet>
git merge --continue
~~~

Nếu muốn hủy merge đang diễn ra:

~~~bash
git merge --abort
~~~

Không xóa thủ công `MERGE_HEAD` hoặc các tệp trong Git directory để kết thúc merge. Hãy dùng lệnh Git tương ứng để index, working tree và metadata được cập nhật nhất quán.

## 7. ORIG_HEAD và reflog: dùng gì để khôi phục?

`ORIG_HEAD` tiện lợi khi bạn cần mốc trước một thao tác gần đây. Nhưng vì nó có thể bị ghi đè, reflog thường hữu ích hơn khi cần tìm lịch sử di chuyển HEAD.

Xem reflog:

~~~bash
git reflog --date=local
~~~

Ví dụ, reflog có thể ghi lại:

- HEAD trước merge.
- HEAD sau merge.
- HEAD sau reset.
- Các lần checkout hoặc rebase.

Sau khi xác định commit cần cứu, tạo một nhánh backup:

~~~bash
git branch rescue/before-merge <commit-can-cuu>
~~~

Nếu commit cần cứu chính là `ORIG_HEAD`, có thể dùng:

~~~bash
git branch rescue/before-merge ORIG_HEAD
~~~

Nhánh cứu hộ tạo một tham chiếu ổn định hơn đến commit trong repository. Nó vẫn không sao lưu các thay đổi chưa commit trong working tree hoặc index; nếu cần giữ cả những phần đó, hãy bảo toàn riêng trước khi thực hiện thao tác tiếp theo.

Reflog là dữ liệu cục bộ và có thời hạn lưu giữ. Nó không thay thế backup repository hoặc remote.

## 8. Những sai lầm thường gặp

- **Coi ORIG_HEAD là backup vĩnh viễn:** giá trị có thể bị thao tác Git tiếp theo ghi đè. Kiểm tra sớm và tạo nhánh backup nếu cần.
- **Nhầm FETCH_HEAD với origin/main:** FETCH_HEAD ghi kết quả fetch gần nhất; remote-tracking branch là tham chiếu theo dõi nhánh remote lâu dài.
- **Cho rằng fetch đã merge:** fetch tải đối tượng và cập nhật thông tin; nó không tự tích hợp thay đổi vào nhánh hiện tại.
- **Cho rằng MERGE_HEAD là nhánh đích:** nó ghi commit đang được merge vào HEAD, không phải tên nhánh local mà bạn đang checkout.
- **Dùng reset --hard ORIG_HEAD khi merge còn đang dở:** nếu merge chưa hoàn tất, `git merge --abort` thường là lệnh phù hợp hơn.
- **Dùng ORIG_HEAD mà không xem commit thực tế:** pseudo-ref có thể đã được cập nhật bởi thao tác khác. Xem `git show` và `git reflog` trước khi reset.
- **Xóa thủ công file metadata trong Git directory:** có thể làm trạng thái index và thao tác đang dở không nhất quán. Dùng `git merge --continue` hoặc `git merge --abort`.
- **Giả định MERGE_HEAD tồn tại trong mọi kiểu merge:** fast-forward và squash merge có hành vi khác merge commit thông thường.

## 9. Bảng tra cứu nhanh

| Mục tiêu | Lệnh |
| --- | --- |
| Xem mốc trước thao tác | `git show -s --oneline ORIG_HEAD` |
| Kiểm tra ORIG_HEAD có phải commit hợp lệ | `git rev-parse --verify 'ORIG_HEAD^{commit}'` |
| Xem commit vừa fetch | `git show -s --oneline FETCH_HEAD` |
| Xem commit đang được merge | `git show -s --oneline MERGE_HEAD` |
| Xem vị trí Git directory | `git rev-parse --git-dir` |
| Xem đường dẫn pseudo-ref | `git rev-parse --git-path FETCH_HEAD` |
| Xem lịch sử di chuyển HEAD | `git reflog --date=local` |
| Xem trạng thái merge/conflict | `git status` |
| Xem các mục chưa hợp nhất | `git ls-files -u` |
| Tiếp tục merge | `git merge --continue` |
| Hủy merge đang diễn ra | `git merge --abort` |
| Tạo nhánh cứu hộ từ ORIG_HEAD | `git branch rescue/before-merge ORIG_HEAD` |

## 10. Tổng kết

`ORIG_HEAD`, `FETCH_HEAD` và `MERGE_HEAD` giúp bạn hiểu Git đang ở đâu trong một chu trình đồng bộ hoặc tích hợp. `ORIG_HEAD` ghi lại mốc HEAD trước một số thao tác quan trọng; `FETCH_HEAD` ghi kết quả fetch gần nhất; `MERGE_HEAD` ghi commit đang được merge vào HEAD khi Git giữ trạng thái merge chờ hoàn tất.

Chúng là các dấu mốc phục vụ thao tác, không phải ba nhánh backup có thể dựa vào lâu dài. Khi cần điều tra, hãy kết hợp chúng với `git status`, `git log`, `git diff` và `git reflog`. Khi cần khôi phục, xác nhận commit đích và trạng thái working tree trước khi dùng reset, tiếp tục merge hoặc abort. Cách kiểm tra này giúp bạn xử lý sự cố đồng bộ có căn cứ và bảo toàn lịch sử quan trọng của repository.


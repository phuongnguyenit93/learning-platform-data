# Hợp nhất squash và ảnh hưởng đến quan hệ lịch sử

Squash merge gộp thay đổi từ một nhánh thành một commit duy nhất trên nhánh đích. Cách làm này giúp lịch sử của nhánh chính gọn hơn, nhưng có một hệ quả quan trọng: commit squash không ghi nhận commit của nhánh nguồn là tổ tiên của nó. Git lưu kết quả nội dung trong một commit mới, còn quan hệ ancestry giữa hai nhánh vẫn tách biệt.

Vì vậy, sau khi squash, Git có thể xem nhánh nguồn là chưa được merge dù nội dung của nó đã xuất hiện trong nhánh đích. Điều này ảnh hưởng đến việc kiểm tra branch đã merge, xóa branch, tiếp tục phát triển trên branch cũ và thực hiện lần merge tiếp theo.

Bài học thuộc chương **Hợp nhất nhánh** của module `SOURCE_CONTROL_GIT`. Module hướng dẫn working tree, staging area, commit, lịch sử, branch, merge, rebase, remote và tag; hiểu cả kết quả nội dung lẫn quan hệ lịch sử giúp bạn chọn cách hợp nhất phù hợp với quy trình cộng tác.

## 1. Squash merge là gì?

Squash merge lấy tổng hợp thay đổi của nhánh nguồn so với điểm chung, áp dụng chúng lên nhánh đích và chuẩn bị một snapshot để bạn tạo commit mới. Các commit riêng lẻ trên nhánh nguồn không trở thành parent của commit mới.

Giả sử lịch sử ban đầu:

~~~text
A---B---C  feature
 \
  (main)
~~~

Trong đó:

- `A` là commit chung ban đầu.
- `B` và `C` là hai commit trên nhánh `feature`.
- Nhánh `main` vẫn đang ở `A`.

Sau khi squash các thay đổi của `feature` vào `main` và tạo commit `S`, lịch sử có dạng:

~~~text
A---B---C  feature
 \
  S        main
~~~

Commit `S` có parent là `A`. Nó chứa snapshot kết quả sau khi tích hợp thay đổi, nhưng không có `C` làm parent. Vì vậy, `B` và `C` không nằm trên ancestry path của `main`.

Đây là điểm phân biệt quan trọng giữa “đã đưa nội dung vào” và “đã ghi nhận lịch sử nhánh nguồn là tổ tiên”.

## 2. Tạo squash merge bằng Git

Trước khi hợp nhất, chuyển sang nhánh đích và kiểm tra working tree:

~~~bash
git status
git switch main
git fetch origin
~~~

Nếu nhánh đích cần cập nhật từ remote, tích hợp thay đổi theo chính sách của nhóm trước khi squash. Tiếp theo, xem lịch sử và phạm vi thay đổi của nhánh nguồn:

~~~bash
git log --oneline --graph --decorate --all
git diff --stat main...feature
git diff main...feature
~~~

`git diff main...feature` so sánh nhánh nguồn với merge base chung, giúp xem phần thay đổi mà feature mang đến kể từ điểm phân nhánh.

Thực hiện squash:

~~~bash
git merge --squash feature
~~~

Git áp dụng kết quả hợp nhất vào working tree và index. Lệnh này không tự tạo commit, không di chuyển `HEAD` và không ghi `MERGE_HEAD` như một merge thông thường.

Kiểm tra nội dung đã stage:

~~~bash
git status
git diff --cached --stat
git diff --cached
~~~

Nếu kết quả đúng, tạo commit:

~~~bash
git commit -m "Add payment workflow"
~~~

Commit mới là một commit thông thường trên `main`, có một parent là commit trước đó của `main`. Nó lưu toàn bộ snapshot sau squash.

### Không phải cứ chạy git merge --squash là đã có commit

Lệnh `git merge --squash` chỉ chuẩn bị index và working tree. Bạn vẫn cần kiểm tra nội dung rồi chạy `git commit`. Nếu chưa commit, thay đổi vẫn là staged/working-tree changes local, chưa có mốc lịch sử mới.

## 3. So sánh squash merge với merge commit và rebase

Ba cách này có thể đưa thay đổi đến cùng một kết quả nội dung, nhưng tạo quan hệ lịch sử khác nhau.

| Cách tích hợp | Kết quả trên nhánh đích | Parent của commit mới | Commit nhánh nguồn có trở thành tổ tiên? |
| --- | --- | --- | --- |
| Squash merge | Một commit chứa tổng hợp thay đổi | Một parent: commit trước đó của nhánh đích | Không |
| Merge commit | Một merge commit ghi nhận việc hợp nhất | Thường có hai parent: đích và nguồn | Có |
| Rebase rồi fast-forward | Các commit nguồn được phát lại trên nền mới rồi nhánh đích tiến tới tip mới | Mỗi commit được phát lại có một parent | Có, dưới dạng các commit đã viết lại nằm trên nhánh đích |

Ví dụ merge commit:

~~~text
A---M  main
 \ /
  B---C  feature
~~~

`M` có hai parent: commit trước merge trên `main` và tip `feature`. Git có thể đi ngược ancestry từ `M` đến `C`, nên nhận biết các commit của feature đã được tích hợp theo quan hệ lịch sử.

Ví dụ squash:

~~~text
A---B---C  feature
 \
  S        main
~~~

`S` chỉ có parent `A`. Git không thể suy ra `B` và `C` đã được tích hợp chỉ từ ancestry.

Ví dụ rebase rồi fast-forward:

~~~text
A---B'---C'  main, feature (sau rebase)
~~~

`B'` và `C'` là các commit mới được tạo lại trên nền `A` hoặc nền mới hơn. Nội dung có thể tương đương commit cũ nhưng hash thay đổi vì parent và metadata commit thay đổi.

### Squash merge khác với interactive rebase squash

- `git merge --squash feature` áp dụng thay đổi của branch nguồn vào branch đích và tạo một commit mới sau đó.
- Trong interactive rebase, lệnh `squash` hoặc `fixup` kết hợp commit trong chuỗi commit đang được viết lại. Rebase tạo lại commit history của branch đó.

Cả hai có thể làm số commit giảm, nhưng phạm vi thao tác và quan hệ lịch sử khác nhau.

## 4. Commit squash ghi nhận điều gì?

Commit squash là commit bình thường. Nó có:

- Một commit ID riêng.
- Author và committer metadata.
- Commit message.
- Một parent commit trên nhánh đích.
- Tree snapshot chứa kết quả các thay đổi đã hợp nhất.

Nó không tự lưu danh sách commit nguồn như các parent. Các commit message, tác giả và ranh giới từng commit trên branch nguồn cũng không tự động được ghép vào metadata của commit squash.

Nếu cần ghi nhận đóng góp hoặc liên kết review, có thể đưa mã pull request, issue, tên tính năng hoặc trailer như `Co-authored-by` vào commit message theo quy ước dự án.

Ví dụ:

~~~text
Add payment workflow

Combines validation, payment form and invoice updates.
Reviewed in PR #248.

Co-authored-by: Tran Binh <binh@example.com>
~~~

Trailer chỉ là thông tin trong commit message; nó không tạo quan hệ ancestry đến các commit nguồn.

## 5. Xác minh commit squash và parent

Sau khi tạo commit, kiểm tra nội dung:

~~~bash
git show --stat --oneline HEAD
git show --format=fuller HEAD
~~~

Xem commit object và parent:

~~~bash
git cat-file -p HEAD
~~~

Hoặc chỉ xem parent hash:

~~~bash
git rev-list --parents -n 1 HEAD
~~~

Với commit squash thông thường, dòng đầu tiên có commit ID mới và chỉ một parent. Merge commit thường hiển thị hai parent trở lên.

Xem đồ thị toàn bộ refs:

~~~bash
git log --oneline --graph --decorate --all
~~~

Kiểm tra commit tip của feature có phải tổ tiên của main không:

~~~bash
git merge-base --is-ancestor feature main
~~~

Sau squash merge, lệnh này thường trả exit code khác 0 vì tip `feature` không phải tổ tiên của `main`. Điều đó không tự chứng minh nội dung feature chưa được đưa vào main; nó chỉ nói quan hệ ancestry chưa được ghi nhận.

## 6. Vì sao branch vẫn được xem là chưa merge?

Git xác định một branch đã merge bằng quan hệ commit ancestry, không chỉ bằng cách so sánh nội dung tệp.

Sau squash:

~~~bash
git branch --merged main
~~~

Branch `feature` thường không xuất hiện trong danh sách, vì tip của nó không phải tổ tiên của `main`.

Lệnh xóa branch an toàn:

~~~bash
git branch -d feature
~~~

có thể từ chối xóa với thông báo branch chưa được merge. Đây là hành vi có chủ đích: Git không biết commit nguồn đã được tổng hợp vào một commit khác bằng squash.

Không nên lập tức dùng `git branch -D feature` chỉ để bỏ cảnh báo. Trước tiên, xác minh commit squash có chứa đúng nội dung mong muốn, kiểm tra pull request hoặc review record, và xác định chính sách lưu giữ lịch sử nguồn.

Nếu đã xác nhận có thể xóa branch local:

~~~bash
git branch -D feature
~~~

Lệnh này xóa ref branch local. Nó không xóa commit squash trên `main`. Tuy nhiên, nếu các commit nguồn không còn ref nào khác giữ lại, chúng có thể trở thành unreachable và được Git thu hồi sau các chu kỳ garbage collection.

Để xóa branch nguồn trên remote sau khi nhóm xác nhận:

~~~bash
git push origin --delete feature
~~~

Việc xóa branch remote cũng cần tuân theo chính sách review và lưu trữ của nhóm.

## 7. Nội dung giống nhau nhưng lịch sử vẫn khác

Một điểm dễ gây nhầm lẫn: sau squash merge, cây tệp của `main` và `feature` có thể giống hệt nhau, nhưng Git vẫn không xem tip feature là tổ tiên của main.

Ví dụ, nếu commit `S` trên main chứa cùng snapshot với commit `C` trên feature:

~~~bash
git diff main feature
~~~

có thể không hiển thị khác biệt nội dung. Tuy nhiên:

~~~bash
git merge-base --is-ancestor feature main
~~~

vẫn có thể trả về false.

Hai lệnh đang trả lời hai câu hỏi khác nhau:

- `git diff` so sánh nội dung tree.
- `git merge-base --is-ancestor` kiểm tra quan hệ tổ tiên giữa các commit.

Tương tự, xem các commit chỉ có ở mỗi phía:

~~~bash
git log --oneline --left-right main...feature
~~~

Bạn vẫn có thể thấy `S` ở phía main và `B`, `C` ở phía feature. Các commit này khác nhau về ID và ancestry dù snapshot cuối cùng có thể giống nhau.

Đây là lý do không thể chỉ nhìn trạng thái file để kết luận Git đã ghi nhận nhánh nguồn là merged.

## 8. Điều gì xảy ra nếu tiếp tục dùng branch nguồn sau squash?

Giả sử bạn squash `feature` vào `main` bằng commit `S` nhưng vẫn giữ branch `feature` ở `C`.

Sau đó bạn tạo thêm commit `D` trên feature:

~~~text
A---B---C---D  feature
 \
  S            main
~~~

Khi merge feature vào main lần nữa, Git vẫn dùng `A` làm merge base vì `B` và `C` chưa nằm trong ancestry của `main`. Git sẽ xem các thay đổi từ A đến D ở phía feature và các thay đổi từ A đến S ở phía main.

Nếu snapshot S đã chứa chính xác thay đổi B và C, merge có thể nhận ra một phần nội dung đã có, nhưng không có cam kết rằng mọi lần tích hợp tiếp theo đều tự động sạch. Các chỉnh sửa khác nhau trên cùng vùng, cách giải quyết conflict trước đó hoặc thay đổi mới có thể tạo conflict hoặc kết quả không mong muốn.

Vì vậy, sau khi squash một pull request, quy trình phổ biến là:

1. Xác nhận commit squash đã được đưa vào branch đích.
2. Đóng pull request và xóa branch nguồn theo chính sách.
3. Tạo branch tính năng tiếp theo từ branch đích mới nhất.

Ví dụ:

~~~bash
git switch main
git pull --ff-only
git switch -c feature/payment-receipts
~~~

Branch mới bắt đầu từ lịch sử đã chứa commit squash, nên lần phát triển tiếp theo có merge base phù hợp với main.

Nếu cần tiếp tục branch cũ vì lý do công việc, hãy thống nhất cách đồng bộ lại với nhánh đích và kiểm tra kỹ patch/ancestry trước lần tích hợp tiếp theo. Không mặc định rằng squash đã khiến Git đánh dấu mọi commit nguồn là đã merge.

## 9. Giữ lịch sử branch nguồn khi cần audit

Squash làm lịch sử trên branch đích gọn hơn, nhưng có thể làm mất đường đi trực tiếp từ branch đích đến từng commit nguồn. Nếu nhóm cần truy vết chi tiết, hãy quyết định cách lưu lịch sử trước khi xóa branch.

Một số lựa chọn:

- Giữ branch nguồn trên remote trong thời hạn quy định.
- Tạo tag lưu mốc tip nguồn theo chính sách đặt tên của nhóm.
- Giữ pull request, review record và commit links trên nền tảng quản lý mã.
- Lưu bundle hoặc snapshot repository nếu yêu cầu lưu trữ dài hạn.

Ví dụ tạo tag lưu mốc branch trước khi xóa:

~~~bash
git tag archive/feature-payment feature
git push origin refs/tags/archive/feature-payment
~~~

Tag này giữ một ref đến tip feature. Nó không làm commit nguồn trở thành tổ tiên của main, nhưng giữ cho commit chain đó có thể truy cập qua tag.

Tag không tự bất biến về mặt kỹ thuật: người có quyền có thể xóa hoặc di chuyển tag. Nếu yêu cầu audit nghiêm ngặt, dùng chính sách bảo vệ tag và backup có retention phù hợp.

## 10. Revert squash commit khác revert merge commit

Vì commit squash là commit bình thường có một parent, có thể hoàn tác bằng:

~~~bash
git revert <squash-commit>
~~~

Git tạo một commit mới đảo ngược thay đổi của commit squash. Không cần chỉ định mainline parent.

Với merge commit có nhiều parent, revert cần chọn parent chính, thường dùng `-m 1` nếu muốn giữ nhánh đích làm mainline:

~~~bash
git revert -m 1 <merge-commit>
~~~

Không dùng cú pháp revert merge commit cho squash commit. Hãy kiểm tra số parent trước:

~~~bash
git rev-list --parents -n 1 <commit>
~~~

Việc revert không xóa commit cũ; nó thêm một commit mới để đảo nội dung. Nếu commit squash đã được chia sẻ, đây thường là cách an toàn hơn viết lại lịch sử branch chung.

## 11. Xử lý conflict khi squash

Squash merge dùng cơ chế hợp nhất nội dung tương tự merge. Nếu cùng vùng được sửa ở hai phía, Git có thể dừng với conflict.

Thực hiện:

~~~bash
git merge --squash feature
git status
~~~

Xem các tệp chưa hợp nhất:

~~~bash
git diff --name-only --diff-filter=U
~~~

Mở từng tệp, giải quyết conflict marker, sau đó stage kết quả:

~~~bash
git add path/to/resolved-file
git diff --cached
~~~

Khi tất cả đường dẫn đã được giải quyết và nội dung staged đúng, tạo commit bình thường:

~~~bash
git commit -m "Integrate feature with squash"
~~~

Vì `git merge --squash` không ghi `MERGE_HEAD`, nó không tạo trạng thái merge thông thường để tiếp tục bằng `git merge --continue`. Hãy kiểm tra trạng thái thực tế và hoàn tất bằng commit sau khi đã stage các tệp được giải quyết.

Nếu muốn bỏ kết quả squash đang dở, trước hết bảo toàn các thay đổi local đã tồn tại trước khi merge. Squash không lưu merge metadata như merge thông thường, nên đừng mặc định `git merge --abort` có thể khôi phục chính xác trạng thái ban đầu. Chỉ dùng các lệnh khôi phục index/working tree sau khi đã kiểm tra và sao lưu nội dung cần giữ.

## 12. Chọn squash merge khi nào?

Squash phù hợp khi nhóm muốn branch chính có một commit đại diện cho một đơn vị thay đổi, ví dụ một pull request hoặc một tính năng nhỏ.

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Feature branch có nhiều commit thử nghiệm, sửa typo và fixup | Squash merge | Gộp thành một commit dễ đọc trên main |
| Cần giữ từng commit và quan hệ merge của nhánh | Merge commit | Lưu parent của cả hai nhánh |
| Muốn lịch sử tuyến tính nhưng giữ các commit riêng | Rebase rồi fast-forward | Commit được phát lại trên nền mới và vẫn xuất hiện riêng |
| Nhánh có yêu cầu audit về quá trình tích hợp | Merge commit hoặc giữ thêm refs/review records | Dễ truy lại chuỗi commit nguồn |
| Nhánh ngắn, một đơn vị công việc độc lập | Squash merge có thể phù hợp | Một commit đại diện cho thay đổi |

Không có một chiến lược tốt nhất cho mọi repository. Hãy thống nhất trong nhóm về việc commit trên main cần thể hiện từng bước phát triển hay chỉ cần snapshot hoàn chỉnh cho từng thay đổi.

## 13. Quy trình squash merge có kiểm soát

Một trình tự thực tế:

~~~bash
# 1. Kiểm tra trạng thái local
git status

# 2. Chuyển sang branch đích và cập nhật
git switch main
git fetch origin
git pull --ff-only

# 3. Review lịch sử và thay đổi của branch nguồn
git log --oneline --graph --decorate main...feature
git diff --stat main...feature
git diff main...feature

# 4. Squash thay đổi vào index và working tree
git merge --squash feature

# 5. Review nội dung sẽ commit
git status
git diff
git diff --cached --stat
git diff --cached

# 6. Tạo một commit mới trên branch đích
git commit -m "Add payment workflow"

# 7. Xác minh commit và ancestry
git show --stat --oneline HEAD
git rev-list --parents -n 1 HEAD
git merge-base --is-ancestor feature main

# 8. Push branch đích
git push origin main
~~~

Lệnh `git merge-base --is-ancestor feature main` ở bước 7 thường trả false sau squash; đây là kết quả dự kiến. Hãy đánh giá nội dung đã tích hợp bằng commit diff, review record và kiểm tra tree, không dựa riêng vào ancestry.

Chỉ xóa branch nguồn sau khi đã xác minh commit đích, quyết định retention và xác nhận nhóm không cần tiếp tục phát triển trên branch đó.

## 14. Sơ đồ quan hệ lịch sử

~~~mermaid
flowchart TD
    A[Commit chung A] --> B[Commit feature B]
    B --> C[Commit feature C]
    A --> S[Squash commit S trên main]
    C -. Không là parent của S .-> S
    S --> T[Commit tiếp theo trên main]
    C --> D[Commit tiếp theo nếu vẫn dùng feature]
~~~

Đường liền biểu thị quan hệ parent-child. Đường nét đứt chỉ thể hiện rằng hai nhánh có liên quan về nội dung công việc, không phải quan hệ ancestry được Git ghi trong commit.

Trước khi kết thúc, hãy tự xác nhận:

1. Tôi có phân biệt squash merge với merge commit và interactive rebase squash không?
2. Tôi hiểu commit squash chỉ có parent thuộc nhánh đích không?
3. Tôi đã review staged diff trước khi tạo commit chưa?
4. Tôi hiểu vì sao `git branch --merged` có thể không liệt kê branch đã squash chưa?
5. Tôi đã quyết định giữ hay xóa branch nguồn dựa trên retention và nhu cầu audit chưa?
6. Nếu tiếp tục phát triển, tôi có tạo branch mới từ nhánh đích đã cập nhật không?
7. Tôi biết revert squash commit là revert commit thường, không cần mainline `-m` không?

Squash merge giúp lịch sử nhánh đích gọn bằng cách lưu một commit chứa kết quả thay đổi. Đổi lại, commit nguồn không trở thành tổ tiên của commit squash. Hãy quản lý branch nguồn, lần merge tiếp theo và yêu cầu audit theo đúng hệ quả này; đừng đánh đồng việc nội dung đã có trong tree với việc lịch sử đã được nối bằng ancestry.

## Tài liệu tham khảo

- [Git documentation: git-merge](https://git-scm.com/docs/git-merge) — tùy chọn `--squash`, merge strategies và xử lý kết quả hợp nhất.
- [Git documentation: git-commit](https://git-scm.com/docs/git-commit) — tạo commit từ index.
- [Git documentation: git-merge-base](https://git-scm.com/docs/git-merge-base) — tìm common ancestor và kiểm tra quan hệ ancestry.
- [Git documentation: git-branch](https://git-scm.com/docs/git-branch) — kiểm tra branch đã merge và xóa branch.
- [Git documentation: git-revert](https://git-scm.com/docs/git-revert) — hoàn tác commit thường và merge commit.
- [Pro Git: Basic Branching and Merging](https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging) — mô hình branch và các cách hợp nhất.

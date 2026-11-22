# Làm gọn nhánh trước khi bàn giao bằng interactive rebase

Trong quá trình phát triển một tính năng, lịch sử commit trên nhánh cá nhân thường ghi lại cả những bước thử nghiệm: sửa lỗi chính tả, thêm log để debug, điều chỉnh test, đổi tên biến hoặc sửa lại một commit vừa tạo. Những commit nhỏ này hữu ích khi đang làm việc, nhưng nếu bàn giao nguyên trạng, người review có thể phải đọc một chuỗi thay đổi rời rạc để hiểu một kết quả hoàn chỉnh.

`git rebase -i` (interactive rebase) cho phép sắp xếp, gộp, đổi thông điệp, chỉnh sửa hoặc loại bỏ commit trước khi bàn giao. Bài thực hành này mô phỏng toàn bộ quy trình: kiểm tra nhánh, bảo vệ lịch sử ban đầu, cập nhật nhánh nền, làm gọn commit, xử lý conflict, chạy kiểm tra và bàn giao lịch sử rõ ràng.

Đây là thao tác viết lại lịch sử. Mã commit có thể thay đổi, vì vậy cần xác định nhánh đã được chia sẻ hay chưa và thống nhất với nhóm trước khi viết lại một nhánh mà người khác đang sử dụng.

## 1. Kết quả cần đạt

Sau bài thực hành, bạn có thể:

- Xác định chính xác những commit riêng của nhánh tính năng so với nhánh nền.
- Bảo vệ trạng thái hiện tại bằng branch backup và ghi nhận mã commit.
- Dùng interactive rebase để đổi thứ tự, gộp, sửa thông điệp và loại commit.
- Dùng `fixup!` cùng `--autosquash` để gom các commit sửa bổ sung.
- Xử lý conflict trong quá trình replay commit và biết khi nào tiếp tục, bỏ qua hoặc hủy rebase.
- Kiểm tra lịch sử sau khi làm gọn và xác minh nội dung tính năng vẫn đầy đủ.
- Bàn giao nhánh theo quy trình phù hợp với trạng thái đã push hay chưa.

## 2. Tình huống thực hành

Giả sử nhóm đang phát triển chức năng thanh toán. Nhánh nền là `main`, còn nhánh cá nhân là `feature/payment-summary`. Trong lúc làm việc, bạn tạo các commit:

```text
main: A --- B --- C
                  \
feature:           D --- E --- F --- G --- H
```

Ý nghĩa các commit:

| Commit | Nội dung hiện tại | Cách xử lý dự kiến |
| --- | --- | --- |
| D | Thêm model tổng hợp thanh toán | Giữ |
| E | Sửa typo trong model | Gộp vào D |
| F | Thêm service tính tổng tiền | Giữ |
| G | Thêm test cho service | Giữ hoặc gộp vào F tùy chính sách review |
| H | Sửa thông điệp log và tên biến | Gộp vào commit phù hợp |

Mục tiêu là tạo lịch sử dễ review, ví dụ:

```text
main: A --- B --- C
                  \
feature:           D' -------- F' --- G'
```

Trong đó mỗi commit mô tả một phần thay đổi có ý nghĩa. Không có quy tắc bắt buộc mọi nhánh phải chỉ còn một commit; điều quan trọng là lịch sử phản ánh được các đơn vị thay đổi hợp lý và dễ kiểm tra.

## 3. Chuẩn bị repository và xác định phạm vi commit

Trước khi viết lại lịch sử, kiểm tra repository:

```bash
git status -sb
git branch --show-current
git log --oneline --decorate --graph -15
```

Xác nhận bạn đang ở `feature/payment-summary`. Nếu working tree hoặc index có thay đổi chưa commit, hãy xử lý trước:

- Commit phần công việc còn dang dở nếu nó đã có ý nghĩa độc lập.
- Hoặc stash nếu đó là thay đổi tạm thời cần mang theo sau rebase.
- Lưu riêng file untracked quan trọng vì stash mặc định không bao gồm chúng.

Interactive rebase thường cần working tree sạch. Không bắt đầu khi có chỉnh sửa chưa được bảo vệ, vì rebase có thể không chạy hoặc việc giải quyết conflict sẽ khó phân biệt với công việc đang làm.

### Cập nhật thông tin từ remote

```bash
git fetch origin
git status -sb
```

`fetch` cập nhật remote-tracking refs mà không tự merge hoặc rebase thay đổi vào nhánh hiện tại. Xác định nhánh nền thực tế của tính năng; trong bài này dùng `origin/main`.

Xem các commit riêng của nhánh:

```bash
git log --oneline --decorate origin/main..HEAD
```

Toán tử `origin/main..HEAD` liệt kê commit reachable từ `HEAD` nhưng không reachable từ `origin/main`. Đây thường là phạm vi đưa vào interactive rebase:

```bash
git rebase -i origin/main
```

Nếu nhánh nền trong dự án là `develop`, `release/2.x` hoặc một nhánh khác, thay `origin/main` bằng đúng upstream đã thống nhất. Không đoán nhánh nền chỉ từ tên branch.

### Kiểm tra merge base

```bash
git merge-base origin/main HEAD
```

Merge base là commit tổ tiên chung tốt nhất giữa hai đầu lịch sử. Interactive rebase trên `origin/main` sẽ replay các commit của nhánh hiện tại sau điểm chung lên tip mới của `origin/main`. Nếu lịch sử có nhiều merge hoặc nhánh nền thay đổi phức tạp, xem merge base và graph trước khi thao tác.

## 4. Bảo vệ lịch sử trước khi rebase

Tạo branch backup trỏ tới trạng thái hiện tại:

```bash
git branch backup/feature-payment-summary-before-rebase
```

Ghi lại commit hiện tại:

```bash
git rev-parse HEAD
git show --no-patch --oneline HEAD
```

Branch backup là một ref giữ commit và toàn bộ lịch sử reachable từ nó. Nếu kết quả rebase không như mong muốn, bạn vẫn có thể so sánh hoặc tạo lại branch từ mốc này.

Kiểm tra branch backup:

```bash
git branch --list "backup/*"
git log --oneline --decorate backup/feature-payment-summary-before-rebase -10
```

Không xóa branch backup ngay sau khi rebase. Chỉ dọn nó sau khi đã xác nhận nhánh mới, CI và review đều ổn, đồng thời nhóm không còn cần khả năng quay lại lịch sử trước rebase.

### Reflog là lớp hỗ trợ phục hồi

Git ghi lại thay đổi vị trí của `HEAD` và branch trong reflog:

```bash
git reflog --date=local
```

Reflog hữu ích khi vô tình di chuyển branch hoặc cần tìm commit trước rebase. Tuy nhiên, reflog chỉ có tính cục bộ và có thời hạn lưu; branch backup rõ ràng dễ nhận biết hơn khi chuẩn bị một thao tác viết lại lịch sử.

## 5. Mở interactive rebase

Chạy:

```bash
git rebase -i origin/main
```

Git mở editor với danh sách commit theo thứ tự từ cũ đến mới. Ví dụ:

```text
pick 1a2b3c4 Add payment summary model
pick 2b3c4d5 Fix typo in payment model
pick 3c4d5e6 Add payment calculation service
pick 4d5e6f7 Add tests for payment calculation
pick 5e6f7a8 Improve payment log message
```

Mỗi dòng bắt đầu bằng một lệnh điều khiển và mã commit. Bạn có thể thay lệnh hoặc sắp xếp lại các dòng. Git sẽ thực hiện lại chuỗi commit theo thứ tự trong todo list.

Mặc định, editor thường hiển thị hướng dẫn các lệnh được hỗ trợ ở phần dưới. Chỉ sửa các dòng lệnh commit ở đầu danh sách; giữ nguyên phần comment hướng dẫn.

## 6. Các lệnh interactive rebase thường dùng

| Lệnh | Bí danh | Tác dụng |
| --- | --- | --- |
| `pick` | `p` | Giữ commit như hiện tại |
| `reword` | `r` | Giữ thay đổi nhưng sửa commit message |
| `edit` | `e` | Dừng tại commit để sửa nội dung hoặc metadata rồi tiếp tục |
| `squash` | `s` | Gộp commit vào commit trước và cho phép chỉnh sửa message |
| `fixup` | `f` | Gộp commit vào commit trước, bỏ message của commit được gộp |
| `drop` | `d` | Loại commit khỏi lịch sử được tạo lại |
| `exec` | `x` | Chạy một shell command tại vị trí đó trong quá trình rebase |
| `break` |  | Dừng tại vị trí đó để người dùng kiểm tra rồi tiếp tục |

Khi dùng `squash` hoặc `fixup`, commit cần gộp phải nằm sau commit đích trong todo list. Nếu một commit được gộp mà không có commit trước phù hợp, rebase sẽ báo lỗi hoặc không thể thực hiện theo ý muốn.

Các lệnh nâng cao như `label`, `reset` và `merge` được dùng trong todo list khi rebase bảo toàn merge topology, thường kết hợp `--rebase-merges`. Bài thực hành này tập trung vào lịch sử tuyến tính để dễ kiểm soát; không tự xóa hoặc thay đổi các dòng merge do Git sinh ra nếu chưa hiểu topology của nhánh.

## 7. Gộp commit bằng squash và fixup

### Squash: gộp và chỉnh thông điệp

Ví dụ todo list:

```text
pick 1a2b3c4 Add payment summary model
squash 2b3c4d5 Fix typo in payment model
pick 3c4d5e6 Add payment calculation service
pick 4d5e6f7 Add tests for payment calculation
squash 5e6f7a8 Improve payment log message
```

Git gộp thay đổi của commit `2b3c4d5` vào commit trước đó. Vì dùng `squash`, Git mở editor để kết hợp hoặc viết lại thông điệp commit. Tương tự, commit log message được gộp vào commit test ngay trước nó trong ví dụ.

Sau khi gộp, hãy viết message mô tả kết quả cuối cùng, ví dụ:

```text
Add payment summary model
```

hoặc:

```text
Add payment calculation tests and improve diagnostics
```

Không để lại một danh sách message rời rạc như “fix”, “again”, “typo” nếu commit mới cần được người review hiểu độc lập.

### Fixup: gộp và bỏ message phụ

Nếu commit chỉ sửa một chi tiết của commit trước, `fixup` thường phù hợp:

```text
pick 1a2b3c4 Add payment summary model
fixup 2b3c4d5 Fix typo in payment model
pick 3c4d5e6 Add payment calculation service
```

`fixup` giữ message của commit đầu và bỏ message của commit được gộp. Nội dung code của cả hai commit vẫn được kết hợp.

### Không gộp mọi commit theo thói quen

Một commit test có thể nên giữ riêng nếu nhóm muốn review logic và test thành hai đơn vị rõ ràng. Một commit sửa migration hoặc thay đổi API có thể cần được giữ riêng để dễ cherry-pick. Chọn cấu trúc dựa trên cách nhóm review, phát hành và bảo trì.

## 8. Sửa commit message bằng reword

Nếu nội dung commit đúng nhưng message chưa rõ:

```text
pick 1a2b3c4 Add payment summary model
reword 3c4d5e6 Add service
pick 4d5e6f7 Add tests for payment calculation
```

Khi rebase tới commit `3c4d5e6`, Git mở editor để nhập message mới. Ví dụ:

```text
Add service to calculate payment totals
```

Message nên mô tả thay đổi cụ thể, dùng cách diễn đạt nhất quán với quy ước commit của dự án. Không đưa thông tin bí mật, dữ liệu khách hàng hoặc token vào commit message.

## 9. Chỉnh sửa nội dung commit bằng edit

Khi cần sửa code trong một commit cũ, đổi `pick` thành `edit`:

```text
pick 1a2b3c4 Add payment summary model
edit 3c4d5e6 Add payment calculation service
pick 4d5e6f7 Add tests for payment calculation
```

Git dừng sau khi áp dụng commit được đánh dấu `edit`. Lúc này có thể sửa file, stage và amend:

```bash
git status
# Chỉnh sửa file cần thiết
git add src/main/java/PaymentService.java
git commit --amend
```

Nếu chỉ muốn sửa message, có thể dùng `git commit --amend -m "Add payment calculation service"`; nếu cần mở editor thì dùng `git commit --amend`.

Sau khi amend, tiếp tục replay các commit còn lại:

```bash
git rebase --continue
```

Commit hiện tại và các commit được replay sau nó có thể nhận mã mới. Nếu thay đổi được amend làm commit sau không còn áp dụng sạch, Git sẽ dừng với conflict; xử lý như phần conflict bên dưới.

## 10. Loại commit bằng drop

Nếu một commit là thử nghiệm không cần giữ:

```text
pick 1a2b3c4 Add payment summary model
drop 2b3c4d5 Add temporary debug output
pick 3c4d5e6 Add payment calculation service
```

`drop` loại commit khỏi lịch sử mới. Trước khi dùng, kiểm tra diff của commit:

```bash
git show --stat 2b3c4d5
git show 2b3c4d5
```

Không drop commit chỉ vì message xấu hoặc commit nhỏ. Nếu commit chứa một phần logic cần thiết, gộp hoặc chỉnh sửa thay vì xóa. Khi drop một commit mà commit sau phụ thuộc vào nó, các commit sau có thể conflict hoặc tạo ra hành vi không đúng.

## 11. Sắp xếp lại thứ tự commit

Bạn có thể di chuyển các dòng trong todo list. Ví dụ:

```text
pick 1a2b3c4 Add payment summary model
pick 3c4d5e6 Add payment calculation service
pick 4d5e6f7 Add tests for payment calculation
```

Thứ tự commit cần phản ánh dependency. Commit tạo model nên đứng trước commit dùng model; commit test có thể đứng sau code mà nó kiểm tra. Nếu đảo thứ tự, commit ở giữa có thể không build hoặc test được.

Sắp xếp lại commit không chỉ thay đổi cách hiển thị log. Git thực sự replay patch theo thứ tự mới; patch có thể không còn áp dụng sạch hoặc tạo ra trạng thái trung gian không hợp lệ.

Nếu hai commit phụ thuộc chặt chẽ, cân nhắc gộp chúng. Nếu muốn từng commit đều có thể build, hãy kiểm tra từng trạng thái sau rebase hoặc dùng `exec` để chạy test ở các điểm cần thiết.

## 12. Tự động gộp commit bổ sung với autosquash

Git hỗ trợ tạo commit có tiền tố `fixup!` hoặc `squash!` để đánh dấu commit đích.

Ví dụ, sau khi đã commit phần model, bạn phát hiện cần sửa một lỗi nhỏ:

```bash
git add src/main/java/PaymentSummary.java
git commit --fixup=1a2b3c4
```

Git tạo commit message có dạng `fixup! Add payment summary model`. Sau đó chạy:

```bash
git rebase -i --autosquash origin/main
```

Git tự di chuyển các commit `fixup!` và `squash!` tới vị trí commit đích và chọn lệnh `fixup` hoặc `squash` tương ứng trong todo list.

Có thể bật autosquash mặc định:

```bash
git config --global rebase.autoSquash true
```

Hoặc chỉ dùng `--autosquash` cho một lần rebase. Khi tạo fixup commit, nên chỉ định commit đích rõ ràng bằng hash hoặc cú pháp được Git hỗ trợ. Kiểm tra todo list trước khi lưu để chắc chắn commit được gộp vào đúng mục tiêu.

## 13. Dùng exec để kiểm tra tự động trong quá trình rebase

`exec` chèn một lệnh shell vào todo list. Git chạy lệnh tại vị trí tương ứng trong quá trình replay.

Ví dụ:

```text
pick 1a2b3c4 Add payment summary model
exec ./gradlew test --tests PaymentSummaryTest
pick 3c4d5e6 Add payment calculation service
exec ./gradlew test --tests PaymentServiceTest
pick 4d5e6f7 Add tests for payment calculation
```

Nếu lệnh `exec` thất bại, rebase dừng để bạn kiểm tra. Sửa lỗi hoặc điều chỉnh lịch sử rồi tiếp tục bằng `git rebase --continue`; nếu mục tiêu không còn phù hợp, có thể hủy bằng `git rebase --abort`.

Có thể thêm `--exec` trực tiếp:

```bash
git rebase -i --exec "./gradlew test" origin/main
```

Lệnh test cần chạy được ở mọi commit trung gian. Nếu commit đầu tiên chưa có test hoặc build configuration cần thiết, `exec` có thể thất bại dù trạng thái cuối cùng hợp lệ. Chọn test phù hợp với từng giai đoạn hoặc chỉ chạy ở các điểm cần thiết.

## 14. Xử lý conflict trong interactive rebase

Conflict xảy ra khi patch của commit đang replay không thể áp dụng tự động lên trạng thái hiện tại. Git tạm dừng và cho biết file cần xử lý:

```bash
git status
git diff --name-only --diff-filter=U
```

Mở file, xem các marker conflict hoặc dùng merge tool đã cấu hình. Sau khi chọn và chỉnh sửa nội dung cuối:

```bash
git add src/main/java/PaymentService.java
git status
git rebase --continue
```

Lặp lại nếu commit tiếp theo cũng conflict. Đừng chạy `git commit` thủ công để thay thế `git rebase --continue` trong phiên rebase đang dở; Git cần điều khiển quá trình replay và metadata của nó.

### Ba lựa chọn khi gặp conflict

| Lệnh | Khi dùng | Hệ quả |
| --- | --- | --- |
| `git rebase --continue` | Đã giải quyết và stage conflict | Tiếp tục replay commit |
| `git rebase --skip` | Commit hiện tại không còn cần hoặc thay đổi của nó đã được tích hợp theo cách khác | Bỏ commit đang replay |
| `git rebase --abort` | Muốn hủy toàn bộ rebase | Trở về trạng thái trước khi bắt đầu rebase |

Không dùng `--skip` chỉ để vượt qua conflict khó. Nó loại toàn bộ thay đổi của commit hiện tại khỏi lịch sử mới. Kiểm tra `git show REBASE_HEAD` hoặc commit đang được replay để hiểu nội dung trước khi quyết định.

### Kiểm tra trạng thái sau conflict

```bash
git diff
git diff --cached
git ls-files -u
```

Sau khi đã giải quyết và stage, `git ls-files -u` không còn liệt kê file đã xử lý. Chạy test phù hợp trước khi tiếp tục nếu conflict ảnh hưởng tới logic quan trọng.

## 15. Hủy rebase và phục hồi khi kết quả không đúng

Nếu vẫn đang ở giữa phiên rebase và muốn quay lại trạng thái ban đầu:

```bash
git rebase --abort
```

Nếu rebase đã kết thúc nhưng kết quả không đúng, branch backup tạo trước đó là điểm phục hồi rõ ràng:

```bash
git log --oneline --decorate backup/feature-payment-summary-before-rebase -10
```

Có thể tạo branch mới từ backup để kiểm tra:

```bash
git switch -c rescue/payment-summary-before-rebase backup/feature-payment-summary-before-rebase
```

Nếu không tạo backup, reflog có thể giúp tìm vị trí trước rebase:

```bash
git reflog --date=local
```

Tạo branch cứu hộ từ commit đúng trước khi thử thao tác khác:

```bash
git branch rescue/before-interactive-rebase <commit-id>
```

Không chạy `git gc --prune=now` hoặc expire reflog khi đang cần phục hồi commit. Khi branch backup đã tồn tại, giữ nó cho đến khi bàn giao và xác minh hoàn tất.

## 16. Kiểm tra lịch sử sau khi làm gọn

Sau khi rebase hoàn tất:

```bash
git status -sb
git log --oneline --decorate --graph origin/main..HEAD
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
```

Xác nhận:

- Working tree sạch.
- Danh sách commit chỉ gồm các thay đổi thuộc tính năng.
- Message mô tả rõ nội dung.
- Không còn commit debug hoặc thay đổi tạm không cần thiết.
- Thứ tự commit hợp lý và dễ review.
- Diff cuối cùng chứa đầy đủ chức năng mong muốn.

So sánh nội dung trước và sau rebase bằng branch backup:

```bash
git diff backup/feature-payment-summary-before-rebase HEAD
```

Lệnh này so sánh snapshot cuối của hai đầu branch. Vì mục tiêu của rebase là làm gọn lịch sử chứ không đổi sản phẩm cuối, diff giữa hai tip thường nên rỗng hoặc chỉ có khác biệt đã được giải thích. Nếu diff lớn ngoài dự kiến, kiểm tra các commit đã drop, fixup hoặc reorder.

### Kiểm tra commit riêng so với nhánh nền

```bash
git log --oneline origin/main..HEAD
git diff origin/main...HEAD
```

`git log origin/main..HEAD` liệt kê commit riêng của branch. `git diff origin/main...HEAD` so sánh thay đổi từ merge base tới tip branch, phù hợp để xem phần tính năng đóng góp so với nhánh nền.

## 17. Chạy kiểm tra trước khi bàn giao

Chạy các kiểm tra mà dự án yêu cầu. Ví dụ với dự án Java dùng Gradle:

```bash
./gradlew clean test
```

Nếu dự án dùng Maven:

```bash
mvn clean verify
```

Không chạy cả hai nếu dự án chỉ dùng một build tool. Dùng đúng lệnh được quy định trong repository và xác nhận test bao phủ phần thay đổi.

Kiểm tra whitespace và conflict marker:

```bash
git diff --check origin/main...HEAD
git grep -n -E '^(<<<<<<<|=======|>>>>>>>)' -- .
```

Lệnh `git grep` có thể trả mã thoát khác 0 khi không tìm thấy marker; điều đó thường là kết quả mong muốn. Nếu dự án có file tài liệu minh họa chứa marker, kiểm tra thủ công để phân biệt ví dụ hợp lệ với conflict chưa xử lý.

Xem trạng thái cuối:

```bash
git status -sb
git diff --stat origin/main...HEAD
git log --oneline --decorate origin/main..HEAD
```

## 18. Nhánh chưa push và nhánh đã chia sẻ khác nhau

Trước khi rebase, xác định trạng thái chia sẻ:

| Trạng thái nhánh | Cách xử lý |
| --- | --- |
| Chỉ tồn tại local, chưa push | Có thể rebase sau khi backup và kiểm tra |
| Đã push nhưng chỉ mình sử dụng | Có thể cần force update sau khi thống nhất quy trình nhóm |
| Đã được người khác checkout hoặc phát triển tiếp | Không tự ý rewrite; phối hợp lịch đồng bộ trước |
| Nhánh release/main dùng chung | Không tự ý interactive rebase; tuân theo chính sách bảo vệ nhánh |

Rebase tạo commit mới nên commit hash thay đổi. Nếu nhánh đã push, remote vẫn giữ commit cũ cho tới khi được cập nhật. Người khác có thể đang dựa vào commit cũ; force push bất ngờ sẽ khiến lịch sử local của họ lệch với remote.

Với nhánh cá nhân đã push và được phép viết lại, cập nhật remote bằng `--force-with-lease` sau khi xác nhận remote không có commit mới cần giữ:

```bash
git push --force-with-lease origin feature/payment-summary
```

`--force-with-lease` kiểm tra remote ref có còn ở giá trị mà local kỳ vọng trước khi cập nhật. Nó an toàn hơn `--force`, nhưng không thay thế việc trao đổi với đồng đội. Nếu remote đã thay đổi, push bị từ chối; hãy fetch, xem commit mới và quyết định cách tích hợp trước khi thử lại.

Không dùng force push lên `main`, nhánh release hoặc nhánh được bảo vệ nếu không có quy trình quản trị rõ ràng.

## 19. Bàn giao nhánh sau khi rebase

Trước khi tạo pull request hoặc thông báo review:

1. Xác nhận nhánh đang đứng là nhánh tính năng.
2. Xác nhận `git status` sạch.
3. Xác nhận diff cuối cùng so với nhánh nền đúng mục tiêu.
4. Chạy test, lint và kiểm tra mà nhóm yêu cầu.
5. Đọc lại commit message và thứ tự commit.
6. Push nhánh theo quy trình của nhóm.
7. Tạo hoặc cập nhật pull request, mô tả kết quả và các điểm cần reviewer chú ý.

Ví dụ push nhánh chưa từng được publish:

```bash
git push -u origin feature/payment-summary
```

Nếu nhánh đã tồn tại remote và vừa được rewrite, chỉ dùng force-with-lease khi nhóm cho phép:

```bash
git push --force-with-lease origin feature/payment-summary
```

Trong mô tả pull request, nêu rõ chức năng, cách kiểm thử và các quyết định kỹ thuật quan trọng. Không cần liệt kê toàn bộ thao tác sửa nhỏ đã được gộp; lịch sử mới nên tự giải thích được nội dung thay đổi.

## 20. Ví dụ todo list hoàn chỉnh

Giả sử lịch sử ban đầu có năm commit:

```text
pick a111111 Add payment summary model
pick b222222 Fix typo in payment model
pick c333333 Add payment calculation service
pick d444444 Add tests for payment calculation
pick e555555 Improve payment log message
```

Một cách làm gọn:

```text
pick a111111 Add payment summary model
fixup b222222 Fix typo in payment model
pick c333333 Add payment calculation service
pick d444444 Add tests for payment calculation
fixup e555555 Improve payment log message
```

Kết quả còn ba commit có ý nghĩa:

```text
Add payment summary model
Add payment calculation service
Add tests for payment calculation
```

Nếu quy ước nhóm muốn test nằm cùng commit service, có thể squash hoặc fixup commit test vào service. Nếu muốn reviewer đánh giá test độc lập, giữ commit test riêng. Lịch sử tốt là lịch sử giúp người khác hiểu và kiểm tra thay đổi, không phải lịch sử có ít commit nhất.

## 21. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| `rebase` báo working tree dirty | Có thay đổi chưa commit hoặc untracked gây cản trở | Commit/stash và lưu riêng file untracked cần giữ |
| Không thấy commit cần gộp trong todo list | Chọn sai upstream hoặc commit đã reachable từ upstream | Kiểm tra `git log upstream..HEAD` và merge base |
| `squash` không gộp đúng commit | Dòng squash không nằm ngay sau commit đích trong todo list | Sắp xếp lại todo list và kiểm tra thứ tự |
| Rebase conflict sau khi đổi thứ tự | Commit phụ thuộc vào thay đổi của commit trước | Khôi phục thứ tự hợp lý hoặc gộp commit phụ thuộc |
| `--autosquash` không di chuyển commit | Message không khớp commit đích hoặc commit không có tiền tố fixup/squash | Kiểm tra commit message và todo list |
| Test trong `exec` thất bại | Commit trung gian chưa có đủ cấu trúc/test/dependency | Chọn test phù hợp từng giai đoạn hoặc sửa commit trung gian |
| Rebase xong nhưng diff cuối khác nhiều | Đã drop hoặc gộp nhầm commit | So sánh với branch backup và phục hồi commit cần thiết |
| Push bị từ chối sau rebase | Remote đã thay đổi hoặc branch được bảo vệ | Fetch, xem commit mới và phối hợp với nhóm; không chuyển ngay sang `--force` |
| Đồng đội không thể push branch cũ | Lịch sử local của họ dựa trên commit trước rewrite | Thông báo, hướng dẫn fetch và rebase/cherry-pick phần việc riêng |

## 22. Bài thực hành hoàn chỉnh

Thực hiện trong repository thử nghiệm hoặc nhánh cá nhân chưa được chia sẻ:

### Giai đoạn A — Tạo lịch sử có commit phụ

1. Tạo nhánh `feature/rebase-lab` từ nhánh nền.
2. Thêm model và commit `Add payment summary model`.
3. Sửa typo trong model và commit `Fix typo in payment model`.
4. Thêm service và commit `Add payment calculation service`.
5. Thêm test và commit `Add tests for payment calculation`.
6. Sửa log message và commit `Improve payment log message`.
7. Xem lịch sử bằng `git log --oneline --graph`.

### Giai đoạn B — Bảo vệ và làm gọn

1. Kiểm tra `git status -sb` và bảo đảm working tree sạch.
2. Fetch nhánh nền.
3. Tạo branch backup.
4. Chạy `git rebase -i <upstream>`.
5. Dùng `fixup` để gộp typo vào model.
6. Giữ service và test riêng hoặc gộp theo chính sách review.
7. Dùng `reword` nếu message chưa mô tả đúng thay đổi.
8. Hoàn tất rebase và xem lại log.

### Giai đoạn C — Thử autosquash và conflict

1. Tạo một commit sửa bổ sung bằng `git commit --fixup=<commit-id>`.
2. Chạy `git rebase -i --autosquash <upstream>`.
3. Nếu có conflict, xem `git status` và diff.
4. Giải quyết file, stage và chạy `git rebase --continue`.
5. Trong repository thử nghiệm, thử `git rebase --abort` để quan sát cách quay về trạng thái trước phiên rebase.

### Giai đoạn D — Xác minh và bàn giao

1. So sánh tip mới với branch backup.
2. Xem `git log --oneline <upstream>..HEAD`.
3. Chạy test và `git diff --check`.
4. Kiểm tra working tree sạch.
5. Push lên remote thử nghiệm hoặc tạo pull request theo quy trình nhóm.
6. Giữ branch backup cho tới khi xác nhận bàn giao thành công.

Không dùng `--force` trên nhánh dùng chung trong bài thực hành. Nếu muốn mô phỏng nhánh đã push, chỉ dùng remote thử nghiệm do bạn kiểm soát.

## 23. Checklist trước khi bàn giao

- [ ] Đang ở đúng branch tính năng.
- [ ] Working tree và index sạch.
- [ ] Đã fetch upstream mới nhất.
- [ ] Đã xác định đúng phạm vi `upstream..HEAD`.
- [ ] Đã tạo branch backup hoặc có điểm phục hồi rõ ràng.
- [ ] Đã kiểm tra commit nào cần giữ, gộp, sửa message hoặc loại bỏ.
- [ ] Todo list có thứ tự hợp lý.
- [ ] Đã xử lý hết conflict và không còn trạng thái rebase dang dở.
- [ ] Diff cuối cùng so với upstream đúng mục tiêu.
- [ ] Test, lint và kiểm tra chất lượng đã pass.
- [ ] Đã thống nhất với nhóm nếu cần rewrite branch đã push.
- [ ] Đã push đúng cách và cập nhật pull request.

## 24. Tự kiểm tra kiến thức

1. Vì sao nên chạy `git fetch` trước khi interactive rebase?
2. `git log origin/main..HEAD` giúp xác định phạm vi nào?
3. Vì sao cần tạo branch backup trước khi viết lại lịch sử?
4. `pick`, `reword`, `edit`, `squash`, `fixup` và `drop` khác nhau thế nào?
5. Vì sao commit được gộp bằng `squash` mở editor còn `fixup` thường bỏ message phụ?
6. `git commit --fixup` phối hợp với `--autosquash` ra sao?
7. Khi nào nên dùng `edit` thay vì `reword`?
8. `git rebase --continue`, `--skip` và `--abort` khác nhau thế nào?
9. Vì sao không nên tự ý rebase nhánh đã được người khác checkout?
10. `--force-with-lease` bảo vệ điều gì và không thay thế bước phối hợp nào?
11. Làm thế nào xác minh nội dung cuối không thay đổi sau khi gộp commit?
12. Vì sao số lượng commit ít nhất không phải lúc nào cũng là lịch sử tốt nhất?

## Kết luận

Interactive rebase giúp biến chuỗi commit phát triển thành lịch sử rõ ràng trước khi bàn giao. Hãy xác định đúng upstream, bảo vệ branch hiện tại, dùng `pick`, `reword`, `edit`, `squash`, `fixup` và `drop` theo mục tiêu, rồi xử lý conflict bằng `--continue`, `--skip` hoặc `--abort` một cách có chủ đích. Sau rebase, so sánh diff với branch backup, chạy test và xác nhận working tree sạch. Nếu nhánh đã được chia sẻ, phối hợp với nhóm trước khi cập nhật remote; dùng `--force-with-lease` theo quy trình đã thống nhất và hướng dẫn mọi clone liên quan đồng bộ lịch sử mới.

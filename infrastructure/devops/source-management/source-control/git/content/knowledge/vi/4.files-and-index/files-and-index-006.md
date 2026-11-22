# Khôi phục thay đổi chưa commit bằng `git restore` và phạm vi mất dữ liệu

Khi sửa nhầm một file, stage nhầm nội dung hoặc xóa một đường dẫn, bạn có thể dùng `git restore` để đưa file hoặc index về một phiên bản đã biết. Lệnh này rất hữu ích vì cho phép chọn rõ nơi cần khôi phục: working tree, staging area hoặc cả hai. Tuy nhiên, restore có thể ghi đè nội dung chưa commit. Trước khi chạy, hãy xác định phiên bản đang nằm ở đâu, nguồn muốn lấy là gì và phạm vi pathspec sẽ bị tác động.

## 1. Ba trạng thái cần phân biệt trước khi khôi phục

Git làm việc với ba trạng thái chính của một file:

| Trạng thái | Vai trò | Lệnh thường dùng để xem |
|---|---|---|
| `HEAD` | Snapshot của commit hiện tại | `git show HEAD:path/to/file` |
| Index (staging area) | Phiên bản sẽ được đưa vào commit tiếp theo | `git diff --cached -- path/to/file` |
| Working tree | Nội dung file hiện có trên ổ đĩa | `git diff -- path/to/file` |

Một file có thể có ba nội dung khác nhau cùng lúc. Ví dụ, bạn stage một thay đổi, sau đó tiếp tục sửa file mà chưa stage lại. Khi đó:

- `HEAD` vẫn là phiên bản trong commit gần nhất.
- Index giữ phiên bản đã stage ở lần đầu.
- Working tree giữ phiên bản mới nhất trên ổ đĩa.

`git commit` lấy nội dung từ index. Vì vậy, khi định khôi phục, không nên chỉ nhìn file đang mở trong editor; hãy kiểm tra cả thay đổi staged và unstaged.

## 2. Kiểm tra trước khi chạy `git restore`

Bắt đầu bằng trạng thái tổng quát:

```bash
git status --short
```

Xem thay đổi chưa stage:

```bash
git diff -- path/to/file
```

Xem thay đổi đã stage:

```bash
git diff --cached -- path/to/file
```

Nếu cần xem phiên bản đang được commit:

```bash
git show HEAD:path/to/file
```

Với file quan trọng, hãy lưu bản sao ra ngoài repository, commit phần công việc muốn giữ hoặc stash trước khi restore. Một cách stash cả thay đổi tracked lẫn file untracked là:

```bash
git stash push -u -m "Backup before restoring files"
```

`-u` bao gồm file untracked nhưng không bao gồm file ignored. Nếu cần lưu cả file ignored, `git stash push -a` có phạm vi rộng hơn; hãy kiểm tra kỹ vì có thể gom cả cache và dữ liệu local lớn.

## 3. Nguồn mặc định của `git restore`

`git restore` lấy nội dung từ một nguồn (*source*) và ghi vào một đích (*destination*). Nếu không chỉ định `--source`, nguồn mặc định phụ thuộc vào đích:

| Lệnh | Nguồn mặc định | Đích được cập nhật |
|---|---|---|
| `git restore --worktree -- file` | Index | Working tree |
| `git restore --staged -- file` | `HEAD` | Index |
| `git restore --source=<commit> --worktree -- file` | Commit chỉ định | Working tree |
| `git restore --source=<commit> --staged -- file` | Commit chỉ định | Index |
| `git restore --source=<commit> --staged --worktree -- file` | Commit chỉ định | Index và working tree |

Nếu không ghi `--staged`, Git mặc định cập nhật working tree. Khi có `--staged`, nguồn mặc định là `HEAD`. Việc nêu rõ `--source` và các đích cần cập nhật giúp lệnh dễ đọc, đặc biệt khi thao tác có nguy cơ làm mất thay đổi.

`--` phân cách tùy chọn của Git với pathspec. Nên dùng nó khi chỉ định file để tên file không bị hiểu nhầm là tùy chọn:

```bash
git restore --worktree -- src/main/App.java
```

## 4. Bỏ thay đổi chưa stage trong working tree

Giả sử bạn đã sửa `src/main/App.java` nhưng chưa chạy `git add`. Muốn bỏ phần sửa và lấy lại nội dung từ index:

```bash
git restore --worktree -- src/main/App.java
```

Lệnh này chỉ cập nhật working tree. Index vẫn giữ nguyên. Nếu file chưa có thay đổi staged, nội dung trong index thường giống `HEAD`; khi đó file trở về phiên bản commit hiện tại.

Kiểm tra sau khi restore:

```bash
git diff -- src/main/App.java
git status --short
```

Nếu không còn thay đổi unstaged cho file đó, `git diff` không hiển thị nội dung khác biệt. Các file khác trong repository không bị tác động vì pathspec chỉ chỉ định một file.

## 5. Bỏ stage nhưng giữ nội dung đang sửa

Nếu đã chạy `git add` nhưng muốn đưa thay đổi ra khỏi staging area để tiếp tục chỉnh sửa, dùng:

```bash
git restore --staged -- src/main/App.java
```

Lệnh lấy phiên bản từ `HEAD` và cập nhật index. Working tree không bị ghi đè, nên nội dung file đang sửa vẫn còn trên ổ đĩa và trở thành thay đổi chưa stage.

Kiểm tra:

```bash
git diff --cached -- src/main/App.java
git diff -- src/main/App.java
```

Sau khi unstage, diff staged thường rỗng; diff working tree hiển thị phần sửa được giữ lại. Đây là cách phù hợp khi stage nhầm file hoặc muốn chia một commit thành nhiều phần.

## 6. Bỏ cả thay đổi staged và unstaged của một file

Nếu muốn file trở về đúng phiên bản trong commit hiện tại, bất kể index và working tree đang khác nhau thế nào, chỉ rõ nguồn và cả hai đích:

```bash
git restore --source=HEAD --staged --worktree -- src/main/App.java
```

Lệnh này cập nhật index và working tree từ `HEAD`. Những thay đổi staged và unstaged của đường dẫn đó sẽ bị thay thế. Các file khác không nằm trong pathspec vẫn giữ nguyên.

Trước khi chạy, nên xem cả hai diff:

```bash
git diff -- src/main/App.java
git diff --cached -- src/main/App.java
```

Sau khi chạy, kiểm tra lại:

```bash
git status --short -- src/main/App.java
```

Không dùng lệnh này nếu bạn chỉ muốn unstage mà vẫn giữ phần sửa trong working tree; trường hợp đó dùng `git restore --staged -- file`.

## 7. Khôi phục file đã bị xóa khỏi working tree

Nếu file tracked bị xóa khỏi ổ đĩa nhưng thao tác xóa chưa được stage, index vẫn có nội dung file. Khôi phục từ index:

```bash
git restore --worktree -- src/main/App.java
```

Git tạo lại file trong working tree theo phiên bản index. Đây là cách đơn giản để phục hồi một file tracked vừa xóa nhầm.

Kiểm tra trạng thái trước khi chạy để biết thao tác xóa đã được stage hay chưa:

```bash
git status --short
```

Ký hiệu ` D` thường biểu thị file bị xóa trong working tree nhưng chưa stage; `D ` biểu thị thao tác xóa đã được stage. Khoảng trắng và vị trí ký tự rất quan trọng trong output dạng short status.

## 8. Khôi phục file đã xóa và thao tác xóa đã được stage

Nếu file bị xóa rồi bạn chạy `git add -u` hoặc stage thao tác xóa, index cũng không còn entry của file. Khi đó `git restore --worktree -- file` lấy từ index sẽ không khôi phục được nội dung như mong muốn.

Đưa cả index và working tree về phiên bản trong `HEAD`:

```bash
git restore --source=HEAD --staged --worktree -- src/main/App.java
```

Nếu chỉ muốn bỏ stage thao tác xóa trước, dùng:

```bash
git restore --staged -- src/main/App.java
```

Lệnh này đưa entry trở lại index từ `HEAD`, còn file trên ổ đĩa vẫn đang bị xóa. Sau đó khôi phục working tree từ index:

```bash
git restore --worktree -- src/main/App.java
```

Hai bước giúp nhìn rõ tác động: bước đầu khôi phục index, bước sau tạo lại file. Nếu mục tiêu cuối cùng là bỏ toàn bộ thay đổi của file, lệnh kết hợp ở đầu phần này ngắn hơn.

## 9. Khôi phục một file đã stage thêm mới

Giả sử `notes.txt` chưa từng tồn tại trong `HEAD`, bạn tạo file rồi chạy `git add notes.txt`. Nếu muốn bỏ stage nhưng giữ nội dung file:

```bash
git restore --staged -- notes.txt
```

Vì `HEAD` không có đường dẫn này, entry được loại khỏi index. File vẫn còn trong working tree và thường xuất hiện lại dưới dạng untracked.

Nếu muốn bỏ cả file mới đã stage khỏi index và working tree, có thể dùng:

```bash
git restore --source=HEAD --staged --worktree -- notes.txt
```

Vì đường dẫn không tồn tại trong nguồn `HEAD`, Git loại đường dẫn khỏi cả hai đích. Hãy xác nhận file không chứa dữ liệu cần giữ trước khi chạy.

## 10. Khôi phục từ commit hoặc tag cũ

Bạn có thể lấy nội dung file từ một commit cũ mà không di chuyển branch hiện tại. Ví dụ, đưa phiên bản từ hai commit trước vào working tree:

```bash
git restore --source=HEAD~2 --worktree -- src/main/App.java
```

Index không bị thay đổi; working tree có nội dung từ `HEAD~2`. Git xem đó là thay đổi so với index hiện tại. Bạn có thể review rồi quyết định stage hay tiếp tục chỉnh sửa.

Muốn lấy phiên bản cũ vào cả index và working tree:

```bash
git restore --source=HEAD~2 --staged --worktree -- src/main/App.java
```

Sau đó xem nội dung sẽ commit:

```bash
git diff --cached -- src/main/App.java
```

Nếu muốn ghi nhận việc khôi phục như một commit mới, chạy test, review diff rồi commit. Lịch sử branch vẫn tiến về phía trước; Git không di chuyển `HEAD` về commit cũ.

Có thể dùng tag hoặc hash commit làm nguồn:

```bash
git restore --source=v1.4.0 --worktree -- config/default.yml
```

Hãy xác minh commit/tag và đường dẫn tồn tại trong snapshot nguồn trước khi restore. Nếu nguồn không có đường dẫn được chỉ định, thao tác có thể loại đường dẫn đó khỏi đích khôi phục tương ứng.

## 11. Khôi phục cả thư mục hoặc nhiều đường dẫn

`git restore` nhận pathspec là file, thư mục hoặc nhiều đường dẫn. Ví dụ khôi phục toàn bộ file tracked dưới `src/generated/` từ `HEAD`:

```bash
git restore --source=HEAD --worktree -- src/generated/
```

Muốn cập nhật cả index và working tree:

```bash
git restore --source=HEAD --staged --worktree -- src/generated/
```

Có thể truyền nhiều đường dẫn:

```bash
git restore --worktree -- README.md src/main/App.java config/default.yml
```

Pathspec mặc định được diễn giải tương đối với thư mục hiện tại trong repository. Nếu muốn chỉ định rõ từ root repository, có thể dùng pathspec magic `:(top)`:

```bash
git restore --worktree -- ':(top)src/main/App.java'
```

Đặt pathspec trong dấu nháy khi có ký tự wildcard để shell không tự mở rộng trước khi Git nhận được. Kiểm tra kỹ phạm vi trước khi dùng pathspec rộng như `.` hoặc `:(top)**`.

## 12. Chỉ khôi phục một phần bằng chế độ tương tác

Không phải lúc nào cũng muốn bỏ toàn bộ thay đổi của một file. Tùy chọn `-p` (hoặc `--patch`) cho phép chọn từng hunk cần khôi phục.

Bỏ một số hunk unstaged trong working tree, lấy nội dung tương ứng từ index:

```bash
git restore -p --worktree -- src/main/App.java
```

Unstage một số hunk, lấy nội dung tương ứng từ `HEAD` vào index:

```bash
git restore -p --staged -- src/main/App.java
```

Git hiển thị từng phần thay đổi và hỏi bạn có muốn khôi phục phần đó không. Đọc kỹ từng hunk trước khi chọn. Với file có thay đổi xen kẽ phức tạp, có thể cần chỉnh sửa thủ công sau khi restore.

`git restore -p` là lựa chọn hữu ích khi một file chứa cả phần muốn giữ và phần muốn bỏ. Nếu cần chia thay đổi thành các commit nhỏ, kết hợp `git add -p` để stage từng hunk và `git restore -p --staged` để đưa phần stage nhầm trở lại.

## 13. Khôi phục một phía khi file đang conflict

Trong lúc merge, rebase hoặc cherry-pick, index có thể chứa nhiều stage cho cùng một đường dẫn:

| Stage | Ý nghĩa |
|---|---|
| 1 | Phiên bản base chung, nếu có |
| 2 | Phiên bản phía `ours` |
| 3 | Phiên bản phía `theirs` |

Nếu muốn lấy nguyên phiên bản `ours` vào working tree:

```bash
git restore --ours --worktree -- path/to/conflicted-file
```

Hoặc lấy phiên bản `theirs`:

```bash
git restore --theirs --worktree -- path/to/conflicted-file
```

Hai tùy chọn này chỉ dùng cho đường dẫn đang ở trạng thái unmerged và không kết hợp với `--source`. Sau khi chọn một phía, file trong working tree không còn marker conflict theo nội dung phía đó, nhưng index vẫn cần được đánh dấu đã giải quyết:

```bash
git add path/to/conflicted-file
git status
```

Lưu ý: trong rebase, cách Git đặt tên `ours` và `theirs` có thể khác trực giác khi bạn nghĩ theo nhánh tính năng và nhánh đích. Hãy xem `git status`, các stage và nội dung từng phía trước khi chọn. Nếu cần xem base, có thể đọc stage 1 bằng:

```bash
git show :1:path/to/conflicted-file
```

Nếu cần hủy toàn bộ thao tác merge/rebase thay vì chọn một phía, dùng lệnh abort phù hợp (`git merge --abort` hoặc `git rebase --abort`) sau khi xác định trạng thái.

## 14. Phạm vi mất dữ liệu của từng lệnh

Điều quan trọng nhất khi dùng restore là hiểu đích bị ghi đè:

| Lệnh | Có thể làm mất gì? | Điều gì được giữ? |
|---|---|---|
| `git restore --worktree -- file` | Thay đổi unstaged của file trong working tree | Index và file khác |
| `git restore --staged -- file` | Phiên bản staged của file trong index bị thay bằng `HEAD` | Working tree và file khác |
| `git restore --source=HEAD --staged --worktree -- file` | Cả thay đổi staged và unstaged của file | Commit history và file ngoài pathspec |
| `git restore -p ...` | Chỉ các hunk bạn chọn | Các hunk không chọn và đường dẫn khác |
| `git restore --source=<commit> --worktree -- directory/` | Thay nội dung working tree của các đường dẫn trong phạm vi thư mục theo snapshot nguồn | Index và các đường dẫn ngoài phạm vi |

Các lệnh restore không tạo commit mới, không di chuyển branch và không xóa commit cũ. Chúng thay đổi index và/hoặc working tree theo đích được chỉ định. Tuy nhiên, dữ liệu bị ghi đè có thể không còn bản sao để khôi phục.

Đừng dùng `git restore .` khi chưa biết tất cả file tracked trong thư mục hiện tại đang có thay đổi gì. Dấu `.` có thể bao phủ nhiều file hơn bạn định khôi phục. Hãy xem `git status` và chỉ định pathspec hẹp nhất có thể.

## 15. `git restore` không khôi phục mọi loại dữ liệu

Git chỉ có thể lấy nội dung từ object hoặc index mà nó còn biết. `git restore` không thể tự khôi phục:

- File untracked bị xóa nếu file đó chưa từng được lưu trong Git.
- Nội dung working tree chưa stage đã bị ghi đè và không còn bản sao khác.
- File ignored chưa từng được commit hoặc stash.
- Dữ liệu trong database, volume, dịch vụ cloud hoặc hệ thống ngoài repository.
- Nội dung chưa từng được commit nếu nó đã bị mất khỏi working tree và index.

Reflog ghi lại chuyển động của các ref như `HEAD` và branch; nó không ghi nhật ký mọi lần bạn sửa file. Vì vậy, reflog thường không thể cứu nội dung chưa commit đã bị ghi đè.

Nếu mất file untracked hoặc nội dung local chưa được Git lưu, hãy kiểm tra Recycle Bin/Trash, backup hệ thống, IDE Local History, snapshot filesystem hoặc công cụ khôi phục dữ liệu phù hợp. Kết quả phụ thuộc vào việc byte cũ còn tồn tại trên thiết bị hay đã bị ghi đè.

## 16. Phân biệt `restore`, `reset`, `revert` và `clean`

Các lệnh này có mục tiêu và phạm vi khác nhau:

| Lệnh | Tác động chính | Khi phù hợp |
|---|---|---|
| `git restore` | Khôi phục nội dung path trong index và/hoặc working tree | Bỏ hoặc lấy lại thay đổi của file cụ thể |
| `git reset` | Di chuyển `HEAD`/branch và tùy mode cập nhật index, working tree | Điều chỉnh vị trí branch hoặc staging state |
| `git revert` | Tạo commit mới đảo ngược thay đổi của commit cũ | Hoàn tác commit đã chia sẻ mà vẫn giữ lịch sử |
| `git clean` | Xóa file untracked khỏi working tree | Dọn file chưa được Git theo dõi sau khi đã kiểm tra |

`git restore` không thay thế `git revert` khi cần hoàn tác commit đã chia sẻ. Nếu commit đã được push và nhóm cần giữ lịch sử, `git revert` thường phù hợp hơn. `git clean` là lệnh xóa untracked files; nó không phải công cụ khôi phục. Luôn dùng `git clean -n` để xem trước nếu cần dọn file và chỉ chạy lệnh xóa thật sau khi xác nhận.

## 17. Ví dụ thực hành: file có cả staged và unstaged changes

Giả sử bạn sửa `src/main/InvoiceService.java`, stage phần đầu, rồi tiếp tục sửa thêm:

```bash
git add src/main/InvoiceService.java
```

Sau đó tiếp tục chỉnh sửa file mà không stage lại. Kiểm tra:

```bash
git status --short
git diff -- src/main/InvoiceService.java
git diff --cached -- src/main/InvoiceService.java
```

Nếu phần đã stage đúng nhưng phần sửa thêm chưa muốn giữ, chỉ khôi phục working tree từ index:

```bash
git restore --worktree -- src/main/InvoiceService.java
```

Nếu bạn nhận ra đã stage nhầm toàn bộ nội dung và muốn giữ file hiện tại để chia lại commit:

```bash
git restore --staged -- src/main/InvoiceService.java
```

Nếu muốn bỏ toàn bộ thay đổi của file và quay về `HEAD`:

```bash
git restore --source=HEAD --staged --worktree -- src/main/InvoiceService.java
```

Sau mỗi lựa chọn, chạy `git status` và hai lệnh `git diff` để xác nhận index và working tree đúng như mục tiêu.

## 18. Quy trình an toàn trước khi restore

1. **Xác định đường dẫn:** chọn file hoặc thư mục chính xác, kiểm tra tracked/untracked.
2. **Đọc trạng thái:** chạy `git status --short`, `git diff` và `git diff --cached`.
3. **Chọn nguồn:** index, `HEAD`, tag hoặc commit cụ thể.
4. **Chọn đích:** working tree, index hoặc cả hai.
5. **Bảo toàn nội dung cần giữ:** commit, stash hoặc sao lưu ra ngoài repository.
6. **Giới hạn pathspec:** tránh dùng `.` hoặc wildcard rộng nếu chỉ cần sửa một file.
7. **Thực hiện restore:** nêu rõ `--worktree`, `--staged` và `--source` khi cần.
8. **Review sau thao tác:** chạy status và diff để xác nhận dữ liệu còn lại.
9. **Chạy test và commit:** nếu kết quả khôi phục là thay đổi cần chia sẻ, stage và tạo commit mới.

Ví dụ khôi phục phiên bản cũ rồi ghi nhận bằng commit mới:

```bash
git status --short
git log --oneline -- src/main/InvoiceService.java
git show <commit>:src/main/InvoiceService.java
git restore --source=<commit> --worktree -- src/main/InvoiceService.java
git diff -- src/main/InvoiceService.java
git add src/main/InvoiceService.java
git diff --cached -- src/main/InvoiceService.java
git commit -m "Restore invoice service implementation"
```

Thay `<commit>` bằng commit đã xác minh. Nếu muốn stage ngay phiên bản cũ, thêm `--staged` vào lệnh restore; vẫn cần review diff trước khi commit.

## 19. Ghi nhớ

`git restore` khôi phục nội dung theo nguồn và đích được chọn. Mặc định, `--worktree` lấy từ index; `--staged` lấy từ `HEAD`. Dùng `--source` để lấy phiên bản từ commit khác, và dùng cả `--staged --worktree` khi muốn hai nơi cùng trở về một snapshot. Lệnh chỉ tác động tới pathspec hoặc hunk đã chọn, không tạo commit và không di chuyển branch. Nó không thể phục hồi file untracked hay chỉnh sửa chưa commit đã bị ghi đè nếu Git hoặc một hệ thống backup không còn bản sao. Hãy kiểm tra trạng thái, bảo toàn dữ liệu cần giữ và review diff trước khi thực hiện thao tác có thể làm mất nội dung.

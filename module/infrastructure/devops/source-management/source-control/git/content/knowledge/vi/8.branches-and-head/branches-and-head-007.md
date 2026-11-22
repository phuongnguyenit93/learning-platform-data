# Điều kiện chuyển nhánh khi có thay đổi chưa commit

Khi đang sửa code, bạn có thể cần chuyển sang branch khác để xử lý bug, review pull request hoặc bắt đầu một công việc mới. Nếu working tree còn thay đổi chưa commit, Git phải xác định những thay đổi đó có thể được giữ nguyên khi checkout nội dung của branch đích hay không.

Git cho phép chuyển branch khi thay đổi local không bị ghi đè bởi snapshot của branch đích. Nếu việc chuyển branch có nguy cơ làm mất nội dung đang sửa, Git thường từ chối và yêu cầu bạn xử lý trước. Bạn có thể commit tạm, stash, tạo branch mới hoặc chủ động dùng chế độ merge khi hiểu rõ kết quả. Bài viết giải thích các điều kiện này và cách chọn quy trình an toàn.

## 1. Ba vùng cần kiểm tra trước khi chuyển branch

Git làm việc với ba vùng chính:

- **HEAD**: commit hiện tại mà branch hoặc detached HEAD đang trỏ tới.
- **Index (staging area)**: nội dung đã stage để chuẩn bị cho commit tiếp theo.
- **Working tree**: các file đang hiện diện trong thư mục làm việc.

Thay đổi chưa commit có thể nằm ở index, working tree hoặc cả hai. Vì vậy, chỉ nhìn một dòng tóm tắt là chưa đủ để quyết định có thể chuyển branch an toàn hay không.

Sơ đồ:

```text
HEAD (commit hiện tại) -- git diff --cached --> Index (đã stage)
Index ----------------- git diff -----------> Working tree
HEAD ----------------- git diff HEAD -------> Working tree
```

Bắt đầu bằng:

```bash
git status --short --branch
git diff
git diff --cached
```

- `git status` cho biết branch hiện tại, staged, unstaged, untracked và trạng thái conflict.
- `git diff` xem thay đổi chưa stage.
- `git diff --cached` xem thay đổi đã stage so với HEAD.

Nếu cần xem cả file untracked và ignored:

```bash
git status --short --untracked-files=all --ignored
```

Các file untracked không nằm trong index. Tuy nhiên, chúng vẫn có thể cản trở việc chuyển branch nếu branch đích có file tracked cùng đường dẫn.

## 2. Khi nào Git cho phép chuyển branch?

Giả sử branch hiện tại là `feature/a`, branch đích là `feature/b`. Git cần cập nhật index và working tree để phản ánh snapshot của branch đích.

Có thể chuyển branch khi những thay đổi local có thể được giữ lại mà không ghi đè nội dung cần checkout từ branch đích. Ví dụ:

- Bạn sửa `README.md` ở branch hiện tại.
- Branch đích không thay đổi `README.md` so với commit chung hoặc việc cập nhật file không làm mất phần sửa local.
- Git có thể giữ nguyên thay đổi local trong working tree khi chuyển sang branch đích.

Khi đó:

```bash
git switch feature/b
```

có thể thành công và thay đổi local vẫn còn sau khi chuyển branch. Bạn vẫn cần kiểm tra `git status` để xác nhận thay đổi đang nằm ở trạng thái nào.

Git thường từ chối chuyển branch nếu snapshot đích cần ghi đè một file đang có thay đổi local. Ví dụ:

```text
Branch feature/a: src/App.java = phiên bản A
Working tree:     src/App.java đã sửa local
Branch feature/b: src/App.java = phiên bản B khác
```

Nếu chuyển sang `feature/b` sẽ làm mất nội dung đang sửa, Git sẽ dừng và báo rằng local changes would be overwritten by checkout/switch.

Đây là cơ chế bảo vệ dữ liệu. Khi gặp thông báo này, hãy đọc danh sách file Git nêu ra và bảo toàn các thay đổi trước khi thử lại.

## 3. Staged và unstaged changes ảnh hưởng ra sao?

Git kiểm tra cả index và working tree. Hai loại thay đổi có thể cùng tồn tại:

```text
 M src/App.java
M  README.md
A  src/NewFeature.java
```

Ý nghĩa:

- ` M`: file tracked được sửa trong working tree nhưng chưa stage.
- `M `: thay đổi của file đã được stage trong index.
- `A `: file mới đã được stage.

Một thay đổi staged vẫn là thay đổi chưa commit. Việc đã chạy `git add` không có nghĩa nội dung đó đã được lưu vào lịch sử commit.

Nếu branch đích không yêu cầu ghi đè những đường dẫn có thay đổi, Git có thể giữ chúng khi chuyển branch. Nếu có nguy cơ ghi đè, Git từ chối. Đừng giả định staged changes luôn an toàn hơn unstaged changes; cả hai đều cần được bảo toàn.

Kiểm tra riêng hai vùng:

```bash
git diff
git diff --cached
git status --short
```

Nếu bạn đã stage một phần file rồi tiếp tục sửa phần khác, có thể thấy cùng một file xuất hiện ở cả hai cột trạng thái. Hãy hiểu nội dung trong index và working tree trước khi chuyển branch.

## 4. Untracked files có thể chặn việc chuyển branch

File untracked chưa được Git theo dõi, nhưng vẫn có thể bị ảnh hưởng bởi checkout.

Ví dụ, branch hiện tại có file untracked:

```text
src/Experimental.java
```

Nếu branch đích có một file tracked cùng đường dẫn `src/Experimental.java`, Git không thể ghi file của branch đích lên trên file local mà không có nguy cơ làm mất dữ liệu. Lệnh switch thường từ chối.

Kiểm tra file untracked chi tiết:

```bash
git status --short --untracked-files=all
git ls-files --others --exclude-standard
```

Có ba cách xử lý thường gặp:

1. Đưa file vào commit nếu nó thuộc công việc của branch hiện tại.
2. Stash cả file untracked bằng `git stash push -u`.
3. Di chuyển hoặc sao lưu file ra vị trí an toàn rồi chuyển branch.

Đừng xóa file untracked chỉ để làm lệnh switch chạy được nếu chưa xác nhận chúng có thể bỏ đi.

Ignored files cũng cần được chú ý. Một số file ignored có thể bị checkout ghi đè khi branch đích cần tạo file cùng đường dẫn. Nếu file local có giá trị, hãy sao lưu trước khi chuyển branch; `git status --ignored` giúp phát hiện chúng.

## 5. Thử chuyển branch và đọc thông báo của Git

Quy trình đơn giản:

```bash
git status --short --branch
git switch feature/b
```

Nếu thành công, kiểm tra ngay:

```bash
git status --short --branch
git branch --show-current
```

Nếu thất bại vì local changes, Git thường nêu các file có nguy cơ bị ghi đè. Không nên thêm `--force` hoặc `--discard-changes` theo phản xạ. Hãy xác định thay đổi nào cần giữ và chọn cách bảo toàn phù hợp.

Nếu Git báo đang có unmerged paths hoặc một thao tác merge/rebase/cherry-pick chưa hoàn tất, hãy xử lý thao tác đang dở trước. Chuyển branch khi index còn conflict có thể bị từ chối vì repository chưa ở trạng thái phù hợp.

## 6. Cách 1: Commit thay đổi trước khi chuyển branch

Nếu thay đổi đã đủ rõ ràng và thuộc về branch hiện tại, cách trực tiếp nhất là tạo commit:

```bash
git status
git add -- src/App.java
git diff --cached
git commit -m "Update application behavior"
git switch feature/b
```

Commit lưu snapshot của index vào lịch sử. Sau khi commit thành công, thay đổi không còn là thay đổi chưa commit; branch hiện tại giữ commit đó.

Nếu công việc còn dang dở nhưng bạn vẫn muốn giữ nó trong lịch sử local, có thể tạo một commit tạm với thông điệp dễ nhận biết:

```bash
git add -A
git commit -m "WIP: save progress before switching"
```

Sau đó chuyển branch. Khi quay lại, bạn có thể tiếp tục sửa hoặc chỉnh lịch sử riêng tư bằng các thao tác phù hợp, chẳng hạn amend hoặc rebase interactive nếu commit chưa được chia sẻ.

Chỉ dùng `git add -A` sau khi kiểm tra danh sách file. Lệnh này stage cả thêm, sửa và xóa trong phạm vi repository; file ignored không tự được thêm. Nếu có file local hoặc secret không nên commit, hãy stage rõ từng đường dẫn hoặc dùng `git add -p`.

## 7. Cách 2: Stash thay đổi để chuyển branch tạm thời

Nếu chưa muốn tạo commit, có thể cất thay đổi vào stash:

```bash
git stash push -m "WIP before switching branch"
git status --short --branch
git switch feature/b
```

Mặc định, stash lưu các thay đổi tracked trong index và working tree rồi đưa working tree về trạng thái sạch tương ứng với HEAD. File untracked không được đưa vào stash mặc định.

Nếu cần cất cả file untracked:

```bash
git stash push -u -m "WIP including untracked files"
```

Tùy chọn `-u` tương đương `--include-untracked`. File ignored vẫn không được đưa vào stash theo tùy chọn này.

Nếu thật sự cần cất cả file ignored:

```bash
git stash push -a -m "WIP including ignored files"
```

`-a` tương đương `--all`, bao gồm untracked và ignored files. Hãy kiểm tra kỹ trước khi dùng vì các file cấu hình local, cache hoặc dữ liệu cần thiết có thể bị dọn khỏi working tree sau khi stash.

Xem danh sách stash:

```bash
git stash list
git stash show --stat stash@{0}
```

Sau khi hoàn thành việc ở branch khác, quay lại branch ban đầu và áp dụng stash:

```bash
git switch feature/a
git stash apply stash@{0}
```

`apply` giữ stash trong danh sách, giúp bạn có thời gian xác minh nội dung đã phục hồi đầy đủ. Khi chắc chắn, xóa entry bằng:

```bash
git stash drop stash@{0}
```

`git stash pop` vừa áp dụng vừa xóa stash nếu áp dụng thành công. Khi thay đổi quan trọng, `apply` rồi kiểm tra trước khi `drop` là cách dễ kiểm soát hơn.

## 8. Stash riêng phần unstaged hoặc staged

Đôi khi bạn đã stage phần thay đổi muốn commit, nhưng còn phần khác chưa stage. Tùy mục tiêu, có thể dùng `--keep-index` để giữ nội dung đã stage trong index và chỉ cất phần còn lại:

```bash
git add -- src/App.java
git stash push --keep-index -m "Stash unstaged work"
```

Tùy chọn này hữu ích khi muốn giữ phần staged để chạy test hoặc tạo commit trong khi cất phần unstaged. Hãy xem `git status` sau lệnh để xác nhận chính xác phần nào còn lại.

Nếu muốn cất riêng một số đường dẫn, dùng pathspec:

```bash
git stash push -m "Save documentation edits" -- docs/
```

Stash có thể được áp dụng lên branch khác và phát sinh conflict nếu nội dung nền khác nhau. Stash không phải commit trên branch và không tự được chia sẻ với remote.

## 9. Cách 3: Tạo branch mới từ trạng thái hiện tại

Nếu bạn nhận ra thay đổi local thực ra thuộc về một công việc mới, có thể tạo branch mới ngay tại commit hiện tại:

```bash
git switch -c feature/new-task
```

Lệnh tạo branch mới từ HEAD hiện tại và chuyển sang branch đó. Vì branch mới bắt đầu tại cùng commit, Git thường giữ nguyên các thay đổi chưa commit trong index và working tree.

Ví dụ:

```text
Trước:
main (HEAD) ---- A
                  \
                   working tree có thay đổi local

Sau git switch -c feature/new-task:
main ------------ A
feature/new-task  A (HEAD)
                   \
                    cùng thay đổi local tiếp tục nằm trong working tree/index
```

Sau khi tạo branch, kiểm tra:

```bash
git status --short --branch
git branch --show-current
```

Bây giờ bạn có thể commit các thay đổi lên branch mới. Đây là cách phù hợp khi bắt đầu sửa nhầm trên `main` nhưng chưa tạo commit.

Nếu branch mới cần bắt đầu từ một commit khác, hãy bảo toàn thay đổi trước bằng stash hoặc commit rồi mới chuyển. Không nên kỳ vọng `git switch -c <new-branch> <other-start-point>` sẽ mang mọi thay đổi local sang một nền khác mà không có xung đột.

## 10. Cách 4: Dùng git switch --merge khi muốn Git hợp nhất thay đổi local

`git switch --merge <branch>` yêu cầu Git thử hợp nhất thay đổi local với nội dung của branch đích bằng cơ chế three-way merge.

Ví dụ:

```bash
git switch --merge feature/b
```

Cách này có thể hữu ích khi bạn chủ động muốn mang thay đổi local sang branch đích và Git có thể hợp nhất chúng. Tuy nhiên, thao tác có thể tạo conflict nếu cùng vùng nội dung bị thay đổi theo các hướng khác nhau.

Sau lệnh, kiểm tra:

```bash
git status
git diff
git diff --cached
git diff --name-only --diff-filter=U
```

Nếu có conflict:

1. Mở từng file và kết hợp nội dung phù hợp với branch đích.
2. Stage file đã giải quyết bằng `git add`.
3. Kiểm tra lại index và working tree.
4. Tạo commit nếu muốn lưu phần thay đổi đã hợp nhất.

Ví dụ:

```bash
git add -- src/App.java
git status
git diff --cached
```

`switch --merge` không thay thế việc review kết quả. Nếu không chắc Git sẽ kết hợp thế nào, stash trước là lựa chọn dễ kiểm soát hơn.

## 11. Không dùng --discard-changes để né thông báo

Git có tùy chọn:

```bash
git switch --discard-changes feature/b
```

Tùy chọn này yêu cầu bỏ các thay đổi trong index và working tree để chuyển sang branch đích. Nội dung tracked chưa commit có thể bị ghi đè. File untracked hoặc ignored cản trở việc checkout cũng có thể gặp rủi ro tùy đường dẫn và thao tác checkout.

Chỉ dùng khi bạn đã xác nhận mọi thay đổi cần thiết đã được commit, stash hoặc sao lưu ở nơi khác.

Trước khi cân nhắc:

```bash
git status --short --untracked-files=all --ignored
git diff
git diff --cached
```

Nếu còn nghi ngờ, không dùng `--discard-changes`. Stash hoặc tạo bản sao an toàn trước, rồi chuyển branch bình thường.

Tương tự, tránh dùng `git reset --hard` chỉ để làm working tree sạch. Lệnh đó di chuyển HEAD/index và ghi lại file tracked theo commit đích, có thể làm mất nội dung local.

## 12. Nếu đang có merge, rebase hoặc cherry-pick dở

Khi Git đang ở giữa một thao tác tích hợp, index có thể chứa các stage conflict hoặc metadata sequencer. Chuyển branch lúc này thường bị từ chối.

Kiểm tra:

```bash
git status
git ls-files -u
```

Nếu đang merge và muốn hoàn tất, giải quyết conflict rồi:

```bash
git add -- <resolved-path>
git merge --continue
```

Nếu muốn hủy merge đang dở:

```bash
git merge --abort
```

Với rebase:

```bash
git rebase --continue
# hoặc
git rebase --abort
```

Với cherry-pick:

```bash
git cherry-pick --continue
# hoặc
git cherry-pick --abort
```

Chỉ abort khi hiểu những thay đổi nào sẽ được khôi phục hoặc loại bỏ. Nếu có công việc chưa được bảo toàn trước khi bắt đầu thao tác, hãy xem `git status` và các diff hiện tại trước khi quyết định.

Sau khi thao tác tích hợp kết thúc, xác nhận không còn unmerged paths rồi mới chuyển branch.

## 13. Chuyển sang branch remote khi local còn thay đổi

Nếu muốn chuyển sang branch remote chưa có branch local, có thể tạo local tracking branch:

```bash
git fetch origin
git switch --track origin/feature/review
```

Lệnh tạo branch local `feature/review` theo dõi `origin/feature/review` và chuyển sang đó. Điều kiện bảo toàn thay đổi local vẫn giống khi chuyển giữa hai branch local: nếu checkout không ghi đè thay đổi thì Git có thể giữ chúng; nếu có nguy cơ ghi đè, Git từ chối.

Nếu branch local cùng tên đã tồn tại, kiểm tra upstream và trạng thái trước khi chuyển:

```bash
git branch -vv
git switch feature/review
```

Không dùng `git pull` như cách xử lý thay đổi local bị chặn khi switch. Pull tích hợp lịch sử remote vào branch hiện tại; nó không phải lệnh stash hoặc bảo toàn working tree để chuyển branch.

## 14. Khôi phục stash khi branch đích đã thay đổi

Sau khi stash, branch đích có thể đã thay đổi cùng file. Khi áp dụng stash, Git có thể conflict.

Dùng `apply` để giữ stash nếu áp dụng thất bại:

```bash
git stash apply stash@{0}
git status
```

Nếu conflict, giải quyết file, stage và kiểm tra nội dung. Khi đã phục hồi đầy đủ, mới xóa stash:

```bash
git stash drop stash@{0}
```

Nếu muốn tạo branch từ commit nền của stash và áp dụng thay đổi lên branch đó:

```bash
git stash branch rescue/work-in-progress stash@{0}
```

Lệnh này thường giúp phục hồi stash trên đúng nền mà nó được tạo, giảm nguy cơ conflict do branch hiện tại đã tiến xa. Nếu thành công, Git xóa stash entry được dùng.

Nếu stash có cả untracked files, xác minh chúng đã được phục hồi:

```bash
git status --short --untracked-files=all
git stash list
```

Không drop stash chỉ vì lệnh apply trả mã thoát thành công; hãy kiểm tra các file quan trọng và diff trước.

## 15. Ví dụ thực tế: đang sửa dở thì cần chuyển sang xử lý bug khẩn cấp

Bạn đang ở branch `feature/report`, đã sửa hai file:

- `src/ReportService.java` đã stage.
- `src/ReportFormatter.java` chưa stage.
- `notes/debug.txt` là file untracked.

Có yêu cầu xử lý bug khẩn cấp trên branch `hotfix/payment`.

**Bước 1: Kiểm tra đầy đủ trạng thái.**

```bash
git status --short --untracked-files=all
git diff
git diff --cached
```

**Bước 2: Cất cả tracked và untracked changes.**

```bash
git stash push -u -m "WIP report before payment hotfix"
```

**Bước 3: Xác nhận working tree sạch và chuyển branch.**

```bash
git status --short --branch
git switch hotfix/payment
```

**Bước 4: Sửa bug, test và commit trên branch hotfix.**

```bash
git add -- src/PaymentService.java
git commit -m "Fix payment validation"
```

**Bước 5: Quay lại công việc cũ.**

```bash
git switch feature/report
git stash list
git stash apply stash@{0}
```

**Bước 6: Xác minh thay đổi đã phục hồi.**

```bash
git status --short --untracked-files=all
git diff
git diff --cached
```

Nếu mọi nội dung đã trở lại đúng vị trí, xóa stash entry tương ứng:

```bash
git stash drop stash@{0}
```

Nếu trong lúc làm hotfix, `feature/report` đã được cập nhật từ remote hoặc có thay đổi khác, stash apply có thể conflict. Hãy giải quyết dựa trên nội dung mới, không xóa stash trước khi xác nhận.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `git switch` báo local changes would be overwritten | Branch đích cần ghi đè file đang sửa | Commit, stash hoặc bảo toàn file trước |
| Switch thành công nhưng thay đổi vẫn còn | Git có thể giữ thay đổi không xung đột | Kiểm tra `git status`, đừng cho rằng switch tự commit |
| File untracked chặn switch | Branch đích có file tracked cùng đường dẫn | Stash với `-u`, di chuyển hoặc sao lưu file |
| File ignored có nguy cơ bị ghi đè | Checkout cần tạo file cùng đường dẫn | Kiểm tra `--ignored` và sao lưu file quan trọng |
| Stash không chứa file untracked | Dùng stash mặc định | Dùng `git stash push -u` |
| Stash không chứa file ignored | `-u` không bao gồm ignored files | Chỉ dùng `-a` nếu thực sự muốn cất cả ignored files |
| Stash apply phát sinh conflict | Branch nền đã thay đổi | Giải quyết conflict, kiểm tra rồi mới drop stash |
| `git switch -c` báo branch đã tồn tại | Tên branch local đã được dùng | Kiểm tra branch bằng `git branch -vv`, chọn tên khác hoặc chuyển sang branch có sẵn |
| Không thể switch khi đang merge/rebase | Repository có thao tác tích hợp chưa hoàn tất | Tiếp tục hoặc abort thao tác sau khi bảo toàn công việc |
| Dùng `--discard-changes` làm mất sửa đổi | Đã yêu cầu Git bỏ local changes | Khôi phục từ stash/backup nếu có; kiểm tra trước khi dùng tùy chọn này |

## 17. Checklist trước khi chuyển branch

- [ ] Đã chạy `git status --short --branch`.
- [ ] Đã xem `git diff` và `git diff --cached`.
- [ ] Đã kiểm tra file untracked và ignored có thể bị ảnh hưởng.
- [ ] Đã xác nhận có merge, rebase, cherry-pick hoặc conflict đang diễn ra không.
- [ ] Đã quyết định commit, stash, tạo branch mới hay dùng merge.
- [ ] Nếu stash, đã chọn đúng phạm vi tracked, untracked (`-u`) và ignored (`-a`).
- [ ] Không dùng `--discard-changes` hoặc `reset --hard` khi chưa xác nhận có thể bỏ nội dung.
- [ ] Sau khi switch, đã kiểm tra branch và trạng thái local.
- [ ] Sau khi apply stash, đã xác minh nội dung trước khi drop stash.

## Kết luận

Git có thể chuyển branch khi thay đổi local được giữ nguyên mà không bị snapshot của branch đích ghi đè. Nếu có nguy cơ mất nội dung, Git thường từ chối; hãy đọc thông báo và kiểm tra cả index, working tree, untracked files trước khi tiếp tục. Commit phù hợp khi muốn lưu tiến độ vào lịch sử, stash phù hợp khi cần cất tạm, tạo branch mới phù hợp khi thay đổi thuộc một công việc khác, còn `git switch --merge` dành cho tình huống bạn chủ động muốn Git hợp nhất thay đổi local. Chỉ dùng `--discard-changes` khi đã xác nhận có thể bỏ toàn bộ thay đổi liên quan. Sau mỗi lần chuyển branch hoặc phục hồi stash, kiểm tra lại `git status` và diff để bảo đảm công việc vẫn nguyên vẹn.

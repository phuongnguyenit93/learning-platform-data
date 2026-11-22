# Khôi phục nhánh bằng commit tìm được trong reflog

Một nhánh Git chỉ là một tham chiếu trỏ tới commit. Khi vô tình xóa nhánh, reset nhầm hoặc di chuyển nhánh sang commit khác, các commit cũ có thể vẫn còn trong repository dù không còn nhánh nào trỏ tới chúng. **Reflog** ghi lại những lần các tham chiếu cục bộ thay đổi, nhờ đó bạn có thể tìm lại commit trước thao tác sai và tạo một nhánh mới từ commit đó.

Cách phục hồi an toàn gồm ba việc: tìm đúng commit trong reflog, xác minh nội dung commit, rồi tạo lại nhánh trỏ tới commit ấy. Reflog là công cụ cứu hộ hữu ích, nhưng chỉ tồn tại trong từng bản clone và không phải bản sao lưu lâu dài.

## 1. Vì sao có thể khôi phục nhánh từ reflog?

Trong Git, branch là một tên tham chiếu tới commit. Ví dụ, nhánh `feature/report` có thể trỏ tới commit `a1b2c3d`. Khi tạo commit mới trên nhánh, Git di chuyển tham chiếu đó tới commit mới.

Nếu lỡ xóa nhánh hoặc chạy lệnh làm nhánh trỏ sang vị trí khác, tên nhánh cũ có thể biến mất hoặc trỏ sai. Tuy nhiên, Git thường vẫn giữ các commit cũ trong kho đối tượng một thời gian. Reflog giúp tìm lại hash của commit mà nhánh từng trỏ tới.

Ví dụ trước khi thao tác nhầm:

~~~text
A---B---C---D  main
         \
          E---F  feature/report
~~~

Bạn vô tình reset nhánh `feature/report` về commit `C`. Nhánh hiện tại trở thành:

~~~text
A---B---C  main, feature/report
         \
          E---F  (không còn nhánh trỏ tới)
~~~

Các commit `E` và `F` có thể vẫn còn trong repository. Reflog có thể cho biết nhánh từng trỏ tới `F`; sau khi xác minh, bạn tạo lại một nhánh từ commit đó.

## 2. Reflog là gì?

Reflog (reference log) là nhật ký cục bộ ghi lại những lần giá trị của các tham chiếu Git thay đổi. Những thay đổi thường được ghi nhận gồm:

- Tạo commit và di chuyển HEAD.
- Chuyển từ nhánh này sang nhánh khác.
- Reset nhánh về commit khác.
- Hoàn tất rebase hoặc merge.
- Cập nhật một branch hoặc một tham chiếu khác.

Mỗi entry thường có hash commit, vị trí trong reflog, thời điểm và mô tả thao tác.

Xem reflog của HEAD:

~~~bash
git reflog
~~~

Lệnh này tương đương với cách xem nhật ký của HEAD và thường là điểm bắt đầu tốt khi cần phục hồi thao tác vừa thực hiện.

Xem reflog với thời gian dễ đọc:

~~~bash
git reflog --date=local
~~~

Xem reflog của một nhánh cụ thể:

~~~bash
git reflog show feature/report
~~~

Xem tất cả reflog mà Git còn giữ:

~~~bash
git reflog --all --date=iso
~~~

Reflog không phải lịch sử commit dùng chung của repository. Mỗi bản clone có reflog riêng; khi bạn push commit lên remote, reflog local không được gửi theo.

## 3. Đọc một entry trong reflog

Kết quả minh họa:

~~~text
f6a91d2 HEAD@{0}: reset: moving to HEAD~2
b72c4e8 HEAD@{1}: commit: Add report export
9d3a1f0 HEAD@{2}: commit: Add report filters
c4e8b21 HEAD@{3}: checkout: moving from main to feature/report
~~~

Có thể đọc các phần như sau:

| Thành phần | Ý nghĩa |
|---|---|
| `f6a91d2` | Commit mà HEAD trỏ tới tại entry đó |
| `HEAD@{0}` | Entry mới nhất của reflog HEAD |
| `HEAD@{1}` | Entry ngay trước entry mới nhất |
| `reset: moving to HEAD~2` | Mô tả thao tác đã làm thay đổi HEAD |

Chỉ số trong `HEAD@{n}` là vị trí trong nhật ký, không phải số commit cha. `HEAD@{2}` có nghĩa là entry thứ ba tính từ entry mới nhất, còn `HEAD~2` có nghĩa là đi ngược hai commit cha trong đồ thị lịch sử.

Ví dụ trên cho thấy HEAD hiện ở `f6a91d2` sau reset. Entry trước đó trỏ tới `b72c4e8`, và entry trước nữa trỏ tới `9d3a1f0`. Nếu mục tiêu là lấy lại trạng thái trước reset, một trong các hash cũ có thể là ứng viên. Phải kiểm tra nội dung và lịch sử trước khi chọn.

Các số thứ tự reflog thay đổi khi có thao tác mới. Khi tìm được commit đúng, hãy ghi lại hash đầy đủ để dùng trong các lệnh tiếp theo thay vì phụ thuộc mãi vào `HEAD@{1}`.

## 4. Tìm commit trước thao tác sai

Giả sử bạn vừa chạy:

~~~bash
git reset --hard HEAD~2
~~~

và nhận ra hai commit gần nhất trên nhánh tính năng đã biến mất khỏi đầu nhánh.

Bắt đầu bằng:

~~~bash
git status
git reflog --date=local
~~~

Tìm entry có mô tả liên quan đến thao tác sai, chẳng hạn `reset: moving to HEAD~2`. Entry ngay trước lần reset thường chứa tip cũ của HEAD.

Bạn có thể xem riêng reflog của nhánh nếu nhánh vẫn tồn tại:

~~~bash
git reflog show feature/report --date=local
~~~

Nếu nhánh đã bị xóa, reflog riêng của nhánh có thể cũng đã bị xóa. Khi đó, hãy kiểm tra reflog HEAD:

~~~bash
git reflog --date=local
~~~

HEAD thường đã ghi lại những lần checkout và commit khi bạn làm việc trên nhánh. Đây có thể là nơi còn lưu dấu vết của commit cuối cùng trước khi nhánh bị xóa.

### Không chọn commit chỉ dựa trên vị trí

Một entry gần thao tác sai chưa chắc là commit bạn cần. Hãy xác định:

1. Commit đó có thuộc nhánh cần phục hồi không?
2. Thời điểm tạo hoặc checkout có khớp với lúc bạn làm việc trên nhánh không?
3. Commit có chứa thay đổi cuối cùng mà bạn muốn lấy lại không?
4. Commit cha có hợp lý so với nhánh nền không?

Nếu không chắc, kiểm tra một vài ứng viên thay vì reset ngay.

## 5. Xác minh commit trước khi tạo nhánh

Sau khi tìm được hash, xem thông tin commit:

~~~bash
git show --no-patch --format=fuller b72c4e8
~~~

Xem danh sách file và thống kê thay đổi:

~~~bash
git show --stat b72c4e8
~~~

Xem các commit trước đó:

~~~bash
git log --oneline --graph --decorate -10 b72c4e8
~~~

Nếu cần xem chính xác nội dung thay đổi của commit:

~~~bash
git show b72c4e8
~~~

Đối chiếu thông điệp commit, tác giả, thời gian, file được sửa và nội dung diff với công việc bạn muốn phục hồi. Hash trong bài chỉ là ví dụ; hãy dùng hash lấy được từ repository của bạn.

Có thể lấy hash đầy đủ từ một mã rút gọn:

~~~bash
git rev-parse b72c4e8
~~~

Hãy ghi lại giá trị đó trước khi tạo nhánh.

## 6. Tạo lại nhánh từ commit trong reflog

Nếu tên nhánh cũ đã được giải phóng, cách đơn giản nhất là tạo nhánh mới từ commit đã xác minh:

~~~bash
git branch feature/report b72c4e8
~~~

Lệnh tạo nhánh `feature/report` trỏ tới commit `b72c4e8` nhưng không tự chuyển working tree sang nhánh đó.

Nếu muốn tạo và chuyển sang nhánh ngay:

~~~bash
git switch -c feature/report b72c4e8
~~~

Sau đó kiểm tra:

~~~bash
git status
git branch --show-current
git log --oneline --decorate -8
~~~

Nếu muốn giữ nhánh gốc và tạo nhánh phục hồi riêng để kiểm tra trước, dùng tên khác:

~~~bash
git switch -c recover/feature-report b72c4e8
~~~

Đây thường là cách thận trọng khi bạn chưa chắc commit đã chọn đúng. Nhánh cũ có thể được khôi phục hoặc công việc có thể được cherry-pick sau khi xác minh.

### Khi tên nhánh cũ vẫn tồn tại

Nếu `feature/report` vẫn tồn tại nhưng đang trỏ tới commit sai, đừng tạo nhánh trùng tên. Trước tiên, giữ lại vị trí hiện tại:

~~~bash
git branch rescue/feature-report-current feature/report
~~~

Nếu bạn muốn di chuyển nhánh cũ về commit đã tìm được, hãy kiểm tra các worktree đang sử dụng nhánh:

~~~bash
git worktree list
~~~

Chuyển khỏi nhánh đích ở mọi worktree trước khi cập nhật tham chiếu. Khi nhánh không còn được checkout, có thể cập nhật:

~~~bash
git branch -f feature/report b72c4e8
~~~

Nếu nhánh đang được checkout trong worktree hiện tại, chuyển sang một nhánh khác trước khi dùng `git branch -f`. Hoặc sau khi sao lưu và kiểm tra working tree, có thể dùng `git reset --hard b72c4e8` khi đang đứng trên đúng nhánh cần di chuyển. Lệnh reset thay đổi HEAD, index và working tree, vì vậy chỉ dùng khi các thay đổi chưa commit đã được giữ an toàn.

## 7. Khôi phục nhánh đã bị xóa

Giả sử bạn đã xóa nhánh:

~~~bash
git branch -D feature/report
~~~

Sau đó nhận ra nhánh vẫn còn commit chưa được tích hợp. Nếu commit vẫn được giữ trong reflog HEAD hoặc nơi khác, bạn có thể tìm lại.

Xem nhật ký HEAD:

~~~bash
git reflog --date=local
~~~

Tìm entry khi bạn chuyển sang nhánh `feature/report`, tạo commit trên nhánh đó hoặc chuyển khỏi nhánh. Xác định hash của commit cuối cùng cần giữ.

Kiểm tra commit:

~~~bash
git show --stat <commit-id>
git log --oneline --decorate -8 <commit-id>
~~~

Tạo lại nhánh:

~~~bash
git switch -c feature/report <commit-id>
~~~

Lưu ý: xóa branch bằng `git branch -d` hoặc `git branch -D` thường xóa luôn reflog riêng của branch đó. Vì vậy, `git reflog show feature/report` có thể không còn kết quả. Reflog HEAD hoặc reflog của tham chiếu khác có thể vẫn chứa commit cần phục hồi.

## 8. Phục hồi sau khi reset nhầm nhánh

Một trường hợp khác là bạn đang ở nhánh `feature/report` nhưng chạy reset nhầm về commit của `main`:

~~~bash
git switch feature/report
git reset --hard origin/main
~~~

`reset --hard` thay đổi HEAD, index và working tree; các thay đổi chưa commit có thể bị mất. Trong ví dụ này, giả sử working tree đã sạch hoặc mọi thay đổi cần giữ đã được sao lưu. Nếu nhánh chưa push thay đổi này lên remote, tip cũ có thể vẫn còn trong reflog của nhánh hoặc HEAD.

Quy trình:

**Bước 1 — Xác định nhánh và trạng thái hiện tại**

~~~bash
git status
git branch --show-current
~~~

**Bước 2 — Tìm tip cũ trong reflog**

~~~bash
git reflog show feature/report --date=local
~~~

Nếu nhánh reflog không còn hoặc không rõ, kiểm tra:

~~~bash
git reflog --date=local
~~~

**Bước 3 — Xác minh hash**

~~~bash
git show --stat <old-tip>
git log --oneline --graph -10 <old-tip>
~~~

**Bước 4 — Tạo nhánh cứu hộ từ commit cũ**

~~~bash
git branch recover/feature-report <old-tip>
~~~

**Bước 5 — Kiểm tra nội dung đã phục hồi**

~~~bash
git switch recover/feature-report
git status
git log --oneline --decorate -10
~~~

Nếu nhánh cứu hộ đúng, bạn có thể tiếp tục phát triển trên đó hoặc phối hợp với nhóm để đưa thay đổi trở lại nhánh làm việc chính.

## 9. Dùng reflog để khôi phục sau rebase

Rebase thay đổi hash của các commit được phát lại. Nếu rebase đã hoàn tất và bạn nhận ra nhánh bị đặt sai nền, reflog có thể chứa tip trước khi rebase bắt đầu.

Xem nhật ký:

~~~bash
git reflog show feature/report --date=local
~~~

Tìm các entry có mô tả như:

~~~text
rebase (finish): returning to refs/heads/feature/report
rebase (pick): Add report export
rebase (start): checkout main
~~~

Entry trước `rebase (start)` thường là tip của nhánh trước rebase. Xác minh hash đó bằng `git show`, sau đó tạo nhánh cứu hộ:

~~~bash
git branch rescue/feature-report-after-rebase <old-tip>
~~~

Nếu mục tiêu là đưa nhánh hiện tại trở lại tip cũ, hãy giữ lại trạng thái sau rebase bằng một nhánh khác trước khi di chuyển nhánh. Khi đã kiểm tra working tree và chọn đúng commit, cập nhật nhánh theo cách phù hợp với trạng thái checkout. Với rebase vẫn đang chạy, dùng `git rebase --abort` thay vì tìm reflog để tự reset giữa tiến trình.

## 10. Nếu reflog không còn entry cần tìm

Reflog có thời hạn lưu và chỉ tồn tại cục bộ. Entry có thể hết hạn theo cấu hình, và các object không còn được tham chiếu có thể bị Git garbage collection dọn đi. Nếu không tìm thấy commit trong reflog, vẫn có thể thử tìm object chưa được tham chiếu.

Chạy:

~~~bash
git fsck --no-reflogs --unreachable
~~~

Git có thể liệt kê các object không thể truy cập từ ref hoặc reflog. Hãy chú ý các dòng dạng:

~~~text
unreachable commit 9f7a2b1...
dangling commit 4c8d6e3...
~~~

Xem từng commit ứng viên:

~~~bash
git show --stat 9f7a2b1
git log --oneline --graph -8 9f7a2b1
~~~

Khi đã xác minh đúng commit, tạo nhánh để giữ nó:

~~~bash
git branch recover/found-commit 9f7a2b1
~~~

`git fsck` có thể trả về nhiều object không liên quan. Không tạo nhánh từ một hash chỉ vì nó xuất hiện trong kết quả; hãy kiểm tra nội dung và lịch sử.

Nếu object đã bị garbage collection loại bỏ và không còn trong bản clone khác hoặc bản sao lưu, Git có thể không còn đủ dữ liệu để khôi phục.

## 11. Reflog có thể khôi phục điều gì và không thể khôi phục điều gì?

Reflog ghi lại sự thay đổi của tham chiếu, không phải nhật ký đầy đủ mọi thao tác trên file.

| Tình huống | Reflog có giúp không? | Ghi chú |
|---|---|---|
| Reset nhầm làm mất tip nhánh | Thường có | Tìm tip cũ rồi tạo nhánh mới |
| Xóa nhánh local | Có thể | HEAD reflog hoặc reflog khác có thể còn hash commit |
| Rebase sai đã hoàn tất | Thường có | Tìm tip trước rebase |
| Checkout sang nhánh khác | Có | HEAD reflog ghi lại chuyển nhánh |
| Thay đổi chưa commit bị mất | Không trực tiếp | Reflog không lưu working tree |
| File chưa được theo dõi bị xóa | Không | Cần bản sao lưu, stash nếu đã lưu hoặc công cụ phục hồi file |
| Commit đã bị garbage collection dọn | Không còn nếu object không tồn tại ở nơi khác | Thử clone khác, backup hoặc artifact có chứa object |

Điều này giải thích vì sao nên commit công việc quan trọng hoặc lưu thay đổi chưa commit bằng stash trước thao tác có rủi ro. Reflog là công cụ phục hồi commit và tham chiếu, không thay thế backup.

## 12. Reflog chỉ có trong repository local

Mỗi bản clone có reflog riêng. Ví dụ, nếu bạn xóa nhánh local trên máy A, reflog của máy B không bị ảnh hưởng. Nếu đồng đội vẫn có nhánh hoặc commit cũ, họ có thể giúp tìm lại hash.

Ngược lại, nếu bạn push một nhánh lên remote rồi sau đó force push, reflog local của bạn không tự động trở thành nhật ký phục hồi trên máy chủ. Một số nền tảng có cơ chế khôi phục riêng, nhưng không nên mặc định remote cung cấp reflog cho người dùng.

Khi phục hồi một commit đã từng được chia sẻ, hãy cân nhắc cách đưa nó trở lại quy trình nhóm:

- Tạo nhánh phục hồi mới và push lên remote.
- Mở Pull Request/Merge Request để review thay đổi.
- Nếu cần di chuyển nhánh dùng chung, phối hợp với maintainer và kiểm tra lịch sử remote trước.
- Tránh force push chỉ để làm cho tên nhánh trông giống như trước nếu có người khác đã dựa vào lịch sử mới.

## 13. Quy trình thực hành: cứu nhánh feature/report sau reset nhầm

Giả sử bạn đang phát triển báo cáo. Nhánh `feature/report` có hai commit chưa được tích hợp. Bạn vô tình chạy:

~~~bash
git reset --hard HEAD~2
~~~

Hai commit không còn ở đầu nhánh. Hãy thực hiện theo quy trình sau.

**Bước 1 — Kiểm tra repository**

~~~bash
git status
git branch --show-current
git log --oneline --decorate -8
~~~

**Bước 2 — Xem reflog**

~~~bash
git reflog --date=local
~~~

Tìm entry trước dòng `reset: moving to HEAD~2`. Giả sử hash tip cũ là `b72c4e8`.

**Bước 3 — Kiểm tra commit**

~~~bash
git show --stat b72c4e8
git log --oneline --graph -8 b72c4e8
~~~

Xác nhận hai commit báo cáo cần giữ đều nằm trong lịch sử.

**Bước 4 — Tạo nhánh cứu hộ**

~~~bash
git branch recover/feature-report b72c4e8
~~~

**Bước 5 — Chuyển sang nhánh cứu hộ và kiểm tra**

~~~bash
git switch recover/feature-report
git status
git log --oneline --decorate -8
~~~

Nhánh `recover/feature-report` hiện giữ lịch sử cũ. Bạn có thể tiếp tục làm việc trên nhánh này, so sánh với nhánh hiện tại hoặc tạo PR/MR để đưa thay đổi trở lại quy trình nhóm.

## 14. Những lỗi thường gặp khi phục hồi

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không thấy reflog của nhánh đã xóa | Git thường xóa reflog riêng khi xóa branch | Xem reflog HEAD và các reflog còn lại |
| Chọn nhầm entry reflog | Entry gần nhất không nhất thiết là tip cần phục hồi | Kiểm tra hash bằng `git show` và `git log` |
| `git branch` báo tên đã tồn tại | Nhánh chưa bị xóa hoặc đã được tạo lại | Dùng tên nhánh cứu hộ khác; không ghi đè khi chưa sao lưu |
| Commit không còn trong reflog | Entry đã hết hạn hoặc ref bị xóa | Thử `git fsck --no-reflogs --unreachable` và kiểm tra clone khác |
| Nhánh phục hồi có vẻ thiếu file | Chọn commit cũ hơn mốc mong muốn hoặc file chưa từng commit | Kiểm tra log, diff và backup của working tree |
| Push nhánh phục hồi bị từ chối | Remote có lịch sử mới hoặc chính sách bảo vệ | Fetch, xem lịch sử và push nhánh mới để review |

Khi gặp lỗi, hãy kiểm tra tên nhánh, commit đích và trạng thái local/remote trước khi xóa hoặc ghi đè.

## 15. Checklist trước khi khôi phục nhánh

Trước khi tạo hoặc di chuyển nhánh, hãy kiểm tra:

- [ ] Xác nhận đúng repository và nhánh đang thao tác.
- [ ] Chạy `git status` để kiểm tra thay đổi chưa commit.
- [ ] Xem `git reflog` hoặc `git reflog show <branch>`.
- [ ] Tìm hash của commit trước thao tác sai.
- [ ] Xác minh commit bằng `git show` và `git log`.
- [ ] Tạo nhánh cứu hộ nếu cần giữ trạng thái hiện tại.
- [ ] Tạo nhánh phục hồi từ hash đã xác minh.
- [ ] Kiểm tra working tree, diff và lịch sử sau khi phục hồi.
- [ ] Nếu cần chia sẻ, push nhánh phục hồi mới và phối hợp qua PR/MR.

## 16. Những điểm cần ghi nhớ

- Reflog ghi lại lịch sử thay đổi của HEAD và các tham chiếu Git trong repository local.
- `git reflog` là điểm bắt đầu tốt để tìm commit trước reset, rebase hoặc thao tác xóa nhánh.
- `HEAD@{n}` là vị trí trong reflog; `HEAD~n` là số bước đi theo commit cha.
- Luôn xác minh commit bằng `git show`, `git show --stat` và `git log` trước khi tạo nhánh.
- `git branch <ten-nhanh> <commit>` tạo nhánh mới tại commit được chỉ định.
- Nếu nhánh cũ vẫn tồn tại, tạo nhánh cứu hộ trước khi di chuyển tham chiếu.
- Reflog không lưu thay đổi chưa commit và không được chia sẻ lên remote.
- Khi reflog không còn entry, có thể thử `git fsck --no-reflogs --unreachable` hoặc tìm trong bản clone khác.
- Reflog và object chưa được tham chiếu có thể hết hạn hoặc bị garbage collection dọn; phục hồi càng sớm càng tốt.

Khi mất một nhánh, điều quan trọng là tìm lại commit mà nhánh từng trỏ tới. Một khi đã xác minh được commit đó, tạo nhánh mới từ hash sẽ giúp giữ lịch sử và đưa công việc trở lại quy trình phát triển một cách có kiểm soát.


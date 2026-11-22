# Xem, xóa và phục hồi stash bị mất trước khi đối tượng bị dọn

Git stash giúp cất tạm thay đổi trong working tree để bạn chuyển nhánh hoặc xử lý một công việc khác. Mỗi stash được lưu dưới dạng các đối tượng Git và được quản lý qua tham chiếu `refs/stash` cùng reflog của nó. Bạn có thể xem lại, áp dụng, lấy stash ra khỏi danh sách hoặc xóa stash khi không còn cần thiết.

Nếu một stash bị xóa nhầm, dữ liệu đôi khi vẫn còn trong object database dưới dạng commit không còn được tham chiếu. Khi các đối tượng này chưa bị Git dọn, bạn có thể tìm chúng bằng `git fsck`, xác định commit stash phù hợp rồi tạo lại một tham chiếu để phục hồi. Vì thời gian tồn tại của đối tượng không được tham chiếu là có giới hạn và phụ thuộc cấu hình dọn dẹp, hãy ngừng các thao tác prune và tìm cách giữ đối tượng càng sớm càng tốt.

## 1. Stash được lưu và đánh số như thế nào?

Git lưu danh sách stash thông qua ref `refs/stash`. Mỗi lần tạo stash mới, Git cập nhật ref này và ghi một mục trong reflog. Các tên như `stash@{0}`, `stash@{1}` là cách truy cập theo vị trí trong reflog:

- `stash@{0}` thường là stash mới nhất.
- `stash@{1}` là stash đứng ngay trước nó.
- Chỉ số thay đổi khi bạn thêm hoặc xóa stash.

Vì chỉ số có thể dịch chuyển, hãy kiểm tra `git stash list` trước khi dùng `stash@{n}`. Nếu cần nhận diện một stash cụ thể qua nhiều thao tác, có thể lấy OID của commit stash và ghi lại:

```bash
git stash list
git rev-parse 'stash@{0}'
```

Về cấu trúc, một stash thường là một commit có parent thứ nhất trỏ đến commit `HEAD` tại thời điểm cất tạm, parent thứ hai lưu trạng thái index, và có thể có parent thứ ba chứa các tệp chưa được theo dõi nếu stash được tạo với `-u` hoặc `-a`. Tùy chọn `-a` còn bao gồm cả tệp bị ignore. Tree của commit stash mô tả trạng thái working tree đã cất.

Hiểu cấu trúc này hữu ích khi phục hồi stash đã mất: `git fsck` có thể tìm thấy commit stash dù nó không còn xuất hiện trong `git stash list`.

## 2. Liệt kê và xem nội dung stash

Liệt kê các stash hiện có:

```bash
git stash list
```

Ví dụ:

```text
stash@{0}: On feature/payment: save payment validation
stash@{1}: WIP on main: 4c2a1b7 update documentation
stash@{2}: On feature/search: add unfinished search flow
```

Thông điệp sau dấu hai chấm được tạo từ thông tin nhánh và commit nền hoặc từ nội dung `-m` bạn đã đặt. Nên đặt thông điệp cụ thể khi tạo stash để dễ nhận diện.

Xem thống kê thay đổi của một stash:

```bash
git stash show --stat 'stash@{0}'
```

Xem diff chi tiết:

```bash
git stash show -p 'stash@{0}'
```

Nếu stash có chứa tệp chưa được theo dõi, thêm `--include-untracked` để xem cả phần đó:

```bash
git stash show --stat --include-untracked 'stash@{0}'
git stash show -p --include-untracked 'stash@{0}'
```

Tùy chọn `--only-untracked` giới hạn phần hiển thị ở các tệp chưa được theo dõi có trong stash. Các tùy chọn xem này không thay đổi nội dung stash.

Mặc định, `git stash push` không cất các tệp chưa được theo dõi. Dùng `-u` (`--include-untracked`) để cất cả các tệp đó; dùng `-a` (`--all`) nếu cần cất thêm các tệp bị ignore. Khi kiểm tra stash cũ, hãy nhớ rằng các tệp không được đưa vào stash từ đầu sẽ không thể xuất hiện trong quá trình phục hồi.

## 3. Áp dụng, phục hồi và xóa stash

### Apply: áp dụng nhưng giữ stash trong danh sách

```bash
git stash apply 'stash@{0}'
```

`apply` đưa thay đổi từ stash vào working tree hiện tại và giữ nguyên mục stash. Đây thường là lựa chọn tốt khi bạn muốn kiểm tra kết quả trước khi quyết định xóa stash.

Nếu muốn khôi phục cả trạng thái staged đã được lưu trong stash, dùng `--index`:

```bash
git stash apply --index 'stash@{0}'
```

Git sẽ cố gắng khôi phục cả trạng thái index. Nếu việc áp dụng index không thành công do xung đột hoặc khác biệt trạng thái, bạn có thể phải giải quyết thủ công và kiểm tra lại staging area.

### Pop: áp dụng rồi xóa khỏi danh sách khi thành công

```bash
git stash pop 'stash@{0}'
```

`pop` tương tự `apply`, nhưng Git xóa stash khỏi danh sách nếu việc áp dụng thành công. Nếu có xung đột khiến việc áp dụng không hoàn tất, stash thường được giữ lại để bạn xử lý và thử lại. Với công việc quan trọng, hãy dùng `apply` trước, kiểm tra kết quả, rồi mới `drop` khi chắc chắn không cần bản stash nữa.

### Branch: tạo nhánh từ commit nền của stash

Khi stash được tạo trên một nhánh khác hoặc áp dụng vào nhánh hiện tại dễ gây xung đột, có thể dùng:

```bash
git stash branch recover/payment-work 'stash@{0}'
```

Git tạo và chuyển sang nhánh mới tại commit mà stash ban đầu được tạo, sau đó áp dụng thay đổi của stash. Nếu áp dụng thành công, mục stash được xóa khỏi danh sách. Cách này thường hữu ích khi muốn tiếp tục công việc trong đúng bối cảnh ban đầu.

### Drop: xóa một mục stash

```bash
git stash drop 'stash@{1}'
```

Lệnh này xóa mục được chỉ định khỏi danh sách stash. Hãy kiểm tra `git stash list` ngay trước khi drop vì chỉ số `stash@{n}` có thể đã thay đổi sau các thao tác khác.

### Clear: xóa toàn bộ danh sách stash

```bash
git stash clear
```

`clear` xóa tất cả các mục stash. Các đối tượng commit có thể trở thành unreachable và cuối cùng bị dọn khỏi object database. Không dùng `clear` như một cách làm sạch thường xuyên nếu chưa xác nhận mọi stash đều không còn cần thiết.

## 4. Hiểu stash bị mất và đối tượng unreachable

Khi stash còn trong danh sách, ref `refs/stash` và reflog giúp Git tìm đến commit stash. Khi bạn drop một mục hoặc clear danh sách, một số commit stash có thể không còn ref nào trỏ đến. Chúng trở thành đối tượng không thể truy cập từ các ref hiện tại, thường được gọi là **unreachable** hoặc **dangling** tùy cách kiểm tra.

Unreachable không có nghĩa là dữ liệu đã bị xóa ngay lập tức. Nội dung đối tượng có thể vẫn còn trong `.git/objects` hoặc object database được đóng gói. Git có thể dọn chúng trong các lần garbage collection/prune tiếp theo khi chúng đã quá hạn theo cấu hình.

Vì vậy, nếu vừa xóa nhầm stash:

1. Dừng các thao tác dọn dẹp như `git gc --prune=now`, `git prune` hoặc lệnh làm hết hạn reflog ngay lập tức.
2. Tránh chạy các công cụ tự động dọn object database trong lúc tìm stash.
3. Tìm commit stash còn sót và tạo ref giữ lại nó trước khi tiếp tục các công việc khác.

Không có thời hạn phục hồi cố định cho mọi repository. Tuổi đối tượng, reflog, cấu hình `gc.pruneExpire`, `gc.reflogExpire`, tác vụ bảo trì và phiên bản Git đều có thể ảnh hưởng việc đối tượng còn tồn tại hay không.

## 5. Kiểm tra reflog trước khi tìm object bị mất

Nếu ref stash vẫn tồn tại, xem reflog của nó:

```bash
git reflog show refs/stash
```

Reflog ghi lại những lần một ref thay đổi. Nếu mục cần tìm vẫn còn trong reflog, bạn có thể lấy OID tương ứng rồi tạo lại mục stash hoặc áp dụng trực tiếp. Tuy nhiên, thao tác `drop` và đặc biệt `clear` có thể loại bỏ mục hoặc reflog liên quan; khi đó cần tìm object unreachable.

Kiểm tra các ref và reflog khác nếu bạn từng tạo một nhánh hoặc tag trỏ đến commit stash. Một ref dự phòng như vậy vẫn có thể giữ commit sống và giúp khôi phục dễ dàng hơn.

## 6. Tìm stash đã bị drop hoặc clear bằng git fsck

`git fsck` kiểm tra tính toàn vẹn object database và có thể liệt kê các đối tượng không còn được tham chiếu. Dùng:

```bash
git fsck --full --no-reflogs --unreachable
```

Lệnh này yêu cầu Git kiểm tra đầy đủ và liệt kê các đối tượng unreachable mà không xem reflog như một gốc tham chiếu. Trong kết quả, chú ý các dòng có dạng:

```text
unreachable commit 7a91d2f...
unreachable tree  1b52e30...
```

Các commit được liệt kê có thể là stash đã mất, commit cũ sau rebase, commit bị bỏ hoặc dữ liệu khác. Không phải mọi unreachable commit đều là stash, vì vậy cần kiểm tra từng ứng viên.

Nếu muốn Git ghi các đối tượng dangling vào thư mục `.git/lost-found` để tiện kiểm tra, có thể chạy:

```bash
git fsck --full --no-reflogs --lost-found
```

`--lost-found` tạo các tệp tham chiếu trong thư mục nội bộ của Git; nó không tự khôi phục stash vào danh sách và cũng không tự áp dụng thay đổi vào working tree.

## 7. Nhận diện commit stash trong danh sách ứng viên

Với mỗi OID có kiểu `commit`, xem metadata và các parent:

```bash
git cat-file -p <stash-oid>
```

Một stash commit thường có thông điệp như `WIP on ...` hoặc `On ...`, có parent đầu là commit nền và parent thứ hai là commit lưu index. Nếu stash từng bao gồm tệp chưa được theo dõi, có thể có parent thứ ba. Cấu trúc này giúp phân biệt ứng viên stash với commit thông thường.

Xem thông tin tóm tắt và diff so với commit nền:

```bash
git show --stat --oneline <stash-oid>
git diff <stash-oid>^1 <stash-oid>
```

Trong lệnh thứ hai, `^1` là parent thứ nhất của stash commit. Diff giữa parent thứ nhất và commit stash cho thấy trạng thái working tree được lưu so với commit nền. Để kiểm tra riêng phần index, có thể so sánh parent thứ nhất với parent thứ hai:

```bash
git diff <stash-oid>^1 <stash-oid>^2
```

Nếu có parent thứ ba, đó thường là snapshot của các tệp chưa được theo dõi được lưu cùng stash. Có thể xem danh sách tệp trong tree đó:

```bash
git ls-tree -r <stash-oid>^3
```

Thay OID minh họa bằng mã đầy đủ mà `git fsck` trả về. Kiểm tra tên tệp, thông điệp, commit nền và nội dung diff để xác nhận đây đúng là stash cần tìm. Đừng chọn chỉ dựa trên thông điệp `WIP`, vì commit khác cũng có thể dùng thông điệp tương tự.

## 8. Tạo lại tham chiếu và phục hồi stash

Khi đã xác nhận OID là stash commit phù hợp, hãy lưu nó vào stash stack bằng `git stash store`:

```bash
git stash store -m "Recovered payment work" <stash-oid>
```

Lệnh này ghi commit stash vào `refs/stash` và reflog, giúp Git tiếp tục quản lý nó như một stash. Kiểm tra lại:

```bash
git stash list
git stash show --stat 'stash@{0}'
```

Nếu muốn giữ commit bằng một ref riêng để dễ tra cứu, có thể tạo ref khôi phục trước:

```bash
git update-ref refs/recovery/stash-payment <stash-oid>
```

Ref dưới `refs/recovery/` giữ đối tượng khỏi bị xem là unreachable. Không cần checkout ref này. Nếu đã tạo ref riêng, vẫn nên chạy `git stash store` như bước trên để đưa commit vào stash stack; ref riêng là bản giữ an toàn bổ sung, còn `stash@{0}` là mục vừa được đưa trở lại danh sách.

Sau khi commit đã được đưa trở lại stash stack, áp dụng vào working tree phù hợp:

```bash
git stash apply --index 'stash@{0}'
```

Ưu tiên `apply` khi phục hồi vì nó giữ stash lại để bạn có thể thử lại nếu phát sinh xung đột. Kiểm tra working tree và index:

```bash
git status
git diff
git diff --cached
```

Nếu nội dung đã được phục hồi và xác nhận đầy đủ, bạn có thể commit công việc hoặc tiếp tục chỉnh sửa. Chỉ xóa stash phục hồi khi đã chắc chắn không còn cần bản dự phòng.

## 9. Xử lý xung đột khi áp dụng stash phục hồi

Stash được tạo từ một trạng thái repository trước đó. Nếu tệp đã thay đổi đáng kể kể từ thời điểm đó, `apply` có thể phát sinh xung đột.

Khi gặp xung đột:

```bash
git status
```

Mở từng tệp được đánh dấu unmerged, kết hợp nội dung theo mục đích của thay đổi, xóa conflict marker và kiểm tra kết quả. Sau khi giải quyết:

```bash
git add src/payment/PaymentService.java
```

Kiểm tra cả phần staged và unstaged trước khi commit. Stash vẫn được giữ khi bạn dùng `apply`; nếu thao tác không thành công hoàn toàn, đừng vội drop nó. Nếu trạng thái hiện tại quá phức tạp, hãy tạo một nhánh hoặc worktree riêng để thử phục hồi, giữ nguyên ref cứu hộ cho đến khi xác minh xong.

Nếu cần phục hồi trong đúng bối cảnh commit ban đầu, có thể dùng `git stash branch` sau khi stash đã được đưa lại vào danh sách:

```bash
git stash branch recover/payment-work 'stash@{0}'
```

Lệnh tạo nhánh tại commit nền ban đầu, áp dụng stash rồi xóa mục stash nếu thành công. Nếu thao tác bị xung đột, xử lý trên nhánh mới và giữ lại các ref cứu hộ cho đến khi nội dung được xác minh.

## 10. Khi nào không thể phục hồi bằng git fsck?

`git fsck` chỉ có thể tìm các đối tượng vẫn còn trong object database. Nếu Git đã prune đối tượng stash và không còn bản sao nào trong reflog hoặc ref khác, OID cũ không thể tái tạo nội dung đã mất.

Khi không tìm thấy stash:

- Kiểm tra các clone khác của cùng repository; object có thể vẫn còn ở máy của đồng đội.
- Kiểm tra backup của thư mục `.git`, snapshot ổ đĩa hoặc hệ thống sao lưu của máy.
- Kiểm tra lịch sử local của IDE, bản vá đã xuất, file tạm hoặc bản sao nội dung trong trình soạn thảo.
- Nếu một phần thay đổi đã được commit ở nhánh khác, dùng `git log`, `git reflog` hoặc tìm commit tương ứng để lấy lại phần đó.

Không nên tiếp tục chạy prune hoặc garbage collection với hy vọng Git sẽ phục hồi thêm dữ liệu. Các lệnh dọn dẹp chỉ có thể loại bỏ thêm những object chưa được bảo vệ.

## 11. Quy trình an toàn khi xem và dọn stash

Một quy trình ngắn giúp tránh mất stash ngoài ý muốn:

```bash
# 1. Liệt kê và xem các stash
git stash list
git stash show --stat 'stash@{0}'
git stash show -p 'stash@{0}'

# 2. Áp dụng thử nhưng giữ stash
git stash apply --index 'stash@{0}'

# 3. Kiểm tra kết quả
git status
git diff
git diff --cached

# 4. Chỉ xóa stash cụ thể khi đã xác nhận không còn cần
git stash drop 'stash@{0}'
```

Nếu cần xóa nhiều stash, hãy xem từng mục, ghi lại những OID quan trọng hoặc tạo ref dự phòng trước. `git stash clear` là thao tác xóa toàn bộ danh sách; chỉ dùng khi đã xác nhận không còn công việc cần phục hồi.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| `git stash drop` xóa object ngay lập tức | Nó gỡ mục khỏi stash reflog; object có thể còn trong object database cho đến khi được prune. |
| `git stash clear` có thể hoàn tác bằng một lệnh đơn giản | Clear loại bỏ danh sách stash và reflog liên quan; cần tìm object unreachable nếu dữ liệu chưa bị dọn. |
| `stash@{0}` là định danh cố định | Đây là vị trí trong reflog và có thể thay đổi sau khi thêm hoặc xóa stash. |
| `git stash apply` xóa stash | Apply giữ stash; pop mới xóa mục khi áp dụng thành công. |
| `git fsck` tự phục hồi stash | Fsck chỉ tìm và báo object; bạn cần nhận diện commit, tạo ref hoặc dùng `git stash store`, rồi tự áp dụng. |
| Mọi unreachable commit đều là stash | Có thể là commit cũ từ rebase, reset hoặc thao tác khác; phải kiểm tra parent, message và diff. |
| Đã drop stash thì chắc chắn mất dữ liệu | Object có thể vẫn còn cho đến khi Git dọn; phục hồi phụ thuộc việc object còn tồn tại và được nhận diện đúng. |

## 13. Tự kiểm tra

1. **Lệnh nào liệt kê stash hiện có?**
   - `git stash list`.
2. **Khác biệt giữa `apply` và `pop` là gì?**
   - Apply giữ stash trong danh sách; pop áp dụng và xóa mục nếu áp dụng thành công.
3. **Sau khi drop stash, vì sao vẫn có thể phục hồi?**
   - Commit stash có thể vẫn tồn tại dưới dạng object unreachable cho đến khi bị garbage collection/prune dọn.
4. **Lệnh nào tìm các object unreachable trong repository?**
   - `git fsck --full --no-reflogs --unreachable`.
5. **Sau khi nhận diện đúng stash commit, lệnh nào đưa nó trở lại stash stack?**
   - `git stash store -m "Recovered stash" <oid>`.
6. **Vì sao nên giữ một ref cứu hộ trước khi áp dụng stash phục hồi?**
   - Ref giữ object không bị xem là unreachable, giúp bạn còn điểm quay lại nếu thao tác áp dụng hoặc xử lý xung đột gặp vấn đề.

## Kết luận

Hãy dùng `git stash list` và `git stash show` để xem nội dung, `apply` hoặc `branch` để phục hồi, và `drop` hoặc `clear` để dọn các mục không còn cần. Nếu stash bị xóa nhầm, kiểm tra reflog rồi tìm commit unreachable bằng `git fsck --full --no-reflogs --unreachable`. Khi xác định đúng commit stash, dùng `git stash store` hoặc tạo ref cứu hộ để giữ object, sau đó áp dụng và kiểm tra thay đổi. Cơ hội phục hồi chỉ còn khi object chưa bị dọn, vì vậy hãy tránh prune và garbage collection trong lúc tìm kiếm.

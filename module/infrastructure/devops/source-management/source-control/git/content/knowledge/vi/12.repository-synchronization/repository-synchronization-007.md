# Từ chối non-fast-forward: nguyên nhân và cách xử lý

Khi `git push` bị từ chối với thông báo `non-fast-forward`, Git đang bảo vệ lịch sử đã có trên remote. Commit mà bạn định đẩy không chứa commit mới nhất hiện có ở nhánh đích, nên nếu cập nhật con trỏ nhánh theo cách thông thường, một phần lịch sử remote có thể bị bỏ khỏi nhánh đó. Cách xử lý an toàn là cập nhật thông tin remote, xem hai phía đã thay đổi gì, tích hợp các commit cần giữ rồi push lại.

## 1. Fast-forward và non-fast-forward là gì?

Mỗi nhánh Git trỏ tới một commit. Khi push, Git kiểm tra quan hệ giữa commit hiện tại của nhánh remote và commit mới mà client muốn đưa lên.

**Fast-forward** xảy ra khi commit đang ở remote là tổ tiên của commit mới. Git chỉ cần di chuyển con trỏ nhánh remote tiến lên commit mới mà không phải bỏ qua lịch sử nào.

Ví dụ, remote đang ở `B`, còn nhánh local có thêm `C`:

```text
A---B---C
    ^   ^
 remote local
```

Push từ local lên remote có thể fast-forward từ `B` tới `C`.

**Non-fast-forward** xảy ra khi commit remote không phải tổ tiên của commit mà bạn định push. Ví dụ, sau commit chung `B`, hai phía có commit riêng:

```text
      C  (origin/main)
     /
A---B
     \
      D  (main local)
```

Local có `D`, remote có `C`. Nếu push `D` trực tiếp lên `main`, Git sẽ phải làm cho nhánh remote bỏ qua `C`. Vì `C` chưa nằm trong lịch sử của `D`, thao tác đó bị từ chối theo quy tắc push thông thường.

Sau khi tích hợp hai phía, lịch sử có thể trở thành một trong hai dạng:

```text
Merge:
      C-------M
     /       /
A---B-------D

Rebase:
A---B---C---D'
```

Merge giữ nguyên commit `D` và tạo commit kết hợp `M`. Rebase phát lại thay đổi của `D` trên `C`, tạo commit mới `D'`. Cả hai cách đều có thể tạo lịch sử mà remote tip là tổ tiên của commit mới, cho phép push thông thường.

## 2. Những nguyên nhân thường gặp

### 2.1. Người khác đã push trước bạn

Bạn và đồng đội cùng làm trên một nhánh. Sau lần fetch gần nhất, đồng đội push thêm commit lên remote. Nhánh local của bạn chưa có commit đó, nên push bị từ chối để bảo vệ thay đổi mới.

### 2.2. Nhánh local và remote đã phân kỳ

Bạn có commit local riêng trong khi remote cũng có commit mới. Hai nhánh có một tổ tiên chung nhưng mỗi bên đi theo một hướng. Cần tích hợp hai lịch sử trước khi push.

### 2.3. Remote-tracking branch đã cũ

`origin/main` là tham chiếu local ghi lại trạng thái nhánh remote ở lần fetch gần nhất. Nếu lâu chưa fetch, `origin/main` có thể chưa phản ánh commit mới trên máy chủ. `git status` và `git branch -vv` chỉ so sánh với tham chiếu local đó; chúng không tự hỏi máy chủ tại thời điểm chạy.

### 2.4. Bạn đang push tới nhánh đích khác dự kiến

Refspec hoặc cấu hình upstream có thể khiến Git push nhánh local vào một nhánh remote mà bạn không định cập nhật. Hãy kiểm tra tên remote, nhánh hiện tại và đích push trước khi đồng bộ.

### 2.5. Nhánh remote đã được cập nhật trong lúc bạn xử lý

Ngay cả khi fetch và tích hợp thành công, một người khác vẫn có thể push commit mới trước khi lệnh push của bạn đến máy chủ. Khi đó push lại có thể tiếp tục bị từ chối. Đây là tình huống cộng tác bình thường; cần fetch và tích hợp phần mới nhất một lần nữa.

## 3. Đọc thông báo để xác định đúng loại từ chối

Thông báo `failed to push some refs` là dòng tổng quát, chưa đủ để kết luận nguyên nhân. Hãy đọc dòng chi tiết đi kèm.

| Dấu hiệu | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| `[rejected] ... (non-fast-forward)` | Nhánh remote có lịch sử mà commit định push chưa bao gồm | Fetch, xem khác biệt, merge hoặc rebase rồi push lại |
| `[remote rejected] ... (protected branch hook declined)` | Máy chủ từ chối vì chính sách nhánh hoặc hook | Dùng pull request hoặc quy trình được quản trị repository quy định |
| `Permission denied` hoặc `403` | Danh tính hoặc quyền ghi không đáp ứng yêu cầu | Kiểm tra credential, quyền repository và quyền cập nhật nhánh |
| `stale info` khi dùng `--force-with-lease` | Remote đã thay đổi so với trạng thái mà lease kỳ vọng | Fetch, xem commit mới và quyết định lại trước khi ghi đè lịch sử |
| `src refspec ... does not match any` | Nhánh hoặc ref nguồn không tồn tại, hoặc chưa có commit phù hợp | Kiểm tra tên nhánh, refspec và trạng thái commit local |

Từ chối do branch protection, hook hoặc quyền truy cập không được giải quyết bằng cách merge/rebase. Trước tiên hãy phân biệt lỗi non-fast-forward thực sự với các chính sách phía máy chủ.

## 4. Quy trình chẩn đoán trước khi tích hợp

Trước khi thay đổi lịch sử, kiểm tra repository và nhánh đang làm việc:

```bash
git status -sb
git branch -vv
git remote -v
```

- `git status -sb` cho biết nhánh hiện tại và trạng thái working tree.
- `git branch -vv` cho biết upstream của từng nhánh và số commit ahead/behind theo remote-tracking refs local.
- `git remote -v` xác nhận URL fetch/push của remote.

Nếu working tree còn thay đổi chưa commit, hãy xác định và lưu chúng theo quy trình làm việc của bạn trước khi bắt đầu merge hoặc rebase. Đừng để các chỉnh sửa chưa lưu bị lẫn với việc giải quyết xung đột.

Tiếp theo, cập nhật thông tin từ remote:

```bash
git fetch origin
```

`fetch` tải các đối tượng cần thiết và cập nhật remote-tracking refs như `origin/main`. Nó không tự thay đổi nhánh local hiện tại hoặc hợp nhất nội dung vào working tree.

So sánh lịch sử hai phía:

```bash
git log --oneline --graph --decorate --left-right HEAD...origin/main
```

Thay `origin/main` bằng upstream thực tế. Với `--left-right`, commit chỉ có ở phía `HEAD` được đánh dấu `<`, còn commit chỉ có ở phía `origin/main` được đánh dấu `>`. Nhờ đó bạn thấy commit local và remote đang khác nhau ở đâu.

Có thể kiểm tra nhanh remote tip đã là tổ tiên của local hay chưa:

```bash
git merge-base --is-ancestor origin/main HEAD
```

Nếu lệnh trả mã thoát `0`, `origin/main` là tổ tiên của `HEAD`; push thông thường có thể fast-forward về mặt quan hệ lịch sử. Nếu trả mã khác `0`, cần xem xét tích hợp hoặc một tình huống lịch sử khác trước khi push. Lệnh này chỉ so sánh các commit local hiện có; vì vậy phải fetch trước để remote-tracking ref được cập nhật.

## 5. Cách xử lý bằng merge

Merge phù hợp khi nhóm muốn giữ nguyên danh tính commit đã tạo và ghi nhận điểm kết hợp hai nhánh trong lịch sử.

Giả sử bạn đang ở nhánh `main` local và cần tích hợp `origin/main`:

```bash
git fetch origin
git merge origin/main
```

Nếu không có xung đột, Git kết hợp lịch sử. Nếu có xung đột, đọc `git status`, kiểm tra cả hai phía và sửa nội dung theo ý nghĩa cần giữ. Sau đó:

```bash
git add path/to/resolved-file
git diff --cached
git merge --continue
```

Lặp lại với mọi file còn xung đột. Sau khi merge hoàn tất, push lại:

```bash
git push origin main
```

Nếu nhánh đang làm là nhánh tính năng, hãy thay `main` bằng tên nhánh tương ứng. Khi upstream đã được cấu hình đúng, `git push` có thể đủ; chỉ định rõ remote và nhánh giúp tránh push nhầm đích.

Nếu merge không thể hoàn tất hoặc bạn quyết định dừng thao tác, `git merge --abort` có thể đưa repository về trạng thái trước khi bắt đầu merge. Trước khi abort, hãy đọc trạng thái và bảo đảm các thay đổi chưa commit của bạn đã được lưu an toàn.

## 6. Cách xử lý bằng rebase

Rebase phù hợp khi bạn muốn phát lại các commit local chưa chia sẻ trên đầu lịch sử mới nhất của remote, tạo một đường lịch sử tuyến tính hơn.

Ví dụ trên nhánh tính năng `feature/report`:

```bash
git fetch origin
git switch feature/report
git rebase origin/feature/report
```

Git phát lại từng commit local trên đầu `origin/feature/report`. Nếu xảy ra xung đột:

```bash
git status
```

Sửa từng file để giữ đúng ý nghĩa, rồi đánh dấu và tiếp tục:

```bash
git add path/to/resolved-file
git rebase --continue
```

Nếu commit tiếp theo cũng xung đột, tiếp tục xử lý cho tới khi rebase hoàn tất. Khi cần hủy toàn bộ lần rebase đang thực hiện, dùng `git rebase --abort`.

Sau khi rebase thành công, push nhánh tính năng:

```bash
git push origin feature/report
```

Nếu các commit được rebase chỉ là commit local chưa từng chia sẻ, push thông thường thường hoạt động vì lịch sử mới được dựng trên tip remote vừa fetch. Rebase tạo commit có mã định danh mới. Nếu các commit cũ đã được người khác lấy về hoặc đang dùng chung, việc viết lại chúng có thể làm lịch sử của mọi người phân kỳ; hãy thống nhất với nhóm trước và cân nhắc merge để giữ nguyên commit đã chia sẻ.

## 7. Chọn merge hay rebase?

| Tiêu chí | Merge | Rebase |
|---|---|---|
| Commit cũ | Giữ nguyên mã commit | Tạo mã commit mới cho các commit được phát lại |
| Lịch sử | Ghi nhận điểm kết hợp bằng merge commit khi cần | Có thể tạo lịch sử tuyến tính |
| Phù hợp khi | Nhánh đã chia sẻ hoặc nhóm muốn lưu dấu lần tích hợp | Commit local chưa chia sẻ cần đặt trên nền remote mới |
| Xử lý xung đột | Có thể giải quyết trong một lần merge | Có thể phải giải quyết ở nhiều commit được phát lại |
| Rủi ro cộng tác | Thường dễ theo dõi vì không viết lại commit đã chia sẻ | Có thể làm người khác phải đồng bộ lại nếu viết lại lịch sử chung |

Không có một lựa chọn đúng cho mọi repository. Hãy theo quy ước của nhóm và cân nhắc ai đang sử dụng nhánh. Với nhánh dùng chung, merge thường ít gây xáo trộn lịch sử hơn. Với nhánh cá nhân chưa chia sẻ, rebase có thể giúp cập nhật nền trước khi push.

## 8. Khi nào được dùng force push?

`git push --force` yêu cầu máy chủ cập nhật ref bất kể quan hệ fast-forward. Nếu remote có commit mà bạn chưa giữ ở nơi khác, force push có thể làm commit đó không còn được tham chiếu từ nhánh và gây mất công việc của đồng đội.

Vì vậy, không dùng force push chỉ để làm biến mất thông báo non-fast-forward. Trước tiên hãy fetch và tích hợp commit remote theo quy trình bình thường.

Có một trường hợp cần viết lại lịch sử có chủ đích, chẳng hạn bạn vừa rebase một nhánh cá nhân đã từng push và nhóm đồng ý cập nhật lại nhánh đó. Khi ấy, `--force-with-lease` an toàn hơn `--force` vì Git kiểm tra remote vẫn ở trạng thái mà bạn kỳ vọng trước khi thay ref:

```bash
git fetch origin
git log --oneline --graph --decorate HEAD origin/feature/report
git push --force-with-lease origin feature/report
```

Hãy kiểm tra kỹ nhánh đích và các commit trước khi thực hiện. Nếu lease từ chối vì remote đã thay đổi, dừng lại, fetch và xem commit mới; đừng chuyển ngay sang `--force`. `--force-with-lease` giảm nguy cơ ghi đè thay đổi mới mà bạn chưa biết, nhưng vẫn có thể thay thế lịch sử remote khi điều kiện lease được thỏa mãn. Nó không thay thế việc phối hợp với người cùng làm nhánh và có thể bị branch protection chặn.

## 9. Tránh các cách xử lý làm mất lịch sử

- **Không chạy `git push --force` theo phản xạ.** Nó có thể khiến commit của người khác biến mất khỏi nhánh remote.
- **Không chạy `git reset --hard origin/main` chỉ để hết ahead/behind.** Lệnh này di chuyển nhánh local và ghi đè working tree/index, có thể làm mất commit hoặc thay đổi local chưa được lưu.
- **Không dùng `git pull` mà không biết chiến lược tích hợp đang được cấu hình.** `pull` thực hiện fetch rồi merge hoặc rebase tùy cấu hình và tùy chọn; khi đang xử lý sự cố, dùng `fetch` riêng để xem lịch sử trước sẽ rõ ràng hơn.
- **Không xóa commit remote chỉ vì nó không có trên máy bạn.** Hãy xem commit đó thuộc công việc của ai và có cần giữ không.
- **Không nhầm lỗi quyền hoặc branch protection với non-fast-forward.** Đọc toàn bộ thông báo từ máy chủ để chọn cách xử lý đúng.
- **Không rebase nhánh đã chia sẻ nếu chưa thống nhất.** Những người đã dựa trên commit cũ sẽ cần điều chỉnh lịch sử local của họ.

## 10. Ví dụ thực hành đầy đủ

Bạn đang làm trên nhánh `feature/report`. Lần cuối fetch, remote ở commit `B`. Bạn tạo commit `D` local. Trong lúc đó, đồng đội push commit `C` lên cùng nhánh:

```text
      C  (origin/feature/report)
     /
A---B
     \
      D  (feature/report)
```

Push bị từ chối vì remote có `C` mà local chưa tích hợp. Bạn kiểm tra trạng thái và fetch:

```bash
git status -sb
git fetch origin
git log --oneline --graph --decorate --left-right HEAD...origin/feature/report
```

Sau khi xác nhận `C` là thay đổi cần giữ, nhóm chọn merge để không viết lại commit đã chia sẻ:

```bash
git merge origin/feature/report
```

Nếu có xung đột, bạn giải quyết theo yêu cầu của hai thay đổi, chạy test, stage kết quả và hoàn tất merge. Sau đó:

```bash
git status -sb
git log --oneline --graph --decorate -5
git push origin feature/report
```

Nếu một đồng đội push thêm commit mới trong khoảng thời gian giữa fetch và push, máy chủ có thể từ chối lần push này một lần nữa. Hãy lặp lại việc fetch, xem commit mới và tích hợp chúng. Không force push để vượt qua lần từ chối thứ hai.

## 11. Ghi nhớ

Non-fast-forward là cơ chế bảo vệ lịch sử remote khi commit bạn định push chưa chứa commit đang có ở nhánh đích. Hãy fetch để biết trạng thái mới, so sánh hai phía, chọn merge hoặc rebase theo quy ước cộng tác, giải quyết xung đột và push lại. Chỉ viết lại lịch sử remote khi có chủ đích rõ ràng, đã phối hợp với người liên quan và dùng biện pháp kiểm tra như `--force-with-lease`.

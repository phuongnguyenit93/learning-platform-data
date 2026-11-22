# Reset theo đường dẫn so với reset con trỏ nhánh

`git reset` có hai cách sử dụng dễ bị nhầm lẫn. Khi đi kèm đường dẫn, lệnh cập nhật **index (staging area)** cho những file được chọn và không di chuyển `HEAD` hay con trỏ nhánh. Khi nhận một commit mà không có đường dẫn, lệnh có thể di chuyển `HEAD`/nhánh và tùy chế độ còn cập nhật index hoặc working tree.

Phân biệt hai dạng này giúp bạn bỏ staging một file mà vẫn giữ phần chỉnh sửa, hoặc đưa cả nhánh trở lại commit cũ khi thực sự muốn viết lại lịch sử local.

## 1. Hai dạng lệnh có mục đích khác nhau

### Reset theo đường dẫn: chỉ thay đổi index

Cú pháp tổng quát:

```bash
git reset [<tree-ish>] -- <pathspec>
```

Ví dụ thường gặp:

```bash
git reset -- src/config.yml
```

Khi bỏ qua `<tree-ish>`, Git dùng `HEAD`. Lệnh lấy phiên bản `src/config.yml` từ `HEAD` và chép mục tương ứng vào index. `HEAD` và branch hiện tại không thay đổi; file trong working tree cũng không bị ghi đè.

Đây là cách bỏ staging một file đã `git add` nhầm:

```bash
git add src/config.yml
git reset -- src/config.yml
```

Sau lệnh reset, nội dung staged của file trở về giống `HEAD`, còn phần chỉnh sửa trong working tree vẫn còn để bạn tiếp tục sửa hoặc stage lại.

Bạn có thể chọn một tree khác làm nguồn cho index:

```bash
git reset HEAD~1 -- src/config.yml
```

Lệnh trên lấy phiên bản file từ commit cha của `HEAD` để cập nhật index. Nó không chuyển branch về commit cha và không thay đổi nội dung file đang nằm trong working tree.

### Reset con trỏ nhánh: thay đổi vị trí HEAD

Khi không có pathspec, cú pháp có dạng:

```bash
git reset [--soft | --mixed | --hard | --merge | --keep] [<commit>]
```

Ví dụ:

```bash
git reset --mixed HEAD~1
```

Lệnh này di chuyển `HEAD` và nhánh hiện tại về commit cha, đồng thời đưa index về trạng thái của commit đó. Working tree được giữ lại. Các thay đổi từ commit vừa bỏ khỏi đầu nhánh trở thành thay đổi chưa staged trong working tree.

Khi đang ở một branch, reset commit sẽ cập nhật branch đó. Nếu đang ở trạng thái detached `HEAD`, Git chỉ di chuyển `HEAD` đang tách rời, không cập nhật một branch có tên.

## 2. Reset theo đường dẫn hoạt động như thế nào?

Index là nơi lưu nội dung sẽ được đưa vào commit tiếp theo. Khi bạn chạy `git add`, Git cập nhật mục trong index bằng nội dung hiện tại của file. Reset theo đường dẫn chép nội dung từ một tree vào index để thay thế mục đã stage.

Mô hình trước và sau khi bỏ staging:

```text
Trước git reset -- file
HEAD:       phiên bản A
Index:      phiên bản B  (đã stage)
Working tree: phiên bản C (có thể có sửa đổi tiếp)

Sau git reset -- file
HEAD:       phiên bản A
Index:      phiên bản A
Working tree: phiên bản C (được giữ nguyên)
```

Trạng thái sau reset có nghĩa là thay đổi B không còn nằm trong staging area. Nếu working tree khác A, Git vẫn hiển thị file là modified nhưng chưa staged.

Kiểm tra từng vùng:

```bash
git status
git diff --cached -- src/config.yml
git diff -- src/config.yml
```

- `git diff --cached` xem khác biệt giữa index và `HEAD`.
- `git diff` xem khác biệt giữa working tree và index.

Sau `git reset -- src/config.yml`, phần khác biệt staged thường biến mất, trong khi phần khác biệt chưa staged vẫn còn.

### Bỏ staging một phần thay đổi

Nếu chỉ muốn bỏ staging một số hunk thay vì toàn bộ file, dùng chế độ tương tác:

```bash
git reset -p -- src/config.yml
```

Git lần lượt hiển thị các hunk đang staged để bạn chọn phần muốn đưa khỏi index. Nội dung trong working tree vẫn được giữ. Đây là lựa chọn hữu ích khi một file chứa cả thay đổi đã hoàn tất và thay đổi còn đang làm dở.

Một cách diễn đạt tương đương, dễ hiểu hơn trong nhiều tình huống, là:

```bash
git restore --staged --source=HEAD -- src/config.yml
```

Lệnh `restore --staged` cũng khôi phục index từ `HEAD` và không sửa working tree. `git reset <tree-ish> -- <pathspec>` là cú pháp cũ, vẫn được hỗ trợ rộng rãi.

## 3. Reset theo đường dẫn không di chuyển branch

Điểm quan trọng nhất là vị trí của `--` và pathspec:

```bash
git reset HEAD~1 -- src/config.yml
```

Trong lệnh này:

- `HEAD~1` là nguồn tree để lấy phiên bản file.
- `--` kết thúc phần tùy chọn và phân tách revision với đường dẫn.
- `src/config.yml` là file được cập nhật trong index.

Branch vẫn trỏ đến commit hiện tại. Để tự xác minh, chạy:

```bash
git rev-parse HEAD
git status
git diff --cached -- src/config.yml
git diff -- src/config.yml
```

Nếu mục tiêu là bỏ staging một file theo phiên bản hiện tại của `HEAD`, hãy dùng `git reset -- <file>`. Nếu mục tiêu là di chuyển cả nhánh về commit trước, không thêm pathspec:

```bash
git reset --mixed HEAD~1
```

Hai lệnh có phạm vi ảnh hưởng hoàn toàn khác nhau. Đừng bỏ `--` khi tên file có thể bị Git hiểu nhầm là tên revision hoặc tùy chọn.

## 4. Các chế độ reset con trỏ nhánh

Khi reset một commit mà không có pathspec, chế độ quyết định Git xử lý index và working tree như thế nào.

| Chế độ | `HEAD`/branch | Index | Working tree |
|---|---|---|---|
| `--soft` | Di chuyển đến commit đích | Giữ nguyên | Giữ nguyên |
| `--mixed` (mặc định) | Di chuyển đến commit đích | Đặt lại theo commit đích | Giữ nguyên |
| `--hard` | Di chuyển đến commit đích | Đặt lại theo commit đích | Đặt lại theo commit đích |
| `--merge` | Di chuyển đến commit đích nếu an toàn | Đặt lại theo commit đích | Cập nhật có điều kiện, giữ các thay đổi chưa staged khi có thể |
| `--keep` | Di chuyển đến commit đích nếu an toàn | Đặt lại theo commit đích | Giữ thay đổi local; hủy nếu cập nhật sẽ ghi đè thay đổi |

Ví dụ với commit mới nhất:

```bash
git reset --soft HEAD~1
```

Commit cuối cùng bị bỏ khỏi đầu branch, nhưng thay đổi của commit đó vẫn nằm trong index. Bạn có thể chỉnh sửa lại hoặc tạo commit mới.

```bash
git reset --mixed HEAD~1
```

Commit cuối cùng bị bỏ khỏi đầu branch; index trở về commit cha, còn thay đổi vẫn nằm trong working tree ở trạng thái chưa staged. Đây là chế độ mặc định nếu bạn không chỉ định chế độ.

```bash
git reset --hard HEAD~1
```

Branch, index và working tree đều được đưa về commit cha. Thay đổi tracked chưa commit trong index và working tree bị loại bỏ. Các file hoặc thư mục untracked nằm chắn đường ghi các file tracked có thể bị xóa để Git ghi phiên bản đích; lệnh này không phải cách dọn mọi file untracked trong repository.

`--merge` và `--keep` là các chế độ có điều kiện, thường dùng trong những tình huống cần reset nhưng vẫn bảo vệ một số thay đổi local. Nếu Git phát hiện việc cập nhật sẽ ghi đè thay đổi không an toàn, lệnh có thể dừng. Hãy đọc thông báo và kiểm tra `git status`; không xem hai chế độ này là bảo đảm giữ được mọi chỉnh sửa trong mọi trạng thái.

## 5. Chọn đúng thao tác theo mục tiêu

| Mục tiêu | Lệnh thường dùng | Ảnh hưởng chính |
|---|---|---|
| Bỏ staging một file, giữ chỉnh sửa | `git reset -- file` | Chỉ cập nhật index |
| Bỏ staging một số hunk | `git reset -p -- file` | Chọn hunk để cập nhật index |
| Đưa index của file về phiên bản commit khác | `git reset <commit> -- file` | Chỉ cập nhật index theo tree chỉ định |
| Bỏ commit cuối nhưng giữ thay đổi staged | `git reset --soft HEAD~1` | Di chuyển branch, giữ index và working tree |
| Bỏ commit cuối, giữ thay đổi chưa staged | `git reset --mixed HEAD~1` | Di chuyển branch và đặt lại index |
| Bỏ commit cuối cùng cùng thay đổi tracked local | `git reset --hard HEAD~1` | Di chuyển branch, index và working tree |

### Ví dụ: stage nhầm file cấu hình

Bạn chỉnh `src/config.yml`, chạy `git add`, sau đó phát hiện file còn chứa thông tin thử nghiệm không nên đưa vào commit. Bạn muốn bỏ staging để chỉnh tiếp:

```bash
git status
git reset -- src/config.yml
git diff -- src/config.yml
```

Sau đó sửa nội dung và stage lại:

```bash
git add src/config.yml
git diff --cached -- src/config.yml
```

### Ví dụ: muốn viết lại commit cuối

Bạn vừa tạo commit nhưng nhận ra cần bổ sung một file và muốn chỉnh lại commit đó trước khi chia sẻ:

```bash
git reset --soft HEAD~1
git status
git add src/missing-file.java
git commit -c ORIG_HEAD
```

Sau `--soft`, thay đổi của commit vừa bỏ vẫn staged. `ORIG_HEAD` thường lưu vị trí `HEAD` trước lần reset để bạn có thể dùng lại thông tin commit trước; kiểm tra giá trị này nếu repository vừa thực hiện nhiều thao tác khác có thể cập nhật nó. Bạn cũng có thể dùng `git commit --amend` khi commit cũ vẫn còn là `HEAD`, nhưng trong ví dụ này `HEAD` đã được lùi lại nên tạo commit mới bằng `-c ORIG_HEAD` là cách thể hiện rõ ý định dùng lại thông điệp cũ.

## 6. Giới hạn với nhánh đã chia sẻ và cách hoàn tác an toàn

Reset con trỏ branch làm thay đổi lịch sử mà branch công bố. Nếu commit đã được push và đồng đội đã dựa trên nó, reset rồi force push có thể khiến lịch sử ở các clone phân kỳ và làm mất công việc mà người khác đã đẩy lên.

Với commit đã chia sẻ, thường nên dùng `git revert` để tạo commit mới đảo ngược thay đổi:

```bash
git revert <commit-can-hoan-tac>
```

`revert` giữ nguyên các commit cũ và ghi thêm một commit mới. Với merge commit, cần xác định mainline parent bằng tùy chọn `-m` theo lịch sử thực tế; không chọn parent theo phỏng đoán.

Nếu reset nhầm trên branch local, reflog thường giúp tìm lại vị trí cũ:

```bash
git reflog --date=local
```

Tìm entry trước lần reset, rồi tạo một branch cứu hộ tại mã commit phù hợp:

```bash
git branch rescue-before-reset <commit-id>
```

Tạo branch cứu hộ giúp giữ commit đó có thể truy cập được trong lúc bạn kiểm tra. Chỉ sau khi xác nhận đúng commit và hiểu trạng thái working tree mới quyết định di chuyển branch hiện tại. Reflog là nhật ký local và các entry có thể hết hạn theo cấu hình dọn dẹp; đừng xem nó là bản sao lưu dài hạn.

## 7. Bài tập thực hành

Tạo một repository thử nghiệm và tạo commit có hai file `README.md` và `src/config.yml`. Sau đó chỉnh sửa cả hai file và stage chúng.

1. Chạy `git status` và `git diff --cached` để xem thay đổi đã staged.
2. Sửa tiếp `src/config.yml` sau khi stage để file có cả thay đổi staged và chưa staged.
3. Chạy `git reset -- src/config.yml`, rồi so sánh `git diff --cached` và `git diff` để xác nhận working tree còn nguyên.
4. Chạy `git reset -p -- README.md` trong repository thử nghiệm để bỏ staging một hunk.
5. Tạo thêm một commit local, rồi thử `git reset --soft HEAD~1` và `git reset --mixed HEAD~1` trên các nhánh thử nghiệm riêng để so sánh index và working tree.
6. Quan sát reflog sau reset và tạo một branch cứu hộ từ commit trước đó.

Bạn hoàn thành bài tập khi giải thích được vì sao reset có pathspec chỉ tác động đến index, còn reset theo commit có thể di chuyển branch và thay đổi thêm index/working tree tùy chế độ.

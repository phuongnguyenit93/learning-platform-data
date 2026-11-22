# Khôi phục một tệp hoặc thư mục từ phiên bản trước

Khi một tệp bị sửa sai, xóa nhầm hoặc cần lấy lại nội dung từ một commit cũ, bạn không nhất thiết phải quay lui toàn bộ nhánh. `git restore` cho phép chọn đúng tệp hoặc thư mục và lấy nội dung từ `HEAD`, index hoặc một commit cụ thể. Điều quan trọng là xác định đúng nguồn và phạm vi trước khi chạy lệnh, vì khôi phục có thể ghi đè thay đổi đang có trong working tree hoặc index.

## 1. Hiểu ba nơi Git có thể lấy nội dung

Một tệp trong repository có thể có nội dung khác nhau ở ba nơi:

- **HEAD**: commit hiện tại mà nhánh đang trỏ tới.
- **Index (staging area)**: phiên bản đã được stage, sẽ được đưa vào commit tiếp theo.
- **Working tree**: tệp đang có trên ổ đĩa mà bạn mở và chỉnh sửa.

`git restore` có thể lấy nội dung từ một trong các nguồn này để cập nhật tệp hoặc index. Nếu không chỉ rõ nguồn, Git dùng mặc định phụ thuộc vào đích khôi phục:

| Lệnh | Nguồn mặc định | Nơi được cập nhật |
|---|---|---|
| `git restore --worktree -- file` | Index | Working tree |
| `git restore --staged -- file` | `HEAD` | Index |
| `git restore --source=<commit> --worktree -- file` | Commit chỉ định | Working tree |
| `git restore --source=<commit> --staged --worktree -- file` | Commit chỉ định | Index và working tree |

Nếu không ghi `--staged` hoặc `--worktree`, mặc định Git chỉ khôi phục working tree. Hãy chỉ định rõ các cờ khi thao tác trên tệp quan trọng để tránh nhầm lẫn.

## 2. Kiểm tra trạng thái trước khi khôi phục

Trước khi chạy lệnh, hãy xem nhánh hiện tại và những thay đổi đang tồn tại:

```bash
git status --short
git diff -- path/to/file
git diff --cached -- path/to/file
```

- `git status --short` cho biết tệp nào đang sửa, đã stage, bị xóa hoặc chưa được theo dõi.
- `git diff -- path/to/file` hiển thị thay đổi trong working tree so với index.
- `git diff --cached -- path/to/file` hiển thị thay đổi đã stage so với `HEAD`.

Nếu nội dung hiện tại có giá trị, hãy commit, stash hoặc sao lưu ra vị trí an toàn trước khi khôi phục. `git restore` không tự lưu một bản dự phòng của nội dung mà nó ghi đè. Đặc biệt, các chỉnh sửa chưa commit không phải lúc nào cũng có thể tìm lại bằng reflog.

## 3. Khôi phục tệp về phiên bản trong HEAD

Nếu bạn đã sửa một tệp tracked trong working tree nhưng chưa stage và muốn bỏ phần sửa đó, có thể dùng:

```bash
git restore --worktree -- src/main/ReportService.java
```

Git lấy nội dung từ index và ghi vào working tree. Trong trường hợp index không có thay đổi staged, nội dung đó thường giống `HEAD`.

Nếu muốn khôi phục index về `HEAD` để bỏ trạng thái staged của tệp:

```bash
git restore --staged -- src/main/ReportService.java
```

Lệnh này đưa phiên bản trong index về `HEAD`, nhưng giữ nguyên nội dung working tree. Nếu tệp đã được sửa trước đó, thay đổi có thể xuất hiện lại dưới dạng chưa staged.

Nếu muốn cả index và working tree đều trở về nội dung trong `HEAD`:

```bash
git restore --source=HEAD --staged --worktree -- src/main/ReportService.java
```

Lệnh cuối có thể loại bỏ cả thay đổi staged lẫn unstaged của tệp. Chỉ chạy sau khi đã xác nhận rằng bạn thực sự muốn bỏ toàn bộ thay đổi hiện tại của đường dẫn đó.

## 4. Khôi phục tệp từ một commit cũ

Khi cần lấy phiên bản ở một commit cụ thể, dùng `--source` để chọn nguồn:

```bash
git restore --source=<commit> --worktree -- src/main/ReportService.java
```

Thay `<commit>` bằng hash, tag hoặc biểu thức commit đã xác minh, chẳng hạn `a1b2c3d` hoặc `HEAD~2`. Lệnh đưa nội dung tệp ở commit đó vào working tree hiện tại. Theo mặc định, index không bị cập nhật; nếu muốn stage phiên bản cũ ngay, hãy thêm `--staged`.

Ví dụ khôi phục phiên bản của tệp từ hai commit trước:

```bash
git restore --source=HEAD~2 --worktree -- src/main/ReportService.java
```

Sau lệnh này, tệp trong working tree có nội dung từ `HEAD~2`, còn nhánh hiện tại vẫn trỏ tới commit cũ nhất hiện tại. Không có commit mới nào được tạo tự động.

Nếu muốn biến phiên bản cũ thành thay đổi đã stage để chuẩn bị commit:

```bash
git restore --source=HEAD~2 --staged --worktree -- src/main/ReportService.java
git diff --cached -- src/main/ReportService.java
```

Sau khi kiểm tra diff và chạy test, bạn có thể tạo commit mới để ghi nhận việc đưa tệp về phiên bản trước. Cách này giữ nguyên lịch sử hiện tại và thể hiện việc khôi phục như một thay đổi mới.

## 5. Tìm commit chứa phiên bản cần lấy

Nếu chưa biết hash commit, hãy xem lịch sử của tệp:

```bash
git log --oneline -- src/main/ReportService.java
```

Nếu tệp từng được đổi tên và bạn muốn theo dõi lịch sử qua lần đổi tên, dùng:

```bash
git log --oneline --follow -- src/main/ReportService.java
```

`--follow` hữu ích cho một đường dẫn tệp đơn lẻ khi Git nhận diện được thao tác rename. Nếu commit cần tìm không nằm trong lịch sử nhánh hiện tại, có thể mở rộng phạm vi tìm kiếm:

```bash
git log --oneline --all --follow -- src/main/ReportService.java
```

Sau khi chọn commit, xem nội dung tệp ở commit đó trước khi ghi đè phiên bản hiện tại:

```bash
git show <commit>:src/main/ReportService.java
```

Lệnh này chỉ hiển thị nội dung trong terminal, không thay đổi working tree hoặc index. Nếu tệp không tồn tại ở commit đã chọn, Git sẽ báo không tìm thấy đường dẫn trong tree của commit đó.

## 6. Khôi phục cả một thư mục

`git restore` cũng nhận pathspec là thư mục. Ví dụ lấy các tệp được quản lý dưới `src/main/report/` từ commit cũ:

```bash
git restore --source=<commit> --worktree -- src/main/report/
```

Thêm `--staged` nếu bạn muốn index cũng phản ánh phiên bản từ commit nguồn:

```bash
git restore --source=<commit> --staged --worktree -- src/main/report/
```

Đường dẫn thư mục kết thúc bằng dấu `/` giúp thể hiện rõ phạm vi. Có thể dùng pathspec cụ thể hơn nếu chỉ muốn khôi phục một phần thư mục. Ví dụ:

```bash
git restore --source=<commit> --worktree -- 'src/main/report/*.java'
```

Pathspec được Git diễn giải theo quy tắc pathspec của Git, không phải lúc nào cũng giống wildcard của shell. Dùng dấu nháy khi cần tránh shell mở rộng ký tự trước khi Git nhận được đối số.

Khôi phục thư mục có thể ảnh hưởng nhiều tệp cùng lúc. Trước khi thực hiện, hãy xem danh sách file và diff ở commit nguồn. Không dùng pathspec quá rộng như `.` nếu mục tiêu chỉ là sửa một vài tệp.

## 7. Khôi phục tệp đã bị xóa

Nếu tệp tracked bị xóa khỏi working tree nhưng việc xóa chưa được stage, có thể khôi phục từ index:

```bash
git restore --worktree -- src/main/ReportService.java
```

Nếu việc xóa đã được stage, index cũng không còn phiên bản tệp. Khi đó, chỉ khôi phục working tree từ index sẽ không lấy lại được nội dung. Hãy lấy cả index và working tree từ `HEAD`:

```bash
git restore --source=HEAD --staged --worktree -- src/main/ReportService.java
```

Nếu muốn lấy tệp từ một commit cũ khác:

```bash
git restore --source=<commit> --staged --worktree -- src/main/ReportService.java
```

Nếu tệp đã bị xóa trong commit hiện tại nhưng tồn tại ở commit cũ, hãy xác minh đường dẫn trong commit nguồn bằng `git show <commit>:<path>` trước khi restore.

## 8. Khôi phục tệp đã đổi tên hoặc di chuyển

Git lưu snapshot của cây thư mục ở mỗi commit; thông tin rename thường được suy ra khi so sánh các snapshot. Vì vậy, một tệp được đổi tên có thể xuất hiện dưới đường dẫn cũ ở commit trước và đường dẫn mới ở commit hiện tại.

Để tìm lịch sử qua lần đổi tên:

```bash
git log --follow --oneline -- path/to/new-name.java
```

Sau khi tìm được commit còn chứa đường dẫn cũ, xem nội dung bằng đường dẫn tại commit đó:

```bash
git show <commit>:path/to/old-name.java
```

Nếu muốn lấy nội dung đó vào đường dẫn hiện tại, dùng `git restore` với pathspec tương ứng trong commit nguồn. Khi đường dẫn cũ và mới khác nhau, hãy xác định rõ bạn muốn khôi phục file dưới tên nào. Có thể lấy nội dung ra để xem trước bằng `git show`, sau đó tạo file mới hoặc điều chỉnh đường dẫn có chủ đích.

Không giả định Git tự hiểu ý định đổi tên khi bạn chỉ định một đường dẫn không tồn tại trong commit nguồn. Xác minh tên file ở từng thời điểm trước khi restore.

## 9. Khôi phục có tạo commit mới không?

`git restore` chỉ cập nhật index và/hoặc working tree; nó không tự tạo commit. Sau khi khôi phục một phiên bản cũ, bạn có thể xem thay đổi:

```bash
git status --short
git diff
git diff --cached
```

Nếu cần ghi nhận việc khôi phục vào lịch sử, stage đúng tệp rồi tạo commit:

```bash
git add src/main/ReportService.java
git diff --cached
git commit -m "Restore report service implementation"
```

Commit mới sẽ ghi nhận nội dung được khôi phục trên nền lịch sử hiện tại. Đây thường là cách phù hợp khi thay đổi đã được chia sẻ và bạn muốn mọi người nhận được việc khôi phục qua pull hoặc fetch.

Nếu chỉ đang thử nghiệm local và chưa muốn commit, bạn có thể giữ thay đổi trong working tree hoặc index. Hãy lưu ý rằng chúng vẫn có thể bị ghi đè bởi thao tác khác sau đó.

## 10. So sánh `git restore` với cú pháp checkout cũ

Trước khi có `git restore`, nhiều hướng dẫn dùng:

```bash
git checkout <commit> -- path/to/file
```

Cú pháp này vẫn có thể gặp trong repository hoặc tài liệu cũ. Nó thường cập nhật cả index và working tree của đường dẫn từ commit được chỉ định. `git restore` tách rõ nơi cần cập nhật bằng `--staged` và `--worktree`, nên dễ đọc và ít nhầm với thao tác chuyển nhánh hơn.

| Nhu cầu | Cách dùng rõ ràng với `git restore` |
|---|---|
| Bỏ sửa unstaged, lấy từ index | `git restore --worktree -- file` |
| Bỏ stage, giữ sửa trong working tree | `git restore --staged -- file` |
| Lấy phiên bản commit cũ vào working tree | `git restore --source=<commit> --worktree -- file` |
| Lấy phiên bản commit cũ vào cả index và working tree | `git restore --source=<commit> --staged --worktree -- file` |

Không nhầm `git restore` với `git switch` hoặc `git checkout <branch>`. Các lệnh switch/checkout thay đổi nhánh hoặc vị trí HEAD; restore thay nội dung của đường dẫn được chọn.

## 11. Những gì Git không thể khôi phục bằng restore

`git restore` chỉ lấy được nội dung đã có trong nguồn Git mà bạn chỉ định. Nó không thể tự khôi phục:

- Tệp mới chưa từng được commit hoặc lưu trong stash.
- Nội dung chỉnh sửa chưa commit đã bị ghi đè và không còn trong index, stash hay bản sao nào khác.
- Tệp bị xóa trước khi Git từng theo dõi nó.
- Dữ liệu runtime hoặc dữ liệu bên ngoài repository, như database, file upload hay tài nguyên cloud.

Tệp untracked không có phiên bản trong commit để Git restore. Nếu tệp mới bị xóa nhầm, hãy kiểm tra backup, IDE local history hoặc công cụ khôi phục file của hệ điều hành. Nếu tệp từng được stash, hãy tìm stash phù hợp và khôi phục từ đó.

Reflog ghi lại sự di chuyển của các ref như `HEAD` và branch; nó không phải nhật ký mọi lần chỉnh sửa file. Nếu nội dung chưa commit đã bị ghi đè, reflog thường không thể khôi phục nội dung đó.

## 12. Quy trình an toàn trước khi restore

Trước một thao tác khôi phục, thực hiện lần lượt:

1. **Xác định đúng đường dẫn.** Kiểm tra tên file, thư mục và trạng thái tracked/untracked.
2. **Chọn nguồn chính xác.** Xác định muốn lấy từ index, `HEAD`, tag hay commit cụ thể.
3. **Xem nội dung nguồn.** Dùng `git show <commit>:<path>` để đọc trước khi ghi đè.
4. **Bảo toàn thay đổi hiện tại.** Commit, stash hoặc sao lưu những nội dung chưa muốn mất.
5. **Chọn đích khôi phục.** Dùng `--worktree`, `--staged` hoặc cả hai theo mục tiêu.
6. **Giới hạn pathspec.** Chỉ khôi phục đúng file hoặc thư mục cần thiết.
7. **Kiểm tra sau thao tác.** Dùng `git status`, `git diff`, `git diff --cached` và test liên quan.
8. **Commit nếu cần chia sẻ.** Tạo commit mới để mọi người nhận được thay đổi khôi phục theo lịch sử bình thường.

Ví dụ hoàn chỉnh: lấy phiên bản cũ của một file, xem lại và tạo commit khôi phục:

```bash
git status --short
git log --oneline --follow -- src/main/ReportService.java
git show <commit>:src/main/ReportService.java
git restore --source=<commit> --worktree -- src/main/ReportService.java
git diff -- src/main/ReportService.java
git add src/main/ReportService.java
git diff --cached -- src/main/ReportService.java
git commit -m "Restore report service from previous version"
```

Thay `<commit>` bằng commit đã xác minh. Nếu muốn index cũng được cập nhật ngay từ nguồn đó, thêm `--staged` vào lệnh restore và vẫn kiểm tra diff staged trước khi commit.

## 13. Ghi nhớ

`git restore` giúp lấy lại một tệp hoặc thư mục mà không cần quay lui toàn bộ nhánh. Hãy phân biệt nguồn `HEAD`, index và commit cũ; chọn rõ cập nhật working tree, index hay cả hai; giới hạn đúng pathspec và xem trước nội dung nguồn. Lệnh không tự tạo commit và không thể khôi phục dữ liệu chưa từng được Git lưu. Với thay đổi đã chia sẻ, hãy commit kết quả khôi phục như một thay đổi mới để giữ lịch sử cộng tác nhất quán.

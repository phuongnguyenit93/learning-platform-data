# Ý nghĩa ours và theirs trong merge, rebase và cherry-pick

Khi Git không thể tự kết hợp hai thay đổi, nó đánh dấu các file xung đột và giữ những phiên bản cần thiết trong index để người dùng quyết định kết quả cuối cùng. Hai nhãn **ours** và **theirs** giúp phân biệt các phía của thao tác đang chạy. Chúng rất hữu ích khi đọc conflict marker, xem từng phiên bản hoặc chọn nhanh một phía bằng lệnh Git.

Điểm cần nhớ là **ours luôn là stage 2 và theirs luôn là stage 3 trong index của một xung đột**, nhưng tên nhánh tương ứng phụ thuộc vào thao tác. Với merge và cherry-pick, cách hiểu thường trực quan: ours là phía hiện tại, theirs là thay đổi được đưa vào. Với rebase, cách hiểu này dễ gây nhầm vì Git đang phát lại từng commit lên một nền mới.

## 1. Ours và theirs trong một conflict

Giả sử cùng một dòng trong file được hai phía sửa khác nhau. Git có thể để lại đoạn đánh dấu như sau:

```text
<<<<<<< HEAD
const timeout = 30;
=======
const timeout = 60;
>>>>>>> feature/timeout
```

Đoạn này có ba phần:

- Phần sau `<<<<<<<` là nội dung của phía **ours**.
- Phần giữa `=======` và `>>>>>>>` là nội dung của phía **theirs**.
- Các dấu phân cách do Git thêm vào để bạn chỉnh sửa và tạo ra một kết quả hợp nhất.

Tên hiển thị sau dấu `<<<<<<<` hoặc `>>>>>>>` là nhãn Git dùng cho thao tác hiện tại. Không nên chỉ nhìn tên nhánh trong marker rồi kết luận đâu là nhánh gốc của công việc; hãy kiểm tra `git status` để biết Git đang merge, rebase hay cherry-pick.

Trong index, Git lưu tối đa ba phiên bản chưa hợp nhất của một đường dẫn:

| Stage | Ý nghĩa | Vai trò |
|---|---|---|
| 1 | Base | Phiên bản cơ sở chung mà Git dùng để so sánh |
| 2 | Ours | Phiên bản của phía hiện tại trong thao tác |
| 3 | Theirs | Phiên bản của phía được đưa vào thao tác |

Khi file còn xung đột, Git chưa tạo stage 0 (phiên bản đã giải quyết) cho file đó. Sau khi bạn chỉnh sửa và chạy `git add`, nội dung hiện tại được ghi thành stage 0; các stage xung đột được loại bỏ.

Không phải conflict nào cũng có đủ cả ba stage. Ví dụ, xung đột add/add có thể không có stage 1 vì file chưa tồn tại ở base. Xung đột modify/delete có thể thiếu stage của phía đã xóa file. Vì vậy, nếu một lệnh `git show :1:...`, `:2:...` hoặc `:3:...` báo không tìm thấy object, hãy kiểm tra loại conflict thay vì cho rằng repository bị hỏng.

## 2. So sánh cách hiểu theo từng thao tác

| Thao tác | Ours (stage 2) | Theirs (stage 3) | Lệnh tiếp tục |
|---|---|---|---|
| Merge | Nhánh đang được checkout trước khi merge | Nhánh được merge vào | `git merge --continue` |
| Rebase | Nền mới: upstream và các commit đã được phát lại | Commit của nhánh đang được phát lại ở bước hiện tại | `git rebase --continue` |
| Cherry-pick | Nhánh hiện tại nhận commit | Commit đang được cherry-pick | `git cherry-pick --continue` |

### Merge: ours là nhánh hiện tại

Ví dụ bạn đang ở nhánh `main` và chạy:

```bash
git switch main
git merge feature
```

Nếu xảy ra conflict:

- **Ours** là nội dung từ `main`, tức nhánh đang được checkout.
- **Theirs** là nội dung từ `feature`, tức nhánh đang được merge vào.

Trong trường hợp này, `<<<<<<< HEAD` thường đại diện cho phía `main`; phần cuối thường mang nhãn của nhánh `feature`. Đây là cách hiểu phổ biến nhất khi làm merge.

### Rebase: ours là nền mới, theirs là commit đang phát lại

Rebase là trường hợp dễ nhầm nhất. Xét lệnh:

```bash
git switch feature
git rebase main
```

Git lấy các commit riêng của `feature`, chuyển điểm xuất phát của nhánh sang `main`, rồi lần lượt phát lại từng commit lên nền mới. Khi một commit đang được phát lại gây conflict:

- **Ours** là `HEAD` tại thời điểm đó: nền mới bắt đầu từ `main`, cộng với các commit đã được phát lại thành công trước đó.
- **Theirs** là commit của `feature` mà Git đang cố phát lại ở bước hiện tại.

Do đó, trong rebase, `git restore --ours -- path/to/file` giữ phiên bản từ nền mới; `git restore --theirs -- path/to/file` giữ phiên bản từ commit `feature` đang được áp dụng. Điều này có thể ngược với trực giác “ours là code của nhánh tôi đang làm”.

Nếu rebase có nhiều commit, Git có thể dừng ở nhiều conflict khác nhau. Theirs ở mỗi lần dừng là commit đang được áp dụng ở lần đó, không nhất thiết là toàn bộ trạng thái cuối cùng của nhánh `feature`. Dùng `git show REBASE_HEAD` hoặc `git rebase --show-current-patch` để xem commit/patch hiện tại.

### Cherry-pick: ours là nhánh nhận commit

Ví dụ bạn đang ở `release` và muốn lấy một commit cụ thể từ nhánh khác:

```bash
git switch release
git cherry-pick abc123
```

Nếu xảy ra conflict:

- **Ours** là nội dung hiện có trên `release`.
- **Theirs** là thay đổi của commit `abc123` đang được áp dụng.

Bạn có thể dùng `git show CHERRY_PICK_HEAD` để xem commit đang được cherry-pick. Nếu cherry-pick một dãy commit, Git xử lý từng commit; conflict hiện tại gắn với commit đang được áp dụng.

## 3. Kiểm tra hai phía trước khi quyết định

Đừng chọn ours hoặc theirs chỉ vì tên gọi. Trước tiên, xác định thao tác và xem Git đang xung đột ở đâu:

```bash
git status
git diff --name-only --diff-filter=U
```

Với một file cụ thể, xem phần khác biệt tổng hợp:

```bash
git diff --cc -- path/to/file
git diff --base -- path/to/file
git diff --ours -- path/to/file
git diff --theirs -- path/to/file
```

Bạn cũng có thể đọc trực tiếp các phiên bản Git lưu trong index:

```bash
git ls-files -u -- path/to/file

git show :1:path/to/file
git show :2:path/to/file
git show :3:path/to/file
```

Các lệnh `:1:`, `:2:`, `:3:` lần lượt đọc base, ours và theirs. Chúng đặc biệt hữu ích khi conflict marker khó đọc, file đã bị chỉnh sửa một phần hoặc cần so sánh nguyên vẹn hai phía. Với tên file có khoảng trắng, hãy đặt đường dẫn trong dấu nháy phù hợp với shell đang dùng.

Để xác định nguồn thay đổi theo thao tác, có thể xem thêm:

```bash
# Khi merge
git show MERGE_HEAD

# Khi rebase
git show REBASE_HEAD
git rebase --show-current-patch

# Khi cherry-pick
git show CHERRY_PICK_HEAD
```

Chỉ chạy lệnh tương ứng với thao tác đang diễn ra; pseudo-ref đó có thể không tồn tại ở các thao tác khác.

## 4. Chọn một phía hoặc tự kết hợp nội dung

Nếu đã xác định chắc chắn muốn dùng toàn bộ file từ một phía, có thể yêu cầu Git khôi phục phiên bản đó vào working tree:

```bash
# Lấy toàn bộ file từ ours (stage 2)
git restore --ours -- path/to/file

# Hoặc lấy toàn bộ file từ theirs (stage 3)
git restore --theirs -- path/to/file
```

Lệnh cũ tương đương thường gặp là `git checkout --ours -- path/to/file` và `git checkout --theirs -- path/to/file`. `git restore` diễn đạt rõ hơn mục đích khôi phục file.

Các lệnh trên thay thế toàn bộ nội dung file bằng phiên bản của một phía. Chúng không chọn riêng từng dòng hoặc từng hunk. Nếu cả hai phía đều có thay đổi cần giữ, hãy mở file, xóa các conflict marker và biên tập thành kết quả mong muốn. Có thể dùng công cụ so sánh/merge trực quan:

```bash
git mergetool
```

Với conflict ở cấp file, chẳng hạn một phía xóa file còn phía kia sửa file, hãy quyết định rõ kết quả cần giữ. Nếu kết quả là xóa file, dùng `git rm -- path/to/file`; nếu giữ file, tạo nội dung cuối cùng rồi dùng `git add -- path/to/file`.

Sau khi giải quyết, đánh dấu file đã xử lý:

```bash
git add -- path/to/file
```

Lệnh `git add` đưa nội dung working tree hiện tại vào index và báo cho Git rằng conflict của file đã được giải quyết. Nếu bạn chọn xóa file thì dùng `git rm`. Kiểm tra lại trước khi tiếp tục:

```bash
git status
git diff --cached
git diff --check
```

## 5. Quy trình xử lý conflict an toàn

Một quy trình có thể áp dụng cho cả ba thao tác:

1. **Xác định thao tác đang dừng.** Chạy `git status`; đọc thông báo “merging”, “rebasing” hoặc “cherry-picking”.
2. **Liệt kê file xung đột.** Dùng `git diff --name-only --diff-filter=U` để biết phạm vi cần xử lý.
3. **Xác định ý nghĩa ours/theirs trong thao tác đó.** Dùng bảng ở phần 2; riêng rebase phải nhớ theirs là commit đang được phát lại.
4. **Đọc base và hai phía.** Dùng conflict marker, `git diff` hoặc các stage trong index. Tìm hiểu mục đích của từng thay đổi trước khi kết hợp.
5. **Tạo nội dung cuối cùng.** Có thể chọn một phía cho toàn file hoặc kết hợp các phần cần thiết. Xóa toàn bộ marker còn sót lại.
6. **Đánh dấu file đã giải quyết.** Dùng `git add` hoặc `git rm`, sau đó xem lại staged diff.
7. **Tiếp tục đúng thao tác.** Dùng lệnh continue tương ứng và xử lý các conflict tiếp theo nếu Git dừng lại lần nữa.
8. **Kiểm tra kết quả.** Chạy test/build phù hợp, xem `git status` và kiểm tra commit cuối cùng.

Các lệnh tiếp tục và hủy thao tác thường dùng:

```bash
# Merge
git merge --continue
git merge --abort

# Rebase
git rebase --continue
git rebase --abort

# Cherry-pick
git cherry-pick --continue
git cherry-pick --abort
```

`--abort` hủy thao tác đang thực hiện và đưa repository về trạng thái trước khi thao tác bắt đầu trong phạm vi Git có thể khôi phục. Nếu working tree đã có thay đổi chưa commit trước đó, hãy thận trọng và bảo toàn chúng trước khi bắt đầu merge/rebase/cherry-pick; đừng dùng `git reset --hard` như một cách giải quyết conflict vì lệnh đó có thể làm mất thay đổi đang cần giữ.

## 6. Phân biệt `-X ours` với việc chọn nguyên file

Ngoài `git restore --ours` và `--theirs`, Git còn có tùy chọn chiến lược như `-X ours` hoặc `-X theirs`. Với merge, ví dụ:

```bash
git merge -X ours feature
```

`-X ours` yêu cầu chiến lược merge ưu tiên phía ours **ở những hunk đang xung đột**. Các thay đổi không xung đột từ phía còn lại vẫn có thể được đưa vào kết quả. Tương tự, `-X theirs` ưu tiên phía theirs ở các hunk xung đột.

Điều này khác với:

```bash
git merge -s ours feature
```

`-s ours` chọn chiến lược merge `ours`, tạo kết quả merge theo toàn bộ cây của nhánh hiện tại và bỏ qua nội dung của nhánh được merge vào. Đây là quyết định ở cấp chiến lược, có thể loại bỏ rất nhiều thay đổi. Không nên dùng chỉ vì muốn giải quyết nhanh một vài conflict. Khi dùng các tùy chọn này với rebase, hãy đặc biệt kiểm tra ý nghĩa ours/theirs theo ngữ cảnh rebase đã trình bày ở trên.

## 7. Những nhầm lẫn thường gặp

- **Cho rằng ours luôn là nhánh mình vừa checkout.** Điều này đúng với merge và cherry-pick thông thường, nhưng trong rebase, ours là nền mới mà commit đang được phát lại lên đó.
- **Cho rằng theirs luôn là nhánh đích hoặc nhánh nguồn.** Theirs là phiên bản của phía còn lại trong thao tác hiện tại; trong rebase, đó là commit đang được áp dụng.
- **Chọn toàn bộ một phía mà không xem phần còn lại.** `git restore --ours` và `--theirs` thay thế toàn file. Những thay đổi hợp lệ ở phía kia có thể bị mất khỏi kết quả.
- **Nghĩ rằng xóa marker là đã giải quyết conflict.** Git chỉ coi file đã được xử lý sau khi nội dung được đưa vào index bằng `git add` hoặc việc xóa được ghi nhận bằng `git rm`.
- **Nhầm `-X ours` với `-s ours`.** Một tùy chọn ưu tiên khi xử lý hunk xung đột; tùy chọn còn lại chọn chiến lược dùng toàn bộ cây của ours.
- **Tiếp tục sai thao tác.** Merge, rebase và cherry-pick có lệnh continue riêng. Hãy đọc `git status` trước khi chạy lệnh.

## Kết luận

Hãy ghi nhớ hai lớp ý nghĩa: trong index, ours là stage 2 và theirs là stage 3; còn stage 2 và stage 3 đại diện cho nhánh/commit nào thì phải xác định theo thao tác hiện tại. Merge và cherry-pick thường dùng cách hiểu trực quan “phía hiện tại” và “phía được đưa vào”. Rebase đảo trực giác đó: ours là nền mới, theirs là commit đang được phát lại. Khi chưa chắc chắn, kiểm tra `git status`, đọc các stage của file và xem commit đang được áp dụng trước khi chọn một phía.

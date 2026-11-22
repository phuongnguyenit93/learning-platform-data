# Đưa tệp vào chỉ mục bằng git add theo tệp, thư mục và toàn bộ kho

Sau khi chỉnh sửa dự án, Git chưa tự động đưa các thay đổi vào commit. Bạn cần chọn nội dung sẽ được ghi nhận bằng lệnh `git add`. Lệnh này cập nhật **index** (còn gọi là staging area), nơi lưu snapshot mà commit tiếp theo sẽ sử dụng. Bạn có thể stage một tệp, nhiều tệp, cả thư mục hoặc toàn bộ repository tùy phạm vi công việc.

Chọn đúng phạm vi stage giúp commit tập trung vào một mục đích rõ ràng. Ví dụ, bạn có thể commit riêng phần sửa lỗi trong `src/`, để tài liệu trong `docs/` tiếp tục ở trạng thái chưa stage. Nếu dùng `git add` cho toàn bộ kho mà chưa xem lại thay đổi, các tệp không liên quan cũng có thể bị đưa vào commit.

## 1. `git add` cập nhật index như thế nào?

Git có ba vùng trạng thái thường gặp:

- **Working tree:** các tệp hiện tại trên đĩa, nơi bạn chỉnh sửa mã nguồn.
- **Index / staging area:** snapshot nội dung và metadata sẽ được dùng cho commit tiếp theo.
- **Repository history:** các commit đã được tạo.

`git add` đọc nội dung hiện tại của đường dẫn trong working tree rồi cập nhật mục tương ứng trong index. Lệnh không tạo commit và không đẩy thay đổi lên remote.

```text
Working tree                Index                 Commit
-------------------         ----------------      ----------------
src/app.js đã sửa  --add--> snapshot mới   --commit--> lịch sử mới
docs/guide.md mới            chưa stage
```

Điểm quan trọng: `git add` stage nội dung tại thời điểm lệnh chạy. Nếu bạn sửa tiếp tệp sau khi đã stage, index vẫn giữ snapshot cũ; phần sửa mới xuất hiện như thay đổi chưa stage.

Ví dụ:

```bash
# Sửa src/app.js
git add src/app.js

# Tiếp tục sửa src/app.js sau khi đã stage
# Index vẫn chứa phiên bản tại thời điểm chạy git add lần đầu
git status
```

Trong trường hợp này, cùng một tệp có thể vừa có thay đổi staged vừa có thay đổi unstaged. Đây là hành vi bình thường và cho phép bạn chia một lần chỉnh sửa thành nhiều commit có mục đích riêng.

## 2. Stage một tệp cụ thể

Khi chỉ muốn đưa một tệp vào commit, truyền đường dẫn tệp cho `git add`:

```bash
git add src/app.js
```

Nếu đường dẫn có dấu cách hoặc ký tự đặc biệt, đặt trong dấu nháy:

```bash
git add -- "src/feature flag.js"
```

`--` đánh dấu kết thúc phần tùy chọn. Các nội dung phía sau được hiểu là pathspec, tránh trường hợp tên tệp bắt đầu bằng dấu `-` bị hiểu nhầm là option.

Stage nhiều tệp bằng cách truyền nhiều đường dẫn:

```bash
git add -- src/app.js src/auth/login.js docs/setup.md
```

Bạn có thể stage cả tệp mới, tệp đã sửa và việc xóa tệp nếu đường dẫn phù hợp. Git sẽ cập nhật các mục tương ứng trong index.

### Kiểm tra trước và sau khi stage

```bash
# Trước khi stage
git status --short

# Stage đúng tệp cần commit
git add -- src/app.js

# Xem trạng thái sau khi stage
git status --short

# Xem nội dung đã stage
git diff --cached -- src/app.js
```

`git diff --cached` (tương đương `git diff --staged`) hiển thị khác biệt giữa index và commit hiện tại. Đây là cách kiểm tra nội dung thực tế mà commit tiếp theo sẽ ghi nhận.

## 3. Stage toàn bộ tệp trong một thư mục

Để stage một thư mục và các nội dung bên trong, truyền đường dẫn thư mục:

```bash
git add src/
```

Lệnh này cập nhật các tệp phù hợp trong `src/`, bao gồm tệp mới và tệp đã sửa; những tệp tracked đã bị xóa trong phạm vi đó cũng được ghi nhận là đã xóa. Các thư mục con được duyệt đệ quy.

Bạn có thể stage nhiều thư mục cùng lúc:

```bash
git add -- src/ tests/ docs/
```

Đây là lựa chọn phù hợp khi một phần công việc nằm trong một khu vực rõ ràng, ví dụ sửa mã nguồn và test tương ứng nhưng chưa muốn stage tài liệu ở thư mục khác.

### Phạm vi thư mục phụ thuộc đường dẫn bạn truyền

Nếu bạn đang ở repository root, `git add src/` stage thay đổi dưới `src/`. Nếu đang ở thư mục con, đường dẫn tương đối được tính từ thư mục hiện tại:

```bash
# Đang ở repository root
git add src/

# Đang ở thư mục src/services
git add auth/
```

Lệnh thứ hai chỉ nhắm đến `src/services/auth/`. Nếu muốn đường dẫn bắt đầu từ repository root, có thể dùng pathspec magic `:/`:

```bash
# Từ bất kỳ thư mục con nào trong repository
git add -- ':(top)src/app.js'
```

Với người mới, cách đơn giản nhất là chuyển về repository root trước khi stage theo đường dẫn dự án, rồi kiểm tra lại `git status`.

## 4. Stage toàn bộ repository

Khi muốn đưa mọi thay đổi hiện có trong working tree vào index, dùng:

```bash
git add --all
```

Hoặc dạng ngắn:

```bash
git add -A
```

Không truyền pathspec, `git add -A` cập nhật toàn bộ working tree của repository, bất kể bạn đang đứng ở thư mục con nào. Lệnh này ghi nhận:

- Tệp mới chưa được theo dõi (untracked) và không bị ignore.
- Nội dung sửa đổi của tệp đã tracked.
- Tệp tracked đã bị xóa khỏi working tree.
- Những thay đổi đường dẫn như di chuyển hoặc đổi tên, được biểu diễn trong index dưới dạng xóa/thêm.

Ví dụ:

```bash
# Từ repository root hoặc thư mục con
git add --all

# Xem tất cả nội dung đã stage
git status
git diff --cached --stat
git diff --cached
```

`git add -A` không tự động thêm các tệp bị ignore. Nếu một tệp phù hợp với `.gitignore` hoặc quy tắc ignore khác, Git tiếp tục bỏ qua nó trừ khi bạn chủ động dùng `-f`.

### So sánh `git add .` và `git add -A`

Hai lệnh thường bị nhầm lẫn:

| Lệnh | Phạm vi |
|---|---|
| `git add .` | Stage thay đổi dưới thư mục hiện tại và các thư mục con |
| `git add -A` | Stage mọi thay đổi trong toàn bộ working tree khi không truyền pathspec |
| `git add -A -- src/` | Stage mọi thay đổi thuộc phạm vi `src/` |

Ví dụ, nếu bạn đang ở `src/services/`, `git add .` chỉ nhắm đến `src/services/` và nội dung bên dưới. `git add -A` không có pathspec vẫn cập nhật toàn bộ repository. Để tránh phụ thuộc vị trí terminal, hãy chuyển về root khi muốn stage toàn bộ dự án và dùng `git add --all`.

## 5. Stage thay đổi của các tệp đã được theo dõi bằng `-u`

Nếu chỉ muốn stage thay đổi của các tệp đã tracked, không thêm tệp mới, dùng `-u` (`--update`):

```bash
git add --update
```

Lệnh này cập nhật nội dung đã sửa và ghi nhận xóa đối với các tệp đã tracked. Nó không đưa tệp untracked mới vào index.

Có thể giới hạn phạm vi:

```bash
git add -u -- src/
```

So sánh các lựa chọn:

| Lệnh | Tệp tracked đã sửa | Tệp tracked đã xóa | Tệp mới untracked |
|---|---:|---:|---:|
| `git add <path>` | Có, nếu khớp pathspec | Có, nếu khớp pathspec | Có, nếu khớp pathspec và không bị ignore |
| `git add -u` | Có | Có | Không |
| `git add -A` | Có | Có | Có, nếu không bị ignore |
| `git add .` | Có trong phạm vi hiện tại | Có trong phạm vi hiện tại | Có trong phạm vi hiện tại, nếu không bị ignore |

`-u` hữu ích khi bạn muốn cập nhật các tệp đã quản lý mà chưa muốn thêm các file mới vào commit.

## 6. Stage tệp mới, sửa đổi và xóa tệp

### Tệp mới

Khi tạo một tệp mới, Git hiển thị nó là untracked. Đưa tệp vào index bằng:

```bash
git add README.md
```

Sau lệnh này, tệp trở thành staged và sẽ được lưu trong commit kế tiếp nếu bạn không bỏ stage nó.

### Tệp đã sửa

Khi sửa một tệp tracked, Git hiển thị thay đổi ở working tree. Stage phiên bản mới:

```bash
git add src/app.js
```

Nếu tiếp tục sửa sau đó, cần chạy `git add` lần nữa để cập nhật snapshot mới vào index.

### Tệp đã xóa

Nếu xóa tệp bằng hệ điều hành, có thể stage việc xóa bằng:

```bash
git add -- docs/old-guide.md
```

Hoặc dùng lệnh chuyên biệt:

```bash
git rm docs/old-guide.md
```

`git rm` vừa xóa tệp khỏi working tree vừa cập nhật index. Nếu muốn giữ bản sao trên máy nhưng bỏ tệp khỏi index, dùng `git rm --cached <path>`; đây là thao tác khác với việc stage một file đã bị xóa khỏi đĩa.

## 7. Đổi tên hoặc di chuyển tệp

Git không lưu một thao tác rename riêng như một object độc lập. Trong index, việc đổi tên thường được biểu diễn bằng xóa đường dẫn cũ và thêm đường dẫn mới. Khi hiển thị diff, Git có thể nhận diện rename dựa trên mức độ tương đồng nội dung.

Ví dụ, sau khi đổi tên `docs/start.md` thành `docs/quickstart.md`, stage cả hai phía:

```bash
git add -A -- docs/
git diff --cached --summary
git diff --cached --find-renames
```

Hoặc dùng:

```bash
git mv docs/start.md docs/quickstart.md
```

`git mv` thực hiện đổi tên trong working tree và cập nhật index. Nếu bạn dùng File Explorer hoặc `mv` để đổi tên, `git add -A` trong phạm vi phù hợp cũng có thể stage kết quả.

## 8. Stage tệp bị ignore một cách có chủ đích

`git add` thông thường bỏ qua đường dẫn bị quy tắc ignore khớp. Kiểm tra lý do một tệp bị ignore:

```bash
git check-ignore -v build/output.log
```

Nếu đã xác nhận tệp cần được đưa vào repository, có thể ép stage bằng `-f` (`--force`):

```bash
git add -f build/required-fixture.dat
```

Không dùng `-f` chỉ để làm biến mất thông báo ignore. Các tệp như secret, credential, log cá nhân hoặc sản phẩm build thường bị ignore có chủ đích; hãy xác minh nội dung và chính sách dự án trước khi force add.

## 9. Dùng pathspec để chọn chính xác phạm vi

Đối số đường dẫn của `git add` được Git xử lý như pathspec. Bạn có thể truyền đường dẫn cụ thể, thư mục hoặc mẫu chọn tệp. Dùng dấu nháy để bảo đảm shell chuyển nguyên mẫu cho Git:

```bash
# Stage một file
git add -- src/app.js

# Stage các file Markdown dưới docs
git add -- 'docs/*.md'

# Stage một thư mục từ repository root
git add -- ':(top)src/services/'
```

Pathspec magic `:(top)` neo đường dẫn vào repository root, kể cả khi lệnh được chạy từ thư mục con. Có nhiều chế độ pathspec khác, nhưng trong công việc hằng ngày, đường dẫn rõ ràng và dấu `--` thường đủ để tránh nhầm lẫn.

Nếu tên tệp bắt đầu bằng dấu gạch ngang, luôn đặt `--` trước pathspec:

```bash
git add -- -draft.md
```

## 10. Kiểm tra chính xác nội dung đã stage

Sau khi chạy `git add`, đừng chỉ dựa vào việc lệnh không báo lỗi. Hãy xem index đã chứa đúng nội dung chưa:

```bash
# Tóm tắt trạng thái
git status --short

# Danh sách tên tệp đã stage
git diff --cached --name-status

# Thống kê số dòng thay đổi đã stage
git diff --cached --stat

# Xem toàn bộ diff đã stage
git diff --cached

# Xem các thay đổi còn ở working tree
git diff
```

Trong `git status --short`, ký tự cột đầu thể hiện trạng thái staged; cột thứ hai thể hiện thay đổi chưa stage. Một dòng có cả hai ký tự có thể cho biết cùng một tệp đang có thay đổi ở index và working tree.

Ví dụ:

```text
M  src/app.js
 M docs/setup.md
A  tests/app.test.js
 D src/legacy.js
```

Ở đây `src/app.js` đã stage; `docs/setup.md` có thay đổi chưa stage; `tests/app.test.js` đã stage như tệp mới; `src/legacy.js` có thay đổi xóa chưa stage. Hãy đọc cả hai cột trước khi commit.

## 11. Ví dụ thực tế: stage một phần công việc

Giả sử bạn đang làm một thay đổi gồm:

```text
sample-app/
├── src/
│   ├── auth.js          <- sửa logic đăng nhập
│   └── profile.js       <- đang thử nghiệm dở
├── tests/
│   └── auth.test.js     <- thêm test cho đăng nhập
└── docs/
    └── notes.md        <- ghi chú cá nhân chưa hoàn tất
```

Bạn muốn commit logic đăng nhập và test tương ứng, giữ các phần còn lại cho công việc sau:

```bash
# Stage đúng hai tệp liên quan
git add -- src/auth.js tests/auth.test.js

# Xem những gì sắp được commit
git diff --cached --stat
git diff --cached

# Xác nhận phần còn lại chưa stage
git diff
git status
```

Sau khi kiểm tra, commit:

```bash
git commit -m "Add authentication validation"
```

`src/profile.js` và `docs/notes.md` vẫn còn trong working tree để bạn tiếp tục sau. Cách stage theo mục đích giúp commit dễ review, dễ revert và có lịch sử rõ ràng.

## 12. Một số lưu ý khi dùng `git add`

- `git add` không tạo commit; nó chỉ cập nhật index.
- `git add` không push dữ liệu lên remote.
- Stage một tệp không có nghĩa toàn bộ thay đổi tương lai của tệp đó tự động được stage.
- Tệp bị ignore không được thêm theo cách thông thường; `-f` có thể vượt qua ignore.
- `git add -A` không xóa file khỏi working tree; nó ghi nhận trạng thái thêm/sửa/xóa vào index.
- Nếu đang giải quyết merge conflict, `git add <path>` thường được dùng để đánh dấu đường dẫn đã được giải quyết và stage kết quả.
- Với submodule, `git add <submodule-path>` cập nhật gitlink theo commit mà submodule đang checkout; các tệp bên trong cần được commit ở repository con trước.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| `git add` tạo commit | Không. Nó cập nhật index; `git commit` mới tạo commit. |
| `git add file` stage mọi chỉnh sửa về sau của file | Không. Nó stage snapshot tại thời điểm chạy; sửa tiếp cần stage lại. |
| `git add .` và `git add -A` luôn có cùng phạm vi | Không. `.` giới hạn ở thư mục hiện tại; `-A` không có pathspec cập nhật toàn bộ working tree. |
| `git add -u` thêm cả tệp mới | Không. Nó chỉ cập nhật đường dẫn đã tracked, gồm sửa đổi và xóa. |
| `git add -A` tự thêm mọi tệp kể cả bị ignore | Không. Tệp bị ignore vẫn bị bỏ qua trừ khi dùng `git add -f`. |
| `git add -A` xóa tệp khỏi máy | Không. Nó chỉ ghi nhận việc xóa đã xảy ra vào index. |
| Git lưu thao tác rename thành một loại object riêng | Không. Rename được suy ra từ việc xóa đường dẫn cũ và thêm đường dẫn mới. |
| Chạy `git add .` từ thư mục con sẽ stage cả repository | Không. Nó giới hạn trong thư mục hiện tại và các thư mục con. |

## 14. Tự kiểm tra

1. **`git add` cập nhật vùng nào của Git?**
   - Index (staging area).
2. **Lệnh nào stage một tệp cụ thể?**
   - `git add -- <path>`.
3. **Lệnh nào stage các thay đổi trong toàn bộ working tree?**
   - `git add --all` hoặc `git add -A` khi không truyền pathspec.
4. **`git add -u` khác `git add -A` ở điểm nào?**
   - `-u` chỉ cập nhật tệp đã tracked; `-A` còn thêm tệp mới không bị ignore.
5. **Vì sao phải chạy `git add` lại sau khi sửa tệp đã stage?**
   - Vì index lưu snapshot tại thời điểm stage; chỉnh sửa mới chưa tự động được đưa vào index.
6. **Lệnh nào xem nội dung đã stage?**
   - `git diff --cached` hoặc `git diff --staged`.
7. **Muốn stage một tệp đang bị ignore sau khi xác minh, dùng gì?**
   - `git add -f -- <path>`.

## Kết luận

`git add` đưa snapshot của đường dẫn vào index để chuẩn bị cho commit. Dùng `git add <file>` để chọn từng tệp, `git add <directory>/` để stage một khu vực, và `git add --all` hoặc `git add -A` để cập nhật toàn bộ working tree. `git add -u` chỉ cập nhật tệp đã tracked; `git add .` giới hạn theo thư mục hiện tại. Sau mỗi lần stage, hãy kiểm tra `git status`, `git diff --cached` và `git diff` để chắc chắn commit chỉ chứa những thay đổi bạn dự định ghi nhận.

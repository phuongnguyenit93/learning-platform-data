# Bỏ nội dung khỏi chỉ mục bằng git restore --staged

Trong Git, `git add` đưa nội dung file vào **index** (staging area) để chuẩn bị cho commit tiếp theo. Nếu bạn stage nhầm file hoặc muốn rút một phần thay đổi ra khỏi commit sắp tạo, hãy dùng `git restore --staged`.

Lệnh này khôi phục mục trong index từ một nguồn được chọn, mặc định là `HEAD`. Nó chỉ thay đổi staging area; nội dung trong working tree vẫn được giữ nguyên. Vì vậy, sau khi bỏ staging, phần chỉnh sửa thường trở thành thay đổi chưa stage để bạn tiếp tục sửa hoặc chọn lại.

## 1. Cú pháp cơ bản

Cú pháp:

```bash
git restore --staged [--source=<tree>] [--] <pathspec>...
```

Trong đó:

- `--staged` yêu cầu Git cập nhật index.
- `--source=<tree>` chỉ định tree/commit dùng làm nguồn; nếu bỏ qua, Git dùng `HEAD`.
- `--` phân cách tùy chọn với đường dẫn, hữu ích khi tên file bắt đầu bằng dấu gạch ngang.
- `<pathspec>` là một hoặc nhiều đường dẫn cần bỏ staging.

Ví dụ bỏ staging một file:

```bash
git restore --staged src/config.yml
```

Ví dụ bỏ staging nhiều file:

```bash
git restore --staged README.md src/app.js tests/payment.test.js
```

Lệnh không xóa file khỏi working tree. Nó chỉ đưa trạng thái index của các đường dẫn đã chọn về giống phiên bản trong `HEAD`.

## 2. Hiểu index và working tree trước khi bỏ staging

Git theo dõi hai vùng riêng biệt sau commit hiện tại:

- **Index:** nội dung sẽ được đưa vào commit nếu bạn chạy `git commit` ngay lúc này.
- **Working tree:** nội dung file đang có trên đĩa, có thể chứa thay đổi mới hơn nội dung đã stage.

Giả sử `src/config.yml` ban đầu có nội dung A. Bạn sửa thành B rồi stage; sau đó sửa tiếp thành C:

```bash
# Thay đổi A thành B
git add src/config.yml

# Tiếp tục sửa B thành C sau khi đã stage B
git status
```

Lúc này index chứa B, working tree chứa C. Nếu chạy:

```bash
git restore --staged -- src/config.yml
```

index trở về A từ `HEAD`, còn working tree vẫn là C. Kết quả là thay đổi A → C còn trong working tree ở trạng thái chưa stage.

Mô hình trước và sau:

```text
Trước git restore --staged
HEAD:         A
Index:        B       (đã stage)
Working tree: C       (sửa tiếp sau khi stage)

Sau git restore --staged
HEAD:         A
Index:        A       (khớp HEAD)
Working tree: C       (được giữ nguyên)
```

Đây là điểm quan trọng nhất: `git restore --staged` không phải lệnh hoàn tác nội dung file đang sửa. Nó chỉ bỏ nội dung khỏi vùng chuẩn bị commit.

## 3. Kiểm tra kết quả bằng git status và git diff

Trước và sau khi bỏ staging, nên kiểm tra trạng thái:

```bash
git status --short
git diff --cached
git diff
```

- `git status --short` hiển thị trạng thái ngắn của file.
- `git diff --cached` so sánh index với `HEAD`, tức phần đã stage.
- `git diff` so sánh working tree với index, tức phần chưa stage.

Sau khi chạy `git restore --staged <file>`, phần thay đổi staged của file thường biến mất khỏi `git diff --cached`. Nếu working tree vẫn khác `HEAD`, thay đổi đó sẽ xuất hiện trong `git diff`.

Ví dụ quy trình đầy đủ:

```bash
git status
git diff --cached -- src/config.yml
git restore --staged -- src/config.yml
git status
git diff --cached -- src/config.yml
git diff -- src/config.yml
```

Nếu file trở về trạng thái hoàn toàn giống `HEAD` ở cả index lẫn working tree, `git status` sẽ không còn hiển thị thay đổi cho file đó.

## 4. Bỏ staging file mới chưa từng commit

Giả sử bạn tạo file mới `notes/draft.md` rồi stage:

```bash
git add notes/draft.md
git status --short
```

Vì file chưa tồn tại trong `HEAD`, lệnh:

```bash
git restore --staged -- notes/draft.md
```

sẽ loại mục đó khỏi index. File vẫn còn trên đĩa và trở thành **untracked**:

```bash
git status --short
```

Bạn có thể tiếp tục chỉnh sửa, stage lại hoặc xóa file bằng thao tác hệ thống tệp nếu thực sự muốn xóa. `git restore --staged` không xóa file mới khỏi working tree.

Đây là cách an toàn để sửa tình huống stage nhầm file mới, ví dụ file log hoặc file nháp, trước khi commit.

## 5. Bỏ staging một file đã bị xóa

Nếu bạn xóa một file tracked khỏi working tree rồi stage thao tác xóa:

```bash
git rm src/legacy-config.yml
```

Index ghi nhận việc xóa file. Nếu muốn bỏ staging thao tác xóa nhưng vẫn giữ file ở trạng thái đã xóa trong working tree, chạy:

```bash
git restore --staged -- src/legacy-config.yml
```

Git đưa mục index trở lại phiên bản từ `HEAD`, nhưng không tự khôi phục file vào working tree. Kết quả là index cho rằng file vẫn tồn tại, còn working tree không có file; `git status` sẽ hiển thị thao tác xóa chưa stage.

Nếu mục tiêu là khôi phục cả file trong working tree, đó là thao tác khác:

```bash
git restore --worktree -- src/legacy-config.yml
```

Lệnh trên lấy nội dung từ index hiện tại và ghi lại file trên đĩa. Hãy phân biệt rõ `--staged` với `--worktree` để tránh ghi đè nội dung bạn muốn giữ.

## 6. Bỏ staging một phần thay đổi bằng chế độ patch

Nếu một file có nhiều hunk đã stage và bạn chỉ muốn rút một số hunk khỏi index, dùng chế độ tương tác:

```bash
git restore --staged --patch -- src/app.js
```

Git hiển thị từng hunk khác biệt giữa nguồn khôi phục (mặc định là `HEAD`) và index. Bạn chọn hunk muốn khôi phục vào index. Các thay đổi trong working tree được giữ nguyên.

Một số phím thường gặp trong chế độ patch:

| Phím | Ý nghĩa |
|---|---|
| `y` | Áp dụng hunk đang hiển thị vào index (bỏ staging hunk đó) |
| `n` | Giữ nguyên hunk trong index |
| `q` | Thoát chế độ tương tác |
| `s` | Chia hunk thành các phần nhỏ hơn nếu có thể |
| `?` | Xem trợ giúp các lựa chọn |

Với `git restore --staged --patch`, thao tác `y` khôi phục hunk trong index về nội dung từ nguồn, thường là `HEAD`; nó không xóa hunk khỏi working tree. Sau khi kết thúc, kiểm tra lại:

```bash
git diff --cached -- src/app.js
git diff -- src/app.js
```

Chế độ patch hữu ích khi bạn đã stage một phần file, sau đó nhận ra một vài thay đổi chưa sẵn sàng đưa vào commit.

## 7. Chọn nguồn khác bằng --source

Mặc định, `git restore --staged` dùng `HEAD` làm nguồn. Bạn có thể chọn một commit hoặc tree khác:

```bash
git restore --staged --source=HEAD~1 -- src/config.yml
```

Lệnh đưa mục index của `src/config.yml` về phiên bản ở commit cha của `HEAD`. Working tree vẫn không thay đổi. Sau đó, nếu stage lại file bằng `git add`, nội dung trong working tree sẽ thay thế mục index.

Có thể dùng tag hoặc mã commit:

```bash
git restore --staged --source=v1.2.0 -- docs/release-notes.md
git restore --staged --source=<COMMIT_ID> -- src/api/schema.json
```

Khi dùng nguồn khác `HEAD`, hãy kiểm tra kỹ nội dung index sau thao tác vì bạn đang chọn một phiên bản cũ hoặc khác với commit hiện tại. `git restore --staged` không di chuyển branch và không thay đổi commit.

## 8. Đường dẫn, thư mục và pathspec

Bạn có thể chỉ định thư mục để bỏ staging tất cả mục bên trong:

```bash
git restore --staged -- src/generated/
```

Đường dẫn tương đối thường được hiểu từ thư mục hiện tại nơi bạn chạy Git. Nếu muốn chỉ rõ đường dẫn tính từ gốc repository, có thể dùng pathspec magic:

```bash
git restore --staged -- ':(top)src/config.yml'
```

Nếu tên file bắt đầu bằng dấu `-`, dùng `--` để Git không hiểu tên đó là tùy chọn:

```bash
git restore --staged -- -draft.txt
```

Với đường dẫn có khoảng trắng, đặt trong dấu nháy theo shell:

```bash
git restore --staged -- "docs/release notes.md"
```

Trên Windows PowerShell, dấu nháy kép thường phù hợp với ví dụ này. Hãy kiểm tra `git status` trước khi thao tác trên nhiều đường dẫn hoặc pattern rộng.

## 9. Phân biệt git restore --staged với các lệnh liên quan

| Lệnh | Tác động lên index | Tác động lên working tree | Mục đích |
|---|---|---|---|
| `git restore --staged -- <path>` | Khôi phục mục từ `HEAD` vào index | Giữ nguyên | Bỏ staging |
| `git restore --worktree -- <path>` | Giữ nguyên | Khôi phục file từ index | Bỏ thay đổi chưa stage |
| `git restore --staged --worktree -- <path>` | Khôi phục index từ `HEAD` | Khôi phục working tree từ nguồn theo quy tắc lệnh | Đưa cả hai vùng về trạng thái nguồn |
| `git reset -- <path>` | Khôi phục index từ `HEAD` | Giữ nguyên | Cú pháp cũ để bỏ staging |
| `git rm --cached -- <path>` | Xóa mục khỏi index | Giữ file trên đĩa | Ngừng theo dõi file trong commit tiếp theo |

Hai lệnh sau thường dễ nhầm:

```bash
git restore --staged -- config/local.yml
git rm --cached -- config/local.yml
```

Lệnh thứ nhất đưa mục index về trạng thái trong `HEAD`. Nếu file đã được commit, nó vẫn tiếp tục được theo dõi. Lệnh thứ hai xóa mục khỏi index, khiến file trở thành untracked (trừ khi bị ignore); đây thường là thao tác dùng khi muốn ngừng theo dõi file nhưng giữ bản local.

`git reset <path>` là cách truyền thống để bỏ staging. Trong Git hiện đại, `git restore --staged` thể hiện ý định rõ hơn và tách riêng thao tác khôi phục index khỏi việc di chuyển `HEAD` của `git reset`.

## 10. Những điều cần kiểm tra trước khi bỏ staging

- Xem `git status` để biết file nào đã stage và file nào còn thay đổi chưa stage.
- Dùng `git diff --cached` để xác nhận nội dung hiện đang nằm trong index.
- Nếu file có cả staged và unstaged changes, nhớ rằng bỏ staging toàn bộ file sẽ đưa index về nguồn, còn mọi nội dung trong working tree được giữ.
- Nếu chỉ muốn bỏ staging vài hunk, dùng `--patch` thay vì bỏ staging cả file.
- Nếu file mới chưa tồn tại trong `HEAD`, sau khi bỏ staging nó sẽ trở thành untracked.
- Nếu file đã bị stage xóa, bỏ staging sẽ khôi phục mục trong index nhưng không khôi phục file trên đĩa.
- Kiểm tra lại `git diff --cached` trước khi commit để chắc chắn commit chỉ chứa nội dung mong muốn.

## 11. Quy trình ví dụ: stage nhầm file cấu hình

Giả sử bạn đang chuẩn bị commit tính năng đăng nhập. Bạn stage các file:

```bash
git add src/auth/LoginService.java src/auth/LoginController.java config/local.yml
```

Sau đó nhận ra `config/local.yml` chứa cấu hình riêng của máy và không nên đưa vào commit. Kiểm tra:

```bash
git status --short
git diff --cached -- config/local.yml
```

Bỏ staging file cấu hình:

```bash
git restore --staged -- config/local.yml
```

Kiểm tra lại:

```bash
git status --short
git diff --cached
git diff -- config/local.yml
```

Nếu file vẫn cần tồn tại ở local, giữ nguyên working tree và thêm quy tắc ignore phù hợp nếu đó là file cấu hình riêng của máy. Nếu file chứa secret đã từng được commit trước đây, bỏ staging hiện tại không xóa secret khỏi lịch sử; cần xử lý sự cố lộ secret và quy trình loại bỏ khỏi lịch sử riêng.

Khi nội dung staged đã đúng:

```bash
git diff --cached
git commit -m "Implement login flow"
```

## 12. Bài tập thực hành

Trong một repository thử nghiệm, tạo commit ban đầu chứa `README.md` và `src/app.js`.

1. Sửa `README.md`, chạy `git add README.md`, rồi dùng `git diff --cached` để xem nội dung đã stage.
2. Sửa tiếp `README.md` sau khi stage và kiểm tra cả `git diff --cached` lẫn `git diff`.
3. Chạy `git restore --staged -- README.md`, sau đó xác nhận thay đổi vẫn còn trong working tree nhưng không còn trong index.
4. Tạo file mới `notes/draft.md`, stage file, rồi bỏ staging và xác nhận file trở thành untracked nhưng vẫn còn trên đĩa.
5. Xóa một file tracked, stage thao tác xóa, rồi dùng `git restore --staged` để xác nhận file vẫn bị xóa trong working tree nhưng mục index được khôi phục.
6. Stage nhiều hunk trong một file và dùng `git restore --staged -p` để chỉ bỏ staging một hunk.
7. Dùng `--source=HEAD~1` trong repository có ít nhất hai commit, rồi kiểm tra nội dung index đã được lấy từ commit nào.
8. So sánh `git restore --staged`, `git restore --worktree` và `git rm --cached` bằng `git status`.

Bạn hoàn thành bài tập khi có thể bỏ staging một file hoặc một phần thay đổi mà không làm mất nội dung working tree, và giải thích được khác biệt giữa khôi phục index, khôi phục file trên đĩa và ngừng theo dõi file.

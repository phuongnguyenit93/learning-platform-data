# Đổi tên, di chuyển và xóa tệp bằng git mv, git rm

Khi đổi tên hoặc chuyển vị trí một file đã được Git theo dõi, bạn có thể dùng `git mv`. Khi muốn xóa file khỏi repository, dùng `git rm`. Hai lệnh này cập nhật cả working tree và index để thao tác được ghi nhận cho commit tiếp theo.

Điểm cần nhớ là Git lưu snapshot của các đường dẫn và nội dung file. Commit không lưu một thao tác “rename” riêng biệt. Khi xem lịch sử, Git nhận diện đổi tên bằng cách so sánh nội dung ở đường dẫn cũ và mới. Vì vậy, đổi tên đúng cách giúp staging rõ ràng, còn khả năng Git hiển thị đó là rename phụ thuộc vào mức độ giống nhau của nội dung.

## 1. Đổi tên file bằng git mv

Cú pháp cơ bản:

```bash
git mv <source> <destination>
```

Ví dụ đổi tên file:

```bash
git mv src/old-name.js src/new-name.js
```

Sau lệnh, file được chuyển trong working tree và index được cập nhật để ghi nhận đường dẫn mới. Kiểm tra:

```bash
git status --short
git diff --cached --summary
git diff --cached --find-renames
```

Nếu Git nhận diện được độ tương đồng nội dung, `status` thường hiển thị trạng thái rename, ví dụ `R` trong dạng ngắn. Phần thay đổi đã stage có thể được xem bằng `git diff --cached`.

### Di chuyển file sang thư mục khác

Bạn cũng có thể thay đổi cả thư mục chứa file:

```bash
git mv src/config.yml config/config.yml
git mv docs/old-guide.md docs/guides/guide.md
```

Đích có thể là một đường dẫn file mới hoặc một thư mục đã tồn tại. Nếu đích là thư mục, Git chuyển file vào thư mục đó theo tên file hiện tại. Các thư mục cha cần tồn tại hoặc có thể được tạo theo cách Git và hệ điều hành hỗ trợ.

### Di chuyển cả thư mục

Git không theo dõi thư mục rỗng như một object riêng; Git theo dõi file và đường dẫn của chúng trong tree. Khi chuyển một thư mục có file được theo dõi:

```bash
git mv src/legacy-module src/archive/legacy-module
```

Git chuyển các file tracked trong thư mục đó và cập nhật index. Thư mục rỗng không được giữ lại trong commit nếu không có file nào bên trong.

## 2. git mv làm gì với index?

`git mv` là lệnh tiện ích kết hợp thao tác di chuyển trên filesystem với cập nhật index. Có thể hình dung gần tương đương với việc di chuyển file, stage đường dẫn mới và loại đường dẫn cũ khỏi index:

```bash
# Minh họa ý nghĩa tương đương, không cần chạy thêm sau git mv
mv src/old-name.js src/new-name.js
git add src/new-name.js
git rm --cached src/old-name.js
```

Trong thực tế, hãy dùng `git mv` để Git thực hiện các bước liên quan một cách nhất quán. Sau lệnh, index ghi nhận file ở đường dẫn mới và không còn entry ở đường dẫn cũ. Nội dung file mới được stage theo trạng thái tại thời điểm thao tác.

Nếu file có thay đổi chưa stage trước khi đổi tên, hãy chú ý: nội dung hiện tại có thể được đưa vào index cùng thao tác rename. Nếu bạn cần tách riêng thay đổi nội dung và đổi tên thành các commit khác nhau, hãy stage/commit phần nội dung theo kế hoạch trước, hoặc kiểm tra kỹ `git diff --cached` và `git diff` sau khi di chuyển.

## 3. Đổi tên không đồng nghĩa Git lưu một thao tác rename

Git lưu tree snapshot. Một tree chứa entry có tên và OID của object; sau khi đổi tên, tree mới có tên đường dẫn mới. Trong commit, Git nhìn thấy đường dẫn cũ biến mất và đường dẫn mới xuất hiện.

Khi hiển thị diff, Git có thể ghép cặp file bị xóa với file mới dựa trên độ tương đồng nội dung. Đây là **rename detection** (nhận diện đổi tên), không phải một loại object hoặc metadata rename được lưu độc lập trong commit.

Ví dụ:

```text
Commit trước:                 Commit sau:
src/old-name.js               src/new-name.js
blob A                        blob A hoặc blob B
```

Nếu nội dung giữ nguyên, Git thường nhận diện đây là rename 100%. Nếu file được đổi tên và chỉnh sửa nhiều, mức tương đồng có thể thấp và diff có thể hiển thị thành delete + add.

Yêu cầu Git hiển thị nhận diện rename rõ ràng:

```bash
git diff --cached --find-renames
git show --summary --find-renames HEAD
```

Có thể đặt ngưỡng tương đồng, ví dụ:

```bash
git diff --cached --find-renames=70%
```

Ngưỡng cao yêu cầu nội dung giống nhau nhiều hơn để ghép thành rename; ngưỡng thấp cho phép nhận diện các file đã được chỉnh sửa nhiều hơn. Kết quả là cách Git trình bày diff, không thay đổi cách commit lưu snapshot.

## 4. Đổi tên file chỉ khác chữ hoa/chữ thường

Trên một số filesystem mặc định không phân biệt chữ hoa và chữ thường, đặc biệt cấu hình Windows phổ biến, việc đổi `Readme.md` thành `README.md` có thể không được xử lý như hai đường dẫn khác nhau ở filesystem.

Một cách an toàn là dùng tên trung gian:

```bash
git mv Readme.md README.tmp
git mv README.tmp README.md
```

Kiểm tra lại tên file và trạng thái:

```bash
git status --short
git diff --cached --summary
```

Nếu repository dùng filesystem phân biệt hoa thường, thao tác một bước có thể hoạt động; tên trung gian là cách dễ dự đoán hơn khi cộng tác giữa Windows, macOS và Linux.

## 5. Các tùy chọn thường gặp của git mv

| Tùy chọn | Tác dụng |
|---|---|
| `-v`, `--verbose` | Hiển thị chi tiết file được di chuyển |
| `-f`, `--force` | Cho phép ghi đè đích trong các trường hợp Git cho phép |
| `-n`, `--dry-run` | Chỉ hiển thị thao tác dự kiến, không thực hiện |
| `-k` | Bỏ qua lỗi từng đường dẫn và tiếp tục với đường dẫn khác khi có thể |

Xem trước một thao tác:

```bash
git mv --dry-run src/old-name.js src/new-name.js
```

`--force` có thể ghi đè file đích. Hãy kiểm tra file đích trước khi dùng; nếu file đó chứa nội dung chưa được lưu, thao tác ghi đè có thể làm mất dữ liệu. `--dry-run` hữu ích khi đổi tên nhiều file hoặc di chuyển một cây thư mục lớn.

## 6. Xóa file khỏi working tree và index bằng git rm

`git rm` xóa file khỏi working tree và stage thao tác xóa trong index.

Cú pháp:

```bash
git rm [options] -- <pathspec>...
```

Ví dụ xóa một file:

```bash
git rm src/obsolete-helper.js
```

Xóa nhiều file:

```bash
git rm docs/old-api.md tests/obsolete-test.js
```

Sau khi chạy, file bị xóa khỏi working tree và index ghi nhận đường dẫn đó không còn trong snapshot tiếp theo. Kiểm tra:

```bash
git status --short
git diff --cached --summary
git diff --cached
```

Khi commit, thao tác xóa sẽ được ghi vào lịch sử:

```bash
git commit -m "Remove obsolete API helper"
```

## 7. Xóa thư mục bằng git rm -r

Để xóa tất cả file được Git theo dõi bên trong một thư mục, dùng `-r`:

```bash
git rm -r -- src/legacy-module
```

Lệnh đệ quy xóa các file tracked phù hợp trong thư mục và stage các thao tác xóa. File untracked hoặc ignored không tự động trở thành đối tượng được Git quản lý chỉ vì chúng nằm trong cùng thư mục; hãy kiểm tra kỹ trước khi dọn cả thư mục bằng công cụ hệ thống.

Trước khi xóa nhiều file, có thể xem trước:

```bash
git rm -n -r -- src/legacy-module
```

`-n`/`--dry-run` liệt kê thao tác dự kiến mà không xóa file hoặc cập nhật index. Dùng dry-run khi pathspec rộng hoặc thư mục chứa nhiều nội dung.

## 8. Khi file có thay đổi chưa commit

Nếu file tracked đã bị chỉnh sửa trong working tree hoặc index, `git rm` có thể từ chối xóa để tránh mất thay đổi. Ví dụ:

```text
error: the following file has local modifications:
    src/config.yml
```

Trước khi quyết định, xem thay đổi ở cả hai vùng:

```bash
git status --short
git diff -- src/config.yml
git diff --cached -- src/config.yml
```

Nếu thay đổi cần giữ, hãy commit hoặc sao lưu chúng trước. Nếu bạn đã xác nhận muốn xóa file cùng các thay đổi local, có thể dùng `-f`:

```bash
git rm -f -- src/config.yml
```

`-f` (force) bỏ qua một số kiểm tra an toàn về khác biệt giữa `HEAD`, index và working tree. Đây là thao tác có thể làm mất nội dung chưa được lưu ở nơi khác; không dùng chỉ để làm lệnh chạy qua khi chưa xem diff.

## 9. Ngừng theo dõi file nhưng giữ file trên máy bằng git rm --cached

Nếu một file đã được commit nhưng từ nay không muốn Git theo dõi nữa, trong khi vẫn cần giữ bản local, dùng `--cached`:

```bash
git rm --cached -- config/local.yml
```

Lệnh này xóa entry khỏi index nhưng giữ file trong working tree. Khi commit, repository sẽ ghi nhận file bị xóa; ở máy của bạn, file vẫn còn và thường xuất hiện là untracked (trừ khi bị ignore).

Trường hợp phổ biến là file cấu hình riêng của từng máy. Sau khi bỏ theo dõi, thêm quy tắc phù hợp vào `.gitignore`:

```gitignore
config/local.yml
```

Sau đó stage `.gitignore` và commit cả hai thay đổi:

```bash
git add .gitignore
git status --short
git commit -m "Stop tracking local configuration"
```

Lưu ý: `git rm --cached` chỉ ngừng theo dõi trong các commit tiếp theo. Nếu file từng chứa mật khẩu, token hoặc khóa riêng, nội dung cũ vẫn có trong lịch sử Git. Cần thu hồi/đổi secret và xử lý lịch sử theo quy trình bảo mật; thêm `.gitignore` không xóa dữ liệu đã commit.

## 10. Các tùy chọn hữu ích của git rm

| Tùy chọn | Tác dụng |
|---|---|
| `-r` | Xóa đệ quy các file tracked trong thư mục |
| `-f`, `--force` | Bỏ qua kiểm tra an toàn khi file có thay đổi |
| `--cached` | Chỉ xóa khỏi index, giữ file trong working tree |
| `-n`, `--dry-run` | Xem trước các đường dẫn sẽ bị xóa |
| `-q`, `--quiet` | Giảm thông báo đầu ra |
| `--ignore-unmatch` | Không báo lỗi nếu pathspec không khớp file tracked nào |

Ví dụ:

```bash
git rm --dry-run -r -- generated/
git rm --cached -- .env.local
```

Hãy dùng `--ignore-unmatch` trong script khi việc không có file khớp là tình huống chấp nhận được. Trong thao tác thủ công, lỗi không khớp thường là tín hiệu cần kiểm tra lại đường dẫn.

## 11. Xóa file bằng hệ thống tệp khác gì git rm?

Bạn có thể xóa file bằng Explorer, Finder, `rm` hoặc `del`. Khi đó, working tree thay đổi nhưng index chưa được cập nhật. `git status` sẽ báo file tracked bị deleted nhưng chưa stage.

Ví dụ:

```bash
rm src/obsolete-helper.js
git status --short
```

Để stage thao tác xóa sau khi đã xóa bằng filesystem:

```bash
git add -u -- src/obsolete-helper.js
```

Hoặc stage mọi thay đổi tracked:

```bash
git add -u
```

`git rm` kết hợp xóa trên filesystem và cập nhật index trong một lệnh, nên thường rõ ý định hơn. Dù dùng cách nào, Git vẫn lưu snapshot ở commit; nó không ghi một lịch sử thao tác xóa riêng ngoài thay đổi tree.

Không dùng `git clean` để thay cho `git rm` khi muốn xóa file tracked. `git clean` dọn file untracked (và có thể cả ignored với tùy chọn phù hợp), còn `git rm` xử lý đường dẫn đang được index theo dõi.

## 12. Xem lịch sử sau khi rename hoặc delete

Vì Git nhận diện rename bằng cách so sánh nội dung, bạn có thể xem tóm tắt thao tác bằng:

```bash
git diff --cached --summary --find-renames
git show --summary --find-renames HEAD
```

Để theo dõi lịch sử của file qua các lần đổi tên, dùng `--follow`:

```bash
git log --follow --oneline -- src/new-name.js
```

`--follow` giúp lần ngược lịch sử của một file qua rename được Git nhận diện. Tùy chọn này áp dụng cho một path và có giới hạn với lịch sử merge phức tạp. Nếu Git không nhận diện được rename do nội dung thay đổi quá nhiều, lịch sử có thể không nối như bạn mong đợi.

Muốn tìm commit đã xóa file:

```bash
git log --all --diff-filter=D --summary -- src/obsolete-helper.js
```

Lệnh tìm các commit có thay đổi xóa đường dẫn đó. Nếu file đã được xóa ở branch hiện tại nhưng còn trong commit trước, có thể xem nội dung cũ bằng:

```bash
git show HEAD~1:src/obsolete-helper.js
```

Thay `HEAD~1` bằng commit phù hợp tìm được trong lịch sử.

## 13. Hoàn tác thao tác trước khi commit

Nếu bạn vừa stage một thao tác xóa bằng `git rm` nhưng chưa commit, có thể khôi phục index từ `HEAD`:

```bash
git restore --staged -- src/obsolete-helper.js
```

Lệnh này bỏ staging việc xóa; file vẫn chưa có trong working tree. Để khôi phục file trên đĩa từ index:

```bash
git restore --worktree -- src/obsolete-helper.js
```

Nếu đã commit thao tác xóa và muốn đảo ngược trên branch dùng chung, cách an toàn thường là tạo commit mới bằng `git revert`:

```bash
git revert <DELETE_COMMIT>
```

Nếu cần lấy lại file từ một commit cụ thể, có thể khôi phục đường dẫn từ commit đó rồi commit lại:

```bash
git restore --source=<COMMIT_ID> --worktree -- src/obsolete-helper.js
git add src/obsolete-helper.js
git commit -m "Restore obsolete helper"
```

Hãy xác định đúng commit nguồn trước khi ghi file để tránh thay thế phiên bản hiện tại bằng nội dung cũ ngoài ý muốn.

## 14. Quy trình thực tế: đổi tên, di chuyển và xóa file

Giả sử bạn cần tổ chức lại module trong dự án:

```bash
# Đổi tên file
git mv src/old-service.js src/payment-service.js

# Di chuyển tài liệu
git mv docs/old-api.md docs/api/guide.md

# Xóa file không còn dùng
git rm src/legacy-adapter.js

# Kiểm tra trạng thái và diff đã stage
git status --short
git diff --cached --summary --find-renames
git diff --cached
```

Nếu kết quả đúng, tạo commit:

```bash
git commit -m "Reorganize payment module files"
```

Nếu một file cấu hình cần giữ local nhưng không còn theo dõi:

```bash
git rm --cached -- config/local.yml
```

Sau đó thêm file vào `.gitignore` và commit thay đổi ignore cùng với việc ngừng theo dõi.

## 15. Bài tập thực hành

Trong repository thử nghiệm, tạo commit ban đầu chứa `src/old-name.js`, `docs/old-guide.md` và `config/local.yml`.

1. Dùng `git mv` đổi tên `src/old-name.js` thành `src/new-name.js`; kiểm tra bằng `git status --short` và `git diff --cached --summary`.
2. Dùng `git mv` chuyển tài liệu vào `docs/guides/guide.md`; xác nhận index ghi nhận đường dẫn mới.
3. Chỉnh sửa nội dung file sau khi đổi tên, rồi dùng `git diff --cached` và `git diff` để phân biệt phần đã stage với phần chưa stage.
4. Dùng `git rm` xóa một file tracked và kiểm tra thao tác xóa đã được stage.
5. Thử `git rm --cached config/local.yml`, xác nhận file còn trên đĩa và không còn được index theo dõi; thêm quy tắc vào `.gitignore`.
6. Trong môi trường filesystem phù hợp, thử đổi tên chỉ khác chữ hoa/thường qua một tên trung gian.
7. Commit các thay đổi, sau đó dùng `git log --follow --oneline -- src/new-name.js` để xem lịch sử qua rename.
8. Giải thích vì sao Git nhận diện rename dựa trên nội dung thay vì lưu một thao tác rename riêng.

Bạn hoàn thành bài tập khi biết dùng `git mv` để đổi tên/di chuyển, dùng `git rm` để xóa và `git rm --cached` để ngừng theo dõi mà giữ file local; đồng thời kiểm tra được nội dung staged trước khi commit.

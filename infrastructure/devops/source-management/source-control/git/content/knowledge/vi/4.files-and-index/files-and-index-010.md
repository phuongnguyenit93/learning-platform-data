# Chọn đường dẫn bằng pathspec và tách tùy chọn với dấu `--`

Các lệnh Git thường nhận đường dẫn để giới hạn phạm vi thao tác: stage một vài tệp, xem diff của một thư mục, khôi phục một file hoặc tìm lịch sử của một module. Git dùng **pathspec** để mô tả tập đường dẫn cần chọn. Pathspec có thể là tên tệp cụ thể, thư mục, mẫu wildcard hoặc biểu thức có magic như `:(glob)`, `:(top)`, `:(literal)` và `:(exclude)`.

Một ký tự `-` ở đầu tên tệp có thể khiến Git hiểu nhầm đó là tùy chọn. Dấu phân cách `--` giải quyết sự nhập nhằng này bằng cách báo cho Git rằng các đối số tiếp theo là đường dẫn/pathspec. Nó cũng giúp phân tách revision với path trong các lệnh như `git log` và `git diff`.

Bài này thuộc chương **Tệp và chỉ mục** của SOURCE_CONTROL_GIT. Bạn sẽ học cách chọn đúng phạm vi đường dẫn, kiểm soát wildcard, loại trừ thư mục, xử lý tên tệp đặc biệt và dùng `--` an toàn trong các thao tác hằng ngày.

## 1. Pathspec là gì?

Pathspec là cú pháp Git dùng để xác định một hoặc nhiều đường dẫn. Nó xuất hiện trong nhiều lệnh, ví dụ:

```bash
git add -- src/app.js
git diff -- src/
git restore --staged -- README.md
git log --oneline -- src/app.js
git ls-files -- '*.js'
```

Trong các ví dụ này, pathspec có thể là một tệp, một thư mục hoặc một mẫu chọn nhiều tệp. Lệnh Git sẽ áp dụng hành động lên những đường dẫn khớp với pathspec theo quy tắc của lệnh đó.

Pathspec không phải lúc nào cũng chỉ là chuỗi đường dẫn literal. Nó có thể chứa wildcard hoặc magic để điều khiển cách Git so khớp. Do đó, cần hiểu pathspec trước khi dùng nó trong lệnh có tác động tới index hoặc working tree.

### 1.1. Đường dẫn cụ thể

Pathspec đơn giản nhất là đường dẫn tương đối:

```bash
git add -- src/app.js
git diff -- src/app.js
```

Nếu đưa một thư mục:

```bash
git add -- src/
```

Git áp dụng lệnh cho các đường dẫn phù hợp trong thư mục đó và các thư mục con. Đây là cách thuận tiện khi muốn thao tác theo một module.

### 1.2. Pathspec thường tính từ thư mục hiện tại

Đường dẫn pathspec thông thường được hiểu tương đối với thư mục làm việc hiện tại. Giả sử repository:

```text
project/
  src/
    api/
      client.js
    web/
      app.js
  docs/
    setup.md
```

Nếu đang ở thư mục gốc `project`, lệnh:

```bash
git add -- src/api/client.js
```

chọn `src/api/client.js`. Nhưng nếu đang ở `project/src/api`, pathspec:

```bash
git add -- client.js
```

mới chỉ tới cùng tệp đó. Pathspec `src/api/client.js` khi chạy từ `src/api` không còn có nghĩa là đường dẫn từ gốc repository.

Nếu muốn pathspec luôn tính từ gốc repository, dùng magic `top` hoặc dạng rút gọn `:/`.

## 2. Dùng `--` để kết thúc phần tùy chọn

Trong nhiều lệnh Git, `--` là dấu phân cách giữa các tùy chọn/đối số trước đó và danh sách pathspec phía sau.

Ví dụ:

```bash
git add -p -- src/app.js
git diff --cached -- src/app.js
git restore --staged -- src/app.js
git rm -- src/old-file.js
```

Git hiểu các phần sau `--` là pathspec, không tiếp tục phân tích chúng như tùy chọn của lệnh.

### 2.1. Khi tên tệp bắt đầu bằng dấu `-`

Giả sử repository có một tệp tên `-draft.txt`. Nếu gọi:

```bash
git add -draft.txt
```

Git có thể hiểu `-draft.txt` là một tùy chọn và báo lỗi. Hãy dùng:

```bash
git add -- -draft.txt
```

Hoặc ghi rõ đường dẫn tương đối:

```bash
git add -- ./-draft.txt
```

Tương tự với các lệnh khác:

```bash
git diff -- --draft.txt
git restore --staged -- -draft.txt
git rm -- -draft.txt
```

### 2.2. `--` không phải một phần của pathspec

Trong lệnh:

```bash
git add -- src/app.js
```

pathspec là `src/app.js`; `--` chỉ là dấu phân cách. Không đưa `--` vào tên tệp hoặc vào pattern.

### 2.3. `--` trong lệnh có cả revision và path

Một số lệnh nhận cả revision và đường dẫn. Ví dụ:

```bash
git log --oneline HEAD -- src/app.js
git diff HEAD~1 HEAD -- src/app.js
git show HEAD -- src/app.js
```

Các đối số revision nằm trước `--`; pathspec nằm sau `--`. Điều này giúp Git không nhầm tên đường dẫn với tên branch, tag hoặc revision.

Với `git log`, nếu chỉ muốn xem lịch sử của một đường dẫn từ HEAD hiện tại:

```bash
git log --oneline -- src/app.js
```

Nếu muốn xem cả một branch cụ thể:

```bash
git log --oneline origin/main -- src/app.js
```

## 3. Phân biệt pathspec với wildcard của shell

Khi gõ lệnh trong terminal, wildcard có thể được xử lý bởi shell trước khi Git nhận đối số. Đây là nguồn gây nhầm lẫn phổ biến.

Ví dụ:

```bash
git add *.js
```

Ở một số shell, `*.js` được shell mở rộng thành danh sách tên tệp trong thư mục hiện tại trước khi gọi Git. Khi đó, Git không nhận một pathspec wildcard duy nhất mà nhận nhiều đối số đường dẫn đã được shell mở rộng.

Nếu muốn Git tự xử lý pattern, hãy quote nó:

```bash
git add -- '*.js'
```

Quy tắc quote cụ thể tùy shell. Ví dụ trên dùng dấu nháy đơn trong Bash, zsh và PowerShell để truyền pattern như một đối số. Trong script, hãy quote từng biến chứa pathspec và tránh ghép dữ liệu thành chuỗi lệnh.

### 3.1. Vì sao nên quote pathspec?

Quote giúp:

- Ngăn shell mở rộng `*`, `?` hoặc `[]` trước khi Git xử lý.
- Giữ nguyên dấu cách trong tên tệp.
- Tránh tách một pathspec thành nhiều đối số ngoài ý muốn.
- Làm ví dụ nhất quán hơn giữa các shell.

Ví dụ tên tệp có dấu cách:

```bash
git add -- 'docs/meeting notes.md'
```

Không quote:

```bash
git add docs/meeting notes.md
```

shell có thể truyền `docs/meeting` và `notes.md` thành hai đối số khác nhau, khiến Git tìm sai đường dẫn.

### 3.2. Wildcard được Git xử lý

Khi pattern được quote, Git nhận pattern và áp dụng quy tắc pathspec của nó. Để tránh phụ thuộc vào cách hiểu wildcard mặc định, có thể dùng rõ `:(glob)` khi muốn glob-style matching.

Ví dụ:

```bash
git add -- ':(glob)src/**/*.js'
```

Với glob magic:

- `*` khớp các ký tự trong một thành phần đường dẫn, không đi qua dấu `/`.
- `?` khớp một ký tự trong một thành phần đường dẫn.
- `**` có ý nghĩa đặc biệt để khớp qua nhiều cấp thư mục.
- `**/` có thể khớp không cấp thư mục nào hoặc nhiều cấp thư mục.

Pattern `:(glob)src/**/*.js` có thể khớp `src/app.js`, `src/api/client.js` và các tệp `.js` ở sâu hơn trong `src`.

## 4. Pathspec magic

Git cho phép thêm magic vào đầu pathspec để thay đổi cách so khớp. Dạng dài:

```text
:(magic[,magic...])pattern
```

Ví dụ:

```bash
git add -- ':(top,glob)src/**/*.js'
```

Trong đó `top` và `glob` là các magic được áp dụng cùng lúc cho pattern.

### 4.1. `top`: tính từ gốc repository

Magic `top` buộc pathspec được tính từ gốc working tree, bất kể lệnh được gọi từ thư mục con nào:

```bash
git add -- ':(top)src/api/client.js'
```

Dạng rút gọn là `:/`:

```bash
git add -- ':/src/api/client.js'
```

Điều này hữu ích trong script được gọi từ nhiều thư mục khác nhau. Pathspec `:(top)` giúp phạm vi không phụ thuộc current working directory.

### 4.2. `literal`: coi mọi ký tự là ký tự thường

Magic `literal` yêu cầu Git không diễn giải wildcard hoặc magic trong phần pattern:

```bash
git add -- ':(literal)src/[draft]*.txt'
```

Pathspec này tìm đúng đường dẫn có ký tự `[draft]*.txt` theo nghĩa literal, thay vì coi `[]` và `*` là pattern.

Khi đường dẫn đến từ người dùng hoặc dữ liệu bên ngoài và cần khớp đúng tên, `literal` giúp tránh việc wildcard vô tình chọn thêm tệp.

### 4.3. `glob`: dùng cú pháp glob rõ ràng

Magic `glob` dùng quy tắc glob-style cho pathspec:

```bash
git ls-files -- ':(glob)docs/**/*.md'
git diff --cached -- ':(glob)src/**/*.ts'
```

Với `glob`, `*` và `?` không khớp dấu phân cách thư mục `/`; dùng `**` khi muốn đi qua nhiều cấp. Magic `glob` không kết hợp với `literal` vì hai chế độ có mục đích trái ngược.

### 4.4. `icase`: không phân biệt chữ hoa/thường

Magic `icase` khiến việc so khớp không phân biệt chữ hoa và chữ thường:

```bash
git ls-files -- ':(icase)readme.md'
```

Nó hữu ích khi tìm đường dẫn trong repository có thể được tạo trên hệ thống filesystem khác nhau. Tuy nhiên, không nên dùng `icase` để che giấu khác biệt tên tệp trong dự án nếu nhóm cần giữ quy ước viết hoa/thường nhất quán.

### 4.5. `exclude`: loại trừ một phần đường dẫn

Magic `exclude` (dạng ngắn `:!` hoặc `:^`) loại các pathspec khớp khỏi tập đã chọn. Thường cần có ít nhất một pathspec dương trước đó.

Ví dụ stage nội dung trong `src/` nhưng bỏ qua mã sinh tự động:

```bash
git add -A -- ':(top)src' ':(exclude,top)src/generated'
```

Ở đây:

- `:(top)src` chọn đường dẫn thuộc thư mục `src` từ gốc repository.
- `:(exclude,top)src/generated` loại thư mục `src/generated` khỏi tập đó.

Dạng ngắn:

```bash
git add -A -- ':/src' ':!/src/generated'
```

Khi dùng exclusion, hãy xem lại kết quả:

```bash
git status --short
git diff --cached --name-status
```

Nếu pathspec âm không khớp như mong đợi, kiểm tra vị trí gốc, dấu `/`, wildcard và thứ tự các pathspec. Không commit chỉ dựa trên giả định rằng thư mục đã được loại trừ.

### 4.6. `attr`: chọn đường dẫn theo Git attributes

Magic `attr` cho phép chọn đường dẫn dựa trên thuộc tính được gán trong `.gitattributes`:

```bash
git ls-files -- ':(attr:filter=lfs)'
```

Ví dụ này tìm đường dẫn có attribute `filter` mang giá trị `lfs`. Có thể dùng điều kiện thuộc tính phủ định hoặc chưa được đặt theo cú pháp attr pathspec. Đây là tính năng nâng cao; cần bảo đảm `.gitattributes` được đọc đúng trong repository và hiểu quy tắc attribute trước khi dùng để stage hoặc xóa tệp.

## 5. Dùng pathspec trong các lệnh Git thường gặp

Pathspec được nhiều lệnh dùng để giới hạn phạm vi. Dấu `--` thường đặt ngay trước pathspec để phân tách rõ các tùy chọn hoặc revision.

| Mục tiêu | Lệnh ví dụ |
|---|---|
| Stage một tệp | `git add -- src/app.js` |
| Stage thư mục | `git add -- src/api/` |
| Stage mọi file `.js` theo glob | `git add -- ':(glob)**/*.js'` |
| Stage và loại thư mục generated | `git add -A -- ':(top)src' ':(exclude,top)src/generated'` |
| Xem diff của một tệp | `git diff -- src/app.js` |
| Xem diff staged của một thư mục | `git diff --cached -- src/api/` |
| Bỏ stage một tệp | `git restore --staged -- src/app.js` |
| Khôi phục tệp từ HEAD | `git restore --source=HEAD --worktree -- src/app.js` |
| Xóa và stage việc xóa | `git rm -- src/old.js` |
| Xem lịch sử của tệp | `git log --oneline -- src/app.js` |
| Liệt kê tệp tracked theo pattern | `git ls-files -- ':(glob)docs/**/*.md'` |

### 5.1. Với `git add`

`git add` cập nhật index theo pathspec:

```bash
git add -- ':(top,glob)src/**/*.js'
```

Chỉ các đường dẫn khớp pattern được xét. Sau đó dùng:

```bash
git diff --cached --name-status
```

để kiểm tra tập tệp đã stage.

### 5.2. Với `git restore`

Pathspec xác định đường dẫn cần khôi phục. Ví dụ bỏ stage một nhóm file:

```bash
git restore --staged -- ':(glob)src/**/*.js'
```

Khôi phục nội dung working tree từ commit HEAD:

```bash
git restore --source=HEAD --worktree -- ':(top,glob)src/**/*.js'
```

Lệnh thứ hai có thể ghi đè thay đổi chưa stage của các đường dẫn khớp. Hãy xem `git diff` hoặc sao lưu nội dung trước khi chạy.

### 5.3. Với `git reset`

Để bỏ stage một đường dẫn theo cú pháp cũ:

```bash
git reset HEAD -- src/app.js
```

Pathspec sau `--` xác định phần index cần cập nhật. Khi chỉ reset pathspec, Git không di chuyển branch như `git reset --hard <commit>`; tuy nhiên, luôn đọc kỹ lệnh và đối số trước khi chạy vì `reset` có nhiều chế độ.

### 5.4. Với `git log` và `git diff`

Khi lệnh nhận cả revision lẫn đường dẫn, dấu `--` giúp phân tách:

```bash
git log main -- src/api/
git diff main...feature -- src/api/
```

Trong ví dụ thứ hai, `main...feature` là phạm vi revision của diff; `src/api/` là pathspec. Không có `--`, một tên có thể bị phân giải nhầm trong phần revision/path tùy lệnh.

## 6. Xử lý tên đường dẫn đặc biệt

Tên tệp trong repository có thể chứa dấu cách, wildcard, dấu nháy hoặc bắt đầu bằng dấu `-`. Hãy kết hợp quote, pathspec magic và `--` phù hợp.

| Tên tệp | Cách chọn rõ ràng |
|---|---|
| `meeting notes.md` | `git add -- 'meeting notes.md'` |
| `-draft.txt` | `git add -- -draft.txt` |
| `[draft].txt` | `git add -- ':(literal)[draft].txt'` |
| `report*.txt` (dấu `*` là ký tự thật) | `git add -- ':(literal)report*.txt'` |
| `src/file.js` từ mọi thư mục con | `git add -- ':(top)src/file.js'` |

### 6.1. Dùng `./` để làm rõ đường dẫn tương đối

Nếu một pathspec có vẻ nhập nhằng hoặc bắt đầu bằng ký tự đặc biệt, có thể ghi `./`:

```bash
git add -- ./-draft.txt
```

Tuy nhiên, `./` không thay thế cho `--` trong mọi trường hợp. Dùng cả hai là cách rõ ràng khi tên tệp bắt đầu bằng dấu gạch ngang.

### 6.2. Không dùng `eval` để xử lý tên tệp

Trong script, tránh tạo chuỗi kiểu:

```bash
eval "git add $user_path"
```

Nếu `user_path` chứa dấu nháy, dấu chấm phẩy hoặc cú pháp shell, lệnh có thể bị diễn giải ngoài ý muốn. Hãy truyền pathspec như một argument riêng, quote biến và đặt `--` trước danh sách đường dẫn:

```bash
git add -- "$user_path"
```

Nếu cần nhiều pathspec, dùng array trong Bash hoặc cơ chế argument list của ngôn ngữ script; không ghép thành một chuỗi lệnh shell.

## 7. Pathspec trong script và automation

### 7.1. Chọn pathspec từ gốc repository

Script có thể được gọi từ nhiều thư mục. Xác định root:

```bash
repo_root=$(git rev-parse --show-toplevel) || exit $?
```

Sau đó chuyển về root trước khi chạy lệnh:

```bash
cd "$repo_root" || exit $?
git diff --cached -- ':(top,glob)src/**/*.js'
```

Hoặc dùng magic `top` để không phụ thuộc thư mục hiện tại:

```bash
git diff --cached -- ':(top,glob)src/**/*.js'
```

### 7.2. Xử lý danh sách đường dẫn an toàn

Nếu lấy tên tệp từ Git, ưu tiên delimiter NUL:

```bash
git diff --name-only -z --cached
```

Tên tệp có thể chứa newline nên không nên dùng `while read` theo dòng thường hoặc command substitution để tách danh sách. Hãy dùng parser NUL-safe phù hợp với shell/ngôn ngữ. Khi truyền lại một đường dẫn cho Git, đặt `--` trước pathspec.

### 7.3. Pathspec và dữ liệu đầu vào không tin cậy

Pathspec có thể chọn nhiều tệp hơn dự kiến nếu chứa wildcard hoặc magic. Nếu đường dẫn đến từ người dùng và cần khớp đúng một tên, dùng literal pathspec:

```bash
git add -- ":(literal)$user_path"
```

Trong Bash, biến được quote để shell truyền một đối số duy nhất; magic `literal` yêu cầu Git không diễn giải wildcard trong phần tên. Nếu tên có thể bắt đầu bằng cú pháp magic, literal mode giúp giữ nguyên ý nghĩa đường dẫn.

`--` chỉ ngăn Git hiểu đối số tiếp theo là option. Nó không thay thế shell quoting, không ngăn shell expansion nếu pattern chưa được quote và không tự chống command injection nếu script dùng `eval`.

## 8. Các lỗi thường gặp

### 8.1. Git báo unknown option khi tên tệp bắt đầu bằng `-`

Nguyên nhân: đường dẫn bị phân tích như tùy chọn. Dùng:

```bash
git add -- -draft.txt
```

### 8.2. Git báo pathspec did not match any files

Nguyên nhân có thể gồm:

- Gõ sai đường dẫn hoặc sai chữ hoa/thường.
- Đang đứng ở thư mục con nên pathspec tương đối không còn đúng.
- Pattern không khớp theo quy tắc glob đang dùng.
- Tệp chưa tồn tại hoặc không thuộc phạm vi mà lệnh xét.
- Tệp bị ignore hoặc trạng thái của nó không phù hợp với thao tác.

Kiểm tra vị trí và đường dẫn:

```bash
git rev-parse --show-toplevel
git status --short
git ls-files -- ':(top)src/app.js'
```

Nếu muốn kiểm tra một tên literal có ký tự wildcard:

```bash
git ls-files -- ':(literal)src/[draft].js'
```

### 8.3. Wildcard chọn quá nhiều hoặc quá ít tệp

Hãy quote pattern để shell không mở rộng trước. Nếu cần quy tắc glob rõ ràng, dùng `:(glob)` và hiểu `*`, `?`, `**`. Chạy `git ls-files -- <pathspec>` hoặc `git status --short` để xem trước phạm vi trước khi dùng pathspec với lệnh thay đổi index.

### 8.4. Pathspec hoạt động khác khi chạy từ thư mục con

Đường dẫn thông thường phụ thuộc current working directory. Dùng `:(top)` hoặc `:/` khi muốn tính từ gốc repository.

### 8.5. Dùng `--` sai vị trí

Các tùy chọn cần đặt trước dấu phân cách:

```bash
git add -p -- src/app.js
```

Không đặt tùy chọn của lệnh sau `--` với kỳ vọng Git vẫn hiểu đó là option; sau dấu phân cách, đối số được xem là pathspec.

## 9. Quy trình chọn đường dẫn an toàn

Trước khi stage, xóa hoặc khôi phục nhiều tệp bằng pathspec, hãy thực hiện:

1. Xác nhận repository và thư mục hiện tại:

   ```bash
   git rev-parse --show-toplevel
   ```

2. Xác định rõ phạm vi: một tệp, một thư mục, toàn repository hay một pattern.
3. Nếu tên bắt đầu bằng `-`, đặt `--` trước pathspec.
4. Nếu pattern có wildcard, quote để Git nhận pattern nguyên vẹn.
5. Nếu cần đường dẫn từ root, dùng `:(top)` hoặc `:/`.
6. Nếu tên cần khớp literal, dùng `:(literal)`.
7. Nếu loại trừ thư mục, dùng pathspec dương kết hợp `:(exclude)`.
8. Xem trước tập đường dẫn bằng `git ls-files`, `git status` hoặc `git diff` với cùng pathspec.
9. Chạy lệnh thay đổi index/working tree.
10. Kiểm tra lại `git status --short` và `git diff --cached`.

Ví dụ muốn stage mọi file `.js` trong `src` nhưng bỏ mã sinh tự động:

```bash
git ls-files -- ':(top,glob)src/**/*.js'
git add -A -- ':(top,glob)src/**/*.js' ':(exclude,top)src/generated'
git diff --cached --name-status
```

Lệnh đầu giúp kiểm tra các đường dẫn tracked đang khớp. Nếu cần bao gồm cả tệp mới, `git status` cũng cần được xem xét vì `git ls-files` chỉ liệt kê tệp trong index. Sau khi stage, `git diff --cached --name-status` cho biết nội dung thay đổi thực tế đã được chọn.

## 10. Ghi nhớ

- Pathspec là cú pháp Git dùng để chọn một hoặc nhiều đường dẫn.
- Pathspec thông thường được tính tương đối với thư mục hiện tại; `:(top)` hoặc `:/` tính từ gốc repository.
- `--` kết thúc phần option/revision và bắt đầu danh sách pathspec; nó không phải một phần của tên tệp.
- Dùng `--` khi đường dẫn bắt đầu bằng `-` hoặc khi lệnh nhận cả revision và path.
- Quote wildcard để Git xử lý pattern thay vì shell mở rộng trước.
- `:(glob)` dùng glob-style matching; `**` hỗ trợ khớp qua nhiều cấp thư mục.
- `:(literal)` khớp tên literal; `:(icase)` không phân biệt hoa/thường; `:(exclude)` loại đường dẫn khỏi tập đã chọn; `:(attr:...)` chọn theo Git attributes.
- Pathspec dương kết hợp exclusion giúp chọn một thư mục nhưng bỏ thư mục con cụ thể.
- Trong script, truyền pathspec như argument riêng, quote biến, dùng parser NUL-safe cho tên tệp và tránh `eval`.
- Xem trước phạm vi trước khi chạy lệnh có thể thay đổi index hoặc working tree.

Khi một lệnh Git tác động sai tệp, nguyên nhân thường nằm ở cách pathspec được phân giải hoặc shell đã biến đổi đối số trước khi Git nhận chúng. Hãy phân tách option bằng `--`, chọn đúng chế độ pathspec và kiểm tra phạm vi trước khi thực hiện thao tác.

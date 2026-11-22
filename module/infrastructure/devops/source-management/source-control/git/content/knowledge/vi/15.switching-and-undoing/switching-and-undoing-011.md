# Xóa tệp chưa theo dõi bằng git clean và kiểm tra trước với -n

Trong quá trình phát triển, working tree thường xuất hiện các tệp Git chưa theo dõi (*untracked files*), chẳng hạn tệp log, kết quả build, tệp tạm hoặc dữ liệu thử nghiệm. Khi muốn dọn những tệp này, Git cung cấp lệnh `git clean`. Đây là lệnh xóa trực tiếp khỏi filesystem, vì vậy cần kiểm tra danh sách mục tiêu trước khi thực hiện.

Tùy chọn `-n` (*dry run*) cho phép xem trước những gì Git sẽ xóa mà không xóa thật. Quy trình an toàn thường bắt đầu bằng `git status`, tiếp theo là `git clean -n` hoặc `git clean -nd` để xem trước, rồi mới chạy lệnh có `-f` khi đã xác nhận đúng phạm vi.

## 1. Untracked file là gì?

Git phân biệt các tệp trong working tree theo trạng thái quản lý:

- **Tracked:** tệp đã được Git ghi nhận trong commit hoặc index. Tệp có thể đang sạch, đã sửa, đã stage hoặc bị xóa trong working tree.
- **Untracked:** tệp hiện có trong working tree nhưng chưa được Git theo dõi trong index/commit.
- **Ignored:** tệp không được Git theo dõi và khớp quy tắc ignore, thường khai báo trong `.gitignore`, `.git/info/exclude` hoặc cấu hình ignore toàn cục.

Ví dụ, sau khi chạy build, dự án có thể tạo `build/output.log`. Nếu tệp chưa được Git theo dõi và không bị ignore, `git status` thường hiển thị nó trong nhóm *Untracked files*. Nếu `build/` đã được khai báo trong `.gitignore`, tệp có thể không xuất hiện trong status thông thường và được coi là ignored.

`git clean` chủ yếu dùng để xóa untracked files và untracked directories. Theo mặc định, lệnh không xóa tệp tracked đã chỉnh sửa hoặc staged, và cũng bỏ qua các tệp bị ignore. Những nhóm này có thể được xử lý bằng các tùy chọn riêng, vì vậy phải hiểu bộ lọc trước khi chạy.

## 2. Kiểm tra trạng thái trước khi dọn dẹp

Trước tiên, xem trạng thái repository:

```bash
git status
```

Để xem trạng thái dạng ngắn, bao gồm tệp untracked và ignored:

```bash
git status --short --ignored
```

Ví dụ:

```text
 M src/App.java
?? notes/tmp-plan.txt
?? scratch/
!! build/
```

Ý nghĩa trong ví dụ:

- ` M src/App.java`: tệp tracked có thay đổi chưa stage.
- `?? notes/tmp-plan.txt`: tệp chưa được theo dõi.
- `?? scratch/`: thư mục chưa được theo dõi.
- `!! build/`: đường dẫn bị ignore.

Nếu cần thấy từng tệp bên trong thư mục untracked hoặc ignored, có thể yêu cầu Git hiển thị chi tiết hơn:

```bash
git status --short --untracked-files=all --ignored
```

Đọc trạng thái trước khi clean giúp tránh nhầm tệp công việc đang làm với dữ liệu có thể bỏ. Đặc biệt, không coi việc một tệp bị ignore là bằng chứng tệp đó không quan trọng: thư mục build có thể tái tạo được, nhưng file cấu hình local hoặc dữ liệu thử nghiệm có thể cần giữ lại.

## 3. Xem trước bằng git clean -n

Lệnh cơ bản:

```bash
git clean -n
```

`-n` là viết tắt của `--dry-run`. Git chỉ in các mục dự kiến xóa, thường với nội dung như:

```text
Would remove notes/tmp-plan.txt
```

Lệnh này không xóa tệp hoặc thư mục. Đây là bước kiểm tra quan trọng trước khi chạy lệnh clean thực tế.

### Xem trước cả thư mục untracked với -d

Mặc định, `git clean` không đi vào xóa thư mục untracked. Dùng `-d` để xem xét các thư mục chưa được theo dõi cùng nội dung bên trong:

```bash
git clean -nd
```

Ví dụ:

```text
Would remove notes/tmp-plan.txt
Would remove scratch/
```

`-d` có ý nghĩa khi muốn dọn thư mục tạm hoặc thư mục sinh ra trong quá trình thử nghiệm. Nếu chỉ dùng `git clean -n`, một thư mục untracked có thể không được liệt kê như một mục sẽ xóa; vì vậy hãy thêm `-d` khi muốn xem xét cả thư mục.

## 4. Xóa sau khi đã kiểm tra danh sách

Sau khi xác nhận danh sách từ dry run, có thể chạy:

```bash
git clean -f
```

`-f` (*force*) cho phép Git thực hiện việc xóa. Nếu cần xóa cả thư mục untracked:

```bash
git clean -fd
```

Trong nhiều cấu hình, Git yêu cầu `-f` vì `clean.requireForce` mặc định được bật. Tùy chọn `-n` và `-i` là chế độ xem trước hoặc tương tác nên không thực hiện xóa ngay; với thao tác xóa tự động, hãy dùng `-f` sau khi đã xem trước.

Một chu trình thường dùng:

```bash
# 1. Xem trạng thái repository.
git status --short --ignored

# 2. Xem trước untracked files và directories.
git clean -nd

# 3. Chỉ sau khi xác nhận danh sách, mới xóa.
git clean -fd

# 4. Kiểm tra lại.
git status
```

Không nên bỏ qua bước dry run trong repository có dữ liệu local quan trọng hoặc khi bạn chưa hiểu các quy tắc ignore của dự án.

## 5. Phân biệt -x và -X khi xử lý ignored files

Mặc định, `git clean` tôn trọng các quy tắc ignore. Có hai tùy chọn thay đổi phạm vi:

| Tùy chọn | Phạm vi |
|---|---|
| Không dùng `-x` hoặc `-X` | Xóa untracked không bị ignore; bỏ qua ignored files |
| `-x` | Bỏ qua quy tắc ignore, xem cả ignored files như mục tiêu có thể xóa |
| `-X` | Chỉ xóa các mục bị ignore; giữ untracked files không bị ignore |

### Xem trước cả ignored files với -x

```bash
git clean -ndx
```

Lệnh này cho xem trước các untracked files/directories, bao gồm cả những mục bị ignore. Nếu thực sự muốn xóa phạm vi đó:

```bash
git clean -fdx
```

Đây là thao tác có phạm vi rộng. Ví dụ, nếu `.gitignore` bỏ qua `.env.local`, `build/` và `coverage/`, `-x` có thể đưa những mục này vào danh sách xóa. Tệp `.env.local` có thể chứa cấu hình riêng không thể tái tạo; đừng chạy lệnh này chỉ vì muốn dọn output build.

### Chỉ xem trước ignored files với -X

```bash
git clean -ndX
```

`-X` viết hoa, chỉ chọn những mục bị ignore. Sau khi xem trước, nếu đúng mục tiêu cần dọn:

```bash
git clean -fdX
```

Tùy chọn này hữu ích khi muốn xóa output build đã được ignore mà vẫn giữ các tệp untracked khác, chẳng hạn ghi chú hoặc tệp thử nghiệm chưa được ignore.

## 6. Giới hạn phạm vi bằng pathspec và loại trừ bằng -e

Có thể giới hạn lệnh clean vào một đường dẫn cụ thể. Ví dụ, chỉ xem trước mục untracked trong thư mục `scratch`:

```bash
git clean -nd -- scratch/
```

Sau khi kiểm tra, nếu muốn xóa đúng phạm vi đó:

```bash
git clean -fd -- scratch/
```

Dấu `--` phân cách tùy chọn với pathspec. Điều này giúp Git hiểu phần sau là đường dẫn cần lọc.

Nếu muốn dọn hầu hết untracked files nhưng giữ lại một pattern, dùng `-e` để thêm quy tắc loại trừ:

```bash
# Xem trước, giữ lại các tệp .local.
git clean -nd -e '*.local'
```

`-e <pattern>` bổ sung pattern vào danh sách exclude cho lần clean đó. Có thể dùng nhiều lần `-e` khi cần giữ nhiều nhóm:

```bash
git clean -nd -e '*.local' -e 'scratch/keep/'
```

Hãy kiểm tra output dry run để xác nhận pattern có loại trừ đúng mục cần giữ. Pattern ignore/exclude có quy tắc khớp đường dẫn riêng; nếu kết quả không như mong đợi, thu hẹp pathspec hoặc điều chỉnh pattern rồi chạy lại dry run.

## 7. Dùng chế độ tương tác -i

Khi danh sách mục tiêu có nhiều loại tệp và bạn muốn chọn từng mục, có thể dùng:

```bash
git clean -i
```

Chế độ tương tác hiển thị danh sách và menu thao tác. Tùy phiên bản Git, các lựa chọn thường gồm:

- `clean`: thực hiện xóa các mục đã chọn.
- `filter by pattern`: lọc danh sách theo pattern.
- `select by numbers`: chọn mục theo số thứ tự.
- `ask each`: hỏi xác nhận cho từng mục.
- `quit`: thoát mà không tiếp tục.
- `help`: xem trợ giúp của menu.

`-i` phù hợp khi cần rà soát thủ công một danh sách lớn. Tuy vậy, hãy đọc từng đường dẫn và xác nhận trước khi chọn hành động `clean`.

## 8. Những trường hợp đặc biệt cần chú ý

### Tệp tracked không bị git clean xóa

Nếu `src/App.java` đã được Git theo dõi và có chỉnh sửa chưa commit, `git clean -fd` không phải lệnh hoàn tác thay đổi đó. `git clean` nhắm đến mục untracked; không dùng nó để xử lý thay đổi tracked. Hãy xem `git status` và chọn công cụ phù hợp với trạng thái của tệp.

### Thư mục chứa repository Git lồng nhau

Git thận trọng với thư mục untracked mà bên trong là một repository Git khác. `git clean -fd` thông thường sẽ không xóa một repository lồng nhau như vậy. Cần thêm một mức force (`-ff`) để cho phép xóa các thư mục repository lồng nhau:

```bash
git clean -ndff
```

Chỉ dùng lệnh xóa tương ứng sau khi đã xem kỹ danh sách. Repository lồng nhau có thể chứa lịch sử và công việc độc lập; xóa cả thư mục sẽ xóa dữ liệu repository đó khỏi filesystem.

### Tệp bị ignore có thể là dữ liệu cần giữ

Các thư mục như `build/`, `dist/` hoặc `coverage/` thường có thể tạo lại. Nhưng `.env`, file chứng thư, database local hoặc dữ liệu test có thể bị ignore vì không nên commit, chứ không phải vì có thể xóa. Kiểm tra nguồn quy tắc ignore trước khi dùng `-x` hoặc `-X`:

```bash
git check-ignore -v .env.local
```

Lệnh trên cho biết pattern và file cấu hình đã khiến đường dẫn bị ignore (nếu có quy tắc khớp).

### git clean không có thao tác undo riêng

Các tệp bị `git clean` xóa không được đưa vào reflog hay một commit mới. Nếu dữ liệu chưa được sao lưu hoặc lưu ở nơi khác, Git thường không thể khôi phục nội dung đó. Dry run, pathspec hẹp và bản sao lưu là những biện pháp kiểm soát trước khi xóa.

## 9. Quy trình dọn dẹp an toàn

Giả sử bạn muốn xóa thư mục `scratch/` và các tệp tạm chưa theo dõi, nhưng giữ ignored config và mọi thay đổi source code.

```bash
# Xem mọi thay đổi, kể cả ignored files.
git status --short --ignored

# Xem trước untracked files và directories, vẫn tôn trọng ignore rules.
git clean -nd

# Nếu muốn chỉ dọn scratch, giới hạn bằng pathspec.
git clean -nd -- scratch/

# Xác nhận lại danh sách rồi mới thực hiện.
git clean -fd -- scratch/

# Kiểm tra trạng thái sau khi dọn.
git status --short --ignored
```

Nếu cần dọn output bị ignore, thực hiện một lượt dry run riêng:

```bash
git clean -ndX
```

Đọc kỹ danh sách, xác nhận các tệp đó có thể tái tạo hoặc đã được sao lưu, rồi mới cân nhắc:

```bash
git clean -fdX
```

Không chuyển từ `-n` sang `-f` một cách máy móc. Hãy giữ nguyên cùng các bộ lọc và pathspec giữa bước xem trước và bước xóa để phạm vi thực tế đúng với điều bạn đã duyệt.

## 10. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| `git clean -n` xóa tệp ngay | `-n` chỉ mô phỏng và in những mục dự kiến xóa |
| `git clean` mặc định xóa mọi tệp không có trong commit | Mặc định nó tôn trọng ignore rules và không xóa ignored files |
| `git clean -d` xóa mọi thư mục trong dự án | Nó nhắm đến thư mục untracked; thư mục chứa repository Git lồng nhau cần mức force bổ sung |
| `-x` và `-X` giống nhau | `-x` bao gồm ignored files; `-X` chỉ chọn ignored files |
| `git clean` hoàn tác thay đổi source code | Nó không xóa thay đổi của tệp tracked; cần dùng thao tác khác cho các trạng thái đó |
| Có thể khôi phục bằng reflog sau khi clean | Reflog theo dõi vị trí ref/HEAD, không lưu bản sao tệp untracked đã bị xóa |

## 11. Ghi nhớ

`git clean` là công cụ dọn tệp chưa được theo dõi. Dùng `-n` để xem trước, thêm `-d` khi cần xét cả thư mục, và chỉ thêm `-f` sau khi đã xác nhận danh sách. Mặc định Git giữ lại ignored files; `-x` mở rộng phạm vi sang cả ignored files, còn `-X` chỉ chọn các mục bị ignore. `-e` và pathspec giúp thu hẹp phạm vi.

Trước khi xóa, hãy kiểm tra `git status --short --ignored`, chạy dry run với đúng các tùy chọn sẽ dùng khi xóa và đọc từng đường dẫn. `git clean` xóa dữ liệu khỏi filesystem và không có cơ chế hoàn tác riêng, vì vậy kiểm tra trước là bước cần thiết để bảo vệ công việc local.

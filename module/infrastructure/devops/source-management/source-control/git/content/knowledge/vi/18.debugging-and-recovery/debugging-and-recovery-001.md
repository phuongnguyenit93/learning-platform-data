# Lập bản sao bảo vệ và ghi nhận trạng thái trước khi cứu dữ liệu

Khi Git gặp sự cố như mất commit, branch bị di chuyển nhầm, rebase dang dở, working tree bị ghi đè hoặc tệp vô tình bị xóa, phản xạ đầu tiên thường là chạy một lệnh để sửa ngay. Tuy nhiên, thao tác phục hồi có thể làm thay đổi thêm dữ liệu và khiến việc tìm lại trạng thái ban đầu khó hơn.

Trước khi dùng `reset`, `clean`, `restore`, `checkout`, `rebase`, `gc` hoặc bất kỳ lệnh nào có thể ghi đè hay loại bỏ dữ liệu, hãy **dừng thao tác ghi, ghi nhận trạng thái hiện tại và tạo một bản sao bảo vệ nằm ngoài repository đang gặp sự cố**.

Một bản sao bảo vệ đầy đủ cần giữ cả working tree, staging area, tệp mới, tệp bị ignore và dữ liệu Git trong `.git` (hoặc Git directory thực tế). Các bản ghi như `git status`, `git diff`, `git reflog` và đồ thị commit giúp ta hiểu trạng thái trước khi phục hồi. Chúng bổ sung cho bản sao, không thay thế bản sao.

## 1. Vì sao phải bảo vệ dữ liệu trước khi phục hồi?

Git lưu lịch sử commit và các ref trong repository, nhưng công việc đang làm có thể chưa nằm trong commit. Một repository đang gặp sự cố có thể chứa nhiều loại dữ liệu:

| Thành phần | Ví dụ | Có thể mất khi nào? |
|---|---|---|
| Commit đã tạo | Commit mới, merge commit, commit đang ở branch riêng | Khi branch/ref bị di chuyển hoặc xóa, đối tượng có thể trở nên khó tìm; về sau có thể bị garbage collection thu hồi nếu không còn được tham chiếu. |
| Branch và tag | `main`, `feature/payment`, `v1.2.0` | Khi xóa hoặc cập nhật nhầm ref. |
| Thay đổi đã stage | Tệp đã chạy `git add` nhưng chưa commit | Khi reset index, checkout hoặc thao tác thay thế nội dung. |
| Thay đổi chưa stage | Tệp tracked đã sửa trong working tree | Khi restore, checkout, reset hoặc ghi đè tệp. |
| Tệp untracked | Tệp mới chưa được `git add` | Khi chạy `git clean` hoặc thao tác dọn thư mục. |
| Tệp ignored | `.env`, file cấu hình local, dữ liệu build hoặc tệp IDE | Khi chạy `git clean -x`, xóa thư mục hoặc công cụ dọn dẹp. |
| Reflog và metadata Git | Dấu vết di chuyển HEAD, ref, index và cấu hình repository | Khi xóa hoặc thay thế Git directory, hoặc khi dữ liệu cũ hết thời gian lưu và bị garbage collection. |

Một lệnh có thể chỉ tác động tới một phần dữ liệu. Ví dụ, `git reset --hard` cập nhật HEAD, index và working tree theo commit đích; `git clean` xóa tệp untracked; `git clean -x` còn có thể xóa tệp ignored. Nếu chạy liên tiếp nhiều lệnh mà chưa kiểm tra, ta có thể mất nhiều loại dữ liệu cùng lúc.

## 2. Quy tắc đầu tiên: dừng ghi và không làm tình hình phức tạp hơn

Khi phát hiện sự cố:

1. Dừng các lệnh đang sửa lịch sử hoặc dọn dữ liệu nếu có thể làm điều đó an toàn.
2. Không chạy thêm `reset --hard`, `clean -fd`, `clean -fdx`, `rebase --abort`, `gc` hoặc lệnh xóa ref theo phỏng đoán.
3. Không tạo commit, stash, branch hoặc tag mới chỉ để thử nghiệm trước khi đã ghi nhận và sao lưu trạng thái hiện tại.
4. Không đóng hoặc xóa thư mục repository nếu chưa biết dữ liệu nào còn cần giữ.
5. Nếu IDE, build tool hoặc tiến trình khác vẫn tự động ghi vào repository, tạm dừng chúng trước khi chụp bản sao nếu có thể.

Mục tiêu là giữ nguyên hiện trạng để có thể điều tra. Mỗi thao tác ghi thêm có thể làm thay đổi index, working tree, reflog hoặc refs, khiến việc phân biệt dữ liệu cũ và mới khó hơn.

## 3. Ghi nhận trạng thái Git bằng các lệnh chỉ đọc

Trước tiên, xác định repository và trạng thái đang có. Các lệnh dưới đây chủ yếu dùng để quan sát, không thay đổi nội dung làm việc.

### 3.1. Xác định repository, branch và commit hiện tại

```bash
git rev-parse --show-toplevel
git rev-parse --show-prefix
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short --branch
```

Các lệnh cho biết:

- Đường dẫn thư mục gốc của working tree.
- Vị trí hiện tại so với repository root.
- Tên branch đang checkout; nếu đang ở detached HEAD, lệnh branch có thể trả về `HEAD`.
- Object ID của commit mà HEAD đang trỏ tới.
- Tóm tắt trạng thái staged, unstaged và untracked.

Ghi lại cả trường hợp detached HEAD. Đừng tự chuyển branch chỉ để làm tên branch xuất hiện, vì việc chuyển branch có thể thay đổi working tree và gây xung đột với thay đổi hiện tại.

### 3.2. Ghi nhận trạng thái chi tiết

```bash
git status --porcelain=v2 --branch --untracked-files=all
```

Định dạng porcelain v2 phù hợp để lưu lại và so sánh vì nó có cấu trúc ổn định hơn định dạng hiển thị thông thường. Tùy chọn `--untracked-files=all` liệt kê từng tệp untracked thay vì chỉ hiển thị thư mục cha.

Nếu cần xem cả ignored files:

```bash
git status --short --branch --ignored
```

Ignored files có thể chứa dữ liệu local quan trọng như cấu hình môi trường hoặc file chưa được thêm vào Git. Hãy kiểm tra danh sách này trước khi thực hiện bất kỳ thao tác dọn dẹp nào.

### 3.3. Ghi nhận thay đổi staged và unstaged

```bash
# Thay đổi tracked chưa stage
git diff --binary

# Thay đổi đã stage
git diff --cached --binary

# Thống kê thay đổi
git diff --stat
git diff --cached --stat
```

`git diff` không hiển thị nội dung tệp untracked. `git diff --cached` thể hiện nội dung đang ở staging area. Hai bản diff này giúp ghi nhận các thay đổi tracked chưa được commit.

Với tệp untracked và ignored, cần ghi nhận danh sách riêng:

```bash
git ls-files --others --exclude-standard
git ls-files --others --ignored --exclude-standard
```

Danh sách không chứa nội dung tệp. Vì vậy, nếu muốn bảo vệ tệp mới hoặc tệp ignored, phải sao chép chính các tệp đó trong bản sao đầy đủ.

### 3.4. Ghi nhận lịch sử và refs

```bash
# Đồ thị commit của các ref đang có
git log --graph --oneline --decorate --all -n 100

# Các branch local và remote-tracking branch
git branch -avv

# Các ref và object ID
git show-ref --head

# Dấu vết di chuyển HEAD và các ref
git reflog --all --date=iso
```

`git reflog` đặc biệt hữu ích khi branch hoặc HEAD vừa bị di chuyển nhầm. Reflog có thể giúp tìm commit trước thao tác sai, nhưng không phải backup lâu dài: entry có thể hết hạn và object không còn được tham chiếu có thể bị garbage collection thu hồi.

Nếu sự cố liên quan tới remote, có thể ghi nhận:

```bash
git remote -v
git config --get-regexp '^branch\.'
```

URL remote đôi khi chứa thông tin xác thực hoặc token. Không chia sẻ nguyên văn log có URL nhạy cảm; hãy che thông tin bí mật trước khi gửi cho người khác.

## 4. Tạo bản sao bảo vệ đầy đủ

### 4.1. Vì sao cần sao chép toàn bộ working copy?

Một bản sao thư mục repository đầy đủ thường bảo vệ được:

- Các tệp tracked hiện tại, kể cả thay đổi staged và unstaged.
- Các tệp untracked chưa được Git quản lý.
- Các tệp ignored, nếu thao tác sao chép có bao gồm chúng.
- Git directory chứa object database, refs, reflogs, index và metadata khác.

Điều này quan trọng vì chỉ clone repository hoặc tạo Git bundle không lưu toàn bộ trạng thái chưa commit.

**Đặt bản sao ở ngoài repository gốc.** Nếu đặt thư mục backup bên trong working tree, bản sao có thể bị Git nhìn thấy như một lượng lớn tệp untracked, làm nhiễu trạng thái và có nguy cơ bị lệnh dọn dẹp xóa.

Nếu sự cố có thể liên quan tới ổ đĩa hoặc thiết bị lưu trữ, hãy đặt bản sao trên một ổ đĩa hoặc vị trí lưu trữ độc lập. Một thư mục nằm ngoài repository nhưng vẫn trên cùng ổ đĩa chỉ bảo vệ trước một số thao tác nhầm, không bảo vệ trước hỏng ổ đĩa. Bản sao có thể chứa `.env`, khóa hoặc dữ liệu nội bộ, nên cần giới hạn quyền truy cập.

### 4.2. Sao chép trên Windows bằng PowerShell và Robocopy

Trong Windows, có thể dùng Robocopy để sao chép cả thư mục ẩn như `.git`. Chạy từ một cửa sổ PowerShell đang ở trong repository:

```powershell
$repoRoot = (git rev-parse --show-toplevel).Trim()
$parentDir = Split-Path -Parent $repoRoot
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupDir = Join-Path $parentDir ("git-recovery-" + $stamp)

New-Item -ItemType Directory -Path $backupDir | Out-Null
robocopy $repoRoot $backupDir /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XJ
if ($LASTEXITCODE -ge 8) {
    throw "Robocopy failed with exit code $LASTEXITCODE"
}
```

Giải thích:

- `$repoRoot` lấy đường dẫn working tree root từ Git.
- `$backupDir` tạo thư mục backup cùng cấp với repository gốc, nằm ngoài working tree.
- `/E` sao chép cả thư mục con rỗng.
- `/COPY:DAT` và `/DCOPY:DAT` giữ dữ liệu, thuộc tính và thời gian.
- `/R:1 /W:1` giới hạn số lần thử lại khi gặp lỗi.
- `/XJ` tránh đi theo junction, hạn chế sao chép vòng lặp hoặc thư mục ngoài ý muốn.
- Robocopy dùng mã thoát từ 0 đến 7 cho các trạng thái hoàn tất hoặc có khác biệt; mã từ 8 trở lên báo lỗi sao chép.

Không dùng `/MIR` trong bước bảo vệ ban đầu. `/MIR` có thể xóa tệp ở đích nếu chúng không có trong nguồn; một lệnh sao chép backup nên tránh hành vi xóa ở thư mục đích.

Sau khi sao chép, kiểm tra thư mục backup có cả nội dung dự án và Git metadata. Nếu `.git` là thư mục, xác nhận nó xuất hiện trong bản sao. Nếu `.git` là một tệp trỏ tới Git directory khác, cần xử lý trường hợp linked worktree ở phần tiếp theo.

### 4.3. Lưu ý với linked worktree và submodule

Không phải working tree nào cũng chứa một thư mục `.git`. Với linked worktree, `.git` có thể là một tệp trỏ tới Git directory nằm ở vị trí khác; nhiều worktree còn dùng chung Git common directory.

Kiểm tra:

```bash
git rev-parse --absolute-git-dir
git rev-parse --git-common-dir
```

Nếu các đường dẫn này nằm ngoài thư mục working tree vừa sao chép, bản sao working tree chưa đủ để bảo vệ metadata Git. Hãy sao chép thêm Git directory thực tế và common directory tới vị trí an toàn, giữ nguyên cấu trúc đường dẫn hoặc ghi nhận rõ quan hệ trỏ tới chúng. Không xóa hoặc di chuyển các thư mục này trước khi xác minh bản sao.

Submodule là repository riêng được tham chiếu từ repository cha. Sao chép working tree cha có thể sao chép thư mục nội dung submodule, nhưng cần kiểm tra Git metadata của từng submodule và trạng thái thay đổi bên trong chúng. Nếu submodule đang có thay đổi chưa commit, hãy sao lưu repository submodule tương ứng, không chỉ dựa vào commit pointer mà repository cha ghi nhận.

## 5. Git bundle: bản sao bổ sung cho commit đã tham chiếu

Sau khi đã bảo vệ working copy, có thể tạo thêm Git bundle để lưu các commit và refs hiện có. Ví dụ trong PowerShell, dùng thư mục backup đã tạo ở bước trước:

```powershell
$bundlePath = Join-Path $backupDir 'repository-recovery.bundle'
git bundle create $bundlePath --all
if ($LASTEXITCODE -ne 0) {
    throw "git bundle create failed with exit code $LASTEXITCODE"
}
git bundle verify $bundlePath
```

Git bundle đóng gói các đối tượng cần thiết để tái tạo các ref được đưa vào bundle. Nó hữu ích để lưu hoặc chuyển giao lịch sử commit mà không cần truy cập remote.

Tuy nhiên, bundle **không thay thế bản sao working copy đầy đủ**:

- Không chứa thay đổi chưa commit trong working tree.
- Không lưu trạng thái staging area như một index có thể khôi phục nguyên trạng.
- Không tự chứa nội dung tệp untracked hoặc ignored chưa được commit.
- Không bảo toàn reflog như một bản sao nguyên trạng của Git directory.
- Không nhất thiết chứa commit chỉ còn được tìm thấy qua reflog nếu commit đó không thuộc các ref được đóng gói.

Vì vậy, bundle phù hợp để bảo vệ lịch sử commit đã tham chiếu, còn bản sao đầy đủ bảo vệ trạng thái thực tế của working copy và Git metadata.

## 6. Ghi lại bằng chứng vào thư mục backup

Sau khi tạo thư mục backup bên ngoài repository, lưu các kết quả chẩn đoán vào đó. Ví dụ PowerShell:

```powershell
git status --porcelain=v2 --branch --untracked-files=all |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'status.txt')

git status --short --branch --ignored |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'status-with-ignored.txt')

git rev-parse --show-toplevel |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'repository-root.txt')

git rev-parse HEAD |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'head.txt')

git branch -avv |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'branches.txt')

git show-ref --head |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'refs.txt')

git log --graph --oneline --decorate --all -n 100 |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'commit-graph.txt')

git reflog --all --date=iso |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'reflog.txt')

git diff --binary |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'unstaged.patch')

git diff --cached --binary |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'staged.patch')

git ls-files --others --exclude-standard |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'untracked-files.txt')

git ls-files --others --ignored --exclude-standard |
    Set-Content -Encoding utf8 (Join-Path $backupDir 'ignored-files.txt')
```

Các file patch là bản ghi bổ sung cho thay đổi tracked; chúng không bao gồm nội dung untracked/ignored. Bản sao đầy đủ vẫn là nguồn bảo vệ chính.

Nếu ghi nhận `git remote -v` hoặc cấu hình Git, hãy xem lại URL và xóa thông tin xác thực trước khi chia sẻ. Không đưa token, mật khẩu, khóa riêng hoặc nội dung `.env` vào báo cáo công khai.

## 7. Kiểm tra bản sao trước khi bắt đầu cứu dữ liệu

Một bản sao chỉ hữu ích khi ta biết nó thực sự tồn tại và có các thành phần cần thiết.

Checklist kiểm tra:

- Thư mục backup nằm ngoài repository gốc.
- Các tệp dự án quan trọng có trong bản sao.
- Tệp untracked và ignored cần giữ có trong bản sao.
- Git directory hoặc Git common directory thực tế đã được sao chép.
- Nếu có submodule hoặc linked worktree, metadata tương ứng đã được bảo vệ riêng.
- Các file ghi nhận trạng thái như `status.txt`, `head.txt`, `reflog.txt` đã được tạo.
- Git bundle, nếu tạo, đã qua `git bundle verify`.
- Không có lỗi sao chép hoặc file bị bỏ qua ngoài dự kiến.

Nếu sự cố nghiêm trọng, nên giữ nguyên bản sao đầu tiên và thực hiện thử nghiệm phục hồi trên một bản sao thứ hai. Nhờ vậy, nếu một phương án phục hồi làm thay đổi thêm dữ liệu, ta vẫn có bản gốc để quay lại.

## 8. Sau khi bảo vệ dữ liệu mới chọn phương án phục hồi

Khi đã có bản sao và bản ghi trạng thái, bắt đầu phân tích nguyên nhân. Chọn thao tác dựa trên loại dữ liệu cần tìm lại.

| Tình huống | Dữ liệu cần tìm | Hướng điều tra ban đầu |
|---|---|---|
| Branch bị xóa hoặc di chuyển nhầm | Commit cũ mà branch từng trỏ tới | `git reflog --all`, `git log --all`, `git show <commit>` |
| HEAD bị reset nhầm | Commit trước thao tác reset | `git reflog`, `git rev-parse`, `git show` |
| Commit bị mất khỏi branch | Object commit còn tồn tại nhưng không còn ref | Reflog, `git fsck --full --no-reflogs --unreachable` sau khi đã sao lưu |
| Tệp tracked bị ghi đè | Nội dung trong commit, index hoặc bản backup | `git show <commit>:<path>`, `git diff`, so sánh bản sao |
| Tệp untracked bị xóa | Nội dung không có trong Git object database | Bản sao đầy đủ, backup hệ điều hành hoặc công cụ khôi phục file |
| Tệp ignored bị xóa | Nội dung local không được Git theo dõi | Bản sao đầy đủ hoặc backup hệ điều hành |
| Rebase/merge đang dở | Trạng thái index, working tree và sequencer metadata | `git status`, metadata Git trong bản sao, các ref và reflog |

Không phải dữ liệu nào cũng có thể khôi phục bằng Git. Tệp untracked hoặc ignored chưa từng được commit có thể không tồn tại trong object database. Nếu chúng bị xóa và không có bản sao khác, cần xem xét backup của hệ điều hành hoặc công cụ khôi phục file; Git không thể tái tạo nội dung mà nó chưa từng lưu.

### 8.1. Tìm commit cũ bằng reflog

Sau khi backup, có thể xem:

```bash
git reflog --all --date=iso
```

Tìm entry ngay trước thao tác gây sự cố, sau đó kiểm tra commit:

```bash
git show --stat <commit-id>
git log --oneline --decorate -n 20 <commit-id>
```

Chỉ khi đã xác định đúng commit mới tạo branch cứu hộ để giữ ref:

```bash
git branch rescue/recovered-state <commit-id>
```

Branch cứu hộ giữ commit không bị mất dấu do ref khác di chuyển. Trước khi tạo, hãy chắc chắn tên branch chưa tồn tại và commit đúng là trạng thái cần cứu.

### 8.2. Tìm object không còn được tham chiếu

Nếu reflog không còn entry phù hợp, sau khi đã tạo bản sao đầy đủ có thể kiểm tra object không còn được tham chiếu:

```bash
git fsck --full --no-reflogs --unreachable
```

Nếu thấy object kiểu commit, kiểm tra nội dung:

```bash
git show --stat <object-id>
git show --no-patch --pretty=fuller <object-id>
```

Không vội chạy `git gc`, `git prune` hoặc lệnh dọn object. Những lệnh đó có thể loại bỏ chính các object đang cần tìm. Khi tìm được commit đúng, tạo ref cứu hộ như branch hoặc tag để giữ nó.

### 8.3. Khôi phục tệp tracked từ commit

Nếu tệp tracked bị thay đổi hoặc xóa, có thể xem phiên bản trong commit đã biết:

```bash
git show <commit-id>:path/to/file
```

Lệnh trên hiển thị nội dung tệp tại commit. Hãy lưu nội dung cần thiết vào vị trí phục hồi hoặc so sánh với bản sao trước khi dùng lệnh ghi đè như `git restore`. Đừng thay thế tệp đang có thay đổi khác khi chưa xác định chúng cần giữ hay không.

## 9. Vì sao không nên dùng một lệnh “cứu nhanh” trước khi backup?

| Lệnh | Tác động cần lưu ý |
|---|---|
| `git reset --hard <commit>` | Di chuyển HEAD/branch và làm index, working tree khớp commit đích; thay đổi tracked chưa commit có thể bị mất. |
| `git clean -fd` | Xóa tệp và thư mục untracked được chọn. |
| `git clean -fdx` | Có thể xóa cả tệp ignored như cấu hình local hoặc dữ liệu build. |
| `git restore <path>` | Có thể ghi đè nội dung working tree bằng phiên bản từ index hoặc nguồn được chỉ định. |
| `git restore --staged <path>` | Thay đổi trạng thái staging; nội dung staged có thể không còn ở index như trước. |
| `git rebase --abort` | Kết thúc phiên rebase và khôi phục trạng thái trước phiên rebase theo metadata Git; cần hiểu các thay đổi đang có. |
| `git gc` / `git prune` | Có thể dọn object không còn được tham chiếu, bao gồm object đang cần điều tra sau sự cố. |

Các lệnh này không phải lúc nào cũng nguy hiểm; chúng là công cụ hợp lệ khi đã hiểu trạng thái và mục tiêu. Vấn đề là chạy chúng trước khi biết dữ liệu nào cần bảo vệ.

## 10. Quy trình phục hồi mẫu

Giả sử một branch vừa bị reset nhầm và working tree còn một số tệp chưa commit. Quy trình có thể triển khai như sau:

1. **Dừng thao tác ghi:** không tiếp tục reset, clean, rebase hoặc checkout theo phỏng đoán.
2. **Ghi nhận hiện trạng:** lưu `status --porcelain=v2`, HEAD, branch, diff staged/unstaged, danh sách untracked/ignored, log và reflog.
3. **Sao chép toàn bộ working copy:** đặt backup bên ngoài repository; xác minh `.git` hoặc Git directory thực tế đã được bảo vệ.
4. **Tạo bản ghi lịch sử bổ sung:** có thể tạo Git bundle và xác minh nếu cần lưu commit đã tham chiếu.
5. **Phân tích nguyên nhân:** xác định thao tác gây lỗi, commit/ref cũ và loại dữ liệu cần phục hồi.
6. **Thử trên bản sao:** nếu có thể, tạo bản sao làm việc thứ hai và thực hiện phương án phục hồi ở đó.
7. **Kiểm tra kết quả:** so sánh tệp, branch, commit, staging và working tree với trạng thái mong muốn; chạy test phù hợp.
8. **Chỉ cập nhật repository chính khi đã xác nhận:** ghi rõ thao tác sẽ làm thay đổi dữ liệu nào và giữ bản sao gốc cho tới khi hoàn tất.

## 11. Ghi nhớ

- Trước khi cứu dữ liệu, hãy dừng thao tác ghi và ghi nhận trạng thái hiện tại.
- `git status --porcelain=v2 --branch --untracked-files=all` giúp lưu trạng thái tracked và untracked có cấu trúc.
- `git diff --binary` và `git diff --cached --binary` ghi lại thay đổi tracked chưa stage và đã stage.
- Danh sách untracked/ignored không chứa nội dung; phải sao chép chính các tệp cần giữ.
- Bản sao đầy đủ cần chứa working tree và Git metadata; linked worktree, Git common directory và submodule có thể nằm ở vị trí riêng.
- Git bundle bảo vệ commit/ref được đóng gói, nhưng không thay thế bản sao working copy, index, untracked, ignored hoặc reflog.
- Reflog hữu ích để tìm commit cũ, nhưng không phải backup lâu dài.
- Không chạy `reset --hard`, `clean`, `gc` hoặc `prune` theo phỏng đoán trước khi đã bảo vệ dữ liệu.
- Thử phục hồi trên bản sao thứ hai khi sự cố phức tạp; chỉ áp dụng lên repository chính sau khi đã xác nhận.

Khi xử lý sự cố Git, hãy coi trạng thái hiện tại là bằng chứng cần bảo toàn. Một bản sao đầy đủ cùng bản ghi trạng thái rõ ràng giúp ta điều tra có căn cứ, thử nhiều phương án và quay lại điểm xuất phát nếu một bước phục hồi không đạt kết quả mong muốn.

# Xem cấu hình hiệu lực bằng `git config --list --show-origin`

Git lấy cấu hình từ nhiều nơi: cấu hình toàn hệ thống, cấu hình người dùng, cấu hình riêng của repository, cấu hình riêng cho worktree và các tùy chọn truyền trực tiếp khi chạy lệnh. Vì vậy, khi `git commit`, `git pull` hoặc một thao tác khác có hành vi không như mong đợi, chỉ mở một file cấu hình thường chưa đủ để tìm nguyên nhân.

Lệnh `git config --list --show-origin` giúp liệt kê các mục cấu hình Git cùng nguồn đã cung cấp từng mục. Kết hợp với `--show-scope`, ta có thể thấy phạm vi cấu hình; kết hợp với `--get` hoặc `--get-all`, ta có thể truy vấn riêng một khóa. Đây là cách thực tế để tìm ra vì sao một giá trị đang được sử dụng và file nào cần chỉnh sửa.

## 1. Chạy lệnh xem toàn bộ cấu hình

Trong thư mục repository, chạy:

```bash
git config --list --show-origin
```

Lệnh hiển thị các mục cấu hình mà Git đọc được, kèm nguồn của từng mục. Ví dụ rút gọn:

```text
file:C:/Program Files/Git/etc/gitconfig    core.autocrlf=false
file:C:/Users/An/.gitconfig                user.name=An Nguyen
file:C:/Users/An/.gitconfig                init.defaultbranch=main
file:D:/work/app/.git/config               user.email=an@example.com
file:D:/work/app/.git/config               core.editor=code --wait
```

Đường dẫn và giá trị trong ví dụ chỉ minh họa. Trên Linux hoặc macOS, đường dẫn cấu hình hệ thống và người dùng sẽ khác.

Mỗi dòng giúp trả lời hai câu hỏi:

- Khóa cấu hình nào đang được khai báo?
- Khai báo đó đến từ file hoặc nguồn nào?

Điều này đặc biệt hữu ích khi cùng một khóa xuất hiện trong nhiều file. Chẳng hạn, `user.name` có thể được đặt ở global nhưng repository hiện tại lại có giá trị local ghi đè.

## 2. Xem cả nguồn gốc và phạm vi cấu hình

Để thấy rõ phạm vi, dùng thêm `--show-scope`:

```bash
git config --list --show-origin --show-scope
```

Ví dụ:

```text
system  file:C:/Program Files/Git/etc/gitconfig    core.autocrlf=false
global  file:C:/Users/An/.gitconfig                user.name=An Nguyen
global  file:C:/Users/An/.gitconfig                init.defaultbranch=main
local   file:D:/work/app/.git/config               user.email=an@example.com
local   file:D:/work/app/.git/config               core.editor=code --wait
command command line:                               core.pager=cat
```

`--show-origin` cho biết nguồn cụ thể; `--show-scope` cho biết phạm vi logic mà Git gán cho cấu hình. Origin thường là `file:/đường/dẫn`, nhưng một số thao tác có thể hiển thị nguồn như `command line`, `standard input` hoặc `blob:<object-id>`.

Các scope thường gặp:

| Scope | Phạm vi | Nơi cấu hình thường gặp |
|---|---|---|
| `system` | Áp dụng cho mọi người dùng hoặc repository trên máy theo cách cài Git. | File hệ thống, thường là `etc/gitconfig` trong thư mục cài Git hoặc `/etc/gitconfig`. |
| `global` | Áp dụng cho người dùng hiện tại trên nhiều repository. | `~/.gitconfig` hoặc `$XDG_CONFIG_HOME/git/config`. |
| `local` | Áp dụng cho một repository. | `.git/config` hoặc Git directory tương ứng. |
| `worktree` | Áp dụng riêng cho một linked worktree khi repository bật cấu hình worktree. | `config.worktree` trong Git directory của worktree. |
| `command` | Áp dụng cho lệnh đang chạy, có độ ưu tiên cao nhất trong các scope cấu hình thông thường. | `git -c key=value` hoặc các biến môi trường cấu hình dạng command scope. |

Không phải repository nào cũng có đủ các scope. Ví dụ, nếu chưa bật cấu hình riêng cho worktree, sẽ không có file `config.worktree` để đọc.

## 3. Thứ tự ưu tiên của các scope

Khi cùng một khóa đơn trị được khai báo ở nhiều scope, cấu hình đọc sau thường ghi đè cấu hình đọc trước. Thứ tự ưu tiên thông dụng từ thấp lên cao là:

```text
system
   ↓
global
   ↓
local
   ↓
worktree
   ↓
command
```

Ví dụ, giả sử:

```text
system: core.autocrlf=false
global: core.autocrlf=input
local:  core.autocrlf=true
```

Trong repository đó, giá trị local `true` là giá trị có hiệu lực cho khóa đơn trị `core.autocrlf`, vì nó có độ ưu tiên cao hơn các giá trị system và global.

Tuy nhiên, không nên hiểu rằng mọi khóa đều chỉ có một giá trị. Một số khóa là **multi-valued** và được phép lặp lại, ví dụ `remote.origin.fetch`. Với những khóa này, các giá trị có thể được cộng dồn thay vì chỉ một giá trị cuối cùng thay thế tất cả. Hành vi cụ thể còn phụ thuộc cách Git định nghĩa khóa đó.

Vì vậy, `--list` là công cụ xem toàn bộ khai báo, không phải lúc nào cũng là bản tóm tắt duy nhất của giá trị cuối cùng được dùng. Khi cần biết giá trị của một khóa cụ thể, hãy truy vấn riêng khóa đó.

## 4. Truy vấn một khóa và xem nguồn của nó

### 4.1. Xem một giá trị

Ví dụ xem tên tác giả:

```bash
git config --show-origin --show-scope --get user.name
```

Kết quả cho biết giá trị và nguồn đã cung cấp nó. Có thể kiểm tra các khóa khác tương tự:

```bash
git config --show-origin --show-scope --get user.email
git config --show-origin --show-scope --get core.editor
git config --show-origin --show-scope --get init.defaultBranch
```

Nếu lệnh không trả kết quả và báo không tìm thấy khóa, có thể khóa đó chưa được cấu hình trong các nguồn đang được đọc.

### 4.2. Xem tất cả giá trị của khóa nhiều giá trị

Với khóa có thể xuất hiện nhiều lần, dùng `--get-all`:

```bash
git config --show-origin --show-scope --get-all remote.origin.fetch
```

Ví dụ một remote có thể có nhiều refspec fetch. Nếu chỉ xem một dòng, ta có thể bỏ sót mapping khác đang được áp dụng.

### 4.3. Tìm một nhóm khóa

`--get-regexp` giúp tìm các khóa theo biểu thức chính quy:

```bash
git config --show-origin --show-scope --get-regexp '^core\.'
git config --show-origin --show-scope --get-regexp '^remote\.origin\.'
git config --show-origin --show-scope --get-regexp '^branch\.'
```

Các lệnh này hữu ích khi cần kiểm tra một nhóm thiết lập liên quan tới line ending, remote hoặc upstream của branch.

## 5. Những file cấu hình Git thường gặp

### 5.1. System config

System config thường được quản trị viên hoặc trình cài đặt Git thiết lập. Nó có thể đặt các mặc định chung cho người dùng trên máy.

Đường dẫn phụ thuộc hệ điều hành và cách cài Git. Một số ví dụ:

- Linux: `/etc/gitconfig`.
- Windows: file `etc/gitconfig` trong thư mục cài Git, ví dụ `C:/Program Files/Git/etc/gitconfig`.
- macOS: có thể là `/etc/gitconfig` hoặc vị trí do bản phân phối Git sử dụng.

Xem riêng system config:

```bash
git config --system --list --show-origin
```

Sửa system config thường cần quyền quản trị. Không nên thay đổi scope này nếu mục tiêu chỉ là điều chỉnh hành vi của một repository.

### 5.2. Global config

Global config thuộc người dùng hiện tại. Nó phù hợp với các thiết lập cá nhân dùng chung cho nhiều repository, chẳng hạn tên, email, editor hoặc alias.

Xem:

```bash
git config --global --list --show-origin
```

Trên Windows, file thường nằm tại `%USERPROFILE%\.gitconfig`; trên Linux/macOS, thường là `~/.gitconfig` hoặc file XDG `$XDG_CONFIG_HOME/git/config` (mặc định thường là `~/.config/git/config`). Đường dẫn thực tế nên được xác nhận bằng `--show-origin`.

### 5.3. Local config

Local config áp dụng cho repository hiện tại. Đây thường là nơi đặt remote, branch tracking, một số tùy chọn dự án hoặc thông tin người commit riêng cho repository.

Xem:

```bash
git config --local --list --show-origin
```

File thường là `.git/config`. Với linked worktree, `.git` có thể là một tệp trỏ tới Git directory chứ không phải thư mục; vì vậy hãy dùng `--show-origin` để thấy đường dẫn thực tế thay vì đoán vị trí.

### 5.4. Worktree config

Một repository có thể có nhiều linked worktree. Khi bật extension `extensions.worktreeConfig`, Git hỗ trợ file cấu hình riêng cho từng worktree.

Kiểm tra:

```bash
git config --local --get extensions.worktreeConfig
```

Nếu đã bật, có thể xem cấu hình của worktree hiện tại:

```bash
git config --worktree --list --show-origin
```

Worktree config hữu ích khi mỗi worktree cần thiết lập khác nhau. Chỉ sử dụng `--worktree` khi repository đã được cấu hình hỗ trợ; nếu không, Git có thể báo lỗi hoặc không có scope tương ứng.

### 5.5. Command scope

Có thể truyền cấu hình chỉ cho một lần chạy:

```bash
git -c core.pager=cat log --oneline
```

Thiết lập `core.pager=cat` chỉ áp dụng cho lệnh `git log` đó. Nó không sửa file global hay local. Khi chạy lệnh khác, cấu hình tạm thời không còn hiệu lực.

Có thể xem nguồn command scope bằng:

```bash
git -c core.pager=cat config --list --show-origin --show-scope
```

## 6. Include và includeIf: vì sao một file cấu hình lại kéo thêm file khác?

Git config hỗ trợ chỉ thị include để một file cấu hình nạp nội dung từ file khác. Ví dụ:

```ini
[include]
    path = ~/.gitconfig-work
```

Khi Git đọc file chứa chỉ thị này, nó cũng đọc file được include. Vì vậy, một khóa xuất hiện trong `git config --list --show-origin` có thể đến từ một file mà ta không ngờ tới.

Git còn hỗ trợ include có điều kiện. Ví dụ:

```ini
[includeIf "gitdir:D:/work/company/"]
    path = ~/.gitconfig-company

[includeIf "gitdir:D:/work/personal/"]
    path = ~/.gitconfig-personal
```

Trong ví dụ, repository nằm dưới thư mục công việc có thể nạp cấu hình công ty; repository cá nhân có thể nạp cấu hình cá nhân. Các điều kiện khác có thể dựa trên branch đang checkout hoặc remote URL, tùy phiên bản và cú pháp Git hỗ trợ.

Khi include được xử lý, `--show-origin` giúp nhận ra khóa đến từ file include nào. Nếu cần xem danh sách mà không mở rộng include, có thể dùng:

```bash
git config --list --show-origin --no-includes
```

Lệnh này hữu ích để phân biệt nội dung khai báo trực tiếp trong file đang đọc với các giá trị được nạp qua include.

## 7. Biến môi trường cũng có thể làm thay đổi cấu hình được đọc

Ngoài file cấu hình, một số biến môi trường có thể thay đổi nguồn cấu hình hoặc đưa giá trị cấu hình vào lần chạy hiện tại. Các biến đáng chú ý:

| Biến | Ảnh hưởng |
|---|---|
| `GIT_CONFIG_SYSTEM` | Chỉ định file system config thay thế. |
| `GIT_CONFIG_GLOBAL` | Chỉ định file global config thay thế. |
| `GIT_CONFIG_NOSYSTEM` | Bỏ qua system config khi được bật. |
| `GIT_CONFIG_COUNT` cùng `GIT_CONFIG_KEY_n` và `GIT_CONFIG_VALUE_n` | Đưa một hoặc nhiều cặp khóa/giá trị vào cấu hình cho tiến trình Git. |

Ví dụ PowerShell, đặt một cấu hình tạm cho các lệnh Git trong tiến trình hiện tại:

```powershell
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'core.pager'
$env:GIT_CONFIG_VALUE_0 = 'cat'

git config --list --show-origin --show-scope

Remove-Item Env:GIT_CONFIG_COUNT
Remove-Item Env:GIT_CONFIG_KEY_0
Remove-Item Env:GIT_CONFIG_VALUE_0
```

Trong thực tế, các biến môi trường có thể được IDE, script hoặc CI thiết lập. Nếu kết quả khác với khi mở terminal thông thường, hãy kiểm tra môi trường của tiến trình đang chạy Git.

Không phải mọi biến môi trường ảnh hưởng tới Git đều là config key. Ví dụ, một số biến `GIT_AUTHOR_*`, `GIT_COMMITTER_*` hoặc biến điều khiển repository có thể ảnh hưởng hành vi mà không xuất hiện như một mục trong `git config --list`. Vì vậy, lệnh liệt kê config không phải bản kiểm kê toàn bộ môi trường tiến trình.

## 8. Chỉnh đúng nguồn cấu hình sau khi tìm ra nguyên nhân

Khi đã biết giá trị sai đến từ đâu, chọn đúng scope để sửa.

### 8.1. Sửa cấu hình global

```bash
git config --global user.name "An Nguyen"
git config --global user.email "an@example.com"
```

Các giá trị này áp dụng cho người dùng trên nhiều repository, trừ khi có cấu hình ưu tiên cao hơn ghi đè.

### 8.2. Sửa cấu hình local

```bash
git config --local user.name "An Nguyen"
git config --local user.email "an@company.example"
```

Các giá trị này chỉ áp dụng cho repository hiện tại và có thể ghi đè cấu hình global. Đây là lựa chọn thường dùng khi repository công ty cần email commit riêng.

### 8.3. Thay thế, thêm hoặc xóa giá trị

```bash
# Thay thế giá trị của một khóa
git config --local --replace-all core.editor "code --wait"

# Thêm một giá trị mới cho khóa multi-valued
git config --local --add remote.origin.fetch "+refs/heads/release/*:refs/remotes/origin/release/*"

# Xóa mọi giá trị của khóa trong scope local
git config --local --unset-all remote.origin.fetch
```

Chỉ dùng `--unset-all` khi thực sự muốn xóa tất cả giá trị của khóa trong scope đó. Với khóa multi-valued, có thể cần xem lại và thêm lại các mapping cần thiết sau khi xóa.

### 8.4. Sửa file nào?

Nếu `--show-origin` cho biết giá trị sai nằm trong file global, sửa global. Nếu nó đến từ `.git/config`, sửa local. Nếu giá trị đến từ include file, hãy chỉnh file include hoặc điều kiện include tương ứng. Nếu giá trị đến từ command scope, kiểm tra script hoặc lệnh gọi Git thay vì sửa file cấu hình lâu dài.

Sau khi sửa, chạy lại:

```bash
git config --list --show-origin --show-scope
git config --show-origin --show-scope --get core.editor
```

Đối chiếu cả giá trị lẫn nguồn để chắc chắn cấu hình có hiệu lực như mong muốn.

## 9. Những điểm cần cẩn thận khi đọc kết quả

### 9.1. `--list` hiển thị mọi khai báo, không chỉ giá trị cuối cùng

Nếu `user.name` xuất hiện ở global và local, cả hai có thể được liệt kê. Đừng thấy giá trị global rồi kết luận đó là giá trị đang dùng trong repository. Hãy xem scope và truy vấn khóa cụ thể.

### 9.2. Khóa nhiều giá trị có thể được cộng dồn

Các khóa như `remote.origin.fetch` có thể có nhiều dòng hợp lệ. Dùng `--get-all` để kiểm tra đầy đủ. Xóa hoặc thay thế một giá trị mà không hiểu mapping còn lại có thể làm fetch thiếu branch.

### 9.3. Include khiến nguồn cấu hình phân tán

Một file global có thể include file riêng theo thư mục hoặc branch. Khi thấy giá trị đến từ file lạ, hãy xem `--show-origin` và kiểm tra điều kiện include trước khi chỉnh sửa.

### 9.4. Đầu ra có thể chứa thông tin nhạy cảm

`git config --list --show-origin` có thể in URL remote có token, HTTP extra header, credential helper hoặc thông tin nội bộ khác. Không đăng nguyên đầu ra lên issue công khai, chat nhóm hoặc log CI. Khi cần nhờ người khác hỗ trợ, hãy lọc khóa liên quan và che token, mật khẩu, địa chỉ nội bộ nhạy cảm.

### 9.5. Cấu hình không phải là mọi thứ Git đang sử dụng

Một hành vi có thể chịu ảnh hưởng bởi biến môi trường, tùy chọn dòng lệnh, phiên bản Git, cấu hình hệ thống bên ngoài hoặc công cụ gọi Git. Nếu đã xác định config key đúng mà hành vi vẫn khác, hãy kiểm tra lệnh thực tế và môi trường tiến trình.

## 10. Quy trình chẩn đoán cấu hình sai

Giả sử commit đang dùng sai email dù global config đã được đặt đúng. Thực hiện theo thứ tự:

**Bước 1: Xác nhận repository hiện tại**

```bash
git rev-parse --show-toplevel
```

**Bước 2: Xem mọi khai báo và nguồn**

```bash
git config --list --show-origin --show-scope
```

**Bước 3: Truy vấn đúng khóa**

```bash
git config --show-origin --show-scope --get user.email
```

**Bước 4: Nếu là khóa nhiều giá trị, xem tất cả**

```bash
git config --show-origin --show-scope --get-all remote.origin.fetch
```

**Bước 5: Kiểm tra include và môi trường nếu nguồn chưa rõ**

```bash
git config --list --show-origin --no-includes
```

Trên PowerShell, có thể kiểm tra các biến cấu hình liên quan:

```powershell
Get-ChildItem Env:GIT_CONFIG*
```

**Bước 6: Sửa đúng scope**

Nếu email sai do local config, sửa local thay vì thay đổi global:

```bash
git config --local user.email "an@company.example"
```

**Bước 7: Xác minh lại**

```bash
git config --show-origin --show-scope --get user.email
```

Nếu cần kiểm tra thông tin tác giả của commit đã tạo, xem commit đó:

```bash
git log -1 --format=fuller
```

Thay đổi cấu hình không sửa ngược thông tin tác giả của các commit đã tồn tại. Muốn thay đổi metadata commit cũ phải thực hiện thao tác viết lại lịch sử riêng.

## 11. Ghi nhớ

- `git config --list --show-origin` liệt kê các mục cấu hình cùng file hoặc nguồn cung cấp chúng.
- Thêm `--show-scope` để thấy `system`, `global`, `local`, `worktree` hoặc `command`.
- Thứ tự ưu tiên thông dụng tăng dần: system → global → local → worktree → command.
- `--list` hiển thị mọi khai báo; nó không phải lúc nào cũng là bản tóm tắt giá trị hiệu lực cuối cùng.
- Dùng `--get` cho một khóa, `--get-all` cho khóa nhiều giá trị và `--get-regexp` để tìm một nhóm khóa.
- Include và includeIf có thể nạp cấu hình từ file khác; `--show-origin` giúp tìm file thực sự cung cấp giá trị.
- Biến môi trường và tùy chọn `git -c` có thể làm thay đổi cấu hình của một lần chạy.
- Sửa đúng scope và xác minh lại nguồn sau khi chỉnh.
- Không chia sẻ nguyên đầu ra cấu hình khi chưa kiểm tra token, mật khẩu hoặc thông tin nội bộ.

Khi một lệnh Git hoạt động khác mong đợi, hãy bắt đầu bằng `git config --list --show-origin --show-scope`, sau đó truy vấn khóa cụ thể. Xác định đúng nguồn trước khi sửa sẽ giúp tránh thay đổi global không cần thiết hoặc vô tình làm ảnh hưởng các repository khác.

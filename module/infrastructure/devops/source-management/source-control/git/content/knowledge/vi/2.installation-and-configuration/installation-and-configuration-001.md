# Cài đặt Git trên Windows, macOS và Linux

Git là hệ thống quản lý phiên bản phân tán dùng để ghi nhận lịch sử thay đổi của mã nguồn, làm việc với branch và phối hợp qua repository từ xa. Trước khi dùng các lệnh như `git status`, `git add`, `git commit`, `git fetch` hoặc `git push`, máy tính cần có Git client và terminal có thể gọi được chương trình `git`.

Git có thể được cài trên Windows, macOS và nhiều bản phân phối Linux. Mỗi hệ điều hành có cách cài đặt khác nhau, nhưng quy trình chung giống nhau: chọn nguồn cài phù hợp, cài chương trình, mở terminal mới, xác minh phiên bản và cấu hình danh tính commit.

## 1. Chuẩn bị trước khi cài đặt

Trước khi cài, xác định hệ điều hành và quyền quản trị trên máy:

- **Windows:** dùng tài khoản có quyền cài phần mềm; có thể cài bằng bộ cài Git for Windows hoặc Windows Package Manager (`winget`).
- **macOS:** có thể dùng Command Line Tools của Apple hoặc một trình quản lý gói như Homebrew.
- **Linux:** cài gói `git` từ repository của bản phân phối bằng trình quản lý gói tương ứng.

Git là công cụ chạy trên máy. GitHub, GitLab và Bitbucket là các nền tảng lưu trữ repository và hỗ trợ cộng tác; tạo tài khoản trên các nền tảng đó không đồng nghĩa Git client đã được cài đặt.

Nếu máy đã có Git, nên kiểm tra trước để tránh cài trùng không cần thiết:

```bash
git --version
```

Nếu terminal trả về phiên bản, chẳng hạn `git version 2.x.y`, Git đã có thể được gọi từ terminal hiện tại. Bạn vẫn nên kiểm tra đường dẫn thực thi nếu máy có nhiều bản Git.

## 2. Cài đặt Git trên Windows

Trên Windows, bản phân phối phổ biến là **Git for Windows**. Gói này cung cấp Git command line, Git Bash và tùy chọn Git GUI. Git Bash mang đến môi trường shell kiểu Unix, trong khi Git cũng có thể được gọi từ PowerShell hoặc Command Prompt nếu PATH được cấu hình phù hợp.

### Cách 1: Dùng bộ cài Git for Windows

1. Mở trang tải chính thức: <https://git-scm.com/download/win>.
2. Tải bộ cài phù hợp với kiến trúc máy, thường là 64-bit hoặc ARM64.
3. Chạy file cài đặt và đọc các lựa chọn trong trình hướng dẫn.
4. Chọn các thành phần cần thiết. Git Bash và Git GUI có thể được cài cùng Git command line.
5. Ở bước cấu hình PATH, lựa chọn thường phù hợp cho người phát triển là cho phép dùng Git từ command line và cả phần mềm bên thứ ba. Lựa chọn này giúp PowerShell, Command Prompt và IDE tìm được `git`.
6. Chọn terminal mặc định cho Git Bash và các tùy chọn khác theo nhu cầu. Nếu chưa có quy ước riêng của nhóm, có thể giữ lựa chọn mặc định được đề xuất bởi bộ cài.
7. Hoàn tất cài đặt.

Một số phiên bản bộ cài có lựa chọn về line ending, terminal, credential helper và tên nhánh mặc định. Hãy đọc kỹ các lựa chọn này. Với line ending, dự án có thể quy định bằng `.gitattributes`; không nên thay đổi cấu hình chỉ để khắc phục một diff bất thường khi chưa hiểu quy tắc của repository.

### Cách 2: Dùng winget

Trên Windows có Windows Package Manager, mở PowerShell hoặc Windows Terminal và chạy:

```powershell
winget install --id Git.Git -e --source winget
```

Lệnh yêu cầu `winget` cài gói Git for Windows có ID `Git.Git`. Nếu Windows yêu cầu xác nhận nguồn hoặc quyền cài đặt, làm theo hướng dẫn của hệ thống. Sau khi hoàn tất, đóng và mở lại terminal để nạp PATH mới.

Để cập nhật Git đã cài qua winget:

```powershell
winget upgrade --id Git.Git -e
```

Nếu `winget` không có trên máy hoặc không tìm thấy gói, dùng bộ cài chính thức ở cách 1 hoặc cập nhật Windows App Installer rồi thử lại.

### Kiểm tra trên Windows

Mở một cửa sổ PowerShell mới:

```powershell
git --version
where.exe git
```

`git --version` xác nhận chương trình chạy được; `where.exe git` liệt kê các vị trí `git.exe` mà PATH tìm thấy. Nếu có nhiều kết quả, máy có thể có nhiều bản Git. Hãy kiểm tra bản nào được ưu tiên để tránh IDE và terminal dùng các phiên bản khác nhau.

Bạn cũng có thể mở **Git Bash** từ Start Menu và chạy:

```bash
git --version
which git
```

Git Bash thường đi kèm trong Git for Windows. Bạn có thể dùng PowerShell, Windows Terminal, Command Prompt hoặc Git Bash; điều quan trọng là terminal đang dùng phải tìm được đúng Git executable.

## 3. Cài đặt Git trên macOS

macOS có một số cách cài Git. Có thể dùng Command Line Tools do Apple cung cấp hoặc cài bản Git mới hơn qua Homebrew.

### Cách 1: Cài Apple Command Line Tools

Mở Terminal và chạy:

```bash
xcode-select --install
```

macOS sẽ hiển thị hộp thoại cài đặt Command Line Tools. Làm theo hướng dẫn và chờ quá trình hoàn tất. Bộ công cụ này bao gồm các tiện ích phát triển cần thiết, trong đó có Git.

Trên một số máy, khi chạy `git --version` lần đầu, macOS có thể tự đề nghị cài Command Line Tools. Bạn cũng có thể kiểm tra trạng thái bằng:

```bash
xcode-select -p
```

Nếu lệnh trả về đường dẫn bộ công cụ, chẳng hạn `/Library/Developer/CommandLineTools`, công cụ đã được cài và đang được chọn. Nếu máy đã cài Xcode đầy đủ, đường dẫn có thể nằm bên trong ứng dụng Xcode.

### Cách 2: Cài qua Homebrew

Nếu đã cài Homebrew, chạy:

```bash
brew install git
```

Để cập nhật package Git sau này:

```bash
brew update
brew upgrade git
```

Homebrew thường cài Git ở prefix riêng, ví dụ `/opt/homebrew` trên Apple Silicon hoặc `/usr/local` trên một số máy Intel. Nếu máy đồng thời có Git từ Apple Command Line Tools, kiểm tra đường dẫn để biết terminal đang dùng bản nào:

```bash
command -v git
type -a git
git --version
```

Nếu muốn dùng bản Homebrew, bảo đảm thư mục `bin` của Homebrew được thêm vào PATH theo hướng dẫn cài đặt Homebrew cho shell hiện tại. Không cần gỡ Command Line Tools chỉ vì đã cài thêm Git bằng Homebrew.

## 4. Cài đặt Git trên Linux

Phần lớn bản phân phối Linux cung cấp Git trong kho package chính thức. Hãy dùng trình quản lý gói tương ứng với bản phân phối đang chạy. Các lệnh dưới đây cần quyền quản trị, thường thông qua `sudo`.

### Ubuntu và Debian

```bash
sudo apt update
sudo apt install git
```

`apt update` làm mới thông tin package; `apt install git` cài Git từ kho đã cấu hình.

### Fedora

```bash
sudo dnf install git
```

### RHEL, Rocky Linux và AlmaLinux

```bash
sudo dnf install git
```

Tùy phiên bản và repository được bật, package có thể không phải bản Git mới nhất. Nếu dự án yêu cầu một phiên bản cụ thể, kiểm tra nguồn package được tổ chức hỗ trợ trước khi cài từ nguồn bên ngoài.

### Arch Linux và các bản dựa trên Arch

```bash
sudo pacman -S git
```

### openSUSE

```bash
sudo zypper install git
```

### Alpine Linux

```bash
sudo apk add git
```

Sau khi cài, kiểm tra:

```bash
git --version
command -v git
```

Để cập nhật Git, dùng trình quản lý gói của bản phân phối, ví dụ `sudo apt upgrade git`, `sudo dnf upgrade git` hoặc lệnh cập nhật tương ứng. Nên ưu tiên kho package chính thức hoặc repository nội bộ được tổ chức phê duyệt để bảo đảm nguồn gói và quy trình cập nhật nhất quán.

## 5. Xác minh Git đã được cài đúng

Sau khi cài đặt, đóng các cửa sổ terminal cũ và mở terminal mới. Chạy:

```bash
git --version
```

Ví dụ:

```text
git version 2.45.0
```

Số phiên bản cụ thể phụ thuộc nguồn cài đặt và thời điểm cập nhật. Bạn không cần có đúng phiên bản trong ví dụ; điều cần xác nhận là lệnh trả về phiên bản thay vì báo không tìm thấy chương trình.

Kiểm tra đường dẫn executable:

```bash
# Windows PowerShell
where.exe git

# macOS / Linux / Git Bash
command -v git
type -a git
```

Nếu `where.exe` hoặc `command -v` trả về đường dẫn, terminal đã tìm thấy Git thông qua PATH. Nếu có nhiều đường dẫn, xem xét thứ tự PATH và cấu hình IDE để bảo đảm mọi công cụ sử dụng bản Git mong muốn.

Có thể kiểm tra thư mục chứa các lệnh phụ trợ của Git:

```bash
git --exec-path
```

Lệnh này hữu ích khi điều tra cài đặt không đầy đủ hoặc nhiều bản Git cùng tồn tại; người dùng thông thường không cần thay đổi thư mục đó.

## 6. Cấu hình danh tính cho commit đầu tiên

Sau khi cài Git, nên cấu hình tên và email được ghi vào metadata của commit. Đây là thông tin tác giả/committer mà Git lưu trong lịch sử; nó không phải tài khoản đăng nhập GitHub hoặc GitLab.

Thiết lập ở phạm vi người dùng hiện tại:

```bash
git config --global user.name "Nguyen Van A"
git config --global user.email "nguyen.van.a@example.com"
```

Thay các giá trị minh họa bằng tên và email phù hợp với chính sách của nhóm. Nếu tổ chức yêu cầu email công ty hoặc email riêng tư do nền tảng cung cấp, hãy dùng địa chỉ được quy định.

Kiểm tra hai giá trị:

```bash
git config --global --get user.name
git config --global --get user.email
```

Git hỗ trợ ba phạm vi cấu hình phổ biến:

| Phạm vi | Cách khai báo | Tác động |
|---|---|---|
| System | `git config --system` | Áp dụng cho mọi người dùng trên máy; thường cần quyền quản trị |
| Global | `git config --global` | Áp dụng cho người dùng hiện tại trên các repository của họ |
| Local | `git config --local` | Áp dụng cho repository hiện tại và có ưu tiên cao hơn global |

Nếu một dự án cần danh tính khác, vào thư mục repository và đặt cấu hình local:

```bash
git config --local user.name "Team Bot"
git config --local user.email "team-bot@example.com"
```

Giá trị local ghi đè cấu hình global trong repository đó. Không nên dùng danh tính bot hoặc email của người khác nếu chưa được nhóm cho phép.

## 7. Một vài cấu hình ban đầu hữu ích

### Đặt tên branch mặc định khi init repository

Để repository mới khởi tạo bằng `git init` dùng branch `main`:

```bash
git config --global init.defaultBranch main
```

Thiết lập này ảnh hưởng đến repository mới được khởi tạo sau đó; nó không tự đổi tên branch trong repository đã tồn tại.

### Chọn editor cho thông điệp commit

Git có thể mở editor khi cần nhập commit message. Ví dụ, nếu muốn dùng Visual Studio Code và lệnh `code` đã có trong PATH:

```bash
git config --global core.editor "code --wait"
```

`--wait` giúp Git chờ đến khi bạn đóng cửa sổ chỉnh sửa trước khi tiếp tục. Có thể chọn editor khác theo môi trường phát triển của bạn.

### Hiển thị cấu hình và nguồn cấu hình

```bash
git config --list --show-origin
```

Lệnh liệt kê cấu hình hiệu lực cùng file nguồn. Hãy xem output trước khi chia sẻ vì cấu hình cá nhân có thể chứa thông tin nội bộ hoặc đường dẫn riêng. Khi chỉ cần kiểm tra một giá trị, ưu tiên `git config --get <key>`.

## 8. Kết nối repository từ xa sau khi cài Git

Cài Git không tự động đăng nhập vào GitHub, GitLab hay máy chủ Git của tổ chức. Khi cần clone repository, bạn phải có URL và quyền truy cập phù hợp.

Ví dụ clone qua HTTPS:

```bash
git clone https://example.com/team/project.git
```

Hoặc clone qua SSH:

```bash
git clone git@example.com:team/project.git
```

HTTPS thường sử dụng credential manager hoặc cơ chế xác thực của nền tảng. SSH cần có key phù hợp và public key được đăng ký với máy chủ. Không đặt mật khẩu hoặc access token trực tiếp trong URL được lưu vào lịch sử terminal hay file cấu hình công khai.

Sau khi clone, đi vào thư mục repository và kiểm tra:

```bash
cd project
git status
git remote -v
```

Nếu chưa có repository, có thể tạo một repository local để thử lệnh cơ bản:

```bash
mkdir git-practice
cd git-practice
git init
git status
```

## 9. Xử lý các lỗi cài đặt thường gặp

### Terminal báo git is not recognized hoặc command not found

Nguyên nhân thường là Git chưa được cài, terminal chưa nạp PATH mới hoặc thư mục chứa executable chưa có trong PATH.

- Windows: đóng và mở lại PowerShell/Windows Terminal; chạy `where.exe git`; kiểm tra tùy chọn PATH trong bộ cài Git for Windows.
- macOS: chạy `xcode-select --install` nếu thiếu Command Line Tools; với Homebrew, kiểm tra `brew --prefix` và PATH.
- Linux: kiểm tra package `git` đã được cài bằng trình quản lý gói và chạy `command -v git`.

Không tải một file `git.exe` rời rạc từ nguồn không rõ để xử lý lỗi PATH. Hãy dùng lại nguồn cài chính thức hoặc package manager đáng tin cậy.

### Terminal và IDE dùng hai phiên bản Git khác nhau

Một máy có thể có Git từ nhiều nguồn, ví dụ Git for Windows và một bản Git đi kèm công cụ khác; macOS có thể có bản Apple Command Line Tools và Homebrew cùng lúc. Kiểm tra đường dẫn bằng `where.exe git` hoặc `type -a git`, rồi xem phần cấu hình Git executable trong IDE nếu IDE cho phép chọn riêng.

### macOS yêu cầu cài Command Line Tools

Đây thường là thông báo hệ thống khi một công cụ phát triển chưa có sẵn. Chạy `xcode-select --install` và hoàn tất hộp thoại. Nếu đã cài Xcode hoặc Command Line Tools nhưng Git vẫn không chạy, kiểm tra `xcode-select -p` và đường dẫn Git.

### Linux báo không có quyền cài package

Lệnh cài package thường cần quyền quản trị. Dùng `sudo` theo chính sách của máy. Trên máy công ty hoặc môi trường được quản lý, liên hệ quản trị viên nếu tài khoản không có quyền hoặc repository package bị giới hạn.

### Không thể xác thực khi clone hoặc push

Đây thường là vấn đề thông tin xác thực hoặc quyền repository, không phải lỗi cài Git. Kiểm tra URL remote, quyền truy cập, credential manager hoặc SSH key. Có thể xác minh kết nối SSH theo hướng dẫn của nhà cung cấp Git hosting; không chia sẻ private key hoặc token để nhờ người khác kiểm tra.

## 10. Quy trình cài đặt và kiểm tra nhanh

Sau đây là checklist chung có thể dùng trên máy mới:

1. Xác định hệ điều hành và chọn nguồn cài chính thức hoặc package manager được hỗ trợ.
2. Cài Git bằng bộ cài Git for Windows, Apple Command Line Tools/Homebrew hoặc package manager Linux.
3. Mở terminal mới để nạp PATH.
4. Chạy `git --version` để xác minh cài đặt.
5. Chạy `where.exe git` trên PowerShell hoặc `command -v git` trên macOS/Linux để kiểm tra executable.
6. Cấu hình `user.name` và `user.email` ở phạm vi global hoặc local phù hợp.
7. Thiết lập editor và `init.defaultBranch` nếu nhóm cần.
8. Clone một repository được cấp quyền hoặc tạo repository thực hành bằng `git init`.
9. Chạy `git status` để xác nhận Git hoạt động trong repository.

## 11. Ghi nhớ

Git có thể cài trên cả Windows, macOS và Linux. Windows thường dùng Git for Windows; macOS có thể dùng Apple Command Line Tools hoặc Homebrew; Linux thường cài package `git` từ kho của bản phân phối. Sau khi cài, hãy mở terminal mới, xác minh bằng `git --version` và kiểm tra đường dẫn thực thi nếu có nhiều bản Git.

Trước commit đầu tiên, cấu hình `user.name` và `user.email` để lịch sử có thông tin tác giả phù hợp. Git client, tài khoản Git hosting và quyền truy cập repository là những phần riêng biệt; cài thành công Git mới chỉ là bước đầu để làm việc với mã nguồn và cộng tác qua remote.

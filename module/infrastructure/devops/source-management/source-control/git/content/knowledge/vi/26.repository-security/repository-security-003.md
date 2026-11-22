# Khóa SSH, ssh-agent và kiểm tra dấu vân tay máy chủ

SSH cho phép Git kết nối đến remote qua một kênh được mã hóa và xác thực. Khi dùng SSH, có hai việc xác minh riêng biệt: máy khách phải xác nhận **đúng máy chủ** đang kết nối, và máy chủ phải xác nhận **đúng người dùng hoặc khóa máy khách** đang yêu cầu truy cập. Khóa SSH cá nhân và `ssh-agent` hỗ trợ việc xác thực máy khách; dấu vân tay máy chủ giúp bạn kiểm tra danh tính máy chủ trước khi gửi thông tin xác thực.

Hiểu rõ hai chiều này giúp tránh nhầm public key của tài khoản với host key của máy chủ, tránh chấp nhận nhầm máy chủ giả mạo và xử lý được các lỗi thường gặp khi clone, fetch hoặc push qua SSH.

## 1. SSH dùng những loại khóa nào?

Khi kết nối Git remote bằng SSH, có hai cặp thông tin khóa cần phân biệt:

| Thành phần | Nằm ở đâu | Mục đích |
|---|---|---|
| Khóa cá nhân của người dùng (client key) | Máy của bạn: private key và public key | Chứng minh bạn có quyền truy cập tài khoản hoặc máy chủ Git |
| Khóa máy chủ (host key) | Máy chủ Git giữ private host key; máy khách lưu public host key đã tin cậy trong `known_hosts` | Chứng minh máy chủ là đúng máy chủ mà bạn định kết nối |

Khóa cá nhân thường có tên như `id_ed25519` và `id_ed25519.pub`. Bạn giữ file không có hậu tố `.pub` ở máy của mình; chỉ đăng ký nội dung file `.pub` với dịch vụ Git hoặc quản trị viên. Không gửi private key cho người khác.

Host key là khóa của máy chủ, không phải khóa tài khoản của bạn. Dấu vân tay host key được hiển thị khi kết nối lần đầu hoặc khi bạn chủ động tra cứu. Bạn phải so sánh fingerprint đó với thông tin do nhà cung cấp hoặc quản trị viên công bố qua một kênh đáng tin cậy.

Luồng kết nối đơn giản:

```text
Máy của bạn                              Máy chủ Git
    |                                         |
    |---- yêu cầu kết nối SSH --------------->|
    |<--- host key / yêu cầu xác minh --------|
    |                                         |
    |  kiểm tra fingerprint với nguồn tin cậy |
    |                                         |
    |---- yêu cầu xác thực bằng client key -->|
    |<--- chấp nhận hoặc từ chối -------------|
    |                                         |
    |---- Git fetch / push qua SSH ---------->|
```

SSH mã hóa phiên làm việc sau khi thiết lập kết nối và xác thực theo giao thức. Việc xác minh host key phải diễn ra trước khi bạn tin tưởng máy chủ và gửi yêu cầu xác thực tài khoản.

## 2. Tạo khóa SSH cá nhân

Trước tiên, kiểm tra thư mục khóa hiện có để tránh ghi đè khóa đang sử dụng:

```bash
ls -la ~/.ssh
```

Trên Windows PowerShell:

```powershell
Get-ChildItem $env:USERPROFILE\.ssh
```

Nếu chưa có khóa phù hợp, tạo khóa Ed25519:

```bash
ssh-keygen -t ed25519 -C "dev@example.com"
```

Git/SSH sẽ hỏi đường dẫn lưu khóa. Mặc định thường là `~/.ssh/id_ed25519`; nếu đã có khóa ở vị trí đó, hãy chọn một tên riêng, chẳng hạn `~/.ssh/id_ed25519_work`, thay vì ghi đè. Tiếp theo, nhập passphrase để mã hóa private key trên đĩa. Nên đặt passphrase đủ mạnh; `ssh-agent` có thể giữ khóa đã mở khóa trong bộ nhớ để bạn không phải nhập lại mỗi lần kết nối.

Sau khi tạo, bạn sẽ có hai file:

```text
~/.ssh/id_ed25519       # private key: giữ bí mật
~/.ssh/id_ed25519.pub   # public key: đăng ký với dịch vụ Git
```

Xem public key để sao chép vào trang quản lý SSH keys của dịch vụ Git:

```bash
cat ~/.ssh/id_ed25519.pub
```

Trên Windows PowerShell:

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

Chỉ sao chép dòng public key bắt đầu bằng loại khóa như `ssh-ed25519`. Không sao chép nội dung file private key. Khi thêm khóa vào tài khoản Git, đặt tên dễ nhận biết theo thiết bị hoặc mục đích, ví dụ `Laptop work`.

### Bảo vệ private key

Trên Linux/macOS, thư mục và private key nên chỉ cho chủ sở hữu truy cập:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
```

Nếu dùng tên khóa khác, thay đúng đường dẫn. Trên Windows, OpenSSH cũng có thể từ chối khóa nếu ACL cho phép người dùng không phù hợp đọc private key; hãy kiểm tra quyền file trong Security properties và chỉ cấp quyền cần thiết cho tài khoản của bạn.

Không commit private key, không gửi qua email/chat và không đưa passphrase vào script hoặc biến cấu hình của repository. Nếu thiết bị chứa private key bị mất hoặc nghi ngờ bị lộ, thu hồi public key tương ứng khỏi tài khoản/dịch vụ Git và tạo cặp khóa mới.

## 3. Đăng ký public key với dịch vụ Git

Mỗi dịch vụ Git có trang quản lý SSH keys riêng. Quy trình chung:

1. Mở phần cài đặt tài khoản hoặc quản lý deploy key của repository.
2. Chọn thêm SSH key.
3. Dán toàn bộ một dòng public key từ file `.pub`.
4. Đặt tên thiết bị và thời hạn nếu dịch vụ hỗ trợ.
5. Lưu lại và kiểm tra trạng thái khóa.

Khóa tài khoản thường đại diện cho người dùng và có quyền theo tài khoản. Deploy key thường gắn với một repository cụ thể và có thể chỉ được cấp quyền đọc hoặc được bật quyền ghi riêng. Chọn loại khóa theo nhu cầu và chính sách của tổ chức.

Sau khi đăng ký, bạn có thể kiểm tra kết nối SSH tới máy chủ Git:

```bash
ssh -T git@git.example.com
```

Thay `git.example.com` bằng hostname của dịch vụ. Một số dịch vụ trả về lời chào xác nhận tài khoản và thông báo không cung cấp shell tương tác; điều đó vẫn có thể là kết quả xác thực SSH thành công. Hãy đối chiếu thông báo với hướng dẫn của nhà cung cấp.

Xác thực SSH thành công chưa chứng minh bạn có quyền đọc hoặc ghi mọi repository. Hãy kiểm tra URL remote và quyền trên repository bằng một thao tác Git phù hợp, chẳng hạn:

```bash
git ls-remote origin
```

Lệnh này kiểm tra khả năng đọc các ref từ remote đã cấu hình. Quyền push là quyền riêng và có thể bị giới hạn theo branch hoặc chính sách máy chủ.

## 4. ssh-agent là gì?

`ssh-agent` là tiến trình giữ các khóa cá nhân đã được mở khóa trong bộ nhớ. Khi SSH cần xác thực, client có thể yêu cầu agent ký thử thách bằng khóa đã nạp mà không phải đọc passphrase từ người dùng mỗi lần.

Agent không thay thế private key và cũng không gửi private key cho máy chủ. Private key vẫn nằm trên máy của bạn; agent cung cấp thao tác ký bằng khóa đã nạp. Hãy bảo vệ phiên đăng nhập và quyền truy cập vào agent socket, vì tiến trình cùng quyền người dùng có thể yêu cầu agent thực hiện chữ ký khi agent đang hoạt động.

Các lệnh cơ bản:

```bash
ssh-add ~/.ssh/id_ed25519
ssh-add -l
ssh-add -L
```

- `ssh-add <private-key>` nạp khóa vào agent; lần đầu có thể hỏi passphrase.
- `ssh-add -l` liệt kê fingerprint của các khóa đang nạp.
- `ssh-add -L` hiển thị public key của các khóa đang nạp.

Giới hạn thời gian giữ khóa trong agent:

```bash
ssh-add -t 1h ~/.ssh/id_ed25519
```

Sau một giờ, agent loại khóa đó khỏi danh sách khóa đang giữ. Xóa một khóa cụ thể:

```bash
ssh-add -d ~/.ssh/id_ed25519
```

Xóa tất cả khóa khỏi agent hiện tại:

```bash
ssh-add -D
```

## 5. Khởi động và sử dụng ssh-agent trên Linux và macOS

Trên nhiều môi trường desktop, agent được hệ điều hành hoặc trình quản lý phiên khởi chạy sẵn. Nếu chưa có agent trong phiên terminal, với OpenSSH có thể chạy:

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

Lệnh đầu khởi chạy agent và thiết lập các biến môi trường cho shell hiện tại; lệnh thứ hai nạp private key. Nếu mở một terminal độc lập khác không thừa hưởng môi trường của agent, shell đó có thể không kết nối được tới cùng agent.

Trên macOS, Apple OpenSSH có thể tích hợp passphrase với Keychain:

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
```

Trong `~/.ssh/config`, có thể cấu hình:

```sshconfig
Host *
    AddKeysToAgent yes
    UseKeychain yes
```

`UseKeychain` là tùy chọn của Apple OpenSSH; không phải bản OpenSSH trên Linux hoặc Windows nào cũng hỗ trợ. Nếu máy báo tùy chọn không hợp lệ, bỏ dòng đó và dùng cách quản lý agent phù hợp với hệ điều hành.

Kiểm tra agent đang hoạt động và khóa đã nạp:

```bash
ssh-add -l
```

Nếu nhận thông báo không có identity, hãy nạp khóa bằng `ssh-add`. Nếu báo không kết nối được agent, kiểm tra agent đã chạy và biến `SSH_AUTH_SOCK` có trỏ đến socket của agent trong phiên hiện tại hay không.

## 6. Khởi động ssh-agent trên Windows

Windows 10/11 có thể dùng OpenSSH Authentication Agent service nếu thành phần OpenSSH Client đã được cài. Kiểm tra dịch vụ trong PowerShell:

```powershell
Get-Service ssh-agent
```

Nếu dịch vụ đã có, mở PowerShell với quyền quản trị để đặt chế độ tự khởi động và khởi chạy dịch vụ:

```powershell
Set-Service -Name ssh-agent -StartupType Automatic
Start-Service ssh-agent
```

Sau đó mở terminal dưới tài khoản người dùng của bạn và nạp private key:

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
ssh-add -l
```

Nếu `Get-Service` không tìm thấy `ssh-agent`, hãy kiểm tra tính năng OpenSSH Client trong Windows Optional Features hoặc cài đặt thành phần OpenSSH theo hướng dẫn của phiên bản Windows đang dùng. Thay đổi startup type có thể cần quyền quản trị.

PowerShell, Windows Terminal, Git Bash và các ứng dụng khác có thể dùng những bản OpenSSH khác nhau. Nếu `ssh-add` nạp khóa vào một agent nhưng Git lại không nhìn thấy, kiểm tra đường dẫn `ssh` và `ssh-add` đang được gọi:

```powershell
Get-Command ssh
Get-Command ssh-add
```

Nên dùng nhất quán cùng bộ OpenSSH và agent trong môi trường làm việc để tránh nhầm lẫn giữa nhiều tiến trình hoặc socket.

## 7. Chọn đúng khóa bằng ~/.ssh/config

Nếu bạn có nhiều tài khoản hoặc nhiều khóa, cấu hình SSH giúp chọn đúng identity cho từng host. Ví dụ file `~/.ssh/config`:

```sshconfig
Host git-work
    HostName git.example.com
    User git
    IdentityFile ~/.ssh/id_ed25519_work
    IdentitiesOnly yes

Host git-personal
    HostName git.example.net
    User git
    IdentityFile ~/.ssh/id_ed25519_personal
    IdentitiesOnly yes
```

`Host` là bí danh do bạn chọn; `HostName` là hostname thật; `User` thường là `git` với dịch vụ Git hosting; `IdentityFile` chỉ rõ private key; `IdentitiesOnly yes` yêu cầu SSH ưu tiên các identity đã cấu hình cho host đó, tránh thử quá nhiều khóa đang có trong agent.

Sau đó có thể cấu hình remote bằng alias:

```bash
git remote set-url origin git@git-work:platform/storefront.git
```

Kiểm tra cấu hình hiệu lực:

```bash
ssh -G git-work
```

Lệnh này hiển thị cấu hình mà SSH áp dụng cho alias. Nếu máy chủ dùng cổng khác 22, thêm `Port` trong block `Host`:

```sshconfig
Host git-internal
    HostName git.example.com
    User git
    Port 2222
    IdentityFile ~/.ssh/id_ed25519_work
    IdentitiesOnly yes
```

Với cổng không mặc định, mục host trong `known_hosts` thường có dạng `[git.example.com]:2222`. Hãy dùng đúng hostname và port mà client thực sự kết nối.

## 8. Host key và dấu vân tay máy chủ

Khi kết nối SSH lần đầu, client thường chưa có host key của máy chủ trong `known_hosts`. OpenSSH có thể hiển thị thông tin dạng:

```text
The authenticity of host 'git.example.com' can't be established.
ED25519 key fingerprint is SHA256:...
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

Đây là thời điểm cần xác minh fingerprint. Hãy lấy fingerprint chuẩn từ tài liệu bảo mật chính thức của nhà cung cấp hoặc quản trị viên qua một kênh độc lập, chẳng hạn cổng quản trị HTTPS đã xác thực hoặc kênh liên lạc nội bộ đã được xác minh. So sánh toàn bộ chuỗi `SHA256:...`, đồng thời kiểm tra đúng hostname và thuật toán.

Không chấp nhận chỉ vì hostname trông quen thuộc hoặc vì người khác trong nhóm đã bấm `yes`. Nếu fingerprint khớp nguồn tin cậy, xác nhận kết nối; OpenSSH sẽ lưu host key vào `known_hosts` để so sánh ở các lần sau.

### Lấy fingerprint để so sánh trước khi kết nối

Có thể truy vấn public host key bằng `ssh-keyscan`, lưu ra file tạm và tính fingerprint:

```bash
ssh-keyscan -t ed25519 git.example.com > /tmp/git.example.com.keys
ssh-keygen -lf /tmp/git.example.com.keys -E sha256
```

So sánh fingerprint vừa tính với fingerprint chính thức do quản trị viên hoặc nhà cung cấp công bố. Chỉ sau khi xác minh mới thêm đúng key đã kiểm tra vào `known_hosts`:

```bash
cat /tmp/git.example.com.keys >> ~/.ssh/known_hosts
```

`ssh-keyscan` chỉ thu thập public key mà máy chủ đang trình bày tại thời điểm truy vấn. Bản thân nó không xác thực rằng key đó thuộc về máy chủ thật; nếu kẻ tấn công đứng giữa kết nối, `ssh-keyscan` cũng có thể thu được key của kẻ đó. Vì vậy, bước so sánh với fingerprint lấy từ một kênh độc lập là bắt buộc.

Nếu nhà cung cấp công bố nhiều thuật toán host key, hãy truy vấn và xác minh đúng loại key mà client sẽ sử dụng. Không tự suy ra fingerprint chuẩn từ chính kết quả `ssh-keyscan` rồi coi đó là xác minh.

## 9. known_hosts lưu điều gì?

`known_hosts` lưu public host key mà máy khách đã chấp nhận cho một hostname/port. Mặc định, file thường nằm tại:

```text
Linux/macOS: ~/.ssh/known_hosts
Windows:     %USERPROFILE%\.ssh\known_hosts
```

Tìm host key đã lưu:

```bash
ssh-keygen -F git.example.com -f ~/.ssh/known_hosts
```

Tính fingerprint từ các host key đã lưu:

```bash
ssh-keygen -lf ~/.ssh/known_hosts -E sha256
```

OpenSSH có thể băm hostname trong `known_hosts` để giảm việc lộ danh sách máy chủ trong file. `ssh-keygen -F` vẫn có thể tìm host đã băm khi được cung cấp đúng hostname.

Bạn có thể yêu cầu SSH chỉ kết nối nếu host key đã có trong danh sách tin cậy:

```sshconfig
Host git.example.com
    StrictHostKeyChecking yes
```

Với chế độ này, hãy thêm host key đã được xác minh vào `known_hosts` trước khi kết nối. `StrictHostKeyChecking accept-new` có thể tự chấp nhận host mới lần đầu và từ chối host key thay đổi về sau; nó hữu ích cho một số môi trường tự động hóa nhưng không thay thế việc xác minh fingerprint độc lập trong quy trình bảo mật nghiêm ngặt.

## 10. Xử lý cảnh báo host key thay đổi

Nếu máy chủ thay host key, hoặc bạn kết nối nhầm máy chủ, OpenSSH có thể hiển thị cảnh báo:

```text
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
```

Đây là cảnh báo bảo mật quan trọng. Nguyên nhân có thể là quản trị viên đã xoay vòng host key, máy chủ được thay mới, DNS/địa chỉ IP thay đổi hoặc có nguy cơ bị tấn công trung gian. Không xóa cảnh báo bằng cách bỏ qua kiểm tra hoặc tự động chấp nhận key mới.

Quy trình xử lý:

1. Dừng kết nối và xác minh với quản trị viên/nhà cung cấp xem host key có vừa được thay đổi hay không.
2. Lấy fingerprint mới qua kênh độc lập và so sánh chính xác.
3. Nếu thay đổi hợp lệ, sao lưu `known_hosts` nếu cần và xóa entry cũ cho đúng host.
4. Thêm host key mới đã được xác minh, rồi kết nối lại.

Xóa entry của hostname mặc định:

```bash
ssh-keygen -R git.example.com
```

Với cổng không mặc định:

```bash
ssh-keygen -R '[git.example.com]:2222'
```

Sau đó thêm key mới đã xác minh hoặc kết nối lại và kiểm tra fingerprint trước khi chấp nhận. `ssh-keygen -R` chỉ xóa bản ghi local tương ứng; lệnh này không xác minh key mới và không sửa lỗi DNS hoặc máy chủ.

## 11. Kiểm tra kết nối và chẩn đoán lỗi

Thử xác thực SSH:

```bash
ssh -T git@git.example.com
```

Nếu cần xem quá trình chọn key và xác thực:

```bash
ssh -vT git@git.example.com
```

Thông tin debug có thể cho biết SSH đang đọc file config nào, thử identity nào, có kết nối agent hay không và máy chủ phản hồi ra sao. Không chia sẻ log debug công khai nếu trong đó có hostname nội bộ, username hoặc thông tin nhạy cảm.

Một số lỗi thường gặp:

| Thông báo | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Permission denied (publickey)` | Public key chưa được đăng ký, client chọn sai private key hoặc agent chưa nạp key | Kiểm tra tài khoản, `IdentityFile`, `ssh-add -l` và chạy `ssh -vT` |
| `Host key verification failed` | Host key chưa có trong `known_hosts` hoặc không khớp | Xác minh fingerprint từ nguồn tin cậy, rồi thêm key đúng |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | Host key đã đổi hoặc kết nối đến máy chủ khác | Dừng lại, xác minh thay đổi trước khi cập nhật `known_hosts` |
| `Too many authentication failures` | SSH thử quá nhiều khóa từ agent | Dùng `IdentitiesOnly yes` và chỉ định `IdentityFile` đúng |
| `Could not open a connection to your authentication agent` | Agent chưa chạy hoặc shell không có socket/biến môi trường đúng | Khởi động agent trong phiên hiện tại và nạp lại key |
| `sign_and_send_pubkey: signing failed` | Agent không ký được, khóa bị khóa hoặc không tương thích | Kiểm tra agent, passphrase, quyền file và loại khóa |
| Timeout hoặc connection refused | Sai hostname/port, firewall hoặc máy chủ không nhận SSH | Kiểm tra URL remote, VPN, firewall và cổng dịch vụ |

Nếu `ssh -T` xác thực thành công nhưng `git ls-remote origin` bị từ chối, kiểm tra URL repository và quyền đọc. Nếu fetch được nhưng push thất bại, kiểm tra quyền ghi, branch protection và chính sách của remote.

## 12. Lưu ý bảo mật khi dùng agent và SSH

- Dùng passphrase cho private key và chỉ nạp khóa vào agent trong khoảng thời gian cần thiết.
- Tạo khóa riêng cho công việc và mục đích khác nhau khi chính sách yêu cầu; thu hồi khóa của thiết bị đã mất hoặc không còn sử dụng.
- Chỉ đăng ký public key. Không gửi private key hoặc passphrase cho quản trị viên.
- Xác minh host key ở lần kết nối đầu tiên và khi có cảnh báo thay đổi.
- Hạn chế `ForwardAgent yes`. Agent forwarding cho phép máy từ xa yêu cầu agent local ký trong thời gian phiên được chuyển tiếp; nếu máy từ xa không đáng tin, điều này có thể bị lạm dụng dù private key không rời khỏi máy bạn.
- Không bật agent forwarding toàn cục. Nếu thật sự cần, giới hạn cho host cụ thể và chỉ dùng với máy chủ đáng tin.
- Giữ OpenSSH và Git LFS/Git được cập nhật theo chính sách của hệ điều hành và tổ chức.
- Không tắt `StrictHostKeyChecking` để xử lý lỗi kết nối. Hãy xác minh và sửa đúng host key.

## 13. Quy trình thiết lập SSH cho một repository

Một quy trình thường dùng cho máy phát triển mới:

1. Kiểm tra `~/.ssh` hoặc `%USERPROFILE%\.ssh` để xác định khóa hiện có.
2. Tạo khóa Ed25519 mới với passphrase nếu cần.
3. Đăng ký public key `.pub` vào tài khoản hoặc deploy key được cấp quyền.
4. Khởi động `ssh-agent`, nạp private key và kiểm tra bằng `ssh-add -l`.
5. Lấy fingerprint host key từ nguồn chính thức; xác minh rồi lưu vào `known_hosts`.
6. Chạy `ssh -T git@<host>` để kiểm tra xác thực tài khoản.
7. Cấu hình remote URL dạng SSH và chạy `git ls-remote origin` để kiểm tra quyền đọc repository.

Ví dụ cấu hình remote:

```bash
git remote set-url origin git@git.example.com:platform/storefront.git
git remote -v
git ls-remote origin
```

Nếu tổ chức dùng host alias hoặc cổng SSH riêng, cấu hình `~/.ssh/config` trước rồi dùng alias trong URL remote. Ghi lại hostname, port và fingerprint đã xác minh theo quy trình onboarding của nhóm để thành viên khác có thể kiểm tra độc lập.

## 14. Bài tập thực hành

Thực hiện trong tài khoản và repository thử nghiệm, không dùng private key production để luyện tập:

1. Tạo một cặp khóa Ed25519 với passphrase và xác định sự khác nhau giữa file private key và `.pub`.
2. Đăng ký public key vào tài khoản Git thử nghiệm.
3. Khởi động `ssh-agent`, nạp khóa bằng `ssh-add` và kiểm tra bằng `ssh-add -l`.
4. Lấy host key bằng `ssh-keyscan`, tính fingerprint của file đã lưu bằng `ssh-keygen -lf /tmp/git.example.com.keys -E sha256` và so sánh với fingerprint do nhà cung cấp công bố qua kênh độc lập.
5. Lưu host key đã xác minh vào `known_hosts`, rồi thử kết nối với `StrictHostKeyChecking yes`.
6. Cấu hình host alias trong `~/.ssh/config` để chọn một private key cụ thể.
7. Chạy `ssh -vT` và `git ls-remote origin`; giải thích lệnh nào kiểm tra xác thực SSH và lệnh nào kiểm tra quyền đọc repository.
8. Trong môi trường thử nghiệm, xem cách `ssh-keygen -R` xóa một entry cũ; giải thích vì sao phải xác minh host key mới trước khi thêm lại.

Bạn hoàn thành bài tập khi phân biệt được client key và host key, sử dụng được `ssh-agent`, xác minh fingerprint trước khi tin cậy máy chủ và xử lý được cảnh báo host key thay đổi theo quy trình an toàn.

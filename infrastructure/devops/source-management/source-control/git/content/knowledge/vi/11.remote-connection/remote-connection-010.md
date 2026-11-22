# Chẩn đoán lỗi URL, DNS, proxy, chứng chỉ và kết nối SSH

Khi Git không thể trao đổi với repository từ xa, thông báo lỗi thường xuất hiện ở lệnh `git clone`, `git fetch`, `git pull` hoặc `git push`. Nguyên nhân có thể nằm ở địa chỉ remote, phân giải tên miền, đường truyền TCP, proxy, chứng chỉ TLS, xác thực hoặc quyền truy cập repository. Với kết nối SSH, lỗi còn có thể đến từ cổng SSH, khóa riêng, `ssh-agent` hoặc danh sách host key đã tin cậy.

Muốn tìm đúng nguyên nhân, hãy kiểm tra theo từng lớp từ ngoài vào trong: xác nhận URL và tên host, kiểm tra DNS và cổng mạng, kiểm tra proxy/TLS, sau đó kiểm tra xác thực và quyền truy cập Git. Mỗi bước nên dùng một lệnh nhỏ để xác định lớp nào đang lỗi trước khi thay đổi cấu hình.

Trong dịch vụ quản lý mã nguồn Git, remote là điểm kết nối để các thành viên trao đổi commit và nhánh. Việc chẩn đoán có hệ thống giúp khôi phục hoạt động cộng tác, tránh thay đổi nhầm remote hoặc làm suy yếu bảo mật của kết nối.

## 1. Hiểu các lớp của một kết nối Git

Một lệnh Git qua mạng thường đi qua các bước sau:

1. Git xác định URL cần dùng từ cấu hình remote, URL rewrite và cấu hình fetch/push.
2. Hệ điều hành phân giải hostname thành địa chỉ IP qua DNS.
3. Máy khách mở kết nối TCP tới máy chủ hoặc proxy trên cổng phù hợp.
4. Với HTTPS, hai bên thương lượng TLS và kiểm tra chứng chỉ máy chủ; với SSH, hai bên thương lượng giao thức và xác minh host key.
5. Git thực hiện xác thực người dùng hoặc khóa SSH.
6. Máy chủ kiểm tra repository có tồn tại và tài khoản có quyền đọc hoặc ghi hay không.

Một lỗi ở bước trước có thể khiến các bước sau chưa diễn ra. Ví dụ, lỗi `Could not resolve host` xảy ra trước khi Git có thể xác thực; lỗi `Permission denied (publickey)` cho thấy kết nối SSH đã tới được máy chủ nhưng xác thực bằng khóa chưa thành công.

```text
URL remote
   |
   v
DNS phân giải hostname
   |
   v
TCP tới cổng máy chủ/proxy
   |
   +---- HTTPS: TLS + kiểm tra chứng chỉ
   |
   +---- SSH: trao đổi SSH + xác minh host key
   |
   v
Xác thực tài khoản/khóa
   |
   v
Kiểm tra repository và quyền đọc/ghi
```

Không phải lệnh kiểm tra nào cũng chứng minh toàn bộ đường đi hoạt động. `Resolve-DnsName` chỉ kiểm tra DNS; `Test-NetConnection` kiểm tra khả năng mở TCP; `curl.exe -Iv` kiểm tra kết nối HTTPS ở mức HTTP/TLS; `git ls-remote` kiểm tra thêm giao thức Git, xác thực và quyền đọc repository.

## 2. Bắt đầu bằng URL và cấu hình remote

Trước tiên, xác định remote nào đang lỗi và URL nào thực sự được sử dụng. Ví dụ dưới đây dùng remote `origin`; thay tên này bằng remote trong dự án của bạn.

```bash
git remote -v
git remote get-url --all origin
git remote get-url --push --all origin
```

`git remote -v` hiển thị URL fetch và push. Hai URL có thể khác nhau nếu repository được cấu hình `pushurl`. Hai lệnh `git remote get-url` cho biết URL sau khi Git áp dụng các quy tắc viết lại URL; lệnh thứ hai lấy URL push. Vì vậy, chỉ nhìn một URL có thể bỏ sót việc fetch đang đi tới máy chủ này còn push đi tới máy chủ khác.

Có thể xem các giá trị cấu hình cùng nguồn khai báo:

```bash
git config --show-origin --get-regexp '^remote\..*\.(url|pushurl)$'
git config --show-origin --get-regexp '^url\..*\.insteadof$'
```

Kết quả `--show-origin` cho biết cấu hình đến từ file nào, chẳng hạn `.git/config`, file cấu hình người dùng hoặc cấu hình hệ thống. Quy tắc `url.<base>.insteadOf` có thể tự động thay tiền tố URL, khiến địa chỉ được dùng khác với chuỗi bạn nghĩ mình đã cấu hình.

### Nhận biết cú pháp URL

Ba dạng thường gặp:

```text
HTTPS:       https://git.example.com/team/project.git
SSH URI:     ssh://git@git.example.com:22/team/project.git
SSH SCP-like: git@git.example.com:team/project.git
```

- HTTPS thường dùng cổng `443` và xác thực bằng token, OAuth hoặc credential manager tùy nhà cung cấp.
- SSH URI ghi rõ giao thức và có thể ghi cổng sau hostname.
- Dạng SCP-like dùng dấu hai chấm sau hostname để phân cách đường dẫn repository; đây là cú pháp Git/SSH quen thuộc, không phải URL SCP đầy đủ.

Một số lỗi URL thường gặp:

- Gõ sai hostname, tên nhóm hoặc tên repository.
- Dùng dấu `/` thay cho dấu `:` trong dạng SCP-like, ví dụ `git@git.example.com/team/project.git`.
- Thiếu tên người dùng SSH hoặc dùng sai cổng SSH.
- URL còn trỏ tới repository cũ sau khi dự án được chuyển nhóm hoặc đổi máy chủ.
- Có khoảng trắng, ký tự đặc biệt hoặc dấu gạch chéo thừa trong đường dẫn.
- URL fetch đúng nhưng `pushurl` vẫn trỏ tới một remote cũ.

Tên repository có phân biệt chữ hoa/chữ thường hay không phụ thuộc máy chủ. Một số dịch vụ tự chuyển hướng URL cũ, nhưng không nên dựa vào chuyển hướng để thay thế việc cập nhật remote chính xác.

### Sửa URL khi đã xác định địa chỉ đúng

```bash
git remote set-url origin https://git.example.com/team/project.git
```

Nếu chỉ cần thay URL dùng cho push:

```bash
git remote set-url --push origin git@git.example.com:team/project.git
```

Các lệnh này thay cấu hình local, không tự kiểm tra URL mới có kết nối được hay không. Sau khi sửa, đọc lại URL và kiểm tra bằng `git ls-remote origin`.

**Lưu ý bảo mật:** URL remote đôi khi chứa username hoặc token nếu ai đó đã nhúng thông tin xác thực vào URL. Trước khi chia sẻ kết quả `git remote -v`, hãy kiểm tra và che mọi token, mật khẩu, thông tin nội bộ hoặc hostname riêng tư. Không nên lưu token trực tiếp trong URL vì token có thể xuất hiện trong file cấu hình, log hoặc ảnh chụp màn hình.

## 3. Kiểm tra DNS và hostname

DNS chuyển hostname, ví dụ `git.example.com`, thành địa chỉ IP. Nếu DNS không phân giải được, Git thường báo:

```text
fatal: unable to access 'https://git.example.com/...':
Could not resolve host: git.example.com
```

Đầu tiên, xác nhận hostname được trích từ URL remote là chính xác. Sau đó kiểm tra phân giải tên miền.

### Trên Windows PowerShell

```powershell
Resolve-DnsName git.example.com
nslookup git.example.com
```

### Trên Linux hoặc macOS

```bash
dig +short git.example.com
nslookup git.example.com
```

Trên Linux, có thể dùng thêm `getent hosts git.example.com` để kiểm tra phân giải qua resolver hệ thống; lệnh `getent` thường không có sẵn mặc định trên macOS.

Nếu lệnh trả về địa chỉ IP, DNS đã phân giải hostname ở thời điểm kiểm tra. Nếu nhận `NXDOMAIN`, tên miền có thể sai hoặc bản ghi không tồn tại trong DNS mà máy đang dùng. Nếu truy vấn hết thời gian, có thể DNS resolver không phản hồi, VPN chưa kết nối hoặc mạng đang chặn truy vấn DNS.

Trong mạng doanh nghiệp, một hostname nội bộ có thể chỉ phân giải được khi kết nối VPN hoặc dùng DNS nội bộ. Nếu dịch vụ có nhiều vùng mạng, DNS split-horizon có thể trả về địa chỉ khác nhau tùy vị trí. Hãy xác nhận VPN, mạng đang dùng và DNS resolver theo hướng dẫn của đơn vị quản trị.

`ping` không phải phép kiểm tra DNS hay TCP đáng tin cậy duy nhất. Máy chủ có thể chặn ICMP nhưng vẫn nhận kết nối HTTPS/SSH; ping thất bại không chứng minh Git server không hoạt động. Hãy kiểm tra đúng cổng dịch vụ ở bước tiếp theo.

## 4. Kiểm tra kết nối TCP và cổng dịch vụ

Sau khi có hostname, kiểm tra máy có mở được kết nối tới cổng cần thiết hay không. HTTPS thường dùng cổng `443`; SSH thường dùng cổng `22`, nhưng máy chủ có thể cấu hình cổng khác. Nếu Git đi qua proxy, đường TCP từ máy của bạn trước hết tới hostname và cổng proxy; hãy kiểm tra proxy thay vì chỉ kiểm tra trực tiếp máy chủ đích. Ví dụ proxy là `proxy.example.com:8080`, hãy thử TCP tới `proxy.example.com` trên cổng `8080`.

### Trên Windows PowerShell

```powershell
Test-NetConnection git.example.com -Port 443
Test-NetConnection git.example.com -Port 22
```

Xem trường `TcpTestSucceeded`. `True` nghĩa là TCP handshake tới cổng đó thành công; nó chưa chứng minh TLS, xác thực Git hoặc quyền repository hoạt động. `False` có thể do sai hostname/cổng, firewall, VPN, proxy, route mạng hoặc dịch vụ không lắng nghe.

### Trên Linux hoặc macOS

```bash
nc -vz git.example.com 443
nc -vz git.example.com 22
```

Nếu `nc` không được cài đặt, dùng công cụ kiểm tra mạng sẵn có của hệ điều hành hoặc yêu cầu quản trị mạng kiểm tra đường đi và cổng. Không tự mở firewall hoặc thay đổi route trên máy công ty nếu chưa được cấp quyền.

Phân biệt một số kết quả:

- **Connection timed out:** không nhận được phản hồi trong thời gian chờ; thường liên quan firewall, VPN, route, proxy hoặc cổng bị lọc.
- **Connection refused:** máy đích có thể tới được nhưng cổng không có dịch vụ lắng nghe hoặc máy chủ chủ động từ chối.
- **Connection reset:** kết nối bị đóng đột ngột; có thể do proxy, firewall, thiết bị bảo mật hoặc máy chủ.
- **TCP thành công:** chuyển sang kiểm tra TLS/SSH và xác thực.

## 5. Chẩn đoán proxy HTTP/HTTPS

Trong mạng công ty, lưu lượng HTTPS có thể phải đi qua proxy. Proxy sai địa chỉ, sai cổng hoặc thiếu xác thực có thể khiến `git fetch` và `git push` thất bại dù DNS và mạng nội bộ vẫn hoạt động.

### Kiểm tra proxy trong cấu hình Git

```bash
git config --show-origin --get-all http.proxy
git config --show-origin --get-regexp '^http\..*\.proxy$'
```

Lệnh đầu kiểm tra cấu hình `http.proxy`; lệnh sau kiểm tra các proxy được đặt theo URL cụ thể. Cấu hình theo URL có thể khiến một máy chủ dùng proxy riêng trong khi máy chủ khác không dùng.

Git cũng có thể nhận proxy qua biến môi trường. Tên thường gặp là `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` và `NO_PROXY` (một số chương trình còn đọc biến chữ thường). Hãy kiểm tra giá trị ngay trên máy của mình và che username, password hoặc token trước khi chia sẻ. `NO_PROXY` liệt kê host/domain cần truy cập trực tiếp thay vì qua proxy.

### Thử một proxy cho đúng một lệnh

Nếu quản trị mạng đã cung cấp địa chỉ proxy, có thể thử tạm thời mà không lưu cấu hình lâu dài:

```bash
git -c http.proxy=http://proxy.example.com:8080 ls-remote origin
```

Thiết lập này áp dụng cho remote dùng HTTP/HTTPS; nó không chuyển remote SSH qua proxy.

Nếu lệnh tạm thời hoạt động trong khi lệnh thường thất bại, cấu hình proxy mặc định có thể sai hoặc chưa được đặt. Địa chỉ, cổng và cách xác thực phải theo thông tin của tổ chức. Tránh ghi username/password trực tiếp trong câu lệnh vì lịch sử terminal và log có thể lưu lại chúng.

### Đọc lỗi proxy

| Thông báo hoặc dấu hiệu | Khả năng cần kiểm tra |
| --- | --- |
| `407 Proxy Authentication Required` | Proxy yêu cầu xác thực; kiểm tra tài khoản hoặc cơ chế xác thực proxy |
| `Could not resolve proxy` | Hostname của proxy không phân giải được hoặc URL proxy sai |
| `Failed to connect to proxy` | Sai cổng, proxy ngừng hoạt động hoặc đường mạng tới proxy bị chặn |
| `502 Bad Gateway` / `504 Gateway Timeout` | Proxy hoặc gateway không lấy được phản hồi từ máy chủ đích |
| Kết nối HTTPS chỉ lỗi khi ở mạng công ty | Kiểm tra proxy TLS inspection và CA doanh nghiệp |

Nếu cần bỏ một proxy đã cấu hình sai, hãy xác định nguồn cấu hình trước. Ví dụ, chỉ khi giá trị sai nằm trong cấu hình global:

```bash
git config --global --unset http.proxy
```

Nếu cấu hình nằm trong `.git/config`, dùng `--local`; nếu đến từ file hệ thống hoặc biến môi trường, cần xử lý ở đúng nguồn đó. Không xóa proxy toàn cục của máy công ty chỉ vì một repository gặp lỗi.

Proxy cho HTTPS và proxy cho SSH là hai cấu hình khác nhau. `http.proxy` không tự chuyển lưu lượng SSH qua proxy. Với SSH, tổ chức có thể yêu cầu `ProxyJump`, `ProxyCommand` hoặc một cổng SSH riêng trong cấu hình OpenSSH.

## 6. Chẩn đoán lỗi chứng chỉ TLS khi dùng HTTPS

Khi remote dùng HTTPS, Git xác minh chứng chỉ TLS để đảm bảo đang kết nối tới máy chủ đúng và dữ liệu không bị giả mạo. Nếu chuỗi chứng chỉ không đáng tin, hostname không khớp hoặc chứng chỉ hết hạn, Git có thể báo:

```text
SSL certificate problem: unable to get local issuer certificate
SSL: certificate subject name does not match target host name
certificate has expired
```

### Xác định nguyên nhân

1. Kiểm tra URL có đúng hostname và đúng dịch vụ hay không.
2. Kiểm tra ngày, giờ và múi giờ của máy. Đồng hồ sai có thể khiến chứng chỉ hợp lệ bị xem là chưa có hiệu lực hoặc đã hết hạn.
3. Kiểm tra máy có dùng proxy kiểm tra TLS (TLS inspection) hay không. Proxy loại này có thể thay chứng chỉ máy chủ bằng chứng chỉ do CA nội bộ ký.
4. Xác nhận chuỗi CA gốc/trung gian của dịch vụ hoặc CA doanh nghiệp đã được cài vào trust store phù hợp.
5. So sánh kết quả từ Git với trình duyệt hoặc `curl.exe`; Git có thể dùng TLS backend hoặc trust store khác trình duyệt.

Có thể kiểm tra HTTPS độc lập với giao thức Git:

```powershell
curl.exe -Iv https://git.example.com
```

Trên Linux hoặc macOS:

```bash
curl -Iv https://git.example.com
```

Lệnh này giúp quan sát quá trình kết nối TLS và phản hồi HTTP của máy chủ. Một mã HTTP như `200`, `301`, `401` hoặc `403` vẫn cho thấy TLS/HTTP đã phản hồi; nó chưa chứng minh tài khoản có quyền truy cập repository Git. Nếu `curl` thành công nhưng Git thất bại, hãy kiểm tra TLS backend, CA path và cấu hình Git.

### Kiểm tra cấu hình TLS của Git

```bash
git config --show-origin --get http.sslBackend
git config --show-origin --get http.sslCAInfo
git config --show-origin --get http.sslCAPath
git config --show-origin --get http.sslVerify
```

`http.sslVerify` mặc định là bật. Nếu cấu hình CA riêng được đặt sai đường dẫn hoặc trỏ tới file CA không còn phù hợp, Git có thể không xác minh được máy chủ. `http.sslBackend` cho biết backend TLS được cấu hình nếu có; trên Git for Windows, backend có thể ảnh hưởng trust store được sử dụng.

Nếu tổ chức cấp CA nội bộ dưới dạng PEM, hãy lấy file từ nguồn quản trị đáng tin cậy và cấu hình đường dẫn theo hướng dẫn của họ, ví dụ:

```bash
git config --global http.sslCAInfo /path/to/company-ca-bundle.pem
```

Đường dẫn trên chỉ là ví dụ; Windows có thể dùng đường dẫn dạng `C:/certs/company-ca-bundle.pem`. Chỉ cấu hình CA mà bạn đã xác minh nguồn và dấu vân tay. Nếu Git for Windows cần dùng kho chứng chỉ Windows, hãy hỏi quản trị viên về backend phù hợp; không thay TLS backend một cách tùy tiện.

**Không khắc phục bằng cách tắt xác minh chứng chỉ.** Không đặt `http.sslVerify=false`, `GIT_SSL_NO_VERIFY` hoặc tùy chọn tương đương để tiếp tục dùng kết nối không xác minh. Cách này mở đường cho tấn công giả mạo máy chủ và có thể làm lộ thông tin xác thực. Hãy sửa hostname, đồng hồ, CA hoặc cấu hình proxy để khôi phục xác minh đúng.

## 7. Chẩn đoán kết nối SSH

SSH thường được dùng khi remote có dạng `git@host:group/repository.git`. Khi lỗi xảy ra, hãy tách việc kiểm tra thành ba phần: TCP tới cổng SSH, xác minh host key và xác thực bằng khóa người dùng.

### Kiểm tra URL và cổng SSH

```bash
git remote get-url origin
```

Xác định hostname và cổng từ URL. Nếu URL dạng SCP-like, cổng mặc định thường là `22` trừ khi cấu hình SSH chỉ định cổng khác. Kiểm tra TCP trên cổng tương ứng bằng `Test-NetConnection` hoặc `nc` ở phần trước.

### Kiểm tra bắt tay và xác thực SSH

```bash
ssh -T git@git.example.com
ssh -vT git@git.example.com
```

`ssh -T` thử xác thực mà không mở shell tương tác. Nhiều máy chủ Git trả thông báo xác thực thành công nhưng vẫn kết thúc với mã thoát khác 0 vì tài khoản Git không được cấp shell; hãy đọc nội dung phản hồi thay vì chỉ dựa vào exit code. `-vT` bật log chi tiết để xem SSH đang dùng cấu hình, khóa và phương thức xác thực nào.

Không gửi log SSH nguyên bản lên kênh công khai. Log có thể chứa username, hostname nội bộ, đường dẫn khóa và thông tin hạ tầng; hãy che các dữ liệu đó trước khi chia sẻ.

### Kiểm tra khóa và ssh-agent

Liệt kê khóa công khai đang có trong agent:

```bash
ssh-add -l
```

Nếu không có identity nào được nạp, có thể nạp khóa riêng đã tạo cho tài khoản:

```bash
ssh-add ~/.ssh/id_ed25519
```

Trên Windows PowerShell, đường dẫn khóa thường nằm dưới thư mục hồ sơ người dùng, ví dụ:

```powershell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

Tên khóa có thể khác. Không tạo hoặc nạp khóa mới trước khi xác định khóa nào được tổ chức hoặc dịch vụ Git yêu cầu. Đối chiếu fingerprint của khóa công khai với khóa đã đăng ký trên tài khoản:

```bash
ssh-keygen -lf ~/.ssh/id_ed25519.pub
```

Thông báo `Permission denied (publickey)` thường có nghĩa máy chủ không chấp nhận khóa được gửi. Kiểm tra khóa công khai đã đăng ký đúng tài khoản chưa, agent có nạp đúng khóa không, `IdentityFile` có trỏ đúng file không và tài khoản có quyền với repository không. Không gửi file khóa riêng (thường không có đuôi `.pub`) cho bất kỳ ai.

Trên Windows, nếu OpenSSH agent không chạy, có thể kiểm tra trạng thái dịch vụ:

```powershell
Get-Service ssh-agent
```

Việc bật hoặc thay đổi dịch vụ có thể cần quyền quản trị và chính sách máy. Hãy làm theo hướng dẫn quản trị thiết bị thay vì tự ý thay đổi cấu hình dịch vụ trên máy công ty.

### Kiểm tra cấu hình SSH hiệu lực

OpenSSH có thể lấy cấu hình từ `~/.ssh/config`, cấu hình hệ thống, tham số dòng lệnh và agent. Dùng:

```bash
ssh -G git@git.example.com
```

Lệnh hiển thị cấu hình hiệu lực, gồm hostname, user, port và identity file. Để cấu hình riêng cho máy chủ, có thể thêm một mục vào `~/.ssh/config`:

```sshconfig
Host git-company
    HostName git.example.com
    User git
    Port 22
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

Sau đó remote có thể dùng alias:

```bash
git remote set-url origin git@git-company:team/project.git
ssh -T git-company
```

`IdentitiesOnly yes` yêu cầu SSH ưu tiên identity được khai báo thay vì thử mọi khóa trong agent. Chỉ đặt khi đã xác định đúng khóa cần dùng.

Nếu mạng chặn cổng 22, hãy hỏi nhà cung cấp dịch vụ hoặc quản trị mạng xem có endpoint SSH trên cổng khác hay SSH qua cổng 443 được hỗ trợ không. Không tự giả định cổng 443 nhận SSH; endpoint và hostname phải do dịch vụ công bố. Nếu phải đi qua máy trung gian, quản trị viên có thể cung cấp cấu hình `ProxyJump` hoặc `ProxyCommand`.

### Xác minh host key và known_hosts

Ở lần kết nối SSH đầu tiên, OpenSSH có thể hỏi có tin cậy fingerprint host key hay không. Chỉ chấp nhận sau khi đối chiếu fingerprint với tài liệu chính thức hoặc quản trị viên qua một kênh đáng tin cậy.

Nếu gặp:

```text
Host key verification failed
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
```

máy chủ có thể đã thay host key hợp lệ, DNS có thể trỏ tới máy chủ khác, hoặc có nguy cơ kết nối bị giả mạo. Không bỏ qua cảnh báo và không tắt `StrictHostKeyChecking` để tiếp tục.

Kiểm tra bản ghi đã lưu:

```bash
ssh-keygen -F git.example.com
```

Chỉ sau khi xác minh fingerprint mới qua nguồn tin cậy, mới xóa bản ghi cũ để OpenSSH hỏi lại:

```bash
ssh-keygen -R git.example.com
```

Nếu dùng cổng không mặc định, tên bản ghi có thể ở dạng `[git.example.com]:2222`; cần kiểm tra và xử lý đúng hostname/cổng. Không xóa toàn bộ `known_hosts` chỉ để xử lý một cảnh báo.

## 8. Phân biệt lỗi kết nối với lỗi xác thực và quyền repository

Khi DNS, TCP và TLS/SSH đã hoạt động, Git vẫn có thể từ chối do thông tin xác thực hoặc quyền truy cập.

| Thông báo | Hướng kiểm tra |
| --- | --- |
| `Authentication failed` | Token hết hạn/sai, thông tin cũ trong credential manager hoặc cơ chế xác thực đã thay đổi |
| `HTTP 401` | Chưa xác thực hoặc thông tin xác thực không hợp lệ |
| `HTTP 403` | Có thể đã xác thực nhưng tài khoản/token không có quyền hoặc thiếu scope cần thiết |
| `Repository not found` | Sai đường dẫn, repository đã chuyển/xóa hoặc tài khoản không được phép nhìn thấy repository riêng tư |
| `Permission denied (publickey)` | SSH không cung cấp khóa được máy chủ chấp nhận |
| `Could not read from remote repository` | Thông báo tổng quát; kiểm tra URL, SSH/authentication và quyền đọc |
| Push bị từ chối dù fetch thành công | Tài khoản có thể chỉ có quyền đọc, nhánh được bảo vệ hoặc chính sách máy chủ từ chối cập nhật |

Với HTTPS, nhiều dịch vụ không còn cho phép dùng mật khẩu tài khoản trực tiếp qua Git. Hãy dùng cơ chế được dịch vụ hỗ trợ, thường là token cá nhân, OAuth hoặc credential manager. Token phải có quyền tối thiểu cần thiết và còn hiệu lực. Nếu thông tin cũ được lưu trong Windows Credential Manager hoặc credential helper, hãy cập nhật/xóa đúng mục của máy chủ theo hướng dẫn của công cụ quản lý thông tin xác thực.

Kiểm tra helper đang cấu hình mà không đọc nội dung bí mật:

```bash
git config --show-origin --get-all credential.helper
```

Không chạy lệnh hiển thị credential, không dán token vào câu lệnh và không gửi token, mật khẩu, private key hay file `.env` trong báo cáo lỗi.

## 9. Dùng git ls-remote để kiểm tra toàn tuyến Git

Sau khi đã kiểm tra URL và mạng, dùng `git ls-remote` để xác minh Git có thể đọc danh sách tham chiếu từ remote:

```bash
git ls-remote origin
```

Nếu lệnh trả về các dòng gồm mã object và tên ref như `refs/heads/main`, Git đã liên lạc được với remote và đọc được danh sách ref. Lệnh không tải working tree và không thay đổi nhánh hiện tại.

Một số trường hợp cần diễn giải cẩn thận:

- Lệnh thành công nhưng không in dòng nào có thể là repository rỗng hoặc chưa có ref phù hợp; kiểm tra exit code và trạng thái repository.
- `ls-remote` thành công chứng minh khả năng đọc, không chứng minh có quyền push.
- Nếu fetch URL và push URL khác nhau, `git ls-remote origin` kiểm tra URL fetch. Hãy kiểm tra URL push riêng trước khi kết luận cả hai hướng đều hoạt động.
- Nếu lệnh thất bại, thông báo thường giúp xác định lỗi nằm ở DNS, TLS, SSH, xác thực hay đường dẫn repository.

Có thể giới hạn danh sách nhánh:

```bash
git ls-remote --heads origin
```

Lệnh này chỉ hiển thị các ref nhánh. Nó hữu ích khi cần xác nhận tên nhánh trên máy chủ mà không dựa vào remote-tracking refs cũ trong local.

## 10. Quy trình chẩn đoán theo thứ tự

Khi một lệnh Git qua mạng thất bại, thực hiện quy trình sau và ghi lại kết quả của từng lớp:

### Bước 1: Ghi nhận lệnh và thông báo lỗi nguyên văn

Xác định lỗi xuất hiện khi clone, fetch, pull hay push; xác định remote đang dùng và thời điểm bắt đầu lỗi. Không suy luận chỉ từ dòng cuối nếu log có thông báo cụ thể hơn ở phía trên.

### Bước 2: Xác nhận URL thực tế

```bash
git remote -v
git remote get-url --all origin
git remote get-url --push --all origin
```

Kiểm tra hostname, đường dẫn repository, giao thức, cổng và sự khác nhau giữa fetch/push URL. Che thông tin nhạy cảm trước khi gửi log.

### Bước 3: Kiểm tra DNS và TCP

Trên Windows, dùng `Resolve-DnsName` và `Test-NetConnection`; trên Linux, dùng `getent` hoặc `dig`, còn macOS có thể dùng `dig` hoặc `nslookup`; kiểm tra cổng bằng `nc`. Nếu DNS sai, xử lý VPN hoặc DNS trước. Nếu TCP không mở được, kiểm tra cổng, firewall, route và proxy với quản trị mạng.

### Bước 4: Kiểm tra giao thức bảo mật

- Với HTTPS: dùng `curl.exe -Iv` hoặc `curl -Iv`, kiểm tra CA, đồng hồ hệ thống và proxy TLS inspection.
- Với SSH: dùng `ssh -vT`, kiểm tra cổng, cấu hình hiệu lực, agent, identity và host key.

### Bước 5: Kiểm tra xác thực và quyền

Chỉ sau khi kết nối HTTPS/SSH thành công mới kiểm tra token, credential helper, khóa công khai, quyền repository và chính sách nhánh.

### Bước 6: Xác minh lại bằng Git

```bash
git ls-remote origin
git fetch origin
```

Nếu chỉ push lỗi, kiểm tra push URL và quyền ghi riêng. Không dùng force push để thử kết nối hoặc vượt qua lỗi xác thực.

## 11. Một số tình huống thực tế

### Tình huống A: Fetch báo không phân giải được host

```text
fatal: unable to access 'https://git.example.com/team/project.git/':
Could not resolve host: git.example.com
```

Quy trình xử lý:

1. Đọc lại URL để loại trừ lỗi gõ hostname.
2. Chạy `Resolve-DnsName git.example.com` hoặc `dig +short git.example.com`.
3. Nếu là host nội bộ, xác nhận VPN và DNS nội bộ.
4. Khi DNS đã trả về IP, kiểm tra TCP cổng 443 rồi chạy lại `git ls-remote origin`.

Không thay URL bằng một IP lấy từ lần tra cứu ngẫu nhiên; máy chủ có thể dùng nhiều IP, CDN hoặc chứng chỉ TLS gắn với hostname.

### Tình huống B: HTTPS trả về 407

```text
Received HTTP code 407 from proxy after CONNECT
```

Đây là phản hồi từ proxy yêu cầu xác thực. Xác nhận proxy URL, cổng, tài khoản và phương thức xác thực với quản trị mạng. Kiểm tra `http.proxy`, proxy theo URL và biến môi trường. Không nhúng mật khẩu vào remote URL hoặc commit file cấu hình có chứa thông tin đăng nhập.

### Tình huống C: TLS báo không tìm thấy CA phát hành

```text
SSL certificate problem: unable to get local issuer certificate
```

Kiểm tra đồng hồ máy, URL hostname và việc mạng có TLS inspection không. Nếu dùng CA doanh nghiệp, nhận đúng CA bundle từ quản trị viên rồi cấu hình trust store hoặc `http.sslCAInfo` theo hướng dẫn. Giữ bật xác minh chứng chỉ trong suốt quá trình.

### Tình huống D: SSH báo Permission denied (publickey)

```text
git@git.example.com: Permission denied (publickey).
fatal: Could not read from remote repository.
```

Kiểm tra TCP tới cổng SSH, chạy `ssh-add -l`, xác nhận fingerprint khóa công khai đã đăng ký và dùng `ssh -vT git@git.example.com` để xem khóa nào được thử. Nếu có nhiều khóa, khai báo đúng `IdentityFile` và cân nhắc `IdentitiesOnly yes` trong cấu hình host.

### Tình huống E: Host key của máy chủ thay đổi

```text
WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!
```

Dừng thao tác và xác minh fingerprint mới qua thông báo thay đổi chính thức hoặc quản trị viên. Chỉ sau khi xác nhận đây là thay đổi hợp lệ mới xóa đúng bản ghi host/cổng bằng `ssh-keygen -R` rồi kết nối lại. Không tắt kiểm tra host key.

### Tình huống F: Fetch thành công nhưng push bị từ chối

Fetch thành công chỉ chứng minh quyền đọc. Hãy kiểm tra push URL, quyền ghi, token scope, khóa SSH gắn với đúng tài khoản, nhánh được bảo vệ và quy trình pull request của dự án. Máy chủ có thể cho phép clone/fetch nhưng cấm push trực tiếp vào `main`.

## 12. Những cách xử lý cần tránh

- Không tắt xác minh TLS bằng `http.sslVerify=false` hoặc `GIT_SSL_NO_VERIFY`.
- Không tắt xác minh host key bằng `StrictHostKeyChecking=no` để bỏ qua cảnh báo SSH.
- Không xóa toàn bộ `known_hosts` khi chỉ một host có thay đổi; xác minh fingerprint rồi xử lý đúng bản ghi.
- Không force push để khắc phục lỗi kết nối, DNS, proxy hoặc xác thực.
- Không đưa token hoặc mật khẩu vào URL remote, script, log hay lịch sử shell.
- Không chia sẻ private key, token, file credential hoặc log chưa được che thông tin nhạy cảm.
- Không đổi DNS, firewall, proxy hoặc dịch vụ hệ thống trên máy doanh nghiệp khi chưa hiểu tác động và chưa được cấp quyền.

## 13. Checklist kiểm tra nhanh

| Lớp | Câu hỏi | Lệnh gợi ý |
| --- | --- | --- |
| URL | Remote và fetch/push URL có đúng không? | `git remote -v` |
| Rewrite | Có quy tắc `insteadOf` thay URL không? | `git config --show-origin --get-regexp '^url\..*\.insteadof$'` |
| DNS | Hostname có phân giải được không? | `Resolve-DnsName host` / `dig host` |
| TCP | Cổng 443 hoặc cổng SSH có mở không? | `Test-NetConnection host -Port 443` / `nc -vz host 22` |
| Proxy | Git hoặc môi trường có proxy nào? | `git config --show-origin --get-all http.proxy` |
| TLS | Chứng chỉ và CA có hợp lệ không? | `curl.exe -Iv https://host` |
| SSH | Khóa và host key có đúng không? | `ssh -vT git@host`, `ssh-add -l` |
| Git/auth | Đọc được refs từ remote không? | `git ls-remote origin` |
| Permission | Có quyền ghi và đúng push URL không? | Kiểm tra push URL, credential và chính sách repository |

## 14. Thực hành

Thực hiện trên repository thử nghiệm có remote mà bạn được phép truy cập:

1. Chạy `git remote -v`, ghi lại fetch URL và push URL; xác định giao thức và hostname.
2. Dùng công cụ DNS của hệ điều hành để phân giải hostname.
3. Kiểm tra TCP tới cổng HTTPS hoặc SSH phù hợp.
4. Nếu dùng HTTPS, chạy `curl -Iv` tới hostname và quan sát quá trình TLS; nếu dùng SSH, chạy `ssh -vT` và xác định identity được thử.
5. Chạy `git ls-remote origin` để kiểm tra Git có đọc được refs hay không.
6. Thử phân tích một thông báo lỗi mẫu trong bài: lỗi thuộc DNS, TCP, proxy, TLS/host key, xác thực hay quyền repository?
7. Nếu phải sửa cấu hình trong môi trường thử nghiệm, chỉ thay đổi một yếu tố mỗi lần, ghi lại giá trị trước/sau và xác minh bằng `git ls-remote`.

Sau thực hành, hãy giải thích vì sao `Test-NetConnection` thành công chưa đủ kết luận Git hoạt động, vì sao `git ls-remote` thành công chưa chứng minh quyền push, và vì sao không nên tắt kiểm tra chứng chỉ hoặc host key để vượt qua lỗi.

## 15. Tự kiểm tra kiến thức

1. Một lỗi `Could not resolve host` xảy ra ở lớp nào? Những nguyên nhân nào cần được kiểm tra trước?
2. `Test-NetConnection host -Port 443` chứng minh điều gì và không chứng minh điều gì?
3. Vì sao fetch URL và push URL có thể khác nhau? Lệnh nào giúp kiểm tra từng URL?
4. Thông báo HTTP 407 khác HTTP 401 như thế nào?
5. Khi Git báo `unable to get local issuer certificate`, cần kiểm tra những yếu tố nào?
6. `Permission denied (publickey)` gợi ý kiểm tra agent, identity và khóa công khai ra sao?
7. Vì sao cần xác minh fingerprint host key mới trước khi xóa bản ghi cũ trong `known_hosts`?
8. `git ls-remote` thành công cho biết điều gì về quyền đọc và quyền push?
9. Vì sao tắt `http.sslVerify` hoặc `StrictHostKeyChecking` làm giảm an toàn của kết nối?

## Kết luận

Lỗi kết nối Git cần được chẩn đoán theo lớp. Hãy xác minh URL trước, kiểm tra DNS và TCP tiếp theo, rồi kiểm tra proxy cùng TLS hoặc SSH, cuối cùng mới xử lý thông tin xác thực và quyền repository. Các lệnh `git remote`, công cụ mạng của hệ điều hành, `curl`, `ssh -vT` và `git ls-remote` cung cấp bằng chứng cho từng bước. Khi thay đổi cấu hình, hãy sửa đúng nguồn gây lỗi, xác minh lại kết quả và luôn giữ xác minh chứng chỉ TLS cùng host key SSH được bật.

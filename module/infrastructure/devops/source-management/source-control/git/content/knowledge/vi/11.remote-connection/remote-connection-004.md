# Giao thức HTTPS, SSH và đường dẫn kho mã cục bộ

Khi làm việc với Git, bạn có thể lấy và gửi thay đổi đến một kho mã thông qua HTTPS, SSH hoặc một đường dẫn trên hệ thống tệp. Ba cách này chỉ khác nhau ở cách Git tìm đến kho mã và xác thực quyền truy cập. Các đối tượng Git như commit, branch và tag vẫn có cùng ý nghĩa dù bạn dùng giao thức nào.

## 1. Remote trong Git là gì?

**Remote** là một tên gợi nhớ được Git dùng để lưu địa chỉ của một kho mã khác. Remote thường trỏ đến kho mã trên dịch vụ lưu trữ như GitHub, GitLab hoặc máy chủ Git của tổ chức, nhưng cũng có thể trỏ đến một thư mục kho mã trên máy tính hoặc ổ đĩa dùng chung.

Một remote thường có hai thành phần:

- **Tên remote**: bí danh dùng trong lệnh, chẳng hạn `origin` hoặc `upstream`.
- **URL**: địa chỉ Git dùng để truy cập kho mã, chẳng hạn URL HTTPS, SSH hoặc đường dẫn cục bộ.

`origin` là tên mặc định thường được tạo khi bạn clone một kho mã. Đây chỉ là quy ước đặt tên, không phải từ khóa bắt buộc. Trong dự án có một kho mã gốc và một bản fork, nhóm thường dùng `origin` cho bản fork của mình và `upstream` cho kho mã gốc.

Xem các remote đã cấu hình:

```bash
git remote -v
```

Ví dụ kết quả:

```text
origin  https://git.example.com/team/app.git (fetch)
origin  https://git.example.com/team/app.git (push)
```

Một remote có thể có địa chỉ fetch và push khác nhau. Vì vậy, hãy xem cả hai dòng khi kiểm tra cấu hình. Để xem thêm thông tin về remote và các nhánh theo dõi:

```bash
git remote show origin
```

Git lưu cấu hình remote trong `.git/config` của kho mã hiện tại. Remote không phải là một bản sao đang đồng bộ trực tiếp; các tham chiếu như `origin/main` là thông tin Git đã tải về lần gần nhất và được cập nhật khi bạn fetch.

## 2. Ba cách chỉ định địa chỉ kho mã

### 2.1. HTTPS

URL HTTPS thường có dạng:

```text
https://<host>/<nhom-hoac-nguoi-dung>/<ten-kho>.git
```

Ví dụ:

```bash
git clone https://git.example.com/platform/payment-service.git
```

Khi dùng HTTPS, Git kết nối qua HTTP được bảo vệ bằng TLS. Máy chủ xác thực người dùng thông qua cơ chế đăng nhập mà nhà cung cấp hỗ trợ, thường là token truy cập cá nhân hoặc thông tin xác thực được quản lý bởi Git Credential Manager. Nhiều dịch vụ không còn chấp nhận mật khẩu tài khoản thông thường cho thao tác Git qua HTTPS.

HTTPS phù hợp khi:

- Mạng của tổ chức cho phép HTTPS nhưng hạn chế kết nối SSH.
- Bạn mới làm quen với Git và muốn dùng cơ chế đăng nhập do dịch vụ cung cấp.
- Máy tính đã có Git Credential Manager để lưu và sử dụng thông tin xác thực an toàn.

Không đưa token hoặc mật khẩu trực tiếp vào URL, ví dụ `https://user:token@host/...`. URL có thể bị lưu trong cấu hình, lịch sử lệnh hoặc log. Hãy để trình quản lý thông tin xác thực xử lý việc đăng nhập.

### 2.2. SSH

URL SSH thường có một trong hai dạng:

```text
git@<host>:<duong-dan-kho>.git
ssh://<user>@<host>:<port>/<duong-dan-kho>.git
```

Ví dụ dạng SCP-like thường gặp:

```bash
git clone git@git.example.com:platform/payment-service.git
```

Ví dụ dạng URI có chỉ rõ cổng:

```bash
git clone ssh://git@git.example.com:22/platform/payment-service.git
```

Ở dạng thứ nhất, dấu hai chấm phân tách máy chủ và đường dẫn kho mã. Ở dạng `ssh://`, cổng được ghi sau tên máy chủ và trước đường dẫn.

SSH thường xác thực bằng cặp khóa bất đối xứng:

- **Khóa riêng (private key)** nằm trên máy của bạn và phải được bảo vệ.
- **Khóa công khai (public key)** được đăng ký với tài khoản hoặc máy chủ Git.
- `ssh-agent` có thể giữ khóa đã mở khóa trong phiên làm việc để bạn không phải nhập cụm mật khẩu nhiều lần.

Trên máy có OpenSSH, bạn có thể tạo khóa Ed25519 bằng lệnh:

```bash
ssh-keygen -t ed25519 -C "ten-may-hoac-email"
```

Sau đó thêm khóa công khai vào tài khoản hoặc máy chủ Git theo hướng dẫn của đơn vị cung cấp. Nếu dùng `ssh-agent`, nạp khóa riêng bằng:

```bash
ssh-add ~/.ssh/id_ed25519
```

Tên và vị trí tệp khóa có thể khác nếu bạn đã chọn đường dẫn khác khi tạo khóa. Trên Windows, các lệnh OpenSSH có thể chạy trong PowerShell hoặc Git Bash tùy cách cài đặt.

Kiểm tra kết nối SSH đến máy chủ:

```bash
ssh -T git@git.example.com
```

Thay `git.example.com` bằng máy chủ thực tế. Một số dịch vụ trả về thông báo chào mừng hoặc thông báo rằng xác thực thành công nhưng không cấp shell tương tác; điều đó vẫn có thể cho thấy khóa đã được nhận. Hãy làm theo cú pháp kiểm tra riêng của nhà cung cấp nếu họ yêu cầu.

Trong lần kết nối đầu tiên, SSH có thể hỏi bạn có tin cậy khóa máy chủ hay không. Hãy đối chiếu fingerprint với thông tin chính thức từ quản trị viên hoặc nhà cung cấp trước khi chấp nhận. Không bỏ qua cảnh báo thay đổi khóa máy chủ một cách máy móc.

SSH phù hợp khi bạn thường xuyên fetch và push, muốn xác thực bằng khóa, hoặc tổ chức đã chuẩn hóa việc cấp khóa SSH. Kết nối có thể cần cấu hình thêm nếu mạng chặn cổng SSH mặc định.

### 2.3. Đường dẫn kho mã cục bộ

Git cũng có thể truy cập một kho mã thông qua đường dẫn trên cùng máy hoặc một hệ thống tệp được gắn vào máy. Ví dụ:

```bash
git clone ../shared/payment-service.git
git clone /srv/git/payment-service.git
```

Đường dẫn có thể là:

- **Tương đối**, ví dụ `../shared/payment-service.git`, được diễn giải dựa trên thư mục làm việc khi chạy lệnh.
- **Tuyệt đối**, ví dụ `/srv/git/payment-service.git` hoặc `D:/git/payment-service.git`.
- **URI file**, ví dụ `file:///srv/git/payment-service.git`.

Đường dẫn cục bộ hữu ích khi học Git, sao lưu, trao đổi dữ liệu trong môi trường không có mạng hoặc làm việc với kho mã trên ổ đĩa dùng chung. Khi cần nhiều bản clone push vào cùng một kho mã, nên dùng **bare repository** làm kho nhận thay đổi. Bare repository chứa dữ liệu Git nhưng không có working tree để người dùng chỉnh sửa trực tiếp.

Tạo một bare repository:

```bash
git init --bare /srv/git/payment-service.git
```

Clone từ kho đó:

```bash
git clone /srv/git/payment-service.git payment-service
```

Bạn cũng có thể thêm đường dẫn này làm remote cho một kho mã đã tồn tại:

```bash
git remote add local-backup ../shared/payment-service.git
git remote -v
```

Không nên dùng một kho mã thông thường có working tree đang được checkout làm nơi nhận push từ nhiều người. Git thường từ chối cập nhật nhánh đang được checkout để tránh làm working tree ở máy nhận rơi vào trạng thái không nhất quán. Bare repository là lựa chọn phù hợp hơn cho mục đích nhận push.

## 3. So sánh và chọn giao thức

| Tiêu chí | HTTPS | SSH | Đường dẫn cục bộ |
|---|---|---|---|
| Địa chỉ thường gặp | `https://host/group/repo.git` | `git@host:group/repo.git` | `../repo.git`, `/srv/git/repo.git` |
| Xác thực | Token hoặc thông tin đăng nhập qua credential manager | Cặp khóa SSH | Quyền truy cập hệ thống tệp |
| Mạng | Thường dùng cổng HTTPS 443 | Thường dùng cổng SSH 22, có thể thay đổi | Không cần Internet; cần truy cập được đường dẫn |
| Phù hợp với | Mạng chỉ mở HTTPS, đăng nhập theo dịch vụ | Làm việc thường xuyên, tổ chức quản lý khóa | Học tập, sao lưu, máy chủ tệp hoặc môi trường nội bộ |
| Điểm cần chú ý | Bảo vệ token và credential | Bảo vệ khóa riêng, xác minh khóa máy chủ | Quyền đọc/ghi và cách tổ chức kho nhận push |

Không có giao thức nào thay đổi cách Git lưu commit. Hãy chọn theo chính sách xác thực, khả năng kết nối mạng và cách nhóm quản lý quyền truy cập. Một kho mã có thể được truy cập bằng HTTPS ở máy này và SSH ở máy khác; điều quan trọng là các địa chỉ đó thực sự trỏ đến cùng kho mã.

## 4. Kết nối remote với một kho mã hiện có

Nếu bạn clone từ một URL, Git thường tự tạo remote `origin`. Nếu đã có kho mã cục bộ và muốn kết nối nó với một kho trên máy chủ, hãy thêm remote:

```bash
git remote add origin https://git.example.com/platform/payment-service.git
git remote -v
```

Tải thông tin nhánh và commit từ remote:

```bash
git fetch origin
```

`fetch` cập nhật các remote-tracking branch như `origin/main`, nhưng không tự tích hợp thay đổi vào nhánh local hiện tại. Bạn có thể xem các nhánh và trạng thái theo dõi bằng:

```bash
git branch -vv
git branch -r
```

Khi muốn đẩy nhánh hiện tại lên remote và thiết lập nhánh theo dõi lần đầu, dùng:

```bash
git push -u origin main
```

Thay `main` bằng tên nhánh thực tế trong kho của bạn. Tùy chọn `-u` (hay `--set-upstream`) thiết lập upstream để những lần sau có thể dùng `git push` hoặc `git pull` ngắn gọn hơn.

Nếu remote đã tồn tại nhưng địa chỉ thay đổi, cập nhật URL thay vì thêm một remote trùng tên:

```bash
git remote set-url origin git@git.example.com:platform/payment-service.git
git remote -v
```

Bạn có thể lấy URL đang dùng cho một remote bằng:

```bash
git remote get-url origin
```

Nếu dự án làm việc với một kho mã fork và kho gốc, có thể khai báo hai remote:

```bash
git remote add origin git@git.example.com:my-account/payment-service.git
git remote add upstream https://git.example.com/platform/payment-service.git
git remote -v
```

Trong ví dụ này, `origin` trỏ đến bản fork và `upstream` trỏ đến kho mã gốc. Tên remote chỉ có ý nghĩa theo cấu hình của dự án; hãy thống nhất quy ước với nhóm.

## 5. Kiểm tra kết nối trước khi thao tác

Sau khi cấu hình remote, bạn có thể kiểm tra địa chỉ và quyền đọc bằng:

```bash
git remote -v
git ls-remote origin
```

`git ls-remote` yêu cầu Git truy cập máy chủ và liệt kê các tham chiếu mà tài khoản có quyền xem. Lệnh này giúp phát hiện URL sai, lỗi mạng hoặc lỗi xác thực khi đọc. Nó không chứng minh rằng bạn có quyền push.

Để xem Git có thể thực hiện push hay không mà không cập nhật nhánh trên remote, có thể chạy thử:

```bash
git push --dry-run origin HEAD
```

Dry run hữu ích để kiểm tra cấu hình và quyền push ở mức cơ bản, nhưng kết quả vẫn có thể khác lần push thật do hook, chính sách máy chủ hoặc trạng thái remote thay đổi.

Khi làm việc hằng ngày, các lệnh thường dùng là:

```bash
git fetch origin
git pull --ff-only origin main
git push origin main
```

`git pull` thực hiện fetch rồi tích hợp thay đổi vào nhánh hiện tại theo cấu hình pull của bạn. Ví dụ trên dùng `--ff-only` để chỉ cho phép cập nhật fast-forward; nếu lịch sử đã phân kỳ, Git dừng lại để bạn kiểm tra và chọn cách xử lý. Hãy thay `main` bằng nhánh cần làm việc.

## 6. Chuyển đổi giữa HTTPS và SSH

Bạn không cần clone lại kho mã chỉ để đổi giao thức. Hãy cập nhật URL của remote:

```bash
git remote set-url origin git@git.example.com:platform/payment-service.git
git remote -v
git ls-remote origin
```

Nếu muốn quay lại HTTPS:

```bash
git remote set-url origin https://git.example.com/platform/payment-service.git
```

Việc đổi URL không thay đổi commit, nhánh hoặc working tree đang có. Tuy nhiên, sau khi đổi, bạn cần bảo đảm máy đã cấu hình đúng thông tin xác thực cho giao thức mới. Nếu nhóm dùng URL fetch và push riêng, hãy kiểm tra cả hai dòng từ `git remote -v` trước khi kết luận đã đổi xong.

## 7. Lỗi thường gặp và cách xử lý

| Thông báo hoặc biểu hiện | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| `Repository not found` | Sai URL, kho riêng tư hoặc tài khoản chưa được cấp quyền | Kiểm tra lại host, nhóm, tên kho và quyền truy cập của tài khoản |
| `Authentication failed` khi dùng HTTPS | Token hết hạn, sai thông tin đăng nhập hoặc credential cũ được lưu | Đăng nhập lại qua credential manager; tạo/cấp lại token theo chính sách của nhà cung cấp |
| `Permission denied (publickey)` | SSH chưa tìm thấy khóa phù hợp hoặc khóa công khai chưa được đăng ký | Kiểm tra khóa, `ssh-agent`, `ssh-add -l` và tài khoản đã nhận khóa công khai |
| `Host key verification failed` | Khóa máy chủ chưa được tin cậy hoặc đã thay đổi | Đối chiếu fingerprint qua kênh chính thức rồi mới cập nhật `known_hosts` |
| Kết nối bị timeout hoặc bị từ chối | Sai host/cổng, firewall, VPN hoặc proxy | Kiểm tra mạng, cấu hình proxy và cổng mà máy chủ hỗ trợ |
| `non-fast-forward` khi push | Remote có commit mà nhánh local chưa tích hợp | Fetch, xem lịch sử hai nhánh rồi merge hoặc rebase theo quy ước nhóm |
| Push vào đường dẫn cục bộ bị từ chối | Đích là kho có working tree và nhánh đang checkout | Dùng bare repository làm nơi nhận push hoặc chọn cách chia sẻ phù hợp |

Một quy trình kiểm tra ngắn khi không kết nối được:

```bash
git remote -v
git remote get-url origin
git ls-remote origin
```

Sau đó xác định lỗi thuộc về địa chỉ, mạng hay xác thực. Tránh thay nhiều cấu hình cùng lúc vì sẽ khó biết thay đổi nào đã giải quyết vấn đề.

## 8. Bảo vệ thông tin xác thực và kho mã

- Không commit token, mật khẩu hoặc khóa riêng vào repository.
- Không ghi token vào URL remote hoặc chia sẻ URL chứa thông tin xác thực.
- Chỉ cấp quyền cần thiết cho tài khoản và khóa SSH; thu hồi khóa khi thiết bị không còn được sử dụng.
- Bảo vệ khóa riêng bằng quyền truy cập tệp phù hợp và cụm mật khẩu khi chính sách yêu cầu.
- Xác minh fingerprint khóa máy chủ khi thiết lập SSH lần đầu hoặc khi nhận cảnh báo khóa thay đổi.
- Với kho mã cục bộ trên ổ đĩa dùng chung, kiểm soát quyền đọc/ghi và dùng bare repository làm nơi nhận push.

## 9. Bài tập thực hành

Giả sử bạn có một kho mã local tên `payment-service` và nhóm cung cấp URL HTTPS cùng URL SSH cho cùng một repository.

1. Thêm remote tên `origin` bằng URL HTTPS và xác nhận bằng `git remote -v`.
2. Chạy `git ls-remote origin` để kiểm tra khả năng đọc repository.
3. Chuyển `origin` sang URL SSH bằng `git remote set-url`.
4. Kiểm tra khóa SSH và chạy lại `git ls-remote origin`.
5. Tạo một bare repository ở thư mục khác, thêm nó với tên `local-backup`, rồi kiểm tra cả hai remote.

Bạn đã hoàn thành bài tập khi giải thích được mỗi remote trỏ đến đâu, Git dùng cơ chế nào để xác thực và cách kiểm tra kết nối mà không làm thay đổi lịch sử trên remote.

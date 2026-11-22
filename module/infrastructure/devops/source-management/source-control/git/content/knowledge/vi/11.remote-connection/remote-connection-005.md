# Kiểm tra kết nối và quyền truy cập kho mã từ xa

Một repository Git có thể hoạt động bình thường trên máy nhưng vẫn không lấy được mã hoặc đẩy thay đổi lên máy chủ. Nguyên nhân có thể nằm ở URL remote, mạng, cơ chế xác thực, quyền của tài khoản hoặc chính sách bảo vệ nhánh. Biết cách kiểm tra từng lớp giúp bạn xác định đúng vấn đề trước khi thay đổi cấu hình hay yêu cầu quản trị viên cấp quyền.

## 1. Phân biệt remote, kết nối, xác thực và quyền truy cập

Trong Git, **remote** là tên đại diện cho một repository ở vị trí khác. Tên `origin` thường được tạo khi clone, nhưng đó chỉ là tên quy ước; nó không phải tên máy chủ và cũng không chứng minh kết nối đang hoạt động.

Cần phân biệt bốn khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ vấn đề |
|---|---|---|
| Cấu hình remote | Tên remote và URL Git dùng để liên hệ | URL sai, remote chưa được khai báo |
| Kết nối mạng | Máy có thể liên lạc với máy chủ qua DNS, mạng, proxy và cổng phù hợp | Không phân giải được tên máy, timeout, bị firewall chặn |
| Xác thực (*authentication*) | Máy chủ xác định bạn là tài khoản hoặc danh tính nào | Token hết hạn, SSH key chưa được đăng ký |
| Phân quyền (*authorization*) | Tài khoản được phép thực hiện thao tác nào trên repository hoặc nhánh | Đọc được nhưng không được push, nhánh bị bảo vệ |

Một lần `fetch` thành công cho thấy bạn đã truy cập được dữ liệu đọc cần thiết ở remote đó. Nó không chứng minh bạn có quyền ghi. Tương tự, đăng nhập thành công vào một nền tảng Git không có nghĩa tài khoản được phép truy cập mọi repository trên nền tảng.

## 2. Kiểm tra cấu hình remote tại máy local

Trước tiên, xem các remote đã khai báo:

```bash
git remote -v
```

Ví dụ kết quả:

```text
origin  https://git.example.com/team/service.git (fetch)
origin  https://git.example.com/team/service.git (push)
```

Mỗi remote có thể có URL dùng để fetch và URL dùng để push. Hai URL này có thể khác nhau, ví dụ tổ chức cho phép đọc qua một máy chủ mirror nhưng yêu cầu ghi vào máy chủ chính. Vì vậy, hãy xem cả hai dòng và đối chiếu với URL repository mà nhóm cung cấp.

Để xem URL đã được Git phân giải sau các quy tắc viết tắt `insteadOf`, có thể dùng:

```bash
git remote get-url --all origin
git remote get-url --push --all origin
```

Thay `origin` bằng tên remote thực tế. Nếu chưa có remote nào, `git remote -v` không in ra danh sách; điều đó chỉ nói rằng repository local chưa khai báo remote.

Một số thao tác sửa cấu hình thường dùng:

```bash
git remote add origin https://git.example.com/team/service.git
git remote set-url origin https://git.example.com/team/service.git
git remote set-url --push origin https://git-write.example.com/team/service.git
```

`remote add` thêm một remote mới; `set-url` đổi URL fetch mặc định; `set-url --push` đặt URL push riêng. Chỉ thực hiện khi đã xác nhận URL chính xác. Nếu remote đã tồn tại, không thêm một remote trùng tên.

Lưu ý bảo mật: URL remote đôi khi chứa thông tin nhạy cảm nếu ai đó nhúng token vào URL. Không đăng nguyên URL có token lên ticket, log, ảnh chụp màn hình hoặc tin nhắn. Nên dùng credential manager hoặc cơ chế xác thực do tổ chức hướng dẫn thay vì lưu token trực tiếp trong URL.

## 3. Kiểm tra remote có phản hồi hay không

`git remote -v` chỉ đọc cấu hình local, không gửi yêu cầu đến máy chủ. Để kiểm tra remote thực sự có thể được truy cập, dùng:

```bash
git remote show origin
```

Lệnh này liên hệ với remote để lấy thông tin như URL fetch/push, nhánh mặc định và quan hệ theo dõi nhánh. Nếu lệnh thất bại, đọc thông báo để xác định lỗi mạng, xác thực, quyền hoặc URL.

Một cách kiểm tra trực tiếp danh sách ref mà remote công bố là:

```bash
git ls-remote --symref origin HEAD
git ls-remote --heads origin
```

Lệnh thứ nhất hỏi thông tin `HEAD` và nhánh mà nó trỏ tới nếu máy chủ công bố symbolic ref. Lệnh thứ hai liệt kê các nhánh từ xa. `git ls-remote` không cập nhật các remote-tracking branch trong repository local; nó chỉ truy vấn ref hiện có ở máy chủ.

Nếu repository mới tạo và chưa có commit, lệnh có thể kết thúc thành công nhưng không in ra nhánh nào. Vì vậy, đầu ra rỗng không tự động có nghĩa là mất kết nối; cần xem mã thoát và trạng thái repository ở máy chủ.

Để kiểm tra khả năng fetch mà chưa cập nhật ref local, có thể chạy:

```bash
git fetch --dry-run origin
```

Tùy chọn `--dry-run` cho biết Git sẽ làm gì mà không thực hiện cập nhật fetch. Khi cần thực sự tải dữ liệu và cập nhật remote-tracking branch, dùng `git fetch origin`; thao tác này thay đổi dữ liệu Git local nhưng không sửa nhánh làm việc hiện tại.

## 4. Kiểm tra quyền đọc và quyền ghi

Quyền đọc và quyền ghi thường được cấp riêng. Hãy kiểm tra theo đúng thao tác mà bạn cần thực hiện.

### 4.1. Quyền đọc

Các thao tác như `git ls-remote` và `git fetch` cần quyền đọc repository. Nếu `git ls-remote origin` liệt kê được ref, đó là bằng chứng tốt rằng danh tính hiện tại có thể đọc repository qua URL đó.

Nếu nhóm yêu cầu lấy mã về máy, sau khi kiểm tra có thể thực hiện:

```bash
git fetch origin
```

`fetch` tải các đối tượng và cập nhật remote-tracking refs theo cấu hình. Nó không tự hợp nhất thay đổi vào nhánh hiện tại. `git pull` thường gồm fetch rồi tích hợp thay đổi vào nhánh đang làm việc, vì vậy không nên dùng `pull` chỉ như một phép thử kết nối khi chưa muốn tích hợp mã.

### 4.2. Quyền ghi

Quyền đọc thành công không đồng nghĩa quyền push. Nếu cần kiểm tra khả năng cập nhật một nhánh mà chưa gửi cập nhật ref, có thể thử chế độ mô phỏng:

```bash
git push --dry-run origin HEAD:refs/heads/<branch>
```

Thay `<branch>` bằng nhánh đích mà bạn được phép cập nhật. `--dry-run` yêu cầu Git mô phỏng thao tác push và không cập nhật ref trên remote. Kết quả giúp phát hiện một số vấn đề xác thực hoặc quyền ghi, nhưng không phải cam kết rằng lần push thật chắc chắn thành công: máy chủ có thể áp dụng branch protection, kiểm tra hook, quy tắc fast-forward hoặc chính sách khác khi nhận cập nhật thực tế. Lỗi non-fast-forward cũng không nhất thiết có nghĩa tài khoản thiếu quyền ghi.

Nếu cần xác nhận quyền ghi một cách dứt khoát, hãy kiểm tra chính sách của repository hoặc nhờ quản trị viên xác nhận quyền của tài khoản và nhánh đích. Không tự push một nhánh thử nghiệm hay xóa nhánh từ xa nếu chưa được nhóm cho phép.

## 5. Xác thực bằng HTTPS và SSH

Git thường dùng HTTPS hoặc SSH để kết nối máy chủ. Hãy dùng đúng phương thức mà nhóm hoặc nhà cung cấp Git hỗ trợ.

### 5.1. HTTPS

Với HTTPS, máy chủ thường xác thực bằng tài khoản kết hợp token truy cập hoặc cơ chế đăng nhập được tổ chức quản lý. Mật khẩu tài khoản có thể không được chấp nhận cho thao tác Git; điều này tùy nền tảng và chính sách tổ chức.

Khi gặp lỗi xác thực, kiểm tra các điểm sau:

- URL có đúng giao thức, hostname, nhóm và tên repository không.
- Credential manager có đang dùng thông tin của tài khoản cũ không.
- Token còn hạn, có đúng scope/quyền cần thiết và đã được cấp quyền SSO nếu tổ chức yêu cầu không.
- Tài khoản đã được mời vào nhóm hoặc repository chưa.

Không dán token vào câu lệnh, file cấu hình được commit hoặc nội dung báo lỗi công khai. Nếu nghi ngờ token đã lộ, hãy thu hồi và tạo thông tin xác thực mới theo quy trình của tổ chức.

### 5.2. SSH

Với SSH, máy local dùng khóa riêng để chứng minh danh tính; máy chủ Git thường lưu khóa công khai tương ứng trong tài khoản. Kiểm tra danh sách khóa đang được SSH agent quản lý:

```bash
ssh-add -l
```

Nếu không có khóa phù hợp, hãy kiểm tra SSH agent, cấu hình `~/.ssh/config`, tài khoản đăng ký public key và hostname/port mà nhà cung cấp yêu cầu. Không gửi private key cho người khác; chỉ public key mới được đăng ký trên dịch vụ Git.

Có thể kiểm tra bắt tay SSH với máy chủ theo hướng dẫn của nhà cung cấp, ví dụ:

```bash
ssh -T git@git.example.com
```

Thay hostname và tên người dùng SSH bằng giá trị dịch vụ cung cấp. Một số nền tảng dùng cổng hoặc tài khoản SSH riêng. Thông báo xác thực thành công ở bước này chỉ xác nhận máy chủ nhận diện được khóa/tài khoản; bạn vẫn cần kiểm tra quyền trên repository cụ thể bằng `git ls-remote` hoặc thao tác tương ứng.

Khi SSH báo máy chủ có host key chưa biết hoặc fingerprint thay đổi, hãy đối chiếu fingerprint với tài liệu chính thức của nhà cung cấp hoặc quản trị viên qua kênh đáng tin cậy. Không chấp nhận một fingerprint lạ chỉ để bỏ qua cảnh báo.

## 6. Đọc và khoanh vùng lỗi thường gặp

Thông báo lỗi thường cho biết vấn đề nằm ở lớp nào. Tuy nhiên, một số máy chủ cố ý trả về thông báo chung để không tiết lộ repository riêng tư có tồn tại hay không.

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `Could not resolve host` | DNS hoặc hostname sai | Kiểm tra chính tả hostname, DNS, VPN và cấu hình mạng |
| `Connection timed out` hoặc `Connection refused` | Firewall, proxy, VPN, cổng hoặc dịch vụ máy chủ | Kiểm tra mạng được phép, proxy, cổng và trạng thái dịch vụ |
| `SSL certificate problem` | Chứng chỉ hoặc chuỗi CA không được tin cậy, proxy kiểm tra TLS | Kiểm tra đồng hồ hệ thống, CA và hướng dẫn proxy của tổ chức |
| `Permission denied (publickey)` | Máy chủ không chấp nhận SSH key đang dùng | Kiểm tra agent, key được nạp, public key đăng ký và SSH config |
| `Authentication failed` hoặc HTTP `401` | Thông tin xác thực sai, hết hạn hoặc bị thu hồi | Kiểm tra credential manager và tạo lại token theo chính sách |
| HTTP `403` hoặc thông báo access denied | Tài khoản đã nhận diện nhưng thiếu quyền hoặc token thiếu scope | Kiểm tra quyền repository, scope token và yêu cầu SSO |
| `Repository not found` hoặc HTTP `404` | URL sai, repository không tồn tại hoặc máy chủ ẩn repository không được phép đọc | Đối chiếu URL và yêu cầu quyền truy cập với chủ sở hữu repository |
| Push bị từ chối do protected branch hoặc hook | Chính sách nhánh hoặc kiểm tra phía máy chủ không cho phép cập nhật | Đọc thông báo server, dùng pull request hoặc quy trình được nhóm quy định |
| `non-fast-forward` | Nhánh remote có commit mà nhánh local chưa tích hợp | Fetch, xem lịch sử và tích hợp theo quy trình nhóm trước khi push |

Không nên khắc phục lỗi chứng chỉ bằng cách tắt xác minh TLS (`http.sslVerify=false`) hoặc xử lý cảnh báo SSH bằng cách xóa host key một cách tùy tiện. Những cách này làm suy yếu khả năng xác minh máy chủ và có thể khiến thông tin xác thực bị gửi tới máy chủ giả mạo.

## 7. Phân biệt remote-tracking branch với quyền truy cập

Remote-tracking branch như `origin/main` là bản tham chiếu local ghi nhận trạng thái nhánh remote ở lần fetch gần nhất. Xem chúng bằng:

```bash
git branch -r
git branch -vv
```

Các lệnh trên không hỏi máy chủ tại thời điểm chạy. Vì vậy, việc nhìn thấy `origin/main` không chứng minh remote hiện còn truy cập được hoặc tài khoản hiện tại vẫn có quyền đọc. Muốn kiểm tra trạng thái mới nhất, cần truy vấn remote, chẳng hạn `git ls-remote origin` hoặc `git fetch origin`.

Nhánh local có thể được cấu hình theo dõi một nhánh remote. Cấu hình upstream giúp Git biết nguồn mặc định cho các thao tác như pull và push, nhưng bản thân nó không cấp quyền cho tài khoản. Quyền truy cập do máy chủ và chính sách của tổ chức quyết định.

## 8. Quy trình kiểm tra đề xuất

Khi clone, fetch hoặc push gặp lỗi, hãy thực hiện lần lượt:

1. **Xác nhận repository và remote.** Chạy `git status` và `git remote -v`; đối chiếu URL fetch/push với địa chỉ chính thức của nhóm.
2. **Kiểm tra khả năng liên lạc.** Chạy `git remote show origin` hoặc `git ls-remote origin` để biết máy chủ có phản hồi qua URL đó không.
3. **Xác định phương thức xác thực.** Kiểm tra credential manager với HTTPS hoặc SSH agent và cấu hình khóa với SSH. Đảm bảo đang dùng đúng tài khoản.
4. **Thử đúng quyền cần thiết.** Dùng `git ls-remote`/`git fetch` cho quyền đọc. Với quyền ghi, xem chính sách nhánh và có thể dùng `git push --dry-run` như phép kiểm tra sơ bộ.
5. **Phân loại thông báo lỗi.** Tách lỗi mạng, chứng chỉ, xác thực, phân quyền, branch protection và non-fast-forward trước khi thay đổi cấu hình.
6. **Ghi lại thông tin đủ để hỗ trợ.** Cung cấp lệnh đã chạy, loại giao thức, hostname, tên repository, thời điểm và thông báo lỗi đã che thông tin nhạy cảm. Không gửi token, mật khẩu, private key hoặc URL chứa credential.

Ví dụ một lượt kiểm tra chỉ đọc:

```bash
git status
git remote -v
git remote show origin
git ls-remote --symref origin HEAD
```

Nếu các lệnh đọc thành công nhưng push bị từ chối, hãy chuyển hướng kiểm tra sang quyền ghi, nhánh đích và chính sách bảo vệ nhánh. Không cần thay khóa SSH hoặc token khi bằng chứng cho thấy xác thực đọc đang hoạt động và lỗi chỉ xuất hiện ở thao tác ghi.

## 9. Ghi nhớ

Remote là cấu hình trỏ tới repository khác; kết nối mạng, xác thực danh tính và phân quyền thao tác là các bước riêng biệt. Hãy kiểm tra URL trước, truy vấn remote để xác nhận quyền đọc, rồi kiểm tra chính sách ghi theo nhánh và thao tác cụ thể. Bảo vệ token, private key và thông tin xác minh máy chủ trong suốt quá trình xử lý.

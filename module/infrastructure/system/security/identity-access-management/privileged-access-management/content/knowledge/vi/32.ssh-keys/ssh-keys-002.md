# Private key protection — Bảo vệ private key SSH

## Bối cảnh và mục tiêu

Trong chương **SSH và key** của module quản lý truy cập đặc quyền (PAM), private key là tài sản có thể mở đường vào tài khoản quản trị, tài khoản dịch vụ và máy chủ nhạy cảm. Một khóa được dùng cho nhiều máy còn tạo ra quan hệ tin cậy vượt xa chiếc laptop đang lưu nó.

Bảo vệ private key vì thế bao gồm cả nơi lưu khóa, cách cho phép ký xác thực, phạm vi quyền mà khóa mở được và khả năng thu hồi trên toàn bộ đích. Cài đặt quyền truy cập tệp là một phần của thiết kế đó.

Sau bài học, người học có thể:

- Phân biệt bí mật của khóa, passphrase và quyền truy cập được cấp phía máy chủ.
- Chọn biện pháp bảo vệ cho khóa cá nhân, khóa của workload và khóa dùng trong hệ thống PAM.
- Sử dụng tệp khóa cùng SSH agent với phạm vi và thời gian phù hợp.
- Lập quy trình kiểm kê, luân chuyển, khôi phục và xử lý nghi ngờ lộ khóa.
- Lưu bằng chứng vận hành mà không đưa private key hoặc passphrase vào hồ sơ kiểm toán.

Các lệnh trong bài là ví dụ thực hành cho môi trường lab. Tên máy thuộc miền `example.net` là minh họa; cần thay bằng tài nguyên được cấp quyền. Các lệnh Bash và PowerShell được tách riêng, không chạy lẫn giữa hai môi trường.

## 1. Hiểu đúng tài sản cần bảo vệ

### 1.1. Private key, public key và quyền truy cập

Một cặp khóa SSH gồm hai phần liên quan về mặt mật mã:

| Thành phần | Vai trò | Cách quản lý |
|---|---|---|
| Private key của người dùng | Tạo chữ ký để chứng minh quyền sử dụng khóa | Giữ bí mật; giới hạn nơi lưu và nơi có thể yêu cầu ký |
| Public key tương ứng | Cho phép bên kiểm tra xác thực chữ ký | Phân phối có kiểm soát đến hệ thống cấp quyền |
| Fingerprint | Định danh khóa phục vụ đối chiếu, kiểm kê và truy vết | Có thể lưu trong registry; vẫn xem metadata về hạ tầng là thông tin nội bộ |
| Passphrase | Bảo vệ bản private key được mã hóa trên thiết bị | Giữ riêng khỏi tệp khóa và khỏi tài liệu vận hành |
| Quy tắc cấp quyền | Ánh xạ khóa hoặc certificate đến tài khoản và phạm vi truy cập | Do máy chủ, hệ thống danh tính và PAM quản lý |

Public key không phải bí mật tương đương private key, nhưng **quyền thay đổi danh sách public key được tin cậy** là quyền nhạy cảm. Người có thể tự thêm public key vào tài khoản quản trị có thể tạo thêm đường đăng nhập cho mình.

Cũng cần tách ba câu hỏi:

1. Ai có thể sử dụng private key để ký?
2. Máy chủ nào chấp nhận chữ ký đó cho tài khoản nào?
3. Sau khi đăng nhập, tài khoản được làm gì?

Ví dụ, khóa của `linh-admin` có thể đăng nhập thành công nhưng tài khoản chỉ được đọc log. Nếu tài khoản được cấp `sudo` rộng, cùng khóa đó có thể trở thành đường đến quyền quản trị toàn máy. Bảo vệ khóa phải đi cùng least privilege và kiểm soát nâng quyền.

### 1.2. Khóa xác thực không phải toàn bộ bảo mật phiên SSH

Không nên diễn giải SSH là gửi private key cho máy chủ để giải mã dữ liệu. Trong xác thực public key, phía sử dụng khóa chứng minh quyền sở hữu thông qua chữ ký. Việc xác thực máy chủ, thương lượng khóa phiên và bảo vệ kênh truyền là các phần khác của giao thức.

Có private key được bảo vệ tốt vẫn chưa giải quyết được việc kết nối nhầm máy chủ, cấp quyền quá rộng hoặc sử dụng một endpoint đã bị chiếm. Trong PAM, cần xem toàn bộ chuỗi từ thiết bị quản trị đến tài khoản đích.

Phân biệt thêm các loại khóa:

- **User key:** xác thực người hoặc workload đăng nhập.
- **Host key:** định danh máy chủ SSH.
- **CA key:** ký SSH certificate để các máy chủ tin cậy certificate đó.

Bài này tập trung vào private key dùng cho truy cập. Không dùng private host key làm khóa cá nhân; không dùng private CA key như một khóa đăng nhập hàng ngày.

### 1.3. Passphrase bảo vệ bản lưu, không tự thu hồi quyền

Passphrase giúp bảo vệ một bản private key khi tệp bị sao chép. Sau khi khóa được mở hoặc khả năng ký đã được cấp cho một tiến trình, cần những biện pháp khác để kiểm soát việc sử dụng.

Việc đổi passphrase không thay thế cặp khóa và không làm bản sao cũ biến mất. Một bản sao đã bị lấy trước đó vẫn chịu cơ chế bảo vệ của bản sao ấy. Khi nghi khóa bị lộ, phải xử lý cả khóa và các nơi đang tin cậy nó.

Không mặc định coi “private key có passphrase” là MFA được máy chủ hoặc PAM bắt buộc thực thi. Máy chủ thông thường không biết người dùng vừa nhập passphrase, đang dùng agent đã mở khóa hay đang sử dụng một cơ chế lưu khóa khác. Nếu tổ chức yêu cầu xác thực bổ sung tại thời điểm phê duyệt hoặc truy cập, phải thiết kế và kiểm chứng yêu cầu đó riêng.

## 2. Mô hình đe dọa: khóa có thể bị lấy hoặc bị dùng như thế nào?

Xét tình huống một quản trị viên lưu khóa production trên laptop. Khóa được thêm vào agent cả ngày và trước đây từng được chép sang jump host để thuận tiện xử lý sự cố.

| Tình huống | Rủi ro chính | Biện pháp phù hợp | Giới hạn cần nhớ |
|---|---|---|---|
| Laptop bị mất khi tắt máy | Bản lưu khóa bị sao chép | Mã hóa ổ đĩa, passphrase mạnh, quản lý thiết bị | Không bảo vệ đầy đủ khi máy đã mở khóa và bị điều khiển |
| Người dùng khác đọc được thư mục | Lộ tệp khóa hoặc thay đổi cấu hình | Quyền tệp, ACL, tài khoản cá nhân riêng | Quyền quản trị hệ điều hành vẫn là ranh giới quan trọng |
| Malware chạy cùng tài khoản | Đọc dữ liệu, chờ mở khóa hoặc gọi agent | Bảo vệ endpoint, giảm phần mềm không tin cậy, hạn chế thời gian sử dụng khóa | Quyền tệp đơn thuần không phân biệt được hai tiến trình cùng người dùng |
| Agent được chuyển tiếp đến máy không đáng tin | Kẻ kiểm soát máy từ xa có thể lợi dụng khả năng ký | Hạn chế forwarding, dùng đường truy cập phù hợp | Không cần lấy được tệp khóa để gây hại |
| Khóa nằm trong repository hoặc artifact | Bản sao lan ra nhiều nơi | Ngăn đưa secret vào mã nguồn, kiểm tra pipeline, thu hồi khi lộ | Xóa bản hiện tại không xóa hết lịch sử hay bản sao |
| CI runner dùng chung cho nhiều dự án | Job khác sử dụng credential được nạp | Cô lập runner, scope theo workload và môi trường | Che secret trong log không ngăn job được phép đọc secret |
| Nhiều người dùng cùng một khóa | Khó quy trách nhiệm và thu hồi từng cá nhân | Khóa riêng, danh tính riêng, audit của PAM | Comment trong public key không chứng minh ai đã dùng khóa |

Điểm cần quan sát là **khả năng sử dụng khóa**. Một thiết kế chỉ kiểm tra “tệp chưa bị tải ra ngoài” sẽ bỏ qua việc kẻ tấn công sử dụng agent đang mở hoặc điều khiển trực tiếp phiên của người quản trị.

## 3. Kiểm kê trước khi lựa chọn biện pháp bảo vệ

Không thể thu hồi đáng tin cậy một khóa mà không biết nó đang được tin cậy ở đâu. Mỗi khóa đặc quyền cần có owner chịu trách nhiệm, mục đích cụ thể và bản đồ quyền truy cập.

Một bản ghi quản lý có thể có cấu trúc minh họa như sau. Đây là metadata, không phải nơi chứa secret:

```yaml
key_id: ssh-human-prod-017
owner: linh-admin
identity_type: human
environment: production
purpose: maintenance-through-pam
public_key_fingerprint: "<fingerprint SHA256 đã xác minh>"
custody: managed-workstation
approved_targets:
  - account: linh-admin
    host_group: payments-linux
approval_reference: CHG-LAB-017
review_due: "<ngày theo chính sách nội bộ>"
revocation_owner: identity-operations
```

Các trường cần được duy trì khi phạm vi quyền thay đổi. Chẳng hạn, owner đổi nhóm không có nghĩa public key tự biến mất khỏi những máy từng được cấp quyền.

Không đưa private key, passphrase, mã khôi phục hoặc nội dung session vào trường ghi chú. Registry nên trỏ đến định danh đối tượng trong vault nếu cần, thay vì sao chép secret ra registry.

Tách khóa theo người, mục đích và môi trường khi điều đó giúp thu hẹp phạm vi ảnh hưởng. Một khóa phát triển được dùng thêm cho production sẽ nối hai vùng rủi ro vốn cần được kiểm soát khác nhau.

## 4. Bảo vệ private key khi lưu trên thiết bị

### 4.1. Quyền tệp trên Linux và các hệ thống tương tự Unix

Với khóa phần mềm của một người dùng, thư mục riêng và quyền tệp chặt là baseline thường dùng. Ví dụ dưới đây giả định khóa lab đã có và các đường dẫn thuộc chính người đang thao tác:

```bash
ls -ld "$HOME/.ssh"
ls -l "$HOME/.ssh/id_ed25519_pam_lab"

chmod 700 "$HOME/.ssh"
chmod 600 "$HOME/.ssh/id_ed25519_pam_lab"

ls -ld "$HOME/.ssh"
ls -l "$HOME/.ssh/id_ed25519_pam_lab"
```

Quyền `700` trên thư mục dành quyền truy cập cho owner; `600` trên private key dành quyền đọc và ghi cho owner. Cần kiểm tra owner thực tế, ACL mở rộng nếu có và đường dẫn đang trỏ đến đối tượng nào. Không sửa đệ quy toàn bộ home directory để chữa một lỗi quyền của khóa.

Nếu khóa nằm trên filesystem dùng chung hoặc thư mục đồng bộ, phải hiểu thêm quyền từ phía dịch vụ lưu trữ, bản snapshot và quyền quản trị. Màn hình `ls` của một tệp không mô tả toàn bộ các bản sao.

Đừng dùng `chmod 777` để “sửa SSH không đọc được khóa”. Khi bị từ chối, hãy xác minh user thực thi, owner, quyền của thư mục cha và loại tệp, rồi sửa đúng đối tượng.

### 4.2. ACL trên Windows

Trên Windows, kiểm soát truy cập dựa vào ACL; không chuyển nguyên xi cách suy luận về bit quyền Unix. Ví dụ kiểm tra chỉ đọc:

```powershell
$pamLabKeyPath = Join-Path $env:USERPROFILE '.ssh\id_ed25519_pam_lab'

Get-Item -LiteralPath $pamLabKeyPath |
    Select-Object FullName, Length, Attributes

Get-Acl -LiteralPath $pamLabKeyPath |
    Format-List Owner, AccessToString
```

Kiểm tra owner, quyền được cấp trực tiếp và quyền kế thừa. Quyền cần phù hợp với danh tính sử dụng khóa và chính sách quản trị thiết bị; các nhóm người dùng rộng không nên được đọc private key. Phân biệt ACL của user key với ACL của host key do dịch vụ SSH quản lý. Cách quản lý khóa trên Windows được mô tả trong [tài liệu OpenSSH của Microsoft](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement).

Không áp dụng một lệnh thay ACL hàng loạt cho cả thư mục chỉ vì một client báo lỗi. Nếu khóa do tài khoản dịch vụ dùng, cần xét đúng danh tính chạy service thay vì cấp quyền đọc cho mọi user.

### 4.3. Mã hóa ổ đĩa và quản lý endpoint

Mã hóa ổ đĩa giúp giảm rủi ro đọc dữ liệu từ thiết bị bị mất, nhưng không thay thế passphrase hoặc kiểm soát tiến trình khi hệ điều hành đang chạy.

Thiết bị quản trị đặc quyền nên có kiểm soát cập nhật, khóa màn hình, phần mềm được phép chạy và quy trình xử lý khi bị mất. Cũng cần xác định thư mục SSH có bị sao lưu hoặc đồng bộ tự động đến tài khoản cá nhân hay không.

Một khóa có passphrase tốt nhưng nằm trong một bản sao lưu công khai vẫn là sự cố cần xử lý. Chi phí dò passphrase chỉ là một lớp cản trở, không phải lý do giữ nguyên credential đã bị phát tán.

## 5. Sinh và bảo vệ khóa phần mềm

### 5.1. Tạo khóa riêng cho mục đích đã xác định

Ví dụ Bash sau dùng một tên khóa lab riêng. Trước khi chạy, kiểm tra cả tên private key lẫn tệp `.pub` tương ứng; nếu tên đã tồn tại, chọn tên mới và không chấp nhận ghi đè:

```bash
umask 077
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

ls -l "$HOME/.ssh/id_ed25519_pam_lab" \
      "$HOME/.ssh/id_ed25519_pam_lab.pub"

# Chỉ tiếp tục nếu cả hai đường dẫn chưa tồn tại.
ssh-keygen -t ed25519 -a 64 \
  -C "pam-lab-individual-access" \
  -f "$HOME/.ssh/id_ed25519_pam_lab"

chmod 600 "$HOME/.ssh/id_ed25519_pam_lab"

ssh-keygen -lf "$HOME/.ssh/id_ed25519_pam_lab.pub"
```

Lệnh `ls` có thể báo không tìm thấy tệp khi tên chưa được sử dụng; đó là bước quan sát, không phải cơ chế tự động chống ghi đè. Vẫn phải kiểm tra trước khi tạo.

Nhập passphrase tương tác khi được hỏi. `-a` điều chỉnh số vòng KDF; giá trị `64` là ví dụ lab cần đo độ trễ trên thiết bị, không phải chuẩn bắt buộc. Thuật toán và định dạng phải phù hợp chính sách mật mã của môi trường. Xem mô tả chính thức của `-a`, `-f` và `-p` trong [ssh-keygen(1)](https://man.openbsd.org/ssh-keygen).

Không đưa passphrase thật vào command line, script, ticket hoặc biến cấu hình chia sẻ. Chọn secret đủ khó đoán và có phương án quản lý phù hợp; tránh tái sử dụng mật khẩu đăng nhập doanh nghiệp cho khóa.

Public key được phân phối qua quy trình cấp quyền. Private key của người quản trị không cần được chép lên máy đích để SSH public key authentication hoạt động.

### 5.2. Thay passphrase và phân biệt với rotation

Đối với khóa lab do mình sở hữu, có thể thay passphrase bằng chế độ tương tác:

```bash
ssh-keygen -p -f "$HOME/.ssh/id_ed25519_pam_lab"
ssh-keygen -lf "$HOME/.ssh/id_ed25519_pam_lab.pub"
```

Giữ bản ghi fingerprint trước và sau để minh họa sự khác biệt giữa **thay cách bảo vệ bản lưu** và **thay cặp khóa**. Đổi passphrase đúng cách không làm public key trở thành một khóa mới.

Nếu khóa đang nằm trong agent, đừng giả định việc sửa tệp trên đĩa tự cập nhật hoặc vô hiệu hóa identity đã nạp. Quản lý riêng trạng thái của agent và các bản sao được tổ chức cho phép.

Khi quên passphrase, quy trình vận hành cần dùng phương án khôi phục đã phê duyệt hoặc cấp khóa mới. Không nên tạo sẵn một bản private key không được bảo vệ chỉ để dự phòng việc quên secret.

## 6. Bảo vệ lúc sử dụng: SSH agent và đường truy cập

### 6.1. Agent là một quyền ký đang hoạt động

`ssh-agent` cung cấp khả năng xác thực bằng khóa đã được nạp. Với khóa phần mềm, việc dùng agent giúp giảm số lần mở tệp bằng passphrase, nhưng kéo theo quyền truy cập vào agent.

Trên hệ Unix, tiến trình cùng người dùng hoặc có quyền quản trị có thể là nguồn rủi ro đối với socket agent. Việc forwarding còn đưa khả năng yêu cầu ký sang một máy khác. Xem mô hình agent và lưu ý về socket trong [ssh-agent(1)](https://man.openbsd.org/ssh-agent).

Do đó, cần quản lý ba trạng thái riêng:

| Trạng thái | Câu hỏi kiểm soát |
|---|---|
| Tệp private key trên đĩa | Ai đọc được? Có được mã hóa bằng passphrase? Có bản sao nào? |
| Identity đã nạp vào agent | Ai có thể gọi agent? Được giữ trong bao lâu? |
| Phiên SSH đã xác thực | Ai điều khiển phiên? Quyền nào còn hiệu lực? Khi nào kết thúc? |

Gỡ identity khỏi agent không xóa tệp khóa; kết thúc thời gian giữ khóa trong agent không tự kết thúc phiên SSH đã mở.

### 6.2. Nạp đúng khóa với thời gian giới hạn

Ví dụ dưới đây dành cho một shell lab riêng. Chỉ khởi tạo agent mới nếu lab chưa có agent phù hợp; tránh vô tình thay môi trường agent mà phiên desktop đang dùng.

```bash
# Chỉ dùng dòng này khi cần tạo agent riêng cho shell lab.
eval "$(ssh-agent -s)"

# Nạp đúng khóa trong tối đa 900 giây.
ssh-add -t 900 "$HOME/.ssh/id_ed25519_pam_lab"

# Kiểm tra fingerprint các identity đang có trong agent.
ssh-add -l

# Khi xong lab, gỡ đúng identity này.
ssh-add -d "$HOME/.ssh/id_ed25519_pam_lab.pub"

ssh-add -l
```

`ssh-add -t` đặt thời gian giữ identity; `-l` liệt kê fingerprint; `-d` gỡ identity được chỉ định. `-c` có thể yêu cầu xác nhận khi sử dụng nếu môi trường hỗ trợ cơ chế xác nhận cần thiết. Cần kiểm chứng giao diện xác nhận trước khi đưa vào quy trình. Tham khảo [ssh-add(1)](https://man.openbsd.org/ssh-add.1).

Thời gian `900` giây chỉ giới hạn identity trong agent đó. Khóa vẫn có thể được nạp lại nếu người dùng còn khóa và passphrase. Đây không phải cơ chế JIT phía máy chủ, cũng không phải thời hạn tuyệt đối của credential.

### 6.3. Giảm nhu cầu chuyển tiếp agent

Một thiết kế truy cập lab qua jump host có thể dùng cấu hình sau. Hai tệp khóa khác nhau phải được tạo và đăng ký riêng; ví dụ không ngầm tạo chúng:

```sshconfig
Host pam-jump-lab
    HostName jump.lab.example.net
    User linh-admin
    IdentityFile ~/.ssh/id_ed25519_pam_jump_lab
    IdentitiesOnly yes
    ForwardAgent no
    AddKeysToAgent no
    StrictHostKeyChecking yes

Host pam-target-lab
    HostName target.lab.example.net
    User linh-admin
    IdentityFile ~/.ssh/id_ed25519_pam_lab
    IdentitiesOnly yes
    ProxyJump pam-jump-lab
    ForwardAgent no
    AddKeysToAgent no
    StrictHostKeyChecking yes
```

`ProxyJump` tạo đường truyền qua jump host; khóa dùng xác thực máy đích có thể tiếp tục nằm ở client. `IdentitiesOnly` giới hạn các identity được đề xuất theo cấu hình. Nó không thay thế sự bảo vệ agent hoặc quyền phía máy chủ. Các directive được mô tả trong [ssh_config(5)](https://man.openbsd.org/ssh_config.5).

Với `StrictHostKeyChecking yes`, thông tin tin cậy của máy chủ phải được chuẩn bị qua quy trình xác minh phù hợp. Không xử lý lỗi host key bằng cách bỏ kiểm tra trên mọi máy.

Có thể quan sát cấu hình hiệu lực trước khi kết nối:

```bash
ssh -G pam-target-lab
```

Cần đọc cả cấu hình đích và jump host. Một mục `Host` khác, các tệp include hoặc nhiều `IdentityFile` có thể ảnh hưởng kết quả. Bản in cấu hình giúp hiểu client sẽ làm gì; nó chưa chứng minh máy chủ đã thực thi chính sách PAM.

ProxyJump cũng không tự cung cấp ghi hình phiên hoặc phê duyệt truy cập. Nếu cần audit nội dung phiên, phải chọn kiến trúc broker hoặc cơ chế ghi nhận được thiết kế cho yêu cầu đó.

## 7. Chọn nơi giữ khóa: thiết bị, phần cứng hay PAM?

Không có một kiểu lưu trữ phù hợp cho mọi danh tính. Cần chọn dựa trên ai sử dụng khóa, mức đặc quyền và khả năng thu hồi.

| Mô hình | Điểm mạnh | Điều kiện vận hành |
|---|---|---|
| Tệp mã hóa trên thiết bị quản trị | Đơn giản, dễ tích hợp client | Endpoint được quản lý, passphrase, ít bản sao, vòng đời rõ ràng |
| Khóa gắn với thiết bị phần cứng | Giảm khả năng lấy nguyên vật liệu khóa ra tệp thông thường | Tương thích client, đăng ký thiết bị, xử lý mất thiết bị và thay thế |
| Vault cấp phát khóa cho tiến trình | Tập trung quyền đọc và audit cấp phát | Hạn chế export, kiểm soát endpoint nhận khóa, thu hồi tại đích |
| Broker PAM thực hiện kết nối | Có thể giữ credential ngoài máy người dùng | Kiểm soát đường truy cập, ánh xạ người dùng, độ sẵn sàng và log |
| Khóa kết hợp SSH certificate ngắn hạn | Giới hạn thời gian và danh tính được cấp phép | Bảo vệ CA, kiểm soát cấp certificate và cách các máy chủ xác thực |

### 7.1. Khóa phần cứng giảm một nhóm rủi ro cụ thể

Một ví dụ là khóa SSH dựa trên FIDO. Các loại `ecdsa-sk` và `ed25519-sk` phụ thuộc phần cứng và hỗ trợ của bộ OpenSSH. Tệp trên đĩa có thể chứa key handle, nên sao chép tệp không tương đương sao chép toàn bộ khóa phần cứng. Cơ chế này được giải thích trong [ghi chú hỗ trợ FIDO của OpenSSH](https://www.openssh.org/txt/release-8.2).

Điều cần kiểm chứng trong triển khai thực tế là yêu cầu hiện diện người dùng, PIN hoặc xác minh người dùng, chính sách của thiết bị và hành vi khi thiết bị bị mất. Đừng suy ra rằng mọi thiết bị đều hỗ trợ mọi thuật toán hoặc mọi chế độ.

Phần cứng không tự sửa được quyền quá rộng. Nếu người dùng xác nhận một yêu cầu ký sai trong lúc endpoint bị điều khiển, hậu quả còn phụ thuộc máy chủ đích và quyền của tài khoản. Cần đánh giá cả giao diện yêu cầu xác nhận và bối cảnh công việc.

Không thiết kế khôi phục bằng giả định có thể xuất một private key không xuất được. Có thể đăng ký thiết bị dự phòng theo quy trình riêng, hoặc cấp credential thay thế sau khi xác minh danh tính.

### 7.2. Vault không tự ngăn việc sao chép sau khi export

Nếu vault trả private key về laptop dưới dạng tệp, laptop trở thành một điểm giữ secret. Audit “ai đã lấy khóa” hữu ích, nhưng chưa cho biết các bản sao sau đó nằm ở đâu.

Trong thiết kế PAM, nên mô tả rõ:

- Người dùng nhận raw private key hay chỉ nhận một phiên kết nối?
- Tiến trình nào có quyền yêu cầu sử dụng hoặc xuất khóa?
- Credential được dùng cho tài khoản nào, trên nhóm máy nào?
- Hết thời gian phê duyệt thì điều gì thực sự bị vô hiệu hóa?
- Nếu broker hoặc vault mất khả dụng, đường khôi phục có được kiểm soát tương đương không?

Nếu một raw key đã được export và vẫn được máy chủ tin cậy, hết hạn checkout trong vault không đủ để làm khóa đó mất hiệu lực ở máy chủ. Tương tự, hết phiên đăng nhập PAM không chứng minh một đường SSH trực tiếp bên ngoài PAM đã bị chặn.

### 7.3. Certificate ngắn hạn vẫn cần bảo vệ private key

SSH certificate gắn public key với thông tin được CA xác nhận. Certificate có thời hạn không có nghĩa private key dùng kèm tự biến mất khi hết thời hạn.

Thiết kế cần loại bỏ đường cấp quyền song song ngoài ý muốn. Ví dụ, cùng public key vừa được cấp certificate ngắn hạn vừa được cài như raw key lâu dài sẽ tạo hai đường xác thực khác nhau. Đường raw key có thể làm mục tiêu giới hạn thời gian bị vô hiệu về mặt vận hành.

Khóa CA cần được quản lý với mức độ nghiêm ngặt tương xứng khả năng ký. Không phân phối private CA key cho quản trị viên để họ tự ký certificate khi cần truy cập.

## 8. Khóa cho service account và pipeline

Khóa của một workload phải thuộc workload đó, có owner vận hành và được giới hạn theo công việc. Không sao chép khóa cá nhân của kỹ sư vào service hoặc pipeline.

Vấn đề thường gặp là tác vụ tự động không có người nhập passphrase. Có ba hướng thiết kế cần đánh giá:

1. Dùng danh tính workload được xác thực để nhận credential ngắn hạn hoặc yêu cầu kết nối qua broker.
2. Giữ khóa trong cơ chế ký được quản lý nếu ứng dụng và nền tảng hỗ trợ.
3. Nếu phải dùng tệp khóa tĩnh, giới hạn mạnh nơi nhận khóa, quyền tại đích và khả năng luân chuyển.

Việc lưu passphrase ngay cạnh khóa trong cùng cấu hình đọc được bởi cùng job thường không tạo được một ranh giới bảo vệ độc lập. Nó vẫn có thể đáp ứng yêu cầu định dạng của phần mềm, nhưng phải giải thích đúng giới hạn.

Một quy trình cấp phát cho pipeline có thể được mô tả như sau:

```text
Xác thực workload và ràng buộc dự án/môi trường
    -> Đánh giá chính sách cấp secret hoặc certificate
    -> Cấp cho runner được cô lập trong thời gian cần thiết
    -> Thực hiện đúng tác vụ đã được cho phép tại đích
    -> Kết thúc job và xử lý credential tạm
    -> Đối chiếu log cấp phát với log sử dụng
```

Đây là thiết kế mục tiêu, không phải tính năng tự có của mọi secret store. Đặc biệt cần kiểm tra job từ nhánh, pull request hoặc dự án không đáng tin có thể tiếp cận credential production hay không.

Đối với khóa chỉ phục vụ một tác vụ, có thể bổ sung ràng buộc phía máy chủ. Ví dụ minh họa trong `authorized_keys`:

```text
restrict,from="192.0.2.0/24",command="/usr/local/libexec/approved-backup" ssh-ed25519 <PUBLIC_KEY_BASE64> backup-lab
```

`<PUBLIC_KEY_BASE64>` là chỗ giữ chỗ và phải được thay bằng public key hợp lệ. Mạng `192.0.2.0/24` là địa chỉ minh họa.

`restrict` hạn chế forwarding và một số chức năng phiên; nó không tự cấm mọi lệnh. `command=` buộc chạy chương trình đã chọn, còn `from=` giới hạn nguồn theo điều kiện được cấu hình. Chi tiết tùy chọn nằm trong [định dạng authorized_keys của sshd(8)](https://man.openbsd.org/sshd).

Chương trình `approved-backup` vẫn phải được kiểm soát owner, quyền sửa và cách xử lý đầu vào. Một wrapper cho phép thực thi tùy ý thông qua tham số sẽ làm hỏng mục tiêu giới hạn tác vụ. Các hạn chế này bổ sung cho việc bảo vệ private key, không thay thế việc đó.

## 9. Bản sao lưu, khôi phục và khóa dự phòng

Có bản sao lưu là có thêm một nơi giữ secret. Trước khi sao lưu private key, cần trả lời khóa ấy có cần được khôi phục nguyên trạng hay có thể cấp lại bằng quy trình danh tính.

Với khóa cá nhân, cấp khóa mới có thể phù hợp hơn việc tổ chức giữ bản sao mọi private key. Với credential dịch vụ cần phục hồi khẩn cấp, có thể cần lưu giữ có kiểm soát. Quyết định phải xuất phát từ yêu cầu vận hành cụ thể.

Nếu được phép sao lưu, thiết kế tối thiểu nên xác định:

- Bản sao được mã hóa và ai có thể giải mã.
- Ai được yêu cầu khôi phục, ai phê duyệt và ai thực hiện.
- Thời gian lưu, vị trí các bản sao và trách nhiệm quản lý.
- Cách thử khôi phục trong môi trường cô lập.
- Cách xử lý bản sao khi khóa bị thu hồi hoặc bị nghi lộ.

Không gửi private key vào email nhóm, ticket hoặc kho lưu trữ chung để làm “dự phòng”. Không dùng một khóa dự phòng chung cho mọi quản trị viên mà không có cơ chế quy trách nhiệm.

Bằng chứng thử khôi phục có thể gồm định danh bản sao, fingerprint public key đã đối chiếu, thời điểm thử, người được phép thực hiện và kết quả. Không cần lưu private key trong biên bản để chứng minh phép thử thành công.

## 10. Rotation và thu hồi: thay đổi niềm tin tại đúng nơi

### 10.1. Phân biệt các thao tác thường bị gọi chung là đổi khóa

| Thao tác | Điều thay đổi | Điều chưa được giải quyết |
|---|---|---|
| Đổi passphrase | Cách mã hóa bản private key đang sửa | Bản sao cũ, public key được tin cậy và phiên đã mở |
| Gỡ identity khỏi agent | Khả năng dùng identity trong agent đó | Tệp khóa, agent khác và quyền tại máy chủ |
| Tạo cặp khóa mới | Có một danh tính mật mã mới để cấp quyền | Khóa cũ vẫn dùng được nếu còn được chấp nhận |
| Bỏ public key khỏi một tài khoản | Một đường cấp quyền tại tài khoản đó | Máy khác, tài khoản khác và nguồn cấp key động |
| Thu hồi certificate hoặc khóa theo cơ chế server | Ngăn xác thực mới trong phạm vi cơ chế đã triển khai | Phiên đã xác thực trước đó |
| Đóng phiên SSH | Chấm dứt phiên được xử lý | Khả năng mở phiên khác nếu credential còn hiệu lực |

Bảng này giúp tránh một lỗi phổ biến: hoàn tất một thao tác phía client rồi kết luận khóa đã bị thu hồi trên toàn hạ tầng.

### 10.2. Rotation chủ động

Trong một lần rotation theo kế hoạch, quy trình có thể gồm:

1. Chốt danh sách máy, tài khoản và nguồn cấp quyền đang chấp nhận khóa cũ.
2. Tạo cặp khóa mới tại nơi giữ khóa đã được phê duyệt; đăng ký owner và fingerprint.
3. Cấp quyền cho public key mới với scope phù hợp.
4. Kiểm thử xác thực bằng khóa mới trong một phiên độc lập.
5. Loại bỏ các đường tin cậy của khóa cũ và cập nhật nguồn cấu hình có thẩm quyền.
6. Kiểm thử khóa cũ bị từ chối, sau đó xác minh trạng thái các máy chưa áp dụng được.
7. Xử lý bản lưu cũ, cập nhật registry và lưu bằng chứng.

Khoảng thời gian hai khóa cùng được tin cậy cần có mục đích và thời điểm kết thúc. Không để giai đoạn chuyển đổi trở thành quyền tồn tại vĩnh viễn cho cả hai khóa.

Cần có đường quản trị độc lập được kiểm soát để tránh tự khóa mình ra ngoài. Không dùng chính phiên đang thay khóa làm bằng chứng duy nhất rằng đường đăng nhập mới hoạt động.

### 10.3. Kiểm thử âm phải thực sự dùng khóa cũ

Một lần SSH thất bại chưa đủ chứng minh thu hồi thành công: máy chủ có thể đang mất mạng. Ngược lại, đăng nhập thành công cũng chưa chứng minh khóa cũ còn hiệu lực nếu client đã dùng một identity khác.

Khi thiết kế phép thử, cần kiểm soát:

- Identity được đề xuất và certificate đi kèm.
- Agent có thể cung cấp khóa khác hay không.
- Các phương thức xác thực dự phòng.
- Kết nối đã xác thực được tái sử dụng qua multiplexing.
- Tài khoản, máy đích, đường đi và thời điểm thử.

Kết quả tốt có cả phép thử dương bằng credential mới và phép thử âm bằng credential cũ, cùng bằng chứng server phân biệt được hai trường hợp. Nếu một máy chưa thể kiểm tra, ghi rõ là chưa xác nhận thay vì coi mặc định đã thu hồi.

### 10.4. Thu hồi tập trung cần được triển khai thật tại server

OpenSSH có `RevokedKeys` để từ chối public key được liệt kê, có thể dùng danh sách hoặc KRL. Cấu hình và khả năng đọc tệp phải đúng; một tệp thu hồi không đọc được có thể gây từ chối xác thực public key rộng hơn dự định. Xem [sshd_config(5), RevokedKeys](https://man.openbsd.org/sshd_config.5).

Tạo một tệp KRL ở máy quản trị chưa có tác dụng với những server không tham chiếu hoặc chưa nhận bản cập nhật. Cần theo dõi độ phủ áp dụng, bao gồm máy offline và máy được tạo lại từ image cũ.

Nguồn cấu hình có thẩm quyền cũng phải được sửa. Nếu automation tiếp tục đồng bộ public key cũ vào máy chủ, việc xóa tay tại một nơi chỉ tạo ra trạng thái tạm thời.

## 11. Xử lý khi nghi private key bị lộ

### 11.1. Dấu hiệu cần kích hoạt quy trình

Một số tình huống đủ để mở điều tra:

- Có nội dung private key trong commit, artifact, log hoặc kênh trao đổi.
- Thiết bị giữ khóa bị mất hoặc có dấu hiệu bị điều khiển.
- Khóa được tìm thấy ở một nơi không nằm trong danh sách được phép.
- Có lần đăng nhập bằng fingerprint liên quan nhưng owner không giải thích được.
- Agent được chuyển tiếp đến một máy đã bị xác nhận xâm nhập.

Không cần chờ bằng chứng kẻ khác đã giải mã được khóa mới kiểm soát quyền truy cập. Mức khẩn cấp phụ thuộc phạm vi quyền, trạng thái thiết bị và các lớp bảo vệ còn đáng tin.

### 11.2. Các bước ứng phó

**Khoanh vùng và xác định phạm vi.** Dùng fingerprint, registry, lịch sử cấp quyền và log để xác định khóa liên quan. Bảo toàn bằng chứng qua kênh được kiểm soát; tránh tiếp tục phát tán tệp khóa bằng cách đính kèm nó vào ticket.

**Chặn khả năng lạm dụng.** Theo quyền hạn ứng phó đã xác định, thu hồi các đường tin cậy hoặc hạn chế truy cập liên quan. Cân nhắc tài khoản, certificate đã cấp, quyền cấp certificate mới, agent và endpoint. Nếu có phiên đáng ngờ đang hoạt động, xử lý phiên đó riêng.

**Cấp lại trên môi trường đáng tin cậy.** Tạo khóa thay thế từ endpoint được xác minh hoặc qua hệ thống giữ khóa phù hợp. Nếu máy cũ vẫn bị kiểm soát, sinh khóa mới trên máy ấy có thể làm lộ khóa thay thế ngay.

**Kiểm chứng thu hồi.** Kiểm tra các máy đích, nguồn cấu hình và cơ chế cấp quyền tập trung. Phân biệt trạng thái “đã gửi thay đổi”, “đã áp dụng” và “đã thử từ chối”.

**Điều tra và phục hồi.** Xem thời gian có thể bị lộ, các lần xác thực, hoạt động đặc quyền và secret khác có thể bị tiếp cận. Rotation một khóa SSH không tự xử lý mọi thay đổi mà kẻ xâm nhập đã tạo.

Thứ tự và mức song song phụ thuộc tình huống. Trong sự cố đang bị khai thác, ưu tiên kiềm chế rủi ro; không chờ hoàn tất mọi công việc rotation theo kế hoạch mới thu hồi khóa bị nghi lộ.

### 11.3. Ví dụ vận hành

Giả sử nhóm phát hiện khóa của một service đã được đưa vào artifact của pipeline. Artifact đã bị tải xuống và khóa có quyền vào ba máy backup.

Chỉ xóa artifact và đổi passphrase của tệp trong vault là chưa đủ. Nhóm cần xác định ba máy và các tài khoản chấp nhận khóa; thu hồi quyền của khóa cũ; cấp credential mới cho workload qua đường đáng tin cậy; kiểm tra job mới hoạt động và khóa cũ bị từ chối.

Nếu một trong ba máy đang offline, hồ sơ sự cố phải chỉ rõ trạng thái ấy cùng biện pháp ngăn máy quay lại phục vụ với cấu hình cũ. Đó là phần còn thiếu của phạm vi thu hồi, không phải một lỗi giấy tờ nhỏ.

## 12. Bài thực hành trong môi trường lab

### 12.1. Chuẩn bị

Dùng tài khoản lab riêng, một client được kiểm soát và một máy SSH đích có thể khôi phục. Nếu thực hành jump host, bổ sung máy jump được cấp quyền. Chuẩn bị phương án quản trị độc lập trước khi thay quyền đăng nhập.

Không dùng khóa production hoặc sao chép private key hiện có vào lab. Toàn bộ fingerprint, log và ticket trong phần thực hành phải gắn với danh tính lab.

### 12.2. Thực hiện

**Bước 1 — Tạo và đăng ký khóa.** Kiểm tra tên tệp mới, sinh khóa có passphrase theo ví dụ ở mục 5, rồi ghi nhận fingerprint, owner, mục đích và máy đích. Chỉ cấp public key cho tài khoản lab cần thiết.

**Bước 2 — Kiểm tra bản lưu.** Kiểm tra quyền tệp hoặc ACL, owner và vị trí lưu. Xác nhận thư mục không được chia sẻ hoặc đồng bộ ngoài phạm vi đã chọn. Lưu kết quả kiểm tra quyền; không in nội dung private key.

**Bước 3 — Kiểm tra agent.** Trong môi trường agent riêng của lab, nạp identity với lifetime ngắn. Dùng `ssh-add -l` trước và sau khi nạp, sau khi gỡ hoặc hết lifetime. Ghi lại fingerprint để tránh nhầm với identity khác.

Nếu client vẫn đăng nhập được sau khi identity hết lifetime, kiểm tra xem client có tự đọc tệp khóa hoặc dùng credential khác hay không. Đó không tự động là lỗi của lifetime agent.

**Bước 4 — Kiểm tra đường truy cập.** Quan sát `ssh -G`, xác minh host key theo quy trình lab và kết nối đến tài khoản được cấp phép. Nếu có jump host, xác nhận private key của máy đích không được chép lên jump host và agent forwarding phù hợp chính sách.

**Bước 5 — Thay passphrase.** Ghi fingerprint public key, thay passphrase tương tác trên khóa lab, rồi đối chiếu lại fingerprint. Giải thích vì sao đây chưa phải thay cặp khóa.

**Bước 6 — Rotation có kiểm soát.** Sinh một cặp khóa lab thứ hai với tên mới. Kiểm thử khóa mới qua một kết nối độc lập, thu hồi quyền của khóa thứ nhất và thử lại bằng đúng identity cũ với các đường dự phòng được kiểm soát.

**Bước 7 — Tổng hợp bằng chứng.** Ghi owner, fingerprint cũ và mới, phạm vi đích, thời điểm thay đổi, kết quả dương/âm và những phần chưa kiểm tra được. Khi kết thúc, xử lý tài khoản và credential lab theo quy trình của môi trường.

### 12.3. Tiêu chí hoàn thành

| Nội dung cần chứng minh | Bằng chứng chấp nhận được |
|---|---|
| Bản lưu được bảo vệ | Owner và quyền/ACL đúng trên chính tệp khóa lab |
| Credential có danh tính rõ | Registry chứa fingerprint, owner, scope và mục đích |
| Agent được giới hạn | Identity xuất hiện rồi được gỡ/hết lifetime trong agent đã chọn |
| Cấp quyền được thu hẹp | Khóa truy cập đúng tài khoản và phạm vi lab |
| Rotation hoàn thành | Khóa mới dùng được; khóa cũ bị từ chối trong phép thử có kiểm soát |
| Hồ sơ không chứa secret | Không có private key hoặc passphrase trong log và biên bản |

Việc agent hết lifetime và việc máy chủ từ chối khóa cũ là hai kết quả khác nhau, phải được chứng minh bằng hai phép quan sát phù hợp.

## 13. Lỗi thường gặp và cách suy luận

| Hiện tượng | Cần kiểm tra | Cách xử lý theo mục tiêu bảo vệ khóa |
|---|---|---|
| Client báo quyền private key quá rộng | Owner, quyền tệp, ACL, user chạy client | Sửa đúng đối tượng; không mở quyền cho toàn bộ người dùng |
| SSH hỏi passphrase nhiều lần | Có đúng agent/socket và identity hay không | Xác định tiến trình đang dùng agent nào trước khi nạp lại |
| SSH không hỏi passphrase | Agent đã có khóa, credential khác hoặc phiên tái sử dụng | Kiểm tra identity và đường xác thực; không suy ra khóa không được mã hóa |
| Gỡ khóa khỏi agent nhưng SSH vẫn dùng được | Tệp khóa vẫn còn, agent khác, phương thức khác | Phân biệt ngừng dùng tại client với thu hồi tại server |
| Khóa cũ dùng được sau rotation | Scope còn sót, cấu hình tự đồng bộ lại, raw key song song certificate | Sửa nguồn cấp quyền và kiểm chứng từng đường tin cậy |
| Không rõ ai đã đăng nhập | Khóa dùng chung, tài khoản dùng chung, thiếu log tương quan | Cấp danh tính riêng và liên kết audit PAM với tài khoản đích |
| Khóa có trong log đã được che trên UI | Log thô, artifact, bộ thu log hoặc bản tải xuống | Điều tra bản gốc và phạm vi phát tán; masking không đồng nghĩa chưa lộ |
| Khóa phần cứng không dùng được trên máy mới | Client, token, middleware và đăng ký credential | Kiểm tra tính tương thích; không chuyển sang khóa dùng chung để chữa tạm |

Log debug của SSH có thể hữu ích để xác định identity được đề xuất và phương thức xác thực. Dù thường không in private key, log vẫn có thể lộ tên máy, tài khoản, đường dẫn hoặc cấu trúc hạ tầng. Chia sẻ log qua kênh nội bộ phù hợp và giảm dữ liệu không cần thiết.

Không kiểm tra một tệp bằng cách dán private key vào công cụ web hoặc gửi toàn bộ tệp cho người hỗ trợ. Chẩn đoán thường có thể bắt đầu từ thông báo lỗi, loại khóa, fingerprint public key và quyền truy cập tệp.

## 14. Bằng chứng PAM và trách nhiệm vận hành

Một hồ sơ vận hành hữu ích cần trả lời được:

- Ai sở hữu khóa, ai phê duyệt quyền và ai có thể xuất hoặc sử dụng khóa?
- Khóa đang được chấp nhận cho những tài khoản, máy và tác vụ nào?
- Các giới hạn về thiết bị, thời gian và quyền được thực thi ở đâu?
- Khi owner rời nhóm, mất thiết bị hoặc xảy ra sự cố, ai thu hồi và mất bao lâu để kiểm chứng?
- Trạng thái nào chỉ được khai báo, trạng thái nào đã quan sát hoặc thử nghiệm?

Có thể lưu fingerprint, mã thay đổi, bản chụp quyền tệp, kết quả áp dụng cấu hình và kết quả thử xác thực. Với PAM broker, bổ sung định danh phiên và liên kết tới log được bảo vệ. Không cần thu thập private key để làm bằng chứng tuân thủ.

Phân biệt **không thấy sử dụng** với **không thể sử dụng**. Log không có đăng nhập trong một khoảng thời gian chỉ cho thấy hoạt động được quan sát; bằng chứng thu hồi cần mô tả cơ chế và kết quả từ chối.

Độ trưởng thành của kiểm soát thể hiện ở việc xử lý đầy đủ vòng đời: tạo đúng danh tính, bảo vệ đúng nơi, giới hạn đúng quyền, quan sát đúng hoạt động và vô hiệu hóa được mọi đường tin cậy khi cần. Với private key SSH, mục tiêu cuối cùng là kiểm soát ai có thể dùng khóa để thực hiện hành động đặc quyền, trong phạm vi nào và với bằng chứng gì.

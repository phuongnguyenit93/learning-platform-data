# SSH key, chứng chỉ SSH và quản lý tài khoản Linux

Máy ảo và máy chủ Linux trên đám mây cần một cơ chế xác định ai được phép đăng nhập, tài khoản đó được làm gì và cách thu hồi quyền khi người dùng hoặc workload không còn cần truy cập. SSH là phương thức quản trị từ xa phổ biến. Nếu mọi người dùng chung một mật khẩu hoặc một private key, việc truy vết và thu hồi quyền sẽ rất khó. Một hệ thống truy cập tốt cần danh tính riêng cho từng người hoặc workload, xác thực bằng khóa công khai hoặc chứng chỉ có thời hạn, phân quyền theo nhóm và ghi nhận hoạt động.

Bài học này trình bày cách tạo và sử dụng SSH key, cách tổ chức SSH certificate với Certificate Authority (CA), cùng vòng đời tài khoản Linux. Nội dung đặt các cơ chế này trong bối cảnh máy tính đám mây, nơi máy chủ có thể được tạo mới, thay thế hoặc mở rộng tự động.

Sau bài học, bạn có thể:

- Phân biệt public key, private key, host key và SSH certificate.
- Tạo, cài đặt, bảo vệ, kiểm tra và luân chuyển SSH key.
- Giải thích cách SSH CA cấp chứng chỉ người dùng và máy chủ có thời hạn.
- Tạo tài khoản Linux, quản lý nhóm, quyền sudo và khóa hoặc thu hồi tài khoản.
- Cấu hình SSH server an toàn và kiểm tra cấu hình trước khi áp dụng.
- Điều tra lỗi đăng nhập và xây dựng quy trình cấp, rà soát, thu hồi quyền truy cập.

## 1. Danh tính máy và tài khoản Linux

Linux phân biệt người dùng và nhóm bằng các mã số:

- **UID (User ID):** định danh một tài khoản người dùng.
- **GID (Group ID):** định danh nhóm chính của người dùng.
- **Supplementary groups:** các nhóm bổ sung mà tài khoản là thành viên.
- **Root:** tài khoản có UID 0, có quyền quản trị cao nhất trên hệ thống.

Thông tin tài khoản thường được phân giải qua cơ chế Name Service Switch (NSS). Trên máy Linux thông thường, **/etc/passwd** chứa thông tin tài khoản như tên, UID, GID, thư mục home và shell; **/etc/shadow** lưu thông tin xác thực mật khẩu được bảo vệ; **/etc/group** mô tả nhóm. Môi trường doanh nghiệp có thể lấy danh tính từ LDAP, Active Directory hoặc dịch vụ quản lý danh tính tập trung thông qua NSS/PAM.

Không nên coi một tên đăng nhập là danh tính duy nhất trên mọi máy. UID/GID, nguồn danh tính và chính sách nhóm có thể khác nhau giữa các máy. Khi triển khai một cụm máy, cần có cách đồng bộ danh tính hoặc quản lý quyền truy cập tập trung để tránh cùng một người có quyền khác nhau ngoài dự kiến.

Các lệnh kiểm tra cơ bản:

~~~bash
id alice
getent passwd alice
getent group cloud-operators
whoami
groups
~~~

Lệnh **getent** truy vấn qua cơ chế phân giải danh tính của hệ thống nên hữu ích hơn việc chỉ đọc trực tiếp một file cục bộ khi máy dùng danh tính tập trung.

## 2. SSH public key authentication hoạt động như thế nào?

SSH key authentication sử dụng một cặp khóa mật mã:

- **Private key:** được giữ bí mật trên máy của người dùng hoặc trong thiết bị bảo mật. Khóa này dùng để chứng minh người đăng nhập sở hữu danh tính tương ứng; không gửi private key lên máy chủ.
- **Public key:** có thể cài trên máy chủ để máy chủ kiểm tra chữ ký tạo bởi private key tương ứng.

Khi kết nối, máy khách yêu cầu xác thực bằng public key. Máy chủ kiểm tra public key có được cho phép đối với tài khoản đích hay không, sau đó xác minh chữ ký trong quá trình trao đổi SSH. Private key không rời khỏi máy khách trong quy trình xác thực thông thường.

Public key của người dùng thường được đặt trong **~/.ssh/authorized_keys** của tài khoản trên máy chủ. File này là danh sách các khóa được phép đăng nhập vào tài khoản đó. Nếu cùng một người truy cập nhiều máy, có thể cài cùng public key vào từng tài khoản được cấp quyền, hoặc dùng SSH CA để quản lý ở quy mô lớn.

### Tạo một cặp khóa

Với OpenSSH hiện đại, Ed25519 là lựa chọn gọn và mạnh cho phần lớn trường hợp:

~~~bash
ssh-keygen -t ed25519 -a 64 -C "alice@laptop-2026" -f ~/.ssh/id_ed25519
~~~

Lệnh tạo hai file:

- **~/.ssh/id_ed25519:** private key.
- **~/.ssh/id_ed25519.pub:** public key.

Khi được hỏi, nên đặt passphrase cho private key. Passphrase bảo vệ khóa khi file bị sao chép hoặc thiết bị bị mất. Nếu thiết bị có phần cứng bảo mật tương thích, có thể cân nhắc khóa FIDO như **ed25519-sk**. RSA vẫn có thể cần cho hệ thống cũ, nhưng nên dùng kích thước khóa và thuật toán chữ ký phù hợp với chính sách hiện hành của tổ chức.

Xem fingerprint để nhận diện khóa:

~~~bash
ssh-keygen -lf ~/.ssh/id_ed25519.pub
~~~

Fingerprint là dấu nhận diện ngắn của public key. Khi quản trị viên nhận public key từ người dùng, có thể đối chiếu fingerprint qua một kênh tin cậy để xác nhận đúng khóa đã được gửi.

### Bảo vệ private key

Private key phải được bảo vệ như một thông tin xác thực có quyền đăng nhập:

- Không gửi private key qua email, chat, ticket hoặc lưu trong repository.
- Không sao chép cùng một private key cho cả nhóm người dùng.
- Đặt passphrase và giới hạn quyền truy cập file.
- Dùng thiết bị mã hóa, secret storage hoặc phần cứng bảo mật phù hợp.
- Tạo khóa riêng cho từng người, thiết bị hoặc mục đích sử dụng để dễ thu hồi.
- Xoay vòng khóa theo chính sách và ngay khi nghi ngờ bị lộ.

Quyền file thường dùng:

~~~bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
~~~

Public key không cần giữ bí mật, nhưng vẫn cần được quản lý để biết khóa thuộc về ai và còn được phép sử dụng hay không. Trên máy chủ, thư mục **.ssh** và **authorized_keys** cần thuộc sở hữu đúng tài khoản. Quyền ghi quá rộng có thể khiến người khác thêm khóa của họ vào tài khoản.

## 3. Cài đặt public key và kết nối SSH

Trên hệ thống có **ssh-copy-id**, người dùng có thể cài public key vào tài khoản từ xa:

~~~bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub alice@vm-01.example.internal
~~~

Nếu không có **ssh-copy-id**, quản trị viên có thể thêm nội dung public key vào file **~/.ssh/authorized_keys** của tài khoản đích. Ví dụ trên máy chủ, khi đang có quyền quản trị:

~~~bash
install -d -m 700 -o alice -g alice /home/alice/.ssh
cat /tmp/alice_id_ed25519.pub >> /home/alice/.ssh/authorized_keys
chown alice:alice /home/alice/.ssh/authorized_keys
chmod 600 /home/alice/.ssh/authorized_keys
~~~

Đường dẫn home và tên nhóm trong ví dụ cần điều chỉnh theo tài khoản thực tế. Tránh ghi đè **authorized_keys** nếu file đã chứa các khóa hợp lệ khác; dùng thao tác thêm khóa có kiểm soát và kiểm tra nội dung sau khi thay đổi.

Kết nối bằng khóa cụ thể:

~~~bash
ssh -i ~/.ssh/id_ed25519 alice@vm-01.example.internal
~~~

Có thể khai báo cấu hình cho máy thường truy cập trong **~/.ssh/config**:

~~~sshconfig
Host orders-prod
    HostName vm-01.example.internal
    User alice
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ServerAliveInterval 30
~~~

Sau đó kết nối bằng **ssh orders-prod**. **IdentitiesOnly yes** giúp SSH chỉ thử danh tính đã chỉ định thay vì thử nhiều khóa từ agent, tránh một số lỗi do máy chủ giới hạn số lần xác thực.

### SSH agent và agent forwarding

SSH agent giữ khóa đã mở khóa trong phiên làm việc để người dùng không phải nhập passphrase mỗi lần. Ví dụ:

~~~bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
ssh-add -l
~~~

Agent forwarding (**ssh -A**) cho phép máy trung gian dùng agent của máy khách để xác thực tới máy tiếp theo. Điều này tiện khi cần nhảy qua bastion, nhưng máy trung gian có thể yêu cầu agent ký xác thực trong thời gian phiên được chuyển tiếp. Không nên bật forwarding tùy tiện trên máy không đáng tin cậy. Có thể dùng **ProxyJump** để đi qua bastion mà không phải chuyển tiếp agent:

~~~sshconfig
Host bastion
    HostName bastion.example.internal
    User alice
    IdentityFile ~/.ssh/id_ed25519

Host private-vm
    HostName 10.20.1.15
    User alice
    ProxyJump bastion
    IdentityFile ~/.ssh/id_ed25519
~~~

## 4. Phân biệt user key và host key

SSH sử dụng khóa ở cả hai phía:

- **User key** xác thực người hoặc workload với máy chủ. Public key được máy chủ tin cậy thông qua **authorized_keys** hoặc CA.
- **Host key** xác thực máy chủ với máy khách. Máy khách dùng host key hoặc chứng chỉ host để phát hiện kết nối tới đúng máy chủ, tránh giả mạo máy chủ.

Lần đầu kết nối, SSH thường hỏi có tin cậy fingerprint host key hay không rồi lưu vào **~/.ssh/known_hosts**. Quản trị viên nên lấy fingerprint từ console hoặc kênh quản trị đáng tin cậy và đối chiếu trước khi chấp nhận. **ssh-keyscan** có thể thu thập public host key từ mạng, nhưng bản thân nó không xác minh rằng máy đang trả lời là máy chủ thật.

Khi host key thay đổi do máy được tạo lại, máy khách có thể cảnh báo **REMOTE HOST IDENTIFICATION HAS CHANGED**. Không nên xóa cảnh báo một cách máy móc. Hãy xác minh thay đổi qua kênh tin cậy trước, sau đó mới cập nhật bản ghi **known_hosts**. Cảnh báo có thể là thay đổi hợp lệ sau khi thay máy, nhưng cũng có thể báo hiệu tấn công trung gian.

## 5. SSH certificate và Certificate Authority

Quản lý **authorized_keys** thủ công có thể phù hợp với vài máy, nhưng khó mở rộng khi có hàng trăm hoặc hàng nghìn máy. Khi người dùng thay đổi nhóm, nghỉ việc hoặc mất thiết bị, quản trị viên phải tìm và gỡ public key khỏi nhiều máy. SSH certificate giải quyết bài toán phân phối bằng cách để một CA ký xác nhận public key cùng các thuộc tính như danh tính, principal và thời hạn.

### Certificate hoạt động ra sao?

Người dùng vẫn giữ cặp khóa của mình. Họ gửi public key tới hệ thống cấp chứng chỉ. CA kiểm tra danh tính và quyền, sau đó dùng private key của CA ký một SSH certificate. Máy chủ tin cậy public key của CA nên có thể xác minh certificate mà không cần cài public key cá nhân vào từng **authorized_keys**.

Certificate thường mang các thông tin:

- Public key được chứng nhận.
- Loại certificate: user hoặc host.
- Key ID để nhận diện lần cấp.
- Principal, ví dụ tên tài khoản hoặc vai trò được phép.
- Thời điểm bắt đầu và hết hạn.
- Các tùy chọn hoặc extension được CA cấp.

Certificate có thời hạn ngắn giúp giảm thời gian một thông tin xác thực bị lộ còn sử dụng được. CA có thể cấp certificate mới sau khi người dùng xác thực qua SSO, MFA hoặc quy trình phê duyệt của tổ chức.

### Cấp user certificate với OpenSSH

Trong ví dụ minh họa, CA đã có một cặp khóa riêng được lưu an toàn. Người dùng tạo khóa cá nhân như phần trước và gửi public key tới hệ thống cấp certificate. Quản trị viên hoặc dịch vụ CA ký public key:

~~~bash
ssh-keygen -s /secure/ssh-user-ca \
  -I "alice-session-2026-11-22" \
  -n "alice" \
  -V "-5m:+8h" \
  ~/.ssh/id_ed25519.pub
~~~

Lệnh tạo file certificate có hậu tố **-cert.pub**, ví dụ **id_ed25519-cert.pub**. **-I** đặt key ID để tra cứu/audit; **-n** khai báo principal; **-V** đặt khoảng hiệu lực. Tên principal phải khớp chính sách mà SSH server kiểm tra. Đây là ví dụ ký trực tiếp để giải thích định dạng; trong tổ chức, private key của CA nên được giữ trong hệ thống bảo mật chuyên dụng và không được phân phối cho người dùng hoặc máy ứng dụng.

Trên SSH server, cài public key của CA và cấu hình **sshd_config**:

~~~sshconfig
PubkeyAuthentication yes
TrustedUserCAKeys /etc/ssh/user_ca.pub
AuthorizedPrincipalsFile .ssh/authorized_principals
~~~

File **/etc/ssh/user_ca.pub** chỉ chứa public key của CA. File **~/.ssh/authorized_principals** của tài khoản đích chứa các principal được phép, ví dụ:

~~~text
alice
~~~

Khi certificate có principal **alice**, server có thể cho phép đăng nhập vào tài khoản **alice** nếu chữ ký hợp lệ, certificate còn hạn, không bị thu hồi và các chính sách bổ sung đều đạt. Nếu không dùng **AuthorizedPrincipalsFile**, OpenSSH có quy tắc principal mặc định dựa trên tên tài khoản; cần kiểm tra chính sách thực tế trước khi phát hành.

Máy khách dùng private key và certificate tương ứng:

~~~bash
ssh -i ~/.ssh/id_ed25519 alice@vm-01.example.internal
~~~

OpenSSH tự tìm file certificate có hậu tố **-cert.pub** cạnh private key trong cấu hình mặc định. Có thể chỉ định rõ bằng tùy chọn **CertificateFile** khi cần.

### Host certificate

CA cũng có thể ký host public key. Khi máy khách tin cậy host CA, nhiều máy chủ có thể được xác thực bằng certificate mà không cần phân phối từng host key riêng. Trong **known_hosts**, quản trị viên có thể khai báo CA cho một phạm vi tên máy:

~~~text
@cert-authority *.example.internal ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... host-ca
~~~

Máy chủ được cấu hình **HostCertificate** trỏ tới certificate đã ký. Host certificate giúp máy khách xác minh danh tính máy chủ theo CA, nhưng cần quản lý vòng đời host key, certificate và phạm vi tên miền cẩn thận. Không dùng wildcard quá rộng nếu các vùng tên thuộc những mức tin cậy khác nhau.

### Bảo vệ CA và thu hồi certificate

CA là điểm tin cậy quan trọng. Nếu private key của CA bị lộ, kẻ tấn công có thể ký certificate cho danh tính khác. Vì vậy:

- Giữ private key CA trong HSM, KMS phù hợp hoặc máy ký chuyên dụng được kiểm soát chặt.
- Chỉ cấp quyền ký cho dịch vụ hoặc người được ủy quyền.
- Ghi log người yêu cầu, principal, key ID, thời hạn và kết quả phê duyệt.
- Dùng certificate thời hạn ngắn, giới hạn principal và tùy chọn theo nhu cầu.
- Có kế hoạch luân chuyển CA, phân phối CA public key mới và ngừng tin cậy CA cũ.
- Có quy trình thu hồi và cập nhật danh sách thu hồi trên toàn bộ server.

OpenSSH hỗ trợ Key Revocation List (KRL). Quản trị viên có thể tạo KRL từ public key cần thu hồi:

~~~bash
ssh-keygen -k -f /etc/ssh/revoked_keys.krl revoked_key.pub
~~~

Sau đó cấu hình server:

~~~sshconfig
RevokedKeys /etc/ssh/revoked_keys.krl
~~~

KRL có thể chứa khóa hoặc certificate bị thu hồi. Khi cập nhật KRL đã tồn tại, cần dùng quy trình cập nhật phù hợp, phân phối file mới tới tất cả server và xác minh server đã nạp danh sách đó. Thu hồi certificate không thay thế việc điều tra thiết bị bị xâm nhập, xoay vòng các khóa liên quan và rà soát phiên đăng nhập hiện hữu.

## 6. Quản lý tài khoản Linux

Tài khoản nên được tạo theo vai trò và nhu cầu công việc. Không nên dùng chung tài khoản quản trị cho nhiều người vì log sẽ không thể hiện rõ ai đã thực hiện thao tác.

### Tạo tài khoản và nhóm

Ví dụ tạo tài khoản **alice** có home directory và shell đăng nhập:

~~~bash
sudo useradd --create-home --shell /bin/bash alice
sudo groupadd cloud-operators
sudo usermod --append --groups cloud-operators alice
id alice
~~~

**--append** (tương đương **-a**) rất quan trọng khi thêm nhóm bằng **usermod -G**: nếu bỏ **-a**, danh sách nhóm bổ sung hiện tại có thể bị thay thế. Tên nhóm quản trị tùy bản phân phối; Ubuntu/Debian thường dùng **sudo**, trong khi nhiều bản phân phối khác dùng **wheel**.

Thư mục home, shell và nhóm cần theo chuẩn của hệ thống. Tài khoản dịch vụ không cần đăng nhập tương tác nên thường dùng shell như **/usr/sbin/nologin** hoặc đường dẫn tương ứng trên bản phân phối:

~~~bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin orders-api
~~~

Không cấp SSH key cho tài khoản dịch vụ nếu workload có thể dùng machine identity hoặc cơ chế xác thực chuyên dụng.

### Cấp quyền sudo theo nguyên tắc tối thiểu

Không nên cấp quyền root đầy đủ cho mọi người chỉ vì họ cần khởi động lại một dịch vụ. Có thể cấp đúng lệnh cần thiết qua file trong **/etc/sudoers.d/**. Luôn sửa bằng **visudo** để kiểm tra cú pháp:

~~~bash
sudo visudo -f /etc/sudoers.d/orders-operator
sudo visudo -c
sudo -l -U alice
~~~

Ví dụ nội dung chính sách có thể cho phép một nhóm vận hành chạy một số lệnh đã được xác định:

~~~sudoers
%cloud-operators ALL=(root) /usr/bin/systemctl status orders-api, /usr/bin/systemctl restart orders-api
~~~

Đường dẫn lệnh phải khớp máy thực tế và cần đánh giá liệu quyền restart dịch vụ có cho phép gián tiếp thực thi lệnh tùy ý thông qua file cấu hình hoặc script có thể sửa hay không. Tránh **NOPASSWD: ALL** nếu không có yêu cầu được phê duyệt và biện pháp kiểm soát tương ứng.

### Khóa, hết hạn và xóa tài khoản

Khi người dùng tạm ngừng công việc, quản trị viên có thể khóa xác thực bằng mật khẩu:

~~~bash
sudo passwd --lock alice
sudo chage -l alice
~~~

Lưu ý: khóa mật khẩu không nhất thiết vô hiệu hóa đăng nhập bằng public key. Nếu tài khoản có **authorized_keys** hoặc được chấp nhận qua SSH CA, người dùng vẫn có thể đăng nhập bằng cơ chế khóa công khai tùy cấu hình PAM và chính sách của hệ thống. Để thu hồi SSH access, cần gỡ khóa hoặc certificate trust tương ứng, thu hồi principal/nhóm, áp dụng thời hạn tài khoản và kiểm tra các đường truy cập khác.

Để đặt ngày hết hạn tài khoản:

~~~bash
sudo usermod --expiredate 2026-12-31 alice
~~~

Định dạng ngày là **YYYY-MM-DD**. Với tài khoản đã rời tổ chức, quy trình có thể gồm khóa hoặc hết hạn tài khoản, gỡ khỏi nhóm truy cập, thu hồi SSH key/certificate, thu hồi quyền sudo, vô hiệu hóa token và phiên liên quan, lưu giữ dữ liệu cần thiết theo chính sách rồi mới xóa tài khoản.

Xóa tài khoản:

~~~bash
sudo userdel --remove alice
~~~

**--remove** xóa home directory và mail spool của tài khoản trên máy đó. Chỉ thực hiện sau khi đã xác nhận dữ liệu cần lưu trữ, quyền sở hữu file và phụ thuộc của dịch vụ. Trong môi trường dùng LDAP/AD hoặc danh tính tập trung, cần thu hồi tại nguồn danh tính có thẩm quyền; xóa một bản ghi cục bộ có thể không đủ.

## 7. Cấu hình SSH server an toàn

SSH daemon thường đọc cấu hình từ **/etc/ssh/sshd_config** và các file được include. Một cấu hình cơ sở có thể như sau:

~~~sshconfig
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PermitEmptyPasswords no
MaxAuthTries 4
LoginGraceTime 30
X11Forwarding no
AllowGroups cloud-operators
~~~

Đây là mẫu tham khảo, không phải cấu hình dùng nguyên xi cho mọi hệ thống. **AllowGroups** giới hạn SSH login vào nhóm được chỉ định; cần thêm đúng người dùng vào nhóm trước khi bật, nếu không có thể khóa quyền truy cập của toàn bộ đội vận hành. Một số môi trường cần keyboard-interactive cho MFA; khi đó không được tắt phương thức này nếu chưa thay bằng cơ chế MFA tương đương. Một số dịch vụ cũng cần port forwarding hoặc X11; chỉ tắt khi không có nhu cầu.

Trước khi áp dụng:

1. Giữ phiên SSH quản trị hiện tại mở.
2. Mở một phiên mới và xác nhận ít nhất một tài khoản quản trị khác đăng nhập được.
3. Kiểm tra cú pháp cấu hình:

~~~bash
sudo sshd -t
~~~

4. Xem cấu hình hiệu lực khi cần:

~~~bash
sudo sshd -T | grep -E 'pubkeyauthentication|passwordauthentication|permitrootlogin|allowgroups'
~~~

5. Chỉ reload sau khi kiểm tra thành công:

~~~bash
sudo systemctl reload sshd
~~~

Một số bản phân phối đặt tên service là **ssh** thay vì **sshd**. Hãy xác định đúng service name của hệ thống. Sau khi reload, thử đăng nhập từ một phiên mới trước khi đóng phiên quản trị ban đầu. Nếu lỗi, dùng phiên đang mở để khôi phục cấu hình.

### Giới hạn quyền theo nhóm hoặc tài khoản

**AllowUsers**, **AllowGroups**, **DenyUsers** và **DenyGroups** có thể giới hạn ai được kết nối. Các khối **Match User** hoặc **Match Group** áp dụng chính sách riêng cho nhóm tài khoản, chẳng hạn tài khoản tự động chỉ được dùng một lệnh cụ thể hoặc không được mở shell tương tác.

Một dòng trong **authorized_keys** cũng có thể giới hạn cách dùng khóa, ví dụ giới hạn nguồn IP hoặc ép chạy một command. Các tùy chọn này cần được kiểm thử kỹ để không vô tình cấp quyền rộng hơn dự kiến. Với tài khoản automation, có thể dùng **restrict** và **command="..."** khi mô hình công việc phù hợp; command bị ép phải được viết an toàn và không tin cậy tham số đầu vào.

## 8. Áp dụng trong môi trường điện toán đám mây

Trên đám mây, máy ảo có thể được tạo mới từ image hoặc thay thế bởi autoscaling. Việc gắn khóa cá nhân thủ công vào từng máy dễ tạo ra danh sách khóa không đồng bộ. Một số cách tổ chức phổ biến:

- **Bootstrap key:** nền tảng chèn public key ban đầu vào VM để người quản trị thiết lập máy. Cần giới hạn người có quyền tạo hoặc thay đổi key metadata.
- **Bastion hoặc access gateway:** người dùng kết nối qua điểm quản trị tập trung, giảm số máy phải mở SSH trực tiếp ra mạng.
- **SSH CA:** hệ thống cấp certificate sau khi người dùng xác thực qua SSO/MFA, với principal và thời hạn ngắn.
- **Machine identity:** workload dùng danh tính dịch vụ, instance identity hoặc token ngắn hạn để truy cập dịch vụ khác thay vì chia sẻ SSH private key.
- **Configuration management:** công cụ quản lý cấu hình đồng bộ nhóm, chính sách SSH, CA public key và trạng thái tài khoản trên các máy.

Không nên mở cổng SSH công khai cho toàn Internet nếu có thể giới hạn qua VPN, private network, bastion hoặc chính sách firewall theo nguồn. Security group/firewall cần cho phép đúng nguồn và đúng cổng. Việc xác thực mạnh ở SSH không thay thế phân đoạn mạng.

Với nhóm máy tự động thay thế, danh tính và quyền truy cập nên được cấp theo trạng thái khai báo. Khi instance bị hủy, quyền truy cập gắn với instance cần hết hiệu lực hoặc được thu hồi tự động. Tránh nhúng private key dùng chung vào machine image; mọi máy được tạo từ image đó sẽ mang cùng một bí mật và làm tăng phạm vi ảnh hưởng khi một máy bị xâm nhập.

## 9. Điều tra lỗi SSH và lỗi tài khoản

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| **Permission denied (publickey)** | Sai user, sai key, public key chưa được cài hoặc principal không khớp | **ssh -vvv**, kiểm tra **authorized_keys**, certificate và log server |
| SSH bỏ qua khóa mong muốn | Agent có nhiều khóa hoặc client chọn identity khác | Dùng **-i**, **IdentitiesOnly yes**, kiểm tra **ssh-add -l** |
| Server từ chối do quyền file | Home, **.ssh** hoặc **authorized_keys** có owner/mode không phù hợp | **namei -l /home/alice/.ssh/authorized_keys**, **stat** |
| Host key changed | Máy được tạo lại hoặc có khả năng giả mạo host | Đối chiếu fingerprint qua kênh tin cậy trước khi cập nhật **known_hosts** |
| Certificate expired/invalid | Hết hạn, chưa đến thời điểm hiệu lực, CA không được tin cậy hoặc principal sai | **ssh-keygen -Lf id_ed25519-cert.pub**, kiểm tra thời gian hệ thống và cấu hình CA |
| Đăng nhập được nhưng không có quyền quản trị | Thiếu nhóm sudo/wheel hoặc sudoers không hợp lệ | **id**, **sudo -l**, **visudo -c** |
| Tài khoản bị từ chối dù key đúng | Tài khoản hết hạn, shell không hợp lệ, PAM hoặc AllowGroups chặn | **getent passwd**, **chage -l**, log xác thực và **sshd -T** |

Trên máy khách, bật verbose để thấy quá trình thương lượng:

~~~bash
ssh -vvv -i ~/.ssh/id_ed25519 alice@vm-01.example.internal
~~~

Trên máy chủ, log có thể nằm trong journal:

~~~bash
sudo journalctl -u sshd --since "15 minutes ago"
~~~

Một số hệ thống ghi log xác thực vào **/var/log/auth.log** hoặc **/var/log/secure**. Đường dẫn và tên service phụ thuộc bản phân phối. Log có thể chứa tên tài khoản, địa chỉ IP và thông tin vận hành; chỉ người có quyền phù hợp mới được truy cập.

## 10. Rà soát và luân chuyển quyền truy cập

Một khóa hoặc tài khoản không nên tồn tại vô thời hạn chỉ vì chưa gây sự cố. Hãy duy trì danh mục gồm chủ sở hữu, mục đích, máy hoặc nhóm máy được phép truy cập, thời điểm tạo, ngày hết hạn và trạng thái sử dụng.

Quy trình luân chuyển khóa cá nhân có thể gồm:

1. Người dùng tạo cặp khóa mới trên thiết bị được quản lý.
2. Public key mới được xác minh và cấp quyền theo đúng tài khoản/principal.
3. Người dùng kiểm thử kết nối bằng khóa mới trong khi khóa cũ vẫn còn hiệu lực.
4. Quản trị viên gỡ khóa cũ khỏi **authorized_keys** hoặc ngừng cấp certificate dựa trên khóa cũ.
5. Rà soát log và danh mục để xác nhận không còn máy nào phụ thuộc khóa cũ.

Nếu private key bị lộ, cần thu hồi ngay public key hoặc certificate tương ứng, thu hồi phiên và token liên quan khi có thể, rà soát log đăng nhập, kiểm tra thay đổi tài khoản/sudoers và đánh giá khả năng kẻ tấn công đã duy trì quyền truy cập. Chỉ tạo khóa mới mà không gỡ khóa bị lộ sẽ không giải quyết được sự cố.

Đối với tài khoản nhân sự, nên tích hợp vòng đời cấp quyền với quy trình onboarding, thay đổi vai trò và offboarding. Quyền truy cập phải được rà soát định kỳ theo chủ sở hữu và nhu cầu công việc. Tài khoản khẩn cấp cần có người chịu trách nhiệm, kiểm soát phê duyệt, cảnh báo khi sử dụng và kiểm tra sau mỗi lần truy cập.

## 11. Ví dụ: cấp quyền SSH cho một kỹ sư vận hành

Giả sử nhóm có một VM chạy API đặt hàng. Kỹ sư Alice cần xem trạng thái dịch vụ và được phép restart riêng **orders-api**. Nhóm không muốn cấp quyền root tương tác đầy đủ.

**Bước 1: Tạo tài khoản và nhóm truy cập**

~~~bash
sudo groupadd cloud-operators
sudo useradd --create-home --shell /bin/bash alice
sudo usermod --append --groups cloud-operators alice
~~~

**Bước 2: Cài public key đã xác minh**

Alice tạo khóa Ed25519 trên máy cá nhân và gửi file **.pub** qua kênh được phê duyệt. Quản trị viên đối chiếu fingerprint, sau đó cài public key vào **authorized_keys** của Alice với owner và mode phù hợp.

**Bước 3: Cấp quyền sudo giới hạn**

Quản trị viên dùng **visudo -f /etc/sudoers.d/orders-operator** để thêm chính sách phù hợp với đường dẫn **systemctl** trên máy:

~~~sudoers
alice ALL=(root) /usr/bin/systemctl status orders-api, /usr/bin/systemctl restart orders-api
~~~

Sau đó kiểm tra:

~~~bash
sudo visudo -c
sudo -l -U alice
~~~

**Bước 4: Kiểm tra SSH và quyền**

Alice đăng nhập bằng public key, kiểm tra **id** và **sudo -l**, chạy lệnh status. Nhóm vận hành xác nhận Alice không thể thực hiện lệnh quản trị ngoài danh sách được cấp.

**Bước 5: Thu hồi khi đổi vai trò**

Khi Alice không còn phụ trách dịch vụ, nhóm gỡ quyền sudo, gỡ khóa khỏi **authorized_keys** hoặc thu hồi certificate/principal, xóa Alice khỏi nhóm truy cập và xác nhận phiên đăng nhập hiện hữu đã được xử lý theo chính sách. Nếu Alice nghỉ việc, quy trình offboarding còn phải thu hồi các danh tính và token khác có liên quan.

Ví dụ này minh họa quyền được gắn với từng người và vai trò cụ thể. Với nhiều VM, có thể chuyển phần cấp certificate và đồng bộ nhóm sang hệ thống danh tính tập trung để giảm thao tác thủ công.

## 12. Checklist quản lý SSH và tài khoản

- [ ] Mỗi người dùng hoặc workload có danh tính riêng.
- [ ] Private key được giữ bí mật, có passphrase hoặc bảo vệ bằng phần cứng phù hợp.
- [ ] Public key được xác minh fingerprint trước khi cấp quyền.
- [ ] Host key hoặc host certificate được xác minh để tránh kết nối nhầm máy chủ.
- [ ] File **.ssh** và **authorized_keys** có owner và mode phù hợp.
- [ ] Không dùng chung private key hoặc nhúng private key vào image.
- [ ] Tài khoản có shell, home và nhóm đúng nhu cầu.
- [ ] Quyền sudo được giới hạn theo lệnh và vai trò.
- [ ] SSH server chỉ bật các phương thức xác thực được phê duyệt.
- [ ] Thay đổi **sshd_config** được kiểm tra cú pháp và thử bằng phiên mới trước khi đóng phiên cũ.
- [ ] SSH certificate có principal, thời hạn và CA được quản lý.
- [ ] Có danh sách thu hồi và quy trình xử lý khóa bị lộ.
- [ ] Có log, danh mục khóa/tài khoản và rà soát quyền định kỳ.
- [ ] Quy trình offboarding thu hồi cả khóa, certificate, nhóm, token và phiên liên quan.

## 13. Bài tập vận dụng

Một nhóm vận hành quản lý 40 máy Linux trên hai vùng đám mây. Hiện tại, 5 kỹ sư dùng chung một SSH key được cài trong **authorized_keys** trên tất cả máy. Một kỹ sư chuyển sang nhóm khác và nhóm cần cấp quyền tạm thời cho một nhà thầu trong 4 giờ.

1. Những rủi ro nào xuất hiện khi nhiều người dùng chung một private key?
2. Hãy đề xuất cách chuyển sang danh tính riêng và SSH certificate có principal, thời hạn ngắn.
3. Máy chủ cần cấu hình những gì để tin cậy user CA và giới hạn principal được phép?
4. Khi nhà thầu kết thúc công việc, nhóm cần thu hồi những quyền nào? Vì sao chỉ khóa mật khẩu Linux là chưa đủ?
5. Nếu một máy báo **REMOTE HOST IDENTIFICATION HAS CHANGED**, nhóm cần xác minh điều gì trước khi sửa **known_hosts**?

Gợi ý: cấp một cặp khóa riêng cho mỗi kỹ sư, dùng hệ thống xác thực tập trung để cấp certificate tối đa 4 giờ với principal được giới hạn. Máy chủ tin cậy public key của CA và kiểm tra principal theo chính sách. Khi kết thúc, ngừng cấp certificate, thu hồi certificate/khóa nếu cần, gỡ quyền nhóm và xử lý phiên còn hoạt động. Với host key thay đổi, xác minh fingerprint qua console hoặc kênh quản trị đáng tin cậy trước khi cập nhật.

## Kết luận

SSH key giúp xác thực mà không phải chia sẻ mật khẩu, còn SSH certificate cho phép quản lý quyền truy cập theo danh tính, principal và thời hạn thông qua CA. Tài khoản Linux và nhóm xác định người dùng có thể làm gì sau khi đăng nhập; sudo cấp quyền quản trị có kiểm soát. Khi kết hợp danh tính riêng, bảo vệ private key, xác minh host, chính sách server an toàn, log và quy trình thu hồi, đội vận hành có thể quản lý truy cập máy chủ đám mây nhất quán và có thể kiểm toán.

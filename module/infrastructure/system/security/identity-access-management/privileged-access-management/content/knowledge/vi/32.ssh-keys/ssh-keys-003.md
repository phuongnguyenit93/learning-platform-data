# SSH certificate authority

## Mục tiêu và tình huống sử dụng

Trong hệ thống quản lý truy cập đặc quyền (PAM), SSH certificate authority (SSH CA) là bên ký chứng chỉ để gắn một public key với danh tính, phạm vi truy cập và khoảng thời gian được phép sử dụng. Thay vì chép public key của từng quản trị viên lên hàng trăm máy, đội vận hành phân phối public key của CA đến những nơi cần xác minh chứng chỉ.

Bài thuộc chương **SSH và key**, tập trung vào cách đưa SSH CA vào quy trình kiểm kê quyền, least privilege, cấp quyền vừa đúng lúc (JIT), giám sát và lưu bằng chứng. Sau bài học, người học có thể:

- Phân biệt user certificate, host certificate và khóa của CA.
- Thiết kế principal để kiểm soát tài khoản và nhóm máy được truy cập.
- Thực hiện một luồng cấp chứng chỉ ngắn hạn trong phòng lab.
- Giải thích vai trò của thu hồi, bảo vệ CA, đồng bộ thời gian và kiểm toán.
- Nhận diện những giới hạn mà chứng chỉ SSH không tự giải quyết.

Tình huống xuyên suốt: Alice cần vào `app01.prod.example.internal` để điều tra sự cố theo ticket `INC-2041`. Quyền được cấp trong khoảng 30 phút, phải đi qua đường truy cập đã quản lý và không được biến thành quyền root thường trực. Các tên miền, địa chỉ IP và số serial trong bài là dữ liệu minh họa.

## 1. Từ public key phân tán đến điểm tin cậy có quản lý

Với mô hình public key truyền thống, mỗi tài khoản đích thường có danh sách khóa được phép trong `authorized_keys`. Khi một người chuyển bộ phận, mất thiết bị hoặc kết thúc hợp đồng, tổ chức phải tìm và gỡ khóa khỏi mọi máy có liên quan. Một mục bị bỏ sót có thể duy trì quyền truy cập rất lâu.

SSH CA chuyển phần lớn quyết định cấp chứng chỉ vào một dịch vụ tập trung. Máy đích vẫn thực hiện kiểm tra và áp dụng chính sách tại chỗ; nó không chuyển toàn bộ trách nhiệm phân quyền cho CA.

| Thành phần | Vai trò | Vật liệu cần bảo vệ hoặc quản lý |
| --- | --- | --- |
| Khóa cá nhân của người dùng | Chứng minh người kết nối giữ private key tương ứng | Private key, passphrase hoặc thiết bị giữ khóa |
| User certificate | Mang thông tin đã ký cho việc xác thực người dùng | Principal, hạn dùng, serial, key ID, hạn chế |
| User CA | Ký user certificate theo quyết định cấp quyền | Private key CA và chính sách cho phép ký |
| Host certificate | Giúp client xác thực danh tính máy chủ | Tên host, hạn dùng và public key của host |
| Host CA | Ký chứng chỉ cho máy chủ đã được kiểm chứng | Private key CA và quy trình đăng ký host |
| Chính sách trên máy đích | Quyết định certificate được vào tài khoản nào | CA tin cậy, ánh xạ principal, quyền hệ điều hành |

OpenSSH sử dụng định dạng chứng chỉ riêng, khác X.509 của hệ thống TLS. User certificate và host certificate phục vụ hai chiều xác thực khác nhau. [Tài liệu chứng chỉ của OpenSSH](https://man.openbsd.org/ssh-keygen#CERTIFICATES).

Việc triển khai CA không tự xóa các đường truy cập cũ. Nếu raw public key, mật khẩu hoặc một cơ chế xác thực khác vẫn được chấp nhận, người dùng có thể đi theo đường đó mà không cần xin certificate mới. Vì vậy, kế hoạch chuyển đổi phải kiểm kê cả đường truy cập chính và ngoại lệ.

## 2. Chứng chỉ công khai không thay thế private key

Một certificate SSH chứa public key được chứng nhận cùng dữ liệu do CA ký. Client vẫn phải chứng minh đang giữ private key tương ứng khi xác thực. Chỉ lấy được file `-cert.pub` không đủ để đăng nhập.

Có ba loại private key cần phân biệt:

1. **Private key của người dùng:** nằm ở thiết bị người dùng hoặc phương tiện giữ khóa được quản lý.
2. **Private host key:** nằm trên máy chủ, dùng để chứng minh máy chủ giữ khóa được chứng nhận.
3. **Private key CA:** chỉ dùng cho hoạt động ký; không phân phối đến máy người dùng hay máy chủ thông thường.

Điểm thứ ba là ranh giới đặc quyền quan trọng. Lộ một khóa người dùng ảnh hưởng đến các quyền mà khóa đó có thể sử dụng. Lộ khóa CA có thể cho phép kẻ giữ khóa tạo ra chứng chỉ mới trong toàn bộ phạm vi đang tin CA đó.

Certificate không phải bí mật tương đương private key nhưng vẫn chứa dữ liệu nhạy cảm về tổ chức: tên người, vai trò, ticket hoặc tên host. Chỉ ghi thông tin cần thiết và tránh đưa token, mật khẩu, nội dung sự cố hay dữ liệu cá nhân không cần thiết vào key ID.

## 3. User CA và Host CA giải quyết hai câu hỏi khác nhau

### 3.1. User CA: ai được truy cập?

Máy chủ giữ public key của User CA. Khi Alice trình certificate, máy chủ kiểm tra chứng chỉ và đối chiếu chính sách tài khoản đích.

Ví dụ quyết định truy cập cần trả lời:

- CA ký có nằm trong tập được máy chủ tin cậy không?
- Chứng chỉ có đúng loại user và còn hiệu lực không?
- Public key trong chứng chỉ có khớp với bằng chứng giữ private key không?
- Principal có được chấp nhận cho tài khoản đích không?
- Chứng chỉ hoặc khóa có bị thu hồi không?
- Điều kiện nguồn kết nối và cấu hình máy chủ có cho phép không?

Danh sách trên mô tả các điều kiện phải thỏa, không phải cam kết về thứ tự kiểm tra nội bộ của OpenSSH.

### 3.2. Host CA: đang kết nối đúng máy nào?

Client giữ public key của Host CA và phạm vi tên máy được tin. Máy chủ trình host certificate tương ứng với private host key mà nó đang giữ.

Nếu client gọi `app01.prod.example.internal` thì cấu hình tin cậy và tên trong certificate phải phù hợp với tên được client xác minh. Việc ký certificate cho một host đòi hỏi quy trình chứng minh quyền đăng ký tên đó; chỉ nhận một public key rồi ký theo hostname người gửi yêu cầu là chưa đủ.

Host CA hữu ích khi máy chủ được tạo lại thường xuyên: public host key có thể thay đổi nhưng client tiếp tục tin vào CA đã được phân phối qua kênh quản lý. Điều này chỉ an toàn khi quy trình ký host kiểm soát chặt việc cấp tên.

### 3.3. Tách miền tin cậy

Một thiết kế PAM nên cân nhắc các CA riêng cho:

- User và host.
- Production và môi trường thử nghiệm.
- Con người và workload tự động khi yêu cầu kiểm soát khác nhau.
- Miền hạ tầng có mức ảnh hưởng hoặc chủ sở hữu khác nhau.

Đây là quyết định về phạm vi ảnh hưởng, không phải yêu cầu mỗi máy cần một CA. Quá nhiều CA cũng làm tăng chi phí phân phối, xoay khóa và phục hồi.

Không giả định có thể xây chuỗi root/intermediate giống TLS rồi đưa root cho mọi máy là xong. Mô hình chứng chỉ OpenSSH thông thường xác minh với khóa CA được cấu hình tin cậy trực tiếp. Thiết kế phải chỉ rõ khóa ký nào thực sự có mặt trong trust store của bên xác minh.

## 4. Principal là ràng buộc truy cập, không phải nhãn trang trí

Principal là tên được CA đưa vào certificate. Đối với user certificate, principal có thể là danh tính cá nhân hoặc một tên vai trò được chính sách phía máy chủ ánh xạ đến tài khoản đích.

Ví dụ:

| Principal | Ý nghĩa trong thiết kế minh họa |
| --- | --- |
| `alice@example.internal` | Danh tính cá nhân Alice |
| `prod-app-incident` | Vai trò ứng phó sự cố trên nhóm máy ứng dụng production |
| `stage-app-maintenance` | Vai trò bảo trì trong staging |
| `backup-export` | Vai trò dành cho một tác vụ tự động được giới hạn |

Tên vai trò không tự tạo ra giới hạn hệ điều hành. Nếu `prod-app-incident` được ánh xạ đến tài khoản có `sudo ALL` thì certificate vẫn dẫn đến quyền rất lớn. Least privilege cần được thực thi bằng tài khoản, nhóm, sudo policy, lệnh được phép và đường truy cập.

Trong mô hình sử dụng `TrustedUserCAKeys`, `AuthorizedPrincipalsFile` có thể xác định những principal được chấp nhận cho từng tài khoản. Nếu không dùng cơ chế ánh xạ đó, mặc định liên quan đến tên tài khoản đăng nhập; không nên đoán ánh xạ từ key ID. [Cấu hình principal trong sshd_config](https://man.openbsd.org/sshd_config#AuthorizedPrincipalsFile).

### 4.1. Tách danh tính, vai trò và tài khoản đích

Giả sử:

~~~text
Danh tính IdP: alice@example.internal
Vai trò được phê duyệt: prod-app-incident
Tài khoản Linux đích: alice
Ticket: INC-2041
~~~

Một certificate mang principal `prod-app-incident` có thể được phép vào tài khoản `alice` nếu chính sách cho tài khoản này chấp nhận principal đó. Điều này cũng có nghĩa là bất kỳ người nào có certificate cùng principal đều có thể vượt qua phần kiểm tra principal cho tài khoản ấy, trừ khi có ràng buộc bổ sung.

Vì vậy, không được coi role principal dùng chung là đủ để bảo đảm chỉ Alice vào được tài khoản `alice`. Thiết kế cần lựa chọn rõ:

- Dùng principal cá nhân cho tài khoản cá nhân, còn vai trò được quyết định bằng phạm vi cấp chứng chỉ và chính sách máy đích.
- Dùng principal kết hợp như `alice:prod-app-incident` và ánh xạ chính xác.
- Dùng cơ chế quyết định động có kiểm tra cả danh tính, tài khoản đích và tài nguyên.

Phòng lab trong bài chọn principal kết hợp để biểu diễn rõ ràng quan hệ này. Production có thể chọn cách khác nhưng phải chứng minh được kiểm thử âm: Bob có cùng vai trò vẫn không tự đăng nhập vào tài khoản Alice.

### 4.2. Key ID không phải trường phân quyền mặc định

Key ID phục vụ truy vết và có thể hỗ trợ quy trình thu hồi. Đặt key ID thành `root` không làm certificate tự có quyền root; ngược lại, key ID mang tên Alice không ngăn certificate có principal quá rộng.

Một quy ước minh họa:

~~~text
subject=alice;role=prod-app-incident;ticket=INC-2041;request=req-7842
~~~

Dịch vụ ký phải tự dựng key ID và principal từ dữ liệu đã xác thực. Không chuyển nguyên yêu cầu do client tự khai thành nội dung được ký.

## 5. Luồng cấp chứng chỉ trong PAM

~~~mermaid
sequenceDiagram
    participant U as Alice và thiết bị giữ khóa
    participant P as Cổng PAM
    participant D as IdP và bộ quyết định quyền
    participant C as Dịch vụ ký User CA
    participant H as Máy đích
    participant A as Kho bằng chứng
    U->>P: Yêu cầu truy cập, public key, ticket
    P->>D: Xác thực, MFA, kiểm tra quyền và tài nguyên
    D-->>P: Cho phép với phạm vi và hạn dùng
    P->>C: Yêu cầu ký đã chuẩn hóa
    C-->>U: User certificate ngắn hạn
    C->>A: Serial, key ID, fingerprint, quyết định
    U->>H: Kết nối bằng private key và certificate
    H->>H: Kiểm tra CA, principal và chính sách
    H->>A: Kết quả xác thực và dữ liệu phiên
~~~

Đây là kiến trúc minh họa cho module PAM; các thông điệp cụ thể phụ thuộc sản phẩm triển khai.

Những ràng buộc cần có ở biên dịch vụ ký:

- Xác thực người yêu cầu và mức bảo đảm phiên đăng nhập.
- Kiểm tra quyền hiện tại thay vì chỉ dựa vào việc người đó từng được cấp trước đây.
- Ràng buộc public key với yêu cầu và kiểm tra bằng chứng giữ khóa khi đăng ký.
- Ánh xạ tài nguyên được yêu cầu thành principal nằm trong allowlist.
- Áp giới hạn thời gian tối đa ở phía server.
- Gán serial duy nhất trong phạm vi CA và ghi lại fingerprint của CA.
- Ghi nhận người phê duyệt hoặc policy tự động đã ra quyết định.
- Từ chối yêu cầu thiếu dữ liệu kiểm soát bắt buộc.

MFA ở cổng cấp chứng chỉ chứng minh một bước xác thực khi cấp. Nó không có nghĩa mọi kết nối SSH tiếp theo đều hỏi MFA lại. Nếu cần xác thực mới cho từng phiên, chính sách và hạ tầng phải được thiết kế để đáp ứng yêu cầu đó.

## 6. Phòng lab: cấp user certificate ngắn hạn

### 6.1. Phân vai và điều kiện

Các lệnh trong phần này là hướng dẫn cho một lab Linux có OpenSSH, không phải lệnh cần chạy trên máy đang lưu bài học.

Dùng ba vai trò tách biệt:

| Nơi thực hiện | Dữ liệu giữ tại đó |
| --- | --- |
| Máy ký lab | Private User CA và public key cần ký |
| Máy trạm Alice | Private key Alice và certificate được cấp |
| Máy đích app01 | Public User CA và chính sách principal |

Tài khoản Linux `alice` trên app01 phải đã được cấp phát theo quy trình quản lý tài khoản. Certificate không tự tạo tài khoản. Bài lab không cấp sudo; nếu cần sudo cho một nhiệm vụ, phải thêm chính sách riêng có phạm vi tương ứng.

Kiểm tra phiên bản, tính năng hỗ trợ và cấu hình thực tế trên hệ điều hành đang dùng. Đường dẫn binary `sshd`, tên dịch vụ và vị trí log có thể khác giữa các bản phân phối.

### 6.2. Tạo CA riêng cho lab

Trên máy ký, trong một thư mục lab mới chưa có khóa cùng tên:

~~~bash
umask 077
ssh-keygen -t ed25519 -f ./user_ca_lab -C "pam-user-ca-lab"
ssh-keygen -lf ./user_ca_lab.pub
~~~

Nhập passphrase khi công cụ hỏi. Hai file được tạo có vai trò khác nhau:

- `user_ca_lab` là private key CA, chỉ ở máy ký.
- `user_ca_lab.pub` là public key CA, có thể phân phối đến máy đích.

Tạo riêng CA production qua quy trình bảo vệ khóa của tổ chức. Không lấy khóa lab để đưa vào môi trường thật. Việc dùng file private key trong ví dụ chỉ nhằm làm rõ cơ chế ký; hệ thống vận hành cần kiểm soát truy cập dịch vụ ký và phương tiện giữ khóa phù hợp.

### 6.3. Alice tạo khóa truy cập

Trên máy trạm Alice, chọn một tên file mới:

~~~bash
ssh-keygen -t ed25519 -f ~/.ssh/pam_alice_lab -C "alice-pam-lab"
ssh-keygen -lf ~/.ssh/pam_alice_lab.pub
~~~

Alice giữ `~/.ssh/pam_alice_lab` và gửi **chỉ public key** `pam_alice_lab.pub` đến kênh đăng ký đã xác thực. Trong lab, public key này được đặt tại `./requests/alice/pam_alice_lab.pub` trên máy ký.

Kênh đăng ký phải giữ được quan hệ giữa Alice, fingerprint public key và yêu cầu truy cập. Nếu kẻ khác thay public key trong lúc đăng ký, certificate có thể được cấp cho khóa không thuộc Alice dù mọi phép ký sau đó đều đúng.

### 6.4. Ký với principal và thời gian cụ thể

Trên máy ký:

~~~bash
ssh-keygen \
  -s ./user_ca_lab \
  -I 'subject=alice;role=prod-app-incident;ticket=INC-2041;request=req-7842' \
  -z 10001 \
  -n 'alice:prod-app-incident' \
  -V '-1m:+30m' \
  -O clear \
  -O permit-pty \
  -O source-address=192.0.2.25/32 \
  ./requests/alice/pam_alice_lab.pub

ssh-keygen -L -f ./requests/alice/pam_alice_lab-cert.pub
~~~

Trong ví dụ, chứng chỉ bắt đầu sớm hơn thời điểm ký một phút và hết hạn sau thời điểm ký 30 phút. Khoảng lùi đầu kỳ chỉ là dung sai nhỏ cho lab; thời gian thực tế phải do chính sách quy định và các hệ thống phải đồng bộ đồng hồ.

`192.0.2.25` đại diện cho nguồn kết nối mà app01 thực sự nhìn thấy. Nếu đi qua bastion hoặc NAT, địa chỉ đó có thể khác IP máy Alice. Không sao chép nguyên địa chỉ minh họa rồi kỳ vọng kết nối hoạt động.

Nhóm tùy chọn `-O` trong ví dụ bỏ các quyền mở rộng mặc định rồi cho phép PTY; giới hạn địa chỉ nguồn được đặt riêng. Không có tùy chọn force-command nên certificate này vẫn có thể dẫn đến shell của tài khoản đích nếu máy chủ cho phép. Ý nghĩa các cờ ký và cách xem certificate được mô tả trong [ssh-keygen](https://man.openbsd.org/ssh-keygen).

Kết quả là `pam_alice_lab-cert.pub`. Chuyển certificate này về máy Alice qua kênh quản lý. Không chuyển private key CA hoặc private key Alice giữa các vai trò.

### 6.5. Cấu hình tin cậy trên app01

Phân phối `user_ca_lab.pub` tới app01 bằng kênh cấu hình đã xác thực. Trước khi cài, so sánh fingerprint với giá trị lấy từ nguồn quản lý độc lập.

Ví dụ, file đã nhận nằm ở `/tmp/user_ca_lab.pub`:

~~~bash
ssh-keygen -lf /tmp/user_ca_lab.pub

sudo install -o root -g root -m 0644 \
  /tmp/user_ca_lab.pub /etc/ssh/pam_user_ca.pub

sudo install -d -o root -g root -m 0755 \
  /etc/ssh/auth_principals
~~~

Tạo file `/etc/ssh/auth_principals/alice` bằng công cụ quản lý cấu hình hoặc trình soạn thảo được phép. Nội dung đúng một principal:

~~~text
alice:prod-app-incident
~~~

File này và thư mục chứa phải thuộc root, không cho Alice sửa. Một tài khoản tự thêm principal cho chính nó sẽ phá vỡ ranh giới giữa người sử dụng quyền và người cấp quyền.

Trong cấu hình `sshd` của máy đích lab, đặt ở phạm vi global phù hợp:

~~~text
PubkeyAuthentication yes
TrustedUserCAKeys /etc/ssh/pam_user_ca.pub
AuthorizedPrincipalsFile /etc/ssh/auth_principals/%u
PermitRootLogin no
LogLevel VERBOSE
~~~

Các dòng trên minh họa điểm cấu hình, không phải toàn bộ một file `sshd_config` hoàn chỉnh. Kiểm tra các `Include`, giá trị đã có và khối `Match` để biết cấu hình nào thực sự được áp dụng. Với nhiều tùy chọn, việc thêm một dòng ở cuối không thay thế giá trị đã được đọc trước đó.

Sau khi cấu hình:

~~~bash
sudo /usr/sbin/sshd -t

sudo /usr/sbin/sshd -T \
  -C user=alice,host=alice-client.example.internal,addr=192.0.2.25
~~~

Chỉ reload dịch vụ sau khi kiểm tra thành công, theo tên dịch vụ của hệ điều hành. Giữ một phiên quản trị hợp lệ và đường phục hồi đã thử trong lúc thay đổi cơ chế xác thực.

Cấu hình này chưa tắt mọi đường xác thực khác. Khi chuyển sang mô hình chỉ dùng certificate, cần đánh giá `AuthorizedKeysFile`, `AuthorizedKeysCommand`, mật khẩu, keyboard-interactive, các phương thức khác và ngoại lệ liên quan. Ví dụ `AuthorizedKeysFile none` chỉ xử lý một nguồn raw public key, không chứng minh toàn bộ hệ thống đã chuyển sang certificate.

### 6.6. Alice thử kết nối

Trên máy Alice, đặt certificate đã nhận tại `~/.ssh/pam_alice_lab-cert.pub` rồi kiểm tra:

~~~bash
ssh-keygen -L -f ~/.ssh/pam_alice_lab-cert.pub

ssh \
  -i ~/.ssh/pam_alice_lab \
  -o CertificateFile=~/.ssh/pam_alice_lab-cert.pub \
  -o IdentitiesOnly=yes \
  alice@app01.prod.example.internal
~~~

Client vẫn phải xác thực host. Trong lab, dùng một host key đã xác minh hoặc triển khai Host CA theo phần tiếp theo. Không bỏ kiểm tra danh tính máy chủ để giải quyết lỗi đăng nhập.

Sau kết nối, đối chiếu log xác thực trên app01 với bản ghi cấp chứng chỉ. Một kết nối thành công chỉ chứng minh bài kiểm tra đó thành công; chưa chứng minh các đường truy cập ngoài chính sách đã bị chặn.

## 7. Bổ sung Host CA

### 7.1. Đăng ký public host key

Tạo một cặp khóa CA riêng cho host trên máy ký Host CA. Trên app01, lấy public key tương ứng với host key đang dùng; không đưa private host key ra khỏi máy chỉ để xin ký.

Trong ví dụ, public host key đã được chuyển đến máy ký tại `./requests/app01/ssh_host_ed25519_key.pub`. Quy trình cấp phải xác thực app01 và quyền sử dụng hostname trước khi ký.

~~~bash
ssh-keygen \
  -s ./host_ca_lab \
  -I 'host=app01.prod.example.internal;request=host-enroll-51' \
  -h \
  -z 20001 \
  -n app01.prod.example.internal \
  -V '-1m:+24h' \
  ./requests/app01/ssh_host_ed25519_key.pub
~~~

`host_ca_lab` là khóa CA riêng đã được tạo và bảo vệ trước đó. Hạn 24 giờ chỉ là lựa chọn minh họa; chu kỳ gia hạn host phải tính cả khả năng phục hồi khi dịch vụ ký gián đoạn.

Phân phối certificate về app01 và cấu hình cặp tương ứng:

~~~text
HostKey /etc/ssh/ssh_host_ed25519_key
HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub
~~~

Kiểm tra cấu hình và reload có kiểm soát như khi cấu hình user certificate.

### 7.2. Phân phối điểm tin cậy cho client

Trên máy Alice, file known_hosts được quản lý có thể chứa một dòng dạng:

~~~text
@cert-authority app01.prod.example.internal ssh-ed25519 <BASE64_PUBLIC_HOST_CA> host-ca-lab
~~~

Thay `<BASE64_PUBLIC_HOST_CA>` bằng phần public key thực của **Host CA**, không phải public host key của app01. Placeholder trên không phải dòng cấu hình có thể dùng trực tiếp.

Marker `@cert-authority` biểu thị CA được tin để kiểm tra host certificate trong phạm vi tên được khai báo. [Định dạng known_hosts của OpenSSH](https://man.openbsd.org/sshd#SSH_KNOWN_HOSTS_FILE_FORMAT).

Có thể quản lý tập tin riêng và cấu hình client cho lab:

~~~text
Host app01.prod.example.internal
    StrictHostKeyChecking yes
    UserKnownHostsFile ~/.ssh/known_hosts_pam_lab
~~~

Cần hiểu cả file tin cậy riêng lẫn file tin cậy toàn hệ thống mà client sử dụng. Nếu vẫn có raw host key hợp lệ được tin qua đường khác, một lần kết nối thành công không nhất thiết chứng minh host certificate đã được dùng; xem thông tin chẩn đoán của client để xác nhận.

Khi kết nối bằng alias, IP hoặc cổng khác, phải kiểm tra cách client xác định tên host và đối chiếu certificate. Không giải quyết sai tên bằng cách tắt kiểm tra host. Trong triển khai quy mô lớn, tránh mở rộng mẫu tin cậy đến mọi hostname nếu nhu cầu chỉ là một nhóm máy nhỏ.

## 8. JIT không đồng nghĩa với chấm dứt phiên đúng hạn

Certificate ngắn hạn giới hạn cửa sổ có thể dùng để xác thực. Nó không tự bảo đảm một phiên đã mở sẽ bị ngắt ngay khi hết hạn.

Ví dụ:

~~~text
10:00  Certificate được cấp, hết hạn 10:30.
10:25  Alice mở phiên SSH thành công.
10:30  Certificate hết hạn.
10:40  Phiên đã mở có thể vẫn tiếp tục nếu không có kiểm soát khác.
~~~

Nếu yêu cầu nghiệp vụ là “chỉ được thao tác đến 10:30”, hệ thống phải bổ sung kiểm soát vòng đời phiên: giới hạn thời lượng tại gateway, quản lý phiên tập trung hoặc cơ chế chấm dứt phù hợp với môi trường.

Tương tự, xóa quyền tại IdP và dừng cấp chứng chỉ mới không nhất thiết vô hiệu hóa certificate còn hạn đã được phát. Thiết kế JIT cần mô tả riêng ba thời điểm:

1. Khi nào không được xin quyền mới nữa.
2. Khi nào credential đã cấp không còn được chấp nhận cho kết nối mới.
3. Khi nào phiên hiện hữu thực sự kết thúc.

Có thể biểu diễn chính sách mong muốn như sau:

~~~text
valid_before = min(
    thời điểm cấp + TTL tối đa của vai trò,
    thời điểm kết thúc phê duyệt,
    thời điểm kết thúc ca hoặc hợp đồng
)
~~~

Công thức này là ví dụ thiết kế chính sách của dịch vụ ký, không phải cú pháp cấu hình OpenSSH.

Với kết nối multiplexing, một kết nối SSH còn tồn tại cũng cần được tính vào mô hình phiên. Muốn kiểm thử việc hết hạn hoặc thu hồi, hãy tạo kết nối độc lập thay vì vô tình dùng lại kết nối đã xác thực trước đó.

## 9. Thu hồi và ứng phó sự cố

### 9.1. Chọn đúng đối tượng thu hồi

| Sự kiện | Hướng xử lý cần đánh giá |
| --- | --- |
| Cấp sai một certificate | Thu hồi certificate đó và sửa nguyên nhân cấp sai |
| Lộ private key người dùng | Thu hồi khóa, xử lý certificate liên quan và đăng ký khóa mới |
| Lộ private host key | Thay host key, cấp lại certificate, cập nhật thu hồi phía client |
| Lộ private key CA | Loại CA khỏi điểm tin cậy hoặc thu hồi CA theo thiết kế, thay khóa và điều tra |
| Người dùng bị chấm dứt quyền | Dừng cấp mới, xử lý credential còn hạn và phiên hiện hữu |

Không coi thu hồi một serial là tương đương thu hồi mọi certificate được cấp cho cùng public key. Phải chọn phạm vi phù hợp với sự cố.

### 9.2. Minh họa KRL cho user certificate

OpenSSH hỗ trợ Key Revocation List (KRL). Ví dụ dưới đây tạo một KRL lab mới chứa certificate cần thu hồi, tại máy quản lý thu hồi:

~~~bash
ssh-keygen -k \
  -f ./user-revoked-lab.krl \
  ./requests/alice/pam_alice_lab-cert.pub

ssh-keygen -Q \
  -f ./user-revoked-lab.krl \
  ./requests/alice/pam_alice_lab-cert.pub
~~~

Truy vấn có thể trả mã khác không khi certificate bị thu hồi hoặc có lỗi; phải đọc kết quả cụ thể, không gom mọi mã khác không thành “thu hồi thành công”. Để bổ sung vào KRL hiện hữu, dùng chế độ cập nhật `-u` thay vì tạo lại và làm mất các mục cũ. [Quản lý KRL bằng ssh-keygen](https://man.openbsd.org/ssh-keygen#KEY_REVOCATION_LISTS).

Phân phối KRL đã kiểm tra đến máy đích trước khi tham chiếu nó trong cấu hình:

~~~text
RevokedKeys /etc/ssh/user-revoked.krl
~~~

KRL không tự đi đến các máy. Pipeline phân phối cần biết phiên bản mong muốn, máy nào đã nhận, máy nào lỗi và độ trễ cập nhật. Một máy lâu không đồng bộ có thể vẫn chấp nhận credential mà nơi khác đã thu hồi.

Nếu file `RevokedKeys` không đọc được, OpenSSH có thể từ chối xác thực bằng public key. Cần kiểm tra quyền file và cách triển khai trước khi bật cấu hình này trên diện rộng. [Tùy chọn RevokedKeys](https://man.openbsd.org/sshd_config#RevokedKeys).

Thu hồi user certificate tại `sshd` không thay thế cơ chế thu hồi host certificate ở client. Mỗi chiều xác thực có nơi kiểm tra riêng.

### 9.3. Xử lý khi CA bị nghi lộ

Quy trình ứng phó nên có sẵn:

1. Chặn yêu cầu ký mới và cô lập thành phần có liên quan.
2. Xác định CA fingerprint, miền tin cậy và khoảng thời gian có thể bị ảnh hưởng.
3. Triển khai thay đổi trust store hoặc thông tin thu hồi đến bên xác minh.
4. Cấp lại credential bằng CA sạch cho những đối tượng được xác minh lại.
5. Xử lý phiên đang hoạt động theo mức độ sự cố.
6. Đối chiếu nhật ký ký với certificate thực tế được quan sát.
7. Lưu bằng chứng, khôi phục dịch vụ và sửa nguyên nhân.

Nếu kẻ tấn công đã lấy được private key CA, chỉ dừng dịch vụ ký hợp lệ là chưa đủ: khóa bị lấy vẫn có thể được dùng để ký ở nơi khác. Phản ứng phải tác động đến điểm tin cậy ở phía xác minh.

## 10. Bảo vệ dịch vụ ký và xoay CA

### 10.1. Phân tách khả năng vận hành và khả năng cấp quyền

Tài khoản vận hành máy ký không nên mặc nhiên được tự cấp mọi principal. Cần tách các quyền:

- Sửa chính sách cấp chứng chỉ.
- Phê duyệt yêu cầu đặc quyền.
- Gọi API ký trong phạm vi được giao.
- Quản lý khóa CA hoặc thiết bị giữ khóa.
- Đọc nhật ký và bằng chứng.
- Phân phối CA public key, principal policy và KRL.

Phương tiện giữ khóa như HSM hoặc cơ chế ký phần cứng có thể giảm khả năng xuất private key. Tuy nhiên, nếu ứng dụng bị chiếm và vẫn có quyền yêu cầu ký tùy ý, kẻ tấn công có thể lạm dụng quyền ký mà không cần xuất khóa. Chính sách và việc bảo vệ API vẫn cần thiết.

Tổ chức cũng phải có phương án backup hoặc khôi phục khóa được kiểm soát. Backup CA có khả năng ký là một tài sản đặc quyền, không phải bản sao vô hại.

### 10.2. Xoay khóa có khoảng chuyển tiếp hữu hạn

Một kế hoạch xoay CA thông thường gồm:

1. Tạo CA mới và xác minh fingerprint qua quy trình quản lý.
2. Phân phối public key mới vào tập tin cậy của đúng miền.
3. Xác nhận độ phủ và kiểm thử bằng certificate mới.
4. Chuyển dịch vụ ký sang CA mới.
5. Chờ certificate cũ hết hạn hoặc xử lý thu hồi theo yêu cầu.
6. Gỡ CA cũ và xác minh không còn điểm tin cậy ngoài dự kiến.

Khoảng chồng lấn làm giảm nguy cơ gián đoạn nhưng đồng thời duy trì hai điểm tin cậy. Phải có người chịu trách nhiệm và hạn gỡ CA cũ. Khi CA cũ bị lộ, không áp dụng máy móc lịch chuyển tiếp của một lần xoay khóa thông thường.

## 11. Nhật ký và bằng chứng kiểm toán

Bằng chứng cần nối được quyết định cấp quyền với hoạt động xác thực và phiên thao tác.

| Nguồn | Dữ liệu nên ghi nhận | Câu hỏi được trả lời |
| --- | --- | --- |
| Cổng PAM/IdP | Danh tính, mức xác thực, request ID | Ai đã yêu cầu? |
| Bộ quyết định quyền | Vai trò, tài nguyên, phê duyệt, phiên bản policy | Vì sao yêu cầu được cho phép? |
| Dịch vụ ký | CA fingerprint, serial, key ID, public key fingerprint, principal, hạn dùng | Credential nào đã được cấp? |
| Máy đích/gateway | Host, tài khoản đích, nguồn kết nối, kết quả xác thực, dữ liệu certificate có sẵn | Credential đã được dùng ở đâu? |
| Hệ thống quản lý phiên | Session ID, thời điểm bắt đầu/kết thúc, bản ghi thao tác theo chính sách | Phiên đã làm gì và kéo dài bao lâu? |
| Pipeline cấu hình | Phiên bản trust store, KRL, principal policy, kết quả triển khai | Quyết định chặn đã đến máy nào? |

Định dạng và độ chi tiết log của máy đích thay đổi theo phiên bản, mức log và bản phân phối. Không giả định chỉ đặt `LogLevel VERBOSE` là đã có session recording hoặc đầy đủ mọi trường trong bảng. Cần thử một kết nối thực tế và xem dữ liệu được ghi nhận.

Trong kho bằng chứng, định danh certificate nên gắn với **CA fingerprint và serial**, không chỉ serial riêng lẻ. Key ID có thể lặp do lỗi vận hành hoặc quy ước; request ID phải được kiểm soát để có thể đối chiếu.

Không ghi private key hay passphrase vào log. Bản ghi terminal và lệnh cũng có thể chứa dữ liệu nhạy cảm, vì vậy quyền đọc, thời gian lưu và tính toàn vẹn của bằng chứng cần được quản lý.

## 12. Kiểm thử trước khi triển khai rộng

Một kế hoạch thử nghiệm phải gồm cả trường hợp được phép và bị từ chối. Các kiểm thử dưới đây là yêu cầu thực hành cho lab, chưa phải kết quả đã chạy.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Alice, CA đúng, principal đúng, thời gian đúng, nguồn đúng | Kết nối mới được chấp nhận |
| Certificate do CA không được tin ký | Bị từ chối |
| Principal khác principal được chấp nhận | Bị từ chối |
| Bob có role tương tự nhưng principal cá nhân khác | Không vào được tài khoản Alice |
| Certificate đã hết hạn hoặc chưa đến hạn | Kết nối mới bị từ chối |
| Nguồn kết nối không phù hợp điều kiện source-address | Bị từ chối |
| Certificate/khóa nằm trong KRL đã phân phối | Kết nối mới bị từ chối |
| Alice xin certificate cho tài nguyên ngoài quyền | Dịch vụ ký từ chối trước khi ký |
| Client gọi tên host không được chứng nhận | Không xác thực được host bằng certificate đó |
| Certificate hết hạn khi phiên đã mở | Quan sát và xác nhận cơ chế giới hạn phiên riêng |
| Đường raw key cũ vẫn còn | Phát hiện được để xử lý theo kế hoạch chuyển đổi |
| Một máy chưa nhận phiên bản KRL mới | Hệ thống phát hiện sai lệch và cảnh báo |

Với kiểm thử âm, cần bảo đảm client không âm thầm chuyển sang một phương thức xác thực khác rồi khiến kết quả trông như certificate vẫn hợp lệ. Với kiểm thử hết hạn và thu hồi, tạo kết nối SSH mới độc lập.

### Chẩn đoán có thứ tự

Khi gặp `Permission denied (publickey)`, lần lượt đối chiếu:

1. Client có trình đúng certificate cùng private key tương ứng không?
2. Có đang dùng nhầm identity trong agent hoặc kết nối tái sử dụng không?
3. CA fingerprint trên máy đích có đúng với CA ký không?
4. Loại certificate, hạn dùng và đồng hồ các máy có hợp lệ không?
5. Principal có phù hợp tài khoản đích và policy thực tế không?
6. Source-address có khớp nguồn mà server quan sát không?
7. KRL và các giới hạn tài khoản có chặn không?
8. Cấu hình hiệu lực của `sshd` có khác dự kiến do Include/Match không?

Dùng `ssh -vvv` cho một lần chẩn đoán cần thiết và log phía server để tìm bằng chứng. Dữ liệu chẩn đoán có thể chứa tên host, tài khoản và metadata nên phải được xử lý phù hợp trước khi chia sẻ.

## 13. Những ngộ nhận dễ dẫn đến cấp quyền quá rộng

### “Có certificate thì không cần quản lý authorized_keys nữa”

Certificate chỉ là một đường xác thực. Khóa cũ còn được tin có thể bỏ qua bước xin cấp mới. Kế hoạch chuyển đổi phải có thời hạn và bằng chứng loại bỏ hoặc phê duyệt ngoại lệ.

### “Principal ghi read-only thì tài khoản chỉ được đọc”

Tên principal là chuỗi định danh để đối chiếu. Muốn read-only cần kiểm soát thực tế tại tài khoản, filesystem, lệnh, sudo hoặc ứng dụng. Một shell có đủ quyền vẫn có thể làm nhiều hơn ý nghĩa tên principal.

### “Tắt forwarding là chặn được mọi đường chuyển tiếp dữ liệu”

Giới hạn forwarding của SSH làm giảm các khả năng do giao thức cung cấp, nhưng một người có shell và công cụ mạng vẫn có thể tạo cách chuyển tiếp khác. Cần xét cả quyền thực thi lệnh và chính sách mạng, không chỉ các extension trong certificate.

### “Certificate 15 phút nghĩa là quyền đặc biệt chỉ tồn tại 15 phút”

Một phiên đã mở, tiến trình nền hoặc quyền tồn tại trong hệ điều hành cần được xử lý riêng. Phải phân biệt hạn credential và hạn phiên.

### “CA không cấp mới nữa là mọi truy cập đã bị chặn”

Certificate còn hạn vẫn có thể được xác minh tại máy đích mà không gọi lại dịch vụ ký. Cần cơ chế thu hồi, cập nhật policy hoặc chấm dứt phiên tùy yêu cầu.

### “Ký host nào cũng được vì client đã tin CA”

Chính việc client tin CA làm cho sai sót cấp tên host nguy hiểm. Quy trình đăng ký host và phân vùng miền tin cậy là phần bắt buộc của thiết kế.

## 14. Bài tập vận dụng

Thiết kế luồng cấp quyền cho Alice để điều tra `app01.prod.example.internal` trong 30 phút theo ticket `INC-2041`. Không cấp quyền root trực tiếp và phải truy ngược được người yêu cầu.

Sản phẩm bài tập gồm:

1. Sơ đồ nơi giữ private key người dùng, User CA, Host CA và các public key được phân phối.
2. Quy tắc principal chứng minh Bob không thể dùng certificate của Bob để vào tài khoản Alice.
3. Chính sách xác định TTL, điều kiện cấp lại và hành vi khi cổng PAM ngừng hoạt động.
4. Mẫu bản ghi cấp chứng chỉ chứa CA fingerprint, serial, request ID và principal.
5. Kịch bản thu hồi khi máy Alice bị mất.
6. Kịch bản kết thúc phiên khi phê duyệt hết hạn.
7. Bằng chứng của ít nhất một kiểm thử thành công và ba kiểm thử bị từ chối.

Một đáp án tốt phải mô tả được cả lúc cấp quyền và lúc kết thúc quyền. Nếu chỉ trình bày lệnh ký certificate mà chưa xác định ai được ký, ai tin CA, principal được ánh xạ thế nào và cách kiểm tra thu hồi thì thiết kế PAM vẫn còn thiếu.

## 15. Điểm cần ghi nhớ

SSH CA giúp quản lý việc tin cậy và phát hành credential có hạn dùng ở quy mô lớn. Giá trị của nó trong PAM xuất hiện khi quyết định ký gắn với danh tính đã xác thực, phạm vi công việc, tài nguyên và bằng chứng phê duyệt.

User certificate xác thực người dùng; host certificate xác thực máy chủ. Private key CA là tài sản đặc quyền có phạm vi ảnh hưởng lớn. Principal và hạn dùng cần được kiểm soát ở dịch vụ ký rồi được thực thi cùng chính sách trên máy đích.

Một hệ thống hoàn chỉnh còn phải quản lý các đường truy cập cũ, giới hạn quyền sau đăng nhập, phân phối thu hồi, vòng đời phiên và dấu vết kiểm toán. Certificate hợp lệ là một điều kiện để truy cập, không phải bằng chứng rằng toàn bộ hoạt động sau đó đã đúng quyền.

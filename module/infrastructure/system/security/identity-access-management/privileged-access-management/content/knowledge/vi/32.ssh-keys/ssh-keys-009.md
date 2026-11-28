# Authorized keys review

## 1. Mục tiêu và phạm vi

Một public key nằm trong `authorized_keys` không chỉ là dữ liệu cấu hình. Nếu SSH server chấp nhận dòng đó, người giữ private key tương ứng có thể đăng nhập vào một tài khoản trên máy đích, với các giới hạn do dòng key và cấu hình server quyết định. Tài khoản đó có thể chạy ứng dụng, đọc dữ liệu nhạy cảm, dùng `sudo`, điều khiển agent hoặc chuyển tiếp kết nối đến hệ thống khác.

Trong quản lý truy cập đặc quyền — Privileged Access Management, hay PAM — authorized keys review là quá trình xác định **key nào đang cấp quyền cho ai, trên tài khoản nào, từ nguồn nào, với phạm vi gì và còn được phép tồn tại hay không**. Kết quả phải dẫn đến một quyết định có chủ sở hữu và bằng chứng, thay vì chỉ tạo danh sách fingerprint.

Sau bài này, bạn có thể:

- Xác định các nguồn mà OpenSSH thực sự dùng để cấp quyền public key.
- Đọc một dòng authorized key, phân biệt danh tính mật mã với comment và tùy chọn hạn chế.
- Đối chiếu key với owner, mục đích, mức đặc quyền, phê duyệt và vòng đời credential.
- Nhận diện key mồ côi, key dùng chung, quyền quá rộng và sai lệch giữa cấu hình quản lý với trạng thái thực tế.
- Thu hồi quyền theo quy trình có kiểm thử, tránh khóa đường quản trị hoặc làm gián đoạn service.
- Lưu bằng chứng đủ để phục vụ kiểm toán và ứng phó sự cố.

Bài tập trung vào quyền SSH phía server. Việc bảo vệ private key, vận hành SSH certificate authority và luân chuyển key là các hoạt động liên quan, nhưng mỗi hoạt động có tiêu chí riêng. Hoàn thành review một file không đồng nghĩa đã kiểm tra toàn bộ đường truy cập SSH.

## 2. Mô hình tư duy: key, tài khoản và quyền là ba đối tượng khác nhau

Giả sử máy chủ `app-prod-01` có tài khoản `deploy`. Trong file authorized keys có một key với fingerprint `SHA256:KEY_A`. Điều đó không tự chứng minh key thuộc về đội triển khai, dù comment ghi `deployment-team`.

Cần nối các quan hệ sau:

```text
Owner có trách nhiệm
        |
        v
Credential: public key / fingerprint
        |
        v
Nguồn cấp quyền SSH trên một máy
        |
        v
Tài khoản hệ điều hành
        |
        v
Quyền thực tế: file, service, sudo, container, mạng
```

Một người có thể sở hữu nhiều key. Một key có thể được cài trên nhiều host hoặc nhiều tài khoản. Một tài khoản dịch vụ có thể chấp nhận key của nhiều người. Vì vậy, đơn vị review không nên chỉ là “một key”, mà là một **quan hệ cấp quyền**:

```text
(host, tài khoản đích, nguồn cấp quyền, fingerprint, điều kiện sử dụng)
```

Ví dụ, cùng một fingerprint xuất hiện ở hai nơi:

| Quan hệ cấp quyền | Quyền phát sinh | Quyết định có thể khác nhau |
| --- | --- | --- |
| `lab-01 / student` | Thử nghiệm trong lab | Có thể được giữ theo chính sách lab |
| `prod-db-01 / root` | Quản trị trực tiếp cơ sở dữ liệu production | Cần kiểm soát chặt hoặc thay đường truy cập |

Dùng fingerprint để nhận diện vật liệu public key. Dùng hồ sơ cấp phát và bằng chứng kiểm soát credential để xác định owner. Dùng cấu hình hệ thống để xác định quyền thực tế. Không thay thế ba loại bằng chứng này bằng comment trong file.

## 3. Xác định đúng nguồn cấp quyền trước khi đọc key

### 3.1. Không giả định chỉ có một file mặc định

Đường dẫn quen thuộc là `~/.ssh/authorized_keys`, nhưng server có thể:

- Khai báo nhiều đường dẫn trong `AuthorizedKeysFile`.
- Dùng đường dẫn tập trung, ví dụ `/etc/ssh/authorized_keys/%u`.
- Có cấu hình khác nhau qua `Include` và `Match`.
- Lấy key từ chương trình khai báo bởi `AuthorizedKeysCommand`.
- Chấp nhận user certificate thông qua `TrustedUserCAKeys`.
- Dùng dòng có tùy chọn `cert-authority` trong authorized keys để tin cậy một CA cho tài khoản.
- Hạn chế certificate principal qua `AuthorizedPrincipalsFile`, `AuthorizedPrincipalsCommand` hoặc tùy chọn liên quan trên dòng CA.

Các cơ chế này không nhất thiết đồng thời hoạt động trên mọi máy. Người review cần xác định cơ chế hiện hành và phiên bản OpenSSH thực tế của hệ thống.

Ví dụ, nếu key đến từ một lệnh tra cứu thư mục danh tính, xóa key trong file local không chặn được nguồn tra cứu đó. Nếu người dùng còn có certificate hợp lệ từ một CA được tin cậy, việc gỡ public key thông thường cũng chưa đóng hết quyền của họ.

### 3.2. Kiểm tra cấu hình có hiệu lực

Trong môi trường Linux có OpenSSH, có thể dùng lệnh kiểm tra cấu hình. Các lệnh dưới đây là ví dụ; cần dùng đúng binary, đúng file cấu hình và đúng dịch vụ SSH đang vận hành.

```bash
# Kiểm tra cú pháp cấu hình của sshd.
sudo /usr/sbin/sshd -t

# Hiển thị cấu hình sau khi áp dụng điều kiện kết nối minh họa.
sudo /usr/sbin/sshd -T -C user=deploy,host=review-client.example,addr=192.0.2.25
```

Với `-C`, `user` là tài khoản đăng nhập, `addr` là địa chỉ client theo ngữ cảnh server xử lý, còn `host` là hostname của client dùng cho điều kiện cấu hình. Không điền hostname máy đích vào `host` chỉ vì đang kiểm tra máy đó. Nếu chính sách có `Match LocalAddress`, `LocalPort` hoặc các điều kiện khác, phải cung cấp ngữ cảnh tương ứng và kiểm tra các trường hợp thực sự có thể xảy ra.

Nếu daemon dùng file khác mặc định, thêm `-f` với đúng file đó. Nếu có nhiều SSH daemon, container hoặc cổng quản trị riêng, kiểm tra từng instance trong phạm vi.

Một lần chạy `sshd -T` không chứng minh mọi tài khoản, nguồn mạng và đường kết nối đều có cấu hình giống nhau. Đặc biệt, cần xét các điều kiện `Match` có thể làm thay đổi nơi lấy key hoặc chính sách đăng nhập.

Nhóm chỉ thị cần ghi nhận gồm:

| Nhóm | Ví dụ cần xem | Câu hỏi review |
| --- | --- | --- |
| Nguồn public key | `AuthorizedKeysFile`, `AuthorizedKeysCommand`, `AuthorizedKeysCommandUser` | Key được cung cấp từ đâu và ai kiểm soát nguồn đó? |
| Certificate | `TrustedUserCAKeys`, `AuthorizedPrincipalsFile`, `AuthorizedPrincipalsCommand` | CA và principal nào mở thêm đường truy cập? |
| Xác thực | `PubkeyAuthentication`, `AuthenticationMethods`, `PermitRootLogin` | Key đủ để đăng nhập hay còn điều kiện khác? |
| Giới hạn phiên | `ForceCommand`, `PermitTTY`, `AllowTcpForwarding`, `AllowAgentForwarding` | Sau xác thực, phiên được làm gì? |
| Bảo vệ đường dẫn | `StrictModes` và quyền sở hữu file, thư mục | Có ai ngoài chủ thể được phép có thể thay đổi quyền đăng nhập? |
| Thu hồi, thuật toán | `RevokedKeys`, `PubkeyAcceptedAlgorithms` | Credential bị thu hồi và thuật toán bị cấm được xử lý ra sao? |

Cấu hình xác thực nhiều bước cũng cần đọc đúng. Ví dụ, một key hợp lệ có thể mới hoàn thành một yếu tố trong `AuthenticationMethods`. Ngược lại, không được tự cho rằng mọi đăng nhập public key đều đã có MFA.

## 4. Đọc một dòng authorized key

### 4.1. Cấu trúc cơ bản

Một dòng thường có dạng:

```text
[options] key-type base64-public-key [comment]
```

Ví dụ hình thức:

```text
ssh-ed25519 <BASE64_PUBLIC_KEY> alice@managed-laptop
from="192.0.2.0/24",restrict ssh-ed25519 <BASE64_PUBLIC_KEY> ci-runner-17
```

Các chuỗi `<BASE64_PUBLIC_KEY>` là placeholder để giải thích cấu trúc, không phải key có thể cài vào hệ thống.

Một dòng có thể có nhiều option phân cách bằng dấu phẩy. Giá trị option có thể được đặt trong dấu nháy và chứa dấu cách. Vì vậy, tách dòng đơn giản bằng khoảng trắng rồi lấy “cột 1 là key type, cột 2 là key” sẽ sai với nhiều dòng hợp lệ.

Ví dụ:

```text
command="/usr/local/libexec/backup-receiver --target daily",restrict ssh-ed25519 <BASE64_PUBLIC_KEY> backup
```

Ở đây, phần trước key type có cả dấu cách bên trong giá trị `command`. Công cụ kiểm kê phải hiểu cú pháp authorized keys, hoặc dùng công cụ chuyên dụng để trích thông tin cần thiết.

### 4.2. Fingerprint không phải comment

Fingerprint là dấu vân tay tính từ public key. Với cùng vật liệu key, đổi comment không làm thay đổi fingerprint; nhưng fingerprint cũng không mang theo toàn bộ chính sách của dòng key.

Các tình huống cần phân biệt:

- Hai dòng cùng fingerprint nhưng comment khác nhau vẫn có thể là cùng một credential.
- Hai dòng cùng fingerprint nhưng option khác nhau có thể cấp các phạm vi truy cập khác nhau.
- Hai key có cùng comment nhưng fingerprint khác nhau là hai credential khác nhau.
- Comment ghi tên người đã nghỉ việc có thể là dấu hiệu đáng điều tra, nhưng chưa đủ kết luận key thuộc người đó.
- Comment ghi `vault-managed` không chứng minh private key đang được vault quản lý.

Dùng một định dạng fingerprint thống nhất, thường là SHA-256, trong báo cáo và hệ thống kiểm kê để tránh đối chiếu nhầm giữa các cách biểu diễn.

### 4.3. Các option quan trọng với PAM

| Option | Ý nghĩa cần hiểu khi review | Giới hạn hoặc bẫy thường gặp |
| --- | --- | --- |
| `from="..."` | Giới hạn nguồn được phép sử dụng key | Cần khớp nguồn server nhìn thấy; bastion, proxy hoặc NAT có thể làm nhiều client dùng chung một nguồn |
| `command="..."` | Ép chạy một command cho key | Wrapper vẫn có thể có lỗi; không tự động vô hiệu mọi forwarding hoặc mọi khả năng thoát khỏi lệnh |
| `restrict` | Bật một nhóm giới hạn như không PTY, không forwarding, không agent/X11 forwarding và không chạy user rc | Không tự cấm shell hoặc command thông thường; cần đánh giá cùng forced command và các option cho phép lại |
| `no-port-forwarding` | Cấm TCP forwarding cho key | Không phải firewall tổng quát; process có quyền chạy trên host vẫn có thể tự mở kết nối |
| `permitopen="host:port"` | Giới hạn đích mở qua local forwarding | Không nên diễn giải thành giới hạn toàn bộ kết nối mạng của tài khoản |
| `permitlisten="host:port"` | Giới hạn địa chỉ/cổng lắng nghe cho remote forwarding | Cần đọc cùng cấu hình server và phiên bản hỗ trợ |
| `no-agent-forwarding` | Không cho chuyển tiếp SSH agent | Không thay cho bảo vệ private key hoặc kiểm soát quyền chạy lệnh |
| `no-pty` | Không cấp pseudo-terminal | Không đồng nghĩa không chạy được lệnh hoặc không truy cập được dữ liệu |
| `expiry-time="..."` | Đặt thời điểm hết hạn theo cú pháp OpenSSH hỗ trợ | Cần xác nhận phiên bản, múi giờ/cách biểu diễn và đồng hồ; không tự chấm dứt phiên đã mở |
| `cert-authority` | Tin cậy key này như một CA cho xác thực certificate | Đây là quyền tin cậy nhiều credential được CA ký, không chỉ một key người dùng |
| `principals="..."` | Giới hạn principal khi dùng dòng CA tương ứng | Principal được ký và cơ chế ánh xạ tài khoản vẫn cần review |
| `environment="..."` | Yêu cầu thiết lập biến môi trường | Chỉ có hiệu lực theo chính sách server cho phép; biến môi trường có thể ảnh hưởng chương trình được chạy |

Không đánh giá một option độc lập. Quyền cuối cùng phụ thuộc tổ hợp dòng key, cấu hình server, loại credential và quyền của tài khoản đích.

Ví dụ `restrict,pty` không giống `restrict` đứng một mình trên phiên bản hỗ trợ việc cho phép lại PTY. Một reviewer chỉ tìm chuỗi `restrict` rồi gắn nhãn “an toàn” có thể bỏ sót quyền được mở lại.

### 4.4. Cùng key xuất hiện nhiều lần có thể làm suy yếu giới hạn

Giả sử một nguồn cấp quyền có hai dòng:

```text
from="192.0.2.20",restrict,command="/usr/local/libexec/deploy-wrapper" ssh-ed25519 <SAME_KEY> deploy-approved
ssh-ed25519 <SAME_KEY> old-migration
```

Không được coi dòng thứ nhất là chính sách chắc chắn áp dụng cho mọi lần dùng key. Dòng thứ hai có thể tạo một cách chấp nhận cùng credential với điều kiện rộng hơn. Cần kiểm tra hành vi thực tế của server với toàn bộ các nguồn và dòng phù hợp, rồi loại bỏ quan hệ cấp quyền dư thừa.

Nguyên tắc review là: **không dựa vào một bản ghi hạn chế để bỏ qua một bản ghi khác cấp quyền rộng**.

## 5. Những bằng chứng phải thu thập

### 5.1. Hồ sơ tối thiểu của một quan hệ cấp quyền

| Trường | Nội dung minh họa |
| --- | --- |
| Host và môi trường | `app-prod-01 / production` |
| Tài khoản đích | `deploy`, tài khoản dịch vụ |
| Nguồn cấp quyền | `/etc/ssh/authorized_keys/deploy`, do configuration management quản lý |
| Credential | Fingerprint SHA-256, loại key, độ dài nếu áp dụng |
| Phạm vi | Các option trên dòng key, forced command và giới hạn server có liên quan |
| Owner | Nhóm chịu trách nhiệm, người phê duyệt và đầu mối vận hành |
| Mục đích | Triển khai ứng dụng A từ runner được quản lý |
| Quyền tài khoản | File/service có thể tác động, quyền sudo hoặc quyền tương đương |
| Vòng đời | Ngày cấp, lần review, hạn sử dụng theo chính sách, kế hoạch rotate |
| Bằng chứng sử dụng | Sự kiện xác thực liên quan, phạm vi log và thời gian bao phủ |
| Quyết định | Giữ, thu hẹp, thay thế, thu hồi hoặc cần điều tra |
| Thực thi | Ticket thay đổi, kết quả kiểm thử và readback sau thay đổi |

Có thể bổ sung định danh máy bất biến, định danh credential trong vault và phiên bản chính sách. Khi host được tái tạo thường xuyên, chỉ dùng hostname có thể trộn dữ liệu của nhiều instance.

### 5.2. Trạng thái sử dụng không phải là lý do duy nhất để giữ key

Log cho thấy một key được dùng hôm qua chỉ chứng minh có một sự kiện sử dụng theo khả năng quan sát hiện có. Nó không chứng minh quyền đó được phê duyệt, người dùng còn hợp lệ hoặc mức quyền phù hợp.

Tương tự, không tìm thấy log không tự chứng minh key chưa từng dùng. Có thể do:

- Log rotation làm mất lịch sử cần kiểm tra.
- Cấu hình logging chưa ghi fingerprint ở mức thông tin đang thu thập.
- Log nằm trên hệ thống tập trung khác hoặc một SSH daemon khác.
- Chỉ thu log host đích, chưa nối với bastion hoặc hệ thống cấp quyền.
- Key phục vụ một tác vụ ít chạy nhưng vẫn có phụ thuộc thực tế.

Báo cáo nên ghi `không quan sát thấy trong cửa sổ 30 ngày, log bao phủ 26/30 ngày` thay vì ghi chắc chắn `không dùng 30 ngày` khi thiếu dữ liệu.

### 5.3. Không suy tuổi key từ mtime

Thời gian sửa file authorized keys có thể thay đổi khi configuration management triển khai lại, chỉnh comment hoặc đồng bộ file. Mtime của file không phải thời điểm tạo từng key, cũng không phải thời điểm private key được cấp.

Nếu không có dữ liệu cấp phát, đánh dấu `ngày cấp chưa xác định`, mở việc bổ sung bằng chứng và áp dụng chính sách xử lý credential thiếu hồ sơ. Không tạo ngày giả từ mtime để làm báo cáo trông đầy đủ.

## 6. Quy trình review từ đầu đến cuối

### Bước 1 — Chốt phạm vi và tiêu chí

Xác định nhóm host, tài khoản, môi trường, nguồn cấp quyền và thời điểm chụp dữ liệu. Ưu tiên tài khoản có khả năng:

- Đăng nhập root hoặc trở thành root.
- Thay đổi cấu hình sản xuất, secrets, agent hoặc service quan trọng.
- Quản trị hypervisor, container runtime, CI/CD runner hoặc thành phần IAM/PAM.
- Dùng forwarding để tiếp cận vùng mạng khác.
- Cấp hoặc sửa quyền SSH cho người khác.

Ghi rõ tiêu chí quyết định từ chính sách của tổ chức. Ví dụ: key không có owner phải được điều tra trong thời hạn cụ thể; quyền production cần phê duyệt hợp lệ; ngoại lệ phải có ngày hết hạn. Các mốc này là quyết định quản trị, không phải giá trị mặc định do OpenSSH cung cấp.

### Bước 2 — Chụp trạng thái thực tế và nguồn quản lý

Thu thập cấu hình hiệu lực, vị trí key, fingerprint, option và metadata đường dẫn. Đối chiếu với trạng thái mong muốn trong công cụ quản lý cấu hình hoặc kho dữ liệu cấp quyền đã được phép truy cập.

Phân biệt:

```text
Trạng thái mong muốn: cấu hình đã được duyệt trong nguồn quản lý
Trạng thái thực tế: cấu hình/file mà sshd trên host đang dùng
```

Sai lệch giữa hai bên có thể cho thấy thay đổi thủ công, triển khai chưa đồng bộ hoặc một nguồn cấp quyền chưa được quản lý. Nếu chỉ kiểm tra nguồn quản lý, có thể bỏ sót key được chèn trực tiếp trên host.

Chụp dữ liệu có dấu thời gian và định danh host. Nếu hệ thống thay đổi liên tục, nêu rõ review dựa trên snapshot nào; không trình bày kết quả snapshot như một cam kết giám sát liên tục.

### Bước 3 — Chuẩn hóa key và đường cấp quyền

Tạo một bản ghi cho mỗi quan hệ cấp quyền. Gom các dòng trùng fingerprint để phân tích, nhưng giữ nguyên thông tin host, tài khoản, nguồn và option của từng dòng.

Các trường hợp phải tách rõ:

- Public key cá nhân.
- Public key của workload/service.
- CA key trong nguồn tin cậy certificate.
- Dòng trùng credential với phạm vi khác nhau.
- Dòng không hợp lệ hoặc công cụ không phân tích được.

Dòng không phân tích được là finding cần xử lý, không nên âm thầm bỏ qua. Việc parser tự viết không đọc được một dòng cũng chưa chứng minh sshd từ chối dòng đó.

### Bước 4 — Đối chiếu owner, phê duyệt và phụ thuộc

Với từng bản ghi, trả lời:

1. Ai chịu trách nhiệm credential này?
2. Ai hoặc workload nào thực sự có quyền dùng private key?
3. Quyền trên tài khoản đích được cấp để làm gì?
4. Phê duyệt còn hiệu lực và đúng môi trường không?
5. Có thể đạt mục đích bằng quyền hẹp hơn hoặc thời hạn ngắn hơn không?
6. Quy trình rotate và thu hồi có bao phủ tất cả nơi cài key không?
7. Nếu gỡ hôm nay, tác vụ nào có thể bị gián đoạn?

Không gửi private key để “chứng minh owner”. Có thể đối chiếu với registry cấp phát, public key đã đăng ký, hồ sơ quản lý thiết bị hoặc bằng chứng kiểm soát key được thiết kế an toàn. Không yêu cầu ký một nội dung tùy ý nếu chưa hiểu mục đích và cách dùng chữ ký đó.

Đối với key dùng chung, owner của nhóm chỉ là đầu mối chịu trách nhiệm. Nó không khôi phục được khả năng quy trách nhiệm cho từng người đã dùng cùng private key.

### Bước 5 — Đánh giá quyền thực tế và rủi ro

Một key vào tài khoản `backup` có thể nguy hiểm hơn tên tài khoản gợi ý nếu tài khoản được sudo không giới hạn hoặc sửa được script chạy bởi root.

Cần xem ít nhất:

- Quyền hệ điều hành và quyền trên dữ liệu nhạy cảm.
- Quyền sửa service unit, cron, script, plugin hoặc thư mục được tiến trình đặc quyền nạp.
- Quyền sudo, nhóm quản trị hoặc khả năng quản lý container.
- Khả năng tự sửa nguồn authorized keys.
- Các giới hạn command, forwarding, nguồn mạng và thời gian.
- Cách phiên được ghi nhận trong bastion/PAM và khả năng liên kết đến actor.

Tài khoản dịch vụ có thể cần không có terminal tương tác, nhưng `no-pty` một mình chưa đáp ứng điều đó. Một key có forced command vẫn cần đánh giá wrapper, đối số, biến môi trường, file mà wrapper đọc và quyền ghi của tài khoản.

### Bước 6 — Ra quyết định và thực thi theo thay đổi được kiểm soát

Mỗi bản ghi cần một quyết định cụ thể:

| Quyết định | Khi áp dụng | Bằng chứng đóng việc |
| --- | --- | --- |
| Giữ | Có owner, nhu cầu hợp lệ và phạm vi phù hợp | Phê duyệt review và kỳ review tiếp theo |
| Thu hẹp | Nhu cầu còn nhưng quyền rộng | Option/chính sách mới và kiểm thử luồng được phép, bị cấm |
| Thay thế | Key dùng chung, mô hình cấp phát không đáp ứng chính sách | Credential mới hoặc cơ chế certificate/JIT đã hoạt động |
| Thu hồi | Hết nhu cầu, hết hiệu lực hoặc có nguy cơ | Đã gỡ khỏi mọi nguồn liên quan và kiểm thử từ chối xác thực mới |
| Điều tra | Thiếu owner, provenance hoặc có hành vi bất thường | Ticket có người xử lý, thời hạn và kiểm soát tạm thời |

Không dùng trạng thái “đã liên hệ owner” thay cho quyết định cuối cùng. Một review có thể có các finding chưa đóng, nhưng báo cáo phải chỉ rõ chúng vẫn còn mở.

### Bước 7 — Xác minh và lưu bằng chứng

Sau thay đổi, đọc lại nguồn quản lý và file/cấu hình có hiệu lực trên host. Kiểm tra lần xác thực mới qua đúng đường kết nối đã review.

Cần phân biệt:

- Public key còn được server chấp nhận hay không.
- Phiên mới còn thực hiện được hành động bị cấm hay không.
- Phiên cũ hoặc kết nối multiplex đã mở còn tồn tại hay không.
- Tự động hóa hợp lệ đã khôi phục hoạt động hay chưa.

Kết quả kiểm thử và quyết định đóng finding cần liên kết với ticket, thời gian và người thực hiện. Không chỉ ghi `done`.

## 7. Thu thập bằng chứng trên một host Linux

Các lệnh dưới đây minh họa thao tác kiểm tra trong môi trường được ủy quyền. Chúng không phải script quét tự động toàn bộ hạ tầng. Chọn tài khoản và đường dẫn từ cấu hình hiệu lực đã xác định.

### 7.1. Xác định tài khoản và đường dẫn

```bash
getent passwd deploy

# Dùng đường dẫn thật thu được từ cấu hình và hồ sơ tài khoản.
sudo stat /home/deploy /home/deploy/.ssh /home/deploy/.ssh/authorized_keys

# Trên hệ thống có namei, xem quyền của từng thành phần đường dẫn.
sudo namei -l /home/deploy/.ssh/authorized_keys
```

Không suy home directory bằng cách ghép `/home/` với username. Tài khoản hệ thống có thể có home ở nơi khác; môi trường directory service cũng có thể ánh xạ khác.

Với `AuthorizedKeysFile`, đường dẫn tương đối được diễn giải theo home của người dùng. Các token được hỗ trợ phải được giải đúng theo cấu hình và phiên bản. Không bỏ sót đường dẫn thứ hai chỉ vì đường dẫn đầu tiên trông đúng.

### 7.2. Trích fingerprint

```bash
sudo ssh-keygen -lf /home/deploy/.ssh/authorized_keys -E sha256
```

Lệnh giúp nhận diện fingerprint của các key mà công cụ đọc được. Giữ cả output lỗi và đối chiếu với các dòng cấu hình để phát hiện entry chưa phân tích được. Không lấy danh sách fingerprint làm bản sao hoàn chỉnh của chính sách: output fingerprint không thay thế việc xem option và nguồn cấp quyền.

Nếu file chứa CA trust hoặc certificate, cần ghi nhận loại bản ghi và phân tích đúng vai trò. Một CA fingerprint không tương đương một credential cá nhân.

### 7.3. Kiểm tra quyền sửa file

Với bố trí thông thường do người dùng quản lý, `.ssh` có mode `0700` và `authorized_keys` có mode `0600` là các giá trị phổ biến. Tuy nhiên, không nên áp một lệnh chmod/chown hàng loạt chỉ dựa trên ví dụ này.

File tập trung do root quản lý có thể có mô hình quyền khác, miễn đáp ứng yêu cầu đọc của sshd trong ngữ cảnh thực tế và không cho chủ thể không được phép sửa. Cần kiểm tra owner, group, ACL, symlink, thư mục cha và cơ chế quản lý file.

`StrictModes` hỗ trợ kiểm tra quyền sở hữu và mode liên quan trước khi chấp nhận đăng nhập, nhưng không chứng minh owner của key còn hợp lệ. Mode `0600` bảo vệ khả năng sửa/đọc file theo chính sách hệ điều hành; nó không giới hạn quyền mà key cấp sau xác thực.

Nếu tài khoản có thể sửa chính authorized keys của mình, một phiên SSH đã được cấp quyền rộng có thể cài thêm key để duy trì truy cập. Với tài khoản đặc quyền, cân nhắc nguồn key tập trung do một vai trò quản trị tách biệt kiểm soát.

### 7.4. Liên kết với log

Tìm sự kiện xác thực theo user, host, thời gian, nguồn kết nối và fingerprint nếu log cung cấp. Tên service systemd và vị trí log khác nhau giữa các hệ thống; không giả định mọi máy đều có cùng một file log.

Một bản ghi phân tích có thể biểu diễn như sau:

```text
host: app-prod-01
user: deploy
fingerprint: SHA256:KEY_A
source_seen_by_sshd: 192.0.2.20
window: 2026-10-01T00:00:00Z / 2026-10-31T23:59:59Z
observed_auth_events: 43
coverage: 31 days, no known collection gaps
correlation: CI job identity available in deployment audit system
```

Số sự kiện SSH không nhất thiết bằng số deployment, số command hoặc số người dùng. Kết nối được dùng lại có thể phục vụ nhiều tác vụ. Muốn quy trách nhiệm đến actor, cần liên kết với hệ thống PAM/bastion, CI/CD hoặc cơ chế danh tính workload phù hợp.

## 8. Forced command và các giới hạn cần kiểm thử

Một chính sách có thể muốn key của runner chỉ được triển khai đúng một ứng dụng:

```text
from="192.0.2.20",restrict,command="/usr/local/libexec/deploy-approved-app" ssh-ed25519 <RUNNER_PUBLIC_KEY> ci/app-a/prod
```

Đây là ví dụ thiết kế, chưa phải cấu hình sẵn dùng. Trước khi chấp nhận, cần xác minh:

- Runner kết nối từ đúng địa chỉ mà server nhìn thấy.
- Wrapper do vai trò tin cậy quản lý và tài khoản đích không sửa được.
- Wrapper không chuyển `SSH_ORIGINAL_COMMAND` vào `eval` hoặc shell không kiểm soát.
- Nếu wrapper có nhận đầu vào, nó phân tích và cho phép đúng tập hành động cần thiết.
- Đường dẫn binary, cấu hình và các file phụ thuộc không bị tài khoản đích thay thế.
- Không có dòng khác hoặc nguồn cấp quyền khác chấp nhận cùng key với quyền rộng.
- Hoạt động hợp lệ vẫn chạy được khi không có PTY và forwarding.
- Audit liên kết được phiên SSH với job/actor và kết quả triển khai.

`SSH_ORIGINAL_COMMAND` là đầu vào từ phía client, không phải quyết định phê duyệt đáng tin. Một wrapper ghi log chuỗi đó rồi thực thi nguyên văn không tạo ra giới hạn meaningful cho command.

Ma trận kiểm thử có thể gồm:

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Runner hợp lệ thực hiện deployment đã định nghĩa | Thành công, có audit |
| Dùng key từ nguồn ngoài phạm vi | Bị từ chối xác thực cho dòng này; đồng thời kiểm tra không có nguồn khác cho phép |
| Yêu cầu shell hoặc command tùy ý | Không có shell tùy ý; wrapper chỉ làm hành động được thiết kế |
| Yêu cầu local/remote forwarding | Không thiết lập được forwarding trái chính sách |
| Yêu cầu PTY hoặc agent forwarding | Bị từ chối theo giới hạn áp dụng |
| Tài khoản đích thử sửa wrapper hoặc nguồn cấp key tập trung | Không sửa được |
| Đường hợp lệ sau rotate credential | Hoạt động bằng credential mới, credential cũ không xác thực mới được |

Không diễn giải “client trả exit code khác 0” thành bằng chứng đầy đủ cho mọi giới hạn. Cần xem hành vi server, log xác thực và kết quả hành động cụ thể.

## 9. Thu hồi key an toàn và xử lý phiên còn sống

### 9.1. Chuẩn bị trước thay đổi

Trước khi thu hồi key dùng trong production:

1. Xác định đầy đủ nơi cài key và nguồn nào có thể cài lại.
2. Xác nhận credential hoặc đường quản trị thay thế đã được kiểm thử.
3. Xác nhận các job/service phụ thuộc đã chuyển đổi nếu đây là thay đổi có kế hoạch.
4. Ghi ticket, phạm vi, người thực hiện và tiêu chí thành công.
5. Có phương án truy cập khẩn cấp phù hợp; không duy trì một key mồ côi chỉ để làm “dự phòng”.

Nếu key nghi bị lộ, ưu tiên xử lý theo quy trình sự cố. Lịch thay đổi thông thường không được dùng làm lý do trì hoãn việc chặn một đường truy cập nguy hiểm đã được xác nhận. Hành động cụ thể phải nằm trong thẩm quyền ứng phó của tổ chức.

### 9.2. Thay đổi đúng nguồn

Nếu file do configuration management quản lý, sửa nguồn chuẩn và triển khai có kiểm soát. Chỉ sửa trên host có thể khiến key quay lại ở lần đồng bộ sau.

Nếu key đến từ `AuthorizedKeysCommand`, cập nhật nguồn dữ liệu thực sự cấp key. Nếu credential là certificate, cần xử lý trust, principal, thời hạn hoặc cơ chế thu hồi tương ứng; không coi việc gỡ một public key thông thường là đủ.

Với nghi ngờ credential bị lộ, rà soát cùng fingerprint trên những tài khoản và host khác trong phạm vi ứng phó. Cũng cần xét attacker có thể đã thêm credential mới hoặc sửa cấu hình trong thời gian truy cập.

### 9.3. Không mặc định phải restart SSH daemon

Với nguồn file authorized keys thông thường, nội dung được dùng khi xác thực mới; thay file không đồng nghĩa phải restart toàn bộ sshd. Nếu thay cấu hình daemon, thực hiện kiểm tra cú pháp và reload theo cơ chế của hệ thống, đồng thời giữ đường truy cập quản trị đã được kiểm chứng.

Nguồn key động có thể có cache ở dịch vụ hoặc lớp trung gian. Cần hiểu thời gian có hiệu lực và kiểm thử xác thực mới sau thay đổi thay vì suy luận từ thao tác cập nhật dữ liệu.

### 9.4. Xác thực mới khác phiên cũ

Gỡ key ngăn việc xác thực mới qua entry đã gỡ, nhưng không tự kết thúc một phiên SSH đã mở. Kết nối ControlMaster còn sống có thể tạo thêm channel mà không thực hiện lại public-key authentication.

Ví dụ kiểm thử trong môi trường cho phép, với đúng credential cũ:

```bash
ssh -F /dev/null -S none   -o ControlMaster=no   -o ControlPath=none   -o IdentitiesOnly=yes   -o IdentityAgent=none   -o PreferredAuthentications=publickey   -o PasswordAuthentication=no   -o KbdInteractiveAuthentication=no   -o BatchMode=yes   -i /secure-review-path/old_key   deploy@app-prod-01 true
```

Nếu môi trường cần jump host, port riêng hoặc cấu hình định tuyến khác, phải bổ sung tường minh đường kết nối thực tế; ví dụ trên không tự có các cấu hình đó. Luôn giữ kiểm tra host key theo chính sách. Không tắt kiểm tra danh tính server để làm phép thử thuận tiện hơn.

Cần kiểm soát cả certificate đi kèm và mọi identity bổ sung mà client có thể cung cấp. Xem log/debug thích hợp để xác nhận credential thực sự được thử. Nếu client chưa kết nối đến đúng server do lỗi mạng, kết quả thất bại chưa chứng minh key đã bị từ chối.

Chỉ dùng credential được phép sử dụng trong bài kiểm thử. Nếu không có private key cũ, không yêu cầu sao chép nó để lấy bằng chứng; dùng quy trình xác minh khác với dữ liệu hiệu lực, log server hoặc chủ thể đang kiểm soát credential theo thẩm quyền.

Trong sự cố, có thể cần kết thúc phiên, thu hồi credential khác, kiểm tra persistence và điều tra tác động. Đó là các quyết định riêng ngoài thao tác xóa dòng authorized key.

## 10. Các phát hiện thường gặp và cách xử lý

### 10.1. Key của người đã rời tổ chức

**Dấu hiệu:** hồ sơ key gắn với người đã offboard; entry còn trên tài khoản quản trị hoặc service.

**Kiểm tra:** đối chiếu fingerprint và lịch sử cấp phát, không chỉ comment. Xác định người khác có đang dùng chung private key không và quyền còn tồn tại trên các host khác không.

**Xử lý:** thu hồi quan hệ cấp quyền không còn hợp lệ; nếu key đã được chia sẻ, thay credential cho các luồng hợp lệ. Xem xét khoảng trống trong quy trình offboarding và bằng chứng sử dụng sau thời điểm kết thúc quyền.

### 10.2. Một key cá nhân dùng trên nhiều tài khoản đặc quyền

**Dấu hiệu:** cùng fingerprint xuất hiện ở `root`, `deploy`, `backup` trên nhiều vùng môi trường.

**Rủi ro:** lộ một private key mở nhiều đường truy cập; khó tách người dùng, workload và mục đích.

**Xử lý:** tách credential theo chủ thể và phạm vi, giảm quyền trực tiếp, áp dụng thời hạn/JIT hoặc certificate khi phù hợp. Tránh coi một lần rotate là đã xử lý xong mô hình cấp quyền rộng.

### 10.3. Key không có owner nhưng có sử dụng gần đây

**Dấu hiệu:** log có xác thực thành công; registry không có chủ sở hữu.

**Rủi ro:** đường truy cập hoạt động nhưng không có người chịu trách nhiệm.

**Xử lý:** điều tra qua nguồn mạng, job và lịch sử cấp phát; thiết lập kiểm soát tạm thời theo mức rủi ro. Đặt thời hạn xử lý rõ ràng. Hoạt động gần đây không phải phê duyệt ngầm.

### 10.4. Key bị giới hạn ở một dòng nhưng mở ở dòng khác

**Dấu hiệu:** fingerprint trùng, option không đồng nhất.

**Rủi ro:** reviewer nhìn dòng có `restrict` và bỏ sót đường rộng.

**Xử lý:** phân tích mọi quan hệ cấp quyền của credential, kiểm thử các ngữ cảnh kết nối và chuẩn hóa chính sách tại nguồn quản lý. Không tự động giữ “dòng đầu tiên” rồi xóa phần còn lại nếu chưa đánh giá phụ thuộc.

### 10.5. Authorized keys đúng nhưng quyền tài khoản quá rộng

**Dấu hiệu:** key có owner và hạn dùng, nhưng tài khoản sửa được script root hoặc quản lý container runtime.

**Rủi ro:** phạm vi quyền thực tế vượt mục đích được duyệt.

**Xử lý:** thu hẹp quyền hệ điều hành và đường thực thi, tách tài khoản hoặc dùng wrapper/command hạn chế được kiểm thử. Review key phải nối với least privilege của tài khoản đích.

### 10.6. Key được thêm lại sau khi thu hồi

**Dấu hiệu:** snapshot sau đồng bộ lại có fingerprint đã gỡ.

**Nguyên nhân có thể:** sửa sai nguồn, nhiều pipeline quản lý, cache chưa hết hiệu lực hoặc actor có quyền ghi file tự thêm lại.

**Xử lý:** xác định nguồn thực thi, sửa quyền quản lý và truy dấu thay đổi. Một lần readback ngay sau xóa chưa đủ nếu đã biết có nguồn tự động tái tạo.

## 11. Tình huống thực hành

Đội vận hành review tài khoản `deploy` trên 12 host production. Chính sách yêu cầu deployment đi qua runner được quản lý và mỗi credential có owner.

Bản kiểm kê có bốn nhóm:

| Nhóm | Bằng chứng | Phân tích ban đầu |
| --- | --- | --- |
| A | Key runner có owner, forced command; cùng key còn một dòng không option trên 2 host | Nhu cầu hợp lệ nhưng quyền không đồng nhất |
| B | Key mang comment tên nhân viên đã nghỉ; chưa đối chiếu registry | Cần xác minh danh tính credential và quy trình offboarding |
| C | Key backup không có owner; log thấy dùng mỗi tuần | Phụ thuộc hoạt động nhưng thiếu trách nhiệm quản trị |
| D | CA được tin cậy cho tài khoản; file principals có nhóm vận hành rộng | Có đường certificate ngoài các public key trực tiếp |

Một cách xử lý phù hợp:

1. Với A, xác định nguồn tạo dòng rộng, thu hẹp sau kiểm thử deployment và các hành vi bị cấm; kiểm tra cả 12 host.
2. Với B, đối chiếu fingerprint và hồ sơ cấp phát, rồi thu hồi nếu quyền thực sự hết hiệu lực. Kiểm tra sự kiện sử dụng sau ngày offboarding.
3. Với C, tìm workload và owner qua log, scheduler cùng hồ sơ hạ tầng. Đặt thời hạn xác minh và kế hoạch thay credential nếu là key dùng chung; không bỏ qua vì job đang chạy.
4. Với D, review principal, quyền cấp certificate, thời hạn và thu hồi. Không đánh dấu tài khoản hoàn tất chỉ vì các dòng public key trực tiếp đã sạch.

Kết quả không chỉ là bốn nhãn “giữ/xóa”. Báo cáo cần số quan hệ cấp quyền bị ảnh hưởng, thay đổi đã triển khai, kiểm thử, các finding còn mở và người chịu trách nhiệm.

## 12. Bằng chứng kiểm toán và chỉ số theo dõi

Một bộ bằng chứng nên đủ để người khác tái dựng quyết định:

- Phạm vi host/tài khoản/nguồn cấp quyền và thời gian snapshot.
- Fingerprint, loại credential, option và cấu hình hiệu lực có liên quan.
- Owner, mục đích, phê duyệt, ngoại lệ và thời hạn.
- Cửa sổ log, mức bao phủ và các giới hạn quan sát.
- Quyết định review cùng lý do cụ thể.
- Ticket thay đổi, trạng thái thực thi và kiểm thử.
- Finding chưa đóng, người xử lý và ngày đến hạn.

Public key không phải private key, nhưng comment, hostname, account và sơ đồ quyền vẫn có thể là dữ liệu nhạy cảm. Lưu bằng chứng trong hệ thống có kiểm soát truy cập và thời gian lưu phù hợp; không đưa private key, passphrase hoặc dữ liệu phiên không cần thiết vào báo cáo.

Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa | Điều cần tránh |
| --- | --- | --- |
| Tỷ lệ quan hệ cấp quyền có owner xác minh | Chất lượng kiểm kê và trách nhiệm | Tính comment như bằng chứng owner |
| Tỷ lệ quyền đặc quyền đã review đúng hạn | Mức bao phủ kiểm soát | Chỉ đếm số file đã mở |
| Số key mồ côi hoặc key dùng chung | Rủi ro thiếu quy trách nhiệm | Gộp mọi bản ghi cùng fingerprint rồi mất phạm vi |
| Thời gian từ quyết định thu hồi đến chặn xác thực mới | Hiệu quả thực thi | Đo từ lúc tạo ticket và giả định đã áp dụng |
| Tỷ lệ drift tái diễn | Chất lượng nguồn quản lý | Chỉ sửa host mà không xử lý nguồn |
| Finding còn mở quá hạn | Rủi ro chưa được xử lý | Gọi finding là hoàn tất khi mới gửi mail hỏi owner |

Mẫu số cần được định nghĩa. “100% key được review” có thể thiếu ý nghĩa nếu chỉ tính file mặc định, bỏ qua key động hoặc trust certificate.

## 13. Bài tập tự kiểm tra

### Bài tập 1 — Đọc phạm vi

Một key có `restrict`, không có `command`, đăng nhập vào tài khoản được phép chạy nhiều chương trình. Có thể kết luận key chỉ chạy một tác vụ cố định không?

**Gợi ý đáp án:** Không. `restrict` giới hạn một nhóm tính năng SSH nhưng không tự biến tài khoản thành một API chỉ thực hiện một tác vụ. Cần xét command, quyền tài khoản và khả năng thực thi thực tế.

### Bài tập 2 — Đối chiếu danh tính

Hai dòng có comment khác nhau nhưng cùng fingerprint; một dòng có `from`, dòng còn lại không có. Đơn vị review nên là một hay hai bản ghi?

**Gợi ý đáp án:** Giữ hai quan hệ cấp quyền để phân tích phạm vi, đồng thời liên kết chúng với cùng credential. Không lấy dòng hạn chế làm đại diện cho mọi lần dùng key.

### Bài tập 3 — Thu hồi chưa đủ

Sau khi xóa key local, user vẫn đăng nhập được. Nêu các giả thuyết cần kiểm tra trước khi kết luận OpenSSH bỏ qua thay đổi.

**Gợi ý đáp án:** Có file authorized keys khác, nguồn key động, certificate còn hợp lệ, key khác được agent/client cung cấp, cấu hình daemon khác, key bị đồng bộ trở lại hoặc kết nối cũ được multiplex. Kiểm tra đúng host và đúng đường kết nối nữa.

### Bài tập 4 — Bằng chứng sử dụng

Không có sự kiện fingerprint trong 90 ngày, nhưng log chỉ lưu 14 ngày và thiếu dữ liệu của bastion. Có đủ cơ sở ghi “key không dùng 90 ngày” không?

**Gợi ý đáp án:** Không. Phải ghi mức bao phủ thực tế và phần chưa xác định. Quyết định thu hồi cần bổ sung dữ liệu hoặc tuân theo chính sách xử lý credential thiếu bằng chứng.

### Bài tập 5 — Owner không đồng nghĩa người sử dụng

Một key thuộc nhóm platform được sáu người cùng giữ private key. Registry có owner hợp lệ. Vấn đề PAM nào vẫn tồn tại?

**Gợi ý đáp án:** Thiếu định danh actor riêng, khó quy trách nhiệm, khó thu hồi riêng một người và phạm vi lộ key rộng. Cần chuyển sang credential cá nhân/workload riêng hoặc cơ chế cấp quyền có danh tính và thời hạn phù hợp.

## 14. Tiêu chí hoàn tất một đợt review

Một đợt authorized keys review có thể được coi là hoàn tất về phạm vi đã xác định khi:

- Đã xác định các nguồn cấp quyền hiệu lực, bao gồm ngoại lệ và đường certificate liên quan.
- Mỗi quan hệ cấp quyền có owner hoặc finding xử lý rõ ràng.
- Đã đánh giá quyền tài khoản và giới hạn SSH theo nhu cầu được phê duyệt.
- Quyết định giữ, thu hẹp, thay thế hoặc thu hồi có lý do và bằng chứng.
- Thay đổi được đọc lại ở nguồn quản lý và trên hệ thống đích.
- Kiểm thử phân biệt xác thực mới, phiên cũ và hành động sau xác thực.
- Finding còn mở được nêu đúng trạng thái với người xử lý và thời hạn.
- Bằng chứng đủ để kiểm toán viên hiểu phạm vi, phương pháp và giới hạn kết luận.

Authorized keys review có giá trị khi biến một tập public key thành một bức tranh quyền truy cập có trách nhiệm, có thời hạn và có khả năng thu hồi. Mục tiêu của PAM là kiểm soát đường đi từ credential đến đặc quyền, bao gồm cả cách quyền được cấp, được sử dụng, được giám sát và được chấm dứt.

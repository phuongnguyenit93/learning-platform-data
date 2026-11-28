# Permission của key file: Bảo vệ khóa mật mã bằng quyền truy cập hệ điều hành

> **Chương:** Key storage  
> **Bài học:** Permission của key file  
> **Module:** `SECURITY_KEY_MANAGEMENT_FUNDAMENTALS` — học vòng đời khóa mật mã từ tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy; kết nối mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, IAM và kiểm toán để thiết kế hệ thống bảo vệ khóa an toàn.

## 1. Tình huống mở đầu: Private key đúng thuật toán vẫn có thể bị đọc trộm

Một dịch vụ Java chạy trên Linux dùng private key Ed25519 để ký sự kiện và một file PKCS#12 để thiết lập mTLS:

```text
/opt/billing/keys/signing-private.pem
/opt/billing/keys/identity.p12
```

Đội phát triển tạo hai file, sau đó chạy:

```bash
chmod 777 /opt/billing/keys/signing-private.pem
chmod -R 777 /opt/billing/keys
```

Họ làm vậy để giải quyết lỗi `Permission denied` khi service account không thể đọc file. Ứng dụng chạy được, nhưng **mọi tài khoản trên cùng host có thể đọc hoặc thay đổi private key**, tùy cơ chế hệ thống file và quyền thực tế. Nếu một workload ít đặc quyền bị chiếm quyền điều khiển, attacker có thể lấy khóa ký và giả mạo thông điệp.

Ngay cả khi file dùng RSA-3072 hoặc Ed25519, thuật toán đủ mạnh không bù đắp được việc **bí mật khóa bị lộ qua file permission**.

Một thay đổi tốt hơn không chỉ là:

```bash
chmod 600 signing-private.pem
```

mà cần trả lời:

- File thuộc **UID/GID** nào? Tiến trình Java chạy dưới danh tính nào?
- **Các thư mục cha** có cho phép tài khoản khác sửa, thay thế file hoặc đi qua đường dẫn không?
- Có **ACL mở rộng** ngoài các bit `rwx` không?
- Quyền trên **Linux, Windows, container, Kubernetes, NFS** có cùng nghĩa không?
- Ai có thể đọc file qua **backup, image layer, CI artifact, snapshot, log hoặc quyền root/admin**?
- Khi rotate key, file mới có được tạo **an toàn ngay từ đầu**, hay có thời điểm tạm mở quyền?
- Khi key compromised, có thể **thu hồi quyền, thay khóa và xử lý phiên/dữ liệu phụ thuộc** thế nào?

**Permission của key file** là các quyền và chính sách hệ điều hành/hệ thống lưu trữ xác định chủ thể nào được **đọc, thay đổi, truy cập đường dẫn hoặc quản lý file chứa vật liệu khóa**. Đây là một lớp thiết yếu của **key storage**, nhưng **không thay thế bảo vệ key material tại KMS/HSM, mã hóa khi lưu, IAM, bảo vệ runtime hay vận hành khóa đúng vòng đời**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu quyền POSIX `rwx`, UID/GID, `chmod`, `chown`, `umask`, ACL và sự khác biệt giữa quyền file với quyền thư mục.
2. Giải thích khi nào dùng `0600`, `0400`, `0640`, `0700`, `0750` và vì sao không dùng `0777` cho key secrets.
3. Phân biệt private key, public key, certificate, truststore, PKCS#12/JKS và secret được cấp qua file.
4. Thiết kế quyền đọc file phù hợp cho **service account** nhưng không cấp quyền dư cho user/process khác.
5. Hiểu giới hạn của NTFS ACL trên Windows, Kubernetes Secrets, Docker image và CI/CD.
6. Đọc ví dụ **Java 17 NIO** tạo file demo với POSIX permissions an toàn ngay lúc tạo, kiểm tra quyền và fail closed.
7. Phòng tránh symlink/path traversal, directory replacement, `umask` không phù hợp và race khi rotate file.
8. Gắn quyền file với KMS/HSM, DEK/KEK, key inventory, kiểm toán, ứng cứu và hủy khóa.
9. Viết checklist và kiểm thử để phát hiện file chứa khóa có quyền quá rộng.

---

## 2. Phân tích rủi ro: Ai đang cố đọc hoặc thay file khóa?

### 2.1. Các nhóm mối đe dọa

| Đối tượng | Khả năng | Ý nghĩa của file permission |
|---|---|---|
| **Tài khoản local khác** | Có thể thử mở file trên cùng host. | Quyền OS/ACL đúng có thể chặn đọc/ghi trái phép. |
| **Ứng dụng khác cùng UID** | Chia cùng identity với tiến trình giữ khóa. | `0600` **không tách biệt** hai tiến trình cùng UID. |
| **Process bị compromise** | Chạy code với quyền của service sở hữu file. | Nếu service cần đọc raw private key, attacker trong process có thể cũng đọc. |
| **Root/administrator/host owner** | Có quyền nâng cao hoặc kiểm soát hệ thống. | `chmod 600` **không ngăn tuyệt đối** root/admin hoặc kỹ thuật thu thập memory/disk. |
| **Attacker sửa được thư mục cha** | Có thể rename/thay thế entry, tạo symlink. | Quyền file tốt không đủ nếu đường dẫn không đáng tin. |
| **Attacker có bản backup/image** | Có thể truy cập bản sao ở nơi khác. | Permission trên bản gốc không tự áp lên artifact/backup. |
| **Attacker có quyền KMS/secret manager** | Lấy hoặc dùng khóa qua API được cấp. | Quyền file chỉ là một lớp; IAM và API policy vẫn bắt buộc. |
| **Attacker đọc log/crash dump** | Thấy raw key từng được ghi/giữ trong bộ nhớ. | `0600` trên key file không sửa lỗi lộ key ở log/dump. |

### 2.2. Phân biệt confidentiality, integrity và availability

File permission không chỉ phục vụ **bí mật**:

- **Confidentiality:** tài khoản không được phép không thể đọc private/secret key.
- **Integrity:** tài khoản không được phép không thể sửa hoặc thay file, tránh cấp một khóa giả, thay trust anchor hoặc đổi nội dung keystore.
- **Availability:** service được phép phải đọc được key, nhưng không để file bị xóa/rename trái phép hoặc permission drift gây downtime.

Ví dụ, attacker không cần lấy được private key nếu họ có thể **thay truststore** của một ứng dụng mTLS để thêm root CA không đáng tin. Vì vậy một số file chứa **public material** cũng cần bảo vệ **integrity**, dù không cần hạn chế đọc như private key.

### 2.3. File permission khác với cryptographic strength

```text
AES-256 key trong file mode 0666:
    Thuật toán có thể mạnh.
    Confidentiality của vật liệu khóa có thể bị phá ở tầng OS.

Ed25519 private key trong file mode 0600:
    OS giảm quyền đọc của user khác.
    Nhưng user sở hữu file hoặc process có quyền vẫn có thể lạm dụng.
```

**Đánh giá an toàn phải xem cả thuật toán, nguồn sinh, ranh giới lưu trữ, quyền file, IAM và vòng đời**, không chỉ một con số hoặc command `chmod`.

---

## 3. Mô hình quyền POSIX: User, group và others

Trên Linux/Unix, các file thường có bộ quyền:

```text
owner / group / others
    r      read
    w      write
    x      execute
```

Ví dụ:

```text
-rw-------  1 billing-svc billing-svc  1834 signing-private.pem
drwx------  2 billing-svc billing-svc  4096 keys
```

- `-` đầu chuỗi biểu thị file thường; `d` biểu thị thư mục.
- `rw-` đầu là quyền của owner.
- `---` tiếp theo là group.
- `---` cuối cùng là others.

### 3.1. Hệ bát phân (`chmod`)

Mỗi quyền có trọng số:

| Quyền | Giá trị bát phân |
|---|---:|
| Read (`r`) | 4 |
| Write (`w`) | 2 |
| Execute (`x`) | 1 |
| Không có quyền | 0 |

Cộng các bit trong từng nhóm:

| Mode | Dạng ký tự | Ngữ nghĩa với file thường |
|---|---|---|
| `0600` | `rw-------` | Owner đọc/ghi; group/others không đọc/ghi. |
| `0400` | `r--------` | Owner chỉ đọc; group/others không đọc/ghi. |
| `0640` | `rw-r-----` | Owner đọc/ghi; group đọc; others không có quyền. |
| `0440` | `r--r-----` | Owner và group đọc; không ai trong ba nhóm có quyền ghi qua mode bits. |
| `0644` | `rw-r--r--` | Mọi user có thể đọc; **không phù hợp với file chứa private key** trên host đa user. |
| `0666` | `rw-rw-rw-` | Mọi user có thể đọc và ghi; rất nguy hiểm với secret. |
| `0777` | `rwxrwxrwx` | Mọi user có quyền đọc/ghi/chạy; không dùng để “sửa lỗi Permission denied” cho key. |

Số `0600` thường viết có số `0` đầu để chỉ hệ bát phân trong ngữ cảnh code/Unix. Khi kiểm tra CLI, có thể hiển thị `600`.

### 3.2. File chứa private key nên để `0600` hay `0400`?

**Mẫu mặc định phổ biến:**

```bash
chmod 600 /path/to/signing-private.pem
```

Điều này phù hợp khi **một service account** cần đọc và có quy trình thay/ghi file theo chính account đó.

Nếu file chỉ cần đọc sau khi provision:

```bash
chmod 400 /path/to/signing-private.pem
```

`0400` làm giảm khả năng tiến trình owner vô ý sửa **nội dung file theo quyền file**. Nhưng:

- Nếu owner có quyền ghi thư mục chứa file, họ có thể thay/rename directory entry.
- Owner hoặc admin có thể đổi permission tùy OS/quyền.
- Một số tool cần ghi tạm hoặc rotate file; nên dùng owner khác với reader hoặc workflow có quyền phù hợp.
- **Read-only mode không phải WORM hay cơ chế chống sửa bởi root.**

Vì thế chọn `0400` không đồng nghĩa file trở nên bất biến tuyệt đối.

### 3.3. Public key và chứng thư có thể đọc công khai, nhưng không được sửa tùy ý

Một file public certificate:

```bash
chmod 644 /etc/myapp/certs/server.crt
```

có thể phù hợp vì certificate không chứa secret. Tuy nhiên directory/file phải được quản trị để không ai thay certificate tùy ý.

**Phân biệt:** public key được công bố ≠ public key đáng tin. Trust chain, fingerprint, PKI và kiểm soát nguồn vẫn cần thiết.

---

## 4. Permission của thư mục khác permission của file

### 4.1. `x` trên thư mục là quyền đi qua

Đối với directory:

- `r`: liệt kê tên entry trong thư mục (khi có quyền traversal phù hợp).
- `w`: tạo, xóa hoặc rename directory entries (thường kết hợp `x`).
- `x`: **traverse/search** qua thư mục để truy cập đường dẫn con.

Vì thế:

```text
file = 0600
directory = 0777
```

không phải cấu hình lý tưởng. Một user khác có thể không đọc được nội dung file theo mode bits, nhưng nếu directory cho phép ghi, họ có thể **thay directory entry, rename hoặc phá luồng cấp phát** trong một số trường hợp. Quyền sửa directory khác quyền sửa bytes bên trong file.

### 4.2. Mẫu thư mục riêng

```bash
chmod 700 /opt/billing/private-keys
chmod 600 /opt/billing/private-keys/signing-private.pem
```

`0700` = `rwx------`, chỉ owner có quyền liệt kê, thay entries và traverse vào thư mục theo POSIX bits.

**Cần kiểm tra owner của cả thư mục và file.** Nếu service chạy bằng `billing-svc` nhưng file thuộc `root` với mode `0600`, service thường không đọc được. Không giải quyết bằng `chmod 777`; hãy điều chỉnh ownership, group/ACL hoặc provisioning theo thiết kế.

### 4.3. Quyền của các thư mục cha

Đường dẫn:

```text
/opt/billing/private-keys/signing-private.pem
```

cần kiểm tra cả:

```text
/opt
/opt/billing
/opt/billing/private-keys
```

Các thư mục cha có thể cho user khác **đổi hoặc thay** tên thư mục đích nếu quyền ghi và cấu trúc cho phép. Một file mode `0600` không bảo vệ được khỏi **path substitution** nếu ứng dụng đi qua đường dẫn bị attacker kiểm soát.

Trên Linux có thể kiểm tra bằng lệnh `namei -l` (khi tool có sẵn) và công cụ đọc ACL. Không giả định công cụ này tồn tại trên mọi Unix.

### 4.4. Mẫu cho service đọc nhưng không được tự thay key

Một thiết kế chặt hơn:

```text
/opt/billing/keys/
    owner: root hoặc key-provisioner
    group: billing-key-readers
    directory: 0750

signing-private.pem:
    owner: root hoặc key-provisioner
    group: billing-key-readers
    file: 0440 hoặc 0640 theo workflow
```

Dịch vụ chỉ thuộc group được phép đọc. Một `0440` với **directory không ghi được bởi group** có thể giúp giới hạn khả năng sửa của service.

Nhưng group membership cấp quyền cho **mọi process trong group**. Cần kiểm tra những tài khoản nào cùng GID, quyền supplementary groups và các ACL khác. Không tạo một nhóm `all-services` đọc mọi private key.

### 4.5. Sticky bit không thay thế quyền thư mục an toàn

Thư mục như `/tmp` thường có sticky bit để hạn chế xóa/rename file người khác trong thư mục world-writable. Nhưng **đừng dùng `/tmp` làm nơi cất private key dài hạn** chỉ vì file có mode `0600` và `/tmp` có sticky bit.

Có thêm rủi ro symlink, path prediction, quá trình dọn tự động, mount configuration và metadata exposure. Dùng thư mục do provisioner sở hữu với quyền chặt chẽ.

---

## 5. UID, GID và danh tính tiến trình quyết định quyền thực tế

### 5.1. Quyền được xét theo credential của process

Một tiến trình Java không “là người sở hữu file” chỉ vì cấu hình có:

```text
service.name=billing
```

Kernel kiểm soát quyền dựa trên **UID/GID, supplementary groups, ACL, capabilities và các lớp bảo mật khác**.

Ví dụ:

```text
Java process UID: billing-svc
Key file owner:   root
Key file mode:    0600
```

Dịch vụ thường không có quyền đọc; với `0640`, nếu nhóm file là `billing-key-readers` và process thuộc group đó, nó có thể đọc theo group.

### 5.2. Cách kiểm tra trên Linux

Các lệnh minh họa sau chỉ **đọc metadata**, không in raw key:

```bash
id billing-svc
ls -ld /opt/billing/private-keys
ls -l /opt/billing/private-keys/signing-private.pem
stat -c '%a %U %G %n' /opt/billing/private-keys/signing-private.pem
```

Cú pháp `stat -c` là dạng phổ biến trên GNU/Linux, có thể khác trên macOS/BSD.

Để kiểm tra những người dùng khác có thể truy cập:

```bash
getfacl /opt/billing/private-keys/signing-private.pem
getfacl /opt/billing/private-keys
```

`getfacl` không nhất thiết được cài mặc định. Khi đánh giá sản xuất, cần bổ sung kết quả **actual access test** dưới principal bị cấm và principal được phép.

### 5.3. Không giải quyết lỗi permission bằng chạy service dưới root

Chạy mọi ứng dụng bằng root để đọc key:

```text
java service -> UID 0
```

làm tăng blast radius khi process bị compromise. Với các key files cần quyền cao, nên dùng provisioning/secret delivery tạo ownership và ACL phù hợp, hoặc chuyển thao tác mật mã vào KMS/HSM.

### 5.4. Một UID chung cho nhiều service là rủi ro

Nếu `orders-service` và `payments-service` chạy cùng UID:

```text
UID=1000 cho cả hai process
```

thì mode `0600` trên file do UID=1000 sở hữu **không ngăn tiến trình còn lại** đọc file đó, nếu đường dẫn và lớp bảo mật khác cho phép.

**Tách service identities** là điều kiện quan trọng. Trên hệ multi-tenant, file permissions chỉ là một phần; có thể cần tách container, host, namespace, MAC policy hoặc HSM/KMS riêng.

---

## 6. `umask`: Ngăn file bị tạo quá rộng ngay từ đầu

### 6.1. `chmod` sau khi tạo có thể quá muộn

Quy trình yếu:

```bash
write-private-key-to-file
chmod 600 private.key
```

Trong khoảng giữa hai bước, file có thể mang quyền mặc định rộng hơn cần thiết, tùy ứng dụng, `umask` và filesystem. Quy trình có thể bị ngắt trước `chmod`, để lại secret lộ.

**Ưu tiên tạo file với quyền mong muốn tại thời điểm tạo**.

### 6.2. Tính mode từ `umask`

Các mức khởi tạo thường dùng trong POSIX:

```text
File mới:      0666 & ~umask
Directory mới: 0777 & ~umask
```

Với:

```bash
umask 077
```

kết quả thông thường:

```text
regular file -> 0600
directory    -> 0700
```

Với `umask 027`:

```text
regular file -> 0640
directory    -> 0750
```

Đây là mô hình POSIX cơ bản. ACL mặc định, filesystem và API tạo file có thể ảnh hưởng kết quả; **phải kiểm tra quyền thực tế sau provision**.

### 6.3. `umask` có phạm vi process

Ví dụ cho shell provisioning:

```bash
umask 077
```

Giá trị này áp dụng cho shell và các child process kế thừa theo môi trường OS, không tự thay đổi permission của các file đã tồn tại và không phải policy cho mọi service trên host.

Trong systemd có thể có cấu hình `UMask=` ở unit tùy môi trường; nhưng cần kiểm tra kết quả thực tế, không giả định mọi tool đều tôn trọng như nhau.

### 6.4. Sử dụng temp files an toàn

Nên tạo temp file trong **thư mục riêng đáng tin cậy** với quyền giới hạn khi tạo. Tránh chuỗi tên đoán được như:

```text
/tmp/private-key-123.pem
```

và tránh việc ghi raw key vào stdout, command arguments hoặc log khi dựng file. Lưu ý một số công cụ tạo temp file an toàn có default permissions tốt hơn, nhưng vẫn phải kiểm chứng khi dùng trong workflow cấp secret.

---

## 7. POSIX ACL: Vì sao `ls -l` chưa đủ?

### 7.1. ACL mở rộng có thể cấp quyền cho user hoặc group cụ thể

Ngoài owner/group/others, một filesystem có thể hỗ trợ ACL:

```text
user::rw-
user:billing-svc:r--
group::---
mask::r--
other::---
```

Đây là ví dụ ACL để minh họa. Các bit `rwx` trên output `ls -l` có thể không cho biết hết danh sách principal có quyền.

Lệnh kiểm tra:

```bash
getfacl /opt/billing/private-keys/signing-private.pem
```

Không nên kết luận chỉ từ `chmod 600` nếu filesystem/ACL có quy tắc đặc biệt hoặc host policy khác cần xem.

### 7.2. ACL và effective permissions

POSIX ACL có **mask** giới hạn quyền hiệu lực đối với một số entry user/group được chỉ định. Vì vậy một ACL entry có `r--` chưa chắc thực sự đọc được nếu mask không cho phép.

Khi đánh giá:

1. Đọc ACL đầy đủ.
2. Kiểm tra owner/group thực tế.
3. Hiểu default ACL trên thư mục tạo file.
4. Test bằng tài khoản service được phép và tài khoản bị cấm.
5. Xem mount/NFS policy/SELinux khi phù hợp.

### 7.3. Khi nào dùng ACL thay vì group?

Nếu một service account được phép đọc riêng một key nhưng không muốn đưa nó vào group có nhiều key khác, ACL có thể giúp cấp quyền **theo đúng principal**. Tuy nhiên ACL làm tăng độ phức tạp của inventory, migration, backup và debugging.

Một lệnh Linux ví dụ khi người vận hành đã có approval:

```bash
setfacl -m u:billing-svc:r-- /opt/billing/private-keys/signing-private.pem
```

**Không áp dụng máy móc**: cần kiểm tra mask, directory traversal và quyền thay file. Mọi ví dụ thay đổi ACL cần triển khai trong test/staging trước khi dùng production.

### 7.4. Default ACL kế thừa

Một thư mục có default ACL có thể tạo ra file với các quyền khác so với kỳ vọng từ `umask`. Vì vậy không chỉ kiểm tra script đã gọi `umask 077`; **kiểm tra actual file permissions và ACL** sau key delivery/rotation.

---

## 8. Windows: NTFS ACL không phải `chmod 600`

### 8.1. Mô hình quyền Windows

Trên Windows, NTFS sử dụng **Access Control Lists (ACL)** với các Access Control Entries (ACE) cho user, group, service identity và hệ thống.

Các khái niệm cần kiểm tra:

- **Owner** của file.
- **DACL**: principal nào được Allow/Deny Read/Write/Modify/Full Control.
- **Inherited permissions** từ parent directory.
- **Service identity** như domain service account hoặc service SID.
- **Administrative/SYSTEM privileges** và khả năng nâng quyền.
- **EFS/BitLocker/DPAPI** nếu thiết kế có thêm encryption.

Không áp dụng `chmod 600` làm control chính trên NTFS rồi giả định có hiệu quả giống POSIX.

### 8.2. Nguyên tắc ACL cho private key file

Ví dụ directory:

```text
C:\ProgramData\Billing\Keys\signing-private.p8
```

Một chính sách có thể yêu cầu:

- `BillingService` chỉ **Read** key cần dùng.
- Key provisioner/administrator chuyên trách có quyền thay file theo workflow.
- `SYSTEM` và nhóm quản trị được xử lý theo policy hệ thống.
- Không để các nhóm rộng như `Everyone` hoặc `Users` có Read/Modify không cần thiết.
- Không để parent directory có quyền ghi/đổi ACL rộng.
- Có audit cho thay quyền hoặc thay nội dung key.

**Cấu hình ACL cụ thể phụ thuộc dịch vụ, domain, backup/EDR và cấu trúc host.** Đừng tự xóa ACE của SYSTEM hoặc Administrators chỉ vì muốn “tăng bảo mật”; có thể làm hỏng recovery/maintenance.

### 8.3. Kiểm tra thay vì đoán

PowerShell có thể đọc ACL:

```powershell
Get-Acl 'C:\ProgramData\Billing\Keys\signing-private.p8' |
    Format-List
```

Công cụ `icacls` cũng có thể hiển thị ACL:

```powershell
icacls 'C:\ProgramData\Billing\Keys\signing-private.p8'
```

Đây chỉ là lệnh kiểm tra metadata. Khi thay ACL, nên dùng mẫu đã được review, triển khai với account phù hợp và **kiểm thử service vẫn đọc được key trong khi tài khoản không được phép bị chặn**.

### 8.4. EFS, DPAPI và BitLocker không thay ACL

- **BitLocker** giúp bảo vệ dữ liệu trên ổ đĩa khi ổ không được mở khóa theo mô hình cụ thể.
- **EFS** có thể mã hóa file theo danh tính/chứng thư Windows.
- **DPAPI** hỗ trợ bảo vệ secret bằng cơ chế của nền tảng.
- **Windows Certificate Store/CNG KSP** có thể giữ private keys qua API/ACL của key container, thay vì một PEM file đơn giản.

Các công nghệ này **không thay thế** authorization, credential lifecycle và protection khi ứng dụng đang chạy. Đối với private key quan trọng, một key container/TPM/HSM-backed provider có thể phù hợp hơn tự lưu raw PEM.

### 8.5. macOS và BSD

Các hệ Unix khác có POSIX mode nhưng cú pháp `stat`, ACL, keychain và sandbox/mandatory controls có thể khác Linux. Trên macOS, **Keychain** hoặc cơ chế quản lý khóa nền tảng thường đáng cân nhắc hơn một private key file tự quản lý.

---

## 9. Phân loại file: Không phải file nào có chữ “key” cũng là secret

| File/vật liệu | Có bí mật không? | Quyền đọc thường hướng tới | Cần bảo vệ integrity? |
|---|---|---|---|
| Private key PEM/DER/PKCS#8 | **Có** | Service cần dùng và provisioner. | Có. |
| Symmetric AES/HMAC key raw | **Có** | Tối thiểu; ưu tiên KMS/HSM/secret manager. | Có. |
| PKCS#12 chứa private key | **Có** | Service/provisioner; thường kết hợp keystore password. | Có. |
| Public certificate `.crt` | Thường không | Có thể đọc rộng. | **Có**, tránh thay trust. |
| Public key `.pub` | Không chứa private secret | Có thể phân phối công khai. | Có, cần trust mapping. |
| Java truststore | Thường chứa CA/public cert, có thể có metadata khác | Có thể đọc bởi ứng dụng, chỉnh sửa rất hạn chế. | **Rất quan trọng**. |
| Java keystore | Tùy nội dung; có thể chứa private/secret key | Theo sensitive contents. | Có. |
| KMS key ID/alias | Không phải raw key | Theo access policy metadata. | Có, tránh confused deputy/nhầm đích. |
| Config chứa keystore password | **Có** | Chỉ process/provisioner cần. | Có. |
| Wrapped DEK | Được mã hóa/bọc, không phải raw key | Tùy threat model; vẫn cần metadata/AAD integrity. | Có. |
| SSH `authorized_keys` | Public keys được phép đăng nhập | Không nhất thiết bí mật, nhưng sửa file là rủi ro authentication. | **Có**. |

**Sai lầm:** lưu private key dưới đuôi `.txt` rồi coi không cần bảo vệ, hoặc coi `.p12` luôn an toàn chỉ vì có password.

### 9.1. Key file có thể chứa nhiều đối tượng

Một PKCS#12 keystore có thể chứa private key, certificate chain và các entry khác. Không suy ra file chỉ chứa public cert từ tên `truststore.p12` nếu chưa kiểm tra nội dung/semantics bằng cách an toàn.

### 9.2. Metadata cũng có thể nhạy cảm

Tên file như:

```text
/keys/tenant-personal-email@example.com/payment-master.pem
```

có thể tiết lộ PII và kiến trúc. Ưu tiên opaque IDs và registry metadata hạn chế quyền đọc. Không xem tên file hoặc key ID là một secret, nhưng vẫn quản lý privacy và tính toàn vẹn.

---

## 10. SSH: Quyền file ảnh hưởng trực tiếp đến authentication

### 10.1. Mẫu quyền phổ biến cho private key

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
```

Đây là những giá trị điển hình trên Unix cho một tài khoản cá nhân; OpenSSH còn có các yêu cầu kiểm tra quyền của các thư mục liên quan trong những cấu hình nhất định.

**Không dùng private SSH key trong repository, container image hoặc artifact công khai.** Nếu một SSH key đã bị commit rồi xóa khỏi Git working tree, bản sao trong history/artifact vẫn có thể tồn tại; cần revoke/rotate.

### 10.2. `authorized_keys` và integrity

File `~/.ssh/authorized_keys` lưu **public keys được phép** đăng nhập, không chứa private key, nhưng nếu attacker có quyền ghi vào file này, họ có thể thêm public key của họ để được cấp quyền theo cấu hình SSH server.

Do đó protection đối với `authorized_keys` tập trung vào **integrity**, directory ownership và policy authentication. `chmod 600` là cấu hình thường dùng, không phải cơ chế duy nhất.

### 10.3. SSH agent giảm nhu cầu copy raw private key

Một SSH agent có thể giữ private key/passphrase hoặc thao tác ký theo cấu trúc riêng, giúp ứng dụng không liên tục đọc một file raw key ở nhiều nơi. Tuy nhiên agent socket, forward agent và quyền sử dụng agent vẫn là bề mặt tấn công.

Không coi việc có agent là bằng chứng HSM-backed. Một agent có thể dùng software private key hoặc hardware token tùy cấu hình.

### 10.4. Host key và client identity khác nhau

- **Server host key** chứng thực máy chủ SSH; lộ private host key ảnh hưởng tin cậy server.
- **User/client private key** chứng thực một tài khoản/identity.
- **Public host key/known_hosts** cần kiểm soát integrity để tránh tin sai server.

Naming, ownership và rotation phải phân biệt rõ mục đích từng khóa.

---

## 11. Java TLS/mTLS: Keystore, truststore và file permission

### 11.1. Sơ đồ đọc keystore

```mermaid
sequenceDiagram
    participant Java as Java service
    participant FS as Filesystem / key mount
    participant KS as KeyStore / TLS provider
    participant Peer as Remote peer
    Java->>FS: Open keystore file as service UID
    FS-->>Java: Bytes only if OS/ACL permits
    Java->>KS: Load keystore + password/key provider
    KS-->>Java: Private key access / key managers
    Java->>Peer: TLS/mTLS handshake
    Note over Java,KS: Key có thể tồn tại trong memory nếu file-based
```

Một file permission đúng **không tự bảo đảm** TLS endpoint tin đúng CA hoặc client certificate hợp lệ. Cần cấu hình trust chain, hostname verification, protocol version, cipher suite và certificate renewal.

### 11.2. PKCS#12 và JKS

Java có thể dùng **PKCS#12** hoặc các keystore format/provider khác. Mật khẩu keystore có vai trò bảo vệ theo khả năng định dạng/provider, nhưng:

- Password yếu có thể bị brute-force nếu attacker có file.
- Một số định dạng/entry có semantics riêng về integrity và confidentiality.
- Mật khẩu bị log hoặc nằm trong config đọc công khai làm mất lớp bảo vệ.
- Một process đã mở keystore có thể giữ private key trong memory.
- File được bảo vệ bằng password không thay thế `0600`/ACL tối thiểu.

**Tách nguồn lưu password khỏi file keystore** theo thiết kế, dùng secret manager/identity hoặc API OS phù hợp. Không ghi `-storepass MyPassword` vào shell command hay CI logs nếu có nguy cơ lộ qua history/process list.

### 11.3. Đọc file chỉ bằng service account

Trong một service production:

```text
Key file owner: provisioner/root
Key file group: tls-client-readers
Mode file: 0440 hoặc 0640 theo workflow
Directory: 0750, không group-write
Service UID: billing-svc (thành viên readers theo policy)
```

Ưu điểm của mẫu này là service có thể đọc key để khởi tạo TLS nhưng không có quyền sửa file/directory trực tiếp. Người có quyền thay key phải thuộc provisioning workflow.

Nếu service chỉ có thể khởi chạy khi chạy root, cần xem lại UID/GID, container mount, thư mục cha, ACL hoặc key provider; **không nới sang `chmod 777`**.

### 11.4. Truststore bị thay cũng nguy hiểm

Nếu một process ít đặc quyền được phép ghi truststore, attacker có thể thêm CA giả. Khi đó **tính xác thực peer** bị phá dù private key của dịch vụ chưa lộ.

Vì vậy truststore có thể `0644` hoặc cấu hình phù hợp để đọc rộng, nhưng **quyền ghi phải hạn chế nghiêm ngặt** và file hash/config drift nên được kiểm tra.

### 11.5. Ưu tiên key handle khi cần non-exportable

Nếu private signing/TLS key phải được bảo vệ non-exportable trong HSM, Java có thể dùng provider hoặc cơ chế tương thích để thực hiện tác vụ key mà không xuất plaintext private key thành file.

Khi đó đối tượng kiểm soát chuyển từ:

```text
private-key.pem và chmod
```

sang:

```text
HSM key object + key usage attributes + IAM/token
+ provider configuration + service account + audit
```

File permission vẫn áp dụng cho **provider config, token/credential, socket và certificate** nếu các thành phần này có trên disk.

---

## 12. Java 17: Tạo file demo an toàn ngay lúc tạo

Code dưới đây minh họa **quy trình tạo file** trên filesystem hỗ trợ POSIX attributes. Nó **không ghi private key thật**; nội dung là một chuỗi huấn luyện không phải bí mật.

Thiết kế:

1. Chỉ nhận đường dẫn directory do **operator đáng tin cậy** cung cấp.
2. Tạo thư mục mới mode `0700`, không dùng một thư mục sẵn có có thể bị attacker sửa.
3. Tạo temp file với **POSIX attributes `0600` ngay tại lúc tạo**.
4. Ghi nội dung demo.
5. Chuyển temp file tới tên đích trong **cùng thư mục** bằng atomic move nếu filesystem hỗ trợ.
6. Kiểm tra quyền file/directory và owner sau khi tạo.
7. Không fallback âm thầm sang filesystem không hỗ trợ POSIX.
8. Không in nội dung file.

Đây là bài tập lập trình, **không phải một secret manager hoặc quy trình tạo private key production**.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public final class SecureKeyFileDemo {
    private static final Set<PosixFilePermission> DIR_PERMISSIONS =
            PosixFilePermissions.fromString("rwx------");

    private static final Set<PosixFilePermission> FILE_PERMISSIONS =
            PosixFilePermissions.fromString("rw-------");

    private SecureKeyFileDemo() {}

    static void requireExactPermissions(
            Path path, Set<PosixFilePermission> expected)
            throws IOException {

        if (Files.isSymbolicLink(path)) {
            throw new IOException("Symbolic link not allowed");
        }

        Set<PosixFilePermission> actual =
                Files.getPosixFilePermissions(
                        path, LinkOption.NOFOLLOW_LINKS);

        if (!actual.equals(expected)) {
            throw new IOException(
                    "Unexpected POSIX permissions: " + actual);
        }
    }

    public static void main(String[] args)
            throws IOException {

        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Pass a NEW, trusted directory path for the demo");
        }

        Path dir = Path.of(args[0]).toAbsolutePath().normalize();

        FileStore store = Files.getFileStore(dir.getParent());
        if (!store.supportsFileAttributeView("posix")) {
            throw new IOException(
                    "POSIX file permissions are not supported");
        }

        // Chỉ hoạt động trên đường dẫn mới. Không reuse dir
        // và không để attacker ghi trong các parent directories.
        FileAttribute<Set<PosixFilePermission>> dirAttrs =
                PosixFilePermissions.asFileAttribute(
                        DIR_PERMISSIONS);
        Files.createDirectory(dir, dirAttrs);

        requireExactPermissions(dir, DIR_PERMISSIONS);

        FileAttribute<Set<PosixFilePermission>> fileAttrs =
                PosixFilePermissions.asFileAttribute(
                        FILE_PERMISSIONS);

        Path temp = Files.createTempFile(
                dir, ".demo-stage-", ".tmp", fileAttrs);
        Path target = dir.resolve("example-not-a-real-key.txt");

        try {
            requireExactPermissions(temp, FILE_PERMISSIONS);

            // Chỉ ghi dữ liệu huấn luyện; KHÔNG phải raw secret.
            Files.writeString(
                    temp,
                    "TRAINING DATA ONLY - NOT A CRYPTOGRAPHIC KEY\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);

            if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)) {
                throw new IOException("Target already exists");
            }

            try {
                Files.move(
                        temp, target,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException ex) {
                // Không âm thầm chuyển sang copy rồi chmod.
                throw new IOException("Atomic move is required", ex);
            }

            requireExactPermissions(target, FILE_PERMISSIONS);

            if (!Files.getOwner(target)
                    .equals(Files.getOwner(dir))) {
                throw new IOException("Unexpected owner mismatch");
            }

            System.out.println("Demo file created with 0600");
            System.out.println("Directory created with 0700");

        } finally {
            // Nếu đã move, temp không còn; nếu lỗi, xóa file
            // demo tạm. Không tuyên bố xóa an toàn bytes trên disk.
            Files.deleteIfExists(temp);
        }
    }
}
```

### 12.1. Kết quả dự kiến

Nếu chạy trên filesystem POSIX có thư mục cha đáng tin và quyền cần thiết:

```text
Demo file created with 0600
Directory created with 0700
```

Đây là **kết quả kỳ vọng**, không phải báo cáo chương trình đã được compile/test trên mọi provider, OS hoặc filesystem.

### 12.2. Vì sao `Files.createTempFile(..., attrs)` tốt hơn `write` rồi `chmod`?

Thuộc tính khởi tạo được yêu cầu **cùng thao tác tạo file**. Nó giúp giảm nguy cơ cửa sổ file tạm có quyền quá rộng. Java NIO API cho phép dùng `FileAttribute` để yêu cầu POSIX permissions ngay lúc tạo.

Tuy nhiên, **effective mode thực tế vẫn phải đọc lại** vì filesystem/provider/umask và cơ chế khác có thể ảnh hưởng. Đó là lý do demo kiểm tra sau khi tạo.

### 12.3. Vì sao code từ chối filesystem không hỗ trợ POSIX?

Trên Windows/NTFS, quyền được quản lý qua ACL và không thể diễn đạt đầy đủ bằng `PosixFilePermissions`. Demo **fail closed** để không tạo file mang quyền rộng ngoài dự kiến.

Ứng dụng đa nền tảng thực tế cần **một nhánh Windows ACL được thiết kế/kiểm thử riêng**, hoặc dùng secret manager/key store của hệ điều hành.

### 12.4. Những giới hạn rất quan trọng của demo

- `dir` chỉ đáng tin khi **mọi thư mục cha và nguồn input đều nằm dưới quyền kiểm soát của provisioner**.
- File có mode `0600` nhưng cùng UID với process đã bị compromise vẫn có thể bị đọc.
- `Files.move` có thể có ngữ nghĩa đặc biệt khi đích tồn tại; demo dùng thư mục mới được tạo để tránh đụng độ, nhưng không phải solution chống mọi race trên cây thư mục không đáng tin.
- `ATOMIC_MOVE` là atomic namespace operation trong phạm vi filesystem hỗ trợ; **không tự đảm bảo ghi bền vững sau mất điện hoặc dữ liệu đã được `fsync`**.
- Code không chứng minh không có ACL phụ/default ACL, SELinux policy, network filesystem semantics hoặc Windows permissions.
- Code không tạo key cryptographic, không rotate, không mã hóa payload và không ngăn memory exposure.
- Nếu cần độ bền dữ liệu production, còn phải có cơ chế flush/sync, recovery và versioned publication theo thiết kế.
- `deleteIfExists` không phải cryptographic erase; SSD, filesystem snapshots và backup có thể còn dữ liệu.

**Mục đích học tập:** hiểu ranh giới giữa **tạo file với quyền đúng** và **quản lý bí mật an toàn trong cả vòng đời**.

---

## 13. Java 17: Kiểm tra file permission trước khi load key

Một dịch vụ có thể thực hiện kiểm tra trước khi đọc key file trên POSIX.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.EnumSet;
import java.util.Set;

public final class KeyFilePermissionGuard {
    private KeyFilePermissionGuard() {}

    static void validatePrivateKeyFile(Path file)
            throws IOException {

        if (Files.isSymbolicLink(file)) {
            throw new IOException("Unexpected key symlink");
        }

        if (!Files.isRegularFile(
                file, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Key path is not a regular file");
        }

        Set<PosixFilePermission> p =
                Files.getPosixFilePermissions(
                        file, LinkOption.NOFOLLOW_LINKS);

        Set<PosixFilePermission> prohibited = EnumSet.of(
                PosixFilePermission.GROUP_READ,
                PosixFilePermission.GROUP_WRITE,
                PosixFilePermission.GROUP_EXECUTE,
                PosixFilePermission.OTHERS_READ,
                PosixFilePermission.OTHERS_WRITE,
                PosixFilePermission.OTHERS_EXECUTE,
                PosixFilePermission.OWNER_EXECUTE
        );

        for (PosixFilePermission bad : prohibited) {
            if (p.contains(bad)) {
                throw new IOException(
                        "Private key file has overly broad mode");
            }
        }

        if (!p.contains(PosixFilePermission.OWNER_READ)) {
            throw new IOException("Owner cannot read key file");
        }
    }

    public static void main(String[] args)
            throws IOException {

        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Pass trusted private key path");
        }

        Path file = Path.of(args[0])
                .toAbsolutePath()
                .normalize();

        validatePrivateKeyFile(file);

        // Chỉ sau validation mới bắt đầu load key theo
        // trusted provider / application policy.
        // Không in raw key hay nội dung file.
        System.out.println("POSIX mode check passed");
    }
}
```

### 13.1. Kiểm tra trên khác với bảo đảm an toàn toàn diện

Hàm trên chỉ kiểm tra:

- File là regular file (không qua symlink ở final path).
- Mode bits không cấp quyền group/others.
- Owner có quyền đọc.

Nó **không xác nhận**:

- File owner là service account đúng.
- Các thư mục cha không bị ghi/thay bởi attacker.
- Không có TOCTOU giữa `validate` và thao tác `open`.
- ACL/mount/mandatory access controls khác không mở rộng khả năng thực tế.
- Key nội dung không bị thay.
- File không phải bản copy key bị lộ trước đó.

**Không được mô tả `validatePrivateKeyFile` là security boundary hoàn chỉnh.** Một implementation production cần secure file descriptor handling, trusted directory/file identity, owner/ACL check và kiểm thử hệ điều hành cụ thể; có thể cần thiết kế không dựa vào PEM file.

### 13.2. Symlink trên Kubernetes là ngoại lệ phải hiểu

Ví dụ guard **cố ý từ chối symlink**. Nhưng Kubernetes Secret projected volumes thường dùng symlink do hệ thống quản lý để chuyển phiên bản dữ liệu (atomic writer). Vì vậy gọi guard trên một Secret volume hợp lệ có thể fail.

Trong môi trường Kubernetes, cần thiết kế **trust model riêng cho projected volume**: kiểm tra mount source, UID/GID/mode **của file đích thực tế**, directory protections và quyền Pod; không đơn giản cấm mọi symlink mà không hiểu platform.

### 13.3. Tránh race condition giữa kiểm tra và đọc

Chuỗi:

```text
check permissions
    -> attacker thay file/symlink
        -> application open file khác
```

là mô hình **time-of-check/time-of-use (TOCTOU)** nếu thư mục/đường dẫn có thể bị sửa.

Tăng bảo vệ bằng:

- Dùng thư mục không ghi được bởi attacker.
- Chọn key path từ config đáng tin, không từ request.
- Không follow symlink không đáng tin.
- Dùng API xử lý file descriptor/handle an toàn theo nền tảng khi cần.
- Kiểm tra chủ sở hữu/inode/file type/ACL và source phù hợp.
- Ưu tiên secret mount hoặc KMS/HSM có boundary rõ thay vì tự viết filesystem security framework.

---

## 14. Symlink, hard link, path traversal và thay thế file

### 14.1. Vì sao symlink nguy hiểm?

Nếu một tiến trình privileged ghi key file bằng đường dẫn do attacker kiểm soát:

```text
/tmp/key-output.pem -> /home/victim/important-file
```

một symlink có thể dẫn đến **ghi sai mục tiêu** hoặc đặt secret ở nơi khác nếu API mặc định follow symlink.

Tương tự, nếu app đọc `keys/current.pem` qua symlink attacker có thể sửa, nó có thể nạp **khóa không đúng danh tính** hoặc file bị thay thế.

### 14.2. Hard link và ownership

Hard link là nhiều directory entries trỏ cùng inode, không giống symlink. Khả năng tạo hard link được OS hạn chế theo quyền và sysctl tùy môi trường, nhưng không nên lấy đó làm lý do lưu key trong directory world-writable.

Một file key có mode đúng nhưng có link/hard copy hoặc backup ở nơi khác vẫn có thể tạo vùng lộ bí mật hoặc drift khi rotate.

### 14.3. Path traversal từ cấu hình không đáng tin

Sai:

```java
Path keyPath = Path.of("/keys", request.getKeyName());
```

nếu `keyName` đến trực tiếp từ client và không được kiểm soát. Input như `../...` có thể thoát khỏi thư mục dự kiến.

Thiết kế tốt hơn:

1. Xác thực principal.
2. Xác định tenant/purpose được phép từ server.
3. Resolve `logicalKeyName` trong registry đã tin cậy.
4. Chỉ lấy **file descriptor/key handle** thuộc allowlist và root path đáng tin.
5. Không cho caller tùy ý chỉ định path, KMS URI hay private key object.

**Không dựa vào tên file để thay thế IAM hoặc tenant authorization.**

### 14.4. Atomic replace và giới hạn

Trong rotation, có thể tạo file mới và dùng atomic rename trong cùng filesystem để cập nhật pointer. Điều này giúp reader thấy **phiên bản cũ hoặc mới hoàn chỉnh**, thay vì một file đang ghi dở.

Nhưng cần:

- Tạo file mới với permission và owner đúng **trước cutover**.
- Kiểm tra nội dung/certificate/key pairing theo policy.
- Giữ reference/backup của version cũ khi còn cần.
- Kiểm soát các thư mục và symlink do provisioning sở hữu.
- Nếu app giữ open file descriptor, có thể vẫn đang dùng version cũ.
- Đánh giá fsync/durability, rollback, cache và event signaling.

`chmod 600` **sau** khi atomic move có thể tạo cửa sổ file mới có quyền sai. Permission cần đúng ngay từ khâu tạo.

---

## 15. Docker/container: Image layer không phải nơi cất private key

### 15.1. Lỗi build phổ biến

Ví dụ không nên:

```dockerfile
COPY private-key.pem /app/private-key.pem
RUN chmod 600 /app/private-key.pem
```

Dù file trong image có mode `0600`, raw secret đã được đóng gói vào image layer và có thể tiếp cận bởi người có quyền tải/đọc image, registry artifact, cache hoặc host.

Đặc biệt, quy trình:

```dockerfile
COPY private-key.pem /tmp/private-key.pem
RUN rm /tmp/private-key.pem
```

không bảo đảm xóa secret khỏi layer trước. **Xóa trong layer mới không xóa bytes khỏi history layer cũ.**

### 15.2. Cách cấp key phù hợp hơn

- Dùng runtime secret mount từ orchestrator/secret manager.
- Dùng KMS/HSM qua workload identity khi có thể, tránh private key file.
- Với Docker build cần secret cho dependency fetch, dùng build secret mechanism được hỗ trợ (ví dụ BuildKit secrets), không đưa trực tiếp vào `ARG`/`ENV` hoặc image layers.
- Không in raw secret trong build logs.
- Tách service UID, container filesystem và least privilege.
- Hạn chế quyền truy cập image registry, CI cache và artifact retention.

### 15.3. Root trong container không đồng nghĩa an toàn

Container chạy root có thể đọc nhiều file mount trong chính container; mức quyền đối với host phụ thuộc namespace, capabilities, rootless/userns, mount và runtime policy.

Không tự kết luận:

```text
File mode 0600 trong container -> hoàn toàn tránh được host compromise
```

Host admin, container runtime và workload có quyền cao có thể vẫn truy cập dữ liệu tùy kiến trúc. Cần đánh giá container escape, shared volumes và runtime secrets.

### 15.4. Read-only mount chỉ bảo vệ một chiều

Một volume mount `readOnly: true` giúp giảm khả năng ứng dụng sửa trực tiếp file trong mount. Nhưng nó **không chặn process đọc secret được phép rồi log/gửi ra ngoài**.

Read-only mount + OS permissions + workload identity + app authorization là các lớp bổ sung nhau.

---

## 16. Kubernetes Secrets: `defaultMode`, `runAsUser`, `fsGroup` và symlink

### 16.1. Secret được mount thành file

Một cấu hình minh họa:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: billing-demo
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
  containers:
    - name: app
      image: example.invalid/billing:demo
      volumeMounts:
        - name: tls-key
          mountPath: /var/run/billing-keys
          readOnly: true
  volumes:
    - name: tls-key
      secret:
        secretName: billing-tls
        defaultMode: 0400
```

Đây là manifest **minh họa**. Nếu secret file thuộc UID `root` mà mode `0400`, tiến trình UID `10001` có thể **không đọc được**. Đừng dùng mẫu này rồi kết luận mọi cluster chạy được.

Phải thiết kế **UID/GID, volume type, kubelet behavior và admission/security policy** theo bản Kubernetes/provider thực tế.

### 16.2. `defaultMode` là permission bit mask, không phải key length

Trong YAML Kubernetes, ví dụ `0400` thường biểu diễn bát phân mode chỉ owner đọc; trong JSON biểu diễn cùng giá trị bằng **số thập phân `256`**. Các tool YAML/JSON và version có khác biệt trong cách xử lý số.

Vì vậy khi dùng GitOps/templating:

1. Kiểm tra YAML parser.
2. Kiểm tra manifest sau render.
3. Kiểm tra mode **thực tế bên trong Pod**.
4. Kiểm tra chủ sở hữu và group.
5. Test access bằng UID của container.

Đừng suy luận `0400` là 400 bit hoặc một số quyền bất biến trong mọi toolchain.

### 16.3. `fsGroup` có tác động tùy loại volume

Một Pod có thể dùng:

```yaml
securityContext:
  runAsUser: 10001
  fsGroup: 20001
```

Nhưng group ownership/permissions thực tế của volume có thể phụ thuộc volume plugin, CSI driver và các chính sách xử lý của Kubernetes. Không khẳng định `fsGroup` luôn sửa quyền tất cả Secret volumes theo cùng cách.

Nếu mode file chỉ owner đọc, việc thêm group **không tự tạo group-read**. Cần chọn một mô hình cấp quyền phù hợp: sidecar/init container được phê duyệt, driver hỗ trợ owner/mode hoặc cơ chế external secret delivery, với staging directory bảo vệ đúng.

### 16.4. Kubernetes Secret projection và symlink

Một volume Secret được projected có thể có cấu trúc tương tự:

```text
tls.key -> ..data/tls.key
..data -> ..2026_.../
```

Cơ chế này hỗ trợ cập nhật dữ liệu tương đối nguyên tử. Vì thế:

- Lệnh `ls -l` trên link hiển thị **quyền của symlink**, không nhất thiết là effective mode của target.
- Khi kiểm tra mode của file đích, cần theo dõi link đúng cách, ví dụ `stat -L` trên Linux khi phù hợp.
- Không cho phép attacker kiểm soát mount path hoặc projected volume.
- Không áp dụng rule “mọi symlink là tấn công” khi platform có symlink được quản lý hợp lệ.
- Rotation có thể không được ứng dụng nhận ngay nếu app cache bytes hoặc mở file descriptor cũ.

### 16.5. `subPath` và cập nhật Secret

Trong Kubernetes, Secret mount qua `subPath` thường **không tự nhận các lần cập nhật Secret** như projected volume thông thường. Vì vậy một thiết kế dựa vào hot reload phải kiểm tra cơ chế mount thực tế.

Nếu app đọc key khi startup và giữ private key trong memory, file mới trong volume **không đồng nghĩa ứng dụng đã rotate key đang dùng**. Cần reload/restart có kiểm soát, key version và test mTLS/signature compatibility.

### 16.6. Secret không được mã hóa chỉ nhờ Base64

Kubernetes Secret resource có thể chứa `data` ở dạng Base64. **Base64 không phải mã hóa.** Phải đánh giá:

- RBAC đối với Secret API.
- Encryption at rest cho etcd theo cấu hình cluster.
- Quyền trên node/kubelet/mounted volume.
- Namespace và service account isolation.
- Admission policy, audit và backup.
- Quyền operator/cluster admin và khả năng truy cập pod.

Một Secret được mount với mode `0400` **không tự giải quyết** rủi ro API server hoặc cluster-admin compromise.

---

## 17. CI/CD và infrastructure-as-code: Đừng để key lọt vào artifact

### 17.1. Những nơi dễ làm lộ private key

- Git repository, kể cả Git history sau khi đã xóa file.
- CI workspace, cache và artifact uploads.
- Docker image/build context và layer.
- Logs có `set -x` hoặc debug in toàn bộ environment.
- Shell arguments hoặc command history chứa keystore password/raw secret.
- Test reports, exception dumps, stack traces.
- Terraform/state file hoặc template đã render chứa plaintext secret.
- Package registry hoặc file đính kèm ticket.

Chỉ `chmod 600` trên key file **trong runner** không thu hồi bản sao đã được upload.

### 17.2. Provisioning pipeline đúng hướng

```mermaid
flowchart TD
    A["Authenticated CI workload"] --> B["IAM/approved secret manager"]
    B --> C["Fetch key handle / short-lived secret"]
    C --> D["Trusted dedicated directory"]
    D --> E["Create file with restrictive owner/mode"]
    E --> F["Verify permission + contents metadata"]
    F --> G["Start service as least-privilege UID"]
    G --> H["Audit use + cleanup/rotation"]
```

Nếu có thể, không cần file raw private key: service gọi HSM/KMS qua identity riêng. Nếu buộc phải cấp file, runner phải hạn chế job isolation, retention, access và không lưu raw secret sau deployment.

### 17.3. `umask 077` và secret masking

Một script provisioning có thể cấu hình:

```bash
umask 077
```

**Nhưng secret masking của CI không phải biện pháp tuyệt đối.** Nó có thể không nhận ra secret được encode, cắt, biến đổi hoặc in theo format lạ. Do đó không xuất secret ra log ngay từ đầu.

### 17.4. `.gitignore` không bảo đảm secret không bị commit

`.gitignore` giúp tránh add file theo pattern trong những trường hợp phù hợp, nhưng:

- File đã tracked không tự bị loại.
- Developer có thể force-add.
- Secret có thể xuất trong command output, patch hoặc artifact.
- Credential từng commit phải được **revoke/rotate** theo risk assessment, không chỉ delete commit hiện tại.

### 17.5. IaC không nên chứa raw keys

Một định nghĩa phù hợp hơn:

```yaml
keyReference: kms://approved/key/immutable-id
keyPurpose: DIGITAL_SIGNATURE
serviceIdentity: billing-svc
environment: prod
```

Thay vì:

```yaml
privateKeyPem: "-----BEGIN PRIVATE KEY-----..."
```

Cần xem security của state backend, plan output, secrets interpolation và access logs. Một key reference không phải raw secret, nhưng phải kiểm tra ownership/tenant và integrity.

---

## 18. File encryption at rest và permission là hai lớp riêng

### 18.1. Quyền file bảo vệ ở mức OS identity

POSIX `0600` chặn các user khác theo mode bits; NTFS ACL xác định Access Control Entries. Nhưng khi kẻ tấn công có quyền root/admin hoặc quyền đọc raw disk/backup, lớp permission có thể bị vượt qua.

### 18.2. Mã hóa file bằng passphrase

Một private key có thể ở dạng **encrypted PKCS#8** hoặc bên trong password-protected keystore. Điều này giảm rủi ro nếu attacker có file nhưng không có passphrase.

Tuy nhiên:

- Passphrase có thể yếu hoặc bị lưu ngay cạnh file.
- App cần giải mã private key để sử dụng, có thể đưa material vào memory.
- Encryption format và KDF phải phù hợp, không dùng thuật toán legacy lỗi thời.
- Có nguy cơ mất khả năng khôi phục nếu mất passphrase.
- Permission sai vẫn tăng exposure và cơ hội offline guessing.

**Không dùng password protection để thay thế quyền file tối thiểu.**

### 18.3. Full-disk encryption

BitLocker, LUKS/FileVault hoặc cơ chế disk encryption tương đương giúp giảm rủi ro **mất thiết bị/disk** theo threat model. Nhưng nếu hệ thống đã unlock và process/user có quyền đọc file, disk encryption **không tự chặn**.

### 18.4. Secret manager và KMS/HSM

Với private key dài hạn quan trọng, giảm việc giữ raw key trong file thường có giá trị hơn tối ưu `chmod`:

```text
Service identity
   -> KMS/HSM API
   -> Sign/Decrypt/Wrap trong boundary phù hợp
   -> Trả ciphertext/signature hoặc secret theo API contract
```

Nếu API trả plaintext DEK cho ứng dụng, DEK vẫn xuất hiện trong memory; cần các control riêng. Nếu HSM Sign chỉ trả signature và giữ private key non-exportable, khả năng lộ raw private key qua file có thể được loại bỏ khỏi thiết kế.

### 18.5. Không có một lớp nào đủ

Một mô hình lớp phòng vệ:

```text
Strong cryptography
+ Secure key generation
+ Filesystem/ACL least privilege
+ Workload isolation and IAM
+ Encryption at rest or module-backed keys
+ Runtime memory/log hygiene
+ Audit and incident response
+ Lifecycle/rotation/backups
```

Bỏ bất kỳ lớp quan trọng nào có thể tạo đường tấn công không phụ thuộc vào sức mạnh thuật toán.

---

## 19. Rotation key file: Thay đúng key, không chỉ thay bytes

### 19.1. Mục tiêu rotation

Khi thay private key hoặc PKCS#12:

- Key mới được tạo từ nguồn mật mã an toàn.
- File mới có owner/group/mode đúng ngay lúc tạo.
- Certificate/public key tương ứng được phát hành/đăng ký.
- App chuyển sử dụng key version mới tại thời điểm có kiểm soát.
- Hệ xác minh biết public key/certificate phù hợp.
- Dữ liệu/chữ ký lịch sử còn được xử lý theo retention.
- Key cũ bị hạn chế thao tác, revoke/destroy theo policy.

### 19.2. Mẫu cutover

```mermaid
sequenceDiagram
    participant P as Provisioner
    participant FS as Protected key directory
    participant A as Java service
    participant V as Verifier/Peer
    P->>FS: Create v2 with approved owner/mode
    P->>FS: Validate key+cert, ACL and metadata
    P->>V: Publish trusted public key/certificate v2
    P->>FS: Atomic/controlled cutover active reference
    P->>A: Reload/restart with v2
    A->>V: Sign or mTLS with v2
    V-->>A: Verify by trusted key binding
    P->>FS: Retire v1 after compatibility review
```

Không phải mọi ứng dụng hỗ trợ hot reload. Một số cần rolling restart và thời gian overlap certificate/key acceptance.

### 19.3. Quyền trên file mới quan trọng như file cũ

Một lỗi phổ biến:

```text
Old file: 0600
New file copied from CI workspace: 0644
Alias/current symlink đổi sang new file
```

App vẫn hoạt động nhưng secret có thể bị đọc bởi user khác. **Kiểm tra file target mới trước cutover**, không chỉ kiểm tra tên alias.

### 19.4. Không ghi đè trực tiếp file đang sử dụng

Ghi đè file private key đang được process đọc có thể tạo nội dung dở dang hoặc không khớp certificate. Nên tạo version mới, kiểm tra nhất quán rồi chuyển pointer.

Nhưng alias/symlink/reload là phần của **state machine**, phải có:

- Version metadata.
- Kiểm thử rollback phù hợp.
- Quyền thư mục chặt.
- Đồng bộ nhiều instance.
- Audit và thông báo failure.

### 19.5. Rewrap DEK không giống thay file chứa DEK

Nếu private key hoặc KEK được lưu dưới dạng file và bị lộ, thay file/đổi password chưa chắc đủ:

- Với **DEK bị lộ**: có thể phải generate DEK mới và re-encrypt data.
- Với **KEK bị lộ**: cần đánh giá wrapped DEKs/ciphertext có thể attacker lấy được; có thể rewrap hoặc re-encrypt theo blast radius.
- Với **signing key bị lộ**: cần revoke/replace key, cập nhật verifier và đánh giá chữ ký cũ.
- Với **TLS private key bị lộ**: thay certificate/key và đánh giá phiên/khả năng tấn công theo cấu hình giao thức, forward secrecy và phạm vi lộ.

**Đổi chmod sau khi secret bị sao chép không làm bản sao đã mất quyền kiểm soát biến mất.**

---

## 20. Backup, snapshot, log và file copies: Ranh giới ngoài file gốc

### 20.1. Quyền file gốc không tự theo sang backup

Một file:

```text
/opt/billing/keys/signing-private.pem 0600
```

có thể được backup vào object storage/bundle với access policy khác. Cần kiểm tra:

- Encryption at rest của backup.
- Quyền tải/giải mã backup.
- Retention và lifecycle.
- Vai trò người vận hành/DR.
- Audit truy cập backup.
- Khả năng xóa/hủy key copy theo chính sách.
- Bản sao do CI, local developer hoặc debug tạo ra.

### 20.2. Snapshots có thể chứa bản cũ sau rotation

Nếu file private key bị thay vào ngày T1 nhưng snapshot T0 vẫn có private key cũ, **key rotation chưa loại bỏ mọi bản sao**.

Phải quản lý:

```text
active key version
retired key versions
backup/snapshot copies
data and certificate dependencies
retention/legal holds
deletion and incident policy
```

Trong một số hệ thống có yêu cầu lưu chứng cứ, không thể xóa mọi key ngay; cần hạn chế mục đích verify/decrypt lịch sử theo policy.

### 20.3. Hard delete không phải cryptographic erase

Xóa file hoặc overwrite trên filesystem/SSD có wear leveling, snapshots, copy-on-write và backup không bảo đảm vật liệu không còn. Cryptographic erase có thể phù hợp nếu dữ liệu được bảo vệ dưới key có thể hủy mà không còn bản sao, nhưng phải hiểu đúng key hierarchy và khả năng recovery.

### 20.4. Log và crash dump

Một ứng dụng có thể vô tình log:

```text
privateKey.getEncoded()
AES key as Base64
PKCS12 password
```

Hoặc stack trace chứa secret input. Đó là **bề mặt lộ ngoài key file**. Dùng secure logging/redaction, hạn chế core dump và crash diagnostics theo hệ điều hành.

File mode đúng **không giảm** khả năng attacker đọc raw DEK nếu ứng dụng đã in nó vào log có quyền rộng.

### 20.5. Tmpfs và bộ nhớ

Lưu key trong `tmpfs` có thể giảm persistence trên disk trong một số cấu hình, nhưng không tự đảm bảo:

- Không có swap/crash dump.
- Không có bản sao trong process heap.
- Không bị admin/container escape đọc.
- Không cần quyền file/ACL.
- Không có backup hoặc snapshot của vùng dữ liệu liên quan.

Chọn cơ chế này phải theo threat model, không gắn nhãn “100% không lưu trên đĩa” khi chưa kiểm chứng kernel/runtime.

---

## 21. Kiểm soát quyền file theo vòng đời khóa

| Giai đoạn | Permission/control cần làm gì? | Failure mode |
|---|---|---|
| **Generate** | Sinh key bằng CSPRNG/KMS/HSM; nếu phải ghi file, tạo ngay với mode/ACL chặt. | Tạo file `0644` rồi mới `chmod`. |
| **Distribute** | Chỉ gửi tới authorized service identity/host, audit delivery. | Chuyển qua email/chat hoặc lưu artifact công khai. |
| **Store** | Owner/group/ACL/parent directory đúng; encryption at rest khi cần. | Key có `0600` nhưng cùng UID với nhiều service. |
| **Use** | Process chỉ có quyền đọc key đúng purpose, tenant và operation. | Backend dùng arbitrary path/key ID do client nhập. |
| **Rotate** | Tạo version mới, verify, controlled atomic publication, reload. | Key mới `0644` hoặc cert không khớp. |
| **Revoke** | Chặn truy cập và key use, invalidate sessions/grants liên quan. | Chỉ `chmod 000`, nhưng bản copy/loaded key vẫn tồn tại. |
| **Destroy** | Đánh giá backup, dependencies, retention; hủy theo cơ chế phù hợp. | Xóa key còn cần decrypt/verify dữ liệu lịch sử. |
| **Audit** | Ghi who/what/when/where, permission changes và access anomalies. | Log raw key hoặc thiếu evidence thay quyền. |

### 21.1. `chmod 000` không đồng nghĩa key revoked

Nếu app đã load private key vào memory hoặc HSM vẫn chấp nhận `Sign`, việc đổi quyền file sau đó không tự làm các key copies/crypto handles mất hiệu lực.

Revoke cần xử lý **runtime state, key usage permissions, certificate/issuer status, HSM grants, app sessions và trusted public keys** theo loại khóa.

### 21.2. Deletion gate

Trước khi xóa file key hoặc disable KMS/HSM key:

```text
Có dữ liệu/ciphertext nào còn phụ thuộc?
Có wrapped DEK/backup nào cần mở?
Có signature cần verify lịch sử?
Có credential/certificate session nào còn tồn tại?
Có bản sao nào cần thu hồi?
Có legal hold và approval nào?
```

Một key file permission an toàn không có ý nghĩa nếu vận hành xóa key làm mất dữ liệu vĩnh viễn.

---

## 22. Key inventory và policy-as-code cho file permission

### 22.1. Metadata cần theo dõi

Một bản ghi inventory có thể có:

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| `keyId` | `billing-sign-v4` | Định danh logic/version thực tế. |
| `keyPurpose` | `DIGITAL_SIGNATURE` | Không dùng nhầm với DEK/KEK. |
| `storageType` | `FILE`, `KMS`, `HSM`, `OS_KEYSTORE` | Nơi khóa được giữ. |
| `pathReference` | `/opt/billing/keys/...` | Tham chiếu có kiểm soát, không chứa raw key. |
| `environment` | `prod` | Ranh giới dùng. |
| `tenantScope` | `shared` | Cách phân tách tenant. |
| `ownerPrincipal` | `billing-svc` | Principal sở hữu/đọc khóa. |
| `groupPrincipal` | `billing-key-readers` | Nhóm được phép nếu có. |
| `expectedFileMode` | `0600` | Quy tắc kỳ vọng đối với POSIX. |
| `observedFileMode` | `0600` | Metadata đã đọc lại. |
| `aclPolicyRef` | `acl-billing-v2` | Kiểm soát ACL cụ thể OS. |
| `parentDirectoryPolicy` | `0700` / `0750` | Không chỉ kiểm file. |
| `keyOrigin` | `HSM_GENERATED`, `IMPORTED`, `APP_GENERATED` | Nguồn vật liệu. |
| `exportPolicy` | `NON_EXPORTABLE`, `APPLICATION_MEMORY` | Có raw key tại app không. |
| `lastVerifiedAt` | UTC timestamp | Lần đối soát gần nhất. |
| `rotationDueAt` | UTC timestamp | Thời hạn thay khóa. |
| `policyVersion` | `key-storage-2026-v1` | Chuẩn được dùng đánh giá. |

**Lưu ý:** lưu file path/owner có thể tiết lộ chi tiết kiến trúc. Inventory cần IAM/retention đúng; không ghi raw private key hay password.

### 22.2. Policy mẫu theo loại vật liệu

```yaml
policyId: key-file-storage-baseline
version: 1

rules:
  - materialType: PRIVATE_KEY
    environment: prod
    storagePreference: HSM_OR_OS_KEYSTORE
    ifFileRequired:
      posixModesAllowed: ["0400", "0600"]
      parentDirectoryModesAllowed: ["0700"]
      authorizedReader: service-identity
      prohibitBroadAcl: true
      prohibitUntrustedSymlink: true

  - materialType: PKCS12_WITH_PRIVATE_KEY
    environment: prod
    ifFileRequired:
      posixModesAllowed: ["0400", "0600"]
      requirePasswordProtection: according-to-crypto-policy
      requireSecretPasswordSource: true

  - materialType: PUBLIC_CERTIFICATE
    environment: prod
    integrityProtectionRequired: true
    restrictWriteTo: approved-provisioner
```

Đây là **policy-as-code minh họa**, không phải cấu hình của một engine hay provider cụ thể. Trên container, Windows hoặc volume chia nhóm, cần profile khác đã được review thay vì áp máy móc `0600` cho mọi trường hợp.

### 22.3. Kiểm tra không chỉ mode bits

Một policy guard production nên kiểm:

```text
file type / symlink policy
file owner / group
POSIX mode hoặc NTFS DACL/ACE
directory traversal và write permissions
effective access test
container UID/GID và mount semantics
SELinux/AppArmor/OS sandbox
key content/provenance khi được phép
backup/image/CI copies
rotation/key version
```

Không một `stat -c %a` nào đánh giá được toàn bộ.

### 22.4. Kết quả compliance nên có UNKNOWN

Nếu hệ thống không thể truy vấn ACL của một file share:

```text
status = UNKNOWN
reason = permission-metadata-unavailable
```

Không tự báo `PASS` chỉ vì key ở path có tên `/secure/`. Cũng không nên khẳng định chắc chắn đã bị xâm nhập; cần kiểm tra và escalation theo risk tier.

---

## 23. Monitoring và audit thay đổi quyền truy cập

### 23.1. Các sự kiện nên giám sát

- File permission chuyển từ `0600` sang `0644`/`0666`.
- ACL thêm user/group không thuộc allowlist.
- Owner/group bị đổi.
- Thư mục cha mở quyền ghi ngoài dự kiến.
- Key được copy sang path mới không thuộc inventory.
- Private key xuất hiện trong image/repository/log/CI artifact.
- Symlink hoặc target file thay đổi ngoài rotation workflow.
- Certificate/key pair mismatch sau deploy.
- Service nhận lỗi đọc key sau khi UID/GID thay.
- KMS/HSM grants thay, key alias cutover hoặc key bị disable.

### 23.2. Logging không chứa secret

Một event tốt có:

```text
timestamp
host/pod/service
principal/workload identity
keyId/version hoặc hashed path reference
eventType = PERMISSION_DRIFT / KEY_FILE_REPLACED
previousMode / currentMode
owner / group / policyVersion
actor / correlationId
decision / remediationStatus
```

Không ghi nội dung private key, keystore password, raw DEK/KEK hoặc file dump vào cảnh báo.

### 23.3. Giám sát hiệu lực, không chỉ cấu hình

Một scanner chạy mỗi ngày có thể phát hiện `0644` sau nhiều giờ. Với file signing key production, yêu cầu thời gian phát hiện có thể nghiêm ngặt hơn.

Cần kết hợp:

- Admission/CI gate trước deploy.
- Kiểm tra ngay sau mount/provision.
- File integrity/permission monitoring phù hợp OS.
- Event khi file owner/mode/ACL thay.
- Lịch đối soát định kỳ.
- Người trực và incident playbook.

**Có alert nhưng không có owner xử lý không phải control vận hành đầy đủ.**

---

## 24. Incident response: Phát hiện private key bị world-readable

### 24.1. Tình huống

Security scanner phát hiện:

```text
/opt/payment/keys/signing.pem mode 0644
```

Trong 12 giờ, file có thể đọc bởi các user khác trên cùng host. Không có bằng chứng ngay rằng key đã bị trích xuất, nhưng **confidentiality boundary bị vi phạm**.

### 24.2. Hành động theo thứ tự rủi ro

1. **Khoanh vùng:** host, filesystem, key ID/version, principal và thời gian file mở quyền.
2. **Chặn exposure mới:** sửa quyền/ownership và directory ACL theo approved runbook; không làm service outage ngoài dự kiến.
3. **Bảo toàn evidence:** permission history, EDR/audit, process list, access logs và file metadata; không sao chép raw key vào ticket.
4. **Đánh giá khả năng truy cập:** user/process nào có thể đọc, snapshots/backups nào có bản copy, key có bị log/đưa vào image không?
5. **Xử lý key compromise theo mức rủi ro:** với private signing key bị nghi lộ, ưu tiên tạo key mới, cập nhật public key/certificate/trust và revoke/disable old key phù hợp.
6. **Kiểm tra hệ phụ thuộc:** JWT/JWS, TLS/mTLS, chữ ký lưu trữ, CA/trust registry, session đang hoạt động và retention.
7. **Sửa nguyên nhân gốc:** umask, CI file copy, UID/GID, volume permissions, IaC, default ACL hoặc rotation script.
8. **Kiểm thử lại:** negative access tests, audit, failover và rollback scenarios.
9. **Cập nhật runbook/policy:** thêm guardrails ngăn `chmod 777` và secret artifact leakage.

### 24.3. Chỉ `chmod 600` là chưa đủ

Nếu attacker đã lấy private key, chuyển mode về `0600` **không thu hồi key**. Tùy hệ thống:

- Private signing key: revoke/replace, review signature validity.
- TLS key: thay certificate/key và đánh giá các phiên/kiểu tấn công có thể.
- HMAC key: rotate key giữa các bên, điều chỉnh replay window và xác minh thông điệp.
- AES DEK: re-encrypt dữ liệu khi key bị lộ.
- KEK: đánh giá wrapped DEK và ciphertext copies; rewrap/re-encrypt theo phạm vi.

### 24.4. Không tự kết luận truy cập đã xảy ra

`0644` chứng minh một nhóm principal **có thể** đọc theo mode bits nếu đường dẫn cho phép; không chứng minh ai **đã thực sự** đọc. Cần kết hợp audit, host forensics và impact analysis. Tuy vậy thiếu log không đồng nghĩa key chưa bị sao chép.

---

## 25. Case study: Bảo vệ signing key cho microservice Java trong Kubernetes

### 25.1. Bối cảnh

Một nền tảng có:

- `Payment Service` Java 17 ký webhook và xác thực mTLS.
- Nhiều replicas trên Kubernetes, production và staging tách biệt.
- Một private signing key, một certificate chain, một truststore.
- KMS/HSM và secret manager đã được phê duyệt.
- CI/CD triển khai versioned artifacts.
- Key inventory, central audit và backup/DR.

Yêu cầu:

1. Không ai ngoài workload được cấp quyền có thể đọc private key.
2. Không đưa raw private key vào image/repository/CI artifact.
3. Private key rotation không gây dùng nhầm key version giữa pods.
4. Không mở quyền `0777` để vượt lỗi mounted Secret permissions.
5. Có audit/cảnh báo khi ACL hoặc key version drift.
6. Có kế hoạch nâng lên HSM non-exportable nếu threat model yêu cầu.

### 25.2. Thiết kế theo lớp

**Phương án ưu tiên khi cần non-exportable signing key:**

```text
Workload identity -> authorized KMS/HSM Sign
                   -> signature
Private key không có dạng PEM file trong Pod
```

Cần kiểm tra KMS/HSM hỗ trợ thuật toán, latency, rate limits, authorization nghiệp vụ, audit và key availability. Không phải mọi provider hỗ trợ tất cả signing algorithms hoặc mode.

**Phương án file-based khi được policy cho phép:**

```text
Secret manager / Kubernetes Secret
    -> mount vào Pod với UID/GID/mode được kiểm chứng
    -> Java TLS/signing provider load file
    -> key chỉ tồn tại trong Pod/process theo data flow
```

Mỗi Pod chỉ nhận đúng key theo service/tenant scope; không share một volume chứa nhiều private keys không cần thiết.

### 25.3. Kiểm soát cấp container

- `runAsNonRoot` và service UID tách biệt.
- Root filesystem read-only khi phù hợp.
- Secret volume read-only.
- Không mount Docker socket/host filesystem tùy ý.
- Không cấp privileged container hoặc Linux capabilities không cần.
- Network policy và workload identity giới hạn đường truy cập.
- Không sử dụng một UID/group chung cho mọi service nhạy cảm.
- Quan sát quyền thực tế ở file target của projected Secret.

### 25.4. Kiểm tra sau deploy

Một quy trình test an toàn có thể xác nhận:

```text
Service account can read its own key: PASS
Other app identity can read key: DENIED
Key target effective owner/mode: matches approved policy
Parent/mount path writable by unrelated workload: NO
Secret present in image layers: NO
Secret value appears in logs/artifacts: NO
mTLS/signature succeeds under expected key version: PASS
```

Kết quả phải đến từ kiểm tra thực tế, không phải chỉ đọc manifest YAML.

### 25.5. Mô hình rotation

```mermaid
flowchart TB
    Gen["Generate new key/version"] --> Publish["Publish certificate/public key"]
    Publish --> Secret["Provision secret or HSM key ID"]
    Secret --> Verify["Verify ACL/UID/GID + key metadata"]
    Verify --> Roll["Rolling reload/restart Pods"]
    Roll --> Accept["Confirm active key version in app"]
    Accept --> Audit["Audit + monitor"]
    Audit --> Retire["Retire old key after overlap"]
```

Nếu ứng dụng không tự nạp lại projected Secret, cần rolling restart. Nếu dùng TLS key/cert cặp đôi, phải cập nhật nhất quán. Nếu ký JWT/JWS, verifier cần trust public keys theo issuer và `kid` đúng, không lấy key tùy ý do client khai.

### 25.6. Sự cố thường gặp và cách xử lý

| Sự cố | Nguyên nhân có thể | Không nên làm | Hướng xử lý |
|---|---|---|---|
| Pod UID 10001 không đọc được key mode 0400 root-owned | Ownership/mode không khớp | `chmod 777` | Thiết kế delivery/UID/GID hoặc CSI/init workflow an toàn |
| Một replica ký bằng key cũ | Secret cache/subPath/app chưa reload | Xóa old public key ngay | Theo dõi active version và rolling update |
| Signing key lộ trong image layer | Build COPY key | Chỉ `RUN rm` | Revoke/rotate, làm sạch pipeline/image artifacts |
| App đọc file khác sau rotation | Symlink/mapping drift | Bỏ qua key ID/version | Verify target, trusted path, controlled cutover |
| Keystore password ở ConfigMap đọc rộng | Nhầm config với secret | Giữ nguyên vì PKCS12 có password | Secret delivery + IAM + rotation |
| Key đúng mode nhưng process đọc được key tenant khác | Cùng UID/volume hoặc authz sai | Chỉ đổi tên file | Tenant isolation, identity/volume/key mapping |

### 25.7. Bằng chứng cần lưu

- Manifest/IaC policy version, Secret reference và deployment revision.
- UID/GID/mode/ACL effective (không lưu raw key).
- Test principal được phép và không được phép.
- Key version ID, certificate serial/fingerprint công khai phù hợp.
- Sự kiện rotate, revoke, reload và audit.
- Kết quả scan image/artifact và DR.
- Exception nếu cần thay đổi quyền theo mô hình đặc thù.

---

## 26. Lỗi thường gặp và cách khắc phục

| Sai lầm | Vì sao nguy hiểm? | Cách khắc phục |
|---|---|---|
| `chmod 777 private.key` | Đọc/sửa rộng, có thể giả mạo/lộ key. | Quyền tối thiểu theo owner/group/ACL. |
| `chmod 600` nhưng service chạy root | Blast radius lớn, không giảm quyền process. | UID riêng, IAM, tách privilege. |
| `chmod 600` nhưng key thuộc UID chung cho nhiều service | Mọi service cùng UID có thể đọc. | Tách identities, container/OS boundaries. |
| File đúng mode nhưng thư mục parent world-writable | Có thể thay entry/symlink. | Kiểm tra/trói quyền toàn bộ path. |
| Dùng `umask 022` rồi ghi secret trước `chmod` | File có thể tạo `0644`. | Tạo file với mode ngay lúc tạo, `umask 077`. |
| Chỉ dùng `ls -l`, bỏ qua ACL | Không biết effective rights. | `getfacl`, NTFS ACL và access tests. |
| Group `shared-services` được đọc mọi private keys | Blast radius rộng. | Group/ACL riêng theo service/purpose. |
| Chạy service bằng root để đọc secret | Privileged app compromise. | Provision owner/group phù hợp. |
| Lưu private key trong Docker image | Secret tồn tại trong image layers/cache. | Runtime secret delivery/KMS/HSM. |
| Xóa key ở Docker layer sau COPY | Layer cũ vẫn có bytes. | Không đưa key vào build context/layers. |
| Kubernetes `defaultMode: 0400` với nonroot UID khác owner | Pod không đọc được. | Kiểm tra owner/mode/fsGroup/driver. |
| Tưởng symlink Kubernetes luôn là tấn công | Projected Secret thường dùng symlink. | Trust platform, kiểm target effective và mount source. |
| Dùng Secret `subPath` và đợi tự cập nhật | Key version có thể stale. | Controlled reload/rollout, kiểm app behavior. |
| Base64 Kubernetes Secret được coi là encryption | Base64 chỉ encoding. | RBAC, etcd encryption at rest và node controls. |
| PKCS12 password lưu ngay cạnh file đọc công khai | Mất lớp bảo vệ. | Secret manager và access controls riêng. |
| Truststore cho phép mọi user ghi | Có thể thêm CA giả. | Bảo vệ integrity và audit. |
| `getPosixFilePermissions` được dùng làm xác minh Windows | NTFS ACL có model khác. | Windows-specific ACL validation. |
| Chỉ đổi `chmod` sau khi key bị lộ | Không thu hồi copies. | Revoke/rotate và xử lý dependencies. |
| Rename file khi rotation nhưng quên quyền | New key có mode sai. | Secure create + verify trước cutover. |
| Không kiểm tra active process key version | App giữ key cũ trong memory. | Reload/restart, version tracking. |
| Lưu raw key vào CI logs/trace | Tạo bản sao ngoài filesystem policy. | Không log bí mật, kiểm scan, rotate khi lộ. |
| Xóa file và nghĩ key đã bị hủy hoàn toàn | Backup/snapshot/SSD vẫn có copies. | Key lifecycle/cryptographic erase theo policy. |
| Một KMS key ID trong config bị client tự chọn | Confused deputy/tenant bypass. | Server-side registry và authorization. |
| File `0400` được coi là immutable tuyệt đối | Owner có thể thay directory entry, root có quyền. | Folder integrity, separated provisioner, OS controls. |
| Không có DR test | Key mất khiến ciphertext không đọc được. | Versioned inventory và restore drill. |

---

## 27. Checklist production cho Permission của key file

### OS/filesystem

- [ ] Xác định file có chứa **private/secret key** hay chỉ public certificate/trust material.
- [ ] Private key file trên POSIX được tạo với mode chặt ngay từ đầu (`0600`/`0400` hoặc profile khác đã duyệt).
- [ ] Directory chứa key và các parent paths có quyền owner/group/ACL phù hợp.
- [ ] Không có write permission trái phép trên parent directory.
- [ ] Service UID/GID được kiểm tra, không dùng root vô cớ.
- [ ] Các service khác không dùng chung UID/group có quyền đọc cùng secret không cần thiết.
- [ ] `umask`, default ACL và effective permissions được kiểm tra sau provisioning.
- [ ] Windows dùng NTFS ACL riêng; không áp giả định POSIX mode.
- [ ] Có chính sách xử lý symlink/path traversal và atomic replace.
- [ ] Có negative access test dưới principal không được phép.

### Secret storage và Java

- [ ] Không lưu raw key trong image, Git, CI artifacts, logs, config đọc rộng.
- [ ] Java keystore/PKCS12 có password bảo vệ phù hợp, nhưng **vẫn** có OS access restrictions.
- [ ] Password/secret của keystore được cấp qua nguồn bảo vệ phù hợp.
- [ ] Public cert/truststore được bảo vệ **integrity** ngay cả khi không cần giấu.
- [ ] Với private key non-exportable, ưu tiên HSM/KMS/OS key store khi phù hợp.
- [ ] Key ID/alias và tenant được resolve từ nguồn tin cậy, không từ request tùy ý.
- [ ] Không dùng `getEncoded()` để log hoặc kiểm kê raw key.
- [ ] Có chính sách hạn chế memory/core dump khi app buộc load secret.

### Containers/Kubernetes

- [ ] Secret volume là read-only khi có thể.
- [ ] Kiểm chứng `defaultMode`, UID/GID, `runAsUser`, `fsGroup` và driver behavior **trên Pod thật**.
- [ ] Hiểu project Secret symlinks, `subPath` và cơ chế cập nhật.
- [ ] Không có secret trong image layer hoặc build cache.
- [ ] Kubernetes Secret API RBAC và etcd encryption được cấu hình đúng risk policy.
- [ ] Không cấp privileged pod/host mount không cần thiết.
- [ ] Có cơ chế reload/restart và kiểm active key version sau rotation.

### Lifecycle/audit

- [ ] Key inventory lưu owner, storage type, file path reference, version, policy và evidence.
- [ ] Rotation tạo file mới an toàn, kiểm key/cert pairing và cutover.
- [ ] File permission/ACL drift được phát hiện và có người xử lý.
- [ ] Audit không chứa raw private key, DEK, password hoặc HMAC secret.
- [ ] Có runbook khi key file bị world-readable hoặc bản sao xuất hiện ở CI/Git.
- [ ] Backup/snapshot được bảo vệ và có retention, access audit rõ ràng.
- [ ] Trước khi xóa/revoke, kiểm tra ciphertext và chữ ký lịch sử còn phụ thuộc.
- [ ] Có DR drill và kiểm thử decrypt/verify dữ liệu lịch sử.
- [ ] Không coi `chmod 000`, xóa file hay đổi tên là key revocation hoàn chỉnh.

---

## 28. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `chmod 600 private.key` thường tốt hơn `chmod 644` trên host đa user?

**Gợi ý:** `0600` không cấp read cho group/others theo POSIX mode; `0644` cho phép others đọc.

**Câu 2.** Một private key file có mode `0600` nhưng nằm trong thư mục group-writable. Có còn rủi ro không?

**Gợi ý:** có. Directory write cho phép thay/rename entry trong điều kiện nhất định; cần kiểm soát toàn bộ đường dẫn.

**Câu 3.** `chmod 400` có khiến key trở nên immutable đối với owner/root không?

**Gợi ý:** không. Permission trên directory và quyền admin có thể cho sửa/thay entry hoặc mode.

**Câu 4.** `umask 077` có làm các key file cũ tự chuyển thành `0600` không?

**Gợi ý:** không. Nó ảnh hưởng mode tạo mới của process và còn phụ thuộc API/ACL.

**Câu 5.** Vì sao hai service cùng UID vẫn có thể đọc chung file `0600`?

**Gợi ý:** kernel xét UID, không dựa vào tên ứng dụng. Cần phân tách service identities.

**Câu 6.** Vì sao chỉ đọc `ls -l` có thể không đủ khi filesystem hỗ trợ ACL?

**Gợi ý:** named users/groups, ACL mask và default ACL có thể ảnh hưởng effective access.

**Câu 7.** Trên Windows, dùng `chmod 600` có đủ thay NTFS ACL không?

**Gợi ý:** không. Cần kiểm tra DACL, ACE, inherited permissions và service identity.

**Câu 8.** Truststore chỉ chứa certificate công khai. Có cần bảo vệ không?

**Gợi ý:** có, cần bảo vệ integrity; attacker có quyền ghi có thể thêm CA giả.

**Câu 9.** Đã có password trên PKCS#12 thì có thể để file `0644` không?

**Gợi ý:** không nên mặc định. Password có thể yếu/lộ và attacker có thể offline guess; dùng least privilege.

**Câu 10.** Vì sao xóa private key bằng `RUN rm` trong Dockerfile chưa chắc loại bỏ nó?

**Gợi ý:** image layer trước vẫn có thể chứa dữ liệu.

**Câu 11.** Tại sao Kubernetes Secret mount `0400` đôi khi khiến Pod `runAsUser: 10001` không đọc được?

**Gợi ý:** owner có thể là root; group/read policy cần phù hợp effective UID/GID.

**Câu 12.** Một Secret projected volume dùng symlink. Có nên luôn từ chối toàn bộ symlink không?

**Gợi ý:** không; phải hiểu symlink do platform quản lý, trust mount source và kiểm target/file identity.

**Câu 13.** Kubernetes Secret lưu Base64 đã được mã hóa chưa?

**Gợi ý:** chưa. Base64 chỉ encoding; xem RBAC, etcd encryption và node permissions.

**Câu 14.** Vì sao file mode đúng nhưng raw key vẫn có thể lộ trong CI?

**Gợi ý:** vì build logs, artifact, image layers, cache và command history là những bản sao độc lập.

**Câu 15.** Việc đổi permission sau khi key bị world-readable có đủ xử lý sự cố không?

**Gợi ý:** không. Key có thể đã bị sao chép; cần đánh giá compromise, rotate/revoke và xử lý dữ liệu phụ thuộc.

**Câu 16.** Đổi KEK hay rewrap DEK có làm một DEK đã bị lộ trở nên bí mật lại không?

**Gợi ý:** không. Nếu raw DEK lộ cần thay DEK và re-encrypt dữ liệu theo phạm vi.

**Câu 17.** Vì sao việc kiểm permission trước khi open file có thể có TOCTOU?

**Gợi ý:** attacker có thể thay đường dẫn giữa kiểm tra và sử dụng nếu parent directory không đáng tin.

**Câu 18.** HSM non-exportable private key còn cần file permission không?

**Gợi ý:** không có raw private key file để chmod, nhưng config/provider token/socket và credentials vẫn cần bảo vệ OS/IAM.

**Câu 19.** Nếu service cần đọc nhưng không cần thay private key, thiết kế owner/group nào có ích?

**Gợi ý:** file do provisioner sở hữu, group reader hạn chế, service chỉ có group-read; directory không group-write, kiểm ACL.

**Câu 20.** Tại sao phải lưu key ID/version trong inventory dù key chỉ ở file?

**Gợi ý:** để truy vết rotation, certificate/signature/ciphertext dependencies, backup, audit và incident response.

---

## 29. Tổng kết: `chmod` là điểm bắt đầu, không phải toàn bộ key storage

**Permission của key file** giúp giới hạn ai được đọc, ghi và truy cập đường dẫn chứa private/secret keys. Trên POSIX, file secret thường phù hợp với `0600` hoặc `0400` cùng thư mục `0700` trong những mô hình đơn service account; một số hệ cần owner/group/ACL đọc riêng, ví dụ `0440` với thư mục `0750` và quyền ghi bị hạn chế. Trên Windows, dùng **NTFS ACL** và cơ chế bảo vệ khóa theo nền tảng.

Những điểm cần ghi nhớ:

1. **Bảo vệ file lẫn thư mục cha:** permission của directory quyết định khả năng traverse, rename và thay entry.
2. **Tạo file an toàn từ đầu:** `umask`, `FileAttribute` và secure provisioning giảm cửa sổ lộ secret.
3. **Kiểm tra effective access:** UID/GID, ACL, owner, mount, container identity và OS policy.
4. **Không dùng `chmod 777` để giải lỗi đọc key:** phải tìm đúng quyền của service account.
5. **Không đưa raw key vào Git/image/CI/log/backup thiếu kiểm soát:** các bản sao này không được bảo vệ chỉ bằng permission file gốc.
6. **Phân biệt private key với public certificate và truststore:** confidentiality và integrity có yêu cầu khác nhau.
7. **Kubernetes/Windows cần mô hình riêng:** không áp POSIX `0600` máy móc cho mọi volume/provider.
8. **Rotation phải đảm bảo mode, owner, key version và reload đúng:** đổi tên file không tự đổi khóa đang dùng trong process.
9. **KMS/HSM làm giảm nhu cầu raw key file:** nhưng IAM, key usage, audit và memory exposure vẫn quan trọng.
10. **Quyền file không sửa được key đã lộ:** phải ứng cứu, thu hồi/rotate/re-encrypt và kiểm tra lịch sử.

Trong **quản lý vòng đời khóa mật mã**, file permission là một **preventive control ở tầng hệ điều hành**, cần được liên kết với **key generation, secure storage, key inventory, access policy, audit, rotation, revoke và disaster recovery**. Không chỉ cần một file không đọc được bởi người lạ; cần một hệ thống biết **ai được dùng đúng khóa vào đúng mục đích, bằng chứng nào chứng minh điều đó và phải làm gì khi một lớp bảo vệ thất bại**.

### Tài liệu nền

- **NIST SP 800-57 Part 1**, *Recommendation for Key Management* — key protection, cryptoperiod, lifecycle và quyền sử dụng.
- **NIST SP 800-130**, *A Framework for Designing Key Management Systems* — yêu cầu thiết kế hệ quản lý khóa và storage controls.
- **FIPS 140-3**, *Security Requirements for Cryptographic Modules* — bảo vệ key material trong cryptographic boundary.
- **POSIX / IEEE Std 1003.1**, *File Permissions and Access Control* — semantics `rwx`, owner/group, directories, `umask`.
- **Linux manual pages**, *chmod(1), umask(2), open(2), stat(2), acl(5)* — quyền, ACL, file operations và những giới hạn.
- **Java SE 17 API**, `java.nio.file.Files`, `PosixFilePermissions`, `PosixFileAttributeView`, `AclFileAttributeView` — hỗ trợ kiểm soát filesystem.
- **OpenSSH documentation**, *SSH Key Authentication / ssh_config / sshd_config* — key files, identities và quyền filesystem.
- **Microsoft Windows documentation**, *Access Control Lists, NTFS File Security, DPAPI/CNG* — file permissions và bảo vệ khóa theo nền tảng.
- **Kubernetes documentation**, *Secrets, Pod Security Context, Volumes* — secret mount, `defaultMode`, UID/GID, projected volumes và rotation.
- **Docker documentation**, *Build Secrets / Security* — tránh lưu raw secrets trong image build layers.
- **OWASP Key Management Cheat Sheet** — thực hành quản lý và bảo vệ key material.
- **OWASP Secrets Management Cheat Sheet** — quản lý bí mật, quyền, logging và vòng đời.
- **OWASP Cryptographic Storage Cheat Sheet** — DEK/KEK, envelope encryption và secure storage.

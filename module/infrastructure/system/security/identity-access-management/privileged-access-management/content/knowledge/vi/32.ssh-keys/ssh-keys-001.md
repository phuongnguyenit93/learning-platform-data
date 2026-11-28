# SSH key inventory

## 1. Mục tiêu của bài học

Trong Privileged Access Management (PAM), kiểm kê SSH key là việc xác định **khóa nào đang tồn tại, ai hoặc workload nào sử dụng, được phép vào đâu, với quyền gì và còn được phép tồn tại đến khi nào**. Một danh sách file có đuôi `.pub` chưa trả lời được những câu hỏi này.

Sau bài học, bạn có thể:

- Phân biệt khóa xác thực người dùng, khóa máy chủ, SSH certificate và các điểm cấu hình cấp quyền.
- Dùng fingerprint để đối soát cùng một public key qua nhiều hệ thống.
- Thiết kế danh mục khóa và danh mục quan hệ cấp quyền đủ phục vụ least privilege, thu hồi và kiểm toán.
- Thu thập bằng chứng theo phạm vi được giao, hạn chế dữ liệu nhạy cảm và ghi nhận rõ phần chưa quan sát được.
- Chuyển các phát hiện như khóa vô chủ, quyền root, đường truy cập ngoài PAM hoặc ngoại lệ quá hạn thành công việc có người chịu trách nhiệm.

Bài học dùng các ví dụ OpenSSH trên Linux. Vị trí file, cơ chế định danh, tùy chọn được hỗ trợ và cách thu thập log phụ thuộc hệ thống thực tế. Không áp dụng nguyên trạng đường dẫn mẫu cho mọi máy.

## 2. Vì sao PAM cần kiểm kê SSH key?

Giả sử một công ty quản lý 120 máy chủ. Nhóm vận hành cho biết mọi truy cập quản trị đều đi qua bastion và phải được phê duyệt. Tuy nhiên, một public key cũ của kỹ sư đã nghỉ việc vẫn xuất hiện trong `/root/.ssh/authorized_keys` trên ba máy. Tường lửa hiện tại chặn đường truy cập trực tiếp, nhưng một thay đổi mạng trong tương lai có thể làm đường này hoạt động trở lại.

Có ba điều cần phân biệt:

1. Khóa vẫn được cấu hình cấp quyền.
2. Đường mạng hiện có thể sử dụng được hay không.
3. Có bằng chứng khóa đã được dùng trong một khoảng thời gian cụ thể hay không.

Không quan sát thấy đăng nhập không đồng nghĩa khóa đã được thu hồi. Không có đường mạng hôm nay cũng không chứng minh quyền cấu hình là phù hợp.

PAM cần inventory để biết đầy đủ bề mặt đặc quyền trước khi quyết định vault, luân chuyển khóa, chuyển sang certificate ngắn hạn hoặc áp dụng Just-in-Time (JIT). Nếu bỏ sót một điểm tin cậy, có thể đóng quyền trong cổng PAM nhưng vẫn để lại một đường SSH khác.

Một bản kiểm kê có ích phải hỗ trợ câu hỏi:

> “Nếu khóa có fingerprint X bị lộ ngay bây giờ, chúng ta cần kiểm tra và thu hồi những quan hệ cấp quyền nào, ai phê duyệt và làm sao xác nhận đã xử lý đủ?”

## 3. Những đối tượng dễ bị nhầm lẫn

| Đối tượng | Vai trò | Inventory cần ghi nhận |
|---|---|---|
| Private key của người dùng hoặc workload | Chứng minh quyền sở hữu trong quá trình xác thực | Chủ thể giữ khóa, hình thức bảo quản, thiết bị hoặc hệ thống giữ khóa; không thu thập giá trị private key |
| Public key tương ứng | Định danh vật liệu công khai dùng để xác thực | Fingerprint, loại khóa, nguồn bằng chứng và các quan hệ cấp quyền |
| `authorized_keys` | Một nguồn cấu hình public key được chấp nhận cho tài khoản đích | Máy, tài khoản đích, đường dẫn, tùy chọn đi kèm từng bản ghi |
| SSH host key | Giúp client xác thực danh tính máy chủ | Máy hoặc endpoint, fingerprint host key, nguồn xác minh và vòng đời |
| `known_hosts` | Điểm tin cậy phía client đối với máy chủ hoặc host CA | Phạm vi client, endpoint và chính sách quản lý trust |
| SSH user certificate | Public key được CA ký với thuộc tính và thời hạn | CA, serial, key ID, principals, thời hạn, ràng buộc và nguồn cấp |
| SSH agent | Cung cấp khả năng ký cho client bằng khóa đang được nạp hoặc được thiết bị hỗ trợ | Thiết bị, phiên, chính sách forwarding; đây không phải danh mục toàn hệ thống |

Public key không phải bí mật tương đương private key, nhưng danh mục public key vẫn tiết lộ cấu trúc tài khoản, hệ thống quan trọng và quan hệ truy cập. Chỉ cấp quyền đọc inventory theo nhu cầu công việc.

### 3.1. Public key không tự mang đầy đủ quyền truy cập

Một public key có thể được chấp nhận dưới tài khoản `deploy` trên máy A và tài khoản `root` trên máy B. Quyền sau đăng nhập còn phụ thuộc `sudo`, nhóm, ACL, lệnh cưỡng chế và cấu hình dịch vụ.

Vì vậy, không thể gắn một nhãn duy nhất như “read-only” cho toàn bộ khóa rồi dùng nhãn đó cho mọi nơi. Quyền phải được mô tả trên từng quan hệ giữa khóa và đích.

### 3.2. Host key khác user key

Khóa của máy chủ trả lời câu hỏi “Tôi đang kết nối đúng máy không?”. Khóa của người dùng hoặc workload trả lời câu hỏi “Chủ thể này có được xác thực vào tài khoản đích không?”.

Hai nhóm đều có thể nằm trong chương trình quản lý SSH key, nhưng phải có loại đối tượng riêng. Không tính host key vào số lượng khóa người dùng đặc quyền.

### 3.3. Có certificate không có nghĩa đã hết việc kiểm kê

Khi máy chủ tin một user CA, không nhất thiết tồn tại một dòng cho mỗi public key người dùng trong `authorized_keys`. Quyền có thể đến từ CA được tin cậy, principals được cho phép và các giới hạn của certificate.

Inventory phải theo dõi cả **cơ chế cấp quyền**, thay vì chỉ quét file public key.

## 4. Phạm vi và đơn vị kiểm kê

Trước khi thu thập, xác định rõ phạm vi được phép: môi trường, nhóm máy, tài khoản, nguồn cấu hình, điểm quản trị PAM và nguồn log. Không tự mở rộng sang mạng hoặc tài khoản ngoài nhiệm vụ.

Nên tách ít nhất bốn loại bản ghi:

1. **Chủ thể:** nhân viên, nhà thầu, tài khoản máy, service hoặc workload.
2. **Khóa:** public key đã được nhận diện, có định danh và vòng đời riêng.
3. **Quan hệ cấp quyền:** một khóa hoặc cơ chế certificate được phép xác thực vào tài khoản tại một đích.
4. **Bằng chứng quan sát:** dữ liệu nào chứng minh bản ghi, thu thập từ đâu, lúc nào và còn giới hạn gì.

Một khóa được cấp vào 50 máy vẫn có thể là một bản ghi khóa nhưng có 50 quan hệ cấp quyền. Nếu cùng khóa được lặp hai lần trong một file, cần giữ dấu vết hai lần xuất hiện để sửa cấu hình; không tự kết luận đó là hai khóa khác nhau.

~~~mermaid
flowchart LR
    S["Người hoặc workload"] -->|sử dụng| K["Public key / fingerprint"]
    K --> G1["Grant: bastion / ops"]
    K --> G2["Grant: app-prod-01 / deploy"]
    G1 --> R1["Quyền vận hành được phê duyệt"]
    G2 --> R2["Forced command và quyền sau đăng nhập"]
    E["Cấu hình, nguồn quản lý, log"] -. bằng chứng .-> G1
    E -. bằng chứng .-> G2
~~~

Sơ đồ cho thấy một khóa có nhiều grant. Thu hồi khóa phải xử lý tất cả grant liên quan trong phạm vi, chứ không chỉ sửa một dòng trong vault.

## 5. Thiết kế dữ liệu inventory

### 5.1. Bản ghi khóa

Các trường sau là một mô hình tham khảo, không phải schema bắt buộc của OpenSSH.

| Trường | Ý nghĩa |
|---|---|
| `key_id` | Mã nội bộ ổn định, không dùng comment làm định danh |
| `fingerprint_sha256` | Fingerprint do công cụ SSH tính từ public key |
| `key_type`, `key_size` | Loại khóa và thông số phù hợp với loại đó |
| `subject_type` | Human, workload, break-glass hoặc loại đã quy ước |
| `owner_id` | Định danh chủ sở hữu đã đối soát với nguồn quản trị danh tính |
| `accountable_team` | Nhóm chịu trách nhiệm khắc phục khi owner vắng mặt |
| `custody_type` | Ví dụ thiết bị bảo mật, agent, nền tảng CI hoặc vault |
| `custody_reference` | Mã tham chiếu được kiểm soát, không chứa bí mật hay token truy cập |
| `first_observed_at` | Thời điểm inventory lần đầu nhìn thấy khóa |
| `created_at` | Chỉ ghi nếu có nguồn tạo khóa đáng tin cậy |
| `review_due_at` | Mốc phải xác nhận lại nhu cầu sử dụng |
| `lifecycle_state` | Candidate, active, retirement-pending, retired hoặc trạng thái nội bộ |
| `owner_verification` | Ai xác nhận owner, qua quy trình nào, lúc nào |
| `evidence_ids` | Các bằng chứng liên quan |

`first_observed_at` không phải ngày tạo khóa. Thời gian sửa file có thể thay đổi khi copy hoặc triển khai lại, nên không dùng nó làm bằng chứng chắc chắn về tuổi khóa.

Một owner được điền đầy đủ vẫn có thể sai. Trường “đã xác minh” cần nguồn đối soát hoặc xác nhận có trách nhiệm, không chỉ là tên suy ra từ comment.

### 5.2. Bản ghi grant

| Trường | Ý nghĩa |
|---|---|
| `grant_id` | Định danh riêng cho quan hệ cấp quyền |
| `key_id` hoặc `trust_policy_id` | Khóa trực tiếp hoặc chính sách tin certificate |
| `asset_id`, `environment` | Tài sản chuẩn hóa và môi trường |
| `endpoint`, `port` | Điểm kết nối quan sát được; hỗ trợ máy có nhiều SSH instance |
| `target_account` | Tài khoản đích trên máy chủ |
| `authorization_source` | File, lệnh tra cứu, thư mục định danh, cấu hình CA hoặc nguồn khác |
| `source_reference` | Tham chiếu nơi cấu hình và vị trí bản ghi |
| `effective_options` | Các tùy chọn hạn chế trên bản ghi cấp quyền |
| `privilege_summary` | Quyền trực tiếp và khả năng nâng quyền đã xác minh |
| `approved_access_path` | Bastion/PAM hoặc tuyến truy cập được phép |
| `approval_reference` | Ticket, quyết định hoặc chính sách phê duyệt |
| `valid_until` | Thời điểm cần kết thúc quyền theo chính sách |
| `last_observed_use` | Lần dùng gần nhất có bằng chứng trong cửa sổ log đã nêu |
| `observed_at`, `collector_id` | Thời gian và nguồn thu thập |
| `review_state` | Trạng thái rà soát và người xử lý |

Phân biệt `valid_until` trong inventory với thời hạn được hệ thống thực thi. Điền ngày hết hạn trong cơ sở dữ liệu quản trị không tự làm một dòng public key tĩnh ngừng hoạt động.

Nếu dùng tùy chọn hết hạn của OpenSSH, phải kiểm tra phiên bản hỗ trợ, cú pháp, đồng hồ hệ thống và bằng chứng cấu hình được áp dụng. Certificate có thời hạn được ký cũng cần được kiểm tra theo cấu hình xác thực thực tế.

### 5.3. Ví dụ một bản ghi rút gọn

~~~yaml
key:
  key_id: KEY-0042
  fingerprint_sha256: "<fingerprint SHA256 đầy đủ do ssh-keygen trả về>"
  subject_type: workload
  owner_id: svc-release-prod
  accountable_team: platform-release
  custody_type: managed-ci-secret-store
  custody_reference: ci-secret-record-184
  owner_verification: "IAM-REVIEW-2026-014"
  lifecycle_state: active

grant:
  grant_id: SSH-GRANT-0087
  key_id: KEY-0042
  asset_id: app-prod-01
  environment: production
  endpoint: app-prod-01.internal
  port: 22
  target_account: deploy
  authorization_source: authorized_keys
  source_reference: "/home/deploy/.ssh/authorized_keys; observed-entry=3"
  effective_options:
    - 'from="10.20.30.40/32"'
    - 'command="/usr/local/sbin/release-entrypoint"'
    - no-agent-forwarding
    - no-port-forwarding
    - no-pty
    - no-user-rc
    - no-X11-forwarding
  privilege_summary: "Chỉ chạy entrypoint đã được rà soát; chưa xác nhận quyền sudo"
  approval_reference: CHG-1842
  valid_until: "<mốc quản trị; cần cơ chế thu hồi riêng>"
  review_state: needs-privilege-verification
~~~

Đây là dữ liệu minh họa, không phải file cấu hình có thể triển khai. Các tùy chọn xuất hiện không chứng minh lệnh wrapper an toàn: vẫn phải kiểm tra quyền sửa script, cách xử lý đầu vào và quyền nâng cao của tài khoản đích.

## 6. Fingerprint: nền tảng để đối soát khóa

### 6.1. Không dùng tên file hoặc comment làm khóa chính

Các tên như `id_ed25519.pub`, `deploy-prod.pub` hay comment `alice@laptop` có thể thay đổi. Một khóa có thể được copy sang nhiều file với comment khác nhau. Ngược lại, cùng comment có thể được dùng cho nhiều khóa.

Dùng fingerprint theo cùng quy ước để so sánh:

~~~bash
ssh-keygen -lf /path/to/approved-user-key.pub -E sha256
~~~

Ví dụ hình thức đầu ra:

~~~text
256 SHA256:<giá-trị-fingerprint-đầy-đủ> alice@workstation (ED25519)
~~~

Lưu fingerprint đầy đủ, không cắt ngắn để làm định danh trong hệ thống. Phần comment chỉ là dữ liệu do người tạo hoặc người sửa file cung cấp.

Fingerprint SSH không phải SHA-256 của toàn bộ file văn bản. Nếu tính hash trực tiếp trên file, đổi khoảng trắng, xuống dòng hoặc comment có thể làm hash file thay đổi dù public key vẫn là cùng một khóa. Hash file hữu ích để bảo vệ tính toàn vẹn bằng chứng, nhưng phải lưu riêng với fingerprint public key.

### 6.2. Đọc file cấp quyền có nhiều dòng

Với file theo định dạng OpenSSH mà công cụ hỗ trợ:

~~~bash
ssh-keygen -lf /home/deploy/.ssh/authorized_keys -E sha256
~~~

Lệnh này giúp lấy fingerprint, nhưng không thay thế việc phân tích từng bản ghi và tùy chọn. Nếu công cụ báo lỗi, phải ghi nhận lỗi và vị trí cần kiểm tra; không được biến lỗi đọc thành kết luận “không có khóa”.

Một dòng `authorized_keys` có thể có dạng:

~~~text
from="10.20.30.40/32",command="/usr/local/sbin/release-entrypoint",no-agent-forwarding,no-port-forwarding,no-pty ssh-ed25519 <PUBLIC_KEY_BASE64> release-job
~~~

Không tách dòng bằng khoảng trắng một cách đơn giản để lấy cột cố định, vì phần option có thể chứa chuỗi được đặt trong dấu nháy. Không dùng `eval` hoặc chạy phần `command=` khi phân tích dữ liệu. Trong công cụ thu thập thực tế, cần parser phù hợp định dạng, có kiểm tra đầu vào và giữ nguyên bằng chứng gốc trong kho được bảo vệ.

Giá trị `<PUBLIC_KEY_BASE64>` ở trên là placeholder, không phải một public key hợp lệ.

### 6.3. Đối với certificate

Có thể đọc thuộc tính certificate công khai bằng:

~~~bash
ssh-keygen -Lf /path/to/user-cert.pub
~~~

Ghi nhận ít nhất loại certificate, khóa công khai liên quan, CA ký, serial, key ID, principals, thời gian hiệu lực, critical options và extensions. Key ID là nhãn do bên cấp đặt; nó không tự bảo đảm ánh xạ chính xác đến nhân sự.

Định danh sự kiện cấp certificate nên bao gồm CA và thông tin phát hành, không chỉ serial đơn lẻ. Quy trình CA cần bảo đảm quy ước serial và khả năng truy nguyên. Một certificate đã hết hạn không chứng minh mọi đường public key tĩnh của cùng người đã được loại bỏ.

## 7. Thu thập inventory theo nhiều nguồn

### 7.1. Bắt đầu từ danh mục tài sản và nguồn quản lý

Lấy phạm vi máy từ nguồn quản lý tài sản được chấp thuận, thay vì quét ngẫu nhiên cả mạng. Đối chiếu ít nhất:

- Hệ thống PAM và bastion: đích được quản lý, tài khoản, cơ chế đưa khóa hoặc certificate vào phiên.
- Công cụ cấu hình: template và khai báo public key được triển khai.
- Hệ thống IAM: chủ thể đang hoạt động, đã nghỉ việc hoặc hết hạn hợp đồng.
- Nền tảng CI/CD: workload giữ khóa, môi trường triển khai và nhóm sở hữu.
- Cấu hình thực tế trên đích: quyền đang được chấp nhận có khớp khai báo không.
- Nguồn log: bằng chứng sử dụng và phần thời gian có thể quan sát.

Nguồn khai báo trả lời “đáng lẽ nên có gì”; cấu hình thực tế trả lời “đang có gì”. Hai dữ liệu này cần đối soát, không thay thế nhau.

### 7.2. Kiểm tra cấu hình SSH có hiệu lực

Không giả định mọi hệ thống đều dùng `~/.ssh/authorized_keys`. Các cấu hình như `AuthorizedKeysFile`, `AuthorizedKeysCommand`, `TrustedUserCAKeys`, `AuthorizedPrincipalsFile` và cơ chế tra cứu principals có thể làm thay đổi nguồn cấp quyền.

Ví dụ kiểm tra cấu hình bằng OpenSSH trong bối cảnh thử nghiệm đã được cho phép:

~~~bash
sudo /usr/sbin/sshd -T \
  -C user=deploy,host=runner.example.internal,addr=10.20.30.40,laddr=10.50.0.12,lport=22
~~~

Các giá trị trong `-C` là ngữ cảnh kết nối để đánh giá cấu hình, không phải một lần đăng nhập và không chứng minh kết nối đã thành công. `host` ở đây là thông tin host phía kết nối theo ngữ cảnh đánh giá, không phải tên tài sản đích trong inventory.

Nếu instance đang chạy dùng file cấu hình riêng hoặc tùy chọn khởi động khác, phải kiểm tra đúng cấu hình đó. Một kết quả `sshd -T` theo mặc định không tự đại diện cho mọi instance hoặc mọi khối `Match`.

Tránh bỏ sót:

- File cấu hình được include.
- Tài khoản và nguồn địa chỉ chịu các khối `Match` khác nhau.
- Nhiều dịch vụ SSH, port hoặc container trên cùng máy.
- Nguồn cấp quyền từ thư mục định danh, hệ thống quản trị tập trung hoặc chương trình tra cứu.
- Sự khác nhau giữa cấu hình trên đĩa và cấu hình mà tiến trình hiện tại đã nạp.

Việc xem cấu hình không yêu cầu reload dịch vụ. Mọi thay đổi cấu hình thuộc quy trình thay đổi riêng.

### 7.3. Xác định tài khoản và home directory đúng nguồn

Không chỉ liệt kê `/home/*`. Tài khoản root, tài khoản service và tài khoản từ NSS/LDAP có thể có home ở vị trí khác. Trong môi trường Linux được phép truy vấn, có thể bắt đầu bằng:

~~~bash
getent passwd
~~~

Kết quả phụ thuộc nguồn định danh và khả năng liệt kê của hệ thống. Với thư mục không cho phép enumerate toàn bộ người dùng, phải phối hợp nguồn quản trị danh tính để xây dựng danh sách tài khoản đích. Không có trong đầu ra liệt kê không đủ để kết luận tài khoản không tồn tại.

Thu thập theo danh sách tài khoản và đường dẫn đã xác định từ cấu hình có hiệu lực. Ghi nhận cả trường hợp thiếu quyền đọc, file không tồn tại, đường dẫn không chuẩn hoặc nguồn tra cứu không truy cập được.

### 7.4. Giữ việc khám phá ở chế độ đọc

Không thử dùng từng khóa để đăng nhập hàng loạt nhằm “xác nhận inventory”. Cách đó có thể kích hoạt cảnh báo, tác động giới hạn kết nối và đòi hỏi khả năng dùng private key ngoài phạm vi thu thập.

Không gom file private key về một thư mục trung tâm. Inventory chỉ cần public metadata và tham chiếu có kiểm soát đến nơi bảo quản. Nếu tìm thấy private key ngoài vị trí được phê duyệt, ghi nhận vị trí và chuyển theo quy trình xử lý phù hợp; không đưa giá trị khóa vào ticket, terminal dùng chung hay báo cáo.

Một collector tốt cần trả về cả dữ liệu và trạng thái:

~~~text
asset=app-prod-01
account=deploy
source=authorized_keys
collection_state=success
observed_entries=2
observed_at=<thời-gian-UTC>

asset=legacy-db-01
account=root
source=authorized_keys
collection_state=permission_denied
observed_entries=unknown
observed_at=<thời-gian-UTC>
~~~

`unknown` khác `0`. Nếu hệ thống chưa quan sát được, không được tính như đã xác nhận không có khóa.

## 8. Các điểm cần kiểm kê ngoài authorized_keys

### 8.1. AuthorizedKeysCommand và nguồn tập trung

Một chương trình tra cứu có thể lấy public key từ hệ thống IAM hoặc kho quản trị. Inventory cần xác định nguồn dữ liệu, cách ánh xạ user, cơ chế cache, người có quyền sửa nguồn và thời gian để thay đổi có hiệu lực.

Không tự thực thi chương trình tra cứu dưới tài khoản đặc quyền chỉ để xem kết quả. Sử dụng giao diện được phê duyệt hoặc phương thức thu thập đã được chủ hệ thống xác nhận.

Đặc biệt cần kiểm tra tình huống nguồn tập trung đã thu hồi nhưng một file local vẫn chấp nhận public key. Thu hồi ở một nguồn không đồng nghĩa tất cả nguồn khác đã từ chối.

### 8.2. User CA và principals

Khi dùng certificate, tạo bản ghi chính sách trust chứa:

- Public CA được tin cậy và fingerprint tương ứng.
- Tập máy hoặc tài khoản tin CA đó.
- Nguồn principals được cho phép và logic ánh xạ.
- Quy trình phê duyệt cấp certificate, thời hạn và ràng buộc.
- Khả năng truy xuất lịch sử phát hành.
- Cơ chế thu hồi, ví dụ nguồn `RevokedKeys` hoặc KRL nếu hệ thống sử dụng.
- Tình trạng phân phối dữ liệu thu hồi tới các đích.

CA public key được tin cậy không đủ để kết luận bất kỳ certificate nào do CA ký đều đăng nhập được: loại certificate, principals, thời hạn, tùy chọn, chính sách tài khoản và các điều kiện khác vẫn ảnh hưởng quyết định.

### 8.3. Bastion, proxy và agent forwarding

Ghi nhận cả hai chặng nếu phiên đi qua bastion: người dùng tới bastion và bastion hoặc client tới máy đích. Một fingerprint xuất hiện trong log bastion chưa chắc là fingerprint mà máy đích nhìn thấy.

`ProxyJump` không mặc nhiên có nghĩa private key phải được lưu trên bastion. Ngược lại, agent forwarding không nhất thiết copy private key lên máy trung gian, nhưng có thể cho phía có quyền truy cập agent socket sử dụng khả năng ký trong thời gian liên quan.

Inventory cần thể hiện việc forwarding có được phép, tại đâu và với điều kiện nào. Không dùng cách diễn đạt “không copy private key nên không có rủi ro”.

### 8.4. Nền tảng CI/CD và workload

Một SSH key trong CI có thể chỉ kéo mã nguồn, triển khai ứng dụng hoặc chạy lệnh bảo trì có đặc quyền. Phải kiểm kê theo quyền thực tế trên đích, không theo tên secret hay tên pipeline.

Đối với khóa dùng chung cho nhiều job, ghi nhận tất cả workload liên quan và mức khó khăn khi thu hồi. Một owner là “DevOps” quá chung chung sẽ làm chậm xử lý sự cố; cần nhóm chịu trách nhiệm và định danh workload cụ thể.

## 9. Đối soát danh tính, quyền và bằng chứng sử dụng

### 9.1. Xác minh owner bằng nhiều nguồn

Có thể bắt đầu từ hệ thống cấp khóa, nguồn cấu hình và hệ thống IAM. Sau đó yêu cầu owner hoặc nhóm chịu trách nhiệm xác nhận nhu cầu và mục đích hiện tại.

Không coi những điều sau là bằng chứng đủ:

- Comment chứa email.
- Tên file chứa tên nhân viên.
- File nằm trong home directory của một người.
- Người cuối cùng sửa template là owner của mọi khóa trong template.

Nếu chưa xác minh được, lưu `owner_verification=pending` và giữ phát hiện “chưa rõ chủ”. Đừng gán tạm một người rồi làm biến mất vấn đề.

Khóa được dùng chung bởi nhiều người làm suy giảm khả năng quy trách nhiệm. Khi chưa thể thay thế ngay, phải mô tả việc dùng chung và cơ chế bù đắp; không ghi nhận như khóa cá nhân đã được quản lý tốt.

### 9.2. Xác định đặc quyền theo ngữ cảnh

Tài khoản đích không phải root vẫn có thể quản trị toàn hệ thống qua `sudo`, quyền sửa unit service, quyền truy cập runtime container hoặc nhóm có đặc quyền cao. Ngược lại, một bản ghi bị cưỡng chế chạy lệnh có thể chỉ cho phép thao tác hẹp.

Inventory nên phân biệt:

- Quyền xác thực được quan sát.
- Quyền sau đăng nhập đã được xác minh.
- Khả năng nâng quyền cần được kiểm tra thêm.
- Kết luận dựa trên chính sách hay dựa trên bằng chứng kỹ thuật.

Không tự gắn “least privilege” chỉ vì tên tài khoản là `deploy` hoặc `readonly`.

### 9.3. Diễn giải last-used đúng giới hạn

Log có thể cung cấp tài khoản đích, thời gian, nguồn kết nối và fingerprint tùy cấu hình. Cần đối soát log ở đúng chặng, múi giờ, thời gian lưu và mức chi tiết đang bật.

Mỗi giá trị `last_observed_use` phải có cửa sổ quan sát. Ví dụ:

~~~text
last_observed_use: không tìm thấy
observation_window: 30 ngày
coverage: log đầy đủ cho 27/30 ngày
meaning: chưa có bằng chứng sử dụng trong phần dữ liệu hiện có
~~~

Không biến thông tin này thành “khóa chưa từng dùng”. Một job khôi phục chạy theo quý có thể hợp lệ dù không xuất hiện trong log tháng gần nhất. Quyết định thu hồi cần kết hợp owner, mục đích, mức rủi ro và quy trình thay đổi.

## 10. Quy trình kiểm kê và xử lý phát hiện

### Bước 1 — Chốt phạm vi và quyền thu thập

Xác định tài sản, môi trường, loại tài khoản, nguồn cấp quyền, dữ liệu được phép lấy và người xử lý lỗi truy cập. Đặt chuẩn thời gian và định danh tài sản trước khi hợp nhất dữ liệu.

### Bước 2 — Thu thập khai báo và quan sát thực tế

Thu thập từ PAM, cấu hình tập trung và máy đích. Ghi nhận phiên bản hoặc revision của nguồn quản lý nếu có, thời gian quan sát và trạng thái thành công hoặc lỗi.

Không sửa cấu hình trong bước thu thập để làm dữ liệu “đẹp” hơn.

### Bước 3 — Chuẩn hóa và khử trùng lặp

Dùng fingerprint thống nhất để nhận ra cùng public key; vẫn giữ riêng từng lần xuất hiện và grant. Chuẩn hóa tài khoản, tài sản và thời gian. Đưa các dòng không parse được vào hàng đợi kiểm tra, không âm thầm bỏ qua.

### Bước 4 — Đối soát owner và nhu cầu

So sánh với IAM, danh mục workload và phê duyệt. Mỗi grant cần mục đích hiện tại, người chịu trách nhiệm và mốc rà soát. Đánh dấu quyền không có phê duyệt hoặc chủ thể đã hết hiệu lực.

### Bước 5 — Phân tích rủi ro theo grant

Ưu tiên theo đặc quyền, độ nhạy cảm tài sản, phạm vi dùng lại, khả năng đi ngoài PAM và mức thiếu bằng chứng. Cùng một khóa có thể có grant rủi ro cao và grant hợp lệ ở nơi khác.

### Bước 6 — Giao xử lý theo quy trình thay đổi

Tạo việc thu hồi, chuyển owner, tách khóa workload, đưa vào quản lý tập trung hoặc chuyển sang certificate/JIT. Thông tin cần có gồm phạm vi, phụ thuộc, người thực hiện, thời gian, tiêu chí thành công và phương án khôi phục được phê duyệt.

### Bước 7 — Xác nhận sau thay đổi

Thu thập lại từ đúng nguồn cấp quyền, đối chiếu các bản ghi bị loại bỏ và kiểm tra tác vụ nghiệp vụ theo kế hoạch. Không chỉ dựa vào trạng thái “đã đóng ticket”.

Đối với public key tĩnh, việc xóa grant ngăn xác thực mới tại nguồn đó khi thay đổi có hiệu lực; không tự chấm dứt phiên đã mở. Nếu xử lý sự cố, việc kiểm tra và kết thúc phiên cần nhiệm vụ riêng.

### Bước 8 — Duy trì inventory

Kết hợp khám phá định kỳ với sự kiện cấp quyền, đổi owner, nhân sự nghỉ việc, thay đổi pipeline, thêm máy và thu hồi. Xác định tần suất theo rủi ro và tốc độ thay đổi của môi trường.

Snapshot được xác nhận hôm qua không bảo đảm không có grant mới được thêm hôm nay. Inventory cần có tuổi dữ liệu và khả năng phát hiện drift.

## 11. Phân loại các phát hiện điển hình

| Phát hiện | Ý nghĩa cần kiểm tra | Hướng xử lý |
|---|---|---|
| Không rõ owner | Không xác định được người chịu trách nhiệm và nhu cầu hiện tại | Đối soát nguồn cấp, đặt hạn xác minh và xử lý theo mức rủi ro |
| Owner đã nghỉ việc | Có thể còn quyền của chủ thể đã hết hiệu lực | Ưu tiên xác minh và thu hồi đầy đủ grant liên quan |
| Một khóa dùng ở nhiều môi trường | Phạm vi ảnh hưởng khi lộ khóa có thể lớn | Tách danh tính hoặc khóa theo phạm vi phù hợp |
| Khóa người dùng được dùng bởi service | Vòng đời workload phụ thuộc tài khoản cá nhân | Chuyển sang danh tính workload có owner và quy trình riêng |
| Grant vào root | Có đặc quyền trực tiếp, khó áp dụng phân tách tác vụ | Rà soát nhu cầu, mô hình tài khoản cá nhân và nâng quyền có kiểm soát |
| Grant không có trong PAM | Có thể có đường truy cập chưa được quản lý | Đối soát nguồn, tuyến truy cập và chính sách phê duyệt |
| Không thấy dùng gần đây | Có thể thừa quyền hoặc là tác vụ ít chạy | Xác nhận nghiệp vụ và giới hạn log trước khi quyết định |
| Đã xóa khai báo nhưng đích còn khóa | Có drift hoặc lỗi triển khai | Xác định nguồn thực sự quản lý và sửa quy trình đồng bộ |
| Nguồn thu thập bị từ chối quyền | Chưa biết quyền thực tế ở đích | Giao bổ sung quyền đọc hoặc phương thức quan sát hợp lệ |
| Dòng không parse được | Dữ liệu chưa được diễn giải đầy đủ | Kiểm tra định dạng và collector, giữ lại bằng chứng |

Loại khóa và kích thước khóa là dữ liệu cần có để đối chiếu chính sách mật mã. Không đồng nhất tên public key `ssh-rsa` với mọi tình huống dùng chữ ký RSA/SHA-1: thuật toán khóa và thuật toán chữ ký được sử dụng là hai khía cạnh cần phân biệt. Kết luận tuân thủ phải dựa trên chính sách và cấu hình thực tế, không chỉ tên trong file.

## 12. Tình huống thực hành: một khóa xuất hiện ở ba đích

Một đợt thu thập trong phạm vi production cho kết quả sau. Các nhãn `FP-A` và `FP-B` là ký hiệu minh họa thay cho fingerprint đầy đủ.

| Fingerprint | Đích / tài khoản | Bằng chứng owner | Ghi chú |
|---|---|---|---|
| FP-A | bastion-01 / an.nguyen | IAM xác nhận đang làm việc | Phê duyệt vận hành còn hiệu lực |
| FP-A | db-prod-01 / root | Comment ghi tên An | Không thấy grant tương ứng trong PAM |
| FP-A | app-prod-01 / deploy | Chưa xác minh | Pipeline được cho là đang dùng khóa này |
| FP-B | app-prod-02 / deploy | Workload release-prod được xác nhận | Không có log dùng trong 30 ngày |

### 12.1. Đếm đúng đối tượng

Có hai public key được nhận diện và bốn grant được quan sát. FP-A cần một bản ghi khóa với ba quan hệ cấp quyền, không phải ba khóa độc lập.

Trạng thái owner của FP-A chưa hoàn toàn rõ: việc An sở hữu một bản public key không chứng minh pipeline không có bản private key tương ứng. Cần xác minh custody và khả năng dùng chung.

### 12.2. Xử lý ưu tiên

Grant `db-prod-01 / root` cần được ưu tiên vì đặc quyền trực tiếp và chưa đối soát được với PAM. Tuy nhiên, chưa đủ bằng chứng để kết luận có xâm nhập. Nhóm vận hành phải xác nhận nguồn cấp quyền, nhu cầu, lịch sử sử dụng và chính sách trước khi thực hiện thay đổi phù hợp.

Grant `app-prod-01 / deploy` cho thấy nguy cơ dùng khóa cá nhân cho workload. Xác minh nơi giữ khóa và phụ thuộc pipeline, sau đó chuẩn bị danh tính workload riêng và kế hoạch chuyển đổi.

FP-B không được tự động xóa chỉ vì không có log trong 30 ngày. Có thể đây là pipeline theo lịch dài hoặc log chưa đủ. Owner cần xác nhận nhu cầu và lịch chạy.

### 12.3. Khi FP-A được báo lộ

Dùng inventory truy xuất đủ ba grant cùng các nguồn cấu hình liên quan. Phối hợp thu hồi hoặc thay thế tại tất cả nguồn, cập nhật cấu hình quản lý tập trung, rà soát phiên đang mở và thu thập bằng chứng sau thay đổi.

Nếu chỉ bỏ FP-A khỏi bastion nhưng giữ trên máy đích, quyền cấu hình vẫn tồn tại. Nếu chỉ sửa máy đích mà không sửa template, lần triển khai tiếp theo có thể thêm khóa trở lại.

## 13. Chỉ số và tiêu chí hoàn thành

Một vòng kiểm kê hoàn thành khi phạm vi và phần thiếu quan sát được mô tả rõ, không phải khi báo cáo có nhiều dòng.

Có thể theo dõi các chỉ số sau với mẫu số và cửa sổ thời gian cụ thể:

| Chỉ số | Cách hiểu |
|---|---|
| Độ phủ thu thập tài sản | Tài sản thu thập thành công / tài sản trong phạm vi |
| Độ phủ nguồn cấp quyền | Nguồn đã quan sát / nguồn được xác định cần quan sát |
| Tỷ lệ grant có owner được xác minh | Grant có owner và bằng chứng hợp lệ / grant đã quan sát |
| Tỷ lệ grant có phê duyệt | Grant đối soát được quyết định cho phép / grant đã quan sát |
| Grant ngoài chính sách | Số grant vi phạm đã xác nhận, phân theo mức rủi ro |
| Tuổi snapshot | Khoảng thời gian từ lần quan sát gần nhất đến thời điểm báo cáo |
| Thời gian xử lý phát hiện | Từ lúc xác nhận phát hiện đến lúc có bằng chứng khắc phục |

Tỷ lệ owner 100% trên 40% số máy không có nghĩa đã kiểm kê đầy đủ. Luôn đặt số lượng chưa thu thập, lỗi đọc và dòng chưa parse cạnh số liệu tổng hợp.

Bộ bằng chứng tối thiểu nên đủ để trả lời: phạm vi là gì, ai thu thập, lúc nào, nguồn nào, định danh khóa ra sao, grant nào, owner được xác minh bằng gì, phát hiện nào đang mở và thay đổi nào đã được xác nhận.

Kho bằng chứng cần có quyền truy cập phù hợp, bảo vệ tính toàn vẹn và thời gian lưu theo chính sách. Báo cáo phổ thông có thể chỉ hiển thị ID và fingerprint; dữ liệu cấu hình chi tiết được đặt ở nguồn có kiểm soát.

## 14. Bài tập tự thực hành

Dùng dữ liệu giả lập, không dùng private key thật hoặc thông tin production.

1. Tạo một bảng khóa với hai fingerprint mẫu, một owner cá nhân và một owner workload.
2. Tạo bốn grant, trong đó một grant vào root, một grant chưa rõ owner và một grant có forced command.
3. Ghi riêng nguồn bằng chứng, thời gian quan sát và cửa sổ log.
4. Thêm một tài sản không đọc được cấu hình. Bảo đảm báo cáo thể hiện “chưa biết”, không hiển thị “không có khóa”.
5. Lập danh sách công việc xử lý, chỉ rõ owner, phạm vi thay đổi và bằng chứng cần có sau thay đổi.
6. Mô phỏng một khóa bị lộ và truy xuất mọi grant cần xử lý.
7. Kiểm tra rằng số khóa duy nhất khác với số grant và số dòng cấu hình.

Sản phẩm đạt yêu cầu khi người khác có thể dùng bảng của bạn để xác định phạm vi thu hồi mà không phải đoán owner từ comment hoặc đoán tài khoản từ tên file.

## 15. Câu hỏi tự kiểm tra

**Vì sao đếm file `.pub` không đủ để kiểm kê quyền SSH?**

Public key có thể được copy, quyền có thể đến từ nguồn tra cứu hoặc CA, và file phía client không cho biết đầy đủ đích chấp nhận khóa. Cần kiểm kê cả quan hệ cấp quyền tại nguồn có hiệu lực.

**Một fingerprint xuất hiện trên mười máy có nghĩa có mười khóa không?**

Không. Có thể là một public key với mười hoặc nhiều hơn mười grant, tùy tài khoản và nguồn cấp quyền trên từng máy.

**Có thể xác nhận owner từ comment trong public key không?**

Không đủ. Comment là nhãn có thể sửa; cần đối soát nguồn cấp khóa, IAM hoặc xác nhận có trách nhiệm.

**Nếu đã ghi ngày hết hạn trong inventory, grant có tự bị thu hồi không?**

Không. Phải có cơ chế thực thi và bằng chứng áp dụng, chẳng hạn thu hồi grant, cơ chế certificate hoặc tính năng được hỗ trợ và cấu hình đúng.

**Không thấy fingerprint trong log có chứng minh khóa không còn dùng không?**

Không. Cần xem cửa sổ và độ phủ log, cấu hình ghi nhận, chặng kết nối và lịch hoạt động của workload.

**Thu hồi khóa khỏi vault có đủ không?**

Không đủ để kết luận đã hết quyền. Cần xử lý các điểm tin cậy và nguồn cấp quyền trên đích, nguồn triển khai có thể tái thêm khóa, cùng các phiên hoặc khả năng sử dụng còn liên quan.

**Một snapshot inventory tốt cần thể hiện điều gì ngoài các khóa đã tìm thấy?**

Phạm vi, thời gian, nguồn bằng chứng, owner, grant, lỗi thu thập, phần chưa biết và công việc khắc phục còn mở.

## 16. Kết quả cần đạt trong PAM

SSH key inventory cung cấp bản đồ từ **chủ thể → khóa hoặc chính sách certificate → quan hệ cấp quyền → đặc quyền trên tài sản**. Giá trị của bản đồ nằm ở khả năng hành động: xác định đúng người chịu trách nhiệm, giảm quyền thừa, tìm đường truy cập ngoài kiểm soát và thu hồi đầy đủ khi cần.

Hãy duy trì fingerprint thống nhất, owner đã xác minh, grant tách riêng, bằng chứng có thời gian và trạng thái quan sát rõ ràng. Đó là dữ liệu đầu vào để triển khai vault, luân chuyển credential, JIT/JEA, giám sát phiên và kiểm toán một cách có căn cứ.

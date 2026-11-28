# Migrate SSH key

## 1. Mục tiêu của việc di chuyển SSH key vào PAM

Di chuyển SSH key trong một chương trình Privileged Access Management (PAM) là chuyển một quan hệ truy cập SSH sang cách quản lý có chủ sở hữu, chính sách cấp quyền, kiểm soát vật liệu khóa và bằng chứng sử dụng. Công việc này có thể bao gồm nhập khóa hiện hữu vào vault, thay khóa bằng một cặp khóa mới do quy trình PAM quản lý, hoặc chuyển sang chứng thư SSH có thời hạn.

Đích đến không chỉ là “đăng nhập được bằng khóa mới”. Sau migration, tổ chức cần trả lời được:

- Ai hoặc workload nào được dùng khóa để truy cập tài khoản nào, trên những máy nào?
- Yêu cầu truy cập được phê duyệt ở đâu, có giới hạn thời gian và phạm vi lệnh hay không?
- Private key được tạo, giữ, sử dụng và luân chuyển như thế nào?
- Những đường truy cập bằng khóa cũ đã được đóng ở đâu?
- Có thể truy vết một lần sử dụng về đúng người, workload, yêu cầu và phiên làm việc hay không?
- Nếu cutover lỗi, ai được phép rollback và bằng chứng nào chứng minh việc phục hồi an toàn?

Ví dụ xuyên suốt bài: một job triển khai tên `deploy-agent` dùng tài khoản `release` trên ba máy ứng dụng. Private key cũ nằm trên runner, public key được cài thủ công vào tài khoản đích. Mục tiêu là chuyển sang khóa do PAM quản lý, giữ nguyên nhu cầu triển khai đã được phê duyệt, loại bỏ bản private key cũ trên runner và ngăn khóa cũ mở kết nối SSH mới.

Migration không tự động cấp thêm quyền. Một khóa được lưu trong vault nhưng vẫn đăng nhập tài khoản đặc quyền không giới hạn từ mọi nơi chưa đáp ứng mục tiêu least privilege.

## 2. Hiểu chính xác đối tượng đang di chuyển

### 2.1. Cặp khóa người dùng và quan hệ tin cậy

Trong xác thực SSH bằng public key, client chứng minh mình có thể thực hiện thao tác ký bằng private key tương ứng. Server kiểm tra public key đó có được chấp nhận cho tài khoản đích theo cấu hình và chính sách hiện hành hay không. Private key không cần được gửi sang server đích để thực hiện xác thực SSH thông thường.

Có ba nhóm đối tượng cần phân biệt:

| Đối tượng | Vai trò | Ý nghĩa trong migration |
|---|---|---|
| Private key của người dùng hoặc workload | Dùng để ký trong quá trình xác thực | Vật liệu bí mật; phải kiểm soát nơi lưu và nơi thực hiện thao tác ký |
| Public key tương ứng | Định danh phía công khai của cặp khóa | Được đối chiếu với nguồn cấp quyền cho tài khoản đích |
| Quy tắc chấp nhận public key | Gắn khóa với tài khoản, nguồn truy cập và giới hạn sử dụng | Phải di chuyển và kiểm tra cùng khóa, không chỉ sao chép chuỗi public key |

Public key và quyền truy cập là hai khái niệm khác nhau. Biết fingerprint của một khóa không chứng minh khóa đó chỉ có một nơi sử dụng; cùng một public key có thể xuất hiện trên nhiều máy và nhiều tài khoản.

### 2.2. Không nhầm user key với host key

**User key** xác thực client hoặc workload đối với tài khoản trên server. **Host key** giúp client xác thực server mà nó đang kết nối.

Bài này tập trung di chuyển user key. Không lấy private host key của server nhập vào vault như một khóa đăng nhập người dùng. Nếu migration đồng thời đổi bastion, proxy hoặc đích kết nối, cần xử lý nhận diện host theo một công việc được xác định rõ: kiểm chứng fingerprint hoặc nguồn tin cậy, cập nhật cấu hình client có kiểm soát và lưu bằng chứng.

Không tắt kiểm tra host key để làm bài kiểm tra cutover thành công. Kết nối thành công tới một host chưa được xác thực không chứng minh migration an toàn.

### 2.3. Phân biệt khóa tĩnh với chứng thư SSH

Một chứng thư SSH của người dùng gắn public key với danh tính, thời hạn và các ràng buộc do một SSH certificate authority ký. Đây không phải chứng chỉ TLS/X.509.

Khi chuyển từ khóa tĩnh sang chứng thư SSH, phạm vi thay đổi còn bao gồm:

- Server tin cậy CA nào.
- Principal nào được chấp nhận cho tài khoản đích.
- Thời hạn và điều kiện cấp chứng thư.
- Cơ chế xử lý thu hồi, sự cố CA và độ lệch thời gian.
- Các nguồn tin cậy cũ còn cho phép khóa tĩnh đăng nhập hay không.

Chỉ cài CA mới mà vẫn để toàn bộ khóa tĩnh cũ được chấp nhận sẽ để lại đường truy cập ngoài vòng đời chứng thư.

## 3. Chọn mô hình đích trước khi chuyển khóa

Có thể gặp ba hướng migration. Lựa chọn phải dựa trên khả năng của nền tảng PAM, hệ thống SSH, chính sách mật mã và yêu cầu vận hành thực tế.

| Hướng | Cách thực hiện | Điểm phải kiểm chứng |
|---|---|---|
| Nhập private key hiện hữu | Đưa khóa đang dùng vào vùng quản lý được phê duyệt của PAM | Không tạo thêm bản sao ngoài kiểm soát; nhận diện và xử lý các bản sao cũ |
| Thay bằng cặp khóa mới | Tạo khóa mới, cài public key mới, chuyển client, sau đó thu hồi khóa cũ | Cả client lẫn server đã chuyển; khóa cũ bị từ chối trên toàn bộ phạm vi |
| Chuyển sang chứng thư SSH | Client dùng khóa và chứng thư do CA được server tin cậy cấp | Đúng principal, thời hạn, ràng buộc và cơ chế thu hồi; đường tĩnh cũ đã được xử lý |

Nhập khóa cũ có thể là một bước trung gian để kiểm kê và quản lý. Nó không xóa được rủi ro của những bản private key đã từng bị sao chép. Khi lịch sử phân phối không rõ, cần lập kế hoạch thay khóa thay vì coi việc nhập vault là bằng chứng rằng chỉ PAM còn sở hữu khóa.

Với ví dụ `deploy-agent`, nhóm chọn tạo cặp khóa mới cho workload. Public key mới được cấp quyền trên ba máy; private key được giữ trong thành phần quản lý bí mật đã chọn. Runner sử dụng một cơ chế được phê duyệt để yêu cầu thao tác SSH cho đúng job, thay vì gắn một private key dùng chung vào repository.

Mô hình đích phải mô tả nơi thực sự sử dụng private key:

1. PAM hoặc broker giữ khóa và thực hiện kết nối thay mặt người dùng.
2. Client được cấp quyền dùng một agent hoặc dịch vụ ký.
3. Workload nhận khóa qua một kênh cấp phát được kiểm soát và phải xử lý vòng đời bản sao tại runtime.

Ba cách này có rủi ro khác nhau. Không giả định mọi tích hợp PAM đều giữ private key hoàn toàn bên trong vault. Nếu runtime nhận private key, kế hoạch phải bao gồm quyền file, thời gian tồn tại, bộ nhớ hoặc ổ đĩa tạm, cleanup và cách tránh rò rỉ vào log.

## 4. Kiểm kê theo quan hệ truy cập

### 4.1. Lập danh sách cạnh, không chỉ danh sách file khóa

Đơn vị cần di chuyển là một quan hệ truy cập:

```text
Chủ sở hữu → Client/workload → Khóa hoặc chứng thư
            → Đường mạng/bastion → Host đích → Tài khoản đích → Quyền thực thi
```

Một file private key có thể được nhiều job sử dụng. Một tài khoản đích có thể tin cậy nhiều public key. Chỉ kiểm tra một máy thử nghiệm sẽ không phát hiện đầy đủ các phụ thuộc này.

Với mỗi quan hệ, ghi tối thiểu:

| Trường | Nội dung cần ghi |
|---|---|
| Chủ sở hữu | Nhóm chịu trách nhiệm, người phê duyệt và liên hệ khi lỗi |
| Danh tính sử dụng | Người dùng cụ thể hoặc workload cụ thể |
| Client | Runner, máy quản trị, container, thiết bị hoặc job sử dụng |
| Dấu định danh khóa | Fingerprint có ghi rõ cách biểu diễn, loại khóa và vị trí metadata |
| Đích | Mã tài sản/host và tài khoản SSH |
| Nguồn cấp quyền | File, dịch vụ tra cứu khóa, CA/principal hoặc nguồn cấu hình tương ứng |
| Giới hạn | Nguồn mạng, lệnh cưỡng bức, forwarding, thời gian và quyền hệ điều hành |
| Lịch sử sử dụng | Lần dùng gần nhất, chu kỳ job và bằng chứng quan sát |
| Phương án đích | Nhập khóa, thay khóa hoặc chứng thư SSH |
| Cutover/rollback | Cửa sổ thay đổi, người thực hiện và điều kiện kích hoạt |

Không đưa private key, passphrase hoặc credential mở vault vào bảng kiểm kê.

### 4.2. Fingerprint giúp đối chiếu, không thay thế kiểm kê quyền

Ví dụ sau chỉ đọc public key đã được thu thập hợp lệ:

```bash
ssh-keygen -lf /secure-inventory/deploy-agent-old.pub
```

Kết quả giúp đối chiếu cùng một khóa giữa các nguồn. Trường comment trong public key có thể hỗ trợ tra cứu nhưng không phải bằng chứng đáng tin cậy về chủ sở hữu: comment có thể tùy ý sửa, bỏ trống hoặc được sao chép từ một khóa khác.

Cũng cần xác định một public key trong nguồn cấu hình có thực sự đang có hiệu lực hay không. Một file đã cũ hoặc nằm ngoài đường dẫn được SSH server sử dụng không đủ chứng minh quyền hiện tại.

Không quét toàn bộ thư mục cá nhân rồi sao chép private key về một nơi để “kiểm kê”. Nếu cần phát hiện khóa, dùng phương pháp được phê duyệt, ưu tiên metadata, public key và cấu hình cấp quyền; xử lý nội dung bí mật theo quy trình riêng.

### 4.3. Tìm đủ nguồn tin cậy

Nguồn chấp nhận khóa có thể bao gồm:

- Các file được cấu hình qua `AuthorizedKeysFile`.
- Chương trình hoặc dịch vụ được gọi qua `AuthorizedKeysCommand`.
- Hệ thống quản lý cấu hình sinh lại file cấp quyền.
- Cấu hình CA và nguồn principal nếu dùng chứng thư SSH.
- Bastion, gateway hoặc thiết bị trung gian có kho khóa riêng.
- Image, mẫu máy, bootstrap và quy trình phục hồi có thể cài lại khóa cũ.

Không mặc định mọi server dùng đúng một file `~/.ssh/authorized_keys`. Cần xác minh cấu hình thực tế, kể cả cấu hình áp dụng riêng cho từng nhóm người dùng hoặc kết nối.

Một khóa đã bị xóa khỏi máy đang chạy có thể quay lại sau lần cấu hình tiếp theo nếu nguồn quản lý cấu hình vẫn giữ nó. Vì vậy, nguồn khai báo và trạng thái runtime đều thuộc phạm vi migration.

## 5. Bảo toàn giới hạn quyền khi cài khóa mới

Một dòng trong nguồn cấp quyền có thể mang các điều kiện bổ sung. Khi thay public key, phải hiểu và giữ các giới hạn cần thiết, đồng thời đánh giá lại những quyền đang quá rộng.

Ví dụ minh họa một entry trong `authorized_keys`:

```text
from="192.0.2.10",command="/usr/local/libexec/release-gateway",no-agent-forwarding,no-port-forwarding,no-X11-forwarding,no-pty ssh-ed25519 <PUBLIC_KEY_BASE64> deploy-agent-migration
```

Đây là mẫu giải thích, không phải cấu hình để sao chép nguyên trạng. Địa chỉ `192.0.2.10` là địa chỉ minh họa, chuỗi public key là placeholder và thuật toán thực tế phải theo chính sách đã được phê duyệt cùng khả năng tương thích của môi trường.

Những điểm cần kiểm tra:

- Địa chỉ mà server quan sát có phải IP của runner, NAT hay bastion hay không.
- Lệnh cưỡng bức có kiểm tra đầu vào và chỉ cho phép nghiệp vụ dự kiến hay không.
- Workflow có thực sự cần PTY, chuyển tiếp cổng hoặc chuyển tiếp agent hay không.
- Tài khoản đích có quyền `sudo`, quyền file và nhóm phù hợp hay không.
- Cơ chế triển khai dùng shell, SFTP hay SCP có tương thích với lệnh cưỡng bức không.
- Các điều kiện này có được biểu diễn tương đương trong mô hình chứng thư hoặc broker mới hay không.

Một forced command không tự động bảo đảm JEA. Nếu chương trình được gọi cho phép chạy shell tùy ý hoặc sửa file đặc quyền, phạm vi quyền vẫn rộng. Tương tự, cấp khóa trong một khoảng thời gian không tự động kết thúc các phiên SSH đã mở.

Không bật agent forwarding chỉ để migration dễ chạy. Agent forwarding có thể cho phép bên nhận chuyển tiếp yêu cầu agent thực hiện xác thực trong thời gian kết nối còn khả dụng, dù không nhất thiết làm lộ byte của private key.

## 6. Chuẩn bị phương án thay đổi

### 6.1. Tạo kế hoạch riêng cho từng nhóm phụ thuộc

Gom tài sản theo cùng chủ sở hữu, client, đường mạng và cách quản lý khóa. Bắt đầu với nhóm có thể quan sát và phục hồi được. Không dùng một đợt thay đồng loạt cho các máy có cấu hình khác nhau chỉ vì chúng tin cậy cùng fingerprint.

Một kế hoạch có thể được mô tả bằng metadata như sau:

```yaml
migrationId: pam-ssh-deploy-wave-01
identity:
  kind: workload
  name: deploy-agent
targetAccount: release
assets:
  - app-01
  - app-02
  - app-03
keyReferences:
  old: inventory:key-old
  new: pam:key-new
strategy: replace-key
changeOwner: platform-operations
approvalRef: change-approved
overlap:
  required: true
  owner: platform-operations
  deadline: change-window-end
validation:
  positive:
    - fresh-authentication-with-new-key
    - approved-deployment-workflow
  negative:
    - old-key-rejected-after-revocation
    - unauthorized-source-rejected
rollback:
  trigger: deployment-or-authentication-gate-failed
  authority: change-owner-and-security
  channel: approved-recovery-path
```

Đây là mẫu kế hoạch trung lập với sản phẩm, không phải schema import của một hệ thống PAM. Các tham chiếu khóa chỉ là định danh; không chứa vật liệu bí mật. Thời điểm thực tế, điều kiện đo và người phê duyệt phải được điền rõ trong kế hoạch triển khai.

### 6.2. Xác định kênh phục hồi trước khi thay đổi

Cần có một đường phục hồi đã kiểm thử, ví dụ console được kiểm soát hoặc quy trình break-glass đã được phê duyệt. Không chỉ dựa vào “một phiên SSH còn mở” vì phiên đó có thể bị đứt hoặc không đủ quyền sửa cấu hình.

Trước cutover, xác nhận:

1. Người có quyền phục hồi đang sẵn sàng trong cửa sổ thay đổi.
2. Kênh phục hồi truy cập được đúng host.
3. Quyền sửa nguồn cấp quyền được cấp đúng người và đúng thời gian.
4. Bản cấu hình cần khôi phục có provenance và quyền truy cập phù hợp.
5. Dùng kênh phục hồi tạo ra bằng chứng và được thu hồi sau khi xử lý.

Nếu khóa cũ bị nghi lộ, không dùng việc cài lại khóa đó làm phương án rollback mặc định. Cần một credential phục hồi riêng và xử lý theo quy trình sự cố.

### 6.3. Tách người phê duyệt, người thực hiện và người xác nhận

Với hệ thống nhạy cảm, có thể bố trí:

- Chủ tài sản xác nhận nhu cầu truy cập và thời điểm thay đổi.
- Nhóm PAM quản lý khóa, chính sách cấp quyền và bằng chứng vault.
- Nhóm hệ thống cập nhật nguồn tin cậy trên host.
- Chủ workload kiểm tra hành vi ứng dụng.
- Người xác nhận nghiệm thu đối chiếu bằng chứng và các ngoại lệ còn lại.

PAM không nên biến một tài khoản kỹ thuật dùng chung thành một danh tính không thể quy trách nhiệm. Nếu nhiều người dùng chung tài khoản đích, hệ thống phải liên kết từng lần truy cập với danh tính cá nhân và yêu cầu đã được phê duyệt.

## 7. Thực hiện theo các cổng kiểm tra

### 7.1. Cổng 1 — Chuẩn hóa và tiếp nhận khóa

Nếu nhập khóa hiện hữu:

- Xác minh đúng cặp khóa bằng metadata và fingerprint public key.
- Chọn kênh nhập được phê duyệt, có kiểm soát truy cập và bảo vệ dữ liệu truyền.
- Xử lý passphrase qua kênh bí mật riêng nếu quy trình cần.
- Xác định các bản sao đang có, chủ sở hữu và kế hoạch loại bỏ.
- Kiểm tra PAM có thể thực hiện thao tác sử dụng khóa theo mô hình đích.

Nếu tạo khóa mới:

- Tạo trong môi trường và cơ chế sinh khóa được phê duyệt.
- Chọn loại khóa, kích thước, khả năng xuất và chính sách bảo vệ theo quy định của tổ chức.
- Gắn khóa với danh tính, mục đích, môi trường và chu kỳ luân chuyển.
- Chỉ phân phối public key tới nguồn cấp quyền.
- Không ghi private key vào ticket, dòng lệnh, biến đầu ra CI hay log chẩn đoán.

Một cơ chế ký không cho xuất private key có thể giảm phạm vi phân phối, nhưng phải kiểm tra tích hợp thực tế có hỗ trợ nó không. Không tuyên bố khóa “không thể xuất” nếu pipeline vẫn tải private key về file tạm.

### 7.2. Cổng 2 — Cài public key hoặc cấu hình trust mới

Cập nhật đúng nguồn được xác định trong kiểm kê. Nếu cần khoảng chồng lấn, cho phép khóa cũ và mới cùng tồn tại trong một khoảng đã có chủ sở hữu, hạn kết thúc và cơ chế theo dõi.

Khoảng chồng lấn phục vụ chuyển đổi, không phải trạng thái đích. Ghi nhận rõ máy nào đã cài khóa mới và máy nào còn chờ, tránh tình trạng một file báo “đã migrate” trong khi một phần tài sản vẫn chỉ nhận khóa cũ.

Khi sửa nguồn cấp quyền:

- Giữ nguyên quyền sở hữu và quyền truy cập file/thư mục cần thiết.
- Không thay cả file bằng một danh sách thiếu các khóa hợp lệ khác.
- Dùng cơ chế cập nhật phù hợp với nguồn cấu hình để tránh ghi dở.
- Kiểm tra agent quản lý cấu hình không khôi phục bản cũ.
- Nếu thay cấu hình SSH server, xác minh cấu hình theo quy trình của môi trường trước khi áp dụng.

Đổi public key trong `authorized_keys` và đổi cấu hình daemon SSH là hai loại thay đổi khác nhau. Không khởi động lại dịch vụ một cách máy móc chỉ để thêm một public key; phải theo cách nguồn cấp quyền được hệ thống thực sự đọc.

### 7.3. Cổng 3 — Chuyển client hoặc workload

Cập nhật cấu hình client để dùng tham chiếu khóa hoặc cơ chế broker mới. Đồng thời kiểm tra:

- Đúng endpoint, tài khoản, bastion và nguồn mạng.
- Runner hoặc người dùng có quyền yêu cầu credential mới.
- Workflow nhận được đúng credential cho đúng môi trường.
- Không còn fallback tự động sang khóa cũ hoặc mật khẩu ngoài kế hoạch.
- Không ghi secret ra đầu ra khi kiểm tra lỗi.
- Job không tiếp tục dùng secret được cache từ một lần chạy trước.

Nếu PAM chỉ cung cấp private key cho runner, việc runner đã gọi được API của PAM chưa chứng minh SSH thành công. Nếu broker kết nối thay client, cần kiểm tra cả xác thực client vào broker và kết nối broker tới host đích.

### 7.4. Cổng 4 — Kiểm tra bằng kết nối mới, có cô lập phương thức xác thực

Một kết nối SSH đã có sẵn có thể được tái sử dụng qua connection multiplexing. SSH agent hoặc cấu hình client cũng có thể cung cấp một khóa khác. Vì thế, “lệnh vừa chạy thành công” chưa chắc chứng minh khóa mới đã được dùng.

Ví dụ kiểm tra cho mô hình có private key file trên một client thử nghiệm được phê duyệt:

```bash
ssh -F /dev/null \
  -o BatchMode=yes \
  -o PreferredAuthentications=publickey \
  -o PasswordAuthentication=no \
  -o KbdInteractiveAuthentication=no \
  -o IdentitiesOnly=yes \
  -o IdentityAgent=none \
  -o ControlMaster=no \
  -o ControlPath=none \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/secure-test/known_hosts \
  -i /run/pam-test/deploy-agent-new \
  release@app-01.example.invalid 'id -un'
```

Lệnh chỉ minh họa một phiên kiểm tra. Host dùng tên miền ví dụ, file host trust phải được kiểm chứng trước, và private key file chỉ tồn tại nếu mô hình được phê duyệt cho phép. Cần điều chỉnh tương thích với SSH client đang triển khai. Nếu môi trường yêu cầu bastion hoặc cấu hình đặc thù, phải khai báo đường đi tương ứng; không dùng `-F /dev/null` rồi vô tình kiểm tra một tuyến khác với tuyến production.

Ở mô hình broker, agent chuyên dụng hoặc chứng thư, thiết kế phép thử tương đương với phương thức được hỗ trợ. Không xuất private key chỉ để chạy lệnh mẫu này.

`id -un` kiểm tra tài khoản thực thi, chưa kiểm tra đủ quyền nghiệp vụ. Sau phép thử xác thực, phải chạy workflow nghiệp vụ đã được phê duyệt trên phạm vi phù hợp. Đối chiếu thời điểm và định danh khóa trong log xác thực phía đích hoặc bằng chứng của broker để chứng minh không có đường fallback.

### 7.5. Cổng 5 — Thu hồi khóa cũ trên toàn bộ nguồn

Chỉ thu hồi sau khi kiểm tra mới đạt yêu cầu và nhóm phụ thuộc đã được đối chiếu. Việc thu hồi phải bao gồm:

1. Xóa hoặc vô hiệu hóa public key cũ tại mọi nguồn đang cấp quyền thuộc phạm vi.
2. Cập nhật nguồn quản lý cấu hình, bootstrap và image liên quan để khóa không quay lại.
3. Đóng quyền checkout hoặc dùng khóa cũ trong PAM và các kho bí mật liên quan.
4. Thu hồi bản cấp phát tại runner, máy quản trị và agent đang giữ khóa.
5. Xử lý backup và bản lưu theo chính sách, đồng thời bảo đảm phục hồi không tái cấp quyền cũ.
6. Kiểm tra kết nối mới bằng khóa cũ bị từ chối tại từng quan hệ đã di chuyển.

Việc xóa public key cũ trên một host không tự động vô hiệu hóa private key trên các host khác. Xóa private key khỏi một runner cũng không thu hồi quyền của những bản sao còn ở nơi khác.

Nếu đang dùng chứng thư, cần kiểm tra đúng cơ chế thu hồi mà server thực sự áp dụng, ví dụ danh sách thu hồi được hỗ trợ và cách phân phối. Không giả định một thay đổi trạng thái trong PAM tức thì vô hiệu hóa chứng thư đang còn hiệu lực trên mọi host.

### 7.6. Cổng 6 — Xử lý phiên đang hoạt động

Thu hồi quyền xác thực thường chỉ chặn các lần xác thực mới. Phiên đã mở, kết nối điều khiển đang được tái sử dụng và tác vụ đã chạy cần được đánh giá riêng.

Kế hoạch phải xác định:

- Có cần kết thúc phiên cũ không.
- Ai có quyền kết thúc và ảnh hưởng nghiệp vụ là gì.
- Có tiến trình nền hoặc tác vụ đặc quyền còn chạy không.
- Có kết nối được multiplex qua phiên cũ không.
- Sau khi xử lý phiên, các phép thử có thực sự tạo xác thực mới không.

Không tuyên bố khóa cũ đã bị vô hiệu hóa hoàn toàn chỉ dựa trên một lần đăng nhập mới thất bại.

## 8. Kiểm thử migration có đủ chiều rộng

Dùng một ma trận gồm cả điều kiện được phép và bị từ chối. Các phép thử phủ định chỉ thực hiện trong phạm vi được ủy quyền, với số lần giới hạn phù hợp để tránh gây khóa tài khoản hoặc nhiễu giám sát.

| Phép thử | Kết quả kỳ vọng | Bằng chứng cần có |
|---|---|---|
| Khóa mới, đúng workload và đúng host | Xác thực mới thành công | Tài khoản, host, thời điểm và dấu định danh khóa tương ứng |
| Workflow được phê duyệt | Chức năng cần thiết chạy đúng | Kết quả job, mã thay đổi và đối chiếu quyền |
| Khóa cũ sau thu hồi | Xác thực mới bị từ chối | Nguồn tin cậy đã cập nhật và log từ chối |
| Nguồn mạng ngoài điều kiện cho phép | Truy cập bị chặn theo chính sách | Kết quả từ điểm kiểm thử đã được ủy quyền |
| Workload khác xin dùng khóa | Bị từ chối ở lớp PAM | Danh tính yêu cầu và quyết định chính sách |
| Hết thời gian được cấp quyền | Yêu cầu hoặc xác thực mới bị từ chối như thiết kế | Thời hạn và bằng chứng thực thi ở đúng lớp |
| Lệnh hoặc forwarding ngoài phạm vi | Bị từ chối nếu mô hình đích có giới hạn đó | Sự kiện và kết quả kiểm tra giới hạn |
| Cấu hình được áp dụng lại | Khóa cũ không xuất hiện trở lại | Kết quả đối chiếu nguồn khai báo và runtime |
| Phục hồi cấu hình được diễn tập | Không tái cấp khóa cũ ngoài kế hoạch | Biên bản diễn tập và nguồn cấu hình sau phục hồi |

Bài kiểm tra hết thời gian cần chỉ rõ đang thử TTL của credential, thời hạn chứng thư, quyền checkout hay thời hạn phiên. Các giới hạn này không đồng nghĩa với nhau.

Nếu PAM chỉ ghi nhận việc lấy khóa mà kết nối SSH đi trực tiếp từ runner đến host, sự kiện checkout không thay thế log xác thực hay ghi nhận phiên phía đích. Cũng không mặc định có session recording cho các kết nối không đi qua thành phần có khả năng ghi phiên.

## 9. Cutover và rollback qua một ví dụ

### 9.1. Lộ trình cutover của deploy-agent

Giả sử kiểm kê cho thấy cùng public key cũ được cấp cho `release` trên `app-01`, `app-02`, `app-03`; runner chính và runner dự phòng đều sử dụng nó.

Lộ trình có thể là:

1. Tạo khóa mới, cấu hình quyền workload và xác nhận đường phục hồi.
2. Cài public key mới lên cả ba máy qua nguồn quản lý cấu hình.
3. Chuyển runner thử nghiệm, xác nhận kết nối mới và workflow triển khai.
4. Chuyển runner chính và dự phòng; kiểm tra cả hai.
5. Chạy các job theo chu kỳ cần thiết hoặc kiểm tra có kiểm soát để bao phủ job ít chạy.
6. Thu hồi khóa cũ ở ba máy và các nguồn sinh cấu hình.
7. Kiểm tra khóa cũ không mở kết nối mới, xử lý phiên cũ theo quyết định.
8. Dọn các bản private key cũ và chốt bằng chứng.

Nếu runner chính đã chuyển nhưng runner dự phòng chưa chuyển, chưa thể thu hồi khóa cũ rồi tuyên bố dự phòng vẫn hoạt động. Ngược lại, giữ khóa cũ vô thời hạn chỉ để dự phòng sẽ làm migration không đạt mục tiêu thu hồi.

Không đặt một khoảng quan sát cố định cho mọi workload. Một job chạy hằng ngày và một job chỉ chạy cuối kỳ cần cách chứng minh khác nhau; phải có chủ sở hữu xác nhận đủ độ bao phủ.

### 9.2. Điều kiện rollback phải đo được

Ví dụ điều kiện rollback:

- Workload không lấy hoặc sử dụng được credential mới trong thời gian cho phép.
- Một host trong phạm vi không xác thực được theo mô hình mới.
- Workflow nghiệp vụ thất bại do khác biệt quyền đã được xác minh.
- Bằng chứng danh tính hoặc audit bị thiếu ở một cổng bắt buộc.
- Đường truy cập thay đổi làm mất điều kiện vận hành đã được phê duyệt.

Khi lỗi xuất hiện, trước hết xác định lớp lỗi: cấp quyền tại PAM, định tuyến, host trust, xác thực user key, quyền tài khoản hay hành vi nghiệp vụ. Không nới tất cả quyền hoặc tắt kiểm tra bảo mật để tìm cách cho job chạy.

Rollback có thể chỉ chuyển một nhóm máy hoặc một workload về trạng thái trước đó, thay vì đảo toàn bộ đợt migration. Phạm vi rollback phải được ghi rõ để tránh một nhóm tiếp tục dùng khóa mới trong khi báo cáo lại coi mọi hệ thống đã quay về khóa cũ.

### 9.3. Rollback cũng là một thay đổi có kiểm soát

Nếu cần phục hồi quyền của khóa cũ, phải có quyết định, phạm vi và hạn kết thúc. Kiểm tra lại quyền thật sự sau phục hồi, ghi dấu thời gian và giữ trạng thái bài migration là chưa hoàn tất.

Không khôi phục nguyên một file `authorized_keys` cũ lên nhiều máy nếu sau snapshot có những thay đổi hợp lệ khác. Cần phục hồi đúng entry hoặc đúng phiên bản cấu hình được xác định, bảo toàn các thay đổi ngoài phạm vi.

Sau khi khắc phục nguyên nhân, tạo kế hoạch cutover lại. Không xóa log hoặc sửa bằng chứng của lần thử trước để báo cáo chỉ còn kết quả thành công.

## 10. Bằng chứng và điều kiện nghiệm thu

Một gói bằng chứng hữu ích gồm:

- Danh sách quan hệ truy cập và chủ sở hữu đã xác nhận.
- Fingerprint cũ/mới hoặc định danh chứng thư phù hợp, không có private key.
- Tham chiếu phê duyệt và cấu hình chính sách PAM.
- Nguồn cấp quyền trước/sau theo phạm vi, với dữ liệu nhạy cảm được xử lý phù hợp.
- Kết quả kiểm thử xác thực mới, nghiệp vụ và từ chối khóa cũ.
- Bằng chứng xử lý runner dự phòng, job ít chạy và nguồn quản lý cấu hình.
- Quyết định về phiên còn mở và kết quả thực hiện.
- Kết quả cleanup credential, ngoại lệ tồn tại và thời hạn xử lý.

Đồng bộ thời gian giữa các nguồn log cần đủ để liên kết sự kiện. Một chuỗi bằng chứng nên nối được:

```text
Yêu cầu/Job → Danh tính đã xác thực → Quyết định cấp quyền PAM
            → Khóa/chứng thư được sử dụng → Host/tài khoản đích
            → Phiên hoặc lần xác thực → Kết quả nghiệp vụ
```

Chỉ đánh dấu một quan hệ truy cập đã hoàn tất khi tất cả điều kiện liên quan đạt yêu cầu:

1. Chủ sở hữu và mục đích sử dụng đã được xác nhận.
2. Mô hình mới hoạt động cho đầy đủ client và host trong phạm vi.
3. Quyền thực tế không rộng hơn phạm vi đã được phê duyệt.
4. Khóa cũ bị từ chối cho xác thực mới ở toàn bộ nguồn thuộc phạm vi.
5. Các bản private key và phiên cũ đã được xử lý theo kế hoạch.
6. Nguồn sinh cấu hình và quy trình phục hồi không tái tạo quyền cũ ngoài kiểm soát.
7. Có bằng chứng kiểm thử, luân chuyển và người chịu trách nhiệm vận hành tiếp theo.

Nếu một tài sản chưa thể thu hồi khóa cũ, ghi nó là ngoại lệ có chủ sở hữu và thời hạn. Không gộp ngoại lệ vào trạng thái “đã hoàn tất toàn bộ”.

## 11. Những lỗi thường gặp

### 11.1. Nhập vào vault nhưng không xử lý bản sao

**Biểu hiện:** khóa mới xuất hiện trong PAM nhưng private key cũ vẫn nằm trên nhiều laptop và runner.

**Hệ quả:** việc dùng khóa ngoài PAM có thể tiếp tục mà không qua phê duyệt hoặc quy trách nhiệm.

**Cách xử lý:** kiểm kê nơi sử dụng, thay cặp khóa khi cần, thu hồi public key cũ và xử lý bản sao theo quy trình. Không lấy thao tác import làm bằng chứng hoàn tất.

### 11.2. Thử thành công nhờ agent hoặc kết nối cũ

**Biểu hiện:** test qua ngay nhưng log không xác nhận dấu định danh của khóa mới.

**Hệ quả:** cutover thật có thể thất bại khi client sạch chạy lần đầu.

**Cách xử lý:** dùng kết nối mới, kiểm soát tập identity mà client được phép thử, tách connection multiplexing và đối chiếu log phía đích.

### 11.3. Bỏ mất option hạn chế khi thay public key

**Biểu hiện:** entry mới chỉ có public key, không còn điều kiện nguồn mạng hoặc lệnh cưỡng bức của entry cũ.

**Hệ quả:** migration làm mở rộng quyền truy cập.

**Cách xử lý:** kiểm tra cả khóa lẫn điều kiện cấp quyền, kiểm thử phủ định và quyền hệ điều hành.

### 11.4. Xóa khóa ở runtime nhưng cấu hình tự cài lại

**Biểu hiện:** khóa cũ bị từ chối sau cutover, rồi được chấp nhận trở lại sau một đợt cấu hình.

**Hệ quả:** quyền đã thu hồi quay lại mà nhóm vận hành không nhận ra.

**Cách xử lý:** cập nhật nguồn khai báo, image và bootstrap; kiểm tra sau một chu kỳ áp dụng lại hoặc diễn tập phục hồi phù hợp.

### 11.5. Bật fallback để che lỗi

**Biểu hiện:** job chuyển sang khóa mới nhưng khi thất bại tự dùng mật khẩu hoặc một khóa quản trị chung.

**Hệ quả:** kết quả job không còn chứng minh mô hình PAM mới hoạt động.

**Cách xử lý:** xác định rõ fallback nào được phép, kiểm thử độc lập từng đường và ghi nhận đường thực tế đã sử dụng. Fallback tạm thời phải có chủ sở hữu và hạn đóng.

### 11.6. Nhầm thu hồi khóa với kết thúc phiên

**Biểu hiện:** public key đã bị xóa nhưng một kết nối vẫn thực hiện lệnh.

**Hệ quả:** báo cáo thu hồi không phản ánh quyền truy cập đang còn tồn tại.

**Cách xử lý:** đánh giá phiên, connection multiplexing và tiến trình nền; kết thúc theo thẩm quyền và tác động nghiệp vụ đã được duyệt.

## 12. Bài thực hành theo tình huống

Một tổ chức có hai runner, bốn máy ứng dụng và một máy dự phòng chưa bật thường xuyên. Tất cả đang dùng một public key cho tài khoản `release`. Public key được sinh vào cấu hình máy bởi công cụ quản lý cấu hình. Một job triển khai hằng ngày chạy trên runner chính; job kiểm tra phục hồi chạy theo lịch ít hơn.

Hãy lập kế hoạch migration với các đầu ra:

1. Bảng quan hệ client–host–tài khoản, có chủ sở hữu cho cả máy dự phòng.
2. Lựa chọn mô hình quản lý private key và cách workload được phép sử dụng.
3. Danh sách điều kiện quyền phải bảo toàn, gồm quyền lệnh và forwarding.
4. Trình tự cài khóa mới, chuyển hai runner, kiểm tra máy dự phòng và đóng khoảng chồng lấn.
5. Ma trận test chứng minh khóa mới hoạt động và khóa cũ bị từ chối bằng xác thực mới.
6. Phương án phục hồi nếu công cụ quản lý cấu hình cài lại khóa cũ.
7. Gói bằng chứng không chứa secret và tiêu chí xác nhận hoàn tất.

Các câu hỏi cần tự giải thích:

- Vì sao chỉ kiểm tra runner chính chưa đủ?
- Vì sao xóa file private key trên runner không thu hồi quyền trên server?
- Vì sao khôi phục một image cũ có thể làm khóa cũ được chấp nhận trở lại?
- Làm sao chứng minh một kết nối không dùng SSH agent hoặc phiên đã mở?
- Khi nào cần kết thúc phiên cũ thay vì chỉ từ chối lần xác thực mới?
- Nếu tổ chức chuyển sang chứng thư SSH, những điều kiện trust, principal và vòng đời nào cần bổ sung?

Một kế hoạch đạt yêu cầu phải chứng minh được toàn bộ quan hệ truy cập đã chuyển sang mô hình PAM đích, các giới hạn quyền được giữ đúng và quyền cũ đã được xử lý có bằng chứng. Việc sao chép một private key hoặc chạy thành công một lệnh SSH chỉ là một phần của quá trình đó.

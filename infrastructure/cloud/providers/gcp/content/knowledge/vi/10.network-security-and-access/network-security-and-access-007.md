# OS Login và kiểm soát truy cập SSH trên Google Cloud

Một nhóm vận hành quản lý máy ảo **Compute Engine** dùng để chạy công cụ nội bộ, xử lý tác vụ nền và khắc phục sự cố. Nhóm muốn lập trình viên được truy cập những VM phù hợp với công việc, nhân viên trực hệ thống có thể thực hiện tác vụ quản trị khi được giao, và người rời dự án không còn đăng nhập được. Đồng thời, doanh nghiệp muốn hạn chế cổng SSH công khai và tránh phải sao chép khóa SSH thủ công lên từng VM.

**OS Login** là cơ chế của Google Cloud giúp quản lý quyền đăng nhập hệ điều hành trên VM Linux bằng **Identity and Access Management (IAM)**. Thay vì dựa chủ yếu vào SSH public keys nằm trong metadata của project/instance, OS Login liên kết việc đăng nhập với danh tính Google Cloud, quyền IAM và hồ sơ người dùng POSIX/SSH được quản lý qua OS Login. Để kiểm soát SSH thực sự an toàn, còn cần **đường mạng tới cổng 22**, cấu hình SSH daemon, vòng đời khóa, xác thực nhiều bước khi hỗ trợ, giám sát và quy trình xử lý khẩn cấp.

Bài học thuộc chương **Bảo mật và truy cập mạng**, mô-đun **CLOUD_PROVIDERS_GCP**. Khi xây dựng hệ thống với organization/project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, người học cần chọn mô hình truy cập quản trị phù hợp, bảo vệ máy và dữ liệu, tự động hóa cấu hình và theo dõi cả độ tin cậy lẫn chi phí.

## 1. Các mục tiêu cần đạt

Sau bài này, người học có thể:

1. Giải thích cơ chế OS Login và sự khác biệt với cách quản lý SSH keys bằng metadata.
2. Phân biệt quyền `roles/compute.osLogin`, `roles/compute.osAdminLogin`, quyền dùng service account và quyền mở IAP TCP tunnel.
3. Xác định phạm vi bật OS Login theo project hoặc instance và hiểu khả năng kế thừa/ghi đè metadata.
4. Kết hợp OS Login với **Identity-Aware Proxy (IAP) TCP forwarding** để kết nối VM không có external IP.
5. Thiết lập quy trình cấp/thu hồi quyền, quản lý SSH keys, kiểm tra 2-step verification và ghi nhận audit.
6. Chẩn đoán riêng lỗi IAM, OS Login, SSH daemon, firewall, routing và ứng dụng.

## 2. Bốn lớp của một phiên đăng nhập SSH

Để đăng nhập thành công, cần đồng thời thỏa nhiều điều kiện:

| Lớp | Câu hỏi | Thành phần liên quan |
| --- | --- | --- |
| **Danh tính** | Ai đang yêu cầu truy cập? | Tài khoản Google/Cloud Identity, nhóm IAM, SSH key hoặc cơ chế chứng thực được hỗ trợ. |
| **Ủy quyền** | Danh tính đó được vào VM nào, có được dùng `sudo` không? | OS Login roles, IAM allow/deny, điều kiện truy cập, các yêu cầu bổ sung với service account. |
| **Kết nối mạng** | Máy của người quản trị tới được SSH port trên VM không? | External IP hoặc IAP tunnel, VPC firewall, route, ingress policy, SSH port. |
| **Hệ điều hành** | VM có hỗ trợ OS Login, SSH daemon và cấu hình xác thực hợp lệ không? | Guest environment, NSS/PAM, POSIX username, `sshd`, filesystem, cấu hình Linux. |

~~~mermaid
flowchart LR
    OP["Kỹ sư vận hành"] --> AUTH["Google identity / IAM"]
    AUTH --> IAP["IAP TCP tunnel hoặc đường SSH được phép"]
    IAP --> FW["VPC firewall: TCP 22"]
    FW --> VM["Compute Engine Linux VM"]
    VM --> OS["OS Login + SSH daemon"]
    OS --> SH["Shell người dùng"]
    P["IAM role và POSIX privileges"] -. "Quyền truy cập / sudo" .-> OS
~~~

**OS Login không phải VPN, firewall hay một đường hầm SSH.** Nó giải quyết danh tính và quyền đăng nhập hệ điều hành. Một người có IAM role hợp lệ vẫn không SSH được nếu VPC firewall chặn cổng 22. Ngược lại, firewall đã mở không cho phép một người không có quyền OS Login tự đăng nhập.

### 2.1. OS Login áp dụng cho workload nào?

Trường hợp điển hình là **Compute Engine VM Linux** có guest environment hỗ trợ OS Login. Với custom image, phải xác minh đã cài các thành phần OS Login và cấu hình SSH/NSS/PAM phù hợp. VM Windows sử dụng cơ chế quản trị tài khoản và kết nối khác, không áp dụng nguyên mẫu đăng nhập SSH Linux của bài này.

Nếu node **GKE** chạy trên Compute Engine, quyền SSH vào node và quy trình vận hành node có các ràng buộc riêng của GKE; không coi node của một cụm được quản lý giống hoàn toàn VM tự vận hành. **Cloud Run** là môi trường serverless, không có thao tác SSH trực tiếp vào VM của dịch vụ; xem logs, revision và công cụ chẩn đoán của Cloud Run thay thế. Các quyền truy cập **Cloud SQL** hoặc **Cloud Storage** cũng không được cấp chỉ vì người dùng đã SSH vào một VM.

## 3. OS Login so với SSH key trong metadata

### 3.1. Cách truyền thống: metadata-based SSH keys

Trong mô hình SSH keys qua metadata, public key có thể được đưa vào metadata của **project** hoặc **instance**. Compute Engine guest environment trên VM sử dụng cơ chế hỗ trợ để tạo/cập nhật người dùng Linux và quản lý `authorized_keys`.

~~~text
Người quản trị → gcloud/metadata SSH key → VM guest environment
             → Linux user + authorized_keys → sshd
~~~

Cách này có thể tiện cho một máy thử nghiệm, nhưng khi số VM tăng, việc quản lý ai được đăng nhập, key nào còn hợp lệ và khi nào quyền cần thu hồi dễ trở nên phân tán. Tính năng metadata `block-project-ssh-keys=TRUE` có thể ngăn sử dụng SSH keys từ metadata cấp project trên VM được cấu hình, nhưng **không đồng nghĩa đã bật hoặc bắt buộc sử dụng OS Login**.

### 3.2. Cách với OS Login

Khi OS Login có hiệu lực:

1. Người dùng được gán **IAM role** phù hợp trên tài nguyên hoặc phạm vi tổ tiên.
2. SSH public key (nếu dùng phương án key) được gắn với **OS Login profile** của danh tính, không dùng danh sách project/instance metadata SSH keys làm nguồn đăng nhập thông thường.
3. Guest environment của VM phối hợp với OS Login để nhận diện tài khoản POSIX và kiểm tra khả năng đăng nhập.
4. Người dùng đăng nhập vào shell với quyền Linux tương ứng; chỉ người được cấp quyền quản trị phù hợp mới có thể dùng `sudo` theo cơ chế OS Login.

Khi bật OS Login, Compute Engine không sử dụng SSH keys trong project/instance metadata để xác thực theo đường quản lý metadata thông thường. Các khóa nằm trong metadata không được xem là nguồn cấp quyền OS Login. Tuy nhiên, **không nên khẳng định OS Login vô hiệu hóa mọi tài khoản cục bộ hoặc mọi cách truy cập khác trên một custom image đã bị chỉnh sửa**: cần kiểm tra `sshd`, local accounts, authorized keys tùy biến và đường truy cập quản trị còn tồn tại.

| Tiêu chí | SSH keys trong metadata | OS Login |
| --- | --- | --- |
| Nguồn chính quản lý truy cập | Keys trong metadata project/instance và cấu hình guest. | Danh tính và IAM role kết hợp OS Login profile. |
| Thu hồi quyền nhân sự | Cần quản lý keys/metadata liên quan, bảo đảm đồng bộ guest. | Thu hồi IAM binding hoặc thành viên nhóm; kiểm tra phiên đang tồn tại và quyền khác. |
| Quyền thường / quyền `sudo` | Phụ thuộc cấu hình user/guest và SSH key workflow. | Tách rõ role đăng nhập thường và role quản trị OS. |
| Xác thực bổ sung | Cần thiết kế cơ chế riêng. | Có OS Login 2-step verification khi đáp ứng điều kiện hỗ trợ. |
| Kiểm toán | Theo dõi thay đổi metadata và logs guest. | Thêm dấu vết IAM/OS Login API và logs guest, theo loại sự kiện được ghi. |
| Phạm vi triển khai | Cấu hình theo metadata/VM. | Bật theo project hoặc instance; quản lý role bằng IAM. |

OS Login giúp **tập trung quy trình phân quyền**, không có nghĩa chỉ cần gán IAM role là đủ để hệ thống SSH an toàn. Chính sách mạng, bảo vệ khóa cá nhân, cập nhật OS và ghi log vẫn là thành phần bắt buộc.

## 4. Các quyền IAM cần hiểu

### 4.1. Hai role chính

| Role | Công dụng | Ví dụ người nhận |
| --- | --- | --- |
| `roles/compute.osLogin` | Cho phép đăng nhập OS Login với quyền người dùng thông thường trên VM đủ điều kiện. | Lập trình viên cần xem file/log ứng dụng trong phạm vi được phê duyệt. |
| `roles/compute.osAdminLogin` | Cho phép đăng nhập OS Login với khả năng quản trị hệ điều hành, bao gồm `sudo`, trong phạm vi được phép. | Nhân viên vận hành hệ thống thực hiện bảo trì được ủy quyền. |

`roles/compute.osAdminLogin` là quyền nhạy cảm: một người có đặc quyền root trên VM có thể tác động tới process, file, khóa ứng dụng, credential có mặt trên máy và tính sẵn sàng. Không cấp `osAdminLogin` chỉ vì người dùng gặp lỗi khi truy cập thư mục cần đọc. Hãy điều chỉnh **Linux file permissions, ownership** hoặc nhiệm vụ cần làm trước khi mở quyền quản trị toàn máy.

### 4.2. Gắn role ở cấp nào?

Role OS Login có thể được gán ở project và, theo hỗ trợ, tại VM cụ thể hoặc phạm vi tổ tiên phù hợp. Nơi đặt binding quyết định phạm vi:

~~~text
Organization
└── Folder: production
    ├── Project: retail-prod
    │   ├── VM: checkout-worker-01
    │   └── VM: reporting-worker-02
    └── Project: analytics-prod
~~~

- Gán một role đăng nhập ở **project `retail-prod`** có thể cấp khả năng SSH vào nhiều VM đủ điều kiện trong project.
- Nếu chỉ được bảo trì **một VM**, ưu tiên binding nhỏ hơn ở instance khi role và quy trình cấp quyền hỗ trợ.
- Gán role rộng ở **folder/organization** có thể làm quyền lan tới nhiều project. Điều này chỉ phù hợp với những nhóm được giao nhiệm vụ tương ứng.

IAM allow policies có thể chịu ảnh hưởng của **IAM Conditions**, deny policies và các cơ chế giới hạn khác. Vì vậy, khi phân tích quyền hiệu lực không chỉ xem một binding trực tiếp tại VM.

### 4.3. Những quyền bổ sung dễ bị bỏ sót

| Tình huống | Quyền hoặc cơ chế cần kiểm tra | Vì sao? |
| --- | --- | --- |
| SSH qua IAP TCP forwarding | `roles/iap.tunnelResourceAccessor` tại phạm vi phù hợp. | Cho phép sử dụng IAP tunnel tới tài nguyên được bảo vệ. |
| VM có service account được gắn | Có thể cần `roles/iam.serviceAccountUser` trên **service account gắn với VM** theo luồng SSH/quy tắc OS Login áp dụng. | Quyền truy cập VM gắn với danh tính service account là một kiểm soát riêng cần tôn trọng. |
| Người dùng bên ngoài organization | Có thể cần `roles/compute.osLoginExternalUser` cấp theo yêu cầu ở **organization** và role OS Login thông thường ở phạm vi VM/project. | Cho phép tổ chức kiểm soát danh tính ngoài phạm vi nội bộ dùng OS Login. |
| Tự liệt kê/đọc thông tin VM qua gcloud | Các permission như `compute.instances.get`, `compute.instances.list` theo lệnh và giao diện sử dụng. | Quyền OS Login là quyền đăng nhập, không mặc nhiên cho mọi thao tác quản lý Compute Engine. |
| Tạo/sửa metadata hoặc IAM policy | Role quản trị Compute Engine/IAM phù hợp. | Người chỉ được SSH không nhất thiết được phép bật/tắt OS Login hay cấp thêm quyền cho người khác. |

Một người muốn kết nối qua IAP cần **cả quyền dùng tunnel lẫn quyền đăng nhập Linux**. Nếu thiếu một trong hai, phiên SSH có thể thất bại ở các bước khác nhau. Với service account hoặc tài khoản ngoài organization, kiểm tra tài liệu và mô hình danh tính thực tế để biết các yêu cầu bổ sung có áp dụng không.

### 4.4. Dùng group thay vì cấp quyền rời rạc

Một phương án quản trị:

~~~text
group:vm-readers@example.com
  → roles/compute.osLogin
  → phạm vi: nhóm VM được phép hỗ trợ

group:vm-maintainers@example.com
  → roles/compute.osAdminLogin
  → phạm vi: nhóm VM cần bảo trì có kiểm soát

group:vm-iap-users@example.com
  → roles/iap.tunnelResourceAccessor
  → phạm vi: tunnel/VM phù hợp
~~~

Người quản trị có thể đồng thời thuộc nhiều nhóm. Hãy xác định thành viên, owner duyệt và thời hạn sử dụng mỗi nhóm; với quyền `sudo` nên có quy trình phê duyệt, quản lý đặc quyền tạm thời khi tổ chức có giải pháp phù hợp và rà soát định kỳ.

## 5. Bật OS Login trên VM và project

### 5.1. Chuẩn bị trước khi thay đổi

Trước khi bật trên production:

1. Xác nhận VM là **Linux VM hỗ trợ OS Login** và có guest environment tương thích. Với custom image, kiểm tra cấu hình trước.
2. Kiểm kê người đang quản trị, tài khoản dịch vụ được gắn, nhóm OS Login và IAP có quyền hay không.
3. Xác định kết nối thử nghiệm còn dùng được khi key metadata bị bỏ qua.
4. Kiểm tra `sshd`, firewall, route và đường vào thay thế theo quy trình khôi phục của tổ chức.
5. Thử trên một VM nonproduction tương đồng, xác nhận cả người dùng thường và người có quyền `sudo`.
6. Đánh giá thay đổi nếu project có nhiều VM đang phụ thuộc vào metadata SSH keys, ví dụ tác vụ bảo trì hoặc pipeline cũ.

Bật OS Login khi chưa cấp đúng IAM role có thể khiến đội vận hành **mất quyền SSH** vào VM. Chuẩn bị đường khôi phục có kiểm soát trước khi sửa metadata hoặc áp Organization Policy bắt buộc.

### 5.2. Bật ở cấp project

`enable-oslogin=TRUE` là metadata key dùng để bật OS Login. Cấu hình ở **project** giúp áp dụng mặc định cho các VM đủ điều kiện, trừ những ghi đè hợp lệ tại instance và các ràng buộc policy.

~~~bash
# Các ví dụ sử dụng Bash và project ID minh họa.
PROJECT_ID="retail-prod"

# READ-ONLY: xem metadata chung của project.
gcloud compute project-info describe \
  --project="$PROJECT_ID" \
  --format="yaml(commonInstanceMetadata.items)"

# WRITE: bật OS Login qua project metadata.
gcloud compute project-info add-metadata \
  --project="$PROJECT_ID" \
  --metadata=enable-oslogin=TRUE
~~~

Lệnh `add-metadata` **thay đổi cấu hình thực tế**. Chỉ chạy khi có quyền và đã xác nhận mọi VM chịu ảnh hưởng. Nếu tổ chức yêu cầu OS Login trên toàn bộ VM, người quản trị có thể sử dụng Organization Policy constraint như **`constraints/compute.requireOsLogin`**, sau khi đánh giá phạm vi và hỗ trợ hiện hành. Đây là kiểm soát khác với việc đơn thuần đặt metadata.

### 5.3. Bật ở cấp một instance

~~~bash
PROJECT_ID="retail-prod"
ZONE="asia-southeast1-a"
VM="checkout-worker-01"

# READ-ONLY: xem metadata và service account của VM.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --format="yaml(name,metadata.items,serviceAccounts)"

# WRITE: bật OS Login tại đúng VM.
gcloud compute instances add-metadata "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --metadata=enable-oslogin=TRUE
~~~

Metadata cấp instance có thể **ghi đè giá trị tương ứng ở cấp project** khi không bị chính sách tổ chức bắt buộc. Vì vậy, project metadata đang là `TRUE` chưa đủ để kết luận mọi instance đều bật OS Login: cần kiểm tra cả instance metadata và những ràng buộc có hiệu lực.

Không dùng `enable-oslogin=FALSE` làm giải pháp né cơ chế quản trị khi Organization Policy yêu cầu OS Login. Thay đổi cấu hình truy cập phải nằm trong quy trình được phê duyệt.

### 5.4. Đọc lại trạng thái

~~~bash
# READ-ONLY: xác nhận metadata của VM sau thay đổi.
gcloud compute instances describe checkout-worker-01 \
  --project=retail-prod \
  --zone=asia-southeast1-a \
  --format="yaml(metadata.items)"
~~~

Lệnh này xác nhận **metadata được lưu**, nhưng vẫn cần đăng nhập thử bằng danh tính hợp lệ để biết guest environment hoạt động. Đừng xem `enable-oslogin=TRUE` là phép kiểm tra toàn bộ SSH, IAM và networking.

## 6. Quản lý SSH public keys với OS Login

### 6.1. Public key và private key

SSH key pair gồm:

- **Private key:** lưu an toàn trên thiết bị hoặc bộ quản lý khóa của người dùng; không gửi qua email, Git repository hay metadata dùng chung.
- **Public key:** có thể được thêm vào OS Login profile để hệ thống xác minh chữ ký khi đăng nhập.

Đừng nhầm **SSH key dùng đăng nhập VM** với **service account key JSON** dùng xác thực tới Google APIs. Chúng là hai loại thông tin xác thực có chức năng và rủi ro riêng.

### 6.2. Thêm khóa vào OS Login profile

Giả sử người dùng đã có SSH public key tại `~/.ssh/id_ed25519.pub`:

~~~bash
# Đọc thông tin OS Login profile của danh tính hiện tại.
gcloud compute os-login describe-profile

# WRITE: thêm public key vào OS Login profile của danh tính.
gcloud compute os-login ssh-keys add \
  --key-file="$HOME/.ssh/id_ed25519.pub"

# READ-ONLY: liệt kê các public keys trong profile.
gcloud compute os-login ssh-keys list
~~~

Tùy phiên bản CLI và chính sách, có thể cấu hình **thời hạn hiệu lực** cho key thay vì lưu vô thời hạn; đọc trợ giúp `gcloud compute os-login ssh-keys add --help` để dùng đúng tùy chọn. Định dạng khóa, username và thời hạn còn phụ thuộc OS Login profile và khả năng hỗ trợ của hệ thống.

Lệnh `gcloud compute ssh` có thể thực hiện những bước tạo/import key và chuẩn bị tên đăng nhập theo cơ chế OS Login. Không nên tự gán một Linux username như `ubuntu` hoặc `root` khi chưa xem profile. Tên POSIX có thể được tạo từ danh tính Google Cloud và có quy tắc riêng.

### 6.3. Vòng đời key và thu hồi quyền

Khi một người rời nhóm:

1. Thu hồi IAM role hoặc quyền thành viên nhóm dẫn tới OS Login.
2. Kiểm tra quyền cấp trực tiếp từ các project/instance hoặc tổ tiên khác.
3. Đánh giá và xóa/cho hết hạn SSH key trong OS Login profile khi cần, theo quy trình phù hợp.
4. Xử lý những phiên SSH **đã thiết lập** nếu cần chấm dứt ngay, vì thu hồi quyền truy cập mới không luôn chủ động ngắt phiên shell đang chạy.
5. Kiểm tra local accounts, keys tự quản lý, các phương án SSH khác và audit logs nếu môi trường có cấu hình đặc biệt.

Thu hồi quyền đăng nhập mới là việc chính, nhưng đối với sự cố danh tính bị lộ, còn phải xét các token, private keys, quyền truy cập dữ liệu và sessions khác trong toàn hệ thống.

## 7. OS Login 2-step verification

### 7.1. Vai trò của 2-step verification

**OS Login 2-step verification (OS Login 2FA)** bổ sung bước kiểm tra danh tính bên cạnh cơ chế SSH được hỗ trợ. Mục đích là giảm rủi ro khi private key hoặc thông tin đăng nhập bị lộ.

Các điều kiện liên quan có thể gồm:

- Người dùng và loại tài khoản hỗ trợ xác thực hai bước theo Google Cloud/Cloud Identity.
- Tài khoản có phương thức xác thực hai bước phù hợp và đã đăng ký theo chính sách tổ chức.
- VM Linux và guest environment hỗ trợ OS Login 2FA.
- Cách SSH được sử dụng có thể hoàn thành thử thách xác thực; một số quy trình tự động/non-interactive có hạn chế.

**Bật metadata 2FA không tự làm mọi loại principal đáp ứng được thử thách**. Cần kiểm tra khả năng hỗ trợ của loại danh tính, VM image và công cụ SSH. Với tự động hóa, hãy dùng cơ chế quản trị có kiểm soát phù hợp thay vì đặt private SSH key cá nhân trong pipeline.

### 7.2. Ví dụ cấu hình

~~~bash
# WRITE: bật OS Login và yêu cầu OS Login 2FA ở cấp project.
gcloud compute project-info add-metadata \
  --project=retail-prod \
  --metadata=enable-oslogin=TRUE,enable-oslogin-2fa=TRUE
~~~

Để áp dụng cho một VM riêng, có thể dùng metadata instance theo cùng ý tưởng:

~~~bash
# WRITE: cấu hình instance sau khi xác nhận khả năng hỗ trợ.
gcloud compute instances add-metadata checkout-worker-01 \
  --project=retail-prod \
  --zone=asia-southeast1-a \
  --metadata=enable-oslogin=TRUE,enable-oslogin-2fa=TRUE
~~~

Nếu organization đã có chính sách bắt buộc cơ chế truy cập riêng, cần đối chiếu với chính sách đó. Với môi trường production, hãy thử đầy đủ luồng xác thực của người dùng thực tế trước khi bật đồng loạt; đừng loại bỏ phương án khôi phục đã được phê duyệt.

## 8. Kết hợp OS Login với IAP: SSH không cần external IP

### 8.1. Vì sao nên cân nhắc IAP TCP forwarding?

Một VM đặt trong VPC riêng có thể **không có external IPv4**. Để người quản trị vẫn SSH từ mạng bên ngoài, **IAP TCP forwarding** tạo đường hầm TCP thông qua dịch vụ IAP tới VM, với kiểm soát quyền phù hợp.

~~~mermaid
flowchart LR
    USER["Máy người quản trị"] --> IAM["IAM: quyền IAP + OS Login"]
    USER --> T["IAP TCP forwarding"]
    T --> FW["VPC firewall: TCP 22 từ IAP"]
    FW --> VM["VM Linux chỉ có internal IP"]
    IAM -. "OS Login authorization" .-> VM
    VM --> SSH["sshd → Linux shell"]
~~~

IAP bổ sung lớp **bảo vệ đường vào mạng**; OS Login kiểm soát **người được phép đăng nhập vào hệ điều hành**. Có thể triển khai cả hai để không phải công khai cổng TCP 22 của VM ra Internet.

### 8.2. Những yêu cầu cần có

| Hạng mục | Điều kiện |
| --- | --- |
| IAP API / cấu hình | Dịch vụ và môi trường được cấu hình phù hợp cho IAP TCP forwarding. |
| Quyền IAP | Principal có quyền IAP tunnel, thường từ `roles/iap.tunnelResourceAccessor` trên phạm vi được giao. |
| Quyền OS Login | Principal có role đăng nhập Linux thích hợp và các quyền bổ sung nếu áp dụng. |
| Quyền xem tài nguyên | `gcloud` có quyền đọc thông tin VM cần thiết để thiết lập kết nối. |
| VPC firewall | TCP 22 được phép từ dải nguồn của IAP TCP forwarding đến VM đúng đối tượng. |
| VM guest | Linux VM hỗ trợ OS Login, `sshd` đang phục vụ và không có chặn ở guest firewall. |
| Đường Internet của người dùng | Thiết bị người quản trị có kết nối ra dịch vụ IAP qua HTTPS thích hợp. |

Với IAP TCP forwarding IPv4, dải nguồn firewall thường được tài liệu Google Cloud sử dụng là **`35.235.240.0/20`**. Dải này cho phép đường từ dịch vụ IAP tới VM, **không đồng nghĩa cho phép mọi người trên Internet SSH**: IAM của IAP và OS Login vẫn bắt buộc. Khi thiết kế IPv6 hoặc mô hình đặc biệt, đối chiếu dải và cơ chế nguồn trong tài liệu hiện hành.

### 8.3. Ví dụ firewall hẹp cho IAP SSH

Giả sử VM được gắn network tag `iap-ssh` trong VPC `retail-vpc`. Firewall rule sau là ví dụ **thay đổi mạng**:

~~~bash
# WRITE: chỉ tạo khi tổ chức đã phê duyệt nguồn, đích và scope.
gcloud compute firewall-rules create allow-iap-ssh \
  --project=retail-prod \
  --network=retail-vpc \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags=iap-ssh
~~~

Nếu VM không có tag `iap-ssh`, rule theo tag trên **không áp dụng** cho VM đó. Trong hệ thống dùng **Shared VPC**, firewall thuộc đúng host VPC/network và quản trị ở project phù hợp. Ngoài VPC firewall rules, hierarchical firewall policy, guest firewall hoặc các quy tắc khác có thể tiếp tục chặn traffic.

Không mở `0.0.0.0/0` tới TCP 22 chỉ vì phiên IAP đầu tiên thất bại. Hãy kiểm tra theo lớp để giữ đúng mô hình bảo vệ.

### 8.4. Ví dụ SSH qua IAP

~~~bash
# READ/CONNECT: khởi tạo phiên SSH, không tự cấp quyền IAM.
gcloud compute ssh checkout-worker-01 \
  --project=retail-prod \
  --zone=asia-southeast1-a \
  --tunnel-through-iap
~~~

Lệnh có thể yêu cầu thao tác tương tác để tạo SSH key hoặc hoàn thành xác thực. Nó không tạo external IP cho VM. Nếu đủ các quyền và điều kiện, người dùng sẽ vào shell của VM với tài khoản POSIX do OS Login quản lý.

`gcloud compute ssh` cũng có thể kết nối trực tiếp qua đường mạng khác khi được phép. **Sử dụng IAP là một lựa chọn đường truyền**, không phải một chế độ thay thế OS Login. Nếu tổ chức yêu cầu tất cả SSH đi qua IAP, cần bảo đảm không còn đường SSH trực tiếp ngoài ý muốn.

## 9. Cấp quyền IAM theo quy trình

### 9.1. Đọc allow policy trước khi thay đổi

~~~bash
PROJECT_ID="retail-prod"

# READ-ONLY: xem IAM allow policy gắn trực tiếp lên project.
gcloud projects get-iam-policy "$PROJECT_ID" \
  --format="yaml(bindings)"
~~~

Kết quả này không hiển thị đầy đủ mọi **binding kế thừa từ folder/organization**, các quyền tại VM cụ thể, IAM deny và các điều kiện policy khác. Để xác định chính xác ai có quyền, cần phân tích cả phạm vi tổ tiên và cấu hình IAM hiện hành.

### 9.2. Ví dụ cấp OS Login cho nhóm vận hành

Những lệnh sau thay đổi policy thực, chỉ dùng khi đã được phê duyệt:

~~~bash
# WRITE: cấp đăng nhập thường trên project.
gcloud projects add-iam-policy-binding retail-prod \
  --member="group:vm-readers@example.com" \
  --role="roles/compute.osLogin"

# WRITE: cấp quyền quản trị hệ điều hành cho nhóm được kiểm soát.
gcloud projects add-iam-policy-binding retail-prod \
  --member="group:vm-maintainers@example.com" \
  --role="roles/compute.osAdminLogin"

# WRITE: cấp quyền dùng IAP tunnel ở cấp project (có thể thu hẹp hơn).
gcloud projects add-iam-policy-binding retail-prod \
  --member="group:vm-iap-users@example.com" \
  --role="roles/iap.tunnelResourceAccessor"
~~~

Ví dụ dùng **project scope** để dễ hiểu, nhưng trên production nên cân nhắc scope nhỏ hơn và IAM Conditions nếu có nhu cầu phân quyền theo VM, IP hoặc thời gian. Không cấp quyền quản trị toàn project cho nhóm chỉ cần SSH một VM.

Nếu VM gắn service account, cần kiểm tra điều kiện dùng danh tính đó. Khi thật sự cần cấp quyền actAs trên một service account xác định:

~~~bash
# WRITE: grant trên service account cụ thể, không phải mọi service account.
gcloud iam service-accounts add-iam-policy-binding \
  vm-runtime@retail-prod.iam.gserviceaccount.com \
  --project=retail-prod \
  --member="group:vm-maintainers@example.com" \
  --role="roles/iam.serviceAccountUser"
~~~

`roles/iam.serviceAccountUser` là quyền nhạy cảm vì cho phép sử dụng danh tính service account trong các thao tác hỗ trợ. Cần đánh giá quyền mà service account đó đang sở hữu; không cấp một cách máy móc chỉ để sửa lỗi SSH mà chưa xác nhận tài nguyên và nguyên nhân.

### 9.3. Thu hồi và kiểm chứng

~~~bash
# WRITE: thu hồi binding đăng nhập thường tại project.
gcloud projects remove-iam-policy-binding retail-prod \
  --member="group:vm-readers@example.com" \
  --role="roles/compute.osLogin"
~~~

Thu hồi một binding không chứng minh người dùng đã mất tất cả quyền, vì có thể còn role trực tiếp, qua nhóm khác hoặc từ tổ tiên. Kiểm tra quyền hiệu lực và những đường truy cập khác; xử lý sessions đang hoạt động khi tình huống yêu cầu thu hồi tức thời.

## 10. Tình huống triển khai: hệ thống bán hàng production

Giả sử tổ chức có các thành phần:

- API đặt hàng chạy trên **Cloud Run**.
- **Cloud SQL** lưu dữ liệu giao dịch.
- **Cloud Storage** chứa tệp ảnh và dữ liệu tĩnh.
- Một số **Compute Engine VM Linux** chạy tác vụ đồng bộ dữ liệu và công cụ điều tra sự cố.
- **GKE** chạy các workload khác, có quy trình quản trị node riêng.
- Một **VPC production** không cấp external IP cho các VM quản trị thông thường.

Đội bảo mật muốn người dùng chỉ SSH tới VM được giao, nhân sự vận hành mới có quyền `sudo`, và mọi thao tác bảo trì đi qua IAP.

### 10.1. Thiết kế quyền theo trách nhiệm

| Đối tượng | Nhu cầu | Quyền/phương án đề xuất |
| --- | --- | --- |
| Nhóm phát triển ứng dụng | Đọc log và kiểm tra trạng thái service trên VM liên quan. | OS Login thường trong phạm vi VM được giao; quyền Cloud Logging riêng nếu cần. |
| Nhóm quản trị hệ thống | Cài bản vá, khởi động dịch vụ và khắc phục sự cố được duyệt. | `osAdminLogin` trên phạm vi được giao, quy trình phê duyệt và audit. |
| Nhóm bảo mật | Rà soát người được SSH và cấu hình metadata. | Quyền đọc IAM/policy/asset phù hợp, không nhất thiết là quyền shell root. |
| CI/CD | Triển khai ứng dụng qua cơ chế tự động được quản lý. | Danh tính workload/deployer riêng; tránh dùng private key SSH cá nhân. |
| Nhân sự trực hỗ trợ | Kết nối VM không có external IP để điều tra khi có sự cố. | IAP tunnel access + OS Login thích hợp + khả năng xem VM. |

**Không nên cho service account của Cloud Run quyền `osAdminLogin` chỉ vì ứng dụng cần gọi Cloud SQL.** Quyền quản trị hệ điều hành VM khác với quyền kết nối database hoặc đọc object trên Cloud Storage. Tách danh tính **quản trị máy**, **triển khai** và **runtime** giúp giảm phạm vi ảnh hưởng khi credential bị lộ.

### 10.2. Luồng truy cập từ người vận hành

~~~mermaid
sequenceDiagram
    participant E as Kỹ sư trực
    participant I as IAM / IAP
    participant V as Compute Engine VM
    participant O as OS Login / Linux
    E->>I: gcloud compute ssh --tunnel-through-iap
    I->>I: Kiểm tra quyền tunnel
    I->>V: Mở TCP tunnel tới port 22
    E->>O: Xác thực SSH và OS Login
    O->>O: Kiểm tra danh tính / quyền đăng nhập
    O-->>E: Shell thường hoặc quyền admin theo role
~~~

Trong thực tế, việc xác thực SSH, tra cứu OS Login và kết nối qua tunnel là một luồng kỹ thuật nhiều bước. Sơ đồ gom các bước chính để phân biệt **IAP quyết định đường vào**, còn **OS Login quyết định đăng nhập Linux và đặc quyền**.

### 10.3. Quy trình onboarding và offboarding

**Onboarding:**

1. Quản lý xác nhận VM cần truy cập và nhiệm vụ cụ thể.
2. Thêm người dùng vào group OS Login thường hoặc admin tương ứng.
3. Thêm quyền IAP ở phạm vi phù hợp, kiểm tra quyền đọc thông tin VM và những yêu cầu service account nếu có.
4. Xác nhận người dùng đã đăng ký phương thức 2FA phù hợp khi policy yêu cầu.
5. Thử đăng nhập từ đường mạng được cho phép và ghi lại phạm vi quyền.

**Offboarding hoặc đổi vai trò:**

1. Thu hồi thành viên group hoặc binding liên quan.
2. Kiểm tra những quyền còn lại tại project, instance và tổ tiên.
3. Xử lý SSH keys và sessions theo yêu cầu thu hồi.
4. Rà soát thay đổi trên VM nếu người đó từng có quyền `sudo`.
5. Ghi nhận ngày xử lý và người xác nhận.

Đối với quyền production nhạy cảm, tổ chức có thể áp dụng **truy cập đặc quyền có thời hạn** và kiểm soát phê duyệt phù hợp thay vì để role `osAdminLogin` tồn tại vô thời hạn.

## 11. Kiểm tra SSH an toàn và giám sát

### 11.1. Bộ kiểm tra read-only

~~~bash
# Kiểm tra metadata project/instance.
gcloud compute project-info describe \
  --project=retail-prod \
  --format="yaml(commonInstanceMetadata.items)"

gcloud compute instances describe checkout-worker-01 \
  --project=retail-prod \
  --zone=asia-southeast1-a \
  --format="yaml(name,networkInterfaces,metadata.items,serviceAccounts)"

# Kiểm tra OS Login profile của danh tính gcloud hiện tại.
gcloud compute os-login describe-profile

# Kiểm tra IAM binding trực tiếp tại project.
gcloud projects get-iam-policy retail-prod \
  --format="yaml(bindings)"

# Xem firewall rules để đối chiếu đường IAP đến VM.
gcloud compute firewall-rules list \
  --project=retail-prod
~~~

Với Shared VPC, danh sách firewall rules phải được kiểm tra ở **host project chứa network**. Những lệnh trên chỉ cho thấy cấu hình và quyền mà danh tính hiện tại xem được; để xác nhận truy cập, vẫn cần thử kết nối với đúng principal và phân tích các policy có hiệu lực.

### 11.2. Log nào trả lời câu hỏi nào?

| Nguồn | Câu hỏi có thể hỗ trợ giải đáp |
| --- | --- |
| **Cloud Audit Logs** liên quan thay đổi IAM/Compute Engine metadata | Ai thay đổi binding, metadata hoặc tài nguyên quản trị và khi nào? |
| **OS Login API logs**, theo loại hoạt động được ghi và cấu hình logging | Có hoạt động quản lý profile/SSH keys hoặc sử dụng OS Login API nào liên quan? |
| **IAP audit/telemetry** theo phạm vi hỗ trợ | Ai dùng IAP TCP forwarding, có lỗi kiểm soát truy cập tunnel không? |
| **Linux auth logs/journald** của VM | `sshd` có chấp nhận hay từ chối đăng nhập? Tài khoản Linux và địa chỉ nguồn nào xuất hiện? |
| **Cloud Logging/Monitoring** của VM, nếu được cấu hình | Log và cảnh báo có được tập trung để điều tra mà không cần SSH thường xuyên không? |

Không phải mọi nguồn tự động ghi tất cả sự kiện hoặc có retention giống nhau. Xác minh Audit Logs được bật theo loại log, vị trí lưu, quyền truy cập và chính sách giữ dữ liệu. Một phiên SSH không thành công có thể cần đối chiếu **log IAP** và **log SSH trong guest OS** mới thấy nguyên nhân.

### 11.3. Đo độ tin cậy của đường quản trị

Các chỉ số nội bộ hữu ích:

- Tỷ lệ VM Linux production có OS Login được bật theo baseline.
- Tỷ lệ kết nối quản trị dùng IAP so với đường SSH trực tiếp, khi chính sách yêu cầu IAP.
- Số người và group có quyền `osAdminLogin`; thời hạn của quyền đặc biệt.
- Thời gian thu hồi quyền khi nhân sự đổi nhóm hoặc rời tổ chức.
- Tỷ lệ lỗi SSH do IAM, IAP, mạng hoặc SSH daemon.
- Mức độ đầy đủ của audit logs và quy trình truy cập khẩn cấp.

Mục tiêu là **giảm quyền dư thừa nhưng vẫn duy trì khả năng xử lý sự cố**. Nếu bảo mật khiến đội trực không có bất kỳ đường khôi phục hợp lệ nào khi IAP hoặc IAM gặp vấn đề, thiết kế chưa cân bằng được rủi ro và độ tin cậy.

## 12. Xử lý sự cố theo đúng lớp

### 12.1. Bảng chẩn đoán

| Triệu chứng | Nguyên nhân có thể gặp | Cách kiểm tra |
| --- | --- | --- |
| `Permission denied (publickey)` | SSH key không nằm trong OS Login profile, IAM OS Login chưa đủ, guest OS chưa cấu hình đúng hoặc username sai. | Kiểm tra profile/key, role, guest environment và auth logs. |
| `403` khi tạo IAP tunnel | Thiếu quyền tunnel, IAM Conditions không thỏa hoặc IAP API/policy từ chối. | Xác định principal, tài nguyên và binding IAP. |
| IAP tunnel có nhưng SSH timeout | Firewall đến TCP 22, guest firewall, `sshd` hoặc route/network không đáp ứng. | Xem dải nguồn IAP, network tag, port và log guest. |
| Có quyền OS Login nhưng bị từ chối trên VM có service account | Có thể thiếu quyền bổ sung sử dụng service account theo luồng truy cập. | Đọc serviceAccounts của VM và kiểm tra yêu cầu `iam.serviceAccounts.actAs`. |
| Đăng nhập được nhưng không thể `sudo` | Chỉ được `roles/compute.osLogin`, không có quyền admin hoặc cấu hình OS khác giới hạn. | Kiểm tra IAM role hiệu lực và sudo policy. |
| Lỗi sau khi bật `enable-oslogin=TRUE` | VM trước đây dựa vào metadata SSH keys, thiếu IAM hoặc guest environment chưa hỗ trợ. | So sánh metadata, role, guest logs; thực hiện kế hoạch khôi phục. |
| Một người có quyền project nhưng VM báo không có quyền | Instance metadata, IAM Conditions, deny policies hoặc phạm vi role khác dự kiến. | Xác định chính sách hiệu lực ở tổ tiên và tại VM. |
| OS Login 2FA liên tục thất bại | Tài khoản chưa đăng ký phương thức hợp lệ, workflow không hỗ trợ hoặc guest image không tương thích. | Đọc hướng dẫn hỗ trợ theo loại tài khoản/image, kiểm thử tương tác. |
| SSH có thể đi trực tiếp dù muốn bắt buộc IAP | External IP, firewall ingress hoặc bastion path chưa được khóa. | Kiểm tra IP, ingress, đường truy cập thực tế và chính sách mạng. |
| Cấp lại role vẫn chưa vào được | Vấn đề ở lớp mạng/SSH daemon, IAM propagation hoặc key/session. | Kiểm tra từ DNS/IP → IAP → TCP 22 → SSH auth → OS Login. |

### 12.2. Quy trình điều tra ngắn

1. **Đúng VM chưa?** Kiểm tra project ID, zone, instance name, internal/external IP.
2. **Đúng principal chưa?** `gcloud auth list` để biết tài khoản CLI; kiểm tra danh tính thật của người/automation và quyền được cấp.
3. **Có đường tới TCP 22 không?** Nếu dùng IAP, kiểm tra role IAP, mạng, firewall và `--tunnel-through-iap`.
4. **OS Login bật theo cách nào?** Kiểm tra metadata project, instance và organization policy.
5. **Role OS Login phù hợp chưa?** Phân biệt quyền đăng nhập thường, quyền admin và những điều kiện bổ sung.
6. **SSH key/profile đúng chưa?** Kiểm tra public key, thời hạn, username POSIX và client dùng key nào.
7. **Guest OS có nhận kết nối không?** Xem `sshd`, Linux auth logs và trạng thái guest environment.
8. **Thử lại theo kịch bản nhỏ nhất:** kết nối từ danh tính kiểm thử, ghi lại lỗi chính xác và thời điểm để đối chiếu logs.

Tránh cách “sửa nhanh” bằng cách cấp `roles/owner`, `roles/editor`, thêm external IP hoặc mở `0.0.0.0/0` tới TCP 22. Những thay đổi đó làm tăng rủi ro, đồng thời che đi nguyên nhân ban đầu.

### 12.3. Phương án khôi phục quản trị

Khi bật OS Login hay 2FA trên production, đội hạ tầng nên có **runbook break-glass**:

- Người được phê duyệt truy cập khẩn cấp và cách xác thực độc lập.
- Phạm vi VM/project được khôi phục, điều kiện kích hoạt và thời hạn quyền tạm.
- Cách kiểm chứng guest environment, metadata và IAM khi luồng SSH thông thường hỏng.
- Phương án sửa cấu hình bằng công cụ quản trị được tổ chức cho phép khi SSH không hoạt động.
- Audit và review lại sau khi xử lý sự cố.

Không mặc định có thể “vào serial console” trong mọi môi trường: truy cập serial có điều kiện bảo mật, IAM và chính sách riêng. Thiết kế phương án dự phòng theo công cụ thực sự được tổ chức bật và kiểm soát.

## 13. Bài thực hành

### Bài 1 — Chọn role

Ba người cần truy cập cùng một VM Linux production:

1. Lập trình viên chỉ xem log ứng dụng.
2. Nhân viên SRE được phép cập nhật cấu hình hệ điều hành và chạy `sudo`.
3. Kiểm toán viên chỉ xem danh sách người có quyền, không vào shell.

**Gợi ý:** người (1) bắt đầu với `roles/compute.osLogin` và quyền đọc file Linux phù hợp; người (2) cân nhắc `roles/compute.osAdminLogin` trong phạm vi và thời hạn được duyệt; người (3) dùng quyền đọc IAM/audit phù hợp, không cần OS Login.

### Bài 2 — Thiết kế SSH không có external IP

VM `checkout-worker-01` không có external IPv4, chạy trong VPC `retail-vpc`. Hãy nêu những điều kiện để kỹ sư SSH qua IAP.

**Gợi ý:** IAP API/tunnel, `roles/iap.tunnelResourceAccessor`, OS Login role, quyền xem VM, metadata OS Login, firewall cho TCP 22 từ dải nguồn IAP tới VM, `sshd` và danh tính/SSH key hợp lệ. Nếu VM có service account, xác minh yêu cầu IAM bổ sung.

### Bài 3 — Đọc metadata

Chạy các lệnh **read-only**:

~~~bash
gcloud compute project-info describe \
  --project=retail-prod \
  --format="yaml(commonInstanceMetadata.items)"

gcloud compute instances describe checkout-worker-01 \
  --project=retail-prod \
  --zone=asia-southeast1-a \
  --format="yaml(metadata.items)"
~~~

**Câu hỏi:** nếu project có `enable-oslogin=TRUE` nhưng instance metadata là `enable-oslogin=FALSE`, phải xem thêm yếu tố nào để kết luận trạng thái OS Login có hiệu lực? Vì sao không nên thay đổi instance metadata khi organization policy bắt buộc OS Login?

### Bài 4 — Lỗi `publickey`

Một người có quyền SSH qua IAP nhưng nhận `Permission denied (publickey)`. Hãy mô tả cách phân biệt **IAP thành công** với **OS Login/SSH key bị từ chối**, bao gồm cách xem public key trong profile, username và guest auth logs.

### Bài 5 — Thu hồi quyền

Một nhân viên rời nhóm SRE, từng có `osAdminLogin` qua group và đã mở phiên SSH tới VM. Hãy trình bày quy trình thu hồi quyền, kiểm tra binding khác, xử lý phiên đang tồn tại, rà soát log và xác nhận người đó không còn đường truy cập khác.

### Bài 6 — Đánh giá ảnh hưởng đến CI/CD

Một script triển khai cũ SSH vào VM bằng key lưu trong metadata project. Platform team muốn bật OS Login trên toàn project. Hãy đề xuất kế hoạch migration: kiểm kê script, chọn danh tính và cơ chế deployment phù hợp, thử quyền, chuyển đổi trên nonproduction, kiểm tra log/rollback và giới hạn quyền máy tự động.

## 14. Checklist trước khi áp dụng trên production

| Hạng mục | Điều cần xác minh |
| --- | --- |
| **Image và guest environment** | Linux image hỗ trợ OS Login, SSH daemon/PAM/NSS phù hợp. |
| **Project/instance metadata** | Giá trị `enable-oslogin`, `enable-oslogin-2fa` và khả năng ghi đè đã được hiểu đúng. |
| **Organization Policy** | Có/không có constraint bắt buộc OS Login; chính sách và ngoại lệ được quản lý. |
| **Principal và role** | Phân biệt người đăng nhập thường, OS admin, IAP user và danh tính tự động. |
| **Service account gắn VM** | Kiểm tra quyền bổ sung nếu yêu cầu, tránh cấp rộng. |
| **Khóa SSH** | Private keys an toàn, public keys/profile và vòng đời/thu hồi được quản lý. |
| **2-step verification** | Loại danh tính, image và workflow tương thích; có kiểm thử thực tế. |
| **Đường SSH** | External IP/IAP, ingress TCP 22, đúng network target, guest firewall và route. |
| **Logging/audit** | Theo dõi IAM, OS Login, IAP và Linux auth logs với retention hợp lý. |
| **Tự động hóa** | Metadata và IAM qua IaC/review; không lưu SSH key cá nhân trong pipeline. |
| **Khôi phục** | Có break-glass runbook, người chịu trách nhiệm và phương án kiểm thử. |
| **Chi phí/độ tin cậy** | Theo dõi VM, logging, đường kết nối, thời gian phục hồi và phạm vi truy cập. |

## 15. Tài liệu chính thức và điểm cần ghi nhớ

OS Login, hỗ trợ 2-step verification, IAM role, IAP và các phương án xác thực có thể thay đổi theo phiên bản dịch vụ/guest image. Khi triển khai trên Google Cloud, kiểm tra tài liệu hiện hành:

- [OS Login overview](https://cloud.google.com/compute/docs/oslogin)
- [Set up OS Login](https://cloud.google.com/compute/docs/oslogin/set-up-oslogin)
- [Set up OS Login with 2-step verification](https://cloud.google.com/compute/docs/oslogin/set-up-oslogin-2fa)
- [Connect to Linux VMs using IAP](https://cloud.google.com/compute/docs/connect/ssh-using-iap)
- [IAP TCP forwarding](https://cloud.google.com/iap/docs/using-tcp-forwarding)
- [SSH best practices for Compute Engine](https://cloud.google.com/compute/docs/connect/ssh-best-practices)
- [Understanding IAM roles](https://cloud.google.com/iam/docs/understanding-roles)
- [Organization Policy overview](https://cloud.google.com/resource-manager/docs/organization-policy/overview)
- [gcloud compute os-login reference](https://cloud.google.com/sdk/gcloud/reference/compute/os-login)

**OS Login đặt quyền đăng nhập Linux vào mô hình IAM; IAP cung cấp đường SSH được kiểm soát; VPC firewall quyết định mạng có đi qua hay không.** Khi xác định rõ trách nhiệm từng lớp, bạn có thể kiểm soát quyền quản trị VM theo nhóm, tách `sudo` khỏi quyền đăng nhập thường, thu hồi quyền có hệ thống và duy trì khả năng xử lý sự cố mà không phải công khai SSH cho toàn Internet.

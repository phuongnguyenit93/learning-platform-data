# Backup vaults và bảo vệ bản sao lưu khỏi xóa trái phép

Trong module `CLOUD_PROVIDERS_GCP`, người học đi từ quản lý project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, rồi vận dụng kiến thức để bảo vệ tài nguyên, tự động hóa phát hành, theo dõi độ tin cậy và chi phí. Chương **Sao lưu và phục hồi thảm họa** đặt câu hỏi quan trọng: nếu người vận hành bấm xóa nhầm, một service account bị chiếm quyền hoặc ransomware tìm cách phá hủy dữ liệu, liệu bản sao lưu có còn tồn tại và khôi phục được không?

Bài này giới thiệu **Backup vaults** của **Google Cloud Backup and DR**, đặc biệt các cơ chế **enforced retention**, **retention lock**, **project liens**, **IAM separation of duties** và **access restrictions**. Bạn sẽ thiết kế một kho sao lưu biệt lập, cấu hình backup plan cho disk thử nghiệm, xác minh trạng thái bảo vệ bằng thao tác đọc, và xây quy trình phục hồi có kiểm soát.

> **Cảnh báo vận hành:** Enforced retention có thể giữ dữ liệu và tiếp tục phát sinh phí cho toàn bộ thời gian bảo vệ. Khi retention lock đã có hiệu lực, bạn không thể giảm kỳ retention hoặc gỡ lock. Không thử các thao tác phá hủy, khóa retention nhiều năm hoặc mua tài nguyên thật trong production khi chưa có thay đổi được phê duyệt. Bài lab sử dụng project staging và chỉ hướng dẫn xác minh chính sách theo cách an toàn.

## 1. Mối đe dọa: mất dữ liệu nguồn và mất luôn bản sao lưu

Backup chỉ hữu ích nếu còn nguyên vẹn **khi cần restore**. Cần xét ít nhất bốn tình huống:

| Mối đe dọa | Ví dụ | Điều cần chống |
| --- | --- | --- |
| Xóa nhầm | Quản trị viên xóa disk, backup hoặc project khi cleanup. | Không thể xóa recovery point trước thời hạn bảo vệ. |
| Tấn công ransomware | Tài khoản có quyền cao bị chiếm và kẻ tấn công xóa cả bản sao lưu. | Cô lập quyền điều hành sản xuất với quyền quản lý vault, cưỡng chế retention. |
| Thay đổi chính sách | Kẻ xấu giảm retention còn một ngày rồi chờ xóa. | Khóa khả năng **giảm** enforced minimum retention sau ngày hiệu lực. |
| Xóa project chứa vault | Người có quyền Resource Manager tìm cách xóa project để vượt qua retention. | Project lien, IAM riêng và phê duyệt nhiều người cho thao tác quản trị lien. |
| Cướp quyền khôi phục | Người không được phép restore dữ liệu sang project khác. | Hạn chế backup/restore scope, IAM, audit logs và approval. |
| Tài nguyên bị mã hóa sai | CMEK bị vô hiệu hóa hoặc key không truy cập được khi restore. | Quản trị vòng đời khóa riêng, kiểm tra restore và phân tách quản trị KMS. |

**Không nên nhầm:** Backup, snapshot, replica và high availability giải quyết các mục tiêu khác nhau. Replica có thể sao chép cả lỗi xóa dữ liệu; HA giúp giảm gián đoạn do sự cố hạ tầng nhưng không nhất thiết giữ bản dữ liệu đúng ở thời điểm trước khi thao tác sai xảy ra. Vaulted backups bổ sung recovery points có vòng đời và chính sách bảo vệ độc lập.

## 2. Backup vault là gì?

Trong Google Cloud Backup and DR, **backup vault** là tài nguyên lưu trữ do Google quản lý, có khả năng **cô lập, bất biến trong thời gian enforced retention và chống xóa sớm**. Không phải tạo một bucket Cloud Storage bất kỳ rồi gắn tên "vault". Backup vault có mô hình tài nguyên và API riêng:

- **Backup vault:** container cao nhất, lưu cấu hình location, minimum enforced retention, retention inheritance, lock, encryption và access restriction.
- **Data source:** tài nguyên con thể hiện đối tượng được bảo vệ, chẳng hạn một Compute Engine disk hoặc instance; Backup and DR tạo khi có backup phù hợp.
- **Backup:** recovery point cụ thể, gắn với data source và thời gian hết hạn/bảo vệ.
- **Backup plan:** chính sách **khi nào sao lưu và giữ bao lâu** cho loại workload được hỗ trợ.
- **Backup plan association:** liên kết giữa một resource cụ thể và backup plan để backup tự động.
- **Backup vault service agent:** danh tính do Google quản lý, được dùng để thao tác cần thiết lên resource ở project được bảo vệ.

~~~mermaid
flowchart TB
  ORG[Google Cloud Organization]
  ORG --> HUB[Backup hub project]
  ORG --> SPOKE[Workload project]
  HUB --> VAULT[Backup vault]
  HUB --> PLAN[Backup plan / daily rule]
  VAULT --> SOURCE[Data source: disk-orders]
  SOURCE --> B1[Recovery point 1]
  SOURCE --> B2[Recovery point 2]
  PLAN --> ASSOCIATION[Backup plan association]
  ASSOCIATION --> DISK[Compute Engine disk]
  SPOKE --> DISK
  VAULT --> IAM[Vault IAM + access restriction]
  VAULT --> RETENTION[Minimum retention + lock]
  HUB --> LIEN[Project lien]
  RETENTION --> B1
  RETENTION --> B2
~~~

### 2.1. Workload và giao diện quản lý

Các workload được **Google Cloud console-based backup plans** hỗ trợ gồm Compute Engine instances, Compute Engine disks, Cloud SQL instances, AlloyDB clusters và Filestore instances, tùy loại và vị trí. Một số workload khác như Google Cloud VMware Engine, Oracle hoặc SQL Server có mô hình **appliance management console** và giới hạn khác. Không giả định cùng cách cấu hình, location hoặc CMEK của một workload dùng được cho tất cả.

Các backup transaction logs của Cloud SQL/AlloyDB liên quan PITR có thể được lưu **ngoài backup vault**. Vì vậy, câu nói "toàn bộ dữ liệu phục hồi và tất cả transaction logs đều được giữ bất biến trong vault" là sai nếu không đối chiếu sản phẩm và cấu hình riêng. Cần xác định chính xác những thành phần nào được bảo vệ bởi vault.

### 2.2. Centralized hub/spoke hay mỗi project một vault?

| Mô hình | Cách tổ chức | Lợi ích | Đánh đổi |
| --- | --- | --- | --- |
| **Centralized hub/spoke** | Backup vaults/plans trong project do đội sao lưu quản lý; workload ở các service projects. | Phân tách quyền với team vận hành workload; quản trị retention/audit tập trung. | Phải cấp quyền cho service agents qua project, xác định trách nhiệm vận hành rõ. |
| **Decentralized** | Mỗi workload project có vault và plan riêng. | Đội ứng dụng tự quản, ít cross-project IAM. | Một principal bị chiếm quyền có thể kiểm soát nhiều thành phần cùng project; dễ lệch policy. |

Để chống ransomware và xóa trái phép, thường nên cân nhắc **project backup hub riêng** với người quản trị, chính sách bảo mật và vòng đời khác với project nguồn. Project hub và spoke vẫn có thể ở cùng organization để áp dụng access restriction phù hợp.

## 3. Hai loại retention phải được phân biệt

Một backup được điều khiển bởi **assigned retention** trong backup plan và **enforced retention** ở vault. Chúng không đồng nghĩa.

| Khái niệm | Nơi định nghĩa | Ý nghĩa |
| --- | --- | --- |
| **Assigned retention** hay `Delete backups after` | Backup rule trong backup plan | Thời gian dự kiến giữ backup; hết hạn sẽ được hệ thống dọn tự động theo chính sách. |
| **Minimum enforced retention** hay `Prevent backup deletion` | Backup vault | Sàn bắt buộc: không ai được xóa thủ công backup trước khi khoảng bảo vệ này qua đi. |
| **Retention inheritance mode** | Chọn khi tạo vault | Quyết định thời gian chống xóa của mỗi backup theo minimum vault hay theo expiration từ backup rule. |
| **Retention lock** | Cấu hình vault với ngày hiệu lực | Sau ngày hiệu lực, không thể **giảm** minimum enforced retention; chỉ được tăng. |

Minimum enforced retention của vault được cấu hình từ **0 ngày đến tối đa 99 năm**, nhưng từng resource type/backup rule có **giới hạn cụ thể**. Giá trị 0 không tạo mức bảo vệ chống xóa đáng kể cho backup; với dữ liệu quan trọng, cần quy định lớn hơn 0 theo yêu cầu kinh doanh và pháp lý.

Backup rule dành cho resource sử dụng vault phải có retention **ít nhất bằng minimum enforced retention**. Ví dụ không hợp lệ: vault minimum 30 ngày nhưng backup plan giữ 7 ngày.

### 3.1. Hai chế độ inheritance

Khi tạo vault, chọn một trong hai chế độ:

1. `inherit-vault-retention` (mặc định): khoảng **enforced retention** của backup kế thừa mức minimum vault. Backup plan vẫn quản lý thời gian expiration được gán, nhưng khoảng cấm xóa thủ công có thể ngắn hơn assigned retention.
2. `match-backup-expire-time`: khoảng chống xóa của từng backup được gắn đến **backup expiration** theo retention rule của backup plan. Đây là phương án mạnh hơn khi muốn ngăn xóa thủ công cho **toàn bộ vòng đời** của bản sao lưu, thay vì chỉ một số ngày đầu.

Chế độ inheritance **không thể đổi sau khi tạo vault**. Hãy quyết định ngay khi thiết kế vault. Với môi trường compliance, thường cân nhắc `match-backup-expire-time`, nhưng cần review chi phí và các loại backup được sử dụng.

### 3.2. Ví dụ 7 ngày và 30 ngày

Giả sử:

- Vault minimum enforced retention: **7 ngày**.
- Backup rule: giữ recovery point **30 ngày**.
- Backup được tạo vào ngày 01/11, ngày hết hạn thông thường là sau 30 ngày.

| Chế độ vault | Cửa sổ không được xóa thủ công | Diễn giải |
| --- | --- | --- |
| `inherit-vault-retention` | Ít nhất 7 ngày đầu | Sau mốc enforced minimum, chính sách có thể cho phép xóa thủ công backup trước ngày hết hạn theo các quyền/quy tắc còn lại. |
| `match-backup-expire-time` | Đến hết kỳ backup retention 30 ngày | Không thể xóa thủ công trong toàn bộ 30 ngày; hệ thống xử lý xóa khi backup hết hạn. |

**Điểm bảo mật:** Đừng chỉ thấy "backup plan giữ 30 ngày" rồi kết luận "30 ngày bất biến". Phải đọc **vault inheritance mode và thời gian enforced retention thực tế của backup**.

### 3.3. Khi sửa minimum retention

Theo tài liệu Backup and DR:

- Vault **unlocked**: người có quyền có thể tăng hoặc giảm minimum retention cho **backup tạo sau khi thay đổi**.
- Vault **locked**: chỉ có thể tăng minimum retention, không được giảm.
- Thay đổi minimum của vault **không rút ngắn hoặc kéo dài enforced retention đã ghi nhận cho backup hiện có**.
- Nếu minimum mới lớn hơn retention của backup plan, các **console-based plans** có thể chặn thay đổi; phải kiểm tra và cập nhật các plan tương thích theo đúng quy trình.

Nhờ vậy, giảm minimum của một vault chưa khóa không lập tức giải phóng backup đã được tạo với enforced retention dài hơn. Tuy nhiên, nó có thể làm **backup tạo về sau** ít được bảo vệ hơn. Đó là lý do khóa policy có ý nghĩa đối với phòng chống tấn công kéo dài.

## 4. Retention lock: chống sửa chính sách để xóa backup về sau

Enforced retention chống xóa sớm từng backup. **Retention lock** bảo vệ **mức minimum enforced retention của vault** khỏi hành động giảm xuống sau ngày lock có hiệu lực.

Quy trình lock có ba trạng thái chính:

~~~mermaid
flowchart LR
  U[Unlocked] -->|Set lock effective date| P[Lock pending]
  P -->|Effective date reached| L[Locked]
  P -->|Authorized edit before effective date| U
  L -->|Can increase minimum only| L
  L -.->|Cannot remove lock or reduce minimum| X[Denied]
~~~

- **Unlocked:** có thể sửa minimum theo quyền và điều kiện.
- **Pending lock:** đã chọn ngày hiệu lực; trước ngày đó vẫn có thể điều chỉnh hoặc gỡ lock theo cơ chế được hỗ trợ.
- **Locked:** khi ngày hiệu lực đến, **không thể gỡ lock hoặc giảm minimum**, kể cả Project Owner. Chỉ được tăng minimum.

Đây là một quyết định bảo mật có hậu quả dài hạn. Nếu một vault vô tình lock minimum retention quá lớn, có thể không có cách giảm nó trước khi dữ liệu vượt thời hạn. Hãy dùng **change review nhiều người** khi thiết lập hoặc tăng retention, với dữ liệu/thời hạn đã được Legal, Security và Backup owners phê duyệt.

Trong lab, bạn có thể tạo một vault thử nghiệm **chưa lock** để quan sát cấu hình, rồi nghiên cứu màn hình lock bằng thao tác đọc. **Không ấn xác nhận lock có hiệu lực vĩnh viễn trong bài học này.** Nếu tổ chức cần chứng minh retention lock thực tế, thực hiện trong môi trường compliance test riêng với người có trách nhiệm phê duyệt và cân nhắc chi phí không thể đảo ngược.

## 5. Project liens ngăn xóa cả project chứa vault

Nếu một người có quyền `resourcemanager.projects.delete` xóa project chứa vault, retention ở cấp backup cần có lớp bảo vệ bổ sung. **Project lien** là rào chắn của Resource Manager, ngăn xóa project khi lien còn hiệu lực.

Từ **ngày 01/11/2026**, Backup and DR tự động áp dụng **project-level lien** với project chứa backup vault có **backup đang được enforced retention bảo vệ**. Hãy xác minh trạng thái thực tế trên project hub, vì vault chưa có backup được bảo vệ hoặc môi trường đặc thù có thể không đáp ứng điều kiện auto-lien. Với project test không có enforced retention, có thể cần tạo lien thủ công theo hướng dẫn quản trị.

### 5.1. Lien không phải quyền bất khả xâm phạm

Principal có quyền phù hợp vẫn có thể tìm cách **gỡ lien**, nên lien chỉ là một lớp phòng vệ. Đội bảo mật cần hạn chế `roles/resourcemanager.lienModifier`, dùng **Privileged Access Manager (PAM)** để yêu cầu **nhiều người phê duyệt** trước khi cấp quyền nâng cao tạm thời.

| Thành phần | Bảo vệ | Giới hạn |
| --- | --- | --- |
| Enforced retention | Không xóa backup đang trong thời gian bảo vệ. | Không tự chặn tất cả thay đổi IAM và các backup trong tương lai. |
| Retention lock | Chặn giảm minimum retention về sau. | Không thay thế việc tạo backup đúng lịch; thời gian bảo vệ vẫn hết hạn. |
| Project lien | Chặn thao tác xóa project chứa vault. | Có thể bị gỡ nếu principal có đủ quyền; cần PAM/SoD. |
| Vault IAM | Hạn chế ai quản lý vault, restore và xem backups. | Sai phân quyền/role quá rộng vẫn là nguy cơ. |
| Access restriction | Giới hạn các nguồn backup/restore hợp lệ. | Không thay IAM và phải chọn đúng lúc tạo vault. |
| Restore drill | Kiểm chứng backup thực sự dùng được. | Không ngăn hành động phá hoại; cần quy trình độc lập. |

Ví dụ kiểm tra lien bằng gcloud (chỉ đọc):

~~~bash
gcloud alpha resource-manager liens list
~~~

Ở môi trường sử dụng bản CLI khác, kiểm tra cú pháp/flags hiện có để lọc đúng project trước khi kết luận. Không gỡ lien trong production chỉ để chứng minh rằng việc xóa project là có thể. Khi thực hiện diễn tập, chỉ kiểm tra metadata lien và rà soát quyền người được phép chỉnh sửa.

## 6. Vault access restrictions: giới hạn nơi được backup và restore

Khi tạo vault, cấu hình **access restriction** quyết định các project/organization có thể sử dụng backup vault làm nguồn hoặc đích cho backup/restore. Giá trị này **không thể thay đổi sau khi tạo**.

| Mode gcloud | Ý nghĩa | Phù hợp |
| --- | --- | --- |
| `within-project` | Chỉ backup và restore resource trong cùng project. | Vault độc lập theo project. |
| `within-org` | Giới hạn với resource thuộc organization hiện tại; mặc định nếu không chỉ định. | Hub/spoke nhiều project thuộc một organization. |
| `within-org-but-unrestricted-for-ba` | Console-managed resources theo organization; có ngoại lệ cho backup appliance-managed resources. | Tổ chức còn dùng appliance management console và đã đánh giá rủi ro. |
| `unrestricted` | Cho phép sử dụng từ project/organization khác theo khả năng và IAM. | Chỉ khi có yêu cầu cross-organization rõ ràng, đã phê duyệt. |

Đối với centralized backup project nằm cùng organization với workload projects, `within-org` thường là điểm khởi đầu hợp lý. Nếu chọn `within-project`, backup từ project spoke khác có thể bị chặn dù service agent đã có IAM cần thiết. Nếu chọn `unrestricted`, phạm vi bảo vệ được mở rộng hơn mức cần thiết và phải kiểm soát restore destinations kỹ hơn.

Access restriction **không phải công cụ cho phép tự động**. Vẫn cần IAM cho principal, vault service agent, backup plans và quyền trên resource đích.

## 7. Phân quyền và tách trách nhiệm hub/spoke

Một triển khai chống xóa trái phép cần phân tách người có thể **quản trị vault**, **tạo/duy trì backup**, **khôi phục**, và **thay đổi quản trị project**.

### 7.1. Vai trò và quyền tối thiểu

| Nhóm/persona | Quyền thường cần | Vùng cấp quyền |
| --- | --- | --- |
| Backup security administrator | `roles/backupdr.backupvaultAdmin` hoặc custom role giới hạn thao tác | Project chứa vault. |
| Người xem trạng thái vault/backup | `roles/backupdr.backupvaultViewer` | Project chứa vault. |
| Backup operator | Các role Backup and DR dành cho quản lý/áp dụng backup plan, kích hoạt backup theo resource | Project quản lý plan và project nguồn phù hợp. |
| Restore operator | `roles/backupdr.restoreUser` và các quyền tạo resource đích tương ứng | Chỉ restore project đã phê duyệt. |
| Backup vault service agent | Ví dụ `roles/backupdr.diskOperator` hoặc `roles/backupdr.computeEngineOperator` theo resource type | Workload project được bảo vệ. |
| Project lien administrator | `roles/resourcemanager.lienModifier` thông qua PAM/JIT | Project hub. |
| Security auditor | Quyền xem IAM/audit logs và backups thích hợp, không có quyền delete | Project hub/spokes. |

Tên role là gợi ý từ tài liệu IAM của Backup and DR; quyền chính xác cho **resource type và thao tác** phải kiểm tra trong bảng permissions chính thức. Không cấp `roles/backupdr.admin` cho toàn bộ đội ứng dụng nếu họ chỉ cần trigger backup hoặc xem trạng thái. Role của **service agent** không được gán cho human/service account thông thường.

### 7.2. Vault service agent và quyền cross-project

Mỗi backup vault có một service agent được Google quản lý. Khi vault trong project hub và disk nguồn trong project spoke, service agent cần quyền tương ứng **trên project spoke**.

Ví dụ cho **Compute Engine disk**, sau khi lấy đúng service agent email từ trang chi tiết vault:

~~~bash
gcloud projects add-iam-policy-binding WORKLOAD_PROJECT_ID \
  --member="serviceAccount:BACKUP_VAULT_SERVICE_AGENT_EMAIL" \
  --role="roles/backupdr.diskOperator"
~~~

Với **Compute Engine VM instance** thay vì disk, vai trò được hướng dẫn có thể là `roles/backupdr.computeEngineOperator`. Không tự áp dụng role VM cho disk hoặc Cloud SQL. Với disk/VM nằm **cùng project với vault**, điều kiện cấp quyền có thể khác; xem hướng dẫn cụ thể theo resource type.

Nếu backup hoặc restore báo `PERMISSION_DENIED`, xác định đúng service agent email, project, backup plan association, role và quyền RESTORE destination. Không sửa bằng cách cấp Owner toàn organization rồi quên thu hồi.

### 7.3. Đường tấn công qua quản trị thay vì xóa từng backup

Một tài khoản bị chiếm quyền có thể cố:

- Xóa backup hiện tại (bị enforced retention từ chối).
- Giảm retention cho backup tạo tương lai (bị retention lock ngăn nếu đã locked).
- Gỡ liên kết backup plan khỏi workload để **ngừng tạo backup mới**.
- Gỡ project lien hoặc xóa project nếu có quyền.
- Vô hiệu hóa CMEK key làm dữ liệu khó hoặc không thể restore.
- Lấy cắp dữ liệu bằng việc restore ra project khác.
- Tắt alert, log sink hoặc sửa retention của logs.

Do đó, chương trình chống ransomware không chỉ đếm số backup tồn tại mà phải theo dõi **backup schedule compliance**, **security configuration changes**, **IAM drift**, **service agents**, **key lifecycle** và **khả năng restore**.

## 8. Chọn location, encryption và retention theo workload

Backup vault có thể được tạo ở location được hỗ trợ, gồm regional, cross-regional hoặc multi-regional. Khả năng dùng location phụ thuộc loại workload:

| Workload | Regional/cross-regional | Multi-region | Lưu ý |
| --- | --- | --- | --- |
| Compute Engine VM instances | Có, theo location compatibility | Có tại các multi-regions được hỗ trợ | Đánh giá nhất quán của application trong VM. |
| Compute Engine disks | Có | Có | Disk backup khác backup nguyên VM. |
| Cloud SQL instances | Có | Có | PITR transaction logs có đặc điểm lưu trữ riêng ngoài vault. |
| AlloyDB clusters | Có các điều kiện location riêng | Không theo danh sách hiện hành | Kiểm tra vùng nguồn/vault và retention range. |
| Filestore instances | Có | Không theo danh sách hiện hành | Hạn chế theo resource và location. |

Regional/cross-regional vaults bảo vệ trước sự cố đơn zone nhờ lưu redundant data; multi-region vault hỗ trợ chống ảnh hưởng toàn region đối với workload được hỗ trợ. Không có nghĩa chọn multi-region sẽ đạt RTO=0 hoặc tự phục hồi application; restore vẫn cần công cụ, quyền và runbook.

### 8.1. Bảo vệ với CMEK

Mặc định backup data được mã hóa at rest bằng Google-managed keys. Nếu có yêu cầu khóa do khách hàng kiểm soát, có thể dùng **CMEK** khi workload/vault location hỗ trợ. Nhưng:

- Tùy resource type, hỗ trợ CMEK của backup vault có giới hạn; kiểm tra tài liệu riêng và compatibility của source encryption.
- **Chỉ chọn CMEK khi tạo vault**; không coi đó là thuộc tính có thể bật tùy ý sau.
- Key phải có location tương thích với vault.
- Việc vô hiệu hóa/hủy key có thể làm backup không restore được dù retention vẫn còn.
- Tách người quản trị Cloud KMS khỏi người quản trị Backup and DR và theo dõi lịch rotation/destroy.

**Immutability không tương đương recoverability**: backup không bị xóa nhưng khóa cần thiết cho giải mã đã mất thì restore vẫn thất bại.

### 8.2. Chọn retention và chi phí

Ví dụ giả định theo yêu cầu dữ liệu:

| Môi trường | Backup frequency | Assigned retention | Minimum enforced retention | Lock decision |
| --- | --- | --- | --- | --- |
| Lab staging | Daily | 30 ngày | 7 ngày | Không lock vĩnh viễn; chỉ xem UI trạng thái. |
| Production đơn hàng | Daily + weekly/monthly theo policy | 35–90 ngày hoặc theo quy định | Tùy RPO/compliance; có thể match full expiration | Review với Security/Legal, khóa sau phê duyệt. |
| Pháp lý/điều tra | Theo yêu cầu retention cụ thể | Có thể dài | Theo policy lưu trữ hợp pháp | Cần quyết định và phê duyệt chuyên biệt. |

Các con số ở đây chỉ là **ví dụ thiết kế**, không thay chính sách lưu trữ thực tế. Backup plan retention có giới hạn riêng theo giờ/ngày/tuần/tháng và loại resource. Không nhập 99 năm cho một daily rule chỉ vì maximum vault là 99 năm.

Thời gian lưu backup ảnh hưởng phí lưu trữ và data transfer; dữ liệu đã được enforced retention bảo vệ không thể xóa sớm để tiết kiệm phí. Hãy tính storage consumption, thay đổi dữ liệu theo ngày, retention, vị trí lưu trữ, restore operations và phí network từ Pricing Calculator trước khi lock.

## 9. Thực hành lab an toàn: tạo vault chống xóa sớm

**Kiến trúc lab:** một `BACKUP_HUB_PROJECT_ID` lưu vault/plan; một `WORKLOAD_PROJECT_ID` có Compute Engine disk giả lập. Hai project nằm cùng organization; region minh họa `asia-southeast1`. Chỉ dùng project được phê duyệt với budget/alerts; các lệnh tạo tài nguyên **sẽ phát sinh phí** nếu được chạy.

### 9.1. Chuẩn bị API và quyền

Trong project hub, bật Backup and DR API bằng principal quản trị được ủy quyền:

~~~bash
gcloud services enable backupdr.googleapis.com \
  --project=BACKUP_HUB_PROJECT_ID
~~~

Bật API và các dịch vụ Compute Engine cần thiết ở workload project theo quy trình tổ chức. Người tạo vault cần role `roles/backupdr.backupvaultAdmin` ở hub project; người tạo backup plans/associations và người truy cập disk cần các permissions tương ứng, không nhất thiết là cùng một người.

### 9.2. Tạo vault: minimum 7 ngày, lock theo rule 30 ngày

Ví dụ CLI chỉ dành cho môi trường lab được phép tạo backup:

~~~bash
gcloud backup-dr backup-vaults create orders-lab-vault \
  --project=BACKUP_HUB_PROJECT_ID \
  --location=asia-southeast1 \
  --backup-min-enforced-retention=7 \
  --backup-retention-inheritance=match-backup-expire-time \
  --access-restriction=within-org
~~~

Giải thích tham số:

- `--backup-min-enforced-retention=7` đặt sàn không được xóa sớm 7 ngày.
- `--backup-retention-inheritance=match-backup-expire-time` bảo vệ mỗi backup **đến hết expiration của rule**, chẳng hạn 30 ngày.
- `--access-restriction=within-org` cho phép cross-project trong cùng organization nhưng vẫn phải có IAM.
- Ví dụ **không đặt retention lock vĩnh viễn**. Muốn khóa minimum theo ngày hiệu lực, hãy thực hiện sau security review bằng trang chi tiết vault/Console và phê duyệt tương ứng.

Khi tạo vault, Backup and DR trả operation ID. Kiểm tra trạng thái bất đồng bộ bằng:

~~~bash
gcloud backup-dr operations describe FULL_OPERATION_ID
~~~

Khi operation hoàn thành, kiểm tra cấu hình và status của vault:

~~~bash
gcloud backup-dr backup-vaults describe orders-lab-vault \
  --project=BACKUP_HUB_PROJECT_ID \
  --location=asia-southeast1
~~~

Kiểm tra tên, location, minimum enforced retention, inheritance mode, access restriction, trạng thái lock và service agent. Nếu `match-backup-expire-time` không đúng thì **không thể đổi mode tại vault hiện có**; cần tạo một vault mới theo thiết kế đã duyệt, không xóa vault có backup đang được bảo vệ.

### 9.3. Tạo backup plan cho disk mẫu

Ví dụ tạo plan daily giữ **30 ngày**; backup rule nằm trong region của disk nguồn:

~~~bash
gcloud backup-dr backup-plans create disk-daily-30d \
  --project=BACKUP_HUB_PROJECT_ID \
  --location=asia-southeast1 \
  --backup-vault=orders-lab-vault \
  --resource-type=compute.googleapis.com/Disk \
  --backup-rule='rule-id=daily,retention-days=30,recurrence=DAILY,time-zone=UTC,backup-window-start=0,backup-window-end=4' \
  --max-custom-on-demand-retention-days=30
~~~

Rule chạy trong cửa sổ 00:00–04:00 UTC theo giờ backup plan, không đảm bảo đúng 00:00. Đảm bảo disk nằm cùng region được backup plan hỗ trợ, và policy 30 ngày lớn hơn minimum vault 7 ngày. Với `match-backup-expire-time`, backup theo rule này không được xóa thủ công trước khi hết khoảng 30 ngày.

Nếu CLI phiên bản đang dùng thay đổi cú pháp `--backup-rule`, xem `gcloud backup-dr backup-plans create --help` và tài liệu mới nhất; không sửa policy production chỉ để lệnh lab chạy.

### 9.4. Liên kết disk với plan

Lấy **numeric ID** của test disk:

~~~bash
gcloud compute disks describe TEST_DISK_NAME \
  --zone=asia-southeast1-a \
  --project=WORKLOAD_PROJECT_ID \
  --format="value(id)"
~~~

Sau đó người có quyền cần thiết tạo association ở **workload project**:

~~~bash
gcloud backup-dr backup-plan-associations create orders-disk-assoc \
  --project=WORKLOAD_PROJECT_ID \
  --location=asia-southeast1 \
  --resource=projects/WORKLOAD_PROJECT_ID/zones/asia-southeast1-a/disks/DISK_NUMERIC_ID \
  --resource-type=compute.googleapis.com/Disk \
  --backup-plan=projects/BACKUP_HUB_PROJECT_ID/locations/asia-southeast1/backupPlans/disk-daily-30d
~~~

Thay `DISK_NUMERIC_ID` bằng giá trị lấy từ lệnh describe. Với centralized hub/spoke, cấp `roles/backupdr.diskOperator` cho đúng vault service agent ở workload project **trước** khi chạy nếu loại disk yêu cầu. Một association bảo vệ một disk; backup cả VM instance cùng hệ thống disk đính kèm cần dùng loại plan dành cho Compute Engine Instance hoặc liên kết nhiều disks theo thiết kế.

### 9.5. Kiểm tra kết quả bằng thao tác chỉ đọc

Sau khi job backup hoàn tất:

1. Mở **Backup and DR → Vaulted backups** trong Console.
2. Chọn data source disk mẫu, xem backup list, creation time, assigned expiration, enforced retention và trạng thái backup.
3. Đối chiếu backup rule, vault mode và thời điểm có thể xóa.
4. Mở vault details, kiểm tra minimum, inheritance, lock status và access restriction.
5. Kiểm tra project hub có lien (nếu backup protected đủ điều kiện auto-lien).
6. Ghi bằng chứng trạng thái/metadata; **không cần gọi delete API**.

Ví dụ lệnh đọc backup list:

~~~bash
gcloud backup-dr backups list \
  --backup-vault=orders-lab-vault \
  --data-source=DATA_SOURCE_ID \
  --location=asia-southeast1 \
  --project=BACKUP_HUB_PROJECT_ID
~~~

`DATA_SOURCE_ID` được lấy từ Vaulted backups/data source sau khi backup đầu tiên xuất hiện. Nếu chưa có backup, đừng coi `list` trả rỗng là bảo vệ hoạt động: kiểm tra job status, association, schedule, API/IAM và thời gian backup window.

## 10. Thiết kế bài test chống xóa trái phép mà không phá dữ liệu

Bài test cần chứng minh các **security properties** theo cách kiểm soát được:

| Test ID | Điều cần xác minh | Phương pháp an toàn | Kết quả đúng |
| --- | --- | --- | --- |
| BV-01 | Vault đã enforce retention | `backup-vaults describe` + Vaulted backups metadata | Minimum lớn hơn 0; các backup mới có enforced period phù hợp. |
| BV-02 | Mode kế thừa đúng | Xem field inheritance và backup expiration | Mode `match-backup-expire-time` đúng nếu yêu cầu toàn kỳ. |
| BV-03 | Lock status | Xem vault details | `Locked` khi ngày hiệu lực đã qua, hoặc `Unlocked` nếu lab chưa phê duyệt lock. |
| BV-04 | IAM tách người vận hành | Review IAM policy trên hub/spoke, principal và roles | Người dùng workload không có quyền sửa vault/retention. |
| BV-05 | Cross-project access không mở rộng quá mức | Xem access restriction `within-org` và service agent bindings | Không tự cho phép ngoài organization. |
| BV-06 | Project lien bảo vệ hub | List liens, xem quyền Lien Modifier và PAM | Có lien khi thỏa điều kiện; không ai được gỡ đơn phương. |
| BV-07 | Backup không bị thay đổi sau khi tạo | Đọc backup metadata và audit logs | Backup không có thao tác sửa/xóa trái chính sách. |
| BV-08 | Restore khả thi | Tạo restore resource mới trong staging cô lập, xác minh dữ liệu checksum | Dữ liệu có thể đọc; RTO/RPO ghi lại. |
| BV-09 | Ngừng bảo vệ không đồng nghĩa mất backup cũ | Review association và backups hiện có | Thay association chỉ ảnh hưởng backup mới; recovery points cũ chịu retention riêng. |

Nếu yêu cầu có **negative delete test**, phải dùng vault/backup thử nghiệm riêng, có approval, thời gian retention ngắn và ngân sách; không thử `gcloud backup-dr backups delete` trên dữ liệu thật. Mã lỗi trả về khi thao tác bị từ chối có thể phụ thuộc IAM trước khi tới policy retention (ví dụ `PERMISSION_DENIED` hay precondition error), nên không hard-code một mã HTTP duy nhất làm bằng chứng.

### 10.1. Thời gian sửa retention có ảnh hưởng backup cũ không?

Nếu một administrator thay minimum từ 7 xuống 3 ngày **trước khi lock**, những backup đã được tạo với enforced retention 7 ngày **không bị rút ngắn**. Test nên xác minh metadata của backup trước/sau, không chỉ nhìn vault minimum hiện tại. Những backup tạo sau đó mới chịu cấu hình mới theo rules thích hợp.

Nếu lock đã effective, nỗ lực giảm minimum phải bị hệ thống từ chối. Tuy nhiên, quyền IAM thiếu có thể chặn request ngay từ đầu; muốn chứng minh **retention lock** chứ không phải thiếu quyền, phải phối hợp kiểm thử với security owner và quan sát nguyên nhân chính xác.

## 11. Diễn tập khôi phục: backup bất biến phải còn dùng được

Một backup được bảo vệ khỏi xóa nhưng không restore được **không đạt mục tiêu DR**. Đặt hai chỉ số:

- **RPO:** lượng dữ liệu có thể mất theo mục tiêu, ví dụ 24 giờ với daily backup nếu không có cơ chế bổ sung.
- **RTO:** thời gian đưa workload trở lại hoạt động, gồm quyền restore, cấp tài nguyên, kết nối mạng, kiểm tra dữ liệu và chuyển traffic.

Diễn tập tối thiểu với disk staging:

1. Chọn recovery point đã thành công và nằm trong vault.
2. Tạo một **disk mới** ở project/zone staging được cấp phép, không ghi đè disk nguồn.
3. Đảm bảo vault service agent/restore operator có quyền ở restore project.
4. Attach disk mới vào một VM kiểm thử cô lập; mount **read-only** nếu cần bảo toàn chứng cứ.
5. Kiểm tra filesystem, checksum hoặc một tập file marker; với ứng dụng database, kiểm tra nhất quán ứng dụng chứ không chỉ file tồn tại.
6. Ghi thời gian từ yêu cầu restore đến xác minh thành công; cập nhật runbook và dọn resource staging theo approval.

Đối với Cloud SQL/AlloyDB, quy trình restore khác disk và có thể liên quan PITR logs nằm ngoài vault. Cần diễn tập riêng đúng loại database, credentials, CMEK và networking. Không dùng kết quả restore disk để suy rằng toàn bộ hệ thống database có RPO/RTO tương tự.

## 12. Giám sát, audit và cảnh báo sớm

Để phát hiện việc cố gỡ bảo vệ **trước khi xảy ra mất dữ liệu**, cần kết hợp backup jobs, thay đổi cấu hình và hoạt động IAM.

| Tín hiệu | Phát hiện | Hành động |
| --- | --- | --- |
| Backup schedule compliance | Backup không chạy, job thất bại, thiếu recovery point mới. | Điều tra policy, quyền service agent, quota, workload health. |
| Thay đổi vault minimum/lock/access | Cố sửa retention hoặc thay đổi quản trị vault. | Alert Security/Backup owner; đối chiếu change ticket. |
| Backup plan association bị xóa | Workload dừng tạo backup mới. | Phục hồi protection với approval và kiểm tra các backup đã có. |
| Service agent IAM drift | Backup job/restore lỗi 403 hoặc cấp quyền quá rộng. | Sửa binding theo resource type; review quyền định kỳ. |
| Project lien bị gỡ hoặc IAM lienModifier mới | Có nguy cơ xóa hub project. | Kiểm tra PAM approvals, alert ưu tiên cao. |
| CMEK disable/destroy schedule | Backup có thể không giải mã được khi restore. | Escalate cho KMS owner, ngăn destroy trái phép. |
| Backup bytes/retention tăng bất thường | Phí tăng hoặc sai retention rule. | Xem backup expiration, số data sources, cost/billing report. |
| Restore drill thất bại hoặc RTO vượt mục tiêu | Backup không đáp ứng recovery requirement. | Điều chỉnh runbook, permissions, location, dependency recovery. |

Với Cloud Logging, lọc **Admin Activity audit logs** cho Backup and DR API; ví dụ minh họa:

~~~text
protoPayload.serviceName="backupdr.googleapis.com"
protoPayload.methodName:("backupVaults" OR "backupPlans" OR "backupPlanAssociations")
~~~

Cú pháp và `methodName` thực tế có thể thay đổi theo API version; bắt đầu từ một log entry thật rồi tạo filter khớp field. Thao tác đọc/khôi phục có thể cần Data Access audit logs được bật và quyền Logs Viewer/Private Logs Viewer tương ứng. Đừng gắn nhãn "chưa có log" là "không có truy cập" nếu Audit Logs của loại đó chưa được cấu hình.

Nên gửi alert về backup failure, protection removed, IAM changes và lien changes đến kênh trực ca độc lập với workload production. Khi kẻ tấn công đã chiếm project sản xuất, một dashboard chỉ lưu trong project đó có thể không phải nguồn bằng chứng đáng tin duy nhất.

## 13. Chi phí, dữ liệu cưỡng chế giữ và vòng đời thanh lý

Enforced retention là một **cam kết lưu dữ liệu**, không chỉ một rule an ninh miễn phí. Nếu backup cần giữ 30 ngày, bạn không thể xóa ngày thứ ba để giảm bill hoặc dọn test environment.

Những yếu tố ảnh hưởng chi phí:

1. Lượng backup data thực sự lưu, thay đổi dữ liệu và cách tối ưu lưu trữ theo dịch vụ.
2. Số recovery points, retention và chu kỳ daily/weekly/monthly.
3. Location (regional, cross-regional, multi-region), data transfer và restore transfer.
4. Phí Backup and DR management/storage cùng chi phí compute/disk khi diễn tập restore.
5. Các nghĩa vụ lâu hơn từ compliance, litigation hold hoặc retention lock.

Ví dụ minh họa **không phải báo giá**: nếu một dataset có bản đầu 200 GiB và mỗi ngày có 5 GiB biến động cần giữ, sau 30 ngày tổng dữ liệu lưu có thể tăng đáng kể so với 200 GiB. Con số tính tiền thực tế còn phụ thuộc định dạng backup, incremental behavior, compression/deduplication và pricing; hãy dùng Google Cloud Pricing Calculator và dữ liệu Billing theo workload.

Khi decommission:

- Ngừng tạo backup mới bằng quy trình **unprotect** phù hợp.
- Chờ những backup hiện có hết enforced retention và expiration.
- Xác nhận không còn data sources/backups ngăn vault deletion.
- Quản lý project lien và quyền gỡ bằng PAM/approval theo quy trình quản trị.
- Chỉ xóa vault khi điều kiện dịch vụ và compliance cho phép; không tìm cách phá retention để "dọn nhanh".

Một vault **không thể bị xóa** khi còn backup chưa thỏa enforced retention hoặc chưa được xử lý hết theo quy tắc hết hạn. Đây là đặc tính bảo vệ cần dự tính trong kế hoạch ngân sách và đóng project.

## 14. Tình huống ứng phó ransomware

Giả sử một service account của project sản xuất bị lộ. Kẻ tấn công xóa disk của hệ thống đơn hàng, cố xóa backup plan association và truy cập backup vault trong hub project.

Runbook đề xuất:

1. **Cô lập sự cố:** thu hồi token, disable hoặc giới hạn principal bị lộ theo quy trình, chặn thay đổi IAM bất thường, thu thập audit logs.
2. **Xác định phạm vi:** workload nào bị xóa/mã hóa, backup plan association nào mất, vault nào lưu recovery points, project liens còn không?
3. **Kiểm tra khả năng bất biến:** vault minimum, inheritance, retention lock status và enforced end time của backup **đã có**.
4. **Bảo vệ đường restore:** dùng restore operator riêng, kiểm soát IAM đích, mạng cô lập và KMS key, tránh restore ngay vào môi trường bị xâm nhập.
5. **Chọn recovery point sạch:** đối chiếu thời điểm bị xâm nhập và backup trước thời điểm đó; immutable backup vẫn có thể chứa dữ liệu đã bị malware mã hóa nếu backup sau khi sự cố bắt đầu.
6. **Khôi phục thử:** restore vào staging/forensic project, kiểm tra checksum, tính toàn vẹn ứng dụng, truy cập mạng và credentials.
7. **Khôi phục dịch vụ:** deploy hạ tầng sạch, vá lỗ hổng, xoay vòng secret, restore dữ liệu được xác minh, chỉ chuyển traffic khi Security phê duyệt.
8. **Đo RPO/RTO và hậu kiểm:** ghi thiếu sót về IAM, retention, alerts, backup schedule, vị trí vault và kế hoạch tránh tái phát.

Một backup bất biến **không đủ** để ngăn rò rỉ dữ liệu hoặc duy trì business continuity nếu backup gần nhất đã nhiễm lỗi, khóa không thể giải mã, hoặc operator không có quyền restore. Cyber resilience yêu cầu cả **prevention, detection, response và recovery**.

## 15. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và xử lý |
| --- | --- | --- |
| Backup plan không thể dùng vault | Minimum enforced retention lớn hơn retention của rule, hoặc location/resource type không tương thích. | Đối chiếu rule duration, backup plan region và vault location/support matrix. |
| Vault được tạo nhưng chưa thấy backups | Chưa associate resource, backup window chưa đến hoặc job lỗi. | Kiểm tra plan association, job logs và service agent. |
| Cross-project backup báo 403 | Vault service agent chưa có role operator ở workload project. | Lấy đúng service agent email và cấp role theo disk/VM/SQL tương ứng. |
| Không thể giảm retention | Vault đã locked hoặc rule/backup compatibility không cho phép. | Kiểm tra lock status; nếu đã effective, không có thao tác giảm. |
| Backup rule 30 ngày nhưng có thể xóa sau 7 ngày | Vault chọn `inherit-vault-retention` với minimum 7 ngày. | Xem inheritance mode; thiết kế vault mới với `match-backup-expire-time` nếu cần toàn vòng đời. |
| Không tìm thấy quyền restore từ project đích | Thiếu role restore/operator hoặc access restriction. | Kiểm tra IAM trên hub/restore project và restriction mode. |
| Project hub không thể xóa | Project lien đang hoạt động. | Đúng behavior khi còn protected backups; theo quy trình decommission. |
| Có quyền Project Owner nhưng không thể xóa backup | Enforced retention đang bảo vệ backup. | Không bypass; chờ đến enforced expiration. |
| Backup còn nguyên nhưng restore lỗi CMEK | Key bị disable/destroy hoặc thiếu KMS permissions. | Điều tra vòng đời key và quyền KMS theo policy. |
| Vault đổi location không được | Location là một phần định danh/thiết kế vault. | Tạo vault mới ở location hỗ trợ, migrate protection có kế hoạch. |
| Phí backup tăng bất thường | Assigned/enforced retention dài, nhiều recovery points hoặc multi-region. | Phân tích billing, storage footprint và backup rules; không hạ lock trái quy trình. |
| Audit không thấy restore hoặc đọc backup | Chưa bật log type cần thiết hoặc filter sai. | Đối chiếu Cloud Audit Logs và enable Data Access khi phù hợp. |

## 16. Checklist hoàn thành bài học

- [ ] Giải thích được vault → data source → backup, backup plan và association.
- [ ] Phân biệt assigned retention của backup rule với enforced retention của vault.
- [ ] Biết minimum enforced retention có thể đến 99 năm nhưng mỗi resource type có giới hạn riêng.
- [ ] Phân biệt `inherit-vault-retention` và `match-backup-expire-time`.
- [ ] Hiểu inheritance mode không thể đổi sau khi tạo vault.
- [ ] Hiểu retention lock hiệu lực rồi không thể gỡ hoặc giảm minimum.
- [ ] Biết sửa minimum về sau không thay đổi enforced retention của backups đã tạo.
- [ ] Biết từ 01/11/2026 project có vault với protected backups được tự động áp dụng lien.
- [ ] Có PAM/multi-party approval để bảo vệ quyền gỡ lien.
- [ ] Phân tách hub project và spoke/workload projects khi phù hợp.
- [ ] Cấp role tối thiểu cho backup vault admins, viewers, restore operators và service agents.
- [ ] Chọn đúng access restriction trước khi tạo vault; ưu tiên `within-org` cho hub/spoke cùng organization.
- [ ] Xác minh CMEK/location/resource type compatibility và trách nhiệm vòng đời khóa.
- [ ] Tạo backup plan có retention >= vault minimum và association đúng resource.
- [ ] Xem backup metadata, thời gian enforced retention và trạng thái lock bằng thao tác chỉ đọc.
- [ ] Có backup schedule compliance alert và cảnh báo thay đổi vault/IAM/liens.
- [ ] Đã restore thử vào resource staging cô lập, kiểm tra dữ liệu và đo RPO/RTO.
- [ ] Có kế hoạch chi phí, decommission, IAM review và incident response.
- [ ] Không thử xóa/giảm retention trên production để làm bằng chứng kiểm thử.

## Tài liệu tham khảo

- [Overview of backup vaults — Google Cloud Backup and DR](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-vault) — vault model, locations, enforced retention, lock và access restrictions.
- [Create and manage a backup vault](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/backup-vault-create) — Console, gcloud, Terraform, minimum retention, CMEK, service agent và delete constraints.
- [Backup plans overview](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/backup-plan) — assigned retention, backup plan rules, resource type và compatibility.
- [Back up disks to a backup vault](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/compute/disk-backup) — backup plan associations, IAM cho disk, on-demand backup, restore.
- [Protect and recover disks — Quickstart](https://docs.cloud.google.com/backup-disaster-recovery/docs/quickstarts/disk-backup-vault) — tạo plan và backup disk qua vault.
- [Manage backups in the Google Cloud console](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/bv-backup-manage) — liệt kê, xem recovery points và thời gian expiration.
- [Protect projects with liens](https://docs.cloud.google.com/backup-disaster-recovery/docs/configuration/project-liens) — tự động áp dụng lien, bảo vệ project và điều kiện gỡ.
- [Protect project liens with Privileged Access Manager](https://docs.cloud.google.com/backup-disaster-recovery/docs/configuration/project-liens-multi-party-approval) — multi-party approval trước khi gỡ lien.
- [Configure cyber resilience for Backup and DR](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/best-practices-cyber-resilience) — kiến trúc hub/spoke, separation of duties, IAM, KMS và giám sát.
- [Best practices against ransomware](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/best-practices-ransomware) — phòng chống ransomware và bất biến dữ liệu backup.
- [Backup and Disaster Recovery IAM roles](https://docs.cloud.google.com/iam/docs/roles-permissions/backupdr) — role/permission theo tài nguyên và principal.
- [Backup and DR overview](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-dr) — phạm vi Backup and DR, quản lý workload và các model sao lưu.


# Directory backup trong IAM: sao lưu, khôi phục và kiểm chứng vòng đời danh tính

**Directory backup** là quá trình tạo, bảo vệ, lưu giữ và định kỳ kiểm tra các bản sao có thể khôi phục của dữ liệu cùng cấu hình **directory service**. Directory lưu danh tính, thuộc tính người dùng, nhóm, tài khoản máy/dịch vụ và nhiều thông tin cần thiết để **Identity Provider (IdP)**, ứng dụng và hệ thống phân quyền hoạt động đúng. Mất directory hoặc khôi phục sai có thể khiến người dùng không đăng nhập được, người cũ lấy lại quyền, tài khoản dịch vụ ngừng hoạt động hoặc hệ thống mất dấu vết kiểm toán.

Bài **“Directory backup”** thuộc chương **Directory service** trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Module tìm hiểu quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: từ xác minh danh tính, tạo tài khoản và cấp quyền đến rà soát, thay đổi vai trò và thu hồi khi nghỉ việc. Directory backup liên kết với **IdP/SSO, SCIM provisioning, RBAC/ABAC, service account, audit** và mục tiêu giảm **quyền truy cập tồn dư** sau sự cố.

**Tình huống dẫn nhập:** Chiều thứ Sáu, một quản trị viên phát hiện hàng nghìn account trong directory bị xóa nhầm bởi connector đồng bộ. Tổ chức có backup từ tối thứ Năm. Nếu khôi phục dữ liệu mà không đối soát những nhân viên đã nghỉ hoặc đổi vai trò trong ngày thứ Sáu, bản backup có thể **phục hồi cả tài khoản và quyền lẽ ra đã thu hồi**. Vì vậy, directory backup không chỉ là “chép dữ liệu rồi restore”; nó là một quy trình **phục hồi có kiểm soát danh tính và quyền truy cập**.

## 1. Directory service chứa gì và vì sao phải sao lưu?

Một directory service tổ chức dữ liệu danh tính thành các đối tượng và quan hệ: user, group, computer, organizational unit, policy, service identity, thuộc tính và các đối tượng liên quan. Tùy công nghệ, dữ liệu có thể được lưu trong Active Directory Domain Services (**AD DS**), LDAP directory như OpenLDAP, nền tảng identity/cloud directory hoặc hệ thống lai.

| Nhóm dữ liệu | Ví dụ | Tác động khi mất hoặc khôi phục sai |
| --- | --- | --- |
| **Danh tính người dùng** | User object, identifier ổn định, trạng thái account. | Không đăng nhập được, tạo trùng hoặc nối nhầm danh tính. |
| **Nhóm và quan hệ** | Group membership, nhóm lồng nhau, OU. | Role RBAC bị mất hoặc quyền cũ được khôi phục ngoài ý muốn. |
| **Thông tin máy/dịch vụ** | Computer account, service identity, khóa/thuộc tính liên quan. | Workload, domain join, Kerberos hoặc tích hợp bị gián đoạn. |
| **Cấu hình và schema** | Schema, LDAP overlays, replication settings, directory policies. | Dữ liệu được restore nhưng không còn được diễn giải đúng. |
| **Chính sách và cấu hình phụ trợ** | GPO/SYSVOL, DNS tích hợp AD, trust configuration tùy nền tảng. | Đăng nhập hoặc áp chính sách bảo mật không nhất quán. |
| **Credential-related data** | Password verifier/hash, key material hoặc tham chiếu khóa tùy công nghệ. | Lộ backup có thể dẫn đến chiếm tài khoản/khả năng giả mạo. |
| **Liên kết IAM** | ObjectGUID/SID, external identifiers, account mappings. | SCIM/IGA không liên kết được đúng account sau khôi phục. |
| **Bằng chứng vận hành** | Thời điểm backup, manifest, version/cấu hình. | Không chứng minh được dữ liệu phục hồi có toàn vẹn và đúng thời điểm. |

**Không phải mọi dữ liệu liên quan IAM đều nằm trong directory.** HRIS, IGA approvals, phiên IdP, OAuth grants, refresh token, nhật ký SIEM, tài khoản SaaS cục bộ, khóa trong vault hoặc dữ liệu chứng chỉ của CA có thể được quản trị riêng. Kế hoạch khôi phục phải kiểm kê và có phương án cho các hệ thống phụ thuộc, thay vì mặc định một file directory backup khôi phục được toàn bộ IAM.

## 2. Backup khác replication, high availability và export

| Cơ chế | Mục tiêu chính | Có giúp chống lỗi/xóa nhầm không? | Giới hạn |
| --- | --- | --- | --- |
| **Replication** | Đồng bộ thay đổi giữa các directory replica/domain controller. | Có thể hỗ trợ tính sẵn sàng, nhưng **xóa sai có thể lan sang mọi replica**. | Không phải lịch sử khôi phục độc lập. |
| **High Availability / failover** | Duy trì dịch vụ khi một node hoặc vùng gặp sự cố. | Giảm downtime do lỗi hạ tầng. | Không nhất thiết có dữ liệu tốt trước sự cố logic. |
| **Point-in-time backup** | Giữ bản sao dữ liệu ở thời điểm đã xác định. | Có nếu bản sao toàn vẹn, tách biệt và chưa bị phá. | Có mất dữ liệu sau điểm sao lưu (RPO). |
| **Directory-aware backup** | Sao lưu dữ liệu và trạng thái theo cơ chế ứng dụng hỗ trợ. | Có thể khôi phục dịch vụ và đối tượng theo runbook phù hợp. | Phụ thuộc nền tảng, version và phạm vi được hỗ trợ. |
| **LDIF export** | Xuất một tập đối tượng/thuộc tính LDAP để kiểm tra hoặc nhập lại. | Hữu ích cho khôi phục từng phần trong một số trường hợp. | Có thể thiếu credential, ACL, schema, replication metadata và trạng thái hệ thống. |
| **VM snapshot** | Ghi trạng thái máy ảo tại thời điểm chụp. | Hữu ích trong một số workflow được nhà cung cấp hỗ trợ. | Không mặc định là backup directory nhất quán hoặc phương thức restore DC an toàn. |
| **Audit/event log** | Tái dựng ai đã thay đổi gì và khi nào. | Giúp xác định nguyên nhân và bù thay đổi sau backup. | Không thay thế bản sao dữ liệu có thể restore. |

**Replication không thay thế backup.** Nếu ransomware mã hóa dữ liệu, admin gỡ nhầm nhóm hoặc hệ thống đồng bộ phát sự kiện Leaver sai, lỗi có thể được nhân bản tới toàn bộ các node khỏe mạnh. Một bản backup có thể phục hồi phải có **phiên bản trước sự cố, khả năng cô lập khỏi hệ thống đang bị chiếm và quy trình restore đã kiểm thử**.

### Physical backup, logical export và cấu hình

- **Physical/application-consistent backup** cần tuân thủ phương pháp được directory vendor hỗ trợ để bảo toàn các database và metadata liên quan.
- **Logical export** như LDIF có thể dùng cho sao lưu cấu trúc/đối tượng, nhưng không nên suy rằng có thể tái dựng hệ thống nguyên vẹn chỉ bằng file export.
- **Configuration backup** cần xét schema, chính sách, key/certificate, connector settings, trust và các thành phần phụ thuộc. Một số secret/khóa phải bảo vệ hoặc sao lưu qua cơ chế riêng.

## 3. Xác định nguồn sự thật và ranh giới backup

Trước khi sao lưu, cần biết **directory đang giữ dữ liệu gốc hay là bản sao được provision từ hệ thống khác**.

~~~mermaid
flowchart TD
    HR["HRIS / Contractor Registry<br/>Nguồn trạng thái JML"] --> IGA["IGA / IAM<br/>Desired access + approvals"]
    IGA --> DIR["Directory: AD DS / LDAP<br/>Accounts + Groups"]
    DIR --> IDP["IdP / SSO"]
    IGA --> SCIM["SCIM / Connectors"]
    SCIM --> APP["SaaS / App accounts"]
    DIR --> LDAPAPP["LDAP-dependent Apps"]
    DIR --> BACKUP["Directory-aware backup"]
    BACKUP --> VAULT["Kho backup bảo vệ / immutable"]
    VAULT --> LAB["Recovery environment / verification"]
    HR --> RECON["JML reconciliation sau restore"]
    IGA --> RECON
    LAB --> RECON
~~~

**Ví dụ phân chia trách nhiệm:**

| Thuộc tính / đối tượng | Nguồn quản lý có thẩm quyền | Cách sử dụng khi restore |
| --- | --- | --- |
| Trạng thái nhân sự, ngày nghỉ | HRIS. | Áp lại thay đổi JML sau thời điểm backup. |
| Phê duyệt role và chính sách SoD | IGA/business owner. | So sánh role thực tế với desired access đã phê duyệt. |
| Account SID/ObjectGUID, group membership | AD DS hoặc directory tương ứng trong phạm vi của nó. | Khôi phục đúng đối tượng rồi đối chiếu các grant còn hợp lệ. |
| App User.id và mapping SCIM | IAM connector/app đích. | Không tạo trùng hoặc gỡ nhầm user sau restore. |
| OAuth grants, sessions/token | AS/IdP hoặc hệ thống session chuyên dụng. | Kiểm tra cơ chế revoke; không suy từ directory restored. |
| Tài khoản SaaS có local login | Chính SaaS hoặc một nguồn quản trị được phê duyệt. | Cần kiểm tra độc lập, không dựa riêng vào AD disable. |

Đối với dữ liệu được đồng bộ từ HRIS, **restore directory về quá khứ không biến dữ liệu HRIS của quá khứ thành nguồn sự thật hiện tại**. Kế hoạch phải xác định cách **replay các thay đổi hợp lệ** và ngăn các connector tự đồng bộ dữ liệu sai trong lúc phục hồi.

## 4. Mô hình sao lưu AD DS: System State và phụ thuộc

Với **Active Directory Domain Services**, một phương án được Microsoft hỗ trợ thường sử dụng **System State backup của domain controller** hoặc giải pháp backup directory-aware tương thích. Thành phần System State trên DC có thể bao gồm **AD DS database và metadata liên quan, SYSVOL, registry, system files** cùng những thành phần phụ thuộc theo hệ điều hành/cấu hình; danh mục cụ thể phải đối chiếu phiên bản Windows Server và vai trò đã cài.

### Những thành phần phải đưa vào kế hoạch

1. **Domain controller:** hệ điều hành, bản vá, vai trò AD DS, thời điểm backup, cơ chế khôi phục được hỗ trợ.
2. **AD database và transaction logs:** không copy file database đang hoạt động theo kiểu thông thường rồi giả định nhất quán.
3. **SYSVOL/GPO:** các chính sách và script đi kèm directory, cần được kiểm sau phục hồi.
4. **AD-integrated DNS:** bản ghi/vùng DNS cần thiết cho DC discovery, Kerberos và truy cập domain.
5. **Forest/domain topology:** domain/forest, trust, site, replication, FSMO roles và Global Catalog theo thiết kế.
6. **Khóa/chứng chỉ liên quan:** AD CS/CA database và private keys là phạm vi sao lưu riêng cần kế hoạch đồng bộ, không tự nằm đầy đủ trong mọi System State backup.
7. **Backup tuổi và tính phù hợp:** phải tuân theo giới hạn và thủ tục khôi phục AD DS được hỗ trợ, bao gồm tác động của tombstone lifetime và replication.

**Không chỉ backup một DC duy nhất rồi mặc định toàn bộ forest khôi phục được.** Kế hoạch forest recovery cần đảm bảo có backup hợp lệ cho những domain/DC cần thiết và biết vai trò của mỗi bản trong quy trình khôi phục. Phương án cụ thể phụ thuộc forest topology, DNS, SYSVOL và tài liệu hỗ trợ của Microsoft cho phiên bản đang chạy.

### Ví dụ lệnh System State backup (minh họa)

~~~powershell
# MINH HỌA trên Windows Server Domain Controller, chỉ chạy
# theo runbook đã được phê duyệt với backup destination phù hợp.
wbadmin start systemstatebackup -backuptarget:E: -quiet
~~~

Ví dụ trên **không phải hướng dẫn áp dụng trực tiếp ở production**. Đường dẫn E: chỉ tượng trưng cho đích backup được chuẩn bị và bảo vệ; cú pháp/khả năng đích thực tế còn phụ thuộc version/cấu hình và công cụ được sử dụng. Cần xác minh backup job hoàn tất, catalog, tính toàn vẹn, mã hóa và **khả năng restore** — exit code thành công không thay cho buổi diễn tập.

### VM snapshot: lưu ý đặc biệt với DC

Hoàn nguyên DC về snapshot máy ảo không được xem là phương án backup mặc định. Trên các hệ thống cũ/không hỗ trợ, rollback có thể gây **USN rollback, replication inconsistency và mất tính toàn vẹn directory**. Các nền tảng Windows Server/hypervisor hỗ trợ **VM-Generation ID** có cơ chế giảm một số rủi ro clone/rollback, nhưng **không biến mọi snapshot thành phương pháp disaster recovery đầy đủ**. Hãy dùng quy trình backup/restore AD DS được hỗ trợ và kiểm thử trong môi trường thích hợp.

## 5. Các kiểu khôi phục AD DS và khi nào sử dụng

| Kiểu phục hồi | Khi thích hợp | Cần kiểm soát |
| --- | --- | --- |
| **Khôi phục một đối tượng bằng AD Recycle Bin** | Xóa nhầm object, tính năng đã bật và object vẫn trong thời gian giữ. | Thuộc tính/liên kết được khôi phục theo khả năng và trạng thái tính năng, kiểm quyền sau restore. |
| **Non-authoritative restore** | DC cần được khôi phục rồi nhận thay đổi phù hợp từ các DC khỏe mạnh. | Replication phải nhất quán; không tự phục hồi một object đã bị xóa hợp lệ và replicate. |
| **Authoritative restore** | Cần phục hồi object/subtree cụ thể để thay đổi phục hồi được ưu tiên trong replication theo quy trình AD DS. | Phải chọn đúng đối tượng, có kế hoạch ảnh hưởng replication và ACL, tránh hồi sinh quyền sai. |
| **Forest recovery** | Sự cố trên diện rộng, mất/chiếm quyền kiểm soát nhiều DC hoặc forest. | Kế hoạch chuyên biệt, cô lập, thứ tự domain/DC, DNS, SYSVOL, trust, key và kiểm thử bảo mật. |
| **Rebuild + reconcile** | Môi trường mới hoặc dữ liệu đã không còn đáng tin, theo chiến lược được duyệt. | Không mặc định tái tạo được SID, trust, credential và mọi đường ứng dụng; cần mapping và cutover cẩn thận. |

Khôi phục **không phải luôn chọn bản mới nhất**. Nếu sự cố logic hoặc ransomware đã xuất hiện trước thời điểm backup, bản mới nhất có thể chứa dữ liệu bị hỏng hoặc backdoor. Cần xác định **last known good** bằng audit, IOC, timeline và xác minh độc lập.

**Không cho một domain controller phục hồi từ bản cũ kết nối lại với các replica đang có trạng thái không tương thích** trước khi runbook xác định rõ cách khôi phục. Nguy cơ không chỉ là downtime mà còn replication sai hoặc hồi sinh quyền.

## 6. Backup directory LDAP/OpenLDAP: data, schema và cấu hình

Directory dựa trên LDAP có thể dùng backend storage, schema, ACL, overlay và replication khác nhau tùy triển khai. Với **OpenLDAP**, một lựa chọn phổ biến để xuất dữ liệu logic là công cụ **slapcat**; nhưng file LDIF không tự chứa đầy đủ mọi thành phần khôi phục vận hành.

Các nhóm cần có trong kế hoạch:

- **Directory entries** thuộc từng suffix/database; có thể chứa user, group, service identity, thuộc tính nhạy cảm.
- **Configuration database** (ví dụ \`cn=config\`), schema, ACL, overlay, indexes, module/backend settings.
- **Replication topology** và metadata liên quan; không tự tin import LDIF là phục hồi đồng bộ replica.
- **TLS certificate/private key**, credential của replication bind account, SASL/Kerberos integration, policy và secret từ kho liên quan.
- **Filesystem permissions, service configuration, phiên bản phần mềm** và cách kiểm dữ liệu sau restore.

Ví dụ **minh họa logical export**, đường dẫn/phương thức thay đổi tùy phân phối:

~~~bash
# Chỉ thực thi theo runbook LDAP backup được phê duyệt.
# -n 0 thường biểu diễn configuration database cn=config.
slapcat -F /etc/ldap/slapd.d -n 0 -l /secure/backups/slapd-config.ldif

# -n 1 chỉ là ví dụ về database số 1; cần xác minh backend/suffix.
slapcat -F /etc/ldap/slapd.d -n 1 -l /secure/backups/directory-data.ldif
~~~

**Không giả định mọi backend/phiên bản có cùng quy tắc snapshot khi dịch vụ đang ghi.** Hãy theo tài liệu vận hành của OpenLDAP/nhà cung cấp để đảm bảo consistency. Nếu dùng online export, phải hiểu rõ dữ liệu nào nhất quán ở mốc nào; nếu dùng offline backup, cần kế hoạch ảnh hưởng dịch vụ.

### Giới hạn của LDIF

Một LDIF export có thể không chứa tất cả **file bí mật, certificate key, runtime state, replication metadata, external storage và tài nguyên ngoài directory**. Một số thuộc tính nhạy cảm (đặc biệt password verifier) có thể xuất hiện, tùy quyền và cơ chế export. Vì vậy:

- Bảo vệ LDIF **như một kho credential nhạy cảm**, không commit Git hoặc đính kèm ticket.
- Kiểm schema, ACL và tính tương thích phiên bản trước khi import.
- Thực hiện restore trong môi trường cô lập; tránh chèn dữ liệu cũ vào cluster đang phục vụ.
- Đối soát user/group/attribute và thử truy cập thực tế; một import thành công chưa chứng minh authentication hoạt động.

## 7. Managed/cloud directory: giới hạn của “backup”

Các dịch vụ directory do nhà cung cấp quản lý có thể không cho truy cập database vật lý hoặc System State như một DC tự vận hành. Tùy sản phẩm, người quản trị chỉ có thể dùng **native recovery/soft-delete**, xuất đối tượng qua API, lưu cấu hình bằng Infrastructure as Code hoặc dùng giải pháp backup được nhà cung cấp hỗ trợ.

| Thành phần | Có thể sao lưu hoặc lưu phiên bản bằng cách nào? | Không nên khẳng định |
| --- | --- | --- |
| User/group và một số thuộc tính | API/export theo quyền, phương án native hoặc đối tác được hỗ trợ. | Export JSON/CSV khôi phục đầy đủ credential và identifier nội bộ. |
| App registrations/service principals | Configuration export/IaC, inventory permissions/owners và quy trình tái lập. | Mọi private key và secret có thể đọc lại từ API. |
| Conditional access/identity policies | Versioned configuration, API hoặc công cụ chuyên dụng theo nền tảng. | Chỉ sao lưu user list là đủ phục hồi chính sách. |
| Identity governance | Workflow/configuration backup, approval record theo hệ thống nguồn. | Có thể tái dựng phê duyệt chỉ từ bản sao directory. |
| Audit/sign-in logs | Xuất định kỳ theo khả năng và retention policy. | Nhà cung cấp giữ mọi log vô hạn theo ý muốn doanh nghiệp. |
| Sessions/tokens | Quản trị bằng revoke/logout/rotation theo API hỗ trợ. | Restore user object đồng nghĩa phục hồi hoặc hủy đúng mọi phiên. |

**Ví dụ với Microsoft Entra ID hoặc nền tảng cloud directory tương tự:** các tính năng xóa mềm/khôi phục đối tượng, export cấu hình và backup của bên thứ ba có **giới hạn và mức hỗ trợ khác nhau theo loại đối tượng, thời gian giữ và dịch vụ**. Cần lập ma trận **“khôi phục được gì, bằng cách nào, mất gì và mất bao lâu”** thay vì gọi mọi bản export là full backup.

Đặc biệt, **secret đã tạo nhưng nền tảng chỉ cho xem một lần** có thể không thể xuất lại từ API. Muốn phục hồi một workload, cần quy trình tạo credential mới, cập nhật trust và triển khai an toàn, không hứa “restore nguyên private key” nếu không có bản sao được bảo vệ.

## 8. Threat model: directory backup bị lộ cũng là sự cố IAM

Directory backup có thể chứa thông tin giúp attacker **mạo danh hoặc mở rộng quyền truy cập**. Với AD DS, backup liên quan database danh tính có thể bao gồm password hashes và dữ liệu mật mã nhạy cảm; với LDAP, LDIF có thể chứa các thuộc tính credential/secret hoặc chính sách. Do đó sao lưu không đơn thuần là bài toán availability.

| Nguy cơ | Ví dụ | Kiểm soát |
| --- | --- | --- |
| **Ransomware** | Attacker xóa hoặc mã hóa toàn bộ backup cùng production. | Immutable/offline backup, isolation, backup credentials riêng và restore drill. |
| **Credential theft** | Bản AD/LDAP backup bị sao chép ra ngoài. | Mã hóa, RBAC, key management, phát hiện export bất thường. |
| **Backup deletion** | Admin hoặc tài khoản bị chiếm xóa retention/version. | WORM/immutability, separation of duties, MFA và cảnh báo. |
| **Poisoned backup** | Bản gần nhất đã chứa tài khoản backdoor hoặc group grant sai. | Nhiều điểm phục hồi, integrity/IOC check, chọn last known good. |
| **Restore sai phạm vi** | Khôi phục domain test vào production hoặc ngược lại. | Phân tách môi trường, kiểm backup ID, approval và recovery plan. |
| **Restore tràn quyền** | Phục hồi account Leaver hoặc nhóm admin đã thu hồi. | JML reconciliation từ HRIS/IGA trước khi mở truy cập. |
| **Mất khóa backup** | Dữ liệu còn nhưng không thể giải mã sau thảm họa. | Backup/recovery key procedure riêng, escrow được kiểm soát, test key access. |
| **Backup không nhất quán** | Copy database lúc đang ghi, file restore không dùng được. | Directory-aware backup, consistency check và kiểm thử restore. |
| **Lộ dữ liệu riêng tư** | File LDIF chứa email, số điện thoại, thuộc tính nhân sự. | Data minimization, access log, retention và quy định lưu trữ hợp pháp. |

### 3-2-1-1-0 như một mục tiêu vận hành

Một chiến lược thường được tham khảo là **3-2-1-1-0**: ít nhất ba bản sao dữ liệu, trên hai loại phương tiện/lớp lưu trữ, một bản ở vị trí khác, một bản immutable hoặc offline, và **không có lỗi chưa phát hiện trong kiểm chứng backup/restore**. Đây là **nguyên tắc thiết kế**, không phải chứng nhận rằng backup an toàn chỉ vì đạt số lượng.

Khi directory có thông tin credential, phải xét **khả năng attacker dùng cùng tài khoản đặc quyền để truy cập cả production và backup**. Backup admin nên được tách ranh giới tin cậy, giới hạn hành động và có phê duyệt đặc biệt cho restore hoặc thay retention.

## 9. RPO, RTO và chọn lịch sao lưu

Hai chỉ số cốt lõi của chiến lược phục hồi:

- **Recovery Point Objective (RPO):** lượng dữ liệu/thay đổi tối đa có thể mất, đo theo khoảng thời gian giữa trạng thái bị mất và điểm khôi phục.
- **Recovery Time Objective (RTO):** thời gian mục tiêu để đưa một dịch vụ/phạm vi phục hồi trở lại trạng thái hoạt động chấp nhận được.

Ví dụ một directory có RPO mục tiêu 4 giờ và RTO mục tiêu 2 giờ **không đồng nghĩa backup 4 giờ/lần sẽ chắc chắn đáp ứng**. Cần tính thời gian job chạy, lỗi backup, tính hợp lệ của restore point, thời gian khởi tạo DC/replica, dependency DNS/Kerberos và thời gian **đối soát quyền JML**.

### Ưu tiên dịch vụ và tình huống

| Hạng mục | Câu hỏi thiết kế |
| --- | --- |
| Đăng nhập nhân viên | Không có directory thì SSO, VPN, máy trạm và ứng dụng nào ngừng? |
| Directory change rate | Mỗi giờ có bao nhiêu Joiner, Mover, Leaver, reset password và group updates? |
| Replication topology | Có DC/LDAP replica ở vùng khác không? Những thay đổi xấu có replicate ngay không? |
| Ransomware risk | Backup có độc lập với quyền domain admin và mạng đang bị chiếm không? |
| Phạm vi restore | Khôi phục một object khác forest-wide disaster recovery như thế nào? |
| Compliance/retention | Thời hạn giữ dữ liệu, nơi lưu và yêu cầu xóa khi hết hạn là gì? |
| Assurance sau restore | Bao lâu mới xác minh không có account cũ đang truy cập? |

**Lịch backup phải dựa trên dữ liệu thay đổi, tác động nghiệp vụ và kết quả diễn tập**, không dựa vào một con số mẫu áp cho mọi tổ chức. Khi sự kiện JML phát sinh liên tục, cần lưu **event history hoặc nguồn sự thật còn nguyên vẹn** để tái áp thay đổi sau restore point.

## 10. Thiết kế job backup có thể kiểm chứng

Một job “thành công” cần nhiều thông tin hơn sự tồn tại của một file.

~~~mermaid
flowchart TD
    A["Lập lịch theo RPO, policy và target"] --> B["Xác minh quyền backup và trạng thái nguồn"]
    B --> C["Chạy directory-aware backup / supported export"]
    C --> D["Kiểm manifest, component, size, checksum, backup catalog"]
    D --> E["Mã hóa + chuyển kho tách biệt/immutable"]
    E --> F["Kiểm tính toàn vẹn và retention"]
    F --> G["Định kỳ restore thử trong môi trường cô lập"]
    G --> H["Kiểm directory, authentication và JML reconciliation"]
    H --> I{"Đạt RPO/RTO và test?"}
    I -->|Có| J["Lưu evidence + monitoring"]
    I -->|Không| K["Alert, investigate, sửa runbook hoặc lịch backup"]
~~~

Một bản ghi backup có thể gồm:

~~~yaml
backupJobId: directory-backup-prod-20261123-01
environment: production
directoryType: AD_DS
scope:
  forestRef: corp.example
  domainRef: corp.example
  domainControllerRef: dc1.corp.example
backupType: SYSTEM_STATE_SUPPORTED
startedAt: "2026-11-23T01:00:00Z"
completedAt: "2026-11-23T01:18:00Z"
status: BACKUP_COMPLETED
artifact:
  immutableStorageRef: backup-vault-immutable/entry-842
  manifestRef: manifest-842
  integrityCheck: PASSED
recoveryTest:
  lastVerifiedAt: "2026-11-20T05:00:00Z"
  result: PASSED
retentionPolicyRef: identity-critical-v3
~~~

**Đây là YAML minh họa**, không phải schema của Windows Server Backup, OpenLDAP hoặc một sản phẩm backup. Bản ghi này phân biệt **job backup** với **lần restore test gần nhất**. Mốc ngày và giá trị ở ví dụ chỉ có ý nghĩa giảng giải.

### Những thông tin không được đưa vào manifest

Không lưu **mật khẩu admin, private key giải mã, token truy cập backup vault hoặc nội dung secret directory** trong log/manifest. Chỉ dùng **tham chiếu an toàn, trạng thái kiểm tra, ID và metadata cần thiết** theo chính sách lưu dữ liệu.

## 11. Bảo vệ, mã hóa và quản lý truy cập kho backup

Directory backup nên được xem là **tài sản có độ nhạy cao**. Chỉ một người có quyền download bản backup có thể tiếp cận dữ liệu mật mã và thông tin danh tính mà tài khoản bình thường không thể xem.

Các lớp bảo vệ:

1. **Encrypt in transit:** bảo vệ luồng từ DC/LDAP tới backup proxy, vault và vị trí dự phòng.
2. **Encrypt at rest:** mã hóa backup bằng khóa được quản lý ngoài dữ liệu backup; phân quyền giải mã độc lập với quyền liệt kê file.
3. **Key recovery:** có phương án lấy lại khóa sau thảm họa, được escrow/bảo vệ và kiểm tra định kỳ.
4. **Least privilege:** backup operator chỉ có quyền đọc/backup theo scope; người có quyền delete/restore cần kiểm soát riêng.
5. **Separation of duties:** người thay retention hoặc khóa immutability không đồng thời đơn phương phê duyệt xóa bằng chứng quan trọng.
6. **MFA/phishing-resistant authentication** cho console quản trị backup và quyền đặc biệt khi nền tảng hỗ trợ.
7. **Offline/immutable copy:** backup không dễ bị xóa hoặc mã hóa ngay cả khi domain bị chiếm.
8. **Audit immutable:** ghi lại create, read, download, restore, delete, đổi policy, thất bại xác thực và truy cập bất thường.
9. **Data retention và location:** đáp ứng quyền riêng tư, thời hạn pháp lý và quy định khu vực lưu dữ liệu.
10. **Dọn dữ liệu tạm:** sau restore test, xóa an toàn môi trường thử chứa credential theo quy định; không để snapshot hoặc LDIF trong thư mục dùng chung.

**Backup không nên phụ thuộc duy nhất vào tài khoản Domain Admin đang tồn tại ở production.** Khi AD bị xâm nhập toàn diện, quyền dùng để khôi phục cần có ranh giới và phương án truy cập khẩn cấp đủ độc lập để không bị attacker khóa hoặc xóa.

## 12. Runbook recovery: xác định mục tiêu trước khi restore

Directory có thể gặp các tình huống rất khác nhau: một group bị xóa, một DC bị hỏng, toàn bộ forest bị mã hóa hoặc credential của directory administrator bị lộ. **Không dùng một lệnh restore chung cho mọi sự cố**.

### Bước 1 — Phân loại sự cố

| Tình huống | Mục tiêu khôi phục | Hướng xử lý cần cân nhắc |
| --- | --- | --- |
| Một user/group bị xóa nhầm | Khôi phục đối tượng/quan hệ cần thiết. | Native undelete/Recycle Bin hoặc object-level restore nếu phù hợp. |
| Một node directory hỏng | Khôi phục tính sẵn sàng mà không làm hỏng replication. | Thay node, khôi phục đúng theo tài liệu vendor; tận dụng replica khỏe nếu phù hợp. |
| Replication mang thay đổi sai | Phục hồi dữ liệu về trạng thái nghiệp vụ được phép. | Dừng luồng phát sinh lỗi, xác định phạm vi, object-level hoặc authoritative recovery phù hợp. |
| Ransomware/compromise trên nhiều DC | Khôi phục **môi trường đáng tin**, không chỉ database. | Forest recovery plan, hệ thống cô lập, chọn backup sạch, rotate credential/trust bị ảnh hưởng. |
| Cloud directory bị xóa/cấu hình sai | Khôi phục qua native feature hoặc API theo phạm vi hỗ trợ. | Xác định dữ liệu có thể khôi phục, backup/export, tái tạo cấu hình và kiểm IAM. |
| Dữ liệu sai do SCIM/IGA | Ngăn đồng bộ lỗi tiếp tục và đưa quyền về desired state. | Tạm dừng connector nguy hiểm, xác định event/revision, phục hồi và reconcile. |

### Bước 2 — Xác định phạm vi và mốc thời gian

Ghi nhận **incident ID**, phạm vi account/group, thời điểm đầu tiên phát hiện dấu hiệu lỗi, **last known good**, điểm backup an toàn, RPO/RTO và hệ thống phụ thuộc. Nếu nghi bị xâm nhập, việc chọn backup cần đối chiếu log/IOC; bản sao được tạo **sau khi attacker chiếm quyền** có thể chứa object/ACL/secret đã bị thay đổi.

### Bước 3 — Cô lập và giữ bằng chứng

Trong sự cố bảo mật, ưu tiên cô lập các thành phần bị ảnh hưởng theo kế hoạch ứng cứu: không cho replica cũ/connector tự phát lại thay đổi sai, bảo vệ backup khỏi xóa tiếp và giữ log cần thiết. Hành động cô lập có thể làm giảm khả năng đăng nhập, nên cần phối hợp với **Incident Response, IAM, hạ tầng, ứng dụng và business owner**.

### Bước 4 — Chọn phương thức restore được vendor hỗ trợ

Với AD DS, phân biệt object restore, non-authoritative, authoritative hoặc forest recovery. Với OpenLDAP, kiểm phương thức backend/export/import được hỗ trợ và điều kiện tắt/bật dịch vụ. Với cloud directory, dùng cơ chế native/API đã được đánh giá. Đừng suy rằng restore có thể hoàn tất bằng **copy file thô** hoặc import user CSV.

### Bước 5 — Khôi phục trong môi trường đủ kiểm soát

Nên thử trên **môi trường cô lập hoặc recovery staging** khi có thể. Đảm bảo DNS, time synchronization, PKI/trust, network, service dependencies và quyền phục hồi được quản lý chặt. Không cho tài khoản vừa restore truy cập Internet hoặc production API ngoài dự kiến trước khi hoàn tất đánh giá quyền.

### Bước 6 — Kiểm tra và đồng bộ lại trạng thái IAM

Sau restore kỹ thuật, IAM phải đối chiếu account, group, role với **HRIS/IGA hiện hành**. Những thay đổi phát sinh sau thời điểm backup cần được phân tích và áp lại an toàn; account đã Leaver hoặc quyền đã bị thu hồi **không được tự mở lại**.

### Bước 7 — Kích hoạt dịch vụ từng bước

Chỉ mở traffic hoặc kết nối federation/SCIM trở lại sau khi có bằng chứng: directory đúng cấu trúc, authentication hoạt động, các quyền nhạy cảm đã được soát, connector không gây drift và bảo vệ backup/credential còn nguyên vẹn.

## 13. Khôi phục AD DS: thứ tự và các điểm kiểm soát

**AD DS restore** phải dựa vào runbook cho version Windows Server, cấu trúc forest/domain, cơ chế replication và nguyên nhân sự cố. Trong sự cố diện rộng, tham khảo quy trình **forest recovery** do nhà cung cấp hướng dẫn; không thử lệnh ngẫu nhiên trực tiếp trên DC production.

### Trước restore

1. Kiểm tính hợp lệ của bản **System State** hoặc backup directory-aware: thời điểm, tính đầy đủ, thành phần, catalog và khả năng giải mã.
2. Xác minh **domain/forest/DC** nguồn, version, backup age và điều kiện supported restore.
3. Biết domain nào còn replica khỏe, replica nào nhiễm lỗi, và cách cô lập để tránh đồng bộ sai.
4. Chuẩn bị credential/khóa recovery và quy trình **Directory Services Restore Mode (DSRM)** khi phương pháp khôi phục cần; không để mật khẩu DSRM trong tài liệu công khai.
5. Xác định tình trạng **DNS, SYSVOL/GPO, SYSVOL replication, FSMO roles, trust và certificate services**.
6. Nếu có dấu hiệu compromise, đánh giá cần rotate **krbtgt**, mật khẩu tài khoản đặc quyền, service account credentials và trust secrets theo quy trình ứng cứu chuyên biệt.

### Trong và sau restore

| Thành phần kiểm tra | Mục tiêu |
| --- | --- |
| **AD database integrity** | Dữ liệu directory được khôi phục không hỏng và dịch vụ khởi tạo đúng. |
| **DNS/DC discovery** | Client và dịch vụ tìm được domain controllers đúng, bản ghi quan trọng hợp lệ. |
| **Replication health** | Các DC có trạng thái nhất quán, không rollback hoặc replication error tồn dư. |
| **SYSVOL/GPO** | Policy và script thực tế đúng version mong muốn, không phát lại cấu hình độc hại. |
| **Kerberos/authentication** | Đăng nhập thử với account được phép thành công; account đã disable bị từ chối. |
| **SID/object links** | Group membership, ACL, mapping ứng dụng còn liên kết đúng subject. |
| **High privilege** | Domain Admins, Enterprise Admins, delegated ACL, service accounts được rà soát. |
| **Time/PKI/trust** | Đồng hồ, chứng chỉ và quan hệ tin cậy phù hợp để hoạt động an toàn. |

**Không dùng một lần đăng nhập thành công của admin để kết luận recovery hoàn tất.** Thử cả user thông thường, service principal được phép, account disabled và các chính sách deny quan trọng. Nếu một số ứng dụng cần làm mới session/token, phải xử lý riêng thay vì tin AD đã phục hồi thì mọi SP tự đồng bộ.

### Khi restore một đối tượng

Khôi phục một group không nhất thiết khôi phục chính xác **membership, ACL hoặc trạng thái nghiệp vụ hiện tại**. Ví dụ, backup chứa nhóm Sales với một thành viên đã chuyển sang Finance; sau restore phải tái tính membership từ **desired state**, không chỉ “giữ nguyên dữ liệu backup”.

Nếu dùng AD Recycle Bin, cần biết tính năng đã được bật từ trước và giới hạn retention/thuộc tính theo trạng thái hệ thống. Nếu dùng authoritative restore, phải có phương án kiểm soát replication và xác minh quan hệ liên kết đúng sau khi các DC đồng bộ.

## 14. Khôi phục LDAP/OpenLDAP: tính nhất quán dữ liệu và topology

Khôi phục LDAP từ LDIF hoặc snapshot backend phải xét:

- **Schema:** các objectClass và attributeType có sẵn và tương thích trước khi nhập.
- **Config/ACL:** quyền đọc/ghi, password policies, overlays, module, indexes và TLS.
- **Backend storage:** định dạng database, permissions, quyền sở hữu thư mục và công cụ restore được hỗ trợ.
- **Replication:** provider/consumer, contextCSN, serverID hoặc thông tin tương đương theo mô hình; không tự kết nối replica cũ vào mạng khi chưa kiểm.
- **Credential/keys:** secret của bind account, certificate private key, keys/peppers ngoài LDIF cần khôi phục bằng cơ chế riêng.
- **Application mapping:** DN/suffix, memberOf/member attribute và định danh liên kết ứng dụng phải đúng.

### Luồng mẫu

~~~mermaid
flowchart TD
    I["Phát hiện lỗi LDAP"] --> S["Cô lập provider/consumer và connector gây lỗi"]
    S --> B["Chọn backup/LDIF sạch + config/schema phù hợp"]
    B --> R["Restore bằng quy trình backend được hỗ trợ"]
    R --> C["Kiểm schema, ACL, TLS, suffix, indexes"]
    C --> P["Kiểm LDAP bind/search, auth và membership"]
    P --> J["So desired JML với dữ liệu restore"]
    J --> D{"Đạt tiêu chí?"}
    D -->|Không| F["Sửa drift, xác minh lại"]
    F --> J
    D -->|Có| A["Khôi phục replication và ứng dụng từng bước"]
~~~

**Ví dụ kiểm tra logic sau restore:**

~~~text
Expected:
  baseDN = dc=company,dc=example
  employeeAccount(person-4821) = ACTIVE
  employeeAccount(person-3182) = DISABLED (Leaver)
  group(finance-invoice-readers) = desiredMembersFromIGA
  bindAccount(directory-sync) = limitedServiceAccount

Verify:
  LDAP bind with approved test identity
  LDAP search by stable identifier
  Group membership readback and nesting
  Denied bind for disabled identity
  TLS certificate and server identity
  ACL/tenant restrictions on sensitive attributes
~~~

Đây là **danh sách kiểm thử minh họa**, không phải kết quả thật. Cần tách **LDAP bind thành công** khỏi **quyền API ở ứng dụng**: nhiều ứng dụng lấy user/group lúc đăng nhập rồi lưu cache, nên sau khôi phục cần kiểm tra cả session, cache và authorization tại ứng dụng.

## 15. Khôi phục cloud directory và cấu hình liên kết

Với cloud directory, quy trình phục hồi phụ thuộc **native object restore, soft-delete, API quản trị, backup đối tác hoặc cấu hình phiên bản hóa**. Không thể áp runbook System State của AD DS lên tất cả dịch vụ SaaS.

Một recovery plan cho cloud identity nên xác định:

1. **Khả năng khôi phục từng loại object**: user, group, app registration, service principal, role assignment, policy, device và conditional access.
2. **Retention và điểm phục hồi** của native recovery; đối tượng đã bị xóa vĩnh viễn có thể không phục hồi được.
3. **Cấu hình cần tái lập** từ IaC hoặc backup/export đã được kiểm thử.
4. **Secrets/keys chỉ hiện một lần** cần cấp mới và cập nhật các ứng dụng đích khi không thể restore nguyên secret.
5. **Admin emergency access** nếu danh tính quản trị thông thường bị khóa; giữ quyền này được kiểm soát/audit.
6. **Federation trust**: SAML metadata/signing key, OIDC client registration, redirect URI, workload trust và certificate cần được soát sau recovery.
7. **SCIM connectors**: dừng/resume có kiểm soát, chống duplicate và double-provision.
8. **Đối soát vòng đời**: nguồn HRIS và IGA approvals quyết định trạng thái account/grant đúng ở thời điểm hiện tại.

**Cảnh báo về object identifier:** Một user được tạo lại thủ công sau khi mất bản ghi gốc có thể có **ID mới**. Ứng dụng đích đang tham chiếu ID cũ có thể mất mapping; tệ hơn, nếu ghép theo email mà không kiểm nguồn, dữ liệu có thể bị gán sai chủ thể. Phải thiết kế **identity linking** được phê duyệt, lưu old/new references và kiểm quyền trước khi mở truy cập.

## 16. JML reconciliation sau restore: chặn hồi sinh quyền cũ

Đây là bước riêng của IAM, không thể bỏ qua khi backup chứa trạng thái directory **ở thời điểm quá khứ**.

Giả sử:

- 00:00: Backup được tạo.
- 09:00: Ngọc chuyển từ Sales sang Finance (**Mover**).
- 13:00: Hùng nghỉ việc (**Leaver**).
- 15:00: Connector xóa nhầm một OU.
- 16:00: Directory được restore từ backup 00:00.

Trong bản restore, Ngọc có thể vẫn thuộc Sales và Hùng vẫn **ACTIVE**. Nếu mở SSO ngay, hệ thống có nguy cơ trả lại quyền đã không còn hợp lệ.

### Cách đối soát

| Thao tác | Nguồn có thẩm quyền | Kết quả cần đạt |
| --- | --- | --- |
| Lấy trạng thái nhân sự hiện hành | HRIS/contract registry. | Hùng vẫn là Leaver, Ngọc thuộc Finance. |
| Lấy approval/desired entitlements | IGA/RBAC/ABAC policy. | Chỉ các role được duyệt còn tồn tại. |
| Kiểm directory actual state | DC/LDAP/cloud directory đã restore. | Phát hiện account ACTIVE sai, group cũ và ACL dư. |
| Tính khác biệt | Desired vs actual. | Phân loại **REVOKE / KEEP / GRANT / INVESTIGATE**. |
| Thu hồi ưu tiên rủi ro | IdP, directory, SCIM/app, credential manager. | Chặn ngay account Leaver và đặc quyền không hợp lệ. |
| Cấp quyền cần thiết sau khi đã kiểm soát lỗi | IGA/connector. | Mover có quyền mới đúng, không chồng lấn SoD. |
| Xử lý session/token | IdP, OAuth AS, SP/RS. | Session cũ và token gắn quyền đã bị thu hồi không còn dùng ngoài SLA. |
| Kiểm chứng cuối đường | Resource Server và ứng dụng đích. | Effective access đúng với ngày hiện tại. |

Về mặt khái niệm:

\[
\text{RevokeCandidates} = \text{ActualAfterRestore} \setminus \text{DesiredNow}
\]

\[
\text{GrantCandidates} = \text{DesiredNow} \setminus \text{ActualAfterRestore}
\]

Tập quyền thực tế có thể có **nhiều nguồn cấp** (RBAC nhóm, ACL trực tiếp, nested group, ABAC), do đó phép chênh lệch chỉ là khung tư duy. Hành động phải dựa trên **effective permissions** và nguồn có thẩm quyền, không xóa bừa mọi account thuộc một OU.

### Không replay sự kiện tùy tiện

Nếu event Mover cũ đến sau event Leaver mới, consumer có thể cấp lại quyền. Vì vậy workflow cần:

- **Event ID và revision** để chống trùng/sai thứ tự.
- **EffectiveAt** với múi giờ được xác định rõ.
- **Trạng thái hiện hành từ nguồn HRIS**, không chỉ thứ tự message arrival.
- **Idempotent provisioning/deprovisioning** và mapping đúng target account.
- Cơ chế **pause/resume connector** cho tới khi desired state được rà soát.
- Audit các thay đổi đã tái áp và thời điểm xác minh sau recovery.

**Đừng mở lại toàn bộ kết nối SCIM và dynamic group rules ngay sau khi nạp backup** nếu chưa biết chúng sẽ đồng bộ theo hướng nào. Một connector sai có thể tiếp tục xóa hoặc tạo account/role hàng loạt.

## 17. Session, SSO và token sau khi directory phục hồi

Khôi phục directory đúng dữ liệu chưa chắc giải quyết **phiên đăng nhập đã được tạo trước hoặc trong sự cố**.

| Thành phần | Rủi ro sau restore | Hành động cần xác minh |
| --- | --- | --- |
| **IdP session** | Người dùng đã Leaver có session SSO cũ. | Revoke session/disable account theo khả năng IdP; thử login mới bị từ chối. |
| **SP local session** | SaaS đã tạo cookie cục bộ từ trước. | SLO/session termination nếu hỗ trợ; kiểm API ở SP. |
| **OAuth refresh token** | Client tiếp tục lấy token mới dù trạng thái user đã đổi. | Revoke grants/refresh tokens; kiểm token endpoint không cấp mới trái policy. |
| **JWT access token** | Token tự chứa còn hạn được API tin vì signature/exp hợp lệ. | Kiểm quyền hiện hành, denylist/version/introspection hoặc TTL theo yêu cầu. |
| **Client credentials** | Workload có secret/key dài hạn đã lộ trong backup. | Đánh giá rotate/revoke và kiểm client/grant đang hoạt động. |
| **Kerberos tickets** | Vé đã cấp trước khi khôi phục có thể còn hiệu lực theo thời hạn và chính sách. | Kết hợp account/credential response, kiểm quyền tài nguyên, và các thủ tục khẩn theo tình huống compromise. |
| **Cached application roles** | SP giữ nhóm/role cũ trong session hoặc cache. | Xóa cache, buộc re-evaluate authorization, kiểm effective access. |

### Nếu sự cố liên quan credential compromise

Không chỉ restore dữ liệu rồi cho chạy lại. Trong sự cố ảnh hưởng **directory secrets, administrator credentials hoặc khóa ký**, nhóm ứng cứu cần phân tích cần rotate hoặc thu hồi khóa nào. Với AD DS, **krbtgt** là thành phần đặc biệt nhạy cảm đối với Kerberos; kế hoạch reset an toàn sau compromise phải tuân theo hướng dẫn hỗ trợ và kiểm tác động replication/ticket. Không tự xoay các khóa quan trọng theo thao tác tùy hứng.

Với OAuth/OIDC hoặc SAML, có thể cần thay **client secret, signing keys, federation trust/certificates** và thu hồi phiên đã cấp khi bị ảnh hưởng. Việc thay khóa một phía không đủ nếu các bên còn tin khóa cũ hoặc token cũ chưa bị chặn.

## 18. Kiểm chứng restoration: data, authentication và authorization

Một buổi **restore drill** đạt yêu cầu cần chứng minh ba lớp:

1. **Data integrity:** directory objects, schema, quan hệ, config và dữ liệu cần thiết có thể khôi phục nhất quán.
2. **Authentication functionality:** người dùng/dịch vụ hợp lệ xác thực được; account bị disable hoặc credential bị thu hồi bị từ chối.
3. **Authorization correctness:** group, ACL, role, ABAC và API decisions đúng theo desired state **hiện tại**, không chỉ đúng tại thời điểm backup.

| Loại test | Ví dụ | Kết quả kỳ vọng |
| --- | --- | --- |
| Backup catalog/manifest | Có đúng backup point và component mong muốn. | Metadata toàn vẹn, đủ nguồn và giải mã được. |
| Directory schema/objects | Kiểm OU, user, group, identifier. | Đúng mapping, không tạo trùng. |
| Search và bind | LDAP bind/search với principal test. | Account hợp lệ làm việc, disabled account bị từ chối. |
| AD replication/DNS | Kiểm hoạt động giữa DC, SRV records, SYSVOL. | Không lỗi replication/kết nối gây sai login. |
| Group membership | So nhóm nhạy cảm với desired IGA. | Không có member đã Leaver/Mover ngoài ngoại lệ. |
| Privileged access | Thử chính sách admin/PAM/vault. | Không tự khôi phục đặc quyền đã bị thu hồi. |
| IdP/SSO | Login qua OIDC/SAML với account test. | Authentication/assurance đúng, token issuer/audience hợp lệ. |
| OAuth token lũy kế | Dùng luồng thử đã được phê duyệt với token cũ. | Quyền đã thu hồi bị RS chặn trong SLA. |
| SCIM/provisioning | Đồng bộ user/group test có kiểm soát. | Không duplicate, không xóa lại object hợp lệ. |
| Secrets/service identities | Kiểm workload được phép và secret/trust đang dùng. | Dịch vụ hợp lệ hoạt động, credential rủi ro đã xử lý. |
| Audit trail | Liên kết event HRIS, restore, deprovision. | Có bằng chứng theo mốc thời gian và policy version. |

### Negative test phải có positive control

Nếu LDAP query thất bại vì DNS hoặc server down, điều đó **không chứng minh** account bị thu hồi đúng chính sách. Cần một **positive control** chứng minh dịch vụ/endpoint đang hoạt động với principal thử hợp lệ, sau đó kiểm hành động bị cấm. Đừng diễn giải HTTP 503 hoặc lỗi mạng như một kết quả authorization deny.

**Kiểm thử phải được cấp phép, an toàn và không phá hoại.** Không dùng tài khoản thật của người nghỉ việc để thử truy cập dữ liệu nhân sự nhạy cảm; hãy dùng test principal/resource hoặc API policy simulator đáng tin khi có thể.

## 19. Pseudocode Java: đối soát directory sau khôi phục

Đây là **mã diễn giải quy trình**, không phải bộ khôi phục AD DS/LDAP hoặc Java API có thể chạy trực tiếp. Các bước restore vật lý phải do runbook và công cụ được nhà cung cấp hỗ trợ thực hiện.

~~~java
// Pseudocode: chạy SAU khi directory restore kỹ thuật hoàn tất,
// và TRƯỚC khi mở các đường truy cập nhạy cảm theo policy.
RecoveryVerificationReport reconcileAfterDirectoryRestore(
        TrustedRecoveryContext recovery) {

    recoveryPolicy.requireApprovedIncident(recovery.incidentId());
    recoveryPolicy.requireTrustedBackupManifest(recovery.backupRef());

    // Dữ liệu hiện hành của HRIS/IGA không lấy từ backup directory đã cũ.
    WorkforceSnapshot workforce = hrRepository.currentTrustedSnapshot();
    DesiredEntitlements desired = igaPolicy.calculateDesiredState(workforce);

    DirectorySnapshot actual = directoryReader.readRestoredState();
    RecoveryVerificationReport report =
        new RecoveryVerificationReport(recovery.incidentId());

    // Chặn trước các quyền có rủi ro cao và tài khoản đã Leaver.
    for (RevocationAction action : accessDiff.revocations(actual, desired)) {
        if (action.isHighRiskOrLeaver()) {
            connector(action.target()).revokeIdempotently(action);
            report.recordReadback(
                action,
                authorizationVerifier.verifyNoUnapprovedAccess(action)
            );
        }
    }

    // Chỉ cấp quyền mới sau approval/SoD và mốc hiệu lực đã kiểm.
    for (GrantAction action : accessDiff.grants(actual, desired)) {
        approvalPolicy.assertCurrentlyAllowed(action);
        sodPolicy.assertNoProhibitedOverlap(action);
        connector(action.target()).grantIdempotently(action);
    }

    // Bao gồm accounts tại SP, phiên, token và các quyền nằm ngoài directory.
    report.merge(connectedAppsReconciler.verifyTargets(desired));
    report.merge(sessionAndTokenVerifier.verifyLifecycleRestrictions(workforce));
    report.merge(serviceIdentityVerifier.verifyOwnersAndTrust(workforce));

    if (report.allRequiredTargetsVerified()
            && report.hasNoUnapprovedResidualAccess()) {
        report.markReadyForControlledCutover();
    } else {
        incidentWorkflow.escalateUnverifiedTargets(report);
    }
    audit.persistMetadataWithoutSecrets(report);
    return report;
}
~~~

Điều kiện để triển khai thực:

- **Không đọc từ bản restore như nguồn HR truth** khi đánh giá nhân viên còn active.
- **Không cấp quyền mới trước khi gỡ các quyền xung đột** nếu có Separation of Duties.
- **Idempotency và revision** giúp retry không tạo trùng user/group hoặc hồi sinh quyền cũ.
- **Readback tại đích** mới chứng minh việc gỡ/khôi phục đã áp; HTTP 200 chỉ là bước trung gian.
- **Coverage gap không được coi là PASS**: SP không có API kiểm tra quyền phải có phương án chứng minh thay thế và owner xử lý.
- **Log không chứa credential/secret**, kể cả khi backup đang được xử lý bởi môi trường recovery.

## 20. Tình huống thực hành: xóa nhầm OU rồi phục hồi

### Bối cảnh

Công ty có AD DS phục vụ workstation sign-in và nhóm IAM, IdP làm SSO, SCIM connector đồng bộ user/group sang một ứng dụng CRM. Sáng thứ Hai, connector cấu hình sai xóa nhầm các đối tượng trong một OU. Tối Chủ nhật đã có System State backup hoàn chỉnh và một bản copy immutable đã được kiểm tra gần đây.

Trong khoảng từ backup đến sự cố:

- **Linh (Joiner)** được kích hoạt tài khoản hợp lệ.
- **An (Mover)** từ Sales chuyển sang Finance và không còn được xuất dữ liệu CRM.
- **Bình (Leaver)** đã nghỉ và bị disable trước khi OU bị xóa.

### Bước 1 — Khoanh vùng

IAM cô lập connector lỗi theo kế hoạch, thu thập event IDs và xác định object đã bị xóa nhầm. Đội AD xem khả năng phục hồi đối tượng từ **AD Recycle Bin** nếu có và phù hợp; chỉ chuyển sang phương án restore rộng hơn khi cần. Mục tiêu là **không rollback toàn bộ forest** nếu một thao tác object-level đáp ứng yêu cầu và ít rủi ro hơn.

### Bước 2 — Chọn bản và cơ chế restore

Nhóm recovery xác minh manifest và độ tin cậy của bản sao. Họ đối chiếu backup time, replication health, dữ liệu cần khôi phục và phương pháp được vendor hỗ trợ. Nếu phải dùng backup cũ, họ ghi rõ sự kiện JML sau mốc backup cần tái áp.

### Bước 3 — Phục hồi trong môi trường kiểm soát

Đội directory thực hiện quy trình phù hợp, kiểm dữ liệu và replica trước khi mở lại luồng đồng bộ. Connector nguy hiểm vẫn tạm dừng để tránh xóa lần hai. Logs/backup evidence được bảo vệ khỏi sửa hoặc thất lạc.

### Bước 4 — Reconcile sự kiện JML

| Nhân sự | Trạng thái trong backup tối Chủ nhật | Trạng thái hiện hành | Hành động bắt buộc |
| --- | --- | --- | --- |
| Linh | Chưa có hoặc chưa active. | **Joiner đã được duyệt.** | Tạo/link account đúng ID, cấp quyền cơ sở khi đủ điều kiện. |
| An | Vẫn thuộc Sales. | **Mover sang Finance.** | Gỡ quyền Sales, cấp Finance đúng phê duyệt; xử lý phiên/role CRM. |
| Bình | Có thể vẫn active. | **Leaver.** | Disable, revoke session/token, deprovision app và kiểm mọi đường truy cập. |

**Phục hồi dữ liệu directory xong nhưng chưa áp ba thay đổi này thì hệ thống chưa an toàn để mở lại quyền nghiệp vụ.**

### Bước 5 — Kiểm cuối đường

Test account hợp lệ đăng nhập SSO được; account Leaver bị từ chối; An không còn được CRM cho xuất dữ liệu; Linh nhận đúng nhóm đã được duyệt. Đội IAM kiểm các nhóm admin, ACL trực tiếp, app-local permissions, SCIM mappings, service accounts và token còn hạn theo scope recovery plan.

### Bước 6 — Đóng incident và cải tiến

Lưu bản đồ trước/sau, thời điểm restore, kết quả readback, RPO/RTO thực tế và lỗi connector. Sửa cấu hình connector và triển khai test/canary/approval để ngăn xóa hàng loạt lần sau. Chỉ đóng hồ sơ khi **mọi target bắt buộc VERIFIED** hoặc có ngoại lệ đã được phê duyệt, có owner và thời hạn xử lý.

## 21. Ma trận kiểm thử directory backup và recovery

| ID | Tình huống kiểm thử | Kết quả kỳ vọng |
| --- | --- | --- |
| D01 | Sao lưu khi directory có lưu lượng ghi bình thường. | Backup hoàn tất theo phương pháp consistency được hỗ trợ và manifest đầy đủ. |
| D02 | Replica đều khỏe nhưng một admin xóa nhầm group. | Replication không bị coi là backup; có điểm phục hồi hoặc undelete phù hợp. |
| D03 | File backup tồn tại nhưng khóa giải mã đã mất. | Restore drill FAIL; kích hoạt xử lý key recovery. |
| D04 | Backup chứa credential nhạy cảm, user thường truy cập vault. | Bị từ chối; chỉ actor được phê duyệt có quyền đọc/giải mã. |
| D05 | Tài khoản Domain Admin bị chiếm cố xóa backup immutable. | Bị chặn theo ranh giới và policy đã thiết kế; tạo alert. |
| D06 | Khôi phục DC từ snapshot không được hỗ trợ. | Runbook từ chối phương pháp không bảo đảm consistency/replication. |
| D07 | Backup AD không có SYSVOL/GPO phụ thuộc cần thiết. | Không đánh dấu đủ phạm vi restore; bổ sung kế hoạch backup. |
| D08 | OpenLDAP LDIF có data nhưng thiếu schema/config. | Báo missing dependency; không kết luận phục hồi đầy đủ. |
| D09 | Cloud export có Users nhưng thiếu app registrations hoặc secrets. | Ghi rõ coverage gap và phương án tái tạo theo hỗ trợ vendor. |
| D10 | Restore xong nhưng user Leaver trong backup còn ACTIVE. | Đánh dấu chưa an toàn, disable/revoke theo HRIS hiện hành. |
| D11 | Mover còn nhóm cũ từ thời điểm backup. | Thu hồi quyền cũ, kiểm SoD và effective access. |
| D12 | Joiner hợp lệ xuất hiện sau backup. | Tạo/link theo nguồn có thẩm quyền, không gộp nhầm theo email. |
| D13 | SCIM connector chạy lại event cũ sau recovery. | Chặn stale/duplicate bằng revision và desired state. |
| D14 | IdP disable đã PASS nhưng CRM session cũ còn gọi API được. | Deprovision chưa VERIFIED; xử lý session/RS theo SLA. |
| D15 | OAuth JWT còn hạn và chứa role cũ. | RS không cho phép quyền đã thu hồi theo cơ chế kiến trúc được thiết kế. |
| D16 | Service account vẫn chạy nhưng owner đã Leaver. | Chuyển owner, gỡ quyền cá nhân và đánh giá secret rotation. |
| D17 | Đăng nhập thử thất bại vì DNS down. | Không kết luận authorization deny; sửa DNS và thử lại với positive control. |
| D18 | Một AD replica chứa thay đổi xấu chưa được cô lập. | Chưa rejoin/re-enable replication tùy tiện trước khi xác minh. |
| D19 | Recovery test làm lộ LDIF vào thư mục chia sẻ. | Test không đạt; xử lý lộ dữ liệu và dọn môi trường thử. |
| D20 | RTO chỉ đo lúc database restore, bỏ qua SCIM/JML reconciliation. | Báo metric chưa đủ; đo đến mức dịch vụ và quyền vận hành chấp nhận được. |
| D21 | Backup gần nhất có dấu hiệu attacker thêm tài khoản đặc quyền. | Không chọn mặc định; đánh giá last known good và điều tra. |
| D22 | Một ứng dụng legacy không hỗ trợ readback quyền. | Ghi blocker/coverage gap, yêu cầu owner xác minh thay thế. |
| D23 | Restore thành công trong lab, nhưng không có lần test gần đây trên version hiện tại. | Không suy tự động production readiness; lập thử nghiệm tương thích. |
| D24 | Hết retention hợp lệ, backup chứa dữ liệu danh tính nhạy cảm. | Xóa theo cơ chế/policy đã được phê duyệt, giữ bằng chứng cần thiết. |

### Xác minh “khôi phục được” bằng kết quả thực tế

Mỗi bài kiểm thử cần gắn với **backup ID, thời điểm, version, target, evidence và actor**. Không tính job backup đã hoàn tất như một lần restore test thành công. Để đo khả năng phục hồi thật, cần có định kỳ **tabletop exercise**, **restore drill trong lab** và khi phù hợp, các thử nghiệm cutover được tổ chức chấp thuận.

## 22. Audit, vận hành và chỉ số theo dõi

Một hồ sơ audit có ích cho directory backup cần nối được **cấu hình backup → bản sao → lần thử restore → kết quả JML reconciliation**.

| Nhóm bằng chứng | Metadata cần lưu | Câu hỏi kiểm toán |
| --- | --- | --- |
| Backup policy | Policy version, owner, target, RPO/RTO, retention. | Ai chịu trách nhiệm và mục tiêu là gì? |
| Backup execution | Job ID, timestamp, component, backup point, status, manifest. | Đã tạo bản sao vào lúc nào, từ nguồn nào? |
| Storage security | Vault reference, encryption/key ref, immutability, access log. | Ai có thể đọc/xóa/restore backup? |
| Restore rehearsal | Lab environment, software version, method, duration, test cases. | Bản backup có thể dùng để khôi phục không? |
| Incident recovery | Incident ID, approval, last known good, timeline, actual RPO/RTO. | Tại sao chọn bản/method đó? |
| Data integrity | Directory objects, schema, replication, GPO/DNS check. | Dữ liệu/điều kiện vận hành có đúng không? |
| JML reconciliation | HRIS revision, group/role before/after, readback, exceptions. | Tài khoản Leaver và quyền Mover có bị hồi sinh không? |
| Session/token checks | IdP/SP session refs, result, API access check. | Quyền cũ còn dùng được sau restore không? |
| Change management | Certificate rotation, connector restart, trusted changes. | Khi nào hệ thống được phép kết nối lại production? |

Các KPI:

- **Backup success rate:** tỷ lệ job tạo được artifact đúng policy.
- **Restore verification success rate:** tỷ lệ bản sao qua được kiểm tra phục hồi thực tế.
- **RPO/RTO achieved:** so sánh mục tiêu với kết quả đo theo từng loại sự cố.
- **Age of last verified restore:** thời gian từ lần diễn tập thành công gần nhất.
- **Immutable/offsite coverage:** tỷ lệ dữ liệu/phạm vi directory có bản sao được bảo vệ độc lập.
- **Backup credential exposure:** sự kiện truy cập/giải mã/tải backup bất thường.
- **Post-restore entitlement drift:** số quyền khác desired state sau phục hồi.
- **Residual access after recovery:** số account/role/session trái chính sách còn sử dụng được.
- **JML reconciliation latency:** thời gian đưa mọi thay đổi JML hợp lệ về trạng thái đúng sau restore.
- **Coverage gaps:** hệ thống/thuộc tính/chứng chỉ không thể phục hồi hoặc kiểm chứng bằng giải pháp hiện có.

**Không tối ưu KPI bằng cách chỉ đếm bản backup.** Có nhiều bản sao nhưng không giải mã được, không khôi phục được DNS/Kerberos hoặc làm sống lại quyền Leaver vẫn là một chiến lược thất bại.

## 23. Sai lầm phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Coi nhiều DC/replica là đã có backup. | Xóa sai hoặc ransomware lan rộng, không có điểm phục hồi sạch. | Backup độc lập, kiểm restore định kỳ. |
| Copy raw database đang ghi rồi coi là nhất quán. | Restore lỗi/corrupt. | Phương pháp application-consistent được vendor hỗ trợ. |
| Coi VM snapshot là chiến lược AD restore chung. | Rủi ro replication inconsistency/rollback. | AD-aware backup và runbook được hỗ trợ. |
| Chỉ lưu LDIF user/group, bỏ schema/ACL/TLS. | Directory hoạt động sai hoặc không thể tái lập. | Backup cấu hình, khóa, phụ thuộc và test restore. |
| Không tách backup admin khỏi quyền production. | Attacker chiếm domain rồi xóa cả backup. | Ranh giới riêng, least privilege, immutability. |
| Backup mã hóa nhưng không thử khôi phục khóa. | Không giải mã được khi thảm họa. | Escrow và test key recovery có phê duyệt. |
| Restore snapshot cũ rồi mở ngay SSO. | Hồi sinh tài khoản nghỉ việc và role cũ. | JML reconciliation và chặn quyền rủi ro trước cutover. |
| Chỉ nhìn user count để kết luận đúng. | Group/ACL, ID, policy, trust bị lệch. | Kiểm schema, object mapping, effective permissions. |
| Khôi phục account bằng email trùng. | Liên kết nhầm identity hoặc cấp dữ liệu sai người. | Stable ID/mapping và kiểm nguồn có thẩm quyền. |
| Mở SCIM connector ngay sau restore. | Đồng bộ lại thay đổi sai/xóa hàng loạt. | Pause, kiểm event revision, canary và resume kiểm soát. |
| Quên phiên/token đang lưu hành. | Access cũ vẫn được API/SaaS chấp nhận. | Revoke/reauthorize tại IdP, SP và RS. |
| Lộ NTDS/LDIF backup vào ticket/log. | Phơi bày dữ liệu credential và thông tin cá nhân. | Secret handling, mã hóa, audit access, incident response. |
| Chỉ thử restore trên một version từ nhiều năm trước. | Runbook không còn tương thích hạ tầng hiện tại. | Diễn tập định kỳ sau upgrade/topology change. |
| Chỉ đo thời gian restore database. | RTO không bao gồm DNS, login, connector và IAM policy. | Đo service readiness và effective-access verification. |

## 24. Checklist trước khi đánh dấu Directory recovery hoàn tất

1. **Backup tin cậy:** đúng nguồn, đúng phạm vi, còn hợp lệ, không có chỉ báo bị chỉnh sửa và giải mã được.
2. **Phương pháp được hỗ trợ:** restore tương thích AD DS/LDAP/cloud directory, version và topology.
3. **Dữ liệu đầy đủ:** user, group, schema, ACL, policy và các thành phần phụ thuộc đã được kiểm.
4. **Hạ tầng hoạt động:** DNS, replication, clock, SYSVOL/GPO, TLS/PKI và IdP dependency đúng trạng thái.
5. **Danh tính ổn định:** mapping ObjectGUID/SID/subjectID/app IDs không sai người hoặc trùng.
6. **Nguồn JML hiện hành:** HRIS, IGA approvals, event revision được dùng để tính desired state.
7. **Leaver bị chặn:** account, phiên và token không còn cấp quyền trái chính sách.
8. **Mover không còn quyền cũ:** group, direct grants, ACL và SoD đã được kiểm chứng.
9. **Joiner đúng thời điểm:** user mới được cấp account/quyền sau approval, không kích hoạt sớm.
10. **Workload còn owner và bảo đảm:** service account/trust/secret được rà soát, không giữ quyền của nhân viên cũ.
11. **Ứng dụng đích đã đối soát:** SCIM/provisioning, SaaS và API đúng quyền sau cutover.
12. **Bằng chứng và SLA:** readback, test, exception, RPO/RTO và sign-off được lưu an toàn.

Nếu một điều kiện bắt buộc chưa đạt, kết quả nên được ghi là **IN_PROGRESS, BLOCKED hoặc EXCEPTION_APPROVED** theo policy; không tự ghi **VERIFIED** chỉ vì directory service đã khởi động lại.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Có ba domain controller đang replication khỏe. Có thể bỏ hẳn directory backup không?

**Trả lời:** Không. Replication giúp tăng sẵn sàng nhưng có thể nhân bản thay đổi sai, xóa nhầm hoặc cấu hình độc hại. Cần backup có thể khôi phục từ trước sự cố và được bảo vệ độc lập.

**Câu 2.** Vì sao một LDIF export thành công chưa chắc đủ để dựng lại OpenLDAP?

**Trả lời:** LDIF có thể không chứa toàn bộ configuration, schema, ACL, TLS private key, backend settings, replication state và các phụ thuộc bên ngoài. Phải kiểm phạm vi và restore thực tế.

**Câu 3.** Khi khôi phục AD DS, có nên mặc định restore toàn forest nếu chỉ một group bị xóa?

**Trả lời:** Không. Cần đánh giá native object recovery/Recycle Bin hoặc object-level restore trước, chọn phương án ít rủi ro phù hợp và được hỗ trợ.

**Câu 4.** Điều nguy hiểm nhất khi restore bản backup directory từ hôm qua trong lúc có nhân viên nghỉ việc hôm nay là gì?

**Trả lời:** Bản backup có thể chứa account/role cũ ở trạng thái active, khiến quyền đã thu hồi được hồi sinh. Cần đối soát HRIS/IGA hiện hành và chặn effective access trước khi mở lại hệ thống.

**Câu 5.** Vì sao thay khóa/chặn đăng nhập tại IdP sau restore chưa chứng minh mọi quyền API đã bị thu hồi?

**Trả lời:** Session ở SP, refresh token, JWT access token còn hạn và API key độc lập có thể còn hoạt động. Cần cơ chế revoke/current-state check và kiểm quyền tại Resource Server.

**Câu 6.** Directory backup mã hóa có còn rủi ro nếu Domain Admin truy cập được backup vault?

**Trả lời:** Có. Nếu cùng tài khoản hoặc quyền bị chiếm có thể tải/xóa bản sao hoặc lấy khóa giải mã, backup không còn độc lập. Cần ranh giới quản trị, least privilege, immutability và bảo vệ khóa.

**Câu 7.** Chỉ số RTO nên dừng khi dịch vụ LDAP trả lời TCP request chưa?

**Trả lời:** Chưa chắc. Mục tiêu nghiệp vụ thường cần login, DNS, trust, ứng dụng, nhóm/quyền và JML reconciliation hoạt động chấp nhận được. Cần xác định RTO theo dịch vụ và mức an toàn yêu cầu.

**Câu 8.** Một managed cloud directory có export JSON danh sách user. Có thể coi đó là bản sao lưu đầy đủ không?

**Trả lời:** Không. Export có thể thiếu credentials, group/role relation, policy, service principal keys, sessions, audit và identifier. Cần ma trận khả năng phục hồi theo từng loại đối tượng và khả năng vendor hỗ trợ.

**Câu 9.** Sau restore, một account đã Leaver bị disabled nhưng vẫn đọc dữ liệu SaaS bằng local session. Có thể đóng recovery chưa?

**Trả lời:** Chưa. Cần xử lý local session, token/permission tại SaaS và kiểm chứng access bị từ chối theo phạm vi/SLA của kế hoạch.

**Câu 10.** Vì sao cần thử cả trường hợp đăng nhập hợp lệ (positive control) và trường hợp bị từ chối (negative test)?

**Trả lời:** Một lỗi kết nối/DNS/HTTP 503 có thể trông giống “không truy cập được” nhưng không chứng minh phân quyền từ chối đúng. Positive control giúp xác nhận điểm thực thi đang hoạt động trước khi đánh giá negative test.

---

**Ghi nhớ:** **Directory backup là năng lực khôi phục danh tính và quyền truy cập an toàn, không chỉ sao chép dữ liệu.** Replication không thay thế bản backup có thể restore; AD DS, LDAP và cloud directory cần phương pháp phù hợp từng nền tảng. Sau khôi phục, IAM phải **đối soát với HRIS/IGA hiện hành, vô hiệu lại Leaver, gỡ quyền cũ của Mover, kiểm session/token ở IdP/SSO và ứng dụng, kiểm service accounts và ghi audit**. Chỉ khi **dữ liệu nhất quán, xác thực hoạt động và effective access đúng chính sách** mới nên coi recovery đã hoàn tất.

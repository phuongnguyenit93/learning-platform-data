# Kiểm chứng phục hồi, đối soát dữ liệu và quy trình xử lý sự cố

Triển khai một ứng dụng dùng **Spring Data LDAP** không kết thúc ở thời điểm service khởi động và kết nối được tới directory. Trong vận hành, LDAP server có thể mất node, hỏng database, nhận nhầm thay đổi schema, bị xóa nhầm entry, mất chứng thư TLS hoặc bị gián đoạn replication. Sau khi khôi phục dịch vụ, ứng dụng vẫn có thể gặp dữ liệu thiếu, group membership sai hoặc workflow provisioning bị dở dang.

Một kế hoạch triển khai đáng tin cậy cần trả lời ba câu hỏi:

1. **Có thể phục hồi dịch vụ và dữ liệu tới thời điểm nào?** Đây là phạm vi của backup, restore và mục tiêu RPO/RTO.
2. **Làm sao chứng minh dữ liệu sau phục hồi đúng?** Đây là phạm vi của kiểm chứng phục hồi và reconciliation.
3. **Ai làm gì khi sự cố xảy ra?** Đây là phạm vi của incident runbook, phân quyền, điều phối và bằng chứng vận hành.

Bài học này hướng dẫn xây dựng quy trình phục hồi cho Spring Data LDAP trong môi trường production. Nội dung bao gồm lập mục tiêu phục hồi, bảo vệ dữ liệu và cấu hình directory, phân biệt cách khôi phục OpenLDAP với Active Directory, kiểm chứng sau restore, đối soát với nguồn dữ liệu có thẩm quyền, chuyển endpoint an toàn và xử lý sự cố từ lúc phát hiện tới khi đóng incident.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định RPO, RTO, phạm vi dữ liệu và dependency cần bảo vệ.
- Thiết kế backup cho cả dữ liệu LDAP, schema, cấu hình, chứng thư và thông tin vận hành.
- Phân biệt backup nhất quán ở mức database với trạng thái nhất quán của một workflow nghiệp vụ.
- Lập quy trình backup/restore riêng cho OpenLDAP và Active Directory.
- Phân biệt authoritative restore, nonauthoritative restore và phục hồi một domain controller mới.
- Khôi phục trong môi trường cô lập trước khi đưa node trở lại production.
- Kiểm chứng Root DSE, naming context, bind, ACL, TLS, schema, entry và replication.
- Đối soát LDAP với HR, identity provider hoặc nguồn dữ liệu có thẩm quyền.
- Thiết kế cutover/failover tránh split-brain và ghi đồng thời lên hai writer.
- Tích hợp Spring Data LDAP với endpoint phục hồi, health check và connection lifecycle.
- Thực hiện incident runbook, ghi audit và lưu bằng chứng phục hồi.

## 2. Xác định phạm vi phục hồi

Trước khi chọn công cụ backup, hãy xác định hệ thống cần phục hồi gồm những thành phần nào. Một LDAP service production thường có nhiều dependency ngoài file database.

### 2.1. Danh mục thành phần

| Thành phần | Nội dung cần bảo vệ | Hậu quả nếu thiếu |
| --- | --- | --- |
| Directory data | Entry, attribute, DN, group membership, operational attributes | Người dùng, group hoặc quan hệ directory bị mất. |
| Schema | Attribute type, object class, OID, syntax, matching rule | Entry không được đọc/ghi đúng hoặc server không khởi động. |
| Server configuration | Database suffix, backend, module, overlay, ACL, limits, replication | Directory chạy sai hành vi hoặc từ chối request hợp lệ. |
| TLS material | Server certificate, private key, CA chain, truststore | Client không xác thực được endpoint hoặc TLS handshake thất bại. |
| Service credentials | Bind account, secret, password policy, credential rotation state | Ứng dụng không thể bind hoặc dùng sai quyền. |
| DNS và network | LDAP/LDAPS hostname, SRV record, firewall, load balancer | Client kết nối nhầm node hoặc không tìm thấy endpoint. |
| Replication metadata | Sync cookie, context CSN, invocation/USN metadata tùy server | Replica không hội tụ hoặc cần khởi tạo lại. |
| Application configuration | Base DN, URL, timeout, pool, secret reference | Spring Data LDAP không thể kết nối hoặc truy vấn sai phạm vi. |
| Workflow state | Operation ID, checkpoint, outbox/inbox, trạng thái provisioning | Khôi phục directory nhưng không biết thao tác nghiệp vụ nào đã hoàn tất. |
| Audit và monitoring | Access/audit log, backup log, incident timeline | Khó xác định thời điểm sai lệch và chứng minh kết quả phục hồi. |

Không phải mọi thành phần đều nằm trong cùng một backup. Hãy lập manifest chỉ rõ nguồn, chủ sở hữu, lịch backup, cách restore và nơi lưu.

### 2.2. RPO và RTO

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa tổ chức chấp nhận mất, tính theo thời gian. RPO 15 phút nghĩa là sau sự cố, dữ liệu được phục hồi không cũ hơn quá 15 phút so với thời điểm sự cố theo mục tiêu đã thống nhất.
- **RTO (Recovery Time Objective):** thời gian tối đa cho phép để khôi phục dịch vụ về mức vận hành đã định nghĩa.

Ví dụ:

| Thành phần | RPO mục tiêu | RTO mục tiêu | Cách đạt mục tiêu |
| --- | --- | --- | --- |
| LDAP authentication | 5 phút | 30 phút | Replication đa node, backup định kỳ, endpoint failover. |
| Directory profile | 15 phút | 2 giờ | Backup nhất quán, restore rehearsal và reconciliation. |
| Audit log | 1 giờ | 4 giờ | Export log sang kho lưu trữ độc lập. |
| Workflow provisioning | 1 phút | 30 phút | Database backup, transaction log và outbox bền vững. |

Đây chỉ là ví dụ. RPO/RTO phải do chủ hệ thống và nghiệp vụ xác nhận. Replication có thể giảm thời gian chuyển node, nhưng không thay thế backup vì thao tác xóa nhầm hoặc dữ liệu hỏng cũng có thể được replicate.

### 2.3. Xác định mức độ sự cố

| Mức | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Một ứng dụng không bind được | Sai secret, DNS cache, certificate hết hạn | Kiểm tra từ ứng dụng tới endpoint; không restore directory ngay. |
| Một LDAP node hỏng, replica còn khỏe | Disk failure, service crash | Fencing node hỏng; failover hoặc dựng node mới và đồng bộ. |
| Một naming context bị sai lệch | Xóa nhầm entry, ghi sai group membership | Khôi phục dữ liệu có chọn lọc hoặc reconcile từ source of truth. |
| Toàn bộ directory bị mất | Hỏng storage, ransomware, mất site | Kích hoạt disaster recovery plan và phục hồi từ backup sạch. |
| Cấu hình/schema bị hỏng | slapd không start, schema OID sai | Phục hồi config/schema tương thích trước khi nạp data. |
| Compromise identity | Bind credential hoặc quyền quản trị bị lộ | Cô lập, điều tra, khôi phục từ nguồn tin cậy và rotate credential. |

Không chọn quy trình restore toàn bộ chỉ vì một ứng dụng báo lỗi LDAP. Trước hết phải phân biệt lỗi client, lỗi mạng, lỗi server, lỗi dữ liệu và lỗi replication.

## 3. Thiết kế backup nhất quán

Backup chỉ có giá trị khi có thể khôi phục và chứng minh được dữ liệu sau restore. Một file LDIF tạo thành công chưa đủ chứng minh backup bao phủ toàn bộ directory hoặc phản ánh một trạng thái nghiệp vụ nhất quán.

### 3.1. Directory backup và application consistency

Giả sử một workflow tạo người dùng bằng nhiều thao tác:

1. Tạo entry uid=alice.
2. Thêm Alice vào group cn=engineering.
3. Cập nhật trạng thái provisioning.

Nếu backup được tạo sau bước 1 nhưng trước bước 2, dữ liệu backup có thể hợp lệ theo LDAP nhưng không phản ánh trạng thái workflow hoàn chỉnh. Sau restore, Alice tồn tại nhưng thiếu group membership.

Đây là khác biệt giữa:

- **Database-consistent backup:** backend có thể được phục hồi về một trạng thái dữ liệu hợp lệ.
- **Application-consistent recovery point:** trạng thái phản ánh một ranh giới nghiệp vụ đã được phối hợp hoặc có đủ journal/checkpoint để tiếp tục.

Để giảm rủi ro:

- Có thể đưa provisioning vào maintenance/read-only window khi tạo backup quan trọng.
- Hoặc dùng workflow journal/outbox và checkpoint để biết thao tác nào đã hoàn tất.
- Ghi timestamp, server/node, suffix và trạng thái replication vào backup manifest.
- Sau restore, chạy reconciliation để hoàn tất hoặc sửa workflow dở dang.

Không giả định một snapshot filesystem tự động đồng bộ với trạng thái của các hệ thống khác.

### 3.2. Lịch backup

Một lịch mẫu:

| Loại backup | Tần suất minh họa | Mục đích |
| --- | --- | --- |
| Full backup dữ liệu | Hằng ngày | Khôi phục cơ sở dữ liệu directory. |
| Incremental/log backup nếu backend hỗ trợ | Theo RPO | Giảm mất dữ liệu giữa hai full backup. |
| Backup cấu hình và schema | Sau mỗi thay đổi; kèm backup định kỳ | Khôi phục đúng cấu hình tương thích. |
| Export audit/access log | Liên tục hoặc theo batch ngắn | Điều tra và xác định thay đổi. |
| Backup certificate/secret metadata | Khi rotate và theo chính sách | Khôi phục TLS/bind integration. |
| Restore rehearsal | Theo lịch định kỳ và sau thay đổi lớn | Chứng minh quy trình phục hồi thực sự chạy được. |

Điều chỉnh tần suất theo RPO, dung lượng, tốc độ thay đổi và khả năng restore. Không chỉ lưu bản mới nhất; cần retention đủ để quay về trước thời điểm corruption hoặc compromise được phát hiện.

### 3.3. Bảo vệ backup

- Mã hóa khi truyền và khi lưu.
- Lưu bản sao ngoài failure domain của LDAP server.
- Dùng immutable/object-lock retention nếu phù hợp chính sách chống ransomware.
- Phân quyền đọc/ghi backup tách biệt với quyền quản trị LDAP.
- Lưu checksum và manifest cho mỗi artifact.
- Kiểm tra dung lượng, tuổi backup, thời gian tạo và kết quả job.
- Không đặt private key, bind password hoặc secret dạng plaintext trong cùng thư mục backup không được bảo vệ.
- Thử khôi phục bằng tài khoản có quyền phù hợp, không chỉ kiểm tra file tồn tại.

Backup cần được bảo vệ như dữ liệu production vì LDIF có thể chứa thông tin cá nhân, group membership và thuộc tính xác thực.

## 4. Backup và restore OpenLDAP

OpenLDAP có thể dùng backend khác nhau, chẳng hạn MDB. Cách backup phải phù hợp backend và phiên bản. Với OpenLDAP, cần bảo vệ riêng **database directory** và **configuration database cn=config**.

### 4.1. Backup bằng slapcat

slapcat xuất database thành LDIF. Với back-mdb, tài liệu OpenLDAP cho phép chạy slapcat khi slapd đang hoạt động. Tuy nhiên, nếu ứng dụng thực hiện nhiều thao tác LDAP để hoàn tất một workflow, bản export có thể nằm giữa các thao tác đó và không nhất quán theo góc nhìn nghiệp vụ.

Ví dụ export cấu hình cn=config:

~~~bash
slapcat -F /etc/ldap/slapd.d -n 0 -l backup-cn-config.ldif
~~~

Export database theo suffix:

~~~bash
slapcat -F /etc/ldap/slapd.d \
  -b "dc=example,dc=org" \
  -l backup-directory.ldif
~~~

Tham số -n 0 chọn configuration database trong cách cài đặt OpenLDAP dùng cn=config. Tham số -b chọn database theo suffix. Xác minh số database và suffix trên máy mục tiêu trước khi chạy; không mặc định database đầu tiên luôn là dữ liệu người dùng.

Nếu cần application-consistent backup, hãy quiesce các workflow ghi hoặc đưa database vào chế độ read-only trong cửa sổ backup theo quy trình đã thử nghiệm. OpenLDAP Admin Guide lưu ý slapcat online có thể tạo ra trạng thái không nhất quán đối với ứng dụng đang thực hiện chuỗi nhiều thao tác.

### 4.2. Backup backend MDB

OpenLDAP mô tả hai phương pháp cơ bản:

- Sao chép database LMDB bằng công cụ mdb_copy, có thể thực hiện khi database đang hoạt động theo hướng dẫn của backend.
- Export LDIF bằng slapcat.

Không copy trực tiếp các file database đang được ghi bằng một lệnh filesystem thông thường rồi coi đó là backup hợp lệ. Nếu dùng snapshot storage, phải theo hướng dẫn nhất quán của backend, filesystem và nền tảng lưu trữ.

### 4.3. Manifest cho OpenLDAP

Mỗi backup nên ghi:

- Phiên bản OpenLDAP và hệ điều hành.
- Backend và đường dẫn database.
- Suffix của từng database.
- File export cn=config.
- Schema chuẩn và custom schema/OID.
- Module, overlay và dependency.
- ACL, limits, replication directives và server ID.
- TLS certificate, CA chain và vị trí private key (không đưa private key plaintext vào manifest).
- Thời điểm bắt đầu/kết thúc backup.
- Trạng thái read-only/quiesce.
- Checksum, kích thước và kết quả kiểm tra LDIF.

Không chỉ backup dữ liệu người dùng. Nếu thiếu cn=config hoặc custom schema, server có thể không khởi động được hoặc không hiểu các attribute đã lưu.

### 4.4. Restore OpenLDAP trong môi trường cô lập

Quy trình khái quát:

1. Tạo máy phục hồi riêng, chặn kết nối từ ứng dụng production và không cho replica cũ ghi vào node này.
2. Cài phiên bản OpenLDAP tương thích với backup và backend cần dùng.
3. Khôi phục cn=config, schema, module và cấu hình backend.
4. Dừng slapd trước khi nạp dữ liệu offline.
5. Nạp LDIF bằng slapadd vào database đúng suffix/backend.
6. Sửa owner/group và permission của file database theo service account thực tế.
7. Chạy kiểm tra cấu hình, kiểm tra index nếu cần, rồi mới khởi động slapd.
8. Xác minh Root DSE, naming context, bind, search, ACL và dữ liệu.
9. Kiểm tra replication trước khi cho node tham gia topology.

Ví dụ lệnh nạp data LDIF offline:

~~~bash
systemctl stop slapd

slapadd -F /etc/ldap/slapd.d \
  -b "dc=example,dc=org" \
  -l backup-directory.ldif

chown -R openldap:openldap /var/lib/ldap
~~~

Đây là ví dụ minh họa cho một layout Linux/OpenLDAP cụ thể. Tên service, user/group, config path, database path và cách chọn database phụ thuộc bản phân phối và cấu hình. Hãy dùng đúng đường dẫn đã ghi trong manifest.

Nếu phục hồi cn=config bằng slapadd, phải dùng đúng config directory và database số 0 theo tài liệu phiên bản đang chạy. Chỉ nạp config vào config directory sạch/đã chuẩn bị cho restore; không nạp chồng lên database cấu hình đang hoạt động. Không nạp data trước khi schema và backend tương ứng sẵn sàng.

### 4.5. Kiểm tra sau slapadd

- Xác minh tiến trình slapd khởi động và không báo lỗi schema/backend.
- Xác minh owner/group của database và config directory.
- Xác minh custom object class và attribute xuất hiện trong schema.
- Kiểm tra slapindex nếu quá trình restore/migration yêu cầu xây dựng lại index.
- Kiểm tra contextCSN/entryCSN và server ID nếu node sẽ tham gia replication.
- Không đưa node vào multi-provider topology với server ID trùng hoặc metadata replication không hợp lệ.

Đặc biệt với syncrepl/multi-provider, cần làm theo hướng dẫn về contextCSN, entryCSN, serverID và tùy chọn slapadd tương ứng. Không tự xóa replication metadata chỉ để server start được.

## 5. Backup và restore Active Directory

Active Directory Domain Services (AD DS) có cơ chế backup/restore riêng, gắn với domain controller, System State, SYSVOL, Directory Services Restore Mode (DSRM) và replication topology. Không dùng quy trình slapcat/slapadd của OpenLDAP cho Active Directory.

### 5.1. Backup domain controller

Với domain controller on-premises, backup thường bao gồm **System State** theo hướng dẫn Microsoft. Với domain controller chạy trên VM/cloud, cần theo hướng dẫn backup/restore được hỗ trợ cho nền tảng đó và bảo đảm các safeguard dành cho virtualized domain controller.

Backup plan phải ghi:

- Domain, forest và site.
- Domain controller nào được backup.
- Thời điểm backup và tuổi backup.
- System State/full server backup type.
- DSRM recovery credential được quản lý ở secret vault.
- DNS/SYSVOL dependency.
- FSMO role holder và Global Catalog topology.
- Quy trình forest recovery và metadata cleanup.

### 5.2. Nonauthoritative và authoritative restore

Hai chế độ này giải quyết tình huống khác nhau:

| Chế độ | Hành vi | Tình huống thường gặp |
| --- | --- | --- |
| Nonauthoritative restore | Domain controller được restore nhận lại thay đổi từ các domain controller còn khỏe qua replication. | Dựng lại một DC trong domain vẫn còn DC hoạt động. |
| Authoritative restore | Dữ liệu/object được chọn được đánh dấu để trở thành bản có thẩm quyền và replicate sang DC khác. | Khôi phục object bị xóa nhầm hoặc dữ liệu cần được phục hồi trên toàn domain/forest. |

Với domain controller bị mất trong một domain vẫn còn DC khỏe, Microsoft thường khuyến nghị dựng domain controller mới và để replication đồng bộ, thay vì restore backup cũ nếu không có lý do đặc biệt. Khi cần restore, phải chọn đúng mode và làm theo forest recovery guide.

### 5.3. DSRM và System State

Khôi phục AD DS trên domain controller thường yêu cầu khởi động vào Directory Services Restore Mode (DSRM). DSRM dùng credential quản trị riêng của domain controller.

Không coi một bản copy file NTDS database hoặc một VM snapshot tùy ý là phương án restore được hỗ trợ. Thực hiện theo hướng dẫn Microsoft cho phiên bản Windows Server và kiểu backup đang dùng.

### 5.4. Tombstone lifetime

Backup AD phải đủ mới so với tombstone lifetime được cấu hình trong forest/domain. Một bản backup quá cũ có thể khiến object đã bị xóa và tombstone đã hết hạn xuất hiện trở lại trên node phục hồi, gây sai lệch replication.

Không hard-code một số ngày mặc định trong runbook. Hãy đọc giá trị tombstoneLifetime thực tế của domain và đặt retention/alert backup sao cho phù hợp.

### 5.5. Forest recovery

Nếu không còn domain controller khỏe hoặc phải phục hồi toàn bộ forest, đây là quy trình forest recovery chuyên biệt. Nó có thể bao gồm:

- Chọn backup tin cậy và domain controller đầu tiên để phục hồi.
- Cô lập các DC chưa phục hồi để tránh replication không mong muốn.
- Phục hồi AD DS và SYSVOL theo đúng trình tự.
- Kiểm tra DNS, Global Catalog, FSMO role và replication.
- Làm sạch metadata của DC đã bị loại bỏ.
- Thay đổi các secret quan trọng theo forest recovery plan, bao gồm KRBTGT theo hướng dẫn Microsoft khi tình huống yêu cầu.
- Dựng lại các DC còn lại theo thứ tự được phê duyệt.

Không tự ứng biến forest recovery trong incident. Runbook phải trỏ tới hướng dẫn Microsoft tương ứng với Windows Server version và topology cụ thể.

## 6. Khôi phục không đồng nghĩa với failover

Hai thao tác thường bị nhầm:

- **Failover:** chuyển traffic sang một node/replica đã có dữ liệu đủ mới và đủ quyền phục vụ.
- **Restore:** nạp dữ liệu từ backup hoặc dựng lại node từ trạng thái đã lưu.

Nếu một replica khỏe, cập nhật gần nhất và được phép ghi, failover có thể đáp ứng RTO nhanh hơn. Nếu dữ liệu đã bị xóa nhầm và deletion được replicate, failover sang replica khác có thể chỉ đưa ứng dụng tới cùng trạng thái sai. Khi đó cần phục hồi dữ liệu hoặc authoritative recovery.

### 6.1. Bảng quyết định

| Tình huống | Hướng xử lý ưu tiên |
| --- | --- |
| Một node chết, replica khỏe và đã hội tụ | Fencing node hỏng, failover sang replica khỏe. |
| Một node chết, replica chưa hội tụ | Đánh giá mức mất dữ liệu; có thể restore hoặc đồng bộ lại từ provider. |
| Xóa nhầm entry đã replicate khắp topology | Phục hồi object từ backup/Recycle Bin hoặc quy trình authoritative restore tùy server. |
| Schema/config hỏng trên mọi node | Phục hồi schema/config tương thích trước, sau đó kiểm chứng data. |
| Ransomware/compromise đã lan sang replica | Cô lập topology, xác định backup sạch và thực hiện recovery plan. |
| Một DC mất nhưng domain còn DC khỏe | Cân nhắc dựng DC mới và replicate thay vì restore backup cũ. |

## 7. Kiểm chứng backup trước khi có sự cố

Một backup job báo thành công chỉ chứng minh công cụ hoàn thành thao tác theo cách nó hiểu. Nó chưa chứng minh file backup đầy đủ, không hỏng, schema tương thích, restore khởi động được, ACL/TLS hoạt động hoặc workflow nghiệp vụ không bị mất trạng thái.

### 7.1. Kiểm tra tính toàn vẹn

Với mỗi backup:

1. Tính checksum cho artifact.
2. Lưu kích thước, timestamp và server identity.
3. Kiểm tra LDIF có thể đọc/parse.
4. Kiểm tra backup bao gồm đúng suffix và cn=config/System State.
5. Xác minh bản sao đã được đẩy tới storage độc lập.
6. Đối chiếu backup manifest với danh mục schema/config mong đợi.
7. Ghi kết quả job vào monitoring.

Checksum chỉ xác minh file không đổi so với lúc tính checksum; nó không chứng minh nội dung backup đúng. Restore rehearsal vẫn cần thiết.

### 7.2. Restore rehearsal

Theo lịch, chọn một backup và khôi phục vào môi trường cô lập:

- Không cho ứng dụng production ghi vào môi trường test.
- Dùng hostname/DNS riêng.
- Dùng credential test hoặc credential được cấp quyền tối thiểu.
- Xác minh cấu hình, schema, dữ liệu và TLS.
- Chạy các truy vấn đại diện.
- Chạy integration smoke test từ một instance ứng dụng.
- Ghi thời gian restore thực tế để so sánh với RTO.

Restore rehearsal phải dùng cùng phiên bản server/backend hoặc ghi rõ khác biệt. Nếu production nâng cấp OpenLDAP/Windows Server, cần thử khôi phục với đúng phiên bản đích trước khi thay đổi production.

## 8. Kiểm chứng directory sau restore

Không cutover chỉ vì service process đang chạy. Cần một bộ kiểm tra nhiều lớp.

### 8.1. Kiểm tra server và Root DSE

Xác minh:

- TCP port/LDAPS port mở từ subnet ứng dụng.
- TLS handshake và certificate chain hợp lệ.
- Root DSE trả về namingContexts, supportedLDAPVersion, supportedControl và capability cần thiết.
- Naming context mong đợi có mặt.
- Server identity/endpoint đúng node đã phục hồi.
- Không có cảnh báo schema/backend nghiêm trọng trong log.

Có thể truy vấn Root DSE bằng ldapsearch để kiểm tra naming context và capability:

~~~bash
ldapsearch -x -H ldaps://ldap-vip.example.org:636 \
  -b "" -s base namingContexts supportedLDAPVersion supportedControl
~~~

Đây là truy vấn đọc Root DSE; dùng endpoint và CA trust phù hợp với môi trường. Không đưa bind password vào command line hoặc shell history.

### 8.2. Kiểm tra bind và ACL

Thực hiện bind bằng từng loại service account thực tế:

- Read-only account có thể đọc các attribute cần thiết.
- Provisioning account có thể tạo/update đúng OU được phép.
- Account không thể ghi vào vùng ngoài phạm vi.
- Password policy và bind mechanism hoạt động đúng.
- TLS certificate được client tin cậy.

Đừng kiểm tra chỉ bằng cn=admin hoặc root DN. Quyền quản trị có thể che giấu lỗi ACL mà ứng dụng production sẽ gặp.

### 8.3. Kiểm tra dữ liệu đại diện

Chọn tập entry đại diện:

- Người dùng đang hoạt động.
- Người dùng đã disabled.
- Group có ít và nhiều member.
- Entry có custom object class.
- Entry có binary attribute nếu ứng dụng sử dụng.
- Entry có DN/attribute chứa ký tự cần escaping.
- Entry ở OU/base DN mà repository đang truy vấn.

So sánh số lượng entry chỉ là kiểm tra sơ bộ. Hai directory có cùng số entry nhưng attribute hoặc membership khác nhau vẫn có thể sai.

### 8.4. Kiểm tra ứng dụng Spring Data LDAP

Ứng dụng cần xác minh:

- LdapContextSource kết nối đúng URL/base DN.
- Bind DN/secret đã được inject đúng.
- LdapTemplate lookup được entry test.
- Repository query trả đúng kết quả theo filter và base.
- ODM mapping @Entry, @Id, @Attribute không phát sinh converter/schema error.
- Connection pool không giữ context cũ hoặc credential hết hạn.
- Timeout và retry policy không biến outage thành tải retry không giới hạn.

Chạy smoke test bằng cùng cấu hình và quyền như production nhưng trên dữ liệu test/read-only khi có thể.

## 9. Kiểm tra replication sau phục hồi

Một node được restore có thể chạy bình thường nhưng chưa hội tụ với topology.

### 9.1. OpenLDAP syncrepl

OpenLDAP syncrepl là cơ chế replication theo LDAP Content Synchronization. Consumer giữ trạng thái đồng bộ và trao đổi synchronization cookie với provider. Khi nạp consumer từ backup LDIF, syncrepl có thể đồng bộ các thay đổi mới hơn từ provider.

Kiểm tra:

- Provider URL và search base đúng.
- Bind identity của replication account còn hợp lệ.
- Consumer có thể kết nối và đọc dữ liệu cần thiết.
- contextCSN và trạng thái sync tiến triển.
- Không có lỗi schema hoặc ACL làm một số entry không được replicate.
- Server ID/replication ID hợp lệ với topology, đặc biệt multi-provider.

Không xóa cookie/contextCSN hoặc tái sử dụng server ID tùy tiện. Thao tác đó có thể làm replication phải full refresh hoặc gây xung đột.

### 9.2. Active Directory replication

Sau khi restore/rebuild DC, kiểm tra:

- Replication partner và naming context.
- DNS/SRV record và site topology.
- SYSVOL/NETLOGON share.
- Global Catalog nếu DC có vai trò đó.
- FSMO roles nếu có thay đổi.
- Replication error và thời điểm last successful replication.
- Metadata cleanup cho DC đã loại bỏ.

Dùng công cụ/command Microsoft phù hợp với Windows Server version và forest recovery plan. Không chỉ kiểm tra một lệnh trả success; cần xác minh các naming context và partner thực tế.

### 9.3. Không đưa node vào phục vụ trước khi đạt điều kiện

Node chỉ được đưa vào load balancer khi:

- Dữ liệu cần thiết đã có.
- Replication state đạt ngưỡng chấp nhận.
- TLS, bind và ACL đúng.
- Không có nguy cơ split-brain hoặc hai writer ngoài ý muốn.
- Health check từ subnet ứng dụng đạt.

Nếu node chỉ được phép đọc trong giai đoạn catch-up, hãy cấu hình read-only hoặc không route write traffic cho tới khi được phê duyệt.

## 10. Đối soát dữ liệu với nguồn có thẩm quyền

Sau restore, dữ liệu LDAP có thể cũ hơn HR database, identity provider hoặc workflow database. Reconciliation so sánh trạng thái mong đợi với trạng thái thực tế và phân loại sai lệch trước khi sửa.

### 10.1. Xác định source of truth

Ví dụ:

| Thuộc tính | Nguồn có thẩm quyền | LDAP đóng vai trò |
| --- | --- | --- |
| employeeId | HR | Lưu khóa liên kết. |
| department | HR | Bản sao phục vụ search/access policy. |
| mail | HR hoặc mail service theo quy định | Bản sao cho directory lookup. |
| member/uniqueMember | Identity governance hoặc group owner | Quan hệ thành viên được đồng bộ. |
| Password/hash | Hệ thống xác thực được chỉ định | Chỉ lưu nếu kiến trúc và policy yêu cầu. |
| appProvisioningState | Workflow service | Trạng thái tích hợp, không tự thay thế HR state. |

Không dùng modifyTimestamp của LDAP để quyết định nguồn nào đúng nếu timestamp không đại diện cho quyền sở hữu dữ liệu. Một admin có thể sửa LDAP sau khi HR đã phát hành trạng thái chuẩn mới.

### 10.2. Dùng khóa định danh ổn định

DN có thể thay đổi khi rename/move entry. Đối soát nên dùng immutable identity key như employeeId hoặc external identity ID, sau đó tìm DN hiện tại để thao tác.

Nếu dùng entryUUID hoặc objectGUID, phải xác nhận thuộc tính tương ứng tồn tại trên server mục tiêu. Không giả định mọi LDAP vendor có cùng thuộc tính hoặc cùng semantics.

### 10.3. Phân loại sai lệch

| Loại sai lệch | Ví dụ | Hành động ban đầu |
| --- | --- | --- |
| Missing entry | HR có employee active nhưng LDAP không có | Kiểm tra OU/search scope và restore point, sau đó tạo lại nếu hợp lệ. |
| Orphan entry | LDAP có employee ID không còn trong HR | Kiểm tra trạng thái nghỉ việc, retention và ownership trước khi disable. |
| Attribute drift | Department/mail khác nguồn chuẩn | Tạo repair plan theo source of truth. |
| Membership drift | Group thiếu/thừa member | Kiểm tra managed group và nguồn cấp quyền. |
| Duplicate identity | Hai DN cùng employee ID | Dừng auto-repair; xử lý conflict thủ công. |
| Stale replica | Writer có entry, replica chưa thấy | Chờ hội tụ hoặc đọc authoritative endpoint. |
| Permission gap | Search không trả entry vì ACL | Sửa quyền/đường đọc; không kết luận entry bị mất. |
| Schema mismatch | Entry có attribute mà schema restore không nhận | Phục hồi schema/config tương thích trước khi sửa dữ liệu. |

### 10.4. Quy trình reconciliation an toàn

1. Chạy **audit-only** để tạo mismatch report.
2. Đối chiếu source of truth, endpoint, search base, ACL và replication state.
3. Phân loại từng mismatch và mức độ ảnh hưởng.
4. Sinh repair plan có operation ID và batch giới hạn.
5. Yêu cầu phê duyệt cho delete, disable hàng loạt hoặc thay đổi quyền.
6. Chạy repair idempotent cho các trường hợp rõ ràng.
7. Đọc lại entry và xác minh kết quả.
8. Ghi audit, số lượng thành công/thất bại và các trường hợp chuyển manual review.

Không tự động xóa entry chỉ vì không tìm thấy trong một search. Có thể search base sai, referral không được theo dõi, ACL không đủ quyền hoặc replica chưa hội tụ.

## 11. Ví dụ reconciliation theo employee ID

Một service có thể lấy danh sách employee active từ HR, tìm entry LDAP theo employeeId, rồi so sánh một số attribute do HR sở hữu.

Pseudocode:

~~~java
for (EmployeeRecord expected : hrClient.findActiveEmployees(batchCursor)) {
    List<Person> matches = personRepository.findByEmployeeId(
            expected.employeeId());

    if (matches.isEmpty()) {
        report.missing(expected.employeeId());
        continue;
    }

    if (matches.size() > 1) {
        report.duplicate(expected.employeeId(), matches.size());
        continue;
    }

    Person actual = matches.get(0);
    if (!normalize(actual.getDepartment())
            .equals(normalize(expected.department()))) {
        report.attributeDrift(
                expected.employeeId(),
                "department",
                actual.getDepartment(),
                expected.department());
    }
}
~~~

Đây là pseudocode minh họa; PersonRepository, EmployeeRecord, client HR và report model thuộc ứng dụng. Hãy chuẩn hóa giá trị theo matching rule/nghiệp vụ trước khi so sánh. Không so sánh DN hoặc chuỗi đa trị bằng thứ tự trả về của server.

### 11.1. Repair có điều kiện

Sau audit-only, nếu HR thực sự sở hữu department, repair có thể cập nhật attribute đó. Nhưng nếu department bị quản trị viên LDAP chỉnh sửa theo một quy trình được phê duyệt, phải giải quyết ownership trước.

Với group membership:

- Chỉ tự động sửa group do provisioning service quản lý.
- Không xóa membership thủ công hoặc do hệ thống khác cấp.
- Thêm/xóa từng giá trị có chủ đích thay vì replace toàn bộ tập nếu không sở hữu toàn bộ collection.
- Lưu operation ID để retry và audit.

## 12. Incident runbook

Runbook giúp người trực vận hành hành động theo thứ tự có thể kiểm chứng. Một incident nên có Incident Commander (IC), người điều phối kỹ thuật và người phụ trách nghiệp vụ/dữ liệu.

### 12.1. Giai đoạn 1 — Phát hiện và phân loại

Ghi nhận:

- Thời điểm bắt đầu và thời điểm phát hiện.
- Ứng dụng/service nào bị ảnh hưởng.
- Endpoint LDAP và node/site đang được sử dụng.
- Lỗi bind, search, modify hay TLS.
- Phạm vi người dùng/OU/naming context.
- Có thay đổi schema, ACL, certificate hoặc network gần đây không.
- Có dấu hiệu compromise hoặc thao tác xóa/sửa ngoài dự kiến không.

Phân loại lỗi trước khi chọn failover/restore. Nếu chỉ một app không kết nối được, kiểm tra DNS, secret, truststore và network từ đúng runtime trước khi kết luận LDAP server hỏng.

### 12.2. Giai đoạn 2 — Cô lập và bảo toàn bằng chứng

- Chỉ định IC và người có quyền quyết định restore/cutover.
- Lưu log, audit record, backup manifest và thời điểm thay đổi.
- Nếu nghi ngờ compromise, cô lập node/credential bị ảnh hưởng theo security incident plan.
- Ngăn node lỗi tiếp tục nhận write nếu có nguy cơ corruption.
- Không xóa log hoặc thay đổi nhiều cấu hình cùng lúc trước khi thu thập bằng chứng.
- Không đưa replica nghi ngờ bị compromise vào làm writer chỉ vì nó còn online.

### 12.3. Giai đoạn 3 — Chọn recovery path

Quyết định:

- Failover sang replica khỏe.
- Dựng node mới và đồng bộ từ provider.
- Restore toàn bộ database/config.
- Restore một phần object hoặc naming context theo khả năng server.
- Phục hồi forest AD.
- Chạy reconciliation từ HR/identity governance.

Ghi rõ lý do chọn recovery point, dữ liệu có thể mất và người phê duyệt. Nếu nghi ngờ deletion đã replicate, không failover sang replica khác mà chưa kiểm tra trạng thái dữ liệu.

### 12.4. Giai đoạn 4 — Phục hồi trong môi trường cô lập

- Dùng backup đã xác minh checksum.
- Phục hồi đúng server version/backend/schema.
- Giữ node ở trạng thái không nhận production traffic.
- Kiểm tra data, ACL, TLS, bind và các query đại diện.
- Kiểm tra replication metadata và khả năng catch-up.
- Ghi thời gian thực tế của từng bước.

### 12.5. Giai đoạn 5 — Cutover có kiểm soát

Trước cutover:

1. Xác định writer duy nhất hoặc topology multi-writer đã được kiểm soát.
2. Fencing node cũ nếu có nguy cơ hai writer cùng nhận update.
3. Cập nhật DNS/load balancer/config endpoint theo change plan.
4. Đóng hoặc làm mới connection pool/context cũ trong ứng dụng theo cơ chế triển khai.
5. Chạy readiness check từ subnet và service account thực tế.
6. Mở write traffic theo từng nhóm ứng dụng hoặc canary.

Không để node cũ tiếp tục nhận write sau khi node phục hồi đã trở thành writer nếu replication/topology chưa được cấu hình an toàn.

### 12.6. Giai đoạn 6 — Đối soát và theo dõi tăng cường

- Chạy audit-only reconciliation.
- So sánh count, key set và attribute quan trọng.
- Kiểm tra các workflow provisioning pending.
- Xác minh group membership và quyền truy cập.
- Theo dõi bind/search/modify error rate, latency và replication lag.
- Chạy repair theo batch đã được phê duyệt.
- Chỉ kết thúc incident khi các tiêu chí phục hồi đã đạt.

## 13. Tích hợp Spring Data LDAP trong môi trường phục hồi

Ứng dụng cần cấu hình endpoint, base DN, bind credential và TLS theo môi trường. Secret phải được inject từ secret manager hoặc cơ chế quản lý cấu hình an toàn.

### 13.1. Cấu hình endpoint

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  ldap:
    urls: ldaps://ldap-vip.example.org:636
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}
~~~

Các placeholder phải được inject từ secret manager hoặc environment của deployment. Không commit bind password vào file cấu hình.

Ví dụ dùng một virtual IP/load balancer làm endpoint ổn định. Nếu triển khai nhiều URL LDAP trực tiếp, hãy xác minh behavior failover của JNDI provider, Spring LDAP version và connection pool trong môi trường thực tế; không giả định chỉ khai báo nhiều URL đã tạo health-aware failover hoặc bảo đảm đọc/ghi nhất quán.

Với phiên bản Spring Boot hỗ trợ SSL bundles, có thể cấu hình trust material bằng thuộc tính spring.ldap.ssl.bundle và trỏ tới bundle đã khai báo. Nếu dùng phiên bản cũ hơn, có thể quản lý truststore qua JVM hoặc cấu hình SSL trên ContextSource riêng. SSL bundle của auto-configuration không tự áp dụng cho ContextSource do ứng dụng tự tạo. Thuộc tính này dành cho LDAPS; StartTLS cần cấu hình DirContextAuthenticationStrategy tương ứng.

### 13.2. Connection pool và context cũ

Sau failover hoặc rotate credential:

- Context đang mở có thể vẫn trỏ tới endpoint cũ.
- Connection pool có thể giữ connection chết hoặc connection đã bind bằng credential cũ.
- DNS cache có thể giữ địa chỉ cũ.
- TLS truststore/certificate có thể chưa được reload trong JVM.

Runbook cần chỉ rõ cách refresh/restart instance ứng dụng hoặc recreate ContextSource/pool. Tránh xóa connection pool hoặc restart toàn bộ fleet cùng lúc nếu có thể triển khai theo từng nhóm.

### 13.3. Readiness và liveness

Phân biệt:

- **Liveness:** tiến trình ứng dụng còn hoạt động; không nên restart liên tục chỉ vì LDAP tạm thời unavailable.
- **Readiness:** ứng dụng có thể nhận traffic yêu cầu LDAP hay chưa; có thể phản ánh dependency bắt buộc theo chính sách.

Health check nên:

- Dùng service account phù hợp.
- Thực hiện bind và một lookup/search nhỏ trên base DN cần thiết.
- Có timeout ngắn và không tạo write side effect.
- Không trả bind DN, password, full exception hoặc topology nhạy cảm ra endpoint công khai.
- Có trạng thái degraded nếu tính năng phụ thuộc LDAP bị hạn chế nhưng ứng dụng vẫn phục vụ phần không cần directory.

## 14. Kiểm tra readiness bằng Spring

Một health indicator có thể kiểm tra lookup tới một entry ổn định hoặc search base health riêng. Ví dụ khái niệm:

Ví dụ yêu cầu Spring Boot Actuator có trên classpath. Chỉ expose endpoint health theo chính sách bảo mật của deployment.

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.stereotype.Component;

@Component
public class DirectoryHealthIndicator implements HealthIndicator {
    private final LdapTemplate ldapTemplate;

    public DirectoryHealthIndicator(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    @Override
    public Health health() {
        try {
            ldapTemplate.lookup("ou=people", ctx -> Boolean.TRUE);
            return Health.up().build();
        } catch (Exception ex) {
            return Health.down()
                    .withDetail("dependency", "ldap")
                    .withDetail("reason", "directory lookup failed")
                    .build();
        }
    }
}
~~~

Ví dụ giả định base DN của LdapContextSource là dc=example,dc=org và entry ou=people tồn tại, được service account đọc. Trong ứng dụng thực tế, dùng một health entry chuyên dụng và timeout phù hợp; không đưa exception message hoặc thông tin xác thực ra response.

Health indicator này chỉ xác minh một lookup tại thời điểm kiểm tra. Nó không chứng minh mọi repository query, mọi replica hoặc write permission đều hoạt động. Kiểm tra sâu hơn nên nằm trong deployment verification/synthetic test riêng.

## 15. Kiểm chứng sau cutover

Sau khi chuyển traffic, chạy kiểm tra theo thứ tự từ ít rủi ro tới có tác động:

| Bước | Kiểm tra | Điều kiện đạt |
| --- | --- | --- |
| 1 | DNS/TLS/connectivity | Client tới đúng endpoint và certificate hợp lệ. |
| 2 | Bind read-only | Service account đọc được base DN cần thiết. |
| 3 | Lookup mẫu | Tìm thấy entry ổn định. |
| 4 | Repository search | Query thực tế trả đúng số lượng và attribute. |
| 5 | ACL boundary | Không đọc/ghi vượt quyền dự kiến. |
| 6 | Replication | Node đạt trạng thái hội tụ theo topology. |
| 7 | Synthetic write trên fixture riêng | Add/modify/delete test entry thành công nếu được phép. |
| 8 | Reconciliation audit | Không có mismatch nghiêm trọng chưa giải thích. |
| 9 | Canary application traffic | Error rate và latency trong ngưỡng. |
| 10 | Mở traffic đầy đủ | IC và owner nghiệp vụ phê duyệt. |

Không chạy synthetic write lên entry người dùng thật. Dùng OU/entry test được bảo vệ và cleanup có kiểm soát.

## 16. Các kịch bản sự cố và hướng xử lý

| Kịch bản | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| LDAP service down | Connection refused/timeout trên nhiều client | Kiểm tra node/network; failover nếu replica khỏe. |
| TLS certificate hết hạn | Handshake/certificate validation lỗi | Xác minh chain, rotate cert, reload truststore/context. |
| Bind account hết hạn/disabled | Invalid credentials hoặc account locked | Kiểm tra secret/identity policy, rotate theo quy trình. |
| Search trả thiếu dữ liệu | Không thấy entry hoặc attribute | Kiểm tra ACL, base DN, scope, referral và replica. |
| Schema mismatch sau deploy | objectClassViolation/undefinedAttributeType | Khôi phục schema/config tương thích hoặc rollback schema migration. |
| Xóa nhầm entry | Entry mất trên nhiều replica | Chọn object recovery/authoritative restore phù hợp; reconciliation. |
| Restore OpenLDAP lỗi permission | slapd không đọc được database | Sửa owner/group/mode theo service account; kiểm tra path. |
| AD restore lỗi replication | DC không hội tụ hoặc SYSVOL lỗi | Theo forest recovery guide, DSRM và replication validation. |
| Replica lag | Writer thấy update, reader không thấy | Chờ hội tụ, đọc authoritative node, tránh repair nhầm. |
| Credential compromise | Bind bất thường, quyền bị lạm dụng | Cô lập, preserve evidence, rotate secret/cert và restore sạch khi cần. |
| Workflow dở dang | LDAP có entry nhưng thiếu group/account ngoài | Đọc workflow journal, chạy retry/compensation/reconciliation. |

## 17. Dữ liệu và workflow sau khi phục hồi

Restore directory không tự phục hồi trạng thái của database HR, identity provider hoặc message broker. Sau restore, cần nối lại các hệ thống bằng workflow state và nguồn dữ liệu có thẩm quyền.

### 17.1. Phân loại workflow theo checkpoint

| Trạng thái trước sự cố | Xử lý sau restore |
| --- | --- |
| Chưa gửi thao tác LDAP | Tiếp tục từ bước LDAP sau khi xác minh source of truth. |
| LDAP đã ghi, workflow state chưa cập nhật | Tra cứu theo business key/operation ID trước khi retry. |
| LDAP đã ghi, identity provider chưa hoàn tất | Tiếp tục provisioning hoặc compensation theo policy. |
| Outbox event chưa publish | Publisher gửi lại; consumer phải deduplicate. |
| Event đã publish, consumer chưa xử lý | Broker redelivery hoặc replay theo event ID. |
| Compensation đang dở | Xác minh side effect thực tế rồi tiếp tục compensation. |

Không replay toàn bộ message hoặc workflow một cách mù quáng. Mỗi bước phải idempotent hoặc có cơ chế xác minh trạng thái.

### 17.2. Xác định dữ liệu nào được phục hồi từ backup và dữ liệu nào được tái tạo

Một số dữ liệu có thể được tạo lại từ nguồn có thẩm quyền:

- department, title, mail từ HR hoặc mail service.
- Group membership được tính từ identity governance.
- Cache và projection có thể được rebuild.

Một số dữ liệu cần được phục hồi chính xác:

- Identity key và operational attribute.
- Custom schema/config.
- Security ACL và password policy.
- Audit history theo retention requirement.

Không tái tạo password/hash hoặc credential bằng cách copy tùy tiện giữa hệ thống. Tuân thủ chính sách xác thực và rotation.

## 18. Bảo mật trong quá trình phục hồi

Recovery environment thường có quyền cao hơn runtime bình thường. Cần kiểm soát:

- Dùng tài khoản restore riêng, chỉ cấp trong thời gian thực hiện.
- Tách quyền backup operator, LDAP administrator và application service account.
- Bảo vệ DSRM credential, root DN secret, replication credential và private key.
- Không mở LDAP admin endpoint ra mạng ứng dụng trong quá trình restore.
- Mã hóa backup và giới hạn quyền tải xuống.
- Thu hồi quyền tạm thời sau khi kết thúc.
- Rotate credential nếu có dấu hiệu compromise hoặc secret bị lộ trong incident.
- Ghi lại ai phê duyệt restore, ai thực hiện và thời điểm từng bước.

Nếu sự cố có dấu hiệu compromise, không đưa backup chưa xác minh nguồn gốc hoặc replica đã bị ảnh hưởng trở lại production chỉ để đạt RTO.

## 19. Monitoring và bằng chứng vận hành

Theo dõi các metric:

| Metric | Mục đích |
| --- | --- |
| Backup age | Phát hiện backup quá cũ so với RPO. |
| Backup duration/size | Phát hiện backup bất thường hoặc thiếu dữ liệu. |
| Restore rehearsal duration | So sánh với RTO. |
| Checksum/restore validation result | Xác minh integrity và khả năng phục hồi. |
| LDAP bind/search/modify error rate | Phát hiện lỗi dịch vụ sau cutover. |
| TLS certificate expiry | Cảnh báo trước khi certificate hết hạn. |
| Replication lag/state | Theo dõi hội tụ giữa node. |
| Entry count/key reconciliation | Phát hiện thiếu/trùng dữ liệu. |
| Workflow pending age | Phát hiện provisioning bị dở dang. |
| Outbox backlog | Phát hiện event chưa được phát. |

Lưu recovery evidence:

- Backup ID, checksum và manifest.
- Recovery point được chọn và lý do.
- Server/version/backend được restore.
- Thời điểm bắt đầu/kết thúc từng bước.
- Kết quả Root DSE, TLS, bind, ACL và sample queries.
- Replication status trước/sau cutover.
- Mismatch report và repair operation ID.
- Người phê duyệt và người thực hiện.
- Tiêu chí nào đã đạt/chưa đạt khi đóng incident.

## 20. Lỗi thường gặp khi phục hồi

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Xem replication là backup | Xóa nhầm hoặc corruption được replicate | Duy trì backup độc lập và restore rehearsal. |
| Chỉ backup user data | Thiếu schema/config, server không hiểu entry | Backup cn=config, schema, module, ACL và TLS material. |
| Copy trực tiếp file database đang ghi | Backup có thể không nhất quán/hỏng | Dùng công cụ backend hỗ trợ hoặc export theo hướng dẫn. |
| Chạy slapcat online khi workflow nhiều bước đang ghi | Snapshot hợp lệ ở LDAP nhưng lệch trạng thái nghiệp vụ | Quiesce writes/read-only hoặc reconcile từ workflow journal. |
| Restore AD như một LDAP server thông thường | Replication/USN/SYSVOL/forest state sai | Dùng System State, DSRM và Microsoft forest recovery guidance. |
| Restore DC backup quá cũ | Tombstone/replication inconsistency | Kiểm tra tombstone lifetime cấu hình và tuổi backup. |
| Đưa node restore vào load balancer ngay | Client đọc dữ liệu chưa hội tụ | Validate data, ACL, TLS và replication trước cutover. |
| Để node cũ và node restore cùng nhận write | Split-brain hoặc xung đột dữ liệu | Fencing và xác định writer/topology. |
| Chỉ kiểm tra process đang chạy | Ứng dụng vẫn có thể bind/search sai | Chạy smoke test bằng service account và query thật. |
| Auto-delete entry không có trong HR | Xóa nhầm do ACL, scope hoặc replica lag | Audit-only, ownership và manual review. |
| Replay mọi workflow sau restore | Tạo trùng account/membership hoặc xóa nhầm | Dùng checkpoint, operation ID và idempotency. |

## 21. Bài tập thực hành

**Bài 1.** Một OpenLDAP backup chỉ có LDIF dữ liệu người dùng, không có cn=config và custom schema. Rủi ro là gì?

**Đáp án:** Server có thể thiếu backend, suffix, module, ACL hoặc schema cần thiết để đọc/ghi entry. Cần backup và restore cấu hình/schema tương thích cùng dữ liệu.

**Bài 2.** Có thể chạy slapcat khi slapd đang hoạt động không?

**Đáp án:** Với back-mdb, OpenLDAP cho phép chạy slapcat online. Tuy nhiên, nếu provisioning workflow thực hiện nhiều LDAP operation, snapshot có thể nằm giữa các bước và không nhất quán theo nghiệp vụ. Cần quiesce writes hoặc reconciliation.

**Bài 3.** Một domain controller bị mất nhưng domain vẫn còn DC khỏe. Có nhất thiết restore System State không?

**Đáp án:** Không. Có thể dựng domain controller mới và để replication đồng bộ theo hướng dẫn Microsoft; chọn restore khi recovery scenario yêu cầu.

**Bài 4.** Khi nào dùng authoritative restore trong Active Directory?

**Đáp án:** Khi cần làm cho object/dữ liệu đã phục hồi trở thành bản có thẩm quyền, ví dụ khôi phục object bị xóa nhầm để thay đổi được replicate. Nonauthoritative restore thường dùng khi rebuild DC trong domain còn khỏe.

**Bài 5.** Một backup AD cũ hơn tombstone lifetime có thể gây điều gì?

**Đáp án:** Object đã xóa và tombstone hết hạn có thể xuất hiện trở lại trên DC được restore và tạo replication inconsistency. Phải kiểm tra giá trị tombstone lifetime thực tế của domain.

**Bài 6.** Vì sao không nên failover sang replica khác khi phát hiện xóa nhầm entry?

**Đáp án:** Deletion có thể đã replicate sang mọi replica. Cần xác minh dữ liệu trên topology và chọn object recovery/authoritative restore phù hợp.

**Bài 7.** Sau restore, service account admin bind được nhưng ứng dụng không đọc được mail. Điều gì cần kiểm tra?

**Đáp án:** ACL, quyền đọc attribute, search base/scope, referral, endpoint/replica và mapping của ứng dụng bằng đúng bind account production.

**Bài 8.** Reconciliation tìm thấy LDAP thiếu entry nhưng read replica chưa hội tụ. Có nên tạo lại entry ngay không?

**Đáp án:** Không. Xác minh writer, ACL, search scope và replication lag trước; chỉ repair sau khi xác nhận dữ liệu thực sự thiếu.

## 22. Checklist triển khai và phục hồi

### Trước khi đưa production vào vận hành

- [ ] RPO/RTO được nghiệp vụ phê duyệt.
- [ ] Backup bao gồm data, schema, config, TLS, replication và workflow state cần thiết.
- [ ] Backup được mã hóa, checksum và lưu ngoài failure domain.
- [ ] Có manifest và retention policy.
- [ ] Có runbook OpenLDAP hoặc AD đúng vendor/version.
- [ ] Có restore rehearsal với kết quả đo được.
- [ ] Có nguồn dữ liệu có thẩm quyền và quy tắc reconciliation.
- [ ] Có owner và escalation path cho incident.

### Khi phục hồi

- [ ] Phân loại failover, rebuild, object restore hay disaster recovery.
- [ ] Cô lập node lỗi và bảo toàn evidence.
- [ ] Xác minh backup/recovery point.
- [ ] Restore trong môi trường cô lập.
- [ ] Kiểm tra schema, config, TLS, bind, ACL và dữ liệu.
- [ ] Kiểm tra replication và xác định writer.
- [ ] Fencing node cũ trước cutover khi cần.
- [ ] Chạy canary và readiness check.
- [ ] Chạy reconciliation audit-only trước auto-repair.
- [ ] Xác minh workflow pending, outbox và consumer state.
- [ ] Ghi recovery evidence và thông báo hoàn tất.

### Sau khi đóng incident

- [ ] Thu hồi quyền restore tạm thời.
- [ ] Rotate credential/certificate nếu cần.
- [ ] Kiểm tra backup mới sau phục hồi.
- [ ] Cập nhật manifest và runbook theo thay đổi thực tế.
- [ ] Ghi post-incident review, nguyên nhân gốc và action item.
- [ ] Lên lịch restore rehearsal tiếp theo.

## 23. Ghi nhớ

- RPO xác định mức dữ liệu có thể mất; RTO xác định thời gian cần khôi phục dịch vụ.
- Replication hỗ trợ availability nhưng không thay thế backup độc lập.
- Backup cần bảo vệ cả directory data, schema, cn=config, ACL, TLS, replication và workflow state.
- Với OpenLDAP, phân biệt export cn=config và data suffix; slapcat online có thể không nhất quán theo workflow nhiều thao tác.
- Với Active Directory, dùng System State/DSRM và chọn authoritative hay nonauthoritative restore theo recovery scenario.
- Kiểm tra tombstone lifetime thực tế khi đánh giá tuổi backup AD.
- Không đưa node phục hồi vào traffic trước khi kiểm tra TLS, bind, ACL, dữ liệu và replication.
- Reconciliation phải dựa trên source of truth, identity key ổn định, ownership và audit trail.
- Spring Data LDAP cần làm mới endpoint/context/pool sau failover theo behavior đã kiểm thử.
- Incident chỉ được đóng khi tiêu chí phục hồi, reconciliation và bằng chứng vận hành đã đạt.

## Tài liệu tham khảo

- [OpenLDAP Software 2.5 Administrator's Guide — Maintenance and Directory Backups](https://www.openldap.org/doc/admin25/OpenLDAP-Admin-Guide.pdf): slapcat, mdb_copy, backup LDIF, consistency và maintenance.
- [OpenLDAP Administrator's Guide — Replication](https://www.openldap.org/doc/admin25/OpenLDAP-Admin-Guide.pdf): phần replication, syncrepl, provider/consumer, synchronization cookie và khởi tạo replica từ backup.
- [OpenLDAP Administrator's Guide — Recovering from a broken configuration](https://www.openldap.org/doc/admin25/OpenLDAP-Admin-Guide.pdf): export/restore cn=config, slapadd và slaptest.
- [Microsoft Learn — Back up and restore Active Directory domain controllers](https://learn.microsoft.com/en-us/azure/backup/active-directory-backup-restore): System State, authoritative/nonauthoritative restore, DSRM và tombstone lifetime.
- [Microsoft Learn — Active Directory Forest Recovery procedures](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/forest-recovery-guide/ad-forest-recovery-procedures): forest recovery, SYSVOL, FSMO, DNS, metadata cleanup và replication verification.
- [Microsoft Learn — Restoring an Active Directory server](https://learn.microsoft.com/en-us/windows/win32/ad/restoring-an-active-directory-server): quy trình restore AD DS trong DSRM.
- [Spring LDAP — Reference Documentation](https://docs.spring.io/spring-ldap/reference/): LdapContextSource, LdapTemplate, repository và cấu hình kết nối.
- [Spring Boot — LDAP](https://docs.spring.io/spring-boot/reference/data/nosql.html): cấu hình LDAP trong ứng dụng Spring Boot.

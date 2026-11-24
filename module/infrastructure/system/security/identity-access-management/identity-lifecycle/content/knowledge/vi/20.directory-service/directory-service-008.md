# Directory availability trong IAM: duy trì dịch vụ thư mục sẵn sàng và trạng thái danh tính đáng tin cậy

**Directory availability (tính sẵn sàng của dịch vụ thư mục)** là khả năng một **directory service** tiếp tục phục vụ những thao tác cần thiết của hệ thống danh tính — chẳng hạn tìm kiếm đối tượng, tra cứu thuộc tính, xác minh thông tin tài khoản, truy xuất nhóm hoặc ghi nhận thay đổi — **đúng thời điểm, đúng phạm vi và với kết quả đủ đáng tin cậy**. Trong doanh nghiệp, thư mục có thể là **Active Directory Domain Services (AD DS)**, một dịch vụ thư mục dùng **LDAP**, hoặc thành phần thư mục được quản lý của nền tảng danh tính.

Tính sẵn sàng không chỉ được chứng minh bằng việc một máy chủ mở cổng LDAP hay có phản hồi mạng. Người dùng có thể không đăng nhập được nếu **DNS không tìm thấy Domain Controller (DC)**, **Kerberos/KDC không hoạt động**, **chứng thư TLS hết hạn**, **replica thiếu dữ liệu mới**, hoặc **IdP không lấy được thuộc tính cần cho chính sách**. Ngược lại, một máy chủ thư mục đang hoạt động vẫn có thể trả về **vai trò cũ của nhân viên đã đổi bộ phận** hoặc **trạng thái còn active của người đã nghỉ** nếu đồng bộ bị chậm.

Bài học thuộc chương **Directory service**, mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE** về quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: xác minh người dùng, tạo account, cấp quyền, rà soát và thu hồi khi thay đổi vai trò hoặc quan hệ làm việc. Một directory service sẵn sàng, có kiểm soát về **tính mới của dữ liệu**, giúp **IdP/SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán** vận hành đúng. Khi thiết kế HA/DR, mục tiêu không chỉ là “không ngừng đăng nhập” mà còn là **không duy trì quyền truy cập tồn dư trái chính sách**.

**Thông điệp cốt lõi:** Directory availability phải được đánh giá trên cả **khả năng truy cập dịch vụ, chất lượng dữ liệu, độ mới của thay đổi và hiệu quả thực thi chính sách IAM**. Một hệ thống “còn lên” nhưng không nhận được sự kiện Leaver hoặc trả quyền cũ có thể tạo rủi ro bảo mật nghiêm trọng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích directory availability và phân biệt **uptime, khả năng phục vụ thao tác, độ trễ, tính nhất quán và độ mới dữ liệu**.
2. Xác định các phụ thuộc như **LDAP/LDAPS, DNS, Kerberos, IdP/SSO, mạng, TLS, cơ sở dữ liệu và đồng bộ replica**.
3. Thiết kế mô hình **nhiều nút, nhiều site, phát hiện lỗi và chuyển hướng kết nối** phù hợp với directory service.
4. Đánh giá vì sao **replication lag**, cache và sự kiện đến sai thứ tự có thể khiến Joiner/Mover/Leaver không đạt trạng thái mong muốn.
5. Xác định những thao tác được phép tiếp tục ở **degraded mode** mà không vô tình **fail-open** cho truy cập nhạy cảm.
6. Xây dựng kế hoạch giám sát dựa trên **SLI/SLO, synthetic probe, readback và tình trạng đồng bộ**.
7. Mô tả quy trình **backup, disaster recovery, thử nghiệm failover và khôi phục tính nhất quán**.
8. Liên hệ các quyết định availability với **least privilege, MFA, RBAC/ABAC, SCIM, tài khoản dịch vụ và bằng chứng kiểm toán**.

## 2. Directory service cung cấp những chức năng nào?

**Directory service** thường là kho thông tin có cấu trúc và giao diện truy cập cho **user, group, computer, service account và các thuộc tính liên quan**. Nền tảng có thể dùng những giao thức/cơ chế khác nhau:

| Chức năng | Ví dụ | Tác động khi không sẵn sàng |
|---|---|---|
| **Tra cứu user/đối tượng** | Tìm account theo ID, DN hoặc thuộc tính | Ứng dụng không ánh xạ được danh tính |
| **Tra cứu group/role-related attributes** | Lấy membership hoặc thông tin phòng ban | Policy không đủ dữ liệu hoặc dùng dữ liệu cũ |
| **Authentication dependency** | LDAP bind phù hợp hoặc AD/Kerberos | Đăng nhập có thể lỗi, dù ứng dụng vẫn mở |
| **Ghi thay đổi** | Tạo user, disable account, cập nhật group | Sự kiện Joiner/Mover/Leaver bị chậm hoặc lỗi |
| **Replication** | Đồng bộ đối tượng giữa các DC/replica | Các nút trả dữ liệu khác nhau |
| **Discovery và kết nối** | DNS SRV, tên dịch vụ, TLS endpoint | Client không tìm được máy chủ khỏe |
| **Dữ liệu cho IdP/IAM** | Đồng bộ user/group từ directory sang IdP | Claim hoặc trạng thái đăng nhập có thể lỗi thời |
| **Kiểm kê/đối soát** | Đọc lại trạng thái account và quyền | Không xác minh được việc cấp/thu hồi đã hoàn tất |

**LDAP** là giao thức truy cập dữ liệu thư mục; **LDAP server** không nhất thiết có kiến trúc giống AD DS. Với **AD DS**, nhiều thao tác danh tính còn phụ thuộc **DNS, Kerberos/KDC, Global Catalog (GC), các DC và vai trò điều phối đặc thù**. Một nền tảng cloud directory có mô hình HA khác và có thể không công khai các DC/replica bên dưới cho người dùng quản trị.

**Không đồng nhất:** “Directory online” ≠ “IdP hoạt động” ≠ “SSO đăng nhập được” ≠ “SCIM đã đồng bộ xong” ≠ “người dùng có đúng entitlement”.

## 3. Nhiều chiều của tính sẵn sàng

Một hệ thống thư mục có thể đáp ứng một chiều nhưng thất bại ở chiều khác.

| Chiều | Câu hỏi cần trả lời | Ví dụ lỗi |
|---|---|---|
| **Reachability** | Client có tới đúng directory endpoint không? | Mạng phân đoạn, firewall, DNS sai |
| **Service readiness** | Endpoint có thực hiện được thao tác LDAP/Kerberos cần thiết không? | Mở TCP nhưng bind/query lỗi |
| **Authentication availability** | Người dùng/ứng dụng có xác thực được theo policy không? | KDC lỗi, TLS trust sai |
| **Read availability** | Query user/group trả kết quả phù hợp không? | Replica quá tải hoặc lỗi index |
| **Write availability** | Có thể tạo/disable user, sửa group ở nút có quyền ghi không? | Chỉ còn read-only replica |
| **Consistency/freshness** | Kết quả đã bao gồm thay đổi cần thiết ở thời điểm hiện tại chưa? | Leaver đã disable tại DC A nhưng DC B chưa nhận |
| **Authorization correctness** | Quyết định RBAC/ABAC có dùng trạng thái hợp lệ không? | Cache role cũ vẫn cho quyền |
| **Recoverability** | Có thể khôi phục dữ liệu và dịch vụ trong phạm vi cam kết không? | Backup hỏng hoặc runbook chưa thử |

### Ví dụ khác nhau giữa uptime và readiness

Một DC trả TCP connect thành công tới cổng LDAPS; dashboard hạ tầng hiển thị “healthy”. Nhưng truy vấn group trên DC đó timeout vì quá tải và **dịch vụ cần thiết đối với SSO không hoạt động được**. Từ góc nhìn người dùng, directory **chưa sẵn sàng**, dù host vẫn online.

Một tình huống khác: user mới đã được tạo ở DC A nhưng ứng dụng query DC B chưa thấy. **Độ sẵn sàng đọc có thể vẫn cao, nhưng độ mới dữ liệu không đáp ứng mục tiêu Joiner**. Đối với Leaver, dữ liệu cũ có thể giữ nguyên đường truy cập quá hạn.

## 4. Kiến trúc tham chiếu: các lớp phụ thuộc

~~~mermaid
flowchart TD
    H["HR / VMS<br/>Nguồn biến cố JML"] --> I["IAM / IGA<br/>Identity + desired entitlements"]
    I --> W["Provisioning<br/>LDAP / API / SCIM"]
    W --> D1["Directory node / DC A<br/>Site 1"]
    W --> D2["Directory node / DC B<br/>Site 2"]
    D1 <-->|"Replication và trạng thái"| D2
    N["DNS / service discovery"] --> D1
    N --> D2
    D1 --> P["IdP / Kerberos / SSO"]
    D2 --> P
    P --> A["Ứng dụng / API<br/>RBAC + ABAC"]
    I --> A
    A --> O["Audit, readback và<br/>reconciliation"]
    D1 --> O
    D2 --> O
    O --> I
~~~

Đây là **mô hình khái niệm**. Một số dịch vụ directory dùng nhiều writer; một số dùng leader/replica, đồng bộ bất đồng bộ, managed control plane hoặc cơ chế khác. **Không áp một topology cụ thể cho mọi sản phẩm**. Thiết kế phải biết rõ **đọc/ghi tại nút nào, cơ chế nhất quán, quyền của replica, cách client failover và cách khôi phục**.

### Các câu hỏi kiến trúc trước khi triển khai

- Những ứng dụng nào cần **LDAP bind**, những ứng dụng dùng **Kerberos/SSO** và những ứng dụng chỉ nhận account qua **SCIM**?
- Nếu site A mất mạng, site B có thể xử lý **đọc, xác thực và ghi** không, hay chỉ một phần?
- Hệ thống cần Global Catalog/role đặc thù nào cho nghiệp vụ? Có phụ thuộc địa điểm không?
- Một thay đổi Leaver khi nào được xem là **đã có hiệu lực trên các điểm kiểm tra quyền**?
- Khi không truy cập được directory, IdP/ứng dụng xử lý thế nào đối với **phiên đã có, user mới, quyền admin và refresh token**?
- Cách quan sát trạng thái **thực tế** ở các DC, IdP và application target có nhất quán không?

## 5. Đường truy cập không chỉ phụ thuộc LDAP

Với AD DS, một luồng đăng nhập có thể liên quan **DNS service discovery, DC locator, Kerberos KDC, time synchronization, trust và LDAP/GC**. Việc kiểm tra một cổng mạng đơn lẻ không phản ánh toàn bộ.

| Phụ thuộc | Vai trò | Khi lỗi có thể thấy gì? |
|---|---|---|
| **DNS A/AAAA/SRV** | Tìm DC/LDAP/Kerberos phù hợp site/domain | Không tìm được DC, chuyển site sai |
| **Kết nối mạng** | Đường truyền giữa client, DC, IdP và site | Timeout, mất một phần dịch vụ |
| **LDAP/LDAPS** | Tra cứu và cập nhật thư mục theo policy | Bind/search/write lỗi |
| **Kerberos/KDC** | Phát hành và kiểm tra cơ chế ticket trong AD/realm tương ứng | Không lấy được ticket hoặc lỗi xác thực |
| **Đồng hồ hệ thống** | Giới hạn skew và thời gian hiệu lực ticket/chứng thư | Lỗi Kerberos hoặc TLS do lệch thời gian |
| **TLS/certificate chain** | Bảo vệ kết nối thư mục và xác minh server | Client từ chối LDAPS/StartTLS |
| **GC và dữ liệu forest** | Hỗ trợ một số truy vấn/đăng nhập nhóm trong AD | Tra cứu hoặc kiểm tra thành viên đặc thù bị ảnh hưởng |
| **Replication/DB** | Đảm bảo dữ liệu cần thiết đến các nút | Khác biệt account/group giữa các replica |
| **Service credential** | Client ứng dụng kết nối và truy vấn directory | Bind fail khi secret/chứng thư hết hạn |
| **IdP/SSO/ứng dụng** | Tiêu thụ thông tin danh tính và thực thi truy cập | Directory khỏe nhưng login/authorization vẫn lỗi |

### 5.1. DNS và site awareness

Trong AD, client và dịch vụ có thể dùng **DNS SRV records** cùng cơ chế chọn DC/site. Nếu bản ghi SRV lỗi thời hoặc DNS không phân giải được, client có thể kết nối tới một DC ở xa, tăng độ trễ hoặc dùng nút không phù hợp.

**Không tạo một DNS alias đơn giản rồi coi là đủ HA** nếu client thật sự sử dụng cơ chế discovery khác. Cần kiểm tra hành vi resolver, TTL, cache, phân vùng mạng và loại truy vấn của từng client.

### 5.2. LDAP bind, TLS và Kerberos

LDAP được dùng để đọc/cập nhật directory và có cơ chế bind. Trong AD, nhiều luồng đăng nhập miền được xử lý bằng **Kerberos** thay vì ứng dụng trực tiếp gửi mật khẩu qua LDAP.

Với kết nối cần bảo mật, dùng **LDAPS hoặc LDAP StartTLS** theo sản phẩm/chính sách, kiểm chứng hostname và chuỗi chứng thư; không làm “khắc phục availability” bằng cách tắt kiểm tra TLS hoặc quay sang gửi credential trên kết nối không an toàn.

## 6. High Availability: nhiều nút và nhiều vùng lỗi

**High Availability (HA)** hướng tới duy trì dịch vụ khi một thành phần bị lỗi. Thiết kế cần loại bỏ **single point of failure** trong phạm vi khả thi mà không tạo ra cấu hình quá phức tạp không thể vận hành.

| Lớp | Biện pháp thường gặp | Giới hạn cần đánh giá |
|---|---|---|
| Directory nodes | Nhiều DC/replica hoặc cụm HA theo sản phẩm | Tất cả nút có thể cùng phụ thuộc một mạng, storage hoặc cấu hình sai |
| Site/zone | Phân bố tại các site/vùng lỗi | Replication, latency, khả năng ghi và đường truyền liên site |
| DNS | Nhiều resolver, kiểm tra bản ghi dịch vụ | DNS cache hoặc cấu hình site có thể vẫn sai |
| KDC/GC/role | Phân bố dịch vụ phù hợp đặc thù AD | Không phải mọi role tự động thay thế tức thì |
| Certificate/secret | Có kế hoạch gia hạn và rotation | Chứng thư hết hạn đồng loạt vẫn có thể gây outage |
| Client | Có khả năng chọn endpoint khác, timeout và retry | Retry sai có thể gây bão request hoặc thao tác trùng |
| Network | Đường truyền dự phòng, định tuyến đúng | Phân vùng mạng có thể khiến dữ liệu không nhất quán |
| Operations | Giám sát, runbook, owner và diễn tập | HA trên sơ đồ không chứng minh được failover thật |

### 6.1. Read replica không tương đương writable node

Một số thư mục có **read-only replica**. Trong AD, **Read-Only Domain Controller (RODC)** có cơ chế và giới hạn đặc thù; không thể mặc định nó thay DC có quyền ghi đối với mọi thao tác provisioning.

Nếu chỉ còn replica chỉ đọc, **người dùng có thể tiếp tục thực hiện một số thao tác tra cứu/đăng nhập**, nhưng việc **disable account, sửa group hoặc tạo user** có thể không được phép tại nút đó. Cần đánh giá khả năng truy cập DC có quyền ghi và sự lan truyền thay đổi đến nơi kiểm soát truy cập.

### 6.2. Không phải tất cả vai trò đều có khả năng dự phòng giống nhau

AD DS có những **vai trò FSMO** với chức năng đặc thù. Nhiều DC cho phép các hoạt động thông thường tiếp tục khi một nút lỗi, nhưng **một số thao tác nhất định** có thể bị ảnh hưởng nếu vai trò/đường tới vai trò không sẵn sàng.

Không nên tự tuyên bố “có hai DC thì mọi thao tác đều HA”. Cần lập danh sách **chức năng phụ thuộc role**, xác định thời gian chịu lỗi cho từng thao tác và thử nghiệm tương ứng. Thao tác chuyển/seize role phải theo quy trình quản trị cụ thể, không tự động thực hiện vì một probe tạm thời timeout.

## 7. Replication: sẵn sàng nhưng dữ liệu có thể chưa mới

**Replication** giúp nhân bản dữ liệu directory sang các nút khác nhau. Nó cải thiện khả năng phục vụ khi một nút lỗi nhưng tạo ra bài toán **thay đổi chưa kịp lan truyền** và **quyết định quyền không cùng trạng thái**.

### 7.1. Thời gian từ ghi đến quan sát

Giả sử IAM ghi thay đổi tại DC A lúc `t0`:

~~~text
t0:  HR/VMS phát Leaver
t1:  IAM ghi user disabled / gỡ group ở DC A
t2:  DC B vẫn còn bản ghi cũ vì replication chưa xong
t3:  IdP hoặc app tra cứu DC B -> thấy trạng thái cũ
t4:  Replication tới DC B hoàn tất
t5:  Cache/phiên tại ứng dụng mới được làm mới hoặc vô hiệu hóa

Khoảng t1 → t5 mới là vùng rủi ro cần đánh giá,
không phải chỉ thời gian API trả "success" tại t1.
~~~

**Replication lag** không tự đồng nghĩa có sự cố, nhưng độ trễ có thể vượt ngưỡng nghiệp vụ khi người dùng cần quyền mới ngay hoặc khi tổ chức bắt buộc thu hồi quyền trong thời hạn chặt chẽ.

### 7.2. Read-after-write và tính nhất quán

Các hệ thống thư mục có các đảm bảo nhất quán khác nhau. Một thao tác ghi thành công trên một nút **không phải bảo đảm mọi replica đã phản ánh thay đổi ngay**. Với quá trình quan trọng:

1. Ghi thay đổi tại đúng điểm được phép ghi.
2. Kiểm tra response có ý nghĩa gì: accepted, committed tại nút hay đã đồng bộ.
3. Đọc lại ở điểm mà **IdP/ứng dụng thực sự sử dụng**, không chỉ đọc lại cùng nguồn đã ghi.
4. Đánh giá replication và những cache/session phía sau.
5. Nếu chưa đạt, giữ trạng thái **PENDING_VERIFICATION/DEGRADED** và áp kiểm soát bù trừ theo chính sách.

Trong AD, thuật toán replication và việc xung đột thuộc tính/đối tượng có đặc thù; không nên tự gộp mọi mô hình LDAP thành “eventual consistency chắc chắn đạt trong vài giây”.

### 7.3. Reconciliation và nguồn có thẩm quyền

Một replica hoặc connector có thể nhận sự kiện đến trễ. IAM cần biết **nguồn có thẩm quyền cho thuộc tính**, version hoặc mốc hiệu lực của biến cố để tránh:

- Joiner cũ đến trễ tự kích hoạt lại Leaver.
- Mover từ phòng ban trước ghi đè vai trò mới.
- Nhóm bị gỡ ở một nơi nhưng được đồng bộ lại từ dữ liệu cũ.
- Contractor hết hạn nhưng sponsor hoặc app còn giữ grant cục bộ.

**Availability tốt không thể bù cho chất lượng dữ liệu kém**. Một hệ thống HA đồng bộ sai quyền nhanh hơn vẫn không an toàn.

## 8. Availability và ranh giới giữa authentication với authorization

Khi directory tạm thời không sẵn sàng, nhiều ứng dụng muốn dùng cache để người dùng không bị gián đoạn. Nhưng cần xác định **cache cái gì, được dùng khi nào và có nguy cơ duy trì quyền đã thu hồi hay không**.

### 8.1. Các trường hợp khác nhau

| Trường hợp | Hệ thống có thể tiếp tục ra sao? | Rủi ro |
|---|---|---|
| User đang có phiên hợp lệ | Một số thao tác có thể hoạt động trong thời hạn phiên đã duyệt | Quyền/engagement đổi sau khi phiên tạo |
| User đăng nhập mới | IdP có thể cần directory để xác thực/tra trạng thái | Không thể xác nhận account còn hợp lệ |
| API kiểm quyền tại mỗi request | Nếu policy store/thuộc tính không sẵn sàng, có thể từ chối hoặc dùng chế độ được duyệt | Fail-open có thể cho quyền quá hạn |
| Thiết bị đã đăng nhập trước đó | Có thể hỗ trợ cơ chế offline sign-in cục bộ theo nền tảng | Đăng nhập thiết bị không đồng nghĩa quyền truy cập mạng/API mới |
| Workload có credential hợp lệ | Một số hoạt động máy đến máy có thể tiếp tục theo thời hạn token | Secret/account máy bị thu hồi nhưng cache chưa nhận |
| Leaver vừa có hiệu lực | Cần chặn truy cập không còn căn cứ | Replica/session/token cũ tiếp tục được tin |

**Nguyên tắc an toàn:** Không tự động biến “directory unavailable” thành “allow all”. Với hành động nhạy cảm hoặc không thể chứng minh người dùng còn đủ điều kiện, chính sách nên chọn **fail-closed hoặc cơ chế giảm chức năng an toàn**. Đối với chức năng ít rủi ro, tổ chức có thể cho phép duy trì phiên đã xác thực trong **giới hạn được phê duyệt**, nhưng phải xác định rõ trạng thái, tuổi cache, danh sách ngoại lệ và cách chặn Leaver khẩn cấp.

### 8.2. Offline sign-in khác quyền online

Một thiết bị doanh nghiệp có thể có cơ chế **cached credentials/offline logon**. Người dùng được phép vào hệ điều hành khi mất kết nối directory theo cấu hình, nhưng điều đó **không chứng minh họ còn quyền gọi API, mở tài liệu nhạy cảm trên mạng hay tiếp tục sử dụng VPN**.

Nếu một người bị Leaver trong lúc laptop đang offline, cần chính sách riêng cho **quyền máy cục bộ, mã hóa dữ liệu, thiết bị quản lý, chứng thư, phiên và thu hồi khi thiết bị kết nối lại**. Không thể giải quyết tất cả bằng cách disable account ở directory.

## 9. Thiết kế degraded mode an toàn

**Degraded mode** là trạng thái hệ thống chỉ còn một phần chức năng nhưng vẫn hoạt động theo chính sách được định nghĩa trước.

| Chức năng | Khi directory không thể xác minh dữ liệu mới | Hành động thiết kế cần cân nhắc |
|---|---|---|
| Đăng nhập mới vào hệ thống nhạy cảm | Không đủ trạng thái account/chính sách | Từ chối hoặc yêu cầu cơ chế xác minh thay thế đã duyệt |
| Tra cứu hồ sơ hiển thị | Có thể có cache ngắn hạn ít nhạy cảm | Giới hạn tuổi cache và chỉ dùng thuộc tính không quyết định đặc quyền |
| Cấp quyền admin mới | Không chắc quyền hiện hành | Hoãn hoặc chặn; cơ chế khẩn cấp riêng |
| Thu hồi quyền Leaver | Đích chưa sẵn sàng để ghi | Escalate ưu tiên, chặn ở lớp có thể kiểm soát khác |
| Workflow đang chạy với token cũ | Token có thể còn hợp lệ theo cơ chế RS | Kiểm soát tuổi token và trạng thái khi cần |
| Cập nhật nhóm/quyền | Không ghi được vào writable directory | Hàng đợi có kiểm soát, đối soát sau phục hồi |
| Service account sản xuất | Có phụ thuộc vận hành quan trọng | Kế hoạch dự phòng không mở rộng quyền hoặc rò secret |

### 9.1. Thứ tự ưu tiên phục hồi

Một mô hình minh họa:

1. **Ngăn truy cập trái phép:** Đảm bảo quyền quan trọng không bị mở do lỗi directory.
2. **Duy trì đường xác thực hợp lệ còn có thể kiểm chứng:** Nút dự phòng, KDC/IdP hoạt động, trust đúng.
3. **Duy trì/khôi phục khả năng ghi thay đổi bảo mật:** Disable user, revoke group, xử lý sự kiện Leaver.
4. **Đối soát replica và cache:** Bảo đảm điểm đọc của ứng dụng thấy trạng thái mới.
5. **Giải phóng backlog:** Xử lý Joiner/Mover/Leaver theo thứ tự và version hợp lệ.
6. **Xác minh nghiệp vụ:** Thử luồng đăng nhập và kiểm quyền đầu-cuối trên dữ liệu kiểm thử.

Thứ tự cụ thể do mức rủi ro và kiến trúc quyết định. **Không coi “đã bật lại máy chủ” là đã phục hồi toàn bộ IAM**.

## 10. Directory và IdP/SSO: ai cần phụ thuộc thời gian thực?

Không phải mọi IdP bắt buộc truy vấn LDAP trên từng lần đăng nhập. Có thiết kế:

- IdP dùng directory trực tiếp để xác thực hoặc đọc thuộc tính.
- IdP **đồng bộ dữ liệu** về kho nội bộ rồi phục vụ phiên dựa trên snapshot.
- IdP dùng **federation** tới một hệ thống xác thực khác.
- Ứng dụng có account cục bộ và chỉ dùng SSO khi cần.
- Client nhận JWT đã phát từ AS và RS kiểm cục bộ mà không gọi directory.

Mỗi mô hình làm thay đổi **đường phụ thuộc và giới hạn thu hồi**.

| Kiến trúc | Lợi ích availability | Rủi ro cần quản lý |
|---|---|---|
| IdP query directory trực tiếp | Quyết định có thể dựa trên dữ liệu mới nếu query thành công | Directory outage ảnh hưởng login ngay |
| IdP có kho đồng bộ riêng | Login có thể tiếp tục khi directory tạm lỗi | Tài khoản/group/Leaver có thể lỗi thời |
| Token JWT tự chứa | RS có thể tiếp tục kiểm token khi AS/directory lỗi | Token cũ còn hợp lệ đến hạn nếu thiếu kiểm tra bổ sung |
| Token introspection/status check | RS có thể xác minh trạng thái gần hiện tại | Phụ thuộc mạng/AS và cache introspection |
| Local app account | Giảm phụ thuộc login ở một số hệ thống | Account ngoài IAM dễ bị bỏ sót lúc Leaver |

**Cần ghi rõ source-of-truth và quyền quyết định cuối.** Đặc biệt, nếu ứng dụng dùng cache hoặc token tự chứa, phải có cơ chế giới hạn thời gian và xử lý chấm dứt quyền phù hợp với thời hạn thu hồi đã cam kết.

## 11. Directory availability trong Joiner lifecycle

Một người mới được HR phê duyệt, identity proofing đã đạt và IAM phát yêu cầu tạo account. Nếu directory không sẵn sàng, có thể gặp:

- Create user thành công tại nút A nhưng chưa thấy tại nút B, nơi IdP truy vấn.
- Account được tạo nhưng nhóm vai trò chưa đồng bộ.
- Người dùng nhận hướng dẫn kích hoạt nhưng login thất bại.
- User đã vào được IdP nhưng ứng dụng đích chưa nhận account qua SCIM.
- Tài khoản chưa đến ngày làm việc nhưng một bản cache/nhóm mặc định mở quyền sớm.

### Cách kiểm chứng readiness cho Joiner

1. Xác nhận biến cố từ nguồn HR/VMS có thẩm quyền, đúng identity và mốc hiệu lực.
2. Kiểm tra account được tạo ở directory **với ID ổn định** và trạng thái đúng.
3. Xác minh dữ liệu đã xuất hiện ở **điểm đọc mà IdP/connector sử dụng**.
4. Kiểm tra nhóm/thuộc tính nền tảng và bộ quyền mong muốn.
5. Đọc lại account và entitlement tại ứng dụng SCIM/API bắt buộc.
6. Kiểm tra người dùng có thể xác thực theo chính sách tại thời điểm được phép.
7. Phân biệt trạng thái **PROVISIONED**, **PENDING_REPLICATION**, **PENDING_APPLICATION** và **READY** thay vì chỉ báo “đã tạo”.

**Không tự retry CREATE một user mới** khi query replica chưa nhìn thấy account ở DC khác. Cần idempotency và mapping identity–account để tránh tạo trùng do replication lag.

## 12. Directory availability trong Mover lifecycle

Một nhân viên chuyển bộ phận hoặc địa điểm có thể vẫn đăng nhập thành công nhưng giữ **quyền cũ** vì group chưa đồng bộ hoặc ứng dụng giữ token đã phát trước thay đổi.

| Tình huống | Biểu hiện | Kiểm soát |
|---|---|---|
| Nhóm mới chưa tới DC IdP đọc | Người dùng không có quyền nhiệm vụ mới | Theo dõi replication và điểm đọc |
| Nhóm cũ chưa được gỡ ở một replica | Người dùng giữ quyền cũ | Readback trên đường truy cập thực tế |
| Group update đúng nhưng app giữ cache | Ứng dụng vẫn dùng role cũ | Policy cache TTL, invalidation và đối soát |
| Token cũ chứa claim cũ | API vẫn chấp nhận quyền quá hạn | Quy định thời hạn token/kiểm trạng thái hiện hành |
| Sai nguồn phòng ban/site | Đồng bộ nhanh nhưng cấp sai quyền | Nguồn có thẩm quyền, version, review |
| Mất writable directory | Không cập nhật được quyền | Queue có kiểm soát, xử lý ngoại lệ và giảm rủi ro |

**Mover phải tính cả quyền cần thêm và quyền cần thu hồi.** Không gọi sự kiện “hoàn tất” chỉ vì nhóm mới đã xuất hiện. Cần xác nhận nhóm/quyền cũ không còn hiệu lực tại ứng dụng và API khi không còn căn cứ.

## 13. Directory availability trong Leaver lifecycle

**Leaver là tình huống kiểm thử quan trọng nhất về sự kết hợp availability và security.** Nếu directory không sẵn sàng để disable account hoặc chưa đồng bộ trạng thái, một người đã hết quan hệ làm việc có thể còn truy cập tài nguyên.

~~~mermaid
sequenceDiagram
    autonumber
    participant H as HR / VMS
    participant I as IAM / IGA
    participant A as Directory A (writable)
    participant B as Directory B / replica
    participant P as IdP / SSO
    participant R as App / API

    H->>I: Leaver event có mốc hiệu lực
    I->>A: Disable user + revoke grants
    A-->>I: Write accepted / committed tại A
    A-->>B: Replication bất đồng bộ
    I->>B: Readback ở điểm phục vụ truy cập
    B-->>I: Có thể còn state cũ
    I->>I: Giữ trạng thái PENDING_VERIFICATION
    I->>P: Thu hồi phiên/token theo cơ chế hỗ trợ
    I->>R: Thu hồi entitlement / local session
    B-->>I: State mới sau replication
    I->>B: Readback lại
    B-->>I: Disabled + grants revoked
    I->>R: Kiểm chứng quyền hiệu dụng ở app
    R-->>I: Access denied theo policy
    I->>I: Chỉ đóng khi tiêu chí bắt buộc đạt
~~~

### 13.1. Không chỉ kiểm tra user.disabled

Một kết quả `disabled=true` ở directory **không tự chứng minh**:

- Access token JWT cũ đã vô hiệu hóa tại RS.
- Local session trong ứng dụng đã bị kết thúc.
- Personal access token, API key hoặc credential máy đã bị thu hồi.
- Quyền chia sẻ trực tiếp và role ứng dụng đã mất.
- Các replica/connector đã nhận trạng thái mới.

Kế hoạch Leaver cần bao phủ **IdP/SSO, SCIM/API, session/token, RBAC/ABAC, quyền ứng dụng và tài khoản dịch vụ có liên quan**. Nếu chưa có bằng chứng từ target bắt buộc, workflow phải giữ trạng thái phù hợp và có owner xử lý.

### 13.2. Trong lúc outage không thể ghi thu hồi

Nếu không thể disable account tại directory ngay, IAM phải **báo lỗi và ưu tiên biện pháp bù trừ ở các lớp có thể điều khiển** theo chính sách, ví dụ revoke session/token ở IdP, chặn account tại ứng dụng, khóa VPN/ZTNA hoặc quyền vật lý. Những biện pháp này cần được kiểm chứng và không đồng nghĩa đã cập nhật thành công directory. Khi khôi phục, phải tiếp tục ghi, đọc lại và đối soát toàn bộ.

## 14. Service accounts và các phụ thuộc vận hành ẩn

Dịch vụ thư mục thường được truy cập bởi **service account, bind account hoặc workload identity**. Những account này có thể có vòng đời riêng với nhân viên.

| Trường hợp | Rủi ro availability | Kiểm soát |
|---|---|---|
| Bind account hết hạn mật khẩu/secret | Hàng loạt ứng dụng LDAP bind thất bại | Owner, secret management, rotation và thử nghiệm |
| Service account bị disable nhầm | Provisioning/IdP đồng loạt ngừng đồng bộ | Xác định workload dependency, change control |
| Certificate của LDAPS hết hạn | Client từ chối kết nối bảo vệ | Giám sát expiry, gia hạn và readback |
| Job đồng bộ chỉ có một credential | Tạo single point of failure vận hành | Phương án khôi phục credential không vi phạm chính sách |
| Người vận hành service account nghỉ việc | Account máy không còn owner, secret có thể bị biết | Chuyển owner, đánh giá rotation và quyền quản trị |
| Quá nhiều quyền directory | Credential bị lộ gây thao tác ngoài phạm vi | Least privilege, phân tách read/write và giới hạn scope |
| Retry bind liên tục khi lỗi | Làm directory quá tải hoặc khóa account | Backoff, circuit breaker và cảnh báo |

**Không dùng tài khoản admin domain làm bind account đọc directory thường ngày** nếu nhu cầu chỉ cần tra cứu. Quyền của client/service account nên tối thiểu và có khả năng kiểm toán. Mặt khác, **không xóa bừa một service account** đang phục vụ ứng dụng production chỉ vì người tạo đã rời tổ chức; phải xác định workload/owner rồi xử lý quyền và credential an toàn.

## 15. Giám sát Directory availability bằng SLI và SLO

**Service Level Indicator (SLI)** là phép đo chất lượng thực tế; **Service Level Objective (SLO)** là mục tiêu đã thỏa thuận cho phép đo ấy. Với directory, cần theo dõi cả **trải nghiệm xác thực và độ mới trạng thái**, không chỉ ping host.

| SLI | Cách đo gợi ý | Tín hiệu lỗi |
|---|---|---|
| **Directory query success** | Tỷ lệ bind/search hợp lệ hoàn thành trong thời hạn | Timeout, LDAP error, không tìm thấy đối tượng kỳ vọng |
| **Authentication dependency health** | Thử giao dịch kiểm tra bằng tài khoản kiểm thử an toàn | LDAP/Kerberos/IdP login hỏng |
| **Query latency** | Độ trễ ở percentile phù hợp theo site | Site xa, overload, lỗi index |
| **Write success** | Tạo/sửa/disable đối tượng kiểm thử ở môi trường được phép | Không có writable endpoint, policy lỗi |
| **Replication freshness** | Tuổi thay đổi chưa đến replica; health replication | Group/Leaver trễ so với ngưỡng |
| **DNS/service discovery correctness** | Trả endpoint đúng site, DNS SRV hợp lệ | DC không được chọn hoặc chọn DC lỗi |
| **TLS readiness** | Handshake an toàn, chứng thư/hostname hợp lệ | Cert hết hạn, trust chain sai |
| **End-to-end IAM readiness** | Test IdP→app trên account kiểm thử có quyền giới hạn | Directory xanh nhưng login/app lỗi |
| **JML convergence** | Từ event tới lúc target truy cập phản ánh quyền mong muốn | Joiner chờ, Mover quyền cũ, Leaver còn quyền |
| **Deprovision verification coverage** | Phần trăm target bắt buộc có readback | Request thành công nhưng không biết quyền còn không |

### 15.1. Synthetic probe đáng tin cậy

**Synthetic monitoring** nên mô phỏng một thao tác thật, ví dụ query đối tượng kiểm thử hoặc xác thực qua kênh được phép. Không nên chỉ TCP connect tới cổng LDAP.

Mô hình probe:

~~~text
Mỗi site, theo lịch và giới hạn tần suất phù hợp:
  1. Phân giải tên DNS / service discovery của directory.
  2. Kết nối tới endpoint được phép qua TLS khi áp dụng.
  3. Thực hiện bind/test auth với credential kiểm thử hạn quyền.
  4. Query bản ghi sentinel: ID, nhóm/thuộc tính mong đợi.
  5. Đo độ trễ, mã lỗi, endpoint thực sự được sử dụng.
  6. Kiểm tra replication/freshness từ nguồn quản trị phù hợp.
  7. Ghi metrics và cảnh báo; không ghi mật khẩu hoặc token.
~~~

**Credential của probe** phải được bảo vệ, có owner và phạm vi chỉ đọc thích hợp; tránh tạo lưu lượng làm tăng tải hoặc khóa hàng loạt account khi dịch vụ đang gặp sự cố. Đối với test **write/disable**, dùng đối tượng thử nghiệm trong phạm vi/tenant được phê duyệt và có cleanup; không tự thực hiện trên account người dùng thật.

### 15.2. Cảnh báo phải phản ánh tác động

Một DC lỗi có thể không gây outage nếu các nút còn lại phục vụ được client. Nhưng cũng có thể **mất khả năng ghi hoặc tăng replication lag**, dẫn đến Leaver không đạt SLA. Cảnh báo cần phân loại **nút lỗi, mất site, mất capability, đồng bộ trễ và tác động truy cập nhạy cảm**.

## 16. Đo lường độ mới dữ liệu và hội tụ JML

Một directory có thể đáp ứng SLO đọc nhưng không đạt mục tiêu **hội tụ quyền**. Nên theo dõi vòng đời từ **sự kiện có thẩm quyền tới kết quả tại ứng dụng**.

~~~mermaid
flowchart LR
    E["JML event<br/>HR / VMS"] --> I["IAM policy<br/>Desired state"]
    I --> W["Directory write<br/>Committed state"]
    W --> P["Replication<br/>Replica state"]
    P --> D["IdP / SSO / Connector<br/>Consumed state"]
    D --> A["Ứng dụng / API<br/>Effective access"]
    A --> V["Readback + audit<br/>Verified convergence"]
~~~

### 16.1. Các mốc thời gian cần phân biệt

| Mốc | Ý nghĩa |
|---|---|
| `eventReceivedAt` | IAM nhận biến cố từ nguồn |
| `effectiveAt` | Thời điểm thay đổi phải có hiệu lực theo chính sách |
| `directoryWriteAt` | Thao tác tại điểm ghi được xác nhận |
| `replicaVisibleAt` | Các điểm đọc liên quan đã thấy thay đổi |
| `idpAppliedAt` | IdP/connector áp trạng thái mới |
| `appAppliedAt` | Ứng dụng cập nhật account/quyền |
| `accessVerifiedAt` | Quyền thực tế đã được kiểm chứng |
| `closedAt` | Quy trình đóng sau khi đạt tiêu chí |

**Độ trễ từ event đến lệnh ghi** khác **độ trễ đến quyền thực tế**. Với Leaver, tổ chức cần đặt mục tiêu kiểm tra theo **mốc effectiveAt và yêu cầu bảo mật**, không chỉ KPI tốc độ API.

### 16.2. Readback cần đúng điểm và đúng nguồn

Nếu IAM ghi ở DC A và sau đó cũng chỉ đọc DC A, kết quả có thể PASS trong khi IdP đang kết nối DC B chưa đồng bộ. Vì vậy, readback phải biết **đường truy cập thực tế và phạm vi replica/target bắt buộc**.

Nếu không thể truy vấn trực tiếp từng replica, cần phương pháp gián tiếp hoặc kiểm soát bù trừ đã phê duyệt; không tuyên bố đã xác minh tất cả khi chỉ có một nguồn quan sát.

## 17. Kế hoạch Backup và Disaster Recovery (DR)

HA giúp duy trì dịch vụ khi có lỗi thành phần, nhưng **không thay thế backup**. Dữ liệu bị xóa nhầm, ransomware, thay đổi cấu hình sai hoặc corruption có thể **lan truyền qua replication đến nhiều nút**. Để phục hồi, tổ chức cần kế hoạch **Disaster Recovery (DR)** phù hợp từng loại directory.

| Hạng mục | Cần chuẩn bị |
|---|---|
| **Backup** | Bản sao có bảo vệ, đúng kiểu backup hỗ trợ, đủ bao phủ directory và cấu hình quan trọng |
| **Khả năng phục hồi** | Thử restore định kỳ trên môi trường cô lập và theo quy trình sản phẩm |
| **RTO** | Thời gian phục hồi dịch vụ mục tiêu theo mức ảnh hưởng |
| **RPO** | Lượng thay đổi dữ liệu tối đa có thể mất theo chính sách |
| **Trust/keys/certificates** | Phương án phục hồi bí mật/khóa/chứng thư an toàn, đúng ownership |
| **DNS/network** | Thứ tự phục hồi phụ thuộc thiết yếu |
| **Replication** | Kế hoạch đưa replica vào hoạt động lại tránh nhân bản dữ liệu sai |
| **IAM connector** | Khởi động lại đồng bộ, xử lý backlog và sự kiện đến trễ |
| **Audit/forensics** | Log, dấu vết thay đổi và khả năng điều tra sau sự cố |

### 17.1. Lưu ý đặc thù Active Directory

Khôi phục AD DS phải tuân theo **phương pháp backup/restore được hệ thống hỗ trợ**, bao gồm xem xét **system state**, trạng thái DC, replication, thời hạn và cơ chế khôi phục phù hợp. Không nên copy thư mục database hoặc khôi phục snapshot tùy tiện vào production mà chưa đánh giá rủi ro như **lỗi nhất quán replication/USN rollback** và các biện pháp bảo vệ của phiên bản đang dùng.

Các thao tác phục hồi đối tượng, **authoritative/nonauthoritative restore**, khôi phục domain/forest hoặc xử lý FSMO là nghiệp vụ vận hành chuyên sâu, cần runbook đã kiểm thử và người có thẩm quyền. Bài này không đưa lệnh khôi phục trực tiếp để tránh gây hỏng môi trường.

### 17.2. Phục hồi không kết thúc ở “dịch vụ LDAP đã lên”

Sau restore cần:

1. Kiểm tra DNS, mạng, TLS/Kerberos và endpoint directory thực sự phục vụ.
2. Xác minh replication, trạng thái dữ liệu và health từng nút/site.
3. Đối chiếu các biến cố JML đã xảy ra trong khoảng gián đoạn/khôi phục.
4. Không phát lại sự kiện cũ theo cách kích hoạt account Leaver hoặc khôi phục nhóm cũ.
5. Đối soát IdP/SCIM/ứng dụng, token/session và quyền hiệu dụng.
6. Lưu bằng chứng phục hồi, điểm còn rủi ro và quyết định mở lại toàn bộ dịch vụ.

## 18. Runbook xử lý khi directory không sẵn sàng

Một quy trình ứng phó sự cố nên tách **phát hiện, khoanh vùng, khôi phục và kiểm chứng quyền**.

### Giai đoạn A — Xác định phạm vi

- Lỗi xảy ra trên **một DC**, một site, toàn bộ directory, DNS, KDC hay một nhóm ứng dụng?
- Client bị lỗi **bind/search, Kerberos, password change, group lookup hay provisioning**?
- Có ảnh hưởng riêng với user mới, user hiện hữu, service account hoặc admin?
- Những biến cố **Leaver/khóa khẩn cấp** nào đang chờ xử lý?
- Đã có failover thực tế tới endpoint khác hay chưa?

### Giai đoạn B — Bảo vệ và giảm ảnh hưởng

- Đảm bảo **không chuyển sang LDAP không mã hóa** hoặc tắt kiểm chứng TLS/SSO để “cho chạy lại”.
- Áp chính sách degraded mode đã duyệt; chặn quyền nhạy cảm khi trạng thái không thể xác minh.
- Với Leaver khẩn cấp, đánh giá **chặn ở IdP, RS, VPN/ZTNA hoặc ứng dụng** nếu directory không ghi được.
- Giảm retry storm, dùng backoff có giới hạn; bảo vệ credential probe/service account.
- Có owner điều phối sự cố và nhật ký thay đổi trạng thái.

### Giai đoạn C — Khắc phục nguyên nhân

- Kiểm tra DNS và endpoint discovery; loại trừ sai site/host.
- Kiểm tra đường mạng, TLS, certificate, thời gian hệ thống và Kerberos khi liên quan.
- Đánh giá tải, pool kết nối, timeout, storage và dịch vụ trên nút lỗi.
- Kiểm tra writable endpoint, replication health, backlog và cấu hình firewall.
- Chuyển hướng client/failover theo quy trình được hỗ trợ; không tạo cấu hình ad hoc gây split-brain hoặc xung đột dữ liệu.

### Giai đoạn D — Đối soát sau sự cố

- Thử đăng nhập và truy vấn directory đầu-cuối trên tài khoản kiểm thử.
- Xác minh dữ liệu mới và cũ hội tụ trên các điểm truy cập liên quan.
- Xử lý backlog Joiner, Mover, Leaver dựa trên **version/trạng thái hiện hành từ nguồn có thẩm quyền**.
- Readback các thao tác cấp/thu hồi quyền và đánh giá token/phiên tồn dư.
- Chỉ đóng sự cố IAM khi chức năng và tiêu chí bảo mật bắt buộc đã đạt; hạng mục còn lại phải có owner và thời hạn.

## 19. Các tình huống thực hành

### Tình huống A — DC A lỗi nhưng đăng nhập vẫn được

**Bối cảnh:** Một doanh nghiệp có DC A và DC B. DC A mất điện, nhân viên hiện hữu vẫn SSO được qua DC B. Tuy nhiên, helpdesk không tạo được account mới vì connector chỉ được cấu hình ghi tới DC A.

**Phân tích:** Đây là **khả năng xác thực còn hoạt động nhưng write availability không đạt**. Không thể báo “directory HA hoàn toàn” chỉ vì login thành công. Cần xác minh thiết kế writable DC, service discovery của connector và cơ chế retry/failover an toàn, sau đó thử tạo account kiểm thử và đọc lại.

### Tình huống B — User đã nghỉ nhưng replica chưa thấy disable

**Bối cảnh:** IAM disable contractor trên DC A lúc 18:00. IdP đang query DC B, nơi chưa nhận thay đổi. Một token/phiên cũ vẫn có thể đọc tài liệu dự án.

**Phân tích:** Đây là kết hợp **replication lag và session/token staleness**. Phải theo dõi thời gian áp thay đổi tại B, chặn token/phiên hoặc quyền ứng dụng khi chính sách đòi hỏi và **readback quyền thực tế**. Việc lệnh LDAP trên A thành công chưa chứng minh Leaver hoàn tất.

### Tình huống C — LDAP port mở nhưng IdP không bind được

**Bối cảnh:** Giám sát hạ tầng báo DC khỏe vì TCP 636 mở. IdP lại báo TLS handshake failure sau khi LDAPS certificate hết hạn.

**Phân tích:** Đây là **endpoint reachable nhưng không service-ready**. Cần kiểm tra chain, hostname, expiry, trust và quy trình gia hạn certificate. Không vô hiệu hóa TLS validation như cách xử lý lâu dài.

### Tình huống D — Mover bị tích lũy quyền

**Bối cảnh:** Linh chuyển từ dự án A sang B. Group mới đã đồng bộ, nhưng quyền A vẫn còn trên một application cache và một ACL trực tiếp.

**Phân tích:** Directory write/replication không tự gỡ quyền ứng dụng ở mọi nguồn. IAM phải tính lại **desired vs effective entitlement**, thu hồi grant A không còn căn cứ, xử lý cache/session và xác minh tại API. Không coi việc nhóm B xuất hiện là đã hoàn tất Mover.

### Tình huống E — Nhiều DC nhưng cùng một điểm lỗi

**Bối cảnh:** Hai DC nằm trên hai VM khác nhau nhưng dùng chung một máy chủ lưu trữ và một đường mạng duy nhất. Khi storage lỗi, cả hai đều ngừng.

**Phân tích:** Đây là **HA trên sơ đồ nhưng chưa tách failure domain**. Cần đánh giá sự phụ thuộc hạ tầng, placement, mạng, DNS, backup và khả năng phục hồi ngoài cụm. Không có số lượng nút cố định nào bảo đảm sẵn sàng nếu tất cả có chung điểm lỗi.

### Tình huống F — Service account mất owner trong quá trình DR

**Bối cảnh:** Sau khôi phục directory, một job đối soát dữ liệu cần bind bằng service account. Owner cũ đã nghỉ; credential đang nằm trong cấu hình không còn người quản lý.

**Phân tích:** Không tự kích hoạt lại service account với quyền admin cũ. Cần xác minh workload và owner hiện hành, cấp credential an toàn/rotate theo rủi ro, quyền tối thiểu và khả năng readback; chỉ đưa job trở lại khi đáp ứng điều kiện kỹ thuật lẫn bảo mật.

## 20. Bài tập tự kiểm tra

**Câu 1:** Ping DC và kiểm cổng LDAP đều thành công. Có thể kết luận directory đủ sẵn sàng cho IAM không?

**Gợi ý:** Chưa. Cần probe thao tác LDAP/Kerberos/IdP thực tế, DNS, TLS, write capability khi cần và độ mới replication.

**Câu 2:** User được tạo ở DC A nhưng IdP query DC B chưa thấy. Có nên chạy lệnh CREATE lại ngay?

**Gợi ý:** Không nên. Kiểm ID và mapping, replication lag và readback; retry có tính lặp an toàn để tránh user trùng.

**Câu 3:** Directory không truy cập được, ứng dụng mặc định cho phép mọi admin đang mở phiên thao tác. Điều gì sai?

**Gợi ý:** Đây là nguy cơ **fail-open**. Cần chính sách degraded mode/authorization đã duyệt, giới hạn quyền và đánh giá trạng thái phiên/cache.

**Câu 4:** Vì sao có hai DC không tự bảo đảm mọi thao tác AD DS luôn hoạt động khi một DC lỗi?

**Gợi ý:** Tính sẵn sàng phụ thuộc DNS/network, role đặc thù, writable capability, KDC/GC, replication và cách client chọn DC.

**Câu 5:** Bản ghi user đã disabled ở directory nhưng token tự chứa cũ còn hiệu lực tại API. Leaver đã hoàn tất chưa?

**Gợi ý:** Chưa đủ căn cứ. Cần kiểm token/session và quyền hiệu dụng tại RS/ứng dụng theo tiêu chí thu hồi.

**Câu 6:** SLO đọc directory tốt nhưng Mover mất hai giờ mới thu hồi quyền cũ. Vấn đề nằm ở đâu?

**Gợi ý:** SLI availability thuần đọc không bao phủ **JML convergence**, cache, connector và application entitlement. Cần đo end-to-end.

**Câu 7:** Restore backup AD DS thành công và LDAP query trả dữ liệu. Có cần rà soát gì nữa?

**Gợi ý:** Kiểm replication, DNS/Kerberos, trạng thái account/quyền, các biến cố JML xảy ra sau mốc backup, IdP/SCIM và session/token.

**Câu 8:** Service account dùng để bind directory bị lỗi, đội vận hành muốn chuyển sang Domain Admin và ghi mật khẩu vào file. Cách làm có phù hợp không?

**Gợi ý:** Không. Phải dùng credential hạn quyền có owner, bảo vệ secret và xử lý nguyên nhân bind/TLS/rotation, tránh tăng đặc quyền không cần thiết.

## 21. Checklist thiết kế và vận hành Directory availability

- [ ] **Phạm vi:** Đã phân loại thao tác cần HA: authentication, lookup, group, create/disable, replication và readback?
- [ ] **Nguồn danh tính:** HR/VMS, directory và IAM có ranh giới dữ liệu có thẩm quyền rõ ràng?
- [ ] **Failure domains:** DC/replica, storage, site, DNS, mạng và quyền ghi không có điểm lỗi đơn chưa được xử lý?
- [ ] **Discovery:** Client chọn endpoint hợp lệ, DNS/SRV và site awareness được kiểm chứng?
- [ ] **Bảo vệ kết nối:** LDAP/TLS, certificate, Kerberos/time sync và credential service được quản lý?
- [ ] **Read/write:** Đã phân biệt điểm có thể đọc, xác thực và ghi; thử failover cho từng khả năng?
- [ ] **Replication:** Có SLI cho độ mới, thay đổi đến trễ và cơ chế ngăn event cũ ghi đè state mới?
- [ ] **IdP/SSO:** Đã xác định live query hay cache/sync; session/token có giới hạn thu hồi phù hợp?
- [ ] **SCIM/API:** Provisioning và deprovisioning có retry an toàn, readback và cảnh báo lỗi một phần?
- [ ] **RBAC/ABAC:** Chính sách kiểm quyền dựa trên trạng thái còn hiệu lực; không mở quyền rộng khi directory lỗi?
- [ ] **Degraded mode:** Quy định rõ chức năng được phép, bị chặn, giới hạn tuổi cache, escalation và phương án khẩn cấp?
- [ ] **Joiner:** Account tạo đúng người, đúng mốc, đúng điểm đọc, không tạo trùng do replication lag?
- [ ] **Mover:** Quyền mới được cấp và quyền cũ được thu hồi trên ứng dụng/phiên thực tế?
- [ ] **Leaver:** Có kiểm chứng disable, entitlement, phiên/token và quyền tồn dư tại các target bắt buộc?
- [ ] **Service account:** Bind/workload account có owner, credential lifecycle, least privilege và kế hoạch khi người quản trị rời đi?
- [ ] **Monitoring:** Có synthetic probes thực tế, SLI/SLO theo site, write health và JML convergence?
- [ ] **HA/DR:** Có backup/restore được hỗ trợ, RTO/RPO mục tiêu, diễn tập failover/khôi phục và runbook?
- [ ] **Kiểm toán:** Đã lưu event, thời điểm, endpoint, kết quả readback, ngoại lệ và owner mà không làm lộ credential?
- [ ] **Phục hồi:** Sau outage đã đối soát backlog JML, replication, cache, role và token trước khi xác nhận hoàn tất?
- [ ] **Quyền riêng tư:** Probe/log không lưu mật khẩu, secret, token hoặc dữ liệu cá nhân vượt mục đích?

**Ghi nhớ:** **Directory availability** không chỉ là có một LDAP/AD server đang chạy. Một hệ thống IAM đáng tin cậy phải bảo đảm **đường truy cập, khả năng xác thực/tra cứu/ghi, replication đủ mới, dữ liệu đúng nguồn và kết quả authorization thực tế**. HA, DNS/Kerberos, giám sát, failover và DR giúp tăng tính liên tục; còn **IdP/SSO, SCIM, RBAC/ABAC, quản lý service account, readback và kiểm toán** giúp bảo vệ sự chính xác của quyền truy cập. Thiết kế hoàn chỉnh phải phục vụ cả **Joiner sẵn sàng đúng lúc, Mover không tích lũy quyền cũ và Leaver được thu hồi có thể chứng minh**, ngay cả khi directory gặp sự cố.

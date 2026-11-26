# Sao lưu và diễn tập khôi phục trước khi nâng cấp

Một bản nâng cấp Neo4j có thể thay đổi database engine, định dạng lưu trữ, catalog schema, cấu hình bảo mật, plugin và khả năng tương thích của ứng dụng Java. Nếu hệ thống gặp lỗi sau nâng cấp, một nút **“khởi động lại phiên bản cũ”** chưa chắc là phương án khôi phục: phiên bản cũ có thể không đọc được store đã được mở hoặc chuyển đổi bởi phiên bản mới. **Phương án quay lui đáng tin cậy phải bắt đầu từ bản sao lưu hợp lệ và một quy trình restore đã được diễn tập.**

Bài thuộc chương **Nâng cấp và di trú** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Neo4j lưu node, relationship và property theo mô hình **property graph**, truy vấn bằng Cypher, sử dụng index/constraint để bảo vệ và truy xuất dữ liệu, đồng thời kết nối ứng dụng qua Java Driver hoặc Spring Data Neo4j. Khi nâng cấp hệ thống này, cần bảo vệ không chỉ các bản ghi mà cả **liên kết, bất biến nghiệp vụ, schema, quyền, transaction log, đường kết nối và khả năng phục hồi ứng dụng**.

Sau bài học, bạn có thể:

- Phân biệt **backup**, **restore**, **recovery**, **rollback**, **snapshot**, **replica** và mục tiêu **RPO/RTO**.
- Lựa chọn cách sao lưu phù hợp với Community/Enterprise, self-managed/cluster hoặc Neo4j Aura theo **phiên bản và gói đang vận hành**.
- Lập hồ sơ trước nâng cấp, tạo bản sao lưu độc lập, kiểm tra tính đầy đủ và khả năng truy cập của bản sao.
- Diễn tập restore vào môi trường cô lập, xác minh node, relationship, property, index, constraint, transaction và ứng dụng.
- Định nghĩa chính xác điểm cắt dữ liệu, thời gian ngừng ghi, kế hoạch cutover và rollback khi ứng dụng đã phát sinh giao dịch mới.
- Xây dựng quy trình GO/NO-GO, kiểm thử sự cố và báo cáo bằng chứng phục hồi.

> **Lưu ý phiên bản:** Lệnh `neo4j-admin`, tính năng online/incremental backup, quy trình migration/restore, tính năng cluster và gói backup của Aura thay đổi theo phiên bản, edition. Những lệnh minh họa bên dưới chủ yếu theo kiểu cú pháp của dòng Neo4j 5.x; phải xác minh lệnh thực tế bằng tài liệu và `--help` của **phiên bản cài đặt**. Không áp dụng lệnh ghi/xóa/restore vào production nếu chưa có thay đổi được phê duyệt.

## 1. Vì sao backup là điều kiện bắt buộc trước nâng cấp?

Giả sử một dịch vụ Neo4j quản lý khách hàng và đơn hàng:

~~~text
(:UpgradeDemoCustomer {tenantId, customerId, name})
                  |
                  | [:UPGRADE_DEMO_PLACED]
                  v
(:UpgradeDemoOrder {tenantId, orderId, status, amountMinor})
~~~

Ứng dụng đọc một khách cùng các đơn hàng, cập nhật trạng thái bằng transaction và dùng index để tra cứu theo mã khách hoặc mã đơn. Một lần nâng cấp có thể làm lỗi xuất hiện ở nhiều lớp:

| Lớp | Rủi ro khi nâng cấp | Kiểm chứng cần có |
| --- | --- | --- |
| Store | Store không tương thích với bản cũ hoặc migration thất bại. | Restore được bản sao trên phiên bản được hỗ trợ; database mở và đọc/ghi đúng. |
| Transaction | Ghi đã commit trước lỗi không được phục hồi như kỳ vọng. | Thử ghi, commit, restart/restore và đọc lại. |
| Node/relationship | Dữ liệu bị thiếu, thay đổi nhãn/type hoặc cạnh sai chiều. | Đối soát khóa, thuộc tính, số cạnh và endpoint nghiệp vụ. |
| Index/constraint | Index chưa ONLINE, constraint lỗi hoặc schema thay đổi. | `SHOW INDEXES`, `SHOW CONSTRAINTS`, truy vấn bất biến. |
| Security | Quyền, role, secret, TLS hoặc auth provider không giống môi trường gốc. | Thử user/role thật trong môi trường phục hồi có kiểm soát. |
| Plugin/driver | APOC, GDS, Java Driver, SDN hoặc Cypher không còn tương thích. | Kiểm thử smoke/integration và ma trận hỗ trợ. |
| Cluster/routing | Một thành viên không thể bắt kịp, route sai hoặc thiếu quorum. | Kiểm tra topology, routing, replication và failover theo quy trình phiên bản. |
| Backup/operations | Backup thiếu, mất khóa mã hóa, restore quá lâu. | Diễn tập độc lập và đo RTO thực tế. |

**Tệp backup tồn tại ≠ backup dùng được.** Chỉ sau khi đọc, restore, mở database, kiểm tra dữ liệu và chạy ứng dụng thành công, ta mới có bằng chứng rằng bản sao có thể giúp khôi phục.

### 1.1. Hai cách xử lý lỗi rất khác nhau

~~~text
Nâng cấp -> lỗi
   |
   +-- Restart bản mới, sửa cấu hình rồi tiếp tục
   |       (chưa phải rollback)
   |
   '-- Phục hồi một bản sao trước nâng cấp
           trên phiên bản tương thích
           + xác minh dữ liệu + mở lại traffic
           (đây mới là rollback bằng restore)
~~~

Nếu ứng dụng đã tiếp tục nhận ghi sau nâng cấp, restore bản sao trước nâng cấp có thể **làm mất các giao dịch mới**. Vì vậy, quyết định rollback không chỉ là thao tác kỹ thuật; phải có **điểm cắt, chính sách giữ hoặc phát lại giao dịch và người phê duyệt**.

## 2. Thuật ngữ và mục tiêu khôi phục

| Thuật ngữ | Ý nghĩa | Lầm tưởng cần tránh |
| --- | --- | --- |
| **Backup** | Bản sao dữ liệu được tạo bằng cơ chế được hỗ trợ để phục hồi về trạng thái xác định. | Một bản copy file bất kỳ khi DB đang ghi không mặc nhiên là backup nhất quán. |
| **Restore** | Đưa dữ liệu từ backup vào một database/môi trường phù hợp. | Lệnh restore không chứng minh ứng dụng đã phục vụ đúng. |
| **Recovery** | Đưa database về trạng thái nhất quán sau crash hoặc restore, có thể áp dụng log theo cơ chế engine. | Khởi động xong không đồng nghĩa mọi index/query/role hoạt động. |
| **Rollback** | Quay về trạng thái/phiên bản được phê duyệt sau nâng cấp lỗi. | Đổi tag container sang bản cũ không chắc đọc được store đã migration. |
| **Snapshot** | Bản chụp storage hoặc dịch vụ ở thời điểm nào đó. | Snapshot volume không tự bảo đảm application consistency. |
| **Replica** | Bản sao đồng bộ/nhân bản phục vụ HA theo kiến trúc. | Replica có thể sao chép cả xóa nhầm/lỗi nghiệp vụ; không thay thế backup. |
| **RPO** | Mức dữ liệu có thể mất tối đa, tính theo thời điểm được phục hồi. | Không đồng nghĩa khoảng cách giữa hai lần chạy backup nếu còn log/cơ chế phục hồi khác. |
| **RTO** | Thời gian tối đa cho phép đến khi dịch vụ phục hồi ở mức đã cam kết. | Chỉ đo tốc độ copy tệp chưa tính verify, routing, index, ứng dụng. |

Ví dụ doanh nghiệp quy định:

- **RPO = 15 phút:** sau một sự cố, trạng thái được phục hồi có thể cũ tối đa 15 phút so với điểm lỗi, theo phương thức đo được phê duyệt.
- **RTO = 60 phút:** từ lúc sự cố được nhận diện đến khi các thao tác nghiệp vụ cốt lõi hoạt động trở lại không quá 60 phút.

Đó là **mục tiêu ví dụ**, không phải khả năng mặc định Neo4j nào cũng có. Nếu diễn tập restore thực tế mất 95 phút thì phương án hiện tại **không đạt RTO**, dù backup đọc được.

### 2.1. Chuỗi thời gian quanh nâng cấp

~~~text
T0         T1             T2                T3
|----------|--------------|-----------------|----->
backup     chặn ghi       nâng cấp          kiểm tra
đã test    + final backup và migration      + mở traffic

                    \___ rollback path ___/
              restore bản sao có điểm cắt rõ ràng
~~~

Thời điểm nào được chọn là **điểm khôi phục cuối được chấp nhận** phải thống nhất giữa database, ứng dụng và những hệ thống tích hợp (queue/CDC, search index, object store). Không được tuyên bố RPO bằng 0 chỉ vì “backup ngay trước khi bấm upgrade” khi có giao dịch đang chạy hoặc event nguồn chưa áp dụng.

## 3. Kiểm kê toàn bộ những thứ cần bảo vệ

Một bản dump/backup database không tự chứa mọi thứ cần để hệ thống hoạt động. Lập một **bảng inventory** trước nâng cấp:

| Nhóm | Thành phần | Cách bảo vệ |
| --- | --- | --- |
| Database nghiệp vụ | Node, relationship, property và metadata của database được chọn. | Backup/dump được Neo4j hỗ trợ. |
| Schema | Index, constraint, tên index và trạng thái xây dựng. | Backup theo cơ chế phù hợp và bản kê Cypher/schema riêng để đối soát. |
| Database `system` | User/role, cấu hình database metadata và thông tin quản trị được lưu trong database hệ thống theo kiến trúc. | Xác định **quy trình backup/restore riêng cho system database** theo phiên bản/edition; không suy ra từ backup một DB nghiệp vụ. |
| Neo4j configuration | Cấu hình server, memory, transaction log, TLS, routing, backup endpoint. | Bản kê cấu hình đã kiểm soát secret, IaC/Helm/GitOps. |
| Credential và khóa | Mật khẩu, private key, trust store, secret dùng mã hóa. | Secret manager/backup khóa tách biệt, quyền truy cập và kế hoạch rotation. |
| Plugin | APOC, GDS, custom procedure, binary và cấu hình. | Version pin, artifact đáng tin và ma trận tương thích. |
| Ứng dụng | Java Driver, SDN, Cypher query, service và config. | Build/deployment artifact, kiểm thử tích hợp và rollback ứng dụng. |
| Tích hợp | CDC offset, event IDs, outbox, broker retention, ETL checkpoint. | Kế hoạch điểm cắt và phát lại có idempotency. |
| Hạ tầng | DNS, LB, certificate, disk, PV/PVC, backup location. | IaC, sơ đồ topology, quyền/đường kết nối và thao tác phục hồi. |
| Monitoring/audit | Dashboard, alert, log correlation và bằng chứng thay đổi. | Lưu riêng phù hợp retention; không nhúng PII vào tài liệu diễn tập. |

**Nguyên tắc:** backup data store bảo vệ dữ liệu được bao phủ bởi cơ chế đó; cấu hình bên ngoài, secret và quy trình vận hành phải có nguồn khôi phục riêng. Nếu restore được database nhưng không thể giải mã backup, xác thực tài khoản hoặc kết nối được driver, mục tiêu hệ thống vẫn chưa đạt.

## 4. Chọn phương thức sao lưu theo deployment và edition

Không có một câu lệnh duy nhất cho mọi Neo4j.

| Phương thức | Đặc điểm | Khi nào cân nhắc | Điểm phải kiểm tra |
| --- | --- | --- | --- |
| **Offline dump** bằng công cụ Neo4j được hỗ trợ | Tạo bản dump khi database không phục vụ ghi theo yêu cầu công cụ/phiên bản. | Cơ sở dữ liệu nhỏ/trung bình, có cửa sổ bảo trì phù hợp hoặc môi trường staging. | Downtime, dung lượng tệp, định dạng dump, khả năng load và quyền OS. |
| **Online backup** (khi edition/phiên bản hỗ trợ) | Tạo backup qua cơ chế backup của Neo4j khi database đang hoạt động. | Production cần giảm downtime và có công cụ backup Enterprise phù hợp. | Cấu hình server/port, full/incremental, backup chain, quyền, tính nhất quán và phiên bản. |
| **Neo4j Aura backup/snapshot** | Quản lý qua console/API/chính sách dịch vụ. | Deployment được quản lý. | Gói dịch vụ, lịch, retention, export, PITR/restore nếu được hỗ trợ, vùng và quyền. |
| **Storage-level snapshot** | Chụp volume ở tầng CSI/cloud/storage. | Bổ sung chiến lược DR khi có quy trình application-consistent được chứng minh. | Tính nhất quán khi DB ghi, nhiều volume, transaction logs, restore test. |
| **Copy tập tin thủ công** | Sao chép thư mục store từ filesystem. | **Không dùng như backup online tự phát.** | Có thể tạo bản sao không nhất quán; cần công cụ/quy trình Neo4j được hỗ trợ. |

### 4.1. Offline dump và online backup không phải cùng một thứ

- **Offline dump** cần đáp ứng điều kiện database phải không chạy/không mở ghi theo hướng dẫn phiên bản. Nó có thể làm tăng downtime, nhưng quy trình thường rõ ràng khi tổ chức chấp nhận ngừng phục vụ.
- **Online backup** được thiết kế để chụp dữ liệu trong khi database vẫn nhận hoạt động theo cơ chế được hỗ trợ. Nó có thể tạo một backup chain cần nhiều phần để restore đúng điểm.
- **Snapshot** ở tầng storage có thể hữu ích cho hệ thống file, nhưng không được tự kết luận một snapshot của store và transaction logs là nhất quán nếu Neo4j vẫn đang ghi.

Kiểm tra **edition, version, quyền, backup path, quyền truy cập server, network và plugin** trước khi chọn. Community Edition không nên bị giả định có mọi tính năng online backup/cluster của Enterprise.

### 4.2. Cú pháp offline dump minh họa

Trên một **database thực hành đã dừng đúng cách**, với `neo4j-admin` của phiên bản hỗ trợ cú pháp tương ứng:

~~~bash
# Ví dụ minh họa: database đã dừng và đường dẫn backup có quyền ghi.
neo4j-admin database dump neo4j --to-path=/backup/drill-pre-upgrade
~~~

Lệnh chỉ dùng khi **điều kiện offline và phiên bản** cho phép. Đường dẫn `/backup/drill-pre-upgrade` là ví dụ; không đặt backup duy nhất trên cùng volume sắp bị nâng cấp/xóa. Cần lưu output, exit code, kích thước, checksum và tài liệu version backup.

Không chạy một lệnh `dump` “thử cho biết” trên database production đang hoạt động mà chưa xác minh nó được hỗ trợ trong trạng thái đó. Xác nhận cú pháp bằng:

~~~bash
neo4j-admin database dump --help
~~~

Các cờ và định dạng dump có thể khác theo Neo4j 4.x, 5.x và các dòng sau này. Lệnh dump **không** chứng minh khả năng restore; phải có bài diễn tập load và kiểm chứng dữ liệu.

### 4.3. Online backup theo Enterprise hoặc tính năng được cấp

Với Neo4j self-managed có hỗ trợ, hãy dùng **công cụ backup chính thức của chính phiên bản được triển khai**, xác định:

1. Database được chọn, danh tính server có thể phục vụ backup và endpoint backup.
2. Cơ chế full/incremental và khả năng restore từ backup chain.
3. Công cụ có cần log giao dịch hoặc metadata bổ sung khi restore không.
4. Giới hạn thời gian giữ, mã hóa, băng thông, I/O và tình huống cluster có thành viên không khỏe.
5. Quyền quản trị/backup, vị trí nhận dữ liệu và bằng chứng đã kết thúc thành công.

Không đưa một cú pháp `neo4j-admin database backup` cố định vào automation production nếu chưa kiểm tra option `--from`, `--to-path` và khả năng backup trên bản thực tế. Khi cần online backup, hãy lấy lệnh/Helm hook từ **Operations Manual đúng phiên bản** rồi chạy diễn tập trước.

### 4.4. Neo4j Aura

Với dịch vụ quản lý, backup, restore và khả năng khôi phục theo thời điểm có thể phụ thuộc **gói, khu vực và loại instance**. Một số thao tác được thực hiện qua Aura console/API thay vì `neo4j-admin`. Đội ứng dụng cần xác nhận:

- Gói hiện tại có cho tạo backup theo yêu cầu ngay trước maintenance không.
- Có thể tải/export dữ liệu hoặc restore thành một instance riêng để thử hay không.
- Thời gian lưu và điểm phục hồi cuối cùng có đáp ứng RPO không.
- Việc đổi phiên bản/khôi phục có yêu cầu mở ticket với nhà cung cấp không.

Không suy ra từ một bản managed instance rằng người dùng có SSH để đọc thư mục Neo4j hoặc tùy ý copy transaction logs.

## 5. Full, incremental và point-in-time: kiểm tra khả năng thật

### 5.1. Full backup

Full backup là điểm nền có thể dùng để phục hồi theo cơ chế và định dạng tương ứng. Nó có thể tốn dung lượng và thời gian lớn, nhưng giúp giảm phụ thuộc vào các chuỗi tăng dần quá dài.

### 5.2. Incremental backup

Incremental backup ghi phần thay đổi kể từ một mốc/backup trước theo cơ chế công cụ. Nó **không tự tồn tại độc lập** nếu cần full baseline và các phần của chuỗi backup để restore.

~~~text
Full F0
  |
  +---- Incremental I1
               |
               +---- Incremental I2
                            |
                            +---- Điểm restore mong muốn
~~~

Nếu `I1` bị mất/hỏng mà chuỗi cần nó, chỉ có `F0 + I2` chưa chắc đủ. Quy trình kiểm chứng phải kiểm **cả chain**, manifest/metadata, quyền và khả năng restore cuối chuỗi.

### 5.3. Point-in-time recovery (PITR)

Khôi phục đến một thời điểm/giao dịch cụ thể chỉ khả thi khi **edition, công cụ, backup/log chain và gói dịch vụ hỗ trợ cơ chế đó**. Đừng tuyên bố “còn transaction log nên có thể khôi phục mọi timestamp” nếu công cụ không cung cấp quy trình nhất quán và đã được thử.

Đối với nâng cấp, có thể cần hai mốc:

| Mốc | Ý nghĩa |
| --- | --- |
| **B0 – trước bảo trì** | Bản backup thường kỳ, đã kiểm chứng để biết đường khôi phục dài hạn. |
| **B1 – điểm cắt nâng cấp** | Bản sao cuối cùng sau khi đóng băng ghi hoặc theo cơ chế consistent backup đã thống nhất. |

Nếu nâng cấp lỗi trước khi mở lại traffic, B1 thường là ứng viên rollback rõ nhất. Nếu lỗi **sau khi mở lại ghi**, phải quyết định cách giữ/copy/phát lại những giao dịch sau B1 hoặc chấp nhận RPO đã phê duyệt; không được âm thầm vứt chúng.

## 6. Kiểm kê trạng thái Neo4j trước bảo trì

Một kế hoạch backup cần lưu **baseline** để khi restore biết so với điều gì. Sử dụng một tài khoản giám sát có quyền phù hợp.

### 6.1. Phiên bản và topology

Ghi lại **Neo4j server version**, edition, số database, topology cluster, plugin và phiên bản Java Driver/SDN. Cách kiểm tra version có thể thay đổi theo dòng Neo4j; trên những bản có procedure:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Trong những triển khai hạn chế quyền, lệnh có thể không chạy hoặc không hiển thị toàn bộ thông tin. Có thể lấy version từ công cụ quản trị/console đã được kiểm chứng thay vì cấp quyền thừa cho ứng dụng.

~~~cypher
SHOW DATABASES
YIELD name, currentStatus, requestedStatus
RETURN name, currentStatus, requestedStatus
ORDER BY name;
~~~

`SHOW DATABASES` giúp kiểm tra database online/offline; nó không đo dung lượng hoặc bảo đảm backup vừa tạo có thể restore.

### 6.2. Trạng thái index

~~~cypher
SHOW INDEXES
YIELD name, type, entityType,
      labelsOrTypes, properties, state,
      populationPercent
RETURN name, type, entityType,
       labelsOrTypes, properties, state,
       populationPercent
ORDER BY name;
~~~

Khi tạo baseline, ghi index nào đã `ONLINE`, `POPULATING` hoặc `FAILED`. Không tự coi trạng thái `POPULATING` trong restore là **mất dữ liệu**; nó có thể cần thêm thời gian xây dựng. Tuy nhiên, một truy vấn nghiệp vụ yêu cầu index đó có thể chậm hoặc không hoạt động theo giả định cho tới khi sẵn sàng.

### 6.3. Constraint và định danh nghiệp vụ

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

Những constraint trên key nghiệp vụ là điều kiện quan trọng: hai node mang cùng khóa hoặc node thiếu trường khóa có thể khiến ứng dụng hành xử sai dù database online.

### 6.4. Lưu bảng trước/sau

| Thành phần | Trước nâng cấp | Sau restore/nâng cấp | Chấp nhận khi |
| --- | --- | --- | --- |
| Database status | ONLINE | ... | Database ở trạng thái mong đợi. |
| Node/relationship theo loại chính | Số lượng tại cùng điểm cắt | ... | Khớp baseline hoặc giải thích chênh lệch có chứng cứ. |
| Constraint nghiệp vụ | Danh sách tên/type/property | ... | Không thiếu ràng buộc cần thiết. |
| Index | State/loại/properties | ... | Index quan trọng ONLINE và query dùng đúng. |
| Security | Quyền role/user và auth method | ... | Quyền thật được thử, không chỉ catalog giống tên. |
| Backup | Manifest, timestamp, checksum, location | ... | Bản sao đọc/restore được. |
| Ứng dụng | Driver/SDN, API smoke tests | ... | Truy vấn đọc/ghi/transaction đạt. |
| RPO/RTO | Mục tiêu được duyệt | Kết quả diễn tập | Không vượt mục tiêu. |

## 7. Tạo một fixture có thể kiểm chứng bằng Cypher

Để diễn tập trên **database test cô lập**, dùng label/type có tiền tố `UpgradeDemo`. Không nạp fixture lên database production khi chưa có sự cho phép và quy trình xóa an toàn.

### 7.1. Khóa định danh

~~~cypher
CREATE CONSTRAINT upgrade_demo_customer_key IF NOT EXISTS
FOR (c:UpgradeDemoCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT upgrade_demo_order_key IF NOT EXISTS
FOR (o:UpgradeDemoOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

Đây là uniqueness constraint theo cặp thuộc tính khi các giá trị có mặt. Nó **không tự bắt buộc** mọi thuộc tính khóa luôn tồn tại; khi production cần vừa bắt buộc tồn tại vừa duy nhất, đánh giá key/existence constraint theo edition/phiên bản và validate từ ứng dụng.

### 7.2. Dữ liệu mẫu

~~~cypher
MERGE (c:UpgradeDemoCustomer {
  tenantId: 'tenant-demo',
  customerId: 'C01'
})
SET c.name = 'Khách thử nghiệm'
MERGE (o1:UpgradeDemoOrder {
  tenantId: 'tenant-demo',
  orderId: 'O01'
})
SET o1.amountMinor = 125000,
    o1.status = 'PAID'
MERGE (o2:UpgradeDemoOrder {
  tenantId: 'tenant-demo',
  orderId: 'O02'
})
SET o2.amountMinor = 34000,
    o2.status = 'PENDING'
MERGE (c)-[:UPGRADE_DEMO_PLACED]->(o1)
MERGE (c)-[:UPGRADE_DEMO_PLACED]->(o2);
~~~

Chạy trên fixture sạch sẽ có một khách, hai đơn và hai relationship đúng chiều.

### 7.3. Oracle kiểm chứng phục hồi

~~~cypher
MATCH (c:UpgradeDemoCustomer {
  tenantId: 'tenant-demo',
  customerId: 'C01'
})
OPTIONAL MATCH (c)-[r:UPGRADE_DEMO_PLACED]->
               (o:UpgradeDemoOrder)
RETURN c.customerId AS customerId,
       count(r) AS relationshipCount,
       count(DISTINCT o) AS orderCount,
       sum(o.amountMinor) AS totalAmountMinor,
       collect(DISTINCT o.status) AS statuses;
~~~

Với dữ liệu minh họa, kỳ vọng:

| Kiểm tra | Giá trị mong đợi |
| --- | --- |
| `customerId` | `C01` |
| `relationshipCount` | `2` |
| `orderCount` | `2` |
| `totalAmountMinor` | `159000` |
| `statuses` | Chứa `PAID` và `PENDING` |

Kiểm tra một chiều ngược sai:

~~~cypher
MATCH (o:UpgradeDemoOrder)
      -[r:UPGRADE_DEMO_PLACED]->
      (c:UpgradeDemoCustomer)
WHERE o.tenantId = 'tenant-demo'
RETURN count(r) AS reversedRelationships;
~~~

Kết quả mong đợi `reversedRelationships = 0`. Một bản restore có đúng **hai node đơn** nhưng thiếu relationship hoặc tạo cạnh ngược chiều vẫn **không đạt**.

### 7.4. Không chỉ kiểm fixture

Trên hệ thống thực, tạo danh sách **invariant nghiệp vụ** đại diện:

- Mỗi Order phải có đúng một Customer thuộc cùng tenant khi nghiệp vụ yêu cầu.
- Không có hai node cùng khóa chính trong một tenant.
- Những trường số tiền/trạng thái đúng kiểu và giới hạn cho phép.
- Quan hệ quyền/thành viên đi đúng hướng và không tạo liên kết cross-tenant.
- Tổng số, thống kê theo loại/trạng thái và checksum có chuẩn hóa khớp **cùng điểm cắt**.
- Index/constraint cần thiết tồn tại và hoạt động.

Một count trùng nhau có thể che trường hợp “thiếu một đơn và thừa một đơn khác”. Cần đối chiếu theo khóa, thuộc tính và relationship ở những vùng dữ liệu quan trọng.

## 8. Runbook tạo backup trước nâng cấp

**Mục tiêu:** tạo bản sao độc lập, biết chính xác điểm dữ liệu nào được giữ và có thể restore trên môi trường phù hợp.

### Bước 1 — Chuẩn bị

Xác nhận:

- Nguồn Neo4j: database, server/cluster, edition/version, plugin và configuration.
- Mục tiêu nâng cấp: phiên bản đích, đường upgrade được hỗ trợ, các thay đổi schema/index và kế hoạch tương thích ứng dụng.
- RPO/RTO, cửa sổ bảo trì và chủ sở hữu thao tác.
- Tài khoản backup có quyền cần thiết nhưng không dư đặc quyền.
- Dung lượng đĩa nguồn/đích đủ cho backup, transaction logs, index population và tệp tạm.
- Vị trí backup độc lập failure domain, mã hóa, retention và quyền truy cập.
- Bản backup trước đó đã restore được hoặc có phương án bổ sung nếu chưa.

### Bước 2 — Thiết lập điểm cắt và kiểm soát writer

Tùy mô hình triển khai:

1. Công bố thời điểm bắt đầu bảo trì và yêu cầu ứng dụng giảm/tạm dừng mutation.
2. Ngăn job import, ETL, cron, CDC consumer và các đường ghi khác tiếp tục tạo dữ liệu **ngoài dự kiến** khi đã chốt điểm.
3. Đợi các transaction đang chạy hoàn tất hoặc xử lý theo quy tắc đã được phê duyệt; không giết vô điều kiện.
4. Ghi lại watermark/offset nguồn và trạng thái những sự kiện đã áp dụng trong Neo4j.
5. Chọn phương thức backup theo điều kiện online/offline tương ứng.

Không được coi “tắt API HTTP” là đã chặn tất cả writer: Java batch, admin scripts, queue consumer hoặc công cụ vận hành vẫn có thể ghi. Đối với backup online chạy trong khi ứng dụng tiếp tục ghi, phải chứng minh thời điểm và mức đảm bảo nhất quán của backup theo công cụ được hỗ trợ.

### Bước 3 — Chạy backup theo phương thức được hỗ trợ

Ghi lại tối thiểu:

| Thông tin | Ví dụ |
| --- | --- |
| `backupRunId` | `pre-upgrade-2026-11-25-a` |
| Database và instance | `neo4j` / `graph-node-1` |
| Version, edition | Chuỗi từ môi trường nguồn đã xác minh |
| Công cụ, phiên bản | Neo4j Admin tool/backup tool/gói Aura thực tế |
| Điểm cắt | Thời gian/watermark/transaction ID theo nguồn |
| Loại backup | Offline dump, full/incremental online, managed backup |
| Đích | Kho lưu được phê duyệt, **không ghi bí mật** |
| Kết quả | Exit code, log kết thúc, kích thước, checksum và lỗi |

Đặt mã backup trong tên artifact để tránh ghi đè nhầm. Không chỉ dựa vào dòng console “backup started”; xác nhận **kết thúc thành công** và mọi thành phần backup chain cần thiết đã có mặt.

### Bước 4 — Xác minh artifact

- Tệp/manifest không rỗng và có kích thước hợp lý theo baseline.
- Không có lỗi I/O, disk full, permission denied hoặc mạng đứt giữa chừng.
- Các phần của full/incremental chain có đầy đủ metadata.
- Kiểm tra checksum/hash phù hợp cho vận chuyển và lưu trữ; bản hash ở kho độc lập nếu cần.
- Khóa giải mã, credential/role phục hồi và binary công cụ khôi phục **có thể dùng** trong môi trường drill.
- Backup được copy ra khỏi failure domain của nguồn và có chính sách retention/xóa bảo vệ.

**Checksum chỉ chứng minh byte không đổi so với lúc tính hash; nó không chứng minh một backup có tính nhất quán ứng dụng hoặc có thể restore.**

### Bước 5 — Cập nhật hồ sơ và bảo vệ bản sao

Bản backup chuẩn bị cho rollback phải có:

- Người chịu trách nhiệm, thời gian tạo, trạng thái `READY_FOR_RESTORE_DRILL` hay `VERIFIED_RESTORABLE`.
- Đường dẫn/ID storage không chứa secrets, checksum, version và phạm vi database.
- Điểm cutover để biết giao dịch nào xảy ra trước/sau.
- Ngày hết hạn và ngoại lệ retention nếu cần giữ đến khi kết thúc giai đoạn theo dõi hậu nâng cấp.
- Kết quả diễn tập, bao gồm sai lệch/giới hạn phát hiện được.

## 9. Diễn tập restore trên môi trường cô lập

**Bước restore là phép kiểm tra trung tâm.** Không được thực hiện restore đè lên production chỉ để chứng minh backup dùng được.

### 9.1. Thiết kế môi trường drill

Một môi trường diễn tập phù hợp cần:

1. **Database/instance riêng**, namespace/VPC hoặc máy thử độc lập.
2. Phiên bản Neo4j **tương thích với định dạng backup/store**, theo quy trình được hỗ trợ.
3. CPU, RAM, disk, throughput và filesystem đủ tương đồng để đo RTO có ý nghĩa.
4. Kết nối outbound hạn chế: không gửi email, thanh toán, webhook hoặc event sang hệ thống thật.
5. Secret/certificate dùng cho drill, không vô tình dùng credential production cho các tích hợp bên ngoài.
6. Snapshot hoặc backup đầu vào được mount **read-only nếu cơ chế cho phép**, cùng thư mục đích trống hoặc được phê duyệt ghi đè.
7. Kịch bản kiểm thử dữ liệu tổng hợp hoặc dữ liệu đã được bảo vệ/anonymize nếu nguồn có PII.

Khi dùng dữ liệu thật để diễn tập, sao lưu vẫn chứa dữ liệu nhạy cảm, dù ở môi trường staging. Áp dụng cùng tiêu chuẩn mã hóa, giới hạn truy cập, nhật ký truy cập và xóa dữ liệu sau thử nghiệm.

### 9.2. Ví dụ restore từ dump offline

Trên một **instance test có database đích không chạy** và đã kiểm tra công cụ Neo4j tương ứng, các phiên bản Neo4j 5.x hỗ trợ mẫu lệnh gần như:

~~~bash
# Chỉ trên test host; đích "neo4j" đã dừng theo yêu cầu công cụ.
neo4j-admin database load neo4j \
  --from-path=/backup/drill-pre-upgrade
~~~

Hãy chạy:

~~~bash
neo4j-admin database load --help
~~~

trước khi triển khai để xác nhận option, quyền và định dạng tệp. Nếu database đích đã có nội dung, lệnh có thể báo không thể ghi đè; **không tự thêm option overwrite** khi chưa biết chắc đường dẫn đích/nguồn chứa dữ liệu gì. Đừng dựa vào cú pháp ví dụ để chạy restore có khả năng phá hủy môi trường thật.

Sau khi load hoàn tất, khởi động Neo4j theo quy trình phù hợp, chờ database đạt trạng thái được phép truy vấn rồi kiểm tra Cypher. **Load thành công không đồng nghĩa dữ liệu và ứng dụng đã đạt.**

### 9.3. Restore online backup hoặc managed backup

Đối với online backup/backup chain, sử dụng **command restore riêng của phiên bản** và đầy đủ manifest. Với Aura, dùng chức năng phục hồi sang instance test nếu gói cho phép. Cần ghi:

- Backup ID và chain đã dùng.
- Công cụ/lệnh/phiên bản phục hồi.
- Trạng thái transaction log apply/recovery theo công cụ.
- Thời gian load/restore, startup, index population.
- Những setting phải tái áp dụng (TLS, routing, auth, plugin, data source).
- Bằng chứng database sẵn sàng phục vụ sau restore.

**Không mở một backup Enterprise mới bằng một server cũ không được hỗ trợ** chỉ để thử rollback. Nếu store đã được nâng cấp, quy trình quay về phiên bản trước thường là **restore từ bản backup tạo trước nâng cấp bằng tool/version tương thích**, không hạ version engine tại chỗ.

## 10. Kiểm chứng dữ liệu phục hồi theo nhiều lớp

### 10.1. Lớp A — Database mở và hoạt động

Quan sát:

~~~cypher
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

Với database test, xác nhận `ONLINE` và kết nối Cypher thành công. Đây mới là **điểm bắt đầu**, chưa đủ để kết luận restore đạt.

### 10.2. Lớp B — Schema và index

So sánh danh mục `SHOW CONSTRAINTS`, `SHOW INDEXES` với baseline. Nếu một index đang `POPULATING`, phải chờ/đánh giá thời gian xây dựng và kiểm tra `ONLINE` cho các truy vấn quan trọng trước khi mở tải.

Đối với mỗi query cốt lõi:

~~~cypher
EXPLAIN
MATCH (o:UpgradeDemoOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
RETURN o.status AS status, o.amountMinor AS amountMinor;
~~~

Khi an toàn trên dữ liệu drill:

~~~cypher
PROFILE
MATCH (o:UpgradeDemoOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
RETURN o.status AS status, o.amountMinor AS amountMinor;
~~~

`EXPLAIN` không thực thi; `PROFILE` **thực thi** và báo thống kê theo plan. Với một upgrade có thay đổi planner/runtime/index provider, query vẫn đúng nhưng chi phí có thể tăng mạnh; đo Rows, DB Hits và độ trễ trên dữ liệu đại diện, không chỉ nhìn index catalog.

### 10.3. Lớp C — Nội dung nghiệp vụ và mối quan hệ

Kiểm tra:

- **Khóa:** node trùng/mất theo tenant và business ID.
- **Property:** kiểu dữ liệu, số tiền, trạng thái, timezone và nullability.
- **Cạnh:** type, chiều, endpoint đúng tenant và số relationship hợp lệ.
- **Deleted/tombstone:** bản ghi đã xóa hoặc soft-deleted không vô tình “sống lại” sau restore.
- **Quy tắc dữ liệu:** tổng theo trạng thái, đối chiếu nghiệp vụ và tập ID quan trọng.
- **Các trường hợp đặc biệt:** supernode, đa cạnh giữa hai node, value lớn, ký tự Unicode, temporal/spatial/vector nếu hệ thống dùng.

Truy vấn tìm một relationship nối sai tenant:

~~~cypher
MATCH (c:UpgradeDemoCustomer)
      -[r:UPGRADE_DEMO_PLACED]->
      (o:UpgradeDemoOrder)
WHERE c.tenantId <> o.tenantId
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       c.tenantId AS customerTenant,
       o.tenantId AS orderTenant
LIMIT 100;
~~~

Nếu mô hình quy định mọi đơn phải thuộc khách cùng tenant, kết quả mong đợi **0 hàng**. Nếu hệ thống thật có quan hệ xuyên tenant hợp lệ, phải điều chỉnh invariant thay vì áp dụng một quy tắc không đúng nghiệp vụ.

Truy vấn tìm đơn thiếu cạnh sở hữu:

~~~cypher
MATCH (o:UpgradeDemoOrder {tenantId: $tenantId})
WHERE NOT EXISTS {
  MATCH (:UpgradeDemoCustomer)-[:UPGRADE_DEMO_PLACED]->(o)
}
RETURN o.orderId AS orderId
LIMIT 100;
~~~

Đây là query phát hiện một loại thiếu liên kết; với nghiệp vụ có đơn không cần customer, loại trừ các trường hợp hợp lệ bằng bộ lọc rõ ràng.

### 10.4. Lớp D — Bảo mật và cấu hình

Kiểm tra cả quyền **thực tế**, không chỉ lệnh liệt kê role:

- Service account chỉ đọc có bị ngăn mutation không?
- Account ghi có truy cập được database đích và chỉ các label/property được phép không?
- Các query có lọc tenant và không rò rỉ thông tin giữa các tenant không?
- TLS/certificate, DNS và URI Bolt/routing có hợp lệ với ứng dụng drill không?
- Các user/role hoặc external auth có cần chuyển từ `system` database/cấu hình riêng không?
- Backup đã được bảo vệ ở nơi lưu và dữ liệu thử có bị lộ cho người ngoài quyền không?

### 10.5. Lớp E — Giao dịch mới sau restore

Một database chỉ đọc được vẫn có thể lỗi khi ghi do storage, quyền hoặc config. Trên môi trường drill:

1. Ghi một node/relationship thử bằng transaction.
2. Xác minh commit trả thành công và đọc lại từ session mới.
3. Restart database thử một cách có kiểm soát.
4. Đọc lại dữ liệu vừa commit.
5. Kiểm tra rollback khi chủ động ném lỗi trong transaction.

Đây là bước kiểm tra **độ bền và tính nguyên tử** tối thiểu; không thay thế các bài test crash recovery/storage chuyên sâu.

## 11. Kiểm tra bằng Java Driver và Spring Data Neo4j

Ứng dụng Neo4j thực tế thường không chỉ dùng Cypher trực tiếp. Sau restore hoặc upgrade, một API có thể lỗi vì driver không tương thích, URI/routing thay đổi, certificate mới hoặc mapping Spring Data Neo4j không còn khớp với schema.

### 11.1. Java Driver smoke test

Đoạn mã sau giả định một `Driver` đã được cấu hình tới **database drill** bằng secret và TLS thích hợp; không hardcode credential:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class RestoreSmokeTest {
    public static void verify(Driver driver) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            long matches = session.executeRead(tx ->
                tx.run("""
                    MATCH (c:UpgradeDemoCustomer {
                      tenantId: $tenantId, customerId: $customerId
                    })-[r:UPGRADE_DEMO_PLACED]->
                    (o:UpgradeDemoOrder)
                    RETURN count(r) AS count
                    """, Map.of(
                    "tenantId", "tenant-demo",
                    "customerId", "C01"
                )).single().get("count").asLong());

            if (matches != 2L) {
                throw new IllegalStateException(
                    "Restore invariant failed: expected 2 links");
            }
        }
    }
}
~~~

Ví dụ chỉ xác minh fixture; với ứng dụng thật cần tập assertion lớn hơn về node, thuộc tính, transaction, quyền, pagination và query quan trọng. Hãy kiểm tra **Java Driver, runtime Java và Spring Data Neo4j** trên ma trận tương thích với Neo4j version đích, không tự suy ra rằng chạy được một query là mọi tính năng đều ổn.

### 11.2. Spring Data Neo4j

Trong ứng dụng SDN, một test tích hợp nên:

- Tải entity node bằng repository theo khóa nghiệp vụ.
- Tải relationship có property nếu dùng `@RelationshipProperties`/`@TargetNode`.
- Kiểm tra hướng cạnh `OUTGOING`/`INCOMING` và việc không mất relationship khi save.
- Kiểm thử `@Transactional` với commit/rollback.
- Dùng query cập nhật hẹp nếu aggregate không tải đầy đủ, tránh vô ý xóa quan hệ sau restore.
- Thực thi migrations ứng dụng ở **môi trường diễn tập**, không chạy trực tiếp lên production chỉ để “xem có lỗi không”.

Một điều thường bị bỏ quên: sau nâng cấp database, ứng dụng vẫn có thể dùng **query cũ tạo kết quả khác về thứ tự nếu không có `ORDER BY`**. Test cần kiểm nghĩa nghiệp vụ, không chỉ so toàn bộ JSON mà bỏ qua thay đổi thứ tự không có cam kết.

## 12. Diễn tập nâng cấp trên bản đã restore

Khôi phục backup lên một môi trường cô lập giúp kiểm chứng **bản sao dùng được**. Nhưng mục tiêu “trước khi nâng cấp” còn cần diễn tập **chính upgrade trên bản đó**, thay vì thử lần đầu ở production.

~~~text
Production version A
        |
        +---- backup B1 ----> Drill A (version A)
                                  |
                                  | restore + verify baseline
                                  v
                             Upgrade A -> B
                                  |
                                  v
                       Verify graph/schema/app
                                  |
                          +-------+-------+
                          |               |
                         PASS            FAIL
                          |               |
                          v               v
                    Quy trình GO       NO-GO + sửa
~~~

### 12.1. Ma trận tương thích phải được phê duyệt

| Thành phần | Cần đối chiếu |
| --- | --- |
| Neo4j source/target | Đường nâng cấp được hỗ trợ, trung gian bắt buộc, store format migration. |
| Operating system/Java runtime | JDK/JVM/OS/container base image phù hợp phiên bản Neo4j. |
| Driver/SDN | Neo4j Java Driver và Spring Data Neo4j hỗ trợ server target. |
| APOC/GDS/custom plugins | Bản plugin khớp engine và API procedure; có thay đổi behavior không? |
| Cypher/schema | Query syntax, index/constraint, planner, deprecation và migration. |
| Cluster | Quorum, member topology, thứ tự nâng cấp, protocol và routing. |
| Backup/restore | Công cụ nào đọc được artifact nguồn; khả năng rollback về version A. |
| Security | Authentication/authorization, TLS và cách quản lý secret/role. |
| Hạ tầng | Heap/page cache, disk/headroom, log rotation, network/ports. |

Một đường nâng cấp **A → B** thành công với một database bé không chứng minh upgrade production khối lượng lớn sẽ kịp cửa sổ bảo trì. Đo cả thời gian store migration, khởi động, index population, kiểm tra dữ liệu và ứng dụng.

### 12.2. Sau nâng cấp drill, test những phần có rủi ro cao

1. **Mở database** trên version B, không bỏ qua cảnh báo migration/index.
2. **So sánh invariant** với bản drill trên version A tại cùng điểm cắt dữ liệu.
3. Kiểm `SHOW INDEXES`, `SHOW CONSTRAINTS` và query plans.
4. Chạy smoke test Java Driver, SDN/GraphQL/REST nếu dùng.
5. Đo p95/p99 query/transaction trên workload đại diện.
6. Thử restart server, backup mới trên B và restore backup B sang môi trường tương thích khác.
7. Thử **rollback bằng B1 trên version A**, không dùng store B đã migration để hạ version tại chỗ.
8. Ghi lại chênh lệch thời gian/memory/disk và cập nhật runbook.

Nếu không thể restore B1 về A do công cụ/định dạng/quyền không tương thích, **đường rollback chưa được chứng minh**; không được kết luận GO chỉ vì nâng cấp A → B thành công.

## 13. Điểm cắt dữ liệu và các writer bên ngoài

Một hệ thống thường có nhiều nguồn ghi:

~~~text
HTTP API ---------+
Batch import -----+--> Neo4j database
CDC consumer -----+
Scheduled job ----+
Admin Cypher -----+
~~~

Để có một điểm restore rõ ràng:

1. Liệt kê và tạm dừng/kiểm soát **mọi writer** thuộc phạm vi maintenance.
2. Xác định transaction nào đã commit và event/offset nguồn nào đã áp dụng.
3. Ghi lại watermark/changelog, bảng kiểm và thời điểm backup.
4. Đảm bảo backup B1 phản ánh trạng thái đã thống nhất; nếu online backup ghi đồng thời, dùng semantics của công cụ để xác định recovery point.
5. Với hệ thống liên quan broker, giữ đủ log/source snapshot để **phát lại idempotent** những event chưa được áp dụng.
6. Chỉ mở lại writer khi database B vượt qua các kiểm tra và kế hoạch rollback đã có giới hạn rõ.

### 13.1. Không tự nhận “backup nhất quán” vì count trùng

Giả sử hệ thống nguồn đang cập nhật:

~~~text
T0: Customer C1 có hai Order, tổng 159000
T1: Order O02 đổi amountMinor từ 34000 thành 39000
T2: CDC event đến Neo4j
T3: Backup Neo4j kết thúc
~~~

Nếu đọc nguồn ở T1 và Neo4j ở T0, hai bên có thể khác nhau dù pipeline không mất event. Đối soát phải so tại **cùng watermark** hoặc có cách đọc trạng thái theo phiên bản; không so hai hệ thống sống đang thay đổi tùy ý rồi kết luận backup sai.

### 13.2. Rủi ro ở điểm cutover

Ngay khi mở traffic tới database version B, những giao dịch mới có thể khiến rollback bằng B1 mất dữ liệu. Có thể giảm rủi ro bằng:

- **Khoảng canary** đọc trước khi mở ghi nếu sản phẩm cho phép.
- Chặn ghi trong giai đoạn xác minh đầu tiên, chỉ mở theo từng nhóm sau khi qua gate.
- Lưu event/outbox có khóa idempotency hoặc thiết kế phát lại có kiểm chứng.
- Ghi nhận **time/version của dữ liệu** mà ứng dụng đã đọc và mutation đã thực hiện.
- Định nghĩa điểm “không còn rollback nhanh về A” mà chỉ sửa tới hoặc fail-forward.

**Dual-write tự phát** lên cả version A và B dễ tạo hai hệ thống lệch nhau khi một bên commit còn một bên lỗi. Nếu kiến trúc cần dual-write, phải có giao thức xử lý thứ tự/idempotency, theo dõi lệch và khả năng hòa giải; không thêm như một giải pháp đơn giản mà chưa kiểm thử.

## 14. Phương án rollback: kỹ thuật và nghiệp vụ

Rollback phải trả lời bốn câu hỏi:

1. Khôi phục **bản nào** (backup ID, version, checksum, điểm cắt)?
2. Khôi phục **ở đâu** (máy/cluster/PVC/instance nào, quyền truy cập và đường kết nối)?
3. Mất hoặc phát lại **những giao dịch nào** đã xảy ra sau điểm cắt?
4. Ai **phê duyệt** chuyển traffic trở lại và xác nhận tính đúng của dữ liệu?

### 14.1. Mô hình quyết định

| Tình huống | Hướng xử lý | Rủi ro |
| --- | --- | --- |
| Nâng cấp lỗi trước khi mở ghi trên B | Restore B1 về môi trường A tương thích; test rồi chuyển traffic. | Thời gian restore, routing, config và các job còn gửi sự kiện. |
| B chạy được, chỉ một query ứng dụng lỗi | Có thể sửa query/driver hoặc rollback ứng dụng mà không đụng database nếu tương thích. | Phải xác nhận query cũ/driver cũ vẫn hỗ trợ server B. |
| B đã nhận ghi mới, nghi ngờ lỗi lớn | Đánh giá fail-forward hoặc rollback có phát lại giao dịch sau B1. | Không được âm thầm bỏ các thay đổi đã commit trên B. |
| Store B không tương thích A | Không mở store đó bằng A. Restore backup trước upgrade theo đường được hỗ trợ. | Downtime và mất dữ liệu nếu thiếu điểm cắt/failback. |
| Bản backup B1 không restore được | NO-GO nếu chưa nâng cấp; nếu đã nâng cấp cần kích hoạt phương án khắc phục theo thực tế. | Không có đường rollback được chứng minh. |
| Cluster mất quorum trong khi nâng cấp | Dừng thao tác tiếp theo, áp dụng runbook cluster đúng phiên bản. | Scale/restart không đúng có thể làm tình trạng xấu hơn. |

### 14.2. Phân biệt rollback với fail-forward

- **Rollback:** trở lại bản A/trạng thái B1 đã được xác minh, có thể phải bù hoặc phát lại giao dịch mới.
- **Fail-forward:** sửa cấu hình, ứng dụng, migration hoặc dữ liệu trên B để tiếp tục chạy phiên bản B.

Fail-forward đôi khi ít rủi ro mất dữ liệu hơn nếu B đã nhận nhiều ghi; rollback đôi khi phù hợp hơn khi chưa mở traffic. Quyết định thuộc người chịu trách nhiệm sự cố, dựa trên **RPO/RTO, ảnh hưởng nghiệp vụ và bằng chứng**.

## 15. Dung lượng và thời gian dành cho diễn tập

Một lần restore có thể cần **nhiều chỗ trống hơn kích thước file backup** vì phải giải nén, load store, ghi transaction logs, tạo index và giữ bản sao cũ.

| Hạng mục | Nhu cầu cần đo |
| --- | --- |
| File backup/dump | Kích thước artifact khi lưu trữ và sau giải nén nếu có. |
| Data store | Dung lượng node/relationship/property và metadata sau restore. |
| Index | Kích thước index và peak trong quá trình population/rebuild. |
| Transaction logs | Dung lượng khi apply/recovery hoặc nhận ghi mới. |
| Tệp tạm | Workspace import/restore, OS logs và công cụ migration. |
| Headroom | Dự phòng cho burst ghi, log rotation và rollback. |

### 15.1. Bài toán ngân sách minh họa

Giả sử sau restore vào môi trường thử:

- Store sử dụng 240 GiB.
- Index 45 GiB **không nằm trong giá trị store** ở nguồn đo này.
- Transaction logs và tệp tạm dự kiến đỉnh 80 GiB.
- Dự phòng an toàn 25% trên tổng nhu cầu trước dự phòng.

Khi các số liệu không chồng lấp, nhu cầu là `240 + 45 + 80 = 365 GiB`. Thêm 25% cho khoảng `456,25 GiB`. Đây là ví dụ về cách tính, **không phải mức mặc định Neo4j**. Nếu store metric đã bao gồm index thì phải trừ phần đếm trùng; nếu store và logs ở hai volume, lập ngân sách riêng cho từng volume.

### 15.2. Đo thời gian phục hồi theo thành phần

~~~text
RTO observed =
  phát hiện/escalate
  + cấp hạ tầng/secret/volume
  + lấy backup
  + load/restore/apply logs
  + database startup/recovery/index
  + xác minh dữ liệu/ứng dụng
  + chuyển DNS/routing/traffic
~~~

Một benchmark chỉ đo thao tác copy dump mà bỏ qua xác minh dữ liệu và chuyển traffic **không phải RTO đầy đủ**. Khi restore trên máy rất mạnh còn production DR chỉ có node nhỏ hoặc mạng chậm, số liệu diễn tập cần nêu giới hạn đại diện đó.

## 16. Bảo vệ backup trước tấn công và lỗi vận hành

Backup là bản sao chứa toàn bộ hoặc phần lớn dữ liệu nhạy cảm: PII, mối quan hệ khách hàng, giao dịch và có thể metadata quản trị. Bảo vệ nó tương đương hoặc chặt hơn database trực tuyến.

### 16.1. Các kiểm soát bắt buộc

- **Mã hóa:** khi truyền và khi lưu, với khóa được quản lý trong kho thích hợp.
- **Tách quyền:** người chạy backup không mặc nhiên có quyền xóa mọi bản cũ; người đọc log không có quyền tải dump chứa PII.
- **Vị trí:** có bản sao nằm ngoài failure domain của database và cluster đang nâng cấp.
- **Tính bất biến:** cân nhắc object lock/retention hoặc kho append-only phù hợp để giảm nguy cơ ransomware/xóa nhầm.
- **Kiểm toán:** ai tạo, truy cập, tải, restore hoặc xóa backup, thời gian và lý do.
- **Retention:** thời gian giữ trước/sau nâng cấp rõ ràng, bao gồm quy tắc xóa dữ liệu nhạy cảm trong môi trường drill.
- **Khóa giải mã:** có cơ chế khôi phục khóa bí mật và chứng minh có thể mở bản backup khi nguồn chính không còn.

### 16.2. Không để diễn tập gây tác động thật

Môi trường đã restore từ production có thể chứa:

- Email, số điện thoại và địa chỉ thật.
- Queue/outbox event “chưa gửi” có thể được job gửi lại.
- Webhook URL, API key và credential kết nối hệ thống bên ngoài.
- Các job lịch chạy định kỳ.

Trước khi mở ứng dụng trên môi trường drill:

1. Ngắt hoặc giả lập các tích hợp ghi ra bên ngoài.
2. Dùng secret và endpoint dành riêng cho môi trường thử.
3. Tắt scheduler/worker gửi sự kiện thật; gắn cờ read-only/test theo chính sách.
4. Hạn chế quyền truy cập dữ liệu phục hồi.
5. Có kế hoạch xóa an toàn dữ liệu drill sau khi đã thu bằng chứng kiểm thử.

**Restore thành công rồi vô tình gửi hàng nghìn email/thanh toán thật là một sự cố**, không phải diễn tập đạt.

## 17. Test matrix trước nâng cấp

Không cần cố tình làm hỏng production để đánh giá khả năng phục hồi. Dùng môi trường cô lập và backup đã phê duyệt.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| U01 | Backup thành công và artifact hiện diện. | Có exit status, manifest/checksum, kích thước và địa điểm độc lập. |
| U02 | Restore từ full backup sang instance test. | Database ONLINE, query đọc và ghi hoạt động. |
| U03 | Restore từ full + incremental chain. | Đầy đủ các phần, đúng điểm phục hồi dự kiến. |
| U04 | Thiếu một incremental trong chain. | Phát hiện restore không đầy đủ; **không** đánh dấu đạt. |
| U05 | Sai/thiếu khóa giải mã hoặc credential. | Báo BLOCKER rõ ràng, có đường khôi phục khóa hợp lệ. |
| U06 | Backup bị truncate/corrupt trong test. | Phát hiện qua công cụ/checksum/restore; không mở traffic. |
| U07 | Dữ liệu fixture có node và relationship properties. | Đúng khóa, giá trị, hướng, số cạnh và bất biến. |
| U08 | Index đang POPULATING sau restore. | Đợi index quan trọng ONLINE và đo truy vấn trước khi GO. |
| U09 | Một constraint/key quan trọng thiếu sau restore. | Đối soát catalog phát hiện; không tuyên bố dữ liệu sẵn sàng. |
| U10 | Đọc/ghi và rollback transaction bằng Java Driver. | Commit bền vững và rollback giữ bất biến. |
| U11 | Spring Data Neo4j load/save relationship properties. | Không mất property/cạnh vì mapping hoặc query load chưa đủ. |
| U12 | Role chỉ đọc và role ghi. | Quyền đúng sau restore, tenant không bị lộ dữ liệu. |
| U13 | Giả lập driver mất kết nối khi commit. | Có idempotency/tra cứu kết quả; không tự nhân đôi side effect. |
| U14 | Upgrade drill trên data đã restore. | Hoàn tất đường migration được hỗ trợ; ứng dụng và query đạt. |
| U15 | Thử rollback trên version trước upgrade. | Bản backup B1 restore được mà **không** dùng store đã upgrade. |
| U16 | CDC/batch đang còn event chưa áp dụng. | Watermark được ghi rõ; không mất hoặc phát lại trùng sau cutover. |
| U17 | Hệ thống staging thiếu tài nguyên. | Đo RTO/chi phí thực; không giấu nguyên nhân timeout/thiếu đĩa. |
| U18 | Một replica/primary lỗi trong thử nghiệm cluster. | Áp dụng đúng quy trình quorum và restore/catch-up; không tự xóa PVC. |
| U19 | Mất log/metrics trong lúc drill. | Đánh dấu thiếu bằng chứng, có alert; không coi mất log là “không lỗi”. |
| U20 | Backup quá thời hạn lưu hoặc bị xóa nhầm. | Chính sách retention/tính bất biến phát hiện và có bản sao dự phòng. |
| U21 | Dữ liệu drill có outbound integration. | Không phát tán email/webhook/payment thật. |
| U22 | Phục hồi dưới tải và sau restart. | Kiểm RPO/RTO, transaction, query p95/p99 và index readiness. |

### 17.1. Kết luận test phải có số liệu

Một báo cáo diễn tập tối thiểu:

| Mục | Ví dụ cách ghi |
| --- | --- |
| Test ID | `U15` |
| Source backup | `pre-upgrade-2026-11-25-a` |
| Source version / target test version | Chuỗi đã kiểm tra thật |
| Thời điểm dữ liệu được phục hồi | Watermark hoặc timestamp được công cụ xác nhận |
| Phương án | Offline dump/online backup/managed restore |
| Thời gian phục hồi đo được | Tổng từ bắt đầu xử lý sự cố giả lập đến service ready |
| Kiểm tra graph/schema | Số lượng, checksum, invariant, index/constraint |
| Kiểm tra ứng dụng | Java Driver/SDN/API smoke/load tests |
| Kết quả | PASS / FAIL / BLOCKED, có giải thích |
| Người phê duyệt | Owner của database và ứng dụng |

Không dùng nhận xét chung “restore OK” mà không lưu **thời điểm, dữ liệu, công cụ và kết quả kiểm thử**.

## 18. Runbook nâng cấp có điểm dừng rõ ràng

### Giai đoạn A — Trước cửa sổ bảo trì

1. Xác minh version/edition, đường upgrade và ma trận tương thích.
2. Inventory database, schema, system/security config, plugin, driver, integration.
3. Chụp baseline dữ liệu, query, index và KPI.
4. Tạo backup B0 theo chính sách; restore drill và xác minh.
5. Diễn tập upgrade từ A lên B trên dữ liệu đã restore.
6. Thử rollback về A **từ bản sao trước upgrade**.
7. Đo RPO/RTO và xác nhận capacity, quyền, secret, runbook.
8. Phê duyệt GO với owner/nhóm trực sự cố được chỉ định.

### Giai đoạn B — Trong cửa sổ bảo trì

1. Thông báo bảo trì, kiểm tra health/backup gần nhất và khả năng hỗ trợ.
2. Tạm dừng writer và job tích hợp theo kế hoạch; drain transaction.
3. Ghi checkpoint/watermark và **tạo backup B1 cuối**.
4. Xác minh B1 đọc được và ghi nhận điểm cắt; giữ B0 độc lập.
5. Thực hiện upgrade theo runbook của **phiên bản thật**, không bỏ qua cảnh báo.
6. Kiểm tra database, index, constraint, graph, quyền, Java/SDN và transaction.
7. Chỉ mở traffic khi các gate đều PASS; nếu không, kích hoạt quyết định rollback/fail-forward theo phạm vi.

### Giai đoạn C — Sau khi mở traffic

1. Canh p95/p99, query error, transaction rollback, index FAILED, disk/log growth.
2. Theo dõi CDC lag, job tích hợp và idempotency khi replay.
3. Đối chiếu các bản ghi thay đổi sau B1 để biết khả năng rollback còn lại.
4. Tạo/kiểm thử backup trên version B theo chính sách.
5. Đóng change khi hoàn tất thời gian quan sát, có biên bản kết quả và retention cho B1.

**Không bỏ qua backup B1 chỉ vì B0 đã được thử hôm trước.** Sau B0, dữ liệu có thể đã thay đổi; điểm rollback cần phù hợp cửa sổ nâng cấp và RPO.

## 19. GO/NO-GO và vai trò phê duyệt

| Điều kiện | GO khi | NO-GO khi |
| --- | --- | --- |
| Khả năng restore | Backup B1/B0 có artifact và đường restore đã được kiểm chứng. | Chưa có diễn tập hoặc mất khóa/backup chain. |
| RPO/RTO | Kết quả drill đạt hoặc ngoại lệ đã phê duyệt bằng văn bản. | Restore quá lâu hoặc điểm khôi phục không đạt yêu cầu. |
| Tương thích | Có đường nâng cấp hợp lệ cho server, driver, plugin, schema. | Phiên bản/edition/plugin không tương thích hoặc không rõ. |
| Dữ liệu | Node/relationship/property, constraint và bất biến đạt. | Chỉ kiểm database ONLINE mà chưa kiểm dữ liệu. |
| Writers | Đã kiểm soát API, batch, CDC, admin và checkpoint. | Vẫn có nguồn ghi không xác định có thể làm lệch điểm cắt. |
| Rollback | Biết restore bản nào về A và xử lý giao dịch sau điểm cắt. | Chỉ có kế hoạch “đổi image/tag cũ”. |
| Bảo mật | Secret, quyền, TLS, tenant, backup encryption đúng. | Backup lộ PII/credential hoặc staging có thể gửi sự kiện thật. |
| Capacity | Đủ nơi lưu backup, restore, index, log, headroom. | Disk gần đầy, không đủ chỗ hoặc volume không thể mở rộng. |
| Observability | Có monitoring, alert, owner và tiêu chí dừng. | Không thể đo lỗi hoặc không có người chịu trách nhiệm. |
| Cluster | Quorum, member health, backup source và kế hoạch thứ tự upgrade đã được thử. | Chỉ dùng lệnh rolling restart Kubernetes mà không xét Neo4j cluster. |

**GO không đồng nghĩa không có rủi ro.** Nó nghĩa là các rủi ro quan trọng đã được nhận diện, có kiểm soát, có bằng chứng thử nghiệm và có người chịu trách nhiệm khi quy trình phải dừng.

## 20. Lỗi thường gặp khi chuẩn bị backup nâng cấp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ kiểm `ls backup-file` thấy tệp tồn tại. | Backup có thể lỗi hoặc không restore được. | Thử restore, query dữ liệu và giao dịch. |
| Copy store directory khi Neo4j đang ghi. | Bản sao có thể không nhất quán. | Dùng offline dump/online backup hoặc snapshot nhất quán được hỗ trợ. |
| Giữ backup duy nhất trên cùng PVC/volume. | Lỗi volume hoặc xóa PVC làm mất cả nguồn và backup. | Lưu độc lập failure domain, mã hóa và retention. |
| Không backup/kiểm kê `system`, role và config. | Database phục hồi nhưng quyền/ứng dụng không hoạt động. | Inventory đầy đủ và kế hoạch khôi phục riêng theo version. |
| Restore trên production để “test”. | Có thể ghi đè dữ liệu thật. | Dùng instance/database drill cô lập. |
| Không chặn CDC/batch writer. | Điểm cắt không rõ hoặc có event ghi thêm. | Ghi watermark và kiểm soát tất cả writer. |
| Chỉ test số node. | Relationship sai/mất, property lệch nhưng count vẫn đúng. | Kiểm invariant và so theo khóa/phiên bản. |
| Chỉ thấy index tồn tại. | Index có thể FAILED/POPULATING hoặc query plan tệ. | Kiểm state và `EXPLAIN`/`PROFILE`. |
| Chỉ đo thời gian copy backup. | Đánh giá RTO quá lạc quan. | Tính cả startup, index, app, DNS và verify. |
| Hạ image về bản cũ sau store migration. | Engine cũ có thể không đọc được store mới. | Restore bản trước nâng cấp bằng công cụ/phiên bản tương thích. |
| Không xét ghi mới sau cutover. | Rollback gây mất dữ liệu đã commit. | Chính sách fail-forward/replay/RPO rõ ràng. |
| Backup không có khóa giải mã hoặc quyền đọc. | Có dữ liệu nhưng không sử dụng được lúc khẩn cấp. | Diễn tập với chính người/quyền DR và nguồn khóa dự phòng. |
| Bật toàn bộ job của staging sau restore. | Gửi email/webhook/thanh toán thật. | Cách ly outbound, secret và scheduler. |
| Chỉ test single node khi production có cluster. | Không phát hiện lỗi quorum/routing/replica. | Diễn tập theo topology/phiên bản production. |
| Mặc định snapshot PVC là backup Neo4j nhất quán. | Restore lỗi vì store/log chụp lệch thời điểm. | Dùng quy trình supported và verify thực tế. |

## 21. Bài tập thực hành

**Bài 1 — Định nghĩa phục hồi.** Hệ thống phải đạt RPO 10 phút và RTO 45 phút. Một bản full backup được tạo 2 giờ trước, restore mất 35 phút, nhưng không có cơ chế áp dụng thay đổi sau backup. Hãy đánh giá từng mục tiêu và đề xuất phương án cải thiện.

**Bài 2 — Khác nhau giữa dump và backup.** Một môi trường Community chỉ có thể chấp nhận ngừng dịch vụ 90 phút, môi trường Enterprise cần backup trong lúc hệ thống hoạt động. Hãy so sánh offline dump và online backup dựa vào tính năng được hỗ trợ, downtime, công cụ, backup chain và restore drill.

**Bài 3 — Đối soát graph.** Dùng fixture ở mục 7, tạo bản dump/backup trên môi trường học tập, restore sang database test và kiểm tra `relationshipCount`, `totalAmountMinor`, chiều cạnh và hai uniqueness constraint. Giải thích vì sao node count đúng chưa đủ.

**Bài 4 — Backup chain hỏng.** Full `F0` còn nguyên, incremental `I1` bị mất, `I2` vẫn tồn tại. Hãy lập quyết định: điểm nào có thể phục hồi chắc chắn, dữ liệu nào chưa chứng minh được và hệ thống phải làm gì để không báo RPO sai.

**Bài 5 — Rollback sau ghi mới.** B1 được chụp lúc 00:00. Nâng cấp hoàn tất 00:30; từ 00:30 đến 01:00 có 1.000 đơn hàng mới. Lúc 01:00 phát hiện một lỗi nghiêm trọng. Hãy chọn rollback hoặc fail-forward, phân tích rủi ro dữ liệu, event/outbox và sự cần thiết của phê duyệt nghiệp vụ.

**Bài 6 — Chọn môi trường DR.** Production dùng Neo4j cluster và plugin GDS/APOC, nhưng môi trường drill chỉ có một instance nhỏ không cài plugin. Hãy nêu những bài test vẫn có giá trị, những kết luận **không được** rút ra và cách thiết kế rehearsal đại diện hơn.

**Bài 7 — Dung lượng.** Store cần 240 GiB, index 45 GiB chưa nằm trong store, log/temp peak 80 GiB và headroom 25%. Tính nhu cầu lưu trữ; nếu store/index ở volume A nhưng log ở volume B, hãy tách yêu cầu và giải thích vì sao tổng GB không đủ đánh giá.

**Bài 8 — Khôi phục sai quyền.** Sau restore, database ONLINE nhưng user chỉ đọc lại có quyền ghi do cấu hình security khác nguồn. Viết ma trận kiểm thử authorization, role chồng lấn, tenant và secret rotation trước khi GO.

**Bài 9 — Lỗi ứng dụng sau nâng cấp.** Neo4j phiên bản B trả Cypher bình thường, nhưng Spring Data Neo4j ánh xạ thiếu relationship properties. Hãy liệt kê các bài test ở entity, repository, driver, schema và query để phân biệt lỗi mapping với lỗi backup dữ liệu.

**Bài 10 — Viết runbook.** Soạn lịch trình T-7 ngày, T-1 ngày, T-1 giờ, T0, T+30 phút và T+1 ngày cho một nâng cấp có downtime. Ghi artifact cần lưu, gate GO/NO-GO, điểm rollback, người phụ trách và bằng chứng hoàn thành.

## 22. Checklist trước khi nhấn nút nâng cấp

1. **Phạm vi rõ:** biết database, Neo4j source/target version, edition, cluster, plugin, Java Driver và Spring Data Neo4j.
2. **Đường nâng cấp hợp lệ:** đã đối chiếu ma trận hỗ trợ, store compatibility, thứ tự nâng cấp và những bước trung gian bắt buộc.
3. **RPO/RTO được duyệt:** có mục tiêu cụ thể và kết quả restore drill đáp ứng hoặc ngoại lệ được chấp nhận.
4. **Backup có thể phục hồi:** không chỉ có file; đã restore, mở DB, kiểm graph và transaction.
5. **Backup chain đầy đủ:** full/incremental/log/metadata theo phương thức được hỗ trợ, checksum và khóa sẵn sàng.
6. **Điểm cắt rõ:** mọi writer, queue, CDC và transaction in-flight đã được kiểm soát hoặc có chính sách nhất quán.
7. **Không thiếu phần ngoài database:** system/security metadata, config, secret, plugin, driver, IaC và TLS có đường phục hồi riêng.
8. **Bản sao độc lập:** backup không cùng một failure domain, có mã hóa, quyền tối thiểu và retention thích hợp.
9. **Đã diễn tập nâng cấp:** thử A → B trên bản restore, kiểm schema/index/constraint và workload ứng dụng.
10. **Rollback có thật:** đã thử B1 → A bằng quy trình tương thích; không cố downgrade store tại chỗ.
11. **Đã xét ghi sau cutover:** không bỏ quên dữ liệu phát sinh trên version mới và cách phát lại/idempotency.
12. **Có kế hoạch vận hành:** capacity, monitoring, owner, cửa sổ bảo trì, thông báo và thời điểm ra quyết định dừng.
13. **Drill cô lập:** không sử dụng credential/integration thật để gửi message, email hoặc thanh toán ngoài ý muốn.
14. **Đủ bằng chứng:** báo cáo backup ID, version, thời điểm, RPO/RTO, kết quả kiểm tra và người phê duyệt.
15. **Sau nâng cấp vẫn được backup:** có lịch backup trên version mới, restore test và theo dõi hậu triển khai.

**Kết luận:** sao lưu trước nâng cấp không chỉ là chạy một lệnh `dump` hoặc bấm tạo snapshot. Một kế hoạch đáng tin cậy phải **xác định điểm cắt dữ liệu, sử dụng cơ chế sao lưu được phiên bản/edition hỗ trợ, lưu bản sao an toàn, diễn tập restore trên môi trường cô lập, kiểm chứng property graph và ứng dụng, rồi mới phê duyệt nâng cấp**. Khi hiểu rõ RPO/RTO, khả năng tương thích store, dữ liệu phát sinh sau cutover và đường rollback, đội vận hành mới có thể quyết định tiếp tục, dừng hoặc khôi phục mà không đánh đổi tính đúng đắn của Neo4j.

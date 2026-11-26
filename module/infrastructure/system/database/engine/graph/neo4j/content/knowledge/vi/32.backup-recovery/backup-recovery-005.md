# Kiểm tra tính nhất quán và khả năng sử dụng của bản sao

## 1. Một tệp backup tồn tại không có nghĩa là đã có khả năng phục hồi

Trong hệ thống **DATABASE_ENGINE_GRAPH_NEO4J**, các node, relationship, index, constraint và transaction tạo thành dữ liệu phục vụ ứng dụng Java Driver, Spring Data Neo4j và những truy vấn Cypher. Khi hệ thống gặp lỗi ổ đĩa, thao tác xóa nhầm, tấn công mã hóa dữ liệu hoặc nâng cấp thất bại, bản sao lưu (*backup*) chỉ có giá trị nếu có thể **khôi phục thành một database nhất quán, khởi động được và trả kết quả đúng cho ứng dụng**.

Hãy phân biệt các trạng thái dễ bị đánh đồng:

1. **Backup job báo thành công:** quá trình sao lưu kết thúc theo quy tắc của công cụ.
2. **Artifact tồn tại và truy cập được:** tệp hoặc tập tệp có thể liệt kê, đọc và tải xuống.
3. **Chuỗi backup hợp lệ:** có full backup và các differential cần thiết, cùng database ID, với khoảng transaction nối tiếp đúng.
4. **Kiểm tra consistency đạt:** cấu trúc lưu trữ graph, index và các thành phần được kiểm tra không có lỗi được công cụ phát hiện.
5. **Restore thành công:** backup tạo được database trên một Neo4j mục tiêu hợp lệ.
6. **Ứng dụng dùng được:** database lên trạng thái phục vụ; dữ liệu, quyền truy cập, truy vấn và những quy tắc nghiệp vụ trọng yếu đều đạt.

Một hệ thống có thể đạt bước 1–2 nhưng thất bại ở bước 3, hoặc đạt consistency check nhưng thiếu các relationship nghiệp vụ do dữ liệu đã sai **trước khi backup**. Vì vậy, mục tiêu của bài học thuộc chương **Sao lưu và phục hồi** là tạo ra **bằng chứng phục hồi được**, không chỉ tạo ra một tệp có đuôi **.backup**.

> **Nguyên tắc an toàn:** Tất cả ví dụ restore, aggregation và consistency check trong bài đều dành cho **môi trường thử nghiệm cô lập**. Không dùng tùy chọn ghi đè database sản xuất, không xóa các tệp của chuỗi backup gốc và không khởi động trực tiếp một bản sao chưa kiểm chứng để phục vụ lưu lượng thật.

## 2. Cần kiểm tra những lớp nào?

| Lớp kiểm tra | Câu hỏi | Bằng chứng / công cụ |
|---|---|---|
| **Inventory** | Có bản sao của đúng database, đúng thời điểm? | Danh sách artifact, kích thước, backup job ID, timestamp |
| **Metadata & chain** | Full/differential có cùng database ID và khoảng transaction phù hợp? | **neo4j-admin backup inspect** |
| **Artifact integrity** | Tệp bị cắt cụt, thay thế hoặc lỗi truyền tải không? | Checksum/hash độc lập, kiểm tra tải và truy cập tệp |
| **Physical consistency** | Node/relationship/property/index/count-store có cấu trúc hợp lệ? | **neo4j-admin database check** |
| **Restore drill** | Có thể phục hồi, replay log và đưa database lên ONLINE? | **neo4j-admin database restore**, **CREATE DATABASE**, **SHOW DATABASES** |
| **Logical/business integrity** | Graph vẫn đáp ứng quy tắc nghiệp vụ? | Assertion Cypher về định danh, số lượng, hướng quan hệ và tenant |
| **Application usability** | Java Driver/SDN truy vấn được với quyền và schema thích hợp? | Smoke/integration tests, auth, index state, latency |
| **Recoverability/SLO** | Có phục hồi trong thời gian và mức mất dữ liệu đã cam kết? | RPO/RTO đo từ diễn tập, log, báo cáo đối soát |

**Consistency check không thay thế business validation.** Một node **Order** thiếu mối quan hệ tới **Customer** vẫn có thể là cấu trúc graph hợp lệ về mặt lưu trữ. Công cụ không biết hệ thống của bạn yêu cầu mỗi Order phải gắn đúng một Customer.

**Restore drill cũng không thay thế consistency check.** Một database có thể khởi động và trả vài truy vấn đơn giản trong khi một thành phần index hoặc một vùng dữ liệu ít được truy cập có lỗi chưa bị phát hiện.

### 2.1. Bản sao lưu khác bản replica

**Backup artifact** là vật liệu phục hồi được quản lý tách khỏi database đang hoạt động. **Cluster replica/secondary** là thành viên phục vụ sao chép và truy vấn, không mặc nhiên là một bản backup độc lập: lỗi logic, xóa dữ liệu và thay đổi sai có thể được sao chép sang replica.

Không sử dụng “cụm có ba thành viên” làm bằng chứng đủ để bỏ lịch backup. Nếu cần phục hồi trạng thái trước một lệnh xóa nhầm đã commit, replica bình thường có thể đã nhận chính thay đổi sai đó.

## 3. Xác định RPO, RTO và điểm phục hồi cần kiểm tra

- **RPO — Recovery Point Objective:** mức mất dữ liệu tối đa có thể chấp nhận; ví dụ muốn phục hồi tới trạng thái cách sự cố không quá **15 phút**.
- **RTO — Recovery Time Objective:** tổng thời gian tối đa từ khi bắt đầu sự cố đến khi dịch vụ phục hồi sử dụng được; ví dụ **60 phút**.
- **Recovery point thực tế:** transaction/timestamp cuối cùng hiện diện trong **backup chain đã xác minh**, không chỉ thời điểm job bắt đầu.

Giả sử backup full hoàn tất lúc 01:00, differential cuối cùng chứa dữ liệu đến 01:45, còn sự cố xảy ra 02:00. Nếu restore tới 01:45, mức mất dữ liệu theo thời gian là khoảng **15 phút**. Muốn tuyên bố đạt RPO, phải chứng minh **01:45 đúng là điểm transaction được phục hồi** chứ không chỉ là tên tệp có chuỗi ngày giờ đó.

Tương tự, RTO không chỉ là thời gian chạy lệnh **restore**. Nó còn gồm lấy artifact từ storage, giải mã, khôi phục transaction, khởi động database, kiểm tra quyền, điều chỉnh kết nối ứng dụng và chạy smoke tests.

Một bản sao **consistent và restore được** nhưng chỉ phục hồi xong sau 4 giờ vẫn có thể không đáp ứng RTO 1 giờ của hệ thống.

## 4. Hiểu đúng loại backup và các giới hạn theo edition

Neo4j cung cấp cơ chế sao lưu khác nhau theo edition:

| Cơ chế | Phạm vi điển hình | Điều cần nhớ khi kiểm tra |
|---|---|---|
| **Online backup** qua **neo4j-admin database backup** | **Enterprise Edition** tự quản lý | Có full/differential artifact; cần backup service, nguồn và quyền phù hợp |
| **Offline dump** qua **neo4j-admin database dump** | Bao gồm các tình huống Community | Database nguồn phải không được sử dụng khi dump; kiểm tra dump/restore theo quy trình của bản chạy |
| **Backup dịch vụ quản lý** | Ví dụ Neo4j Aura | Sử dụng tính năng snapshot/restore, retention và giới hạn do nhà cung cấp công bố |
| **Filesystem/snapshot hạ tầng** | Phụ thuộc cách tổ chức triển khai | Chỉ là backup được hỗ trợ nếu có quy trình snapshot nhất quán cho store và transaction log |

Trong **Enterprise**, một backup **full** chứa cơ sở dữ liệu nền cần thiết để phục hồi. Một backup **differential** chứa các transaction mới so với điểm phù hợp trước đó và **không phải một database độc lập để kiểm tra consistency trực tiếp**.

**Không sao chép nóng thư mục data và transaction logs bằng thao tác copy file tùy ý** rồi mặc định có một bản backup nhất quán. Cơ chế backup của Neo4j cần phối hợp dữ liệu lưu trữ và các transaction đang diễn ra.

### 4.1. Ví dụ online backup — chỉ dùng khi có server và quyền tương ứng

~~~bash
# Ví dụ trên máy backup client Neo4j Enterprise.
# Thay địa chỉ bằng backup endpoint được quản trị viên công bố.
bin/neo4j-admin database backup \
  --from=backup-server.example:6362 \
  --to-path=/srv/neo4j-backups \
  --type=FULL \
  neo4j
~~~

Đây là **mẫu cú pháp**, không phải lệnh đã được thực thi trong bài. Địa chỉ và cổng backup phải được cấu hình và cho phép truy cập; chạy bằng tài khoản hệ điều hành thích hợp theo hướng dẫn. Dùng **--type=FULL** để minh họa một điểm nền; những lần backup tiếp theo có thể tạo **DIFF** hoặc **AUTO** theo chính sách.

Trên môi trường **Aura**, người dùng không tự chạy lệnh này trên máy chủ của dịch vụ. Hãy theo tài liệu backup/restore của gói Aura cụ thể.

## 5. Tầng 1 — Kiểm tra danh sách và metadata của backup

### 5.1. Đọc metadata bằng lệnh inspect

Trên **Neo4j Enterprise hiện hành**:

~~~bash
bin/neo4j-admin backup inspect /srv/neo4j-backups
~~~

Chỉ xem **chuỗi backup mới nhất** của database neo4j:

~~~bash
bin/neo4j-admin backup inspect /srv/neo4j-backups \
  --database=neo4j --latest-chain
~~~

Có thể sử dụng **--format=JSON** để một công cụ kiểm thử đọc metadata có cấu trúc, thay vì parse bảng văn bản có thể đổi format.

Những trường nên lưu lại trong báo cáo:

| Trường metadata | Câu hỏi kiểm tra |
|---|---|
| **DATABASE** | Đúng tên database định phục hồi? |
| **DATABASE ID** | Các mảnh full/differential thuộc cùng database thực, hay chỉ trùng tên? |
| **TIME (UTC)** | Khoảng thời gian lưu bản sao có đáp ứng lịch backup không? |
| **FULL** | Chuỗi có bắt đầu từ một full backup hợp lệ? |
| **LOWEST TX / HIGHEST TX** | Khoảng transaction có nối tiếp và không bị thiếu mảnh? |
| **RECOVERED** | Full artifact đã ở trạng thái recovered để kiểm tra trực tiếp chưa? |
| **COMPRESSED** | Môi trường kiểm tra có hỗ trợ giải nén/đủ dung lượng tạm? |

**Bản Neo4j trước 2025.07** có thể cần tùy chọn **--show-metadata** để hiển thị metadata; trên bản mới trường này đã hiển thị mặc định. Không giả định tất cả tùy chọn chạy giống nhau trên Neo4j 4.x hoặc 5.x.

### 5.2. Minh họa chuỗi transaction đầy đủ và chuỗi bị thiếu

~~~text
Chuỗi A — hợp lệ:
  full      db-id=XYZ  tx=[1..100]
  diff-1    db-id=XYZ  tx=[101..140]
  diff-2    db-id=XYZ  tx=[141..170]

Chuỗi B — có khoảng trống:
  full      db-id=XYZ  tx=[1..100]
  diff-1    db-id=XYZ  tx=[101..140]
  diff-2    db-id=XYZ  tx=[151..170]  <-- thiếu 141..150

Chuỗi C — không cùng database:
  full      db-id=XYZ  tx=[1..100]
  diff-1    db-id=ABC  tx=[101..140]  <-- khác DATABASE ID
~~~

Chuỗi A có điều kiện metadata phù hợp để tiếp tục kiểm tra. Chuỗi B/C không được coi là một đường restore hợp lệ chỉ vì cùng tên thư mục hoặc cùng tên database. Công cụ backup/aggregate sẽ còn thực hiện các phép kiểm tra khi đọc artifact thật.

Một **differential rỗng** cũng có thể xuất hiện nếu không có transaction mới. Đừng tự coi mọi khoảng trống số trong output hoặc file rỗng về transaction là mất dữ liệu; cần hiểu metadata và quy tắc của phiên bản đang sử dụng.

### 5.3. Metadata không bảo đảm byte integrity

Lệnh **backup inspect** đọc thông tin mô tả và giúp xác định chuỗi; nó không phải lời bảo đảm rằng mọi byte bên trong artifact đều không hỏng hoặc mọi property graph còn đúng.

Khi chuyển backup từ máy chủ sang object storage:

1. Ghi lại **kích thước**, ngày sao chép và vị trí nguồn/đích.
2. Tạo **SHA-256/checksum** ở thời điểm sao chép hoặc khi artifact được khóa bất biến.
3. Lưu checksum/manifest ở kênh hoặc kho tin cậy phù hợp, không để kẻ tấn công sửa đồng thời artifact và manifest mà không bị phát hiện.
4. Định kỳ **tải ngược về môi trường phục hồi**, kiểm tra hash và dùng công cụ Neo4j để kiểm tra/restore.
5. Với backup artifact **chia thành nhiều phần** (tính năng của bản Neo4j mới), bảo đảm **toàn bộ các phần** được lưu cùng vị trí và được kiểm tra; thiếu một phần là không thể kết luận backup đầy đủ.

**SHA-256 đúng chỉ chứng minh bản tải về khớp với dữ liệu đã được băm theo nguồn tin cậy.** Nếu bản nguồn đã sai về nghiệp vụ hoặc băm được tính sau khi file đã hỏng, checksum không phát hiện được lỗi đó. Vì vậy vẫn cần consistency check và restore drill.

## 6. Tầng 2 — Chuẩn bị full backup đã recovery trước khi kiểm tra

Neo4j cho phép dùng **neo4j-admin database check** đối với database đang dừng, dump hoặc **full backup đã recovered**. Công cụ **không chạy trực tiếp** trên một differential backup riêng lẻ hoặc full backup chưa recovery xong.

Nếu có chuỗi **full + nhiều differential**, cần gom và replay chúng thành một full artifact đã recovered bằng **aggregate** trước khi kiểm tra consistency. Trong môi trường thử nghiệm, nên làm trên **bản sao của artifact** hoặc giữ nguyên chuỗi gốc.

### 6.1. Aggregate một chuỗi backup

~~~bash
# Neo4j Enterprise: tạo một full backup đã replay transaction.
# Giữ lại chuỗi gốc để kiểm chứng và rollback bài diễn tập.
bin/neo4j-admin backup aggregate \
  --from-path=/srv/neo4j-backups \
  --keep-old-backup=true \
  neo4j
~~~

**Quan trọng:** giá trị mặc định của tùy chọn **--keep-old-backup** là **false** trên các bản hiện hành, nên nếu vận hành không muốn xóa chuỗi cũ, hãy ghi **--keep-old-backup=true** và diễn tập trên kho kiểm thử. Aggregation có thể cần **nhiều dung lượng tạm, CPU, I/O và thời gian** để replay các transaction.

Từ **Neo4j 2025.11**, online full backup có thể được tạo với **--skip-recovery=true** để giảm thời gian backup, khiến bước recovery được dời sang lúc aggregate/restore. Vì vậy, **FULL=true** trong metadata không luôn đồng nghĩa **RECOVERED=true**.

Sau aggregate, inspect lại artifact đích và bảo đảm có một **full recovered** đúng database và recovery point cần kiểm tra. Nếu yêu cầu kiểm tra một mốc lịch sử cụ thể, **không chỉ chọn bản mới nhất** theo tiện lợi.

### 6.2. Không nhầm giữa aggregate và restore

**Aggregate** gộp chuỗi thành một artifact có thể dùng để kiểm tra và phục hồi nhanh hơn. **Restore** tạo ra dữ liệu database ở nơi đích. Dù aggregation báo thành công, việc diễn tập restore vẫn cần thiết để chứng minh artifact hoạt động với một Neo4j server và cấu hình thực tế.

## 7. Tầng 3 — Chạy Neo4j consistency checker

### 7.1. Kiểm tra trực tiếp trên full recovered backup

Với **Neo4j 2025.09 trở lên**, tùy chọn **--from-path** của lệnh check nhận đường dẫn một artifact cụ thể hoặc thư mục chứa artifact:

~~~bash
# Thay tên file bằng full recovered artifact vừa được inspect.
# Chạy trên máy kiểm thử có tài nguyên CPU/RAM/disk thích hợp.
bin/neo4j-admin database check \
  --from-path=/srv/neo4j-verify/neo4j-recovered.backup \
  --report-path=/srv/neo4j-verify/reports \
  neo4j
~~~

**Tên file trong ví dụ là placeholder**: không phải tệp do bài này tạo sẵn. Chọn đúng artifact được công cụ aggregate tạo ra. Với bản Neo4j cũ chưa hỗ trợ **--from-path** như trên, dùng hướng dẫn **database check** của chính phiên bản đó sau khi tạo một bản phục hồi offline.

Một lựa chọn khác (trên **database đã dừng**) là:

~~~bash
bin/neo4j-admin database check neo4j
~~~

**Không chạy consistency checker trực tiếp trên database đang được sử dụng.** Trong production, hãy kiểm tra artifact hoặc database phục hồi ở môi trường cô lập để không phải dừng dịch vụ chính. Không lấy một filesystem snapshot không nhất quán đang bị ghi rồi cho checker chạy như thể là database offline hoàn chỉnh.

### 7.2. Những gì consistency checker có thể phát hiện

| Nhóm kiểm tra | Mục đích |
|---|---|
| **Graph records** | Node, relationship, property, type và các liên kết cấu trúc nhất quán |
| **Index consistency** | Index có cấu trúc và quan hệ tới dữ liệu phù hợp |
| **Counts** | Bộ đếm số phần tử nhất quán với graph |
| **Property ownership** | Kiểm tra thêm quyền sở hữu property trên các store record |

Một số tùy chọn:

~~~bash
bin/neo4j-admin database check \
  --from-path=/srv/neo4j-verify/neo4j-recovered.backup \
  --check-graph=true \
  --check-indexes=true \
  --check-counts=true \
  --check-property-owners=true \
  --report-path=/srv/neo4j-verify/reports \
  neo4j
~~~

**--check-property-owners** có thể tăng đáng kể chi phí kiểm tra; tùy chọn này không bật mặc định trong tài liệu hiện hành. Với database lớn, có thể giới hạn **--threads** và **--max-off-heap-memory** theo tài nguyên thử nghiệm; không tắt kiểm tra quan trọng chỉ để làm báo cáo nhanh mà không ghi rõ phạm vi đã giảm.

### 7.3. Đọc kết quả đúng cách

Khi không phát hiện inconsistency, công cụ thường kết thúc với **exit code 0** và không tạo báo cáo lỗi. Nếu phát hiện lỗi, nó trả **exit code khác 0** và có thể tạo file dạng **inconsistencies-*.report** tại **--report-path**.

Bộ kiểm thử tự động cần ghi:

- Command line và phiên bản **neo4j-admin**.
- Artifact được kiểm tra, hash và database ID.
- Exit code, log cuối, đường dẫn report.
- Các tùy chọn kiểm tra có bật/tắt hay không.
- Tài nguyên máy và thời gian hoàn tất.

**Không chỉ tìm chuỗi “success” trong stdout.** Dùng exit code và report của chính lệnh, đồng thời xác nhận job không bị timeout/hết bộ nhớ. Một lần checker không chạy hết **không được gắn nhãn PASS**.

**Giới hạn của PASS:** checker khẳng định những cấu trúc được kiểm tra không có lỗi đã phát hiện. Nó không chứng minh có đủ dữ liệu để đáp ứng một nghiệp vụ cụ thể, không thay thế xác minh constraint theo schema, và không chứng minh API Java hoạt động được.

## 8. Tầng 4 — Diễn tập restore vào database cô lập

**Restore drill** là phép thử mạnh nhất cho câu hỏi: “Nếu database chính biến mất, đội vận hành có thực sự đưa hệ thống trở lại hoạt động được không?”

### 8.1. Lập môi trường kiểm thử trước khi restore

1. Chọn **Neo4j Enterprise standalone** thử nghiệm cùng hoặc phiên bản mới hơn phiên bản tạo backup theo đường nâng cấp được hỗ trợ.
2. Dự trù dung lượng cho **artifact, temp files, restored store, transaction logs và index**, không chỉ bằng đúng dung lượng tệp nén.
3. Đảm bảo database đích **không tồn tại**; không dùng tên database production làm đích nếu hạ tầng có bất kỳ kết nối chia sẻ nào.
4. Tắt hoặc cách ly các **worker, scheduler, webhook, connector** có thể gây tác động ra ngoài nếu dữ liệu sản xuất được phục hồi.
5. Kiểm soát tài khoản và dữ liệu nhạy cảm; mạng thử nghiệm không được tự kết nối tới cổng thanh toán hoặc hệ thống gửi email thật.

**Không bật tùy chọn --overwrite-destination=true** trong bài kiểm thử thông thường; tùy chọn ghi đè có thể phá hủy database đích nếu đặt nhầm tên hoặc đường dẫn. Trong cluster, ghi đè trực tiếp còn có rủi ro trạng thái cluster không khớp; phải dùng quy trình phục hồi cluster riêng.

### 8.2. Restore từ artifact — Enterprise Edition

Giả sử đã có một backup được chọn và kiểm chứng ở **/srv/neo4j-verify/neo4j-recovered.backup**:

~~~bash
# Chạy khi database restore_check chưa tồn tại/không được sử dụng.
# Dùng tài khoản hệ điều hành neo4j theo hướng dẫn.
bin/neo4j-admin database restore \
  --from-path=/srv/neo4j-verify/neo4j-recovered.backup \
  restore_check
~~~

Trên server có **database restore_check** được restore theo cách tạo mới, sau khi lệnh restore hoàn tất, kết nối vào database **system** bằng tài khoản quản trị và tạo database:

~~~cypher
CREATE DATABASE restore_check;
~~~

Sau đó:

~~~cypher
SHOW DATABASES
YIELD name, currentStatus, requestedStatus
WHERE name = 'restore_check'
RETURN name, currentStatus, requestedStatus;
~~~

Chỉ tính là “khởi động được” khi database đạt trạng thái phục vụ mong đợi và không báo lỗi recovery/index trong log. **Tên database restore_check** dùng cho bài diễn tập, không phải tên bắt buộc của Neo4j.

**Lưu ý phiên bản/edition:** cú pháp và các phương án phục hồi có thể thay đổi. Từ **Neo4j 2026.03**, còn có lựa chọn **neo4j-admin database copy** trong một số quy trình. Bài này chọn **database restore** vì thể hiện rõ việc dùng backup artifact. Không dùng trực tiếp lệnh Enterprise ở Community hay Aura rồi giả định có cùng tính năng.

### 8.3. Backup chain và PITR

Nếu đầu vào là **differential cuối của một chuỗi**, **database restore** có thể tìm full và các differential liên quan để replay. Với một điểm phục hồi cụ thể, công cụ có **--restore-until** (tùy định dạng và phiên bản):

~~~bash
# Ví dụ khung: lấy tất cả transaction được commit trước mốc UTC.
bin/neo4j-admin database restore \
  --from-path=/srv/neo4j-backups/last-differential.backup \
  --restore-until="2026-11-20 09:00:00" \
  restore_pitr_check
~~~

**Chuỗi nguồn và timestamp là ví dụ; phải chọn artifact thật chứa transaction cần phục hồi.** Với một transaction ID n, Neo4j khôi phục tới **trước giao dịch n** khi sử dụng tiêu chí ID, không phải “bao gồm n”. Tương tự, với UTC timestamp, chỉ những giao dịch được commit **trước** mốc được lựa chọn mới nằm trong điểm khôi phục.

Không suy ra chỉ giữ một full backup là có thể khôi phục tới mọi phút trong ngày; cần có các log/differential phù hợp và cách lưu được thiết kế cho mục tiêu RPO.

## 9. Tầng 5 — Kiểm tra logic graph sau restore

Khi **restore_check** đã ONLINE, sử dụng **Cypher** để kiểm chứng các invariant nghiệp vụ. Những truy vấn sau giả định ứng dụng có nhãn **DemoBackupCustomer**, **DemoBackupOrder** và relationship **DEMO_BACKUP_PLACED**. **Đây là dữ liệu minh họa**, không phải bảng bắt buộc của Neo4j.

### 9.1. Fixture mẫu để xây golden result

Trên **database thử nghiệm độc lập**, nếu muốn tạo dữ liệu minh họa, chạy một lần:

~~~cypher
CREATE CONSTRAINT demo_backup_customer_unique IF NOT EXISTS
FOR (c:DemoBackupCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_backup_order_unique IF NOT EXISTS
FOR (o:DemoBackupOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

~~~cypher
CREATE
  (c1:DemoBackupCustomer {tenantId: 'shop-a', customerId: 'C-1'}),
  (c2:DemoBackupCustomer {tenantId: 'shop-b', customerId: 'C-1'}),
  (o1:DemoBackupOrder {tenantId: 'shop-a', orderId: 'O-1', amountMinor: 15000}),
  (o2:DemoBackupOrder {tenantId: 'shop-a', orderId: 'O-2', amountMinor: 8000}),
  (o3:DemoBackupOrder {tenantId: 'shop-b', orderId: 'O-1', amountMinor: 9000}),
  (c1)-[:DEMO_BACKUP_PLACED]->(o1),
  (c1)-[:DEMO_BACKUP_PLACED]->(o2),
  (c2)-[:DEMO_BACKUP_PLACED]->(o3);
~~~

Tập mẫu gồm **2 Customer, 3 Order, 3 relationship** và có cùng **customerId/orderId** giữa hai tenant để bắt lỗi truy vấn bỏ điều kiện tenant. Không chạy đoạn **CREATE** lặp lại trên database đã có fixture; có thể vướng uniqueness constraint hoặc tạo quan hệ không chủ đích. Khi diễn tập backup, hãy tạo fixture **trước khi lấy backup** nếu muốn dùng nó làm golden result.

### 9.2. Kiểm tra số lượng và danh sách định danh

~~~cypher
MATCH (c:DemoBackupCustomer)
RETURN count(c) AS customerCount;
~~~

~~~cypher
MATCH (o:DemoBackupOrder)
RETURN o.tenantId AS tenant,
       o.orderId AS orderId,
       o.amountMinor AS amountMinor
ORDER BY tenant, orderId;
~~~

Với fixture trên, kỳ vọng **customerCount = 2** và danh sách Order là:

~~~text
shop-a  O-1  15000
shop-a  O-2   8000
shop-b  O-1   9000
~~~

**Đừng so sánh restored database với production hiện tại nếu production đã tiếp tục ghi sau recovery point.** Kỳ vọng phải dựa trên **snapshot/golden manifest tại đúng mốc backup**.

### 9.3. Kiểm tra trùng business key

~~~cypher
MATCH (o:DemoBackupOrder)
WITH o.tenantId AS tenant,
     o.orderId AS orderId,
     count(*) AS copies
WHERE copies > 1
RETURN tenant, orderId, copies;
~~~

Kết quả phải **không có hàng** nếu định danh duy nhất được bảo vệ đúng. **Uniqueness constraint** giúp ngăn trùng cho những thuộc tính có mặt, nhưng không tự bảo đảm mọi node đều có ID bắt buộc:

~~~cypher
MATCH (o:DemoBackupOrder)
WHERE o.tenantId IS NULL OR o.orderId IS NULL
RETURN count(o) AS missingBusinessIds;
~~~

Kỳ vọng **0**. Nếu có node thiếu business key, đó là lỗi logic/quality dù consistency checker vật lý có thể vẫn PASS.

### 9.4. Kiểm tra quan hệ và cô lập tenant

~~~cypher
MATCH (c:DemoBackupCustomer {
  tenantId: 'shop-a',
  customerId: 'C-1'
})-[:DEMO_BACKUP_PLACED]->(o:DemoBackupOrder)
RETURN o.orderId AS orderId
ORDER BY orderId;
~~~

Kỳ vọng **O-1, O-2**. Để phát hiện đường nối sai tenant:

~~~cypher
MATCH (c:DemoBackupCustomer)-[r:DEMO_BACKUP_PLACED]->
      (o:DemoBackupOrder)
WHERE c.tenantId <> o.tenantId
RETURN count(r) AS crossTenantRelationships;
~~~

Kỳ vọng **0**. Để phát hiện Order **không có hoặc có nhiều hơn một** Customer đặt:

~~~cypher
MATCH (o:DemoBackupOrder)
OPTIONAL MATCH (c:DemoBackupCustomer)-[:DEMO_BACKUP_PLACED]->(o)
WITH o, count(c) AS owners
WHERE owners <> 1
RETURN o.tenantId AS tenant, o.orderId AS orderId, owners;
~~~

Kết quả phải **không có hàng** nếu hợp đồng nghiệp vụ yêu cầu mỗi Order gắn với đúng một Customer. Nếu nghiệp vụ cho phép nhiều người cùng đặt, assertion này phải thay theo domain, không tự áp đặt.

### 9.5. Kiểm tra schema và index

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent
RETURN name, type, state, populationPercent
ORDER BY name;
~~~

Không chỉ đếm số index. Xác nhận **tên/loại, nhãn, property và trạng thái ONLINE** theo yêu cầu ứng dụng. Index **POPULATING** có thể cần thời gian hoàn tất sau restore; index **FAILED** cần được điều tra trước khi đưa vào phục vụ.

Sau restore cũng nên chạy các **golden Cypher queries** quan trọng của ứng dụng: tìm node theo khóa, truy vấn đường đi, lọc tenant, MERGE idempotent trên database test, cùng các truy vấn có nhiều relationship và NULL.

## 10. Tầng 6 — Kiểm tra khả năng ứng dụng truy cập bản phục hồi

Database có thể ONLINE và query thủ công chạy được, nhưng Java Driver hoặc Spring Data Neo4j vẫn gặp lỗi vì:

- DNS, Bolt URI, TLS hoặc chứng chỉ không đúng.
- Tài khoản ứng dụng không được tạo/phân quyền như mong đợi.
- Driver/SDN đang kết nối nhầm database hoặc cluster.
- **APOC/GDS** cần cho các câu Cypher không được cài hoặc bị allowlist chặn.
- Một constraint/index đã thay đổi khiến repository mapping hoặc truy vấn thất bại.
- Các tác vụ nền có thể vô tình gửi email/thanh toán thật khi môi trường restore bắt đầu phục vụ.

### 10.1. Smoke test bằng Java Driver

Đoạn Java dưới **chỉ đọc** trên database restore thử nghiệm, dùng Java Driver hiện đại. Driver được tạo một lần, còn session được đóng đúng vòng đời.

~~~java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.SessionConfig;

String uri = System.getenv("RESTORE_NEO4J_URI");
String user = System.getenv("RESTORE_NEO4J_USERNAME");
String password = System.getenv("RESTORE_NEO4J_PASSWORD");

try (var driver = GraphDatabase.driver(
        uri, AuthTokens.basic(user, password))) {

    driver.verifyConnectivity();

    try (var session = driver.session(
            SessionConfig.forDatabase("restore_check"))) {
        var orders = session.executeRead(tx -> tx.run("""
            MATCH (c:DemoBackupCustomer {
                tenantId: $tenant, customerId: $customer
            })-[:DEMO_BACKUP_PLACED]->(o:DemoBackupOrder)
            RETURN o.orderId AS orderId
            ORDER BY orderId
            """, Map.of("tenant", "shop-a", "customer", "C-1"))
            .list(row -> row.get("orderId").asString()));

        if (!orders.equals(java.util.List.of("O-1", "O-2"))) {
            throw new IllegalStateException("Restore smoke test failed");
        }
    }
}
~~~

**Điều kiện chạy:** fixture đã được đưa vào backup trước đó và được restore, biến môi trường trỏ tới **môi trường kiểm thử**, user đủ quyền đọc. Nếu backup thực không chứa nhãn demo, thay bằng **golden query đúng dữ liệu nghiệp vụ**, không tự tạo node demo sau khi restore rồi coi đó là bằng chứng backup đã chứa chúng.

**Kiểm tra thêm qua Spring Data Neo4j:** chạy các repository query và transaction boundary cần thiết trên cấu hình kết nối thử nghiệm, đặc biệt composite business key, mapping relationship, lazy/eager loading và các câu Cypher tùy chỉnh. Không chỉ gọi **driver.verifyConnectivity()** rồi kết luận toàn bộ ứng dụng đã sẵn sàng.

### 10.2. Security và system database

Trong Neo4j Enterprise, metadata người dùng/vai trò có các cơ chế backup/restore riêng. Sau restore backup dữ liệu, **không mặc định mọi user/role/privilege đã được áp dụng vào DBMS mới**. Tài liệu restore chỉ ra có thể cần thực thi **restore_metadata.cypher** trong **database system** nếu muốn khôi phục quyền.

Phân biệt:

1. **Database dữ liệu:** node, relationship, index/constraint và trạng thái giao dịch.
2. **System database / metadata:** database definitions, quyền và thành phần quản trị có phạm vi DBMS.
3. **Môi trường vận hành:** plugin JAR, biến môi trường, neo4j.conf, TLS, secrets, DNS và topology.

Những thành phần ngoài artifact dữ liệu phải có **runbook/configuration as code** và được diễn tập riêng. Chỉ khôi phục graph mà quên quyền truy cập có thể khiến ứng dụng thất bại hoặc môi trường mở quyền quá rộng.

## 11. Tiêu chí PASS/FAIL của một buổi diễn tập restore

| Kiểm tra | PASS khi | FAIL/BLOCKED khi |
|---|---|---|
| **Artifact** | Đọc được tất cả tệp/phần, checksum khớp manifest tin cậy | Thiếu file, sai hash, tải xuống lỗi |
| **Chain** | Đúng database ID và transaction continuity cho recovery point | Mất differential, khác database ID |
| **Consistency** | Checker hoàn tất, exit code 0, phạm vi kiểm tra đã ghi nhận | Exit code khác 0, không chạy hết, báo inconsistency |
| **Restore** | Restore thành database mới thành công, không ghi đè ngoài ý muốn | Lỗi replay, thiếu disk, sai quyền/phiên bản |
| **Availability** | Database ONLINE, Bolt/TLS và quyền ứng dụng hoạt động | Không mở database, sai auth, không thể truy vấn |
| **Graph invariants** | Golden queries, ID, counts, relationship và tenant scope đạt | Thiếu/trùng dữ liệu hoặc liên kết sai |
| **RPO** | Điểm khôi phục nằm trong ngân sách mất dữ liệu | Thiếu lịch sử hoặc recovery point quá cũ |
| **RTO** | Thời gian đầu-cuối trong SLO được duyệt | Restore hay warm-up quá chậm |
| **Security** | Không rò rỉ dữ liệu, không gọi side effect production, role phù hợp | Môi trường test truy cập nhầm hệ thống thật |

**Một PASS kỹ thuật không đồng nghĩa toàn bộ hệ thống đã an toàn.** Ví dụ checker PASS nhưng business validation FAIL thì kết quả diễn tập tổng thể phải **FAIL**, không “PASS một phần” cho mục tiêu sử dụng trong production.

### 11.1. Cách đo RPO và RTO có chứng cứ

Lưu các timestamp:

~~~text
incident_reference_at        = 2026-11-20T10:00:00Z
backup_recovery_point_at     = 2026-11-20T09:47:00Z
restore_drill_started_at     = 2026-11-20T10:05:00Z
database_online_at          = 2026-11-20T10:29:00Z
smoke_tests_passed_at       = 2026-11-20T10:35:00Z
~~~

Trong ví dụ, **mất dữ liệu theo thời gian ước lượng = 13 phút**. Thời gian từ khi **bắt đầu diễn tập đến smoke-test pass = 30 phút**, còn thời gian từ **incident reference đến smoke-test pass = 35 phút**. Định nghĩa RTO của tổ chức phải ghi rõ nó bắt đầu tại mốc nào; không trộn các cách đo khi làm báo cáo.

Nếu chỉ có thông tin **transaction ID** mà không có thời gian commit chính xác, hãy đo RPO theo đơn vị dữ liệu/giao dịch và đánh giá thời gian bằng bằng chứng bổ sung; không bịa ra độ trễ phút từ ID.

## 12. Những thử nghiệm âm tính giúp phát hiện backup không dùng được

Bên cạnh tình huống thông thường, cần có bài thử trên **bản sao thử nghiệm**, tuyệt đối không phá hỏng artifact backup gốc.

| Tình huống lỗi được mô phỏng | Điều cần chứng minh |
|---|---|
| **Thiếu một differential** | Inspect/aggregate/restore không nhận nhầm chuỗi là đầy đủ |
| **Một tệp bị cắt cụt** | Checksum hoặc thao tác đọc/recovery phát hiện lỗi; pipeline FAIL |
| **Khác database ID** | Không nối nhầm backup chỉ vì tên database giống nhau |
| **Chỉ có full chưa recovery** | Không gọi consistency check trực tiếp rồi ghi PASS giả |
| **Artifact nhiều phần bị thiếu một part** | Phát hiện inventory thiếu phần thay vì thử restore mù |
| **Database restore trùng tên** | Không sử dụng overwrite ngoài chủ đích |
| **Không đủ temp/disk** | Runbook báo blocker tài nguyên, không phá hỏng bản sao nguồn |
| **Role ứng dụng thiếu READ** | Smoke test dưới tài khoản ứng dụng FAIL đúng cách |
| **Neo4j đích cũ hơn nguồn** | Phát hiện không hỗ trợ downgrade/restore về bản thấp hơn |
| **Backup chứa dữ liệu sai nghiệp vụ** | Consistency có thể PASS nhưng các assertion graph FAIL |

**Không yêu cầu mọi test âm tính phải chạy trong production.** Những tình huống giả lập thiếu file/hỏng byte thực hiện trên một **bản copy** đặt trong vùng thử nghiệm riêng. Mục tiêu là kiểm tra khả năng **phát hiện lỗi**, không cố tạo một sự cố thật.

## 13. Lịch kiểm tra và tích hợp CI/CD

Một lịch phù hợp cần dựa trên độ quan trọng của database, dung lượng backup, RPO/RTO và khả năng thay đổi phiên bản. Ví dụ chính sách minh họa:

| Tần suất gợi ý | Hoạt động | Kết quả cần lưu |
|---|---|---|
| **Mỗi lần backup** | Xác nhận job, inventory, database ID, tx-range, checksum | Backup manifest và log |
| **Hằng ngày** | Inspect chuỗi mới nhất, báo alert nếu thiếu lịch hoặc sai chain | Chain report, tuổi backup |
| **Hằng tuần** | Aggregate/consistency check trên bản được chọn | Exit code và report, phạm vi check |
| **Hằng tháng** | Restore drill vào môi trường cô lập + golden queries | RPO/RTO và smoke-test report |
| **Trước nâng cấp/migration lớn** | Restore từ artifact của phiên bản cũ rồi thử upgrade/schema | Kết quả tương thích và kế hoạch rollback |
| **Sau thay đổi quan trọng** | Diễn tập riêng bảo mật, phân quyền, cluster/CDC nếu có | Evidence từ workload/topology phù hợp |

Các tần suất là **gợi ý về quy trình**, không phải cam kết chính thức của Neo4j. Database trọng yếu có thể cần diễn tập nhiều hơn; database lớn có thể kiểm tra theo mẫu nhưng phải có chiến lược bao phủ toàn bộ chuỗi trong khoảng thời gian xác định.

### 13.1. Pipeline kiểm tra dạng khái niệm

~~~text
Backup job hoàn tất
  -> Kiểm tra artifact tồn tại và checksum
  -> neo4j-admin backup inspect: database ID, TX range, chain
  -> Copy chain vào staging, bảo toàn bản gốc
  -> Aggregate thành full recovered (nếu cần)
  -> neo4j-admin database check: exit code, report
  -> Restore vào database cô lập
  -> CREATE DATABASE và chờ ONLINE
  -> Cypher assertions + Java Driver/SDN smoke tests
  -> Đo recovery point, RPO/RTO
  -> Lưu kết quả PASS/FAIL + artifact hashes
  -> Teardown an toàn database thử nghiệm sau khi lưu evidence
~~~

Nếu bước trước FAIL thì **không** chuyển bước sau thành PASS vì “còn chạy được vài query”. Pipeline phải có trạng thái **BLOCKED** khi thiếu quyền, thiếu resource, chưa có fixture hoặc chưa có môi trường phù hợp.

### 13.2. Manifest và nhật ký diễn tập

Lưu một báo cáo cho **từng database + từng recovery point**:

~~~yaml
# Ví dụ định dạng báo cáo; KHÔNG phải tệp cấu hình Neo4j.
database: neo4j
source_neo4j_version: "2026.10.2"
restore_neo4j_version: "2026.10.2"
backup_type: "full-plus-differential"
database_id: "example-database-id"
last_transaction_id: 170
artifact_sha256_verified: true
chain_verified: true
consistency_exit_code: 0
restore_online: true
business_invariants_passed: true
application_smoke_passed: true
measured_rpo_minutes: 13
measured_rto_minutes: 35
result: PASS
~~~

Đây là số liệu **minh họa**; không dùng làm bằng chứng cho một backup thật. Khi lưu báo cáo production, kết hợp hash/ID với đường dẫn lưu trữ và thời gian UTC thực tế; tránh ghi secrets vào manifest.

## 14. Tương thích phiên bản, cluster và Aura

### 14.1. Neo4j 5.x so với bản năm–tháng

Các lệnh hiện hành như **neo4j-admin backup inspect**, **backup aggregate** và **database check --from-path** có sự thay đổi về tên/tùy chọn theo version. Đặc biệt:

- **database check --from-path** nhận artifact trực tiếp từ **2025.09**.
- **backup inspect** hiển thị metadata mặc định từ **2025.07**.
- **--skip-recovery** của online full backup xuất hiện từ **2025.11**.
- Một số phiên bản hiện đại hỗ trợ **backup split archive**; cần giữ đủ mọi phần.

Vì vậy **luôn kiểm tra neo4j-admin --help của đúng phiên bản nguồn/đích** và migration guide. Một câu lệnh trong bài không được xem như có thể copy không sửa sang Neo4j 4.x.

**Restore một backup về Neo4j phiên bản thấp hơn phiên bản đã tạo nó không được hỗ trợ**. Hãy thực hành trên phiên bản tương thích theo tài liệu nâng cấp; đừng thử “rollback bằng cách dùng binary cũ mở store mới” thay cho restore bản backup trước nâng cấp.

### 14.2. Cluster không chỉ là restore lên một node bất kỳ

Trong Neo4j cluster, database còn có trạng thái phân bổ/đồng thuận và topology. Restore trực tiếp lên một thành viên rồi bật **--overwrite-destination** không phải cách chuẩn để thay toàn bộ database cluster. Tài liệu Neo4j có các quy trình **recreate database from URI**, **designated seeder**, hoặc phương án cluster restore theo phiên bản.

Một **restore drill standalone** đủ để chứng minh artifact, consistency và nhiều truy vấn nghiệp vụ, nhưng **chưa kiểm tra failover, catch-up, leader election hoặc routing**. Nếu SLA yêu cầu khả dụng sau sự cố cluster, phải có diễn tập topology riêng.

### 14.3. Neo4j Aura

Trong **Aura**, quản lý snapshot/backup và restore theo khả năng của dịch vụ, không đăng nhập server để chạy **neo4j-admin database restore** hoặc sửa filesystem. Bằng chứng cần có vẫn tương tự: backup point, thử restore vào instance kiểm thử được hỗ trợ, truy vấn xác minh, quyền kết nối và đo RPO/RTO theo gói dịch vụ.

Không suy ra Aura có cùng cú pháp và quyền với Enterprise tự quản lý. Thông số retention, số lần restore, hỗ trợ point-in-time recovery hoặc lựa chọn backup do **tier và tài liệu Aura hiện hành** quy định.

## 15. Lỗi thường gặp và hướng xử lý

| Biểu hiện | Nguyên nhân có thể | Hành động |
|---|---|---|
| Backup job SUCCESS nhưng không restore được | Chuỗi thiếu file, artifact hỏng, sai phiên bản | Inspect chain, checksum, aggregate và restore drill |
| Full backup nhưng consistency check từ chối | Artifact **RECOVERED=false** | Aggregate/recovery trước khi kiểm tra |
| Chỉ có differential | Không có base full phù hợp | Lấy đầy đủ chain; không tự kết luận diff độc lập sử dụng được |
| Không rõ backup thuộc database nào | Trùng tên nhưng khác database ID | Đọc metadata, chọn đúng database ID |
| Check báo inconsistency | Store/index/count/property không nhất quán | Giữ report, cô lập artifact, điều tra nguyên nhân; không đưa vào phục vụ |
| Restore thất bại do dung lượng | Thiếu temp/staging/store space | Tăng dung lượng staging theo kế hoạch, không xóa backup gốc |
| Database ONLINE nhưng app không đăng nhập được | User/role metadata, TLS hoặc secrets sai | Kiểm tra system/auth và cấu hình kết nối |
| Count đúng nhưng dữ liệu sai | Chỉ assert tổng số node | So tập business key, relationship, tenant và golden queries |
| Restore đúng nhưng rất chậm | Replay nhiều differential, download chậm, index/page cache warm-up | Đo từng chặng RTO, cân nhắc aggregate định kỳ |
| Smoke test trên restore làm phát sự kiện thật | Worker và connector test không được cô lập | Ngắt external side effects; dùng sandbox/stub |
| Backup ở storage nhưng không tải về được | Quyền cloud, khóa mã hóa, retention tier hoặc mất credentials | Diễn tập lấy bản sao bằng chính tài khoản recovery |
| Khi cần phục hồi từ timestamp không có transaction | Chain không chứa recovery point hoặc log bị pruning | Chọn điểm khả dụng, báo RPO thực tế; cải thiện backup policy |

## 16. Bài tập thực hành

### Bài 1 — Metadata của chuỗi backup

Cho full **tx 1–80**, differential A **81–100**, differential B **111–130**. Có thể gọi đây là chuỗi đầy đủ đến tx 130 không? Hãy chỉ ra phần thiếu và những trường metadata khác cần so sánh ngoài transaction ID.

### Bài 2 — Full chưa recovery

Một job tạo full backup với **RECOVERED=false**. Người vận hành chạy **neo4j-admin database check** trực tiếp trên artifact và thất bại. Hãy mô tả đúng thứ tự **inspect → aggregate/recovery → check** và lý do không được đổi kết quả thất bại thành PASS.

### Bài 3 — Tách structural consistency khỏi business invariant

Một backup được checker đánh giá consistent nhưng có Order O-1 thiếu Customer. Viết truy vấn Cypher tìm Order không có relationship **DEMO_BACKUP_PLACED** và giải thích tại sao checker có thể PASS.

### Bài 4 — Thiết kế restore drill

Bạn được giao một chuỗi backup trên object storage. Hãy liệt kê những bước cần làm để kiểm chứng hash, chain, restore, quyền truy cập, trạng thái ONLINE và hai truy vấn nghiệp vụ quan trọng. Tại bước nào phải bảo đảm môi trường không thể gửi email hoặc thanh toán thật?

### Bài 5 — RPO/RTO

Sự cố xảy ra 13:00 UTC, recovery point cuối ở 12:48 UTC, hệ thống phục vụ trở lại với smoke-test pass lúc 13:42 UTC. Tính mất dữ liệu theo thời gian và RTO theo định nghĩa từ thời điểm sự cố; xác định hệ thống có đạt **RPO 15 phút** và **RTO 45 phút** không.

### Bài 6 — Kiểm tra cô lập tenant

Fixture có **shop-a / C-1** và **shop-b / C-1**. Viết truy vấn so sánh Order của từng tenant, tìm relationship nối hai tenant khác nhau và tìm business key trùng **trong cùng tenant**.

### Bài 7 — Backup đúng nhưng vận hành chưa sẵn sàng

Backup đã aggregate và consistency check PASS. Database restore cũng ONLINE, nhưng Spring Data Neo4j báo lỗi vì tài khoản thiếu quyền đọc và procedure APOC không nạp. Hãy phân biệt **artifact correctness** với **service readiness**, đề xuất checklist để chuyển từ trạng thái BLOCKED sang PASS.

## 17. Tổng kết

Đối với Neo4j, **bản sao đáng tin cậy** là bản sao đã được **kiểm tra chuỗi nguồn và metadata**, **xác minh byte integrity**, **kiểm tra consistency**, **phục hồi vào một database cô lập**, rồi **xác nhận graph và ứng dụng còn đúng**.

Quy trình cần nhớ:

**Inventory & checksum → inspect database ID/transaction chain → aggregate thành full recovered → database check → restore drill → graph invariants → Java Driver/SDN smoke test → RPO/RTO evidence.**

Trên production, không dùng backup job SUCCESS hoặc một phép đếm node để thay thế toàn bộ quy trình; đặc biệt không ghi đè database thật trong một bài thử. Lịch sao lưu cần đi cùng **lịch diễn tập phục hồi**, vì mục tiêu cuối cùng không phải tích lũy nhiều file, mà là **khôi phục dữ liệu đúng và đưa dịch vụ trở lại trong giới hạn đã cam kết**.

### Tài liệu Neo4j chính thức

- [Neo4j Operations Manual – Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual – Back up an online database](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/)
- [Neo4j Operations Manual – Inspect the metadata of a backup file](https://neo4j.com/docs/operations-manual/current/backup-restore/inspect/)
- [Neo4j Operations Manual – Aggregate a backup chain](https://neo4j.com/docs/operations-manual/current/backup-restore/aggregate/)
- [Neo4j Operations Manual – Check database consistency](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/)
- [Neo4j Operations Manual – Restore a database backup](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-backup/)
- [Neo4j Operations Manual – Back up an offline database](https://neo4j.com/docs/operations-manual/current/backup-restore/offline-backup/)
- [Neo4j Operations Manual – Restore a database dump](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-dump/)
- [Neo4j Java Driver Manual – Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)

# Sao lưu trực tuyến khi edition hoặc dịch vụ hỗ trợ trong Neo4j

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **sao lưu trực tuyến (online backup)**, **sao lưu ngoại tuyến (offline dump)**, snapshot dịch vụ, replication của cluster và khôi phục sau sự cố.
- Xác định **edition và mô hình triển khai** nào hỗ trợ `neo4j-admin database backup`, môi trường nào phải dùng snapshot do nhà cung cấp quản lý.
- Cấu hình dịch vụ backup, địa chỉ mạng, cổng, TLS, quyền đọc/ghi và tài nguyên cho Neo4j **Enterprise self-managed**.
- Thực hiện và giải thích **FULL**, **DIFF**, **AUTO**, chuỗi backup, metadata và các tùy chọn có điều kiện theo phiên bản.
- Thiết kế lịch backup phù hợp **RPO** và **RTO**, tránh đứt chuỗi, thiếu transaction log và thiếu dung lượng lưu trữ tạm.
- Kiểm tra metadata của bản backup, diễn tập **restore vào môi trường độc lập**, kiểm tra consistency và đối chiếu dữ liệu nghiệp vụ.
- Bảo vệ bản backup chứa thông tin nhạy cảm, thiết kế giám sát, cảnh báo và quy trình khôi phục khi hệ thống graph gặp sự cố.

Đây là bài thuộc chương **Sao lưu và phục hồi** trong module **DATABASE_ENGINE_GRAPH_NEO4J**. Neo4j lưu node, relationship, property, index và constraint để hỗ trợ truy vấn Cypher về liên kết và đường đi. Ứng dụng Java Driver hoặc Spring Data Neo4j phụ thuộc vào trạng thái graph đúng để thực hiện giao dịch đọc/ghi. Backup vì vậy không chỉ là “lưu một tệp”: nó phải giúp tái lập **trạng thái database nhất quán**, đáp ứng mục tiêu mất dữ liệu tối đa và thời gian phục hồi của hệ thống.

> **Phạm vi phiên bản:** Những lệnh trong bài dựa trên Neo4j Operations Manual dành cho Neo4j 5.x và các dòng 2025.x–2026.x có API tương ứng. **Tùy chọn CLI, mặc định, khả năng sao lưu qua cloud storage và quy tắc chuỗi differential thay đổi theo bản.** Trước khi chạy trên production, kiểm tra `neo4j-admin ... --help` và tài liệu **đúng phiên bản đã cài**. Các lệnh thay đổi dữ liệu hoặc restore được ghi rõ là dành cho **môi trường thực hành/cách ly**, không phải hướng dẫn ghi đè production trực tiếp.

## 1. Online backup là gì và giải quyết điều gì?

**Online backup** thu thập dữ liệu cần khôi phục **khi database nguồn vẫn đang chạy** và tiếp nhận giao dịch. Với **Neo4j Enterprise self-managed**, công cụ `neo4j-admin database backup` liên hệ một backup service trên server nguồn, sao lưu store và thông tin transaction cần thiết để tạo artifact có thể khôi phục.

~~~mermaid
flowchart LR
    A["Java / Spring application"] -->|Cypher READ/WRITE| N[("Neo4j Enterprise<br/>đang online")]
    N -->|Backup protocol| C["Backup client<br/>neo4j-admin"]
    C -->|FULL / DIFF| B[("Backup repository<br/>các artifact .backup")]
    B --> V["Inspect + consistency + restore drill"]
    V --> R[("Neo4j recovery environment")]
~~~

Đặc điểm cần nhớ:

- **Nguồn còn chạy** trong lúc backup, nhưng backup vẫn dùng CPU, I/O, network và có thể làm tăng độ trễ truy vấn.
- **Backup artifact** là dữ liệu lưu trữ cho một database và metadata đi kèm; không phải một luồng `MATCH` xuất ra CSV hoặc JSON.
- Có thể tạo **FULL** ban đầu và **DIFF** về sau nhằm giảm dữ liệu phải truyền.
- Để phục hồi đến một trạng thái hợp lệ, hệ thống cần **chuỗi backup đầy đủ** và khả năng áp dụng các transaction tương ứng.
- Có backup thành công **không tự bảo đảm** rằng đã có runbook restore, quyền truy cập bản backup hay RTO đạt yêu cầu.

### Online backup không đồng nghĩa HA/replication

| Cơ chế | Mục đích | Có thay thế backup không? |
| --- | --- | --- |
| **Cluster replication** | Duy trì khả năng phục vụ khi một thành viên lỗi | **Không**: lệnh xóa dữ liệu hoặc ghi sai có thể được đồng bộ sang nhiều thành viên |
| **Online backup** | Lưu các mốc dữ liệu có thể phục hồi từ nơi lưu độc lập | Là nguồn dữ liệu khôi phục, nhưng không tự failover |
| **Offline dump** | Tạo tệp lưu trữ khi database không online | Có thể dùng cho migration/lab và kịch bản chấp nhận downtime |
| **Aura snapshot** | Sao lưu do dịch vụ quản lý theo quyền lợi gói | Không đồng nghĩa tự chạy `neo4j-admin` trên máy Aura |
| **CDC / event stream** | Đồng bộ thay đổi dữ liệu đã commit | Không tự thay thế snapshot nhất quán và quy trình restore |

Nếu một transaction nghiệp vụ xóa nhầm toàn bộ relationship `PLACED`, cluster có thể sao chép chính thay đổi sai đó. Backup độc lập theo thời điểm trước sự cố là một lớp phòng vệ khác.

## 2. Điều kiện hỗ trợ theo edition và mô hình triển khai

Đừng suy luận từ việc có Neo4j Java Driver, có quyền đăng nhập admin, hoặc Neo4j phiên bản mới rằng môi trường chắc chắn hỗ trợ lệnh online backup.

| Môi trường | Online backup `neo4j-admin database backup` | Cách nên tiếp cận |
| --- | --- | --- |
| **Neo4j Enterprise Edition self-managed** | **Có**, khi backup service và quyền mạng/tài nguyên được cấu hình phù hợp | Dùng backup client, FULL/DIFF/AUTO, đặt lịch và restore drill |
| **Neo4j Community Edition self-managed** | **Không** hỗ trợ tính năng online backup Enterprise này | Xem `neo4j-admin database dump` cho database **offline**, hoặc kiến trúc có edition hỗ trợ nếu cần backup khi chạy |
| **Neo4j Enterprise trong Docker/Kubernetes** | **Có** nếu image/license, service backup, port, volume và quyền được cấu hình đúng | Dùng công cụ backup từ client/job đáng tin, không chỉ copy volume đang ghi |
| **AuraDB Free** | Không có lịch snapshot backup người dùng như các gói trả phí theo bảng dịch vụ hiện hành | Không mặc định có khả năng phục hồi snapshot; xem chính sách gói và phương án export được phép |
| **AuraDB Professional, Business Critical, Virtual Dedicated Cloud** | **Không chạy lệnh Enterprise self-managed trực tiếp** | Sử dụng **snapshot/backup/restore** do Aura cung cấp theo gói; tần suất và retention khác nhau |
| **AuraDS hoặc dịch vụ quản lý khác** | Phụ thuộc sản phẩm/gói và giao diện được cung cấp | Kiểm tra chính sách snapshot và các tác vụ quản trị dành riêng cho dịch vụ |

Theo tài liệu Aura hiện hành, ví dụ **AuraDB Professional** có full snapshot hằng ngày; **Business Critical** có full hằng ngày và differential hằng giờ; **Virtual Dedicated Cloud** có chính sách phụ thuộc thế hệ instance và gói. **Thời gian giữ, quyền on-demand/export và phạm vi restore** khác nhau; bảng chính thức có thể đổi. Không viết một lịch “30 ngày retention” rồi coi đó là mặc định của mọi Aura.

Tham khảo:

- [Neo4j — Back up an online database](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/)
- [Neo4j — Backup modes](https://neo4j.com/docs/operations-manual/current/backup-restore/modes/)
- [Aura — Backup, export, restore and upload](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/)

**Kiểm tra tại chỗ** nếu có quyền:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Đối chiếu giá trị `versions` và `edition` với bản cài và license. Với Aura, các quyền quan sát này có thể khác; xem tên gói ở bảng điều khiển dịch vụ và khả năng snapshot thực tế.

## 3. Xác định RPO, RTO và phạm vi phải sao lưu

Trước khi quyết định cron và dung lượng lưu trữ, xác định:

- **RPO (Recovery Point Objective):** mức dữ liệu tối đa có thể mất, thường đo theo thời gian giữa mốc phục hồi gần nhất và sự cố.
- **RTO (Recovery Time Objective):** thời gian tối đa được phép để dịch vụ hoạt động lại ở mức đã cam kết.
- **Backup scope:** một database hay toàn DBMS, bao gồm `system` database, các user-defined databases, cấu hình/secret/connector cần dựng lại.
- **Failure scope:** hỏng node, hỏng volume, mất cả vùng, thao tác xóa nhầm, ransomware hay sai dữ liệu nghiệp vụ.
- **Restore target:** khôi phục database mới để đối soát, thay database hiện tại hay dựng một cụm phục hồi độc lập.

Ví dụ hợp đồng giả định:

| Khả năng | Mục tiêu ví dụ | Hệ quả kiến trúc |
| --- | --- | --- |
| RPO | 15 phút | Tổ chức chu kỳ DIFF/backup đủ dày, có cảnh báo khi thất bại |
| RTO | 2 giờ | Cần bản FULL gần, chuỗi DIFF không quá dài và môi trường restore có sẵn |
| Phạm vi | `orders_graph` và `system` | Backup đủ từng database/metadata cần thiết, không chỉ DB mặc định |
| Địa điểm | Có sự cố mất cả host | Artifact phải nằm **ngoài máy chủ nguồn**, tránh chung failure domain |
| Tính đúng | Toàn bộ node, relationship, constraint, query quan trọng | Đo kiểm sau restore, không chỉ kiểm tra file tồn tại |

Các con số trên chỉ là ví dụ đào tạo. **Backup mỗi 15 phút không mặc nhiên bảo đảm RPO đúng 15 phút**: một job thất bại, log thiếu hoặc quá trình upload chậm có thể khiến mốc khôi phục mới nhất cũ hơn.

### 3.1. Một application có thể dùng nhiều database

Ví dụ ứng dụng chứa `customer_graph` và `order_graph` hoặc có nhiều database trong một DBMS. Neo4j backup lưu **artifact theo database**. Nếu backend update hai database trong hai transaction riêng, backup của chúng tại hai thời điểm khác nhau **không tạo snapshot nguyên tử xuyên database**.

Cần thỏa thuận:

1. Database nào là nguồn dữ liệu có thẩm quyền?
2. Có cần backup **`system`** để bảo toàn metadata quản trị và vận hành không?
3. Có tài liệu cách tái tạo user/role/privilege, alias, cấu hình và secrets không?
4. Nếu hai database cùng phục vụ một quy trình, sau restore sẽ **reconcile** bằng business ID/version thế nào?

**Không mặc định artifact của một database chứa toàn bộ cấu hình máy chủ hoặc state của các hệ thống ngoài Neo4j.**

## 4. Kiến trúc FULL, DIFF và chuỗi backup

Neo4j Enterprise online backup có những loại artifact:

- **FULL:** chứa store cần thiết của một database và metadata.
- **DIFF:** chứa transaction logs/phần thay đổi tiếp nối từ một backup cha phù hợp.
- **AUTO:** công cụ tự chọn; khi chưa có chuỗi phù hợp, có thể tạo FULL; khi đủ điều kiện sẽ thực hiện DIFF.

~~~mermaid
flowchart LR
    F["FULL #1<br/>store cơ sở"] --> D1["DIFF #2<br/>transactions tiếp theo"]
    D1 --> D2["DIFF #3"]
    D2 --> D3["DIFF #4"]
    D3 --> R["Restore tới mốc #4"]
~~~

Một **backup chain** phụ thuộc vào mối quan hệ giữa các artifact. Nếu xóa một DIFF ở giữa mà các DIFF sau cần nó, chuỗi không còn khôi phục được tới điểm mong muốn. Ngoài chuỗi còn có **database ID**, transaction IDs, bản Neo4j hỗ trợ và thông tin phục hồi.

### 4.1. Trường hợp DIFF không thể chạy

Một DIFF cần bản cha và những transaction log thích hợp. Nếu log cần thiết đã bị prune hoặc chuỗi không phù hợp, công cụ ở chế độ `AUTO` có thể cần thực hiện FULL mới. Không nên cấu hình “chỉ DIFF mãi mãi” mà không theo dõi lý do thất bại, chain continuity và chi phí lưu trữ.

**Không sao chép một tệp có đuôi `.backup` ra khỏi tập rồi kết luận đó là bản restore độc lập.** FULL có thể tự đủ khi đã được recovery phù hợp; một DIFF chỉ có ý nghĩa với phần chuỗi liên quan.

### 4.2. Các mốc hành vi theo phiên bản

| Phiên bản/tùy chọn | Ý nghĩa cần lưu ý |
| --- | --- |
| **Neo4j 2025.04**: `--prefer-diff-as-parent` | Có thể ưu tiên DIFF gần nhất làm cha để duy trì chuỗi theo mục tiêu; phải xem chính sách retention |
| **Neo4j 2025.09**: `--remote-address-resolution` | Hỗ trợ chọn máy chủ nguồn backup trong topology khi khả dụng |
| **Neo4j 2025.11**: `--skip-recovery` và `--parallel-download` | Có thể điều chỉnh thời gian backup/restore hoặc tải song song; cần đánh giá tài nguyên và hỗ trợ |
| **Neo4j 2026.02** | DIFF đầu sau FULL được phép **overlap** với FULL trước; giúp lịch FULL và DIFF độc lập hơn |
| **Neo4j 2026.08**: `--skip-empty-diffs` | Có thể bỏ qua tạo file DIFF rỗng trong điều kiện lựa chọn metadata được chỉ định |
| **Neo4j 2026.09**: `--split-archive-part-size` | Có thể chia artifact lớn thành nhiều phần với giới hạn tối thiểu theo tài liệu; phải giữ đủ các phần để restore |

Các tùy chọn này **không tồn tại ở mọi bản**. Ngoài ra, `--skip-recovery` có thể chuyển thêm việc recovery sang thời điểm restore: giảm thời gian backup nhưng **không tự tốt hơn cho RTO**. Tham khảo [Online backup](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/) và [Aggregate backup chain](https://neo4j.com/docs/operations-manual/current/backup-restore/aggregate/).

## 5. Chuẩn bị Neo4j Enterprise self-managed

### 5.1. Điều kiện trước khi chạy

- Neo4j DBMS đang chạy **Enterprise** được cấp phép và database cần sao lưu đang online.
- Máy backup client có **`neo4j-admin` tương thích** với server nguồn.
- Đã xác định tên database đúng; không backup nhầm **alias** thay vì database vật lý.
- Dịch vụ backup được bật, backup port đi tới được **từ đúng máy backup client**.
- Có đủ không gian lưu trữ **destination và vùng tạm**, đồng thời hệ thống đáp ứng CPU, heap, page cache, I/O và network.
- Người vận hành có quyền thực thi CLI và quyền filesystem phù hợp; hạn chế user có thể tải/copy artifacts.
- Đã định nghĩa vị trí backup an toàn, retention, encryption và restore drill.

Kiểm tra danh sách database trên môi trường cho phép:

~~~cypher
SHOW DATABASES
YIELD name, requestedStatus, currentStatus
RETURN name, requestedStatus, currentStatus
ORDER BY name;
~~~

Chỉ định database **`orders_graph`** trong ví dụ tiếp theo nếu nó tồn tại thật; thay tên theo hệ thống của bạn.

### 5.2. Cấu hình backup service

Trong Neo4j Enterprise self-managed, các setting phổ biến:

~~~properties
# neo4j.conf - ví dụ minh họa. Cấu hình trên server nguồn.
server.backup.enabled=true
server.backup.listen_address=127.0.0.1:6362
~~~

Theo tài liệu vận hành hiện hành, backup service **mặc định enabled** nhưng chỉ lắng nghe **loopback** `127.0.0.1:6362`. Điều đó phục vụ backup local; backup từ host riêng cần bind vào **địa chỉ mạng nội bộ cụ thể** và mở đúng đường mạng, chẳng hạn:

~~~properties
# Chỉ dùng khi backup client ở mạng riêng đã kiểm soát.
server.backup.enabled=true
server.backup.listen_address=10.0.10.12:6362
~~~

Địa chỉ là ví dụ; cần khớp interface thực tế. Đổi cấu hình có thể yêu cầu restart/redeploy theo phiên bản và quy trình server. Không đổi sang `0.0.0.0` rồi mở cổng 6362 ra Internet: **đây là giao diện nhạy cảm cho phép sao chép dữ liệu database**. Sử dụng firewall, mạng riêng, kiểm soát service account và TLS.

### 5.3. Cổng backup không phải cổng Bolt

| Chức năng | Cổng phổ biến | Dùng để |
| --- | ---: | --- |
| **Bolt** | 7687 | Java Driver, Spring Data Neo4j, các truy vấn Cypher |
| **HTTP** | 7474 | Giao diện HTTP/Browser nếu bật |
| **Backup protocol** | 6362 | `neo4j-admin database backup` trên Enterprise |
| **Cluster traffic** | Phụ thuộc topology/config | Trao đổi cluster, cần chính sách mạng riêng |

`neo4j-admin database backup --from=...` dùng **backup endpoint**, không phải URI `neo4j://...:7687` hoặc tài khoản đăng nhập Browser. **Thấy port 7687 hoạt động không chứng minh backup port 6362 đang phục vụ**.

### 5.4. Bật TLS cho backup

Neo4j hỗ trợ SSL policy riêng cho backup, có cấu hình phía server và phía backup client. Ví dụ phần cờ khái niệm:

~~~properties
# Phần khung thiết lập policy backup; KHÔNG phải cấu hình TLS hoàn chỉnh.
dbms.ssl.policy.backup.enabled=true
dbms.ssl.policy.backup.client_auth=REQUIRE
~~~

Để sử dụng thật, phải cấu hình **certificate, private key, trust, CA chain, chính sách TLS phiên bản và cipher** đồng bộ giữa server/client theo tài liệu Neo4j. Không chỉ bật hai cờ trên rồi cho rằng kết nối đã an toàn. Ưu tiên chứng chỉ CA được tin cậy và giới hạn đúng mạng backup. Xem [Online backup — SSL/TLS configuration](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/).

## 6. Thực hiện một bản online FULL

**Chỉ thực hiện trên môi trường Enterprise thử nghiệm đã cấu hình.** Giả định:

- Máy chạy `neo4j-admin` là một backup client được phép truy cập backup server `10.0.10.12:6362`.
- Database nguồn tên `orders_graph` và đang online.
- Directory `/srv/neo4j-backups/orders` đã tồn tại, đủ dung lượng và không đặt trong data directory của Neo4j.

~~~bash
# Trên backup client; KHÔNG chạy trong Cypher Browser.
neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=/srv/neo4j-backups/orders \
  --type=FULL \
  orders_graph
~~~

Kết quả là artifact FULL trong thư mục đích. Tên chính xác thường chứa tên database và timestamp; **không tự đặt tên file khi cần restore** mà phải đọc metadata của artifact được tạo.

Có thể đặt giới hạn tài nguyên backup client theo khả năng:

~~~bash
# Giá trị minh họa, không phải khuyến nghị chung.
export HEAP_SIZE=2G

neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=/srv/neo4j-backups/orders \
  --pagecache=4G \
  --type=FULL \
  orders_graph
~~~

`HEAP_SIZE` và `--pagecache` ở đây là cấu hình tài nguyên **cho tiến trình backup client**, không phải một lệnh tự thay đổi heap/page cache của Neo4j Server. Chọn dựa trên RAM có sẵn, kích thước store và tải máy backup.

### 6.1. Vì sao nên dùng máy backup riêng?

Một lệnh backup có thể tốn CPU để nén/recovery, disk I/O và RAM. Nếu đặt luôn backup client trên node đang chịu tải giao dịch nặng, công việc sao lưu cạnh tranh với `MATCH`, traversal và `MERGE` của ứng dụng. Máy backup riêng trong **mạng tin cậy** giúp cô lập nhiều phần chi phí, mặc dù server nguồn vẫn phải gửi dữ liệu và đọc store.

Để giảm ảnh hưởng lên ứng dụng, theo dõi **p95/p99 Java API**, CPU, page cache, disk và network trong thời gian backup. Chọn khung giờ ít tải nếu SLO yêu cầu.

## 7. Sao lưu DIFF/AUTO và quản lý chuỗi

Sau khi đã có FULL đầu tiên, có thể dùng `AUTO`:

~~~bash
neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=/srv/neo4j-backups/orders \
  --type=AUTO \
  orders_graph
~~~

Hoặc yêu cầu DIFF khi điều kiện đã đáp ứng:

~~~bash
neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=/srv/neo4j-backups/orders \
  --type=DIFF \
  orders_graph
~~~

**Không cố ý chạy DIFF đầu tiên khi chưa có FULL**: cần một backup chain làm nền. Nếu giữ `AUTO`, công cụ có thể tự tạo FULL khi chưa có chain, nhưng việc đổi mode thực tế cần quan sát qua metadata, log và exit code.

### 7.1. Ví dụ lịch backup

~~~text
Chủ nhật 02:00: FULL    orders_graph
Hằng ngày 02:00: DIFF/AUTO tùy khả năng phiên bản và policy
Mỗi 15 phút:   DIFF/AUTO nếu RPO yêu cầu
Hằng ngày:     inspect chain + cảnh báo missing backup
Hằng tuần:     restore drill ở môi trường tách biệt
~~~

Lịch trên chỉ mô tả **một kịch bản học tập**. Đối với Neo4j **trước 2026.02**, lịch FULL xen giữa các DIFF có những ràng buộc về chain continuity khác; **từ 2026.02** cho phép DIFF đầu overlap FULL cha. Thiết kế lịch độc lập FULL/DIFF phải kiểm tra phiên bản và chính sách parent `--prefer-diff-as-parent` nếu có.

### 7.2. Rủi ro chuỗi dài

Một chuỗi FULL + 500 DIFF có thể giúp tiết kiệm băng thông mỗi lần backup, nhưng restore có thể tốn thời gian áp dụng nhiều thay đổi. Để giảm RTO:

- Tăng tần suất FULL theo khả năng.
- **Aggregate** chuỗi backup thành một artifact FULL đã được recovery khi tính năng/phiên bản hỗ trợ.
- Đo thời gian restore thực tế trên dữ liệu lớn, không chỉ suy từ thời gian tạo artifact.
- Chỉ xóa các artifact cũ khi chắc chắn chúng **không còn được chuỗi muốn giữ tham chiếu**.

## 8. Backup trong cluster: chọn nguồn và bảo vệ write availability

Với Neo4j Enterprise cluster, nhiều server có thể host cùng database nhưng khác vai trò/độ cập nhật tại thời điểm hỏi. Backup có thể lấy từ một thành viên đủ điều kiện, và nên chọn theo topology, transaction IDs và tác động tải.

### 8.1. Mẫu chỉ định nhiều backup endpoint

~~~bash
neo4j-admin database backup \
  --from=10.0.10.21:6362,10.0.10.22:6362,10.0.10.23:6362 \
  --to-path=/srv/neo4j-backups/orders \
  --type=AUTO \
  orders_graph
~~~

Đây là **danh sách địa chỉ ví dụ**. Không dùng các IP đó nếu không thuộc mạng thực tế; với cluster thật cần kiểm tra membership, backup listen address, firewall và trạng thái database trên từng member.

### 8.2. Đánh giá secondary/primary

Nếu topology hỗ trợ thành viên **secondary** có dữ liệu đủ mới, có thể ưu tiên backup từ secondary để giảm cạnh tranh trên primary phục vụ ghi. Tuy nhiên:

- Secondary có thể **trễ so với writer**, khiến mốc khôi phục không mới như yêu cầu.
- Một secondary có network/disk chậm có thể khiến backup không đạt deadline.
- Nếu secondary không có mặt, có thể dùng primary phù hợp theo quy trình vận hành.
- Khi cluster gặp sự cố/quorum mất, không nên tăng tải hoặc tự động restart toàn bộ chỉ vì job backup lỗi.

Theo dõi transaction IDs hoặc chỉ số replication/lag được bản Neo4j hỗ trợ để đánh giá mốc dữ liệu. Với phiên bản có `--remote-address-resolution`, DBMS có thể lựa chọn backup source phù hợp; **tùy chọn này không tồn tại trong các bản cũ**.

### 8.3. Database alias không phải database vật lý

Nếu ứng dụng Java kết nối qua alias để che tên database vật lý, lệnh online backup vẫn cần một **database thật**. Không sao lưu alias như thể nó chứa riêng các store files; hãy xác định database được alias trỏ đến, đồng thời lưu lại cấu hình alias khi thiết kế phục hồi.

## 9. Đích lưu trữ, cloud và tài nguyên tạm

Chọn nơi lưu backup phải xét **khả năng truy cập khi nguồn gặp sự cố**:

| Đích | Ưu điểm | Rủi ro cần xử lý |
| --- | --- | --- |
| Directory riêng trên backup client | Dễ chạy lệnh, kiểm tra và restore | Nếu cùng host/volume hoặc vùng lỗi với nguồn, backup cũng mất |
| Network storage | Tách được khỏi máy nguồn | Quyền mount, tốc độ I/O, sự cố mạng và ransomware |
| Object storage (S3/GCS/Azure) | Khả năng lưu trữ bền vững và lifecycle policy | IAM, encryption, versioning/retention, chi phí và staging space |
| Nhiều vùng/địa điểm | Chịu được sự cố vùng lớn | Cần kiểm tra replication và thử phục hồi từ bản ở vùng khác |

Trong các phiên bản Neo4j hỗ trợ cloud storage URI, `--to-path` có thể trỏ tới **S3, Google Cloud Storage hoặc Azure** theo cú pháp và quyền cloud phù hợp. Tuy nhiên, **backup lên cloud vẫn sử dụng staging local** để chứa store/log trước khi đóng gói hoặc upload. Phải bảo đảm `--temp-path` có đủ dung lượng:

~~~bash
# Cú pháp minh họa trên bản hỗ trợ URI S3.
neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=s3://approved-neo4j-backups/orders/ \
  --temp-path=/mnt/backup-staging \
  --type=FULL \
  orders_graph
~~~

`/mnt/backup-staging` phải là **directory trống/phù hợp** với quyền cho backup client và đủ chỗ cho dữ liệu tạm; đừng để mặc định đổ vào partition nhỏ chứa hệ điều hành. Tên bucket ví dụ không đại diện cho tài nguyên có thật. Tài khoản cloud chỉ được cấp quyền cần thiết theo vai trò, không đặt access key vào command line, shell history hoặc file backup.

### Artifact nhiều phần

Với bản **từ Neo4j 2026.09** có `--split-archive-part-size`, artifact lớn có thể được chia thành nhiều file. Các file này là **một bộ thống nhất**; mất `.backup.1` hoặc di chuyển một phần sang directory khác có thể khiến restore không thành công. Không dùng tùy chọn này trên version không hỗ trợ, và khi sao chép phải kiểm tra **đủ mọi phần**.

## 10. Sao lưu trên Aura: snapshot do dịch vụ quản lý

**Neo4j Aura không cho khách hàng truy cập máy chủ để chạy `neo4j-admin database backup` như self-managed.** Gói dịch vụ xác định các loại snapshot, tần suất, retention và khả năng restore/export. Việc restore được thao tác bằng **UI/API/quy trình do Aura cung cấp**, không dùng backup port 6362.

Quy trình khái quát:

1. Xác định **gói Aura, phiên bản instance và quyền tài khoản quản trị**.
2. Mở trang quản lý instance/database và mục **Backups/Snapshots** được gói hỗ trợ.
3. Kiểm tra **snapshot theo lịch** và khả năng tạo **on-demand snapshot**.
4. Xác định retention, loại snapshot có thể restore/export và giới hạn theo gói.
5. Chọn cách **restore vào môi trường có kiểm soát** nếu muốn thử; không chọn ghi đè database production theo thói quen.
6. Sau restore, kiểm tra URI, credential, network access, dữ liệu ứng dụng, kế hoạch đồng bộ và các integration liên quan.

### Không nhầm snapshot với khả năng export

Một snapshot có thể **restorable** trong dịch vụ nhưng **không exportable** trong cùng thời hạn. Tài liệu Aura phân biệt:

- **Scheduled full/differential snapshot** theo gói và thế hệ dịch vụ.
- **On-demand snapshot**, có giới hạn/tính năng theo gói.
- **Restorable days** và **exportable days**, có thể khác nhau.
- Một số thao tác restore ảnh hưởng **từng database** hoặc **toàn instance** khác nhau.

Do đó, trước khi hứa “có thể lấy tệp backup để chuyển sang server tự quản”, hãy xác minh tính năng **export thực tế** của snapshot/gói. Không dùng các con số retention của môi trường khác để suy luận cho AuraDB Free hoặc Professional.

Nguồn: [Neo4j Aura — Backup, export, restore and upload](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/).

## 11. Kiểm tra artifact và chuỗi backup sau khi chạy

Một job chỉ được xem là hoàn thành về mặt kỹ thuật khi:

1. Công cụ trả **exit code thành công** và log không chỉ ra lỗi.
2. Artifact tồn tại, không có file thiếu và nằm đúng repository.
3. Metadata thể hiện đúng **database name/ID**, timestamp, loại FULL/DIFF và khoảng transaction IDs.
4. Chuỗi có thể được sử dụng để restore tại mốc mong muốn.
5. Khả năng restore đã được thử nghiệm định kỳ trên database cách ly.

### 11.1. Inspect metadata

~~~bash
neo4j-admin database backup \
  --inspect-path=/srv/neo4j-backups/orders
~~~

Lệnh `--inspect-path` đọc thông tin artifact (không tạo backup mới). Metadata có thể bao gồm:

| Trường | Ý nghĩa khi kiểm tra |
| --- | --- |
| `FILE` | Đường dẫn artifact, cần còn tồn tại và đọc được |
| `DATABASE` / `DATABASE ID` | Không nhầm bản backup của database khác |
| `TIME` | Mốc backup, ảnh hưởng độ mới khi restore |
| `FULL` | `true` cho FULL, `false` cho DIFF |
| `LOWEST TX` / `HIGHEST TX` | Phạm vi transaction IDs của artifact |
| `COMPRESSED` / `RECOVERED` | Tùy phiên bản/công cụ, trạng thái nén và recovery |

**Inspect không phải kiểm chứng toàn bộ tính nhất quán vật lý**. Một artifact có metadata hợp lý vẫn có thể không restore được vì thiếu phần chuỗi, lỗi storage, incompatibility hoặc thiếu dung lượng.

### 11.2. Aggregate chuỗi khi phù hợp

Với phiên bản có lệnh `neo4j-admin backup aggregate` (tên hiện đại từ 2025.01):

~~~bash
# Thực hành trên repository backup được phép.
# Giữ lại artifact cũ trong lúc kiểm thử, tránh xóa chuỗi đang sử dụng.
neo4j-admin backup aggregate \
  --from-path=/srv/neo4j-backups/orders \
  --keep-old-backup=true \
  orders_graph
~~~

Lệnh này có thể kết hợp FULL + DIFF, thực hiện recovery và tạo artifact FULL dùng phục hồi. Nó **không miễn phí về CPU, I/O hoặc dung lượng tạm**. Trong các bản cũ hơn, tên lệnh aggregate có thể khác; cần kiểm tra `--help`.

### 11.3. Consistency check

Neo4j có công cụ `neo4j-admin database check` cho việc kiểm tra tính nhất quán trong phạm vi được phiên bản hỗ trợ. Trước khi dùng với artifact:

- Xác minh phiên bản có hỗ trợ `--from-path` cho backup/dump (tùy chọn này thay đổi trong dòng 2025.x).
- Nếu công cụ yêu cầu backup đã recovery, aggregate trước.
- Chạy ở máy và thời điểm đủ RAM/disk; kiểm tra exit code và report.
- Phân biệt **consistency vật lý** với **tính đúng của nghiệp vụ**: một đồ thị có constraint và relationship sai nghiệp vụ vẫn có thể qua kiểm tra cấu trúc.

Tham khảo [Neo4j — Consistency checker](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/).

## 12. Restore drill: kiểm chứng backup bằng một lần phục hồi thật

**Cảnh báo:** Restore là thao tác nhạy cảm. **Không chạy các ví dụ dưới đây trên database production đang phục vụ khách hàng.** Hãy dựng một server/DBMS thử nghiệm có quyền, cấu hình và storage riêng, dùng bản backup copy được duyệt.

### 12.1. Quy trình restore an toàn

1. Chọn **mốc phục hồi và artifact FULL/DIFF** theo metadata; kiểm tra đủ chain.
2. Dựng một **Neo4j Enterprise lab** hoặc môi trường được phiên bản tài liệu cho phép, có cấu hình và version tương thích.
3. Bảo đảm database đích **chưa được tạo hoặc đã dừng theo đúng quy trình**; tránh ghi đè dữ liệu khác.
4. Chạy restore bằng `neo4j-admin database restore` với `--from-path` tới artifact/chuỗi phù hợp.
5. Tạo/start database sau restore theo hướng dẫn của phiên bản (nếu cần), rồi kiểm tra status online.
6. Chạy consistency check và **query đối soát nghiệp vụ**, đo thời gian đến khi API có thể sử dụng trở lại.
7. Tài liệu hóa sai lệch so với RPO/RTO và sửa runbook.

### 12.2. Ví dụ lệnh chỉ dành cho lab độc lập

~~~bash
# Đường dẫn phải trỏ tới artifact thực tế trong một chuỗi đầy đủ.
# Database đích orders_graph_restored CHƯA tồn tại trên lab DBMS.
neo4j-admin database restore \
  --from-path=/srv/neo4j-backups/orders/orders_graph-TIMESTAMP.backup \
  orders_graph_restored
~~~

`orders_graph-TIMESTAMP.backup` là **placeholder**; lấy tên thật bằng lệnh inspect. Khi chọn một artifact DIFF cuối chuỗi, công cụ sẽ cần tìm các artifact liên quan để phục hồi đủ transaction. Theo tài liệu, sau restore vào database mới thường phải thực hiện lệnh **`CREATE DATABASE orders_graph_restored`** trong ngữ cảnh `system` (Enterprise) để đăng ký database, rồi xác minh online.

**Không thêm `--overwrite-destination=true` như thói quen.** Ghi đè một database đang tồn tại có thể phá dữ liệu, và tài liệu Neo4j cảnh báo việc ghi đè trong cluster **không an toàn** do cluster state; với cluster, nên khôi phục vào **database mới** theo quy trình cụ thể.

### 12.3. Kiểm tra sau restore bằng Cypher

~~~cypher
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

~~~cypher
// Chạy trên database đã restore, không phải database nguồn.
MATCH (c:Customer)
RETURN count(c) AS customerCount;
~~~

~~~cypher
// Kiểm tra một liên kết nghiệp vụ trọng yếu.
MATCH (c:Customer)-[:PLACED]->(o:Order)
RETURN count(*) AS placedEdges;
~~~

~~~cypher
SHOW CONSTRAINTS
YIELD name, type
RETURN name, type
ORDER BY name;
~~~

Số lượng node/relationship chỉ là **sanity check**. Cần có phép đối soát theo business ID và trạng thái nghiệp vụ, ví dụ `Order.orderId`, ownership của `PLACED`, khóa `Customer.customerId`, kết quả truy vấn đường đi, index/constraint cần thiết và thời điểm commit cuối cùng phục hồi được.

### 12.4. Khả năng phục hồi ứng dụng

Khi công cụ restore đã thành công, ứng dụng có thể vẫn chưa hoạt động vì:

- Database name/alias, quyền user và vai trò chưa được phục hồi đúng.
- URI, TLS certificate, routing/cluster hoặc network policy chưa trỏ tới máy mới.
- Plugin APOC/GDS, custom procedures hoặc `neo4j.conf` chưa được tái triển khai.
- Job đồng bộ Kafka/CDC, search index, cache, bookmark hoặc checkpoint chưa được rà soát.
- Dữ liệu sau mốc backup cần replay/đối soát với các hệ thống có thẩm quyền khác.

**RTO đo đến khi người dùng thực hiện được các thao tác trọng yếu**, không chỉ đến khi command restore báo success.

## 13. Các lưu ý về metadata, user/role và tính liên hệ thống

### 13.1. Database `system` và RBAC

Trong Neo4j Enterprise multi-database, `system` chứa thông tin quản trị. Tài liệu backup khuyên **lên kế hoạch sao lưu các database, bao gồm `system`**. Tùy lựa chọn `--include-metadata`, artifact của database cũng có thể chứa phần metadata user/role liên quan.

Tuy nhiên, **không mặc định backup một database đã mang toàn bộ user/role/privilege và cấu hình DBMS**. Khi restore, metadata người dùng/vai trò có thể cần chạy script tái tạo do công cụ tạo, kiểm tra xung đột và quyền quản trị. Luôn backup/quản lý **cấu hình, secret, chứng chỉ TLS và định nghĩa plugin** bằng quy trình phù hợp, tách khỏi artifact dữ liệu.

### 13.2. External systems không nằm trong Neo4j backup

Ví dụ Order Service dùng PostgreSQL làm nguồn giao dịch, Neo4j làm read model và Kafka làm broker. Một backup Neo4j chỉ phản ánh **trạng thái graph tại mốc đó**; nó không backup đồng thời bảng PostgreSQL, Kafka offsets, object storage hoặc search index.

Khi restore:

1. Xác định graph đang thiếu bao nhiêu event so với source of truth.
2. Tìm mốc **source version/watermark** có thể đối soát.
3. Replay hoặc rebuild projection bằng business ID, idempotent upsert/delete.
4. Kiểm tra event xóa, đổi ownership, trạng thái out-of-order và dữ liệu mồ côi.
5. Chỉ đưa API phụ thuộc độ mới về trạng thái ready khi đáp ứng freshness contract.

### 13.3. Neo4j CDC sau restore

Nếu hệ thống đọc Neo4j CDC, restore có thể thay đổi vòng đời database/transaction log và làm **change identifier/cursor cũ không còn dùng được**. Mode `txLogEnrichment` có thể cần được cấu hình lại khi tạo database mới. Không tự khởi chạy consumer với cursor cũ rồi coi mọi event đã được bảo toàn.

Thiết kế recovery CDC phải gồm:

- Xác định điểm cắt nhất quán, nguồn event nào còn giữ được.
- Kiểm tra database đã bật CDC trong edition/version hỗ trợ.
- Rebootstrap/reconcile các hệ downstream có thể mất sự kiện.
- Lưu lại bằng chứng mốc đồng bộ đã phục hồi.

### 13.4. Graph Data Science và state trong bộ nhớ

Named graph trong **GDS graph catalog** là trạng thái phân tích trong bộ nhớ, không phải node/relationship gốc lưu trong store. Sau restore/start lại, các graph projection trong bộ nhớ có thể phải được **project lại**, các mô hình phân tích/feature không nằm trong backup tùy chính sách GDS và edition. Đừng đánh giá một lần restore là đầy đủ chỉ vì Cypher `MATCH` chạy tốt nếu ứng dụng còn phụ thuộc job GDS và cache.

## 14. Bảo mật bản backup và phục hồi

Backup có thể chứa **toàn bộ dữ liệu nhạy cảm** mà user Neo4j thông thường bị hạn chế đọc. Nếu một người tải được tệp backup, lớp RBAC của database nguồn có thể không còn bảo vệ được nội dung offline. Vì vậy backup repository là **tài sản có độ nhạy cao**.

Các nguyên tắc:

- **Mạng:** chặn truy cập công khai vào backup port `6362`; chỉ cho backup client được chỉ định đi tới endpoint, dùng TLS theo chính sách.
- **Quyền OS:** thư mục backup và file artifact chỉ đọc được bởi tài khoản vận hành cần thiết; tránh đặt backup trong `/tmp` hoặc thư mục chia sẻ rộng.
- **Mã hóa:** bảo vệ dữ liệu khi truyền và khi lưu, quản lý khóa ngoài repository; định nghĩa quy trình khôi phục khóa khi có sự cố.
- **Phân quyền IAM:** cấp tối thiểu quyền ghi/đọc/list/delete cho job và người vận hành; tách quyền tạo backup khỏi quyền xóa backup khi có thể.
- **Immutability/retention:** sử dụng cơ chế versioning hoặc object lock phù hợp để hạn chế xóa/chỉnh sửa không được phép, đồng thời tuân thủ quy định giữ/xóa dữ liệu.
- **Cô lập:** lưu một bản ở failure domain khác; cân nhắc mô hình 3-2-1 và kiểm thử từ bản off-site.
- **Audit:** log người tạo/tải/xóa artifact, thay đổi backup policy và kết quả restore drill; không đưa secret vào command logs.

Đặc biệt: cho phép backup port truy cập từ Internet có thể tạo **lỗ hổng sao chép dữ liệu database**. Không giải quyết lỗi kết nối backup bằng cách mở `0.0.0.0:6362` không có firewall/TLS.

## 15. Giám sát backup: đo thành công chứ không chỉ có cron

Một job backup phải xuất **telemetry** có thể cảnh báo:

| Chỉ số | Ý nghĩa | Cảnh báo khi |
| --- | --- | --- |
| `last_successful_backup_at` | Thời điểm bản backup hợp lệ gần nhất | Quá xa so với lịch/RPO |
| `backup_duration_seconds` | Thời gian tạo/copy/compress/recovery | Tăng mạnh, vượt cửa sổ |
| `backup_exit_code` | Kết quả công cụ | Khác thành công hoặc không có log job |
| `backup_type` | FULL/DIFF/AUTO thực sự tạo được | DIFF thất bại hoặc FULL ngoài dự kiến |
| `backup_bytes` / tốc độ truyền | Dung lượng và network I/O | Tăng/giảm bất thường, đích đầy |
| `backup_chain_health` | Chuỗi và transaction IDs có hợp lệ | Thiếu artifact, chain gap |
| `restore_drill_result` | Khả năng phục hồi đã được chứng minh | Diễn tập lỗi, quá RTO |
| `backup_repository_free_bytes` | Dung lượng còn trống | Gần đầy hoặc tốc độ tăng bất thường |
| `production_latency_during_backup` | Tác động lên workload | p95/p99 giao dịch vượt SLO |

Không đưa `databaseName` hoặc ID nghiệp vụ nhạy cảm tự do làm nhãn metric nếu số lượng lớn. Ghi rõ **environment, database, backup job, source server, artifact time** với tập nhãn được kiểm soát.

### 15.1. Bẫy “cron chạy nên backup OK”

Một scheduler có thể hoàn tất lệnh shell nhưng chỉ là “đã khởi chạy”, không kiểm tra exit code thật của `neo4j-admin`. Cần quan sát:

1. Job bắt đầu và kết thúc lúc nào?
2. Công cụ trả **exit code bao nhiêu**?
3. Artifact có được tạo, đầy đủ và đúng đích?
4. Inspect có nhìn thấy mốc transaction mới?
5. Lần restore drill gần nhất **thành công đến mức nào**?

Nếu backup hôm nay lỗi, còn backup thành công gần nhất đã cách ba ngày, RPO thực tế không phải 15 phút dù lịch được đặt “mỗi 15 phút”.

### 15.2. Cảnh báo phù hợp

- **Critical:** không còn bản backup đáp ứng ngưỡng phục hồi, artifact/chain bị thiếu, repository bị xóa bất thường hoặc backup source không truy cập được kéo dài.
- **Warning:** dung lượng gần đầy, backup duration tăng, restore drill vượt RTO, backup tác động lớn lên OLTP.
- **Informational:** FULL theo lịch, thay đổi backup client version, thay đổi chính sách retention có phê duyệt.

Thiết kế alert dựa trên **tác động tới khả năng phục hồi**, không chỉ trạng thái CPU một lần đo.

## 16. Runbook: sự cố backup và cách xử lý

### Trường hợp A — Không kết nối được backup endpoint

Triệu chứng: `Connection refused`, timeout hoặc TLS handshake failure khi gọi `neo4j-admin database backup`.

1. Xác nhận **Enterprise**, database đích online và backup service đã bật.
2. Kiểm tra `server.backup.listen_address` đúng interface/cổng, phân biệt localhost với remote client.
3. Kiểm tra network path, firewall, Docker port/NetworkPolicy và proxy.
4. Nếu dùng TLS, kiểm tra trust store, CA, hostname, key/cert và version TLS.
5. Thử lại trong phạm vi được phép; không mở backup port công khai để chữa cháy.

### Trường hợp B — DIFF thất bại hoặc chain bị đứt

1. Dùng `--inspect-path` để xem đầy đủ FULL và DIFF cùng database ID, transaction IDs.
2. Xác minh artifact cha chưa bị xóa/move và backup destination không bị trộn của nhiều nguồn không tương thích.
3. Kiểm tra log có thiếu transaction log cần thiết hoặc lỗi retention không.
4. Nếu policy cho phép, tạo **FULL mới** bằng công cụ chính thức; điều chỉnh lịch retention/aggregation.
5. Đối chiếu RPO từ thời điểm FULL/DIFF gần nhất **thực sự phục hồi được**.

### Trường hợp C — Không đủ dung lượng staging

1. Xác định `--to-path` và `--temp-path` là **hai phạm vi dung lượng khác nhau**, đặc biệt khi ghi cloud.
2. Kiểm tra dung lượng tuyệt đối, inodes/quota, tốc độ ghi và quyền file.
3. Mở rộng staging trên volume phù hợp; không xóa các artifact trong chuỗi còn cần.
4. Chạy lại và ghi nhận peak space để capacity planning.

### Trường hợp D — Backup làm truy vấn ứng dụng chậm

1. Xem CPU/disk/network trên Neo4j source và backup client, API p95/p99, số transaction.
2. Giảm số job đồng thời hoặc chọn member khác đủ mới trong cluster.
3. Chuyển nén/aggregation sang backup client thích hợp, điều chỉnh page cache/heap có cơ sở.
4. Dời lịch FULL hoặc chia tải; kiểm tra tác động tới RPO/RTO.
5. **Không** ưu tiên backup “nhanh bằng mọi giá” nếu nó làm ứng dụng ghi thanh toán lỗi.

### Trường hợp E — Restore xong nhưng ứng dụng không chạy

1. Xác minh database đã được đăng ký/start và `currentStatus` đúng.
2. Kiểm tra users/roles, alias, database name, TLS/URI, network và Java Driver routing.
3. Xác minh index/constraint, sample Cypher lookup và đường đi trọng yếu.
4. Phục hồi plugin/config và rebuild graph projection/caches nếu ứng dụng cần.
5. Reconcile những hệ thống ngoài Neo4j, CDC/checkpoint/outbox và dữ liệu mất sau mốc backup.
6. Chỉ chuyển traffic khi đạt tiêu chí **read/write availability** và dữ liệu nghiệp vụ được chấp nhận.

## 17. Bài thực hành: một chu trình FULL → DIFF → inspect → restore drill

**Mục tiêu:** trên môi trường **Neo4j Enterprise lab riêng**, chứng minh rằng bản sao lưu trực tuyến trong lúc database hoạt động có thể phục hồi được và đánh giá sơ bộ RPO/RTO. Không thực hành restore hoặc đổi backup listener trên production.

### Bước 1 — Thiết lập dữ liệu mẫu

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
MERGE (c:Customer {customerId: 'C-BACKUP-01'})
MERGE (o:Order {orderId: 'O-BACKUP-01'})
SET o.status = 'CREATED', o.totalCents = 100000
MERGE (c)-[:PLACED]->(o);
~~~

### Bước 2 — Cấu hình và chạy FULL

Xác nhận bản Enterprise, backup service, quyền thư mục, backup client và backup port ở mạng riêng. Chạy:

~~~bash
neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=/srv/neo4j-backups/lab \
  --type=FULL \
  neo4j
~~~

Tên `neo4j` ở đây chỉ là **database lab ví dụ**. Không tự giả định mọi hệ thống có database tên này hoặc backup mọi database khi chỉ cần một.

### Bước 3 — Tạo thay đổi và chạy DIFF

~~~cypher
MATCH (o:Order {orderId: 'O-BACKUP-01'})
SET o.status = 'PAID';
~~~

~~~bash
neo4j-admin database backup \
  --from=10.0.10.12:6362 \
  --to-path=/srv/neo4j-backups/lab \
  --type=DIFF \
  neo4j
~~~

**Kiểm tra:** lệnh thứ hai tạo DIFF thành công, đúng database và đúng chain; không dựa riêng vào tên file để xác định loại backup.

### Bước 4 — Inspect và ghi nhận mốc

~~~bash
neo4j-admin database backup \
  --inspect-path=/srv/neo4j-backups/lab
~~~

Ghi lại artifact nào là FULL/DIFF, thời gian, database ID và khoảng transaction IDs. Đánh giá nếu mất DIFF, sẽ chỉ có thể phục hồi tới mức nào theo mốc FULL còn lại.

### Bước 5 — Restore vào môi trường cách ly

1. Dựng Neo4j lab target **tách biệt** với nguồn.
2. Chọn đúng artifact DIFF cuối chuỗi và đầy đủ các file liên quan.
3. Thực hiện `neo4j-admin database restore` theo tài liệu phiên bản, tạo database mới nếu cần.
4. Kiểm tra `O-BACKUP-01` đã có `status='PAID'` hay chưa:

~~~cypher
MATCH (o:Order {orderId: 'O-BACKUP-01'})
RETURN o.orderId AS id, o.status AS status, o.totalCents AS totalCents;
~~~

5. Kiểm tra relationship và constraint, đo thời gian từ lúc bắt đầu phục hồi đến khi query đọc/ghi lab hoạt động.

Nếu restore từ **chỉ FULL trước khi thay đổi** thì trạng thái `CREATED` là kết quả phù hợp; nếu restore chain gồm DIFF chứa transaction chuyển sang `PAID` thì kỳ vọng `PAID`. Đó là bài học về **mốc RPO và chain continuity**.

### Bước 6 — Mô phỏng lỗi có kiểm soát

Không cần xóa dữ liệu thật. Dùng **bản sao thư mục backup trong lab** để thử:

- Bỏ một artifact DIFF khỏi **bản copy**, không sửa repository chính.
- Cấp sai quyền đọc cho bản copy hoặc đặt sai `--temp-path` rồi quan sát thông báo lỗi.
- Sử dụng tên database khác và xác minh không restore nhầm.
- Đo thời gian restore khi có nhiều DIFF; cân nhắc aggregate nếu RTO chưa đạt.

### Câu hỏi tự kiểm tra

**1. Neo4j Community có thể online backup bằng cách bật `server.backup.enabled=true` không?**

Không. `neo4j-admin database backup` là tính năng Enterprise; setting không biến Community thành Enterprise.

**2. Vì sao không coi cluster replication là backup?**

Vì thay đổi sai/xóa nhầm có thể được sao chép tới các thành viên; replication phục vụ sẵn sàng, backup phục vụ phục hồi mốc dữ liệu.

**3. Job chạy DIFF mỗi 15 phút nhưng lần thành công gần nhất cách 2 giờ. RPO thực tế gần 15 phút không?**

Không. Cần tính từ **mốc phục hồi hợp lệ gần nhất** tới sự cố và xét kết quả backup/chain thực tế.

**4. Vì sao backup qua S3 vẫn cần `--temp-path` có dung lượng?**

Vì quá trình backup sử dụng staging local trước khi đẩy artifact lên cloud; object storage không thay thế tài nguyên đĩa tạm.

**5. Backup port 6362 có thể mở Internet nếu đã dùng mật khẩu Bolt không?**

Không. Giao thức backup và Bolt khác nhau; backup endpoint phải được bảo vệ bằng firewall/mạng riêng và TLS theo chính sách.

**6. Có thể dùng `--overwrite-destination=true` để restore thẳng database trên cluster đang hoạt động không?**

Không nên: đây là tình huống nguy hiểm vì cluster state; tài liệu khuyến nghị **restore thành database mới** và làm theo quy trình cluster được hỗ trợ.

**7. Sau restore, `MATCH` chạy tốt nhưng CDC consumer không hoạt động. Tại sao?**

Cấu hình enrichment, cursor/transaction log, checkpoint hoặc vòng đời database có thể thay đổi; cần tái bootstrap/reconcile thay vì mặc định dùng cursor cũ.

## 18. Checklist triển khai và vận hành

- [ ] Xác nhận **Neo4j edition, version, license và mô hình triển khai**; không dùng online backup Enterprise với Community/Aura.
- [ ] Định nghĩa **RPO/RTO** và mốc phục hồi cho từng database/dịch vụ.
- [ ] Liệt kê database vật lý cần sao lưu, bao gồm `system` khi phù hợp, và tài sản ngoài database cần tái dựng.
- [ ] Cấu hình backup service và địa chỉ listen **chỉ ở mạng được phép**; bảo vệ cổng 6362 bằng firewall/TLS.
- [ ] Dùng backup client/version phù hợp, quyền OS và IAM tối thiểu.
- [ ] Chọn FULL/DIFF/AUTO theo phiên bản, tạo FULL ban đầu và kiểm tra chain.
- [ ] Theo dõi transaction ID của source/backup, đặc biệt trong cluster.
- [ ] Tách destination khỏi nguồn; bảo vệ artifact bằng encryption, retention, versioning/immutability phù hợp.
- [ ] Cấp đủ **disk destination, staging, heap, page cache, CPU và network** cho backup.
- [ ] Xác minh exit code, artifact metadata bằng `--inspect-path` và chain continuity.
- [ ] Thực hiện consistency check/aggregation theo đúng điều kiện phiên bản.
- [ ] Restore drill định kỳ vào server/database **cách ly**, không ghi đè production.
- [ ] Đối chiếu dữ liệu Cypher: node, relationship, business IDs, indexes/constraints và transaction mốc.
- [ ] Đo RTO đến lúc ứng dụng **thực sự phục vụ**, không chỉ đến khi CLI xong.
- [ ] Lưu runbook cho roles, alias, secrets, plugins, cấu hình, CDC, cache và đồng bộ liên hệ thống.
- [ ] Có cảnh báo khi **last successful backup** quá cũ, chain thiếu, destination gần đầy hoặc restore drill lỗi.
- [ ] Kiểm tra định kỳ **chính sách snapshot/retention của Aura** nếu sử dụng dịch vụ quản lý.
- [ ] Diễn tập thiếu disk, mất artifact, sai version, mất quyền storage và kịch bản cần phục hồi vùng khác.

## Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Back up an online database](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/)
- [Neo4j Operations Manual — Backup modes](https://neo4j.com/docs/operations-manual/current/backup-restore/modes/)
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual — Aggregate a database backup chain](https://neo4j.com/docs/operations-manual/current/backup-restore/aggregate/)
- [Neo4j Operations Manual — Restore a database backup](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-backup/)
- [Neo4j Operations Manual — Check database consistency](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/)
- [Neo4j Operations Manual — Offline database dump](https://neo4j.com/docs/operations-manual/current/backup-restore/offline-backup/)
- [Neo4j Operations Manual — Backup ports and configuration](https://neo4j.com/docs/operations-manual/current/configuration/ports/)
- [Neo4j Operations Manual — Docker online backup](https://neo4j.com/docs/operations-manual/current/docker/backup-restore/)
- [Neo4j Aura — Backup, export, restore and upload](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/)

**Kết luận:** Sao lưu trực tuyến Neo4j là năng lực có **điều kiện theo edition và dịch vụ**. Với **Enterprise self-managed**, `neo4j-admin database backup` cho phép tạo FULL/DIFF trong lúc database còn online, nhưng phải quản lý backup endpoint, TLS, tài nguyên, chuỗi transaction và quyền lưu trữ. Với **Aura**, snapshot được quản lý theo gói dịch vụ; với **Community**, không dùng lệnh Enterprise online backup thay cho offline dump. **Bản backup chỉ đáng tin khi có thể restore, đối soát dữ liệu và đưa ứng dụng hoạt động trở lại trong RPO/RTO đã cam kết.**

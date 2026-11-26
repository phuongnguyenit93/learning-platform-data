# Xử lý mất dữ liệu hoặc hỏng lưu trữ theo quy trình đã diễn tập trong Neo4j

## 1. Mục tiêu: phục hồi có kiểm chứng, không “thử sửa dữ liệu” trực tiếp

Trong Neo4j, một database property graph lưu **node**, **relationship**, **property**, schema index/constraint và thông tin phục vụ transaction. Khi dữ liệu bị xóa nhầm, một ổ đĩa lỗi hoặc database không thể khởi động, hành động đầu tiên **không phải** là xóa file nghi hỏng, chạy lại các lệnh `MERGE` hay khởi động lại liên tục.

Mục tiêu của một quy trình phục hồi tốt là:

1. **Ngăn mất thêm dữ liệu** và tránh làm hỏng bằng chứng/chứng cứ kỹ thuật.
2. **Xác định phạm vi sự cố**, mức ảnh hưởng, thời điểm dữ liệu còn đúng gần nhất.
3. **Chọn bản sao lưu và phương án khôi phục** phù hợp edition, cấu trúc cụm và mục tiêu khôi phục.
4. **Dựng dữ liệu trên môi trường cách ly trước**, kiểm tra tính nhất quán cả store lẫn dữ liệu nghiệp vụ.
5. **Mở lại dịch vụ theo từng bước**, có kế hoạch chuyển lưu lượng và rollback.
6. **Đối soát phần giao dịch có nguy cơ mất**, cập nhật hậu kiểm và cải tiến lần diễn tập tiếp theo.

Chủ đề thuộc chương **Sao lưu và phục hồi** của Neo4j. Các ví dụ tập trung vào vận hành database dùng Cypher, Java Driver và Spring Data Neo4j, không phải kỹ thuật xử lý file nhị phân nội bộ của Neo4j.

> **Giới hạn an toàn:** lệnh `restore`/`load` có thể thay thế database hiện có khi dùng `--overwrite-destination`. Bài cố ý sử dụng **database thử nghiệm mới** khi minh họa. Không áp dụng lệnh phá hủy hoặc thay thế store trên production khi chưa có change approval, bản sao nguồn và phương án quay lại.

## 2. Phân loại sự cố trước khi quyết định restore

Hai biểu hiện đều là “mất dữ liệu” nhưng có cách xử lý hoàn toàn khác nhau.

| Dấu hiệu | Nguyên nhân khả dĩ | Ưu tiên đầu tiên | Phương án thường xét |
| --- | --- | --- | --- |
| Một node/relationship bị xóa hoặc cập nhật sai | Lỗi Cypher, script, ứng dụng, quyền truy cập | **Dừng nguồn ghi sai**, xác định transaction/thời điểm | Point-in-time recovery, dựng bản sao để đối chiếu, khôi phục nghiệp vụ có kiểm soát |
| Database mất dữ liệu sau rollback hoặc import/load | Đổi đích, overwrite, sai pipeline | Cô lập job gây sự cố, giữ log và bản sao | Restore backup gần nhất, tính toán lại phần thay đổi |
| Một host/disc của cluster lỗi, thành viên còn lại khỏe | Hardware, node crash | Kiểm tra quorum, leader và trạng thái member | Failover/replacement/reseed đúng quy trình cluster, **chưa nhất thiết restore toàn bộ graph** |
| Database không `ONLINE` hoặc báo corruption | Store/index/log lỗi, storage bị cắt, sự cố filesystem | Dừng ghi, giữ nguyên store/log, xem log và health | Kiểm tra offline; restore một bản đã xác minh, hoặc xử lý với Neo4j Support |
| Mất storage volume/persistent disk | Disk/volume bị mất, thao tác hạ tầng | Ngừng các tác vụ có thể ghi lên đích, giữ chứng cứ | Dựng lại storage, restore bản sao lưu độc lập |
| Mất/thiếu một file trong chuỗi backup | Retention sai, copy thiếu, đối tượng cloud bị xóa | Ngừng cleanup/rotation | Tìm chain còn đầy đủ hoặc chọn full backup khác |
| Dữ liệu có dấu hiệu bị thay đổi trái phép | Lộ credential, ransomware, truy cập bất thường | Incident bảo mật: cách ly quyền, bảo vệ backup, audit | Restore **clean recovery point**, rotation secret, xác minh không tái nhiễm |
| Ứng dụng trả dữ liệu cũ nhưng database khỏe | Cache, read replica lag, bookmark/routing | Kiểm tra dữ liệu gốc và độ trễ đồng bộ | Sửa consistency/cache, **không restore tùy tiện** |

**Không đồng nhất độ sẵn sàng và khả năng phục hồi dữ liệu.** Cluster có thể giúp tiếp tục phục vụ khi một member hỏng, nhưng những thao tác `DELETE` hợp lệ về mặt transaction có thể đã được nhân bản sang các member khác. Cluster **không thay thế backup độc lập**.

## 3. Xác lập RPO và RTO trước khi sự cố xảy ra

### 3.1. Hai chỉ số không thể đánh tráo

- **RPO — Recovery Point Objective:** khoảng thời gian dữ liệu tối đa được phép mất sau sự cố. Ví dụ RPO 15 phút nghĩa là mục tiêu có thể khôi phục đến trạng thái cách thời điểm sự cố **không quá 15 phút**.
- **RTO — Recovery Time Objective:** thời gian tối đa từ lúc phát hiện/ghi nhận sự cố đến khi dịch vụ được khôi phục ở mức chấp nhận được, **bao gồm kiểm tra và mở lại lưu lượng**.

Ví dụ chính sách của dịch vụ đặt hàng:

| Mục tiêu | Giá trị minh họa | Hệ quả |
| --- | --- | --- |
| RPO | 15 phút | Cần các điểm backup/transaction logs đủ dày và thành công |
| RTO | 90 phút | Cần backup đã kiểm tra, restore đủ nhanh và một quy trình chuyển lưu lượng |
| Mức xác minh | Store consistency + counts/constraints + đơn hàng mẫu | Không tính “restore xong file” là dịch vụ đã phục hồi |
| Phạm vi | Graph `orders` + service account + kết nối downstream | Cần kiểm tra cả quyền, driver và tích hợp CDC/event |

**RPO và RTO là mục tiêu, không phải lời bảo đảm bởi việc đặt lịch.** Backup thất bại, mất một mắt xích differential, chậm truyền từ object storage hoặc restore chưa được diễn tập đều có thể khiến thực tế tệ hơn.

### 3.2. Dòng thời gian minh họa

```text
10:00    10:15    10:30    10:42       10:50
  |---------|--------|---------|-----------|
 FULL       DIFF     DIFF     Xóa nhầm     Phát hiện
                           10:42:17
                                |
                       Clean recovery target:
                       trước 10:42:17
```

Nếu có chuỗi full/differential đủ transaction logs, Enterprise có thể phục hồi đến một thời điểm hoặc transaction ID phù hợp. **Không nhất thiết chọn “backup mới nhất”**: với xóa nhầm lúc 10:42, một backup chứa thay đổi xóa nhầm có thể không phải điểm phục hồi an toàn nhất.

Khi phục hồi theo timestamp, chuyển về **UTC** theo yêu cầu của `--restore-until`. Nếu sự cố được ghi nhận theo giờ Việt Nam (UTC+07), phải đổi giờ trước khi chọn điểm. Timestamp và transaction ID phục hồi đều áp dụng ranh giới **loại trừ** theo tài liệu: các transaction commit **trước** thời điểm/transaction ID được chọn mới được áp dụng.

## 4. Công cụ có thể dùng tùy edition và môi trường

| Môi trường | Tạo bản sao lưu | Phục hồi/kiểm tra | Điều kiện |
| --- | --- | --- | --- |
| **Neo4j Community tự quản lý** | `neo4j-admin database dump` khi DBMS offline | `neo4j-admin database load` khi DBMS offline; `neo4j-admin database check` offline | Không có online backup/differential backup của Enterprise |
| **Neo4j Enterprise tự quản lý** | `neo4j-admin database backup` khi database online, full/differential; `dump` khi offline | `restore`, `load`, `backup aggregate`, `database check` | Backup service, quyền file, version tương thích và quy trình standalone/cluster |
| **Enterprise cluster** | Online backup từ server phù hợp (khuyến nghị backup client riêng) | Theo quy trình URI/seeder/recreate/copy phù hợp với cluster | **Không overwrite file đích trực tiếp trên cluster** như standalone |
| **Neo4j AuraDB** | Snapshot/backup do dịch vụ quản lý theo tier | Restore/export/create từ snapshot hoặc backup qua Aura Console/API được phép | Không tự chạy `neo4j-admin database backup/restore` bên trong Aura |
| **Cơ sở dữ liệu composite** | Sao lưu **các database thành phần** | Kiểm tra/restore từng thành phần và cấu hình liên quan | Các lệnh admin backup/check không áp dụng trực tiếp cho composite database |

Với AuraDB, tính năng và thời gian giữ bản sao **khác theo tier**. Theo tài liệu Aura hiện hành:
- **Free:** không có lịch snapshot tự động như các tier trả phí.
- **Professional:** thông thường full snapshot hằng ngày, retention theo chính sách tier.
- **Business Critical:** có full snapshot và differential snapshot thường xuyên hơn.
- **Virtual Dedicated Cloud:** chính sách chi tiết phụ thuộc dòng version và phương án dịch vụ.

Không dùng bảng retention cũ để suy ra dữ liệu chắc chắn còn có thể phục hồi. **Kiểm tra trực tiếp điểm khôi phục hiện còn trong Aura Console** trước khi cam kết RPO.

### 4.1. Phân biệt `backup/restore` và `dump/load`

**Enterprise online backup**:
- Hỗ trợ full và differential.
- Lưu thành các backup artifact có metadata như database ID, thời gian và phạm vi transaction ID.
- Có thể dùng `--restore-until` khi có chuỗi transaction log đáp ứng điểm cần phục hồi.
- Có thể cần `aggregate` để hợp nhất chuỗi và chuẩn bị cho kiểm tra nhất quán.

**Offline dump**:
- Là archive của database tại thời điểm dừng và dump.
- Phù hợp Community hoặc kế hoạch bảo trì chủ động, nhưng không tạo một chuỗi full+differential để replay đến thời điểm tùy ý.
- **Không tự bao gồm metadata user/role** như cơ chế backup Enterprise có tùy chọn metadata.

**Không sao chép trực tiếp thư mục `data/databases/<name>` và `data/transactions/<name>` bằng thao tác copy/paste khi database đang chạy** rồi gọi đó là backup hợp lệ. Neo4j không hỗ trợ cách này như một phương án thay thế backup; có thể tạo bản dữ liệu không nhất quán.

## 5. Runbook ứng phó sự cố theo các mốc thời gian

### 5.1. Trong 0–5 phút: xác nhận và ngăn thiệt hại lan rộng

1. Ghi **Incident ID**, người điều phối, thời điểm phát hiện, các dịch vụ chịu ảnh hưởng.
2. Xác định biểu hiện: đọc sai, ghi lỗi, database `OFFLINE`, storage mất, một member hỏng hay mất toàn bộ cluster.
3. **Dừng nguồn ghi sai**: vô hiệu hóa job/script gây lỗi, chặn API ghi, chuyển ứng dụng sang chế độ bảo trì nếu cần.
4. Nếu nghi xâm nhập, thực hiện quy trình an ninh: cô lập credential, tạm dừng integration đáng nghi, bảo vệ bản backup sạch.
5. Ngừng các job tự động có thể **xóa, ghi đè hoặc dọn dẹp backup** trong lúc điều tra.
6. **Không chạy lại lệnh restore/load/import hoặc xóa transaction log** trước khi biết database đích và điểm phục hồi mong muốn.

Dừng ghi tại **nguồn ứng dụng** có thể an toàn hơn chỉ tắt một Neo4j member trong cluster; với cluster, member khác vẫn có thể tiếp nhận ghi. Cần người điều phối xác định ranh giới chuyển dịch vụ rõ ràng.

### 5.2. Trong 5–20 phút: thu bằng chứng và đặt ranh giới phục hồi

Thu thập tối thiểu:

| Nguồn | Ghi nhận |
| --- | --- |
| App log/tracing | Request/job nào gây thay đổi, thời điểm và correlation ID |
| Neo4j query log/security log | Cypher/actor/transaction nào liên quan, chỉ lấy log được phép |
| Neo4j debug/neo4j logs | Lỗi startup, transaction log, index, storage và cluster |
| Hệ điều hành/storage | Disk errors, filesystem, OOM, volume detach, dung lượng trống |
| Cluster health | Member nào `ONLINE`, leader, lag, routing, replication |
| Backup inventory | Full/differential artifacts, checksum, timestamp, ID, quyền truy cập |
| Business data | Tổng đơn, tổng dòng hàng, high-water mark, nguồn sự kiện/outbox, khóa |

Để bảo toàn chứng cứ, dùng snapshot hạ tầng hoặc bản sao file **theo quy trình do đội vận hành/storage hỗ trợ**, trên hệ thống đã được cô lập khi cần. **Snapshot hệ thống tệp không tự thay thế Neo4j backup có tính nhất quán**; muốn dùng làm phương án phục hồi phải chứng minh tính đúng qua quy trình kiểm tra.

### 5.3. Trong 20–45 phút: quyết định nhánh xử lý

```text
Sự cố được xác nhận
        |
        +-- Chỉ lỗi ứng dụng/query, database khỏe?
        |     +-- Có --> dừng nguồn lỗi, sửa dữ liệu qua quy trình nghiệp vụ
        |
        +-- Chỉ một member cluster bị lỗi, member khác khỏe?
        |     +-- Có --> runbook failover/reseed, kiểm tra quorum và lag
        |
        +-- Store/log hỏng, database không dùng được?
        |     +-- Có --> cách ly, kiểm tra bản sao, chuẩn bị restore sạch
        |
        +-- Xóa nhầm được commit/nhân bản?
              +-- Có --> chọn clean recovery point,
                         đánh giá mất những write hợp lệ sau đó,
                         khôi phục trên môi trường tách biệt
```

Việc chọn nhánh nào phải dựa trên bằng chứng và mục tiêu RPO/RTO. **Restore toàn database khi chỉ một node hoặc một transaction bị sai** có thể làm mất nhiều giao dịch hợp lệ được commit sau thời điểm sự cố. Đôi khi dựng database bản sao rồi đối chiếu và sửa có kiểm soát là phù hợp hơn; quy trình này vẫn cần xác định idempotency và ranh giới nghiệp vụ.

## 6. Điều tra tình trạng database mà không làm thay đổi dữ liệu

### 6.1. Kiểm tra trạng thái DBMS

Kết nối với database `system` bằng tài khoản quản trị có quyền, kiểm tra:

```cypher
SHOW DATABASES;
```

Khi cần chỉ một database:

```cypher
SHOW DATABASE orders;
```

Lệnh giúp quan sát trạng thái/requested state và thông tin lỗi nếu DBMS còn hoạt động. Nó không tự xác minh integrity của mọi store record. Nếu kết nối không thể thiết lập, thu log từ máy chủ/pod và storage layer trước khi quyết định bước tiếp theo.

### 6.2. Tránh tạo thêm transaction nghiệp vụ

Trong chế độ điều tra:
- Không chạy `CREATE`/`MERGE`/`SET`/`DELETE` để “thử database có chạy không”.
- Không mở một job `PROFILE` chứa câu ghi; `PROFILE` **thực thi query thật**.
- Không dùng `DROP INDEX` hay xóa thư mục index để sửa hỏng dữ liệu khi chưa biết phạm vi corruption.
- Không tự sửa nội dung binary store hoặc xóa/đổi tên transaction logs.
- Không chạy lệnh Neo4j Admin trên những store đang được DBMS sử dụng khi công cụ yêu cầu offline.

Tạm dừng job Spring/Java ghi vào graph, kể cả retry hoặc CDC consumer có khả năng tái tạo dữ liệu. Nếu cần kiểm chứng truy vấn đọc, dùng account chỉ đọc và tập query giới hạn.

### 6.3. Dấu hiệu index lỗi so với store lỗi

Không phải mọi thông báo `Index ... FAILED` đều có nghĩa node/relationship đã hỏng. Ngược lại, một index báo `ONLINE` không chứng minh toàn bộ graph không có lỗi. Phải đối chiếu:
- Database có `ONLINE` hay không.
- `SHOW INDEXES` và các state của index/constraint.
- Neo4j logs và lỗi storage/transaction.
- `neo4j-admin database check` khi có một store hoặc archive hợp lệ **không đang được sử dụng**.

**Không tự “sửa” một index bị lỗi bằng xóa/tạo lại nếu chưa loại trừ lỗi nền tảng của disk hoặc store**.

## 7. Kiểm tra tính nhất quán bằng `neo4j-admin database check`

Công cụ này kiểm tra cấu trúc graph, relationship, property, counts và index theo tùy chọn. Nó **không chạy trên database còn được sử dụng**, do đó cần dừng database hoặc kiểm tra **bản artifact đã phục hồi**.

### 7.1. Kiểm tra database offline

Ví dụ **chỉ trên database lab đã dừng**:

```bash
bin/neo4j-admin database check \
  --report-path=/srv/recovery-reports \
  orders_drill
```

Kết quả:
- Exit code **0** và không có report lỗi: các phép kiểm tra được yêu cầu không phát hiện inconsistency.
- Exit code **khác 0** và file `inconsistencies-....report`: cần lưu report, đọc và điều tra.
- Nếu lệnh hết RAM/dung lượng tạm: đó là lỗi kiểm tra, **không phải bằng chứng store sạch**.

Có thể điều chỉnh `--max-off-heap-memory`, `--threads` và các phép kiểm tra cụ thể cho dữ liệu lớn, nhưng **không tắt kiểm tra khó rồi tuyên bố integrity PASS toàn diện**.

### 7.2. Kiểm tra backup/dump artifact

Với một `.dump` hoặc **full backup đã recovered**:

```bash
bin/neo4j-admin database check \
  --from-path=/srv/recovery/checked-archive/ \
  --report-path=/srv/recovery-reports \
  orders
```

**Giới hạn:** công cụ không kiểm tra trực tiếp một differential backup đơn lẻ hoặc một full backup **chưa recovered**. Cần `neo4j-admin backup aggregate` để tạo full backup đã replay transaction logs rồi mới chạy check tương ứng. Khi `--from-path` trỏ thư mục, tool có thể chọn **chuỗi mới nhất**; nếu cần đúng một bản, chỉ rõ artifact trên phiên bản hỗ trợ. Đừng để test vô tình kiểm tra backup khác ngày.

### 7.3. Store consistency không đồng nghĩa dữ liệu nghiệp vụ đúng

Consistency checker có thể cho kết quả sạch trong khi:
- Toàn bộ node của một tenant đã bị xóa bằng một transaction **hợp lệ**.
- Relationship bị nối sai đầu mút do bug ứng dụng nhưng storage vẫn hợp lệ.
- Đơn hàng có `status = 'PAID'` mà không có dòng hàng.
- Một số transaction đã commit sau recovery point không còn hiện diện.

Vì vậy, **consistency PASS chỉ là một trong những cổng nghiệm thu**; phải bổ sung schema, counts, ràng buộc nghiệp vụ và so sánh nguồn ghi.

## 8. Xác nhận backup chain trước khi chọn điểm khôi phục

### 8.1. Backup Enterprise: full và differential

Backup trực tuyến bằng Enterprise có thể tạo:
- **Full backup**: điểm neo dữ liệu.
- **Differential backup**: phần thay đổi/transaction log tiếp theo; nó phụ thuộc vào chuỗi backup phù hợp.
- **Aggregated backup**: một full artifact đã áp transaction logs từ chuỗi để giảm chi phí replay tại thời điểm restore.

Một sơ đồ:

```text
Full F0  ----> DIFF D1 ----> DIFF D2 ----> DIFF D3
  |             |              |             |
  +-------------+--------------+-------------+
                Chuỗi hợp lệ cần đủ các mắt xích
                             |
                      backup aggregate
                             |
                      Full recovered F3
                             |
                     database check/restore
```

Không thể bảo đảm khôi phục được chỉ bằng việc thấy có file `D3.backup`; cần đủ phần full và những transaction logs liên quan. Một lịch backup “mỗi 15 phút” chỉ giúp RPO nếu **mỗi lần backup thành công, artifact an toàn, chain có thể đọc và restore test được**.

### 8.2. Kiểm tra metadata bằng lệnh inspect

```bash
bin/neo4j-admin backup inspect \
  /srv/neo4j-backups/orders-2026-11-25T03-30-00.backup
```

**Tên file trên là giả định**. `backup inspect` hiển thị các thông tin như database, database ID, thời điểm UTC, full/differential, lowest/highest transaction ID và trạng thái recovered. Kết quả giúp phân biệt:
- Backup thuộc database nào.
- File `.backup` có phải mắt xích mong muốn không.
- Khoảng transaction mà backup bao phủ.
- Có cần aggregate/recover trước khi kiểm tra hay không.

Nếu một đường dẫn trong tài liệu thay đổi qua các phiên bản, chạy `bin/neo4j-admin backup inspect --help` trên bản Neo4j thực tế để xác nhận.

### 8.3. Aggregate mà không phá chuỗi gốc của lần diễn tập

Ví dụ trên **bản sao backup dành riêng cho lab**:

```bash
bin/neo4j-admin backup aggregate \
  --from-path=/srv/recovery/backup-chain \
  --keep-old-backup=true \
  orders
```

Tùy chọn `--keep-old-backup=true` giúp giữ chain nguồn khi aggregate. Mặc định của lệnh có thể xóa/thu hồi các artifact cũ sau khi hợp nhất; do đó **không chạy trên thư mục backup production khi đang điều tra**, trừ khi chính sách retention và owner cho phép.

Theo tài liệu từ Neo4j 2025.01, cú pháp mới là `neo4j-admin backup aggregate`; tên cũ `neo4j-admin database aggregate-backup` đã deprecated.

## 9. Ví dụ online backup Enterprise để có dữ liệu diễn tập

Lệnh sau minh họa quy trình **tạo backup trước khi xảy ra sự cố**, không phải lệnh chữa một store đang hỏng:

```bash
bin/neo4j-admin database backup \
  --from=127.0.0.1:6362 \
  --to-path=/srv/neo4j-backups \
  --type=FULL \
  orders
```

Điều kiện:
- Neo4j Enterprise hỗ trợ online backup.
- Backup service đã được cấu hình, firewall/TLS/quyền được thiết lập phù hợp. `127.0.0.1:6362` chỉ có nghĩa nếu chạy trên cùng máy hoặc có listener phù hợp; với backup client khác host phải dùng địa chỉ được phép.
- Thư mục backup có quyền đúng, đủ dung lượng và không cùng điểm lỗi với dữ liệu gốc.
- Lệnh chạy dưới identity có quyền filesystem thích hợp, thường là user `neo4j`.
- Với cluster, có thể cung cấp nhiều địa chỉ backup server theo tài liệu để giảm rủi ro khi một member không sẵn sàng.

Để backup lịch tự động sau full, `--type=AUTO` có thể chọn full/differential theo tình trạng chain. Chỉ định `--type=DIFF` cần hiểu chuỗi và transaction logs đang có. Theo Neo4j 2026.02+, có thể lên lịch full và differential với cadence độc lập; vẫn cần đo **RPO thực tế và thời gian aggregate/restore thực tế**, không chỉ cấu hình cron.

**Không đặt backup và nguồn trên cùng một đĩa** rồi kỳ vọng xử lý được mất volume. Cần một vùng lưu trữ ngoài host/availability zone phù hợp, quyền truy cập tách biệt, retention và kiểm tra khả năng tải về khi cần.

## 10. Diễn tập restore Enterprise trên database mới

### 10.1. Chọn môi trường cô lập và tên đích khác production

Giả định:
- Database nguồn: `orders`.
- Backup artifact hợp lệ đã được copy sang thư mục lab: `/srv/recovery/orders-clean.backup`.
- Instance Neo4j Enterprise để diễn tập tương thích với version backup.
- Database đích **`orders_drill` chưa tồn tại**.
- Backup file thực sự chứa một full recovered artifact hoặc một chain đủ để restore.

**Không dùng `--overwrite-destination` trong ví dụ này.** Việc đặt tên database mới giúp giảm nguy cơ xóa dữ liệu đang dùng.

### 10.2. Xem help và thực hiện restore

```bash
bin/neo4j-admin database restore --help
```

```bash
bin/neo4j-admin database restore \
  --from-path=/srv/recovery/orders-clean.backup \
  --temp-path=/srv/recovery/tmp \
  orders_drill
```

Ở đây:
- `--from-path` có thể trỏ một backup artifact cụ thể hoặc thư mục/chuỗi backup.
- `--temp-path` dùng **thư mục staging đủ dung lượng**, thích hợp khi cần replay logs; thư mục phải theo yêu cầu trống/quyền của tool.
- `orders_drill` là tên database đích mới.
- Không cho ứng dụng kết nối hoặc ghi vào đích này trước khi kiểm tra xong.

Lệnh restore phải có quyền trên các thư mục Neo4j data/transaction logs và chạy ở môi trường có thể truy cập store đích. **Phục hồi từ phiên bản Neo4j mới hơn về bản Neo4j cũ hơn không được hỗ trợ**; kiểm tra ma trận version/format trước khi restore.

### 10.3. Check offline trước khi mở database

Khi `orders_drill` chưa được đăng ký/mount, chạy:

```bash
bin/neo4j-admin database check \
  --report-path=/srv/recovery-reports \
  orders_drill
```

Nếu consistency check phát hiện lỗi, **không công bố database đã phục hồi**. Ghi kết quả cùng incident ID và chọn lại artifact/chain hoặc trao đổi với Neo4j Support. Không bỏ qua lỗi chỉ vì REST API có thể kết nối.

### 10.4. Đăng ký database trong DBMS và xác minh trạng thái

Kết nối `system` với quyền quản trị trên **instance diễn tập** rồi chạy:

```cypher
CREATE DATABASE orders_drill;
```

Kiểm tra:

```cypher
SHOW DATABASE orders_drill;
```

Chỉ tiếp tục khi database hoạt động ở trạng thái `ONLINE`. Nếu bản phục hồi dùng tên DB mới, Java Driver phải kết nối đúng tên `orders_drill`; không để frontend production chuyển sang database đó trước thời điểm được phê duyệt.

**Database được restore từ data backup chưa đồng nghĩa user/role đã có.** Metadata RBAC cần được phục hồi/tái áp dụng bằng quy trình riêng nếu cần; xem mục 13.

## 11. Diễn tập point-in-time recovery (PITR) cho xóa nhầm

Một sự cố điển hình:
- 03:15 UTC: một job Cypher xóa nhầm relationship `PLACED`.
- 03:20 UTC: sự cố được phát hiện.
- Có full backup trước đó và các differential/transaction logs **bao phủ tới trước sự cố**.

Để khôi phục đến trước 03:15 UTC, sử dụng backup chain được chọn và `--restore-until`:

```bash
bin/neo4j-admin database restore \
  --from-path=/srv/recovery/backup-chain/orders-last-diff.backup \
  --restore-until="2026-11-25 03:15:00" \
  --temp-path=/srv/recovery/tmp \
  orders_pitr_drill
```

**Đây là minh họa tên file và thời gian**, không phải artifact hiện hữu.

Ý nghĩa:
- Timestamp phải là **UTC**.
- Chỉ áp các transaction có commit time **trước** timestamp.
- Nếu dùng transaction ID: `--restore-until=12345` có nghĩa phục hồi đến **trước transaction 12345**.
- Cần chain có các transaction logs phù hợp; không thể tạo transaction đã thất lạc bằng cách chọn một timestamp tùy ý.
- Nếu trong một transaction đã xóa dữ liệu và cập nhật nhiều entity khác, việc PITR loại bỏ **toàn transaction** đó, không tách từng câu lệnh trong transaction.

### 11.1. Đánh giá mất dữ liệu hợp lệ sau thời điểm PITR

PITR có thể đưa graph về trạng thái sạch trước xóa nhầm, nhưng **cũng loại bỏ các write hợp lệ xảy ra sau điểm đó**. Ví dụ:

| Transaction | Thời điểm | Bản chất | Khi PITR về 03:15 UTC |
| --- | --- | --- | --- |
| T100 | 03:14:40 | Đơn hàng hợp lệ | Giữ |
| T101 | 03:15:01 | Xóa nhầm | Loại |
| T102 | 03:15:30 | Thanh toán hợp lệ khác | Cũng bị loại |
| T103 | 03:16:00 | Cập nhật kho hợp lệ | Cũng bị loại |

Vì vậy, runbook phải lập **danh sách giao dịch sau điểm khôi phục** và phương án xử lý từ nguồn nghiệp vụ (outbox, event log, hệ thống thanh toán, CDC hoặc audit) bằng cơ chế **idempotent và đã đối soát**. Không tự chạy lại tất cả lệnh cũ, đặc biệt lệnh thanh toán hoặc gửi thông báo vốn có side effect ngoài Neo4j.

Nếu chỉ một vài node bị lỗi, có thể dựng `orders_pitr_drill` để **so sánh** dữ liệu cũ với hiện tại và thiết kế repair query có review, thay vì chuyển toàn bộ dịch vụ về một snapshot cũ.

## 12. Phục hồi bằng `dump/load` khi không có online backup

### 12.1. Tạo dump khi database offline

Trên Neo4j Community hoặc một môi trường có kế hoạch downtime, ví dụ:

```bash
bin/neo4j-admin database dump \
  neo4j \
  --to-path=/srv/dumps
```

Điều kiện quan trọng:
- Database đích phải **offline/không đang được mount sử dụng**.
- Community yêu cầu DBMS offline đối với các thao tác dump/load theo tài liệu.
- `/srv/dumps` phải tồn tại, có quyền hạn phù hợp, không world-readable/world-executable.
- Dump **không bao gồm user/role metadata**; cần sao lưu/reconstruct phần này riêng theo edition.
- Đây là **bản chụp data tại thời điểm dump**, không phải chuỗi differential để PITR.

### 12.2. Nạp từ dump trên môi trường Community

Ví dụ trên **instance Community riêng biệt, đã dừng và có database đích mặc định phù hợp**:

```bash
bin/neo4j-admin database load \
  --from-path=/srv/dumps \
  neo4j
```

Hai lệnh trong ví dụ sử dụng nhất quán database `neo4j`: lệnh dump tạo archive cho `neo4j` và lệnh load đọc lại archive tương ứng. Nếu trong bài toán thật tên database hoặc archive khác, phải xác minh đúng tên/đường dẫn theo tài liệu `load`; **không tùy ý đổi tên file rồi coi mọi metadata đều tương thích**.

Để thay thế **database đang tồn tại** trong một bài diễn tập riêng, lệnh load cần database đã dừng và `--overwrite-destination=true`. Đây là thao tác **có thể xóa dữ liệu đích** nên không đưa vào ví dụ chạy trực tiếp. Sau load, khởi động đúng DBMS/đăng ký database theo edition và xác minh.

### 12.3. Khi có Enterprise nhưng chỉ còn file `.dump`

`neo4j-admin database load` có thể đọc archive từ `database dump`, và tùy điều kiện còn có thể đọc **full backup artifact** Enterprise. Nhưng **không dùng `load` để thay thế việc restore một chuỗi differential theo timestamp**. Nếu cần PITR, hãy dùng `database restore` cùng chain có transaction logs và điều kiện phù hợp.

## 13. Quy trình cluster: failover không đồng nghĩa restore

Với cluster Neo4j Enterprise, câu hỏi đầu tiên là **sự cố chỉ xảy ra trên một server hay đã ảnh hưởng tới trạng thái graph được đồng thuận/replicate**.

### 13.1. Một member lỗi, các thành viên khác còn dữ liệu đúng

Thông thường:
1. Kiểm tra quorum và trạng thái các member.
2. Xác nhận ứng dụng dùng routing URI `neo4j://` hoặc `neo4j+s://` và Driver có khả năng cập nhật routing table.
3. Cô lập member lỗi; tránh để nó tiếp tục ghi vào những store không đáng tin cậy.
4. Phục hồi sự sẵn sàng theo **quy trình thêm member/reseed database** của đúng phiên bản và topology.
5. Kiểm tra transaction lag, leader, read/write và độ trễ sau khi tái đồng bộ.

**Không mặc nhiên restore backup cũ lên member hỏng rồi cho nó join cluster.** Cluster có trạng thái đồng thuận và metadata riêng; phục hồi sai cách có thể khiến database không nhất quán.

### 13.2. Cả cluster đã nhận transaction xóa nhầm

Replication không giúp “undo” transaction này: các member khỏe có thể đều đã áp dụng thay đổi. Khi đó:
- Dừng nguồn ghi sai ở ứng dụng/toàn hệ thống.
- Chọn clean recovery point theo backup độc lập.
- Dùng quy trình **restore into a new database**, **URI-based restore**, **designated seeder** hoặc `dbms.recreateDatabase()` theo tài liệu chính thức tương ứng.
- Không dùng `neo4j-admin database restore --overwrite-destination` trên database đã tồn tại trong cluster; tài liệu Neo4j cảnh báo **không an toàn** vì trạng thái cluster bổ sung có thể không tương thích.
- Xác minh routing, privileges, ứng dụng và CDC trước khi chuyển traffic.

Với topology phân tán, thời điểm hồi phục, source of truth và việc khôi phục từng database phải được thống nhất theo incident commander. Không chép đè cùng một store directory sang mọi member bằng `scp` như cách tái tạo cluster.

### 13.3. Tính năng mới theo phiên bản

Theo Neo4j 2026.03+, `neo4j-admin database copy` được bổ sung vào các phương án khôi phục dữ liệu từ backup và có thể hỗ trợ một số workflow làm sạch inconsistency/reclaim space. **Không coi `copy` là phép màu khôi phục dữ liệu đã bị xóa khỏi tất cả backup**; nó có điều kiện edition/version, hướng dẫn setup và phạm vi khác `restore`.

## 14. AuraDB: thao tác qua snapshot/backup của dịch vụ

Với AuraDB, người dùng không trực tiếp quản lý filesystem hoặc thực thi `neo4j-admin database restore` trên server dịch vụ. Quy trình thao tác hợp lệ:

1. Vào **Aura Console** và xác định instance/database có sự cố.
2. Kiểm tra **Snapshots** (instance một user database) hoặc **Backups** (instance nhiều database) cùng tier, retention và thời gian có sẵn.
3. Chọn thời điểm sạch trước sự cố; kiểm tra sự khác nhau giữa **restore vào instance hiện có** và **tạo instance mới từ snapshot/export**.
4. Ưu tiên **tạo instance khôi phục riêng** để kiểm tra khi dịch vụ/tier cho phép.
5. Chạy kiểm chứng nghiệp vụ, schema và quyền, sau đó chuyển endpoint/credential và traffic theo change plan.
6. Nếu chọn restore đè instance đang chạy, cần xác nhận việc **ghi đè dữ liệu hiện có** và những thay đổi sẽ mất.
7. Với instance chứa nhiều database, có thể có **restore point toàn instance**; xem Action cho từng database vì database không có backup tương ứng ở thời điểm chọn có thể **bị xóa sạch** khi restore instance theo tài liệu Aura.

Đối với backup/snapshot tải xuống hoặc `.dump/.backup`, nên xem đúng khả năng export/restore của tier. **Không giả định Aura hỗ trợ nạp archive chia nhiều phần (split archive)**; tài liệu hiện hành nêu restore từ split backup archive 2026.09 **chưa được hỗ trợ** trên Aura.

### Một ví dụ quyết định

Một AuraDB Professional có sự cố xóa nhầm lúc 15:00, nhưng snapshot khả dụng gần nhất là 00:00:
- Không thể suy ra có PITR 14:59 chỉ vì Neo4j Enterprise self-host có `--restore-until`.
- Nếu restore snapshot 00:00, có nguy cơ mất **15 giờ** giao dịch hợp lệ.
- Cần kiểm tra retention và khả năng dựng instance mới, rồi quyết định có thể phục hồi chọn lọc từ nguồn nghiệp vụ hay phải chấp nhận mất dữ liệu theo RPO đã thỏa thuận.

## 15. Xác minh data graph sau restore: ba tầng kiểm thử

Phục hồi file thành công chỉ chứng minh **lệnh kết thúc**, không chứng minh graph phù hợp nghiệp vụ. Chạy kiểm tra theo thứ tự.

### 15.1. Tầng 1: store và database health

- `neo4j-admin database check` trên database đã dừng hoặc artifact recovered, lưu exit code/report.
- Database khởi động `ONLINE`.
- Không có lỗi storage/index/transaction trong log mới.
- `SHOW INDEXES`: các index cần dùng đã `ONLINE`; `SHOW CONSTRAINTS` trả cấu trúc phù hợp.
- Kiểm tra version/edition, compatibility plugin APOC/GDS và auth metadata khi cần.

Ví dụ sau khi database `orders_drill` online:

```cypher
SHOW INDEXES
YIELD name, type, state
RETURN name, type, state
ORDER BY name;
```

```cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
```

### 15.2. Tầng 2: số lượng và tính toàn vẹn nghiệp vụ

Giả sử graph có:
- `(:Customer {customerId, tenantId})`.
- `(:Order {orderId, tenantId, status})`.
- `(:Customer)-[:PLACED]->(:Order)`.
- `(:Order)-[:HAS_LINE]->(:Product)`.

Kiểm tra số lượng:

```cypher
MATCH (o:Order)
RETURN count(o) AS orders;
```

```cypher
MATCH ()-[r:PLACED]->()
RETURN count(r) AS placedRelationships;
```

```cypher
MATCH ()-[r:HAS_LINE]->()
RETURN count(r) AS orderLines;
```

Kiểm tra relationship và tenant (theo mô hình một khách sở hữu một đơn):

```cypher
MATCH (o:Order)
WHERE NOT EXISTS {
  MATCH (:Customer)-[:PLACED]->(o)
}
RETURN count(o) AS ordersWithoutOwner;
```

```cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE c.tenantId <> o.tenantId
RETURN count(*) AS crossTenantOrderLinks;
```

Nếu mô hình cho phép guest order hoặc cross-tenant workflow, **điều kiện nghiệm thu phải điều chỉnh theo nghiệp vụ**; không tự xem mọi số khác 0 đều là corruption.

Đối soát với:
- Số đơn và transaction ID gần nhất có thể phục hồi.
- Payment/ERP/order event log làm nguồn xác minh độc lập.
- Những customer/order ID quan trọng (canary).
- Dữ liệu vừa thay đổi sát thời điểm xảy ra sự cố.

### 15.3. Tầng 3: ứng dụng thực tế

- Java Driver kết nối database khôi phục bằng đúng URI/database.
- Read query trên DTO và traversal trả kết quả mong đợi.
- Spring Data Neo4j entity mapping không lỗi vì mất property/relationship.
- Index/constraint và role phù hợp, user chỉ đọc/ghi đúng quyền.
- Query `EXPLAIN`/`PROFILE` ở dataset có kiểm soát không có plan bất thường.
- Không có webhook, CDC hoặc event consumer phát đi sự kiện sai khi dịch vụ hồi phục.
- Dữ liệu tenant không bị lộ qua một endpoint vốn phải kiểm tra ownership.

### 15.4. Java Driver smoke test read-only

Đoạn Java sau minh họa với **Driver đã được tạo** và database thử nghiệm `orders_drill`:

```java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

static long countRecoveredOrders(Driver driver) {
    try (Session session = driver.session(
            SessionConfig.forDatabase("orders_drill"))) {

        return session.executeRead(tx ->
            tx.run("""
                MATCH (o:Order)
                RETURN count(o) AS total
                """)
              .single()
              .get("total")
              .asLong()
        );
    }
}
```

Đây là smoke test đếm, **không đủ thay consistency check hay đối soát giao dịch**. Không cho API production tự động “sửa số lượng bị thiếu” trong lúc chưa xác minh nguyên nhân.

## 16. RBAC, `system` database và downstream: những thứ dễ quên

### 16.1. Metadata người dùng/role

Khi backup Enterprise, có thể có metadata về user/role trong artifact theo cài đặt `--include-metadata` (thông thường mặc định có). Tuy nhiên **restore dữ liệu không mặc nhiên áp lại toàn bộ role/user vào `system`**.

Theo tài liệu restore Enterprise, quy trình có thể sinh một file `restore_metadata.cypher`. Nếu cần hồi phục RBAC, **người vận hành phải xem xét và thực thi có chủ đích** trên database `system` bằng quyền phù hợp, sau khi kiểm tra chính sách/trùng tên và không làm lộ credential.

`neo4j-admin database dump` **không chứa metadata user/role**. Với Community, ranh giới quyền quản lý khác Enterprise; với Enterprise nhiều database, nên có kế hoạch backup cả `system`, đồng thời hiểu rằng việc khôi phục system database có thể ảnh hưởng danh tính và điều khiển DBMS.

### 16.2. CDC, Kafka/outbox và hệ thống bên ngoài

Restore hoặc load database thay đổi trạng thái graph bằng cách thay store, **không tái phát từng sự kiện tương ứng như các transaction ghi trực tuyến**. Neo4j CDC không bắt sự thay đổi do `neo4j-admin database load` theo tài liệu.

Nếu downstream đã nhận các sự kiện trước sự cố:
- Consumer có thể giữ **offset/bookmark/change identifier** không còn khớp với graph sau PITR.
- Các write hợp lệ sau recovery point có thể đã được gửi đến Kafka, payment gateway hoặc hệ thống khác.
- Việc chạy lại producer sau restore có thể tạo sự kiện trùng, thiếu hoặc không theo thứ tự.

Cần dựng kế hoạch **reconciliation/snapshot rebuild**, không kỳ vọng chỉ restore Neo4j xong là toàn hệ thống quay về cùng một mốc thời gian.

### 16.3. Backup phải độc lập với credential bị lộ

Backup không giúp chống ransomware khi tài khoản bị xâm nhập có thể xóa luôn backup. Chính sách nên gồm:
- Storage ngoại vi, retention, khả năng **immutable/object lock** khi hỗ trợ.
- Credential backup tách với credential ứng dụng.
- Mã hóa trong lưu trữ/vận chuyển, giới hạn truy cập và nhật ký audit.
- Kiểm tra tải xuống/đọc thực tế theo lịch.
- Phương án sử dụng backup khi control plane/IdP chính gặp sự cố.

## 17. Phê duyệt chuyển lưu lượng và rollback

Trước khi cutover tới database khôi phục, cần một **go/no-go checklist**:

| Cổng nghiệm thu | Minh chứng | Chịu trách nhiệm |
| --- | --- | --- |
| Đúng recovery point | Artifact/database ID, tx IDs, thời điểm UTC | Database operator |
| Store nhất quán | Check report sạch, startup không lỗi | DBA/SRE |
| Schema sẵn sàng | Index `ONLINE`, constraint hợp lệ | DBA/Dev |
| Dữ liệu đúng | Count, canary keys, relationship, tenant invariants | Data/Business owner |
| Downstream đồng bộ | CDC/Kafka/payment/ERP reconcile plan | Integration owner |
| Ứng dụng hoạt động | Smoke test Java Driver/SDN, read/write có kiểm soát | Application owner |
| An ninh | Role, secret, chứng chỉ, quyền mạng | Security |
| Vận hành ổn định | p95/p99, error rate, disk/CPU/heap, backup mới | SRE |
| Rollback rõ | Trạng thái trước cutover vẫn được bảo toàn | Incident commander |

**Quy trình cutover gợi ý:**

1. Giữ dịch vụ ở chế độ bảo trì/no-write.
2. Đóng các kết nối/queue cũ theo chiến lược ứng dụng; đừng để retry ghi lại vào database đích sai.
3. Cập nhật config database name/URI/routing thông qua deployment được kiểm soát.
4. Kiểm tra end-to-end bằng tài khoản test, sau đó mở read traffic.
5. Chỉ mở write traffic sau khi đã xác nhận logic duplicate prevention và downstream reconciliation.
6. Theo dõi thời gian thực các metric và logs; ghi thời điểm mở traffic.
7. Nếu gặp lỗi nghiêm trọng, dừng write và **quay về phương án đã dự trù**, không mù quáng đảo DNS về database cũ nếu dữ liệu đã phân nhánh sau cutover.

Rollback không phải luôn chỉ “đổi URL cũ”. Nếu bản phục hồi và hệ thống cũ đã nhận **các transaction khác nhau**, chuyển ngược không đối soát có thể làm dữ liệu phân nhánh vĩnh viễn.

## 18. Kế hoạch diễn tập định kỳ: phục hồi phải được chứng minh

Một bản sao lưu có exit code 0 là **backup đã tạo**, chưa phải **backup có thể dùng để phục hồi đúng RTO/RPO**. Tổ chức nên diễn tập với các điều kiện có thể xảy ra.

| Bài diễn tập | Mục tiêu | Bằng chứng cần lưu |
| --- | --- | --- |
| **D1: Mất database standalone** | Restore full backup trên instance mới | Thời gian restore, check report, kết quả business smoke |
| **D2: Hỏng một differential** | Chọn chain còn đủ và điều chỉnh RPO | File/metadata chain, recovery point thực đạt |
| **D3: Xóa nhầm transaction** | PITR đến trước thời điểm xóa; xử lý write hợp lệ sau đó | Tx boundary, dữ liệu so sánh, bản đối soát |
| **D4: Hỏng một cluster member** | Failover/reseed không mất dữ liệu đã được bảo đảm | Quorum/lag, driver routing, downtime |
| **D5: Mất volume/zone** | Restore từ backup ngoài vùng lỗi | Khả năng truy cập backup, RTO thực, checksum |
| **D6: Restore trên Aura** | Chọn đúng snapshot/tier, tạo instance thử | Thời gian tạo, xác minh data/role và cost |
| **D7: Credential backup bị thu hồi** | Kiểm tra kịch bản truy cập backup bằng break-glass | Thời gian lấy quyền, audit, khả năng khôi phục |
| **D8: Downstream inconsistency** | Khôi phục lại đồng bộ Kafka/ERP/CDC | Offset, số đơn đối soát, bản ghi trùng/thiếu |

### 18.1. Các tiêu chí chấm điểm diễn tập

Đo độc lập:
- **Recovery point thực tế** so với điểm sự cố (actual data loss window).
- **Thời gian phát hiện** và kích hoạt runbook.
- **Thời gian lấy artifact** từ vùng lưu trữ, giải nén/replay logs và `database check`.
- **Thời gian index/constraint và application trở về ổn định**.
- **Tổng thời gian không phục vụ được các chức năng chính** so với RTO.
- **Số transaction hợp lệ sau recovery point** phải xử lý lại.
- **Tỷ lệ bài kiểm thử đạt**, số canary keys đúng và số lỗi quyền/CDC còn tồn.
- Chi phí nguồn lực, storage bandwidth và tác động nếu diễn tập gần production.

### 18.2. Hồ sơ diễn tập mẫu

```yaml
drillId: neo4j-orders-restore-2026-11-25
sourceDatabase: orders
targetDatabase: orders_drill
scenario: accidental-delete-before-cutover
environment: isolated-staging
neo4jVersion: "<ghi version thực tế>"
backupArtifact: "<đường dẫn/ID artifact đã được xác minh>"
recoveryTargetUtc: "2026-11-25 03:15:00"
rpoTargetMinutes: 15
rtoTargetMinutes: 90
actualDataLossMinutes: null
actualRecoveryMinutes: null
consistencyCheck: NOT_RUN
businessValidation: NOT_RUN
securityValidation: NOT_RUN
downstreamReconciliation: NOT_RUN
approvedForCutover: false
```

Đây là **mẫu hồ sơ**, không phải file bắt buộc và không ngụ ý đã diễn tập. Trong một lần diễn tập thật, thay `null`/`NOT_RUN` bằng số liệu thực đo, lưu log/checksum và chữ ký phê duyệt trong hệ thống quản lý sự cố.

## 19. Các sai lầm làm sự cố nghiêm trọng hơn

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Thấy lỗi storage liền xóa transaction log | Mất cơ hội phục hồi transaction, có thể hỏng thêm store | Cô lập, thu log, giữ bằng chứng và làm theo runbook |
| Copy/paste thư mục database đang chạy | Store có thể không nhất quán | Dùng backup/dump/snapshot đúng cơ chế |
| Restore “backup mới nhất” sau xóa nhầm | Có thể backup đã chứa transaction xóa nhầm | Chọn clean recovery point bằng timestamp/tx ID |
| Chỉ kiểm tra exit code của restore | Bỏ sót corruption hoặc sai dữ liệu nghiệp vụ | Offline consistency + index/schema + business reconciliation |
| Chạy check trên database đang mount | Tool không hỗ trợ, nguy cơ thao tác sai | Dừng database hoặc kiểm tra artifact đủ điều kiện |
| Kiểm tra differential đơn lẻ như full | Không thể kiểm tra toàn bộ chain | Aggregate/recover chain trước |
| Bật `--overwrite-destination` để “cho chạy được” | Xóa data đích, đặc biệt nguy hiểm trên cluster | Restore vào database mới/đúng quy trình cluster |
| Chọn PITR theo giờ địa phương nhưng không đổi UTC | Khôi phục sai mốc, mất giao dịch hợp lệ | Xác minh timezone và ranh giới commit |
| Coi replication là backup | Xóa nhầm có thể lan tới mọi member | Dùng backup độc lập và offsite |
| Mở write traffic ngay sau restore | Viết lên trạng thái chưa đối soát | Cổng nghiệm thu nhiều lớp và cutover có kiểm soát |
| Quên `system`/role metadata | Ứng dụng không còn quyền hoặc bị cấp quá rộng | Quản lý auth metadata và kiểm thử role |
| Chỉ khôi phục Neo4j, quên Kafka/CDC/payment | Phát sinh duplicate/missing events | Kế hoạch reconcile/idempotency |
| Không thử tải backup từ cloud | RTO bị phá do chậm/mất quyền tải xuống | Diễn tập cả download, staging và disk |
| Đo RTO tới lúc file restore xong | Ứng dụng thực tế còn lỗi, index chưa online | Tính tới lúc dịch vụ đạt mức hoạt động cần thiết |
| Giữ backup trên cùng volume lỗi | Backup cũng mất | Tách failure domain, retention và quyền |
| Rollback khi hai bên đã nhận write khác nhau | Split-brain dữ liệu nghiệp vụ | Dừng ghi và đối soát trước khi chuyển ngược |

## 20. Bài tập thực hành

1. Một cluster ba member có một member lỗi disk, hai member còn lại khỏe. Hãy mô tả cách quyết định failover/reseed so với restore từ backup cũ.
2. Một lệnh `DETACH DELETE` xóa nhầm lúc 10:42:17 (Asia/Ho_Chi_Minh). Hãy tính timestamp UTC cần dùng cho PITR để loại transaction đó. Giải thích vì sao phải chọn **điểm trước commit**, không chỉ thời điểm phát hiện.
3. Một chuỗi `Full F0 → Diff D1 → D2 → D3` bị mất `D2`. Phân tích khả năng dùng `D3` và cách lựa chọn clean recovery point.
4. Thiết kế chuỗi lệnh kiểm tra metadata (`backup inspect`), aggregate, check offline rồi restore sang `orders_drill`. Chỉ ra lệnh nào không được chạy trên database đang sử dụng.
5. Vì sao `neo4j-admin database check` trả PASS vẫn không chứng minh đơn hàng bị xóa nhầm đã trở lại?
6. Viết hai câu Cypher kiểm tra số `Order` và các `Order` không có relationship `PLACED` sau restore.
7. Một AuraDB Professional có snapshot gần nhất cách 20 giờ, RPO nghiệp vụ 15 phút. Đề xuất phương án và nêu rõ phần **không thể bảo đảm chỉ bằng snapshot**.
8. Một Java service đã gửi message Kafka về đơn `o400` nhưng Neo4j được PITR về trước transaction tạo `o400`. Thiết kế bước reconcile tránh tạo đơn hoặc event trùng.
9. Vì sao restore backup một user database chưa đồng nghĩa toàn bộ role/user của `system` cũng được phục hồi?
10. Lập checklist go/no-go để chuyển traffic sau khi restore, gồm phiên bản, index, RBAC, CDC, latency và cơ chế rollback.
11. Một instance Community cần phục hồi từ dump. Nêu điều kiện offline và vì sao không thể dùng chuỗi full/differential PITR như Enterprise.
12. Lập kịch bản diễn tập “mất hoàn toàn volume tại 01:00 UTC” với RPO 30 phút, RTO 2 giờ: cần những mốc thời gian và minh chứng nào?

## 21. Ghi nhớ

- **Phục hồi phải theo runbook đã diễn tập**, bắt đầu bằng dừng nguồn lỗi, giữ bằng chứng và xác định clean recovery point.
- **RPO đo khoảng dữ liệu có thể mất; RTO đo thời gian dịch vụ phải hoạt động trở lại**. Lịch backup không bảo đảm tự động đạt cả hai.
- **Cluster/failover xử lý lỗi sẵn sàng, không tự đảo ngược transaction xóa nhầm đã replicate.**
- **Enterprise** có online full/differential backup, restore và PITR khi chain transaction logs phù hợp; **Community** chủ yếu dùng dump/load offline.
- `neo4j-admin database check` cần database offline hoặc archive đáp ứng điều kiện; **store consistency PASS chưa đủ** để xác nhận dữ liệu nghiệp vụ đúng.
- **Không xóa log, copy store đang chạy hoặc overwrite database cluster tùy tiện.** Restore sang database/instance cách ly để kiểm chứng trước.
- **Timestamp `--restore-until` là UTC và mang ngữ nghĩa trước mốc commit**; PITR có thể làm mất cả write hợp lệ sau thời điểm đã chọn.
- **AuraDB** dùng cơ chế snapshot/backup của dịch vụ, giới hạn theo tier; không áp lệnh self-host `neo4j-admin database restore` trực tiếp lên Aura.
- Sau restore cần kiểm tra **index, constraint, tenant/relationship, user-role metadata, Java Driver, Spring Data Neo4j và CDC/downstream**.
- Chỉ công bố phục hồi hoàn tất khi **technical integrity, business reconciliation, security và cutover checks** đều đạt.
- **Diễn tập định kỳ, đo RPO/RTO thực tế và giữ bản sao lưu ngoài failure domain** là điều kiện để kế hoạch có giá trị khi sự cố thật xảy ra.

### Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual — Backup and restore planning](https://neo4j.com/docs/operations-manual/current/backup-restore/planning/)
- [Neo4j Operations Manual — Backup modes](https://neo4j.com/docs/operations-manual/current/backup-restore/modes/)
- [Neo4j Operations Manual — Back up an online database](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/)
- [Neo4j Operations Manual — Back up an offline database](https://neo4j.com/docs/operations-manual/current/backup-restore/offline-backup/)
- [Neo4j Operations Manual — Aggregate a database backup chain](https://neo4j.com/docs/operations-manual/current/backup-restore/aggregate/)
- [Neo4j Operations Manual — Restore a database backup](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-backup/)
- [Neo4j Operations Manual — Restore a database dump](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-dump/)
- [Neo4j Operations Manual — Check database consistency](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/)
- [Neo4j Operations Manual — Transaction logging](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-logs/)
- [Neo4j Operations Manual — Backup/restore in Kubernetes](https://neo4j.com/docs/operations-manual/current/kubernetes/operations/backup-restore/)
- [Neo4j Aura — Backup, export, restore and upload](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/)
- [Neo4j Java Driver Manual — Query the database](https://neo4j.com/docs/java-manual/current/query-simple/)
- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/)

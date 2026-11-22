# Phân biệt replication, snapshot và bản sao lưu độc lập

## 1. Ba bản sao của dữ liệu chưa chắc là một bản backup

Một công ty vận hành ứng dụng đặt hàng bằng Java và NoSQL. Cụm database có ba replicas trải trên ba availability zones. Đội phát triển tin rằng dữ liệu đã an toàn vì “còn hai bản sao nếu một node chết”.

Lúc 10:00, một lệnh xóa nhầm toàn bộ orders thuộc tenant T17 được thực thi bởi tài khoản có quyền ghi. Lệnh xóa hợp lệ theo database protocol và được replication sang cả ba replicas. Đến 10:02, cả ba bản sao đều trả lời: orders của tenant T17 không còn.

Ba replicas đã hoạt động **đúng nhiệm vụ**: giữ các bản sao gần nhau và đảm bảo ứng dụng tiếp tục đọc/ghi khi node lỗi. Nhưng chúng không giữ lại **trạng thái trước lệnh xóa nhầm**.

Một tình huống thứ hai: cụm NoSQL có snapshot định kỳ trên cùng hệ thống lưu trữ. Một tài khoản quản trị bị chiếm quyền, kẻ tấn công xóa cả database và snapshot. Ảnh chụp đã tồn tại, nhưng nó không được cách ly khỏi cùng failure domain và cùng quyền xóa.

Hai sự cố này cho thấy ba cơ chế rất khác nhau:

1. **Replication (nhân bản):** duy trì các bản sao phục vụ sẵn sàng, mở rộng đọc và/hoặc chịu lỗi node.
2. **Snapshot (ảnh chụp):** ghi lại trạng thái dữ liệu hoặc storage tại một mốc cụ thể để có thể dùng cho phục hồi, clone hoặc kiểm thử.
3. **Independent backup (bản sao lưu độc lập):** bản sao có chính sách phục hồi, giữ lại và tách biệt đủ mạnh khỏi hệ thống nguồn để còn sử dụng được khi lỗi lan truyền hoặc nguồn bị chiếm quyền.

Một snapshot có thể trở thành một phần của chiến lược backup độc lập, **nhưng không phải mọi snapshot đều độc lập**. Một backup có thể dựa trên snapshot, log/archive hoặc export theo engine, **nhưng không phải mọi replica đều là backup**.

Bài học thuộc module **Database No SQL**, chương **Sao lưu và phục hồi**, sẽ giải thích ranh giới này bằng ví dụ thực tế, quy trình vận hành và bài tập thiết kế.

### Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt đúng replication, snapshot, backup và point-in-time recovery (PITR).
- Giải thích vì sao replication có thể lan truyền xóa nhầm, corrupt data hoặc mutation của attacker.
- Phân biệt crash-consistent với application-consistent và transaction-consistent snapshot.
- Thiết kế backup vượt qua failure domain của cluster, tài khoản quản trị, Region và ransomware theo threat model.
- Tính và áp dụng RPO/RTO thay vì chỉ nhìn số replicas hay tần suất snapshot.
- Hiểu full/incremental/differential backup, WAL/oplog/commitlog archival và retention.
- Biết giới hạn, cách chọn và kiểm chứng các tính năng sao lưu của MongoDB, Cassandra/ScyllaDB, DynamoDB, Redis, Elasticsearch/OpenSearch.
- Xây restore runbook cho ứng dụng Java/NoSQL có indexes, caches, search projections, CDC và các side effects.
- Đo thành công bằng **restore được dữ liệu đúng, đúng mốc, trong thời gian yêu cầu**, chứ không chỉ thấy backup job báo success.

## 2. Định nghĩa ngắn nhưng chính xác

| Cơ chế | Nó bảo vệ chủ yếu điều gì? | Có giữ lịch sử khi xóa nhầm? | Có phải độc lập khỏi hệ nguồn? |
|---|---|---|---|
| Replication | Node/AZ failure, read availability, durability tùy acknowledgment mode | Thường không: xóa hợp lệ được lan truyền | Không mặc nhiên |
| Snapshot | Trạng thái tại một thời điểm hoặc một checkpoint | Có nếu snapshot trước lỗi còn sử dụng được | Không mặc nhiên |
| Backup độc lập | Khả năng phục hồi khi nguồn/cùng quyền quản trị không còn tin cậy | Có nếu retention/coverage đáp ứng | Phải được thiết kế và kiểm chứng |
| PITR | Khôi phục tới mốc thời gian hợp lệ trong cửa sổ được hỗ trợ | Có trong cửa sổ PITR | Phụ thuộc nơi lưu bản nền và log |
| CDC/event log | Phát thay đổi cho consumer/projection | Chỉ có thể hỗ trợ nếu log đủ và phục hồi có kiểm soát | Không mặc nhiên |
| Geo-replication | Có bản sao tại vị trí địa lý khác | Xóa nhầm vẫn có thể lan sang Region khác | Khác vị trí chưa chắc khác quyền kiểm soát |

“Không mặc nhiên” là điểm cốt lõi. Tùy hệ và cấu hình, một managed database có thể cung cấp backups độc lập như một tính năng riêng; hãy đọc chính xác contract và retention của tính năng đó.

### 2.1. Replication là trạng thái sống

Replica thường nhận hoặc đồng thuận về **các thay đổi mới**. Nó giúp cụm tiếp tục xử lý request khi một số thành phần lỗi, không được thiết kế mặc định như một kho chứa lịch sử không thể sửa.

### 2.2. Snapshot là mốc dữ liệu

Snapshot mô tả trạng thái có thể được giữ ở mốc t0. Nếu được lưu bền vững và nhất quán phù hợp, có thể dùng để tạo một bản clone hay làm nền restore. Nhưng snapshot trên cùng volume/account có thể cùng bị xóa hoặc mã hóa bởi attacker.

### 2.3. Backup là một khả năng phục hồi

Backup phải bao gồm cả dữ liệu, metadata, keys/dependencies cần thiết và quy trình restore đã được kiểm chứng. Một file copy tồn tại nhưng không thể giải mã, không biết schema hay bị lỗi checksum không đáp ứng mục tiêu.

### 2.4. Recovery không đồng nghĩa failover

Failover chuyển traffic sang replica đang sẵn sàng. Restore đưa hệ về trạng thái có thể dùng từ snapshot/backup/log và thường phải quyết định xử lý những mutations xảy ra sau mốc khôi phục.

## 3. Sơ đồ ba tầng bảo vệ

~~~mermaid
flowchart TD
    A["Application / Java services"] --> P["NoSQL primary / partition leaders"]
    P --> R1["Replica 1 / AZ B"]
    P --> R2["Replica 2 / AZ C"]
    P --> S["Consistent snapshot at t0"]
    S --> B["Independent backup repository"]
    L["Write-ahead / operation logs"] --> B
    B --> V["Independent validation / restore environment"]
    V --> X["Recovered dataset"]
    N["Shared admin credentials"] -. risk .-> P
    N -. risk if not separated .-> S
~~~

Mũi tên là mô hình khái niệm, **không khẳng định mọi engine đều có một primary hoặc mọi snapshot đọc trực tiếp từ primary**. DynamoDB là dịch vụ managed, Cassandra có mô hình replica/consistency khác MongoDB; chiến lược cụ thể phải theo engine.

### 3.1. Ba lớp trả lời ba câu hỏi

- Replica: “Nếu một node/zone hỏng, ai tiếp tục phục vụ?”
- Snapshot: “Dữ liệu ở thời điểm t0 là gì?”
- Backup độc lập: “Nếu nguồn, quyền quản trị hoặc địa điểm bị mất/chiếm, ta còn bản dữ liệu đáng tin để khôi phục không?”

### 3.2. Một hệ có thể cần cả ba

Đối với nghiệp vụ quan trọng, replication đảm bảo availability thường ngày; snapshots/logs tạo mốc phục hồi; bản backup tách quyền và vị trí bảo vệ trước lỗi tương quan.

### 3.3. Không nhất thiết dùng đúng ba sản phẩm

Một managed service có thể gộp một số cơ chế bên dưới. Điều cần thiết là chứng minh được các mục tiêu bảo vệ, không chỉ đếm tên tính năng trong bảng giá.

## 4. Những loại sự cố cần tách biệt

| Sự cố | Replication | Snapshot cùng cụm | Backup độc lập |
|---|---|---|---|
| Hỏng một disk/node | Thường giúp chịu lỗi nếu có đủ replicas | Có thể hỗ trợ | Hỗ trợ nếu phải rebuild |
| Mất một availability zone | Tùy placement/quorum | Tùy snapshot storage | Tùy nơi lưu |
| Lệnh DELETE nhầm | Thường lan truyền xóa | Chỉ giúp nếu giữ mốc trước xóa | Giúp nếu có mốc đủ cũ |
| UPDATE sai do bug | Thường lan truyền giá trị sai | Có thể phục hồi mốc cũ | Có thể phục hồi/đối soát |
| Ransomware có quyền DB | Replicas có thể cùng bị phá | Có thể bị xóa cùng quyền | Cần immutable/isolated policy |
| Account quản trị bị chiếm | Replicas không phải ranh giới IAM | Có thể cùng bị xóa | Tách principal/account giúp giảm rủi ro |
| Region outage | Chỉ khi đặt/replicate đủ xa | Snapshot trong Region có thể khó truy cập | Cross-Region theo RTO yêu cầu |
| Schema migration sai | Thường lan truyền | Có thể có pre-migration snapshot | Backup + restore drill giúp rollback dữ liệu |
| Encryption key mất | Replicas vẫn chứa ciphertext không đọc được | Snapshot cũng vậy | Backup phải có key-access/retention plan |
| Corruption do storage/driver | Có thể lan hoặc không tùy lỗi | Snapshot có thể đã chứa corruption | Cần nhiều mốc + kiểm tra integrity |

**Không đánh dấu một ô là “đảm bảo” nếu chưa biết replication topology, consistency settings, snapshot semantics, retention và quyền xóa của hệ đang dùng.**

## 5. Vì sao replication không thay backup?

### 5.1. Replication lan truyền writes hợp lệ lẫn writes sai

~~~text
t0: Order O101 tồn tại.
t1: Admin script DELETE O101 (nhầm).
t2: Replication áp dụng DELETE ở các replicas.
t3: Mọi replica đồng ý rằng O101 không còn.
~~~

Đây không phải replication bug. Nó đang duy trì hệ ở một trạng thái mới phù hợp mutation đã commit.

### 5.2. Corrupted application state vẫn có thể được nhân bản

Nếu code update sai priceMinor=0 cho hàng triệu products và commit thành công, các replicas có thể phân phối dữ liệu sai rất nhanh. Replication giúp “đồng bộ lỗi” nhanh như đồng bộ thay đổi đúng.

### 5.3. Độ trễ replication không phải chiến lược backup

Một replica bị trễ vài giây có thể vô tình còn dữ liệu cũ, nhưng dựa vào nó để restore là rủi ro: replica có thể bắt kịp bất cứ lúc nào, có thể mất snapshot consistent và chưa chắc giữ transaction boundary.

### 5.4. Đếm số replica không đo khả năng phục hồi xóa nhầm

RF=3 mô tả ba bản sao theo placement/consistency của engine, không nói ta có thể quay về 09:59 sau lệnh xóa lúc 10:00.

### 5.5. Replication có thể cải thiện durability nhưng không đủ bảo vệ lịch sử

Quorum/majority acknowledgment có thể giảm một số rủi ro mất write khi node lỗi, **nhưng không phải cơ chế chống hợp lệ hóa lệnh xóa sai**.

## 6. Replication đồng bộ, bất đồng bộ và phạm vi lỗi

### 6.1. Synchronous/quorum acknowledgement

Client có thể đợi số replicas/quorum xác nhận theo protocol. Nếu đã ACK, độ bền chịu một số lỗi có thể cao hơn mức ACK từ một node, nhưng các guarantees cụ thể phụ thuộc engine.

### 6.2. Asynchronous replication

Replica nhận write sau primary; khi failover có thể có replication lag và dữ liệu ACK theo cấu hình yếu bị mất hoặc tạm chưa thấy.

### 6.3. Replication có thể xuyên Region

Geo-replication hữu ích cho Region failure, nhưng lệnh xóa nhầm hoặc attacker mutation có thể tiếp tục lan truyền xuyên Region.

### 6.4. Replica không phải bản sao lưu tại thời điểm bất biến

Thường replica nhận writes liên tục. Không thể chọn “trạng thái lúc 09:45” trên một replica hôm nay nếu hệ không cung cấp lịch sử/PITR riêng.

### 6.5. Failure domain

Hai replicas trên hai nodes trong cùng rack không chịu lỗi rack như hai replicas ở hai AZ; hai Region cùng một cloud account và IAM admin cũng chưa độc lập về quyền xóa.

## 7. Snapshot là gì, và không phải là gì?

Snapshot có thể là:

- **Storage-level snapshot:** copy-on-write hoặc cơ chế block/storage ở một mốc.
- **Database-level snapshot:** engine tạo ảnh dữ liệu ở mốc nhất quán theo cơ chế của nó.
- **Logical export/dump:** bản xuất records/schema ở dạng có thể import lại, có thể không “instantaneous” nếu đọc kéo dài.
- **Managed point-in-time snapshot:** dịch vụ dựng bản tại mốc được chọn từ base + change log.

Không gộp tất cả thành “zip folder database”.

### 7.1. Snapshot không tự độc lập

Một snapshot trên cùng account/Region với cluster có thể cùng bị xóa khi credential admin bị chiếm, dù nó nằm trên storage khác.

### 7.2. Snapshot có thể rẻ nhờ copy-on-write

Một số storage snapshots chia sẻ blocks/chỉ lưu changed blocks; “snapshot 100 GB” không nhất thiết ngay lập tức copy riêng 100 GB. Nhưng khi source thay đổi/xóa, storage usage và costs có thể phát triển.

### 7.3. Snapshot có thể cần engine phối hợp

Copy thẳng các database files trong lúc engine đang ghi có thể tạo một tập file không nhất quán nếu không có snapshot/backup protocol chính thức.

### 7.4. “Snapshot succeeded” không chứng minh restore được

Cần thử restore vào môi trường độc lập, xác minh số records, indexes, quyền, encryption keys và ứng dụng đọc được.

### 7.5. Snapshot có thể là một thành phần của backup

Khi snapshot được export/copy đến repository đủ cách ly, giữ nhiều versions, có checksum và restore test, nó có thể trở thành một phần quan trọng của backup system.

## 8. Crash-consistent, application-consistent, transaction-consistent

### 8.1. Crash-consistent

Ảnh chụp tương đương “máy bị mất điện ngay thời điểm đó”; sau restore, database dựa trên journal/WAL/commitlog để recovery, **nếu tất cả files và logs cần thiết đều có trong ảnh**.

### 8.2. Application-consistent

Ứng dụng/database đảm bảo dữ liệu ở mốc chụp hợp lệ cho logic nghiệp vụ, ví dụ hoàn tất hoặc đóng băng một số writes, snapshot across dependent stores hoặc ghi checkpoint/watermark.

### 8.3. Transaction-consistent

Không xuất hiện trạng thái nửa transaction: một multi-document transaction đã commit thì thấy đầy đủ, transaction chưa commit thì không thấy. Khả năng này phải được bảo đảm theo engine và snapshot mechanism.

### 8.4. Multi-volume crash-consistency

Snapshot volume data lúc 10:00:01 nhưng volume journal lúc 09:59:59 có thể thiếu records phục hồi. Nếu cần nhiều volumes, phải dùng mechanism có tính nhất quán across volumes hoặc quy trình quiesce được hỗ trợ.

### 8.5. Cross-service consistency còn khó hơn

Order DB có OrderCreated nhưng Inventory DB vẫn chưa reserve ở mốc snapshot; một Saga đang IN_PROGRESS có thể là trạng thái hợp lệ nếu recovery workflow xử lý tiếp. Không mong các snapshots từng database tự tạo một transaction ACID xuyên services.

## 9. Backup độc lập là độc lập ở những chiều nào?

Độc lập không chỉ là “lưu tại một bucket khác”.

### 9.1. Quyền xóa và tài khoản

Nếu cùng principal có thể xóa nguồn và backup, một credential compromise có thể phá cả hai. Tách backup-writer, backup-reader, recovery-operator và người quản lý retention.

### 9.2. Storage/Region

Đặt backup ở storage/Region riêng khi RTO/RPO và threat model cần chịu Region outage. Nhưng bản copy cross-Region vẫn có thể chung organization admin hoặc key hierarchy.

### 9.3. Immutable retention

WORM/Object Lock hoặc cơ chế retention bất biến được hỗ trợ có thể ngăn xóa/sửa backup trong thời hạn đã đặt, kể cả với một số tài khoản có quyền cao. Hiệu quả phụ thuộc mode, provider, policy và khả năng sửa chính sách retention.

### 9.4. Credential separation

Ứng dụng production chỉ cần ghi backup hoặc trigger backup, thường không cần quyền xóa lịch sử backup. Recovery roles cần được cấp qua workflow kiểm soát.

### 9.5. Logical separation

Backup giữ nhiều mốc lịch sử, có manifest/checksum và không tự đồng bộ “xóa ở nguồn thì xóa ngay bản cũ” theo replication semantics.

### 9.6. Key independence

Encrypted backup cần keys hợp lệ và một plan phục hồi khi production IAM/key access không dùng được. Backup encryption key nằm trong cùng tài khoản bị chiếm có thể là điểm yếu.

### 9.7. Restore independence

Nếu chỉ restore được bằng một service account/cluster đã bị hủy, backup chưa thực sự phục hồi được. Test cần cho thấy có thể dựng môi trường mới theo quyền và công cụ được duy trì.

## 10. Các lớp dữ liệu cần đưa vào backup plan

Một NoSQL system không chỉ gồm documents:

~~~text
Canonical data
  + schema / table definitions / indexes
  + auth roles / ACL / grants (khôi phục theo policy)
  + write-ahead/change logs for PITR
  + database configurations/topology metadata
  + version/feature compatibility
  + encrypted data key references and recovery permissions
  + backup manifest / checkpoints
  + application state (idempotency, outbox, pending workflows)
~~~

### 10.1. Không phải mọi thứ nên restore nguyên xi

Production users/passwords/ACLs có thể không phù hợp restore vào staging/DR environment. Cần kế hoạch rebind identities, reissue credentials và tránh mở quyền quá rộng sau restore.

### 10.2. Indexes có thể rebuild, nhưng RTO phải tính

Một số backup giữ index files, số khác restore data rồi rebuild indexes. Khi sizing thời gian phục hồi, tính cả index build, shard rebalancing, cache warm-up và validation.

### 10.3. Search/cache thường là projection

Redis cache và search index có thể được rebuild từ source nếu chấp nhận RTO/cost. Nhưng Redis cũng có thể giữ sessions/queues/authoritative counters; không mặc định Redis chỉ là cache.

### 10.4. Các service-boundaries

Order DB, Payment ledger, Inventory reservations và outbox có thể cần thứ tự restore/đối soát riêng; backup mỗi DB thành công chưa đảm bảo business workflow hoạt động đúng.

## 11. RPO và RTO: biến câu “có backup” thành yêu cầu đo được

**RPO (Recovery Point Objective)** là mức mất dữ liệu theo thời gian tối đa mà nghiệp vụ chấp nhận, tính từ thời điểm sự cố về trạng thái có thể phục hồi.

**RTO (Recovery Time Objective)** là thời gian mục tiêu để khôi phục dịch vụ/khả năng nghiệp vụ theo phạm vi đã định, sau khi sự cố được xác định/kích hoạt recovery.

Ví dụ:

~~~text
RPO mục tiêu: 5 phút
RTO mục tiêu: 60 phút
~~~

Những con số này chỉ là ví dụ; một hệ thanh toán có thể cần mục tiêu nghiêm ngặt hơn một catalog.

### 11.1. RPO không phải backup frequency theo cách máy móc

Snapshot mỗi giờ, không có change logs, thường không thể hứa RPO 5 phút trong worst case. Nếu kết hợp snapshot nền + log archival liên tục có thể phục hồi gần mốc hơn, nhưng còn phụ thuộc độ trễ archive, gaps và retention.

### 11.2. RTO bao gồm nhiều hơn tốc độ copy file

\[
RTO_\text{end-to-end}
\approx T_\text{detect}+T_\text{decide}+T_\text{provision}
+T_\text{restore}+T_\text{replay}+T_\text{validate}+T_\text{cutover}
\]

Các giai đoạn có thể chồng nhau; công thức là khung lập kế hoạch, không phải đẳng thức đo được trong mọi kiến trúc.

### 11.3. Mục tiêu khác kết quả đo

RPO/RTO trên tài liệu không đồng nghĩa hệ đã đạt. Cần drill, ghi actual recovery point và elapsed recovery time theo kịch bản lỗi.

### 11.4. Đặt mốc thời gian đúng

Nếu 10:00:00 xảy ra xóa nhầm và backup gần nhất có state 09:45:00, data-loss window tính theo mốc phục hồi là 15 phút, chưa kể các writes đã diễn ra giữa hai mốc có thể cần phục hồi riêng.

### 11.5. RTO theo mức tối thiểu hữu dụng

Một database đã trả ping nhưng search indexes chưa dựng hoặc API chưa được chuyển traffic không hẳn đã đáp ứng RTO nghiệp vụ. Định nghĩa “recovered” bằng chức năng cụ thể.

## 12. Ví dụ tính RPO và chọn lịch backup

Giả sử:

~~~text
Snapshot đầy đủ: 00:00 mỗi ngày.
Incremental snapshot: mỗi 6 giờ.
Change logs: archive gần liên tục, có thể trễ 2 phút.
Incident: 14:35.
~~~

### 12.1. Nếu chỉ có full snapshot

Mốc gần nhất 00:00; dữ liệu từ 00:00 đến sự cố có nguy cơ cần xây lại. RPO thực tế với lịch ngày có thể lên gần 24 giờ.

### 12.2. Nếu có incremental gần nhất 12:00

Khôi phục đến 12:00; nguy cơ mất 2 giờ 35 phút dữ liệu nếu không có log replay.

### 12.3. Nếu có log archive đủ liên tục đến 14:33

Có thể chọn replay tới 14:33 nếu snapshot/log chain nhất quán và tool hỗ trợ, nhờ đó data-loss window có thể khoảng 2 phút. Nhưng phải xét **log tail thực sự được archive và khả năng restore**.

### 12.4. Xóa nhầm lúc 14:35

Nếu muốn tránh DELETE sai, restore đến ngay trước mốc xóa (ví dụ 14:34:59) có thể phù hợp hơn restore đến thời điểm hiện tại. Cần nhận diện mutation xấu, time precision, transaction boundary và sự khác biệt đồng hồ/commit timestamp.

### 12.5. Hai mục tiêu khác nhau

Region outage có thể cần khôi phục state mới nhất; logical corruption cần khôi phục trạng thái **trước điểm hỏng**. Cùng hệ backup nhưng điểm replay mục tiêu khác nhau.

## 13. Full, incremental và differential backup

### 13.1. Full backup

Lưu toàn bộ phạm vi dữ liệu tại mốc được chọn. Restore có thể trực tiếp hơn nhưng tốn dung lượng/bandwidth và thời gian tạo/copy.

### 13.2. Incremental backup

Chỉ giữ thay đổi từ mốc backup trước theo cơ chế engine/provider. Restore có thể cần base + chuỗi incrementals hoặc được dịch vụ tự tổng hợp; mất một mắt xích có thể làm một số restore points không dùng được.

### 13.3. Differential backup

Lưu thay đổi so với full backup nền. Restore thường cần full + differential gần nhất. Không phải mọi NoSQL provider cung cấp thuật ngữ hay tính năng differential như nhau.

### 13.4. Continuous log-based backup

Archive WAL/oplog/commitlog hoặc mechanism tương đương cho PITR. Có thêm yêu cầu log ordering, durability, gap detection và replay tới timestamp/sequence phù hợp.

### 13.5. Snapshot “incremental” của nhà cung cấp

Một managed snapshot có thể dùng cơ chế lưu changed blocks bên dưới; nó không có nghĩa người dùng phải tự quản lý chain như các file incrementals truyền thống. Tìm hiểu restore contract thay vì suy từ tên “incremental”.

### 13.6. Retention của một chain

Xóa full base trong khi còn giữ các incrementals phụ thuộc nó có thể làm restore thất bại. Retention logic phải biết dependency graph hoặc dựa vào service quản lý chain đúng cách.

## 14. Point-in-time recovery không chỉ là chọn giờ trên giao diện

PITR yêu cầu:

1. Một trạng thái nền hợp lệ.
2. Dòng thay đổi được ghi/archived đầy đủ trong cửa sổ cần phục hồi.
3. Thứ tự và transaction boundaries có thể replay chính xác.
4. Tool và metadata nhận diện điểm dừng hợp lệ.
5. Môi trường và keys đủ để đọc dữ liệu.

### 14.1. Oplog, WAL, commitlog không mặc nhiên là backup độc lập

MongoDB oplog, WAL của các engines hoặc Cassandra commitlog phục vụ replication/recovery theo thiết kế, nhưng có retention và cách sử dụng khác nhau. **File log đang nằm trên cluster không tự biến thành PITR archive bền vững.**

### 14.2. Cần log gap detection

Nếu một khoảng log bị mất, dù snapshot và các log còn lại đều “thành công”, replay qua gap có thể không thể bảo đảm consistency. Theo dõi contiguous sequence/offset/LSN/timestamp theo mechanism được hỗ trợ.

### 14.3. RPO bị giới hạn bởi archive lag

Nếu logs được ship mỗi 10 phút, không nên hứa RPO 30 giây chỉ vì ứng dụng có WAL. Actual archived/recoverable watermark mới là thứ cần đo.

### 14.4. Restore tới “ngay trước lệnh xóa”

Tìm operation bằng audit/oplog metadata có quyền truy cập, xác định mốc trước transaction/mutation xấu. Không chọn dựa trên thời gian laptop người dùng rồi giả định hoàn toàn đồng bộ với database commit clock.

### 14.5. PITR và transaction consistency

Nếu khôi phục giữa một multi-statement transaction chưa commit, hệ phải bỏ/hoàn nguyên các thay đổi chưa commit theo restore semantics. Không tự dừng replay tùy byte offset nếu tool không hỗ trợ.

## 15. Snapshot consistency xuyên shard và partition

Một cụm NoSQL phân tán có shards/partitions khác nhau:

~~~text
Shard A snapshot at 10:00:00.
Shard B snapshot at 10:00:20.
Shard C snapshot at 10:00:45.
~~~

Ghép ba snapshots độc lập có thể tạo một trạng thái chưa từng tồn tại logic trên toàn cụm.

### 15.1. Ví dụ chuyển tiền

~~~text
Shard A: debit account A at 10:00:10.
Shard B: credit account B at 10:00:11.
~~~

Nếu snapshot A tại 10:00:20 và snapshot B tại 10:00:00, bản restore có debit nhưng không có credit, trừ khi mechanism transaction/replay phối hợp giải quyết.

### 15.2. Cần backup protocol của engine

Đối với sharded MongoDB, managed DynamoDB hay Cassandra, sử dụng quy trình snapshot/backup được hỗ trợ theo topology, checkpoint/consistency, thay vì chụp file từng node ngẫu nhiên.

### 15.3. Application consistency có thể cần write barrier

Nếu không có mechanism snapshot toàn cụm được hỗ trợ, có thể cần quiesce writers, capture consistent checkpoints, export committed data và replay logs. Điều này ảnh hưởng availability và RTO/RPO, cần lên kế hoạch.

### 15.4. Một transaction ở hai databases

Nếu Order DB và Inventory DB không chia sẻ transaction manager, snapshot mỗi DB cùng “10:00” vẫn không bảo đảm mọi Saga đã hoàn tất. Có thể cần business reconciliation, event ledger và checkpoint cross-service.

### 15.5. Đồng hồ không đủ

NTP giúp so sánh timestamps nhưng không thay distributed consistent snapshot protocol. Mốc timestamp cùng tên không tự chứng minh các causal events đã được chụp đúng thứ tự.

## 16. Checkpoints, manifests và chứng cứ một bản backup

Một backup cần mô tả đủ để restore, ví dụ:

~~~yaml
backupId: orders-2026-11-14T000000Z
source:
  engine: example-nosql
  engineVersion: example-version
  deploymentId: cluster-orders-prod
  namespace: orders
consistency:
  mode: engine-supported-consistent-snapshot
  checkpoint: opaque-source-watermark
contents:
  snapshotRef: immutable-object-location
  logArchiveFrom: source-sequence-A
  logArchiveTo: source-sequence-B
  schemaRef: schema-export-location
security:
  encryptionKeyRef: recovery-key-alias
  backupPolicyVersion: 4
integrity:
  manifestDigest: sha256-placeholder
  status: VERIFIED
~~~

Đây là YAML mô tả metadata đề xuất, **không phải manifest chuẩn của một engine cụ thể**. Values như key ref, object location và deployment ID có thể là metadata nhạy cảm, chỉ hiển thị cho role có quyền.

### 16.1. Tính toàn vẹn

Checksums/hash cho backup objects, manifest có bảo vệ tính toàn vẹn, kiểm tra khả năng download và kiểm thử restore.

### 16.2. Nguồn version/feature

Backup trên phiên bản engine mới có thể không restore được trên phiên bản cũ. Cần lưu engine version, format, feature flags và tool version.

### 16.3. Schema và indexes

Một backup chỉ có rows mà thiếu schema/index definitions hoặc auth config có thể restore data nhưng làm API không chạy. Danh mục dependency phải rõ.

### 16.4. Metadata không thay phép restore

Checksum khớp chứng minh bytes đúng theo một digest, không tự chứng minh snapshot có nhất quán nghiệp vụ hoặc đúng tenant. Cần semantic validation.

## 17. 3-2-1 và 3-2-1-1-0: nguyên tắc chứ không phải phép đếm hình thức

Quy tắc 3-2-1 thường được hiểu:

- Ba copies dữ liệu (bao gồm nguồn).
- Hai loại media/storage độc lập.
- Một copy off-site.

Biến thể 3-2-1-1-0 thường bổ sung một bản offline/immutable/air-gapped theo cách triển khai, và mục tiêu **zero unverified errors** trong backup/restore verification.

### 17.1. Ba replicas không bằng ba backups

Nếu cả ba đều bị logical DELETE cập nhật trong vài giây, bạn không có ba restore points độc lập.

### 17.2. “Off-site” không giải quyết cùng IAM

Một bucket ở Region khác nhưng được cùng admin principal quyền xóa toàn bộ vẫn có common administrative failure domain.

### 17.3. Immutable khác không thể bị xóa dưới mọi tình huống

Object Lock có mode và cấu hình riêng; retention policies có thể bị cấu hình sai hoặc chưa áp trên mọi object/version. Verify policy thực tế và delete attempts trong test environment.

### 17.4. Air-gap có chi phí

Backup offline hoặc tách mạng có thể mạnh trước ransomware nhưng khó đạt RPO vài giây, tốn transfer/restore time. Chọn mức độ cách ly theo threat model và mục tiêu.

### 17.5. “Zero errors” phải được kiểm tra

Một dashboard “backup jobs successful” chưa chứng minh không có corruption. Integrity scans và periodic restore drills là phần cốt lõi.

## 18. Backup immutability và quyền xóa

Một chính sách mẫu:

~~~text
Production service:
  write operational data
  request backup creation
  no permission to delete protected backups

Backup operator:
  create/copy/verify backups
  cannot reduce immutable retention unilaterally

Recovery operator:
  read backup through approved emergency procedure
  restore to isolated account/environment

Security admin:
  reviews IAM, retention, access logs, key lifecycle
~~~

### 18.1. Least privilege của backup writer

Không cấp quyền xóa toàn bộ historical snapshots cho ứng dụng chỉ vì nó cần ghi bản backup mới.

### 18.2. Tách account và credential

Cross-account vault hoặc đối tượng lưu trữ có policy riêng giúp giảm khả năng một credential production compromise xóa cả backups.

### 18.3. Retention lock cần được đặt đúng lúc

Nếu backup object được upload nhưng chưa bật retention, attacker có thể xóa nó trong khoảng đó. Thiết kế controls từ thời điểm tạo hoặc kiểm tra trạng thái lock trước khi đánh dấu complete.

### 18.4. Backup deletion cũng cần lifecycle

Giữ mãi mọi backup làm tăng chi phí, rủi ro lưu PII không cần và có thể vi phạm retention policy. Cần deletion policy nhưng phải không bị writer/attacker dễ dàng rút ngắn.

### 18.5. Legal hold và privacy

Một yêu cầu xóa dữ liệu cá nhân có thể mâu thuẫn với immutable backup retention. Phải xử lý qua chính sách pháp lý, thời hạn và restoration controls, không sửa backup tùy tiện nếu không có thẩm quyền.

## 19. Retention, versioning và lịch lưu nhiều mốc

Một bản backup độc lập hữu ích khi **vẫn còn bản trước thời điểm lỗi**, không chỉ bản mới nhất.

### 19.1. Một snapshot mỗi ngày nhưng chỉ giữ bản gần nhất

Giả sử bug làm hỏng dữ liệu từ thứ Hai, nhưng tới thứ Tư người dùng mới phát hiện. Nếu các bản hằng ngày bị ghi đè và chỉ còn bản thứ Tư, backup cũng chứa dữ liệu lỗi.

### 19.2. Retention là phân bố của restore points

Một chính sách minh họa:

~~~text
Hourly recoverable points:  giữ 48 giờ
Daily backups:              giữ 30 ngày
Weekly backups:             giữ 12 tuần
Monthly backups:            giữ 12 tháng
~~~

Đây là lịch mẫu; policy thực tế cần xét RPO, khả năng lỗi được phát hiện muộn, dữ liệu nhạy cảm, chi phí và pháp luật.

### 19.3. Grandfather-Father-Son

GFS thường chỉ việc giữ một số mốc ngắn hạn, trung hạn và dài hạn với các chu kỳ ngày/tuần/tháng. Nó giảm lượng lưu so với giữ mọi snapshot mãi mãi, nhưng không tự đảm bảo dữ liệu trong các mốc đúng.

### 19.4. Backup rotation khác credential rotation

“Rotation” trong backup thường là lịch thay/cull các bản lưu theo retention; khác hẳn luân chuyển password hay cryptographic keys. Hãy dùng thuật ngữ rõ để tránh vô tình xóa key đang cần cho restore.

### 19.5. Retention dependency

Khi backup incremental phụ thuộc base, chính sách dọn cũ phải bảo vệ chain cần thiết. Test restore từ một mốc xa, không chỉ bản incremental mới nhất.

### 19.6. Detection window

Nếu corrupt data có thể tồn tại 45 ngày mới được phát hiện, chỉ giữ 7 ngày backup không đáp ứng một số kịch bản logical recovery. Đây là một quyết định nghiệp vụ, không thuần storage cost.

## 20. Khôi phục nguyên cụm, một collection/table hay một vài records?

**Scope của restore** ảnh hưởng mạnh tới RTO và rủi ro ghi đè dữ liệu mới.

### 20.1. Full-cluster disaster recovery

Dựng cụm mới từ backup, restore mọi dữ liệu cần thiết, validation và chuyển traffic. Hợp với mất toàn cụm, ransomware hoặc lỗi storage diện rộng.

### 20.2. Namespace/collection restore

Chỉ một MongoDB collection hay một DynamoDB table bị xóa nhầm; có thể tạo namespace mới từ backup thay vì ghi đè toàn database.

### 20.3. Item-level logical recovery

Nếu chỉ Order O101 bị xóa, full restore đè toàn hệ có thể làm mất hàng nghìn writes hợp lệ sau t0. An toàn hơn thường là **restore vào cluster cô lập rồi trích xuất đúng record**, đối soát với trạng thái hiện tại và áp một repair command có kiểm soát.

### 20.4. Restore cũng có thể là replay business events

Nếu có event-sourced canonical log đáng tin, có thể rebuild projection. Nhưng event log phải có durability, retention, event version/schema và completeness; không gọi bất kỳ Kafka topic/CDC queue nào là backup chỉ vì nó chứa events.

### 20.5. Ranh giới phục hồi

Phải biết cần phục hồi những gì: primary data, outbox, idempotency state, inventory holds, search indexes, Redis keys và external payment side effects không cùng một transaction.

### 20.6. Đừng overwrite production trước khi nhìn dữ liệu phục hồi

Khôi phục vào namespace/cluster cách ly, compare results, rồi mới quyết định merge/swap/cutover thường giảm nguy cơ hơn thao tác in-place không thể đảo ngược.

## 21. Restore không phải phép “undo” đơn giản

Giả sử t0=09:00 là snapshot tốt, t1=10:00 một operator xóa nhầm customer records, t2=10:10 có thêm 500 writes hợp lệ.

### 21.1. Full rollback về 09:00

Khôi phục tất cả về 09:00 cũng làm mất những cập nhật hợp lệ từ 09:00 đến 10:10. Đây có thể vi phạm business contract.

### 21.2. Selective repair

Có thể restore snapshot vào hệ cô lập, tìm những records bị xóa nhầm, so ownership/version với current source, rồi tái tạo có kiểm tra. Không blindly insert toàn bộ vì một số records có thể đã được tạo lại hợp lệ.

### 21.3. PITR trước mutation sai

Khôi phục toàn DB tới 09:59:59 có thể loại mutation xóa, nhưng các transactions hợp lệ sau đó vẫn cần cách xử lý. Đôi khi phải replay **có chọn lọc** từ authoritative event source; khả năng thực thi phụ thuộc engine/application và sự phức tạp.

### 21.4. Version và idempotency

Một repair write nên có operationId, expected version/generation và audit. Nếu không, recovery script chạy lại có thể tạo trùng hoặc ghi đè một phiên bản mới.

### 21.5. External systems

Khôi phục Order record cũ không tự đảo ngược payment đã capture hay email đã gửi. Cần reconcile side effects theo domain owner và Saga state.

## 22. Restore thành một môi trường biệt lập để kiểm chứng

Một recovery drill an toàn thường:

~~~text
Protected backup repository
    |
    v
Isolated restore account/network
    |
    +--> Restore database
    +--> Load schema/config metadata
    +--> Validate indexes/data counts
    +--> Test Java application read/write in restricted mode
    +--> Check security & encryption/decryption
    +--> Produce recovery evidence/report
~~~

### 22.1. Tách network và identity

Không cho recovered environment tự gửi email, charge thẻ, publish production messages hoặc gọi webhook thực. Dùng endpoint giả, egress deny hoặc integration stubs.

### 22.2. Bảo vệ dữ liệu nhạy cảm

Backup production có thể chứa PII. Môi trường drill phải có quyền, encryption, audit và data retention tương ứng; không sao chép xuống laptop cá nhân.

### 22.3. Không vô tình ghi vào production

Java service chạy cùng config có thể kết nối Redis/queue/Payment Provider thật. Kiểm tra credentials và network destinations trước khi chạy application smoke tests.

### 22.4. Health check không đủ

DB ping success không chứng minh các queries cốt lõi hay encryption key access hoạt động. Thực hiện những read paths đại diện và các validation không gây side effect.

### 22.5. Restore data cũng cần kiểm tra phân quyền

Khôi phục role/ACL nguyên xi vào DR có thể gây quyền admin quá rộng. Dùng kế hoạch rebind identities và xác minh least privilege.

## 23. Verify backup khác verify restore

### 23.1. Verify artifact

Checksum/hash, object count, manifest consistency, storage availability và retained lock. Điều này trả lời “backup files có còn lành lặn không?”.

### 23.2. Verify database

Restore engine mở được, có thể recovery journal/log, indexes hợp lệ, collection/table count và logical data consistency.

### 23.3. Verify application

Java queries hoạt động, encryption keys usable, tenants/permissions đúng, các nghiệp vụ tiêu biểu hợp lệ.

### 23.4. Verify time objective

Đo từ lúc bắt đầu disaster declaration tới lúc business function khôi phục trong RTO. Nếu chỉ đo tốc độ copy 100 GB file, RTO sẽ bị báo lạc quan.

### 23.5. Verify recoverable point

Đối chiếu watermark/timestamp/sequence thực tế. Một restore thành công nhưng dừng ở hôm qua không đạt RPO 5 phút.

### 23.6. Test restoration theo lịch

Không chờ production incident mới lần đầu đọc runbook. Tần suất drill phụ thuộc criticality, rate of change và chi phí; drill sau thay đổi topology/engine/key/version rất quan trọng.

## 24. Xác minh dữ liệu bằng counts, checksums và invariants

Một bản restore cần kiểm tra:

~~~text
Expected collections/tables present?
Count by tenant/date/status plausible?
Source backup checkpoint reached?
Key queries return expected objects?
Indexes available/rebuilt?
Outbox/idempotency states recoverable?
Encrypted fields decrypt successfully?
~~~

### 24.1. Count không đủ

Hai datasets có cùng 1 triệu records nhưng nội dung khác nhau. Dùng sampled hashes, business aggregates và invariants.

### 24.2. Checksum theo partition

Tính digest theo tenant/time bucket hoặc key range giúp phát hiện thiếu dữ liệu với chi phí vừa phải. Cần canonical serialization để hash ổn định, bỏ những trường metadata thay đổi không liên quan.

### 24.3. Invariant nghiệp vụ

Ví dụ:

~~~text
Each order has a valid tenant.
order.totalMinor matches the canonical pricing contract.
No duplicate idempotency operationId within scope.
Inventory reserved quantity obeys state rules.
~~~

Không kết luận business invariant từ current application state nếu snapshot được chụp giữa một workflow eventual; có thể cần mô hình PENDING/reconciliation.

### 24.4. Kiểm tra cả lỗi âm thầm

Một restore thiếu 1% dữ liệu cold có thể không lộ ngay trong GET hot keys. Sampling nên trải theo tenant, tuổi, size, shard/partition và các key versions.

### 24.5. Lưu kết quả verify

Ghi backupId, restore time, verification job version, counts/hashes/invariants và phần chưa kiểm tra. Không đưa plaintext PII/raw secrets vào report.

## 25. Backup encryption và kế hoạch giữ khóa

Một backup được mã hóa nhưng **không còn khóa để giải mã** có thể tương đương không có backup.

### 25.1. Encryption at rest

Backup repository nên mã hóa ở storage, transmission qua TLS, và dùng chính sách truy cập phù hợp. Application-level encrypted fields có key lifecycle riêng.

### 25.2. KMS/DEK dependencies

Nếu dữ liệu source đã mã hóa bằng envelope encryption, backup có thể chứa ciphertext và wrapped DEKs. Restore cần quyền với KEKs/versions và metadata AAD cần thiết.

### 25.3. KMS Region/account

Copy backup sang Region/account khác không tự chứng minh key có thể decrypt ở nơi mới. Cần xét tính năng re-encryption/cross-Region key policies của provider, quyền restore và kế hoạch disaster account.

### 25.4. Key rotation

Không xóa key version cũ chỉ vì backup hiện tại dùng version mới. Historical backups vẫn có thể cần old key material và key policy.

### 25.5. Bảo vệ backup credentials

Production identity không nên được phép xóa/chỉnh lock backup. Recovery credentials cần bảo quản, kiểm thử truy cập định kỳ và không để cùng một secret compromise phá cả source lẫn backup.

### 25.6. Secrets trong manifest

Manifest chỉ chứa key reference/metadata được phép, không lưu plaintext data keys, passwords, access tokens hoặc URI có credentials.

## 26. Backup chain, integrity và vấn đề “bản gần nhất đã hỏng”

### 26.1. Lỗi âm thầm

Một backup job viết ra object nhưng truyền thiếu bytes; object có thể vẫn tồn tại với tên đúng. Verify checksums và restore.

### 26.2. Backup corruption theo thời gian

Stored objects có thể không truy cập được do lifecycle policy sai, permission change hoặc mất key. Kiểm tra định kỳ không chỉ ngay sau tạo.

### 26.3. Incremental chain gaps

Nếu chain A→B→C→D mà C mất, có thể không restore D theo cơ chế đó. Một backup catalog phải thể hiện dependencies và chỉ xóa khi không phá các restore points còn giữ.

### 26.4. Multiple recovery generations

Giữ các base backups độc lập theo lịch có thể giảm blast radius nếu một chain lỗi. Quyết định dựa trên cost, RTO và provider design.

### 26.5. Backup thử restore nhiều thế hệ

Không luôn test bản mới nhất. Thử một backup cũ hơn để phát hiện key retention, format upgrade và catalog/incremental dependency problems.

## 27. Backup và schema evolution

### 27.1. Dữ liệu cũ có schema cũ

Một backup sáu tháng trước có thể chứa fields, enum states hoặc ID formats mà Java application hiện tại không còn hỗ trợ.

### 27.2. Restore compatible engine versions

Một backup từ engine version A cần được restore bằng phiên bản được hỗ trợ; nâng cấp major version, storage engine format và feature flags có thể ràng buộc restore path.

### 27.3. Migration sau restore

Nếu restore vào cluster mới rồi chạy migrations, cần kiểm thử migrations đối với dữ liệu cũ; không chạy production migration tool trên backup chưa cô lập.

### 27.4. Replay từ event logs cần versioned events

Event schemas có thể thay đổi theo thời gian. Rebuild projection từ logs cũ cần reader/upcaster/compatibility plan.

### 27.5. Metadata và configuration

Schema definitions, indexes, TTL policies, table capacity settings, partitioning logic và feature flags ảnh hưởng chức năng sau restore. Lưu chúng theo backup snapshot/commit version.

## 28. Backup và indexes, TTL, caches

### 28.1. MongoDB indexes

Dump/restore logic có thể dựng lại index theo metadata/công cụ thay vì copy raw index structures. Thời gian index build có thể chiếm phần lớn RTO.

### 28.2. Cassandra tables/secondary structures

SSTable snapshot/restore cần đúng schema và maintenance theo hướng dẫn. Materialized views/indexes và topology có thể yêu cầu rebuild hoặc reconciliation.

### 28.3. DynamoDB tables/GSIs

Khi restore table, cần đối chiếu GSI definitions, capacity modes, encryption, streams, TTL, PITR và tags/permissions theo behavior thực tế của service. Không assume mọi configuration tự theo cùng.

### 28.4. Redis cache

Nếu Redis chỉ là derived cache, rebuild có thể chấp nhận nhưng cache stampede và backend load sau disaster phải được tính RTO. Nếu Redis giữ state quan trọng thì persistence/backup phải theo state semantics.

### 28.5. TTL sau restore

Records có thời điểm hết hạn cũ có thể lập tức expire khi được restore hoặc cần được cleanup theo engine. Phải biết liệu recovery cần dữ liệu lịch sử hay chỉ dữ liệu còn active.

## 29. MongoDB: replica set không thay logical backup

Trong MongoDB replica set, primary và secondaries phục vụ replication và failover. Nếu ứng dụng xóa document bằng một mutation được commit, mutation đó thường được replicate.

### 29.1. Backup phải tính consistency

Các lựa chọn có thể gồm:

- Cơ chế backup/snapshot do managed provider hỗ trợ, có thể kèm PITR.
- Database-aware filesystem snapshot theo quy trình đúng cho storage engine và topology.
- Logical backup bằng mongodump/mongorestore trong phạm vi mà công cụ hỗ trợ.

Chúng có trade-off khác về kích thước, tốc độ và khả năng chụp dữ liệu nhất quán khi có concurrent writes.

### 29.2. Logical dump không mặc nhiên là một ảnh tức thời

Nếu một job mongodump chạy từ 12:00 đến 12:20 trong lúc hàng triệu writes tiếp tục, các documents khác nhau có thể được đọc tại những thời điểm khác nhau, trừ khi công cụ/option/topology cung cấp cơ chế consistency phù hợp.

### 29.3. Oplog hỗ trợ một số backup workflows

Trong các tình huống/phiên bản được hỗ trợ, mongodump có tùy chọn liên quan oplog để cải thiện consistency khi dump replica set và mongorestore có cơ chế replay. Không áp dụng một option đơn giản cho mọi sharded cluster hay thay thế hoàn toàn PITR theo provider; kiểm tra giới hạn của phiên bản và topology đang dùng.

### 29.4. Backup ở mức sharded cluster

Chụp từng shard độc lập mà không phối hợp checkpoint/configuration state có thể tạo trạng thái cross-shard không nhất quán. Cần dùng quy trình backup sharded cluster được hỗ trợ.

### 29.5. Restore vào namespace cô lập

Nếu chỉ collection orders bị xóa nhầm, một chiến lược là restore toàn tập hoặc collection vào cluster riêng, lấy các records đúng tenant/time và merge bằng version checks.

### 29.6. MongoDB change streams không phải backup

Change streams có thể giúp downstream consumers nhận updates, nhưng resume token/change history bị giới hạn và không bảo đảm tồn tại độc lập khi cluster bị phá. Muốn PITR, cần backup/log archival theo mechanism được hỗ trợ, không dựa vào một consumer đang chạy.

### 29.7. Indexes và roles

Mongodump logical data/metadata không đồng nghĩa mọi users, roles, cluster-level settings hay external secrets sẽ được khôi phục tự động. Lập danh mục riêng theo tool và deployment.

### 29.8. Cần test restore thật

Xác minh sau restore: số records, unique indexes, TTL indexes, sharding/tenant boundaries, Java driver compatibility và quyền đọc/ghi theo role mới.

## 30. DynamoDB: Multi-AZ, Global Tables, on-demand backup và PITR là các chức năng khác nhau

DynamoDB là managed NoSQL service nên người dùng không tự chụp disk của node. Cần phân biệt các tính năng do dịch vụ cung cấp.

### 30.1. Durability/replication của table

DynamoDB tự quản lý các bản sao/hạ tầng bên dưới theo phạm vi dịch vụ. Điều đó **không tự tạo khả năng quay về trước DELETE sai** trong application.

### 30.2. Global Tables

Global Tables cung cấp replication đa Region theo chế độ/khả năng cụ thể. Nếu một DELETE hợp lệ được replicated, Region khác có thể cùng mất item; đó không phải independent historical backup.

### 30.3. On-demand backup

Một bản backup theo yêu cầu có thể chụp table tại một mốc và cho phép restore theo service API. Nên quản lý retention, permission, encryption và restore target riêng.

### 30.4. Point-in-time recovery

PITR là tính năng riêng cung cấp cửa sổ recoverable times khi được bật/hỗ trợ. Cửa sổ chính xác và behavior có thể thay đổi theo cấu hình/dịch vụ; không tự ghi “giữ vô hạn”. Kiểm tra earliest/latest restorable times.

### 30.5. Restore thường tạo một table mới

Thiết kế restore/cutover cần chuẩn bị tên table mới, IAM permissions, application config, indexes/capacity/streams/TTL và các dependencies theo metadata mà service thực sự restore. Không giả định restore trực tiếp đè table đang active hoặc mọi settings tự giống ban đầu.

### 30.6. Backup độc lập hơn cần chính sách riêng

Backup/restore có sẵn không tự bảo đảm cross-account, immutable retention hay quyền xóa tách biệt. Nếu threat model gồm tài khoản AWS bị chiếm hoặc Region outage, cần chiến lược vault/copy/retention/keys phù hợp với các tính năng đang hỗ trợ.

### 30.7. Query sau restore

Một GSI hoặc read model có thể khác hiện trạng/đang build tùy restoration. Test GetItem theo PK, Query qua GSI, pagination, TTL behavior và permissions, không chỉ gọi DescribeTable.

### 30.8. DynamoDB Streams không phải vô hạn

Streams hữu ích cho change processing nhưng có retention và delivery semantics khác backup/PITR. Một consumer đang đọc stream không thay thế bản sao lưu độc lập.

## 31. Cassandra/ScyllaDB: replication factor, SSTable snapshot và commitlogs

Cassandra/ScyllaDB là hệ phân tán kiểu wide-column/LSM; replication factor mô tả bản sao dữ liệu theo topology/consistency, không giữ các mốc lịch sử để rollback.

### 31.1. Tombstone cũng được replicate

Một DELETE tạo tombstone hoặc metadata xóa theo engine; replication và repair giúp các replicas dần tôn trọng delete. Tăng RF không tạo khả năng quay lại trước delete.

### 31.2. SSTable snapshot

Cassandra có cơ chế snapshot các SSTable files, thường thông qua các công cụ quản trị như nodetool snapshot. Cách nó sử dụng hard links/files phụ thuộc filesystem và version.

### 31.3. Snapshot ở từng node chưa phải backup ngoài cụm

Nếu snapshots nằm cùng disks của nodes, mất cụm hoặc xóa file có thể làm mất chúng. Cần copy/verify tới repository độc lập theo topology, manifest và schema.

### 31.4. Một logical table có nhiều replica files

Backup/restore trên các nodes cần biết token ranges, replica placement, schema, partitioners, compaction strategy và cách restore/streaming tương thích. Không ghép SSTables từ nhiều mốc tùy tiện rồi giả định một transaction-consistent cluster snapshot.

### 31.5. Incremental backup

Một số Cassandra deployments hỗ trợ lưu newly flushed SSTables và cơ chế incremental backup. Cần hiểu full base, SSTable coverage, compaction và catalog; những file incremental riêng lẻ không tự là PITR hoàn chỉnh.

### 31.6. Commitlog

Commitlog phục vụ write durability/recovery trên node. PITR theo commitlog yêu cầu giải pháp archival/replay phù hợp và bảo đảm không gap; không suy rằng bật commitlog mặc định có nghĩa restore được mọi timestamp.

### 31.7. ScyllaDB khác theo version/managed service

ScyllaDB có công cụ/backup service và storage format/lifecycle riêng theo deployment. Không áp dụng nguyên một lệnh nodetool Cassandra cho mọi ScyllaDB version mà không kiểm tra tài liệu sản phẩm.

### 31.8. Restore verification

Kiểm tra keyspaces, table definitions, clustering order, partition widths, TTL/tombstone semantics, read CL và read queries. Sau restore, repair/bootstrap/streaming có thể tăng latency; tính vào RTO.

## 32. Redis: replication và persistence có nhiệm vụ khác nhau

Redis thường xuất hiện như cache, session store, queue hoặc operational data store. Đầu tiên cần xác định dữ liệu Redis có thể rebuild từ authority khác hay không.

### 32.1. Redis replication

Replicas giúp failover/read scalability tùy deployment. Một DEL/FLUSH được thực hiện hợp lệ có thể lan sang replica, không lưu “bản trước khi xóa” theo mặc định.

### 32.2. RDB snapshot

RDB tạo ảnh dữ liệu Redis tại mốc theo cơ chế persistence. Nó có thể dùng để khởi động/khôi phục trong phạm vi cho phép, nhưng nếu file nằm cùng server và bị xóa/ransomware thì chưa độc lập.

### 32.3. AOF

Append Only File ghi các commands/mutations theo chính sách đồng bộ đĩa. AOF có thể giảm mất dữ liệu giữa các snapshots và hỗ trợ restart/recovery, nhưng **AOF hiện hành trên cùng máy không tự là backup immutable**. Một lệnh DEL sai cũng có thể xuất hiện trong AOF.

### 32.4. RDB/AOF lựa chọn theo durability

RDB interval, AOF fsync policies, rewrite và replication đều tạo trade-off về RPO, latency, disk và recovery. Không gọi Redis “bền vững tuyệt đối” chỉ vì có replica.

### 32.5. Cache có thể không cần backup

Nếu tất cả Redis keys là cache có thể rebuild, independent backup Redis không luôn đáng chi phí; nguồn canonical cần backup. Nhưng tính thời gian warm cache và stampede trong RTO.

### 32.6. Redis chứa authoritative state thì khác

Nếu Redis là nơi duy nhất giữ rate limits critical, sessions không thể tái tạo, queues/counters có side effects hoặc token blacklists, phải đánh giá dữ liệu mất khi Redis failure và recovery workflows.

### 32.7. Avoid destructive restore

Restore RDB/AOF không nên đè Redis production đang live nếu chưa có kế hoạch; những keys mới/expirations ngoài snapshot có thể mất hoặc có semantics khác.

## 33. Elasticsearch/OpenSearch: snapshot repository khác replica shards

Search cluster có primary/replica shards để availability và query throughput, nhưng delete/update/reindex lỗi có thể được phản ánh trên cả primary/replica.

### 33.1. Snapshot API/repository

Đối với Elasticsearch/OpenSearch, dùng cơ chế snapshot repository được hỗ trợ cho backup cluster/index state; không copy raw index files của các nodes trong lúc cluster hoạt động rồi xem là consistent backup.

### 33.2. Snapshot chỉ bảo vệ phạm vi đã chọn

Chọn indexes/data streams và cluster state theo options, version và repository semantics. Nếu một index quan trọng không được include, snapshot thành công vẫn không chứa nó.

### 33.3. Repository độc lập và quyền hạn

Một repository ở object storage có thể cần cross-account, lock và role tách biệt. Nếu cluster được cấp quyền xóa mọi snapshots trong cùng bucket, attacker chiếm cluster credential vẫn có thể phá backup.

### 33.4. Search thường là projection

Nếu authoritative products nằm ở MongoDB/DynamoDB, có thể rebuild search từ source và event logs. Nhưng reindex hàng TB có thể vượt RTO; đôi khi snapshot search vẫn cần để giảm thời gian.

### 33.5. Index alias và cutover

Sau restore phải kiểm tra aliases, mappings, analyzers, index templates, security, shard allocation và application query behavior; đừng chỉ thấy index green là coi phục hồi xong.

### 33.6. Compatibility

Snapshot của engine/index version có thể có constraints khi restore lên cluster version khác. Ghi version và test upgrade path trước disaster.

## 34. Event log, Kafka, outbox và CDC: khi nào đủ để rebuild?

Giả sử canonical Order DB ghi outbox events:

~~~text
OrderCreated(O101)
OrderConfirmed(O101)
OrderShipped(O101)
~~~

Consumer dùng events để dựng search read model.

### 34.1. Rebuild projection

Nếu event stream đầy đủ trong window và handlers idempotent, có thể xóa/rebuild projection; đây là **derived-state recovery**, không nhất thiết restore canonical source.

### 34.2. Retention hữu hạn

Nếu Kafka topic giữ 7 ngày nhưng read model cần lịch sử 3 năm, chỉ replay topic 7 ngày không dựng được full state nếu không có base snapshot/archive.

### 34.3. Event schemas/versioning

Replay old events cần handlers tương thích. Thay đổi payload fields hoặc enum có thể khiến rebuild lỗi ở event cũ.

### 34.4. Event ordering và duplicates

Delivery at-least-once có thể gửi lặp, cùng entity có thể có event order/version. Projector phải chống duplicate/stale events, không tạo thêm business actions khi replay.

### 34.5. Outbox không tự bảo vệ canonical writes

Nếu lệnh xóa nhầm được commit như một event hợp lệ, event replay có thể tái tạo đúng trạng thái đã bị xóa. Để rollback logical error cần mốc trước lỗi và policy chọn event nào được áp dụng.

### 34.6. Backup event archive

Nếu event log được coi là source of truth, nó cũng cần backup/retention/immutability, schema registry compatibility, keys và restore drills như database.

## 35. Managed backup không miễn trách nhiệm restore

Một managed NoSQL provider có thể tự vận hành backups. Người dùng vẫn phải biết:

- Backup tự bật hay cần bật?
- Retention bao lâu?
- Có hỗ trợ PITR không, cửa sổ nào?
- Có thể restore tới cùng Region/account hay khác?
- Restore tạo cluster/table mới hay overwrite?
- Chi phí storage/recovery/transfer thế nào?
- Backup gồm indexes/users/roles/streams/config không?
- Keys, IAM và network có còn sử dụng được khi source account/Region lỗi?
- Có immutable retention/cross-account copy theo threat model không?
- Có bằng chứng restore drill gần đây không?

### 35.1. SLA provider không thay business RTO

Provider cam kết uptime của dịch vụ hoặc vận hành backup theo contract, nhưng application cutover, secrets, migrations và validation vẫn có thể làm recovery kéo dài.

### 35.2. Đừng dựa vào bảng giá cũ

Storage tier, PITR window và backup features thay đổi theo provider/version. Với bài này, công thức và phương pháp được mô tả tổng quát; khi triển khai phải kiểm tra tài liệu/cấu hình hiện hành.

### 35.3. Tính năng bị tắt mới là thực trạng

Một hệ hỗ trợ PITR nhưng table production chưa bật PITR không có khả năng phục hồi PITR chỉ vì tính năng tồn tại trong documentation.

## 36. Một kiến trúc mẫu kết hợp replication, PITR và independent backup

Giả sử Order Service chạy trên Java với NoSQL canonical database và search projection:

~~~text
                             ┌────────────────────────────┐
                             │ Java Order Service         │
                             └────────────┬───────────────┘
                                          │
                     ┌────────────────────▼─────────────────────┐
                     │ NoSQL source / HA replicas (3 AZs)      │
                     │ Replication protects node/AZ failures   │
                     └───────────┬──────────────────┬───────────┘
                                 │                  │
                    Snapshot/log backup       Outbox / CDC
                                 │                  │
                    ┌────────────▼─────────┐        ▼
                    │ Backup account/vault │   Search projection
                    │ versioned + retained │   Rebuildable, lag measured
                    │ encryption + audit   │
                    └────────────┬─────────┘
                                 │
                           Restore drill
                                 │
                       Isolated recovery VPC
~~~

### 36.1. Failure domain của mỗi lớp

- NoSQL replicas: node/AZ operations.
- PITR: temporal recovery from recent logical mistakes.
- Immutable vault: account/control-plane compromise và historical recovery.
- Isolated DR: recovery when production cluster/identity cannot be trusted.

### 36.2. Chính sách writes

Java client dùng write acknowledgment/consistency phù hợp durability contract. Nhưng application còn cần idempotency và reconciliation để tránh duplicate effects khi response timeout.

### 36.3. Chính sách restore

Với một record xóa nhầm, restore isolated và merge có điều kiện; với mất toàn cụm, dựng cluster mới và cutover; với search lag, rebuild projection từ source/outbox.

### 36.4. Tránh một điểm hỏng mới

Backup repository cũng cần IAM, key availability, versioning và monitoring. Tách account nhưng không có recovery key hoặc không có thủ tục break-glass vẫn có thể thất bại.

## 37. Backup job cần quan sát gì?

Một status SUCCESS chưa đủ. Các metrics đề xuất:

| Metric | Câu hỏi vận hành |
|---|---|
| backup_attempts_total | Có bao nhiêu lượt tạo backup? |
| backup_failures_total{reason} | Thất bại do storage, auth, engine, timeout hay quota? |
| backup_last_success_timestamp_seconds | Bản thành công gần nhất từ lúc nào? |
| backup_bytes_written_total | Dung lượng đã ghi? |
| backup_duration_seconds | Tạo/copy backup mất bao lâu? |
| backup_objects_verified_total | Bao nhiêu artifacts qua integrity checks? |
| backup_manifest_validation_failures_total | Metadata/chain có thiếu? |
| backup_restore_point_timestamp_seconds | Dữ liệu có thể khôi phục tới mốc nào? |
| backup_immutable_retention_violations_total | Có backup chưa được khóa retention đúng policy? |
| backup_key_access_failures_total | Recovery key/IAM có vấn đề? |

Các tên metric trong bảng là gợi ý application/collector, không phải names mặc định của một provider.

### 37.1. Đừng nhầm “job kết thúc” với “mốc recoverable mới”

Một backup job lúc 11:00 có thể chụp state tới 10:53 vì pipeline lag. Alert phải dựa trên **latest verified recoverable point**, không chỉ thời gian process kết thúc.

### 37.2. Cảnh báo backup age

~~~text
Now:                          12:00
Latest verified restore point:11:57
Recoverable lag:              3 minutes
~~~

Nếu RPO mục tiêu 5 phút, hiện có vẻ trong ngưỡng. Nhưng cần tính worst-case và khả năng restore, không chỉ một sample.

### 37.3. Backup storage consumption

Monitor object count, bytes, incremental retention cost và approaching quota. Repository đầy có thể khiến job dừng hoặc mất khả năng giữ restore points mới.

### 37.4. Một số metric cần có nguồn khác

Quyền immutable retention hoặc Object Lock không thể suy từ app counter tự báo; phải kiểm tra từ provider/control plane một cách có thẩm quyền.

## 38. Metrics phục hồi quan trọng không kém metrics backup

Đo:

~~~text
restore_drills_total{result=...}
restore_duration_seconds{scope=...}
restore_bytes_read_total
restore_point_lag_seconds
restore_data_validation_failures_total
restore_key_unavailable_total
restore_indexes_build_duration_seconds
restore_application_readiness_seconds
~~~

### 38.1. Successful restore có nhiều mức

Một recovery có thể:

1. Download files thành công.
2. Database start thành công.
3. Data verification thành công.
4. Application smoke tests thành công.
5. Business traffic cutover thành công.

Chọn rõ mốc “restored” theo SLO.

### 38.2. Đo restore từ backup cũ

Nếu data encrypted bằng key v1, một drill chỉ dùng backup v3 không kiểm chứng được key retention cho dữ liệu lịch sử.

### 38.3. RTO có thể tăng theo size

Restore cluster 100 GB với indexes nhỏ không đại diện một cụm 20 TB, 8 indexes và 20 triệu hot requests. Benchmark/recovery plan cần capacity forecast.

### 38.4. Tách manual time

Nếu trung bình mất 40 phút chờ security approval và 10 phút restore, RTO end-to-end là gần 50 phút cộng các bước khác. Runbook có thể cần pre-approved break-glass protocol.

## 39. Java: mô hình metadata backup có thể kiểm chứng

Một service Java không nhất thiết tự thực hiện disk snapshot. Nó có thể làm **backup coordinator** ghi nhận manifest và chỉ đánh dấu ready khi external backup service xác nhận.

~~~java
import java.time.Instant;
import java.util.List;

public record BackupArtifact(
        String objectRef,
        String checksumSha256,
        long sizeBytes
) {}

public record BackupManifest(
        String backupId,
        String engineVersion,
        Instant capturedAt,
        Instant recoverableUntil,
        String consistencyMode,
        String restorePointId,
        List<BackupArtifact> artifacts,
        String keyReference,
        boolean integrityVerified
) {}
~~~

### 39.1. Không coi boolean integrityVerified là toàn bộ bằng chứng

Một field do writer tự đặt true chưa thay phép kiểm tra checksum từ storage, chain completeness và independent restore. Cần lưu evidence/hashes và chữ ký/policy nếu threat model yêu cầu chống sửa manifest.

### 39.2. Không lưu raw keys vào manifest

keyReference có thể là alias/key ID được phép, không bao giờ là DEK plaintext hoặc KMS key material.

### 39.3. Schema version của manifest

Khi backup format thay đổi, manifest parser cần versioning/backward compatibility. Một restore trong tương lai phải đọc được metadata của bản cũ.

### 39.4. Checkpoint không phải wall-clock time tự đặt

restorePointId nên đến từ engine/provider, ví dụ checkpoint token/sequence hợp lệ. Không lấy Instant.now() trên application server rồi coi đó là commit watermark.

### 39.5. Hỗ trợ nhiều artifacts

Một backup có thể gồm nhiều objects per shard/table và log segments. Nếu thiếu một object, trạng thái verification phải phản ánh.

## 40. Java: safe restore readiness checks

Một validator đơn giản giúp chặn **những trường hợp metadata thiếu rõ ràng** trước khi gọi restore API:

~~~java
import java.time.Instant;

public final class BackupPolicyValidator {
    public static void validate(
            BackupManifest manifest,
            Instant targetPoint
    ) {
        if (manifest.artifacts() == null
                || manifest.artifacts().isEmpty()) {
            throw new IllegalArgumentException("No backup artifacts");
        }
        if (!manifest.integrityVerified()) {
            throw new IllegalStateException("Backup not verified");
        }
        if (manifest.keyReference() == null
                || manifest.keyReference().isBlank()) {
            throw new IllegalStateException("Recovery key unavailable");
        }
        if (targetPoint.isBefore(manifest.capturedAt())
                || targetPoint.isAfter(manifest.recoverableUntil())) {
            throw new IllegalArgumentException("Target outside declared window");
        }
    }
}
~~~

**Đây chỉ là kiểm tra metadata minh họa**, không phải một proof có thể restore. capturedAt/recoverableUntil không nhất thiết là mô hình đúng với snapshot thuần hoặc engine-specific PITR; cần định nghĩa mốc thực theo provider và xác minh thực tế.

### 40.1. Không tin manifest không được xác thực

Nếu attacker sửa được manifest, họ có thể đặt integrityVerified=true hoặc đổi keyReference. Backup catalog cần giới hạn quyền, checksum/signature/attestation khi phù hợp.

### 40.2. Không truy cập recovery key trong validator

Việc kiểm tra key reference tồn tại chỉ là precondition; thực tế phải test KMS decrypt/unwrap với quyền restore trong môi trường cách ly.

### 40.3. Không in full manifest tùy tiện

Object references, account IDs, topologies có thể là metadata nhạy cảm. Log backupId, status category và hash/alias đã được phép.

## 41. Restore orchestration: làm gì trước khi trả traffic?

Một quy trình full recovery:

~~~mermaid
flowchart TD
    A["Declare incident / isolate compromised source"] --> B["Choose restore point and backup set"]
    B --> C["Provision isolated target with IAM, KMS, network"]
    C --> D["Restore base snapshot and logs"]
    D --> E["Database recovery, indexes and schema"]
    E --> F["Verify data counts, versions, invariants"]
    F --> G["Reconcile outbox, projections and external effects"]
    G --> H["Canary Java service with restricted egress"]
    H --> I{"RPO/RTO and correctness accepted?"}
    I -->|Yes| J["Controlled cutover and monitor"]
    I -->|No| K["Investigate alternate point / repair"]
    K --> B
~~~

### 41.1. Incident declaration

Nếu source đang bị ransomware hoặc credential compromise, không tự cho recovery system truy cập source bằng cùng quyền mạnh; isolate theo incident runbook trước.

### 41.2. Chọn restore point

Xác định lỗi là physical outage, logical corruption hay malicious change, từ đó chọn latest good mốc phù hợp và dữ liệu có thể mất.

### 41.3. Validate trước cutover

Chạy sample queries theo tenants/tables, decrypt, index/query shape, uniqueness/invariants và service health.

### 41.4. Reconcile với external world

Khôi phục database về quá khứ không đảo ngược payment capture/shipping webhooks đã xảy ra. Xác định facts từ authoritative owners và reconcile.

### 41.5. Cutover có điều kiện

Quản lý DNS/service discovery, client pools, token/cache invalidation, feature flags và traffic ramp. Không chuyển toàn bộ traffic chỉ vì DB process khởi động.

## 42. Runbook: xóa nhầm một tenant trong NoSQL

### Bước 1 — Khoanh vùng sai sót

Thu thập tenantId/collection, operationId, audit timestamp và phạm vi DELETE. Dừng job gây lỗi và tránh chạy lại tự động.

### Bước 2 — Đánh giá nguồn live

Kiểm tra xem deletes đã replicated/committed tới đâu. Không “cứ tìm replica chậm” rồi xem đó là backup đáng tin.

### Bước 3 — Xác định restore point tốt

Tra backup catalog/PITR window gần trước mutation sai; xác minh recovery key, artifact integrity và trạng thái immutable.

### Bước 4 — Restore vào môi trường cô lập

Không overwrite toàn production. Đọc restored records và lập danh sách tài nguyên cần repair.

### Bước 5 — So sánh current source

Một số items có thể đã được tạo lại hoặc cập nhật hợp lệ sau xóa. Dùng version/unique key và chính sách merge thay vì insert mù.

### Bước 6 — Repair qua domain API/command

Thực hiện conditional writes, operationId/audit, rate limit và dry-run để tránh phá invariants. Nếu cần bulk repair, ghi checkpoint/resumability.

### Bước 7 — Rebuild projections

Search/Redis cache có thể vẫn thiếu items; invalidate/reindex theo source versions, tránh replay stale events.

### Bước 8 — Xác minh

Đối soát item count theo tenant, sample values, business consistency và user-visible GET. Theo dõi p99, errors và outbox lag sau repair.

### Bước 9 — Bảo vệ khỏi tái diễn

Siết destructive operation approvals, IAM, soft delete nếu phù hợp, dry-run, change review và restore drills.

## 43. Runbook: mất toàn Region

### 43.1. Có replica ở Region khác?

Nếu geo-replication đã đáp ứng contract và còn dữ liệu đủ mới, failover có thể nhanh hơn full restore. Nhưng phải kiểm tra replication lag, conflict/fencing và khả năng writes bị mất theo acknowledgment mode.

### 43.2. Nếu cần independent restore

Dựng new cluster từ cross-Region backup, IAM/KMS/access, schema/indexes và DNS/config cutover. Không giả định backup ở Region mất vẫn có thể tải về ngay.

### 43.3. Ngăn split brain

Nếu primary cũ hồi phục, không để hai cụm cùng nhận writes mà không có fencing/ownership protocol. Cần reconciliation trước rejoin.

### 43.4. Kiểm tra business continuity

Order create, inventory reserve, payment idempotency, user authentication và search phải chạy được theo định nghĩa RTO; một DB ping không đủ.

### 43.5. Đo actual recovery

Ghi earliest unavailable time, declaration, provision, restore, validation và cutover; tính RPO actual theo latest committed/recoverable source watermark.

## 44. Runbook: ransomware hoặc admin account compromise

### 44.1. Không dùng cùng credential

Nếu attacker có quyền admin production, đừng cấp lại quyền đó vào recovery vault/cluster. Tách recovery principal và incident approval.

### 44.2. Xác định last known good

Một snapshot đã chứa malicious writes hoặc encryption logic sai có thể không phù hợp. Chọn mốc theo audit/evidence; không mặc định bản mới nhất là sạch.

### 44.3. Scan và cô lập

Quy trình có thể bao gồm forensics/malware scanning của hosts/images/config, credential/key rotation, IAM audit và restore vào môi trường sạch; không đơn giản import dữ liệu rồi gắn vào hệ cũ chưa được tin cậy.

### 44.4. Immutable backup là lớp giảm blast radius

Nếu retention/lock có hiệu lực và quyền xóa tách biệt, attacker khó phá bản cũ hơn. Nhưng nếu key material bị xóa hoặc key access bị compromise, recovery vẫn có rủi ro.

### 44.5. Kiểm tra dữ liệu có bị sửa trước incident

Attacker có thể thay đổi business data âm thầm nhiều tuần. Cần nhiều generations of backups, anomaly/audit logs và validation, không chỉ một point gần đây.

### 44.6. Diễn tập quyền truy cập emergency

Nếu bình thường không ai có quyền recovery và break-glass procedure chưa từng thử, RTO có thể bị vi phạm chỉ vì không lấy được keys hoặc không được cấp role đúng lúc.

## 45. Thứ tự phục hồi nhiều dịch vụ và projections

Một workflow commerce có:

~~~text
Order Source NoSQL
Payment Ledger
Inventory Reservation
Outbox / CDC
Search Index
Redis Cache
~~~

### 45.1. Không restore các hệ độc lập rồi bật mọi consumers ngay

Nếu khôi phục Order DB về 09:00 nhưng Payment Ledger còn state 10:00, worker có thể thấy order chưa thanh toán và capture lại. Cần đóng băng hoặc kiểm soát consumers, rồi reconcile.

### 45.2. Phân loại canonical vs derived

Source of truth cho từng fact (order, payment, inventory) phải rõ. Search/Redis projections có thể rebuild sau; application jobs không được tạo side effect mới chỉ vì thấy source stale.

### 45.3. Outbox version và replay watermark

Khôi phục outbox có thể gửi lại events đã được consumer nhận trước đó. Consumers phải idempotent, dùng eventId/version để chống double effects.

### 45.4. Inventory và payment cần đối soát

Không áp một global rollback timestamp tùy tiện lên external providers không cùng transaction scope. Hỏi authoritative provider về captures/refunds/reservations và thực hiện compensation khi cần.

### 45.5. Caches có thể giữ state mới hơn hoặc cũ hơn

Sau cutover, cache entries từ cụm cũ có thể che dữ liệu đã restore hoặc chứa stale user permissions. Invalidate/generation bump theo phạm vi, tránh cache poisoning.

## 46. Recovery khi database đã tiếp tục nhận writes

### 46.1. Bản restore có nhánh lịch sử khác

Nếu production đã nhận writes A, B, C sau snapshot nhưng restore bản t0 rồi tiếp tục nhận D, hai nhánh trạng thái có thể xung đột. Cần một quyết định ownership/merge rõ.

### 46.2. Tách điểm cắt traffic

Tạm dừng writes hoặc chuyển sang queue khi cho phép, đợi active transactions hoàn tất hoặc có outcome reconciliation, rồi chọn checkpoint/cutover có bằng chứng.

### 46.3. Replay có chọn lọc

Chỉ replay những operations hợp lệ với trạng thái mới và có stable operationId/version. Blind replay có thể tạo double charges hoặc duplicated orders.

### 46.4. Đảm bảo idempotency ledger

Nếu source mới thiếu record idempotency của một payment đã capture, request retry có thể tạo duplicate effect. Restore/reconcile ledger theo authoritative facts trước khi mở API.

### 46.5. Source version sau restore

Nếu restored version nhỏ hơn old production version, event consumers hoặc caches có thể bỏ qua updates vì tưởng cũ. Có thể cần generation/epoch mới và quy trình invalidate/rebuild.

## 47. RTO thường bị chi phối bởi băng thông và rebuild

Giả sử có 3 TB dữ liệu cần tải và effective transfer throughput 300 MB/s:

\[
T_\text{transfer}
=\frac{3{,}000{,}000\text{ MB}}{300\text{ MB/s}}
=10{,}000\text{ s}\approx2.78\text{ giờ}.
\]

Đây chỉ tính transfer theo đơn vị decimal, chưa gồm provisioning, index build, shard rebalance, decryption và validation.

### 47.1. Restore performance phải được benchmark

Nếu RTO 60 phút nhưng data transfer riêng đã 2,78 giờ, cần đổi kiến trúc: warm standby/replica, parallel restore, locality, smaller scope hoặc mục tiêu RTO có khả năng đạt.

### 47.2. Effective throughput khác link speed

Network “10 Gbps” không đồng nghĩa restore đạt tốc độ tối đa vì source storage, object APIs, request rate limits, decompression, KMS calls và destination disk đều là bottleneck.

### 47.3. Index rebuild

Một DB có thể restore raw documents nhanh nhưng mất hàng giờ dựng lại index, làm API list/search chưa hoạt động. Thời gian này thuộc business RTO.

### 47.4. Restore theo giai đoạn

Có thể ưu tiên essential tables, recent hot data hoặc critical customers nếu data model/engine hỗ trợ và business cho phép. Tuy nhiên partial readiness phải được nêu rõ; không gọi toàn bộ hệ recovered.

### 47.5. Không bỏ qua cold cache

Ngay khi restore, page/cache working set có thể lạnh; p99 cao và stampede khi traffic mở lại. Warmup có kiểm soát hoặc ramp traffic giúp tránh overload.

## 48. Recovery test cần đo điều kiện xấu, không chỉ lý tưởng

### 48.1. Backup trong cùng Region vs DR Region

Restore gần nguồn thường nhanh hơn restore across Region. Diễn tập với đường network/account thực sự dự kiến dùng lúc disaster.

### 48.2. Encryption key không sẵn có

Nếu backup cần KMS key của Region đang mất, recovery có thể bị chặn. Thử emergency key access/rewrap policy mà không xuất raw key.

### 48.3. Managed service quotas

Tạo table/cluster mới, restore jobs, node capacity, I/O throughput và API rate limits có thể tạo delays. Đừng tính RTO dựa trên lý thuyết copy bytes mà bỏ qua giới hạn provider.

### 48.4. Incident đồng thời với traffic peak

RTO ở giờ thấp tải không phản ánh traffic khi campaign; có thể phải throttle noncritical features và scale read paths trước khi mở toàn bộ.

### 48.5. Restore nhỏ không đại diện restore lớn

Một test 10 GB chạy 3 phút không chứng minh restore 10 TB dưới 50 phút. Cần test ở data scale/thước đo thực tế hoặc một mô hình capacity có validation.

## 49. RPO/RTO là quyết định chi phí và rủi ro

| Nhu cầu | Kiến trúc có thể phù hợp | Trade-off |
|---|---|---|
RTO tính giây khi node hỏng | HA replicas/automatic failover | Không có lịch sử chống DELETE sai |
RPO tính phút khi xóa nhầm | PITR/log archival | Thêm chi phí storage, log completeness |
Phục hồi dữ liệu một tháng trước | Versioned backups, retention nhiều generations | Lưu lâu và khả năng đọc schema/key cũ |
Khôi phục khi admin compromise | Immutable/cross-account backup | Quản lý IAM, keys và break-glass |
RTO rất ngắn khi Region outage | Geo-replication/warm standby | Chi phí vận hành cao, conflict/fencing |
Phục hồi một record | Isolated restore + selective merge | Cần repair logic/validation |

### 49.1. Không có “best backup” chung

Một blog demo chỉ cần backup hằng ngày có thể chấp nhận mất vài giờ. Một order/payment system có thể không. Đặt RPO/RTO theo business impact trước rồi chọn cơ chế.

### 49.2. Data criticality theo loại

Catalog price, user preferences, legal audit logs, inventory reservations và payment ledger có độ quan trọng khác. Không phải mọi table cần cùng lịch, nhưng một workflow có dependencies phải tương thích nhau.

### 49.3. Cost of lost data

Chi phí không chỉ là doanh thu mất: còn thời gian đối soát, vi phạm hợp đồng, audit/regulatory, user trust và manual repair.

### 49.4. Cost of independent isolation

Cross-Region/cross-account copies, immutable retention, recovery drills và keys làm tăng chi phí nhưng có thể giảm tail risk vốn không hiện trong bình quân hằng ngày.

## 50. Những anti-pattern thường gặp

| Anti-pattern | Vì sao nguy hiểm | Thay bằng |
|---|---|---|
| “RF=3 nên không cần backup” | Delete/update nhầm lan tới replicas | PITR và historical backup |
| “Có secondary lag 30s là đủ rollback” | Lag không ổn định, có thể bắt kịp | Mốc snapshot/log nhất quán |
| Snapshot nằm trên cùng disk, không copy đi | Mất disk/cụm là mất ảnh | Independent repository |
| Snapshot cùng tài khoản admin và có thể xóa | Admin compromise phá cả nguồn/backup | Separate roles/account + immutable retention |
| Chỉ giữ một bản gần nhất | Bug được phát hiện trễ | Nhiều generations theo detection window |
| Copy database files đang ghi tùy tiện | Inconsistent blocks/logs | Engine-supported snapshot protocol |
| Dùng CDC/Kafka có retention ngắn làm backup | Thiếu history và snapshot nền | Proper archive/checkpoint |
| “Backup job xanh” nghĩa restore được | Không kiểm tra schema/keys/checksum | Periodic full restore drills |
| PITR chưa bật nhưng assume hỗ trợ | Không có recoverable window | Verify table/cluster settings |
| Giữ incrementals, xóa full base | Chain restore bị gãy | Dependency-aware retention |
| Hủy KEK cũ sau rotation | Backup lịch sử không decrypt được | Key retention/restore tests |
| Restore trực tiếp đè production ngay | Mất writes hợp lệ, khó đảo ngược | Isolated restore + merge/cutover |
| Không tính index rebuild vào RTO | API vẫn chậm/không hoạt động | End-to-end recovery measurement |
| Không restore idempotency/outbox | Duplicate effects sau replay | Business state reconciliation |
| Mở lại workers trước khi reconcile | Charge/ship/replay hai lần | Controlled consumers/egress |
| Không có retention delete plan | Cost/PII retention risk | Governed lifecycle policy |
| Gọi cross-Region replica là immutable backup | Lệnh xóa và cùng IAM vẫn lan/tấn công | Independent historical copy |
| Chỉ đo mean restore time | Worst-case vượt RTO | Drill nhiều scenarios, p95/worst-case |
| Backup chứa raw secrets trong manifest | Dễ leak credential/key | Metadata references only |
| Restore vào test cùng live payment credentials | Gây side effects thật | Isolated account/network/stubs |

## 51. Checklist đánh giá một chiến lược backup

### 51.1. Bối cảnh nghiệp vụ

- Những datasets nào là canonical, những datasets nào rebuildable?
- RPO và RTO cho từng business capability là gì?
- Các failure scenarios gồm node, AZ, Region, DELETE nhầm, ransomware, admin compromise và logical corruption?
- Dữ liệu mới có thể tiếp tục được ghi trong lúc khôi phục không?

### 51.2. Replication và snapshot

- Replication factor, placement, acknowledgment và failover behavior đã hiểu?
- Snapshot mechanism có consistency semantics chính xác?
- Đã biết snapshots/logs nằm ở đâu và có bị cùng quyền xóa không?
- Các tables/shards/collections có được chụp cùng mốc nhất quán?

### 51.3. Backup độc lập

- Có cross-account/cross-Region theo threat model?
- Có immutable retention/versioning và quyền xóa tách biệt?
- Có encryption, KMS key retention, recovery credentials và audit?
- Retention giữ được điểm trước khi lỗi được phát hiện muộn?
- Full/incremental/log dependencies có được quản lý?

### 51.4. Phục hồi

- Có runbook dựng cluster/table mới, không phụ thuộc source cũ?
- Có kế hoạch lấy schema, indexes, roles, configs, keys và data logs?
- Có cô lập payment/notification/webhook consumers?
- Có kiểm tra counts, sample hashes, business invariants, permissions?
- Có thử actual RPO/RTO và key/cross-version restore?
- Có người chịu trách nhiệm, break-glass và diễn tập gần đây?

### 51.5. Quan sát

- Latest verified recoverable point và backup age được đo?
- Job failures/integrity/key failures có alert?
- Test restore được ghi lịch và lưu evidence?
- Backup cost/storage growth và retention được quản trị?

## 52. Bài tập 1 — replication có phải backup không?

Một MongoDB replica set có ba members ở ba AZ. Admin nhầm lẫn chạy DELETE trên toàn bộ orders của tenant T17; lệnh commit và được replicate.

1. Hãy vẽ timeline mutation từ primary sang secondaries.
2. Vì sao hai secondaries không phải “bản backup chưa xóa”?
3. Nếu secondary đang lag 2 giây, có được xây chiến lược rollback bằng cách đợi lấy dữ liệu từ nó không?
4. Cần những restore points nào để lấy lại orders trước DELETE?
5. Đề xuất quyền IAM/DB giúp hạn chế thao tác xóa hàng loạt.

## 53. Bài tập 2 — phân biệt ba cơ chế

Phân loại:

~~~text
A. DynamoDB Global Tables ở hai Regions.
B. MongoDB storage snapshot mỗi ngày, giữ 30 bản.
C. Cassandra SSTables snapshot trên cùng disks.
D. Copy đã verify sang object store ở account độc lập có immutable retention.
E. Redis replica được cập nhật liên tục.
F. PITR với base backup và change logs đã archive đầy đủ.
~~~

1. Cơ chế nào chủ yếu phục vụ HA?
2. Cơ chế nào giữ historical restore point?
3. Cơ chế nào có failure-domain independence rõ hơn?
4. B và C cần thêm gì để giảm common failure domain?
5. F có cần key retention và restore test không?

## 54. Bài tập 3 — RPO từ lịch snapshot

Một hệ chỉ có snapshot mỗi 6 giờ:

~~~text
00:00 snapshot
06:00 snapshot
12:00 snapshot
18:00 snapshot
14:35 incident
~~~

1. Restore point gần nhất là giờ nào?
2. Có nguy cơ mất bao nhiêu thời gian thay đổi?
3. Worst-case RPO theo lịch này gần bao nhiêu nếu không có log archival?
4. Nếu business RPO=5 phút, lịch này có đủ không?
5. Đề xuất backup/PITR thay thế và cách đo actual recoverable watermark.

## 55. Bài tập 4 — RPO với log lag

Một hệ có base snapshot lúc 12:00 và log archive từ 12:00 tới 14:33, trong khi incident lúc 14:35. Log archive được xác minh không gap.

1. Mốc recoverable mới nhất là gì nếu engine hỗ trợ replay?
2. Data-loss window khoảng bao nhiêu?
3. Nếu log sequence từ 14:10 đến 14:12 bị thiếu thì kết luận thay đổi thế nào?
4. Nếu một lệnh DELETE sai xảy ra lúc 14:34, nên phục hồi tới mốc nào?
5. Vì sao wall-clock time chưa đủ để xác nhận đúng transaction boundary?

## 56. Bài tập 5 — RTO tính đủ quy trình

Disaster recovery mất:

~~~text
Detection/decision: 12 minutes
Provisioning:       18 minutes
Transfer:           70 minutes
Log replay:         25 minutes
Index rebuild:      35 minutes
Validation:         20 minutes
Cutover:            10 minutes
~~~

1. Tính RTO nếu chạy tuần tự.
2. Nếu một số bước có thể chạy song song, làm sao tìm critical path?
3. Với mục tiêu RTO=90 phút, kế hoạch hiện tại có đạt không?
4. Nếu transfer là bottleneck, đưa ra các phương án warm standby/parallel transfer.
5. Vì sao API chỉ ping database thành công trước validation chưa tính là recovered?

## 57. Bài tập 6 — independent backup và quyền xóa

Source NoSQL và mọi backups đều nằm trong một cloud account. Production admin role có quyền xóa cluster, snapshots và bucket objects.

1. Mất một disk khác với compromise role này như thế nào?
2. Bốn biện pháp nào giảm nguy cơ cùng nguồn và backup bị phá?
3. Phân tách backup writer/recovery reader/deletion admin ra sao?
4. Immutable retention có cần test hành vi xóa theo policy không?
5. Nếu backup encryption key vẫn thuộc đúng tài khoản bị chiếm, còn rủi ro gì?

## 58. Bài tập 7 — snapshot consistency across shards

Một sharded NoSQL có ba shards, snapshot lần lượt lúc 10:00:00, 10:00:20 và 10:00:45. Một transaction chuyển value giữa shards lúc 10:00:10.

1. Vì sao bộ files snapshot có thể không biểu diễn một consistent cut?
2. Khi nào snapshot cần engine-aware coordination?
3. Write barrier/quiesce có giúp không, và đánh đổi availability gì?
4. Chỉ đồng bộ NTP có đủ không?
5. Đề xuất test để phát hiện trạng thái “debit có nhưng credit không”.

## 59. Bài tập 8 — incremental chain bị hỏng

Một backup chain:

~~~text
Full F0 -> Incremental I1 -> Incremental I2 -> Incremental I3
~~~

I2 bị xóa do lifecycle policy sai, còn F0/I1/I3.

1. Có thể chắc chắn restore I3 không?
2. Vì sao chỉ kiểm tra I3 tồn tại là không đủ?
3. Retention policy cần hiểu dependencies nào?
4. Đề xuất integrity/catalog checks trước khi dọn cũ.
5. Một full base mới độc lập giúp giảm rủi ro gì?

## 60. Bài tập 9 — MongoDB logical dump

Một job mongodump đọc 10 triệu documents trong 45 phút khi application vẫn ghi orders.

1. Vì sao dump có thể không phản ánh một thời điểm duy nhất nếu thiếu cơ chế consistency?
2. Mongodump và storage/database snapshot khác nhau thế nào?
3. Oplog hỗ trợ những workflow consistency nào trong phạm vi engine cho phép?
4. Vì sao một option oplog của replica set không được suy là giải pháp chung cho sharded cluster?
5. Sau restore cần kiểm tra indexes, roles, schema và application query behavior ra sao?

## 61. Bài tập 10 — DynamoDB Global Tables và PITR

Một table có Global Tables ở Region A/B. Admin xóa nhầm item ở A, delete lan tới B.

1. Global Tables đã bảo vệ node/Region availability nhưng chưa giải quyết lỗi nào?
2. PITR khác Global Tables thế nào?
3. Nếu restore tới một table mới, Java application cần đổi cấu hình/quyền nào?
4. Streams có thể được dùng thay PITR vô hạn không?
5. Nếu cần chịu account compromise, đề xuất chiến lược backup isolation.
6. Sau restore cần kiểm tra GSI, TTL, streams, capacity và IAM như thế nào?

## 62. Bài tập 11 — Cassandra snapshot trên cùng node

Một cụm Cassandra có RF=3, dùng nodetool snapshot trên từng node và giữ SSTable snapshot files cùng local disk.

1. Vì sao RF=3 không giải quyết xóa nhầm?
2. Vì sao snapshots trên local disks chưa độc lập với node failure?
3. Cần inventory schema, token ranges, version và SSTable files thế nào?
4. Đề xuất copy/verify tới object storage tách quyền và retention.
5. Nếu muốn PITR từ commitlog, cần thêm điều kiện log archival/gap detection nào?
6. Vì sao restore từ các nodes tại thời điểm tùy ý có thể không consistent?

## 63. Bài tập 12 — Redis replica, RDB và AOF

Một Redis service chứa session keys và một số counters quan trọng. Có một replica và AOF trên primary, nhưng chưa copy AOF/RDB ra ngoài.

1. Replica xử lý node failure nhưng có giữ lịch sử trước FLUSHALL sai không?
2. AOF có thể chứa lệnh DEL/FLUSHALL không?
3. RDB có thể giúp khôi phục tới một mốc cũ trong điều kiện nào?
4. Nếu disk node bị hỏng, AOF local còn không?
5. Nếu Redis chỉ là cache có thể rebuild, backup requirement khác trường hợp counters authoritative thế nào?
6. Kế hoạch bảo vệ sensitive session tokens trong RDB/AOF?

## 64. Bài tập 13 — OpenSearch snapshot vs shard replicas

Một search index chứa 300 triệu documents, ba replica shards và snapshot repository cùng account. Reindex script mới vô tình loại 30% records, các replicas đều theo index mới.

1. Replicas còn giúp lấy index cũ không?
2. Nên chọn snapshot nào để tránh reindex lỗi?
3. Nếu canonical source MongoDB vẫn đúng, có thể rebuild index không? RTO trade-off gì?
4. Snapshot API repository cần quyền và retention gì?
5. Sau restore nên kiểm tra mappings, aliases, analyzers, index templates và query result counts thế nào?

## 65. Bài tập 14 — outbox/Kafka không phải backup vô hạn

Một service giữ Kafka events 7 ngày; Orders được tạo từ 18 tháng trước. Team muốn rebuild toàn bộ read model bằng cách replay Kafka hiện tại.

1. Vì sao retention 7 ngày có thể không đủ?
2. Cần một base snapshot hoặc archive events như thế nào?
3. Replayed events có thể trùng hoặc đến sai thứ tự ra sao?
4. Khi một event tạo payment side effect, có được replay vào payment provider không?
5. Làm sao chứng minh event archive độc lập với source account và còn đọc được schema cũ?

## 66. Bài tập 15 — restore một record mà không rollback cả hệ

Lúc 09:00 có snapshot. Lúc 10:00 user xóa nhầm O101. Từ 10:00 tới 10:10 hệ nhận 2.000 writes hợp lệ cho các orders khác.

1. Nếu full restore về 09:00, những writes nào sẽ mất?
2. Có cách nào restore snapshot vào cluster cô lập rồi chỉ trích O101?
3. Nếu O101 đã được recreated ở current source, repair phải kiểm tra điều kiện gì?
4. Thiết kế operationId/expectedVersion cho repair command.
5. Khi search/cache còn negative O101, cần bước nào sau repair?
6. Audit trail nào phải được giữ?

## 67. Bài tập 16 — encryption key bị mất

Một bản backup NoSQL đã mã hóa được giữ trong vault 1 năm. Sau khi rotate KEK, team xóa mọi key versions cũ. Restore từ snapshot 6 tháng trước báo lỗi Decrypt.

1. Backup files có còn toàn vẹn không?
2. Vì sao toàn vẹn bytes không đủ để có khả năng restore?
3. Cần key retention và restore drills như thế nào?
4. Nếu key material bị destroy không có recovery path, có thể giải mã backup cũ không?
5. Đề xuất policy liên kết backup retention với key lifecycle.
6. Nếu backup copy cross-account, quyền KMS/Region cần xét gì?

## 68. Bài tập 17 — sai lầm trong dashboard

Một dashboard ghi:

~~~text
Last backup job: SUCCESS, 2 minutes ago.
Last validated restore point: 3 hours ago.
Business RPO: 15 minutes.
Last restore drill: 11 months ago.
~~~

1. Từ số liệu trên có thể tuyên bố RPO đạt 15 phút không?
2. Vì sao job success không tự làm restore point mới verified?
3. Alert nào cần phát ngay?
4. Lên lịch restore drill cần cân nhắc những gì?
5. Metrics nào chứng minh backup immutable lock đã áp dụng?

## 69. Bài tập 18 — RTO với 3 TB

Bạn có 3 TB dữ liệu (theo decimal), tốc độ tải thực 300 MB/s, ngoài ra index rebuild cần 1,5 giờ và validation 30 phút.

1. Tính transfer time.
2. Nếu các bước tuần tự, RTO tối thiểu từ những phần này là bao nhiêu?
3. Nếu business RTO=2 giờ, kế hoạch hiện tại có khả thi không?
4. Thay đổi kiến trúc nào giúp giảm RTO: warm standby, partial restore, parallelism, colocated backup?
5. Vì sao network 10 Gbps không đảm bảo đạt tốc độ restore tương ứng?

## 70. Bài tập 19 — thiết kế backup plan nhiều lớp

Một SaaS multi-tenant dùng:

~~~text
MongoDB: canonical orders
DynamoDB: idempotency ledger
Redis: cache and sessions
OpenSearch: catalog search
Kafka: outbox/event stream
KMS: application encryption keys
~~~

1. Phân loại canonical vs derived data.
2. Viết RPO/RTO riêng cho order create, payment idempotency, search và sessions.
3. Chọn replication/HA, snapshots, PITR, immutable backup theo mỗi service.
4. Thiết kế backup IAM/account/Region isolation.
5. Thiết kế thứ tự restore/reconcile side effects.
6. Đề xuất cách tránh gửi emails/charges khi chạy isolated DR test.
7. Viết verification checklist về counts, versions, indexes, keys, streams, ACL.
8. Đề xuất metrics và drill frequency cho từng lớp.

## 71. Bài tập 20 — diễn tập xóa nhầm và compromise cùng lúc

Giả sử:

~~~text
09:00: Backup độc lập tốt gần nhất.
09:40: Admin credential bị lộ.
09:45: Attacker xóa nhiều records và cố xóa snapshots.
09:47: Deletes đã replicate sang các AZ.
10:00: Security phát hiện.
10:05: Production vẫn có một số writes hợp lệ.
~~~

Yêu cầu:

1. Định nghĩa ngay failure domains bị ảnh hưởng.
2. Giải thích vì sao replicas không đủ.
3. Kiểm tra backup repository có thực sự tách credentials/immutable không.
4. Chọn last known good restore point và giới hạn dữ liệu có thể mất.
5. Thiết kế cách ngăn attacker tiếp tục ảnh hưởng recovery account.
6. Restore vào môi trường cô lập và xác minh dữ liệu không bị sửa trước sự cố.
7. Đối soát writes hợp lệ từ 09:00 tới 10:05 mà không reapply các mutation ác ý.
8. Reconcile downstream orders/payments/notifications.
9. Thiết kế canary/cutover/fencing để không tạo split brain.
10. Đo RPO/RTO actual và lập post-incident report.

## 72. Tổng kết: replication để tiếp tục chạy, snapshot để có mốc, backup độc lập để còn đường quay lại

Ba cơ chế có thể cùng xuất hiện trong một hệ NoSQL nhưng không thể đánh đồng:

1. **Replication phục vụ availability/durability theo protocol.** Nó không giữ quá khứ theo mặc định và thường lan truyền DELETE/update nhầm cùng với writes hợp lệ.
2. **Snapshot giữ trạng thái ở một mốc.** Giá trị phục hồi phụ thuộc consistency, checkpoint, storage và khả năng đọc snapshot bằng công cụ được hỗ trợ.
3. **Bản backup độc lập bảo vệ khỏi lỗi tương quan.** Nên tách quyền, account/Region/storage theo threat model, có retention/immutability, encryption và restore test.
4. **PITR cần base data và change history đầy đủ.** Oplog, WAL, commitlog, CDC hay AOF không tự là independent, indefinite PITR archive.
5. **RPO đo độ mới của restore point; RTO đo thời gian khôi phục được nghiệp vụ.** Chúng không được suy chỉ từ frequency snapshot, số replicas hoặc tốc độ download file.
6. **Consistency của snapshot phải phù hợp topology.** Ghép files từ nhiều shards/nodes/time points tùy ý có thể tạo state chưa từng hợp lệ.
7. **Retention phải giữ nhiều thế hệ.** Một bản mới nhất có thể đã chứa corruption bị phát hiện muộn; incremental chains cần đầy đủ dependencies.
8. **Backup không dùng được nếu thiếu keys/schema/tool compatibility.** Giữ KMS references, data key versions, index metadata, recovery identities và test restore từ backups lịch sử.
9. **Restore isolated trước khi cutover giảm rủi ro.** Có thể recover selective records mà không rollback hàng nghìn writes hợp lệ sau snapshot.
10. **Một hệ nhiều services cần business reconciliation.** Khôi phục Order DB không tự hoàn tác Payment capture, Inventory reserve, emails hay outbox events.
11. **NoSQL engines khác nhau.** MongoDB replica set và oplog, DynamoDB Global Tables/PITR, Cassandra SSTable snapshots, Redis RDB/AOF và search repository snapshots có các contract riêng.
12. **Quan sát mốc phục hồi thực.** Backup job SUCCESS không chứng minh latest recoverable point đã tăng; cần integrity checks, key access và restore drills.
13. **Backup security là một phần của data security.** Immutable retention, IAM separation, vault policies, audit và privacy/retention controls giảm blast radius.
14. **Khôi phục phải được diễn tập ở quy mô phù hợp.** RTO có thể bị chi phối bởi data volume, network, index rebuild, cold cache và thời gian approval.
15. **Mục tiêu cuối là business correctness.** Đếm records, checksum, tenant isolation, idempotency và reconciliation quan trọng không kém khả năng khởi động cluster.

Khi đánh giá bất kỳ tuyên bố “chúng ta đã có ba bản dữ liệu”, hãy hỏi:

> **“Nếu một lệnh xóa nhầm hoặc một tài khoản admin bị chiếm khiến mọi replica cùng mất dữ liệu ngay bây giờ, ta có thể lấy trạng thái tốt trước lỗi từ đâu, bằng quyền/khóa nào, và đã chứng minh được việc khôi phục đúng trong RPO/RTO hay chưa?”**










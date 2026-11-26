# Sao lưu, khôi phục và kiểm tra khả năng đọc lại dữ liệu ứng dụng

Một bản sao lưu Couchbase có trạng thái **SUCCESS** chưa chứng minh ứng dụng Spring Data Couchbase có thể chạy lại sau sự cố. Backup có thể chứa dữ liệu KV, trong khi môi trường khôi phục lại thiếu bucket/scope/collection, GSI, quyền RBAC, khóa giải mã hoặc phiên bản converter phù hợp. Document vẫn tồn tại nhưng `repository.findById(...)` trả lỗi hoặc không dựng được entity; một đơn hàng và outbox event có thể không ở cùng mốc; session hết TTL có thể không còn khi người dùng thử đọc.

Bài thuộc chương **Quan sát và vận hành** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase với document mapping, Repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để bảo đảm hiệu năng, nhất quán và khả năng vận hành.

> **Thông điệp chính:** **Backup thành công ≠ restore thành công ≠ ứng dụng đọc được đúng dữ liệu ≠ nghiệp vụ đã phục hồi.** Một kế hoạch khả dụng phải xác định **RPO/RTO**, phạm vi dữ liệu và cấu hình cần bảo vệ, thử khôi phục vào môi trường cô lập, chạy **kiểm thử đọc lại theo hợp đồng Spring Data/SDK/SQL++**, rồi đối soát trạng thái nghiệp vụ trước khi mở traffic.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt RPO, RTO, backup, restore, replication/XDCR, high availability và business reconciliation.
2. Lập danh mục backup theo **bucket/scope/collection**, document body/metadata, indexes và cấu hình ngoài Couchbase.
3. Hiểu `cbbackupmgr`, archive/repository, backup đầu tiên và các bản incremental; phân biệt khả năng/giới hạn của Capella managed backups.
4. Lựa chọn lịch backup, retention, off-site storage, encryption, kiểm tra integrity và chiến lược restore thử.
5. Không hiểu nhầm backup là một snapshot ACID tại cùng một thời điểm trên mọi documents.
6. Biết phục hồi vào cluster/bucket cô lập, xử lý mapping, option `--start`/`--end` và xung đột với dữ liệu đích.
7. Giải thích tác động của document expiration, `maxExpiry`, CAS và Spring `@Version` sau restore.
8. Kiểm tra entity mapping `@Field`, `_class`, custom conversions và application schema version.
9. Kiểm tra **đọc theo KV lẫn SQL++**; phục hồi/BUILD indexes và xem xét Search/Analytics/Eventing theo khả năng.
10. Xác minh dữ liệu nhạy cảm, khóa giải mã, secrets, credentials và quyền RBAC ở môi trường restore.
11. Thiết kế phép thử **canary/sentinel**, checksums, invariants, counts, business reconciliation và fail-closed acceptance.
12. Xử lý outbox/inbox, broker replay, payment provider và idempotency sau khi rollback dữ liệu về một mốc cũ.
13. Viết runbook, drill có fault injection, SLO và checklist bàn giao vận hành.

## 2. Bài toán xuyên suốt: cửa hàng Spring Data Couchbase

Ứng dụng giả định quản lý:

~~~text
Couchbase Server/Capella cluster
└── Bucket: shop
    ├── Scope: catalog
    │   ├── Collection: products
    │   └── Collection: categories
    ├── Scope: sales
    │   ├── Collection: orders
    │   ├── Collection: outbox_events
    │   └── Collection: inbox_events
    └── Scope: auth
        └── Collection: sessions
~~~

- `products`: có `@Field`, `@Version`, custom conversion và Search index.
- `orders`: đơn hàng, số tiền theo minor units, trạng thái và business version.
- `outbox_events`: sự kiện bền cần publish ít nhất một lần khi có thay đổi Order.
- `inbox_events`: receipt dùng chống xử lý message trùng.
- `sessions`: document có expiry/TTL ngắn, không được hồi sinh trái chính sách.
- Query/GSI: phục vụ tìm Order theo tenant, ngày và trạng thái.
- Search/Analytics: có thể có dữ liệu/chỉ mục suy ra từ KV.

Một bộ backup chỉ chứa body của `orders` nhưng thiếu chỉ mục, khóa giải mã hoặc receipt/inbox vẫn có thể trông “đủ dữ liệu” ở cấp file, nhưng **chưa đáp ứng điều kiện ứng dụng phục hồi**.

## 3. Backup, replication và khả năng phục hồi là ba việc khác nhau

| Cơ chế | Giải quyết | Không mặc nhiên giải quyết |
| --- | --- | --- |
| Data replicas trong cluster | Node failover, tính sẵn sàng nội bộ | Xóa nhầm hoặc dữ liệu hỏng đã replicate |
| XDCR/replication sang cluster khác | DR, gần thời gian thực theo thiết kế | Khả năng rollback về mốc trước thao tác sai |
| Backup full/incremental | Bản sao phục hồi tới các mốc đã lưu | Chuyển traffic tự động, ứng dụng đọc đúng |
| Restore | Đưa dữ liệu/cấu hình được hỗ trợ về target | Tự rebuild mọi index, secrets và external state |
| Spring Data readback test | Xác minh mapping và truy vấn phục hồi | Bảo đảm mọi business invariant nếu test quá ít |
| Reconciliation | So DB state với event log/payment/ledger | Thay transaction ACID ban đầu |

Replication có thể nhân bản cả xóa nhầm hoặc corruption. Backup cần retention và mốc lưu đủ cũ để phục hồi. DR cần **diễn tập** chứ không chỉ một sơ đồ kiến trúc.

## 4. RPO và RTO không phải hai cách gọi cùng một thời gian

**RPO — Recovery Point Objective**: khoảng dữ liệu mới nhất có thể mất mà nghiệp vụ chấp nhận, đo bằng thời gian từ điểm sự cố về tới mốc có thể khôi phục.

**RTO — Recovery Time Objective**: thời gian tối đa chấp nhận để dịch vụ đạt mức hoạt động đã định sau sự cố.

Ví dụ:

~~~text
09:00  Backup thành công
09:15  Incremental backup
09:30  Incremental backup
09:42  Cluster gặp sự cố
10:10  Restore và application readback hoàn tất
10:20  Mở traffic trở lại sau đối soát
~~~

Nếu restore được tới khoảng 09:30, **khoảng mất dữ liệu có thể là 12 phút**. Nếu phát hiện sự cố lúc 09:42 và mở traffic lúc 10:20, **thời gian khôi phục vận hành là 38 phút**. Đây là ví dụ; mốc backup thực, transaction/connector consistency và thời điểm có thể truy cập phải kiểm chứng.

**Không nói “RPO 15 phút” chỉ vì cron chạy mỗi 15 phút**: nếu backup thất bại hoặc archive không khả dụng, RPO đạt được có thể lớn hơn. **Không nói “RTO 30 phút” chỉ dựa thời gian copy data**: còn tạo cluster, build index, deploy app, test và cutover.

## 5. Định nghĩa điều kiện hoàn tất phục hồi theo ứng dụng

Một recovery acceptance contract cho cửa hàng có thể là:

1. Cluster và các bucket/scope/collection bắt buộc tồn tại.
2. Dữ liệu KV của collections trọng yếu có thể đọc theo document key.
3. Spring Repository đọc/deserialize được entity; field mapping, enum, date, money đúng.
4. SQL++ queries quan trọng trả về đúng shape và index đã ở trạng thái phục vụ.
5. Index/Search/Analytics/derived state có lịch rebuild/freshness đáp ứng use case.
6. `tenantId`/keyspace authorization không cho lộ dữ liệu chéo tenant.
7. Các invoices/payment outcomes được đối soát với provider; không ghi đè mới bằng bản cũ.
8. Outbox/inbox replay không tạo double charge, duplicate invoice hay mất event.
9. TTL cho session, token, cache đúng; không hồi sinh dữ liệu đã hết hạn trái quy định.
10. Secrets/keys/RBAC/TLS phục hồi theo quy trình riêng; audit được bật.
11. Lỗi/timeout dưới ngưỡng đã thống nhất, readback/smoke tests pass.
12. SRE/owner xác nhận thời điểm mở traffic; có rollback/cutover plan.

Đây là mức hoàn tất **business recovery**, không chỉ exit code của công cụ backup.

## 6. Phạm vi cần sao lưu: đừng chỉ nghĩ tới documents

| Thành phần | Ví dụ | Lưu ý phục hồi |
| --- | --- | --- |
| KV data | Body JSON và metadata document | TTL/expiry, deletion/tombstone và schema |
| Bucket/scope/collection | `shop.sales.orders` | Names, IDs, collection maxTTL/config |
| GSI definitions | Index tenant+status+createdAt | Có thể phải BUILD lại sau restore |
| Search definitions | FTS index, aliases | Phải kiểm tra build/catch-up |
| Analytics metadata | Datasets/indexes/links theo khả năng tool | Không mặc định toàn bộ analytics derived data |
| Eventing definitions | Functions, settings theo backup configuration | Verify trạng thái deploy/binding và side effects |
| Query metadata | Functions/synonyms/contexts tùy version | Không đồng nhất với KV data |
| RBAC/users | Accounts và roles nếu được sao lưu/restore hỗ trợ | Không assume Admin/Secrets đầy đủ |
| External secrets | DB passwords, TLS private keys, KMS/crypto keys | Nằm ngoài backup Couchbase thông thường |
| Application versions | JAR image, Spring Data converter, migrations | Pin deployment tương thích schema |
| Broker/ledger | Kafka offsets, payment capture, invoices khác hệ | Phải backup/đối soát riêng |
| Infrastructure | DNS, networking, certs, IAM, cluster topology | Không tự được tái tạo khi restore bucket |

**Chú ý:** Các nhóm metadata mà `cbbackupmgr` hỗ trợ phụ thuộc Server/tool version, edition và backup repository config. Cả khi index definition được backup, **trạng thái build/sẵn sàng index không mặc nhiên được sao chép nguyên vẹn**.

## 7. Hai hệ điều hành backup: self-managed và Capella

### Couchbase Server tự quản lý

Có thể dùng `cbbackupmgr` (cùng bản công cụ phù hợp Server) để quản lý archive/repository và sao lưu đầy đủ/tăng dần. Tài liệu Server hiện hành ghi nhận công cụ hiện diện cho **Community và Enterprise Edition**, nhưng **một số tùy chọn** như lọc cấp scope/collection hoặc native cloud integration được giới hạn theo edition/version. Đừng suy rằng mọi flag áp dụng ở mọi môi trường.

### Couchbase Capella

Capella có **managed on-demand/scheduled bucket backups** và các tùy chọn cluster backup theo sản phẩm/gói. Tài liệu Capella cho biết bucket backup **không phải snapshot point-in-time nhất quán toàn cụm**: mỗi item được sao lưu nhất quán, nhưng không cam kết mọi item cùng một mốc. Cluster networking/configuration cũng không nằm trọn trong bucket backup.

| Tiêu chí | Server `cbbackupmgr` | Capella managed backup |
| --- | --- | --- |
| Khởi tạo | CLI/automation riêng | Capella UI/API/workflow được hỗ trợ |
| Full/incremental | Backup đầu full, tiếp theo thường incremental | Full + incremental theo lịch/cycle |
| Chọn scope | Repository config/flag, tùy edition | Scope theo giao diện và loại backup |
| Quyền quản trị | RBAC/backup credentials | Capella roles/cluster access |
| Kiểm soát storage | Archive local/object store nếu hỗ trợ | Capella quản lý theo retention/billing |
| Restore kiểm thử | Cluster/bucket đích cô lập do team chuẩn bị | Cơ chế restore/clone theo khả năng Capella |
| Kiểm thử ứng dụng | **Bắt buộc** | **Bắt buộc** |

Không đem một lệnh `cbbackupmgr` cho self-managed áp dụng máy móc lên Capella: restore Capella có các `--capella`/service restrictions và credentials tương ứng.

## 8. Đặc điểm của `cbbackupmgr`

Khái niệm:

~~~text
Backup archive /data/couchbase-backups
  ├── repository shop-prod
  │   ├── configuration
  │   ├── first full backup (base)
  │   ├── incremental backup 1
  │   ├── incremental backup 2
  │   └── ...
  └── repository another-cluster
~~~

Theo tài liệu:

- Trước khi chạy `backup` cần tạo **repository** bằng `config`.
- Backup đầu tiên sao lưu dữ liệu đầy đủ theo repository config.
- Các lần sau thường incremental dựa trên backup trước.
- Archive/repository phải được quản lý bằng **cbbackupmgr**, không tự chỉnh/xóa files trong cấu trúc nội bộ.
- **Không cho nhiều clients đồng thời thao tác trên cùng một archive** vì có nguy cơ corrupt archive.
- Backup có thể partial/fail; `--resume`/`--purge` có semantics riêng cho backup.
- Backup khi cluster rebalance vẫn có thể chạy nhưng tăng áp lực tài nguyên.
- Tool version phải tương thích Server version/backup format.

Một repository được cấu hình scope quá hẹp sẽ tạo các bản backup “thành công” mà vẫn **không có collection nghiệp vụ quan trọng**.

## 9. Khởi tạo repository có phạm vi rõ

Trên môi trường quản trị **được phép** và đã chuẩn bị archive location:

~~~bash
cbbackupmgr config \
  --archive /data/couchbase-backups \
  --repo shop-prod
~~~

Ví dụ này dùng default backup configuration; **không phải lệnh để chạy trên production từ bài học**. Trước khi thực thi cần biết:

1. Archive directory phải hợp lệ/không có dữ liệu tool khác.
2. Quyền filesystem/storage đủ, backup storage có quota.
3. Có đúng source cluster và backup repository strategy.
4. Có plan bảo vệ archive khỏi xóa/ransomware, có off-site copy.
5. Có pin tool/Server versions tương thích.
6. Có quyền backup và secret management an toàn.
7. Có bản ghi inventory: bao gồm những buckets/scopes/collections nào?
8. Có lựa chọn mã hóa repository theo tool/version/edition và quản lý keys.

Nếu muốn lọc dữ liệu bằng `--include-data`, kiểm tra khả năng cấp scope/collection ở edition/version và không làm mất các collection quan trọng.

## 10. Thực hiện backup incremental có giám sát

Ví dụ syntax:

~~~bash
cbbackupmgr backup \
  --archive /data/couchbase-backups \
  --repo shop-prod \
  --cluster couchbase://cb-node-a.internal \
  --username backup_operator
~~~

Không truyền password dạng literal trên command line trong ví dụ; CLI có thể prompt theo authentication mode. Trong CI, dùng cơ chế secret injection an toàn, không log args/environment chứa credentials.

Khi chạy:

- Theo dõi exit status, progress, danh sách bucket và **partial backup flags**.
- Xem throughput/data transfer, elapsed, storage growth, retry/failure.
- Không cho concurrent jobs cùng archive/repository khi tool không hỗ trợ.
- Cảnh báo nếu backup mới nhất quá tuổi RPO, không chỉ nếu job gần nhất “đã chạy”.
- Thống nhất lịch full/incremental và retention để không thiếu dependency chain.
- Theo dõi node rebalance, failover, backup client/network pressure.
- Không xóa/merge incremental chain bằng thao tác filesystem thủ công.
- Sau job, dùng `cbbackupmgr info` để kiểm tra backup có trong repository.

`cbbackupmgr` là **CLI vận hành**, không phải API Java gọi trong mỗi HTTP request của Spring.

## 11. Kiểm tra archive inventory bằng `cbbackupmgr info`

~~~bash
cbbackupmgr info \
  --archive /data/couchbase-backups \
  --repo shop-prod
~~~

Nên ghi lại cho mỗi recovery point:

| Field kiểm tra | Vì sao quan trọng |
| --- | --- |
| Backup identifier/time | Có mốc khôi phục nào và tuổi của nó? |
| Result complete/partial | Backup partial có thể thiếu tài liệu |
| Included buckets/collections | Scope được bảo vệ có đúng không? |
| Backup chain dependency | Có đủ full+incremental để restore? |
| Stored size/data volume | Có bất thường nhỏ đột ngột? |
| Encryption/key access | Disaster recovery có giải mã archive được không? |
| Tool version/Server version | Có restore tương thích được không? |
| Storage object/version/checksum | Phát hiện chuyển/đọc sai bytes |
| Retention/deletion date | Có bị purge trước hạn pháp lý/SLO không? |

`info` xác nhận cấu trúc metadata archive; **không phải một integration test bảo đảm Spring Data sẽ đọc được từng document**.

## 12. Full và incremental ảnh hưởng RPO/RTO khác nhau

| Lựa chọn | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Full backup thường xuyên | Ít bước dependency để restore | Chi phí CPU/network/storage cao |
| Full + incremental ngắn | RPO tốt hơn và lưu tiết kiệm | Restore phải xử lý chain, quản lý retention |
| Archive off-site/object store | Giảm rủi ro mất cả primary và backup | Transfer latency/egress/access |
| Snapshot storage ở hạ tầng | Có thể nhanh ở một số thiết kế | Phải kiểm chứng nhất quán của dịch vụ phân tán |
| XDCR + backups | DR gần thời gian thực và rollback point | Chi phí/độ phức tạp tăng, cần reconcile |

RTO phải được **đo từ drill thực tế với dữ liệu tương đương production**, không ngoại suy tuyến tính từ 1.000 test documents.

## 13. Backup không phải transaction snapshot của toàn ứng dụng

Trong một lần backup đang chạy, một Order và một outbox event có thể được chụp ở những thời điểm không trùng nhau nếu công cụ không cung cấp snapshot đồng nhất đa document.

Ví dụ:

~~~text
T0  Backup đọc Order trạng thái PENDING
T1  Business transaction đổi Order=PAID, tạo outbox OrderPaid
T2  Backup đọc outbox OrderPaid
T3  Backup hoàn tất
~~~

Bản restore **có thể chứa Order=PENDING cùng outbox OrderPaid** do tính nhất quán tại thời điểm quét không đồng nhất theo document — dù transaction lúc T1 trên live cluster là atomic. Không kết luận backup đã làm sai transaction; đó là **phạm vi consistency của quy trình backup**.

Cách giảm rủi ro:

1. Đọc tài liệu consistency của công cụ/plan cụ thể.
2. Với hệ thống cần cross-document snapshot, xem xét quiesce/freeze writes hoặc các cơ chế recovery được hỗ trợ.
3. Dùng business event/sequence/checkpoint và reconciliation sau restore.
4. Không replay external side effects trước khi xác minh state/inbox.
5. Với ledger quan trọng, giữ một external source-of-truth/audit evidence độc lập.
6. Thiết kế restore/cutover gate kiểm tra **invariants liên quan nhiều documents**.

**Một backup thành công vẫn có thể cần business reconciliation.**

## 14. Định nghĩa nguồn sự thật và mức nhất quán chấp nhận được

Phân loại dữ liệu:

- **Orders/payments:** thường cần xác minh với payment provider, invoice ledger hoặc audit trail.
- **Products/catalog:** có thể cho phép lấy lại phiên bản cũ hơn trong giới hạn RPO; phải cảnh báo giá tồn kho thay đổi.
- **Sessions/tokens:** bảo mật có thể đòi không khôi phục một token đã bị thu hồi; cân nhắc xóa toàn bộ sessions khi DR hoặc revoke theo policy.
- **Outbox/inbox:** cần giữ event identity và replay boundaries để không gửi/áp dụng side effect hai lần.
- **Cache:** có thể xóa và rebuild nếu nguồn authoritative khác.
- **Search/Analytics:** có thể rebuild sau restore, nhưng cần biết thời gian/chi phí và freshness SLA.

Một chính sách tổng quát “restore hết và mở traffic” là quá thô. Xác định **business source-of-truth** cho mỗi collection.

## 15. Mã hóa backup, quyền truy cập và tách kho

Backup của `orders`/`products` có thể chứa dữ liệu khách hàng, giá vốn, token hoặc thông tin nội bộ. Người có quyền đọc archive có thể nhìn thấy nội dung dù ứng dụng production có RBAC hạn chế.

Checklist:

1. Mã hóa archive/storage theo cơ chế được hỗ trợ (`cbbackupmgr`/object-store encryption) và quản lý keys riêng.
2. TLS khi chuyển backup giữa cluster/client/object store; xác minh certificate, tránh `--no-ssl-verify`.
3. Service account backup có quyền cần thiết; tách quyền backup, restore, delete/retention.
4. Không lưu password, object-store secret, passphrase hoặc KMS key ngay trong script/repo.
5. Kho backup off-site/isolated, có policy immutable/WORM/object lock nếu yêu cầu.
6. Thời gian lưu và quyền xóa tương thích pháp lý và chính sách dữ liệu cá nhân.
7. Logging không ghi full JSON/PII hoặc secret vào report.
8. Rotation/access audit cho KMS keys; thử decrypt archive **trong drill**.
9. Xác minh backup bao gồm đúng tenant theo policy, không dùng snapshot production làm dữ liệu dev mở.
10. Hạn chế egress/copy archive ra laptop.

**Encryption at rest của Couchbase Server không có nghĩa các cấu hình encryption-at-rest sẽ được sao lưu và khôi phục tự động.** Tài liệu `cbbackupmgr` lưu ý một số settings đó không nằm trong backup config.

## 16. Backup là tài sản cần kiểm thử integrity

Một cơ chế cơ bản:

~~~text
Backup job complete
  -> cbbackupmgr info
  -> Archive object/file inventory
  -> Checksum/signature nếu có
  -> Off-site replica verification
  -> Test restore
  -> Spring app readback + business reconciliation
~~~

- Một checksum SHA-256 chứng minh **bytes khớp với bản tham chiếu**, không chứng minh business schema đúng.
- Nếu archive thiếu incremental base, mọi objects ở đó có thể checksum hợp lệ nhưng không đủ để restore mốc mong muốn.
- Nếu mất encryption keys, archive vẫn nguyên vẹn nhưng **không giải mã được**.
- Nếu backup bị corrupt, không cho phép `--continue-on-cs-failure` như mặc định “cho qua”.
- Khi download Capella backup, nếu UI cung cấp checksum, đối chiếu bằng `sha256sum`/`Get-FileHash` ở môi trường phù hợp.
- Định kỳ thực hiện **restore vào môi trường cô lập**; đây là bằng chứng mạnh hơn việc chỉ đọc metadata.

Đừng lấy việc backup scheduler báo “success” làm chỉ số duy nhất của DR readiness.

## 17. Không khôi phục thử trực tiếp lên production

Một lần restore có thể:

- Ghi lại document cũ lên collection đang phục vụ.
- Tái tạo document đã xóa hoặc hết hạn nếu options cho phép.
- Thay đổi bucket/collection settings hoặc index definitions theo restore configuration.
- Gây xung đột với dữ liệu mới hơn ở target.
- Kích hoạt Eventing/CDC/search update và downstream side effects.
- Gây tăng tải KV/index/Query, ảnh hưởng p99.
- Làm lộ dữ liệu production trong môi trường không được bảo vệ như production.

**Recovery drill chuẩn bắt đầu ở môi trường cô lập**: cluster/bucket đích khác production, credentials/tokens riêng, network rules riêng, outbound integration bị chặn hoặc thay bằng mocks.

~~~text
Production Couchbase ----> Backup archive / immutable storage
                                 |
                                 v
                   Isolated DR test Couchbase
                                 |
                      Read-only verification
                                 |
                       Spring readback tests
                                 |
                      Business reconciliation
                                 |
                          Approval report
~~~

Không cho DR test gửi email, webhook, payment capture, Kafka event hoặc Eventing function vào hệ thống thật. Nếu cần đo quy trình cutover, chỉ thực hiện trong tabletop/staging hoặc theo change control được phê duyệt.

## 18. Lập kế hoạch restore: ai, ở đâu, đến mốc nào?

Trước khi chạy restore cần một **restore manifest**:

~~~yaml
recovery:
  incidentId: "DR-2026-11"
  archive: "/data/couchbase-backups"
  repository: "shop-prod"
  sourceBucket: "shop"
  targetBucket: "shop_dr"
  targetCluster: "cb-dr-a.internal"
  recoveryPoint: "backup-name-selected-from-info"
  applicationImage: "spring-shop:version-locked"
  businessReadback: "required"
  externalEventsEnabled: false
~~~

Đây là **file mẫu minh họa**, không tự tạo trong repo học tập và không được dùng làm credential/config production.

Checklist quyết định:

1. Mốc backup được chọn có đáp ứng RPO thực tế không?
2. Có đầy đủ incremental chain và key giải mã không?
3. Target version tương thích với backup tool và source Server không?
4. Target bucket/scope/collection có trống hoặc mapping rõ không?
5. Có ngăn side effects từ Eventing, Kafka connector và Spring jobs không?
6. Có kiểm soát quyền người restore/approval/dry-run tài nguyên không?
7. Có nhân sự chịu trách nhiệm acceptance và rollback?
8. Có đủ capacity để restore + rebuild indexes trong RTO không?

## 19. Restore bằng `cbbackupmgr` vào target cô lập

Ví dụ CLI chỉ cho **môi trường diễn tập**:

~~~bash
cbbackupmgr restore \
  --archive /data/couchbase-backups \
  --repo shop-prod \
  --cluster couchbase://cb-dr-a.internal \
  --username restore_operator \
  --map-data shop=shop_dr
~~~

Điều kiện:

- Source backup có bucket `shop`; target `shop_dr` được chuẩn bị hoặc workflow dùng option tự tạo phù hợp.
- Khi remap bucket, kiểm tra **scopes/collections/IDs/settings** và metadata restrictions trên Server/tool version.
- Tool mặc định có thể restore nhiều data/metadata loại khác nhau, tùy repository configuration và flags; đừng ngầm cho phép tất cả khi diễn tập.
- Không hardcode password. Dùng authentication phù hợp (prompt, mTLS, secret manager).
- Nếu dùng TLS, cung cấp CA certificate và xác minh server identity; **không tắt SSL verification**.
- Khi archive chứa nhiều backups, nếu không chỉ định start/end, `cbbackupmgr` có thể phục hồi một **dải** từ backup đầu đến mới nhất theo behavior tool. Hãy chỉ rõ recovery point khi bài toán yêu cầu mốc cụ thể.
- Nếu nhận checksum failure/partial backup, phải phân tích trước khi bỏ qua.
- Sau restore vẫn phải verify data, index và application readback.

Không chạy lệnh này trên production hay trên target có dữ liệu thật khi chưa có quyền, backup/snapshot đích và change plan.

## 20. Chọn `--start` và `--end` với backup IDs thực

Dùng:

~~~bash
cbbackupmgr info \
  --archive /data/couchbase-backups \
  --repo shop-prod
~~~

để xem các backup identifiers thực tế.

Để phục hồi một recovery point cụ thể, dùng dải `--start`/`--end` theo tài liệu `cbbackupmgr restore`. **Không bịa backup ID** hoặc copy timestamp từ tài liệu ví dụ rồi chạy.

Lưu ý:

- Một backup incremental dựa trên lịch sử trước nó; phục hồi **chỉ một backup** không đồng nghĩa “mang theo mọi base dữ liệu” trong tất cả trường hợp.
- Tài liệu restore cho biết hành vi khi failover giữa các backup có thể ảnh hưởng việc dữ liệu nào được áp lại trong dải; phải hiểu command semantics và thử trong DR cluster.
- Chọn mốc **trước thao tác xóa/corruption** khi sự cố logic.
- Chọn mốc **mới nhất đã verify** khi ưu tiên RPO.
- Khoảng giữa backup và incident cần business reconciliation, không giả bộ không có writes.
- Nếu restore chỉ một subset keys/collections, phải kiểm tra dependencies và consistency khi ứng dụng đọc.

## 21. `--force-updates` và conflict resolution: cảnh báo mạnh

Theo tài liệu Couchbase, restore thông thường sử dụng conflict resolution, tránh ghi đè dữ liệu đích mới hơn bằng những document cũ từ backup trong nhiều tình huống.

Option:

~~~text
--force-updates
~~~

có thể **ghi đè document mới hơn tại target**, gây mất dữ liệu nếu dùng nhầm.

**Không dùng `--force-updates` như cách chữa “restore skipped docs” mà chưa biết vì sao skipped**. Những nguyên nhân có thể bao gồm key đã tồn tại với version mới, tombstone/expired record, scope IDs khác, backup range semantics hoặc source corruption.

Ưu tiên một target bucket/cluster **mới và cô lập** để hạn chế xung đột. Nếu bắt buộc restore in-place, cần approval, freeze writes, backup target trước, dry-run/manifest và phương án phục hồi ngược.

## 22. Mapping bucket/scope/collection không được đoán

Ứng dụng Spring có:

~~~java
@Document
@Scope("catalog")
@Collection("products")
public class ProductEntity {
    @Id
    private String id;
    // Fields...
}
~~~

Nó sẽ tìm `shop.catalog.products` theo cấu hình bucket.

Nếu restore vào `shop_dr.catalog.products`, ứng dụng chạy test phải **đổi bucket config sang `shop_dr`**, không trỏ về production.

Quy tắc `cbbackupmgr --map-data` có giới hạn:

- Bucket có thể remap sang bucket.
- Scope/collection thường remap trong **cùng bucket** và đúng cấp, tùy version.
- Một số chuyển đổi bucket `_default._default` → collection đặc biệt có giới hạn metadata.
- Không mặc định remap chéo bucket ở cấp collection là hợp lệ.
- Scope/collection có cùng name nhưng khác internal IDs có thể yêu cầu mapping explicit.
- `--auto-resolve-conflicts` có thể remap theo tên, chỉ dùng khi chắc hai keyspaces là cùng mục đích.
- `--preserve-collection-settings` có thể giữ settings ở target thay vì overwrite bởi backup, nhưng phải đánh giá TTL/maxExpiry policy.

**Một tên collection trùng chưa chứng minh document thuộc đúng logical tenant/schema.**

## 23. TTL và expiry khi restore: không hồi sinh nhầm sessions

Document Couchbase có **expiry metadata** ngoài JSON body. Ví dụ:

~~~text
session::tenant-01::s-123
createdAt: 2026-11-25T01:00:00Z
expiryAt:  2026-11-25T01:30:00Z
restoreAt: 2026-11-25T09:00:00Z
~~~

Nếu giữ nguyên expiry, session này đã hết hạn tại thời điểm khôi phục và không nên trở lại hoạt động. Nhưng tùy restore flags/Server maxTTL và expiration behavior, record có thể bị skip, hết hạn ngay hoặc thay TTL.

Các options `cbbackupmgr restore` liên quan:

| Option | Ý nghĩa | Rủi ro |
| --- | --- | --- |
| `--exclude-expired` | Bỏ qua items đã hết hạn | Hợp với nhiều trường hợp session, nhưng có thể bỏ dữ liệu cần forensic |
| `--replace-ttl all` + `--replace-ttl-with ...` | Thay expiry cho mọi item được chọn | Có thể kéo dài đời session/token trái chính sách |
| `--replace-ttl expired` | Thay expiry cho items đã hết hạn | Có thể hồi sinh thông tin từng bị xóa theo TTL |
| `--replace-ttl-with 0` | Yêu cầu bỏ document expiry | Server `maxExpiry` vẫn có thể áp default/upper bound |

**Không đặt `--replace-ttl all --replace-ttl-with 0` cho production backup chỉ để “đọc được hết dữ liệu”**. Với session/token, đặc biệt cần chính sách bảo mật; có trường hợp đúng là **không khôi phục session collection** hoặc thu hồi mọi session sau DR.

## 24. `maxExpiry` ở target có thể thay đổi kết quả

TTL/expiry sau restore còn chịu quy tắc bucket/collection `maxExpiry`. Nếu target có cấu hình khác source:

- Document không-expire ở source có thể bị gắn expiry ở target.
- Document có expiry dài có thể bị cắt bởi giới hạn target.
- Document đã expired có thể không đọc được dù restore có log received.
- `--preserve-collection-settings` làm target giữ cấu hình, có thể khác source chủ đích.
- `@Expiry`/`@Document(expiry=...)` của Spring Data chỉ ảnh hưởng các operations sau restore theo config; **không tự rewrite mọi expiry metadata đã được backup**.

Trong readback, dùng:

~~~java
import static com.couchbase.client.java.kv.GetOptions.getOptions;

GetResult result = sessions.get(
        sessionId,
        getOptions().withExpiry(true));

long casAfterRestore = result.cas();
Optional<Instant> expiryAfterRestore = result.expiryTime();
~~~

Chỉ assert expiry với document cần giữ TTL; test dùng **tolerance hợp lý**. Đừng dùng `Instant.now()` làm nguồn duy nhất khi clock skew với Server/cbbackupmgr client có thể xảy ra.

## 25. CAS sau restore không nên coi là version bất biến

CAS là token optimistic locking của một document, phục vụ đồng thời. Spring Data:

~~~java
@Version
private Long version;
~~~

và Java SDK:

~~~java
GetResult result = products.get(id);
long currentCas = result.cas();
~~~

đều liên quan tới **CAS hiện hành tại target cluster**.

Không giả định:

- CAS sau restore sẽ bằng CAS ở source/mốc backup.
- CAS có thể dùng làm timestamp hoặc globally monotonic business version.
- CAS cũ lưu trong HTTP ETag/offline client còn hợp lệ sau DR.
- Có thể replay `replaceOptions().cas(oldSourceCas)` mà không đọc lại target.
- `@Version` tự “khôi phục” trạng thái của một transaction external.

**Sau restore, các writers phải đọc lại entity/document để lấy current version**, và những write commands chưa rõ kết quả cần reconciliation. Business `schemaVersion`/`aggregateVersion` phải được quản lý độc lập với CAS.

## 26. Metadata và index definitions không đồng nghĩa index ready

Một backup/recovery có thể đưa lại **GSI index definitions** nhưng không khôi phục nguyên trạng dữ liệu index. Tài liệu `cbbackupmgr restore` cảnh báo một số indexes sẽ được tạo mà **chưa build**, nhất là khi index nodes ở target không trùng source.

Sau restore:

1. Liệt kê các indexes và trạng thái qua hệ thống Query Service/Index Service theo version.
2. Kiểm tra có index bị `deferred`, `building`, lỗi mapping/partition không.
3. Chạy `BUILD INDEX` phù hợp (với đúng names/keyspace, theo runbook), không chạy DDL bừa ở mọi pod startup.
4. Đợi Index Service phục hồi và index build/catch-up hoàn tất.
5. Xem `EXPLAIN` cho critical queries.
6. Chạy truy vấn thực có filter/ORDER BY/pagination; đối chiếu shape, counts và latency.
7. Kiểm tra Search index/alias build và Search freshness nếu UI phụ thuộc.
8. Analytics datasets/links/ingestion có cần tạo lại/refresh theo khả năng backup không.

**KV readback PASS không có nghĩa SQL++ derived queries đã phục vụ được.**

## 27. DDL/index ví dụ cho truy vấn đọc lại

Một index dùng trong bài:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON `shop_dr`.`sales`.`orders`(
  tenantId,
  status,
  createdAt,
  META().id
);
~~~

Lệnh minh họa cấu trúc; không chạy nếu index đã tồn tại hoặc policy yêu cầu `defer_build`. Đối với SQL++ trong Couchbase, tên keyspace/`META()`/index syntax và khả năng optimizer phải được test theo Server version.

Truy vấn readback:

~~~sql
SELECT META(o).id AS id,
       o.orderId AS orderId,
       o.status AS status,
       o.totalMinorUnits AS totalMinorUnits
FROM `shop_dr`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = $status
ORDER BY o.createdAt DESC, META(o).id DESC
LIMIT $limit;
~~~

Khi index chưa build, query có thể lỗi hoặc dùng scan path không phù hợp. Nếu query ngay sau restore/build, cân nhắc `REQUEST_PLUS` của Query Service trong **bài test có budget**, nhưng nó không tạo snapshot toàn bộ transaction hoặc sửa mapping sai.

## 28. Document tồn tại không đồng nghĩa Spring Data mapping đúng

Ví dụ source entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
@Scope("catalog")
@Collection("products")
public class ProductEntity {

    @Id
    private String id;

    @Version
    private Long version;

    @Field("product_name")
    private String name;

    private String tenantId;
    private Long priceMinorUnits;
    private String currency;

    // Constructor, getters/setters cần cho Spring Data mapping.
}
~~~

Document JSON:

~~~json
{
  "_class": "com.example.catalog.ProductEntity",
  "tenantId": "tenant-01",
  "product_name": "Cà phê rang mộc",
  "priceMinorUnits": 145000,
  "currency": "VND"
}
~~~

Khi chỉ dùng SDK:

~~~java
GetResult kv = products.get(productId);
JsonObject raw = kv.contentAsObject();
String name = raw.getString("product_name");
~~~

Khi dùng Repository, mapping của Spring xử lý annotation `@Field("product_name")`. Nếu restore dữ liệu V1 thiếu field hoặc `_class` đã đổi, KV raw đọc được nhưng Repository/DTO conversion có thể sai.

**Bài test cần đọc cả hai đường**: raw KV shape và Spring entity model.

## 29. Đọc lại bằng `CouchbaseRepository`

~~~java
import java.util.Optional;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<ProductEntity, String> {
}
~~~

Một smoke test minh họa:

~~~java
@Test
void restoredProductCanBeMappedByRepository() {
    Optional<ProductEntity> found =
            productRepository.findById(
                    "product::tenant-01::sku-1001");

    assertTrue(found.isPresent());

    ProductEntity entity = found.orElseThrow();

    assertEquals("tenant-01", entity.getTenantId());
    assertEquals("Cà phê rang mộc", entity.getName());
    assertEquals(145000L,
            entity.getPriceMinorUnits().longValue());
    assertEquals("VND", entity.getCurrency());
    assertNotNull(entity.getVersion());
}
~~~

Đây là **khung JUnit**: getters, beans, dependency/test fixture cần được tạo trong ứng dụng test. Không lưu fixtures hardcoded thật có PII/token vào bài học.

Lưu ý:

- `findById` theo keyspace/ID chỉ chứng minh **một document**.
- Spring converter còn phụ thuộc type hints, custom conversions, auditing/mapping và application version.
- Test nên gồm **nhiều schema versions, tenant, nullable field, enum, Instant và monetary representation**.
- Không thực hiện `repository.save(entity)` trong bài smoke test read-only nếu chưa chủ đích kiểm tra write path ở một environment có thể ghi.
- Tránh dùng `repository.findAll()` để “test toàn bộ backup”: tốn tải, có thể yêu cầu GSI và không scale.

## 30. Readback bằng SDK KV để phân biệt lỗi dữ liệu với lỗi converter

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.GetResult;

public record KvEvidence(
        String documentId,
        long cas,
        String storedName,
        String tenantId) {}

public KvEvidence readRaw(
        Collection products, String documentId) {

    GetResult r = products.get(documentId);
    JsonObject raw = r.contentAsObject();

    return new KvEvidence(
            documentId,
            r.cas(),
            raw.getString("product_name"),
            raw.getString("tenantId"));
}
~~~

Nếu raw KV body đúng nhưng Repository mapping lỗi, điều tra:

1. Spring `@Field` alias đã đổi?
2. Spring type discriminator `_class`/type key có đúng với class/alias không?
3. Custom converter/Jackson/Java time module đã được cấu hình?
4. Stored JSON number/string có đúng schema hiện tại không?
5. Entity Java được deploy phiên bản tương thích?
6. Document key nằm trong collection dự kiến?
7. RBAC ở Spring credentials khác account dùng restore?
8. Document có bị expired sau restore không?

Nếu **SDK KV GET cũng báo not-found**, hãy kiểm tra keyspace, TTL, filter/mapping restore, actual stored keys, thay vì lập tức sửa converter.

## 31. SQL++ readback phải kiểm tra alias, index và quyền tenant

Ví dụ Java:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;

JsonObject params = JsonObject.create()
        .put("tenantId", "tenant-01")
        .put("status", "PAID")
        .put("limit", 50);

QueryResult result = cluster.query(
        """
        SELECT META(o).id AS id,
               o.orderId AS orderId,
               o.status AS status,
               o.totalMinorUnits AS totalMinorUnits
        FROM `shop_dr`.`sales`.`orders` AS o
        WHERE o.tenantId = $tenantId
          AND o.status = $status
        ORDER BY o.createdAt DESC, META(o).id DESC
        LIMIT $limit
        """,
        queryOptions()
                .parameters(params)
                .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
                .readonly(true));

List<JsonObject> rows = result.rowsAsObject();
~~~

Kiểm tra:

- Các rows trả đúng alias (không tự suy từ source field name).
- Query không cross-tenant; tenant lấy từ trusted test identity.
- GSI đã build và query plan không full scan ngoài ý định.
- `REQUEST_PLUS` giúp freshness index Query Service ở thời điểm test, **không thay transaction snapshot hoặc application-level consistency**.
- Nếu query 0 rows, phân biệt thực sự không có Orders PAID với lỗi dữ liệu filter/cutoff.
- Data Service KV theo key và Query Service theo index có failure modes khác nhau.

Không test `COUNT(*)` rồi tuyên bố mọi fields/metadata đã map chính xác.

## 32. Quan sát document count và sampling có giới hạn

Một phép đếm:

~~~sql
SELECT COUNT(1) AS total
FROM `shop_dr`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId;
~~~

Dùng nó để so với **expected manifest** theo tenant, nhưng cần lưu ý:

- Count theo index/query cần đúng predicate và index state.
- Backup/restore time window có thể làm lệch count với live cluster.
- TTL, xóa, rebalance và backup consistency làm “count bằng y chang” không phải tiêu chuẩn phổ quát.
- Count không phát hiện giá tiền sai kiểu, ID nhầm tenant hoặc một record bị thay bằng record khác.
- Một vài documents canary phải được đọc **theo key** với fields cụ thể.
- Với datasets lớn, chọn sampling có kiểm soát, không `findAll()` tràn heap.

Một report kết hợp **counts + sentinel keys + domain invariants + index tests** mạnh hơn bất kỳ một con số đơn lẻ nào.

## 33. Kiểm tra CAS, TTL và security metadata sau restore

Với tập canary:

| Thành phần | Kỳ vọng hợp lý |
| --- | --- |
| Document key | Đúng collection và ID |
| Body fields | Đúng schema alias/type, giá trị nghiệp vụ |
| CAS | Có current CAS để optimistic locking; **không yêu cầu bằng source CAS** |
| Expiry | Theo retention/security policy của target |
| `_class`/type alias | Có đủ cho converter/repository query theo config |
| SchemaVersion | Supported by current application image |
| Encryption envelope | Decrypt được bằng keys được ủy quyền |
| Tenant authorization | Đọc tenant khác bị chặn theo app policy |
| Collection `maxExpiry` | Không làm mất hoặc kéo dài lifespan trái ý định |
| Document type/flags | JSON objects nhận diện đúng, raw binary không bị coi thành JSON |

**Đừng ghi lại/sửa mọi document chỉ để khởi tạo CAS mới.** Chỉ khi có migration/repair được phê duyệt, mới thực hiện mutations, có idempotency và backup target trước.

## 34. Kiểm tra Repository query và type discriminator

Một test chỉ gọi `findById(id)` có thể thành công, nhưng generated Repository query vẫn trả rỗng nếu:

- Spring type hint `_class`/type alias đã thay đổi hoặc document gốc không có nó.
- Property `@Field("product_name")` đổi tên, còn query cũ vẫn theo alias trước.
- Entity subtype/enum/`Instant` từ V1 không tương thích với class mới.
- GSI/index chưa build hoặc Query Service chưa đủ quyền.
- Target keyspace mapping bị nhầm sau `--map-data`.
- Derived query/DTO projection thiếu metadata cần cho converter.

Nếu ứng dụng khai báo:

~~~java
public interface ProductRepository
        extends CouchbaseRepository<ProductEntity, String> {
    List<ProductEntity> findByTenantId(String tenantId);
}
~~~

thì test cần gọi cả `findById` lẫn `findByTenantId` với tenant đã xác minh, kiểm tra shape, ordering nếu có và ID không thuộc tenant khác.

**KV body tồn tại không chứng minh mọi Spring Data derived query/projection đã hoạt động.**

## 35. Cấu hình Spring Boot để chỉ đọc DR target

Một DR-only profile minh họa:

~~~yaml
spring:
  couchbase:
    connection-string: "${DR_COUCHBASE_CONNECTION_STRING}"
    username: "${DR_COUCHBASE_USERNAME}"
    password: "${DR_COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "shop_dr"

app:
  outbound:
    kafka-enabled: false
    webhook-enabled: false
    payment-capture-enabled: false
  scheduled-jobs-enabled: false
~~~

`app.*` là **configuration tự định nghĩa của ứng dụng**, phải có code thực sự kiểm soát các jobs/clients tương ứng. YAML không tự vô hiệu hóa Eventing functions, Kafka connectors hoặc external HTTP ở Server/runtime.

Trước test:

1. Kiểm tra connection string, bucket chỉ trỏ DR; nên có network isolation cấm production.
2. DR service account có RBAC đọc đủ collections, không phải Full Admin.
3. Chặn mọi outbound payment/webhook/email/broker consumer; mock integrations.
4. Không cho scheduled jobs tự chạy/mutate data khi context start.
5. Dùng app image/schema converter tương thích backup hoặc có reader V1/V2.
6. Không ghi raw document/PII vào logs/test output.
7. Test runner fail closed nếu có sai keyspace/credential/tenant.

## 36. Schema evolution có thể khiến backup “nguyên vẹn” mà app không đọc

Backup có thể chứa:

~~~json
{
  "schemaVersion": 1,
  "product_name": "Cà phê",
  "priceCents": 145000
}
~~~

trong khi ứng dụng mới chỉ hiểu:

~~~json
{
  "schemaVersion": 2,
  "name": "Cà phê",
  "priceMinorUnits": 145000,
  "currency": "VND"
}
~~~

Khi restore:

- Inventory schema versions bằng sample/manifest.
- Xác định app image/converter nào đọc được các versions.
- Nếu phải migrate, dùng migration **versioned, idempotent, checkpointed** trong target cô lập.
- Không đổi ý nghĩa `priceCents`/`priceMinorUnits`, currency exponent, date timezone bằng ép kiểu ngầm.
- Đọc/test trước migration và sau migration để phân biệt lỗi restore với lỗi upgrade.
- Bảo toàn `@Version`/CAS, TTL và field mapping khi viết lại.
- Không đưa app version mới lên trước khi đã có backward-compatible readers hoặc migration plan.
- Test derived queries và type discriminator `_class`, không chỉ JSON parse.

## 37. Reactive readback cho nhiều sentinel keys có giới hạn

Một helper test (các imports Reactor/SDK được bổ sung theo project):

~~~java
public record ReadbackOutcome(
        String id, boolean success, String reason) {}

public Flux<ReadbackOutcome> checkSentinels(
        com.couchbase.client.java.Collection products,
        List<String> ids,
        String expectedTenant) {

    return Flux.fromIterable(ids)
            .flatMapSequential(id ->
                    products.reactive().get(id)
                            .map(result -> {
                                JsonObject body =
                                        result.contentAsObject();
                                boolean valid =
                                        expectedTenant.equals(
                                                body.getString("tenantId"))
                                        && result.cas() != 0L;

                                return new ReadbackOutcome(
                                        id,
                                        valid,
                                        valid ? "OK" : "INVALID_SCHEMA");
                            })
                            .onErrorResume(error ->
                                    Mono.just(new ReadbackOutcome(
                                            id,
                                            false,
                                            error.getClass().getSimpleName()))),
                    8);
}
~~~

Đây là ví dụ **read-only KV**, không kiểm tra hết domain fields. Test runner phải fail tổng thể nếu bất kỳ outcome `success=false`. Không nuốt exception thành item “success” hoặc `Mono.empty()`. `flatMapSequential(...,8)` giới hạn concurrent GET trong một subscription; không phải concurrency cap toàn hệ thống. Chỉ dùng tập canary nhỏ, không `collectList()` triệu IDs.

CAS khác source sau restore là hợp lệ; kiểm tra sơ bộ `!= 0` không phải bằng chứng domain consistency. Tránh log document IDs nhạy cảm và raw JSON PII.

## 38. Search, Analytics, Eventing và CDC cần kiểm tra riêng

| Hệ thống | Tình trạng sau restore có thể gặp | Điều cần test |
| --- | --- | --- |
| KV | Document có mặt | Key, schema, CAS, expiry |
| SQL++/GSI | Index definitions có nhưng chưa build | `EXPLAIN`, index status, critical queries |
| Search/FTS | Definitions/aliases có, dữ liệu index chưa ingest | Search hit, tenant filter, current KV hydrate |
| Analytics | Datasets/links/ingestion chưa sẵn | Aggregate + freshness SLO |
| Eventing | Functions được restore/đang active ngoài ý định | Vô hiệu hóa side effects trong DR |
| XDCR | Replication direction/targets khác môi trường gốc | Tránh republish/replicate ngược vào prod |
| Kafka/DCP | Broker offsets/checkpoints nằm ngoài backup bucket | Không bật consumers trước reconciliation |
| Cache/projection | Có thể rebuild từ authoritative data | Quy trình invalidate/recompute |

Một Search hit không chứng minh giá hoặc quyền của document hiện hành; nếu cần, KV hydrate rồi authorize. Analytics có ingestion lag; không yêu cầu một Query Service read nhất quán tức thời với nó nếu thiết kế không hỗ trợ.

## 39. Outbox, inbox và các hệ thống ngoài không rollback cùng backup

Timeline:

~~~text
09:00  Backup: Order=PENDING, chưa có outbox OrderPaid
09:20  Payment CAPTURED, Order=PAID, outbox OrderPaid commit
09:25  Kafka consumer tạo Invoice ngoài Couchbase source
09:40  Cluster hỏng; restore về snapshot 09:00
~~~

Bản restore không biết payment/invoice đã xảy ra sau 09:00. Cần:

1. Chặn outbox relays, Kafka consumers, Eventing và payment jobs khi restore.
2. Đối chiếu payment provider/ledger/broker evidence với Order/receipt/outbox.
3. Nếu event đã gửi nhưng outbox hiện PENDING, chỉ replay **cùng eventId** với idempotent consumer.
4. Nếu inbox receipt đã mất, tìm evidence từ consumer ledger trước khi reapply.
5. Không cấp eventId mới cho cùng logical business command.
6. Quarantine trường hợp outcome không rõ thay vì tự refund/recharge.
7. Nếu backup làm lệch trạng thái của nhiều documents, chạy reconciliation script/service được review.
8. Có approval riêng cho mass replay có external side effects.

**Restore Couchbase không hoàn tác một khoản tiền đã capture hoặc một email đã gửi.**

## 40. Business reconciliation phải dùng nguồn độc lập

| Invariant | Nguồn đối chiếu | Kết quả khi lệch |
| --- | --- | --- |
| PAID order có payment đã xác nhận | Payment provider/ledger | Reconcile/manual review |
| Một payment không tạo 2 invoices | Invoice ledger | Deduplicate/compensate theo policy |
| Stock reservation hợp lệ | Inventory ledger | Recalculate / manual check |
| OrderPaid có event identity | Event archive/Kafka metadata | Re-publish đúng event ID nếu an toàn |
| Inbox receipt phản ánh side effect | Consumer database/ledger | Rebuild receipt hoặc quarantine |
| Session đã revoke không active | Auth/revocation source | Rotate/revoke sessions |
| Product price/currency hợp lệ | Catalog audit | Versioned correction |

Report ví dụ:

~~~json
{
  "orderId": "1001",
  "backupStatus": "PENDING",
  "paymentStatus": "CAPTURED",
  "invoiceStatus": "ISSUED",
  "risk": "RESTORE_BEHIND_EXTERNAL_EFFECT",
  "recommendation": "RECONCILE_BEFORE_REPLAY"
}
~~~

`recommendation` là **đề xuất**, không phải một command tự gọi external API.

## 41. Capella cluster snapshot có giới hạn và rủi ro riêng

Capella có **Cloud Snapshot cluster backup** bên cạnh bucket backup:

- Snapshot cấp cluster lưu trữ toàn cụm/buckets theo dịch vụ cloud provider, một backup là một recovery unit logic độc lập.
- Khác bucket backup full/incremental cycle; cluster snapshot **không tải xuống** để dùng `cbbackupmgr` như bucket archive.
- Cluster snapshot có thể restore cả indexes và giảm RTO nhưng vẫn phải chạy Spring Data readback/authorization tests.
- Memory Only bucket data không nằm trong cluster snapshot.
- Restore sang cluster khác, copy cross-region, version compatibility phụ thuộc deployment/cloud/Server version.
- CMEK/KMS key ID cần giữ được; xóa key có thể khiến backup không thể giải mã.

**Cảnh báo từ tài liệu Capella:** khi restore cluster snapshot, **dữ liệu hiện có trên target cluster sẽ bị hủy** và cluster không phục vụ trong quá trình restore. Cluster access credentials và allowlisted IPs có thể bị xóa, phải lưu inventory bảo mật và tái tạo trước khi đưa ứng dụng trở lại. Không dùng restore cluster snapshot in-place làm test vô hại.

## 42. Bốn tầng chấp nhận khôi phục

~~~text
Tầng A: Archive hợp lệ
  |
  +-- Backup COMPLETE
  +-- Chain/full/incremental đủ
  +-- Đọc được archive; checksum/key đúng
  |
Tầng B: Couchbase KV hợp lệ
  |
  +-- Đúng bucket/scope/collection
  +-- Sentinel GET, schema, expiry, CAS
  +-- Count/sample tenant trong kỳ vọng
  |
Tầng C: Ứng dụng đọc được
  |
  +-- Spring Repository/Template mapping
  +-- SQL++ index/query
  +-- Search/Analytics nếu critical
  +-- RBAC, encryption keys
  |
Tầng D: Nghiệp vụ và cutover
  |
  +-- Payment/invoice/outbox/inbox reconciliation
  +-- No side-effect replay chưa được chấp thuận
  +-- SLO/readiness đạt
  +-- Owner/SRE/Business sign-off
~~~

Không tự động mở traffic chỉ vì `cbbackupmgr restore` exit code bằng 0. Nếu một tầng chưa đạt, báo **partial recovery** và chặn những chức năng có nguy cơ sai, hoặc dùng degraded plan đã được thiết kế.

## 43. Integration và fault-injection tests

| Test case | Kỳ vọng |
| --- | --- |
| Full+incremental chain đầy đủ | Restore đúng mốc và collections |
| Thiếu base incremental | Không báo recovery PASS |
| Backup partial | Chặn/promote theo policy, báo missing data |
| Checksum corruption | Fail closed; không bỏ qua bằng `--continue-on-cs-failure` |
| Wrong decryption key | Fail an toàn và alert |
| Target sai bucket `--map-data` | Canary không tìm thấy, không mở traffic |
| Scope/collection same name nhưng ID khác | Có mapping có kiểm soát, không silently overwrite |
| TTL source khác target `maxExpiry` | Readback phát hiện lifespan sai |
| Expired session/token | Không bị hồi sinh thành active |
| CAS source khác target | App dùng current CAS, không reuse token cũ |
| Missing `_class`/bad converter | KV OK nhưng Repository test fail |
| GSI definition chưa BUILD | SQL++ smoke test chưa đạt |
| FTS chưa ingest | Search không được coi là ready |
| Spring image mới không đọc schema V1 | Có migration/fallback đã test |
| Outbox đã gửi nhưng restore về PENDING | Replay cùng eventId, không duplicate business effect |
| Payment ngoài DB mới hơn backup | Reconciliation, không capture lại |
| RBAC của DR user thiếu quyền | Phát hiện qua app credentials, không chỉ admin |
| Wrong restore credentials/network | Dừng, không lộ secrets |
| Cluster snapshot in-place trên target có dữ liệu | Chặn bằng approval/target isolation |
| Restore dưới tải gần production | RTO/SLO/heap/Index build được đo |

Kiểm thử phá dữ liệu chỉ thực hiện ở **test/DR cluster có thể tái tạo**, không ở production không có change control.

## 44. Runbook khôi phục từng bước

**Pha A — Triage và giữ bằng chứng**

1. Xác định loại incident: node failover, logical deletion, ransomware, cluster loss, data corruption hay sai schema deployment.
2. Tạm dừng những writers/relays có thể làm tình hình xấu hơn, nếu nghiệp vụ cho phép.
3. Giữ nguyên log, backup inventory, transaction IDs, broker/payment evidence.
4. Xác định người chịu trách nhiệm ra quyết định và channel phối hợp.
5. Xác định mốc RPO có thể khôi phục và RTO còn lại.

**Pha B — Chuẩn bị**

1. Chọn archive/repository/recovery point từ `cbbackupmgr info` hoặc Capella UI.
2. Xác minh complete backup chain, storage integrity, encryption keys, tool/Server versions.
3. Tạo target cluster/bucket cô lập với capacity và cấu hình network/TLS.
4. Chặn external side effects/replication nhầm chiều.
5. Chuẩn bị manifest expected collections, sentinel keys, query/index definitions và app image tương thích.
6. Lấy approval restore target và rollback plan.

**Pha C — Restore kỹ thuật**

1. Restore dữ liệu theo lệnh/Capella workflow phù hợp.
2. Xác minh output: received, errors, skipped, partial, warning.
3. Xác minh bucket/scope/collection, maxTTL và RBAC/security settings.
4. Rebuild/khởi tạo indexes, Search/Analytics/Query metadata cần thiết.
5. Kiểm tra schema/conversion migration nếu phải chạy, có checkpoint.

**Pha D — Readback và reconciliation**

1. Chạy SDK KV sentinel GET + CAS/expiry/field JSON.
2. Chạy Spring Repository/Template tests qua credentials DR.
3. Chạy SQL++ critical queries và index readiness; đo latency.
4. Kiểm tra Search/Analytics nếu thuộc critical workflow.
5. So counts, source manifest, business invariants và tenant authorization.
6. Đối soát Order/payment/invoice/outbox/inbox với external evidence.
7. Quarantine các workflow outcome chưa rõ.

**Pha E — Cutover có kiểm soát**

1. Xác nhận RPO thực, elapsed RTO và những mất mát được chấp nhận.
2. SRE/DBA/application owner/business owner ký nhận.
3. Cập nhật routing/secrets/credentials/TLS theo change plan.
4. Bật traffic từng bước với readiness, circuit breaker, rate limiter.
5. Bật background jobs/consumers/relays sau reconciliation.
6. Theo dõi p95/p99, CAS conflicts, Query failures, duplicate events và backlog.
7. Có rollback/forward-fix plan nếu phát hiện lỗi ứng dụng.

## 45. Observability cho backup và restore

Các metrics sau là **đề xuất của application/operations**, không khẳng định đều được SDK tự phát:

| Metric | Ý nghĩa |
| --- | --- |
| `backup_last_success_age_seconds` | Mốc phục hồi gần nhất đã cũ bao lâu |
| `backup_job_failures_total` | Bao nhiêu job thất bại |
| `backup_partial_count` | Backup thiếu data |
| `backup_bytes_total` | Số bytes đã backup |
| `backup_repository_size_bytes` | Dung lượng/quota/retention |
| `backup_integrity_check_success` | Checksum/manifest verification |
| `restore_elapsed_seconds` | Thời gian restore |
| `restore_items_skipped_total` | Items bị conflict/expired/filter |
| `restore_index_build_seconds` | Chi phí rebuild GSI/Search |
| `restore_application_readback_failures` | DTO/entity/query lỗi |
| `restore_business_reconciliation_gaps` | Business invariants chưa khớp |
| `rpo_achieved_seconds` | RPO thực đo theo recovery point |
| `rto_achieved_seconds` | Thời gian đến acceptance/cutover |
| `dr_drill_success` | Kết quả diễn tập end-to-end |

Đừng chỉ alert khi backup job exit non-zero: alert khi **mốc backup khả dụng gần nhất** vượt RPO, khi backup partial, khi archive sắp hết dung lượng hoặc khi lần diễn tập restore/readback mới nhất quá hạn.

Không đưa document IDs, user email, paymentId hoặc secret vào metric labels có cardinality cao. Report chi tiết theo key chỉ ở môi trường audit được phân quyền/redacted.

## 46. Cutover và “khóa ghi” cần là chính sách rõ

Việc chuyển từ cluster mất sang DR target cần một thời điểm owner quyết định:

~~~text
Old primary unavailable / quiesced
         |
Choose restore/recovery point
         |
Restore DR target
         |
Readback + reconciliation + sign-off
         |
Switch application config/routing
         |
Gradually enable traffic
         |
Enable workers, brokers, relays safely
         |
Monitor; prevent split-brain writers
~~~

Rủi ro:

- Old primary trở lại và **cùng nhận writes**: split-brain.
- Broker consumer của môi trường cũ tiếp tục ghi vào target mới sai phiên bản.
- Old caches chứa price/session state trước restore.
- XDCR đẩy bản cũ ngược hướng sau khi đảo vai trò.
- JWT/session từ trước sự cố được chấp nhận dù revoke record đã mất.
- Writer dùng CAS cũ từ source nhưng target đã có token mới.
- GSI/Search/Analytics chưa bắt kịp, trong khi traffic đã mở đầy đủ.

Phải có policy **single-writer**, fencing/lease/credentials/network isolation, cache invalidation, version/ETag refresh và re-enable jobs có kiểm soát. Không khẳng định một DNS change tự giải quyết tất cả.

## 47. Đo thực tế RPO và RTO qua DR drill

Một báo cáo thử nghiệm:

~~~text
Incident simulation at:       13:40
Latest usable recovery point: 13:30
Restore target ready:         14:04
Spring Data readback pass:    14:12
Business reconciliation pass: 14:25
Traffic cutover pass:         14:32

Observed data recovery gap:   10 minutes
Observed end-to-end downtime: 52 minutes
~~~

Phần này minh họa cách ghi số liệu; không dùng số đo giả làm thực tế production.

Nếu mục tiêu RPO ≤ 15 phút và RTO ≤ 45 phút, ví dụ đạt RPO nhưng **không đạt RTO**, dù `cbbackupmgr restore` đã hoàn thành lúc 14:04. Cần tối ưu bottleneck đã đo: data transfer, GSI rebuild, RBAC, app schema compatibility hoặc reconciliation.

Drill nên bao phủ:

- Full backup và một chuỗi incrementals dài.
- Archive ở storage/region khác (nếu thiết kế DR yêu cầu).
- Cluster/bucket đủ lớn gần production.
- Backup phục hồi với keys KMS đã rotation.
- Schema V1/V2 cùng tồn tại.
- Index rebuild và Query p99.
- Outbox/inbox events, TTL/CAS, tenant security.
- Unexpected skipped/conflict docs.
- Restart ứng dụng, workers, readiness và traffic cutover.
- Có người ký xác nhận business recovery.

## 48. Checklist trước khi tuyên bố “có backup”

### Archive và bảo mật

- [ ] Có RPO/RTO được chủ sở hữu nghiệp vụ phê duyệt.
- [ ] Có lịch backup và retention đáp ứng các mục tiêu ấy.
- [ ] Complete backup chain, không còn partial unknown.
- [ ] Archive được bảo vệ off-site/immutable theo chính sách.
- [ ] Checksum/encryption keys/truststore và access permissions đã thử.
- [ ] Tool/Server versions tương thích, edition/options được kiểm tra.
- [ ] Có manifest buckets/scopes/collections/indexes cần bảo vệ.
- [ ] Có tài liệu riêng cho secrets/IAM/cluster config không nằm trong backup.

### Restore và ứng dụng

- [ ] Có DR target cô lập, không gửi external side effects.
- [ ] Lệnh/backup selection/`--map-data` được review.
- [ ] Không dùng `--force-updates` hoặc thay TTL hàng loạt tùy tiện.
- [ ] MaxExpiry/TTL và expired sessions theo policy.
- [ ] CAS/`@Version` dùng current state sau restore.
- [ ] GSI/FTS/Analytics/Eventing readiness được kiểm tra theo workload.
- [ ] Spring Repository/Template và SDK KV readback đều PASS.
- [ ] SQL++ queries, DTOs và schemaVersion/custom converters đọc được.
- [ ] Tenant/RBAC/encryption/PII được xác minh.
- [ ] Sentinel canaries/aggregate counts/domain invariants có evidence.

### Nghiệp vụ và vận hành

- [ ] Outbox/inbox/broker/payment reconciliation completed hoặc exceptions được quarantine.
- [ ] Không có split-brain writers, XDCR/CDC replay ngoài ý muốn.
- [ ] Có criteria sign-off/cutover/rollback.
- [ ] RPO/RTO đo bằng drill, không chỉ ước lượng.
- [ ] Có alerts cho backup age, partial, integrity, readback failures.
- [ ] Có ownership, on-call, runbook và ngày diễn tập kế tiếp.

## 49. Bài tập thực hành và tự kiểm tra

### Bài tập A — Backup có inventory

1. Trên Couchbase test cluster, tạo `shop.catalog.products` và `shop.sales.orders`.
2. Tạo ít nhất 20 documents có các schema versions/`@Field`/TTL khác nhau.
3. Tạo GSI cho Query theo tenant và trạng thái.
4. Dùng `cbbackupmgr config` tạo repository vào archive **cô lập**.
5. Chạy backup, sau đó update một số records và chạy incremental.
6. Dùng `cbbackupmgr info` ghi danh sách backups, full/incremental và completeness.
7. Viết manifest có sentinel keys, expected schema, selected recovery point.
8. Đo backup duration, storage size và backup age.

### Bài tập B — Restore và readback

1. Tạo DR target bucket `shop_dr` trong test cluster riêng.
2. Restore đúng recovery point từ manifest, dùng mapping phù hợp.
3. Kiểm tra TTL document còn/hết hạn theo source/target maxExpiry.
4. Dùng SDK GET đọc ít nhất 5 sentinel keys; kiểm tra CAS/expiry/JSON.
5. Chạy `ProductRepository.findById` với Spring bucket config trỏ `shop_dr`.
6. Test derived query theo `@Field` và tenant filter.
7. Kiểm tra GSI index state; build lại nếu cần; chạy `EXPLAIN`.
8. So counts, types, nullable fields, currency/date conversions với manifest.
9. Ghi report PASS/FAIL, không chỉ log command succeeded.

### Bài tập C — Lỗi và đối soát

1. Thử restore thiếu incremental base (chỉ trong test).
2. Dùng wrong KMS/secret để thấy backup không giải mã được.
3. Thử schemaVersion V1 nhưng reader chỉ có V2.
4. Trình bày sự khác nhau giữa source CAS và current target CAS.
5. Giả lập session đã revoked/expired trước incident.
6. Giả lập payment capture và invoice xảy ra **sau mốc backup**.
7. Viết reconciliation report không tự recharge.
8. Test outbox/inbox replay cùng eventId, consumer idempotent.
9. Nếu có Capella test workspace, đối chiếu tính năng bucket backup/cluster snapshot và yêu cầu restore target.
10. Đo RPO/RTO đầy đủ tới lúc ứng dụng đọc được dữ liệu.

### Câu hỏi tự kiểm tra

1. Backup job success chứng minh những gì và không chứng minh gì?
2. RPO khác RTO ở thời điểm bắt đầu/kết thúc nào?
3. Vì sao replication không thay thế backup?
4. Archive/repository/full/incremental của `cbbackupmgr` khác nhau thế nào?
5. Vì sao không có hai backup clients đồng thời trên cùng archive?
6. Vì sao một bản backup có thể nhất quán theo item nhưng không nhất quán đồng thời giữa Order/outbox?
7. `cbbackupmgr info` có chứng minh Spring entity mapping đúng không?
8. Restore option `--force-updates` nguy hiểm thế nào?
9. Vì sao cần kiểm soát `--map-data` ở bucket/scope/collection?
10. TTL/`maxExpiry` có thể làm restored session biến mất hoặc hồi sinh như thế nào?
11. CAS sau restore có cần bằng CAS nguồn không?
12. Khi nào `@Version`/`_class`/`@Field` tạo vấn đề readback?
13. KV GET đúng nhưng SQL++ query trả 0 rows: có những nguyên nhân nào?
14. Index definitions được restore có tự chứng minh index đã BUILD không?
15. Search/Analytics readback khác KV readback điểm nào?
16. Vì sao cần khóa giải mã và credentials ngoài backup dữ liệu?
17. Capella cluster snapshot khác bucket backup ở phạm vi/restore semantics nào?
18. Vì sao restore cluster snapshot Capella cần approval đặc biệt?
19. Nếu payment đã capture sau mốc backup, có nên capture lại không?
20. Inbox receipt và outbox event có vai trò gì sau restore?
21. Sentinel canary và business reconciliation bổ sung cho COUNT thế nào?
22. Khi nào nên chặn traffic dù restore CLI thành công?
23. Cần đo những metrics nào để xác nhận RPO/RTO đạt thực tế?
24. Split-brain writers xuất hiện thế nào trong cutover?
25. Tại sao DR drill phải gồm cả Spring Data Repository queries?
26. Những bước nào cần sign-off trước khi bật lại consumers/relays?

## 50. Tài liệu chính thức và giới hạn phiên bản

- [Couchbase Server — cbbackupmgr](https://docs.couchbase.com/server/current/backup-restore/enterprise-backup-restore.html): phạm vi, incremental strategy và compatibility.
- [Couchbase Server — cbbackupmgr config](https://docs.couchbase.com/server/current/backup-restore/cbbackupmgr-config.html): archive/repository config, scope và flags.
- [Couchbase Server — cbbackupmgr backup](https://docs.couchbase.com/server/current/backup-restore/cbbackupmgr-backup.html): backup jobs, partial/resume/purge và constraints.
- [Couchbase Server — cbbackupmgr restore](https://docs.couchbase.com/server/current/backup-restore/cbbackupmgr-restore.html): restore range, `--map-data`, `--force-updates`, TTL, GSI rebuild và conflict resolution.
- [Couchbase Server — cbbackupmgr info](https://docs.couchbase.com/server/current/backup-restore/cbbackupmgr-info.html): archive inventory và backup metadata.
- [Couchbase Server — cbbackupmgr tutorial](https://docs.couchbase.com/server/current/backup-restore/cbbackupmgr-tutorial.html): ví dụ full/incremental và đọc `info`.
- [Couchbase Server — backup strategies](https://docs.couchbase.com/server/current/backup-restore/cbbackupmgr-strategies.html): periodic merge và retention patterns.
- [Couchbase Capella — Bucket backups](https://docs.couchbase.com/cloud/clusters/backup-restore.html): scheduled/on-demand backup, incremental cycles, consistency limitations và download checksum.
- [Couchbase Capella — Cluster backups](https://docs.couchbase.com/cloud/clusters/cloud-snapshots.html): Cloud Snapshots, CMEK, destructive restore và access configuration.
- [Couchbase Capella — CLI backup/restore](https://docs.couchbase.com/cloud/clusters/cli-backup-restore.html): restrictions khi dùng `cbbackupmgr` với Capella.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): `GetResult`, CAS và expiry metadata.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): Query Service, scan consistency và query metadata.
- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Field`, `@Version`, converters và type metadata.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): `findById`/derived queries và entity mapping.
- [Spring Data Couchbase — Template](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): low-level data access với converter.
- [Spring Boot — Couchbase configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html): app connection, bucket và auto-configuration.

**Phụ thuộc phiên bản và deployment:** Backup/restore tool, Capella plan, edition, encryption, Server version và các option `cbbackupmgr` phải được đối chiếu chính xác trước khi chạy. Java SDK/Spring Data converter behavior, source type key, `@Expiry`, Query index build và các bước phục hồi Eventing/Analytics cũng phụ thuộc cấu hình thực tế. Các snippets là **tài liệu học tập**, không phải lệnh đã được thực thi ở production. Biên dịch ví dụ, kiểm tra domain invariants và Content QA đầy đủ thuộc bước kiểm thử chuyên môn kế tiếp.

> **Ghi nhớ:** **Có backup chưa phải có khả năng phục hồi.** Hãy chọn đúng recovery point theo RPO, restore an toàn vào target cô lập, kiểm tra integrity và cấu trúc bucket/scope/collection, đọc lại bằng **SDK KV + Spring Repository/Template + SQL++**, xác minh TTL/CAS/schema/index, đối soát mọi external side effects, rồi mới mở traffic. Thành công là **dữ liệu còn đọc đúng và nghiệp vụ tiếp tục an toàn**, không phải một dòng log “Restore completed successfully”.




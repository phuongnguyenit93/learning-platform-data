# Xác định dữ liệu cần bảo vệ và yêu cầu RPO/RTO

## 1. Tại sao phải xác định dữ liệu trước khi chọn công cụ backup?

Một ứng dụng bán vé dùng nhiều thành phần:

~~~text
                 +--> MongoDB: đơn đặt chỗ
                 |
Java API --------+--> Redis: session, quota, idempotency
                 |
                 +--> Kafka: sự kiện thanh toán
                 |
                 +--> Elasticsearch: tìm kiếm
                 |
                 +--> Object storage: vé PDF
~~~

Sau một lần triển khai lỗi, dữ liệu MongoDB bị xóa nhầm. Đội vận hành tìm được snapshot gần nhất, khôi phục collection và thông báo rằng database đã “phục hồi thành công”. Nhưng đơn hàng mới sau snapshot biến mất; Redis vẫn giữ idempotency key cũ; Elasticsearch đã cập nhật những trạng thái mới; vé PDF của một số giao dịch không còn bản ghi tham chiếu; một worker có thể gửi email xác nhận thêm lần nữa.

Ở tình huống này, việc khôi phục **một database** khác việc phục hồi **một quy trình nghiệp vụ**. Nếu chưa xác định chính xác tài sản dữ liệu nào cần bảo vệ, phụ thuộc nào phải khôi phục cùng nhau, và doanh nghiệp cho phép mất bao nhiêu dữ liệu hoặc gián đoạn bao lâu, rất khó chọn backup strategy đúng.

Bài **“Xác định dữ liệu cần bảo vệ và yêu cầu RPO/RTO”** thuộc chương **Sao lưu và phục hồi** trong module **Database No SQL**. Đây là bước nền tảng trước khi thảo luận snapshot, point-in-time recovery, incremental backup, restore automation hay disaster recovery.

**Ý tưởng cốt lõi:** bắt đầu từ hậu quả nghiệp vụ và ranh giới dữ liệu có thẩm quyền; sau đó mới xác định mức RPO/RTO, failure scenarios và cơ chế backup/recovery có thể kiểm chứng được.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Lập danh mục dữ liệu cần bảo vệ theo dịch vụ, tenant, region và nguồn có thẩm quyền.
2. Phân biệt dữ liệu gốc, dữ liệu dẫn xuất, cache, logs, CDC, snapshots và metadata bắt buộc để khôi phục.
3. Diễn giải chính xác **Recovery Point Objective (RPO)** và **Recovery Time Objective (RTO)**.
4. Xác định RPO/RTO theo **tình huống sự cố**, không gán một con số duy nhất cho mọi loại lỗi.
5. Tính giới hạn mất dữ liệu từ thời điểm phục hồi, độ trễ replication, backup interval và log continuity.
6. Ước lượng tổng thời gian RTO từ phát hiện sự cố đến khi nghiệp vụ phục vụ trở lại, kể cả kiểm chứng và cutover.
7. Thiết kế ranh giới snapshot/restore nhất quán khi dữ liệu nằm trên nhiều collections, shards hoặc systems.
8. Phân biệt high availability, replication, backup, PITR và archival retention.
9. Lập kế hoạch theo đặc điểm MongoDB, Cassandra, DynamoDB, Redis và Elasticsearch/OpenSearch.
10. Xây bằng chứng bằng restore drills, metrics, runbook và acceptance criteria.

---

## 2. RPO và RTO là gì?

### 2.1. RPO — cho phép mất bao nhiêu dữ liệu?

**RPO (Recovery Point Objective)** là mục tiêu về mức lùi thời gian của trạng thái dữ liệu có thể phục hồi so với thời điểm sự cố, trong một failure scenario xác định.

Ví dụ:

~~~text
10:00  Backup snapshot
10:10  Customer A đặt đơn #101
10:20  Customer B đặt đơn #102
10:29  Storage bị phá hủy
10:40  Restore snapshot 10:00
~~~

Nếu chỉ có snapshot lúc 10:00, recovery point lùi khoảng **29 phút** so với sự cố; những commits sau 10:00 có thể không có trong bản khôi phục.

Một tổ chức công bố `RPO <= 5 phút` thì backup snapshot mỗi giờ, không có log replay hoặc cơ chế bổ sung, **không đáp ứng mục tiêu đó** cho tình huống mất toàn bộ dữ liệu nguồn.

RPO là **mục tiêu**, không phải bằng chứng hệ thực tế đã đạt. Phải phân biệt:

- **RPO mục tiêu:** mức mất dữ liệu tối đa được chấp nhận.
- **Recoverable point thực tế:** thời điểm/position mới nhất có thể phục hồi an toàn.
- **Observed data loss:** khác biệt giữa committed state trước sự cố và state sau recovery, có thể không đều giữa shards hoặc systems.

### 2.2. RTO — mất bao lâu để phục hồi dịch vụ?

**RTO (Recovery Time Objective)** là mục tiêu thời gian tối đa để khôi phục khả năng phục vụ được định nghĩa sau một sự cố.

Ví dụ:

~~~text
10:29  Sự cố bắt đầu
10:34  Phát hiện và xác nhận
10:49  Chọn recovery point, cấp môi trường mới
11:45  Restore data files
12:10  Replay logs và rebuild indexes
12:24  Kiểm chứng đơn hàng, thanh toán, ACL
12:30  Chuyển traffic trở lại
~~~

Nếu thời điểm bắt đầu tính theo sự cố 10:29 và kết thúc khi nghiệp vụ thực sự phục vụ lúc 12:30, thời gian phục hồi khoảng **2 giờ 1 phút**. Không chỉ tính 56 phút chạy lệnh restore.

### 2.3. RPO là mốc dữ liệu; RTO là thời gian gián đoạn

~~~mermaid
flowchart LR
    RP["Recoverable point"] -->|"RPO gap"| F["Failure at T0"]
    F -->|"RTO duration"| S["Service restored at T1"]
~~~

RPO và RTO **độc lập về ý nghĩa**, dù phương án kỹ thuật để đáp ứng chúng có liên quan.

### 2.4. Hai mục tiêu có thể khác nhau giữa dữ liệu

- Thanh toán: RPO rất nhỏ, yêu cầu đối soát chặt.
- Product catalog có nguồn khác: có thể rebuild và chấp nhận lùi một khoảng.
- Search index: có thể mất index và tái tạo từ nguồn, nhưng RTO tìm kiếm có thể vẫn cần ngắn.
- Log điều tra: có thể chịu một khoảng mất log theo policy nhưng cần lưu đủ lâu để kiểm toán.
- Session: người dùng có thể đăng nhập lại, trừ khi session đang chứa trạng thái chưa commit.

### 2.5. Recovery Time khác Recovery Point

Một hệ có thể phục hồi trong 3 phút nhưng mất 1 giờ ghi gần nhất; hoặc bảo toàn mọi committed write trong kiến trúc đã thiết kế nhưng cần 8 giờ để chuyển traffic. Không thể lấy RTO tốt để kết luận RPO tốt.

---

## 3. RPO/RTO phải có phạm vi và mốc tính rõ

Một phát biểu chưa đủ:

> “Database có RPO 15 phút, RTO 1 giờ.”

Cần hỏi:

- Database nào, data sets nào, tenant/region nào?
- Với node crash, operator error hay mất cả region?
- Những thao tác nào: point read, ghi đơn hàng, xem hóa đơn, tìm kiếm?
- Đếm thời gian từ **sự cố bắt đầu**, phát hiện sự cố hay quyết định phục hồi?
- Trạng thái “phục hồi” là node chạy, API 200 hay nghiệp vụ đúng và đáp ứng SLO?
- Có chấp nhận degraded mode/read-only không?
- Có bao gồm schema, index, encryption keys, ACL và dependencies?
- Có yêu cầu tránh phục hồi dữ liệu đã bị xóa theo chính sách không?

### 3.1. Một phát biểu có thể đo

Ví dụ mục tiêu được **đề xuất**, không phải tiêu chuẩn chung:

> “Đối với mất toàn bộ primary database ở một region, hệ thống đặt hàng phải khôi phục các đơn đã commit với mức mất dữ liệu theo thời gian không quá 5 phút, và có thể nhận đơn mới trong vòng 60 phút tính từ lúc sự cố bắt đầu; trạng thái thanh toán chưa rõ phải được đối soát trước khi phát hành vé.”

### 3.2. Phân biệt mục tiêu với cam kết

- **Objective:** giới hạn mong muốn được business phê duyệt.
- **Architecture capability:** mức có thể đạt theo cơ chế.
- **Tested result:** kết quả diễn tập gần nhất.
- **Observed result:** thực tế trong sự cố.
- **Contractual SLA:** nếu có, là cam kết có phạm vi/pháp lý riêng.

Không tự đổi một RTO objective thành SLA bảo đảm 100%.

### 3.3. RPO không phải “mất đúng N phút”

Nói `RPO 5 phút` nghĩa **mức mất dữ liệu theo thời gian được phép tối đa theo mục tiêu**, không có nghĩa luôn mất 5 phút. Có thể phục hồi gần như hoàn toàn hoặc tệ hơn mục tiêu nếu backup/log gặp lỗi.

---

## 4. Xác định dữ liệu nào cần bảo vệ: bắt đầu từ quy trình nghiệp vụ

Không nên bắt đầu bằng danh sách server vì một nghiệp vụ có thể phụ thuộc nhiều hệ lưu trữ.

Ví dụ quy trình đặt hàng:

~~~mermaid
flowchart TD
    API["Order API"] --> O["Orders: authoritative NoSQL"]
    API --> I["Inventory reservation"]
    API --> P["Payment provider"]
    O --> OUT["Transactional outbox"]
    OUT --> K["Event stream / CDC"]
    K --> S["Search read model"]
    K --> A["Analytics"]
    API --> R["Redis session / idempotency"]
    O --> B["Object storage: invoices"]
    AUTH["IAM / KMS / TLS identities"] -. "Required to restore" .-> O
    CFG["Schema, indexes, IaC, config"] -. "Required to restore" .-> O
~~~

Một danh mục có ích phải liên kết **tài sản dữ liệu → mục đích → nơi lưu → nguồn có thẩm quyền → phụ thuộc → recovery requirement**.

### 4.1. Đi từ customer journey

Liệt kê các thao tác mà thiếu dữ liệu sẽ gây thiệt hại:

- Tạo/sửa/hủy đơn hàng.
- Giữ chỗ tồn kho.
- Thanh toán và hoàn tiền.
- Cấp/revoke quyền truy cập.
- Giao hàng và truy xuất chứng từ.
- Bảo lưu lịch sử kiểm toán.
- Xem trạng thái đơn hàng.
- Tìm kiếm và báo cáo.

### 4.2. Ranh giới commit nghiệp vụ

Một hệ có thể coi “đơn hàng được xác nhận” chỉ sau khi database ghi và payment provider báo thành công. Nếu snapshot chỉ lấy MongoDB mà không đối soát với payment provider, recovery có thể tạo trạng thái **đã thu tiền nhưng không có đơn**.

### 4.3. Quyết định dữ liệu có thể dựng lại hay không

Một search index có thể rebuild được từ authoritative Orders; nhưng nếu event log chứa thông tin duy nhất mà Orders không lưu, analytics/read model có thể **không còn tái tạo được**.

### 4.4. Quy tắc thực tế

Dữ liệu “có thể dựng lại” chỉ nên được phân loại vậy nếu **nguồn dựng lại vẫn tồn tại, đủ lịch sử, có schema/code, có quyền truy cập và có thời gian/capacity để rebuild**.

---

## 5. Sáu nhóm tài sản dữ liệu thường có trong NoSQL

| Nhóm | Ví dụ | Mức độ bảo vệ cần đánh giá |
|---|---|---|
| **Authoritative transactional data** | Orders, accounts, stock, entitlements | RPO/RTO thường nghiêm; consistency và đối soát |
| **Reference/configuration data** | Catalog, price rules, feature flags | Cần version/rollback và thời điểm hiệu lực |
| **Derived projections/indexes** | Search, recommendations, reporting views | Có thể rebuild nếu source và pipeline đủ |
| **Ephemeral/operational state** | Cache, rate limits, sessions | Một số mất được; một số liên quan bảo mật/giao dịch |
| **Event/change history** | CDC, outbox, Kafka, audit logs | Có thể bắt buộc cho replay và legal evidence |
| **Recovery dependencies** | Schema, index DDL, KMS key, IAM, secret, backup manifest, IaC | Thiếu là không thể giải mã hoặc đưa service trở lại |

### 5.1. “Cache” không luôn là mất cũng được

Redis chỉ chứa product cache derived khác Redis là nguồn duy nhất của session, idempotency ledger, distributed locks hoặc queue. Phải phân loại **theo key namespace và semantics**, không theo tên sản phẩm.

### 5.2. Event log không tự là backup

Một event stream có retention giới hạn, không có snapshot base hoặc không giữ mọi state change cần thiết, không đủ để rebuild authoritative state.

### 5.3. Backup của application config cũng quan trọng

Có data files mà thiếu schema migrations, index definitions, collection validation rules, RBAC roles và KMS keys có thể khôi phục dữ liệu về mặt vật lý nhưng **không thể phục vụ đúng**.

### 5.4. Tách nghiệp vụ khỏi hạ tầng

Không nên chỉ ghi “node-03 cần backup”. Node có thể chứa nhiều shard/replica của nhiều datasets, mỗi dataset có owner và RPO khác nhau.

---

## 6. Lập bảng Data Protection Inventory

Ví dụ:

| Asset | Nguồn có thẩm quyền | Có thể rebuild? | Rủi ro mất | Dependency |
|---|---|---|---|---|
| Orders | MongoDB Orders collection | Không, trừ từ nguồn giao dịch đủ hơn | Mất đơn đã ACK | Payment, outbox |
| Inventory reservations | NoSQL reservation store | Có thể đối soát từng phần | Oversell/double release | Inventory authority |
| Customer consent | Account database | Không thể suy từ cache | Vi phạm quyền riêng tư | Audit/change log |
| Search index | Elasticsearch | Có, khi Orders + CDC đầy đủ | Search outage/stale results | Index mappings, backfill |
| Product cache | Redis | Có từ catalog | Source load spike | TTL/warm-up |
| Idempotency records | Redis hoặc DB | Không phải lúc nào | Thanh toán/đơn trùng | Request IDs, TTL policy |
| Audit events | Immutable event store | Không nếu là evidence duy nhất | Không truy vết được | Retention, integrity |
| PDF invoices | Object storage | Có thể có điều kiện | Thiếu chứng từ | Template, source fields |
| Schema/IaC | Version-controlled deployment | Có nếu bản dùng khôi phục được | App không khởi động | Artifact repository |
| Encryption keys | Managed KMS/HSM | Có lifecycle riêng, không được mất | Không giải mã backup | IAM/key policy |

### 6.1. Fields nên có trong inventory thực

- `assetId`, `businessOwner`, `technicalOwner`, `systemOfRecord`.
- Collection/table/keyspace/topic/bucket và region.
- Sensitivity và compliance constraints.
- Retention/deletion/legal hold policy.
- Data growth, logical/physical size.
- Change rate, peak mutations/s.
- Backup frequency, recoverable window, restore destination.
- RPO/RTO objectives theo scenario.
- Verification oracle và last successful drill.
- Dependencies và data-consistency boundary.
- Người được phép approve restore/cutover.

### 6.2. Không đưa PII vào inventory

Inventory cần metadata để tìm dữ liệu, không nên chứa bản sao raw addresses, tokens hoặc health records.

### 6.3. Owner là bắt buộc

Nếu không ai có quyền xác nhận recovered Orders có đúng hay không, việc restore thành công kỹ thuật khó trở thành phục hồi nghiệp vụ.

---

## 7. Dữ liệu gốc và dữ liệu dẫn xuất: ví dụ cụ thể

### 7.1. Authoritative source

Nếu `orders` là nguồn có thẩm quyền về trạng thái đơn, những read models phải **được kiểm soát hoặc rebuild** từ Orders và committed change history.

### 7.2. Materialized view

`orders_by_customer` có thể giữ dữ liệu nhân bản theo query pattern. Nếu mất view nhưng source+replay đầy đủ, RPO logical có thể gần 0 về dữ liệu nghiệp vụ, **nhưng RTO để rebuild view vẫn có thể vài giờ**.

### 7.3. Cache

Mất cache derived không nhất thiết làm mất Orders, nhưng nếu tỷ lệ hit trước đó là 95%, source có thể phải nhận khối lượng read tăng mạnh khi cache trống. RTO ứng dụng cần tính giai đoạn cold start.

### 7.4. Offline client

Ứng dụng mobile có thể giữ changes offline chưa sync. Backup server không thể khôi phục những writes **chưa từng tới server**. Nêu rõ phạm vi RPO chỉ tính writes đã đạt điểm chấp nhận/ACK theo contract.

### 7.5. External provider

Payment provider, email gateway và shipping partner là các hệ ngoài ranh giới database backup. Recovery cần đối soát identifiers và outcomes, không chỉ replay event đã lưu.

---

## 8. Các loại sự cố quyết định backup strategy

| Sự cố | Dữ liệu bị đe dọa | Giải pháp/kiểm thử cần xét |
|---|---|---|
| Crash một process | Unflushed/in-flight state | WAL/journal recovery, retries |
| Mất một disk/node | Replica copy, local data | Failover, replica health, backup |
| Hỏng đồng thời nhiều nodes | Quorum/replica groups | Off-cluster backups, alternate site |
| Mất Availability Zone | Nhiều failure domain cùng lúc | Multi-AZ redundancy |
| Mất cả region | Primary region và local backups | Cross-region recovery, DNS, IAM, keys |
| Operator chạy DELETE sai | Dữ liệu đã delete và replication có thể lan | PITR, logical recovery, approval |
| Bug ứng dụng ghi sai hàng triệu rows | Logical corruption | Historical restore + data reconciliation |
| Ransomware/credentials bị lộ | Source và backups có thể cùng bị phá | Immutable/offline copies, separation of duties |
| Replication bơm dữ liệu sai | Replica không còn là bản sạch | Historical recovery points |
| Index mapping sai | Query/read model | Restore/reindex từ source |
| Schema migration lỗi | Structure + data compatibility | Schema versions, reversible migrations |
| CDC connector bỏ lỡ log | Downstream projections bị sai | Replay horizon, resnapshot |
| Khóa mã hóa bị mất | Backups không giải mã được | Key custody/rotation/recovery |
| Xóa theo TTL nhầm | Data quá hạn bị xóa vật lý | PITR/restore nếu retention cho phép |
| Restore backup cũ | Deleted/expired data hồi sinh | Deletion ledger/revalidation |
| Cloud account bị khóa | Storage còn nhưng không truy cập | Separate credentials, DR account |

### 8.1. RPO/RTO của node crash khác region loss

Một cluster đa replica có thể tự phục hồi sau một node failure trong vài chục giây, không cần restore snapshot. Nhưng mất toàn region có thể yêu cầu cấp cluster mới, chuyển DNS, khôi phục KMS/backup và mất hàng giờ.

### 8.2. Replication không bảo vệ lỗi logic

Nếu một ứng dụng chạy delete sai và replication truyền delete sang tất cả replicas, bản sao mới nhất cũng sai. Cần **lịch sử có thể phục hồi** chứ không chỉ nhiều replicas giống nhau.

### 8.3. Backup không đảm bảo RTO

Có một bản snapshot tốt nhưng cần 18 giờ tải từ archive và rebuild indexes thì không đáp ứng RTO 1 giờ.

---

## 9. RPO mục tiêu: xác định theo hậu quả của dữ liệu bị mất

Business impact analysis (BIA) nên hỏi:

- Nếu mất một đơn hàng đã được xác nhận, mất bao nhiêu tiền/công?
- Có thể tái tạo từ payment records hoặc email không?
- Có cần liên hệ người dùng xác nhận lại?
- Một thay đổi quyền truy cập bị mất có tạo lỗ hổng bảo mật không?
- Có khả năng **ghi trùng** khi khách retry sau restore?
- Nếu mất nhật ký kiểm toán 15 phút, có vi phạm nghĩa vụ nào không?
- Có thể đối soát tự động, hay cần manual review?
- Mức tăng của sai lệch theo thời gian là tuyến tính hay có tính hệ thống?

### 9.1. Bảng phân tầng minh họa

| Dữ liệu/quy trình | RPO mục tiêu minh họa | Giải thích |
|---|---:|---|
| Thanh toán đã xác nhận | Gần 0 hoặc yêu cầu không mất committed state | Mất hoặc duplicate gây rủi ro tài chính |
| Đặt hàng đã ACK | 1 phút | Có thể mất đơn đã hứa với khách |
| User permission revocation | Gần 0 và phải fail closed | Phục hồi quyền cũ là sự cố bảo mật |
| Catalog có nguồn ERP | 30 phút | Có thể đồng bộ lại nếu ERP còn |
| Search projection | Rebuild từ source, không mất business facts | RTO tìm kiếm vẫn phải rõ |
| Derived recommendation cache | Không đặt RPO dữ liệu gốc | Recompute, nhưng capacity warm-up cần |
| Audit logs | Theo retention/compliance, có thể rất nghiêm | Bằng chứng không tái tạo dễ dàng |

Các giá trị là **bài tập thiết kế**, không phải mức chuẩn khuyến nghị cho mọi doanh nghiệp.

### 9.2. Trường hợp RPO bằng 0

Phát biểu “RPO = 0” cần làm rõ phạm vi:

- Mọi transaction đã được ACK theo contract nào?
- Những failure domains nào được bao phủ?
- Replication synchronous/quorum hay asynchronous?
- Đối với corruption và malicious delete thì sao?
- Backup/log phục hồi có được giữ ở nơi độc lập không?
- Có kiểm được cutover không làm mất acknowledged writes?

**Async replica có thể lag, vì vậy không đủ để mặc định hứa RPO 0 khi mất primary region.** RPO 0 cũng không chứng minh tránh được lỗi logic replicated sang mọi bản sao.

---

## 10. RTO mục tiêu: xác định khi nào nghiệp vụ hoạt động trở lại

Không phải mọi ứng dụng đều cần trở về **100% tính năng** ngay.

### 10.1. Phân tầng phục hồi

~~~text
Tier 0: Đọc dữ liệu quan trọng, chặn writes không an toàn
Tier 1: Nhận giao dịch mới, đồng bộ với payment/inventory
Tier 2: Search, reporting, recommendation hoạt động
Tier 3: Batch analytics và các job nền bắt kịp
~~~

Một RTO cần ghi **mốc serving nào**:

- API health green?
- Đọc được order details?
- Có thể nhận đơn mới?
- Có thể cấp/revoke quyền?
- Search index đầy đủ?
- Hệ đạt p99/throughput SLO bình thường?
- All historical analytics restored?

### 10.2. RTO có thể tách chức năng

Ví dụ mục tiêu:

~~~text
Critical order lookup:          30 phút
New order placement:            60 phút
Search/recommendations:          4 giờ
Batch analytics historical:     24 giờ
~~~

### 10.3. RTO không bắt đầu khi DBA gõ lệnh

Nếu cam kết dựa trên sự cố bắt đầu, phải gồm detection, triage, decision, provisioning, transfer, validation và traffic switch. Mốc khởi đầu cần nêu trong contract để không báo cáo RTO “đẹp” một cách sai lệch.

### 10.4. Thời gian cần con người phê duyệt

Quyết định restore nhầm có thể phá data mới. Approval có thể cần thiết, nhưng phải đo thời gian này vào RTO và chuẩn bị on-call/runbook để không làm mục tiêu bất khả thi.

---

## 11. Công thức ước lượng RPO từ backup và log

Giả sử:

- Full/incremental snapshot tạo recoverable point mỗi \(T_b\) phút.
- Không có log/PITR giữ các writes sau điểm snapshot.
- Sự cố xảy ra bất kỳ lúc nào trong chu kỳ.

Trong mô hình lý tưởng, **worst-case time gap** có thể gần \(T_b\), chưa tính snapshot consistency, backup lag và upload/verification delay.

### 11.1. Ví dụ backup mỗi 30 phút

~~~text
09:00 Snapshot recoverable
09:30 Snapshot recoverable
09:59 Source failure
~~~

Nếu snapshot 09:30 là bản mới nhất khả dụng, recovery point gap gần 29 phút. Thực tế có thể lớn hơn nếu bản 09:30 chưa copy/verify thành công và chỉ có 09:00.

### 11.2. PITR thay đổi bài toán

Nếu có baseline snapshot + **dòng transaction/change log liên tục và bền vững**, có thể replay tới một recovery position gần thời điểm sự cố, với điều kiện:

- Log chứa đủ thông tin cần thiết.
- Không có gap hoặc corruption.
- Backup và log cùng một lineage/cluster state tương thích.
- Có consistency/commit cut rõ.
- Log ở failure domain còn sống.
- Công cụ restore hỗ trợ phục hồi đến target time/position.

### 11.3. Replication lag ảnh hưởng RPO failover

Nếu region B nhận replication bất đồng bộ và đang sau A 40 giây, mất A có thể khiến B không chứa phần committed changes cuối. Mức mất phụ thuộc ACK contract và vị trí dữ liệu đã durable ở B, không chỉ một chỉ số “lag trung bình”.

### 11.4. Log retention không phải vô hạn

Nếu connector/storage log đã cleanup khoảng cần replay, không thể giả định PITR vẫn khôi phục tới mọi thời điểm. Phải đo recoverable window thực tế.

---

## 12. Ước lượng mất dữ liệu bằng mutation rate

Giả sử ứng dụng ghi trung bình \(r\) **committed events/s**; RPO gap thực tế là \(T\) giây.

Số sự kiện có nguy cơ mất gần đúng:

\[
N_{\text{at risk}}\approx rT.
\]

### 12.1. Ví dụ

~~~text
Số đơn được commit:          500 đơn/s
Recovery point gap:           90 s
~~~

\[
N\approx 500\times90=45\,000\text{ đơn}.
\]

45.000 đơn là con số có thể gây hậu quả lớn dù “RPO chỉ 90 giây”.

### 12.2. Dung lượng dữ liệu

Nếu writes tạo khoảng 6 MiB/s logical changed bytes:

\[
D_{\text{at risk}}\approx 6\times90=540\text{ MiB}.
\]

Nhưng bytes nhỏ chưa chắc impact nhỏ: **một quyền admin bị xóa rồi hồi sinh** có thể nghiêm trọng hơn 540 MiB log không quan trọng.

### 12.3. Không giả định arrival rate đều

Sự cố trong giờ peak có thể có 5.000 đơn/s, không phải 500. BIA cần tính peak rate, đặc biệt nếu RPO mục tiêu là cận trên.

### 12.4. Số event không đồng nghĩa số giao dịch độc lập

Một order workflow có thể phát nhiều events, hoặc một event chứa nhiều operations. Muốn tính tác động business, cần chọn đơn vị đúng: order/payment/reservation/permission change.

### 12.5. Phân biệt ACKed và in-flight

Dữ liệu client chưa nhận ACK nhưng source có thể đã commit. Khi recovery, phải xử lý **unknown outcome** và idempotency chứ không chỉ đếm lost acknowledged transactions.

---

## 13. RTO là tổng chuỗi công việc, không chỉ tốc độ restore

Một mô hình:

\[
T_{\text{recover}}
=
T_{\text{detect}}
+T_{\text{triage}}
+T_{\text{approve}}
+T_{\text{provision}}
+T_{\text{transfer}}
+T_{\text{restore}}
+T_{\text{replay}}
+T_{\text{validate}}
+T_{\text{cutover}}.
\]

Đây là **mô hình tuần tự đơn giản**. Một số bước có thể song song nhưng phụ thuộc và critical path phải được tính rõ.

### 13.1. Ví dụ RTO 60 phút

| Pha | Ước lượng |
|---|---:|
| Phát hiện và phân loại | 5 phút |
| Quyết định phương án recovery | 7 phút |
| Chuẩn bị môi trường/credentials/keys | 8 phút |
| Tải backup và restore | 22 phút |
| Replay logs/rebuild metadata | 8 phút |
| Kiểm chứng data và consistency | 6 phút |
| Cutover, warm-up, smoke test | 4 phút |
| **Tổng** | **60 phút** |

Nếu một pha tăng 20 phút, mục tiêu không còn được đáp ứng dù câu lệnh restore chạy rất nhanh.

### 13.2. Phần validation không được bỏ qua

Một database process báo Ready nhưng dữ liệu đã restore lệch payment provider, không có indexes hoặc không được cấp KMS access thì hệ **chưa phục hồi nghiệp vụ**.

### 13.3. RTO phải được đo ở kích thước thật

Restore 1 GiB trong test không chứng minh restore 20 TiB sẽ xong trong cùng khoảng. Throughput, network, parallelism, indexes, replay logs, dedup và kiểm tra dữ liệu đều scale khác nhau.

### 13.4. Warm-up và goodput

Service mở traffic nhưng cache lạnh khiến source bị quá tải có thể chưa đạt RTO theo business SLO. Cần xác định rõ “serving” bao gồm throughput và error budget đến mức nào.

---

## 14. Tính thời gian truyền dữ liệu khi restore

Giả sử cần tải \(S\) TiB backup từ object storage, thông lượng **effective** \(B\) MiB/s.

\[
T_{\text{transfer}}
\approx
\frac{S\times1024\times1024}{B}
\quad\text{giây, với }S\text{ tính bằng TiB}.
\]

### 14.1. Ví dụ

Backup 2 TiB, effective throughput 400 MiB/s:

\[
T
=\frac{2\times1024\times1024}{400}
\approx5243\text{ s}
\approx87.4\text{ phút}.
\]

**Riêng truyền dữ liệu đã vượt RTO 60 phút**, chưa tính restore/replay/validation. Nếu source/destination có giới hạn IOPS, băng thông thực có thể thấp hơn.

### 14.2. Dữ liệu nén và kích thước truyền

Nếu backup được nén tốt, bytes truyền nhỏ hơn logical storage, nhưng CPU giải nén và disk rewrite vẫn cần tính. Không ước lượng từ tên file hay dung lượng uncompressed mà không đo.

### 14.3. Parallelism có giới hạn

Tăng số streams không tự tăng tổng throughput nếu network quota/object-store limits/volume writes/CPU đã bão hòa.

### 14.4. Cold/archive tier có retrieval delay

Một backup có lưu lâu và chi phí thấp nhưng cần hàng giờ để đưa ra khỏi archive có thể phù hợp retention/compliance nhưng không phù hợp RTO ngắn.

---

## 15. High availability, replication và backup không thay nhau

| Cơ chế | Mục tiêu chính | Không tự giải quyết |
|---|---|---|
| **Replication** | Có bản sao phục vụ và khả năng failover | Xóa nhầm/bug có thể replicate |
| **Quorum/consensus** | Điều phối xác nhận writes/roles theo protocol | Dữ liệu lịch sử tốt sau logical corruption |
| **Automatic failover** | Giảm gián đoạn khi member mất | RPO 0 nếu replication bất đồng bộ |
| **Snapshot backup** | Giữ recovery point trong quá khứ | Giữ mọi write sau snapshot |
| **Incremental backup** | Giảm dung lượng/khối lượng copy thay đổi | Restore nếu thiếu baseline/chain |
| **PITR** | Phục hồi gần một thời điểm/position đã hỗ trợ | Gaps log hoặc không nhất quán cross-system |
| **Cross-region backup** | Sống sót khi region mất | Có sẵn để phục vụ ngay |
| **Immutable/offline backup** | Giảm rủi ro backup bị sửa/xóa | Restore nhanh nếu quá chậm |
| **Archive** | Giữ lịch sử lâu hoặc theo policy | RTO ngắn cho hot data |
| **CDC/event replay** | Dựng lại downstream/updates | Dữ liệu đã ngoài retention hoặc thiếu history |

### 15.1. Một replica khỏe không phải recovery point lịch sử

Nếu một ứng dụng ghi sai `balance=0` và replication phổ biến ghi ngay sang tất cả replicas, failover không đưa trạng thái trước lỗi trở lại.

### 15.2. Backup đã tạo không đồng nghĩa backup khôi phục được

Cần kiểm file, manifest, chain, KMS, version compatibility, network access và actual restore tests.

### 15.3. HA và DR là hai mục tiêu khác

High availability cho failure cục bộ có thể đạt RTO vài giây/phút. Disaster recovery của cả region có thể cần RTO lâu hơn. Cùng một service nên có các target và thiết kế riêng.

---

## 16. Failure domain: backup phải sống sót đúng sự cố

Một failure domain có thể là:

- Process/container.
- Host/VM.
- Disk hoặc storage volume.
- Rack/AZ/datacenter.
- Region.
- Cloud account/subscription.
- IAM/KMS control plane.
- Người quản trị có quyền xóa cả source và backup.

### 16.1. Backup cùng node không bảo vệ mất node

Một thư mục `backup/` trên chính volume nguồn có thể giúp rollback lỗi ứng dụng nhỏ nhưng không bảo vệ khi disk hỏng.

### 16.2. Multi-AZ replica không tự bảo vệ account compromise

Nếu cùng IAM principal có quyền xóa toàn bộ snapshots và backup repositories, một lỗi/attack có thể phá cả các AZ.

### 16.3. Cross-region không tự đủ

Backup nằm ở region khác nhưng KMS key chỉ có tại region đã mất hoặc quyền restore phụ thuộc một account bị khóa có thể khiến RTO thất bại.

### 16.4. Nguyên tắc nhiều bản sao độc lập

Một chiến lược kiểu **3-2-1** hoặc các biến thể với immutable/offline copy có thể là điểm xuất phát. Điều quan trọng hơn số lượng là các bản sao phải vượt qua **failure domain đã mô hình hóa**, có khóa/định danh độc lập và được thử restore.

---

## 17. Nhất quán của recovery point: không chỉ “cùng timestamp”

Một hệ NoSQL phân tán có nhiều nodes/shards và writes đang diễn ra.

~~~text
Shard A checkpoint: 10:00:00
Shard B checkpoint: 10:00:05
Shard C checkpoint: 09:59:53
~~~

Nếu lấy ba snapshots tùy ý rồi gộp, một giao dịch hoặc workflow trải nhiều shards có thể chỉ phục hồi **một phần**.

### 17.1. Crash-consistent và application-consistent

- **Crash-consistent:** trạng thái tương tự hệ vừa mất điện, có log recovery phù hợp.
- **Application-consistent:** có thêm phối hợp để đảm bảo các invariants/transactions nghiệp vụ trong boundary xác định.

Tên/semantics chính xác tùy engine và công cụ backup.

### 17.2. Consistent snapshot của một node khác cluster-consistent

Snapshot của một replica có thể hợp lệ về mặt local recovery nhưng chưa bao phủ toàn bộ token ranges/shards hoặc log positions.

### 17.3. Restore toàn cluster cần cut nhất quán

Một số hệ có phương thức point-in-time recovery ở cluster scope; một số yêu cầu orchestration snapshot + commit/log positions; một số chỉ hỗ trợ table/bucket restore riêng.

### 17.4. Distributed business workflow

Ngay cả khi MongoDB data snapshot nhất quán, payment external provider hoặc Kafka consumer may have advanced. Recovery cần một protocol reconciliation cho tác vụ cross-system.

### 17.5. Không hứa “mọi hệ cùng một thời điểm” nếu không có cơ chế

Timestamp UTC gần nhau không tự tạo atomic transaction cut qua MongoDB, Redis, Kafka, object storage và payment provider.

---

## 18. WAL, oplog, CDC và backup log chain

Giả sử:

~~~text
Snapshot S at position L100
Log records L101 ... L200 available
Failure after L200
~~~

Khôi phục có thể là:

1. Restore snapshot `S`.
2. Xác minh đúng cluster lineage/schema.
3. Replay `L101..L200` **liền mạch** theo engine protocol.
4. Dừng tại target commit point.
5. Kiểm tính đúng đắn và cutover.

### 18.1. Log continuity

Nếu thiếu `L156` và engine cần nó, không được tự bỏ qua rồi tuyên bố đã recovery tới `L200`. Cần phát hiện gap/checksum/sequence inconsistency.

### 18.2. Backup chain

Incremental snapshots có thể phụ thuộc full baseline và các đoạn thay đổi. Một file incremental “backup success” không còn dùng được nếu baseline bị xóa hoặc không có khóa giải mã.

### 18.3. Oplog/CDC retention

Một connector offline vượt source-log horizon có thể phải resnapshot. Backup PITR và CDC streams có cơ chế giữ log/positions khác nhau; không đồng nhất chúng.

### 18.4. Commit position khác wall-clock

Một vị trí log/epoch/token/sequence giúp định danh trạng thái theo engine chính xác hơn đồng hồ tường trong nhiều tình huống. Không tự parse opaque resume token để suy timestamp khi driver không cam kết.

### 18.5. Version compatibility

Backup được tạo bằng engine version/schema khác có thể cần đường upgrade/restore được hỗ trợ. Không mặc định một snapshot dùng được trên bất kỳ release nào.

---

## 19. Khôi phục dữ liệu có thể gây “hồi sinh” delete

Một customer xóa dữ liệu cá nhân lúc 10:30. Backup được tạo lúc 10:00. Sau region incident, restore snapshot lúc 10:00.

Khi đó một document đáng lẽ đã xóa lúc 10:30 có thể xuất hiện trở lại.

### 19.1. RPO chỉ mô tả thời gian, không bao quát mọi điều kiện bảo mật

Nếu chính sách đòi dữ liệu đã được xóa không được phục vụ lại, **restore snapshot cũ phải có deletion reconciliation**.

### 19.2. Deletion ledger

Một cơ chế có thể lưu delete requests/versions tối thiểu, đủ tin cậy để áp lại những xóa xảy ra sau snapshot, theo policy dữ liệu nhạy cảm. Ledger phải được bảo vệ, không chứa payload thừa và có recovery RPO/RTO riêng.

### 19.3. Cache/index cũng cần đồng bộ sau restore

Một index xây từ snapshot cũ có thể chứa stale entities; cần rebuild hoặc reconcile với authoritative source và deletion events trước khi mở traffic.

### 19.4. Mất log deletion thì sao?

Nếu delete history đã hết retention, không được giả định replay đủ. Cần authoritative reconciliation/quarantine và quy trình xử lý riêng.

### 19.5. Legal hold và retention

Yêu cầu xóa dữ liệu, bắt buộc lưu trữ chứng từ hoặc legal hold thay đổi theo loại dữ liệu và pháp luật áp dụng. Cần privacy/legal review thay vì một TTL chung cho mọi assets.

---

## 20. Mối quan hệ giữa RPO và “đã ACK”

Trước khi hứa không mất committed data, phải biết engine xác nhận một write khi nào.

~~~text
Client sends write
    |
    v
Node receives
    |
    v
WAL/replicas/consensus commit per chosen settings
    |
    v
Client gets ACK
~~~

### 20.1. ACK contract

ACK có thể đến sau một local memory write, local durable write, nhiều replicas, majority commit hoặc một protocol khác, tùy engine/config. Những mức này **không tương đương**.

### 20.2. RPO 0 cần phạm vi đúng

Nếu một node ACK trước khi write durable ở failure domain còn sống, mất node có thể làm mất write dù API đã trả success.

### 20.3. Unknown outcome

Nếu client timeout trước ACK nhưng write đã commit, recovery có thể chứa write đó. Client không được tự tạo operation trùng vì suy thất bại.

### 20.4. Idempotency và reconciliation

Trong thanh toán/đặt hàng, dùng operation IDs/idempotency keys và đối soát source of truth để xử lý retry/replay, không suy dữ liệu thiếu chỉ từ client timeout.

---

## 21. RPO/RTO của cache và ephemeral state

Câu “Redis có thể mất hết cũng được” cần được kiểm.

### 21.1. Derived cache

Nếu Redis lưu product pages có thể lấy lại từ MongoDB, RPO của **business data** không phụ thuộc Redis. Tuy nhiên mất cache tạo cold-start load và có thể làm RTO API tăng.

### 21.2. Session

Mất session có thể buộc đăng nhập lại. Đây có thể là acceptable product impact nhưng phải được ghi trong RTO/UX policy.

### 21.3. Rate limit và revocation

Nếu một security decision chỉ sống trong Redis và mất khi restore, có thể mở lại quyền đã revoke hoặc đặt sai limits. Khi đó nó không là ephemeral state vô hại.

### 21.4. Idempotency ledger

Nếu key bảo vệ `charge(paymentId)` mất, retry có thể gây double charge. Cần backing authority/retention phù hợp, không chỉ snapshot Redis tùy hứng.

### 21.5. Queue/workflow state

Một queue trong Redis nếu là nguồn duy nhất của pending jobs có RPO riêng. Nếu jobs được lưu bền ở source/outbox và có thể rehydrate, danh mục dữ liệu cần ghi khả năng rebuild thực tế.

---

## 22. Metadata và cấu hình cũng thuộc backup boundary

Phục hồi data bytes nhưng thiếu:

- Schema definitions/validation.
- Index definitions.
- Partition keys/sharding configuration.
- User/role/ACL mappings.
- Certificates, secrets references và IAM policies.
- KMS keys/key versions/rotation records.
- Infrastructure-as-Code và container artifacts.
- CDC mappings, stream offsets, outbox processors.
- Backup manifest và checksum.
- DNS, service endpoints và runbook credentials.
- Restore tooling/driver versions.
- Data migration history.
- Monitoring/alert/incident configuration.

có thể làm dịch vụ không chạy hoặc chạy sai.

### 22.1. Không nhất thiết “backup mọi thứ thành một file”

Một số cấu hình đã nằm trong Git/IaC/artifact registry, một số nằm trong managed KMS/IAM và một số metadata là database-native. Điều cần bảo vệ là **khả năng lấy lại đúng phiên bản và quyền truy cập**, không phải sao chép private key bừa bãi.

### 22.2. Encryption keys là phụ thuộc sống còn

Một backup mã hóa không khôi phục được nếu key bị xóa, revoke nhầm hoặc không có quyền `decrypt` trong DR account/region. Cần test quyền/khoá trên môi trường DR và chính sách rotation.

### 22.3. Secrets phải được bảo vệ riêng

Không xuất credentials/plaintext private keys vào zip backup thiếu kiểm soát. Dùng secrets manager/identity policy và audit.

---

## 23. MongoDB: snapshot, oplog và PITR trong recovery planning

MongoDB có replica sets/sharding, oplog, change streams và nhiều phương án backup tùy cách vận hành (self-hosted, managed service, vendor tooling).

### 23.1. Replica không phải historical backup

Một replica set giúp failover và có thể duy trì nhiều bản dữ liệu, nhưng delete sai có thể replicate tới mọi members.

### 23.2. Snapshot/copy cần nhất quán

Không copy tùy tiện những tệp data đang thay đổi rồi giả định là snapshot hợp lệ. Dùng cơ chế backup/storage snapshot được MongoDB và triển khai hỗ trợ, với logic nhất quán và log coverage phù hợp.

### 23.3. PITR cần backup + oplog history

Để phục hồi một điểm trong quá khứ có thể cần baseline snapshot và oplog/continuous backup theo giải pháp cung cấp. Oplog retention của replica set **không tự bảo đảm** PITR vô hạn.

### 23.4. Sharded cluster

Consistency của snapshot trên nhiều shards/config metadata phải được giải pháp backup hỗ trợ ở cluster scope. Snapshot từng shard vào thời điểm tùy ý không tự đồng nghĩa recoverable cluster-consistent point.

### 23.5. Indexes và `mongos`

Sau restore cần xác nhận index definitions, sharding metadata, replica set membership, cluster identity, authentication/TLS và driver routing. Không chỉ kiểm document count.

### 23.6. RPO/RTO thực tế

Đo đến recovery point nào có thể replay, thời gian restore collection/cluster, thời gian election/replica sync và thời gian ứng dụng chạy canary. Managed provider có thể đặt limits/feature options riêng; cần đối chiếu deployment/version.

---

## 24. Cassandra: snapshot, SSTables và repair horizon

Cassandra dùng SSTables/commit logs và replication theo token/partition ranges.

### 24.1. Snapshot không bao phủ mọi dữ liệu theo một cách đơn giản

Một `nodetool snapshot` tạo snapshot theo semantics của Cassandra; để backup hoàn chỉnh cần phối hợp **tất cả token ranges/replicas cần thiết**, schema, metadata và đồng bộ trạng thái ứng dụng nếu muốn một recovery point có scope rộng.

### 24.2. Incremental backups

Tùy cấu hình, incremental backup có thể lưu các SSTables mới; nhưng nó không tự tương đương **mọi mutation WAL** cần PITR tới bất kỳ giây nào.

### 24.3. Commit log và replay

Muốn RPO nhỏ hơn interval snapshot, cần giải pháp giữ/đọc replayable change history phù hợp và được thử thực tế. Không tự tuyên bố snapshot hàng ngày + replication RF=3 có RPO 0 cho logical corruption.

### 24.4. Tombstone và zombie data

Replica offline quá horizon an toàn, tombstones đã bị garbage-collected trong khi replica giữ dữ liệu cũ, có thể tạo zombie data. Restore/rejoin phải theo **repair/reseed** policy, không cho node quá cũ nhập cluster tùy tiện.

### 24.5. RTO của bootstrap/streaming

Một node mới có thể cần tải dữ liệu lớn qua mạng, compact/repair và warm cache. `nodetool status UN` chưa đủ để tuyên bố toàn bộ queries đạt SLO.

### 24.6. Scope theo keyspace/table

Inventory phải ghi tables, replication strategies, compaction/TTL, indexes, role/permissions và dependency data models. Không khôi phục mỗi một table rồi tuyên bố các denormalized copies đã nhất quán.

---

## 25. DynamoDB: managed backup/PITR và khôi phục table

Amazon DynamoDB cung cấp các tính năng backup/restore managed, gồm on-demand backup và point-in-time recovery theo khả năng/config của dịch vụ.

### 25.1. Không suy table `ACTIVE` là đang có PITR

PITR phải được bật/cấu hình phù hợp; recovery window và earliest/latest restorable time cần lấy từ service API/console tại thời điểm vận hành.

### 25.2. PITR có recovery window hữu hạn

Khả năng chọn point-in-time nằm trong cửa sổ hỗ trợ của dịch vụ và trạng thái backup. Không tự cam kết khôi phục 6 tháng trước nếu điểm cần thiết đã quá retention.

### 25.3. Restore thường tạo một table đích mới

Trong các đường restore DynamoDB phổ biến, dữ liệu được khôi phục **sang table mới**, không âm thầm rewind table source đang hoạt động. RTO cần tính:

- Tạo/khôi phục table.
- Thiết lập/kiểm tra GSIs và các tùy chọn được/không được phục hồi tự động.
- IAM/capacity/autoscaling, streams/TTL và tags/settings theo contract.
- CDC/consumer reconfiguration.
- Cutover applications.
- Dữ liệu ghi vào source kể từ selected recovery point.

### 25.4. Global tables không tương đương PITR

Cross-region replication có thể lan lỗi logic; backup lịch sử là cơ chế khác. Khi DR cần xác nhận replicas và restore ở region đích theo tính năng/mode hỗ trợ.

### 25.5. DynamoDB Streams

Streams có retention ngắn theo service contract, nên không coi là historical backup vô hạn. Nếu rebuilding downstream vượt thời gian giữ, cần backup/export/source resnapshot.

### 25.6. RPO/RTO và service quotas

Managed restore có tốc độ/quotas, table size, index build, config và read traffic warm-up ảnh hưởng RTO. Không dùng kết quả restore một bảng nhỏ để hứa thời gian giống hệt cho bảng vài TB.

---

## 26. Redis: RDB, AOF và câu hỏi “cache có mất được không?”

### 26.1. RDB snapshot

RDB cho recovery point theo lần snapshot thành công, tùy chính sách và storage persistence. Giữa snapshots có thể mất writes nếu crash mà không có cơ chế khác.

### 26.2. AOF

AOF ghi lại các thao tác thay đổi và có fsync policies; trade-off giữa throughput, latency và lượng dữ liệu có thể mất khi host crash/power loss. Không hứa một con số RPO cố định mà không kiểm policy và failure model.

### 26.3. Replication async

Một primary ACK write rồi mất trước khi replica nhận mutation có thể làm write biến mất sau failover. `WAIT` hoặc cơ chế xác nhận replicas ở Redis không tự chuyển thành một hệ consensus với guaranteed durable commit.

### 26.4. Derived cache

Nếu dữ liệu là cache dễ tái tạo, có thể chọn không backup Redis và đầu tư vào **throttled warm-up**, single-flight và bảo vệ source DB.

### 26.5. Stateful Redis

Nếu Redis giữ session duy nhất, quota, lock, queue hoặc idempotency ledger, phải đặt RPO/RTO tương ứng. Redis persistence/replication RPO có thể không đủ cho financial side effects; cân nhắc đưa authority vào durable store.

### 26.6. Khởi động lạnh

RTO không chỉ là Redis process `PONG`: cache hit rate, source DB load, cold miss rate và business API p99 có thể vẫn dưới yêu cầu.

---

## 27. Elasticsearch/OpenSearch: snapshot index khác backup dữ liệu gốc

Elasticsearch/OpenSearch thường lưu **read-optimized/index data**. Nếu đó là projection từ NoSQL source, cần biết có thể rebuild từ source và event history không.

### 27.1. Snapshot repository

Index snapshots qua repository/managed feature có semantics theo shards/segments và consistency riêng. Không copy file data của live node làm backup thay cho cơ chế được hỗ trợ.

### 27.2. Index mappings/templates

Để khôi phục search service, cần index settings/mappings, aliases, pipelines, templates, security configuration và compatibility; không chỉ document bytes.

### 27.3. Search RTO

Reindex 10 TB có thể tốn nhiều giờ/ngày tùy cluster. Dù toàn bộ business data còn trong MongoDB, search feature RTO có thể không đạt nếu không có snapshot của search index.

### 27.4. Replica shards không là backup

Một delete/mapping error trên primary có thể được phản ánh sang replicas. Snapshot và versioned templates giải quyết vấn đề khác.

### 27.5. Recovery và cutover

Có thể restore index đích mới, kiểm count/mapping/query smoke tests rồi chuyển alias có kiểm soát, thay vì overwrite index đang nhận writes. Cần phối hợp tail CDC để tránh mất mutations trong quá trình rebuild.

### 27.6. Không gán global transaction consistency cho search snapshot

Nếu source NoSQL vẫn đang ghi, search snapshot có thể phản ánh một projection lag. Cần biết watermark/CDC position để tính dữ liệu còn thiếu sau restore.

---

## 28. Những hệ khác và bài học xuyên suốt

### 28.1. Couchbase

Bảo vệ buckets/collections, data/index services, replication/XDCR settings, vBuckets và backup metadata theo khả năng của phiên bản/công cụ. Không coi XDCR replica ở region khác là full historical protection chống operator error.

### 28.2. Neo4j/graph

Cần backups phù hợp graph store và transaction logs, schema/indexes, constraints, security và causal cluster state. Phục hồi graph một phần có thể phá relationship invariants, cần application-level validation.

### 28.3. Embedded RocksDB

Khi Java app/stream processor dùng RocksDB state store, snapshot/checkpoint cần phù hợp với input stream offsets và changelog, không chỉ copy directory live. Local disk loss có thể rebuild được nếu changelog hợp lệ và đủ retention.

### 28.4. Object storage

Bảo vệ object versions, bucket permissions/lifecycle, encryption keys và delete markers theo business contract; nếu invoice PDF là nguồn duy nhất của chứng từ, không gọi nó là cache.

### 28.5. Một kết luận chung

**Backup mechanism chỉ bảo vệ được asset nằm trong coverage thực tế**, và restore chỉ đúng khi khôi phục cùng những metadata/versions/keys liên quan.

---

## 29. Recovery của nhiều nguồn dữ liệu: không thể ghép snapshot tùy ý

Ví dụ:

~~~text
Orders DB:      snapshot at 10:00
Inventory DB:   snapshot at 10:07
Kafka offset:   consumer committed through 10:12
Search index:   snapshot at 09:55
```

Nếu bật tất cả và nhận đơn mới ngay, có thể:

- Có order nhưng reservation hết hạn/không còn tồn tại.
- Có inventory reserved nhưng không có order.
- Kafka consumer tin đã xử lý event mà database restore chưa có record liên quan.
- Search chứa trạng thái cũ.
- Payment đã capture nhưng order DB lùi.

### 29.1. Tìm authoritative boundary

Định nghĩa source of truth cho từng quyết định. Nếu payment provider có transaction IDs, nó phải tham gia reconciliation cho payments sau restore.

### 29.2. Chọn chiến lược

- Snapshot/cutover phối hợp theo nguồn có hỗ trợ.
- Transactional outbox và replay từ checkpoint nhất quán.
- Idempotent event handlers.
- Rebuild projections từ authoritative state.
- Reconcile ledger/versions khi không có global snapshot.

### 29.3. Không dùng Kafka offset như global database timestamp

Offset có thứ tự trong partition, không là thứ tự toàn cục cho tất cả partitions/systems. Recovery cần mapping checkpoint thực tế.

### 29.4. Chỉ mở ứng dụng sau safety gates

Nếu source restored nhưng downstream vẫn trỏ tới snapshot cũ, có thể tạm vô hiệu các thao tác tạo side effects cho tới khi reconciliation hoàn tất.

---

## 30. RPO và RTO theo phân vùng, shard và tenant

Một cluster 100 shards không nhất thiết phục hồi mọi shard tới cùng điểm.

### 30.1. RPO per-shard

~~~text
Shard A recoverable through 10:10:00
Shard B recoverable through 10:09:55
Shard C recoverable through 10:08:20
```

Nếu yêu cầu dữ liệu **toàn bộ cluster** trong một consistent cut, điểm khôi phục chung có thể bị giới hạn bởi shard chậm nhất và khả năng transaction coordination. Không suy một timestamp gần nhất của A là recovery point toàn cluster.

### 30.2. RTO theo subset

Khôi phục tenant A đầu tiên có thể giúp phục hồi một phần business service trước, nhưng phải có routing/isolation để không phục vụ data incomplete cho tenant B.

### 30.3. Priority order

Khi capacity hạn chế, business có thể ưu tiên dữ liệu/orders hoạt động trong 7 ngày gần nhất, nhưng dữ liệu cũ, payment audit và quyền truy cập vẫn có invariant riêng. Không tùy tiện mất data cũ nếu retention/compliance yêu cầu.

### 30.4. “Partial restored” phải được công bố

Một hệ trả HTTP 200 cho 30% tenants nhưng thiếu 70% không được báo `RTO met` cho toàn service nếu contract đòi đủ coverage.

---

## 31. Một bảng RPO/RTO theo failure scenario

| Asset/workflow | Failure | RPO mục tiêu minh họa | RTO mục tiêu minh họa | Cơ chế chính |
|---|---|---:|---:|---|
| Orders | Mất một node | 0 cho writes đã commit theo contract | 5 phút | Quorum/HA, automatic failover |
| Orders | Region mất | 5 phút | 60 phút | Cross-region backup/replication, reconcile |
| Orders | Logical delete nhầm | 5 phút | 90 phút | PITR/restore + reconcile commits |
| Product catalog | Region mất | 30 phút | 4 giờ | ERP source + restore |
| Search | Index corruption | Rebuild từ Orders | 2 giờ | Index snapshot/reindex + CDC |
| Sessions | Cache mất | Cho phép mất session | 15 phút | Restart + source protection |
| Idempotency | Redis mất | Không mất active keys hoặc có authority khác | 30 phút | Durable ledger/repair |
| Audit | Backup xóa nhầm | Theo compliance contract | 24 giờ | Immutable offsite archive |
| Analytics | Read model mất | Dựng lại được từ history | 1 ngày | Reprocess logs + snapshots |

**Các con số hoàn toàn minh họa.** Mỗi tổ chức phải thỏa thuận với business, security/legal và kiểm tra năng lực kỹ thuật thực.

### 31.1. Tại sao không có một “RPO cluster” chung?

Nhiều data sets có mức quan trọng khác, backup modes khác và hạ tầng khác. Báo cáo một số đẹp nhất sẽ che rủi ro của asset yếu nhất.

### 31.2. Mỗi hàng cần owner

Một bảng đẹp nhưng không có owner quyết định/duyệt trade-offs sẽ không trở thành runbook vận hành thực.

---

## 32. Policy bảo vệ dữ liệu theo tier

Có thể đề xuất **tiers** để đơn giản hóa ra quyết định:

| Tier | Đặc điểm | Hướng kỹ thuật thường cần |
|---|---|---|
| **Critical** | Data loss gây tổn thất cao/vi phạm | Durable ACK, cross-domain copies, PITR, frequent drills |
| **Important** | Có thể đối soát phần nhỏ | Frequent backups, recovery automation |
| **Rebuildable** | Có authoritative source khác | Reindex/resnapshot, throughput/capacity plan |
| **Disposable** | Cache tạm, không chứa state độc nhất | No backup nếu được phê duyệt; cold-start plan |
| **Compliance archive** | Phải giữ và bảo vệ tính toàn vẹn | Retention, access audit, immutability, key custody |

### 32.1. Tier không tự quyết RPO/RTO

Một index có thể rebuildable nhưng search service rất quan trọng nên RTO của index vẫn 15 phút; ngược lại một data archive rất quan trọng để giữ lâu nhưng không cần truy cập trong 15 phút.

### 32.2. Data classification có thể thay đổi

Một namespace Redis ban đầu chỉ cache, sau đó nhóm phát triển thêm idempotency keys vào nó; nếu inventory không cập nhật, chiến lược “không backup Redis” có thể không còn hợp lệ.

---

## 33. Kiến trúc backup phù hợp với mục tiêu phục hồi

Một thiết kế có thể kết hợp:

~~~mermaid
flowchart LR
    DB["Authoritative NoSQL"] --> S["Versioned snapshots"]
    DB --> L["Continuous log / change history"]
    S --> R["Encrypted backup repository"]
    L --> R
    R --> I["Immutable / offsite copy"]
    I --> DR["Recovery environment"]
    R --> DR
    DR --> V["Validation / reconciliation"]
    V --> CO["Controlled cutover"]
    OBS["Monitoring / drills"] -.-> R
    OBS -.-> DR
~~~

### 33.1. Backup cadence

Từ RPO tính được tần suất snapshot/log capture cần thiết, nhưng phải cộng backup duration và upload lag; `cron` bắt đầu lúc 00:00 không đồng nghĩa recoverable snapshot tồn tại lúc 00:00.

### 33.2. Backup retention

Lưu bao nhiêu recovery points? Cần phục hồi logical corruption phát hiện sau 2 tuần? PITR window phải dài đủ cho detection delay, không chỉ tính RPO 5 phút.

### 33.3. Backup isolation

Sử dụng quyền write/restore/delete tách biệt nếu có thể; có immutable policy/versioning và offsite copy phù hợp threat model.

### 33.4. Backup encryption

Mã hóa at rest/in transit và giữ key lifecycle có khả năng DR. Một backup encrypted không khôi phục được có thể tệ hơn không backup.

### 33.5. Recovery automation

Infrastructure-as-code và restore scripts có thể giảm RTO, nhưng cần change gates để không overwrite nguồn hiện tại hoặc làm lộ PII trong staging.

### 33.6. Testing

Sự khác biệt lớn nhất giữa **“có backup”** và **“có recovery capability”** là bản backup đã được restore và kiểm chứng dưới điều kiện đại diện.

---

## 34. Backup manifest: biết chính xác có gì trong bản sao

Một manifest có thể chứa:

~~~json
{
  "backupId": "orders-2026-11-14T09:00Z",
  "assetId": "orders-prod",
  "engine": "mongodb",
  "scope": "cluster-1",
  "backupType": "full-snapshot",
  "consistencyScope": "cluster-consistent-by-approved-tool",
  "checkpoint": "opaque-source-position",
  "startedAt": "2026-11-14T09:00:00Z",
  "completedAt": "2026-11-14T09:04:31Z",
  "validatedAt": "2026-11-14T09:05:10Z",
  "encryptionKeyReference": "kms://approved-key-version",
  "schemaVersion": "orders-schema-42",
  "artifacts": [
    {"path": "s3://backup-repo/orders/full-001", "checksum": "example"}
  ]
}
~~~

Đây là schema **minh họa**, không là manifest do MongoDB/AWS tự xuất.

### 34.1. Những trường quan trọng

- Scope: database/table/shard/cluster và region.
- Recovery point/log position được hỗ trợ.
- Backup type và dependencies (base/incremental).
- Consistency method.
- File locations/checksums/sizes.
- Encryption key reference, không phải secret key.
- Schema/engine version compatibility.
- Verification result và operator/job ID.
- Retention/immutability expiry.

### 34.2. `completedAt` không là recovery point

Snapshot bắt đầu 09:00, hoàn thành 09:04 không tự chứa dữ liệu đã commit tới 09:04. Mốc phục hồi phải lấy từ consistency/checkpoint semantics của backup tool.

### 34.3. Backup manifest không chứng minh recoverable nếu chưa restore

Manifest/checksum giúp integrity, nhưng không kiểm schema compatibility, KMS access, index build hoặc end-to-end business correctness.

---

## 35. Đo “freshness” của backup đúng cách

Đặt:

- \(t_{\text{now}}\): thời gian hiện tại.
- \(t_{\text{recoverable}}\): thời điểm mới nhất có thể phục hồi với **chain đã verify**.

Độ cũ của recovery point:

\[
A=t_{\text{now}}-t_{\text{recoverable}}.
\]

### 35.1. Ví dụ

~~~text
Now:                         11:00
Last backup job completed:    10:58
Recoverable source point:     10:30
Log archive latest verified:  10:42
~~~

Nếu công cụ restore hỗ trợ replay tới 10:42 và chain hoàn chỉnh, recoverable data point có thể là 10:42, tức 18 phút cũ. Không báo “backup age 2 phút” chỉ dựa trên last job completion lúc 10:58.

### 35.2. Theo failure domain

Recovery point trên cùng node không tồn tại sau disk loss. “Recoverable” cho region loss phải là artifact đã tồn tại và có thể truy cập **ngoài region**.

### 35.3. Theo asset/shard

Một backup job báo success tổng thể nhưng shard C thất bại thì không thể lấy mốc A/B để đại diện toàn cluster.

### 35.4. Đánh giá RPO trong drill

Ghi rõ các committed events trước fault, vị trí phục hồi và số operations mất/thừa. So time gap cùng data invariants; không chỉ đọc timestamp từ manifest.

---

## 36. Java: tính tuổi recovery point và RPO budget

Ví dụ Java 17 tính age theo `Instant`. Đây là kiểm tra metric logic, không thay việc xác minh artifact thực sự khôi phục được.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class RecoveryPointBudget {

    public record Assessment(
        Duration age,
        Duration objective,
        boolean objectiveMet
    ) {}

    public static Assessment assess(
            Instant latestVerifiedRecoverablePoint,
            Duration rpoObjective,
            Clock clock) {

        Objects.requireNonNull(latestVerifiedRecoverablePoint);
        Objects.requireNonNull(rpoObjective);
        Objects.requireNonNull(clock);

        if (rpoObjective.isNegative()) {
            throw new IllegalArgumentException(
                "RPO objective cannot be negative"
            );
        }

        Instant now = clock.instant();

        if (latestVerifiedRecoverablePoint.isAfter(now)) {
            throw new IllegalArgumentException(
                "Recovery point is in the future"
            );
        }

        Duration age = Duration.between(
            latestVerifiedRecoverablePoint,
            now
        );

        return new Assessment(
            age,
            rpoObjective,
            age.compareTo(rpoObjective) <= 0
        );
    }
}
~~~

### 36.1. `Clock` giúp test

Cho phép unit tests dùng một clock cố định, tránh phụ thuộc thời gian thực.

### 36.2. Phải chọn recovery point đúng scope

Tham số đầu vào phải đến từ inventory/manifest/checkpoint đã verify. Nếu chọn latest snapshot trong node bị mất, kết quả `objectiveMet=true` là sai về khả năng khôi phục.

### 36.3. Tránh high-cardinality metrics

Không tạo Prometheus label theo backupId cho mọi lần backup. Dùng asset tier, region, failure scenario và status loại hữu hạn.

### 36.4. Khi không có recovery point

Một `null` hoặc missing manifest không được ngụy trang thành timestamp `Instant.now()`. Báo `UNKNOWN`/`UNRECOVERABLE` và cảnh báo.

---

## 37. Java JUnit 5: kiểm tuổi backup theo RPO

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

public class RecoveryPointBudgetTest {

    private static final Clock FIXED = Clock.fixed(
        Instant.parse("2026-11-14T11:00:00Z"),
        ZoneOffset.UTC
    );

    @Test
    void freshRecoveryPointMeetsFiveMinuteRpo() {
        var result = RecoveryPointBudget.assess(
            Instant.parse("2026-11-14T10:57:00Z"),
            Duration.ofMinutes(5),
            FIXED
        );
        assertTrue(result.objectiveMet());
        assertEquals(Duration.ofMinutes(3), result.age());
    }

    @Test
    void oldRecoveryPointViolatesRpo() {
        var result = RecoveryPointBudget.assess(
            Instant.parse("2026-11-14T10:42:00Z"),
            Duration.ofMinutes(5),
            FIXED
        );
        assertFalse(result.objectiveMet());
        assertEquals(Duration.ofMinutes(18), result.age());
    }

    @Test
    void futurePointIsInvalid() {
        assertThrows(
            IllegalArgumentException.class,
            () -> RecoveryPointBudget.assess(
                Instant.parse("2026-11-14T11:01:00Z"),
                Duration.ofMinutes(5),
                FIXED
            )
        );
    }
}
~~~

### 37.1. Đây không phải DR drill

Unit tests chỉ xác nhận công thức. Nó không chứng minh MongoDB backup còn đủ oplog hay KMS key có thể decrypt trong region DR.

### 37.2. Tích hợp ở mức hệ thống

Có thể lấy latest verified restorable timestamp từ backup service API, đối chiếu policy và phát gauge/alert; phải định kỳ **restore thật** để kiểm thông tin đó chính xác.

---

## 38. Java: mô hình thời gian RTO theo giai đoạn

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Objects;

public final class RecoveryTimeBudget {

    public record Stage(
        String name,
        Duration elapsed
    ) {
        public Stage {
            Objects.requireNonNull(name);
            Objects.requireNonNull(elapsed);
            if (name.isBlank() || elapsed.isNegative()) {
                throw new IllegalArgumentException(
                    "Invalid recovery stage"
                );
            }
        }
    }

    public record Result(
        Duration total,
        Duration target,
        boolean targetMet
    ) {}

    public static Result assessSequential(
            List<Stage> stages,
            Duration target) {
        Objects.requireNonNull(stages);
        Objects.requireNonNull(target);
        if (target.isNegative()) {
            throw new IllegalArgumentException(
                "Negative RTO target"
            );
        }

        Duration sum = Duration.ZERO;
        for (Stage stage : stages) {
            sum = sum.plus(stage.elapsed());
        }

        return new Result(
            sum,
            target,
            sum.compareTo(target) <= 0
        );
    }
}
~~~

### 38.1. Giới hạn

Đây là mô hình tuần tự. Nếu provisioning chạy song song với approval hoặc index restore, lấy tổng các stage sẽ đếm trùng thời gian. Với DR workflow thật, dùng **timeline events/critical path** và mốc bắt đầu-kết thúc rõ ràng.

### 38.2. Ví dụ

~~~java
var result = RecoveryTimeBudget.assessSequential(
    List.of(
        new RecoveryTimeBudget.Stage(
            "detect", Duration.ofMinutes(5)),
        new RecoveryTimeBudget.Stage(
            "triage", Duration.ofMinutes(10)),
        new RecoveryTimeBudget.Stage(
            "restore", Duration.ofMinutes(45)),
        new RecoveryTimeBudget.Stage(
            "validate", Duration.ofMinutes(15)),
        new RecoveryTimeBudget.Stage(
            "cutover", Duration.ofMinutes(5))
    ),
    Duration.ofMinutes(60)
);
// total = 80 phút, targetMet = false.
~~~

`List` trong đoạn ví dụ phải được import `java.util.List` tại nơi dùng. Thực tế RTO được đo từ incident clock và service eligibility, không nên chỉ nhập estimate rồi tuyên bố pass.

---

## 39. Runbook diễn tập khôi phục để xác nhận RPO/RTO

### Pha A — Chuẩn bị an toàn

1. Xác định scope dataset và failure scenario cần test.
2. Phê duyệt môi trường staging/DR cách ly khỏi traffic thật.
3. Ghi business owners, data classifications và test success criteria.
4. Chọn nguồn backup/restore points cần xác minh.
5. Ghi expected committed transactions và deletion markers.
6. Xác minh người thử **không có quyền phá production source**.
7. Xác minh KMS/IAM/secret/network access trong recovery region.
8. Dự báo disk, transfer bandwidth, compute và chi phí drill.

### Pha B — Tạo tình huống

9. Tạo dữ liệu canary có IDs và committed timestamps.
10. Tạo cả `CREATE`, `UPDATE`, `DELETE` và idempotent business events.
11. Ghi checkpoint/backup state.
12. Giả lập mất một failure domain trong staging.
13. Bắt đầu đồng hồ RTO từ mốc được định nghĩa trước.

### Pha C — Restore

14. Quyết định recovery method, tránh chọn nhầm point.
15. Provision environment bằng IaC/version đã pin.
16. Restore snapshot/backup chain.
17. Replay log changes tới supported target point.
18. Cấu hình database authentication, encryption keys, indexes.
19. Chạy recovery/replication/compaction cần thiết.
20. Dựng lại projections từ consistent source/CDC.
21. Reconcile external side effects/payments và deletions.
22. Kiểm data invariants, source counts/samples/checksums.

### Pha D — Cutover và đo

23. Smoke test application với endpoint/test tenant phù hợp.
24. Kiểm p99, goodput, errors, retry và warm-up.
25. Xác nhận business operation classes đủ điều kiện.
26. Dừng đồng hồ RTO theo mốc serving trong contract.
27. Tính actual recoverable gap và business operations affected.
28. Ghi RPO/RTO actual và khoảng sai lệch so target.

### Pha E — Hậu diễn tập

29. Không nhập restored staging data trở lại production tùy tiện.
30. Cleanup resources theo approval, giữ report/manifest hợp lệ.
31. Ghi blockers, manual steps, bottleneck và missing artifacts.
32. Cập nhật runbook/capacity/retention rồi lên lịch kiểm lại.

---

## 40. Oracles: restore “đúng” được kiểm thế nào?

Chỉ có `db.ping()` thành công chưa đủ.

### 40.1. Database consistency

- Engine metadata và schema hợp lệ.
- Không thiếu required shards/partitions.
- Không có logical corruption/incomplete migration.
- Queries quan trọng trả dữ liệu đúng.
- Indexes và uniqueness/constraints theo thiết kế.

### 40.2. Business invariants

- Order trạng thái paid phải được đối soát với payment provider.
- Một ticket ID không được cấp trùng.
- Inventory reservation không tạo oversell.
- User revocation đã commit không biến thành quyền active sau restore.
- Delete requests đã xử lý không hồi sinh data trái policy.

### 40.3. Cross-system consistency

- CDC checkpoint không bỏ qua events.
- Outbox entries không publish double side effects không idempotent.
- Search/analytics phản ánh source theo watermark.
- Cache không trả stale/forbidden state.

### 40.4. Security/recovery constraints

- KMS key and IAM policies đúng.
- Restore dữ liệu nhạy cảm chỉ vào environment được phép.
- Audit log và access controls hoạt động.
- Backup repo không bị exposure.

### 40.5. User-visible SLO

- Critical read/write operations thành công.
- Error rate dưới ngưỡng.
- p95/p99 phù hợp.
- Throughput đủ.
- Không còn maintenance debt cản phục vụ.

---

## 41. Monitoring: không chỉ “backup job success”

| Metric | Ý nghĩa | Dấu hiệu đáng cảnh báo |
|---|---|---|
| `last_backup_success` | Job gần nhất có hoàn tất | Backup pipeline lỗi |
| `latest_verified_recoverable_point` | Mốc thực sự có thể restore | RPO budget bị vượt |
| `backup_validation_age` | Bao lâu chưa kiểm backup | Checksum/chain lỗi không bị phát hiện |
| `backup_bytes` | Backup footprint/growth | Capacity/cost |
| `backup_duration` | Thời gian tạo artifact | Chậm hơn chu kỳ backup |
| `log_archival_lag` | Change history chưa copy | PITR gap |
| `backup_replication_lag` | Offsite copy chưa cập nhật | Region loss RPO |
| `restore_test_last_success` | Đã diễn tập gần đây chưa | Recovery ability chưa kiểm |
| `restore_test_total_duration` | Measured RTO | RTO không đạt |
| `restore_test_data_loss_gap` | Observed RPO | RPO không đạt |
| `restore_data_validation_failures` | Data invariant sai | Recovery không an toàn |
| `kms_access_failures` | Không decrypt được | DR blocked |
| `restore_transfer_mibps` | Effective throughput | RTO bị vượt |
| `replication_lag_by_shard` | Failover RPO exposure | Một shard tụt xa |
| `cdc_resume_gap` | Replay không đầy đủ | Projection stale |
| `deletion_reconcile_pending` | Delete requests chưa áp sau restore | Privacy/security risk |

Metric names là **gợi ý contract**, không khẳng định tất cả exporters đã cung cấp những chuỗi đó.

### 41.1. Label scope

Theo asset tier/region/failure scenario, không dùng từng document ID hoặc backup object path làm labels không giới hạn.

### 41.2. Alert theo objective

Một alert có thể so *latest verified recoverable point age* với 80% RPO budget để có thời gian sửa trước khi vượt. Cần policy cho các scenario khác nhau.

### 41.3. Backups chưa được thử restore

“Backup success 100% trong 30 ngày” vẫn có thể vô nghĩa nếu không có một bài restore thành công với schema/keys hiện hành.

---

## 42. Phân bổ chi phí bảo vệ dữ liệu theo RPO/RTO

Càng yêu cầu phục hồi nhanh và mất dữ liệu ít, thường càng cần:

- Redundancy đồng thời ở nhiều failure domains.
- Replication/consensus hoặc transaction log capture bền.
- Snapshot/PITR frequency cao.
- Storage copy và backup retention.
- Pre-provisioned DR environment.
- Automation, operational staffing và drills.
- Strong monitoring/alerting.
- Extra network/disk headroom.
- Security isolation, immutability và key custody.

### 42.1. Không kết luận “RPO=0 luôn tốt nhất”

RPO 0 cho một loại lỗi có thể rất đắt hoặc không khả thi với kiến trúc hiện tại. Nếu business có khả năng tái tạo dữ liệu mất trong 10 phút, có thể chọn trade-off khác, được owner phê duyệt.

### 42.2. Chi phí missed objectives

Cần so chi phí kỹ thuật với tổn thất dự kiến khi dữ liệu mất/gián đoạn; có cả uy tín, legal compliance, security và manual reconciliation.

### 42.3. Không dùng một con số cost-only

Đối với payment/permissions, một missing record có thể gây hậu quả phi tuyến tính. Phân loại risk/criticality trước khi chọn mức backup tối thiểu.

---

## 43. Ma trận kiểm thử phục hồi: 32 kịch bản

| ID | Kịch bản | Oracle chính |
|---|---|---|
| R01 | Một node crash trong cluster healthy | HA phục vụ đúng; acknowledged writes giữ theo contract |
| R02 | Mất toàn bộ data volume một node | Rebuild replica/restore với RPO/RTO đo được |
| R03 | Mất một AZ | Phần còn lại đủ role/quorum/capacity |
| R04 | Mất region nguồn | Cross-region artifacts truy cập được; cutover đúng |
| R05 | Delete nhầm collection/table | PITR tới trước lỗi, reconcile writes sau đó |
| R06 | Application bug sửa sai 1 triệu documents | Logical corruption bị phát hiện và khoanh vùng |
| R07 | Backup job fail 3 lần | Freshness alert trước vượt RPO |
| R08 | Baseline snapshot bị xóa | Restore chain fail closed, báo unrecoverable |
| R09 | Incremental segment bị thiếu | Không tuyên bố PITR thành công |
| R10 | Change log archive trễ 40 phút | Actual recoverable point phản ánh lag |
| R11 | KMS key không có quyền ở DR region | Test báo blocker thay vì startup giả |
| R12 | Truststore/secret khác sau restore | Security/driver handshake được kiểm |
| R13 | Backup repository bị xóa bởi principal sai | Immutable/offsite copy còn khả dụng |
| R14 | Restore time gấp đôi vì network chậm | RTO violation rõ trong report |
| R15 | Backup 1 GB restore nhanh, 10 TB restore chậm | Capacity sizing từ dataset đại diện |
| R16 | MongoDB sharded snapshot không nhất quán | Không cutover nếu thiếu consistent point |
| R17 | Cassandra node offline quá repair/tombstone horizon | Không zombie data, reseed đúng |
| R18 | DynamoDB PITR cần table đích mới | IAM/index/config/cutover tính trong RTO |
| R19 | Redis derived cache mất sạch | Backend không bị stampede |
| R20 | Redis idempotency keys mất | Không double charge/double order |
| R21 | Elasticsearch index mất | Reindex/snapshot restore và alias cutover đúng |
| R22 | CDC consumer checkpoint vượt log retention | Rebootstrap thay vì skip changes |
| R23 | Kafka offset mới hơn restored DB state | Không bỏ qua event business |
| R24 | External payment đã capture nhưng order mất | Reconciliation không double charge |
| R25 | Restore snapshot cũ sau user deletion | Delete ledger ngăn resurrection |
| R26 | Một shard có recovery point cũ hơn các shard khác | Không claim cluster RPO từ shard tốt nhất |
| R27 | Backup được mã hóa bằng key đã retire | Key lifecycle/recoverability được kiểm |
| R28 | Old app version không đọc schema restored | Schema/artifact compatibility kiểm |
| R29 | Restore trong khi source vẫn nhận writes | Conflict/cutover protocol đúng |
| R30 | Recovery environment thiếu capacity | Test báo RTO/capacity blocker |
| R31 | Backup offsite tồn tại nhưng IAM account bị khóa | Break-glass/DR access được thử |
| R32 | Simulated full blackout + cold start | End-to-end SLO/consistency đạt tại RTO endpoint |

Không cố ý phá production data, KMS keys, backups hoặc region để chạy tests. Dùng staging/DR environment và chaos procedures được phê duyệt.

---

## 44. Runbook quyết định recovery khi có incident

### Bước 1 — Ổn định hệ

- Chặn/giới hạn writes đang gây corruption.
- Bảo toàn logs/evidence theo chính sách.
- Không tiếp tục replication/cutover mù quáng vào bản dữ liệu đã sai.
- Xác định owner và mức khẩn.

### Bước 2 — Xác định failure mode

- Node failure hay logical corruption?
- Source còn authoritative state sạch không?
- Replicas có copy sạch hay lỗi đã replicate?
- Sự cố nằm ở dataset nào và từ thời điểm nào?
- RPO/RTO được phê duyệt cho scenario này là bao nhiêu?

### Bước 3 — Chọn recovery point

- Liệt kê available verified backups/log chains.
- Xác định earliest/latest restorable timestamps.
- So mất dữ liệu dự kiến và RPO budget.
- Chọn checkpoint trước lỗi logic nếu cần.
- Không chọn điểm gần nhất khi điểm đó đã chứa corruption.

### Bước 4 — Chọn restore method

- Automatic failover nếu only node failure và state đúng.
- PITR/snapshot restore nếu cần quay ngược lịch sử.
- Rebuild projections nếu authoritative source còn tốt.
- Replay logs nếu history đầy đủ.
- Manual reconciliation nếu có cross-system side effects.

### Bước 5 — Thực thi có kiểm soát

- Dùng environment/permissions/keys đúng.
- Restore vào target cách ly nếu có thể.
- Không overwrite source chưa xác định đúng.
- Theo dõi transfer/restore/replay/validation time.

### Bước 6 — Data correctness gates

- Kiểm key business invariants.
- Kiểm thiếu/trùng acknowledged transactions.
- Kiểm deletion/permission revocation.
- Đối soát payment/fulfillment/providers.
- Rebuild search/cache/outbox/CDC checkpoints đúng.

### Bước 7 — Cutover và đo

- Chạy canaries.
- Chuyển traffic theo plan.
- Đo error, p99, goodput và freshness.
- Dừng RTO clock theo contract.
- Ghi RPO actual và bất kỳ exceptions chưa giải quyết.

### Bước 8 — Hậu sự cố

- Thu thập nguyên nhân, gap, time lost và costs.
- Cập nhật backup retention, monitoring, automation.
- Bổ sung restore drill vào chu kỳ định kỳ.
- Ghi formal risk acceptance nếu mục tiêu không đạt.

---

## 45. Bài tập 1 — Phân loại dữ liệu cần bảo vệ

Một hệ gồm:

~~~text
MongoDB: orders, customer_profiles
Redis: product_cache, user_sessions, idempotency_keys
Kafka: order_created, payment_captured, order_deleted
Elasticsearch: orders_search
Object storage: invoice PDFs
KMS: encryption keys
Git/IaC: schema/index definitions
```

Hãy lập inventory với mỗi asset:

1. Owner.
2. System of record.
3. Dữ liệu gốc hay dẫn xuất?
4. Có thể rebuild không, từ đâu và trong bao lâu?
5. Điều gì xảy ra khi mất 30 phút?
6. Có PII/compliance obligations nào?
7. Dependencies phải khôi phục cùng.
8. RPO/RTO mục tiêu minh họa cho node loss và region loss.

**Gợi ý:** `idempotency_keys` không nên mặc nhiên disposable chỉ vì lưu trong Redis.

---

## 46. Bài tập 2 — Tính RPO mất dữ liệu

Một source ghi:

~~~text
Average committed orders: 250/s
Peak committed orders:    1.200/s
Latest verified point:    10:45:00
Source failed at:         10:47:30
~~~

1. Actual time gap là bao nhiêu?
2. Ước lượng đơn bị ảnh hưởng theo average và peak.
3. Nếu RPO mục tiêu 60 giây, có đạt không?
4. Nếu offsite backup chỉ recoverable đến 10:40, region loss RPO là bao nhiêu?
5. Nếu payment provider đã capture nhiều đơn sau point, kế hoạch reconciliation thế nào?
6. Khi client timeout, điều gì khiến số đơn bị ảnh hưởng không thể suy chính xác chỉ từ rate?

Gợi ý: gap 150 giây; average 37.500 đơn; peak 180.000 đơn trong mô hình đơn giản.

---

## 47. Bài tập 3 — RTO và effective throughput

Một backup 3 TiB cần restore từ remote repository:

~~~text
Effective transfer:       500 MiB/s
Provisioning:             15 phút
Restore/replay:           35 phút
Validation:               20 phút
Cutover/warm-up:          10 phút
RTO target:               120 phút
```

1. Tính transfer time lý tưởng.
2. Tính tổng tuần tự.
3. RTO 120 phút có khả thi?
4. Nếu chuyển backup nén chỉ 1 TiB, bottleneck tiếp theo là gì?
5. Nếu có hai restore streams nhưng shared disk quota không tăng, hiệu quả ra sao?
6. Nêu ít nhất bốn cách giảm critical path **không** bỏ validation.

---

## 48. Bài tập 4 — Snapshot không nhất quán

Cụm có hai shards:

~~~text
Shard A snapshot: 10:00
Shard B snapshot: 10:03
Cross-shard workflow moves quota from A to B at 10:02
```

1. Rủi ro khi restore hai snapshots cùng nhau?
2. Một timestamp gần nhau có đảm bảo consistency không?
3. Cần loại backup/transaction checkpoint protocol nào?
4. Nếu không có global consistent cut, có thể dùng ledger reconciliation thế nào?
5. Business invariants phải kiểm là gì?
6. Có nên mở writes trước khi đối soát quota không?

---

## 49. Bài tập 5 — DynamoDB PITR và cutover

Một DynamoDB table có PITR, cần phục hồi dữ liệu trước một thao tác delete sai.

Hãy thiết kế:

1. Xác định earliest/latest restorable point.
2. Restore sang table đích.
3. Xác minh indexes, TTL, Streams, capacity, IAM và tags.
4. Xử lý các writes đã đến source table sau point được chọn.
5. Reconfigure CDC consumers.
6. Test query/conditional write/idempotency.
7. Chuyển endpoint/configuration traffic.
8. Giới hạn stale GSI reads.
9. Kiểm RPO/RTO actual.
10. Đảm bảo không phục hồi user deletions trái chính sách.

---

## 50. Bài tập 6 — Redis “chỉ là cache”?

Một Redis cluster chứa:

~~~text
products:*          Cache derived
sessions:*          User sessions
idempotency:*       Charge request IDs
locks:*             Distributed lock tokens
ratelimit:*         Abuse prevention counters
```

1. Namespace nào có thể mất mà không làm mất business facts?
2. Namespace nào cần authoritative backing store hoặc backup?
3. Nếu mất Redis, cold-cache load lên MongoDB tăng thế nào?
4. AOF/replica có bảo đảm RPO 0 không?
5. Locks và fencing tokens ảnh hưởng correctness sau restore thế nào?
6. Phân loại failure mode security/accountability.
7. Viết RTO/UX contract cho session loss.
8. Lập kế hoạch warm-up có rate limit.

---

## 51. Bài tập 7 — Dựng RPO/RTO dashboard

Thiết kế dashboard tối thiểu gồm:

- Latest verified recovery point theo asset/region.
- Age vs target RPO.
- Backup job success/failures.
- Incremental/log archival lag.
- Last restore drill timestamp.
- Measured RTO per scenario.
- Restore throughput, bytes và time.
- KMS/permission errors.
- Offsite replica availability.
- Recovery chain completeness.
- Reconciliation/deletion exceptions.
- Business owner/runbook link.

Hãy nêu metric nào là **gauge**, **counter**, **duration histogram**, và vì sao “last backup job finished” không phải recoverable point timestamp.

---

## 52. Bài tập 8 — Soạn Recovery Contract và diễn tập

Một tổ chức chọn:

~~~text
Critical order writes:
  Region-loss RPO <= 5 phút
  Region-loss RTO <= 60 phút

Search:
  Can rebuild, RTO <= 4 giờ

Audit:
  No loss of required compliance evidence
  Access within 24 giờ
```

Hãy viết recovery contract chứa:

1. Failure scenario và start/end clocks.
2. Data assets/cross-system boundaries.
3. Durability/ACK assumptions.
4. Backup/PITR/replication mechanism.
5. Offsite/immutable copies.
6. KMS/IAM recovery.
7. Snapshot+logs recovery point verification.
8. Restore resource sizing.
9. Reconciliation for payment and deletion.
10. Canary/cutover gates.
11. Measured RPO/RTO acceptance.
12. Ownership, escalations và review cadence.

Từ đó lập một tabletop drill và một technical restore drill. Đề xuất chỉ số nào chứng minh objective đạt và bước nào có thể fail.

---

## 53. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Có backup là đã có DR.” | Phải restore được, đúng dữ liệu và trong RTO |
| “Replica là backup.” | Lỗi logic/delete có thể replicate |
| “RPO và RTO là một.” | RPO là độ mất dữ liệu, RTO là thời gian phục vụ |
| “Backup 30 phút/lần chắc có RPO 30 phút.” | Job có thể fail, recovery point và upload lag khác |
| “Backup job kết thúc lúc 10:00 nghĩa dữ liệu đến 10:00.” | Cần checkpoint/consistent recovery position |
| “Backup mới nhất luôn là tốt nhất.” | Có thể đã chứa corruption |
| “PITR tự bao phủ mọi shard/system.” | Scope/consistency khác nhau theo tool |
| “CDC luôn đủ để rebuild.” | Có retention, gaps và schema/version constraints |
| “Kafka offset là global timestamp.” | Ordering theo partition và contract |
| “RPO 0 chỉ cần replication async.” | ACK/cross-domain durability phải đủ |
| “RTO chỉ là lệnh restore.” | Còn detect, triage, provision, validate, cutover |
| “Database ping thành công = business recovered.” | Cần integrity, dependencies, SLO |
| “Search là derived nên không cần RTO.” | Rebuild lớn có thể vượt thời gian cho phép |
| “Redis luôn disposable.” | Idempotency/session/queue có thể là state quan trọng |
| “Có snapshot là không cần encryption keys.” | Không có key thì backup có thể vô dụng |
| “DynamoDB PITR rewind table đang chạy.” | Recovery thường tạo table đích mới |
| “Mongo replica đảm bảo chống accidental DELETE.” | Delete có thể lan toàn replica set |
| “Cassandra snapshot một node đã đủ toàn cluster.” | Cần đủ token ranges/metadata/consistency |
| “Dùng Elasticsearch replica shard là lịch sử phục hồi.” | Replica không giữ bản trước logical corruption |
| “Backup cùng AZ vẫn sống khi cả AZ mất.” | Phải tách failure domains |
| “Cross-region copy có nghĩa account compromise không phá được.” | Cần isolation/immutability/permissions |
| “Backup immutable chắc restore nhanh.” | RTO còn transfer/provision/replay |
| “Có catalog là đủ, không cần inventory key/ACL.” | Recovery phụ thuộc configs và quyền |
| “RPO 5 phút nghĩa chỉ mất ít bytes.” | Peak commits và giá trị từng event quan trọng |
| “Tất cả shards đều cùng mốc mới nhất.” | Có thể có lag/consistent cut limits |
| “Restore snapshot cũ không ảnh hưởng user deletion.” | Có thể resurrect PII/permissions |
| “Full backup thành công nên incremental chain không cần kiểm.” | Missing segment làm PITR fail |
| “RTO đạt nếu chỉ 20% tenants truy cập được.” | Scope phục vụ phải được định nghĩa |
| “DR drill quá tốn, có thể chỉ test API backup.” | Không kiểm restore thì rủi ro chưa biết |
| “Một bài restore 1 GiB chứng minh 10 TiB.” | Transfer và build scale khác |
| “Chỉ DBA cần đặt RPO/RTO.” | Business/security/legal phải sở hữu quyết định rủi ro |
| “Cứ thêm replication là đạt mọi mục tiêu.” | Phải đo failover, corruption, backup và recovery |

---

## 54. Checklist quyết định RPO/RTO trước khi triển khai

- [ ] Đã liệt kê business workflows và những thao tác có side effect.
- [ ] Có inventory data assets với owner và source of truth.
- [ ] Phân loại authoritative, derived, ephemeral, logs, archives và dependencies.
- [ ] Xác định dữ liệu nào không thể rebuild và vì sao.
- [ ] RPO/RTO được đặt riêng cho node, AZ, region và logical corruption khi cần.
- [ ] Mỗi objective có start/end clocks và operation scope rõ.
- [ ] Tính số giao dịch/giá trị có thể mất trong peak RPO gap.
- [ ] Hiểu ACK/write concern/consistency contract của source.
- [ ] Backup mechanism bao gồm toàn bộ shards/partitions/token ranges cần thiết.
- [ ] Biết backup có crash-consistent hay application-consistent boundary.
- [ ] Snapshot/restore có checkpoint phù hợp với WAL/oplog/CDC.
- [ ] Đã xác minh log chain không có gaps và retention đủ.
- [ ] Có offsite/immutable copy phù hợp failure model.
- [ ] KMS/keys/IAM/secrets và schema/IaC có DR path.
- [ ] RTO đã tính provisioning, transfer, restore, replay, validation, cutover.
- [ ] Đã thử restore dataset có kích thước đại diện.
- [ ] Có measured recovery point age và last successful restore drill.
- [ ] Search/index/cache RTO và warm-up được lập kế hoạch.
- [ ] Có phương án ngăn/cảnh báo replay trùng side effects.
- [ ] Có reconciliation với payment/inventory/external systems.
- [ ] Backup restore không hồi sinh user deletion hoặc revoked permissions.
- [ ] RPO/RTO được kiểm theo worst shard/region trong scope.
- [ ] Có owner phê duyệt mục tiêu và chấp nhận rủi ro còn lại.
- [ ] Có escalation khi objective bất khả thi với hạ tầng hiện tại.
- [ ] Có runbook phù hợp engine/version và cách cô lập môi trường restore.
- [ ] Không phá production data khi chạy backup/restore tests.
- [ ] Metrics bao gồm actual recoverability, không chỉ backup success.
- [ ] Sau mỗi thay đổi topology/index/retention cập nhật protection plan.
- [ ] Có lịch tabletop và technical restore drills.
- [ ] Báo cáo kết quả thành công theo data correctness lẫn user-visible SLO.

---

## 55. Tổng kết

**Sao lưu và phục hồi NoSQL bắt đầu bằng một quyết định nghiệp vụ: phải giữ dữ liệu nào và chấp nhận hậu quả mất dữ liệu, ngừng phục vụ tới mức nào.** Khi những quyết định đó rõ ràng, đội kỹ thuật mới có cơ sở chọn snapshot, PITR, replication, offsite copies và recovery automation.

Mười nguyên tắc cần nhớ:

1. **RPO là mốc dữ liệu có thể phục hồi; RTO là thời gian trở lại trạng thái phục vụ được định nghĩa.** Chúng không thay nhau.
2. **Đừng bắt đầu từ máy chủ.** Lập inventory từ workflows, data authority, dependencies và side effects.
3. **Phân loại dữ liệu theo khả năng rebuild thật.** Cache, index và event log có thể rất quan trọng tùy semantics.
4. **RPO/RTO phụ thuộc failure scenario và operation class.** Node crash khác mất region hay logical deletion.
5. **Replication phục vụ availability, backup/PITR phục vụ lịch sử recoverable.** Không có một kỹ thuật đơn lẻ bảo vệ mọi lỗi.
6. **Backup mốc thời gian phải nhất quán trong scope.** Shards/systems có thể ở những vị trí commit khác nhau.
7. **Đo RPO từ latest verified recoverable point**, không từ thời gian job báo hoàn thành.
8. **Đo RTO end-to-end**, bao gồm phát hiện, chuẩn bị, tải dữ liệu, replay, kiểm đúng nghiệp vụ và cutover.
9. **Khôi phục cũ có thể tạo lỗi mới**: double payment, stale permission, resurrect deleted data hoặc consumer bỏ qua events.
10. **Khả năng phục hồi chỉ đáng tin khi được diễn tập** với dataset, failure domain, quyền truy cập và SLO đại diện cho thực tế.

**Câu cần nhớ: “Trước khi hỏi ‘backup chạy mấy giờ một lần?’, hãy hỏi ‘khi mất dữ liệu, điều gì không được phép mất, chúng ta chấp nhận lùi bao lâu, và bao lâu sau khách hàng có thể dùng dịch vụ đúng trở lại?’. RPO và RTO là câu trả lời có thể đo được cho hai câu hỏi cuối.”**

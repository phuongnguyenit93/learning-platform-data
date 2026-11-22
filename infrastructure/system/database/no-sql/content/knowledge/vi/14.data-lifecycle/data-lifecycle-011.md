# Khôi phục dữ liệu xóa nhầm và kiểm tra dữ liệu không bị tái xuất hiện

Trong vòng đời dữ liệu NoSQL, **xóa dữ liệu** không đồng nghĩa với việc một bản ghi biến mất tức thì khỏi mọi nơi. Dữ liệu có thể còn ở replica, snapshot, backup, cache, search index, bảng phục vụ truy vấn, message queue và kho phân tích. Điều này tạo ra hai yêu cầu cần được giải quyết cùng nhau: **phục hồi dữ liệu bị xóa nhầm** và **không để dữ liệu đã xóa hợp lệ xuất hiện trở lại**.

Khôi phục từ một bản backup cũ có thể lấy lại hồ sơ vô tình bị mất, nhưng cũng có thể làm sống lại tài khoản mà người dùng đã yêu cầu xóa sau thời điểm backup. Ngược lại, một replica chưa nhận tombstone có thể làm bản ghi đã xóa quay lại sau repair hoặc failover. Một consumer CDC phát lại sự kiện CREATE cũ có thể đưa document trở về search index, dù bản ghi nguồn đang ở trạng thái DELETED.

Vì vậy, một kế hoạch khôi phục đáng tin cậy cần biết **cái gì bị xóa, xóa do ai và vì sao, phiên bản nào là hợp lệ, dữ liệu được phép phục hồi từ nguồn nào, các xóa hợp lệ phải tiếp tục được giữ ở đâu, và dùng bằng chứng gì để chứng minh kết quả cuối đúng**.

Bài học này trình bày cách phân biệt xóa nhầm với xóa hợp lệ, lựa chọn snapshot/PITR, phục hồi chọn lọc, giữ tombstone hoặc deletion ledger, chống dữ liệu cũ được phát lại, và kiểm tra sau khôi phục trong nhiều sản phẩm NoSQL. Các ví dụ về MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis và search/read model đều phải được điều chỉnh theo **phiên bản và cấu hình thực tế**, không được coi là quy trình khôi phục chạy nguyên xi cho mọi deployment.

## 1. Hai sự cố khác nhau nhưng liên quan chặt chẽ

Giả sử nền tảng có hai khách hàng, **C-42** và **C-99**.

~~~text
10:00 — Snapshot S1 chứa cả C-42 và C-99.
10:05 — Cleanup job lỗi xóa nhầm C-42.
10:10 — Một yêu cầu hợp lệ xóa C-99 được chấp nhận.
10:30 — Đội vận hành muốn khôi phục C-42 từ S1.
~~~

Nếu chép toàn bộ S1 đè lên production:

- **C-42** quay lại: đó là kết quả mong muốn.
- **C-99** cũng quay lại: đó là **resurrection trái chính sách**.
- Các thay đổi hợp lệ từ 10:00 đến 10:30 có thể bị mất.
- Những consumer đọc thay đổi có thể phát hiện hàng loạt bản ghi mới và thực hiện tác động phụ không mong muốn.

Do đó, **có backup** và **khôi phục đúng** là hai khả năng khác nhau. Backup có thể giữ dữ liệu lịch sử, nhưng không tự phân biệt được xóa nhầm và xóa hợp lệ.

### Các khái niệm phải phân biệt

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Accidental delete** | Xóa sai do lỗi phần mềm, thao tác nhầm hoặc cấu hình TTL không đúng. |
| **Intentional delete** | Xóa đã được nghiệp vụ hoặc người có thẩm quyền chấp nhận. |
| **Soft delete** | Giữ bản ghi và đánh dấu đã xóa, thường bằng status/deletedAt/version. |
| **Hard delete** | Loại bản ghi theo cơ chế lưu trữ; không mặc định mọi backup vật lý đã mất dữ liệu ngay. |
| **Tombstone** | Dấu xóa được lưu để truyền tải hoặc bảo vệ thông tin rằng dữ liệu không còn hợp lệ. |
| **TTL / expiration** | Dữ liệu hết hiệu lực sau thời hạn, cơ chế xóa vật lý tùy sản phẩm. |
| **Snapshot/backup** | Bản sao dữ liệu được giữ để phục hồi. |
| **PITR** | Point-in-time recovery: phục hồi về một thời điểm được hỗ trợ trong cửa sổ lưu giữ. |
| **Resurrection** | Dữ liệu đã xóa xuất hiện lại từ bản ghi cũ, replica, restore, CDC hoặc import. |
| **Deletion ledger** | Bản ghi có thẩm quyền về ý định xóa, phiên bản và phạm vi xóa. |
| **Reconciliation** | Đối chiếu dữ liệu nguồn, bản sao và ý định nghiệp vụ để phát hiện/sửa sai lệch. |

Tombstone của Cassandra, document soft delete và bản ghi deletion ledger **khác nhau về vai trò và phạm vi bảo đảm**; không được dùng ba thuật ngữ này như từ đồng nghĩa.

## 2. Vì sao dữ liệu xóa có thể tái xuất hiện?

Một document gốc có thể được sao chép theo nhiều đường:

~~~mermaid
flowchart LR
    API[API nghiệp vụ] --> SRC[NoSQL nguồn]
    SRC --> R[Replica / Region]
    SRC --> B[Backup / snapshot]
    SRC --> E[CDC / event stream]
    E --> M[Read models]
    E --> S[Search index]
    M --> C[Cache]
    SRC --> A[Analytics / export]
~~~

Các con đường hồi sinh thường gặp:

1. **Replica cũ:** một node offline chưa nhận delete, sau đó kết nối trở lại và mang dữ liệu cũ.
2. **Restore backup cũ:** bản sao chứa document trước khi có xóa hợp lệ.
3. **CDC replay:** event CREATE/UPDATE cũ đến sau event DELETE và được consumer upsert.
4. **Reindex:** index được dựng lại từ snapshot chưa lọc dữ liệu cần xóa.
5. **Import:** batch CSV/JSON từ quá khứ được nạp vào dữ liệu hiện tại.
6. **Cache:** key cũ còn TTL, invalidation bị bỏ sót hoặc đồng bộ hai chiều ghi ngược cache vào nguồn.
7. **Region phân tán:** policy giải quyết xung đột chọn bản cập nhật cũ hoặc hai nơi có trạng thái khác nhau.
8. **Thiết bị offline:** thiết bị cũ đồng bộ một phiên bản trước khi tài khoản bị xóa.
9. **Read model denormalized:** bản ghi chi tiết đã xóa nhưng bảng danh sách vẫn chứa nó.
10. **Backup phục hồi thử nghiệm:** môi trường staging có dữ liệu cũ được đồng bộ nhầm vào production.
11. **TTL:** dữ liệu hết hạn nhưng vẫn còn ở một nơi trước khi tác vụ xóa nền chạy.
12. **Repair/compaction không phù hợp:** dấu xóa biến mất trước khi bản sao cũ đồng bộ.

Mỗi con đường cần một biện pháp **chặn dữ liệu cũ thắng trạng thái xóa mới**, không chỉ một lệnh DELETE ở primary.

## 3. Không thấy dữ liệu khi đọc chưa chứng minh đã xóa an toàn

Giả sử:

~~~text
GET /customers/C-99 -> NOT_FOUND
~~~

Kết quả NOT_FOUND có thể do bản ghi bị xóa, bị soft delete, bị lọc bởi phân quyền, nằm ở replica chưa bắt kịp, cache có negative entry, query dựa trên index chưa đồng bộ hoặc yêu cầu timeout bị diễn giải thành “không tồn tại”.

Cần phân biệt các mức kiểm chứng:

| Mức | Điều phải chứng minh |
| --- | --- |
| **API visibility** | Người dùng không còn được phục vụ dữ liệu đã xóa hợp lệ. |
| **Source state** | Nguồn sự thật ghi nhận trạng thái và version xóa đúng. |
| **Replica convergence** | Những replica/vùng thuộc phạm vi cam kết đã đồng bộ trạng thái xóa. |
| **Derived data** | Search, cache, feed và read model không còn phục vụ bản cũ. |
| **Recovery safety** | Restore/reindex/replay không thể tự tái tạo bản ghi bị cấm. |
| **Physical retention** | Dữ liệu trong log, backup và storage được dọn theo thời hạn đã phê duyệt. |

Các mức này **không nhất thiết hoàn tất cùng lúc**. Một hệ có thể ẩn dữ liệu khỏi API ngay nhưng vẫn giữ backup để khôi phục trong một cửa sổ retention; điều đó cần được mô tả rõ theo chính sách. Không hứa “đã xóa hoàn toàn khỏi mọi bản sao” nếu chưa có bằng chứng và nếu cơ chế sản phẩm không cho phép.

## 4. Phân loại nguyên nhân xóa nhầm

| Nguyên nhân | Ví dụ | Cần thu thập |
| --- | --- | --- |
| Lệnh DELETE sai điều kiện | Không có tenant filter | Query, actor, danh sách khóa và transaction ID |
| Cleanup job lỗi | Xóa tất cả record thay vì record hết hạn | Job version, checkpoint, window và log |
| TTL sai | Đặt TTL 1 giờ thay vì 1 năm | expiresAt, config, những key đã hết hạn |
| Schema migration lỗi | Bỏ field hoặc đổi khóa sai | Migration version, snapshot trước migration |
| Partial update sai | Gán null thay vì bỏ qua field | Payload, driver serialization, bản ghi trước |
| Xóa quan hệ dây chuyền | Xóa graph node kéo theo edges | Danh sách node và edge, cascade scope |
| Restore sai môi trường | Chép dataset staging vào production | Audit quyền, endpoint, backup ID |
| Xung đột replica | Bản cũ thắng marker xóa | Region/node, consistency, timeline, version |
| Consumer lỗi | Xóa nguồn rồi create lại từ event cũ | Event IDs, offsets, version và consumer logs |

Một tập dữ liệu mất trong cùng khoảng thời gian không có nghĩa tất cả DELETE đều sai. **Không khôi phục theo thời gian đơn thuần** khi có thể có các xóa hợp lệ xen kẽ.

## 5. Định nghĩa hợp đồng khôi phục trước khi chọn công cụ

Một sự cố có ba mục tiêu độc lập:

1. **Lấy lại dữ liệu bị mất nhầm** với đúng nội dung, chủ sở hữu và quan hệ.
2. **Không làm mất những thay đổi hợp lệ xảy ra sau điểm backup.**
3. **Không làm sống lại dữ liệu đã bị xóa hợp lệ.**

Hai thước đo quen thuộc:

- **RPO (Recovery Point Objective):** khoảng mất dữ liệu tối đa chấp nhận được, thường biểu diễn bằng thời gian.
- **RTO (Recovery Time Objective):** thời gian tối đa đến khi đạt trạng thái phục hồi đã xác định.

Cần thêm các điều kiện đúng đắn: **không ghi đè version mới**, **không phục hồi entity bị cấm**, **không duplicate payment/order**, **không xuất hiện ở search hoặc cache sau reindex**, và **có thể đối soát lịch sử**.

Ví dụ hợp đồng sự cố giả định:

~~~yaml
incident:
  type: ACCIDENTAL_DELETE
  affectedTenant: T1
  affectedEntities:
    - C-42
  desiredRecoveryPoint: "Before erroneous delete"
recovery:
  rtoMinutes: 60
  rpoMinutes: 5
  restoreInto: "Isolated environment"
  mergeMode: "Conditional, version-aware"
  deletionAuthority: "Approved deletion ledger"
acceptance:
  missingApprovedRecoveredEntities: 0
  restoredLegitimatelyDeletedEntities: 0
  overwrittenNewerVersions: 0
  duplicatedBusinessSideEffects: 0
~~~

Các con số chỉ minh họa cách viết yêu cầu; không phải cam kết của MongoDB, DynamoDB, Cassandra hay bất kỳ hệ nào.

## 6. Chuẩn bị trước sự cố: backup và bản đồ dữ liệu

Muốn khôi phục một bản ghi trước khi bị xóa, hệ phải còn **backup, PITR, transaction log, audit history hoặc một nguồn lịch sử được phép sử dụng**. Không thể lấy lại một giá trị từ không khí sau khi mọi bản sao hợp lệ đã biến mất.

Hồ sơ tối thiểu cho một entity:

~~~yaml
entity: Customer
primaryKey: [tenantId, customerId]
sourceOfTruth: "Customer primary store"
dependentViews:
  - customer_by_email
  - customer_search
  - profile_cache
  - daily_analytics
backup:
  type: "Product-supported snapshot or PITR"
  retention: "Approved recovery window"
deletion:
  authority: "Versioned deletion intent ledger"
  propagation: "CDC/events to derived views"
recovery:
  owner: "Authorized operations team"
  mode: "Isolated restore and selective merge"
~~~

### Thử backup chứ không chỉ bật backup

Kiểm tra các câu hỏi:

- Backup bao phủ chính xác bảng/collection, index và metadata nào?
- Có phục hồi một record hay cần restore cả bảng vào tài nguyên khác?
- Có đủ log để đạt điểm PITR mong muốn không?
- Cửa sổ retention có dài hơn thời gian thường phát hiện lỗi không?
- Snapshot nhiều partition/shard có cùng logical time hay không?
- Đã lưu schema, encryption keys, thông tin phiên bản và quyền truy cập khôi phục chưa?
- Có test restore hoàn chỉnh với dữ liệu thật đã được bảo vệ chưa?
- Khi restore, deletion ledger và changes sau backup được xử lý bằng giao thức nào?

**Replication không phải backup.** Một DELETE sai có thể được sao chép rất nhanh sang mọi replica; replica tăng khả năng phục vụ khi hỏng node nhưng không tự giữ lịch sử để chọn điểm trước lỗi.

## 7. Runbook khi phát hiện xóa nhầm

### Bước 1 — Dừng nguồn gây lỗi

Tắt job hoặc chặn đường ghi đang gây DELETE sai theo quy trình quản trị, ưu tiên hành động có thể đảo. Không chạy ngay lệnh restore khi chương trình lỗi vẫn còn tiếp tục xóa dữ liệu.

Không tự dọn tombstone, tắt replica hoặc thay grace period theo phản xạ; các thao tác này có thể làm mất bằng chứng và tăng nguy cơ resurrection.

### Bước 2 — Đóng băng thông tin điều tra

Ghi:

~~~text
incidentId:
detectedAt:
suspectedStart / suspectedEnd:
affectedTenant:
knownEntityIds / keyRanges:
actor / jobVersion:
deletionOperationId:
sourceCluster / regions:
availableBackupIds:
lastKnownGoodVersion:
~~~

Thu thập audit, event offsets và transaction IDs khi có. Timestamp từ nhiều máy có thể lệch nên ưu tiên log position, version hoặc sequence có thẩm quyền khi cần xác định thứ tự.

### Bước 3 — Phân biệt delete sai và delete hợp lệ

So sánh audit log, request của người dùng, batch ID, quyền thao tác và **deletion intent**. Một backup có bản ghi không có nghĩa bản ghi đó còn được phép tồn tại.

### Bước 4 — Bảo vệ trạng thái hiện tại

Nếu có thể, tạo snapshot/trạng thái sao lưu hiện tại để đối chiếu và rollback thao tác phục hồi lỗi. Đừng ghi đè lên nguồn trước khi có kế hoạch kiểm tra những cập nhật hợp lệ sau backup.

### Bước 5 — Restore vào môi trường tách biệt

Khôi phục backup/PITR sang cluster, database, collection hoặc table **khác production**, với quyền và kết nối giới hạn. Không cho các side-effect consumer, payment job, email job tự chạy trên môi trường này.

### Bước 6 — Chọn lọc và hợp nhất có kiểm soát

Lập manifest gồm entityId, version, backup source, trạng thái hiện hành, delete intent và quyết định khôi phục. Chỉ ghi lại những bản ghi được phê duyệt, có điều kiện tránh ghi đè dữ liệu mới.

### Bước 7 — Tái tạo read model đúng cách

Cập nhật search/cache/feed theo nguồn đã hợp nhất, đồng thời giữ version/tombstone để không nhận event cũ.

### Bước 8 — Đối soát và theo dõi

Kiểm tra nguồn, replica, index, cache, event replay, failover và backup restore test. Chỉ đánh dấu hoàn tất sau khi các đường quan trọng đạt điều kiện nghiệm thu.

## 8. Vì sao không restore trực tiếp toàn snapshot vào production?

Giả sử snapshot lúc 10:00 có:

~~~text
C-42 ACTIVE v5
C-99 ACTIVE v8
C-50 ACTIVE v3
~~~

Production lúc 10:30:

~~~text
C-42 bị xóa nhầm ở 10:05.
C-99 xóa hợp lệ ở v9 lúc 10:10.
C-50 đã được cập nhật lên v4 lúc 10:15.
~~~

Restore toàn bộ snapshot có thể lấy lại C-42 nhưng cũng làm sống lại C-99 và lùi C-50 từ v4 xuống v3.

Quy trình chọn lọc tốt hơn:

~~~text
Backup restore (cách ly)
    |
    v
Candidate records
    |
    +--> Có deletion intent hợp lệ?
    |        -> không restore
    |
    +--> Production đã có generation/version mới hơn?
    |        -> không ghi đè, cần reconcile
    |
    +--> Được phê duyệt phục hồi?
             -> tạo RESTORE operation mới
             -> merge có điều kiện
~~~

**Khôi phục chọn lọc** không phải PUT lại tất cả giá trị cũ. Nó là một chuyển trạng thái nghiệp vụ có phê duyệt, với **định danh thao tác khôi phục (recoveryId)** và một version/generation mới được cấp theo authority.

## 9. Khôi phục đúng phiên bản và giữ thay đổi mới

Một record có thể thay đổi sau backup, trước khi xóa:

~~~text
09:55 Snapshot S1: C-42 v10, email cũ.
10:02 C-42 đổi email, trở thành v11.
10:06 Job lỗi xóa C-42.
10:20 Bắt đầu khôi phục.
~~~

Nếu phục hồi v10, hồ sơ quay lại nhưng **đánh mất email mới**. Nếu PITR/change log có v11, phải xem đó là điểm khôi phục chính xác hơn. Nếu chỉ có v10 và không có nguồn khác, cần công bố dữ liệu không thể khôi phục trọn vẹn; không tự báo SUCCESS như thể v11 đã được lấy lại.

### Quy tắc merge

- **Không ghi đè version mới hơn** bằng payload cũ từ backup.
- **Không tự dùng timestamp máy client** làm thứ tự authoritative nếu có clock skew.
- **Không tái sử dụng version/generation cũ** trong một RESTORE khiến consumer tưởng đây là event đến muộn.
- **Không bỏ qua các xóa hợp lệ mới hơn snapshot.**
- **Không sử dụng cùng ID cho hai vòng đời khác nhau** nếu nghiệp vụ cần phân biệt account cũ với account đăng ký mới.

Ví dụ recovery event:

~~~json
{
  "eventId": "REC-E-1200",
  "operation": "RESTORE",
  "tenantId": "T1",
  "entityId": "C-42",
  "generation": 4,
  "version": 16,
  "sourceBackup": "S1",
  "recoveryId": "INC-214"
}
~~~

Version/generation phải được cấp trong ranh giới đồng bộ phù hợp. Chỉ thêm 1 vào version cũ từ backup mà không kiểm tra nguồn hiện tại vẫn có thể tạo collision.

## 10. Soft delete như một lớp an toàn có giới hạn

Soft delete giữ bản ghi ở nguồn với trạng thái đã xóa:

~~~json
{
  "tenantId": "T1",
  "customerId": "C-42",
  "state": "DELETED",
  "deletedAt": "2026-11-14T10:05:00Z",
  "deletedBy": "cleanup-job-17",
  "deleteReason": "RETENTION",
  "version": 14
}
~~~

Ưu điểm:

- Có thể điều tra ai xóa, lúc nào và theo chính sách nào.
- Có cơ hội khôi phục xóa nhầm khi payload còn được phép giữ.
- Cho consumer biết bản ghi đã xóa để tránh upsert từ một event cũ.
- Có thể tách thời điểm **ngừng phục vụ dữ liệu** khỏi thời điểm **purge vật lý**.

Hạn chế:

- Payload vẫn tồn tại; không đáp ứng mọi yêu cầu xóa dữ liệu nhạy cảm.
- Mọi API phải áp điều kiện visibility và authorization.
- Search/cache/index có thể chưa được cập nhật.
- Một UPDATE vô điều kiện có thể đổi state về ACTIVE.
- Khi purge payload, marker chống tái xuất hiện cũng có thể mất nếu không thiết kế riêng.

### State machine gợi ý

~~~text
ACTIVE
  |
  | delete được chấp thuận
  v
DELETE_REQUESTED
  |
  | chặn phục vụ + phát sự kiện
  v
DELETED
  |
  | hết thời gian giữ, hoàn tất điều kiện purge
  v
PURGED

RESTORE:
  chỉ xảy ra khi policy cho phép, đã được phê duyệt,
  và dùng version/generation mới.
~~~

Không nên cho một endpoint thông thường được tự ý đặt **state=ACTIVE** từ DELETED. Phục hồi là thao tác có quyền riêng và phải để lại audit.

## 11. Tombstone trong Cassandra và nguy cơ resurrection

Apache Cassandra sử dụng **tombstone** để biểu diễn việc xóa theo ngữ nghĩa của hệ lưu trữ phân tán. Replica offline có thể chưa nhận dấu xóa; tombstone phải tồn tại đủ điều kiện để quá trình repair/đồng bộ truyền thông tin xóa tới replica đó trước khi tombstone được dọn.

Một kịch bản nguy hiểm:

~~~text
Replica A: K = old-value
Replica B: K = old-value
Replica C: K = old-value, sau đó offline

T1: DELETE K được A/B ghi nhận thành tombstone.
T2: C vẫn offline, giữ dữ liệu cũ.
T3: Tombstone ở A/B bị dọn sau grace/compaction
    khi C chưa từng nhận delete.
T4: C quay lại, tham gia đồng bộ/repair.
T5: Giá trị cũ ở C có thể được lan trở lại.
~~~

Đây là hiện tượng dữ liệu đã xóa **sống lại từ replica cũ**. Cơ chế và điều kiện compaction thực tế phức tạp hơn hình vẽ, nhưng nguyên tắc vận hành rất rõ: **không để replica có dữ liệu cũ trở lại khi cluster đã mất bằng chứng xóa tương ứng**.

### Những khái niệm phải hiểu

| Khái niệm | Tác động tới xóa và phục hồi |
| --- | --- |
| **gc_grace_seconds** | Khoảng grace liên quan việc tombstone có thể được dọn; không tùy ý giảm chỉ để bớt disk. |
| **Anti-entropy repair** | Giúp các replica đồng bộ dữ liệu và dấu xóa theo phạm vi sản phẩm hỗ trợ. |
| **Compaction** | Có thể xử lý SSTable, dữ liệu hết hạn và tombstone theo điều kiện. |
| **TTL expiration** | Có thể dẫn tới tombstone/trạng thái hết hạn với vòng đời riêng. |
| **Consistency level** | Ảnh hưởng cách đọc/ghi được xác nhận, không thay thế lịch repair. |
| **Hinted handoff** | Giúp một số replica tạm offline nhận thay đổi, nhưng không phải backup vô hạn hoặc thay thế repair. |

### Hành động vận hành

1. Theo dõi thời lượng node offline, lịch repair và cấu hình grace.
2. Không thay đổi **gc_grace_seconds** khi chưa đánh giá nguy cơ lost delete.
3. Thực hiện repair theo khuyến nghị đúng phiên bản, topology và workload.
4. Khi một node offline quá lâu, đánh giá **rebuild từ nguồn tin cậy** thay vì đơn giản cho node cũ hòa lại.
5. Kiểm tra cả tình huống TTL, delete range và tombstone có số lượng lớn.
6. Sau restore/failover, kiểm tra không có record đã xóa tái xuất hiện.

**Tombstone ở Cassandra bảo vệ trong phạm vi replication/repair**, không tự chặn một ứng dụng import CSV cũ hoặc một consumer upsert từ event cũ. Vì thế hệ thống còn cần cơ chế kiểm soát cấp nghiệp vụ.

## 12. Snapshot của Cassandra/ScyllaDB không phải PITR tự động

Trong Apache Cassandra, các cơ chế như snapshot SSTable và quy trình backup/restore tùy phiên bản có thể được dùng để lấy dữ liệu trước sự cố. Ví dụ một lệnh quản trị thường gặp:

~~~bash
nodetool snapshot -t before-recovery
~~~

Lệnh phải được điều chỉnh theo phiên bản, keyspace/table và quy trình vận hành thực tế. Snapshot SSTable **không mặc nhiên tạo một điểm PITR nhất quán toàn cụm đối với mọi dữ liệu nghiệp vụ**.

Khi cần khôi phục xóa nhầm:

- Xác định chính xác keyspace/table và snapshot còn chứa record.
- Giữ schema, topology và metadata phiên bản cần cho restore.
- Khôi phục vào cluster riêng trước khi chọn record.
- Đánh giá log/backup tăng dần nếu cần điểm gần thời gian xóa; **không mặc định mọi Cassandra deployment đều có PITR tùy ý**.
- Tránh copy SSTable cũ trực tiếp vào production khi có tombstone và ghi mới.
- Kiểm tra deletion ledger sau snapshot.
- Dựng lại các bảng đọc phụ, so sánh version và kiểm tra replica cũ.

ScyllaDB có công cụ backup/snapshot/repair theo sản phẩm và phiên bản; không lấy một runbook Cassandra rồi áp nguyên xi khi chưa xác minh.

## 13. MongoDB: xóa nhầm, soft delete và restore document

MongoDB hỗ trợ DELETE/UPDATE trên document với semantics của sản phẩm:

~~~javascript
db.customers.deleteOne({
  tenantId: "T1",
  customerId: "C-42"
});
~~~

Nếu muốn có vùng đệm khôi phục, một cách là dùng conditional soft delete:

~~~javascript
db.customers.updateOne(
  {
    tenantId: "T1",
    customerId: "C-42",
    state: "ACTIVE",
    version: 14
  },
  {
    $set: {
      state: "DELETED",
      deletedAt: new Date(),
      deleteReason: "USER_REQUEST"
    },
    $inc: { version: 1 }
  }
);
~~~

Mẫu này bảo vệ **một document** khỏi chuyển trạng thái dựa trên version cũ. Nó không tự xóa document trong search index, không thực hiện transaction với mọi collection khác và không thay cho chính sách purge.

### Những câu hỏi cần giải trước khi restore

- Hệ có backup/PITR nào và cửa sổ lưu giữ bao lâu?
- Có snapshot trước DELETE và log để lấy trạng thái trước xóa không?
- Đang chạy Replica Set hay Sharded Cluster; điểm khôi phục nhất quán ở phạm vi nào?
- Change stream/oplog có đủ retention/resume position không?
- Pre-images có được cấu hình và giữ đủ lâu nếu cần bản trước thay đổi không?
- Document có version mới hơn từ request khác hoặc đã được tái tạo với ID khác chưa?
- Restore có cần rebuild unique index/secondary index hoặc các relation phụ không?
- Có delete intent hợp lệ sau điểm backup không?

Không nên hiểu **oplog/change stream** như kho lịch sử giữ mọi document cũ vô thời hạn. Khả năng truy xuất pre-image và thời hạn retention phụ thuộc cấu hình và bản triển khai.

### Khôi phục một document bằng thao tác có điều kiện

~~~text
Restore DB cách ly -> tìm candidate C-42.
Kiểm tra approved recoveryId.
Kiểm tra deletion intent và production version.
Nếu được phép, ghi RESTORE với version/generation mới
bằng transaction/conditional update phù hợp.
Phát event phục hồi cho các read models.
Đối soát source, indexes, cache và quyền truy cập.
~~~

Không thay toàn document nếu chỉ một field bị mất và các field khác đã được người dùng cập nhật sau snapshot.

## 14. DynamoDB: PITR, TTL và đường merge item

Với DynamoDB, **Point-in-Time Recovery** có thể được bật cho bảng và dùng để khôi phục trong cửa sổ mà dịch vụ hỗ trợ. Quy trình restore PITR thông thường **tạo một bảng mới**, không tự ghi lại các item đơn lẻ vào bảng production. Vì vậy, phục hồi một customer vẫn cần bước lọc, đối chiếu và ghi có điều kiện.

Ví dụ item:

~~~text
PK = TENANT#T1
SK = CUSTOMER#C-42
state = ACTIVE
version = 14
~~~

Logic khôi phục không được đơn giản là PutItem vô điều kiện. Cần kiểm tra:

~~~text
approvedRecoveryId
entityId + generation
currentVersion
deletion intent hiện hành
candidateVersion từ backup
~~~

Nếu tất cả điều kiện trên nằm ở nhiều item, cần **TransactWriteItems** hoặc một giao thức phân xử có phạm vi và giới hạn được hỗ trợ. Đọc ledger tại client rồi ghi nguồn sau đó **không tự atomic**.

### DynamoDB TTL

TTL giúp hệ tự xóa item hết hạn theo cơ chế nền. Khi một item vừa vượt expiresAt:

- Nó có thể vẫn tồn tại/được đọc trong một khoảng trước khi thao tác TTL delete xảy ra.
- Ứng dụng cần tự kiểm tra tính hợp lệ về thời gian khi API yêu cầu hết hạn đúng mốc.
- Một restore từ thời điểm cũ có thể mang lại item đã hết hạn sau đó.
- Cần rà soát TTL, Streams, replication và policy của từng Region/deployment theo tài liệu phù hợp.

Khi TTL cấu hình nhầm gây xóa dữ liệu còn cần, cần **sửa chính sách TTL trước khi restore**, nếu không bản ghi vừa khôi phục có thể hết hạn lại.

## 15. Redis: cache và persistence không thể thay thế deletion authority

Redis có cơ chế snapshot/persistence như RDB và AOF theo cấu hình, cùng replication/failover. Ví dụ:

~~~redis
SET profile:T1:C-42 "payload"
DEL profile:T1:C-42
UNLINK profile:T1:C-99
~~~

**DEL** xóa key theo ngữ nghĩa Redis; **UNLINK** tách key khỏi keyspace rồi giải phóng bộ nhớ theo cách phù hợp. Cả hai không có nghĩa dữ liệu đã biến mất khỏi mọi RDB/AOF/backup đã tạo trong quá khứ.

Nếu Redis là cache:

- Ưu tiên invalidate/rebuild từ nguồn đã đối soát thay vì restore cache cũ.
- Không cho cache có quyền ghi ngược bản cũ vào nguồn.
- Negative cache cho NOT_FOUND phải được invalidated khi một RESTORE hợp lệ diễn ra.
- Kiểm tra TTL không làm hồi sinh một session/profile đã bị hủy.
- Nếu cache key được tái tạo từ event, consumer phải kiểm tra version/deletion intent.

Nếu Redis giữ dữ liệu nguồn quan trọng, phải có chính sách persistence, backup, RPO và trình tự phục hồi cụ thể. Không mặc định replica tương đương một lịch sử đầy đủ hay file RDB cũ an toàn để nạp thẳng production.

## 16. Search index và read model sau sự cố

Một customer có thể xuất hiện ở nhiều nơi:

~~~text
customers                  — nguồn
customers_by_email         — lookup phụ
customer_search            — tìm kiếm
customer_orders_feed       — danh sách
profile_cache              — Redis
customer_analytics         — báo cáo
~~~

Khôi phục riêng document nguồn chưa đủ nếu các đường đọc phụ vẫn trả NOT_FOUND hoặc thông tin cũ. Ngược lại, nếu xóa hợp lệ, việc chỉ xóa nguồn không đủ khi search index vẫn có thể tìm theo email.

Cần đặt **deletion propagation contract**:

| Hệ | Xóa hợp lệ | RESTORE được duyệt |
| --- | --- | --- |
| **Nguồn** | Mark/delete theo version và policy | Chuyển trạng thái có thẩm quyền, version mới |
| **Replica** | Đồng bộ marker/xóa | Theo version/consistency được công bố |
| **Cache** | Evict và chặn tái nạp bản cũ | Invalidate negative cache, nạp nguồn mới |
| **Search** | Delete/upsert tombstone có version | Reindex từ nguồn đã duyệt |
| **Read model** | Gỡ entry theo khóa truy vấn | Tạo lại entry phù hợp, không nhân đôi |
| **Analytics** | Áp policy xóa và retention | Chỉ dựng lại phần được phép |
| **Event consumer** | Chặn CREATE/UPDATE cũ | Nhận RESTORE hợp lệ có version/generation mới |

**Reindex từ nguồn cũ** là một phép thử bắt buộc nếu index có thể được rebuild từ snapshot hoặc event log chứa bản ghi trước DELETE.

## 17. Deletion ledger: hàng rào chống dữ liệu cũ

Khi dữ liệu nguồn bị hard delete hoặc purge, có thể không còn document để biết rằng nó đã từng bị xóa. Một **deletion intent ledger** lưu metadata tối thiểu để chặn việc nhập lại bản cũ:

~~~json
{
  "tenantId": "T1",
  "entityId": "C-99",
  "generation": 3,
  "deletionId": "DEL-9001",
  "deleteVersion": 18,
  "deletedAt": "2026-11-14T10:10:00Z",
  "reasonCode": "APPROVED_DELETION",
  "state": "ACTIVE_DELETION"
}
~~~

Một consumer có thể dùng quy tắc:

~~~text
Khi nhận CREATE/UPDATE/import:
    xác định entityId và generation.
    đọc marker có thẩm quyền.
    nếu incomingVersion <= deleteVersion
       và marker còn hiệu lực:
        bỏ qua hoặc từ chối.

Khi nhận RESTORE:
    phải có recovery approval và thao tác mới.
    chỉ thực thi với version/generation được phân xử.
~~~

### Quan trọng: kiểm tra rồi ghi có thể bị race

Nếu consumer đọc ledger từ database A và ghi record sang database B, một DELETE mới có thể đến giữa hai bước. Vì vậy **một lần kiểm tra ledger trước khi ghi chưa đủ** để bảo vệ tuyệt đối dưới tranh chấp. Cần:

- Một authority phân xử version/xóa có thể áp conditional write/transaction.
- Một protocol đảm bảo mọi writer tuân cùng hàng rào version.
- Hoặc trạng thái trung gian/repair và reconciliation đủ để đạt hợp đồng nhất quán đã chọn.

Deletion ledger **không phải phép màu** tạo atomic transaction giữa mọi dịch vụ. Nó cung cấp dấu vết có thẩm quyền để hệ có thể từ chối sự kiện cũ và đối soát dữ liệu bị sống lại.

### Giữ marker trong bao lâu?

Thời gian giữ phải xét:

- Backup cũ nhất còn được phép restore.
- CDC/event log và khả năng replay.
- Thiết bị offline có thể gửi thay đổi cũ trong bao lâu.
- ID/generation có thể tái sử dụng hay không.
- Quy định retention, xóa dữ liệu nhạy cảm và legal hold nếu có.
- Khả năng import từ dữ liệu lịch sử không kiểm soát.

Có thể giữ **metadata tối thiểu** thay vì payload đã xóa; nhưng metadata/hashes vẫn cần được đánh giá về quyền riêng tư. Không tự mặc định lưu marker vô thời hạn là hợp lệ.

## 18. Version và thứ tự event trong một pipeline bất đồng bộ

Ví dụ:

~~~text
v10 CREATE C-99
v12 UPDATE C-99
v18 DELETE C-99

Consumer nhận:
    v10 -> v12 -> v18 -> v12 (phát lại)
~~~

Nếu event UPDATE được xử lý bằng upsert vô điều kiện, event v12 cuối có thể **tạo lại C-99**. Cần lưu phiên bản áp dụng cuối:

~~~text
projectionState:
    entityId = C-99
    generation = 3
    lastAppliedVersion = 18
    deleted = true

Nhận v12:
    bỏ qua vì 12 <= 18

Nhận RESTORE v19:
    chỉ chấp nhận nếu có recovery authorization hợp lệ.
~~~

Một số lưu ý:

- **Version theo từng entity** không phải cùng một global timestamp.
- Không dùng timestamp từ client có clock skew để quyết định sự kiện nào thắng nếu không có giao thức ordering.
- Nếu event chỉ chứa **delta** chứ không có full state, nhảy qua một version có thể thiếu dữ liệu; cần phát hiện gap và replay hoặc đọc nguồn.
- Version phải tăng theo giao thức nguồn, kể cả khi entity đã hard delete rồi tạo lại.
- Khi ID được tái sử dụng, cần **generation/incarnation** tránh gắn event của tài khoản cũ sang tài khoản mới.
- Replay CREATE/UPDATE không được gọi lại side effect như thanh toán, gửi email nếu đó chỉ là quá trình dựng read model.

## 19. Soft delete, hard delete và dữ liệu cần xóa theo chính sách

Đôi khi mục tiêu khôi phục và mục tiêu xóa có vẻ mâu thuẫn:

- Soft delete dài ngày giúp sửa lỗi dễ.
- Hard delete sớm giảm thời gian payload còn tồn tại.
- Backup retention dài giúp lấy lại lỗi muộn.
- Backup cũ lại có thể chứa dữ liệu đã xóa hợp lệ.

Không có một thời hạn phù hợp cho tất cả. Cần quy định theo **loại dữ liệu**, mức độ nhạy cảm, giá trị nghiệp vụ, yêu cầu phục hồi và chính sách retention hiện hành.

### Một mô hình phân tầng

~~~text
ACTIVE
  |
  v
DELETE_REQUESTED
  |
  | chặn phục vụ, ghi intent, phát event
  v
DELETED
  |
  | thực hiện purge theo policy
  v
PURGED
~~~

**RESTORE** là chuyển trạng thái riêng có phê duyệt, chỉ được thực hiện khi policy cho phép. Khi dữ liệu đã bị purge theo yêu cầu hợp lệ, **không được dùng một bản backup cũ để tùy ý phục hồi payload**.

Nếu có yêu cầu pháp lý về xóa/giữ lại, cần theo chính sách tổ chức và thẩm quyền phù hợp. Bài học này không thay thế việc xác định nghĩa vụ cụ thể theo luật hoặc hợp đồng.

## 20. Lưu ý về quyền khôi phục và audit

Một thao tác restore có thể tạo hậu quả tương đương thao tác ghi dữ liệu nhạy cảm vào production. Nên có:

~~~json
{
  "recoveryId": "REC-2026-001",
  "incidentId": "INC-214",
  "tenantId": "T1",
  "entityId": "C-42",
  "sourceBackupId": "S1",
  "expectedCurrentVersion": 15,
  "approvedBy": "authorized-operator",
  "reason": "Accidental deletion verified"
}
~~~

Bắt buộc xác định:

1. Ai có quyền yêu cầu và phê duyệt recovery?
2. Có cần phê duyệt độc lập cho dữ liệu nhạy cảm không?
3. Tập entity nào được phép restore?
4. Delete intent và version hiện tại có được kiểm tra ngay trước commit không?
5. RecoveryId có idempotent khi operator nhấn lại hoặc client retry không?
6. Ai chịu trách nhiệm kiểm tra dữ liệu phụ và downstream side effects?
7. Audit ghi rõ backup, thời gian, actor và kết quả từng bước chưa?
8. Đã cô lập quyền truy cập dữ liệu trong môi trường restore chưa?

Không cho phép một API thông thường đổi state DELETED thành ACTIVE chỉ bằng cách gửi body cập nhật.

## 21. Dữ liệu có quan hệ: khôi phục parent không đủ

Một customer có thể có:

~~~text
Customer
   +-- Preferences
   +-- Addresses
   +-- Orders
   +-- Payment references
   +-- Support tickets
   +-- Search/read models
~~~

Nếu customer bị xóa nhầm cùng một số document con, chỉ phục hồi parent có thể tạo **tham chiếu thiếu**. Nhưng phục hồi toàn bộ các record con cũng có thể làm sống lại những dữ liệu đã được xóa hợp lệ từ trước.

| Loại dữ liệu | Quy tắc xem xét |
| --- | --- |
| **Owned children** | Có cùng sự cố xóa nhầm hay có vòng đời riêng? |
| **Shared references** | Entity đích còn tồn tại và có quyền liên kết lại không? |
| **Immutable ledger** | Phải giữ bản gốc/audit; không phát lại tác động tài chính. |
| **Read model** | Có thể dựng lại từ nguồn đã đối soát không? |
| **Cache** | Có thể invalidate rồi nạp lại thay vì phục hồi? |
| **External side effects** | Email, payment, webhook có bị kích hoạt lại không? |

Một event **RESTORED_FOR_RECOVERY** nên được phân biệt với event **ORDER_CREATED** hoặc **PAYMENT_CAPTURED**, tránh consumer phát sinh thanh toán/gửi thư lần hai khi chỉ cần tái tạo dữ liệu đọc.

## 22. Kiểm chứng dữ liệu không tái xuất hiện phải có manifest

Trước khi chạy restore, lập hai tập:

~~~text
approvedRecoveryManifest:
    entityId, tenantId, generation,
    approvedVersion, backupSource, recoveryId

protectedDeletionManifest:
    entityId, tenantId, generation,
    deleteVersion, deletionId, reasonCode
~~~

Sau khi phục hồi:

- Tất cả entity trong recovery manifest phải được xử lý theo kết quả được duyệt.
- Không entity nào trong protected deletion manifest xuất hiện lại ở trạng thái được phục vụ.
- Không có version hợp lệ mới hơn bị ghi đè.
- Không có tác động nghiệp vụ bị thực hiện hai lần.
- Các read model và index phải đạt trạng thái phù hợp với nguồn.
- Những trường hợp không có dữ liệu backup đủ để phục hồi phải được ghi **PARTIAL/UNRECOVERABLE**, không được im lặng bỏ qua.

Một con số COUNT đúng **không đủ**: có thể mất C-42 nhưng lại sống lại C-99, khiến tổng số bản ghi vẫn như cũ. Cần đối chiếu **tập định danh, version và trạng thái từng entity**.

## 23. Các lớp kiểm tra sau khôi phục

| Lớp | Cách kiểm tra | Nguy cơ nếu bỏ qua |
| --- | --- | --- |
| **Source of truth** | Lookup theo khóa, state và version | Dữ liệu sai ngay tại nguồn. |
| **Replica** | Đọc theo consistency/Region được quy định | Node cũ phục vụ dữ liệu đã xóa. |
| **Cache** | Kiểm tra key cũ và negative cache | Trả profile cũ hoặc che profile phục hồi. |
| **Secondary index** | Query theo email, phone, status, ID | Entry cũ vẫn có mặt. |
| **Search** | Tìm theo nhiều thuộc tính sau refresh/reindex | Dữ liệu hồi sinh do rebuild. |
| **Read model** | Các danh sách theo tenant/customer | Dòng phụ không được xóa hoặc tạo đúng. |
| **CDC consumer** | Replay event cũ có chủ đích | UPDATE cũ upsert dữ liệu đã xóa. |
| **Backup** | Restore bản cũ bằng runbook chuẩn | Deletion intent bị bỏ qua. |
| **Analytics/export** | Đối chiếu theo policy retention | Dữ liệu bị xóa còn được phục vụ qua đường phụ. |
| **Client offline** | Đồng bộ local copy cũ | Ghi lại generation không hợp lệ. |

Cần kiểm tra **nhiều thời điểm**: ngay sau commit xóa, sau khi downstream catch-up, sau cache TTL/refresh, sau failover/repair, sau rebuild/replay và sau một lần restore test.

## 24. Test chống resurrection: replica offline

Kịch bản minh họa trong môi trường kiểm thử an toàn:

~~~text
1. Tạo key K version 1; xác nhận replica nhận bản ghi.
2. Cho một replica offline theo kịch bản đã được duyệt.
3. Xóa K ở phần cụm đang hoạt động.
4. Đợi một khoảng mô phỏng downtime và repair window.
5. Đưa replica trở lại theo đúng quy trình sản phẩm.
6. Chạy repair/rebuild cần thiết.
7. Đọc K qua các đường được hỗ trợ.
8. K phải tiếp tục bị xóa theo hợp đồng.
~~~

Đối với Cassandra, phải đặc biệt xem **gc_grace_seconds**, compaction và repair. Không thử thao tác có nguy cơ mất dữ liệu lên production ngoài kế hoạch fault-injection có phê duyệt.

## 25. Test chống resurrection: backup cũ

~~~text
1. Tạo A và B.
2. Chụp backup S có cả hai.
3. Xóa A hợp lệ, lưu deletion intent.
4. Xóa nhầm B.
5. Restore S vào khu vực cách ly.
6. Chọn B để phục hồi, giữ A trong danh sách cấm.
7. Merge bằng version và recoveryId mới.
8. Reindex/replay và kiểm tra A không xuất hiện trở lại.
~~~

Test nên so sánh cả **dữ liệu và audit**, không chỉ API trả đúng số dòng.

## 26. Test chống resurrection: event đến sai thứ tự

~~~text
E1: CREATE X v1
E2: UPDATE X v2
E3: DELETE X v3

Thứ tự nhận:
    E1 -> E2 -> E3 -> E2

Expected:
    X vẫn DELETED v3.
    Consumer không upsert từ v2.
    Cache và search không chứa X.
~~~

Mở rộng kịch bản để thử hai consumer chạy đồng thời, event trùng sau timeout, và event v4 có cùng entityId nhưng generation khác.

## 27. Test chống resurrection: TTL và cache

~~~text
1. Tạo item Y với expiresAt hợp lệ.
2. Cho Y hết hiệu lực.
3. Restore từ backup trước expiresAt.
4. Kiểm tra API không phục vụ Y đã hết hạn.
5. Đảm bảo TTL/cleanup sẽ xử lý Y theo policy.
6. Kiểm tra cache và search không giữ Y sau catch-up.
~~~

Đối với DynamoDB TTL hoặc các tác vụ xóa nền, item có thể còn tồn tại một thời gian sau expiresAt; ứng dụng phải kiểm tra hiệu lực khi nghiệp vụ yêu cầu hết hạn đúng mốc.

## 28. Test chống resurrection: reindex và client offline

Hai phép thử thường bị bỏ qua:

**Reindex từ dữ liệu cũ:**

~~~text
Source: X đã DELETE v8.
Backfill snapshot: X còn ACTIVE v5.
Job index nhận X v5.

Expected:
    ledger/version fence chặn X v5.
    search không thấy X sau reindex.
~~~

**Client đồng bộ sau thời gian dài offline:**

~~~text
Mobile có X ACTIVE v2.
Server xóa X v5.
Mobile online, gửi UPDATE X v3.

Expected:
    server từ chối stale generation/version.
    X không hồi sinh từ bản cache của thiết bị.
~~~

Nếu cho phép tạo lại một tài khoản với cùng ID/email, phải phân biệt **entity mới** và **entity cũ** bằng generation/incarnation theo chính sách hệ.

## 29. Kịch bản tổng hợp: khôi phục hồ sơ và giữ xóa hợp lệ

Một hệ bán hàng có:

~~~text
customers             — nguồn
customers_by_email    — bảng đọc phụ
customer_search       — search
profile_cache         — Redis
customer_changes      — event stream
deletion_intents      — ledger
backups               — snapshot và log
~~~

Timeline:

~~~text
09:55 Snapshot S-0955: C-42 v10, C-99 v20.
10:02 C-42 đổi số điện thoại, v11.
10:04 C-99 được xóa hợp lệ, delete v21.
10:06 Cleanup job lỗi xóa C-42.
10:08 Phát hiện sự cố.
10:12 Search consumer nhận lại UPDATE C-99 v19.
~~~

### Phân tích

**C-42** là candidate cần phục hồi, nhưng snapshot chứa v10, trong khi phiên bản hợp lệ gần nhất trước DELETE là v11. Nếu log/PITR có v11 thì khôi phục v11; nếu không có, phải ghi nhận khoảng mất dữ liệu.

**C-99** không được phép phục hồi vì có deletion intent v21. Event UPDATE v19 cũng phải bị chặn dù đến sau khi đã xóa.

### Quy trình

1. Dừng cleanup job và bảo toàn log.
2. Restore S-0955 vào môi trường cách ly; tìm thêm log/PITR cho C-42 v11.
3. Đối chiếu deletion_intents; đánh dấu C-99 là PROTECTED_DELETE.
4. Tạo recovery manifest cho C-42 với approval.
5. Merge có điều kiện với version/generation mới, không ghi đè mọi bản ghi từ snapshot.
6. Phát RESTORED event, chỉ cập nhật những read model cần thiết.
7. Invalidate Redis negative cache của C-42 nếu đang ghi nhớ NOT_FOUND.
8. Kiểm tra C-99 qua source, search, cache, feed và replay v19.
9. Kiểm tra các quan hệ, đơn hàng và quyền truy cập của C-42.
10. Lưu bằng chứng kết quả, sai lệch còn lại và trách nhiệm follow-up.

Không được phát lại nghiệp vụ **payment captured** hoặc **send welcome email** chỉ vì đang dựng lại search/read model.

## 30. Đánh giá bằng đối soát chứ không chỉ COUNT

Sau merge, kiểm tra:

- **Membership:** những key cần phục hồi có mặt, những key phải xóa vẫn vắng mặt.
- **Version/generation:** không bản cũ nào ghi đè trạng thái mới.
- **Field-level data:** các field được phép khôi phục khớp nguồn được duyệt.
- **References:** không có orphan hoặc liên kết tới incarnation cũ không còn hợp lệ.
- **Business state:** không có order/payment/reservation được thực hiện lại sai.
- **Read models:** index/search/cache đã đồng bộ với nguồn và deletion ledger.
- **Replica:** khi repair/failover, record bị xóa không tái xuất hiện.
- **Recovery audit:** có đầy đủ incidentId, backupId, actor, version và kết quả.

Có thể dùng checksum/hash để phát hiện khác biệt nhưng phải chuẩn hóa dữ liệu và chỉ so cùng snapshot/watermark. Checksum tổng không thay thế kiểm tra từng entity cần giữ ở trạng thái deleted. Hơn nữa, hash định danh có thể vẫn mang rủi ro riêng tư, không mặc định xuất ra log công khai.

## 31. Chỉ số vận hành và SLO

Các metric hữu ích:

~~~text
accidental_delete_detected_total
approved_restore_total
recovery_conflicts_total
recovery_missing_entities
newer_versions_overwritten
deletion_propagation_lag_seconds
resurrected_deleted_entities_total
stale_event_replays_rejected_total
cdc_oldest_unprocessed_event_age_seconds
search_deletion_backlog
replica_repair_health
backup_restore_success_total
reconciliation_mismatch_entities
~~~

Một ma trận nghiệm thu **minh họa**:

| Mã | Điều kiện | Cách kiểm tra |
| --- | --- | --- |
| AC-01 | Không thiếu entity trong tập được duyệt khôi phục | Đối chiếu recovery manifest. |
| AC-02 | Không có entity xóa hợp lệ bị sống lại | Đối chiếu deletion manifest ở mọi đường đọc. |
| AC-03 | Không ghi đè phiên bản mới hơn | So version/generation trước và sau merge. |
| AC-04 | Event cũ không được upsert sau DELETE | Replay v1/v2/DELETE/v2. |
| AC-05 | Replica cũ quay lại không phục hồi bản ghi bị xóa | Diễn tập node offline/repair. |
| AC-06 | Không có side effect tài chính/email chạy lại | Kiểm tra operationId và audit tác động. |
| AC-07 | Search/cache đạt freshness SLO | Đo thời gian propagation và query sau catch-up. |
| AC-08 | Khôi phục đạt RTO/RPO đã phê duyệt | Diễn tập trên backup và dataset đại diện. |
| AC-09 | Restore test không bỏ qua deletion intents | Restore snapshot trước xóa rồi merge. |
| AC-10 | Có bằng chứng rollback/khắc phục nếu merge lỗi | Kiểm tra runbook và audit. |

Khi tiêu chí xóa hợp lệ là **không được tái xuất hiện**, một lỗi resurrection không thể được bù bằng p95 latency tốt hoặc bằng tỷ lệ đúng 99,9%. Đây là điều kiện về **tính đúng và tuân thủ chính sách**, không chỉ chất lượng hiệu năng.

## 32. Đánh đổi retention và khả năng khôi phục

| Lựa chọn | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Backup giữ lâu | Có thể phát hiện lỗi muộn vẫn phục hồi | Giữ nhiều bản sao chứa dữ liệu đã xóa; phải lọc restore. |
| PITR cửa sổ gần | Có cơ hội lấy version sát sự cố | Cần dịch vụ/log và giới hạn cửa sổ thực. |
| Soft delete | Dễ đảo xóa nhầm khi còn payload | Dữ liệu vẫn tồn tại, cần quyền và purge policy. |
| Hard delete sớm | Giảm thời gian payload hiện diện | Khó cứu xóa nhầm nếu không còn nguồn được phép. |
| Tombstone đủ lâu | Giảm nguy cơ replica cũ gây resurrection | Tốn disk/compaction; cần repair. |
| Deletion ledger | Chặn restore/replay cũ | Cần retention, version authority và bảo vệ metadata. |
| Rebuild read model | Lấy kết quả từ nguồn đã đối soát | Tốn thời gian và có thể làm tăng tải nguồn. |

Không có một retention “mặc định tốt nhất” cho mọi entity. Phải phân loại dữ liệu, chính sách xóa/giữ, cửa sổ backup, tải vận hành và yêu cầu phục hồi theo bối cảnh sản phẩm.

## 33. Các sai lầm thường gặp

**“Có snapshot mới nhất là có thể restore an toàn.”** Snapshot có thể cũ hơn delete hợp lệ và các cập nhật mới hơn. Cần merge chọn lọc và version.

**“Replica còn bản ghi cũ thì cứ đưa vào cụm.”** Có thể làm mất dấu xóa và lan dữ liệu đã bị xóa hợp lệ.

**“Xóa ở primary là xong.”** Cache, search, replica, data lake và thiết bị offline có thể còn bản cũ.

**“TTL đã hết thì dữ liệu biến mất khỏi tất cả nơi lưu.”** Thời gian hết hiệu lực và thời gian dọn vật lý không nhất thiết trùng.

**“Dọn tombstone càng sớm càng tốt.”** Dọn quá sớm có thể làm replica cũ gây resurrection.

**“Đã xóa source nên reindex không thể tái tạo record.”** Reindex từ snapshot cũ vẫn có thể mang record quay lại.

**“UPDATE event cứ upsert, rồi eventual consistency sẽ tự sửa.”** Event cũ có thể đến sau DELETE và làm hồi sinh record nếu thiếu version fence.

**“Chỉ so số dòng trước và sau.”** Tập đúng có thể bị thay bằng tập sai với cùng cardinality.

**“Phục hồi hồ sơ cần phát lại toàn bộ event cũ.”** Điều đó có thể kích hoạt payment/email/side effects lần nữa.

**“Chỉ cần xóa deletedAt để phục hồi.”** Phải có phê duyệt, kiểm tra delete intent và version.

**“Một lần GET NOT_FOUND chứng minh vĩnh viễn không tái xuất hiện.”** Chưa thử failover, replay, restore và reindex.

**“Backup giữ vô thời hạn luôn tốt.”** Phải cân nhắc retention, bảo mật và nghĩa vụ xóa dữ liệu theo chính sách.

## 34. Bài thực hành: phân biệt dữ liệu được phục hồi và dữ liệu phải tiếp tục xóa

Một hệ quản lý thành viên có các thành phần:

~~~text
members                — nguồn
members_by_email       — read model
member_search          — index
member_cache           — Redis
member_changes         — event stream
deletion_intents       — deletion ledger
daily_backups          — snapshots + log hỗ trợ
~~~

Timeline:

~~~text
09:00 Snapshot S1:
    M-10 ACTIVE v4
    M-20 ACTIVE v7
    M-30 ACTIVE v2

09:15 M-10 đổi email, version 5.
09:20 M-20 được xóa hợp lệ, version 8.
09:30 Cleanup job xóa nhầm M-10 và M-30.
09:40 Dừng job.
10:00 Search consumer phát lại UPDATE M-20 version 6.
~~~

### Yêu cầu

1. Xác định tập được phép restore và tập phải tiếp tục bị xóa.
2. Nêu vì sao không thể restore nguyên S1 vào production.
3. Tìm cách lấy **M-10 v5**, thay vì chỉ v4 trong snapshot.
4. Thiết kế recovery manifest, deletion manifest và idempotency key.
5. Nêu quy tắc chặn UPDATE M-20 v6 sau DELETE v8.
6. Quyết định những read model/index nào nên rebuild từ nguồn.
7. Mô tả cách invalidation negative cache của M-10.
8. Đề xuất kiểm tra replica offline rồi quay lại.
9. Nêu trường hợp không đủ log để phục hồi dữ liệu sau snapshot.
10. Viết điều kiện nghiệm thu để không có M-20 trong kết quả sau reindex/replay.

### Lời giải định hướng

- **M-10:** phục hồi từ nguồn gần nhất v5 nếu còn PITR/log; nếu không, công bố phần mất dữ liệu theo RPO.
- **M-30:** phục hồi từ backup v2 sau khi xác minh không có delete intent hợp lệ mới hơn.
- **M-20:** tiếp tục bị xóa theo version 8; mọi event cũ như v6 phải bị chặn.
- **Read models:** dựng lại từ nguồn đã được merge và ledger, không lấy index cũ làm nguồn thẩm quyền.
- **Cache:** invalidate key cũ/negative cache và tái nạp có version.
- **Phép thử:** replay event, reindex từ snapshot, failover/repair và đối chiếu từng ID trước khi đóng incident.

## 35. Quy trình quyết định tổng hợp

~~~mermaid
flowchart TD
    A[Phát hiện dữ liệu bị xóa nhầm] --> B[Dừng nguồn lỗi và giữ bằng chứng]
    B --> C[Xác định entity, version và deletion intents]
    C --> D{Có backup/PITR phù hợp?}
    D -->|Có| E[Restore vào khu vực cách ly]
    D -->|Không| F[Đánh giá log/nguồn khác, ghi giới hạn RPO]
    E --> G[Đối chiếu xóa hợp lệ và ghi mới]
    F --> G
    G --> H{Được phép phục hồi?}
    H -->|Không| I[Giữ trạng thái xóa và chặn dữ liệu cũ]
    H -->|Có| J[Approved RESTORE với version/generation mới]
    J --> K[Merge có điều kiện]
    K --> L[Đồng bộ index/cache/read models]
    I --> L
    L --> M[Thử replay, reindex, replica và failover]
    M --> N[Đối soát key, version, quyền và dữ liệu]
    N --> O[Đóng incident khi đạt nghiệm thu]
~~~

Quy tắc cốt lõi:

1. **Không khôi phục trực tiếp toàn backup lên production** khi chưa phân tích thay đổi sau snapshot.
2. **Không phục hồi một bản ghi chỉ vì backup còn lưu nó**; phải kiểm tra ý định xóa hiện hành.
3. **Không để replica, importer, cache hoặc consumer tự vượt qua hàng rào version.**
4. **Không giảm tombstone grace hoặc đưa replica stale trở lại tùy tiện.**
5. **Không replay những side effect nghiệp vụ không idempotent** khi dựng lại dữ liệu đọc.
6. **Không tuyên bố phục hồi đầy đủ khi còn mất phiên bản hoặc dependent record.**
7. **Không kết luận dữ liệu xóa sẽ không tái xuất hiện chỉ bằng một lần GET.**
8. **Phải có test restore và test chống resurrection định kỳ**, kèm kết quả audit và reconciliation.

## Kết luận

Khôi phục dữ liệu xóa nhầm trong NoSQL không chỉ là copy một record từ backup. Đó là bài toán về **ý định xóa, lịch sử phiên bản, quyền phục hồi, tính nhất quán giữa nhiều bản sao và các luồng thay đổi dữ liệu**. Snapshot/PITR có thể lấy lại trạng thái cũ, nhưng cũng có thể ghi đè cập nhật mới hoặc làm sống lại những record đã được xóa hợp lệ. Tombstone bị dọn quá sớm, replica cũ, sự kiện CDC đến muộn, reindex và cache là những nguồn resurrection quan trọng.

Một quy trình an toàn phải **khôi phục trong môi trường cách ly**, đối chiếu **recovery manifest và deletion intents**, merge có điều kiện theo version/generation, cập nhật lại các đường đọc, rồi kiểm chứng qua **replay, failover, repair, reindex và restore test**. Khôi phục thành công nghĩa là **lấy lại đúng dữ liệu được phép lấy lại, giữ nguyên mọi thay đổi hợp lệ và chứng minh dữ liệu đã xóa hợp lệ không bị tái xuất hiện**.

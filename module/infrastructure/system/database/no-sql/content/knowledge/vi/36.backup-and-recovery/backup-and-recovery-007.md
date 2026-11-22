# Bao gồm schema, cấu hình, quyền và khóa mã hóa trong kế hoạch bảo vệ

Một doanh nghiệp lưu đơn hàng trong MongoDB, sự kiện trong Cassandra, cache trong Redis và một số bảng nghiệp vụ trên DynamoDB. Nhóm vận hành đặt lịch snapshot thành công mỗi đêm, lưu nhiều bản sao ở vùng khác và tự tin rằng **dữ liệu đã được bảo vệ**. Một ngày, một thao tác sai làm hỏng cụm chính. Nhóm dựng môi trường mới và phục hồi snapshot, nhưng ứng dụng vẫn không hoạt động:

- Dữ liệu MongoDB còn nguyên nhưng **unique index, validator và cấu hình đọc/ghi** chưa được tái tạo đúng; ứng dụng ghi dữ liệu trùng.
- Các bảng Cassandra được dựng lại với **replication strategy và datacenter names khác**, khiến consistency level đang dùng không hoạt động như trước.
- Redis khôi phục các keys nhưng **ACL, TLS và cluster topology** chưa có nên Java services không kết nối được.
- IAM của dịch vụ mới không có quyền đọc backup hoặc giải mã bằng **KMS key cũ**.
- Một khóa mã hóa từng bảo vệ backup đã bị hủy sau đợt key rotation; tệp backup còn tồn tại nhưng không thể giải mã.
- CDC consumers không có checkpoint tương thích, làm projection và search index thiếu dữ liệu dù cơ sở dữ liệu chính đã phục hồi.

**Có bản sao bytes không đồng nghĩa có khả năng phục hồi dịch vụ.** Cần bảo vệ toàn bộ những thứ mà dữ liệu phụ thuộc để có thể được giải mã, hiểu đúng, truy cập đúng quyền, đặt đúng topology và đưa trở lại một trạng thái nghiệp vụ nhất quán.

Bài học thuộc chương **Sao lưu và phục hồi**, module **Database No SQL**. Ta sẽ xây dựng kế hoạch bảo vệ cả **data, schema, cấu hình, identity/quyền, khóa mã hóa, metadata sao lưu và các phụ thuộc downstream**. Nội dung áp dụng cho NoSQL tự quản lý lẫn dịch vụ managed, với ví dụ MongoDB, Cassandra, Redis, DynamoDB và CouchDB.

> **Câu hỏi kiểm chứng cốt lõi:** Nếu mất toàn bộ cụm chính, người vận hành có thể dựng một môi trường tin cậy mới, đọc được backup, tái tạo schema/topology, cấp đúng quyền, giải mã được dữ liệu và đưa ứng dụng trở lại SLO trong RTO/RPO đã cam kết không?

Những giá trị thời gian và cấu hình minh họa trong bài **không phải chính sách mặc định hay cam kết của bất kỳ dịch vụ nào**. Cần kiểm hướng dẫn phiên bản, giới hạn dịch vụ, security policy và luật/hợp đồng áp dụng cho môi trường thực.

## 1. Khác biệt giữa “backup dữ liệu” và “bảo vệ khả năng phục hồi”

**Backup dữ liệu** trả lời câu hỏi: “Có bản sao các records, files, snapshots hoặc logs không?”

**Bảo vệ khả năng phục hồi** phải trả lời thêm:

1. Có đủ **schema, indexes, validators, constraints, view và metadata** để hiểu dữ liệu?
2. Có đúng **cấu hình hệ thống, replication, consistency, durability, storage và topology**?
3. Có tái tạo được **users, roles, IAM/ACL, service identities và network trust**?
4. Có còn **khóa giải mã, key references, KMS/HSM access và secret rotation history** cần thiết?
5. Có đủ **snapshot/log chain, checkpoint, manifest, checksums và source versions**?
6. Có đủ **application/driver version và migration history** tương thích?
7. Có thể khôi phục **streams, projections, indexes và dependent services**?
8. Có thể **kiểm chứng** dữ liệu sau restore và giữ RPO/RTO?

Một câu “backup job xanh” chưa chứng minh bất kỳ điều nào trong những bước sau đó.

## 2. Những thành phần tối thiểu của một bộ bảo vệ

| Thành phần | Ví dụ | Nếu thiếu khi restore |
|---|---|---|
| Dữ liệu | Snapshot, collection dump, SSTables, RDB/AOF | Không có business state |
| Log phục hồi | WAL, oplog, commit log, PITR chain | Có thể vượt RPO hoặc không replay được |
| Schema | Collections/validators, keyspaces/tables, data types | Không đọc/ghi đúng định dạng |
| Indexes/views | Unique/TTL/compound index, materialized views | Truy vấn chậm hoặc vi phạm logic |
| Cấu hình | RF, consistency, cache, retention, cluster settings | Semantics thay đổi |
| Topology | Shards, slots, token ranges, AZ/DC placement | Thiếu replica, sai phân phối |
| Danh tính | Roles, IAM policies, ACL, certificates | Access denied hoặc mở quyền quá mức |
| Khóa mã hóa | KMS/HSM key dependency, key versions, wrapped DEKs | Có backup nhưng không giải mã |
| Secrets | Database credentials, service certificates, references | Application không kết nối |
| Manifest | Version, hash, snapshot time, source scope | Không biết bản sao gồm gì |
| Dependencies | CDC offsets, outbox, search projection, application config | State không đồng bộ |
| Runbook | Restore order, owners, stop conditions | Khôi phục ứng biến, không đúng RTO |

Các thành phần trên **không nhất thiết nằm trong cùng một file**. Thực tế nên có các hệ quản lý chuyên trách như source-controlled infrastructure-as-code, secret manager, identity provider, KMS và backup catalog. Nhưng kế hoạch phục hồi phải **chỉ ra rõ chúng được tìm ở đâu, bảo vệ ra sao và thứ tự khôi phục**.

## 3. Sơ đồ phụ thuộc của phục hồi

~~~mermaid
flowchart TD
    ID["Danh tính phục hồi / quyền break-glass"] --> KMS["KMS/HSM và khóa giải mã"]
    ID --> STORE["Backup storage và catalog"]
    KMS --> DECRYPT["Giải mã snapshot/log"]
    STORE --> DECRYPT
    IAC["IaC, topology, network, version"] --> CLUSTER["Dựng NoSQL cluster"]
    SECRETS["Secret manager / certificates"] --> CLUSTER
    DECRYPT --> RESTORE["Restore data + log chain"]
    CLUSTER --> RESTORE
    SCHEMA["Schema / validator / index definitions"] --> RESTORE
    RESTORE --> VALID["Kiểm tính đúng và RPO"]
    POLICY["IAM/ACL roles và service bindings"] --> APP["Application và drivers"]
    VALID --> APP
    APP --> REPLAY["CDC/outbox/search/index catch-up"]
    REPLAY --> SLO["Đạt SLO và xác nhận RTO"]
~~~

Đây là **đồ thị phụ thuộc**, không phải thứ tự cứng bất biến. Ví dụ schema Cassandra thường cần được dựng trước khi nạp dữ liệu dạng SSTable; một cơ chế logical restore khác có thể mang metadata theo format riêng. Mỗi engine cần **restore sequence được kiểm chứng**.

## 4. Hai khái niệm: recovery artifact và recovery dependency

**Recovery artifact** là thứ có thể đem ra restore hoặc tái tạo một phần trạng thái:
- Snapshot, dump, WAL/oplog archive.
- DDL/schema definition.
- Configuration/IaC revision.
- Audit manifest, checksum, runbook.

**Recovery dependency** là thứ phải hoạt động để artifact dùng được:
- Danh tính có quyền gọi KMS.
- Encryption key phiên bản thích hợp.
- Backup bucket/object store.
- Control plane/IAM.
- Network/DNS/TLS.
- Database binary/driver tương thích.
- License hoặc module bắt buộc theo sản phẩm.

Một dependency có thể **không xuất ra một file backup** theo cách thông thường. Ví dụ khóa nằm trong HSM không được phép xuất raw key material; kế hoạch thay vì sao chép khóa cần bảo vệ **cơ chế tồn tại, dự phòng, quyền và khả năng dùng key đó khi khôi phục**.

## 5. NoSQL linh hoạt schema không có nghĩa không cần schema

Một document store có thể cho phép hai documents khác cấu trúc, nhưng ứng dụng vẫn dựa vào:
- Kiểu và tên field.
- Quy tắc bắt buộc/validation.
- Nested structure và serialization format.
- Unique, compound, TTL hoặc text indexes.
- Collation và sorting semantics.
- Shard/partition key.
- Application-side invariants.

Một wide-column store như Cassandra lại có keyspace/table/type definitions rõ ràng. Redis thường để ứng dụng tự quản lý định dạng values, TTL và key conventions. DynamoDB có key schema, index definitions và runtime data contracts. CouchDB có document/design documents và security/config metadata.

**Schema cần bảo vệ là toàn bộ hợp đồng diễn giải và truy cập dữ liệu**, không chỉ file DDL của hệ quan hệ.

## 6. Schema kỹ thuật và schema nghiệp vụ

Ví dụ một document:

~~~json
{
  "_id": "order-101",
  "schemaVersion": 3,
  "tenantId": "tenant-7",
  "items": [{"sku": "item-1", "quantity": 2}],
  "totalMinorUnits": 125000,
  "status": "PAID"
}
~~~

Lớp kỹ thuật có thể chỉ yêu cầu `_id` là unique; lớp ứng dụng có thể yêu cầu:
- `totalMinorUnits` không âm.
- `status` theo state machine.
- `items` không rỗng.
- `tenantId` bắt buộc và không thay đổi.
- `schemaVersion` tương thích với serializer hiện tại.

Sau restore, database có thể chấp nhận document, nhưng ứng dụng mới **không đọc được dữ liệu schemaVersion 1** nếu thiếu converter. Vì vậy bảo vệ schema còn gồm **migration history và application decoder compatibility**.

## 7. Bảo vệ index definitions

Một restore chỉ có records có thể thiếu:

~~~javascript
// Ví dụ MongoDB minh họa cấu trúc index
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true, name: "tenant_external_unique" }
);
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "tenant_createdAt" }
);
~~~

Nếu thiếu unique index, ứng dụng có thể tạo duplicate `externalOrderId` trong cùng tenant. Nếu thiếu index truy vấn, một API từng chạy p99 30 ms có thể chuyển thành scan lớn và timeout. Nếu thiếu TTL index, dữ liệu không được dọn theo policy; nếu tạo TTL index sai, dữ liệu có thể bị xóa sớm hơn dự kiến.

**Index là một phần của khả năng phục hồi đúng**, không chỉ tối ưu hiệu năng.

Không chạy lệnh trên production chỉ từ ví dụ. Kế hoạch cần kiểm tra loại index, options, collation, partial filter và version compatibility của engine.

## 8. Bảo vệ validators, constraints và policies

Các quy tắc có thể nằm ở:
- Database collection validator.
- Application code.
- Search mapping/index templates.
- ORM/serializer schemas.
- Infrastructure configuration.
- Authorization policies.
- TTL/retention settings.

Nếu restore data trước khi khôi phục rule phù hợp, có thể:
- Tạo dữ liệu mới không hợp lệ.
- Bị chặn ghi vì validator quá mới.
- Làm index build thất bại vì duplicates.
- Xóa nhầm records do TTL sai.
- Đọc vượt phạm vi tenant vì policy thiếu.

Kế hoạch phải nêu **quy tắc nào được khôi phục trước, khi nào được bật writes và cách so khớp schema version**.

## 9. Version compatibility khi restore

Các phiên bản cần ghi nhận:
- Database server/edition/feature compatibility.
- Storage format và backup tool format.
- Driver/SDK version.
- Application schema version.
- Serialization/codec version.
- Index option/feature versions.
- KMS integration/encryption format.
- CDC connector version.

Ví dụ một snapshot tạo từ phiên bản mới có thể không được restore trực tiếp trên binary cũ. Một field mới có thể không được code cũ hiểu. Một index feature chỉ có ở version đích khiến rollback khó.

**Không suy “backup được lưu” đồng nghĩa “mọi version đều đọc được backup”**. Luôn kiểm restore target matrix trên đúng engine/version.

## 10. Migration scripts phải được quản lý như thành phần phục hồi

Một manifest migration:

~~~text
M001-create-orders-collection
M002-add-tenant-externalOrderId-unique-index
M003-introduce-totalMinorUnits
M004-backfill-currency
M005-change-order-status-format
~~~

Nên lưu:
- Nội dung migration.
- Version/checksum.
- Thứ tự thực thi.
- Điều kiện trước/sau.
- Tính idempotent.
- Mapping/convert logic.
- Compatibility cũ/mới.
- Dữ liệu đối soát.
- Hướng rollback hoặc rollforward.
- Người phê duyệt và deployment artifact.

Không ghi lại trạng thái cuối bằng cách “tự chạy mọi migration” nếu snapshot đã ở version M004. Cần **marker version và kế hoạch khôi phục đúng mốc**.

## 11. Schema tại thời điểm backup và tại thời điểm phục hồi

Giả sử:

~~~text
10:00 Snapshot data theo schema v3.
10:30 Deploy app hiểu schema v4.
11:00 Migration một phần v3 → v4.
11:15 Sự cố; cần restore về 10:00.
~~~

Nếu khôi phục v3 nhưng đưa ứng dụng v4 lên ngay:
- Có thể đọc sai field mới.
- Business invariant v4 không thỏa.
- Logic cleanup làm mất dữ liệu v3.
- Index mới không tồn tại.
- Consumer nhận event format khác.

Restore plan phải chỉ rõ **ứng dụng/driver và schema version nào đi cùng recovery point**. Có thể cần bước migrate forward sau khi restore, nhưng phải giữ source versions, idempotency và đối soát.

## 12. Cấu hình cụm ảnh hưởng semantics dữ liệu

Không chỉ ghi lại hostnames. Những config quan trọng có thể gồm:
- Replication factor và placement.
- Read/write consistency settings.
- Durability/acknowledgement.
- Shard key/partition strategy.
- Cache/memory limits.
- Compaction/flush/retention policies.
- TTL settings.
- Snapshot/log retention.
- Query/transaction timeouts.
- Authentication/TLS settings.
- Index/stream/CDC settings.
- Network ACLs và endpoints.
- Backup scheduling.
- Monitoring/audit configuration.

Nếu chỉ restore records, một cụm mới có thể **trả dữ liệu khác kỳ vọng** vì read preference hoặc consistency setting thay đổi, dù application endpoint trả HTTP 200.

## 13. Tách cấu hình có thể version-control và bí mật

**Phù hợp với Git/IaC:**
- Cluster topology và instance classes.
- Database/server config templates.
- Replica placement.
- Schema/index/migration code.
- IAM policy definitions (không chứa credentials).
- Backup lifecycle policy.
- Alarm/monitoring config.

**Không nên đưa plaintext vào Git/runbook:**
- DB passwords.
- TLS private keys.
- API tokens.
- KMS raw key material.
- Secret recovery phrases.
- Encrypted blobs nếu vẫn chứa dữ liệu cần phân loại mà không có policy.

Thay vào đó lưu **reference, version identifier và quy trình cấp quyền** từ secret manager/KMS/HSM. Một bản backup config chứa `password=...` trong text có thể tạo sự cố bảo mật lớn hơn sự cố mất dữ liệu.

## 14. Infrastructure as Code là một bản thiết kế khôi phục

IaC có thể tái tạo:
- VPC/subnet/firewall/security groups.
- Node/cluster definitions.
- Volumes/object buckets.
- Replication topology.
- IAM roles và policy bindings.
- Backup jobs và alerts.
- Secret references.
- KMS key aliases/policies theo mô hình hỗ trợ.

Lợi ích:
- Có version/commit hash.
- Review và approval.
- So drift giữa production và desired state.
- Dựng môi trường DR có thể lặp lại.

Nhưng IaC **không tự là backup của dữ liệu hoặc keys**, và có thể phụ thuộc vào một Git server, CI identity hoặc state backend đang không sẵn sàng trong disaster. Kế hoạch DR cần **bootstrap path** độc lập.

## 15. Recovery bootstrap và vòng phụ thuộc

Một vòng phụ thuộc thường thấy:

~~~text
Muốn dựng cluster phải chạy CI.
Muốn CI chạy phải đọc secrets từ secret manager.
Muốn lấy secrets phải đăng nhập qua IdP.
IdP/secret manager lại phụ thuộc vào hạ tầng vùng vừa hỏng.
~~~

Nếu không thiết kế bootstrap:
- Có snapshot nhưng không có quyền tải.
- Có IaC nhưng không có runner/credentials.
- Có keys nhưng người vận hành không gọi được KMS.
- Có backup catalog nhưng không đọc được khi account production bị khóa.

Nên có **break-glass procedure**, recovery principals độc lập và tài liệu truy cập bảo mật được thử nghiệm. Không lưu plaintext passwords trong README để phá vòng phụ thuộc.

## 16. Danh tính và quyền là một phần trạng thái hệ thống

Phân biệt:
- **End users**: đăng nhập/authorization ở ứng dụng.
- **Service identities**: Java API, CDC connector, backup agent.
- **Database users/roles**: quyền đọc/ghi/DDL/maintenance.
- **Cloud IAM**: quyền trên tables, backups, KMS, network resources.
- **Recovery operator/break-glass**: quyền dùng trong sự cố.
- **Audit/SOC identities**: quyền đọc log bằng chứng.
- **Key administrators**: quyền quản trị key, có thể tách khỏi quyền decrypt.

Khi restore sang cụm mới, identity provider/database users/roles **không nhất thiết được mang theo cùng data snapshot**. Cần inventory và tái tạo đúng.

## 17. Phục hồi quyền không phải “cấp admin cho mọi service”

Một phản ứng vội:
~~~text
Restore xong nhưng app bị AccessDenied.
Cấp full-admin cho mọi service account.
```

Hậu quả:
- Tenant isolation bị phá.
- App bị compromise có quyền rộng hơn trước.
- Một nhầm lẫn có thể xóa backup/keys.
- Không còn đối soát permission drift.

Nên phục hồi **least-privilege roles** và test allow/deny:
- API chỉ đọc/ghi collections/tables cần thiết.
- CDC connector chỉ có quyền nguồn và sink theo contract.
- Backup agent có quyền tạo backup nhưng không mặc nhiên xóa mọi bản.
- Recovery operator có quyền đặc biệt có kiểm soát, tự hết hạn.
- Audit reader không được sửa logs.

Việc khôi phục phải giữ **nguyên tắc phân tách nhiệm vụ**, ngay cả trong incident.

## 18. Quyền của backup writer, reader và deleter nên tách

Ba quyền khác nhau:

| Principal | Cần làm gì | Không nên mặc định có |
|---|---|---|
| Backup writer | Tạo bản sao vào nơi bảo vệ | Xóa/version purge mọi bản backup |
| Restore operator | Đọc catalog/backup và dùng key theo scope | Sửa chính sách retention hoặc export toàn bộ dữ liệu khác |
| Retention administrator | Quản lý lifecycle theo approval | Giải mã và đọc dữ liệu nghiệp vụ |
| KMS administrator | Quản lý key metadata/policy | Giải mã tùy ý nếu role tách biệt |
| Application service | Đọc/ghi business data cần thiết | Xóa backup, disable keys, đổi IAM |
| Security auditor | Đọc evidence và key-use logs | Sửa/xóa evidence |

Một account compromise không nên vừa xóa dữ liệu, vừa xóa backups, vừa hủy keys và vô hiệu audit.

## 19. KMS/HSM làm gì trong backup?

Ở một mô hình **envelope encryption** điển hình:
1. Dữ liệu được mã hóa bằng **Data Encryption Key (DEK)** hoặc khóa dữ liệu tương đương.
2. DEK được mã hóa/bọc bằng **Key Encryption Key (KEK)** do KMS/HSM quản lý hoặc được bảo vệ tương đương.
3. Backup lưu ciphertext và metadata cần tìm encrypted DEK/key reference.
4. Khi restore, principal có quyền cần sử dụng KMS/HSM để giải mã/unwarp DEK theo chính sách và thuật toán phù hợp.

~~~mermaid
flowchart TD
    DATA["Plaintext business data"] --> ENC["Encrypt with DEK"]
    DEK["Data Encryption Key"] --> ENC
    ENC --> BACKUP["Encrypted backup bytes"]
    KEK["KMS/HSM protected KEK"] --> WRAP["Wrap DEK"]
    DEK --> WRAP
    WRAP --> EDEK["Encrypted DEK + key metadata"]
    EDEK --> BACKUP
    BACKUP --> REST["Restore process"]
    REST --> KMS["KMS decrypt/unwrap permission"]
    KMS --> DEC["Decrypt data to authorized target"]
    KEK --> KMS
~~~

Không phải mọi sản phẩm dùng đúng cấu trúc này; một hệ có thể mã hóa ở disk, file, database, client hoặc cloud service. Nhưng mọi phương án đều có **key dependencies cần tồn tại trong khoảng thời gian backup có thể được phục hồi**.

## 20. Backup encrypted chưa đủ nếu key mất

Tình huống:
~~~text
Snapshot S1 còn trong object storage.
S1 được bảo vệ bằng key K1.
Sau key rotation, operator xóa K1.
K2 đang hoạt động cho dữ liệu mới.
```

Nếu S1 vẫn cần K1 hoặc một key version cũ để giải mã, **backup không còn dùng được**, dù file không hỏng.

Điều cần quản lý:
- Key ID/version/algorithm dependency cho từng backup.
- Trạng thái enabled/disabled/deletion scheduled.
- Thời gian key material phải còn khả dụng.
- Key policy và quyền decrypt ở môi trường DR.
- Rotation behavior của dịch vụ cụ thể.
- Cross-region/cross-account availability.
- Restore drill sau rotation.

Không tự giả định “đổi alias sang K2” khiến các ciphertext được K1 bảo vệ tự giải mã bằng K2.

## 21. Key rotation không luôn là re-encryption

Có thể có nhiều kiểu:
- **Key material rotation** trong cùng một managed key identity, provider giữ các phiên bản cũ để giải mã.
- **Chuyển sang key identity mới** cho các writes/backups mới.
- **Rewrapping DEK** sang KEK khác.
- **Re-encrypt dữ liệu/backup bytes** bằng khóa khác.
- **Certificate rotation** phục vụ TLS, khác encryption-at-rest keys.

Các hành vi phụ thuộc provider/engine/algorithm. Không thể suy từ từ “rotate” rằng mọi bản sao cũ đã đổi khóa.

Trước khi retire key:
1. Inventory các backup/snapshots/logs tham chiếu key.
2. Xác minh mối liên hệ key ID/version.
3. Test decrypt/restore với bản sao cũ nhất còn phải giữ.
4. Thực thi rewrap/re-encrypt nếu cần và được hỗ trợ.
5. Verify bản sao mới, quyền DR.
6. Chỉ sau đó mới xem xét disable/delete theo retention và approval.

## 22. Key alias là tên, không phải bản thân khóa

Ví dụ:
~~~text
alias/production-backup
    -> key K1 vào ngày snapshot.
alias/production-backup
    -> key K2 sau rotation.
~~~

Nếu manifest chỉ ghi alias mà không lưu **key identifier liên quan tới ciphertext**, người phục hồi có thể gọi nhầm key. Cần kiểm metadata mà encryption format thực sự yêu cầu, không tự lưu plaintext key.

Kế hoạch có thể ghi:
~~~yaml
encryption:
  provider: approved-kms
  keyReference: "opaque-key-id-or-arn"
  keyVersionOrGeneration: "record-when-applicable"
  cryptographicFormat: "documented-backup-format"
  decryptRoleReference: "dr-backup-restore-role"
  rawKeyMaterialIncluded: false
~~~

Các field là ví dụ, không có nghĩa mọi KMS đều có cùng API key version hoặc khả năng export.

## 23. Key deletion, disabling và crypto-shredding

**Disable key:** có thể ngăn giải mã dù dữ liệu còn.

**Scheduled deletion:** có thể có thời gian chờ theo sản phẩm, nhưng sau khi key material bị hủy, ciphertext phụ thuộc khóa có thể không phục hồi.

**Crypto-shredding:** cố ý phá khả năng giải mã bằng hủy key material; có thể phù hợp một số chính sách xóa dữ liệu, nhưng mâu thuẫn với backup retention hoặc legal hold nếu không được thiết kế.

Không dùng key deletion như thao tác “dọn dẹp sau rotation” mà chưa rà soát **mọi backup và log chain** cần khóa cũ. Ngược lại, không giữ key mãi mãi chỉ vì từng tồn tại backup; key lifecycle phải theo policy đã phê duyệt.

## 24. Quyền KMS khác quyền đọc backup

Một principal có thể:
- Đọc object backup nhưng không được decrypt.
- Dùng key để decrypt nhưng không có quyền đọc object.
- Có quyền backup nhưng không tạo được database target.
- Có quyền target database nhưng không thể gọi KMS từ vùng/account DR.

Khả năng phục hồi cần các quyền kết hợp đúng **và đúng network/region/key policy conditions**.

Một bài restore drill phải chạy với **đúng recovery identity và environment** dự kiến dùng khi sự cố, không dùng quyền admin cá nhân vượt mọi policy rồi kết luận runbook đạt.

## 25. Không phải khóa nào cũng xuất được thành file backup

HSM và nhiều KMS được thiết kế để key material **không được export**. Vì vậy kế hoạch bảo vệ khóa không có nghĩa chép plaintext key sang ổ USB.

Có thể cần:
- Nhà cung cấp bảo đảm durability/availability cho key.
- Multi-region key/copy theo khả năng sản phẩm.
- Backup/restore chuyên biệt cho HSM nếu được hỗ trợ và có quorum/controls.
- Quản lý KMS account/resource policy bằng IaC.
- Key inventory và emergency access.
- Kiểm thử decrypt từ account/region dự phòng.
- Contract về key destruction và retention.

**Không tự xuất, hiển thị hoặc nhúng raw encryption key vào runbook** để “phòng sự cố”.

## 26. Cross-region không tự đồng nghĩa key sẵn sàng

Backup được copy từ region A sang B nhưng:
- KMS key chỉ hoạt động ở A.
- Key policy không cho restore principal ở B.
- Encrypted DEK phụ thuộc key identity không có bản sao tại B.
- IAM/resource policy ngăn cross-account access.
- Network/endpoint tới KMS A không còn.
- Replica/copy operation không áp dụng cho loại key đó.

Cần thiết kế cross-region encryption/key strategy theo capability thật, có thể phải re-encrypt backup copy bằng key của vùng đích. Không sao chép một blob đã mã hóa rồi giả định khôi phục được khi vùng nguồn hoàn toàn mất.

## 27. Cross-account DR và mất quyền control plane

Một kiến trúc tăng khả năng chống ransomware có thể:
~~~text
Production account:
  Business database và application identities.

Recovery account:
  Immutable or restricted backup copies.
  Recovery KMS/key access.
  Separate administrators.
  Preconfigured restore identities.
```

Lợi ích: giảm nguy cơ tài khoản production bị compromise có thể xóa toàn bộ backups.

Rủi ro:
- Cross-account policies sai.
- KMS grants không hiệu lực.
- Backup share/copy feature có giới hạn.
- DR account thiếu network, quotas hoặc service setup.
- Backup readers vô tình được quyền quá rộng.

Diễn tập phải kiểm **thực sự mở được bản sao và phục hồi vào target**, không chỉ thấy object trong bucket.

## 28. Quản lý bí mật ứng dụng khác quản lý khóa dữ liệu

Secret manager có thể lưu:
- Database passwords.
- API tokens.
- TLS certificate/private-key references.
- CDC connector credentials.
- Service-to-service secrets.

KMS/HSM có thể bảo vệ key material cho encryption hoặc bản thân secret manager.

Kế hoạch:
- Quản lý secret path/reference và ownership.
- Có phương án identity bootstrap.
- Không hardcode secret values trong IaC.
- Rotation cùng service consumers.
- DR availability và reissue/rehydrate secrets khi cần.
- Kiểm expiration/CA trust và revocation.
- Thu hồi temporary recovery credentials sau sự cố.

**Có data encryption key không đồng nghĩa application đã có quyền login**, và có password không đồng nghĩa backup được decrypt.

## 29. Certificate và CA trust là điều kiện kết nối

Sau restore:
- Node có thể dùng TLS certificate mới nhưng client vẫn tin CA cũ.
- Certificate SAN/hostname không khớp endpoint DR.
- Clock của nodes lệch làm cert có vẻ chưa hiệu lực hoặc đã hết hạn.
- Mutual TLS identity không được cấp đúng.
- Một service đã rotate truststore nhưng batch consumer chưa cập nhật.

Nên bảo vệ:
- Certificate issuance/renewal procedure.
- Trusted CA chain và rollout strategy.
- Secret references/private-key custody.
- Client truststore configs.
- Emergency renewal permissions.
- Tests handshake theo service role.

Không sao chép private keys tùy tiện vào backup metadata; có thể cần **cấp lại** chứng chỉ cho môi trường phục hồi.

## 30. Backup manifest: cần mô tả toàn bộ dependency

Một manifest mẫu:

~~~yaml
recoveryPackage:
  id: "orders-dr-2026-11-14"
  dataOwner: "commerce-platform"
  environment: "production"
  engine: "mongodb"
  engineVersion: "documented-source-version"
  createdAt: "2026-11-14T01:00:00Z"
  backup:
    type: "consistent-snapshot-plus-log-chain"
    catalogReference: "opaque-backup-ref"
    sourceCluster: "commerce-primary"
    scope: ["orders", "payments-metadata"]
    consistencyPoint: "documented-checkpoint-reference"
    checksumManifest: "verified-digest-reference"
  schema:
    revision: "git-commit-or-artifact-digest"
    validatorRevision: "validator-bundle-v7"
    indexRevision: "index-bundle-v12"
    migrationVersion: 42
  configuration:
    iacRevision: "git-commit-or-artifact-digest"
    topologyRevision: "dr-topology-v3"
    durabilityPolicyRef: "write-policy-v5"
  access:
    rolePolicyRevision: "iam-policy-v11"
    recoveryRoleReference: "dr-restore-role"
    secretReferences: ["secret-manager-path-or-id"]
  encryption:
    keyReference: "opaque-kms-key-id"
    keyVersionReference: "if-applicable"
    rawKeyMaterialIncluded: false
  dependencies:
    applicationRelease: "orders-api-compatible-release"
    cdcCheckpoint: "cdc-checkpoint-ref"
    searchIndexSpec: "search-index-v8"
  verification:
    lastRestoreDrill: "2026-11-01"
    rpoTargetMinutes: 5
    rtoTargetMinutes: 60
~~~

**Không đưa plaintext password, raw key material, customer rows hoặc full token vào manifest**. Manifest phải có integrity protection, access controls và versioning; các references phải giải được trong tình huống mất vùng/account chính.

## 31. Chữ ký và checksum không chứng minh restore đầy đủ

Checksum/hash giúp kiểm:
- Artifact không bị thay đổi so với digest đã biết.
- Các file chunks khớp.
- Catalog không bị sửa nếu có trusted signature/anchor.

Nhưng checksum không tự chứng minh:
- Snapshot nhất quán qua shards.
- Có đủ WAL/PITR logs.
- Mọi index/schema đúng.
- Decrypt key vẫn tồn tại.
- IAM có quyền khi disaster.
- Data ứng dụng sau restore hợp lệ.

**Integrity của bytes chỉ là một lớp trong recovery correctness**. Cần restore drill và business validation.

## 32. Consistent snapshot và log chain

Khi database vẫn nhận ghi, có thể có:
~~~text
Snapshot bắt đầu lúc t0.
Một số files được copy trước, files khác sau.
Writes vẫn tiếp tục.
Log tiếp tục được ghi.
~~~

Nếu backup strategy không bảo đảm consistency point và log continuity, bản sao files ghép lại có thể là trạng thái không nhất quán.

Các phương pháp tùy engine:
- Engine/database-aware snapshot.
- Transactionally consistent export trong phạm vi hỗ trợ.
- Snapshot cộng WAL/oplog/commit-log chain.
- Application quiesce hoặc coordination barrier khi cần.
- Per-shard checkpoint/watermark với reconciliation protocol.

Không tự chép random files từ thư mục data đang chạy rồi gọi đó là backup hoàn chỉnh.

## 33. Cross-shard consistency có thể khó hơn một node

Nếu một nghiệp vụ update hai shards:
~~~text
Shard A snapshot ở LSN 100.
Shard B snapshot ở LSN 90.
Transaction có các bước liên quan cả hai.
~~~

Kết quả khôi phục có thể chứa một nửa tác động nếu backup không có cơ chế global consistent point hoặc replay phù hợp.

Kế hoạch cần biết:
- Engine có hỗ trợ consistent multi-shard backup như thế nào.
- Distributed transactions được checkpoint/restore ra sao.
- Metadata/config service có cùng recovery point không.
- Những outbox/ledger records nào cần reconcile.
- Business invariants được kiểm sau restore bằng cách nào.

**Một timestamp ghi trên folder không biến các snapshots độc lập thành một transactionally consistent cluster backup.**

## 34. RPO: khoảng dữ liệu có thể mất

**Recovery Point Objective (RPO)** là mức mất dữ liệu theo thời gian được phép khi khôi phục.

Ví dụ:
~~~text
RPO target: 5 phút.
Full snapshot lúc 00:00.
Incremental/log archive tới 09:57.
Sự cố lúc 10:00.
```

Về lý thuyết log chain có thể đưa recovery point gần 09:57, nhưng phải kiểm liên tục và replay được.

RPO thực tế phụ thuộc:
- Recovery point được xác minh.
- Tình trạng backup logs.
- Replication semantics.
- Key availability.
- Integrity of backups.
- Các nguồn dữ liệu phụ trợ cần đồng bộ.

**Không tính RPO chỉ bằng “lịch snapshot mỗi đêm”** nếu có PITR hoặc nếu bản sao mới nhất thực ra hỏng/không thể mở.

## 35. RTO: thời gian tới khi dịch vụ có ích trở lại

**Recovery Time Objective (RTO)** phải định nghĩa mốc dịch vụ phục hồi. Một cụm vừa tạo xong chưa chắc ứng dụng đạt SLO.

Ví dụ ngân sách thời gian minh họa:

| Công đoạn | Thời gian |
|---|---:|
| Xác định sự cố và kích hoạt DR | 5 phút |
| Dùng recovery identity/KMS | 10 phút |
| Dựng hạ tầng/cluster | 20 phút |
| Tải và restore data/logs | 35 phút |
| Rebuild/verify indexes, schema, permissions | 20 phút |
| Kiểm business correctness và reconnect apps | 15 phút |
| CDC/search catch-up, traffic ramp | 15 phút |
| **Tổng tuần tự giả định** | **120 phút** |

Nếu RTO cam kết 60 phút, kế hoạch như vậy **chưa đạt**, dù backup có sẵn. Có thể cần pre-provisioned infrastructure, warm standby, parallel tasks an toàn hoặc RTO được điều chỉnh/đầu tư thêm.

Một số bước có thể chạy song song; **critical path** mới quyết định thời gian thực, không chỉ cộng mọi việc khi chúng độc lập.

## 36. Recovery critical path

Ví dụ:
~~~text
IAM bootstrap -> KMS access -> decrypt -> restore data -> validate.
       \
        -> IaC cluster provisioning -----/
```

Dù restore dữ liệu mất 20 phút, IAM/KMS bootstrap mất 90 phút thì RTO khó đạt dưới 90 phút.

Kế hoạch DR cần:
- Đo thời gian từng bước trong diễn tập.
- Xác định bước có thể chạy song song.
- Chuẩn bị dependencies trước.
- Bỏ thao tác đòi con người chờ approval không có lịch dự phòng.
- Biết bottleneck băng thông/IOPS.
- Chọn ưu tiên phục hồi read-only trước hay read-write theo business goals.

**Tối ưu tốc độ tải backup mà không kiểm con đường giải mã/đăng nhập có thể không cải thiện RTO.**

## 37. Thứ tự khôi phục tổng quát

Một runbook mẫu:

~~~text
1. Tuyên bố incident và chọn recovery point được phê duyệt.
2. Đóng băng thao tác có thể làm hỏng bằng chứng; ghi trạng thái source.
3. Dùng recovery identity độc lập và xác minh IAM/KMS.
4. Kiểm catalog, integrity, snapshot/log chain, key references.
5. Dựng network, cluster topology và engine/version tương thích.
6. Cấp TLS/secret references, roles tối thiểu.
7. Khôi phục schema/index metadata theo trình tự engine yêu cầu.
8. Restore data và replay logs tới recovery point.
9. Kiểm resource versions, counts, consistency và invariants.
10. Hoàn tất indexes/views/validators, TTL policies có kiểm soát.
11. Mở quyền app/services theo từng phạm vi.
12. Kiểm smoke tests gồm read, write, auth deny và key decryption.
13. Reconcile outbox/CDC/streams và rebuild projections/search nếu cần.
14. Traffic ramp/canary, theo dõi p99/errors/lag và SLO.
15. Ghi audit, recovery evidence, backup schedule và bàn giao.
~~~

Đây là **mẫu quy trình**, không phải thứ tự cứng cho mọi engine. Ví dụ MongoDB logical restore có thể phục hồi index definitions cùng data, còn Cassandra SSTable restore cần schema/tokens đã thiết lập đúng trước. Không bật destructive TTL/cleanup hoặc mọi production writes nếu schema/permissions chưa được xác minh.

## 38. Khởi động ứng dụng theo từng pha

Một hướng triển khai:
- **Phase A – Isolated:** dựng và restore trong network không nhận external traffic.
- **Phase B – Read-only checks:** xác minh schema, data, index, encryption và authorization.
- **Phase C – Controlled writes:** dedicated test data hoặc canary tenants.
- **Phase D – Stream recovery:** CDC/outbox/search projections và cache.
- **Phase E – Traffic ramp:** tăng lưu lượng theo SLO.
- **Phase F – Full service:** bật normal backup/alerts/audit, handoff.

Không đưa tất cả services lên ngay khi database process UP; nếu code schema mới tự chạy migration/TTL cleanup, nó có thể thay dữ liệu vừa restore trước khi được kiểm.

## 39. Cẩn thận với uniqueness và constraint khi rebuild

Nếu source đã bị hỏng rồi mới tạo backup:
- Có thể tồn tại duplicates.
- Unique index rebuild thất bại.
- Validator mới chặn writes.
- TTL index xóa records cũ ngay khi bật.
- Application projection inconsistency xuất hiện.

Khi phục hồi:
1. Chọn recovery point trước lỗi nếu có thể.
2. Giữ bản immutable của dữ liệu để đối soát.
3. Kiểm business duplicates và data quality.
4. Sửa theo runbook có audit, không âm thầm bỏ index.
5. Dựng constraints trong đúng thời điểm.
6. Kiểm read/write behavior sau khi bật.

Không coi “bỏ unique index để restore xong” là thành công nếu nghiệp vụ yêu cầu duy nhất.

## 40. MongoDB: những phụ thuộc quan trọng

Với MongoDB, một bộ bảo vệ có thể cần:
- Collections và documents.
- Index definitions: unique, compound, TTL, partial, text, collation, options.
- Collection validators và collection options.
- Replica set/sharded topology và config metadata.
- Users/roles và authentication mechanism theo phạm vi backup.
- Server configuration, FCV/version compatibility.
- Oplog/PITR continuity nếu thiết kế backup dùng log replay.
- Encryption-at-rest/KMS integration, TLS và secret refs.
- Change Stream consumers/resume tokens và ứng dụng downstream.

**Không giả định** một lần xuất dữ liệu kiểu logical dump luôn chứa mọi users, custom roles, server configs, cluster metadata và keys. Phải chọn công cụ backup và scope phù hợp.

## 41. MongoDB logical export khác full-cluster recovery

Ví dụ:
~~~text
Logical dump một collection:
  document contents và một số metadata/index definitions
  tùy công cụ và options.

Full-cluster recovery:
  replica sets, sharded config metadata, users/roles,
  encryption, consistency across shards,
  log chain, application dependencies.
```

Một dump hữu ích cho di chuyển tập con dữ liệu, nhưng có thể không đủ để phục hồi toàn bộ cluster production theo RPO/RTO.

Cần test **mongodump/mongorestore hoặc công cụ snapshot/managed backup cụ thể theo phiên bản**, và kiểm chính xác những gì được mang theo, không dựa vào giả định chung.

## 42. MongoDB index và validator verification

Sau restore có thể kiểm bằng các truy vấn chỉ đọc theo môi trường đã được phân quyền:

~~~javascript
// Chỉ minh họa cách quan sát metadata ở một database.
db.orders.getIndexes();
db.getCollectionInfos({name: "orders"});
~~~

Đối chiếu với schema revision đã lưu:
- Expected unique index có tồn tại và đúng options không?
- TTL policy có đúng không?
- Collection validator/collation có đúng không?
- Shard key/placement khớp không?
- Source/restore versions tương thích không?

Không kết luận chỉ vì số documents bằng nhau.

## 43. Cassandra: cần keyspace/table/type metadata

Một snapshot Cassandra chủ yếu liên quan tới dữ liệu lưu trữ theo cơ chế engine, không tự làm người vận hành hiểu đầy đủ schema nếu thiếu schema exports/versioned definitions.

Những thứ cần bảo vệ:
- Keyspace replication strategy và per-DC RF.
- Table schema, partition/clustering keys.
- UDTs, indexes, views và table options.
- Compaction/compression/TTL settings.
- Roles/permissions và TLS configs.
- Token/rack/DC topology.
- Snapshot/commit-log recovery strategy.
- Repair/bootstrap/streaming state.

**Không tạo keyspace mới với RF mặc định rồi nạp SSTables** nếu ứng dụng cần `LOCAL_QUORUM` hoặc topology khác.

## 44. Ví dụ Cassandra schema và replication

~~~sql
CREATE KEYSPACE commerce
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '3'
};

CREATE TABLE commerce.events_by_account (
  account_id text,
  event_day date,
  event_ts timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((account_id, event_day), event_ts, event_id)
) WITH CLUSTERING ORDER BY (event_ts DESC);
~~~

Đây là ví dụ DDL, **không phải lệnh nên chạy trên môi trường thật**. Datacenter name `dc1`, RF, compaction, GC grace, TTL và consistency của ứng dụng phải được lấy từ topology/requirements đã xác minh.

Nếu restore schema khác:
- Partitioning thay đổi.
- Queries không tìm đúng data.
- Replicas không đủ theo consistency requirement.
- Tombstone/TTL behavior thay đổi.
- Storage footprint và compaction cost khác.

## 45. Cassandra: role và access policy cũng phải được tái tạo

Sau khi xây cluster mới, cần kiểm:
- Authentication/authorization enablement.
- Database roles và permission grants.
- Service-to-keyspace/table scope.
- TLS certificates/credentials.
- Cluster internode security.
- Repair/backup operator permissions.
- Dùng database system keyspaces nào và phục hồi chúng ra sao theo official process.

Không tự restore các system tables vào topology/version không tương thích. Các thành phần security metadata và system keyspaces có quy trình đặc biệt theo phiên bản/bản phân phối.

## 46. Redis: RDB/AOF không phải full environment backup

Redis có thể dùng RDB snapshots hoặc AOF persistence theo cấu hình, nhưng phục hồi nghiệp vụ có thể còn cần:
- `redis.conf` và runtime config.
- Maxmemory và eviction policy.
- ACL definitions/users và credentials.
- TLS certificates/CA.
- Redis Cluster hash-slot assignments, master/replica mapping.
- Sentinel configuration nếu dùng Sentinel.
- Persistence policy, replication settings.
- Modules/scripts/functions theo deployment/version.
- Application key conventions, serialization và TTL expectations.

Không giả định RDB/AOF sẽ tự tạo đúng network topology, ACL hoặc certificate của cluster mới.

## 47. Redis Cluster: slot ownership là metadata vận hành

Một cụm Redis Cluster có:
~~~text
16384 hash slots.
Các masters giữ từng dải slots.
Các replicas hỗ trợ failover.
```

Sau khi dựng lại nodes từ dữ liệu:
- Phải xác nhận slot coverage.
- Không có slot bị bỏ trống ngoài policy.
- Master/replica mapping hợp lệ.
- Client hỗ trợ MOVED/ASK/slot map refresh theo semantics.
- Mỗi key thuộc đúng slot.
- TLS/ACL và persistence hoạt động.
- Cache source fallback có capacity nếu cache chưa nóng.

Khôi phục file dữ liệu vào một node **không tự khôi phục cluster membership và slot map an toàn**.

## 48. Redis cache có thể tái tạo, nhưng phải chứng minh

Nếu Redis chỉ là cache-aside:
- Có thể quyết định không bảo vệ toàn bộ cached values.
- Nhưng vẫn cần bảo vệ config, ACL/TLS, key namespace, TTL policies và bootstrap.
- Cần nguồn dữ liệu có thẩm quyền và đủ capacity để chịu cache miss surge.
- Dùng throttled prewarm/singleflight/rate limiting.
- Đo time-to-SLO sau cache loss.

Ngược lại, nếu Redis chứa queues, counters hoặc state không thể tái dựng từ nguồn khác, **không được mặc định coi nó là dữ liệu tạm**. Phải có RPO/RTO, persistence/replication và recovery strategy tương xứng.

## 49. DynamoDB: restore data khác tái tạo toàn bộ hệ sinh thái

Trong một thiết kế dùng DynamoDB, cần inventory:
- Table names/key schema và required GSIs/LSIs.
- PITR hoặc backup/export capabilities đã bật và tested.
- Capacity mode/autoscaling policies.
- TTL configuration.
- Streams configuration và consumers.
- Global tables/replication nếu dùng.
- IAM policies/roles và resource policies nếu áp dụng.
- KMS key dependency theo encryption setting.
- Application/SDK endpoints, table aliases và environment config.
- Alarms, quotas, backups/retention.

**Mỗi restore mode có semantics cụ thể**: tạo bảng đích mới, trạng thái indexes/settings, streams/TTL và permissions có thể cần thiết lập hoặc xác minh riêng theo dịch vụ/version. Không tự cho rằng backup table data là bản sao hoàn chỉnh của IAM hoặc Global Tables topology.

## 50. DynamoDB point-in-time recovery và service cutover

Một runbook cần làm rõ:
1. Recovery point nào hợp lệ/được giữ?
2. Restore target table có tên/ARN/region gì?
3. Key schema/index status có đúng không?
4. IAM/KMS permissions ở bảng và backup có tương thích không?
5. Streams/consumers sẽ đọc từ đâu sau restore?
6. TTL/autoscaling/capacity/alarms có đúng policy không?
7. Global replication sẽ được tái thiết lập như thế nào?
8. Application config và DNS/table mapping chuyển tới target ra sao?
9. Những writes sau recovery point được đối soát thế nào?
10. Có test nhất quán, business invariants và RTO thực nghiệm không?

Không tự động trỏ toàn bộ production traffic tới target chỉ vì bảng đã có status cho phép truy cập.

## 51. CouchDB: design documents và security metadata

CouchDB dùng document model và có design documents, revisions, `_changes`, replication. Khi phục hồi, cần nghĩ tới:
- Business documents và revisions theo backup method.
- Design documents/views/index definitions.
- Database security configuration.
- Cluster/replication endpoints và auth.
- Replication checkpoints/cursors.
- Conflict handling.
- Database config và user/role access.
- TLS/encryption dependencies.

Một `_changes` cursor là vị trí đồng bộ theo source, **không phải bằng chứng rằng có thể restore toàn cluster** từ feed mà không có snapshot và retention tương ứng.

## 52. Search index và materialized views cũng là dependency

Một application có thể lưu source data ở MongoDB nhưng đọc sản phẩm từ search index. Restore source chưa phục hồi search index.

Có hai hướng:
- **Backup và restore projection/index** kèm schema/mapping.
- **Rebuild từ source** với snapshot + CDC catch-up.

Cần kiểm:
- Index mapping/analyzer/template version.
- Derived view schema.
- Event replay ability và source retention.
- Idempotency/dedup.
- Index build time và memory/disk cost.
- Tính nhất quán khi phục vụ reads.
- Thời điểm cutover/alias swap.

Nếu reindex mất sáu giờ nhưng RTO chỉ một giờ, “có thể rebuild” chưa phải kế hoạch đạt RTO.

## 53. CDC/outbox checkpoint là trạng thái cần bảo vệ

Một hệ:
~~~text
MongoDB source state restored to t0.
CDC consumer checkpoint points to t1 > t0.
```

Nếu consumer tiếp tục từ t1, nó có thể **bỏ qua events giữa t0 và t1** cần tái tạo projection. Nếu checkpoint ở quá xa quá khứ và source log đã hết retention, cũng không thể replay bình thường.

Kế hoạch phải:
- Lưu source snapshot/watermark/cursor liên quan.
- Phân biệt source commit position và consumer-applied position.
- Dùng stable event IDs/idempotent consumers.
- Có rebuild/resnapshot protocol nếu cursor hết hạn.
- Tính downstream replay vào RTO.
- Không `resume latest` chỉ để hệ bớt báo lỗi.

Backup của authoritative database và backup của **stream processing state** cần có quan hệ recovery point rõ ràng.

## 54. Đừng dùng backup làm cách xóa dấu vết thao tác

Nếu thao tác sai làm mất dữ liệu rồi restore snapshot:
- Business state quay về mốc cũ.
- Audit/security evidence về thao tác đã xảy ra vẫn cần được bảo toàn.
- Orders/transactions mới sau mốc backup có thể cần đối soát.
- External payments/email/fulfillment đã phát sinh không tự đảo.
- Downstream caches/search/queues có thể chứa state mới hơn.

**Rollback dữ liệu không phải rollback thế giới bên ngoài.** Có thể cần compensating operations, ledger reconciliation và audit correction events.

## 55. Bảo vệ backup trước ransomware và insider threats

Threat model:
~~~text
Attacker kiểm soát production DB admin credential.
Attacker xóa hoặc mã hóa business data.
Attacker cố xóa backups, disable keys và giảm retention.
```

Các lớp phòng vệ:
- Backup copy trong boundary IAM khác.
- Immutable/object-lock/WORM khi phù hợp.
- Tách quyền create/read/delete và key administration.
- Delayed deletion và dual approval.
- Audit changes tới backup/KMS policies.
- Alert khi backup job ngừng hoặc key deletion được lên lịch.
- Test restore bằng account độc lập.
- Offline/isolated copy theo nhu cầu.

Không phải mọi hình thức immutability đều giống nhau và không giải quyết key loss. **Một bản backup bất biến nhưng key bị xóa vẫn có thể vô dụng.**

## 56. Quy tắc “nhiều bản sao” vẫn cần phụ thuộc giải mã

Một chiến lược có thể có:
- Primary backup copy.
- Second copy ở failure domain khác.
- Một copy immutable hoặc offline.
- Snapshot + log chain.
- Encryption key access có kiểm soát.

Nhưng nếu cả ba copies đều phụ thuộc cùng một KMS key chỉ tồn tại trong một vùng mà kế hoạch DR giả định mất hoàn toàn, **ba bản sao không tạo ra ba phương án khôi phục độc lập**.

Đánh giá **failure domains của dữ liệu, metadata, keys, IAM và network** cùng nhau.

## 57. Bảo vệ backup manifest khỏi bị sửa

Một attacker có thể không xóa backup mà sửa:
- Catalog references.
- Checksum manifest.
- Key identifier.
- Restore script.
- Schema revision.
- Recovery timestamp.
- IAM policy.
- Runbook link dẫn tới môi trường giả.

Nên áp dụng:
- Versioned manifests và protected approvals.
- Checksums/signatures có trusted verification keys.
- Immutable/append-only change records khi phù hợp.
- Access audit.
- Integrity verification trong mỗi restore drill.
- Không thực thi script tải từ nguồn không tin cậy ngay trong DR.

Một manifest là **bản đồ phục hồi**; sai manifest có thể làm restore thất bại ngay cả khi bytes còn nguyên.

## 58. Monitoring cho khả năng khôi phục

| Metric | Câu hỏi |
|---|---|
| last_successful_backup_age | Backup gần nhất bao lâu? |
| last_verified_restore_age | Khi nào restore cuối được chứng minh? |
| backup_artifact_integrity_status | Có checksum/copy integrity? |
| PITR/log_chain_gap_count | Có đứt mạch recovery? |
| snapshot_coverage_by_shard | Có thiếu shard/partition nào? |
| backup_copy_age_by_region | DR copy có bị trễ? |
| KMS_decrypt_test_success | Recovery principal giải mã được không? |
| key_deletion_pending_count | Có key cần giữ đang chờ hủy? |
| schema_config_drift_count | Desired/actual metadata lệch? |
| permission_drift_count | Role/policy scope có đổi? |
| certificate_expiry_days | TLS có sắp hết hạn? |
| recovery_drill_duration | Thực nghiệm RTO bao nhiêu? |
| restored_data_validation_failures | Business invariants có sai? |
| CDC_replay_gap_count | Stream/projection có thiếu event? |
| backup_access_anomaly_count | Có truy cập/export bất thường? |

Không ghi raw secrets hoặc customer identifiers trong metric labels. Alert về key deletion/backup privilege change phải được gửi đến đội trực có khả năng xử lý.

## 59. Tần suất review không chỉ dựa trên lịch backup

Các kiểm tra có nhịp khác nhau:
- **Hằng ngày:** backup success, PITR chain, copy lag, disk/quota, KMS status alerts.
- **Hằng tuần hoặc theo thay đổi:** schema/index/config drift, service-role permissions, certificate status.
- **Sau schema upgrade/key rotation:** test compatibility với backups còn phải giữ.
- **Theo lịch DR drill:** restore end-to-end, kiểm RPO/RTO và ứng dụng.
- **Sau incident/change:** kiểm dependencies mới, cập nhật owner/runbook.

Các chu kỳ chỉ là ví dụ quản trị. Một thay đổi KMS key policy hôm nay có thể làm hỏng khả năng khôi phục **ngay hôm nay**, không thể chờ đến đợt kiểm hàng quý.

## 60. Restore drill khác backup inspection

**Inspection** kiểm backup tồn tại, size và checksum.

**Restore drill** phải:
1. Dùng recovery identity/phân quyền dự kiến.
2. Dựng target cô lập.
3. Tìm và giải mã backup bằng KMS/key đúng.
4. Áp dụng schema/config/roles.
5. Restore data và log chain.
6. Kiểm database reads/writes với test identities.
7. Kiểm unique/TTL/index và consistency.
8. Chạy application smoke/business tests.
9. Kiểm stream/CDC/projection recoverability.
10. Đo thời gian và ghi blocker.

Nếu chỉ chạy restore bằng user admin toàn quyền, drill có thể **bỏ qua chính những thiếu sót IAM cần phát hiện**.

## 61. Môi trường restore cần cô lập dữ liệu nhạy cảm

Backup chứa PII, tài chính hoặc secrets application-level. Test restore phải:
- Có environment và IAM riêng.
- Encryption at rest/in transit.
- Network hạn chế, không public endpoint.
- Access audit và data minimization.
- Không trỏ notification/payment integrations tới production.
- Dùng synthetic test accounts và cấm gửi email thật.
- Có cleanup sau drill.
- Retention rõ cho bản restore tạm.
- Không copy plaintext dump vào laptop/ticket/chat.

Restore drill an toàn phải tránh **biến kế hoạch phục hồi thành một vụ rò rỉ dữ liệu khác**.

## 62. Business validation sau restore

Một số kiểm tra:
- Record counts theo tenant/partition/collection.
- Checksum/aggregate có giải thích thay đổi theo recovery point.
- Unique business keys không bị duplicate.
- Document schema versions được application giải mã.
- Conditional writes/optimistic concurrency hoạt động.
- Read-your-writes/consistency behavior đúng policy.
- TTL/retention rules không xóa nhầm.
- Orders/payments/ledger totals đối soát.
- Role `reader` không thể ghi.
- Role `writer` không thể xóa backups/keys.
- Source projection/search/CDC có thể catch up.

Đếm số rows bằng nhau chưa chứng minh **giá trị, thứ tự hoặc quan hệ nghiệp vụ** đúng, đặc biệt khi có writes đồng thời và dữ liệu denormalized.

## 63. Schema drift và config drift

Drift xảy ra khi:
- Operator tạo index trực tiếp nhưng không cập nhật IaC.
- Một rule IAM được thêm trong emergency rồi không thu hồi.
- Replica RF thực tế khác manifest.
- TLS certificate được thay ngoài pipeline.
- KMS key alias đổi nhưng runbook chưa cập nhật.
- Backup lifecycle bị sửa trên console.
- Application schemaVersion mới đã deploy nhưng migration file thiếu.

Giải pháp:
- Snapshot inventory từ control plane.
- So sánh với versioned desired state.
- Ghi chênh lệch và owner.
- Cập nhật manifest theo change review.
- Cảnh báo drift ảnh hưởng recovery.
- Dùng IaC chỉ khi cơ chế import/adopt phù hợp, không áp dụng bừa lên live resources.

**Không coi Git là toàn bộ sự thật nếu production đã drift**; phải đối chiếu và điều chỉnh an toàn.

## 64. Quyền truy cập trong DR có thể vừa quá ít vừa quá nhiều

Hai rủi ro ngược nhau:

**Thiếu quyền:**
- Không đọc được backup.
- Không gọi được KMS.
- Không cấp network target.
- Không tạo table/index.
- Không restore users/roles.

**Quá quyền:**
- Restore operator có thể xóa production.
- CI runner thấy plaintext customer data.
- Service account có full admin.
- DR target public internet.
- Backup deletion không cần approval.

Một quy trình đúng cần **permission matrix được thử nghiệm**, không chỉ “đăng nhập bằng global admin khi có sự cố”.

## 65. Preflight trước khi restore

~~~text
[ ] Incident/recovery objective và recovery point đã duyệt.
[ ] Phân loại: logical corruption, disaster, ransomware hay migration error.
[ ] Backup catalog, data scope, snapshot/log chain đủ.
[ ] Checksums/integrity và manifest signature hợp lệ.
[ ] KMS/HSM key references còn dùng được.
[ ] Recovery identities có quyền tối thiểu đã test.
[ ] IaC/config/schema/app versions tương thích.
[ ] Network/quotas/storage/compute headroom đủ.
[ ] Certificate/secret bootstrap sẵn sàng.
[ ] Source và target isolation chính xác.
[ ] Kế hoạch side effects/CDC/outbox/replay được duyệt.
[ ] RPO/RTO/cutover và stop conditions đã định nghĩa.
[ ] Monitoring, audit và người trực sẵn sàng.
~~~

Không phải mọi sự cố đều cho phép chờ kiểm thủ công hết checklist, nhưng mọi ngoại lệ khẩn cấp cần **thẩm quyền, rủi ro và quyết định được ghi lại**, không coi “thiếu bằng chứng” là GO mặc định.

## 66. Restore execution state machine

~~~mermaid
flowchart TD
    A["Select recovery point"] --> B["Verify manifest, data and keys"]
    B --> C{"All required dependencies usable?"}
    C -->|"No"| STOP["NO-GO / resolve blocker"]
    C -->|"Yes"| D["Provision isolated target"]
    D --> E["Apply schema, configs, identities"]
    E --> F["Restore bytes and replay logs"]
    F --> G["Verify indexes, keys, authorization"]
    G --> H["Business data reconciliation"]
    H --> I{"RPO / correctness achieved?"}
    I -->|"No"| STOP
    I -->|"Yes"| J["Reconnect apps / CDC / projections"]
    J --> K{"SLO / RTO and access tests achieved?"}
    K -->|"No"| STOP
    K -->|"Yes"| L["Controlled cutover, monitor, audit"]
~~~

Bước restore phải có checkpoint/idempotency, không nên tự động “resume từ nơi gần nhất” nếu không biết thao tác nào đã hoàn tất. Một restore bị dừng có thể để lại dữ liệu partial; runbook phải quy định **clean restart hay resume an toàn**.

## 67. Khi restore thất bại vì AccessDenied

Đừng lập tức cấp quyền admin toàn cầu. Chẩn đoán theo lớp:
1. Principal/role thực tế trong request là gì?
2. Lỗi ở backup storage, KMS, DB target hay secret manager?
3. Account/region/resource ARN có đúng?
4. IAM identity policy và resource/key policy có cho phép?
5. Có explicit deny, boundary, organization policy, network condition không?
6. Encryption context/KMS grant có khớp không nếu dịch vụ dùng?
7. Có token/session hết hạn hoặc clock skew?
8. Có event audit để chứng minh policy evaluation?
9. Cần sửa quyền nào **tối thiểu**?
10. Có test lại bằng recovery principal dự kiến?

**AccessDenied không phải dấu hiệu phải vô hiệu bảo mật**, mà là tín hiệu xác định dependency chưa được phục hồi đúng.

## 68. Khi có file backup nhưng giải mã thất bại

Các giả thuyết:
- Sai key ID/region/version.
- Key disabled/deletion pending/deleted.
- KMS policy/grant thiếu.
- Encrypted DEK metadata không tương thích.
- Ciphertext bị hỏng hoặc sai encryption context.
- Backup copy chưa được re-encrypt theo policy vùng đích.
- HSM/KMS service unavailable.
- Phương thức cryptographic format không được client/tool hỗ trợ.
- Một secret trong envelope encryption chain bị mất.

Không thử brute-force hoặc thay plaintext key material thủ công trong production. Nên **xác minh metadata và quyền có thẩm quyền**, đối chiếu backups khác, thực hiện restore drill theo tài liệu sản phẩm và liên hệ security/key owner.

Nếu key material đã bị hủy và không có cơ chế khôi phục được nhà cung cấp/thiết kế hỗ trợ, có thể **không có cách giải mã**, cần báo tình trạng trung thực.

## 69. Khi data phục hồi nhưng ứng dụng vẫn lỗi

Checklist:
- SchemaVersion/serializer compatibility.
- Missing validators/indexes.
- Unique index build thất bại do duplicates.
- Keyspace/table/collection/table name khác.
- IAM/DB role chưa đúng.
- TLS/hostname/CA trust lỗi.
- Query/read/write consistency khác.
- Driver server discovery/connection pool.
- Redis key serialization và namespace.
- Search index/projection chưa rebuild.
- CDC checkpoint lệch recovery point.
- App config vẫn trỏ endpoint cũ.

Không chỉ tăng timeout hoặc disable authorization để che lỗi. Cần tìm **phụ thuộc nào vắng mặt so với recovery manifest**.

## 70. Khi restore được nhưng đã vượt RTO

Ví dụ:
~~~text
Data restore: 25 phút.
Schema/index rebuild: 70 phút.
KMS approval: 40 phút.
CDC catch-up: 30 phút.
```

Có thể tổng thực tế vượt RTO dù backup rất nhanh.

Hành động cải thiện:
- Pre-provision DR networking và roles.
- Warm standby metadata/indexes nếu phù hợp.
- Test key grants thường xuyên.
- Tối ưu backup granularity và transfer bandwidth.
- Có incremental restore/PITR path.
- Chọn mức service ưu tiên: read-only trước nếu được phép.
- Hạn chế data/index rebuild bằng snapshot strategy đúng.
- Rà soát RTO với business owner nếu yêu cầu không khả thi.

Không báo “restore thành công 25 phút” nếu business service phải mất hơn hai giờ mới đạt SLO.

## 71. Khi dữ liệu khôi phục đúng nhưng quyền quá rộng

Sau DR, có thể thấy:
~~~text
Tất cả services dùng credential admin tạm.
Một số collections chứa dữ liệu tenant khác cũng đọc được.
Backup storage public/readable cho role không liên quan.
```

Đây là **sự cố bảo mật mới** dù RPO đạt.

Cần:
1. Giảm quyền theo permission matrix.
2. Thu hồi break-glass/temporary credentials.
3. Kiểm deny tests và tenant isolation.
4. Kiểm backup/KMS access audit.
5. Kiểm network ingress.
6. Đánh giá cần rotate keys/secrets không.
7. Ghi evidence correction và post-incident review.

**Recovery success luôn gồm security correctness**, không chỉ data correctness.

## 72. Mô hình lỗi và mục tiêu phục hồi khác nhau

| Sự cố | Thách thức khác biệt |
|---|---|
| Một node hỏng | Replica rebuild, placement, cache cold |
| Cả cluster hỏng | Restore topology, data, roles, keys |
| Vùng cloud mất | Cross-region copy, KMS/IAM independence |
| Account production compromise | Backup immutability, recovery principal riêng |
| Logical corruption | Cần PITR trước thời điểm lỗi, tránh replay thao tác sai |
| Ransomware | Backup/keys/audit isolation, xác minh không nhiễm |
| Key disabled/deleted | Cryptographic dependency, có thể mất khả năng decrypt |
| Schema migration sai | Snapshot version và app compatibility |
| Credential leak | Rotate/reissue và kiểm backup access |
| CDC log retention mất | Rebuild projections từ snapshot và reconciliation |
| Backup catalog bị sửa | Signature/independent manifests |
| DR control plane unavailable | Bootstrap path và pre-provisioned resources |

Một kế hoạch duy nhất chưa chắc đủ cho mọi threat model. Cần chọn **kịch bản có xác suất và hậu quả đáng kể**.

## 73. Bảng trách nhiệm cho recovery package

| Thành phần | Owner đề xuất | Bằng chứng kiểm chứng |
|---|---|---|
| Data backup/log chain | Database platform | Restore drill + checksum |
| Schema/index/migrations | Application + data platform | Schema diff và migration tests |
| IaC/topology/config | Platform/SRE | Recreated environment |
| IAM/ACL/roles | Security/IAM owner | Least-privilege allow/deny tests |
| KMS/HSM dependencies | Key management/security | Decrypt test với recovery principal |
| Secrets/TLS | Security/platform | Service handshake và rotation drill |
| CDC/stream consumers | Data integration team | Replay/reconciliation |
| Business data validation | Product/domain owner | Invariant checks |
| RPO/RTO | Business continuity owner | Timed exercise report |
| Audit/privacy retention | Security/privacy | Access/deletion/hold evidence |

Không nên có một manifest vô chủ. Khi thay schema, key hoặc IAM policy, cần xác định **ai phải cập nhật tài liệu và diễn tập**.

## 74. Một mô hình đối chiếu sau restore

Ví dụ kiểm định:
~~~text
Source snapshot reference S at t0.
Recovered cluster R after replay to t0.
```

Có thể so:
- Document counts per collection/tenant và delta hợp lệ.
- Checksums theo partitions/buckets.
- Business aggregates như order totals, ledger balances.
- Unique key constraints.
- Data/schema versions.
- Permission matrices.
- KMS decrypt tests.
- Index and query plan behavior.
- CDC/outbox sequence checkpoints.
- Retention/TTL rules.

Nếu dataset có eventual consistency/replication lag, phải nêu **mốc snapshot và giới hạn so sánh**. Không so current production state tại t1 với restored t0 rồi mặc định mọi khác biệt là lỗi.

## 75. Bài tập thực hành

### Bài tập 1 — Backup tồn tại nhưng không phục hồi được

Một backup MongoDB có checksum đúng nhưng môi trường DR thiếu indexes, database roles và KMS grant. Hãy tách data artifact và recovery dependencies; đề xuất thứ tự khắc phục.

### Bài tập 2 — Schema linh hoạt

Một document store cho phép mỗi document có fields khác nhau. Vì sao vẫn phải bảo vệ schemaVersion, serializer, validators, unique indexes và migration history?

### Bài tập 3 — Unique index bị mất

Restore documents thành công nhưng thiếu unique index theo `(tenantId, externalOrderId)`. Xác định invariant bị phá và cách xác minh trước khi bật production writes.

### Bài tập 4 — TTL index sai

Một collection sau restore bị tạo TTL index với thời hạn ngắn hơn production. Những dữ liệu nào có nguy cơ mất và preflight nào cần có?

### Bài tập 5 — Schema v3 và app v4

Snapshot ở schema v3, application release hiện tại hiểu v4. Thiết kế compatibility matrix và bước migrate forward an toàn.

### Bài tập 6 — Infrastructure as Code

Thiết kế IaC bundle cho network, database topology, IAM policies và backup schedules. Fields nào được version-control, fields nào chỉ nên tham chiếu secret manager?

### Bài tập 7 — Bootstrap dependency loop

CI cần secret manager, secret manager lại phụ thuộc IdP trong region vừa mất. Đề xuất recovery identity/path độc lập và cách diễn tập.

### Bài tập 8 — Least privilege

Một restore engineer được cấp full-admin để khôi phục. Thiết kế permission matrix cho backup reader, KMS decrypt, DB target provisioning và policy administrator.

### Bài tập 9 — Envelope encryption

Vẽ data → DEK → wrapped DEK/KEK → encrypted backup → decrypt path. Phân biệt DEK, KEK và credentials truy cập backup.

### Bài tập 10 — Key K1 bị xóa sau rotation

Backup S1 cần K1; hệ đã dùng K2. Nếu K1 bị hủy, S1 ra sao? Nêu chính sách trước khi retire K1 và cách không lộ raw key.

### Bài tập 11 — Key alias đổi

Manifest chỉ có alias `backup/current`. Vì sao thiếu key identity/version có thể gây nhầm khi restore bản cũ?

### Bài tập 12 — KMS disabled

Backup vẫn ở object store nhưng key bị disabled. Đề xuất monitoring, quyền phục hồi và điều kiện xử lý mà không tự cấp admin không giới hạn.

### Bài tập 13 — HSM non-exportable key

Không thể export raw key từ HSM. Thiết kế key availability/restore strategy có nhiều failure domains mà không copy plaintext.

### Bài tập 14 — Cross-region DR

Copy encrypted backup từ region A sang B. KMS A không thể truy cập khi A outage. Những điều kiện nào phải kiểm để restore ở B?

### Bài tập 15 — Cross-account isolation

Một attacker có quyền admin database production nhưng không có quyền DR account. Thiết kế backup copies, immutability, IAM và KMS separation.

### Bài tập 16 — TLS và secrets

Database restore có dữ liệu nhưng client handshake lỗi vì CA trust khác. Nêu preflight certificate/secret references và quy trình cập nhật clients.

### Bài tập 17 — Manifest

Tạo YAML manifest có data scope, snapshot/log chain, checksum, schema revision, IaC revision, IAM role reference, KMS key ID, app release và CDC checkpoint; tuyệt đối không chứa raw secrets.

### Bài tập 18 — Consistent snapshot

Một copy files khi DB đang ghi không có coordination và WAL. Vì sao không tự coi đó là backup nhất quán? Đề xuất chiến lược thay thế.

### Bài tập 19 — Cross-shard recovery point

Hai shards được snapshot ở thời điểm khác nhau, có distributed transaction liên quan. Cần metadata/protocol gì để tránh phục hồi trạng thái một nửa?

### Bài tập 20 — RPO

RPO yêu cầu 5 phút, snapshot nửa đêm, log chain chỉ đến 09:57, sự cố 10:00. Tính RPO lý thuyết và liệt kê điều kiện phải kiểm chứng.

### Bài tập 21 — RTO critical path

Một restore có các bước provisioning 20 phút, KMS approval 40, data restore 35, index build 70, CDC catch-up 30. Thiết kế dependency graph và xác định đường găng, đề xuất cách giảm RTO.

### Bài tập 22 — MongoDB scope

So sánh logical dump một collection với full-cluster recovery: indexes/validators/users/roles/config servers/oplog/KMS. Những gì phải kiểm theo công cụ/version?

### Bài tập 23 — Cassandra schema

Restore SSTables nhưng dựng keyspace sai replication strategy và datacenter. Phân tích tác động tới `LOCAL_QUORUM` và tính đúng đường truy cập.

### Bài tập 24 — Cassandra security

Kế hoạch đưa users/roles và system keyspace metadata sang cụm mới cần giới hạn gì về phiên bản, topology và phương pháp được hỗ trợ?

### Bài tập 25 — Redis RDB/AOF

Redis khôi phục được keys nhưng thiếu ACL/TLS/cluster slot map. Thiết kế runbook để ứng dụng kết nối và kiểm slot coverage.

### Bài tập 26 — Redis cache vs authoritative state

Khi nào có thể rebuild Redis cache từ MongoDB mà không cần backup toàn bộ cached values? Khi nào Redis chứa dữ liệu cần RPO riêng?

### Bài tập 27 — DynamoDB PITR

Một bảng được restore thành target mới. Hãy kiểm table/index schema, IAM, KMS, Streams, TTL, autoscaling, Global Tables và app cutover mà không suy mọi settings tự theo backup.

### Bài tập 28 — CouchDB design documents

Business docs được restore nhưng design docs/security config và replication checkpoints chưa đúng. Những lỗi gì có thể xảy ra?

### Bài tập 29 — Search projection

Source database restore trong 20 phút nhưng rebuild search index mất sáu giờ, RTO một giờ. Đề xuất khả năng backup projection hoặc kế hoạch ưu tiên dịch vụ.

### Bài tập 30 — CDC checkpoint lệch

Source restore về t0, consumer checkpoint ở t1 sau t0. Vì sao `resume latest` không an toàn? Thiết kế snapshot + replay/reconciliation.

### Bài tập 31 — Ransomware

Attacker có quyền xóa database và backup trong cùng account. Đề xuất separation of duties, immutable DR copies, KMS key protection và detection.

### Bài tập 32 — Restore drill có PII

Một đội muốn tải production backup về laptop cá nhân để kiểm restore. Đề xuất môi trường kiểm cô lập, quyền, mã hóa, audit và cleanup.

### Bài tập 33 — Giám sát recovery readiness

Thiết kế dashboard theo dõi last restore drill, backup age, PITR gaps, key-decrypt tests, IAM drift, schema drift, CDC lag, certificate expiry và RTO.

### Bài tập 34 — Runbook AccessDenied

Recovery principal không đọc được backup object hoặc gọi KMS. Lập quy trình tìm identity/resource/key policy issue mà không cấp full-admin.

### Bài tập 35 — Tích hợp đa nền tảng

Một nền tảng có Java services, MongoDB orders, Cassandra events, Redis Cluster, DynamoDB preferences và search indexes. Hãy xây kế hoạch:

1. Business RPO/RTO theo data class.
2. Snapshot/log chains theo engine.
3. Schema/index/validators/serialization revisions.
4. IaC/topology/consistency/durability configs.
5. IAM/DB roles/ACL/secret references.
6. KMS/HSM key inventory, rotation và cross-region decrypt.
7. Immutable/offsite backups và threat model.
8. Manifest, integrity, approval và ownership.
9. Restore order, CDC/outbox/projection recovery.
10. Drill, functional/security validation và postflight handoff.

### Bài tập 36 — Phê bình kế hoạch bảo vệ sai

Một đề xuất:

~~~text
Backup file dữ liệu mỗi đêm là đủ.
Không cần lưu index/schema vì NoSQL không có schema.
Khôi phục Redis RDB thì ACL và Cluster slot map tự trở lại.
Dùng admin credential chung cho mọi DR jobs.
Sau rotation có thể xóa tất cả KMS keys cũ.
Copy encrypted backup sang region khác là đã DR-ready.
Không kiểm stream checkpoints hoặc app version.
Dùng backup ở production để test trên laptop nhân viên.
Restore xong thấy database UP là đạt RTO.
Không cần thử xóa/đọc backup với recovery identity.
~~~

Hãy chỉ ra từng giả định sai, hậu quả và viết lại một bản kế hoạch **bảo vệ trọn vẹn dữ liệu, schema, cấu hình, quyền và khả năng giải mã**, có bằng chứng kiểm chứng và phân quyền an toàn.

---

**Kết luận:** Một kế hoạch sao lưu và phục hồi NoSQL chỉ đáng tin khi bảo vệ **toàn bộ khả năng tái tạo dịch vụ**, không chỉ các bytes dữ liệu. **Schema, validators, indexes, migration versions, configuration/topology, identity/IAM/ACL, TLS/secrets và KMS/HSM encryption keys** đều là phụ thuộc của recovery. Backup cần có manifest về scope, consistency point, log chain, key references và compatibility; khóa mã hóa phải tồn tại và có thể được dùng từ môi trường DR đúng quyền, kể cả sau rotation hoặc lỗi vùng. Một quy trình tốt triển khai **least privilege, separation of duties, integrity checks, immutable copies và restore drills** để kiểm chứng khả năng đọc backup, phục hồi schema/permissions, đối soát business state, bắt kịp CDC/projections và đạt RPO/RTO. **Không bao giờ coi backup tồn tại, database process UP hoặc dashboard xanh là bằng chứng đủ rằng hệ có thể phục hồi an toàn.**

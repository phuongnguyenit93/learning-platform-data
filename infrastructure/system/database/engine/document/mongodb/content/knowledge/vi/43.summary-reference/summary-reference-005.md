# Checklist rà soát mô hình, truy vấn, bảo mật, sao lưu và vận hành MongoDB

Một ứng dụng MongoDB có thể chạy đúng các ca CRUD cơ bản nhưng vẫn gặp rủi ro khi đưa vào production: document tăng vô hạn theo thời gian, index không theo mẫu truy vấn thật, trường hợp `null` làm hỏng unique constraint, ứng dụng đọc nhầm tenant khác, backup chưa từng restore, hoặc một lần failover khiến hàng loạt request tạo đơn trùng vì retry không có idempotency. Những vấn đề đó thuộc **các lớp khác nhau**, nên một lần kiểm tra riêng code Java hoặc một lệnh `db.stats()` sẽ không cho kết luận đủ tin cậy.

Bài **“Checklist rà soát mô hình, truy vấn, bảo mật, sao lưu và vận hành”** thuộc chương **Tổng kết và tra cứu** của module **Database Engine Document MongoDB**. Đây là tài liệu dùng để rà soát một thiết kế trước triển khai, kiểm tra định kỳ hệ thống đang chạy, chuẩn bị cho thay đổi lớn và bàn giao vận hành. Mỗi mục phải dẫn tới **bằng chứng cụ thể** và **quyết định hành động** chứ không chỉ là câu trả lời cảm tính “đã xem”.

## 1. Kết quả cần đạt và năm trụ cột rà soát

Sau khi dùng tài liệu, nhóm phụ trách nên trả lời được:

1. **Mô hình dữ liệu:** document, liên kết, kiểu BSON, unique constraints và vòng đời dữ liệu có phù hợp nghiệp vụ và tốc độ tăng trưởng không?
2. **Truy vấn và hiệu năng:** các query/aggregation/index quan trọng có được quan sát bằng workload thật và `explain` đúng cách không?
3. **Bảo mật:** authentication, database RBAC, tenant authorization, network/TLS, quản lý secrets và bảo vệ PII có đủ lớp không?
4. **Sao lưu và khôi phục:** có bản backup sử dụng được, mục tiêu RPO/RTO, quy trình restore và bằng chứng diễn tập không?
5. **Vận hành:** hệ thống có monitoring, alert, capacity plan, runbook, maintenance và quy trình ứng phó failure/failover không?

Sơ đồ kiểm tra tổng thể:

```text
Yêu cầu nghiệp vụ và SLO/RPO/RTO
                 |
                 v
          MÔ HÌNH DỮ LIỆU
     schema, key, quan hệ, retention
                 |
                 v
         TRUY VẤN VÀ INDEX
       access patterns, explain, load
                 |
                 v
              BẢO MẬT
    auth, quyền, tenant, TLS, secrets
                 |
                 v
          SAO LƯU / RESTORE
      backups, PITR, drills, evidence
                 |
                 v
              VẬN HÀNH
       metrics, failover, runbooks
                 |
                 v
         RỦI RO + OWNER + HẠN XỬ LÝ
                 |
                 v
         Quyết định release / cải tiến
```

**Phạm vi:** MongoDB tự quản lý, replica set, sharded cluster, Atlas và ứng dụng Java/Spring Data MongoDB; tính năng thực tế phụ thuộc server version, cluster tier, topology, driver và cấu hình. Ví dụ dùng database và dữ liệu giả. Không chạy lệnh thay đổi schema, xóa dữ liệu hoặc mô phỏng sự cố trên production chỉ vì có mặt trong checklist.

## 2. Cách dùng checklist để không biến thành hình thức

Với mỗi mục, ghi một trong bốn trạng thái:

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **PASS** | Đã kiểm tra và có bằng chứng còn hiệu lực | Unique index có thật, test duplicate thất bại đúng |
| **FAIL** | Có bằng chứng không đáp ứng yêu cầu | User chỉ đọc vẫn có quyền xóa |
| **UNKNOWN** | Chưa có bằng chứng đáng tin | Backup có lịch chạy nhưng chưa restore thử |
| **N/A** | Không áp dụng, có giải thích | Không dùng sharding nên mục shard key N/A |

Không ghi `PASS` chỉ vì một cấu hình xuất hiện trong source code hoặc wiki. **Code được viết, tài nguyên được tạo, cấu hình đang chạy và hành vi quan sát được** là bốn loại bằng chứng khác nhau.

Mỗi finding nên lưu:

```text
Mã kiểm tra:
Yêu cầu/tiêu chí:
Môi trường:
Trạng thái: PASS | FAIL | UNKNOWN | N/A
Bằng chứng: link dashboard/query plan/test report/change ticket
Ảnh hưởng nếu sai:
Mức độ rủi ro:
Owner:
Hạn xử lý:
Biện pháp tạm thời:
Ngày kiểm tra và người kiểm tra:
```

### Phân loại rủi ro

- **Critical:** có khả năng mất dữ liệu, lộ bí mật, đọc/ghi chéo tenant, hoặc không khôi phục được dịch vụ tối quan trọng.
- **High:** dễ gây gián đoạn sản xuất, quá tải nhanh, mất bảo đảm consistency hoặc không đáp ứng RPO/RTO.
- **Medium:** thiếu capacity headroom, query không ổn định ở tải cao, thiếu cảnh báo quan trọng.
- **Low:** vấn đề tài liệu, cải tiến nhỏ có workaround đã kiểm chứng.

Đây là gợi ý để review; mức severity cuối cùng cần dựa trên criticality, phạm vi tác động, khả năng khai thác và chính sách tổ chức.

## 3. Khi nào cần rà soát lại?

| Thời điểm | Trọng tâm |
| --- | --- |
| **Trước thiết kế** | Access patterns, aggregate boundaries, growth, security model, RPO/RTO |
| **Trước release** | Indexes thật, migrations, query plans, quyền, backup, rollback |
| **Sau đổi workload** | Index performance, hot keys, CPU/RAM/disk, SLO |
| **Sau thêm collection/field nhạy cảm** | Schema validation, DTO/redaction, encryption, access control |
| **Trước sharding/cluster resize** | Shard key, unique indexes, capacity, data migration, failover |
| **Trước nâng cấp phiên bản** | Driver/server compatibility, deprecated behavior, restore/failback |
| **Hàng tháng/quý** | Role review, backups/drills, alert rules, unused indexes, retention |
| **Sau incident** | Root cause, dữ liệu ảnh hưởng, alert gap, runbook, remediation |

Đối với hệ thống nhỏ, nhiều kiểm tra có thể gộp trong một buổi. Đối với hệ thống lớn, nên phân công riêng engineering, DBA/SRE, security và người chịu trách nhiệm nghiệp vụ.

## 4. Chốt yêu cầu phi chức năng trước khi đánh giá

Chưa thể kết luận một cluster “đủ tốt” nếu không biết mục tiêu:

- **SLO đọc/ghi:** p95/p99, throughput, error budget, số clients đồng thời.
- **RPO:** mức mất dữ liệu tối đa chấp nhận được.
- **RTO:** thời gian cho phép để khôi phục dịch vụ.
- **Data retention:** dữ liệu nào phải giữ, bao lâu, ở đâu.
- **Consistency:** user có cần read-your-writes, đọc mới nhất hay chấp nhận eventual consistency?
- **Bảo mật và pháp lý:** loại PII, residency, audit, nguyên tắc least privilege.
- **Tăng trưởng:** data, index, oplog, backup, working set và write volume theo thời gian.
- **Các failure domains:** node, AZ, region, cloud provider hoặc dependency bên ngoài.

Checklist:

- [ ] Có danh sách use cases quan trọng và owner từng use case.
- [ ] Có định nghĩa thành công/thất bại cho critical writes.
- [ ] Có SLO latency/availability và budget retries.
- [ ] Có RPO/RTO được phê duyệt, không chỉ “backup hằng ngày”.
- [ ] Biết các yêu cầu encryption, logging và data retention.
- [ ] Biết giới hạn chi phí/khả năng mở rộng.

## 5. Lập bản đồ tài sản MongoDB

Trước khi review collection, cần có **inventory những thứ đang thật sự vận hành**:

```text
Environment -> cluster / project
            -> region / topology / MongoDB version
            -> databases / collections
            -> indexes / validators / TTL
            -> service accounts / roles
            -> applications / jobs / CDC consumers
            -> storage / backup / network controls
            -> owning team / escalation contact
```

Checklist:

- [ ] Có owner của mỗi cluster/database/collection quan trọng.
- [ ] Biết version server, driver Java, Spring Data và upgrade path.
- [ ] Biết replica set/sharded topology, shard keys và regions.
- [ ] Biết các đường ghi ngoài ứng dụng chính: ETL, migration, scheduler, mongosh, import tool.
- [ ] Biết các client đọc: API, analytics, change streams, export, backups.
- [ ] Có môi trường staging đủ đại diện cho các thay đổi quan trọng.
- [ ] Secrets và topology details được lưu ở hệ thống có quyền truy cập, không public repo.

**Dấu hiệu rủi ro:** “chỉ ứng dụng này ghi collection” nhưng tồn tại migration scripts hoặc background workers không có owner rõ.

## 6. Mô hình dữ liệu: aggregate boundaries

MongoDB lưu dữ liệu dạng documents; **đơn vị truy vấn và tính nguyên tử single-document** nên được cân nhắc khi chọn cấu trúc.

Ví dụ đơn hàng:

```javascript
{
  _id: "ORD-001",
  tenantId: "tenant-a",
  status: "RESERVED",
  items: [
    { sku: "SKU-A", quantity: 2, price: NumberDecimal("125000") },
    { sku: "SKU-B", quantity: 1, price: NumberDecimal("85000") }
  ],
  total: NumberDecimal("335000")
}
```

Các dòng hàng thường được đọc và sửa trong ngữ cảnh một đơn có thể phù hợp để embed trong order document. Nhưng thông tin product master, lịch sử giá dài hạn hoặc hồ sơ khách hàng có vòng đời độc lập thường cần cách lưu khác.

Checklist:

- [ ] Mỗi document đại diện một aggregate/business entity được định nghĩa rõ.
- [ ] Những fields thường được đọc cùng nhau được cân nhắc embed hợp lý.
- [ ] Các collections tham chiếu có ownership và lifecycle rõ ràng.
- [ ] Có quy tắc khi dữ liệu nhúng được sửa nhưng nguồn tham chiếu thay đổi.
- [ ] Có nguyên tắc tránh write hotspots trên một document.
- [ ] Invariants nhiều collections được thực thi bằng transaction hoặc workflow phù hợp.

**Bằng chứng:** ví dụ 3–5 request nghiệp vụ thật và đường đi tới các collections, không chỉ sơ đồ ERD được chuyển nguyên từ SQL.

## 7. Embed hay reference?

| Câu hỏi | Nếu “có” | Gợi ý |
| --- | --- | --- |
| Dữ liệu con luôn đọc cùng dữ liệu cha? | Có | Cân nhắc embed |
| Số phần tử con tăng vô hạn? | Có | Cân nhắc collection riêng |
| Con có owner/lifecycle độc lập? | Có | Thường reference |
| Cần cập nhật cha và con nguyên tử? | Có | Embed nếu kích thước/cardinality cho phép |
| Nhiều tài liệu cần dùng chung một thực thể? | Có | Reference hoặc snapshot theo nghiệp vụ |
| Cần join/report liên collection phức tạp? | Có | Đánh giá `$lookup`, denormalization và chi phí |

Ví dụ lịch sử sự kiện ghi vào `events:[]` trong một account document sẽ tăng mãi nếu không có giới hạn. Giữ events trong collection riêng với key accountId/time có thể phù hợp hơn.

Checklist:

- [ ] Không có array “không giới hạn” trên một document nóng.
- [ ] Không làm nhiều documents lặp lại PII nhạy cảm ngoài nhu cầu.
- [ ] Nếu denormalize, có quy tắc đồng bộ và stale-data tolerance.
- [ ] Có thử nghiệm kích thước document tương lai, không chỉ dữ liệu demo.

## 8. Kiểm tra document size, cardinality và tốc độ tăng

MongoDB có giới hạn BSON document size **16 MiB** cho document thông thường. Thiết kế phải xét tốc độ tăng thực, số phần tử array và các nested objects.

Ví dụ cần dự báo:

```text
Một user có 2 sự kiện mỗi phút
~2 x 60 x 24 x 365 = 1.051.200 sự kiện/năm
```

Không nên nhúng toàn bộ lịch sử sự kiện vào một user document. Ngoài giới hạn size, mỗi update trên document lớn có thể làm tăng contention và chi phí.

Checklist:

- [ ] Có maximum/percentile document size theo collection.
- [ ] Biết các arrays có thể tăng không giới hạn.
- [ ] Biết high-cardinality fields và phân bố giá trị.
- [ ] Có chiến lược bucketing/archive hoặc reference cho history.
- [ ] Có dự báo growth theo số tenant/user/transaction.
- [ ] Không để một document hot phải chứa mọi counters/events của cả hệ thống.

**Đừng chỉ xem trung bình:** một số tenant hoặc thiết bị rất lớn có thể chạm giới hạn trước phần còn lại.

## 9. Kiểu dữ liệu BSON và ID

Checklist:

- [ ] `_id` có kiểu thống nhất: ObjectId, String, UUID Binary subtype phù hợp.
- [ ] Java POJO/codec không trộn ObjectId với String hex cho cùng ý nghĩa.
- [ ] UUID dùng representation nhất quán giữa writers (ví dụ STANDARD khi policy chọn).
- [ ] Số tiền dùng `Decimal128`/`BigDecimal` với quy tắc precision/scale, không dùng Double tùy tiện.
- [ ] Timestamp lưu dưới dạng BSON Date/UTC theo quy tắc nhất quán.
- [ ] Phân biệt `Instant`, `LocalDate`, `LocalDateTime` và timezone conversion ở ứng dụng.
- [ ] Các fields ID từ nguồn bên ngoài được normalize type/format.
- [ ] Enumerations có contract cho giá trị lạ và schema migration.
- [ ] Không dùng String cho mọi kiểu dữ liệu chỉ để dễ serialize JSON.

Ví dụ hai truy vấn dưới đây **không phải lúc nào tương đương**:

```javascript
db.orders.findOne({ _id: ObjectId("65f000000000000000000001") });
db.orders.findOne({ _id: "65f000000000000000000001" });
```

Vì BSON ObjectId và BSON String khác kiểu. Khi migrate, test cả code cũ và code mới.

## 10. Null, missing và defaults

MongoDB có các trạng thái khác nhau:

```javascript
{ _id: 1, email: null }
{ _id: 2 }
{ _id: 3, email: "" }
```

Query:

```javascript
db.customers.find({ email: null });
```

thường match cả **field explicit null** và **field missing**. Một unique single-field index không-partial có semantics null/missing cần hiểu trước khi thêm dữ liệu optional.

Checklist:

- [ ] Có semantics rõ cho missing, explicit null, empty string và empty array.
- [ ] API DTO có quy tắc patch: omitted field là “không đổi” hay “xóa”?
- [ ] Unique optional field dùng index strategy đúng (partial/sparse nếu cần).
- [ ] Các quy tắc so sánh kiểu BSON được kiểm thử.
- [ ] Không giả định default trong Java tự được backfill trên database.

Lệnh tra cứu:

```javascript
// Field không tồn tại:
db.customers.find({ email: { $exists: false } }).limit(20);

// Field có BSON Null:
db.customers.find({ email: { $type: 10 } }).limit(20);
```

## 11. Schema validation và quản lý thay đổi

MongoDB linh hoạt về schema, nhưng **không có nghĩa mọi document trong collection đều nên khác nhau**.

Checklist:

- [ ] Có tài liệu field bắt buộc/tùy chọn, BSON types và validation rules.
- [ ] Có collection validator/`$jsonSchema` hoặc validation tương đương ở application khi phù hợp.
- [ ] Có validation ở API trước khi ghi để trả lỗi dễ hiểu.
- [ ] Validator được thử với positive/negative fixtures.
- [ ] Khi thêm field mới, readers cũ xử lý missing field an toàn.
- [ ] Có schema version hoặc migration strategy cho dữ liệu legacy khi cần.
- [ ] Index mới được build từ dữ liệu sạch, không assume annotation tự deploy.
- [ ] Migration có kế hoạch rollback/forward-fix khi phải chạy lâu.
- [ ] Không thay type của field shared giữa các services mà không có compatibility window.

Ví dụ validator khái niệm:

```javascript
db.createCollection("reviews", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "rating"],
      properties: {
        tenantId: { bsonType: "string" },
        rating: {
          bsonType: "int",
          minimum: 1,
          maximum: 5
        }
      }
    }
  }
});
```

Lệnh tạo collection chỉ chạy trong **lab** hoặc migration được duyệt. Validator không thay authorization theo tenant.

## 12. Mẫu schema evolution an toàn

Một thay đổi field thường nên theo hướng **expand → migrate → contract**:

```text
Release A: Readers hiểu cả oldField và newField
          Writers chuyển dần sang newField
              |
              v
Migration: Backfill/dual-read/verify
              |
              v
Release B: Ngừng phụ thuộc oldField
              |
              v
Cleanup: Bỏ oldField khi đã có backup và điều kiện
```

Checklist:

- [ ] Client versions cũ/mới trong rollout có thể cùng tồn tại.
- [ ] Migration idempotent hoặc có checkpoint/resume marker.
- [ ] Có bounded batch size, rate limit và kiểm soát oplog/secondary lag.
- [ ] Có số liệu trước/sau: matched, modified, missing, invalid types.
- [ ] Không viết script update hàng triệu documents mà thiếu dry-run và observability.
- [ ] Có plan nếu unique index build thất bại vì duplicates.

**Rủi ro:** sửa field `amount` từ String sang Decimal128 trong lúc một job Java cũ vẫn ghi String; dữ liệu trở thành mixed types và query/index/filter có hành vi khó đoán.

## 13. Dữ liệu thời gian, TTL và retention

Checklist:

- [ ] Phân loại data: giao dịch, audit, logs, sensor metrics, sessions, tokens, backups.
- [ ] Có retention policy và legal hold cho từng loại.
- [ ] TTL index chỉ dùng ở collection phù hợp; expiry không được coi là tức thời.
- [ ] Time series collection dùng `timeField/metaField/granularity` phù hợp nếu workload là measurements.
- [ ] Không dùng TTL để thay business cancellation hoặc authorization.
- [ ] Có archive/rollup/downsampling cho dữ liệu lịch sử lớn.
- [ ] Kiểm tra secondary/oplog impact nếu xoá hàng loạt.
- [ ] Biết dữ liệu đã xóa ở collection vẫn có thể tồn tại trong backup/snapshot trong retention window.

Ví dụ index TTL:

```javascript
db.temporary_sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0, name: "ttl_expires_at" }
);
```

Chỉ tạo khi policy chấp nhận expiry dựa trên BSON Date và TTL monitor asynchronous. Kiểm tra collection options/index restrictions theo server version.

## 14. Shard key và khả năng mở rộng

Chỉ áp dụng nếu cluster dùng hoặc chuẩn bị dùng sharding.

Checklist:

- [ ] Shard key phù hợp query routing và write distribution.
- [ ] Phân bố khóa tránh hotspot (ví dụ một giá trị tenant quá lớn).
- [ ] Đã phân tích cardinality, monotonicity và frequency của shard key.
- [ ] Các truy vấn critical có shard key/effective targeting khi cần.
- [ ] Unique index đáp ứng restriction trên sharded collections của version đang chạy.
- [ ] Có dự báo chunk distribution, balancer/migration cost và shard capacity.
- [ ] Có plan cho query scatter-gather không thể tránh.
- [ ] Đã kiểm tra cross-shard transactions/aggregations và latency.

**Không chọn shard key chỉ vì field được dùng nhiều trong filter**; cần xem phân bố load, tính bất biến, index constraints và yêu cầu routing.

## 15. Danh mục workload và mẫu truy vấn

Mỗi collection quan trọng nên có bảng:

| Query ID | Truy vấn | Tần suất | SLO | Index dự kiến |
| --- | --- | --- | --- | --- |
| Q1 | Get order theo tenant + ID | Cao | p95 thấp | `_id_` + tenant check |
| Q2 | List orders tenant theo createdAt giảm dần | Cao | p95 thấp | `{tenantId:1,createdAt:-1}` |
| Q3 | Đơn theo status/time window | Trung bình | Theo báo cáo | Compound index theo filter/sort |
| Q4 | Update inventory theo SKU + available | Cao | Ghi có điều kiện | Unique `_id` |
| Q5 | Aggregation doanh thu theo tháng | Theo batch | Bounded | Pipeline/rollup đánh giá riêng |

Checklist:

- [ ] Biết top queries theo **thời gian tích lũy** và theo **p95/p99**, không chỉ số lần.
- [ ] Có query shape, filter, sort, projection, limit, batch size.
- [ ] Có thống kê cardinality/selectivity trên dữ liệu đại diện.
- [ ] Có query/aggregation đột biến theo tenant lớn.
- [ ] Có workload peak và background jobs.
- [ ] Có connection pool behavior và retry amplification.

**Bằng chứng:** logs/profiler/Atlas Query Profiler hoặc công cụ APM được phép, đã loại bỏ PII; không chạy profiler mức cao trên production theo phản xạ.

## 16. Đánh giá index: ít nhưng đúng

Index làm truy vấn nhanh hơn trong trường hợp phù hợp nhưng có chi phí:

- Bộ nhớ/index cache.
- Disk storage và backup.
- Insert/update/delete phải duy trì index entries.
- Build/rebuild và migration time.

Checklist:

- [ ] Mỗi index có query shape hoặc unique/TTL requirement cụ thể.
- [ ] Key order của compound index phù hợp equality/range/sort.
- [ ] Đã kiểm tra collation cho string comparison/case-insensitive searches.
- [ ] Đã đánh giá partial/sparse/unique/multikey index semantics.
- [ ] Không tạo duplicate/redundant indexes không có lý do.
- [ ] Không drop index production chỉ vì thấy ít được dùng trong một cửa sổ ngắn.
- [ ] Biết index size và tốc độ tăng.
- [ ] Khi sửa index, có plan build, rollout, quyền, load và rollback.

Ví dụ:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created_desc" }
);
```

Chỉ là ví dụ index candidate. Có phù hợp hay không phải kiểm chứng bằng workload/explain; không tạo theo công thức cho mọi query.

## 17. Equality, sort, range và thứ tự compound index

Một nguyên tắc thực dụng thường được gọi là **ESR** (Equality → Sort → Range) để cân nhắc thứ tự fields trong compound index, nhưng không phải luật cứng cho mọi truy vấn.

Ví dụ query:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(50);
```

Index candidate:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

Checklist:

- [ ] Equality filters có khả năng giới hạn scan hiệu quả.
- [ ] Sort có được index hỗ trợ hay xuất hiện blocking SORT?
- [ ] Range predicates và thứ tự fields đã đo bằng explain.
- [ ] Không dùng một giant compound index để “bao hết mọi API”.
- [ ] Đã cân nhắc index prefix reuse cho các query shapes khác.
- [ ] Query với `$in`, regex, collation và multikey được kiểm tra riêng.

**Đừng chỉ nhìn số lượng index:** vấn đề là index nào được chọn, số keys/docs phải đọc và chi phí write duy trì chúng.

## 18. Unique indexes: lỗi thường bị bỏ sót

Checklist:

- [ ] Mọi business unique key có unique index thực tế, không chỉ check ở ứng dụng.
- [ ] Với multi-tenant, index scope gồm tenant khi business identity theo tenant.
- [ ] Các optional fields có policy rõ cho `null`/missing.
- [ ] Có xử lý `E11000` theo **index gây lỗi**, không catch-all success.
- [ ] `upsert` filter khớp business unique identity, tránh thêm status/version gây no-match và duplicate insert.
- [ ] Cùng idempotency key nhưng payload khác phải được xem là conflict.
- [ ] Collation/case normalization không gây duplicate khó giải thích.
- [ ] Có test concurrent insert/upsert.

Đặc biệt:

```javascript
db.orders.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uk_tenant_request" }
);
```

Một unique index giúp chặn hai orders cùng key, nhưng **không tự ngăn thanh toán hoặc email gửi hai lần** nếu code retry outside transaction/outbox.

## 19. Multikey, array queries và indexing

Checklist:

- [ ] Query array-of-documents dùng `$elemMatch` khi nhiều điều kiện phải cùng một phần tử.
- [ ] Đã biết khi nào dot notation có thể match **khác phần tử** trong mảng.
- [ ] Compound multikey restrictions được kiểm tra.
- [ ] Không assume unique multikey index cấm duplicate **bên trong một array của cùng document**.
- [ ] Large arrays không làm document và update quá nặng.
- [ ] Có projection/limit để tránh trả arrays lớn không cần thiết.

Ví dụ:

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "SKU-A",
      quantity: { $gte: 2 }
    }
  }
});
```

Nếu chỉ dùng `"items.sku":"SKU-A"` và `"items.quantity":{$gte:2}` cùng lúc, hai điều kiện có thể được thỏa ở **hai phần tử khác nhau**. Đây có thể là lỗi tính đúng đắn, không chỉ lỗi performance.

## 20. Kế hoạch thực thi: đọc `explain` đúng

Lệnh quan sát trong lab/staging:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20)
  .explain("executionStats");
```

Các chỉ số/đặc điểm đáng xem:

- `winningPlan` và các stages tương ứng với engine/version.
- `IXSCAN` / `COLLSCAN`, index key pattern thực.
- `totalKeysExamined` và `totalDocsExamined`.
- `nReturned`.
- Có blocking sort hay không.
- Ước lượng execution time và pipeline stages.
- Query có bị scatter-gather ở sharded cluster không.

Checklist:

- [ ] Explain được chạy với **dữ liệu có phân bố và kích thước đại diện**.
- [ ] Các indexes/filters/sorts giống production.
- [ ] Không dùng một explain rất nhanh trên collection 20 documents làm bằng chứng SLO.
- [ ] Đã kiểm tra `docsExamined/nReturned` và `keysExamined/nReturned`.
- [ ] Có đối chiếu latency thực với cache warm/cold và concurrency.
- [ ] Không coi mọi COLLSCAN đều sai: collection nhỏ hoặc full scan có chủ đích có thể hợp lý.

**Lưu ý:** `explain` có semantics riêng, và `executionStats` là kết quả thực thi thử có thể đọc/scan dữ liệu đáng kể. Không chạy query/aggregation quá nặng trên primary trong incident chỉ để lấy explain.

## 21. Projection, covered queries và hạn chế dữ liệu

Ví dụ API chỉ cần:

```javascript
db.orders.find(
  { tenantId: "tenant-a", status: "PAID" },
  { _id: 1, status: 1, total: 1, createdAt: 1 }
).limit(50);
```

Checklist:

- [ ] API không trả toàn document khi chỉ cần vài fields.
- [ ] Projection không lộ PII/password/token/internal fields.
- [ ] Có kiểm tra network payload size và serialization cost.
- [ ] Covered query được đánh giá đúng constraints, không coi là mục tiêu bắt buộc.
- [ ] Không dùng negative projection blacklist làm bảo mật duy nhất nếu schema thường xuyên thêm sensitive fields.
- [ ] DTO allowlist ở API có schema/contract rõ.

**Projection không thay authorization**. Trả ít fields của document tenant khác vẫn là rò rỉ.

## 22. Aggregation: giới hạn bộ nhớ và scope dữ liệu

Checklist:

- [ ] `$match` sớm khi semantic cho phép, dùng indexes phù hợp.
- [ ] `$project`/`$unset` loại fields không cần thiết.
- [ ] `$group` có cardinality dự tính; không gom hàng triệu keys không budget.
- [ ] `$lookup` có join keys/indexes đúng và tenant boundaries.
- [ ] `$sort`, `$facet`, `$unwind` được đo output expansion.
- [ ] Không bật `allowDiskUse` mù quáng khi disk/IOPS thiếu.
- [ ] Có limit/timeouts/quotas cho reporting endpoints.
- [ ] Đã cân nhắc pre-aggregation/rollup thay vì quét toàn history mỗi request.
- [ ] Pipeline không vô tình lấy dữ liệu từ tenant khác khi `$lookup`/`$unionWith`.

Ví dụ:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID",
      createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
    }
  },
  {
    $group: {
      _id: "$currency",
      total: { $sum: "$total" },
      orderCount: { $sum: 1 }
    }
  }
]);
```

Không cộng tiền khác currency thành một tổng chung nếu business logic không quy đổi theo quy tắc tỷ giá rõ ràng.

## 23. Pagination, sorting và cursor lifecycle

Checklist:

- [ ] Sorting có **tiebreaker duy nhất** để phân trang ổn định, thường `_id`.
- [ ] Deep pagination bằng `skip` đã được đánh giá chi phí; có keyset/range pagination cho feed lớn nếu phù hợp.
- [ ] Cursor batch size/timeouts phù hợp workload.
- [ ] Các queries từ Java không vô tình materialize toàn bộ collection vào List.
- [ ] Có limit tối đa cho client-supplied page size.
- [ ] Multi-tenant scope và authorization được giữ nguyên trên mọi trang.

Ví dụ keyset với sort mới nhất:

```javascript
// Index candidate:
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 }
);

db.orders.find({
  tenantId: "tenant-a",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
}).sort({ createdAt: -1, _id: -1 }).limit(50);
```

`lastCreatedAt` và `lastId` là **biến ứng dụng**, phải encode/decode và kiểm soát tenant từ principal; ví dụ không phải copy-paste độc lập khi chưa định nghĩa chúng.

## 24. Write patterns, contention và idempotency

Checklist:

- [ ] Không dùng read–modify–write thiếu version/CAS cho data có cạnh tranh.
- [ ] Với counter/stock, cân nhắc atomic `$inc` + business predicate.
- [ ] Với same key/same payload, retry không tạo duplicate business effect.
- [ ] Có unique idempotency key và response contract.
- [ ] MongoDB transactions chỉ dùng cho invariants phải commit nhiều documents.
- [ ] Transactions ngắn, không gọi payment/email trong callback có thể retry.
- [ ] Có xử lý `WriteConflict`, `TransientTransactionError` và unknown commit outcome theo driver.
- [ ] Không coi mọi timeout là ghi thất bại chắc chắn.
- [ ] Có bounded retries, backoff/jitter và rate limit.
- [ ] Có test 2–100 writes đồng thời theo hot key, không chỉ unit tests.

Ví dụ conditional decrement:

```javascript
db.inventory.updateOne(
  { _id: "SKU-A", available: { $gte: 2 } },
  { $inc: { available: -2 } }
);
```

Đây là atomic update **trên một document**, không tự làm atomic với insert order ở collection khác. Với đơn hàng và tồn kho cần cùng commit, dùng transaction hoặc workflow bù trừ được thiết kế rõ.

## 25. Mẫu kiểm tra tính đúng đắn theo invariant

Đối với nghiệp vụ quan trọng, nên có **invariant cụ thể**:

| Nghiệp vụ | Invariant |
| --- | --- |
| Inventory | `available >= 0` |
| Tạo đơn | Mỗi `(tenantId, requestId)` tối đa một order |
| Giữ hàng | Available + active reserved quantity khớp stock movements |
| Ví/ledger | Tổng bút toán cân bằng theo kế toán |
| User profile | Update không ghi đè version mới hơn |
| Booking | Không có hai reservations không tương thích trên cùng đơn vị/thời gian |
| Event consumer | Cùng event ID không gây side effect lặp |

Checklist:

- [ ] Invariant được viết thành assertions/tests/reconciliation jobs.
- [ ] Không chỉ check HTTP 200 hoặc “MongoDB command không lỗi”.
- [ ] Có test transaction abort/fault injection giữa chừng.
- [ ] Có cơ chế xử lý data drift sau outage.
- [ ] Có owner nghiệp vụ phê duyệt cách bù trừ, không xóa records tùy tiện.

## 26. Replica set, write concern và read preference

Checklist:

- [ ] Biết replica set members/votes, failure domains và điều kiện có majority.
- [ ] Có primary/secondary replication health monitoring.
- [ ] Write concern cho critical writes phù hợp RPO, không mặc định `w:0`.
- [ ] Có read preference policy rõ theo endpoint.
- [ ] Khi đọc secondary, application chấp nhận replication lag theo nghiệp vụ.
- [ ] Read concern được chọn theo consistency requirement (local/majority/snapshot/linearizable khi phù hợp).
- [ ] Có plan khi election, stepdown và primary không khả dụng.
- [ ] Không cho read preference secondary làm check idempotency sai vì chưa nhìn thấy order mới.

**Cần tách hai câu hỏi:** “write có được majority acknowledgment không?” và “read có nhìn thấy phiên bản nào?”. Một read từ secondary có thể trả dữ liệu cũ dù write vừa thành công trên primary.

## 27. Kiểm tra transaction boundaries

Trong Java Sync Driver:

```java
try (ClientSession session = mongoClient.startSession()) {
    session.withTransaction(() -> {
        orders.insertOne(session, newOrder);
        inventory.updateOne(
            session,
            stockFilter,
            stockUpdate
        );
        return null;
    }, transactionOptions);
}
```

Đây là code minh họa: các biến `mongoClient`, `orders`, `inventory`, `newOrder`, `stockFilter`, `stockUpdate` và `transactionOptions` do service tạo. Không đưa external non-idempotent side effects vào callback.

Checklist:

- [ ] Mọi MongoDB operations cần atomic đều tham gia cùng session/transaction.
- [ ] Mỗi concurrent transaction có session riêng.
- [ ] Application biết operation nào **không** nằm trong transaction.
- [ ] Spring `@Transactional` có đúng `MongoTransactionManager` và proxy boundary.
- [ ] Có timeout/retry budget; transactions không kéo dài theo thời gian user mở form.
- [ ] Business failures làm abort đúng, không bị catch rồi commit nửa chừng.
- [ ] Tests dùng replica set/sharded cluster hỗ trợ transactions, không chỉ standalone mock.

## 28. Change streams, oplog và consumers

Nếu dùng Change Streams/CDC:

- [ ] Có resume token persistence qua restart.
- [ ] Consumer xử lý at-least-once delivery/idempotency phù hợp.
- [ ] Có alert lag và ước lượng oplog window.
- [ ] Có policy khi resume token hết lịch sử oplog: rebootstrap/snapshot/reconcile.
- [ ] Có chủ đích với fullDocument lookups, pre/post images và retention.
- [ ] Không đưa sensitive document vào unprotected stream logs.
- [ ] Có test replica set failover và consumer restart.
- [ ] Không tự xóa/cắt oplog để tiết kiệm disk khi chưa đánh giá CDC và replication.

**Đừng chỉ kiểm tra consumer đang “Connected”.** Nó có thể kết nối nhưng không theo kịp event rate hoặc đã bỏ lỡ lịch sử cần thiết.

## 29. Authentication và database RBAC

Checklist:

- [ ] Production không mở unauthorized database access.
- [ ] Mỗi ứng dụng/service có identity riêng khi có thể.
- [ ] Service chỉ có quyền cần: read/write trên đúng database/collection, không root.
- [ ] Bootstrap/migration user tách khỏi runtime user.
- [ ] Reader không thể insert/update/drop; writer không tự quản trị users/roles.
- [ ] Có quy trình tạo/thu hồi/rotate credentials.
- [ ] Test correct/wrong password và authSource với MongoDB auth-enabled môi trường riêng.
- [ ] Không nhầm database RBAC với HTTP user/tenant authorization.
- [ ] Role changes được review và audit.

Khi role scoped theo collection, kiểm tra **custom privilege definitions thật**, vì built-in `readWrite` ở database scope thường rộng hơn một collection.

### Bằng chứng

Một negative test chỉ pass khi operation bị từ chối **do Unauthorized**, không phải vì TLS/network hỏng. Cần có positive connection precondition và assert no unauthorized data mutation.

## 30. Network isolation và TLS

Checklist:

- [ ] MongoDB chỉ reachable từ những mạng/services được phê duyệt.
- [ ] Firewall/Atlas IP Access List/Private Endpoint/VPC peering được review.
- [ ] Không mở `0.0.0.0/0` theo thói quen để khắc phục lỗi kết nối.
- [ ] TLS được yêu cầu và certificate chain/hostname được xác minh.
- [ ] Không dùng `tlsInsecure=true` hoặc tắt hostname verification trong production.
- [ ] Certificate rotation có ownership và cảnh báo trước hạn.
- [ ] Backup/monitoring/admin clients cũng dùng đường kết nối an toàn.
- [ ] Khi dùng Private Endpoint, DNS và route thực tế được kiểm chứng, không chỉ endpoint đã được tạo.
- [ ] Có phân biệt lỗi DNS/TLS/AuthN/RBAC trong runbook.

Một MongoDB URI có `tls=true` nhưng ứng dụng vẫn bỏ xác minh certificate không đáp ứng cùng mức bảo vệ như TLS có trust chain/hostname đúng.

## 31. Multi-tenant và object-level authorization

Một service account MongoDB có thể có quyền tìm mọi document trong `orders`, nhưng API phải hạn chế theo principal:

```javascript
db.orders.findOne({
  _id: "ORD-001",
  tenantId: "tenant-a"
});
```

Checklist:

- [ ] Tenant/owner scope lấy từ authenticated principal hoặc quyền ủy nhiệm được xác minh.
- [ ] Không tin tenantId do client tùy ý gửi.
- [ ] GET by ID, list, search, aggregation, export, attachment đều có scope.
- [ ] PATCH/DELETE có điều kiện tenant/owner **ngay trong write predicate** khi phù hợp.
- [ ] Có negative tests cho tài nguyên của tenant khác.
- [ ] Cache keys và query results không leak cross-tenant.
- [ ] Business admins chỉ có cross-tenant permissions theo policy rõ.
- [ ] Unauthorized resource existence không bị lộ qua error/status quá chi tiết.

**Projection không thay authorization**; ngay cả một field duy nhất từ document của tenant khác cũng có thể là rò rỉ.

## 32. Injection và kiểm soát đầu vào

Checklist:

- [ ] API validate types/schemas, không nhận raw MongoDB query object từ client trừ endpoint quản trị đã được kiểm soát kỹ.
- [ ] Java code dùng typed filters/criteria, không ghép JSON tùy ý thành operators.
- [ ] Không để request JSON chứa `$ne`/`$where` được diễn giải như query operator khi field đáng lẽ là String.
- [ ] Sort/filter fields từ client có allowlist.
- [ ] Có limit page size, regex complexity, batch size và timeout.
- [ ] Có validation BSON types và value ranges.
- [ ] Import/ETL không bypass tenant/business validations một cách vô ý.

Ví dụ Java Sync Driver:

```java
collection.find(
    Filters.and(
        Filters.eq("tenantId", principalTenantId),
        Filters.eq("email", requestEmailString)
    )
);
```

`requestEmailString` phải được validate là String; các placeholders là dữ liệu ứng dụng được thiết lập ở code khác. Không xây filter trực tiếp từ một untrusted `Map<String,Object>` chứa MongoDB operators.

## 33. Secrets, encryption và PII

Checklist:

- [ ] MongoDB URI/password không nằm trong Git, test report hoặc error response.
- [ ] Secrets được lưu trong secret manager và có rotation/revocation plan.
- [ ] Private keys/TLS certificates có quyền file/KMS đúng.
- [ ] TLS in transit có kiểm chứng.
- [ ] Encryption at rest được xác minh qua cấu hình storage/platform, bao gồm backups.
- [ ] Với fields cần bảo vệ thêm, CSFLE/Queryable Encryption hoặc giải pháp tương đương được đánh giá theo feature support.
- [ ] Authorized read vẫn thấy plaintext không có nghĩa at-rest encryption sai.
- [ ] PII trong logs, query profiler, traces, exports và audit events được mask/minimize.
- [ ] Public API trả DTO allowlist thay vì serialize toàn bộ persistence entity.
- [ ] Có data classification và retention policy.

Phân biệt: **base64 là encoding, hash không phải encryption đảo ngược được, TLS không bảo vệ dữ liệu đã lưu trên disk, encryption at rest không tự giới hạn người có DB read role**.

## 34. Audit và quyền truy cập dữ liệu

Checklist:

- [ ] Sensitive reads/exports/role changes/deletes có audit trail phù hợp chính sách.
- [ ] Application audit ghi HTTP actor/tenant/correlation ID khi cần.
- [ ] MongoDB/Atlas audit feature chỉ được đánh dấu PASS nếu thực sự bật và tier hỗ trợ.
- [ ] Audit logs có access control và retention riêng.
- [ ] Không ghi plaintext secrets/PII toàn phần nếu không cần.
- [ ] Có cảnh báo cho privilege elevation và truy cập bất thường.
- [ ] Có phương án điều tra mà không phải bật full request logging khi incident.

Vì nhiều HTTP users cùng dùng một MongoDB service account, database audit có thể chỉ biết identity của service. Application audit bổ sung actor/ngữ cảnh nghiệp vụ; hai tầng không thay thế nhau.

## 35. Backup inventory: có gì, ở đâu và do ai sở hữu?

Checklist:

- [ ] Biết công nghệ backup: managed snapshot, filesystem snapshot, `mongodump` hoặc giải pháp phù hợp.
- [ ] Có lịch chạy, retention, encryption và storage isolation.
- [ ] Có owner vận hành và người được quyền restore.
- [ ] Backup lưu ở failure domain/region phù hợp RPO/RTO.
- [ ] Có monitoring backup job fail/missed/slow.
- [ ] Có danh mục những databases/collections cần backup và các ngoại lệ.
- [ ] Có kế hoạch khi backup size tăng nhanh hơn dự kiến.
- [ ] Không ghi dump archive lên chính `dbPath` đang thiếu dung lượng.
- [ ] Có inventory về key/KMS cần để giải mã backup khi restore.

**“Backup mỗi đêm” chưa đủ**: phải biết kết quả gần nhất **thực sự thành công, nhất quán, còn đọc được và đã được test restore**.

## 36. Tính nhất quán của backup

Các phương pháp backup có semantics khác nhau. Một bản copy file database đang được ghi có thể **không nhất quán** với journal/checkpoint. Trên replica set/sharded cluster, backup multi-node/point-in-time phải được đánh giá theo khả năng tạo consistent recovery point.

Checklist:

- [ ] Phương thức backup được MongoDB/platform hỗ trợ cho topology.
- [ ] Không dùng `cp -r dbPath` của live mongod như phương án consistent backup mặc định.
- [ ] Snapshot có cơ chế phối hợp/consistency theo vendor.
- [ ] Có oplog/PITR nếu RPO yêu cầu phục hồi tới thời điểm nhỏ hơn interval full backups.
- [ ] Backup encryption keys và metadata được giữ cùng lifecycle phù hợp.
- [ ] Có kiểm tra integrity, khả năng tải xuống và restore.
- [ ] Có bằng chứng bản backup thật chứa những collections critical.

Một `mongodump` có thể phục vụ môi trường phù hợp, nhưng không mặc định cung cấp PITR hoặc consistent snapshot của **mọi shard** trong mọi điều kiện. Cần xem tài liệu tương ứng với deployment/version.

## 37. RPO và RTO: tính theo thao tác khôi phục

Ví dụ:

```text
Critical ordering API:
  RPO = vài giây theo business approval
  RTO = 30 phút

Daily-only backup:
  Last backup = đêm qua
  Potential restore point = cách hiện tại nhiều giờ
```

Nếu RPO yêu cầu vài giây nhưng chỉ có backup hằng đêm, **không thể coi PASS** mà không có bổ sung replication/PITR/DR strategy phù hợp.

Checklist:

- [ ] RPO/RTO có owner nghiệp vụ phê duyệt.
- [ ] Backup interval + PITR window đáp ứng RPO.
- [ ] Thời gian provision hạ tầng, tải data và replay oplog được tính vào RTO.
- [ ] Có test restore data volume ở kích thước đủ đại diện.
- [ ] Có kế hoạch cutover ứng dụng và kiểm tra consistency sau restore.
- [ ] Có tiêu chí chọn restore point khi corruption/ransomware/bug migration.
- [ ] Có cách ngăn upstream tiếp tục ghi sai trong khi đang restore.

**Replication không tự thay backup:** xóa nhầm hoặc update sai có thể được replicate tới các secondaries. Backup/PITR giúp khôi phục về trạng thái trước sự kiện trong giới hạn retention.

## 38. Restore drill là bằng chứng cuối cùng

Một buổi diễn tập nên gồm:

1. Chọn backup thực tế đã được tạo bởi pipeline production-like.
2. Provision môi trường restore **cô lập**, có đủ capacity/network/RBAC.
3. Giải mã/tải backup bằng identity được cấp quyền.
4. Restore bằng thủ tục đúng với backup type.
5. Xác minh databases/collections, indexes, users/roles và config nào được/không được restore theo thiết kế.
6. Chạy kiểm thử nghiệp vụ đọc/ghi trên restored environment khi thích hợp.
7. Đối chiếu record counts, checksums/sample invariants và logs.
8. Đo **thời gian hoàn tất thực tế** so với RTO.
9. Ghi lại RPO của recovery point có thể đạt.
10. Cleanup dữ liệu nhạy cảm và quyền tạm theo policy.

Checklist:

- [ ] Có ngày diễn tập gần nhất và kết quả chi tiết.
- [ ] Có bằng chứng restore không chỉ “backup success”.
- [ ] Có thử lỗi thiếu/rotate KMS key và permissions theo kế hoạch.
- [ ] Có runbook restore không cần thông tin chỉ một cá nhân biết.
- [ ] Có người phê duyệt trước khi restore lên production.
- [ ] Có quy trình đối soát transaction kết quả không rõ sau cutover.

Nếu môi trường restore chứa dữ liệu production, phải bảo vệ nó **theo cùng phân loại nhạy cảm**, không đưa cho developer quyền rộng chỉ vì tên môi trường là staging.

## 39. Sao lưu theo vùng và disaster recovery

Checklist:

- [ ] Có xác định failure domain: host, AZ, region, tài khoản cloud, KMS, operator.
- [ ] Backup không phụ thuộc hoàn toàn vào cùng vùng/tài khoản có thể mất quyền truy cập.
- [ ] Multi-region DR có đánh giá data residency và chi phí.
- [ ] Có plan DNS/connection string/network cutover.
- [ ] Có plan failback sau khi site gốc phục hồi.
- [ ] Có kiểm thử restore/failover theo vùng ở môi trường được phép.
- [ ] Có policy tránh split-brain hoặc hai writer sets không phối hợp.
- [ ] Không quảng bá RTO/RPO vùng nếu chưa đo thời gian failover/restore.

Một bản backup ở vùng khác nhưng application secrets/KMS keys chỉ tồn tại ở vùng đã hỏng có thể vẫn **không khôi phục được** trong RTO.

## 40. Monitoring: bốn nhóm chỉ số

Một dashboard đủ dùng nên phân tách:

| Nhóm | Chỉ số | Vấn đề giúp nhận diện |
| --- | --- | --- |
| **User/SLO** | p95/p99 API latency, error rate, successful writes | Trải nghiệm thực |
| **MongoDB** | query latency, ops, active connections, lock/cache, replication lag | Database bottleneck |
| **Hạ tầng** | CPU, memory/cgroup OOM, disk bytes/inodes, IOPS/latency | Tài nguyên |
| **Khôi phục** | backup freshness, restore drills, oplog window, alerts | Recovery readiness |

Checklist:

- [ ] Có baseline bình thường và peak hours.
- [ ] Dashboard cho những endpoints critical, không chỉ CPU/disk trung bình.
- [ ] Metrics/alerts gắn với owner và on-call route.
- [ ] Có correlation ID nối app failures với DB/network events.
- [ ] Có thời gian lưu metrics đủ nhìn xu hướng tăng trưởng.
- [ ] Không expose credentials/PII trong metric labels.
- [ ] Có alert khi backup thất bại hoặc không còn bản hợp lệ.

## 41. Storage capacity và I/O performance

Checklist:

- [ ] Biết `dbPath`/mount/PVC/Atlas tier thực và filesystem còn bytes.
- [ ] Theo dõi **inodes, quotas, read-only remount** nếu môi trường áp dụng.
- [ ] Có dự báo **time-to-full** dựa trên tốc độ tăng, không chỉ 90% threshold.
- [ ] Có IOPS/throughput/latency headroom cho peak, backup và initial sync.
- [ ] Biết storage autoscale giới hạn, điều kiện kích hoạt và độ trễ.
- [ ] Backup/archive/logs không vô tình cạnh tranh data volume.
- [ ] Index growth và oplog/CDC retention được dự toán.
- [ ] Có runbook resize volume/PVC an toàn.

Ước lượng đơn giản:

```text
Time-to-full ≈ available GiB / net growth GiB per hour
```

Chỉ dùng nếu growth rate dương và tương đối ổn định. Index build, import, TTL backlog và storage autoscaling có thể làm xu hướng thay đổi đột ngột.

**Không xóa WiredTiger data files, journal hoặc oplog để giảm dung lượng.** Xóa logical documents cũng không luôn trả OS bytes ngay vì storage reuse.

## 42. Memory, WiredTiger và query pressure

Checklist:

- [ ] Phân biệt host RAM với container cgroup limit.
- [ ] Theo dõi process RSS, OS MemAvailable, swap/OOM events.
- [ ] WiredTiger cache size phù hợp phiên bản và memory limit thực.
- [ ] Có metrics eviction/dirty pages/read pressure.
- [ ] Query sorts/groups/aggregations không có unbounded memory usage.
- [ ] Java client không load hàng triệu documents vào List không giới hạn.
- [ ] Connection pool và cursor lifecycle được quản lý.
- [ ] Không tăng WiredTiger cache khi nguyên nhân là cgroup OOM.
- [ ] Không bật disk spill mù quáng khi volume đã thiếu I/O hoặc capacity.

**Ghi nhớ:** WiredTiger cache không phải tổng RSS của `mongod`. Linux free RAM thấp chưa chắc là thiếu RAM nếu page cache có thể thu hồi.

## 43. Replica health và failover readiness

Checklist:

- [ ] Có đủ healthy voting members để duy trì majority.
- [ ] Replication lag được theo dõi theo từng member.
- [ ] Oplog window đủ cho lag/maintenance/CDC needs.
- [ ] Có test failover/driver reconnection trong môi trường staging.
- [ ] Có khả năng rolling restart theo topology mà không mất quorum.
- [ ] Biết kết quả write có thể rollback theo write concern contract.
- [ ] Có kế hoạch cho member đầy disk, OOM hoặc cần initial sync.
- [ ] Khi tất cả members gần đầy, failover không được xem là phương án tạo capacity.
- [ ] Ứng dụng không retry liên tục không có backoff khi election xảy ra.

Một kiểm tra `rs.status()` thành công tại một thời điểm **không thay** giám sát lag/heartbeat/election theo thời gian.

## 44. Log, slow operations và incident signals

Checklist:

- [ ] Log rotation/retention không làm đầy data volume.
- [ ] Slow query diagnostics có ngưỡng/chi phí phù hợp.
- [ ] Không log raw connection URI có password.
- [ ] Có alert E11000 rate/WriteConflict/timeouts tùy business criticality.
- [ ] Có phân biệt authentication failures, authorization failures và network/TLS failures.
- [ ] Có visibility backup jobs, index builds, migrations và TTL backlog.
- [ ] Incident evidence được giữ theo policy và đã redact dữ liệu nhạy cảm.

Mẫu log an toàn:

```json
{
  "event": "MONGO_OPERATION_FAILURE",
  "operation": "update_inventory",
  "errorCategory": "TRANSIENT_TRANSACTION",
  "correlationId": "req-demo-001",
  "collection": "inventory",
  "durationMs": 250,
  "sensitivePayload": "REDACTED"
}
```

Đây là schema minh họa; không cần in document đầy đủ để biết incident đang xảy ra.

## 45. Maintenance, index builds và upgrade

Checklist:

- [ ] Có chính sách phiên bản MongoDB/driver/Spring Data được hỗ trợ.
- [ ] Có môi trường staging tương ứng cho upgrade.
- [ ] Có backup và rollback/failback plan trước schema/config changes.
- [ ] Đã đánh giá wire protocol/feature compatibility và driver APIs.
- [ ] Không đổi feature compatibility version mà chưa hiểu rollback restrictions.
- [ ] Rolling upgrade tuân theo hướng dẫn replica set/sharded cluster của version.
- [ ] Schema/index migrations có load budget và review.
- [ ] Có đo performance sau upgrade, không chỉ health ping.
- [ ] Có test transaction/change stream/encryption behavior nếu đang dùng.
- [ ] Có change window, owner, communications và abort criteria.

Nếu cần xây index unique mới, trước đó phải kiểm tra dữ liệu legacy **đã không có duplicates**; index build không tự chọn record nào để xóa.

## 46. Java/Spring Data: checklist tích hợp

- [ ] MongoDB driver và Spring Data dependency versions được quản lý nhất quán.
- [ ] Java entity mapping `@Id`, `@Version`, `@Field`, codecs cho UUID/Decimal128/Date đúng.
- [ ] MongoClient lifecycle dùng connection pool chung phù hợp.
- [ ] Có connection/server selection/socket timeouts theo SLO.
- [ ] Queries dùng tenant filters từ authenticated principal.
- [ ] DTOs tách khỏi persistence entities.
- [ ] Có handling `DuplicateKeyException`, optimistic locking, transient errors và unknown outcomes.
- [ ] Các writes cần transaction có session/transaction manager phù hợp.
- [ ] Có bounded retry và idempotency keys cho các thao tác quan trọng.
- [ ] Cursor/stream/aggregation results được giới hạn.
- [ ] Secrets không hard-code trong `application.yml` hoặc logs.
- [ ] Integration tests chạy MongoDB thật với topology/roles tương ứng.

Ví dụ lỗi thường gặp: `@Version` bảo vệ entity saves, nhưng API HTTP reload document mới nhất trước mỗi save mà **không kiểm tra expectedVersion do client gửi** thì có thể vẫn ghi đè một form người dùng đã mở từ trước.

## 47. Mẫu lệnh tra cứu *chỉ đọc* trong `mongosh`

Các ví dụ dùng database giả `appdb`, collection `orders`. Chọn lệnh phù hợp và role được phép; không chạy query có thể scan hàng trăm triệu documents trên production đang quá tải.

```javascript
// Server/topology:
db.adminCommand({ hello: 1 });

// Thông tin bộ chỉ số (quyền giám sát phù hợp):
const server = db.adminCommand({ serverStatus: 1 });
printjson(server.connections);
printjson(server.mem);
printjson(server.wiredTiger?.cache);

// Thống kê database:
const app = db.getSiblingDB("appdb");
printjson(app.stats());

// Indexes:
printjson(app.orders.getIndexes());

// Query plan trên tập đại diện và có giới hạn:
printjson(
  app.orders.find({
    tenantId: "tenant-demo",
    status: "PAID"
  }).sort({ createdAt: -1 })
    .limit(20)
    .explain("queryPlanner")
);
```

`queryPlanner` không thực thi cùng workload đo runtime như `executionStats`; dùng executionStats khi cần kiểm tra actual scan behavior và đã đánh giá chi phí. Không phân tích production chỉ dựa trên một snapshot.

### Kiểm tra replica set

```javascript
// Chạy trên replica set với role tương ứng:
rs.status();
```

Không áp dụng `rs.status()` trực tiếp như lệnh bắt buộc cho standalone hoặc mongos. Khi dùng Atlas, ưu tiên dashboard/metrics được cung cấp theo cluster tier và role.

## 48. Mẫu kiểm tra Java để đối soát index và query

Một ví dụ chạy ở integration test **trên database lab**:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public class QueryReviewExample {

    public static void run(MongoClient client) {
        MongoDatabase database = client.getDatabase("appdb");
        MongoCollection<Document> orders =
            database.getCollection("orders");

        Document found = orders.find(
            Filters.and(
                Filters.eq("tenantId", "tenant-demo"),
                Filters.eq("status", "PAID")
            )
        ).projection(
            new Document("_id", 1)
                .append("status", 1)
                .append("createdAt", 1)
        ).limit(1).first();

        System.out.println(
            found == null ? "No matching fixture" : "Fixture found");
    }
}
```

Điểm cần quan sát:

- Filter luôn chứa tenant scope cho dữ liệu multi-tenant.
- Projection chỉ đọc những fields cần thiết.
- Limit giúp không materialize một tập lớn.
- Không in whole document/PII vào logs.
- Integration test dùng fixture giả và xác nhận cả positive/negative results.

Đây không phải benchmark. Để đánh giá index cần thêm explain/workload/latency và trạng thái index thật.

## 49. Runbook ứng phó sự cố: trình tự ít phá hủy

```text
Phát hiện alert/SLO breach
          |
          v
Xác nhận phạm vi + topology + business impact
          |
          v
Giữ bằng chứng cần thiết, bảo vệ data/quorum
          |
          v
Giảm nguồn tải/retry không thiết yếu
          |
          v
Phân loại network/AuthN/RBAC/query/resource/storage
          |
          v
Chọn khôi phục ít phá hủy: capacity / failover
theo runbook / rollback thay đổi lỗi
          |
          v
Đối soát dữ liệu + transaction outcomes + API SLO
          |
          v
Incident closure + postmortem + preventive actions
```

Checklist:

- [ ] Có incident commander/on-call/escalation contacts.
- [ ] Có runbook riêng cho primary mất khả dụng, replica lag, disk-full, OOM, backup failure.
- [ ] Các lệnh thao tác nguy hiểm cần preconditions và approval.
- [ ] Không xóa `journal/`, `WiredTiger*`, oplog hoặc PVC để “chữa nhanh” disk full.
- [ ] Không restart đồng loạt replica set members.
- [ ] Không gọi `rs.reconfig(..., {force:true})` theo phản xạ.
- [ ] Có phân biệt lỗi do quyền, network và data corruption.
- [ ] Sau khôi phục, xác minh writes đã ACK, unknown outcomes và side effects.

## 50. Bảng tra cứu triệu chứng → hướng rà soát

| Triệu chứng | Kiểm tra đầu tiên | Tránh nhầm lẫn |
| --- | --- | --- |
| E11000 duplicate key | Index name/keyValue/filter/upsert | Không phải mọi duplicate là idempotent |
| Query p99 tăng | Query plan, index, data cardinality, disk I/O | Không chỉ tăng connection pool |
| Memory/OOM | RSS/cgroup/WiredTiger/query spill/JVM heap | Không chỉ tăng cache |
| ENOSPC | `dbPath` mount, bytes, inodes, quota, I/O | Không xóa WiredTiger files |
| Secondary lag | Write rate, oplog window, disk/network | Không cắt oplog mù quáng |
| No primary | Majority/health/elections/network | Không force reconfig tùy tiện |
| Authentication failed | TLS/network, credentials, authSource | Không cấp root để thử |
| Unauthorized | Roles/privileges/collection scope | Không nhầm với bad password |
| Cross-tenant leak | Principal, filter, cache/export/lookup | Projection không đủ |
| Timeout sau write | Driver labels, commit status, idempotency key | Không mặc định chưa ghi |
| Backup succeeded nhưng restore fail | Archive integrity, KMS, procedure | Có backup ≠ khôi phục được |
| Change stream cannot resume | Token persistence, oplog window | Không tự tạo event đã mất |
| TTL data chưa biến mất | TTL monitor/index, date types | TTL không tức thời |
| Collection lớn sau delete | WiredTiger storage reuse/indexes | `deleteMany` không buộc `df` giảm |
| Index build thất bại | Existing duplicates, RAM/disk/index constraints | Không xóa data tùy tiện |

## 51. Bộ kiểm tra tối thiểu trước khi phát hành

### Mô hình

- [ ] Business entities và aggregate boundaries rõ.
- [ ] Types/IDs/unique keys ổn định và có schema validation.
- [ ] Không có unbounded array/document growth.
- [ ] Retention/TTL/archive plan rõ.
- [ ] Migration và backward compatibility đã có plan.

### Truy vấn

- [ ] Top queries có index candidates và explain/metrics.
- [ ] Sort/pagination/aggregation được giới hạn.
- [ ] Các queries hot không gây COLLSCAN ngoài ý muốn.
- [ ] Có performance test trên data volume đại diện.
- [ ] Transaction/idempotency/concurrency invariants đã được test.

### Bảo mật

- [ ] Authentication/RBAC/TLS/network controls đúng phạm vi.
- [ ] Cross-tenant/owner negative tests pass.
- [ ] Secrets/PII không lộ qua API/log/exports.
- [ ] Audit và key rotation có owner.

### Sao lưu

- [ ] Backup gần nhất hợp lệ và có alert khi fail.
- [ ] RPO/RTO đáp ứng yêu cầu.
- [ ] Restore drill có bằng chứng và chưa quá hạn review.
- [ ] Backup encryption/ACL/retention phù hợp.

### Vận hành

- [ ] Capacity headroom/time-to-full và load budget rõ.
- [ ] Replica/quorum/lag/CDC được theo dõi.
- [ ] Có on-call, runbooks, rollback và escalation.
- [ ] Server/driver compatibility và kế hoạch upgrade ổn.
- [ ] Các critical SLO/alerts được kiểm tra.

Không có mục nào tự cho phép “release” khi Critical FAIL chưa được xử lý hoặc chấp nhận rủi ro theo thẩm quyền. Một mục UNKNOWN quan trọng như “restore chưa từng thử” phải được coi là **lỗ hổng bằng chứng**, không phải PASS.

## 52. Mẫu biên bản rà soát để tái sử dụng

```markdown
# MongoDB Architecture & Operations Review

## Context
- Application:
- Environment:
- Cluster / MongoDB version:
- Driver / Spring Data version:
- Database(s):
- Business owner:
- Engineering owner:
- On-call / DBA:
- Review date:

## Requirements
- Critical operations / SLO:
- RPO / RTO:
- Data classification:
- Retention / residency:
- Peak workload / forecast:

## Findings
| ID | Pillar | Status | Risk | Evidence | Owner | Due |
|----|--------|--------|------|----------|-------|-----|
| M-01 | Model | UNKNOWN | High |  |  |  |
| Q-01 | Query | UNKNOWN | Medium |  |  |  |
| S-01 | Security | UNKNOWN | Critical |  |  |  |
| B-01 | Backup | UNKNOWN | Critical |  |  |  |
| O-01 | Operations | UNKNOWN | High |  |  |  |

## Decisions
- Must-fix before release:
- Accepted risks (with approver):
- Mitigations / feature flags:
- Rollback plan:
- Restore readiness:
- Follow-up date:
```

Đây là mẫu cho review; không mặc định các dòng UNKNOWN là tình trạng của một hệ thống cụ thể. Lưu evidence ở nơi có quyền truy cập phù hợp, nhất là query samples, diagrams, backups và thông tin cấu hình bảo mật.

## 53. Ví dụ rà soát một ứng dụng bán hàng

**Bối cảnh giả định:** một API Java/Spring Boot dùng MongoDB replica set, có collections `customers`, `orders`, `inventory` và `payment_requests`.

### Mô hình

Phát hiện:

```text
orders.items được embed: hợp lý
customers.purchaseHistory[] tăng không giới hạn: FAIL
payment_requests requestId có unique index: PASS
amount đang lưu Double: REVIEW/HIGH nếu money
```

Hành động: chuyển purchase history sang collection truy vấn theo user/time; dùng Decimal128 và migration có kiểm soát cho money.

### Truy vấn

Phát hiện:

```text
GET orders/{id} đã check tenant: PASS
GET /orders?status=... sort createdAt: thiếu index: FAIL
Daily revenue aggregation quét toàn lịch sử: cần đánh giá rollup
```

Hành động: đo explain/latency trên workload thật, thiết kế compound index và giới hạn reporting budget.

### Bảo mật

Phát hiện:

```text
Service account đang dùng quyền quản trị: CRITICAL
API trả internalNotes trong customer JSON: HIGH
TLS được bật với hostname verification: PASS
```

Hành động: tách migration/runtime credentials, tạo role tối thiểu, DTO allowlist và negative integration tests.

### Sao lưu

Phát hiện:

```text
Daily backup job success: PASS về lịch chạy
Restore drill chưa có: UNKNOWN/HIGH hoặc CRITICAL theo RPO/RTO
Backup nằm cùng cloud account/region: REVIEW
```

Hành động: diễn tập restore, đo RTO và rà soát failure domain/secret/KMS dependencies.

### Vận hành

Phát hiện:

```text
Disk 82%, growth 8 GiB/ngày: cần time-to-full forecast
Replica lag alert chưa đặt: FAIL
App retry timeout không giới hạn: HIGH
```

Hành động: alert theo capacity và lag, backoff/jitter/idempotency, diễn tập failover. Ví dụ giúp minh họa cách **một finding phải có hành động**, không phải đánh giá hệ thống thật.

## 54. Các câu hỏi phỏng vấn kỹ thuật/ôn tập

### Câu 1. Một collection có 3 triệu documents nhưng không có index cho query chính. Chỉ thêm RAM có đủ không?

**Đáp án:** Chưa chắc. Phải xem query plan, selectivity, sort, working set và storage I/O; index phù hợp có thể giảm scanned docs nhiều hơn chỉ tăng RAM.

### Câu 2. Hai requests cùng đọc tồn kho 2 rồi lưu available=1. Vì sao MongoDB single-document atomicity chưa đủ?

**Đáp án:** Mỗi write atomic, nhưng read–modify–write dùng giá trị cũ có thể lost update. Dùng conditional `$inc` hoặc CAS/version.

### Câu 3. Vì sao unique index không thay idempotency?

**Đáp án:** Index ngăn duplicate keys; ứng dụng vẫn cần phân biệt same key/same payload với different payload và ngăn external side effects lặp.

### Câu 4. Collection `orders` có unique `{tenantId,requestId}`. Hai tenants dùng cùng requestId có bị trùng không?

**Đáp án:** Không, nếu tenantId khác và không vi phạm index khác; uniqueness áp cho cặp.

### Câu 5. GET tenant A chỉ trả field status của order B. Có còn là vi phạm không?

**Đáp án:** Có. Projection không thay authorization theo document/tenant.

### Câu 6. API tìm theo `{email:null}` trả cả documents thiếu email. Vì sao?

**Đáp án:** MongoDB query equality null match explicit null và missing field theo semantics này; dùng `$type`/`$exists` khi cần phân biệt.

### Câu 7. Vì sao `@Version` không tự bảo vệ form HTTP bị stale?

**Đáp án:** Nếu backend reload version mới nhất rồi save mà không so expectedVersion từ client, nó có thể ghi đè dữ liệu dựa trên form cũ. Cần expectedVersion/ETag và CAS khi ghi.

### Câu 8. Đã có replica set ba nodes, còn cần backup không?

**Đáp án:** Có. Xóa/cập nhật sai có thể replicate. Backup/PITR phục vụ recovery khỏi logical errors và sự cố mất dữ liệu khác.

### Câu 9. Backup báo Success liên tục. Vì sao vẫn phải restore drill?

**Đáp án:** Backup có thể thiếu data, sai encryption keys, hỏng archive, thiếu quyền hoặc restore quá lâu so với RTO. Restore drill tạo bằng chứng thực.

### Câu 10. Disk báo 95%, làm gì trước khi xóa documents?

**Đáp án:** Đánh giá tốc độ tăng, `dbPath`/mount, bytes/inodes/IOPS, workload, topology/quorum và mở rộng capacity/giảm ingest. Không xóa files WiredTiger/journal/oplog.

### Câu 11. Vì sao `allowDiskUse` không luôn là giải pháp cho aggregation bị thiếu RAM?

**Đáp án:** Có thể chuyển áp lực sang temporary disk/IOPS; nếu disk đang nghẽn hoặc gần đầy, tình hình có thể xấu hơn.

### Câu 12. Một `COLLSCAN` trong explain có tự chứng minh lỗi không?

**Đáp án:** Không. Phụ thuộc collection size, query intent, selectivity và execution cost. Cần nhìn scanned/returned và workload thực.

### Câu 13. Service chỉ cần đọc orders nhưng dùng `readWriteAnyDatabase`. Nhóm nào phải FAIL?

**Đáp án:** Bảo mật least privilege/RBAC. Service được cấp quyền quá rộng.

### Câu 14. Timeout sau commit transaction nghĩa chắc chắn transaction abort?

**Đáp án:** Không. Có thể unknown commit result; phải retry commit/reconcile theo driver semantics và idempotency key.

### Câu 15. Vì sao dùng `skip(100000)` có thể chậm hơn keyset pagination?

**Đáp án:** Deep skip có thể yêu cầu engine đi qua nhiều entries trước khi trả trang. Keyset lọc từ sort key/tiebreaker có thể tránh công việc bỏ qua lớn nếu index phù hợp.

### Câu 16. Trong sharded collection, tạo unique index theo field tùy ý có luôn bảo đảm global uniqueness?

**Đáp án:** Không. Unique index có restrictions liên quan shard key và MongoDB version; phải kiểm tra trước.

### Câu 17. Dữ liệu Time Series đã có TTL, backup sẽ tự xóa ngay dữ liệu quá hạn?

**Đáp án:** Không. TTL hoạt động bất đồng bộ trên collection theo policy; backup/snapshot có retention riêng.

### Câu 18. Chỉ một Java service được phép ghi collection, nhưng có job ETL dùng raw driver. Tại sao cần đưa ETL vào review?

**Đáp án:** ETL là một writer thực, có thể bypass validation/version/idempotency và làm hỏng invariants.

### Câu 19. Query projection loại passwordHash nhưng response vẫn lộ internalRiskScore. Sai ở đâu?

**Đáp án:** Blacklist projection bỏ sót field nhạy cảm; cần DTO allowlist và regression tests.

### Câu 20. Worker change stream có resume token lưu trong RAM. Sau crash cần gì?

**Đáp án:** Durable token storage và xử lý khi oplog history không còn; consumers còn cần idempotency/rebootstrap.

### Câu 21. Một secondary lag hơn oplog window. Có thể tiếp tục resume bình thường không?

**Đáp án:** Không bảo đảm; có thể phải initial sync hoặc rebootstrap theo topology và consumer needs.

### Câu 22. MongoDB document 20 MiB có hợp lệ không?

**Đáp án:** Document BSON thông thường vượt giới hạn 16 MiB; cần thiết kế lại embedding/bucketing/reference/GridFS nếu phù hợp dữ liệu tệp.

### Câu 23. `MongoClients.create(uri)` chạy không lỗi đã chứng minh credentials đúng chưa?

**Đáp án:** Chưa. Driver có thể kết nối/authenticate khi command đầu tiên chạy; test phải thực thi operation thật.

### Câu 24. Vì sao test security “insert bị lỗi bất kỳ” chưa đủ chứng minh RBAC đúng?

**Đáp án:** Có thể lỗi duplicate key, network hoặc TLS. Cần assert Unauthorized và xác minh không thay đổi dữ liệu.

### Câu 25. Restore RTO mục tiêu 30 phút, nhưng restore drill mất 4 giờ. Trạng thái?

**Đáp án:** FAIL so với RTO; cần cải thiện backup/DR/capacity và/hoặc thay đổi yêu cầu có phê duyệt, không ghi PASS.

### Câu 26. Khi disk đầy vì journal/WiredTiger, có nên `rm` những file lớn trong `dbPath`?

**Đáp án:** Không. Chúng là state nội bộ cần cho storage engine/recovery; ưu tiên tăng capacity và hành động được hỗ trợ.

### Câu 27. Hai users cùng sửa hai fields khác nhau, `@Version` báo conflict. Có phải MongoDB hỏng?

**Đáp án:** Không. Version cấp document bảo thủ để tránh lost update; merge field-level phải có policy riêng.

### Câu 28. Đã bật TLS, có thể để URI/password trong logs không?

**Đáp án:** Không. TLS bảo vệ dữ liệu trên đường truyền, không ngăn rò rỉ tại application logs.

### Câu 29. Dataset được restore sang staging nhưng chứa PII production. Có được giảm RBAC vì là staging không?

**Đáp án:** Không. Restored sensitive data cần mức bảo vệ tương ứng, masking, access control và retention.

### Câu 30. Khi đánh giá trước release, mục Backup Restore Drill là UNKNOWN. Có thể tự ghi PASS vì backup schedule thành công?

**Đáp án:** Không. Schedule success không phải bằng chứng restore được; cần drill hoặc formal risk decision.

## 55. Bảng đánh giá ưu tiên sau rà soát

Không phải mọi finding được sửa cùng lúc. Một cách sắp xếp:

| Ưu tiên | Ví dụ | Quyết định thường gặp |
| --- | --- | --- |
| **P0 / Block** | Cross-tenant data leak, plaintext credential lộ, không có recoverable backup cho dữ liệu critical | Ngăn release/incident response theo policy |
| **P1 / Trước release hoặc có mitigation** | Không có unique idempotency key cho payment, transaction mất atomicity, no quorum headroom | Sửa trước hoặc risk acceptance chính thức |
| **P2 / Sprint gần** | Query p99 vượt SLO, index missing trên endpoint quan trọng | Lập action có deadline và benchmark |
| **P3 / Cải tiến định kỳ** | Index dư ít ảnh hưởng, thiếu tài liệu không gây blocking | Giao owner, kỳ review kế tiếp |

Mẫu phân công:

```text
Finding ID: Q-07
Mô tả: /orders list query quét nhiều docs trên tenant lớn
Evidence: explain + p99 dashboard
Risk: High
Owner: Orders backend team
Mitigation: giới hạn page size + rate limit
Fix: compound index & pagination keyset
Acceptance: p99 đạt SLO ở peak fixture
Deadline:
Rollback: feature flag/restore previous index policy
```

Các số liệu/điều kiện acceptance phải lấy từ SLO thật. Không dùng một con số p99 mang tính mẫu làm chuẩn cho mọi hệ thống.

## 56. Checklist cuối cùng theo năm trụ cột

### A. Mô hình dữ liệu

- [ ] Các aggregate/document boundaries phù hợp use cases.
- [ ] Embed/reference theo cardinality và lifecycle.
- [ ] Không có document/array tăng vô hạn.
- [ ] BSON types, IDs, money và timestamps chuẩn hóa.
- [ ] Missing/null/optional fields có contract.
- [ ] Unique constraints và schema validation đang hoạt động.
- [ ] Schema migration/retention/archive có kế hoạch.
- [ ] Shard key/time series phù hợp workload nếu áp dụng.

### B. Truy vấn

- [ ] Top query shapes được đo trên dữ liệu đại diện.
- [ ] Compound/unique/partial/multikey/collation indexes đúng.
- [ ] `explain` và scanned/returned ratio được hiểu.
- [ ] Sort/pagination/aggregation có giới hạn và phù hợp index.
- [ ] Application không materialize unbounded results.
- [ ] Write concurrency/invariants có atomic updates, CAS, transaction, idempotency phù hợp.

### C. Bảo mật

- [ ] Authentication được bật và negative tests xác nhận.
- [ ] Database RBAC least privilege.
- [ ] Network/TLS/private connectivity đúng.
- [ ] Tenant/owner authorization ở mọi path.
- [ ] Secrets, encryption, PII, logs/exports và audit được quản lý.
- [ ] Credential/key rotation có owner.

### D. Sao lưu

- [ ] Backup hợp lệ, encrypted, retention/ACL đúng.
- [ ] RPO/RTO có định nghĩa rõ.
- [ ] Có PITR nếu yêu cầu nghiệp vụ cần.
- [ ] Đã restore drill và đo thời gian.
- [ ] Có DR/failure-domain plan và kiểm soát sensitive restore data.
- [ ] Có alert cho backup failure và recovery readiness.

### E. Vận hành

- [ ] SLO/error budget/metrics/alerts có owner.
- [ ] Capacity bytes/inodes/IOPS/RAM có headroom và time-to-full.
- [ ] Replica health/quorum/lag/oplog được monitor.
- [ ] Có on-call, runbook, incident decision/rollback.
- [ ] Maintenance/upgrade/index builds có change process.
- [ ] Java pools/retries/transactions/CDC có observability.
- [ ] Có postmortem/reconciliation procedure khi dữ liệu sai hoặc ghi không rõ kết quả.

## 57. Kết luận

Một MongoDB deployment đáng tin cậy cần **đúng dữ liệu, đúng truy vấn, đúng quyền, có thể khôi phục và có thể vận hành**. Năm trụ cột liên kết chặt: mô hình sai làm index khó tối ưu; query kém tạo cache/disk pressure; quyền quá rộng khiến data dễ bị lộ; backup không thử restore không đủ bảo vệ; monitoring/runbook thiếu làm thời gian gián đoạn kéo dài.

Điểm then chốt của checklist không phải số lượng ô đánh dấu, mà là **bằng chứng và hành động**. Đối với từng nguy cơ, hãy ghi owner, mức tác động, test hoặc metric chứng minh, deadline và tiêu chí xác nhận đã xử lý. Những finding chưa có bằng chứng phải giữ trạng thái UNKNOWN; những rủi ro nghiêm trọng phải được giải quyết hoặc chấp nhận theo đúng thẩm quyền trước khi release.

Khi áp dụng lặp lại ở thiết kế, trước release, trong vận hành định kỳ và sau sự cố, checklist trở thành **hợp đồng kỹ thuật giữa lập trình viên, DBA/SRE, security và business owner**. Nó giúp phát hiện lỗi sớm, giảm phát sinh duplicate/lost update, duy trì SLO và chuẩn bị khả năng phục hồi trước khi cần dùng tới.

### Tài liệu tham khảo chính thức

- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Aggregation](https://www.mongodb.com/docs/manual/aggregation/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [MongoDB Manual — Authentication and Authorization](https://www.mongodb.com/docs/manual/core/authentication/)
- [MongoDB Manual — Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/)
- [MongoDB Manual — Backup Methods](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Manual — Replica Sets](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Atlas — Monitor Cluster Metrics](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/)
- [MongoDB Atlas — Backup and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/)

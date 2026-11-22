# Phiên bản schema và tương thích giữa ứng dụng cũ với mới trong MongoDB

## Mục tiêu bài học

MongoDB hỗ trợ tài liệu linh hoạt: hai document trong cùng collection có thể mang các field, cấu trúc lồng nhau hoặc kiểu dữ liệu khác nhau. Sự linh hoạt này giúp ứng dụng phát triển nhanh, nhưng **không tự bảo đảm một phiên bản ứng dụng cũ sẽ hiểu dữ liệu do phiên bản mới ghi ra**.

Ví dụ, ứng dụng V1 lưu tên khách trong field `full_name`. Ứng dụng V2 muốn đổi thành `display_name`, thêm `schema_version` và chuyển một số trạng thái khách hàng. Trong thời gian triển khai rolling deployment, cả hai bản ứng dụng có thể còn đang phục vụ request, chạy worker hoặc xử lý sự kiện. Nếu chỉ sửa annotation Java rồi deploy, các tác hại có thể là:

- V1 đọc document mới nhưng không tìm thấy `full_name`.
- V2 đọc document cũ nhưng `display_name` là `null`.
- V1 `save` một document được V2 thêm field, vô tình xóa field mới.
- V1 và V2 cùng ghi hai tên field khác nhau làm dữ liệu mâu thuẫn.
- Query/index/validator chỉ biết một schema nên bỏ sót bản ghi.
- Một sự cố buộc rollback code, nhưng dữ liệu đã được đổi sang format mà code cũ không đọc được.

Bài thuộc **Database Engine Document MongoDB → Tiến hóa dữ liệu → Phiên bản schema và tương thích giữa ứng dụng cũ với mới**.

Sau bài học, bạn có thể:

1. Phân biệt **schema version của document**, **version của ứng dụng**, **event/API contract version**, **MongoDB Server version** và **Feature Compatibility Version (FCV)**.
2. Vẽ ma trận V1/V2 theo hai chiều đọc và ghi, xác định thời điểm mixed-version deployment an toàn.
3. Xây quy trình **expand → migrate → contract** mà không cần đổi toàn bộ collection trong một lần.
4. Thiết kế **dual-read**, **dual-write**, fallback, field aliases và rules xác định source of truth khi có writer cũ.
5. Dùng field `schema_version` khi cần, nhưng không coi nó là thay thế cho schema validation hoặc mapping.
6. Backfill theo lô nhỏ với checkpoint, điều kiện bảo vệ, chạy lại an toàn và reconciliation.
7. Tránh lost update khi ứng dụng cũ dùng full-document replacement.
8. Quản lý `missing`, `null`, numeric types, date/time, enum, embedded objects và arrays khi thay schema.
9. Dùng MongoDB `$jsonSchema` validator với mức kiểm tra phù hợp giai đoạn triển khai.
10. Lên kế hoạch tạo/xóa index, thay unique constraints và thực hiện thay đổi dữ liệu trong sharded cluster.
11. Dùng Spring Data MongoDB `@Field`, `MongoTemplate`, conditional updates và optimistic locking trong compatibility window.
12. Xác định rollback boundary, tiêu chí hoàn tất migration, giám sát và kế hoạch khôi phục.
13. Viết integration tests cho mọi cặp ứng dụng và schema còn được phép hoạt động.
14. Thiết kế runbook và diễn tập tiến hóa dữ liệu mà không mất tính đúng nghiệp vụ.

> **Nguyên tắc:** Một migration schema thành công phải giữ được **tính đúng khi cả code cũ lẫn code mới đang chạy**, không chỉ khiến code mới đọc được dữ liệu sau khi tất cả bản ghi đã chuyển xong.

---

## 1. “MongoDB schemaless” thực sự có nghĩa gì?

MongoDB không bắt buộc mọi document trong một collection phải có cùng cấu trúc mặc định. Chẳng hạn:

~~~javascript
db.customers.insertMany([
  {
    _id: "CUS-001",
    tenant_id: "tenant-a",
    full_name: "Nguyễn An",
    status: "ACTIVE"
  },
  {
    _id: "CUS-002",
    tenant_id: "tenant-a",
    display_name: "Trần Bình",
    schema_version: 2,
    status: "ACTIVE",
    preferred_language: "vi"
  }
]);
~~~

Cả hai có thể tồn tại trong `customers`. Nhưng:

~~~javascript
db.customers.find({
  display_name: "Nguyễn An"
});
~~~

không tìm thấy CUS-001 vì document đó chỉ có `full_name`.

### 1.1. “Schema linh hoạt” không đồng nghĩa “không có schema”

Ứng dụng, queries, indexes, validators, ETL pipelines, dashboards, event consumers và các service khác **đang cùng giả định một schema**. Tập hợp các giả định ấy là **hợp đồng dữ liệu (data contract)**, dù database chưa bật validator.

### 1.2. Schema ở nhiều tầng

| Tầng | Hợp đồng liên quan | Ví dụ |
|---|---|---|
| BSON document | Tên field, kiểu, cấu trúc | `display_name:string` |
| Java entity | Properties, codecs/converters | `Customer.displayName` |
| Query/index | Đường dẫn field dùng để lọc/sort | `display_name` |
| API JSON | Public response/request schema | `displayName` |
| Event schema | Payload do producer phát | `customerDisplayName` |
| Report/ETL | Cột hoặc metric từ MongoDB | `customer_name` |
| Authorization | Tenant/roles/visibility | `tenant_id` |

Sửa tên field ở MongoDB có thể ảnh hưởng tất cả tầng trên, ngay cả khi Java entity compile thành công.

---

## 2. Năm loại phiên bản dễ bị nhầm

### 2.1. Application version

Ví dụ `order-service 1.12` và `order-service 2.0`. Đây là version của binary/container đang chạy. Cùng một application version có thể đọc nhiều document schema versions.

### 2.2. Document schema version

Field do ứng dụng định nghĩa, ví dụ:

~~~javascript
{
  _id: "CUS-001",
  schema_version: 2,
  display_name: "Nguyễn An"
}
~~~

MongoDB **không tự thêm hoặc tự tăng** field này. Business migration hoặc application code chịu trách nhiệm.

### 2.3. API version

`/api/v1/customers` và `/api/v2/customers` có thể dùng DTO khác nhau, nhưng cùng đọc một MongoDB collection. API version **không nhất thiết bằng** `schema_version`.

### 2.4. Event schema version

Một event `CustomerUpdated` có thể có `event_schema_version:3`. Event có thể tồn tại lâu trong broker hoặc data lake, độc lập với document schema hiện hành.

### 2.5. MongoDB Server/FCV

`db.version()` cho biết version server, còn FCV là trạng thái compatibility của những feature persisted trong MongoDB deployment. FCV **không phải** `schema_version` của business entity.

### 2.6. Bảng đối chiếu

| Version | Chủ sở hữu | Được tăng khi |
|---|---|---|
| Application | Đội phát triển/deployment | Release code |
| Document schema | Chủ collection/domain | Đổi persistent contract |
| API | API owner | Đổi external interface contract |
| Event | Event producer/contract owner | Đổi payload semantics |
| Server/FCV | DBA/SRE/Atlas | Nâng MongoDB engine/features |

Không tạo quy tắc “app V2 bắt buộc mọi document có schema_version=2” nếu ứng dụng thực tế đang chấp nhận dữ liệu cũ trong giai đoạn chuyển đổi.

---

## 3. Thế nào là tương thích ngược và tương thích xuôi?

### 3.1. Backward compatibility

**Ứng dụng mới đọc được dữ liệu cũ.**

~~~text
Document V1 -> Application V2 -> OK
~~~

Ví dụ V2 đọc `full_name` nếu `display_name` chưa có.

### 3.2. Forward compatibility

**Ứng dụng cũ chịu được dữ liệu do ứng dụng mới ghi**, trong phạm vi contract đã thiết kế.

~~~text
Document V2 -> Application V1 -> OK
~~~

Nếu V2 chỉ ghi `display_name` mà V1 chỉ đọc `full_name`, yêu cầu này thất bại.

### 3.3. Write compatibility

Đọc được không có nghĩa **ghi an toàn**. Một ứng dụng cũ có thể decode V2 document, nhưng `save` toàn document lại xóa những fields mới mà nó không biết.

### 3.4. Mixed-version window

Khoảng thời gian có nhiều versions cùng hoạt động, bao gồm:

- Instances của REST API.
- Background workers.
- Scheduled jobs.
- Change Stream consumers.
- Mobile/offline clients (nếu trực tiếp tác động contract qua API).
- External services được cấp quyền đọc/ghi collection.
- Batch/ETL jobs chạy theo lịch không trùng deploy.

Một migration chỉ an toàn khi xem xét **tất cả writers/readers**, không chỉ pod mới của web service.

---

## 4. Ma trận tương thích ứng dụng và document

Giả sử:

- App V1 chỉ biết `full_name`.
- App V2 hiểu `full_name` và `display_name`.
- Document V1 có `full_name`.
- Document V2 có `display_name`.

### 4.1. Ma trận đọc

| Reader | Document V1 | Document V2 |
|---|---|---|
| App V1 (chỉ full_name) | Đọc được | **Lỗi/mất tên** nếu V2 không giữ field cũ |
| App V2 (dual-read) | Đọc được qua fallback | Đọc được |

### 4.2. Ma trận ghi

| Writer | Document V1 | Document V2 |
|---|---|---|
| App V1 (chỉ ghi full_name) | Ghi đúng field cũ | Có thể làm dữ liệu lệch nếu V2 dùng display_name |
| App V2 (ghi cả hai) | Duy trì khả năng V1 đọc | Duy trì cả hai fields, nhưng phải tránh race |

### 4.3. Điều kiện tối thiểu

Để deployment an toàn, phải nêu cụ thể:

1. Reader V2 đọc được V1 và V2 documents.
2. Reader V1 đọc được những documents mà writer V2 tạo trong thời gian V1 vẫn chạy.
3. Writer V1 không phá dữ liệu V2 cần.
4. Writer V2 không tạo giá trị mà V1 không hiểu (đặc biệt enum/validation).
5. Những thay đổi cập nhật đồng thời được giải quyết có thứ tự rõ ràng.
6. Rollback code trong compatibility window vẫn đọc/ghi được.

### 4.4. Không chỉ kiểm tra “query chạy thành công”

Một query không trả lỗi nhưng trả `null`, mất field hoặc bỏ qua 20% records vẫn là thất bại về contract.

---

## 5. Case study xuyên suốt: đổi tên khách hàng

Ta sử dụng collection `customers`.

### 5.1. Schema V1

~~~javascript
{
  _id: "CUS-101",
  tenant_id: "tenant-a",
  full_name: "Nguyễn An",
  status: "ACTIVE",
  created_at: ISODate("2026-11-01T10:00:00Z")
}
~~~

### 5.2. Schema đích V2

~~~javascript
{
  _id: "CUS-101",
  tenant_id: "tenant-a",
  display_name: "Nguyễn An",
  schema_version: 2,
  status: "ACTIVE",
  created_at: ISODate("2026-11-01T10:00:00Z")
}
~~~

### 5.3. Schema chuyển tiếp

~~~javascript
{
  _id: "CUS-101",
  tenant_id: "tenant-a",
  full_name: "Nguyễn An",
  display_name: "Nguyễn An",
  schema_version: 2,
  status: "ACTIVE",
  created_at: ISODate("2026-11-01T10:00:00Z")
}
~~~

Schema chuyển tiếp giữ cả hai fields. Điều đó giúp ứng dụng cũ tiếp tục đọc, **nhưng chưa giải quyết được vấn đề khi writer cũ cập nhật chỉ full_name**; vấn đề này sẽ được xử lý ở các bước triển khai.

### 5.4. Vì sao không `$rename` ngay?

~~~javascript
db.customers.updateMany(
  {},
  {
    $rename: {
      full_name: "display_name"
    }
  }
);
~~~

Lệnh này xóa tên field cũ trên những documents được đổi. App V1 vẫn đọc `full_name` sẽ mất dữ liệu, còn duplicate/target field có thể bị overwrite theo semantics `$rename`. Không thực hiện như một bước đầu của zero-downtime migration.

---

## 6. Chiến lược chuẩn: expand → migrate → contract

~~~text
          V1 đang chạy
                |
                v
       EXPAND compatibility
       - V2 đọc schema cũ/mới
       - V2 viết dữ liệu để V1 vẫn hiểu
       - indexes/validators tạm hỗ trợ cả hai
                |
                v
          MIGRATE data
       - backfill theo lô
       - quan sát lag/duplicates
       - đối soát và sửa drift
                |
                v
        RETIRE old writers
       - dừng các app/job V1 ghi field cũ
       - final reconciliation
       - chuyển canonical field
                |
                v
           CONTRACT
       - xóa field cũ khi an toàn
       - bỏ fallback/code tạm
       - siết validator và dọn indexes
~~~

### 6.1. Expand

Mở rộng phần mềm để hiểu nhiều schema versions, không buộc mọi document đổi ngay.

### 6.2. Migrate

Backfill dữ liệu cũ sang format mới, trong khi các versions khác nhau còn hoạt động. Để tránh drift, cần đồng bộ/khóa những writers cũ hoặc có reconciliation.

### 6.3. Contract

Chỉ bỏ schema cũ sau khi **không còn consumer/writer cần nó**, migration hoàn tất, rollback window đã kết thúc và monitoring chứng minh không còn phụ thuộc.

### 6.4. Không làm ba pha trong một deploy

Dồn “code mới + rename field + index drop + validator strict” vào một release làm rollback rất khó. Tách nhiều releases có checkpoints rõ ràng.

---

## 7. Phân loại thay đổi schema theo rủi ro

| Thay đổi | Rủi ro tương thích | Cách tiếp cận |
|---|---|---|
| Thêm optional field | Thường thấp với readers chịu unknown fields | Deploy reader an toàn; kiểm tra replace writers |
| Thêm required field | Cao với documents cũ | Default/fallback → backfill → validator |
| Rename field | Cao | Dual-read/write, final sync, contract |
| Xóa field | Cao nếu có consumer cũ | Inventory consumers, deprecate, staged removal |
| Đổi BSON type | Cao | Dual fields/converter/backfill, test precision |
| Đổi enum value | Cao | Readers chấp nhận cả cũ/mới trước khi writers phát giá trị mới |
| Đổi embedded → reference | Rất cao | Dual representation, consistency và backfill |
| Split collection | Cao | Data ownership/cutover/transaction/outbox |
| Merge collections | Cao | Key collision, dedup, schema reconciliation |
| Đổi tenant/shard key | Rất cao | Thay topology/query patterns, procedures riêng |
| Đổi index | Ảnh hưởng đọc/ghi và uniqueness | Create-first, validate, cutover, drop-last |
| Thay validator | Có thể chặn writes cũ | Gradual warn/moderate/error theo policy |

Không có thay đổi nào “chắc chắn an toàn” chỉ vì JSON document vẫn parse được.

---

## 8. Có nên thêm field `schema_version` vào từng document?

### 8.1. Khi hữu ích

`schema_version` giúp:

- Xác định codec/mapper cần dùng cho những cấu trúc khác nhau.
- Đếm documents chưa được migrate.
- Tạo backfill checkpoint và migration cohorts.
- Chọn strategy theo phiên bản khi dữ liệu lịch sử phải tồn tại lâu.
- Cung cấp audit/provenance trong ETL.

Ví dụ:

~~~javascript
{
  _id: "CUS-101",
  schema_version: 2,
  display_name: "Nguyễn An"
}
~~~

### 8.2. Không phải lúc nào cũng cần

Nếu chỉ thêm một optional field mà readers xử lý missing tốt, việc gắn `schema_version` trên toàn collection có thể không mang lại giá trị đủ lớn.

### 8.3. Version phải có semantics

Ví dụ định nghĩa:

| schema_version | Ý nghĩa |
|---|---|
| Missing hoặc 1 | Tên canonical trong `full_name` |
| 2 | `display_name` có dữ liệu, tương thích V2; có thể còn `full_name` trong chuyển tiếp |
| 3 | Không còn field legacy; chỉ `display_name`, các ràng buộc mới |

Nếu version 2 chỉ nói “code deploy ngày X” thì vô nghĩa với data contract.

### 8.4. Version đơn điệu hay nhiều chiều?

Một số hệ thống có nhiều bounded contexts trong cùng collection. Một số nguyên duy nhất có thể không biểu diễn hết thay đổi độc lập. Có thể dùng các trường version theo logical sections hoặc migration markers.

### 8.5. Không dùng version thay cho kiểm tra field

Một document ghi `schema_version:2` nhưng thiếu `display_name` vẫn có dữ liệu lỗi. Khi đọc và backfill cần kiểm tra **shape thực tế**, không chỉ tin marker.

### 8.6. Version không được tự tăng mỗi update

`schema_version` là version **hình dạng dữ liệu**, không phải optimistic locking version. Sửa `status` từ PENDING sang PAID không nhất thiết tăng schema_version.

---

## 9. Phân biệt schema_version và optimistic version

Ví dụ:

~~~javascript
{
  _id: "CUS-101",
  schema_version: 2,
  version: NumberLong("7"),
  display_name: "Nguyễn An"
}
~~~

- `schema_version=2`: cấu trúc document phù hợp contract V2.
- `version=7`: thế hệ cập nhật entity, dùng cho optimistic locking hoặc CAS.

### 9.1. Vì sao quan trọng?

Nếu backfill đổi shape từ V1 sang V2 trong khi user sửa `display_name`, phải bảo vệ update cạnh tranh. Dùng optimistic version hoặc conditional field predicates; không dùng `schema_version` làm counter concurrency nếu các operations thông thường không quản lý nó.

### 9.2. Version counter cần write path nhất quán

Nếu app mới dùng `@Version` nhưng app cũ ghi bằng raw `updateOne` không tăng version, CAS sẽ không phát hiện mọi write. Trong thời gian chuyển tiếp, cần xác định tất cả writers và update conventions.

---

## 10. Reader V2: dual-read với fallback

Một mapping Java minh họa:

~~~java
public final class CustomerNameView {

    private final String displayName;

    public CustomerNameView(String displayName) {
        this.displayName = displayName;
    }

    public String displayName() {
        return displayName;
    }
}
~~~

Ở tầng read model, ta có thể lấy hai fields từ raw BSON:

~~~java
import org.bson.Document;
import com.mongodb.client.MongoCollection;

MongoCollection<Document> rawCustomers =
    mongoDatabase.getCollection("customers");

Document raw = rawCustomers.find(
    new Document("_id", "CUS-101")
).first();

if (raw != null) {
    String oldName = raw.getString("full_name");
    String newName = raw.getString("display_name");

    // Trong khi V1 vẫn ghi, full_name có thể
    // là giá trị mới nhất: chọn chính sách rõ.
    String selected = oldName != null
        ? oldName
        : newName;

    CustomerNameView view =
        new CustomerNameView(selected);
}
~~~

### 10.1. “Ưu tiên field nào?” là quyết định nghiệp vụ

Nếu writer V1 vẫn được phép sửa `full_name` và writer V2 luôn sửa cả `full_name`/`display_name`, đọc **ưu tiên field cũ** trong mixed-version window sẽ giảm nguy cơ đọc giá trị mới đã stale sau khi V1 update.

Sau khi chặn được mọi writer cũ và hoàn tất final synchronization, chuyển reader sang **ưu tiên display_name**.

### 10.2. Không tự dùng `display_name ?? full_name` mà không xét writer

Nếu V1 thay `full_name` hôm nay nhưng `display_name` vẫn giữ giá trị từ hôm qua, reader ưu tiên field mới sẽ hiển thị tên cũ. Dual-read chỉ giải quyết thiếu field, **không tự xử lý hai giá trị mâu thuẫn**.

### 10.3. Null và empty string

Một field rỗng `""` có thể là giá trị không hợp lệ; nhưng fallback dựa trên Java `null` không xử lý được empty string. Định nghĩa rule:

- Missing: fallback.
- Explicit null: fallback hoặc business-null theo contract.
- Empty string: reject, normalize hay xem là giá trị?
- Cả hai có nhưng khác nhau: ưu tiên theo writer phase, log discrepancy.

### 10.4. Không bỏ exception âm thầm

Nếu field tồn tại nhưng có BSON type sai (number thay vì string), `getString` có thể lỗi. Không catch mọi exception và mặc định tên rỗng; ghi data-quality metric và xử lý theo policy.

---

## 11. Dual-read trong MongoDB aggregation

Dùng `$ifNull` khi muốn fallback đơn giản:

~~~javascript
db.customers.aggregate([
  {
    $match: {
      tenant_id: "tenant-a"
    }
  },
  {
    $project: {
      _id: 1,
      tenant_id: 1,
      resolved_name: {
        $ifNull: [
          "$display_name",
          "$full_name"
        ]
      },
      schema_version: {
        $ifNull: ["$schema_version", 1]
      }
    }
  }
]);
~~~

### 11.1. Chỉ dùng thứ tự này khi phù hợp giai đoạn

Pipeline trên ưu tiên `display_name`. Trong mixed writer window nơi V1 vẫn có thể cập nhật `full_name`, có thể cần đổi thứ tự:

~~~javascript
resolved_name: {
  $ifNull: [
    "$full_name",
    "$display_name"
  ]
}
~~~

Đây là sự khác biệt giữa **fallback theo sự tồn tại của field** và **quy tắc xác định nguồn mới nhất**.

### 11.2. `$ifNull` không sửa dữ liệu

Nó chỉ tạo field kết quả khi đọc. Collection vẫn có schema hỗn hợp, và query/index trên `display_name` vẫn không tự dùng `full_name`.

### 11.3. Tính đúng của pagination/sort/search

Nếu user sort theo tên đã resolve, một index chỉ trên `display_name` không chắc hỗ trợ hiệu quả khi cần tính `$ifNull`. Trong chuyển tiếp, API có thể phải query cả hai paths hoặc chịu chi phí sort; đây là lý do migration phải có kế hoạch index và performance.

---

## 12. Writer V2: dual-write nhất quán trong một document

Trong compatibility window, mọi V2 update tên phải ghi **cả hai fields trong một operation**:

~~~javascript
db.customers.updateOne(
  {
    _id: "CUS-101",
    tenant_id: "tenant-a"
  },
  {
    $set: {
      full_name: "Nguyễn An Mới",
      display_name: "Nguyễn An Mới",
      schema_version: 2
    }
  }
);
~~~

### 12.1. Vì sao một operation?

Nếu gọi hai lệnh riêng:

~~~text
set full_name
     |
request crash
     |
display_name chưa được cập nhật
~~~

thì hai fields có thể lệch ngay cả khi không có writer cũ. Một update document có `$set` cả hai fields là atomic trong MongoDB.

### 12.2. Nhưng writer V1 vẫn có thể gây drift

V1 chỉ chạy:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  { $set: { full_name: "Tên từ V1" } }
);
~~~

Kết quả:

~~~javascript
{
  full_name: "Tên từ V1",
  display_name: "Nguyễn An Mới",
  schema_version: 2
}
~~~

Hai field khác nhau. **Dual-write của V2 không thể sửa một writer V1 mà V2 không kiểm soát.**

### 12.3. Các lựa chọn xử lý

1. **Ưu tiên old field khi đọc** cho đến khi V1 writers dừng hẳn.
2. **Nâng V1 bằng compatibility patch** để V1 cũng dual-write, nếu có thể.
3. **Tạm khóa một loại write** trong cửa sổ ngắn, nếu nghiệp vụ chấp nhận.
4. **Đồng bộ qua Change Streams/outbox** với ordering/version; phức tạp hơn và có độ trễ.
5. **Routing writers**: đưa tất cả name updates qua một service duy nhất đã hỗ trợ dual-write.

Không chọn “last write wins” dựa trên hai clocks không đáng tin khi không có thiết kế rõ ràng.

---

## 13. Sequence triển khai không gián đoạn

### Giai đoạn 0 — Inventory

Tìm tất cả writers/readers:

- Java API V1.
- Admin UI.
- Scheduled CRM sync.
- MongoDB migration jobs.
- Data pipelines.
- Change Stream consumers.
- Mobile/offline reconciliation.
- Script bảo trì trực tiếp trên MongoDB.

Ghi rõ ai đang đọc/ghi `full_name` và có dùng full replacement không.

### Giai đoạn 1 — Safety release

Nếu V1 dùng `save`/`replaceOne` toàn document và xóa unknown fields, cần **sửa V1 thành field-level updates hoặc giữ unknown fields** trước khi V2 thêm dữ liệu. Đây là điều kiện bắt buộc trong một số hệ thống.

### Giai đoạn 2 — Expand app V2

V2:

- Đọc cả `full_name`/`display_name`.
- Khi V1 còn chạy, chọn read precedence phù hợp writer.
- Ghi cả hai field khi sửa tên.
- Vẫn phát enum/event payload mà V1 hiểu.
- Không tự xóa field legacy.

### Giai đoạn 3 — Deploy V2 dần

Canary một phần traffic, kiểm tra errors/mismatch. Phần V1 còn lại tiếp tục hoạt động được.

### Giai đoạn 4 — Backfill

Sao chép `full_name` sang `display_name` trên documents còn thiếu, đặt marker `schema_version` với điều kiện phù hợp.

### Giai đoạn 5 — Drain old writers

Bảo đảm không còn pod, worker, scheduled job hoặc scripts V1 ghi `full_name` đơn lẻ. Có thể cần chờ in-flight requests và job leases.

### Giai đoạn 6 — Final reconciliation

Đồng bộ lại những documents bị writer V1 cập nhật sau khi backfill, xác định canonical source, kiểm tra counts và sample diffs.

### Giai đoạn 7 — Switch canonical

Mọi readers dùng `display_name` là nguồn chính, V2 có thể tiếp tục dual-write trong rollback window.

### Giai đoạn 8 — Contract

Sau khi không còn V1 dependency/rollback need, xóa `full_name` có kiểm soát, cập nhật validator/index, bỏ code compatibility.

---

## 14. Backfill: chuyển dữ liệu cũ sang schema mới

### 14.1. Vì sao không chạy một lệnh không giới hạn ngay trên production?

Một `updateMany` quét hàng chục triệu documents có thể gây:

- I/O và CPU tăng.
- Oplog/change stream volume tăng.
- Write contention.
- Disk/storage growth.
- Replica lag.
- Ảnh hưởng p95/p99 latency.
- Khó dừng và phục hồi nếu job lỗi giữa chừng.

Trên dataset nhỏ có thể dùng một updateMany, nhưng production thường cần **batching, rate limit, checkpoint và monitoring**.

### 14.2. Bản sao một lượt bằng aggregation update pipeline

Ví dụ có điều kiện, chỉ với documents thiếu field mới:

~~~javascript
db.customers.updateMany(
  {
    full_name: { $type: "string" },
    display_name: { $exists: false }
  },
  [
    {
      $set: {
        display_name: "$full_name",
        schema_version: 2
      }
    }
  ]
);
~~~

Update bằng **aggregation pipeline** cho phép dùng `"$full_name"` như biểu thức đọc giá trị field hiện tại. Nếu sử dụng classic update `{$set:{display_name:"$full_name"}}`, nó có thể ghi literal string `"$full_name"`, không copy nội dung.

### 14.3. Idempotency

Filter `display_name:{$exists:false}` giúp lần chạy lại không overwrite những documents đã có field mới. Tuy nhiên nếu field mới đã tồn tại nhưng **stale**, bước này **không sửa drift**; final reconciliation là một giai đoạn riêng.

### 14.4. Null/missing edge case

Nếu `full_name` là null/missing, filter `$type:"string"` sẽ bỏ qua document; cần phân loại và xử lý theo policy thay vì viết `display_name:null` rồi đánh dấu migration thành công.

### 14.5. Không tự nâng version khi chưa đúng contract

Nếu app V2 đòi có cả `display_name` không rỗng và `tenant_id` hợp lệ, những documents chưa đạt phải ở trạng thái needs-repair; không chỉ set `schema_version:2` cho mọi document.

---

## 15. Backfill theo batch có thể chạy lại

Dưới đây là một cách thực hành trong `mongosh` để xử lý các documents thiếu field mới theo thứ tự `_id`.

~~~javascript
use schema_evolution_lab

const batchSize = 200;
let lastId = null;
let totalModified = 0;

while (true) {
  const filter = {
    full_name: { $type: "string" },
    display_name: { $exists: false }
  };

  if (lastId !== null) {
    filter._id = { $gt: lastId };
  }

  const batch = db.customers.find(
    filter,
    { _id: 1 }
  ).sort({ _id: 1 }).limit(batchSize).toArray();

  if (batch.length === 0) {
    break;
  }

  const writes = batch.map(doc => ({
    updateOne: {
      filter: {
        _id: doc._id,
        full_name: { $type: "string" },
        display_name: { $exists: false }
      },
      update: [
        {
          $set: {
            display_name: "$full_name",
            schema_version: 2
          }
        }
      ]
    }
  }));

  const result = db.customers.bulkWrite(
    writes,
    { ordered: false }
  );

  totalModified += result.modifiedCount;
  lastId = batch[batch.length - 1]._id;

  print(
    "lastId=" + lastId
    + " modified=" + totalModified
  );
}
~~~

### 15.1. Những giới hạn của script minh họa

- Dùng trong lab/staging hoặc production **đã được phê duyệt**.
- Không có persistent checkpoint xuyên process restart; thực tế cần lưu `lastId`/job version/metadata trong collection control.
- Chỉ duyệt các documents hiện đang thỏa filter, nên writes mới vào các `_id` nhỏ hơn checkpoint có thể xuất hiện **sau khi cursor đi qua**; cần chạy một vòng reconciliation cuối.
- Có thể bị concurrent writer đổi dữ liệu giữa lúc tìm batch và lúc update; filter được kiểm tra lại khi write, nhưng với writer cũ có thể vẫn xảy ra drift sau đó.
- Không có built-in sleep/rate limiting; production cần giới hạn throughput theo monitoring.
- Nếu `_id` có hỗn hợp BSON types, cách so sánh theo `_id` cần được thử nghiệm để bảo đảm ordering/pagination nhất quán.
- Thực tế phải xử lý bulk errors và partial results thay vì giả định mọi batch thành công.
- Bulk update pipeline yêu cầu MongoDB Server version hỗ trợ aggregation pipeline updates.

### 15.2. Checkpoint an toàn

Một thiết kế thực tế:

~~~javascript
{
  _id: "customer_name_v2_backfill",
  run_id: "MIG-2026-11-14",
  last_id: "CUS-40000",
  status: "RUNNING",
  batches_completed: 200,
  modified_total: 38950,
  updated_at: ISODate("2026-11-14T05:00:00Z")
}
~~~

Checkpoint chỉ được nâng sau khi batch thành công theo criteria đã chọn. Nếu có unknown write result, phải query/reconcile trước khi tiếp tục để tránh báo sai.

### 15.3. Chia theo tenant

Nếu dữ liệu nhiều tenant, có thể phân công tenant cohorts để giới hạn ảnh hưởng và dễ rollback/canary. Nhưng cần kiểm tra skew: một tenant có thể lớn hơn tất cả tenants khác.

---

## 16. Final reconciliation: xử lý khác biệt giữa hai fields

Sau khi **không còn writer V1**, xác định old field là nguồn đúng cuối cùng trong compatibility policy ví dụ.

### 16.1. Tìm documents lệch

~~~javascript
db.customers.aggregate([
  {
    $match: {
      full_name: { $type: "string" },
      display_name: { $type: "string" }
    }
  },
  {
    $match: {
      $expr: {
        $ne: [
          "$full_name",
          "$display_name"
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      tenant_id: 1,
      full_name: 1,
      display_name: 1
    }
  },
  { $limit: 100 }
]);
~~~

### 16.2. Tại sao không tự sửa tất cả bằng new field?

Nếu V1 update `full_name` sau khi initial backfill, `display_name` có thể cũ hơn. Cần xác định nguồn đúng dựa vào phase/writer policy hoặc audit log, không dùng “tên field mới hơn là đúng”.

### 16.3. Final sync theo policy old canonical

Khi đã chắc chắn **old field là authoritative** trong mixed window và không còn writer cũ:

~~~javascript
db.customers.updateMany(
  {
    full_name: { $type: "string" }
  },
  [
    {
      $set: {
        display_name: "$full_name",
        schema_version: 2
      }
    }
  ]
);
~~~

Lệnh có thể thay field mới ở những documents đang chứa giá trị khác; **chỉ chạy nếu policy old canonical là chắc chắn** và có backups/audit. Trên production nên chạy theo batch/checkpoint, không phải luôn dùng một updateMany toàn collection.

### 16.4. Nếu V2 đã cho ghi field mới độc lập

Khi hai bên ghi độc lập, không còn nguồn canonical đơn giản. Phải dùng version/event ordering/audit để merge; **không suy thứ tự cập nhật từ việc field nào tồn tại**.

---

## 17. Spring Data MongoDB: ánh xạ V1 và V2

### 17.1. Entity V1

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("customers")
public class CustomerV1 {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("full_name")
    private String fullName;

    public CustomerV1() {}

    // Getter/setter.
}
~~~

### 17.2. Entity V2 đọc cả hai trường

~~~java
@Document("customers")
public class CustomerV2 {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("full_name")
    private String legacyFullName;

    @Field("display_name")
    private String displayName;

    @Field("schema_version")
    private Integer schemaVersion;

    public CustomerV2() {}

    public String nameDuringMixedWindow() {
        return legacyFullName != null
            ? legacyFullName
            : displayName;
    }

    public String nameAfterCutover() {
        return displayName != null
            ? displayName
            : legacyFullName;
    }

    // Getter/setter cho các mapped fields.
}
~~~

### 17.3. Vì sao hai methods?

Trong mixed window, old writer có thể là nguồn name mới nhất. Sau khi dừng old writer và final sync, new field là canonical. Việc này phải được điều khiển bằng **migration phase/feature flag**, không triển khai tùy hứng theo từng service.

### 17.4. Mapped query paths

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("displayName").is("Nguyễn An")
);

CustomerV2 result = mongoTemplate.findOne(
    query,
    CustomerV2.class
);
~~~

Khi Spring Data mapping áp dụng, property `displayName` được ánh xạ tới `display_name`. Với raw driver hoặc custom query expressions, cần kiểm tra tên BSON thực tế.

### 17.5. Đừng chỉ đổi annotation

Đổi `@Field("full_name")` thành `@Field("display_name")` **không tự di chuyển dữ liệu đã lưu**. Cũng không khiến app V1 đọc được `display_name`.

---

## 18. Spring Data MongoTemplate: dual-write atomic

Ví dụ service V2 cập nhật tên:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class CustomerRenameService {

    private final MongoTemplate template;

    public CustomerRenameService(MongoTemplate template) {
        this.template = template;
    }

    public boolean changeName(
            String trustedTenantId,
            String customerId,
            String newName) {

        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                "Name must not be blank"
            );
        }

        Query q = Query.query(
            Criteria.where("id").is(customerId)
                .and("tenantId").is(trustedTenantId)
        );

        Update u = new Update()
            .set("legacyFullName", newName)
            .set("displayName", newName)
            .set("schemaVersion", 2);

        UpdateResult r = template.updateFirst(
            q,
            u,
            CustomerV2.class
        );

        return r.wasAcknowledged()
            && r.getMatchedCount() == 1;
    }
}
~~~

### 18.1. Vì sao dùng `Update` thay `save`?

`Update` chỉ sửa các fields cụ thể, tránh replace cả document và làm mất field mà model không biết.

### 18.2. Kiểm tra matchedCount

Nếu customer không tồn tại hoặc tenant không đúng, không được coi là cập nhật thành công. Với security, trả response phù hợp mà không tiết lộ ID có tồn tại ở tenant khác hay không.

### 18.3. Không phải dual-write là hai transactions

Hai tên field nằm trong **cùng một document**, được set bằng một MongoDB update nên atomic ở cấp document. Không cần mở transaction chỉ vì sửa hai fields cùng document.

### 18.4. Khi cần CAS

Nếu V1/V2 cùng thay tên và business yêu cầu conflict detection, thêm expected version vào Query và increment một optimistic version thống nhất; lưu ý **mọi writer** phải tuân thủ version protocol.

---

## 19. Vấn đề nguy hiểm: full-document replacement từ app cũ

Giả sử V2 ghi:

~~~javascript
{
  _id: "CUS-101",
  full_name: "Nguyễn An",
  display_name: "Nguyễn An",
  schema_version: 2,
  loyalty_points: 100
}
~~~

App V1 đọc về entity chỉ biết:

~~~text
_id
full_name
loyalty_points
~~~

Rồi dùng `save`/`replaceOne` để thay cả document:

~~~javascript
{
  _id: "CUS-101",
  full_name: "Nguyễn An",
  loyalty_points: 120
}
~~~

Các fields `display_name` và `schema_version` có thể bị mất.

### 19.1. Cách phòng tránh

- Đổi V1 writes thành `$set`/`$inc` tại field cần sửa.
- Nếu không đổi được writer cũ, trì hoãn rollout schema mới hoặc cô lập records/writes.
- Trong một số models, giữ unknown fields bằng extra-elements mapping, nhưng vẫn cần test kỹ vì replace semantics.
- Có version/CAS hoặc transaction nếu business yêu cầu conflict detection.
- Monitoring count documents từng schema sau khi V1 writes tiếp tục.

### 19.2. Không mặc định optimistic lock bao trùm mọi actor

`@Version` trong Spring Data chỉ giúp nếu tất cả thao tác liên quan thực sự tuân thủ version/conditional check. Một raw script hay service cũ không tăng version có thể làm bảo vệ đó thiếu hiệu lực.

### 19.3. Partial read model cũng nguy hiểm

Ngay cả V2 có đầy đủ fields, nếu query projection chỉ tải vài fields rồi dùng `save`, những fields không được load có thể biến mất. Không dùng partial entity cho full replacement.

---

## 20. Các trường hợp dữ liệu `missing`, `null` và empty

Ví dụ:

~~~javascript
{ _id: 1 }
{ _id: 2, display_name: null }
{ _id: 3, display_name: "" }
{ _id: 4, display_name: "Nguyễn An" }
~~~

Bốn trạng thái có thể mang nghĩa nghiệp vụ khác nhau.

### 20.1. Query tồn tại

~~~javascript
db.customers.find({
  display_name: { $exists: false }
});
~~~

Tìm những documents **không có** field.

### 20.2. Query null

~~~javascript
db.customers.find({
  display_name: null
});
~~~

Thường match cả BSON null **và missing**. Nếu chỉ muốn field explicit null, có thể dùng `$type:10` theo semantics MongoDB.

### 20.3. Missing khác null trong migration

Nếu `display_name` missing, backfill từ `full_name` là hợp lý. Nếu `display_name:null` biểu thị “khách cố ý xóa tên hiển thị”, tự backfill có thể đảo ngược ý định.

### 20.4. Null và primitive Java

Nếu thêm field `int loyaltyPoints`, documents thiếu field có thể decode thành 0 trong một số Java mapping paths. Nếu cần phân biệt chưa có với 0, dùng `Integer`/presence semantics và validator.

### 20.5. Fallback không giải quyết sai kiểu

`display_name` là BSON number 123 không trở thành tên hợp lệ chỉ vì `$ifNull` không coi nó là null. Cần validation/data repair.

---

## 21. Thay đổi kiểu BSON: String → Number hoặc Double → Decimal128

### 21.1. Trường hợp rủi ro

V1 lưu:

~~~javascript
{
  amount: "125000"
}
~~~

V2 muốn:

~~~javascript
{
  amount_minor: NumberLong("125000")
}
~~~

Nếu V2 chỉ đổi Java property từ `String` thành `Long`, dữ liệu V1 vẫn là string. Codec/converter có thể không xử lý hoặc xử lý không như business muốn.

### 21.2. Phương án chuyển tiếp

- Thêm field mới `amount_minor`.
- Reader V2 đọc field mới nếu hợp lệ, nếu không parse field cũ theo rules rõ.
- Writer V2 ghi cả fields trong compatibility window khi V1 cần.
- Backfill có kiểm tra parse/overflow.
- Reconcile values và loại bản ghi lỗi ra queue repair.
- Chỉ bỏ field cũ khi readers/writers V1 dừng.

### 21.3. Không dùng Double cho tiền tùy tiện

Binary floating-point có sai số. Với tiền, dùng `NumberLong` minor units hoặc `Decimal128` tùy currency/rounding policy. Đổi representation phải xét precision, rounding và exchange rates.

### 21.4. Chuyển đổi bằng aggregation pipeline

Ví dụ chỉ với chuỗi số nguyên hợp lệ:

~~~javascript
db.invoices.updateMany(
  {
    amount_minor: { $exists: false },
    amount_string: {
      $type: "string",
      $regex: /^[0-9]+$/
    }
  },
  [
    {
      $set: {
        amount_minor: {
          $toLong: "$amount_string"
        },
        schema_version: 2
      }
    }
  ]
);
~~~

**Lưu ý:** Regex không đảm bảo số nằm trong miền Int64; `$toLong` có thể lỗi nếu overflow. Trên production, có thể dùng `$convert` với `onError`/`onNull`, phân loại dữ liệu lỗi và không đánh dấu thành công nếu chưa chuyển đúng.

### 21.5. Numeric comparison và indexes

Nếu cùng field có cả string `"100"` và number `100`, sorting/filtering dựa trên BSON type comparison khác kỳ vọng toán học. Tránh để API V2 dùng một index/query assume field đã đồng nhất khi backfill còn đang diễn ra.

---

## 22. Enum và business status versioning

Giả sử V1 chỉ biết:

~~~text
PENDING
PAID
CANCELLED
~~~

V2 bổ sung:

~~~text
PARTIALLY_REFUNDED
~~~

Nếu V2 ghi `PARTIALLY_REFUNDED` trong khi V1 Java enum decoder không biết giá trị này, V1 có thể decode thất bại.

### 22.1. Expand reader trước writer

1. Deploy V1.1 reader chấp nhận trạng thái mới nhưng vẫn xử lý theo fallback an toàn.
2. Xác nhận toàn bộ consumers hiểu trạng thái.
3. Bật writer phát giá trị mới bằng feature flag.
4. Theo dõi errors/backward compatibility.
5. Khi migration hoàn tất, có thể bỏ fallback cũ nếu contract cho phép.

### 22.2. Không tự map unknown thành một trạng thái làm thay đổi nghiệp vụ

Ví dụ chuyển mọi unknown status thành `PENDING` có thể khiến đơn đã được hoàn tiền lại bị xử lý như chưa thanh toán. Với state machine/finance, unknown thường phải được reject/quarantine hoặc xử lý theo explicit policy.

### 22.3. Event consumers cũng phải tương thích

Nếu application V2 publish `PARTIALLY_REFUNDED` vào Kafka, những consumers cũ không được cập nhật vẫn có thể hỏng dù database query không lỗi.

---

## 23. Đổi nested object và array schema

V1:

~~~javascript
{
  shipping_address: "12 Đường A, HCM"
}
~~~

V2:

~~~javascript
{
  shipping_address_v2: {
    line1: "12 Đường A",
    city: "Hồ Chí Minh",
    country: "VN"
  }
}
~~~

### 23.1. Tại sao không overwrite cùng field ngay?

V1 dùng `String shippingAddress`, V2 dùng nested object. Nếu cùng BSON key có lúc string, có lúc document, codecs/queries có thể lỗi hoặc mất ý nghĩa. Tạo field mới trong compatibility window thường rõ ràng hơn.

### 23.2. Không thể parse mọi address string hoàn hảo

Legacy address không cấu trúc có thể thiếu country/city. Những dữ liệu không chuyển được cần review/manual repair, không tự điền thông tin bịa.

### 23.3. Mảng embedded

V1:

~~~javascript
items: [
  { sku: "SKU-1", qty: 2 }
]
~~~

V2:

~~~javascript
items_v2: [
  {
    sku: "SKU-1",
    quantity: 2,
    unit_price_minor: NumberLong("100000")
  }
]
~~~

Nếu thiếu giá ở data cũ, phải xác định source: order snapshot, product price at purchase, invoice ledger... Không lấy current product price tùy tiện để tái dựng giá lịch sử.

### 23.4. Array update paths

Trong thời gian tồn tại V1/V2, một worker dùng `items.$[line].qty` còn V2 dùng `items_v2.$[line].quantity`; nếu không có đồng bộ, hai structures lệch nhau. Cần xác định canonical representation và write compatibility strategy.

---

## 24. Embedded → referenced documents

Ví dụ V1 lưu shipping addresses ngay trong customer:

~~~javascript
{
  _id: "CUS-101",
  addresses: [
    { id: "ADDR-1", city: "HCM" }
  ]
}
~~~

V2 muốn tách:

~~~javascript
// customers
{
  _id: "CUS-101",
  address_ids: ["ADDR-1"]
}

// addresses
{
  _id: "ADDR-1",
  customer_id: "CUS-101",
  city: "HCM"
}
~~~

### 24.1. Rủi ro

- Hai collections có thể tạm không nhất quán.
- Old writer chỉ sửa embedded addresses, new reader chỉ đọc references.
- Delete cascade/tenant isolation thay đổi.
- One-to-many reference có eventual consistency nếu sync qua CDC.
- Transactions trên nhiều documents có chi phí/giới hạn.

### 24.2. Chuyển tiếp

- New reader có thể đọc cả embedded và referenced representation.
- Backfill addresses với stable IDs và unique keys.
- Đồng bộ writes hoặc tạm chuyển ownership qua một service.
- Reconcile referential integrity.
- Khi không còn old writers, switch canonical sang references.
- Chỉ xóa embedded field sau rollback window.

### 24.3. Không mặc định transaction giải quyết external consistency

Transaction MongoDB có thể atomic across documents theo điều kiện deployment. Nhưng message broker/payment provider/HTTP callbacks bên ngoài vẫn cần outbox/idempotency.

---

## 25. MongoDB schema validation: áp dụng theo giai đoạn

MongoDB có thể dùng validator dựa trên `$jsonSchema` hoặc biểu thức query. Validator **không tự migration dữ liệu cũ**.

### 25.1. Giai đoạn đầu: chấp nhận old/new shapes

Nếu collection có hai schema, có thể bắt đầu với validator không quá chặt và `validationAction:"warn"` để quan sát không chặn writer cũ.

Ví dụ:

~~~javascript
db.runCommand({
  collMod: "customers",
  validator: {
    $or: [
      { full_name: { $type: "string" } },
      { display_name: { $type: "string" } }
    ]
  },
  validationLevel: "moderate",
  validationAction: "warn"
});
~~~

Điều kiện này chỉ là minh họa, chưa kiểm tra tất cả fields/tenant rules. **`collMod` thay cấu hình validator hiện có**, nên cần biết validator production trước khi đổi; không được ghi đè các điều kiện bảo vệ hiện hành.

### 25.2. `validationLevel`

- `strict`: kiểm tra inserts và updates theo validator.
- `moderate`: kiểm tra inserts và updates với documents hiện có đang valid; những documents đã invalid có xử lý linh hoạt hơn theo semantics MongoDB.

### 25.3. `validationAction`

- `warn`: ghi cảnh báo cho violations thay vì chặn writes.
- `error`: từ chối những writes vi phạm khi chúng thuộc phạm vi validation.

Chọn theo tình trạng dữ liệu, khả năng sửa và mục tiêu rollout. Không để `warn` vĩnh viễn rồi cho rằng schema đã được cưỡng chế.

### 25.4. Sau migration: validator nghiêm hơn

Khi mọi old writers đã dừng và documents đạt V2 contract:

~~~javascript
db.runCommand({
  collMod: "customers",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenant_id",
        "display_name",
        "schema_version"
      ],
      properties: {
        tenant_id: {
          bsonType: "string"
        },
        display_name: {
          bsonType: "string",
          minLength: 1
        },
        schema_version: {
          bsonType: "int",
          minimum: 2
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

**Cẩn thận:** Những documents có version lưu kiểu Int64 thay vì Int32 có thể bị validator `bsonType:"int"` chặn. Khi áp quy tắc, phải kiểm tra BSON types thực tế và chọn contract nhất quán.

### 25.5. Validator không bảo đảm mọi business rule

Nó không tự kiểm tra cross-collection references, uniqueness theo nghiệp vụ hoặc external payment invariants. Dùng indexes/transactions/services khi cần.

### 25.6. Validation bypass

Những roles/operations có quyền `bypassDocumentValidation` có thể bỏ qua validator trong điều kiện hỗ trợ. Không dùng validator như cơ chế security duy nhất; dùng least privilege và audit.

---

## 26. Index migration: tạo trước, xóa sau

### 26.1. V1 query theo field cũ

~~~javascript
db.customers.createIndex(
  {
    tenant_id: 1,
    full_name: 1
  },
  {
    name: "idx_customer_tenant_full_name"
  }
);
~~~

### 26.2. V2 query theo field mới

~~~javascript
db.customers.createIndex(
  {
    tenant_id: 1,
    display_name: 1
  },
  {
    name: "idx_customer_tenant_display_name"
  }
);
~~~

Trong giai đoạn mixed-version, có thể cần **cả hai** indexes.

### 26.3. Tạo index không đồng nghĩa data đã backfill

Một index trên `display_name` không làm queries theo field mới tìm được những V1 documents chỉ có `full_name`. Phải dùng fallback query/aggregation hoặc chuyển dữ liệu.

### 26.4. Khi nào xóa index cũ?

Chỉ khi không còn queries/jobs cần `full_name` và telemetry xác nhận không còn phụ thuộc. Xóa sớm có thể làm app V1 chậm hoặc timeout.

### 26.5. Write amplification

Duy trì hai fields và hai indexes tăng storage/write cost tạm thời. Đây là chi phí của compatibility window cần được capacity-planning.

### 26.6. Kiểm tra query plans

~~~javascript
db.customers.find({
  tenant_id: "tenant-a",
  display_name: "Nguyễn An"
}).explain("executionStats");
~~~

Xem plan/index, docs examined, latency. Không dựa trên lab vài documents để kết luận performance.

---

## 27. Unique constraint khi đổi business key

V1 unique theo `tenant_id, email_lowercase`; V2 muốn unique theo `tenant_id, normalized_email`.

### 27.1. Trình tự rủi ro

Tạo unique index mới ngay khi dữ liệu cũ chưa chuẩn hóa có thể thất bại do duplicates hoặc missing/null semantics.

### 27.2. Quy trình

1. Định nghĩa normalization policy (casefold, Unicode, whitespace).
2. Backfill field mới và ghi nhận conflicts.
3. Sửa duplicates theo business ownership.
4. Tạo unique index phù hợp, có thể dùng partial filter nếu business chỉ unique khi field có giá trị hợp lệ.
5. Chuyển writers/readers sang new key.
6. Kiểm tra concurrent upserts; chỉ bỏ index cũ sau compatibility window.

### 27.3. Partial unique index

Ví dụ chỉ enforce unique với documents đã có `normalized_email` kiểu string:

~~~javascript
db.customers.createIndex(
  {
    tenant_id: 1,
    normalized_email: 1
  },
  {
    name: "uq_tenant_normalized_email",
    unique: true,
    partialFilterExpression: {
      normalized_email: { $type: "string" }
    }
  }
);
~~~

Điều này **không** bảo vệ documents chưa được backfill; phải bảo đảm application không tạo duplicates trong compatibility window.

### 27.4. Unique index không làm hai schemas tương đương

Nếu V1 upsert theo `email_lowercase` còn V2 upsert theo `normalized_email`, cả hai có thể tạo records logic trùng nhau nếu chưa có identity/key policy thống nhất.

---

## 28. Query compatibility trong giai đoạn mixed schema

### 28.1. Tìm customer theo tên

Query đơn field:

~~~javascript
db.customers.find({
  display_name: "Nguyễn An"
});
~~~

bỏ sót V1 documents.

### 28.2. Query chuyển tiếp

~~~javascript
db.customers.find({
  tenant_id: "tenant-a",
  $or: [
    { display_name: "Nguyễn An" },
    { full_name: "Nguyễn An" }
  ]
});
~~~

Tuy nhiên nếu hai fields mâu thuẫn, query có thể match document qua field cũ dù canonical name mới khác. Query matching và read precedence phải phù hợp cùng contract.

### 28.3. Sorting và pagination

Nếu sort theo `display_name` khi chỉ một nửa documents đã backfill, kết quả có thể khác so với sort tên đã resolve. Một aggregation tính `resolved_name` có thể tốn CPU/sort memory và không hưởng lợi trực tiếp từ index đơn field.

### 28.4. Text/Search indexes

Nếu app dùng MongoDB Search/Vector Search hoặc text index trên tên, cấu hình index phải chuyển sang field mới theo rollout. Data backfill không tự rebuild tất cả derived indexes ở mọi deployment mode ngay tức khắc.

### 28.5. Projections

Code cũ dùng projection chỉ trả `full_name` có thể vô tình che field mới; code mới phải kiểm tra projection tương thích trước khi fallback.

---

## 29. Change Streams và CDC trong tiến hóa schema

Change Streams có thể theo dõi inserts/updates, nhưng không phải migration engine bảo đảm consistency tự động.

### 29.1. Kiến trúc tùy chọn

~~~text
V1/V2 writes to MongoDB
        |
        v
Change Stream consumer
        |
        v
Normalization / validation / version checks
        |
        v
Repair new field or materialized projection
        |
        v
Checkpoint + monitoring
~~~

### 29.2. Độ trễ

Consumer xử lý event sau write, nên V1 cập nhật `full_name` trước khi `display_name` được đồng bộ có một khoảng dữ liệu lệch. Reader phải có fallback/consistency policy trong khoảng đó.

### 29.3. Duplicate/retry

Change Stream resume không biến business processing thành exactly-once. Consumer có thể xử lý event lại sau crash; migration repair phải idempotent hoặc có event/version dedup.

### 29.4. Ordering

Nếu nhiều workers partitions, có thể thấy event từ cùng entity đến lệch thứ tự. Dùng source version/sequence và conditional writes, không dựa vào thời gian nhận của worker.

### 29.5. Delete/pre-image

Delete event không mặc định có toàn bộ before document. Nếu cần biết old field/tenant để cập nhật projection hoặc cleanup, có thể cần pre-images với cấu hình/retention thích hợp, audit log hoặc contribution ledger.

### 29.6. Resume history bị mất

Nếu consumer nghỉ quá lâu, resume token có thể không còn dùng được. Cần bootstrap/reconciliation, không chỉ bắt đầu watch tại hiện tại rồi bỏ qua thay đổi cũ.

---

## 30. Backfill và online writes: vấn đề lost update

Timeline:

~~~text
T1  Migration đọc full_name="An"
T2  User đổi full_name="An Mới"
T3  Migration ghi display_name="An" từ dữ liệu T1
T4  Reader V2 ưu tiên display_name -> trả tên cũ
~~~

### 30.1. Vì sao script pipeline update có lợi?

Nếu dùng update pipeline:

~~~javascript
[
  {
    $set: {
      display_name: "$full_name"
    }
  }
]
~~~

server tính `"$full_name"` từ giá trị document tại lúc update, giảm nguy cơ dùng snapshot cũ do client đọc trước. Tuy nhiên V1 vẫn có thể ghi sau thời điểm backfill và làm drift.

### 30.2. Khi nào dùng CAS?

Nếu worker lấy snapshot rồi cần tính dữ liệu ở client, dùng filter `_id + expectedVersion` hoặc expected old field value:

~~~javascript
db.customers.updateOne(
  {
    _id: "CUS-101",
    full_name: "An",
    display_name: { $exists: false }
  },
  {
    $set: {
      display_name: "An",
      schema_version: 2
    }
  }
);
~~~

Nếu user đã đổi `full_name`, filter không match; worker phải re-read/retry, không overwrite.

### 30.3. Không chỉ dựa vào timestamps

Hai máy có thể lệch clock, event time khác commit order, dữ liệu offline có thể tới muộn. Dùng version/sequence monotonic hoặc compare-and-swap khi cần xác định “mới nhất”.

### 30.4. Khi đa collection

Đổi embedded structure thành references hoặc hai aggregate collections có thể cần transaction hoặc outbox + reconciliation. Atomicity single document không đủ.

---

## 31. Quy trình migration có thể tạm dừng và tiếp tục

Một job production nên quản lý:

~~~javascript
{
  _id: "customer_v2_migration",
  migration_version: 2,
  state: "RUNNING",
  owner: "data-platform",
  current_tenant: "tenant-a",
  last_id: "CUS-30000",
  examined: NumberLong("30000"),
  modified: NumberLong("28100"),
  skipped: NumberLong("1900"),
  errors: NumberLong("0"),
  started_at: ISODate("2026-11-14T01:00:00Z"),
  last_checkpoint_at: ISODate("2026-11-14T02:10:00Z")
}
~~~

### 31.1. Các trạng thái

- `PLANNED`.
- `RUNNING`.
- `PAUSED`.
- `FAILED_NEEDS_REPAIR`.
- `BACKFILL_COMPLETE`.
- `RECONCILED`.
- `CONTRACT_READY`.
- `DONE`.

### 31.2. Một migration run chỉ một owner hợp lệ

Nếu hai workers cùng backfill cùng bucket/tenant, cần lease/lock hoặc versioned CAS. Với idempotent updates, chạy trùng có thể không sai dữ liệu nhưng tăng tải và gây khó theo dõi.

### 31.3. Rate limit

Chọn batch size, concurrency, sleep, maxTimeMS/budget theo khả năng cluster; giám sát replication lag, CPU/IO và latency của online API.

### 31.4. Có lỗi thì dừng hay bỏ qua?

Đừng auto-skip mọi invalid documents rồi báo migration 100%. Ghi ID, reason, count, ticket; quyết định sửa thủ công hoặc quarantine theo business policy.

### 31.5. Backfill completion không đồng nghĩa contract ready

Chạy hết cursor chỉ nói job đã quét; vẫn cần kiểm tra data drift, old writers, search/index state, validator và rollback requirements.

---

## 32. Đo mức độ hoàn thành và bất nhất

### 32.1. Đếm documents thiếu new field

~~~javascript
db.customers.countDocuments({
  display_name: { $exists: false }
});
~~~

### 32.2. Đếm old field còn tồn tại

~~~javascript
db.customers.countDocuments({
  full_name: { $exists: true }
});
~~~

Trong compatibility window, count này có thể vẫn rất lớn **và hoàn toàn dự kiến**.

### 32.3. Đếm documents có cả hai nhưng khác nhau

~~~javascript
db.customers.countDocuments({
  full_name: { $type: "string" },
  display_name: { $type: "string" },
  $expr: {
    $ne: ["$full_name", "$display_name"]
  }
});
~~~

### 32.4. Đếm sai schema marker

~~~javascript
db.customers.countDocuments({
  schema_version: { $gte: 2 },
  display_name: { $exists: false }
});
~~~

Có marker V2 nhưng thiếu field bắt buộc → data-quality violation.

### 32.5. Không chỉ so counts

Hai collections có cùng số document vẫn có thể lệch data values. Với tiền, identifiers, permissions cần checksum/bucket-level reconciliation và business invariants.

### 32.6. Metrics nên có

| Metric | Ý nghĩa |
|---|---|
| `legacy_documents_remaining` | Số document chưa đạt new shape |
| `dual_field_mismatch_count` | Field cũ/mới lệch |
| `migration_processed_total` | Số records đã kiểm tra |
| `migration_modified_total` | Số records đã đổi |
| `migration_failed_total` | Records lỗi |
| `migration_checkpoint_age_seconds` | Job có bị kẹt? |
| `old_writer_write_rate` | Có còn writer legacy? |
| `new_reader_fallback_rate` | V2 còn cần đọc field cũ? |
| `schema_validation_warn_total` | Violations |
| `legacy_query_rate` | Có còn query cũ? |
| `replica_lag_seconds` | Migration ảnh hưởng replica |
| `app_p95_latency_ms` | Tác động end-user |

Tên metrics là gợi ý instrumentation, không phải metrics mặc định của MongoDB.

---

## 33. Rollback: khi nào có thể quay về app cũ?

### 33.1. Rollback code và rollback data khác nhau

Nếu V2 dual-write cả `full_name`/`display_name`, V1 vẫn đọc field cũ, có thể rollback code trong compatibility window **nếu** V1 không phá schema V2 và chưa xuất hiện enum/type khác.

Nếu đã xóa `full_name` trong contract phase, rollback V1 có thể làm app không đọc được khách hàng nữa.

### 33.2. Đánh dấu rollback boundary

~~~text
EXPAND:
  V1 rollback supported if writer compatibility preserved

MIGRATE:
  V1 rollback still supported, pending final sync,
  but must check any V2-only persisted features

CUTOVER:
  V1 rollback maybe not supported by policy

CONTRACT:
  V1 rollback unsupported unless reintroduced old shape
~~~

Đây là **kế hoạch cần xác nhận**, không phải mặc định mỗi hệ thống.

### 33.3. Roll forward có thể tốt hơn reverse migration

Nếu production V2 có lỗi nhỏ sau khi đã contract, triển khai V2.1 sửa lỗi có thể an toàn hơn rollback V1 và cố khôi phục schema cũ.

### 33.4. Không tự restore toàn cluster để đảo một field rename

Restore snapshot cũ có thể xóa các writes hợp lệ mới, ảnh hưởng orders/payments khác. Cần tính RPO/RTO, scope và business approval.

### 33.5. Lưu audit của từng pha

Ai bật feature flag, khi nào hết V1 writers, backfill run ID, source/target versions và kết quả reconciliation? Không có log này sẽ rất khó chọn rollback path.

---

## 34. Phát hành bằng feature flags

Có thể tách behavior của app V2:

| Flag | Chức năng |
|---|---|
| `customer_dual_read_enabled` | Đọc cả full_name và display_name |
| `customer_dual_write_enabled` | Ghi cả hai fields |
| `customer_prefer_new_name` | Chọn new canonical |
| `customer_new_field_required` | Không cho tạo document chỉ có old field |
| `customer_legacy_write_disabled` | Chặn source ghi old-only nếu routing hỗ trợ |

### 34.1. Không bật flag sai thứ tự

Nếu bật `prefer_new_name` trước khi final reconciliation, user có thể thấy tên cũ. Nếu bật `new_field_required` trong khi còn app V1 write, validator có thể từ chối yêu cầu cũ.

### 34.2. Flag phải có ownership

Ai bật? Theo metric nào? Rollback flag có an toàn sau khi đã bỏ field cũ chưa? Feature flag không tự giải quyết consistency.

### 34.3. Không giữ compatibility code vô thời hạn

Có chi phí mỗi lần query, nhiều indexes, code paths khó test và nguy cơ hai fields lệch. Đặt deadline cho contract, nhưng chỉ thực hiện sau khi đủ tiêu chí.

---

## 35. Online migrations khi triển khai rolling

Một rolling deploy có thời gian:

~~~text
10:00 App V1 phục vụ 100% traffic
10:05 App V2 canary 5%
10:15 App V2 50%, V1 50%
10:30 App V2 100% REST API
10:45 Background worker V1 vẫn chạy scheduled job
11:00 Worker V1 dừng hoàn toàn
11:15 Final reconciliation bắt đầu
~~~

Nếu đánh dấu “V1 đã dừng” lúc 10:30, ta bỏ sót worker tiếp tục ghi đến 11:00.

### 35.1. Deployment inventory

Theo dõi:

- Pod/container image digests.
- JVM build versions.
- Worker deployments.
- CronJobs/schedulers.
- CI scripts.
- External clients.
- Database users có quyền direct writes.
- Event consumers lagging.
- Offline clients/event replay.

### 35.2. Mixed reads và writes phải được kiểm thử

Chạy test đồng thời V1/V2 trên staging:

~~~text
V1 read V1 doc
V1 read transitional doc
V1 update transitional doc
V2 read V1 doc
V2 read transitional doc
V2 update V1 doc
V2 update transitional doc
V2 replace partial doc (phải bị cấm/được bảo vệ)
~~~

### 35.3. Canary cần quan sát lỗi âm thầm

Không chỉ HTTP 500. Theo dõi số records thiếu tên, fallback rate, mismatch count và search results.

---

## 36. Event-driven architecture và schema versioning

Có thể một service V2 vẫn cần phát events tương thích V1:

~~~json
{
  "event_type": "CustomerRenamed",
  "event_schema_version": 1,
  "customer_id": "CUS-101",
  "full_name": "Nguyễn An Mới"
}
~~~

V2 muốn:

~~~json
{
  "event_type": "CustomerRenamed",
  "event_schema_version": 2,
  "customer_id": "CUS-101",
  "display_name": "Nguyễn An Mới"
}
~~~

### 36.1. Không đổi payload và bắt mọi consumer hiểu ngay

Nếu broker giữ sự kiện cũ nhiều ngày hoặc consumers lag, payload V1 và V2 cùng tồn tại. Consumer mới phải chấp nhận những versions trong retention/replay window.

### 36.2. Các chiến lược

- Event V2 giữ legacy field trong một thời gian.
- Producer phát event theo versioned topic/event type riêng.
- Consumer adapter map cả hai sang canonical internal model.
- Schema registry/contract tests theo công nghệ sự kiện đang dùng.
- Outbox lưu event schema version độc lập document schema.

### 36.3. Replaying old events

Nếu backfill source lên V2 rồi replay event V1 với field cũ, consumer không được làm mất new-only fields hoặc downgrade document một cách âm thầm.

### 36.4. Ordering và idempotency

Event có stable ID và aggregate version giúp xử lý duplicates/out-of-order. Không mặc định “event đến cuối cùng” là mới nhất theo business time.

---

## 37. Materialized views, cache và downstream projections

Thay schema ở `customers` có thể ảnh hưởng:

- Search index lấy `full_name`.
- Collection tổng hợp `customerProfiles`.
- Redis cache chứa raw BSON/JSON.
- BI/warehouse extract queries.
- Export CSV.
- Change Stream projection workers.
- Audit/compliance report.

### 37.1. Cần migration cho read models

Nếu projection lưu `full_name`, một app V2 dùng `display_name` có thể không tìm thấy data; cần rebuild/recompute hoặc dual representation.

### 37.2. Cache invalidation

Nếu cache key/payload không có schema version, rollback/cutover có thể đọc stale payload dù MongoDB đã sửa. Có thể version cache namespace hoặc invalidate theo migration phase.

### 37.3. Không coi count source = count projection là đủ

Một profile có thể tồn tại ở cả hai collection nhưng displayName khác. Cần so values, checksums hoặc sampling theo business contract.

### 37.4. Search index lag

Sau khi đổi indexed fields, Search/Vector Search có thể cần rebuild/sync. API read readiness gồm search behaviors chứ không chỉ MongoDB CRUD.

---

## 38. Data migration và multi-tenant isolation

Một collection dùng chung nhiều tenant:

~~~javascript
{
  tenant_id: "tenant-a",
  full_name: "Nguyễn An"
}
~~~

### 38.1. Backfill phải giữ tenant

Nếu script chỉ update name fields trong cùng document, tenant ID thường không thay; tuy vậy khi split/merge collections hoặc build new document, phải giữ correct tenant ownership và tránh trộn dữ liệu.

### 38.2. Canary từng tenant

Có thể migrate một tenant thử trước để quan sát, nhưng tenant skew rất lớn. Cần chọn nhóm đại diện theo volume, document shapes và query patterns.

### 38.3. Authorization

Không lấy `tenant_id` từ một arbitrary user request để chạy migration. Chỉ admin jobs đã được phê duyệt, credentials hạn chế, audit và allowlist tenants.

### 38.4. Query scope

Nếu new reader dùng `$or` fallback mà đặt tenant filter sai nhánh logic, có thể vô tình đọc cross-tenant. Luôn test authorization khi thay query shape.

---

## 39. Sharded cluster và schema evolution

### 39.1. Shard key không phải field đổi tên tùy tiện

Nếu `tenant_id` là shard key, đổi nó sang `tenantId` không chỉ là rename thông thường; có thể ảnh hưởng query targeting, unique indexes, routing và sharding metadata. Cần procedure cụ thể cho shard key/resharding nếu thật sự cần thay.

### 39.2. Batching theo shard/tenant

Backfill across shards có thể gây network/merge overhead và load không đều. Query chứa shard key khi phù hợp giúp giới hạn scope, nhưng phải kiểm tra shard key thực tế và routing.

### 39.3. Feature/version gates

Một số aggregation update operators, transaction behaviors, time-series formats hoặc indexes phụ thuộc MongoDB Server/FCV. Document schema version V2 không đồng nghĩa server hiện tại hỗ trợ mọi pipeline migration.

### 39.4. Không chỉ kiểm thử standalone

Nếu production là sharded cluster có Change Streams, transactions và retryable writes, staging chỉ có local standalone sẽ không phản ánh đầy đủ operational risks.

---

## 40. Khi nào dùng collection mới thay vì cùng collection?

Có những thay đổi mà dual fields trong cùng document không hợp lý:

- Từ document khổng lồ sang nhiều documents.
- Thay tenant partition/ownership.
- Viết lại model với khóa định danh mới.
- Tách dữ liệu nhạy cảm thành collection có quyền khác.
- Tạo read model tính sẵn.
- Chuyển từ embedded array lớn sang riêng collection line items.

### 40.1. Migration sang collection mới

~~~text
customers_v1 (source)
       |
       +-- backfill -> customers_v2
       |
       +-- CDC/dual-write trong compatibility window
                           |
                           v
                    Validation/cutover
                           |
                           v
                       readers V2
~~~

### 40.2. Những câu hỏi phải giải quyết

- Canonical source là collection nào?
- Có thể nhận writes song song không?
- Stable business ID có giữ nguyên không?
- Data quá lớn cần backfill/copy bao lâu?
- Index/unique constraints ở target có hoạt động không?
- Delete/restore có đồng bộ không?
- Query migration và routing thực hiện lúc nào?
- Rollback trước và sau cutover khác nhau thế nào?

### 40.3. Dual-write sang hai collections không atomic mặc định

Hai separate writes có thể bị crash giữa chừng. Dùng transaction khi phù hợp hoặc outbox/CDC + reconciliation, không coi “cả hai cùng database” là đủ atomic.

---

## 41. Migrations ảnh hưởng backup và restore

### 41.1. Snapshot cũ có schema cũ

Nếu rollback/restore dữ liệu từ snapshot trước migration, App V2 phải còn đọc được V1 format hoặc có runbook re-backfill.

### 41.2. Snapshot mới có schema mới

Nếu rollback App V1 sau contract, nó có thể không đọc được snapshot data V2. Backup không giúp giải quyết compatibility trừ khi có data downgrade procedure.

### 41.3. RPO/RTO và business approval

Phục hồi toàn collection về trước migration có thể mất writes hợp lệ sau đó. Không dùng full rollback data như “undo schema” mà không tính data loss và consistency của các collections liên quan.

### 41.4. Backup keys và metadata

Khi migration đổi encryption hoặc unique indexes, restore phải có keys/index definitions tương ứng. Có thể cần test restore cả trước và sau cutover.

### 41.5. Restore drill

Trong staging:

1. Restore backup V1 vào target cách ly.
2. Chạy App V2 reader test.
3. Chạy backfill resume.
4. Chạy validator/index migration.
5. Thử rollback app khi còn legacy field.
6. Kiểm tra business invariants.

---

## 42. Runbook triển khai production

### Bước 1 — Định nghĩa contract

Ghi rõ V1/V2 BSON examples, required/optional fields, types, enum values, null/missing semantics và owners.

### Bước 2 — Lập inventory

Liệt kê mọi readers/writers/indexes/jobs/consumers/reports, cả các script vận hành và offline clients.

### Bước 3 — Phân tích rủi ro

Xác định full-document replacements, unique indexes, hot documents, shard key, validator, security scope và rollback window.

### Bước 4 — Baseline

Lấy counts/invalid documents/mismatch rates/latency/index stats, backup state, replication lag và current schema distribution.

### Bước 5 — Safety release

Loại bỏ writes nguy hiểm từ V1 như full replace làm mất unknown fields nếu chúng phá new schema.

### Bước 6 — Expand

Deploy app V2 dual-read và compatible write, chưa loại field cũ hoặc phát enum mới ngoài support range.

### Bước 7 — Canary

Chạy integration tests, kiểm tra fallback/mismatch, throughput và security khi hai app versions cùng tồn tại.

### Bước 8 — Backfill

Chạy migration batches có checkpoint, rate limit, idempotent filters và error quarantine.

### Bước 9 — Drain old writers

Ngừng toàn bộ job/pod/client còn ghi old-only; chờ in-flight writes hoàn thành và xác nhận bằng metrics/audit.

### Bước 10 — Final reconciliation

Sửa tất cả drift, kiểm tra records không thể migrate, counts và business invariants.

### Bước 11 — Switch read canonical

Chuyển reader dùng new field là nguồn chính, giữ dual-write tạm thời để bảo vệ rollback nếu policy yêu cầu.

### Bước 12 — Validator/index migration

Enforce contract V2 khi dữ liệu sẵn sàng, kiểm tra duplicate/unique constraints, query plans và downstream projections.

### Bước 13 — Contract

Sau rollback window và business sign-off, xóa legacy fields/code/indexes theo batch, không làm mất giá trị mới.

### Bước 14 — Postmortem/close

Lưu run IDs, checksums/metrics, incidents, performance delta và hướng dẫn để future upgrade đọc được documents còn tồn tại.

---

## 43. Test matrix cho V1/V2

### 43.1. Read compatibility

| Test | Kết quả mong muốn |
|---|---|
| V1 đọc V1 document | OK |
| V2 đọc V1 document | OK qua fallback |
| V1 đọc transitional document | OK |
| V2 đọc transitional document | OK, đúng precedence |
| V2 đọc new-only document | OK sau cutover |
| V1 đọc new-only document | Không được phép trong rollback window |
| V2 đọc field null/missing | Theo contract |
| V2 đọc sai BSON type | Báo data-quality, không tự sửa bừa |

### 43.2. Write compatibility

| Test | Kết quả mong muốn |
|---|---|
| V2 tạo customer mới trong mixed window | Cả hai fields |
| V2 đổi tên trong mixed window | Hai fields atomically bằng nhau |
| V1 đổi tên sau backfill | V2 reader vẫn trả tên đúng theo phase |
| V1 full replace unknown field | Phải chặn hoặc bảo vệ |
| V2 update bằng CAS bị stale | Detect conflict |
| V2 update record old-only | Không mất old field |
| Backfill chạy lại | Không ghi đè một new value hợp lệ |
| Backfill crash rồi resume | Không mất/nhân đôi dữ liệu |
| Validator bật warn | Log warnings và không chặn flow được thiết kế |
| Validator bật error | Chặn writes không tuân contract |

### 43.3. End-to-end

- Truy vấn theo tên và sort theo tên.
- Search index.
- Unique key/upsert.
- Events V1/V2.
- Offline clients.
- Transaction/order/payment invariants.
- Permission/tenant isolation.
- Backup/restore cả hai giai đoạn.
- Performance dưới concurrent traffic.

### 43.4. Failure injection

Thử worker crash giữa batch, network timeout sau update, duplicate events, old writer còn sót và rollback code trong mixed phase để tìm lỗi trước production.

---

## 44. Ví dụ làm rõ rollback bằng timeline

~~~text
Ngày 1:
  V1 đọc/ghi full_name
  V2 chưa phát hành

Ngày 2:
  Safety patch V1 ngừng full replace
  V2 dual-read; V2 dual-write

Ngày 3:
  Backfill display_name cho 80% records
  V1 và V2 cùng ghi

Ngày 4:
  V1 REST đã dừng, V1 scheduled worker vẫn chạy
  Không bật prefer-new

Ngày 5:
  Worker cũ dừng; final reconciliation hoàn tất
  V2 prefer display_name

Ngày 6:
  Giữ full_name phục vụ rollback window
  Monitoring discrepancy=0

Ngày 14:
  Kết thúc rollback window
  Contract: bỏ full_name, old index, old fallback
~~~

### 44.1. Nếu rollback ở Ngày 3

Có thể quay về V1 **nếu** new app chưa phát dữ liệu mới mà V1 không hiểu, và old field còn đầy đủ. Sau đó cần ngừng/đánh giá các workers đã tạo dữ liệu V2, chứ không chỉ thay container image.

### 44.2. Nếu rollback ở Ngày 14

V1 không còn đảm bảo hoạt động vì field cũ đã bị xóa. Phải roll forward hoặc có reverse migration được thiết kế riêng; không hứa rollback nhanh.

### 44.3. Không dùng ngày làm tiêu chí duy nhất

Timeline chỉ là ví dụ. Real gates phải dựa trên telemetry, data quality, consumer inventory và business approval.

---

## 45. Bài tập thực hành

### Bài 1 — Nhận diện schema

Cho ba documents: có `full_name`, có `display_name` và có cả hai. Xác định reader V1/V2 trả kết quả gì theo từng giai đoạn.

### Bài 2 — Ma trận tương thích

Tạo bảng 2×2 gồm App V1/V2 × Document V1/V2; đánh dấu đọc, ghi, full replace có an toàn không.

### Bài 3 — Dual-read

Viết Java method lấy customer name từ hai fields. Cho biết precedence khi old writer vẫn hoạt động và sau final reconciliation.

### Bài 4 — Dual-write

Dùng `MongoTemplate.updateFirst` set `full_name` và `display_name` trong cùng một operation, với filter tenant+ID.

### Bài 5 — Null/missing

Tạo documents: missing, null, empty, string cho `display_name`. So sánh `$exists`, `$type` và `$ifNull`.

### Bài 6 — Schema version

Định nghĩa semantics `schema_version`=1,2,3 cho quá trình rename; giải thích vì sao khác `@Version`.

### Bài 7 — Backfill

Tạo 10.000 documents V1; dùng batch update pipeline copy `full_name` sang `display_name`.

### Bài 8 — Idempotency

Chạy backfill hai lần, xác nhận không overwrite field mới được ghi hợp lệ khi filter `display_name` missing.

### Bài 9 — Race condition

Một worker V1 sửa `full_name` sau backfill. Chứng minh vì sao V2 reader ưu tiên `display_name` có thể stale.

### Bài 10 — CAS

Viết update filter dùng expected `full_name` và new field missing; chứng minh khi tên thay đổi đồng thời thì update không match.

### Bài 11 — Final sync

Giả định old field canonical trong mixed window. Viết query tìm discrepancies và kế hoạch sửa sau khi V1 writers đã dừng.

### Bài 12 — Full replace

Mô phỏng app V1 đọc/replace document có `display_name`; quan sát field mới biến mất. Chuyển thành field-level `$set`.

### Bài 13 — Validator

Tạo validator warn cho old/new documents; sau backfill mới enforce V2 contract bằng `$jsonSchema`.

### Bài 14 — Index migration

Tạo indexes cho `full_name` và `display_name`. Thử query plans trước/sau backfill; xác định thời điểm drop legacy index.

### Bài 15 — Unique constraint

Đổi email normalization, phát hiện duplicate keys khi chuẩn hóa; đề xuất partial unique index và quy trình repair.

### Bài 16 — Enum version

Thêm status `PARTIALLY_REFUNDED`. Thiết kế reader-first, writer-later rollout để V1 không lỗi.

### Bài 17 — Numeric types

Đổi `amount_string` sang `amount_minor` Int64. Xử lý invalid strings/overflow và test precision.

### Bài 18 — Nested document

Đổi `shipping_address:string` thành `shipping_address_v2:object`; xác định dữ liệu không thể parse tự động.

### Bài 19 — Embedded → reference

Tách addresses ra collection riêng với stable IDs. Thiết kế dual-read, write ownership và reconciliation.

### Bài 20 — CDC

Dùng Change Streams/outbox để đồng bộ fields; mô tả retry, ordering, lag và bootstrap sau history loss.

### Bài 21 — Sharding

Nếu tenant_id là shard key, nêu vì sao không thể coi rename thành tenantId là migration field thông thường.

### Bài 22 — Multi-tenant

Migrate theo tenant cohorts. Thiết kế tenant isolation trong backfill, API query và monitoring.

### Bài 23 — Rollback

V2 đã xóa `full_name`. Phân tích vì sao rollback App V1 không an toàn và chọn roll-forward/reverse migration.

### Bài 24 — Contract tests

Viết tests cho V1/V2 applications đọc/ghi V1/transitional documents, plus raw BSON field assertions.

### Bài 25 — Restore drill

Restore snapshot cũ chứa V1 schema rồi chạy V2. Chứng minh app đọc được và backfill có thể resume.

### Bài 26 — Observability

Thiết kế dashboard gồm remaining V1 documents, fallback rate, mismatch count, old writer rate và replication lag.

### Bài 27 — Migration job lỗi

Simulate crash sau khi ghi batch nhưng trước khi lưu checkpoint. Giải thích vì sao cần idempotency.

### Bài 28 — Partial backfill

Một tenant chỉ mới được migrate 40%, V2 search theo display_name. Phân tích khả năng bỏ sót, hướng query fallback hoặc feature gating.

### Bài 29 — Schema validator strict

Một document có `schema_version:NumberLong("2")` nhưng validator đòi BSON Int32. Phân tích lỗi và cách thống nhất types.

### Bài 30 — Thiết kế đầy đủ

Lập kế hoạch expand–migrate–contract cho một hệ thống có Java API, scheduled worker, Kafka consumer, Atlas Search và BI report. Nêu test gates, rollback boundary và business sign-off.

---

## 46. Câu hỏi ôn tập

1. Tại sao MongoDB linh hoạt schema không có nghĩa ứng dụng cũ/mới tự tương thích?
2. Document schema version khác application version thế nào?
3. FCV của MongoDB khác `schema_version` ra sao?
4. API version và event schema version có phải bằng document version không?
5. Backward compatibility trong data layer là gì?
6. Forward compatibility trong data layer là gì?
7. Vì sao write compatibility quan trọng không kém read compatibility?
8. Mixed-version deployment gồm những writers nào ngoài REST API?
9. Có nên thêm `schema_version` cho mọi collection không?
10. Vì sao schema marker không thay schema validation?
11. Optimistic version khác schema version ra sao?
12. Có thể chỉ đổi `@Field` để migrate BSON field không?
13. Expand–migrate–contract gồm những pha nào?
14. Pha nào phải chuẩn bị rollback trước khi thay dữ liệu?
15. Vì sao không `$rename` ngay khi app V1 đang chạy?
16. Dual-read và dual-write khác nhau ra sao?
17. Dual-write có tự đồng bộ writers V1 không?
18. Tại sao reader V2 có thể phải ưu tiên old field trong mixed window?
19. Khi nào an toàn đổi reader ưu tiên new field?
20. Vì sao final reconciliation phải đợi old writers dừng?
21. Cần xử lý `missing` và `null` khác nhau thế nào?
22. BSON number và string dùng trong cùng field gây rủi ro gì?
23. Enum value mới có thể làm V1 lỗi thế nào?
24. Vì sao nested object migration cần data-quality policy?
25. Full-document replacement của V1 gây mất field V2 thế nào?
26. `@Version` có bảo vệ nếu raw writer cũ không tăng version không?
27. Backfill bằng aggregation update khác classic `$set` thế nào?
28. Vì sao batch migration cần checkpoint?
29. Vì sao vẫn cần reconciliation sau khi scan hết `_id`?
30. Conditional update với expected field value giúp tránh race thế nào?
31. Khi nào chọn validator `warn`?
32. Khi nào chuyển sang `validationAction:"error"`?
33. `validationLevel:"moderate"` khác strict ở đâu?
34. MongoDB validator có tự đổi documents cũ không?
35. Vì sao tạo new index không đồng nghĩa backfill đã xong?
36. Những điều kiện nào cho phép drop legacy index?
37. Partial unique index có bảo vệ các records ngoài filter không?
38. Change Stream có tự bảo đảm exactly-once không?
39. Làm sao xử lý old event khi replay vào dữ liệu V2?
40. Vì sao cached/derived projections phải tham gia schema migration?
41. Shard key rename có khác ordinary field rename không?
42. Tại sao transaction không tự giải quyết external broker consistency?
43. Rollback code khác rollback data thế nào?
44. Contract phase làm rollback V1 khó ra sao?
45. Những metrics nào chứng minh không còn phụ thuộc schema cũ?
46. Vì sao should not use duration alone làm contract gate?
47. Integration tests cần cover những cặp app/document versions nào?
48. Những invalid documents nào phải quarantine thay vì tự chuyển?
49. Cần giữ backup snapshots và restore drill như thế nào trong migration?
50. Một migration hoàn tất về số lượng nhưng vẫn có fallback rate cao có được coi là done không?

---

## 47. Tổng kết

**Tiến hóa schema trong MongoDB là bài toán tương thích giữa các producers, consumers và dữ liệu đang tồn tại qua thời gian.** Database không ép mọi document cùng shape, nhưng application code, indexes, validators và external systems vẫn dựa vào một data contract.

Các nguyên tắc quan trọng nhất:

1. **Tách các loại version**: application, document, event, API, MongoDB Server và FCV không phải một.
2. **Xây ma trận read/write** giữa App V1/V2 và Document V1/V2; kiểm tra cả full replacement.
3. **Expand → migrate → contract** thay vì đổi field, dữ liệu, index và validator trong một release.
4. **Dual-read chưa đủ** nếu old writer vẫn cập nhật old field sau khi new field được backfill; cần canonical precedence và final reconciliation.
5. **Dual-write một document atomically** giúp giảm divergence của V2 writes, nhưng không kiểm soát V1 old-only writes.
6. **Backfill có checkpoint, idempotency, rate limit, conflict handling và repair path**; không coi scan xong là đủ.
7. **Schema version không phải optimistic lock version** và không thay validator.
8. **Indexes, validators, Search, caches, reports, event consumers và tenant security** đều là phần của migration.
9. **Rollback boundary phải được thiết kế trước contract**, vì dữ liệu V2 có thể không còn đọc được bởi V1.
10. **Hoàn tất migration phải có bằng chứng**: no old writers, no unresolved mismatches, low/zero fallback theo policy, business invariants đúng và restore path được kiểm chứng.

Khi thiết kế một thay đổi nhỏ như `full_name → display_name`, câu hỏi không chỉ là “Java class mới đã dùng tên field nào?” mà là: **Trong lúc cả app cũ và mới cùng chạy, ai là nguồn ghi đúng, reader nào còn phụ thuộc schema cũ, dữ liệu có thể được khôi phục thế nào và điều kiện nào cho phép xóa legacy field mà không mất khả năng rollback?**

## Tài liệu tham khảo

- [MongoDB Manual — Data Model Design](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/)
- [MongoDB Manual — Specify Validation Level for Existing Documents](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/)
- [MongoDB Manual — Specify Validation Action](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-action/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [MongoDB Manual — Updates with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — $rename](https://www.mongodb.com/docs/manual/reference/operator/update/rename/)
- [MongoDB Manual — $ifNull](https://www.mongodb.com/docs/manual/reference/operator/aggregation/ifNull/)
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — Template CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking)
- [MongoDB Java Sync Driver — Read Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)

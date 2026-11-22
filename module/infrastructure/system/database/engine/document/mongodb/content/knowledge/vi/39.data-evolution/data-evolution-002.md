# Thêm, đổi tên, bỏ trường theo quy trình triển khai nhiều giai đoạn trong MongoDB

Trong MongoDB, mỗi document không bắt buộc có cùng một tập field. Một collection có thể đồng thời chứa document cũ với trường **name** và document mới với trường **displayName**. Tính linh hoạt này giúp hệ thống phát triển nhanh, nhưng cũng tạo ra một rủi ro vận hành: **nếu ứng dụng đang chạy ở nhiều phiên bản mà schema thay đổi quá sớm, một phần hệ thống có thể đọc sai, ghi thiếu, mất dữ liệu hoặc không thể rollback**.

Ví dụ nhóm phát triển muốn thực hiện ba thay đổi trên collection **customers**:

- **Thêm** field **preferredLocale** để lưu ngôn ngữ hiển thị.
- **Đổi tên** field **name** thành **displayName**.
- **Bỏ** field **legacyTag** không còn được dùng.

Một migration kiểu:

~~~javascript
db.customers.updateMany({}, { $rename: { name: "displayName" } });
db.customers.updateMany({}, { $set: { preferredLocale: "vi-VN" } });
db.customers.updateMany({}, { $unset: { legacyTag: "" } });
~~~

có thể chạy được ở một môi trường đơn giản nhưng **không an toàn để mặc định chạy ngay trên production** khi vẫn còn service cũ tìm theo **name**, writer cũ tiếp tục ghi **name**, nhiều workers xử lý bất đồng bộ hoặc validator/index đang dựa vào schema cũ.

Thay vì “đổi field một lần”, phương án thường được chọn là **expand → migrate → contract**:

~~~text
Schema cũ
   |
   v
EXPAND
 Ứng dụng đọc được cũ + mới
 Writer chuyển tiếp có thể ghi hai field
   |
   v
MIGRATE
 Backfill dữ liệu lịch sử
 Kiểm soát writers cũ, đối soát dữ liệu
   |
   v
SWITCH
 Ứng dụng dùng field mới làm nguồn chính
 Theo dõi và giữ rollback window thích hợp
   |
   v
CONTRACT
 Ngừng phụ thuộc field cũ
 Xóa field/index/schema validation cũ
   |
   v
Schema mới
~~~

Bài học này hướng dẫn cách thiết kế và vận hành từng giai đoạn, có ví dụ **mongosh**, **MongoDB Java Driver**, **Spring Data MongoDB**, checklist kiểm thử, giám sát, rollback và bài tập tình huống.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **thay đổi schema logic ở ứng dụng** và **thay đổi dữ liệu vật lý trong MongoDB**.
2. Thiết kế **compatibility contract** giữa old reader, new reader, old writer và new writer.
3. Thực hiện **add field** bằng default policy, optional reads và backfill có điều kiện.
4. Thực hiện **rename field** qua giai đoạn dual-read/dual-write thay vì chạy **$rename** quá sớm.
5. **Drop field** khi đã chứng minh không còn dependencies và hết rollback window phù hợp.
6. Viết migration theo lô **idempotent**, giới hạn tải và không ghi đè bản cập nhật mới.
7. Dùng **$set**, **$unset**, **$rename**, aggregation pipeline update và **bulkWrite** đúng ngữ nghĩa.
8. Điều chỉnh indexes, validators, unique constraints và schema serialization theo đúng thứ tự.
9. Phối hợp với **Java/Spring Data MongoDB**, các phiên bản service, CDC/change streams và job nền.
10. Kiểm tra và vận hành schema evolution khi deploy nhiều replicas, rollback hoặc traffic thay đổi.

**Phạm vi:** MongoDB document collections và các API thường gặp trong Java/Spring Data. Ví dụ dùng database thử nghiệm riêng, không tự động áp dụng vào production. Tính năng cụ thể (như update dùng aggregation pipeline, change streams hay validator settings) cần đối chiếu MongoDB server version và driver version thực tế.

## 2. Vì sao MongoDB vẫn cần schema migration?

MongoDB không yêu cầu các document trong cùng collection có cùng cấu trúc. Chẳng hạn:

~~~javascript
{
  _id: "C-101",
  tenantId: "T-A",
  name: "An",
  legacyTag: "old-import"
}
~~~

và:

~~~javascript
{
  _id: "C-102",
  tenantId: "T-A",
  displayName: "Bình",
  preferredLocale: "vi-VN"
}
~~~

đều có thể tồn tại trong một collection không áp dụng validator chặt. Nhưng:

- Một Java class chỉ khai báo **name** có thể đọc **displayName** thành null.
- Một báo cáo group theo **name** sẽ không tìm thấy field đã đổi.
- Một unique index hoặc filter có thể hoạt động khác khi field bị missing.
- Một REST API có thể trả field cũ cho client cũ, field mới cho client mới.
- Một background worker cũ có thể **ghi name trở lại** sau khi batch migration đã đổi sang displayName.
- Một schema validator có thể từ chối writes từ code cũ.

**Schema không chỉ là cấu trúc trong database.** Nó còn là hợp đồng giữa tất cả readers, writers, indexes, validators, events, API responses và jobs có liên quan.

### 2.1. Schema vật lý và schema logic

**Schema vật lý** là những fields BSON đang lưu trong documents:

~~~text
customer.name
customer.displayName
customer.preferredLocale
customer.legacyTag
~~~

**Schema logic** là cách ứng dụng diễn giải thông tin:

~~~text
Tên hiển thị chính thức của khách hàng = ?
Ngôn ngữ mặc định có ý nghĩa gì?
Ai có quyền thay tên?
Khi name và displayName khác nhau thì chọn cái nào?
~~~

Một migration có thể **đúng cú pháp** nhưng sai nghiệp vụ nếu không định nghĩa logic này.

### 2.2. Bốn chủ thể cần xét

| Thành phần | Ví dụ | Rủi ro nếu đổi field đột ngột |
|---|---|---|
| Old reader | API bản A đọc name | Trả null sau khi chỉ còn displayName |
| New reader | API bản B đọc displayName | Không thấy document chưa backfill |
| Old writer | Consumer bản A cập nhật name | Tạo lại field cũ hoặc làm displayName cũ |
| New writer | Service bản B ghi displayName | Old reader không thấy lần cập nhật mới |

Trong rolling deployment, **tất cả bốn kiểu có thể cùng tồn tại** trong một khoảng thời gian. Không được giả định deploy mới là mọi process cũ đã biến mất ngay lập tức.

## 3. Case study xuyên suốt

Collection **app_lab.customers** có dữ liệu:

~~~javascript
use app_lab

db.customers.insertMany([
  {
    _id: "C-101",
    tenantId: "T-A",
    name: "An",
    legacyTag: "import-2024",
    updatedAt: ISODate("2026-10-01T00:00:00Z")
  },
  {
    _id: "C-102",
    tenantId: "T-A",
    name: "Bình",
    legacyTag: "import-2024",
    updatedAt: ISODate("2026-10-02T00:00:00Z")
  },
  {
    _id: "C-103",
    tenantId: "T-B",
    name: "Chi",
    legacyTag: "import-2025",
    updatedAt: ISODate("2026-10-03T00:00:00Z")
  }
]);
~~~

Đây là dữ liệu **giả lập**, không chứa hồ sơ khách hàng thật. Chỉ chạy một lần trên collection thử nghiệm sạch; **_id** cố định khiến chạy lại insertMany có thể gặp duplicate key.

### 3.1. Mục tiêu cuối

~~~javascript
{
  _id: "C-101",
  tenantId: "T-A",
  displayName: "An",
  preferredLocale: "vi-VN",
  updatedAt: ISODate("2026-10-01T00:00:00Z")
}
~~~

Kết quả mong muốn:

- **displayName** thay thế hoàn toàn **name**.
- **preferredLocale** có chính sách mặc định rõ ràng, ví dụ **vi-VN** khi nghiệp vụ cho phép.
- **legacyTag** không còn trong documents mới/cũ.
- Không làm mất cập nhật tên xảy ra **trong lúc migration**.
- Các service vẫn hoạt động khi rolling deployment và có kế hoạch rollback từng bước.

### 3.2. Những giả định cần công khai

Để ví dụ dễ hiểu:

- **name** vốn là String có ý nghĩa tên hiển thị.
- **displayName** mới cũng là String, **cùng ý nghĩa nghiệp vụ** với name trong quá trình chuyển đổi.
- **preferredLocale** được phép có default **vi-VN** theo policy của bài lab; production phải quyết định default phù hợp từng tenant/user.
- **legacyTag** không còn cần phục vụ nghiệp vụ, nhưng chỉ xóa sau khi hoàn tất kiểm kê phụ thuộc và đáp ứng retention policy.
- Có nhiều API instances và background consumers, nên **old writers có thể tồn tại** trong quá trình rolling deployment.

Không biến các giả định của bài lab thành quy tắc chung: **rename không phải lúc nào cũng đồng nghĩa giá trị giữ nguyên**. Nếu field mới thay đổi cả ý nghĩa/đơn vị (ví dụ giá trước thuế thành giá sau thuế), cần migration có transformation riêng.

## 4. Expand – Migrate – Contract

Mỗi giai đoạn có một mục tiêu và một điều kiện hoàn tất.

| Giai đoạn | Database có thể chứa | Reader | Writer | Mục tiêu |
|---|---|---|---|---|
| Trước thay đổi | name, legacyTag | name | name | Baseline |
| Expand 1 | name, displayName?, preferredLocale? | name-first, fallback new | old hoặc dual-write | Giữ tương thích với old deployment |
| Expand 2 | name, displayName, preferredLocale? | hỗ trợ cả hai | tất cả writers đã dual-write | Chấm dứt old-only writers |
| Migrate | mixed data, tiến tới full new fields | vẫn tương thích | dual-write | Backfill và đối soát |
| Switch | cả hai field, giá trị đồng bộ | displayName-first, fallback name | dual-write | Chuyển nguồn đọc chính |
| Contract chuẩn bị | còn name và new fields | new-only | new-only | Hết phụ thuộc cũ |
| Contract dữ liệu | chỉ new fields | new-only | new-only | Bỏ name/legacyTag và index cũ |

Dấu **?** nghĩa field có thể **chưa tồn tại**. Trong giai đoạn mixed schema, application phải xử lý cả hai trạng thái.

### 4.1. Vì sao tách expand và switch?

Trong khi old writer còn hoạt động:

~~~text
T0: name="An", displayName="An"
T1: old writer cập nhật name="An Mới"
T2: displayName vẫn "An" (stale)
~~~

Nếu new reader **ưu tiên displayName quá sớm**, nó đọc giá trị cũ. Trong giai đoạn còn old-only writer, có thể cần tạm chọn **name làm nguồn chính** hoặc dùng một cơ chế đồng bộ có bảo đảm riêng. Sau khi old-only writers đã rút hết và đối soát hoàn chỉnh, mới chuyển sang **displayName-first**.

### 4.2. Backfill không phải một nút bấm

Backfill trên hàng triệu documents có thể chạy lâu và trong lúc đó:

- Users cập nhật hồ sơ.
- App vẫn tạo document mới.
- Consumers xử lý messages bị trễ.
- Jobs định kỳ chạy.
- Replicas có phiên bản ứng dụng khác nhau.

Do đó migration cần **idempotence, điều kiện update tại thời điểm ghi, checkpoint và khả năng chạy lại**. Không chỉ duyệt danh sách IDs rồi ghi đè mù quáng bằng dữ liệu snapshot cũ.

### 4.3. Contract là bước phá tương thích

Xóa field cũ, ngừng dual-write hoặc sửa validator thành **require displayName** có thể khiến rollback về phiên bản ứng dụng cũ **không còn an toàn**. Vì vậy những bước này phải có gate/cửa sổ quan sát và kế hoạch phục hồi riêng.

## 5. Bước chuẩn bị: kiểm kê toàn bộ nơi đọc và ghi field

Trước khi chạy **$set**, **$rename** hoặc **$unset**, hãy liệt kê dependencies:

| Nhóm thành phần | Câu hỏi cần xác minh |
|---|---|
| REST/GraphQL APIs | Request/response DTO nào còn field name? |
| Java/Spring Data entities | @Field, constructor, mapper nào còn trỏ name? |
| Batch jobs | Job nào đọc/ghi/ghi lại toàn bộ document? |
| Consumers | Consumer dùng schema message cũ hay mới? |
| Aggregation/report | Có group/project/sort theo name không? |
| MongoDB indexes | Index/unique/partial/TTL nào liên quan? |
| Validators | $jsonSchema required/properties còn field cũ không? |
| CDC/change streams | Downstream có tiêu thụ change payload cũ? |
| Exports/ETL | Data warehouse/search index có ánh xạ name không? |
| Search/filter | UI còn search name, sort name, collation? |
| Permissions | Field-level policy còn tên field cũ không? |
| Backup/restore | Rollback có yêu cầu giữ giá trị cũ không? |

**Tất cả các writers** bao gồm services, cron jobs, ad-hoc scripts, data repair tools và integration adapters. Nếu một script chạy mỗi cuối tháng vẫn dùng **name**, migration hoàn tất giữa tháng có thể bị phá vỡ ở lần chạy tiếp theo.

### 5.1. Tạo bảng version compatibility

| Thành phần | V1 (cũ) | V2 (chuyển tiếp) | V3 (cuối) |
|---|---|---|---|
| Reader | name-only | đọc name và displayName | displayName-only |
| Writer | ghi name | ghi đồng thời name/displayName | ghi displayName |
| Locale | không biết preferredLocale | fallback và ghi field mới | yêu cầu preferredLocale |
| legacyTag | có thể đọc | bỏ phụ thuộc | không còn dùng |
| Rollback | V1 | V1 còn cần name | V1 không còn an toàn sau contract |

Các version labels là **mốc kế hoạch triển khai**, không bắt buộc trùng semantic version của codebase.

### 5.2. Đo baseline trước migration

~~~javascript
db.customers.countDocuments({ name: { $exists: true } });
db.customers.countDocuments({ displayName: { $exists: true } });
db.customers.countDocuments({ preferredLocale: { $exists: true } });
db.customers.countDocuments({ legacyTag: { $exists: true } });
~~~

Các phép **countDocuments** có thể tốn tài nguyên trên collection lớn, đặc biệt với **$exists** và index không phù hợp. Trên production cần hạn chế tần suất, kiểm tra query plan hoặc dùng monitoring/counters có kiểm soát.

Đếm field **tồn tại** khác đếm field **có giá trị hợp lệ**. Ví dụ **displayName: null** vẫn thỏa **$exists: true**.

### 5.3. Phát hiện dữ liệu bất thường

~~~javascript
db.customers.find(
  {
    name: {
      $exists: true,
      $not: { $type: "string" }
    }
  },
  { _id: 1, name: 1 }
).limit(20);
~~~

Nếu có null/Number/array thay vì String, không nên sao chép mù sang displayName. Cần chính sách làm sạch dữ liệu và ghi lại các bản ghi không chuyển được.

### 5.4. Có được phép thay default không?

Giá trị **preferredLocale: "vi-VN"** là quyết định nghiệp vụ, không phải giá trị MongoDB tự chọn. Có thể cần default theo tenant, account, user preference hoặc giá trị UNKNOWN.

Migration không nên tự gán **vi-VN** cho mọi người nếu điều đó làm sai trải nghiệm hoặc policy lưu trữ.

## 6. Thêm field mới: tương thích từ reader đến writer

Thêm field thường ít rủi ro hơn rename/drop nhưng không hoàn toàn vô hại.

### 6.1. Giai đoạn A — reader chấp nhận field missing

Ứng dụng V2 nên có policy fallback:

~~~text
Nếu preferredLocale hợp lệ -> sử dụng.
Nếu missing -> áp dụng default được business phê duyệt.
Nếu kiểu dữ liệu sai -> ghi nhận lỗi dữ liệu, không âm thầm giả định.
~~~

Ví dụ Java:

~~~java
import org.bson.Document;

public final class CustomerLocalePolicy {
    private CustomerLocalePolicy() {}

    public static String resolveLocale(
            Document customer,
            String approvedDefaultLocale) {
        Object raw = customer.get("preferredLocale");
        if (raw == null) {
            return approvedDefaultLocale;
        }
        if (raw instanceof String value && !value.isBlank()) {
            return value;
        }
        throw new IllegalStateException(
                "Invalid preferredLocale BSON value");
    }
}
~~~

Ví dụ coi **missing/null** cùng nhánh default. Nếu null có ý nghĩa khác missing, cần kiểm tra **containsKey** hoặc truy vấn riêng.

### 6.2. Giai đoạn B — mọi new write có field mới

~~~javascript
db.customers.insertOne({
  _id: "C-104",
  tenantId: "T-A",
  name: "Dung",
  displayName: "Dung",
  preferredLocale: "vi-VN"
});
~~~

Vẫn ghi cả **name** và **displayName** do đang giữ tương thích với old readers.

### 6.3. Giai đoạn C — backfill field thiếu

Nếu **vi-VN** được nghiệp vụ chấp thuận:

~~~javascript
db.customers.updateMany(
  { preferredLocale: { $exists: false } },
  { $set: { preferredLocale: "vi-VN" } }
);
~~~

Điều kiện **$exists: false** bảo vệ user đã tự chọn preferredLocale khỏi bị ghi đè. Không chạy:

~~~javascript
// Nguy hiểm: ghi đè lựa chọn của mọi user.
db.customers.updateMany(
  {},
  { $set: { preferredLocale: "vi-VN" } }
);
~~~

### 6.4. Missing và null khác nhau

~~~javascript
{ _id: "C-201", preferredLocale: null }
{ _id: "C-202" }
~~~

**$exists: false** chỉ match document không có field. Nếu business coi null là chưa gán, có thể thực hiện bước riêng:

~~~javascript
db.customers.updateMany(
  { preferredLocale: { $type: "null" } },
  { $set: { preferredLocale: "vi-VN" } }
);
~~~

Không gộp null và missing nếu **null** có ý nghĩa có chủ đích, chẳng hạn user chưa muốn chọn ngôn ngữ.

### 6.5. Khi nào require field mới?

Chỉ bật validator **required: ["preferredLocale"]** sau khi:

1. Tất cả writers ghi field mới.
2. Backfill hoàn tất hoặc có policy cho legacy documents.
3. Replacement/upsert paths được kiểm tra.
4. Validator đã được thử trên dữ liệu đại diện.
5. Có kế hoạch rollback khi writes bị chặn.

Nếu yêu cầu field quá sớm, writer cũ hoặc replaceOne có thể bị từ chối.

## 7. Đổi tên field: vì sao không làm bằng một lệnh ngay?

MongoDB hỗ trợ:

~~~javascript
db.customers.updateMany(
  {},
  { $rename: { name: "displayName" } }
);
~~~

Nhưng trong rolling deployment:

~~~text
T0: Document có name
T1: MongoDB $rename name -> displayName
T2: Old API GET chỉ đọc name -> null
T3: Old worker ghi name mới vào document
T4: New API GET chỉ đọc displayName -> giá trị cũ
~~~

**Thành công của $rename không chứng minh hệ thống đã migrate an toàn.** Một cách ít rủi ro hơn là copy field mới, vận hành tương thích rồi mới xóa field cũ.

### 7.1. Rename có thay đổi ý nghĩa giá trị không?

Nếu chỉ đổi **name** thành **displayName** và ngữ nghĩa không đổi, backfill có thể copy nguyên String.

Nếu đổi:

~~~text
old field: amountCents
new field: amount
~~~

thì cần biết **amount** lưu đơn vị cent hay đơn vị tiền lớn. Nếu đổi đơn vị, migration cần chuyển đổi số học và kiểm thử precision/overflow, không chỉ rename.

### 7.2. Quy tắc nguồn chính qua các pha

Khi old-only writer còn hoạt động:

~~~text
Canonical value = name
displayName là bản sao chuyển tiếp
~~~

Khi chắc chắn old-only writers đã rút hết và dữ liệu được đối soát:

~~~text
Canonical value = displayName
name giữ tạm để phục vụ rollback
~~~

Không cho reader chọn ngẫu nhiên khi hai giá trị khác nhau. Mỗi pha cần một **quy tắc nguồn chính** rõ ràng.

## 8. Dual-read: đọc được cả hai schema

Một reader có thể dùng policy khác nhau theo phase:

~~~java
import org.bson.Document;

public final class CustomerNameReader {
    private CustomerNameReader() {}

    public static String beforeCutover(Document customer) {
        String oldName = customer.getString("name");
        if (oldName != null && !oldName.isBlank()) {
            return oldName;
        }
        return customer.getString("displayName");
    }

    public static String afterCutover(Document customer) {
        String newName = customer.getString("displayName");
        if (newName != null && !newName.isBlank()) {
            return newName;
        }
        return customer.getString("name");
    }
}
~~~

**Hai phương thức khác nhau về ưu tiên.** Không dùng afterCutover trong pha old-only writers còn tồn tại nếu chưa có cơ chế đồng bộ bảo đảm.

### 8.1. Fallback phải có telemetry

Một fallback tồn tại vĩnh viễn có thể che giấu documents chưa migrate và drift giữa hai fields. Nên theo dõi counters **không chứa PII**:

~~~text
customer_name_legacy_fallback_total
customer_name_conflicting_values_total
customer_name_missing_both_total
~~~

Phân nhóm theo application version và scope phù hợp; tránh labels là customer ID/email làm tăng cardinality metrics và rò rỉ dữ liệu.

### 8.2. Database schema và API contract là hai lớp khác nhau

Trong database còn cả name/displayName, API có thể trả:

~~~javascript
{
  customerId: "C-101",
  displayName: "An"
}
~~~

hoặc cùng lúc hỗ trợ hai tên API trong một giai đoạn deprecation. Không expose nguyên BSON Document ra REST chỉ vì cần tương thích. Nếu external clients còn dùng thuộc tính **name**, phải version/deprecate **API contract** độc lập với migration nội bộ.

### 8.3. Query trên mixed schema

Trong pha tìm trên cả hai field:

~~~javascript
db.customers.find({
  tenantId: "T-A",
  $or: [
    { name: "An" },
    { displayName: "An" }
  ]
});
~~~

Truy vấn này giúp không bỏ sót record, nhưng có thể tìm cả document **đã drift** (name khác displayName). Nó không xác định chính xác tên nào hiện là nguồn chính; với dữ liệu lớn cần kế hoạch index riêng cho mỗi nhánh hoặc một giai đoạn search cutover có kiểm soát.

### 8.4. Projection để tránh dữ liệu thiếu

Trong query đọc document, cần include cả hai fields cho đến khi rollback/fallback không còn cần:

~~~javascript
db.customers.find(
  { tenantId: "T-A" },
  {
    _id: 1,
    tenantId: 1,
    name: 1,
    displayName: 1,
    preferredLocale: 1
  }
);
~~~

Nếu projection chỉ lấy displayName nhưng code cố fallback sang name, fallback **sẽ không bao giờ hoạt động** dù field name tồn tại trong database.

## 9. Dual-write: ghi hai field trong một thao tác

Khi new service ghi giá trị tên, nó có thể thực hiện:

~~~javascript
db.customers.updateOne(
  { _id: "C-101", tenantId: "T-A" },
  {
    $set: {
      name: "An Mới",
      displayName: "An Mới",
      updatedAt: new Date()
    }
  }
);
~~~

Trong **một document**, updateOne với cùng operator update cập nhật hai field **atomically** theo MongoDB single-document atomicity. Các readers sẽ không thấy trạng thái trung gian của **chính lệnh cập nhật đó**.

### 9.1. Không tách thành hai updateOne khi có thể tránh

Không tốt:

~~~javascript
db.customers.updateOne(
  { _id: "C-101" },
  { $set: { name: "An Mới" } }
);

db.customers.updateOne(
  { _id: "C-101" },
  { $set: { displayName: "An Mới" } }
);
~~~

Giữa hai lệnh, service có thể crash, network lỗi hoặc reader thấy dữ liệu chưa đồng bộ. Ghi cả hai field trong **một updateOne** cho cùng document là đơn giản hơn. Điều này **không** biến nhiều updates trên nhiều documents thành một transaction tự động.

### 9.2. Old writer vẫn là rủi ro

New writer ghi đôi không ngăn được old writer ghi riêng **name**:

~~~text
New writer: set name=A, displayName=A
Old writer: set name=B
Result: name=B, displayName=A
~~~

Do đó trước cutover cần chứng minh **không còn old-only writers** hoặc có cơ chế đồng bộ/cấm ghi cũ đáng tin cậy. Không chỉ trông chờ backfill chạy một lần.

### 9.3. Khi rollback bị kéo dài

Nếu đội vận hành muốn quay về V1 trong nhiều tuần, có thể phải **duy trì dual-write** lâu hơn. Khi đó:

- Tốn thêm storage và chi phí ghi.
- Cần reconciliation định kỳ.
- Phải phát hiện old-only writes.
- Không được xóa field name sớm.

Một lựa chọn khác là chốt ngày hết rollback V1 sau khi hệ thống V2/V3 ổn định. Đây là một quyết định sản phẩm/vận hành chứ không chỉ kỹ thuật.

## 10. Chặn lost updates bằng điều kiện version

Khi user cập nhật cùng hồ sơ đồng thời, dùng version hoặc một concurrency control phù hợp.

Document:

~~~javascript
{
  _id: "C-101",
  tenantId: "T-A",
  name: "An",
  displayName: "An",
  version: 7
}
~~~

Update:

~~~javascript
const result = db.customers.updateOne(
  {
    _id: "C-101",
    tenantId: "T-A",
    version: 7
  },
  {
    $set: {
      name: "An Mới",
      displayName: "An Mới"
    },
    $inc: { version: 1 }
  }
);

if (result.matchedCount !== 1) {
  throw new Error("Concurrent update: reload and retry");
}
~~~

Nếu another writer cập nhật version trước, điều kiện version=7 không match. Ứng dụng phải đọc lại, revalidate business logic và chỉ retry khi an toàn.

**Giới hạn:** cơ chế này chỉ bảo vệ khi **mọi writer liên quan** đều tuân thủ version discipline. Nếu old writer vẫn ghi name mà không tăng version, new writer không thể dựa vào version để biết tất cả thay đổi. Vì vậy version control **không thay thế bước loại bỏ old-only writers**.

### 10.1. Thận trọng với replaceOne

Một service đọc snapshot:

~~~javascript
{ name: "An", displayName: "An", preferredLocale: "vi-VN" }
~~~

rồi dựng lại document chỉ có:

~~~javascript
{ name: "An Mới" }
~~~

và gọi **replaceOne** có thể làm mất **displayName/preferredLocale**, vì replacement thay toàn document (trừ _id theo quy tắc MongoDB).

Trong thời gian mixed schema, ưu tiên **targeted $set/$unset** trên fields thay đổi hoặc xây replacement DTO đủ mọi field và có version condition. Không sử dụng “read rồi replace toàn bộ” từ old DTO trên document đã có field mới.

## 11. Backfill rename bằng aggregation pipeline update

Sau khi new writers đã triển khai và không còn old-only writers, cần chuyển **name** sang **displayName** cho documents lịch sử.

### 11.1. Vì sao không dùng $set với literal?

Lệnh:

~~~javascript
db.customers.updateMany(
  { displayName: { $exists: false } },
  { $set: { displayName: "name" } }
);
~~~

ghi **chuỗi literal "name"** vào mỗi document, không sao chép giá trị của field **name**.

Để lấy giá trị từ một field khác trong cùng document, dùng **aggregation pipeline update** (MongoDB 4.2+):

~~~javascript
db.customers.updateMany(
  {
    displayName: { $exists: false },
    name: { $type: "string" }
  },
  [
    {
      $set: {
        displayName: "$name"
      }
    }
  ]
);
~~~

Trong update pipeline:

- **"$name"** là biểu thức tham chiếu tới giá trị field name của document.
- Điều kiện **displayName missing** tránh ghi đè giá trị field mới đã tồn tại.
- Điều kiện **name kiểu String** nhằm tránh sao chép giá trị sai format.
- Thao tác cập nhật **mỗi document atomically**, nhưng **updateMany không là một transaction atomic toàn collection**.

### 11.2. Vì sao idempotent?

Lần đầu:

~~~text
Before: { name: "An" }
After : { name: "An", displayName: "An" }
~~~

Lần thứ hai, điều kiện **displayName: {$exists:false}** không còn match, nên document không bị sửa lại. Nếu new writer đã đặt displayName trước lệnh migration, document cũng không bị ghi đè.

**Nhưng idempotent không giải quyết mọi race**: nếu old-only writer vẫn update **name** sau backfill, name/displayName có thể khác. Vì thế điều kiện cần là đã vô hiệu old-only writers hoặc có cơ chế đồng bộ liên tục.

### 11.3. Không ghi đè xung đột một cách mù quáng

Nếu:

~~~javascript
{
  name: "An Cũ",
  displayName: "An Mới"
}
~~~

lệnh trên sẽ **không sửa** vì displayName tồn tại. Đây là hành vi an toàn hơn so với overwrite mà không biết field nào đúng, nhưng cần **phân loại và xử lý conflict**.

Trước khi switch, kiểm tra:

~~~javascript
db.customers.countDocuments({
  name: { $type: "string" },
  displayName: { $type: "string" },
  $expr: { $ne: ["$name", "$displayName"] }
});
~~~

Với dữ liệu production lớn, đây có thể là collection scan; cần có cách chạy bounded/off-peak hoặc job reconciliation có checkpoint và chỉ báo tổng hợp.

### 11.4. Backfill khác logic tự sửa khi đọc

Một cách thường bị đề xuất:

~~~text
Mỗi lần đọc legacy document:
  -> nếu displayName missing thì ghi nó ngay
~~~

Đây là **read repair**, có thể hữu ích trong một số thiết kế nhưng làm các read requests thành writes, tăng latency và nguy cơ ghi sai khi có concurrency. Không dùng read repair như cơ chế duy nhất nếu có documents ít được truy cập hoặc người dùng có quyền đọc nhưng không có quyền ghi.

Một **backfill job độc lập** dễ kiểm soát tốc độ, telemetry và hoàn tất hơn.

## 12. Backfill theo lô có giới hạn

Một **updateMany toàn collection** có thể tạo nhiều I/O, replication load và tăng độ trễ. Với lượng dữ liệu lớn, chia thành các batches nhỏ và theo dõi tiến độ.

### 12.1. Mẫu mongosh dùng bulkWrite

Ví dụ dưới đây xử lý **mỗi lần tối đa 200 candidates** trong database thử nghiệm:

~~~javascript
const batchSize = 200;
let examined = 0;
let totalModified = 0;

while (true) {
  const candidates = db.customers
    .find(
      {
        displayName: { $exists: false },
        name: { $type: "string" }
      },
      { _id: 1 }
    )
    .sort({ _id: 1 })
    .limit(batchSize)
    .toArray();

  if (candidates.length === 0) {
    break;
  }

  const operations = candidates.map(doc => ({
    updateOne: {
      filter: {
        _id: doc._id,
        displayName: { $exists: false },
        name: { $type: "string" }
      },
      update: [
        { $set: { displayName: "$name" } }
      ]
    }
  }));

  const result = db.customers.bulkWrite(
    operations, { ordered: false }
  );

  examined += candidates.length;
  totalModified += result.modifiedCount;
  printjson({
    examined,
    totalModified,
    batchMatched: result.matchedCount,
    batchModified: result.modifiedCount
  });

  sleep(100); // Lab: giới hạn tốc độ giữa batches.
}
~~~

**Ý nghĩa concurrency safety:**

- Job chỉ đọc **_id** của candidates.
- Khi thực hiện updateOne, filter vẫn yêu cầu **displayName chưa tồn tại**.
- Phép **$set: "$name"** lấy giá trị name hiện tại tại thời điểm update, không dùng bản snapshot String đã đọc trước.
- Nếu writer mới đã ghi displayName, updateOne sẽ không match, tránh overwrite.
- Nếu job chết giữa chừng, chạy lại vẫn an toàn đối với documents đã được cập nhật.

### 12.2. Batching trong production cần thêm điều kiện

Ví dụ minh họa chưa phải hệ thống migration production hoàn chỉnh. Một job thực tế cần:

1. **Checkpoint** được lưu lâu bền, không chỉ biến RAM.
2. **Leader/lock/lease** để tránh hai migration workers vô tình chạy cùng phần việc nếu không có kế hoạch.
3. **Timeout, retry có giới hạn và idempotency** với partial bulk errors.
4. **Throttling** theo replication lag, server CPU/IO và pool pressure.
5. **Per-tenant constraints** khi dữ liệu thuộc phạm vi quyền khác nhau.
6. **Dead-letter/quarantine** cho documents có kiểu dữ liệu sai.
7. **Khả năng resume/reconcile** sau deploy hoặc mạng lỗi.
8. **Audit** người chạy, version script và thời điểm kết thúc.

### 12.3. Checkpoint theo _id

Có thể duyệt các documents theo **_id tăng dần**:

~~~javascript
const page = db.customers.find(
  {
    _id: { $gt: lastProcessedId },
    displayName: { $exists: false }
  },
  { _id: 1 }
).sort({ _id: 1 }).limit(200).toArray();
~~~

Nhưng **_id không phải luôn đại diện thứ tự cập nhật**; document mới có thể được insert với _id nhỏ hơn checkpoint, hoặc field thay đổi sau khi đã đi qua. Vì thế ngoài checkpoint scan cần **reconciliation/final sweep** sau khi writers đã chuyển đổi xong.

Không dùng một giả định rằng **ObjectId luôn phản ánh thứ tự commit toàn cục** cho mọi collection hoặc mọi loại _id.

### 12.4. Khi bulkWrite thất bại giữa chừng

Với **ordered:false**, driver có thể xử lý những operations khác dù một operation lỗi; kết quả có thể thành công một phần. Cần:

- Ghi nhận số matched/modified và loại lỗi.
- Không coi toàn batch thất bại là mọi document chưa được đổi.
- Retry những candidates chưa thành công với **guarded filters**.
- Không log nội dung nhạy cảm của document.

Một backfill idempotent giúp retry an toàn hơn nhưng vẫn phải kiểm tra lỗi validation, permissions và tài nguyên.

## 13. Gate để chuyển từ old-first sang new-first

Chỉ đổi source of truth khi có bằng chứng rõ:

| Điều kiện | Bằng chứng |
|---|---|
| Không còn old-only writers | Deployment inventory, version telemetry, jobs/consumers đã nâng cấp |
| New writer dual-write đúng | Integration tests và metrics của write paths |
| Backfill hoàn tất | Missing displayName giảm về 0 theo phạm vi |
| Không có drift | Reconciliation theo tên/field version |
| Các query/index mới sẵn sàng | Explain, load tests, latency |
| Reader cũ vẫn có đường rollback | name còn đầy đủ và đồng bộ |
| API/CDC consumers tương thích | Contract tests, monitoring |

Sau đó triển khai phiên bản reader **displayName-first**. Có thể dùng feature flag/canary để chuyển dần, nhưng flag chỉ đổi hành vi ứng dụng; nó không tự giữ consistency cho hai fields.

### 13.1. Canary trong rolling deployment

Một kế hoạch:

~~~text
0% new-first readers
  -> 1% canary
  -> 10%
  -> 50%
  -> 100%
~~~

Ở mỗi bước quan sát:

- Missing displayName.
- Drift giữa name/displayName.
- API error/empty name rate.
- Latency của query/index mới.
- Dữ liệu từ delayed consumers.

Không tăng tỷ lệ chỉ dựa vào request success nếu field giá trị mới **sai nhưng vẫn có String**.

### 13.2. Backfill sau cutover?

Có thể duy trì một job sửa **remaining missing** trong rollback window, nhưng không nên backfill theo name khi displayName đã là canonical rồi, bởi vì lúc này name có thể chỉ là bản sao tạm. Phải cập nhật quy tắc reconciler theo source-of-truth của từng pha.

## 14. Khi nào dùng trực tiếp $rename?

MongoDB có operator **$rename** cho trường hợp thực sự muốn chuyển tên một field trong document.

~~~javascript
db.customers.updateOne(
  { _id: "C-101" },
  {
    $rename: {
      name: "displayName"
    }
  }
);
~~~

### 14.1. Hành vi quan trọng của $rename

- Nếu source field **không tồn tại**, thao tác không có gì để chuyển.
- Nếu target field đã tồn tại, **$rename ghi đè target**, nên có nguy cơ mất dữ liệu đang là canonical.
- $rename là thao tác chuyển field, không copy để giữ đồng thời cả hai.
- MongoDB không bảo đảm giữ nguyên **thứ tự field** trong document sau rename.
- $rename không thể sử dụng tùy ý cho **field bên trong phần tử array**.
- Với update trên một document, tính atomicity vẫn theo quy tắc **single-document atomic update**.
- Với updateMany, không có atomicity toàn collection.

**Tuyệt đối không chạy $rename tràn lan** trên collection đã có cả name và displayName nếu displayName có thể chứa giá trị mới hơn.

### 14.2. $rename không thay thế migration nhiều phiên bản

Phù hợp hơn trong một batch/offline scenario:

1. Tất cả services đã ngừng viết/đọc source field.
2. Target field chưa tồn tại hoặc target được cho phép overwrite theo policy rõ ràng.
3. Dữ liệu chưa có trạng thái mixed làm phát sinh xung đột.
4. Có backup/checkpoint và được kiểm tra trên staging.

Trong rolling deployment có nhiều old/new writers, **copy field với conditional update** thường an toàn hơn.

### 14.3. Với nested field có dấu chấm

Ví dụ:

~~~javascript
db.customers.updateOne(
  { _id: "C-101" },
  {
    $rename: {
      "profile.name": "profile.displayName"
    }
  }
);
~~~

Đây là đổi field bên trong **embedded document thường**. Không suy ra nó hoạt động trên mỗi object trong array **profiles[]**. Khi cần thay tên keys trong các phần tử array, sử dụng chiến lược migration riêng (aggregation pipeline với **$map/$mergeObjects** hoặc update đúng những phần tử và fields được hỗ trợ).

### 14.4. Đổi field trong array of documents

Ví dụ:

~~~javascript
{
  _id: "C-301",
  contacts: [
    { type: "HOME", phone: "000-111" },
    { type: "WORK", phone: "000-222" }
  ]
}
~~~

Không dùng $rename với path **contacts.$[].phone** để giả định tất cả phần tử array sẽ được đổi an toàn. Một migration phức tạp thường gồm:

- Xây transformation **newContacts** ở tầng ứng dụng hoặc aggregation pipeline.
- Giữ cả field cũ/mới nếu old readers còn dùng.
- Backfill từng document với version/guarded condition.
- Kiểm tra array length, order và các phần tử thiếu phone.
- Sau cùng mới loại phone cũ.

Nếu transformation dùng pipeline **$map**, cần xử lý null, empty arrays và preserve các field khác; không dùng phép map đơn giản sẽ làm mất metadata của từng contact.

## 15. Bỏ field: ba việc khác nhau

“Bỏ field” có thể có ba nghĩa:

1. **Bỏ khỏi API/DTO**: ứng dụng không trả trường đó nữa.
2. **Ngừng ghi/đọc trong application**: field vẫn có thể còn trong documents cũ.
3. **Xóa vật lý khỏi MongoDB**: cập nhật documents bằng $unset hoặc migration tương ứng.

Ba việc này **không nhất thiết cùng thời điểm**.

### 15.1. Giai đoạn ngừng sử dụng field

Ví dụ **legacyTag** không còn được code đọc hoặc ghi. Trước khi xóa:

- Tất cả API/reports/batch jobs đã bỏ dependency.
- Có metrics chứng minh không còn truy cập theo thiết kế.
- Không còn consumers dựa vào change event chứa legacyTag.
- Schema validator không yêu cầu legacyTag.
- Không còn rollback version yêu cầu legacyTag.
- Không bị policy audit/retention yêu cầu giữ nguyên.

Không thể chứng minh field không còn được dùng chỉ bằng việc **grep một source code repository**: các scripts khác, BI tools, ETL, admin queries hoặc ứng dụng bên ngoài có thể vẫn truy cập.

### 15.2. Ngừng ghi trước khi xóa

Nếu service V2 vẫn có đoạn:

~~~javascript
db.customers.updateOne(
  { _id: "C-101" },
  { $set: { legacyTag: "import-2026" } }
);
~~~

thì một job xóa toàn bộ legacyTag chỉ có hiệu lực tạm thời. Sau đó writer có thể tạo lại field.

Trình tự đúng:

~~~text
Deploy readers không dùng legacyTag
         |
         v
Deploy writers không tạo legacyTag
         |
         v
Verify no legacy writers
         |
         v
Wait required rollback/retention window
         |
         v
$unset legacyTag in batches
         |
         v
Verify no recurrence
~~~

### 15.3. Xóa dữ liệu bằng $unset

~~~javascript
db.customers.updateMany(
  { legacyTag: { $exists: true } },
  { $unset: { legacyTag: "" } }
);
~~~

**$unset** bỏ field khỏi document. Giá trị **""** là một dạng được dùng trong cú pháp update operator; nó không có nghĩa MongoDB gán field thành String rỗng.

Ví dụ:

~~~text
Before: { _id:"C-101", legacyTag:"import-2024" }
After : { _id:"C-101" }
~~~

Không nhầm **$unset** với **$set: {legacyTag:null}**. Với $set null, field vẫn **tồn tại** và có kiểu Null, gây khác biệt cho $exists, indexes, serialization và validator.

### 15.4. Tại sao không xóa name ngay sau copy?

Sau backfill:

~~~javascript
{ name: "An", displayName: "An" }
~~~

có thể người vận hành vẫn muốn rollback phiên bản V1 chỉ đọc name. Nếu xóa name ngay, rollback sẽ trả null hoặc phải chạy migration ngược trong thời gian khẩn cấp.

Vì vậy có thể giữ **name** trong một **rollback window được định nghĩa rõ**. Chỉ sau khi quyết định không hỗ trợ rollback trực tiếp tới V1 mới tiến hành contract bằng $unset.

### 15.5. Bỏ field không đồng nghĩa xóa mọi bản sao lịch sử

Khi xóa legacyTag:

- Replication log có thể còn dữ liệu lịch sử trong thời hạn lưu.
- Backup/snapshot cũ có thể còn bản ghi.
- Warehouse, cache, search index hoặc exports có thể vẫn có field.
- Audit logs có thể chứa thông tin liên quan.

Nếu field phải xóa vì privacy retention/erasure, cần quy trình xóa xuyên **toàn bộ data lifecycle**, không chỉ một lệnh $unset trên primary collection.

## 16. Bỏ field name trong giai đoạn contract

Chỉ sau khi mọi reader/writer đã dùng displayName và rollback V1 không còn yêu cầu name:

~~~javascript
db.customers.updateMany(
  { name: { $exists: true } },
  { $unset: { name: "" } }
);
~~~

Sau đó xác minh:

~~~javascript
db.customers.countDocuments({
  name: { $exists: true }
});
~~~

Kết quả mục tiêu là 0 theo scope đã migrate. Sau khi xóa, còn phải quan sát **field reappearance** từ delayed writers, admin jobs hoặc external connectors.

### 16.1. Không chỉ xóa documents mà quên code

Nếu Java DTO còn:

~~~java
@Field("name")
private String name;
~~~

thì code có thể vẫn ghi field name trong upsert/replace. Phải chuyển mapping trong source và database migration theo **cùng release plan**, không chỉ đổi collection.

### 16.2. Xóa index cũ sau dependency cuối

Nếu từng có:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, name: 1 },
  { name: "tenant_name_v1" }
);
~~~

sau khi mọi queries đã chuyển sang displayName và index mới sẵn sàng, mới cân nhắc:

~~~javascript
db.customers.dropIndex("tenant_name_v1");
~~~

Không drop index cũ ngay từ đầu giai đoạn dual-read, bởi các old queries vẫn có thể cần nó. Trên hệ thống lớn, index build/drop ảnh hưởng resource và cần kế hoạch vận hành riêng.

### 16.3. Không thay đổi collection name cùng lúc nếu chưa cần

Nếu đổi cả **collection**, **field** và **database namespace** trong cùng release, số đường tương thích/rollback tăng mạnh. Nên tách những thay đổi độc lập thành nhiều pha, hoặc xây chiến lược data replication/cutover riêng có gate rõ.

## 17. Schema validator: thay đổi theo nhiều bước

MongoDB hỗ trợ collection validator, thường dùng **$jsonSchema** để kiểm tra shape của document trong những thao tác insert/update theo validation settings.

### 17.1. Không require displayName khi old writers còn tồn tại

Validator quá sớm:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["displayName"],
    properties: {
      displayName: { bsonType: "string" }
    }
  }
}
~~~

có thể khiến old insert chỉ có name bị từ chối. Một replaceOne từ old client cũng có thể bị chặn vì bỏ field mới.

### 17.2. Giai đoạn mở rộng validator

Trong pha expand, validator nên chấp nhận document thuộc schema cũ và mới theo quy tắc nghiệp vụ:

~~~javascript
// Fragment minh họa một validator chấp nhận name hoặc displayName.
{
  $jsonSchema: {
    bsonType: "object",
    anyOf: [
      { required: ["name"] },
      { required: ["displayName"] }
    ],
    properties: {
      name: { bsonType: "string" },
      displayName: { bsonType: "string" },
      preferredLocale: { bsonType: "string" }
    }
  }
}
~~~

**anyOf** không tự đảm bảo hai fields bằng nhau nếu cùng tồn tại. Equality cross-field hoặc policy nguồn chính cần được quản lý ở application/migration layer. Production validator phải giữ các constraints hiện có.

### 17.3. Quan sát trước khi siết chặt

Ví dụ lệnh **collMod**:

~~~javascript
db.runCommand({
  collMod: "customers",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["displayName"],
      properties: {
        displayName: { bsonType: "string" },
        preferredLocale: { bsonType: "string" }
      }
    }
  },
  validationAction: "warn",
  validationLevel: "moderate"
});
~~~

**warn** cho phép ghi document vi phạm nhưng tạo cảnh báo; **moderate** có semantics riêng với những document hiện đã invalid. Hai lựa chọn này không đảm bảo mọi document cũ đã đúng schema mới.

Sau backfill, writers tương thích và hết rollback V1, có thể siết:

~~~javascript
db.runCommand({
  collMod: "customers",
  validationAction: "error",
  validationLevel: "strict"
});
~~~

Đây là **ví dụ theo trình tự**. Nếu collection có validator hiện hành, lệnh **collMod validator** mới có thể **thay thế biểu thức validator cũ**. Phải kết hợp tất cả constraints trước đó, không vô tình bỏ điều kiện kiểm tra tenantId hoặc fields khác.

### 17.4. Validation không sửa dữ liệu cũ

Validator kiểm tra những thao tác ghi theo validation policy; nó **không tự backfill** documents đã tồn tại.

Sau khi bật **strict/error**, vẫn cần:

- Báo cáo documents cũ chưa đạt schema.
- Kiểm soát quyền **bypassDocumentValidation**.
- Bảo đảm ETL/admin writers không bypass một cách tùy tiện.
- Kiểm tra bằng dữ liệu đại diện và quan sát error rates.

### 17.5. Validator có thể phá rollback

Nếu V1 chỉ ghi **name**, validator mới require **displayName**, rollback binary V1 sau khi bật strict/error có thể làm writes thất bại. Ngày siết validator là **compatibility gate**, không phải việc dọn dẹp vô hại.

## 18. Index migration theo giai đoạn

Trong giai đoạn có cả hai field:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, name: 1 },
  { name: "tenant_name_v1" }
);

db.customers.createIndex(
  { tenantId: 1, displayName: 1 },
  { name: "tenant_displayName_v2" }
);
~~~

### 18.1. Expand index trước khi chuyển read path

Trình tự:

1. Xác định query/filter/sort theo displayName.
2. Tạo index mới trong change plan phù hợp.
3. Quan sát index build, storage và write overhead.
4. Dùng **explain**/load test kiểm tra index.
5. Bật new-first readers/canary khi index sẵn sàng.
6. Giữ old index trong rollback window.
7. Drop old index khi mọi old readers/writers đã dừng.

**Index mới không nhất thiết nhanh hơn**: hiệu năng phụ thuộc selectivity, cardinality, filter, collation và phân bố dữ liệu.

### 18.2. Unique index và dữ liệu mixed schema

Ví dụ business cần field **externalCode** unique theo tenant. Tạo ngay:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, externalCode: 1 },
  { unique: true }
);
~~~

có thể thất bại hoặc áp đặt ràng buộc không mong muốn khi nhiều documents chưa có externalCode.

Một cách chuyển tiếp có thể là **unique partial index** cho documents đã có String:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, externalCode: 1 },
  {
    name: "tenant_externalCode_v2",
    unique: true,
    partialFilterExpression: {
      externalCode: { $type: "string" }
    }
  }
);
~~~

Điều này chỉ bảo đảm uniqueness cho **documents đáp ứng partial filter**. Nó không bảo đảm những document thiếu externalCode thỏa business invariant.

Trước khi xây unique index:

- Chuẩn hóa kiểu và normalization.
- Phát hiện duplicates, kiểm tra collation.
- Đảm bảo writers mới không tạo duplicates.
- Xác định unique scope theo tenant/sharding topology.
- Có kế hoạch nếu index build bị lỗi.

### 18.3. Một rename có thể thay đổi query cardinality

Nếu name có nhiều null/missing còn displayName đã được điền, index mới sẽ có phân bố key khác index cũ. Query plan có thể thay đổi ngay cả khi logic ứng dụng giống nhau. Cần đo stats thực tế sau backfill.

### 18.4. Collation phải nhất quán

Nếu old index dùng collation khác new index, equality/sort có thể khác về chữ hoa và dấu.

Ghi rõ trong migration plan:

~~~text
old query collation:
new query collation:
new index collation:
normalization policy:
~~~

và kiểm thử tên khác chữ hoa/dấu. Không tự đổi collation hoặc canonicalization trong cùng một rename khi chưa có quyết định riêng.

## 19. Phân biệt thay đổi additive và breaking

| Thao tác | Rủi ro chính | Giai đoạn thích hợp |
|---|---|---|
| Thêm optional field | Old data missing | Expand |
| New writer ghi optional field | Old reader có thể bỏ qua | Expand |
| Require field mới bằng validator | Old writers có thể bị chặn | Sau migrate/gate |
| Copy name sang displayName | Dữ liệu trùng, drift | Migrate |
| Ưu tiên displayName khi đọc | Old writer làm new value stale | Switch sau old-writer drain |
| Chạy $rename name → displayName | Old reader mất field, overwrite target | Chỉ khi kiểm soát hoàn toàn |
| Xóa name bằng $unset | Rollback V1 có thể hỏng | Contract |
| Xóa legacyTag bằng $unset | Mất dữ liệu lịch sử/consumer dependency | Contract sau retention |
| Drop old index | Old queries chậm | Cuối contract |
| Bỏ field khỏi DTO/API | External clients có thể lỗi | API migration độc lập |

Thêm field không bắt buộc thường là **additive change**, dễ rollout hơn xóa field mà old reader vẫn dùng.

### 19.1. Đổi kiểu dữ liệu còn khó hơn đổi tên

Ví dụ:

~~~text
old: price = "120.50" (String)
new: amount = NumberDecimal("120.50")
~~~

Cần parsing, rounding, invalid values, query/index changes và type conversion. Không chỉ copy String sang field mới rồi coi đã chuyển Decimal128.

### 19.2. Thay field ở đường dẫn lồng nhau

Nếu chuyển:

~~~text
old: customer.name
new: customer.profile.displayName
~~~

cần kiểm tra ancestor objects: profile missing, null, Array hay String. Dùng **$set với dotted path** có thể tạo embedded object thích hợp, nhưng lỗi nếu ancestor có kiểu không tương thích. Phải phát hiện và xử lý dữ liệu bất thường.

### 19.3. Field nhạy cảm

Khi migration liên quan PII:

- Không log giá trị mismatch.
- Không copy dữ liệu sang kho báo cáo không được phép.
- Không dump plaintext vào CI artifacts/laptop.
- Kiểm soát KMS/CSFLE/Queryable Encryption nếu field được mã hóa.

Với **client-side encrypted fields**, thao tác server-side $rename/$set không tự bảo đảm encryption schema/index mới phù hợp. Có thể cần client được ủy quyền **decrypt/re-encrypt** và migration chuyên biệt theo kỹ thuật mã hóa.

## 20. Java MongoDB Sync Driver: ghi đồng thời hai field

Một repository nên được inject **MongoCollection<Document>** từ một MongoClient dùng chung theo vòng đời ứng dụng.

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public final class CustomerRepository {
    private final MongoCollection<Document> customers;

    public CustomerRepository(
            MongoCollection<Document> customers) {
        this.customers = customers;
    }

    public boolean renameForTransition(
            String trustedTenantId,
            String customerId,
            String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Name required");
        }

        UpdateResult result = customers.updateOne(
                Filters.and(
                        Filters.eq("tenantId", trustedTenantId),
                        Filters.eq("_id", customerId)
                ),
                Updates.combine(
                        Updates.set("name", newName),
                        Updates.set("displayName", newName)
                )
        );

        return result.getMatchedCount() == 1;
    }

    public Document findById(
            String trustedTenantId,
            String customerId) {
        return customers.find(
                Filters.and(
                        Filters.eq("tenantId", trustedTenantId),
                        Filters.eq("_id", customerId)
                )
        ).first();
    }
}
~~~

Đây là **transitional dual-write** cho một document. Nó không tự giải quyết:

- Đồng thời old-only writers.
- Lost update khi nhiều new requests cùng sửa tên.
- Business validation/authorization.
- Events/CDC/analytics cũng cần tên field mới.

Các ràng buộc đó phải được xử lý ở tầng application workflow và rollout plan.

### 20.1. Optimistic locking trong Java

Nếu mọi writers đã dùng trường version:

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;

public boolean renameIfVersion(
        String tenantId,
        String customerId,
        int expectedVersion,
        String newName) {

    var result = customers.updateOne(
            Filters.and(
                    Filters.eq("_id", customerId),
                    Filters.eq("tenantId", tenantId),
                    Filters.eq("version", expectedVersion)
            ),
            Updates.combine(
                    Updates.set("name", newName),
                    Updates.set("displayName", newName),
                    Updates.inc("version", 1)
            )
    );
    return result.getMatchedCount() == 1;
}
~~~

Ví dụ này là **method trong cùng repository**, dùng field customers đã được inject. Version phải là một contract chung giữa các writers; trong pha còn old writer không tăng version, optimistic locking không thể bảo vệ khỏi tất cả thao tác cũ.

### 20.2. Đọc canonical value tùy phase

~~~java
public String getCustomerDisplayName(
        String trustedTenantId,
        String customerId,
        boolean newFieldIsCanonical) {

    Document customer = findById(
            trustedTenantId, customerId);
    if (customer == null) {
        return null;
    }

    String oldValue = customer.getString("name");
    String newValue = customer.getString("displayName");

    if (newFieldIsCanonical) {
        return newValue != null ? newValue : oldValue;
    }
    return oldValue != null ? oldValue : newValue;
}
~~~

Flag **newFieldIsCanonical** phải là cấu hình rollout đáng tin cậy và đi kèm với gate trước khi bật. Trong code production, nên ưu tiên kiểm tra nonblank/value validity và ghi metrics nếu có fallback hoặc conflict.

### 20.3. Không tự tạo MongoClient cho từng batch

Một backfill worker Java nên sử dụng một MongoClient được tạo một lần cho job, tái sử dụng connection pool, dùng **BulkWriteOptions**/timeouts và đóng tài nguyên cuối workflow. Không tạo hàng chục nghìn MongoClient ứng với từng customer.

## 21. Java backfill theo lô với guarded pipeline update

Trong Java Sync Driver, update pipeline có thể được mô tả bằng **List<Bson>** nếu driver/server version hỗ trợ:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.WriteModel;
import com.mongodb.client.model.BulkWriteOptions;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;

public final class CustomerBackfillJob {
    private final MongoCollection<Document> customers;

    public CustomerBackfillJob(
            MongoCollection<Document> customers) {
        this.customers = customers;
    }

    public long runOneBatch(int batchSize) {
        List<Document> candidates = customers.find(
                Filters.and(
                        Filters.exists("displayName", false),
                        Filters.type("name",
                                org.bson.BsonType.STRING)
                )
        ).projection(new Document("_id", 1))
         .sort(new Document("_id", 1))
         .limit(batchSize)
         .into(new ArrayList<>());

        if (candidates.isEmpty()) {
            return 0L;
        }

        List<WriteModel<Document>> operations =
                new ArrayList<>();

        for (Document candidate : candidates) {
            Bson guardedFilter = Filters.and(
                    Filters.eq("_id", candidate.get("_id")),
                    Filters.exists("displayName", false),
                    Filters.type("name",
                            org.bson.BsonType.STRING)
            );

            List<Bson> updatePipeline = List.of(
                    new Document("$set",
                            new Document("displayName", "$name"))
            );

            operations.add(new UpdateOneModel<>(
                    guardedFilter, updatePipeline));
        }

        return customers.bulkWrite(
                operations,
                new BulkWriteOptions().ordered(false)
        ).getModifiedCount();
    }
}
~~~

**Lưu ý:** đây là **một batch method**, không phải job orchestration hoàn chỉnh. Nó dùng:

- Projection chỉ lấy _id để giảm dữ liệu mạng.
- Filter tại write time tránh overwrite displayName.
- Pipeline update lấy **giá trị hiện tại** của name.
- bulkWrite unordered để không ngừng ngay ở lỗi đầu tiên nếu các thao tác khác vẫn có thể chạy.

Một Java program production còn cần vòng lặp, checkpoint lâu bền, rate limiting, timeout, retry có giới hạn, error classification, dead-letter handling và metrics. Nếu có docs mà displayName không thể tạo vì dữ liệu sai, job phải lưu lỗi thay vì quay vô hạn.

### 21.1. Rủi ro raw Document với typed mapping

Trong native Java Driver, field names như **name**, **displayName**, **tenantId** là **BSON field names thật**. Nếu Spring Data Entity dùng **@Field("customer_name")** cho Java property, raw driver không tự biết annotation Spring Data đó.

Vì vậy khi backfill qua native driver, phải dựa vào **schema vật lý BSON**, không dựa vào Java property name một cách mù quáng.

### 21.2. Dùng bulkWrite không có nghĩa toàn batch atomic

Một thao tác updateOne được bảo đảm atomic trên một document. Một bulk gồm 200 updateOne **không đồng nghĩa 200 documents được cập nhật trong một transaction**. Khi partial failure, chạy lại với guarded filters là phương án thường phù hợp hơn kỳ vọng rollback toàn batch.

## 22. Spring Data MongoDB: entity và field mapping trong pha chuyển đổi

Giả sử application sử dụng Spring Boot + Spring Data MongoDB:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("customers")
public class CustomerDocument {
    @Id
    private String id;

    private String tenantId;

    @Field("name")
    private String legacyName;

    @Field("displayName")
    private String displayName;

    private String preferredLocale;

    private String legacyTag;

    public CustomerDocument() {
    }

    // Getters/setters hoặc constructor binding theo chuẩn dự án.
}
~~~

Entity V2 giữ **cả legacyName và displayName**, cho phép đọc dữ liệu mixed schema. Thuộc tính **legacyName** của Java ánh xạ BSON field **name**. Không thể chỉ đổi:

~~~java
private String name;
~~~

thành:

~~~java
private String displayName;
~~~

rồi kỳ vọng Spring Data tự copy dữ liệu trong collection cũ.

### 22.1. Reader chuẩn hóa dữ liệu ở tầng service

Một service/read mapper có thể trả response DTO:

~~~java
public record CustomerResponse(
        String id,
        String displayName,
        String preferredLocale
) {}
~~~

Ở pha old-first:

~~~java
String effectiveName =
        entity.getLegacyName() != null
                ? entity.getLegacyName()
                : entity.getDisplayName();
~~~

Ở pha new-first:

~~~java
String effectiveName =
        entity.getDisplayName() != null
                ? entity.getDisplayName()
                : entity.getLegacyName();
~~~

Code trên giả định class có getters tương ứng. Trong code hoàn chỉnh cần xử lý empty String, validation và metrics; cách ưu tiên phải dựa vào **migration phase**.

### 22.2. Dual-write bằng MongoTemplate

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class CustomerTransitionWriter {
    private final MongoTemplate template;

    public CustomerTransitionWriter(MongoTemplate template) {
        this.template = template;
    }

    public boolean changeName(
            String trustedTenantId,
            String customerId,
            String newName) {

        Query query = new Query(Criteria.where("_id").is(customerId)
                .and("tenantId").is(trustedTenantId));

        Update update = new Update()
                .set("name", newName)
                .set("displayName", newName);

        UpdateResult result =
                template.updateFirst(query, update, "customers");

        return result.getMatchedCount() == 1;
    }
}
~~~

Với overload chỉ truyền **collection name**, code minh họa dùng trực tiếp BSON fields **name** và **displayName**. Trong overload dùng **entity class**, Spring Data có thể áp dụng mapping metadata. Không trộn tên Java/BSON của hai kiểu gọi nếu không kiểm tra query thực được gửi.

### 22.3. @Version và optimistic locking

Spring Data hỗ trợ **@Version** trên entity để thực hiện optimistic locking trong các luồng save/update được hỗ trợ.

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

Nhưng:

- Mọi writers cần tuân thủ version contract.
- Một old writer không tăng version có thể phá bảo đảm.
- Native MongoDB writes hoặc manual updates cần được thiết kế tương thích với versioning.
- Version field chỉ nhằm concurrency, không tự xác định schema đã migrate.

Không nên dùng cùng một field **version** cho cả optimistic locking và **schemaVersion** mà không phân biệt ý nghĩa.

### 22.4. Cẩn thận với repository.save()

Một Spring Data repository có thể có:

~~~java
customerRepository.save(customer);
~~~

Khi save entity theo cơ chế replacement, những fields **không có trong entity/serializer** có thể biến mất. Trong mixed schema, một worker dùng entity V1 không biết displayName có thể **ghi lại toàn bộ document và làm mất displayName**.

Do đó:

- Kiểm tra tất cả **save/replaceOne/upsert** code paths.
- Trong pha chuyển đổi, ưu tiên targeted updates khi thích hợp.
- Chỉ dùng full-document save với entity chứa đầy đủ dữ liệu cần giữ và optimistic locking phù hợp.
- Không coi dual-write chỉ ở controller là đủ nếu background repository.save() vẫn dùng model cũ.

### 22.5. Spring Data @Field không phải migration engine

Annotation **@Field("displayName")** chỉ hướng dẫn ánh xạ thuộc tính Java sang BSON field. Nó không:

- Tạo displayName cho documents đã có name.
- Xóa name cũ khỏi database.
- Tạo/dời index cũ sang field mới.
- Cập nhật validator tự động theo mọi policy.
- Chuyển search pipelines/aggregation đang dùng name.
- Bảo đảm event consumers đã dùng schema mới.

Cần application compatibility code và data migration riêng.

## 23. Sử dụng schemaVersion có cần thiết không?

Một hệ thống có thể đánh dấu:

~~~javascript
{
  _id: "C-101",
  schemaVersion: 2,
  displayName: "An",
  preferredLocale: "vi-VN"
}
~~~

Lợi ích:

- Cho phép diagnostics và migration routing.
- Giúp đọc một số format khác nhau.
- Giúp đánh giá version adoption.

Nhưng **schemaVersion=2 không chứng minh mọi field của document hợp lệ**. Một writer sai vẫn có thể:

~~~javascript
{
  schemaVersion: 2,
  name: "An"
}
~~~

hoặc document bị partial update khiến schemaVersion và fields không đồng bộ.

### 23.1. Khi nào nên dùng?

SchemaVersion có ích khi có **các shape khác nhau có ý nghĩa** hoặc cần chuyển dữ liệu qua nhiều version. Nhưng với một field optional mới, **field-existence + validation** có thể đủ và đơn giản hơn.

Không thêm schemaVersion vào mọi document chỉ vì muốn đánh dấu một lần chạy $set; nếu có nó, phải định nghĩa rõ **ai cập nhật version, điều kiện nào và nó có ý nghĩa gì**.

### 23.2. Schema version và optimistic version khác nhau

| Field | Mục đích | Ví dụ |
|---|---|---|
| schemaVersion | Định dạng/ý nghĩa của document | 1, 2, 3 |
| version hoặc revision | Điều khiển ghi đồng thời | 10, 11, 12 |
| migrationId | Dấu vết job/batch nếu cần | UUID migration run |

Không tăng **schemaVersion** mỗi lần user đổi tên, trừ khi document thực sự chuyển sang schema logic khác.

### 23.3. Migration trạng thái riêng

Với migration phức tạp, có thể có collection metadata của migration worker:

~~~javascript
{
  _id: "customers-name-to-displayName-v2",
  phase: "BACKFILL",
  lastProcessedId: "C-500000",
  startedAt: ISODate("2026-11-01T00:00:00Z"),
  updatedAt: ISODate("2026-11-14T00:00:00Z")
}
~~~

Đây là **orchestration state**, không phải field bắt buộc trong mỗi customer. Nơi lưu checkpoint cần permission riêng và cập nhật an toàn để tránh hai workers ghi đè tiến độ nhau.

### 23.4. Không coi checkpoint là chứng cứ cuối

Checkpoint chỉ nói job đã đi qua một vùng dữ liệu, không chứng minh:

- Không có document insert muộn với ID cũ.
- Không có old writer tái tạo name.
- Không có conflict.
- Không có document bị bỏ qua vì kiểu sai.

Phải có **final reconciliation** và quan sát sau khi cutover.

## 24. Multi-service và message/event schema

Một API không phải toàn bộ hệ thống. Trong hệ thống event-driven có thể có:

~~~text
Customer API V2
      |
      v
MongoDB customers
      |
      +--> Change stream consumer
      +--> Search index worker
      +--> Data warehouse ETL
      +--> Invoice service
      +--> Notification service
~~~

Nếu các downstream consumers vẫn chờ **name**, một thay đổi database chỉ giữ **displayName** có thể phá chúng dù API mới chạy tốt.

### 24.1. Version hóa event contract độc lập

Một event chuyển tiếp có thể:

~~~javascript
{
  eventType: "CustomerProfileChanged",
  eventVersion: 2,
  customerId: "C-101",
  name: "An Mới",
  displayName: "An Mới"
}
~~~

Sau khi consumers đã chuyển:

~~~javascript
{
  eventType: "CustomerProfileChanged",
  eventVersion: 3,
  customerId: "C-101",
  displayName: "An Mới"
}
~~~

Không nên tuyên bố **eventVersion=3** được tạo tự động vì database document có schemaVersion=3. Hai hợp đồng có thể có lịch triển khai khác nhau.

### 24.2. Change streams và migration writes

Backfill một triệu documents cũng tạo ra nhiều update events trong replication/change streams. Consumer có thể:

- Nhận nhiều events mà business logic không mong đợi.
- Reindex dữ liệu rất lớn.
- Gửi notification thừa nếu không phân biệt migration updates.
- Bị lag hoặc mất resume position do retention window.

Cần thiết kế event filtering/consumer behavior và capacity trước khi chạy job lớn. Với change streams:

- Cần deployment hỗ trợ tính năng.
- Dùng resume tokens/checkpoints đúng quy tắc.
- Không giả định mọi event luôn chứa fullDocument mới nhất tại đúng thời điểm update.
- Phân biệt **updateDescription.updatedFields**, **removedFields** và document lookup semantics theo version.

### 24.3. Delayed job là old writer trá hình

Một message tạo từ tuần trước có:

~~~javascript
{
  customerId: "C-101",
  name: "An Cũ"
}
~~~

Nếu được consumer V1 xử lý sau khi cutover, nó có thể ghi **name** trở lại hoặc overwrite dữ liệu mới.

Trước switch:

- Kiểm tra consumer lag/dead-letter queues.
- Nâng cấp consumer sang model tương thích.
- Xác định semantics khi xử lý event cũ.
- Sử dụng version/timestamp/sequence guards nơi cần để tránh stale event overwrite.

Một **drain hoàn tất** phải xem cả queued work, không chỉ số pods đang chạy.

## 25. Rollback: khả năng quay lại thay đổi theo mỗi pha

“Có backup” không đồng nghĩa “rollback về V1 không mất dữ liệu”. Các phiên bản ứng dụng có thể yêu cầu schema khác nhau và trong lúc khôi phục hệ thống vẫn tiếp tục nhận writes.

### 25.1. Bảng rollback theo giai đoạn

| Pha đã triển khai | Có thể rollback V1 trực tiếp? | Điều kiện |
|---|---|---|
| Expand reader tolerant | Thường có | Vẫn còn name và writer V1 hoạt động |
| V2 dual-write | Có thể | name tiếp tục được đồng bộ và validator cho phép V1 |
| Backfill, giữ cả hai field | Có thể | name còn, không bị stale, index/contract cũ chưa bị loại |
| Switch read displayName-first | Có thể nếu name vẫn đúng | Reconcile, V2 vẫn dual-write |
| Dừng dual-write name | Không tự bảo đảm | name có thể stale so với displayName |
| $unset name | Không trực tiếp | Cần reverse migration hoặc forward-fix |
| Strict validator require displayName | V1 có thể bị chặn | Cần thay validator và phục hồi field cũ |
| Drop old index | V1 queries có thể chậm | Cần tạo lại index trước/đồng thời rollback |

### 25.2. Rollback trước contract

Nếu name luôn được new writers cập nhật và chưa bị xóa:

~~~text
New reader returns displayName
       |
       v
Incident detected
       |
       v
Flag back to name-first reader
       |
       v
Keep dual-write during investigation
~~~

Rollback này tương đối nhẹ nhưng chỉ an toàn nếu **name còn được đồng bộ** và mọi validation/index/consumers vẫn tương thích.

### 25.3. Reverse backfill sau khi name đã bị xóa

Nếu new field displayName là nguồn dữ liệu chính xác và có thể tạm dừng/điều phối writers, một bước phục hồi tên field cũ có thể là:

~~~javascript
db.customers.updateMany(
  {
    name: { $exists: false },
    displayName: { $type: "string" }
  },
  [
    {
      $set: {
        name: "$displayName"
      }
    }
  ]
);
~~~

Đây là **copy ngược có điều kiện**, không phải full rollback plan. Còn phải:

1. Đảm bảo app đang ghi displayName không làm name stale ngay sau reverse backfill.
2. Điều chỉnh validator để V1 writes hợp lệ.
3. Phục hồi indexes cũ nếu query pattern V1 cần.
4. Xác minh dữ liệu/versions/permissions.
5. Chuyển traffic an toàn.
6. Khôi phục workers/events tương thích.

Không chạy reverse backfill tự động khi hai field đang có xung đột mà chưa xác định nguồn đúng.

### 25.4. Forward fix hay rollback?

Nếu đã contract và data loss không thể phục hồi đơn giản, một **forward fix** (sửa V3) có thể ít rủi ro hơn quay về V1. Quyết định phải dựa trên:

- Tính nghiêm trọng của incident.
- Có nguồn dữ liệu canonical đáng tin không?
- Migration có làm thay đổi semantics/units không?
- Thời gian khôi phục có thể chấp nhận.
- Backup/restore point và mất dữ liệu chấp nhận được.

Không thiết kế rollback bằng cách **restore toàn database từ backup cũ** nếu điều đó xóa cả updates hợp lệ của người dùng diễn ra sau snapshot.

### 25.5. Không xóa bản sao cũ trước khi hết retention

Một organization có thể yêu cầu giữ dữ liệu theo chính sách audit/backups; một organization khác yêu cầu xóa PII đúng thời hạn. Cần phân biệt **rollback window** và **data retention obligations**; không để một bản sao tên cũ tồn tại vô hạn chỉ vì chưa chốt rollback.

## 26. Transactions, atomicity và migration

MongoDB bảo đảm atomicity ở cấp **một document** cho các thao tác update thích hợp. Với updateMany hoặc bulkWrite, mỗi document có thể được cập nhật atomically, nhưng **không có một điểm chuyển đổi nguyên tử toàn collection** theo mặc định.

### 26.1. Khi cần transaction?

Ví dụ một invariant trải trên **hai collections**:

~~~text
customers.displayName
customer_search.displayName
~~~

Nếu sản phẩm yêu cầu hai bản ghi phải thay đổi cùng nhau theo một giao dịch, cần xem **multi-document transactions** trên topology hỗ trợ hoặc một thiết kế event/outbox có consistency phù hợp.

Tuy nhiên, không mặc định gói **hàng triệu updates** vào một transaction duy nhất:

- Transaction dài tăng tải/khóa tài nguyên.
- Giới hạn hoạt động, lifetime và log/replication.
- Lỗi transient/retry phức tạp.
- Có thể gây ảnh hưởng lớn đến workload thật.

Backfill theo lô idempotent thường là lựa chọn vận hành phù hợp hơn cho schema evolution của collection lớn.

### 26.2. Atomicity của dual-write trong cùng document

~~~javascript
db.customers.updateOne(
  { _id: "C-101" },
  { $set: { name: "An", displayName: "An" } }
);
~~~

Ở đây hai field cùng document được thay đổi atomically bằng một update. Không cần multi-document transaction chỉ để đảm bảo **hai field trong cùng document** được ghi đồng thời.

### 26.3. Thay schema trong sharded cluster

Trong sharded cluster:

- Migration có thể phân bố lên nhiều shards.
- Query có shard key có thể target chính xác hơn một shard.
- Collection scan/multi updates có thể tốn tài nguyên toàn cluster.
- Unique indexes có ràng buộc theo shard key và topology.
- Balancer/chunk migrations và replication lag cần được theo dõi.

Không coi updateMany trên sharded collection là một transaction toàn cluster. Phải kiểm tra compatibility/operational restrictions của server version.

### 26.4. Một migration không nên chiếm toàn bộ pool

Nếu service và migration worker dùng cùng cluster, migration cần giới hạn concurrency. Số threads/connection pool lớn không đảm bảo backfill nhanh hơn, mà có thể đẩy production traffic vào wait queue và gây timeout.

Khuyến nghị vận hành theo dữ liệu đo:

~~~text
low concurrency
  -> monitor p95 latency, CPU/IO, replication lag
  -> increase gradually if headroom exists
  -> pause when SLO deteriorates
~~~

Không chọn batchSize/concurrency lớn nhất chỉ vì máy dev chạy được.

## 27. Monitoring và các chỉ số migration

Nên có dashboard theo **phase** và **deployment version**, không chỉ một log “migration done”.

| Chỉ số | Ý nghĩa |
|---|---|
| legacy_read_fallback_total | Bao nhiêu requests cần name fallback |
| dual_write_success_total | Các writes đã ghi đúng cả hai fields |
| old_only_writer_detected_total | Phát hiện source còn ghi riêng name |
| missing_displayName_count | Documents chưa có field mới |
| invalid_displayName_count | New field tồn tại nhưng sai kiểu/rỗng |
| name_displayName_drift_count | Hai giá trị không đồng nhất trong pha cần đồng bộ |
| preferredLocale_missing_count | Documents còn thiếu field mới |
| legacyTag_remaining_count | Documents chưa cleanup |
| migration_batch_duration_ms | Độ trễ xử lý từng batch |
| migration_batch_modified | Số documents đã cập nhật mỗi batch |
| migration_error_count | Errors theo loại |
| change_stream_lag | Độ trễ consumers/CDCs nếu có |
| app_read_error_rate | Lỗi ở reader/canary |
| app_write_error_rate | Lỗi ở writer/validator |
| db_replication_lag | Tác động lên replica set |

Tên metrics trong bảng là **đề xuất cho hệ thống**, không phải MongoDB tự cung cấp nguyên các tên đó.

### 27.1. Query phát hiện các documents chưa migrate

~~~javascript
db.customers.find(
  {
    displayName: { $exists: false },
    name: { $type: "string" }
  },
  { _id: 1, tenantId: 1 }
).limit(20);
~~~

### 27.2. Query phát hiện conflict

~~~javascript
db.customers.aggregate([
  {
    $match: {
      name: { $type: "string" },
      displayName: { $type: "string" }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$name", "$displayName"] }
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1
    }
  },
  { $limit: 20 }
]);
~~~

Projection chỉ đưa ra **_id** và **tenantId**, tránh xuất hai giá trị tên thật vào log migration. Nếu tenantId cũng nhạy cảm, cần che hoặc giảm phạm vi observability tương ứng.

### 27.3. Không chỉ đếm, phải xét chất lượng

**missing_displayName_count = 0** vẫn chưa chứng minh migration thành công nếu:

- Field chứa String rỗng.
- Field là một bản sao cũ.
- Values sai normalization.
- Một số clients không còn đọc đúng.
- Index/collation khác semantics.

Do đó cần thêm **validity, drift và functional checks**.

### 27.4. Khi nào dừng migration?

Có thể tạm dừng theo cảnh báo:

- Latency p95/p99 vượt SLO.
- Replication lag tăng.
- Bulk errors tăng đột ngột.
- Validator errors xuất hiện từ một service version cũ.
- Downstream consumers bị quá tải.
- Chênh lệch name/displayName tăng thay vì giảm.

Không để job tự chạy tiếp khi invariant dữ liệu đang bị phá vỡ.

## 28. Các lỗi thường gặp khi triển khai nhiều pha

### 28.1. Đổi @Field trong Java rồi tưởng MongoDB đã đổi field

**Triệu chứng:** entity mới có displayName nhưng đọc document cũ thấy null.

**Nguyên nhân:** @Field chỉ điều khiển mapping; dữ liệu vật lý vẫn có name.

**Xử lý:** reader tương thích, backfill có điều kiện, rồi chuyển read path theo gate.

### 28.2. Chạy $rename một lần làm API cũ mất tên

**Nguyên nhân:** $rename chuyển field, không giữ bản sao cho old readers.

**Xử lý:** dùng expand/dual-read/dual-write rồi contract. Nếu đã rename, cần kế hoạch phục hồi name và xử lý old writers.

### 28.3. $rename ghi đè giá trị displayName mới

**Nguyên nhân:** target field tồn tại và có thông tin mới hơn, nhưng $rename được chạy tràn lan.

**Xử lý:** dừng job, xác định source of truth, phục hồi từ event log/backups nếu cần; không chạy lại blindly.

### 28.4. Backfill ghi literal "name" vào displayName

**Nguyên nhân:** dùng update document **$set: {displayName:"name"}** thay vì aggregation pipeline update.

**Xử lý:** hiểu khác biệt literal và expression **"$name"**, cô lập những documents đã bị ghi sai và sửa có kiểm soát.

### 28.5. Backfill ghi đè tên do người dùng mới sửa

**Nguyên nhân:** job đọc snapshot cũ rồi ghi một String stale mà không kiểm tra target field/version tại thời điểm update.

**Xử lý:** dùng guarded update/pipeline references tại server, optimistic version hoặc concurrency control phù hợp.

### 28.6. New reader đã chọn displayName nhưng old writer vẫn cập nhật name

**Nguyên nhân:** phase switch quá sớm.

**Xử lý:** rollback read preference tạm về name-first nếu an toàn; nâng cấp/drain old writers và reconcile trước khi chuyển lại.

### 28.7. Chạy lại migration làm dữ liệu thay đổi thêm

**Nguyên nhân:** migration không idempotent, ví dụ cộng số/append array hoặc ghi timestamp mới mỗi lần chạy.

**Xử lý:** định nghĩa trạng thái đã migrate, filter có điều kiện và checkpoint. Kiểm tra retries không làm lặp side effects.

### 28.8. Job bỏ sót document có name null

**Nguyên nhân:** filter chỉ xử lý String, nên invalid/empty data bị loại khỏi candidate set.

**Xử lý:** phân loại anomalies riêng, không ép tất cả null thành String rỗng. Có quy tắc sửa dữ liệu rõ.

### 28.9. Bật strict validator quá sớm

**Nguyên nhân:** old writer chưa tạo preferredLocale/displayName.

**Xử lý:** điều chỉnh validator về phase tương thích, nâng cấp writers, backfill và chỉ siết khi đạt gate.

### 28.10. Index mới không tăng tốc

**Nguyên nhân:** query dùng field sai, collation khác, query shape không hợp index hoặc data distribution không phù hợp.

**Xử lý:** explain, đo query plans/keys examined, sửa index/query thay vì chỉ thêm nhiều indexes.

### 28.11. Index unique mới không build được

**Nguyên nhân:** duplicates, missing values, collation/normalization hoặc sharding constraints.

**Xử lý:** điều tra duplicates và scope; dùng partial unique index trong giai đoạn chuyển tiếp nếu semantics phù hợp, rồi xử lý dữ liệu trước khi siết.

### 28.12. Old background job làm field name xuất hiện lại

**Nguyên nhân:** scheduler/consumer không nằm trong rolling deployment của main API.

**Xử lý:** kiểm kê và nâng cấp mọi writer, drain queue/dead-letter, quan sát field reappearance.

### 28.13. Full-document save làm mất field mới

**Nguyên nhân:** V1 entity không có displayName/preferredLocale, save/replace toàn document.

**Xử lý:** targeted update, mô hình V2 tương thích và concurrency controls; không dựa vào DTO cũ cho replace.

### 28.14. Count mới và cũ đều bằng nhau nhưng dữ liệu sai

**Nguyên nhân:** hai fields đều tồn tại nhưng chứa giá trị khác nhau.

**Xử lý:** đối soát **value equality** và quy tắc canonical, không chỉ đếm $exists.

### 28.15. Nhiều worker migrations chạy trùng

**Nguyên nhân:** job scheduler tạo nhiều instances không có lease hoặc checkpoint synchronization.

**Xử lý:** leader election/lease hoặc thiết kế idempotent và partition ownership, đo partial failures.

### 28.16. Rollback sau khi xóa name làm API V1 lỗi

**Nguyên nhân:** V1 chỉ biết name, document giờ chỉ có displayName.

**Xử lý:** không rollback binary V1 trực tiếp; thực hiện reverse migration/forward fix có gate, validator/index compatibility.

### 28.17. Đổi field API nhưng external client chưa nâng cấp

**Nguyên nhân:** gộp database schema migration với public API breaking change.

**Xử lý:** version API, deprecation policy, compatibility response và thông báo cho consumers.

### 28.18. CDC consumer lag sau backfill hàng triệu documents

**Nguyên nhân:** migration gây write/event burst, consumer không kịp xử lý.

**Xử lý:** giới hạn tốc độ, đo lag và resume token, đánh giá cách phân biệt migration events khỏi business events.

### 28.19. Xóa field nhạy cảm nhưng backup cũ vẫn chứa nó

**Nguyên nhân:** $unset chỉ ảnh hưởng documents hiện tại, không tự xóa mọi lịch sử/copy.

**Xử lý:** áp dụng retention/erasure policy xuyên backup, exports, warehouse, logs và cache với kiểm soát khôi phục.

### 28.20. Chuyển field trong array bằng $rename không hoạt động

**Nguyên nhân:** $rename không hỗ trợ rename tùy ý từng phần tử array.

**Xử lý:** transformation có hiểu cấu trúc array, bảo toàn phần tử/field, kiểm thử missing/null và version concurrency.

## 29. Runbook triển khai tham khảo

Một runbook production nên chia thành các **gates có thể xác nhận** và có owner rõ:

### Giai đoạn 0 — thiết kế và baseline

1. Tạo ADR ghi scope: **name → displayName, add preferredLocale, drop legacyTag**.
2. Xác định default/normalization, quyền và retention.
3. Kiểm kê toàn bộ readers/writers/consumers/jobs.
4. Đo baseline field distribution, data types, latency và indexes.
5. Kiểm tra backup/restore strategy và quyền migration worker.
6. Chốt rollback window/feature flags.

### Giai đoạn 1 — expand

1. Deploy V2 readers đọc được old/new fields, ưu tiên name.
2. Deploy V2 writers cập nhật name và displayName trong cùng update.
3. New creates có preferredLocale khi business default được phép.
4. Mở rộng validator để chấp nhận trạng thái mixed.
5. Tạo index displayName cần cho future queries.
6. Monitor application versions, writes, errors.

**Gate 1:** không còn các code paths bắt buộc phải có displayName ngay trong khi dữ liệu chưa backfill; V1 vẫn hoạt động khi rolling deploy.

### Giai đoạn 2 — ngừng old-only writers

1. Nâng cấp main API replicas.
2. Nâng cấp consumers và batch jobs.
3. Dừng hoặc drain queued work theo schema cũ.
4. Xác nhận telemetry của old versions.
5. Tắt quyền chạy old scripts nếu đã hết sử dụng.

**Gate 2:** không còn nguồn tạo độc lập **name-only changes** hoặc source đó có cơ chế chuyển tiếp đáng tin cậy.

### Giai đoạn 3 — migrate dữ liệu

1. Backfill preferredLocale missing theo policy.
2. Backfill displayName khi missing và name hợp lệ.
3. Dùng guarded operations, batches, checkpoints, retry.
4. Theo dõi replication lag/latency.
5. Tách/analyze records invalid.
6. Reconcile name/displayName conflicts.

**Gate 3:** new fields có giá trị hợp lệ, conflicts được xử lý và metrics đã đạt tiêu chí chuyển đổi.

### Giai đoạn 4 — switch

1. Canary displayName-first readers.
2. So sánh nội dung response và error/latency.
3. Ramp rollout dần.
4. Tiếp tục dual-write trong rollback window.
5. Xác nhận Search, analytics, API contracts đều dùng new fields.

**Gate 4:** new read path vận hành ổn định và vẫn rollback an toàn theo kế hoạch.

### Giai đoạn 5 — contract

1. Quyết định kết thúc rollback V1.
2. Chuyển writers sang new-only.
3. Bỏ fallback name ở readers khi không còn cần.
4. Ngừng yêu cầu name/legacyTag trong events/APIs.
5. Bật strict validator mới nếu policy yêu cầu.
6. Xóa name/legacyTag bằng guarded batches.
7. Drop indexes cũ sau khi xác minh query dependencies.
8. Theo dõi field reappearance và downstream lag.

**Gate 5:** không còn phụ thuộc cũ; documents, indexes, validators và events đều theo schema mới.

### Giai đoạn 6 — đóng migration

1. Ghi kết quả, thời gian, errors và exceptions đã chấp nhận.
2. Lưu migration script/ADR/rollback limitations.
3. Gỡ transitional flags và code dual-write khi đã an toàn.
4. Kiểm soát quyền migration account, secrets và jobs cũ.
5. Đối chiếu retention/backups/warehouse.

**Không làm contract dựa trên một mốc thời gian cứng** nếu gate về data correctness và writer drainage vẫn chưa đạt.

## 30. Kiểm thử tính tương thích giữa nhiều phiên bản ứng dụng

Một migration không chỉ cần test document có dữ liệu đúng, mà cần test **nhiều application versions cùng chạy** trên collection có mixed schema.

### 30.1. Ma trận đọc/ghi

| Dữ liệu | V1 reader name-only | V2 reader old-first | V3 reader new-first |
|---|---|---|---|
| Chỉ name | Đọc được | Đọc được | Đọc qua fallback nếu còn |
| Cả name và displayName giống nhau | Đọc được | Đọc được | Đọc được |
| Cả hai khác nhau | Đọc name | Đọc name | Đọc displayName |
| Chỉ displayName | Không đọc được tên | Đọc qua fallback | Đọc được |
| Cả hai missing | Không có tên | Error/fallback theo policy | Error/fallback theo policy |

Mục **cả hai khác nhau** là quan trọng nhất khi có old-only writers: nó chứng minh không thể chọn new-first quá sớm.

### 30.2. Test một document được cập nhật đồng thời

~~~text
Document: name=A, displayName=A, version=1

Request 1: read version=1
Request 2: read version=1

Request 1: update to B with version=1 -> success
Request 2: update to C with version=1 -> matchedCount=0
~~~

Kết quả hợp lệ:

~~~text
name=B, displayName=B, version=2
~~~

Request 2 phải reload/revalidate, không âm thầm overwrite B. Một test như vậy cần MongoDB thật hoặc integration environment có concurrency semantics phù hợp; unit test mock đơn thuần thường không đủ.

### 30.3. Test backfill và user update cùng lúc

~~~text
T0: name=A, displayName missing
T1: backfill chọn _id
T2: app mới update name=B, displayName=B
T3: backfill update với filter displayName missing
~~~

Kết quả: backfill không match nữa, giữ B. Đây là lý do **guarded filter tại thời điểm ghi** quan trọng hơn chỉ đọc candidates một lần.

### 30.4. Test old writer còn sót

~~~text
T0: name=A, displayName=A
T1: old writer set name=B
T2: new-first reader returns A
~~~

Đây là **test phát hiện rủi ro**, không phải hành vi mong muốn. Gate switch không nên mở khi old writer vẫn tồn tại mà không có đồng bộ.

### 30.5. Test replaceOne với DTO cũ

Một entity V1 chỉ có name. Sau khi V2 tạo displayName, chạy save/replace với V1 shape để xác định:

- displayName có bị mất không?
- preferredLocale có bị mất không?
- version có bảo vệ update không?
- validator có chặn replacement không?

Chỉ làm trong integration dataset, không trên dữ liệu thật.

### 30.6. Test data validation

Tạo các document:

~~~javascript
{ _id: "CASE-1", name: "An" }
{ _id: "CASE-2", name: null }
{ _id: "CASE-3", name: 123 }
{ _id: "CASE-4", displayName: "An" }
{ _id: "CASE-5", name: "An", displayName: "An Mới" }
{ _id: "CASE-6", name: "" }
~~~

Nên xác định:

- CASE-1 được backfill.
- CASE-2/3 được tách ra xử lý.
- CASE-4 không bị overwrite.
- CASE-5 được ghi nhận là conflict.
- CASE-6 có phải tên hợp lệ không theo nghiệp vụ.

### 30.7. Test phased rollback

Một test môi trường staging:

1. Deploy V2 compatible.
2. Migrate một subset.
3. Switch new-first.
4. Rollback reader old-first khi name còn đúng.
5. Tiếp tục một write.
6. Xác minh old/new values đồng bộ.

Sau contract, rollback test phải bao gồm **reverse migration/validator/index plan**, không chỉ roll back Docker image.

## 31. Bài tập thực hành và tình huống

Các bài tập dùng database **app_lab** và collection **customers** của mục 3. Không sử dụng database production để thử các lệnh $rename/$unset.

### Bài 1. Add field không ghi đè user preference

Một document có preferredLocale="en-US", document khác thiếu preferredLocale.

**Yêu cầu:** viết update chỉ gán vi-VN cho document thiếu field.

**Đáp án:**

~~~javascript
db.customers.updateMany(
  { preferredLocale: { $exists: false } },
  { $set: { preferredLocale: "vi-VN" } }
);
~~~

### Bài 2. Missing khác null

Hai documents:

~~~javascript
{ _id: "X", preferredLocale: null }
{ _id: "Y" }
~~~

**Câu hỏi:** filter preferredLocale: {$exists:false} match document nào?

**Đáp án:** chỉ Y. X có field tồn tại với giá trị null.

### Bài 3. Rename một bước có an toàn không?

Ứng dụng còn 5 pods V1 đọc name. DBA chạy $rename name→displayName trên mọi document.

**Câu hỏi:** điều gì xảy ra?

**Đáp án:** V1 readers có thể không tìm thấy name; V1 writers có thể tạo name trở lại. Cần reader/writer tương thích trước khi xóa old field.

### Bài 4. Copy field bằng pipeline update

Document:

~~~javascript
{ _id: "X", name: "An" }
~~~

**Yêu cầu:** tạo displayName từ name, không ghi đè displayName đã tồn tại.

**Đáp án:**

~~~javascript
db.customers.updateMany(
  {
    displayName: { $exists: false },
    name: { $type: "string" }
  },
  [
    { $set: { displayName: "$name" } }
  ]
);
~~~

### Bài 5. Phân biệt literal và field reference

~~~javascript
{ $set: { displayName: "name" } }
~~~

so với:

~~~javascript
[ { $set: { displayName: "$name" } } ]
~~~

**Đáp án:** update document đầu tiên gán chuỗi literal "name"; aggregation pipeline update thứ hai lấy giá trị từ field name.

### Bài 6. Dual-write nguyên tử

**Yêu cầu:** cập nhật cả name và displayName trong một lệnh.

**Đáp án:**

~~~javascript
db.customers.updateOne(
  { _id: "C-101", tenantId: "T-A" },
  {
    $set: {
      name: "An Mới",
      displayName: "An Mới"
    }
  }
);
~~~

### Bài 7. Old writer tạo drift

~~~text
T0: name=A, displayName=A
T1: old writer set name=B
~~~

**Câu hỏi:** new-first reader trả gì? Có an toàn không?

**Đáp án:** trả A dù old writer đã ghi B. Không an toàn nếu chưa loại bỏ old-only writers hoặc reconcile.

### Bài 8. Chọn source of truth

**Câu hỏi:** trong pha còn V1 writers, vì sao có thể ưu tiên name? Sau khi old writers dừng nên ưu tiên gì?

**Đáp án:** name là field duy nhất được mọi writers cập nhật ban đầu; sau dual-write phổ cập, backfill và reconcile, displayName có thể trở thành nguồn chính.

### Bài 9. Backfill idempotency

**Câu hỏi:** vì sao filter displayName missing giúp chạy lại migration an toàn?

**Đáp án:** documents đã backfill không còn match; job tránh overwrite field mới được tạo/cập nhật.

### Bài 10. Dữ liệu conflict

~~~javascript
{ name: "An Cũ", displayName: "An Mới" }
~~~

**Câu hỏi:** có nên chạy $rename name→displayName?

**Đáp án:** không, vì target có thể bị overwrite. Cần phân loại conflict và xác định field canonical theo phase, lịch sử/version và nghiệp vụ.

### Bài 11. UpdateMany có atomic toàn collection không?

**Câu hỏi:** cập nhật một triệu documents bằng updateMany có bảo đảm mọi document chuyển sang schema mới cùng lúc không?

**Đáp án:** không. MongoDB có atomicity trên từng document, nhưng không có điểm chuyển đổi toàn collection mặc định.

### Bài 12. Batch checkpoint

Một job duyệt _id tới C-5000. Sau đó document mới có _id C-0400 được insert theo schema cũ.

**Câu hỏi:** tiếp tục từ lastProcessedId có chắc xử lý C-0400 không?

**Đáp án:** không. Cần final reconciliation/sweep và đảm bảo writer mới tạo schema đúng.

### Bài 13. Đổi field trong array

Document có contacts là array of objects, mỗi object có phone.

**Câu hỏi:** có thể mặc định dùng $rename contacts.$[].phone→contacts.$[].contactPhone không?

**Đáp án:** không. $rename có giới hạn với fields trong arrays. Cần transformation có kiểm soát, bảo toàn từng phần tử và concurrency.

### Bài 14. Bỏ field bằng $unset

**Yêu cầu:** xóa legacyTag khỏi documents có field.

~~~javascript
db.customers.updateMany(
  { legacyTag: { $exists: true } },
  { $unset: { legacyTag: "" } }
);
~~~

### Bài 15. Null thay vì unset

**Câu hỏi:** $set legacyTag:null có tương đương $unset legacyTag không?

**Đáp án:** không. $set null giữ field tồn tại; $unset loại field khỏi document.

### Bài 16. Validator quá sớm

V1 writer chỉ tạo name, còn admin bật validator **required: ["displayName"]**, action=error.

**Câu hỏi:** điều gì có thể xảy ra?

**Đáp án:** old inserts/replacements có thể bị từ chối. Cần expand validator hoặc nâng writers trước khi siết strict/error.

### Bài 17. Validation warn và moderate

**Câu hỏi:** sau khi bật validationAction=warn, validationLevel=moderate, có thể kết luận mọi document đã đúng schema không?

**Đáp án:** không. Warn không chặn dữ liệu sai; moderate có semantics riêng với records hiện invalid. Validator không tự backfill.

### Bài 18. Unique partial index

Một triệu documents chưa có externalCode, nhưng new writer cần unique externalCode trong từng tenant.

**Câu hỏi:** partial unique index có tác dụng và giới hạn gì?

**Đáp án:** có thể áp dụng uniqueness cho subset có externalCode hợp lệ theo filter; không bảo đảm tất cả documents đều có field hoặc toàn bộ business invariant đã được thực hiện.

### Bài 19. Index cũ và mới

V2 readers vẫn query name, V3 readers query displayName.

**Câu hỏi:** khi nào drop index tenant_name_v1?

**Đáp án:** sau khi không còn readers dùng name và rollback V1 không cần index cũ; trước đó cần giữ trong giai đoạn chuyển tiếp và theo dõi chi phí hai indexes.

### Bài 20. DTO dùng @Field

Entity Java cũ có:

~~~java
@Field("name")
private String customerName;
~~~

Developer sửa thành:

~~~java
@Field("displayName")
private String customerName;
~~~

**Câu hỏi:** Spring Data đã đổi toàn bộ dữ liệu MongoDB chưa?

**Đáp án:** chưa. @Field chỉ ảnh hưởng mapping khi converter đọc/ghi, không migrate documents đã lưu.

### Bài 21. Full-document save

Sau khi V2 thêm displayName, một V1 job đọc customer vào entity chỉ có name, rồi save toàn document.

**Câu hỏi:** rủi ro?

**Đáp án:** replacement có thể làm mất displayName/preferredLocale, vì model V1 không biết những fields đó. Nên chuyển job sang version tương thích hoặc targeted update.

### Bài 22. SchemaVersion và optimistic version

Document:

~~~javascript
{ schemaVersion: 2, version: 19 }
~~~

**Câu hỏi:** hai fields khác nhau gì?

**Đáp án:** schemaVersion mô tả format document; version/revision là cơ chế kiểm soát ghi đồng thời. Không tăng schemaVersion mỗi lần user thay tên nếu schema không đổi.

### Bài 23. Khả năng rollback

V3 đã ngừng dual-write, xóa name và bật strict validator require displayName. Đội vận hành muốn rollback binary V1 ngay.

**Câu hỏi:** có an toàn không?

**Đáp án:** không. V1 thiếu field đọc/ghi, validator và index có thể không tương thích. Cần reverse migration, validator/index restoration hoặc forward fix.

### Bài 24. Change streams và traffic migration

Backfill hai triệu documents gây nhiều update events.

**Câu hỏi:** những downstream components nào bị ảnh hưởng?

**Đáp án:** CDC, search indexers, caches, analytics, notification workers. Cần đo lag, rate limiting và tránh triggering business actions không mong muốn.

### Bài 25. Old message trong queue

Sau switch, consumer nhận message cũ chứa name="An Cũ" rồi ghi field name vào database.

**Câu hỏi:** vì sao số pods V1 bằng 0 vẫn chưa đủ?

**Đáp án:** message cũ và delayed jobs có thể tác động. Cần drain queues, schema-aware handlers hoặc version/sequence guards.

### Bài 26. PII sau $unset

Hệ thống xóa legacyTag khỏi MongoDB, nhưng backup và warehouse vẫn có field.

**Câu hỏi:** có thể tuyên bố dữ liệu đã bị xóa khỏi mọi nơi chưa?

**Đáp án:** chưa. Phải xem retention/erasure obligations và xử lý bản sao/export/cache/log tương ứng.

### Bài 27. Tranh chấp dữ liệu khi rollback

Trước rollback:

~~~javascript
{ name: "An Cũ", displayName: "An Mới" }
~~~

**Câu hỏi:** reverse backfill nên làm gì?

**Đáp án:** không tự copy field này sang field kia nếu chưa xác định canonical source. Cần xem phase, event history và policy xử lý conflict.

### Bài 28. Thay đổi đơn vị dữ liệu

Field oldPriceCents=12345, field newPrice theo đơn vị tiền lớn.

**Câu hỏi:** có thể chỉ dùng $rename không?

**Đáp án:** không. Cần chuyển đổi /100, kiểu số Decimal, rounding policy, overflow và currency.

### Bài 29. Thiết kế phased rollout đầy đủ

Yêu cầu:

~~~text
old field: email
new field: contact.emailAddress
old readers: còn 12 pods
old writers: nightly batch job
new API: cần search theo contact.emailAddress
rollback requirement: 7 ngày
~~~

**Yêu cầu bài làm:** thiết kế các bước:

1. Mở rộng reader/serializer.
2. Dual-write email và contact.emailAddress.
3. Nâng cấp nightly batch job.
4. Backfill có guarded conditions.
5. Tạo index cho field mới.
6. Switch search path.
7. Giữ old field qua rollback window.
8. Contract và xóa index cũ.

**Định hướng:** không xóa email hoặc bật new-only writer khi batch job cũ còn chạy. Với email phải tính uniqueness, normalization, security/PII, external API và duplicate handling.

### Bài 30. Sự cố sau cutover

Trong canary 10%:

~~~text
missing displayName count = 0
name/displayName drift count = 500
read error rate = 0
~~~

**Câu hỏi:** có thể ramp lên 100% không?

**Đáp án:** không nên. Không có lỗi HTTP không bảo đảm dữ liệu đúng; 500 conflicts cần giải thích và xử lý trước khi ramp.

### Bài 31. Batch có lỗi một phần

Một bulkWrite chạy 200 updateOne, modifiedCount=192 và lỗi validation ở ba documents.

**Câu hỏi:** có nên chạy lại toàn batch bằng update không filter để chắc chắn không?

**Đáp án:** không. Cần phân loại matched/modified/errors, retry có điều kiện, cô lập invalid documents và đảm bảo idempotence.

### Bài 32. Đánh giá mức độ hoàn tất

Dashboard:

~~~text
displayName missing = 0
preferredLocale missing = 0
legacyTag remaining = 0
V1 pods = 0
V1 queued messages = 1000
~~~

**Câu hỏi:** có thể tuyên bố contract hoàn thành chưa?

**Đáp án:** chưa. V1 queued messages còn có thể tạo old writes; cần drain/migrate messages và theo dõi field reappearance.

## 32. Checklist triển khai thực tế

### 32.1. Trước khi deploy

- [ ] Có sơ đồ old/new fields và định nghĩa canonical source cho từng phase.
- [ ] Đã kiểm kê tất cả readers, writers, batch jobs, consumer và external clients.
- [ ] Có dữ liệu mẫu cho missing/null/invalid/conflict.
- [ ] Có policy default/normalization/type conversion được duyệt.
- [ ] Có migration owner, checklist gates và rollback window.
- [ ] Đã chuẩn bị index mới và phương án giữ index cũ.
- [ ] Có kế hoạch với schema validator và unique constraints.
- [ ] Có quyền migration tối thiểu cần thiết và phương án backup/restore.

### 32.2. Trong giai đoạn expand

- [ ] Readers chịu được old và new shape.
- [ ] Old-first source được dùng trong thời gian old-only writers tồn tại.
- [ ] New writer ghi name/displayName trong **cùng update**.
- [ ] Không có full-document replacement xóa field mới.
- [ ] API event/CDC consumers được chuẩn bị.
- [ ] Metrics phát hiện missing/fallback/drift có sẵn.

### 32.3. Trong migrate

- [ ] Backfill có guarded filter, idempotent và batch size hợp lý.
- [ ] Job có checkpoint/retry/dead-letter và throttle.
- [ ] Anomalies được xử lý riêng, không overwrite dữ liệu hợp lệ.
- [ ] Đã chứng minh old writers được nâng cấp/drain.
- [ ] Monitor replication lag, p95 latency, write errors.
- [ ] Reconciliation kiểm tra **giá trị**, không chỉ $exists.

### 32.4. Trong switch và contract

- [ ] Canary new-first readers đã qua gate.
- [ ] Rollback compatibility được định nghĩa và có thời hạn.
- [ ] Không còn V1 binaries, queue messages hoặc admin scripts có thể ghi old field.
- [ ] New-only writers sẵn sàng.
- [ ] Validator strict/error được bật khi phù hợp.
- [ ] Old field/index bị xóa sau khi hết dependencies.
- [ ] Có theo dõi field reappearance và data copies sau contract.

## 33. Bảng tra cứu nhanh

| Nhu cầu | Công cụ/cách tiếp cận |
|---|---|
| Thêm field có default | $set + filter $exists:false |
| Phân biệt missing và null | $exists và $type |
| Copy giá trị field này sang field khác | Aggregation pipeline update với field reference |
| Đổi tên field một bước khi không còn mixed clients | $rename với điều kiện kiểm soát |
| Giữ old/new readers cùng lúc | Dual-read với source-of-truth theo phase |
| Giữ old/new writers cùng lúc | Dual-write cùng document |
| Tránh lost update | Version condition / optimistic locking |
| Backfill hàng triệu records | Guarded batches, checkpoint, retry, throttling |
| Xóa field vật lý | $unset sau contract |
| Tăng tính chặt schema | collMod validator theo giai đoạn |
| Search trên field mới | Tạo index mới trước read cutover |
| Bỏ index cũ | Sau khi hết old queries/rollback |
| Rollback sau khi đã xóa source | Reverse migration/forward fix có kế hoạch |
| Theo dõi consistency | Missing/invalid/drift counters và reconciliation |
| Tránh event consumers bị phá | Version/deprecate event contract và drain queues |

## 34. Tài liệu tham khảo

Các URL chính thức nên tra đúng **MongoDB server version**, **Java Driver version** và **Spring Data MongoDB version** đang dùng:

- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [MongoDB Manual — $set](https://www.mongodb.com/docs/manual/reference/operator/update/set/)
- [MongoDB Manual — $unset](https://www.mongodb.com/docs/manual/reference/operator/update/unset/)
- [MongoDB Manual — $rename](https://www.mongodb.com/docs/manual/reference/operator/update/rename/)
- [MongoDB Manual — Updates with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — updateMany](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/)
- [MongoDB Manual — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Modify Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/update-schema-validation/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Java Sync Driver — CRUD Update](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update/)
- [Spring Data MongoDB — Template API](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking)

MongoDB và Spring Data thay đổi hỗ trợ API/semantics theo phiên bản. Trước khi chạy một script production, phải đối chiếu tài liệu đúng deployment, đặc biệt với **array updates, validator behavior, sharding và transaction limits**.

## 35. Kết luận

Thay đổi một field MongoDB tưởng như là công việc CRUD đơn giản, nhưng trong hệ thống đang chạy, nó thực chất là **một quá trình chuyển đổi hợp đồng dữ liệu giữa nhiều phiên bản phần mềm**.

~~~text
                    BEFORE
              customers.name
                    |
                    v
               EXPAND READERS
          old-first, accept both
                    |
                    v
                DUAL-WRITE
             name + displayName
                    |
                    v
               DRAIN V1 WRITERS
                    |
                    v
                  BACKFILL
     guarded $set + batch + checkpoint
                    |
                    v
                RECONCILE
    missing=0, invalid=0, drift resolved
                    |
                    v
                 SWITCH READ
              displayName-first
                    |
                    v
               ROLLBACK WINDOW
         keep old copy while needed
                    |
                    v
                  CONTRACT
        stop old writes/read fallback
        $unset old fields, drop index
                    |
                    v
                    AFTER
          customers.displayName
~~~

**Mười nguyên tắc cần nhớ:**

1. **Add field** nên bắt đầu bằng optional readers và writers mới; chỉ require sau khi dữ liệu và code tương thích.
2. **Rename field** trong rolling deployment thường là **copy → dual-run → switch → delete**, không phải chạy $rename ngay.
3. **Old-only writer có thể làm bản sao mới stale**; không chuyển sang new-first cho đến khi xử lý rủi ro này.
4. **Dual-write hai field cùng document trong một update** đơn giản và an toàn hơn hai updates rời.
5. **Backfill cần idempotent và guarded**; không overwrite những field mới đã có giá trị hợp lệ.
6. **$rename có thể ghi đè target**; không dùng tùy tiện trên documents chứa old/new fields xung đột.
7. **$unset chỉ nên ở contract**, khi không còn old readers/writers và rollback không cần field cũ.
8. **Indexes, validators, events, DTOs và background jobs đều là một phần của schema migration**, không chỉ documents.
9. **Phải đo correctness**, bao gồm missing, invalid, drift và queued old events, không chỉ kiểm tra app có lỗi hay không.
10. **Rollback là một yêu cầu thiết kế từ đầu**. Sau khi stop dual-write, xóa old fields hoặc siết validator, rollback về binary cũ thường cần data migration ngược hoặc forward fix.

Khi làm đúng, MongoDB cho phép tiến hóa schema gần như không làm gián đoạn người dùng: các phiên bản ứng dụng được mở rộng khả năng đọc trước, writers và dữ liệu được chuyển dần, sau đó mới thu hẹp về schema mới. **Bí quyết là thay đổi từng pha có điều kiện xác nhận, không để một lệnh cập nhật dữ liệu đi trước khả năng tương thích của cả hệ thống.**

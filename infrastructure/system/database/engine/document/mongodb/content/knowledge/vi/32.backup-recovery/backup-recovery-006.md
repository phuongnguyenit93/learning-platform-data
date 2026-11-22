# Phân biệt mongoexport, mongoimport với công cụ sao lưu đầy đủ trong MongoDB

## 1. Mục tiêu bài học

Giả sử một hệ thống MongoDB đang lưu đơn hàng, khách hàng, giao dịch và dữ liệu quản trị. Bạn cần:

- Gửi bảng đơn hàng cho nhóm phân tích dữ liệu dưới dạng **CSV**.
- Chuyển một phần document sang một collection thử nghiệm bằng **JSON**.
- Di chuyển dữ liệu từ môi trường cũ sang môi trường mới, giữ kiểu BSON và index.
- **Phục hồi sau sự cố xóa nhầm** lúc 14:20 mà vẫn giữ các thay đổi hợp lệ trước đó.
- Khôi phục cả **replica set** hoặc **sharded cluster** sau lỗi hạ tầng.
- Chứng minh được **RPO** và **RTO** cho yêu cầu vận hành.

Không thể mặc định giải quyết tất cả bằng một lệnh `mongoexport`.

MongoDB cung cấp những nhóm công cụ khác nhau:

1. **`mongoexport` và `mongoimport`**: xuất/nhập **dữ liệu document** giữa MongoDB và JSON/CSV/TSV cho mục đích trao đổi dữ liệu, tích hợp, làm sạch hoặc nạp dữ liệu.
2. **`mongodump` và `mongorestore`**: tạo/khôi phục **bản dump logic ở định dạng BSON**, có metadata collection/index phù hợp; có hỗ trợ oplog để tạo bản dump nhất quán của **replica set** trong những điều kiện cụ thể.
3. **Filesystem/cloud snapshots và dịch vụ backup có phối hợp**: giải pháp backup cho deployment, có thể kết hợp snapshots, oplog, lưu trữ nhiều bản sao và **point-in-time recovery** (PITR) trong một khoảng retention được cấu hình.

> **Thông điệp quan trọng:** Tài liệu chính thức MongoDB nói rõ: **`mongoexport` không phải công cụ sao lưu một deployment**. Nó không mang theo đủ trạng thái và metadata để tự phục hồi một hệ thống MongoDB hoạt động đúng như trước.

Sau bài học, bạn có thể:

- Chọn công cụ đúng theo mục tiêu **export**, **migration**, **logical backup**, **snapshot backup** hoặc **PITR**.
- Hiểu khác biệt giữa JSON/CSV, **Extended JSON** và BSON.
- Thực hành `mongoexport`, `mongoimport`, `mongodump`, `mongorestore` trên database lab.
- Nhận diện metadata bị mất khi chỉ chuyển documents: indexes, unique constraints, collection options, validators, views, users và roles.
- Hiểu giới hạn `mongodump --oplog`/`mongorestore --oplogReplay` và vì sao backup toàn sharded cluster cần phối hợp.
- Đánh giá snapshot, Atlas Cloud Backups, Continuous Cloud Backups, RPO/RTO, bảo mật và chi phí.
- Thiết kế một **khôi phục có thể kiểm chứng**, thay vì chỉ tạo ra file có tên “backup”.

---

## 2. Bốn khái niệm phải phân biệt

### 2.1. Data export — xuất dữ liệu

**Data export** là chuyển dữ liệu sang một định dạng khác, chẳng hạn JSON hoặc CSV.

Ví dụ:

```text
MongoDB orders collection
        |
    mongoexport
        |
     orders.csv
        |
   BI / spreadsheet
```

Thường dùng cho:

- Báo cáo, phân tích.
- Trao đổi dữ liệu với ứng dụng bên ngoài.
- Chuyển một subset nhỏ theo bộ lọc.
- Hỗ trợ điều tra có kiểm soát.
- Nạp dữ liệu thử nghiệm.

File CSV có thể đủ để phân tích doanh số, nhưng **không biết** collection từng có unique index, TTL index, schema validator, phân quyền và những quy tắc lưu trữ nào.

### 2.2. Data import — nạp dữ liệu

**Data import** là đưa những documents từ JSON/CSV/TSV vào một collection MongoDB.

```text
orders.json
    |
 mongoimport
    |
 MongoDB collection
```

Nó thích hợp:

- Nhập dữ liệu nguồn từ đối tác.
- Nạp seed data.
- Chuyển dữ liệu dạng JSON/CSV.
- Hợp nhất/upsert theo khóa được thiết kế rõ.

**Import không đồng nghĩa restore toàn hệ thống.** Nó xử lý dữ liệu ở tầng document, không tự tái tạo đầy đủ thiết kế database.

### 2.3. Logical backup — bản dump logic

**Logical backup** lưu các documents/metadata ở mức database, không phải copy nguyên từng file của storage engine.

```text
MongoDB collection + BSON + metadata
                 |
             mongodump
                 |
          *.bson + *.metadata.json
                 |
             mongorestore
                 |
           MongoDB restored data
```

Với cấu hình thích hợp, `mongodump` lưu BSON documents và metadata collection/index. Có thể hữu ích cho khôi phục database hoặc migration tương thích.

Nhưng **logical dump đơn giản** chưa chắc là backup nhất quán khi có concurrent writes; cần chú ý replica set, oplog, các hạn chế với sharded cluster và quyền users/roles.

### 2.4. Deployment backup / disaster recovery

Một **backup deployment** thực sự cần cân nhắc:

- Dữ liệu đầy đủ cần bảo vệ.
- Metadata, cấu hình, indexes, users/roles và dependency ngoài database.
- **Tính nhất quán** trong một thời điểm.
- Recovery point / time objectives.
- Bản sao lưu an toàn, có version, nằm ngoài failure domain của production.
- Khả năng phục hồi, kiểm chứng và chạy lại ứng dụng.
- Backup retention, audit, mã hóa và quyền truy cập.

Công cụ có thể là:

- MongoDB Atlas Cloud Backups / Continuous Cloud Backups.
- Giải pháp backup có phối hợp, như các dịch vụ MongoDB được hỗ trợ.
- Filesystem snapshots được thực hiện đúng quy trình.
- Logical dumps với điều kiện thích hợp.
- Kết hợp nhiều lớp để đạt chính sách tổ chức.

**Backup không được định nghĩa bởi đuôi file `.json`, `.bson` hay `.zip`; được định nghĩa bởi khả năng phục hồi trạng thái được yêu cầu.**

---

## 3. Bảng quyết định nhanh

| Tiêu chí | `mongoexport` | `mongoimport` | `mongodump` | `mongorestore` | Snapshot/managed backup |
| --- | --- | --- | --- | --- | --- |
| Vai trò | Xuất documents | Nạp documents | Tạo logical dump | Khôi phục logical dump | Tạo/khôi phục backup deployment |
| Định dạng chính | Extended JSON, CSV | JSON, CSV, TSV | BSON + metadata, archive | BSON/metadata dump | Storage snapshot + metadata/oplog theo hệ thống |
| Dùng cho BI/Excel | Phù hợp với CSV | Không phải hướng chính | Không trực tiếp | Không trực tiếp | Không |
| Giữ BSON types | Extended JSON có thể giữ theo cách encode | Extended JSON có thể tái tạo type | **Có** ở định dạng BSON | **Có** khi restore tương thích | **Có** trong snapshot đúng |
| Giữ collection/index metadata | **Không** | **Không** tự xây từ export | **Có phạm vi phù hợp** | Tạo lại từ metadata khi có | Theo coverage backup |
| Giữ user/role | Không | Không | Phụ thuộc phạm vi/tùy chọn | Phụ thuộc dump và restore options | Theo backup scope |
| Ghi nhận mọi thay đổi trong khi chạy | Không bảo đảm | Không áp dụng | Có lựa chọn `--oplog` cho replica set | Có `--oplogReplay` cho dump phù hợp | PITR nếu dịch vụ hỗ trợ |
| Backup nhất quán của sharded cluster | **Không** | Không | **Không chỉ bằng `--oplog` qua mongos** | Không hỗ trợ `--oplogReplay` sharded | Dùng quy trình có phối hợp |
| Phục hồi tới mốc thời gian tùy chọn | Không | Không | Chỉ trường hợp/khung oplog giới hạn | Không phải continuous PITR hoàn chỉnh | Continuous backup có PIT window |
| Phù hợp production DR | Không | Không | Có thể là một thành phần, cần thiết kế đúng | Thành phần restore | Thường là lựa chọn chính |
| Nguy cơ thao tác sai | Xuất PII, thiếu dữ liệu | Trùng/xóa collection, đổi type | Tăng tải, inconsistent dump | Ghi đè/xóa dữ liệu đích | Restore nhầm target/point, mất dữ liệu mới |

Lưu ý: `mongodump` và `mongorestore` thuộc **MongoDB Database Tools**, không phải bằng chứng tự động rằng toàn topology, secrets, deployment configuration hay search indexes đã được phục hồi.

---

## 4. MongoDB Database Tools chạy ở đâu?

`mongoexport`, `mongoimport`, `mongodump`, `mongorestore` là **chương trình dòng lệnh hệ điều hành**.

Không chạy như JavaScript trong `mongosh`:

```javascript
// SAI nếu gõ trực tiếp trong mongosh:
mongoexport --db=shop --collection=orders;
```

Thay vào đó, mở terminal:

```bash
mongoexport --version
mongoimport --version
mongodump --version
mongorestore --version
```

Ở nhiều phiên bản MongoDB, Database Tools có release numbering riêng, ví dụ `100.x`, **không đồng nhất với version MongoDB Server**. Kiểm tra compatibility matrix, đặc biệt khi dump và restore qua khác version/FCV.

### 4.1. Kết nối và credentials

Ví dụ local lab không auth:

```bash
mongoexport \
  --uri="mongodb://127.0.0.1:27017" \
  --db=export_backup_lab \
  --collection=orders \
  --out=orders.json
```

Trên production:

- Dùng TLS và xác minh CA/hostname.
- Dùng user có quyền tối thiểu cần thiết.
- Không hardcode password trong URI được commit lên Git.
- Tránh đưa password vào process list hoặc shell history.
- Dùng password prompt hoặc `--config` theo hướng dẫn Database Tools, với file quyền hạn chế.
- Không upload file export chứa dữ liệu nhạy cảm vào công cụ bên ngoài không được phép.

Ví dụ `--config` là cách quản lý secrets cho Database Tools hiện đại, nhưng **không đưa nội dung cấu hình có mật khẩu** vào ví dụ giảng dạy.

### 4.2. Thư mục và shell

Các ví dụ shell dưới đây dùng cú pháp Bash trên Linux/macOS hoặc terminal tương thích. Với Windows PowerShell, cách xuống dòng, quoting, đường dẫn và xử lý ký tự `$` khác; tránh copy lệnh chứa JSON query nguyên xi mà không điều chỉnh shell.

---

## 5. Lab: tạo dữ liệu có nhiều kiểu BSON và metadata

Để thấy export/import khác backup thế nào, lab cần cả **dữ liệu** và **quy tắc collection**.

Mở `mongosh` kết nối local lab. Các lệnh `drop()` chỉ dùng trong database thử nghiệm; **không chạy trên production**.

```javascript
const lab = db.getSiblingDB("export_backup_lab");

lab.orders.drop();
lab.orders_from_json.drop();
lab.orders_from_csv.drop();
lab.orders_from_bson.drop();

lab.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "orderId",
        "createdAt",
        "amount",
        "status"
      ],
      properties: {
        tenantId: { bsonType: "string" },
        orderId: { bsonType: "string" },
        createdAt: { bsonType: "date" },
        amount: { bsonType: "decimal" },
        status: {
          enum: ["NEW", "PAID", "CANCELLED"]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});

lab.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true, name: "uq_tenant_order" }
);

lab.orders.createIndex(
  { createdAt: -1 },
  { name: "ix_createdAt_desc" }
);

lab.orders.insertMany([
  {
    _id: ObjectId("650000000000000000000001"),
    tenantId: "tenant-A",
    orderId: "A-100",
    createdAt: ISODate("2026-11-14T08:00:00Z"),
    amount: NumberDecimal("125.50"),
    status: "PAID",
    quantity: NumberInt(2),
    sequence: NumberLong("9007199254740993"),
    shipping: {
      city: "Hà Nội",
      region: "Bắc Bộ"
    },
    tags: ["vip", "online"]
  },
  {
    _id: ObjectId("650000000000000000000002"),
    tenantId: "tenant-A",
    orderId: "A-101",
    createdAt: ISODate("2026-11-14T08:05:00Z"),
    amount: NumberDecimal("0.99"),
    status: "NEW",
    quantity: NumberInt(1),
    sequence: NumberLong("9007199254740994"),
    shipping: { city: "Đà Nẵng" },
    tags: ["online"]
  },
  {
    _id: ObjectId("650000000000000000000003"),
    tenantId: "tenant-B",
    orderId: "B-200",
    createdAt: ISODate("2026-11-14T08:12:00Z"),
    amount: NumberDecimal("99999.01"),
    status: "CANCELLED",
    quantity: NumberInt(3),
    sequence: NumberLong("9007199254740995"),
    shipping: { city: "TP.HCM" },
    tags: []
  },
  {
    _id: ObjectId("650000000000000000000004"),
    tenantId: "tenant-B",
    orderId: "B-201",
    createdAt: ISODate("2026-11-14T08:20:00Z"),
    amount: NumberDecimal("45.00"),
    status: "PAID",
    quantity: NumberInt(1),
    sequence: NumberLong("9007199254740996"),
    shipping: {
      city: "Cần Thơ",
      region: "Đồng bằng sông Cửu Long"
    },
    tags: ["app"]
  }
]);

lab.orders.countDocuments({});
// 4
```

Bốn bản ghi chứa:

- `_id` kiểu **ObjectId**.
- `createdAt` kiểu **Date**.
- `amount` kiểu **Decimal128**.
- `quantity` kiểu **Int32**.
- `sequence` kiểu **Int64**, cố ý lớn hơn số nguyên an toàn của JavaScript.
- Object lồng nhau và array.
- Unique index, secondary index và `$jsonSchema` validator.

Nếu một phương pháp chỉ giữ **dữ liệu dưới dạng text**, các quy tắc bảo vệ dữ liệu có thể biến mất dù số document vẫn là 4.

### 5.1. Kiểm tra kiểu BSON và index

```javascript
lab.orders.aggregate([
  {
    $project: {
      _id: 0,
      orderId: 1,
      idType: { $type: "$_id" },
      amountType: { $type: "$amount" },
      dateType: { $type: "$createdAt" },
      quantityType: { $type: "$quantity" },
      sequenceType: { $type: "$sequence" }
    }
  }
]).toArray();

lab.orders.getIndexes();
lab.getCollectionInfos({ name: "orders" });
```

Lệnh đầu cho thấy kiểu như `objectId`, `decimal`, `date`, `int`, `long`. Các lệnh sau giúp nhìn index definitions và collection options/validator.

---

## 6. `mongoexport`: xuất JSON để chuyển dữ liệu

Trong terminal:

```bash
mongoexport \
  --uri="mongodb://127.0.0.1:27017" \
  --db=export_backup_lab \
  --collection=orders \
  --type=json \
  --out=orders.json
```

Mặc định JSON export của Database Tools hiện đại dùng **Extended JSON v2, relaxed mode**. Theo định dạng mặc định, mỗi document được viết trên **một dòng JSON** (JSON Lines/NDJSON-like), không phải một mảng JSON duy nhất.

Dữ liệu Date/ObjectId có thể trông như:

```json
{
  "_id": { "$oid": "650000000000000000000001" },
  "createdAt": { "$date": "2026-11-14T08:00:00Z" },
  "amount": { "$numberDecimal": "125.50" }
}
```

**Ví dụ chỉ trích một phần document**; file xuất thực tế còn fields khác và thường ghi một document trên một dòng.

### 6.1. Extended JSON không phải JSON thuần nghiệp vụ

BSON có những kiểu mà JSON gốc không mô tả trực tiếp:

- `ObjectId`.
- `Date`.
- `Decimal128`.
- `Int32` và `Int64`.
- `Timestamp`.
- `Binary`.
- `RegularExpression`, `MinKey`, `MaxKey`...

MongoDB **Extended JSON** dùng những wrapper như:

```json
{ "$oid": "650000000000000000000001" }
```

```json
{ "$date": "2026-11-14T08:00:00Z" }
```

```json
{ "$numberDecimal": "125.50" }
```

```json
{ "$numberLong": "9007199254740993" }
```

Khi import bằng `mongoimport` hỗ trợ Extended JSON đúng version/format, những wrapper này giúp tái tạo các BSON types. Nhưng khi một hệ thống khác coi wrapper là object JSON bình thường, nó có thể không hiểu kiểu MongoDB.

### 6.2. Canonical vs relaxed

Tùy mục tiêu:

```bash
# Mặc định: Extended JSON relaxed.
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --out=orders-relaxed.json
```

```bash
# Canonical: diễn đạt BSON types một cách tường minh hơn.
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --jsonFormat=canonical \
  --out=orders-canonical.json
```

Canonical giúp rõ Int32/Int64/Double representation hơn:

```json
{ "quantity": { "$numberInt": "2" } }
```

```json
{ "sequence": { "$numberLong": "9007199254740993" } }
```

**Khuyến nghị:** Nếu mục tiêu là chuyển dữ liệu có kiểu BSON quan trọng mà vẫn dùng JSON, ưu tiên **Extended JSON canonical** và kiểm thử với `mongoimport` cùng Database Tools version. Nếu mục tiêu là BI, relaxed JSON/CSV có thể dễ tiêu thụ hơn nhưng cần hợp đồng kiểu rõ.

### 6.3. Một JSON array thay vì mỗi dòng một object

```bash
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --jsonArray \
  --out=orders-array.json
```

Mặc định export **không** có `--jsonArray`. Nếu file import là một JSON array, tương ứng phải khai báo `mongoimport --jsonArray`.

### 6.4. Export một subset

```bash
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --query='{"status":"PAID"}' \
  --out=paid-orders.json
```

Kết quả fixture có **2 đơn PAID**.

Một filter theo ngày cần Extended JSON cho Date:

```bash
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --query='{"createdAt":{"$gte":{"$date":"2026-11-14T08:10:00Z"}}}' \
  --out=recent-orders.json
```

Kết quả fixture có **2 documents** được tạo từ 08:10 UTC trở đi.

**Lưu ý shell:** Trên Bash, single quotes bảo vệ ký tự `$gte`, `$date` khỏi expansion. PowerShell/Windows quoting cần điều chỉnh theo shell.

### 6.5. Export với `--queryFile`

Khi query phức tạp, có thể đặt filter Extended JSON vào file:

```json
{
  "status": "PAID",
  "createdAt": {
    "$gte": {
      "$date": "2026-11-14T08:00:00Z"
    }
  }
}
```

Sau đó:

```bash
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --queryFile=paid-after-date.json \
  --out=paid-orders-filtered.json
```

File query là dữ liệu có thể chứa thông tin nhạy cảm. Kiểm soát path và quyền đọc.

### 6.6. Sort, limit và skip

```bash
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --sort='{"createdAt":1,"_id":1}' \
  --limit=2 \
  --out=first-two.json
```

Nếu cần export theo trang, phải xác định **thứ tự ổn định** và kế hoạch chống skip/duplicate khi dữ liệu thay đổi. `--skip` sâu vẫn có chi phí và không tự tạo snapshot consistency.

**Đừng** chia một production collection đang có writes thành nhiều file `--skip`/`--limit` rồi gọi đó là backup đầy đủ. Documents có thể được thêm/xóa giữa các lượt và thay đổi vị trí.

---

## 7. `mongoexport` sang CSV: thuận tiện nhưng mất thông tin kiểu

Xuất những cột dễ phân tích:

```bash
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --type=csv \
  --fields=tenantId,orderId,status,amount,createdAt \
  --out=orders.csv
```

Với CSV, **bắt buộc chỉ định fields** qua `--fields` hoặc `--fieldFile`.

File sẽ có các cột tương tự:

```csv
tenantId,orderId,status,amount,createdAt
tenant-A,A-100,PAID,125.50,2026-11-14T08:00:00.000Z
```

Đây là **hình thức minh họa**, biểu diễn chính xác của các giá trị phụ thuộc Database Tools version/cách serializer diễn đạt kiểu. Điều quan trọng là **CSV không có BSON type tags** và không lưu các collection rules.

### 7.1. Những gì CSV có thể làm mất

- Không tự phân biệt string `"0012"` và số `12` theo schema.
- Không có ObjectId/Date/Decimal128 type wrapper.
- Không giữ nested objects/arrays như BSON structure một cách tự nhiên.
- Không có index, collection validator, view definition.
- Không thể tự phân biệt null, missing hoặc blank trong mọi tình huống.
- Có thể gặp vấn đề Unicode/encoding ở công cụ phân tích.
- Spreadsheet có thể tự chuyển chuỗi dài thành number/scientific notation.

Ví dụ `sequence = 9007199254740993` vượt số nguyên an toàn của JavaScript. Nếu một hệ thống đọc CSV qua floating-point number mà không có ràng buộc kiểu, giá trị có thể bị thay đổi.

### 7.2. CSV là hợp đồng dữ liệu, không phải bản sao BSON

Khi chuyển CSV, cần có tài liệu schema riêng:

| Field | Type nghiệp vụ | Quy tắc |
| --- | --- | --- |
| `tenantId` | String | Không được thiếu |
| `orderId` | String | Giữ nguyên leading zeros nếu có |
| `amount` | Decimal string | Không convert qua binary float nếu cần tiền tệ chính xác |
| `createdAt` | ISO 8601 UTC | Không tự đoán timezone |
| `status` | Enum | NEW/PAID/CANCELLED |

Nếu người nhận mở CSV bằng spreadsheet, cần chú ý **CSV formula injection**: các giá trị từ người dùng bắt đầu bằng `=`, `+`, `-` hoặc `@` có thể bị spreadsheet diễn giải là công thức. Kiểm soát xuất dữ liệu khi đưa cho người khác mở, đặc biệt nội dung nhập tự do.

---

## 8. `mongoimport`: nhập JSON/CSV, không tự tái tạo database

### 8.1. Import JSON vào collection khác

```bash
mongoimport \
  --uri="mongodb://127.0.0.1:27017" \
  --db=export_backup_lab \
  --collection=orders_from_json \
  --type=json \
  --file=orders-canonical.json
```

Với lab, collection đích mới ban đầu trống, nên dự kiến có **4 documents**. `mongoimport` có thể nhận Extended JSON v2 Canonical/Relaxed và tạo BSON types tương ứng.

Kiểm tra bằng `mongosh`:

```javascript
const lab = db.getSiblingDB("export_backup_lab");

lab.orders_from_json.countDocuments({});
// 4

lab.orders_from_json.aggregate([
  {
    $project: {
      _id: 0,
      orderId: 1,
      amountType: { $type: "$amount" },
      createdAtType: { $type: "$createdAt" },
      sequenceType: { $type: "$sequence" }
    }
  }
]).toArray();
```

**Nhưng hãy so metadata:**

```javascript
lab.orders.getIndexes();
lab.orders_from_json.getIndexes();

lab.getCollectionInfos({ name: "orders" });
lab.getCollectionInfos({ name: "orders_from_json" });
```

`orders_from_json` thường chỉ có **index `_id` mặc định**, không tự có `uq_tenant_order`, `ix_createdAt_desc` hay `$jsonSchema` validator đã định nghĩa ở nguồn.

### 8.2. Import JSON array

Nếu nguồn được export bằng `--jsonArray`:

```bash
mongoimport \
  --db=export_backup_lab \
  --collection=orders_from_json \
  --type=json \
  --jsonArray \
  --file=orders-array.json
```

Chạy vào collection đã có cùng `_id` sẽ gây duplicate key error hoặc xung đột tương ứng; **không dùng ví dụ này để import đè ngay trên một collection đã nạp**. Trong lab, cần dùng collection đích khác hoặc xóa riêng collection lab theo chủ đích.

### 8.3. Import CSV

```bash
mongoimport \
  --db=export_backup_lab \
  --collection=orders_from_csv \
  --type=csv \
  --headerline \
  --file=orders.csv
```

`--headerline` báo dòng đầu là tên field. Nếu bỏ nó, header có thể bị coi là dữ liệu hoặc cần cấu hình fields khác.

Sau import, **không được giả định** `amount` trở thành Decimal128, `createdAt` trở thành Date và `sequence` trở thành Int64. CSV không mang type information; có thể dùng `--columnsHaveTypes`, field type conversion hoặc ETL validation/transform riêng theo Database Tools documentation.

Kiểm tra:

```javascript
lab.orders_from_csv.find(
  {},
  { _id: 0, orderId: 1, amount: 1, createdAt: 1 }
).limit(4).toArray();

lab.orders_from_csv.aggregate([
  {
    $project: {
      orderId: 1,
      amountType: { $type: "$amount" },
      dateType: { $type: "$createdAt" }
    }
  }
]).toArray();
```

Đây là lý do CSV thường phù hợp **trao đổi** hơn là backup.

### 8.4. Import mode và idempotency

`mongoimport` có `--mode` điều khiển cách xử lý document trùng, chẳng hạn:

- `insert`: thêm document; duplicate key có thể gây lỗi.
- `upsert`: cập nhật/thêm theo khóa upsert.
- `merge`: hợp nhất trường cho document có khóa tương ứng.
- `delete`: xóa records phù hợp input/khóa theo ngữ nghĩa của version.

Ví dụ khi collection đích đã có **unique index** trên `(tenantId,orderId)` và bạn muốn upsert theo cặp đó:

```bash
mongoimport \
  --db=export_backup_lab \
  --collection=orders_from_json \
  --file=orders-canonical.json \
  --mode=upsert \
  --upsertFields=tenantId,orderId
```

**Cần kiểm tra trước:**

1. Các trường dùng upsert key tồn tại ở mọi document.
2. Đích có unique index và business uniqueness đúng phạm vi.
3. Update semantics phù hợp (replace/merge khác nhau).
4. Không ghi đè sửa đổi production bằng dữ liệu cũ.
5. Có rollback và đối chiếu sau import.

`--mode=upsert` không biến một import file thành restore nhất quán hoặc exactly-once migration khi có concurrent writes.

### 8.5. `--drop` có thể phá dữ liệu đích

```bash
# CHỈ LAB, KHÔNG CHẠY TRÊN PRODUCTION:
mongoimport \
  --db=export_backup_lab \
  --collection=orders_from_csv \
  --drop \
  --type=csv \
  --headerline \
  --file=orders.csv
```

`--drop` xóa collection đích và các indexes liên quan trước khi import. **Không có chức năng undo** từ riêng lệnh import.

Không dùng `--drop` trên collection production khi chưa có maintenance approval, backup phục hồi được và kế hoạch dừng traffic.

---

## 9. Vì sao mongoexport/mongoimport không phải backup đầy đủ?

### 9.1. Mất metadata

`mongoexport` chủ yếu xuất **document data**.

Không được kỳ vọng nó đi kèm:

- Index definitions và compound indexes.
- `unique`, `partialFilterExpression`, TTL index settings.
- Collection validators và collection options.
- Collection-level default collation.
- Views và view pipelines.
- Users, roles, privilege assignments.
- Replica set configuration/topology.
- Shard keys, chunk placement và config metadata.
- Internal credentials, TLS certificates, encryption keys.
- Backup policy, oplog continuity và restore checkpoints.

Nhiều thông tin trên cần được backup/khôi phục hoặc tái triển khai bằng **cơ chế khác** ngay cả khi dùng một logical dump.

### 9.2. Mất invariant dữ liệu

Giả sử collection nguồn có:

```javascript
lab.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true }
);
```

Nếu chỉ import JSON vào collection mới, index này không tự xuất hiện. Hai đơn trùng `(tenantId,orderId)` với `_id` khác nhau có thể được nhập, trong khi nguồn cấm.

Đây là lỗi nghiệp vụ mà `countDocuments()` bằng nhau **không phát hiện**.

### 9.3. Không bảo đảm nhất quán giữa các collection

Giả sử:

```text
10:00:00  Export orders bắt đầu
10:00:30  Ứng dụng tạo invoice cho order mới
10:01:00  Export invoices bắt đầu
```

Các file export có thể chứa invoice nhưng thiếu order tương ứng, hoặc ngược lại. Một tập JSON files lấy ở các thời điểm khác nhau **không phải một cluster-wide point-in-time snapshot**.

Mongoexport không tự thu oplog và replay để đưa nhiều collections về một thời điểm chung.

### 9.4. Không bảo đảm DR khi mất cả deployment

Ngay cả khi có hàng triệu JSON documents, vẫn cần:

- Chọn MongoDB server version/topology mới.
- Cấu hình users/roles, network/TLS/keys.
- Tạo collection schema/indexes.
- Xử lý dữ liệu bị thay đổi trong lúc export.
- Kiểm tra transaction/business consistency.
- Kiểm tra application startup/connection.
- Đo thời gian nạp lại.

Một file export có thể rất có ích cho ETL, nhưng **không đáp ứng RTO/RPO** nếu restore mất hàng ngày.

---

## 10. `mongodump`: logical BSON backup

`mongodump` là một trong các **MongoDB Database Tools** dùng để tạo dump logic.

Khác JSON export, dump chứa documents dưới dạng **BSON** và các metadata files giúp `mongorestore` dựng collection/index options.

### 10.1. Dump database lab

Terminal:

```bash
mongodump \
  --uri="mongodb://127.0.0.1:27017" \
  --db=export_backup_lab \
  --out=./dump-lab
```

Ví dụ cấu trúc output:

```text
dump-lab/
  export_backup_lab/
    orders.bson
    orders.metadata.json
    orders_from_json.bson
    orders_from_json.metadata.json
    orders_from_csv.bson
    orders_from_csv.metadata.json
```

Những collection nào có thật ở thời điểm dump mới xuất hiện. Tên file có thể được encode theo conventions của Database Tools.

Phân biệt:

- `.bson` chứa BSON documents.
- `.metadata.json` chứa index definitions và collection metadata liên quan (bằng Extended JSON).
- Dump logical **không phải raw WiredTiger data files**.

### 10.2. Vì sao BSON tốt hơn CSV cho backup logic?

BSON giữ type information của `ObjectId`, `Date`, `Decimal128`, `Int32`, `Int64`, binary và nested fields theo format MongoDB.

`mongodump` cũng có metadata của collection/index, giúp `mongorestore` khôi phục nhiều collection options. Nó không phải thao tác chuyển qua một bảng phẳng.

**Tuy vậy:** BSON dump vẫn là logical dump; có những trạng thái cluster/hạ tầng mà nó không tự mang theo (network rules, certs, passwords ngoài database, automation config, Search index data, backup retention...).

### 10.3. Dump một collection

```bash
mongodump \
  --db=export_backup_lab \
  --collection=orders \
  --out=./dump-orders
```

Hữu ích để chuyển/khôi phục subset nhỏ. Nhưng không đồng nghĩa có snapshot consistent của tất cả collections khi writes đang diễn ra.

### 10.4. Archive và gzip

```bash
mongodump \
  --db=export_backup_lab \
  --archive=orders-lab.archive.gz \
  --gzip
```

Có thể chuyển thành một file archive nén thay vì một thư mục files. `--archive` và `--out` không được dùng chung trong cùng lệnh.

Lưu ý gzip nén file **không phải encryption**. File backup chứa dữ liệu nhạy cảm vẫn cần mã hóa, access control và quản lý retention.

### 10.5. Dung lượng/hiệu năng của mongodump

Khi chạy trên workload lớn, `mongodump` có thể:

- Đọc lượng dữ liệu lớn từ storage.
- Tốn CPU/network/I/O.
- Cạnh tranh cache/tài nguyên với queries production.
- Tạo file dump lớn trên destination disk.
- Làm tăng thời gian backup khi dataset tăng.
- Không phù hợp cho mọi RTO/RPO ở hệ thống nhiều TB.

Vì vậy, với production lớn, có thể ưu tiên coordinated filesystem/cloud snapshots và **PITR** khi đáp ứng mục tiêu vận hành. Cần benchmark quá trình dump/restore trên dataset đại diện chứ không chỉ đo thao tác backup.

---

## 11. `mongorestore`: khôi phục BSON và metadata

Khác `mongoimport`, `mongorestore` hiểu dump structure của `mongodump` và có thể tạo lại collection/index metadata khi có dữ liệu metadata phù hợp.

### 11.1. Restore vào database khác trên môi trường lab

Giả sử đã chạy:

```bash
mongodump \
  --db=export_backup_lab \
  --out=./dump-lab
```

Khôi phục sang `restore_lab` **đang trống**:

```bash
mongorestore \
  --uri="mongodb://127.0.0.1:27017" \
  --dir=./dump-lab \
  --nsInclude='export_backup_lab.*' \
  --nsFrom='export_backup_lab.*' \
  --nsTo='restore_lab.*'
```

**Điều kiện:** destination namespaces chưa có data gây xung đột. `--nsFrom`/`--nsTo` đổi namespace, không phải chỉnh từng `_id`.

Trong `mongosh`:

```javascript
const restored = db.getSiblingDB("restore_lab");

restored.orders.countDocuments({});
// 4, nếu dump được chụp sau khi nạp 4 orders.

restored.orders.getIndexes();
restored.getCollectionInfos({ name: "orders" });
```

So với collection được `mongoimport` từ JSON, logical BSON restore có khả năng khôi phục **unique index, `ix_createdAt_desc`, validator và collection options** từ metadata.

### 11.2. Restore archive nén

```bash
mongorestore \
  --uri="mongodb://127.0.0.1:27017" \
  --archive=orders-lab.archive.gz \
  --gzip \
  --nsFrom='export_backup_lab.*' \
  --nsTo='restore_lab.*'
```

Nên restore vào một target/database mới để kiểm tra trước. Nếu đã có `restore_lab`, cần đưa ra quyết định merge/replace riêng; không coi lệnh import nhiều lần là idempotent mặc định.

### 11.3. `--drop` trong mongorestore cũng nguy hiểm

```bash
# CHỈ ví dụ với target lab:
mongorestore \
  --db=restore_lab \
  --drop \
  ./dump-lab/export_backup_lab
```

Cú pháp/namespace mapping thực tế cần đối chiếu với Database Tools version khi sử dụng `--db` trên dump directory. **Quan trọng hơn:** `--drop` xóa target collection trước khi restore, có thể gây mất dữ liệu sản xuất.

Với recovery DR thực tế, hãy ưu tiên **restore vào environment cách ly**, validate rồi cut over, thay vì thử ngay trên production đang hoạt động.

### 11.4. Users, roles và database scope

Users/roles có các lựa chọn backup/restore riêng. Ví dụ:

- Dump toàn deployment và dump database đơn không luôn có cùng coverage.
- `mongodump --dumpDbUsersAndRoles` dùng khi backup một database và cần users/roles theo điều kiện được hỗ trợ.
- `mongorestore --restoreDbUsersAndRoles` khôi phục users/roles từ dump được tạo với tùy chọn tương ứng.
- Restore `admin` database có semantics quản lý users/roles khác; phải theo docs và quyền hợp lệ.

**Không** khẳng định chỉ `mongodump --db shop` chắc chắn giữ tất cả users/roles toàn cluster. Quyền MongoDB có thể là external auth/cert identities không nằm đơn giản trong collection business.

---

## 12. Tính nhất quán khi backup replica set có ghi đồng thời

Giả sử trong quá trình dump, ứng dụng vẫn tạo orders và payments.

```text
t0: mongodump bắt đầu
t1: order A được ghi
t2: payment A được ghi
t3: mongodump kết thúc
```

Nếu `mongodump` đọc collection `orders` tại t0, rồi `payments` tại t2, output có thể phản ánh **các thời điểm khác nhau**.

### 12.1. `mongodump --oplog` là gì?

Với **replica set member có oplog**, `mongodump --oplog` ghi nhận các oplog entries phát sinh trong lúc dump để có thể khôi phục một trạng thái nhất quán tương ứng trong khoảng dump.

Ví dụ **chỉ trên replica set được phép, không phải mongos**:

```bash
mongodump \
  --uri="mongodb://rs1.example.net:27017/?directConnection=true" \
  --oplog \
  --archive=rs-backup.archive.gz \
  --gzip
```

Tùy version/URI và topology, có thể sử dụng connection string tới replica set member có oplog theo cách Database Tools hỗ trợ.

Dump chứa:

- BSON/metadata của các database đủ điều kiện trong full dump.
- Oplog entries của khoảng diễn ra dump, chẳng hạn `oplog.bson` ở top-level nếu dump ra thư mục.

**Không có `--oplog`:** nếu writes diễn ra, bản dump không được bảo đảm phản ánh một thời điểm duy nhất.

### 12.2. Restore với `--oplogReplay`

Ví dụ khôi phục **full replica set dump** vào target cách ly và tương thích:

```bash
mongorestore \
  --uri="mongodb://restore-rs.example.net:27017" \
  --archive=rs-backup.archive.gz \
  --gzip \
  --oplogReplay
```

Phải theo tutorial đầy đủ của MongoDB để bảo đảm target mới, backup ownership, quyền và restore semantics. Ví dụ trên **không phải lệnh chạy trên production đang chứa dữ liệu**.

### 12.3. Các giới hạn bắt buộc của `--oplog`

Theo MongoDB Database Tools:

- Chỉ hoạt động trên nodes **có oplog**, như members của replica set.
- Cần **full dump** của replica set member.
- **Không** dùng `--oplog` với `--db`, `--collection`, `--query`, `--dumpDbUsersAndRoles`.
- `mongodump --oplog` **không tạo một backup nhất quán cho toàn sharded cluster qua `mongos`**.
- Có những DDL/config changes trong lúc dump khiến `mongodump --oplog` thất bại, chẳng hạn `renameCollection`, một số `$out`/role changes và thao tác cluster-wide.
- Oplog phải đủ khả dụng, không bị rollover theo cách làm dump/restore không đáp ứng yêu cầu.

**Không được viết:**

```bash
# Sai kỳ vọng: --oplog không hỗ trợ khi giới hạn --db.
mongodump --db=shop --oplog --out=./backup
```

### 12.4. Những giới hạn của `--oplogReplay`

Theo `mongorestore`:

- Cần full dump tương ứng được tạo với `--oplog`.
- Không kết hợp tùy tiện `--db`, `--collection`, `--nsInclude`, `--nsExclude`, `--nsFrom`, `--nsTo` với `--oplogReplay`.
- **Sharded clusters không hỗ trợ `mongorestore --oplogReplay`**.
- Manual `--oplogFile`/`--oplogLimit` đòi hiểu chính xác oplog, có cảnh báo nguy cơ corruption nếu dùng sai.

`mongodump --oplog` + `mongorestore --oplogReplay` giúp nhất quán **trong phạm vi full replica set dump đã thu**, nhưng **không phải hệ thống continuous backup** giữ oplog history suốt ngày/tuần để phục hồi tùy ý tới mọi thời điểm.

### 12.5. Oplog window và FCV

Oplog có retention hữu hạn. Dump dài mà oplog cần thiết không còn khả dụng là rủi ro cho backup consistency. Cũng cần tránh thay đổi **feature compatibility version (FCV)** trong thời gian dump/restore theo các giới hạn phiên bản, đặc biệt qua time-series format conversion giữa MongoDB 8.x và 9.0.

Trước một upgrade, kiểm tra tính tương thích của Database Tools, server, FCV, dump và replay. Đừng dùng `mongodump` lâu ngày từ version rất cũ để dựng phục hồi mà không rehearsal.

---

## 13. Backup sharded cluster khác backup replica set

Một sharded cluster có nhiều data subsets trên các shards và config server metadata.

```text
                      mongos
                        |
           +------------+------------+
           |            |            |
       Shard A RS   Shard B RS    Config RS
        orders A     orders B      routing/
        + indexes    + indexes     chunks
```

Nếu chỉ dump Shard A, sẽ thiếu dữ liệu trên Shard B. Nếu lấy hai snapshots không đồng bộ thời gian, các operations xuyên shard hoặc chunk migrations có thể khiến một bản ghi bị **thiếu hoặc trùng** khi ghép các tập backup.

### 13.1. Vì sao không chỉ `mongodump --oplog` qua mongos?

`mongos` là router, **không duy trì một oplog chung** cho cả cluster. MongoDB documentation ghi rõ không dùng `mongodump --oplog` làm backup sharded cluster và `mongorestore --oplogReplay` không hỗ trợ sharded cluster.

Không có một `oplog.bson` duy nhất có thể replay mọi transaction/routing change xuyên các shards như một replica set đơn.

### 13.2. Manual backup phải phối hợp

Các tutorial backup self-managed sharded cluster bằng dump hoặc filesystem snapshots có những bước nhạy cảm:

- Dừng balancer và chờ các chunk migrations hoàn tất.
- Dừng writes/schema transformations theo quy trình.
- Bảo đảm trạng thái phù hợp trên **mọi shard** và CSRS.
- Tạo backup các thành phần liên quan.
- Giữ metadata và data có thể cùng phục hồi.
- Bật lại các thành phần theo trình tự được hướng dẫn.
- Kiểm tra chunk ownership, routing và application consistency.

**Không** biến những việc này thành một script `mongodump --uri=mongos...` chạy khi cluster đang ghi và balancer còn hoạt động rồi tuyên bố có consistent backup.

### 13.3. Managed/coordinated backups

MongoDB Atlas và các giải pháp backup có phối hợp được MongoDB hỗ trợ có thể xử lý cluster-wide consistent backup cùng các hoạt động của cluster theo tính năng và phiên bản, không cần tự dừng balancer theo cách manual backup.

Nhưng cần đọc **backup coverage cụ thể**, retention, PIT availability, restore target constraints và các thao tác hậu restore như Search index rebuild.

### 13.4. Shard key/metadata không phải CSV

Sharding phụ thuộc:

- Shard key của collection.
- Chunks/ranges và placement.
- Config metadata.
- Indexes phục vụ shard key/query.
- Cluster topology và routing.

CSV chỉ là những dòng dữ liệu. Ngay cả khi nhập đầy đủ các documents, bạn **chưa khôi phục sharded deployment** nếu chưa có đúng topology, metadata, shard configuration và constraints.

---

## 14. Filesystem snapshots và physical backup

Filesystem snapshot ghi lại trạng thái **block/storage files** ở một thời điểm theo cơ chế snapshot của filesystem/storage provider.

Ví dụ công nghệ:

- LVM snapshots.
- Cloud block-volume snapshots.
- Storage appliance snapshots.
- Managed snapshots của MongoDB Atlas.

### 14.1. Lợi thế

- Có thể tạo điểm snapshot nhanh so với đọc toàn collection.
- Không cần serialize mọi BSON document thành text.
- Có thể phục hồi nguyên trạng nhiều cấu trúc storage phù hợp.
- Có thể phù hợp RTO của deployment lớn hơn logical dump.
- Có thể được tích hợp với incremental snapshots và PIT recovery.

### 14.2. Điều kiện nhất quán quan trọng

**Không** copy trực tiếp thư mục `dbPath` bằng `cp` khi `mongod` đang chạy rồi coi đó là physical backup an toàn.

Snapshots cần tuân thủ quy trình MongoDB cho storage engine, filesystem, journals và tất cả volumes. Nếu data và journal nằm ở volumes khác, chúng cần trạng thái snapshot nhất quán. Với sharded cluster, còn phải phối hợp toàn cluster.

Một snapshot ở tầng volume có thể **crash-consistent**, nhưng điều đó khác với bảo đảm mọi collection/shard/transaction nghiệp vụ nằm trong cùng logical point nếu nhiều volumes/shards không đồng bộ.

### 14.3. `fsyncLock()` và backup

MongoDB có những quy trình dùng `fsync`/`db.fsyncLock()` để giúp dừng writes phục vụ snapshot trong những hoàn cảnh được hỗ trợ. Đây là thao tác tác động availability nên:

- Chỉ làm trong runbook đã được phê duyệt.
- Biết cách unlock/recover.
- Không dùng trên production một cách thử nghiệm.
- Kiểm tra hướng dẫn version/topology.
- Xác minh các hoạt động/transactions đã được xử lý.

**Càng nhiều shard và volume, càng cần quy trình có phối hợp**, không thể ghép các snapshot độc lập theo cảm giác.

---

## 15. MongoDB Atlas Cloud Backups và Continuous Cloud Backups

Với Atlas deployment/tier hỗ trợ:

### 15.1. Cloud Backups

Atlas cung cấp snapshots theo backup policy, có retention theo giờ/ngày/tuần/tháng/năm tùy cấu hình và hỗ trợ restore theo điều kiện của dịch vụ.

Một snapshot là bản trạng thái tại một mốc. Nếu hệ thống chỉ backup định kỳ, những writes sau mốc snapshot gần nhất có thể không có trong bản phục hồi.

### 15.2. Continuous Cloud Backups (PITR)

Continuous Cloud Backups có thể kết hợp snapshot và oplog history để cho phép khôi phục tới **một mốc thời gian trong restore window** được cấu hình.

Ví dụ:

```text
09:00  Snapshot gần nhất
10:00  Orders writes
11:00  Payments writes
14:20  Xóa nhầm một collection
14:21  Phát hiện sự cố
```

Nếu có **continuous backup và PIT window** bao phủ khoảng này, có thể chọn thời điểm ngay trước sự cố theo độ phân giải/scope được Atlas hỗ trợ.

**Không mặc định** mọi Atlas cluster đều có Continuous Cloud Backups bật, mọi project đều có PITR, hoặc thời điểm chọn luôn là millisecond chính xác; phụ thuộc tier, backup policy, retention và restore mode.

### 15.3. Tác động Search indexes sau restore

Theo tài liệu Atlas, các restore loại tương ứng có thể mang theo **MongoDB Search index definitions**, nhưng **không restore dữ liệu index đã xây**; Search processes cần **initial sync/rebuild** các indexes.

Điều này có nghĩa:

- Source BSON documents có thể đã phục hồi.
- Query `$search`/`$vectorSearch` có thể chưa sẵn sàng hoặc bị ảnh hưởng trong lúc indexes xây lại.
- RTO của ứng dụng search phải tính **thời gian index rebuild**, không chỉ thời gian database restored.

Chi tiết behavior phụ thuộc loại restore/tier, nên phải rehearsal đúng kiến trúc đang dùng.

### 15.4. Restore point và restore window

PITR thường chỉ cho chọn timestamp **nằm trong restore window**. Nếu xóa nhầm dữ liệu từ 40 ngày trước nhưng chỉ giữ PIT history bảy ngày, không thể mặc định quay về đúng mốc đó.

Backup policy là **quyết định nghiệp vụ** trước sự cố, không phải tùy chọn có thể bổ sung sau khi dữ liệu đã mất.

---

## 16. RPO và RTO: chọn công cụ bằng số đo

### 16.1. RPO — Recovery Point Objective

**RPO** là mức mất dữ liệu tối đa chấp nhận được tính theo thời gian.

Ví dụ business yêu cầu:

```text
RPO <= 15 phút
```

Nếu chỉ có snapshot **6 giờ/lần** và không có PIT/continuous oplog coverage, có thể mất tới xấp xỉ sáu giờ changes khi khôi phục về snapshot gần nhất. Điều đó **không đạt RPO 15 phút**.

Một `mongoexport` chạy hằng đêm có RPO thực tế có thể đến một ngày và không có snapshot consistency.

### 16.2. RTO — Recovery Time Objective

**RTO** là thời gian tối đa để khôi phục dịch vụ về mức chấp nhận được.

RTO không chỉ là thời gian chạy `mongorestore`. Có thể gồm:

```text
Detect incident
  + Decide restore point/target
  + Provision infrastructure
  + Transfer/restore data
  + Rebuild indexes/Search indexes
  + Reconfigure credentials/network
  + Validate data and business invariants
  + Reconnect applications
  + Resume service
```

Nếu dump 1 TB mất 2 giờ để tạo nhưng restore + rebuild indexes mất 20 giờ, backup process “chạy nhanh” không nói gì về RTO.

### 16.3. Ví dụ tính RPO

```text
09:00  Snapshot backup
14:20  Incident
14:21  Sự cố được phát hiện
```

Nếu restore snapshot 09:00, có thể mất **5 giờ 20 phút** dữ liệu được ghi hợp lệ từ 09:00 đến 14:20.

Không nên nói “RPO của hệ thống là 5 giờ 20 phút” chỉ dựa một sự cố. Đó là **data loss exposure của kịch bản cụ thể**; RPO policy là ngưỡng business muốn đạt và frequency/backup system phải được thiết kế để đáp ứng.

### 16.4. Ma trận chọn backup theo RPO/RTO

| Nhu cầu | Công cụ/phương án khả dĩ | Điều kiện |
| --- | --- | --- |
| Xuất dữ liệu cho BI mỗi tuần | `mongoexport` CSV | Chấp nhận dữ liệu point-in-time không đồng nhất |
| Nạp seed data | `mongoimport` JSON | Schema/index được chuẩn bị riêng |
| Restore một database nhỏ test | `mongodump`/`mongorestore` | Metadata, types và target compatibility |
| Consistent replica set dump khi có writes | `mongodump --oplog`/`mongorestore --oplogReplay` | Full dump, oplog, không có DDL cản trở |
| Sharded cluster production DR | Coordinated backup/snapshot | Cluster-wide consistency, config metadata |
| PITR trong 15 phút | Continuous backup có oplog history | Restore window, tier, policy, rehearsal |
| Ổn định RTO cho dataset rất lớn | Snapshot/managed backups | Restore throughput, index rebuild, network |
| Tuân thủ bảo mật và lưu trữ dài hạn | Encrypted/immutable/offsite backups | Retention, audit, recovery drills |

---

## 17. Tính nhất quán nghiệp vụ không chỉ là số documents

Giả sử hệ thống có:

```javascript
// Một order.
{
  _id: "order-100",
  amount: NumberDecimal("100.00"),
  status: "PAID"
}
```

```javascript
// Một payment liên kết.
{
  _id: "payment-100",
  orderId: "order-100",
  amount: NumberDecimal("100.00")
}
```

Nếu export `orders` lúc 09:00 rồi `payments` lúc 09:05, một transaction phát sinh giữa hai thời điểm có thể tạo dữ liệu không nhất quán giữa files.

Những invariant cần kiểm tra sau restore:

- Mọi payment có order phù hợp.
- Số tiền và currency mapping đúng.
- Unique business keys không bị lặp.
- Foreign/reference relationships hợp lệ.
- Sequence/version counters không lùi.
- User/role có đúng quyền.
- Index/validator/TTL hoạt động.
- Report aggregates nằm trong khoảng hợp lý.
- Change streams/consumers có kế hoạch resume/rebuild theo checkpoint.

Chỉ kiểm tra `countDocuments()` bằng số trước backup **chưa đủ**. Trong trường hợp có TTL hoặc thay đổi hợp lệ sau restore point, count khác còn có thể là hành vi mong đợi; phải đối chiếu theo snapshot time.

---

## 18. Chiến lược kiểm chứng một bản backup

### 18.1. Backup artifact inventory

Mỗi bản backup nên có manifest/quản lý metadata ngoài dữ liệu:

```yaml
backupId: "backup-2026-11-14-0900"
environment: "staging"
deploymentType: "replicaSet"
sourceCluster: "rs0"
backupMethod: "mongodump-with-oplog"
startedAtUtc: "2026-11-14T09:00:00Z"
completedAtUtc: "2026-11-14T09:03:42Z"
mongodbVersion: "document-from-source"
databaseToolsVersion: "document-from-tools"
format: "archive-gzip"
encryptedAtRest: true
checksumAlgorithm: "SHA-256"
retentionClass: "daily"
restoreTestStatus: "pending"
```

Đây là **manifest ví dụ**, không phải định dạng tự động do MongoDB sinh. Các timestamp/versions phải ghi từ thực tế, không hardcode.

### 18.2. Kiểm tra artifact kỹ thuật

- Lệnh backup exit code thành công.
- File tồn tại, size hợp lý, không phải 0 bytes bất thường.
- Dung lượng storage destination đủ.
- Checksum được tính và lưu ngoài nơi chứa artifact.
- File được mã hóa và quyền truy cập đúng.
- Không có secret lộ trong logs.
- Backup không bị retention process xóa ngay.
- Nếu có oplog, dump và oplog segment có thể replay đúng cách.

Nhưng **file checksum hợp lệ không chứng minh backup có thể restore**.

### 18.3. Restore rehearsal

Quy trình test đáng tin:

1. Tạo target cluster cách ly, đúng version/topology cần thiết.
2. Cấp credentials/secrets phù hợp và hạn chế network.
3. Restore artifact vào target.
4. Xác minh BSON types và số documents theo snapshot time.
5. Kiểm tra indexes, validators, views, TTL và users/roles.
6. Chạy smoke test ứng dụng.
7. Kiểm tra business invariants.
8. Thử search/index readiness nếu có `$search`/`$vectorSearch`.
9. Đo thời gian từ bắt đầu sự cố giả định tới service-ready.
10. Ghi kết quả, lỗi và thay đổi runbook.

Backup chỉ có giá trị khi team **đã chứng minh có thể restore**.

### 18.4. Điểm cần lưu riêng ngoài MongoDB dump

- Secret manager references, certificate rotation plan.
- TLS CA/public trust chain và quyền truy xuất private keys phục hồi.
- Infrastructure as Code, firewall/DNS/load balancers.
- Authentication provider mappings.
- KMS configuration và encryption key recovery.
- Application schema migration version.
- Job schedulers, Kafka offsets/consumer checkpoints, integration configs.
- Search index definitions theo backup coverage.
- Monitoring/alerting và backup retention policy.

Không bỏ private keys vào cùng thư mục backup không mã hóa rồi gọi đó là “full backup”.

---

## 19. Bảo mật dữ liệu xuất và dữ liệu backup

### 19.1. JSON/CSV export cũng là dữ liệu nhạy cảm

Một file `users.csv` có thể chứa email, số điện thoại, địa chỉ, order history và trường nội bộ. Nó có thể bị:

- Gửi nhầm qua email.
- Upload lên Drive/bucket công khai.
- Commit vào repository.
- Lưu trên laptop không mã hóa.
- Đưa vào BI demo/test environment không được bảo vệ.
- Đọc bởi spreadsheet với formula injection.

**Xuất dữ liệu không được miễn chính sách bảo vệ PII.**

### 19.2. Backup nên có cơ chế bảo vệ riêng

- Mã hóa at rest và in transit.
- Access control theo least privilege.
- Retention policy có audit.
- Backup copies ngoài failure domain.
- Có immutable/WORM hoặc backup compliance controls khi yêu cầu.
- Tách quyền xóa production data và quyền xóa backup.
- Kiểm tra ability-to-restore của encryption keys.
- Không lộ user credentials trong backup scripts.

### 19.3. Quy tắc 3-2-1

Một định hướng thường gặp:

- **3 bản sao** dữ liệu.
- **2 loại media/storage** hoặc failure domains phù hợp.
- **1 bản sao offsite**.

Đây là một nguyên tắc thực hành, không phải cấu hình MongoDB tự động. Với cloud-managed backup, cần xét region, account/project isolation, immutable retention và khả năng khôi phục sau ransomware.

---

## 20. Những tình huống lựa chọn công cụ

### 20.1. Gửi báo cáo doanh số cho phòng kế toán

**Nhu cầu:** CSV có các cột `orderId`, `createdAt`, `amount`, `status`; không cần index, validator, users.

**Lựa chọn:** `mongoexport --type=csv --fields=...` với bộ lọc/anonymization cần thiết.

**Cảnh giác:** Currency precision/Decimal128, timezone, formula injection và schema mapping.

### 20.2. Nhập catalog từ đối tác

**Nhu cầu:** nhận file JSON/CSV, có thể upsert theo product SKU.

**Lựa chọn:** ETL validation + `mongoimport` hoặc ứng dụng nhập dữ liệu; tạo unique index trước và định nghĩa upsert semantics.

**Cảnh giác:** Product SKU collision, update cũ ghi đè mới, thiếu validation, không có transaction cross-collection tự động.

### 20.3. Di chuyển một collection giữa lab databases

**Nhu cầu:** giữ BSON types và indexes.

**Lựa chọn:** `mongodump --db ... --collection ...` + `mongorestore` phù hợp, hoặc migration tool.

**Cảnh giác:** Namespace mapping, metadata version và target schema compatibility.

### 20.4. Hằng ngày backup replica set nhỏ

**Nhu cầu:** bản dump logic nhất quán trong lúc writes tiếp diễn, RTO còn chấp nhận.

**Lựa chọn:** `mongodump --oplog` + `mongorestore --oplogReplay` trên full dump của replica set member, nếu đáp ứng prerequisites và giới hạn.

**Cảnh giác:** Không kết hợp `--db`, hoạt động DDL/user role trong lúc dump, oplog window và test restore.

### 20.5. Sharded cluster có transactions xuyên shards

**Nhu cầu:** backup nhất quán mà không dừng dịch vụ lâu.

**Lựa chọn:** dịch vụ coordinated backup (Atlas hoặc giải pháp được hỗ trợ) và backup policy.

**Cảnh giác:** Không chỉ `mongodump --oplog` qua `mongos`; manual backup phải dừng balancer/writes/schema changes theo docs.

### 20.6. Khôi phục tới vài giây/phút trước khi xóa nhầm

**Nhu cầu:** PITR trong một restore window và thời gian phục hồi phù hợp.

**Lựa chọn:** Continuous Cloud Backup/PIT service theo availability và policy.

**Cảnh giác:** Snapshot định kỳ không tự có PITR; oplog retention/history phải đủ, restore target được phê duyệt và search indexes có thể rebuild.

### 20.7. Dataset nhiều TB, RTO 30 phút

**Nhu cầu:** restore nhanh hơn logical import/dump.

**Lựa chọn:** ưu tiên nghiên cứu snapshot/direct-attach/managed backup topology phù hợp.

**Cảnh giác:** Chỉ khi benchmark end-to-end chứng minh RTO đạt; index rebuild, replica sync, network và application validation vẫn tốn thời gian.

---

## 21. Ước lượng chi phí và thời gian

Một phép tính throughput sơ bộ:

\[
T_{\mathrm{transfer}} =
\frac{\mathrm{BackupSizeBytes}}{\mathrm{EffectiveBytesPerSecond}}
\]

Ví dụ **giả định**:

- Backup artifact: **800 GB**.
- Restore effective throughput: **100 MB/s** (thập phân).

\[
T = \frac{800{,}000\ \mathrm{MB}}{100\ \mathrm{MB/s}}
  = 8{,}000\ \mathrm{s} \approx 2.22\ \mathrm{hours}
\]

Chỉ riêng truyền/ghi 800 GB đã mất hơn hai giờ trong giả định này, chưa kể:

- Provision cluster.
- Restore BSON decode.
- Index rebuild.
- Replica sync.
- Search index initial sync.
- Business validation.
- App reconnect.

Nếu RTO là 30 phút, giải pháp trên **không đạt**, bất kể lệnh backup đơn giản ra sao.

### 21.1. Cost of ownership

Một mô hình tổng chi phí:

```text
Monthly backup TCO =
   snapshot/object storage
 + replication / cross-region copies
 + oplog/continuous backup retention
 + data transfer / egress
 + encryption / KMS
 + restore test infrastructure
 + monitoring / alerting
 + operator engineering / on-call
```

`mongoexport` có thể tạo file rẻ và dễ đọc nhưng **không phải** thay thế cho các khoản chi này khi business cần disaster recovery.

### 21.2. Giá thành phụ thuộc RPO/RTO

- RPO càng nhỏ, thường cần lưu changes liên tục hơn.
- RTO càng nhỏ, có thể cần restore mechanism nhanh, bản sao nóng hoặc hạ tầng dự phòng.
- Retention càng dài, storage và compliance complexity tăng.
- Chạy restore rehearsal tăng chi phí nhưng giảm rủi ro không thể phục hồi.

Không tối ưu chỉ phí tạo backup; hãy tính **chi phí và khả năng phục hồi** theo SLO.

---

## 22. Lab so sánh trước–sau import/restore

### 22.1. Các bước thực hiện

1. Tạo collection `export_backup_lab.orders` có 4 documents, validator và hai indexes.
2. `mongoexport --jsonFormat=canonical` sang `orders-canonical.json`.
3. `mongoimport` sang `orders_from_json`.
4. `mongodump --db export_backup_lab --out dump-lab`.
5. `mongorestore` sang database trống `restore_lab`.
6. Dùng `mongosh` so document counts, types, indexes và collection options.

### 22.2. Kiểm chứng số documents

```javascript
const source = db.getSiblingDB("export_backup_lab");
const restored = db.getSiblingDB("restore_lab");

printjson({
  source: source.orders.countDocuments({}),
  importedJson: source.orders_from_json.countDocuments({}),
  restoredBson: restored.orders.countDocuments({})
});
```

Với fixture ban đầu và mỗi bước chạy một lần vào target trống:

```javascript
{
  source: 4,
  importedJson: 4,
  restoredBson: 4
}
```

**Đếm bằng nhau không phải chứng nhận backup hoàn chỉnh.**

### 22.3. Kiểm tra data types

```javascript
function typesFor(dbRef, collection) {
  return dbRef.getCollection(collection).aggregate([
    {
      $project: {
        _id: 0,
        orderId: 1,
        amountType: { $type: "$amount" },
        dateType: { $type: "$createdAt" },
        sequenceType: { $type: "$sequence" }
      }
    },
    { $sort: { orderId: 1 } }
  ]).toArray();
}

printjson(typesFor(source, "orders"));
printjson(typesFor(source, "orders_from_json"));
printjson(typesFor(restored, "orders"));
```

Dùng Extended JSON canonical giúp JSON import giữ kiểu BSON nếu không có biến đổi mất thông tin ở giữa. BSON dump/restore giữ native types.

### 22.4. Kiểm tra indexes và validator

```javascript
printjson(source.orders.getIndexes());
printjson(source.orders_from_json.getIndexes());
printjson(restored.orders.getIndexes());

printjson(source.getCollectionInfos({ name: "orders" }));
printjson(source.getCollectionInfos({ name: "orders_from_json" }));
printjson(restored.getCollectionInfos({ name: "orders" }));
```

Kỳ vọng:

- **Source:** `_id`, `uq_tenant_order`, `ix_createdAt_desc` và validator.
- **JSON import:** chỉ `_id` mặc định, không có validator/indexes của source.
- **BSON restore:** metadata phù hợp từ dump để dựng indexes/validator khi restore theo đúng options.

Một restore có thể thay đổi chi tiết theo version, namespace remapping và metadata compatibility; kiểm tra thực tế thay vì khẳng định mọi property luôn giống hệt.

### 22.5. Thử invariant unique

Trên `orders_from_json` (chỉ lab), nếu collection không có unique `(tenantId,orderId)`:

```javascript
const imported = source.orders_from_json;
const copy = imported.findOne({ orderId: "A-100" });

// Cùng logical business key, _id mới.
imported.insertOne({
  ...copy,
  _id: new ObjectId()
});
```

Document thứ hai có thể insert được vì collection imported không có `uq_tenant_order`. Cùng thao tác vào source có unique index sẽ gây `E11000` (nếu không vướng validator).

Điều này cho thấy **mất metadata có thể làm thay đổi business correctness** dù BSON types còn nguyên.

---

## 23. Tự động hóa backup: không chỉ chạy cron

Một job thực tế cần các giai đoạn:

```text
Scheduled trigger
       |
Preflight health/capacity
       |
Create backup artifact
       |
Check exit status + artifact manifest
       |
Encrypt / upload / immutability
       |
Verify checksum/inventory
       |
Retention / lifecycle
       |
Periodic isolated restore test
       |
Measure RPO/RTO and alert on failures
```

### 23.1. Điều kiện preflight

- Cluster/quorum đang khỏe.
- Credentials và TLS hợp lệ.
- Có đủ destination disk.
- Nếu dump replica set: oplog window đủ, không có DDL incompatible.
- Nếu sharded manual backup: đã đáp ứng đúng các điều kiện tạm dừng balancer/writes.
- Backup target không phải volume production duy nhất.
- Không có secret trong logs/command line ngoài chính sách.

### 23.2. Monitoring

| Metric | Vì sao quan trọng |
| --- | --- |
| Thời điểm backup gần nhất thành công | Biết có vượt RPO không |
| Backup duration | Phát hiện tăng trưởng/throughput giảm |
| Artifact size | Phát hiện output bất thường |
| Checksum/verification | Phát hiện file lỗi |
| Backup job failure rate | Phát hiện mất coverage |
| Restore rehearsal duration | Đo RTO thực |
| Oplog/PIT retention window | Biết earliest recoverable point |
| Storage/backup cost | Capacity và ngân sách |
| Number of isolated copies | Chống mất cùng failure domain |
| Search index rebuild time | End-to-end application readiness |

### 23.3. Alerting

Không chỉ alert “job exit code != 0”. Cần cảnh báo:

- Không có backup thành công trong **khoảng mong đợi**.
- Backup artifact quá nhỏ/bất thường.
- Snapshot/PIT retention sắp không đáp ứng RPO.
- Restore drill thất bại.
- KMS key/credential hết hạn.
- Backup storage đầy hoặc mất quyền ghi.
- Restore duration vượt RTO.
- Copy offsite thất bại.

---

## 24. Những sai lầm thường gặp

| Sai lầm | Thực tế | Hướng khắc phục |
| --- | --- | --- |
| “Có `mongoexport` hằng ngày là có backup full” | Export không có đầy đủ metadata/consistency | Backup strategy riêng |
| “JSON luôn làm mất mọi BSON types” | Extended JSON có wrappers cho nhiều types | Dùng Canonical + round-trip test |
| “CSV giữ Date/Decimal128 như BSON” | CSV không có type tags | Schema và type conversion rõ |
| “Mongoexport giữ indexes” | Chỉ export documents | Dùng dump/restore hoặc IaC index creation |
| “Mongoimport dựng validator” | Không từ JSON export | Tạo schema/index riêng |
| “Mongoimport luôn idempotent” | Insert có thể duplicate/error | Upsert keys/unique index và retry plan |
| “`--drop` chỉ xóa documents” | Xóa collection/index trước import/restore | Chỉ dùng khi chủ đích |
| “Chỉ cần `mongodump` là consistent giữa writes” | Không `--oplog` có thể không một thời điểm | Replica set full dump + oplog hoặc managed backup |
| “`mongodump --db x --oplog` hợp lệ” | Oplog mode yêu cầu full dump | Không dùng options giới hạn |
| “`--oplog` trên mongos backup toàn sharded” | Không có oplog chung | Coordinated sharded backup |
| “`mongorestore --oplogReplay` trên sharded cluster” | Không hỗ trợ | Dùng restore process tương ứng |
| “Dump BSON là bản sao filesystem” | Logical, không có WiredTiger files nguyên trạng | Phân biệt logical/physical |
| “Copy dbPath lúc server chạy là snapshot” | Không đảm bảo nhất quán | Snapshot theo docs |
| “Tắt balancer là đủ cho mọi sharded backup” | Còn writes/schema changes/transactions | Follow end-to-end tutorial |
| “Mọi Atlas cluster tự có PITR” | Phụ thuộc tier/backup policy | Kiểm tra continuous backup |
| “Backup có là chắc chắn restore được” | Có thể file lỗi, thiếu quyền/keys/metadata | Restore rehearsal |
| “RPO và RTO giống nhau” | RPO mức mất dữ liệu, RTO thời gian phục vụ lại | Đo riêng |
| “Snapshot daily đáp ứng RPO 15 phút” | Khoảng giữa snapshots dài | Continuous oplog/PIT |
| “Khôi phục DB xong là app dùng ngay” | Index build/Search sync/migrations còn thời gian | Đo end-to-end RTO |
| “Backup nằm cùng disk production vẫn an toàn” | Disk/region failure xóa cả hai | Offsite/isolated copies |
| “Gzip là encryption” | Gzip chỉ nén | Encrypt + access controls |
| “Không cần lưu CA/KMS/secret recovery plan” | Có thể không mở được backup | DR inventory ngoài DB |
| “Khôi phục đúng count là đủ” | Type/index/relationships vẫn có thể sai | Integrity checks |
| “CSV nội bộ không có rủi ro bảo mật” | Có PII và formula injection | Data governance |

---

## 25. Bài tập thực hành

### Bài 1 — Phân loại công cụ

Chọn `mongoexport`, `mongoimport`, `mongodump`/`mongorestore` hoặc managed backup:

1. Gửi CSV đơn hàng cho BI.
2. Nạp một tập JSON catalog vào collection lab.
3. Chuyển database test, giữ BSON/indexes.
4. Khôi phục toàn sharded cluster tới trước sự cố.

**Đáp án:** 1 export, 2 import, 3 dump/restore, 4 coordinated backup/PITR theo deployment.

### Bài 2 — Vai trò của mongoexport

Vì sao MongoDB khẳng định `mongoexport` **không phải deployment backup tool**? Kể ít nhất sáu metadata/system states không có trong CSV export.

### Bài 3 — Extended JSON

Viết Extended JSON canonical biểu diễn:

- `_id = ObjectId("650000000000000000000001")`.
- `amount = Decimal128("125.50")`.
- `quantity = Int32(2)`.
- `sequence = Int64("9007199254740993")`.

**Đáp án gợi ý:** Dùng `$oid`, `$numberDecimal`, `$numberInt`, `$numberLong`.

### Bài 4 — Relaxed vs Canonical

Vì sao Canonical phù hợp khi cần kiểm soát kiểu BSON hơn JSON relaxed? Có phải Canonical đã mang theo collection indexes không?

**Đáp án:** Canonical diễn đạt nhiều types tường minh hơn, **không** tự mang index metadata.

### Bài 5 — Import JSON array

Nếu export với `--jsonArray`, cần thêm cờ nào khi import?

**Đáp án:** `mongoimport --jsonArray`.

### Bài 6 — CSV schema

Xuất `amount`, `createdAt`, `sequence` thành CSV. Nêu ba lỗi khi người nhận đọc mà không có schema định nghĩa.

**Gợi ý:** Decimal precision, Date timezone/type, Int64 overflow.

### Bài 7 — Export PAID

Viết `mongoexport --query` chỉ lấy `status: "PAID"` từ collection lab. Có bao nhiêu documents trong fixture?

**Đáp án:** **2**.

### Bài 8 — Import có unique business key

Nguồn có unique `(tenantId,orderId)` nhưng collection import mới chỉ có `_id` index. Hệ thống có thể chấp nhận duplicate nào?

**Đáp án:** Hai `_id` khác nhau nhưng cùng `(tenantId,orderId)`.

### Bài 9 — `--drop`

Nếu `mongoimport --drop` vào collection production, điều gì xảy ra với indexes và documents hiện có?

**Đáp án:** Collection bị drop và indexes cùng dữ liệu bị xóa trước khi import.

### Bài 10 — Dump output

`mongodump --db=export_backup_lab --out=./dump-lab` thường tạo những loại files nào? Mỗi loại chứa gì?

**Đáp án:** `.bson` chứa documents, `.metadata.json` chứa metadata/index options.

### Bài 11 — BSON vs CSV

Tại sao BSON phù hợp khôi phục Decimal128/Date/ObjectId hơn CSV? Tại sao BSON dump chưa tự trở thành physical snapshot?

### Bài 12 — Replica set đang ghi

Một full `mongodump` chạy trong lúc writes tiếp tục. Không dùng `--oplog`, có bảo đảm các collections ở cùng một thời điểm không?

**Đáp án:** Không. Dùng `--oplog` khi đáp ứng prerequisites của replica set hoặc backup mechanism khác.

### Bài 13 — Oplog constraints

Lệnh sau có phù hợp không?

```bash
mongodump --db=shop --oplog --out=./backup
```

**Đáp án:** Không. `--oplog` yêu cầu full dump replica set member, không dùng với `--db`.

### Bài 14 — Oplog replay

Một full replica set dump đã tạo với `--oplog`. Công cụ/flag nào dùng để replay oplog khi restore?

**Đáp án:** `mongorestore --oplogReplay` trong topology được hỗ trợ.

### Bài 15 — Sharded cluster

Vì sao `mongodump --oplog` qua `mongos` không cung cấp consistent whole-cluster backup? Cần phối hợp những thành phần nào?

**Gợi ý:** Shards, CSRS, balancer, concurrent writes/schema operations và restore metadata.

### Bài 16 — Filesystem snapshot

Vì sao chạy `cp -r /var/lib/mongodb` trong lúc `mongod` hoạt động không tương đương storage snapshot nhất quán?

### Bài 17 — RPO

Snapshot cuối lúc 09:00, incident lúc 14:20, không có PIT coverage. Có thể mất bao lâu dữ liệu hợp lệ?

**Đáp án:** Tối đa theo kịch bản là **5 giờ 20 phút** kể từ snapshot.

### Bài 18 — RTO

Restore phải di chuyển 800 GB với tốc độ hiệu dụng 100 MB/s. Chỉ transfer mất bao lâu?

**Đáp án:** 8.000 giây ≈ **2 giờ 13 phút 20 giây**.

### Bài 19 — Atlas PITR

Điều kiện nào cần có để khôi phục ngay trước lần xóa nhầm lúc 14:20? Vì sao snapshot mỗi sáu giờ không tự đáp ứng RPO 15 phút?

### Bài 20 — Search index sau restore

Một hệ thống dùng MongoDB Vector Search. Source BSON restored nhưng Search index rebuild 45 phút. RTO cho API search có thể tính từ khi nào?

**Đáp án:** Khi search/index đã queryable và API đáp ứng mức dịch vụ, không phải chỉ khi MongoDB source data restore xong.

### Bài 21 — Restore verification

Thiết kế checklist ít nhất tám bước: documents, types, indexes, validators, roles, relationships, app smoke test, monitoring, Search freshness và RTO.

### Bài 22 — Backup bảo mật

Backup archive được gzip và đặt trên cùng disk với production. Kể ít nhất bốn rủi ro.

**Gợi ý:** Không mã hóa, cùng failure domain, ransomware, thiếu offsite retention, thiếu access controls.

### Bài 23 — Backup users/roles

`mongodump --db shop` có tự đảm bảo khôi phục toàn bộ users/roles của mọi database không? Nêu tùy chọn hoặc quy trình cần xem.

**Đáp án:** Không mặc định. Kiểm tra `--dumpDbUsersAndRoles`/`--restoreDbUsersAndRoles` và cách xử lý admin database theo docs.

### Bài 24 — Full backup hay data export?

Một team tạo `mongoexport` cho mọi collection qua nhiều phút, thấy counts đúng. Bằng chứng nào còn thiếu trước khi gọi đây là backup production?

**Gợi ý:** Consistency, metadata, PIT capability, RBAC, topology, secrets, RPO/RTO và rehearsal.

### Bài 25 — Chiến lược cho ba môi trường

Thiết kế chính sách cho:

- Dev: dữ liệu mẫu không nhạy cảm, phục hồi có thể làm lại.
- Staging: cần replay dữ liệu kiểm thử và schema.
- Production: RPO 15 phút, RTO 1 giờ, sharded cluster có Search indexes.

Chọn công cụ, retention, monitoring và cách kiểm tra restore.

### Bài 26 — So sánh TCO

Một logical dump rẻ để tạo nhưng restore mất 12 giờ; một snapshot service đắt hơn nhưng restore 45 phút. Nếu RTO tối đa là một giờ, phương án nào khả thi?

**Đáp án:** Phương án có RTO đã được kiểm chứng trong một giờ; chi phí thấp hơn không bù được việc vi phạm điều kiện bắt buộc.

### Bài 27 — Index/validator sau import

Chạy lab `orders` → JSON export/import → BSON dump/restore. So các kết quả `getIndexes()` và `getCollectionInfos()`. Giải thích vì sao cùng bốn documents nhưng hệ thống có thể cư xử khác.

### Bài 28 — Kế hoạch DR thực tế

Viết runbook cho trường hợp xóa nhầm collection trên production:

1. Ngăn sự cố tiếp tục.
2. Xác định timestamp cuối cùng an toàn.
3. Chọn backup/restore point.
4. Restore vào target cách ly.
5. Kiểm chứng dữ liệu và metadata.
6. Chọn cutover/migration strategy.
7. Xác nhận ứng dụng hoạt động.
8. Ghi thời gian mất dữ liệu và khôi phục.
9. Cập nhật chính sách/automation.

Giải thích những bước **không thể thay bằng `mongoimport` một file CSV**.

---

## 26. Tổng kết

Để chọn đúng công cụ sao lưu/phục hồi MongoDB, hãy bắt đầu bằng **mục tiêu nghiệp vụ**:

1. **`mongoexport`** dùng xuất JSON/CSV — hỗ trợ tích hợp, báo cáo và chuyển dữ liệu; **không phải deployment backup**.
2. **`mongoimport`** nạp JSON/CSV/TSV vào collection — cần kiểm soát kiểu BSON, indexes, uniqueness, validation và import mode; không tự khôi phục topology.
3. **`mongodump`** tạo BSON logical dump và metadata; **`mongorestore`** giúp phục hồi collection/index options trong phạm vi được hỗ trợ.
4. **`mongodump --oplog`** cùng **`mongorestore --oplogReplay`** hỗ trợ consistent full dump trên **replica set member** trong những giới hạn rõ ràng; không kết hợp với các options giới hạn database/collection.
5. **Sharded cluster** cần coordinated backup/restore, không dùng `--oplog` qua `mongos` như thể có một oplog chung.
6. **Snapshots/managed backups** có thể phù hợp hơn cho deployment lớn và RTO thấp, nhưng cần quy trình filesystem/cluster consistency đúng.
7. **PITR** yêu cầu history/retention và tính năng continuous backup phù hợp, không xuất hiện chỉ nhờ có file JSON/BSON.
8. **RPO và RTO** quyết định chiến lược; lưu được file không đồng nghĩa phục hồi được dịch vụ.
9. **Bảo mật backup** phải bao gồm encryption, offsite/immutable copies, access control và keys recovery.
10. **Restore rehearsal** là bằng chứng quan trọng nhất: cần xác minh data types, indexes, validators, users/roles, business invariants và application readiness.

**Câu hỏi cuối cùng không phải “đã export đủ số dòng chưa?” mà là “nếu production gặp sự cố, chúng ta có thể khôi phục đúng dữ liệu, metadata và dịch vụ trong RPO/RTO đã cam kết hay không?”**

### Tài liệu MongoDB chính thức

- [mongoexport — MongoDB Database Tools](https://www.mongodb.com/docs/database-tools/mongoexport/) — JSON/CSV export; tài liệu xác nhận **không phải deployment backup tool**.
- [mongoimport — MongoDB Database Tools](https://www.mongodb.com/docs/database-tools/mongoimport/) — import JSON/CSV/TSV, modes, `--drop`, `--headerline`.
- [mongoimport Examples](https://www.mongodb.com/docs/database-tools/mongoimport/mongoimport-guide/) — BSON-specific types qua Extended JSON.
- [MongoDB Extended JSON v2](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/) — Canonical/Relaxed và representations của BSON.
- [mongodump — MongoDB Database Tools](https://www.mongodb.com/docs/database-tools/mongodump/) — BSON backup, `--archive`, `--gzip`, `--oplog`.
- [mongorestore — MongoDB Database Tools](https://www.mongodb.com/docs/database-tools/mongorestore/) — metadata restore, oplog replay và limitations.
- [Back Up and Restore with MongoDB Tools](https://www.mongodb.com/docs/manual/tutorial/backup-and-restore-tools/) — logical backup workflows.
- [Back Up Self-Managed Deployment with Filesystem Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-with-filesystem-snapshots/) — block-level backups và consistency.
- [Back Up Sharded Cluster with Database Dump](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-database-dumps/) — requirements cho manual sharded backup.
- [Back Up Sharded Cluster with Filesystem Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-filesystem-snapshots/) — stopping writes/balancer và coordination.
- [Manage Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/tutorial/manage-sharded-cluster-balancer/) — dừng balancing cho manual backups.
- [Atlas Backup Guidance](https://www.mongodb.com/docs/atlas/architecture/current/backups/) — Cloud Backups, continuous backup, RPO/RTO.
- [Restore from Continuous Cloud Backup](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-from-continuous/) — PIT recovery và Search index rebuild considerations.
- [Recover a Point in Time](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/) — restore window, timestamp và yêu cầu.

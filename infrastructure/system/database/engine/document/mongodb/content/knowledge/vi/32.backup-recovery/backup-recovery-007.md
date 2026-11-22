# Khôi phục có chọn lọc, namespace, index và schema validation trong MongoDB

Hãy tưởng tượng một dịch vụ thương mại điện tử dùng MongoDB với nhiều collection: `customers`, `orders`, `payments` và `products`. Một thao tác nhầm đã xóa một số đơn hàng, nhưng các collection khác vẫn chạy bình thường và tiếp tục nhận dữ liệu mới. Nếu khôi phục **toàn bộ database** từ bản sao lưu cũ, hệ thống có thể ghi đè những đơn hàng, khách hàng hoặc thanh toán phát sinh sau thời điểm backup. Nếu chỉ phục hồi một collection mà không kiểm tra quan hệ dữ liệu, **đơn hàng có thể trỏ tới khách hàng hoặc payment không tồn tại**. Ngoài ra, khôi phục document thôi chưa đủ: **index**, **collection options** và **schema validator** ảnh hưởng trực tiếp đến tính đúng đắn và hiệu năng của dữ liệu sau phục hồi.

Trong chương **Sao lưu và phục hồi** của module **Database Engine Document MongoDB**, bài này giải thích cách **khôi phục có chọn lọc**, giới hạn phạm vi theo **namespace**, cách xử lý **index** và **schema validation**, đồng thời xây dựng quy trình vận hành an toàn khi cần lấy lại một phần dữ liệu từ backup.

Mục tiêu:

1. Phân biệt phục hồi toàn bộ cluster, một database, một collection và một tập document.
2. Dùng `mongodump`/`mongorestore` với `--nsInclude`, `--nsExclude`, `--nsFrom` và `--nsTo`.
3. Hiểu lúc nào `--drop` có thể phá hủy dữ liệu đang có, và vì sao nên phục hồi vào **staging namespace** trước.
4. Biết metadata backup liên quan tới **index, collation, collection options, validator** như thế nào.
5. Phân biệt restore **data** với restore **schema/configuration** và xử lý dữ liệu cũ không đạt validator hiện tại.
6. Kiểm tra kết quả phục hồi về **số lượng, tính toàn vẹn, index, quan hệ nghiệp vụ và quyền truy cập**.
7. Nhận biết giới hạn của selective restore đối với **point-in-time consistency**, Atlas, sharded cluster và workload đang ghi liên tục.

> **An toàn trước tiên:** các câu lệnh có khả năng thay đổi hoặc xóa dữ liệu trong bài được đặt trong ngữ cảnh database lab. Không chạy `mongorestore --drop`, `collMod` hoặc copy dữ liệu vào production nếu chưa xác minh namespace, backup, đối tượng chịu tác động và phương án rollback.

## 1. “Khôi phục có chọn lọc” có những cấp độ nào?

Không phải mọi yêu cầu “restore một phần” đều cùng mức độ.

| Cấp độ | Câu hỏi | Công cụ/cách tiếp cận |
| --- | --- | --- |
| **Toàn deployment/cluster** | Phục hồi trạng thái hệ thống sau sự cố lớn | Snapshot/cluster restore, backup platform phù hợp |
| **Một database** | Chỉ lấy lại database `shop_app` | Logical dump/restore có phạm vi namespace |
| **Một collection** | Chỉ phục hồi `shop_app.orders` | `mongorestore --nsInclude` |
| **Một nhóm collections** | Lấy `orders` và `payments` | Nhiều `--nsInclude` hoặc pattern phù hợp |
| **Đổi tên database/collection khi restore** | Lấy `shop_app.orders` thành `restore_review.orders` | `--nsFrom` / `--nsTo` |
| **Một số document theo filter** | Chỉ cứu đơn hàng `ORD-1001` | Restore collection vào staging rồi lọc/copy có kiểm soát |
| **Chỉ cấu trúc index/validator** | Cần áp lại metadata nhưng không thay dữ liệu | Đối chiếu metadata rồi tạo index/`collMod` có kiểm soát |
| **Trạng thái tại thời điểm cụ thể** | Phục hồi tới trước khi thao tác nhầm xảy ra | Point-in-time restore dựa trên backup + log/snapshot thích hợp |

**Điểm phân biệt quan trọng:** `mongorestore` chọn phạm vi theo **namespace**, không cung cấp một tùy chọn chung kiểu `--query='{orderNo:...}'` để chọn document tùy ý từ BSON dump rồi merge an toàn vào production. Nếu chỉ cần vài document, luồng phổ biến là **khôi phục cả collection vào staging** rồi dùng truy vấn/app migration để đưa đúng document trở lại.

## 2. Namespace trong MongoDB là gì?

Một **namespace** xác định collection trong database, thường được viết:

```text
<database>.<collection>
```

Ví dụ:

```text
shop_app.orders
shop_app.customers
shop_app.payments
audit.events
restore_review.orders
```

Ở đây:

- `shop_app` hoặc `restore_review` là database name.
- `orders` là collection name.
- `shop_app.orders` và `restore_review.orders` là **hai namespace khác nhau**, dù cùng tên collection `orders`.

### Source namespace và destination namespace

Khi restore:

```text
Backup chứa:
  shop_app.orders
          |
          | --nsFrom shop_app.orders
          | --nsTo   restore_review.orders
          v
MongoDB đích:
  restore_review.orders
```

Việc đổi namespace giúp xem dữ liệu backup **không thay thế collection `shop_app.orders` đang vận hành**.

### Namespace không phải quyền truy cập

Một namespace chỉ là định danh dữ liệu. Việc phục hồi vào database có tên `restore_review` **không tự cô lập quyền đọc dữ liệu nhạy cảm**: cần kiểm tra user roles, network access, môi trường đích và chính sách dữ liệu, đặc biệt khi backup chứa PII hoặc secrets.

## 3. Logical backup: `mongodump` lưu những gì?

`mongodump` thuộc bộ **MongoDB Database Tools**. Nó xuất dữ liệu MongoDB thành BSON dump; khi dùng chế độ thư mục, thường có các file như:

```text
dump/
  shop_app/
    orders.bson
    orders.metadata.json
    customers.bson
    customers.metadata.json
    payments.bson
    payments.metadata.json
```

Ý nghĩa:

- `orders.bson`: các **documents** được dump cho collection.
- `orders.metadata.json`: **metadata** phục vụ restore, thường bao gồm collection options và index definitions khi được lưu trong backup.
- Các file tương ứng cho những collections khác.

Trong thực tế, tên file/layout còn phụ thuộc cách dump, loại collection, công cụ và phiên bản. Không chỉnh tay BSON/metadata backup như một JSON văn bản thuần rồi kỳ vọng `mongorestore` hiểu mọi sửa đổi.

### Backup dạng archive

Thay vì một thư mục, có thể tạo một **archive**:

```bash
# Chạy trên máy được phép sao lưu, với URI qua môi trường an toàn.
mongodump \
  --uri="$SOURCE_URI" \
  --db="shop_app" \
  --archive="shop_app.archive" \
  --gzip
```

`--archive` chứa nội dung dump theo định dạng archive của Database Tools; `--gzip` nén dữ liệu. Đây **không phải file ZIP chung có thể giải nén và chỉnh sửa như backup SQL**. Khi restore phải dùng options archive/gzip tương ứng.

### Một bản dump không mặc nhiên là snapshot nhất quán toàn ứng dụng

Nếu nhiều collections đang được ghi trong lúc backup, những document được đọc ở các thời điểm khác nhau có thể không tạo thành **một trạng thái nghiệp vụ nguyên tử toàn database**. Các chế độ như `mongodump --oplog` hoặc giải pháp backup có point-in-time capability có điều kiện và giới hạn riêng. Không xem một dump chọn lọc là “ảnh chụp chính xác mọi collection vào cùng một mili giây” nếu chưa xác nhận phương thức backup và workload.

## 4. `mongorestore` đọc BSON và metadata như thế nào?

`mongorestore` là công cụ import lại BSON data, và có thể xử lý collection metadata/indexes đi cùng dump tùy flags. Các phần liên quan:

```text
mongodump output
  |
  +-- BSON document data --------> collection documents
  |
  +-- collection options --------> collection configuration
  |                                 (khi có metadata và được hỗ trợ)
  |
  +-- index specifications ------> index definitions/builds
                                    (khi được chọn phục hồi)
```

Vì vậy “restore xong documents” **không đồng nghĩa**:

- Mọi index đã có và build thành công.
- Unique constraints giống database cũ.
- Default collation giống bản cũ.
- `validator`, `validationLevel` và `validationAction` giống môi trường nguồn.
- Dữ liệu thỏa tất cả quy tắc nghiệp vụ hiện tại.

Phải **đọc kết quả lệnh và kiểm tra trạng thái sau restore**. Số documents được công cụ báo chèn không thay cho việc xác nhận index builds và collection options.

### Công cụ, server và version

MongoDB Database Tools có phiên bản riêng với MongoDB server. Khi backup và restore qua những server/tool versions khác nhau, một số feature hoặc index/collection option có thể có ràng buộc tương thích. Nên kiểm tra:

```bash
mongodump --version
mongorestore --version
```

Và ghi lại:

```javascript
db.version()
```

Nếu restore sang MongoDB Atlas hoặc cluster khác phiên bản, cần đối chiếu tài liệu tương thích của MongoDB Database Tools/driver/server trước khi chạy.

## 5. Kịch bản xuyên suốt: lấy lại một số đơn hàng

Giả sử database nguồn `shop_app` có:

```text
shop_app
  ├── customers
  ├── orders
  ├── payments
  └── products
```

Một thao tác xóa nhầm làm mất đơn hàng có mã `ORD-1001`. Các đơn hàng khác trong production vẫn nhận ghi mới. Ta không muốn restore đè toàn bộ `shop_app.orders`.

Mục tiêu an toàn:

```text
Backup shop_app.orders
        |
        v
Restore vào restore_review.orders
        |
        v
Đánh giá dữ liệu/index/validator
        |
        v
Tìm ORD-1001 và các dependencies
        |
        v
Kế hoạch copy chọn lọc có kiểm soát
        |
        v
Theo dõi/đối soát production
```

**Bản sao phục hồi phải được tạo ở một namespace không xung đột với dữ liệu đang hoạt động.** Điều này giảm rủi ro ghi đè do dùng nhầm flags.

### Định nghĩa mẫu dữ liệu

```javascript
{
  _id: ObjectId("65f000000000000000000101"),
  orderNo: "ORD-1001",
  customerId: "CUS-01",
  status: "PAID",
  total: NumberDecimal("125000.00"),
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  items: [
    { sku: "SKU-A", quantity: 2, unitPrice: NumberDecimal("50000.00") },
    { sku: "SKU-B", quantity: 1, unitPrice: NumberDecimal("25000.00") }
  ]
}
```

Nếu `shop_app.orders` có unique index trên `orderNo`, việc đưa document cũ vào collection hiện tại phải xem đơn hàng đó đã được tạo lại dưới một `_id` khác chưa. Nếu chỉ chạy insert một cách mù quáng, có thể gặp duplicate key hoặc tạo dữ liệu logic trùng.

## 6. Tạo backup mẫu trong môi trường được phép

### 6.1. Dump một database

Trên shell kiểu Bash, `SOURCE_URI` là biến môi trường không chứa plaintext password trong source code:

```bash
mongodump \
  --uri="$SOURCE_URI" \
  --db="shop_app" \
  --out="./dump_lab"
```

Nếu muốn archive:

```bash
mongodump \
  --uri="$SOURCE_URI" \
  --db="shop_app" \
  --archive="./shop_app.archive" \
  --gzip
```

Đối với dữ liệu production đang thay đổi, một lần dump đơn giản cần được đánh giá về consistency và yêu cầu RPO/RTO. Không coi hai lệnh trên là chiến lược backup production hoàn chỉnh.

### 6.2. Dump riêng một collection

```bash
mongodump \
  --uri="$SOURCE_URI" \
  --db="shop_app" \
  --collection="orders" \
  --out="./orders_dump"
```

Đây là một hình thức **selective backup**: chỉ backup một collection. Tương tự, cũng có thể lựa chọn namespace phù hợp qua options mà phiên bản Database Tools hỗ trợ. Cần phân biệt:

- **Chọn lúc dump**: backup **không chứa** collection ngoài phạm vi.
- **Chọn lúc restore**: backup có thể chứa nhiều collections, nhưng chỉ **khôi phục phần được chọn**.

Nếu đang xử lý sự cố và chỉ có một bản backup toàn database, có thể dùng `--nsInclude` lúc restore thay vì bắt buộc dump lại.

## 7. Chọn namespace bằng `--nsInclude`

Giả sử backup thư mục có `shop_app.orders`, `shop_app.customers` và `shop_app.payments`.

Muốn chỉ restore collection `shop_app.orders` vào **một môi trường lab rỗng hoặc cô lập**:

```bash
mongorestore \
  --uri="$TARGET_URI" \
  --nsInclude="shop_app.orders" \
  "./dump_lab"
```

`--nsInclude` giới hạn source namespace từ dump. Nó **không giới hạn document theo filter** và không tự đổi tên collection.

### Chọn nhiều namespaces

Ví dụ chỉ phục hồi `orders` và `payments`:

```bash
mongorestore \
  --uri="$TARGET_URI" \
  --nsInclude="shop_app.orders" \
  --nsInclude="shop_app.payments" \
  "./dump_lab"
```

Có thể dùng pattern phù hợp, ví dụ `shop_app.*` để bao gồm những collections trong database. **Pattern rộng cần được review kỹ** vì collection mới được thêm vào backup có thể làm phạm vi restore lớn hơn dự định.

### Chọn từ archive nén

```bash
mongorestore \
  --uri="$TARGET_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders"
```

`--gzip` tương ứng với archive đã tạo bằng gzip. Đích restore được lấy từ URI và namespace mapping; nếu không đổi tên, namespace trong backup có thể trùng collection hiện tại ở target. **Không thực hiện ví dụ này trên production đang chạy nếu namespace đích chưa được xác nhận.**

## 8. Loại trừ namespace bằng `--nsExclude`

Khi muốn phục hồi gần như toàn database nhưng bỏ qua một collection như `auditLogs`:

```bash
mongorestore \
  --uri="$TARGET_URI" \
  --nsInclude="shop_app.*" \
  --nsExclude="shop_app.auditLogs" \
  "./dump_lab"
```

`--nsExclude` giúp loại collection không muốn restore trong phạm vi lựa chọn. Tuy nhiên:

- Nó không giải quyết dependencies giữa collections.
- Nó không giúp chọn một số documents trong collection.
- Nó không mặc nhiên ngăn những collections khác bị tác động nếu pattern đầu vào quá rộng.
- Cần chú ý views, collections đặc biệt và metadata khi backup có chúng.

### Không dùng pattern rộng theo thói quen

```bash
# Có thể quá rộng đối với môi trường có nhiều database.
mongorestore --uri="$TARGET_URI" --nsInclude="*.*" "./dump_lab"
```

Một wildcard khớp nhiều namespaces có thể restore ngoài phạm vi nghiệp vụ muốn cứu. Trong incident recovery, nên bắt đầu từ **namespace hẹp nhất** và mở rộng chỉ khi có lý do.

## 9. Đổi tên khi restore bằng `--nsFrom` và `--nsTo`

Đây là một trong những kỹ thuật quan trọng nhất của **khôi phục an toàn**: đưa dữ liệu backup sang một namespace mới để kiểm tra.

Ví dụ:

```bash
mongorestore \
  --uri="$TARGET_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders" \
  --nsFrom="shop_app.orders" \
  --nsTo="restore_review.orders"
```

Kết quả mong muốn:

```text
Nguồn trong archive:
  shop_app.orders

Đích trong MongoDB:
  restore_review.orders

Không thay đổi trực tiếp:
  shop_app.orders
```

**`--nsInclude` chọn namespace nguồn** cần lấy từ backup; **`--nsFrom` / `--nsTo` ánh xạ namespace nguồn sang namespace đích**. Mỗi phiên bản Database Tools có quy tắc cụ thể cho syntax/wildcards; với lệnh nguy hiểm, dùng tên namespace tường minh và kiểm tra trên một môi trường riêng trước.

### Đổi cả database bằng pattern

Ví dụ ý tưởng: giữ tên collection nhưng đổi database:

```bash
mongorestore \
  --uri="$TARGET_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.*" \
  --nsFrom="shop_app.*" \
  --nsTo="restore_review.*"
```

Với pattern tương thích, `shop_app.orders` thành `restore_review.orders`, `shop_app.customers` thành `restore_review.customers`, v.v.

**Dùng tên tường minh khi phạm vi có thể gây phá hủy.** Wildcard làm quá trình nhanh hơn nhưng dễ chọn dư collection nếu backup hoặc naming conventions thay đổi.

## 10. Vì sao staging restore thường là bước bắt buộc?

Một workflow trực tiếp:

```text
Backup cũ --> mongorestore --drop --> Production orders
```

có thể xóa toàn bộ collection `orders` hiện tại trước khi khôi phục dữ liệu backup. Như vậy những đơn hàng phát sinh sau backup có nguy cơ biến mất.

Workflow staging:

```text
Backup cũ
    |
    v
restore_review.orders
    |
    +--> count / schema / index review
    +--> tìm docs cần cứu
    +--> kiểm tra dependencies
    +--> business approval
    |
    v
Copy chọn lọc với idempotency + rollback
    |
    v
Production orders
```

Ưu điểm:

- Xác định được dữ liệu nào thực sự có trong backup.
- Có thể truy vấn/đối chiếu mà không dừng production.
- Có thể thử sửa định dạng dữ liệu cũ trước khi đưa về.
- Kiểm tra index và validator của backup khác target.
- Giảm nguy cơ thao tác `--drop` nhầm collection đang hoạt động.

**Staging vẫn chứa dữ liệu thật**, nên cần kiểm soát quyền, retention và việc xóa staging sau khi incident kết thúc. Không đưa bản sao nhạy cảm vào môi trường dev public.

## 11. `--drop`: tùy chọn cần hiểu kỹ

Khi dùng `mongorestore --drop`, công cụ sẽ **drop collection đích tương ứng trước khi restore collection đó** trong phạm vi thao tác. Điều này giúp tránh trộn với dữ liệu cũ và khôi phục lại metadata/index có điều kiện phù hợp, nhưng có thể xóa dữ liệu hiện hành.

Ví dụ chỉ **trong database lab dùng để review**, khi được xác nhận rằng collection staging có thể thay thế:

```bash
mongorestore \
  --uri="$LAB_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders" \
  --nsFrom="shop_app.orders" \
  --nsTo="restore_review.orders" \
  --drop
```

**Không đổi `restore_review.orders` thành `shop_app.orders` rồi chạy trên production** chỉ vì muốn giữ index: `--drop` có thể xóa cả dữ liệu đã ghi sau thời điểm backup.

### `--drop` không phải “chỉ xóa các document trùng”

`--drop` hoạt động ở cấp **collection**, không phải bộ lọc chọn những document có cùng `_id`. Nó cũng ảnh hưởng những indexes/options hiện tại vì collection đích bị drop rồi được tái tạo theo cơ chế restore.

Trước khi chạy cần xác định:

1. Chính xác target URI/cluster nào?
2. Source namespace nào được `--nsInclude` chọn?
3. `--nsFrom` / `--nsTo` biến nó thành target namespace nào?
4. Collection đích có đang có dữ liệu mới hoặc được app sử dụng không?
5. Có backup/rollback của trạng thái hiện tại không?
6. Có views, triggers, jobs, CDC hoặc references phụ thuộc collection không?

### Không dùng `--drop` thì sao?

Nếu collection đích đã có dữ liệu, `mongorestore` có thể cố gắng insert thêm documents và gặp **duplicate key** trên `_id` hoặc các unique indexes. Nó **không phải phép upsert thông minh** để tự so trạng thái mới/cũ và giữ bản đúng theo nghiệp vụ.

Nếu muốn phục hồi từng đơn hàng đã mất, **không nên dựa vào hành vi trùng khóa của `mongorestore` để merge production**. Hãy restore staging và triển khai logic chọn tài liệu cụ thể.

## 12. Khôi phục từng document: vì sao cần bước thứ hai?

Giả sử backup chứa 1 triệu đơn hàng nhưng production chỉ mất hai mã `ORD-1001` và `ORD-1002`. Bạn đã restore vào `restore_review.orders`.

Kiểm tra:

```javascript
const review = db.getSiblingDB("restore_review");

review.orders.find({
  orderNo: { $in: ["ORD-1001", "ORD-1002"] }
}, {
  orderNo: 1,
  customerId: 1,
  status: 1,
  total: 1,
  createdAt: 1
});
```

Sau đó so với production:

```javascript
const production = db.getSiblingDB("shop_app");

production.orders.find({
  orderNo: { $in: ["ORD-1001", "ORD-1002"] }
}, {
  orderNo: 1,
  customerId: 1,
  status: 1,
  total: 1,
  createdAt: 1
});
```

Đây chỉ là **truy vấn đọc**. Không sửa production khi chưa phân tích:

- Document có thực sự mất hay chỉ thay đổi ID/status?
- `orderNo` có unique index không, và có record khác dùng cùng key không?
- `customerId` có tồn tại và được phép liên kết không?
- `payments` và inventory có trạng thái mới nào sau backup không?
- Document có cần được **migrate schema** theo phiên bản hiện tại không?
- Khôi phục y nguyên có khiến hệ thống phát lại workflow không?

### Không thể dùng `--nsInclude` để lọc theo document fields

`--nsInclude="shop_app.orders"` chỉ chọn **toàn collection**. Không có ngữ nghĩa `where orderNo in (...)` ở option này.

Khi chỉ cần vài document, phương án phù hợp là:

1. Restore source collection vào staging.
2. Query xác định document cần phục hồi.
3. Review cùng owner nghiệp vụ.
4. Copy theo **insert-only** hoặc **conditional upsert** tùy policy, với unique/idempotency controls.
5. Đối soát trước và sau copy.

Nếu cần script copy bằng driver, nên có **dry-run riêng do ứng dụng triển khai**, danh sách IDs đã duyệt và logging. Không mặc định `mongorestore` tự cung cấp business-level dry-run an toàn.

## 13. Index ảnh hưởng gì sau phục hồi?

MongoDB index giúp:

- Tối ưu truy vấn/filter/sort.
- Thực thi ràng buộc **unique**.
- Hỗ trợ TTL và dọn dữ liệu theo thời gian.
- Hỗ trợ partial index, collation hoặc các loại index đặc thù.

Ví dụ collection `orders` có:

```javascript
db.orders.createIndex(
  { orderNo: 1 },
  { unique: true, name: "uk_order_no" }
);

db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_customer_created" }
);
```

Nếu khôi phục dữ liệu mà thiếu index thứ hai, API danh sách đơn hàng theo khách có thể chậm. Nếu thiếu unique index đầu, hệ thống có thể cho phép tạo **hai document trùng `orderNo`**, phá vỡ invariant nghiệp vụ.

Vì thế, sau restore không chỉ xác nhận documents có mặt. Phải xem **toàn bộ tập index**, gồm options như unique, collation, partial filter, TTL hoặc hidden status.

### Kiểm tra index

```javascript
use restore_review

db.orders.getIndexes();
```

Đối chiếu với tài liệu schema/index của ứng dụng hoặc metadata backup, không chỉ đếm số index. Hai index cùng key pattern nhưng khác `unique` hoặc `collation` **không tương đương về hành vi**.

## 14. Index metadata trong `mongodump`

Khi `mongodump` ghi metadata collection trong chế độ thư mục, file tương ứng thường chứa thông tin như:

```json
{
  "options": {
    "validator": {
      "$jsonSchema": {
        "bsonType": "object",
        "required": ["orderNo", "total"]
      }
    }
  },
  "indexes": [
    {
      "key": {"_id": 1},
      "name": "_id_"
    },
    {
      "key": {"orderNo": 1},
      "name": "uk_order_no",
      "unique": true
    }
  ]
}
```

Đây là **hình minh họa đã giản lược**, không phải nội dung metadata chắc chắn y hệt từ mọi phiên bản. Metadata còn có thể chứa cấu hình khác hoặc định dạng BSON/Extended JSON đặc thù.

Khi mongorestore đọc một dump có metadata, mặc định công cụ cố gắng phục hồi những definitions liên quan được hỗ trợ, **nếu không bị flags loại trừ** và thao tác không lỗi. Những index không tương thích server đích hoặc vi phạm dữ liệu hiện tại có thể không tạo được.

## 15. `--noIndexRestore` và `--noOptionsRestore`

Hai flags này kiểm soát hai phạm vi khác nhau:

| Flag | Bỏ qua phần nào khi restore? | Rủi ro cần biết |
| --- | --- | --- |
| `--noIndexRestore` | Không restore index definitions từ backup | Target có thể thiếu index và unique constraint |
| `--noOptionsRestore` | Không restore collection options từ backup | Target có thể thiếu validator, default collation hoặc tùy chọn khác |

### Chỉ restore dữ liệu vào một collection lab không muốn nhận cấu hình từ backup

```bash
mongorestore \
  --uri="$LAB_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders" \
  --nsFrom="shop_app.orders" \
  --nsTo="restore_review.orders" \
  --noIndexRestore \
  --noOptionsRestore
```

Đây có thể hữu ích nếu đội chỉ muốn **đọc và phân tích BSON** trong staging, tự quản lý cấu hình collection. Tuy nhiên, collection staging có thể **khác hành vi collection nguồn**:

- Một truy vấn có thể chậm hơn vì thiếu index.
- Duplicate data có thể được chèn mà không bị unique index từ backup chặn.
- Các writes mới có thể không bị schema validator kiểm soát.
- Collation mặc định có thể khác, làm query/sort/unique behavior khác.

**Đừng dùng hai flags theo thói quen rồi tuyên bố đã “restore đầy đủ”.** Nên ghi rõ mục đích là **data-only restore** và lập kế hoạch áp lại index/options nếu cần.

### Bỏ index để phục hồi nhanh hơn có an toàn không?

Có thể có tình huống cần trì hoãn xây index để giảm chi phí ingest. Nhưng với collection nghiệp vụ, tạm thiếu unique/TTL/partial index có thể làm hành vi khác production. Nếu cần tách dữ liệu/index:

1. Restore vào staging cô lập.
2. Kiểm tra dữ liệu, xử lý duplicates.
3. Tạo indexes theo quy trình được kiểm soát.
4. Xác minh index build hoàn tất trước khi bật traffic.

Không tối ưu tốc độ restore bằng cách đánh đổi ràng buộc dữ liệu mà không ghi nhận.

## 16. Unique index: restore có thể thất bại vì dữ liệu trùng

Giả sử backup có:

```javascript
[
  { _id: 1, orderNo: "ORD-1001" },
  { _id: 2, orderNo: "ORD-1001" }
]
```

Nếu tạo:

```javascript
db.orders.createIndex(
  { orderNo: 1 },
  { unique: true }
);
```

thì index build có thể thất bại vì **hai document trùng giá trị**. Tình huống có thể phát sinh khi:

- Backup vốn có dữ liệu lỗi từ thời điểm chưa có unique index.
- Restore merge vào collection đích đang có dữ liệu khác.
- Source/target khác nhau về collation, khiến các giá trị từng khác biệt bị coi tương đương.
- Một migration trước đó tạo duplicate keys.

### Tìm duplicate trong staging trước khi áp unique

```javascript
db.getSiblingDB("restore_review").orders.aggregate([
  {
    $group: {
      _id: "$orderNo",
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 100 }
]);
```

Pipeline chỉ có mục đích **phân tích**. Với tập dữ liệu rất lớn, `$push` toàn bộ IDs của một nhóm có cardinality cực cao có thể tạo tài liệu lớn; khi vận hành thật nên điều chỉnh pipeline/báo cáo theo quy mô.

Không tự xóa các bản trùng mà chưa hiểu cái nào là bản chuẩn; cần owner nghiệp vụ xác định reconciliation policy.

## 17. TTL index: khôi phục index có thể làm dữ liệu biến mất

TTL index có thể tự động xóa những document đã hết hạn theo tiêu chí time/retention.

Ví dụ:

```javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
```

Nếu restore bản backup cũ của `sessions` rồi tạo/restore TTL index này, các document có `expiresAt` trong quá khứ có thể sớm bị TTL monitor xóa. Điều này làm người vận hành tưởng “restore bị thiếu dữ liệu”, trong khi bản chất là **retention đang vận hành**.

### Cách tiếp cận an toàn

- Restore vào môi trường được cô lập khỏi job và TTL policy không mong muốn, nếu cần điều tra lịch sử.
- Kiểm tra index definitions và collection options trước khi quyết định giữ TTL.
- Nếu mục tiêu là khôi phục phiên làm việc hiện hành, dữ liệu expired từ nhiều ngày trước có thể không nên kích hoạt lại.
- Nếu mục tiêu là pháp chứng/forensics, dùng môi trường phù hợp và tránh cho background cleanup phá hủy bằng chứng.

**Đừng drop index TTL trên production chỉ để “giữ dữ liệu restore” mà không có phê duyệt**, vì sẽ thay đổi retention cho toàn collection.

## 18. Partial, sparse, hidden và collation của index

Ngoài unique/TTL, cần chú ý:

| Index property | Vai trò | Nguy cơ khi thiếu/sai sau restore |
| --- | --- | --- |
| `partialFilterExpression` | Chỉ index những document thỏa điều kiện | Query planner và điều kiện uniqueness có thể khác |
| `sparse` | Không index một số documents thiếu field | Coverage/unique behavior thay đổi |
| `hidden` | Index tồn tại nhưng không được planner cân nhắc thông thường | Kế hoạch query khác môi trường nguồn |
| `collation` | Quy tắc so sánh/case/locale | Unique/ordering có thể khác |
| `expireAfterSeconds` | TTL retention | Document cũ bị dọn hoặc giữ lâu ngoài ý muốn |
| `unique` | Ngăn các key trùng theo index semantics | Data invariant có thể bị vi phạm |

### Collation của collection cũng quan trọng

Ví dụ collection nguồn có default collation tiếng Anh case-insensitive hoặc locale khác, nhưng staging được tạo không có option tương ứng. Một truy vấn equality/sort/index behavior có thể khác ngay cả khi documents giống hệt.

Default collection collation là một phần của **collection options**, không phải trường hiển thị trong document. Không nên giả định có thể sửa mọi thuộc tính collection sau khi tạo bằng `collMod`; thay đổi default collation thường đòi tái tạo collection theo thiết kế phù hợp.

### Kiểm tra đầy đủ thay vì chỉ nhìn tên index

```javascript
const review = db.getSiblingDB("restore_review");
printjson(review.orders.getIndexes());
printjson(review.getCollectionInfos({ name: "orders" }));
```

Hai API trả index specifications và collection options để đối chiếu với bản backup và môi trường đích.

## 19. Schema validation trong MongoDB là gì?

**Schema validation** cho phép định nghĩa những quy tắc mà document phải thỏa khi insert/update, thường bằng `$jsonSchema` hoặc query expressions được hỗ trợ.

Ví dụ ứng dụng mong đợi mỗi đơn hàng có:

- `orderNo` kiểu string.
- `total` kiểu số BSON.
- `createdAt` kiểu BSON Date.
- `status` là một trong những giá trị hợp lệ.

Một validator có thể là:

```javascript
const orderValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["orderNo", "total", "createdAt"],
    properties: {
      orderNo: {
        bsonType: "string"
      },
      total: {
        bsonType: ["int", "long", "double", "decimal"]
      },
      createdAt: {
        bsonType: "date"
      },
      status: {
        enum: ["NEW", "PAID", "CANCELLED"]
      }
    }
  }
};
```

Ở đây:

- `required` yêu cầu những fields cụ thể tồn tại.
- `bsonType` kiểm tra loại BSON, không chỉ JSON string/number ở tầng API.
- `enum` giới hạn những giá trị cho field khi có field tương ứng.

Nếu business policy yêu cầu `status` bắt buộc, phải thêm `status` vào `required`; riêng `enum` không làm field bắt buộc.

### Schema validation không phải type conversion

Một document:

```javascript
{
  orderNo: "ORD-1001",
  total: "125000.00",
  createdAt: "2026-11-14"
}
```

có `total` và `createdAt` là **string**. Validator không tự chuyển chúng thành `Decimal128` và `Date`. Nếu schema hiện tại yêu cầu số/BSON Date, document phải được migrate hoặc được xử lý theo chính sách phù hợp.

## 20. Tạo collection có validator

Trong một database lab rỗng:

```javascript
use restore_validation_lab

db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderNo", "total", "createdAt"],
      properties: {
        orderNo: { bsonType: "string" },
        total: { bsonType: ["int", "long", "double", "decimal"] },
        createdAt: { bsonType: "date" },
        status: {
          enum: ["NEW", "PAID", "CANCELLED"]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Thêm document hợp lệ:

```javascript
db.orders.insertOne({
  orderNo: "ORD-OK",
  total: NumberDecimal("125000.00"),
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  status: "PAID"
});
```

Document không hợp lệ:

```javascript
db.orders.insertOne({
  orderNo: "ORD-BAD",
  total: "125000.00",
  createdAt: "2026-11-14",
  status: "UNKNOWN"
});
```

Trong điều kiện validator `strict` + `error`, insert thứ hai sẽ bị từ chối vì sai type/enum. **Đây là demo hành vi validation**, không cần thực thi trên production.

### `validationLevel` và `validationAction` khác nhau

| Tùy chọn | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `validationLevel: "strict"` | Strict | Áp dụng validation cho inserts/updates theo quy tắc validator |
| `validationLevel: "moderate"` | Moderate | Inserts được kiểm tra; một số updates trên documents vốn đã invalid có thể không bị kiểm tra tương tự |
| `validationAction: "error"` | Error | Chặn write không hợp lệ |
| `validationAction: "warn"` | Warn | Cho phép write nhưng phát cảnh báo/log theo cơ chế server |

Các mode/khả năng ghi log khác có thể phụ thuộc MongoDB version. Khi restore vào môi trường mới, hãy xác minh **giá trị thực tế của cả level và action**, không chỉ thấy có `validator` là kết luận đang cưỡng chế đúng.

## 21. Schema validation trong restore: bốn tình huống

### A. Restore vào collection mới, metadata đầy đủ

Collection mới có thể được tạo cùng collection options/validator từ backup (nếu metadata tồn tại, tương thích và không bị flags tắt). Các documents được restore có thể chịu tác động của validator trong quá trình ghi.

### B. Restore vào collection hiện có với validator mới hơn

Source backup có document legacy chưa đạt schema mới. Khi restore vào target hiện tại không `--drop`, insert có thể bị từ chối vì **document validation** dù backup ban đầu hoàn toàn hợp lệ ở thời điểm được tạo.

### C. Restore với `--noOptionsRestore`

Không phục hồi collection options từ backup. Nếu collection mới được tạo với defaults, nó có thể thiếu validator; nếu collection đã tồn tại, validator hiện hành của target có thể tiếp tục áp dụng. Không xem `--noOptionsRestore` là một lệnh “tắt validation trong mọi trường hợp”.

### D. Restore với `--drop`

Nếu target collection bị drop, cấu hình validator/index hiện tại có thể bị mất và được tái tạo từ metadata backup (nếu có và được áp dụng). Điều này có thể **đưa validator cũ trở lại** hoặc làm mất thay đổi schema mới ở target.

**Kết luận:** chiến lược restore dữ liệu và chiến lược restore schema phải được quyết định riêng. Cả hai đều cần kiểm tra theo đích đến.

## 22. `--bypassDocumentValidation`: có ích nhưng nguy hiểm nếu hiểu sai

`mongorestore` hỗ trợ tùy chọn `--bypassDocumentValidation` trong những điều kiện phiên bản/quyền phù hợp. Nó cho phép thao tác restore bỏ qua **document validation checks** khi ghi dữ liệu, hữu ích khi cần đưa legacy documents vào một collection để sửa sau.

Ví dụ chỉ trong **môi trường phục hồi cô lập**:

```bash
mongorestore \
  --uri="$LAB_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders" \
  --nsFrom="shop_app.orders" \
  --nsTo="restore_review.orders" \
  --bypassDocumentValidation
```

**Điều không được hiểu nhầm:**

- Bypass validation không tự sửa document sai kiểu.
- Bypass không mặc nhiên loại bỏ unique indexes hoặc cho phép duplicate `_id`.
- Bypass không làm mất mọi authorization/privilege requirements.
- Dữ liệu không hợp lệ được chèn có thể tiếp tục tồn tại sau khi validator hoạt động bình thường.
- Ứng dụng có thể gặp lỗi về sau khi đọc/ghi documents thiếu fields hoặc sai types.

Vì vậy chỉ dùng khi có **kế hoạch làm sạch dữ liệu và kiểm tra lại validator**, không coi là cách bỏ qua lỗi để đưa production online nhanh.

### Phân biệt bypass với thay validator

Sử dụng `--bypassDocumentValidation` áp dụng cho **write operation phù hợp**, còn thay `validator` hoặc `validationAction` trên collection làm thay đổi **chính sách của collection** cho những thao tác sau.

Trên database đang phục vụ production, đổi validation mode sang `warn` để “cho restore qua” có thể khiến **các writes từ ứng dụng khác** cũng được chấp nhận dù không hợp lệ. Đây là tác động rộng hơn rất nhiều so với xử lý data trong staging.

## 23. Kiểm tra dữ liệu legacy có thỏa schema hiện tại không?

Sau khi restore vào staging, có thể kiểm tra document theo cùng logic `$jsonSchema`.

Ví dụ:

```javascript
const schema = {
  bsonType: "object",
  required: ["orderNo", "total", "createdAt"],
  properties: {
    orderNo: { bsonType: "string" },
    total: {
      bsonType: ["int", "long", "double", "decimal"]
    },
    createdAt: { bsonType: "date" }
  }
};

const reviewOrders = db
  .getSiblingDB("restore_review")
  .getCollection("orders");

reviewOrders.find({
  $nor: [{ $jsonSchema: schema }]
}, {
  orderNo: 1,
  total: 1,
  createdAt: 1
}).limit(100);
```

Đây là truy vấn **phát hiện những document không khớp validator minh họa**, không phải lệnh sửa tự động. Trong môi trường thật, phải dùng đúng validator mục tiêu, cùng các điều kiện bổ sung, validationLevel/action và nghiệp vụ.

### Cẩn thận khi migrate

Ví dụ:

```javascript
// Legacy format
{
  orderNo: "ORD-1001",
  total: "125000.00",
  createdAt: "2026-11-14"
}

// Target format mong muốn
{
  orderNo: "ORD-1001",
  total: NumberDecimal("125000.00"),
  createdAt: ISODate("2026-11-14T00:00:00Z")
}
```

Việc chuyển chuỗi ngày thành UTC midnight chỉ là **giả định nghiệp vụ**. Nếu timestamp gốc đại diện cho một giờ địa phương hoặc transaction time, tự chọn UTC midnight có thể thay đổi ý nghĩa dữ liệu. Migration cần quy tắc rõ ràng cho timezone, đơn vị tiền, null và kiểu số.

## 24. `collMod` để sửa validator: khác restore document

MongoDB hỗ trợ lệnh `collMod` để thay đổi một số options của collection theo phiên bản, trong đó có schema validation.

Ví dụ **trong lab**:

```javascript
db.getSiblingDB("restore_validation_lab").runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderNo", "total", "createdAt"],
      properties: {
        orderNo: { bsonType: "string" },
        total: {
          bsonType: ["int", "long", "double", "decimal"]
        },
        createdAt: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Không dùng `collMod` như cách “cập nhật mọi schema và index”. Indexes phải được xử lý theo API/capability phù hợp; một số collection options không thể thay đổi tại chỗ. Với production, thay validator cần:

1. Đánh giá dữ liệu hiện hữu có bao nhiêu document invalid.
2. Xác định ứng dụng version nào đang ghi dữ liệu theo schema cũ.
3. Test writes và update paths.
4. Có rollout/backfill theo giai đoạn.
5. Giám sát validation errors và có kế hoạch rollback.

**Đổi validator không tự sửa dữ liệu cũ.** Nếu trước đó đã có những document invalid, chúng có thể tiếp tục tồn tại cho tới khi được cập nhật hoặc xử lý theo chính sách.

## 25. Kiểm tra metadata của collection sau restore

Trong `mongosh`:

```javascript
const review = db.getSiblingDB("restore_review");

printjson(
  review.getCollectionInfos({ name: "orders" })
);

printjson(
  review.orders.getIndexes()
);
```

Hãy ghi nhận:

- Collection có tồn tại đúng tên và đúng loại không?
- `validator` có nội dung dự kiến không?
- `validationLevel` và `validationAction` có phù hợp không?
- Default collation và những collection options quan trọng có đúng không?
- Unique, TTL, partial, text, wildcard hay các index đặc thù có được tạo thành công không?
- Có index tên giống nhưng định nghĩa/key/options khác nhau không?

### Phân biệt schema validation với storage validation

Lệnh:

```javascript
db.getSiblingDB("restore_review").runCommand({
  validate: "orders",
  full: true
});
```

liên quan đến kiểm tra **tính hợp lệ/cấu trúc dữ liệu lưu trữ** theo cơ chế server, **không thay thế** việc query kiểm tra tất cả documents có thỏa business `$jsonSchema` mới hay không. Hai loại kiểm tra có mục đích khác nhau.

## 26. Chọn phục hồi index hay giữ index của target?

Không có lựa chọn đúng cho mọi kịch bản.

| Tình huống | Hướng thường cân nhắc | Vì sao |
| --- | --- | --- |
| Khôi phục nguyên trạng collection vào cluster lab cùng version | Restore metadata/index từ backup | Muốn tái tạo hành vi source |
| Cứu vài documents vào production có schema/index mới | Restore staging, **giữ target indexes** | Không muốn đưa lại index/validator cũ |
| Phân tích dữ liệu lịch sử, không cần benchmark query | Có thể bỏ index restore ở staging | Giảm chi phí index build, nhưng hiểu giới hạn |
| Migrate sang version MongoDB khác | Review/tái tạo indexes theo target capability | Index options có thể khác |
| Tạo collection mới cho ứng dụng hiện hành | Áp schema/index **mục tiêu** rồi chuyển dữ liệu đã sửa | Tối ưu cho code đang chạy |
| Lưu chứng cứ trước thao tác recovery | Giữ bản backup độc lập, kiểm soát retention | Tránh làm mất dữ liệu cần điều tra |

### Index restoration không phải “phục hồi chỉ một index”

Nếu chỉ thiếu một index trên collection production, thường nên **tạo lại index theo definition được duyệt**, không restore nguyên collection chỉ để lấy metadata index.

Ví dụ:

```javascript
// Chỉ trên môi trường được cấp quyền và đã duyệt.
db.getSiblingDB("shop_app").orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_customer_created" }
);
```

Trước khi chạy trên production, kiểm tra index có sẵn, data cardinality, build resources, tác động tới workload và version restrictions. Bỏ qua index build failure có thể khiến triển khai tưởng thành công trong khi performance hoặc constraint vẫn thiếu.

## 27. Data-only restore không đồng nghĩa restore chính xác

Một lỗi phổ biến:

```text
mongorestore --noIndexRestore --noOptionsRestore
                |
                v
Documents đã có
                |
                v
Kết luận: phục hồi thành công hoàn toàn
```

Kết luận này quá sớm vì:

- Unique index chưa được xác minh.
- Validator có thể chưa bật.
- Collation/TTL khác nguồn.
- Application có thể phụ thuộc vào một index để đạt SLA.
- Data có thể không phù hợp model hiện tại.

**Thành công kỹ thuật của data import** chỉ là một phần của **thành công nghiệp vụ sau phục hồi**.

### Ba lớp xác nhận

1. **Physical/logical data restore:** namespace và documents xuất hiện; không có lỗi restore chưa xử lý.
2. **Metadata/schema restore:** index, options, validator đúng theo chính sách.
3. **Business recovery:** dữ liệu đầy đủ, consistency theo dependencies, API/query chạy đúng và không gây side effects.

Một hệ thống chỉ đạt lớp 1 vẫn có thể không an toàn để đưa vào vận hành.

## 28. Selective restore và tính nhất quán giữa collections

Ví dụ:

```text
customers:
  CUS-01  [đã đổi trạng thái sau backup]

orders:
  ORD-1001 -> CUS-01  [bản cũ]

payments:
  PAY-77 -> ORD-1001  [đã refund sau backup]
```

Nếu chỉ phục hồi `orders` từ backup một tuần trước:

- `ORD-1001` có thể chỉ là trạng thái **PAID cũ**, trong khi payment hiện tại đã refund.
- `customerId` có thể trỏ tới customer bị gộp/đã xóa.
- Một outbox event/stock reservation đã được xử lý và không nên chạy lại.

### Selective restore không phải “quay ngược hệ thống tới quá khứ”

Một restore namespace riêng chỉ lấy dữ liệu của namespace ở thời điểm backup. Nó **không tự chuyển những collection khác về trạng thái tương ứng**. Hơn nữa, một logical backup đang chạy giữa các writes có thể có inconsistency riêng nếu không dùng cơ chế backup phù hợp.

Vì vậy cần:

1. Xác định **invariants** giữa collections.
2. Liệt kê dependencies của document cần cứu.
3. Đối chiếu dữ liệu hiện tại với bản backup.
4. Quyết định field nào lấy từ bản cũ, field nào giữ trạng thái mới.
5. Chọn restore nguyên document hay chỉ copy một số thuộc tính.
6. Đánh dấu/audit những correction events.

Không tự phục hồi trạng thái thanh toán bằng cách chép một document cũ nếu điều đó có thể tác động tới tiền thật.

## 29. Point-in-time recovery: điều gì vượt quá `--nsInclude`?

**RPO** (*Recovery Point Objective*) là khoảng dữ liệu tối đa có thể mất theo mục tiêu; **RTO** (*Recovery Time Objective*) là khoảng thời gian khôi phục dịch vụ theo mục tiêu.

Một backup tạo lúc 01:00 không tự chứa những thay đổi lúc 01:01–03:00. Nếu lỗi xóa xảy ra lúc 03:00, `--nsInclude` không thể “tự lấy lại trạng thái 02:59” từ file BSON lúc 01:00.

### PIT restore cần lịch sử thay đổi phù hợp

Một quy trình point-in-time recovery thường phụ thuộc:

- Base backup nhất quán theo phương thức được hỗ trợ.
- Oplog/change history hoặc backup service đủ để đưa đến mốc mong muốn.
- Topology, tool options và phiên bản hỗ trợ.
- Khả năng khôi phục toàn phạm vi cần thiết với đúng thứ tự operations.

**Không ghép tùy tiện `--nsInclude` với replay oplog rồi coi đã có point-in-time consistency cho vài collection.** Oplog có thể chứa operations liên quan nhiều namespaces, transactions và dependencies; các flags/restrictions cần được kiểm tra theo Database Tools. Nếu yêu cầu chính xác thời điểm trước xóa nhầm, nên dùng quy trình PIT được hỗ trợ trong một môi trường cô lập rồi tiếp tục chọn documents để đưa về production.

### Atlas snapshots khác `mongodump`

MongoDB Atlas có những tính năng backup/snapshot/restore tùy tier và chính sách. Một snapshot restore có thể hoạt động ở cấp cluster hoặc theo phạm vi được dịch vụ hỗ trợ, không đồng nghĩa có thể áp dụng mọi `mongorestore --nsInclude` trực tiếp lên snapshot. Nếu cần phục hồi một collection từ snapshot, có thể phải restore sang **cluster tạm** trước rồi export/migrate theo namespace.

Không giả định Atlas backup luôn hỗ trợ arbitrary per-document restore hoặc mọi chức năng PIT trên mọi tier/version.

## 30. Restore vào Atlas: cần chuẩn bị gì?

Nếu target là Atlas, `mongorestore` từ client/runner được cấp quyền thường vẫn là một con đường cho logical BSON data, nhưng cần kiểm tra:

1. **Network path:** Atlas IP Access List cho public egress hoặc private connectivity phù hợp.
2. **TLS:** dùng URI/CA/hostname validation đúng.
3. **Database role:** user cần quyền tạo collection, chèn documents, tạo indexes hoặc sửa collection options theo thao tác restore.
4. **Tool compatibility:** Database Tools version tương thích deployment.
5. **Cluster capacity:** storage, CPU, RAM, connection limits, index build resources.
6. **Sharding/topology:** nếu target sharded, đánh giá chiến lược key/distribution.
7. **Backup policy:** không làm thay đổi production backup/retention ngoài ý muốn.
8. **Secrets:** không hard-code credentials trong script hoặc command history.

### URI placeholder

```bash
# SOURCE_URI và TARGET_URI lấy từ secret management.
mongorestore \
  --uri="$TARGET_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders" \
  --nsFrom="shop_app.orders" \
  --nsTo="restore_review.orders"
```

Chỉ chạy khi `TARGET_URI` trỏ tới môi trường **staging/đích đã được duyệt**. Nếu target Atlas project là production, việc tạo một database `restore_review` có thể vẫn chứa dữ liệu nhạy cảm và tốn tài nguyên trên chính cluster đang hoạt động.

## 31. Sharding, views và collection types đặc biệt

### Sharded collections

Restore logical data vào sharded cluster có thể chịu ảnh hưởng của shard key, unique index constraints, phân phối chunk và routing. Không coi namespace mapping là đủ để tái tạo toàn bộ sharding metadata/topology của source.

Trước khi restore:

- Xác định target collection có sharded không.
- Kiểm tra shard key và các unique index có tương thích không.
- Đánh giá cardinality/distribution và write hot spots.
- Cân nhắc phục hồi vào một unsharded staging collection để phân tích trước.
- Đối chiếu version, topology và khuyến cáo của công cụ backup.

### Views

View là định nghĩa truy vấn dựa trên collection khác. Selective restore chỉ view metadata mà không có source data hoặc thay namespace không tương ứng có thể tạo view không hoạt động như mong đợi.

### Time series, capped và clustered collections

Những loại collection này có các options và restrictions riêng. Nếu dùng `--noOptionsRestore` rồi để tool tạo collection thường, **không được coi đó là bản sao tương đương cấu trúc**. Khi có dữ liệu time series hoặc collection đặc biệt, phải kiểm tra document/collection representation và support của Database Tools theo phiên bản.

### GridFS

GridFS thường dùng hai collections liên quan, ví dụ `fs.files` và `fs.chunks`. Chỉ restore `fs.files` sẽ đưa về metadata nhưng thiếu bytes của những tệp; chỉ restore `fs.chunks` có thể tạo orphan chunks. Nếu phục hồi một file cụ thể, cần xử lý cả hai collections và những business references, dùng quy trình GridFS phù hợp.

Đây là ví dụ điển hình vì sao **chọn collection về mặt kỹ thuật không đủ để bảo đảm consistency nghiệp vụ**.

## 32. Kiểm tra số lượng documents

Sau staging restore:

```javascript
const review = db.getSiblingDB("restore_review");

print("orders:", review.orders.countDocuments({}));
print("indexes:", review.orders.getIndexes().length);
```

Nếu có số lượng mong đợi từ nguồn backup hoặc backup report, hãy đối chiếu:

- Total documents được dump.
- Total documents được restore thành công.
- Số errors (duplicate key, validation failure, namespace conflict).
- Số documents thực tế sau restore.

### Vì sao count bằng nhau vẫn chưa đủ?

Hai collections đều có 100.000 documents nhưng một collection có thể thiếu `ORD-1001` và có duplicate `ORD-2001` dưới ID khác. Count không chứng minh contents giống nhau.

Với dữ liệu quan trọng, nên so **key set, hash/fingerprint được thiết kế phù hợp, fields nghiệp vụ, relationships và sample queries**. Không cố tính một SHA-256 duy nhất trên các JSON documents theo thứ tự không xác định rồi xem là proof, vì BSON type/field order, serialization và document order có thể khác.

### Lấy mẫu key nghiệp vụ

```javascript
review.orders.find(
  { orderNo: { $in: ["ORD-1001", "ORD-1002"] } },
  { orderNo: 1, status: 1, total: 1, createdAt: 1 }
).sort({ orderNo: 1 });
```

Khi cần kiểm tra hàng triệu documents, dùng quy trình đối soát theo batch/key range để giới hạn bộ nhớ và tránh ảnh hưởng production.

## 33. Kiểm tra truy vấn và index với `explain`

Sau restore indexes, không nên chỉ nhìn `getIndexes()` rồi kết luận query performance sẽ giống production.

Ví dụ:

```javascript
review.orders.find({
  customerId: "CUS-01",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(20)
  .explain("executionStats");
```

Đánh giá:

- Có index phù hợp với filter/sort không?
- Query có `COLLSCAN` hoặc sort tốn nhiều tài nguyên ngoài ý muốn không?
- `totalKeysExamined` và `totalDocsExamined` có hợp lý so với số kết quả không?
- Collation có phù hợp với cách ứng dụng query không?
- Target có cấu hình index khác source do các phiên bản/mapping khác nhau không?

Không so latency từ một staging cluster rất nhỏ với production load cao rồi coi đó là một phép benchmark công bằng; cần mô phỏng workload đại diện.

## 34. Collection metadata có thể gây tác dụng phụ

Ngoài index và validator, collection options có thể ảnh hưởng:

- **Default collation**: case/locale sensitivity trong query/sort/unique.
- **Capped behavior**: giới hạn kích thước và thứ tự dữ liệu ở collection có cấu hình capped.
- **Time series options**: tổ chức dữ liệu measurement và retention.
- **Change stream/pre/post image options** trong những môi trường có hỗ trợ.
- **TTL/retention** hoặc những cấu hình phụ trợ liên quan.

Một backup lịch sử có thể chứa metadata hợp lệ **ở thời điểm cũ** nhưng không phù hợp với schema hiện nay. Do đó không thể coi việc restore toàn metadata là luôn đúng; cũng không thể luôn bỏ metadata và chỉ restore documents.

### Quy tắc ra quyết định

Hãy tách:

```text
Mục tiêu A: tái hiện hệ thống cũ để điều tra
  -> ưu tiên metadata của thời điểm backup

Mục tiêu B: đưa một số document về ứng dụng đang chạy
  -> ưu tiên schema/index hiện tại của target
     sau khi chuyển đổi dữ liệu phù hợp
```

Hai mục tiêu này thường cần **hai môi trường** hoặc hai bước restore khác nhau.

## 35. Khôi phục dữ liệu có chọn lọc bằng application script

Sau khi staging được kiểm tra, việc đưa một số documents trở lại production nên được thiết kế như một **data-repair operation**.

Một quy trình thực tế:

1. Tạo tập keys cần phục hồi, ví dụ `["ORD-1001","ORD-1002"]`.
2. Query backup/staging để biết source document.
3. Query production xác nhận record chưa tồn tại hoặc đang ở trạng thái cho phép sửa.
4. Đối chiếu customer/payment/inventory với trạng thái hiện tại.
5. Migrate schema nếu cần, không xóa fields mới hoặc chỉnh ngược trạng thái nghiệp vụ.
6. Thử operation trên database lab, ghi before/after diff.
7. Thực hiện writes bằng identity hạn chế quyền và batch nhỏ.
8. Ghi audit/correlation ID, kiểm tra errors và kết quả.
9. Nếu operation bị retry, phải có idempotency/unique business key bảo vệ.
10. Đối soát sau thay đổi và giám sát app.

### Tại sao không dùng `replaceOne` từ backup cho mọi ID?

Vì một order có thể đã thay đổi sau backup. `replaceOne` bằng document cũ có thể:

- Xóa field mới mà ứng dụng đã thêm.
- Thay status mới bằng status cũ.
- Đổi payment/inventory reference về giá trị đã lỗi thời.
- Vô tình phát lại workflow hoặc đổi business state.

Với partial recovery, cần có **policy field-level**: document nào insert hoàn toàn, document nào patch, document nào chỉ tạo correction/audit event.

### Có thể dùng aggregation `$merge` không?

`$merge` có thể ghi kết quả aggregation vào collection đích, nhưng có semantics `on`, `whenMatched`, `whenNotMatched` và yêu cầu index/namespace riêng. Nó không tự giải quyết xung đột nghiệp vụ. Nếu dùng, phải thử trên **staging-to-staging** trước và xác định chính xác behavior cho records đã tồn tại.

Không chạy pipeline `$merge` từ backup trực tiếp vào production với `whenMatched:"replace"` chỉ vì nó tiện hơn viết application script.

## 36. Lập runbook phục hồi an toàn

### Giai đoạn A — xác định phạm vi sự cố

Trả lời:

- Collection nào mất/sai dữ liệu?
- Thời điểm bắt đầu lỗi và thời điểm phát hiện?
- Có đang tiếp tục ghi vào cùng namespace không?
- Những business keys/documents nào bị ảnh hưởng?
- Hệ thống có snapshot/PIT khả dụng không?
- RPO/RTO và mức ưu tiên phục hồi?

### Giai đoạn B — bảo toàn trạng thái hiện tại

Trước khi sửa:

- Sao lưu hoặc snapshot trạng thái hiện hành theo phương thức được phê duyệt.
- Giữ nguyên backup gốc, tránh ghi đè archive hoặc metadata.
- Tạo incident/change ID và người chịu trách nhiệm.
- Nếu có chứng cứ cần điều tra, đảm bảo quyền truy cập và retention phù hợp.

### Giai đoạn C — restore staging

```bash
mongorestore \
  --uri="$LAB_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders" \
  --nsFrom="shop_app.orders" \
  --nsTo="restore_review.orders"
```

**Không dùng `--drop` trừ khi staging collection chắc chắn có thể thay thế.**

### Giai đoạn D — kiểm tra dữ liệu và metadata

```javascript
const r = db.getSiblingDB("restore_review");

printjson(r.getCollectionInfos({ name: "orders" }));
printjson(r.orders.getIndexes());
print("documents =", r.orders.countDocuments({}));
```

Sau đó kiểm tra documents liên quan, unique keys, validator, collation, TTL, dependencies và các validation errors.

### Giai đoạn E — repair và approval

Chuẩn bị:

```text
Incident ID:
Source backup timestamp:
Source namespace:
Staging namespace:
Destination namespace:
Document keys:
Data transformation:
Indexes/validator target:
Dependencies:
Expected changes:
Rollback:
Approver:
```

Chỉ thực thi writes khi plan cụ thể được kiểm tra và cấp quyền theo quy trình tổ chức.

### Giai đoạn F — kiểm chứng và cleanup

- Đối soát keys/count/fields/relationships.
- Theo dõi application errors và query latency.
- Xác nhận indexes và validation hoạt động đúng.
- Giữ audit report của recovery.
- Xóa staging theo retention policy khi không còn cần; tránh để dữ liệu nhạy cảm tồn tại ngoài ý muốn.

## 37. Khôi phục thất bại: cách nhận diện nguyên nhân

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `namespace not found` / không có collection trong dump | Chọn sai source namespace hoặc backup thiếu dữ liệu | Kiểm tra manifest/dump source và spelling |
| Restore vào sai database | `--nsFrom`/`--nsTo` hoặc target URI sai | Dừng thao tác, xác minh mapping và môi trường |
| `duplicate key error` | `_id`/unique key đã tồn tại ở target hoặc backup trùng | Staging, reconcile keys, không bỏ qua tùy tiện |
| `Document failed validation` | Legacy BSON không đạt validator hiện hành | Phân tích field/type, migrate trong staging |
| `not authorized` | User thiếu quyền create/index/collMod/write | Cấp quyền theo thao tác, không dùng root mặc định |
| Index build thất bại | Duplicate keys, unsupported option, collation mismatch | Phân tích data/index definition và version |
| Query chậm sau restore | Index không được restore/build, stats/workload khác | `getIndexes()`, `explain()` và benchmark |
| Dữ liệu biến mất sau restore | TTL index hoặc retention job dọn data cũ | Kiểm tra TTL/options và background jobs |
| Count thấp hơn backup | Restore errors, filters, wrong namespace, TTL | Đọc logs, đối soát namespace và metadata |
| Count bằng nhưng sai order | Dữ liệu cũ hoặc khác business state | So business keys và dependencies |
| View không chạy | Thiếu underlying source collection hoặc mapping | Khôi phục/điều chỉnh dependencies |
| GridFS chỉ thấy tên file, download hỏng | Phục hồi `files` mà thiếu `chunks` | Phục hồi có kiểm soát cả hai collections |
| Atlas TCP timeout | Network access, NAT, DNS, private endpoint | Kiểm tra đường mạng trước auth |
| URI hoạt động nhưng insert bị từ chối | AuthZ/validator/unique constraints | Xem nested error chi tiết |
| Dữ liệu cũ không khớp app hiện tại | Schema drift và migration chưa chạy | Data transformation/version policy |
| Lỗi sau restart/failover | Topology/HA, write concern, session state | Kiểm tra replica set và kết quả writes |

**Không bỏ qua lỗi chỉ vì một số documents đã được restore.** Một thao tác trả lỗi có thể đã tạo dữ liệu một phần; phải xác nhận kết quả thực tế trước khi retry.

## 38. Những hiểu nhầm thường gặp

| Nhận định | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “Restore một collection sẽ khôi phục luôn mọi dependency” | References có thể nằm trong collections khác | Đối soát quan hệ nghiệp vụ |
| “`--nsInclude` lọc document theo field” | Nó chọn namespace, không phải query predicate | Restore staging rồi lọc documents |
| “`--nsTo` tự thay đổi schema cho phù hợp target” | Nó chỉ đổi namespace mapping | Schema migration riêng |
| “`--drop` chỉ xóa document trùng” | Nó drop collection đích tương ứng | Có nguy cơ mất dữ liệu mới |
| “Không dùng `--drop` là an toàn tuyệt đối” | Có thể duplicate/validation errors, partial writes | Vẫn cần staging và review |
| “Data restore xong là index chắc đã đúng” | Index build có thể lỗi hoặc bị skip | Kiểm tra `getIndexes()`/logs |
| “`--noIndexRestore` không ảnh hưởng correctness” | Unique constraints có thể thiếu | Áp lại indexes có kiểm soát |
| “`--noOptionsRestore` chỉ tắt log” | Nó bỏ restore collection options | Validator/collation có thể khác |
| “`--bypassDocumentValidation` chuyển kiểu tự động” | Bypass không transform data | Migrate types rõ ràng |
| “Validator mới tự sửa documents cũ” | Validation không có tính năng auto-repair | Data cleanup/backfill |
| “Dữ liệu từng hợp lệ luôn hợp lệ ở server mới” | Schema/version thay đổi | So theo target schema |
| “`validate` physical chứng minh JSON Schema đúng” | Mục đích kiểm tra khác | Query schema riêng |
| “Count bằng là hoàn toàn đúng” | Có thể thiếu/nhầm key | So business keys và relationships |
| “TTL chỉ tác động dữ liệu mới” | TTL có thể dọn các docs cũ restore | Review TTL trước |
| “Một BSON dump luôn nhất quán toàn cluster” | Có thể dump khi nhiều writes đang diễn ra | Dùng backup/PIT strategy phù hợp |
| “Partial restore luôn đạt point-in-time” | Namespace selection không replay history | PIT cần cơ chế riêng |
| “Restore Atlas snapshot giống mongorestore archive” | Hai hình thức có scope/capability khác | Kiểm tra Atlas backup features |
| “Một GridFS collection đủ để tải file” | File data và metadata ở hai collections | Khôi phục `files` và `chunks` |
| “Index name giống nhau thì semantics giống nhau” | Unique/collation/partial/TTL có thể khác | So toàn bộ index definition |
| “Có thể copy backup vào production bằng replaceOne hết” | Ghi đè state mới và side effects | Data-repair plan theo business keys |

## 39. Bài tập có đáp án

### Bài 1. Namespace

Trong MongoDB, `shop_app.orders` và `restore_review.orders` có phải cùng namespace?

**Đáp án:** Không. Namespace gồm database và collection; khác database nghĩa là khác namespace.

### Bài 2. Chọn một collection

Archive có `shop_app.orders`, `shop_app.customers`, `shop_app.payments`. Cần restore chỉ `orders`, dùng option nào?

**Đáp án:** `--nsInclude="shop_app.orders"`, với source dump/target URI đúng. Không dùng wildcard `shop_app.*` nếu chỉ muốn một collection.

### Bài 3. Đổi tên khi restore

Muốn đưa `shop_app.orders` thành `restore_review.orders`, dùng flags gì?

**Đáp án:** Kết hợp `--nsInclude="shop_app.orders"` với `--nsFrom="shop_app.orders"` và `--nsTo="restore_review.orders"`, thử trên môi trường lab.

### Bài 4. Lấy hai document

Chỉ muốn cứu `ORD-1001` và `ORD-1002`, dùng `--nsInclude` để lọc `orderNo` trực tiếp được không?

**Đáp án:** Không. Restore whole collection tương ứng vào staging, tìm hai documents theo key rồi copy có kiểm soát.

### Bài 5. `--drop`

Backup được tạo lúc 01:00, production có dữ liệu mới lúc 02:00. Chạy `mongorestore --drop` lên production `orders` có rủi ro gì?

**Đáp án:** Collection đích bị drop trước restore, dữ liệu tạo sau backup có thể biến mất. Cần restore staging và data-repair plan.

### Bài 6. Không dùng `--drop`

Target đã có document `_id: 1`, backup cũng có `_id: 1`. Công cụ có tự merge fields để giữ bản mới hơn không?

**Đáp án:** Không mặc nhiên. Có thể xảy ra duplicate key error; cần xác định semantic merge và conflict policy ở tầng ứng dụng.

### Bài 7. Metadata

Trong thư mục dump có `orders.bson` và `orders.metadata.json`. Hai file có vai trò gì?

**Đáp án:** BSON chứa documents; metadata thường mô tả collection options/indexes phục vụ restore theo tool/version.

### Bài 8. Tắt index restore

Restore với `--noIndexRestore` vào collection mới. Có chắc unique key `orderNo` được bảo vệ không?

**Đáp án:** Không. Cần tạo/kiểm tra unique index trên target; không coi data-only restore là tái tạo đầy đủ schema.

### Bài 9. Tắt option restore

Restore với `--noOptionsRestore` vào một collection mới. Có chắc validator cũ được phục hồi không?

**Đáp án:** Không. Option này bỏ qua collection options từ backup, gồm validator nếu nó được lưu trong options; target cần cấu hình schema theo mục tiêu.

### Bài 10. Unique index lỗi

Backup có hai documents cùng `orderNo`, nhưng target muốn unique index trên `orderNo`. Điều gì có thể xảy ra?

**Đáp án:** Index build hoặc insert có thể thất bại vì duplicate key. Cần phân tích/trị duplicate theo nghiệp vụ trong staging.

### Bài 11. TTL sau restore

Restore collection có TTL `expireAfterSeconds: 0` trên `expiresAt`, phần lớn dates đã qua. Vì sao documents có thể nhanh chóng biến mất?

**Đáp án:** TTL monitor có thể dọn những documents đã expired. Cần kiểm tra retention/index và mục tiêu phục hồi.

### Bài 12. BSON type

Validator yêu cầu `total` là Decimal128 nhưng backup chứa `total: "125000.00"`. Bypass validation có chuyển string sang Decimal128 không?

**Đáp án:** Không. Bypass chỉ bỏ qua validation check phù hợp khi ghi; dữ liệu vẫn là string và cần migration.

### Bài 13. Strict và moderate

Sự khác biệt cơ bản giữa `validationLevel: "strict"` và `"moderate"`?

**Đáp án:** Strict áp validation cho writes theo quy tắc; moderate có xử lý nhẹ hơn đối với một số updates trên documents hiện có vốn invalid, nhưng inserts vẫn phải được xem theo validator/action.

### Bài 14. Error và warn

`validationAction: "warn"` có đảm bảo document sai schema bị từ chối không?

**Đáp án:** Không. Warn cho phép write nhưng ghi cảnh báo theo hành vi server; `error` dùng để từ chối write không hợp lệ.

### Bài 15. Kiểm tra physical validation

Lệnh `db.runCommand({validate:"orders", full:true})` có chứng minh mọi order đều thỏa business JSON Schema mới?

**Đáp án:** Không. Storage validation và schema/business validation là hai loại kiểm tra khác nhau.

### Bài 16. Chọn index

Muốn chỉ khôi phục một secondary index bị thiếu trên production. Có nên drop cả collection và restore dump để lấy lại index?

**Đáp án:** Không nên. Lấy definition đúng, đánh giá impact rồi tạo lại index trên collection hiện tại theo quy trình được duyệt.

### Bài 17. Data consistency

Đơn hàng backup mang status `PAID`, nhưng payment hiện tại đã `REFUNDED`. Copy nguyên order cũ về production có an toàn không?

**Đáp án:** Chưa. Cần đối chiếu dependencies và chính sách nghiệp vụ, có thể chỉ phục hồi một số field hoặc tạo correction event.

### Bài 18. Point in time

Dump tạo lúc 01:00 có thể nhờ `--nsInclude` tự phục hồi chính xác trạng thái 02:59 không?

**Đáp án:** Không. Namespace selection không tạo lịch sử thay đổi sau backup. PIT cần backup/history mechanism phù hợp.

### Bài 19. Atlas snapshot

Có thể coi Atlas snapshot tương đương archive có thể chạy trực tiếp `mongorestore --nsInclude` không?

**Đáp án:** Không. Snapshot/backup service và Database Tools archive là hai cơ chế khác; phạm vi hỗ trợ selective restore phụ thuộc phương thức/tier.

### Bài 20. GridFS

Restore `fs.files` mà không restore `fs.chunks` có đủ để download những files lớn không?

**Đáp án:** Không. `files` chứa metadata; `chunks` chứa bytes. Cần đảm bảo dữ liệu và references nhất quán.

### Bài 21. Count

Backup có 10.000 documents, target sau restore cũng có 10.000 documents. Có đủ kết luận phục hồi đúng không?

**Đáp án:** Chưa. Cần so tập IDs/business keys, nội dung, schema, indexes và dependencies; count có thể bằng dù dữ liệu sai.

### Bài 22. Dùng `--bypassDocumentValidation`

Trong restore một collection production, team muốn bật bypass để mọi document cũ được chèn nhanh. Vấn đề?

**Đáp án:** Có thể đưa dữ liệu sai schema vào môi trường app hiện tại, trong khi unique/other constraints vẫn tồn tại. Nên xử lý trong staging với kế hoạch migration/validation.

### Bài 23. Restore sau lỗi deployment

Một rollout thêm validator mới làm các imports bị từ chối. Nên xóa validator trên production ngay lập tức không?

**Đáp án:** Không nên. Cần xác định lỗi schema, version ứng dụng, dữ liệu legacy, phân tích khả năng rollback rollout và sửa trong staging; đổi validator ảnh hưởng toàn bộ writes.

### Bài 24. Chọn chiến lược

Ứng dụng vẫn ghi liên tục; chỉ mất hai đơn hàng sau backup. Phương án khôi phục an toàn nào nên ưu tiên?

**Đáp án:** Bảo toàn production hiện tại, restore collection vào namespace staging, đối chiếu hai đơn hàng và dependencies, migrate schema nếu cần, thực hiện insert/patch idempotent có phê duyệt, rồi xác nhận kết quả.

## 40. Checklist kỹ thuật trước, trong và sau restore

### Trước restore

- [ ] Có incident/change ID, owner và phạm vi dữ liệu cần cứu.
- [ ] Đã xác định **source backup**, thời điểm backup và độ tin cậy của backup.
- [ ] Đã xác định **target URI/database/collection** rõ ràng.
- [ ] Đã sao lưu/truy xuất được trạng thái production hiện tại nếu cần rollback.
- [ ] Đã đọc chính xác namespace patterns và mapping.
- [ ] Đã kiểm tra Database Tools/server version và topology.
- [ ] Đã định nghĩa RPO/RTO, downtime và consistency expectations.
- [ ] Đã quyết định có cần PIT restore/cluster tạm hay chỉ BSON dump.
- [ ] Đã kiểm soát quyền truy cập tới staging chứa dữ liệu nhạy cảm.

### Trong staging restore

- [ ] Không sử dụng `--drop` ngoài môi trường/collection được phép thay thế.
- [ ] Chỉ chọn namespace cần thiết.
- [ ] Đọc kết quả `mongorestore` và lưu errors/warnings.
- [ ] Kiểm tra file dump/metadata hiện có và có được xử lý không.
- [ ] Xác minh count và sample business keys.
- [ ] Xác minh `getIndexes()`, unique/TTL/partial/collation.
- [ ] Xác minh collection options và validator.
- [ ] Tìm documents legacy không đạt target schema.
- [ ] Đối soát dependencies giữa collections.

### Trước khi đưa dữ liệu về production

- [ ] Có danh sách record/fields cụ thể được duyệt.
- [ ] Có chính sách insert/patch/conflict/idempotency.
- [ ] Đã migrate schema/type/units/timezone nếu cần.
- [ ] Đã thử trên staging-to-staging với điều kiện gần production.
- [ ] Đã xác minh target unique constraints và authorization.
- [ ] Có phương án rollback đối với từng write operation.
- [ ] Có kế hoạch bảo vệ các workflows thanh toán/outbox/notifications.

### Sau phục hồi

- [ ] Đối soát dữ liệu bằng business keys và các quan hệ quan trọng.
- [ ] Kiểm tra indexes và query performance.
- [ ] Kiểm tra schema validation và application behavior.
- [ ] Theo dõi errors, duplicate keys và TTL/retention.
- [ ] Lưu audit log/recovery report theo policy.
- [ ] Xóa staging và access tạm khi không còn nhu cầu.
- [ ] Cập nhật runbook để tránh lặp lại sự cố.

## 41. Tổng kết

**Khôi phục có chọn lọc** trong MongoDB là một quy trình gồm nhiều quyết định, không chỉ một flag `mongorestore`. `--nsInclude` và `--nsExclude` giới hạn **namespace nguồn** được phục hồi; `--nsFrom` và `--nsTo` cho phép **đổi tên database/collection ở đích**, rất hữu ích để tạo môi trường **staging**. Chúng **không tự lọc document theo business query**.

**`--drop`** có thể thay thế toàn bộ collection đích trong phạm vi restore, nên không được dùng như một cách merge dữ liệu mới và cũ. Với nhu cầu chỉ cứu vài document, cần restore staging, kiểm tra business keys/dependencies, rồi copy có kiểm soát.

**Index và collection options** là một phần quan trọng của kết quả phục hồi. `--noIndexRestore` và `--noOptionsRestore` cho phép bỏ qua một phần metadata, nhưng có thể làm thay đổi **unique constraints, TTL, collation, schema validator và hiệu năng truy vấn**. `--bypassDocumentValidation` có thể giúp nạp legacy data trong điều kiện phù hợp, nhưng không biến dữ liệu sai kiểu thành hợp lệ.

Quy trình an toàn là **bảo toàn trạng thái hiện tại → khôi phục vào namespace cô lập → kiểm tra documents/index/validator → đối chiếu nghiệp vụ → áp dụng repair có phê duyệt → xác minh và dọn staging**. Nếu mục tiêu là trạng thái tại một thời điểm cụ thể, phải đánh giá **point-in-time recovery** và khả năng của backup platform, chứ không nhầm nó với namespace filtering.

### Tài liệu tham khảo chính thức

- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Specify Validation Level](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/)
- [MongoDB Manual — Specify Validation Action](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-action/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Modify Collection Validation](https://www.mongodb.com/docs/manual/core/schema-validation/modify-schema-validation/)
- [MongoDB Atlas — Backup and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)

# Thiết kế index, schema validation và migration cho nhiều tenant

Trong hệ thống **multi-tenant**, nhiều khách hàng (tenant) sử dụng cùng một ứng dụng nhưng dữ liệu của họ phải được tách biệt về quyền truy cập, độ tin cậy và khả năng vận hành. Với **SPRING_DATA_MONGODB**, ứng dụng dùng `MongoClient`, `MongoDatabaseFactory`, `MongoTemplate` hoặc repository để kết nối, ánh xạ document, truy vấn và quản lý nhiều database MongoDB. Khi tăng số lượng tenant, **index**, **schema validation** và **migration** phải được áp dụng nhất quán trên đúng database/collection của từng tenant.

Bài học thuộc chương **Nhiều database**. Trọng tâm là cách thiết kế và triển khai ba thành phần trên mà không làm lẫn dữ liệu giữa các tenant, không tạo xung đột khi cập nhật schema và có khả năng theo dõi, chạy lại khi migration thất bại.

## 1. Bài toán thực tế và mục tiêu

Giả sử một nền tảng quản lý đơn hàng phục vụ hai tenant:

- `north` lưu dữ liệu tại database `commerce_north`.
- `south` lưu dữ liệu tại database `commerce_south`.

Cả hai có collection `orders`, nhưng mỗi tenant được phép có đơn hàng cùng mã `ORD-001`. Ứng dụng cần tìm các đơn theo trạng thái và thời điểm tạo, xác thực cấu trúc document, đồng thời nâng schema từ phiên bản 1 sang phiên bản 2.

Sau bài này, người học có thể:

1. Chọn chiến lược cô lập tenant ảnh hưởng đến cấu trúc index và phạm vi unique constraint.
2. Thiết kế index theo truy vấn thực tế, tránh index dư thừa và hiểu giới hạn khi sharding.
3. Thiết lập MongoDB `$jsonSchema` validator cho collection và xử lý dữ liệu lịch sử chưa hợp lệ.
4. Thực hiện migration theo các pha tương thích ngược, backfill, kiểm chứng và siết validation.
5. Lập trình thao tác theo từng tenant qua Spring Data MongoDB, kiểm thử và chẩn đoán lỗi vận hành.

## 2. Lựa chọn mô hình cô lập tenant

Không phải mọi hệ thống multi-tenant đều cần một database riêng cho mỗi tenant. Quyết định cách lưu trữ sẽ quyết định **phạm vi** của index, validator và migration.

| Mô hình | Ví dụ | Index và unique | Schema validation và migration |
| --- | --- | --- | --- |
| **Shared database, shared collection** | `app.orders` có trường `tenantId` | Index phục vụ truy vấn cần bắt đầu bằng `tenantId` khi phù hợp; unique thường gồm `tenantId` và khóa nghiệp vụ | Một validator chung cho collection; migration lọc theo tenant nếu cần triển khai từng đợt |
| **Database per tenant** | `commerce_north.orders`, `commerce_south.orders` | Mỗi database có các index riêng; `orderNo` unique chỉ trong một collection của một tenant | Tạo/điều chỉnh validator và chạy migration trên **từng database tenant** |
| **Cluster per tenant** | Tenant có MongoDB deployment riêng | Index và unique tách hoàn toàn theo deployment | Phải điều phối migration, kết nối, credentials và phiên bản MongoDB của từng cluster |

Trong chương **Nhiều database**, ta chủ yếu thực hành **database per tenant**. Hai database có thể cùng nằm trên một cluster. Khi cùng cluster, cùng credentials và thông số driver, có thể tái sử dụng **một `MongoClient`** và tạo factory/template với database mặc định khác nhau. Nếu các tenant nằm ở cluster hoặc nhóm credentials khác nhau, phải quản lý những `MongoClient` phù hợp. Không tạo một client mới cho mỗi HTTP request.

Sơ đồ trách nhiệm:

```text
JWT / auth context -> tenant registry -> tenantId đã kiểm tra quyền
                                             |
                                             v
                                TenantTemplateResolver
                                             |
                        +--------------------+-------------------+
                        |                                        |
                 commerce_north                           commerce_south
                        |                                        |
                MongoTemplate N                          MongoTemplate S
                        |                                        |
                orders, indexes,                         orders, indexes,
                validator, ledger                        validator, ledger
                        +--------------------+-------------------+
                                             |
                                    MongoClient chung
                                    (cùng deployment)
```

**Nguyên tắc bảo mật:** tenant được lấy từ danh tính đã xác thực/ủy quyền, đối chiếu với tenant registry; không ghép trực tiếp giá trị `tenantId` tùy ý từ URL hoặc body thành tên database. Mọi thao tác nghiệp vụ và migration phải đi qua một cơ chế chọn database đã kiểm soát.

## 3. Xác định schema và truy vấn trước khi thiết kế index

Ví dụ, document đơn hàng **v1**:

```javascript
{
  _id: ObjectId("65e000000000000000000001"),
  orderNo: "ORD-001",
  customer: "customer-17",
  status: "PAID",
  createdAt: ISODate("2026-01-10T10:00:00Z"),
  amountCents: NumberLong("259900")
}
```

Schema mục tiêu **v2** đổi `customer` thành `customerId` và thêm `schemaVersion`:

```javascript
{
  _id: ObjectId("65e000000000000000000001"),
  orderNo: "ORD-001",
  customerId: "customer-17",
  status: "PAID",
  createdAt: ISODate("2026-01-10T10:00:00Z"),
  amountCents: NumberLong("259900"),
  schemaVersion: NumberInt(2)
}
```

Tập truy vấn sản phẩm cần hỗ trợ:

| Nhu cầu | Query thường gặp | Điều cần bảo đảm |
| --- | --- | --- |
| Tìm đơn theo mã | `find({ orderNo: "ORD-001" })` | Mã đơn duy nhất **trong mỗi tenant** |
| Danh sách đơn đã thanh toán gần đây | `find({ status: "PAID" }).sort({ createdAt: -1 }).limit(50)` | Lọc trạng thái và trả về theo thứ tự thời gian |
| Danh sách đơn của khách | `find({ customerId: "customer-17" }).sort({ createdAt: -1 })` | Sau migration, truy vấn theo trường mới |
| Dọn dữ liệu tạm hết hạn | Truy vấn/TTL trên `sessions.expiresAt` | Có chính sách lưu giữ rõ ràng, không xóa nhầm dữ liệu bắt buộc phải lưu |

Một index tốt phải xuất phát từ bộ lọc, sort, tính chọn lọc, số lần đọc/ghi và kích thước dữ liệu. Không nên đánh index lên mọi trường chỉ vì chúng xuất hiện trong model. Index tăng chi phí ghi, bộ nhớ, dung lượng đĩa và thời gian triển khai cho **tất cả tenant**.

## 4. Thiết kế index cho từng database tenant

Với mô hình database per tenant, quản trị viên hoặc quy trình migration chọn database cụ thể rồi tạo các index. Ví dụ dưới đây chạy trong `mongosh` với quyền phù hợp.

```javascript
const tenantDb = db.getSiblingDB("commerce_north");

// Bảo đảm mỗi tenant chỉ có một orderNo.
tenantDb.orders.createIndex(
  { orderNo: 1 },
  { name: "ux_orders_order_no", unique: true }
);

// Hỗ trợ lọc status, sắp xếp createdAt giảm dần.
tenantDb.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "ix_orders_status_created_at" }
);

// Chỉ tạo sau khi ứng dụng và backfill đã dùng customerId.
tenantDb.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "ix_orders_customer_created_at" }
);
```

Lệnh tạo index trong `commerce_north` **không tự áp dụng** vào `commerce_south`. Công cụ provisioning/migration phải chạy cùng bộ định nghĩa trên từng database thuộc phạm vi triển khai. Dùng tên index ổn định để nhận diện và kiểm tra trạng thái; nếu cùng tên nhưng đổi key/options, lệnh tạo lại có thể báo xung đột. Khi thay cấu trúc index, thường tạo index với tên mới, xác minh và chỉ sau đó mới loại bỏ index cũ nếu an toàn.

### 4.1. Tính duy nhất và dữ liệu lỗi trước khi tạo unique index

Mỗi collection có namespace riêng nên mã `ORD-001` có thể xuất hiện một lần tại `commerce_north.orders` và một lần tại `commerce_south.orders`. Unique index trên `orderNo` chỉ chặn trùng **trong collection hiện tại**.

Trước khi triển khai index unique cho collection đã có dữ liệu, kiểm tra bản ghi trùng:

```javascript
tenantDb.orders.aggregate([
  { $group: { _id: "$orderNo", count: { $sum: 1 } } },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } }
]);
```

Cần xử lý cả document **thiếu `orderNo` hoặc có `null`**: unique single-field index thông thường không thể chấp nhận nhiều document cùng có giá trị khóa `null`/thiếu trường như kỳ vọng của nhiều hệ thống nghiệp vụ. Hãy sửa dữ liệu hoặc định nghĩa partial index phù hợp với ràng buộc thật; không dùng partial index chỉ để che một vấn đề dữ liệu chưa được giải quyết.

Nếu mã nghiệp vụ không phân biệt chữ hoa/thường, cần quyết định chính sách chuẩn hóa hoặc collation khi tạo unique index; truy vấn muốn sử dụng index có collation phải tương thích với collation đó.

### 4.2. Trường hợp nhiều tenant dùng chung collection

Nếu thay bằng `app.orders` chứa `tenantId`, index phải phản ánh phạm vi tenant:

```javascript
const sharedDb = db.getSiblingDB("app");

sharedDb.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  { name: "ux_orders_tenant_order", unique: true }
);

sharedDb.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "ix_orders_tenant_status_created_at" }
);
```

Một unique index chỉ trên `orderNo` sẽ vô tình cấm hai tenant sử dụng cùng mã đơn. Từng truy vấn và thao tác cập nhật/xóa ở shared collection phải có **điều kiện tenant** do tầng ủy quyền kiểm soát; chỉ có index tiền tố `tenantId` không tự tạo ranh giới bảo mật.

Với sharded collection, cần kiểm tra quy tắc unique index gắn với shard key: unique index trên sharded collection thường cần **shard key làm tiền tố** của index; một số loại shard key/index có giới hạn riêng. Không áp dụng nguyên mẫu ở trên vào sharded collection mà chưa kiểm tra cấu hình phân mảnh thực tế.

### 4.3. TTL, partial index và chiến lược đo hiệu năng

Với session tạm (không phải đơn hàng cần lưu trữ lâu dài), TTL index có thể tự xóa bản ghi sau thời điểm hết hạn:

```javascript
tenantDb.sessions.createIndex(
  { expiresAt: 1 },
  { name: "ttl_sessions_expires_at", expireAfterSeconds: 0 }
);
```

`expiresAt` phải là giá trị BSON Date hợp lệ. TTL monitor xóa bất đồng bộ nên dữ liệu không biến mất chính xác ngay tại thời điểm hết hạn; kiểm tra quyền truy cập và hết hạn ở tầng ứng dụng nếu yêu cầu chặn tức thời. Không dùng TTL để thay cho cơ chế lưu giữ/chứng cứ pháp lý hoặc xóa tenant có kiểm soát.

Partial index chỉ chứa document đáp ứng `partialFilterExpression`, giúp giảm kích thước trong một số tình huống. Truy vấn muốn được hưởng lợi thường cần điều kiện phù hợp với bộ lọc của partial index. Không mặc định rằng một index nhỏ hơn luôn nhanh hơn.

Để đánh giá index theo truy vấn thật:

```javascript
tenantDb.orders
  .find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(50)
  .explain("executionStats");
```

Theo dõi `winningPlan`, `IXSCAN`/`COLLSCAN`, `totalKeysExamined`, `totalDocsExamined`, thời gian thực thi và độ trễ ghi. `IXSCAN` không tự động đồng nghĩa truy vấn tối ưu; phải xem lượng document quét, sort, khả năng phủ index và tải thực tế. Tenant rất lớn có thể cần tập index khác tenant nhỏ, nhưng mọi ngoại lệ phải được quản lý có phiên bản.

## 5. Quản lý index với Spring Data MongoDB

Với `MongoTemplate`, Spring Data MongoDB cung cấp `IndexOperations` và `ensureIndex`. Dùng chúng trong quá trình provisioning/migration của **từng tenant** thay vì khởi tạo index tùy ý trên mọi request.

Ví dụ Java:

```java
package com.example.multitenant.migration;

import org.springframework.data.domain.Sort.Direction;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.IndexOperations;

public final class OrderIndexInstaller {

    public void ensureIndexes(MongoTemplate template) {
        IndexOperations indexes = template.indexOps("orders");

        // Chỉ thực hiện khi đã kiểm tra và xử lý orderNo trùng.
        indexes.ensureIndex(new Index()
                .on("orderNo", Direction.ASC)
                .unique()
                .named("ux_orders_order_no"));

        indexes.ensureIndex(new Index()
                .on("status", Direction.ASC)
                .on("createdAt", Direction.DESC)
                .named("ix_orders_status_created_at"));

        indexes.ensureIndex(new Index()
                .on("customerId", Direction.ASC)
                .on("createdAt", Direction.DESC)
                .named("ix_orders_customer_created_at"));
    }
}
```

Để chạy cho `north`, truyền template trỏ đến `commerce_north`; cho `south`, truyền template trỏ đến `commerce_south`. Phương thức trên giúp đảm bảo định nghĩa index tồn tại theo tên/key/options khi không có xung đột, **không** tự kiểm tra và sửa dữ liệu gây lỗi unique, không tự đổi cấu hình index đã tồn tại nhưng khác thông số.

Có thể dùng `@Indexed`, `@CompoundIndex` trên model, nhưng **không mặc định dựa vào cơ chế auto-index creation khi có nhiều database**. Spring Data MongoDB không tự tạo index mặc định trong những phiên bản hiện hành; và ngay cả khi bật cấu hình đó, phải bảo đảm đúng template/mapping context/collection của từng tenant. Trên production, quy trình migration có phiên bản và kiểm thử rõ ràng thường giúp kiểm soát thay đổi index tốt hơn.

## 6. Schema validation với MongoDB `$jsonSchema`

### 6.1. Định nghĩa schema v2

MongoDB hỗ trợ collection-level JSON Schema validator với cú pháp `$jsonSchema` (MongoDB JSON Schema có các kiểu BSON như `int`, `long`, `date`). Ví dụ đầy đủ cho `orders` v2:

```javascript
const ordersV2Schema = {
  bsonType: "object",
  required: [
    "orderNo", "customerId", "status",
    "createdAt", "amountCents", "schemaVersion"
  ],
  properties: {
    orderNo: {
      bsonType: "string",
      minLength: 1,
      description: "Mã đơn bắt buộc"
    },
    customerId: {
      bsonType: "string",
      minLength: 1
    },
    status: {
      enum: ["NEW", "PAID", "CANCELED"]
    },
    createdAt: {
      bsonType: "date"
    },
    amountCents: {
      bsonType: "long",
      minimum: 0
    },
    schemaVersion: {
      bsonType: "int",
      enum: [2]
    }
  }
};

const ordersV2Validator = { $jsonSchema: ordersV2Schema };
```

Ý nghĩa:

- `required` yêu cầu các trường xuất hiện; các điều kiện `bsonType`/`enum`/`minimum` kiểm tra giá trị cụ thể.
- `amountCents` dùng BSON `long` nhằm lưu số tiền nguyên theo đơn vị nhỏ nhất; ứng dụng Java có thể ánh xạ kiểu `Long`. Đừng thay bằng `double` khi cần độ chính xác tiền tệ.
- `schemaVersion` dùng BSON `int`; application/migration phải ghi đúng kiểu như `NumberInt(2)`.
- Validator không tạo unique constraint hay index. Cần cả **validator** và **unique index** để đồng thời kiểm soát cấu trúc và tính duy nhất.
- Không bắt buộc mọi field phải xuất hiện trong `properties`; để cấm field ngoài danh sách cần tính đến `_id` và quy tắc `additionalProperties`, tránh làm hỏng các document hợp lệ hoặc mapping của ứng dụng.

### 6.2. Collection mới: tạo kèm validator

Nếu collection chưa tồn tại và ứng dụng chỉ ghi schema v2:

```javascript
const tenantDb = db.getSiblingDB("commerce_north");

tenantDb.createCollection("orders", {
  validator: ordersV2Validator,
  validationLevel: "strict",
  validationAction: "error"
});
```

Khi `validationAction: "error"`, write vi phạm validator bị từ chối (thường là `DocumentValidationFailure`, mã 121). `validationLevel: "strict"` áp dụng validation cho insert và update theo quy tắc MongoDB. Nếu collection đã tồn tại, `createCollection` không phải lệnh thay validator; dùng `collMod` ở mục tiếp theo.

### 6.3. Collection đang chạy: triển khai validator theo từng pha

Trong giai đoạn còn tài liệu v1, siết ngay `strict + error` có thể chặn các write/update hợp lệ theo logic ứng dụng cũ. Bắt đầu bằng cảnh báo để quan sát:

```javascript
tenantDb.runCommand({
  collMod: "orders",
  validator: ordersV2Validator,
  validationLevel: "strict",
  validationAction: "warn"
});
```

`warn` cho phép ghi nhưng phát ra cảnh báo về vi phạm để điều tra. `strict` yêu cầu kiểm tra các insert/update; tùy chiến lược chuyển đổi, có thể cân nhắc `moderate` để không từ chối cập nhật một số document cũ vốn đã không hợp lệ sau khi bật `error`. Phải hiểu rằng `moderate` không bảo đảm mọi write đều đáp ứng schema mục tiêu. Chọn cách nào cũng cần backfill và đếm tài liệu vi phạm.

**Quan trọng:** thay validator không làm MongoDB tự quét hoặc sửa mọi document tồn tại trước đó. Muốn xác nhận tất cả document đang lưu đều đạt yêu cầu, cần chạy truy vấn kiểm tra riêng (mục 8).

Sau khi ứng dụng tương thích v2 và số document vi phạm bằng 0, chuyển sang chế độ chặn:

```javascript
tenantDb.runCommand({
  collMod: "orders",
  validator: ordersV2Validator,
  validationLevel: "strict",
  validationAction: "error"
});
```

Cả `createCollection` lẫn `collMod` chỉ tác động lên database được chọn. Lệnh đã chạy trên tenant `north` không đổi validator của tenant `south`. Các thay đổi validator nên được quản lý dưới quyền migration account, không để tài khoản ứng dụng thông thường tùy ý sửa.

### 6.4. Schema của shared collection và giới hạn theo tenant

Nếu dùng shared collection, toàn bộ tenant dùng **một validator**. Có thể biểu diễn nhiều phiên bản tài liệu được chấp nhận bằng ràng buộc phù hợp (`oneOf`/`anyOf` trong khả năng validator), song cách này làm tăng độ phức tạp, kéo dài thời gian giữ tương thích. Với các tenant yêu cầu schema khác nhau lâu dài, hãy đánh giá database/collection riêng hoặc chia version có điều kiện, thay vì duy trì một validator khổng lồ khó chứng minh tính đúng đắn.

Schema validator không có thông tin về người dùng đã xác thực, nên không ngăn một request ghi nhầm vào collection/database của tenant khác. Tenant isolation vẫn phải đến từ authorization, connection routing và quy trình test.

## 7. Migration schema v1 → v2 theo phương án expand–migrate–contract

Migration dữ liệu phải xét đến khả năng hệ thống đang phục vụ request và các tenant có thể đang ở những phiên bản khác nhau.

**Pha 0 — Chuẩn bị.** Kiểm kê số tenant, phiên bản server, kích thước collection, index hiện có, tỷ lệ tài liệu v1 và dữ liệu lỗi. Sao lưu và **kiểm chứng khả năng khôi phục**. Xác định đặc tả v2, thứ tự triển khai, hạn mức tải, thời điểm bảo trì và tiêu chí thành công/thất bại. Chọn nhóm tenant thử nghiệm trước.

**Pha 1 — Expand ứng dụng.** Phát hành ứng dụng có thể **đọc được cả `customer` và `customerId`**, nhưng các bản ghi mới ghi `customerId` cùng `schemaVersion = 2`. Đảm bảo logic đọc ghi và index dùng được trong thời gian dữ liệu v1/v2 cùng tồn tại. Đừng chỉ đổi tên field Java rồi giả định tài liệu MongoDB lịch sử sẽ tự được chuyển đổi.

**Pha 2 — Quan sát schema.** Bật `collMod` với `validationAction: "warn"` cho từng tenant để phát hiện write trái cấu trúc v2. Bảo đảm không còn tiến trình cũ tiếp tục ghi document v1 (hoặc xây cơ chế tương thích nếu cần).

**Pha 3 — Backfill idempotent.** Chỉ thao tác trên tenant đang được chọn. Ví dụ với tập dữ liệu nhỏ/vừa:

```javascript
const tenantDb = db.getSiblingDB("commerce_north");

// Chuyển document v1 có customer hợp lệ sang customerId.
const renameResult = tenantDb.orders.updateMany(
  {
    customerId: { $exists: false },
    customer: { $type: "string" }
  },
  [
    {
      $set: {
        customerId: "$customer",
        schemaVersion: NumberInt(2)
      }
    },
    { $unset: "customer" }
  ]
);

// Hoàn thiện version cho document đã có customerId.
const versionResult = tenantDb.orders.updateMany(
  {
    customerId: { $type: "string" },
    schemaVersion: { $ne: NumberInt(2) }
  },
  { $set: { schemaVersion: NumberInt(2) } }
);

printjson({
  renamed: renameResult.modifiedCount,
  versioned: versionResult.modifiedCount
});
```

Hai cập nhật có điều kiện nên **có thể chạy lại** khi gặp lỗi giữa chừng; sau khi chuyển thành công, document không còn khớp điều kiện pha đổi tên. Tuy nhiên:

- Document thiếu cả `customer` lẫn `customerId`, hoặc có kiểu dữ liệu bất thường, phải vào danh sách xử lý ngoại lệ; không gán đại một customer giả.
- `updateMany` không phải một transaction atomic cho mọi document. Với collection lớn, chia nhỏ theo khoảng `_id` hoặc cursor, dùng `bulkWrite` với batch vừa phải, kiểm soát tải và lưu checkpoint.
- Nếu ứng dụng khác sửa cùng document trong lúc backfill, phải thiết kế quy tắc cạnh tranh/đồng bộ hoặc điều kiện update thích hợp để tránh ghi đè dữ liệu. Ví dụ trên giả định quá trình triển khai đã bảo đảm writer sử dụng v2.
- Không tự chuyển các trường tiền tệ từ `double` sang `long` bằng phép nhân 100 rồi làm tròn tùy tiện; nếu có dữ liệu kiểu cũ, cần đặc tả chuyển đổi chính xác và kiểm thử về tiền.

**Pha 4 — Kiểm chứng và tạo index v2.** Kiểm tra dữ liệu, đối soát số lượng, phát hiện trùng mã đơn, xác minh cả trường mới và kết quả truy vấn. Chỉ triển khai unique index sau khi dữ liệu đáp ứng điều kiện. Trước khi chạy tại mỗi tenant, đo thời gian tạo index và ảnh hưởng tải.

**Pha 5 — Contract.** Khi dữ liệu tất cả tenant trong phạm vi phát hành hợp lệ và không còn writer v1, chuyển validator sang `strict + error`; sau đó gỡ code đọc trường cũ và những index/logic hỗ trợ v1 không còn cần thiết. Không xóa trường/index cũ trước khi có bằng chứng cả ứng dụng lẫn dữ liệu đã chuyển xong.

Các pha trên mô tả một **quy trình mở rộng rồi thu hẹp hợp đồng**, không mặc định mọi tenant được nâng cấp đồng thời. Mỗi tenant nên có trạng thái migration, thời điểm kiểm tra và kết quả triển khai riêng.

## 8. Kiểm tra độ sạch dữ liệu trước khi siết validator

Sau khi backfill, kiểm tra v1 chưa chuyển:

```javascript
tenantDb.orders.countDocuments({
  $or: [
    { customerId: { $exists: false } },
    { schemaVersion: { $ne: NumberInt(2) } }
  ]
});
```

Đếm document vi phạm **toàn bộ schema v2** (bao gồm các trường khác như `amountCents` và `createdAt`):

```javascript
tenantDb.orders.countDocuments({
  $nor: [{ $jsonSchema: ordersV2Schema }]
});
```

Truy vấn trên dùng `ordersV2Schema` đã định nghĩa ở mục 6, nên cần chạy trong cùng phiên `mongosh` hoặc nạp lại định nghĩa schema trước. Số lượng bằng 0 chứng minh dữ liệu trong lần quét đó đáp ứng validator; các write đồng thời vẫn có thể phát sinh sai lệch. Vì vậy cần siết chế độ chặn khi đã kiểm soát writer, rồi giám sát lỗi ghi sau triển khai.

Kiểm tra hệ thống index hiện tại:

```javascript
tenantDb.orders.getIndexes();
```

Và kiểm tra truy vấn mục tiêu bằng `explain("executionStats")`. Chỉ hoàn tất tenant khi dữ liệu đạt yêu cầu, index phù hợp, ứng dụng đọc/ghi ổn và có thông tin rollback/hỗ trợ khắc phục.

## 9. Định tuyến tenant trong Spring Data MongoDB

### 9.1. Một client, nhiều MongoTemplate trong cùng deployment

Ví dụ dưới đây cho thấy cách dùng chung một `MongoClient` giữa hai database. Danh sách tenant→database được cố định để minh họa; trong môi trường thật lấy từ tenant registry có xác thực, hỗ trợ thay đổi có kiểm soát.

```yaml
app:
  mongo:
    uri: ${MONGODB_URI:mongodb://localhost:27017}
```

```java
package com.example.multitenant.config;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;
import org.springframework.stereotype.Component;

@Configuration(proxyBeanMethods = false)
class MongoConnectionConfig {

    @Bean(destroyMethod = "close")
    MongoClient sharedMongoClient(
            @Value("${app.mongo.uri}") String uri) {
        return MongoClients.create(uri);
    }
}

@Component
public class TenantTemplateResolver {

    private static final Map<String, String> DEMO_DATABASES = Map.of(
            "north", "commerce_north",
            "south", "commerce_south"
    );

    private final MongoClient sharedClient;
    private final ConcurrentMap<String, MongoTemplate> templates =
            new ConcurrentHashMap<>();

    public TenantTemplateResolver(MongoClient sharedClient) {
        this.sharedClient = sharedClient;
    }

    public MongoTemplate forTenant(String authorizedTenantId) {
        String database = DEMO_DATABASES.get(authorizedTenantId);
        if (database == null) {
            throw new IllegalArgumentException(
                    "Unknown or unauthorized tenant");
        }

        return templates.computeIfAbsent(
                database,
                name -> new MongoTemplate(
                        new SimpleMongoClientDatabaseFactory(
                                sharedClient, name)));
    }
}
```

Trong ví dụ, `authorizedTenantId` **phải đến từ tầng phân quyền**; resolver vẫn kiểm tra tên tenant có trong registry. Sơ đồ này có số tenant ít và ổn định; khi có hàng nghìn tenant, cache `MongoTemplate` vô hạn có thể tốn tài nguyên mapping và bộ nhớ. Cần đánh giá cache có giới hạn, quản trị registry hoặc factory chọn database động để giảm số instance, đồng thời giữ khả năng cấu hình converter, mapping, index của từng tenant một cách rõ ràng.

Khi dùng `@EnableMongoRepositories`, `mongoTemplateRef` liên kết một nhóm repository với **template cố định**. Repository kiểu đó không tự chuyển database theo tenant ở runtime. Với tenant được chọn động, sử dụng `MongoTemplate` qua resolver có kiểm soát hoặc triển khai một tầng định tuyến factory/repository chuyên biệt, kèm kiểm thử phân tách ngữ cảnh. Không nên lưu tenant hiện tại bằng biến static toàn cục hoặc state mutable dùng chung giữa các request.

### 9.2. Chạy migration trên đúng template

Một bước dựng index theo tenant có thể dùng lại `OrderIndexInstaller` ở mục 5:

```java
package com.example.multitenant.migration;

import com.example.multitenant.config.TenantTemplateResolver;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class TenantIndexMigration {

    private final TenantTemplateResolver resolver;
    private final OrderIndexInstaller installer;

    public TenantIndexMigration(TenantTemplateResolver resolver) {
        this.resolver = resolver;
        this.installer = new OrderIndexInstaller();
    }

    public void migrateOneTenant(String authorizedTenantId) {
        MongoTemplate template = resolver.forTenant(authorizedTenantId);

        // Chạy sau bước làm sạch dữ liệu và trước khi đánh dấu
        // migration đã hoàn tất trong migration ledger.
        installer.ensureIndexes(template);
    }
}
```

Đoạn này chỉ minh họa **bước index** trong migration. Bước backfill, `collMod` và cập nhật ledger phải được orchestrator gọi riêng theo thứ tự của mục 7; không tự chạy `migrateOneTenant` cho mọi request. Với nhiều tenant, ưu tiên job được quản trị riêng, giới hạn concurrency và ghi log theo mã tenant logic.

### 9.3. Theo dõi phiên bản migration cho từng tenant

Đặt một collection `schema_migrations` trong **mỗi database tenant**. Ví dụ một bản ghi:

```javascript
{
  _id: "orders_v2",
  status: "APPLIED",
  appliedAt: ISODate("2026-11-20T00:00:00Z"),
  sourceVersion: 1,
  targetVersion: 2,
  updatedCount: 18450,
  schemaChecksum: "sha256:..."
}
```

`_id` là khóa duy nhất mặc định cho mỗi collection, giúp định danh một migration trong một tenant. Ghi trạng thái `APPLIED` **sau khi** đã kiểm chứng dữ liệu, index, validator và truy vấn quan trọng. Khi lỗi, lưu trạng thái và chi tiết retry/checkpoint có kiểm soát để tiếp tục từ điểm dừng. Đừng chỉ dựa vào bản ghi ledger để kết luận database đã đúng nếu index/schema có thể đã bị sửa thủ công.

Khi có nhiều instance/job runner, dùng cơ chế lock có lease và bảo vệ chống hai worker cùng migrate một tenant; quá hạn lease phải tránh runner cũ tiếp tục ghi gây xung đột. Lệnh provisioning/migration cần đủ quyền thay index/validator, trong khi quyền runtime ứng dụng nên được giới hạn theo nghiệp vụ.

## 10. Kiểm thử và giám sát rollout nhiều tenant

### 10.1. Ma trận kiểm thử tối thiểu

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Tenant `north` có `ORD-001` và `south` cũng có `ORD-001` | Cả hai hợp lệ trong mô hình database per tenant |
| Ghi hai đơn trùng `orderNo` vào cùng database tenant | Unique index từ chối bản ghi trùng |
| Thiếu `customerId` khi validator `strict + error` | MongoDB từ chối write (thường mã 121) |
| Dữ liệu v1 được backfill rồi chạy lại migration | Không tạo bản ghi trùng; schema v2 vẫn hợp lệ |
| Tenant không thuộc registry hoặc không được cấp quyền | Request bị từ chối trước khi chọn MongoTemplate |
| Repository/template dùng sai database | Integration test phát hiện tenant bị lẫn hoặc đích database sai |
| Lỗi network sau khi xử lý được nửa tenant | Có checkpoint/trạng thái để chạy lại an toàn |
| Lệnh tạo index khi tên cũ có cấu trúc khác | Không tự coi là thành công; cần migration thay index rõ ràng |

### 10.2. Test với môi trường MongoDB thật

Có thể dùng Testcontainers với MongoDB hoặc môi trường kiểm thử tương đương. Tạo hai database tenant, chạy provisioning, insert bộ document v1/v2, thực hiện migration, rồi kiểm tra `getCollectionInfos()`/`getIndexes()`, kiểm tra validator và truy vấn đối chiếu.

Đoạn kiểm tra cơ bản:

```java
MongoTemplate north = resolver.forTenant("north");
MongoTemplate south = resolver.forTenant("south");

assertEquals("commerce_north", north.getDb().getName());
assertEquals("commerce_south", south.getDb().getName());

assertTrue(north.indexOps("orders").getIndexInfo().stream()
        .anyMatch(i -> "ux_orders_order_no".equals(i.getName())));
```

Các assertion giả định đã import JUnit 5 `assertEquals`, `assertTrue` và đã chạy migration. Test này xác nhận wiring và index name; cần thêm thử insert/query thực tế để chứng minh dữ liệu không vượt ranh giới tenant và unique/validator hoạt động đúng. Hai database cùng cluster vẫn có thể bị lỗi chọn nhầm nếu tenant registry sai.

### 10.3. Tổ chức rollout

Rollout nên có các trạng thái cụ thể, ví dụ:

```text
PENDING -> RUNNING -> VERIFYING -> APPLIED
                  \-> FAILED_RETRYABLE
                  \-> FAILED_MANUAL_REVIEW
```

Một pipeline triển khai có thể:

1. Khóa lịch sử migration và xác nhận đúng tenant/database/cluster trước mỗi lần chạy.
2. Chọn nhóm tenant canary nhỏ, hoàn tất và giám sát trước khi mở rộng.
3. Giới hạn đồng thời xây index và backfill để không làm cạn I/O, CPU, connection pool.
4. Theo dõi % tenant hoàn tất, số document chưa hợp lệ, thời gian query, số lỗi duplicate/validation, tiến độ index, độ trễ và lỗi retry.
5. Chặn pha contract nếu bất kỳ tenant trong đợt chưa đạt điều kiện; tenant lỗi phải có trạng thái, nguyên nhân và cách tiếp tục.

Rollback cần phân biệt **rollback ứng dụng** với **đảo ngược dữ liệu**. Sau khi đổi document từ `customer` sang `customerId` và bật validator v2, quay về app chỉ đọc v1 có thể gây lỗi ngay cả khi deployment được rollback. Vì vậy giữ code tương thích ngược đủ lâu; lập kế hoạch phục hồi bằng backup/restore và migration đảo chiều nếu thực sự khả thi, đồng thời đánh giá dữ liệu phát sinh trong thời gian chuyển đổi. Không tự động drop index/validator hàng loạt chỉ để ép rollback mà chưa đánh giá tác động.

## 11. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| Tenant A nhanh, tenant B chậm với cùng query | Index không được triển khai ở B; dữ liệu phân bố khác | Đối chiếu `getIndexes()`, `explain()` và kích thước collection theo tenant |
| `E11000 duplicate key error` khi tạo unique index | Đã có `orderNo` trùng hoặc null/thiếu nhiều lần | Kiểm kê và sửa dữ liệu trước, xác định lại unique scope |
| App ghi lỗi mã 121 sau nâng schema | Writer v1 hoặc field BSON sai kiểu | Kiểm tra validator, luồng writer, chuyển đổi định dạng và kế hoạch tương thích |
| Chạy lại `createIndex` báo conflict | Tên index trùng nhưng key/options khác | Viết migration đổi index có phiên bản; tạo mới/đối chiếu trước khi xóa cũ |
| Một số tenant có `schemaVersion=1` sau rollout | Migration bị bỏ sót, job lỗi hoặc vẫn còn writer cũ | Đối chiếu ledger từng tenant, backfill tiếp và kiểm tra ứng dụng |
| Query ở tenant sai database | Tenant context không được xác thực hoặc resolver sai mapping | Chọn tenant từ auth, registry allowlist và test phân tách |
| Backfill làm tăng latency toàn hệ thống | Batch quá lớn hoặc nhiều tenant chạy đồng thời | Giảm batch/concurrency, phân kỳ thời gian, theo dõi I/O và write load |
| Rollback app làm hỏng đọc ghi | Đã loại bỏ field/logic v1 quá sớm | Duy trì pha expand đủ lâu, kiểm thử rollback trên bản sao dữ liệu |

## 12. Checklist trước khi hoàn tất một tenant

- [ ] Tenant đã được xác thực; ánh xạ chính xác đến database và deployment dự kiến.
- [ ] Đã đo truy vấn thực tế; index phù hợp, unique scope đúng, không có dữ liệu trùng/thiếu trước khi tạo unique.
- [ ] Validator v2 được áp dụng trên đúng collection; toàn bộ document lịch sử được kiểm chứng.
- [ ] Đã triển khai code tương thích, backfill idempotent và xử lý ngoại lệ.
- [ ] Đã chuyển sang `strict + error` sau khi làm sạch dữ liệu; theo dõi lỗi ghi sau triển khai.
- [ ] Ledger, checkpoint, thời điểm chạy, số lượng document và trạng thái migration được lưu theo tenant.
- [ ] Đã thử isolation giữa các tenant, duplicate key, invalid schema, retry và kịch bản rollback.
- [ ] Đã đối chiếu `explain()` và metrics sau khi tạo index; công việc thay đổi diễn ra trong hạn mức tải cho phép.

**Ghi nhớ:** Trong MongoDB, index và validator thuộc về **collection trong một database cụ thể**, không thuộc về một class Java dùng chung cho toàn bộ tenant. Vì vậy ứng dụng Spring Data MongoDB phải định tuyến đúng database, còn quy trình migration phải triển khai, kiểm chứng và ghi nhận kết quả **riêng cho từng tenant**. Việc đọc/ghi dữ liệu qua `MongoTemplate` hay repository chỉ an toàn khi ranh giới tenant, schema và chỉ mục được quản lý thống nhất.

## Tài liệu tham khảo

- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html)
- [Spring Data MongoDB — MongoTemplate](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html)
- [MongoDB — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB — $jsonSchema](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/)
- [MongoDB — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB — collMod command](https://www.mongodb.com/docs/manual/reference/command/collMod/)
- [MongoDB — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)

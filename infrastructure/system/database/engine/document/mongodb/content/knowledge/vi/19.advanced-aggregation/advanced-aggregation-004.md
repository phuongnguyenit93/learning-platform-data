# Hợp nhất tập dữ liệu bằng $unionWith trong MongoDB

## 1. Bài toán: một kết quả từ nhiều nguồn document

Một ứng dụng quản lý đơn hàng lưu dữ liệu đang hoạt động ở collection `orders_current` và dữ liệu lịch sử ở `orders_archive`. Người dùng muốn xem **tất cả đơn hàng của mình trên cùng một trang**, không quan tâm bản ghi đang nằm ở collection nào. Hai collection có thể có cấu trúc khác nhau:

```javascript
// Collection orders_current
{
  _id: ObjectId("66a000000000000000000001"),
  tenantId: "TENANT-A",
  externalOrderId: "A-101",
  status: "PAID",
  createdAt: ISODate("2026-11-12T09:00:00Z"),
  totalCents: NumberLong("120000")
}

// Collection orders_archive: cấu trúc của hệ thống cũ
{
  _id: ObjectId("66a000000000000000000002"),
  clientTenant: "TENANT-A",
  reference: "A-099",
  legacyState: "PAID",
  dateText: "2026-10-15T08:00:00Z",
  amountText: "90000"
}
```

Một báo cáo lịch sử cần đọc từ cả hai collection, chuẩn hóa về các field chung như `externalOrderId`, `status`, `createdAt` và `amountCents`, rồi sắp xếp theo thời gian. Với aggregation framework, MongoDB cung cấp stage **`$unionWith`** cho kiểu hợp nhất này.

Các tình huống tương tự:

- Gộp các sự kiện từ `app_events` và `legacy_events` để tạo timeline.
- Tổng hợp giao dịch từ nhiều collection có cấu trúc gần nhau.
- Gộp kết quả hai nhánh lọc khác nhau rồi tính thống kê chung.
- Đọc song song dữ liệu hiện hành và lưu trữ trong giai đoạn migration.
- Hợp nhất dữ liệu từ ba hay nhiều collection cùng database thành một tập document cho pipeline tiếp theo.

Sau bài học, bạn sẽ hiểu cú pháp `$unionWith`, điểm khác biệt giữa **UNION ALL** và loại bỏ trùng, cách chuẩn hóa schema mỗi nguồn, cách lọc/sắp xếp/phân trang đúng sau khi hợp nhất, các giới hạn của stage và cách khảo sát hiệu năng bằng `explain()`.

## 2. `$unionWith` thực sự làm gì?

### 2.1. Hợp nhất hai luồng document

Một aggregation pipeline thường bắt đầu từ một collection và xử lý lần lượt các document:

```text
orders_current
      |
      v
    $match
      |
      v
   $project
      |
      +------------------------------+
      |                              |
      v                              v
 Luồng kết quả A               $unionWith
                                     |
                             orders_archive
                                     |
                              pipeline riêng
                                     |
                                     v
                               Luồng kết quả B
      |                              |
      +---------------+--------------+
                      |
                      v
              Luồng hợp nhất A + B
                      |
                 $sort / $group
                      |
                      v
                Kết quả đầu ra
```

Về mặt khái niệm, `$unionWith` lấy **các document đã đi tới stage này từ pipeline chính** và kết hợp với **kết quả của pipeline chạy trên collection chỉ định**. Các stage đặt sau nó xử lý luồng kết quả hợp nhất.

Không có một phép ghép hai document theo khóa ở bước này. Mỗi document từ mỗi nhánh vẫn là **một document riêng** trong đầu ra, trừ khi stage tiếp theo chủ động biến đổi hoặc gom nhóm.

### 2.2. Tương tự `UNION ALL` của SQL

Trong SQL, `UNION ALL` nối các hàng của hai tập kết quả và **giữ bản ghi lặp**. `$unionWith` có tính chất tương tự.

```sql
SELECT order_id, status, created_at FROM current_orders
UNION ALL
SELECT order_id, status, created_at FROM archive_orders;
```

Nhưng MongoDB làm việc với **document**, không phải bảng có các cột cố định. Hai nhánh có thể trả document với tên field và kiểu BSON khác nhau. `$unionWith` **không tự đổi tên field, ép kiểu hay căn chỉnh schema**.

| Câu hỏi | Hành vi của `$unionWith` |
| --- | --- |
| Có thể hợp nhất kết quả từ hai collection? | Có |
| Có thể đặt một pipeline riêng cho collection thứ hai? | Có |
| Có thể đặt nhiều stage `$unionWith` liên tiếp? | Có |
| Có loại bản ghi trùng tự động? | Không |
| Có tự ghép document cùng `_id` thành một document? | Không |
| Có đòi hai collection cùng schema? | Không |
| Có bảo đảm tài liệu từ nhánh nào được trả trước? | Không |
| Có tự ghi kết quả vào collection mới? | Không |

Đặc biệt, **thứ tự xuất hiện của các document sau union không được bảo đảm**. Nếu ứng dụng yêu cầu sắp xếp, phải có `$sort` trên kết quả hợp nhất.

### 2.3. Khác `$lookup` như thế nào?

Hai stage có mục đích hoàn toàn khác nhau:

```text
$unionWith: NỐI các luồng kết quả

Collection A --> doc A1
             --> doc A2  ----+
                             +--> [A1, A2, B1, B2]
Collection B --> doc B1  ----+
             --> doc B2

$lookup: GHÉP thông tin liên quan

Order A1 --customerId--> Customer C1
                   |
                   v
Order A1 + customer: [C1]
```

`$lookup` thực hiện một dạng **left outer join**, thường thêm một mảng các document liên quan vào từng document đầu vào. `$unionWith` không nối theo khóa; nó thêm những document của nhánh thứ hai vào tập kết quả.

Khi muốn hiển thị **một dòng cho mỗi giao dịch từ hai nguồn**, nghĩ đến `$unionWith`. Khi muốn hiển thị **đơn hàng kèm thông tin khách hàng**, nghĩ đến `$lookup`.

## 3. Cú pháp `$unionWith`

### 3.1. Dạng rút gọn: lấy toàn bộ document của collection thứ hai

```javascript
db.orders_current.aggregate([
  { $unionWith: "orders_archive" }
]);
```

Lệnh trả kết quả từ collection chính `orders_current` kết hợp với tất cả document trong `orders_archive`. Đây là cách viết đơn giản khi không cần lọc hay chỉnh schema của nhánh thứ hai.

### 3.2. Dạng đầy đủ: `coll` và `pipeline`

```javascript
db.orders_current.aggregate([
  {
    $match: { status: "PAID" }
  },
  {
    $unionWith: {
      coll: "orders_archive",
      pipeline: [
        { $match: { legacyState: "PAID" } },
        {
          $project: {
            _id: 0,
            externalOrderId: "$reference",
            status: "$legacyState"
          }
        }
      ]
    }
  }
]);
```

Ý nghĩa:

- `coll` là tên collection hoặc view dùng làm nguồn của nhánh union, thông thường nằm trong **cùng database** với collection chính.
- `pipeline` là các stage được thực hiện cho document của nguồn chỉ định ở `coll`.
- Những stage **trước** `$unionWith` chỉ xử lý dòng dữ liệu chính.
- Những stage **sau** `$unionWith` xử lý kết quả của **cả hai** nhánh.

Trong ví dụ, pipeline chính chỉ lọc `status` ở collection hiện hành. Collection lưu trữ được lọc bằng `legacyState` trong pipeline riêng. Tuy nhiên, nhánh chính vẫn còn nhiều field gốc vì chưa được `$project`; nếu muốn hai nhánh có đầu ra đồng nhất, cần chuẩn hóa cả hai như phần thực hành.

### 3.3. Trường hợp có nhiều nguồn

Có thể viết nhiều stage liên tiếp:

```javascript
db.app_events.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $unionWith: {
      coll: "legacy_events",
      pipeline: [
        { $match: { tenantId: "TENANT-A" } }
      ]
    }
  },
  {
    $unionWith: {
      coll: "imported_events",
      pipeline: [
        { $match: { tenantId: "TENANT-A" } }
      ]
    }
  },
  { $sort: { occurredAt: -1 } }
]);
```

Ví dụ này giả định ba collection có field `occurredAt` cùng là BSON Date. Nếu mỗi nguồn lưu kiểu khác nhau, cần chuẩn hóa field thời gian **trước khi sort chung**.

### 3.4. Hợp nhất với dữ liệu khai báo trực tiếp bằng `$documents`

Ở các phiên bản hỗ trợ `$documents` trong subpipeline, có thể bỏ `coll` **nếu** pipeline bắt đầu bằng `$documents`:

```javascript
db.app_events.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $unionWith: {
      pipeline: [
        {
          $documents: [
            {
              tenantId: "TENANT-A",
              type: "SYSTEM",
              message: "Bắt đầu chu kỳ đối soát"
            }
          ]
        }
      ]
    }
  }
]);
```

Nhánh này thêm một document không đến từ collection lưu trữ. Với MongoDB 8.0 trở lên, cơ chế xác thực namespace trong subpipeline yêu cầu dùng `coll` đúng khi pipeline thực sự bắt đầu từ collection, và **bỏ `coll`** khi pipeline bắt đầu bằng nguồn độc lập như `$documents`. Để tương thích với triển khai thực tế, luôn kiểm tra tính năng và cú pháp theo phiên bản server.

## 4. Chuẩn bị dữ liệu thực hành trong `mongosh`

Ví dụ bên dưới dùng database thử nghiệm `mongo_union_row203_lab` và hai collection riêng. Chỉ thao tác trên MongoDB mà bạn được phép ghi; không chèn/xóa dữ liệu trong collection nghiệp vụ thật.

Kết nối với `mongosh`, chẳng hạn trong môi trường local:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

Thay URI theo server, xác thực và TLS của môi trường thực hành. Trong `mongosh`:

```javascript
const lab = db.getSiblingDB("mongo_union_row203_lab");
const current = lab.getCollection("orders_current_demo");
const archive = lab.getCollection("orders_archive_demo");

// Mỗi lượt thực hành có một namespace dữ liệu riêng.
const runId = "row203-" + new ObjectId().toHexString();
const tenantId = runId;

print("database=" + lab.getName());
print("runId=" + runId);

current.insertMany([
  {
    runId,
    tenantId,
    externalOrderId: "A-101",
    status: "PAID",
    createdAt: ISODate("2026-11-12T09:00:00Z"),
    totalCents: NumberLong("120000")
  },
  {
    runId,
    tenantId,
    externalOrderId: "A-102",
    status: "NEW",
    createdAt: ISODate("2026-11-13T10:00:00Z"),
    totalCents: NumberLong("75000")
  },
  {
    runId,
    tenantId,
    externalOrderId: "A-103",
    status: "PAID",
    createdAt: ISODate("2026-11-14T02:00:00Z"),
    totalCents: NumberLong("200000")
  }
]);

archive.insertMany([
  {
    runId,
    clientTenant: tenantId,
    reference: "A-098",
    legacyState: "PAID",
    dateText: "2026-09-10T08:00:00Z",
    amountText: "55000"
  },
  {
    runId,
    clientTenant: tenantId,
    reference: "A-099",
    legacyState: "PAID",
    dateText: "2026-10-15T08:00:00Z",
    amountText: "90000"
  },
  {
    runId,
    clientTenant: tenantId,
    reference: "A-101",
    legacyState: "PAID",
    dateText: "2026-11-12T09:00:00Z",
    amountText: "120000"
  }
]);

print("current=" + current.countDocuments({ runId }));
print("archive=" + archive.countDocuments({ runId }));
```

Ta có:

- **3 document current** với `createdAt` là BSON Date và `totalCents` là BSON Int64.
- **3 document archive** với ngày và số tiền lưu dạng string.
- Mã nghiệp vụ `A-101` xuất hiện trong **cả hai collection**. Đây là trường hợp cố ý tạo trùng để minh họa.
- `runId` giúp dọn dữ liệu chính xác mà không ảnh hưởng các lượt thử nghiệm khác.

Đừng xóa các document chỉ dựa trên `externalOrderId` hoặc `reference` chung chung. Trong ứng dụng đa tenant, mã đơn có thể được tái sử dụng ở tenant khác.

## 5. Hợp nhất đơn giản và quan sát bản ghi trùng

### 5.1. Union không tự đồng nhất schema

```javascript
const rawUnion = current.aggregate([
  { $match: { runId } },
  {
    $unionWith: {
      coll: "orders_archive_demo",
      pipeline: [
        { $match: { runId } }
      ]
    }
  }
]).toArray();

print("rawCount=" + rawUnion.length);
printjson(rawUnion);
```

Với dữ liệu mẫu, `rawCount` bằng **6**. Chúng ta có ba document current và ba document archive. Kết quả gồm **hai kiểu cấu trúc khác nhau** vì chưa có bước chuẩn hóa.

Hai bản ghi `A-101` vẫn là hai document riêng. `$unionWith` không so sánh business key, không kiểm `_id` trùng và không tự gộp record giống nhau.

### 5.2. Vì sao không thể giả định thứ tự “current trước, archive sau”?

Mặc dù pipeline bắt đầu từ `current`, tài liệu MongoDB quy định **thứ tự đầu ra sau `$unionWith` không được bảo đảm**. Không viết ứng dụng với giả định:

```text
3 document đầu  = current
3 document sau  = archive
```

Nếu muốn biết nguồn, hãy thêm **trường đánh dấu nguồn** như `origin: "current"` và `origin: "archive"` trong từng nhánh. Nếu muốn thứ tự ngày mới nhất, hãy thêm `$sort` trên kết quả sau khi chuẩn hóa.

### 5.3. Hợp nhất một collection với chính nó

```javascript
const twice = current.aggregate([
  { $match: { runId } },
  {
    $unionWith: {
      coll: "orders_current_demo",
      pipeline: [
        { $match: { runId } }
      ]
    }
  }
]).toArray();

print("count=" + twice.length);
```

Kết quả dự kiến cũng bằng **6** vì mỗi document của `current` được đưa vào hai nhánh. Đây là cách quan sát trực tiếp tính chất **UNION ALL**: kể cả hai nhánh đọc cùng một collection và trả cùng document, MongoDB vẫn không tự loại bản ghi lặp.

## 6. Chuẩn hóa document trước khi hợp nhất

### 6.1. Mục tiêu: một contract chung cho kết quả

Hai collection có cấu trúc lưu trữ khác nhau, nhưng API mong nhận một document thống nhất:

```javascript
{
  sourceId: ObjectId("..."),
  tenantId: "row203-...",
  externalOrderId: "A-101",
  status: "PAID",
  createdAt: ISODate("2026-11-12T09:00:00Z"),
  amountCents: NumberLong("120000"),
  origin: "current",
  originPriority: 2
}
```

Các nguyên tắc:

1. **Tên field giống nhau**: `reference` của archive đổi thành `externalOrderId`; `legacyState` đổi thành `status`.
2. **Kiểu BSON thống nhất**: `dateText` parse thành Date, `amountText` chuyển sang Long.
3. **Giữ nguồn gốc**: `origin` cho biết bản ghi đến từ collection nào.
4. **Không dựa vào `_id` làm khóa trùng toàn hệ thống**: document ở hai collection có thể có `_id` khác nhau dù biểu diễn cùng một đơn.
5. **Tách nguyên tắc ưu tiên**: `originPriority` là field tạm dùng khi chọn một record giữa các bản sao.

### 6.2. Dựng pipeline hợp nhất chuẩn hóa

Trong cùng phiên `mongosh` có `runId` và `tenantId` đã khai báo, tạo mảng pipeline có thể dùng lại:

```javascript
const normalizedUnion = [
  // Nhánh 1: các đơn đang hoạt động.
  {
    $match: { runId, tenantId }
  },
  {
    $project: {
      _id: 0,
      sourceId: "$_id",
      tenantId: "$tenantId",
      externalOrderId: "$externalOrderId",
      status: "$status",
      createdAt: "$createdAt",
      amountCents: "$totalCents",
      origin: { $literal: "current" },
      originPriority: { $literal: 2 }
    }
  },
  // Nhánh 2: các đơn lưu trữ của hệ thống cũ.
  {
    $unionWith: {
      coll: "orders_archive_demo",
      pipeline: [
        {
          $match: {
            runId,
            clientTenant: tenantId
          }
        },
        {
          $project: {
            _id: 0,
            sourceId: "$_id",
            tenantId: "$clientTenant",
            externalOrderId: "$reference",
            status: "$legacyState",
            createdAt: {
              $dateFromString: {
                dateString: "$dateText",
                onError: null,
                onNull: null
              }
            },
            amountCents: {
              $convert: {
                input: "$amountText",
                to: "long",
                onError: null,
                onNull: null
              }
            },
            origin: { $literal: "archive" },
            originPriority: { $literal: 1 }
          }
        }
      ]
    }
  }
];

printjson(current.aggregate(normalizedUnion).toArray());
```

Ở đây:

- `$project` trên **nhánh chính** tạo cùng tên field với `$project` trong subpipeline.
- `$dateFromString` parse chuỗi ISO 8601 có `Z` thành BSON Date. `onError: null` tránh làm toàn pipeline dừng khi dữ liệu cũ chứa chuỗi ngày không hợp lệ; cần quan sát những giá trị được chuyển thành null.
- `$convert` với `to: "long"` chuyển chuỗi số nguyên sang BSON Int64; `onError`/`onNull` trả null khi không chuyển đổi được.
- `$literal` làm rõ `origin` và `originPriority` là **hằng số**, không phải đường dẫn field.
- `_id: 0` không giữ `_id` gốc ở top-level; thay vào đó `sourceId: "$_id"` giữ ID của document nguồn.

Khi dữ liệu cũ sai kiểu, việc “chuyển thành null” có thể tiện cho báo cáo nhưng cũng có thể che lỗi chất lượng. Trong hệ thống thật nên thống kê số record lỗi hoặc đưa vào kênh kiểm tra riêng; không cộng tiền mặc định bằng 0 khi chưa có chính sách nghiệp vụ rõ ràng.

### 6.3. Sort sau khi hai nhánh đã cùng kiểu dữ liệu

```javascript
const sorted = current.aggregate([
  ...normalizedUnion,
  {
    $sort: {
      createdAt: -1,
      externalOrderId: 1,
      origin: 1,
      sourceId: 1
    }
  },
  {
    $project: {
      originPriority: 0
    }
  }
]).toArray();

printjson(sorted);
```

`createdAt` bây giờ là BSON Date trên cả hai nhánh nên có thể so sánh theo **thời điểm**, không dựa vào thứ tự chữ của chuỗi ngày. Các trường bổ sung trong `$sort` tạo thứ tự ổn định khi nhiều record có cùng timestamp.

**Đừng chỉ sort trước `$unionWith` rồi kỳ vọng kết quả cuối cùng vẫn được sắp xếp toàn cục.** Muốn sắp xếp tập hợp nhất, hãy đặt `$sort` phù hợp **sau** union.

## 7. Xử lý dữ liệu trùng: union không đồng nghĩa deduplication

### 7.1. Trùng document và trùng nghiệp vụ là hai khái niệm

Có ít nhất ba khái niệm “trùng”:

1. **Cùng document nguồn** được đưa vào pipeline hai lần, chẳng hạn union một collection với chính nó.
2. **Cùng `_id`** nhưng ở hai collection khác nhau.
3. **Cùng khóa nghiệp vụ**, chẳng hạn `(tenantId, externalOrderId)`, dù `_id` và vài field khác nhau.

MongoDB không quyết định giúp bạn khái niệm nào là đúng. Nếu API hiển thị mỗi đơn hàng một lần, thì phải định nghĩa khóa từ nghiệp vụ; ví dụ:

```text
unique business key = (tenantId, externalOrderId)
```

Với dữ liệu mẫu, 6 document được union nhưng chỉ có **5 khóa đơn hàng** vì `A-101` xuất hiện ở cả current và archive.

### 7.2. Đếm số khóa nghiệp vụ khác nhau

```javascript
const distinctCounts = current.aggregate([
  ...normalizedUnion,
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      }
    }
  },
  { $count: "distinctOrders" }
]).toArray();

printjson(distinctCounts);
```

Kết quả dự kiến:

```javascript
[{ distinctOrders: 5 }]
```

`$group` với khóa ghép tạo một nhóm cho mỗi cặp, rồi `$count` đếm số nhóm. Nó khác `$count` trực tiếp sau union, vốn sẽ đếm tất cả 6 document, bao gồm bản sao.

### 7.3. Giữ một bản ghi theo chính sách ưu tiên nguồn

Nếu mỗi khóa chỉ được xuất hiện một lần trong API, cần quyết định giữ bản nào. Trong ví dụ này, **current được ưu tiên hơn archive** khi cả hai chứa cùng mã đơn. Ta dùng `originPriority: 2` cho current và `1` cho archive.

```javascript
const deduplicated = current.aggregate([
  ...normalizedUnion,
  {
    $sort: {
      tenantId: 1,
      externalOrderId: 1,
      originPriority: -1,
      createdAt: -1,
      sourceId: 1
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      chosen: { $first: "$$ROOT" },
      duplicateCount: { $sum: 1 }
    }
  },
  {
    $replaceWith: {
      $mergeObjects: [
        "$chosen",
        { duplicateCount: "$duplicateCount" }
      ]
    }
  },
  { $project: { originPriority: 0 } },
  {
    $sort: {
      createdAt: -1,
      externalOrderId: 1,
      sourceId: 1
    }
  }
]).toArray();

printjson(deduplicated);
```

Giải thích:

1. `$sort` sắp theo business key, rồi đặt bản current ở trước archive trong cùng một nhóm. Với cùng nguồn, `createdAt` và `sourceId` làm tiêu chí tiếp theo.
2. `$group` gom theo khóa nghiệp vụ, chọn document đầu nhóm bằng `$first: "$$ROOT"` và đếm số record cùng key.
3. `$replaceWith` và `$mergeObjects` trả root về document đã chọn, kèm `duplicateCount` để quan sát.
4. `$project` bỏ field kỹ thuật `originPriority` nếu API không cần.
5. `$sort` cuối sắp xếp **danh sách đơn hàng đã loại trùng** theo thời gian.

Với dữ liệu mẫu, `A-101` được chọn từ `current`; `duplicateCount: 2` cho biết có hai record biểu diễn cùng một khóa.

**Cảnh báo về dữ liệu:** “current được ưu tiên” là **quy tắc của ví dụ**, không phải quy tắc MongoDB. Một hệ thống thực tế có thể cần chọn event có `version` lớn nhất, chọn trạng thái từ nguồn đáng tin hơn hoặc giữ cả lịch sử thay đổi. Không dùng `$first` không kèm định nghĩa thứ tự để quyết định bản ghi “đúng”.

### 7.4. Chỉ dùng `$group` có đủ không?

Đoạn sau loại trùng về **giá trị khóa**:

```javascript
current.aggregate([
  ...normalizedUnion,
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      }
    }
  }
]);
```

Nhưng nó **không giữ các field** `status`, `createdAt` hoặc `amountCents`. Nếu mục tiêu chỉ là danh sách ID khác nhau, như vậy có thể đủ. Nếu cần một document đầy đủ, phải định nghĩa cách chọn hoặc gộp dữ liệu.

Ngoài ra, `$group: {_id:"$_id"}` có thể cho kết quả sai nghiệp vụ nếu cùng đơn nằm ở hai collection với hai `_id` khác nhau. Đúng khóa ở đây là **tenant + external order ID**.

### 7.5. Trùng có thể là tín hiệu cần điều tra

Không phải lúc nào cũng nên xóa trùng một cách âm thầm. Nếu `A-101` ở current có `amountCents: 120000` nhưng ở archive lại có `amountText: "125000"`, hai bản ghi cùng key nhưng khác tiền.

Ta có thể lập báo cáo nghi vấn:

```javascript
current.aggregate([
  ...normalizedUnion,
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      count: { $sum: 1 },
      amounts: { $addToSet: "$amountCents" },
      origins: { $addToSet: "$origin" }
    }
  },
  { $match: { count: { $gt: 1 } } }
]);
```

Kết quả cho biết khóa nào được lặp và có những giá trị số tiền nào. Với dữ liệu lớn, `$addToSet` trên nhiều trường có thể tốn bộ nhớ; hãy chọn trường cần so sánh và giới hạn báo cáo theo mục tiêu. Một bản ghi trùng không nhất thiết là lỗi: có thể do giai đoạn migration giữ đồng thời bản current và archive có chủ đích.

## 8. Lọc và phân trang kết quả sau union

### 8.1. Lọc trong từng nhánh để giảm dữ liệu đầu vào

Trong `normalizedUnion`, mỗi nhánh đã lọc theo `runId` và tenant của nó. Đây là bước quan trọng: thay vì đưa mọi document của hai collection qua pipeline rồi mới lọc, ta giảm lượng dữ liệu ngay từ từng nguồn khi có thể.

```javascript
// Điều kiện chỉ áp dụng cho current khi đặt trước $unionWith.
{
  $match: {
    runId,
    tenantId,
    status: "PAID"
  }
}

// Điều kiện cho archive phải ở subpipeline riêng:
{
  $match: {
    runId,
    clientTenant: tenantId,
    legacyState: "PAID"
  }
}
```

Nếu chỉ thêm `$match: {status:"PAID"}` vào nhánh chính mà không lọc nhánh archive, các bản ghi archive có thể chứa trạng thái khác. Ngược lại, nếu muốn lọc chung sau khi đã chuẩn hóa:

```javascript
current.aggregate([
  ...normalizedUnion,
  { $match: { status: "PAID" } },
  { $sort: { createdAt: -1, externalOrderId: 1 } }
]);
```

`$match` sau union có cùng tên field trên cả hai nhánh, dễ viết và bảo đảm logic chung. Tuy nhiên, nó có thể khiến database xử lý nhiều document trước khi lọc hơn. Một thiết kế tốt có thể **đẩy điều kiện tương đương xuống hai nhánh** và vẫn giữ một filter chung nếu cần bảo vệ hợp đồng đầu ra.

### 8.2. Lọc theo khoảng thời gian

Sau khi chuẩn hóa `createdAt` thành Date:

```javascript
const start = ISODate("2026-11-01T00:00:00Z");
const end = ISODate("2026-12-01T00:00:00Z");

current.aggregate([
  ...normalizedUnion,
  {
    $match: {
      createdAt: { $gte: start, $lt: end }
    }
  },
  { $sort: { createdAt: -1, externalOrderId: 1 } }
]);
```

Khoảng nửa mở `[start, end)` tránh bỏ sót phần mili giây ở cuối kỳ và không đếm trùng khi chia kỳ liên tiếp. Đây là khoảng **UTC**; nếu báo cáo theo ngày Việt Nam hoặc múi giờ khác, phải chuyển **ranh giới ngày địa phương** sang các instant UTC phù hợp trước khi truy vấn.

Trên nhánh archive, việc parse `dateText` thành Date ngay trong pipeline có thể tốn tài nguyên và hạn chế khả năng lọc bằng index thời gian. Nếu dữ liệu legacy thường xuyên được báo cáo theo ngày, nên cân nhắc migration sang BSON Date hoặc thêm trường chuẩn hóa phục vụ query.

### 8.3. `$sort`, `$skip` và `$limit` phải xét trên tập hợp nhất

Để hiển thị trang thứ hai với kích thước 2:

```javascript
const page = 2;
const pageSize = 2;

current.aggregate([
  ...normalizedUnion,
  {
    $sort: {
      createdAt: -1,
      externalOrderId: 1,
      origin: 1,
      sourceId: 1
    }
  },
  { $skip: (page - 1) * pageSize },
  { $limit: pageSize }
]);
```

Lưu ý:

- Phân trang **sau union** là phân trang trên kết quả từ cả hai nguồn, không phải một trang từ current cộng một trang từ archive.
- Sort cần xác định, đặc biệt khi nhiều document có cùng timestamp. Dùng các trường phụ như `externalOrderId`, `origin`, `sourceId` để tạo thứ tự ổn định.
- Nếu API muốn **mỗi đơn một lần**, cần **dedup trước khi skip/limit**. Nếu phân trang trên dữ liệu còn trùng, một order có thể xuất hiện ở nhiều trang hoặc đếm sai tổng số đơn.
- Nếu dữ liệu liên tục thay đổi, offset pagination bằng `$skip` có thể dẫn tới phần tử dịch trang; với khối lượng lớn, cân nhắc cursor/keyset pagination theo khóa sort ổn định cùng một chính sách consistency.

### 8.4. Đếm đúng tổng số

```javascript
// Tổng số document sau union: đếm cả bản trùng.
printjson(
  current.aggregate([
    ...normalizedUnion,
    { $count: "rowsIncludingDuplicates" }
  ]).toArray()
);

// Tổng số khóa đơn hàng khác nhau: không đếm trùng nghiệp vụ.
printjson(
  current.aggregate([
    ...normalizedUnion,
    {
      $group: {
        _id: {
          tenantId: "$tenantId",
          externalOrderId: "$externalOrderId"
        }
      }
    },
    { $count: "distinctOrders" }
  ]).toArray()
);
```

Với dữ liệu mẫu, hai giá trị là **6** và **5**. Đó là hai câu trả lời cho **hai câu hỏi khác nhau**, không phải mâu thuẫn.

## 9. Thống kê sau khi hợp nhất

### 9.1. Tổng hợp theo trạng thái

Nếu muốn số document của từng trạng thái (chấp nhận giữ bản sao từ nhiều nguồn):

```javascript
current.aggregate([
  ...normalizedUnion,
  {
    $group: {
      _id: "$status",
      documents: { $sum: 1 },
      amountCents: { $sum: "$amountCents" }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Ví dụ này có thể **cộng đôi tiền** của `A-101` vì đơn xuất hiện ở current và archive. Nó chỉ đúng nếu ý nghĩa nghiệp vụ thực sự là “thống kê mọi bản ghi của mọi nguồn”.

Nếu muốn **tổng doanh thu theo đơn hàng duy nhất**, hãy dedup theo business key **trước** `$group` theo trạng thái:

```javascript
current.aggregate([
  ...normalizedUnion,
  {
    $sort: {
      tenantId: 1,
      externalOrderId: 1,
      originPriority: -1,
      createdAt: -1,
      sourceId: 1
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      chosen: { $first: "$$ROOT" }
    }
  },
  { $replaceWith: "$chosen" },
  {
    $group: {
      _id: "$status",
      uniqueOrders: { $sum: 1 },
      amountCents: { $sum: "$amountCents" }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Trong hệ thống tài chính, phải xác định rõ **bản ghi nào là nguồn sự thật**. Một trường hợp trùng nhưng dữ liệu mâu thuẫn không nên được tự động phân xử bằng “bản mới nhất” nếu quy trình kế toán yêu cầu xác nhận phiên bản, trạng thái hoặc nguồn phát sinh.

### 9.2. Thống kê theo nguồn

Để biết tỷ trọng dữ liệu mỗi collection đóng góp:

```javascript
current.aggregate([
  ...normalizedUnion,
  {
    $group: {
      _id: "$origin",
      documents: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Field `origin` được thêm trong từng `$project` trước union, giúp theo dõi dòng dữ liệu. Việc giữ provenance hữu ích cho quan sát, debug, migration và truy vết lỗi định dạng.

## 10. Dùng lại một collection ở nhiều nhánh

`$unionWith` không bắt buộc đọc một collection khác. Có thể chia một collection thành hai nhánh xử lý độc lập rồi hợp nhất.

Ví dụ tìm các đơn `NEW` và các đơn có tổng tiền lớn hơn 100000, đồng thời gắn lý do khớp:

```javascript
current.aggregate([
  {
    $match: {
      runId,
      status: "NEW"
    }
  },
  {
    $project: {
      _id: 1,
      externalOrderId: 1,
      reason: { $literal: "NEW_STATUS" }
    }
  },
  {
    $unionWith: {
      coll: "orders_current_demo",
      pipeline: [
        {
          $match: {
            runId,
            totalCents: { $gt: NumberLong("100000") }
          }
        },
        {
          $project: {
            _id: 1,
            externalOrderId: 1,
            reason: { $literal: "HIGH_AMOUNT" }
          }
        }
      ]
    }
  }
]);
```

Nếu một order vừa `NEW` vừa có số tiền lớn, nó xuất hiện **hai lần với hai giá trị reason**, bởi hai nhánh độc lập đều trả nó. Đó có thể là điều mong muốn khi tạo danh sách “lý do cảnh báo”; nếu mục tiêu là danh sách **đơn hàng** duy nhất, cần nhóm theo ID và có thể dùng `$addToSet` để giữ nhiều lý do:

```javascript
// Áp dụng sau hai nhánh ở ví dụ trên:
{
  $group: {
    _id: "$_id",
    externalOrderId: { $first: "$externalOrderId" },
    reasons: { $addToSet: "$reason" }
  }
}
```

Trong trường hợp chỉ cần điều kiện logic `NEW OR totalCents > 100000`, một `$match` với `$or` có thể đơn giản và hiệu quả hơn. Chỉ dùng `$unionWith` khi các nhánh thực sự cần pipeline riêng, nguồn riêng hoặc cách xử lý độc lập.

## 11. Giới hạn và điểm cần lưu ý của `$unionWith`

### 11.1. Không dùng trong transaction

Theo tài liệu MongoDB, một aggregation pipeline có `$unionWith` **không được dùng bên trong transaction**. Không thiết kế quy trình “mở transaction rồi chạy `$unionWith` để có bản báo cáo nguyên tử” theo cách đó.

Nếu báo cáo cần mức nhất quán cụ thể khi dữ liệu đang thay đổi, hãy đánh giá read concern, snapshot/read semantics được triển khai hỗ trợ, chiến lược materialization hoặc kiến trúc dữ liệu thích hợp. **Mặc định một union đọc từ hai collection không phải là cam kết nghiệp vụ rằng mọi bản ghi thuộc cùng một snapshot giao dịch.**

### 11.2. Không có `$out` hoặc `$merge` bên trong union subpipeline

`pipeline` lồng trong `$unionWith` **không được chứa** stage `$out` hoặc `$merge`. Những stage này phục vụ ghi kết quả aggregation, không phải bước xử lý của nhánh union.

```javascript
// Không hợp lệ: $merge nằm bên trong pipeline của $unionWith.
{
  $unionWith: {
    coll: "orders_archive_demo",
    pipeline: [
      { $match: { status: "PAID" } },
      { $merge: "some_report_collection" }
    ]
  }
}
```

Nếu muốn materialize **kết quả tổng hợp cuối cùng**, có thể cân nhắc đặt `$merge` hoặc `$out` ở **cuối pipeline ngoài**, nếu phiên bản, topology, quyền và ngữ nghĩa ghi hỗ trợ. Đây là một tác vụ ghi dữ liệu khác với `$unionWith` chỉ kết hợp luồng kết quả; phải kiểm soát việc ghi đè, khóa unique và chạy lại để tránh lặp.

### 11.3. Collation trên nhiều nguồn

Collation quyết định cách so sánh và sắp xếp string. Với `$unionWith`:

- Nếu lệnh `aggregate()` chỉ định `collation`, toàn bộ operation dùng collation đó.
- Nếu không chỉ định, operation kế thừa collation của collection/view chính.
- Collation mặc định của **collection** được union không tự áp dụng thay thế collation của pipeline chính.
- Nếu nguồn union là **view**, collation của view phải tương thích theo yêu cầu của MongoDB; view có collation khác collection/view chính có thể khiến lệnh lỗi.

Ví dụ chỉ định collation cho operation:

```javascript
current.aggregate(
  [
    ...normalizedUnion,
    { $sort: { externalOrderId: 1 } }
  ],
  {
    collation: { locale: "vi", strength: 2 }
  }
);
```

Collation còn ảnh hưởng đến `$group` khi khóa nhóm là string. Nếu phân biệt case hoặc dấu là phần của business key, cần xác định chính sách so sánh rõ ràng; không chọn collation tiện cho hiển thị rồi vô tình coi hai mã kỹ thuật khác nhau là cùng khóa.

### 11.4. MongoDB Search trong union subpipeline

Trong những triển khai có MongoDB Search và phiên bản hỗ trợ, `$unionWith` có thể có `$search` hoặc `$searchMeta` ở **đầu subpipeline** theo quy tắc tài liệu. Đây là cơ chế nâng cao, phụ thuộc vào tính năng Search và index chuyên dụng, không giống một `$match` B-tree thông thường.

Không đưa `$search` vào giữa subpipeline tùy ý hoặc kỳ vọng `mongod` local không cấu hình Search chạy được ví dụ đó.

### 11.5. Namespace và phiên bản triển khai

`coll` thường chỉ định tên collection/view cùng database. Không nên coi `"otherDatabase.collection"` là một cú pháp chuẩn để union tự động sang database khác; cần xem cơ chế hỗ trợ của phiên bản cụ thể hoặc thiết kế ETL/materialized collection khi thật sự cần dữ liệu xuyên database.

MongoDB có những thay đổi về xác thực namespace của `$unionWith` subpipeline từ phiên bản 8.0; khi dùng `$documents` thay vì collection, không chỉ định `coll`. Với stage bắt đầu từ collection, khai báo `coll` rõ ràng.

Các giới hạn có thể thay đổi theo phiên bản server, topology, loại collection/view và các stage lồng nhau. Đối với triển khai production, kiểm tra tài liệu MongoDB **ứng với phiên bản đang vận hành** trước khi dựa vào tổ hợp nhiều tính năng nâng cao.

## 12. Hiệu năng và index cho từng nhánh

### 12.1. Chi phí union phụ thuộc cả hai nguồn

Một pipeline union phải xử lý document được các nhánh đưa vào. Nếu current có một triệu bản ghi và archive có mười triệu bản ghi, một pipeline không lọc, chuẩn hóa hàng triệu document rồi `$sort` toàn bộ có thể tốn nhiều CPU, I/O, RAM và thời gian.

Không nên kỳ vọng `$unionWith` làm dữ liệu nhỏ đi hoặc tự lọc trùng. Các stage như `$sort` và `$group` trên tập kết quả lớn có thể là thành phần chi phí đáng kể.

### 12.2. Đặt `$match` có thể dùng index ở từng collection

Với query pattern của ví dụ:

```javascript
// Index trên nhánh current.
current.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "tenant_createdAt" }
);

// Index trên nhánh archive.
archive.createIndex(
  { clientTenant: 1 },
  { name: "clientTenant" }
);
```

Hai index phục vụ các filter ở **hai collection khác nhau**. Index của current không thể được dùng để tìm document trong archive. Ngược lại, nếu nhánh archive lọc `clientTenant`, cần index ở chính archive.

Một index trên chuỗi `dateText` không tương đương index thời gian trên BSON Date sau `$dateFromString`. Việc parse dữ liệu trong aggregation có thể khiến query khó tận dụng range scan theo giá trị thời gian. Nếu báo cáo cần chạy thường xuyên, hãy cân nhắc chuyển dữ liệu cũ sang Date hoặc tạo một cấu trúc chuẩn hóa có index thích hợp.

### 12.3. Lọc sớm, nhưng giữ đúng ngữ nghĩa

Ví dụ cần đơn hàng của tenant T và khoảng ngày tháng 11:

- Nhánh current có thể `$match` trực tiếp trên `tenantId` và `createdAt` nếu đã index.
- Nhánh archive có thể `$match` theo `clientTenant` trước khi parse; nếu có field ngày chuẩn hóa thì dùng tiếp range.
- Cuối cùng giữ một `$match` theo `createdAt` chuẩn hóa nếu muốn thực thi cùng ranh giới cho hai nguồn.

Không đẩy một điều kiện vào nhánh nguồn theo cách làm **thay đổi ý nghĩa**. Chẳng hạn dữ liệu legacy có chuỗi ngày thiếu timezone; so sánh string thẳng có thể cho kết quả khác với Date. Tối ưu hóa chỉ hợp lệ khi semantics tương đương.

### 12.4. Theo dõi với `explain("executionStats")`

```javascript
printjson(
  current.explain("executionStats").aggregate([
    ...normalizedUnion,
    { $sort: { createdAt: -1 } }
  ])
);
```

Kế hoạch và cách biểu diễn có thể khác nhau giữa các phiên bản MongoDB/engine. Khi quan sát, tìm:

- `COLLSCAN` và `IXSCAN` ở các nguồn;
- index nào được dùng tại nhánh chính và nhánh union;
- số khóa/document được quét nếu kế hoạch hiển thị;
- các bước sort/group tốn tài nguyên;
- số document phải xử lý trước và sau khi lọc.

Đừng khẳng định query nhanh chỉ vì đầu ra có ít document. Một phép union có thể trả 20 record nhưng vẫn quét hàng triệu document nếu điều kiện/index không phù hợp.

Với tập dữ liệu demo chỉ có 6 document, optimizer có thể chọn collection scan vì chi phí thấp hơn; không dùng kết quả nhỏ này để kết luận tốc độ production.

### 12.5. Chỉ tạo các index đáng giá

Mỗi index tốn disk/cache và chi phí ghi. Không tạo mọi index có thể tưởng tượng được cho mỗi nhánh union. Bắt đầu từ workload:

1. API thường lọc theo tenant, status hay khoảng ngày?
2. Có thường cần phân trang mới nhất không?
3. Dữ liệu archive có được đọc thường xuyên hay chỉ trong báo cáo tháng?
4. Có thể materialize một tập dữ liệu hợp nhất cho báo cáo nặng không?
5. `explain()` và đo tải thực tế có cho thấy index mới cải thiện rõ không?

Việc tách collection current/archive có thể hữu ích cho vòng đời dữ liệu, nhưng một màn hình cần đọc cả hai phải trả thêm chi phí union và chuẩn hóa so với một collection đã có schema thống nhất.

## 13. Khi nào nên dùng `$unionWith` và khi nào không?

| Mục tiêu | Công cụ thường phù hợp | Lý do |
| --- | --- | --- |
| Gộp record từ hai collection thành một danh sách | `$unionWith` | Nối hai luồng document |
| Gộp record cùng collection từ hai nhánh xử lý | `$unionWith` hoặc `$match $or` | Chọn theo mức độ khác nhau của mỗi nhánh |
| Ghép order với dữ liệu customer theo `customerId` | `$lookup` | Join theo quan hệ |
| Chỉnh/đổi tên vài field | `$project`, `$set`, `$replaceWith` | Chuẩn hóa hình dạng |
| Loại duplicate theo business key sau union | `$group` và chính sách chọn record | `$unionWith` không loại trùng |
| Tính doanh thu của cả hai nguồn | `$unionWith` rồi `$group` | Tính trên luồng hợp nhất; chú ý trùng nghiệp vụ |
| Tạo collection báo cáo lưu bền vững | `$merge` hoặc `$out` sau pipeline phù hợp | Stage ghi dữ liệu riêng |
| Sao chép dữ liệu xuyên dịch vụ/database không cùng phạm vi union | ETL/streaming/đồng bộ theo thiết kế | Không mặc định `$unionWith` giải quyết truy cập xuyên hệ thống |
| Bảo đảm ràng buộc unique khi ghi dữ liệu | Unique index và xử lý cạnh tranh | `$unionWith` chỉ là phép đọc/biến đổi, không chống trùng lúc insert |

Một điểm thường bị nhầm: **dedup khi đọc** chỉ làm kết quả hiển thị gọn hơn. Nó không xóa document trùng đang lưu và không thay thế unique index hoặc logic nhập liệu để bảo vệ dữ liệu ngay tại điểm ghi.

## 14. Các lỗi thiết kế và cách tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nghĩ `$unionWith` tương đương SQL `UNION` loại trùng | Đếm doanh thu/đơn hàng hai lần | Hiểu là **UNION ALL**; dùng `$group` khi cần |
| Nghĩ hai collection phải cùng schema | Viết query quá phức tạp hoặc bỏ qua stage hữu ích | Dùng `$project`/`$convert`/`$dateFromString` để chuẩn hóa |
| Không chuẩn hóa field trước `$sort` | Date và string được so sánh khác semantics | Quy về cùng kiểu BSON |
| Dùng `_id` để loại trùng dữ liệu giữa collection | Cùng đơn có thể có hai `_id` khác nhau | Nhóm theo khóa nghiệp vụ đầy đủ |
| Dùng `$first` nhưng không sắp xếp | Chọn record không ổn định | Xác định ưu tiên, sort và tie-breaker |
| Sort trong từng nhánh rồi không sort sau union | Thứ tự cuối không được bảo đảm | `$sort` sau union |
| `$limit` trên từng nhánh khi cần page tổng | Có thể bỏ sót record cần hiển thị | Tính trang trên tập hợp nhất |
| Dedup sau khi `$skip/$limit` | Bản sao chiếm chỗ trong trang | Dedup trước phân trang |
| Chỉ filter theo tenant ở nhánh chính | Đọc cả archive của tenant khác | `$match` riêng từng nhánh hoặc filter sau chuẩn hóa |
| Dùng `$dateFromString` không xử lý legacy input xấu | Một ngày lỗi có thể làm pipeline thất bại | `onError`, quan sát và sửa dữ liệu nguồn |
| Dùng `$convert` thành null rồi âm thầm cộng 0 | Che sai lệch số tiền | Báo lỗi dữ liệu, xác định quy tắc bỏ qua/đối soát |
| Giả định có một collation riêng cho mỗi nhánh | Group/sort cho kết quả không như ý | Hiểu collation cấp operation và view |
| Dùng `$unionWith` trong transaction | Lệnh không được hỗ trợ | Thiết kế read semantics và kiến trúc khác |
| Đặt `$merge`/`$out` trong subpipeline union | Vi phạm giới hạn stage | Chỉ cân nhắc ghi ở outer pipeline khi hợp lệ |
| Gộp dữ liệu từ nhiều nguồn nhưng không giữ provenance | Khó debug hoặc điều tra bản sao | Thêm `origin` và `sourceId` |
| Không xem index ở collection union | Subpipeline phải quét lượng dữ liệu lớn | Thiết kế index cho **mỗi nguồn** |

## 15. Bài thực hành tổng hợp

### 15.1. Bài A: timeline mới nhất của cả hai nguồn

Yêu cầu: trả tất cả record, kể cả bản sao, theo thời gian giảm dần và giữ tên nguồn.

```javascript
current.aggregate([
  ...normalizedUnion,
  { $sort: { createdAt: -1, externalOrderId: 1, sourceId: 1 } },
  {
    $project: {
      _id: 0,
      externalOrderId: 1,
      status: 1,
      createdAt: 1,
      origin: 1,
      amountCents: 1
    }
  }
]);
```

Hỏi: Vì sao `A-101` có thể xuất hiện hai lần? Tại sao phải sort sau union?

### 15.2. Bài B: thống kê doanh thu của các đơn duy nhất

Yêu cầu: mỗi `tenantId + externalOrderId` được tính một lần; khi trùng ưu tiên current.

```javascript
current.aggregate([
  ...normalizedUnion,
  {
    $sort: {
      tenantId: 1,
      externalOrderId: 1,
      originPriority: -1,
      createdAt: -1,
      sourceId: 1
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      chosen: { $first: "$$ROOT" }
    }
  },
  { $replaceWith: "$chosen" },
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: null,
      paidOrders: { $sum: 1 },
      paidAmountCents: { $sum: "$amountCents" }
    }
  }
]);
```

Hỏi: Nếu bỏ bước dedup, tổng doanh thu sẽ sai theo hướng nào? Nếu archive có số tiền khác current, chính sách ưu tiên đã được đặt ở đâu?

### 15.3. Bài C: phát hiện thiếu dữ liệu trong nhánh legacy

Yêu cầu: quan sát những document archive không parse được ngày hoặc số tiền:

```javascript
current.aggregate([
  ...normalizedUnion,
  { $match: { origin: "archive" } },
  {
    $match: {
      $or: [
        { createdAt: null },
        { amountCents: null }
      ]
    }
  },
  {
    $project: {
      tenantId: 1,
      externalOrderId: 1,
      createdAt: 1,
      amountCents: 1,
      origin: 1
    }
  }
]);
```

Với dữ liệu mẫu hợp lệ, kết quả dự kiến rỗng. Để quan sát lỗi, có thể chèn một **document archive demo** cùng `runId` nhưng `dateText` không hợp lệ; sau đó nhìn thấy `createdAt: null` trong output. Không thay validator hoặc dữ liệu production để thử.

### 15.4. Bài D: so sánh hai câu hỏi

Chạy:

```javascript
// Bao nhiêu document được union?
current.aggregate([
  ...normalizedUnion,
  { $count: "allRows" }
]);

// Bao nhiêu order duy nhất theo business key?
current.aggregate([
  ...normalizedUnion,
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      }
    }
  },
  { $count: "uniqueOrders" }
]);
```

Giải thích tại sao cùng một dữ liệu mà hai câu hỏi cho hai số khác nhau. Tại sao không thể lấy số document của hai collection cộng lại rồi coi là tổng order duy nhất?

## 16. Dọn dữ liệu thử nghiệm an toàn

Các thao tác `aggregate()` trong bài chỉ đọc; document demo được tạo ở mục 4. Trước khi xóa, hãy xác nhận đúng database, collection, `runId` và danh sách document:

```javascript
print("database=" + lab.getName());
print("current collection=" + current.getName());
print("archive collection=" + archive.getName());
print("runId=" + runId);

const ownedCurrent = current.find(
  { runId },
  { _id: 1, runId: 1, externalOrderId: 1 }
).toArray();

const ownedArchive = archive.find(
  { runId },
  { _id: 1, runId: 1, reference: 1 }
).toArray();

printjson(ownedCurrent);
printjson(ownedArchive);
```

Chỉ khi đây là **document do chính lượt thực hành tạo**, xóa theo `_id` **kèm `runId`**:

```javascript
for (const doc of ownedCurrent) {
  printjson(current.deleteOne({ _id: doc._id, runId }));
}

for (const doc of ownedArchive) {
  printjson(archive.deleteOne({ _id: doc._id, runId }));
}

print("current remaining=" + current.countDocuments({ runId }));
print("archive remaining=" + archive.countDocuments({ runId }));
```

Nếu biến `runId` bị mất, hãy dựa vào giá trị đã ghi khi tạo dữ liệu hoặc một danh sách ID đã xác nhận; không đoán ID rồi xóa. Không chạy `deleteMany({})`, `drop()` hoặc `dropDatabase()` trong môi trường chung. Index nếu bạn tạo khi thực hành vẫn tồn tại sau khi xóa document; chỉ quản lý chúng theo đúng quyền và quy trình.

## 17. Câu hỏi ôn tập

1. `$unionWith` khác `$lookup` ở mục tiêu và hình dạng kết quả như thế nào?
2. Vì sao gọi `$unionWith` là tương tự SQL `UNION ALL` thay vì `UNION`?
3. Hai collection cần có schema giống hệt nhau mới union được không?
4. `coll` và `pipeline` trong stage `$unionWith` có ý nghĩa gì?
5. Nếu chỉ đặt `$match` trước `$unionWith`, nó lọc nguồn nào?
6. Vì sao `$sort` của từng nhánh không đủ để bảo đảm thứ tự cuối?
7. Trong ví dụ current/archive, vì sao `A-101` xuất hiện hai lần?
8. Để đếm số order duy nhất, tại sao nhóm theo `(tenantId, externalOrderId)` thay vì `_id`?
9. Vì sao `$first` không kèm quy tắc sort có thể chọn bản ghi không ổn định?
10. Khi nào cần giữ cả `origin` và `sourceId`?
11. Vì sao phải chuẩn hóa ngày string thành BSON Date trước khi so sánh thời gian?
12. Nếu `dateText` không parse được và `$dateFromString` có `onError: null`, kết quả có thể bị ảnh hưởng ra sao?
13. Vì sao phân trang sau union nhưng trước dedup có thể sai về mặt nghiệp vụ?
14. Có được đặt `$merge` trong subpipeline của `$unionWith` không?
15. Có được dùng `$unionWith` trong transaction không?
16. Khi mỗi nguồn có index riêng, vì sao một index trên current không tự tối ưu subpipeline archive?
17. Khi nào đọc từ current/archive bằng union nên được thay bằng một collection báo cáo đã materialize?
18. Collation của collection được union có tự thay thế collation của operation chính không?

## 18. Tài liệu tham khảo

Khi sử dụng trên môi trường production, tham khảo cú pháp, giới hạn và tính năng theo phiên bản MongoDB đang chạy:

- [`$unionWith` (aggregation stage) — MongoDB Database Manual](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unionWith/)
- [`$group` (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [`$project` (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/)
- [`$dateFromString` (aggregation expression)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateFromString/)
- [`$convert` (aggregation expression)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [`$lookup` (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [`$merge` (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/)

## 19. Kết luận

`$unionWith` là stage của MongoDB aggregation dùng để **kết hợp document từ các luồng kết quả**, tương đương ý tưởng **UNION ALL**: nó giữ bản ghi trùng và **không bảo đảm thứ tự đầu ra**. Stage này không join theo khóa, không bắt buộc hai nguồn cùng schema và không tự ghi kết quả vào collection.

Muốn dùng union đúng trong ứng dụng, hãy **lọc đúng từng nguồn**, **chuẩn hóa field và kiểu BSON**, **định nghĩa chính sách xử lý bản ghi trùng** rồi mới thống kê hoặc phân trang. Khi cần kết quả có thứ tự, hãy `$sort` sau khi hợp nhất; khi cần mỗi thực thể nghiệp vụ một lần, hãy dùng `$group` theo **khóa nghiệp vụ đầy đủ** với quy tắc chọn document rõ ràng. Hiệu năng và tính nhất quán phụ thuộc vào dữ liệu, index, stage tiếp theo và giới hạn của MongoDB — không chỉ riêng cú pháp `$unionWith`.

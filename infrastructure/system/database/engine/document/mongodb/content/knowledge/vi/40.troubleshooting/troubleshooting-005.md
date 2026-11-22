# Lỗi document quá lớn, mảng tăng không giới hạn và giới hạn pipeline trong MongoDB

## Mục tiêu bài học

Trong MongoDB, nhiều lỗi vận hành không xuất phát từ mất kết nối hoặc một câu lệnh sai cú pháp. Một hệ thống có thể chạy ổn định suốt nhiều tháng rồi bất ngờ gặp:

- `BSONObjectTooLarge` khi ghi thêm một phần tử vào mảng của một document.
- `Document exceeds maximum size` khi một order, user profile hay audit record ngày càng lớn.
- `ExceededMemoryLimit` trong pipeline chứa `$group`, `$sort` hoặc `$facet`.
- Lỗi aggregation vì **một kết quả** vượt giới hạn BSON, dù query chỉ trả về một document.
- Query trở nên rất chậm sau khi thêm `$lookup`, `$unwind` hoặc `$push` accumulator.
- Lệnh bật `allowDiskUse: true` nhưng pipeline vẫn thất bại.
- Một worker chạy `$push` liên tục vào cùng document, khiến hotspot, index maintenance và tải replication tăng cao.

Bài thuộc **Database Engine Document MongoDB → Xử lý sự cố → Lỗi document quá lớn, mảng tăng không giới hạn và giới hạn pipeline**.

Sau bài học, bạn có thể:

1. Xác định **giới hạn 16 MiB cho một BSON document**, ý nghĩa của bytes, BSON overhead và kích thước trung gian.
2. Phân biệt giới hạn BSON document với giới hạn bộ nhớ aggregation, số pipeline stages, thời gian thực thi và kích thước response.
3. Dùng `$bsonSize`, `$size`, `collStats`, `explain` và server logs để khoanh vùng.
4. Chẩn đoán lỗi xuất hiện lúc `insertOne`, `updateOne`, `findOneAndUpdate`, `aggregate`, `$lookup`, `$group` hoặc `$facet`.
5. Giải thích vì sao `$push`, `$addToSet` và event logs nhúng có thể tạo **unbounded arrays**.
6. Giới hạn mảng bằng `$push + $each + $slice` đúng nghiệp vụ, không coi đó là cách lưu lịch sử dài hạn.
7. Chuyển mô hình dữ liệu từ unbounded embedding sang **referenced collection**, **bounded buckets** hoặc **GridFS** khi phù hợp.
8. Hiểu các stage có thể spill ra đĩa, tương tác của `allowDiskUse` và những trường hợp không thể spill.
9. Giảm fan-out, kích thước intermediate và output trong `$lookup`, `$unwind`, `$group`, `$facet`.
10. Thiết kế pipeline trả **nhiều documents nhỏ qua cursor** thay vì gom tất cả vào một document khổng lồ.
11. Thực hiện migration dữ liệu lớn an toàn với batching, idempotent writes, checkpoint, reconciliation và rollback plan.
12. Đặt guardrails cho ứng dụng Java/Spring Data, xác thực input và theo dõi các chỉ số dự báo sự cố.
13. Viết một runbook ứng cứu production không mất dữ liệu và không làm sự cố lớn hơn.

> **Quy tắc cốt lõi:** `allowDiskUse` có thể giảm áp lực bộ nhớ cho **một số aggregation stages**, nhưng **không tăng giới hạn 16 MiB của một BSON document** và cũng không loại bỏ mọi giới hạn bộ nhớ nội bộ.

---

## 1. Bản đồ các giới hạn dễ nhầm

| Phạm vi | Mốc/giới hạn tiêu biểu | Đặc điểm |
|---|---|---|
| Một BSON document được lưu/trả | **16 MiB = 16.777.216 bytes** | Giới hạn cứng của document |
| Độ sâu lồng BSON | **100 cấp** | Không giải quyết bằng chia array thành nhiều lớp lồng |
| Số aggregation pipeline stages | **1.000 stages** | Kiểm tra trước/sau parse/optimization theo docs |
| Bộ nhớ một số aggregation stages | Mốc **100 MB** theo docs, phụ thuộc server/settings | Một số stages spill nếu được phép |
| `$facet` stage output | Tối đa **100 MB** một document trung gian trong facet | `allowDiskUse` **không** giúp facet spill |
| Kết quả cuối của `$facet` | Vẫn chịu **16 MiB** cho BSON document | Giới hạn của output |
| `$group` accumulator `$push`/`$addToSet` | Có giới hạn bộ nhớ cho **một accumulator value** | Không tự spill dù group state có thể spill |
| Một MongoDB cursor trả nhiều documents | Không bị giới hạn **16 MiB cho cả tập hợp kết quả** | Nhưng từng result document vẫn ≤16 MiB |
| Một array embedded | Không có số phần tử cố định duy nhất áp cho mọi array | Bị ràng buộc bởi kích thước document và khác giới hạn |
| File/ảnh/video lớn | Có thể lưu bằng GridFS | Không phải tăng kích thước một BSON document |

**Lưu ý về phiên bản:** Các giới hạn và semantics có thể có điểm khác giữa các MongoDB Server releases. Mốc 16 MiB và 1.000 stages là những giới hạn phổ biến được MongoDB công bố. Từ MongoDB 6.0, `allowDiskUseByDefault` ảnh hưởng cách các stages spill. Một số versions mới còn có giới hạn tổng bộ nhớ **theo operation** riêng với giới hạn theo stage. Khi ứng cứu, xác nhận `db.version()`, FCV khi liên quan và tài liệu tương ứng phiên bản thực tế.

Nguồn tham khảo: [MongoDB Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/) và [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/).

---

## 2. Hiểu đúng 16 MiB: giới hạn của một BSON document

MongoDB lưu và trao đổi documents ở dạng **BSON**, không phải JSON text thuần. Giới hạn document:

~~~text
16 × 1024 × 1024 = 16,777,216 bytes
~~~

BSON gồm tên các field, kiểu, độ dài string/binary, giá trị, phần tử mảng và overhead. Vì vậy một JSON string dài 15 MiB không đảm bảo BSON sau encoding còn dưới 16 MiB.

### 2.1. Giới hạn áp dụng cho những gì?

- Document được `insertOne` hoặc `insertMany`.
- Trạng thái document **sau** `updateOne`, `updateMany`, `findOneAndUpdate`, `$push`, `$set`.
- Một document trả về từ aggregation.
- Một document tạo bởi `$group`/`$lookup`/`$facet` ở đầu ra có kích thước không phù hợp.

### 2.2. Điều gì không có nghĩa 16 MiB?

- Không phải một collection chỉ được tối đa 16 MiB.
- Không phải một query được trả tối đa 16 MiB **tổng cộng**.
- Không phải kích thước toàn bộ batch/cursor bằng một document.
- Không phải giới hạn của một mảng riêng lẻ nếu document còn nhiều fields.
- Không phải tăng `batchSize` là có thể trả một document lớn hơn.
- Không phải cho phép server nhận một payload tùy ý vì đã bật `allowDiskUse`.

### 2.3. Ví dụ thực tế

~~~javascript
{
  _id: "ORDER-101",
  tenant_id: "tenant-a",
  status: "PAID",
  items: [
    // Ban đầu có 5 phần tử,
    // sau nhiều phiên bản ứng dụng có 300.000 phần tử.
  ],
  audit_events: [
    // Mỗi cập nhật lại append thêm event.
  ]
}
~~~

Ngay cả khi `status` và `tenant_id` nhỏ, hai arrays có thể khiến toàn bộ document vượt ngưỡng.

### 2.4. Giới hạn 100 cấp lồng

Lồng thêm nhiều object không tránh được 16 MiB mà còn có thể va chạm giới hạn độ sâu. Nên chọn cấu trúc phản ánh truy vấn và vòng đời dữ liệu thay vì “đóng gói nhiều lớp để qua giới hạn”.

### 2.5. Thực hành đo bytes, không đo số ký tự

Chuỗi Unicode tiếng Việt có thể tốn nhiều UTF-8 bytes hơn số ký tự. Đo kích thước BSON thực bằng công cụ chuyên dụng, không chỉ dùng `JSON.stringify(doc).length`.

---

## 3. Mô hình lỗi theo vị trí xảy ra

~~~text
Request / Job / Query
         |
         +-- INSERT / UPDATE
         |      |
         |      +-- BSON object too large
         |      +-- Array grows without bound
         |      +-- Invalid array type
         |
         +-- AGGREGATE
         |      |
         |      +-- One result doc > 16 MiB
         |      +-- $facet internal doc > 100 MB
         |      +-- $group accumulator too large
         |      +-- $sort/$group memory no spill
         |      +-- > 1000 pipeline stages
         |      +-- Join/unwind cardinality explosion
         |
         +-- APPLICATION / NETWORK
                |
                +-- Driver/client encoding error
                +-- Timeouts
                +-- API gateway response size
                +-- JVM heap / GC pressure
~~~

Một triệu documents nhỏ trong cursor **khác** với một document chứa mảng một triệu phần tử. Cả hai có thể đòi nhiều tài nguyên, nhưng cách giải quyết khác nhau.

---

## 4. Nhận diện thông báo lỗi

Lỗi cụ thể thay đổi theo server version, driver và điểm phát sinh.

| Dấu hiệu trong exception/log | Khả năng cao | Điều cần xác nhận |
|---|---|---|
| `BSONObjectTooLarge` | Một BSON object vượt kích thước cho phép | Document nào và stage nào tạo ra? |
| `object to insert too large` | Insert/update tạo document quá lớn | `$bsonSize` của document hiện tại và payload mới |
| `Document exceeds maximum size` | Giới hạn kích thước document | Output hay persisted document? |
| `ExceededMemoryLimit` | Một stage/accumulator không đủ bộ nhớ | Stage, allowDiskUse, per-operation cap |
| `QueryExceededMemoryLimitNoDiskUseAllowed` | Stage có thể spill nhưng bị cấm disk | Có thể bật disk an toàn không? |
| `Sort exceeded memory limit` | Sort phải giữ quá nhiều dữ liệu | Có index, match/limit hợp lý không? |
| Lỗi `$facet` ~100 MB | Facet intermediate quá lớn | Có gom dữ liệu thành arrays không? |
| Lỗi exceeded max pipeline stages | Pipeline có quá nhiều stages | Có 1.000+ stages sau parse không? |
| `ExceededTimeLimit`/timeout | Thời gian/nguồn lực hoặc topology | Không tự kết luận là BSON size |
| Java `OutOfMemoryError` | Client giữ dữ liệu quá lớn | Cursor streaming, buffering, heap dump |
| HTTP 413 / gateway limit | Giới hạn API/gateway, không nhất thiết MongoDB | Kích thước response, proxy config |

### 4.1. Đừng ghi cứng error code duy nhất

Một lỗi “document too large” có thể được phát hiện phía client trước khi gửi, ở server khi update hoặc khi aggregation tạo kết quả. Mã lỗi và class exception có thể khác giữa MongoDB Driver/Spring Data versions.

### 4.2. Phải thu thập ngữ cảnh

Lưu operation type, collection, request ID, tenant ID **đã che/giới hạn quyền**, document ID và pipeline stage, server version, driver version, timestamp, stack trace, duration, input payload size. Không dump PII, secrets hoặc toàn bộ document lớn vào log.

---

## 5. Chẩn đoán kích thước document bằng `$bsonSize`

MongoDB có expression `$bsonSize` trả số bytes của BSON document.

### 5.1. Tìm 20 documents lớn nhất

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      tenant_id: 1,
      bson_bytes: {
        $bsonSize: "$$ROOT"
      }
    }
  },
  {
    $sort: {
      bson_bytes: -1,
      _id: 1
    }
  },
  { $limit: 20 }
], {
  allowDiskUse: true
});
~~~

**Giải thích:** `$$ROOT` là document hiện tại. `$bsonSize` đo kích thước khi encoded BSON. `$project` làm output nhỏ trước khi `$sort`. Vẫn cần đọc source document đầy đủ để tính kích thước nên đây có thể là scan nặng trên collection lớn.

### 5.2. Tìm documents vượt ngưỡng cảnh báo

Ví dụ dùng ngưỡng điều hành **8 MiB**, không phải giới hạn MongoDB:

~~~javascript
const alertBytes = 8 * 1024 * 1024;

db.orders.aggregate([
  {
    $project: {
      _id: 1,
      tenant_id: 1,
      bytes: {
        $bsonSize: "$$ROOT"
      }
    }
  },
  {
    $match: {
      bytes: { $gte: alertBytes }
    }
  },
  { $sort: { bytes: -1 } },
  { $limit: 100 }
], {
  allowDiskUse: true
});
~~~

Dùng quota cảnh báo sớm như 2/4/8 MiB tùy business record và tốc độ tăng trưởng; không đợi tới 16 MiB mới phản ứng.

### 5.3. Đo một document xác định

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: "ORDER-101"
    }
  },
  {
    $project: {
      _id: 1,
      bytes: { $bsonSize: "$$ROOT" }
    }
  }
]);
~~~

### 5.4. `$bsonSize` của field lồng

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ORDER-101" } },
  {
    $project: {
      _id: 1,
      total_bytes: { $bsonSize: "$$ROOT" },
      metadata_bytes: {
        $bsonSize: {
          $ifNull: ["$metadata", {}]
        }
      }
    }
  }
]);
~~~

`$bsonSize` đòi đối số resolve thành BSON object hoặc null, không tự đo string/number. Với string/binary dùng `$binarySize` khi thích hợp; với array có thể bọc trong object hoặc khảo sát số phần tử/kiểu và kích thước tổng thể.

### 5.5. Lưu ý các phiên bản mới

Tài liệu `$bsonSize` có thay đổi ở MongoDB 9.0 liên quan intermediate documents lớn hơn 16 MiB. Để điều tra **persisted documents**, ví dụ `$bsonSize:"$$ROOT"` đầu pipeline là trường hợp đơn giản; khi đo **intermediate output >16 MiB**, phải xem semantics theo bản server.

Tài liệu: [`$bsonSize`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonsize/).

---

## 6. Phát hiện mảng lớn và mảng tăng không giới hạn

### 6.1. Đếm số phần tử

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      event_count: {
        $cond: [
          { $isArray: "$audit_events" },
          { $size: "$audit_events" },
          null
        ]
      },
      bytes: { $bsonSize: "$$ROOT" }
    }
  },
  { $sort: { event_count: -1 } },
  { $limit: 20 }
], { allowDiskUse: true });
~~~

Dùng `$isArray` để tránh lỗi nếu field đã bị ghi sai thành string/object hoặc missing.

### 6.2. Mảng nhiều phần tử không luôn lớn nhất

- 100.000 integers nhỏ có thể ít bytes hơn 1.000 objects chứa chuỗi dài.
- `audit_events` với nested payload/raw HTTP body có thể cực lớn dù chỉ vài nghìn events.
- Metadata, comments, images embedded và history snapshots cũng góp phần.

Phải đo **cả count, BSON bytes và distribution**.

### 6.3. Truy vấn top documents theo tỷ lệ

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenant_id: "tenant-a"
    }
  },
  {
    $project: {
      _id: 1,
      bytes: { $bsonSize: "$$ROOT" },
      audit_count: {
        $cond: [
          { $isArray: "$audit_events" },
          { $size: "$audit_events" },
          0
        ]
      }
    }
  },
  { $sort: { bytes: -1 } },
  { $limit: 30 }
]);
~~~

Nếu không có index giúp sort trên computed `bytes`, query phải scan/sort; chạy theo shard key, tenant cohort hoặc ngoài giờ cao điểm nếu data lớn.

### 6.4. Histogram giúp dự báo

Nhóm kích thước theo mức 1 MiB:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      size_mib: {
        $divide: [
          { $bsonSize: "$$ROOT" },
          1024 * 1024
        ]
      }
    }
  },
  {
    $bucket: {
      groupBy: "$size_mib",
      boundaries: [0, 1, 2, 4, 8, 12, 16],
      default: "outside",
      output: {
        documents: { $sum: 1 }
      }
    }
  }
], { allowDiskUse: true });
~~~

Kết quả dùng cho phân tích phân bố, không đồng nghĩa thao tác này rẻ trên collection rất lớn.

---

## 7. `collStats`, `avgObjSize` và giới hạn của thống kê trung bình

### 7.1. Thống kê collection

~~~javascript
db.orders.stats();
~~~

Output có thể bao gồm:

- `count`.
- `size` (logical data size).
- `avgObjSize`.
- `storageSize`.
- `totalIndexSize` hoặc index statistics.
- Các thông tin storage engine/scale khác tùy server/version.

### 7.2. Trung bình che mất tail

Một collection 1 triệu documents có kích thước trung bình 3 KiB vẫn có thể có vài documents 15 MiB. `avgObjSize` **không** thay việc tính p95/p99/max hoặc top large documents.

### 7.3. Logical size khác allocated storage

`size` và `storageSize` có semantics khác: compression/fragmentation/free space có thể khiến storage allocated không khớp bytes của một document. Không lấy `storageSize/count` để khẳng định một document còn cách bao xa so với 16 MiB.

### 7.4. Sharded cluster

`stats` trên collection sharded có thể thể hiện tổng hợp per-shard; cần phân tích distribution/hot shards khi có skew. Tránh quét full collection từ mongos vào giờ cao điểm chỉ để tìm top records.

---

## 8. Nguyên nhân thường gặp: `$push` liên tục

Giả sử service ghi audit events ngay trong order:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORDER-101",
    tenant_id: "tenant-a"
  },
  {
    $push: {
      audit_events: {
        event_id: "evt-0001",
        type: "ORDER_VIEWED",
        at: new Date(),
        details: {
          ip: "192.0.2.1"
        }
      }
    }
  }
);
~~~

Nếu mỗi request append, array tăng liên tục. Một ngày 100 events, mỗi event 1 KiB sẽ tăng khoảng 100 KiB/ngày, chưa tính BSON overhead; sau nhiều tháng vẫn có thể vượt ngưỡng.

### 8.1. `$push` không giới hạn số phần tử

`$push` thêm element. Nếu field chưa tồn tại, MongoDB có thể tạo array; nếu field tồn tại nhưng không phải array, operation lỗi.

### 8.2. Vì sao lỗi chỉ xuất hiện với một số khách hàng?

- Một số accounts có hoạt động lớn hơn nhiều.
- Bots gây nhiều view/tracking events.
- Tenant cao tải có nhiều invoices/comments.
- Một retry loop append nhiều lần.
- Một message consumer không idempotent tạo duplicate events.
- Mảng chứa payload từ bên ngoài ngày càng lớn.

### 8.3. Ghi lại lỗi không được tiếp tục append

Khi document gần ngưỡng, retry cùng payload không sửa được vấn đề. Tăng retry count và log thêm event vào **chính document lỗi** có thể làm tình hình tệ hơn.

---

## 9. `$addToSet` không chống mảng tăng vô hạn

Một cách phản ứng sai là đổi mọi `$push` thành `$addToSet`:

~~~javascript
db.orders.updateOne(
  { _id: "ORDER-101" },
  {
    $addToSet: {
      audit_events: {
        event_id: "evt-1001",
        at: new Date(),
        type: "STATUS_CHECK"
      }
    }
  }
);
~~~

`$addToSet` chỉ ngăn thêm **giá trị trùng theo equality toàn element**. Nếu timestamp thay mỗi lần, mỗi event khác nhau và mảng vẫn tăng.

### 9.1. Nó không unique theo một subfield

~~~javascript
{ event_id: "evt-1001", at: ISODate("2026-11-14T01:00:00Z") }
{ event_id: "evt-1001", at: ISODate("2026-11-14T01:00:01Z") }
~~~

Hai objects khác nhau. `$addToSet` không có unique index kiểu “chỉ một element có event_id=evt-1001”.

### 9.2. Không dọn duplicates đã tồn tại

Nếu array đã có duplicate values từ trước, `$addToSet` không tự xóa toàn bộ duplicates.

### 9.3. Chọn cơ chế phù hợp

- Set tags rất nhỏ, miền giá trị hữu hạn: `$addToSet` có thể tốt.
- Log event vô hạn: chuyển sang collection events riêng.
- Giữ N notifications gần nhất: bounded array.
- Ledger nghiệp vụ: collection records có unique event ID/sequence, không nhúng vô hạn.

---

## 10. Dùng `$push + $each + $slice` để tạo bounded array

Nếu business **chỉ cần 100 sự kiện gần nhất**, lưu trong `recent_events` là hợp lý.

~~~javascript
db.orders.updateOne(
  {
    _id: "ORDER-101",
    tenant_id: "tenant-a"
  },
  {
    $push: {
      recent_events: {
        $each: [
          {
            event_id: "evt-2001",
            at: ISODate("2026-11-14T07:00:00Z"),
            type: "ORDER_UPDATED"
          }
        ],
        $sort: {
          at: -1,
          event_id: -1
        },
        $slice: 100
      }
    }
  }
);
~~~

### 10.1. Thứ tự xử lý

Khi dùng modifiers, MongoDB thêm các elements, áp sort nếu có, rồi slice, sau đó lưu array. `$slice:100` giữ 100 phần tử đầu sau sort.

### 10.2. `$slice:-100`

Nếu không dùng sort và chỉ append theo thời gian, `$slice:-100` giữ **100 phần tử cuối array** sau append.

~~~javascript
db.orders.updateOne(
  { _id: "ORDER-101" },
  {
    $push: {
      recent_events: {
        $each: [
          { event_id: "evt-2002", at: new Date() }
        ],
        $slice: -100
      }
    }
  }
);
~~~

### 10.3. Không đủ cho long-term audit

Mọi event ngoài 100 phần tử sẽ bị loại. Nếu cần lưu lịch sử tuân thủ/phục vụ truy vết, phải ghi toàn bộ vào collection hoặc hệ thống event log riêng; bounded array chỉ là **cache/tóm tắt gần đây**.

### 10.4. Mỗi element vẫn phải giới hạn kích thước

100 events × 200 KiB mỗi event có thể vượt 16 MiB. Bounded **số lượng** chưa đủ; còn phải giới hạn event payload, strings/nested documents.

### 10.5. Idempotency

`$push` với retry có thể chèn event trùng. Nếu cần event không trùng, dùng collection có unique index trên stable event ID hoặc thiết kế dedup riêng.

Tài liệu: [`$push` và modifiers](https://www.mongodb.com/docs/manual/reference/operator/update/push/).

---

## 11. Biện pháp ngắn hạn khi document đã gần 16 MiB

### 11.1. Dừng đường ghi làm document phình ra

Ví dụ tắt feature flag ghi audit array, nhưng **không dừng toàn bộ order workflow nếu chỉ một tính năng phụ gây lỗi**. Quyết định phải dựa vào mức độ nghiệp vụ và data retention.

### 11.2. Chọn lọc log/payload

Dừng lưu raw body, ảnh, base64, large diagnostics hoặc repeated snapshots trong document. Lưu pointer/hash/summary thay vì dữ liệu thô, theo security policy.

### 11.3. Đặt ngưỡng từ application

Chặn event payload vượt max bytes của domain và thay bằng tham chiếu tới nơi lưu phù hợp. Không chờ MongoDB trả lỗi rồi mới cắt cụt dữ liệu bất kỳ.

### 11.4. Không xóa tùy tiện để “cứu kích thước”

`$pop`, `$pull` hoặc `$set: {audit_events: []}` có thể làm mất audit/ledger. Chỉ cắt dữ liệu nếu đã copy và xác minh hoặc domain cho phép retention limit.

### 11.5. Document gần max có thể không thêm được migration marker

Nếu document đã sát 16 MiB, việc set `migration_status:"MIGRATING"` vào cùng document có thể thất bại. Lưu checkpoint/migration metadata ở **collection điều khiển riêng**.

### 11.6. Một update làm giảm kích thước

Nếu đã backup/extract dữ liệu và có approval, `$unset` một field lớn trong document có thể giảm size. Nhưng nếu có concurrent writers, phải dùng lease/CAS/feature flag thích hợp để tránh mất events sinh giữa extract và unset.

---

## 12. Cách mô hình dữ liệu gây tăng trưởng không giới hạn

### 12.1. Những mảng có rủi ro cao

- Audit events, clickstream, page views.
- All comments/likes/views của một sản phẩm.
- Mọi giao dịch ngân hàng của một user.
- Tất cả message của một chat room.
- Mọi notification push của một tài khoản.
- Mọi job execution history của một workflow.
- Giá/hàng tồn kho theo từng phút trong nhiều năm.
- Mọi order ID mà một customer từng tạo.
- Embedded base64 files hoặc thumbnail rất lớn.
- Retry attempts lưu nguyên request/response bodies.

### 12.2. Cardinality phải xét theo vòng đời

Một mảng 10 phần tử hôm nay có thể thành 1 triệu phần tử sau 5 năm. Hãy đặt câu hỏi:

- Một parent có tối đa bao nhiêu children về **business**?
- Tốc độ tăng trưởng theo ngày/tháng?
- Mỗi child có giới hạn bytes không?
- Children có được truy vấn/ghi độc lập không?
- Có phải lấy toàn bộ children khi load parent không?
- Có retention/TTL/legal hold không?
- Có multi-writer contention không?

### 12.3. Embed khi nào?

Thường phù hợp với **nhóm con hữu hạn, nhỏ và thường được đọc/cập nhật cùng parent**, ví dụ 2–5 địa chỉ thanh toán hoặc 10 cấu hình giao diện.

### 12.4. Reference khi nào?

Phù hợp với **one-to-many không giới hạn, có vòng đời và access pattern riêng**, ví dụ order events, comments, notifications, ledger entries.

---

## 13. Đổi từ unbounded array sang referenced collection

### 13.1. Mô hình cũ

~~~javascript
{
  _id: "ORDER-101",
  status: "PAID",
  events: [
    { id: "E1", type: "CREATED", at: ISODate("2026-11-10T10:00:00Z") },
    { id: "E2", type: "PAID", at: ISODate("2026-11-10T10:05:00Z") }
  ]
}
~~~

### 13.2. Mô hình mới

`orders`:

~~~javascript
{
  _id: "ORDER-101",
  tenant_id: "tenant-a",
  status: "PAID",
  event_count: NumberLong("2"),
  latest_event_at: ISODate("2026-11-10T10:05:00Z")
}
~~~

`order_events`:

~~~javascript
{
  _id: "E2",
  tenant_id: "tenant-a",
  order_id: "ORDER-101",
  type: "PAID",
  at: ISODate("2026-11-10T10:05:00Z"),
  schema_version: 1
}
~~~

### 13.3. Indexes gợi ý

~~~javascript
db.order_events.createIndex({
  tenant_id: 1,
  order_id: 1,
  at: -1,
  _id: -1
});
~~~

`_id` của event có unique index mặc định. Nếu cần unique event sequence trong mỗi order:

~~~javascript
db.order_events.createIndex(
  { tenant_id: 1, order_id: 1, sequence: 1 },
  { unique: true }
);
~~~

### 13.4. Đọc theo trang

~~~javascript
db.order_events.find({
  tenant_id: "tenant-a",
  order_id: "ORDER-101"
}).sort({
  at: -1,
  _id: -1
}).limit(50);
~~~

Kết quả là 50 documents riêng, không phải một array embedded lớn trong một document.

### 13.5. Trade-off

- Query toàn bộ order + events cần nhiều operations hoặc `$lookup`.
- Không còn atomic single-document update cho order và mọi event cùng lúc, có thể cần transaction/outbox.
- Ghi events phân tán giảm hotspot ở parent.
- Retention/TTL theo event dễ hơn.
- Pagination/indexing theo event trở nên tự nhiên.

---

## 14. Bounded buckets: trung gian giữa embed và reference

Thay vì lưu mọi event trong một parent document, chia thành nhiều bucket documents, mỗi bucket giới hạn ví dụ 100 hoặc 500 events.

~~~javascript
{
  _id: "ORDER-101:2026-11:part-01",
  tenant_id: "tenant-a",
  order_id: "ORDER-101",
  bucket: "2026-11",
  part: 1,
  count: 100,
  events: [
    // Tối đa 100 events,
    // mỗi event có kích thước được giới hạn.
  ]
}
~~~

### 14.1. Lợi ích

- Giảm số documents so với mỗi event là một document.
- Không có một parent array tăng vô hạn.
- Dễ truy xuất theo partition thời gian/order.
- Giúp ứng dụng đọc theo chunks đã giới hạn.

### 14.2. Rủi ro

- Bucket giới hạn về count vẫn có thể vượt 16 MiB nếu payload lớn.
- Tạo bucket mới đồng thời phải có protocol tránh chèn trùng/lost events.
- Nếu nhiều writers append cùng bucket, contention có thể cao.
- TTL trên bucket xóa toàn bucket; không luôn đúng retention từng event.

### 14.3. Đừng dùng một bucket ID đơn giản dễ race

Nếu tất cả workers tự đặt `part = floor(count/100)` mà không có atomic counter/unique key, hai writers có thể chọn cùng part hoặc tạo gap. Thiết kế allocation/idempotency theo nguồn dữ liệu.

### 14.4. Khi nào không cần bucket?

Nếu event logs lớn, cần truy vấn độc lập, retention per event hoặc đơn giản hóa correctness là ưu tiên, dùng **mỗi event một document** thường dễ quản lý hơn.

---

## 15. GridFS cho file/blob lớn

Nếu cần lưu file PDF, ảnh, video hoặc payload binary lớn hơn 16 MiB, MongoDB hỗ trợ **GridFS**.

GridFS chia file thành chunks, lưu metadata và chunks trong collections liên quan. Nó không cho phép một BSON document bất kỳ vượt 16 MiB.

### 15.1. Phân biệt GridFS và unbounded array

| Dữ liệu | Hướng mô hình |
|---|---|
| Một file lớn 50 MiB | GridFS hoặc object storage |
| Hàng triệu events nhỏ | Collection events riêng |
| 100 notifications gần nhất | Bounded embedded array |
| Một invoice có 5 line items | Embed |
| Một user có 300.000 orders | References; không embed tất cả |
| 3 GB audit attachments | GridFS/object storage theo policy |
| Các thống kê cộng dồn | Materialized counters/aggregations, không gom raw events |

### 15.2. Java Sync Driver GridFS

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;
import com.mongodb.client.MongoDatabase;
import java.io.InputStream;

GridFSBucket bucket =
    GridFSBuckets.create(mongoDatabase, "files");

try (InputStream stream = fileInputStream) {
    var fileId = bucket.uploadFromStream(
        "attachment.pdf",
        stream
    );

    System.out.println(fileId);
}
~~~

Đoạn mã giả định `mongoDatabase` và `fileInputStream` đã tồn tại. Với file production, cần auth, metadata tenant ownership, MIME validation, checksum, retention và chính sách lỗi upload giữa chừng.

### 15.3. Không lưu dữ liệu business vô hạn như một file mù

Đặt hàng triệu events vào một file GridFS có thể tránh 16 MiB nhưng làm khó query/filter/index/update và dedup. GridFS dành cho file-like data, không phải giải pháp tự động cho mọi schema lỗi.

Tài liệu: [GridFS](https://www.mongodb.com/docs/manual/core/gridfs/).

---

## 16. Thêm guardrail kích thước từ phía ứng dụng

### 16.1. Giới hạn event payload

Với event nhận từ bên ngoài, quy định:

- Maximum JSON/BSON payload bytes.
- Maximum string length.
- Maximum nested depth.
- Allowed fields.
- Maximum labels/tags.
- Maximum recent-events retained.
- Retry/dedup semantics.

Đo bytes thực thay vì chỉ so số ký tự.

### 16.2. Cắt payload có chủ đích

Không silently truncate payment event hay legal audit. Nếu mục đích chỉ là diagnostic, có thể lưu subset/hash và link đến blob với TTL theo policy.

### 16.3. Dùng validator cho cấu trúc mảng

Có thể dùng `$jsonSchema` với `maxItems` theo schema/domain:

~~~javascript
db.createCollection("notification_summaries", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        recent_notifications: {
          bsonType: "array",
          maxItems: 100,
          items: {
            bsonType: "object",
            required: ["event_id", "at"]
          }
        }
      }
    }
  }
});
~~~

Đây chỉ kiểm soát số phần tử và shape ở mức phù hợp; **không thay bảo vệ tổng kích thước document** và không tự chuyển dữ liệu legacy. Bật validator theo rollout khi đã kiểm tra current data.

### 16.4. Atomic update kiểm tra count?

Trong một số trường hợp có thể dùng conditional predicate trên kích thước array trước khi push, nhưng điều đó **không thay thế** `$slice` hoặc payload size cap. Concurrency vẫn cần kiểm soát và điều kiện phải bao gồm đúng document/tenant.

### 16.5. Ngưỡng ứng dụng nên thấp hơn 16 MiB

Giới hạn 16 MiB là trần cuối, không phải mục tiêu. Đặt business quota thấp hơn đủ xa để có chỗ cho metadata, schema evolution, future fields và operations.

---

## 17. Vì sao document lớn làm chậm hệ thống dù chưa vượt 16 MiB?

### 17.1. Bandwidth và latency

Một request chỉ cần `status` nhưng đọc cả document vài MiB tiêu tốn network và decode CPU. Projection giúp giảm payload trả về client, nhưng không biến schema hot document thành tối ưu tự động cho mọi thao tác.

### 17.2. Cache working set

Document lớn chiếm nhiều chỗ trong cache, làm giảm số records nóng giữ được trong bộ nhớ. Có thể làm tăng I/O và p99 latency.

### 17.3. Write contention

Nhiều writers append events vào cùng một parent document gây hotspot. Mongod bảo đảm atomic single-document writes, nhưng nhiều requests có thể phải tranh chấp tài nguyên xử lý cùng document.

### 17.4. Index maintenance

Index trên nested arrays là multikey index; mỗi update có thể ảnh hưởng nhiều index entries, tăng thời gian ghi/replication. Không tạo index trên mọi field array nếu không có query workload tương ứng.

### 17.5. Replication và backup

Writes lớn tạo thêm lưu lượng, oplog/replication load và khó phục hồi. Không chỉ quan sát kích thước collection tổng mà phải xem tốc độ tăng của từng hot document.

### 17.6. Driver heap

Nếu Java service dùng `findOne` lấy document lớn rồi convert thành POJO chứa 500.000 nested objects, heap/GC có thể căng ngay cả khi server chưa trả lỗi.

---

## 18. Aggregation pipeline có ba loại giới hạn độc lập

~~~text
Input collection
       |
       v
[$match] -> [$project] -> [$group] -> [$sort] -> [$facet]
                            |           |         |
                            |           |         +-- Facet 100 MB cap
                            |           +-- Memory/spill rules
                            +-- Accumulator memory cap
       |
       v
Output docs
       |
       +-- Từng BSON result document <= 16 MiB
~~~

### 18.1. Result size

Mỗi result document của aggregation phải đáp ứng **16 MiB**. Một pipeline có thể xử lý **intermediate documents** lớn hơn 16 MiB trong một số phiên bản/ngữ cảnh, nhưng không thể xuất result lớn quá giới hạn.

### 18.2. Stage count

Một pipeline tối đa **1.000 stages** theo MongoDB docs. Giới hạn được xét trước hoặc sau parsing; việc tạo pipeline động sinh ra hàng nghìn `$project`/`$addFields` có thể vượt ngưỡng.

### 18.3. Memory

Các blocking stages như `$sort`, `$group`, `$bucket`, `$bucketAuto`, `$setWindowFields`, `$sortByCount` có thể cần memory. Tùy settings/server, một số có thể dùng disk khi vượt ngưỡng; một số accumulators không thể spill.

### 18.4. Không cùng cách sửa

- Result >16 MiB → **giảm output mỗi document** hoặc đổi output shape.
- Memory >limit → **giảm state**, dùng index/filter/limit hoặc spill nếu hỗ trợ.
- Stage count >1.000 → **đơn giản hóa pipeline/kiến trúc**.
- Timeout → tối ưu query/data model, index, cardinality; không tự kết luận là memory.
- Client OOM → streaming, projections, batch iteration, không lưu toàn cursor vào List.

---

## 19. 1.000 pipeline stages: lỗi xuất phát từ builder động

Một Java report generator có thể thêm `$project` cho mỗi rule, và sau 1.001 rules nhận lỗi.

### 19.1. Ví dụ sinh stage không cần thiết

~~~javascript
const pipeline = [];

for (let i = 0; i < 1001; i++) {
  pipeline.push({
    $addFields: {
      last_rule: i
    }
  });
}

// Không chạy trên production:
print(pipeline.length);
~~~

Tất cả 1.001 stages liên tiếp chỉ để thay một field bằng rule mới; thiết kế này không hợp lý.

### 19.2. Chẩn đoán

- In số lượng stages của pipeline được tạo trước khi gửi.
- Ghi tên/type của từng stage, không log dữ liệu nhạy cảm.
- Kiểm tra stage expansion, nested pipeline builder và views.
- Xác nhận server release, vì optimizer/parse có thể ảnh hưởng số stage hiệu lực.

### 19.3. Cách sửa

- Hợp nhất những phép biến đổi độc lập vào một `$project`/`$set` khi đúng semantics.
- Dùng `$map`/`$reduce` cho biến đổi dữ liệu thích hợp thay vì stage per element.
- Chuyển một số transformation sang code hoặc batch job nếu phù hợp.
- Materialize bước nặng thành collection trung gian qua `$merge` rồi tiếp tục trong pipeline ngắn hơn.
- Không tùy tiện chia 1.001 stages thành hai pipelines nếu làm mất atomic/consistent snapshot assumptions.

### 19.4. Đừng “tăng limit” làm workaround mặc định

Đây là giới hạn engine được công bố. Sửa pipeline design thay vì cố truy tìm một server flag không được hỗ trợ để vô hiệu hóa giới hạn.

---

## 20. Hiểu `allowDiskUse`

Từ MongoDB 6.0, server parameter `allowDiskUseByDefault` quyết định mặc định việc các stages đủ điều kiện có thể ghi temporary files ra disk khi dùng nhiều memory.

### 20.1. Bật cho một aggregate

~~~javascript
db.sales.aggregate([
  {
    $match: {
      tenant_id: "tenant-a"
    }
  },
  {
    $group: {
      _id: "$customer_id",
      total_minor: { $sum: "$amount_minor" }
    }
  },
  {
    $sort: {
      total_minor: -1
    }
  },
  { $limit: 100 }
], {
  allowDiskUse: true
});
~~~

### 20.2. Tắt spill để kiểm soát

~~~javascript
db.sales.aggregate(
  [
    { $sort: { amount_minor: -1 } },
    { $limit: 100 }
  ],
  {
    allowDiskUse: false
  }
);
~~~

Nếu sort không dùng index và vượt ngưỡng, có thể báo memory error. Đây không phải dấu hiệu dữ liệu bị hỏng, mà là resource limit cần tối ưu.

### 20.3. Bật spill không miễn phí

Disk spills có thể gây:

- I/O tạm tăng mạnh.
- Query chậm.
- Contention với storage.
- Ảnh hưởng quota/ephemeral storage.
- Performance không ổn định dưới concurrency.

### 20.4. Những gì `allowDiskUse` không sửa

- BSON document >16 MiB.
- `$facet` document >100 MB vì facet không spill.
- `$group` accumulator array vượt giới hạn riêng của nó.
- Pipeline >1.000 stages.
- Missing index khiến join quá chậm trong mọi trường hợp.
- Client heap OOM do `toArray()`/collect toàn cursor.

### 20.5. Giới hạn tổng memory theo operation

MongoDB versions mới có thêm giới hạn **per-operation memory** riêng với mức per-stage. Nếu operation vượt nó, spill không nhất thiết đủ. Kiểm tra thông báo lỗi, server version, config và metrics như `metrics.query.peakMemoryUsageOperation` hoặc `metrics.query.operationsFailedDueToMemoryLimit` khi được server cung cấp. Không mặc định đổi internal parameters trên production.

---

## 21. `$sort` vượt giới hạn bộ nhớ

### 21.1. Pipeline dễ gây lỗi

~~~javascript
db.events.aggregate([
  { $sort: { created_at: -1 } }
], {
  allowDiskUse: false
});
~~~

Nếu không có index phù hợp và dataset rất lớn, MongoDB phải duy trì sort state lớn.

### 21.2. Tạo index hỗ trợ

~~~javascript
db.events.createIndex({
  tenant_id: 1,
  created_at: -1,
  _id: -1
});
~~~

Query:

~~~javascript
db.events.aggregate([
  {
    $match: {
      tenant_id: "tenant-a"
    }
  },
  {
    $sort: {
      created_at: -1,
      _id: -1
    }
  },
  { $limit: 50 },
  {
    $project: {
      _id: 1,
      type: 1,
      created_at: 1
    }
  }
]);
~~~

Index có thể hỗ trợ filter và sort, tùy query plan thực tế. Dùng `explain` để xác nhận.

### 21.3. Match sớm, limit đúng vị trí

- `$match` sớm giúp giảm tập đầu vào khi không thay semantics.
- `$sort` kết hợp `$limit` có thể được tối ưu thành top-k sort.
- `$limit` trước `$sort` **đổi kết quả**, vì chỉ sort tập con.
- `$project` giảm payload nhưng không tự làm index sort xuất hiện.

### 21.4. Sort với fields thiếu hoặc sai kiểu

Nếu `created_at` vừa là string vừa là BSON Date, ordering có thể khác business expectation. Sửa schema/migration thay vì chỉ bật disk spill.

---

## 22. `$group` với `$push:"$$ROOT"` tạo mảng khổng lồ

Một pipeline gây lỗi phổ biến:

~~~javascript
db.order_events.aggregate([
  {
    $group: {
      _id: "$order_id",
      events: {
        $push: "$$ROOT"
      }
    }
  }
], {
  allowDiskUse: true
});
~~~

Nếu một order có 500.000 events, accumulator `events` sẽ chứa toàn bộ documents, rất dễ chạm memory limit hoặc result 16 MiB.

### 22.1. Vì sao allowDiskUse không đủ?

`$group` có thể spill phần **group state** nhất định, nhưng một số accumulator values như `$push`/`$addToSet` không thể tự spill tùy ý. Nếu một array accumulator trở nên quá lớn, stage có thể lỗi dù `allowDiskUse:true`.

### 22.2. Nếu chỉ cần đếm

~~~javascript
db.order_events.aggregate([
  {
    $group: {
      _id: "$order_id",
      event_count: { $sum: 1 }
    }
  }
]);
~~~

Thay vì gom mọi raw events vào array, trả scalar counts.

### 22.3. Nếu cần tổng

~~~javascript
db.order_events.aggregate([
  {
    $match: {
      type: "PAYMENT_APPLIED"
    }
  },
  {
    $group: {
      _id: "$order_id",
      total_minor: {
        $sum: "$amount_minor"
      }
    }
  }
]);
~~~

### 22.4. Nếu cần top N gần nhất của mỗi group

Có thể dùng `$topN`/`$firstN` ở những server versions hỗ trợ, hoặc `$setWindowFields` với partition ranking, nhưng vẫn phải giới hạn N và kiểm tra memory/index. Nếu cần toàn bộ history, **trả documents bằng cursor có pagination**, đừng gom lại vào một result document.

### 22.5. `$addToSet` không khắc phục bản chất

Một array chứa hàng triệu IDs **duy nhất** vẫn rất lớn. Dedupe không đồng nghĩa bounded.

Tài liệu: [`$group` Memory Restrictions](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/).

---

## 23. `$facet`: giới hạn 100 MB và result 16 MiB

`$facet` chạy nhiều sub-pipelines trên cùng đầu vào và trả một result document có các arrays:

~~~javascript
db.products.aggregate([
  {
    $facet: {
      byCategory: [
        {
          $group: {
            _id: "$category",
            count: { $sum: 1 }
          }
        }
      ],
      byBrand: [
        {
          $group: {
            _id: "$brand",
            count: { $sum: 1 }
          }
        }
      ]
    }
  }
]);
~~~

### 23.1. Hai ngưỡng khác nhau

- Trong `$facet`, từng resulting document có giới hạn **100 MB**.
- `$facet` **không spill ra disk**, nên `allowDiskUse:true` không tăng ngưỡng đó.
- Output cuối cùng vẫn chịu **16 MiB BSON document limit**.

### 23.2. Facet sai cách

~~~javascript
db.events.aggregate([
  {
    $facet: {
      allEvents: [
        { $sort: { at: -1 } }
      ],
      counts: [
        { $count: "n" }
      ]
    }
  }
], {
  allowDiskUse: true
});
~~~

`allEvents` không giới hạn có thể trở thành array khổng lồ.

### 23.3. Bounded facet

~~~javascript
db.events.aggregate([
  {
    $match: {
      tenant_id: "tenant-a"
    }
  },
  {
    $facet: {
      page: [
        { $sort: { at: -1, _id: -1 } },
        { $limit: 20 },
        {
          $project: {
            _id: 1,
            type: 1,
            at: 1
          }
        }
      ],
      total: [
        { $count: "value" }
      ]
    }
  }
]);
~~~

`page` chỉ giữ 20 documents và `total` trả một count nhỏ. Nhưng `$facet` vẫn có thể tốn chi phí quét/tính count; với workload lớn, có thể tách pagination và count ra hai requests.

### 23.4. Khi index có tác dụng?

`$facet` ở đầu pipeline có thể dẫn tới collection scan. Đặt `$match` (và các stages tận dụng index phù hợp) trước facet khi không đổi semantics.

### 23.5. Không “fix facet” bằng cách tăng batchSize

Batch size thay số result documents trong cursor batch, không làm nhỏ một facet result document có arrays quá lớn.

Tài liệu: [`$facet`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/).

---

## 24. `$lookup` và join fan-out tạo output lớn

Ví dụ:

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "order_events",
      localField: "_id",
      foreignField: "order_id",
      as: "all_events"
    }
  }
]);
~~~

Nếu một order có 500.000 events, `all_events` sẽ là array rất lớn.

### 24.1. Tại sao join fan-out nguy hiểm?

Một input order được “mở rộng” thêm tất cả matching foreign docs. Từ một document nhỏ có thể tạo một document/intermediate rất lớn, đẩy pipeline tới BSON output/memory limits.

### 24.2. Filter, project, limit trong lookup pipeline

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenant_id: "tenant-a",
      _id: "ORDER-101"
    }
  },
  {
    $lookup: {
      from: "order_events",
      localField: "_id",
      foreignField: "order_id",
      pipeline: [
        { $sort: { at: -1, _id: -1 } },
        { $limit: 10 },
        {
          $project: {
            _id: 1,
            type: 1,
            at: 1
          }
        }
      ],
      as: "recent_events"
    }
  }
]);
~~~

Điều này cố tình chỉ lấy 10 events mới nhất, không phải full history. Tạo index foreign phù hợp:

~~~javascript
db.order_events.createIndex({
  order_id: 1,
  at: -1,
  _id: -1
});
~~~

Nếu data là multi-tenant, cần bảo đảm foreign join cũng không cross-tenant (ví dụ join bằng composite keys/`let` + `$expr` hoặc model event ownership); không chỉ lọc tenant của parent.

### 24.3. `$lookup` khác `$unwind`

`$lookup` tạo array. `$unwind` biến các array elements thành nhiều documents. Nếu mục tiêu cuối là streams of rows, có thể dùng `$unwind`/`$project` nhưng không nên gom ngược mọi rows vào một array sau đó.

### 24.4. Join không có index

`$lookup` với foreign field không được index có thể rất chậm. Kiểm tra execution plan và index selectivity, đặc biệt với correlated subqueries. Đừng chỉ bật allowDiskUse để chữa join không có index.

### 24.5. Khi cần full history

Query `order_events` trực tiếp theo `order_id` và phân trang. Không bắt buộc join tất cả events vào order document chỉ vì API response có một order ID.

---

## 25. `$unwind`: explosion số dòng

Một input document có 50.000 array elements, sau `$unwind` thành 50.000 pipeline documents:

~~~javascript
db.orders.aggregate([
  { $unwind: "$items" }
]);
~~~

Nếu tiếp tục `$lookup` trên mỗi item, tổng operations có thể tăng theo cấp số nhân của các fan-out factors.

### 25.1. Phân biệt số documents và kích thước một document

`$unwind` có thể tăng tổng rows, memory/CPU/disk/time; nhưng mỗi unwound document có thể nhỏ hơn input. Lỗi không nhất thiết là 16 MiB per document.

### 25.2. Match trước/sau unwind

Nếu muốn lọc orders theo tenant và items theo sku:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenant_id: "tenant-a",
      "items.sku": "SKU-1"
    }
  },
  { $unwind: "$items" },
  {
    $match: {
      "items.sku": "SKU-1"
    }
  },
  {
    $project: {
      _id: 1,
      sku: "$items.sku",
      qty: "$items.quantity"
    }
  }
]);
~~~

`$match` đầu giảm parent docs, match sau unwind chỉ giữ matching elements.

### 25.3. Dùng `$filter` khi chỉ cần một mảng nhỏ

Với các documents có mảng hợp lý, `$filter` có thể chọn elements mà không tạo một row riêng cho từng element. Nhưng kết quả mảng vẫn phải bounded; không dùng `$filter` để gom vô hạn.

### 25.4. Không group lại thành `$push:"$$ROOT"` vô hạn

Nếu pipeline unwind 1 triệu elements rồi group lại một array 1 triệu objects, ta quay về lỗi ban đầu và còn tăng resource cost.

---

## 26. Cursor và phân trang: tránh một document khổng lồ

Nếu API cần lịch sử events:

~~~javascript
db.order_events.find({
  tenant_id: "tenant-a",
  order_id: "ORDER-101"
}).sort({
  at: -1,
  _id: -1
}).limit(50);
~~~

### 26.1. Cursor trả nhiều BSON documents

MongoDB cursor có thể trả nhiều batches. Giới hạn 16 MiB áp cho **mỗi document**, không phải toàn bộ lịch sử được đọc qua cursor.

### 26.2. Keyset pagination

Với sort theo `at DESC, _id DESC`, muốn lấy trang tiếp theo dựa trên giá trị cuối trang:

~~~javascript
const lastAt = ISODate("2026-11-13T10:00:00Z");
const lastId = "evt-900";

db.order_events.find({
  tenant_id: "tenant-a",
  order_id: "ORDER-101",
  $or: [
    { at: { $lt: lastAt } },
    {
      at: lastAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  at: -1,
  _id: -1
}).limit(50);
~~~

Ví dụ giả định `_id` là string có thứ tự ổn định. Nếu `_id` là ObjectId hoặc mixed types, paging token phải dùng đúng BSON type và sort semantics.

### 26.3. Vì sao skip lớn không lý tưởng?

`skip(1000000)` thường buộc server bỏ qua rất nhiều kết quả. Keyset pagination dùng index phù hợp sẽ tốt hơn với lịch sử rất dài.

### 26.4. Pagination token phải chứa tenant/filter/sort identity

Không cho client dùng token của tenant khác. Ký/check token hoặc lưu state phù hợp, kiểm tra sort order và snapshot consistency yêu cầu.

---

## 27. Pipeline output 16 MiB: trường hợp `$group` tạo một array

Ví dụ pipeline cần trả thống kê nhưng lại tạo:

~~~javascript
db.sales.aggregate([
  {
    $group: {
      _id: "$customer_id",
      invoices: {
        $push: "$$ROOT"
      }
    }
  }
]);
~~~

Mỗi `customer_id` trả một document chứa tất cả invoices của khách. Một customer lớn có thể vượt 16 MiB.

### 27.1. Sửa theo requirement

Nếu API chỉ cần tổng tiền và số invoice:

~~~javascript
db.sales.aggregate([
  {
    $group: {
      _id: "$customer_id",
      invoice_count: {
        $sum: 1
      },
      total_minor: {
        $sum: "$amount_minor"
      }
    }
  }
]);
~~~

Nếu cần 20 invoices gần nhất, nên query `sales` trực tiếp với `customer_id` index và limit hoặc dùng bounded top-N strategy.

### 27.2. Output document không nhất thiết bằng source document

Một collection không có document >1 MiB nhưng aggregation vẫn có thể tạo result >16 MiB bằng `$group` hoặc `$lookup`.

### 27.3. `$merge`/`$out` không làm một doc >16 MiB trở nên hợp lệ

Ghi aggregation result sang collection không bỏ giới hạn BSON per document. `$merge` phù hợp với **nhiều docs nhỏ, key rõ ràng**, ví dụ mỗi customer một summary scalar, không phải một giant array.

---

## 28. Materialized summary thay raw history

Nếu dashboard cần “doanh thu theo khách hàng”, tạo summary nhỏ:

~~~javascript
db.sales.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $group: {
      _id: {
        tenant_id: "$tenant_id",
        customer_id: "$customer_id"
      },
      paid_count: { $sum: 1 },
      total_minor: { $sum: "$amount_minor" }
    }
  },
  {
    $merge: {
      into: "customer_sales_summary",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
], {
  allowDiskUse: true
});
~~~

### 28.1. Vì sao tốt hơn `$push` toàn bộ invoices?

Một summary chứa count và total, không lớn tỷ lệ tuyến tính với số invoices. Raw invoices vẫn ở source collection để truy vấn lịch sử.

### 28.2. Freshness

Summary có thể stale nếu chỉ chạy daily job. Cần định nghĩa freshness SLA, incremental updates/change streams, reconciliation và cách xử lý deletes/late events.

### 28.3. Overflow kiểu số

`$sum` có semantics số tùy BSON numeric types; với tiền nên dùng NumberLong minor units hoặc Decimal128 theo business contract và kiểm tra overflow/precision.

### 28.4. Không xóa dữ liệu nguồn sớm

`$merge` tạo summary, không thay backup hay transaction ledger. Giữ raw data theo retention/audit policy.

---

## 29. Java Sync Driver: phân tích document size

Một ví dụ Java sử dụng aggregation `$bsonSize` để liệt kê top documents:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;
import java.util.concurrent.TimeUnit;

public class LargeDocumentDiagnostic {

    public static void inspect(MongoDatabase database) {

        MongoCollection<Document> orders =
            database.getCollection("orders");

        List<Document> pipeline = List.of(
            new Document("$project",
                new Document("_id", 1)
                    .append("tenant_id", 1)
                    .append("bson_bytes",
                        new Document(
                            "$bsonSize",
                            "$$ROOT"
                        )
                    )
            ),
            new Document("$sort",
                new Document("bson_bytes", -1)
            ),
            new Document("$limit", 20)
        );

        orders.aggregate(pipeline)
            .allowDiskUse(true)
            .maxTime(20, TimeUnit.SECONDS)
            .forEach(doc -> {
                System.out.println(
                    doc.get("_id")
                    + " bytes="
                    + doc.get("bson_bytes")
                );
            });
    }
}
~~~

### 29.1. Không gọi `into(new ArrayList<>())` cho dữ liệu vô hạn

Nếu aggregation trả 5 triệu records, việc collect hết vào List có thể làm JVM OOM. Duyệt cursor theo batch và xử lý/stream xuống output có giới hạn.

### 29.2. `maxTime` bảo vệ resource budget

`maxTime` giúp giới hạn thời gian thao tác trong điều kiện hỗ trợ; không sửa vấn đề data modeling và không bảo đảm query sẽ hoàn thành.

### 29.3. Query diagnostic cũng cần quyền và phạm vi

Chạy trên staging/sampled tenant hoặc off-peak, không quét toàn bộ collection lớn bất kỳ khi server đang quá tải. Không log raw sensitive document contents.

---

## 30. Spring Data MongoDB: bounded array update

Nếu chỉ giữ N event previews trong entity, có thể dùng `MongoTemplate`:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import java.util.Date;

public class RecentEventWriter {

    private final MongoTemplate template;

    public RecentEventWriter(MongoTemplate template) {
        this.template = template;
    }

    public void addPreview(
            String orderId,
            String tenantId,
            String eventId,
            String type) {

        Document preview = new Document()
            .append("event_id", eventId)
            .append("type", type)
            .append("at", new Date());

        Query query = Query.query(
            Criteria.where("_id").is(orderId)
                .and("tenant_id").is(tenantId)
        );

        Update update = new Update()
            .push("recent_events")
            .each(preview)
            .sort(
                org.springframework.data.domain
                    .Sort.by(
                        org.springframework.data.domain
                            .Sort.Direction.DESC,
                        "at"
                    )
            )
            .slice(100);

        template.updateFirst(
            query,
            update,
            "orders"
        );
    }
}
~~~

Ví dụ dùng collection name và BSON field names để tránh nhầm với Java property mapping. API `PushOperatorBuilder` phụ thuộc Spring Data version; xác nhận signatures bằng Javadoc của dự án khi áp dụng.

### 30.1. Tại sao không nhúng raw event?

Recent preview chỉ có `event_id`, `type`, `at`. Raw payload có thể được lưu ở `order_events` và preview là cache nhỏ.

### 30.2. Failure semantics

Nếu preview update fail nhưng raw event đã lưu, không nhất thiết mất dữ liệu; có thể rebuild preview từ source of truth. Thiết kế source-of-truth rõ ngay từ đầu.

### 30.3. `$slice` không thay dedup

Hai events cùng ID có thể cùng nằm trong preview nếu retry. Nếu cần uniqueness, xây projection lại theo source events/idempotency key hoặc dùng phù hợp `$addToSet` khi equality đủ đại diện.

---

## 31. Java Driver: xử lý lỗi thay vì retry vô hạn

Pseudo-service:

~~~java
public void appendEvent(Event event) {

    try {
        // Ghi event vào order_events bằng stable event ID.
        eventRepository.insertIfAbsent(event);

        // Cập nhật recent preview (best effort).
        orderPreviewRepository.appendBounded(event);

    } catch (RuntimeException ex) {

        // Không retry mù với $push:
        // có thể tạo duplicate và làm doc lớn hơn.
        // Lưu metrics và request/event ID để reconcile.
        throw ex;
    }
}
~~~

`Event`, `eventRepository` và `orderPreviewRepository` là các abstractions minh họa, không phải classes của MongoDB Driver.

### 31.1. Phân loại exception

- **Permanent/schema**: document quá lớn, invalid type, bad field name → sửa model/payload, không retry y nguyên.
- **Transient network/topology**: phân tích retryable semantics theo driver/operation.
- **Unknown write outcome**: query lại bằng stable event ID/operation ID.
- **Insufficient permission**: sửa privilege/config, không retry dồn dập.
- **Aggregation memory**: tối ưu pipeline hoặc spill nếu phù hợp.

### 31.2. Đừng tự động cắt dữ liệu âm thầm

Nếu một payment event không lưu được, không chỉ bỏ `details` và trả success khi dữ liệu bắt buộc đã mất. Tách error handling theo criticality và retention policy.

---

## 32. Runbook khi insert/update báo BSON document quá lớn

### Bước 1 — Đánh giá mức độ

- Có ảnh hưởng mọi requests hay một tenant/document?
- Dữ liệu nguồn có bị mất hay vẫn nằm trong queue?
- Ứng dụng có retry storm gây thêm tải?
- Lỗi bắt đầu từ release/schema nào?
- Tính năng nào đang append nhiều?

### Bước 2 — Ổn định hệ thống

- Giảm/tạm dừng writer append rủi ro bằng feature flag nếu cho phép.
- Đặt retry backoff và dead-letter/quarantine.
- Không tăng worker concurrency để “vượt lỗi”.
- Không xóa dữ liệu lịch sử trước khi có backup/copy.

### Bước 3 — Xác định document

- Ghi ID/tenant đã được phép.
- `$bsonSize` của document.
- Kiểm tra `$size` của arrays chủ chốt.
- Xác định phần nào tăng nhanh: events, attachments, snapshots, comments.
- So sánh với baseline/bản ghi khác.

### Bước 4 — Phân loại khắc phục

- File/blob → GridFS/object storage.
- One-to-many vô hạn → referenced collection.
- Recent items → bounded array.
- Summary/report → scalar materialization.
- Ghi trùng vì retry → idempotency.
- Raw payload quá lớn → validate/reject/store externally.

### Bước 5 — Thử nghiệm trên staging

Copy representative document, thực hiện migration và read/write tests. Đảm bảo ứng dụng cũ/mới không phá field/array mới.

### Bước 6 — Migration có kiểm soát

Backfill child documents, verify counts/values, chuyển writer ownership, cắt mảng legacy sau approval, kiểm tra rollback.

### Bước 7 — Theo dõi

Đo p95/p99 document size, error count, write latency, replication lag, CPU/IO, queue backlog và failure recovery.

---

## 33. Runbook khi aggregation vượt memory

### Bước 1 — Tìm stage gây lỗi

Đọc stack trace/server profiler log và pipeline execution context. Kiểm tra:

- `$sort` không có index?
- `$group` có `$push:"$$ROOT"`?
- `$facet` gom arrays không giới hạn?
- `$lookup` nhiều matches?
- `$unwind` nhân rows?
- `$setWindowFields` giữ state lớn?
- Có hàng nghìn pipeline stages sinh động?

### Bước 2 — Xác định loại giới hạn

- `BSONObjectTooLarge` → size của một result document.
- `ExceededMemoryLimit` → stage/accumulator/per-op.
- `$facet` output limit → facet cannot spill.
- `sort no disk` → có thể xử lý bằng index/top-k/spill.
- `1000 stages` → structural pipeline issue.

### Bước 3 — Thử thay đổi rủi ro thấp

- Đặt `$match` sớm.
- Thêm index hỗ trợ filter/sort.
- Chỉ project fields cần.
- Thêm limit **đúng semantics**.
- Giảm join cardinality/foreign projection.
- Dùng pagination/cursor thay array lớn.
- Chỉ bật allowDiskUse khi stage hỗ trợ và storage budget đủ.

### Bước 4 — Đổi output shape

Nếu API thật sự cần history, trả paginated rows. Nếu chỉ cần statistics, trả counts/sums/top-N. Nếu dashboard cần precomputed results, dùng materialized views.

### Bước 5 — Test tải thực

Dataset lab nhỏ khó tái hiện large-group cardinality hoặc p99 memory. Dùng staging gần production, đo peak memory, spill, disk I/O, latency và error rate.

---

## 34. Quan sát bằng explain, profiler và logs

### 34.1. Explain pipeline

~~~javascript
db.order_events.explain("executionStats").aggregate([
  {
    $match: {
      tenant_id: "tenant-a",
      order_id: "ORDER-101"
    }
  },
  {
    $sort: {
      at: -1
    }
  },
  { $limit: 50 }
]);
~~~

Kiểm tra plan/index, documents examined, keys examined, stage behavior. Cấu trúc explain thay đổi theo server/version.

### 34.2. `usedDisk`

MongoDB profiler/diagnostic log có thể ghi chỉ báo `usedDisk` nếu một stage ghi temporary files vì memory pressure. Theo dõi tần suất và độ lớn spill trong workload nặng.

### 34.3. Không bật profiler mức cao tràn lan

Profiler có thể tăng overhead và ghi sensitive query parameters. Chỉ bật theo quy trình SRE với thời gian/scope cụ thể, chú ý Atlas/managed limitations.

### 34.4. ServerStatus (khi có và đủ quyền)

Các bản server mới có query memory metrics như:

~~~text
metrics.query.peakMemoryUsageOperation
metrics.query.operationsFailedDueToMemoryLimit
metrics.query.configuredMaxMemoryUsageBytesPerOperation
~~~

Không mặc định mọi phiên bản có toàn bộ fields này. Dùng `db.serverStatus()` với quyền phù hợp và kiểm tra docs release.

### 34.5. App metrics

| Metric | Ý nghĩa |
|---|---|
| `bson_document_size_bytes_p95` | Độ lớn document phổ biến cao |
| `bson_document_size_bytes_max` | Tail rủi ro |
| `unbounded_array_length_p99` | Array đang tăng tới đâu |
| `bson_too_large_errors_total` | Ghi/aggregate thất bại |
| `aggregation_memory_errors_total` | Stage memory errors |
| `aggregation_spill_queries_total` | Queries phải spill |
| `aggregation_timeout_total` | Queries không hoàn thành |
| `bulk_retry_count` | Retry storm |
| `large_document_migration_backlog` | Records cần chuyển |
| `event_ingest_lag_seconds` | Dữ liệu nguồn còn pending |
| `orders_update_latency_p99` | Write contention |
| `replica_lag_seconds` | Áp lực replication |

Tên metrics là minh họa cho instrumentation, không phải MongoDB built-in metric names.

---

## 35. Phân biệt kích thước result và API response

### 35.1. Tình huống 1: MongoDB result hợp lệ, HTTP trả 413

Nếu API gom 10.000 documents nhỏ thành một JSON response lớn, MongoDB có thể trả cursor hợp lệ, nhưng reverse proxy/API gateway giới hạn response size.

### 35.2. Tình huống 2: MongoDB result document đã vượt 16 MiB

Một `$group` gom 10.000 records thành một array trong **một document** có thể thất bại ở MongoDB trước khi HTTP response được tạo.

### 35.3. Tình huống 3: Java client OOM

Ứng dụng gọi:

~~~java
List<Document> all = collection.find()
    .into(new ArrayList<>());
~~~

Dù mỗi document hợp lệ, toàn bộ cursor đổ vào một List có thể vượt JVM heap. Dùng cursor streaming và pagination thay vì eager materialization.

### 35.4. Tình huống 4: GUI shell hiển thị bị cắt

Một MongoDB GUI hoặc mongosh có thể truncate output hiển thị. Điều đó **không chứng minh database cắt mất dữ liệu**. Kiểm tra raw BSON/query result và log của client tương ứng.

### 35.5. Sửa đúng tầng

Không tăng giới hạn gateway để chữa `BSONObjectTooLarge` của một document; không bật `allowDiskUse` để chữa Java heap OOM do List.

---

## 36. Migration từ giant array sang collection: kế hoạch an toàn

Giả sử `orders.events` đã phình tới 14 MiB.

### Giai đoạn 0 — Inventory và nguồn đúng

- Xác định writers nào append event.
- Xác định readers nào lấy `orders.events`.
- Kiểm tra có event ID duy nhất hoặc cách tạo stable ID.
- Lấy backup/snapshot và thử restore.
- Xác định retention/legal hold.
- Kiểm tra MongoDB version/topology.

### Giai đoạn 1 — Mở rộng code

- Writers mới ghi events vào `order_events` collection.
- Readers mới có thể đọc cả legacy embedded và collection mới.
- Có cơ chế tránh double-count khi event tồn tại ở cả hai.
- Nếu writers cũ vẫn append vào array, phải giữ compatibility window + catch-up strategy.
- Không xóa legacy events sớm.

### Giai đoạn 2 — Backfill từng order

- Đọc order với projection phù hợp.
- Enumerate legacy events.
- Tạo stable `event_id`, không tạo random ID mới mỗi lần retry.
- Upsert theo `event_id`/business identity.
- Ghi checkpoint theo order/batch, không nhúng marker vào document gần 16 MiB.
- Throttling, checkpoint, metrics.

### Giai đoạn 3 — Catch-up

- Chặn/loại bỏ old writers.
- Đọc và copy các events được thêm sau backfill.
- Đối soát event IDs, counts và fields, không chỉ tổng đếm.
- Dùng Change Streams/outbox nếu cần online sync, xử lý lag/duplicate/restart.

### Giai đoạn 4 — Cutover

- API đọc from `order_events`, có pagination.
- Bounded `recent_events` có thể được dựng lại từ collection.
- Kiểm tra latency, consistency, permissions và search/index.

### Giai đoạn 5 — Contract

- Chỉ sau business sign-off mới remove legacy array.
- Nếu cần giữ audit, có bản lưu đáp ứng retention.
- Loại bỏ index/code/flag cũ theo quy trình.
- Giữ rollback path trong khoảng đã thỏa thuận.

---

## 37. Backfill events idempotent: ví dụ mongosh

Giả định legacy array elements có field `id` ổn định. Với một order nhỏ trong lab:

~~~javascript
const order = db.orders.findOne(
  { _id: "ORDER-101", tenant_id: "tenant-a" },
  { events: 1, tenant_id: 1 }
);

if (order && Array.isArray(order.events)) {
  for (const event of order.events) {
    if (!event.id) {
      throw new Error("Legacy event missing stable id");
    }

    db.order_events.updateOne(
      {
        _id: event.id
      },
      {
        $setOnInsert: {
          tenant_id: order.tenant_id,
          order_id: order._id,
          type: event.type,
          at: event.at,
          payload: event.payload
        }
      },
      {
        upsert: true
      }
    );
  }
}
~~~

### 37.1. Giới hạn của ví dụ

- Chỉ minh họa cơ chế idempotency bằng stable event ID.
- Không xử lý toàn collection hoặc hàng trăm nghìn events trong một call.
- Chưa giải quyết event ID collision giữa các tenants; có thể cần composite/stable `_id` và unique index.
- Nếu source event thiếu ID, phải thiết kế deterministic identity từ source ordering/payload và kiểm tra collision, không tùy tiện hash payload rồi coi mọi identical events là duplicates.
- Không catch-up updates đồng thời.
- Không có bulk error classification/checkpoint.
- `$setOnInsert` không tự cập nhật event khi source sửa nội dung; phải định nghĩa event immutability/repair contract.

### 37.2. Production nên dùng batches

Đọc theo order/tenant, ghi bulk theo chunk hữu hạn, lưu operation IDs và checkpoints; theo dõi failures. Retry toàn batch chỉ an toàn nếu operation idempotent và bảo vệ uniqueness.

### 37.3. Không `$unset events` trước đối soát

Nếu xóa legacy array rồi mới phát hiện một event copy lỗi, có thể mất lịch sử. Luôn kiểm tra completeness/consistency trước khi remove.

---

## 38. Khi document đã không thể cập nhật do quá lớn

### 38.1. Ghi thêm field không phải cách chữa

Nếu document đã gần 16 MiB, thêm `needs_migration:true` có thể lỗi. Dùng migration-control collection riêng, không tăng payload của document đang cần cứu.

### 38.2. Cần giảm dữ liệu đang nhúng

Có thể remove một field hoặc truncate array **sau khi** đã sao lưu/chuyển dữ liệu cần giữ. Đừng xóa dữ liệu để đưa service hoạt động trở lại nếu chưa xác định hậu quả business/audit.

### 38.3. Concurrency khi xóa field cũ

~~~text
T1 Backfill đọc events=[E1..E100]
T2 Old writer append E101
T3 Migration unset events
-> E101 có thể bị mất.
~~~

Giải pháp: stop/drain old writer, capture delta và final reconciliation, hoặc thiết kế CAS/version/transaction theo topology. Không chỉ dựa vào thời điểm “backfill xong”.

### 38.4. Không restore snapshot toàn database chỉ vì một document lỗi

Restore toàn bộ deployment có thể mất writes hợp lệ mới ở unrelated collections. Chỉ sử dụng theo incident/backup plan có RPO/RTO và approval.

### 38.5. Immutable source history

Nếu raw events là ledger quan trọng, preserve source copy/chunk checksums và thử đọc lại trước khi xóa. Giữ audit của migration.

---

## 39. Cảnh báo về sharded cluster

### 39.1. Sharding không tăng giới hạn 16 MiB per document

Sharding chia **nhiều documents** qua shards. Một document 20 MiB vẫn không trở thành hợp lệ vì collection đã sharded.

### 39.2. Hot single-document vẫn là hotspot

Một order có hàng triệu events vẫn nằm trong một document/shard. Tăng số shards không tự phân tán writes vào một document.

### 39.3. Referential collection dễ phân phối hơn

Khi tách events thành documents riêng, shard key/indexes phải phù hợp query và tenant isolation. Không chọn shard key ngẫu nhiên chỉ để tránh hotspot mà khiến query toàn cluster.

### 39.4. `$lookup` và aggregation cross-shard

Joins/aggregations có thể đi qua mongos và shards, tăng fan-out/network. Kiểm tra explain, data placement và phiên bản server. Không suy performance local replica set giống production sharded.

### 39.5. Backup và migration consistency

Copy dữ liệu giữa collections trên sharded cluster cần kiểm soát writes đang tiếp tục, transactions hoặc CDC/reconciliation, không tự đảm bảo consistent snapshot toàn cluster khi dùng nhiều cursor không có protocol.

---

## 40. Bảo mật, độ tin cậy và vận hành

### 40.1. Payload vô hạn từ client

Một API nhận array tùy ý từ client có thể bị lạm dụng gây document growth/DoS. Giới hạn request size, số elements, nested depth và fields.

### 40.2. Không log toàn bộ giant document

In `Document.toJson()` vào application logs có thể tạo log hàng MiB, lộ PII/tokens và làm log pipeline quá tải. Log IDs, size, count, status, bounded sample đã redacted.

### 40.3. Không tăng memory/internal server parameters bừa

Nâng giới hạn memory có thể khiến operations cạnh tranh toàn cluster và OOM node, đặc biệt khi nhiều concurrent pipelines. Ưu tiên giảm cardinality/index, phân trang và materialization.

### 40.4. Guardrail tenant

Các truy vấn chẩn đoán/migration phải có tenant authorization. Trong production không xuất sample documents ra logs/tickets công khai.

### 40.5. Backpressure

Nếu job append thất bại vì document size, hãy tách queue/durable dead letter, giới hạn retry và cho phép repair. Không để infinite loop tạo retry storm.

### 40.6. Version compatibility

Các tính năng như update pipelines, `$bsonSize`, GridFS driver APIs và các aggregation accumulators có yêu cầu server/driver versions. Kiểm tra hỗ trợ trước khi đưa đoạn ví dụ vào production.

---

## 41. Checklist xử lý sự cố document quá lớn

### 41.1. Phân loại sự cố

- [ ] Đã xác định error class/message/stack trace.
- [ ] Xác định operation insert/update/aggregate/read/client.
- [ ] Có server/driver version.
- [ ] Có request/tenant/document ID đúng quyền.
- [ ] Đã loại trừ lỗi gateway/Java heap.
- [ ] Biết nguồn dữ liệu và business criticality.

### 41.2. Chẩn đoán kích thước

- [ ] Đo `$bsonSize:"$$ROOT"` cho document/nhóm nghi ngờ.
- [ ] Đo array counts có `$isArray` guard.
- [ ] Đo p95/p99/max hoặc top-N sample.
- [ ] Kiểm tra avgObjSize không che tail.
- [ ] Xác định field/array/payload tăng nhanh.
- [ ] Kiểm tra retry duplicates và write rate.
- [ ] Không quét toàn collection quá tải trong incident.

### 41.3. Khắc phục

- [ ] Không tiếp tục append dữ liệu làm doc phình.
- [ ] Có backup và xác nhận retention.
- [ ] Chọn bounded array/references/buckets/GridFS đúng use case.
- [ ] Thiết kế idempotency/unique IDs.
- [ ] Có migration, checkpoint, catch-up và reconcile.
- [ ] Không xóa legacy field trước khi verify.
- [ ] Không phá ứng dụng cũ trong rollout.
- [ ] Đặt quota thấp hơn 16 MiB và metrics cảnh báo.

---

## 42. Checklist xử lý pipeline vượt giới hạn

- [ ] Phân biệt result doc >16 MiB, stage memory, facet, accumulator hoặc stage count.
- [ ] Có full pipeline và explain phù hợp.
- [ ] Không log secrets/raw PII trong pipeline.
- [ ] `$match` sớm và đúng semantics.
- [ ] Có index cho filter/sort/join.
- [ ] `$sort + $limit` được đặt đúng.
- [ ] `$lookup` có hạn chế fan-out/foreign projection.
- [ ] Không `$group` gom mọi `$$ROOT` vào array nếu chỉ cần count/sum.
- [ ] Không `$facet` chứa unlimited arrays.
- [ ] `allowDiskUse` chỉ dùng khi stage hỗ trợ và disk budget đủ.
- [ ] Theo dõi usedDisk/per-operation memory nếu version hỗ trợ.
- [ ] Có maxTimeMS và query timeout policy.
- [ ] Kết quả dùng cursor/pagination khi data nhiều.
- [ ] Không collect toàn bộ cursor vào JVM heap.
- [ ] Stage count dưới 1.000.
- [ ] Test trên workload/cardinality đại diện production.

---

## 43. Những hiểu lầm thường gặp

**Sai lầm 1:** “Collection MongoDB tối đa 16 MiB.”  
Không. 16 MiB áp cho **mỗi BSON document**.

**Sai lầm 2:** “MongoDB query chỉ trả tối đa 16 MiB tổng cộng.”  
Cursor có thể trả nhiều documents trong nhiều batches; từng document vẫn chịu giới hạn.

**Sai lầm 3:** “Tăng batchSize giúp trả một document 20 MiB.”  
Không; batchSize không sửa giới hạn document.

**Sai lầm 4:** “Bật allowDiskUse làm BSON limit thành 100 MB.”  
Không. Disk spill khác document size.

**Sai lầm 5:** “`$facet` sẽ spill nếu bật allowDiskUse.”  
Không; facet có giới hạn riêng.

**Sai lầm 6:** “`$group` spill thì `$push` accumulator cũng spill vô hạn.”  
Không; accumulator array có hạn mức riêng.

**Sai lầm 7:** “Không có document lớn trong collection thì aggregation không thể tạo document lớn.”  
`$group` và `$lookup` có thể tạo output rất lớn.

**Sai lầm 8:** “`$addToSet` ngăn mảng tăng.”  
Chỉ tránh thêm exact duplicate values; giá trị mới không giới hạn.

**Sai lầm 9:** “Giới hạn số phần tử đủ giữ dưới 16 MiB.”  
Một phần tử quá lớn vẫn có thể làm lỗi.

**Sai lầm 10:** “Sharding giúp một document 20 MiB hợp lệ.”  
Không; sharding chỉ phân tán nhiều documents.

**Sai lầm 11:** “GridFS có thể dùng thay arbitrary embedded document.”  
GridFS dành cho file-like binary, không phải mọi schema.

**Sai lầm 12:** “Có thể dùng một parent document làm audit log mãi mãi.”  
Unbounded append dễ tạo size/hotspot.

**Sai lầm 13:** “`$slice` là backup log.”  
Nó xóa entries cũ khỏi bounded array.

**Sai lầm 14:** “`$pull` bỏ events có thể chạy tùy tiện để chữa lỗi.”  
Có nguy cơ mất audit/business data.

**Sai lầm 15:** “`avgObjSize` nhỏ nên không có outlier.”  
Average có thể che top documents rất lớn.

**Sai lầm 16:** “`$unwind` chỉ làm nhỏ output.”  
Có thể nhân rows lên rất lớn, làm query tốn tài nguyên.

**Sai lầm 17:** “`$lookup` không cần index nếu bật disk.”  
Join thiếu index vẫn có thể chậm nghiêm trọng.

**Sai lầm 18:** “`$limit` ở bất cứ đâu cũng giữ kết quả giống nhau.”  
Đặt trước `$sort`/`$group` có thể đổi semantics.

**Sai lầm 19:** “`$group` luôn cần giữ mọi raw records.”  
Nhiều report chỉ cần `$sum`/`$count`/scalars.

**Sai lầm 20:** “`$facet` cho pagination vô hạn an toàn.”  
Facet arrays vẫn có giới hạn.

**Sai lầm 21:** “MongoDB server memory error nghĩa Java thiếu heap.”  
Đó là hai tầng khác nhau.

**Sai lầm 22:** “Client OOM chứng minh server BSON limit thấp.”  
Có thể do collect toàn cursor trong JVM.

**Sai lầm 23:** “HTTP 413 nghĩa MongoDB không lưu được document.”  
Có thể là proxy/API limit.

**Sai lầm 24:** “Retry cùng `$push` sẽ tự hồi phục.”  
Có thể tăng duplicates/tải và làm lỗi nặng hơn.

**Sai lầm 25:** “Backfill xong có thể xóa legacy array ngay.”  
Cần drain old writers và final reconciliation.

**Sai lầm 26:** “Một document gần max vẫn thêm migration metadata được.”  
Có thể không còn đủ bytes.

**Sai lầm 27:** “Một unique event ID trong subdocument được `$addToSet` enforce.”  
Không unique theo subfield.

**Sai lầm 28:** “maxTimeMS làm query hết memory trở thành hợp lệ.”  
Nó giới hạn thời gian, không sửa hình dạng dữ liệu.

**Sai lầm 29:** “Bật profiler toàn cluster trong incident không có chi phí.”  
Có thể tăng overhead và lộ thông tin.

**Sai lầm 30:** “Không có lỗi sau fix là đã xong.”  
Cần theo dõi kích thước, backlog, correctness và data loss.

---

## 44. Bài tập thực hành

### Bài 1 — Đo BSON bytes

Tạo ba documents kích thước khác nhau, dùng `$bsonSize:"$$ROOT"` để lấy bytes từng document.

### Bài 2 — JSON vs BSON

Tạo string Unicode tiếng Việt và một ObjectId; giải thích vì sao `JSON.stringify().length` không bằng BSON bytes.

### Bài 3 — Tìm top-20

Tìm 20 documents lớn nhất trong lab, có `_id`, `bson_bytes`, sort descending.

### Bài 4 — Array length

Một số documents thiếu `audit_events`, một số có array, một document có field sai kiểu. Dùng `$isArray`, `$size` để chẩn đoán mà không lỗi.

### Bài 5 — Simulate growth

Append 1.000 events vào một order trong lab theo batches nhỏ; đo size/count sau mỗi batch. Không tạo blob 16+ MiB trên production.

### Bài 6 — Bounded push

Giữ 100 events gần nhất với `$push + $each + $sort + $slice`. Test khi append 120 events.

### Bài 7 — Duplicate events

Dùng `$addToSet` với hai events cùng event_id nhưng timestamp khác; giải thích vì sao cả hai có thể tồn tại.

### Bài 8 — Data model

Chuyển model order chứa 100.000 events sang `orders` + `order_events`. Viết indexes cho list/history.

### Bài 9 — Pagination

Lấy 50 events mới nhất, sau đó keyset page kế tiếp bằng `at + _id`.

### Bài 10 — GridFS

Tạo file giả 20 MiB trong lab và upload qua GridFS. Giải thích vì sao không dùng một BSON document.

### Bài 11 — 1.000 stages

Sinh pipeline nhiều `$addFields` trong chương trình test, đếm stages và đề xuất cách hợp nhất thay vì vượt giới hạn.

### Bài 12 — Sort memory

So sánh aggregation `$sort` trên field chưa index và indexed field bằng explain.

### Bài 13 — Sort + limit

Tìm top 50 events của tenant. Phân tích vì sao `$sort → $limit` khác `$limit → $sort`.

### Bài 14 — Group accumulator

Tạo một group có nhiều events. So sánh `$push:"$$ROOT"` với `$sum:1` về kích thước state/output.

### Bài 15 — Facet

Tạo facet với arrays không giới hạn, rồi chuyển thành facet page 20 + scalar count. Giải thích giới hạn 100MB/16MiB.

### Bài 16 — Lookup fan-out

Một order có nhiều foreign events. Viết `$lookup` pipeline lấy tối đa 10 events, project fields nhỏ và tạo index.

### Bài 17 — Unwind

Một document có 100 elements. `$unwind` tạo bao nhiêu rows? Thêm `$match` trước/sau để chỉ giữ SKU mong muốn.

### Bài 18 — Cursor trong Java

Duyệt 100.000 documents bằng `forEach`/cursor streaming, không gọi `into(new ArrayList<>())`.

### Bài 19 — BSON 16MiB vs response limit

Thiết kế hai lỗi: một MongoDB aggregate tạo result doc quá lớn; một API trả nhiều documents nhỏ nhưng gateway từ chối response. Nêu giải pháp khác nhau.

### Bài 20 — Retention

Thiết kế dữ liệu recent notification (100 gần nhất) và full notification log (30 ngày), dùng bounded array và events collection/TTL theo domain.

### Bài 21 — Migration idempotency

Backfill embedded events vào collection với stable event IDs và `$setOnInsert`, chạy lại không sinh trùng.

### Bài 22 — Migration race

Trong khi backfill, một writer cũ append event mới. Đề xuất drain + catch-up + final reconciliation trước khi `$unset` legacy field.

### Bài 23 — Data quality

Một embedded event thiếu ID, timestamp là string hoặc payload sai kiểu. Đưa vào error queue/review thay vì tự gán ID tùy tiện.

### Bài 24 — Monitoring

Thiết kế dashboard p95/p99/max BSON bytes, array length, memory errors, spill, p99 write latency và migration backlog.

### Bài 25 — Security

Một API nhận user input dưới dạng events array. Thiết kế max elements, max bytes, allowed fields, tenant filter và redacted logs.

### Bài 26 — Transaction/outbox

Khi tách event khỏi parent, thiết kế transactional outbox hoặc idempotent eventual consistency để không mất event sau crash.

### Bài 27 — Materialized view

Thay `$group + $push all invoices` bằng summary per customer chứa count và total.

### Bài 28 — Sharded cluster

Giải thích vì sao tăng shards không làm một order document 20 MiB hợp lệ; thiết kế shard key cho collection events.

### Bài 29 — Incident drill

Giả lập MongoDB trả lỗi document-too-large khi ghi event. Viết runbook thu thập bằng chứng, ổn định, phân loại, khôi phục và prevent recurrence.

### Bài 30 — Pipeline triage

Một pipeline chứa `$lookup`, `$unwind`, `$group`, `$facet` rồi lỗi. Đo cardinality/bytes sau từng phần và đề xuất pipeline mới bounded.

---

## 45. Câu hỏi ôn tập

1. BSON document tối đa bao nhiêu MiB và bao nhiêu bytes?
2. Vì sao không dùng độ dài JSON string làm BSON size?
3. Giới hạn per-document khác giới hạn collection như thế nào?
4. MongoDB có giới hạn nesting depth không?
5. Tại sao một array không có max elements cố định chung?
6. `$bsonSize` trả kết quả theo đơn vị gì?
7. `$bsonSize:"$$ROOT"` khác `$size:"$events"` ở đâu?
8. Vì sao cần `$isArray` trước `$size` trong data bẩn?
9. Vì sao `avgObjSize` không chứng minh không có outlier?
10. Những lỗi nào thường chỉ ra BSONObjectTooLarge?
11. Insert/update và aggregate có thể cùng phát lỗi size nhưng khác nguồn gốc thế nào?
12. `$push` tạo field mới khi field missing không?
13. Nếu field là string, `$push` có tự convert thành array không?
14. `$addToSet` ngăn duplicate theo gì?
15. Vì sao `$addToSet` không ngăn audit array tăng?
16. `$slice:100` khác `$slice:-100` thế nào?
17. `$sort` trong `$push` có tác dụng gì?
18. Vì sao bounded count chưa bảo đảm dưới 16 MiB?
19. Khi nào nên embed?
20. Khi nào nên tách child documents ra collection riêng?
21. Bounded bucket khác unbounded parent array thế nào?
22. GridFS dùng giải quyết loại vấn đề nào?
23. GridFS có làm arbitrary BSON document 100 MiB hợp lệ không?
24. Sharding có tăng giới hạn document không?
25. Vì sao một hot document có thể gây contention?
26. Aggregation result 16 MiB khác stage memory 100 MB thế nào?
27. Aggregation pipeline có giới hạn số stages bao nhiêu?
28. Vì sao builder sinh 1.001 stages nên được refactor?
29. `allowDiskUseByDefault` từ MongoDB 6.0 có vai trò gì?
30. `allowDiskUse:true` giúp các stages nào?
31. Vì sao `allowDiskUse` không sửa `$facet`?
32. `$facet` có hai mức giới hạn nào?
33. `$group` có thể spill nhưng `$push` accumulator vẫn lỗi vì sao?
34. Khi nào cần `$sum` thay `$push:"$$ROOT"`?
35. `$lookup` tạo ra array field nào về mặt semantics?
36. Vì sao lookup fan-out có nguy cơ làm output lớn?
37. Foreign index có ý nghĩa gì với lookup?
38. `$unwind` tác động số lượng pipeline documents thế nào?
39. Vì sao match sớm thường giảm tài nguyên?
40. Vì sao `$limit` trước `$sort` có thể sai kết quả?
41. Cursor nhiều documents có bị 16 MiB tổng không?
42. Keyset pagination có lợi gì so với skip lớn?
43. Vì sao `$merge` không lưu được một output document vượt 16 MiB?
44. Java `into(new ArrayList<>())` có thể gây lỗi gì?
45. `maxTimeMS` có tăng memory limit không?
46. Vì sao bật profiler thiếu kiểm soát có thể gây rủi ro?
47. Unknown write outcome cần retry như thế nào?
48. Vì sao `$push` retry dễ sinh duplicates?
49. Migration events cần stable event IDs để làm gì?
50. Vì sao không xóa legacy array ngay sau initial backfill?
51. Vì sao migration marker nên lưu ngoài document gần 16 MiB?
52. Làm sao xử lý event mới do writer cũ tạo trong lúc migration?
53. Những metrics nào dự báo document size incident?
54. Khi nào nên dùng materialized counters thay gom raw history?
55. Phân biệt MongoDB BSON error, client heap OOM và gateway 413?
56. Cần test gì trên staging để kiểm chứng pipeline fix?
57. Vì sao index nhiều cũng có thể làm write chậm?
58. Kế hoạch retention có thể giảm document growth thế nào?
59. Những dữ liệu nào không được tùy tiện truncate?
60. Khi nào sự cố được coi là đã khắc phục hoàn toàn?

---

## 46. Tổng kết

Ba nhóm giới hạn trong bài có nguyên nhân và hướng sửa khác nhau:

1. **Document quá lớn (16 MiB):** kiểm tra `$bsonSize`, xác định field/array tăng trưởng, giới hạn payload, áp bounded arrays chỉ cho dữ liệu gần đây, hoặc chuyển sang referenced collections/buckets/GridFS theo đúng kiểu dữ liệu.
2. **Mảng tăng không giới hạn:** xử lý từ **data modeling và vòng đời dữ liệu**, không chỉ đổi `$push` thành `$addToSet`. Cần event ID, uniqueness, pagination, retention và migration có thể chạy lại.
3. **Aggregation pipeline vượt giới hạn:** phân biệt stage count 1.000, memory/spill, `$facet` non-spill, `$group` accumulator growth và result BSON 16 MiB. Giảm cardinality, dùng index, filter/projection/limit hợp lý, tránh gom mọi raw documents vào một output array.

Một chiến lược ứng cứu có trách nhiệm cần:

- Dừng retry/write path gây khuếch đại sự cố.
- Đo **kích thước và cardinality thực tế**.
- Không xóa audit/ledger dữ liệu để né lỗi nếu chưa lưu và đối soát.
- Chuyển long-lived unbounded data sang model có thể mở rộng.
- Sử dụng `allowDiskUse` chỉ khi phù hợp với **loại giới hạn thực tế**.
- Thử migration/cutover/rollback trên staging.
- Giám sát p95/p99/max size, spill, latencies, backlog và application correctness sau khi sửa.

**Thông điệp vận hành:** MongoDB hỗ trợ những collections và workloads rất lớn, nhưng **một document không nên được thiết kế để tăng vô hạn**, và **một aggregation result không nên gom toàn bộ lịch sử thành một BSON object duy nhất**.

## Tài liệu MongoDB chính thức

- [MongoDB Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Documents — Document Size Limit](https://www.mongodb.com/docs/manual/core/document/)
- [MongoDB Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB `$bsonSize`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonsize/)
- [MongoDB `$binarySize`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/binarysize/)
- [MongoDB `$push` Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/push/)
- [MongoDB `$addToSet` Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/addToSet/)
- [MongoDB Array Update Operators](https://www.mongodb.com/docs/manual/reference/operator/update-array/)
- [MongoDB `$group` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB `$facet` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/)
- [MongoDB `$lookup` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB `$unwind` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/)
- [MongoDB `$sort` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/)
- [MongoDB `$limit` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/limit/)
- [MongoDB Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB `$merge` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/)
- [MongoDB GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
- [MongoDB Java Sync Driver — GridFS](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/)
- [Spring Data MongoDB — Template CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)

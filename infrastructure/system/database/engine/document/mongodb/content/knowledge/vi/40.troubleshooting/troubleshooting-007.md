# Aggregation thiếu bộ nhớ, tràn ra đĩa và giới hạn của từng stage trong MongoDB

## 1. Khi báo cáo chạy được ở local nhưng thất bại trên production

Một nền tảng tin đăng cho thuê nhà lưu hàng chục triệu sự kiện lượt xem. Để lập báo cáo, developer viết aggregation:

~~~javascript
db.listingViews.aggregate([
  { $match: { createdAt: { $gte: ISODate("2026-11-01") } } },
  { $sort: { createdAt: -1 } },
  {
    $group: {
      _id: "$tenantId",
      allEvents: { $push: "$$ROOT" }
    }
  }
]);
~~~

Trên 1.000 events nó chạy tốt. Ở quy mô thật, truy vấn có thể bị **ExceededMemoryLimit**, **QueryExceededMemoryLimitNoDiskUseAllowed**, vượt kích thước BSON, bị timeout hoặc chậm vì ghi dữ liệu trung gian ra disk. Sửa tạm bằng **allowDiskUse: true** có khi giúp hoàn thành, nhưng có khi vẫn thất bại và gây áp lực I/O cho toàn cụm.

Vấn đề không chỉ là thiếu RAM. Một truy vấn aggregation có thể:

- Cần **blocking state** để sort/group/window.
- Có khả năng **spill** state ra temporary files khi được cho phép.
- Dùng **accumulator hoặc stage không hỗ trợ spill**.
- Tạo **một BSON output document quá lớn**.
- Tạo nhiều stages hoặc dùng tổng memory vượt các giới hạn theo phiên bản.
- Tăng network/disk usage và khiến các API khác vượt SLO dù vẫn trả kết quả.

Đây là bài học xử lý sự cố: tìm đúng nguồn áp lực, thay đổi query shape khi cần, và kiểm chứng kết quả nghiệp vụ không bị biến dạng sau tối ưu.

### Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt streaming stages và blocking stages.
2. Hiểu giới hạn 100 MB theo stage, 16 MiB cho output BSON document, tối đa 1.000 stages, accumulator-specific limits và per-operation limit theo server version.
3. Sử dụng allowDiskUse và hiểu allowDiskUseByDefault từ MongoDB 6.0.
4. Phân tích memory behavior của $sort, $group, $facet, $bucket, $bucketAuto, $sortByCount, $setWindowFields, $lookup và $graphLookup.
5. Chẩn đoán bằng explain, usedDisk, profiler/logs, serverStatus và disk telemetry.
6. Áp dụng $match, projection, index, top-K, bounded arrays và partitioning đúng nghiệp vụ.
7. Thiết kế maxTimeMS, batchSize và report-job concurrency phù hợp.
8. Thực hành mongosh với dữ liệu tổng hợp nhỏ, không cố ép server cạn RAM.
9. Lập runbook đầy đủ: phát hiện, cô lập, giảm tải, sửa, xác minh và phòng ngừa.

> **Phạm vi và cảnh báo:** MongoDB thay đổi một số hạn mức và execution details theo phiên bản. Bài này tách rõ những điểm từ **6.0** và **9.0**, đồng thời dùng tài liệu MongoDB Manual chính thức. Mọi ví dụ ghi dữ liệu chỉ dành cho database lab **mongo_agg_memory_lab_439**, collection **listing_views_439**. Không tăng payload hay số bản ghi trên production chỉ để tạo spilling; không tự thay đổi các server parameters có tiền tố **internalQuery**.

## 2. Tư duy theo luồng xử lý

~~~text
             MongoDB collection
                    |
                 $match       Filter
                    |
                $project      Trim fields
                    |
                  $group      Accumulate state
                    |
                   $sort      Order results
                    |
                  $limit      Bound output
                    |
              Result cursor
                    |
                Application
~~~

Mỗi stage nhận documents và tạo documents cho stage tiếp theo. Trình tối ưu MongoDB có thể push-down hoặc reorder các bước khi hợp lệ, do đó **thứ tự viết pipeline không luôn phản ánh thứ tự thực thi vật lý**. Explain mới cho thấy execution strategy được chọn.

### 2.1. Streaming stage

Một stage có thể xử lý input và phát output dần:

- **$match** lọc documents.
- **$project/$unset** loại field không cần thiết.
- **$set/$addFields** tính field mới.
- **$unwind** biến array thành nhiều documents.
- **$limit** dừng khi đủ documents theo semantics.

Streaming không có nghĩa zero-memory. Một expression tạo array rất lớn vẫn tiêu tốn RAM; $unwind có thể làm dữ liệu downstream tăng mạnh.

### 2.2. Blocking stage

Blocking stage thường phải giữ nhiều input hoặc state trước khi trả kết quả đúng:

- **$sort** không có indexed ordering.
- **$group** cần tích lũy theo group keys.
- **$bucketAuto** cần xác định phân bố dữ liệu.
- **$sortByCount** kết hợp grouping và sorting.
- **$setWindowFields** có thể phải buffer theo partition/order/window.

~~~text
Input 10 triệu documents
        |
   $sort without index
        |
   Buffer / external sort
        |
  Ordered output cursor
~~~

### 2.3. Input volume khác memory

Quét **30 GB input** không đồng nghĩa dùng 30 GB RAM. Một $match streaming có thể đọc nhiều rồi bỏ. Ngược lại, 1 triệu group keys hoặc một $push array lớn có thể chạm memory limit dù input ít hơn.

Không đánh đồng:

~~~text
Input bytes != peak RAM != spilled disk bytes
            != result BSON size != total operation memory
~~~

## 3. Các giới hạn quan trọng và đơn vị áp dụng

### 3.1. Ngưỡng 100 MB cho nhiều memory-intensive stages

MongoDB Manual mô tả những memory restrictions thường là **100 MB** cho state của các stage được theo dõi. Một stage hỗ trợ spill có thể ghi tạm ra disk nếu allowDiskUse có hiệu lực.

**Không** hiểu rằng:

- Cả pipeline được dùng tối đa 100 MB.
- Mọi stage đều chịu cùng cơ chế.
- Bật allowDiskUse thì memory vô hạn.
- Stage được spill thì mọi accumulator của nó cũng spill được.

### 3.2. Mỗi output BSON document tối đa 16 MiB

~~~text
Cursor:
  A: 5 KiB        hợp lệ
  B: 8 KiB        hợp lệ
  C: 19 MiB       lỗi document size
~~~

Tổng cursor có thể lớn hơn 16 MiB vì chứa **nhiều documents**. Ràng buộc áp cho **mỗi document**. Tài liệu nêu rằng một số document trung gian trong aggregation có thể lớn hơn, nhưng document cuối được trả ra phải thỏa BSON document limit.

Nếu $group dùng allRows:{$push:"$$ROOT"} và tạo **một document có array rất lớn**, nó có thể chạm accumulator limit hoặc BSON output limit. Không có lượng RAM nào biến BSON 19 MiB thành output hợp lệ.

### 3.3. Tối đa 1.000 stages

MongoDB có giới hạn **1.000 stages** trong một aggregation pipeline, được xem xét trước/sau parse theo tài liệu. Nếu code generator tạo 1.200 $set/$project stages, tăng RAM hoặc allowDiskUse không sửa lỗi này.

### 3.4. Accumulator-specific limit

Theo MongoDB Manual, **$push** có memory restriction riêng (default 100 MiB được mô tả bởi parameter tương ứng) và **không thể spill array tích lũy** giống state khác của $group. **$addToSet** cũng có thể tạo một accumulated object vượt giới hạn không spill.

~~~text
$group:
  hash/group state -> có thể spill trong điều kiện phù hợp
  $push huge array -> không tự spill, có thể vẫn lỗi
~~~

Không tự nâng internalQueryMaxPushBytes trên production để chứa một array tăng vô hạn.

### 3.5. Per-operation limit từ MongoDB 9.0

Tài liệu MongoDB **từ 9.0** mô tả giới hạn tổng tracked memory của một query operation, ngoài giới hạn từng stage. Nó bao gồm các blocking stages, một số expressions và các execution stages có buffering.

Default được mô tả là **giá trị lớn hơn giữa 1 GiB và 20% memory khả dụng cho server process**, thiết lập khi server khởi động. Đây là ngưỡng **riêng** với stage restriction ~100 MB; nó không thay đổi cách spill của từng stage. Các metrics và server parameters này **không nên giả định có trên MongoDB 6/7/8**.

### 3.6. Bảng nhận diện

| Giới hạn | Đối tượng | allowDiskUse có xử lý? |
| --- | --- | --- |
| Memory-intensive stage ~100 MB | State của stage | Có thể, nếu hỗ trợ spill |
| $push và object accumulator quá lớn | Một accumulator | Có trường hợp **không** |
| $facet tạo document quá 100 MB | Kết quả của facet stage | **Không** |
| Một output BSON document quá 16 MiB | Document cuối | **Không** |
| Pipeline quá 1.000 stages | Số stages | **Không** |
| Per-operation memory từ 9.0 | Tổng tracked memory | Không hoàn toàn; vẫn có giới hạn riêng |
| Temporary disk hết chỗ | Storage thật | **Không**; cờ không tạo disk |

## 4. allowDiskUse và allowDiskUseByDefault

### 4.1. Cách gọi trong mongosh

~~~javascript
const lab = db.getSiblingDB("mongo_agg_memory_lab_439");
const events = lab.getCollection("listing_views_439");

const pipeline = [
  { $match: { labTag: "agg439-v1" } },
  {
    $group: {
      _id: "$tenantId",
      views: { $sum: 1 }
    }
  },
  { $sort: { views: -1, _id: 1 } }
];

printjson(events.aggregate(pipeline, {
  allowDiskUse: true,
  maxTimeMS: 15000,
  comment: "lesson439-spill-aware"
}).toArray());
~~~

**allowDiskUse:true là cho phép spill, không phải cưỡng bức spill.** Nếu stage dùng ít bộ nhớ, query có thể chạy hoàn toàn trong RAM.

### 4.2. Từ MongoDB 6.0

Parameter **allowDiskUseByDefault** quyết định default spill behavior của các stages hỗ trợ. Lệnh riêng có thể override:

| Server default | Command | Hành vi |
| --- | --- | --- |
| false | Không khai báo | Không mặc định cho spill |
| false | allowDiskUse:true | Cho spill |
| true | Không khai báo | Cho spill theo default |
| true | allowDiskUse:false | Cấm spill cho command |

Không tự suy diễn default của một deployment. Trên các phiên bản trước 6.0, kiểm tài liệu option phù hợp thay vì áp parameter mới.

### 4.3. Đọc parameter nếu được phép

~~~javascript
// Quan sát, không chỉnh cấu hình:
printjson(
  db.getSiblingDB("admin").runCommand({
    getParameter: 1,
    allowDiskUseByDefault: 1
  })
);
~~~

Trên managed MongoDB/Atlas, quyền xem hoặc điều chỉnh parameters có thể khác self-managed.

### 4.4. Temporary files có chi phí

Khi spill, mongod có thể ghi/đọc files tạm trong vùng storage liên quan đến **dbPath/_tmp** theo deployment. Temp files thường được quản lý theo vòng đời operation.

Không tự xóa file đang được server sử dụng. Một report spill 3 GB và 10 report đồng thời có thể tạo áp lực temporary storage/I/O tương đương hàng chục GB, bên cạnh workload ứng dụng.

### 4.5. Cờ không phải tối ưu hóa

~~~text
Không cho spill:
  stage quá memory budget -> lỗi

Cho spill:
  stage quá memory budget -> ghi/đọc disk
  có thể hoàn thành nhưng latency tăng
~~~

Với API p99 nghiêm ngặt, một aggregation phải spill nhiều GB vẫn có thể là sự cố performance dù không còn memory error.

## 5. Giới hạn theo từng stage: bảng tổng quan

| Stage | Nguy cơ | Chiến lược |
| --- | --- | --- |
| **$match** | Scan quá nhiều | Dùng predicate/index thích hợp |
| **$project/$set** | Expression hoặc document/array to | Giảm width, tránh tạo array lớn |
| **$unwind** | Tăng số rows downstream | Kiểm fan-out trước $sort/$group |
| **$sort** | Blocking sort state | Index, lọc, top-K; có thể spill |
| **$group** | Nhiều group keys | Giảm cardinality, dùng accumulators nhỏ; state có thể spill |
| **$push/$addToSet** | Một accumulated array/set rất lớn | Không trông chờ spill để cứu |
| **$bucket** | Group/accumulator state | Bounded buckets, sum/count; có thể spill |
| **$bucketAuto** | Xếp nhóm tự động | Giảm input, số buckets; có thể spill |
| **$sortByCount** | Group + sort frequency | Match, top-K; có thể spill |
| **$setWindowFields** | Partition/order/window buffer | Bounded window/index, có thể spill |
| **$facet** | Một document chứa arrays lớn | 100 MB stage limit **không spill**, 16 MiB final BSON |
| **$lookup** | Fan-out/join array | Foreign index, giảm matches, output bound |
| **$graphLookup** | Recursive traversal và result array | maxDepth/filter, kiểm version và spill rules |
| **$search** | Search engine riêng | Không áp 100 MB restriction tương tự mongod; có giới hạn riêng |
| **$merge/$out** | Ghi vào collection, side effects | Không dùng làm mẹo tạm vô kế hoạch |

**Lưu ý về $graphLookup:** MongoDB Manual mới mô tả có thể ghi temporary files khi vượt 100 MB trong điều kiện phù hợp; một số ghi chú driver/docs cũ lại mô tả khác. Hãy kiểm tra **đúng MongoDB server version và manual tương ứng**, không khẳng định một quy tắc bất biến cho mọi phiên bản.

## 6. $sort: lỗi memory hay thiếu index?

### 6.1. Sort toàn tập

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  { $sort: { createdAt: -1 } }
]
~~~

Nếu không có index cung cấp đúng thứ tự, server có thể cần sort một tập lớn. Với nhiều triệu docs, sort state lớn và spill I/O cao.

### 6.2. Tận dụng index

~~~javascript
db.listingViews.createIndex({
  tenantId: 1,
  createdAt: -1
});
~~~

Khi predicate tenantId equality và sort createdAt desc, compound index này có thể hỗ trợ filter + ordering. Còn tùy optimizer, collations, những stages trước sort và selectivity. **Phải xác minh bằng explain**, không suy đoán có index thì chắc chắn không SORT.

### 6.3. Top-K

Nếu chỉ cần 20 events mới nhất:

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 20 }
]
~~~

MongoDB có thể **coalesce $sort và $limit** thành top-K khi không có stage ở giữa thay đổi cardinality, giúp chỉ giữ lượng data gần N thay vì toàn bộ sort set.

### 6.4. Đặt limit sai chỗ làm sai nghiệp vụ

Nếu báo cáo cần tổng views tháng này, đặt **$limit:20 trước $group** chỉ đếm 20 events. Ngược lại, đưa limit sau group+sort là hợp lý nếu cần top 20 listings theo **tổng lượt xem**.

~~~javascript
[
  { $match: { createdAt: { $gte: start } } },
  { $group: { _id: "$listingId", views: { $sum: 1 } } },
  { $sort: { views: -1, _id: 1 } },
  { $limit: 20 }
]
~~~

### 6.5. $unwind giữa sort và limit

~~~javascript
[
  { $sort: { score: -1 } },
  { $unwind: "$tags" },
  { $limit: 20 }
]
~~~

Không giả định top-K tối ưu được như khi sort-limit đứng liền nhau: unwind làm tăng output cardinality.

### 6.6. Sort ổn định cho pagination

Nhiều events có cùng createdAt; sort theo createdAt đơn lẻ có thể trả thứ tự không ổn định. Dùng tie-breaker _id và thiết kế keyset pagination/index phù hợp. Tránh skip các offset quá sâu nếu dữ liệu lớn.

## 7. $group: state và accumulator không giống nhau

### 7.1. Group key cardinality

~~~javascript
[
  {
    $group: {
      _id: "$tenantId",
      views: { $sum: 1 }
    }
  }
]
~~~

Nếu chỉ 20 tenants, state nhóm có thể nhỏ dù đọc hàng chục triệu events. Nhưng group theo eventId unique có thể tạo hàng triệu nhóm và memory pressure.

### 7.2. Anti-pattern $push $$ROOT

~~~javascript
[
  {
    $group: {
      _id: "$tenantId",
      allRows: { $push: "$$ROOT" }
    }
  }
]
~~~

Một tenant lớn sẽ tạo accumulated array tăng vô hạn. $group stage state có thể spill nhưng **array của $push có hạn mức riêng không spill**, và output document vẫn chịu 16 MiB. allowDiskUse:true không đủ.

### 7.3. Giữ đúng dữ liệu cần

~~~javascript
[
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 },
      maxCreatedAt: { $max: "$createdAt" },
      totalDurationMs: { $sum: "$durationMs" }
    }
  }
]
~~~

Không lấy tất cả input documents rồi tính size array trong ứng dụng nếu MongoDB có thể cộng trực tiếp.

### 7.4. Top N theo group

Với server hỗ trợ $topN:

~~~javascript
[
  {
    $group: {
      _id: "$tenantId",
      recent: {
        $topN: {
          n: 5,
          sortBy: { createdAt: -1 },
          output: {
            listingId: "$listingId",
            createdAt: "$createdAt"
          }
        }
      }
    }
  }
]
~~~

Chỉ giữ 5 entries mỗi tenant thay vì allRows. Nhưng nếu mỗi entry rất lớn hoặc số groups quá cao thì vẫn phải xem memory/output limits.

### 7.5. $first/$last có thể được tối ưu

Một số pipeline sort và group cùng key, chỉ dùng $first/$last, có thể tận dụng index để tìm phần tử đầu/cuối. Không thay $max bằng $first khi không bảo đảm order: $group **không cam kết output sort**.

## 8. $facet: cờ allowDiskUse không cứu được

### 8.1. Tại sao output lớn?

$facet trả **một document** có nhiều arrays, mỗi array là kết quả của một sub-pipeline:

~~~javascript
[
  {
    $facet: {
      recent: [
        { $sort: { createdAt: -1 } }
      ],
      count: [
        { $count: "n" }
      ]
    }
  }
]
~~~

Nếu recent giữ mọi events, output array phình to.

### 8.2. Hai giới hạn riêng

MongoDB Manual xác nhận:

- Document mà **$facet** xây dựng có giới hạn **100 MB**; **$facet không spill** và allowDiskUse không thay giới hạn này.
- Final result BSON document phải dưới **16 MiB**. Một facet output 30 MiB có thể chưa chạm 100 MB nhưng đã quá lớn để trả.

### 8.3. Facets có giới hạn hợp lý

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  {
    $facet: {
      recent: [
        { $sort: { createdAt: -1 } },
        { $limit: 10 },
        {
          $project: {
            _id: 1,
            listingId: 1,
            createdAt: 1
          }
        }
      ],
      byCity: [
        { $group: { _id: "$cityCode", count: { $sum: 1 } } },
        { $sort: { count: -1 } },
        { $limit: 10 }
      ],
      total: [{ $count: "n" }]
    }
  }
]
~~~

### 8.4. Index trước facet

Nếu $facet là stage đầu tiên, tài liệu mô tả nó không tận dụng index cho filtering như $match đặt phía trước. Đưa filter có thể dùng index lên trước **khi giữ nguyên business semantics**.

### 8.5. Khi cần nhiều rows, tách API

Một API có thể:

- GET /events dùng cursor/keyset pagination.
- GET /events/facets chỉ trả aggregates nhỏ.

Đừng ép mọi rows và summary vào một facet document. Tách endpoint có thêm round-trip nhưng giúp tránh output limit và dễ kiểm soát resource budgets.

## 9. $setWindowFields: partition và window có thể rất nặng

Ví dụ đếm lũy kế các lượt xem theo listing:

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  {
    $setWindowFields: {
      partitionBy: "$listingId",
      sortBy: { createdAt: 1 },
      output: {
        runningViews: {
          $sum: 1,
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  }
]
~~~

Nguồn áp lực:

- Partition cực lớn.
- Nhiều partitions.
- Cần sort theo order key.
- Unbounded window hoặc accumulator tích lũy dữ liệu lớn.
- Mỗi input event đều tạo output row.

Theo MongoDB aggregation limits, $setWindowFields có thể spill khi policy cho phép, nhưng vẫn có các restrictions riêng.

Nếu business chỉ cần tổng views/listing, dùng $group với một row/listing, không tính runningViews cho mọi event rồi bỏ đi.

### 9.1. Window bounded

~~~javascript
{
  $setWindowFields: {
    partitionBy: "$listingId",
    sortBy: { createdAt: 1 },
    output: {
      last10Events: {
        $sum: 1,
        window: { documents: [-9, "current"] }
      }
    }
  }
}
~~~

Window theo **10 rows** khác window **10 phút**. Không đổi ngữ nghĩa chỉ để giảm RAM.

### 9.2. Index ứng viên

~~~javascript
{ tenantId: 1, listingId: 1, createdAt: 1 }
~~~

có thể hữu ích cho một số query partition/sort shapes, nhưng khả năng dùng index cần xác minh bằng explain theo version và pipeline.

## 10. $bucket, $bucketAuto và $sortByCount

### 10.1. Buckets cố định

~~~javascript
[
  {
    $bucket: {
      groupBy: "$durationMs",
      boundaries: [0, 1000, 5000, 30000, 600000],
      default: "other",
      output: {
        n: { $sum: 1 },
        totalMs: { $sum: "$durationMs" }
      }
    }
  }
]
~~~

Nếu chỉ vài buckets và accumulators count/sum, state thường gọn. Thêm allRows:{$push:"$$ROOT"} cho từng bucket lại gây array growth.

### 10.2. Buckets tự động

~~~javascript
[
  {
    $bucketAuto: {
      groupBy: "$durationMs",
      buckets: 5,
      output: {
        n: { $sum: 1 }
      }
    }
  }
]
~~~

MongoDB cần xử lý phân bố values để tạo buckets. $bucketAuto nằm trong nhóm stages được tài liệu liệt kê có thể spill.

### 10.3. $sortByCount

~~~javascript
[
  { $sortByCount: "$cityCode" },
  { $limit: 10 }
]
~~~

Về ý nghĩa tương tự:

~~~javascript
[
  { $group: { _id: "$cityCode", count: { $sum: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 10 }
]
~~~

Đừng đưa limit trước group nếu muốn **top counts chính xác trên toàn bộ input**.

## 11. $lookup và $graphLookup: fan-out và output arrays

### 11.1. $lookup fan-out

~~~javascript
[
  {
    $lookup: {
      from: "listings",
      localField: "listingId",
      foreignField: "_id",
      as: "listing"
    }
  }
]
~~~

Nếu một local row match hàng nghìn foreign documents, field as có thể trở thành array lớn, vượt BSON size. Nếu sau đó $unwind thì số rows downstream tăng mạnh.

Ví dụ:

~~~text
1.000 input rows × 100 joined rows
  -> 100.000 rows sau unwind
  -> SORT/GROUP nặng hơn
~~~

Xem index của foreignField, join cardinality, filters và data model. Một equality join theo _id được hưởng index _id sẵn có; join theo field khác có thể cần index riêng.

### 11.2. Không áp $limit tùy tiện cho foreign join

Giới hạn foreign matches có thể giảm memory nhưng thay business semantics nếu cần **mọi** records. Khi chỉ cần một record gần nhất, hãy thiết kế join key/order/limit rõ và kiểm thử.

### 11.3. $graphLookup

$graphLookup duyệt quan hệ đệ quy (cây category, hierarchy). Cần kiểm:

- Có **maxDepth** không?
- Có **restrictSearchWithMatch** giảm branch không?
- Foreign connectToField có index hợp lý không?
- Có cycles/broad fan-out không?
- Array kết quả có vượt BSON limit không?

~~~javascript
[
  {
    $graphLookup: {
      from: "lab_categories_439",
      startWith: "$parentCategoryId",
      connectFromField: "parentCategoryId",
      connectToField: "_id",
      as: "ancestors",
      maxDepth: 5,
      restrictSearchWithMatch: { active: true }
    }
  }
]
~~~

Đoạn này chỉ minh họa cú pháp; cần collection thích hợp mới chạy. **Memory/spill behavior theo server manual của phiên bản đang chạy**; đừng dựa vào tài liệu driver cũ để khẳng định mọi bản giống nhau.

## 12. Các stage có đặc thù khác

**$unwind:** không nhất thiết là nguồn blocking memory, nhưng nhân cardinality cho các stages sau. Một event có 8 tags thành 8 rows; group sum count sau đó có thể **đếm 8 lần** nếu quên ý nghĩa.

**$project/$set:** giảm field width có thể giúp giảm transfer/state, nhưng expression tạo mảng lớn vẫn tốn memory. Optimizer có thể push-down projection hợp lệ.

**$search:** chạy trong thành phần search riêng ở Atlas Search, không bị áp 100 MB RAM stage restriction giống $sort trong mongod. Dù vậy nó có quota/limit/resource consumption riêng.

**$merge/$out:** có side effects ghi collection. Không thêm chúng làm một “cách xả ra đĩa” trong production mà chưa kiểm tra semantics, quyền, indexes và ảnh hưởng dữ liệu đích.

## 13. Phân loại lỗi cần làm trước khi sửa

### 13.1. QueryExceededMemoryLimitNoDiskUseAllowed

Điều tra:

- Stage nào bị giới hạn?
- Server default và command allowDiskUse là gì?
- Có thể dùng indexed sort, reduce group state hay top-K không?
- Nếu cần spill, storage có đủ headroom/IOPS không?

### 13.2. ExceededMemoryLimit dù allowDiskUse:true

Kiểm:

- $facet 100 MB non-spill.
- $push/$addToSet và memory restrictions riêng.
- Expression/operation total memory theo version.
- Stage không spill được.
- Output quá lớn hoặc join fan-out.

### 13.3. BSON object too large

Đổi output shape: nhiều cursor documents, pagination, summary riêng, không gom toàn bộ vào một array. Tăng RAM không giải quyết 16 MiB.

### 13.4. Query bị timeout

Phân biệt:

~~~text
MongoDB MaxTimeMSExpired
  != driver socket timeout
  != HTTP gateway timeout
  != memory limit error
~~~

Một spill query có thể chạy quá chậm dù không memory-fail. Điều tra ở đúng layer.

### 13.5. Disk full / I/O contention

Xem disk free/latency, số active spills, concurrency, backup/index jobs và replication lag. Không xóa _tmp thủ công trong lúc mongod chạy.

### 13.6. Thu thập incident evidence

Ghi timestamp UTC, trace/query fingerprint, namespace, MongoDB version/FCV, codeName/message đã lọc PII, allowDiskUse/maxTimeMS, explain, scan stats, usedDisk/spills nếu có, disk/CPU/RAM metrics, report job concurrency và affected SLO.

Không log raw tenant documents hoặc credentials vào ticket.

## 14. Explain: xác định stage nào đang tốn tài nguyên

Trong mongosh:

~~~javascript
const lab = db.getSiblingDB("mongo_agg_memory_lab_439");
const events = lab.getCollection("listing_views_439");

const pipeline = [
  { $match: { labTag: "agg439-v1" } },
  {
    $group: {
      _id: "$tenantId",
      views: { $sum: 1 }
    }
  },
  { $sort: { views: -1 } }
];

printjson(
  events.explain("executionStats").aggregate(
    pipeline,
    { allowDiskUse: true }
  )
);
~~~

Một cách khác nếu driver/helper yêu cầu:

~~~javascript
printjson(
  lab.runCommand({
    explain: {
      aggregate: "listing_views_439",
      pipeline,
      cursor: {},
      allowDiskUse: true,
      comment: "lesson439-explain"
    },
    verbosity: "executionStats"
  })
);
~~~

### 14.1. Tìm gì trong explain?

- **winningPlan**: COLLSCAN, IXSCAN, FETCH, SORT...
- **nReturned**.
- **totalDocsExamined**.
- **totalKeysExamined**.
- **executionTimeMillis**.
- Các dấu hiệu **usedDisk, spills, spilledDataStorageSize, peak memory** khi version/engine cung cấp.
- Thông tin **splitPipeline/merge** khi sharded cluster.

Output shape khác nhau giữa MongoDB versions và classic/SBE engine. Không viết một parser chỉ đọc một key rồi kết luận không spill nếu key vắng mặt.

### 14.2. Plan tốt hơn

~~~text
Trước:
  COLLSCAN -> SORT millions -> GROUP -> LIMIT

Sau khi sửa đúng business requirement:
  MATCH with index -> GROUP by small key
  -> SORT small groups -> LIMIT
~~~

Nếu query cần recent 20 docs, một index-backed sort + limit có thể hợp lý hơn. Nếu query cần tổng count chính xác, không bỏ input bằng limit sớm.

### 14.3. Explain không phải p99 HTTP

Explain giúp hiểu server execution, không tự đo driver pool wait/network, cache warm/cold, concurrency và gateway latency. Kết hợp với application telemetry.

## 15. usedDisk, profiler và metrics phiên bản mới

### 15.1. usedDisk là quan sát thực tế

MongoDB Manual mô tả **usedDisk** trong profiler/diagnostic logs khi một stage thực sự ghi temporary files do memory restrictions. Chỉ có **allowDiskUse:true** không chứng minh đã spill.

Nếu profiler đã được quản trị viên bật hợp lệ:

~~~javascript
const diagnostic = db.getSiblingDB(
  "mongo_agg_memory_lab_439"
);

printjson(
  diagnostic.getCollection("system.profile")
    .find(
      { "command.comment": "lesson439-spill-aware" },
      {
        ts: 1,
        millis: 1,
        usedDisk: 1,
        planSummary: 1,
        "command.comment": 1
      }
    )
    .sort({ ts: -1 })
    .limit(10)
    .toArray()
);
~~~

Profiler mặc định có thể không bật; kết quả rỗng là bình thường. Không tự bật high-volume profiler trên production chỉ để lấy usedDisk: gây overhead và có thể log thông tin nhạy cảm.

### 15.2. serverStatus và MongoDB 9.0

Tài liệu MongoDB 9.0+ nêu một số memory metrics:

~~~text
metrics.query.peakMemoryUsageOperation
metrics.query.operationsFailedDueToMemoryLimit
metrics.query.configuredMaxMemoryUsageBytesPerOperation
~~~

Trên deployment/version hỗ trợ và khi có quyền:

~~~javascript
const status = db.getSiblingDB("admin")
  .runCommand({ serverStatus: 1 });
printjson(status.metrics && status.metrics.query);
~~~

Không thấy metric trên 6.x/7.x/8.x không có nghĩa server không dùng RAM.

### 15.3. Atlas monitoring

Theo dõi query profiler/slow queries, CPU, disk free, disk IOPS/latency, cache pressure, replication lag, per-shard hot spots. Atlas có giới hạn quyền đổi server parameters khác self-managed.

### 15.4. currentOp

Nếu được cấp quyền và hiểu topology, currentOp/$currentOp có thể cho biết operations đang kéo dài. Không dùng killOp hàng loạt nếu chưa biết operation là read-only hay có side effects như $merge/$out.

## 16. Tối ưu hóa pipeline từ gốc

### 16.1. Lọc sớm

Thường nên viết:

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  { $sort: { createdAt: -1 } },
  { $limit: 20 }
]
~~~

thay cho sort toàn collection rồi match. Optimizer có thể tự đẩy $match khi hợp lệ; explain xác minh mức độ pushdown.

### 16.2. Bỏ field không cần

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  { $project: { tenantId: 1, durationMs: 1 } },
  {
    $group: {
      _id: "$tenantId",
      totalDurationMs: { $sum: "$durationMs" }
    }
  }
]
~~~

Đừng đẩy mô tả HTML hoặc payload lớn vào $push nếu report chỉ cần sum.

### 16.3. Group đúng độ hạt

Group theo full createdAt timestamp có thể gần một group/event. Nếu report cần count theo ngày:

~~~javascript
{
  $group: {
    _id: {
      $dateTrunc: {
        date: "$createdAt",
        unit: "day",
        timezone: "Asia/Ho_Chi_Minh"
      }
    },
    views: { $sum: 1 }
  }
}
~~~

Số groups có thể giảm lớn, nhưng phải xác định timezone nghiệp vụ; không tự đổi daily semantics để giảm memory.

### 16.4. Đưa sort sau group khi chỉ cần top groups

Kém:

~~~javascript
[
  { $sort: { createdAt: -1 } },
  { $group: { _id: "$tenantId", views: { $sum: 1 } } },
  { $sort: { views: -1 } }
]
~~~

Tốt hơn cho yêu cầu đếm:

~~~javascript
[
  { $group: { _id: "$tenantId", views: { $sum: 1 } } },
  { $sort: { views: -1, _id: 1 } }
]
~~~

Nếu cần $first/$last theo thời gian, không bỏ sort ban đầu mà chưa đảm bảo semantics.

### 16.5. Chặn fan-out

Unwind tags trước khi count events có thể đếm mỗi event nhiều lần. Kiểm số rows trước/sau $unwind/$lookup và xác định business unit là **event**, **tag** hay **listing**.

### 16.6. Không sửa kết quả để đạt benchmark

Một query nhanh hơn 100 lần nhưng thiếu 99% documents do $limit quá sớm **không phải tối ưu đúng**. So cả kết quả/business invariants, không chỉ executionTimeMillis.

## 17. Index: tránh sort memory nếu có thể

Ví dụ filter tenant và sort theo thời gian:

~~~javascript
db.listingViews.createIndex({
  tenantId: 1,
  createdAt: -1,
  _id: 1
});
~~~

Trong lab có labTag:

~~~javascript
events.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "ix439_tag_tenant_date_id" }
);
~~~

Index chỉ hữu ích khi phù hợp filter/sort/query plan. Một heuristic là equality fields trước, rồi sort, rồi cân nhắc ranges; không phải luật tuyệt đối. Index còn tốn disk/write maintenance, nên đừng build hàng loạt trên cluster đang bị spill-induced disk pressure.

Không kỳ vọng index loại bỏ mọi memory cost của $group, window, facet hoặc $push.

## 18. maxTimeMS, batchSize và giới hạn API

### 18.1. maxTimeMS

~~~javascript
events.aggregate(pipeline, {
  allowDiskUse: true,
  maxTimeMS: 15000
});
~~~

Giúp đặt deadline server-side theo semantics command/cursor, không giới hạn RAM và không đồng nghĩa query chắc chắn trả trước 15 giây. Driver timeout và HTTP gateway timeout là các lớp riêng.

### 18.2. batchSize không sửa blocking stage

~~~javascript
events.aggregate(pipeline, {
  cursor: { batchSize: 100 }
});
~~~

Batch size điều chỉnh việc trả kết quả cho client, **không làm $sort/$group phía server chỉ dùng memory của 100 records**.

### 18.3. Giới hạn người dùng

Một endpoint/report job cần quy định:

- Tenant/security scope.
- Maximum time window.
- Max page size.
- Max concurrent jobs.
- Query type/fields được whitelist.
- Deadline, retry, cancellation và cleanup.
- Khi nào chuyển sang report async.

Không cho client gửi pipeline JSON bất kỳ với allowDiskUse:true và không có quotas.

### 18.4. Async reporting

~~~text
HTTP request -> validate/authenticate
             -> enqueue job
             -> worker with concurrency limit
             -> aggregation + bounded output
             -> status/report artifact
~~~

Background jobs cần idempotency, authorization, storage retention và dead-letter/error handling để tránh retry gây bão I/O.

## 19. Driver Java và Spring Data MongoDB

### 19.1. MongoDB Java Sync Driver

~~~java
import com.mongodb.client.AggregateIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import org.bson.Document;
import java.util.List;
import java.util.concurrent.TimeUnit;

MongoCollection<Document> collection =
    database.getCollection("listing_views_439");

List<Document> stages = List.of(
    new Document("$match",
        new Document("labTag", "agg439-v1")
            .append("tenantId", "tenant-001")
    ),
    new Document("$group",
        new Document("_id", "$listingId")
            .append("views", new Document("$sum", 1))
    ),
    new Document("$sort", new Document("views", -1)),
    new Document("$limit", 10)
);

AggregateIterable<Document> query = collection
    .aggregate(stages)
    .allowDiskUse(true)
    .maxTime(15, TimeUnit.SECONDS)
    .batchSize(100);

try (MongoCursor<Document> cursor = query.iterator()) {
    while (cursor.hasNext()) {
        Document result = cursor.next();
        // Process bounded rows; do not keep unbounded data.
    }
}
~~~

Server thành công không chứng minh Java heap đủ chứa tất cả results. Tránh cursor.into(new ArrayList<>()) cho data stream không giới hạn.

### 19.2. Spring Data MongoTemplate

Ở các Spring Data versions tương ứng, có thể cấu hình AggregationOptions:

~~~java
AggregationOptions options =
    AggregationOptions.builder()
        .allowDiskUse(true)
        .maxTime(Duration.ofSeconds(15))
        .build();

Aggregation aggregation = Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("tenantId").is("tenant-001")
    ),
    Aggregation.group("listingId").count().as("views"),
    Aggregation.sort(Sort.Direction.DESC, "views"),
    Aggregation.limit(10)
).withOptions(options);
~~~

Những APIs/overloads cần kiểm tra theo Spring Data version cụ thể. **MongoTemplate typed query có thể map Java property paths thành BSON field names; raw mongosh/driver cần dùng tên lưu trữ thật.**

### 19.3. Xử lý exception

Không bắt mọi RuntimeException rồi trả một báo cáo rỗng:

~~~java
try {
    return executeReport();
} catch (Exception error) {
    return List.of();  // Sai: nhầm thất bại thành không có dữ liệu
}
~~~

Phân biệt memory, timeout, network, permissions, invalid pipeline; ghi metrics, trả lỗi/partial-result contract rõ và retry có giới hạn.

## 20. Sharded cluster: spill có thể xảy ra ở nhiều nơi

~~~text
                   mongos
                     |
           +---------+---------+
           |                   |
        Shard A             Shard B
      partial GROUP       partial GROUP
           |                   |
           +---------+---------+
                     |
                 MERGE/SORT
                     |
                   Client
~~~

Planner có thể chia pipeline thành phần chạy tại shards và phần merge theo phiên bản/query. Có thể phát sinh memory/network/spill trên từng shard hoặc merging node.

Theo dõi:

- Per-shard CPU/disk/network.
- Spill indicators được log.
- Read/write ops và hot shard key.
- Query targeting/shard fan-out.
- Merge sort/group costs.
- Replication lag.

Thêm shards không làm **một BSON facet output 30 MiB** trở nên hợp lệ. Và thêm RAM không sửa được một accumulator $push không bounded.

## 21. Temp disk và blast radius

Một report spill có thể hoàn thành nhưng tranh chấp disk với API CRUD:

~~~text
Report $sort/$group spill
          |
          v
    Temporary disk I/O
          |
    +-----+-----+
    |           |
Report slow   API p99 tăng
~~~

Giả sử 10 reports đồng thời mỗi report ghi vài GB temporary data. Dù disk còn free bytes, **IOPS/latency** có thể vượt budget. Cần monitoring và rate limiting.

Không xóa tệp tạm do mongod quản lý. Nếu cần dừng query, phải biết read-only hay $merge/$out và dừng theo runbook/permissions thích hợp.

## 22. Lab mongosh: chuẩn bị 12.000 synthetic events

### 22.1. Mục tiêu an toàn

Lab **không cố tạo >100 MB** để làm cạn memory/disk. Ta dùng 12.000 documents để minh họa query shape, cardinality, explain và output:

~~~text
Database: mongo_agg_memory_lab_439
Collection: listing_views_439
4 tenants × 3.000 events
3 city codes
Nhiều listing IDs
eventType, durationMs, score, createdAt
~~~

**allowDiskUse:true** trên lab có thể không tạo usedDisk. Đó không phải lỗi lab.

### 22.2. Seed có thể chạy lại

~~~javascript
(() => {
  const lab = db.getSiblingDB(
    "mongo_agg_memory_lab_439"
  );
  const events = lab.getCollection("listing_views_439");
  const tag = "agg439-v1";
  const n = 12000;
  const batchSize = 200;
  const start = Date.UTC(2026, 0, 1, 0, 0, 0);
  let ops = [];
  let batches = 0;

  function flush() {
    if (!ops.length) return;
    events.bulkWrite(ops, { ordered: false });
    ops = [];
    batches++;
  }

  for (let i = 0; i < n; i++) {
    const id = "agg439-event-"
      + String(i).padStart(6, "0");
    const tenantId = "tenant-"
      + String(1 + (i % 4)).padStart(3, "0");
    const listingId = tenantId + "-listing-"
      + String(1 + (i % 50)).padStart(3, "0");

    const doc = {
      _id: id,
      labTag: tag,
      tenantId,
      listingId,
      cityCode: ["HCM", "HN", "DN"][i % 3],
      eventType: [
        "VIEW", "BOOKMARK", "CONTACT", "VIEW"
      ][i % 4],
      createdAt: new Date(start + i * 216000),
      durationMs: 100 + (i % 18000),
      score: (i * 37) % 1000,
      note: "Synthetic event " + String(i % 100)
    };

    ops.push({
      replaceOne: {
        filter: { _id: id, labTag: tag },
        replacement: doc,
        upsert: true
      }
    });
    if (ops.length >= batchSize) flush();
  }
  flush();

  printjson({
    count: events.countDocuments({ labTag: tag }),
    batches,
    sample: events.find(
      { labTag: tag },
      {
        _id: 1,
        tenantId: 1,
        listingId: 1,
        createdAt: 1
      }
    ).sort({ _id: 1 }).limit(3).toArray()
  });
})();
~~~

Kết quả mong đợi ở lab sạch: **count=12.000**, **batches=60**.

Script không drop collection. Filter có _id + labTag; nếu một document lạ trùng _id nhưng không mang labTag, upsert có thể gặp duplicate key thay vì ghi đè. Không xóa dữ liệu lạ để làm lab chạy.

## 23. Lab A — $group nhỏ và kiểm tra phân bố

~~~javascript
const lab = db.getSiblingDB("mongo_agg_memory_lab_439");
const events = lab.getCollection("listing_views_439");

printjson(events.aggregate([
  { $match: { labTag: "agg439-v1" } },
  {
    $group: {
      _id: "$tenantId",
      events: { $sum: 1 },
      totalDurationMs: { $sum: "$durationMs" },
      latestAt: { $max: "$createdAt" }
    }
  },
  { $sort: { _id: 1 } }
], { maxTimeMS: 15000 }).toArray());
~~~

Mỗi tenant có 3.000 records. **events** ở đây là tổng mọi eventType, không chỉ VIEW; khi muốn đếm VIEW phải thêm match eventType phù hợp.

### 23.1. $push IDs có bound trong lab

~~~javascript
printjson(events.aggregate([
  {
    $match: {
      labTag: "agg439-v1",
      tenantId: "tenant-001"
    }
  },
  {
    $group: {
      _id: "$tenantId",
      ids: { $push: "$_id" }
    }
  },
  {
    $project: {
      _id: 1,
      arrayCount: { $size: "$ids" }
    }
  }
], { allowDiskUse: false, maxTimeMS: 15000 }).toArray());
~~~

Array 3.000 short IDs thường vẫn nhỏ. Bài học: với hàng triệu documents hoặc $$ROOT lớn, $push không bounded và output BSON có thể lỗi.

### 23.2. Đúng hơn nếu chỉ cần đếm

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  { $group: { _id: "$tenantId", n: { $sum: 1 } } }
]
~~~

Không tạo array rồi dùng $size để đếm nếu không cần giữ các phần tử.

## 24. Lab B — Sort toàn bộ so với top-K

~~~javascript
const fullSort = [
  {
    $match: {
      labTag: "agg439-v1",
      tenantId: "tenant-001"
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $project: { _id: 1, listingId: 1, score: 1 } }
];

printjson(
  events.explain("executionStats")
    .aggregate(fullSort, { allowDiskUse: false })
);

const topK = [
  {
    $match: {
      labTag: "agg439-v1",
      tenantId: "tenant-001"
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $limit: 20 },
  { $project: { _id: 1, listingId: 1, score: 1 } }
];

printjson(events.aggregate(topK, {
  allowDiskUse: false,
  maxTimeMS: 15000
}).toArray());
~~~

Top-K trả **20 events**; fullSort có thể trả 3.000. Không kỳ vọng spill ở lab nhỏ.

### 24.1. Thêm index

~~~javascript
events.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    score: -1,
    _id: 1
  },
  { name: "ix439_tag_tenant_score_id" }
);
~~~

Chạy lại explain xem plan có tận dụng index hay không. Tùy dataset/optimizer, không nên khẳng định lúc nào cũng dùng IXSCAN.

## 25. Lab C — Facet bounded output

~~~javascript
const facetPipeline = [
  {
    $match: {
      labTag: "agg439-v1",
      tenantId: "tenant-001"
    }
  },
  {
    $facet: {
      recent: [
        { $sort: { createdAt: -1 } },
        { $limit: 5 },
        {
          $project: {
            _id: 1,
            listingId: 1,
            createdAt: 1
          }
        }
      ],
      byCity: [
        { $sortByCount: "$cityCode" }
      ],
      summary: [
        {
          $group: {
            _id: null,
            total: { $sum: 1 },
            avgDurationMs: { $avg: "$durationMs" }
          }
        }
      ]
    }
  }
];

printjson(events.aggregate(facetPipeline, {
  allowDiskUse: true,
  maxTimeMS: 15000
}).toArray());
~~~

recent có tối đa 5 rows, byCity tối đa 3 city buckets, summary là một document. Nếu bỏ limit và project trong recent, kết quả có thể phát triển không bounded và gặp giới hạn $facet/BSON trên dataset lớn.

## 26. Lab D — Cardinality, dateTrunc và unwind

### 26.1. Group theo timestamp chính xác

~~~javascript
printjson(events.aggregate([
  { $match: { labTag: "agg439-v1" } },
  {
    $group: {
      _id: "$createdAt",
      n: { $sum: 1 }
    }
  },
  { $count: "timestampGroups" }
], { maxTimeMS: 15000 }).toArray());
~~~

Vì seed gán unique timestamp theo i, số groups kỳ vọng gần 12.000.

### 26.2. Group theo ngày

~~~javascript
printjson(events.aggregate([
  { $match: { labTag: "agg439-v1" } },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$createdAt",
          unit: "day",
          timezone: "UTC"
        }
      },
      events: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
], { maxTimeMS: 15000 }).toArray());
~~~

Số groups theo ngày giảm nhiều. Nhưng group theo UTC vs Asia/Ho_Chi_Minh có thể khác biên ngày; phải theo contract báo cáo.

### 26.3. Unwind làm tăng rows

~~~javascript
printjson(events.aggregate([
  { $match: { labTag: "agg439-v1" } },
  {
    $project: {
      syntheticTags: ["rental", "event", "analytics"]
    }
  },
  { $unwind: "$syntheticTags" },
  { $count: "rowsAfterUnwind" }
], { maxTimeMS: 15000 }).toArray());
~~~

Từ 12.000 thành **36.000 rows**. Nếu sort sau unwind, sort input tăng gấp ba; nếu group count theo tenant sau unwind, có thể đếm event ba lần.

## 27. Lab E — Window bounded

~~~javascript
printjson(events.aggregate([
  {
    $match: {
      labTag: "agg439-v1",
      tenantId: "tenant-001",
      listingId: "tenant-001-listing-001"
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$listingId",
      sortBy: { createdAt: 1 },
      output: {
        recent10: {
          $sum: 1,
          window: { documents: [-9, "current"] }
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      createdAt: 1,
      recent10: 1
    }
  },
  { $limit: 20 }
], {
  allowDiskUse: true,
  maxTimeMS: 15000
}).toArray());
~~~

recent10 tăng từ 1 đến 10 rồi giữ 10 sau khi đủ rows; đây là **10 events gần nhất** theo order, không phải 10 phút. Không cần ép memory để quan sát kết quả.

## 28. Lab F — explain với allowDiskUse

~~~javascript
const p = [
  {
    $match: {
      labTag: "agg439-v1",
      tenantId: "tenant-001"
    }
  },
  { $sort: { createdAt: -1, _id: 1 } },
  { $limit: 20 }
];

printjson(
  events.explain("executionStats").aggregate(
    p, { allowDiskUse: false }
  )
);

printjson(
  events.explain("executionStats").aggregate(
    p, { allowDiskUse: true }
  )
);
~~~

So winningPlan, scanned/returned và các spill statistics (nếu được expose). Nếu cả hai không spill, đó là kết quả bình thường với data nhỏ hoặc index-backed sort. **Không thêm hàng triệu records chỉ để ép usedDisk:true**.

## 29. Runbook sự cố production

### Phase A — Impact

1. Xác định API/report/job lỗi và tenants bị ảnh hưởng.
2. Thu thập error code/codeName, UTC time, query fingerprint.
3. Đo p95/p99, error rate và throughput.
4. Xem disk free/latency, CPU/memory, replication lag.
5. Xác nhận MongoDB version/FCV và deployment.

### Phase B — Isolate

1. Kiểm tra pipeline stages.
2. Xem explain, nReturned, docsExamined/keysExamined.
3. Kiểm tra usedDisk/spills nếu có.
4. Phân biệt memory, BSON size, stage count, timeout và disk errors.
5. Tái hiện trên staging có dataset đại diện khi cần.

### Phase C — Mitigate

- Giảm concurrent report jobs.
- Pause các lịch chạy báo cáo không quan trọng theo policy.
- Dùng maxTimeMS và deadline phù hợp.
- Tăng storage headroom nếu thật sự cần và được phê duyệt.
- Không retry vô hạn một query nặng bị timeout.
- Không tự kill operations ghi dữ liệu khi chưa hiểu tác động.

### Phase D — Fix

| Root cause | Hướng xử lý |
| --- | --- |
| SORT in-memory lớn | Index, filter, top-K |
| GROUP quá nhiều keys | Group đúng granularity |
| GROUP $push quá lớn | Count/sum/top-N, stream detail |
| FACET output lớn | Limit branch, tách endpoint |
| LOOKUP fan-out | Index foreign field, filter/join design |
| WINDOW không bounded | Partition/window phù hợp |
| Stage có thể spill | allowDiskUse với disk/concurrency guardrails |
| Disk pressure | Rate limit, query rewrite, capacity |
| 16 MiB output | Thay shape thành nhiều documents |
| 1.000 stages | Rút gọn pipeline generator |

### Phase E — Verify

- Kết quả business trước/sau tương đương.
- Explain giảm scan/sort/spill hoặc chi phí đã trong budget.
- Disk usage và latency trở lại mức an toàn.
- API p95/p99 và error rate đạt SLO.
- Replication/backup ổn.
- Change record và rollback plan đầy đủ.

### Phase F — Prevent

- Review pipeline khi xuất hiện $push, $facet, $lookup hoặc unbounded window.
- Index lifecycle management.
- Test dataset representative trước release.
- Slow-query/usedDisk monitoring theo budget.
- Job concurrency caps và alert disk headroom.
- Incident ownership và runbook được kiểm chứng.

## 30. Ba case studies điển hình

### 30.1. Case A — Sort 50 triệu events

Query:

~~~javascript
[
  { $match: { tenantId: "tenant-001" } },
  { $sort: { createdAt: -1 } }
]
~~~

Không có index, spill gây latency cao. Cho phép spill có thể giúp hoàn thành nhưng không giảm I/O. Ứng viên sửa là **index {tenantId:1,createdAt:-1}**, và **$limit:N** nếu user chỉ cần N mới nhất. Đo trước/sau, đừng sửa semantics toàn bộ report.

### 30.2. Case B — Một tenant rất nhiều events

~~~javascript
[
  {
    $group: {
      _id: "$tenantId",
      allEvents: { $push: "$$ROOT" }
    }
  }
]
~~~

Lỗi do một array/output quá lớn, allowDiskUse vẫn có thể fail. Nếu yêu cầu chỉ là count/latest:

~~~javascript
[
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 },
      latest: { $max: "$createdAt" }
    }
  }
]
~~~

Nếu cần mọi events, dùng cursor/pagination riêng thay vì một document chứa hàng triệu items.

### 30.3. Case C — Facet vừa summary vừa toàn bộ data

Một $facet trả recent array hàng vạn full documents và summary. Có thể vượt 16 MiB BSON dù chưa vượt 100 MB facet restriction. Tách thành paginated detail endpoint và small facet summary endpoint; cân nhắc consistency policy giữa hai requests nếu dữ liệu thay đổi liên tục.

## 31. Monitoring và guardrails

| Tín hiệu | Rủi ro | Biện pháp |
| --- | --- | --- |
| usedDisk/spill bytes tăng | External I/O lớn | Query fingerprint, index, top-K |
| API p99 vượt SLO | Báo cáo cạnh tranh tài nguyên | Throttle job |
| Memory limit errors tăng | Release đổi query shape | Rollback/disable feature |
| Disk free dưới policy | Temp files + data growth | Giảm tải và capacity |
| Disk latency tăng | I/O contention | Giảm concurrency |
| DocsExamined/NReturned cao | Scan thừa | Index/filter |
| Một shard nóng | Data/query skew | Per-shard analysis |
| Client heap OOM | Buffer toàn cursor | Stream results |

Một report batch chạy spill ban đêm có thể hợp lý; không alert chỉ vì usedDisk=true. Alert khi vượt **resource budget, failed rate hoặc SLO**.

Metrics labels nên bounded: query fingerprint, operation type, stage family, environment, release. Không đưa từng _id hoặc tenantId hàng triệu giá trị thành labels.

## 32. Bảng lỗi thường gặp và phản ứng

| Triệu chứng | Điều cần xác minh |
| --- | --- |
| OOM khi allowDiskUse false | Stage spill-capable và index/query alternatives |
| Vẫn lỗi khi allowDiskUse true | $facet, $push, BSON output, per-op limit |
| Disk tăng mạnh | Concurrent spill, temp files, IO |
| Sort chậm | Index/limit/collation/query shape |
| Group tạo millions keys | Key cardinality/granularity |
| Một group rất lớn | Unbounded array accumulators |
| Facet output lớn | Có bounded branch outputs không |
| Lookup gây nhiều rows | Foreign cardinality/index |
| Graph lookup quá sâu | MaxDepth/cycle/branch fan-out |
| Window quá nặng | Partition/bounded window/index |
| Explain không thấy usedDisk | Data nhỏ, engine/version, chưa spill |
| Client bị OOM | Cursor.toArray/into all rows |
| Query timeout | Server/client/gateway deadline |
| 1.000 stages | Generator tạo pipeline quá dài |
| 16 MiB output lỗi | Gộp toàn bộ rows vào một document |
| Tối ưu làm sai report | Limit/unwind/group đổi semantics |
| Report làm CRUD p99 tăng | Shared disk/CPU contention |

## 33. Checklist trước khi bật allowDiskUse trong production

1. Đã xác định stage gây lỗi.
2. Lỗi không phải non-spill facet/push/BSON limit.
3. Server version và allowDiskUseByDefault đã được xác minh.
4. Đã xem query rewrite/index/top-K trước.
5. Có disk headroom và IOPS budget.
6. Có concurrency/rate limit.
7. Có maxTimeMS và application deadlines.
8. Có monitoring usedDisk, latency, error, disk.
9. Không có side effect bất ngờ từ $merge/$out.
10. Có canary và rollback plan.

## 34. Bài tập thực hành

### Bài 1 — Các loại giới hạn

Phân biệt 100 MB stage memory, 16 MiB document, 1.000 stages và per-operation limit từ 9.0. Vì sao không dùng cùng một cách sửa?

### Bài 2 — Streaming và blocking

So $match/$project với $sort/$group. Vì sao $unwind dù không phải full blocking vẫn có thể gây memory problem downstream?

### Bài 3 — allowDiskUse

Từ MongoDB 6.0, so server allowDiskUseByDefault false/true và per-command override.

### Bài 4 — No spill dù allowed

Một query có allowDiskUse:true nhưng explain không hiện usedDisk. Những lý do hợp lệ là gì?

### Bài 5 — Sort và index

Thiết kế compound index cho query tenantId equality, createdAt desc, _id tie-breaker.

### Bài 6 — Top-K

Giải thích vì sao $sort+$limit thường ít memory hơn full sort và khi nào optimizer không coalesce được.

### Bài 7 — Limit semantics

Vì sao đặt $limit:100 trước $group tổng count tháng làm báo cáo sai?

### Bài 8 — Group cardinality

So group theo 20 tenants với group theo 10 triệu eventIds.

### Bài 9 — $push $$ROOT

Một tenant có 3 triệu events. Vì sao allowDiskUse không bảo đảm group allRows thành công?

### Bài 10 — Accumulator thay thế

Nếu chỉ cần total views và latest event, hãy thay $push bằng $sum/$max.

### Bài 11 — $topN

Viết query lấy 5 events mới nhất mỗi tenant. Nêu business trade-off với allEvents.

### Bài 12 — Facet limits

Phân biệt 100 MB facet document limit không spill và 16 MiB final BSON document limit.

### Bài 13 — Faceted API

Thiết kế recent page và byCity summary không nhét vô hạn rows vào một facet document.

### Bài 14 — Facet index

Vì sao $match nên đứng trước $facet nếu có thể? Khi nào limit trước facet gây sai tổng count?

### Bài 15 — Window

So running views mỗi event với group total views mỗi listing.

### Bài 16 — Bounded window

Phân biệt 10 rows gần nhất với 10 phút gần nhất trong $setWindowFields.

### Bài 17 — Bucket

Thiết kế $bucket cho durationMs chỉ lưu count; vì sao không push toàn bộ ROOT vào bucket?

### Bài 18 — BucketAuto

Khi nào cần bins tự động? Số buckets và data distribution ảnh hưởng thế nào?

### Bài 19 — SortByCount

Viết tương đương $group+$sort. Vì sao limit trước count sai?

### Bài 20 — Lookup

Nếu một local row match 100.000 foreign records, những rủi ro memory/BSON nào có thể xuất hiện?

### Bài 21 — GraphLookup

Nêu cách hạn chế recursion với maxDepth và restrictSearchWithMatch. Tại sao phải xem manual đúng version?

### Bài 22 — MongoDB 9.0

Per-operation memory metrics/limit khác memory stage restriction ra sao? Không được suy diễn điều gì khi server là 8.0?

### Bài 23 — Explain

Tìm winningPlan, nReturned, docsExamined, keysExamined, usedDisk/spills theo version. Chỉ số nào nói đến scan thừa?

### Bài 24 — Profiler

Đọc usedDisk và giải thích vì sao profiler level cao có thể tạo overhead/log PII.

### Bài 25 — Temp disk

10 concurrent reports mỗi job spill 3 GB ước lượng. Những monitoring/concurrency guardrails nào phải có?

### Bài 26 — Client OOM

Vì sao một Java client gọi cursor.into(ArrayList) có thể hết heap dù MongoDB query server chạy thành công?

### Bài 27 — Timeouts

Phân biệt maxTimeMS, socket timeout và HTTP gateway timeout.

### Bài 28 — Lab seed

Chạy 12.000 events lab; xác nhận 4 tenants, mỗi tenant 3.000 records. Vì sao script dùng _id + labTag?

### Bài 29 — Lab sort

So fullSort/topK và explain trước/sau index. Vì sao không được đòi usedDisk=true?

### Bài 30 — Lab group

So count và $push IDs. Nếu dữ liệu tăng từ 3.000 lên 3 triệu items, điều gì thay đổi?

### Bài 31 — Lab facet

Chạy bounded facet và lý giải nguy cơ nếu nhánh recent bỏ limit/projection.

### Bài 32 — Lab cardinality

So group exact timestamp và group theo ngày UTC. Việc đổi sang timezone Asia/Ho_Chi_Minh có thể đổi kết quả thế nào?

### Bài 33 — Lab unwind

Từ 12.000 events, mỗi event có ba syntheticTags, sau unwind bao nhiêu rows? Vì sao count sau unwind có thể sai?

### Bài 34 — Sharded cluster

Một shard spill nhiều, hai shard còn lại không. Hãy lập checklist targeting, hot keys, merge và per-shard resource metrics.

### Bài 35 — Read vs write

Vì sao không tự thêm $out hoặc $merge như một biện pháp “spill” trên production khi chưa có change management?

### Bài 36 — Runbook

Viết các phases impact/isolate/mitigate/fix/verify/prevent cho một report làm API p99 tăng gấp ba.

### Bài 37 — Tổng hợp

Pipeline 50 triệu events có $lookup, $unwind, $sort, $group {$push:"$$ROOT"} và $facet chứa allRows/summary. allowDiskUse:true vẫn lỗi. Hãy liệt kê từng stage gây áp lực, ràng buộc không spill, cách thiết kế lại output/index/query, và kế hoạch kiểm chứng kết quả nghiệp vụ cùng p95/p99.

## 35. Tài liệu tham khảo

- MongoDB Manual — [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/): 100 MB, 16 MiB, 1.000 stages, allowDiskUseByDefault và per-operation memory theo version.
- MongoDB Manual — [Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/).
- MongoDB Manual — [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/).
- MongoDB Manual — [$sort](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/): top-K và memory.
- MongoDB Manual — [$group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/): blocking stage và accumulator limitations.
- MongoDB Manual — [$facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/): non-spill facet limit.
- MongoDB Manual — [$bucket](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucket/).
- MongoDB Manual — [$bucketAuto](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucketAuto/).
- MongoDB Manual — [$sortByCount](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sortByCount/).
- MongoDB Manual — [$setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/).
- MongoDB Manual — [$lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/).
- MongoDB Manual — [$graphLookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/graphLookup/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/).
- MongoDB Manual — [aggregate command](https://www.mongodb.com/docs/manual/reference/command/aggregate/).
- MongoDB Manual — [Sort and Index Use](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/).
- MongoDB Manual — [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/).
- MongoDB Java Sync Driver — [Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/).
- Spring Data MongoDB — [Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html).

**Kết luận:** Để xử lý aggregation MongoDB thiếu bộ nhớ, cần phân biệt **memory của blocking stage, spill tạm ra disk, accumulator không spill được và giới hạn BSON output document**. Những stages như **$sort, $group, $bucket, $bucketAuto, $sortByCount, $setWindowFields** có thể sử dụng temporary files khi điều kiện cho phép, nhưng **$facet không spill**, **$push/$addToSet** có giới hạn tích lũy riêng và **mỗi result document vẫn chịu 16 MiB BSON limit**. Ngoài ra còn có stage-count limit và per-operation memory limit ở các phiên bản mới. Kỹ thuật giải quyết bền vững là **đọc explain/usedDisk, giảm input/state, tận dụng index, sử dụng top-K đúng ngữ nghĩa, tránh arrays không bounded, giới hạn concurrency, đặt deadline, bảo vệ disk headroom và theo dõi p95/p99**. Một report chạy thành công nhờ spill chưa chắc là report khỏe; mục tiêu phải là **kết quả nghiệp vụ chính xác, tài nguyên dự đoán được và không làm suy giảm dịch vụ khác**.

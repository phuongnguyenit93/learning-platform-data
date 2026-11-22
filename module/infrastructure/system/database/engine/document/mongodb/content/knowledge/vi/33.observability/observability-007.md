# currentOp, nhận diện thao tác chạy lâu và điều kiện dùng killOp trong MongoDB

Một ứng dụng gặp hiện tượng API tăng latency từ vài chục mili giây lên nhiều giây. Có người đề xuất “dùng **killOp** để giết query lâu nhất”, nhưng hành động này có thể làm gián đoạn giao dịch, khiến client retry, tạo lỗi hàng loạt hoặc chẳng giải quyết được nguyên nhân thực sự. Trước khi dừng bất kỳ thao tác nào, người vận hành cần trả lời: **thao tác nào đang chạy, ai khởi tạo, nó đang thực thi hay đang chờ, vì sao kéo dài, và việc ngắt có an toàn không?**

MongoDB hỗ trợ quan sát các thao tác đang diễn ra thông qua **$currentOp aggregation stage** và helper **db.currentOp()**. Khi đã xác định một hoạt động do client khởi tạo là không còn cần thiết hoặc có nguy cơ gây ảnh hưởng nghiêm trọng, người có quyền có thể cân nhắc **db.killOp(opid)**. Nhưng đây là **biện pháp can thiệp có điều kiện**, không phải công cụ tối ưu query thông thường.

Bài học thuộc chương **Quan sát hệ thống** và tập trung vào:

1. Các nguồn quan sát: **$currentOp**, **db.currentOp()**, profiler, slow query log, explain và metrics.
2. Những trường cần đọc: **opid, active, secs_running, ns, op, command, appName, client, planSummary, waitingForLock, numYields, progress, lsid, transaction**.
3. Lọc, nhóm và phân loại query chạy lâu theo database, namespace, ứng dụng, host, thao tác và tình trạng chờ.
4. Phân biệt **lâu vì truy vấn tốn tài nguyên** với **lâu vì lock, queue, client chậm, tailable cursor, index build hay transaction**.
5. Phân biệt “đang chạy lâu” và “đáng bị ngắt”.
6. Khi nào có thể dùng **killOp**, khi nào không, cần xác minh gì trước và sau.
7. Sự khác nhau giữa **mongod, replica set, mongos và sharded cluster**.
8. Chủ động phòng ngừa bằng **maxTimeMS**, giới hạn batch, index phù hợp, applicationName và query comments.
9. Runbook vận hành, ví dụ mongosh/Node.js/Java, tình huống lỗi và bài tập.

**Nguyên tắc an toàn xuyên suốt:** chỉ dùng **killOp với thao tác được client khởi tạo** sau khi đã xác minh chính xác opid, host, chủ sở hữu, tác động và quyền can thiệp. **Không kill hoạt động nội bộ của MongoDB** như replication, checkpoint, balancer hoặc những công việc hệ thống chỉ vì chúng xuất hiện trong currentOp.

## 1. “Truy vấn chạy lâu” nghĩa là gì?

Một query được xem là **long-running** khi thời gian thực thi vượt ngưỡng được xác định theo **SLA của workload** và đáng điều tra. Không có một con số chung áp dụng cho mọi hệ thống.

Ví dụ:

| Workload | Mục tiêu minh họa | Khi nào cần chú ý |
|---|---|---|
| API đọc một đơn hàng theo ID | p95 dưới 100 ms | Một query 3 giây có thể bất thường |
| API tổng hợp báo cáo trong ngày | p95 dưới 2 giây | 15 giây có thể là sự cố |
| Export dữ liệu nền có giới hạn | Hoàn tất trong vài phút | 30 giây có thể hoàn toàn bình thường |
| Index build theo kế hoạch | Có thể kéo dài nhiều phút | Không được kill chỉ vì lâu |
| Change stream chờ dữ liệu | Cố ý đợi sự kiện | Thời gian chờ dài không tự là lỗi |

Những số liệu trên **chỉ là ví dụ về SLO**; cần chọn ngưỡng theo ứng dụng thật.

### 1.1. Query duration khác request duration

Một request có thể đi qua:

~~~text
HTTP request
    |
    v
Application queue / authentication
    |
    v
Connection pool checkout
    |
    v
Send MongoDB command
    |
    v
MongoDB operation observed in currentOp
    |
    v
Read result batches / deserialize
    |
    v
Application processing / response
~~~

**$currentOp** quan sát thao tác MongoDB hiện tại, **không đo toàn bộ thời gian request ở tầng ứng dụng**. Nếu ứng dụng kẹt 10 giây trong connection pool rồi query chỉ chạy 5 ms, currentOp sẽ không báo một query chạy 10 giây.

### 1.2. Lâu không đồng nghĩa có hại

Một thao tác export lâu nhưng được lên lịch đúng giờ, dùng read preference phù hợp và không làm ảnh hưởng SLA có thể **không cần can thiệp**.

Ngược lại, một query mới chạy 1 giây nhưng đang **giữ lock hoặc đẩy hệ thống vào tình trạng nghẽn nghiêm trọng** có thể đáng ưu tiên hơn một report query chạy 30 giây mà không ảnh hưởng người dùng.

Quyết định phải dựa vào **nguyên nhân + tác động + mức khẩn cấp**, không chỉ một phép so sánh với ngưỡng.

## 2. currentOp là gì và nên dùng API nào?

MongoDB cung cấp một số giao diện liên quan:

| Giao diện | Vai trò | Khuyến nghị |
|---|---|---|
| **$currentOp** aggregation stage | Trả stream document về operations/sessions, cho phép $match/$project/$sort | **Ưu tiên** để quan sát hiện tại |
| **db.currentOp()** | Mongosh helper để xem current operations và lọc nhanh | Hữu ích cho chẩn đoán nhanh |
| **currentOp database command** | Lệnh backend cũ | Không ưu tiên; đã deprecated từ MongoDB 6.2 |
| **system.profile / profiler** | Lưu thông tin operations đã chạy theo cấu hình profiling | Phù hợp tìm lịch sử truy vấn chậm |
| **Slow query logs / Atlas Query Profiler** | Quan sát truy vấn chậm trong khoảng thời gian | Phù hợp điều tra sự kiện đã kết thúc |
| **explain()** | Phân tích execution plan của query có thể tái hiện | Hữu ích tìm vấn đề index/plan |

Theo tài liệu MongoDB hiện hành, **$currentOp được khuyến nghị thay cho currentOp command**. **db.currentOp() vẫn là helper có ích**, nhưng vì có khác biệt triển khai/giới hạn theo mongosh và phiên bản nên các ví dụ trọng tâm dùng **$currentOp**.

### 2.1. currentOp là ảnh chụp tại một thời điểm

~~~text
10:00:00.000   Query A starts
10:00:00.020   Query B starts
10:00:00.060   Query A finishes
10:00:00.100   Operator runs $currentOp
10:00:00.200   Query B finishes
~~~

Lúc 10:00:00.100, currentOp có thể thấy Query B nhưng **không còn thấy Query A**. Vì vậy:

- Query không xuất hiện trong currentOp **không chứng minh nó chưa từng chậm**.
- Muốn xem lịch sử, cần profiler, slow-query log hoặc APM.
- Muốn giám sát liên tục, cần thu thập có giới hạn và hệ thống metric theo thời gian.

### 2.2. $currentOp không phải một collection nghiệp vụ

Bạn không viết:

~~~javascript
db.orders.find({ "$currentOp": {} });
~~~

Đúng cách là chạy **aggregation pipeline trên database admin** với **$currentOp là stage đầu tiên**:

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleConnections: false
    }
  }
]);
~~~

Đây là **lệnh quan sát**, không thay đổi dữ liệu ứng dụng. Nhưng dữ liệu phản hồi có thể chứa command/filter, thông tin client, namespace và metadata nhạy cảm; cần giữ quyền truy cập phù hợp.

### 2.3. Điều kiện chạy và quyền

Trên deployment đã bật authorization:

- Để quan sát operations của **mọi user**, cần quyền **inprog** phù hợp.
- Trên standalone/replica set, khi chỉ quan sát operations của chính mình có thể không cần quyền inprog mở rộng.
- Trên sharded cluster, việc dùng $currentOp có yêu cầu quyền **inprog** theo tài liệu.
- Những cluster Atlas tier nhất định như **M0/Flex** không hỗ trợ lệnh/helper currentOp như cluster lớn; cần kiểm tra khả năng của tier.

Một ứng dụng kinh doanh thông thường **không nên được cấp inprog/killop chỉ để phục vụ API**. Tách tài khoản quan sát/on-call và tài khoản thao tác nghiệp vụ.

## 3. Cú pháp $currentOp cơ bản

### 3.1. Chỉ xem operations của user hiện tại

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: false,
      idleConnections: false
    }
  }
]);
~~~

**allUsers: false** giới hạn phạm vi về user đang chạy lệnh. Cấu hình quyền và topology vẫn ảnh hưởng khả năng quan sát.

### 3.2. Xem mọi active operations từ mọi user

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleConnections: false
    }
  },
  {
    $match: {
      active: true
    }
  }
]);
~~~

**allUsers: true** yêu cầu quyền phù hợp; không đưa thẳng quyền này cho tài khoản ứng dụng.

### 3.3. Những thao tác chạy quá 5 giây

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleConnections: false
    }
  },
  {
    $match: {
      active: true,
      secs_running: { $gte: 5 }
    }
  },
  {
    $sort: {
      secs_running: -1
    }
  }
]);
~~~

**secs_running** chỉ xuất hiện khi operation đang chạy. Đây là số thời gian kể từ khi thao tác bắt đầu, **không phải CPU time** và cũng không tự chứng minh query thật sự đang dùng CPU toàn bộ thời gian ấy.

### 3.4. Projection ngắn, tránh in cả command nhạy cảm

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleConnections: false
    }
  },
  {
    $match: {
      active: true,
      secs_running: { $gte: 5 }
    }
  },
  {
    $project: {
      _id: 0,
      host: 1,
      shard: 1,
      opid: 1,
      op: 1,
      ns: 1,
      appName: 1,
      active: 1,
      secs_running: 1,
      waitingForLock: 1,
      planSummary: 1,
      numYields: 1,
      msg: 1,
      "command.comment": 1
    }
  },
  {
    $sort: {
      secs_running: -1
    }
  }
]);
~~~

Việc chỉ project **command.comment** giúp giảm nguy cơ hiển thị literal nhạy cảm trong filter. Nhưng **comment cũng có thể chứa dữ liệu nhạy cảm nếu ứng dụng ghi sai**, nên chỉ dùng ID/tag không có PII.

### 3.5. $currentOp phải đứng đầu

Không viết:

~~~javascript
// Sai cấu trúc:
db.getSiblingDB("admin").aggregate([
  { $match: { active: true } },
  { $currentOp: {} }
]);
~~~

Đúng:

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: {} },
  { $match: { active: true } }
]);
~~~

Stage **$currentOp phải là stage đầu tiên**, và pipeline bắt đầu bằng $currentOp phải chạy trên **admin database**. Nó không được phép bên trong một transaction.

## 4. db.currentOp() để kiểm tra nhanh

Mongosh helper có thể nhận filter:

~~~javascript
db.currentOp();
~~~

Hoặc:

~~~javascript
db.currentOp({
  active: true,
  secs_running: { $gt: 3 }
});
~~~

Truy vấn theo namespace:

~~~javascript
db.currentOp({
  active: true,
  ns: /^sales\./
});
~~~

Xem operations đang chờ lock:

~~~javascript
db.currentOp({
  waitingForLock: true
});
~~~

Xem operations của user hiện tại trên mongod:

~~~javascript
db.currentOp({
  "$ownOps": true
});
~~~

Tham số **true** trong db.currentOp(true) bao gồm cả operations trên idle connections và system operations; **không dùng true làm bộ lọc “chỉ những query đang chạy”**.

**Lưu ý phiên bản:** currentOp command đã deprecated từ MongoDB 6.2; trong các bản mongosh mới, helper có thể sử dụng $currentOp bên dưới. Để xử lý tập kết quả lớn và thuận tiện projection/filter, ưu tiên $currentOp aggregation stage.

## 5. Cách đọc output của currentOp

Một document điển hình được minh họa như sau. Tùy **version, topology, operation type, permissions**, không phải field nào cũng luôn có mặt.

~~~javascript
{
  type: "op",
  host: "db-primary.example.net:27017",
  desc: "conn128",
  client: "198.51.100.25:53124",
  appName: "orders-api",
  active: true,
  opid: 81042,
  secs_running: Long("18"),
  microsecs_running: 18233000,
  op: "command",
  ns: "shop.orders",
  command: {
    find: "orders",
    filter: { status: "PENDING" },
    comment: "orders-api:pending-dashboard",
    "$db": "shop"
  },
  planSummary: "COLLSCAN",
  waitingForLock: false,
  numYields: 25,
  killPending: false
}
~~~

Đây là **output giả lập** nhằm giải thích trường, không phải kết quả của một query đã chạy trên database thật.

### 5.1. type và op

**type** giúp phân biệt các loại document quan sát:

- **op**: thao tác đang hoặc đã được gắn với operation.
- **idleSession**: session không có thao tác active, có thể liên quan transaction.
- **idleCursor**: cursor nhàn rỗi trong những cấu hình thu thập có bật.

**op** thường có giá trị:

~~~text
command
query
update
insert
remove
getmore
killcursors
none
~~~

Nhiều truy vấn hiện đại có **op: "command"**, nên filter chỉ **op: "query"** có thể bỏ sót find, aggregate hoặc các command khác.

### 5.2. opid

**opid** là định danh dùng để tham chiếu tới một operation khi chẩn đoán và có thể dùng với **db.killOp(opid)**.

Không nhầm:

| Trường | Ý nghĩa |
|---|---|
| opid | Định danh operation hiện tại, dùng khi cân nhắc killOp |
| connectionId | Định danh kết nối nơi operation được xử lý |
| lsid | Logical session identifier |
| cursorId | Định danh cursor |
| requestId / comment | Giá trị correlation do ứng dụng cung cấp |
| txnNumber | Định danh transaction trong session, không phải opid |

**Một operation ID không phải “query ID toàn cục tồn tại mãi mãi”.** Operation có thể kết thúc và ID không còn khả dụng. Khi định ngắt phải xác minh ngay trước thao tác, bao gồm **host/shard và nội dung command**.

### 5.3. active và secs_running

~~~javascript
{
  active: true,
  secs_running: 22
}
~~~

Nghĩa là operation được MongoDB xem đang chạy và đã trôi qua khoảng 22 giây từ khi bắt đầu. Nó có thể:

- Đang thực hiện collection/index scan.
- Đang sort/aggregate.
- Đang chờ lock hoặc admission/queue.
- Đang giữ một thao tác đang đợi client/server/event ở trạng thái được xem active.

**active: true không có nghĩa đang chiếm 100% CPU.** Cần đọc thêm trạng thái chờ và metrics hệ thống.

### 5.4. ns

**ns** là namespace **database.collection**:

~~~text
shop.orders
analytics.events
admin.$cmd
~~~

Với một số command, ns có thể là namespace lệnh hoặc giá trị khác mục tiêu business collection. Vì vậy, nếu lọc theo ns mà không thấy operation, kiểm tra thêm **command.find**, **command.aggregate**, **command.update** hoặc **originatingCommand**, tùy operation.

### 5.5. command

**command** thường mô tả thao tác đang thực hiện:

~~~javascript
{
  find: "orders",
  filter: {
    status: "PENDING"
  },
  sort: {
    createdAt: -1
  },
  comment: "orders-api:pending-dashboard"
}
~~~

Điều này giúp nhận biết query pattern và application path, nhưng có thể chứa **literal nhạy cảm**. Dùng projection/chính sách truy cập log để không phát tán taxId, email, token hoặc dữ liệu khách hàng.

Với **Queryable Encryption**, MongoDB có cơ chế **redaction** khiến một số thành phần command/output currentOp không xuất hiện đầy đủ. Không coi command bị lược là bằng chứng không có query.

### 5.6. client, appName và clientMetadata

~~~javascript
{
  appName: "payment-worker",
  client: "198.51.100.45:49300",
  clientMetadata: {
    driver: { name: "mongo-java-driver", version: "..." }
  }
}
~~~

- **appName** giúp phân biệt backend service, batch job và reporting tool.
- **client** giúp xác định kết nối đến từ đâu.
- **clientMetadata** cho biết driver/platform khi sẵn có.

Thiết kế tốt nên đặt **applicationName** trong connection settings, và có **comment** ở các query quan trọng để điều tra chính xác theo endpoint/job.

### 5.7. planSummary

Một số giá trị thông thường:

| planSummary | Diễn giải khái quát |
|---|---|
| COLLSCAN | Scan collection; có thể rất tốn kém với filter kém chọn lọc |
| IXSCAN | Scan index; chưa chắc index tốt hoặc đã tối ưu toàn bộ query |
| Có cả IXSCAN và những stages khác | Phải xem explain để biết fetch/sort/filter |
| Field không xuất hiện | Không suy ra query đã dùng index hoặc không dùng index |

**COLLSCAN không luôn là lỗi.** Với collection rất nhỏ hoặc query cần đọc gần toàn bộ dữ liệu, scan có thể chấp nhận. Ngược lại **IXSCAN** vẫn có thể chậm nếu quét quá nhiều index keys rồi fetch nhiều documents.

### 5.8. waitingForLock

~~~javascript
{
  waitingForLock: true
}
~~~

Cho biết operation đang chờ lock. Đừng kết luận query thiếu index trước khi điều tra **holder/blocker** và tình trạng transaction.

Một lock wait dài có thể đến từ một transaction mở lâu, thao tác schema, hoặc một workload khác. **Kill một waiter** có thể giảm số requests đang treo nhưng không giải quyết root cause nếu lock holder tiếp tục giữ lock.

### 5.9. numYields

**numYields** cho biết số lần operation yield theo cơ chế MongoDB:

~~~javascript
{
  numYields: 250
}
~~~

Giá trị lớn có thể xuất hiện ở query kéo dài, nhưng **không phải số lượng CPU preemptions** và không đủ để xác định lỗi. Cần đặt trong ngữ cảnh operation, plan, locks, index usage và workload.

### 5.10. locks và lockStats

Một số output có:

~~~javascript
{
  locks: {
    Global: "r",
    Database: "r",
    Collection: "r"
  },
  lockStats: {
    Collection: {
      acquireCount: { r: Long("12") },
      acquireWaitCount: { r: Long("2") },
      timeAcquiringMicros: { r: Long("85000") }
    }
  }
}
~~~

Các thông tin trên có thể cho thấy mức độ chờ lock. **Ký hiệu lock mode và cấu trúc lockStats thay đổi theo loại operation/version**, nên không quy đổi trực tiếp “r = read-only nên không ảnh hưởng”.

### 5.11. msg và progress

Một số thao tác như xây index có thể xuất hiện:

~~~javascript
{
  msg: "Index Build: ...",
  progress: {
    done: 820000,
    total: 1000000
  }
}
~~~

Nếu thấy **progress tăng**, thao tác có thể đang tiến triển theo kế hoạch. Không tự kill vì secs_running lớn. Phải biết operation đang là một **migration/index build hợp lệ** hay không và quy trình thay đổi có cho phép ngắt.

### 5.12. killPending

~~~javascript
{
  killPending: true
}
~~~

Cho biết operation đã bị yêu cầu ngắt nhưng có thể **chưa dừng ngay**. KillOp thường được xử lý tại **interrupt point**, không phải một tín hiệu bảo đảm operation biến mất tức thì.

### 5.13. lsid và transaction

Operation thuộc multi-document transaction có thể bao gồm:

~~~javascript
{
  lsid: { id: UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa") },
  transaction: {
    timeOpenMicros: Long("60000000"),
    timeActiveMicros: Long("2000000"),
    timeInactiveMicros: Long("58000000")
  }
}
~~~

Đây là ví dụ rút gọn. Một transaction **mở 60 giây** nhưng chỉ hoạt động 2 giây có thể gây áp lực lên snapshot/history hoặc lock dù không có query active lâu liên tục. Để quan sát transaction idle cần **idleSessions: true** trong $currentOp.

### 5.14. cursor và getMore

Một query ban đầu có thể kết thúc nhưng cursor vẫn tồn tại và client tiếp tục gọi **getMore** để nhận thêm dữ liệu.

~~~javascript
{
  op: "getmore",
  command: {
    getMore: Long("1234567890"),
    collection: "events",
    batchSize: 500
  },
  cursor: {
    cursorId: Long("1234567890"),
    tailable: false,
    awaitData: false
  }
}
~~~

Một **change stream/tailable cursor với awaitData** có thể chờ sự kiện trong thời gian được thiết kế. Không kết luận một getMore lâu là lỗi scan và không kill một change stream production chỉ dựa vào secs_running.

## 6. Những trường có ý nghĩa khác nhau theo phiên bản

MongoDB tăng cường currentOp output theo các release. Ví dụ:

- MongoDB 8.0 bổ sung những thông tin về **admission queues/currentQueue**.
- MongoDB 8.2 có một số field như **versionContext** cho FCV operation.
- Những metrics bộ nhớ theo operation có thể xuất hiện ở các phiên bản mới hơn.
- Sharded cluster bổ sung **shard**, **client_s** và thông tin liên quan routing.

Vì vậy, không viết alert như:

~~~javascript
// Dễ sai: assume mọi operation trên mọi version có planSummary.
{ $match: { planSummary: "COLLSCAN" } }
~~~

rồi kết luận những operations khác đều tối ưu. Có thể dùng field khi tồn tại, và đánh giá **fallback hoặc nhánh theo phiên bản**.

## 7. Mẫu lọc currentOp theo từng mục tiêu

Trong thực tế, một lệnh dump mọi operation có thể trả quá nhiều thông tin. Nên bắt đầu từ bộ lọc đúng câu hỏi vận hành.

### 7.1. Top operations lâu nhất

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true, idleConnections: false } },
  {
    $match: {
      type: "op",
      active: true,
      secs_running: { $gte: 5 }
    }
  },
  { $sort: { secs_running: -1 } },
  { $limit: 20 },
  {
    $project: {
      _id: 0,
      opid: 1,
      host: 1,
      shard: 1,
      secs_running: 1,
      ns: 1,
      op: 1,
      appName: 1,
      waitingForLock: 1,
      planSummary: 1,
      "command.comment": 1
    }
  }
]);
~~~

Đây là một cách lấy **top 20 theo thời gian đã chạy**, không phải 20 operation tiêu tốn CPU nhất.

### 7.2. Lọc theo database hoặc collection

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      ns: "shop.orders"
    }
  }
]);
~~~

Nếu truy vấn là **command với ns không trùng collection business**, có thể cần thêm filter theo **command.find**, **command.aggregate** hoặc đối chiếu operation bằng **comment**. Không vội kết luận collection không có query chạy.

### 7.3. Lọc theo tên ứng dụng

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      appName: "billing-service"
    }
  },
  {
    $project: {
      opid: 1,
      host: 1,
      ns: 1,
      secs_running: 1,
      appName: 1,
      "command.comment": 1
    }
  }
]);
~~~

Để filter có giá trị, các services phải dùng **applicationName** nhất quán. Nếu mọi kết nối đều có appName rỗng hoặc tên chung, không thể dễ dàng quy trách nhiệm theo service.

### 7.4. Lọc những operations đang chờ lock

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      waitingForLock: true
    }
  },
  {
    $project: {
      host: 1,
      opid: 1,
      ns: 1,
      secs_running: 1,
      appName: 1,
      lockStats: 1,
      waitingForLock: 1
    }
  }
]);
~~~

Một danh sách dài waiters nên khiến bạn **tìm nguyên nhân chặn và holder** trước khi cân nhắc kill một waiter bất kỳ.

### 7.5. Lọc các COLLSCAN đang kéo dài

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      secs_running: { $gte: 10 },
      planSummary: /COLLSCAN/
    }
  },
  {
    $project: {
      host: 1,
      opid: 1,
      ns: 1,
      secs_running: 1,
      planSummary: 1,
      "command.comment": 1
    }
  }
]);
~~~

Đây chỉ là **tín hiệu điều tra**. Scan collection có thể là lựa chọn hợp lý với dataset nhỏ hoặc truy vấn đòi nhiều documents; cần **explain** và số liệu thực trước khi tạo index.

### 7.6. Lọc theo comment an toàn

Ứng dụng nên gửi **comment không chứa dữ liệu nhạy cảm**:

~~~text
orders-api:list-pending:v2
billing-worker:reconcile-hourly
analytics:export-daily
~~~

Khi currentOp có field command.comment:

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      "command.comment": "orders-api:list-pending:v2"
    }
  }
]);
~~~

**Comment có thể không hiện ở vị trí này với mọi command/getMore, hoặc có thể bị redacted**. Với getMore, xem **cursor.originatingCommand.comment** khi khả dụng.

### 7.7. Lọc write operations

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      $or: [
        { op: { $in: ["insert", "update", "remove"] } },
        { "command.update": { $exists: true } },
        { "command.delete": { $exists: true } },
        { "command.findAndModify": { $exists: true } }
      ]
    }
  }
]);
~~~

Các command names trong output có thể khác về cách viết/namespace theo driver và version, nên truy vấn này chỉ là **mẫu lọc**, không phải danh sách bao phủ 100% write activity.

### 7.8. Nhóm số operations theo appName

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  { $match: { active: true, type: "op" } },
  {
    $group: {
      _id: "$appName",
      activeCount: { $sum: 1 },
      maxSecs: { $max: "$secs_running" }
    }
  },
  { $sort: { activeCount: -1 } }
]);
~~~

Kết quả là **snapshot của số operations đang active**, không phải throughput operations/second. Để tính QPS, cần metrics theo thời gian hoặc command monitoring ở tầng ứng dụng.

### 7.9. Quan sát các inactive transactions

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleSessions: true
    }
  },
  {
    $match: {
      type: "idleSession",
      transaction: { $exists: true }
    }
  },
  {
    $project: {
      host: 1,
      lsid: 1,
      appName: 1,
      active: 1,
      "transaction.timeOpenMicros": 1,
      "transaction.timeActiveMicros": 1,
      "transaction.timeInactiveMicros": 1
    }
  }
]);
~~~

Điều này giúp tìm **transaction đang mở nhưng không có active query**. Trong một số trường hợp, transaction idle vẫn giữ tài nguyên/locks. Không có opid active tương ứng để killOp như một query thông thường; cần xử lý vòng đời session/transaction bằng cơ chế phù hợp.

### 7.10. Quan sát idle cursors

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleCursors: true
    }
  },
  {
    $match: {
      type: "idleCursor"
    }
  },
  {
    $project: {
      host: 1,
      appName: 1,
      ns: 1,
      "cursor.cursorId": 1,
      "cursor.createdDate": 1,
      "cursor.lastAccessDate": 1,
      "cursor.noCursorTimeout": 1,
      "cursor.tailable": 1
    }
  }
]);
~~~

Idle cursor không giống query đang tính toán. Với cursor mở lâu, cần xem **driver đã đóng cursor chưa**, có đang stream dữ liệu cố ý không, và chính sách idle timeout phù hợp.

### 7.11. Quan sát index build, không tự giết

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleConnections: true
    }
  },
  {
    $match: {
      $or: [
        { "command.createIndexes": { $exists: true } },
        { op: "none", msg: /^Index Build/ }
      ]
    }
  },
  {
    $project: {
      host: 1,
      opid: 1,
      msg: 1,
      progress: 1,
      secs_running: 1,
      ns: 1
    }
  }
]);
~~~

Đây là pattern từ tài liệu MongoDB để điều tra index builds, **không áp dụng cho mọi kiểu rolling index build**. Một index build có thể tiêu tốn tài nguyên và kéo dài; nếu đang chạy theo change window, phải phối hợp DBA/on-call trước bất kỳ biện pháp can thiệp nào.

## 8. Phân loại nguyên nhân một thao tác chạy lâu

Một cách điều tra hữu ích là chia nguyên nhân thành những nhóm:

| Nhóm | Tín hiệu thường gặp | Bước tiếp theo |
|---|---|---|
| Query plan/index kém | COLLSCAN, nhiều keys/docs examined, filter/sort đắt | explain, xem index/query shape |
| Waiting for lock | waitingForLock=true, lockStats | tìm blocker/transaction/schema operations |
| Admission/resource queue | currentQueue/queues, CPU/I/O bão hòa | đo pool, admission, tài nguyên |
| Large sort/aggregation | sort/group lớn, spill, temp disk | explain, rewrite/index/memory |
| getMore/streaming | op=getmore, cursor awaitData | kiểm tra client, batch, change stream |
| Index build/migration | msg/progress, createIndexes | đối chiếu change plan/progress |
| Long transaction | transaction.timeOpenMicros cao | xem snapshot/locks/owner, abort policy |
| Sharded routing | mongos/shards, scatter-gather | shard targeting, query routing |
| Network/client | server operation bình thường nhưng API chậm | connection pool, network, downstream |
| Replication/flow control | waitingForFlowControl, lag, write concern | topology/replication metrics |

Một hiện tượng có thể thuộc **nhiều nhóm**. Chẳng hạn query kém index gây I/O cao, dẫn đến queue tăng và query khác phải chờ. Kill một query chỉ xử lý **triệu chứng tức thời**, còn nguyên nhân index/workload vẫn tồn tại.

## 9. Chậm do query plan hoặc index không phù hợp

Một ví dụ:

~~~javascript
db.orders.find({
  tenantId: "T-001",
  status: "PENDING"
}).sort({ createdAt: -1 }).limit(50);
~~~

Nếu collection có hàng triệu documents nhưng không có index phản ánh filter và sort, query có thể scan rất nhiều documents hoặc sort sau khi scan.

### 9.1. Dùng currentOp để lấy dấu hiệu

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      secs_running: { $gte: 5 },
      ns: "shop.orders"
    }
  },
  {
    $project: {
      opid: 1,
      secs_running: 1,
      planSummary: 1,
      waitingForLock: 1,
      "command.comment": 1
    }
  }
]);
~~~

Nếu thấy **COLLSCAN** và **waitingForLock=false**, đó là một dấu hiệu nghi ngờ plan. Nhưng currentOp chỉ cung cấp **ảnh chụp**, không cho biết toàn bộ số documents examined trong mọi trường hợp.

### 9.2. Dùng explain để phân tích khi an toàn

~~~javascript
db.getSiblingDB("shop").orders
  .find({
    tenantId: "T-001",
    status: "PENDING"
  })
  .sort({ createdAt: -1 })
  .limit(50)
  .explain("executionStats");
~~~

**Lưu ý quan trọng:** explain có thể khiến server thực thi công việc đáng kể. Trên production đang nghẽn, không tự chạy explain executionStats đối với một query rất nặng mà không kiểm soát chi phí. Có thể bắt đầu từ **queryPlanner** hoặc môi trường staging có dữ liệu đại diện, rồi đo có giới hạn.

### 9.3. Những chỉ số explain thường hữu ích

- **winningPlan**: cách thực hiện được chọn.
- **COLLSCAN/IXSCAN**: scan collection/index.
- **totalKeysExamined**: số index entries được xem xét.
- **totalDocsExamined**: số documents được đọc/kiểm tra.
- **nReturned**: số documents kết quả.
- **SORT** stage: sort chưa được giải quyết hoàn toàn bởi index.
- Thời gian executionStats: có ích nhưng không thay được p95 end-to-end metrics.

Ví dụ:

~~~text
nReturned          = 50
totalDocsExamined  = 900000
totalKeysExamined  = 0
planSummary        = COLLSCAN
~~~

Trong nhiều workload, đây là tín hiệu rất đáng xem lại index hoặc query pattern.

### 9.4. Hướng thiết kế index

Với query filter equality trên tenantId/status và sort descending createdAt:

~~~javascript
db.getSiblingDB("shop").orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

Index ví dụ phản ánh **Equality → Sort** cho pattern này. Nhưng không nên tạo index trên production chỉ sau khi nhìn thấy một currentOp: cần đánh giá index hiện có, write overhead, cardinality, frequency, query patterns và rollout.

### 9.5. Một index không chữa được mọi operation lâu

Nếu query đang chờ lock, build index mới có thể làm hệ thống càng nặng. Nếu API chậm do connection pool hoặc external service, index database không giải quyết vấn đề. Phải xác định nguyên nhân trước.

## 10. Chậm do lock, transaction và điều kiện chờ

### 10.1. WaitingForLock: tìm waiter và blocker

Giả sử:

~~~text
Operation A: schema change/transaction giữ resource
              |
              v
Operation B: update đang chờ lock
              |
              v
Operation C: another update đang chờ
~~~

CurrentOp có thể cho biết B/C **waitingForLock=true**, nhưng không phải lúc nào cũng cung cấp đầy đủ một cây wait-for graph nêu chính xác blocker.

Đừng chạy:

~~~javascript
// Không phải hành động hợp lý mặc định:
db.killOp(opidOfWaiter);
~~~

chỉ vì một waiter đang chờ. Nếu blocker vẫn tồn tại, request tiếp theo có thể lại kẹt.

### 10.2. Transaction mở lâu nhưng không active

Một transaction có thể:

~~~text
BEGIN TRANSACTION
      |
      v
UPDATE document
      |
      v
Application chờ một API ngoài
      |
      v
Transaction vẫn mở
~~~

Nó có thể giữ snapshot/history hoặc locks tùy thao tác và storage engine, dù không có active operation liên tục trong currentOp.

Xem:

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleSessions: true
    }
  },
  {
    $match: {
      type: "idleSession",
      transaction: { $exists: true }
    }
  },
  {
    $project: {
      lsid: 1,
      appName: 1,
      "transaction.timeOpenMicros": 1,
      "transaction.timeInactiveMicros": 1
    }
  }
]);
~~~

Đây là trường hợp cần làm việc với **session/transaction owner**. Không tự nhầm lsid với opid để gọi db.killOp().

### 10.3. Lock wait và writeConflict khác nhau

MongoDB có cơ chế concurrency và **write conflicts**. Một operation có writeConflict cao không nhất thiết đang **waitingForLock**:

- Lock wait có thể là chờ một lock mode.
- Write conflict thường xảy ra khi hai operations tranh chấp cập nhật cùng dữ liệu/record, dẫn đến retry hoặc lỗi tùy ngữ cảnh.
- Transaction có thể bị abort do write conflict và cần retry tại client.

Phân biệt bằng currentOp nếu field có, logs, profiler và application error metrics. Không dùng killOp làm cơ chế quản lý concurrency lâu dài.

### 10.4. Admission queue và tài nguyên

MongoDB hiện đại có thông tin **currentQueue/queues** trên các version hỗ trợ. Ví dụ một operation có thể đang đợi admission vào execution dù chưa chiếm CPU thực thi.

Nếu nhiều operations chờ vì CPU/I/O và queue tăng, có thể cần:

- Giảm concurrency đầu vào.
- Giới hạn batch workload hoặc background jobs.
- Tối ưu query/plan.
- Xem tài nguyên cluster và scaling.
- Kiểm tra connection pool và retry storm.

**Kill operations** có thể giải phóng một số request đang chờ, nhưng nếu traffic không giảm thì queue sẽ đầy trở lại.

### 10.5. Flow control và replication

Trong replica set, write có thể gặp **flow control** hoặc chờ đáp ứng write concern/replication. Một số thông tin như **waitingForFlowControl**, replication lag và metrics liên quan giúp chẩn đoán.

Nếu write chậm do replication lag, kill một writer không sửa được mạng giữa nodes hoặc tốc độ apply của secondary. Hãy xem replica set health và write concern theo yêu cầu dữ liệu.

## 11. getMore, cursors và change streams

### 11.1. Vòng đời của cursor

~~~text
find / aggregate
      |
      v
Initial batch
      |
      v
Cursor remains open
      |
      +--> getMore batch 2
      |
      +--> getMore batch 3
      |
      +--> Cursor exhausted / closed / timed out
~~~

Không nên chỉ xem thao tác find ban đầu rồi bỏ qua hàng loạt **getMore** có thể chiếm phần lớn thời gian đọc dữ liệu.

### 11.2. getMore có thể chờ client hoặc dữ liệu mới

Với tailable cursor/change stream:

~~~text
getMore
   |
   v
Await next event (by design)
   |
   +--> Event arrives
   |
   +--> Await time limit
~~~

Một getMore kéo dài có thể là hành vi bình thường, nhất là khi **awaitData=true**. Điều tra phải xem **cursor.tailable**, **cursor.awaitData**, **originatingCommand**, appName và purpose.

### 11.3. Idle cursor và leak

Ứng dụng bỏ quên đóng cursor có thể để cursor idle lâu, nhất là khi dùng noCursorTimeout. Điều tra:

- Cursor được tạo bởi endpoint/job nào?
- Có đang stream dữ liệu cố ý không?
- Last access có cập nhật không?
- Driver có đóng cursor sau exception không?
- Có giới hạn số concurrent cursors không?

Trong Java, nên dùng try-with-resources khi có cursor:

~~~java
try (MongoCursor<Document> cursor =
        collection.find(filter).iterator()) {
    while (cursor.hasNext()) {
        Document item = cursor.next();
        process(item);
    }
}
~~~

**killOp** không phải lựa chọn mặc định cho idle cursor; driver chủ quản nên đóng cursor hoặc dùng API quản lý cursor/session thích hợp.

### 11.4. Query đã bị kill nhưng client retry

Nếu hệ thống tự động retry một read, ngay sau khi killOp, bạn có thể thấy **operation mới có opid mới**. Vì vậy, nếu một endpoint đang tạo nhiều truy vấn nặng lặp lại:

1. Giảm hoặc chặn traffic của endpoint/job.
2. Xác nhận query hoặc transaction nào cần dừng.
3. Nếu vẫn cần, kill một operation có kiểm soát.
4. Theo dõi retry/error rate và operations mới.

Nếu chỉ kill từng opid trong vòng lặp, bạn có thể tạo **vòng lặp kill–retry**, làm hệ thống không ổn định hơn.

## 12. So sánh currentOp với profiler, logs và explain

| Công cụ | Nhìn được gì? | Không thay thế được gì? |
|---|---|---|
| $currentOp | Snapshot operations đang active/idle | Không cho lịch sử đầy đủ |
| db.currentOp() | Snapshot nhanh theo filter | Không phải API ưu tiên cho pipeline lớn |
| Profiler / system.profile | Thao tác đã xảy ra, chi tiết theo cấu hình | Có overhead, không phải live snapshot |
| Slow query logs | Sự kiện chậm có log | Không đủ nếu sampling/threshold bỏ sót |
| explain | Query plan, stages, statistics | Không thể suy ra mọi incident từ một lần chạy |
| Atlas metrics | CPU, connections, I/O, replication, cache, ops | Không chỉ ra một query riêng lẻ nếu không correlate |
| Application traces | Thời gian endpoint, query comment/correlation | Không thể xem internal state của MongoDB |

### 12.1. Profiler dùng khi operation đã kết thúc

Khi một query chạy 12 giây nhưng đã hoàn thành trước khi on-call mở mongosh, **$currentOp không còn thấy nó**.

Khi đó xem:

- Database profiler nếu được bật theo policy.
- Slow operations log.
- Atlas Query Profiler/Query Insights nếu deployment hỗ trợ.
- Application APM traces và command monitoring.

**Profiler có overhead và có thể lưu query metadata nhạy cảm**. Không bật profiling mức cao trên production mà không đánh giá dung lượng và tác động.

### 12.2. Chỉ số chậm cần xem theo phân phối

Nếu p95 API là 150 ms nhưng có vài query 8 giây, cần tìm outliers và query shape. Nếu p95 tăng từ 150 ms lên 2 giây trên toàn hệ thống, cần xem **concurrency, queue, CPU/I/O, replication và resource saturation**, không chỉ top-1 longest query.

### 12.3. Tương quan giữa application trace và MongoDB

Một request có thể có:

~~~text
traceId = trace-19f2
appName = orders-api
queryComment = orders-api:list-pending:v2
MongoDB opid = 81042
~~~

App nên log traceId/correlation an toàn ở tầng ứng dụng và dùng comment có kiểm soát trên query. **opid** do MongoDB cấp cho thao tác quan sát được, không phải traceId; có thể thay đổi nếu request được retry.

## 13. killOp là gì, hoạt động như thế nào?

**db.killOp(opid)** là mongosh helper yêu cầu MongoDB **ngắt một operation đang chạy**. MongoDB xem xét yêu cầu và dừng operation tại **điểm an toàn để xử lý interrupt** tiếp theo.

Ví dụ cú pháp:

~~~javascript
// Chỉ thực hiện thủ công sau khi xác minh đúng opid và phê duyệt.
db.killOp(81042);
~~~

**Lệnh trên chỉ minh họa cú pháp và opid giả lập. Không chạy một opid trong production vì nó xuất hiện trong tài liệu học.**

### 13.1. killOp không giống kill process

~~~text
killOp(opid)
      |
      v
Set interrupt request for target operation
      |
      v
Operation reaches a safe interrupt point
      |
      v
Operation stops / returns error to client
~~~

Đây không phải:

~~~text
kill mongod process
force restart server
delete the collection
rollback every write already finished
~~~

Không dùng OS process kill hoặc restart mongod như một biến thể của killOp để giải quyết một query chậm. Các hành động đó có tác động lớn đến availability và durability.

### 13.2. Không bảo đảm dừng ngay

Một số operations cần đạt **interrupt point**, hoặc đang ở giai đoạn chưa thể dừng ngay. Khi đó:

- Lệnh yêu cầu kill có thể được chấp nhận.
- **killPending** có thể chuyển true.
- Operation vẫn xuất hiện trong currentOp một thời gian.
- Client có thể nhận lỗi ngắt khi thao tác kết thúc.

Không mặc định **killOp trả thành công = toàn bộ tác động đã chấm dứt ngay lập tức**. Luôn xác minh hậu kiểm.

### 13.3. Quyền killop

Trên deployment có authorization:

- Để kill operations của những user khác, cần privilege action **killop** thích hợp.
- Trên **mongod**, user có thể kill operations **của chính mình** trong các điều kiện được tài liệu cho phép ngay cả khi không có privilege killop mở rộng.
- Quyền hoạt động trên **mongos/sharded cluster** có quy tắc khác; xem role và scope cụ thể.

Không nên cấp quyền killop cho tài khoản application hoặc monitoring thuần read-only. Tách **inprog** cho người quan sát và **killop** cho người đủ thẩm quyền xử lý sự cố.

### 13.4. killOp chỉ dùng cho operations do client khởi tạo

Cảnh báo quan trọng trong tài liệu MongoDB: **chỉ kết thúc những operations do client khởi tạo; không kết thúc operations nội bộ của database**.

Các trường hợp **không được kill tùy tiện**:

- Replication/apply operations.
- Checkpoint/storage engine threads.
- Balancer/chunk migration nội bộ.
- Internal query/execution tasks không thuộc một client operation rõ ràng.
- Background maintenance chỉ vì chạy lâu.
- Index build/migration được phê duyệt mà chưa xem runbook.

Nếu không xác minh được operation là **client-initiated** và tác động ngắt an toàn, **không gọi killOp**.

### 13.5. Có thể kill reads, còn writes cần thận trọng hơn

Một read query bị dừng có thể làm client nhận lỗi và retry, hoặc mất cursor/request. Tác động thường ít rủi ro nghiệp vụ hơn nhưng vẫn có thể ảnh hưởng người dùng.

Với write/bulk command:

- Một số document đã được sửa trước thời điểm interrupt có thể **đã commit**.
- Không mặc định mọi update/delete/insert được rollback khi killOp.
- Một transaction có cơ chế atomicity riêng, nhưng kill một operation bên trong transaction không phải phương án thay cho transaction-aware abort/retry.
- Client có thể gặp **unknown outcome**, retry hoặc xử lý lỗi không đúng nếu nghiệp vụ không idempotent.

Vì thế kill write cần phối hợp người quản lý workload, đánh giá trạng thái các writes, idempotency, transaction và kế hoạch đối soát.

### 13.6. killOp khác timeout maxTimeMS

**maxTimeMS** là giới hạn thời gian được client đặt **trước khi operation chạy**:

~~~javascript
db.orders.find({
  status: "PENDING"
}).maxTimeMS(5000);
~~~

Nếu vượt giới hạn thực thi theo quy tắc MongoDB, operation thường trả lỗi **MaxTimeMSExpired** tại interrupt point.

**killOp** là quyết định **sau khi operation đã khởi chạy**, dùng khi cần can thiệp và đã xác định operation cụ thể.

Hai cách đều không phải SLA end-to-end tuyệt đối; app còn có connection pool wait, network, xử lý kết quả, retries và thời điểm interrupt.

## 14. Khi nào NÊN và KHÔNG NÊN dùng killOp?

Không có một ngưỡng chung kiểu **“secs_running > 30 thì kill”**. Nên dùng ma trận:

| Tình huống | Hướng ưu tiên | Cân nhắc killOp? |
|---|---|---|
| Ad-hoc read query của analyst không còn cần, scan lớn và ảnh hưởng production | Yêu cầu analyst cancel từ client, giảm tải | **Có thể**, nếu xác minh opid và tác động |
| API read query bị treo, traffic và retry liên tục | Giảm traffic, kiểm soát retries, tìm root cause | **Có thể**, như biện pháp khẩn cấp |
| Query chạy 2 phút nhưng là export đã được phê duyệt | Xác minh progress/SLO | **Không chỉ vì lâu** |
| Query chờ lock do transaction khác | Tìm blocker/transaction owner | **Không kill waiter mặc định** |
| Index build theo change window | Đối chiếu change plan và tiến độ | **Không khi chưa có quyết định DBA** |
| Replication, checkpoint, balancer nội bộ | Điều tra theo runbook MongoDB | **Không** |
| Bulk write production không rõ trạng thái commit | Dừng nguồn, đánh giá idempotency, đối soát | **Rất thận trọng** |
| Change stream/getMore awaitData | Kiểm tra behavior stream | **Không chỉ vì duration** |
| Long transaction không active | Xử lý session/transaction owner | **killOp không phải mặc định** |
| Query đã hết, không còn opid | Dùng logs/profiler để điều tra | **Không có mục tiêu để kill** |

### 14.1. Điều kiện tích cực để cân nhắc killOp

Một quyết định có thể hợp lý khi **đồng thời** có:

1. Operation xác định rõ là **do client khởi tạo**, không phải internal operation.
2. **Namespace, host/shard, opid, appName/client, command hoặc comment** đều khớp workload được điều tra.
3. Operation đang gây **tác động thực tế** hoặc không còn cần thiết.
4. Đã xem liệu **cancel từ client, maxTimeMS, giới hạn traffic/concurrency** có thể giải quyết tốt hơn không.
5. Có quyền và sự cho phép của **owner/on-call/DBA** theo mức độ nguy hiểm.
6. Đã phân tích **ngắt read/write/transaction có thể ảnh hưởng gì**.
7. Có kế hoạch theo dõi client errors, retries, write outcome và kết quả sau kill.

Không đủ các điều kiện trên thì phải **tiếp tục chẩn đoán**, không thực hiện kill tùy tiện.

### 14.2. Ba câu hỏi trước khi ra quyết định

**Hỏi 1 — Nó có thực sự là tác nhân gây sự cố không?**

Một query 60 giây có thể đang chờ; một background job khác mới là tác nhân đẩy CPU lên cao.

**Hỏi 2 — Việc ngắt có giảm tác động hay tạo lỗi khác?**

Ngắt một write không idempotent có thể dẫn đến unknown outcome và retry trùng nghiệp vụ.

**Hỏi 3 — Tác nhân có khởi chạy lại ngay không?**

Nếu application worker tự retry vô hạn, killOp có thể làm loop nóng hơn. Giảm nguồn traffic hoặc vô hiệu hóa job trước khi can thiệp.

## 15. Runbook killOp có kiểm soát

Phần này là **quy trình quyết định**, không phải script tự động kill. Mọi lệnh kill phải do người có quyền thực hiện trong tình huống đã được phê duyệt.

### Bước 1 — Thu thập tình trạng sự cố

Ghi:

~~~text
Incident ID:
UTC timestamp:
Cluster / environment:
Affected database/collection:
User-facing impact:
Error rate / p95 / p99:
CPU / I/O / connections / queue:
Replication state / lag:
Owner / approving on-call:
~~~

Không chỉ viết “query rất chậm” vì không đủ cơ sở so sánh trước và sau can thiệp.

### Bước 2 — Chụp currentOp read-only

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true, idleConnections: false } },
  {
    $match: {
      type: "op",
      active: true,
      secs_running: { $gte: 10 }
    }
  },
  {
    $project: {
      _id: 0,
      host: 1,
      shard: 1,
      opid: 1,
      ns: 1,
      op: 1,
      appName: 1,
      client: 1,
      secs_running: 1,
      waitingForLock: 1,
      planSummary: 1,
      killPending: 1,
      "command.comment": 1
    }
  },
  { $sort: { secs_running: -1 } }
]);
~~~

Không ghi toàn bộ command/query literals vào một kênh incident công khai nếu chúng chứa dữ liệu khách hàng.

### Bước 3 — Xác minh operation owner và command

Kiểm tra bằng các nguồn độc lập:

- **appName** hoặc client IP trỏ đúng service/worker.
- **ns** và command trỏ đúng collection/workload.
- **comment**/APM trace phù hợp incident.
- **host/shard** hiện tại và thời điểm quan sát.
- Operation là **read** hay **write**.
- Không phải internal database task.

Nếu nguồn gốc không rõ, chuyển cho DBA hoặc chủ hệ thống, không kill vì một cái tên trông quen.

### Bước 4 — Xem lựa chọn ít gây gián đoạn hơn

- Cancel request hoặc stop job từ **ứng dụng**.
- Chặn endpoint/batch mới trong load balancer/queue.
- Giảm concurrency/rate limit.
- Cho operation hoàn tất nếu sắp xong và không còn gây ảnh hưởng.
- Tạm hoãn workload phân tích.
- Dùng maxTimeMS cho các request **sau này**, không kỳ vọng nó tự sửa request đã chạy không có limit.

### Bước 5 — Phê duyệt và xác nhận lại opid

**Trước khi kill ngay tại thời điểm hành động**, quan sát lại một lần để xác nhận:

~~~text
same host/shard?
same appName/client?
same ns/command/comment?
opid still present?
operation still client-initiated?
still causing harm?
~~~

Không reuse opid từ một screenshot cũ vài phút mà không xác minh trạng thái hiện tại.

### Bước 6 — Yêu cầu kill một opid đã được phê duyệt

Ví dụ cú pháp:

~~~javascript
// GIẢ ĐỊNH đã phê duyệt opid 81042 trên đúng mongod/mongos.
// Không chạy mã này với opid lấy từ bài học.
db.killOp(81042);
~~~

Trong sharded cluster, phải hiểu **opid thuộc mongos hay mongod shard nào** trước khi quyết định chạy lệnh ở endpoint nào. Xem mục sharding bên dưới.

Không chạy:

~~~javascript
// KHÔNG LÀM: tự động kill mọi operation chạy quá 10 giây.
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  { $match: { secs_running: { $gte: 10 } } }
]).forEach(op => db.killOp(op.opid));
~~~

Mẫu **không được thực hiện** trên có thể giết nhầm internal operations, báo cáo hợp lệ, index builds hoặc writes đang thực thi.

### Bước 7 — Hậu kiểm operation và ứng dụng

Quan sát:

- Operation **biến mất** khỏi snapshot hiện tại hay **killPending=true**.
- Có operation mới cùng comment/shape được client retry không.
- p95/p99 và error rate thay đổi thế nào.
- Có write nào đã commit một phần hoặc cần đối soát không.
- Replication/locks/queue có phục hồi không.
- Application có báo lỗi interruption/timeout và xử lý đúng không.

Nếu lệnh kill không làm latency giảm, phải tiếp tục điều tra nguyên nhân, **không chuyển ngay sang kill hàng loạt**.

### Bước 8 — Khắc phục gốc và lưu incident record

Ghi root cause:

~~~text
Incident cause:
Query shape / endpoint:
Index / query rewrite:
MaxTimeMS policy:
Retry/backpressure changes:
Outcome / user impact:
Follow-up owner and deadline:
~~~

KillOp chỉ là **biện pháp dập lửa có điều kiện**. Kết thúc sự cố đúng nghĩa là có biện pháp ngăn lặp lại.

## 16. Sharded cluster: mongos khác mongod

Một sharded cluster có:

~~~text
Client
   |
   v
mongos router
   |
   +------------+------------+
   |            |            |
   v            v            v
Shard A       Shard B      Shard C
 mongod        mongod       mongod
~~~

Một query của client có thể được mongos gửi đến một hoặc nhiều shards. Vì vậy một operation có thể có **thông tin ở router và tại từng shard**.

### 16.1. $currentOp qua mongos: localOps=false

Khi chạy $currentOp trên mongos với **localOps: false** (mặc định), MongoDB báo các operations ở **shards** theo phạm vi stage:

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      localOps: false
    }
  },
  {
    $match: {
      active: true,
      secs_running: { $gte: 5 }
    }
  },
  {
    $project: {
      shard: 1,
      host: 1,
      opid: 1,
      ns: 1,
      secs_running: 1,
      "command.comment": 1
    }
  }
]);
~~~

**host**, **shard** và **opid** của shard-side operation phải được giữ lại. Không đưa một opid của shard vào mongos tùy ý rồi giả định nó cùng định danh với một router-side operation.

### 16.2. $currentOp qua mongos: localOps=true

**localOps: true** trên mongos giúp quan sát operations chạy **tại chính mongos/router**:

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      localOps: true
    }
  },
  {
    $match: {
      active: true
    }
  },
  {
    $project: {
      host: 1,
      opid: 1,
      ns: 1,
      secs_running: 1,
      appName: 1,
      "command.comment": 1
    }
  }
]);
~~~

Đây là hai **góc nhìn khác nhau**, không phải hai cách viết đồng nghĩa. Khi điều tra một query scatter-gather, có thể cần cả router-side và shard-side evidence.

### 16.3. targetAllNodes

Ở MongoDB phiên bản hỗ trợ (từ 7.1), **targetAllNodes** có thể làm $currentOp trả thông tin từ nhiều data-bearing nodes của mỗi shard thay vì một node/shard theo mặc định.

Không bật tùy tiện trên production rất lớn chỉ vì muốn “xem tất cả”: cần cân nhắc số nodes, quyền và khối lượng output.

### 16.4. killOp trên mongos đối với read

Theo tài liệu MongoDB, **killOp chạy trên mongos có thể ngắt read query trải qua nhiều shards**.

Kịch bản:

~~~text
Client starts a read through mongos
        |
        v
Read fans out to shards
        |
        v
Operator identifies router-side client operation
        |
        v
Approved killOp on correct mongos opid
        |
        v
Read cancellation can propagate to shards
~~~

Không có nghĩa mọi opid shard-side đều được kill từ mongos bất kỳ. Người vận hành phải xác minh **đúng router, opid và thao tác**.

### 16.5. killOp trên mongos đối với write

Điểm đặc biệt quan trọng: **killOp trên mongos không propagate tới shards khi operation bị kill là write**.

Do đó:

- Đừng khẳng định “mongos đã kill thành công nên mọi shard write đã dừng”.
- Không làm write partial/completed được rollback một cách mặc định.
- Cần DBA xác định shard-side operations và quy trình xử lý phù hợp nếu một write cần can thiệp.
- Phải đối soát kết quả nếu write đã tác động một phần dữ liệu.

Đây là lý do **không dùng một script killOp chung cho read và write trong sharded cluster**.

### 16.6. Các transaction nhiều shards

Sharded transaction liên quan nhiều participants và coordinator. $currentOp có thể cung cấp:

- **transaction** information theo từng shard khi localOps=false.
- **Composite transaction view** tại mongos khi localOps=true.
- **lsid/txnNumber** để nhận diện transaction ở mức session.

Nếu transaction quá lâu hoặc không active, cần xem **transaction lifecycle/abort semantics**, không lấy một shard opid ngẫu nhiên để kết luận cả transaction đã bị dừng an toàn.

### 16.7. Ghi đầy đủ host + opid trong incident

Thay vì:

~~~text
Killed opid: 81042
~~~

hãy ghi:

~~~text
Cluster: prod-sharded
Entry point: mongos-router-2
Node/host of operation: shard-A-primary:27017
Shard: shard-A
Operation ID: 81042
Read or write: read
Application: billing-report
Comment: report:daily-v1
Approval reference: INC-2026-001
~~~

Thông tin ví dụ giúp giảm nguy cơ nhầm opid giữa nhiều nodes, đồng thời phục vụ audit.

## 17. Ngăn thao tác chạy vô hạn bằng maxTimeMS và thiết kế API

**maxTimeMS** là một cơ chế phòng ngừa: đặt giới hạn thời gian server được phép dành cho operation theo quy tắc MongoDB, thay vì chờ on-call dùng killOp.

### 17.1. maxTimeMS cho find trong mongosh

~~~javascript
db.getSiblingDB("shop").orders
  .find({
    tenantId: "T-001",
    status: "PENDING"
  })
  .sort({ createdAt: -1 })
  .limit(50)
  .maxTimeMS(5000);
~~~

Mức 5000 ms là **ví dụ policy của API**, không phải ngưỡng tối ưu cho mọi query.

### 17.2. maxTimeMS cho aggregation

~~~javascript
db.getSiblingDB("shop").orders.aggregate(
  [
    { $match: { tenantId: "T-001" } },
    {
      $group: {
        _id: "$status",
        count: { $sum: 1 }
      }
    }
  ],
  {
    maxTimeMS: 10000,
    comment: "orders-report:status-count:v1"
  }
);
~~~

Driver và mongosh có API đặt timeout khác nhau; quan trọng là **server nhận được maxTimeMS cho operation**.

### 17.3. maxTimeMS không phải toàn bộ deadline

Một HTTP request có thể mất:

~~~text
Connection pool checkout   1500 ms
Network to MongoDB          300 ms
MongoDB operation          4900 ms
Deserialize result          500 ms
Application logic          1000 ms
---------------------------------
Total                      8200 ms
~~~

Nếu chỉ đặt **maxTimeMS: 5000**, request vẫn có thể vượt deadline HTTP 5 giây do thời gian ngoài operation.

Vì vậy cần phối hợp:

- Request deadline ở API/gateway.
- Driver socket/connection/server selection/pool wait timeout phù hợp.
- maxTimeMS server-side cho query.
- Cancellation khi user bỏ request nếu workflow hỗ trợ.
- Giới hạn retry và tổng retry budget.
- Metrics theo từng chặng.

### 17.4. maxTimeMS cũng dựa trên interrupt points

Một operation có thể chỉ dừng khi đạt điểm interrupt được MongoDB kiểm tra, không nhất thiết chính xác tại một mili giây. Khi vượt giới hạn, driver thường nhận **MaxTimeMSExpired**.

Không dùng maxTimeMS như biện pháp thay thế cho **đúng index, filter, sort, batch size** hoặc quản lý tài nguyên.

### 17.5. Đặt maxTimeMS theo loại workload

Ví dụ phân chia:

| Loại | Policy minh họa |
|---|---|
| Interactive read API | 1–3 giây |
| Report query vừa | 10–30 giây |
| Batch aggregation | 1–5 phút |
| Export nền | Theo batch/partition được thiết kế |
| Change stream | Có timeout/await semantics riêng |

Các giá trị là **điểm khởi đầu để thảo luận**, không phải tiêu chuẩn MongoDB bắt buộc. Cần dựa trên load test và SLO.

### 17.6. Dùng pagination thay vì đọc cả triệu documents

Không nên:

~~~javascript
// Ví dụ không phù hợp cho API realtime nếu collection lớn:
db.orders.find({ tenantId: "T-001" }).toArray();
~~~

API nên:

~~~javascript
db.orders.find({
  tenantId: "T-001",
  createdAt: { $lt: ISODate("2026-11-14T00:00:00Z") }
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(50)
  .maxTimeMS(5000);
~~~

Khi cần pagination ổn định với sort createdAt + _id, nên dùng **keyset pagination đầy đủ** với điều kiện tiếp nối theo cặp (createdAt, _id). Đoạn code trên chỉ minh họa việc giới hạn số kết quả; nó chưa thể hiện đầy đủ điều kiện tie-breaker của keyset pagination.

### 17.7. Batch job phải có checkpoint

Nếu một export cần đọc 10 triệu records:

~~~text
Export job
   |
   +--> Partition 1 -> done
   +--> Partition 2 -> done
   +--> Partition 3 -> retry
   +--> Partition 4 -> pending
~~~

Thiết kế checkpoint giúp dừng **job** mà không phải kill một query khổng lồ và bắt đầu lại từ đầu. Mỗi batch có thời gian, giới hạn và cơ chế retry/idempotency riêng.

## 18. Gắn appName và query comment từ ứng dụng

Một trong những điểm khó nhất khi xem currentOp là **không biết một command xuất phát từ endpoint nào**.

### 18.1. appName mô tả service

Ví dụ:

~~~text
orders-api
invoice-worker
analytics-report
data-backfill
~~~

Tên này nên phản ánh **component và môi trường** nếu cần phân biệt, không đưa secrets, customerId hay token vào appName.

### 18.2. comment mô tả query shape

Ví dụ:

~~~text
orders:list-pending:v2
payments:reconciliation:v1
report:daily-revenue:v3
~~~

Comment nên là **nhãn query pattern**, không phải nội dung nhạy cảm. Nếu dùng trace ID động, cần kiểm soát độ dài và cardinality của logs.

### 18.3. Ví dụ Node.js MongoDB Driver

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(
  process.env.MONGODB_URI,
  {
    appName: "orders-api"
  }
);

await client.connect();

try {
  const collection = client
    .db("shop")
    .collection("orders");

  const cursor = collection.find(
    {
      tenantId: "T-001",
      status: "PENDING"
    },
    {
      projection: {
        _id: 1,
        status: 1,
        createdAt: 1
      },
      comment: "orders:list-pending:v2",
      maxTimeMS: 5000
    }
  )
    .sort({ createdAt: -1 })
    .limit(50);

  try {
    const results = await cursor.toArray();
    console.log("Returned:", results.length);
  } finally {
    await cursor.close();
  }
} finally {
  await client.close();
}
~~~

Ở service production, **MongoClient thường được tái sử dụng**, không tạo/đóng client cho từng HTTP request. Ví dụ trên minh họa một script độc lập.

Nếu MongoDB trả lỗi **MaxTimeMSExpired**, API phải xử lý đúng: giới hạn retry, trả lỗi có ý nghĩa và quan sát metrics. Không tự retry vô hạn một query đang quá tải.

### 18.4. Ví dụ Java MongoDB Sync Driver

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public final class SlowQueryAwareExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                    "MONGODB_URI is required");
        }

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyConnectionString(
                                new ConnectionString(uri))
                        .applicationName("orders-api")
                        .build();

        try (MongoClient client = MongoClients.create(settings)) {
            MongoCollection<Document> orders =
                    client.getDatabase("shop")
                            .getCollection("orders");

            FindIterable<Document> iterable = orders.find(
                    Filters.and(
                            Filters.eq("tenantId", "T-001"),
                            Filters.eq("status", "PENDING")
                    )
            )
                    .sort(Sorts.descending("createdAt"))
                    .limit(50)
                    .maxTime(5, TimeUnit.SECONDS);

            try (MongoCursor<Document> cursor =
                         iterable.iterator()) {
                while (cursor.hasNext()) {
                    Document row = cursor.next();
                    System.out.println(row.get("_id"));
                }
            }
        }
    }
}
~~~

Đây là code **đặt appName, time bound và đóng cursor đúng cách**. Trong ứng dụng thật, URI nên lấy từ secret manager, có retry policy và logging không chứa thông tin nhạy cảm. MongoClient nên tồn tại cùng vòng đời application.

### 18.5. Comment và operation correlation không tự tạo tracing

appName/comment giúp quan sát nhưng không tự xây hệ thống distributed tracing. Ứng dụng vẫn cần:

- Request/trace ID.
- Command monitoring hoặc telemetry phù hợp.
- Log nhóm theo endpoint/query shape.
- Correlation giữa request, MongoDB driver và result/error.
- Chính sách ẩn dữ liệu nhạy cảm trong command/filter.

Không đặt nội dung toàn bộ query hoặc JWT vào comment.

## 19. Lab mongosh: quan sát một query có gắn comment

Mục tiêu là **thực hành quan sát**, không chủ động tạo query phá tải. Các bước chạy trên **môi trường sandbox/staging** do bạn sở hữu, không chạy trên production nếu chưa có change approval.

### 19.1. Chuẩn bị dữ liệu mẫu nhỏ

Trong mongosh:

~~~javascript
use ops_observe_lab

const demoDocs = Array.from({ length: 300 }, (_, i) => ({
  _id: "EVT-" + String(i + 1).padStart(4, "0"),
  tenantId: "TENANT-TEST",
  status: i % 4 === 0 ? "PENDING" : "DONE",
  amount: (i % 50) * 100,
  createdAt: new Date(
    Date.UTC(2026, 10, 1, 0, 0, i % 60)
  )
}));

db.events.insertMany(demoDocs);
~~~

Nếu chạy lại trên collection đã có cùng _id, **duplicate key là điều bình thường**. Không drop collection khác hoặc dữ liệu production để chạy lại lab.

Tập 300 records này là dữ liệu nhỏ, **không đủ để bảo đảm query kéo dài và xuất hiện trong currentOp**. Đây là một đặc điểm của snapshot monitoring, không phải lỗi bài tập.

### 19.2. Tạo query có comment và thời hạn

Trong Terminal A:

~~~javascript
db.events.find({
  tenantId: "TENANT-TEST",
  status: "PENDING"
})
  .sort({ createdAt: -1 })
  .comment("lab:pending-events:v1")
  .maxTimeMS(3000)
  .limit(50)
  .toArray();
~~~

Kết quả có thể hoàn tất dưới một giây. Không cố tăng dữ liệu đến hàng chục triệu hoặc dùng vòng lặp CPU vô hạn chỉ để bắt currentOp hiển thị nó.

### 19.3. Xem currentOp từ terminal khác

Trong Terminal B, dùng **tài khoản có quyền quan sát phù hợp**:

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleConnections: false
    }
  },
  {
    $match: {
      $or: [
        { "command.comment": "lab:pending-events:v1" },
        {
          "cursor.originatingCommand.comment":
            "lab:pending-events:v1"
        }
      ]
    }
  },
  {
    $project: {
      opid: 1,
      host: 1,
      ns: 1,
      appName: 1,
      secs_running: 1,
      planSummary: 1,
      waitingForLock: 1
    }
  }
]);
~~~

Có thể không thấy operation nào vì lệnh ở Terminal A đã kết thúc. Đây là điểm khác biệt giữa **quan sát hiện tại** và **truy vấn lịch sử**.

### 19.4. Quan sát plan bằng explain

~~~javascript
db.events.find({
  tenantId: "TENANT-TEST",
  status: "PENDING"
})
  .sort({ createdAt: -1 })
  .limit(50)
  .explain("queryPlanner");
~~~

Sau đó, tạo index lab:

~~~javascript
db.events.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

Chạy explain lại để xem kế hoạch truy vấn. Trên một collection nhỏ, planner có thể vẫn chọn cách phù hợp khác, và thời gian chạy gần như không thay đổi đáng kể. Không dùng lab 300 records để tuyên bố hiệu năng của một index trên hàng triệu records.

### 19.5. Có nên chạy killOp trong lab không?

Lab cơ bản **không cần killOp**. Nếu muốn thử thực tế trong một **môi trường cô lập**, hãy chỉ chọn một **client-initiated read operation** do mình khởi tạo, xác minh opid và giới hạn tác động; phải có quyền/approval phù hợp.

Không thực hiện script “tự động tìm và kill longest operations” trong bất kỳ môi trường nào có workload của người khác. Không tạo giao dịch giữ lock hoặc query dùng quá nhiều CPU chỉ để có thứ để kill.

### 19.6. Dọn dữ liệu mẫu

Chỉ khi chắc chắn đang ở database **ops_observe_lab** và collection **events** thuộc lab:

~~~javascript
// Optional lab cleanup, phải xác minh database trước.
db.getName();
db.events.countDocuments({ tenantId: "TENANT-TEST" });
~~~

Không tự động drop collection trong bài học. Việc dọn tài liệu thử nghiệm là quyết định của người sở hữu môi trường, không phải bước bắt buộc để tìm long-running operations.

## 20. Quy tắc ứng dụng khi operation bị ngắt

Khi MongoDB ngắt operation, client cần xử lý lỗi theo loại workload.

### 20.1. Read query

Ví dụ:

~~~text
User requests list
        |
        v
MongoDB query interrupted
        |
        v
Driver raises an error
        |
        v
API responds with controlled error / retry logic
~~~

Một retry read có thể phù hợp khi:

- Request còn trong deadline.
- Query idempotent và không làm thay đổi dữ liệu.
- Có retry budget nhỏ.
- Hệ thống không ở trạng thái overload.

Không retry ngay vô hạn một query vừa bị kill do nó gây tải.

### 20.2. Write operation

Một write bị interrupt có thể khiến client không chắc trạng thái cuối:

~~~text
Bulk write started
      |
      +-- Document A written
      +-- Document B written
      +-- Document C not yet written
      |
      v
Interruption
      |
      v
Client must reconcile actual state
~~~

Không viết:

~~~text
If killOp returns success:
  assume all writes rolled back
~~~

Điều này **không đúng nói chung**. Tùy write/bulk semantics, một số tài liệu đã được cập nhật trước ngắt.

### 20.3. Retryable writes và idempotency

MongoDB driver có cơ chế retryable writes trong những điều kiện cụ thể, nhưng không có nghĩa mọi command và nghiệp vụ đều retry an toàn:

- Một command bulk với nhiều writes không phải lúc nào cũng atomic toàn bộ.
- Ứng dụng có thể sinh email/sự kiện bên ngoài database.
- Một request tạo mã giao dịch ngẫu nhiên mới ở mỗi retry có thể tạo trùng nghiệp vụ.

Thiết kế tốt dùng:

- Business idempotency key.
- Unique constraint phù hợp.
- Điều kiện update theo version/trạng thái.
- Transaction khi thực sự cần và được hỗ trợ.
- Outbox/inbox pattern cho side effects.
- Quy trình reconciliation cho unknown outcome.

### 20.4. Transaction

Nếu operation đang nằm trong transaction, phải xác định:

~~~text
lsid
txnNumber
transaction start time
transaction owner
participants (nếu sharded)
commit/abort status
~~~

Ngắt một command không phải phương án quản lý transaction tốt bằng **client abortTransaction** hoặc cơ chế session/transaction chuẩn theo runbook. Phải xử lý transaction error labels và retry policy phù hợp.

### 20.5. Không giấu lỗi trong API

Một code path nguy hiểm:

~~~javascript
try {
  return await doDbOperation();
} catch (error) {
  return { success: true, items: [] };
}
~~~

Nếu query bị interrupt, API trả success rỗng sẽ làm người dùng tin không có dữ liệu. Thay vào đó, trả lỗi phù hợp, ghi nhận failure metrics và chỉ fallback khi có policy nghiệp vụ rõ ràng.

## 21. Giám sát tự động: cảnh báo khác tự động kill

Giám sát có thể chạy định kỳ để phát hiện:

- Số active operations vượt ngưỡng.
- Tỷ lệ operations lâu theo appName/namespace.
- Số operations waitingForLock.
- Queue time hoặc connections tăng bất thường.
- Hệ thống có nhiều COLLSCAN query shapes lặp lại.
- Transactions đang mở lâu.

Nhưng **tạo alert** và **tự động kill** là hai cơ chế khác nhau.

### 21.1. Không lập rule kill chỉ dựa trên duration

Không nên:

~~~text
if secs_running > 30:
    killOp(opid)
~~~

Vì rule sẽ không hiểu:

- Operation là internal task hay client-initiated.
- Export có kế hoạch hay API request lỗi.
- Query đang gần hoàn thành hay đang chờ lock.
- Opid thuộc node nào trong sharded cluster.
- Write đã commit một phần chưa.
- Ứng dụng có tự retry tạo storm không.

### 21.2. Alert nên gửi bằng chứng tối thiểu

Ví dụ alert an toàn:

~~~text
Alert: long-running client operation
Cluster: prod
Host: db-primary-1
Namespace: shop.orders
App: orders-api
Duration: 34 s
Op type: command
Waiting for lock: false
Plan summary: COLLSCAN
Query tag: orders:list-pending:v2
Suggested action: investigate / escalate
~~~

Không gửi full filter có tên, số tài khoản hoặc token vào kênh alert công khai.

### 21.3. Alert có thể nhiễu

Một snapshot 5 giây có thể bắt một query 8 giây ngay trước khi nó kết thúc. Nếu alert liên tục cho mọi occurrence, on-call có thể bị nhiễu.

Nên kết hợp:

- Thời gian duy trì bất thường.
- Số lượng operations/chủ đề lặp lại.
- SLO impact.
- CPU/I/O/queue metrics.
- Window/hysteresis/cooldown.
- Metadata workload để loại trừ các job được phê duyệt.

### 21.4. Chi phí giám sát

Thu thập currentOp quá thường xuyên với **allUsers=true**, **idleConnections=true**, hoặc truy vấn mọi node qua mongos có thể tạo output lớn và overhead.

Nên:

- Chỉ lấy fields cần thiết.
- Lọc active operations, bỏ idle không cần.
- Giữ retention của telemetry phù hợp.
- Giới hạn quyền truy cập logs.
- Sử dụng metrics/profiler chuyên dụng cho lịch sử.

Không scrape full command của mọi query mỗi vài mili giây trên cluster nhiều tenant.

## 22. Những lỗi và hiểu nhầm thường gặp

### 22.1. “currentOp không thấy query, vậy query không chậm”

**Sai vì:** currentOp là snapshot. Query có thể kết thúc trước lúc kiểm tra, hoặc nằm trên node/shard khác.

**Cách điều tra:** dùng profiler, slow query logs, APM và đối chiếu timestamp của incident; xem topology và phạm vi quan sát.

### 22.2. “Operation active nghĩa là đang dùng CPU liên tục”

**Sai vì:** active operation có thể chờ lock, queue, I/O hoặc các điểm synchronization.

**Cách điều tra:** xem waitingForLock, currentQueue, lockStats, metrics CPU/I/O và flow control.

### 22.3. “COLLSCAN chắc chắn phải kill ngay”

**Sai vì:** COLLSCAN là một dạng execution plan, không phải một mức độ nguy hiểm. Query trên collection nhỏ có thể rất nhanh; toàn bộ scan có thể được chủ động thực hiện trong batch.

**Cách điều tra:** đo tài nguyên và ảnh hưởng thực, xem explain/query shape, chọn tạo index nếu phù hợp.

### 22.4. “IXSCAN chứng minh query tốt”

**Sai vì:** có index nhưng vẫn có thể scan hàng triệu keys, fetch nhiều documents hoặc sort lớn.

**Cách điều tra:** xem explain, totalKeysExamined, totalDocsExamined, nReturned, SORT stage, cache và schema.

### 22.5. “secs_running=90 là 90 giây CPU”

**Sai vì:** secs_running là thời gian **trôi qua** của operation. CPU time/lock wait/network wait không bằng nhau.

**Cách điều tra:** correlating currentOp với host metrics, driver traces và profiler.

### 22.6. “killOp trả về rồi nên operation đã dừng ngay”

**Sai vì:** killOp được xử lý tại interrupt point. Có thể còn **killPending=true**.

**Cách điều tra:** snapshot lại cùng host/shard, xem operation biến mất hay không, và kiểm tra client errors.

### 22.7. “killOp tự rollback mọi writes”

**Sai vì:** các writes đã commit trước interruption không nhất thiết bị hoàn tác.

**Cách điều tra:** đối soát theo business IDs, idempotency keys, operation results và transaction semantics.

### 22.8. “Kill một waiter sẽ mở khóa toàn bộ”

**Sai vì:** waiter thường không phải blocker.

**Cách điều tra:** xác định lock holder/transaction, chọn dừng workload từ ứng dụng hoặc giải quyết nguyên nhân gốc.

### 22.9. “Kill một long-running transaction bằng opid bất kỳ”

**Sai vì:** transaction có thể idle, trải qua nhiều operations/shards, và lsid khác opid.

**Cách điều tra:** xem idleSessions, transaction fields, owner, hỗ trợ abortTransaction/session management có kiểm soát.

### 22.10. “getMore chạy lâu nên là query xấu”

**Sai vì:** getMore có thể đợi change stream/tailable cursor theo thiết kế.

**Cách điều tra:** cursor.awaitData, cursor.tailable, originatingCommand, client purpose.

### 22.11. “db.currentOp(true) chỉ trả active operations”

**Sai vì:** true có ý nghĩa bao gồm các operations trên idle connections và system operations theo helper.

**Cách điều tra:** dùng filter có mục đích hoặc $currentOp với idleConnections:false.

### 22.12. “Bất kỳ opid nào cũng kill từ mongos”

**Sai vì:** router-side và shard-side operations có phạm vi khác nhau; killOp trên mongos propagate cho read nhưng không propagate write tới shards.

**Cách điều tra:** lưu **host/shard/opid/operation type**, chọn nơi thao tác đúng theo runbook sharded.

### 22.13. “Có quyền đọc collection nghĩa là xem được mọi currentOp”

**Sai vì:** quan sát mọi user cần quyền inprog; kill operation của user khác cần quyền killop trong điều kiện tương ứng.

**Cách điều tra:** cấu hình role quản trị tối thiểu cần thiết; tránh cấp cluster management privileges cho application.

### 22.14. “Một quyền inprog tự cho phép killOp”

**Sai vì:** **inprog** và **killop** là hai privilege actions khác nhau.

**Cách điều tra:** dùng read-only monitoring account để điều tra; chuyển can thiệp tới tài khoản/on-call được cấp quyền riêng.

### 22.15. “Khi currentOp không có command đầy đủ là database lỗi”

**Sai vì:** command có thể được lược hoặc redacted theo version, privilege và Queryable Encryption.

**Cách điều tra:** kiểm tra profiler/APM ở tầng được phép, dùng query comments không nhạy cảm, không cố tắt encryption để xem plaintext.

### 22.16. “KillOp đã giải quyết vấn đề vĩnh viễn”

**Sai vì:** client có thể retry, query plan vẫn không phù hợp, traffic vẫn dồn dập.

**Cách điều tra:** xác định root cause, thiết kế index, maxTimeMS, circuit breaker, rate limit hoặc query rewrite.

### 22.17. “maxTimeMS là HTTP timeout”

**Sai vì:** maxTimeMS đo giới hạn thời gian MongoDB server dành cho operation theo interrupt semantics, không bao gồm tất cả pool/network/serialize/HTTP delays.

**Cách điều tra:** đặt end-to-end deadline và các timeout đồng bộ.

### 22.18. “Nếu opid không còn thì đã bị kill thành công”

**Sai vì:** operation có thể đã tự hoàn tất đúng lúc on-call gửi kill, hoặc được client cancel, timeout, node failover.

**Cách điều tra:** đối chiếu operation outcomes, client errors, logs và timestamps. CurrentOp không mang lịch sử đầy đủ.

### 22.19. “Profiler mức tối đa không có tác động”

**Sai vì:** profiling có chi phí ghi, CPU/disk và có thể lưu query metadata.

**Cách điều tra:** bật theo phiên bản và kế hoạch phù hợp, chọn sampling/filter/retention, kiểm tra quyền và overhead.

### 22.20. “Tất cả operations chạy lâu đều là query”

**Sai vì:** currentOp có thể thấy commands, writes, getMore, index builds, transactions và internal operations.

**Cách điều tra:** đọc type/op/command/appName/description trước khi quyết định.

## 23. Tình huống vận hành có hướng xử lý

### 23.1. API tìm đơn hàng có COLLSCAN

**Bối cảnh:**

~~~text
GET /orders?status=PENDING
p95 latency: 8.2 s
currentOp:
  appName = orders-api
  ns = shop.orders
  secs_running = 12
  planSummary = COLLSCAN
  waitingForLock = false
~~~

**Hướng xử lý:**

1. Xem incident metrics: CPU/I/O, concurrency, queue.
2. Xác minh query shape và filter/sort bằng comment/APM.
3. Xem explain ở mức an toàn, index hiện có, selectivity.
4. Giảm traffic/limit concurrent requests, đặt maxTimeMS cho requests mới.
5. Nếu operation do client khởi tạo gây ảnh hưởng nghiêm trọng và không còn cần, cân nhắc killOp theo runbook.
6. Thiết kế/tạo compound index và rollout theo kế hoạch, sau đó xác minh improvement.

**Điều không nên làm:** kill mọi COLLSCAN của mọi service tự động.

### 23.2. Nhiều writes đang chờ lock

**Bối cảnh:**

~~~text
40 pending updates
waitingForLock = true
One transaction open for 8 minutes
CPU utilization: moderate
~~~

**Hướng xử lý:**

1. Xem idleSessions/transaction fields.
2. Xác định transaction owner và logic đang giữ transaction mở.
3. Xác minh blocker trước khi quyết định ngắt session/transaction.
4. Phối hợp client abort/timeout đúng semantic, theo dõi blocked requests hồi phục.
5. Sửa app không giữ transaction khi gọi API ngoài hoặc chờ user.

**Điều không nên làm:** kill tất cả 40 waiter mà không xử lý transaction.

### 23.3. Báo cáo export hợp lệ chạy ba phút

**Bối cảnh:**

~~~text
appName = analytics-export
comment = daily-archive:v1
secs_running = 180
planSummary = IXSCAN
Resource utilization: expected
Scheduled window: approved
~~~

**Hướng xử lý:** xác minh progress và SLA report. Nếu không ảnh hưởng workload quan trọng, có thể **để hoàn tất**. Nếu tác động lớn, thương lượng dừng từ job owner và đảm bảo checkpoint/restart.

**Điều không nên làm:** coi >30 giây là ngưỡng kill chung.

### 23.4. Change stream chờ sự kiện

**Bối cảnh:**

~~~text
op = getmore
cursor.tailable = true
cursor.awaitData = true
secs_running = 10
Application = notifications-stream
~~~

**Hướng xử lý:** kiểm tra tài liệu change stream/await semantics, nhịp heartbeat và tình trạng client. Đây có thể là **operation chờ hợp lệ**, không phải query kém index.

**Điều không nên làm:** kill mọi getMore có secs_running lớn.

### 23.5. Bulk update bị ngắt giữa chừng

**Bối cảnh:**

~~~text
Batch target: 100000 documents
Some updates possibly applied
killOp requested after 20 s
Client received Interrupted
~~~

**Hướng xử lý:**

1. Không assume rollback toàn bộ batch.
2. Xác định business invariant cần giữ.
3. Đối soát records qua idempotent keys/checkpoint.
4. Chạy lại những phần chưa hoàn tất theo quy trình có bảo vệ concurrency.
5. Sửa batch job thành các chunks nhỏ, measurable và restartable.

### 23.6. Query từ shard bị nhầm với router query

**Bối cảnh:**

~~~text
Observed through mongos:
shard = shard-B
host = shard-B-primary:27017
opid = 82044
~~~

**Hướng xử lý:** phân biệt localOps=false (shard-side) và localOps=true (router-side), đọc/ghi rõ host + opid. Nếu muốn ngắt read distributed, xác định đúng router-side client read operation; nếu là write, hiểu mongos killOp không propagate đến shards.

**Điều không nên làm:** đưa opid shard-B vào mongos bất kỳ mà không xác minh.

### 23.7. KMS hoặc encryption khiến profiler thiếu command

**Bối cảnh:** QE-enabled query xuất hiện trong currentOp nhưng command bị redacted.

**Hướng xử lý:** dùng appName, query comment hợp lệ, APM trace và authorized observability; không tắt encryption hoặc log plaintext để debug.

### 23.8. Monitoring phát hiện opid đã biến mất

**Bối cảnh:** alert gửi opid 45012 lúc 12:00:05, on-call mở mongosh lúc 12:01:00 và không thấy operation.

**Hướng xử lý:** dùng profiler/slow logs và application trace để biết operation đã hoàn thành, timeout hay bị cancel. Không kill một ID đã không còn active.

### 23.9. Long-running index build theo kế hoạch

**Bối cảnh:** currentOp có progress index build 85%, 15 phút trôi qua, storage I/O tăng.

**Hướng xử lý:** đối chiếu change ticket, tiến độ và giới hạn tài nguyên, trao đổi DBA trước quyết định. Không kill index build chỉ vì nó xuất hiện ở top longest.

### 23.10. Retry storm sau killOp

**Bối cảnh:** on-call kill một expensive read, nhưng trong vài giây có năm read mới cùng comment.

**Hướng xử lý:** kiểm tra circuit breaker/retry policy, giảm traffic/stop job, đặt deadline và khắc phục query. Dừng kill liên tục cho đến khi hiểu nguyên nhân.

## 24. Bài tập thực hành: đọc currentOp và chọn hướng xử lý

Các bài sau dùng dữ liệu mô phỏng. Không cần có quyền killOp thật để làm bài; phần thực hành query chỉ dùng **các lệnh read-only** trên môi trường được phép.

### Bài 1. Viết pipeline tìm operations hơn 10 giây

**Yêu cầu:** Dùng $currentOp để lấy các operations active thuộc mọi user có thời gian chạy từ 10 giây trở lên, sắp xếp từ lâu nhất.

**Đáp án:**

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true, idleConnections: false } },
  {
    $match: {
      type: "op",
      active: true,
      secs_running: { $gte: 10 }
    }
  },
  { $sort: { secs_running: -1 } },
  {
    $project: {
      _id: 0,
      opid: 1,
      host: 1,
      ns: 1,
      appName: 1,
      secs_running: 1,
      waitingForLock: 1,
      planSummary: 1
    }
  }
]);
~~~

**Lưu ý:** cần quyền inprog khi quan sát mọi user trong deployment có authentication.

### Bài 2. currentOp trống có chứng minh không có slow query?

Một người dùng nói API vừa mất 8 giây nhưng kết quả $currentOp không có active query nào.

**Câu hỏi:** Có thể kết luận user báo sai không?

**Đáp án:** Không. Query có thể đã kết thúc; hoặc latency nằm ngoài MongoDB (pool/network/application). Dùng profiler, logs và tracing để phân biệt.

### Bài 3. Phân biệt active với CPU

Document:

~~~javascript
{
  opid: 101,
  active: true,
  secs_running: 35,
  waitingForLock: true
}
~~~

**Câu hỏi:** Có thể khẳng định CPU bị thao tác này chiếm 35 giây không?

**Đáp án:** Không. Nó đang đợi lock theo currentOp; cần tìm blocker và đối chiếu metrics để biết nguyên nhân.

### Bài 4. Lọc lock waiters

**Yêu cầu:** Lọc operations đang chờ lock.

~~~javascript
db.getSiblingDB("admin").aggregate([
  { $currentOp: { allUsers: true } },
  {
    $match: {
      active: true,
      waitingForLock: true
    }
  },
  {
    $project: {
      opid: 1,
      host: 1,
      ns: 1,
      secs_running: 1,
      lockStats: 1
    }
  }
]);
~~~

**Câu hỏi:** Có nên kill tất cả kết quả trên?

**Đáp án:** Không. Phải tìm blocker và chủ sở hữu, không coi mọi waiter là nguyên nhân.

### Bài 5. Operation ID với connection ID

CurrentOp:

~~~text
opid = 81042
connectionId = 128
client = 198.51.100.25:53124
~~~

**Câu hỏi:** Đâu là định danh dùng khi gọi db.killOp?

**Đáp án:** **opid**. Không thay bằng connectionId hoặc client port. Trước khi dùng phải xác minh operation và host/shard lại.

### Bài 6. Operation đọc có planSummary COLLSCAN

Document:

~~~text
appName: orders-api
secs_running: 12
planSummary: COLLSCAN
waitingForLock: false
~~~

**Câu hỏi:** Bước nào giúp xác minh nguyên nhân tốt hơn?

**Định hướng:** Xem query shape, filter/sort/index, explain trên môi trường và mức chi phí phù hợp, totalDocsExamined/nReturned; đồng thời xem CPU/I/O/latency.

### Bài 7. IXSCAN nhưng chậm

Một query trả 10 records nhưng totalKeysExamined = 2 triệu.

**Câu hỏi:** Có thể nói index đã đủ tốt vì planSummary IXSCAN không?

**Đáp án:** Không. Index scan có thể quét quá nhiều keys; cần xem compound index, field order, selectivity, covered query và cách sort.

### Bài 8. getMore và awaitData

Document:

~~~javascript
{
  op: "getmore",
  secs_running: 8,
  cursor: {
    tailable: true,
    awaitData: true
  }
}
~~~

**Câu hỏi:** Đây có phải dấu hiệu phải killOp ngay không?

**Đáp án:** Không. Tailable cursor có thể chờ dữ liệu mới theo thiết kế; cần kiểm tra change-stream consumer, timeout và application purpose.

### Bài 9. Transaction idle

~~~text
type: idleSession
transaction.timeOpenMicros: 180000000
transaction.timeActiveMicros: 2000000
~~~

**Câu hỏi:** Transaction đã mở bao lâu và active bao lâu?

**Đáp án:** 180 giây mở, khoảng 2 giây active. Nó có thể không chạy query liên tục nhưng vẫn ảnh hưởng hệ thống. Điều tra owner và quy trình abort, không nhầm lsid với opid.

### Bài 10. Điều kiện dùng killOp

Một ad-hoc read query của nhân viên phân tích đã chạy 2 phút, được xác nhận không còn cần, đang gây CPU/I/O cao, đã có owner chấp nhận ngắt.

**Câu hỏi:** Có thể cân nhắc killOp không?

**Đáp án:** Có thể, **sau** khi xác minh host/opid/current operation vẫn chính xác, có quyền và kiểm tra tác động, lựa chọn cancel từ client, rồi hậu kiểm. Duration không phải điều kiện duy nhất.

### Bài 11. Index build kéo dài

Index build đã chạy 20 phút trong maintenance window, progress tăng đều.

**Câu hỏi:** Vì sao không được tự kill chỉ vì đứng đầu bảng secs_running?

**Đáp án:** Đây có thể là workload đã lên kế hoạch, đang tiến triển; ngắt có thể ảnh hưởng change plan và hiệu năng. Cần phối hợp DBA/chủ change.

### Bài 12. Write operation bị kill

Bulk write có 1000 bản ghi; sau interruption, 400 bản ghi được xác nhận đã ghi.

**Câu hỏi:** Có nên retry toàn bộ 1000 mà không có idempotency không?

**Đáp án:** Không. Một số writes đã thành công; cần đối soát/chia batch, idempotency keys hoặc điều kiện update để không ghi trùng.

### Bài 13. KillPending

Sau lệnh killOp được chấp nhận, operation còn xuất hiện:

~~~javascript
{
  opid: 81042,
  killPending: true
}
~~~

**Câu hỏi:** Có phải MongoDB không xử lý kill request?

**Đáp án:** Chưa thể kết luận. Operation đang chờ interrupt point an toàn. Theo dõi lại và kiểm tra trạng thái, không vội restart server.

### Bài 14. Mongos và shard-side opid

Bạn quan sát qua mongos với localOps=false, thấy:

~~~text
shard = shard-C
host = shard-C-primary
opid = 3030
~~~

**Câu hỏi:** Có thể gọi db.killOp(3030) trên một mongos khác và khẳng định ngắt đúng operation không?

**Đáp án:** Không. Phải phân biệt router/shard operation IDs và xác định nơi thao tác. Không giả định opid có ý nghĩa toàn cluster bất kể host.

### Bài 15. Kill read qua mongos

Một read query từ client chạy qua mongos, scatter-gather sang ba shards.

**Câu hỏi:** Theo tài liệu, killOp trên mongos có thể propagate việc ngắt read xuống shards không?

**Đáp án:** Có, với read query trải qua shards trong điều kiện được hỗ trợ, khi xác định đúng router-side operation. Đây không phải quyền giết tùy ý mọi shard-side operation.

### Bài 16. Kill write qua mongos

Một write qua mongos đã gửi thao tác đến shard A và B. On-call kill router-side operation.

**Câu hỏi:** Có thể coi tất cả shard writes đã bị dừng và rollback không?

**Đáp án:** Không. Tài liệu MongoDB nêu killOp từ mongos **không propagate tới shards đối với write**. Phải đánh giá hoạt động shard-side, kết quả commit và reconciliation.

### Bài 17. Khi query đã biến mất

CurrentOp được chụp lúc 13:00, một operation ID xuất hiện. 13:02 query đã biến mất.

**Câu hỏi:** Nên làm gì?

**Đáp án:** Không dùng lại opid cũ để kill. Xem profiler/log/APM để xác định kết quả và root cause; nếu workload tái diễn, quan sát operation mới đúng host/comment.

### Bài 18. applicationName

Mọi service hiện kết nối với appName rỗng. Người vận hành không phân biệt được query thuộc API hay worker.

**Câu hỏi:** Cần sửa ở đâu?

**Đáp án:** Đặt applicationName cho MongoClient/connection string của từng service, thống nhất naming convention và metadata tracing. Không sửa mỗi query trong MongoDB để đoán nguồn.

### Bài 19. Quyền inprog và killop

Một user có privilege inprog nhưng không có killop.

**Câu hỏi:** Có thể xem operations của user khác? Có thể kill tùy ý?

**Đáp án:** inprog cấp khả năng quan sát theo phạm vi phù hợp; **không tự cấp killop**. Can thiệp cần quyền killop hoặc các ngoại lệ own-operation trên mongod theo tài liệu.

### Bài 20. MaxTimeMS

Một read API có maxTimeMS 3000 nhưng HTTP request mất 7 giây.

**Câu hỏi:** Điều này chứng minh MongoDB bỏ qua maxTimeMS không?

**Đáp án:** Không. Request tổng gồm pool wait, network, serialization, app logic và retries. maxTimeMS không phải end-to-end deadline.

### Bài 21. Phân biệt QPS và currentOp count

Một dashboard chụp $currentOp và thấy 50 active operations.

**Câu hỏi:** Có thể kết luận cluster đang xử lý 50 queries/second không?

**Đáp án:** Không. Đây là **50 operations active trong một snapshot**, không phải tốc độ trên giây. QPS cần đo trong một cửa sổ thời gian bằng metrics phù hợp.

### Bài 22. Lọc theo namespace

Bạn muốn xem mọi hoạt động trên database **billing**, nhưng một số commands có ns là namespace lệnh thay vì billing.invoices.

**Câu hỏi:** Vì sao chỉ lọc exact ns billing.invoices có thể bỏ sót?

**Đáp án:** Một số commands/getMore thể hiện ns/command khác mục tiêu business collection. Có thể đối chiếu **command.find**, **command.aggregate**, **originatingCommand**, appName/comment và namespace liên quan.

### Bài 23. Phân tích một operation đang đợi flow control

Một write có **waitingForFlowControl=true**, replication lag cũng tăng.

**Câu hỏi:** Có chắc thiếu index là nguyên nhân?

**Đáp án:** Không. Đây có thể là tác động của flow control và replica set replication. Cần xem secondaries, write concern, resource utilization và lag trước khi đổi index hay kill writers.

### Bài 24. Profiler không phải currentOp

Một truy vấn chậm đã hoàn thành 5 phút trước. Người học đề xuất chạy $currentOp với secs_running > 5.

**Câu hỏi:** Công cụ nào phù hợp hơn?

**Đáp án:** Profiler/slow-query logs/Atlas Query Profiler hoặc application traces, vì currentOp chỉ cho snapshot hiện tại.

### Bài 25. Tại sao tránh profiler mức cao trên production?

**Định hướng:** Profiling có chi phí ghi/CPU/storage, tăng lượng logs và có thể lưu metadata truy vấn nhạy cảm. Bật theo sampling/filter/time window có kiểm soát, chọn quyền xem phù hợp.

### Bài 26. Query chạy lâu nhưng không tác động SLA

Một report đã lên lịch chạy 4 phút, progress bình thường và CPU/I/O còn dư.

**Câu hỏi:** Có cần killOp để đạt “không còn operation hơn 30 giây” không?

**Đáp án:** Không. Thời gian dài đơn lẻ không phải sự cố. Dựa trên SLA, owner, progress, khả năng hoàn thành và impact.

### Bài 27. Query với comment nhạy cảm

Một service ghi:

~~~text
comment = "lookup-taxid:123456789"
~~~

**Câu hỏi:** Có vấn đề gì?

**Đáp án:** Comment có thể xuất hiện trong currentOp/profiler/logs, làm lộ dữ liệu nhạy cảm. Dùng tag query shape không chứa taxId hoặc secrets.

### Bài 28. Auto-kill rule

Một script lập lịch chạy:

~~~text
Every 5 seconds:
  find all operations with secs_running > 20
  kill every returned opid
~~~

**Câu hỏi:** Có nên triển khai không?

**Đáp án:** Không. Rule không phân biệt internal operation, migration, getMore chờ hợp lệ, write/transaction, host/shard và approval. Nên cảnh báo, phân loại và can thiệp có kiểm soát.

### Bài 29. So sánh trước/sau killOp

Trước can thiệp:

~~~text
p95 API = 5.2 s
CPU = 95%
active expensive reads = 80
~~~

Sau can thiệp:

~~~text
p95 API = 4.9 s
CPU = 95%
active expensive reads = 78
~~~

**Câu hỏi:** Có thể tuyên bố thành công không?

**Định hướng:** Chưa đủ. Cần theo dõi lâu hơn, so sánh SLO mục tiêu, số lượng retries/operations mới và nguyên nhân gốc. Tác động cải thiện không đáng kể có thể chứng minh killOp không phải biện pháp đủ.

### Bài 30. Thiết kế runbook incident

Một cluster MongoDB sharded phục vụ nhiều ứng dụng. Một query read chạy 45 giây và đang làm API timeout.

**Yêu cầu:** Viết runbook gồm:

1. Kiểm tra impacted SLO và resource metrics.
2. Dùng $currentOp trên mongos với localOps phù hợp.
3. Xác định host/shard/opid, appName, namespace và query comment.
4. Phân biệt read operation thật với write/transaction/internal task.
5. Xác định owner và xin approval.
6. Thử stop/cancel từ ứng dụng hoặc giảm traffic trước.
7. Nếu cần, cân nhắc db.killOp tại đúng điểm kết nối và opid.
8. Quan sát killPending, client errors và retries.
9. Đối chiếu p95, CPU, locks, queue và replication sau can thiệp.
10. Dùng explain/profiler và sửa index, maxTimeMS, query shape để tránh lặp.

**Một lời giải tốt không tự động kill mọi operation 45 giây.** Nó phải giữ đủ context để không ảnh hưởng thao tác hợp lệ và không nhầm giữa mongos với shard.

## 25. Bảng quyết định điều tra nhanh

Một quy trình chẩn đoán có thể mô hình hóa:

~~~text
Application latency / DB alert
              |
              v
Do we know the affected query and time?
        /                   \
      Yes                    No
       |                      |
       v                      v
Is it still active?     Use APM/profiler/logs
    /        \                 |
  Yes         No               |
   |           |               |
   v           +---------------+
Read $currentOp
   |
   v
Collect host + opid + appName + ns + command tag
   |
   v
Classify operation
   |
   +--> Waiting for lock? -> Find blocker/transaction
   |
   +--> Query plan?       -> Explain/index/query rewrite
   |
   +--> getMore/stream?   -> Check cursor/await behavior
   |
   +--> Index build?      -> Change plan/progress/DBA
   |
   +--> Write/transaction?-> Check commit/abort/idempotency
   |
   +--> Sharded query?    -> Correlate mongos/shards
   |
   +--> Pool/network?     -> Application tracing
   |
   v
Is it client-initiated and causing significant harm?
           /                  \
          No                  Yes
          |                    |
          v                    v
Continue diagnosis      Cancel from application if possible
                               |
                               v
                     Confirm owner and approval
                               |
                               v
                     Recheck host/opid/type
                               |
                               v
                    Consider one controlled killOp
                               |
                               v
                       Verify and follow up
~~~

Sơ đồ nhấn mạnh rằng **quan sát và phân loại là bắt buộc**; killOp chỉ là **một nhánh tùy điều kiện** của runbook.

## 26. Checklist thực hành cho người trực vận hành

### 26.1. Trước khi mở currentOp

- [ ] Biết cluster và environment chính xác.
- [ ] Biết quyền quan sát inprog hiện có.
- [ ] Có timestamp và mô tả sự cố.
- [ ] Biết ứng dụng/endpoint hoặc namespace đang bị ảnh hưởng.
- [ ] Có metrics CPU, I/O, p95/p99, queue và replication làm baseline.

### 26.2. Khi đọc operation

- [ ] Xác nhận **host/shard/opid**.
- [ ] Xác nhận **appName/client**.
- [ ] Xem **active** và **secs_running**.
- [ ] Xem **op/type/ns**.
- [ ] Phân biệt **waitingForLock** với đang thực thi.
- [ ] Xem **planSummary** khi field có mặt.
- [ ] Xem **command/comment** sau khi cân nhắc dữ liệu nhạy cảm.
- [ ] Nhận diện getMore, index build, migration, internal task.
- [ ] Kiểm tra transaction/lsid nếu phù hợp.
- [ ] Đối chiếu profiler/APM/explain/metrics.

### 26.3. Trước khi cân nhắc killOp

- [ ] Operation **do client khởi tạo**; không phải internal MongoDB operation.
- [ ] Đã phân tích tác động đến end users và dữ liệu.
- [ ] Đã thử phương án ít gián đoạn hơn nếu khả thi.
- [ ] Đã kiểm tra write/transaction/unknown outcome.
- [ ] Đã kiểm tra mongos/shard-side semantics nếu cluster sharded.
- [ ] Được owner/on-call/DBA phê duyệt.
- [ ] Có quyền killop hoặc điều kiện own-operation phù hợp.
- [ ] Opid/host/command được **xác minh lại ngay trước hành động**.
- [ ] Có kế hoạch hậu kiểm và rollback/reconciliation nếu cần.

### 26.4. Sau khi ngắt

- [ ] Đã theo dõi killPending/operation state.
- [ ] Đã xem client errors/timeouts và retries.
- [ ] Đã xác minh tài nguyên/SLO có cải thiện không.
- [ ] Đã đối soát write outcomes nếu cần.
- [ ] Đã ghi lại incident timeline.
- [ ] Đã giao follow-up sửa index/query/deadline/batch/retry.

## 27. Nguồn tham khảo chính thức

Tài liệu có thể thay đổi theo MongoDB version và deployment. Những nguồn quan trọng:

- [MongoDB Manual — $currentOp aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/currentOp/)
- [MongoDB Manual — db.currentOp()](https://www.mongodb.com/docs/manual/reference/method/db.currentOp/)
- [MongoDB Manual — currentOp command](https://www.mongodb.com/docs/manual/reference/command/currentOp/)
- [MongoDB Manual — db.killOp()](https://www.mongodb.com/docs/manual/reference/method/db.killOp/)
- [MongoDB Manual — Terminate Running Operations](https://www.mongodb.com/docs/manual/tutorial/terminate-running-operations/)
- [MongoDB Manual — Monitor Slow Queries](https://www.mongodb.com/docs/manual/tutorial/monitor-slow-queries/)
- [MongoDB Manual — Privilege Actions: inprog and killop](https://www.mongodb.com/docs/manual/reference/privilege-actions/)
- [MongoDB Manual — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)

**Lưu ý phiên bản:** trên MongoDB 6.2+, **currentOp command đã deprecated** và nên ưu tiên **$currentOp aggregation stage**. Cách hiển thị metrics, targetAllNodes, queue information, field availability và sharded behavior có thể khác nhau theo phiên bản. Khi vận hành cụ thể, chọn nhánh tài liệu khớp **server version, mongosh, driver và Atlas tier**.

## 28. Tổng kết

Các khái niệm thường bị nhầm cần nhớ:

| Khái niệm | Ý nghĩa chính |
|---|---|
| $currentOp | Snapshot operations/sessions đang hoạt động hoặc idle tùy options |
| db.currentOp() | Mongosh helper quan sát nhanh |
| opid | ID một operation tại ngữ cảnh host/router/shard phù hợp |
| secs_running | Thời gian trôi qua của operation, không phải CPU time |
| active=true | Operation đang active, vẫn có thể đang chờ |
| waitingForLock=true | Operation đang chờ lock, cần tìm blocker |
| planSummary=COLLSCAN | Tín hiệu scan collection, cần xét query/data/index |
| planSummary=IXSCAN | Scan index, không bảo đảm hiệu quả toàn bộ query |
| getMore | Lấy batch từ cursor, có thể đang chờ sự kiện |
| idleSession/transaction | Session/transaction có thể giữ tài nguyên dù không chạy query |
| killPending | Đã có yêu cầu ngắt, đang chờ interrupt point |
| db.killOp(opid) | Yêu cầu ngắt **client-initiated** operation tại interrupt point |
| maxTimeMS | Giới hạn server-side được đặt trước operation |
| inprog | Privilege quan sát operations theo scope |
| killop | Privilege ngắt operations theo scope |
| localOps=true qua mongos | Quan sát router-local operations |
| localOps=false qua mongos | Quan sát operations ở shards |

**Mười nguyên tắc cốt lõi:**

1. **Thời gian chạy lâu không tự đồng nghĩa có lỗi.** Đánh giá theo SLO, loại workload, progress và tác động.
2. **Ưu tiên $currentOp** để quan sát hiện tại, lọc và project chỉ những field cần thiết.
3. **currentOp là snapshot**, không thay thế profiler, logs, explain và application tracing.
4. **Đọc opid cùng host/shard, appName, namespace, command và trạng thái chờ** trước khi đi đến kết luận.
5. **COLLSCAN/IXSCAN chỉ là dấu hiệu về plan**; phải xem executionStats và dữ liệu thực để quyết định index/query rewrite.
6. **Lock wait, idle transactions và getMore có nguyên nhân khác nhau**, không thể xử lý tất cả bằng killOp.
7. **Chỉ cân nhắc killOp cho operations do client khởi tạo**, khi đã xác minh đúng mục tiêu, quyền, tác động, owner và phương án thay thế.
8. **killOp không đồng nghĩa rollback toàn bộ write**, cũng không bảo đảm ngắt tức thì; client retry có thể khởi chạy operation mới.
9. **Trong sharded cluster, mongos kill read khác write**; read cancellation có thể propagate, còn mongos killOp không propagate đến shards cho write.
10. **Phòng ngừa tốt hơn can thiệp:** maxTimeMS, index phù hợp, pagination, batch checkpoints, appName/comment, backpressure và retry policy.

Mục tiêu của một người vận hành MongoDB không phải là làm cho danh sách currentOp trở nên trống, mà là **nhận diện đúng thao tác có vấn đề và chọn giải pháp ít rủi ro nhất**. Khi việc quan sát có đủ ngữ cảnh và việc dùng killOp tuân theo một runbook chặt chẽ, hệ thống vừa có khả năng xử lý sự cố nhanh vừa hạn chế gián đoạn dữ liệu và dịch vụ ngoài ý muốn.

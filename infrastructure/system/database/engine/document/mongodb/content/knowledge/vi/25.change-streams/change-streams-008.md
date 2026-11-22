# Thứ tự sự kiện, xử lý lặp và giới hạn bảo đảm giao nhận của MongoDB Change Streams

## 1. Vì sao đọc được sự kiện chưa có nghĩa đã xử lý đúng?

MongoDB **Change Streams** cho phép ứng dụng theo dõi những thay đổi đã được xác nhận trên collection, database hoặc phạm vi triển khai phù hợp. Một consumer có thể nhận sự kiện khi document được chèn, cập nhật, thay thế hoặc xóa, rồi cập nhật bộ nhớ đệm, xây bảng tra cứu, gửi thông báo hoặc đồng bộ dữ liệu sang hệ thống khác.

Ví dụ ứng dụng quản lý đơn hàng có một collection:

```javascript
{
  _id: "O-1001",
  customerId: "C01",
  status: "CREATED",
  total: 250000
}
```

Một đơn có thể trải qua các thay đổi:

```text
insert O-1001, status=CREATED
          |
          v
update O-1001, status=PAID
          |
          v
update O-1001, status=SHIPPED
          |
          v
delete O-1001 (nếu chính sách cho phép)
```

Consumer cần trả lời bốn câu hỏi độc lập:

1. **Thứ tự:** làm sao tránh xử lý `SHIPPED` trước `PAID` và sau đó vô tình ghi đè thành `PAID`?
2. **Lặp:** nếu đã xử lý sự kiện `PAID` nhưng mất kết nối trước khi lưu checkpoint, lần khởi động sau nhận lại sự kiện đó thì sao?
3. **Mất sự kiện:** nếu lưu checkpoint trước khi cập nhật hệ thống đích rồi tiến trình chết, ai bảo đảm sự kiện không bị bỏ qua?
4. **Giới hạn bảo đảm:** liệu Change Streams có mang ngữ nghĩa exactly-once cho cả MongoDB, Kafka, email và hệ thống thanh toán không?

Đây là ba trụ cột của bài:

> **Thứ tự sự kiện** được MongoDB cung cấp trong phạm vi một change stream, nhưng ứng dụng phải giữ thứ tự khi xử lý.

> **Resume token** giúp tiếp tục đọc từ một vị trí, nhưng không tự ghi nhớ các side effect mà consumer đã thực hiện.

> **At-least-once, at-most-once và exactly-once** là các tính chất của **toàn quy trình xử lý**, không phải những nhãn có thể mặc nhiên gán cho một lệnh `watch()`.

### 1.1. Mục tiêu bài học

Sau bài này, bạn có thể:

- Mở một change stream, đọc `operationType`, `documentKey`, `clusterTime` và `_id` resume token.
- Phân biệt **thứ tự nhận từ một cursor** với **thứ tự side effect hoàn tất** khi có nhiều worker.
- Giải thích vì sao `clusterTime` và `ObjectId` không thay cho resume token.
- Chọn thứ tự đúng giữa **xử lý sự kiện** và **lưu checkpoint**.
- Thiết kế **deduplication/idempotency** bằng khóa ổn định.
- Hiểu giới hạn của `resumeAfter`, `startAfter`, `startAtOperationTime` và **oplog window**.
- Phân biệt bảo đảm nhận sự kiện với bảo đảm ghi kết quả ra MongoDB hoặc hệ thống ngoài.
- Viết một consumer cơ bản bằng **mongosh** và **MongoDB Java Sync Driver**.

## 2. Change Stream là gì và cần điều kiện gì?

### 2.1. Theo dõi thay đổi thay vì quét lặp collection

Không có change stream, ứng dụng có thể phải polling:

```javascript
db.orders.find({
  updatedAt: { $gt: lastCheckedAt }
});
```

Cách này có các vấn đề:

- `updatedAt` có thể bị bỏ quên khi cập nhật.
- Nhiều thay đổi trên cùng document giữa hai lần polling có thể bị gộp mất.
- Độ chính xác phụ thuộc đồng hồ và quy tắc cập nhật timestamp.
- Muốn phát hiện delete phải thiết kế tombstone hoặc cách theo dõi riêng.

Change Stream là **luồng sự kiện thay đổi** dựa trên cơ chế MongoDB, giúp consumer phát hiện thay đổi theo trình tự của luồng mà không phải tự tạo timestamp cho mọi document.

### 2.2. Deployment được hỗ trợ

Change Streams yêu cầu MongoDB deployment có khả năng replication, điển hình là:

- **Replica set**.
- **Sharded cluster**.

Một standalone `mongod` không chạy với replica set không phải môi trường tiêu chuẩn để thử `watch()`. Trong lab, có thể dùng **single-node replica set** để thực hành cú pháp, nhưng nó không mô phỏng failover hay độ trễ giữa các thành viên.

Change stream nhìn thấy những thay đổi đã đạt các điều kiện commit/majority theo cơ chế server; nó **không cung cấp các thay đổi chưa commit của transaction** như những sự kiện nghiệp vụ đã hoàn tất.

### 2.3. Ba phạm vi theo dõi

Trong mongosh:

```javascript
// Một collection.
db.orders.watch();

// Một database: các thay đổi của collection trong database này.
db.watch();

// Phạm vi toàn deployment theo API/điều kiện hỗ trợ.
db.getMongo().watch();
```

Phạm vi rộng hơn đồng nghĩa nhiều sự kiện, chi phí lọc và quyền truy cập hơn. Không nên dùng stream toàn deployment nếu chỉ cần cập nhật cache cho một collection.

### 2.4. Change Stream không phải hàng đợi lưu trữ vô hạn

Change Streams dựa trên lịch sử thay đổi được duy trì bởi MongoDB, liên quan đến **oplog**. Khả năng resume có **giới hạn theo lịch sử còn được lưu**, không phải một log vĩnh viễn như một hệ thống lưu trữ sự kiện chuyên dụng được cấu hình giữ nhiều năm.

Nếu consumer offline lâu hơn lịch sử cần thiết còn tồn tại, checkpoint cũ có thể không còn resume được. Khi đó không thể giả định “cứ truyền token là chắc chắn lấy lại đủ sự kiện”.

## 3. Hình dạng một sự kiện Change Stream

Ví dụ trong collection `orders`, sau thao tác:

```javascript
db.orders.updateOne(
  { _id: "O-1001" },
  { $set: { status: "PAID" } }
);
```

Consumer có thể nhận một sự kiện dạng rút gọn:

```javascript
{
  _id: {
    _data: "8265...opaque-resume-token..."
  },
  operationType: "update",
  clusterTime: Timestamp(1720000000, 1),
  ns: {
    db: "shop",
    coll: "orders"
  },
  documentKey: {
    _id: "O-1001"
  },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
```

**Đây là ví dụ cấu trúc minh họa**, không phải token hoặc timestamp hợp lệ để copy vào API. Server version, thao tác, phạm vi theo dõi và tùy chọn `watch()` ảnh hưởng các trường có mặt.

### 3.1. Những trường cần hiểu

| Trường | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `_id` | **Resume token**, định danh vị trí của event trong change stream | Lưu nguyên vẹn để resume/checkpoint |
| `operationType` | Loại thay đổi: `insert`, `update`, `replace`, `delete`… | Quyết định nhánh xử lý |
| `ns` | Database và collection liên quan | Xác định nguồn của sự kiện |
| `documentKey` | Khóa document bị thay đổi, có thể gồm shard key tùy cấu hình | Liên hệ với entity nghiệp vụ |
| `clusterTime` | Mốc thời gian logic của sự kiện | Quan sát, đối chiếu; **không thay token** |
| `fullDocument` | Nội dung document nếu được cung cấp theo operation/tùy chọn | Dùng xây projection khi phù hợp |
| `updateDescription` | Trường thay đổi/xóa ở sự kiện update | Cập nhật có chọn lọc hoặc audit |
| `lsid`, `txnNumber` | Có thể xuất hiện với thay đổi thuộc transaction | Liên hệ các thay đổi cùng transaction khi có |

Một event có thể chứa các metadata khác. Không xây consumer dựa trên giả định mọi event luôn có `fullDocument` hoặc `updateDescription`.

### 3.2. `_id` trong event không phải `_id` của document đơn hàng

Ví dụ:

```javascript
// _id của SỰ KIỆN: resume token, giá trị BSON opaque.
change._id

// _id của DOCUMENT bị đổi:
change.documentKey._id
```

Hai giá trị phục vụ hai mục đích:

- `change._id`: **vị trí của một thay đổi cụ thể** trong change stream.
- `change.documentKey._id`: **định danh entity** mà nhiều thay đổi có thể tác động.

Một document đơn hàng có thể có hàng trăm event khác nhau nhưng luôn cùng `documentKey._id`.

### 3.3. Sự kiện khác nhau có thể cùng `documentKey`

```text
Event E1: update O-1001 status=CREATED
Event E2: update O-1001 status=PAID
Event E3: update O-1001 status=SHIPPED
```

Nếu dùng riêng `documentKey._id` để dedupe event, consumer có thể giữ E1 rồi **bỏ E2 và E3**. Đây là lỗi nghiêm trọng.

Muốn dedupe **sự kiện**, dùng định danh sự kiện thích hợp như **resume token được lưu nguyên vẹn** hoặc khóa nghiệp vụ/sequence do nguồn thiết kế. Muốn xác định **đơn hàng**, dùng `documentKey`.

## 4. Thứ tự trong một change stream

### 4.1. Thứ tự luồng do MongoDB cung cấp

Khi một consumer đọc **tuần tự** từ một change stream cursor, nó nhận các event theo trình tự mà MongoDB trình bày cho stream đó.

Ví dụ:

```text
watch(orders)
  |
  +-- E1: insert O-1001
  |
  +-- E2: update O-1001 status=PAID
  |
  +-- E3: update O-1001 status=SHIPPED
```

Nếu consumer thực hiện:

```text
read E1 -> process E1 -> checkpoint E1
read E2 -> process E2 -> checkpoint E2
read E3 -> process E3 -> checkpoint E3
```

thì thứ tự **hoàn thành xử lý** phù hợp với thứ tự **đọc từ cursor**.

### 4.2. Không đồng nghĩa mọi consumer nhìn và xử lý giống hệt nhau

Cần phân biệt:

- Một stream collection chỉ thấy thay đổi của collection đó.
- Một stream database có thể thấy sự kiện của nhiều collection.
- Một stream có pipeline `$match` có thể lọc bỏ một số event.
- Hai consumer có thể bắt đầu ở hai vị trí khác nhau.
- Hai consumer có tốc độ và trạng thái checkpoint khác nhau.

Do đó không được suy ra **một thứ tự xử lý toàn cục giữa mọi service** chỉ vì tất cả dùng Change Streams.

### 4.3. Thứ tự nhận không tự bảo đảm thứ tự hoàn tất

Giả sử consumer đọc tuần tự nhưng giao việc cho hai thread:

```text
Cursor đọc:
  E1: status=PAID
  E2: status=SHIPPED

Worker 1 nhận E1: xử lý mất 900 ms
Worker 2 nhận E2: xử lý mất 100 ms

Thứ tự hoàn tất:
  E2 xong trước
  E1 xong sau
```

Nếu cả hai worker đều ghi:

```javascript
db.orderCache.updateOne(
  { _id: "O-1001" },
  { $set: { status: nextStatus } },
  { upsert: true }
);
```

thì kết quả cuối có thể bị **ghi lùi về PAID** dù event mới hơn đã chuyển thành SHIPPED.

Đây là vấn đề của **ứng dụng xử lý song song**, không phải bằng chứng MongoDB đã phát event sai thứ tự.

## 5. Thứ tự logic khác thời gian đồng hồ

### 5.1. `clusterTime` là thời gian logic

`clusterTime` đại diện cho mốc logic của thay đổi. Nó hữu ích khi quan sát diễn biến và thực hiện một số thao tác bắt đầu stream, nhưng không nên xem nó như **ID sự kiện duy nhất** hay timestamp đồng hồ đo được chính xác từng mili-giây.

Hai event có thể có `clusterTime` giống nhau, đặc biệt khi các thay đổi thuộc cùng một transaction.

```text
Event A: clusterTime = T, documentKey = O-01
Event B: clusterTime = T, documentKey = O-02

Nếu lưu duy nhất T làm checkpoint:
  Không biết đã xử lý A, B, hay cả hai.
```

### 5.2. Không dùng `clusterTime` làm khóa dedupe duy nhất

Đây là thiết kế sai:

```javascript
// KHÔNG dùng clusterTime làm eventId duy nhất.
const eventId = String(change.clusterTime);
```

Nó có thể gây mất các event khác nhau có cùng mốc logic.

Sử dụng:

```javascript
const resumeToken = change._id;
```

và lưu **giá trị BSON của token**, không tự phân tích hoặc sửa chuỗi `_data`.

### 5.3. Không sắp xếp event bằng `_id` của document nghiệp vụ

Nếu event của đơn `O-9999` xuất hiện trước event của `O-0001`, sắp xếp theo `documentKey._id` sẽ đảo thứ tự so với stream.

Tương tự, **ObjectId của document** được tạo ở thời điểm insert không phải sequence của các lần update sau đó. Đừng dùng nó để tái lập thứ tự thay đổi.

### 5.4. `clusterTime` không bảo đảm thứ tự side effect bên ngoài

Giả sử gửi event ra Kafka, email hoặc HTTP. Dù MongoDB xuất event theo stream order, các hệ thống đích có thể:

- Xử lý ở nhiều partition.
- Có nhiều consumer song song.
- Retry các request chậm.
- Hoàn tất sau timeout với thứ tự khác.

Muốn giữ thứ tự theo entity, phải thiết kế **partitioning, sequencing, idempotency hoặc kiểm tra version** tại nơi áp dụng.

## 6. Thứ tự với sharded cluster

### 6.1. Nhiều shard tạo ra nhiều nguồn thay đổi

Trong sharded cluster:

```text
Shard A: A1 -------- A2 -------- A3
Shard B: ----- B1 -------- B2 -----
Shard C: --- C1 ---------------- C2

                |
                v
              mongos
                |
                v
        Change stream cursor
        được phối hợp/merge
```

MongoDB phối hợp luồng sự kiện trên các shard để cung cấp trình tự thay đổi cho **một stream qua mongos**, sử dụng cơ chế thứ tự logic/metadata của cluster. Ứng dụng nên dựa trên **thứ tự trả ra bởi cursor**, không tự ghép kết quả từ ba shard rồi sắp theo `Date.now()`.

### 6.2. Đừng giả định một stream trên từng shard thay cho một stream qua mongos

Nếu ứng dụng tự kết nối trực tiếp từng shard để nhận sự kiện và trộn chúng, nó phải tự giải quyết các vấn đề:

- Đồng bộ mốc logic giữa nguồn.
- Sự kiện đến trễ.
- Những thay đổi diễn ra gần nhau.
- Thay đổi quyền sở hữu range do balancer.
- Checkpoint và khôi phục trên mỗi nguồn.

Với mục tiêu theo dõi **sharded collection**, thường nên dùng **Change Stream qua mongos** theo API được MongoDB hỗ trợ.

### 6.3. Migration không có nghĩa document nghiệp vụ đã được update

Khi balancer chuyển range giữa shards, đó là hoạt động quản trị phân bố dữ liệu, không phải một nghiệp vụ ứng dụng `update status` cho từng document.

Không tự suy rằng mỗi document được copy giữa shards sẽ phát ra một event `insert` mới tương đương thao tác insert từ ứng dụng. Consumer phải dựa vào **operationType và contract change stream**, không dựa vào số bản copy vật lý của MongoDB.

### 6.4. Thêm shard và topology thay đổi

Trong lúc scale cluster hoặc migration, consumer vẫn cần:

- Kết nối qua router phù hợp.
- Driver tương thích version.
- Resume token/checkpoint đáng tin cậy.
- Giám sát độ trễ và các lỗi resumability.

Không dùng hostname shard cố định trong business logic để quyết định event thuộc entity nào.

## 7. Transaction và những event có cùng `clusterTime`

### 7.1. Một transaction có thể thay đổi nhiều document

Ví dụ transaction chuyển tiền:

```text
Transaction TX-01:
  update accounts(A)
  update accounts(B)
  insert transferLedger(TR-01)
  commit
```

Khi transaction commit, change stream có thể phát nhiều event tương ứng các thay đổi.

Điểm quan trọng:

- Những event từ cùng transaction **có thể chia sẻ một `clusterTime`**.
- Một số event có thể mang thông tin `lsid`/`txnNumber` để liên hệ transaction.
- Không được dedupe bằng `clusterTime`.
- Không được giả định “một transaction = một change event”.

### 7.2. Event được nhìn thấy sau commit

Các thay đổi chưa commit của transaction không được xem như những event nghiệp vụ đã được công bố. Khi transaction abort, ứng dụng không nên mong nhận một chuỗi change events tương đương các cập nhật đã bị hủy.

Điều này rất hữu ích cho việc xây projection: một stream chỉ phát các thay đổi hợp lệ theo commit semantics, chứ không yêu cầu consumer tự xử lý rollback của từng thao tác chưa commit.

### 7.3. Consumer vẫn cần tính nhất quán ở nơi nhận

Giả sử ba event của một transaction được đưa qua hai worker. Worker A cập nhật cache tài khoản A; worker B cập nhật cache tài khoản B chậm hơn.

Trong khoảng thời gian ngắn, hệ thống cache ngoài MongoDB có thể nhìn thấy **trạng thái chuyển tiếp**, dù transaction MongoDB đã commit nguyên tử.

Do đó:

> **Atomicity của transaction ở nguồn không tự kéo theo atomicity của projection tại hệ thống đích.**

Nếu projection yêu cầu nhất quán giữa nhiều entity, cần xử lý nhóm event/transaction, dùng một transaction ở đích khi có thể, hoặc thiết kế version/snapshot để người đọc không thấy trạng thái trung gian.

## 8. `fullDocument` và bẫy thời điểm đọc

### 8.1. Sự kiện update không luôn chứa toàn bộ document

Một event `operationType: "update"` thường có `updateDescription`:

```javascript
{
  operationType: "update",
  documentKey: { _id: "O-1001" },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

Nếu consumer cần toàn bộ trạng thái đơn hàng, có thể mở stream với:

```javascript
db.orders.watch([], {
  fullDocument: "updateLookup"
});
```

### 8.2. `updateLookup` không bảo đảm document là đúng ảnh chụp của event

Đây là một bẫy quan trọng khi xây cache:

```text
T1: O-1001 chuyển status=PAID      -> event E1
T2: O-1001 chuyển status=SHIPPED   -> event E2
T3: Consumer xử lý E1, thực hiện updateLookup
```

Khi lookup diễn ra ở T3, `fullDocument` trả về có thể phản ánh trạng thái **mới hơn** sự kiện E1, chẳng hạn `SHIPPED`, chứ không nhất thiết là ảnh chụp chính xác ngay sau update E1. Trong một số trường hợp document có thể đã bị xóa nên kết quả lookup không còn.

Vì vậy:

- Nếu chỉ cần các trường thay đổi ở E1, xét `updateDescription`.
- Nếu cần trạng thái gần hiện tại, `updateLookup` có thể phù hợp.
- Nếu cần **ảnh document đúng tại thời điểm event**, nghiên cứu hỗ trợ **change stream pre/post-images** của phiên bản triển khai và yêu cầu bật/retention.
- Không dựa vào `fullDocument` từ `updateLookup` để suy rằng event E1 thực sự đã ghi trạng thái SHIPPED.

### 8.3. Pre-images và post-images

MongoDB các phiên bản hỗ trợ có thể cung cấp:

- **Pre-image:** document trước thay đổi.
- **Post-image:** document sau thay đổi.

Tính năng này có yêu cầu cấu hình và lưu giữ riêng; hình thức chọn `fullDocumentBeforeChange`, `fullDocument` và các giá trị như `whenAvailable`/`required` tùy API/version.

Pre/post-images **không tự biến Change Streams thành log lưu vĩnh viễn**. Nếu ảnh trước/sau bị hết hạn theo chính sách retention, consumer có thể không còn lấy lại được lịch sử mong muốn.

## 9. Mở change stream bằng mongosh

### 9.1. Chuẩn bị collection thử nghiệm

Lab cần một **replica set** hoặc **sharded cluster** có thể chạy Change Streams. Các lệnh dưới đây chỉ dùng database riêng, không tác động collection production.

Trong terminal mongosh thứ nhất:

```javascript
const labDb = db.getSiblingDB("change_stream_lab277");
const orders = labDb.orders277;

// Chỉ dùng collection lab. Tạo collection nếu chưa tồn tại.
if (!labDb.getCollectionNames().includes("orders277")) {
  labDb.createCollection("orders277");
}

print("Ready for change stream lab");
```

Không dùng `drop()` để reset khi một change stream đang chạy, vì drop có thể dẫn tới sự kiện invalidate và làm stream hiện hành đóng lại.

### 9.2. Mở stream trước khi phát sự kiện

Trong terminal mongosh đang kết nối tới MongoDB lab:

```javascript
const labDb = db.getSiblingDB("change_stream_lab277");
const cursor = labDb.orders277.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace", "delete"]
        }
      }
    }
  ],
  { fullDocument: "updateLookup" }
);

print("Watching orders277. Open another terminal to make changes.");

try {
  while (cursor.hasNext()) {
    const change = cursor.next();

    printjson({
      type: change.operationType,
      documentKey: change.documentKey,
      clusterTime: change.clusterTime,
      resumeToken: change._id,
      updatedFields: change.updateDescription
        ? change.updateDescription.updatedFields
        : undefined
    });
  }
} finally {
  cursor.close();
}
```

Lệnh `hasNext()` có thể chờ sự kiện; đây là hành vi bình thường với một stream đang mở. Để dừng lab, ngắt vòng lặp/đóng cursor theo cách của terminal.

### 9.3. Tạo các thay đổi từ terminal khác

Trong **terminal thứ hai**:

```javascript
const labDb = db.getSiblingDB("change_stream_lab277");

labDb.orders277.insertOne({
  _id: "O-277-001",
  status: "CREATED",
  total: 250000,
  customerId: "C01"
});

labDb.orders277.updateOne(
  { _id: "O-277-001" },
  { $set: { status: "PAID" } }
);

labDb.orders277.updateOne(
  { _id: "O-277-001" },
  { $set: { status: "SHIPPED" } }
);

labDb.orders277.insertOne({
  _id: "O-277-002",
  status: "CREATED",
  total: 100000
});
```

Consumer sẽ nhận các event theo thứ tự của stream. Đừng dựa vào ví dụ để dự đoán chính xác giá trị token BSON hoặc thời điểm server báo từng event.

### 9.4. Khi nào cần pipeline `$match`?

Lọc event loại `insert`/`update` giúp giảm công việc phía consumer:

```javascript
const c = labDb.orders277.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update"]
      }
    }
  }
]);
```

Tuy nhiên, một pipeline lọc mất `delete` có thể khiến cache không xóa entity đã biến mất. Khi thiết kế, phải quyết định **những loại thay đổi nào quan trọng cho trạng thái đích**.

## 10. Resume token: định danh tiến độ đáng tin cậy hơn timestamp

### 10.1. Token đi cùng từng event

Mỗi sự kiện trả về thường mang `_id` là **resume token**. Ví dụ:

```javascript
const change = cursor.next();
const token = change._id;
```

Token là một **giá trị BSON opaque**. Không:

- Tự cắt chuỗi `_data`.
- So sánh token bằng thứ tự chữ cái.
- Đoán định dạng token cố định qua các MongoDB version.
- Dùng `new ObjectId()` thay thế token.
- Tạo token giả từ `clusterTime`.

### 10.2. Token dùng để tiếp tục sau một vị trí

Khi ứng dụng đã xử lý thành công event E10 và lưu token của nó, một stream mới có thể mở với:

```javascript
const resumed = labDb.orders277.watch(
  [],
  {
    resumeAfter: storedToken,
    fullDocument: "updateLookup"
  }
);
```

Ý định của `resumeAfter` là **tiếp tục sau vị trí token**, không phát lại chính event có token đó như một yêu cầu mặc định.

**Điều kiện quan trọng:** token vẫn phải còn hợp lệ/resumable và cấu hình phạm vi stream phải tương thích. Nó không phải phiếu bảo đảm vô hạn.

### 10.3. Nên lưu token ở đâu?

Ứng dụng có thể lưu một document checkpoint:

```javascript
{
  _id: "orders-projection-v1",
  namespace: "change_stream_lab277.orders277",
  resumeToken: {
    _data: "opaque BSON token, example only"
  },
  savedAt: ISODate("2026-11-14T04:00:00Z")
}
```

Trong hệ thống thật, trường `resumeToken` phải lưu **giá trị thực được driver trả về**, không phải chuỗi ví dụ. Bảo đảm serializer **round-trip đầy đủ kiểu BSON**; tự chuyển token sang String JSON tùy ý có thể làm mất thông tin kiểu/field.

### 10.4. Checkpoint là cam kết của consumer, không phải của MongoDB

Change Stream **không tự biết** cache, email hay HTTP downstream của ứng dụng đã được xử lý xong.

MongoDB có thể trả event E10, nhưng liệu consumer đã:

- Ghi cache?
- Gửi message?
- Cập nhật projection?
- Persist checkpoint?

thì MongoDB **không quản lý toàn bộ vòng đời nghiệp vụ đó** cho ứng dụng.

Checkpoint phải thể hiện **mức tiến độ mà consumer có thể chịu trách nhiệm**.

## 11. Thứ tự “xử lý trước — checkpoint sau”

Đây là mẫu phổ biến khi muốn ưu tiên **không bỏ sót sự kiện**, chấp nhận khả năng xử lý lặp:

```text
Nhận event E10
      |
      v
Thực hiện side effect E10
      |
      v
Side effect được xác nhận thành công
      |
      v
Lưu resume token của E10
      |
      v
Nhận event E11
```

### 11.1. Crash window dẫn tới lặp

Giả sử:

```text
T1: Nhận E10.
T2: Ghi projection cho E10 thành công.
T3: Process crash TRƯỚC khi lưu token E10.
T4: Restart, resumeAfter token E9.
T5: Nhận lại E10.
```

E10 có thể bị **xử lý hai lần**. Đây là một replay **dự kiến** trong chiến lược xử lý trước, checkpoint sau.

Nếu side effect là:

```javascript
{ $set: { status: "PAID" } }
```

thì lặp lại thường giữ cùng trạng thái trường đó.

Nếu side effect là:

```javascript
{ $inc: { totalPaidOrders: 1 } }
```

thì lặp lại làm bộ đếm tăng hai lần, gây sai dữ liệu.

**Kết luận:** checkpoint sau xử lý giúp tránh cố tình bỏ event, nhưng phải có idempotency/dedupe để lặp không gây sai.

### 11.2. Cách hiểu at-least-once

Với checkpoint bền vững, resume hợp lệ và consumer có thể retry, ứng dụng có thể xây chiến lược **at-least-once processing**:

> Event chưa được checkpoint sẽ có cơ hội được nhận lại và xử lý lại, nên phải chấp nhận duplicate.

Đây là một mục tiêu **có điều kiện**, không phải bảo đảm vô điều kiện rằng MongoDB giữ mọi sự kiện vĩnh viễn. Nếu oplog history đã hết hoặc có lỗi không resumable, chiến lược này có thể phải dùng **rebuild/reconciliation** để phục hồi.

## 12. Thứ tự “checkpoint trước — xử lý sau”

Một số ứng dụng muốn tránh replay, nên lưu checkpoint trước:

```text
Nhận E10
      |
      v
Lưu token E10
      |
      v
Gửi event E10 tới downstream
```

### 12.1. Crash window dẫn tới mất xử lý

```text
T1: Nhận E10.
T2: Checkpoint E10 thành công.
T3: Process crash TRƯỚC khi ghi projection.
T4: Restart với resumeAfter E10.
T5: Stream tiếp tục từ E11.
```

E10 bị **bỏ qua ở phía consumer**, dù MongoDB đã từng phát sự kiện đó.

Đây là rủi ro **at-most-once theo cách thiết kế pipeline xử lý**: ưu tiên tránh xử lý lặp bằng cách chấp nhận mất hiệu ứng nếu có lỗi giữa checkpoint và side effect.

### 12.2. “Không có duplicate” không có nghĩa hệ thống đúng

Một projection sai vì bỏ mất event update có thể nguy hiểm hơn projection có replay được xử lý idempotent. Do đó nhiều ứng dụng ưu tiên:

```text
process -> durable acknowledge -> checkpoint
```

và thiết kế side effect có thể lặp an toàn, thay vì checkpoint trước để “loại lỗi duplicate”.

## 13. Ba mức bảo đảm giao nhận

### 13.1. At-most-once

Một sự kiện được xử lý **không quá một lần** theo thiết kế consumer, nhưng có thể bị **bỏ qua** nếu xảy ra crash ở cửa sổ không an toàn.

Mẫu đơn giản:

```text
checkpoint E10
  |
  X crash
  |
E10 không được chạy side effect
```

At-most-once không phù hợp nếu mọi sự kiện thay đổi số dư hoặc quyền truy cập đều bắt buộc phải được áp dụng.

### 13.2. At-least-once

Mục tiêu là mỗi sự kiện cần xử lý được xử lý **ít nhất một lần**, với điều kiện có khả năng replay/khôi phục.

```text
process E10
  |
  X crash trước checkpoint
  |
resume sau E9
  |
process E10 thêm một lần
```

Ứng dụng phải chấp nhận duplicate và biến thao tác thành **idempotent**.

### 13.3. Exactly-once

“Exactly-once” có thể mang nhiều nghĩa:

1. **Event được giao đúng một lần** cho callback.
2. **Side effect trong database đích xuất hiện đúng một lần**.
3. **Toàn bộ workflow xuyên MongoDB, broker, HTTP, email, payment gateway** có tác động nghiệp vụ đúng một lần.

Không được đồng nhất ba nghĩa đó.

Chỉ dùng `watch()` và `resumeAfter` **không tự bảo đảm exactly-once end-to-end**. Muốn đạt một dạng “exactly-once effect”, phải xác định **ranh giới atomicity** và thiết kế checkpoint + side effect + deduplication tương ứng.

### 13.4. Bảng so sánh

| Mục tiêu | Chiến lược ví dụ | Rủi ro còn lại |
|---|---|---|
| At-most-once | Lưu token trước khi side effect | Có thể mất side effect |
| At-least-once | Side effect xong mới lưu token | Có thể xử lý lặp |
| Effectively-once cho một projection | At-least-once + idempotent update/dedupe | Cần bảo đảm thứ tự và phục hồi checkpoint |
| Atomic effect + checkpoint trong cùng MongoDB transaction | Commit cả hai vào một transaction được hỗ trợ | Chỉ bao trùm những thao tác cùng transaction |
| Exactly-once end-to-end qua nhiều hệ thống | Thiết kế protocol/idempotency ở từng bên, outbox/inbox, đối soát | Không được hứa chỉ từ Change Stream |

## 14. Dedupe: phải chọn đúng khóa

### 14.1. Không dedupe bằng document key

Sai:

```javascript
// Không dùng orderId làm "event đã xử lý" duy nhất.
const dedupeId = change.documentKey._id;
```

Vì cùng orderId có nhiều event hợp lệ theo thời gian, cách này làm mất những cập nhật sau.

### 14.2. Resume token làm định danh sự kiện

Token là ứng viên để xác định **event cụ thể của một stream**. Có thể lưu nguyên token BSON trong một inbox hoặc checkpoint.

Ví dụ schema minh họa:

```javascript
{
  _id: {
    source: "orders-projection-v1",
    token: { _data: "opaque-token-example" }
  },
  processedAt: ISODate("2026-11-14T04:05:00Z"),
  result: "APPLIED"
}
```

Đây chỉ là **ý tưởng schema**, không phải yêu cầu phải lấy chuỗi `_data` rồi ghép bằng tay.

Nếu dùng hash để tạo một ID compact, phải:

- Hash biểu diễn BSON **ổn định, không mất kiểu**, được định nghĩa rõ.
- Gắn namespace/scope/consumer identity nếu cần.
- Tránh biến `token.toString()` của một thư viện thành hợp đồng lưu trữ lâu dài.
- Kiểm tra khả năng collision và xử lý nó.

Với MongoDB, có thể lưu nguyên `BsonDocument` token vào trường và dùng ràng buộc unique cho identifier thích hợp.

### 14.3. Business event ID từ outbox có thể tốt hơn

Nếu chính ứng dụng nguồn có thể ghi **outbox event**:

```javascript
{
  _id: "EVT-2026-0001",
  aggregateId: "O-1001",
  eventType: "OrderPaid",
  aggregateVersion: 3,
  payload: {
    orderId: "O-1001",
    total: 250000
  }
}
```

consumer có thể dedupe bằng `_id` của **outbox event nghiệp vụ**, độc lập với định dạng resume token của MongoDB.

Resume token vẫn cần để **đọc tiếp change stream**, còn `eventId` phục vụ **tính duy nhất của sự kiện nghiệp vụ** ở các hệ thống downstream.

### 14.4. Dedupe cần thao tác nguyên tử

Đừng làm:

```text
if (!processedEvents.contains(eventId)) {
    sendPayment();
    processedEvents.insert(eventId);
}
```

nếu hai worker có thể cùng kiểm tra trước khi bất kỳ worker nào insert. Cả hai có thể thấy “chưa xử lý” rồi cùng gửi payment.

Thường cần **unique constraint** hoặc thao tác conditional atomic, và nếu side effect ở MongoDB thì cân nhắc transaction để bảo vệ việc ghi marker + dữ liệu đích cùng lúc.

## 15. Idempotent update: áp dụng cùng event nhiều lần không làm sai

### 15.1. `$set` giá trị cố định

Một projection cập nhật trạng thái:

```javascript
db.orderProjection277.updateOne(
  { _id: "O-1001" },
  {
    $set: {
      status: "PAID",
      total: 250000
    }
  },
  { upsert: true }
);
```

Nếu chạy lại **đúng thao tác** trên cùng document, riêng các trường được set thường giữ cùng giá trị.

Nhưng có hai lưu ý:

1. Nếu event cũ chạy **sau event mới**, `$set` có thể ghi lùi trạng thái.
2. Nếu mỗi lần retry còn gọi API, gửi email hoặc thay `updatedAt = new Date()`, **toàn workflow** không còn có cùng tác động.

Do đó **idempotency chống duplicate** và **ordering chống stale write** là hai nhu cầu riêng.

### 15.2. `$inc` là ví dụ điển hình của không idempotent

```javascript
db.dailyMetrics277.updateOne(
  { _id: "2026-11-14" },
  { $inc: { paidOrders: 1 } },
  { upsert: true }
);
```

Nếu sự kiện OrderPaid bị replay hai lần, `paidOrders` có thể tăng từ 10 lên 12 thay vì 11.

Các lựa chọn:

- Dedupe bằng `eventId`/token trước khi áp dụng phép đếm, với cơ chế atomic.
- Tính lại count từ nguồn sự thật trong những trường hợp phù hợp.
- Dùng bảng materialized view có checkpoint/version và cơ chế phục hồi.
- Thiết kế outbox/inbox với unique event ID.

### 15.3. Dedupe marker và counter cùng transaction

Nếu cả hai collection nằm trong cùng MongoDB deployment hỗ trợ transaction, một mô hình:

```text
Transaction tại DB đích:
  1. Insert processedEvents[eventId] (unique)
  2. $inc dailyMetrics
  3. Update checkpoint cho consumer
  4. Commit
```

Nếu đã có `eventId`, không tăng counter lần nữa. Nếu transaction abort, cả marker, counter và checkpoint cùng bị hủy trong phạm vi transaction.

Điều này có thể cung cấp **exactly-once effect trong ranh giới MongoDB transaction** với thiết kế đúng, nhưng không bao trùm email/HTTP bên ngoài.

## 16. Checkpoint và side effect trong cùng MongoDB transaction

### 16.1. Mục tiêu

Thay vì:

```text
Write projection -> Write checkpoint
```

có **cửa sổ crash** ở giữa, ta muốn:

```text
Begin transaction
  +-- Apply event to projection
  +-- Save checkpoint
Commit
```

Nếu transaction commit, **cả hai** có hiệu lực; nếu abort, **cả hai** không có hiệu lực.

### 16.2. Điều kiện

Phải bảo đảm:

- Projection và checkpoint nằm trong môi trường MongoDB hỗ trợ transaction thích hợp.
- Tất cả thao tác ghi liên quan được thực hiện **trong cùng session/transaction**.
- Có write concern đủ phù hợp tại commit.
- Có cơ chế chống replay/đua tranh khi consumer chạy song song.
- Không đặt side effect ngoài MongoDB vào transaction rồi mặc định nó được rollback.

Change stream cursor thường được **đọc ngoài transaction**; transaction ở đây phục vụ **ghi kết quả và checkpoint**, không cố mở `watch()` bên trong transaction.

### 16.3. Pseudocode của processor

```text
cursor = watch(source, resumeAfter = durableCheckpoint)

for each event E, theo thứ tự:
    begin transaction tại target MongoDB

    if E.id chưa tồn tại trong inbox:
        apply E vào projection
        insert inbox[E.id]

    update checkpoint = E.resumeToken
    commit transaction

    // Chỉ sau khi commit thành công hoặc đã đối soát:
    // mới xem checkpoint E là tiến độ bền vững.
```

Trong thực tế, nếu commit trả trạng thái **không rõ**, không tự chạy một transaction mới với side effect không idempotent. Dùng retry commit/đối soát theo driver và event ID.

### 16.4. Checkpoint chung khi có nhiều consumer

Nếu hai process cùng đọc và cùng ghi:

```text
Consumer A: xử lý E10 chậm
Consumer B: xử lý E11 nhanh, checkpoint E11
Consumer A: ghi checkpoint E10 sau đó
```

Checkpoint đã **lùi** từ E11 về E10. Trên restart có thể replay những event không dự kiến; nếu side effect không idempotent sẽ gây sai.

Các lựa chọn:

- Một consumer owner cho mỗi stream/partition.
- Lease/leadership kèm fencing token để ngăn owner cũ ghi.
- Serial checkpoint theo thứ tự đọc.
- Chỉ nâng checkpoint sau khi **mọi event trước nó đã hoàn tất**, kể cả khi xử lý song song.

Không so sánh resume token bằng thứ tự chuỗi để quyết định event nào “lớn hơn”.

## 17. Xử lý song song mà vẫn bảo toàn thứ tự theo entity

### 17.1. Vấn đề global order và throughput

Xử lý mọi event tuần tự giữ thứ tự đơn giản nhưng có thể chậm nếu downstream tốn nhiều thời gian. Chạy 20 worker song song có thể tăng throughput nhưng làm mất **completion order**.

### 17.2. Partition theo business key

Một thiết kế:

```text
               Change Stream Cursor
                        |
               Dispatcher theo orderId
                        |
           +------------+------------+
           |            |            |
        Partition 0   Partition 1  Partition 2
          (FIFO)        (FIFO)       (FIFO)
           |            |            |
         Worker       Worker       Worker
```

Quy tắc:

- Các event của **cùng orderId** đi tới **cùng partition**.
- Mỗi partition xử lý tuần tự theo thứ tự nhận.
- Các orderId khác nhau có thể xử lý song song.

Ví dụ:

```text
E1 order=A -> partition 0
E2 order=B -> partition 1
E3 order=A -> partition 0

Partition 0: E1 -> E3 theo thứ tự.
Partition 1: E2 chạy độc lập.
```

### 17.3. Bẫy checkpoint khi các partition xử lý khác tốc độ

Giả sử stream đọc:

```text
E1(A), E2(B), E3(A), E4(C)
```

Partition xử lý E4 xong nhưng E2 vẫn chậm. **Không được checkpoint E4 như thể toàn bộ E1..E4 đều đã áp dụng**, vì nếu crash, E2 có thể bị bỏ qua.

Một **checkpoint coordinator** cần theo dõi các event đã hoàn tất và chỉ công bố **prefix liên tục**:

```text
Done: E1=yes, E2=no, E3=yes, E4=yes
Checkpoint an toàn: E1

Khi E2 hoàn tất:
Done: E1=yes, E2=yes, E3=yes, E4=yes
Checkpoint an toàn: E4
```

Đây là lý do parallel event processing không chỉ là đổi một vòng `while` thành `parallelStream()`.

### 17.4. Chuyển quyền ownership partition

Khi scale consumer group từ ba lên bốn worker, một entity có thể chuyển partition. Nếu worker cũ còn đang xử lý và worker mới bắt đầu áp dụng event tiếp theo, thứ tự có thể bị phá.

Cần **drain/stop old owner**, fencing hoặc cơ chế bàn giao thứ tự/offset trước khi giao cùng key sang owner mới.

## 18. Dùng version của entity để chống event cũ ghi đè event mới

### 18.1. Thêm `version` vào document nghiệp vụ

Một document có thể chứa:

```javascript
{
  _id: "O-1001",
  status: "PAID",
  version: 3
}
```

Mỗi thay đổi nghiệp vụ tăng `version` theo một quy tắc atomic phù hợp.

Projection cũng lưu version đã áp dụng:

```javascript
{
  _id: "O-1001",
  status: "PAID",
  sourceVersion: 3
}
```

### 18.2. Chỉ áp dụng version mới hơn

Pseudocode:

```text
if event.sourceVersion > projection.sourceVersion:
    write new state
else:
    skip stale/duplicate event
```

Điều kiện này phải được thực thi **atomic tại nơi ghi** nếu có nhiều worker; không chỉ đọc rồi so sánh trong RAM.

### 18.3. Version giúp giải quyết điều gì?

- Event version 4 hoàn tất trước version 3 -> version 3 không ghi lùi.
- Event version 4 bị replay -> đã có version 4, bỏ qua.
- Consumer restart và nhận event cũ -> nhận diện stale event.

Nhưng version **không tự cho biết** có event version 2 bị bỏ qua hay không nếu chỉ thấy version 1 rồi version 3. Nếu nghiệp vụ cần xử lý **từng bước** (ví dụ gửi hóa đơn cho mỗi lần thanh toán), phải kiểm tra khoảng trống sequence hoặc xử lý bằng event ID riêng.

### 18.4. Change Stream không tự tạo business version

Resume token và `clusterTime` không nên được tự biến thành số phiên bản entity chỉ bằng phép so sánh chuỗi.

Nếu hệ thống cần entity version, nguồn phải định nghĩa rõ và cập nhật nó theo cùng quy tắc nghiệp vụ với dữ liệu gốc.

## 19. `resumeAfter`, `startAfter` và `startAtOperationTime`

### 19.1. `resumeAfter`

Mở stream **sau token** của một event/vị trí hợp lệ:

```javascript
const stream = labDb.orders277.watch(
  [],
  { resumeAfter: checkpoint.resumeToken }
);
```

Đây là lựa chọn tự nhiên khi consumer đã checkpoint một event hoàn tất và muốn tiếp tục.

### 19.2. `startAfter`

`startAfter` cũng bắt đầu sau token, nhưng có ý nghĩa đặc biệt: **có thể dùng để mở stream mới sau một sự kiện `invalidate`** trong những điều kiện MongoDB hỗ trợ.

```javascript
const stream = labDb.orders277.watch(
  [],
  { startAfter: invalidateResumeToken }
);
```

Không được dùng `resumeAfter` để tiếp tục **sau invalidate event** như một trường hợp thường; khi cần tiếp tục sau invalidate, xem `startAfter` và ranh giới namespace/scope của stream.

### 19.3. `startAtOperationTime`

Cho phép bắt đầu theo một mốc operation time khi deployment hỗ trợ:

```javascript
const stream = labDb.orders277.watch(
  [],
  {
    startAtOperationTime: savedOperationTime
  }
);
```

Điều kiện:

- `savedOperationTime` phải là Timestamp đúng loại, không phải JavaScript Date tùy ý.
- Lịch sử oplog cần thiết vẫn phải còn.
- Đây **không thay thế token** khi cần checkpoint chính xác từng event, vì nhiều event có thể chung thời điểm logic.

### 19.4. Không trộn các tùy chọn vị trí tùy tiện

Các tùy chọn như `resumeAfter`, `startAfter` và `startAtOperationTime` là những cách **chỉ định vị trí bắt đầu khác nhau**. Không đồng thời đưa nhiều cách mâu thuẫn trong một lệnh rồi kỳ vọng MongoDB tự chọn “cách tốt nhất”.

### 19.5. Lưu token sau các sự kiện lọc

Giả sử pipeline stream chỉ giữ `operationType: "update"`. Những event `insert`/`delete` có thể không đi tới ứng dụng. Nếu consumer chỉ lưu token của event update gần nhất, checkpoint có thể không phản ánh những khoảng thời gian không có event khớp.

Một số driver/cursor có thể cung cấp **post-batch resume token** để biểu thị tiến độ ngay cả khi batch không có event phù hợp. Khi ứng dụng dùng loại token này:

- Phải hiểu API/driver version.
- Chỉ checkpoint sau khi **mọi event đã được giao trước vị trí đó và cần xử lý** đã hoàn tất.
- Không “nhảy” token lên vị trí sau khi nhiều event vẫn đang chạy song song.

Không tự tạo post-batch token từ `Date.now()`.

## 20. Khi nào resume không còn khả thi?

### 20.1. Oplog history đã bị cuốn

Nếu consumer lưu token E100 rồi offline quá lâu, MongoDB có thể không còn lịch sử cần thiết để tiếp tục từ E100. Khi resume, server/driver có thể báo lỗi liên quan **change stream history lost** hoặc một lỗi không resumable.

```text
Oplog giữ: E800 ... E999

Checkpoint consumer: E100

resumeAfter(E100)
    |
    X Lịch sử cần thiết đã không còn.
```

**Không giải quyết bằng retry vô hạn cùng token.** Nếu lịch sử đã mất, cần chiến lược khôi phục trạng thái như **rebuild projection, chụp snapshot mới hoặc đối soát**.

### 20.2. Invalidation

Một số thay đổi cấu trúc namespace, như drop/rename collection, có thể tạo `invalidate` và đóng stream phạm vi collection. Lúc đó không thể giả định cursor cũ sẽ tiếp tục nhận sự kiện mãi mãi.

Ứng dụng phải quyết định:

- Có nên theo dõi collection mới/recreated không?
- Có cần rebuild projection không?
- Có cần mở stream sau invalidate bằng cơ chế thích hợp không?
- Có thay đổi schema hoặc namespace cần migration consumer không?

### 20.3. Thay pipeline/phạm vi watch

Một token đã lưu với stream theo dõi một collection không tự cho phép tùy ý dùng cho mọi stream theo dõi database/cluster, hay mọi pipeline đã đổi hoàn toàn.

Khi nâng version consumer:

- Ghi lại **stream scope/pipeline version**.
- Kiểm tra resume token tương thích.
- Xác định các loại event mới có cần xử lý lại hay không.
- Có kế hoạch rebuild/backfill nếu semantics đã thay đổi.

### 20.4. Lỗi không resumable

Driver có thể tự resume **một số lỗi tạm thời** theo đặc tả. Nhưng không phải mọi exception đều có thể resume, và một driver không có trách nhiệm retry mãi mãi thay cho ứng dụng.

Nên có nhánh xử lý:

```text
RESUMABLE_ERROR   -> retry/resume theo driver + backoff
NON_RESUMABLE     -> dừng pipeline, cảnh báo, điều tra
HISTORY_LOST      -> bắt đầu quy trình rebuild/reconciliation
SCHEMA_ERROR      -> sửa consumer hoặc dữ liệu, không skip im lặng
```

Không dùng `try/catch` rồi bỏ qua sự kiện lỗi để bảo đảm chương trình “không chết”.

## 21. Snapshot ban đầu và Change Stream: vấn đề “đọc xong mới watch”

### 21.1. Change Stream không cung cấp toàn bộ trạng thái ban đầu

Nếu collection đã có một triệu đơn hàng trước khi consumer được bật, lệnh:

```javascript
db.orders.watch();
```

không tự phát một triệu event `insert` cho những document đã tồn tại từ lâu.

Vì vậy, xây **projection mới** thường cần:

1. Lấy snapshot/trạng thái ban đầu.
2. Bắt đầu theo dõi những thay đổi phát sinh trong lúc snapshot.
3. Áp dụng những thay đổi cần thiết mà không mất hoặc nhân đôi dữ liệu.

### 21.2. Anti-pattern: scan rồi mới bắt đầu watch

```text
T0: Quét toàn collection orders để tạo cache.
T1: Trong lúc quét, O-1001 được update PAID.
T2: Quét kết thúc.
T3: Bắt đầu watch() từ thời điểm hiện tại.
```

Nếu thay đổi tại T1 không có trong snapshot đã xử lý và xảy ra **trước vị trí bắt đầu watch**, cache có thể bỏ mất nó.

### 21.3. Thiết kế bootstrap có điểm bắt đầu rõ

Một quy trình tổng quát:

```text
Chọn điểm bắt đầu có thể resume / marker đủ tin cậy
                |
                v
Mở hoặc ghi nhận vị trí Change Stream
                |
                v
Chụp snapshot nguồn theo chính sách nhất quán phù hợp
                |
                v
Áp dụng snapshot vào projection
                |
                v
Replay những thay đổi kể từ điểm bắt đầu
                |
                v
Chuyển sang tiêu thụ live + checkpoint
```

Việc chọn điểm bắt đầu và thứ tự áp dụng phải bảo vệ các race condition; không chỉ “mở stream trước rồi cứ thế ghi cache” là tự an toàn.

### 21.4. Chống snapshot cũ ghi đè event mới

Nếu đang bootstrap và event mới đã được áp dụng, sau đó bản snapshot cũ của cùng entity mới tới, projection có thể bị ghi lùi.

Các phương án:

- Xử lý snapshot xong mới phát các event đã buffer, trong phạm vi lịch sử còn giữ được.
- Gắn source version và áp dụng có điều kiện.
- Dùng quy trình snapshot consistency và high-watermark đã thiết kế rõ.

Snapshot và event replay phải được **điều phối như một quá trình nhất quán**, không phải hai luồng ghi độc lập tùy ý.

## 22. Xử lý delete, replace và các loại event khác

### 22.1. `insert`

Event thường có `fullDocument` của document mới. Consumer có thể tạo projection tương ứng:

```javascript
{
  operationType: "insert",
  documentKey: { _id: "O-1001" },
  fullDocument: {
    _id: "O-1001",
    status: "CREATED"
  }
}
```

### 22.2. `update`

Thường có `updateDescription`; tùy thiết kế, consumer:

- Áp patch lên projection hiện tại, nếu quy tắc và thứ tự được bảo đảm.
- Hoặc làm mới trạng thái từ nguồn sau event.
- Hoặc dùng post-image khi được hỗ trợ và đã bật.

Không áp patch sai vào document đã bị delete/recreate với cùng ID mà không có version hoặc xử lý vòng đời.

### 22.3. `replace`

Một replace event có ngữ nghĩa thay cả document ở nguồn; consumer không nên chỉ gộp các trường mới vào projection nếu những trường cũ cần bị xóa.

```text
Trước: { status:"PAID", note:"old" }
Replace: { status:"SHIPPED" }

Projection đúng theo replace không được vô tình giữ note:"old"
 nếu note đã không còn trong dữ liệu nguồn.
```

### 22.4. `delete`

Event delete thường có `documentKey` nhưng không mặc định mang full document đã bị xóa.

Nếu consumer chỉ quan tâm `insert` và `update`, cache có thể giữ **document đã bị xóa** mãi mãi. Có thể:

- Xóa projection theo document key.
- Viết tombstone nếu hệ thống cần lịch sử hoặc bảo vệ không bị event cũ ghi tái xuất.
- Dùng pre-image nếu nghiệp vụ cần biết dữ liệu trước delete và đã cấu hình phù hợp.

### 22.5. DDL/invalidate

Thay đổi như rename/drop collection hoặc event liên quan cấu trúc có thể ảnh hưởng stream và cần được xử lý riêng. Một consumer không nên bỏ qua mọi `operationType` chưa biết rồi tiếp tục checkpoint khi kết quả là schema projection có thể bị sai.

## 23. Java Sync Driver: đọc Change Stream và lấy token

### 23.1. Ví dụ consumer đơn giản

Đoạn Java dưới đây minh họa một consumer **đọc tuần tự**, in sự kiện và lưu resume token **sau xử lý** qua một hàm do ứng dụng triển khai. Nó không tự cung cấp exactly-once.

```java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.BsonDocument;
import org.bson.Document;

public class OrdersChangeStreamConsumer {

    public static void main(String[] args) {
        // Thay bằng seed list, replicaSet, TLS/auth thật của deployment.
        String uri = "mongodb://localhost:27017/?replicaSet=rsLab";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                .getDatabase("change_stream_lab277")
                .getCollection("orders277");

            BsonDocument checkpoint = loadCheckpoint();

            ChangeStreamIterable<Document> stream = orders.watch()
                .fullDocument(FullDocument.UPDATE_LOOKUP);

            if (checkpoint != null) {
                stream = stream.resumeAfter(checkpoint);
            }

            try (MongoCursor<ChangeStreamDocument<Document>> cursor =
                     stream.iterator()) {

                while (cursor.hasNext()) {
                    ChangeStreamDocument<Document> change = cursor.next();

                    // Xử lý có thể bị gọi lại khi crash/replay.
                    // Handler phải có cơ chế idempotency/ordering phù hợp.
                    processEvent(change);

                    BsonDocument token = change.getResumeToken();
                    saveCheckpoint(token);
                }
            }
        }
    }

    private static BsonDocument loadCheckpoint() {
        // Ví dụ: đọc trường resumeToken BSON từ collection checkpoint.
        // Trả null nếu consumer chưa có checkpoint.
        return null;
    }

    private static void saveCheckpoint(BsonDocument token) {
        // Triển khai persistence thật với độ bền phù hợp.
        // Ví dụ minh họa không ghi file/checkpoint.
    }

    private static void processEvent(
            ChangeStreamDocument<Document> change) {
        System.out.println(
            change.getOperationType() + " " +
            change.getDocumentKey());
    }
}
```

### 23.2. Đọc ý nghĩa của đoạn mã

- `orders.watch()` mở stream trên collection.
- `fullDocument(FullDocument.UPDATE_LOOKUP)` yêu cầu lookup document khi thích hợp; không bảo đảm exact post-image của event update.
- `resumeAfter(checkpoint)` chỉ được gọi nếu có token được lưu trước đó.
- `change.getResumeToken()` cho token để checkpoint.
- `processEvent()` phải hoàn tất trước `saveCheckpoint()` nếu chọn hướng at-least-once.

**Hạn chế có chủ đích:** hai helper persistence ở trên chỉ là chỗ nối cần tự triển khai. Không được copy ví dụ rồi coi checkpoint đã được lưu hoặc hoàn tất theo production policy.

### 23.3. Khi nào nên dùng `tryNext()`?

Trong một số driver, API cursor có thể hỗ trợ phương thức lấy event không chờ vô hạn như `tryNext()`. Điều này giúp consumer kiểm tra tín hiệu shutdown hoặc thực hiện công việc định kỳ.

Nhưng một vòng polling quá nhanh có thể làm tốn CPU/network. Cần dùng tham số thời gian chờ, backoff và driver API đúng version thay vì tự viết `while(true)` tight-loop.

### 23.4. Exception và resume của driver

Driver có thể tự xử lý **một số lỗi resumable**. Ứng dụng vẫn phải:

- Giữ checkpoint durable.
- Giám sát lỗi không resumable/history lost.
- Có backoff/deadline hoặc chính sách restart.
- Không bắt tất cả exception rồi tự tạo stream từ “now”, vì có thể mất sự kiện.
- Không được checkpoint token sau khi `processEvent()` ném lỗi và chưa hoàn tất.

## 24. Ví dụ checkpoint trong MongoDB

### 24.1. Collection checkpoint riêng

Trong database lab:

```javascript
const labDb = db.getSiblingDB("change_stream_lab277");
const checkpoints = labDb.consumerCheckpoints277;
```

Schema:

```javascript
{
  _id: "orders-projection-v1",
  namespace: "change_stream_lab277.orders277",
  resumeToken: /* BSON token returned by a real change event */,
  savedAt: ISODate("2026-11-14T04:00:00Z")
}
```

Phần trên là **biểu diễn ý tưởng**; không copy nguyên cú pháp chú thích vào thao tác `insertOne` rồi mong nó tạo một token hợp lệ.

### 24.2. Ghi checkpoint sau event

Trong hàm xử lý event:

```javascript
function saveTokenAfterSuccess(change) {
  checkpoints.updateOne(
    { _id: "orders-projection-v1" },
    {
      $set: {
        namespace: "change_stream_lab277.orders277",
        resumeToken: change._id,
        savedAt: new Date()
      }
    },
    { upsert: true }
  );
}
```

Chỉ gọi hàm này **sau khi** side effect tương ứng đã thành công và đã nhận xác nhận phù hợp.

### 24.3. Đọc checkpoint khi restart

```javascript
const stored = checkpoints.findOne({
  _id: "orders-projection-v1"
});

const options = {};
if (stored && stored.resumeToken) {
  options.resumeAfter = stored.resumeToken;
}

const cursor = labDb.orders277.watch([], options);
```

Ở production, cần thêm version cấu hình stream, ownership/fencing và xử lý history lost. Đừng chỉ dùng logic trên khi có nhiều consumer cạnh tranh cùng ghi checkpoint.

### 24.4. Một checkpoint collection không tự tạo atomicity

Đoạn:

```text
processEvent()
saveCheckpoint()
```

là **hai thao tác riêng** trừ khi ứng dụng chủ động đưa chúng vào cùng ranh giới transaction phù hợp. Khi process crash giữa hai lệnh, duplicate vẫn có thể xảy ra.

Đây không phải lỗi của MongoDB, mà là giới hạn của một workflow nhiều thao tác không có atomicity chung.

## 25. Ghi ra Kafka, email hoặc HTTP: bảo đảm dừng ở ranh giới hệ thống

### 25.1. Change Stream -> Kafka

Một bridge:

```text
MongoDB Change Stream
          |
          v
      Producer
          |
          v
    Kafka topic
          |
          v
  Kafka consumer
          |
          v
  Database đích / email
```

Có nhiều checkpoint/ack khác nhau:

1. Change Stream resume token.
2. Producer acknowledgment từ Kafka.
3. Kafka offset của consumer.
4. Side effect ở database/email/HTTP.

Lưu token trước khi producer được xác nhận có thể **mất message**. Lưu token sau khi producer thành công có thể **publish lặp** nếu bridge crash trước checkpoint.

Kafka có những tính năng transaction/idempotent producer riêng, nhưng **không tự biến một transaction MongoDB và Kafka thành một atomic transaction phân tán duy nhất**.

### 25.2. Change Stream -> email

```text
E1: OrderPaid
  -> gửi email thành công
  -> crash trước checkpoint
  -> replay E1
  -> gửi email lần hai?
```

Email service thường không có transaction chung với MongoDB. Cần:

- Một `notificationId`/`eventId` ổn định.
- Bảng trạng thái gửi hoặc outbox/inbox.
- Khả năng dedupe tại dịch vụ gửi nếu hỗ trợ.
- Cơ chế đối soát trạng thái không rõ.

Không hứa “email chỉ gửi một lần” chỉ vì Change Stream event có resume token.

### 25.3. Change Stream -> payment gateway

Với tiền, không nên trực tiếp gọi:

```text
on event OrderPaid:
    chargeCard()
```

mà thiếu idempotency key. Nếu event replay, có thể thu tiền hai lần. Payment API thường cần **mã giao dịch nghiệp vụ duy nhất** và quy trình xác minh trạng thái từ cổng thanh toán trước khi phát request mới.

### 25.4. Transactional outbox là một hướng thiết kế

Nếu ứng dụng ghi order cùng outbox record trong **một MongoDB transaction**:

```text
MongoDB transaction:
  update order.status = PAID
  insert outbox { eventId: "PAY-1001", type:"OrderPaid" }
  commit

Change Stream theo dõi outbox
  -> publisher đưa event đi
  -> consumer downstream dedupe theo eventId
```

Outbox giúp không mất thông điệp do tách rời bước ghi business state và tạo event. Tuy nhiên, publisher có thể gửi một outbox record nhiều lần; consumer đích vẫn cần idempotency.

## 26. Backpressure: consumer chậm hơn tốc độ thay đổi

### 26.1. Câu chuyện độ trễ

Nguồn tạo 5.000 thay đổi/giây nhưng consumer xử lý chỉ 1.000 event/giây.

```text
MongoDB tạo:      5000 events/s
Consumer xử lý:   1000 events/s
Chênh lệch:       4000 events/s
```

Consumer sẽ ngày càng tụt lại. Change Streams không phải hệ thống hàng đợi bảo đảm lưu không giới hạn; nếu backlog vượt **cửa sổ lịch sử oplog**, resume sau sự cố có thể không còn khả thi.

### 26.2. Những metric nên theo dõi

- **Lag** giữa tiến độ source và checkpoint consumer, đo theo phương pháp phù hợp.
- **Event processing rate** và p95/p99 thời gian handler.
- **Số event đang xử lý** trong queue/in-flight.
- **Tuổi checkpoint** và thời điểm gần nhất commit checkpoint.
- **Oplog window** của source.
- **Resume errors**, non-resumable errors, invalidation.
- Số event retry/dedupe và dead-letter.
- Lỗi downstream, latency network, saturation của connection pool.

Không đo lag bằng cách lấy `Date.now() - clusterTime` rồi coi đó là con số tuyệt đối trong mọi tình huống: `clusterTime` là logical timestamp và lưu lượng có thể gián đoạn.

### 26.3. Cách ứng phó

- Tối ưu handler và index tại database đích.
- Batch có kiểm soát nếu semantics cho phép.
- Phân vùng theo key và xử lý song song **nhưng giữ checkpoint prefix an toàn**.
- Tăng capacity downstream.
- Giảm dữ liệu không cần thiết trong `fullDocument`/pipeline theo yêu cầu.
- Tối ưu log/outbox nếu sự kiện quá dày.
- Chuẩn bị cơ chế rebuild khi vượt lịch sử.

Không tăng concurrency tới mức phá vỡ thứ tự cùng entity hoặc khiến checkpoint bỏ qua event đang in-flight.

## 27. Một số thay đổi không nên “bỏ qua và checkpoint”

### 27.1. Event không hiểu schema

Giả sử consumer chỉ biết trạng thái `PAID` và `SHIPPED`, nhưng nguồn bắt đầu phát:

```javascript
{ status: "PARTIALLY_REFUNDED" }
```

Nếu code chỉ bỏ qua event lạ rồi checkpoint, projection có thể **mãi sai**.

Nên:

- Log có mã event/correlation ID.
- Phân loại lỗi schema.
- Dừng/đưa vào hàng xử lý lại theo yêu cầu.
- Không tự ý ghi checkpoint vượt một event **bắt buộc** mà chưa xử lý được.

### 27.2. Event delete không có fullDocument

Nếu handler yêu cầu `fullDocument._id` cho mọi operation và delete event không có fullDocument, code có thể ném lỗi.

Nên dùng `documentKey` để xác định entity với delete và xử lý riêng theo `operationType`.

### 27.3. Poison event

Một event làm handler lỗi liên tục:

```text
E9 thành công
E10 lỗi schema, lần nào cũng thất bại
E11, E12 chưa xử lý
```

Nếu cứ resume sau E9 và retry E10 vô hạn, consumer bị kẹt. Nhưng nếu bỏ qua E10 và checkpoint E12, có thể mất thông tin quan trọng.

Phải có **chính sách dead-letter/manual review/reconciliation** dựa trên độ quan trọng của event, với bằng chứng và khả năng replay. Không có giải pháp “luôn skip” đúng cho mọi workflow.

## 28. Khi nhiều service dùng cùng stream

### 28.1. Mỗi consumer có mục tiêu riêng

Ví dụ:

```text
orders Change Stream
   |
   +--> SearchIndexer
   +--> AnalyticsProjection
   +--> NotificationService
```

Mỗi service có:

- Bộ lọc event khác.
- Tốc độ xử lý khác.
- Side effect khác.
- Checkpoint riêng.
- Khả năng rebuild riêng.

Không nên cho cả ba service dùng chung một document checkpoint `"orders-latest"`. Nếu Analytics nhanh hơn SearchIndexer và cập nhật token chung, SearchIndexer có thể **bỏ mất sự kiện**.

### 28.2. Consumer group và ownership

Nếu có nhiều instance của **cùng một consumer logic**, phải quyết định:

- Chỉ một instance là leader đọc stream, những instance khác standby.
- Hay có dispatcher phân phối sự kiện đến các worker với partition/ordering.

Mở ba stream giống nhau trên ba instance **không tự tạo load balancing**; cả ba có thể nhận cùng sự kiện và thực hiện side effect ba lần.

### 28.3. Fencing owner cũ

Một instance có thể mất lease nhưng vẫn đang chạy handler cũ. Nếu instance mới bắt đầu đồng thời, hai owner có thể ghi lẫn nhau.

Một cơ chế leadership an toàn cần có **fencing token/epoch** hoặc điều kiện ghi để owner cũ không được tiếp tục checkpoint hay sửa projection sau khi quyền sở hữu đã chuyển.

## 29. Sự kiện mất thực sự thì khôi phục thế nào?

### 29.1. Không giả lập token mới để “vượt lỗi”

Khi nhận history lost, đây là ý tưởng sai:

```text
resumeAfter(oldToken) -> error
watch() từ now -> tiếp tục, không thông báo
```

Giữa oldToken và “now” có thể có **rất nhiều thay đổi bị bỏ qua**. Projection mới chạy tiếp có thể duy trì trạng thái sai vô thời hạn.

### 29.2. Rebuild projection

Nếu projection hoàn toàn có thể tính lại từ MongoDB source hiện tại:

1. Ghi nhận consumer bị mất history và dừng công bố trạng thái không đáng tin.
2. Tạo projection staging mới.
3. Bootstrap snapshot với điểm bắt đầu Change Stream được điều phối đúng.
4. Replay changes phát sinh trong lúc snapshot.
5. Đối chiếu số lượng, checksum/trường quan trọng.
6. Công bố projection mới khi đủ điều kiện.
7. Lưu checkpoint mới theo scope/pipeline version phù hợp.

### 29.3. Khi rebuild từ trạng thái hiện tại không đủ

Một số sự kiện có ý nghĩa **không thể suy lại chỉ từ trạng thái cuối**, ví dụ:

- Mỗi lần thanh toán thành công phải phát một event độc lập.
- Một đơn hàng chuyển trạng thái nhiều lần cần audit đầy đủ.
- Mỗi email đã gửi cần có lịch sử.

Nếu nguồn chỉ giữ trạng thái cuối và change stream history đã mất, **không thể tự tạo lại đầy đủ các event lịch sử** từ một snapshot hiện tại.

Những nghiệp vụ đó cần **outbox/event log/ledger có retention riêng**, backup hoặc nguồn lịch sử có thể phục hồi. Change Stream là công cụ phân phối thay đổi, không phải một event store thay thế tất cả.

## 30. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| Change Stream luôn giao event đúng một lần | Replay có thể xảy ra sau restart hoặc lỗi kết nối/checkpoint |
| Đọc từ cursor theo thứ tự nghĩa handler song song cũng hoàn tất theo thứ tự | Worker có thể reorder completion |
| `clusterTime` là ID event duy nhất | Nhiều event, nhất là trong transaction, có thể cùng clusterTime |
| `documentKey._id` dùng để dedupe mọi thay đổi | Một document có nhiều event hợp lệ |
| Resume token là String có thể sắp xếp | Token là BSON opaque, không so sánh tùy ý |
| MongoDB tự biết email đã được gửi | Side effect ngoài DB do ứng dụng quản lý |
| Checkpoint trước giúp tránh cả duplicate lẫn mất event | Có cửa sổ crash làm mất xử lý |
| Checkpoint sau bảo đảm không có duplicate | Có cửa sổ crash làm replay |
| `$inc` lặp lại là vô hại | Có thể tăng bộ đếm hai lần |
| `$set` idempotent nghĩa không cần bảo vệ thứ tự | Event cũ có thể ghi đè event mới |
| `updateLookup` là post-image chính xác của từng event | Có thể trả trạng thái mới hơn hoặc null |
| Mỗi transaction MongoDB chỉ tạo một event | Transaction có thể tạo nhiều change events |
| Source transaction atomic thì cache ngoài cũng atomic | Consumer có thể áp dụng từng event khác thời điểm |
| Driver retry mọi lỗi mãi mãi | Chỉ một số lỗi resumable và còn giới hạn |
| Oplog lưu vô hạn | Resume bị giới hạn bởi lịch sử giữ lại |
| `resumeAfter` có thể dùng sau mọi invalidate | `startAfter` có vai trò đặc biệt sau invalidate |
| Dùng Date.now() là checkpoint đầy đủ | Có thể bỏ/nhân đôi event; không thay token |
| Khi history lost, mở stream từ now là đủ | Có thể bỏ mất một khoảng thay đổi không thể phục hồi |
| Nhiều instance watch cùng collection tự chia tải | Mỗi instance có thể nhận tất cả event |
| Cứ checkpoint token mới nhất đã đọc là an toàn | Event cũ hơn có thể chưa hoàn tất xử lý |
| Balancer di chuyển document sẽ tạo insert business event cho mỗi bản copy | Migration là thao tác metadata/phân bố, không mặc định là insert nghiệp vụ |
| Dedupe được một event nghĩa đã xử lý đúng mọi side effect | Cần atomicity và kiểm tra trạng thái downstream |
| Change Streams thay thế hệ thống audit lâu dài | Oplog retention có giới hạn; cần log riêng khi nghiệp vụ yêu cầu |
| Exactly-once MongoDB effect tự mở rộng sang Kafka và payment | Mỗi hệ thống có transaction/ack/idempotency riêng |

## 31. Bài tập thực hành

### Bài 1 — Nhận diện các trường event

Cho:

```javascript
{
  _id: { _data: "opaque" },
  operationType: "update",
  clusterTime: Timestamp(1720000000, 2),
  documentKey: { _id: "O-001" },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

Hãy trả lời:

1. Trường nào là **resume token**?
2. Trường nào định danh **đơn hàng**?
3. Trường nào mô tả loại thao tác?
4. Có thể dùng `clusterTime` làm ID duy nhất không?
5. Vì sao không nên tự parse chuỗi `_data`?

### Bài 2 — Thứ tự đọc và thứ tự hoàn tất

Cursor trả:

```text
E1: O-001 status=PAID
E2: O-001 status=SHIPPED
```

Worker A xử lý E1 mất 900 ms, Worker B xử lý E2 mất 100 ms.

- Nếu cả hai dùng `$set` status lên cùng projection, kết quả cuối có thể là gì?
- Vì sao đây không nhất thiết là lỗi ordering của MongoDB?
- Đề xuất hai cách giữ đúng trạng thái: xử lý tuần tự theo key hoặc dùng version có điều kiện.

### Bài 3 — Checkpoint trước và crash

Timeline:

```text
T1: receive E10
T2: save checkpoint E10
T3: crash
T4: restart resumeAfter E10
```

E10 đã được cập nhật vào projection chưa? Nó có thể được giao lại theo cách resume này không? Chiến lược trên có rủi ro at-most-once nào?

### Bài 4 — Checkpoint sau và crash

Timeline:

```text
T1: receive E10
T2: $inc dailyMetrics by 1
T3: crash before saving checkpoint E10
T4: restart resumeAfter E9
T5: receive E10 again
```

Hãy giải thích:

- Counter có thể tăng mấy lần?
- Tại sao đây là dạng replay dự kiến của at-least-once?
- Có thể dùng unique event ID + transaction như thế nào để tránh nhân đôi tác động?

### Bài 5 — Dedupe sai bằng `documentKey`

Một đơn O-001 có ba sự kiện:

```text
E1: CREATED
E2: PAID
E3: SHIPPED
```

Consumer lưu `processedOrders = { "O-001" }` sau E1 và bỏ tất cả event cùng order ID.

Đây là lỗi gì? Hãy phân biệt **entity identity** với **event identity** và đề xuất khóa dedupe phù hợp.

### Bài 6 — Hai event cùng `clusterTime`

Transaction TX cập nhật tài khoản A và B, rồi chèn một ledger record. Cả ba change events có thể cùng `clusterTime`.

Tại sao checkpoint chỉ lưu timestamp logic không đủ cho tiến độ từng event? Resume token giúp gì? Vì sao transaction source atomic không đảm bảo cache ở hai worker được cập nhật đồng thời?

### Bài 7 — `updateLookup` và trạng thái mới hơn

```text
10:00 E1: O-001 status=PAID
10:01 E2: O-001 status=SHIPPED
10:02 Consumer gọi updateLookup cho E1
```

`fullDocument` của E1 có thể phản ánh trạng thái nào? Nếu cần post-image chính xác ngay sau E1, cần xem tính năng nào của MongoDB? Vì sao không nên dùng `updateLookup` làm audit đầy đủ?

### Bài 8 — `resumeAfter` và `startAfter`

1. Khi consumer có token của event update cuối cùng đã xử lý, nên dùng option nào?
2. Sau một `invalidate` vì collection bị drop/rename, option nào có thể dùng để bắt đầu một stream mới theo điều kiện hỗ trợ?
3. Vì sao một token đã hết lịch sử oplog không tự có thể được resume?
4. `startAtOperationTime` khác một token từng event ở điểm nào?

### Bài 9 — Parallel workers và checkpoint prefix

Cursor đọc:

```text
E1(A), E2(B), E3(A), E4(C), E5(D)
```

Trạng thái:

```text
E1 done
E2 in-flight
E3 done
E4 done
E5 done
```

Checkpoint an toàn nhất thuộc event nào nếu muốn không bỏ mất event đang xử lý? Sau khi E2 hoàn tất, checkpoint có thể tiến tới đâu? Hãy giải thích cơ chế coordinator.

### Bài 10 — Hai consumer độc lập

SearchIndexer và NotificationService cùng theo dõi `orders`:

- SearchIndexer đã xử lý đến E100.
- NotificationService mới xử lý đến E60.

Tại sao không nên dùng **một checkpoint chung E100**? Thiết kế tên checkpoint riêng theo consumer/scope như thế nào?

### Bài 11 — Projection và delete

Một consumer chỉ theo dõi `insert`, `update`; sau đó order O-001 bị xóa khỏi collection nguồn.

Projection sẽ gặp vấn đề gì? Hãy bổ sung nhánh `delete` dựa trên `documentKey` và giải thích khi nào nên dùng tombstone thay vì xóa vật lý.

### Bài 12 — History lost sau một tuần offline

Consumer có checkpoint E100. Oplog hiện chỉ còn lịch sử từ E500. Ứng dụng nhận lỗi không thể resume từ E100.

- Vì sao lặp lại `resumeAfter(E100)` không giúp?
- Nếu projection có thể xây từ trạng thái hiện tại, hãy nêu quy trình rebuild.
- Nếu phải phát **mỗi email cho mỗi lần thay đổi** đã mất, snapshot hiện tại có đủ không?
- Nguồn lịch sử nào nên được thiết kế trước?

### Bài 13 — Change Stream -> Kafka

Bridge gửi E10 tới Kafka thành công, nhưng crash trước khi lưu resume token.

- Khi restart có thể gửi E10 lại không?
- Kafka producer idempotency có tự bảo vệ side effect ở database consumer không?
- Cần event ID và checkpoint tại mỗi ranh giới nào?
- Vì sao không nên hứa exactly-once end-to-end chỉ từ một lệnh `watch()`?

### Bài 14 — Triển khai một bộ đếm chính xác

Với event `OrderPaid`, yêu cầu tăng `paidOrders` đúng một lần cho mỗi event nghiệp vụ.

Thiết kế:

1. Một event ID ổn định.
2. Unique index cho inbox processed events.
3. Update counter `$inc`.
4. Checkpoint resume token.
5. Một MongoDB transaction bao gồm các ghi có liên quan.

Hãy phân tích tình huống crash trước commit, sau commit và khi commit trả kết quả không rõ.

### Bài 15 — Version và reordering

Projection hiện:

```javascript
{ _id: "O-001", sourceVersion: 5, status: "SHIPPED" }
```

Worker trễ nhận event:

```javascript
{ orderId: "O-001", sourceVersion: 4, status: "PAID" }
```

Nên áp dụng event này không? Hãy viết điều kiện cập nhật atomic dựa trên version, đồng thời thảo luận trường hợp version nhảy từ 3 lên 5 khi nghiệp vụ phải xử lý mọi event trung gian.

### Bài 16 — Bootstrap không làm mất update

Một hệ thống cần tạo search index từ một collection có một triệu document. Trong lúc scan, nguồn vẫn tiếp tục ghi.

- Vì sao “scan xong rồi watch từ now” có thể bỏ mất sự kiện?
- Cần chốt điểm bắt đầu stream và snapshot như thế nào?
- Nếu snapshot ghi trễ sau một event live, có thể gây lỗi gì?
- Dùng version hoặc replay có điều phối để phòng tránh ra sao?

### Bài 17 — Quan sát consumer lag

Nguồn tạo 8.000 event/s, consumer xử lý 2.000 event/s. Hãy tính chênh lệch backlog theo giây, đồng thời nêu vì sao không nên dùng chênh lệch đó làm cam kết “số event sẽ được giữ mãi”. Những metric nào phải quan sát để biết nguy cơ vượt oplog window?

### Bài 18 — Thiết kế production runbook

Một consumer Change Stream phục vụ cache có các yêu cầu:

- Không bỏ event nếu còn lịch sử cần thiết.
- Duplicate không làm sai projection.
- Event cùng orderId áp dụng theo thứ tự.
- Có ba worker xử lý song song.
- Có cách phục hồi sau history lost.
- Có log và cảnh báo khi consumer bị tụt lại.

Hãy thiết kế sơ đồ dispatcher/partition/checkpoint coordinator, schema checkpoint/inbox, quy tắc retry và quy trình rebuild. Nêu rõ **bảo đảm nào có thể đạt được** và **giới hạn còn lại**.

## 32. Quy trình thực hành có thể áp dụng

Khi chuẩn bị một consumer Change Stream thật, hãy ra quyết định theo thứ tự sau:

1. **Phạm vi nguồn:** collection, database hay deployment? Cần nhận loại event nào?
2. **Contract event:** dùng `operationType`, `documentKey`, `updateDescription`, `fullDocument` hay pre/post-image?
3. **Thứ tự cần bảo vệ:** toàn stream hay riêng mỗi entity? Có thể xử lý song song tới mức nào?
4. **Checkpoint:** lưu token BSON ở đâu, với write concern nào và ai có quyền ghi?
5. **Crash window:** side effect trước hay checkpoint trước? Mất hay lặp được xử lý thế nào?
6. **Idempotency:** có event ID/bussiness ID ổn định và unique constraint phù hợp không?
7. **Atomicity:** có thể gộp effect + dedupe marker + checkpoint trong transaction của cùng MongoDB deployment không?
8. **Downstream:** email/Kafka/payment có cơ chế ack, dedupe và đối soát riêng không?
9. **Retention:** oplog window có đủ cho downtime, backlog và kế hoạch backup/rebuild không?
10. **Schema/version:** khi thay đổi pipeline/scope hoặc event format, resume/backfill được xử lý thế nào?
11. **Observability:** lag, throughput, retries, checkpoint age, history lost và poison events có được theo dõi không?
12. **Runbook:** khi nhận non-resumable error, ứng dụng dừng và phục hồi có kiểm soát hay âm thầm nhảy tới now?

Những quyết định này quan trọng không kém việc `watch()` mở cursor thành công.

## 33. Tổng kết

**MongoDB Change Streams cung cấp một luồng thay đổi có thứ tự trong phạm vi stream và một resume token để tiếp tục đọc**, nhưng **không tự bảo đảm thứ tự hoàn tất** khi ứng dụng đưa event tới nhiều worker hoặc nhiều hệ thống khác nhau. `clusterTime`, `documentKey` và `ObjectId` không thay thế resume token trong việc checkpoint từng sự kiện.

**Xử lý trước rồi checkpoint sau** thường phù hợp khi không muốn cố tình bỏ sự kiện, nhưng có cửa sổ crash gây replay; **checkpoint trước rồi xử lý sau** có cửa sổ crash làm mất side effect. Vì thế, xây hệ thống bền vững thường cần **at-least-once + idempotency**, hoặc atomic effect/checkpoint trong cùng transaction nếu các tác động nằm trong ranh giới được hỗ trợ.

**Exactly-once phải được định nghĩa theo phạm vi.** Một projection trong MongoDB có thể được bảo vệ bằng unique event ID, update có điều kiện và transaction. Nhưng một lời gọi email, Kafka hoặc payment gateway là ranh giới xác nhận khác; Change Streams không tự cung cấp giao dịch phân tán end-to-end.

**Resume có giới hạn:** token phải còn hợp lệ trong lịch sử MongoDB; invalidate, thay đổi namespace, oplog expiration và lỗi không resumable có thể buộc ứng dụng rebuild hoặc đối soát. Khi lịch sử đã mất, mở lại từ hiện tại không phải cách phục hồi dữ liệu đúng nếu những thay đổi bị bỏ qua có ý nghĩa nghiệp vụ.

Muốn một consumer đáng tin cậy, hãy thiết kế đồng thời **ordering, deduplication, checkpoint, retention, recovery và monitoring**. Đó là nền tảng để khai thác Change Streams như một nguồn thay đổi gần thời gian thực mà không nhầm giữa “đã nhận một event” và “đã áp dụng đúng tác động nghiệp vụ của event đó”.

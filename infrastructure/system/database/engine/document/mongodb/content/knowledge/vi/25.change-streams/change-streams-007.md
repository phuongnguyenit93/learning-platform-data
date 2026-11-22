# Lưu resume token bền vững và xử lý khi lịch sử oplog không còn trong MongoDB

Một ứng dụng có thể dùng **Change Stream** của MongoDB để lắng nghe thao tác `insert`, `update`, `replace`, `delete` và những sự kiện thay đổi khác mà không phải liên tục truy vấn lại toàn bộ collection. Ví dụ: sau khi đơn hàng chuyển sang trạng thái `paid`, một dịch vụ có thể cập nhật bảng tìm kiếm, đồng bộ dữ liệu phân tích, làm mới cache hoặc phát một sự kiện đến hệ thống khác.

Nhưng Change Stream là một **luồng dài hạn**, trong khi tiến trình ứng dụng, kết nối mạng và máy chủ đều có thể gặp sự cố. Giả sử consumer đã nhận đến sự kiện thứ 1.000 rồi khởi động lại. Làm sao nó biết phải đọc từ đâu? Và nếu consumer tắt đủ lâu khiến phần lịch sử cần thiết trong **oplog** bị ghi đè, MongoDB có thể tái phát những sự kiện đã mất không?

Bài học thuộc chương **Change stream** của module **Database Engine Document MongoDB**, tập trung vào hai nhiệm vụ liên quan chặt chẽ:

1. **Lưu resume token bền vững** để consumer có thể khởi động lại, tiếp tục từ vị trí đã xử lý và hạn chế việc phát lại không cần thiết.
2. **Phát hiện và xử lý mất lịch sử oplog** khi token không còn có thể dùng để tiếp tục; khi đó phải có chính sách tái đồng bộ (*rebuild/reconciliation*) với điểm chuyển tiếp an toàn, thay vì âm thầm bỏ qua sự kiện.

Một thiết kế tốt còn phải giải quyết câu hỏi khó hơn: **lúc nào được phép lưu checkpoint?** Nếu lưu token quá sớm thì có nguy cơ mất sự kiện; nếu lưu sau khi xử lý thì có thể nhận trùng. Do đó, Change Stream cần được kết hợp với **idempotency**, độ bền của nơi lưu checkpoint, giám sát độ trễ và kế hoạch khôi phục.

## 1. Change Stream lấy sự kiện từ đâu?

Trên replica set, MongoDB ghi các thay đổi dữ liệu vào **oplog** để các secondary sao chép. Change Stream cung cấp một giao diện theo dõi những thay đổi phù hợp, với các sự kiện được MongoDB tạo ra dựa trên lịch sử thay đổi được duy trì trong hệ thống.

Sơ đồ khái niệm:

```text
                 ỨNG DỤNG GHI
                       |
                       v
                 Primary mongod
                       |
              thao tác dữ liệu
                       |
                       v
                  Oplog
                       |
            sự kiện được commit
                       |
                       v
               Change Stream
                       |
                mongos/mongod
                       |
                       v
                 Consumer
                       |
          +------------+------------+
          |                         |
          v                         v
     Xử lý sự kiện            Lưu checkpoint
     (sink/read model)        (resume token)
```

Change Streams được hỗ trợ trong những môi trường MongoDB có cấu hình phù hợp như **replica set** và **sharded cluster**. Một standalone `mongod` không có đầy đủ cơ chế oplog/replication cần thiết cho tính năng này.

Một số điểm cần phân biệt:

- **Oplog** là nhật ký phục vụ replication; nó **không phải hàng đợi sự kiện vĩnh viễn** được thiết kế để lưu mọi sự kiện cho consumer bất kể thời gian.
- **Change Stream** chỉ cung cấp những sự kiện hợp lệ theo phạm vi theo dõi, pipeline lọc và khả năng truy cập lịch sử hiện có.
- **Resume token** là vị trí tiếp tục do MongoDB tạo, không phải một bản sao của toàn bộ sự kiện và không chứa dữ liệu để dựng lại lịch sử đã bị xóa.
- **Consumer checkpoint** là trạng thái ứng dụng tự quản lý; MongoDB driver có thể tự resume trong một số lỗi tạm thời, nhưng điều đó **không đồng nghĩa** token đã được lưu bền vững qua lần triển khai/khởi động lại.

Change Stream thường phản ánh các thay đổi **majority-committed** theo cơ chế của server. Dữ liệu mới chỉ tồn tại ngắn trên một primary nhưng bị rollback trước khi đủ điều kiện commit không nên được ứng dụng coi là một sự kiện thay đổi đã được Change Stream cam kết phát ổn định.

## 2. Ba loại thông tin phải tách rời

Giả sử một đơn hàng có nội dung:

```javascript
{
  _id: "order-1001",
  customerId: "C01",
  status: "paid",
  total: 250
}
```

Khi đơn này được cập nhật, một change event có thể có hình dạng giản lược như:

```javascript
{
  _id: {
    _data: "825...."
  },
  operationType: "update",
  clusterTime: Timestamp(...),
  ns: {
    db: "change_stream_lab",
    coll: "orders"
  },
  documentKey: {
    _id: "order-1001"
  },
  updateDescription: {
    updatedFields: {
      status: "paid"
    },
    removedFields: []
  }
}
```

Đây là **sơ đồ sự kiện**, không phải output có thể chạy nguyên xi: giá trị `_data` thật và `Timestamp` do MongoDB sinh ra.

| Trường | Vai trò | Có nên dùng làm checkpoint? |
| --- | --- | --- |
| **Event `_id`** | **Resume token** do server tạo cho change event | **Có**, lưu nguyên vẹn dưới dạng BSON/document |
| `documentKey._id` | `_id` của document ứng dụng bị thay đổi | **Không**, chỉ xác định document nghiệp vụ |
| `clusterTime` | Thời điểm logic theo cluster của sự kiện | Dùng để chẩn đoán; không phải thay thế mặc định cho resume token |
| `operationType` | Loại thao tác, ví dụ `insert`, `update`, `delete` | Không xác định vị trí riêng lẻ |
| `ns` | Namespace database/collection | Hữu ích cho consumer nghe nhiều namespace |
| `fullDocument` | Ảnh document nếu được cung cấp theo options | Payload dữ liệu; không phải token |

**Điểm dễ sai nhất:** khi nói “lưu `_id` của change event”, ta nói đến `event._id` (resume token), **không phải** `event.documentKey._id`. Document ID có thể được cập nhật nhiều lần; lưu nó không cho biết đã xử lý đến **lần cập nhật nào**.

Resume token là một giá trị **opaque**: ứng dụng phải coi nó là thông tin do MongoDB quản lý, không tự giải mã `_data` để suy ra một thứ tự nghiệp vụ, không thay token bằng timestamp tự sinh, không cắt chuỗi hoặc thay đổi kiểu BSON của các phần tử.

## 3. Resume token dùng để làm gì?

Sau khi consumer đã xử lý một change event và lưu token `T100`:

```text
Các thay đổi trong stream:

    E98 ---- E99 ---- E100 ---- E101 ---- E102 ---- E103
                       |
                       v
                 checkpoint T100
                       |
                    crash
                       |
                  restart
                       |
                       v
               resumeAfter(T100)
                       |
                       v
                    E101 ...
```

Khi còn đủ lịch sử và token vẫn hợp lệ, option **`resumeAfter`** mở Change Stream **tiếp theo sau** vị trí mà token chỉ tới. Vì vậy, consumer không phải replay lại toàn bộ collection kể từ đầu.

Các tình huống sử dụng:

- Tiến trình consumer được triển khai lại.
- Container bị restart sau sự cố.
- Kết nối network bị ngắt, sau đó ứng dụng mở lại stream.
- Consumer bị chuyển từ một instance sang instance khác.
- Bảo trì ứng dụng trong khoảng thời gian **ngắn hơn cửa sổ lịch sử còn dùng để resume**.

Token không bảo đảm mọi trường hợp đều resume thành công. Nó phụ thuộc việc MongoDB **vẫn có đủ lịch sử liên quan** và cấu hình/phạm vi Change Stream tương thích.

## 4. Điều kiện môi trường để dùng Change Stream

Trước khi viết consumer, cần biết:

1. **Deployment:** replica set hoặc sharded cluster hỗ trợ Change Stream; cluster phải được cấu hình và các member đủ điều kiện hoạt động.
2. **Phiên bản:** dùng phiên bản MongoDB và driver hỗ trợ những option định sử dụng như `resumeAfter`, `startAfter`, `startAtOperationTime` hoặc các loại event mới.
3. **Quyền:** tài khoản cần quyền đọc và mở Change Stream trên namespace liên quan.
4. **Phạm vi:** có thể watch **collection**, **database** hoặc **cluster**, với khác biệt về quyền, phạm vi event, `namespace` và hành vi invalidate.
5. **Kích thước lịch sử:** oplog có dung lượng/thời gian lưu hiệu dụng giới hạn; consumer phải theo kịp tốc độ tạo thay đổi.
6. **Pipeline:** các stage tùy chỉnh không được làm mất hoặc sửa resume token `_id`; filter có thể chấp nhận được, nhưng việc biến đổi event phải tuân thủ quy tắc của Change Stream.

### Mở một stream đơn giản bằng `mongosh`

Trong terminal A, kết nối vào replica set hoặc `mongos` của cluster lab:

```javascript
use change_stream_lab

const stream = db.orders.watch();

while (stream.hasNext()) {
  const change = stream.next();
  printjson(change);
}
```

Terminal B, dùng cùng cluster lab, thực hiện:

```javascript
use change_stream_lab

db.orders.insertOne({
  _id: "order-1001",
  customerId: "C01",
  status: "pending",
  total: NumberDecimal("250.00"),
  createdAt: new Date()
});

db.orders.updateOne(
  { _id: "order-1001" },
  { $set: { status: "paid" } }
);
```

Terminal A sẽ nhận các change events tương ứng sau khi server cung cấp chúng. Lệnh `while (stream.hasNext())` **cố ý chạy dài hạn** và có thể chờ khi chưa có sự kiện mới; đây là hoạt động bình thường của một consumer, không phải một lệnh truy vấn ngắn. Trong ứng dụng thật phải có cơ chế dừng, đóng cursor và khởi động lại theo vòng đời service.

Nếu collection chưa tồn tại hoặc quyền/hạ tầng chưa phù hợp, hãy tạo collection lab và đảm bảo môi trường hỗ trợ; không chạy các ví dụ insert trên database chứa dữ liệu sản xuất.

## 5. Resume token xuất hiện ở đâu?

Một change event hợp lệ có token tại trường `_id`:

```javascript
const change = stream.next();
const token = change._id;

printjson(token);
```

Ví dụ trực quan:

```javascript
{
  _data: "82655..."
}
```

Token thật là một **BSON document**, có thể có thêm thành phần tùy phiên bản hoặc loại sự kiện. Không nên lưu riêng `token._data` rồi giả định có thể dựng lại toàn bộ resume token từ một chuỗi đó.

### Giữ nguyên cấu trúc BSON

Nên lưu:

```javascript
{
  _id: "orders-consumer-v1",
  resumeToken: {
    _data: "..."
  },
  updatedAt: ISODate("2026-11-14T00:00:00Z")
}
```

Trường `resumeToken` ở đây là **toàn bộ document token nhận được từ stream**, không phải dữ liệu giả được nhập thủ công. Thời điểm `updatedAt` chỉ phục vụ vận hành và giám sát.

Nếu cần đưa checkpoint ra hệ thống không lưu BSON trực tiếp, hãy dùng **Extended JSON** có hỗ trợ các kiểu BSON phù hợp hoặc format serialization được driver khuyến nghị; không dựa vào `JSON.stringify()` rồi coi việc mất kiểu BSON chắc chắn không quan trọng. Đặc biệt, document token là cấu trúc opaque; code không được tự thêm/bớt field trong đó.

## 6. Lưu token bền vững ở đâu?

Việc chỉ giữ biến `lastToken` trong RAM là **không bền vững**:

```javascript
let lastToken = change._id;
```

Khi process bị kill, biến biến mất. Một lựa chọn là lưu checkpoint trong **collection riêng**:

```text
Database: change_stream_lab

orders
  ├── order-1001
  ├── order-1002
  └── ...

consumerCheckpoints
  └── {
        _id: "orders-sync-v1",
        resumeToken: <opaque BSON document>,
        updatedAt: <Date>,
        streamScope: "change_stream_lab.orders",
        pipelineVersion: 1
      }
```

Ưu điểm của checkpoint collection:

- Ghi được sau mỗi event hoặc mỗi batch đã xử lý.
- Có thể dùng **write concern `majority`** để tăng độ bền trong replica set.
- Có thể đọc lại checkpoint khi consumer restart trên node khác.
- Dễ quan sát worker nào đang chạy, token cuối được lưu lúc nào, phiên bản pipeline và namespace tương ứng.

Không có quy định bắt buộc phải dùng MongoDB làm nơi lưu checkpoint. Một hệ thống có thể dùng cơ sở dữ liệu giao dịch khác hoặc một kho key-value bền vững; điều kiện là **lưu đúng cấu trúc token**, bền trước crash, có điều phối giữa các consumer và có chiến lược commit cùng side effects.

### Thiết kế document checkpoint

Một schema thực tế có thể chứa:

| Field | Vai trò |
| --- | --- |
| `_id` | Tên duy nhất của consumer hoặc partition logic |
| `resumeToken` | Toàn bộ token BSON cuối đã checkpoint |
| `updatedAt` | Thời điểm checkpoint được ghi |
| `streamScope` | Collection/database/cluster mà token thuộc về |
| `pipelineVersion` | Phiên bản pipeline lọc/biến đổi event |
| `consumerVersion` | Phiên bản code có thể ảnh hưởng cách xử lý |
| `lastOperationType` | Chẩn đoán sự kiện cuối, không dùng thay token |
| `lastClusterTime` | Hỗ trợ đo lag nếu được cung cấp |
| `state` | Ví dụ `RUNNING`, `NEEDS_REBUILD`, `RECONCILING` |

**Không dùng TTL index xóa checkpoint dựa trên `updatedAt` một cách vô thức.** Nếu checkpoint bị xóa sau vài ngày, consumer có thể khởi động lại mà không biết vị trí tiếp tục và phải coi đó là tình trạng cần recovery.

### Lưu checkpoint có write concern

Trong `mongosh`:

```javascript
db.consumerCheckpoints.updateOne(
  { _id: "orders-sync-v1" },
  {
    $set: {
      resumeToken: change._id,
      updatedAt: new Date(),
      streamScope: "change_stream_lab.orders",
      pipelineVersion: 1,
      state: "RUNNING"
    }
  },
  {
    upsert: true,
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
```

Đây là một **mẫu lệnh riêng lẻ** khi `change` đang là event đã xử lý thành công. Không chạy nó với một token giả và không chạy khi tác vụ xử lý sự kiện chưa hoàn tất.

Write concern majority làm checkpoint bền hơn trước failover thông thường, nhưng **không đồng nghĩa** có thể xử lý side effect ngoài MongoDB chính xác một lần. Vấn đề đó sẽ được phân tích riêng.

## 7. Quy tắc vàng: xử lý sự kiện trước, checkpoint sau

Giả sử consumer đang xử lý sự kiện E101:

```text
E101 được nhận
      |
      v
Xử lý E101 thành công
      |
      v
Lưu token của E101 bền vững
      |
      v
Tiếp tục E102
```

Tại sao phải giữ thứ tự này?

### Trường hợp A: lưu checkpoint trước khi xử lý

```text
Nhận E101
    |
    v
Lưu token T101   <-- checkpoint đi trước
    |
    v
Crash trước khi xử lý E101
    |
    v
Restart -> resumeAfter(T101)
    |
    v
Bắt đầu từ E102
```

Kết quả: **E101 có thể bị bỏ qua vĩnh viễn đối với consumer**. MongoDB đã làm đúng theo `resumeAfter`: chỉ phát event sau vị trí đã checkpoint. Lỗi nằm ở thứ tự commit của ứng dụng.

### Trường hợp B: xử lý trước khi checkpoint

```text
Nhận E101
    |
    v
Xử lý E101 thành công
    |
    v
Crash trước khi lưu T101
    |
    v
Restart -> resumeAfter(T100)
    |
    v
E101 được phát lại
```

Kết quả: **E101 có thể được xử lý lại**. Nếu tác vụ xử lý có tính idempotent, việc phát lại sẽ không làm hỏng dữ liệu. Đây là cách đánh đổi thường được chọn: **chấp nhận at-least-once delivery với xử lý trùng an toàn**, thay vì checkpoint sớm để rồi làm mất event.

### Bảng đánh đổi

| Thứ tự | Crash ở giữa | Rủi ro |
| --- | --- | --- |
| Token trước → side effect sau | Sau khi lưu token, trước khi xử lý | **Bỏ sót sự kiện** |
| Side effect trước → token sau | Sau khi xử lý, trước khi lưu token | **Nhận/xử lý trùng** |
| Side effect + token trong cùng transaction của sink tương thích | Transaction abort/commit nguyên tử | Có thể đạt hiệu quả **exactly-once tại sink cụ thể** với điều kiện thiết kế đúng |

Không nên tuyên bố Change Stream tự cung cấp **exactly-once end-to-end**. Driver có thể resume, nhưng việc ứng dụng đã gửi email, gọi REST API hoặc ghi xuống hệ thống khác không nằm trong cùng giao thức commit với resume token.

## 8. Thiết kế idempotency khi có thể nhận lại event

### 8.1. Dùng token hoặc operation ID làm khóa chống trùng

Giả sử consumer ghi log các event đã xử lý:

```javascript
db.processedChanges.updateOne(
  { _id: change._id },
  {
    $setOnInsert: {
      documentKey: change.documentKey,
      operationType: change.operationType,
      processedAt: new Date()
    }
  },
  {
    upsert: true,
    writeConcern: { w: "majority" }
  }
);
```

Vì `_id` của record `processedChanges` sử dụng resume token, cùng một event phát lại sẽ đối chiếu với cùng khóa. Nhưng **chỉ ghi một dấu “processed” không đủ để bảo vệ một side effect diễn ra ở hệ thống khác**: nếu đánh dấu đã xử lý rồi crash trước khi gửi sự kiện ra bên ngoài, lần sau có thể bỏ qua side effect cần thiết.

### 8.2. Cập nhật trạng thái bằng phép gán có thể lặp

Ví dụ một event cho biết trạng thái hiện tại là `paid`. Nếu read model chỉ cần lưu trạng thái hiện tại:

```javascript
db.orderReadModel.updateOne(
  { _id: "order-1001" },
  {
    $set: {
      status: "paid"
    }
  },
  { upsert: true }
);
```

Chạy lại cùng phép `$set` thường không tạo thêm số lần thanh toán. Nhưng cần xét **thứ tự event**: nếu sự kiện cũ được replay sau khi hệ thống đã xử lý một sự kiện mới hơn, thao tác `$set` cũ có thể ghi đè trạng thái mới. Vì thế, idempotency không chỉ là “thao tác chạy hai lần cho cùng kết quả”; còn phải **chống cập nhật lùi phiên bản** nếu consumer có xử lý song song, replay hoặc nhiều nguồn.

Một thiết kế có thể ghi kèm **version/sequence đáng tin cậy**, hoặc buộc xử lý tuần tự và cập nhật có điều kiện. Không dùng so sánh chuỗi `_data` của token để suy ra version; token là opaque.

### 8.3. Tránh phép cộng không idempotent

Nếu mỗi event làm:

```javascript
db.counters.updateOne(
  { _id: "paidOrders" },
  { $inc: { count: 1 } },
  { upsert: true }
)
```

thì một event phát lại có thể tăng `count` **hai lần**. Cần lưu dấu sự kiện đã được áp dụng **cùng với phép tăng** trong một transaction phù hợp, hoặc tính lại counter từ nguồn dữ liệu, hoặc chọn cơ chế tổng hợp khác có khả năng reconciliation.

### 8.4. Atomic sink + checkpoint

Khi **side effect và checkpoint đều nằm trong cùng MongoDB deployment** và mô hình ghi hỗ trợ transaction, có thể thiết kế một transaction:

```text
Nhận event E101 từ Change Stream
       |
       v
BEGIN transaction của sink
       |
       +-- Kiểm tra E101 đã xử lý chưa
       +-- Cập nhật read model / ledger
       +-- Ghi processed event ID
       +-- Ghi checkpoint token T101
       |
       v
COMMIT transaction (writeConcern phù hợp)
```

Khi transaction commit nguyên tử, sink và checkpoint cùng tiến hoặc cùng không tiến. Đây là phương án mạnh khi yêu cầu chính xác, nhưng vẫn phải xử lý **transaction retry/unknown commit result**, khóa unique/operation ID và concurrency. Không được mở Change Stream *bên trong* transaction như một thao tác đọc thông thường; stream được tiêu thụ ngoài transaction, còn **ghi kết quả và checkpoint** có thể được đặt trong transaction riêng.

Với Kafka, email, HTTP hoặc hệ thống ngoài MongoDB, không thể mặc nhiên đặt side effect ngoài ấy cùng một MongoDB transaction. Cần **outbox, deduplication key, idempotent consumer hoặc giao thức phối hợp** phù hợp.

## 9. Ba cơ chế bắt đầu/tiếp tục stream

Change Stream hỗ trợ những cách định vị có mục đích khác nhau.

| Option | Đầu vào | Ý nghĩa | Khi nào dùng? |
| --- | --- | --- | --- |
| **`resumeAfter`** | Resume token đã biết | Bắt đầu **sau** vị trí token | Restart consumer sau event bình thường, lịch sử còn |
| **`startAfter`** | Resume token đã biết | Bắt đầu sau token, hỗ trợ trường hợp đặc biệt như **invalidate event** | Khi cần mở stream mới sau invalidate theo phạm vi được hỗ trợ |
| **`startAtOperationTime`** | BSON Timestamp | Bắt đầu tại/thông qua mốc thời gian thao tác phù hợp | Khi có mốc cluster operation time hợp lệ, không có token hoặc quy trình cần mốc thời gian |

Các option lựa chọn vị trí mở luồng này **không được phối hợp tùy ý trong cùng lệnh**; dùng đúng một cơ chế phù hợp với trạng thái cần phục hồi.

### 9.1. `resumeAfter`

Trong `mongosh`:

```javascript
const checkpoint = db.consumerCheckpoints.findOne({
  _id: "orders-sync-v1"
});

const options = checkpoint && checkpoint.resumeToken
  ? { resumeAfter: checkpoint.resumeToken }
  : {};

const stream = db.orders.watch([], options);
```

Nếu checkpoint chứa token còn hợp lệ và có thể resume, stream đọc tiếp **sau token ấy**. Nếu checkpoint không có, đoạn code trên mở stream từ thời điểm bắt đầu theo cách mặc định của Change Stream; nó **không tự đọc lại mọi thao tác cũ**. Trong hệ thống cần đối soát đầy đủ, tình huống checkpoint bị thiếu phải đi qua **khởi tạo/rebuild có kiểm soát**, không được âm thầm coi là consumer mới và bỏ qua toàn bộ lịch sử.

### 9.2. `startAfter` sau invalidate

Khi watched collection bị drop hoặc rename, một **collection-level change stream** có thể nhận `invalidate` và bị đóng. Trường hợp này có quy tắc khác với lỗi mạng đơn thuần.

```javascript
// Chỉ minh họa việc mở stream mới sau một invalidate token
const stream = db.orders.watch([], {
  startAfter: invalidateResumeToken
});
```

`startAfter` được dùng để bắt đầu stream mới sau một token, kể cả một **invalidate event** trong những tình huống được hỗ trợ. **`resumeAfter` không dùng để tiếp tục qua invalidate event**.

Tuy nhiên, mở stream mới sau invalidate **không làm dữ liệu của collection đã drop tự xuất hiện lại** và không bảo đảm collection mới cùng tên có cùng lịch sử. Khi schema/namespace bị thay đổi, ứng dụng phải xác định **cần xây lại read model hay không**.

### 9.3. `startAtOperationTime`

Ví dụ về cú pháp (timestamp phải lấy từ **cluster thực** hoặc điểm điều phối hợp lệ, không tự bịa):

```javascript
db.orders.watch([], {
  startAtOperationTime: knownClusterTimestamp
});
```

Tùy chọn này không phải phương án thần kỳ khi **oplog đã xóa lịch sử cũ**. Nếu mốc thời gian nằm ngoài phần lịch sử có thể phục vụ, MongoDB vẫn có thể không khôi phục được luồng.

**Không lấy `new Date()` trên máy ứng dụng rồi chuyển thành resume token.** BSON Timestamp dùng trong operation time là khái niệm khác BSON Date của đồng hồ hệ thống; quy tắc chuyển và khả năng bắt đầu phải dựa trên thông tin cluster được hỗ trợ.

### 9.4. Không tự giải mã token để chuyển sang timestamp

```text
Sai cách:
  token._data -> tách vài byte -> đoán timestamp -> startAtOperationTime

Đúng cách:
  giữ nguyên BSON token
  -> resumeAfter(token) khi hợp lệ
  hoặc startAfter(invalidateToken) khi phù hợp
  hoặc dùng operation time có nguồn gốc hợp lệ
```

Cấu trúc nội bộ của resume token có thể thay đổi qua phiên bản; mã ứng dụng không được phụ thuộc vào việc diễn giải token bằng một thuật toán tự chế.

## 10. Post-batch resume token: khi stream đang rảnh vẫn cần checkpoint?

Không phải lúc nào collection cũng có event mới. Một consumer có thể chạy trong nhiều phút mà không nhận `insert`, `update` hay `delete`. Nếu chỉ checkpoint **event token**, vị trí lưu cuối có thể rất cũ dù stream vẫn liên tục đọc các batch rỗng.

MongoDB có cơ chế **post-batch resume token (PBRT)** trong những tình huống được hỗ trợ. Đây là token biểu diễn một vị trí tiến trình server có thể dùng để resume ngay cả khi batch mới không chứa event.

```text
Server xử lý Change Stream
   |
   +-- batch có E101, E102 --> event tokens
   |
   +-- batch rỗng ---------> có thể có postBatchResumeToken
   |
   v
Driver/cursor có thể duy trì một resume token mới nhất
```

Điều này hữu ích để consumer không giữ mãi một checkpoint rất cũ trong khi lịch sử phía server đang tiến về phía trước.

**Nhưng có một quy tắc quan trọng:** không được checkpoint một PBRT **vượt qua những event ứng dụng đã nhận nhưng chưa xử lý xong**. Chỉ lưu token tiến xa khi mọi event trước vị trí ấy thuộc phạm vi stream đã được xử lý bền vững.

### Event token và PBRT khác nhau

- **Event token:** nhận từ `change._id` hoặc `ChangeStreamDocument.getResumeToken()`.
- **PBRT:** nhận từ thông tin batch/cursor do server-driver cung cấp; không phải tự tính từ đồng hồ.
- **Token được persist:** phải tương ứng với **điểm xử lý an toàn**, không nhất thiết là token mới nhất mà driver đang thấy trong bộ nhớ.

MongoDB Java Sync Driver có API của Change Stream cursor để truy cập resume token đang được cursor giữ trong những phiên bản hỗ trợ. Khi consumer cần checkpoint lúc idle, phải hiểu semantics của **cursor buffering, batch processing và thứ tự side effect** trước khi lưu token do cursor báo.

Một mô hình đơn giản, dễ an toàn cho người mới học là chỉ checkpoint **event token sau xử lý thành công**, rồi mở rộng sang PBRT khi đã kiểm soát được toàn bộ xử lý theo batch và idle.

## 11. Cách mở stream sau restart trong `mongosh`

Giả sử đã có collection `consumerCheckpoints`, consumer chỉ xử lý lần lượt từng event và có hàm xử lý idempotent.

```javascript
use change_stream_lab

const consumerId = "orders-sync-v1";
const saved = db.consumerCheckpoints.findOne({
  _id: consumerId
});

const watchOptions = {
  fullDocument: "updateLookup",
  maxAwaitTimeMS: 2000
};

if (saved && saved.resumeToken) {
  watchOptions.resumeAfter = saved.resumeToken;
}

const cursor = db.orders.watch([], watchOptions);

try {
  while (cursor.hasNext()) {
    const change = cursor.next();

    // Mẫu read model đơn giản: lưu dấu event bằng token.
    // Đây chỉ là minh họa side effect idempotent trong MongoDB.
    db.processedChanges.updateOne(
      { _id: change._id },
      {
        $setOnInsert: {
          operationType: change.operationType,
          documentKey: change.documentKey,
          processedAt: new Date()
        }
      },
      {
        upsert: true,
        writeConcern: { w: "majority" }
      }
    );

    // CHỈ checkpoint sau khi side effect ở trên thành công.
    db.consumerCheckpoints.updateOne(
      { _id: consumerId },
      {
        $set: {
          resumeToken: change._id,
          updatedAt: new Date(),
          state: "RUNNING",
          streamScope: "change_stream_lab.orders",
          pipelineVersion: 1
        }
      },
      {
        upsert: true,
        writeConcern: { w: "majority" }
      }
    );

    print("Đã xử lý:", change.operationType);
  }
} finally {
  cursor.close();
}
```

Với `maxAwaitTimeMS`, batch rỗng có thể khiến cursor đợi các đợt dữ liệu tiếp theo; vòng `hasNext()` vẫn có thể chạy dài hạn. Đoạn code **không tự dừng sau một số event**. Trong service thật cần handle shutdown, phân loại lỗi và cơ chế backoff/restart.

### Giới hạn của ví dụ

- `processedChanges` và `consumerCheckpoints` là **hai lệnh ghi độc lập**. Nếu crash sau lệnh thứ nhất, event có thể được phát lại; khóa `_id` chống tạo bản processed trùng.
- Nếu side effect thật là gửi email, ví dụ này **không đủ** để bảo đảm email chỉ gửi một lần.
- Nếu có **hai instance consumer cùng dùng consumerId**, cả hai có thể xử lý event và ghi đè checkpoint lẫn nhau. Cần leader election/lease/fencing token hoặc partition ownership, không chạy tự do nhiều consumer với một checkpoint.
- `fullDocument:"updateLookup"` có thể giúp lấy document hiện tại cho update, nhưng `fullDocument` của update có thể không còn như ảnh “ngay sau update” nếu document bị sửa/xóa tiếp. Không dùng nó như nguồn snapshot lịch sử tuyệt đối.
- Nếu không có checkpoint, code bắt đầu từ vị trí hiện tại. Hệ thống cần chính xác từ đầu phải thực hiện bootstrap/reconciliation trước; đoạn code được dùng minh họa cơ chế kỹ thuật, **không phải quy trình khởi tạo production hoàn chỉnh**.

## 12. Khi consumer dừng lâu: cửa sổ lịch sử oplog là gì?

Oplog là một **capped collection** trong replica set thông thường. Khi thay đổi mới tiếp tục được ghi, lịch sử cũ có thể bị ghi đè để đáp ứng các giới hạn dung lượng và cấu hình lưu giữ. Vì thế, cửa sổ thời gian có thể resume **không phải vô hạn**.

```text
Thời gian quá khứ ------------------------------------> hiện tại

  E01  E02  E03  E04  E05  E06  E07  E08  E09  E10
                 |===============================|
                 |    lịch sử hiện còn trong     |
                 |          oplog                |

Checkpoint consumer: T02
                       |
                       v
                  E02 đã mất
                  không đủ lịch sử

resumeAfter(T02) -> có thể thất bại vì oplog history lost
```

Nếu event cần thiết để xác định vị trí tiếp tục không còn, MongoDB không thể lấy lại nó chỉ từ một opaque resume token.

### Độ dài cửa sổ oplog không cố định

Cùng một oplog có kích thước giới hạn:

- Khi hệ thống ghi rất ít, lịch sử có thể tồn tại khá lâu.
- Khi lượng ghi tăng đột biến, cùng dung lượng bị lấp nhanh hơn, làm **cửa sổ thời gian thực tế ngắn lại**.
- Một đợt bulk load, migration, update hàng loạt hoặc backfill có thể tạo nhiều oplog entries và làm rủi ro consumer bị tụt lại tăng nhanh.

Vì vậy, “oplog đủ cho 24 giờ” phải được hiểu là **ước lượng dựa trên workload**, không phải SLA cố định cho mọi thời điểm nếu hệ thống không có cơ chế bảo đảm retention tương ứng.

### Sharded cluster có nhiều lịch sử cần quan tâm

Trên sharded cluster, mỗi shard là một replica set với oplog riêng. Change Stream có thể cần quan sát thay đổi từ nhiều shard; tình trạng lịch sử của **một shard** cũng có thể ảnh hưởng khả năng resume của luồng phạm vi nhiều shard.

Không chỉ kiểm tra oplog ở một shard có nhiều traffic rồi kết luận toàn bộ stream an toàn. Cần giám sát retention và replication health trên **những shard có liên quan** và lưu ý sự thay đổi topology/migration theo phiên bản.

## 13. Cách nhận biết lỗi không còn lịch sử để resume

Khi resume thất bại vì lịch sử cần thiết đã mất, MongoDB có thể trả lỗi với tên/thông điệp liên quan đến **Change Stream history lost**, chẳng hạn `ChangeStreamHistoryLost`. Tùy server và driver, error code, error message và nhãn lỗi có thể được biểu diễn khác nhau.

Một số tình huống khác cũng làm resume thất bại:

- Token thuộc stream scope/namespace hoặc cấu hình không còn phù hợp.
- Collection bị drop/rename và stream nhận `invalidate`.
- Token bị lưu thiếu field, chuyển sai kiểu BSON hoặc chỉnh sửa thủ công.
- Pipeline thay đổi làm không giữ được resume token `_id` hợp lệ.
- Quyền truy cập bị thu hồi, network lỗi, topology không còn primary hoặc server không hỗ trợ option.

**Không gom tất cả lỗi mở stream vào “history lost”.** Cần phân biệt lỗi tạm thời có thể retry, lỗi không hợp lệ của token/pipeline và lỗi thiếu lịch sử cần **rebuild**.

### Vì sao retry liên tục không sửa được oplog history lost?

```text
Checkpoint T1000
      |
      v
Lịch sử chứa T1000 đã bị ghi đè
      |
      v
resumeAfter(T1000) -> history lost
      |
      v
retry cùng token -> vẫn không có lịch sử đã mất
```

Retry nhanh hàng nghìn lần chỉ tăng tải và log, không thể làm một oplog entry đã bị loại bỏ xuất hiện trở lại. Khi xác nhận **non-resumable history loss**, consumer phải **dừng tiến checkpoint như bình thường** và chuyển sang recovery có kiểm soát.

### Không âm thầm xóa checkpoint rồi mở watch mới

Một cách xử lý sai:

```javascript
// SAI cho một consumer yêu cầu không được bỏ sót sự kiện
try {
  // watch({ resumeAfter: oldToken })
} catch (e) {
  db.consumerCheckpoints.deleteOne({ _id: "orders-sync-v1" });
  db.orders.watch(); // bắt đầu từ hiện tại, bỏ qua khoảng trống
}
```

Nếu các sự kiện giữa T1000 và hiện tại chưa được đưa vào read model, khởi động stream mới từ thời điểm hiện tại sẽ **bỏ qua chúng vĩnh viễn**. Việc cursor không còn báo lỗi sau đó không chứng minh dữ liệu đích đã đồng bộ đúng.

## 14. Phân loại lỗi trước khi khôi phục

| Tình huống | Dấu hiệu | Phản ứng phù hợp |
| --- | --- | --- |
| Network ngắt ngắn | Socket lỗi, server selection lỗi, có thể retry | Backoff, kết nối lại bằng token đã checkpoint |
| Primary failover | Không tìm thấy primary hoặc topology thay đổi trong thời gian ngắn | Chờ topology ổn định rồi resume theo token |
| Error có nhãn resumable theo driver | Driver/server cho phép resume | Dùng cơ chế tự resume hoặc mở lại stream bằng token bền vững |
| `ChangeStreamHistoryLost` | Oplog thiếu lịch sử cần để resume | Đánh dấu `NEEDS_REBUILD`, chạy reconciliation/cutover |
| `invalidate` do collection drop/rename | Event invalidate và stream kết thúc | Đánh giá `startAfter`, scope và dựng lại trạng thái nếu namespace thay đổi |
| Token BSON bị sửa/hỏng | Invalid resume token/parse error | Khôi phục bản checkpoint hợp lệ hoặc rebuild; không “sửa” token bằng đoán |
| Token thuộc scope/pipeline khác | Resume không nhất quán hoặc pipeline vi phạm quy tắc token | Dừng consumer, kiểm tra version/scope rồi khởi tạo lại có chủ đích |
| Lỗi quyền | Unauthorized/không có quyền watch namespace | Sửa quyền/credential; không xóa checkpoint |
| Lỗi xử lý side effect | Sink API/DB từ chối | **Không** checkpoint event; retry xử lý/idempotency |

### Một state machine đơn giản

```text
              STARTING
                  |
        đọc checkpoint hợp lệ
                  |
                  v
               RUNNING
            /     |     \
           /      |      \
      lỗi mạng  sink lỗi  history lost
         |        |          |
         v        v          v
     RETRYING  RETRY_EVENT  NEEDS_REBUILD
         |        |          |
         +--------+          v
            |           RECONCILING
            |                |
            v                v
          RUNNING <---- SAFE_CUTOVER
```

Trạng thái `NEEDS_REBUILD` cần được thể hiện trong hệ thống giám sát. Không nên chỉ in một dòng log rồi tiếp tục phục vụ dữ liệu đích như thể không có khoảng trống.

## 15. Khi history lost: cần tái đồng bộ dữ liệu

Khi không thể resume đúng từ checkpoint cũ, cần phân biệt hai loại hệ thống đích:

1. **Read model/cache có thể tái tạo từ trạng thái hiện tại của MongoDB**: ví dụ bản sao tìm kiếm theo document hiện hành. Có thể full snapshot/reconciliation rồi tiếp tục nhận thay đổi mới từ một vị trí chuyển tiếp an toàn.
2. **Hệ thống cần mọi sự kiện lịch sử chính xác**: ví dụ hệ thống kiểm toán bắt buộc lưu từng chuyển trạng thái. Snapshot hiện tại **không thể dựng lại đầy đủ chuỗi sự kiện đã mất**. Cần nguồn lịch sử khác như durable event log, audit ledger, archive, backup/oplog được giữ riêng hoặc một quy trình khôi phục có giới hạn, nếu chúng tồn tại.

**Không có phương pháp tổng quát biến snapshot hiện tại thành mọi update/delete đã xảy ra.** Nếu một document từng đổi từ A sang B rồi trở lại A, trạng thái cuối A không cho biết đã có hai thay đổi trung gian.

### Ba mức khôi phục

| Nhu cầu | Hướng xử lý | Hạn chế |
| --- | --- | --- |
| Chỉ cần trạng thái hiện tại | Rebuild toàn bộ hoặc reconciliation có điểm chuyển tiếp | Phải tránh gap giữa snapshot và stream mới |
| Cần cập nhật gần thời gian thực, chấp nhận mất lịch sử | Có thể bắt đầu watch mới sau khi báo degraded/loss rõ ràng | Không được tuyên bố đồng bộ đầy đủ lịch sử |
| Cần đủ mọi event không mất | Khôi phục từ nguồn lưu lịch sử độc lập hoặc sự kiện đã durable ngoài oplog | Nếu không có nguồn đó, phần lịch sử đã mất có thể không khôi phục được |

Một hệ thống nghiệp vụ quan trọng phải quyết định loại khôi phục nào chấp nhận được **trước khi** xảy ra history loss.

## 16. Vì sao “snapshot rồi mở stream mới” có thể làm mất sự kiện?

Đây là một lỗi thiết kế phổ biến:

```text
t0: bắt đầu quét collection
t1: đọc order-1001, status = pending
t2: người dùng cập nhật order-1001 -> paid
t3: hoàn tất snapshot
t4: mở change stream từ thời điểm hiện tại

Snapshot đã đọc giá trị pending tại t1.
Event cập nhật xảy ra ở t2.
Stream chỉ bắt đầu ở t4.

=> Read model có thể kẹt mãi ở pending.
```

Chỉ thêm một lần `find()` toàn bộ trước `watch()` **không bảo đảm đúng** nếu vẫn cho phép ghi xảy ra trong khoảng giữa. Đây là **snapshot-to-stream gap**.

### Cần một ranh giới chuyển tiếp an toàn

Có hai họ giải pháp thường dùng:

**A. Dừng/điều phối ghi ngắn hạn (quiesce/fence writes).**

Đặt hệ thống ở một trạng thái không có ghi ngoài ý muốn, rebuild trạng thái hiện tại, xác lập một stream checkpoint mới **trước khi mở lại ghi**, rồi tiếp tục từ checkpoint đó. Cơ chế fence phải đủ mạnh để ngăn cả background job, consumer khác và writer tới các shard liên quan.

**B. Mở stream trước, lưu bền vững thay đổi trong lúc snapshot.**

Thiết lập một vị trí watch hợp lệ; trong khi quét snapshot, **đệm bền vững các event phát sinh**. Sau đó áp dụng snapshot và replay phần thay đổi từ một ranh giới nhất quán, có xử lý trùng/thứ tự, rồi chuyển sang live processing. Phương án này phức tạp hơn, đặc biệt với snapshot nhiều collection/shard, nên cần các điều kiện nhất quán và cutover được định nghĩa rõ.

Hai phương án đều nhằm giải quyết cùng vấn đề: **mọi thay đổi xảy ra giữa snapshot và live stream phải được tính đúng**, không bị lọt qua khoảng trống.

## 17. Recovery có dừng ghi: minh họa theo một quy trình có kiểm soát

Giả sử sink là collection `orderReadModel` có thể xây lại từ trạng thái hiện tại của `orders`. Một quy trình khái quát:

1. **Đánh dấu consumer `NEEDS_REBUILD`**, giữ lại token lỗi để phục vụ điều tra. Ngừng cho phép những checkpoint “RUNNING” mới được ghi bởi consumer cũ.
2. **Fencing writers:** tạm dừng hoặc điều phối toàn bộ writer của namespace nguồn để không có thay đổi chen vào trong khoảng chuyển tiếp. Cần một cơ chế được xác nhận ở phía ứng dụng/hạ tầng, không phải chỉ tắt một instance ngẫu nhiên.
3. **Xây lại sink** từ dữ liệu nguồn đang ổn định. Dùng collection/generation mới để tránh phục vụ một read model đang xây dở.
4. **Xác lập điểm resume hợp lệ khi write vẫn bị fence.** Có thể mở một Change Stream mới và nhận một token có thể lưu, hoặc sử dụng một **barrier event** trong phạm vi watched stream để lấy event token chắc chắn, theo khả năng server/driver.
5. **Lưu bền vững token và generation/cutover state**, dùng write concern thích hợp.
6. **Chuyển người đọc sang sink đã rebuild**, mở consumer tiếp tục từ token mới, rồi giải phóng write fence theo trình tự đã thiết kế.
7. **Giám sát** event lag, sink consistency và lỗi khôi phục.

```text
Writer:   -- hoạt động -- |== FENCE ==| ----- hoạt động ---->
                          |           |
Snapshot:                 |== REBUILD |
                                      |
Resume anchor:                        Tnew
                                      |
Consumer:                             +-- resumeAfter(Tnew) -->
```

### Barrier event là gì?

Một **barrier event** là thao tác thay đổi có chủ đích mà consumer có thể nhận token của nó sau khi mọi writer ứng dụng khác đã bị fence. Ví dụ trong **lab** có thể cập nhật một document metadata thuộc collection được watch, và pipeline watch **không được lọc bỏ event marker trước khi lấy token**.

```javascript
// CHỈ LÀ MINH HỌA CƠ CHẾ BARRIER TRÊN LAB,
// KHÔNG PHẢI LỆNH TỰ ĐỘNG CHẠY TRÊN PRODUCTION.
db.orders.updateOne(
  { _id: "__stream_barrier__" },
  {
    $set: {
      kind: "__stream_barrier__",
      barrierId: "rebuild-2026-11-14",
      createdAt: new Date()
    }
  },
  { upsert: true, writeConcern: { w: "majority" } }
);
```

Consumer theo dõi sự kiện barrier, xác nhận mọi thay đổi trước ranh giới đã được bao phủ bởi snapshot/rebuild, sau đó persist resume token của barrier. Trong ứng dụng thật cần tách marker khỏi dữ liệu nghiệp vụ và chứng minh thứ tự fence/snapshot/marker/consumer là đúng trên topology được sử dụng.

**Không mở lại writes trước khi có một resume anchor an toàn.** Nếu consumer vẫn đọc token cũ đã mất, việc rebuild xong mà không có checkpoint mới hợp lệ sẽ quay lại vòng history lost.

## 18. Recovery không dừng ghi: stream-first + snapshot + replay

Khi không thể tạm dừng ghi, một kiến trúc phổ biến hơn là **capture thay đổi trước khi quét trạng thái**:

```text
t0: mở change stream mới, xác lập resume anchor
          |
t1: bắt đầu lưu bền vững các event mới vào staging log
          |
t2: chụp snapshot / quét nguồn
          |
t3: snapshot hoàn tất
          |
t4: replay các event từ staging theo quy tắc cutover
          |
t5: chuyển sang xử lý live
```

Tính đúng đắn đòi hỏi:

- **Anchor của stream hợp lệ và còn được phục vụ** trong thời gian recovery.
- **Staging log bền vững**, không chỉ là một array trong RAM; nếu restart trong lúc rebuild, vẫn có thể phát lại các event cần thiết.
- **Snapshot nhất quán hoặc thuật toán reconciliation đúng** để xác định event nào phải replay và lúc nào có thể loại phần trùng.
- **Thứ tự áp dụng event phù hợp** với nghiệp vụ và nguồn thay đổi.
- **Không để staging consumer tụt quá xa** khiến chính stream mới cũng vượt khỏi cửa sổ oplog.
- **Cutover có fencing/epoch** để một consumer cũ không ghi checkpoint sai trong khi consumer mới đã bắt đầu.

### Không áp dụng event cũ đè lên snapshot mới một cách mù quáng

Ví dụ:

```text
t0: stream được mở
t1: order-1001 đổi pending -> paid, event E1 được đệm
t2: snapshot đọc order-1001 ở trạng thái paid
t3: order-1001 đổi paid -> refunded, event E2 được đệm
t4: snapshot hoàn tất
```

Nếu sink nạp snapshot trạng thái cuối và sau đó replay E1/E2 theo cách ghi đè không xét thứ tự, có thể còn đúng trong ví dụ đơn giản; nhưng ở hệ thống có nhiều collection, delete, update từng field, event xen kẽ và snapshot không có timestamp thống nhất, kết quả có thể sai.

Để bảo đảm chính xác, cần một **mốc snapshot/cutover rõ ràng** hoặc cơ chế reconcile theo version/ID, không chỉ dựa vào “đọc snapshot trước, replay mọi event đệm sau”. Đối với sharded cluster và dữ liệu đa collection, nên chọn giải pháp bootstrap CDC đã được thiết kế/kiểm chứng cho topology đó.

### Khi không có snapshot nhất quán

Nếu không thể dừng ghi, không có snapshot nhất quán, và cũng không có thuật toán reconcile đúng, hệ thống không thể khẳng định một rebuild thủ công bất kỳ là **lossless**. Khi đó phải ghi rõ **consistency gap** hoặc chọn hệ thống/hạ tầng hỗ trợ quy trình bootstrap đáng tin cậy.

## 19. Oplog retention: theo dõi trước khi xảy ra sự cố

Lịch sử chỉ có ích nếu consumer còn kịp resume. Nên theo dõi:

- **Thời điểm checkpoint xử lý bền vững gần nhất**.
- **Độ trễ giữa event được tạo và event được checkpoint** (consumer lag).
- **Tuổi của oplog entry cũ nhất còn có thể phục vụ** trên các replica set/shard liên quan.
- **Tốc độ sinh thay đổi/oplog volume** trong giờ cao điểm.
- **Số lần reconnect/resume**, lỗi non-resumable và số lần chuyển sang rebuild.
- **Tốc độ xử lý sink**, backlog và thời gian side effect hoàn tất.
- **Độ dài/chi phí rebuild** nếu một ngày phải tái đồng bộ.

### Kiểm tra oplog trên replica set lab

Trong những môi trường và quyền truy cập phù hợp, có thể xem thông tin replication:

```javascript
rs.printReplicationInfo();
```

Lệnh này thường cho các chỉ số về dung lượng oplog và khoảng thời gian giữa những bản ghi cũ/mới đang hiện diện. Trên sharded cluster, cần chạy/thu thập từ **mỗi replica set của các shard liên quan**, không chỉ từ một `mongos` và không suy từ một node rằng tất cả shard đều có cửa sổ giống nhau.

Một cách khảo sát sâu hơn trên **replica set lab**, nếu tài khoản có quyền đọc `local`:

```javascript
db.getSiblingDB("local")
  .getCollection("oplog.rs")
  .find({}, { ts: 1 })
  .sort({ $natural: 1 })
  .limit(1);
```

Đây là thao tác **đọc** để quan sát oplog entry cũ nhất còn thấy được. Không sửa hoặc xóa trực tiếp `local.oplog.rs`. Các phép so sánh thời gian cần xét đúng **BSON Timestamp**, đồng hồ cluster, và độ lệch đồng hồ máy theo môi trường.

### Không dựa vào một ngưỡng thời gian cứng

Giả sử theo dõi thấy:

```text
Consumer lag hiện tại:       45 phút
Cửa sổ oplog đang quan sát:  6 giờ
```

Hệ thống có khoảng đệm, nhưng **không được khẳng định bảo đảm 5 giờ 15 phút**. Nếu tốc độ ghi tăng đột ngột, cửa sổ oplog có thể co lại trước khi consumer theo kịp.

Nên đặt cảnh báo khi lag tiến gần một **tỷ lệ đủ thận trọng** của lịch sử đang còn, đồng thời cảnh báo backlog và thời gian không checkpoint. Ngưỡng cụ thể phụ thuộc SLA, nhịp tải và khả năng khôi phục của từng hệ thống.

## 20. Vai trò của oplog size và retention configuration

Một số deployment cho phép cấu hình dung lượng oplog hoặc các tham số retention tương ứng theo phiên bản. Việc tăng khả năng lưu lịch sử có thể tạo thêm thời gian cho consumer phục hồi sau khi tắt lâu, nhưng cần đánh giá:

1. Chi phí disk, I/O và vận hành của replica set.
2. Tốc độ ghi thực tế (không chỉ số document thay đổi).
3. Độ trễ/khả năng đồng bộ của secondary.
4. Số consumer và tốc độ checkpoint của từng consumer.
5. Khả năng vận hành khi một shard có traffic đột biến.

**Thay đổi cấu hình oplog không thay thế checkpoint bền vững hay idempotency.** Nó chỉ giúp mở rộng cơ hội còn lịch sử để resume. Nếu event đã bị mất hoặc consumer cần bảo toàn sự kiện qua một thời gian lưu trữ vượt quá khả năng oplog, cần hệ thống lưu sự kiện bền vững riêng.

Trong managed MongoDB deployment, khả năng chỉnh oplog/retention có thể bị giới hạn hoặc khác với tự vận hành. Không hướng dẫn chỉnh cấu hình server để xử lý một consumer chậm mà chưa đánh giá toàn hệ thống.

## 21. Lỗi invalidate không giống history lost

Một Change Stream có thể bị **invalidate** bởi các thao tác thay đổi namespace, chẳng hạn drop hoặc rename collection ở phạm vi theo dõi phù hợp.

```text
Collection orders hoạt động
        |
        v
   drop / rename
        |
        v
  invalidate event
        |
        v
   stream kết thúc
```

Đây không nhất thiết là vấn đề oplog thiếu lịch sử. Stream có thể đã phát một **invalidate event** hợp lệ, rồi đóng theo quy tắc của nó.

Phân biệt hai tình huống:

- **Lịch sử oplog không còn:** `resumeAfter` token cũ không lấy lại được phần lịch sử cần thiết. Phải đánh giá rebuild/reconciliation.
- **Nhận invalidate event:** đã quan sát một sự kiện kết thúc phạm vi watch. Có thể mở stream mới qua `startAfter` của **invalidate token** trong những tình huống được hỗ trợ, nhưng phải xem lại **namespace và dữ liệu nguồn**.

Nếu `orders` bị drop rồi tạo lại, read model cũ có thể chứa các đơn không còn tồn tại trong collection mới. Chỉ tiếp tục stream sau invalidate **không tự xóa toàn bộ read model đã lỗi thời**. Hệ thống cần chính sách xử lý collection lifecycle.

## 22. Pipeline có thể khiến resume token không hợp lệ

Change Stream trả event có trường `_id` là resume token. Một số pipeline biến đổi có thể vô tình sửa hoặc loại trường này.

Ví dụ không nên dùng:

```javascript
db.orders.watch([
  {
    $project: {
      _id: 0,
      operationType: 1,
      documentKey: 1
    }
  }
]);
```

Pipeline trên loại `_id`, tức loại resume token. Change Stream cần token để tiếp tục; server có thể từ chối kết quả/pipeline không giữ token phù hợp. Tương tự, không thay `_id` bằng `documentKey._id`.

### Một filter đơn giản

```javascript
db.orders.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  }
]);
```

Filter giúp giảm các event gửi đến ứng dụng, nhưng **đổi filter giữa các phiên bản consumer có thể thay đổi ngữ nghĩa xử lý**. Nếu checkpoint lấy từ pipeline cũ, pipeline mới có thể bỏ những event trước đây được xử lý hoặc ngược lại. Vì vậy, cùng với token nên lưu `streamScope` và `pipelineVersion`; khi đổi logic quan trọng, cần xem lại chiến lược migration/cutover.

Một số thay đổi namespace hoặc option như `fullDocument` cũng có ý nghĩa đối với side effects; không coi mọi lần deploy pipeline mới là tương thích tuyệt đối với checkpoint cũ mà không xét ngữ nghĩa.

## 23. Java MongoDB Sync Driver: consumer đọc/lưu token bền vững

MongoDB Java Sync Driver hỗ trợ:

- `ChangeStreamIterable<T>` để cấu hình stream.
- `ChangeStreamDocument<T>` để đọc event.
- `MongoChangeStreamCursor<T>` để duyệt cursor.
- `resumeAfter(BsonDocument)` và `startAfter(BsonDocument)` để định vị.
- `getResumeToken()` trên event để lấy token BSON.

Đoạn mã dưới đây minh họa **một consumer tuần tự**, lưu event receipt và checkpoint dưới dạng BSON document, không dùng string serialization làm mất kiểu. Dữ liệu sink chỉ là một collection đánh dấu event đã thấy; sản phẩm thật cần thay phần xử lý bằng side effect phù hợp và bổ sung điều phối ownership.

### 23.1. Mã Java

```java
import com.mongodb.WriteConcern;
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.bson.BsonDateTime;
import org.bson.BsonDocument;
import org.bson.BsonString;
import org.bson.Document;

import java.util.Date;
import java.util.concurrent.TimeUnit;

public class DurableChangeStreamConsumer {
    private static final String CONSUMER = "orders-sync-v1";

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("change_stream_lab");

            MongoCollection<Document> orders =
                db.getCollection("orders");

            // Lưu checkpoint dưới dạng BSON, không cắt _data.
            MongoCollection<BsonDocument> checkpoints =
                db.getCollection(
                    "consumerCheckpoints",
                    BsonDocument.class
                ).withWriteConcern(WriteConcern.MAJORITY);

            MongoCollection<BsonDocument> receipts =
                db.getCollection(
                    "processedChanges",
                    BsonDocument.class
                ).withWriteConcern(WriteConcern.MAJORITY);

            BsonDocument saved = checkpoints.find(
                Filters.eq("_id", CONSUMER)
            ).first();

            ChangeStreamIterable<Document> stream =
                orders.watch().maxAwaitTime(2, TimeUnit.SECONDS);

            if (saved != null
                    && saved.containsKey("resumeToken")
                    && saved.isDocument("resumeToken")) {
                stream = stream.resumeAfter(
                    saved.getDocument("resumeToken")
                );
            }

            try (MongoChangeStreamCursor<
                    ChangeStreamDocument<Document>> cursor =
                    stream.cursor()) {

                while (!Thread.currentThread().isInterrupted()) {
                    ChangeStreamDocument<Document> event =
                        cursor.tryNext();

                    if (event == null) {
                        // Không có event mới trong lần poll này.
                        // Không tự chế token bằng System.currentTimeMillis().
                        continue;
                    }

                    BsonDocument token = event.getResumeToken();
                    if (token == null) {
                        throw new IllegalStateException(
                            "Event không có resume token"
                        );
                    }

                    // Minh họa idempotent receipt:
                    // cùng event token chỉ tạo một record.
                    BsonDocument receipt = new BsonDocument()
                        .append("operationType",
                            new BsonString(
                                event.getOperationType().toString()
                            ))
                        .append("processedAt",
                            new BsonDateTime(
                                System.currentTimeMillis()
                            ));

                    receipts.updateOne(
                        Filters.eq("_id", token),
                        new BsonDocument(
                            "$setOnInsert", receipt
                        ),
                        new UpdateOptions().upsert(true)
                    );

                    // Checkpoint CHỈ sau khi xử lý thành công.
                    BsonDocument newCheckpoint = new BsonDocument()
                        .append("_id", new BsonString(CONSUMER))
                        .append("resumeToken", token)
                        .append("updatedAt",
                            new BsonDateTime(
                                System.currentTimeMillis()
                            ))
                        .append("state", new BsonString("RUNNING"))
                        .append("streamScope",
                            new BsonString("change_stream_lab.orders"));

                    checkpoints.replaceOne(
                        Filters.eq("_id", CONSUMER),
                        newCheckpoint,
                        new ReplaceOptions().upsert(true)
                    );

                    System.out.println(
                        "Đã checkpoint event: "
                            + event.getOperationType()
                    );
                }
            }
        }
    }
}
```

Mã cần dependency `mongodb-driver-sync` tương thích và `MONGODB_URI` trỏ tới replica set/sharded cluster hỗ trợ Change Stream. Không thể minh họa stream thật nếu chỉ chạy với standalone `mongod`.

### 23.2. Điểm cần hiểu trong ví dụ Java

1. **Checkpoint được đọc khi start:** nếu có token BSON, `resumeAfter(token)` được áp dụng trước khi mở cursor.
2. **Event token được giữ ở dạng `BsonDocument`:** không dùng `event.getDocumentKey()` thay token.
3. **Receipt có unique `_id` theo token:** ví dụ tránh tạo receipt trùng khi event replay.
4. **Checkpoint sau side effect:** nếu receipt write báo lỗi, code không đi tới bước lưu checkpoint.
5. **Write concern majority:** áp dụng cho collection receipt/checkpoint nhằm giảm nguy cơ ghi trạng thái xử lý bị rollback khi failover thông thường.
6. **Cursor đóng qua try-with-resources:** giảm rủi ro rò rỉ tài nguyên khi consumer dừng.

**Giới hạn cần nhấn mạnh:** vì receipt và checkpoint là hai thao tác khác nhau, crash vẫn có thể để lại một receipt đã tạo nhưng checkpoint chưa tiến; lần sau event sẽ đến lại và receipt update hoạt động idempotent. Nếu phần side effect thật là tăng tiền/counter hoặc gọi API ngoài, cần thiết kế xử lý trùng riêng hoặc transaction/outbox.

Ví dụ không có cơ chế leader lease, health reporting, backoff, xử lý PBRT lúc idle hoặc phân loại lỗi `history lost`. Đây là **mẫu cốt lõi về thứ tự persist**, không phải một daemon production có thể chạy không cần giám sát.

## 24. Java: phát hiện history lost và dừng tiến checkpoint

Phần điều phối lỗi trong service nên phân biệt những trường hợp:

```text
watch/resumeAfter
      |
      +-- thành công ---------> xử lý event
      |
      +-- transient error ----> retry/backoff rồi resume
      |
      +-- history lost -------> NEEDS_REBUILD
      |
      +-- invalid token -----> kiểm tra checkpoint/scope
      |
      +-- invalidate --------> xem startAfter và rebuild
```

Pseudo-code minh họa chính sách:

```java
// PSEUDOCODE: các method là hợp đồng ứng dụng cần tự triển khai.
try {
    runConsumerFromDurableCheckpoint();
} catch (ChangeStreamHistoryLostSignal error) {
    markConsumerState("NEEDS_REBUILD");
    stopPublishingStaleReadModel();
    notifyOperations(error);
    // Không xóa token và tự động xem mất lịch sử như bình thường.
    executeControlledRebuildAndCutover();
} catch (TransientStreamSignal error) {
    backoff();
    reopenFromLastDurableCheckpoint();
}
```

Hai tên exception `ChangeStreamHistoryLostSignal` và `TransientStreamSignal` ở đây **là lớp/predicate minh họa, không phải exception có sẵn của MongoDB Java Driver**. Trong mã thật, dùng các loại `MongoException` và thông tin error code/name/labels do driver cung cấp, đồng thời kiểm tra phiên bản. Không viết `catch (ChangeStreamHistoryLostSignal)` trong code production nếu ứng dụng chưa định nghĩa loại đó.

### Khi không rõ checkpoint write đã commit chưa

Một lệnh lưu checkpoint với `w:"majority"` có thể trả write concern timeout. Điều đó **không chứng minh checkpoint chưa được ghi**. Vì vậy:

- Không tiếp tục tiến tới event sau chỉ vì “chắc checkpoint đã lưu”.
- Đọc lại trạng thái checkpoint bằng mức nhất quán thích hợp hoặc retry theo chính sách write của ứng dụng.
- Side effect phải idempotent, vì consumer có thể phải replay event nếu trạng thái persisted chưa rõ.

Không nên gọi `startAfter` thay `resumeAfter` chỉ vì một network timeout: hai option có mục đích khác nhau.

## 25. Consumer nhiều instance: chỉ một bên được tiến checkpoint

Giả sử hai process A và B cùng chạy consumer `orders-sync-v1`:

```text
Process A: nhận E101 -------> lưu token T101
Process B: nhận E105 -------> lưu token T105
Process A: nhận E102 -------> lưu token T102

Checkpoint cuối = T102  (bị lùi do A)
```

Hai process cũng có thể phát event ra sink hai lần. Đây là lý do ngoài resume token còn cần **consumer ownership**:

- Dùng **distributed lease** với expiry, có kiểm soát tranh chấp.
- Dùng **fencing token/epoch** để consumer cũ không được ghi checkpoint sau khi quyền sở hữu chuyển.
- Lưu một phiên bản checkpoint và cập nhật theo điều kiện (*compare-and-swap*) khi phù hợp.
- Nếu cần scale theo partition, thiết kế nhiều stream/consumer checkpoint **độc lập**, không cho nhiều worker ghi chung một checkpoint mà không điều phối.

### Một ví dụ định dạng checkpoint có epoch

```javascript
{
  _id: "orders-sync-v1",
  resumeToken: { _data: "..." },
  ownerId: "instance-B",
  epoch: NumberLong(12),
  state: "RUNNING",
  updatedAt: ISODate("2026-11-14T00:00:00Z")
}
```

Đây là **document minh họa**, không phải checkpoint thực do server trả. Nếu ứng dụng triển khai fencing, lệnh cập nhật token phải xác nhận `ownerId` và `epoch` vẫn khớp, không chỉ dựa trên `_id`.

Tuyệt đối không so sánh chuỗi `resumeToken._data` bằng toán tử `>` hoặc `<` để quyết định checkpoint nào mới hơn. Token là opaque; phải kiểm soát **quyền ghi và thứ tự xử lý** bằng cơ chế ứng dụng.

## 26. Độ trễ và backpressure: giữ token sống được lâu dài

Giả sử tốc độ tạo sự kiện là 5.000 events/giây, nhưng consumer chỉ xử lý 3.000 events/giây. Mỗi giây backlog tăng khoảng 2.000 sự kiện. Dù không có lỗi network, sau một thời gian consumer có thể bị tụt khỏi phần lịch sử còn giữ trong oplog.

```text
Tốc độ nguồn:  5.000 events/s
Tốc độ sink:   3.000 events/s
               ---------------
Backlog tăng:  2.000 events/s

Nếu không cải thiện tốc độ hoặc đổi kiến trúc,
consumer lag tiếp tục tăng đến ngưỡng nguy hiểm.
```

Các cách kiểm soát:

1. **Đo processing lag và throughput** của consumer theo từng luồng.
2. **Giảm chi phí side effect:** xử lý batch có checkpoint an toàn, index sink và tránh lookup không cần thiết.
3. **Giảm volume event** bằng filter hợp lệ mà không làm mất những sự kiện nghiệp vụ bắt buộc.
4. **Tối ưu nguồn và sink:** I/O, network, pool kết nối, tài nguyên CPU.
5. **Tăng khả năng xử lý song song có điều phối**, nếu thứ tự và ownership cho phép.
6. **Tăng cửa sổ lịch sử** khi phù hợp với deployment, nhưng không dùng nó thay cho sửa backlog tăng vô hạn.
7. **Đệm sự kiện vào durable queue** khi cần tách tốc độ nguồn khỏi sink, kết hợp phương thức commit checkpoint sau khi sự kiện đã vào queue bền vững.

### Checkpoint theo batch: điều kiện an toàn

Có thể lưu checkpoint sau mỗi 100 event đã xử lý thay vì sau từng event:

```text
Nhận 100 event
      |
      v
Xử lý TẤT CẢ event 1..100 thành công
      |
      v
Lưu token của event 100
```

Nếu một event trong batch chưa xử lý thành công, không checkpoint vượt qua nó. Khi crash giữa batch, một số event đã xử lý có thể được phát lại; sink vẫn cần idempotency.

### Xử lý song song cần giữ safe commit frontier

Nếu E101 hoàn thành, E102 chưa xong, E103 đã xong, **không được checkpoint T103** chỉ vì event 103 kết thúc trước. Safe checkpoint chỉ có thể đi tới event cuối của **chuỗi liên tục đã xử lý xong** theo thứ tự stream:

```text
E101 [done] -- E102 [pending] -- E103 [done] -- E104 [done]
                 |
                 v
         safe checkpoint vẫn phải chờ E102
```

Với một stream có thứ tự, xử lý song song làm checkpoint khó hơn. Đối với người mới, xử lý tuần tự thường dễ chứng minh tính đúng hơn.

## 27. Mối quan hệ giữa fullDocument, delete và tái xây read model

Một change event `update` thường có `updateDescription` chứa những field thay đổi; khi cấu hình:

```javascript
db.orders.watch([], {
  fullDocument: "updateLookup"
})
```

server có thể lookup và trả thêm ảnh document hiện tại. Nhưng:

- `fullDocument` có thể không có trong một số tình huống, ví dụ document đã bị xóa trước khi lookup hoặc loại event không phù hợp.
- Với update có nhiều thao tác đồng thời, `fullDocument:"updateLookup"` không nên được hiểu là ảnh **chính xác tại thời điểm update event** trong mọi điều kiện.
- Với `delete`, event có `documentKey` để xác định document bị xóa; không có “document hiện tại” để lookup như một insert.
- Nếu cần **pre-image/post-image** chính xác cho nghiệp vụ kiểm toán, cần xem khả năng, cấu hình và retention của tính năng change stream pre/post images ở phiên bản đang dùng. Không suy ra oplog tự giữ mọi ảnh document vô hạn.

### Reconciliation theo trạng thái cuối

Đối với một search index:

```text
insert/update/replace -> cập nhật search document
delete                -> xóa search document
rebuild               -> quét trạng thái hiện tại của orders
                         rồi thay thế generation index
```

Thiết kế này có khả năng **đạt hội tụ về trạng thái hiện tại** khi có quy trình cutover đúng. Tuy nhiên nếu sink dùng event như một **ledger của từng biến động số dư**, snapshot hiện tại không thay được toàn bộ chuỗi insert/update/delete đã mất.

## 28. Checkpoint sau sự kiện đặc biệt và thay đổi namespace

Change Streams còn có thể trả những loại event liên quan đến namespace/topology tùy phạm vi watch và version. Trước khi checkpoint, consumer phải có chính sách xử lý rõ:

| Loại event | Câu hỏi cần quyết định |
| --- | --- |
| `insert` | Tạo read model record hay phát nghiệp vụ gì? |
| `update` | Dùng `updateDescription` hay lookup lại document? |
| `replace` | Thay toàn bộ trạng thái hay merge field? |
| `delete` | Loại record khỏi sink như thế nào? |
| `drop` / `rename` | Namespace/collection lifecycle ảnh hưởng sink ra sao? |
| `invalidate` | Đóng stream và chọn `startAfter` hoặc rebuild như thế nào? |
| Các event mới theo phiên bản | Consumer có chấp nhận/đánh dấu/loại bỏ có chủ đích không? |

Một consumer **chỉ hỗ trợ insert/update** mà mặc nhiên checkpoint qua `delete` có thể giữ record “ma” trong sink. Nếu nghiệp vụ cần phản ánh delete, đó là bỏ sót xử lý dù resume token vẫn hoạt động.

Việc cập nhật `pipelineVersion` khi thay filter hoặc cách xử lý là cần thiết để tránh tiếp tục một checkpoint cũ với ý nghĩa event mới không tương thích.

## 29. Cảnh báo và playbook vận hành

Trong môi trường production, nên có các cảnh báo:

| Metric / sự kiện | Mục đích |
| --- | --- |
| `lastDurableCheckpointAt` | Consumer có tiến checkpoint không? |
| `lastEventClusterTime` | Đo chênh lệch thời gian xử lý so với nguồn |
| `oplogWindowEstimate` | Khoảng lịch sử còn có thể phục vụ |
| `consumerLag` | Có nguy cơ vượt quá cửa sổ oplog không? |
| `resumableErrorCount` | Network/failover có đang lặp không? |
| `nonResumableErrorCount` | Phát hiện history lost và lỗi token |
| `rebuildState` | Consumer đang phục vụ dữ liệu mới hay đang tái đồng bộ? |
| `pendingSinkWrites` | Có backpressure/điểm nghẽn side effect không? |
| `checkpointWriteConcernErrors` | Checkpoint bền vững có đang bị lỗi không? |
| `ownershipEpoch` | Phát hiện leader cũ viết đè trạng thái |

### Một playbook khi có history lost

1. **Xác nhận loại lỗi**, giữ nguyên log/token/namespace/phiên bản để chẩn đoán.
2. **Chặn tiến checkpoint sai**, không cho consumer khác mở stream mới từ hiện tại mà âm thầm bỏ lịch sử.
3. **Phân loại sink**: trạng thái hiện tại có thể rebuild hay cần lưu đầy đủ mọi event?
4. **Chọn phương án recovery**: quiesce writers và cutover, hoặc stream-first cùng durable staging/snapshot nhất quán.
5. **Rebuild trong generation mới** khi có thể; không phục vụ dữ liệu đang xây dở.
6. **Xác lập resume anchor mới**, đảm bảo không có khoảng trống giữa snapshot và live stream.
7. **Đối soát kết quả**, số lượng document và các invariant nghiệp vụ trước khi đánh dấu healthy.
8. **Quan sát lag sau recovery**, đảm bảo stream mới không lại tụt khỏi oplog.
9. **Điều tra nguyên nhân gốc**: consumer bị dừng quá lâu, sink quá chậm, oplog window quá ngắn, tăng tải đột biến hoặc lỗi checkpoint.

Các bước này không phải hướng dẫn tắt cluster hay xóa oplog. Thay đổi cấu hình replica set và thao tác recovery nguy hiểm phải tuân thủ kế hoạch vận hành, không áp dụng trực tiếp lên production chỉ từ ví dụ bài học.

## 30. Lỗi thường gặp khi lưu token và resume

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Restart luôn bắt đầu từ event mới | Chỉ giữ token trong RAM hoặc không đọc checkpoint | Persist toàn bộ token và nạp lại khi start |
| Consumer bỏ qua một event | Checkpoint trước khi side effect hoàn tất | Xử lý trước, checkpoint sau |
| Một event gây hai lần tính tiền/counter | Replay sau crash, side effect không idempotent | Dedupe, transactional sink, operation ID |
| Resume không tìm lại được lịch sử | Oplog entries cần thiết đã bị ghi đè | Dừng, đánh dấu history lost, rebuild/reconcile |
| Retry `resumeAfter` mãi không thành | Lỗi non-resumable, token cũ không còn lịch sử | Không retry vô hạn; chuyển recovery |
| Resume token bị từ chối | Token bị sửa, mất kiểu BSON hoặc scope không phù hợp | Lưu raw BSON, kiểm tra scope/pipeline/version |
| Resume sau `invalidate` lỗi | Dùng `resumeAfter` qua invalidate | Xem `startAfter` và lifecycle/rebuild |
| Stream mới chạy nhưng sink thiếu dữ liệu | Snapshot-then-watch có gap hoặc bỏ checkpoint cũ | Dùng safe cutover/reconciliation |
| Token bị ghi lùi | Hai consumers ghi chung checkpoint không điều phối | Fencing, lease, epoch, CAS |
| `_id` trong stream bị thiếu | Pipeline `$project` xóa token | Giữ nguyên `event._id` |
| Checkpoint không tiến khi không có event | Chỉ lưu event token, chưa dùng PBRT | Cân nhắc persist PBRT an toàn khi idle |
| Checkpoint tiến nhanh hơn sink | Dùng token mới nhất từ cursor khi còn event pending | Chỉ checkpoint safe processed frontier |
| `fullDocument` của update không như mong đợi | Lookup ảnh hiện tại sau update, có thể đã thay đổi | Dùng updateDescription hoặc dữ liệu/pre-post images phù hợp |
| Query trên `documentKey` không xác định vị trí | Lưu document ID thay cho resume token | Sử dụng event `_id` |
| Mất event trong báo cáo kiểm toán | Oplog không phải archive vĩnh viễn | Dùng durable ledger/event log độc lập |
| Consumer lag tăng vô hạn | Sink throughput thấp hơn nguồn | Đo backlog, giảm chi phí, mở rộng có điều phối |

## 31. Bài tập thực hành và đáp án

### Bài 1. Chọn đúng resume token

Một change event có:

```javascript
{
  _id: { _data: "opaque-token" },
  documentKey: { _id: "order-1001" },
  operationType: "update"
}
```

Bạn phải lưu thông tin nào để sau restart có thể tiếp tục từ event kế tiếp?

**Đáp án:** Lưu **toàn bộ `event._id`** dưới dạng BSON document. `documentKey._id` là ID document nghiệp vụ, không phải vị trí stream.

### Bài 2. Điểm checkpoint sau xử lý

Consumer đã xử lý E1, E2, nhưng đang xử lý E3 thì crash. Token cuối được lưu bền vững là T2. Khi restart sẽ có hành vi gì?

**Đáp án:** `resumeAfter(T2)` có thể trả E3 trở đi nếu lịch sử còn. Nếu E3 đã tạo một phần side effect trước crash, ứng dụng phải xử lý trùng/idempotency. Không được tự lưu T3 khi E3 chưa hoàn tất.

### Bài 3. Tại sao không checkpoint trước?

Consumer nhận E10, lưu T10, rồi crash trước khi gửi event sang sink. Sau restart, dùng `resumeAfter(T10)`. Vì sao sink có thể mất E10?

**Đáp án:** Resume bắt đầu **sau E10**, nên E10 sẽ không được phát lại. Đó là lỗi thứ tự giữa side effect và checkpoint.

### Bài 4. Oplog history lost

Consumer ngừng ba ngày; khi mở `resumeAfter(oldToken)`, server báo history lost. Có thể giải quyết bằng cách lặp lại `resumeAfter(oldToken)` thêm 1.000 lần không?

**Đáp án:** Không. Phần lịch sử cần thiết đã mất khỏi oplog. Cần chuyển sang trạng thái recovery, xác định có thể rebuild từ trạng thái hiện tại hay phải khôi phục sự kiện từ nguồn archive khác.

### Bài 5. Snapshot-to-stream gap

Bạn quét collection để rebuild read model từ 10:00 đến 10:05, rồi mở Change Stream lúc 10:06. Một update diễn ra lúc 10:03 sau khi document đã được quét. Vấn đề gì xảy ra?

**Đáp án:** Update lúc 10:03 có thể không xuất hiện trong snapshot và cũng nằm trước vị trí stream mới, dẫn đến **gap**. Cần an toàn điểm chuyển tiếp bằng write fence/barrier hoặc stream-first + durable staging cùng thuật toán snapshot/reconcile phù hợp.

### Bài 6. `resumeAfter` và `startAfter`

Collection bị drop, stream nhận một `invalidate` rồi đóng. Có nên dùng `resumeAfter(invalidateToken)` để tiếp tục qua invalidate không?

**Đáp án:** Không. `resumeAfter` không được dùng qua invalidate. `startAfter` hỗ trợ mở stream mới sau invalidate trong các trường hợp được phép, nhưng còn phải giải quyết lifecycle và trạng thái dữ liệu của collection.

### Bài 7. PBRT và event đang xử lý dở

Cursor trả PBRT tiến tới vị trí sau E20, nhưng sink mới xử lý thành công đến E18; E19 chưa xong. Có thể lưu PBRT ngay không?

**Đáp án:** Không. Checkpoint vượt quá E19 có thể làm bỏ qua E19 sau crash. Chỉ persist token ở **safe frontier** của chuỗi event đã xử lý hoàn tất.

### Bài 8. Có hai consumer dùng một checkpoint

Worker A ghi T100, worker B ghi T110, rồi A ghi T101. Vấn đề gì? Giải pháp?

**Đáp án:** Checkpoint bị lùi và side effects có thể trùng. Cần một owner/lease/fencing epoch hoặc phân vùng consumer với checkpoint độc lập; không dùng so sánh chuỗi token để quyết định thứ tự.

### Bài 9. Sự kiện thiếu trong audit

Một hệ thống phải lưu **mọi lần** user sửa đơn hàng. Consumer bị history lost, nhưng bạn có thể `find()` toàn bộ document hiện tại. Có thể dựng lại mọi event đã xảy ra chỉ từ kết quả `find()` không?

**Đáp án:** Không. Một document có thể đổi giá trị nhiều lần rồi quay lại trạng thái cũ. Cần nguồn lịch sử bền vững khác; snapshot hiện tại chỉ hỗ trợ tái tạo **trạng thái cuối**, không tái tạo đầy đủ mọi biến động.

### Bài 10. Điểm mạnh/yếu của `updateLookup`

Consumer dùng `fullDocument:"updateLookup"` và nhận update event. Có thể mặc định `fullDocument` luôn là ảnh chính xác ngay tại thời điểm thao tác update vừa diễn ra không?

**Đáp án:** Không. Lookup có thể thấy trạng thái mới hơn nếu document tiếp tục thay đổi, hoặc trả null nếu document không còn. Cần dùng `updateDescription` hay cơ chế ảnh dữ liệu phù hợp với yêu cầu nghiệp vụ.

### Bài 11. Write concern của checkpoint

Ứng dụng cập nhật sink bền vững, rồi lưu token trong checkpoint collection chỉ với `w:1`. Sau failover, checkpoint rollback nhưng sink vẫn giữ kết quả. Điều gì xảy ra?

**Đáp án:** Consumer có thể replay những event đã xử lý vì checkpoint lùi; cần sink idempotent. Dùng write concern majority cho checkpoint giúp giảm một lớp rủi ro rollback trong failover thông thường, nhưng không loại bỏ nhu cầu xử lý trùng.

### Bài 12. Luồng rảnh không có event

Consumer hoạt động tốt nhưng một ngày không có thay đổi. Token event cuối là của hôm qua. Có cách nào checkpoint tiến khi stream rảnh không?

**Đáp án:** Có thể dùng **post-batch resume token** qua API phù hợp của server/driver nếu hiểu semantics và không còn event chưa xử lý. Không tự sinh token từ đồng hồ hoặc clusterTime đoán.

### Bài 13. Filter thay đổi ở bản deploy mới

Consumer phiên bản 1 chỉ nhận insert/update, phiên bản 2 thêm delete. Bạn có thể lấy token cũ và mặc nhiên kết luận mọi delete cũ đã được xử lý không?

**Đáp án:** Không. Các delete bị lọc ở pipeline cũ có thể không có side effect tương ứng trong sink. Cần đánh giá ảnh hưởng đổi filter, version checkpoint và có thể rebuild/reconciliation để bảo đảm trạng thái đích.

### Bài 14. Đọc cảnh báo lag

Mỗi giây source tạo 8.000 thay đổi, consumer xử lý 6.000. Sau 10 phút, backlog tăng bao nhiêu event theo mô hình lý tưởng không có thay đổi khác?

**Đáp án:** Chênh lệch 2.000 events/giây. Trong 600 giây, backlog tăng **1.200.000 events**. Nếu không tăng throughput hoặc đổi kiến trúc, consumer ngày càng gần nguy cơ vượt oplog window.

## 32. Mẫu runbook rút gọn cho đội vận hành

Khi một consumer báo lỗi resume, thay vì xóa token và restart bằng mọi giá, nên ghi nhận:

```text
CONSUMER_ID:
STREAM_SCOPE:
PIPELINE_VERSION:
CHECKPOINT_UPDATED_AT:
LAST_DURABLE_RESUME_TOKEN:
LAST_EVENT_CLUSTER_TIME:
ERROR_NAME / ERROR_CODE / ERROR_LABELS:
OPLOG_WINDOW_OBSERVED:
SOURCE_REPLICA_SET / SHARDS:
SINK_CONSISTENCY_STATUS:
RECOVERY_MODE:
RECOVERY_GENERATION:
NEW_ANCHOR:
CUTOVER_APPROVED_BY:
```

Những trường này không phải tham số bắt buộc của MongoDB; chúng là **thông tin vận hành** để đảm bảo có thể giải thích vì sao một consumer tiếp tục hoặc phải xây lại.

### Các dấu hiệu có thể đóng sự cố

- Đã xác định được nguyên nhân lỗi: transient, invalid token, invalidate hay oplog history lost.
- Có checkpoint mới **được lưu bền vững** và thuộc đúng stream scope/pipeline.
- Sink đã rebuild/reconcile theo một quy trình **không có gap hoặc đã công bố rõ giới hạn mất dữ liệu**.
- Consumer đang xử lý và checkpoint tiến theo đúng thứ tự.
- Lag giảm về ngưỡng an toàn so với cửa sổ oplog đang quan sát.
- Không có owner cũ tiếp tục ghi checkpoint hoặc side effect chồng chéo.
- Các chỉ số/invariant nghiệp vụ chính được đối chiếu ở mức cần thiết.

## 33. Tổng kết

**Resume token** là điểm tựa để một Change Stream consumer tiếp tục sau restart, nhưng nó chỉ hữu ích khi **lịch sử cần thiết vẫn còn trong oplog** và token tương thích với stream. Hãy giữ nguyên **BSON event `_id`**, lưu checkpoint ở kho bền vững với write concern phù hợp, đồng thời lưu thêm stream scope và phiên bản pipeline để tránh nhầm token.

Thứ tự an toàn mặc định là **xử lý event thành công → persist checkpoint**. Thứ tự này có thể tạo replay sau crash, nên sink phải **idempotent**; nếu muốn side effect cùng checkpoint nguyên tử, cần một transaction/sink protocol hỗ trợ. Với consumer song song, chỉ checkpoint đến **frontier liên tục đã xử lý hoàn tất** và cần cơ chế ownership/fencing để ngăn ghi lùi.

Khi lịch sử oplog đã mất, **retry cùng token không phục hồi được sự kiện đã bị xóa**. Không âm thầm bỏ checkpoint rồi mở stream từ hiện tại, bởi điều đó có thể tạo khoảng trống không nhìn thấy. Thay vào đó, phân loại yêu cầu nghiệp vụ: **rebuild trạng thái hiện tại** với một safe cutover giữa snapshot và live stream, hoặc **khôi phục sự kiện từ archive bền vững** nếu bắt buộc giữ toàn bộ lịch sử. Kết hợp monitoring lag/oplog window, quy trình recovery rõ ràng và xử lý idempotent là nền tảng để Change Stream vận hành đáng tin cậy.

### Tài liệu tham khảo MongoDB

- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — Resume a Change Stream](https://www.mongodb.com/docs/manual/changeStreams/#resume-a-change-stream)
- [MongoDB Manual — Change Events](https://www.mongodb.com/docs/manual/reference/change-events/)
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/usage-examples/watch/)

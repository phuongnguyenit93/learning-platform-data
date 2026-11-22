# Kiểm soát kích thước lô ghi và giới hạn yêu cầu khi thêm document vào MongoDB

## 1. Vì sao phải kiểm soát kích thước lô ghi?

Thêm một document vào MongoDB thường bắt đầu bằng **insertOne()**. Khi cần thêm hàng nghìn hoặc hàng triệu document, ứng dụng có thể dùng **insertMany()** hoặc **bulkWrite()** để giảm số lần trao đổi với database. Thay vì gửi từng document trong một vòng giao tiếp mạng, một lời gọi có thể truyền nhiều thao tác ghi.

Nhưng **lô càng lớn không đồng nghĩa hệ thống càng nhanh**. MongoDB có giới hạn với kích thước document BSON, số thao tác trong một write batch và kích thước thông điệp giữa client với server. Ngoài các ngưỡng của MongoDB, ứng dụng còn chịu giới hạn bộ nhớ, kết nối, thời gian chờ, thông lượng đĩa và yêu cầu phản hồi nghiệp vụ.

Ví dụ một dịch vụ nhập danh mục sản phẩm nhận 2 triệu bản ghi từ file:

~~~text
CSV / JSONL / API stream
           |
           v
     Parser + validation
           |
           v
   Bounded batch builder
    - count threshold
    - BSON bytes threshold
    - optional time threshold
           |
           v
       MongoDB Driver
    - enforce server limits
    - encode and split batches
           |
           v
         mongod
    - validate and execute
    - acknowledge per write concern
           |
           v
   Report success / partial errors
~~~

Nếu ứng dụng đọc toàn bộ file vào RAM rồi gọi một lần **insertMany()**, nó có thể bị **OutOfMemoryError** trước khi driver chia request, hoặc phải chờ quá lâu mới biết một phần dữ liệu lỗi. Một cơ chế chia lô có giới hạn rõ ràng giúp kiểm soát bộ nhớ, giảm thời gian giữ tài nguyên và xử lý lỗi theo từng phần.

### Phân biệt ba đơn vị

- **Document:** một bản ghi BSON được lưu trong collection; có giới hạn kích thước riêng.
- **Logical batch:** tập thao tác mà ứng dụng truyền cho một lần gọi **insertMany()** hoặc **bulkWrite()**. Đây có thể là hàng trăm nghìn thao tác.
- **Wire batch / command:** nhóm thao tác thực sự được driver mã hóa thành một thông điệp gửi server. Driver có thể tách một logical batch thành **nhiều** request nhỏ hơn.

Đừng nhìn một lời gọi **insertMany(120000 documents)** và suy ra server nhận đúng một command chứa 120.000 document. Driver MongoDB thường chia theo các giới hạn server đã công bố.

## 2. Các giới hạn quan trọng cần phân biệt

Các bản MongoDB thông dụng công bố ba thông số sau trong thông tin kết nối/handshake:

| Thông số | Giá trị thường gặp | Ý nghĩa |
|---|---:|---|
| **maxBsonObjectSize** | **16.777.216 byte (16 MiB)** | Kích thước tối đa của **một document BSON** thông thường được phép lưu. |
| **maxWriteBatchSize** | **100.000 thao tác** | Số thao tác ghi tối đa trong **một write command batch** mà server hỗ trợ. |
| **maxMessageSizeBytes** | **48.000.000 byte** | Giới hạn kích thước một thông điệp MongoDB wire protocol; bao gồm overhead của message/command, không chỉ document payload. |

Đây là những ngưỡng kỹ thuật tiêu biểu, **không phải mức batch tối ưu trong ứng dụng**. Khi làm việc với deployment cụ thể, driver sẽ dựa vào thông tin server công bố. Không hardcode giả định rằng mọi topology và mọi phiên bản đều giống nhau mà bỏ qua những giá trị thực tế đã được đàm phán.

Lưu ý đơn vị:

- **16 MiB = 16 × 1024 × 1024 = 16.777.216 byte**.
- **48.000.000 byte** là khoảng **45,8 MiB**, không phải 48 MiB.
- Số **100.000** giới hạn **số thao tác**, không có nghĩa cứ đủ 100.000 document thì chắc chắn gói dữ liệu vẫn nhỏ hơn giới hạn wire message.

### 2.1. Lấy giới hạn từ server

Trong **mongosh**:

~~~javascript
const hello = db.adminCommand({ hello: 1 });

printjson({
  maxBsonObjectSize: hello.maxBsonObjectSize,
  maxMessageSizeBytes: hello.maxMessageSizeBytes,
  maxWriteBatchSize: hello.maxWriteBatchSize
});
~~~

Ví dụ kết quả ở một server có giá trị thông dụng:

~~~javascript
{
  maxBsonObjectSize: 16777216,
  maxMessageSizeBytes: 48000000,
  maxWriteBatchSize: 100000
}
~~~

Thông tin này là một phần bề mặt giao tiếp của MongoDB. Driver thường tự đọc và quản lý các giới hạn khi chọn server. Đối với cluster có nhiều node hoặc qua **mongos**, cần xem đặc tính của topology đích; không tự coi một lệnh kiểm tra là nguồn duy nhất cho mọi node.

### 2.2. Các tầng giới hạn khác ngoài MongoDB

Một request ghi có thể bị chặn **trước khi tới server**:

| Tầng | Giới hạn có thể gặp | Dấu hiệu |
|---|---|---|
| **REST API / reverse proxy / API gateway** | Giới hạn HTTP body, timeout, số request đồng thời. | HTTP 413, 429, 504 hoặc lỗi gateway khác tùy cấu hình. |
| **Ứng dụng Java** | Heap, GC, queue, thread, connection pool, thời gian xử lý. | Tăng heap, GC pause, OutOfMemoryError, queue dài. |
| **MongoDB Driver** | Wire batch constraints, encoding, connection pool, timeout. | Driver chia lô, chờ connection, ném exception. |
| **MongoDB Server** | BSON size, command/message size, index/validation, tài nguyên CPU/I/O. | Write error, độ trễ, timeout, thiếu dung lượng. |
| **Replica set / sharded cluster** | Majority acknowledgment, phân bố shard, network giữa node. | Write latency tăng, throttling, write concern error. |

**Giới hạn HTTP request không phải giới hạn MongoDB wire message**. Ví dụ API nhận một body JSON 30 MiB rồi Java phân tách thành các thao tác MongoDB thì cả hai tầng phải được cấu hình phù hợp, và 30 MiB JSON cũng không chắc bằng 30 MiB BSON.

## 3. Giới hạn kích thước một document BSON

MongoDB đặt giới hạn thông dụng **16 MiB cho mỗi BSON document**. Giới hạn bao gồm không chỉ dữ liệu dễ nhìn thấy, mà cả biểu diễn BSON của field, tên field, giá trị và phần overhead cấu trúc.

Ví dụ document có một field chứa chuỗi rất lớn:

~~~javascript
const largeDocument = {
  sourceId: "IMPORT-123",
  payload: "x".repeat(10 * 1024 * 1024)
};
~~~

Chuỗi trên có khoảng 10 MiB ký tự ASCII, nhưng **kích thước BSON của cả document lớn hơn kích thước chuỗi** vì có tên field và metadata BSON. Với ký tự đa byte trong UTF-8, chênh lệch giữa **số ký tự** và **số byte** còn rõ hơn.

### 3.1. Đừng đo bằng chiều dài chuỗi JSON

~~~javascript
const doc = {
  name: "Sản phẩm thử nghiệm",
  quantity: NumberInt(10),
  createdAt: new Date()
};

// JSON string length không phải kích thước BSON.
print(JSON.stringify(doc).length);

// Trong mongosh, đọc kích thước BSON được mã hóa.
print(Object.bsonsize(doc));
~~~

**JSON.stringify(doc).length** đếm số code unit của chuỗi JSON trong JavaScript, không đo byte BSON thực tế. Nó bỏ qua khác biệt giữa BSON và JSON, cũng như các giá trị BSON có kiểu đặc biệt.

Đối với document đã được lưu vào collection, có thể dùng biểu thức aggregation **$bsonSize**:

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 1,
      bsonBytes: { $bsonSize: "$$ROOT" }
    }
  },
  { $sort: { bsonBytes: -1 } },
  { $limit: 10 }
]);
~~~

Kết quả trả kích thước BSON của từng document được đo ở phía server. Với collection lớn, pipeline này có thể cần đọc nhiều dữ liệu; nên kiểm soát phạm vi ở production. Công cụ đo **document size** cũng không tự tính đầy đủ overhead của cả **wire message**.

### 3.2. Vì sao document lớn gây vấn đề ngay cả khi dưới 16 MiB?

Một document hợp lệ về kích thước vẫn có thể gây nhiều chi phí:

- Đọc document phải chuyển nhiều byte qua mạng.
- Truy vấn trả về document lớn có thể chiếm nhiều RAM của server và client.
- Thay đổi một trường có thể làm tăng áp lực cache, storage và replication.
- Nhiều document lớn trong một batch làm tổng payload nhanh chạm giới hạn message.
- Array tăng liên tục có thể đẩy document vượt ngưỡng ở lần cập nhật sau.

Ví dụ không nên nhúng toàn bộ lịch sử sự kiện không giới hạn:

~~~javascript
{
  orderId: "ORD-100",
  events: [
    /* hàng trăm nghìn sự kiện có thể làm document phình to */
  ]
}
~~~

Nếu lịch sử tiếp tục tăng, nên tách sang collection **order_events**, liên kết qua **orderId** và tạo index phù hợp. Không thể giải quyết document vượt 16 MiB chỉ bằng cách giảm số document trong một batch.

### 3.3. Cần làm gì với một record quá lớn?

Tùy dữ liệu:

1. **Chuẩn hóa mô hình document:** tách array, blob hoặc lịch sử không giới hạn thành collection khác.
2. **Lưu file lớn riêng:** sử dụng **GridFS** khi cần lưu file trong MongoDB, hoặc object storage khi phù hợp kiến trúc.
3. **Giảm dữ liệu trùng lặp:** không nhúng nguyên một cấu trúc rất lớn vào mỗi document khi chỉ cần reference.
4. **Báo lỗi đầu vào rõ ràng:** nếu nghiệp vụ quy định record phải nhỏ, từ chối record vượt ngưỡng mềm trước khi gửi đến server.

**GridFS** chia file thành nhiều chunk/document và duy trì metadata; nó không “nới” giới hạn 16 MiB của một BSON document bất kỳ.

## 4. Giới hạn số thao tác trong một write batch

**maxWriteBatchSize** giới hạn số thao tác được đưa vào một write command batch tại server. Giá trị thường gặp là **100.000**. Driver tuân theo giới hạn này và có thể tự chia các thao tác thành nhiều request.

Ví dụ:

~~~javascript
const docs = [];

for (let i = 0; i < 120000; i++) {
  docs.push({
    sourceId: "ROW-" + i,
    kind: "IMPORT",
    value: i
  });
}

db.import_rows.insertMany(docs, { ordered: false });
~~~

Về mặt lời gọi API, đây là một **insertMany 120.000 document**. Về mặt wire protocol, driver phải tuân theo các giới hạn và có thể phát nhiều batch. Một ứng dụng Java cũng tương tự.

**Đừng chạy ví dụ 120.000 document trong shell hoặc production nếu chưa kiểm soát dung lượng, thời gian và bộ nhớ.** Ví dụ trên để minh họa sự khác biệt giữa logical batch và wire batches.

### 4.1. Có thể chạm giới hạn byte trước giới hạn count

Giả sử trung bình mỗi document được mã hóa thành **50 KiB**. Một batch **1.000 document** có payload khoảng:

\[
1.000 \times 50\ \text{KiB}
= 50.000\ \text{KiB}
\approx 48{,}83\ \text{MiB}
\]

Mức này đã lớn hơn giới hạn wire message thông dụng **48.000.000 byte** ngay cả trước khi tính overhead command. Vì vậy dù số lượng 1.000 nhỏ hơn 100.000 rất nhiều, driver vẫn phải chia theo **kích thước byte**.

Ngược lại, 100.000 document rất nhỏ có thể chạm **count limit** trước giới hạn byte.

### 4.2. Một request gửi nhiều thao tác không biến thành một transaction

**insertMany()** hoặc **bulkWrite()** không mặc định bảo đảm tính nguyên tử của **toàn bộ lô**:

- MongoDB bảo đảm tính nguyên tử của một thao tác ghi trên **một document** theo semantics tương ứng.
- Trong một batch có nhiều document, một số ghi có thể thành công và một số có thể thất bại.
- Một bulk write có thể được driver chia thành nhiều write commands.
- **ordered/unordered** ảnh hưởng thứ tự xử lý và hành vi khi gặp lỗi, không tự biến toàn bộ batch thành đơn vị all-or-nothing.

Nếu nghiệp vụ thực sự yêu cầu nhiều document thành một đơn vị giao dịch, cần cân nhắc **multi-document transaction** trong topology hỗ trợ. Transaction có chi phí và giới hạn riêng; nó không bỏ qua giới hạn BSON mỗi document hoặc mọi giới hạn vận hành.

## 5. Giới hạn kích thước thông điệp MongoDB

**maxMessageSizeBytes** là giới hạn ở tầng wire protocol. Giá trị thông dụng **48.000.000 byte** áp dụng cho thông điệp trao đổi với MongoDB; không thể chỉ lấy tổng kích thước text của một mảng JSON để tính chính xác.

Một write command còn có:

- command name và collection/database metadata;
- các tùy chọn như **ordered**, **writeConcern**, session/transaction metadata khi có;
- encoding của BSON array hoặc document sequence;
- header/protocol overhead và các trường khác tùy loại request.

Vì vậy trong thiết kế ứng dụng, nên có **khoảng đệm an toàn** thay vì tự nhắm đúng 48.000.000 byte cho phần dữ liệu document.

### 5.1. Giới hạn wire protocol và mức tối ưu hiệu năng là hai việc khác nhau

Một batch 20 MiB có thể hợp lệ về protocol nhưng vẫn gây:

- latency cao khi gửi, mã hóa và chờ acknowledge;
- áp lực CPU/GC trên JVM khi tạo và giữ danh sách document;
- hàng đợi lớn khi driver thiếu connection sẵn có;
- dao động p95/p99 latency khi I/O bận;
- chi phí xử lý lỗi lớn nếu nhiều document có lỗi validation/duplicate key.

Vì vậy **batch size vận hành** thường cần nhỏ hơn rất nhiều so với giới hạn server. Một điểm khởi đầu có thể là vài trăm đến vài nghìn document với ngưỡng byte thấp hơn đáng kể giới hạn wire message, rồi đo thực tế. Các con số này là **tham số tuning**, không phải mặc định bắt buộc của MongoDB.

## 6. Driver tự chia batch: điều nó làm và điều nó không làm

MongoDB Drivers lấy thông tin giới hạn server và thực hiện encoding/chia request sao cho không vi phạm giao thức. Điều này có ích khi code gọi **insertMany()** hoặc **bulkWrite()** với một logical batch lớn.

Tuy nhiên, driver tự chia không có nghĩa ứng dụng được phép:

1. Đọc hàng triệu document vào một **List** duy nhất không giới hạn.
2. Đẩy vô hạn request bất đồng bộ làm tràn hàng đợi.
3. Coi một lần gọi API là một transaction atomic.
4. Bỏ qua duplicate key, validation error, write concern error hoặc timeout.
5. Coi retry toàn bộ danh sách là an toàn trong mọi trường hợp.

~~~text
Ứng dụng tạo List<Document> 2.000.000 phần tử
                    |
           RAM đã bị tiêu thụ
                    |
             driver nhận List
                    |
          chia thành nhiều commands
                    |
               MongoDB server
~~~

Driver giải quyết giới hạn **wire command**. Ứng dụng vẫn phải giải quyết **memory/backpressure**, xử lý lỗi theo từng nhóm và semantics của nghiệp vụ.

### 6.1. Không tự lắp command vượt giới hạn

Sử dụng API chính thức của driver như **insertMany** và **bulkWrite** thay vì tự tạo một command BSON khổng lồ để gửi bằng **runCommand**, trừ khi đã hiểu rõ giao thức và nhu cầu đặc biệt. Driver có nhiều logic phụ trợ như định tuyến, retry, session và tách lô.

## 7. Lựa chọn giữa insertOne, insertMany và bulkWrite

| API | Đơn vị cung cấp | Dùng khi nào | Lưu ý |
|---|---|---|---|
| **insertOne(document)** | Một document. | API tạo một thực thể riêng lẻ; đơn giản, dễ báo lỗi. | Mỗi request có overhead giao tiếp; throughput thấp hơn nếu gửi tuần tự hàng triệu lần. |
| **insertMany(documents)** | Nhiều insert. | Nạp dữ liệu, import, ghi danh sách document đồng nhất về thao tác. | Có ordered/unordered, có thể thành công một phần. |
| **bulkWrite(models)** | Nhiều loại write model. | Cần kết hợp insert, update, replace, delete theo workflow. | Lỗi và thứ tự phức tạp hơn; không phải transaction tự động. |

Ví dụ thêm ba document:

~~~javascript
db.import_rows.insertMany(
  [
    { sourceId: "A-01", quantity: NumberInt(1) },
    { sourceId: "A-02", quantity: NumberInt(2) },
    { sourceId: "A-03", quantity: NumberInt(3) }
  ],
  { ordered: true }
);
~~~

Ví dụ bulkWrite:

~~~javascript
db.import_rows.bulkWrite(
  [
    {
      insertOne: {
        document: { sourceId: "B-01", quantity: NumberInt(3) }
      }
    },
    {
      updateOne: {
        filter: { sourceId: "A-01" },
        update: { $inc: { quantity: 1 } }
      }
    },
    {
      replaceOne: {
        filter: { sourceId: "A-02" },
        replacement: {
          sourceId: "A-02",
          quantity: NumberInt(99)
        }
      }
    }
  ],
  { ordered: true }
);
~~~

Một **updateOne** hoặc **replaceOne** trong bulkWrite không bắt buộc làm kích thước document sau cập nhật nhỏ đi. Nếu kết quả vượt giới hạn document BSON, MongoDB có thể từ chối thao tác.

## 8. Ordered và unordered ảnh hưởng đến xử lý lỗi

### 8.1. Ordered: dừng khi gặp write error theo thứ tự

Mặc định, **insertMany** có **ordered: true**. Driver/server cố gắng thực thi theo thứ tự và khi gặp lỗi ghi như duplicate key sẽ không tiếp tục những thao tác còn lại theo quy tắc ordered.

Ví dụ đã có unique index:

~~~javascript
db.batch_orders.createIndex({ orderCode: 1 }, { unique: true });

db.batch_orders.insertOne({
  orderCode: "ORD-001",
  amount: NumberDecimal("10.00")
});

db.batch_orders.insertMany(
  [
    { orderCode: "ORD-002", amount: NumberDecimal("20.00") },
    { orderCode: "ORD-001", amount: NumberDecimal("30.00") },
    { orderCode: "ORD-003", amount: NumberDecimal("40.00") }
  ],
  { ordered: true }
);
~~~

Ở đây **ORD-002** có thể được thêm thành công trước khi thao tác thứ hai gây duplicate key. Sau lỗi đó, thao tác **ORD-003** không được tiếp tục trong chế độ ordered thông thường.

**Lô không được rollback toàn bộ**: ORD-002 vẫn có thể tồn tại.

### 8.2. Unordered: tiếp tục các thao tác có thể thực hiện

~~~javascript
db.batch_orders.insertMany(
  [
    { orderCode: "ORD-004", amount: NumberDecimal("20.00") },
    { orderCode: "ORD-001", amount: NumberDecimal("30.00") },
    { orderCode: "ORD-005", amount: NumberDecimal("40.00") }
  ],
  { ordered: false }
);
~~~

Với **ordered: false**, MongoDB có thể tiếp tục xử lý các thao tác khác dù có duplicate key ở một phần tử. Những thao tác thành công và thất bại phải được theo dõi riêng. **Không nên giả định thứ tự thực thi hoặc thứ tự hoàn thành** giống danh sách đầu vào, nhất là trong môi trường sharded.

### 8.3. Tư duy chọn mode

| Trường hợp | Thường cân nhắc |
|---|---|
| Bước sau phụ thuộc chặt vào bước trước và phải dừng khi lỗi. | **ordered: true**, nhưng không coi là transaction. |
| Import nhiều bản ghi độc lập, muốn tiếp tục xử lý record hợp lệ khi một record lỗi. | **ordered: false** + báo cáo lỗi từng phần tử. |
| Nghiệp vụ cần hoặc tất cả cùng thành công hoặc cùng thất bại. | Thiết kế transaction hoặc workflow bù trừ riêng. |

Nếu cần toàn bộ batch “all-or-nothing”, đặt **ordered: true** là chưa đủ.

## 9. Thiết kế ngưỡng batch ở tầng ứng dụng

Một batch builder thực tế nên giới hạn ít nhất theo **số document** và **tổng byte BSON ước tính/đo được**. Với các dòng dữ liệu đến chậm, có thể bổ sung **thời gian chờ tối đa** để tránh giữ batch quá lâu.

### 9.1. Ba ngưỡng mềm

Ví dụ một ứng dụng tự chọn:

~~~text
TARGET_MAX_DOCUMENTS  = 500 documents / application batch
TARGET_MAX_BSON_BYTES = 4 MiB / application batch
MAX_WAIT              = 200 ms / application batch
~~~

Đây chỉ là **cấu hình minh họa** cho ứng dụng, không phải giới hạn MongoDB. Hệ thống có document nhỏ, mạng tốt và tải lớn có thể tăng ngưỡng; hệ thống yêu cầu latency thấp hoặc document lớn có thể giảm.

Quy tắc flush có thể là:

~~~text
Flush khi đạt một trong các điều kiện:

  pendingCount >= 500
       OR
  pendingBsonBytes + nextDocumentBytes > 4 MiB
       OR
  oldestPendingAge >= 200 ms
       OR
  stream kết thúc
~~~

**Ngưỡng count** kiểm soát số thao tác. **Ngưỡng byte** kiểm soát payload. **Ngưỡng thời gian** bảo vệ thời gian chờ khi dữ liệu đến thưa. Với tác vụ nhập file offline, ngưỡng thời gian có thể không cần thiết.

### 9.2. Xử lý document đơn lẻ vượt ngưỡng mềm

Một document BSON 6 MiB có thể hợp lệ vì vẫn dưới 16 MiB, nhưng lớn hơn **TARGET_MAX_BSON_BYTES = 4 MiB** của ví dụ. Có hai chiến lược rõ ràng:

- **Cho phép một batch chỉ chứa document đó**, miễn document hợp lệ với server và hệ thống chấp nhận chi phí.
- **Áp đặt giới hạn nghiệp vụ chặt hơn**, ví dụ record import không quá 4 MiB, rồi từ chối hoặc chuyển file lớn sang storage thích hợp.

Không nên đưa document 6 MiB vào vòng lặp “flush rồi thử lại” vô hạn vì batch rỗng vẫn không thỏa ngưỡng 4 MiB. Batch builder phải có đường xử lý riêng cho oversized singleton.

### 9.3. Giữ khoảng đệm

Tổng BSON bytes của các document không phải toàn bộ message size, vì còn phần command/protocol. Ngưỡng byte mềm nên **thấp hơn đáng kể** giá trị maxMessageSizeBytes; không đặt đúng 48.000.000 byte cho payload tài liệu và hy vọng driver gửi thành một request.

Driver vẫn là lớp cuối cùng thực thi các giới hạn kỹ thuật đã đàm phán. Ngưỡng của ứng dụng là để kiểm soát tài nguyên và độ trễ.

### 9.4. Thuật toán chia lô theo count + bytes

~~~text
batch       = empty
batchBytes  = 0

for each document from bounded source:
    prepare stable _id / idempotency key
    validate document
    size = measure BSON bytes with actual codec

    if size > allowedDocumentSize:
        send to rejected-record report
        continue

    if batch is not empty AND
       (batch.count >= targetCount OR
        batchBytes + size > targetBytes):
        send batch
        handle acknowledgment / partial errors
        clear batch
        batchBytes = 0

    append document to batch
    batchBytes += size

flush remaining batch at end
~~~

**Đo kích thước sau khi thêm _id**, vì driver có thể tự cấp **_id** nếu document chưa có. Nếu tính size trước rồi thêm trường hoặc chuyển đổi sang POJO/BSON bằng codec khác, ước lượng sẽ không còn chính xác.

## 10. Ví dụ Java: chia insertMany theo số lượng và byte BSON

Java Sync Driver có **MongoCollection<Document>**, **InsertManyOptions**, **DocumentCodec**, **BsonBinaryWriter** và **BasicOutputBuffer** để xây dựng luồng chia batch. Ví dụ dưới đây giả định ứng dụng đã có **MongoCollection<Document>** và nhận dữ liệu qua **Iterable<Document>**.

Các giá trị 500 document, 4 MiB/batch và 15 MiB/document là **chính sách bảo vệ của ví dụ**, cố ý chặt hơn giới hạn server thông dụng:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.InsertManyOptions;
import org.bson.BsonBinaryWriter;
import org.bson.Document;
import org.bson.codecs.DocumentCodec;
import org.bson.codecs.EncoderContext;
import org.bson.io.BasicOutputBuffer;
import org.bson.types.ObjectId;

import java.util.ArrayList;
import java.util.List;

public final class BatchInsertService {
    private static final int MAX_DOCUMENTS = 500;
    private static final long TARGET_BATCH_BYTES = 4L * 1024 * 1024;
    private static final long MAX_DOCUMENT_BYTES = 15L * 1024 * 1024;

    private final MongoCollection<Document> collection;
    private final DocumentCodec codec = new DocumentCodec();

    public BatchInsertService(MongoCollection<Document> collection) {
        this.collection = collection;
    }

    public void insert(Iterable<Document> source) {
        List<Document> batch = new ArrayList<>(MAX_DOCUMENTS);
        long batchBytes = 0;

        for (Document document : source) {
            // Ổn định _id trước khi đo kích thước và gửi.
            document.putIfAbsent("_id", new ObjectId());

            int docBytes = bsonSize(document);

            if (docBytes > MAX_DOCUMENT_BYTES) {
                throw new IllegalArgumentException(
                    "Import document exceeds application size policy: "
                    + docBytes + " bytes"
                );
            }

            boolean hitCount = batch.size() >= MAX_DOCUMENTS;
            boolean hitBytes =
                    batchBytes + docBytes > TARGET_BATCH_BYTES;

            if (!batch.isEmpty() && (hitCount || hitBytes)) {
                send(batch);
                batch = new ArrayList<>(MAX_DOCUMENTS);
                batchBytes = 0;
            }

            // Một document > 4 MiB được gửi như batch một phần tử.
            batch.add(document);
            batchBytes += docBytes;
        }

        if (!batch.isEmpty()) {
            send(batch);
        }
    }

    private int bsonSize(Document document) {
        BasicOutputBuffer output = new BasicOutputBuffer();

        try (BsonBinaryWriter writer = new BsonBinaryWriter(output)) {
            codec.encode(
                writer,
                document,
                EncoderContext.builder().build()
            );
        }

        return output.getPosition();
    }

    private void send(List<Document> batch) {
        collection.insertMany(
            batch,
            new InsertManyOptions().ordered(false)
        );
    }
}
~~~

### 10.1. Cách sử dụng

~~~java
MongoCollection<Document> products =
        mongoDatabase.getCollection("import_products");

BatchInsertService service = new BatchInsertService(products);

List<Document> source = List.of(
    new Document("sourceId", "ROW-1").append("name", "Mouse"),
    new Document("sourceId", "ROW-2").append("name", "Keyboard"),
    new Document("sourceId", "ROW-3").append("name", "Monitor")
);

service.insert(source);
~~~

Trong hệ thống nạp file lớn, hãy thay **List.of(...)** bằng nguồn đọc **từng dòng/stream** và giữ số lượng phần tử chờ trong bộ nhớ có giới hạn. **Iterable** có thể là nguồn lazy, nhưng việc nguồn thực sự đọc lazy hay không tùy cách cài đặt.

### 10.2. Giới hạn của ví dụ Java

Ví dụ minh họa thuật toán chia lô, **chưa phải thành phần import hoàn chỉnh để đưa production ngay**:

- **DocumentCodec** đo BSON theo kiểu **Document** và các value đã được chuẩn bị; nếu ứng dụng dùng POJO codec/mapper khác, cần đo bằng **codec thực sự sẽ dùng để ghi**.
- **TOTAL_BATCH_BYTES** mới cộng BSON document bytes; nó chưa tính toàn bộ command/wire overhead.
- **ordered(false)** cho phép thành công một phần. Nếu **insertMany** ném exception, ví dụ **dừng** ở batch đó; ứng dụng production cần thu thập kết quả, xử lý record lỗi và quyết định có tiếp tục các batch sau hay không.
- Việc sinh **ObjectId** trong ứng dụng trước khi gửi có ích khi cần giữ định danh ổn định để kiểm tra/retry, nhưng nó không tự bảo đảm idempotency cho toàn bộ nghiệp vụ. Có thể dùng business key unique.
- Ngưỡng 15 MiB/document là **chính sách của ví dụ**, không phải MongoDB từ chối mọi document lớn hơn 15 MiB.
- Với các hệ dùng session, transaction, write concern hoặc API reactive, cần truyền và xử lý những tham số đó theo contract ứng dụng.

Trong thực tế, có thể điều chỉnh **MAX_DOCUMENTS**, **TARGET_BATCH_BYTES** và độ song song theo metrics thay vì dùng một ngưỡng chung cho mọi collection.

## 11. Ví dụ mongosh: chia danh sách theo count

Nếu chỉ cần thử nghiệm với tập dữ liệu nhỏ và kích thước document đã được kiểm soát, có thể chia thành từng nhóm bằng JavaScript:

~~~javascript
const docs = Array.from({ length: 2500 }, (_, i) => ({
  sourceId: "TEST-" + i,
  quantity: NumberInt(i)
}));

const maxDocsPerCall = 500;

for (let start = 0; start < docs.length; start += maxDocsPerCall) {
  const chunk = docs.slice(start, start + maxDocsPerCall);
  db.import_rows.insertMany(chunk, { ordered: false });
}
~~~

Ví dụ tạo tối đa **500 document cho mỗi lời gọi insertMany**. Nó chưa tính tổng BSON bytes nên **không đủ** cho nguồn có document kích thước biến thiên lớn. Với dữ liệu thực, cần thêm ngưỡng byte như thuật toán ở Mục 9 và tránh tạo mảng chứa toàn bộ đầu vào trước khi chia.

## 12. Backpressure: batch hữu hạn nhưng hàng đợi vẫn có thể vô hạn

Giả sử ứng dụng sinh dữ liệu ở tốc độ **30.000 document/giây**, nhưng database chỉ ghi bền vững được **20.000 document/giây** trong điều kiện hiện tại. Dù đã chia mỗi batch thành 500 document, nếu producer cứ tiếp tục không giới hạn thì queue sẽ lớn dần:

~~~text
Producer: 30.000 docs/s
           |
           v
       Unbounded queue     <--- tích tụ +10.000 docs/s
           |
           v
    Batch writer: 20.000 docs/s
           |
           v
         MongoDB
~~~

Giải pháp là **backpressure**: giới hạn số document/batch đang chờ, số request đang in-flight và tốc độ tạo công việc.

~~~text
Producer
   |
   v
Bounded queue (capacity)
   |
   +-- full --> producer waits / rejects / persists externally
   |
   v
N batch workers (bounded concurrency)
   |
   v
MongoDB connection pool
   |
   v
MongoDB
~~~

Các cách thường gặp:

1. **Producer blocking:** khi queue đầy, chờ writer tiêu thụ bớt.
2. **Rate limiting:** giới hạn số batch hoặc byte được nhận mỗi giây theo hợp đồng.
3. **Bounded concurrency:** không phát hàng nghìn batch song song nếu connection pool và server không chịu được.
4. **Durable queue:** dùng hàng đợi bền vững khi cần tách tốc độ nhận dữ liệu và tốc độ ghi database.
5. **Admission control:** từ chối/thông báo thử lại khi hệ thống quá tải, thay vì âm thầm tích lũy RAM.

**Số kết nối MongoDB không phải số batch nên phát đồng thời tối ưu.** Tăng concurrency có thể tăng throughput tới một điểm, rồi làm độ trễ, lock contention, cache pressure và lỗi timeout xấu đi. Phải đo trên workload thật.

## 13. Partial failure, retry và idempotency

Một batch có thể thành công một phần vì:

- document trùng khóa **_id** hoặc unique business key;
- document không hợp lệ theo schema validation;
- document quá lớn;
- write concern chưa được đáp ứng trong khoảng thời gian chờ;
- lỗi mạng hoặc node failover khi thao tác đang diễn ra;
- thiếu disk space hoặc tài nguyên hệ thống;
- driver/server timeout;
- lỗi thao tác riêng trong **bulkWrite**.

### 13.1. Phân loại lỗi trước khi retry

| Loại lỗi | Tư duy xử lý |
|---|---|
| **Duplicate key** | Kiểm tra đó là bản ghi đã được tạo trước hay xung đột dữ liệu thực sự. Không retry mù. |
| **Schema validation** | Gửi record về bước kiểm tra/sửa nguồn; retry nguyên dữ liệu không giải quyết lỗi. |
| **Document too large** | Thiết kế lại document hoặc từ chối record; giảm batch size không làm một document trở nên nhỏ hơn. |
| **Temporary network/failover** | Kiểm tra nhãn lỗi, semantics retry của driver và idempotency trước khi thử lại. |
| **Write concern timeout/error** | Ghi có thể đã thực hiện nhưng chưa được xác nhận theo mức yêu cầu. Cần kiểm tra trạng thái thay vì khẳng định thất bại. |
| **Overload / timeout** | Giảm concurrency, batch size hoặc điều chỉnh retry có backoff/jitter; xem metrics. |

Một **timeout không chứng minh document chắc chắn chưa được insert**. Client có thể mất phản hồi sau khi server đã áp dụng thao tác. Đây là lý do import cần cơ chế đối chiếu theo ID/biz key.

### 13.2. Dùng business key unique cho idempotency

Ví dụ dữ liệu từ hệ thống nguồn có **sourceSystem** và **externalId**:

~~~javascript
db.import_orders.createIndex(
  { sourceSystem: 1, externalId: 1 },
  { unique: true, name: "uq_source_external_id" }
);
~~~

Khi gửi lại cùng bản ghi, index ngăn tạo thêm hai document cùng danh tính nguồn. Tuy nhiên unique index **không tự xác nhận nội dung là giống nhau**: nếu cùng **externalId** nhưng số tiền khác, đó là một xung đột nghiệp vụ cần được giải quyết.

Một cách khác là dùng **upsert với $setOnInsert** cho luồng chỉ tạo lần đầu:

~~~javascript
db.import_orders.updateOne(
  {
    sourceSystem: "ERP",
    externalId: "ERP-1001"
  },
  {
    $setOnInsert: {
      sourceSystem: "ERP",
      externalId: "ERP-1001",
      amount: NumberDecimal("250000.00"),
      status: "NEW"
    }
  },
  { upsert: true }
);
~~~

Kết hợp với unique index phù hợp, hướng này hữu ích cho ingest idempotent. Nếu nghiệp vụ muốn cập nhật dữ liệu mới, không nên dùng **$setOnInsert** một cách máy móc; cần quy tắc version, timestamp hoặc dedup khác.

### 13.3. Quản lý index của thao tác lỗi

Khi xử lý **BulkWriteException** ở Java, thông tin lỗi có thể bao gồm **index** của thao tác trong danh sách bulk tương ứng cùng mã và thông điệp lỗi. Ứng dụng phải giữ mapping giữa:

~~~text
input record -> logical batch -> operation index -> sourceId
~~~

Nếu tự chia 10.000 record thành 20 batch 500 record, **operation index 3** của batch thứ 5 không phải **dòng thứ 3 của toàn file**. Cần lưu **sourceId/line number** và offset của từng batch để báo lỗi chính xác. Không tự đoán index toàn cục dựa trên chi tiết nội bộ cách driver split wire batches.

### 13.4. Retryable writes không có nghĩa mọi bulk tự retry an toàn

MongoDB Drivers hỗ trợ **retryable writes** cho những thao tác và điều kiện đủ tiêu chuẩn, thường qua **retryWrites=true**. Tuy nhiên:

- Không phải mọi thao tác trong bulk đều có cùng điều kiện retry.
- Một số loại update/delete nhiều document hoặc thao tác transaction có semantics khác.
- Driver có thể đã retry trong phạm vi được hỗ trợ trước khi trả lỗi.
- Retry ở tầng ứng dụng cần tính cả duplicate key, side effects và trạng thái không chắc chắn.

Giải pháp đáng tin cậy là **idempotent ingestion contract**, lưu checkpoint của nguồn và chỉ replay các phần đã được xác định cần xử lý lại.

## 14. Write concern và kích thước batch

**Write concern** quyết định điều kiện acknowledgment. Trong replica set, một batch lớn kết hợp **w: "majority"** có thể có độ trễ cao hơn **w: 1**, tùy replication lag và tải. Lựa chọn ngưỡng batch phải đo trong điều kiện đúng write concern của production.

Ví dụ cấu hình ở mongosh:

~~~javascript
db.import_orders.insertMany(
  [
    {
      sourceSystem: "ERP",
      externalId: "ERP-1002",
      amount: NumberDecimal("150000.00")
    },
    {
      sourceSystem: "ERP",
      externalId: "ERP-1003",
      amount: NumberDecimal("300000.00")
    }
  ],
  {
    ordered: false,
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
~~~

**wtimeout** giới hạn thời gian chờ đạt write concern, không tự đặt timeout cho toàn bộ việc mã hóa, gửi request hoặc mọi công đoạn xử lý của driver. Trong Java, còn có những cấu hình khác như server selection timeout, socket/read timeout hoặc operation timeout tùy phiên bản và API.

**Batch size không phải durability policy**: chia 10.000 document thành 20 batch 500 document không thay đổi bản chất của **w: "majority"**, nhưng ảnh hưởng thời gian xử lý, tải và phạm vi lỗi cần theo dõi.

## 15. Transaction không xóa giới hạn kích thước

Một transaction nhiều document có thể cần khi nghiệp vụ yêu cầu thay đổi đồng thời nhiều thực thể. Tuy nhiên:

- Mỗi document BSON vẫn phải tuân theo giới hạn kích thước tương ứng.
- Transaction có chi phí giữ trạng thái, tài nguyên và giới hạn về thời gian/snapshot.
- Batch cực lớn trong một transaction có thể làm tăng contention, replication overhead và rủi ro timeout.
- Không nên tạo một transaction bao toàn bộ file import hàng triệu dòng chỉ để “có tính nguyên tử”.

Nếu một luồng nhập lớn cần chỉ công bố dữ liệu khi toàn bộ file hợp lệ, cân nhắc **staging collection + validation + publish/swap theo workflow phù hợp**, hoặc trạng thái batch/job để dữ liệu chưa hoàn thành không được người dùng nhìn thấy. Chiến lược cụ thể phụ thuộc topology và cách đọc dữ liệu.

## 16. Batch size trong sharded cluster

Trong sharded cluster, driver gửi thao tác đến **mongos**, còn router định tuyến đến các shard phù hợp. Với unordered bulk writes, MongoDB có thể phân phối các thao tác đến nhiều shard và tận dụng xử lý song song hơn tùy workload.

Nhưng một batch chứa 10.000 document thuộc **một shard key nóng** có thể vẫn gây quá tải ở một shard. Các yếu tố quyết định gồm:

- shard key và phân bố giá trị;
- tỉ lệ request đến từng shard;
- kích thước document/index;
- network giữa **mongos** và các shard;
- trạng thái balancing, replication và disk;
- write concern.

Nếu dùng batch lớn để ghi một tenant “khổng lồ” và một shard luôn bận, chỉ tăng số batch song song không làm dữ liệu tự phân phối đều hơn. Cần xem xét **shard key**, workload và tốc độ ingest.

## 17. Chọn ngưỡng thực tế theo mục tiêu

Không có một giá trị batch size cố định phù hợp mọi ứng dụng. Có thể bắt đầu với một ngưỡng bảo thủ, sau đó điều chỉnh theo số đo.

| Bối cảnh | Chính sách khởi đầu có thể thử | Chỉ số cần quan sát |
|---|---|---|
| **REST API tạo vài document** | insertOne hoặc batch rất nhỏ. | p95/p99 latency, request timeout. |
| **Import CSV offline** | Vài trăm đến vài nghìn document, có ngưỡng bytes và nguồn streaming. | docs/s, MB/s, heap, GC, disk latency, write errors. |
| **Document kích thước lớn/biến thiên** | Giới hạn theo bytes quan trọng hơn count; tách oversized singleton. | per-document BSON bytes, p95 batch bytes, thời gian encode. |
| **Nhiều tenant/shard** | Batch theo nguồn hoặc tenant nếu giúp kiểm soát công bằng; bounded concurrency. | per-shard load, hot tenants, failover effects. |
| **Luồng sự kiện thời gian thực** | Batch nhỏ hơn, flush theo thời gian tối đa. | ingest lag, end-to-end latency, queue depth. |
| **Yêu cầu write concern majority** | Đo với cấu hình majority thực, tránh đẩy quá nhiều request đồng thời. | majority acknowledgment latency, replication lag. |

Các ngưỡng chỉ là gợi ý để **benchmark**. Chúng không thay thế test tải và đánh giá capacity.

### 17.1. Thử nghiệm tăng dần

Một cách tuning:

1. Chọn một dataset đại diện: phân bố kích thước, loại BSON, index và số lượng document giống production.
2. Ghi lại baseline với batch nhỏ, chẳng hạn **100 document** và một số writer hữu hạn.
3. Tăng lên 250/500/1.000 document trong từng lần thử, vẫn giữ ngưỡng byte và concurrency được kiểm soát.
4. Đo throughput, p95/p99 batch latency, heap, GC, disk I/O, network, write concern latency và số lỗi.
5. Khi throughput không cải thiện hoặc latency/resource bắt đầu xấu đi, chọn cấu hình trước ngưỡng đó; đánh giá riêng khi workload thay đổi.

Không thực hiện benchmark ở production bằng một lệnh import không giới hạn. Hãy dùng dữ liệu và môi trường có kiểm soát, đặc biệt khi collection có index lớn hoặc các ứng dụng khác đang sử dụng chung cluster.

### 17.2. Các metric nên ghi trên mỗi batch

~~~text
import_job_id
batch_id
source_offset_start / end
document_count
estimated_bson_bytes
encode_duration_ms
send_duration_ms
ack_duration_ms
inserted_count
duplicate_count
validation_error_count
retry_count
final_status
~~~

Những thông tin này giúp phân biệt **batch quá lớn**, **server quá tải**, **lỗi dữ liệu** và **truyền mạng chậm**. Không ghi trực tiếp nội dung nhạy cảm của mọi document vào log chỉ để debug.

## 18. Các thông số dễ nhầm với giới hạn lô ghi

| Thông số | Thuộc loại | Không nên nhầm với |
|---|---|---|
| **maxWriteBatchSize** | Số thao tác trong một write command batch. | Số document tối ưu trong một lần gọi API. |
| **maxBsonObjectSize** | Kích thước BSON document. | Tổng byte của một logical batch. |
| **maxMessageSizeBytes** | Kích thước MongoDB wire message. | Giới hạn HTTP body hoặc heap của ứng dụng. |
| **cursor batchSize** | Số document trong batch kết quả **đọc**. | Kích thước lô **ghi** của insertMany. |
| **maxTimeMS** | Giới hạn thời gian cho các operation phù hợp. | Giới hạn byte hoặc số thao tác ghi. |
| **maxPoolSize** | Số connection trong connection pool. | Số document mỗi batch hoặc số batch song song tối ưu. |
| **w / j / wtimeout** | Mức acknowledgment và thời gian chờ write concern. | Cơ chế chia request theo wire protocol. |
| **16 MiB document limit** | Một document lưu được bao nhiêu byte. | Dung lượng file được lưu qua GridFS. |

Một tên tham số có chữ “batch” chưa chắc nói về đường ghi. Ví dụ **cursor.batchSize()** dùng cho việc lấy **kết quả truy vấn**, không điều khiển **insertMany()**.

## 19. Các lỗi thường gặp trong quá trình import

### 19.1. Chia theo 100.000 document vì đó là giới hạn server

**Vấn đề:** đây là mức trần cho một write command, không phải điểm tối ưu. Document có kích thước biến thiên có thể chạm ngưỡng message trước đó, còn ứng dụng có thể hết RAM.

**Cách xử lý:** đặt count/bytes/time thresholds ở tầng ứng dụng, để driver tiếp tục thực thi wire constraints.

### 19.2. Tính kích thước bằng JSON.stringify

**Vấn đề:** string length khác BSON bytes; ObjectId, Date, Decimal128, Binary và ký tự UTF-8 có representation khác.

**Cách xử lý:** dùng công cụ đo BSON theo codec thực tế, ví dụ **Object.bsonsize** trong mongosh hoặc BSON encoder phù hợp trong driver.

### 19.3. Chia batch vẫn không insert được document quá lớn

**Vấn đề:** document 20 MiB vượt giới hạn của **một** BSON document; chia 1 document/batch vẫn không giải quyết.

**Cách xử lý:** tách cấu trúc, bỏ dữ liệu không cần thiết hoặc dùng GridFS/object storage cho blob.

### 19.4. Tăng concurrency để bù batch nhỏ

**Vấn đề:** quá nhiều writer có thể làm connection pool queue, replication lag, I/O và timeout tăng.

**Cách xử lý:** bounded concurrency + backpressure, đo throughput/latency dưới cùng write concern.

### 19.5. Dùng ordered:true và kỳ vọng rollback toàn batch

**Vấn đề:** các document được ghi trước lỗi vẫn có thể tồn tại.

**Cách xử lý:** thiết kế partial failure handling và chọn transaction/workflow bù trừ nếu thật sự cần atomicity nhiều document.

### 19.6. Retry toàn bộ batch sau timeout

**Vấn đề:** một số document có thể đã được thêm; retry có thể gặp duplicate key hoặc tạo bản sao khác nếu _id không ổn định.

**Cách xử lý:** giữ identity ổn định, dùng unique business key, tra cứu trạng thái kết quả trước retry và xử lý lỗi theo record.

### 19.7. Báo cáo insertedCount bằng số phần tử đã gửi

**Vấn đề:** batch 500 document nhưng có 20 duplicate key thì số document được chèn không phải 500.

**Cách xử lý:** phân biệt **attempted count**, **acknowledged success**, **rejected/failed**, **uncertain outcome** và **previously existing**.

### 19.8. Để batch quá lâu khi lưu lượng thấp

**Vấn đề:** đạt ngưỡng count/bytes chậm, document chờ trong memory nhiều giây hoặc phút.

**Cách xử lý:** với ingest thời gian thực, bổ sung **flush interval / max wait age**, đồng thời đảm bảo flush cuối khi stream đóng an toàn.

### 19.9. Coi số byte nén như số byte BSON

**Vấn đề:** nội dung BSON có thể khác kích thước network đã nén, kích thước JSON trước mã hóa và dung lượng trên đĩa sau compression.

**Cách xử lý:** đo đúng đơn vị tại đúng tầng. Giới hạn MongoDB wire protocol và application policy cần diễn đạt rõ chúng đo gì.

## 20. Bài thực hành nhỏ

### Bài 1 — Quan sát giới hạn server

Chạy **hello** ở Mục 2.1 và ghi lại ba giá trị. Tính bằng tay:

- 1.500 document, mỗi document khoảng 1 KiB BSON có tổng payload xấp xỉ bao nhiêu?
- 1.500 document, mỗi document khoảng 40 KiB BSON có tổng payload xấp xỉ bao nhiêu?
- Trong hai trường hợp, count limit hay byte limit có khả năng đến trước?

Lưu ý: phép tính này bỏ qua overhead và chỉ phục vụ tư duy, không thay thế cách chia request của driver.

### Bài 2 — Kiểm tra kích thước BSON theo field

~~~javascript
const small = { name: "Mouse", count: NumberInt(10) };
const large = {
  name: "Large description",
  description: "A".repeat(1024 * 1024)
};

print(Object.bsonsize(small));
print(Object.bsonsize(large));
~~~

So sánh kết quả với **JSON.stringify(...).length**. Giải thích vì sao hai số không nhất thiết bằng nhau.

### Bài 3 — Tự chia batch count

Thực hành **2500 document** và **maxDocsPerCall = 500** theo Mục 11. Đếm số lời gọi **insertMany** của ứng dụng và giải thích tại sao số lời gọi ở ứng dụng không nhất thiết bằng số command thực tế nếu document có kích thước lớn.

### Bài 4 — Ordered/unordered khi duplicate key

Tạo **unique index** trên **orderCode**; thực hiện hai ví dụ ở Mục 8 trên collection thử nghiệm riêng. Quan sát:

- document nào vẫn tồn tại sau lỗi;
- exception/error được báo;
- vì sao **ordered: true** không tương đương transaction.

### Bài 5 — Thiết kế import 1 triệu dòng

Giả sử dữ liệu có kích thước BSON từ **0,5 KiB đến 100 KiB** và nguồn có thể phát 30.000 document/giây. Đề xuất:

- ngưỡng count, bytes, thời gian cho mỗi batch;
- cách giữ **queue bounded**;
- số worker đồng thời ban đầu và cách tuning;
- cách lưu tiến độ nguồn để resume sau lỗi;
- cách định danh/idempotency cho mỗi record;
- báo cáo lỗi record theo **source offset** và **sourceId**.

Không cần chọn ngay một con số “chuẩn”; phần quan trọng là quy tắc giới hạn và cách đo.

## 21. Câu hỏi ôn tập

1. Khác biệt giữa **logical batch**, **wire batch** và **một BSON document** là gì?
2. Vì sao MongoDB có giới hạn **maxWriteBatchSize** và **maxMessageSizeBytes** riêng?
3. Một document vượt 16 MiB có thể được insert bằng cách đặt batch size = 1 hay không?
4. Vì sao **48.000.000 byte** không nên được gọi chính xác là **48 MiB**?
5. Driver có thể tự chia batch rồi, tại sao ứng dụng vẫn cần batch builder giới hạn memory?
6. Khi **ordered: false**, điều gì xảy ra nếu một document lỗi duplicate key?
7. Một batch **insertMany** mặc định có atomicity toàn lô không? Vì sao?
8. Một lỗi write concern timeout có chứng minh thao tác chưa được lưu không?
9. Vì sao phải tạo **_id** hoặc business key ổn định trước retry?
10. Tại sao cần đo **BSON bytes** thay vì số ký tự JSON khi tính byte threshold?
11. Backpressure giải quyết vấn đề gì mà việc chia 500 document/batch chưa giải quyết?
12. Cần theo dõi metric nào để biết nên tăng hay giảm batch size?

## 22. Kết luận

Để thêm nhiều document vào MongoDB ổn định, cần phân biệt rõ **giới hạn cứng của server** với **ngưỡng mềm do ứng dụng lựa chọn**:

~~~text
Một document:
  BSON size <= server maxBsonObjectSize
  (thông dụng: 16 MiB)

Một write command:
  operations <= maxWriteBatchSize
  (thông dụng: 100.000)

Một wire message:
  message bytes <= maxMessageSizeBytes
  (thông dụng: 48.000.000 bytes)

Ứng dụng:
  chunk theo count + BSON bytes [+ max wait]
  bounded queue + bounded concurrency
  error accounting + idempotent retry
  đo throughput, latency và tài nguyên
~~~

Một pipeline ingest tốt không chỉ là gọi **insertMany** thay cho **insertOne**. Nó cần quản lý dòng dữ liệu vào, kích thước từng document, giới hạn lô, độ đồng thời, kết quả ghi và khả năng tiếp tục sau lỗi. **MongoDB Driver giúp đảm bảo request hợp lệ về giao thức; ứng dụng chịu trách nhiệm về tính đúng đắn và khả năng vận hành của cả quy trình.**

### Tài liệu MongoDB chính thức tham khảo

- [MongoDB Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/) — giới hạn BSON document, write batch và những ngưỡng liên quan.
- [db.collection.insertMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertMany/) — insert nhiều document và hành vi ordered/unordered.
- [db.collection.bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/) — thao tác bulk kết hợp nhiều loại ghi.
- [MongoDB Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/) — cách xử lý bulk và sự khác nhau giữa ordered/unordered.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — acknowledgment và các trường hợp write concern error.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — Java API, insertMany, bulkWrite, xử lý lỗi và cấu hình kết nối.
- [Object.bsonsize()](https://www.mongodb.com/docs/manual/reference/method/Object.bsonsize/) và [$bsonSize](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonSize/) — đo BSON document size.

Khi áp dụng các con số hoặc tùy chọn trong bài vào hệ thống thực, hãy đối chiếu **phiên bản MongoDB và driver đang dùng**, đọc thông số từ server đích và kiểm chứng bằng workload đại diện. Những giá trị như 500 document/batch hoặc 4 MiB/batch là lựa chọn vận hành để thử nghiệm, không phải giới hạn kỹ thuật cố định của MongoDB.

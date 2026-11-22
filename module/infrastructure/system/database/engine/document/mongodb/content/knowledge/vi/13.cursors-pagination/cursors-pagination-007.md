# Giới hạn thời gian truy vấn bằng maxTimeMS và xử lý hủy yêu cầu trong MongoDB

## 1. Vì sao truy vấn cần thời hạn?

Trong một ứng dụng dùng MongoDB, không phải truy vấn nào cũng hoàn thành nhanh. Một câu lệnh có thể chậm do thiếu index, sắp xếp quá nhiều document, lọc dữ liệu lớn, chờ tài nguyên, tải hệ thống cao hoặc truy vấn phân tán trên nhiều shard. Nếu người dùng đã rời trang nhưng server vẫn tiếp tục tính toán, hệ thống có thể tiêu tốn tài nguyên cho kết quả không ai cần.

Hãy hình dung API hiển thị lịch sử hoạt động của khách hàng:

~~~text
Trình duyệt
    |
    | GET /events?status=open
    v
API server
    |
    | MongoDB find + sort + pagination
    v
MongoDB server
    |
    | Đọc index / lọc / sort / lấy từng batch
    v
API trả kết quả cho trình duyệt
~~~

Nếu người dùng chuyển sang màn hình khác sau 700 ms, một truy vấn mất 20 giây có thể không còn hữu ích. Bên cạnh việc tối ưu index và pagination, hệ thống cần **đặt ngân sách thời gian** và **xử lý tín hiệu hủy** một cách có chủ đích.

Trong MongoDB có ba khái niệm cần phân biệt:

1. **maxTimeMS:** ngân sách thời gian thực thi được MongoDB áp dụng ở phía server cho thao tác hỗ trợ tùy chọn này.
2. **Deadline/timeout phía client hoặc API:** thời gian tối đa mà phía gọi sẵn sàng chờ **toàn bộ** công việc, bao gồm mạng, xử lý ứng dụng và nhiều lời gọi database.
3. **Hủy yêu cầu/cursor:** tín hiệu cho biết kết quả không còn cần thiết; ứng dụng cần dừng tiêu thụ kết quả và giải phóng tài nguyên, có thể yêu cầu driver/server hủy thao tác đang chạy.

**maxTimeMS không tự động là deadline end-to-end cho HTTP request**, và **đóng cursor không đồng nghĩa mọi hoạt động đang chạy trong server đã biến mất ngay lập tức**. Thiết kế đúng thường kết hợp nhiều lớp bảo vệ.

## 2. maxTimeMS làm gì?

### 2.1. Ý nghĩa

**maxTimeMS** là giới hạn thời gian, tính bằng **mili giây**, mà client yêu cầu MongoDB áp dụng cho một thao tác có hỗ trợ tùy chọn này. Khi một thao tác vượt ngưỡng, MongoDB có thể ngắt nó tại **điểm kiểm tra ngắt thích hợp** và trả lỗi hết thời gian.

Ví dụ trong mongosh:

~~~javascript
db.getSiblingDB("mongo_timeout_lab")
  .getCollection("lab_events")
  .find({ status: "open" })
  .maxTimeMS(1500);
~~~

Lệnh đặt giới hạn server-side khoảng **1.500 ms** cho xử lý truy vấn theo cơ chế của MongoDB; nó không có nghĩa MongoDB bắt buộc trả kết quả sau đúng 1.500 ms hoặc thao tác được ngắt chính xác đến từng mili giây.

Các điểm cần nhớ:

- **maxTimeMS được chỉ định ở phía client nhưng được thực thi bởi server** đối với thao tác hỗ trợ.
- **Không bảo đảm kết quả thành công trong khoảng thời gian đó**; thay vào đó, thao tác quá chậm có thể bị từ chối bằng lỗi timeout.
- **Không làm truy vấn nhanh hơn** và không thay thế index tốt.
- **Không tự giới hạn số document** được trả về. Muốn giới hạn số kết quả, dùng **limit** và pagination.
- **Không giới hạn trực tiếp toàn bộ thời gian mạng, render, serialization hay xử lý HTTP**.
- **Không phải một lời hứa rằng tài nguyên sẽ được giải phóng ngay tức khắc tại đúng thời điểm deadline**.

### 2.2. Lỗi khi vượt thời gian

Một truy vấn bị MongoDB kết thúc do **maxTimeMS** thường trả về lỗi có **mã 50**, tên **MaxTimeMSExpired**. Có thể thấy thông điệp gần với:

~~~text
MongoServerError: PlanExecutor error during aggregation ...
operation exceeded time limit
code: 50
codeName: "MaxTimeMSExpired"
~~~

Nội dung thông điệp và lớp exception phụ thuộc phiên bản server, driver và thao tác. Khi xử lý lỗi, ưu tiên **mã lỗi/tên lỗi đã chuẩn hóa** thay vì so khớp toàn bộ chuỗi thông điệp.

Lỗi MaxTimeMSExpired là tín hiệu **truy vấn không hoàn thành theo ngân sách**, không phải dấu hiệu rằng dữ liệu bị sai. Ứng dụng có thể trả một trạng thái timeout phù hợp, yêu cầu người dùng thu hẹp bộ lọc, hoặc ghi telemetry để điều tra.

### 2.3. Truy vấn nhanh vẫn hoàn thành bình thường

Nếu truy vấn hoàn thành trong 10 ms và maxTimeMS đặt 1.500 ms, kết quả vẫn được trả về như bình thường. Đặt maxTimeMS không khiến server cố chờ tới mốc 1.500 ms.

Ví dụ:

~~~javascript
db.getSiblingDB("mongo_timeout_lab")
  .getCollection("lab_events")
  .find({
    tenantId: "t001",
    status: "open"
  })
  .limit(10)
  .maxTimeMS(1500)
  .toArray();
~~~

Nếu collection nhỏ, lệnh rất có thể hoàn thành quá nhanh để quan sát lỗi timeout. Không nên cố tạo truy vấn gây tải cực lớn hoặc sleep lâu trên môi trường dùng chung chỉ để kiểm tra cơ chế timeout.

## 3. Phân biệt các loại thời hạn và giới hạn

Các tùy chọn nghe giống nhau nhưng có mục đích khác nhau:

| Cơ chế | Giới hạn điều gì? | Không bảo đảm điều gì? |
| --- | --- | --- |
| **maxTimeMS** | Thời gian thực thi server của thao tác hỗ trợ tùy chọn này | Deadline toàn bộ API, mạng và xử lý client |
| **Client-side operation timeout / timeoutMS** (nếu driver hỗ trợ) | Ngân sách ở phía driver cho một thao tác gồm các bước theo hợp đồng driver | Truy vấn server bị dừng tức khắc trong mọi tình huống |
| **Socket/read timeout** | Thời gian chờ I/O mạng hoặc đọc dữ liệu theo cấu hình driver | Quy tắc nghiệp vụ về độ trễ API |
| **Server selection timeout** | Thời gian driver tìm server phù hợp | Thời gian thực thi câu truy vấn sau khi chọn server |
| **HTTP request deadline** | Ngân sách tổng cho request từ góc nhìn API | Server database ngừng việc ngay khi HTTP hết hạn |
| **limit(N)** | Số document tối đa trả từ cursor | Truy vấn chắc chắn nhanh hoặc quét tối đa N document |
| **batchSize(N)** | Số document mong muốn trong một batch cursor | Số document tổng cộng và thời gian tổng |
| **maxAwaitTimeMS** | Thời gian chờ dữ liệu mới của cursor dạng tailable/awaitData theo cơ chế liên quan | Giới hạn xử lý của truy vấn find thông thường |

Ví dụ một API có deadline **2.000 ms** có thể dành khoảng **1.200 ms** cho query, phần còn lại cho xác thực, mạng, serialization và biên dự phòng. Đây chỉ là **minh họa ngân sách**, không phải một công thức cố định:

~~~text
Deadline API: 2.000 ms
|-- Xác thực / xác định tenant
|-- MongoDB query: maxTimeMS 1.200 ms
|-- Xử lý kết quả và serializing JSON
|-- Truyền response / dự phòng
~~~

Nếu request có **ba truy vấn liên tiếp**, mỗi truy vấn maxTimeMS 1.200 ms, tổng thời gian có thể vượt xa 2.000 ms. Khi xây dựng deadline thực tế, ngân sách nên được truyền xuyên các bước và tính theo **thời gian còn lại**.

## 4. Chuẩn bị database lab và index

Ta sẽ tạo 24 event cố định, thuộc hai tenant, có trạng thái open/done và mốc thời gian khác nhau. Truy vấn lịch sử thường lọc theo tenant và status, sắp xếp theo occurredAt giảm dần rồi _id giảm dần để phân trang ổn định.

Tất cả document thuộc bài có **dataset: "cursor-timeout-v1"** trong collection **lab_events** của database **mongo_timeout_lab**.

### 4.1. Tạo dữ liệu

Chạy nguyên khối trong mongosh:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_timeout_lab");
  const events = lab.getCollection("lab_events");
  const tag = "cursor-timeout-v1";

  // Chỉ dọn dữ liệu của bài, không drop collection/database.
  events.deleteMany({ dataset: tag });

  const documents = Array.from({ length: 24 }, (_, index) => {
    const number = index + 1;

    return {
      _id: "ev-" + String(number).padStart(3, "0"),
      dataset: tag,
      tenantId: number <= 18 ? "t001" : "t002",
      status: number % 4 === 0 ? "done" : "open",
      eventType: number % 2 === 0 ? "change" : "create",
      title: "Sự kiện " + number,
      occurredAt: new Date(Date.UTC(2026, 0, 1, 0, number, 0))
    };
  });

  events.insertMany(documents);

  events.createIndex(
    {
      dataset: 1,
      tenantId: 1,
      status: 1,
      occurredAt: -1,
      _id: -1
    },
    { name: "ix_lab_event_page" }
  );

  printjson({
    total: events.countDocuments({ dataset: tag }),
    tenant001Open: events.countDocuments({
      dataset: tag,
      tenantId: "t001",
      status: "open"
    })
  });
})();
~~~

**Kết quả mong đợi:** **24 event** tổng cộng; tenant **t001** có **14 event open**. Chạy lại khối seed để phục hồi trạng thái dữ liệu cố định nếu đã sửa document trong lúc thực hành.

Index có các trường equality (dataset, tenantId, status) trước, sau đó là các trường phục vụ sort và pagination (occurredAt, _id). Trong production không cần mang trường dataset nếu không có nhu cầu tương đương; nó được dùng ở đây để cách ly dữ liệu lab.

### 4.2. Xem trước query plan

~~~javascript
db.getSiblingDB("mongo_timeout_lab")
  .getCollection("lab_events")
  .find(
    {
      dataset: "cursor-timeout-v1",
      tenantId: "t001",
      status: "open"
    },
    { _id: 1, title: 1, occurredAt: 1 }
  )
  .sort({ occurredAt: -1, _id: -1 })
  .limit(3)
  .explain("executionStats");
~~~

Trong explain, hãy chú ý:

- **winningPlan:** kế hoạch được chọn.
- **IXSCAN/COLLSCAN:** đang dùng index hay quét collection.
- **indexBounds:** phần index được dùng để lọc.
- **SORT:** có cần sắp xếp blocking ngoài index không.
- **nReturned**, **totalKeysExamined**, **totalDocsExamined:** kết quả và công việc thực hiện.

Với chỉ 24 document, MongoDB có thể chọn kế hoạch khác dự đoán vì quét collection cũng rẻ. Kết quả lab không phải bằng chứng index production sẽ luôn được chọn. Việc tăng maxTimeMS để che một index thiếu là cách xử lý triệu chứng, không phải khắc phục nguyên nhân.

## 5. Dùng maxTimeMS với cursor find

### 5.1. Cursor và thời điểm truy vấn thực sự chạy

Khi viết:

~~~javascript
const cursor = db.getSiblingDB("mongo_timeout_lab")
  .getCollection("lab_events")
  .find({
    dataset: "cursor-timeout-v1",
    tenantId: "t001",
    status: "open"
  });
~~~

Bạn đã tạo một **cursor object** ở phía mongosh. Tùy API, câu truy vấn thường được gửi/thực thi khi cursor được **tiêu thụ**, chẳng hạn gọi **toArray()**, **hasNext()**, **next()** hoặc duyệt vòng lặp; chỉ việc gán biến cursor chưa có nghĩa đã lấy hết document về.

Vì thế, xử lý lỗi timeout phải bao quanh **quá trình thực sự lấy dữ liệu**, không chỉ quanh câu lệnh tạo cursor.

### 5.2. maxTimeMS, limit, batchSize và comment

~~~javascript
(() => {
  const events = db.getSiblingDB("mongo_timeout_lab")
    .getCollection("lab_events");

  const cursor = events.find(
      {
        dataset: "cursor-timeout-v1",
        tenantId: "t001",
        status: "open"
      },
      { _id: 1, title: 1, occurredAt: 1 }
    )
    .sort({ occurredAt: -1, _id: -1 })
    .limit(3)
    .batchSize(2)
    .maxTimeMS(1500)
    .comment("row144-list-open");

  try {
    printjson(cursor.toArray());
  } finally {
    cursor.close();
  }
})();
~~~

**Kết quả mong đợi** từ dữ liệu seed: **ev-018**, **ev-017**, **ev-015** theo occurredAt giảm dần.

Ý nghĩa từng thành phần:

| Thành phần | Mục đích |
| --- | --- |
| **find(filter, projection)** | Chọn document/field phù hợp |
| **sort({occurredAt:-1,_id:-1})** | Xác định thứ tự trang ổn định khi trùng thời điểm |
| **limit(3)** | Chỉ lấy tối đa ba document trong kết quả |
| **batchSize(2)** | Yêu cầu cursor đưa kết quả theo batch nhỏ hơn |
| **maxTimeMS(1500)** | Đặt giới hạn thời gian phía server cho thao tác truy vấn |
| **comment("row144-list-open")** | Gắn nhãn giúp xác định thao tác trong quan sát/log |
| **close()** | Giải phóng cursor khi không còn cần sử dụng |

**limit(3) và batchSize(2) không phải timeout.** Một query tìm ba document vẫn có thể chậm nếu phải xử lý rất nhiều dữ liệu để tìm, lọc hoặc sort; ngược lại, truy vấn trả hàng trăm document cũng có thể rất nhanh nếu index phù hợp.

### 5.3. Cần đặt maxTimeMS trước khi tiêu thụ cursor

Các phương thức như **sort**, **limit**, **batchSize** và **maxTimeMS** nên được cấu hình **trước khi** bắt đầu đọc dữ liệu. Sau khi cursor đã thực thi, không nên giả định bạn có thể sửa toàn bộ tùy chọn và áp chúng hồi tố cho các batch đã lấy.

Ví dụ đúng trình tự:

~~~javascript
const events = db.getSiblingDB("mongo_timeout_lab")
  .getCollection("lab_events");

const cursor = events.find({
  dataset: "cursor-timeout-v1",
  tenantId: "t001"
});

cursor.sort({ occurredAt: -1, _id: -1 });
cursor.limit(5);
cursor.maxTimeMS(1000);

try {
  printjson(cursor.toArray());
} finally {
  cursor.close();
}
~~~

### 5.4. Khi maxTimeMS quá nhỏ

~~~javascript
db.getSiblingDB("mongo_timeout_lab")
  .getCollection("lab_events")
  .find({ dataset: "cursor-timeout-v1" })
  .maxTimeMS(1)
  .toArray();
~~~

Đây chỉ là **minh họa cú pháp**, không phải test timeout đáng tin cậy. Query trên 24 document có thể hoàn tất trước khi đạt 1 ms, hoặc chi phí khởi tạo/lập kế hoạch khác nhau giữa các lần chạy. Không tuyên bố lệnh trên chắc chắn tạo lỗi.

Để đánh giá cơ chế timeout trong dự án thật, nên kiểm thử trên workload đại diện và có môi trường kiểm thử cô lập, sử dụng đo đạc/chẩn đoán thay vì cố tình tạo tác vụ gây nghẽn production.

## 6. maxTimeMS cho aggregation và các lệnh khác

### 6.1. Aggregation pipeline

Ví dụ đếm event theo status:

~~~javascript
db.getSiblingDB("mongo_timeout_lab")
  .getCollection("lab_events")
  .aggregate(
    [
      {
        $match: {
          dataset: "cursor-timeout-v1",
          tenantId: "t001"
        }
      },
      {
        $group: {
          _id: "$status",
          count: { $sum: 1 }
        }
      },
      { $sort: { _id: 1 } }
    ],
    {
      maxTimeMS: 1200,
      comment: "row144-status-summary"
    }
  ).toArray();
~~~

Aggregation có thể tiêu tốn thời gian ở các stage như **$match**, **$group**, **$sort**, **$lookup**, hoặc khi phải quét lượng lớn dữ liệu. **maxTimeMS** giúp giới hạn thực thi nhưng không thay thế giới hạn số document, projection và index phù hợp.

Trong **mongosh**, cách đặt maxTimeMS cho aggregation có thể là tùy chọn trong đối số **options** như trên. Ở các driver khác, cú pháp khác nhau nhưng ý tưởng là cùng truyền giới hạn vào operation.

### 6.2. Dùng trực tiếp lệnh find

Khi cần nhìn cấu trúc command:

~~~javascript
const lab = db.getSiblingDB("mongo_timeout_lab");

const result = lab.runCommand({
  find: "lab_events",
  filter: {
    dataset: "cursor-timeout-v1",
    tenantId: "t001",
    status: "open"
  },
  sort: { occurredAt: -1, _id: -1 },
  limit: 3,
  batchSize: 3,
  maxTimeMS: 1500,
  comment: "row144-direct-find-command"
});

printjson(result);
~~~

Kết quả của lệnh **find** dạng command gồm thông tin cursor và **firstBatch**. Nếu server trả cursor ID khác 0 vì vẫn còn dữ liệu, client có thể cần **getMore** và **killCursors** để quản lý vòng đời; đó là lý do thông thường nên dùng cursor API của driver thay vì tự quản lý nhiều command ở ứng dụng.

### 6.3. Không đánh đồng getMore với lệnh find ban đầu

Một truy vấn trả về nhiều document có thể được chia thành nhiều batch:

~~~text
find / firstBatch
    |
    +-- batch 1
    |
    +-- getMore -> batch 2
    |
    +-- getMore -> batch 3
    |
    +-- kết thúc hoặc đóng cursor
~~~

**maxTimeMS không nên được hiểu đơn giản là một chiếc đồng hồ end-to-end bao toàn bộ việc client đọc từng batch, xử lý từng document và chờ mạng.** Quy tắc timeout cho getMore và cursor dài hạn có thể khác theo loại cursor, tùy chọn driver và phiên bản MongoDB.

Đặc biệt, **tailable/awaitData cursor** dùng để chờ dữ liệu mới có **maxAwaitTimeMS** với mục đích riêng. Không dùng maxAwaitTimeMS thay thế maxTimeMS của truy vấn thông thường, và không áp quy tắc của cursor tailable cho phân trang HTTP.

Nếu API phải hoàn tất trong hai giây, cần thêm **deadline tổng ở phía client**, bất kể cursor có một hay nhiều batch.

## 7. Xử lý timeout khi đọc cursor

### 7.1. Bắt lỗi ở thời điểm tiêu thụ kết quả

Ví dụ mongosh:

~~~javascript
(() => {
  const events = db.getSiblingDB("mongo_timeout_lab")
    .getCollection("lab_events");

  const cursor = events.find({
      dataset: "cursor-timeout-v1",
      tenantId: "t001",
      status: "open"
    })
    .sort({ occurredAt: -1, _id: -1 })
    .limit(20)
    .batchSize(5)
    .maxTimeMS(1500);

  try {
    const documents = cursor.toArray();
    print("Đọc thành công " + documents.length + " document");
  } catch (error) {
    if (
      error.code === 50 ||
      error.codeName === "MaxTimeMSExpired"
    ) {
      print("Truy vấn hết ngân sách maxTimeMS");
    } else {
      print("Lỗi truy vấn khác: " + error.message);
      throw error;
    }
  } finally {
    cursor.close();
  }
})();
~~~

Đoạn này thường không tạo timeout vì bộ dữ liệu quá nhỏ; chức năng chính là thể hiện **mẫu xử lý lỗi và cleanup**. Trong ứng dụng thật, không nên bắt mọi lỗi rồi hiển thị “truy vấn quá chậm”: lỗi kết nối, lỗi cú pháp, quyền truy cập và thao tác bị hủy phải được phân loại khác nhau.

### 7.2. Nếu đã stream một phần kết quả?

Giả sử API stream 100 document, sau 60 document thì nhận lỗi timeout hoặc hủy từ client. Khi ấy một phần dữ liệu **đã rời khỏi server**. Nếu API yêu cầu mỗi trang trả về một danh sách hoàn chỉnh, nên **đọc đủ một trang vào bộ nhớ có giới hạn** trước khi trả response thành công. Nếu giao thức chủ động stream, cần quy ước:

- Client biết stream đã hoàn tất hay bị ngắt giữa chừng.
- Bản ghi được gửi trước đó có thể đã được xử lý; không được tự giả định “chưa có gì xảy ra”.
- Cursor và tài nguyên liên quan được đóng khi client mất kết nối.
- Mỗi trang/đợt có khóa định danh và thứ tự đủ ổn định nếu phải tiếp tục.

Đây là thiết kế giao thức phía ứng dụng, không phải một tính năng mà maxTimeMS tự giải quyết.

### 7.3. Không retry vô điều kiện

Khi nhận MaxTimeMSExpired, chạy lại ngay với cùng filter, cùng index và cùng tải cao có thể chỉ khiến database tốn thêm tài nguyên. Trước khi retry:

1. Kiểm tra request còn cần kết quả không.
2. Kiểm tra còn ngân sách thời gian không.
3. Đánh giá lỗi tạm thời hay truy vấn vốn chậm vì thiết kế.
4. Nếu thật sự cần retry, giới hạn số lần và có backoff phù hợp.
5. Ghi metric của cả lần đầu và lần retry; tránh biến một request chậm thành hàng loạt query chậm.

Đối với **read-only pagination**, retry có thể hợp lý trong một số tình huống tạm thời. Với **ghi dữ liệu**, phải xem idempotency, transaction và trạng thái thực thi; không áp nguyên mẫu retry truy vấn đọc sang lệnh ghi.

## 8. Đóng cursor khi ứng dụng không cần kết quả nữa

### 8.1. Vòng đời cursor

Cursor giúp MongoDB trả một tập kết quả theo nhiều batch, tránh buộc client tải toàn bộ dữ liệu ngay. Cursor có thể nắm giữ tài nguyên ở phía client/server giữa các lần lấy batch.

Các trường hợp cần đóng rõ ràng:

- Người dùng hủy tìm kiếm hoặc rời trang.
- HTTP request đã timeout trước khi đọc hết kết quả.
- Code đã có đủ N document để trả trang.
- Có exception trong khi duyệt hoặc xử lý document.
- Ứng dụng chủ động chấm dứt luồng stream.

Mẫu mongosh:

~~~javascript
(() => {
  const c = db.getSiblingDB("mongo_timeout_lab")
    .getCollection("lab_events");

  const cursor = c.find({
      dataset: "cursor-timeout-v1",
      tenantId: "t001"
    })
    .sort({ occurredAt: -1, _id: -1 })
    .batchSize(2)
    .maxTimeMS(1500);

  try {
    if (cursor.hasNext()) {
      printjson(cursor.next());
    }

    // Ứng dụng không muốn đọc phần còn lại.
  } finally {
    cursor.close();
  }
})();
~~~

**close()** là thao tác cleanup: driver/shell có thể gửi **killCursors** khi cursor phía server còn mở. Khi cursor đã đọc hết và ID server trở về 0, việc đóng tiếp không có gì bất thường.

Tuy nhiên, **đóng cursor không giống hủy ngay một câu lệnh đang thực thi** trong mọi trạng thái, đặc biệt khi lời gọi mạng chưa trả hoặc server đang ở giữa một tác vụ nặng. Việc phát tín hiệu hủy, xử lý tại điểm ngắt và thời điểm tài nguyên thực sự được giải phóng còn phụ thuộc driver/server.

### 8.2. close() không phải rollback

Nếu query là read-only, đóng cursor chủ yếu giải phóng tài nguyên. Nếu ứng dụng đã thực hiện các write trước đó, đóng cursor đọc không tự hoàn tác các write. Tương tự, client hủy HTTP response không đồng nghĩa transaction phía server được rollback nếu ứng dụng không quản lý vòng đời transaction đúng cách.

Luôn phân biệt **ngừng đọc kết quả**, **ngắt query đang chạy**, **rollback transaction** và **khôi phục document đã thay đổi**.

## 9. Hủy yêu cầu từ phía ứng dụng: AbortSignal và deadline

### 9.1. Tình huống người dùng rời trang

Hãy giả sử người dùng đang xem trang lịch sử, bấm sang màn hình khác trước khi truy vấn hoàn tất. Mục tiêu hợp lý:

1. Client phát tín hiệu rằng response không còn cần nữa.
2. API hủy/đóng những tác vụ read còn đang hoạt động nếu driver hỗ trợ.
3. Server không tiếp tục giữ cursor hoặc làm việc không cần thiết lâu hơn mức có thể tránh.
4. API không trả một lỗi 500 do “người dùng đã tự hủy” như thể đó là lỗi hỏng hệ thống.

Trong các driver có hỗ trợ cơ chế cancellation, một **AbortSignal** có thể được truyền vào thao tác. Ví dụ dưới đây minh họa **MongoDB Node.js driver trong phiên bản hỗ trợ tùy chọn signal**.

### 9.2. Ví dụ Node.js: hủy một truy vấn đọc

~~~javascript
// collection: MongoCollection từ MongoDB Node.js driver.
// Truyền signal cho thao tác khi phiên bản driver hỗ trợ.
async function loadOpenEventPage(collection, signal) {
  const cursor = collection.find(
      {
        dataset: "cursor-timeout-v1",
        tenantId: "t001",
        status: "open"
      },
      {
        projection: { _id: 1, title: 1, occurredAt: 1 },
        maxTimeMS: 1200,
        batchSize: 5,
        signal: signal,
        comment: "row144-node-list-page"
      }
    )
    .sort({ occurredAt: -1, _id: -1 })
    .limit(10);

  try {
    return await cursor.toArray();
  } finally {
    await cursor.close();
  }
}
~~~

Ở đây **maxTimeMS** nhắm tới giới hạn phía server, còn **signal** cho driver biết lời gọi có thể bị hủy từ phía client. Hai cơ chế bổ sung cho nhau, không thay thế nhau.

Một deadline ví dụ:

~~~javascript
async function loadPageWithDeadline(collection) {
  const controller = new AbortController();

  // Deadline minh họa phía client: 1.800 ms.
  const timer = setTimeout(() => {
    controller.abort();
  }, 1800);

  try {
    return await loadOpenEventPage(collection, controller.signal);
  } finally {
    clearTimeout(timer);
  }
}
~~~

Để gắn vào HTTP request thật, ứng dụng phải **liên kết tín hiệu ngắt kết nối/hủy request với controller hoặc signal** theo framework đang dùng. Nếu request đã bị hủy từ phía gọi, không nên tạo một controller mới mà bỏ qua tín hiệu đó.

Lưu ý thực tế:

- API hỗ trợ **AbortSignal** khác nhau giữa các phiên bản MongoDB driver; phải dùng phiên bản có hỗ trợ và xem đúng tài liệu của driver.
- Tùy driver, abort có thể làm gián đoạn I/O và **đóng kết nối mạng**, khiến driver phải tạo kết nối thay thế. Không nên coi abort liên tục là công cụ thay thế tối ưu index.
- Ở phía server, cancellation không luôn diễn ra tức thời; MongoDB phải tới điểm kiểm tra ngắt thích hợp.
- Nếu cursor đã trả kết quả trước khi abort, điều đó là bình thường.
- Việc **await cursor.close()** trong finally vẫn là một phần cleanup cần thiết khi API cho phép.

### 9.3. Tránh tự tạo hàng loạt timeout cho cùng một yêu cầu

Một API có thể có thời hạn phía HTTP gateway, middleware, MongoDB driver và server. Nếu từng lớp dùng ngân sách không liên quan, kết quả sẽ khó dự đoán. Ví dụ gateway timeout sau 2 giây nhưng driver vẫn chờ 30 giây sẽ tạo truy vấn mồ côi sau khi client đã mất kết nối.

Nên thiết kế theo nguyên tắc **deadline truyền xuống**:

~~~text
Client deadline
      |
      v
API request deadline
      |
      +---- Xác thực/kiểm tra quyền
      |
      +---- Tính thời gian còn lại
      |
      +---- MongoDB operation maxTimeMS
      |        + Abort/cancellation signal
      |
      +---- Đóng cursor / trả response nếu còn thời gian
~~~

Không đặt maxTimeMS đúng bằng toàn bộ deadline HTTP nếu API còn cần thời gian để gửi response và cleanup. Cũng không buộc mọi query đều có ngưỡng quá nhỏ đến mức các truy vấn hợp lệ thường xuyên bị cắt.

## 10. Hủy một thao tác đang chạy từ phía MongoDB

### 10.1. Quan sát truy vấn đang hoạt động

Người vận hành có thể kiểm tra các operation đang chạy bằng **currentOp**, hoặc aggregation stage **$currentOp** trong môi trường/quyền được hỗ trợ. Nên gắn **comment** cho query để nhận diện thao tác trong log và monitoring.

Ví dụ gắn comment:

~~~javascript
db.getSiblingDB("mongo_timeout_lab")
  .getCollection("lab_events")
  .find({
    dataset: "cursor-timeout-v1",
    tenantId: "t001"
  })
  .comment("row144-observe-own-query")
  .maxTimeMS(1500)
  .toArray();
~~~

Để xem operation, người có quyền quản trị phù hợp có thể dùng:

~~~javascript
// Chạy trong phiên mongosh có quyền quan sát operations.
db.currentOp({
  active: true,
  "command.comment": "row144-observe-own-query"
});
~~~

Cấu trúc thông tin được hiển thị và khả năng lọc có thể khác theo phiên bản, topology và cách operation được biểu diễn; với thao tác hoàn thành nhanh như lab, bạn có thể **không kịp thấy operation**. Không nên tự tạo query gây tải nặng chỉ để nó xuất hiện trong currentOp.

### 10.2. killOp: công cụ vận hành, không phải cơ chế hủy HTTP mặc định

MongoDB có lệnh **killOp** để yêu cầu dừng một operation cụ thể sau khi đã xác định opid. Đây là thao tác quản trị, cần quyền phù hợp và **không bảo đảm ngắt tức thời**. Chỉ thực hiện khi đã xác minh chính xác operation là của mình hoặc được phép can thiệp.

Mẫu minh họa có chặn chạy nhầm:

~~~javascript
// Đọc opid của CHÍNH thao tác được phép hủy từ currentOp.
// Thay null bằng opid được xác minh thủ công trước khi chạy.
const confirmedOpId = null;

if (confirmedOpId === null) {
  throw new Error(
    "Chưa xác minh opid; không được hủy operation khác"
  );
}

printjson(
  db.adminCommand({
    killOp: 1,
    op: confirmedOpId
  })
);
~~~

Các bước vận hành an toàn:

1. Dùng **comment** và thông tin kết nối/namespace/query để nhận diện operation.
2. Xác minh nó thuộc đúng môi trường và đúng yêu cầu cần hủy.
3. Chỉ định **một opid cụ thể**, không viết script quét rồi kill hàng loạt tùy ý.
4. Gửi lệnh hủy bằng tài khoản có quyền tương ứng.
5. Kiểm tra lại currentOp và trạng thái ứng dụng; xử lý việc operation có thể đã hoàn thành trước lúc gửi kill.

Nếu có sharding, thao tác mongos/mongod và cách tra opid có thể khác. Không suy luận từ ví dụ một instance rằng killOp ở mọi topology đều hoạt động giống hệt nhau.

### 10.3. killCursors khác killOp thế nào?

| Cơ chế | Đối tượng | Khi nên dùng |
| --- | --- | --- |
| **cursor.close()** từ client | Cursor mà ứng dụng đang sở hữu | Dừng tiêu thụ và cleanup bình thường |
| **killCursors** | Server cursor có ID xác định | Giải phóng cursor chưa được đóng/đã bỏ không |
| **killOp** | Operation đang chạy có opid xác định | Can thiệp vận hành với quyền và kiểm soát |
| **maxTimeMS** | Thao tác query theo ngân sách server | Giới hạn thời gian khi thực thi |
| **Client abort/deadline** | Lời gọi đang chờ và I/O phía ứng dụng | Khi người dùng hủy hoặc request hết hạn |

**Cursor ID không phải opid**. Không lấy ID của cursor rồi gửi trực tiếp cho killOp, hoặc lấy opid gửi cho killCursors. Chúng giải quyết hai lớp quản lý tài nguyên khác nhau.

## 11. maxTimeMS và phân trang

### 11.1. Kết hợp limit, sort, index và maxTimeMS

Trang lịch sử nên được thiết kế theo một bộ lọc đủ chọn lọc và một thứ tự ổn định, ví dụ:

~~~javascript
const c = db.getSiblingDB("mongo_timeout_lab")
  .getCollection("lab_events");

const page = c.find(
    {
      dataset: "cursor-timeout-v1",
      tenantId: "t001",
      status: "open"
    },
    { _id: 1, title: 1, occurredAt: 1 }
  )
  .sort({ occurredAt: -1, _id: -1 })
  .limit(3)
  .maxTimeMS(1200)
  .toArray();

printjson(page);
~~~

Từ dữ liệu seed, trang đầu là **ev-018, ev-017, ev-015**. **_id** được thêm làm khóa phân biệt khi hai document có cùng occurredAt.

### 11.2. Deep skip có thể chậm dù limit rất nhỏ

~~~javascript
// Ví dụ ý tưởng phân trang offset khi dữ liệu lớn:
db.getSiblingDB("mongo_timeout_lab")
  .getCollection("lab_events")
  .find({
    dataset: "cursor-timeout-v1",
    tenantId: "t001",
    status: "open"
  })
  .sort({ occurredAt: -1, _id: -1 })
  .skip(100000)
  .limit(10)
  .maxTimeMS(1200)
  .toArray();
~~~

Với lab chỉ có 24 document, ví dụ trả mảng rỗng. Trên collection lớn, **skip(100000)** có thể khiến MongoDB phải đi qua lượng lớn kết quả trước khi trả 10 document, nên maxTimeMS có thể bị chạm dù limit = 10.

**maxTimeMS không sửa bản chất của deep pagination**. Nếu truy cập những trang sâu thường xuyên, cân nhắc **keyset/cursor pagination** bằng khóa sort.

### 11.3. Keyset pagination với mốc (occurredAt, _id)

Để lấy trang kế tiếp sau trang đầu:

~~~javascript
(() => {
  const c = db.getSiblingDB("mongo_timeout_lab")
    .getCollection("lab_events");

  const base = {
    dataset: "cursor-timeout-v1",
    tenantId: "t001",
    status: "open"
  };

  const firstPage = c.find(
      base,
      { _id: 1, title: 1, occurredAt: 1 }
    )
    .sort({ occurredAt: -1, _id: -1 })
    .limit(3)
    .maxTimeMS(1200)
    .toArray();

  print("Trang đầu:");
  printjson(firstPage);

  if (firstPage.length === 0) {
    return;
  }

  const last = firstPage[firstPage.length - 1];

  const nextFilter = {
    ...base,
    $or: [
      { occurredAt: { $lt: last.occurredAt } },
      {
        occurredAt: last.occurredAt,
        _id: { $lt: last._id }
      }
    ]
  };

  const secondPage = c.find(
      nextFilter,
      { _id: 1, title: 1, occurredAt: 1 }
    )
    .sort({ occurredAt: -1, _id: -1 })
    .limit(3)
    .maxTimeMS(1200)
    .toArray();

  print("Trang kế tiếp:");
  printjson(secondPage);
})();
~~~

Kết quả dự kiến:

- **Trang đầu:** ev-018, ev-017, ev-015.
- **Trang sau:** ev-014, ev-013, ev-011.

Keyset pagination dựa trên dấu mốc của trang trước nên tránh quét/bỏ qua số lượng bản ghi quá lớn chỉ để lấy trang sâu. Tuy nhiên, dữ liệu mới được chèn hoặc sửa trong khi phân trang vẫn có thể làm kết quả thay đổi; keyset không tự tạo snapshot nhất quán xuyên nhiều HTTP request.

Mỗi page vẫn cần **limit**, **maxTimeMS** và deadline client phù hợp. Với một API nhiều tenant, cursor token phải gắn với filter đã xác thực và không được cho phép người dùng chuyển tenant chỉ bằng cách sửa token.

## 12. Thiết kế response khi timeout hoặc client hủy

### 12.1. Phân loại kết quả ở tầng API

| Trạng thái | Ứng dụng nên xử lý |
| --- | --- |
| Query thành công và đủ trang | Trả dữ liệu và nextCursor thích hợp |
| MongoDB báo **MaxTimeMSExpired** | Trả trạng thái lỗi timeout phù hợp, ghi metrics; không coi dữ liệu rỗng là kết quả thành công |
| Client hủy request | Dừng công việc không còn cần, đóng cursor và ghi nhận cancellation |
| Driver/socket timeout | Phân loại lỗi kết nối/IO; có thể không biết server đã dừng ngay chưa |
| Chỉ nhận được một phần batch stream | Báo stream không hoàn tất, không tự coi đó là trang đầy đủ |
| Truy vấn trả rỗng hợp lệ | Trả danh sách rỗng bình thường; không gắn nhầm nhãn timeout |

**Không trả [] chỉ vì query timeout.** Danh sách rỗng là kết quả nghiệp vụ hợp lệ và có thể bị cache; nếu thay một lỗi timeout bằng [], người dùng sẽ hiểu sai rằng không có bản ghi.

Tương tự, một request bị client chủ động hủy không nên bị ghi thống kê cùng nhóm với lỗi 500 nội bộ nếu hệ thống có khả năng phân biệt.

### 12.2. Dừng công việc phía ứng dụng

Một quy trình xử lý lý tưởng:

~~~text
HTTP request bắt đầu
    |
    v
Xác thực -> xác định tenant -> tính deadline còn lại
    |
    v
Khởi tạo MongoDB cursor với filter, sort, limit, maxTimeMS
    |
    +---- Query xong -> đọc đủ trang -> close -> trả 200
    |
    +---- MaxTimeMSExpired -> close -> trả lỗi timeout
    |
    +---- Client hủy -> phát signal -> close -> ngừng xây response
    |
    +---- Lỗi khác -> close -> log và trả lỗi tương ứng
~~~

Trong mọi nhánh, **finally/cleanup** phải được chạy. Nếu dùng connection pool, việc bỏ rơi cursor hoặc treo I/O quá lâu có thể khiến những request khác thiếu kết nối và bị chậm dây chuyền.

### 12.3. Deadline cho các request liên tiếp

Nếu màn hình gọi ba API liên tiếp, deadline của một API riêng lẻ không mặc nhiên giới hạn tổng thời gian người dùng chờ. Ứng dụng có thể:

- Thiết kế truy vấn để trả đúng dữ liệu màn hình cần trong một endpoint.
- Cho phép cancel các request phụ khi người dùng chuyển trang.
- Ưu tiên những truy vấn ảnh hưởng trực tiếp đến việc render trang hiện tại.
- Không tái sử dụng một timeout rất dài cho từng bước bên trong một request có deadline ngắn.

Mục tiêu là giảm **công việc không còn giá trị**, không chỉ chuyển lỗi từ database sang tầng HTTP.

## 13. Vận hành và quan sát truy vấn bị timeout

### 13.1. Những metric nên theo dõi

Không nên kết luận “đã thêm maxTimeMS nên hiệu năng đã ổn”. Cần theo dõi:

| Metric | Câu hỏi |
| --- | --- |
| Tỷ lệ lỗi **MaxTimeMSExpired** theo API/query shape | Query nào đang chạm ngân sách thường xuyên? |
| **p50/p95/p99 query latency** | Truy vấn bình thường và đuôi chậm ra sao? |
| **totalDocsExamined / nReturned** | Có quét quá nhiều document để trả ít kết quả không? |
| **totalKeysExamined** | Index scan có thực sự chọn lọc không? |
| Tần suất **COLLSCAN**, **SORT**, spill | Có thiếu index hoặc sort khó thực hiện không? |
| Số lượng **cursors** mở/đóng, cursor tồn tại lâu | Có cursor bị bỏ quên hoặc stream quá lâu không? |
| Tỷ lệ **client abort** và deadline HTTP | Người dùng có thường rời trang trước khi có kết quả không? |
| Connection pool pressure, network errors | Cancellation có khiến pool/IO bất ổn không? |
| Tỷ lệ retry và tổng số operations/request | Một timeout có gây bão retry không? |

Nên gắn nhãn query shape hoặc **comment** đủ rõ để liên hệ giữa API, request tracing và MongoDB logs, nhưng **không đặt dữ liệu nhạy cảm** như token hoặc thông tin định danh cá nhân vào comment. Dữ liệu quan sát có thể được lưu trong log/metrics và được nhiều người vận hành truy cập.

### 13.2. Chọn ngưỡng dựa trên tải thực

Nếu p99 truy vấn bình thường là 800 ms, đặt maxTimeMS = 10 ms sẽ tạo lỗi hàng loạt. Nếu SLA toàn API là 2 giây nhưng query được phép chạy 30 giây, ngân sách lại không liên quan đến nhu cầu người dùng.

Cách làm thực tế:

1. Đo latency và độ phân bố của các truy vấn quan trọng.
2. Tối ưu query shape, projection, index và pagination.
3. Xác định deadline từ trải nghiệm người dùng và tài nguyên hệ thống.
4. Chia ngân sách hợp lý giữa MongoDB, ứng dụng và mạng.
5. Thử nghiệm lỗi timeout/cancellation trong môi trường test.
6. Theo dõi tỷ lệ timeout sau khi triển khai để điều chỉnh có cơ sở.

**maxTimeMS là hàng rào bảo vệ**, không phải mục tiêu hiệu năng. Một truy vấn luôn mất 1.190 ms khi giới hạn là 1.200 ms vẫn có thể gây trải nghiệm kém và dùng nhiều tài nguyên.

## 14. Những hiểu lầm và lỗi thường gặp

| Hiểu lầm / hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Cấu hình maxTimeMS(1000) nghĩa API luôn kết thúc sau đúng 1 giây | maxTimeMS kiểm soát thời gian server theo điểm ngắt, không bao trùm client/network | Thêm deadline tổng và cancellation phía client |
| Query nhỏ không báo timeout với maxTimeMS(1) | Query có thể hoàn thành nhanh hơn giới hạn; test không deterministic | Không dùng lab nhỏ để chứng minh timeout chắc chắn xảy ra |
| Có limit(10) nên query không thể chậm | Có thể cần quét hoặc sort rất nhiều document trước khi trả 10 kết quả | Thiết kế index và keyset pagination |
| batchSize(10) làm timeout sau 10 document | batchSize là kích cỡ batch, không phải deadline hoặc tổng số kết quả | Dùng limit và maxTimeMS đúng mục đích |
| Chỉ catch khi tạo cursor nhưng không catch toArray/next | Cursor có thể thực thi khi bắt đầu được tiêu thụ | Đặt try/catch/finally quanh việc đọc cursor |
| Client đóng tab nhưng server vẫn có query đang chạy | HTTP cancellation chưa được truyền tới driver/server | Truyền signal phù hợp và close cursor |
| cursor.close() chắc chắn ngắt mọi operation ngay tức thời | close cleanup cursor; operation đang chạy có quy trình interrupt riêng | Kết hợp deadline, abort và quan sát server |
| maxTimeMS làm chậm query được chữa khỏi | Timeout chỉ chặn tác vụ vượt ngân sách | Xem explain, index và thiết kế truy vấn |
| Timeout được trả về thành danh sách rỗng | Ứng dụng nuốt lỗi và giả làm kết quả hợp lệ | Phân biệt lỗi timeout với kết quả không có dữ liệu |
| Thấy lỗi mạng thì khẳng định server chưa làm gì | Có thể request đã đến server nhưng response chưa về | Phân loại trạng thái không xác định; không retry ghi một cách mù quáng |
| Mọi getMore đều bị ràng buộc cùng một maxTimeMS trên toàn thời gian duyệt | Semantics cursor/getMore khác theo loại cursor/driver | Dùng deadline end-to-end; kiểm tra tài liệu driver |
| killCursors và killOp là một | Cursor ID khác operation ID | Dùng close/killCursors cho cursor, killOp cho operation đã xác minh |
| Tăng timeout thật lớn sẽ giải quyết tải cao | Query vẫn chiếm CPU/I/O lâu hơn, ảnh hưởng request khác | Giảm công việc, index phù hợp, giới hạn concurrency |
| Retry ngay mọi MaxTimeMSExpired | Có thể tạo thêm query chậm trong lúc server quá tải | Retry có giới hạn, backoff và ngân sách còn lại |

## 15. Bài tập thực hành

### Bài 1 — Phân biệt giới hạn

Một API có deadline 2.000 ms, gọi hai truy vấn MongoDB và một dịch vụ HTTP khác. Hãy giải thích vì sao đặt **maxTimeMS: 1.500** cho cả hai truy vấn không đủ bảo đảm API kết thúc trong 2.000 ms. Đề xuất cách tính **thời gian còn lại** và chính sách cleanup.

### Bài 2 — Tạo cursor với giới hạn rõ ràng

Từ bộ dữ liệu lab, viết truy vấn lấy ba event open mới nhất của tenant t001, sort theo occurredAt và _id giảm dần, batchSize hai, maxTimeMS 1.200 ms. Ghi lại ID kết quả và giải thích ý nghĩa của **limit**, **batchSize**, **maxTimeMS**.

### Bài 3 — Phân trang và deep skip

Từ lab, lấy trang đầu ba event, dùng cặp (occurredAt, _id) của event cuối để viết keyset query lấy trang sau. So sánh với skip(3).limit(3) và nêu lý do deep skip có thể đắt khi collection rất lớn.

### Bài 4 — Bắt lỗi và cleanup

Viết hàm đọc cursor bằng try/catch/finally. Phân loại **MaxTimeMSExpired**, **client abort** và **lỗi kết nối khác**. Tại sao không nên trả về mảng rỗng cho mọi lỗi? Lệnh close nên đặt ở đâu để chạy ngay cả khi toArray thất bại?

### Bài 5 — Người dùng hủy request giữa chừng

Giả sử API stream kết quả từ MongoDB theo từng batch. Sau batch thứ hai, client ngắt kết nối. Hãy vẽ luồng tín hiệu hủy từ HTTP tới MongoDB driver, cách dừng ghi response, cách đóng cursor và cách thể hiện rằng stream chưa hoàn tất.

### Bài 6 — Theo dõi operation

Gắn **comment** khác nhau cho truy vấn danh sách và truy vấn tổng hợp. Nêu cách dùng currentOp để xem operation còn chạy, vì sao lab nhỏ có thể không quan sát được chúng, và những điều kiện bắt buộc phải xác minh trước khi dùng killOp.

### Bài 7 — Chẩn đoán timeout bằng explain

Giả sử một truy vấn thực tế bị MaxTimeMSExpired liên tục. Đề xuất trình tự điều tra: collection size, nReturned, totalDocsExamined, totalKeysExamined, IXSCAN/COLLSCAN, blocking SORT, index hiện có, tần suất truy vấn và tải server. Vì sao tăng maxTimeMS có thể chỉ kéo dài thời gian chiếm tài nguyên?

### Bài 8 — Cursor dài hạn và getMore

Một API xuất báo cáo 500.000 document, nhận kết quả qua nhiều getMore. Hãy giải thích vì sao chỉ dùng maxTimeMS trên lệnh find chưa đủ làm deadline 10 giây cho toàn bộ quá trình tải và serialize dữ liệu. Đề xuất cách chia batch, kiểm tra cancellation giữa các batch và quy trình cleanup.

### Bài 9 — So sánh các mức độ hủy

Hoàn thiện bảng cho bốn sự kiện: (a) MongoDB báo lỗi maxTimeMS, (b) người dùng hủy HTTP request, (c) ứng dụng chủ động close cursor, (d) quản trị viên dùng killOp. Với mỗi sự kiện, ghi rõ ai phát tín hiệu, đối tượng bị tác động, yêu cầu quyền, cách xác định đã xử lý xong và điều gì **không được bảo đảm**.

## 16. Tài liệu MongoDB tham khảo

- MongoDB Manual — [cursor.maxTimeMS()](https://www.mongodb.com/docs/manual/reference/method/cursor.maxTimeMS/).
- MongoDB Manual — [db.collection.find()](https://www.mongodb.com/docs/manual/reference/method/db.collection.find/).
- MongoDB Manual — [db.collection.aggregate()](https://www.mongodb.com/docs/manual/reference/method/db.collection.aggregate/).
- MongoDB Manual — [getMore Command](https://www.mongodb.com/docs/manual/reference/command/getMore/).
- MongoDB Manual — [killCursors Command](https://www.mongodb.com/docs/manual/reference/command/killCursors/).
- MongoDB Manual — [db.killOp() và killOp Command](https://www.mongodb.com/docs/manual/reference/method/db.killOp/).
- MongoDB Manual — [explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Node.js Driver — [Abort Queries and Operations](https://www.mongodb.com/docs/drivers/node/current/crud/query/cursor/#abort).

**Điều cần ghi nhớ:** **maxTimeMS** đặt hàng rào thời gian cho thực thi truy vấn phía MongoDB nhưng **không thay thế deadline tổng của API**. Khi một request bị hủy, ứng dụng cần **truyền tín hiệu cancellation nếu driver hỗ trợ, ngừng xử lý kết quả và đóng cursor**. Với truy vấn phân trang, kết hợp **filter đúng, index phù hợp, limit, sort ổn định, keyset pagination, maxTimeMS và deadline client** để tránh cả việc đọc quá nhiều dữ liệu lẫn việc tiếp tục làm việc sau khi kết quả không còn cần thiết.

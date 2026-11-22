# Vòng đời cursor, `getMore` và cơ chế tải dữ liệu theo lô trong MongoDB

## 1. Vì sao truy vấn nhiều document không trả tất cả ngay lập tức?

Giả sử một ứng dụng cần lấy toàn bộ sự kiện của khách hàng trong 12 tháng. Collection MongoDB có thể chứa hàng trăm nghìn hoặc hàng triệu document. Nếu máy chủ cố gom tất cả kết quả vào một phản hồi rồi ứng dụng tải hết vào bộ nhớ, hệ thống sẽ gặp nhiều vấn đề:

- Phản hồi mạng có thể quá lớn và mất nhiều thời gian.
- Máy chủ phải duy trì hoặc tạo ra một lượng dữ liệu kết quả rất lớn trước khi gửi.
- Ứng dụng dùng nhiều bộ nhớ, dễ dừng vì thiếu RAM.
- Không thể xử lý dần tài liệu đầu tiên khi còn hàng nghìn tài liệu phía sau.
- Khi mạng bị gián đoạn, việc chuyển dữ liệu quá lớn trở nên khó kiểm soát.

MongoDB giải quyết bằng **cursor** và **batching**. Thay vì trả toàn bộ kết quả trong một lần, MongoDB thường gửi **một lô kết quả đầu tiên** và một **cursor ID**. Khi ứng dụng cần đọc tiếp, driver gửi lệnh **`getMore`** để nhận lô kế tiếp. Quá trình lặp lại cho đến khi hết kết quả hoặc cursor bị đóng.

```text
Ứng dụng/driver                      MongoDB server
       |                                   |
       |---- find hoặc aggregate --------->|
       |                                   | Lập kế hoạch, bắt đầu đọc
       |<--- firstBatch + cursor ID -------|
       |                                   |
       | Xử lý từng document trong batch   |
       |                                   |
       |---- getMore(cursor ID) ---------->|
       |                                   | Tiếp tục đọc kết quả
       |<--- nextBatch + cursor ID --------|
       |                                   |
       | Xử lý tiếp                        |
       |                                   |
       |---- getMore(cursor ID) ---------->|
       |<--- nextBatch + cursor ID = 0 ----|
       |                                   |
       | Hết dữ liệu, kết thúc đọc         |
```

Đây là **luồng logic**. MongoDB driver thường tự gửi `getMore`; lập trình viên không phải tự quản lý số cursor trong những ứng dụng thông thường.

### Ba khái niệm cần tách biệt

| Khái niệm | Nghĩa |
|---|---|
| **Query** | Yêu cầu tìm hoặc xử lý các document, ví dụ `find({ status: "PAID" })` |
| **Cursor** | Cơ chế cho phép tiếp tục đọc kết quả của query qua nhiều lượt |
| **Batch** | Một nhóm document được truyền từ server về client trong một phản hồi |

Một cursor có thể cung cấp **nhiều batch**, mỗi batch có **nhiều document**. Cursor cũng có thể kết thúc ngay sau batch đầu tiên nếu kết quả nhỏ. Không phải mọi query đều phải chạy `getMore`.

## 2. Chuẩn bị dữ liệu mẫu

Chạy các ví dụ trên một database thử nghiệm trong **mongosh**. Tạo collection `events` chứa sáu sự kiện:

```javascript
db.events.insertMany([
  {
    _id: "E001",
    customerId: "C01",
    eventType: "LOGIN",
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: "E002",
    customerId: "C01",
    eventType: "VIEW",
    createdAt: ISODate("2026-11-01T08:05:00Z")
  },
  {
    _id: "E003",
    customerId: "C01",
    eventType: "ADD_TO_CART",
    createdAt: ISODate("2026-11-01T08:10:00Z")
  },
  {
    _id: "E004",
    customerId: "C01",
    eventType: "CHECKOUT",
    createdAt: ISODate("2026-11-01T08:15:00Z")
  },
  {
    _id: "E005",
    customerId: "C01",
    eventType: "PAYMENT",
    createdAt: ISODate("2026-11-01T08:20:00Z")
  },
  {
    _id: "E006",
    customerId: "C02",
    eventType: "LOGIN",
    createdAt: ISODate("2026-11-01T09:00:00Z")
  }
]);
```

Khi lọc `customerId: "C01"` và sắp theo `createdAt` tăng dần, ta mong đợi **năm** sự kiện `E001` đến `E005`. Trong các ví dụ tiếp theo, `batchSize: 2` giúp nhìn thấy việc trả nhiều batch, dù trong thực tế kích thước batch phù hợp thường khác.

Chỉ nên dùng collection riêng để luyện tập; không nên tạo dữ liệu thử nghiệm hoặc gửi lệnh quản trị cursor tùy ý trên dữ liệu production.

## 3. Cursor ở hai phía: client và server

Một điểm quan trọng là từ “cursor” có thể chỉ **hai đối tượng liên quan nhưng không hoàn toàn giống nhau**.

### 3.1. Cursor phía driver hoặc mongosh

Khi viết:

```javascript
const cursor = db.events
  .find({ customerId: "C01" })
  .sort({ createdAt: 1, _id: 1 });
```

biến `cursor` trong ứng dụng là **đối tượng cursor của client API**. Nó cung cấp cách lặp qua tài liệu và quản lý lấy thêm dữ liệu, thường có các phương thức như `hasNext()`, `next()`, `toArray()` hoặc `close()` tùy driver.

Các driver có thể trì hoãn việc thực thi lệnh đến lúc ứng dụng bắt đầu lặp hoặc yêu cầu kết quả. Vì vậy, không nên khẳng định chỉ cần khởi tạo một biến cursor là MongoDB đã mở cursor trên server. Thời điểm gửi lệnh phụ thuộc API và cơ chế lazy execution của driver.

### 3.2. Cursor phía MongoDB server

Máy chủ có thể duy trì **server-side cursor** để tiếp tục công việc truy vấn qua các lệnh `getMore`. Khi xử lý lệnh `find` hoặc `aggregate`, phản hồi có thể có dạng:

```javascript
{
  cursor: {
    firstBatch: [
      { _id: "E001", customerId: "C01", /* ... */ },
      { _id: "E002", customerId: "C01", /* ... */ }
    ],
    id: NumberLong("123456789"),
    ns: "demo.events"
  },
  ok: 1
}
```

Phản hồi trên là **sơ đồ minh họa**, không phải giá trị ID thực tế. Trường `ns` là namespace của collection; tên database trong ví dụ có thể khác. Server-side cursor có thể mang trạng thái thực thi và tài nguyên liên quan để đọc tiếp.

Khi driver lấy hết kết quả, cursor trên server kết thúc. Driver giữ thông tin cần thiết để biết đã nhận những document nào và còn phải gửi `getMore` hay không.

### 3.3. Không phải mỗi batch có một cursor mới

Một cursor ID được dùng để **tiếp tục cùng một luồng kết quả**. Trên cùng một lệnh truy vấn, `getMore` nhận cursor ID mà server đã cấp và trả lô tiếp theo. Khi cursor đã hết, server thường trả ID bằng **0**, biểu thị không còn server-side cursor để yêu cầu tiếp.

Không nên nhầm **cursor ID** với `_id` của document:

- `_id` xác định một document được lưu.
- `cursor.id` xác định một cursor sống tạm thời trên server, được dùng cho `getMore`.
- Cursor ID không phải khóa nghiệp vụ hay token phân trang bền vững.

## 4. Vòng đời của một cursor thông thường

Một cursor MongoDB thông thường thường trải qua các giai đoạn sau:

### Giai đoạn 1 — Tạo yêu cầu và chọn máy chủ

Ứng dụng cấu hình `find()` hoặc `aggregate()`. Driver chọn server/router phù hợp với topology, read preference và session của thao tác. Driver dùng kết nối từ connection pool khi gửi command.

### Giai đoạn 2 — Server thực thi và tạo batch đầu tiên

MongoDB phân tích filter, index, sort, pipeline và các giới hạn. Server thực hiện đủ công việc cần thiết để trả những kết quả trong batch đầu tiên. Nếu chưa hết dữ liệu, server cấp một cursor ID khác 0.

**Không nên nghĩ chỉ cần `batchSize: 2` thì server chắc chắn mới tính đúng hai document rồi dừng mọi xử lý.** Một số truy vấn có stage phải xử lý nhiều dữ liệu trước khi có thể trả kết quả đầu tiên, chẳng hạn sort không dùng được index hoặc aggregation `$group` có tính chất blocking.

### Giai đoạn 3 — Client tiêu thụ batch

Driver giải mã document BSON thành giá trị của ngôn ngữ lập trình rồi đưa cho ứng dụng. Ứng dụng có thể xử lý từng document, tạo response, ghi file, hoặc tính tổng hợp.

Trong giai đoạn này, client có thể còn document ở **buffer cục bộ** của batch vừa nhận. Gọi `next()` không nhất thiết gửi một request mạng cho mỗi document.

### Giai đoạn 4 — Gửi `getMore` khi cần

Khi batch hiện tại đã hết nhưng cursor server vẫn còn mở, driver gửi `getMore` để xin batch tiếp theo. Server tiếp tục công việc của cursor và trả `nextBatch`.

### Giai đoạn 5 — Kết thúc hoặc đóng sớm

Cursor có thể kết thúc theo nhiều cách:

- **Đọc hết tự nhiên:** server trả cursor ID = 0; driver biết đã hết kết quả.
- **Đóng sớm theo ứng dụng:** client gọi `close()` hoặc phương thức tương đương; driver có thể gửi `killCursors` để giải phóng tài nguyên server.
- **Timeout do không hoạt động:** server có thể đóng cursor nhàn rỗi theo chính sách timeout.
- **Lỗi hoặc thay đổi topology:** kết nối, server, session hoặc transaction liên quan thay đổi khiến việc tiếp tục đọc không còn hợp lệ.

Sơ đồ trạng thái logic:

```text
     Chuẩn bị query ở client
               |
               v
     Gửi find / aggregate
               |
               v
       Nhận firstBatch
               |
               +---- cursorId = 0 ----> Đọc hết batch ----> KẾT THÚC
               |
       cursorId khác 0
               |
               v
       Đọc các document đã nhận
               |
               +---- ứng dụng close() ----> killCursors / dọn dẹp
               |
               +---- lỗi / timeout -------> cursor không thể tiếp tục
               |
               v
        Gửi getMore
               |
               v
         Nhận nextBatch
               |
               +---- cursorId = 0 ----> Đọc hết batch ----> KẾT THÚC
               |
               +---- cursorId khác 0 ----> Lặp lại
```

**Cursor sống tạm thời.** Không nên lưu cursor ID làm “trang tiếp theo” trong database hoặc gửi cho frontend để sử dụng nhiều giờ sau.

## 5. Quan sát `firstBatch` và `getMore` ở mức command

Khi dùng `find()` trong mongosh, nhiều công đoạn được shell và driver thực hiện tự động. Để thấy phản hồi ở mức command, có thể gửi `find` bằng `db.runCommand()`:

```javascript
const initial = db.runCommand({
  find: "events",
  filter: { customerId: "C01" },
  sort: { createdAt: 1, _id: 1 },
  batchSize: 2
});

printjson(initial);
```

Trên bộ dữ liệu mẫu, `firstBatch` có thể chứa:

```javascript
[
  { _id: "E001", customerId: "C01", /* ... */ },
  { _id: "E002", customerId: "C01", /* ... */ }
]
```

Nếu còn dữ liệu, `initial.cursor.id` khác 0. Ta có thể dùng ID đó cho `getMore` tiếp theo:

```javascript
// Chỉ chạy khi initial.ok === 1 và initial.cursor.id khác 0.
const second = db.runCommand({
  getMore: initial.cursor.id,
  collection: "events",
  batchSize: 2
});

printjson(second);
```

Một phản hồi điển hình của `getMore` có dạng:

```javascript
{
  cursor: {
    nextBatch: [
      { _id: "E003", customerId: "C01", /* ... */ },
      { _id: "E004", customerId: "C01", /* ... */ }
    ],
    id: NumberLong("123456789"),
    ns: "demo.events"
  },
  ok: 1
}
```

Khi cần đọc E005, gửi một lệnh `getMore` nữa dùng **cursor ID từ phản hồi gần nhất**:

```javascript
// Chỉ chạy khi second.cursor.id khác 0.
const third = db.runCommand({
  getMore: second.cursor.id,
  collection: "events",
  batchSize: 2
});

printjson(third);
```

Sau lô chứa E005, cursor thông thường sẽ hết; phản hồi có thể mang `id: NumberLong("0")`. Khi cursor ID bằng 0, không gửi `getMore` tiếp với ID đó.

### 5.1. Cấu trúc command cần nhớ

| Trường | Ở command nào? | Vai trò |
|---|---|---|
| `find: "events"` | `find` | Tên collection đang tìm |
| `filter` | `find` | Điều kiện chọn document |
| `sort` | `find` | Thứ tự kết quả |
| `batchSize` | `find` / `getMore` | Yêu cầu số document tối đa mong muốn cho batch |
| `cursor.firstBatch` | Phản hồi `find` / `aggregate` | Lô document đầu tiên |
| `cursor.nextBatch` | Phản hồi `getMore` | Lô document tiếp theo |
| `cursor.id` | Phản hồi có cursor | Định danh cursor; 0 biểu thị không còn cursor trên server |
| `cursor.ns` | Phản hồi có cursor | Namespace nguồn của cursor |
| `getMore` | Command `getMore` | Cursor ID cần đọc tiếp |
| `collection` | Command `getMore` | Collection chứa cursor theo namespace |

Các mẫu phản hồi dùng ID và tên database minh họa. Trong triển khai thực tế, driver còn quản lý thông tin server, session, timeout, xác thực và ngữ cảnh giao thức để gửi `getMore` đúng chỗ. **Ví dụ `db.runCommand` chỉ để hiểu cơ chế**, không phải lời khuyên tự triển khai driver MongoDB.

### 5.2. Phải tiếp tục trên đúng server và đúng ngữ cảnh

Server-side cursor gắn với ngữ cảnh tạo ra nó: namespace, server thích hợp, session khi có và các tài nguyên thực thi. Không thể tùy tiện lấy cursor ID từ một server rồi gửi `getMore` đến một server ngẫu nhiên khác.

Driver lưu thông tin cần thiết để gửi `getMore` tới đích đúng. Trong một số chế độ như load-balanced deployment hoặc transaction, có thể có yêu cầu **pin** một connection/server trong vòng đời cursor. Khi sử dụng API driver thông thường, ứng dụng không nên tự quản lý các chi tiết định tuyến đó.

## 6. Batch size thực sự điều khiển điều gì?

### 6.1. `batchSize` là số document mục tiêu, không phải tổng số kết quả

```javascript
const cursor = db.events.find({ customerId: "C01" })
  .sort({ createdAt: 1, _id: 1 })
  .batchSize(2);

while (cursor.hasNext()) {
  printjson(cursor.next());
}
```

`batchSize(2)` yêu cầu driver/server trao đổi kết quả theo các lô nhỏ khoảng tối đa hai document, tùy giới hạn phản hồi và cơ chế thực thi. **Nó không giới hạn truy vấn chỉ trả hai document**: vòng lặp có thể đọc đủ cả năm sự kiện.

Ngược lại:

```javascript
db.events.find({ customerId: "C01" })
  .sort({ createdAt: 1, _id: 1 })
  .limit(2);
```

`limit(2)` giới hạn **tổng số document** mà truy vấn trả về. Đây là một ý nghĩa khác hoàn toàn.

### 6.2. `batchSize`, `limit` và số bản ghi của một trang API

| Khái niệm | Nó giới hạn gì? | Có tự tạo phân trang HTTP không? |
|---|---|---|
| `batchSize(100)` | Số document mong muốn mỗi batch server → driver | Không |
| `limit(100)` | Số document tối đa của truy vấn | Không tự tạo các trang kế tiếp |
| `skip(100)` | Bỏ qua 100 document đầu theo thứ tự truy vấn | Chỉ là một thành phần phân trang offset |
| `pageSize = 20` của REST API | Số phần tử muốn trả trong một response nghiệp vụ | Do ứng dụng tự thiết kế |

Một endpoint trả 20 document có thể dùng batch size 100; do `limit(20)`, nó không cần tới 100. Ngược lại, một truy vấn trả 10.000 document có thể dùng `batchSize(200)` để xử lý dần 50 batch hoặc nhiều hơn, mà không hề có trang HTTP nào.

### 6.3. Batch đầu tiên và giới hạn kích thước phản hồi

Đối với `find` và `aggregate` thông thường, MongoDB có quy tắc mặc định cho batch đầu tiên; thường tối đa **101 document hoặc 16 MiB dữ liệu**, tùy giới hạn nào đến trước nếu không chỉ định batch size khác. Các batch tiếp theo chịu giới hạn dung lượng phản hồi, và `getMore` có thể trả **ít document hơn** số yêu cầu nếu dữ liệu đủ lớn hoặc có điều kiện thực thi khác.

Điều quan trọng:

- `batchSize` là **số document**, không phải số byte hay kích thước RAM.
- Phản hồi còn bị giới hạn dung lượng, nên batch 1.000 document không được bảo đảm chứa đủ 1.000 document.
- Giới hạn kích thước **một BSON document** là 16 MiB; đây là khái niệm khác với giới hạn kích thước batch.
- Giá trị batch mặc định có thể phụ thuộc loại thao tác, phiên bản và cấu hình client; không nên viết mã phụ thuộc vào con số 101 như một hợp đồng bất biến cho mọi trường hợp.

### 6.4. `batchSize(0)` không có nghĩa đọc 0 document mãi mãi

Ở mức command `find`, `batchSize: 0` có thể dùng để yêu cầu **batch đầu tiên rỗng** nhưng vẫn tạo cursor để đọc tiếp sau đó:

```javascript
const response = db.runCommand({
  find: "events",
  filter: { customerId: "C01" },
  batchSize: 0
});

printjson(response.cursor);
```

Tùy lệnh và tình huống, phản hồi có thể chứa `firstBatch: []` và một cursor ID khác 0. Một yêu cầu `getMore` tiếp theo có thể tiếp tục lấy dữ liệu. Đây là công cụ điều khiển mức command; không nên dùng nó để biểu đạt “truy vấn không có kết quả”. Nếu thật sự chỉ cần kiểm tra tồn tại hoặc đếm, hãy dùng API phù hợp.

## 7. Cách driver tự động gọi `getMore`

Trong đa số code ứng dụng, lập trình viên thấy một vòng lặp thông thường:

```text
for mỗi document trong cursor:
    xử lý document
```

Nhưng bên dưới có thể xảy ra:

```text
Client buffer: [doc1, doc2]
next() -> doc1              [không có request mới]
next() -> doc2              [không có request mới]
next() -> buffer rỗng
Driver gửi getMore
Client buffer: [doc3, doc4]
next() -> doc3              [đọc từ buffer]
next() -> doc4              [đọc từ buffer]
...
```

Driver chịu trách nhiệm:

1. Giữ cursor ID và thông tin server/session.
2. Kiểm tra còn document đã tải trong batch hiện tại không.
3. Gửi `getMore` khi cần và khi cursor server vẫn còn sống.
4. Giải mã BSON thành đối tượng/ngôn ngữ lập trình.
5. Thông báo hết dữ liệu hoặc ném lỗi nếu việc đọc không thể tiếp tục.
6. Gửi lệnh đóng cursor khi ứng dụng đóng sớm và khi API hỗ trợ.

Vì vậy, **một lần gọi `next()` không tương đương một lần gọi mạng**. Một lần gọi `getMore` cũng không tương đương một document.

### 7.1. Mã Java Sync Driver: lặp có kiểm soát và đóng tài nguyên

Ví dụ sử dụng MongoDB Java Sync Driver và `org.bson.Document`:

```java
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.ascending;

public class ReadByBatches {
    public static void main(String[] args) {
        try (MongoClient client =
                     MongoClients.create("mongodb://localhost:27017")) {

            MongoCollection<Document> events = client
                    .getDatabase("learning")
                    .getCollection("events");

            FindIterable<Document> iterable = events
                    .find(eq("customerId", "C01"))
                    .sort(ascending("createdAt", "_id"))
                    .batchSize(100);

            // try-with-resources chủ động đóng cursor kể cả khi có lỗi xử lý.
            try (MongoCursor<Document> cursor = iterable.iterator()) {
                while (cursor.hasNext()) {
                    Document event = cursor.next();
                    System.out.println(event.toJson());
                }
            }
        }
    }
}
```

Điểm đáng chú ý:

- `FindIterable<Document>` mô tả truy vấn và tùy chọn.
- `MongoCursor<Document>` là đối tượng được lặp trong ứng dụng.
- Driver gửi `getMore` ở thời điểm cần đọc thêm batch, không phải code tự gọi `getMore`.
- `try-with-resources` bảo đảm `close()` được gọi khi kết thúc block, kể cả khi xử lý một document gặp ngoại lệ.
- `batchSize(100)` không khiến `System.out.println` chỉ in 100 dòng.

**Không nên dùng `into(new ArrayList<>())` hoặc `toArray()` cho một tập kết quả cực lớn** nếu mục tiêu là xử lý tuần tự và giới hạn RAM. Các API gom toàn bộ kết quả vào collection trong bộ nhớ sẽ tiêu thụ bộ nhớ theo số document được giữ lại, dù driver nhận từ server theo batch.

### 7.2. Mã Node.js: duyệt cursor bằng async iterator

```javascript
import { MongoClient } from "mongodb";

const client = new MongoClient("mongodb://localhost:27017");
await client.connect();

try {
  const events = client.db("learning").collection("events");
  const cursor = events
    .find({ customerId: "C01" })
    .sort({ createdAt: 1, _id: 1 })
    .batchSize(100);

  try {
    for await (const event of cursor) {
      console.log(event._id, event.eventType);
    }
  } finally {
    await cursor.close();
  }
} finally {
  await client.close();
}
```

Driver xử lý tải dữ liệu theo batch và chờ I/O bất đồng bộ. Khi ứng dụng xử lý chậm từng sự kiện, vòng lặp tự nhiên tạo một mức **backpressure** từ phía consumer: nó không phải tự gọi `getMore` liên tục theo tốc độ tối đa trong mọi tình huống. Chi tiết buffering và prefetch vẫn tùy driver và phiên bản.

### 7.3. Mã xử lý có thể dừng sớm

```java
try (MongoCursor<Document> cursor = iterable.iterator()) {
    int processed = 0;

    while (cursor.hasNext()) {
        Document event = cursor.next();
        processEvent(event); // Hàm nghiệp vụ do ứng dụng định nghĩa.

        if (++processed >= 500) {
            break;
        }
    }
}
```

Khi dừng sớm, block `try` đóng cursor thay vì để server giữ trạng thái chưa đọc hết. Nếu yêu cầu chỉ cần 500 document, thường nên đặt `limit(500)` ngay ở truy vấn khi thích hợp; điều đó còn diễn đạt chính xác ý định cho server.

## 8. `getMore`, round-trip và độ trễ

Giả sử cần đọc 10.000 document và mỗi lô chứa đúng 100 document, khi đó driver cần khoảng 100 batch, gồm lô đầu và nhiều lượt `getMore`. Đây là ví dụ làm tròn để hình dung; số batch thực tế có thể khác vì giới hạn kích thước và cơ chế thực thi.

Một batch nhỏ hơn dẫn đến **nhiều chuyến đi mạng** hơn; batch lớn hơn thường giảm số lượt `getMore` nhưng tăng bộ nhớ đệm và lượng dữ liệu chưa được tiêu thụ ở client.

### 8.1. So sánh định tính

| Batch size | Lợi thế có thể có | Chi phí/rủi ro |
|---|---|---|
| Rất nhỏ, ví dụ 1–5 | Client nhận ít document mỗi lượt, giảm lượng dữ liệu chờ xử lý | Nhiều round-trip, overhead cao |
| Vừa, ví dụ 100–500 | Thỏa hiệp giữa round-trip và bộ nhớ cho nhiều workload | Vẫn phải đo theo kích thước document và mạng |
| Rất lớn | Có thể giảm số lượt `getMore` đối với document nhỏ | Batch có thể chạm giới hạn byte; nhiều bộ nhớ và độ trễ batch |

Không có kích thước chuẩn cho mọi truy vấn. Một batch chứa 200 document kích thước vài trăm byte rất khác với 200 document kích thước vài trăm kilobyte.

### 8.2. Một công thức ước lượng đơn giản

Nếu tổng số document là `N` và batch size lý tưởng là `B`, số batch tối thiểu theo số lượng sẽ xấp xỉ:

\[
\text{batchCount} \approx \left\lceil\frac{N}{B}\right\rceil
\]

Trong thực tế, giới hạn byte và những điều kiện trả batch có thể làm số batch cao hơn. Công thức chỉ giúp định hướng, không phải dự báo chính xác số command `getMore`.

### 8.3. Tăng batch size không chữa mọi truy vấn chậm

Nếu truy vấn phải quét hàng triệu document hoặc sắp xếp một tập lớn trước khi có kết quả, chỉ tăng batch size không loại bỏ được chi phí trên server. Phải xem thêm:

- Index có hỗ trợ `filter` và `sort` không?
- Pipeline có stage blocking như một số tình huống `$sort`, `$group` không?
- Projection có trả quá nhiều trường lớn không?
- Có cần tải toàn bộ tập kết quả không?
- Ứng dụng xử lý mỗi document chậm tới mức batch đã nhận phải nằm chờ trong bộ nhớ không?
- Kết nối mạng có độ trễ lớn hoặc băng thông hạn chế không?

Đây là lý do tối ưu query plan và tối ưu batch size là hai công việc liên quan nhưng khác nhau.

## 9. Cursor timeout, session và `noCursorTimeout`

### 9.1. Vì sao MongoDB tự đóng cursor nhàn rỗi?

Một cursor chưa đọc hết có thể giữ tài nguyên phía server. Nếu ứng dụng bỏ quên cursor, server phải có cơ chế thu hồi thay vì để các cursor tồn tại vô hạn.

Trong nhiều cấu hình MongoDB, cursor thông thường có thể bị đóng sau khoảng **10 phút không hoạt động**. Giá trị này liên quan đến cấu hình timeout của máy chủ và có thể thay đổi theo môi trường. Một cursor đang được ứng dụng đọc bình thường không có nghĩa nó luôn bảo đảm sống vô hạn; nếu quá lâu không gọi `getMore`, nó có thể bị xem là nhàn rỗi.

Ví dụ:

```text
Ứng dụng nhận batch #1 lúc 10:00
Ứng dụng xử lý batch #1 rất lâu
Không có getMore trong khoảng nhàn rỗi quá giới hạn
Server dọn dẹp cursor
Ứng dụng gửi getMore lúc 10:15 -> cursor có thể không còn
```

Đây là lý do không nên coi một server cursor như một “phiên đọc” dùng lại sau hàng giờ.

### 9.2. `noCursorTimeout` không có nghĩa không thể hết hạn

MongoDB có tùy chọn **`noCursorTimeout`** (hoặc API driver tương ứng) để yêu cầu server không áp dụng cơ chế timeout nhàn rỗi thông thường đối với cursor.

```javascript
const cursor = db.events
  .find({ customerId: "C01" })
  .noCursorTimeout();
```

Tùy chọn này **không bảo đảm cursor tồn tại mãi mãi**:

- Session gắn với cursor có thể bị hết hạn.
- Kết nối, máy chủ, router hoặc topology có thể thay đổi.
- Ứng dụng có thể đóng cursor.
- Admin có thể đóng tài nguyên; sự cố máy chủ cũng làm mất ngữ cảnh cursor.

MongoDB dùng **logical sessions**. Trong nhiều cấu hình, phiên không hoạt động quá thời gian timeout của session, thường mặc định khoảng **30 phút**, có thể bị hết hạn; các cursor liên quan cũng có thể bị dọn dẹp, kể cả khi bật `noCursorTimeout`. Do vậy, không nên lấy `noCursorTimeout` làm giải pháp duy nhất cho quy trình xử lý mỗi batch trong thời gian rất dài.

### 9.3. Khi nào cân nhắc giữ cursor lâu?

Một tác vụ export lớn có thể cần đọc nhiều giờ. Tuy nhiên, chọn giữ cursor rất lâu thường làm tăng độ phức tạp phục hồi sau lỗi. Một số chiến lược thay thế:

- Đọc với tốc độ đủ đều, xử lý từng document nhanh và giữ batch vừa phải.
- Dùng một pipeline streaming để xử lý dữ liệu thay vì gom tất cả vào RAM.
- Dùng **keyset pagination** theo khóa ổn định, lưu checkpoint cuối đã xử lý, rồi chạy truy vấn mới khi cần.
- Phân chia export thành nhiều khoảng ID/ngày tháng có thể chạy lại.
- Với yêu cầu nhất quán tại một thời điểm, thiết kế snapshot/transaction hoặc cơ chế chụp dữ liệu thích hợp với giới hạn và chi phí đã được hiểu rõ.

`noCursorTimeout` nên được dùng có chủ đích, kèm quản lý session và dọn dẹp tài nguyên, không phải mặc định bật cho mọi truy vấn.

## 10. Đóng cursor bằng `close()` hoặc `killCursors`

### 10.1. Đọc hết tự nhiên

Với một query có ít kết quả, server có thể trả tất cả trong `firstBatch` và cursor ID bằng 0. Driver không cần gửi `getMore` hay `killCursors` cho server cursor đã kết thúc.

Với query lớn, sau batch cuối, `getMore` trả `cursor.id = 0`. Driver vẫn có thể còn document cuối trong batch cục bộ để ứng dụng đọc nốt.

### 10.2. Đóng sớm từ API client

Trong ứng dụng, dùng `close()` hoặc cơ chế quản lý tài nguyên của ngôn ngữ/driver. Driver sẽ cố gắng giải phóng cursor trên server nếu còn cần thiết.

Ví dụ mongosh:

```javascript
const cursor = db.events.find({ customerId: "C01" }).batchSize(2);

if (cursor.hasNext()) {
  printjson(cursor.next());
}

cursor.close();
```

Đóng sau khi chỉ đọc một document có thể giúp tránh để server giữ cursor mở trong khi ứng dụng đã quyết định dừng.

### 10.3. Lệnh `killCursors` ở mức command

Nếu đang thao tác thủ công với một cursor ID hợp lệ, MongoDB có command `killCursors`:

```javascript
// Chỉ chạy nếu initial.cursor.id khác 0 và cursor vẫn còn tồn tại.
db.runCommand({
  killCursors: "events",
  cursors: [initial.cursor.id]
});
```

Đây là minh họa cách đóng server-side cursor trong cùng database/namespace thích hợp. Không nên gửi `killCursors` đến cursor ID tự đoán hoặc cursor thuộc tiến trình khác. Ứng dụng thông thường nên để **driver** thực hiện.

### 10.4. Dọn dẹp trong mọi nhánh lỗi

Một lỗi xử lý business giữa chừng cũng có thể khiến client dừng đọc. Nếu dùng mã thủ công, đặt việc đóng cursor trong `finally` hoặc `try-with-resources`:

```javascript
const cursor = db.events.find({ customerId: "C01" });

try {
  while (cursor.hasNext()) {
    const event = cursor.next();
    // Xử lý nghiệp vụ; có thể ném ngoại lệ.
    print(event._id);
  }
} finally {
  cursor.close();
}
```

Đóng cursor là một phần của quản lý tài nguyên, tương tự đóng stream hoặc file. Tuy nhiên, việc đóng một cursor đã hết không phải lỗi; driver có thể xử lý trường hợp đó.

## 11. Cursor và phân trang: hai lớp khác nhau

Người mới thường nghĩ “cursor = pagination”. Thực tế, **cursor phục vụ tiếp tục lấy batch của một truy vấn**, còn **phân trang** là hợp đồng chia dữ liệu cho người dùng hoặc API.

### 11.1. Offset pagination bằng `skip` và `limit`

Ví dụ một API liệt kê đơn hàng có `pageSize = 20`:

```javascript
// Trang 1
db.events.find({ customerId: "C01" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(0)
  .limit(20);

// Trang 2
db.events.find({ customerId: "C01" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(20)
  .limit(20);
```

Mỗi lần gọi trang có thể tạo **một cursor mới trên server**. Đây không phải yêu cầu `getMore` của cùng một cursor giữa các lần người dùng bấm nút “trang tiếp”.

Ưu điểm của offset pagination: đơn giản, dễ cung cấp số trang và nhảy tới trang N.

Nhược điểm:

- `skip` lớn có thể tốn công duyệt/bỏ qua nhiều kết quả trước khi đến vị trí cần lấy.
- Nếu dữ liệu được chèn/xóa trong khoảng giữa hai request, kết quả có thể bị lặp hoặc bỏ sót.
- Nếu sort không có khóa phụ duy nhất, các document có cùng giá trị sort có thể xuất hiện ở thứ tự không ổn định.

### 11.2. Keyset pagination bằng khóa sắp xếp

Với dữ liệu lớn hoặc luồng cuộn liên tục, **keyset (seek) pagination** thường phù hợp hơn. Thay vì yêu cầu bỏ qua `N` document, truy vấn tiếp bằng điều kiện “sau khóa cuối của trang trước”.

Giả sử trang đầu sắp theo thời gian mới nhất, rồi theo `_id` để tránh trường hợp nhiều sự kiện có cùng timestamp:

```javascript
db.events.find({ customerId: "C01" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Ở trang tiếp theo, lưu lại:

```javascript
const lastCreatedAt = ISODate("2026-11-01T08:10:00Z");
const lastId = "E003";
```

Sau đó truy vấn những document **đứng sau** cặp khóa đó theo thứ tự giảm dần:

```javascript
db.events.find({
  customerId: "C01",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Đây là **một truy vấn mới**, không phải gửi `getMore` của cursor cũ. Token trang của ứng dụng có thể mã hóa hoặc ký giá trị của `lastCreatedAt`, `lastId` và các điều kiện lọc, thay vì để lộ/giữ nguyên server cursor ID.

Index gợi ý cho pattern này:

```javascript
db.events.createIndex({
  customerId: 1,
  createdAt: -1,
  _id: -1
});
```

Index giúp planner có lựa chọn hỗ trợ lọc theo khách hàng và thứ tự; còn hiệu năng của điều kiện `$or` cần xem bằng `explain()` trên dữ liệu thực.

### 11.3. Phân trang không tự tạo snapshot nhất quán

Nếu có dữ liệu mới chèn vào giữa các lần đọc trang, thứ tự kết quả có thể thay đổi. Keyset pagination giúp giảm vấn đề lặp/bỏ sót do dịch chuyển vị trí so với offset pagination, nhưng nó **không tự đóng băng toàn bộ dữ liệu**:

- Một document có thể bị xóa trước khi người dùng đến trang chứa nó.
- Một trường sort như `createdAt` có thể bị cập nhật.
- Điều kiện filter của document có thể thay đổi.
- Các trang độc lập có thể đọc dữ liệu ở các thời điểm khác nhau.

Nếu nghiệp vụ yêu cầu một danh sách “đúng như tại một thời điểm”, phải chọn thêm cơ chế consistency/snapshot phù hợp hoặc dùng một export có checkpoint và bất biến rõ ràng.

### 11.4. Vì sao không dùng cursor ID của MongoDB làm page token?

Cursor ID:

- Có vòng đời ngắn và có thể hết hạn do idle timeout/session.
- Có liên hệ tới server/router và ngữ cảnh tạo cursor.
- Không phải token bền vững có thể tiếp tục trên mọi máy sau failover.
- Không phải định danh một vị trí dữ liệu ổn định khi query hoặc nghiệp vụ thay đổi.

Do đó, **API pagination nên tự định nghĩa token** từ các trường có nghĩa trong thứ tự dữ liệu, với cơ chế kiểm tra tính hợp lệ và quyền truy cập. Server cursor có thể vẫn được dùng bên dưới để lấy batch của **một request API**.

## 12. Tailable cursor và `getMore` khi chưa có dữ liệu mới

Không phải cursor nào cũng là “đọc đến hết rồi đóng”. MongoDB hỗ trợ **tailable cursor** cho những trường hợp thích hợp trên **capped collection**, giúp ứng dụng tiếp tục quan sát dữ liệu mới được thêm vào.

Với cursor thông thường, khi hết dữ liệu, server trả ID = 0. Với tailable cursor, **tạm thời chưa có document** không nhất thiết có nghĩa luồng đọc đã kết thúc vĩnh viễn.

### 12.1. Tailable cursor là gì?

Tailable cursor gần với việc “theo đuôi” một file log:

```text
Tailable cursor đọc các bản ghi đã có
                |
                v
       Chưa có bản ghi mới
                |
        Cursor có thể còn mở
                |
                v
  Có bản ghi mới -> getMore trả tiếp dữ liệu
```

Khác biệt với truy vấn tìm danh sách cố định:

- Được dùng trong ngữ cảnh collection hỗ trợ kiểu tailable, thường là capped collection.
- Trật tự đọc và cách chờ thêm dữ liệu có giới hạn riêng.
- Không phải giải pháp thay thế chung cho mọi dạng theo dõi thay đổi của mọi collection.

### 12.2. `awaitData` và batch rỗng

Trong một số cơ chế tailable cursor, tùy chọn **`awaitData`** cho phép `getMore` chờ một khoảng thời gian khi chưa có dữ liệu mới, thay vì trả về ngay.

Một phản hồi `getMore` với **`nextBatch: []` và cursor ID khác 0** có thể diễn đạt “chưa có dữ liệu mới tại thời điểm này, nhưng cursor vẫn còn sống”.

Vì vậy:

> **Đừng dùng “batch rỗng” làm điều kiện duy nhất để kết luận cursor đã hết.** Cần phân biệt trạng thái cursor ID và loại cursor đang sử dụng.

Khi làm việc với change streams, driver cũng sử dụng cơ chế dựa trên cursor và `getMore` để lấy những thay đổi tiếp theo. Change streams còn có **resume token** và những quy tắc phục hồi riêng; không nên xem resume token là server cursor ID.

### 12.3. Change stream khác một cursor phân trang

```javascript
// Chỉ chạy trên deployment hỗ trợ change streams.
const stream = db.events.watch();

// Đợi sự kiện mới; đây là ví dụ quan sát liên tục.
while (stream.hasNext()) {
  printjson(stream.next());
}
```

Luồng trên có thể tiếp tục lâu dài cho đến khi đóng hoặc gặp điều kiện lỗi. Nó không phải “trang tiếp theo của 20 sự kiện hiện có”. Khi ứng dụng xây dựng một consumer change stream, cần quản lý resume token, xử lý sự kiện trùng, giám sát lag và dọn dẹp tài nguyên.

## 13. Cursor, read concern và thay đổi dữ liệu trong lúc đang đọc

Một cursor đọc nhiều batch có thể kéo dài trong lúc ứng dụng khác chèn, sửa hoặc xóa document. Điều này dẫn đến câu hỏi: **Tất cả batch có đại diện một ảnh chụp dữ liệu cố định không?**

Thông thường, **không được mặc định** điều đó chỉ vì cùng một cursor. Khả năng nhìn thấy thay đổi phụ thuộc read concern, topology, kiểu truy vấn, stage, session và bối cảnh transaction.

### 13.1. Vòng đời cursor không thay thế bảo đảm consistency

```text
Batch 1 trả các document A, B
              |
         Ứng dụng khác ghi dữ liệu
              |
Batch 2 trả những kết quả tiếp theo
```

Không thể từ sơ đồ này suy ra chắc chắn rằng batch 2 nhìn một snapshot “y hệt” batch 1, hoặc rằng mọi thay đổi mới sẽ hiện ngay lập tức. Ứng dụng phải chọn mức nhất quán theo nhu cầu thực tế.

### 13.2. Session, transaction và snapshot

Một transaction với read concern phù hợp có thể cung cấp cách nhìn nhất quán theo ranh giới transaction. Tuy nhiên, transaction dài có chi phí vận hành, giới hạn thời gian và tài nguyên; không nên dùng transaction kéo dài hàng giờ chỉ để giữ một cursor export khổng lồ.

Nếu mục tiêu là báo cáo tại thời điểm chốt ngày, các thiết kế như snapshot dữ liệu, trạng thái chốt theo kỳ, hoặc checkpoint trên khóa bất biến có thể phù hợp hơn tùy yêu cầu.

### 13.3. Đọc từ secondary

Driver có thể chọn secondary theo `readPreference`. Cursor và những lệnh `getMore` liên quan cần tiếp tục đúng ngữ cảnh đọc. Secondary có thể chưa bắt kịp primary; `readConcern: "majority"` cũng không tự đồng nghĩa “thấy thay đổi mới nhất trên primary”. Đây là vấn đề **nhân bản và consistency**, không phải điều khiển batch size.

## 14. Truy vấn aggregate cũng có cursor

Không chỉ `find()` mới trả cursor. Với `aggregate()`, driver cũng có thể lấy kết quả thành nhiều batch:

```javascript
const cursor = db.events.aggregate(
  [
    { $match: { customerId: "C01" } },
    { $sort: { createdAt: 1, _id: 1 } },
    { $project: { eventType: 1, createdAt: 1 } }
  ],
  { cursor: { batchSize: 2 } }
);

while (cursor.hasNext()) {
  printjson(cursor.next());
}
```

Trong mongosh, cách gọi aggregate và cấu hình cursor có thể được driver/shell hỗ trợ thông qua các tham số API riêng; ví dụ trên biểu đạt ý định dùng cursor với batch size 2.

### 14.1. Batch nhỏ không loại bỏ stage blocking

Xét pipeline:

```javascript
db.events.aggregate([
  { $match: { customerId: "C01" } },
  {
    $group: {
      _id: "$eventType",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

`$group` phải gom dữ liệu theo nhóm để biết số lượng. `$sort` theo `count` mới tính cũng có thể cần giữ nhiều kết quả trung gian. Do đó, việc trả batch đầu tiên có thể phải **chờ khá lâu** dù `batchSize` chỉ bằng 2.

Nói cách khác:

- **Batching** điều khiển việc **truyền kết quả**.
- **Query execution** quyết định công việc phải thực hiện để **sinh ra kết quả**.

Một pipeline có thể sinh được kết quả từng phần sớm hoặc phải xử lý rất nhiều dữ liệu trước khi có document đầu tiên; điều này phụ thuộc stage và khả năng tối ưu.

### 14.2. `$limit` không đồng nghĩa `batchSize`

```javascript
db.events.aggregate([
  { $match: { customerId: "C01" } },
  { $sort: { createdAt: -1 } },
  { $limit: 3 }
]);
```

`$limit: 3` chỉ cho ba document đi qua pipeline về sau; nếu kết quả này được nhận trong một batch hay nhiều batch là chuyện khác. Đối với phân trang, `$limit` và thứ tự sắp xếp thuộc **ngữ nghĩa kết quả**, còn batch size thuộc **cách vận chuyển kết quả**.

## 15. Theo dõi và chẩn đoán cursor trong vận hành

Không nên đoán rằng ứng dụng chậm chỉ vì `getMore` xuất hiện nhiều lần. Một quy trình kiểm tra thường bắt đầu từ việc xác định **độ trễ phát sinh ở đâu**.

### 15.1. Phân tách độ trễ

```text
Tổng thời gian ứng dụng đọc dữ liệu
    ├── chờ chọn server / lấy connection
    ├── thời gian server thực thi để trả firstBatch
    ├── thời gian truyền và giải mã batch
    ├── thời gian ứng dụng xử lý document
    ├── các lần getMore (server + mạng)
    └── thời gian chờ do backpressure / tài nguyên
```

Nếu ứng dụng xử lý từng document rất lâu, một cursor sống lâu chưa chắc do MongoDB thực thi chậm. Ngược lại, nếu server phải quét không có index, tăng batch size không giúp loại bỏ nguyên nhân.

### 15.2. Sử dụng `explain()` để xem công việc truy vấn

```javascript
db.events.find({ customerId: "C01" })
  .sort({ createdAt: 1, _id: 1 })
  .explain("executionStats");
```

Các dấu hiệu như `COLLSCAN`, `IXSCAN`, `FETCH`, số khóa/tài liệu được xem xét và số kết quả trả về giúp biết server có đang làm quá nhiều việc không. Nhưng `explain()` của query **không tự mô tả đầy đủ** thời gian xử lý từng document ở ứng dụng hoặc mọi lượt `getMore` trong một quá trình export thực.

Một index phù hợp có thể là:

```javascript
db.events.createIndex({
  customerId: 1,
  createdAt: 1,
  _id: 1
});
```

Index này tương ứng điều kiện bằng nhau của `customerId` và thứ tự `createdAt, _id` tăng dần. Việc planner có dùng nó hay không còn phụ thuộc dữ liệu và các điều kiện thực thi.

### 15.3. Quan sát lệnh `getMore`

Các nguồn quan sát có thể gồm:

- **Command monitoring của driver:** theo dõi các lệnh như `find`, `aggregate` và `getMore` cùng thời gian, số lỗi và tần suất.
- **Database profiler / diagnostic log:** trong môi trường và quyền phù hợp, giúp phân tích các command chậm, bao gồm hoạt động lấy thêm dữ liệu.
- **`serverStatus` / metrics cursor:** tùy phiên bản, có số liệu về cursor đang mở, cursor timeout và tình trạng liên quan.
- **`currentOp` hoặc `$currentOp`:** quan sát một số thao tác đang hoạt động khi có quyền giám sát.
- **Metrics ứng dụng:** số document xử lý, tổng byte, tốc độ, thời gian xử lý mỗi batch và số lần retry.

Không bật profiler mức cao trên production một cách tùy tiện; công cụ giám sát có thể có chi phí và cần quyền quản trị.

### 15.4. Những dấu hiệu đáng chú ý

| Quan sát | Giả thuyết cần kiểm tra |
|---|---|
| Nhiều `getMore`, mỗi batch rất nhỏ | Batch size nhỏ, document lớn hoặc cơ chế trả batch của workload |
| Chậm ngay trước firstBatch | Server query plan, stage blocking, chọn server hoặc kết nối |
| FirstBatch nhanh nhưng tổng export chậm | Nhiều round-trip, xử lý từng document, tốc độ mạng hoặc throttling |
| Lỗi cursor không tìm thấy | Cursor timeout, bị đóng, session hết hạn hoặc topology đổi |
| Rất nhiều cursor mở | Ứng dụng không đóng sớm, nhiều truy vấn song song hoặc các consumer sống dài |
| RAM ứng dụng tăng theo số bản ghi | Tích lũy vào list/array thay vì xử lý streaming |
| Export bị lặp/bỏ sót sau retry | Checkpoint không ổn định hoặc thuật toán phân trang sai |

Một số liệu riêng lẻ chưa đủ kết luận. Ví dụ số cursor mở lớn có thể là bình thường khi có nhiều change stream chủ động; cần đối chiếu với thiết kế và tải thực tế.

## 16. Lỗi giữa chừng: có tiếp tục cursor cũ được không?

Giả sử ứng dụng đã xử lý 10.000 document, sau đó server failover hoặc mạng đứt khi đang gửi `getMore`. Có những vấn đề cần tách:

1. **Lỗi tạm thời có thể được driver xử lý:** tùy thao tác, driver và ngữ cảnh session, một số lỗi có cơ chế thử lại theo quy tắc riêng.
2. **Cursor cũ không còn hợp lệ:** client không thể tùy tiện lấy ID cursor rồi nối lại trên một server bất kỳ.
3. **Đã xử lý một phần kết quả:** nếu tạo truy vấn mới từ đầu mà không có checkpoint, có thể xử lý trùng.

Vì vậy, với quy trình dài, nên thiết kế **khả năng phục hồi ở cấp nghiệp vụ**:

```text
Read batch
    |
    v
Xử lý document theo thứ tự khóa ổn định
    |
    v
Ghi checkpoint của document cuối đã xử lý thành công
    |
    +---- lỗi ----> Mở truy vấn mới từ checkpoint
    |
    v
Tiếp tục
```

Checkpoint không cần là cursor ID; có thể là cặp `(createdAt, _id)` hoặc một khóa duy nhất tăng đơn điệu theo thứ tự đọc. Nếu việc xử lý có tác dụng bên ngoài (ghi file, gọi API, thanh toán), cần định nghĩa cách **chống xử lý trùng** khi retry.

**Điều kiện quan trọng:** chỉ lưu checkpoint sau khi dữ liệu tương ứng đã được xử lý thành công theo quy tắc nghiệp vụ. Nếu lưu checkpoint trước rồi process chết, có thể bỏ sót document. Nếu xử lý thành công nhưng chưa lưu checkpoint, lần chạy lại có thể gặp document trùng; cần xử lý idempotency.

## 17. Những hiểu lầm phổ biến

| Hiểu lầm | Thực tế |
|---|---|
| `find()` luôn trả toàn bộ kết quả trong một lần mạng | MongoDB thường trả batch đầu và dùng `getMore` cho các batch sau |
| `batchSize(100)` nghĩa là query chỉ tìm 100 document | `batchSize` chủ yếu điều khiển lô truyền, còn `limit` giới hạn tổng kết quả |
| Mỗi `next()` là một lệnh `getMore` | Driver thường đọc từ batch đã buffer trước |
| `getMore` tạo query hoàn toàn mới giống `find` | Nó tiếp tục server cursor đã có |
| Batch đầu tiên luôn có đúng 101 document | Con số mặc định có giới hạn byte và tùy ngữ cảnh; có thể ít hơn hoặc cursor kết thúc ngay |
| Batch rỗng chắc chắn là hết dữ liệu | Tailable/change-stream cursor có thể còn sống dù chưa có dữ liệu mới |
| Cursor ID là token phân trang API bền vững | Cursor ID là tài nguyên server sống tạm thời và phụ thuộc ngữ cảnh |
| `toArray()` vẫn dùng ít RAM vì MongoDB batching | Gom toàn bộ document vào array sẽ tăng RAM của ứng dụng |
| `noCursorTimeout` giúp cursor sống mãi | Session, lỗi máy chủ, đổi topology hoặc đóng chủ động vẫn có thể kết thúc |
| Tăng batch size luôn tăng tốc query | Có thể giảm round-trip, nhưng không loại bỏ scan/sort hay ứng dụng xử lý chậm |
| Một cursor đọc nhiều batch tự đảm bảo snapshot | Consistency cần được thiết kế bằng read concern/session/transaction thích hợp |
| `skip(1000)` là lấy batch thứ 1.000 của cùng cursor | Phân trang offset là truy vấn mới với điều kiện bỏ qua kết quả |
| Không cần đóng cursor khi dừng sớm | Đóng giúp giải phóng tài nguyên server và client |

## 18. Bài tập thực hành

### Bài 1 — Quan sát batch đầu tiên và `getMore`

Với sáu sự kiện ở phần 2:

1. Gửi command `find` lọc `customerId: "C01"` và `batchSize: 2`.
2. Xem `cursor.firstBatch`, `cursor.id` và `cursor.ns`.
3. Nếu cursor ID khác 0, gửi `getMore` cùng collection với batch size 2.
4. Tiếp tục đọc đến khi cursor ID bằng 0.
5. Giải thích vì sao năm document có thể được nhận qua ba batch.

Phân biệt **số document trong batch**, **số document toàn query** và **số command được gửi**.

### Bài 2 — `batchSize` khác `limit`

Hãy thử dự đoán kết quả của ba truy vấn:

```javascript
// A
db.events.find({ customerId: "C01" }).batchSize(2);

// B
db.events.find({ customerId: "C01" }).limit(2);

// C
db.events.find({ customerId: "C01" })
  .limit(3)
  .batchSize(2);
```

Truy vấn nào có thể trả tối đa hai document? Truy vấn nào có thể trả cả năm? Truy vấn C có thể cần hơn một batch không? Thêm `sort` nếu muốn xác định chính xác thứ tự các document được chọn bởi `limit`.

### Bài 3 — Phát hiện tình huống dùng nhiều RAM

Cho hai cách xử lý Java giả định:

```java
// Cách A: gom mọi document trước khi xử lý.
List<Document> all = events.find().into(new ArrayList<>());
for (Document event : all) {
    processEvent(event);
}

// Cách B: xử lý từng document, đóng cursor khi xong.
try (MongoCursor<Document> cursor = events.find().iterator()) {
    while (cursor.hasNext()) {
        processEvent(cursor.next());
    }
}
```

Hãy giải thích sự khác biệt về bộ nhớ ứng dụng và tác động của `batchSize` với mỗi cách. Cách nào phù hợp hơn cho export hàng triệu document?

### Bài 4 — Dừng sớm và đóng cursor

Một worker chỉ muốn xử lý tối đa 50 sự kiện từ một collection rất lớn. Hãy viết code theo Java hoặc Node.js:

- Có `limit(50)` nếu logic nghiệp vụ cho phép.
- Dùng vòng lặp qua cursor.
- Bảo đảm đóng cursor kể cả khi `processEvent` phát sinh lỗi.

Giải thích vì sao không nên trông chờ cursor timeout để dọn tài nguyên.

### Bài 5 — Xây dựng API pagination

Thiết kế endpoint:

```text
GET /events?customerId=C01&pageSize=20&after=...
```

Hãy đề xuất:

1. Thứ tự sort gồm `createdAt` và `_id`.
2. Các trường được lưu trong token `after`.
3. Bộ lọc để lấy trang kế tiếp khi sort giảm dần.
4. Một index hỗ trợ điều kiện tìm kiếm.
5. Vì sao token không nên chứa trực tiếp server cursor ID?
6. Cách ứng dụng phát hiện `hasNext`, ví dụ đọc tối đa `pageSize + 1` document.

### Bài 6 — Dữ liệu thay đổi giữa các trang

Ứng dụng đọc trang 1 rồi 30 giây sau đọc trang 2. Trong thời gian đó:

- Có sự kiện mới được chèn với `createdAt` lớn nhất.
- Một sự kiện cũ bị xóa.
- Một sự kiện khác bị thay đổi `createdAt`.

Hãy phân tích rủi ro lặp/bỏ sót của offset pagination và keyset pagination. Keyset có thể giải quyết tất cả trường hợp không? Khi nào cần snapshot?

### Bài 7 — Vì sao batch size nhỏ không làm pipeline nhanh?

Một aggregation có `$match`, `$group` và `$sort` trên hàng triệu sự kiện. Ứng dụng đặt batch size 1 nhưng vẫn chờ lâu trước document đầu tiên.

Hãy giải thích:

- Những stage nào phải làm nhiều việc trước khi trả kết quả?
- Batch size đang giới hạn cái gì?
- Có thể cải thiện bằng index, lọc sớm, projection hoặc lưu số liệu tổng hợp trước không?
- Sử dụng `explain()` để tìm thông tin gì?

### Bài 8 — Xử lý lỗi và checkpoint

Một worker đọc theo `(createdAt, _id)`, đã xử lý đến `E050` và gặp lỗi `getMore`:

1. Vì sao không nên tự đoán cursor ID để nối lại?
2. Cần lưu checkpoint nào để mở truy vấn mới?
3. Nếu việc gửi email hoàn thành nhưng checkpoint chưa lưu, lần chạy lại có thể xảy ra chuyện gì?
4. Cần làm gì để bảo đảm kết quả nghiệp vụ đúng khi xử lý trùng?

## 19. Tóm lược các nguyên tắc quan trọng

**Cursor là cơ chế đọc tiếp một truy vấn**, không phải một danh sách đã tải toàn bộ vào RAM và cũng không phải token phân trang bền vững. Driver quản lý cursor phía client; MongoDB có thể duy trì server-side cursor và cursor ID để tiếp tục qua nhiều batch.

**`firstBatch` và `nextBatch` là các lô document được truyền về client.** Khi batch hiện tại đã hết và cursor server còn sống, driver gửi `getMore`. Cursor ID bằng 0 biểu thị không còn server-side cursor để tiếp tục.

**`batchSize`, `limit` và phân trang API là ba phạm vi khác nhau.** Batch size điều khiển lượng dữ liệu truyền mỗi lượt; limit điều khiển số document kết quả; phân trang quyết định cách ứng dụng chia dữ liệu cho người dùng.

**Cursor có vòng đời và chi phí tài nguyên.** Cần đóng cursor khi dừng sớm, hiểu timeout của cursor/session, không mặc định `noCursorTimeout` giải quyết mọi vấn đề, và dùng streaming khi tập kết quả lớn.

**Tối ưu batch không thay thế tối ưu query hoặc consistency.** Index, sort, pipeline, read concern, topology và logic xử lý document vẫn ảnh hưởng đến thời gian và độ đúng của dữ liệu. Với quy trình dài hoặc phân trang giữa nhiều request, hãy thiết kế khóa sắp xếp ổn định và checkpoint có khả năng khôi phục, thay vì phụ thuộc vào một server cursor sống mãi.

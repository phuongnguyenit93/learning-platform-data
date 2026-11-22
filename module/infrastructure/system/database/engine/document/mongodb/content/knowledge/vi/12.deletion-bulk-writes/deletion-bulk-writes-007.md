# Chia lô tác vụ lớn, điều tiết tốc độ và lưu mốc tiếp tục trong MongoDB

Khi một collection MongoDB có hàng triệu document, việc xóa dữ liệu cũ, cập nhật trạng thái hàng loạt hoặc chuyển đổi schema cần được tổ chức thành một **job có thể kiểm soát và tiếp tục sau sự cố**. Một lệnh thao tác với quá nhiều document có thể kéo dài, làm tăng tải CPU, I/O và replication, khó tạm dừng, đồng thời khó biết phần việc nào đã hoàn thành nếu tiến trình bị ngắt.

Ba kỹ thuật thường được kết hợp:

1. **Chia lô (batching):** mỗi lượt chỉ chọn và ghi một nhóm document có kích thước giới hạn.
2. **Điều tiết tốc độ (throttling):** giới hạn tốc độ hoặc mức song song để job không gây ảnh hưởng quá mức đến truy vấn nghiệp vụ.
3. **Lưu mốc tiếp tục (checkpointing):** ghi lại vị trí đã xử lý an toàn để lần chạy sau tiếp tục đúng chỗ.

Một job đáng tin cậy còn cần **thao tác có thể chạy lại an toàn (idempotency)**. Checkpoint và idempotency đi cùng nhau: tiến trình có thể dừng sau khi ghi dữ liệu thành công nhưng trước khi kịp lưu mốc, nên một phần công việc có thể được thực thi lại.

Bài học dùng ngữ cảnh **xóa và ghi theo lô** trong MongoDB, với ví dụ mongosh, Node.js Driver, Java Driver và cách tổ chức job xử lý hàng triệu document.

## 1. Vì sao không luôn dùng một lệnh updateMany hoặc deleteMany?

Giả sử collection **audit.events** chứa 20 triệu sự kiện. Bạn cần xóa sự kiện đã hết hạn hoặc đánh dấu những document cũ là đã lưu trữ.

Lệnh đơn giản có thể là:

~~~javascript
db.events.deleteMany({
  expiredAt: { $lte: new Date() }
});
~~~

Hoặc:

~~~javascript
db.events.updateMany(
  { status: "OLD" },
  { $set: { archived: true } }
);
~~~

Đây là các API hợp lệ. Với tập dữ liệu nhỏ, chúng có thể phù hợp. Nhưng với job lớn, cần xem xét thêm:

- **Khối lượng công việc:** phải tìm, cập nhật hoặc xóa nhiều document và các entry index liên quan.
- **Tác động đến hệ thống:** thao tác ghi tiêu thụ tài nguyên trên primary; replica set còn phải truyền và áp dụng thay đổi.
- **Khả năng quan sát:** không có checkpoint ứng dụng mô tả lô nào đã hoàn thành.
- **Khả năng ngắt và tiếp tục:** khi timeout, lỗi mạng hoặc tiến trình dừng, không thể suy ra mọi document đều đã xử lý hoặc đều chưa xử lý.
- **Thay đổi dữ liệu đồng thời:** document có thể được thêm hoặc sửa khi job đang chạy.
- **Phạm vi nguyên tử:** updateMany và deleteMany thông thường chỉ bảo đảm tính nguyên tử **trên từng document**, không phải all-or-nothing cho toàn bộ nhóm ngoài transaction.

**Một lệnh gọi API không đồng nghĩa với một transaction đa document.** Nếu một lệnh updateMany đã sửa được một phần document rồi gặp lỗi, ứng dụng cần kiểm tra và xử lý phần còn lại theo semantics của thao tác.

Chia lô không tự làm tổng công việc ít hơn. Lợi ích nằm ở việc **giới hạn độ lớn mỗi lượt, tạo điểm nghỉ và kiểm soát tiến độ**.

## 2. Ba ranh giới của một job xử lý lớn

Một job có thể tách thành những vòng xử lý:

~~~text
                          Cấu hình job cố định
                   (filter, cutoff, batch size)
                                  |
                                  v
                      Đọc checkpoint cuối
                                  |
                                  v
                        Chọn tối đa N ID
                                  |
                                  v
                     Xóa/cập nhật theo lô
                                  |
                      +-----------+-----------+
                      |                       |
                   THÀNH CÔNG                 LỖI
                      |                       |
                      v                       v
               Lưu checkpoint           Dừng, ghi lỗi
                      |                Không vượt qua
                      v                 phần chưa xử lý
                 Nghỉ/điều tiết
                      |
                      v
                   Lặp lại
~~~

Ba ranh giới cần phân biệt:

| Ranh giới | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Lô đọc** | Mỗi lượt lấy bao nhiêu ID/document cần xử lý? | 500 ID theo thứ tự _id |
| **Lô ghi** | Mỗi lần gửi bao nhiêu update/delete? | Một bulkWrite chứa tối đa 500 deleteOne |
| **Checkpoint** | Khi nào được xác nhận đã hoàn thành qua một khóa sắp xếp? | Sau khi toàn bộ bulkWrite hoàn tất thành công |

Một batch đọc có thể dẫn đến nhiều request ghi, hoặc một bulkWrite có thể chứa nhiều lệnh. **Không được đánh dấu checkpoint của cả lô khi vẫn còn lệnh ghi chưa xác định kết quả**.

## 3. Thiết kế phạm vi công việc trước khi chạy

Giả sử mỗi event có:

~~~javascript
{
  _id: ObjectId("672000000000000000000001"),
  status: "EXPIRED",
  expiredAt: ISODate("2026-01-10T00:00:00Z"),
  accountId: "ACC-01",
  payload: {
    action: "LOGIN",
    result: "SUCCESS"
  }
}
~~~

Job cần xóa các event đang có trạng thái **EXPIRED** và hết hạn tính đến một **cutoff cố định**.

~~~javascript
const cutoff = ISODate("2026-11-01T00:00:00Z");

const filter = {
  status: "EXPIRED",
  expiredAt: { $lte: cutoff }
};
~~~

Cutoff cố định làm cho ý nghĩa của cùng một job không trôi theo thời gian. Nếu mỗi lần resume lại dùng **new Date()**, phạm vi xóa sẽ tự mở rộng, có thể dẫn đến job chạy lâu hơn dự kiến và khó đối soát.

### 3.1. Những thông tin cần giữ ổn định

Một bản mô tả job nên có:

- **jobId:** định danh duy nhất, chẳng hạn cleanup-events-2026-11.
- **Collection và filter nghiệp vụ:** dữ liệu nào được phép thao tác.
- **Cutoff và các tham số bất biến:** mốc thời gian, phiên bản quy tắc.
- **Khóa sắp xếp:** trường dùng để duyệt, chẳng hạn _id.
- **Checkpoint:** khóa cuối cùng đã xử lý hoàn toàn.
- **Trạng thái:** RUNNING, PAUSED, DONE hoặc FAILED.
- **Thống kê vận hành:** số batch, thời điểm cập nhật, số lỗi, số document ghi nhận đã tác động.

Nếu một job đã chạy với cutoff A, không nên âm thầm resume cùng jobId nhưng đổi sang cutoff B. Hãy dùng job mới hoặc định nghĩa một thủ tục thay đổi phạm vi có kiểm soát.

### 3.2. Phạm vi dữ liệu có thật sự đứng yên?

Ngay cả khi cutoff cố định, các document vẫn có thể bị insert, cập nhật hoặc xóa đồng thời:

- Một event mới có thể được tạo nhưng có expiredAt cũ do nhập dữ liệu lịch sử.
- Một document có thể đổi status từ ACTIVE sang EXPIRED sau khi job đã đi qua _id của nó.
- Một document EXPIRED có thể được gia hạn, không còn đủ điều kiện xóa.

Vì vậy job dùng keyset pagination trên dữ liệu đang thay đổi thường có ngữ nghĩa **duyệt tập dữ liệu đủ điều kiện được quan sát dọc quá trình**, không phải một snapshot bất biến toàn cục.

Nếu nghiệp vụ yêu cầu xử lý **chính xác danh sách document đã tồn tại tại thời điểm bắt đầu**, cần thiết kế phạm vi snapshot, danh sách ID bất biến hoặc cơ chế ghi nhận work-item riêng. Một cutoff trên field thời gian chưa tự biến collection thành snapshot.

## 4. Chọn kích thước batch

Không có batch size tốt nhất cho mọi collection. Kích thước phù hợp phụ thuộc kích thước document, số index, kiểu update/delete, topology, network và tải ứng dụng.

Một điểm khởi đầu thực dụng có thể là vài trăm document/lượt, sau đó đo đạc:

~~~text
Batch size = 100   -> nhiều lượt nhỏ, dễ ngắt, overhead cao hơn
Batch size = 500   -> mức thử nghiệm trung bình
Batch size = 2000  -> ít vòng lặp hơn nhưng mỗi lượt có thể nặng hơn
~~~

Các con số trên **chỉ là giá trị để thử nghiệm**, không phải cấu hình tối ưu hoặc giới hạn API chính thức.

### 4.1. Batch quá nhỏ

- Mất thêm chi phí mạng và khởi tạo command.
- Tốn nhiều lần đọc checkpoint và cập nhật job.
- Tổng thời gian có thể dài dù ảnh hưởng mỗi lượt nhỏ.

### 4.2. Batch quá lớn

- Tạo đợt tăng tài nguyên I/O và replication.
- Khó kiểm soát độ trễ từng lô.
- Khi lỗi, số thao tác chưa xác định kết quả có thể nhiều hơn.
- Dễ gặp các giới hạn về kích thước thông điệp, số operation hoặc bộ nhớ driver.

MongoDB và driver có các giới hạn riêng cho write batch và kích thước BSON. Driver có thể chia một số thao tác thành nhiều batch giao thức, nhưng điều đó **không biến một bulkWrite thành transaction nguyên tử**. Ứng dụng vẫn cần tự chia công việc ở mức hợp lý.

### 4.3. Đừng nhầm limit, batchSize và write batch

| Khái niệm | Ý nghĩa |
| --- | --- |
| **find().limit(N)** | Giới hạn số document mà truy vấn chọn để xử lý trong lượt |
| **cursor.batchSize(N)** | Gợi ý số document truyền theo từng batch khi nhận cursor, không phải giới hạn tổng kết quả |
| **bulkWrite([...])** | Gửi một nhóm thao tác ghi theo API driver |
| **deleteMany(filter)** | Xóa mọi document phù hợp filter theo semantics của lệnh; không có tham số limit như find |
| **updateMany(filter, update)** | Cập nhật mọi document phù hợp; không có tham số limit cho số document |

Muốn **mỗi lượt chỉ xóa tối đa 500 document**, cách kiểm soát rõ ràng là **chọn tối đa 500 ID** rồi thực hiện deleteOne theo những ID đó, hoặc thiết kế một phạm vi xóa giới hạn được xác định trước.

## 5. Duyệt theo khóa ổn định: keyset pagination

Với collection lớn, dùng **skip()** để duyệt từng trang trong khi đang xóa có thể dẫn đến **bỏ sót document**.

Ví dụ ban đầu:

~~~text
IDs: [1, 2, 3, 4, 5, 6]
Batch size: 3
~~~

Lượt đầu:

~~~text
skip(0).limit(3) -> [1, 2, 3]
Xóa [1, 2, 3]
Còn [4, 5, 6]
~~~

Nếu lượt hai gọi:

~~~text
skip(3).limit(3) -> []
~~~

thì ba document còn lại bị bỏ qua vì sau khi xóa, chúng đã dồn lên đầu kết quả. Ngoài vấn đề tính đúng đắn, skip ở vị trí rất sâu thường tốn chi phí.

### 5.1. Dùng _id làm mốc

Đối với collection có _id cùng một kiểu dữ liệu và thứ tự được xác định nhất quán:

~~~javascript
// Lượt đầu: không có lastId.
db.events.find({
  status: "EXPIRED",
  expiredAt: { $lte: cutoff }
})
.sort({ _id: 1 })
.limit(500)
.project({ _id: 1 });
~~~

Sau khi hoàn tất một lô, lưu ID cuối cùng đã duyệt:

~~~text
lastId = ID của document thứ 500 trong lô
~~~

Lượt sau chỉ lấy document có _id lớn hơn lastId:

~~~javascript
db.events.find({
  status: "EXPIRED",
  expiredAt: { $lte: cutoff },
  _id: { $gt: lastId }
})
.sort({ _id: 1 })
.limit(500)
.project({ _id: 1 });
~~~

Đây là **keyset pagination**: vị trí tiếp tục được xác định bằng giá trị khóa, không phải số lượng record cần bỏ qua.

**_id không mặc nhiên biểu diễn thứ tự tạo chính xác theo thời gian**. ObjectId thường có thành phần thời gian nhưng không bảo đảm thứ tự toàn cục tuyệt đối trong mọi hệ thống; _id có thể là string, UUID hoặc kiểu khác. Ở đây ta dùng _id vì nó tạo ra một **thứ tự duyệt xác định**, không phải vì nó là timestamp đáng tin cậy.

### 5.2. Cần một thứ tự tổng quát, nhất quán

Trong collection không sharding, MongoDB có unique index trên _id. Với sharded collection mà _id không phải shard key, tính duy nhất của _id **không nhất thiết được bảo đảm toàn cục giữa các shard** chỉ bởi index _id. Thiết kế job phân tán phải dùng khóa đủ để nhận diện duy nhất document, thường bao gồm **shard key** và các thành phần cần thiết.

Nếu khóa sắp xếp có giá trị trùng nhau như createdAt, chỉ lưu createdAt có thể bỏ sót document nằm cùng timestamp. Cần **khóa tổng hợp** làm checkpoint.

### 5.3. Checkpoint tổng hợp (createdAt, _id)

Duyệt theo:

~~~javascript
.sort({ createdAt: 1, _id: 1 })
~~~

Giả sử mốc đã xử lý:

~~~javascript
{
  createdAt: ISODate("2026-01-01T10:00:00Z"),
  _id: ObjectId("672000000000000000000123")
}
~~~

Lần sau phải nhận:

- Document có createdAt **lớn hơn** createdAt ở mốc; hoặc
- Document có createdAt **bằng** mốc nhưng _id **lớn hơn** _id ở mốc.

~~~javascript
const lastCreatedAt = ISODate("2026-01-01T10:00:00Z");
const lastId = ObjectId("672000000000000000000123");

db.events.find({
  $or: [
    { createdAt: { $gt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $gt: lastId }
    }
  ]
})
.sort({ createdAt: 1, _id: 1 })
.limit(500);
~~~

Index phù hợp, tùy điều kiện filter và workload, có thể là:

~~~javascript
db.events.createIndex({ createdAt: 1, _id: 1 });
~~~

Cặp **(createdAt, _id)** tạo mốc xác định hơn timestamp đơn lẻ. Tuy nhiên, nếu createdAt bị sửa sau khi đã duyệt, document có thể dịch chuyển về phía trước hoặc sau checkpoint. Các trường dùng làm cursor cho job dài nên **ổn định hoặc bất biến theo hợp đồng dữ liệu**.

## 6. Ghi theo lô bằng bulkWrite

MongoDB Driver cung cấp **bulkWrite** để gửi nhiều operation trong một lần gọi API:

~~~javascript
const operations = [
  {
    deleteOne: {
      filter: { _id: ObjectId("672000000000000000000001") }
    }
  },
  {
    deleteOne: {
      filter: { _id: ObjectId("672000000000000000000002") }
    }
  },
  {
    updateOne: {
      filter: { _id: ObjectId("672000000000000000000003") },
      update: { $set: { archived: true } }
    }
  }
];

const result = db.events.bulkWrite(operations, {
  ordered: false
});

printjson(result);
~~~

Các dạng operation thường có:

- **insertOne:** thêm một document.
- **updateOne:** cập nhật một document phù hợp.
- **updateMany:** cập nhật nhiều document phù hợp.
- **replaceOne:** thay toàn bộ document.
- **deleteOne:** xóa một document phù hợp.
- **deleteMany:** xóa nhiều document phù hợp.

Với job có mục tiêu **giới hạn số document mỗi lô**, danh sách nhiều **deleteOne/updateOne theo ID đã chọn** thường dễ kiểm soát hơn một deleteMany/updateMany không giới hạn số document.

### 6.1. ordered: true và ordered: false

| Tùy chọn | Ý nghĩa | Tác động khi lỗi |
| --- | --- | --- |
| **ordered: true** | Driver/server thực thi operation theo thứ tự được chỉ định | Thường dừng các operation tiếp theo sau lỗi ghi tương ứng |
| **ordered: false** | Không yêu cầu giữ thứ tự từng operation; có thể tối ưu việc thực thi | Những operation khác vẫn có thể được thử dù một operation lỗi |

**ordered: false không bảo đảm mọi operation thành công**, cũng không tạo transaction nguyên tử. Khi lỗi, một số document có thể đã được ghi và một số khác chưa được ghi.

Đối với các operation độc lập, chẳng hạn xóa từng ID không phụ thuộc lẫn nhau, unordered có thể hữu ích. Với chuỗi thao tác cần phụ thuộc theo thứ tự, cần xem lại mô hình; ordered vẫn không cung cấp all-or-nothing.

### 6.2. Một bulkWrite không phải một transaction

Giả sử batch chứa 500 thao tác:

~~~text
Operation 1..200    thành công
Operation 201       thất bại do validation
Operation 202..500   có thể tiếp tục nếu unordered
~~~

Không được coi toàn bộ batch đã thành công chỉ vì đã có nhiều document được cập nhật. Driver có thể ném exception kèm thông tin về những operation thành công và lỗi. Khi trạng thái một batch không chắc chắn, **giữ checkpoint trước batch** và xử lý lại theo chiến lược an toàn.

Nếu cần nhiều document cùng commit hoặc rollback, multi-document transaction có thể đáp ứng một số bài toán. Tuy nhiên, **một transaction cực lớn chỉ để thay thế batching thường không phải cách xử lý tốt cho job bảo trì hàng triệu document**: transaction còn có giới hạn thời gian, tài nguyên, cạnh tranh ghi và chi phí vận hành.

## 7. Idempotency: điều kiện để resume an toàn

Giả sử job xử lý batch 500 ID và thực hiện bulkWrite thành công. Ngay sau đó, tiến trình crash **trước khi ghi checkpoint**.

~~~text
Checkpoint trước batch: lastId = 100
BulkWrite: xóa ID 101..600 thành công
Crash!
Checkpoint vẫn là 100
Restart -> chọn lại từ sau ID 100
~~~

Như vậy hệ thống có thể lặp lại một phần thao tác. **Exactly-once execution** không tự xuất hiện chỉ nhờ lưu mốc. Thiết kế thực tế thường dựa vào **at-least-once attempt + operation idempotent**, sau đó giữ đúng kết quả nghiệp vụ.

### 7.1. Xóa theo ID thường có thể chạy lại an toàn

~~~javascript
db.events.deleteOne({
  _id: ObjectId("672000000000000000000001")
});
~~~

Nếu document đã bị xóa, chạy lại deleteOne không xóa thêm document khác; kết quả thường có **deletedCount = 0**. Đây là thao tác phù hợp để retry trong job dọn dữ liệu theo ID.

Điều kiện xóa nên bao gồm điều kiện nghiệp vụ còn hiệu lực:

~~~javascript
db.events.deleteOne({
  _id: ObjectId("672000000000000000000001"),
  status: "EXPIRED",
  expiredAt: { $lte: cutoff }
});
~~~

Nếu document được gia hạn hoặc đổi trạng thái sau lúc chọn ID, điều kiện mới ngăn việc xóa document **không còn đủ tiêu chuẩn**.

### 7.2. $set một giá trị mục tiêu thường idempotent

~~~javascript
db.events.updateOne(
  { _id: eventId, archived: { $ne: true } },
  {
    $set: {
      archived: true
    }
  }
);
~~~

Dù thao tác bị gửi lại, kết quả cuối vẫn là **archived: true**. Tuy nhiên, nếu kèm **updatedAt: new Date()** trong mỗi lần thử, timestamp có thể thay đổi theo mỗi retry. Idempotency cần được đánh giá trên **toàn bộ hiệu ứng nghiệp vụ**, không chỉ một field.

### 7.3. $inc không mặc nhiên idempotent

~~~javascript
db.accounts.updateOne(
  { _id: "A-01" },
  { $inc: { points: 10 } }
);
~~~

Nếu chạy hai lần, điểm tăng **20**, không phải 10. Tương tự, **$push** có thể thêm phần tử trùng khi retry, còn insert với ID ngẫu nhiên mới mỗi lần có thể tạo bản ghi trùng nghiệp vụ.

Khi phải dùng thao tác không idempotent, cần thiết kế khóa idempotency hoặc marker trạng thái để một công việc chỉ tác động đến mỗi đối tượng đúng một lần.

Ví dụ một marker cục bộ trong cùng document:

~~~javascript
const jobId = "reward-backfill-v1";

db.accounts.updateOne(
  {
    _id: "A-01",
    processedJobs: { $ne: jobId }
  },
  {
    $inc: { points: 10 },
    $addToSet: { processedJobs: jobId }
  }
);
~~~

Điều kiện và thay đổi nằm trên một document nên hai thao tác cập nhật field trong cùng write được thực hiện nguyên tử. Nếu retry, marker giúp tránh cộng lại khi jobId đã tồn tại.

**Giới hạn:** Dùng mảng processedJobs có thể làm document tăng vô hạn. Với hệ thống thực, cần cân nhắc nhật ký xử lý riêng, khóa idempotency lưu có thời hạn hoặc thiết kế job khác, đồng thời phân tích ranh giới nguyên tử của các document liên quan.

### 7.4. Checkpoint không thay thế idempotency

Checkpoint chỉ nói **đã đi qua vị trí nào**. Nó không tự chứng minh mọi side effect bên ngoài đã xảy ra đúng một lần. Nếu một batch đồng thời ghi MongoDB và gọi HTTP API hoặc gửi email, phải thiết kế idempotency/outbox hoặc cơ chế tương ứng cho các hiệu ứng đó.

## 8. Lưu checkpoint ở đâu?

Một cách phổ biến là tạo collection chuyên lưu trạng thái job, ví dụ **maintenance.jobs**.

Document minh họa:

~~~javascript
{
  _id: "cleanup-expired-events-2026-11",
  collection: "audit.events",
  status: "RUNNING",
  cutoff: ISODate("2026-11-01T00:00:00Z"),
  batchSize: 500,
  lastId: ObjectId("672000000000000000000123"),
  batchesDone: 24,
  deletedReported: 11750,
  updatedAt: ISODate("2026-11-14T04:00:00Z"),
  lastError: null
}
~~~

**lastId** là mốc của batch đã hoàn thành, không phải ID hiện tại đang được xử lý dở. **deletedReported** chỉ là số thao tác xóa được ghi nhận qua các kết quả client đã cập nhật checkpoint; nó có thể thiếu các write thành công nhưng tiến trình crash trước khi lưu thống kê. Nếu cần tổng xóa chính xác phục vụ kiểm toán, phải thiết kế cơ chế ghi nhận đáng tin cậy hơn.

### 8.1. Trạng thái job

~~~text
CREATED
   |
   v
RUNNING -----> PAUSED
   |              |
   |              v
   |           RUNNING
   |
   +----------> FAILED
   |              |
   |              v
   |           RUNNING (sau xử lý lỗi)
   |
   +----------> DONE
~~~

- **CREATED:** cấu hình đã cố định, chưa bắt đầu.
- **RUNNING:** đã có tiến độ hoặc đang xử lý.
- **PAUSED:** tạm dừng có chủ đích tại một checkpoint an toàn.
- **FAILED:** dừng vì lỗi cần xử lý; checkpoint được giữ lại.
- **DONE:** đã duyệt hết phạm vi mà job quan sát theo chiến lược đã định.

Trạng thái DONE không tự chứng minh mọi document được tạo hoặc được đổi thành đủ điều kiện **sau khi cursor đã đi qua** đều được xử lý. Với dữ liệu động, cần cơ chế quét lại hoặc run mới.

### 8.2. Trình tự ghi checkpoint

Với mỗi batch:

1. Lấy danh sách ID theo mốc đã lưu.
2. Thực hiện toàn bộ thao tác ghi trong batch.
3. Kiểm tra batch kết thúc thành công theo tiêu chí của job.
4. **Sau đó mới lưu lastId = ID cuối cùng của batch đã chọn.**
5. Chuyển sang batch tiếp theo.

Tuyệt đối không lưu lastId ngay sau bước đọc nếu chưa biết các write đã thành công. Nếu một document bị lỗi nhưng checkpoint đã vượt qua ID của nó, job resume có thể không quay lại để xử lý.

Đối với lỗi từng phần, có hai chiến lược:

- **Giữ nguyên checkpoint và retry cả batch** bằng thao tác idempotent.
- **Theo dõi kết quả ở mức từng ID**, lưu danh sách ID lỗi và chỉ đi qua chúng khi đã có cơ chế xử lý lại đáng tin cậy.

Cách đầu đơn giản hơn cho xóa theo ID hoặc $set có điều kiện. Cách sau phù hợp hơn khi có nhiều lỗi dữ liệu cần cách ly, nhưng phải thiết kế tránh làm mất các ID chưa xử lý.

## 9. Ví dụ hoàn chỉnh bằng Node.js: xóa theo batch và resume

Ví dụ sau dùng MongoDB Node.js Driver. Job:

- Xóa event có **status = EXPIRED** và **expiredAt <= cutoff**.
- Mỗi lượt đọc tối đa **500 ID**, sắp theo _id.
- Ghi bằng bulkWrite chứa các deleteOne có điều kiện.
- Lưu lastId **chỉ sau khi bulkWrite hoàn tất thành công**.
- Nghỉ ngắn giữa các lượt.
- Dừng có kiểm soát sau một số batch để có thể chạy tiếp trong lịch kế tiếp.

Ví dụ giả định collection không sharding hoặc đã có quy tắc _id duy nhất toàn cục, các _id trong tập xử lý có kiểu BSON nhất quán và **chỉ một executor được phép chạy jobId tại một thời điểm**. Phần locking nhiều executor được trình bày ở mục sau.

~~~javascript
import { MongoClient } from "mongodb";

const uri = process.env.MONGODB_URI;
if (!uri) {
  throw new Error("Thiếu biến môi trường MONGODB_URI");
}

const JOB_ID = "cleanup-expired-events-2026-11";
const CUTOFF = new Date("2026-11-01T00:00:00.000Z");
const BATCH_SIZE = 500;
const PAUSE_MS = 200;
const MAX_BATCHES_PER_RUN = 100;

const client = new MongoClient(uri);

function pause(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function run() {
  await client.connect();

  try {
    const events = client.db("audit").collection("events");
    const jobs = client.db("maintenance").collection("jobs");

    // Chỉ tạo trạng thái khởi đầu nếu job chưa tồn tại.
    await jobs.updateOne(
      { _id: JOB_ID },
      {
        $setOnInsert: {
          status: "RUNNING",
          cutoff: CUTOFF,
          lastId: null,
          batchesDone: 0,
          deletedReported: 0,
          createdAt: new Date()
        }
      },
      { upsert: true }
    );

    const job = await jobs.findOne({ _id: JOB_ID });

    // Không resume một job cũ với cutoff mới.
    if (!(job.cutoff instanceof Date) ||
        job.cutoff.getTime() !== CUTOFF.getTime()) {
      throw new Error("Cutoff của job không khớp");
    }

    if (job.status === "DONE") {
      console.log("Job đã hoàn thành");
      return;
    }

    let lastId = job.lastId ?? null;
    let batchesThisRun = 0;

    while (batchesThisRun < MAX_BATCHES_PER_RUN) {
      const query = {
        status: "EXPIRED",
        expiredAt: { $lte: CUTOFF },
        ...(lastId === null
          ? {}
          : { _id: { $gt: lastId } })
      };

      const batch = await events.find(query, {
        projection: { _id: 1 }
      })
      .sort({ _id: 1 })
      .limit(BATCH_SIZE)
      .toArray();

      if (batch.length === 0) {
        const finish = await jobs.updateOne(
          { _id: JOB_ID, lastId },
          {
            $set: {
              status: "DONE",
              completedAt: new Date()
            }
          }
        );

        if (finish.matchedCount !== 1) {
          throw new Error("Checkpoint đã thay đổi");
        }

        console.log("Không còn document phù hợp sau checkpoint");
        break;
      }

      const operations = batch.map(({ _id }) => ({
        deleteOne: {
          filter: {
            _id,
            status: "EXPIRED",
            expiredAt: { $lte: CUTOFF }
          }
        }
      }));

      // Nếu bulkWrite ném lỗi, không ghi checkpoint.
      // Một phần deleteOne có thể đã thành công; retry an toàn
      // vì xóa theo ID và kèm điều kiện nghiệp vụ.
      const result = await events.bulkWrite(operations, {
        ordered: false
      });

      const newLastId = batch[batch.length - 1]._id;

      const saved = await jobs.updateOne(
        { _id: JOB_ID, lastId },
        {
          $set: {
            lastId: newLastId,
            status: "RUNNING",
            updatedAt: new Date()
          },
          $inc: {
            batchesDone: 1,
            deletedReported: result.deletedCount
          }
        }
      );

      if (saved.matchedCount !== 1) {
        throw new Error("Không lưu được checkpoint như kỳ vọng");
      }

      lastId = newLastId;
      batchesThisRun += 1;

      console.log({
        batchesThisRun,
        lastId,
        deleted: result.deletedCount
      });

      await pause(PAUSE_MS);
    }
  } finally {
    await client.close();
  }
}

run().catch((error) => {
  console.error("Job dừng; có thể resume theo checkpoint", error);
  process.exitCode = 1;
});
~~~

### 9.1. Vì sao lệnh chọn batch chỉ lấy _id?

Nếu mục tiêu là xóa, không cần tải toàn bộ payload sự kiện qua mạng. Projection **{ _id: 1 }** giảm lượng dữ liệu đọc về client.

Khi ghi, filter lặp lại **status** và **expiredAt** để tránh xóa một document đã được hệ thống khác thay đổi thành không đủ điều kiện trong khoảng thời gian giữa lúc chọn và lúc xóa.

### 9.2. Vì sao không checkpoint trước bulkWrite?

Nếu checkpoint được tăng trước khi xóa, một lần mất kết nối có thể làm job bỏ qua những document chưa được xóa. Ví dụ dùng **lastId** là ID cuối cùng đã *chọn* nhưng chưa *xử lý* sẽ tạo lỗ hổng khi resume.

Ở đây checkpoint chỉ tăng khi bulkWrite trả về thành công. Trong trường hợp driver ném lỗi sau khi có một số write thành công, checkpoint cũ được giữ, lần sau chọn lại các document còn tồn tại. Đây là lý do **deleteOne theo ID** là thao tác thuận lợi để retry.

### 9.3. Tại sao thống kê deletedReported chỉ mang tính vận hành?

Có thể xảy ra:

~~~text
bulkWrite xóa 500 document thành công
              |
              v
Process crash trước khi tăng deletedReported
              |
              v
Resume: 500 document đó đã biến mất
              |
              v
Job có thể hoàn thành nhưng deletedReported thiếu 500
~~~

Khi cần con số xóa chính xác theo yêu cầu kiểm toán, cần lưu dấu vết xử lý theo ID, snapshot ID đầu vào hoặc một quy trình đối soát được thiết kế riêng. **Không dùng deletedReported của ví dụ như số liệu tài chính hay kiểm toán tuyệt đối.**

### 9.4. Vì sao code có MAX_BATCHES_PER_RUN?

Một job nhiều triệu document có thể cần chia thành nhiều khoảng thời gian vận hành. Giới hạn số batch mỗi lần giúp tiến trình kết thúc có kiểm soát mà không phải duy trì một process liên tục.

Khi đạt giới hạn, trạng thái vẫn là RUNNING và lastId đã lưu. Chạy lại chương trình với **cùng JOB_ID và CUTOFF** sẽ tiếp tục từ checkpoint cũ.

Đây là một điểm dừng vận hành, không phải kết luận job đã xử lý hết dữ liệu.

### 9.5. Giới hạn của ví dụ

Ví dụ giả định **một executor duy nhất**. Nếu hai process cùng dùng một JOB_ID, cả hai có thể đọc cùng checkpoint và xóa trùng các ID. Điều kiện so khớp lastId khi lưu checkpoint giúp phát hiện một số xung đột, nhưng **không thay thế cơ chế khóa độc quyền trước khi ghi**.

Ngoài ra, nếu một document mới được thêm với _id nhỏ hơn checkpoint đã đi qua, job hiện tại có thể bỏ qua nó. Cần có run mới hoặc cơ chế work queue/snapshot khi yêu cầu không bỏ sót những dữ liệu phát sinh muộn.

## 10. Điều tiết tốc độ: không chỉ là sleep

Trong ví dụ Node.js, **pause(200)** tạo khoảng nghỉ 200 ms giữa các lượt. Đây là cách điều tiết đơn giản, dễ hiểu nhưng chưa đủ cho mọi workload.

Tốc độ trung bình có thể ước lượng:

~~~text
documents/second ≈ batchSize / (thời gian xử lý batch + thời gian nghỉ)
~~~

Ví dụ mỗi lô có 500 document, thao tác đọc + ghi + checkpoint mất 0,8 giây và nghỉ 0,2 giây, tốc độ xấp xỉ **500 document/giây**. Nếu mỗi lô mất 3 giây, cùng cấu hình chỉ đạt khoảng **156 document/giây**.

Công thức là xấp xỉ vì số document được chọn, số document thực sự bị sửa, thời gian query, retry và tải hệ thống có thể thay đổi.

### 10.1. Ba cách điều tiết thường gặp

| Cách | Cơ chế | Thích hợp |
| --- | --- | --- |
| **Fixed pause** | Nghỉ N mili giây sau mỗi batch | Job đơn giản, tải tương đối ổn định |
| **Rate limit** | Giới hạn số document/operation xử lý mỗi giây | Khi có mục tiêu throughput rõ |
| **Adaptive throttling** | Tăng giảm batch size/pause theo metric | Hệ thống production có tải thay đổi |

Một **rate limiter** như token bucket có thể cấp quyền xử lý theo một ngân sách operation/giây. Với nhiều worker, rate limit nên được chia sẻ hoặc phân bổ rõ, không để mỗi worker hiểu giới hạn toàn hệ thống là giới hạn riêng của mình.

### 10.2. Cần đo metric gì?

Khi chạy job bảo trì trên MongoDB, nên quan sát:

- Độ trễ **p95/p99** của truy vấn và thao tác ghi phục vụ người dùng.
- CPU, disk I/O và áp lực cache trên primary.
- Replication lag và khả năng secondary theo kịp oplog.
- Thời gian đọc ID, thời gian bulkWrite và thời gian lưu checkpoint.
- Số document được chọn, matched/modified/deleted và số lỗi theo từng batch.
- Số retry, số batch chờ, tốc độ xử lý và thời gian hoàn thành dự kiến.
- Với sharded cluster: tải phân bố giữa các shard và ảnh hưởng đến balancer/di chuyển dữ liệu.

Nếu độ trễ nghiệp vụ tăng hoặc replication lag vượt ngưỡng vận hành, job có thể **giảm batch size, tăng pause hoặc tạm dừng ở checkpoint**.

### 10.3. Batch size và concurrency là hai tham số khác nhau

Một process xử lý tuần tự:

~~~text
Read 500 -> Write 500 -> Save checkpoint -> Pause -> Repeat
~~~

Có thể ít gây áp lực đột biến hơn nhiều worker cùng thực thi:

~~~text
Worker A: 500
Worker B: 500
Worker C: 500
Worker D: 500
~~~

Dù mỗi worker chỉ có 500 operation, bốn worker có thể tạo tải lớn cùng lúc. Khi tăng concurrency, cần phân hoạch công việc rõ ràng, ví dụ mỗi worker sở hữu một range ID hoặc tenant riêng, và không có hai worker xử lý cùng phạm vi.

**maxTimeMS** giới hạn thời gian xử lý của một operation trong những ngữ cảnh được hỗ trợ; nó **không phải cơ chế điều tiết throughput**. Tương tự, giảm cursor.batchSize không thay thế giới hạn số write mà job thực hiện.

### 10.4. Backoff khi có lỗi tạm thời

Với lỗi mạng, replica set đang bầu primary, timeout hoặc tín hiệu hệ thống quá tải, job có thể dùng backoff:

~~~text
Lần retry 1: chờ khoảng 200 ms
Lần retry 2: chờ khoảng 400 ms
Lần retry 3: chờ khoảng 800 ms
Lần retry 4: chờ khoảng 1600 ms
Giới hạn thời gian chờ tối đa; thêm jitter
~~~

**Jitter** là độ ngẫu nhiên nhỏ trong thời gian chờ, giúp nhiều process tránh cùng retry vào một thời điểm.

Không nên retry vô hạn mọi lỗi. Lỗi validation, dữ liệu sai kiểu, thiếu quyền, index constraint hoặc cấu hình sai thường cần xử lý nguyên nhân. Với những thao tác không idempotent, retry sau lỗi mạng mơ hồ có thể gây lặp hiệu ứng.

## 11. Độc quyền xử lý và checkpoint khi có nhiều worker

Nếu có nhiều instance cùng chạy job, dùng **một checkpoint chung mà không có phân quyền sở hữu** có thể dẫn tới trùng công việc và mất tiến độ.

Hai cách tổ chức:

### 11.1. Một job, một executor

Một scheduler chỉ cho phép một instance của **jobId** đang chạy. Đây là hướng đơn giản nhất nếu tốc độ một executor đáp ứng yêu cầu.

Có thể lưu **lease** trong document job:

~~~javascript
{
  _id: "cleanup-expired-events-2026-11",
  ownerId: "worker-A",
  leaseUntil: ISODate("2026-11-14T04:30:00Z"),
  generation: 7,
  lastId: ObjectId("672000000000000000000123")
}
~~~

Quy trình:

1. Executor giành lease bằng cập nhật **có điều kiện và nguyên tử** trên document job.
2. Trong khi chạy, executor gia hạn lease và giữ một **generation/fencing token**.
3. Khi lưu checkpoint, filter phải xác nhận đúng owner/generation hiện tại.
4. Nếu lease hết hạn hoặc generation thay đổi, executor cũ dừng thay vì tiếp tục điều phối.
5. Executor mới resume từ checkpoint đã xác nhận.

Chỉ lưu **ownerId** vào một biến của process hoặc chỉ dựa vào khóa của scheduler không đủ khi có lỗi mạng và các instance cũ chưa dừng hẳn. Fencing token còn giúp phát hiện executor lỗi thời. Trong job có side effect ngoài MongoDB, hệ thống nhận ghi cũng cần chiến lược để từ chối thao tác từ executor cũ.

### 11.2. Nhiều job con, mỗi job một phạm vi

Nếu thực sự cần parallelism, chia dữ liệu thành các partition không giao nhau:

~~~text
Job tổng: cleanup-events
├── Partition A: tenantId thuộc nhóm A
├── Partition B: tenantId thuộc nhóm B
├── Partition C: tenantId thuộc nhóm C
└── Partition D: tenantId thuộc nhóm D
~~~

Mỗi partition có **checkpoint và lease riêng**, đồng thời có giới hạn tốc độ tổng. Với sharded cluster, partition theo shard key có thể giúp giảm phạm vi định tuyến, nhưng cần hiểu topology và phân bố dữ liệu.

Không nên chia partition bằng cách cho nhiều worker cùng chạy **skip(pageNumber * size)** trên một collection đang bị xóa. Khi document biến mất, các offset thay đổi và dễ dẫn đến trùng hoặc bỏ sót.

## 12. Tính đúng đắn khi collection vẫn đang thay đổi

### 12.1. Dữ liệu thay đổi giữa lúc đọc và lúc ghi

Ví dụ:

~~~text
T1: Job chọn event E vì status = EXPIRED
T2: Ứng dụng khôi phục E thành ACTIVE
T3: Job gửi deleteOne
~~~

Nếu deleteOne chỉ có filter **{ _id: E }**, job có thể xóa một event vừa được phục hồi. Vì vậy, cần lặp lại điều kiện nghiệp vụ trong operation ghi:

~~~javascript
db.events.deleteOne({
  _id: eventId,
  status: "EXPIRED",
  expiredAt: { $lte: cutoff }
});
~~~

Việc điều kiện được đánh giá tại thời điểm ghi trên document giúp tránh xóa khi điều kiện đã đổi.

### 12.2. Document trở nên đủ điều kiện sau khi cursor đi qua

Ví dụ job đã checkpoint qua _id = 5000. Sau đó một document _id = 1000 mới chuyển thành EXPIRED. Truy vấn **_id > 5000** sẽ không quay lại.

Đây không phải lỗi của MongoDB mà là giới hạn của mô hình duyệt tiến một chiều trên dữ liệu động. Các cách xử lý có thể là:

- Chạy **job định kỳ mới** để xử lý dữ liệu phát sinh muộn.
- Chốt danh sách work-item/ID tại thời điểm bắt đầu.
- Dùng cơ chế enqueue khi document chuyển trạng thái.
- Duy trì khóa thời gian bất biến và một vùng “lookback” có kiểm soát, kết hợp idempotency.

Không nên tuyên bố job “đã xử lý mọi document có thể đủ điều kiện trong suốt thời gian chạy” nếu thiết kế chưa bảo đảm điều đó.

### 12.3. Job hoàn tất ở thời điểm nào?

Với chương trình dùng keyset:

~~~text
Find next IDs -> empty
-> Mark DONE
~~~

Điều này có nghĩa **không còn document phù hợp ở phía sau checkpoint tại thời điểm truy vấn cuối**. Nó không chứng minh không còn document phù hợp có khóa nhỏ hơn checkpoint do thay đổi muộn.

Nếu cần bảo đảm “không còn document cũ nào đủ điều kiện”, có thể chạy phép kiểm tra lại từ đầu và lặp cho đến khi đạt điều kiện kết thúc phù hợp với hệ thống. Tuy nhiên, trong hệ thống ghi liên tục, không thể mặc định đạt trạng thái rỗng tuyệt đối; cần xác định quy tắc phạm vi theo thời gian hoặc thiết kế queue.

## 13. Xử lý lỗi và retry với bulkWrite

Một lô ghi có thể gặp:

| Nhóm lỗi | Ví dụ | Cách xử lý hợp lý |
| --- | --- | --- |
| **Transient network** | Mất kết nối giữa write và response | Không giả định write chưa xảy ra; dùng thao tác idempotent và retry có backoff |
| **Primary failover** | Replica set bầu primary mới | Giữ checkpoint cũ, chờ cluster hồi phục, retry phù hợp |
| **Write concern** | Không đạt mức xác nhận yêu cầu | Kết quả có thể chưa rõ; xử lý theo bảo đảm cần thiết |
| **Validation** | Document không thỏa schema validator | Ghi nhận document lỗi; không bỏ qua rồi nâng checkpoint vô điều kiện |
| **Duplicate key** | insertOne trùng unique index | Xác định có phải retry của cùng nghiệp vụ hay dữ liệu xung đột |
| **Thay đổi trạng thái** | Document không còn thỏa filter | deleteOne/updateOne có matchedCount/deletedCount = 0 có thể là kết quả hợp lệ |
| **Không lưu checkpoint** | BulkWrite thành công nhưng cập nhật job lỗi | Resume và chạy lại thao tác idempotent, không đoán lastId |

### 13.1. Lỗi từng phần của unordered bulkWrite

Khi **ordered: false**, có thể có operation thành công và operation thất bại. Nếu muốn đi qua cả batch dù có lỗi, cần một cách lưu **danh sách ID lỗi cần xử lý lại**. Đừng bỏ qua lỗi bằng cách chỉ in console rồi lưu checkpoint cuối batch.

Một chiến lược đơn giản là:

~~~text
try:
    bulkWrite(batch, ordered=false)
    checkpoint = lastIdInBatch
catch:
    giữ nguyên checkpoint
    ghi thông tin lỗi
    dừng hoặc retry batch với backoff
~~~

Chiến lược này phù hợp khi thao tác ghi **idempotent** và việc chạy lại không gây tác dụng phụ không mong muốn.

### 13.2. Retryable writes không thay thế checkpoint

MongoDB drivers hỗ trợ cơ chế retryable writes trong những điều kiện và loại thao tác được hỗ trợ. Nhưng retry của driver chỉ xử lý một phạm vi lỗi ở cấp command/operation; nó không biết “job đã đi qua ID nào”, cũng không thay cho logic xử lý lỗi dài hạn của ứng dụng.

Đặc biệt, không nên suy ra rằng một chuỗi bulkWrite, nhiều batch và thao tác cập nhật checkpoint được driver tự bọc thành một giao dịch nguyên tử.

### 13.3. Dùng write concern phù hợp

Với job cần bảo đảm mức xác nhận bền vững trước khi tiến checkpoint, cân nhắc **write concern** theo yêu cầu. Ví dụ trên replica set có cấu hình phù hợp:

~~~javascript
db.events.deleteOne(
  { _id: eventId, status: "EXPIRED" },
  { writeConcern: { w: "majority" } }
);
~~~

Chọn write concern phù hợp giúp xác định mức xác nhận cần đạt trước khi coi một thao tác ghi là hoàn tất. Tuy nhiên, write concern **không** biến các deleteOne trong một bulkWrite thành transaction đa document.

Checkpoint ở collection khác cũng là một write riêng. Nếu cần ràng buộc transaction giữa dữ liệu nghiệp vụ và state job, phải đánh giá việc dùng transaction hoặc thiết kế idempotent và kiểm toán phù hợp.

## 14. Index hỗ trợ job duyệt theo lô

Job thường lọc theo status, cutoff và sắp theo khóa duyệt:

~~~javascript
db.events.find({
  status: "EXPIRED",
  expiredAt: { $lte: cutoff },
  _id: { $gt: lastId }
})
.sort({ _id: 1 })
.limit(500);
~~~

Một index có thể hữu ích trong mô hình này là:

~~~javascript
db.events.createIndex({
  status: 1,
  _id: 1
});
~~~

Nó có thể hỗ trợ lọc theo status và duyệt theo _id. Điều kiện expiredAt vẫn cần được xét; nếu tỷ lệ document thực sự hết hạn rất nhỏ, index này có thể phải quét nhiều entry không đủ điều kiện.

Một hướng khác là index trên **status, expiredAt, _id** rồi duyệt theo cặp khóa **(expiredAt, _id)**. Cách này có thể khoanh vùng expiredAt hiệu quả hơn, nhưng checkpoint phải lưu đủ cặp khóa và điều kiện truy vấn phải phù hợp với sort.

Không có một index luôn tối ưu cho mọi job. Cần đo:

- Nhiều document bị loại bởi filter trước khi đủ một batch không?
- Kế hoạch thực thi có COLLSCAN hoặc sort tốn tài nguyên không?
- Index mới ảnh hưởng chi phí insert/update/delete của ứng dụng ra sao?
- Trên sharded cluster, filter có shard key để giảm fan-out không?

Có thể xem explain của truy vấn **chọn ID**:

~~~javascript
db.events.find({
  status: "EXPIRED",
  expiredAt: { $lte: cutoff }
})
.sort({ _id: 1 })
.limit(500)
.explain("executionStats");
~~~

Một job 500 document trên collection nhỏ có thể trông rất nhanh dù kế hoạch thực thi không phù hợp khi dữ liệu tăng đến hàng chục triệu. Đo trên quy mô đủ đại diện trước khi quyết định batch size và index.

## 15. Xóa dữ liệu cũ: khi nào nên dùng TTL?

Nếu yêu cầu chỉ đơn giản là **tự động xóa document sau một mốc thời gian**, MongoDB có cơ chế **TTL index** cho một số mô hình dữ liệu phù hợp.

Ví dụ minh họa với field BSON Date **expiredAt**:

~~~javascript
db.events.createIndex(
  { expiredAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

Với cấu hình này, document đủ điều kiện sẽ được TTL monitor xóa theo cơ chế nền của MongoDB. Việc xóa **không được bảo đảm xảy ra chính xác ngay lập tức tại thời điểm hết hạn**.

So sánh:

| Nhu cầu | TTL index | Job chia lô tùy chỉnh |
| --- | --- | --- |
| Xóa theo tuổi/Date field đơn giản | Phù hợp | Có thể thực hiện |
| Kiểm soát từng lô và checkpoint ứng dụng | Không phải chức năng chính | Có |
| Xóa theo nghiệp vụ nhiều bước | Hạn chế | Linh hoạt hơn |
| Điều tiết theo metric ứng dụng cụ thể | Không kiểm soát bằng vòng lặp ứng dụng | Có thể thiết kế |
| Ghi audit theo từng ID | Cần cơ chế bổ sung | Có thể tích hợp |
| Chạy migration/cập nhật schema | Không | Có |

TTL là lựa chọn tốt cho nhiều trường hợp retention thông thường. Nhưng nếu cần thứ tự thao tác, báo cáo, kiểm soát tải và khả năng tạm dừng chính xác theo job, một quy trình batching riêng vẫn có giá trị.

## 16. Bulk update thay vì bulk delete

Nguyên tắc batching và checkpoint áp dụng cho cả update.

Giả sử cần đánh dấu các event cũ:

~~~javascript
const batch = db.events.find({
  archived: { $ne: true },
  createdAt: { $lt: cutoff }
})
.sort({ _id: 1 })
.limit(500)
.project({ _id: 1 })
.toArray();

const operations = batch.map((document) => ({
  updateOne: {
    filter: {
      _id: document._id,
      archived: { $ne: true },
      createdAt: { $lt: cutoff }
    },
    update: {
      $set: {
        archived: true
      }
    }
  }
}));

if (operations.length > 0) {
  db.events.bulkWrite(operations, { ordered: false });
}
~~~

Đây là bản minh họa **một batch**, chưa có code checkpoint. Trong job hoàn chỉnh, phải ghi mốc sau khi batch thành công như đã trình bày.

### 16.1. $set và $inc có semantics retry khác nhau

| Thao tác | Chạy lại sau lỗi mạng | Lưu ý |
| --- | --- | --- |
| **deleteOne theo ID và điều kiện** | Thường an toàn về trạng thái dữ liệu cuối | Xóa lần hai thường không làm gì |
| **$set: { archived: true }** | Thường idempotent | Trạng thái cuối vẫn true |
| **$unset một field** | Thường idempotent | Field đã mất thì chạy lại không đổi |
| **$addToSet một giá trị cố định** | Hạn chế thêm phần tử trùng bằng nhau | Cần xét kiểu dữ liệu và semantics phần tử |
| **$inc: { balance: 10 }** | Không idempotent | Retry có thể tăng hai lần |
| **$push** | Không idempotent theo mặc định | Retry có thể thêm phần tử trùng |
| **insertOne với _id cố định** | Retry có thể gặp duplicate key | Cần nhận biết trùng do retry hay xung đột nghiệp vụ |

Khi job yêu cầu phép biến đổi không idempotent, hãy thêm điều kiện chuyển trạng thái hoặc dấu mốc đã xử lý, hoặc thiết kế một bước ghi có bảo đảm chính xác hơn trong phạm vi cần thiết.

## 17. Ví dụ Java Driver: ghi một batch update có điều kiện

Trong MongoDB Java Sync Driver, một batch có thể được biểu diễn bằng danh sách **WriteModel<Document>**:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.WriteModel;
import com.mongodb.bulk.BulkWriteResult;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public class ArchiveEventBatch {

    public static void main(String[] args) {
        List<String> ids = List.of("EV-01", "EV-02", "EV-03");

        try (MongoClient client =
                     MongoClients.create("mongodb://localhost:27017")) {

            MongoCollection<Document> collection =
                    client.getDatabase("audit")
                          .getCollection("events");

            List<WriteModel<Document>> operations = new ArrayList<>();

            for (String id : ids) {
                operations.add(new UpdateOneModel<>(
                        Filters.and(
                                Filters.eq("_id", id),
                                Filters.ne("archived", true)
                        ),
                        Updates.set("archived", true)
                ));
            }

            if (!operations.isEmpty()) {
                BulkWriteResult result = collection.bulkWrite(
                        operations,
                        new BulkWriteOptions().ordered(false)
                );

                System.out.println(
                        "Matched: " + result.getMatchedCount()
                );
                System.out.println(
                        "Modified: " + result.getModifiedCount()
                );
            }
        }
    }
}
~~~

Ví dụ này chỉ minh họa **ghi một batch**; dữ liệu ID được cung cấp sẵn và chưa có vòng đọc mốc/checkpoint. Trong job thật, lấy ID theo keyset, kiểm tra kết quả bulkWrite, lưu mốc sang một collection job và điều tiết giữa các lượt.

Hãy phân biệt **matchedCount** và **modifiedCount**: một document có thể khớp điều kiện nhưng không thay đổi giá trị, hoặc không còn phù hợp vì service khác đã cập nhật. Con số này cần được diễn giải theo nghiệp vụ.

## 18. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dùng skip(offset) khi đang xóa | Document bị dồn vị trí, có thể bị bỏ sót | Dùng keyset pagination |
| Chỉ lưu timestamp làm cursor dù giá trị trùng | Bỏ sót document cùng timestamp | Lưu cặp (timestamp, _id) |
| Dùng khóa sắp xếp có thể bị sửa | Document chuyển qua mốc, gây trùng/bỏ sót | Dùng khóa ổn định hoặc snapshot |
| Lưu checkpoint trước khi ghi | Nếu ghi lỗi, lần sau bỏ qua lô chưa hoàn tất | Chỉ checkpoint sau thành công |
| Retry $inc hoặc $push không có idempotency | Nhân đôi hiệu ứng | Dùng điều kiện/marker/log |
| Hiểu ordered:false là “tất cả sẽ thành công” | Bỏ qua lỗi từng operation | Phân loại partial failure |
| Dùng deleteMany mong đợi limit 500 | Có thể xóa toàn bộ document phù hợp | Chọn 500 ID rồi deleteOne |
| Giảm cursor.batchSize để throttle ghi | Không kiểm soát số write thực tế | Điều tiết vòng xử lý và concurrency |
| Mỗi lần resume thay cutoff bằng new Date() | Phạm vi job thay đổi liên tục | Giữ cutoff bất biến |
| Tăng concurrency nhưng dùng một checkpoint | Có thể ghi trùng và đua trạng thái | Lease hoặc phân hoạch độc lập |
| Chỉ lọc trạng thái ở bước chọn ID | Có thể xóa document không còn đủ điều kiện | Lặp lại điều kiện tại write |
| Coi tổng deletedCount cộng dồn là số kiểm toán chính xác | Crash trước checkpoint có thể làm thiếu thống kê | Thiết kế audit/đối soát riêng |
| Không đo replication lag | Job gây quá tải secondary | Giám sát và điều chỉnh tốc độ |
| Coi DONE là không thể có document mới phù hợp | Dữ liệu đến muộn có thể bị bỏ qua | Chạy đợt mới hoặc queue/snapshot |

## 19. Bài thực hành: job xóa event thử nghiệm

Các bài tập dưới đây có thể chạy trong một database thử nghiệm riêng. Không dùng dữ liệu production để thử lệnh xóa.

### Bài 1: tạo dữ liệu mẫu

~~~javascript
use mongo_batch_lab

db.events.insertMany([
  {
    _id: 1,
    status: "EXPIRED",
    expiredAt: ISODate("2025-01-01T00:00:00Z")
  },
  {
    _id: 2,
    status: "EXPIRED",
    expiredAt: ISODate("2025-02-01T00:00:00Z")
  },
  {
    _id: 3,
    status: "ACTIVE",
    expiredAt: ISODate("2025-03-01T00:00:00Z")
  },
  {
    _id: 4,
    status: "EXPIRED",
    expiredAt: ISODate("2025-04-01T00:00:00Z")
  },
  {
    _id: 5,
    status: "EXPIRED",
    expiredAt: ISODate("2025-05-01T00:00:00Z")
  },
  {
    _id: 6,
    status: "EXPIRED",
    expiredAt: ISODate("2027-01-01T00:00:00Z")
  }
]);
~~~

Giả sử cutoff là ngày 01/01/2026. Các ID đủ điều kiện là **1, 2, 4, 5**. ID 3 có status ACTIVE nên không đủ điều kiện; ID 6 chưa đến hạn theo cutoff.

### Bài 2: lấy hai ID đầu tiên

~~~javascript
const cutoff = ISODate("2026-01-01T00:00:00Z");

const batch1 = db.events.find({
  status: "EXPIRED",
  expiredAt: { $lte: cutoff }
})
.sort({ _id: 1 })
.limit(2)
.project({ _id: 1 })
.toArray();

printjson(batch1);
~~~

Kết quả chọn ID **1** và **2**. Mốc tiếp tục sau batch thành công sẽ là **2**.

### Bài 3: xóa hai ID bằng bulkWrite

~~~javascript
const operations1 = batch1.map((item) => ({
  deleteOne: {
    filter: {
      _id: item._id,
      status: "EXPIRED",
      expiredAt: { $lte: cutoff }
    }
  }
}));

db.events.bulkWrite(operations1, { ordered: false });
~~~

Sau khi lệnh thành công, ID 1 và 2 không còn. Nếu chạy lại cùng **operations1**, kết quả xóa thêm thường là 0 vì ID đã biến mất.

### Bài 4: tiếp tục theo mốc thay vì skip

~~~javascript
const lastId = 2;

const batch2 = db.events.find({
  status: "EXPIRED",
  expiredAt: { $lte: cutoff },
  _id: { $gt: lastId }
})
.sort({ _id: 1 })
.limit(2)
.project({ _id: 1 })
.toArray();

printjson(batch2);
~~~

Kết quả chọn ID **4** và **5**. Nếu dùng skip(2) trên collection đã bị xóa 1 và 2, bạn có thể bỏ sót dữ liệu. Hãy giải thích vì sao lastId giúp tránh vấn đề này.

### Bài 5: mô phỏng crash trước checkpoint

1. Xóa batch1 thành công.
2. Giả sử checkpoint vẫn lưu **lastId = null** vì process dừng trước khi lưu.
3. Chạy lại truy vấn batch đầu tiên.
4. Quan sát MongoDB chỉ còn trả những ID đủ điều kiện chưa bị xóa.
5. Xóa tiếp và lưu checkpoint sau kết quả thành công.

Giải thích vì sao việc **xóa theo ID** hỗ trợ resume an toàn, nhưng con số deletedCount cộng dồn có thể không phản ánh mọi lần xóa đã xảy ra trước khi crash.

### Bài 6: thêm dữ liệu đến muộn

Sau khi checkpoint đã đi qua ID 5, thêm một document thử nghiệm có _id nhỏ hơn 5 và đủ điều kiện xóa. Truy vấn **_id > 5** không tìm thấy document này.

Hãy trả lời: để không bỏ sót dữ liệu đến muộn trong hệ thống thực, nên chạy thêm một đợt job mới, ghi work-item hay tạo snapshot phạm vi xử lý ngay từ đầu?

### Bài 7: thiết kế job cập nhật trạng thái

Một collection **invoices** có các field:

~~~javascript
{
  _id: "INV-1001",
  status: "PENDING",
  dueAt: ISODate("2025-12-01T00:00:00Z"),
  overdue: false
}
~~~

Yêu cầu đánh dấu overdue cho mọi invoice còn PENDING với dueAt đã qua. Hãy thiết kế:

- Filter chọn document, với cutoff cố định.
- Thao tác **$set: { overdue: true }** trên từng ID.
- Batch size và cơ chế pause.
- Checkpoint theo khóa ổn định.
- Điều kiện ghi để không cập nhật invoice vừa chuyển thành PAID.
- Quy tắc retry nếu process crash sau bulkWrite nhưng trước checkpoint.

Không nhất thiết phải dùng transaction đa document cho việc đánh dấu các invoice độc lập. Điều quan trọng là từng write **idempotent**, điều kiện nghiệp vụ được kiểm tra ở thời điểm ghi và checkpoint chỉ vượt qua những lô đã hoàn tất.

## 20. Nguyên tắc vận hành cần ghi nhớ

Trong MongoDB, thao tác trên tập dữ liệu lớn nên được thiết kế như **một chuỗi đơn vị công việc nhỏ có thể xác nhận**. Mỗi lượt chọn số ID giới hạn bằng khóa duyệt ổn định, thực hiện bulkWrite/deleteOne/updateOne theo đúng điều kiện nghiệp vụ, lưu checkpoint sau khi các write hoàn tất, rồi điều tiết trước lượt tiếp theo.

Đối với job kéo dài hàng giờ hoặc nhiều ngày, thiết kế cần chịu được ba sự thật:

1. Process có thể crash ở bất kỳ điểm nào, kể cả **ngay sau khi ghi thành công nhưng trước khi lưu checkpoint**.
2. Các document trong collection có thể thay đổi trong khi job đang chạy.
3. Thao tác ghi có thể chỉ thành công một phần, và **đoạn chương trình xử lý lỗi cần hiểu rõ điều đó**.

Vì vậy, **checkpoint + idempotency + phạm vi công việc ổn định + điều tiết theo metric** là nền tảng để xử lý hàng triệu document mà vẫn có khả năng tạm dừng, resume và kiểm soát ảnh hưởng đến hệ thống.

## Tài liệu tham khảo

- [MongoDB Manual — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Manual — db.collection.bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/)
- [MongoDB Manual — db.collection.deleteMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteMany/)
- [MongoDB Manual — db.collection.updateMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Node.js Driver — Bulk Operations](https://www.mongodb.com/docs/drivers/node/current/crud/bulk-write/)

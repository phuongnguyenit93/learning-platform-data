# `findOneAndDelete` và nhu cầu đọc kèm xóa nguyên tử trong MongoDB

Trong MongoDB, một ứng dụng đôi khi cần **lấy nội dung của một document rồi xóa ngay document đó**. Ví dụ: một worker muốn lấy một công việc từ hàng đợi tạm thời mà không để worker khác lấy cùng công việc; dịch vụ muốn tiêu thụ một mã sử dụng một lần; hoặc tác vụ dọn dẹp cần biết chính xác bản ghi nào vừa bị xóa để ghi nhận kết quả.

Đặt hai lệnh `findOne()` và `deleteOne()` cạnh nhau chưa đáp ứng yêu cầu này. Giữa hai lệnh có thể xuất hiện cập nhật từ tiến trình khác; document được đọc và document bị xóa có thể không còn là cùng một trạng thái. MongoDB cung cấp **`findOneAndDelete(filter, options)`**, cho phép tìm, chọn và xóa **một document** như một thao tác đọc-kèm-ghi nguyên tử, đồng thời trả về document đã bị xóa.

Bài học thuộc chương **Xóa và ghi theo lô**, tập trung vào ý nghĩa đúng đắn của thao tác này, cách lựa chọn document, xử lý đồng thời, khác biệt với `deleteOne()`/`deleteMany()`/bulk, các giới hạn khi xây dựng hàng đợi, và cách sử dụng trong Java hoặc mongosh. Ví dụ sử dụng database thực hành `atomic_delete_lab`. **Không chạy các lệnh xóa trên dữ liệu quan trọng hoặc môi trường production khi chưa có quy trình phê duyệt và khôi phục.**

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `findOne()` rồi `deleteOne()` không tương đương một thao tác đọc-xóa nguyên tử.
2. Dùng `findOneAndDelete()` để xóa một document thỏa filter và **nhận lại chính document đó**.
3. Sử dụng `sort`, `projection` và filter có điều kiện để lựa chọn document phù hợp.
4. Hiểu phạm vi atomicity ở cấp **một document**, kể cả khi có nhiều client cùng truy cập collection.
5. Phân biệt thao tác **nhận việc rồi xóa ngay** với cơ chế **claim/lease/ack** phù hợp hàng đợi có yêu cầu retry.
6. Chọn đúng giữa `findOneAndDelete()`, `deleteOne()`, `deleteMany()`, `findOneAndUpdate()` và thao tác bulk.
7. Thiết kế xử lý timeout, mất phản hồi, lỗi commit không chắc chắn, replication và yêu cầu idempotency.
8. Nhận biết chi phí index, lựa chọn bản ghi theo thứ tự và giới hạn của transaction, sharding.

## 2. “Đọc kèm xóa” cần bảo đảm điều gì?

Xét một collection `jobs`:

~~~javascript
{
  _id: "job-101",
  status: "READY",
  payload: { type: "EXPORT_REPORT", reportId: "r-501" },
  createdAt: ISODate("2026-05-01T08:00:00Z")
}
~~~

Yêu cầu: một worker lấy một job `READY`, nhận nội dung job và loại nó khỏi tập công việc chưa được lấy, sao cho một worker khác không thể lấy cùng document ấy bằng thao tác tương tự.

### Cách dễ sai: tách đọc và xóa

~~~javascript
const job = db.jobs.findOne({ status: "READY" })

if (job !== null) {
  db.jobs.deleteOne({ _id: job._id })
  printjson(job)
}
~~~

Trong hệ thống một worker và không có cập nhật đồng thời, đoạn này *có thể trông như chạy đúng*. Nhưng ngay khi có hai worker:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant DB as MongoDB
    participant B as Worker B
    A->>DB: findOne(status=READY)
    DB-->>A: job-101
    B->>DB: findOne(status=READY)
    DB-->>B: job-101
    A->>DB: deleteOne(_id=job-101)
    DB-->>A: deletedCount=1
    B->>DB: deleteOne(_id=job-101)
    DB-->>B: deletedCount=0
    Note over A,B: Cả A và B đã đọc nội dung job-101
~~~

Nếu cả hai worker xử lý `job` vừa đọc mà không kiểm tra kết quả xóa, cùng một công việc có thể được chạy hai lần. Ngay cả khi B có kiểm tra `deletedCount === 0`, phần đọc và xóa vẫn không có bảo đảm một bước; code phải gắn thêm quy tắc xử lý xung đột.

### Cách đúng cho thao tác lấy-xóa một lần

~~~javascript
const job = db.jobs.findOneAndDelete({
  status: "READY"
})

if (job !== null) {
  printjson(job)
}
~~~

Truy vấn và xóa được thực hiện như **một thao tác nguyên tử trên document được chọn**. Khi hai worker đồng thời gọi lệnh để lấy việc, một document đã bị worker A xóa không thể được trả về như một document còn tồn tại cho worker B ở một thao tác xóa tương ứng khác.

**Lưu ý phạm vi:** thao tác này ngăn hai lời gọi lấy-xóa cùng lấy **một document**; nó **không bảo đảm job đã được xử lý thành công sau khi xóa**. Đây là khác biệt đặc biệt quan trọng trong kiến trúc queue.

## 3. Cú pháp và giá trị trả về

### 3.1. Cú pháp mongosh

~~~javascript
db.collection.findOneAndDelete(
  filter,
  options
)
~~~

Trong đó:

| Thành phần | Vai trò |
|---|---|
| `filter` | Điều kiện chọn document sẽ bị xóa |
| `options.sort` | Quy định thứ tự lựa chọn khi nhiều document khớp |
| `options.projection` | Chọn field xuất hiện trong **document trả về**, không quyết định field bị xóa |
| `options.collation` | Quy định cách so sánh chuỗi theo ngôn ngữ/locale khi cần |
| `options.maxTimeMS` | Giới hạn thời gian xử lý phía server theo API hỗ trợ |

Các option cụ thể có thể khác nhau theo phiên bản MongoDB, driver và cách gọi. Ví dụ trong bài dùng những option cơ bản, phổ biến.

### 3.2. Giá trị trả về

Khi tìm thấy document, mongosh trả về document **trước khi bị xóa**:

~~~javascript
{
  _id: "job-101",
  status: "READY",
  payload: { type: "EXPORT_REPORT", reportId: "r-501" },
  createdAt: ISODate("2026-05-01T08:00:00Z")
}
~~~

Khi không có document khớp, kết quả là `null`:

~~~javascript
const removed = db.jobs.findOneAndDelete({
  _id: "no-such-job"
})

print(removed === null) // true
~~~

**Không trả `deletedCount` giống `deleteOne()`**. Sự khác biệt về kiểu kết quả quan trọng khi thay đổi API hoặc chuyển code từ một lệnh xóa sang lệnh khác.

### 3.3. Khi nào nên dùng?

`findOneAndDelete()` hợp lý nếu:

- Phải biết **nội dung của document vừa bị xóa**.
- Filter có thể khớp nhiều document, và bạn muốn chọn/xóa một document cụ thể dựa trên `sort`.
- Cần tránh cửa sổ cạnh tranh giữa một lệnh đọc riêng và một lệnh xóa riêng.
- Mất document ngay lúc lấy là hành vi được nghiệp vụ chấp nhận.

Nếu chỉ cần xóa theo `_id` và lấy số bản ghi đã xóa, `deleteOne()` thường đơn giản hơn. Nếu cần phục hồi/retry xử lý job sau crash, hãy xem thiết kế claim/lease ở phần sau thay vì mặc định xóa sớm.

## 4. Tạo dữ liệu lab

Các ví dụ tiếp theo giả định database lab mới, chưa có collection `jobs`. Không chạy lại toàn bộ `insertMany()` với `_id` cũ khi đã dùng dữ liệu từ lượt thử trước.

~~~javascript
use atomic_delete_lab

db.jobs.insertMany([
  {
    _id: "job-101",
    status: "READY",
    priority: 2,
    createdAt: ISODate("2026-05-01T08:00:00Z"),
    payload: { type: "EXPORT", reportId: "r-101" }
  },
  {
    _id: "job-102",
    status: "READY",
    priority: 5,
    createdAt: ISODate("2026-05-01T08:05:00Z"),
    payload: { type: "EMAIL", templateId: "t-102" }
  },
  {
    _id: "job-103",
    status: "DONE",
    priority: 9,
    createdAt: ISODate("2026-05-01T08:02:00Z"),
    payload: { type: "CLEANUP", resourceId: "x-103" }
  },
  {
    _id: "job-104",
    status: "READY",
    priority: 5,
    createdAt: ISODate("2026-05-01T08:05:00Z"),
    payload: { type: "EXPORT", reportId: "r-104" }
  },
  {
    _id: "job-105",
    status: "READY",
    priority: 1,
    createdAt: ISODate("2026-05-01T08:10:00Z"),
    payload: { type: "EMAIL", templateId: "t-105" }
  }
])
~~~

Kiểm tra dữ liệu trước khi xóa:

~~~javascript
db.jobs.find(
  {},
  { _id: 1, status: 1, priority: 1, createdAt: 1 }
).sort({ _id: 1 })
~~~

Ta sẽ chọn các job theo thứ tự **priority giảm dần**, rồi theo **createdAt tăng dần**, cuối cùng dùng `_id` làm tie-breaker ổn định.

## 5. Xóa một document và trả về chính document đó

### 5.1. Xóa theo `_id` xác định

~~~javascript
const removed = db.jobs.findOneAndDelete({
  _id: "job-105"
})

printjson(removed)
~~~

Với dữ liệu lab chưa bị thay đổi, lệnh trả document `job-105` và loại nó khỏi collection. Kiểm tra:

~~~javascript
db.jobs.findOne({ _id: "job-105" }) // null
~~~

Nếu chạy lệnh xóa `job-105` lần thứ hai, kết quả là `null`. Điều này **không có nghĩa request thứ hai là lỗi hệ thống**; nó có thể là thao tác được gửi lại sau khi lần đầu thành công. Tuy nhiên, lần thứ hai cũng **không còn nội dung document cũ để trả** nếu ứng dụng không lưu kết quả ở nơi khác.

### 5.2. Xóa theo điều kiện nghiệp vụ

~~~javascript
const removed = db.jobs.findOneAndDelete({
  status: "READY",
  priority: { $gte: 2 }
})

printjson(removed)
~~~

Lệnh chỉ xóa một job khớp filter. Nếu có nhiều job khớp, **không được giả định một thứ tự ổn định** khi không có `sort`. Kết quả có thể khác giữa các lần thử, khi index thay đổi hoặc khi workload thay đổi.

### 5.3. Không chạy filter rỗng một cách tùy tiện

~~~javascript
// NGUY HIỂM: có thể xóa bất kỳ một document nào trong collection.
db.jobs.findOneAndDelete({})
~~~

Đây là minh họa cần tránh trong production. Filter `{}` có nghĩa mọi document đều là ứng viên; không có `sort` và tiêu chí chọn thích hợp, bạn không biết đối tượng nào sẽ bị xóa trước.

Với thao tác quản trị hoặc API quan trọng, nên yêu cầu các trường nhận dạng bắt buộc, kiểm tra giá trị đầu vào và ghi nhận document `_id` đã bị xóa.

## 6. Chọn bản ghi theo `sort`

Khi nhiều document cùng thỏa filter, `options.sort` cho MongoDB biết **ưu tiên document nào để xóa**.

### 6.1. Lấy job ưu tiên cao nhất

Nếu muốn thử lại từ đầu, dùng database lab mới hoặc tạo lại dữ liệu mẫu. Sau đó:

~~~javascript
const job = db.jobs.findOneAndDelete(
  { status: "READY" },
  {
    sort: {
      priority: -1,
      createdAt: 1,
      _id: 1
    }
  }
)

printjson(job)
~~~

Với bộ dữ liệu ban đầu, kết quả đầu tiên là `job-102`; `job-104` có cùng `priority = 5` và cùng `createdAt` nhưng `_id` lớn hơn, nên đứng sau khi sắp xếp tăng dần theo ID.

Lần gọi thứ hai với cùng filter/sort sẽ chọn `job-104` nếu không có concurrent writer hoặc thay đổi trạng thái. `job-103` có priority 9 nhưng status `DONE` nên **không** được chọn.

### 6.2. Vì sao cần tie-breaker?

Ví dụ:

~~~javascript
sort: { priority: -1 }
~~~

không chỉ ra thứ tự giữa hai job có cùng priority. Nếu muốn kiểm soát lựa chọn trong trạng thái ổn định, thêm các khóa phân giải:

~~~javascript
sort: { priority: -1, createdAt: 1, _id: 1 }
~~~

Vì `_id` là duy nhất trong collection thông thường, nó có thể đóng vai trò tie-breaker. Điều này giúp thứ tự được xác định cho tập dữ liệu tại một thời điểm; **không cam kết FIFO tuyệt đối khi nhiều client đồng thời thêm/sửa/xóa job**.

### 6.3. `sort` không biến việc lấy job thành lịch trình bảo đảm toàn cục

Giữa hai lời gọi có thể xuất hiện job ưu tiên cao mới. Các worker cũng có thể cạnh tranh khi dữ liệu và index đang thay đổi. Vì vậy:

- Không coi `sort` là “giao đúng job đầu tiên tuyệt đối” dưới mọi dạng concurrency.
- Không dựa vào thứ tự vật lý/natural order của collection để triển khai queue.
- Nếu nghiệp vụ yêu cầu fairness, FIFO chặt, scheduling hay phân phối có SLA, cần đánh giá thêm queue service hoặc giao thức điều phối riêng.

### 6.4. Index phục vụ filter và sort

Với filter `status: "READY"` và sort như trên:

~~~javascript
db.jobs.createIndex(
  {
    status: 1,
    priority: -1,
    createdAt: 1,
    _id: 1
  },
  { name: "idx_ready_priority_time" }
)
~~~

Đây là một **ứng viên index**, không phải công thức tối ưu cho mọi collection. Equality trên `status`, sau đó các field sort có thể giúp hạn chế scan/sort trong workload phù hợp. Index làm tăng chi phí ghi/xóa và dung lượng; phải đo trên dữ liệu thật, đặc biệt nếu trạng thái thay đổi liên tục.

## 7. `projection`: chỉ giới hạn nội dung được trả về

`projection` của `findOneAndDelete()` **không tạo ra “partial delete”**. Lệnh vẫn xóa toàn bộ document; projection chỉ xác định những field nào ứng dụng nhận được.

Ví dụ:

~~~javascript
const removed = db.jobs.findOneAndDelete(
  {
    status: "READY",
    priority: 2
  },
  {
    projection: {
      _id: 1,
      status: 1,
      priority: 1
    }
  }
)

printjson(removed)
~~~

Với dữ liệu ban đầu, kết quả chỉ chứa `_id`, `status` và `priority` của `job-101`. Trường `payload` không được trả về **nhưng vẫn bị xóa cùng document**.

### Nên trả bao nhiêu field?

- Nếu xử lý nghiệp vụ cần `payload`, không loại nó khỏi projection.
- Nếu chỉ cần biết `_id` của bản ghi vừa xóa, projection nhỏ giúp giảm dữ liệu trả về.
- Nếu cần truy vết/audit, lưu đủ định danh và metadata cần thiết trước khi kết quả mất khỏi bộ nhớ.
- Không loại `_id` khỏi kết quả nếu client cần dùng nó để xác minh hoặc đối chiếu.

Một số driver trả wrapper chứa metadata thay vì document trực tiếp tùy API/version; khi sử dụng driver cần kiểm tra kiểu trả về cụ thể, không suy luận toàn bộ từ mongosh.

## 8. `collation` và điều kiện trên chuỗi

Trong hệ thống hỗ trợ nhiều ngôn ngữ hoặc tìm kiếm không phân biệt hoa/thường, collation ảnh hưởng so sánh chuỗi và thứ tự sort:

~~~javascript
db.session_tokens.findOneAndDelete(
  { ownerEmail: "USER@EXAMPLE.COM" },
  {
    collation: { locale: "en", strength: 2 }
  }
)
~~~

Ví dụ chỉ có ý nghĩa khi collection có dữ liệu và cấu hình collation phù hợp. Mức `strength` có thể cho phép so khớp không phân biệt một số khác biệt chữ hoa/thường theo locale.

Các nguyên tắc:

1. Nếu identity của đối tượng cần phân biệt chính xác, hãy dùng ID/khóa đã chuẩn hóa thay vì đoán theo email hiển thị.
2. Index sử dụng collation cụ thể có thể không được khai thác theo cùng cách với một query dùng collation khác.
3. Không nhầm collation với quyền truy cập: một request muốn xóa token phải được xác thực và được phép xóa token đích.

## 9. Atomicity: MongoDB bảo đảm gì?

### 9.1. Một document là đơn vị nguyên tử

MongoDB có bảo đảm tính nguyên tử cho thao tác ghi trên **một document**, bao gồm thao tác tìm rồi xóa một document bằng `findOneAndDelete()`. Một client khác không nhìn thấy trạng thái “đã đọc nhưng chưa xóa” như hai thao tác ứng dụng tách rời.

Ví dụ hai worker đồng thời:

~~~mermaid
sequenceDiagram
    participant W1 as Worker 1
    participant DB as MongoDB
    participant W2 as Worker 2
    W1->>DB: findOneAndDelete({_id:"job-101"})
    W2->>DB: findOneAndDelete({_id:"job-101"})
    DB-->>W1: job-101 (nếu W1 thắng)
    DB-->>W2: null (nếu W2 đến sau khi xóa)
    Note over W1,W2: Chỉ một lời gọi xóa được document job-101
~~~

Nếu filter rộng và có **nhiều document READY**, cả hai worker có thể đồng thời nhận **hai document khác nhau** — đây là hành vi mong muốn khi chia việc. Nếu collection chỉ có một document khớp, một worker nhận document, worker kia nhận `null` hoặc một kết quả phù hợp với các thay đổi đồng thời khác.

### 9.2. Atomicity không có nghĩa toàn bộ workflow nguyên tử

Giả sử:

~~~text
1. findOneAndDelete(job) thành công
2. gọi dịch vụ gửi email
3. ghi log hoàn tất
~~~

MongoDB chỉ bảo đảm bước 1 ở phạm vi document. Nếu ứng dụng crash ở bước 2, job đã mất khỏi collection nhưng email có thể chưa gửi. Nếu bước 2 gửi email thành công nhưng bước 3 thất bại, hệ thống lại không có dấu vết hoàn tất rõ ràng.

Đây là lý do `findOneAndDelete()` phù hợp với **tiêu thụ dữ liệu mà mất sau khi lấy là chấp nhận được**, nhưng không mặc định phù hợp **hàng đợi công việc cần at-least-once processing**.

### 9.3. Atomicity không tự kéo dài ra nhiều document

Lệnh:

~~~javascript
db.jobs.findOneAndDelete({ status: "READY" })
~~~

chỉ xóa **một document**. Nó không bảo đảm đồng thời giảm counter ở collection khác, xóa audit record, hay ghi outbox event. Khi cần nhiều thay đổi MongoDB nhất quán, cân nhắc transaction hoặc điều chỉnh data model để các giá trị liên quan nằm trong cùng document.

## 10. Không có kết quả khi filter không khớp

~~~javascript
const missing = db.jobs.findOneAndDelete({
  _id: "job-does-not-exist"
})

print(missing === null) // true
~~~

`null` thường nghĩa là **không có document nào khớp tại thời điểm thao tác**; nó không chứng minh:

- Document chưa từng tồn tại.
- Một worker khác vừa xóa (có thể do filter sai, status thay đổi hoặc ID nhập sai).
- Công việc trước đó đã được xử lý thành công.
- Collection hoàn toàn rỗng.

Hãy đọc `null` theo **filter và hợp đồng nghiệp vụ**. Ví dụ một API xóa token theo `_id` có thể coi “đã vắng mặt” là kết quả hợp lệ, nhưng một worker lấy job mà nhận `null` nên coi là “hiện không tìm thấy job đủ điều kiện” — hai ngữ nghĩa khác nhau.

## 11. Dùng filter để tránh xóa dữ liệu đã thay đổi

Một tính chất hữu ích của lệnh tìm-xóa nguyên tử là **kiểm tra điều kiện ngay tại thao tác xóa**, không dựa vào kết quả đọc từ lâu.

### 11.1. Xóa theo trạng thái và hạn sử dụng

Giả sử document:

~~~javascript
{
  _id: "token-001",
  userId: "user-01",
  status: "ACTIVE",
  expiresAt: ISODate("2026-05-15T10:00:00Z")
}
~~~

Một lệnh chỉ xóa token đã hết hạn:

~~~javascript
const now = new Date()

const expiredToken = db.session_tokens.findOneAndDelete({
  _id: "token-001",
  status: "ACTIVE",
  expiresAt: { $lte: now }
})

printjson(expiredToken)
~~~

Nếu token chưa hết hạn tại mốc `now` do ứng dụng cung cấp, lệnh không xóa. Nếu status đã chuyển khỏi `ACTIVE` trước lúc thao tác, filter cũng không khớp. Điều này tránh “đọc trạng thái cũ, sau đó xóa mà không kiểm tra trạng thái mới”.

`new Date()` dùng đồng hồ của process mongosh/ứng dụng. Với nghiệp vụ bảo mật nhạy thời gian, cần xác định rõ nguồn thời gian tin cậy, độ lệch đồng hồ và cơ chế phát hành/hủy token; không cho rằng đồng hồ client nào cũng đồng bộ tuyệt đối.

### 11.2. Optimistic concurrency bằng version

Một object có thể mang `revision`:

~~~javascript
{
  _id: "draft-101",
  ownerId: "user-01",
  revision: 7,
  status: "DRAFT"
}
~~~

Nếu người dùng đã nhìn thấy revision 7 và xác nhận xóa bản đó:

~~~javascript
const deletedDraft = db.drafts.findOneAndDelete({
  _id: "draft-101",
  ownerId: "user-01",
  revision: 7,
  status: "DRAFT"
})
~~~

Nếu một request khác sửa nội dung thành revision 8 hoặc chuyển sang `PUBLISHED` trước thao tác, filter không khớp, nên bản mới không bị xóa nhầm. Ứng dụng có thể trả conflict và yêu cầu người dùng kiểm tra lại, thay vì fallback sang `deleteOne({_id})` làm mất ràng buộc.

### 11.3. Filter phải bao gồm ranh giới quyền truy cập

Một API multi-tenant không được chỉ dùng:

~~~javascript
db.orders.findOneAndDelete({ _id: request.params.orderId })
~~~

nếu ID có thể truy cập xuyên tenant. Khi cần, bổ sung `tenantId`, owner và trạng thái theo principal đã xác thực:

~~~javascript
const deleted = db.orders.findOneAndDelete({
  _id: orderId,
  tenantId: authenticatedTenantId,
  status: "DRAFT"
})
~~~

`authenticatedTenantId` phải được lấy từ ngữ cảnh đã xác thực/ủy quyền, không đơn thuần tin query string của client. Atomicity giúp bảo vệ tính nhất quán, **không thay thế authorization**.

## 12. Dùng làm hàng đợi “lấy rồi xóa”: ưu và nhược

Một hàng đợi đơn giản:

~~~javascript
const job = db.jobs.findOneAndDelete(
  { status: "READY" },
  {
    sort: { createdAt: 1, _id: 1 }
  }
)

if (job !== null) {
  // Ứng dụng tiếp tục xử lý job.payload ở bên ngoài MongoDB.
}
~~~

### Ưu điểm

- Code ngắn gọn, một thao tác lấy-xóa và trả về nội dung.
- Hai worker không cùng nhận một document bị xóa trong những lời gọi cạnh tranh.
- Không cần thêm trạng thái `PROCESSING` hoặc cơ chế giải phóng lock.
- Phù hợp với **dữ liệu dùng một lần** khi mất phần tử sau khi lấy là yêu cầu chấp nhận được, chẳng hạn một số cache/ticket tạm thời với hợp đồng rõ.

### Nhược điểm quan trọng

- **Worker crash sau khi xóa ⇒ job có thể mất.**
- Khi xử lý ngoài MongoDB thất bại, không còn document gốc để retry nếu không lưu ở nơi khác.
- Timeout sau commit khiến worker không biết job nào đã bị xóa và có thể không có payload để xử lý.
- Không có cơ chế ack/retry/dead-letter mặc định.
- Việc ưu tiên và phân phối công việc chịu cạnh tranh, index và topology; không có sẵn SLA của một message broker chuyên dụng.

**Kết luận kiến trúc:** nếu công việc không được phép mất, hãy thiết kế **claim/lease/ack** hoặc một queue system có bảo đảm giao nhận phù hợp. Không dùng `findOneAndDelete()` chỉ vì nó ngăn hai worker nhận trùng mà bỏ qua failure recovery.

## 13. Mẫu an toàn hơn cho hàng đợi: claim bằng `findOneAndUpdate()`

Thay vì xóa ngay, worker **đánh dấu job đã được nhận** và đặt một thời hạn thuê (*lease*). Xử lý xong mới xác nhận hoàn thành hoặc xóa có điều kiện.

~~~mermaid
flowchart LR
    READY["READY"] -->|"findOneAndUpdate + claim token"| LEASED["LEASED"]
    LEASED -->|"Xử lý thành công + ACK"| DONE["DONE hoặc xóa"]
    LEASED -->|"Hết lease / retry"| READY
    LEASED -->|"Quá số lần thử"| DEAD["DEAD LETTER"]
~~~

### 13.1. Khởi tạo job có thể phục hồi

~~~javascript
db.reliable_jobs.insertOne({
  _id: "reliable-job-001",
  status: "READY",
  createdAt: new Date(),
  availableAt: new Date(),
  attempts: 0,
  payload: { type: "EXPORT", reportId: "r-777" }
})
~~~

### 13.2. Claim một job

~~~javascript
const now = new Date()
const workerId = "worker-01"
const claimToken = new ObjectId().toString()
const leaseUntil = new Date(now.getTime() + 60000)

const claimed = db.reliable_jobs.findOneAndUpdate(
  {
    $or: [
      {
        status: "READY",
        availableAt: { $lte: now }
      },
      {
        status: "LEASED",
        leaseUntil: { $lte: now }
      }
    ]
  },
  {
    $set: {
      status: "LEASED",
      leaseOwner: workerId,
      claimToken: claimToken,
      leaseUntil: leaseUntil,
      claimedAt: now
    },
    $inc: { attempts: 1 }
  },
  {
    sort: { createdAt: 1, _id: 1 },
    returnDocument: "after"
  }
)

printjson(claimed)
~~~

Thao tác cập nhật trạng thái của **một job** có tính nguyên tử. Một job đã chuyển từ `READY` sang `LEASED` và chưa hết hạn sẽ không được lấy bởi worker khác nếu tất cả worker dùng cùng giao thức filter/lease.

### 13.3. ACK có điều kiện theo claim token

Sau khi xử lý thành công, worker có thể xóa job **chỉ khi mình vẫn sở hữu lease**:

~~~javascript
if (claimed !== null) {
  const ack = db.reliable_jobs.findOneAndDelete({
    _id: claimed._id,
    status: "LEASED",
    leaseOwner: workerId,
    claimToken: claimToken
  })

  printjson(ack)
}
~~~

Điều kiện `claimToken` giúp tránh một worker cũ xóa job sau khi lease đã được worker khác claim lại. Một hệ thống yêu cầu nghiêm ngặt có thể bổ sung kiểm tra thời hạn và **fencing token** tại hệ thống thực thi side effect. Chỉ có lease trong MongoDB không tự ngăn worker cũ tiếp tục gửi lệnh tới dịch vụ ngoài sau khi lease hết hạn.

### 13.4. Khi xử lý thất bại

Ứng dụng có thể dùng conditional update theo `claimToken` để:

- Trả job về `READY` với `availableAt` ở tương lai nhằm backoff.
- Tăng `attempts` và ngừng retry sau giới hạn.
- Chuyển sang `DEAD_LETTER` để vận hành kiểm tra.
- Gia hạn lease định kỳ nếu công việc dài, chỉ khi owner/token vẫn đúng.

Đừng chỉ sửa `status` về READY mà không kiểm tra owner/token: một worker cũ có thể vô tình giải phóng lease thuộc worker mới.

### 13.5. At-least-once không đồng nghĩa exactly-once effect

Trong workflow có retry, job có thể chạy lại nếu worker đã xử lý side effect nhưng crash trước ACK. Vì vậy **handler phải idempotent** hoặc dùng khóa nghiệp vụ ổn định, transaction/outbox và cơ chế dedupe ở hệ thống nhận. Thiết kế claim/lease thường hướng tới **không mất việc**, chấp nhận khả năng xử lý lại; xử lý đúng một hiệu ứng nghiệp vụ cần thêm bảo đảm.

## 14. Timeout và kết quả commit không chắc chắn

Xét tình huống:

~~~mermaid
sequenceDiagram
    participant Client
    participant DB as MongoDB
    Client->>DB: findOneAndDelete({status:"READY"})
    DB->>DB: Chọn và xóa job-101
    DB--xClient: Phản hồi bị mất vì lỗi mạng
    Note over Client: Không biết đã xóa job nào
    Client->>DB: Gửi lệnh mới cùng filter rộng
    DB-->>Client: Có thể xóa job-102
~~~

Đây là bẫy lớn: **bản thân thao tác nguyên tử không làm cho một yêu cầu API gửi lại trở nên idempotent**.

### 14.1. Retry của driver và retry của ứng dụng không giống nhau

Trong những phiên bản/topology/loại lệnh được hỗ trợ, MongoDB driver có thể sử dụng **retryable writes** để thử lại cùng một thao tác ghi theo cơ chế nhận diện của driver. `findOneAndDelete` là thao tác trong nhóm read-modify-write có khả năng hỗ trợ retryable writes theo điều kiện tương ứng.

Nhưng:

- Một **HTTP request mới** có thể tạo một **MongoDB operation mới**, không cùng identity với lần driver retry.
- Nếu filter rộng (`status:"READY"`), một lời gọi mới có thể chọn document khác.
- Không phải mọi lỗi hoặc mọi topology đều bảo đảm retry theo cùng cách.
- Không được tự giả định việc lặp toàn bộ business function sẽ nhận lại document đã xóa trước đó.

Trong một số triển khai retryable writes, MongoDB phải lưu thêm thông tin phục vụ retry của thao tác find-and-modify; với document lớn hoặc replica set nhiều node, thao tác này có thể có chi phí đáng kể. Hãy xem behavior/metric theo phiên bản cụ thể.

### 14.2. Xóa theo `_id` khác với xóa theo filter rộng

Nếu yêu cầu là “xóa token `token-001`”, khi retry cùng filter:

~~~javascript
db.tokens.findOneAndDelete({ _id: "token-001" })
~~~

lần gọi sau có thể trả `null` nhưng **không xóa token thứ hai**. Điều này hỗ trợ hiệu ứng idempotent “token không còn tồn tại”, tuy nhiên không tự tái tạo **nội dung trả về của lần xóa đầu**.

Nếu yêu cầu là “lấy *một* token/job hợp lệ bất kỳ”, filter rộng có thể chọn document khác ở lần retry. Muốn replay cùng kết quả, cần request identity và nơi lưu document đã chọn hoặc cơ chế claim ổn định.

### 14.3. Mẫu request ledger khi cần trả lại document đã xóa

Đối với API như `POST /consume-token`, có thể:

1. Client gửi một `requestId` ổn định.
2. Server kiểm tra một request ledger với unique index.
3. Trong transaction, xóa token cụ thể và lưu kết quả vào ledger.
4. Khi nhận lại cùng requestId, trả kết quả đã lưu, không chạy một thao tác xóa mới.

Mô hình dữ liệu:

~~~javascript
{
  _id: "consume-req-001",
  operation: "CONSUME_TOKEN",
  targetId: "token-001",
  status: "COMPLETED",
  deletedSnapshot: {
    _id: "token-001",
    ownerId: "user-01",
    type: "ONE_TIME"
  },
  createdAt: ISODate("2026-05-15T10:00:00Z")
}
~~~

Không nên lưu bí mật nhạy cảm của token trong ledger nếu không cần; ví dụ trên chỉ minh họa metadata. Quyền truy cập, encryption, retention và dữ liệu trong `deletedSnapshot` cần được định nghĩa rõ.

### 14.4. Ví dụ transaction cho xóa và lưu kết quả

Ví dụ này giả định môi trường **replica set hoặc sharded cluster có hỗ trợ transaction**, và document đích đã tồn tại:

~~~javascript
const session = db.getMongo().startSession()

try {
  const result = await session.withTransaction(async () => {
    const txDb = session.getDatabase("atomic_delete_lab")
    const requestId = "req-remove-001"
    const targetId = "token-001"

    const existing = await txDb.delete_requests.findOne({
      _id: requestId
    })

    if (existing !== null) {
      if (existing.targetId !== targetId) {
        throw new Error("REQUEST_ID_REUSED_FOR_OTHER_TARGET")
      }
      return existing.deletedSnapshot
    }

    const deleted = await txDb.session_tokens.findOneAndDelete({
      _id: targetId
    })

    await txDb.delete_requests.insertOne({
      _id: requestId,
      targetId,
      status: "COMPLETED",
      deletedSnapshot: deleted,
      completedAt: new Date()
    })

    return deleted
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  printjson(result)
} finally {
  await session.endSession()
}
~~~

Trong trường hợp bình thường, transaction đảm bảo **xóa token và lưu ledger cùng commit hoặc cùng abort**. Nếu hai transaction cùng tranh chấp `requestId`, một transaction có thể gặp duplicate key hoặc write conflict; tầng ứng dụng cần retry/đọc ledger theo key và xử lý trạng thái commit không rõ ràng. Callback transaction không nên có side effect ngoài MongoDB do có thể được gọi lại trong cơ chế retry.

Đây chỉ là một phác thảo lab: để đưa vào production còn phải xác thực actor/tenant, ràng buộc request ID với payload/operation, giới hạn kích thước kết quả, chính sách TTL và xử lý lỗi driver.

## 15. Khi cần thay đổi nhiều document cùng lúc

`findOneAndDelete()` chỉ chọn/xóa **một document**. Đôi khi thao tác nghiệp vụ còn phải:

- Tăng counter thống kê.
- Ghi document audit.
- Tạo outbox event.
- Cập nhật một tài khoản hoặc bảng trạng thái khác.

Nếu các bước này cần nhất quán với thao tác xóa, có thể dùng **multi-document transaction**, trong deployment hỗ trợ, để thực hiện nhiều operation cùng commit.

~~~text
Transaction:
  findOneAndDelete(target)
  insertOne(audit record)
  updateOne(counter)
  insertOne(outbox event)
Commit
~~~

Tuy nhiên, transaction tăng chi phí và có giới hạn thời gian/khả năng cạnh tranh. Không biến một thao tác đọc-xóa đơn giản thành transaction nhiều phút khi có thể thiết kế lại dữ liệu. Ngoài ra, transaction MongoDB **không tự commit nguyên tử với email, cổng thanh toán hoặc message broker**. Với external side effect, dùng outbox và consumer có idempotency hoặc giao thức phù hợp.

### Khi cần xóa nhiều document?

Nếu muốn xóa **mọi document** khớp filter, dùng:

~~~javascript
db.expired_records.deleteMany({
  expiresAt: { $lte: new Date() }
})
~~~

`deleteMany()` trả thông tin số document đã bị xóa, **không trả nội dung từng document**. Ngoài transaction, `deleteMany()` không bảo đảm “tất cả document bị xóa trong một bước nguyên tử toàn tập”; tính nguyên tử ghi vẫn được hiểu ở phạm vi từng document.

Nếu phải lấy nội dung của từng document để lưu audit trước khi xóa, cần một workflow riêng có kiểm soát và cân nhắc transaction, archive-before-delete, hoặc copy-out/verify/delete. **Không lặp `findOneAndDelete()` rồi mặc định cả lô là atomic.**

## 16. So sánh các thao tác xóa liên quan

| Lệnh | Số document mục tiêu | Kết quả chính | Khi nào chọn |
|---|---|---|---|
| `findOneAndDelete(filter, options)` | Tối đa 1 | Document đã bị xóa hoặc `null` | Cần đọc kèm xóa đúng một document |
| `deleteOne(filter)` | Tối đa 1 | Kết quả có `deletedCount` | Chỉ cần xóa và biết có xóa được không |
| `deleteMany(filter)` | Nhiều | Kết quả tổng số bản ghi đã xóa | Xóa tập document theo điều kiện |
| `findOneAndUpdate(filter, update, options)` | Tối đa 1 | Document trước/sau update tùy option | Claim job, đổi trạng thái và nhận nội dung |
| `bulkWrite([...])` | Nhiều operation | Kết quả tổng hợp theo lô | Giảm overhead gửi nhiều lệnh ghi; không trả bản cũ như findOneAndDelete |
| `collection.drop()` | Cả collection | Trạng thái thao tác drop | Xóa luôn collection, index và metadata |

### 16.1. `findOneAndDelete` với `deleteOne`

~~~javascript
// Xóa một token, chỉ biết số bản ghi đã xóa.
const a = db.tokens.deleteOne({ _id: "token-002" })
printjson(a.deletedCount)

// Xóa một token và lấy lại nội dung trước khi xóa.
const b = db.tokens.findOneAndDelete({ _id: "token-003" })
printjson(b)
~~~

Nếu không cần nội dung, không nên dùng `findOneAndDelete()` chỉ vì tên lệnh nghe “đầy đủ” hơn. Chi phí trả document, hỗ trợ retry và mức tải phải được xét.

### 16.2. `findOneAndDelete` với `findOneAndUpdate`

~~~javascript
// Consume một lần: document biến mất ngay.
db.jobs.findOneAndDelete({ status: "READY" })

// Claim có thể phục hồi: document còn tồn tại, đổi status.
db.jobs.findOneAndUpdate(
  { status: "READY" },
  {
    $set: {
      status: "PROCESSING",
      claimedAt: new Date()
    }
  },
  { returnDocument: "after" }
)
~~~

Mẫu thứ hai vẫn cần lease, ownership, retry và ack nếu job có thể chạy lâu. Nhưng nó giữ dữ liệu để điều tra và phục hồi sau crash, không xóa ngay khi worker lấy.

### 16.3. Bulk không đồng nghĩa nguyên tử cả lô

~~~javascript
db.tokens.bulkWrite([
  {
    deleteOne: {
      filter: { _id: "token-004" }
    }
  },
  {
    deleteOne: {
      filter: { _id: "token-005" }
    }
  }
])
~~~

Các operation trong bulk giúp giảm overhead gọi lệnh và có lựa chọn thứ tự xử lý, nhưng **không tự tạo một transaction nguyên tử qua toàn bộ batch**. Nếu muốn không mất bất kỳ thao tác nào khi một phần batch lỗi, phải thiết kế retry/idempotency và xác minh kết quả theo từng mục tiêu; khi cần atomic toàn lô thì xem xét transaction với giới hạn phù hợp.

Trong các phiên bản MongoDB mới, một số API xóa đơn có thể hỗ trợ `sort`; hãy đối chiếu phiên bản/driver trước khi thay thế. Điểm quyết định chính vẫn là **có cần lấy document bị xóa về không**.

## 17. Hiệu năng: index, sort và chi phí ghi

Một lời gọi `findOneAndDelete()` thường có hai phần chi phí:

1. **Tìm** document phù hợp với filter và sort.
2. **Xóa** document, cập nhật các index và ghi nhận thay đổi theo cơ chế storage/replication.

Với collection lớn, filter rộng hoặc sort không có index phù hợp có thể làm MongoDB phải đọc nhiều document, quét nhiều index key hoặc sắp xếp tốn tài nguyên trước khi chọn document để xóa.

### 17.1. Đo phần tìm bằng query tương ứng

Để hiểu khả năng tận dụng index, có thể dùng một lệnh `find()` có cùng filter và sort:

~~~javascript
db.jobs.find({
  status: "READY"
}).sort({
  priority: -1,
  createdAt: 1,
  _id: 1
}).limit(1).explain("executionStats")
~~~

Quan sát `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned` và có hay không stage sort. Đây là cách **tham khảo** chi phí tìm; không phải phép đo toàn bộ công việc xóa và các thao tác retry nội bộ của `findOneAndDelete()`.

### 17.2. Index phải khớp query thực

~~~javascript
db.jobs.createIndex({
  status: 1,
  priority: -1,
  createdAt: 1,
  _id: 1
})
~~~

Chỉ số này có thể hữu ích cho query `status = READY` và sort priority/time/id. Nhưng nếu còn điều kiện `availableAt <= now`, tenant partition, job type hoặc priority thay đổi liên tục, thứ tự index cần được đánh giá lại dựa trên selectivity, scan, sort và chi phí update.

### 17.3. Không dùng `findOneAndDelete` để quét-xóa khối lượng lớn theo kiểu nóng

~~~javascript
// Không chạy vòng lặp này vô hạn trên collection production.
while (db.events.findOneAndDelete({ archived: true }) !== null) {
  // ...
}
~~~

Nếu mục tiêu là xóa toàn bộ nhiều triệu record, mỗi lần chỉ xóa một document có thể tạo rất nhiều round-trip, tranh chấp và tải server. Nên cân nhắc `deleteMany()`, phân lô có giới hạn, retention/TTL, partition/archival, hoặc pipeline snapshot-export-verify-delete tùy mục tiêu. Nếu cần biết toàn bộ document bị xóa, yêu cầu đó phải được thiết kế như một quy trình archive/audit, không chỉ như vòng lặp đọc-xóa.

### 17.4. Nhiều worker cạnh tranh cùng head của queue

Khi hàng nghìn worker đều tìm job đầu tiên theo một index/sort, có thể xuất hiện contention. Một index hiệu quả cho lọc không tự bảo đảm queue scale tuyến tính. Có thể cần:

- Partition job theo tenant, queue name hoặc shard key.
- Giới hạn số worker polling và thêm backoff khi không có job.
- Batch/claim phù hợp để giảm số lần tìm.
- Giám sát CPU, lock/contention, p95/p99, IOPS và replication lag.

Nếu hệ thống có SLA phân phối công việc phức tạp, cân nhắc message broker thay vì cố biến collection thành hàng đợi tổng quát.

## 18. Replica set, write concern và sharded cluster

### 18.1. Replica set

Trên replica set, thao tác xóa được thực hiện trên primary theo mô hình replica set và được nhân bản. Kết quả thao tác ghi chịu ảnh hưởng của **write concern**, khả năng failover và cơ chế retry.

- `w: 1` xác nhận từ primary theo cấu hình áp dụng; không đồng nghĩa dữ liệu đã được majority xác nhận.
- `w: "majority"` yêu cầu mức xác nhận đa số theo semantics của MongoDB/deployment; ảnh hưởng latency và độ bền khi failover.
- Nếu client mất phản hồi, không thể suy luận chỉ từ timeout rằng chưa xóa.
- Các client phải hiểu read preference/read concern và yêu cầu quan sát sau ghi trong topology cụ thể.

Atomicity một document và durability/khả năng quan sát sau failover là **hai khía cạnh khác nhau**. Hãy xác định write concern phù hợp với giá trị của dữ liệu bị xóa.

### 18.2. Sharded cluster

Trong sharded cluster, filter chính xác theo shard key giúp hệ thống định tuyến hiệu quả tới shard liên quan, nhất là khi xóa theo một ID nghiệp vụ đã biết. Với filter rộng hoặc sort toàn cụm, việc tìm ứng viên và điều phối có thể phức tạp, tốn tài nguyên và chịu các giới hạn theo phiên bản.

Không giả định mọi thao tác `findOneAndDelete({status:"READY"}, {sort:...})` sẽ cung cấp FIFO toàn cụm hoặc khả năng mở rộng lý tưởng. Khi thiết kế queue sharded, cần cân nhắc:

- Shard key và ranh giới hàng đợi.
- Điều kiện định tuyến trong filter.
- Tải tập trung tại các shard chứa nhiều job ưu tiên cao.
- Chi phí index, cross-shard operations và topology.
- Các yêu cầu transaction, consistency và failover.

Kiểm tra tài liệu của **phiên bản MongoDB thực tế** trước khi lựa chọn cú pháp, đặc biệt khi dùng tùy chọn phức tạp và transaction trên sharded collection.

### 18.3. Xóa không phải phương án backup

Một document bị xóa và thao tác xóa được nhân bản không có nghĩa secondary sẽ giữ lại một bản cho khôi phục. Nếu xóa nhầm dữ liệu quan trọng, phục hồi thường phụ thuộc backup/snapshot hoặc log/history được thiết kế riêng. Với dữ liệu cần bảo quản, đừng xây dựng quy trình bằng cách xóa trước rồi mới thử lưu bản sao sau.

## 19. Sử dụng `findOneAndDelete` trong Java Driver

Trong MongoDB Java Sync Driver, thao tác có phương thức tương ứng:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.FindOneAndDeleteOptions;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

MongoCollection<Document> jobs = database.getCollection("jobs");

FindOneAndDeleteOptions options = new FindOneAndDeleteOptions()
    .sort(Sorts.orderBy(
        Sorts.descending("priority"),
        Sorts.ascending("createdAt"),
        Sorts.ascending("_id")
    ))
    .projection(Projections.include(
        "_id", "status", "priority", "payload", "createdAt"
    ));

Document deleted = jobs.findOneAndDelete(
    Filters.eq("status", "READY"),
    options
);

if (deleted == null) {
    System.out.println("Không có job phù hợp");
} else {
    System.out.println("Đã lấy và xóa: " + deleted.getString("_id"));
}
~~~

Biến `database` ở ví dụ được giả định là `MongoDatabase` đã nhận từ `MongoClient` kết nối đúng database lab. Không có lệnh `use` bên trong Java như mongosh; Java driver chỉ rõ database khi lấy handle.

### 19.1. So sánh API Java

~~~java
// Chỉ xóa, đọc số bản ghi bị xóa.
long deletedCount = jobs.deleteOne(
    Filters.eq("_id", "job-101")
).getDeletedCount();

// Xóa và nhận document cũ.
Document deletedJob = jobs.findOneAndDelete(
    Filters.eq("_id", "job-102")
);
~~~

Nếu cần asynchronous/reactive driver, API khác cách gọi nhưng cùng ngữ nghĩa MongoDB. Khi sử dụng framework như Spring Data MongoDB, hãy xác minh method được chọn thực sự là một operation tìm-xóa nguyên tử, không phải hai call `find` và `remove` tách rời.

### 19.2. Mã ứng dụng phải xử lý kết quả `null`

Không nên viết:

~~~java
Document deleted = jobs.findOneAndDelete(
    Filters.eq("_id", "missing")
);
System.out.println(deleted.getString("_id")); // Có thể NullPointerException.
~~~

Hãy kiểm tra `deleted != null` trước khi đọc field hoặc thực hiện side effect.

## 20. An toàn nghiệp vụ khi đọc rồi xóa

### 20.1. Mã sử dụng một lần

Giả sử collection lưu token một lần:

~~~javascript
{
  _id: "token-001",
  ownerId: "user-01",
  purpose: "CONFIRM_ACTION",
  status: "ACTIVE",
  expiresAt: ISODate("2026-12-31T00:00:00Z")
}
~~~

Một API có thể tiêu thụ token:

~~~javascript
const consumed = db.one_time_tokens.findOneAndDelete({
  _id: submittedTokenId,
  ownerId: authenticatedUserId,
  purpose: "CONFIRM_ACTION",
  status: "ACTIVE",
  expiresAt: { $gt: new Date() }
})

if (consumed === null) {
  // Token không tồn tại, đã dùng, hết hạn, sai mục đích hoặc không thuộc user.
}
~~~

Hành vi “token biến mất khi dùng” có thể phù hợp. Tuy nhiên, nếu việc tiêu thụ token phải đi kèm thay đổi một resource khác, cần xem xét transaction và xử lý commit không chắc chắn. **Không dùng việc token có trong database như bằng chứng duy nhất rằng người dùng được phép làm hành động**; phải xác thực request và ràng buộc token vào user/purpose.

### 20.2. Dọn record hết hạn và cần audit

Nếu chỉ xóa hàng loạt record hết hạn, `deleteMany()` có thể phù hợp. Nếu cần đưa từng record sang archive, nên có pipeline **archive → verify → delete có điều kiện**. `findOneAndDelete()` lấy được nội dung document trước khi xóa, nhưng nếu process chết sau khi xóa mà chưa lưu archive, bản ghi vẫn có thể mất.

### 20.3. Xóa bản nháp có điều kiện

Khi người dùng yêu cầu xóa một bản nháp đang sửa:

~~~javascript
db.drafts.findOneAndDelete({
  _id: draftId,
  tenantId: tenantIdFromAuth,
  ownerId: currentUserId,
  revision: expectedRevision,
  status: "DRAFT"
})
~~~

Đây là ví dụ tốt cho filter gồm **identity + authorization scope + trạng thái + revision**. Nếu trả `null`, ứng dụng không nên tự chuyển sang xóa theo `_id`; cần phân biệt không tồn tại, không được phép và xung đột phiên bản theo API contract, tránh tiết lộ thông tin không được phép.

## 21. Những sai lầm phổ biến

| Sai lầm | Vì sao sai? | Cách đúng |
|---|---|---|
| `findOne()` rồi `deleteOne()` và coi là atomic | Có khoảng trống cho cập nhật/worker khác | Dùng `findOneAndDelete()` hoặc guard + transaction khi phù hợp |
| Không kiểm tra `deletedCount` trong cách hai lệnh | Worker khác có thể đã xóa trước | Nếu chưa đổi kiến trúc, ít nhất kiểm tra kết quả; tốt hơn là một lệnh |
| Gọi `findOneAndDelete({})` | Có thể xóa một document bất kỳ | Filter rõ và sort khi chọn theo thứ tự |
| Giả định sort theo một field luôn ổn định | Giá trị trùng nhau không có tie-breaker | Thêm `_id`/khóa duy nhất vào sort |
| Cho rằng projection chỉ xóa vài field | Projection chỉ giới hạn giá trị trả về | Muốn xóa field dùng `$unset`, không phải findOneAndDelete |
| Mong nhận `deletedCount` từ `findOneAndDelete()` | API trả document hoặc `null` | Chọn `deleteOne()` nếu chỉ cần count |
| Dùng queue lấy-xóa cho job không được phép mất | Worker crash làm mất job | Claim/lease/ack + retry/idempotency |
| Gọi lại filter rộng sau timeout | Có thể xóa thêm một document khác | Request ledger, claim ổn định hoặc xác định theo `_id` |
| Coi retryable writes là idempotency của HTTP | HTTP retry mới có thể là operation mới | Giữ request ID và replay response theo contract |
| Coi thao tác trên một document là transaction toàn workflow | Không bao phủ external service hoặc collection khác | Transaction/outbox theo ranh giới nhất quán |
| Dùng `deleteMany()` với yêu cầu xóa toàn lô atomic | Không có atomicity toàn tập mặc định | Transaction khi cần và phù hợp giới hạn |
| Bỏ qua tenant/owner trong filter | Có thể xóa resource ngoài phạm vi quyền | Tích hợp authorization scope vào điều kiện |
| Xóa trước rồi export archive | Lỗi giữa hai bước có thể mất dữ liệu | Export, verify, sau đó delete có điều kiện |
| Dùng filter không index trên collection lớn | Quét/sort tốn CPU/I/O | Index theo filter+sort, đo bằng query đại diện |

## 22. Bài thực hành đầy đủ

Hãy thực hiện trên database `atomic_delete_lab`. Để bài có kết quả ổn định, bắt đầu từ bộ dữ liệu `jobs` trong mục 4 với một database lab mới.

### Phần A — Chọn và xóa

**Bài A1.** Tìm job có `status = "READY"` và priority cao nhất, nếu bằng nhau chọn `createdAt` cũ hơn, nếu vẫn bằng chọn `_id` nhỏ hơn. Dùng `findOneAndDelete()` và in `_id`. Dự đoán:

~~~text
Lần 1: job-102
Lần 2: job-104
Lần 3: job-101
Lần 4: job-105
Lần 5: null
~~~

Với bộ dữ liệu gốc, `job-103` có status DONE nên không bị xóa bởi filter READY, mặc dù priority 9.

~~~javascript
function takeNextReadyJob() {
  return db.jobs.findOneAndDelete(
    { status: "READY" },
    {
      sort: {
        priority: -1,
        createdAt: 1,
        _id: 1
      }
    }
  )
}

printjson(takeNextReadyJob())
~~~

**Bài A2.** Dùng `projection` để chỉ trả `_id`, `status` và `priority`. Xác nhận document bị xóa hoàn toàn dù `payload` không được trả về.

**Bài A3.** Xóa một `_id` không tồn tại, quan sát `null` và giải thích ý nghĩa.

### Phần B — So sánh với lệnh khác

**Bài B1.** Viết một lệnh `deleteOne()` theo `_id`; mô tả khác biệt giữa `DeleteResult.deletedCount` và document từ `findOneAndDelete()`.

**Bài B2.** Viết `deleteMany()` để xóa mọi job status DONE trong lab. Nêu vì sao không trả các document bị xóa, và tại sao không được coi cả lô là một write atomic duy nhất.

**Bài B3.** Viết `bulkWrite()` xóa hai ID cụ thể. Nếu một ID không tồn tại, giải thích lệnh có kết quả gì và vì sao vẫn không đồng nghĩa transaction nguyên tử cho mọi operation.

### Phần C — Concurrent workers

Mở hai mongosh cùng kết nối đến **một database lab**, mỗi shell chạy:

~~~javascript
const removed = db.jobs.findOneAndDelete(
  { status: "READY" },
  { sort: { createdAt: 1, _id: 1 } }
)

printjson(removed)
~~~

Quan sát rằng khi có nhiều job, hai lời gọi có thể nhận hai document khác nhau. Nếu chỉ có đúng một job READY, một lời gọi có thể nhận job, lời gọi sau nhận `null`. Không cần cố làm cho hai thread “đến đúng một thời điểm tuyệt đối”; mục tiêu là hiểu ranh giới atomicity.

**Câu hỏi:** Nếu worker xóa job rồi crash, MongoDB có tự tái tạo document không? Trình bày cơ chế cần thêm để tránh mất job.

### Phần D — Thiết kế queue có retry

Thay mẫu xóa ngay bằng:

1. `findOneAndUpdate` để claim một job READY với `claimToken` duy nhất và `leaseUntil`.
2. Một handler idempotent xử lý payload.
3. Conditional `findOneAndDelete` để ACK theo `_id + claimToken`.
4. Retry với backoff khi lease hết hạn.
5. Dead-letter sau số lần thử tối đa.

Giải thích race khi worker A bị treo, lease hết hạn, worker B claim lại, rồi A bất ngờ hoàn thành. Vì sao việc ACK phải dùng claim token và có thể cần fencing ở hệ thống bên ngoài?

### Phần E — Thiết kế API xóa bản nháp

Một hệ thống nhiều tenant có document:

~~~javascript
{
  _id: "draft-101",
  tenantId: "tenant-A",
  ownerId: "user-7",
  status: "DRAFT",
  revision: 3,
  content: { title: "Bản đề xuất" }
}
~~~

Hãy viết filter để xóa document **chỉ khi**:

- `_id` đúng yêu cầu.
- `tenantId` và `ownerId` lấy từ principal được xác thực.
- `status` vẫn là DRAFT.
- `revision` còn bằng 3.

Nếu lệnh trả `null`, giải thích cách API có thể xử lý **xung đột trạng thái** mà không vô tình tiết lộ document của tenant khác.

## 23. Câu hỏi ôn tập và đáp án

**1. `findOneAndDelete()` thực hiện nguyên tử điều gì?**

Nó tìm, chọn và xóa **một document** trong một thao tác trên MongoDB, đồng thời trả về document trước khi bị xóa. Nó không biến xử lý công việc phía ứng dụng thành một transaction.

**2. Vì sao `findOne()` rồi `deleteOne()` không tương đương?**

Vì có cửa sổ giữa đọc và xóa cho tiến trình khác thay đổi/xóa document. Hai worker có thể cùng đọc một job trước khi một worker xóa nó.

**3. Khi nhiều document cùng khớp, làm sao chọn document cần xóa?**

Dùng `sort` trong options. Nếu các field sort có giá trị trùng, nên thêm khóa phân giải duy nhất như `_id` để tạo thứ tự xác định trên tập dữ liệu ổn định.

**4. Kết quả `findOneAndDelete()` khác `deleteOne()` thế nào?**

`findOneAndDelete()` trả document cũ hoặc `null`; `deleteOne()` trả kết quả ghi có `deletedCount`. Không dùng lẫn lộn kiểu kết quả.

**5. Projection có làm chỉ một phần document bị xóa không?**

Không. Projection chỉ giới hạn field của document **trả về**; toàn document bị xóa khỏi collection.

**6. Vì sao worker dùng `findOneAndDelete()` vẫn có thể làm mất job?**

Document bị xóa ngay khi worker lấy. Nếu worker chết trước khi hoàn tất công việc, không còn bản ghi trong collection để retry.

**7. Khi nào nên dùng `findOneAndUpdate()` thay vì `findOneAndDelete()`?**

Khi cần giữ job trong database, đánh dấu PROCESSING/LEASED, có thời hạn lease, retry, ack và khả năng phục hồi sau lỗi.

**8. Một retry HTTP với filter `{status:"READY"}` có an toàn sau timeout không?**

Không tự động. Nếu lần đầu đã xóa job A nhưng mất phản hồi, retry mới có thể xóa job B. Cần request identity/ledger hoặc claim ổn định.

**9. Filter thêm `revision` có lợi ích gì?**

Nó bảo đảm chỉ xóa trạng thái mà client đã biết/được phép xóa; nếu document đã đổi revision, thao tác không khớp thay vì xóa bản mới.

**10. Có thể dùng `findOneAndDelete()` để xóa 100 document nguyên tử không?**

Không. Mỗi lần gọi chỉ xóa tối đa một document. Nhiều lần gọi không tự là transaction; `deleteMany()` cũng không mặc định atomic toàn tập ngoài transaction.

**11. Retryable writes có giải quyết mất phản hồi ở mọi cấp hệ thống không?**

Không. Driver retry một operation theo quy tắc hỗ trợ của MongoDB; request mới ở cấp ứng dụng có thể là operation khác. Với delete theo filter rộng phải có bảo đảm nghiệp vụ riêng.

**12. Vì sao cần index phù hợp khi dùng `sort`?**

Để giảm lượng document/key phải quét và chi phí sắp xếp trước khi chọn một document. Tuy nhiên index cũng làm tăng chi phí ghi/xóa, nên cần đo theo workload thực.

**13. Khi dùng `findOneAndDelete()` cho mã dùng một lần, cần kiểm tra gì ngoài việc token tồn tại?**

Phải xác thực user, mục đích, hạn dùng, trạng thái và ranh giới quyền; nếu cần cập nhật tài nguyên khác cùng lúc, xem xét transaction và xử lý commit chưa biết.

**14. Replica set có phải backup cho document vừa bị xóa không?**

Không. Thao tác xóa hợp lệ được nhân bản; khả năng phục hồi dữ liệu đã xóa phụ thuộc hệ thống backup/history được thiết kế riêng.

## 24. Bảng quyết định nhanh

| Nhu cầu thực tế | Hướng tiếp cận |
|---|---|
| Xóa một document theo ID, không cần nội dung | `deleteOne({_id})` |
| Xóa một document và lấy snapshot trước khi xóa | `findOneAndDelete({_id})` |
| Chọn một document theo filter + thứ tự rồi xóa | `findOneAndDelete(filter, {sort})` |
| Chọn một document rồi giữ lại để worker xử lý/retry | `findOneAndUpdate` + claim/lease/ack |
| Xóa nhiều document theo điều kiện | `deleteMany(filter)` và kế hoạch tải |
| Gộp nhiều lệnh xóa/ghi để giảm round-trip | `bulkWrite` (không đồng nghĩa atomic cả batch) |
| Xóa và ghi audit/outbox/counter nhất quán | Transaction nếu deployment hỗ trợ và phù hợp |
| Cần archive dữ liệu trước khi xóa | Export → verify → delete có điều kiện |
| Xóa record theo tuổi dữ liệu | TTL/retention phù hợp; không coi TTL là archive |
| Retry được cùng một request và trả cùng kết quả xóa | Stable request ID + ledger/transaction/idempotency |

## 25. Kết luận

`findOneAndDelete()` phù hợp khi nghiệp vụ cần **chọn một document, xóa nguyên tử và nhận nội dung vừa bị xóa**. Nó giải quyết chính xác race condition của mô hình “đọc trước, xóa sau” ở phạm vi một document; `filter` bảo vệ điều kiện xóa, `sort` định nghĩa cách chọn ứng viên, còn `projection` chỉ định nội dung phản hồi.

Nhưng **nguyên tử không đồng nghĩa an toàn cho toàn bộ quy trình**. Nếu document đại diện một công việc phải xử lý thành công, việc xóa ngay khi nhận có thể làm mất việc sau crash. Nếu client mất phản hồi sau commit, gọi lại cùng filter rộng có thể xóa một document khác. Hãy dùng claim/lease/ack, request identity, transaction, outbox hoặc queue service phù hợp với yêu cầu retry, durability và idempotency. Quyết định tốt luôn bắt đầu từ câu hỏi: **“Tôi muốn xóa dữ liệu sau khi đã dùng nó, hay tôi cần bảo đảm công việc có thể được tiếp tục sau mọi lỗi?”**

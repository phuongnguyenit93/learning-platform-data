# Mô hình lịch sử, phiên bản và dữ liệu cần lưu trữ lâu dài trong MongoDB

Không phải mọi dữ liệu trong MongoDB đều chỉ cần biểu diễn **trạng thái hiện tại**. Một đơn hàng cần giữ giá ở thời điểm mua; hợp đồng cần truy xuất bản đã ký; cấu hình nghiệp vụ cần biết ai sửa và sửa khi nào; nhật ký thiết bị có thể phải lưu nhiều năm dù rất ít khi được đọc. Những yêu cầu đó đưa bài toán thiết kế document vượt ra ngoài CRUD thông thường: phải xác định **thông tin nào được giữ lại, giữ ở đâu, trong bao lâu và truy xuất theo thời gian như thế nào**.

MongoDB cho phép nhiều cách mô hình hóa: lưu phiên bản cũ ở collection lịch sử, lưu các sự kiện bất biến, chụp snapshot, lưu các khoảng hiệu lực, giữ một tập dữ liệu nóng và chuyển phần cũ sang kho lưu trữ. Không có một mô hình duy nhất tối ưu cho mọi hệ thống. Quyết định phải xuất phát từ yêu cầu truy vấn, khả năng khôi phục, tính toàn vẹn, giới hạn dung lượng và chính sách bảo quản dữ liệu.

Bài học nằm trong chương **Mô hình document** và tập trung vào thiết kế dữ liệu. Các lệnh minh họa dùng **mongosh**, database thử nghiệm `document_history_lab` và các document có ID chuỗi để dễ đọc. Những hành vi phụ thuộc phiên bản MongoDB, driver hoặc topology cần kiểm tra trong môi trường triển khai cụ thể.

## 1. Vì sao mô hình trạng thái hiện tại chưa đủ?

Giả sử một nền tảng bảo hiểm có document hợp đồng:

~~~javascript
{
  _id: "policy-1001",
  customerId: "customer-008",
  premium: NumberDecimal("1200000.00"),
  currency: "VND",
  coverage: "BASIC",
  status: "ACTIVE",
  updatedAt: ISODate("2026-04-15T09:00:00Z")
}
~~~

Nếu ứng dụng chạy lệnh:

~~~javascript
db.policies.updateOne(
  { _id: "policy-1001" },
  {
    $set: {
      premium: NumberDecimal("1500000.00"),
      updatedAt: new Date()
    }
  }
)
~~~

thì document hiện tại thể hiện phí mới. Nhưng document này **không trả lời được**:

- Phí ban đầu của hợp đồng là bao nhiêu?
- Phí thay đổi ở phiên bản nào, có hiệu lực từ ngày nào?
- Ai yêu cầu thay đổi và vì lý do gì?
- Hệ thống đã biết điều chỉnh đó từ thời điểm nào?
- Nếu ứng dụng ghi sai, bản đúng trước đó có thể phục hồi không?
- Sau bảy năm, tài liệu nào cần còn truy xuất được để phục vụ kiểm toán hoặc tranh chấp?

Nếu không thiết kế từ đầu, việc khôi phục thông tin từ log ứng dụng hoặc backup có thể thiếu, rất chậm hoặc không đáp ứng chuẩn bằng chứng nghiệp vụ.

### Ba mục tiêu thường bị trộn lẫn

| Mục tiêu | Câu hỏi cần trả lời | Dữ liệu cần giữ |
|---|---|---|
| **Lịch sử trạng thái** | Tại một lần sửa hoặc thời điểm trước đây, document có giá trị nào? | Các revision/snapshot, thời gian và định danh thực thể |
| **Audit trail** | Ai làm gì, bằng kênh nào, vì sao và kết quả ra sao? | Actor, operation, request/correlation ID, thời điểm, old/new hoặc event |
| **Lưu trữ lâu dài** | Dữ liệu cần còn đọc được sau nhiều năm với chi phí nào? | Bản dữ liệu có version/schema, metadata, chính sách retention, archive và khả năng phục hồi |

Một collection history có thể hỗ trợ cả ba mục tiêu, nhưng không mặc định thỏa mãn yêu cầu pháp lý về audit hoặc retention. Ví dụ, lưu snapshot cũ mà không có actor và nguyên nhân thì chưa đủ điều tra; lưu một log sự kiện nhưng không giữ schema đọc cũ thì có thể không tái dựng được trạng thái.

## 2. Phân biệt ba kiểu phiên bản

Khi nói “version”, cần ghi rõ version của **cái gì**.

| Loại | Ý nghĩa | Ví dụ | Thường dùng để |
|---|---|---|---|
| **Business revision** | Số lần trạng thái một thực thể được thay đổi theo nghiệp vụ | Hợp đồng `revision: 4` | Lấy trạng thái cũ, chống ghi đè đồng thời, audit |
| **Schema version** | Phiên bản cấu trúc document mà code biết cách đọc | `schemaVersion: 2` | Migration, đọc dữ liệu cũ, tương thích ứng dụng |
| **Event format version** | Phiên bản cấu trúc payload của sự kiện | `eventVersion: 1` | Xử lý/replay event được tạo từ các phiên bản ứng dụng khác nhau |

Một hợp đồng có `revision: 7` vẫn có thể lưu theo `schemaVersion: 2`. Một event `PolicyPremiumChanged` có `eventVersion: 1` chưa chắc tương ứng với revision 1 của hợp đồng. **Không dùng chung một field `version` mơ hồ** cho cả ba mục đích.

Ví dụ:

~~~javascript
{
  _id: "policy-1001",
  revision: 7,
  schemaVersion: 2,
  customerId: "customer-008",
  terms: {
    premium: NumberDecimal("1500000.00"),
    currency: "VND",
    coverage: "STANDARD"
  },
  updatedAt: ISODate("2026-04-15T09:00:00Z")
}
~~~

Ở cấp nghiệp vụ, `revision` tăng khi trạng thái liên quan được thay đổi. Ở cấp schema, `schemaVersion` chỉ thay khi định dạng lưu trữ cần được đọc/xử lý khác trước. Thời điểm thay đổi schema không nhất thiết là một lần sửa nghiệp vụ.

## 3. Thời gian trong dữ liệu lịch sử: “khi nào” có hai nghĩa

Một sai lầm phổ biến là thêm một field `updatedAt` rồi coi đó là đủ để biểu diễn toàn bộ quá khứ.

### 3.1. Thời điểm ghi nhận và thời điểm hiệu lực

- **Recorded time / transaction time:** hệ thống ghi nhận thông tin khi nào. Trong mô hình ứng dụng, thường có `recordedAt` hoặc `createdAt`.
- **Valid time / effective time:** thông tin có hiệu lực đối với thế giới nghiệp vụ trong khoảng nào; thường có `validFrom` và `validTo`.

Ví dụ: ngày 10/05, nhân viên nhập một quyết định tăng phí **có hiệu lực từ 01/05**. Hai mốc không trùng nhau:

~~~javascript
{
  entityId: "policy-1001",
  revision: 5,
  premium: NumberDecimal("1500000.00"),
  validFrom: ISODate("2026-05-01T00:00:00Z"),
  recordedAt: ISODate("2026-05-10T08:30:00Z")
}
~~~

Câu hỏi “Phí hợp đồng có hiệu lực ngày 03/05 là bao nhiêu?” khác với “Đến ngày 03/05, **hệ thống đã biết** phí bao nhiêu?”. Đây là nền tảng của tư duy **bitemporal** (hai trục thời gian).

### 3.2. Khoảng thời gian nửa mở

Khi biểu diễn các phiên bản có hiệu lực theo khoảng, một quy ước hữu ích là:

~~~text
[validFrom, validTo)
 bao gồm validFrom
 không bao gồm validTo

Phiên bản A: [2026-01-01, 2026-04-01)
Phiên bản B: [2026-04-01, 2026-07-01)
Phiên bản C: [2026-07-01, vô hạn)
~~~

Giả sử `validTo: null` nghĩa là chưa có mốc kết thúc. Query tìm khoảng còn hiệu lực tại `t` phải xét cả bản chưa có `validTo`:

~~~javascript
const t = ISODate("2026-05-15T12:00:00Z")

db.policy_periods.find({
  entityId: "policy-1001",
  validFrom: { $lte: t },
  $or: [
    { validTo: { $gt: t } },
    { validTo: null }
  ]
})
~~~

**Quan trọng:** điều kiện `{validTo: null}` trong MongoDB cũng có thể khớp document **không có field `validTo`**. Nếu cần phân biệt rõ vắng field với BSON `null`, phải định nghĩa schema thống nhất và dùng điều kiện phù hợp, ví dụ kết hợp `$exists` hoặc `$type`. Quy tắc không cho phép hai khoảng hiệu lực chồng nhau của cùng thực thể thường cần kiểm tra ở service/transaction; **unique index đơn giản không tự bảo đảm “không giao nhau” cho các khoảng thời gian**.

## 4. Bản đồ những mô hình lưu lịch sử

~~~mermaid
flowchart TD
    R["Yêu cầu lưu lịch sử"] --> A{"Cần phiên bản đầy đủ?"}
    A -->|"Có"| B["Current + History / Document Versioning"]
    A -->|"Không, cần chuỗi hành động"| C["Append-only Event Log"]
    B --> D{"Số bản cũ có giới hạn nhỏ?"}
    D -->|"Có"| E["Bounded embedded history"]
    D -->|"Không"| F["History collection riêng"]
    C --> G{"Cần tái dựng nhanh?"}
    G -->|"Có"| H["Snapshot + events"]
    G -->|"Không"| I["Replay events"]
    F --> J["Hot / warm / cold archive"]
    H --> J
    I --> J
~~~

| Mô hình | Ưu điểm | Giới hạn cần chú ý | Nhu cầu phù hợp |
|---|---|---|---|
| **Embedded history có giới hạn** | Đọc current + một vài bản cũ bằng một document | Document tăng dần, giới hạn 16 MiB, write contention | Giữ 3–10 giá trị gần nhất với kích thước nhỏ, được kiểm soát |
| **Current + History collection** | Current gọn, lịch sử truy vấn độc lập, dễ index/retention | Cần bảo đảm current và history cập nhật nhất quán | Hồ sơ, hợp đồng, cấu hình, bảng giá |
| **Append-only events** | Diễn tả hành động nghiệp vụ; có thể tái dựng trạng thái | Phải định nghĩa event schema, thứ tự, idempotency và replay | Ledger, workflow, audit theo event |
| **Snapshots + events** | Giảm chi phí replay từ đầu | Cần giữ tương quan checkpoint với event sequence | Event stream dài, cần tái dựng nhanh |
| **Temporal intervals** | Query dữ liệu có hiệu lực tại thời điểm | Khó xử lý khoảng chồng, sửa hồi tố và hai trục thời gian | Giá theo kỳ, điều khoản có hiệu lực, quyền lợi |
| **Hot/warm/cold archive** | Chi phí lưu dài hạn thấp hơn, current query gọn | Cần catalog, pipeline chuyển dữ liệu, cơ chế tìm/restore | Dữ liệu nhiều năm, ít được đọc |

Các mô hình có thể kết hợp: ví dụ một thực thể có document current, history snapshot theo revision, event audit cho thao tác nghiệp vụ và lịch lưu trữ chuyển những history đã cũ sang archive.

## 5. Mô hình A — Embedded history với giới hạn rõ ràng

Với đối tượng nhỏ, cần vài giá trị gần nhất khi hiển thị hồ sơ, có thể nhúng history trong cùng document:

~~~javascript
{
  _id: "member-001",
  displayName: "Nguyễn Lan",
  phone: "0900000000",
  phoneHistory: [
    {
      value: "0911111111",
      changedAt: ISODate("2026-01-05T09:00:00Z")
    },
    {
      value: "0922222222",
      changedAt: ISODate("2025-12-01T10:00:00Z")
    }
  ]
}
~~~

Nếu quy định chỉ giữ ba số điện thoại gần nhất, một update trên document có thể thêm phần tử mới rồi cắt mảng:

~~~javascript
db.members.updateOne(
  { _id: "member-001" },
  {
    $set: { phone: "0933333333" },
    $push: {
      phoneHistory: {
        $each: [{
          value: "0900000000",
          changedAt: new Date()
        }],
        $position: 0,
        $slice: 3
      }
    }
  }
)
~~~

Ở đây ví dụ giả định số cũ hiện tại là `0900000000` và được truyền vào update. **Trong ứng dụng thực, không nên đọc giá trị cũ rồi ghi mù** khi có nhiều request đồng thời. Cần filter theo revision/giá trị kỳ vọng hoặc dùng update pipeline/transaction phù hợp, để dữ liệu lịch sử phản ánh chính xác lần chuyển trạng thái.

### Vì sao phải giới hạn mảng?

Mỗi BSON document có giới hạn kích thước **16 MiB**. Một mảng lịch sử tăng liên tục:

- Làm document ngày càng lớn.
- Tăng chi phí truyền/đọc document khi chỉ muốn thông tin hiện tại.
- Tạo áp lực cập nhật cùng một document nóng.
- Khó phân trang và có thể chạm giới hạn document.
- Buộc phải mất dữ liệu cũ nếu sau đó mới thêm `$slice`.

**Quy tắc:** chỉ dùng embedded history khi giới hạn số phần tử và kích thước được xác định bằng yêu cầu nghiệp vụ. Với lịch sử cần lưu vô hạn hoặc hàng triệu phiên bản, nên chuyển sang collection riêng.

## 6. Mô hình B — Current document và history collection

Đây là mẫu phổ biến khi **đọc hiện tại thường xuyên, lịch sử ít hơn nhưng cần đầy đủ**.

~~~mermaid
flowchart LR
    API["API đọc hiện tại"] --> Current["policies: mỗi hợp đồng một document current"]
    Current -->|"mỗi thay đổi có kiểm soát"| History["policy_history: nhiều revision cũ"]
    Auditor["API kiểm toán / tra cứu quá khứ"] --> History
    Auditor --> Current
~~~

### 6.1. Thiết kế collection current

~~~javascript
use document_history_lab

db.policies.insertOne({
  _id: "policy-1001",
  revision: 1,
  schemaVersion: 1,
  customerId: "customer-008",
  terms: {
    premium: NumberDecimal("1200000.00"),
    currency: "VND",
    coverage: "BASIC"
  },
  status: "ACTIVE",
  createdAt: ISODate("2026-04-01T09:00:00Z"),
  updatedAt: ISODate("2026-04-01T09:00:00Z")
})
~~~

Ý nghĩa:

- `_id` giữ định danh ổn định xuyên suốt vòng đời hợp đồng.
- `revision` là revision nghiệp vụ của trạng thái hiện tại.
- `schemaVersion` cho biết code phải đọc cấu trúc nào.
- `terms` chứa dữ liệu nghiệp vụ có thể thay đổi theo revision.
- `createdAt` là lúc tạo thực thể; `updatedAt` là lúc cập nhật trạng thái, không tự thay thế audit log.

### 6.2. Thiết kế collection lịch sử

~~~javascript
db.policy_history.createIndex(
  { entityId: 1, revision: 1 },
  { unique: true, name: "uq_policy_revision" }
)

db.policy_history.createIndex(
  { entityId: 1, capturedAt: -1 }
)
~~~

Một document history lưu **snapshot trước khi bị thay thế**:

~~~javascript
{
  _id: ObjectId("65f000000000000000000001"),
  entityId: "policy-1001",
  revision: 1,
  schemaVersion: 1,
  snapshot: {
    customerId: "customer-008",
    terms: {
      premium: NumberDecimal("1200000.00"),
      currency: "VND",
      coverage: "BASIC"
    },
    status: "ACTIVE",
    createdAt: ISODate("2026-04-01T09:00:00Z"),
    updatedAt: ISODate("2026-04-01T09:00:00Z")
  },
  capturedAt: ISODate("2026-04-15T09:00:00Z"),
  actorId: "staff-016",
  operation: "CHANGE_PREMIUM",
  reason: "Điều chỉnh điều khoản",
  requestId: "req-change-492"
}
~~~

Document này minh họa **hình dạng dữ liệu**, không phải kết quả tự phát sinh khi cập nhật. MongoDB không tự tạo collection history cho mọi `updateOne`. Ứng dụng hoặc quy trình ghi phải chủ động lưu. Trong ví dụ, revision 1 được lưu khi chuyển current sang revision 2; current giữ phiên bản mới nhất.

### 6.3. Tại sao nên lưu snapshot cũ thay vì chỉ lưu field thay đổi?

Snapshot đầy đủ cho phép đọc trực tiếp một revision mà không phải phát lại toàn bộ các thay đổi trước đó. Đổi lại, nó làm tăng dung lượng lịch sử, nhất là với document lớn. Nếu thực thể có nhiều field không đổi và tốc độ chỉnh sửa rất cao, có thể lưu delta/event hoặc chụp snapshot định kỳ; nhưng việc tái dựng khi đó phức tạp hơn.

Một snapshot hữu ích cần bao gồm tất cả field cần thiết cho chức năng “xem lại trạng thái”, **không nhất thiết chứa mọi field kỹ thuật hoặc dữ liệu bí mật**. Quy tắc về dữ liệu cá nhân, mã hóa và retention phải được áp dụng riêng.

### 6.4. Tham chiếu bằng ID, không nhúng vô hạn lịch sử

Trong current có thể thêm metadata như `lastChangedBy` và `revision`, nhưng không nhúng toàn bộ history vào mảng. History document gắn với `entityId`. Cách này giúp:

- Query current theo `_id` đơn giản.
- Lịch sử phân trang qua index riêng.
- Đổi retention/archiving của history mà không ảnh hưởng collection current.
- Quản lý access control khác nhau cho dữ liệu đang phục vụ người dùng và audit.

## 7. Ghi current và history nhất quán khi nhiều request đồng thời

Nếu chỉ thực hiện:

~~~text
1. Đọc current revision 1
2. Ghi history revision 1
3. Cập nhật current thành revision 2
~~~

thì lỗi giữa bước 2 và 3 có thể làm lịch sử có thêm bản ghi trong khi trạng thái chưa đổi, hoặc nếu đảo thứ tự thì current thay đổi mà history chưa được ghi. Hai request đồng thời còn có thể đọc cùng revision rồi ghi đè nhau.

### 7.1. Optimistic concurrency bằng revision

Một cập nhật có điều kiện:

~~~javascript
const result = db.policies.updateOne(
  { _id: "policy-1001", revision: 1 },
  {
    $set: {
      "terms.premium": NumberDecimal("1500000.00"),
      updatedAt: new Date()
    },
    $inc: { revision: 1 }
  }
)

printjson({
  matchedCount: result.matchedCount,
  modifiedCount: result.modifiedCount
})
~~~

Nếu request khác đã chuyển revision từ 1 sang 2 trước đó, filter không khớp và `matchedCount` bằng 0. Ứng dụng cần trả lỗi conflict hoặc đọc lại trạng thái hiện tại, **không tự cập nhật với revision mới nếu chưa giải quyết xung đột nghiệp vụ**.

Ví dụ này chỉ bảo vệ thao tác ghi current; **nó chưa tự ghi history**.

### 7.2. Transaction nhiều document

Khi current và history thuộc hai collection, có thể cập nhật chúng trong **một transaction** trên MongoDB deployment hỗ trợ transaction. Ví dụ thao tác dưới đây giả định current `policy-1001` đang ở revision 1 như lúc khởi tạo, và không chạy lại sau khi đã thành công.

~~~javascript
use document_history_lab

const session = db.getMongo().startSession()

try {
  await session.withTransaction(async () => {
    const txDb = session.getDatabase("document_history_lab")
    const current = await txDb.policies.findOne({
      _id: "policy-1001"
    })

    if (!current) {
      throw new Error("POLICY_NOT_FOUND")
    }
    if (current.revision !== 1) {
      throw new Error("REVISION_CONFLICT")
    }

    const changedAt = new Date()
    const update = await txDb.policies.updateOne(
      { _id: current._id, revision: current.revision },
      {
        $set: {
          "terms.premium": NumberDecimal("1500000.00"),
          updatedAt: changedAt
        },
        $inc: { revision: 1 }
      }
    )

    if (update.matchedCount !== 1) {
      throw new Error("REVISION_CONFLICT")
    }

    await txDb.policy_history.insertOne({
      entityId: current._id,
      revision: current.revision,
      schemaVersion: current.schemaVersion,
      snapshot: {
        customerId: current.customerId,
        terms: current.terms,
        status: current.status,
        createdAt: current.createdAt,
        updatedAt: current.updatedAt
      },
      capturedAt: changedAt,
      actorId: "staff-016",
      operation: "CHANGE_PREMIUM",
      reason: "Điều chỉnh điều khoản",
      requestId: "req-change-492"
    })
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })
} finally {
  await session.endSession()
}
~~~

**Điều kiện thực thi:** Transaction nhiều document cần replica set hoặc sharded cluster hỗ trợ transaction; không áp dụng ví dụ này nguyên dạng cho standalone thông thường. Trong transaction, logic phải xử lý transient error, write conflict và trạng thái commit không chắc chắn theo API của driver. Helper transaction có thể chạy lại callback trong một số tình huống: callback phải tránh side effect bên ngoài MongoDB như gửi email hoặc trừ tiền trực tiếp.

**Điều kiện đúng của ví dụ:** sau transaction thành công, current ở revision 2 và history có snapshot revision 1. Nếu một thao tác trong transaction thất bại và transaction bị abort, cả hai thay đổi sẽ không commit.

### 7.3. Khi hai người cùng sửa một hợp đồng

~~~text
Trạng thái ban đầu: revision = 3

User A đọc revision 3
User B đọc revision 3

User A: UPDATE {_id, revision: 3} -> revision 4  [thành công]
User B: UPDATE {_id, revision: 3} -> không khớp [conflict]
~~~

Không có revision guard, request B có thể ghi đè thay đổi của A theo kiểu **lost update**. Revision guard cung cấp tín hiệu xung đột; ứng dụng vẫn phải quyết định merge, yêu cầu nhập lại hoặc giải thích lỗi cho người dùng.

### 7.4. Request ID và idempotency

Revision guard xử lý cạnh tranh; **idempotency** xử lý một request bị gửi lại do timeout/retry. Hai vấn đề khác nhau. Ví dụ client gửi `requestId: "req-change-492"`, server commit thành công nhưng client mất kết nối trước khi nhận response. Nếu gửi lại, ứng dụng cần nhận ra request đã được xử lý và trả kết quả tương ứng, thay vì tạo thay đổi mới.

Có thể dùng collection lưu idempotency key với unique index theo phạm vi nghiệp vụ, hoặc bảo đảm operation ID duy nhất trong luồng event/history. Thiết kế phải rõ trạng thái đang xử lý, đã hoàn tất và lỗi có thể retry. Không chỉ dựa vào timestamp hoặc giả định client sẽ không gửi trùng.

## 8. Truy vấn current và phiên bản cũ

### 8.1. Đọc trạng thái hiện tại

~~~javascript
db.policies.findOne({ _id: "policy-1001" })
~~~

Một document current duy nhất giúp API nghiệp vụ thông thường tránh phải quét toàn bộ các version.

### 8.2. Liệt kê lịch sử theo revision

~~~javascript
db.policy_history.find(
  { entityId: "policy-1001" },
  {
    entityId: 1,
    revision: 1,
    capturedAt: 1,
    operation: 1,
    actorId: 1
  }
).sort({ revision: -1 }).limit(20)
~~~

Index `{entityId: 1, revision: 1}` giúp tìm chuỗi revision theo thực thể; thứ tự sắp xếp của index có thể được sử dụng theo những chiều tương ứng trong trường hợp phù hợp. Cần kiểm chứng bằng `explain("executionStats")` với dữ liệu đại diện.

### 8.3. Xem một revision cụ thể

~~~javascript
const revisionNumber = 1

const historical = db.policy_history.findOne({
  entityId: "policy-1001",
  revision: revisionNumber
})

printjson(historical && historical.snapshot)
~~~

Theo thiết kế “history chứa các bản cũ”, revision hiện tại **không nhất thiết nằm trong `policy_history`**. API “get revision” phải kiểm tra current trước hoặc định tuyến tới history khi yêu cầu revision thấp hơn.

### 8.4. Phân trang dài theo revision

Tránh sử dụng `skip(1000000)` làm chiến lược chính cho một stream rất dài. Dùng keyset:

~~~javascript
const lastSeenRevision = 120

db.policy_history.find({
  entityId: "policy-1001",
  revision: { $lt: lastSeenRevision }
}).sort({ revision: -1 }).limit(20)
~~~

Revision là số tăng đơn điệu **trong phạm vi một thực thể**; không mặc định là thứ tự toàn hệ thống. Nếu phân trang lịch sử của nhiều thực thể, cần một khóa sắp xếp ổn định có phần tử phân giải trường hợp trùng thời gian, ví dụ `recordedAt + _id`, cùng index tương ứng.

## 9. Mô hình C — Append-only event log và event sourcing

Không phải lúc nào câu hỏi cũng là “document từng có giá trị gì?”. Có hệ thống cần biết **điều gì đã xảy ra**:

~~~javascript
{
  _id: "evt-policy-1001-0002",
  aggregateId: "policy-1001",
  sequence: 2,
  type: "PolicyPremiumChanged",
  eventVersion: 1,
  occurredAt: ISODate("2026-04-15T08:58:00Z"),
  recordedAt: ISODate("2026-04-15T09:00:00Z"),
  actorId: "staff-016",
  requestId: "req-change-492",
  payload: {
    previousPremium: NumberDecimal("1200000.00"),
    newPremium: NumberDecimal("1500000.00"),
    currency: "VND"
  }
}
~~~

Event nhấn mạnh hành động nghiệp vụ `PolicyPremiumChanged`, còn snapshot nhấn mạnh trạng thái tại một revision. Event log có thể phục vụ audit; **event sourcing** đi xa hơn: trạng thái current được tái dựng từ chuỗi event theo luật áp dụng sự kiện.

~~~mermaid
flowchart LR
    Command["Command thay đổi"] --> Validation["Kiểm tra nghiệp vụ / concurrency"]
    Validation --> Events["Append event có thứ tự"]
    Events --> Projector["Projector / Reducer"]
    Projector --> Current["Current state projection"]
    Events --> Replay["Replay lịch sử"]
    Replay --> Restored["Trạng thái tại sequence N"]
~~~

### 9.1. Cấu trúc và index cần thiết

~~~javascript
use document_history_lab

db.policy_events.createIndex(
  { aggregateId: 1, sequence: 1 },
  { unique: true, name: "uq_aggregate_sequence" }
)

db.policy_events.createIndex(
  { requestId: 1 },
  { unique: true, name: "uq_event_request_id" }
)
~~~

Index `requestId` unique toàn collection chỉ đúng khi mỗi request sinh **tối đa một event trong collection**. Nếu một request có nhiều event, cần mô hình khóa như `requestId + eventOrdinal`, hoặc một ledger idempotency riêng. Việc chọn index phải xuất phát từ ranh giới idempotency thật.

### 9.2. Replay cần hơn một danh sách event

Để tái dựng tin cậy:

- Event có **thứ tự xác định** trong phạm vi aggregate, ví dụ `sequence`.
- Event đã được ghi có hợp đồng nội dung rõ ràng và không bị chỉnh sửa tùy tiện.
- Reducer xử lý đúng mọi `eventVersion` đã phát hành hoặc dùng lớp chuyển đổi tương thích.
- Event phải được áp dụng đúng một lần ở tầng projection theo ý nghĩa nghiệp vụ; xử lý duplicate/retry.
- Thay đổi logic reducer theo thời gian phải được quản lý; phát lại dữ liệu cũ bằng logic mới có thể cho kết quả khác nếu không kiểm soát.
- Các sự kiện làm phát sinh side effect bên ngoài cần cơ chế giao nhận phù hợp, ví dụ outbox và idempotent consumer.

### 9.3. Event sourcing không miễn phí

Với 100.000 event trên một thực thể, replay từ event đầu tiên mỗi lần đọc là quá tốn kém. Có thể tạo **snapshot sau mỗi N event**:

~~~javascript
{
  _id: "policy-1001-snapshot-500",
  aggregateId: "policy-1001",
  lastAppliedSequence: 500,
  schemaVersion: 2,
  state: {
    status: "ACTIVE",
    premium: NumberDecimal("1500000.00")
  },
  createdAt: ISODate("2026-06-01T00:00:00Z")
}
~~~

Tái dựng trạng thái bằng cách lấy snapshot gần nhất **không vượt quá sequence mục tiêu**, rồi áp dụng event sau `lastAppliedSequence`. Snapshot cần được kiểm chứng tương ứng với chuỗi event gốc; không được bỏ đi event cũ chỉ vì đã có snapshot nếu chính sách audit hoặc khôi phục vẫn yêu cầu chúng.

### 9.4. Phân biệt event log với Change Streams

MongoDB **Change Streams** cho ứng dụng theo dõi thay đổi trên collection/database/cluster ở topology hỗ trợ. Đây là công cụ thích hợp để kích hoạt xử lý phản ứng, đồng bộ projection hoặc một số pipeline; nó **không mặc nhiên là kho audit vĩnh viễn**:

- Change Streams dựa trên thông tin thay đổi có khoảng thời gian có thể resume; retention liên quan oplog/khả năng của deployment.
- Consumer cần lưu resume token, có retry và chịu được việc nhận/áp dụng lại một thay đổi.
- Nếu consumer ngừng quá lâu, resume token có thể không còn hợp lệ.
- Pre/post-images là tính năng cần bật/cấu hình theo hỗ trợ của phiên bản; không mặc định có mọi giá trị cũ.
- Event kỹ thuật “document được update” không luôn chứa ngữ nghĩa nghiệp vụ “vì sao điều chỉnh phí”.

Nếu cần lịch sử kiểm toán lâu dài, **chủ động thiết kế kho lưu sự kiện/history bền vững** và pipeline ghi chính xác, không dùng oplog/change stream làm nguồn lưu lịch sử duy nhất.

## 10. Mô hình D — Dữ liệu có hiệu lực theo thời gian

Một số dữ liệu cần truy vấn “giá hợp lệ tại ngày D” hoặc “chính sách áp dụng khi giao dịch xảy ra”, dù giá mới đã được công bố.

Ví dụ collection `price_periods`:

~~~javascript
db.price_periods.insertMany([
  {
    productId: "product-001",
    price: NumberDecimal("100000.00"),
    currency: "VND",
    validFrom: ISODate("2026-01-01T00:00:00Z"),
    validTo: ISODate("2026-04-01T00:00:00Z"),
    recordedAt: ISODate("2025-12-20T09:00:00Z"),
    revision: 1
  },
  {
    productId: "product-001",
    price: NumberDecimal("120000.00"),
    currency: "VND",
    validFrom: ISODate("2026-04-01T00:00:00Z"),
    validTo: null,
    recordedAt: ISODate("2026-03-15T09:00:00Z"),
    revision: 2
  }
])
~~~

Query tìm giá có hiệu lực ngày 15/05:

~~~javascript
const t = ISODate("2026-05-15T00:00:00Z")

db.price_periods.find({
  productId: "product-001",
  validFrom: { $lte: t },
  $or: [
    { validTo: { $gt: t } },
    { validTo: null }
  ]
})
~~~

Index tham khảo:

~~~javascript
db.price_periods.createIndex({
  productId: 1,
  validFrom: -1
})
~~~

Index này có thể hỗ trợ tìm các khoảng bắt đầu trước thời điểm truy vấn; vẫn phải đo xem query kiểm tra `validTo` đọc bao nhiêu candidate. **Không có một index chung bảo đảm tối ưu mọi bài toán interval overlap**.

### 10.1. Sửa hồi tố làm mô hình phức tạp hơn

Giả sử tháng 6 mới phát hiện mức giá áp dụng từ tháng 4 bị nhập sai. Nếu sửa trực tiếp giá trong period tháng 4, hệ thống không còn chứng cứ về **điều mà hệ thống đã tin là đúng trước khi sửa**.

Có hai nhu cầu:

1. **As-effective:** Giá có hiệu lực nghiệp vụ tại ngày 15/04 sau khi đã áp dụng mọi điều chỉnh?
2. **As-known:** Vào ngày 20/04, hệ thống thực tế đang ghi nhận giá nào?

Để trả lời cả hai, có thể cần bitemporal records với khoảng hiệu lực và khoảng ghi nhận, hoặc event correction gắn với các revision tương ứng. Đây là thiết kế nâng cao cần định nghĩa rõ câu truy vấn trước khi áp dụng.

### 10.2. Lưu snapshot giao dịch không phụ thuộc giá hiện tại

Trong đơn hàng, nên lưu giá chốt:

~~~javascript
{
  _id: "order-2026-001",
  createdAt: ISODate("2026-04-15T09:00:00Z"),
  lines: [
    {
      productId: "product-001",
      qty: 2,
      unitPrice: NumberDecimal("120000.00"),
      currency: "VND"
    }
  ],
  total: NumberDecimal("240000.00")
}
~~~

Nếu product catalog sau đó thay giá, **`unitPrice` của đơn đã xác nhận vẫn giữ snapshot lịch sử**. Cần định nghĩa những thay đổi được phép với đơn đã chốt; nếu phải điều chỉnh, có thể dùng revision, phiếu điều chỉnh hoặc event thay vì ghi đè không lưu dấu vết.

## 11. Phiên bản schema để đọc dữ liệu qua nhiều năm

Giả sử năm đầu tiên hệ thống lưu:

~~~javascript
// schemaVersion 1
{
  _id: "profile-001",
  schemaVersion: 1,
  fullName: "Nguyễn Lan",
  phone: "0900000000"
}
~~~

Về sau, ứng dụng chuyển sang:

~~~javascript
// schemaVersion 2
{
  _id: "profile-001",
  schemaVersion: 2,
  person: {
    displayName: "Nguyễn Lan"
  },
  contacts: {
    primaryPhone: "0900000000"
  }
}
~~~

Nếu history/archive chứa cả hai định dạng, code chỉ đọc v2 sẽ không hiểu snapshot v1. Có ba chiến lược cơ bản:

| Chiến lược | Cách hoạt động | Điểm cần cân nhắc |
|---|---|---|
| **Eager migration** | Backfill document cũ sang cấu trúc mới | Tốn I/O, rủi ro thay đổi lịch sử và khả năng rollback |
| **Lazy migration** | Khi đọc/ghi document cũ thì chuyển sang dạng mới theo quy tắc | Thời gian tồn tại nhiều schema kéo dài, phải xử lý cạnh tranh |
| **Read-time upcasting** | Giữ dữ liệu gốc nhưng khi đọc ánh xạ sang mô hình ứng dụng hiện tại | Giữ byte gốc tốt hơn; phải duy trì các converter theo phiên bản |

Ví dụ upcaster chỉ phục vụ tầng đọc, không tự ghi lại document:

~~~javascript
function toProfileView(doc) {
  if (doc.schemaVersion === 1) {
    return {
      id: doc._id,
      displayName: doc.fullName,
      phone: doc.phone
    }
  }

  if (doc.schemaVersion === 2) {
    return {
      id: doc._id,
      displayName: doc.person.displayName,
      phone: doc.contacts.primaryPhone
    }
  }

  throw new Error("UNSUPPORTED_SCHEMA_VERSION")
}
~~~

**Không mặc định cập nhật history cũ lên schema mới bằng ghi đè.** Nếu history được coi là chứng cứ nguyên bản, giữ payload gốc, schemaVersion và thông tin chuyển đổi; ứng dụng có thể hiển thị view đã chuẩn hóa mà không làm mất nguồn. Nếu quy định yêu cầu xóa/ẩn dữ liệu cá nhân, chính sách đó vẫn có thể áp dụng cho cả bản lưu lịch sử.

### 11.1. Schema evolution cho archive dài hạn

Một archive sau 10 năm cần:

- Biết encoding và schema/format version của từng lô dữ liệu.
- Có mô tả field, timezone, đơn vị tiền/tính toán và quy tắc decimal.
- Giữ công cụ hoặc tài liệu để đọc lại BSON/JSON/Parquet/format đã xuất.
- Có checksum/integrity và nguồn gốc (provenance).
- Có kế hoạch xử lý phiên bản phần mềm không còn hỗ trợ.
- Có cách kiểm chứng đọc/restore thực tế, không chỉ dựa vào tên file archive.

Giữ file mà mất schema hoặc công cụ giải mã cũng có thể khiến dữ liệu không còn giá trị sử dụng.

## 12. Dữ liệu tăng rất dài: không lưu toàn bộ vào một document

Một hệ thống cảm biến có thể ghi hàng nghìn measurement mỗi giờ. Mô hình sau dễ dẫn tới vấn đề:

~~~javascript
// Chỉ để minh họa anti-pattern.
{
  _id: "sensor-001",
  readings: [
    { at: ISODate("2026-01-01T00:00:00Z"), value: 23.1 },
    { at: ISODate("2026-01-01T00:01:00Z"), value: 23.2 }
    // ... mảng tăng không giới hạn theo năm tháng
  ]
}
~~~

Document sẽ tăng tới giới hạn BSON 16 MiB và mỗi lần đọc/ghi có thể phải xử lý cấu trúc lớn. Những mô hình thay thế:

### 12.1. Một event/measurement một document

~~~javascript
{
  sensorId: "sensor-001",
  measuredAt: ISODate("2026-01-01T00:00:00Z"),
  temperatureC: 23.1
}
~~~

Ưu điểm là truy vấn theo khoảng, retention theo thời gian và sharding/archiving linh hoạt hơn. Đổi lại, số lượng document và index entry lớn.

### 12.2. Bucket pattern có giới hạn

Chia các reading theo ngày/giờ/thiết bị, nhưng phải có giới hạn rõ:

~~~javascript
{
  _id: "sensor-001:2026-01-01:00",
  sensorId: "sensor-001",
  bucketStart: ISODate("2026-01-01T00:00:00Z"),
  bucketEnd: ISODate("2026-01-01T01:00:00Z"),
  count: 2,
  readings: [
    { at: ISODate("2026-01-01T00:00:00Z"), value: 23.1 },
    { at: ISODate("2026-01-01T00:01:00Z"), value: 23.2 }
  ]
}
~~~

Bucket giảm metadata/index entry so với document riêng lẻ trong một số workload, nhưng cần bảo đảm số phần tử/kích thước giới hạn, xử lý cạnh tranh ghi vào bucket và truy vấn theo khoảng. Bucket quá lớn vẫn chạm 16 MiB.

### 12.3. Time-series collection

Với dữ liệu measurements có timestamp và metadata nguồn, MongoDB có **time-series collection**. Ví dụ:

~~~javascript
use document_history_lab

db.createCollection("sensor_measurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "sensor",
    granularity: "minutes"
  }
})

db.sensor_measurements.insertOne({
  measuredAt: ISODate("2026-01-01T00:00:00Z"),
  sensor: {
    sensorId: "sensor-001",
    location: "warehouse-A"
  },
  temperatureC: 23.1
})
~~~

Time-series collection được thiết kế cho workload chuỗi thời gian và có cơ chế tổ chức/lưu trữ nội bộ riêng. Khả năng update/delete, index, sharding và retention có thể khác collection thường và thay đổi theo phiên bản. **Không dùng time-series chỉ vì document có field ngày giờ**; hãy đối chiếu workload và tính năng cần thiết.

## 13. Lưu trữ lâu dài: hot, warm và cold

Mọi dữ liệu nhiều năm không nhất thiết phải nằm trong cùng collection phục vụ request hàng ngày. Có thể phân tầng:

~~~mermaid
flowchart LR
    Ingest["Nguồn dữ liệu / API"] --> Hot["HOT: current / lịch sử gần"]
    Hot -->|"Retention / archive job"| Warm["WARM: history ít truy cập"]
    Warm -->|"Archive job đã kiểm chứng"| Cold["COLD: object storage / archival system"]
    Catalog["Archive catalog / manifest"] --> Cold
    Query["Truy vấn lịch sử"] --> Hot
    Query --> Warm
    Query --> Restore["Dịch vụ tìm và phục hồi archive"]
    Restore --> Cold
~~~

| Tầng | Nội dung | Đặc điểm truy cập | Quyết định thiết kế |
|---|---|---|---|
| **Hot** | Current state, history mới | Query trực tiếp, yêu cầu latency thấp | Index theo API, dung lượng working set, HA |
| **Warm** | Revision/event cũ nhưng vẫn cần truy vấn | Truy vấn ít hơn, có thể chịu latency cao hơn | Collection/cluster riêng, index tối giản, batch |
| **Cold** | Dữ liệu hiếm khi truy cập, cần giữ nhiều năm | Tìm theo manifest rồi đọc/restore | Format, checksum, encryption, quyền, chi phí retrieval |

Không nên cố định mốc 30/90/365 ngày cho mọi hệ thống. Chính sách cần dựa vào nhu cầu thực tế và nghĩa vụ lưu giữ:

- Hồ sơ thanh toán/thuế/hợp đồng có thể cần giữ nhiều năm.
- Telemetry có thể chỉ cần chi tiết theo phút trong vài tuần, sau đó giữ aggregate.
- Một số dữ liệu cá nhân phải xóa theo chính sách hoặc yêu cầu hợp lệ.
- Dữ liệu đang điều tra tranh chấp có thể thuộc **legal hold**, tạm dừng việc xóa theo retention thông thường.

### 13.1. Metadata cho một lô archive

Ví dụ một manifest:

~~~javascript
{
  _id: "archive-policy-history-2025-q1",
  dataset: "policy_history",
  fromRecordedAt: ISODate("2025-01-01T00:00:00Z"),
  toRecordedAtExclusive: ISODate("2025-04-01T00:00:00Z"),
  objectUri: "archive://policies/2025/q1/history-v1",
  format: "BSON",
  formatVersion: 1,
  schemaVersions: [1, 2],
  documentCount: 258900,
  checksumAlgorithm: "SHA-256",
  checksum: "<checksum-of-archive>",
  exportedAt: ISODate("2026-04-01T00:00:00Z"),
  retentionUntil: ISODate("2033-04-01T00:00:00Z"),
  state: "VERIFIED"
}
~~~

`objectUri` là địa chỉ khái niệm, không phải một MongoDB API có thể tự đọc. Ứng dụng cần archive service hoặc quy trình export/restore riêng. Trường checksum cũng cần định nghĩa **được tính trên byte nào và thứ tự nào**; một chuỗi placeholder không chứng minh integrity.

### 13.2. Archive phải bảo toàn khả năng tìm kiếm

Nếu dữ liệu chỉ còn file theo ngày, làm thế nào tìm lịch sử của `policy-1001`?

Một thiết kế có thể dùng:

- Manifest theo phạm vi thời gian, tenant, collection hoặc partition.
- Index/catalog mapping `entityId` hoặc các key nghiệp vụ tới archive batch.
- Dịch vụ tra cứu quyết định dữ liệu đang ở hot/warm hay cold.
- Quy trình lấy file, giải mã, xác minh checksum và đọc theo format version.
- Cơ chế cấp quyền giống hoặc nghiêm ngặt hơn database hiện tại.

**Dữ liệu lưu được nhưng không tìm thấy hoặc không giải mã được là lưu trữ chưa hoàn chỉnh.**

## 14. Quy trình archive an toàn và có thể chạy lại

Không nên làm như sau:

~~~text
1. Xóa mọi document cũ khỏi MongoDB.
2. Sau đó mới thử xuất chúng ra file.
~~~

Nếu bước xuất thất bại, dữ liệu đã mất. Một pipeline an toàn hơn:

1. **Chọn cutoff:** ví dụ history có `capturedAt < T` và không bị legal hold; xác định timezone, điều kiện và snapshot phạm vi batch.
2. **Đánh dấu / ghi checkpoint công việc:** xác định batch ID và tập document mục tiêu bằng khóa ổn định, không dựa thuần vào offset.
3. **Xuất dữ liệu:** dùng format có version và kiểm soát thứ tự/metadata; truyền tới storage được cấp quyền.
4. **Xác minh:** đối chiếu record count, checksum, key range, schema version; thử truy xuất các mẫu đại diện từ archive.
5. **Công bố manifest:** chỉ đánh dấu `VERIFIED` khi file và metadata sẵn sàng, lưu thông tin vị trí.
6. **Cho phép xóa phía online:** sau khi kiểm tra retention, legal hold, bản sao và khả năng phục hồi; xóa theo batch giới hạn tải.
7. **Đọc lại và giám sát:** phát hiện document chưa chuyển, bị xuất trùng hoặc cần retry.

~~~mermaid
flowchart TD
    Select["Chọn batch và cutoff"] --> Export["Export sang archive"]
    Export --> Verify{"Checksum + count + readback hợp lệ?"}
    Verify -->|"Không"| Retry["Báo lỗi / retry có idempotency"]
    Retry --> Export
    Verify -->|"Có"| Manifest["Công bố manifest VERIFIED"]
    Manifest --> Policy{"Retention / legal hold cho phép xóa?"}
    Policy -->|"Không"| Keep["Giữ online hoặc dừng chờ"]
    Policy -->|"Có"| Delete["Xóa online theo batch"]
    Delete --> Audit["Readback, audit, metrics"]
~~~

### 14.1. Tính idempotent của archive job

Archive có thể được chạy lại sau timeout, restart hoặc failover. Cần:

- Batch ID ổn định để không tạo hai manifest khác nhau cho một dữ liệu.
- Khóa document xác định; cố định cutoff và cách chọn tập dữ liệu.
- Export/retry không làm biến đổi nội dung không kiểm soát.
- Chỉ xóa online sau khi archive được xác nhận đã đọc được.
- Ghi nhận những lỗi ở mức từng document và có cơ chế tiếp tục.

Với dữ liệu **đang còn thay đổi**, yêu cầu khó hơn. Có thể chỉ archive document đã đóng/bất biến, hoặc dùng trạng thái freeze, version/cutoff transaction và reconciliation để tránh bỏ sót update xảy ra trong lúc export.

### 14.2. Số đếm chưa đủ để chứng minh đúng

Nếu export 10.000 document nhưng bỏ sót một document và lặp lại một document khác, `documentCount` vẫn bằng 10.000. Nên kết hợp kiểm tra key set/unique IDs, checksum theo quy tắc ổn định, metadata schema và thử restore. Một bộ kiểm chứng càng có yêu cầu cao thì càng cần độc lập với job tạo archive.

## 15. TTL, retention và quy tắc xóa dữ liệu

MongoDB có **TTL index** để tự động xóa một số document sau một thời gian. Ví dụ collection log dùng thời điểm tạo:

~~~javascript
db.transient_events.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 60 * 60 * 24 * 30 }
)
~~~

Với document có `createdAt` thuộc BSON Date, cơ chế TTL có thể xóa chúng khi quá tuổi 30 ngày. Nhưng:

- TTL monitor chạy nền nên **không hứa xóa đúng một giây tại thời điểm đến hạn**.
- TTL là **xóa dữ liệu**, không phải export/archive.
- Nếu chưa có archive được kiểm chứng, bật TTL có thể phá hỏng yêu cầu giữ lâu dài.
- TTL không phải công cụ thích hợp cho mọi yêu cầu legal hold hoặc retention khác nhau theo từng document.
- TTL index và khả năng dùng partial filter có giới hạn cụ thể theo phiên bản, loại collection và schema.
- Với time-series collection, các option TTL/expiry có quy tắc riêng; phải kiểm tra phiên bản và loại collection.

### 15.1. Phân biệt thời hạn lưu, thời hạn tra cứu và thời hạn xóa

Ví dụ:

~~~text
Ngày phát sinh giao dịch:       2026-01-01
Tra cứu trực tuyến nhanh tới:  2027-01-01
Lưu archive tới:               2033-01-01
Đến hạn xóa/ẩn danh theo policy: sau khi hết nghĩa vụ giữ
~~~

Ở trường hợp này, không được đặt TTL một năm lên **bản duy nhất** của transaction nếu dữ liệu phải giữ đến năm 2033. Có thể chuyển dữ liệu ra warm/cold sau một năm, giữ manifest và chỉ xóa khi hết nghĩa vụ và không thuộc ngoại lệ hợp lệ.

### 15.2. Soft delete không có nghĩa đã xóa thực tế

~~~javascript
db.policies.updateOne(
  { _id: "policy-1001" },
  {
    $set: {
      deletedAt: new Date(),
      status: "DELETED"
    }
  }
)
~~~

Đây là **soft delete**: document vẫn tồn tại, có thể còn trong backup, history, logs và archive. Nếu cần thực hiện xóa dữ liệu cá nhân theo một yêu cầu hợp lệ, phải xác định phạm vi tất cả bản sao và chính sách lưu giữ, không coi `deletedAt` là bằng chứng đã xóa khỏi hệ thống.

## 16. Index cho truy vấn lịch sử dài hạn

Lịch sử có thể gấp hàng trăm lần kích thước current. Vì vậy không thể bê nguyên index của collection hiện tại sang history rồi coi là tối ưu.

| Query thường gặp | Index cần cân nhắc | Ghi chú |
|---|---|---|
| Xem các revision của một thực thể | `{entityId: 1, revision: -1}` | Phân trang theo revision; có thể unique |
| Xem lịch sử của một thực thể theo thời gian | `{entityId: 1, capturedAt: -1}` | Cần khóa phụ để sort ổn định nếu timestamp trùng |
| Tìm event của một aggregate | `{aggregateId: 1, sequence: 1}` | Bảo đảm sequence duy nhất cho một aggregate |
| Truy vấn log theo tenant và thời gian | `{tenantId: 1, recordedAt: -1}` | Quy mô lớn cần xét sharding/retention |
| Quét batch archive theo cutoff | Index hỗ trợ `capturedAt` và phạm vi partition | Chỉ tạo khi job thực sự cần, tránh gây write amplification |
| Tìm giá theo effective interval | Index bắt đầu từ business key và valid time | Query overlap cần đo thực tế |

### 16.1. Minh họa giải thích kế hoạch truy vấn

~~~javascript
db.policy_history.find({
  entityId: "policy-1001",
  revision: { $lt: 100 }
}).sort({ revision: -1 }).limit(20)
  .explain("executionStats")
~~~

Quan sát `winningPlan`, `totalKeysExamined`, `totalDocsExamined` và `nReturned`. Với collection nhỏ, MongoDB có thể chọn collection scan; không đánh giá hiệu quả index chỉ bằng vài document mẫu.

### 16.2. Tăng trưởng history và dung lượng index

Mỗi revision là một document mới; index trên history cũng tăng. Các quyết định cần tính:

- Tốc độ tạo revision/event theo giây và theo năm.
- Kích thước snapshot trung bình và mức trùng lặp dữ liệu.
- Compressor và footprint trên disk; CPU giải nén.
- Số index cần duy trì khi ghi liên tục.
- Kích thước RAM/cache, working set của dữ liệu nóng.
- Retention/archival, backup, replica set và khả năng restore.

Nếu history chỉ dùng cho kiểm toán hiếm gặp, có thể tránh nhiều index phục vụ bộ lọc tùy ý để giảm chi phí ghi và lưu trữ. Đổi lại, cần cung cấp đường tra cứu xác định, ví dụ theo `entityId` hoặc khoảng thời gian đã phân vùng.

## 17. Tính toàn vẹn, audit và bảo mật

Mô hình history dùng cho kiểm toán phải quan tâm **tính chính xác và khả năng truy vết**.

### 17.1. Những field audit thường cần

| Field | Ý nghĩa | Lưu ý |
|---|---|---|
| `entityId` | Thực thể bị thay đổi | ID ổn định qua mọi revision |
| `revision` / `sequence` | Thứ tự thay đổi | Phải có quy tắc tạo và uniqueness |
| `actorId` | Ai gây ra thao tác | Có thể là service account/system job |
| `operation` | Loại thay đổi nghiệp vụ | Dùng tên có ý nghĩa, không chỉ “update” |
| `reason` | Lý do thay đổi | Có thể bắt buộc cho nghiệp vụ nhạy cảm |
| `recordedAt` | Thời gian hệ thống ghi nhận | Đồng bộ đồng hồ, dùng BSON Date |
| `requestId` / `correlationId` | Liên kết log và request | Hỗ trợ idempotency/điều tra |
| `schemaVersion` / `eventVersion` | Cách diễn giải payload | Cần thiết để đọc lịch sử cũ |
| `oldValue` / `newValue` hoặc `snapshot` | Nội dung thay đổi | Chỉ lưu dữ liệu thật sự cần, hạn chế thông tin nhạy cảm |

### 17.2. Append-only cần được bảo vệ bằng quyền

“Append-only” là **quy ước thiết kế/luồng ứng dụng**; collection MongoDB thường vẫn có thể bị sửa hoặc drop bởi tài khoản có đủ quyền. Nếu cần audit chống sửa đổi:

- Tách quyền ghi của ứng dụng khỏi quyền quản trị.
- Giới hạn thao tác update/delete trên history ở tầng quyền và service.
- Gửi bản sao audit sang hệ thống được bảo vệ độc lập khi yêu cầu bảo đảm cao.
- Dùng checksum/chữ ký hoặc cơ chế immutable/WORM archive theo tiêu chuẩn tổ chức nếu cần.
- Có log các thao tác truy cập, thay đổi quyền, export và xóa dữ liệu.

Không xem unique index hoặc trường `immutable: true` ở cấp ứng dụng là cam kết bảo mật chống lại mọi quản trị viên.

### 17.3. Lịch sử có thể chứa dữ liệu nhạy cảm đã bị sửa/xóa

Nếu trước đây người dùng nhập sai số điện thoại rồi cập nhật, cả số cũ và mới có thể còn trong history. Chính sách cần xác định:

- Ai được phép xem giá trị lịch sử?
- Khi nào được che/mask hoặc xóa một field khỏi lịch sử?
- Dữ liệu nào phải được mã hóa và quản lý khóa?
- Có ngoại lệ lưu giữ hợp pháp hoặc legal hold không?
- Bản backup/archive có tuân thủ cùng yêu cầu retention và access control không?

Mục tiêu audit không tự cho phép lưu mọi dữ liệu cá nhân vô thời hạn.

## 18. Lịch sử không phải backup và backup không thay thế history

Hai mục đích khác nhau:

| Thành phần | Trả lời câu hỏi nào? | Điểm giới hạn |
|---|---|---|
| History collection | “Đối tượng này đã thay đổi thế nào?” | Có thể bị xóa nhầm/corrupt cùng database |
| Audit event stream | “Ai tạo sự kiện gì, ở thứ tự nào?” | Phải bảo vệ integrity và xử lý event schema |
| Replica set | “Hệ thống tiếp tục phục vụ khi một node gặp lỗi?” | Sao chép cả thao tác xóa/sai dữ liệu |
| Backup | “Có thể khôi phục dữ liệu sau sự cố hoặc mất mát?” | Phụ thuộc RPO/RTO, phạm vi và thử restore |
| Archive | “Có thể giữ và tìm dữ liệu ít dùng nhiều năm?” | Phải có manifest, format, quyền, checksum, khả năng đọc |

Một history collection lưu cùng cluster với current vẫn có thể mất cùng lúc do cấu hình sai hoặc thao tác xóa database. Ngược lại, backup theo ngày có thể khôi phục toàn database nhưng không thích hợp cho câu hỏi “Ai đã sửa giá sản phẩm lúc 09:12?”. Hai công cụ nên bổ trợ nhau.

### 18.1. RPO và RTO của hệ thống lịch sử

- **RPO:** mức mất dữ liệu chấp nhận được nếu có sự cố; với audit quan trọng có thể cần rất thấp.
- **RTO:** thời gian tối đa để khôi phục hệ thống/khả năng tra cứu.

Cần kiểm thử restore với **cả current, history, index và metadata phiên bản**, không chỉ collection current. Nếu archive nằm ở hệ thống khác, phải kiểm tra khả năng tải, giải mã và đối chiếu checksum.

## 19. Migration và tương thích khi ứng dụng thay đổi

Một thiết kế tốt phải vận hành qua nhiều lần phát hành phần mềm.

### 19.1. Phát hành theo hướng expand–migrate–contract

Ví dụ đổi field `premium` thành `terms.premium`:

1. **Expand:** phiên bản ứng dụng mới có thể đọc cả schema cũ/mới, ghi theo định dạng đích với quy tắc rõ ràng.
2. **Migrate:** backfill current theo batch, ghi checkpoint và kiểm tra các document vi phạm dữ liệu.
3. **Contract:** khi chắc chắn không còn phụ thuộc field cũ, bỏ code tương thích ở phạm vi hiện hành theo kế hoạch.

History/archive có thể vẫn phải giữ format gốc, nên khả năng **đọc schema cũ** không nhất thiết được loại bỏ cùng lúc với code ghi cũ.

### 19.2. Version migration không phải business change

Nếu chỉ chuyển field `premium` sang `terms.premium` mà giá trị và ý nghĩa nghiệp vụ không đổi, không mặc định tăng `revision` nghiệp vụ hoặc tạo event “điều chỉnh phí”. Có thể ghi migration metadata riêng. Ngược lại, nếu migration biến đổi ý nghĩa giá trị, phải định nghĩa tác động đến audit và revision.

### 19.3. Thử đọc dữ liệu lịch sử thật

Một bộ dữ liệu regression nên có:

- Document current ở schema mới.
- Snapshot ở nhiều schemaVersion cũ.
- Event ở nhiều eventVersion khác nhau.
- Bản ghi có field thiếu/null/kiểu legacy hợp lệ.
- Dữ liệu được restore từ archive.

Mục tiêu là phát hiện sớm việc bản phát hành mới không còn giải mã được dữ liệu cũ.

## 20. Chi phí và độ phức tạp của các lựa chọn

Để chọn mô hình, cần ước lượng **khối lượng lịch sử**, không chỉ document current.

Giả định:

~~~text
Số thực thể:                  2.000.000
Số thay đổi trung bình/năm:   6 lần / thực thể
Kích thước snapshot logic:    3 KiB
Thời gian lưu:                7 năm
~~~

Ước lượng số revision:

~~~text
2.000.000 × 6 × 7 = 84.000.000 history documents
~~~

Ước lượng dữ liệu snapshot logic (chưa tính metadata, index, compression, replica, backup):

~~~text
84.000.000 × 3 KiB
≈ 240 GiB dữ liệu snapshot logic
~~~

Đây chỉ là minh họa. Với event delta có kích thước trung bình 0,3 KiB, dung lượng logic có thể thấp hơn nhiều, nhưng replay, kiểm soát eventVersion và tạo projection tốn công hơn. Snapshot cho truy vấn revision trực tiếp, đổi lại duplicate dữ liệu lớn.

### Tính tổng chi phí theo nhu cầu

~~~text
Chi phí lưu trữ nhiều năm =
  current data
  + history/event/snapshot
  + indexes và metadata
  + replication
  + backup/retention
  + cold archive
  + CPU/I/O cho ghi, query, export và restore
~~~

Compression làm giảm footprint lưu trữ vật lý trong nhiều trường hợp, nhưng không miễn trừ yêu cầu tính CPU, khả năng truy vấn, độ trễ tra cứu và chiến lược chuyển tầng.

## 21. Tình huống thiết kế thường gặp

### Tình huống A — Giá sản phẩm thay đổi nhưng đơn hàng cũ phải đúng

**Yêu cầu:** Cập nhật catalog giá thường xuyên, mỗi đơn phải giữ giá đã chốt.

**Mô hình:** `products` là giá hiện tại, `product_price_history` lưu các lần thay giá hoặc khoảng hiệu lực, còn `orders.lines[].unitPrice` là snapshot không phụ thuộc catalog. Không truy hồi giá đơn cũ bằng cách join vào `products.price` hiện tại.

**Tìm nguyên nhân:** Nếu đơn cũ có tổng tiền thay đổi sau khi sửa catalog, cần kiểm tra ứng dụng đang tính lại từ giá hiện tại hay đã lưu snapshot đúng.

### Tình huống B — Hợp đồng cần xem “bản có hiệu lực vào ngày D”

**Yêu cầu:** Xem điều khoản áp dụng khi phát sinh sự kiện hoặc tranh chấp.

**Mô hình:** Current + history với revision, hoặc effective-date intervals; nếu có sửa hồi tố, xem xét bitemporal. History có actor, reason và schemaVersion. Query theo `validFrom/validTo` phải giải quyết chồng khoảng và timezone.

**Rủi ro:** Chỉ sort `updatedAt` gần nhất không chắc chọn đúng điều khoản có hiệu lực trong quá khứ.

### Tình huống C — Cấu hình ứng dụng cần rollback

**Yêu cầu:** Khi deploy cấu hình sai, cần phục hồi bản trước.

**Mô hình:** Current + history snapshot; mỗi lần thay ghi `revision` và metadata deployment. Rollback nên được ghi thành **revision mới** với nội dung lấy từ revision cũ, để vẫn thấy chuỗi thay đổi; không âm thầm xóa các revision trung gian.

**Rủi ro:** Nếu chỉ thay current bằng snapshot cũ nhưng không ghi nhận hành động rollback, audit bị đứt đoạn.

### Tình huống D — Hàng tỷ telemetry event, truy vấn chủ yếu 30 ngày gần nhất

**Yêu cầu:** Dashboard nhanh cho dữ liệu mới, giữ thống kê nhiều năm.

**Mô hình:** Time-series hoặc event collection phù hợp cho ingestion, index theo sensor/tenant/time, retention online ngắn và aggregate/archive dài hạn. Kiểm soát payload, schemaVersion và catalog. TTL chỉ được dùng trên dữ liệu đã có chính sách xóa rõ ràng.

**Rủi ro:** Lưu tất cả readings vào mảng của một device sẽ gặp document growth và giới hạn 16 MiB.

### Tình huống E — Audit phải tồn tại kể cả khi tài khoản bị xóa

**Yêu cầu:** Điều tra thao tác trong hệ thống và tuân thủ dữ liệu cá nhân.

**Mô hình:** Audit event với actor ID/token danh tính phù hợp, tách quyền truy cập, retention và cơ chế ẩn danh/xóa theo chính sách. Không lưu thừa PII trong payload; xử lý mối quan hệ giữa yêu cầu xóa và nghĩa vụ giữ hợp pháp.

**Rủi ro:** History trở thành nơi giữ vô hạn thông tin nhạy cảm đã được loại bỏ khỏi current.

## 22. Bài thực hành: xây dựng lịch sử thay đổi hợp đồng

Thực hành theo thứ tự trên **database lab**. Phần transaction cần replica set hoặc sharded cluster hỗ trợ; nếu chỉ có standalone, vẫn có thể thực hiện những bước tạo schema/truy vấn, và mô tả transaction mà chưa chạy.

### Phần 1 — Khởi tạo

~~~javascript
use document_history_lab

db.createCollection("policies")
db.createCollection("policy_history")

db.policies.insertOne({
  _id: "lab-policy-001",
  revision: 1,
  schemaVersion: 1,
  status: "ACTIVE",
  terms: {
    premium: NumberDecimal("500000.00"),
    currency: "VND"
  },
  createdAt: ISODate("2026-01-01T00:00:00Z"),
  updatedAt: ISODate("2026-01-01T00:00:00Z")
})

db.policy_history.createIndex(
  { entityId: 1, revision: 1 },
  { unique: true }
)
~~~

Nếu đã thử các ví dụ ở trên, collection/index có thể tồn tại; hãy dùng database lab mới hoặc điều chỉnh tên. Không xóa dữ liệu không thuộc quyền sở hữu chỉ để chạy lại bài.

### Phần 2 — Thiết kế quy trình cập nhật

Mỗi lệnh sửa hợp đồng phải:

1. Nhận `entityId`, `expectedRevision`, `requestId`, actor và nội dung điều chỉnh.
2. Xác thực và validate thay đổi nghiệp vụ.
3. Trong transaction: đọc current, kiểm tra expectedRevision, cập nhật current có điều kiện, ghi snapshot cũ vào `policy_history`.
4. Bảo đảm uniqueness của `entityId + revision` và idempotency cho `requestId` theo phạm vi nghiệp vụ.
5. Sau commit, trả revision mới và trạng thái cuối cho client.

### Phần 3 — Thao tác và quan sát

Thực hiện ít nhất ba lần thay đổi hợp lệ trên cùng `lab-policy-001` với revision tăng dần. Ghi actor và reason khác nhau. Thử thêm:

- Một request dùng `expectedRevision` cũ và xác nhận bị conflict.
- Gửi lặp một `requestId` và nêu cách trả về cùng kết quả, không tạo một lần sửa mới.
- Đọc current và revision 1/2 từ history.
- Truy vấn 20 revision mới nhất và mô phỏng keyset pagination.
- Sửa schema hiển thị v1 → v2 bằng upcaster mà vẫn giữ snapshot cũ.

### Phần 4 — Thiết kế archive

Giả định sau hai năm, history cũ phải chuyển sang kho lạnh nhưng vẫn cần giữ bảy năm.

Hãy viết thiết kế archive batch gồm:

- Cutoff theo thời gian và trạng thái final.
- Quy tắc không lấy record còn đang sửa hoặc thuộc legal hold.
- Export có schemaVersion, checksum và danh sách key.
- Manifest có trạng thái, số lượng, phạm vi, vị trí và retentionUntil.
- Kiểm chứng đọc mẫu và thử restore trước khi xóa online.
- Cơ chế idempotency/checkpoint khi job bị ngắt giữa chừng.
- Đường truy xuất dữ liệu cũ theo `entityId`.

### Phần 5 — Đánh giá kết quả

| Tiêu chí | Bằng chứng cần có |
|---|---|
| Current đúng | Một current document có revision cao nhất |
| History đủ | Mỗi lần chuyển revision lưu snapshot bản bị thay thế |
| Không mất cập nhật | Concurrent update dùng revision guard |
| Không bị nhân đôi | Retry có idempotency, unique key phù hợp |
| Đọc được dữ liệu cũ | Query revision và upcaster nhiều schemaVersion |
| Truy vấn hợp lý | Index theo entity/revision, `explain()` với dữ liệu đại diện |
| Archive có thể phục hồi | Manifest, checksum, restore thử nghiệm |
| Retention đúng | Không TTL/xóa bản duy nhất trước thời hạn; xét ngoại lệ legal hold |

## 23. Những lỗi thiết kế nên tránh

| Lỗi | Hậu quả | Hướng xử lý |
|---|---|---|
| Nhúng toàn bộ history vào một document | Document không giới hạn, đọc/ghi ngày càng nặng | Giới hạn mảng hoặc tách history collection |
| Ghi history sau update current nhưng không có transaction | Có khoảng hở khiến mất phiên bản | Transaction hoặc mô hình event/outbox có reconciliation |
| Ghi đè revision cũ khi rollback | Mất vết thay đổi | Tạo revision mới biểu diễn hành động rollback |
| Dùng `schemaVersion` làm revision nghiệp vụ | Sai logic concurrency và migration | Tách schemaVersion/business revision |
| Dùng `updatedAt` thay cho khoảng hiệu lực | Trả sai dữ liệu có hiệu lực ở quá khứ | Thiết kế validFrom/validTo, recordedAt |
| Mặc định Change Streams là audit vĩnh viễn | Mất khả năng resume/replay lịch sử xa | Lưu event/history bền vững riêng |
| Đặt TTL vào bản dữ liệu duy nhất cần giữ nhiều năm | Xóa không thể tra cứu sau thời hạn TTL | Archive và kiểm chứng trước khi xóa |
| Cho phép update/delete history tùy ý | Mất integrity | Phân quyền, audit, lưu trữ bất biến khi cần |
| Chỉ giữ file archive, không giữ format/schema | Không đọc được dữ liệu sau nâng cấp | Format version, schema catalog, restore drill |
| Giữ PII trong mọi snapshot vô hạn | Rủi ro dữ liệu cá nhân | Data minimization, retention, xử lý legal hold |
| Chọn index history theo mọi field | Index chiếm dung lượng và tăng write cost | Chọn theo query thực, đo executionStats |
| Coi replica set là backup | Xóa nhầm có thể được nhân bản | Backup độc lập và kiểm chứng restore |

## 24. Câu hỏi ôn tập

**1. Khi nào nên tách history thành collection riêng?**

Khi lịch sử tăng theo thời gian, cần truy vấn/phân trang độc lập, retention khác current hoặc khối lượng history không thể giữ có giới hạn nhỏ trong document. MongoDB giới hạn BSON document ở 16 MiB; mảng tăng vô hạn không phù hợp.

**2. Business revision và schemaVersion khác nhau thế nào?**

Business revision biểu diễn thứ tự thay đổi trạng thái nghiệp vụ của một thực thể, thường phục vụ optimistic concurrency. SchemaVersion biểu diễn định dạng dữ liệu cần được code đọc/migrate. Chúng không nhất thiết tăng cùng lúc.

**3. Vì sao lưu snapshot cũ và cập nhật current nên nằm trong một transaction?**

Vì chúng thay đổi hai document/collection và cần thành công hoặc thất bại cùng nhau. Không có bảo đảm atomic đa document, lỗi giữa các bước có thể làm current và history không khớp.

**4. History collection khác event log thế nào?**

History snapshot mô tả trạng thái ở một revision; event mô tả sự kiện/chuyển đổi đã xảy ra. Event sourcing còn có quy tắc tái dựng current bằng cách replay event và xử lý thứ tự, version, idempotency.

**5. Valid time và recorded time giải quyết hai câu hỏi nào?**

Valid time cho biết dữ liệu có hiệu lực nghiệp vụ vào lúc nào. Recorded time cho biết hệ thống biết/ghi nhận dữ liệu khi nào. Sửa hồi tố khiến hai câu hỏi cho kết quả khác nhau.

**6. Có thể coi Change Streams là nguồn audit sau mười năm không?**

Không nên. Change Streams phục vụ quan sát thay đổi trên topology hỗ trợ và việc resume phụ thuộc retention/khả năng triển khai. Muốn lưu dài hạn cần đẩy event vào kho bền vững, có schema/version và quy trình kiểm chứng.

**7. Tại sao một snapshot giá cần lưu trong order?**

Để lịch sử đơn hàng không bị thay đổi khi catalog sản phẩm có giá mới. Đây là bản dữ liệu tại thời điểm giao dịch.

**8. TTL có thay thế archive không?**

Không. TTL chủ yếu hỗ trợ xóa tự động theo tuổi dữ liệu; archive cần export, manifest, integrity, quyền, khả năng tìm và phục hồi. Chỉ bật TTL khi dữ liệu được phép xóa và không còn là bản lưu duy nhất cần giữ.

**9. Vì sao chỉ đối chiếu số lượng record trước/sau export chưa đủ?**

Job có thể xuất trùng một record và bỏ sót một record khác mà count không thay đổi. Cần key set/checksum và kiểm tra restore/truy vấn mẫu.

**10. Khi khôi phục cấu hình cũ, tại sao tạo revision mới thay vì ghi đè lịch sử?**

Vì rollback là một sự kiện thay đổi mới cần được truy vết. Ghi đè revision cũ làm mất mạch audit và khiến hệ thống không tái dựng được chuỗi quyết định.

**11. Mô hình một event một document phù hợp hơn nhúng khi nào?**

Khi số sự kiện lớn, đến liên tục, cần query thời gian/tenant/sensor riêng và chính sách retention độc lập; embedded array không nên tăng vô hạn.

**12. Cần gì để đọc được archive sau nhiều năm?**

Vị trí file, định dạng và schema version, checksum, khóa giải mã nếu có, catalog để tìm theo entity/time, phần mềm đọc tương thích và restore drill định kỳ.

## 25. Checklist thiết kế trước khi triển khai

- [ ] Xác định câu hỏi cần trả lời: xem revision, audit hành động, as-of time hay lưu trữ lâu dài.
- [ ] Tách `revision` nghiệp vụ, `schemaVersion` và `eventVersion` nếu dùng event.
- [ ] Chọn current/history, event log, temporal model hoặc kết hợp có lý do.
- [ ] Quy định chính xác một revision được tạo lúc nào và key nào bảo đảm unique.
- [ ] Thiết kế optimistic concurrency cùng transaction/idempotency cho nhiều collection.
- [ ] Không dùng mảng lịch sử tăng vô hạn trong một BSON document.
- [ ] Xác định field thời gian, timezone và cách diễn giải valid/recorded time.
- [ ] Chỉ lưu snapshot/event chứa dữ liệu cần thiết, bảo vệ dữ liệu nhạy cảm.
- [ ] Chọn index dựa vào API truy vấn lịch sử và workload archive.
- [ ] Có retention, legal hold và quy định xóa dữ liệu từ current/history/archive/backup.
- [ ] Archive có manifest, checksum, version, cơ chế tìm và restore thử nghiệm.
- [ ] Kiểm tra ứng dụng có đọc được lịch sử thuộc nhiều schemaVersion.
- [ ] Phân biệt replication, history, backup và archive trong kế hoạch vận hành.
- [ ] Đo tốc độ tăng history/index, chi phí lưu trữ, thời gian khôi phục và latency tra cứu.

Thiết kế lịch sử tốt giúp hệ thống trả lời được **trạng thái nào từng tồn tại, thay đổi nào tạo ra trạng thái ấy, dữ liệu có hiệu lực khi nào và có thể đọc lại sau nhiều năm ra sao**. Chìa khóa là chọn đúng ranh giới document, bảo vệ tính nhất quán khi tạo revision, quản lý vòng đời dữ liệu và kiểm chứng khả năng truy xuất/khôi phục bằng các tình huống thực tế.

# Phân biệt lỗi xác nhận với thao tác ghi chưa được thực hiện trong MongoDB

## 1. Tại sao “ghi báo lỗi” không đồng nghĩa “không có dữ liệu được ghi”?

Khi xây dựng một ứng dụng dùng MongoDB, lập trình viên thường xử lý một thao tác ghi theo hai nhánh:

```text
Gọi insert/update/delete
        |
   +----+----+
   |         |
Thành công  Bắt exception
   |         |
Trả OK     Trả thất bại?
```

Sơ đồ trên **quá đơn giản** đối với hệ thống phân tán. Giữa ứng dụng và MongoDB tồn tại mạng, replica set, xác nhận từ server, sao chép dữ liệu, journal, timeout và khả năng bầu primary mới. Một lần ghi có thể đã thay đổi dữ liệu trên server nhưng ứng dụng **không nhận được lời xác nhận đầy đủ**.

Đây là khác biệt cốt lõi của bài:

> **“Không nhận được xác nhận ghi” không phải bằng chứng rằng “thao tác ghi chưa từng được thực hiện”.**

Ví dụ người dùng bấm “Đặt hàng”. Ứng dụng gửi `insertOne()` tới MongoDB. Server đã tạo document, nhưng kết nối bị ngắt trước khi phản hồi về tới ứng dụng. Nếu ứng dụng coi exception là “chưa tạo đơn” rồi gửi lại một đơn **với ID mới**, khách hàng có thể nhận **hai đơn**.

Ở chiều ngược lại, không phải lỗi nào cũng mơ hồ. MongoDB có thể thông báo rõ ràng một thao tác **không được áp dụng**, ví dụ lỗi duplicate key cho chính insert đang xét, nhưng những ghi khác của một lệnh bulk vẫn có thể thành công. Vì vậy cần nhìn **loại lỗi và phạm vi lỗi**, không chỉ nhìn một biến Boolean `success`.

Bài học thuộc chương **Nhất quán đọc ghi** và tập trung trả lời:

1. “Lệnh thành công” đã xác nhận điều gì?
2. `writeError` khác `writeConcernError` như thế nào?
3. `wtimeout` có nghĩa thao tác bị hủy hay không?
4. Mất kết nối sau khi gửi lệnh tạo trạng thái **không biết kết quả** ra sao?
5. Khi nào có thể retry, khi nào phải đối soát, và làm thế nào tránh ghi trùng?
6. Có thể dùng read concern và khóa nghiệp vụ để xác minh trạng thái như thế nào?
7. Transaction giúp gì, và vì sao **commit cũng có thể có kết quả xác nhận không rõ**?

## 2. Ba việc khác nhau trong một lần ghi

Không nên dùng cùng một từ “thành công” cho mọi giai đoạn của hệ thống.

### 2.1. Server có thực thi thay đổi hay không?

Ví dụ:

```javascript
db.orders.insertOne({
  _id: "order-1001",
  customerId: "C01",
  total: 250000
});
```

Đây là **tác động lên dữ liệu**: một document mới được chèn vào collection nếu thao tác hợp lệ và không bị chặn bởi ràng buộc.

### 2.2. Mức độ xác nhận ghi đã đạt chưa?

Client có thể yêu cầu server xác nhận theo **write concern**:

```javascript
db.orders.insertOne(
  {
    _id: "order-1002",
    customerId: "C02",
    total: 180000
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 3000
    }
  }
);
```

Với `w: "majority"`, yêu cầu ghi được xác nhận theo tiêu chí đa số của deployment, không chỉ theo việc primary đã nhận lệnh. Nếu không đạt yêu cầu trong thời hạn `wtimeout`, MongoDB có thể báo **write concern error**, dù thao tác ghi đã được áp dụng ở primary.

### 2.3. Ứng dụng có nhận được phản hồi hay không?

Ngay cả khi server đã xử lý và gửi phản hồi, mạng có thể đứt **sau khi server thực thi nhưng trước khi client nhận được kết quả**.

```text
      Client                           MongoDB primary
        |                                    |
        | -------- insertOne -------------> |
        |                                    | Áp dụng ghi
        |                                    | Gửi phản hồi
        |           X                      |
        | <---- phản hồi thất lạc ---------- |
        |
        +--> Timeout/connection error
             Không thể suy ra "chưa ghi"
```

Đây là **lỗi truyền thông/xác nhận từ góc nhìn client**, không tự nó chứng minh thao tác đã hoặc chưa được áp dụng trên server.

### 2.4. Các trục trạng thái không phải cùng một trục

| Câu hỏi | Ví dụ dữ kiện | Điều dữ kiện không tự chứng minh |
|---|---|---|
| Lệnh có đến server không? | Log nhận command | Không tự xác nhận đã hoàn tất |
| Ghi có được áp dụng không? | Document xuất hiện trên primary | Không tự xác nhận đã đạt majority |
| Ghi có đạt write concern không? | Phản hồi acknowledged theo yêu cầu | Không tự chứng minh client đã nhận phản hồi |
| Client có nhận kết quả không? | Driver trả thành công | Không nói mọi secondary đã áp dụng nếu chỉ yêu cầu `w: 1` |
| Ghi có còn sau failover không? | Quan sát bản ghi theo chính sách nhất quán thích hợp | Một lần đọc không thay thế được quyết định write concern/backup |

**Tư duy đúng:** phân biệt **tác động dữ liệu**, **mức xác nhận** và **tính chắc chắn của client**.

## 3. Dòng thời gian một lần ghi trong replica set

Giả sử replica set có ba thành viên chứa dữ liệu:

```text
              Client
                |
                v
             PRIMARY
                |
          Áp dụng ghi local
                |
        Ghi vào oplog / journal
                |
         +------+-------+
         |              |
         v              v
     SECONDARY A     SECONDARY B
         |              |
   Nhận và áp dụng  Nhận và áp dụng
         |              |
         +------+-------+
                |
    Đủ điều kiện write concern?
                |
         Phản hồi cho client
```

Sơ đồ là mô hình tư duy, không phải bảo đảm rằng MongoDB tuần tự thực hiện đúng từng bước theo cách biểu diễn. Việc ghi, journal và replication có chi tiết riêng theo storage engine, phiên bản và cấu hình.

### 3.1. `w: 1`

Khi chỉ yêu cầu một thành viên xác nhận, primary có thể trả thành công **trước khi secondary theo kịp**. Nếu primary gặp sự cố ngay sau đó, dữ liệu chưa đạt mức độ sao chép cần thiết có thể bị rollback trong quá trình failover.

```javascript
db.orders.insertOne(
  { _id: "w1-demo", total: 100 },
  { writeConcern: { w: 1 } }
);
```

Phản hồi thành công trong trường hợp này **không tương đương** “đã có bản ghi trên đa số thành viên”.

### 3.2. `w: "majority"`

```javascript
db.orders.insertOne(
  { _id: "majority-demo", total: 100 },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

Server chỉ xác nhận đáp ứng yêu cầu này khi điều kiện write concern majority được đáp ứng. Mục tiêu là có một mức bảo đảm mạnh hơn trước một số tình huống primary thay đổi.

**Lưu ý:** “đa số thành viên bỏ phiếu” và “độ bền ghi” còn liên quan đến data-bearing members, cấu hình journaling và các bảo đảm của phiên bản. Với topology có arbiter, đừng đơn giản đếm số node còn sống rồi suy ra mọi ghi majority chắc chắn được xác nhận.

### 3.3. `wtimeout` không hủy lệnh đã áp dụng

Nếu secondary chậm hoặc không đủ thành viên xác nhận đúng hạn:

```text
Client yêu cầu: w="majority", wtimeout=3000ms

0ms      Primary nhận và áp dụng ghi
1ms      Primary bắt đầu chờ điều kiện xác nhận
3000ms   Chưa đủ điều kiện write concern
         => báo write concern timeout

Sau đó:  Secondary có thể theo kịp và ghi đạt majority
         (hoặc có thể xảy ra sự cố/failover khác)
```

`wtimeout` giới hạn thời gian **chờ đáp ứng write concern**; nó không có nghĩa server phải hoàn tác thao tác đã áp dụng khi đồng hồ hết hạn.

Đó là lý do **retry mù quáng** ngay sau `wtimeout` có thể nguy hiểm đối với các thao tác không có tính idempotent.

## 4. Bốn nhóm kết quả phải phân biệt

### 4.1. Nhóm A — Thành công với mức xác nhận đã yêu cầu

Ví dụ driver trả kết quả thành công từ `insertOne()` với write concern đã cấu hình và không có lỗi.

Kết luận hợp lý:

- Server đã xử lý lệnh và phản hồi thành công theo yêu cầu xác nhận.
- Nếu `w: "majority"`, yêu cầu majority tương ứng đã được đáp ứng.
- Nếu chỉ `w: 1`, không tự suy ra secondary đã nhận ghi.

### 4.2. Nhóm B — Lỗi thực thi ghi (write error)

Ví dụ:

```javascript
db.orders.insertOne({
  _id: "order-1001",
  customerId: "C99"
});
```

Nếu document `_id: "order-1001"` đã tồn tại, MongoDB sẽ từ chối **lệnh insert đó** vì unique index của `_id`. Đây là lỗi thực thi ràng buộc dữ liệu như **duplicate key**, không phải lời báo “đã ghi nhưng chưa được sao chép”.

Một số lỗi ghi khác có thể liên quan đến validation, kiểu update không hợp lệ, bất biến `_id` hoặc ràng buộc unique index.

Tuy nhiên, với **bulk write** gồm nhiều thao tác, một `writeError` trên thao tác thứ N **không có nghĩa mọi thao tác trước đó đều chưa được thực thi**. Cần xem kết quả và phạm vi thao tác.

### 4.3. Nhóm C — Lỗi write concern sau khi thao tác được xử lý

Ví dụ một response ở mức command có thể báo phần ghi đã xử lý, nhưng đồng thời chứa `writeConcernError` vì chưa đạt mức xác nhận mong đợi.

```javascript
// Hình dạng minh họa, không phải response cố định của mọi phiên bản.
{
  ok: 1,
  n: 1,
  writeConcernError: {
    code: 64,
    errmsg: "waiting for replication timed out"
  }
}
```

Code và thông điệp có thể khác. Điểm cốt lõi: **write concern error không tương đương với write error**.

Ở nhánh này phải nghĩ:

> “Có thể thao tác đã được áp dụng; điều chưa được xác nhận là mức sao chép/độ bền yêu cầu.”

### 4.4. Nhóm D — Mất phản hồi hoặc lỗi mạng, kết quả chưa rõ

```text
Client gửi updateOne()
      |
      +--> Lệnh chưa tới server?
      |
      +--> Lệnh đã tới, chưa thực thi?
      |
      +--> Lệnh đã thực thi, response bị mất?
      |
      +--> Lệnh thực thi nhưng primary đổi vai trò?

Client chỉ nhìn thấy timeout/disconnect.
```

Trong nhiều trường hợp, client **không thể xác định từ exception mạng** một trong bốn khả năng này. Cần sử dụng cơ chế retry được hỗ trợ và thiết kế nghiệp vụ có thể đối soát.

### 4.5. Ma trận tóm tắt

| Tín hiệu | Được phép kết luận | Không được kết luận |
|---|---|---|
| Ghi thành công với `w: 1` | Primary đã xác nhận ở mức yêu cầu | Đã majority-committed |
| Ghi thành công với `w: "majority"` | Mức majority được xác nhận theo cấu hình | Mọi secondary đều theo kịp |
| Duplicate key cho một `insertOne` | Insert đang xét không thể tạo thêm record cùng khóa | Một request trước chắc chắn đã thành công đúng dữ liệu |
| `writeConcernError` / `wtimeout` | Không đạt mức xác nhận đúng hạn | Thao tác chưa hề được áp dụng |
| Socket reset sau khi gửi command | Client không nhận được kết quả cuối cùng | Server chắc chắn không ghi |
| Không có document ở một lần đọc | Chưa thấy document tại điểm đọc đó | Lệnh trước chưa từng tới/được xử lý |
| `NoWritesPerformed` trên tình huống retryable-write được hỗ trợ | Server/driver có tín hiệu xác định các lần thử liên quan chưa thực hiện ghi | Mọi lỗi mạng khác đều có bảo đảm tương tự |

## 5. Chuẩn bị lab an toàn

Các ví dụ tiếp theo sử dụng database riêng:

```javascript
use mongo_ack_lab
```

Khuyến nghị thực hiện trên **MongoDB replica set thử nghiệm**, kể cả single-node replica set cho bài tập cơ bản. Muốn quan sát write concern majority timeout do replication chậm cần topology thực sự có nhiều data-bearing members và môi trường kiểm soát; không cố gây lỗi mạng trên production.

### 5.1. Tạo collection và khóa duy nhất

```javascript
db.orderRequests.createIndex(
  { requestId: 1 },
  { unique: true }
);

db.accounts.createIndex(
  { accountId: 1 },
  { unique: true }
);
```

Ví dụ `orderRequests`:

```javascript
{
  _id: "order:REQ-001",
  requestId: "REQ-001",
  customerId: "C01",
  total: 250000,
  status: "CREATED"
}
```

**`requestId` đại diện cho một yêu cầu nghiệp vụ duy nhất.** Nếu người dùng bấm lại vì timeout, request hợp lệ cần sử dụng **cùng requestId**, không tự sinh ID mới cho cùng sự kiện nghiệp vụ.

### 5.2. Chọn write concern một cách tường minh

```javascript
db.orderRequests.insertOne(
  {
    _id: "order:REQ-001",
    requestId: "REQ-001",
    customerId: "C01",
    total: 250000,
    status: "CREATED"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

Trong môi trường lab ổn định, thao tác có thể được xác nhận thành công. **Không thể dự đoán trước** tốc độ replication, phản hồi và kết quả thực từ mọi deployment.

## 6. `writeError` và `writeConcernError` khác nhau ở đâu?

### 6.1. Một write error liên quan tới việc áp dụng thao tác

Ví dụ tạo một bản ghi:

```javascript
db.orderRequests.insertOne({
  _id: "order:REQ-002",
  requestId: "REQ-002",
  customerId: "C02",
  total: 180000
});
```

Chạy một insert khác trùng `requestId`:

```javascript
db.orderRequests.insertOne({
  _id: "order:REQ-002-DUPLICATE",
  requestId: "REQ-002",
  customerId: "C99",
  total: 999999
});
```

Vì đã tạo unique index `requestId`, insert mới bị từ chối. Document `order:REQ-002-DUPLICATE` **không được tạo bởi insert thất bại** nếu lỗi là duplicate key.

Điều này không cho phép suy ra request `REQ-002` của C99 đã được xử lý thành công: bản ghi tồn tại có thể thuộc **một payload khác**, hoặc do một lần xử lý từ trước.

### 6.2. Một write concern error liên quan mức xác nhận

Ví dụ thay đổi một document hợp lệ có thể đã được áp dụng ở primary nhưng chưa kịp đạt `w: "majority"` trong thời hạn:

```javascript
db.orderRequests.updateOne(
  { requestId: "REQ-001" },
  {
    $set: {
      status: "CONFIRMED"
    }
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 1000
    }
  }
);
```

Nếu nhận write concern timeout:

- **Không tự động đổi status về CREATED.**
- **Không tự động kết luận update chưa chạy.**
- **Không lập tức gửi một thao tác nghiệp vụ mới với mã khác.**
- **Phải xác minh và xử lý theo chính sách retry/consistency.**

`$set` giá trị cố định ở đây có tính **idempotent về trạng thái cuối**: áp dụng lại cùng `status: "CONFIRMED"` thường cho cùng giá trị của trường đó. Nhưng nếu update còn chỉnh timestamp, cộng counter hoặc gửi side effect ngoài MongoDB, tổng workflow chưa chắc idempotent.

### 6.3. Lưu ý `acknowledged` trong driver

Nhiều driver hiển thị thông tin như `acknowledged`, `matchedCount`, `modifiedCount`, `insertedId` khi thao tác trả thành công:

```javascript
const result = db.orderRequests.updateOne(
  { requestId: "REQ-001" },
  { $set: { status: "CONFIRMED" } }
);

printjson(result);
```

Hình dạng thường gặp:

```javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedCount: 0
}
```

Những con số thực phụ thuộc dữ liệu và lệnh. Với `w: 0`, API có thể trả `acknowledged: false` **theo cấu hình không yêu cầu phản hồi**, không có nghĩa server đã chứng minh thao tác thất bại.

Nếu driver **ném exception** trước khi trả một result thông thường, không nên tự tạo `acknowledged: false` rồi coi đó là bằng chứng “chưa ghi”.

## 7. Write concern: `w`, `j`, `wtimeout`

### 7.1. `w` quyết định mức xác nhận

Các mức thường gặp:

| Cấu hình | Ý nghĩa khái quát | Điều cần chú ý |
|---|---|---|
| `w: 0` | Không yêu cầu server trả xác nhận ghi | Client có rất ít thông tin để phân biệt thành công/thất bại |
| `w: 1` | Yêu cầu xác nhận từ primary hoặc thành viên đang nhận ghi theo quy tắc tương ứng | Không bảo đảm majority replication |
| `w: "majority"` | Yêu cầu mức xác nhận từ đa số theo quy tắc replica set | Có thể timeout nếu các thành viên cần thiết không theo kịp |
| `w: N` | Yêu cầu số thành viên xác nhận theo cấu hình hợp lệ | Không tự thay thế phân tích topology và độ bền |

Không khuyến khích `w: 0` cho lệnh tạo thanh toán, đơn hàng hoặc cập nhật số dư vì ứng dụng không nhận đủ kết quả để quyết định an toàn.

### 7.2. `j` và journaling

`j: true` yêu cầu xác nhận liên quan tới journal theo cơ chế được hỗ trợ. Nó là một phần của câu chuyện **độ bền trên storage**, khác với yêu cầu sao chép đến nhiều member.

```javascript
db.orderRequests.insertOne(
  {
    _id: "order:REQ-003",
    requestId: "REQ-003",
    total: 50000
  },
  {
    writeConcern: {
      w: 1,
      j: true,
      wtimeout: 5000
    }
  }
);
```

Không suy rằng `w: 1, j: true` tương đương `w: "majority"`. Một bên gắn với xác nhận trên node nhận ghi và journal; bên kia gắn với yêu cầu sao chép/majority theo cấu hình.

Trong deployment hiện đại, tương tác giữa majority và journaling còn phụ thuộc thiết lập như `writeConcernMajorityJournalDefault` và storage engine; không nên xem hai từ “journal” và “majority” là đồng nghĩa.

### 7.3. `wtimeout` không giống timeout truyền thông của client

`wtimeout` giới hạn thời gian chờ yêu cầu write concern. Còn các timeout khác có thể giới hạn chọn server, tạo kết nối, đọc/ghi socket hoặc tổng thời gian thực hiện API tùy driver.

| Loại timeout | Phạm vi | Có chứng minh không ghi không? |
|---|---|---|
| `wtimeout` | Chờ đáp ứng write concern | **Không** |
| Network/socket timeout | Giao tiếp giữa client và server | **Không**, nếu command có thể đã được gửi |
| Server selection timeout | Chờ chọn server đáp ứng topology | Nếu xác định không gửi command thì chưa có ghi do lần gọi đó; nhưng cần căn cứ vào driver/log |
| Client-side deadline | Giới hạn tổng thời gian request phía client | Không tự xác định server đã dừng xử lý hay chưa |

Một timeout phía client xảy ra **trước khi command được gửi** khác với timeout xảy ra **sau khi command đã tới primary**. Chỉ từ tên exception chung “timeout” không thể phân biệt an toàn mọi trường hợp.

### 7.4. Timeout không phải nút undo

```text
Client: "Tôi chỉ chờ tối đa 3 giây."
Server: "Tôi đã ghi, nhưng chưa xác nhận đủ theo yêu cầu."

Client hết thời gian chờ != Server hoàn tác tất cả thay đổi.
```

Ứng dụng phải định nghĩa rõ trạng thái **UNKNOWN/UNCERTAIN**, thay vì ép mọi timeout vào một trong hai nhánh `SUCCESS` và `FAILED`.

## 8. Mất mạng sau khi gửi: bài toán kết quả không xác định

### 8.1. Ba tình huống client khó phân biệt

Giả sử:

```javascript
db.accounts.updateOne(
  { accountId: "A01" },
  { $inc: { balance: -100 } }
);
```

Trong lúc gọi lệnh, client mất kết nối.

**Tình huống 1 — lệnh chưa được gửi tới server:**

```text
Client --X--> Server
Không có tác động ghi từ lần gửi này.
```

**Tình huống 2 — server nhận lệnh nhưng chưa hoàn tất:**

```text
Client -----> Server (đang xử lý)
Client <---X  Mất phản hồi
Kết cục vẫn đang chuyển tiếp hoặc chưa rõ.
```

**Tình huống 3 — server đã ghi nhưng phản hồi bị mất:**

```text
Client -----> Server
              balance -= 100
Client <---X  Mất phản hồi
Ứng dụng không biết balance đã giảm.
```

Nếu ứng dụng tự gửi lại `$inc: -100` như một **lệnh mới**, số dư có thể giảm thêm 100, tổng cộng -200.

### 8.2. Không nên retry bằng cách tự tạo request mới

Đây là ví dụ sai:

```javascript
// Pseudocode mô tả anti-pattern, KHÔNG dùng cho số dư thật.
try {
  debitAccount(accountId, 100, createNewRequestId());
} catch (e) {
  debitAccount(accountId, 100, createNewRequestId());
}
```

Hai lần gọi dùng **ID nghiệp vụ khác nhau**, nên cơ chế unique index hoặc deduplication theo request ID cũng không nhận ra đây là cùng một yêu cầu.

### 8.3. Đọc lại có giúp được không?

Nếu client đọc lại số dư và thấy đã giảm 100, có thể **đã có tác động của lệnh trước**. Nhưng nếu các giao dịch khác cùng thay đổi số dư, chỉ nhìn giá trị tổng không đủ xác định **giao dịch nào** đã gây biến động.

Tương tự, nếu chưa thấy thay đổi ngay lập tức:

- Lần đọc có thể đi tới secondary bị lag.
- Lệnh trước có thể chưa hoàn tất.
- Trạng thái có thể thay đổi khi failover.
- Một thao tác khác có thể đã bù trừ vào giá trị tổng.

**Muốn đối soát đáng tin cậy, phải theo dõi một định danh giao dịch/yêu cầu duy nhất**, không chỉ so sánh một trường số thay đổi.

## 9. Retryable writes: cơ chế retry của MongoDB driver

MongoDB hỗ trợ **retryable writes** cho những thao tác và deployment phù hợp. Driver có thể gửi lại một thao tác ghi đủ điều kiện sau lỗi truyền thông hoặc failover mà không đối xử với nó như một yêu cầu hoàn toàn mới.

### 9.1. Cấu hình kết nối

Ví dụ URI:

```text
mongodb://mongo-a.example:27017,mongo-b.example:27017,mongo-c.example:27017/?replicaSet=rsApp&retryWrites=true
```

Host và replica set name trên là ví dụ. Cấu hình production cần credential/TLS và địa chỉ thật. Các driver hiện đại thường bật retryable writes theo mặc định khi deployment hỗ trợ; việc khai báo tường minh giúp người đọc biết ý định nhưng không thay việc kiểm tra cấu hình driver thực tế.

### 9.2. Cơ chế nhận diện lần retry

Ở mức khái niệm, cơ chế sử dụng thông tin session và định danh statement/transaction number phù hợp để server nhận ra lần gửi lại của **cùng thao tác retryable**, thay vì coi đó là một thao tác ghi hoàn toàn khác.

```text
Driver gửi write W với session/statement identity
       |
       +--> Response thất lạc
       |
Driver retry write W với identity phù hợp
       |
Server nhận diện retry theo cơ chế được hỗ trợ
       |
Giảm rủi ro áp dụng cùng statement hai lần
```

Điều này khác với code ứng dụng tự gọi lại một API bất kỳ bằng **session hoặc request mới**. Không nên phát biểu rằng “driver có retryable writes nên toàn bộ nghiệp vụ exactly-once”.

### 9.3. Những thao tác thường đủ điều kiện

Trong replica set/sharded cluster có khả năng hỗ trợ, các thao tác ghi một document thường có thể là retryable, ví dụ:

- `insertOne()`.
- `updateOne()`.
- `replaceOne()`.
- `deleteOne()`.
- Một số thao tác find-and-modify như `findOneAndUpdate()`.
- Một số bulk write gồm các thành phần đủ điều kiện, theo đặc tả và giới hạn của driver/server.

**Không nên giả định** `updateMany()` hoặc `deleteMany()` tự động được retry theo cùng cơ chế idempotent của retryable single-document writes. Các lệnh nhiều document có thể áp dụng được một phần trước khi gặp lỗi và cần quy trình phục hồi riêng.

### 9.4. Retryable writes có giới hạn

Không phải mọi lỗi đều được retry. Những điều kiện thường ảnh hưởng gồm:

- MongoDB server/driver version.
- Deployment có hỗ trợ logical sessions và retryable writes không.
- Operation có nằm trong nhóm retryable không.
- Lỗi có đủ điều kiện retry không.
- Driver đã hết số lần thử hoặc deadline chưa.
- Thao tác có nằm trong transaction không.
- Dữ liệu đã bị thay đổi bởi một request khác hoặc ràng buộc nghiệp vụ nào.

**Lỗi duplicate key không mặc nhiên là lỗi tạm thời để retry vô hạn.**

### 9.5. `NoWritesPerformed` là tín hiệu đặc biệt, không phải mặc định

MongoDB 6.1 bổ sung **error label `NoWritesPerformed`** trong những trường hợp retryable write mà cả lần đầu và lần retry đều lỗi **mà không có thao tác ghi được thực hiện**.

Nếu thực sự nhận được label đó trong đúng điều kiện được hỗ trợ, ứng dụng có **tín hiệu mạnh hơn** về việc các lần thử liên quan chưa thực hiện ghi.

Nhưng:

- Không phải mọi phiên bản/deployment đều cung cấp label.
- Không phải mọi loại operation đều thuộc cơ chế này.
- **Không có `NoWritesPerformed` không có nghĩa đã ghi**; nó có thể đơn giản là chưa có đủ thông tin.
- Một exception mạng thông thường không tự mang ý nghĩa `NoWritesPerformed`.

Ví dụ Java:

```java
if (exception.hasErrorLabel("NoWritesPerformed")) {
    // Có bằng chứng chuyên biệt theo cơ chế retryable write.
    // Vẫn phải xử lý quy tắc nghiệp vụ trước khi quyết định thử tiếp.
}
```

Không gắn nhãn này thủ công vào một exception rồi xem đó là bằng chứng server đã đảm bảo không ghi.

## 10. Idempotency: thiết kế thao tác lặp mà không nhân đôi tác động

### 10.1. Khái niệm

Một thao tác **idempotent** nếu áp dụng nhiều lần **với cùng yêu cầu** vẫn cho trạng thái nghiệp vụ cuối như áp dụng một lần, trong phạm vi đã định nghĩa.

Ví dụ:

```javascript
// Thường idempotent đối với riêng trường status:
{ $set: { status: "CONFIRMED" } }

// KHÔNG idempotent nếu được thực thi như hai statement mới:
{ $inc: { balance: -100 } }

// KHÔNG idempotent khi mỗi lần chèn tạo _id mới:
insertOne({ _id: new ObjectId(), requestId: newUUID() })
```

Tính idempotent của một field update **không tự đồng nghĩa** tính idempotent của toàn workflow. Ví dụ cập nhật status một lần nhưng gửi email hai lần vẫn là một workflow có side effect trùng.

### 10.2. Dùng request ID ổn định

Với nghiệp vụ tạo đơn, client tạo một `requestId` duy nhất **một lần cho hành động đặt hàng**, rồi sử dụng lại trong mọi lần retry của chính hành động đó.

```javascript
const requestId = "REQ-ORDER-2026-0001";

const order = {
  _id: "order:" + requestId,
  requestId: requestId,
  customerId: "C01",
  total: 250000,
  currency: "VND",
  status: "CREATED"
};

db.orderRequests.insertOne(
  order,
  { writeConcern: { w: "majority", wtimeout: 5000 } }
);
```

Khi retry theo nghiệp vụ, **không sinh `requestId` và `_id` khác** cho cùng đơn hàng. Unique index trên `requestId` chặn hai document cùng key; `_id` cố định cũng hỗ trợ tránh tạo bản ghi thứ hai.

### 10.3. Duplicate key sau retry có nghĩa gì?

Giả sử client thử insert lại cùng document và nhận duplicate key. Có thể:

1. Lệnh trước đã thành công và cùng document đang tồn tại.
2. Một request khác đã ghi document cùng key.
3. Dữ liệu đích tồn tại nhưng payload khác, ví dụ `total` không khớp.
4. Một tác nhân khác đã sửa document giữa hai lần thử.

Vì vậy, **không tự động coi mọi duplicate key là success**. Cần đọc document theo khóa ổn định và xác minh nó **thuộc cùng request, cùng payload được chấp nhận và trạng thái nghiệp vụ hợp lệ**.

### 10.4. Dùng trạng thái “chưa rõ” cho phía API

Một hợp đồng API tốt thường cần ít nhất ba trạng thái:

```text
SUCCESS
  Ghi đã được xác nhận phù hợp.

REJECTED
  Có bằng chứng thao tác bị từ chối theo quy tắc nghiệp vụ.

UNKNOWN / PENDING_CONFIRMATION
  Kết quả không được xác nhận đầy đủ; phải đối soát hoặc retry an toàn.
```

Không trả thông báo “Tạo đơn thất bại, hãy đặt lại bằng yêu cầu mới” cho mọi timeout nếu chính việc retry bằng ID mới sẽ gây trùng đơn.

### 10.5. Phân biệt deduplication và correctness

Khóa duy nhất ngăn **tạo nhiều document có cùng requestId**, nhưng không tự giải quyết:

- Một request ID bị sử dụng lại với payload khác.
- Chuyển số dư giữa hai tài khoản cần nhiều thao tác.
- Gửi email/thông báo tới hệ thống bên ngoài.
- Hoàn tiền khi đã thu tiền.
- Ghi lịch sử audit và bản ghi nghiệp vụ trong hai collection mà chỉ một bên thành công.

Đây là lý do hệ thống cần **trạng thái nghiệp vụ, ràng buộc dữ liệu, transaction hoặc quy trình khôi phục** phù hợp, chứ không chỉ tạo một unique index rồi coi vấn đề đã xong.

## 11. Đối soát sau lỗi xác nhận

### 11.1. Quy trình an toàn ở mức nghiệp vụ

Giả sử lệnh tạo `order:REQ-001` báo timeout.

```text
Timeout sau lần ghi
        |
        v
Giữ nguyên requestId / business key
        |
        v
Xác định lỗi:
  - writeError?
  - writeConcernError?
  - network / unknown?
  - error label đặc biệt?
        |
        v
Đọc/đối soát trạng thái ở nguồn có thẩm quyền
        |
    +---+--------------------+
    |                        |
Có record phù hợp         Chưa xác định chắc chắn
    |                        |
Kiểm tra payload,        Không tạo request mới
trạng thái, write        Retry an toàn với cùng key
concern/majority         hoặc tiếp tục đối soát
    |                        |
    +------------+-----------+
                 |
         Trả trạng thái nghiệp vụ
```

### 11.2. Truy vấn theo request ID

```javascript
db.orderRequests.findOne({
  requestId: "REQ-001"
});
```

Nên sử dụng **một ID ổn định có unique index** và so sánh ít nhất:

- `requestId`.
- `customerId`.
- `total` và `currency`.
- Trạng thái nghiệp vụ.
- Phiên bản/dấu vết xử lý nếu workflow có nhiều bước.

Nếu thấy document cùng `requestId` nhưng `total` khác, đó là **xung đột dữ liệu**, không phải một “retry thành công” hợp lệ.

### 11.3. Chọn read preference và read concern khi đối soát

Nếu đọc từ một secondary bị trễ ngay sau ghi vào primary, không thấy document là điều có thể xảy ra dù thao tác ghi đã được primary áp dụng.

Một cách đối soát thường phù hợp khi muốn chỉ xem dữ liệu **đã đạt majority** là đọc từ primary với read concern `majority`:

```javascript
db.orderRequests
  .withReadConcern("majority")
  .findOne({ requestId: "REQ-001" });
```

Trong môi trường khác nhau, cú pháp helper của mongosh có thể khác. Một dạng dùng MongoDB command tường minh để minh họa read concern:

```javascript
db.runCommand({
  find: "orderRequests",
  filter: { requestId: "REQ-001" },
  limit: 1,
  readConcern: { level: "majority" }
});
```

**Điều cần hiểu:** một lần đọc majority không thấy document **không chứng minh thao tác cũ chưa từng áp dụng trên primary**. Nó chỉ nói rằng tại điểm đọc với mức bảo đảm đã chọn, client chưa quan sát được document đó. Một write concern timeout trước đó có thể sau này đạt majority, hoặc có thể bị rollback trong một số sự cố.

Nếu nghiệp vụ cần xác định thời điểm có thể **quyết định lại**, phải kết hợp cơ chế deduplication với lifecycle của request và chính sách retry phù hợp, không phụ thuộc vào một lần `findOne()` đơn lẻ.

### 11.4. Đọc thấy document có đồng nghĩa đủ bảo đảm không?

Không phải lúc nào cũng vậy. Một lần đọc local trên primary có thể thấy document **chưa đạt majority write concern**. Nếu primary đổi vai trò trước khi ghi được majority-committed, trạng thái có thể khác sau failover.

Đối với dữ liệu quan trọng, hệ thống cần định nghĩa mức xác nhận và độ nhất quán mong muốn trước khi trả “thành công cuối cùng” tới người dùng.

## 12. Kịch bản: lỗi khi ghi đơn hàng, tài khoản và bộ đếm

### 12.1. Insert với `_id` cố định

```javascript
db.orderRequests.insertOne(
  {
    _id: "order:REQ-100",
    requestId: "REQ-100",
    total: 100000
  },
  { writeConcern: { w: "majority", wtimeout: 3000 } }
);
```

Nếu response mơ hồ:

1. Giữ `REQ-100`.
2. Đối soát document theo `requestId`.
3. Nếu retry, dùng **cùng khóa nghiệp vụ**, không tạo ID mới.
4. Nếu duplicate key, **kiểm tra nội dung document** trước khi báo success.

Đây là mô hình dễ làm idempotent hơn so với insert `_id` mới mỗi lần.

### 12.2. `$set` sang giá trị cố định

```javascript
db.orderRequests.updateOne(
  {
    requestId: "REQ-100",
    status: "CREATED"
  },
  {
    $set: {
      status: "CONFIRMED"
    }
  }
);
```

Filter có điều kiện `status: "CREATED"` giúp biểu đạt một chuyển trạng thái có kiểm soát. Nếu status đã là `CONFIRMED` vì lần trước thành công, retry như một thao tác mới có thể cho `matchedCount: 0`.

**`matchedCount: 0` không tự nghĩa là lỗi.** Nó có thể phản ánh thao tác trước đã chuyển status, record bị xóa, trạng thái xung đột hoặc request không tồn tại. Cần đọc và phân loại trạng thái thật.

### 12.3. `$inc` không idempotent khi chạy lại như lệnh mới

```javascript
db.accounts.updateOne(
  { accountId: "A01" },
  { $inc: { balance: -100 } }
);
```

Nếu ứng dụng gửi lại `$inc` một cách độc lập, thao tác có thể chạy lần hai. Không dùng cách này để “retry chắc ăn” khi client không biết kết quả trước.

Các lựa chọn an toàn hơn tùy nghiệp vụ:

- Sử dụng retryable write đúng cách và không tự tái tạo statement không liên quan.
- Thiết kế ledger có `operationId` duy nhất.
- Ghi dấu đã xử lý và điều chỉnh số dư theo ranh giới atomicity/transaction thích hợp.
- Dùng event sourcing hoặc tính số dư từ sự kiện đã xác nhận khi phù hợp.

### 12.4. `updateMany()` có thể có thành công một phần

```javascript
db.accounts.updateMany(
  { archived: false },
  { $set: { reviewed: true } }
);
```

Nếu command gặp lỗi giữa quá trình, không mặc định “không account nào được thay đổi”. Các thao tác trên nhiều document không tự trở thành transaction chỉ vì viết trong một lệnh `updateMany()`.

Vì `$set: { reviewed: true }` là cập nhật trạng thái cố định, có thể thiết kế quy trình quét lại/idempotent, nhưng vẫn cần xem lỗi, những document mới xuất hiện trong tập filter và tác động của thay đổi đồng thời.

## 13. Bulk write: một lỗi không đại diện cho mọi thao tác

### 13.1. Ordered bulk

Ví dụ:

```javascript
db.bulkAckDemo.bulkWrite(
  [
    {
      insertOne: {
        document: { _id: "A", value: 1 }
      }
    },
    {
      insertOne: {
        document: { _id: "A", value: 2 }
      }
    },
    {
      insertOne: {
        document: { _id: "B", value: 3 }
      }
    }
  ],
  { ordered: true }
);
```

Trong collection rỗng:

1. Insert A đầu tiên có thể thành công.
2. Insert A thứ hai bị duplicate key.
3. Với `ordered: true`, những thao tác phía sau lỗi thường không được thực hiện tiếp trong batch theo quy tắc ordered bulk.

Vì vậy, **bulk command báo lỗi** nhưng document A vẫn có thể tồn tại do thao tác đầu tiên thành công. Không được suy ra “cả bulk đã rollback”.

### 13.2. Unordered bulk

```javascript
db.bulkAckDemo.bulkWrite(
  [
    { insertOne: { document: { _id: "C", value: 1 } } },
    { insertOne: { document: { _id: "C", value: 2 } } },
    { insertOne: { document: { _id: "D", value: 3 } } }
  ],
  { ordered: false }
);
```

Với unordered bulk, server có thể tiếp tục xử lý các thao tác khác dù có lỗi trên một phần tử. **Đừng giả định thứ tự thực thi hoặc tập kết quả bằng thứ tự array nguồn**.

Một phản hồi bulk có thể chứa:

- Số thao tác insert/update/delete thành công.
- Danh sách `writeErrors` kèm index thao tác liên quan.
- `writeConcernError` nếu yêu cầu xác nhận chưa đạt.
- Thông tin upserted IDs hoặc số document khớp/sửa trong giới hạn driver cung cấp.

### 13.3. Quy tắc xử lý bulk an toàn

Không bao giờ biến:

```text
bulkWrite() threw exception
```

thành:

```text
0 thao tác được thực hiện
```

trừ khi có bằng chứng chính xác cho kết luận đó.

Nếu bulk gồm nhiều nghiệp vụ khác nhau, mỗi phần tử nên có **khóa duy nhất/operationId** và cơ chế đối soát riêng. Với bulk khổng lồ, có thể cần chia batch để giới hạn phạm vi phục hồi, nhưng chia batch không tạo tự động tính nguyên tử nhiều document.

## 14. Transaction nhiều document và xác nhận commit không rõ

MongoDB hỗ trợ transaction trên replica set/sharded deployment phù hợp. Transaction có thể giúp nhiều thao tác đọc/ghi thuộc **một đơn vị commit nguyên tử**.

Ví dụ chuyển tiền giữa hai tài khoản có thể cần:

1. Trừ số dư A.
2. Cộng số dư B.
3. Ghi ledger.

Nếu thao tác được commit thành công theo transaction, hai cập nhật thuộc cùng đơn vị transaction theo các bảo đảm MongoDB.

### 14.1. Transaction không làm mất hoàn toàn sự mơ hồ của mạng

```text
Client                 MongoDB
  |                      |
  | --- commitTransaction --> |
  |                      | Transaction được commit
  |     X                | Server gửi response
  | <-- response lost --- |
  |
  +--> Client không biết commit đã thành công chưa
```

Đây là bài toán **uncertain commit outcome**. Không được ngay lập tức chạy lại toàn bộ nghiệp vụ chuyển tiền như một transaction mới chỉ vì client bị timeout ở bước commit.

### 14.2. Nhãn lỗi thường gặp với transaction

MongoDB driver có thể cung cấp error labels như:

- **`TransientTransactionError`**: có thể cần retry cả transaction theo cơ chế được hỗ trợ, khi appropriate.
- **`UnknownTransactionCommitResult`**: kết quả của **commit** chưa rõ; hướng xử lý thường là retry **commit** theo protocol phù hợp thay vì lập tức thực thi lại toàn bộ body nghiệp vụ.

Các driver hỗ trợ callback transaction như `withTransaction()` có cơ chế retry nhất định. Phải sử dụng theo hướng dẫn của phiên bản driver và không tự chồng nhiều vòng retry không kiểm soát.

### 14.3. Sự khác nhau giữa retry body và retry commit

```text
Lỗi trước commit, transaction bị hủy rõ:
  -> có thể retry toàn body nếu nghiệp vụ và driver cho phép.

Lỗi commit với kết quả không xác định:
  -> cần xác minh/retry commit theo protocol,
     KHÔNG tạo một nghiệp vụ mới tùy tiện.
```

Transaction hỗ trợ atomicity của MongoDB, nhưng không tự tạo exactly-once cho **thanh toán bên ngoài, gửi email hoặc gọi API khác** xảy ra trong transaction body. Side effect ngoài MongoDB cần kiến trúc riêng, ví dụ transactional outbox, idempotency key tại bên nhận và quy trình đối soát.

## 15. Ví dụ Java Sync Driver: phân loại exception

Giả sử ứng dụng Java dùng MongoDB Sync Driver. Mục tiêu ví dụ là **không biến mọi MongoException thành “chưa ghi”**.

### 15.1. Tạo collection với write concern

```java
import com.mongodb.MongoException;
import com.mongodb.MongoWriteConcernException;
import com.mongodb.MongoWriteException;
import com.mongodb.WriteConcern;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class WriteAcknowledgementExample {
    public static void main(String[] args) {
        String uri =
            "mongodb://localhost:27017/?replicaSet=rsLab&retryWrites=true";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> base = client
                .getDatabase("mongo_ack_lab")
                .getCollection("orderRequests");

            MongoCollection<Document> writes = base.withWriteConcern(
                WriteConcern.MAJORITY.withWTimeout(5, TimeUnit.SECONDS)
            );

            String requestId = "REQ-JAVA-001";
            Document order = new Document("_id", "order:" + requestId)
                .append("requestId", requestId)
                .append("customerId", "C01")
                .append("total", 250000)
                .append("status", "CREATED");

            try {
                writes.insertOne(order);
                System.out.println("ACKNOWLEDGED");
            } catch (MongoWriteException e) {
                System.out.println("WRITE_ERROR: " + e.getMessage());
                // Ví dụ duplicate key: kiểm tra record cùng requestId.
            } catch (MongoWriteConcernException e) {
                System.out.println("WRITE_CONCERN_UNMET: " + e.getMessage());
                // Không kết luận rằng insert chưa diễn ra.
            } catch (MongoException e) {
                System.out.println("OUTCOME_POSSIBLY_UNKNOWN: " + e.getMessage());
                if (e.hasErrorLabel("NoWritesPerformed")) {
                    System.out.println("Server reports no writes performed");
                }
                // Phân loại lỗi và đối soát theo business key.
            }

            // Dành cho bước đối soát; KHÔNG coi một lần đọc là
            // bằng chứng tuyệt đối rằng ghi trước đó chưa từng chạy.
            MongoCollection<Document> majorityRead =
                base.withReadConcern(ReadConcern.MAJORITY)
                    .withReadPreference(ReadPreference.primary());

            Document observed = majorityRead.find(
                new Document("requestId", requestId)
            ).first();

            System.out.println("Observed at majority read: " + observed);
        }
    }
}
```

**Giả định của ví dụ:** local replica set tên `rsLab` đang chạy trên port được khai báo, collection `orderRequests` có unique index `requestId` và môi trường lab không yêu cầu credential. URI và port phải được thay theo lab thực tế; nếu lab có ba seed node, dùng seed list tương ứng.

### 15.2. Điều gì quan trọng hơn cú pháp catch?

Không phải tên exception nào cũng chứa kết luận cuối cùng của nghiệp vụ. Ứng dụng cần:

- Ghi lại `requestId` từ **trước khi gửi thao tác**.
- Lưu exception type, error labels, write concern và metadata phù hợp.
- Phân biệt lỗi ràng buộc dữ liệu với lỗi mức xác nhận.
- Đối soát document theo request ID nếu response không rõ.
- Xử lý trường hợp record tồn tại nhưng **payload khác**.
- Không phát một debit/payment mới chỉ vì thấy `MongoException`.

Ngoài ra, việc đọc đối soát **cũng có thể lỗi mạng**. Không xây code giả định mọi exception ghi đều được giải quyết bằng đúng một lệnh `find()` ngay sau đó.

### 15.3. Với Java transaction

Khi dùng `ClientSession` và transaction, ưu tiên helper được driver cung cấp cho retry transaction/commit theo nhãn lỗi. Nếu tự viết retry, cần hiểu chính xác `TransientTransactionError` và `UnknownTransactionCommitResult`; không nên gộp chúng với trường hợp insert/update thông thường.

## 16. Ví dụ mongosh: kiểm tra loại lỗi

Một đoạn lab đơn giản để phân biệt lỗi duplicate key với lỗi xác nhận:

```javascript
const collection = db.getSiblingDB("mongo_ack_lab").orderRequests;

const doc = {
  _id: "order:REQ-MONGOSH-001",
  requestId: "REQ-MONGOSH-001",
  total: 90000
};

try {
  const result = collection.insertOne(
    doc,
    {
      writeConcern: {
        w: "majority",
        wtimeout: 5000
      }
    }
  );

  print("Write acknowledged:");
  printjson(result);
} catch (e) {
  print("Write did not return a normal success result:");
  print(e.message);
  printjson({
    name: e.name,
    code: e.code,
    errorLabels: e.errorLabels
  });
}
```

Nếu chạy lại với cùng document mà `_id`/`requestId` đã tồn tại, thường sẽ nhận duplicate key. Đây là cách **tạo lỗi ràng buộc dự đoán được** để quan sát khác biệt với thành công.

**Không thể dùng việc chèn trùng để mô phỏng write concern timeout.** Hai loại lỗi đến từ các điều kiện khác nhau.

### 16.1. Xem bản ghi sau một lỗi

```javascript
collection.findOne({
  requestId: "REQ-MONGOSH-001"
});
```

Nếu đã có bản ghi, kiểm tra payload và trạng thái. Trong lab không có ghi đồng thời, kết quả dễ giải thích; trong hệ thống thật phải xét thêm ai có thể dùng cùng key và thay đổi document.

### 16.2. Quan sát lỗi trực tiếp không phải điều kiện bắt buộc để học

Không cần cố tình dừng primary, ngắt network, làm secondary lag hoặc cưỡng bức write concern timeout để hiểu quy tắc:

- `wtimeout` **không undo**.
- Network error sau khi gửi lệnh có thể có kết quả chưa rõ.
- Duplicate key là write error cho thao tác cụ thể.
- Bulk operation có thể thành công một phần.
- Đối soát bằng business key/idempotency giúp phục hồi.

Thực hành mô phỏng bằng bảng tình huống thường an toàn và có ích hơn việc gây failover thật trên một cluster đang phục vụ người dùng.

## 17. Một bảng quyết định khi exception xảy ra

| Loại tình huống | Trạng thái tác động ghi có thể biết? | Hướng xử lý |
|---|---|---|
| Client-side validation từ chối trước khi gửi | Có thể biết chưa gửi nếu logic chắc chắn chưa gửi | Sửa request, không retry nguyên payload vô ích |
| Duplicate key khi `insertOne` | Insert đó bị từ chối | Đọc theo business key, kiểm tra payload, trả conflict hoặc đã xử lý |
| Validation/write error với một thao tác | Thao tác đó không hoàn tất theo ràng buộc | Sửa dữ liệu/lệnh; với bulk xem từng phần tử |
| `writeConcernError`/`wtimeout` | Tác động có thể đã xảy ra; xác nhận chưa đủ | Giữ ID, đối soát và retry an toàn theo thiết kế |
| Network reset sau khi gửi | Không chắc lệnh đã thực thi chưa | Dựa vào retryable writes, idempotency, đối soát |
| Driver có `NoWritesPerformed` hợp lệ | Có bằng chứng cụ thể các lần thử retryable liên quan chưa ghi | Có thể quyết định retry theo quy tắc nghiệp vụ |
| Bulk write lỗi ở phần tử N | Các phần tử khác có thể đã được áp dụng | Xem writeErrors, upserts, counts và đối soát |
| `UnknownTransactionCommitResult` | Commit chưa được xác nhận chắc chắn | Retry commit/đối soát đúng protocol, không lập tức chạy body mới |
| Primary failover sau `w: 1` thành công | Ghi có thể chưa được majority-committed | Xác định yêu cầu durability và trạng thái sau failover |
| Không tìm thấy record khi đọc secondary | Có thể do replication lag | Đọc bằng chính sách phù hợp, không kết luận sớm |

### 17.1. Không trả HTTP 500 kèm thông điệp dễ gây ghi trùng

Nếu API đặt hàng nhận kết quả không rõ, phản hồi:

> “Không thể xác nhận trạng thái yêu cầu. Vui lòng kiểm tra đơn bằng mã yêu cầu.”

có thể an toàn hơn:

> “Đặt hàng thất bại. Hãy bấm Đặt hàng lần nữa để tạo yêu cầu mới.”

Thiết kế thực tế còn cần quy định mã HTTP, idempotency key, thời gian tra cứu và trạng thái pending, nhưng mục tiêu là **không khuyến khích người dùng tạo thêm thao tác nghiệp vụ khi hệ thống chưa biết trạng thái cũ**.

### 17.2. Không dùng mỗi mã lỗi HTTP làm sự thật dữ liệu

Một API Gateway có thể timeout sau khi service ghi vào MongoDB. HTTP 504 nói rằng gateway **không nhận phản hồi kịp thời**, chứ không phải MongoDB khẳng định insert chưa diễn ra.

Tương tự, client có thể bỏ kết nối HTTP trong khi backend vẫn tiếp tục công việc. Cần ràng buộc trạng thái nghiệp vụ bằng ID xuyên từ frontend qua service tới database và hệ thống downstream.

## 18. Ghi log và đối soát trong production

### 18.1. Metadata nên lưu

Khi gặp lỗi ghi mơ hồ, log kỹ thuật có thể gồm:

```javascript
{
  requestId: "REQ-ORDER-2026-0001",
  operation: "createOrder",
  collection: "orderRequests",
  database: "app",
  writeConcern: { w: "majority", wtimeout: 5000 },
  errorCategory: "WRITE_CONCERN_TIMEOUT",
  errorLabels: [],
  attempt: 1,
  observedState: "UNKNOWN",
  timestamp: ISODate("2026-11-14T10:00:00Z")
}
```

Đây là **ví dụ log do ứng dụng tự thiết kế**, không phải schema MongoDB tự tạo.

Không ghi mật khẩu, token, số thẻ, dữ liệu cá nhân nhạy cảm hoặc nội dung payload đầy đủ không cần thiết. Có thể dùng hash/checksum payload đã chuẩn hóa để hỗ trợ kiểm tra request lặp, nhưng cần bảo vệ và kiểm soát collision/encoding theo yêu cầu hệ thống.

### 18.2. Tạo trạng thái riêng cho yêu cầu chưa kết luận

Một workflow có thể dùng:

```text
RECEIVED
   |
   v
PROCESSING
   |           \
   v            v
COMPLETED     UNKNOWN_OUTCOME
   |              |
   |              v
   |        RECONCILING
   |         /        \
   v        v          v
HOÀN TẤT  COMPLETED   REJECTED/NEEDS_REVIEW
```

Không phải mọi ứng dụng cần nhiều trạng thái như trên. Tuy nhiên, khi thao tác có **tác động tài chính hoặc không thể hoàn tác dễ dàng**, trạng thái “chưa rõ” thường quan trọng hơn việc ép toàn bộ lỗi thành “thất bại”.

### 18.3. Tự động đối soát

Một job đối soát có thể:

1. Tìm các request ở trạng thái `UNKNOWN_OUTCOME`.
2. Đọc theo `requestId` từ nguồn có thẩm quyền.
3. Xác minh payload và state machine.
4. Nếu đã hoàn tất, đánh dấu `COMPLETED`.
5. Nếu chắc chắn bị từ chối, đánh dấu `REJECTED`.
6. Nếu chưa đủ bằng chứng, giữ pending/tiếp tục retry an toàn theo deadline và chính sách.

Không coi “chưa thấy bản ghi trong lần đọc đầu tiên” là đủ để phát lại một thao tác cộng/trừ tiền bằng **ID mới**.

### 18.4. Metrics vận hành cần quan sát

| Metric/dấu hiệu | Câu hỏi |
|---|---|
| Tần suất `writeConcernError` | Có thiếu khả năng xác nhận ghi theo mục tiêu? |
| Số lần `wtimeout` | Secondary lag, majority không sẵn hay yêu cầu quá chặt so với hạ tầng? |
| Network timeouts | Mạng, connection pool, server selection hoặc tải server có vấn đề? |
| Retryable write errors | Có failover hoặc lỗi kết nối thường xuyên? |
| Độ trễ replication | Secondary có theo kịp primary không? |
| Số request `UNKNOWN_OUTCOME` | Có nhiều nghiệp vụ chưa được đối soát không? |
| Tỷ lệ duplicate business key | Client có retry bằng ID ổn định hay đang gửi trùng? |
| Transaction commit retries | Có nhiều commit không được xác nhận rõ? |
| Replica set elections | Có primary chuyển vai trò quá thường xuyên? |

Metrics cần được gắn với thời gian và topology. Một spike timeout khi bầu primary khác với timeout tăng do một truy vấn lâu hoặc tài nguyên đĩa bị nghẽn.

## 19. Bốn quy tắc quan trọng về nhất quán đọc/ghi

### 19.1. Xác nhận ghi không đồng nghĩa mọi bản sao đều đã cập nhật

`w: 1` thành công không đảm bảo mọi secondary đã có dữ liệu. Ngay cả với `w: "majority"`, không cần mọi secondary đều đồng bộ tại cùng một mili-giây.

### 19.2. Đọc từ secondary có thể không thấy ghi mới

Một lần đọc secondary không thấy document **không phủ định** write acknowledgment đã nhận từ primary. Muốn bảo đảm “đọc sau khi ghi thấy dữ liệu” trong một workflow, cần chọn read preference, read concern và session/causal-consistency đúng với yêu cầu.

### 19.3. `wtimeout` là thất bại đạt yêu cầu xác nhận, không phải lệnh rollback

Server có thể áp dụng ghi tại primary nhưng chưa đủ điều kiện đáp ứng `w: "majority"`. Sau timeout, ghi có thể tiếp tục được sao chép hoặc bị ảnh hưởng bởi failover. Trạng thái cần được đánh giá bằng thông tin bổ sung.

### 19.4. “Không biết kết quả” là trạng thái hợp lệ trong hệ thống phân tán

Nếu response mất sau khi gửi command, hệ thống không thể luôn trả lời chắc chắn “đã ghi” hay “chưa ghi” chỉ bằng một exception. **Retryable writes, khóa định danh ổn định, đối soát và state machine** là những công cụ để ứng dụng đi tới kết quả nghiệp vụ đáng tin cậy.

## 20. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| Insert báo timeout nghĩa chưa được insert | Timeout có thể xảy ra sau khi server đã xử lý |
| `wtimeout` là thời gian hủy write operation | Nó giới hạn chờ mức write concern |
| `writeConcernError` là `writeError` | Một bên là mức xác nhận, một bên là lỗi áp dụng thao tác |
| Mọi exception trong driver đều đồng nghĩa không có side effect | Lỗi mạng và commit có thể để kết quả mơ hồ |
| `w: 1` thành công thì sẽ không rollback | Dữ liệu chưa majority-committed có thể gặp rủi ro khi failover |
| `w: "majority"` thành công nghĩa tất cả secondary đã có dữ liệu | Chỉ cần điều kiện majority theo deployment |
| `acknowledged: false` chứng minh ghi thất bại | Với `w: 0`, client chủ đích không nhận xác nhận |
| Bắt duplicate key thì cứ báo success | Cần kiểm tra business key, payload và trạng thái |
| `$inc` có thể retry bằng lệnh mới bao nhiêu lần cũng được | Có thể nhân đôi tác động khi thao tác trước đã áp dụng |
| Driver bật retry là toàn nghiệp vụ exactly-once | Cơ chế chỉ áp dụng cho thao tác đủ điều kiện, không tự bảo vệ side effect khác |
| `NoWritesPerformed` xuất hiện ở mọi lỗi chưa ghi | Là error label chuyên biệt, có điều kiện và giới hạn phiên bản |
| Không có `NoWritesPerformed` thì chắc chắn đã ghi | Không có label không đưa ra kết luận khẳng định |
| Đọc secondary không thấy record nghĩa insert trước thất bại | Secondary có thể bị replication lag |
| Read majority không thấy record chứng minh lệnh chưa từng chạy | Chỉ phản ánh điều đang quan sát với mức read concern đã chọn |
| Lỗi bulk nghĩa cả batch chưa ghi gì | Bulk có thể thành công một phần |
| Transaction luôn cho client biết chắc commit có thành công không | Phản hồi commit có thể bị mất |
| Commit không rõ thì chạy lại toàn bộ nghiệp vụ mới | Cần retry commit/đối soát theo protocol |
| HTTP 504 nghĩa backend/MongoDB chưa thực hiện yêu cầu | Gateway có thể hết thời gian chờ sau khi backend đã ghi |
| Mọi thao tác `$set` đều idempotent toàn bộ | Side effect, timestamp hoặc workflow khác có thể không idempotent |

## 21. Bài tập thực hành

### Bài 1 — Phân loại tín hiệu lỗi

Cho năm tình huống:

1. `insertOne()` trả success với `w: 1`.
2. `insertOne()` trả success với `w: "majority"`.
3. `insertOne()` bị duplicate key.
4. `updateOne()` đã chạy trên primary nhưng gặp `writeConcernError` do `wtimeout`.
5. Client bị socket reset ngay sau khi gửi `updateOne()`.

Hãy viết rõ:

- Điều gì đã biết?
- Điều gì **chưa** thể kết luận?
- Có được phép tự phát lại cùng nghiệp vụ bằng ID mới không?

### Bài 2 — Dự đoán một lệnh `$inc` bị retry

Tài khoản có `balance: 1000`. Ứng dụng gửi:

```javascript
db.accounts.updateOne(
  { accountId: "A01" },
  { $inc: { balance: -100 } }
);
```

Client timeout sau khi gửi. Một đoạn code tạo một lệnh mới tương tự và gửi lại. Hãy liệt kê những giá trị số dư có thể quan sát được trong các kịch bản **không có thao tác khác** và điều kiện giả định cụ thể.

Vì sao không thể suy ra số dư cuối từ đúng một exception network? Đề xuất cách dùng `operationId`, ledger và ranh giới atomicity để làm workflow đáng tin cậy.

### Bài 3 — Duplicate key sau timeout

Client tạo:

```javascript
{
  _id: "order:REQ-10",
  requestId: "REQ-10",
  customerId: "C01",
  total: 200000
}
```

Lần đầu gặp timeout. Lần hai insert cùng key thì nhận duplicate key.

1. Có thể khẳng định lần đầu đã ghi đúng payload không?
2. Cần đọc document theo key nào?
3. Nếu document tồn tại nhưng `total: 500000` thì sao?
4. Nếu document tồn tại đúng payload, còn status là `PROCESSING` thì API nên phản hồi thế nào?

### Bài 4 — `wtimeout` và replica set

Giả sử replica set có ba data-bearing members, primary nhận lệnh ghi yêu cầu majority. Secondary tạm thời bị lag khiến điều kiện xác nhận chưa đạt trước `wtimeout`.

Hãy giải thích:

- Primary có thể đã áp dụng ghi chưa?
- Server có phải undo ghi khi hết hạn không?
- Ghi có thể đạt majority sau khi client đã nhận lỗi không?
- Nếu primary gặp sự cố trước khi đạt majority thì sao?
- Thông tin nào cần dùng trước khi kết luận đơn hàng đã được xác nhận?

### Bài 5 — `w: 0` và tính quan sát

Một ứng dụng gửi thao tác quan trọng với `w: 0`, sau đó API trả success vì không có exception.

Tại sao cách xử lý này có vấn đề? `acknowledged: false` có nghĩa là server khẳng định lệnh không thực thi không? Với nghiệp vụ thanh toán, nên chọn cách thiết kế xác nhận nào?

### Bài 6 — Ordered bulk có lỗi giữa chừng

Trong collection rỗng:

```javascript
db.bulkAckDemo.bulkWrite(
  [
    { insertOne: { document: { _id: "X" } } },
    { insertOne: { document: { _id: "X" } } },
    { insertOne: { document: { _id: "Y" } } }
  ],
  { ordered: true }
);
```

Hãy dự đoán:

- Thao tác nào thành công?
- Thao tác nào lỗi?
- Thao tác nào thường không được thử trong ordered bulk?
- Vì sao exception của toàn bulk không có nghĩa collection vẫn rỗng?

Sau đó phân tích sự khác biệt khi `ordered: false`.

### Bài 7 — Đọc sau khi ghi

Một ứng dụng nhận kết quả insert thành công với `w: 1` từ primary, nhưng đọc ngay sau đó từ secondary không thấy document.

1. Đây có nhất thiết là lỗi ghi không?
2. Replication lag ảnh hưởng thế nào?
3. Đọc từ primary khác gì đọc từ secondary?
4. Khi nào nên cân nhắc read concern majority, write concern majority và causal consistency?
5. Một lần đọc majority không thấy document có phải bằng chứng rằng thao tác trước chưa bao giờ chạy không?

### Bài 8 — Hai loại timeout

Phân biệt:

- Server selection timeout **trước khi chọn được server và chưa gửi command**.
- Socket timeout **sau khi gửi command**.
- Write concern `wtimeout` **sau khi server đã xử lý ghi nhưng chưa đáp ứng mức xác nhận**.

Trong mỗi trường hợp, chỉ ra mức độ chắc chắn của client về tác động dữ liệu và những dữ kiện bổ sung cần có.

### Bài 9 — Transaction commit outcome

Một transaction gồm trừ A, cộng B và ghi ledger. Server nhận `commitTransaction`, commit thành công, nhưng phản hồi bị ngắt.

- Client có được khẳng định transaction đã thất bại không?
- Có nên tạo transaction mới và chạy lại toàn bộ chuyển tiền không?
- `UnknownTransactionCommitResult` hướng tới cách xử lý nào?
- Vì sao email thông báo hoặc gọi cổng thanh toán ngoài MongoDB vẫn cần idempotency/outbox?

### Bài 10 — Thiết kế API idempotent

Một endpoint `POST /orders` cho phép client truyền header `Idempotency-Key`.

Hãy thiết kế:

1. Cách tạo và lưu key cho một hành động đặt hàng.
2. Unique index và trường dữ liệu cần kiểm tra.
3. Kết quả khi lần đầu thành công nhưng response bị mất.
4. Kết quả khi client retry với cùng key, cùng payload.
5. Kết quả khi client retry cùng key, **payload khác**.
6. Trạng thái API khi write concern chưa xác nhận.
7. Quy trình đối soát khi không thể đọc dữ liệu ngay lập tức.

Giải thích vì sao chỉ bắt duplicate key rồi trả HTTP 200 cho mọi trường hợp không phải là thiết kế đúng.

### Bài 11 — Đánh giá một đoạn Java

Đoạn code:

```java
try {
    collection.insertOne(order);
    return "SUCCESS";
} catch (MongoException e) {
    return "NOT_WRITTEN";
}
```

Hãy chỉ ra:

- Những loại exception nào khiến tên `NOT_WRITTEN` có thể sai?
- Cần bổ sung business key/idempotency ở đâu?
- Khi nào có thể phân loại là `REJECTED`?
- Khi nào nên trả `UNKNOWN_OUTCOME`?
- Vì sao không tự loop retry vô hạn khi gặp mọi `MongoException`?

### Bài 12 — Diễn tập kịch bản sự cố

Cho timeline:

```text
10:00:00 Client gửi tạo order REQ-77
10:00:01 Primary thực thi insert
10:00:02 Write concern majority chưa được đáp ứng
10:00:03 Client nhận write concern timeout
10:00:04 Secondary theo kịp
10:00:05 Client tạo REQ-78 để "thử lại"
10:00:06 Primary thực thi REQ-78
```

Hãy xác định bước nào tạo rủi ro hai đơn hàng, và viết lại timeline an toàn hơn bằng **cùng requestId** và bước đối soát. Sau đó xét tình huống primary failover ngay trước 10:00:04 và mô tả vì sao không thể tự suy ra kết cục từ timeout lúc 10:00:03.

## 22. Quy trình thực tế để ra quyết định sau lỗi ghi

Để tránh sai lầm trong ứng dụng thật, hãy đi qua các câu hỏi theo thứ tự:

1. **Thao tác gì?** `insertOne`, `updateOne`, `$inc`, bulk write hay transaction?
2. **Có ID nghiệp vụ ổn định không?** Nếu chưa có, cần thiết kế để không tạo trùng khi retry.
3. **Lỗi thuộc nhóm nào?** Lỗi áp dụng ghi, write concern, mạng, server selection hay uncertain commit?
4. **Driver đã retry tự động chưa?** Có error label gì, có `NoWritesPerformed` đáng tin cậy không?
5. **Write concern yêu cầu là gì?** `w: 1`, majority, journaling, timeout?
6. **Nếu cần đọc lại, đọc ở đâu và với mức nhất quán nào?** Không chọn secondary lag rồi kết luận vội.
7. **Record hiện có có đúng request và payload không?** Duplicate key không tự thành success.
8. **Retry có thể nhân đôi side effect không?** Đặc biệt với `$inc`, phát sự kiện, gọi thanh toán hoặc email.
9. **Nếu chưa đủ thông tin, có trạng thái UNKNOWN không?** Hệ thống cần có cách hẹn kiểm tra/đối soát.
10. **Có log và quy trình phục hồi không?** Để xử lý khi client và server bị tách kết nối lâu.

Đây là quy trình phân loại và vận hành, **không phải công thức buộc mọi trường hợp phải retry hoặc mọi trường hợp phải đọc lại đúng một lần**. Thiết kế cuối cùng còn phụ thuộc mức quan trọng của dữ liệu, khả năng chịu lỗi, SLA, topology và phiên bản driver/server.

## 23. Tổng kết

**Lỗi xác nhận và lỗi thực thi ghi là hai khái niệm khác nhau.** Một `writeError` có thể cho biết thao tác cụ thể bị từ chối; một `writeConcernError` hoặc `wtimeout` cho biết yêu cầu xác nhận chưa đạt, **không có nghĩa thao tác đã được hoàn tác**. Lỗi mạng sau khi gửi command có thể khiến client **không biết** kết quả thực.

**Write concern là một phần của hợp đồng độ bền.** `w: 1` không tương đương `w: "majority"`; `j` không thay thế replication; timeout phía client không phải nút undo của server. Một thao tác đã được primary xác nhận nhưng chưa majority-committed có thể có rủi ro khi failover.

**Retry cần định danh ổn định và ranh giới rõ ràng.** Driver retryable writes giúp giảm nguy cơ thực hiện lại một số thao tác được hỗ trợ, nhưng không tự bảo đảm exactly-once cho toàn bộ nghiệp vụ. `$inc`, bulk write, transaction commit và side effect ngoài MongoDB cần chính sách riêng.

**Đối soát quan trọng hơn suy đoán.** Dùng `requestId`/`operationId` duy nhất, kiểm tra payload và trạng thái, đọc với read concern/read preference phù hợp, ghi nhận lỗi và hỗ trợ trạng thái `UNKNOWN_OUTCOME` khi cần. Nếu chưa đủ bằng chứng để nói “đã ghi” hoặc “chưa ghi”, hãy giữ kết quả **chưa xác định** thay vì phát một thao tác nghiệp vụ mới có thể gây trùng.

Tư duy then chốt của chương **Nhất quán đọc ghi** là: **thao tác đã diễn ra**, **mức xác nhận đạt được** và **điều client biết chắc** là ba vấn đề khác nhau. Phân biệt chúng là nền tảng để xây hệ thống MongoDB an toàn trước timeout, failover và retry.

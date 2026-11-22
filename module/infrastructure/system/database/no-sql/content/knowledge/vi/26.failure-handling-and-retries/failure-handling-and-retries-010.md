# Hủy yêu cầu phía ứng dụng và công việc vẫn tiếp tục trên máy chủ trong NoSQL

## 1. Tình huống mở đầu: nút “Hủy” không hoàn tác giao dịch đã ghi

Người dùng mở ứng dụng đặt vé, bấm **Thanh toán**, sau đó thấy màn hình tải quá lâu và nhấn **Hủy**. Giao diện đóng hộp thoại, request HTTP bị hủy ở trình duyệt. Vài giây sau, người dùng nhận thông báo đã đặt vé thành công.

Nhìn từ phía người dùng, thao tác này có vẻ mâu thuẫn:

- “Tôi đã bấm hủy, tại sao vẫn trừ tiền?”
- “Trình duyệt báo request bị hủy, có nghĩa database đã rollback chưa?”
- “Nếu gửi lại một yêu cầu mới, tôi có bị thanh toán hai lần không?”

Nhìn từ phía hệ thống, các sự kiện có thể diễn ra như sau:

```text
  Browser            API Server             NoSQL Database       Payment/Worker
     |                    |                        |                    |
     | POST /checkout     |                        |                    |
     |------------------->|                        |                    |
     |                    | Reserve order          |                    |
     |                    |----------------------->|                    |
     |                    |       COMMITTED        |                    |
     |                    |<-----------------------|                    |
     |                    | Publish/dispatch work  |                    |
     |                    |-------------------------------------------->|
     | Click CANCEL       |                        |                    |
     X  HTTP connection   |                        |                    |
     |                    |                        |              charge succeeds
     |                    |                        |                    |
     |     response cannot be delivered           |                    |
     |                    |                        |                    |
```

**Hủy request ở client không đồng nghĩa hủy công việc đã nhận trên server; hủy server task không đồng nghĩa rollback write đã commit; rollback database không tự hoàn tác side effect ngoài database.**

Đây là một vấn đề cốt lõi của chương **Lỗi phân tán và retry** trong NoSQL. Với hệ có nhiều lớp như browser, API gateway, application server, database cluster, message broker và worker, việc một lớp tuyên bố **“canceled”** chỉ có ý nghĩa trong **phạm vi của lớp đó**.

Mục tiêu của bài học là phân biệt các kiểu hủy, phân tích kết quả ghi không xác định, thiết kế API cancellation có ngữ nghĩa rõ ràng và bảo vệ nghiệp vụ khỏi ghi trùng, mất tiền, xóa nhầm hoặc phản hồi sai khi request bị ngắt giữa chừng.

## 2. Năm khái niệm thường bị gọi chung là “hủy”

| Khái niệm | Điều thực sự xảy ra | Điều **không** được suy ra |
|---|---|---|
| **Client-side cancellation** | UI/SDK ngừng chờ hoặc ngừng xử lý response | Server đã dừng thực hiện |
| **Transport cancellation/disconnect** | Kết nối HTTP/TCP hoặc RPC stream bị đóng/hủy | Database command chưa commit |
| **Deadline/timeout** | Một tầng quyết định đã chờ quá lâu | Operation chắc chắn thất bại hoặc đã rollback |
| **Server-side cooperative cancellation** | Server đánh dấu yêu cầu dừng; code/driver/engine có thể nhận biết | Mọi bước và side effect đều được đảo ngược |
| **Transaction abort/rollback** | Transaction chưa commit được hủy theo hợp đồng database | Email, tiền, event, call bên ngoài đều được hoàn tác |
| **Compensation** | Tạo hành động nghiệp vụ mới để bù lại kết quả đã xảy ra | Lịch sử như chưa từng có thao tác |

Một hệ có thể hỗ trợ vài loại trong bảng nhưng không hỗ trợ các loại khác. Ví dụ thư viện Java hủy `CompletableFuture`, API server có thể nhận tín hiệu disconnect, MongoDB driver có thể hủy một số operation, nhưng message đã phát sang queue vẫn đang chờ worker tiêu thụ.

### Câu hỏi cần hỏi mỗi khi thấy chữ “cancel”

1. **Ai yêu cầu hủy?** Browser, API gateway, job scheduler, operator hay database?
2. **Cái gì bị hủy?** Việc đợi kết quả, network request, query đang chạy, transaction chưa commit, job dài hạn hay quyết định nghiệp vụ?
3. **Hủy đến được tầng nào?** Chỉ UI, application handler, DB driver, database server, broker hay external provider?
4. **Hủy là best-effort hay có cam kết?** Tín hiệu có thể đến muộn, bị mất hoặc operation đã đi qua điểm không thể dừng.
5. **Một ACK thành công đã được trả chưa?** Nếu đã commit, cancellation không được giả làm rollback.
6. **Client xác minh kết quả thế nào?** Trạng thái job, idempotency key, transaction ID, committed version hay ledger?

Nhiều lỗi xuất hiện vì hệ thống trả lời những câu hỏi này bằng **một biến Boolean `cancelled=true`** mà không chỉ rõ phạm vi.

## 3. Một request có nhiều vòng đời khác nhau

Một thao tác tạo đơn có ít nhất bốn vòng đời:

```text
Client request life:
  CREATED -> SENT -> WAITING -> COMPLETED / CANCELED / TIMED_OUT

Application handler life:
  RECEIVED -> VALIDATED -> EXECUTING -> RESPONDING / FAILED

Database operation life:
  NOT_SENT -> RUNNING -> COMMITTED / ABORTED / UNKNOWN

Background job life:
  ENQUEUED -> CLAIMED -> EXECUTING -> SUCCEEDED / FAILED / CANCELED
```

Các vòng đời **không chuyển trạng thái cùng một lúc**.

Ví dụ:

```text
Client:       CANCELED
API handler:  EXECUTING
Database:     COMMITTED
Background:   ENQUEUED
```

Đây không phải trạng thái bất khả thi. Nó mô tả đúng hiện tượng “người dùng đã hủy màn hình, máy chủ vẫn làm việc”.

### Một bảng sự kiện có thể xảy ra

| Thời điểm người dùng hủy | Điều server có thể đã làm | Kết quả hợp lệ cần tính đến |
|---|---|---|
| Trước khi gửi request | Chưa có request nào tới server | Không có thao tác server **nếu xác minh chắc chưa gửi** |
| Sau khi gửi, trước khi server nhận | Message có thể đang trên mạng | Server có thể nhận sau khi client đã hủy |
| Trong khi handler đang chạy | Query/worker có thể chưa nhận tín hiệu | Handler vẫn có thể tiếp tục |
| Sau khi write được commit | Dữ liệu đã có hiệu lực | Cần xác minh hoặc bù trừ, không gọi là rollback |
| Sau khi event được ghi/publish | Worker khác có thể chạy | Hủy HTTP không xóa event đã được chấp nhận |
| Sau khi payment provider nhận lệnh | Provider có thể charge | Phải dùng provider idempotency/status/refund semantics |
| Trong lúc server đang gửi response | Client không nhận được ACK | Outcome của operation có thể **không rõ với client** |

Thời điểm nhấn “Hủy” trên UI chỉ là một điểm trên timeline của **một participant**. Nó không tự định nghĩa thứ tự của các sự kiện đã diễn ra ở database và các participant khác.

## 4. Vì sao client không biết server đã commit hay chưa?

Xét hai thế giới:

**Thế giới A:**

```text
Client -> Server: UPDATE order to SUBMITTED
Network drops request before server receives it
Client: TIMEOUT/CANCELED
Database: no write
```

**Thế giới B:**

```text
Client -> Server: UPDATE order to SUBMITTED
Server -> Database: COMMIT SUCCESS
Server -> Client: response gets lost
Client: TIMEOUT/CANCELED
Database: order is SUBMITTED
```

Client trong cả hai thế giới đều có thể chỉ quan sát:

```text
Request did not complete from my perspective.
```

Nhưng database có trạng thái khác nhau. **Từ việc không nhận response, client không thể phân biệt một cách đáng tin cậy hai thế giới này** nếu không có thêm bằng chứng.

Đây là nền tảng của **unknown commit outcome**, **ambiguous result** hay **uncertain result** trong hệ phân tán.

### Ba trạng thái không thể gộp

- **Known committed:** có xác nhận hợp lệ về commit theo hợp đồng cần thiết.
- **Known not committed:** có bằng chứng đáng tin rằng thao tác không thể đã commit (ví dụ bị từ chối trước bước ghi theo protocol được tài liệu xác nhận).
- **Unknown:** request có thể đã commit hoặc chưa; timeout/disconnect không đủ để chọn một trong hai.

**Chỉ khi có điều kiện không-commit rõ ràng, ứng dụng mới được coi retry như một attempt hoàn toàn mới**. Trong trường hợp unknown, phải giữ identity của logical operation để có thể tra cứu và tránh duplicate.

## 5. Hủy phía client chỉ là sự kiện của một process

Trong trình duyệt, một fetch có thể được hủy bằng `AbortController`:

```javascript
const controller = new AbortController();

async function submitOrder(orderId, requestId) {
  const response = await fetch("/api/orders/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ orderId, requestId }),
    signal: controller.signal
  });

  if (!response.ok) throw new Error("Submit failed");
  return response.json();
}

// User clicks "Cancel":
controller.abort();
```

Lệnh `abort()` có thể dừng fetch và làm Promise liên quan bị reject tại client. Tuy nhiên:

- Request đã có thể đi qua network và tới server.
- Handler trên server có thể đang gọi database.
- Database có thể đã commit.
- Broker có thể đã nhận event.
- Server không nhất thiết có cách hoàn tác mọi việc sau khi client ngừng chờ.

Vì vậy trong UI, không nên hiển thị ngay **“Đơn đã được hủy thành công”** chỉ vì `fetch` bị abort. Với thao tác tạo hiệu ứng nghiệp vụ, thông báo đúng có thể là:

> “Đã ngừng chờ phản hồi. Trạng thái gửi đơn đang được xác minh.”

Sau đó ứng dụng gọi endpoint kiểm tra bằng `requestId` hoặc `orderId` theo read semantics phù hợp.

### Hủy thao tác đọc thuần khác hủy thao tác ghi

Với một request **đọc dữ liệu**, hủy phía client thường không có tác động thay đổi nghiệp vụ, nhưng server vẫn có thể lãng phí CPU, I/O và network cho query không còn người nhận.

Với một request **ghi**, vấn đề không chỉ là tốn tài nguyên: nếu client lầm tưởng “cancel = thất bại” rồi gửi lại bằng ID mới, có thể tạo **hai đơn, hai lần cộng điểm hoặc hai lần charge**.

## 6. HTTP disconnect không phải transaction rollback

Một HTTP server có thể phát hiện:

- Client đã đóng kết nối.
- Context/aborted signal gắn với request đã bị hủy.
- Ghi response thất bại vì socket không còn.
- Reverse proxy đã đóng upstream request.

Nhưng một handler có thể đã tách công việc ra khỏi lifecycle của HTTP:

```text
HTTP request
    |
    +--> validate
    +--> persist job record
    +--> enqueue task
    +--> return response

Worker process
    |
    +--> consume task
    +--> write database
    +--> call external provider
```

Ngay cả khi HTTP request bị hủy sau khi job đã được chấp nhận, worker vẫn có thể tiếp tục vì nó có **vòng đời riêng**.

### Điều server có thể làm khi nhận disconnect

Nếu operation chưa gây hiệu ứng không thể đảo ngược:

- Ngừng tính toán không cần thiết.
- Dừng đọc thêm dữ liệu.
- Dừng phát các request downstream chưa cần thiết.
- Gửi cancellation tới driver/query engine nếu được hỗ trợ.
- Đóng tài nguyên sau khi biết không còn cần.

Nếu operation đã commit hoặc đã dispatch công việc bền:

- Ghi trạng thái đã commit/chấp nhận.
- Cho client tra cứu kết quả khi reconnect.
- Nếu nghiệp vụ cho phép, nhận **một cancellation request riêng** có state machine và điểm không thể hủy.
- Không sửa lịch sử thành “chưa từng gửi” chỉ để khớp trạng thái UI.

### HTTP 499 không phải một bằng chứng từ database

Một số reverse proxy dùng mã **499** trong access log để biểu thị client đã đóng kết nối trước khi server trả response. Đây là chỉ số ở **proxy/transport layer**, không phải mã trạng thái HTTP tiêu chuẩn do mọi server dùng và **không chứng minh database đã abort**.

Khi điều tra, cần correlate `requestId` từ proxy → service → database/queue/worker, thay vì chỉ đếm 499.

## 7. Timeout không có cùng ngữ nghĩa ở mọi tầng

Một request có thể gặp nhiều hạn chót:

```text
Browser deadline:           5 seconds
API gateway timeout:        10 seconds
Service request timeout:     8 seconds
Database driver timeout:     6 seconds
Database operation limit:    per-command setting
Background job timeout:      2 minutes
```

Đây là **con số minh họa**. Không có nguyên tắc nào nói browser timeout 5 giây sẽ buộc mọi tầng tự động dừng sau 5 giây.

### Các loại timeout cần phân biệt

| Loại | Ví dụ | Phạm vi |
|---|---|---|
| Connection timeout | Không kết nối được DB | Có thể chưa gửi operation |
| Socket/read timeout | Không nhận response trong giới hạn | Operation server có thể vẫn chạy/đã commit |
| Client-side future timeout | Caller ngừng chờ | Không tự dừng runnable/remote operation |
| RPC deadline | Tín hiệu deadline truyền theo RPC | Server cần hợp tác để dừng |
| Server execution time limit | DB engine giới hạn một lệnh hỗ trợ | Không tự hoàn tác side effect đã commit |
| Transaction timeout | Transaction vượt giới hạn được engine áp | Phải đọc commit/abort semantics cụ thể |
| Worker lease timeout | Worker mất quyền sở hữu một job | Worker cũ có thể vẫn đang chạy nếu không fencing |

### Cấu hình deadline theo ngân sách

Nếu service muốn trả lời trong 3 giây, có thể đặt ngân sách:

```text
Total service deadline: 3000 ms
  Authentication:        100 ms
  DB command:           1200 ms
  External provider:    1000 ms
  Response/network:      200 ms
  Retry/overhead buffer: 500 ms
```

Các giá trị chỉ minh họa. Cần dùng **deadline tuyệt đối hoặc remaining budget** để tránh mỗi downstream call được cấp lại toàn bộ 3 giây, dẫn đến tổng thời gian tăng quá mức.

Tuy nhiên truyền deadline chỉ giúp các tầng **có cơ hội** ngừng công việc. Nó **không tạo rollback phân tán** cho những điều đã commit.

## 8. Deadline propagation và cooperative cancellation

Trong RPC như gRPC, caller có thể gắn **deadline** và cancel một call. Server có thể được thông báo và biết deadline đã hết. Nhưng server handler phải hợp tác:

```text
Client deadline expired
       |
       v
RPC cancellation signal
       |
       v
Service handler checks cancellation
       |
       +--> before commit: may stop safely
       |
       +--> after commit: must report/record committed outcome
```

Một handler dài có thể:

- Kiểm tra flag cancellation giữa các batch.
- Không tạo thêm downstream requests.
- Cancel query đang chạy qua API được hỗ trợ.
- Release tài nguyên không còn cần.
- **Không** tự gọi một bước “rollback” không có quyền đảo ngược external provider.

### Deadline đã hết nhưng service vẫn đang chạy

Nếu handler không kiểm tra context hoặc gọi một thư viện blocking không nhận cancellation, công việc vẫn có thể chạy cho tới khi hoàn tất. Một số client libraries cố gửi cancellation ở tầng transport nhưng server/database chưa chắc xử lý ngay hoặc theo semantics mong muốn.

**Cooperative cancellation** có nghĩa là cần sự hợp tác và có thể bị trì hoãn; nó không phải cơ chế “kill đúng lập tức trên mọi máy”.

### Cancellation boundary

Nên xác định một điểm:

```text
PREPARE -> CHECK CANCEL -> COMMIT/IRREVERSIBLE STEP -> COMPLETE
                         ^
                 last safe cancellation boundary
```

Nếu nghiệp vụ không cho phép hủy sau khi thanh toán đã xác nhận, API phải nói rõ **hủy trước hay sau ranh giới nào**. “Cancellation requested” không tự bằng “cancellation completed”.

## 9. Transaction abort khi đang thực thi khác cancel sau commit

Một transaction database có thể có lifecycle:

```text
STARTED -> OPERATIONS -> PREPARING -> COMMITTING -> COMMITTED
           |                  |
           +------ ABORT -----+
```

Trước khi commit, engine có thể cho phép **abort transaction** theo API và điều kiện phù hợp. Sau khi transaction đã commit, không thể biến một request cancellation đến muộn thành “transaction chưa từng xảy ra”.

### Kịch bản hủy trước commit

```text
T0 Begin transaction
T1 Update order status
T2 Cancellation received
T3 Abort transaction
T4 Status remains unchanged
```

Nếu các update thực sự nằm trong cùng transaction và abort thành công theo hợp đồng engine, trạng thái commit của chúng bị hủy.

### Kịch bản hủy sau commit

```text
T0 Begin transaction
T1 Update order status
T2 Commit succeeds
T3 Cancellation received
```

Tại T3, nếu yêu cầu nghiệp vụ là “không muốn đơn này nữa”, cần một **operation mới** như `cancelOrder` có điều kiện và theo trạng thái đơn. Đây không phải rollback của transaction cũ.

### Commit đang xử lý, client ngừng chờ

```text
T0 Client sends COMMIT
T1 Database commits
T2 Client cancels connection
T3 ACK not delivered
```

Kết quả ở client là **unknown**, dù database đã commit. Trường hợp này cần **retry commit phù hợp API, kiểm tra ledger/trạng thái, hoặc xác minh bằng transaction ID** theo cơ chế engine; không tự tạo một giao dịch mới có cùng tác dụng.

## 10. Phân biệt abort, undo và compensation

Giả sử người dùng mua vé:

```text
1. Reserve seat in NoSQL
2. Charge card via payment provider
3. Issue electronic ticket
4. Send confirmation email
```

Khi client hủy HTTP sau bước 2:

- Transaction database của bước 1 đã commit.
- Payment provider có thể đã charge.
- Bước 3, 4 có thể tiếp tục trên queue.

Không thể dùng `rollback` của NoSQL để **xóa giao dịch thanh toán tại provider**. Nếu cần hoàn lại, phải có một **refund/cancel operation riêng**, có audit và điều kiện hợp lệ.

| Kỹ thuật | Phạm vi | Có xóa lịch sử effect không? |
|---|---|---|
| DB transaction abort | Những write thuộc transaction chưa commit | Không có committed effect theo semantics DB |
| DB compensating update | Dữ liệu trong DB sau commit | Không; thêm một write mới |
| Payment refund | Giao dịch mới với payment provider | Không; tồn tại charge và refund |
| Event cancellation | Ngăn một số handler tiếp tục nếu chưa xử lý | Không rút lại event đã được xử lý |
| Search index rebuild | Dữ liệu dẫn xuất | Không sửa source transaction |
| Saga compensation | Các bước nghiệp vụ liên service | Tạo hiệu ứng bù trừ, có thể thất bại và cần retry |

**“Cancel transaction”** và **“Cancel business order”** nên là hai API/khái niệm khác nhau để tránh hứa quá mức.

## 11. Khi enqueue xong, request HTTP không còn sở hữu công việc

Một pattern phổ biến:

```text
POST /exports
   |
   +--> persist Job(id=J1, state=QUEUED)
   +--> enqueue J1
   +--> HTTP 202 Accepted

Client disconnects

Worker:
   dequeue J1
   process 1,000,000 records
   upload artifact
   mark J1 SUCCEEDED
```

Trong pattern này, **job được thiết kế để sống độc lập với kết nối HTTP**. Vì vậy client đóng tab hoặc hủy fetch không nên tự làm mất job.

### Muốn hủy job phải có operation riêng

Một API có thể cung cấp:

```text
POST   /exports               -> create job
GET    /exports/{jobId}       -> query state
POST   /exports/{jobId}/cancel -> request cancellation
```

Điểm quan trọng:

- `POST /cancel` là **một yêu cầu thay đổi trạng thái job**.
- Worker phải quan sát yêu cầu hủy và dừng ở ranh giới an toàn.
- API cần phân biệt **đã nhận yêu cầu hủy** và **đã hủy xong**.
- Nếu job đã `SUCCEEDED`, có thể từ chối hủy hoặc tạo workflow đảo ngược riêng.
- Nếu có output artifact hoặc side effect đã tạo, phải định nghĩa việc xóa/thu hồi/compensate.

### HTTP 202 không phải “job thành công”

`202 Accepted` thường có nghĩa request tạo job **đã được chấp nhận để xử lý**, không phải job đã hoàn thành. Nếu job có thể fail, client phải có cách poll, subscribe hoặc nhận callback với trạng thái cuối.

## 12. State machine cho một job có thể hủy

Một trạng thái tham khảo:

```text
                     +---------+
                     | QUEUED  |
                     +----+----+
                          |
                          v
                     +---------+
             +------>| RUNNING |------------------+
             |       +----+----+                  |
             |            |                       v
             |            |                 +-----------+
             |            +---------------->| SUCCEEDED |
             |            |                 +-----------+
             |            v
             |       +------------------+
             |       | CANCEL_REQUESTED |
             |       +--------+---------+
             |                |
             |                v
             |           +----------+
             |           | CANCELED |
             |           +----------+
             |
             +--- retryable FAILED (theo policy)

Terminal states: SUCCEEDED / CANCELED / FAILED_FINAL
```

Sơ đồ chỉ là gợi ý; một workflow thực có thể cần `COMMITTING`, `COMPENSATING`, `CANCEL_NOT_POSSIBLE` hoặc `UNKNOWN_EXTERNAL_OUTCOME`.

### Định nghĩa chuyển trạng thái chính xác

| Từ trạng thái | Yêu cầu | Kết quả có thể |
|---|---|---|
| `QUEUED` | Cancel trước khi worker claim | CAS thành `CANCELED` nếu chắc chưa thực hiện |
| `RUNNING` | Cancel trong lúc xử lý | `CANCEL_REQUESTED`, worker dừng tại checkpoint |
| `COMMITTING` | Cancel sau điểm không thể đảo ngược | Không đảm bảo hủy; có thể `SUCCEEDED` |
| `SUCCEEDED` | Cancel sau khi hoàn tất | Không rollback; yêu cầu operation ngược riêng nếu hỗ trợ |
| `FAILED_FINAL` | Cancel | Có thể trả trạng thái terminal hiện tại |
| `CANCELED` | Cancel lại | Idempotently trả `CANCELED` |

**Đừng chuyển RUNNING trực tiếp thành CANCELED chỉ vì API nhận được nút bấm**, khi worker vẫn đang có thể ghi.

### Invariant quan trọng

\[
\text{status}=\text{CANCELED}
\Rightarrow
\text{không còn worker được phép tạo hiệu ứng mới cho job theo hợp đồng}
\]

Nếu engine không thể bảo đảm ràng buộc này cho external side effect, status cần nghĩa yếu hơn như **“cancel acknowledged / best-effort”**, và không hứa “đã hủy xong” quá sớm.

## 13. Race giữa yêu cầu hủy và bước commit

Xét:

```text
Cancel handler                     Worker
--------------                     ------
Read job: RUNNING
                                   Read job: RUNNING
                                   Check cancel flag = false
Set CANCEL_REQUESTED
                                   Charge payment provider
                                   Mark SUCCEEDED
```

Nếu cancellation handler chỉ ghi flag, worker có thể **vượt qua điểm kiểm tra hủy** ngay trước khi flag được đặt.

### Không sửa bằng cách kiểm tra flag thường xuyên hơn thôi

Kiểm tra flag ngay trước charge giảm cửa sổ race, nhưng vẫn tồn tại:

```text
Worker: CHECK cancel=false
Cancel: SET cancel=true
Worker: CALL provider
```

Để trả lời được **cancel có được chấp nhận hay không**, cần định nghĩa một **atomic decision point**:

1. Worker dùng conditional transition `RUNNING → COMMITTING` tại nguồn có thẩm quyền.
2. Cancellation dùng conditional transition `RUNNING → CANCEL_REQUESTED`.
3. Chỉ một transition thắng nếu các điều kiện xung đột được bảo vệ cùng nguồn/partition/transaction.
4. Nếu worker đã vào `COMMITTING`, hệ có thể từ chối cancel hoặc chuyển sang bù trừ theo hợp đồng.
5. Nếu cancel thắng, worker không được thực hiện bước commit mới theo state machine.

### Nhưng external provider vẫn là một ranh giới khác

Nếu provider call đã phát ra trước khi application ghi `COMMITTING`, atomic transition tại database không bảo vệ hiệu ứng provider. Cần đặt thứ tự:

```text
CAS RUNNING -> COMMITTING
Invoke external provider with stable idempotency key
Record provider outcome
Mark SUCCEEDED / NEEDS_RECONCILIATION
```

Nếu call timeout, **không** quay trạng thái về `RUNNING` rồi charge lại với ID mới. Phải kiểm tra provider status bằng idempotency key/reference trước khi quyết định.

## 14. Conditional update và compare-and-set bảo vệ state machine

Trong NoSQL, một thao tác cập nhật điều kiện thường hữu ích để phân xử race:

```text
UPDATE job J1
SET state = CANCEL_REQUESTED
WHERE state = RUNNING
  AND version = 7
```

Nếu matched/updated count bằng 0, một participant khác đã chuyển trạng thái hoặc job không ở trạng thái cho phép. **Không tự coi kết quả 0 là “canceled”**; cần đọc lại state hiện hành.

### Ví dụ MongoDB cập nhật có điều kiện

```javascript
const result = await db.collection("jobs").updateOne(
  {
    _id: "JOB-1001",
    tenantId: "T01",
    state: "RUNNING",
    version: 7
  },
  {
    $set: {
      state: "CANCEL_REQUESTED",
      cancellationReason: "USER_REQUEST"
    },
    $inc: { version: 1 }
  }
);

if (result.modifiedCount === 1) {
  // Chỉ có nghĩa flag đã đổi tại document.
  // Worker vẫn cần dừng và xác nhận terminal CANCELED.
}
```

Với một document, `updateOne` theo điều kiện có thể đóng vai trò CAS phù hợp cho state machine nếu schema/read/write concern được thiết kế đúng. Nhưng **không tự tạo transaction nguyên tử với Redis queue hoặc external payment provider**.

### CAS theo version có giới hạn gì?

Nếu job được tạo ở nhiều shard hoặc có nhiều document phụ cần cập nhật như một quyết định, phải xác định một **authority cho job** hoặc dùng distributed transaction phù hợp. Một CAS trên metadata job không tự làm mọi bước đồng thời ở các resource ngoài.

### Tenant và quyền hủy

Không nhận `jobId` từ client rồi update tùy ý. Filter phải ràng buộc tenant/principal, quyền sở hữu job và trạng thái; một user không được hủy công việc của user khác chỉ bằng cách biết ID.

## 15. Lease và worker cũ vẫn có thể chạy sau khi mất quyền

Các job workers thường dùng lease để tránh nhiều worker xử lý một task cùng lúc:

```text
Worker A claims J1 with lease until 10:00:30
A pauses because of GC/network
Lease expires
Worker B claims J1
A resumes at 10:00:45
```

Nếu cả hai chỉ kiểm tra “tôi từng claim job”, cả hai có thể cùng tiếp tục. Khi người dùng hủy trong thời gian này, tình hình càng phức tạp.

### Fencing token / lease generation

Mỗi lần claim hợp lệ tạo một generation tăng:

```text
Worker A: J1 generation=10
Worker B: J1 generation=11
```

Mọi write quan trọng tới authority cần điều kiện:

```text
jobId = J1
AND currentGeneration = 11
AND state = RUNNING/COMMITTING (đúng bước)
```

Worker A dùng generation 10 phải bị từ chối. **Fencing phải được kiểm tra tại nơi thực sự tạo hiệu ứng**, không chỉ trong RAM.

### Không thể fence một provider bất kỳ nếu provider không hỗ trợ

Nếu external service không có idempotency key, conditional reference hoặc semantics cho phép kiểm tra outcome, application không thể dùng một số generation ở database để đảm bảo provider không nhận request cũ. Cần đặt provider call sau một quyết định bền, tránh concurrency và có reconciliation/compensation khi cần.

### TTL xóa job/lease có thể gây mất chứng cứ

Nếu job ledger hoặc idempotency key bị TTL xóa trước khi tất cả retry/side effect đến muộn được giải quyết, worker cũ có thể tưởng job chưa từng chạy và tạo hiệu ứng mới. Retention phải phù hợp với **retry window, queue retention và thời hạn đối soát**.

## 16. Idempotency: nền tảng khi cancellation đi kèm retry

Một client hủy request, sau đó mở ứng dụng lại và gửi cùng thao tác. Ta cần phân biệt:

```text
Logical operation:
  PlaceOrder(orderId=ORD-1001)

Attempts:
  Request attempt #1 -> timeout
  Request attempt #2 -> retry
  Request attempt #3 -> retry
```

**Một logical operation có thể có nhiều attempts**. Mọi attempt nên mang **cùng idempotency key**.

### Thiết kế key

```json
{
  "merchantId": "M01",
  "requestId": "checkout-M01-8e34",
  "orderId": "ORD-1001",
  "amountMinorUnits": 250000
}
```

Một key cần gắn với **merchant/tenant và payload nhất quán**, không chỉ random token rồi dùng lại cho payload khác.

### Ledger trạng thái

```text
Idempotency key K
  -> PENDING       request first accepted
  -> COMMITTED     effect completed, result recorded
  -> FAILED_FINAL  conclusively failed
  -> UNKNOWN       external/transaction result unresolved
```

Các retry:

- K chưa tồn tại → thử tạo entry **có điều kiện**.
- K đã `COMMITTED` → trả kết quả đã ghi.
- K `PENDING` → không chạy thêm bản sao độc lập; trả pending/chờ.
- K `UNKNOWN` → tra source/provider theo reference đã biết.
- Cùng K nhưng payload khác → từ chối theo hợp đồng.

### Exactly-once business effect không đến từ HTTP

HTTP retry, Kafka delivery hoặc driver reconnect không bảo đảm “chỉ thực hiện một lần” cho mọi side effect. Muốn hành vi gần *exactly-once theo nghiệp vụ* phải dùng:

- Unique request identity.
- Conditional insert/transaction tại authority.
- Idempotent provider API khi hỗ trợ.
- Durable result ledger.
- Retry và reconciliation có giới hạn rõ.

Ngay cả khi worker xử lý message hai lần, **business effect** cần không bị nhân đôi. Đây là thiết kế ở cấp ứng dụng, không đơn thuần thuộc transport layer.

## 17. Một API hủy nên trả kết quả gì?

Ví dụ thiết kế endpoint:

```text
POST /jobs/J1/cancel
GET  /jobs/J1
```

Không nên trả `200 "Canceled"` khi mới chỉ cập nhật `cancelRequested=true` và worker vẫn đang xử lý.

Một hợp đồng rõ hơn:

| Tình huống | Response minh họa | Ý nghĩa |
|---|---|---|
| Đã nhận yêu cầu hủy, worker chưa xác nhận | `202 Accepted` | Cancellation requested, chưa hoàn tất |
| Job còn QUEUED và chuyển CANCELED nguyên tử | `200 OK` + `CANCELED` | Đã hủy trước khi chạy |
| Job đã CANCELED, hủy lại | `200 OK` + `CANCELED` | Request hủy idempotent |
| Job đã SUCCEEDED | `409 Conflict` hoặc `200` trạng thái hiện tại | Không hứa hoàn tác, tùy API |
| Job không thuộc user | `404/403` theo policy bảo mật | Không cho truy cập/hủy |
| Cluster không xác minh được status | `503` hoặc `UNKNOWN` | Không trả chắc chắn canceled |

Đây là **lựa chọn hợp đồng**, không phải mapping HTTP duy nhất bắt buộc cho mọi sản phẩm.

### Mẫu response khi mới yêu cầu hủy

```json
{
  "jobId": "J1",
  "state": "CANCEL_REQUESTED",
  "cancellationFinal": false,
  "statusUrl": "/jobs/J1"
}
```

### Mẫu response khi đã xác nhận hủy

```json
{
  "jobId": "J1",
  "state": "CANCELED",
  "cancellationFinal": true,
  "completedSteps": 3,
  "remainingSteps": 0
}
```

Một job đã thực hiện một số bước **có hiệu ứng bền** vẫn cần mô tả những bước ấy và chính sách bù trừ; `state=CANCELED` không được làm người dùng hiểu rằng các bước đã commit bị xóa khỏi lịch sử.

## 18. Java `CompletableFuture.cancel()` không phải remote cancel

Trong Java, một caller có thể chạy:

```java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> future =
    CompletableFuture.supplyAsync(() -> {
        // Giả sử đây là một việc blocking hoặc gọi remote service.
        return performRemoteWrite();
    });

// User không muốn chờ kết quả nữa:
future.cancel(true);
```

`CompletableFuture.cancel(boolean mayInterruptIfRunning)` khiến future hoàn thành ở trạng thái canceled theo semantics của `CompletableFuture`. Tham số `mayInterruptIfRunning` **không đảm bảo interrupt công việc đang chạy** trong implementation của `CompletableFuture`; nó không phải công cụ gửi rollback tới database.

Hàm `performRemoteWrite()` vẫn có thể:

- Đang chạy trên thread/executor.
- Đã gửi write tới database.
- Đã nhận ACK nhưng chưa chuyển kết quả về future.
- Hoàn tất và tạo side effect dù future đã canceled.

### Hủy sự chờ đợi khác hủy hành động

```text
Caller:       future.cancel() -> CancellationException
Worker:       performRemoteWrite() -------> COMMITTED
Database:                                  stored v8
```

Đây là một ví dụ rất rõ rằng **trạng thái của Java future không phải trạng thái transaction trong NoSQL**.

### Không tự suy từ `orTimeout` thành server timeout

```java
future.orTimeout(500, java.util.concurrent.TimeUnit.MILLISECONDS);
```

`orTimeout` làm future hoàn thành exceptionally khi quá thời hạn theo semantics Java, nhưng **không đảm bảo** công việc bên dưới hoặc remote request bị dừng.

Khi triển khai, phải xác định timeout/cancellation thực sự có được truyền qua HTTP client, driver và server hay không.

## 19. Java `Future.cancel(true)` và Thread interruption

Khác với `CompletableFuture`, một `Future` do `ExecutorService.submit` tạo có thể cố **interrupt** thread khi gọi `cancel(true)`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

ExecutorService pool = Executors.newSingleThreadExecutor();

try {
    Future<?> task = pool.submit(() -> {
        while (!Thread.currentThread().isInterrupted()) {
            doOneSmallUnitOfWork();
        }
    });

    task.cancel(true); // cooperative interruption attempt
} finally {
    pool.shutdownNow();
}
```

Nhưng:

- Thread có thể không kiểm tra flag.
- Một call blocking có thể xử lý interrupt theo cách riêng.
- Một socket request đã gửi không tự rollback trên server.
- Việc interrupt giữa bước ghi không thay đổi commit outcome.
- `shutdownNow()` cũng là **best-effort interruption**, không bảo đảm mọi task dừng ngay.

### Một worker hợp tác tốt

```java
void processBatch(CancelCheck cancel) throws Exception {
    for (int i = 0; i < 1000; i++) {
        if (Thread.currentThread().isInterrupted()
                || cancel.isCancellationRequested()) {
            throw new InterruptedException("Cancellation requested");
        }

        // Thực hiện một đơn vị nhỏ theo idempotency/version.
        processOneItem(i);
    }
}

interface CancelCheck {
    boolean isCancellationRequested() throws Exception;
}
```

**Giới hạn:** check trước `processOneItem` không tạo một transaction với bước đó. Nếu quá trình xử lý gọi external provider, cần idempotency/fencing và state transition bền như đã phân tích.

## 20. Ví dụ Java HTTP async: timeout ở client vẫn không rõ write outcome

Java `HttpClient.sendAsync`:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class CheckoutClientExample {
    public static void main(String[] args) {
        String requestId = "checkout-M01-8e34";

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://example.test/api/checkout"))
            .timeout(Duration.ofSeconds(3))
            .header("Content-Type", "application/json")
            .header("Idempotency-Key", requestId)
            .POST(HttpRequest.BodyPublishers.ofString(
                "{\"orderId\":\"ORD-1001\",\"requestId\":\""
                  + requestId + "\"}"
            ))
            .build();

        HttpClient client = HttpClient.newHttpClient();

        CompletableFuture<HttpResponse<String>> pending =
            client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString()
            );

        // Đây là timeout của logic chờ ở caller.
        // Nó không chứng minh server chưa commit.
        pending.orTimeout(2, TimeUnit.SECONDS)
            .exceptionally(error -> {
                System.out.println("Outcome may be unknown: " + error);
                // Ứng dụng thật phải tra cứu bằng requestId.
                return null;
            });
    }
}
```

**Đây là ví dụ về semantics chờ**, không phải chương trình checkout production. Domain giả, không có xử lý TLS/callback lifecycle/retry đầy đủ. Một client HTTP library có thể cố ngắt network khi cancel, nhưng **không thể ép NoSQL server hoàn tác một write đã commit**.

### Khi reconnect

Thay vì gửi một checkout mới:

```text
GET /api/checkout/requests/checkout-M01-8e34
```

Server trả kết quả từ ledger hoặc nguồn giao dịch có thẩm quyền. Nếu không tìm thấy vì dữ liệu đang eventual hoặc tạm unavailable, **không vội coi là chắc chắn chưa commit**; phải hiểu read consistency và khoảng retry liên quan.

## 21. MongoDB: hủy driver operation, maxTimeMS và commit mơ hồ

Trong MongoDB, cần phân biệt:

- **Client-side timeout/disconnect**.
- **Driver/cursor/query cancellation** theo API được hỗ trợ.
- **Server-side execution limits**, ví dụ `maxTimeMS` trên những operation thích hợp.
- **Transaction abort** trước khi commit.
- **Unknown transaction commit result** khi response commit bị mất.

### Query giới hạn thời gian

```javascript
// Minh họa một find có giới hạn thời gian server-side,
// nếu API/server version hỗ trợ option trong trường hợp này.
db.orders.find(
  { tenantId: "T01", status: "SUBMITTED" }
).maxTimeMS(2000);
```

Nếu query vượt thời gian được engine thực thi theo semantics của `maxTimeMS`, server có thể dừng operation với lỗi phù hợp. Tuy nhiên:

- Giới hạn thực thi server không phải timeout end-to-end của HTTP.
- Không phải mọi operation có cùng support/behavior.
- Thao tác đã tạo side effect trước khi bị dừng không tự được undo.
- Một write đã commit trước khi timeout không thành uncommitted chỉ vì client ngừng chờ.

### Transaction commit không rõ kết quả

Ví dụ khái niệm với Node.js driver:

```javascript
const session = client.startSession();

try {
  await session.withTransaction(async () => {
    await db.collection("orders").updateOne(
      { _id: "ORD-1001", state: "DRAFT" },
      { $set: { state: "SUBMITTED" } },
      { session }
    );

    await db.collection("requestLedger").insertOne(
      {
        _id: "checkout-M01-8e34",
        orderId: "ORD-1001",
        state: "COMMITTED"
      },
      { session }
    );
  });
} finally {
  await session.endSession();
}
```

Đây là **mẫu triển khai giản lược** để giải thích việc đặt trạng thái đơn và request ledger trong cùng transaction nếu engine/topology hỗ trợ. Cần thêm kiểm tra kết quả `matchedCount`, xử lý unique key, authorization, write concern và exception thực tế.

MongoDB driver có cơ chế nhãn lỗi như `TransientTransactionError` và `UnknownTransactionCommitResult` trong những tình huống được tài liệu mô tả. Một `withTransaction` helper có thể retry callback hoặc commit theo logic driver. **Không đặt external charge/email không idempotent bên trong transaction callback** rồi giả định callback chỉ chạy một lần.

### Abort không xóa payment đã gọi trước

```text
1. Call payment provider -> charged
2. MongoDB transaction -> abort
```

Payment không được rollback bởi MongoDB. Muốn xử lý đúng phải có outbox/saga/ledger và provider idempotency.

### Read sau unknown commit

Nếu có ledger theo `requestId`, sử dụng đường đọc có consistency phù hợp để kiểm tra. Đọc từ secondary trễ hoặc search index có thể trả “không tìm thấy” dù commit đã thành công ở source. Không dùng một eventual projection làm bằng chứng chắc chắn thao tác chưa diễn ra.

## 22. DynamoDB: request timeout, conditional write và transaction token

DynamoDB cung cấp:

- Write theo primary key.
- **Conditional writes**, ví dụ `attribute_not_exists` hoặc so version.
- **TransactWriteItems** cho các item thuộc phạm vi transaction API hỗ trợ.
- `ClientRequestToken` hỗ trợ idempotency cho transaction trong một **cửa sổ hữu hạn theo tài liệu**.
- Các chế độ read consistency khác nhau trên base table/index/API.

### Conditional write để chặn double checkout

Một pattern là tạo một item ledger theo key:

```text
PK = "CHECKOUT#M01#checkout-M01-8e34"
```

Chỉ một request được tạo key này nếu chưa tồn tại:

```json
{
  "TableName": "CheckoutLedger",
  "Item": {
    "PK": { "S": "CHECKOUT#M01#checkout-M01-8e34" },
    "orderId": { "S": "ORD-1001" },
    "state": { "S": "PENDING" }
  },
  "ConditionExpression": "attribute_not_exists(PK)"
}
```

Nếu request tạo ledger timeout, caller **không tự biết** ledger đã được tạo chưa. Retry giữ cùng key và kiểm tra trạng thái hợp lệ; việc Put bị `ConditionalCheckFailed` có thể có nghĩa entry đã tồn tại, cần đối chiếu `owner/payload` trước khi trả kết quả cũ.

### Transaction cùng ledger

Nếu checkout cần tạo đơn và ledger cùng lúc, có thể dùng `TransactWriteItems` trong phạm vi API cho phép. Một transaction hoàn tất không bị rollback chỉ vì client hủy HTTP sau đó.

### Idempotency token không vĩnh viễn

Không coi `ClientRequestToken` là bảo đảm dedup trọn đời. Thời hạn hỗ trợ và yêu cầu payload phải được kiểm tra ở tài liệu đang dùng; nếu business retry sau nhiều ngày, cần **request ledger bền** với retention phù hợp.

### GSI chưa thấy không có nghĩa chưa commit

Một GSI có thể cập nhật bất đồng bộ theo API. Nếu client hủy sau write rồi query GSI thấy empty, không được tự kết luận ghi thất bại. Hãy tra key tại source/base table với consistency mode được hỗ trợ.

## 23. Cassandra/ScyllaDB: timeout của coordinator không chắc là write thất bại

Trong Cassandra-style replication, một coordinator nhận write và chờ số replica theo consistency level `ONE`, `QUORUM`, `LOCAL_QUORUM` hoặc cấp khác được hỗ trợ.

Một write timeout có thể xuất hiện khi:

- Một số replicas đã áp mutation.
- Coordinator chưa nhận đủ ACK trước deadline.
- Network giữa replica/coordinator chậm.
- Driver timeout trước khi coordinator trả kết quả.

```text
Client -> Coordinator: UPDATE x=v8
             |
             +--> Replica A applied v8
             +--> Replica B applied v8
             +--> Replica C delayed
             |
Client times out / cancels before response
```

Không thể từ lỗi timeout tự suy **mọi replica vẫn v7**. Retry một `SET status='SUBMITTED'` với key cố định thường có tính chất khác retry `counter += 1` hoặc tạo một effect không idempotent.

### Conditional mutation/LWT

Với thao tác cần uniqueness/compare-and-set, Cassandra có lightweight transactions theo phạm vi được hỗ trợ:

```sql
INSERT INTO request_claims (
  tenant_id, request_id, owner_id, state
) VALUES ('T01', 'R101', 'U101', 'CLAIMED')
IF NOT EXISTS;
```

Khi trả về, cần kiểm tra `[applied]`. Nếu call timeout, phải xử lý như **outcome chưa rõ**; không tự phát request ID mới. LWT trên một partition không tự là transaction giữa Cassandra và payment provider.

### Read từ replica trễ

`CL=ONE` và `CL=QUORUM` có semantics khác; một read ở mức yếu có thể không thấy write mới trong một số tình huống. Điều quan trọng khi xác minh canceled/committed là dùng **đường đọc và mức consistency phù hợp với claim**, không quét một replica bất kỳ rồi tuyên bố request chưa xảy ra.

## 24. Redis: lệnh đã được thực thi vẫn có thể mất response

Ví dụ:

```text
Client -> Redis primary: INCR points:U1
Redis executes INCR -> value becomes 101
Network drops response
Client: TIMEOUT
```

Nếu client retry:

```redis
INCR points:U1
```

giá trị thành 102. **`INCR` nguyên tử trên một lệnh không làm retry của hai lần gọi trở thành một logical operation duy nhất.**

### Phân biệt thao tác

| Lệnh/kiểu cập nhật | Retry sau unknown outcome |
|---|---|
| `SET key value` cùng giá trị | Có thể idempotent về state của key, nhưng còn TTL/side effects khác |
| `INCR key` | Không idempotent nếu không có dedup |
| `LPUSH queue item` | Có thể chèn item trùng |
| `DEL key` | Thường cùng kết quả cuối nếu không có concurrent writes; không bảo vệ race |
| Lua/script nhiều key cùng slot | Atomic execution theo phạm vi hỗ trợ; response mất vẫn có ambiguity |

### Redis replication và failover thêm một lớp rủi ro

Primary có thể thực thi write và ACK, nhưng replica chưa nhận khi failover xảy ra. Vì vậy cần xem **replication, persistence, `WAIT`/cơ chế liên quan và failover semantics**, chứ không suy rằng client timeout hoặc ACK đều bảo vệ durable exactly-once.

### Dùng Redis làm cancellation flag

```redis
SET cancel:job:J1 1 EX 3600
```

Worker kiểm tra flag này có thể dừng ở checkpoint. Nhưng:

- Flag có TTL có thể biến mất trước khi worker đọc.
- Client/worker khác có thể truy cập replica trễ.
- Redis flag không tự fence external side effect.
- Nếu job ledger ở DB nguồn, Redis chỉ nên là **tín hiệu tối ưu**, không phải authority duy nhất của terminal state.

Một hệ nghiêm túc cần trạng thái cancellation **bền và có điều kiện** ở nguồn quyết định job, hoặc thừa nhận hủy chỉ best-effort.

## 25. Elasticsearch/OpenSearch: search cancellation và write visibility

Một search query dài có thể tốn CPU/memory. Khi client đóng kết nối, query engine có thể có cơ chế **task cancellation** hoặc kết thúc theo timeout của API tùy loại operation và phiên bản.

Điều quan trọng:

- Client ngừng nhận search result không có nghĩa task search đã ngừng ngay.
- Một số API có thể cung cấp task ID/status/cancel endpoint.
- Task cancellation thường mang tính **best-effort/cooperative**; không phải mọi operation đều cancellable ở mọi thời điểm.
- Search/index refresh có vòng đời khác với client response.

### Search là read-heavy

Nếu chỉ là một `_search` không ghi, hủy có thể chủ yếu tiết kiệm CPU/bandwidth. Nhưng nếu request có thao tác `_update_by_query`, `_reindex`, bulk indexing hoặc quản lý index, một số thay đổi có thể đã được thực hiện **trước khi cancellation được xử lý**.

Không đánh đồng:

```text
Cancel long search -> release resources (eventually)
Cancel update-by-query -> all prior document updates rolled back
```

Hai câu có semantics rất khác. Với batch mutation, cần đọc tài liệu về **task cancellation, partial progress, retries, version conflicts và checkpoint**.

### Search visibility vs source commit

Nếu MongoDB source đã commit đơn v8 nhưng search chưa refresh, user có thể nhìn thấy v7 dù client đã hủy request tạo đơn. Đây là **projection lag**, không phải chứng minh transaction nguồn bị rollback.

## 26. Queue, Kafka và worker: stop consuming không đồng nghĩa undo event

Một công việc có thể đi qua message broker:

```text
API -> DB outbox commit -> broker -> consumer -> external effect
```

Client hủy HTTP sau khi outbox commit; broker/consumer vẫn tiếp tục xử lý.

### Consumer offset/ack không là business commit

Ở một message system:

- Message có thể được fetch.
- Consumer xử lý và ghi database.
- Consumer có thể commit offset/ACK riêng.
- Nếu consumer crash giữa write và ACK offset, message có thể được giao lại.

```text
Consume message M1
Write order state COMMITTED
Crash before ACK/offset commit
Broker redelivers M1
```

Nếu handler không idempotent, effect có thể lặp.

### Cancellation message có thể đến sau work message

```text
Topic/queue A:  CREATE_JOB J1
Topic/queue B:  CANCEL_JOB J1
```

Không có một thứ tự toàn phần miễn phí giữa hai topic/partition/consumer groups khác nhau. Worker có thể nhận cancel **trước** create, hoặc sau khi create đã hoàn tất, tùy topology và ordering semantics.

Giải pháp cần **job state có thẩm quyền**, `jobId/generation` và conditional transition, thay vì chỉ tin thứ tự hai thông điệp trên các queue độc lập.

### Outbox đảm bảo điều gì?

Nếu job record và outbox event được ghi trong cùng database transaction được hỗ trợ, ta giảm race “DB đã commit nhưng message chưa được lưu bền”. Nhưng outbox relay vẫn có thể publish **ít nhất một lần**; consumer cần dedup/idempotency.

Hủy API không xóa một outbox event đã commit nếu sự kiện thể hiện thay đổi nghiệp vụ mà downstream cần biết. Có thể cần thêm một **CancelRequested event** và state machine.

## 27. Sự khác biệt giữa hủy query tốn tài nguyên và hủy lệnh thay đổi dữ liệu

Một nguyên tắc thiết kế hữu ích là **phân loại operation trước khi quyết định cancellation policy**:

| Operation | Hủy request thường nhằm mục đích | Vấn đề chính |
|---|---|---|
| Point lookup/read | Ngừng chờ và tiết kiệm tài nguyên | Query vẫn có thể chạy, read stale |
| Full scan/aggregation | Giảm CPU/I/O của query dài | Server task có thể tiếp tục đến checkpoint |
| Download/export | Dừng truyền dữ liệu | Job tạo file có thể vẫn chạy |
| Idempotent SET/PUT | Ngừng UI/giới hạn retry | Commit outcome có thể unknown |
| Atomic increment/counter | Ngừng thao tác không mong muốn | Retry tạo double increment |
| Reservation/seat claim | Tránh xác nhận sai | Cancel/commit race, unique invariant |
| Multi-key transaction | Abort trước commit | Commit mơ hồ, external effects |
| Payment/charge | Yêu cầu ngừng hoặc bù trừ | Provider side effects, refund |
| Queue consumer task | Dừng công việc nền | Redelivery, lease expiration, fencing |
| Bulk update/reindex | Giới hạn tiến độ | Partial progress, checkpoint, compensation |

Một chính sách chung “cứ thấy HTTP disconnect thì kill mọi việc” vừa không khả thi vừa có thể phá quy trình nghiệp vụ. Ví dụ đã tạo order và ghi outbox, nếu dừng worker gửi confirmation chỉ vì tab browser đóng, hệ có thể để đơn thành công nhưng không gửi thông báo.

## 28. Cách thiết kế “Cancel” trong giao diện người dùng

Một UI có thể có hai ý nghĩa khác nhau:

**A. Đóng hộp thoại / ngừng chờ**

```text
Button label: "Đóng"
Effect: cancel pending fetch/render work
Business outcome: unchanged or unknown
```

**B. Yêu cầu hủy nghiệp vụ**

```text
Button label: "Hủy đơn"
Effect: POST /orders/{id}/cancel with requestId
Business outcome: governed by order state machine
```

Nếu hai hành động cùng tên **“Hủy”**, người dùng dễ hiểu sai hệ thống.

### Mẫu UI cho kết quả chưa rõ

```text
Trạng thái: Đang kiểm tra yêu cầu
Mã tham chiếu: checkout-M01-8e34

Chúng tôi chưa nhận được kết quả cuối của thao tác.
Bạn có thể xem trạng thái hoặc quay lại sau.
Không nên tạo một yêu cầu mới với mã khác
khi thao tác trước vẫn chưa được xác minh.
```

### UX không nên dựa vào một query eventual để nói “thất bại”

Nếu một read từ search/cache thấy “chưa có đơn” ngay sau timeout, giao diện không được tự tạo checkout mới mà không kiểm tra source/ledger phù hợp. Có thể có **replication lag hoặc projection lag**.

### Một trạng thái “đã nhận yêu cầu hủy” phải rõ

Nếu worker còn chạy, hiển thị `CANCEL_REQUESTED`/“Đang hủy”, không hiển thị “Đã hủy hoàn tất” trước khi server xác nhận terminal state.

## 29. Thiết kế endpoint trạng thái theo requestId

Một pattern:

```text
POST /checkout
Headers:
  Idempotency-Key: checkout-M01-8e34

GET /checkout/requests/checkout-M01-8e34
```

Trả:

```json
{
  "requestId": "checkout-M01-8e34",
  "state": "COMMITTED",
  "orderId": "ORD-1001",
  "committedVersion": 8
}
```

Hoặc:

```json
{
  "requestId": "checkout-M01-8e34",
  "state": "PENDING",
  "retryAfterSeconds": 2
}
```

### Không suy từ “404 không thấy” ra “không commit”

Một request có thể đã commit dữ liệu nguồn nhưng ledger projection chưa đồng bộ, hoặc status read đang đi tới replica trễ. Nếu ledger và source không được ghi nguyên tử, còn có cửa sổ tồn tại một bên. API cần định nghĩa **authority** và consistency mode cho việc kiểm tra kết quả.

### Những trường nên lưu trong ledger

- Tenant/principal scope.
- Logical `requestId`, operation type, payload hash.
- State và version/generation.
- Resource IDs được tạo.
- Commit reference/transaction ID nếu có.
- External provider idempotency/reference.
- StartedAt, updatedAt, completedAt.
- Cancellation requestedAt/reason (nếu có).
- Retry count và last known error class.

Không lưu payment secrets, access tokens hoặc PII không cần thiết vào ledger/log. Một hash payload không thay thế quyền truy cập và xác thực toàn bộ request.

## 30. Thiết kế durable job cancellation bằng transaction/CAS

Một mô hình pseudocode:

```text
CREATE_JOB(requestId):
  Atomically create job if requestId absent.
  Store jobId, state=QUEUED, version=1.
  Persist outbox/dispatch intent if supported.
  Return existing job if same requestId is retried.

REQUEST_CANCEL(jobId, user):
  Authenticate and authorize.
  If state is QUEUED:
      CAS QUEUED -> CANCELED
  Else if state is RUNNING:
      CAS RUNNING -> CANCEL_REQUESTED
  Else:
      Return current terminal/committing state.

WORKER_CLAIM(jobId):
  CAS QUEUED -> RUNNING with new generation.
  Abort if claim lost.

WORKER_LOOP(jobId, generation):
  For each safe checkpoint:
      Read durable job state.
      If CANCEL_REQUESTED:
          stop spawning new side effects
          finalize CANCELED only when safe
      Else:
          process idempotent unit with generation fencing

BEFORE_IRREVERSIBLE_STEP:
  CAS RUNNING -> COMMITTING
  if cancellation won, do not invoke external effect.
  if COMMITTING won, cancellation cannot promise stop.

FINALIZE:
  record external result and terminal state with CAS.
```

### Điểm thiết kế bắt buộc

1. **Atomic claim**: hai worker không được cùng nghĩ đã claim độc quyền nếu nghiệp vụ cần single worker.
2. **Fencing**: lease hết hạn phải làm writer cũ mất quyền ghi ở nguồn.
3. **Durable cancel**: flag cancellation phải tồn tại đủ lâu và không biến mất cùng request HTTP.
4. **Checkpoints**: dừng giữa các đơn vị công việc có thể hủy an toàn, không giữa một atomic transaction bất kỳ.
5. **External side effect**: dùng provider idempotency hoặc recovery protocol.
6. **Terminal result**: `CANCELED` chỉ khi cam kết “không còn effect mới” thực sự đúng trong phạm vi đã định nghĩa.
7. **Retry**: kiểm tra trạng thái/ledger và dùng cùng logical operation identity.

### Nếu worker nhận cancel sau khi đã bắt đầu external call

Không có phép CAS trong job table nào làm một request đã bay tới provider chắc chắn biến mất. Hệ cần:

- Chờ xác minh provider outcome.
- Nếu đã commit, có thể thực hiện compensation.
- Nếu chưa rõ, đánh dấu `NEEDS_RECONCILIATION`.
- Không gửi thêm một call không idempotent với ID mới.

## 31. Một ví dụ Java 17 về trạng thái job và quyền hủy

Đoạn mã sau là **interface-level example**, minh họa cách chia ranh giới giữa request cancel và worker. Nó không triển khai một database NoSQL thật; các phương thức `compareAndSet` và `claim` phải được backing store cung cấp nguyên tử trong phạm vi cần thiết.

```java
import java.util.Optional;

enum JobState {
    QUEUED, RUNNING, CANCEL_REQUESTED, COMMITTING,
    SUCCEEDED, CANCELED, FAILED_FINAL, NEEDS_RECONCILIATION
}

record Job(
    String id,
    String tenantId,
    JobState state,
    long version,
    long generation
) {}

interface JobRepository {
    Optional<Job> loadAuthorized(String tenantId, String jobId)
        throws Exception;

    // Update must be atomic and verify version+state.
    boolean compareAndSet(
        String tenantId,
        String jobId,
        long expectedVersion,
        JobState expectedState,
        JobState newState
    ) throws Exception;
}

record CancelResponse(
    JobState state,
    boolean finalCancellation
) {}

final class JobCancellationService {
    private final JobRepository jobs;

    JobCancellationService(JobRepository jobs) {
        this.jobs = jobs;
    }

    CancelResponse requestCancel(String tenantId, String jobId)
            throws Exception {
        for (int attempt = 0; attempt < 5; attempt++) {
            Job current = jobs.loadAuthorized(tenantId, jobId)
                .orElseThrow(() ->
                    new IllegalArgumentException("Job not found"));

            switch (current.state()) {
                case CANCELED:
                    return new CancelResponse(JobState.CANCELED, true);
                case QUEUED:
                    if (jobs.compareAndSet(
                            tenantId, jobId, current.version(),
                            JobState.QUEUED, JobState.CANCELED)) {
                        return new CancelResponse(JobState.CANCELED, true);
                    }
                    break;
                case RUNNING:
                    if (jobs.compareAndSet(
                            tenantId, jobId, current.version(),
                            JobState.RUNNING,
                            JobState.CANCEL_REQUESTED)) {
                        return new CancelResponse(
                            JobState.CANCEL_REQUESTED, false);
                    }
                    break;
                case CANCEL_REQUESTED:
                    return new CancelResponse(
                        JobState.CANCEL_REQUESTED, false);
                default:
                    return new CancelResponse(current.state(), false);
            }
        }

        throw new IllegalStateException(
            "Concurrent transitions; retry using same cancel intent"
        );
    }
}
```

### Ý nghĩa

- `QUEUED → CANCELED` chỉ an toàn nếu claim của worker cũng là CAS đối chọi với cùng trạng thái/phiên bản.
- `RUNNING → CANCEL_REQUESTED` **chưa phải terminal**.
- `COMMITTING`, `SUCCEEDED` và `NEEDS_RECONCILIATION` không bị viết đè thành CANCELED.
- `tenantId` cần lấy từ identity được xác thực; việc repository có chữ `Authorized` không thay cơ chế phân quyền thật.
- Store phải cập nhật `version` đúng và giữ nguyên quy tắc chuyển trạng thái.
- Nếu worker đã claim ở nguồn khác hoặc có provider call ngoài, phải thêm fencing/idempotency và workflow như mục trước.

Đây là hướng minh họa để dùng với conditional update trong MongoDB, DynamoDB hoặc LWT ở datastore phù hợp, chứ không phải bằng chứng một đoạn Java độc lập có thể dừng worker phân tán.

## 32. Background work đã chạy xong nhưng response client bị cancel

Một trường hợp phổ biến ở các hệ asynchronous:

```text
T0 POST /reports requestId=R1
T1 Server persists job J1, returns 202 (response in-flight)
T2 Client aborts fetch, does not receive 202
T3 Worker creates report J1
T4 Worker marks SUCCEEDED
T5 User retries POST /reports with new ID R2
T6 System creates another report J2
```

Nếu việc tạo report tốn tài nguyên, người dùng đang vô tình tạo hai job.

### Cách làm phù hợp hơn

Trả hoặc lưu một **logical requestId ổn định trước khi gửi**, rồi server có unique constraint trên requestId theo tenant:

```text
POST /reports Idempotency-Key=R1
-> creates J1 or returns existing J1

Retry POST /reports Idempotency-Key=R1
-> returns same J1
```

Nếu người dùng thực sự muốn **một report mới với cùng input**, ứng dụng cần một requestId mới và ý định mới. Idempotency không phải cấm mọi thao tác giống nhau, mà là **phân biệt retry của cùng ý định với một ý định mới**.

## 33. Hủy một batch: dừng phần chưa xử lý, xác định phần đã hoàn tất

Ví dụ một job cập nhật 1 triệu document:

```text
Batch 1:  0..9,999       COMMITTED
Batch 2:  10,000..19,999 COMMITTED
Batch 3:  20,000..29,999 RUNNING
User requests CANCEL
Batch 4+: not started
```

Nếu engine/process hỗ trợ cancel giữa các batch, job có thể ngừng sau batch 3 và để lại **20.000 hoặc 30.000 record đã thay đổi**.

### Không nên trả “0 record thay đổi”

Một phản hồi đúng phải nói rõ:

- Những batch nào đã commit.
- Batch đang chạy có kết quả đã xác minh hay chưa.
- Có thể resume không.
- Có thể compensate/rebuild không.
- Có cần chạy reconciliation để tìm partial changes không.

Một API có thể trả:

```json
{
  "jobId": "BULK-01",
  "state": "CANCELED",
  "processed": 30000,
  "remaining": 970000,
  "committedChangesRetained": true
}
```

Đây là **một semantics thiết kế có thể lựa chọn**, không có nghĩa mọi database hủy bulk operation trả cùng số lượng chính xác. Nếu số đã xử lý là ước lượng, phải gắn nhãn đúng.

### Checkpoint và idempotency của batch

Mỗi batch nên có key/checkpoint ổn định. Khi job resume, không replay batch đã commit nếu operation không idempotent. Với delta/counter, cần ledger theo batch hoặc per-item operation ID.

## 34. Độ mới khi kiểm tra kết quả: đừng hỏi nhầm replica

Một client timeout sau write, backend tra lại trạng thái:

```text
Primary: ORDER v8 COMMITTED
Replica R2: ORDER v7 (lag)
Search index: ORDER v7 (projection lag)
Redis cache: ORDER v7 (stale)
```

Nếu status endpoint đọc từ R2/search/cache và trả:

```text
404 / NOT_FOUND / NOT_SUBMITTED
```

thì client có thể retry sai.

### Status read phải có authority rõ

Với giao dịch quan trọng:

- Đọc ledger/nguồn đã commit theo consistency semantics phù hợp.
- Dùng requestId/orderId và version được xác nhận.
- Nếu không thể đạt mức đọc cần thiết do mất quorum, trả **UNKNOWN/UNAVAILABLE** thay vì “chắc chắn không có”.
- Không lấy eventual projection làm chứng cứ âm tính cuối cùng.

### Read-your-writes và cancellation

Khi client reconnect, có thể mang `minVersion` hoặc session token để không đọc về một phiên bản trước khi request đã commit. Token không thay quyền truy cập; phải xác thực user/tenant.

### Không phải mọi operation đều cần strong read

Một report preview có thể dùng eventual read với thông báo trạng thái đồng bộ. Nhưng payment, reservation và idempotency reconciliation cần **bảo đảm đủ mạnh** để tránh tác động sai.

## 35. Phân biệt cancellation với circuit breaker và overload shedding

Một service quá tải có thể:

- Timeout request.
- Từ chối ngay bằng `503/429`.
- Ngừng gửi request downstream.
- Hủy query dài để tiết kiệm tài nguyên.
- Tự tạm đóng circuit breaker.

Đó là **cơ chế bảo vệ tài nguyên**, không tự xác định outcome của một write đã đi vào database.

### Retry storm sau timeout

```text
DB p99 tăng
-> API timeouts
-> clients retry
-> DB nhận thêm tải
-> p99 tăng tiếp
```

Để tránh:

- Deadline budgets nhất quán.
- Exponential backoff và jitter.
- Retry budget/circuit breaker.
- Idempotency keys.
- Không retry non-idempotent mutation không có guard.
- Có cách tra outcome unknown.
- Throttling/shed load trước khi gọi downstream khi chưa chấp nhận request.

**Hủy hàng nghìn futures ở client không tự giảm tải DB** nếu server tiếp tục chạy mọi request. Cần instrumentation để biết cancellation signal có thực sự tới nơi chiếm tài nguyên hay không.

## 36. Lựa chọn xử lý cancellation theo từng loại nghiệp vụ

| Nghiệp vụ | Chính sách thích hợp | Điểm cần bảo vệ |
|---|---|---|
| Autocomplete/search | Ngừng chờ, cancel query best-effort | Resource release, không chặn request mới |
| Export lớn | Job riêng, cancel checkpoints | Partial file và cleanup |
| Bulk reindex | Task cancellation với progress | Partial documents, resume/rebuild |
| Tạo tài khoản | Idempotent request, unique guard | Không tạo hai user |
| Đặt chỗ | State machine reservation, conditional write | Không giữ hai chủ cùng một ghế |
| Thanh toán | Request ledger + provider idempotency | Không double charge |
| Chuyển tiền | Atomic transaction/ledger + idempotency | Không debit hai lần/mất credit |
| Gửi email | Outbox/consumer dedup | Không gửi email trùng nếu chính sách yêu cầu |
| Xóa dữ liệu | Durable delete intent + audit | Không phục hồi dữ liệu do replay muộn |
| Thu hồi quyền | Authoritative permission state | Không tiếp tục cho đọc khi đã thu hồi |
| Tác vụ AI/compute | Cooperative cancellation và quota | Giảm CPU, giữ kết quả đã persist đúng |

Lựa chọn “hủy tốt nhất có thể” có thể phù hợp cho **search**, nhưng với **financial mutation** cần một nguồn có thẩm quyền về trạng thái cuối.

## 37. Runbook khi người dùng báo “tôi đã hủy nhưng hệ vẫn thực hiện”

### Bước 1 — Thu thập logical request identity

Xác định `requestId`, user/tenant, thời điểm người dùng nhấn Hủy và endpoint đã gọi. Không bắt đầu điều tra chỉ bằng IP hoặc một dòng proxy log.

### Bước 2 — Tìm timeline đa tầng

```text
Client send / abort
Proxy receive / disconnect
API handler start / end
Database command invoke / response
Transaction commit/abort
Outbox event persist / publish
Worker claim / complete
External provider invoke / status
```

### Bước 3 — Xác định người dùng thực sự hủy gì

Họ chỉ đóng hộp thoại, hủy HTTP request, hay đã gọi **business cancel endpoint**? UI có gây hiểu nhầm không?

### Bước 4 — Phân loại trạng thái của từng side effect

- Source database đã commit chưa?
- Có transaction ID/commit reference không?
- Queue đã chấp nhận event chưa?
- Worker còn chạy hay terminal?
- Provider đã charge/gửi email chưa?
- Có một retry bằng requestId khác không?

### Bước 5 — Chọn nguồn xác minh đúng

Không lấy search/cache eventual làm chứng cứ “không có write”. Tra ledger/source/provider status với quyền truy cập và consistency phù hợp.

### Bước 6 — Ngăn tác động tiếp theo nếu còn an toàn

Nếu job chưa qua điểm không thể hủy, gửi cancellation riêng hoặc set durable flag, để worker nhận ở checkpoint. Nếu đã commit, chuyển sang workflow bù trừ theo policy.

### Bước 7 — Sửa kết quả nghiệp vụ

Nếu đã double charge hoặc duplicate reservation, cần reconciliation/refund/release theo audit. Không chỉ xóa một document để “ẩn” lỗi.

### Bước 8 — Sửa mô hình API và UX

Phân biệt cancel request vs cancel job/order, bổ sung requestId/status endpoint, idempotency, deadline propagation, logging và test tương ứng.

## 38. Các metric cần theo dõi

Một dashboard có thể gồm:

| Nhóm | Metric gợi ý | Câu hỏi |
|---|---|---|
| Client/transport | `client_aborted_requests_total` | Có bao nhiêu request người dùng ngừng chờ? |
| Proxy | `upstream_disconnect_total` | Proxy phát hiện disconnect nào? |
| API | `handler_running_after_disconnect` | Handler còn chạy bao lâu sau khi client rời? |
| Downstream | `downstream_cancel_sent_total` | Có gửi cancel tới DB/RPC không? |
| Downstream | `downstream_cancel_confirmed_total` | Hủy có được xác nhận theo API không? |
| Database | `db_unknown_outcome_total` | Có bao nhiêu write outcome mơ hồ? |
| Transaction | `transaction_commit_timeout_total` | Commit response bị mất/hết hạn? |
| Job | `job_cancel_requested_total` | Bao nhiêu yêu cầu hủy được chấp nhận? |
| Job | `job_canceled_terminal_total` | Bao nhiêu job thật sự kết thúc canceled? |
| Job | `job_committed_after_cancel_request_total` | Những job qua điểm không thể dừng? |
| Worker | `stale_worker_fence_rejected_total` | Worker cũ có bị chặn đúng không? |
| Queue | `redelivered_message_total` | Có chạy lại do offset/ACK timeout? |
| Idempotency | `duplicate_request_deduplicated_total` | Ledger chặn tác động trùng ra sao? |
| Provider | `external_unknown_result_total` | Phải reconcile bao nhiêu provider call? |
| Recovery | `compensation_pending_age_seconds` | Bù trừ đang chờ bao lâu? |

**Tên trên là gợi ý instrumentation**, không phải tên metric có sẵn của mọi NoSQL engine. Cần định nghĩa unit, sampling, source và áp dụng đúng trách nhiệm.

### Những tỷ lệ hữu ích

\[
\text{Cancel Completion Rate}
=
\frac{\text{số job yêu cầu hủy và cuối cùng kết thúc CANCELED}}
{\text{tổng job có yêu cầu hủy hợp lệ}}
\]

Tỷ lệ này cần cửa sổ thời gian và xử lý **pending jobs** rõ ràng; không được loại bỏ các yêu cầu chưa kết thúc mà không chú thích.

\[
\text{Unknown Outcome Rate}
=
\frac{\text{mutation attempts có kết quả unknown}}
{\text{tổng mutation attempts}}
\]

Một service có unknown rate cao có thể khiến người dùng retry, làm tăng chi phí và rủi ro duplicate. Nhưng một tỉ lệ thấp **không chứng minh** mọi hiệu ứng nghiệp vụ exactly-once; cần ledger/audit.

### Không đưa PII vào metric labels

Không dùng email, card number, raw `orderId` hàng triệu giá trị làm Prometheus label. Dùng service, operation, error class, route, region, job type; trace IDs chi tiết để trong log có phân quyền phù hợp.

## 39. Thử nghiệm fault injection: điều gì phải mô phỏng?

Thử trong **lab/staging với dữ liệu giả** và quyền phù hợp, không cố tình làm mất kết nối production.

### Ma trận thời điểm lỗi

| Lỗi được chèn | Trạng thái có thể xảy ra | Điều cần xác minh |
|---|---|---|
| Client abort trước send | Server chưa biết request | Không tạo effect nếu request thực sự chưa đi |
| Drop request trên network | Client timeout | Không tự chắc request chưa đến |
| Abort sau server nhận | Handler có thể tiếp tục | Cancellation propagation và resource cleanup |
| Drop response sau DB commit | Client unknown | Same ID retry không duplicate |
| Kill API process sau enqueue | Worker vẫn chạy | Durable job và status |
| Kill worker trước DB write | Job được retry | Lease/fencing và checkpoint |
| Kill worker sau DB write trước queue ACK | Message redelivery | Consumer idempotency |
| Cancel trong lúc COMMITTING | Có thể đã quá muộn | Hợp đồng response và compensation |
| Cancel sau external charge | Provider đã commit | Không double charge, refund workflow |
| Failover primary lúc ACK | Write có thể mơ hồ | Read/ledger reconciliation |
| Replica lag khi status read | Client tưởng chưa có kết quả | Read source đúng concern |
| Lease hết hạn rồi worker cũ hồi phục | Hai workers tranh job | Generation/fencing |
| TTL của ledger quá ngắn | Dedup entry biến mất | Không replay side effect cũ |

### Cách triển khai test

1. Tạo một `requestId` duy nhất và payload xác định.
2. Bật recorder cho invoke/complete của client, API, database và worker.
3. Cố tình làm mất **response sau khi server commit** bằng fault injection mô phỏng.
4. Đảm bảo client thấy timeout/canceled.
5. Retry cùng requestId, kiểm tra source/ledger chỉ có **một effect logic**.
6. Retry với requestId khác, xác minh đây được xử lý như một ý định mới hoặc bị invariant chặn.
7. Test cancel trước, trong và sau điểm COMMITTING.
8. Kiểm tra trạng thái cuối theo authoritative read, không chỉ UI.
9. Đo tài nguyên server có thật sự được giải phóng khi cancel read-only query.
10. Ghi rõ phạm vi engine, version, topology và các giả định.

### Phân biệt test behavior với chứng minh toàn hệ

Không thấy duplicate trong 100 lần thử không có nghĩa hệ **không bao giờ** có duplicate. Fault injection nên nhằm vào những cửa sổ race nguy hiểm, đồng thời kết hợp unique constraint/CAS và cách xử lý commit ambiguity đúng hợp đồng.

## 40. History recorder cần ghi gì?

Một record cho client request:

```json
{
  "runId": "cancel-test-001",
  "requestId": "checkout-M01-8e34",
  "attemptId": "attempt-2",
  "clientId": "C01",
  "operation": "CHECKOUT",
  "invokedAt": "2026-11-14T10:00:00.100Z",
  "clientAbortAt": "2026-11-14T10:00:01.000Z",
  "clientObservedResult": "CANCELED_WAIT",
  "serverReceivedAt": "2026-11-14T10:00:00.200Z",
  "dbCommitReference": "txn-101",
  "businessState": "COMMITTED",
  "workerState": "QUEUED"
}
```

Dữ liệu trên là **minh họa**; nhiều trường có thể phải lấy từ nhiều hệ và correlate sau. Không tự suy ra `dbCommitReference` nếu database không cung cấp.

### Phân biệt các mốc thời gian

- `clientAbortAt` là hành động ở client.
- `serverReceivedAt` là thời điểm server biết request.
- `dbCommitAt` (nếu có) là mốc thay đổi được commit theo storage semantics.
- `workerCompletedAt` là mốc xử lý nền hoàn tất.

Không so wall-clock trên nhiều host như một thứ tự tuyệt đối nếu đồng hồ chưa đồng bộ. Có thể ghi **causal handoff**, monotonic duration trong một process và operation IDs để xây dựng history đáng tin hơn.

### Cần log cả failures

Nếu chỉ log success response, trường hợp **commit thành công nhưng response mất** sẽ bị vô hình. Vì vậy cần ghi:

- Request created/sent/canceled.
- DB command started/result/timeout.
- Commit status known/unknown.
- Outbox enqueue/worker claim/result.
- Retry cùng ID hoặc ID khác.
- External provider reference và state.
- Cancellation flag/ack/terminal state.

## 41. Những hiểu nhầm thường gặp

| Ngộ nhận | Vì sao sai? | Cách hiểu đúng |
|---|---|---|
| “Bấm Hủy nên server dừng ngay” | UI chỉ hủy client wait | Server cancellation cần signal và hợp tác |
| “AbortController.rollback database” | AbortController xử lý fetch | Business rollback là API khác |
| “HTTP disconnect làm transaction abort” | Database có lifecycle độc lập | Xác minh commit/abort |
| “Timeout nghĩa write thất bại” | Response có thể mất sau commit | Unknown outcome + ledger |
| “Cancel Future(true) chắc interrupt remote write” | CompletableFuture không bảo đảm dừng supplier | Phân biệt future state và remote side effect |
| “orTimeout dừng server request” | Chỉ hết hạn future theo semantics Java | Truyền deadline và đo downstream |
| “Thread interrupt undo DB write” | Interrupt là best-effort | Không rollback commit |
| “Server gửi cancel thì query luôn dừng tức thì” | Engine có checkpoint/giới hạn | Đọc API và operation type |
| “Hủy transaction giống refund” | Refund là giao dịch mới | Compensation/ledger |
| “202 Accepted nghĩa job xong” | Chỉ chấp nhận xử lý | Poll terminal state |
| “cancelRequested=true nghĩa đã CANCELED” | Worker có thể chưa dừng | Terminal confirmation |
| “Kiểm tra cancel flag trước call là hết race” | Cancel có thể tới ngay sau check | CAS COMMITTING boundary |
| “Lease hết hạn thì worker cũ chết” | Worker cũ có thể hồi phục | Generation/fencing |
| “Redis cancel flag là authority bền” | TTL/replication/failover | Store authoritative durable state |
| “Retry POST với ID mới cũng là retry” | ID mới có thể tạo effect mới | Stable idempotency key |
| “Atomic INCR không thể double increment” | Hai attempts là hai INCR | Dedup logical operation |
| “GSI/search không thấy nên DB chưa commit” | Projection có thể lag | Read authoritative source |
| “Queue ACK đồng nghĩa business effect đúng một lần” | Crash giữa DB write/ACK có redelivery | Idempotent consumer |
| “Kafka exactly-once tự bao mọi payment provider” | Provider ngoài boundary | Provider idempotency/reconcile |
| “Cancel bulk update làm rollback mọi record đã đổi” | Có thể có partial progress | Checkpoint/compensation |
| “Một driver timeout áp giống nhau mọi NoSQL” | API và server semantics khác nhau | Đọc đúng driver/engine/version |
| “Chỉ cần tăng timeout là hết duplicate” | Unknown ACK vẫn có thể xảy ra | Idempotency và status |
| “Hệ khỏe lại thì không cần đối soát” | Job/provider vẫn có thể còn pending | Recovery và reconciliation |

## 42. Bài tập thực hành

### Bài 1 — Hai thế giới giống nhau với client

Client timeout sau `POST /orders`. Hãy vẽ hai timeline: request chưa tới server và request đã commit nhưng ACK bị mất. Vì sao client không thể chỉ dựa vào timeout để xác định kết quả?

### Bài 2 — Hủy future Java

Một `CompletableFuture` chạy `supplyAsync(() -> chargeCard())`. Caller gọi `cancel(true)`. Liệt kê ít nhất ba lý do card vẫn có thể bị charge. Những biện pháp nào cần ở provider/application?

### Bài 3 — HTTP và worker

API nhận `POST /exports`, ghi job và enqueue rồi client đóng tab. Worker tiếp tục chạy. Đây là bug hay thiết kế đúng? Nếu user muốn hủy export thật, bạn cần API và state machine nào?

### Bài 4 — Trả status đúng

Client gửi `POST /jobs/J1/cancel` khi job `RUNNING`. Handler đặt `cancelRequested=true`. Nên trả “Canceled” ngay hay “Cancellation requested”? Vì sao?

### Bài 5 — Cancel–commit race

Worker kiểm tra flag `false` rồi gọi payment provider. Cancellation handler đặt flag `true` đúng lúc ấy. Hãy thiết kế CAS `RUNNING→COMMITTING` và `RUNNING→CANCEL_REQUESTED`. Điều gì xảy ra với request thua?

### Bài 6 — Unknown provider outcome

Provider đã charge nhưng response mất, worker timeout. Nếu client yêu cầu cancel, hệ có nên gửi refund ngay không? Cần xác minh provider reference và các trạng thái `UNKNOWN/NEEDS_RECONCILIATION` thế nào?

### Bài 7 — MongoDB transaction

Một MongoDB transaction cập nhật order + request ledger trong cùng session. Commit response mất. Client tạo order ID mới rồi retry. Rủi ro là gì? Sử dụng idempotency ledger và driver transaction error labels ra sao?

### Bài 8 — DynamoDB ledger

Thiết kế một guard item theo `(tenantId,requestId)` với `ConditionExpression attribute_not_exists(PK)`. Nếu Put timeout rồi retry, vì sao gặp `ConditionalCheckFailed` chưa đủ để trả thành công mà cần đối chiếu payload và state?

### Bài 9 — Cassandra timeout

Coordinator gửi write tới ba replica, hai replica áp mutation, một replica trễ. Client timeout. Có thể kết luận không replica nào đã nhận không? Vì sao retry counter increment khác retry set cùng giá trị?

### Bài 10 — Redis INCR

Lệnh `INCR points:U1` thực thi nhưng response bị mất. Client gửi lại và điểm tăng hai lần. Hãy đề xuất ledger/atomic conditional operation đủ scope để mỗi logical request chỉ được cộng một lần.

### Bài 11 — Worker lease

A claim J1 generation 10, bị pause. Lease hết hạn, B claim generation 11. A tỉnh lại và định commit. Hãy giải thích fencing token phải được enforce ở đâu, vì sao check trong RAM không đủ.

### Bài 12 — Queue redelivery

Consumer ghi document thành công rồi crash trước khi commit offset. Broker giao lại cùng message. Thiết kế dedup theo eventId và transaction/outbox hoặc conditional update phù hợp.

### Bài 13 — Bulk operation

Một batch job đã commit 30.000/100.000 record khi user hủy. Hãy thiết kế response terminal trung thực, checkpoint, resume và compensation nếu cần. Có được nói “đã rollback toàn bộ” không?

### Bài 14 — Read status từ replica trễ

Primary có order v8 COMMITTED, replica có v7, search chưa có order. Client timeout rồi query search thấy empty. Những hành động sai có thể xảy ra? Status endpoint cần dùng authority nào?

### Bài 15 — Timeout budget

Gateway timeout 3 giây, service gọi DB timeout 4 giây rồi payment provider timeout 5 giây. Vì sao tổng thời gian/tải có thể vượt kỳ vọng? Thiết kế một cách truyền remaining deadline nhưng vẫn giữ idempotency.

### Bài 16 — API design

Thiết kế endpoints tạo job, đọc status và yêu cầu cancel. Nêu các response cho `QUEUED`, `RUNNING`, `COMMITTING`, `SUCCEEDED`, `CANCELED` và việc user không có quyền.

### Bài 17 — Test trong lab

Tạo một fault injection làm mất response **ngay sau DB commit**, rồi retry cùng requestId. Nêu các trường log cần thu thập và điều kiện đánh giá “không duplicate business effect”.

### Bài 18 — SLO và monitoring

Thiết kế dashboard phân biệt **client-aborted**, **server-canceled**, **job-canceled-terminal**, **unknown commit**, **retry dedup** và **external compensation**. Vì sao chỉ metric HTTP 499 không đủ?

### Bài 19 — Hủy công việc nền sau deploy

Một app instance đã triển khai phiên bản mới, trong khi worker phiên bản cũ giữ lease và tiếp tục xử lý job. Thiết kế generation/fencing, kiểm tra version schema và quy trình drain workers để không ghi sai.

### Bài 20 — Quyết định nghiệp vụ

So sánh một request search autocomplete, một request giữ ghế và một request thanh toán. Khi user bấm “Hủy”, thao tác nào nên dừng best-effort, thao tác nào cần status/commit barrier, thao tác nào cần compensation? Giải thích dựa trên bất biến nghiệp vụ.

## 43. Checklist thiết kế trước khi triển khai

1. **Cancel mang nghĩa gì?** Ngừng chờ ở UI, hủy RPC, dừng query, hủy job hay hủy nghiệp vụ?
2. **Request đã tới server chưa?** Nếu không rõ, xử lý như outcome có thể mơ hồ.
3. **Có điểm commit không thể đảo ngược không?** Nêu nó trong state machine.
4. **Deadline có truyền xuống các tầng không?** Biết từng timeout có thể và không thể dừng gì.
5. **Transaction abort được hỗ trợ ở đâu?** Không giả định rollback external provider.
6. **Idempotency key có ổn định giữa retry không?** Có kiểm tra payload/tenant?
7. **Request ledger có bền không?** Retention đủ cho retry và replay muộn?
8. **Có endpoint tra trạng thái từ nguồn có thẩm quyền không?** Không dựa vào stale GSI/search.
9. **Cancel được lưu bền và xác nhận terminal thế nào?** Tách `CANCEL_REQUESTED` khỏi `CANCELED`.
10. **Worker kiểm tra cancel ở checkpoint nào?** Có thể dừng an toàn trước bước nào?
11. **Có CAS/fencing khi worker lease hết hạn không?** Worker cũ không được ghi tiếp.
12. **External call có idempotency/reference và reconciliation không?**
13. **Queue redelivery và outbox replay có làm side effect trùng không?**
14. **Bulk job có lưu partial progress/checkpoint không?**
15. **UI có phân biệt “ngừng chờ” với “hủy đơn” không?**
16. **Client có bounded retry/backoff không?** Tránh retry storm.
17. **Log có đủ requestId, attemptId, operationId, commit status không?**
18. **Có fault injection ở những thời điểm nguy hiểm không?** Đặc biệt sau commit nhưng trước ACK.
19. **SLO có đo hủy thực sự hoàn tất không?** Không chỉ client aborted.
20. **Có runbook bù trừ và đối soát sau sự cố không?**

## 44. Tổng kết

Trong NoSQL và các hệ phân tán, một request đi qua nhiều vòng đời độc lập: **client, transport, application handler, database operation, transaction, queue, worker và external provider**. Việc một tầng hủy không buộc những tầng khác hủy thành công.

Những nguyên tắc cần nhớ:

1. **Client-side cancel không đồng nghĩa server-side stop.** Hủy `fetch` hoặc `Future` có thể chỉ chấm dứt việc chờ kết quả.
2. **Timeout không có nghĩa write chưa commit.** Response có thể mất sau khi database đã ghi thành công; phải xử lý unknown outcome.
3. **Server cancellation là best-effort nếu operation chưa tới điểm có thể dừng.** Một số query có thể dừng, nhưng write/transaction đã commit không tự rollback.
4. **Transaction abort, business cancellation và compensation khác nhau.** Hoàn tiền là giao dịch mới, không xóa lịch sử charge.
5. **Background job tồn tại độc lập với HTTP.** Muốn hủy thật cần API, durable state machine, checkpoints và xác nhận terminal.
6. **Race giữa cancel và commit phải có điểm phân xử nguyên tử.** Dùng conditional transition/CAS, generation/fencing và authority phù hợp.
7. **Idempotency bảo vệ retry.** Một logical operation có thể có nhiều attempts; giữ cùng requestId, ledger và provider reference.
8. **Tìm trạng thái từ nguồn đủ mạnh.** Search, cache và secondary replica trễ có thể làm client tưởng write chưa xảy ra.
9. **Giám sát không chỉ số request bị hủy.** Phải biết server còn chạy bao lâu, bao nhiêu job thật sự dừng, bao nhiêu kết quả commit còn mơ hồ và bao nhiêu effect phải bù trừ.
10. **Kiểm thử đúng điểm lỗi.** Đặc biệt mô phỏng mất ACK sau commit, worker crash trước queue ACK, lease hết hạn và cancellation đến sau bước không thể đảo ngược.

Quy tắc quan trọng nhất:

> **“Tôi không còn chờ kết quả” không có nghĩa “máy chủ không còn làm việc”; “máy chủ đã nhận yêu cầu hủy” không có nghĩa “công việc chưa từng commit”.** Hãy định nghĩa cancellation ở từng ranh giới, giữ bằng chứng kết quả bằng requestId và chỉ hứa “đã hủy” khi trạng thái nghiệp vụ thực sự được xác nhận.

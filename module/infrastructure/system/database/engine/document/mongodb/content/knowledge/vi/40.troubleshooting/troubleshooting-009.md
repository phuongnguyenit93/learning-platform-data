# Timeout xác nhận ghi hoặc commit với kết quả chưa xác định trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Xử lý sự cố  
> **Bài học:** Timeout xác nhận ghi hoặc commit với kết quả chưa xác định

## 1. Một timeout có thể tạo ra hai lỗi nghiêm trọng

Hãy tưởng tượng ứng dụng thanh toán gửi yêu cầu cập nhật đơn hàng qua MongoDB. Ứng dụng chờ vài giây rồi nhận exception:

```text
Client                  MongoDB primary             Secondaries
   |                           |                         |
   | update order status       |                         |
   |-------------------------->|                         |
   |                           | apply update            |
   |                           |---- replicate ---------->|
   |                           |                         |
   |         network timeout   |                         |
   |<-------------------------X|                         |
   |                           | replication continues   |
```

Có hai cách xử lý sai:

- **Sai lầm 1 — Coi timeout là rollback:** gửi lại lệnh `$inc` không có khóa chống lặp, khiến số dư hoặc số lần thanh toán bị tăng hai lần.
- **Sai lầm 2 — Coi timeout là thành công:** trả success, xóa công việc khỏi hàng đợi, trong khi transaction có thể chưa commit hoặc write có thể bị rollback sau failover.

**Timeout chỉ nói rằng một thời hạn chờ đã hết; không tự chứng minh dữ liệu đã được ghi hay chưa.** Phân biệt nơi timeout xảy ra mới cho biết điều nào có thể khẳng định.

### 1.1. Tình huống xuyên suốt

Dịch vụ `OrderService` nhận một command:

```json
{
  "requestId": "pay-confirm-20261114-A100",
  "tenantId": "tenant-demo",
  "orderId": "A100",
  "newStatus": "PAID"
}
```

Một yêu cầu này có thể dẫn tới:

1. Cập nhật `orders.status`.
2. Tăng số liệu tổng hợp.
3. Ghi một event/outbox.
4. Xác nhận kết quả cho HTTP client.

Nếu client mất kết nối trong lúc `updateOne()` hoặc `commitTransaction()`, hệ thống cần biết **được làm gì tiếp** để không làm sai nghiệp vụ.

### 1.2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt timeout của network, driver, server, write concern và transaction commit.
2. Hiểu `w:1`, `w:"majority"`, `j:true` và `wtimeout`, không đánh đồng acknowledged với applied hay durable.
3. Giải thích vì sao `writeConcernError` có thể đi kèm write đã áp dụng trên primary.
4. Phân biệt `TransientTransactionError` với `UnknownTransactionCommitResult`.
5. Hiểu cơ chế retryable writes và giới hạn của `retryWrites=true`.
6. Thiết kế command idempotent bằng `requestId`, unique key, CAS và operation ledger.
7. Đối soát trạng thái khi kết quả là **unknown**, kể cả khi document chưa nhìn thấy trên secondary.
8. Chọn phương án retry commit **của cùng transaction** thay vì vô tình chạy lại side effects.
9. Xử lý partial success trong `bulkWrite` hoặc `insertMany`.
10. Thiết kế logs/metrics, runbook, điều kiện escalation và lab an toàn không phá replica set.
11. Tích hợp Java Sync Driver với exception labels, timeouts và transaction callbacks.
12. Giải thích giới hạn của mọi cơ chế khi kết quả đã nằm ngoài MongoDB, như thanh toán/email.

## 2. Năm trạng thái cần phân biệt

Một operation gửi từ application có thể rơi vào nhiều trạng thái:

| Trạng thái | Ý nghĩa | Có được giả định từ timeout? |
| --- | --- | --- |
| `NOT_SENT` | Client chưa gửi command | Chỉ khi ứng dụng có bằng chứng chắc chắn |
| `NOT_APPLIED` | Server chắc chắn không áp dụng | Cần lỗi/bằng chứng phù hợp, không suy từ timeout chung |
| `APPLIED_ON_PRIMARY` | Primary đã thay đổi dữ liệu | Có thể chưa đạt majority/journal theo contract |
| `COMMITTED_DURABLY` | Đã được xác nhận theo durability contract | Cần acknowledgment hoặc read/reconciliation đủ mạnh |
| `UNKNOWN` | Client chưa có bằng chứng kết quả cuối | **Trạng thái mặc định hợp lý khi timeout mơ hồ** |

Không nên biến `UNKNOWN` thành `FAILED` bằng một dòng:

```java
catch (MongoException e) {
    return PaymentStatus.FAILED;
}
```

Nhiều exception cho biết **không thể xác nhận**, không cho biết **không có tác dụng**.

### 2.1. Hai chiều khác nhau: apply và acknowledge

```text
                                  ACK?
                          No                  Yes
Applied?     No       Not applied         N/A (normal write protocol)
             Yes      Applied, ACK lost   Applied, acknowledged
```

Trong ô “Applied, ACK lost”, application có thể thử lại cùng request và tạo side effect trùng nếu không có idempotency. Với transactions, “committed but ACK lost” là trường hợp điển hình của `UnknownTransactionCommitResult`.

### 2.2. Thêm chiều durability/failover

`APPLIED_ON_PRIMARY` chưa chắc là `MAJORITY_COMMITTED`. Một write `w:1` có thể đã xuất hiện trong primary rồi bị rollback nếu primary failover trước khi write được sao chép đủ.

Với `wtimeout` cho `w:"majority"`, việc primary đã apply write **không đồng nghĩa** majority ack; write có thể tiếp tục replicate và cuối cùng đạt majority, hoặc trong tình huống failover có thể bị rollback.

Một GET ngay sau timeout **không đủ** để xác nhận cùng mức durability nếu nó đọc `local` hoặc đọc từ một secondary chưa bắt kịp.

## 3. Các loại timeout: đừng gộp vào một nhãn

| Loại | Nơi thời hạn hết | Thông tin có thể suy ra | Bẫy |
| --- | --- | --- | --- |
| Connection establishment timeout | Kết nối chưa hoàn thành | Có thể command chưa được gửi, nhưng cần context | Tưởng mọi lỗi mạng đều trước lúc gửi |
| Server selection timeout | Driver không tìm server phù hợp | Driver có thể chưa gửi attempt đang xét | Những attempt trước có thể đã xảy ra nếu retry |
| Socket/read timeout | Chờ response trên connection | Server có thể đã apply/commit | Tự gửi lại không idempotent |
| Client-side operation deadline `timeoutMS` | Tổng operation hết thời gian | Có thể đã gửi một hoặc nhiều attempts | Không đồng nghĩa transaction abort |
| Write concern timeout `wtimeout` | Chờ yêu cầu `w` được thỏa sau khi primary áp dụng | Data modifications trước đó **không bị tự undo** | Ghi lại nghiệp vụ lần hai |
| Server-side operation time limit `maxTimeMS` | Server chặn execution vượt hạn ở operations hỗ trợ | Tùy operation/phase; không được suy mọi side effect rollback | Coi maxTimeMS như write-concern timeout |
| Transaction commit uncertainty | Thời điểm `commitTransaction` phản hồi không chắc | Transaction có thể đã commit hoặc chưa | Chạy lại transaction body thay vì retry commit |
| HTTP proxy/gateway timeout | API client hết hạn chờ | API handler có thể vẫn đang ghi | HTTP client retry thành request mới |

### 3.1. Write concern timeout được áp ở giai đoạn nào?

Đối với write concern `w > 1`, `wtimeout` giới hạn thời gian chờ đủ thành viên xác nhận **sau khi operation được áp dụng trên primary**.

Ví dụ:

```javascript
db.orders.insertOne(
  {
    _id: "order-timeout-example",
    status: "CREATED"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 2500
    }
  }
);
```

Nếu không đạt majority trong 2,5 giây, MongoDB có thể trả **write concern error**, nhưng **không tự hoàn tác những thay đổi đã áp dụng**.

Theo tài liệu, `wtimeout` không áp dụng khi `w <= 1`. Đừng giải thích `wtimeout:2500` như “primary có tối đa 2,5 giây để thực hiện mọi logic”. Muốn giới hạn toàn operation, xem API `timeoutMS`/max time được hỗ trợ và semantics của từng driver, không coi đó là phép rollback an toàn.

### 3.2. Write concern error khác write error

Trong response của một số commands:

```javascript
{
  ok: 1,
  n: 1,
  writeConcernError: {
    code: 64,
    codeName: "WriteConcernFailed",
    errmsg: "waiting for replication timed out",
    errInfo: {
      wtimeout: true
    }
  }
}
```

Đây là **minh họa cấu trúc response**, code/fields có thể khác theo phiên bản. Nó gợi ý command đã thực hiện phần write trên primary nhưng chưa đạt write concern. Khác với lỗi như duplicate key hoặc validation failure, vốn có thể từ chối một write trước khi nó hoàn tất.

Tuy nhiên, không có `writeConcernError` **không** chứng minh write được majority acknowledged nếu client chỉ dùng `w:1`.

### 3.3. Vì sao bỏ `wtimeout` có thể nguy hiểm?

Nếu cấu hình `w` không thể thỏa và không có timeout tương ứng, request có thể đợi lâu trong write concern phase. Nhưng đặt timeout ngắn tùy tiện sẽ tăng số kết quả **chưa xác định** cần reconciliation.

Cần lựa chọn theo:

- SLO ứng dụng.
- RTT và replication lag bình thường.
- Thời hạn của gateway và queue.
- Availability của replica set.
- Business requirement về durability.
- Khả năng reconcile an toàn nếu timeout.

Không giải quyết sự cố bằng cách hạ `w:"majority"` về `w:0` trên đường thanh toán quan trọng.

## 4. Write concern: “đã ghi” nghĩa là gì?

### 4.1. `w:0`

Client không yêu cầu server acknowledgment cho kết quả write. Đây là **unacknowledged write**, không phù hợp khi ứng dụng cần biết dữ liệu đã được lưu để thực hiện nghiệp vụ tiếp theo; driver không có đầy đủ result để xác nhận.

Retryable writes thông thường **không áp dụng** cho write concern `w:0`.

### 4.2. `w:1`

Primary xác nhận theo semantics của write concern, thường không cần đa số replicas. Đây là mức có latency thấp hơn trong nhiều trường hợp nhưng một write đã acknowledged vẫn có thể bị rollback sau failover nếu chưa được replicated.

Không gọi mọi `w:1` acknowledgment là “durable across failover”.

### 4.3. `w:"majority"`

Server chờ đáp ứng yêu cầu majority theo topology. Tùy phiên bản/config, MongoDB liên kết majority ack với journal durability, gồm `writeConcernMajorityJournalDefault`.

**Khác biệt phiên bản:** từ MongoDB 8.0, majority acknowledgment dựa trên việc đa số data-bearing voting members đã ghi bền oplog entry; những secondary members có thể apply thay đổi vào collection bất đồng bộ sau đó. Vì vậy một immediate read từ secondary không nhất thiết nhìn thấy dữ liệu trong collection ngay sau majority acknowledgment. Khi cần read-your-writes giữa members, dùng causal consistency/read concern phù hợp.

### 4.4. `j:true`

`j:true` yêu cầu journal sync theo semantics write concern. Nó không tự thay thế `w:"majority"` về replication/failover guarantee.

Ví dụ:

```javascript
{
  w: "majority",
  j: true,
  wtimeout: 5000
}
```

Đây là một yêu cầu durability mạnh thường gặp, nhưng vẫn có thể timeout nếu cluster unhealthy. Timeout ấy **không** làm MongoDB tự xóa write đã có trên primary.

### 4.5. Defaults không được đoán

Write concern mặc định phụ thuộc server version, implicit default write concern, replica set với arbiters, cluster/Atlas policy và client/session config.

Trước khi điều tra, phải ghi nhận **effective write concern** chứ không suy từ việc Java code không gọi `withWriteConcern(...)`. Một số deployment có default majority; một số khác có quy tắc khác.

## 5. Ba dòng thời gian để hiểu trạng thái không rõ

### 5.1. Kịch bản A — Write đã được primary apply, majority chưa xác nhận

```text
T0 Client -> updateOne (w:majority, wtimeout:2000)
T1 Primary applies update
T2 Replication blocked / secondaries slow
T3 2000 ms elapsed -> writeConcernError
T4 Client reports ambiguous result
T5 Replication catches up, write becomes majority committed
```

Nếu client retry bằng lệnh `$inc` mới ở T4, có thể tăng hai lần. Nếu client báo `FAILED` cho nghiệp vụ, một transaction đã xảy ra có thể bị coi là chưa thực hiện.

### 5.2. Kịch bản B — ACK bị mất trên mạng

```text
T0 Client sends insertOne(_id = order-A100)
T1 Server inserts document
T2 Server sends success response
T3 Connection breaks before response reaches client
T4 Driver/application sees network error
```

Trên server, operation đã thành công. Nếu client gửi **một insert mới với ObjectId mới**, có thể tạo duplicate business record. Nếu giữ cùng deterministic `_id` hoặc unique `requestId`, lần gửi lại có cơ chế phát hiện kết quả đã tồn tại.

### 5.3. Kịch bản C — Commit thành công, response mất

```text
T0 startTransaction
T1 insert ledger / update order / add outbox
T2 commitTransaction sent
T3 Transaction commit succeeds
T4 Commit response lost or timeout
T5 Driver sees UnknownTransactionCommitResult
```

Không bắt đầu **transaction mới** để chạy lại từ T0 chỉ vì T5. Cần xử lý `UnknownTransactionCommitResult` bằng **retry commit của cùng transaction/session**, sau đó reconciliation nếu deadline hết.

## 6. Lỗi `UnknownTransactionCommitResult`

### 6.1. Error label diễn đạt điều gì?

Khi driver trả lỗi có label:

```text
UnknownTransactionCommitResult
```

nó nói **kết quả của commit transaction chưa chắc chắn đối với client**. Nó **không** nói transaction đã abort, cũng không nói chắc chắn đã commit.

MongoDB hỗ trợ retry `commitTransaction` theo transaction identity hiện hữu, giúp tìm/hoàn tất quyết định commit mà không chạy lại body như một transaction mới.

### 6.2. Retry commit khác retry transaction

| Trường hợp | Hành động đúng về nguyên tắc |
| --- | --- |
| Lỗi được gắn `TransientTransactionError` trong body | Có thể chạy lại **toàn transaction** với transaction/session được quản lý đúng |
| Commit trả `UnknownTransactionCommitResult` | Retry **commit cùng transaction**, không chạy body mới |
| Commit trả lỗi xác định non-resumable | Phân loại theo code/label và trạng thái; có thể cần reconciliation |
| Mất connection kéo dài, không lấy được kết quả commit | Đánh dấu **UNKNOWN**, đối soát bằng business ID/ledger |
| External side effect đã chạy trong callback | Rủi ro duplicate khi callback retry; phải tách sang outbox |

### 6.3. Retry commit bằng cùng identity

Một transaction trong driver gắn với logical session (`lsid`) và transaction number (`txnNumber`). Retry commit thông qua **cùng ClientSession đang đại diện transaction ấy** là điều quan trọng.

Không tự tạo `MongoClient`/`ClientSession` khác rồi gửi một transaction mới có cùng business payload và gọi đó là “retry commit”.

### 6.4. Driver có thể tự retry commit

MongoDB drivers có quy tắc retry commit, kể cả khi connection option `retryWrites=false` trong các điều kiện được specification hỗ trợ. Với Java Sync Driver, **`ClientSession.withTransaction()`** là callback API có logic retry cho các labels liên quan, trong đó:

- `TransientTransactionError`: có thể retry whole transaction.
- `UnknownTransactionCommitResult`: retry commit.

Callback API không bảo đảm vượt qua mọi lỗi vĩnh viễn, deadline, business side effect, hoặc thiếu oplog/history; application vẫn cần reconciliation khi kết quả cuối cùng không có bằng chứng.

### 6.5. Commit timeout có thể tốn thời gian do cluster

Trong sharded cluster, commit liên quan đến transaction coordinator và các shards. Một vài giai đoạn có yêu cầu majority/journal nội bộ dù application cấu hình `w` khác. Commit transaction có thể chậm khi:

- Participants/shards chậm hoặc unreachable.
- Replication/journal lag.
- Network partition hoặc failover.
- Transaction lớn và write conflict.
- Disk/CPU/lock pressure.
- Cluster đang maintenance/resharding/DDL.

Không suy một cách máy móc “primary có CPU thấp, commit timeout chắc chắn là lỗi Java thread”.

## 7. `TransientTransactionError`: trường hợp nên retry body

### 7.1. Ý nghĩa

Lỗi có label `TransientTransactionError` trong transaction thường chỉ ra một lỗi tạm như primary stepdown/write conflict mà transaction có thể không hoàn tất như dự kiến, và **toàn transaction có thể được retry** theo hướng dẫn driver.

Nhưng callback có thể được thực thi lại, nên body phải **an toàn khi chạy lại**.

### 7.2. Không có nghĩa mọi MongoDB exception đều retryable

Ví dụ:

- `DuplicateKey` do business key thực sự đã tồn tại.
- `DocumentValidationFailure` vì BSON type sai.
- Unsupported collection/index/DDL operation.
- Authorization error.
- Transaction quá lớn không thể vừa cache (`TransactionTooLargeForCache` trên MongoDB 6.2+).
- Logic nghiệp vụ ném exception.

Những lỗi này thường cần sửa dữ liệu/config/code, không tự biến mất khi retry vô hạn.

### 7.3. Sai lầm khi retry body sau unknown commit

```java
try {
    session.commitTransaction();
} catch (MongoException e) {
    // SAI nếu commit outcome chưa chắc chắn:
    runNewTransactionThatIncrementsBalanceAgain();
}
```

Nếu commit đầu đã thành công, transaction mới sẽ áp thêm effects. Với `$inc` số dư, một transaction lặp mới có thể khiến balance sai.

## 8. Retryable writes: lợi ích và giới hạn

### 8.1. Cơ chế

Retryable writes giúp MongoDB official drivers tự thử lại những single-document write operations đủ điều kiện khi gặp một số network/election errors.

Một request được driver định danh qua logical session + transaction number/statement identity, để server có thể nhận diện retry của cùng operation theo protocol.

Trong các version/topology hỗ trợ:

```text
Java Driver (retryWrites=true)
     |
 first attempt (lsid, txnNumber)
     |
 network/election error
     |
 retry eligible operation
 (same logical statement identity)
     |
 server recognizes/replies without blindly applying twice
```

Các yếu tố cần thiết:

- Replica set hoặc sharded cluster, không standalone.
- Driver/server tương thích.
- Acknowledged writes (không `w:0`).
- Write operation nằm trong nhóm hỗ trợ.
- Retention của logical session/transaction history còn hợp lệ.

### 8.2. Các operations thường đủ điều kiện

Những lệnh single-document phổ biến:

- `insertOne`.
- `updateOne`.
- `replaceOne`.
- `deleteOne`.
- `findOneAndUpdate`/`findOneAndReplace`/`findOneAndDelete`.
- Một số batch `insertMany`/`bulkWrite` có các statements đủ điều kiện, theo version/specification.

Không mặc định `updateMany`/`deleteMany` được retryable writes bảo vệ như single-document statements. Với multi-document transactions, **individual writes trong transaction không tự retry như outside transaction**; phải xử lý transaction labels/commit.

### 8.3. Số lần retry tùy phiên bản và timeout model

Tài liệu mô tả mặc định driver thường retry một lần; với client-side operation `timeoutMS`, có thể retry nhiều lần cho tới khi operation thành công, gặp lỗi không retryable hoặc hết deadline.

Không hardcode “retryable writes luôn chỉ 1 lần” hoặc “retry vô hạn”. Đọc đúng Java Driver version, connection options và driver specification.

### 8.4. `NoWritesPerformed` từ MongoDB 6.1+

Nếu cả hai attempts của retryable write thất bại **mà không có write nào được thực hiện**, server có thể trả error label:

```text
NoWritesPerformed
```

Đây là bằng chứng hữu ích **khi label thực sự xuất hiện và server/operation phù hợp**. Ngược lại, **không có label không chứng minh write đã được thực hiện**. Với batch, partial success là một khả năng.

Không tự dựng label này dựa trên loại exception hoặc message; chỉ đọc label do driver/server trả.

### 8.5. Driver retry không thay idempotency nghiệp vụ

Nếu một HTTP client không nhận response, nó gửi **request mới** tới API, và API tạo **MongoDB operation mới** với `_id` ngẫu nhiên, driver chỉ thấy một request mới. Retryable writes ở lớp driver không biết hai HTTP requests là cùng một nghiệp vụ.

Do đó vẫn cần:

- Idempotency key ổn định từ client/API.
- Unique business key hoặc request ledger.
- Không sinh `ObjectId` mới cho cùng command khi retry.
- Atomic conditional updates.
- Quy trình đối soát kết quả chưa xác định.

## 9. Write concern error và retryable writes không đồng nghĩa

Một write có thể thành công trên primary nhưng `wtimeout` chưa thỏa. Đây không phải mọi trường hợp đều được driver tự retry theo cùng cách như network error.

Hãy xem:

- Exception class (ví dụ `MongoWriteConcernException`).
- Write concern error/code/errInfo.
- Retryable/transaction error labels nếu có.
- Lệnh thuộc loại retryable hay không.
- Số attempts và timeout model.
- Trạng thái database sau một phép read phù hợp.

**Không viết “catch mọi `MongoException` rồi gọi lại `updateOne` ngay”.** Việc retry từ application có thể tạo logical request mới khác protocol retry của driver.

## 10. Mẫu kiểm soát lỗi: tách transport, write, commit, business

Một chiến lược xử lý:

```text
                 MongoDB operation outcome
                          |
                  +-------+-------+
                  |               |
              Success         Exception/error
                  |               |
                  v               v
           Confirmed state     Classify phase
                                  |
              +-------------------+----------------+
              |                   |                |
         Deterministic      Retryable/transient    Unknown
          rejection           at supported level  |
              |                   |                v
              v                   v           Reconcile by
        Return business       Bounded retry     requestId/outbox
          failure             with identity     + durable reads
                                  |                |
                                  +--------+-------+
                                           |
                                    final decision /
                                      manual queue
```

**Thứ tự ưu tiên:** bảo toàn nghiệp vụ trước, giảm latency sau. Đặc biệt với payment, inventory, quota, points, counters và email.

## 11. Idempotency key: ràng buộc theo command, không theo request retry

### 11.1. Tại sao cần `requestId`?

Hai HTTP requests:

```text
POST /orders/A100/pay
Idempotency-Key: pay-A100-20261114-01
```

phải được nhận diện là **cùng một command**, kể cả khi lần thứ hai đến sau timeout hoặc pod restart.

Nếu client tạo idempotency key mới khi retry, database khó phân biệt request mới có chủ ý với request cũ bị lặp.

### 11.2. Lưu request ledger

Một collection `operations`:

```javascript
{
  _id: "pay-A100-20261114-01",
  tenantId: "tenant-demo",
  orderId: "A100",
  requestHash: "sha256-of-canonical-business-payload",
  state: "CONFIRMED",
  result: { orderId: "A100", status: "PAID" },
  createdAt: ISODate("2026-11-14T00:00:00Z"),
  finishedAt: ISODate("2026-11-14T00:00:02Z")
}
```

Unique `_id` bảo vệ mỗi idempotency key. `requestHash` giúp phát hiện cùng key nhưng **payload khác**, phải trả conflict thay vì âm thầm chấp nhận.

### 11.3. Trạng thái ledger không được đánh dấu quá sớm

```text
RECEIVED
   |
   v
PROCESSING
   |
   +----> CONFIRMED (có bằng chứng side effect đã bền vững)
   |
   +----> REJECTED (đã xác định nghiệp vụ không áp dụng)
   |
   +----> NEEDS_RECONCILIATION (kết quả chưa chắc chắn)
```

Không set `CONFIRMED` khi chỉ vừa gửi command nhưng chưa có ACK/commit hoặc evidence tương ứng.

### 11.4. Ledger và business write phải có atomicity

Sai:

```text
1. Insert ledger state=CONFIRMED
2. Crash
3. Update order chưa thực hiện
```

Lần retry sẽ thấy `CONFIRMED` và bỏ qua, khiến dữ liệu kinh doanh không khớp.

Tốt hơn nếu cả ledger và order đều ở cùng MongoDB deployment:

- Transaction ngắn ghi **cả order và ledger**.
- Commit với write concern phù hợp.
- Retry theo transaction labels.
- Reconcile sau unknown commit.

Nếu không dùng transaction, cần protocol phân trạng thái, CAS/outbox và reconciliation có thể chứng minh không mất work. Không xem hai single writes rời nhau là atomic chỉ vì dùng cùng collection name prefix.

## 12. Tránh `$inc` bị áp dụng hai lần

### 12.1. Update không idempotent

```javascript
db.accounts.updateOne(
  { _id: "account-demo" },
  { $inc: { balanceCents: NumberLong("5000") } }
);
```

Nếu application gửi hai **logical operations khác nhau** sau một timeout, số dư tăng hai lần.

### 12.2. `$set` có thể idempotent về state nhưng chưa đủ

```javascript
db.orders.updateOne(
  { _id: "A100" },
  { $set: { status: "PAID" } }
);
```

Chạy hai lần có thể cho cùng status, nhưng vẫn có bẫy:

- `updatedAt: new Date()` thay đổi.
- Event/outbox phát hai lần.
- Một concurrent transition `CANCELLED` bị ghi đè về `PAID`.
- Counter/notification nằm ở operation khác.
- Version/audit fields tăng hai lần.

Một update chỉ idempotent khi **toàn bộ business effect** của retry không đổi, không chỉ một field cuối có giá trị giống nhau.

### 12.3. Compare-and-set

```javascript
db.orders.updateOne(
  {
    _id: "A100",
    tenantId: "tenant-demo",
    status: "CREATED",
    version: NumberInt(7)
  },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  }
);
```

Nếu lần đầu đã thành công, lần hai không match vì status/version đổi. Nhưng `matchedCount:0` vẫn cần phân biệt:

- Request cũ đã hoàn tất.
- Request khác đổi order sang state khác.
- ID/tenant sai.
- Dữ liệu đã bị xóa/rollback.
- Version thay đổi vì operation khác.

CAS giúp tránh **ghi đè/lặp update**, nhưng không tự trả lời “ai đã làm thay đổi trước đó”. Cần `requestId`/audit ledger để xác định.

### 12.4. Deterministic upsert theo request

Có thể ghi:

```javascript
db.requestLedger.updateOne(
  { _id: "pay-A100-20261114-01" },
  {
    $setOnInsert: {
      tenantId: "tenant-demo",
      orderId: "A100",
      requestHash: "hash-v1",
      state: "RECEIVED",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
```

Khi retry cùng `_id`, server có thể gặp record đã có và không tạo mới. Tuy nhiên **thao tác upsert ledger không làm payment side effect tự atomic**, và cần xử lý unique race/duplicate key/đối chiếu requestHash.

## 13. HTTP API có trạng thái UNKNOWN

### 13.1. Không trả `200 Success` khi chưa có bằng chứng

Một response chiến lược có thể là:

```json
{
  "requestId": "pay-A100-20261114-01",
  "state": "PENDING_RECONCILIATION",
  "message": "Chưa xác nhận được kết quả cuối cùng; có thể tra cứu lại theo requestId."
}
```

Tùy thiết kế API, có thể trả HTTP `202 Accepted` khi command đã được nhận và sẽ tiếp tục xử lý/đối soát. Nhưng nếu request **chưa chắc đã được nhận bền vững**, đừng phát một trạng thái accepted đánh lừa client. Có thể trả lỗi transient kèm idempotency key và endpoint truy vấn trạng thái.

### 13.2. Tra cứu theo command ID

```text
GET /operations/pay-A100-20261114-01
```

Ứng dụng đọc ledger/projection và trả:

- `CONFIRMED`.
- `REJECTED` có nguyên nhân rõ.
- `PENDING`.
- `NEEDS_RECONCILIATION`.
- `NOT_FOUND` nhưng **không suy ngay rằng write trước chắc chắn chưa xảy ra** nếu commit hoặc replication chưa xác định.

### 13.3. Retry từ mobile/browser phải giữ key

Nếu mạng di động mất kết nối, client có thể retry. Key phải được giữ qua retry và có TTL/retention phù hợp vòng đời nghiệp vụ. Không tạo key mới trong mỗi attempt.

Không đưa key chứa PII, mật khẩu hoặc số thẻ vào URL/log; key nên là opaque identifier và kiểm ownership/authorization trước khi trả trạng thái.

## 14. Quy trình đối soát sau timeout

### 14.1. Một phép `findOne` không luôn đủ

Sau một `wtimeout`, query có thể thấy document trên primary nhưng write chưa đạt majority. Ngược lại, một majority read chưa thấy document chưa chứng minh write sẽ không đạt majority sau đó.

Đối soát cần tách:

- **Visibility:** một read hiện thấy gì?
- **Durability:** trạng thái đã đạt write/read concern mong muốn chưa?
- **Identity:** thay đổi có do đúng `requestId` không?
- **Business effect:** trạng thái cuối, ledger, outbox/counters có khớp không?
- **Time:** còn các attempts/replication tiến hành không?

### 14.2. Quy trình thận trọng

```text
Timeout / unknown result
          |
          v
Stop unsafe duplicate submission
          |
          v
Find requestId / deterministic business key
          |
          v
Read primary with appropriate readConcern/session
          |
          +-- found same request, durable evidence?
          |          |
          |          +-- yes -> CONFIRMED
          |
          +-- found conflict/different payload?
          |          |
          |          +-- yes -> CONFLICT / investigation
          |
          +-- not found or durability unclear
                     |
                     v
             bounded retry / monitor
                     |
                     v
             reconcile ledger, history,
               outbox and business source
                     |
                     v
            confirmed/rejected/UNKNOWN
```

Khi được phép, đặt read concern `majority` để tìm trạng thái majority committed. Nhưng cần hiểu semantics của read concern và read preference theo MongoDB version. Một read từ secondary có thể bị lag; ưu tiên primary hoặc dùng causally consistent session khi yêu cầu read-your-writes.

### 14.3. Không dùng absence làm bằng chứng âm tuyệt đối

Giả sử ở T0 write bị wtimeout và T1 một query `find({requestId})` trả null. Điều đó chỉ nói **trong snapshot/read hiện tại** chưa thấy record đó. Nó không chứng minh write đầu không thể trở thành majority committed sau T1.

Để xác nhận failure cần evidence khác, như outcome server được phân loại xác định, idempotent reservation/ledger state cùng transaction, hoặc một protocol business có điểm quyết định bất biến.

### 14.4. Ghi kết quả reconciliation có thể kiểm toán

```javascript
{
  _id: "pay-A100-20261114-01",
  state: "NEEDS_RECONCILIATION",
  source: "OrderService",
  lastObservedOrderStatus: "PAID",
  lastObservationReadConcern: "majority",
  attempts: NumberInt(2),
  lastErrorCategory: "WRITE_CONCERN_TIMEOUT",
  lastCheckedAt: new Date(),
  nextAction: "RECHECK_AFTER_REPLICATION_RECOVERY"
}
```

Đây là mẫu log/ledger **mô tả công việc**, không phải trường MongoDB có sẵn. Không lưu snapshot đầy đủ chứa PII vào ticket công khai.

## 15. Phân biệt `DuplicateKey` sau retry

### 15.1. Duplicate key có thể là dấu hiệu retry đã xảy ra

Nếu client retry insert với cùng deterministic `_id`:

```javascript
db.orders.insertOne({
  _id: "tenant-demo:A100",
  tenantId: "tenant-demo",
  externalOrderId: "A100",
  status: "CREATED"
});
```

lần thứ hai có thể trả E11000 DuplicateKey. Đây **không tự chứng minh** request đầu thành công theo đúng payload/intent, vì key có thể tồn tại từ request khác hoặc document có nội dung khác.

### 15.2. Quy trình xử lý

1. Bắt error DuplicateKey.
2. Đọc document theo unique key và tenant.
3. So `requestId` và canonical payload hash/expected result.
4. Nếu khớp: có thể coi là already processed khi durability evidence đáp ứng.
5. Nếu không khớp: trả conflict, không overwrite.
6. Nếu không thấy/còn bất định: chuyển reconciliation.

Không catch DuplicateKey rồi trả success vô điều kiện.

### 15.3. Unique index phải đúng scope

Với multi-tenant:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true }
);
```

Nếu business yêu cầu cùng `externalOrderId` được sử dụng ở tenants khác nhau thì index trên đúng tổ hợp. Với sharded collection, unique index còn cần thỏa shard-key prefix restrictions và topology. Không giả định global uniqueness nếu cluster không bảo đảm.

## 16. `insertMany` và `bulkWrite` có thể thành công một phần

### 16.1. Vì sao batch cần xử lý từng phần tử?

Giả sử client gửi 5 documents:

```text
D1 D2 D3 D4 D5
```

D1/D2 có thể được ghi; D3 bị duplicate key; D4/D5 có thể đã hoặc chưa được thử, tùy `ordered`, operation type và lỗi mạng/concern. Không được coi batch là atomic transaction.

### 16.2. `ordered:true` vs `ordered:false`

- `ordered:true`: driver/server dừng chuỗi ở write error theo semantics ordered batch.
- `ordered:false`: cố xử lý những operations khác dù một item lỗi, thứ tự xử lý có thể khác.
- Write concern timeout có thể xuất hiện **sau những writes đã áp dụng**.
- Network error có thể khiến phản hồi batch thiếu thông tin đầy đủ.

### 16.3. Lưu ID ổn định cho từng item

```javascript
const docs = [
  { _id: "batch-1:item-1", amount: 100 },
  { _id: "batch-1:item-2", amount: 200 },
  { _id: "batch-1:item-3", amount: 300 }
];
```

Khi retry/reconcile, dùng `_id`/unique item key cố định; không tạo mỗi lần retry một bộ ObjectId mới.

### 16.4. `NoWritesPerformed` và partial batch

MongoDB 6.1+ có label `NoWritesPerformed` cho một số tình huống retryable write không thực hiện write nào qua các attempts. Nếu label được server trả, đó là evidence rõ; **absence of label không đồng nghĩa partial success**, vì còn các trạng thái khác.

Với batch, kiểm:

- Các item đã insert theo stable IDs.
- Per-item errors/indices.
- Write concern error.
- Server/driver retry labels.
- `BulkWriteException` details và counters có sẵn.
- Data readback và business invariants.

Chỉ retry **những item thật sự chưa được xác nhận/đối soát**, hoặc retry toàn bộ bằng idempotency keys có thể chứng minh không tạo tác dụng phụ lặp.

### 16.5. Một phép read đủ cẩn thận

```javascript
db.batchItems.find({
  _id: {
    $in: [
      "batch-1:item-1",
      "batch-1:item-2",
      "batch-1:item-3"
    ]
  }
});
```

Xác định result nào có majority durability, payload nào khớp, item nào chưa thể kết luận. Không coi “có đủ 3 IDs ngay lúc này” là bằng chứng rằng tất cả business side effects ở hệ thống ngoài đã hoàn tất.

## 17. Transaction commit: cách xử lý khi có nhiều writes cần atomic

### 17.1. Thiết kế đơn hàng và ledger

Một transaction ngắn có thể ghi:

```text
orders
  update status CREATED -> PAID

processed_commands
  insert _id=requestId, result=PAID

outbox
  insert _id=requestId+":OrderPaid", state=NEW
```

Khi commit thành công, các thay đổi này atomic **trong MongoDB transaction**. Worker phát email/payment notification xử lý outbox **sau commit**, không thực hiện external API trong callback retryable.

### 17.2. Việc nào không được thực hiện trong callback?

Sai:

```java
session.withTransaction(() -> {
    chargeCreditCard(); // Sai: external effect có thể bị lặp.
    updateOrder(session);
    return null;
});
```

`withTransaction` có thể retry callback cho `TransientTransactionError`. MongoDB không rollback được việc charge ngoài database. Dùng outbox/saga/idempotency key của gateway.

### 17.3. Transaction callback cần có idempotency

Ngay cả với database-only transaction, callback có thể chạy lại. Dùng `requestId` ở collection ledger và logic read-existing/compare-payload:

```text
begin transaction
    |
 lookup command by requestId
    |
 +-- exists same request hash -> return stored result
 |
 +-- exists different hash -> reject conflict
 |
 +-- absent -> apply conditional business writes,
               insert command result + outbox
    |
 commit with majority
```

Nếu commit lần đầu đã thành công nhưng response mất, retry commit của transaction đó là đường ưu tiên. Nếu cuối cùng phải chạy lại một new request sau recovery, unique ledger giúp không lặp nghiệp vụ.

## 18. Java Sync Driver: cấu hình write concern và retryable writes

### 18.1. Dependency

Ví dụ Maven:

```xml
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-driver-sync</artifactId>
  <version>VERSION_DA_KIEM_TRA</version>
</dependency>
```

Các API dưới đây hướng tới Java 17 và Java Sync Driver 5.x; project cần dùng BOM/driver tương thích MongoDB Server/FCV và runtime của mình, không copy một số version tùy ý.

### 18.2. Khởi tạo client

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import java.util.concurrent.TimeUnit;

String uri = System.getenv("MONGODB_TEST_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalArgumentException("Missing test URI");
}

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .retryWrites(true)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    MongoDatabase database =
        client.getDatabase("mongo_timeout_row441_lab");

    MongoCollection<Document> orders = database
        .getCollection("orders")
        .withWriteConcern(
            WriteConcern.MAJORITY.withWTimeout(
                5, TimeUnit.SECONDS
            )
        );

    // Chỉ thao tác với namespace test thuộc quyền mình.
}
```

Lưu ý:

- `retryWrites=true` không cho phép retry mọi lệnh.
- `wtimeout` là thời gian chờ write concern, không phải toàn bộ latency budget.
- Một số driver/server mới hỗ trợ client-side `timeoutMS` với semantics khác, và một số connection-string `wtimeoutMS` được đánh dấu deprecated; kiểm đúng release trước khi cấu hình.
- URI nên lấy từ secret manager; không log connection string/password.
- Trên Atlas, kiểm default write concern do cluster quản lý.

### 18.3. Bắt riêng `MongoWriteConcernException`

```java
import com.mongodb.MongoException;
import com.mongodb.MongoWriteConcernException;
import com.mongodb.MongoWriteException;
import com.mongodb.client.result.UpdateResult;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;

try {
    UpdateResult result = orders.updateOne(
        Filters.and(
            Filters.eq("_id", "A100"),
            Filters.eq("tenantId", "tenant-demo"),
            Filters.eq("status", "CREATED")
        ),
        Updates.set("status", "PAID")
    );

    System.out.println(
        "matched=" + result.getMatchedCount()
    );

} catch (MongoWriteConcernException e) {
    // Write có thể đã được áp dụng trên primary.
    // KHÔNG kết luận FAILED và không $inc lại.
    System.err.println(
        "Write concern not acknowledged: "
        + e.getWriteConcernError().getCode()
    );
    markNeedsReconciliation("A100");

} catch (MongoWriteException e) {
    // Phân loại DuplicateKey, validation, v.v.
    handleDefiniteWriteError(e);

} catch (MongoException e) {
    // Network/selection/deadline và một số lỗi khác:
    // result có thể chưa rõ; đọc labels/code/context.
    handleMongoOutcomeUncertain(e);
}
```

`markNeedsReconciliation`, `handleDefiniteWriteError` và `handleMongoOutcomeUncertain` là **hàm ứng dụng cần tự định nghĩa**, không có sẵn trong driver. Chọn handling dựa trên **phase, labels và business invariants**, không chỉ tên exception.

### 18.4. `matchedCount:0` không nhất thiết là thất bại

Một CAS update có `matchedCount:0` có thể:

- Command đã thành công trước đó.
- Document đã được service khác cập nhật.
- State transition bị từ chối vì precondition thay đổi.

Không trả 404/500 ngay lập tức nếu chưa đọc status và request ledger.

## 19. Java transaction callback: pattern cho body chỉ ghi MongoDB

### 19.1. Một ví dụ với request ledger

Ví dụ minh họa quy trình trên một MongoDB replica set/sharded cluster test:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;

import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;

import org.bson.Document;
import java.util.Date;

static String markPaidOnce(
        MongoClient client,
        MongoDatabase db,
        String tenantId,
        String orderId,
        String requestId,
        String requestHash) {

    MongoCollection<Document> commands =
        db.getCollection("processed_commands");

    MongoCollection<Document> orders =
        db.getCollection("orders");

    MongoCollection<Document> outbox =
        db.getCollection("outbox");

    TransactionOptions options = TransactionOptions.builder()
        .readPreference(ReadPreference.primary())
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();

    try (ClientSession session = client.startSession()) {
        return session.withTransaction(() -> {
            Document previous = commands.find(
                session, Filters.eq("_id", requestId)
            ).first();

            if (previous != null) {
                if (!requestHash.equals(
                        previous.getString("requestHash"))) {
                    throw new IllegalArgumentException(
                        "Idempotency key reused with different payload"
                    );
                }
                return previous.getString("resultStatus");
            }

            var update = orders.updateOne(
                session,
                Filters.and(
                    Filters.eq("_id", orderId),
                    Filters.eq("tenantId", tenantId),
                    Filters.eq("status", "CREATED")
                ),
                Updates.set("status", "PAID")
            );

            if (update.getMatchedCount() != 1) {
                throw new IllegalStateException(
                    "Order not in CREATED state; reconcile"
                );
            }

            commands.insertOne(session,
                new Document("_id", requestId)
                    .append("tenantId", tenantId)
                    .append("orderId", orderId)
                    .append("requestHash", requestHash)
                    .append("resultStatus", "PAID")
                    .append("createdAt", new Date())
            );

            outbox.insertOne(session,
                new Document("_id", requestId + ":OrderPaid")
                    .append("tenantId", tenantId)
                    .append("orderId", orderId)
                    .append("type", "OrderPaid")
                    .append("state", "NEW")
                    .append("createdAt", new Date())
            );

            return "PAID";
        }, options);
    }
}
```

### 19.2. Điều kiện của ví dụ

- Các collections phải **được tạo trước** transaction; không dựa vào implicit creation trong môi trường/phạm vi không hỗ trợ.
- Unique `_id` của `processed_commands` và `outbox` bảo vệ key trong cùng namespace.
- Mỗi order có `_id` ổn định. Nếu multi-tenant có ID trùng, hãy thiết kế `_id`/index key đúng scope.
- Callback chỉ ghi MongoDB; không gọi email/payment/API ngoài.
- Nếu callback chạy lại sau transient error, preconditions và ledger giúp tránh áp dụng một logical command hai lần.
- Với concurrent requests cùng `requestId`, transaction có thể gặp write conflict/duplicate key. Application vẫn cần kiểm/đối soát, không coi mọi DuplicateKey là success.
- `ReadConcern.SNAPSHOT` và `WriteConcern.MAJORITY` có semantics/phạm vi theo topology; không dùng session này để giải quyết mọi consistency case ngoài transaction.
- Nếu method vẫn ném error sau retry budget, **không suy từ exception rằng commit chắc chắn abort**. Trạng thái có thể phải reconciliation theo transaction label.

### 19.3. Vì sao code không có vòng retry `commitTransaction` tay?

`ClientSession.withTransaction()` là callback API có retry logic cho `TransientTransactionError` và `UnknownTransactionCommitResult`. Viết thêm vòng retry bừa bên ngoài method với **một ClientSession mới và cùng body** có thể tạo semantics sai nếu không có ledger.

Với control thấp hơn (`startTransaction`, `commitTransaction` thủ công), application tự quản retry theo labels và **cùng session**. Hai mô hình không nên chồng chéo tùy tiện.

## 20. Java Core API: xử lý unknown commit đúng cấp

### 20.1. Pseudocode an toàn theo phase

```text
with a live ClientSession:
  startTransaction(transactionOptions)

  try:
      execute MongoDB writes in transaction
  catch e:
      if TransientTransactionError:
          abort if appropriate
          retry WHOLE transaction with bounded policy
      else:
          abort if possible
          stop/reconcile or reject depending error

  while commit budget remains:
      try:
          commitTransaction() ON SAME SESSION
          return CONFIRMED
      catch e:
          if UnknownTransactionCommitResult:
              retry COMMIT of the SAME transaction
          else:
              classify; do not blindly re-run body

  if no conclusive commit result:
      return NEEDS_RECONCILIATION
```

### 20.2. Java skeleton retry commit

```java
import com.mongodb.MongoException;
import com.mongodb.client.ClientSession;
import java.time.Duration;

static void commitWithBoundedRetry(
        ClientSession session,
        Duration budget) {

    long deadline =
        System.nanoTime() + budget.toNanos();

    while (true) {
        try {
            session.commitTransaction();
            return;
        } catch (MongoException e) {
            boolean unknown =
                e.hasErrorLabel("UnknownTransactionCommitResult");

            if (!unknown) {
                throw e;
            }

            if (System.nanoTime() >= deadline) {
                throw new IllegalStateException(
                    "COMMIT_UNKNOWN: requires reconciliation",
                    e
                );
            }

            // Retry COMMIT on same live session; không
            // startTransaction() hay chạy lại business body.
            // Thêm bounded backoff/jitter và metrics nếu cần.
        }
    }
}
```

**Đây là skeleton giải thích nguyên tắc**, không phải full production transaction coordinator: cần retry policy có backoff, interrupt/deadline, error taxonomy, session lifecycle, transition handling và observability. Nếu method ném khi hết budget, application phải giữ `requestId` để reconcile; không tái chạy toàn body chỉ vì nhận `IllegalStateException`.

### 20.3. Driver retry `commitTransaction` với majority

MongoDB docs nêu khi driver retry commit, write concern cho retry commit được nâng/áp thành `w:"majority"` theo transaction commit retry behavior. Không suy mọi retry commit có cùng effective write concern với lệnh ban đầu.

### 20.4. Commit result unknown và session đã đóng

Nếu process crash hoặc session đã kết thúc, không giả định có thể tái tạo nguyên transaction chỉ bằng gửi lại business statements. Recovery dùng ledger/unique request ID, majority reconciliation và các dữ liệu/đường kiểm toán đã được thiết kế.

## 21. Timeout configuration: không có một nút chung

### 21.1. Bảng phân biệt

| Cấu hình | Phạm vi | Dùng cho | Không bảo đảm |
| --- | --- | --- | --- |
| `serverSelectionTimeoutMS` | Driver | Tìm eligible MongoDB server | Rằng write trước chưa apply |
| `connectTimeoutMS` | Driver/socket | Thiết lập kết nối | Trạng thái của attempt đã gửi |
| `socketTimeoutMS` | Driver/socket | Chờ socket read/write (khi hỗ trợ) | Rằng server rollback khi client ngừng chờ |
| `timeoutMS` | Client-side operation timeout ở phiên bản hỗ trợ | Tổng deadline của operation | Transaction body có thể rollback hay không phải xét riêng |
| `wtimeout` | Write concern | Chờ số members ACK yêu cầu | Không undo primary writes |
| `wtimeoutMS` trong URI | Driver/config (có deprecated nuance) | Write concern timeout | Thay thế hoàn toàn `timeoutMS` |
| `maxTimeMS` | Server-side limit ở operations hỗ trợ | Chặn execution vượt hạn | Là guarantee “no mutation” cho mọi loại write |
| `maxCommitTimeMS` | Transaction options trên versions hỗ trợ | Giới hạn thời gian server cho commit | Chứng minh commit chắc chắn không xảy ra sau timeout |
| HTTP gateway timeout | App/API | Hạn phản hồi của request | Client xử lý không còn chạy |

### 21.2. Tránh “timeout chồng timeout” thiếu budget

Ví dụ:

```text
Gateway timeout:            5 s
Java client total timeout:  10 s
MongoDB wtimeout:            8 s
Transaction body:            4 s
External sink timeout:      15 s
```

Gateway có thể trả 504 sau 5 giây trong khi backend tiếp tục ghi tới 10 giây. Client retry ngay với request ID mới sẽ tạo duplicate.

Thiết kế theo end-to-end deadline:

- Dự phòng cho server selection/connection.
- Thời gian query/write/commit.
- Thời gian đối soát hoặc ghi trạng thái PENDING.
- Graceful shutdown.
- Backpressure khi số UNKNOWN tăng.
- Giữ idempotency key qua toàn bộ chu kỳ.

### 21.3. Timeout quá ngắn gây thác lũ retry

```text
replication lag rises
       |
write concern timeouts
       |
clients retry unsafe writes
       |
additional write load
       |
replication lag rises further
```

Đây là **retry storm**. Biện pháp: bounded retries + exponential backoff/jitter, rate limits, circuit breaker, idempotency và giảm tải thay vì tăng timeout không giới hạn.

## 22. Chẩn đoán replication khi `wtimeout` tăng

### 22.1. Câu hỏi đầu tiên

- Lệnh dùng effective `w` nào?
- Lỗi là write concern error thật hay network timeout?
- Có primary healthy không? Vừa election?
- Secondaries có chậm áp dụng oplog hoặc chậm journal/fsync không?
- Oplog replication, flow control, disk IOPS hoặc network đang nghẽn?
- Một member đang ở trạng thái `RECOVERING`, `STARTUP2` hoặc unreachable?
- Có quá nhiều transactions, checkpoint hoặc index builds trùng giờ?
- Trên sharded cluster, commit chờ participant nào?

### 22.2. `rs.status()` và replication info

Trên replica set có quyền:

```javascript
const st = rs.status();

printjson({
  set: st.set,
  myState: st.myState,
  members: st.members.map((m) => ({
    name: m.name,
    stateStr: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate
  }))
});
```

Có thể xem:

```javascript
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
```

Các field có thể khác theo release/permissions. Không dựa vào một giá trị lag trong một snapshot để kết luận nguyên nhân; thu thập time series cùng disk/network/CPU.

### 22.3. Cluster symptoms cần liên hệ

```text
Client wtimeout errors ↑
    |
    +-- Secondary replication lag ↑
    +-- Disk write await/IOPS ↑
    +-- Journal sync latency ↑
    +-- Primary flow control ↑
    +-- Election/stepdown events ↑
    +-- Long transactions/index builds ↑
```

Không tự giải thích “wtimeout tăng = cần tắt majority”. Nếu replica set có vấn đề replication, giảm durability chỉ che giấu symptoms và tăng rủi ro mất dữ liệu.

### 22.4. Sharded transaction khác single-shard write

Transaction qua nhiều shards cần coordination. Nếu một participant chậm hoặc mạng chập chờn, commit outcome có thể unknown lâu hơn. Cần:

- Biết transaction chạm những shards nào.
- Theo dõi mongos/config/shard health.
- Kiểm lock, distributed commit, cross-shard latency.
- Dùng business ledger để reconcile.
- Không restart mọi mongos/shard chỉ vì một transaction timeout.

## 23. Ghi log gì để điều tra?

Một log record đủ an toàn:

```json
{
  "event": "mongo_write_outcome",
  "requestId": "pay-A100-20261114-01",
  "operation": "confirmPayment",
  "namespace": "commerce.orders",
  "phase": "COMMIT",
  "outcome": "UNKNOWN",
  "writeConcern": "majority",
  "errorLabel": "UnknownTransactionCommitResult",
  "attempt": 2,
  "durationMs": 5100,
  "correlationId": "req-51db",
  "reconciliationScheduled": true
}
```

**Không log:**

- Mật khẩu/connection string chứa secrets.
- Full customer documents chứa PII.
- Raw payment/card details.
- Transaction session identifiers khi policy không cho phép.
- Stack traces nhạy cảm gửi vào HTTP response.
- Thông báo “rollback done” nếu chỉ gọi `abortTransaction()` sau commit unknown.

### 23.1. Các metric gợi ý do ứng dụng tự đặt

```text
mongo_write_attempts_total
mongo_write_success_total
mongo_write_concern_timeout_total
mongo_network_timeout_total
mongo_commit_unknown_total
mongo_transaction_transient_error_total
mongo_retryable_write_attempts_total
mongo_reconciliation_pending
mongo_reconciliation_confirmed_total
mongo_reconciliation_conflicts_total
mongo_idempotency_duplicate_requests_total
mongo_business_write_latency_seconds
mongo_transaction_commit_latency_seconds
mongo_replication_lag_seconds
mongo_app_retry_budget_exhausted_total
```

Đây là **tên mẫu**, không phải tên metric MongoDB Server tự trả. Khi phát triển dashboard, lấy tỷ lệ lỗi theo operation type/client version/cluster/tenant cohort, không gộp mọi timeout.

### 23.2. Một cảnh báo tốt có ba lớp

1. **Triệu chứng:** unknown outcomes tăng.
2. **Tài nguyên/DB:** replication lag, disk, elections.
3. **Bất biến nghiệp vụ:** số pending reconciliations, duplicate prevention, phát sinh payments/orders lệch.

Tỷ lệ timeout giảm nhưng reconciliation queue vẫn tăng là **chưa phục hồi đầy đủ**.

## 24. Runbook xử lý incident: write concern timeout

### 24.1. Giai đoạn A — Khoanh vùng và ngăn tác dụng lặp

1. Xác định collection, command type, effective write concern và thời điểm lỗi.
2. Giữ nguyên `requestId`/business ID cho những requests bị ảnh hưởng.
3. Tạm dừng mọi retry **không idempotent** (đặc biệt `$inc`, create random `_id`, external payments).
4. Ghi rõ `UNKNOWN` thay vì đánh dấu failed hoặc success.
5. Kiểm API gateway/client retry logic có tạo request ID mới không.

### 24.2. Giai đoạn B — Đánh giá sức khỏe cluster

- Replica set/shard member status.
- Last election/stepdown.
- Replication lag/oplog apply.
- Disk latency/queue, journal sync, CPU/memory.
- Background tasks: index build, backup, bulk import.
- Network/connection pool/thread contention.
- Write concern policy có đạt được với topology hiện tại không.

### 24.3. Giai đoạn C — Reconcile

- Đọc theo stable `requestId` và expected business key.
- Dùng read concern/preference đáp ứng durability contract.
- So operation ledger, order state, outbox, balances và external gateway.
- Đánh dấu `CONFIRMED` nếu có bằng chứng.
- Đánh dấu `REJECTED` khi có bằng chứng chắc chắn operation không thể/không được áp dụng.
- Giữ `NEEDS_RECONCILIATION` khi vẫn mơ hồ.
- Retry có giới hạn bằng cùng logical identity hoặc recovery protocol đã được phê duyệt.

### 24.4. Giai đoạn D — Khôi phục hiệu năng

Sau khi bảo vệ correctness:

- Throttle batch writes không cấp thiết.
- Khắc phục member/disk/network unhealthy.
- Điều chỉnh application backoff/circuit breaker.
- Kiểm connection pool và server selection config.
- Đánh giá capacity và placement.
- Xem lại SLO/timeout configuration dựa trên measurements.

Không đổi default write concern toàn cluster chỉ để ngừng alert khi chưa hiểu yêu cầu durability.

## 25. Runbook xử lý incident: unknown transaction commit

### 25.1. Không tái thực thi body ngay

Nếu commit error label `UnknownTransactionCommitResult`:

1. Nếu **ClientSession cùng transaction còn sống**: retry commit theo driver/callback API và bounded policy.
2. Nếu driver callback đang điều khiển retries: để nó hoàn tất hoặc trả lỗi theo budget; tránh chồng manual retries.
3. Nếu mất process/session hoặc hết budget: giữ `requestId`, chuyển sang reconciliation.
4. Đọc ledger + tất cả writes trong transaction theo consistency phù hợp.
5. Phân biệt commit thành công, abort xác định và trạng thái chưa đủ bằng chứng.
6. Không gọi `abortTransaction()` sau unknown commit rồi ghi “đã rollback chắc chắn”.

### 25.2. Nếu transaction chứa external side effects

Nếu callback từng gửi email hoặc charge payment, hãy kiểm external idempotency records ngay. MongoDB transaction không rollback một charge đã thành công bên ngoài. Recovery có thể cần **compensation** hoặc outbox/saga, không phải chỉ retry commit.

### 25.3. Nếu commit không thể retry do lỗi vĩnh viễn

Không lặp vô hạn khi:

- Session/transaction không còn khả dụng.
- Token/identity không thể giữ.
- Lỗi authentication/authorization.
- Driver/application đang shutdown.
- Cluster tiếp tục unhealthy.
- Retry budget/HTTP deadline đã hết.

Chuyển trạng thái sang UNKNOWN/reconciliation và tạo alert rõ thay vì silent background retries.

## 26. Lab an toàn với `mongosh`: quan sát outcome và idempotency

### 26.1. Phạm vi thực hành

- Dùng **MongoDB test replica set**; không standalone cho phần transaction/retryable writes.
- Dữ liệu giả, không có thanh toán thật.
- Không `rs.stepDown()`, không tắt secondary, không tạo network partition để “ép timeout”.
- Không đổi FCV/replica set config/oplog.
- Chỉ tạo namespace ngẫu nhiên và documents gắn `runId`.
- Không xóa toàn DB, không đụng dữ liệu người khác.
- Bài lab mô phỏng ambiguous outcome bằng **bỏ qua response ở application** sau một write bình thường; không phá cluster để ép lỗi.

### 26.2. Tạo namespace riêng

```javascript
const lab = db.getSiblingDB("mongo_timeout_row441_lab");
const runId = "row441_" + new ObjectId().toHexString();
const ordersName = "orders_" + runId;
const commandsName = "commands_" + runId;
const tenantId = "tenant_" + runId;

for (const n of [ordersName, commandsName]) {
  if (lab.getCollectionNames().includes(n)) {
    throw new Error("Namespace conflict, refuse overwrite");
  }
}

lab.createCollection(ordersName);
lab.createCollection(commandsName);

const orders = lab.getCollection(ordersName);
const commands = lab.getCollection(commandsName);

printjson({
  db: lab.getName(),
  orders: ordersName,
  commands: commandsName,
  runId,
  tenantId
});
```

### 26.3. Seed một order

```javascript
const orderId = "order_" + runId;
const requestId = "confirm_" + runId;

orders.insertOne({
  _id: orderId,
  runId,
  tenantId,
  status: "CREATED",
  version: NumberInt(1),
  amountCents: NumberLong("1500")
});

printjson(orders.findOne({ _id: orderId, runId }));
```

### 26.4. Ghi một command ID ổn định

```javascript
const commandDoc = {
  _id: requestId,
  runId,
  tenantId,
  orderId,
  requestHash: "demo-confirm-v1",
  state: "RECEIVED",
  createdAt: new Date()
};

commands.updateOne(
  { _id: requestId, runId },
  { $setOnInsert: commandDoc },
  { upsert: true }
);
```

Đây là reservation đơn giản cho lab. **Không coi riêng bước này là atomic với business update**. Trong production, dùng transaction ngắn hoặc protocol ledger có states/recovery chặt chẽ.

### 26.5. Chạy CAS update

```javascript
const first = orders.updateOne(
  {
    _id: orderId,
    runId,
    tenantId,
    status: "CREATED",
    version: NumberInt(1)
  },
  {
    $set: {
      status: "PAID",
      lastRequestId: requestId
    },
    $inc: {
      version: 1
    }
  }
);

printjson({
  matched: first.matchedCount,
  modified: first.modifiedCount
});
```

### 26.6. Mô phỏng “client không nhận kết quả”

Thay vì cố gây network timeout, hãy giả định application không nhận được object `first`. Trên một terminal/consumer logic khác, gửi lại cùng **CAS command**:

```javascript
const again = orders.updateOne(
  {
    _id: orderId,
    runId,
    tenantId,
    status: "CREATED",
    version: NumberInt(1)
  },
  {
    $set: {
      status: "PAID",
      lastRequestId: requestId
    },
    $inc: {
      version: 1
    }
  }
);

printjson({
  retryMatched: again.matchedCount,
  retryModified: again.modifiedCount,
  current: orders.findOne({ _id: orderId, runId })
});
```

Kỳ vọng sau lần đầu thành công: lần hai có `matchedCount:0`; version chỉ tăng từ 1 lên 2, không lên 3. **Nhưng riêng `matchedCount:0` chưa chứng minh nguyên nhân**; document có `lastRequestId` giúp xác nhận request này đã cập nhật order trong lab.

### 26.7. Đối soát trước khi đánh dấu confirmed

```javascript
const observed = orders.findOne({
  _id: orderId,
  runId,
  tenantId
});

if (!observed ||
    observed.status !== "PAID" ||
    observed.lastRequestId !== requestId) {
  throw new Error("Cannot confirm logical request");
}

commands.updateOne(
  {
    _id: requestId,
    runId,
    tenantId,
    state: "RECEIVED"
  },
  {
    $set: {
      state: "CONFIRMED",
      confirmedAt: new Date()
    }
  }
);

printjson({
  observed,
  command: commands.findOne({ _id: requestId, runId })
});
```

Đây là **minh họa giao thức idempotency có bước đối soát**, không phải proof end-to-end atomicity. Do ledger và order là hai writes khác nhau, một production implementation phải xử lý crash giữa chúng; có thể dùng transaction để ghi chung.

### 26.8. Thử write concern ở mức an toàn

```javascript
const ack = lab.runCommand({
  update: ordersName,
  updates: [
    {
      q: { _id: orderId, runId, tenantId },
      u: { $set: { labMarker: "majority-ack" } },
      multi: false
    }
  ],
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 5000
  }
});

printjson({
  ok: ack.ok,
  n: ack.n,
  writeConcernError: ack.writeConcernError
});
```

Trên một replica set test healthy, lệnh thường thành công. Nếu nhận write concern error, **không** chạy lại bằng một `$inc` mù; đọc lại và đối soát.

Không đặt `w:100` hoặc cố làm majority unavailable để kích hoạt timeout. Lab nhằm hiểu cách xử lý, không stress/disable replica members.

### 26.9. Một transaction ngắn trong lab

Nếu deployment test hỗ trợ transactions và đã tạo collections:

```javascript
const session = db.getMongo().startSession();
const sdb = session.getDatabase(lab.getName());
const sorders = sdb.getCollection(ordersName);
const scommands = sdb.getCollection(commandsName);

const txnOrderId = "txn_order_" + runId;
const txnRequestId = "txn_confirm_" + runId;

// Seed ngoài transaction, trước khi start:
orders.insertOne({
  _id: txnOrderId,
  runId,
  tenantId,
  status: "CREATED",
  version: NumberInt(1)
});

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  const result = sorders.updateOne(
    {
      _id: txnOrderId,
      runId,
      tenantId,
      status: "CREATED"
    },
    {
      $set: {
        status: "PAID",
        lastRequestId: txnRequestId
      }
    }
  );

  if (result.matchedCount !== 1) {
    throw new Error("Unexpected transaction precondition");
  }

  scommands.insertOne({
    _id: txnRequestId,
    runId,
    tenantId,
    orderId: txnOrderId,
    state: "CONFIRMED",
    requestHash: "demo-txn-v1"
  });

  session.commitTransaction();
} catch (e) {
  print("Transaction error: " + e.message);

  // Phần lab không cố kích hoạt UnknownTransactionCommitResult.
  // Trên ứng dụng thật, label ấy yêu cầu retry commit
  // của cùng session/transaction trước khi kết luận.
  // Không giả định abortTransaction chắc chắn hủy commit
  // khi kết quả commit đã UNKNOWN.
  throw e;
} finally {
  session.endSession();
}
```

Ví dụ ngắn trên **không có retry loop đầy đủ**; dùng để thấy transaction có thể ghi order + ledger cùng một commit. Nếu server báo lỗi hoặc session commit unknown, coi outcome chưa xác định và áp quy trình ở phần Java/Runbook; không tự replay transaction bằng đoạn script này.

### 26.10. Đọc lại sau commit

```javascript
printjson({
  order: orders.findOne({
    _id: txnOrderId,
    runId
  }),
  command: commands.findOne({
    _id: txnRequestId,
    runId
  })
});
```

Nếu có thể, đọc theo consistency contract tương ứng; trong lab khỏe mạnh sẽ thấy trạng thái PAID và ledger CONFIRMED. **Không** chứng minh transaction đã commit chỉ vì log local nói đã gửi `commitTransaction`.

### 26.11. Cleanup theo `_id + runId`

Trước khi xóa:

```javascript
printjson({
  db: lab.getName(),
  orders: orders.getName(),
  commands: commands.getName(),
  runId
});

const ownOrders = orders.find(
  { runId, tenantId },
  { _id: 1, runId: 1 }
).toArray();

const ownCommands = commands.find(
  { runId, tenantId },
  { _id: 1, runId: 1 }
).toArray();

printjson({
  orderCount: ownOrders.length,
  commandCount: ownCommands.length
});
```

Chỉ sau khi xác minh đúng lượt thử và không có application khác dùng:

```javascript
for (const item of ownOrders) {
  orders.deleteOne({
    _id: item._id,
    runId,
    tenantId
  });
}

for (const item of ownCommands) {
  commands.deleteOne({
    _id: item._id,
    runId,
    tenantId
  });
}

printjson({
  remainingOrders: orders.countDocuments({ runId, tenantId }),
  remainingCommands: commands.countDocuments({ runId, tenantId })
});
```

Không `dropDatabase()` hay `deleteMany({})` trên database chia sẻ. Collection lab có thể được dọn theo owner/retention sau khi xác minh, không tùy tiện drop trong script.

## 27. Thí nghiệm định hướng: tình huống timeout không cần phá cluster

Có thể diễn tập hành vi ứng dụng bằng **fault injection vào response path trong test harness** thay vì giết primary/secondary:

- Cho server ghi thành công, nhưng test stub/adapter trả `UNKNOWN` cho caller.
- Kiểm caller **không** gửi thêm `$inc`/insert random ID.
- Kiểm caller giữ cùng `requestId`.
- Kiểm status endpoint lấy trạng thái từ ledger.
- Kiểm nếu transaction commit result unknown thì code retry **commit** chứ không gọi callback khác bên ngoài cơ chế driver.
- Kiểm workflow cạn retry budget đưa vào reconciliation queue.
- Kiểm reconciliation không đánh dấu REJECTED chỉ vì một lần majority read chưa thấy record.
- Kiểm business sink không tạo email/payment duplicate.
- Kiểm khi failover của test replica set theo runbook do infrastructure team cho phép, không làm trong production.

Một test mock exception chưa chứng minh server thật sử dụng cùng error labels. Kết hợp integration test MongoDB và failure-path tests; STEP 4 chỉ trình bày phương pháp, không thực thi QA.

## 28. Đối soát external payment và outbox

### 28.1. MongoDB transaction không bao trùm payment gateway

```text
MongoDB transaction commits
            |
         response lost
            |
Application unsure
            |
External payment API may also have succeeded
```

Nếu payment gateway dùng idempotency key, giữ **cùng key** qua mọi retries và truy vấn trạng thái giao dịch tại gateway. Không gửi charge mới với key mới rồi hy vọng MongoDB rollback được khoản cũ.

### 28.2. Transactional outbox

Trong MongoDB transaction, cập nhật order và thêm outbox event:

```javascript
{
  _id: "pay-A100-20261114-01:OrderPaid",
  eventType: "OrderPaid",
  orderId: "A100",
  requestId: "pay-A100-20261114-01",
  publishState: "NEW"
}
```

Worker publish **sau** commit, có idempotency ở sink và checkpoint state. Nếu publish response mất, worker có thể retry bằng same event key. Đây là at-least-once delivery với idempotent processing, không tự động exactly once ở mọi downstream system.

### 28.3. Trường hợp nhiều nguồn sự thật

Nếu gateway báo charge succeeded nhưng MongoDB ledger chưa confirmed, cần reconciliation policy:

1. Xác minh gateway transaction ID.
2. Xác minh MongoDB order/request ledger và payment references.
3. Tránh charge lại.
4. Quyết định repair MongoDB state, tạo compensation hay manual review.
5. Ghi audit.

Không quyết định hoàn tiền hoặc charge lại chỉ dựa trên một MongoDB socket timeout.

## 29. Error taxonomy và quyết định tự động

| Sự kiện | Có thể biết chắc điều gì? | Hành động |
| --- | --- | --- |
| `insertOne` acknowledged majority | Write đạt write concern contract | Ghi confirmed, tiếp tục |
| `MongoWriteConcernException` | Write concern chưa đạt; primary modification có thể tồn tại | Reconcile, không blind retry |
| Network timeout sau gửi | Outcome không rõ | Retry eligible driver protocol/idempotency key hoặc reconcile |
| `NoWritesPerformed` được server cung cấp cho eligible retryable write | Không có write thực hiện theo label semantics | Có thể phân loại no-write, vẫn xét business flow |
| DuplicateKey trên retry | Key đã tồn tại | Đọc/so request identity/hash |
| Validation failure | Document không được chấp nhận bởi validator trong operation đó | Sửa payload/type, không retry mãi |
| `TransientTransactionError` trong transaction body | Whole transaction có thể retry | Bounded callback/core transaction retry |
| `UnknownTransactionCommitResult` | Không biết commit đã xảy ra chưa | Retry commit same session; sau đó reconciliation |
| `TransactionTooLargeForCache` | Transaction quá lớn cho cache theo version | Redesign batch/transaction, không blind retry |
| Client-side timeout của `withTransaction` | Callback có thể dừng khi deadline; commit phase cần xem labels | Reconcile, không đánh đồng với abort |
| `matchedCount:0` sau CAS | Preconditions không match tại thời điểm update | Đọc order+ledger; phân biệt already applied/conflict |
| Batch error | Có thể partial success | Per-item reconciliation |
| HTTP 504 | Gateway chờ quá lâu | Giữ requestId, status endpoint/async resolution |

Đây là hướng dẫn phân loại; driver/server/version có thể thêm codes và labels. **Dùng evidence thực tế, không dựng câu chuyện chắc chắn từ một exception chung**.

## 30. Chẩn đoán sai lầm phổ biến

| Nhầm lẫn | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “Timeout nghĩa là chưa có write” | Duplicate update/insert | UNKNOWN trừ khi có evidence |
| “wtimeout rollback dữ liệu” | Client retry sai | Primary modifications không tự undo |
| “wtimeout giới hạn toàn bộ update” | SLO sai | Chỉ write concern phase theo `w` |
| “w:1 là majority durable” | Có thể rollback khi failover | Chọn write concern phù hợp |
| “j:true giống w:majority” | Nhầm journal/replication | Hai chiều durability khác nhau |
| “MongoDB luôn dùng cùng default w” | Sai contract khi đổi topology | Đọc effective default |
| “Một secondary read không thấy = write thất bại” | Bỏ/nhân đôi tác vụ | Replication lag/read concern |
| “Majority ack 8.0 nghĩa secondary đã apply ngay” | Read không thấy state | Causal consistency khi cần |
| “Catch mọi MongoException và retry $inc” | Tăng số dư hai lần | Phân loại lỗi, idempotency |
| “retryWrites=true giải quyết cả HTTP retries” | Requests mới vẫn duplicate | Stable requestId |
| “retryWrites hoạt động trên w:0” | Không có ACK/statement retry | Dùng acknowledged writes |
| “updateMany tự retryable như updateOne” | Có thể lặp multi writes | Kiểm operation eligibility |
| “Mọi retryable write chỉ thử 1 lần ở mọi driver” | Sai khi timeoutMS/versions khác | Đọc đúng docs |
| “NoWritesPerformed không có tức đã viết” | Kết luận sai | Absence không chứng minh |
| “Transaction body lỗi tạm thì commit lại ngay” | Transaction có thể đã abort | Tách transient body/unknown commit |
| “UnknownTransactionCommitResult = aborted” | Làm lại transaction mới | Retry commit same session |
| “Retry commit = chạy callback lại” | Duplicate external effects | Không |
| “withTransaction callback chỉ chạy một lần” | Gửi email/charge trùng | Callback có thể retry |
| “MongoDB transaction rollback payment gateway” | Sai distributed atomicity | Outbox/saga/idempotency |
| “Abort sau unknown commit đảm bảo không commit” | Sai kết luận | Phải reconcile |
| “DuplicateKey sau retry nghĩa success chắc chắn” | Trả nhầm kết quả request khác | So requestHash |
| “CAS matchedCount=0 nghĩa đã thanh toán” | Bỏ sót conflict khác | Đọc ledger |
| “Mỗi retry sinh ObjectId mới” | Trùng business records | Deterministic key |
| “Batch lỗi thì cả batch rollback” | Bỏ sót partial writes | Per-item reconciliation |
| “Driver auto retry là đủ cho exactly once” | Side effects vẫn lặp | End-to-end idempotency |
| “Tăng timeout là sửa root cause” | Che replication pressure | Đo cluster/IOPS/lag |
| “Giảm majority để hết alert” | Mất durability | Sửa nguyên nhân và đánh giá policy |
| “Không cần lưu UNKNOWN state” | Tác vụ bị quên | Durable reconciliation queue |
| “Test timeout bằng tắt secondary production” | Gây sự cố thật | Lab/fault injection có kiểm soát |
| “Log full payload để debug” | Lộ PII/secrets | Redacted structured logging |

## 31. Bài tập vận dụng

### Bài A — Write concern timeout

Tình huống:

```text
Primary applied update at T1.
Secondaries were unreachable.
At T3, wtimeout=2000 ms returned a writeConcernError.
At T4, secondaries came back.
```

1. Có thể nói update đã rollback tại T3 không?
2. Vì sao không được retry `$inc` như một operation mới?
3. Đọc theo majority ở T3/T4 cho biết gì, và không cho biết gì?
4. Nếu primary failover giữa T3/T4, cần kiểm gì?

### Bài B — Network ACK loss

```text
T0 insertOne(_id="A100")
T1 server applies insert
T2 success response lost
T3 client sees socket timeout
```

Thiết kế xử lý bằng deterministic ID, requestHash và readback. Nếu lần retry báo DuplicateKey thì điều kiện nào cần xác minh trước khi coi đó là success?

### Bài C — Commit unknown

Transaction cập nhật `orders`, `ledger`, `outbox`. `commitTransaction` trả label `UnknownTransactionCommitResult`.

1. Retry operation nào?
2. Có chạy lại `session.withTransaction` body như một transaction mới ngay không?
3. Nếu session không còn, reconcile các collections thế nào?
4. Nếu outbox worker đã gửi message, cần bảo vệ trùng ở đâu?

### Bài D — Transient transaction error

Một update trong transaction bị `TransientTransactionError` trước commit.

1. Điều gì khác với unknown commit?
2. Callback có thể được chạy lại thế nào?
3. Vì sao không gọi charge API trong callback?
4. Cần retry budget và idempotency nào?

### Bài E — `$inc` và CAS

Một counter `balance=1000` cần tăng 500 do command `C-17`. Client timeout sau update.

1. Vì sao retry `$inc:500` không an toàn?
2. Viết CAS filter theo version và command ID.
3. Nếu CAS retry matched=0, các nguyên nhân nào có thể?
4. Khi nào cần transaction với command ledger?

### Bài F — API status endpoint

Thiết kế:

```text
POST /orders/A100/pay
Idempotency-Key: C-17
GET /operations/C-17
```

Nêu responses cho `CONFIRMED`, `REJECTED`, `NEEDS_RECONCILIATION`, duplicate same payload và duplicate different payload.

### Bài G — Batch partial success

Một batch có 6 inserts, nhận network error giữa chừng.

1. Có thể retry toàn bộ batch với random ObjectIds không?
2. Phải lưu khóa gì trước khi gửi?
3. Nếu một lần retry báo duplicate key cho một item, kiểm gì?
4. `NoWritesPerformed` hữu ích trong trường hợp nào?

### Bài H — Replica set health

```text
Primary CPU: 45%
Secondary disk w_await: 50 ms
Replication lag: 90 s
wtimeout errors: tăng mạnh
```

Dự đoán nguyên nhân, metric cần kiểm, vì sao chỉ tăng primary CPU không giải quyết và biện pháp giảm tải an toàn.

### Bài I — Majority read không thấy dữ liệu

Sau wtimeout, majority read chưa thấy `requestId`.

1. Có chứng minh request chắc chắn chưa ghi không?
2. Nếu sau đó write mới majority commit thì sao?
3. Có thể dùng protocol nào để tránh submit duplicate?
4. Khi nào cần manual reconciliation?

### Bài J — Timeouts theo lớp

Một request có:

```text
HTTP gateway: 3 s
Java operation timeout: 8 s
MongoDB wtimeout: 5 s
```

1. Vì sao gateway có thể trả 504 trong khi backend vẫn ghi?
2. HTTP retry nên giữ identity gì?
3. Những thay đổi nào bảo vệ correctness?
4. Vì sao tăng gateway timeout không tự giải quyết replication lag?

### Bài K — Java Driver labels

Một exception có:

```text
UnknownTransactionCommitResult
```

Một exception khác có:

```text
TransientTransactionError
```

Viết pseudocode xử lý riêng hai trường hợp, chỉ rõ với Core API và Callback API.

### Bài L — Ledger atomicity

Một service làm:

```text
insert ledger CONFIRMED
update order PAID
```

Nếu crash giữa hai writes, tình trạng gì xảy ra? Thiết kế transaction hoặc state-machine/reconciliation an toàn hơn.

### Bài M — Sharded transaction

Một transaction chạm nhiều shards và commit timeout. Nêu các thành phần phải kiểm, vì sao mongos/coordinator có thể ảnh hưởng latency và cách đọc business state sau unknown commit.

### Bài N — Rollback/failover

Một write `w:1` đã được client ACK trên primary, sau đó primary failover và write không còn ở new primary.

1. Đây có mâu thuẫn với `w:1` không?
2. Làm sao chọn write concern cho nghiệp vụ thanh toán?
3. Idempotency vẫn cần thiết dù dùng majority vì sao?
4. Backup có giúp giải quyết duplicate retries không?

### Bài O — Lab không cần làm hỏng cluster

Thiết kế integration test tạo một write thành công nhưng **fake timeout ở application boundary**. Chứng minh:

- API không trả success giả.
- Retry dùng lại `requestId`.
- CAS/update không tăng version hai lần.
- Reconciliation đọc đúng result.
- Không có external notification lặp.

### Bài P — Postmortem

Một hệ thống có 200 timeout trong 10 phút và 17 đơn hàng bị tính tiền hai lần. Lập postmortem với timeline, write concern, retry path, lỗi idempotency, data repair, monitoring, owner và các bước ngăn tái diễn.

## 32. Kịch bản production rollout khi sửa sự cố

### 32.1. Trước thay đổi

Ghi baseline:

- Số unknown outcomes theo từng operation.
- Rate `wtimeout`, network timeout, transaction commit unknown.
- Effective write concern/driver settings.
- Replication lag, elections, disk latency, journal sync.
- Idempotency key coverage.
- Count duplicate business keys.
- Số operations đang chờ reconciliation.
- Error budget và business impact.

### 32.2. Trong rollout

Thứ tự thường an toàn:

1. Instrument lỗi theo phase/labels.
2. Khóa đường retry unsafe bằng feature flag.
3. Deploy stable request IDs/ledger.
4. Bật idempotent conditional writes/transaction outbox.
5. Bổ sung bounded retries theo đúng level.
6. Kích hoạt reconciliation worker có ownership và rate limit.
7. Tối ưu cluster health/capacity.
8. Quan sát một chu kỳ nghiệp vụ trước khi dừng logic legacy.

Đừng đồng thời đổi majority write concern, connection pool, retry policy và transaction body mà không có cách đối chiếu nguyên nhân.

### 32.3. Khi rollback code

Một app version cũ có thể **không biết** request ledger/idempotency contract mới. Rollback code không được loại bỏ protection của business key. Nếu app cũ không tương thích, cần forward fix hoặc giữ compatibility layer.

Nếu có các commands UNKNOWN trong lúc deploy, chúng phải được xử lý tiếp bởi cùng reconciliation protocol; không xóa pending queue vì “release đã rollback”.

## 33. Tài liệu chính thức và điểm cần xác minh theo phiên bản

Nguồn đối chiếu quan trọng:

- [Write Concern — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/write-concern/) — `w`, `j`, `wtimeout`, write concern error và rollback semantics.
- [Retryable Writes — MongoDB Manual](https://www.mongodb.com/docs/manual/core/retryable-writes/) — eligibility, retryable write identity, `NoWritesPerformed` và timeout model.
- [Transactions — MongoDB Manual](https://www.mongodb.com/docs/manual/core/transactions/) — transaction-level concerns, commit behavior và sharded coordination.
- [Handling Transactions in Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — `TransientTransactionError` và `UnknownTransactionCommitResult`.
- [Java Sync Driver Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession`, `withTransaction()`, callback/core API.
- [Java Sync Driver Connection and Network Options](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/) — driver connection/timeout/retry configuration.
- [Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — timeout/retry/write concern options, `wtimeoutMS` deprecation nuance.
- [Java Driver MongoException](https://mongodb.github.io/mongo-java-driver/) — error labels, exception subclasses và API Javadocs theo đúng version.
- [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — history, replication, rollback risks.
- [Replica Set Rollbacks](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/) — trường hợp writes không đạt majority có thể bị rollback.
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — local/majority/snapshot read semantics.
- [Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/) — read-your-writes với sessions.
- [Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/) — ordered/unordered và partial success.
- [Server Status](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — replication/transactions metrics.
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/) — theo dõi cluster managed deployments.

**Ghi chú phiên bản:** các behavior liên quan retryable writes thay đổi theo driver và `timeoutMS`; label `NoWritesPerformed` xuất hiện từ MongoDB 6.1; `TransactionTooLargeForCache` từ 6.2; đa số xác nhận majority và secondary apply có thay đổi ở MongoDB 8.0. Kiểm đúng server version, FCV, driver, connection-string settings và topology trước khi thay đổi production.

## 34. Kết luận

Timeout MongoDB không phải một boolean “đã thành công” hay “đã thất bại”. Đó là dấu hiệu cần **phân loại phase và chứng cứ**:

1. **`wtimeout` không tự rollback** những writes đã áp dụng trên primary. Một write có thể đạt majority sau khi client nhận write concern error, hoặc bị rollback sau failover nếu chưa majority.
2. **Network/socket/client timeout** có thể mất response dù server đã hoàn thành, nên không được mù quáng gửi lại operation không idempotent.
3. **`retryWrites=true`** bảo vệ những logical writes đủ điều kiện ở driver level, nhưng không biết hai HTTP requests mới là cùng một nghiệp vụ.
4. **`UnknownTransactionCommitResult`** phải được xử lý bằng retry **commit của cùng transaction** khi còn có thể; **`TransientTransactionError`** có thể cần retry **toàn transaction** theo driver/specification.
5. **Idempotency key, unique constraints, CAS, ledger và transactional outbox** tạo lớp bảo vệ cho crash windows và hệ thống ngoài MongoDB.
6. **Readback phải xét durability**. Document đã thấy không tự chứng minh majority ACK; document chưa thấy cũng không chứng minh operation không thể hoàn tất sau đó.
7. **Bulk operations có thể thành công một phần**; cần reconcile từng item theo stable identity thay vì kết luận toàn bộ batch rollback.
8. **Runbook vận hành** phải bảo vệ dữ liệu trước, rồi mới giải quyết replication lag, disk, network, capacity và tuning timeout.
9. Khi không có đủ bằng chứng, trạng thái đúng là **UNKNOWN/NEEDS_RECONCILIATION**, kèm owner, retry budget, lịch kiểm tra và audit trail, không phải một success/failure bịa ra.

**Nguyên tắc cốt lõi:** khi MongoDB báo timeout xác nhận ghi hoặc commit chưa rõ kết quả, hãy **giữ nguyên danh tính nghiệp vụ, không tạo tác dụng phụ trùng, thu thập bằng chứng bền vững và chỉ xác nhận khi đã đối soát được trạng thái**. Đây là nền tảng để hệ thống tiếp tục đúng đắn qua network partitions, failover, retries, deploy và phục hồi sau sự cố.

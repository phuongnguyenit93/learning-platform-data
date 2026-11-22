# TransientTransactionError, UnknownTransactionCommitResult và xử lý lỗi trong MongoDB Transactions

## 1. Vì sao transaction phải có chiến lược xử lý lỗi?

MongoDB hỗ trợ **multi-document transactions** để nhóm nhiều thao tác đọc/ghi vào một đơn vị giao dịch. Khi transaction commit thành công, những thay đổi của giao dịch trở nên có hiệu lực như một nhóm; khi giao dịch abort, những thay đổi chưa commit của giao dịch bị loại bỏ.

Tuy nhiên, một transaction chạy trên replica set hoặc sharded cluster không chỉ có hai trạng thái đơn giản **thành công** và **thất bại chắc chắn**. Trong quá trình thực thi có thể xảy ra:

- Một document bị transaction khác cập nhật, gây **write conflict**.
- Primary bị **step down** hoặc có bầu cử primary mới.
- Network giữa ứng dụng và MongoDB gián đoạn.
- Một thao tác quá thời gian chờ hoặc không lấy được lock.
- **commitTransaction** được gửi đi nhưng kết nối hỏng trước khi response quay về.
- Transaction vượt giới hạn lifetime, cache hoặc tài nguyên của server.

Điểm khó nhất không phải chỉ là nhận ra exception, mà là **biết bước nào được phép chạy lại**.

MongoDB sử dụng **error labels** để giúp ứng dụng quyết định:

| Error label | Diễn giải cốt lõi | Hướng xử lý |
|---|---|---|
| **TransientTransactionError** | Transaction gặp lỗi tạm thời, cần bắt đầu một nỗ lực giao dịch mới. | **Retry toàn bộ transaction body** từ đầu bằng transaction mới. |
| **UnknownTransactionCommitResult** | Kết quả của **commit** chưa xác định đối với client. | **Retry chính commitTransaction**, không chạy lại body ngay. |
| Không có hai label trên | Có thể là validation, duplicate key, authorization, lỗi tài nguyên hoặc lỗi không retryable. | Phân loại lỗi, báo thất bại hoặc phục hồi theo quy tắc cụ thể; **không blind retry**. |

Hai labels này **không phải tên exception class riêng**. Một **MongoException** có thể mang một hoặc nhiều nhãn được thêm bởi server/driver, tùy tình huống.

**Quy tắc nhớ nhanh:**

~~~text
Lỗi khi đang thực hiện transaction
    |
    +-- TransientTransactionError
    |      -> ABORT/để transaction cũ kết thúc
    |      -> START transaction mới
    |      -> chạy lại TOÀN BỘ body
    |
    +-- Lỗi vĩnh viễn / không retryable
           -> dừng, báo lỗi thích hợp

Lỗi khi COMMIT
    |
    +-- UnknownTransactionCommitResult
    |      -> giữ ngữ cảnh transaction/session
    |      -> thử COMMIT lại
    |      -> KHÔNG chạy lại body ngay
    |
    +-- Kết quả khác
           -> phân loại theo thông tin thực tế
~~~

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt lỗi **trước commit** và kết quả **commit không xác định**.
2. Hiểu hai error labels và điểm khác biệt giữa **retry transaction** với **retry commit**.
3. Xây retry policy có giới hạn thời gian, backoff, logging và business idempotency.
4. Sử dụng **Java Sync Driver withTransaction** hoặc Core API phù hợp.
5. Thiết kế xử lý lỗi với **Spring Data MongoDB / MongoTransactionManager**.
6. Phân biệt **unknown outcome**, lỗi dữ liệu và lỗi hệ thống.
7. Kiểm thử failover, transaction conflicts, timeouts và các tác dụng phụ ngoài MongoDB.

## 2. Chu kỳ sống của một MongoDB transaction

Một transaction dùng **ClientSession** và có các giai đoạn:

~~~text
MongoClient
    |
    v
startSession()
    |
    v
startTransaction(options)
    |
    +--> Read / Write A
    |
    +--> Read / Write B
    |
    +--> Read / Write C
    |
    v
commitTransaction()
    |
    +--> Commit được xác nhận -> SUCCESS
    |
    +--> Kết quả commit không rõ -> UNKNOWN
    |
    +--> Transaction không thể tiếp tục -> ERROR/ABORT
~~~

Nếu một operation trong transaction gặp lỗi khiến giao dịch không thể tiếp tục, ứng dụng cần kết thúc giao dịch cũ và **khởi động một transaction mới** khi lỗi có thể retry.

Nếu đã bước sang **commit** và nhận được **UnknownTransactionCommitResult**, client không thể suy từ exception rằng giao dịch chưa commit. Bởi vậy **không được tự tạo transaction mới rồi chạy lại body** chỉ vì chưa thấy response thành công.

### 2.1. Vì sao retry một lệnh bên trong transaction không đủ?

Ví dụ chuyển số dư:

~~~text
Transaction T1:
  1. Trừ account A 200
  2. Cộng account B 200
  3. Ghi transfer record
  4. Commit
~~~

Nếu bước 2 gặp **TransientTransactionError**, cách phục hồi đúng là thử lại **toàn bộ transaction** theo snapshot mới. Chạy riêng bước 2 trong transaction cũ không bảo đảm giao dịch còn hợp lệ; còn chạy riêng bước 2 ở ngoài transaction sẽ phá vỡ nguyên tử.

### 2.2. Vì sao retry commit an toàn hơn retry body khi commit không rõ?

Giả sử toàn bộ body đã chạy xong và server có thể đã commit:

~~~text
Client                        MongoDB
  |                              |
  |---- commitTransaction ------>|
  |                              | COMMIT thành công?
  |             X mất kết nối    |
  |<------ không nhận reply -----|
  |
  | Không thể biết chắc outcome
~~~

Nếu client chạy lại body như một giao dịch mới, một nghiệp vụ có thể bị thực hiện lần thứ hai. Gửi lại **commit cho cùng transaction/session** mới là hướng xử lý **UnknownTransactionCommitResult**.

## 3. Chuẩn bị dữ liệu thực hành

Dùng database riêng trong **mongosh**, không chạy lab trên dữ liệu production:

~~~javascript
use mongo_transaction_error_lab

db.accounts.insertMany([
  {
    _id: "ACC-A",
    ownerId: "USER-A",
    balanceCents: NumberLong(100000),
    version: NumberLong(1)
  },
  {
    _id: "ACC-B",
    ownerId: "USER-B",
    balanceCents: NumberLong(50000),
    version: NumberLong(1)
  }
]);

db.transfers.createIndex(
  { requestId: 1 },
  {
    unique: true,
    name: "uq_transfer_request_id"
  }
);
~~~

Lệnh **insertMany** chỉ chạy một lần trên collection mới; nếu chạy lại với cùng _id sẽ gặp duplicate key. Các ví dụ xử lý lỗi độc lập thường giả định trạng thái đầu:

| Account | balanceCents |
|---|---:|
| ACC-A | 100000 |
| ACC-B | 50000 |

Nghiệp vụ cần chuyển **20000 cents** từ ACC-A sang ACC-B, đồng thời ghi một document transfer:

~~~javascript
{
  _id: "TX-001",
  requestId: "REQ-001",
  fromAccount: "ACC-A",
  toAccount: "ACC-B",
  amountCents: NumberLong(20000),
  status: "COMPLETED"
}
~~~

Sau một transfer được commit đúng một lần, số dư kỳ vọng:

~~~text
ACC-A = 80000
ACC-B = 70000
Tổng    = 150000
~~~

**Tổng số dư** là invariant của ví dụ, nhưng hệ thống tiền thật còn phải tính phí, ledger accounting, số tiền dự trữ, authorization, quy tắc chuyển tiền và integration bên ngoài. Bài này chỉ tập trung **transaction error handling**.

### 3.1. Cấu hình session và transaction

~~~javascript
const session = db.getMongo().startSession();

session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" },
  readPreference: { mode: "primary" }
});
~~~

Một transaction thường dùng:

- **readConcern snapshot** khi cần góc nhìn nhất quán trong nhiều document.
- **writeConcern majority** khi commit cần durability theo đa số.
- **readPreference primary** vì transactional writes đi qua primary.

Những tùy chọn này không tự bật retry policy trong **Core API**. Ứng dụng phải chọn **callback/convenient API** hoặc viết xử lý lỗi rõ ràng.

## 4. Error labels: không phân loại chỉ bằng text thông báo

MongoDB có nhiều loại lỗi khác nhau: lỗi server, lỗi network, conflict, không đủ tài nguyên, thời gian chờ, dữ liệu vi phạm constraints, v.v. Các exception có thể có **error code**, **message**, và **errorLabels**.

Ví dụ hình dung:

~~~javascript
{
  code: 112,
  codeName: "WriteConflict",
  errmsg: "WriteConflict ...",
  errorLabels: [
    "TransientTransactionError"
  ]
}
~~~

Đây là ví dụ minh họa; **không nên giả định mọi lỗi code 112, mọi driver hoặc mọi thời điểm đều có đúng cấu trúc trên**.

### 4.1. Tại sao nên kiểm tra label?

Một mã lỗi như **NetworkTimeout** có thể xuất hiện ở nhiều vị trí:

- Trước khi transaction body được thực hiện.
- Trong một operation của transaction.
- Khi đang commit transaction.
- Sau khi server đã áp dụng commit nhưng trước khi client đọc được response.

**Vị trí lỗi quyết định cách xử lý.** Chỉ bắt exception có tên network rồi retry toàn bộ transaction có thể gây rủi ro double execution.

### 4.2. Error labels trong Java

MongoDB Java Driver cung cấp:

~~~java
if (exception.hasErrorLabel("TransientTransactionError")) {
    // Retry toàn bộ transaction nếu đang ở pha body.
}

if (exception.hasErrorLabel("UnknownTransactionCommitResult")) {
    // Retry commit của cùng transaction.
}
~~~

Đây là API của **MongoException**, không phải method của mọi Java exception. Nếu framework bọc exception thành dạng khác, cần truy nguyên cause/driver exception an toàn.

### 4.3. Error labels trong mongosh

Tùy dạng đối tượng lỗi, có thể quan sát:

~~~javascript
try {
  // Thao tác MongoDB ...
} catch (error) {
  printjson({
    name: error.name,
    message: error.message,
    code: error.code,
    labels: error.errorLabels
  });
}
~~~

Khi viết ứng dụng, ưu tiên method kiểm tra label được driver cung cấp; không parse chuỗi message bằng regex để quyết định retry.

### 4.4. Một lỗi có thể không mang label retryable

Ví dụ lỗi schema validation, duplicate key hoặc unauthorized cần được phân loại đúng. Không nên viết:

~~~text
catch ANY_EXCEPTION:
    retryTransactionForever()
~~~

Retry sai loại lỗi gây tải lớn, ẩn lỗi nghiệp vụ và có thể khiến một thao tác nguy hiểm lặp lại.

## 5. TransientTransactionError: thử lại toàn bộ transaction

### 5.1. Ý nghĩa

Nhãn **TransientTransactionError** cho biết transaction gặp lỗi tạm thời mà **việc bắt đầu một transaction mới rồi chạy lại toàn bộ body có thể thành công**.

Tình huống có thể gặp:

- **Write conflict** giữa các transaction/operations trên cùng document.
- **Primary stepdown** hoặc election ảnh hưởng operation trong transaction.
- Một số **network errors** khi transaction đang thực thi.
- Những lỗi tạm thời khác được server/driver gắn label theo ngữ cảnh.

**Không phải tất cả write conflicts hay timeouts đều được xử lý giống nhau ở mọi trường hợp.** Quyết định dựa vào error label và phase của transaction.

### 5.2. Dòng thời gian hai transaction cạnh tranh

~~~text
Tx A                           Tx B
  |                              |
  |-- READ account ACC-A -------|
  |                              |
  |-- UPDATE ACC-A               |-- UPDATE ACC-A
  |                              |
  |  Write conflict / abort <----+
  |
  v
MongoException
label=TransientTransactionError
  |
  v
Abort/end attempt T1
Start attempt T2 với snapshot mới
Run ALL operations again
~~~

Nếu transaction retry thành công, nó chạy trên trạng thái dữ liệu mới hơn; điều kiện business (ví dụ số dư đủ) **phải được kiểm tra lại** chứ không dùng kết quả cũ của attempt trước.

### 5.3. Không retry riêng operation lỗi

Sai:

~~~text
Begin transaction
  debit account A
  credit account B -> TransientTransactionError
  retry only credit B
  insert transfer
Commit
~~~

Đúng:

~~~text
Begin transaction attempt 1
  debit account A
  credit account B -> TransientTransactionError
Abort attempt 1

Begin transaction attempt 2
  re-check balance
  debit account A
  credit account B
  insert transfer
Commit
~~~

Lỗi tạm thời không bảo đảm attempt thứ hai sẽ thành công, nên **phải có retry budget**.

### 5.4. Body có thể chạy nhiều lần

Callback API của driver có thể tự gọi lại toàn bộ callback khi gặp TTE. Vì vậy mọi thứ nằm trong callback phải **an toàn khi re-execute**:

~~~text
transaction callback:
  read MongoDB
  update MongoDB
  insert MongoDB
  return result
~~~

Không nên đặt các side effects không thuộc transaction ngay trong callback:

~~~text
transaction callback:
  call payment provider to charge card   <-- nguy hiểm
  send confirmation email                <-- nguy hiểm
  publish Kafka message                  <-- nguy hiểm
  update MongoDB
~~~

Callback có thể chạy lại. MongoDB chỉ rollback những writes thuộc MongoDB transaction; nó **không thu hồi tự động** email, charge hoặc message đã gửi.

### 5.5. Vậy có cần abort attempt cũ?

Với **Core API**, khi gặp lỗi trong body:

- Nếu transaction vẫn active, ứng dụng nên **abort** hoặc dùng cơ chế driver kết thúc attempt cũ.
- Bắt đầu transaction mới cho lần retry.
- Ghi nhận lỗi abort nếu cần, nhưng không để lỗi abort che mất nguyên nhân chính.
- Không tiếp tục commit một body đã gặp lỗi.

Callback API quản lý abort/retry phù hợp; không nên tự viết vòng retry ngoài **withTransaction** mà không hiểu khả năng callback đã retry bên trong.

## 6. UnknownTransactionCommitResult: không biết commit đã thành công chưa

### 6.1. Ý nghĩa

Nhãn **UnknownTransactionCommitResult** báo rằng client **không thể xác định kết quả của commit** từ response nhận được.

Nó **không đồng nghĩa commit thất bại**, cũng **không đồng nghĩa commit chắc chắn thành công**.

~~~text
                 commitTransaction()
                          |
                +---------+---------+
                |                   |
                v                   v
         Server commit rồi    Server chưa commit /
         response bị mất      result chưa rõ
                |                   |
                +---------+---------+
                          |
             Client không phân biệt được
                   bằng response hiện có
                          |
                          v
             UnknownTransactionCommitResult
~~~

### 6.2. Những nguyên nhân có thể tạo unknown result

- Kết nối đứt sau khi gửi commit.
- Primary thay đổi khi client đang chờ commit.
- Client timeout trước khi biết kết quả thực tế.
- Commit/write concern chưa được xác nhận trong thời hạn tương ứng.
- Các tình huống khác được driver/server gắn label này.

Không tự nhận định chỉ từ một lỗi network hoặc timeout rằng commit đã được rollback.

### 6.3. Vì sao chỉ retry commit?

Đối với cùng session và transaction identity, **commitTransaction** là thao tác được thiết kế để có thể retry. Server/driver sử dụng transaction identity để xử lý commit lặp phù hợp, thay vì xem đó là một lần bắt đầu nghiệp vụ mới.

**Sai:**

~~~text
1. Body transfer A -> B đã chạy.
2. commitTransaction -> UnknownTransactionCommitResult.
3. startTransaction mới.
4. Trừ A và cộng B lần nữa.
~~~

Nếu commit đầu tiên thực sự đã thành công, cách trên tạo rủi ro chuyển tiền hai lần.

**Đúng:**

~~~text
1. Body transfer A -> B đã chạy.
2. commitTransaction -> UnknownTransactionCommitResult.
3. retry commitTransaction của cùng session/transaction.
4. Chỉ thông báo success khi kết quả commit được xác nhận.
5. Nếu hết retry budget vẫn unknown, giữ trạng thái IN_DOUBT
   và đối soát; không khẳng định failed hoặc tự chạy body mới.
~~~

### 6.4. Không dùng abort để “chắc chắn rollback” khi commit unknown

Sau khi một commit có thể đã thành công, **abortTransaction không phải một phép undo commit**. Nếu outcome vẫn chưa rõ, một lệnh abort không chứng minh các thay đổi đã được hoàn tác.

Không xuất response “giao dịch chắc chắn chưa chạy” dựa trên việc client đã gọi abort sau một unknown commit result.

### 6.5. Retry commit không giống retryWrites=true

MongoDB documentation nêu **commitTransaction là retryable write**, và driver có thể thử lại commit **ngay cả khi retryWrites bị tắt**, tùy API/driver. Điều này khác với các write operations **bên trong** một transaction: chúng không được tự retry riêng lẻ như những standalone retryable writes.

Callback API có logic xử lý UCTR. Core API đòi ứng dụng tự xây retry logic theo error label, ngoài những hành vi retry hữu hạn mà driver có thể thực hiện.

### 6.6. Hết hạn retry thì xử lý ra sao?

Một hệ thống thực tế cần giới hạn retry để không block API vô hạn:

1. Ghi một mã **requestId/business operation ID** cố định.
2. Retry **commit** trong khoảng thời gian cho phép.
3. Nếu vẫn unknown, trả trạng thái **PENDING/UNKNOWN** thay vì thông báo failed chắc chắn.
4. Đối soát trạng thái giao dịch qua unique business record/ledger sau khi có thể đọc majority committed state.
5. Định nghĩa cơ chế tự khôi phục và báo cho người dùng khi outcome đã được xác nhận.

Nếu business operation phải có exactly-once effect, cần thiết kế **idempotency** bổ sung chứ không chỉ dựa vào retry commit.

## 7. Sơ đồ quyết định xử lý lỗi

~~~text
START TRANSACTION
       |
       v
RUN BODY
       |
       +-- Thành công ----------> COMMIT
       |                            |
       |                            +-- SUCCESS -> DONE
       |                            |
       |                            +-- UCTR
       |                            |    |
       |                            |    v
       |                            |  RETRY SAME COMMIT
       |                            |    |
       |                            |    +-- SUCCESS -> DONE
       |                            |    |
       |                            |    +-- DEADLINE -> IN_DOUBT
       |                            |
       |                            +-- Lỗi khác
       |                                 -> xử lý theo loại
       |
       +-- TransientTransactionError
       |         |
       |         v
       |    ABORT OLD ATTEMPT
       |         |
       |         v
       |    RETRY BUDGET?
       |         |
       |         +-- CÓ -> START NEW TRANSACTION -> RUN BODY
       |         |
       |         +-- KHÔNG -> RETRY_EXHAUSTED
       |
       +-- Lỗi không retryable
                 |
                 v
              ABORT / FAIL
~~~

Sơ đồ thể hiện quy tắc chính. Với một số lỗi ở **commit** có những semantics và labels riêng, cần làm theo hướng dẫn của driver/version cụ thể. Đừng suy từ mọi exception commit là “hãy retry cả transaction”.

## 8. Bảng phân loại chi tiết theo phase

| Phase | Tín hiệu | Ý nghĩa thực dụng | Hành động |
|---|---|---|---|
| Body operation | **TransientTransactionError** | Attempt hiện tại không thể tiếp tục an toàn; lỗi có thể tạm thời. | Abort/end attempt, retry **whole body** trong transaction mới. |
| Body operation | **DuplicateKey** | Unique constraint vi phạm hoặc có request trùng. | Không retry mù; xác định dữ liệu/idempotency. |
| Body operation | **Validation / Unauthorized** | Không phù hợp schema/quyền. | Abort; trả lỗi nghiệp vụ hoặc cấu hình. |
| Body operation | **TransactionTooLargeForCache** | Giao dịch quá lớn đối với cache. | Giảm kích thước/thiết kế lại; không kỳ vọng retry y nguyên sẽ thành công. |
| Commit | **UnknownTransactionCommitResult** | Không rõ server đã commit hay chưa. | Retry **same commit**; nếu không xác nhận được, giữ unknown và đối soát. |
| Commit | Commit được xác nhận | Giao dịch thành công với write concern đã cấu hình. | Trả success, phát các side effects sau commit theo thiết kế an toàn. |
| Commit | Lỗi không xác định được bằng quy tắc chung | Phải xem label/code và driver semantics. | Phân loại; không tự suy failed/success. |
| Bất kỳ | Timeout/cancel trước khi gửi lệnh | Có thể chưa chạy gì, nhưng cần xác minh phase. | Không dùng cùng retry policy cho mọi timeout. |

**Một error code đơn lẻ không thay thế error label**, và **phase** là thông tin không thể bỏ qua khi triển khai transaction error handling.

## 9. Mẫu Core API trong mongosh: retry đúng pha

Ví dụ sau trình bày một giao dịch chuyển tiền giữa hai documents **trong cùng MongoDB deployment**. Nó sử dụng hai vòng retry khác nhau:

- Vòng ngoài: retry **toàn transaction** khi body gặp TTE.
- Vòng trong: retry **commit của cùng transaction** khi commit gặp UCTR.

Đây là lab minh họa; ứng dụng tài chính thật phải có ledger, authorization, giới hạn retries theo deadline, idempotency, đối soát và cơ chế kiểm toán.

### 9.1. Hàm kiểm tra label

~~~javascript
function hasLabel(error, label) {
  return Boolean(
    error &&
    Array.isArray(error.errorLabels) &&
    error.errorLabels.includes(label)
  );
}
~~~

Với Java Driver, nên dùng **MongoException.hasErrorLabel()**; ở mongosh đoạn trên dùng field errorLabels theo cách minh họa thường gặp.

### 9.2. Mẫu giao dịch có bounded retry

~~~javascript
function transferWithRetry({
  requestId,
  fromId,
  toId,
  amountCents,
  maxBodyAttempts = 4,
  maxCommitAttempts = 5
}) {
  if (!requestId || fromId === toId) {
    throw new Error("Invalid transfer identity");
  }

  if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
    throw new Error("amountCents must be a positive safe integer");
  }

  const session = db.getMongo().startSession();
  const txDb = session.getDatabase("mongo_transaction_error_lab");
  const accounts = txDb.accounts;
  const transfers = txDb.transfers;

  try {
    for (
      let bodyAttempt = 1;
      bodyAttempt <= maxBodyAttempts;
      bodyAttempt++
    ) {
      session.startTransaction({
        readConcern: { level: "snapshot" },
        writeConcern: { w: "majority" },
        readPreference: { mode: "primary" }
      });

      try {
        const debit = accounts.updateOne(
          {
            _id: fromId,
            balanceCents: { $gte: amountCents }
          },
          {
            $inc: { balanceCents: -amountCents }
          }
        );

        if (debit.matchedCount !== 1) {
          throw new Error("INSUFFICIENT_FUNDS_OR_SOURCE_MISSING");
        }

        const credit = accounts.updateOne(
          { _id: toId },
          {
            $inc: { balanceCents: amountCents }
          }
        );

        if (credit.matchedCount !== 1) {
          throw new Error("DESTINATION_MISSING");
        }

        transfers.insertOne({
          _id: "TX-" + requestId,
          requestId,
          fromAccount: fromId,
          toAccount: toId,
          amountCents: NumberLong(amountCents),
          status: "COMPLETED"
        });
      } catch (error) {
        // Chỉ abort khi body thất bại, chưa bước sang commit.
        try {
          session.abortTransaction();
        } catch (abortError) {
          // Log abortError; giữ lại lỗi body làm nguyên nhân chính.
        }

        if (
          hasLabel(error, "TransientTransactionError") &&
          bodyAttempt < maxBodyAttempts
        ) {
          print("Transient body failure; restart transaction");
          continue;
        }

        throw error;
      }

      // Body đã hoàn tất. Không chạy lại body vì chỉ commit unknown.
      for (
        let commitAttempt = 1;
        commitAttempt <= maxCommitAttempts;
        commitAttempt++
      ) {
        try {
          session.commitTransaction();

          return {
            status: "COMMITTED",
            requestId
          };
        } catch (error) {
          if (hasLabel(error, "UnknownTransactionCommitResult")) {
            if (commitAttempt < maxCommitAttempts) {
              print("Unknown commit result; retry same commit");
              continue;
            }

            // Không được kết luận transaction đã abort.
            return {
              status: "IN_DOUBT",
              requestId,
              message: "Commit outcome needs reconciliation"
            };
          }

          throw error;
        }
      }
    }
  } finally {
    session.endSession();
  }
}
~~~

Gọi ví dụ một lần trên dữ liệu mẫu:

~~~javascript
transferWithRetry({
  requestId: "REQ-001",
  fromId: "ACC-A",
  toId: "ACC-B",
  amountCents: 20000
});
~~~

### 9.3. Giới hạn của mẫu trên

Mẫu có chủ đích tập trung vào **phân nhánh TTE/UCTR**, không phải giải pháp tài chính production:

1. Vòng lặp có số attempts hữu hạn nhưng **chưa có deadline toàn cục/backoff**.
2. Một **DuplicateKey** khi dùng lại requestId không được tự biến thành success. Cần đối chiếu document transfer đã commit và so payload.
3. Nếu commit có một lỗi **khác UCTR**, code chuyển lỗi ra caller để phân loại; không suy mọi lỗi commit là chắc chắn abort.
4. Nếu status = **IN_DOUBT**, caller **không được tự phát một transfer mới**, phải đối soát.
5. Việc tăng/giảm số dư dùng NumberLong ở database và numeric literal trong lab nhỏ; production cần chốt miền số, overflow, validation và schema nhất quán.
6. Nếu session bị đóng khi commit vẫn unknown, không thể đơn giản retry commit bằng một session mới. Thay vào đó phải dùng nghiệp vụ reconciliation với cùng requestId.
7. Không có email, charge thẻ hoặc gửi message trong body vì body có thể chạy lại.
8. Không nên để một lỗi abort thứ cấp che nguyên nhân đã làm body thất bại.

### 9.4. Không retry mãi mãi trong mongosh

Ví dụ tài liệu đôi khi dùng vòng **while(true)** để trình bày thuật toán. Trong production, phải có:

- **Deadline theo request hoặc operation**.
- Số lần retry tối đa/budget.
- **Backoff có jitter** khi retry transient theo chính sách phù hợp.
- Cancellation/shutdown handling.
- Metrics cho từng phase.
- Trạng thái **IN_DOUBT** để không buộc client chờ vô hạn.

## 10. Java Sync Driver: chọn Callback API hay Core API?

MongoDB Java Sync Driver có hai cách điều khiển transaction:

| Phong cách | APIs | Retry TTE/UCTR |
|---|---|---|
| **Callback / Convenient API** | **ClientSession.withTransaction(...)** | Driver tích hợp retry toàn transaction khi TTE và retry commit khi UCTR theo chính sách driver. |
| **Core API** | **startTransaction, commitTransaction, abortTransaction** | Ứng dụng tự xây vòng retry theo phase/error label, ngoài các retries cấp driver cho commit. |

Để giảm lỗi cài đặt, **withTransaction** thường nên là lựa chọn mặc định khi logic phù hợp. Chọn Core API khi cần kiểm soát chặt state machine, lịch retry, telemetry hoặc xử lý unknown outcome chuyên biệt.

### 10.1. Java: withTransaction cơ bản

~~~java
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
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public final class TransferService {
    private final MongoClient client;

    public TransferService(MongoClient client) {
        this.client = client;
    }

    public void transfer(
            String requestId,
            String fromId,
            String toId,
            long amountCents) {

        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("Missing requestId");
        }
        if (fromId.equals(toId) || amountCents <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        MongoDatabase database = client.getDatabase(
                "mongo_transaction_error_lab"
        );

        MongoCollection<Document> accounts =
                database.getCollection("accounts");

        MongoCollection<Document> transfers =
                database.getCollection("transfers");

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        try (ClientSession session = client.startSession()) {
            session.withTransaction(() -> {
                UpdateResult debit = accounts.updateOne(
                        session,
                        Filters.and(
                                Filters.eq("_id", fromId),
                                Filters.gte("balanceCents", amountCents)
                        ),
                        Updates.inc("balanceCents", -amountCents)
                );

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                            "Insufficient funds or source missing"
                    );
                }

                UpdateResult credit = accounts.updateOne(
                        session,
                        Filters.eq("_id", toId),
                        Updates.inc("balanceCents", amountCents)
                );

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                            "Destination account missing"
                    );
                }

                transfers.insertOne(
                        session,
                        new Document("_id", "TX-" + requestId)
                                .append("requestId", requestId)
                                .append("fromAccount", fromId)
                                .append("toAccount", toId)
                                .append("amountCents", amountCents)
                                .append("status", "COMPLETED")
                );

                return null;
            }, options);
        }
    }
}
~~~

**Giải thích từng bước:**

1. Tạo **TransactionOptions** với snapshot read/majority write/primary.
2. Tạo **ClientSession** từ đúng MongoClient.
3. Gọi **withTransaction(callback, options)**.
4. Mọi thao tác **updateOne/insertOne** trong body đều truyền cùng **session**.
5. Nếu một operation có error label TTE, driver callback API có logic retry **whole transaction**.
6. Nếu commit nhận UCTR, driver callback API có logic retry **commit**, không phát lại body chỉ vì commit unknown.
7. Nếu body ném business exception như Insufficient funds, đó không phải một MongoException có TTE và không nên retry vô ích.

**Quan trọng:** method này không tự phân biệt requestId đã xử lý trước đó với một request mới; **DuplicateKey** trên transfer ID cần reconciliation ở service/API. Chỉ dùng duy nhất unique ID trong code không tự tạo một API exactly-once hoàn chỉnh.

### 10.2. Những lỗi dễ gặp khi dùng withTransaction

**Thiếu session ở một thao tác:**

~~~java
session.withTransaction(() -> {
    accounts.updateOne(
            Filters.eq("_id", "ACC-A"),
            Updates.inc("balanceCents", -20000L)
    ); // Không truyền session!
    return null;
}, options);
~~~

Lệnh trên **không tự tham gia transaction** chỉ vì được gọi trong callback; Java Driver API cần overload nhận **ClientSession**. Thao tác có thể ghi ngoài transaction và không rollback cùng body.

**Tự retry bên ngoài một callback vốn đã retry:**

~~~text
for each retry:
    session.withTransaction(callback)
~~~

Nếu không có mục đích rõ, điều này có thể làm budget lớn hơn tưởng tượng. Hãy xem policy của driver và tránh tạo vòng retry lồng chồng không kiểm soát.

**Không nên làm việc ngoài MongoDB trong callback:**

~~~java
session.withTransaction(() -> {
    paymentGateway.charge(...);  // Side effect ngoài transaction.
    accounts.updateOne(session, ...);
    return null;
});
~~~

Callback có thể chạy lại và gọi charge lần nữa. Tách external effects sang workflow idempotent sau commit hoặc **transactional outbox**.

### 10.3. Java Core API: khung retry đúng phase

Khi cần tự điều khiển, có thể dùng một state machine:

~~~java
// PSEUDOCODE: minh họa thuật toán, không phải class Java hoàn chỉnh.
for (int bodyAttempt = 0; bodyAttempt < maxBodyAttempts; bodyAttempt++) {
    session.startTransaction(transactionOptions);

    try {
        executeEntireBusinessBody(session);
    } catch (MongoException e) {
        safeAbort(session);

        if (e.hasErrorLabel("TransientTransactionError")
                && retryBudgetLeft()) {
            backoff();
            continue; // Transaction MỚI; chạy lại body.
        }

        throw e;
    } catch (RuntimeException e) {
        safeAbort(session);
        throw e; // Ví dụ lỗi business không retryable.
    }

    // Body đã thành công.
    while (true) {
        try {
            session.commitTransaction();
            return; // SUCCESS
        } catch (MongoException e) {
            if (e.hasErrorLabel("UnknownTransactionCommitResult")) {
                if (commitRetryBudgetLeft()) {
                    backoff();
                    continue; // CHỈ retry commit.
                }

                throw new CommitOutcomeUnknownException(e);
            }

            throw e; // Cần phân loại theo error semantics.
        }
    }
}

throw new RetryBudgetExceededException();
~~~

Các method **safeAbort**, **retryBudgetLeft**, **backoff** và các exception tùy biến trong pseudocode là trách nhiệm ứng dụng, **không phải APIs sẵn có của driver**. Mục đích là ghi rõ vị trí retry.

Trong Core API thật, **commitTransaction có thể đã được driver thử lại ở mức nội bộ**; ứng dụng vẫn phải dùng error label cho kết quả được driver trả ra. Tính đúng đắn của state machine quan trọng hơn số lần gửi network request.

### 10.4. Java: nhận diện error labels

~~~java
import com.mongodb.MongoException;

public final class TransactionErrorClassifier {
    public static boolean isTransient(MongoException error) {
        return error.hasErrorLabel("TransientTransactionError");
    }

    public static boolean isUnknownCommit(MongoException error) {
        return error.hasErrorLabel("UnknownTransactionCommitResult");
    }
}
~~~

Không viết logic dựa vào **message.contains("WriteConflict")** vì thông báo có thể thay đổi theo version/language và không thể hiện đầy đủ ngữ cảnh.

### 10.5. Một session không dành cho parallel operations

MongoDB Java Driver không hỗ trợ chạy các thao tác song song trong **cùng một transaction**. Không chia sẻ một **ClientSession** duy nhất cho nhiều threads rồi chạy đồng thời.

Một MongoClient được tái sử dụng toàn ứng dụng là bình thường; các logical sessions cần được quản lý riêng theo request/workflow phù hợp.

## 11. Spring Data MongoDB: @Transactional và MongoTransactionManager

Spring Data MongoDB hỗ trợ transaction thông qua **MongoTransactionManager** và **@Transactional**, hoặc programmatic APIs như **TransactionTemplate**.

Điểm quan trọng: **Spring @Transactional không tự đồng nghĩa với Java Driver withTransaction retry policy**. Spring quản lý transaction boundary, nhưng error labels và retry behavior phải được cấu hình/triển khai đúng.

### 11.1. Cấu hình TransactionManager

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        return new MongoTransactionManager(databaseFactory, options);
    }
}
~~~

Với Spring Data MongoDB, transaction support cần được bật/cấu hình phù hợp; không giả định mọi MongoTemplate operation tự động nằm trong transaction chỉ vì ứng dụng có MongoDB.

### 11.2. Service với @Transactional

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SpringTransferService {
    private final MongoTemplate mongoTemplate;

    public SpringTransferService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @Transactional
    public void transfer(
            String requestId,
            String fromId,
            String toId,
            long amountCents) {

        if (amountCents <= 0 || fromId.equals(toId)) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        var debit = mongoTemplate.updateFirst(
                Query.query(
                        Criteria.where("_id").is(fromId)
                                .and("balanceCents").gte(amountCents)
                ),
                new Update().inc("balanceCents", -amountCents),
                "accounts"
        );

        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Insufficient funds or source missing"
            );
        }

        var credit = mongoTemplate.updateFirst(
                Query.query(Criteria.where("_id").is(toId)),
                new Update().inc("balanceCents", amountCents),
                "accounts"
        );

        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Destination missing"
            );
        }

        mongoTemplate.insert(
                new org.bson.Document("_id", "TX-" + requestId)
                        .append("requestId", requestId)
                        .append("amountCents", amountCents)
                        .append("status", "COMPLETED"),
                "transfers"
        );
    }
}
~~~

**Lưu ý:**

- **@Transactional** điều phối MongoDB session/transaction nếu transaction manager phù hợp đã được đăng ký.
- Nếu một operation ném exception và Spring đánh dấu rollback, những writes MongoDB thuộc transaction sẽ bị abort theo cơ chế.
- **Đừng đặt side effects ngoài DB trong method transactional** rồi mong Spring rollback cả chúng.
- **Self-invocation** một method @Transactional qua **this.method()** có thể không đi qua Spring proxy, tùy phương thức cấu hình AOP.
- Method trên là ví dụ hạch toán đơn giản, không bao gồm reconciliation/idempotency đầy đủ.

### 11.3. Spring Retry cho TransientTransactionError

Spring Data documentation khuyến nghị dùng **Spring Retry** khi ứng dụng cần retry transient transaction errors.

Nhưng rất quan trọng về **vị trí retry**:

~~~text
Retry aspect/service layer
      |
      +--> Transaction attempt 1
      |       begin -> body -> error/rollback
      |
      +--> Transaction attempt 2
              begin -> body -> commit
~~~

Để retry cả transaction, mỗi attempt cần **một transaction boundary mới**, chứ không gọi lại DAO method bên trong **cùng transaction đã abort**.

Trong Spring proxy-based AOP, thứ tự của **Retry interceptor** và **Transaction interceptor** quyết định liệu mỗi retry có mở một transaction mới không. Không chỉ gắn **@Retryable** và **@Transactional** cạnh nhau rồi tự giả định thứ tự/hiệu lực đã đúng.

### 11.4. Với UnknownTransactionCommitResult, không retry cả service

Một lỗi dễ mắc:

~~~text
@Retryable(for = MongoException.class)
@Transactional
public void transfer(...) { ... }
~~~

Nếu lỗi xảy ra tại **commit** và có nhãn **UnknownTransactionCommitResult**, retry cả method có thể chạy lại nghiệp vụ đã commit.

Do đó:

- Tách **retry TTE trước commit** khỏi **retry commit unknown**.
- Không dùng một cấu hình retry blanket cho mọi MongoException.
- Nếu dùng Spring transaction manager, xem cơ chế tùy biến/retry **doCommit** phù hợp tài liệu Spring Data thay vì phát lại method nghiệp vụ khi commit unknown.
- Nếu còn unknown sau budget, bảo tồn business requestId để đối soát thay vì coi là rollback chắc chắn.

### 11.5. Spring Data MongoTransactionManager và doCommit

Tài liệu Spring Data nêu có thể override **MongoTransactionManager#doCommit(MongoTransactionObject)** để triển khai retry commit theo hướng dẫn MongoDB.

Đây là **điểm mở rộng cho commit retry**, không phải nơi chạy lại toàn bộ business code. Khi mở rộng, phải nắm rõ:

1. Spring Data version/visibility của transaction object.
2. Quy tắc propagation và rollback của PlatformTransactionManager.
3. Ngữ cảnh MongoDB ClientSession của chính transaction đang commit.
4. Trạng thái unknown khi retry hết budget.
5. Telemetry và integration tests cho failover/network.

Không tùy tiện viết lại commit logic mà thiếu test với driver/server version thực tế.

### 11.6. TransactionTemplate và TransactionalOperator

Ngoài @Transactional, Spring hỗ trợ:

- **TransactionTemplate** cho Java imperative.
- **TransactionalOperator** cho Reactive MongoDB.

Những APIs này giúp quản lý transaction boundary nhưng **không biến một lỗi unknown commit thành chắc chắn abort**. Reactive code còn cần chú ý session nằm trong **Reactor Context** và không dùng session/connection ngoài luồng giao dịch.

## 12. Retry policy: luôn có budget và deadline

Không chỉ cần phân biệt retry đúng phase, mà còn cần giới hạn retry hợp lý.

### 12.1. Các thành phần cần định nghĩa

| Thành phần | Vai trò |
|---|---|
| **Max body attempts** | Giới hạn số lần chạy lại toàn transaction. |
| **Max commit attempts** | Giới hạn số lần retry commit khi UCTR. |
| **Overall deadline** | Không để một API request chờ quá lâu. |
| **Backoff** | Tránh retry ngay liên tục khi hệ thống đang contention. |
| **Jitter** | Giảm nhiều clients retry đồng loạt. |
| **Cancellation policy** | Phân biệt client mất kết nối với trạng thái commit chưa rõ. |
| **Idempotency key** | Giúp nhận diện cùng một nghiệp vụ qua nhiều HTTP requests. |
| **Reconciliation** | Xác nhận final outcome khi client không nhận được commit response. |

### 12.2. Ví dụ backoff minh họa

~~~text
attempt 1: chạy ngay
attempt 2: chờ ngẫu nhiên khoảng ngắn
attempt 3: tăng khoảng chờ trong giới hạn
attempt 4: thử lần cuối trước deadline
~~~

Không coi các con số này là SLA mặc định của MongoDB. Chọn policy dựa trên **request timeout**, latency budget, transaction lifetime và đặc điểm workload.

### 12.3. Transaction lifetime

MongoDB thường đặt **transactionLifetimeLimitSeconds mặc định là 60 giây**, có thể cấu hình trong những deployment được hỗ trợ.

Transaction quá lâu có thể hết hạn và bị abort nhằm giảm áp lực storage cache/snapshot history. Vì vậy body cần **ngắn, đúng phạm vi**, không thực hiện truy vấn chậm hoặc chờ người dùng trong transaction.

### 12.4. Retry budget có thể bị tiêu thụ bởi driver

Callback API có cơ chế retry riêng; Core API có thể dùng driver-level retry cho commit. Khi thêm retry ở service, hãy tính đến **tổng số attempts thực tế** thay vì chỉ đếm số vòng lặp trong controller.

### 12.5. Không dùng retry để chữa dữ liệu sai

Các tình huống như duplicate key, schema validation fail, authorization fail, missing destination hay insufficient funds thường **không thể trở thành hợp lệ chỉ vì chạy lại y nguyên**.

Retry nên có chủ đích theo **error label/phase** và **mức độ có thể phục hồi**, không phải “thử cho đến khi thành công”.

## 13. Những loại lỗi cụ thể cần phân biệt

### 13.1. WriteConflict

Hai transaction có thể cùng cố cập nhật một document. Một transaction phải abort khi không thể duy trì isolation do xung đột.

~~~text
Tx A đọc account balance
Tx B thay balance và commit
Tx A cố update dựa trên snapshot cũ
             |
             v
        WriteConflict
             |
             v
       Abort/retry Tx A
       nếu có TTE label
~~~

Không nhất thiết mọi write conflict là cùng một loại exception ở mọi phase/server version. Trong transaction body, **dựa vào error label** để quyết định retry toàn body.

Trong một attempt mới, **đọc lại** balance, status, version và các điều kiện nghiệp vụ; không sử dụng kết quả snapshot của attempt cũ.

### 13.2. NoSuchTransaction

Server có thể trả một lỗi biểu thị transaction number/state không còn tồn tại trong một ngữ cảnh nhất định, ví dụ transaction đã abort hoặc session/transaction lifecycle không phù hợp.

Không nên xử lý mọi **NoSuchTransaction** bằng cách commit lại vô hạn. Cần xem:

- Lỗi xảy ra trong **body hay commit**?
- Có label **TransientTransactionError** hoặc **UnknownTransactionCommitResult** không?
- Transaction đã được abort, hết lifetime hay session bị sử dụng sai?
- Driver có retry commit và update thông tin session đúng không?

Lỗi có thể là triệu chứng của bug lifecycle, không chỉ là transient network issue.

### 13.3. DuplicateKey

Lỗi unique index thường biểu thị hai writes cố tạo hoặc cập nhật cùng một business key.

~~~javascript
db.transfers.createIndex(
  { requestId: 1 },
  { unique: true }
);
~~~

Nếu ứng dụng đã tạo transfer **REQ-001** rồi một request khác dùng lại cùng ID, **DuplicateKey không được tự coi là success**. Phải đọc bản ghi đã commit và so:

- fromAccount;
- toAccount;
- amountCents;
- tenantId/currency nếu có;
- trạng thái nghiệp vụ;
- checksum hoặc request fingerprint.

Nếu payload khác, đó là **idempotency-key reuse conflict**, không phải “giao dịch đã hoàn thành đúng yêu cầu này”.

**Chi tiết phiên bản:** từ MongoDB **8.1**, một thao tác **upsert trong multi-document transaction** gặp duplicate key **không được retry tự động theo behavior đã thay đổi**. Trong MongoDB **6.2+**, còn có thay đổi đối với TransactionTooLargeForCache. Vì vậy không áp dụng một danh sách “mọi lỗi có thể retry” cố định qua tất cả server versions.

### 13.4. TransactionTooLargeForCache

Khi transaction gây áp lực lớn lên WiredTiger cache hoặc không thể nằm trong cache theo điều kiện của server, MongoDB có thể trả **TransactionTooLargeForCache**.

Từ MongoDB **6.2**, server không retry transaction kiểu này vì retry cùng khối lượng dữ liệu thường khó thành công.

Hướng xử lý:

1. Giảm số documents/bytes tham gia một transaction.
2. Thu hẹp phạm vi business unit.
3. Không đọc hoặc giữ nhiều dữ liệu không cần thiết trong transaction.
4. Kiểm tra index và query plan để giảm lượng dữ liệu quét.
5. Cân nhắc chuyển một batch lớn thành nhiều đơn vị nghiệp vụ độc lập nếu invariants cho phép.

Không dùng vòng retry vô hạn để bù cho một transaction quá lớn về mặt thiết kế.

### 13.5. Timeout và lỗi mạng

Timeout có nhiều nguồn:

- **Client-side deadline** hoặc socket timeout.
- **Server maxTimeMS** của một operation.
- **maxCommitTime** của transaction commit.
- **wtimeout** khi chưa đạt write concern.
- Transaction lifetime exceeded.

Không phải mọi timeout đều mang cùng label hoặc có cùng final outcome.

Đặc biệt, một **commit write concern timeout** có thể xảy ra trong khi server đã thực hiện một phần hoặc toàn bộ công việc cần thiết. Khi outcome chưa rõ, tránh trả “abort chắc chắn” mà không có bằng chứng.

### 13.6. Authentication và authorization

Nếu user không có quyền read/write collection cần thiết trong transaction, lỗi authorization không thể sửa bằng retry. Kiểm tra roles, collection names và tenant policies.

### 13.7. Schema validation và business validation

Một lỗi như:

~~~text
Cannot insert transfer because amountCents is negative
~~~

không trở thành hợp lệ nếu request chạy thêm 100 lần. Domain service nên validate trước khi mở transaction hoặc tại đúng vị trí trong body; lỗi business không nên gắn lại thành TTE tùy tiện.

### 13.8. Transaction đã bị abort do một thao tác lỗi

Khi một operation trong transaction gặp lỗi dẫn đến transaction abort, **không chạy tiếp các lệnh nghiệp vụ như thể mọi thứ vẫn ổn**, rồi cố commit.

Core API cần xác định trạng thái, abort khi cần, bắt đầu attempt mới nếu retryable. Callback API thực hiện lifecycle tương ứng.

## 14. Transactional outbox: side effects sau commit an toàn hơn

Một transaction thường đi cùng yêu cầu phát sự kiện:

~~~text
Transfer committed -> send "TransferCompleted" event
~~~

Nếu phát event **trước commit**:

~~~text
Send Kafka event
       |
       v
MongoDB transaction aborts
       |
       v
Consumer đã xử lý một giao dịch không commit!
~~~

Nếu phát event **sau commit**, ứng dụng có thể crash giữa lúc commit thành công và phát event:

~~~text
MongoDB commit success
       |
       v
Process crashes
       |
       v
Event không được gửi
~~~

### 14.1. Outbox pattern

Một giải pháp thông dụng:

~~~text
MongoDB transaction:
  UPDATE account A
  UPDATE account B
  INSERT transfer record
  INSERT outbox event

COMMIT
   |
   v
Background dispatcher:
  READ outbox event
  PUBLISH to broker
  MARK dispatched / checkpoint
~~~

Các writes trong MongoDB transaction commit/abort cùng nhau. Outbox event chỉ xuất hiện khi transaction đã commit.

Ví dụ insert outbox **bên trong cùng transaction**:

~~~javascript
// Bên trong transaction body, dùng cùng session.
txDb.outbox.insertOne({
  _id: "EVENT-REQ-001",
  eventType: "TransferCompleted",
  requestId: "REQ-001",
  aggregateId: "TX-REQ-001",
  payload: {
    amountCents: NumberLong(20000)
  },
  dispatched: false
});
~~~

**Mỗi operation phải dùng cùng session**. Có thể thêm outbox insert vào transaction body Java đã trình bày, ví dụ **outbox.insertOne(session, eventDocument)**.

### 14.2. Outbox consumer vẫn cần idempotency

Dispatcher có thể publish thành công nhưng crash trước khi đánh dấu dispatched. Khi chạy lại, nó có thể publish event lần hai.

Consumer cần dedupe theo **eventId** hoặc business key; không được coi outbox tự tạo exactly-once trên toàn bộ Kafka/email/payment systems.

### 14.3. Không gọi payment provider trong callback

Giao thức với payment provider nên dùng **idempotency key của provider** hoặc saga/process manager phù hợp. MongoDB transaction không rollback một HTTP charge bên ngoài.

## 15. Idempotency key: phân biệt retry của transaction và retry của yêu cầu nghiệp vụ

### 15.1. Hai loại retry khác nhau

**Transaction-level retry:**

~~~text
Một HTTP request REQ-001
    |
    +-- Tx attempt 1 -> TTE
    +-- Tx attempt 2 -> COMMIT
~~~

**Application/business-level retry:**

~~~text
HTTP request REQ-001 -> timeout

Sau đó client gửi lại:
HTTP request REQ-001 -> retry từ bên ngoài
~~~

Ngay cả khi driver xử lý tốt hai error labels, hệ thống vẫn phải phân biệt **HTTP request lặp** với **business operation mới**.

### 15.2. Unique business key trong transaction

Đặt một **requestId** ổn định trước khi chạy body:

~~~javascript
{
  _id: "TX-REQ-001",
  requestId: "REQ-001",
  fromAccount: "ACC-A",
  toAccount: "ACC-B",
  amountCents: NumberLong(20000)
}
~~~

Và unique index:

~~~javascript
db.transfers.createIndex(
  { requestId: 1 },
  { unique: true }
);
~~~

Khi transaction retry vì TTE, body có thể được thực thi lại trong một transaction mới. **Các writes chưa commit của attempt cũ bị rollback**, vì vậy việc dùng cùng business ID giúp giữ nhận diện ổn định.

Nếu một transaction khác đã commit cùng requestId, một lần attempt mới có thể gặp **DuplicateKey**. Đó là tín hiệu cần **đối chiếu** kết quả của yêu cầu đã xử lý, không phải lý do tự trừ tiền tiếp.

### 15.3. Kiểm tra record hiện tại chưa đủ nếu thiếu unique constraint

Pattern:

~~~text
if transfers.findOne({requestId}) == null:
    debit and credit
    insert transfer
~~~

không an toàn nếu hai request cùng đọc “chưa tồn tại” rồi cùng thực hiện. Unique index/transaction/invariant phải được thiết kế để race được từ chối hoặc xử lý đúng.

### 15.4. Một requestId phải gắn với một ý định bất biến

Nếu REQ-001 ban đầu:

~~~json
{
  "from": "ACC-A",
  "to": "ACC-B",
  "amountCents": 20000
}
~~~

thì request sau:

~~~json
{
  "from": "ACC-A",
  "to": "ACC-C",
  "amountCents": 50000
}
~~~

không được coi là “cùng request đã xử lý” chỉ vì requestId giống nhau. Cần trả conflict cho **ID bị sử dụng lại với payload khác**.

### 15.5. Không sinh requestId mới cho mỗi retry

Nếu client hoặc server tạo ID ngẫu nhiên mới khi retry:

~~~text
Request lần đầu: REQ-001
Retry lần sau:   REQ-002
~~~

unique index không thể nhận ra hai request đại diện cho cùng một ý định. Business requestId cần được bảo toàn xuyên retry.

## 16. Reconciliation khi commit vẫn UNKNOWN sau retry budget

Một ứng dụng tài chính nghiêm túc không thể chỉ có kết quả **SUCCESS** hoặc **FAILED**. Có thể cần thêm:

~~~text
PENDING
   |
   +-- COMMITTED
   |
   +-- NOT_APPLIED / FAILED được xác minh
   |
   +-- IN_DOUBT (cần đối soát)
~~~

### 16.1. Điều gì xảy ra sau UCTR?

Khi commit bị unknown và các lần retry commit đã vượt deadline:

1. Không tự trả **"transaction đã rollback"**.
2. Không tự chạy transaction mới với business requestId mới.
3. Ghi log correlation/request ID và trạng thái **unknown** ở tầng workflow có cơ chế ghi an toàn.
4. Trả response cho client theo contract, ví dụ **202 Accepted** cùng status endpoint nếu hệ thống hỗ trợ.
5. Worker đối soát sau khi database phục hồi.

### 16.2. Kiểm tra transfer record

Nếu transfer record được insert **cùng transaction với debit/credit**:

~~~javascript
db.transfers.findOne({
  requestId: "REQ-001"
});
~~~

Khi document đã majority committed và payload khớp, điều này là bằng chứng quan trọng rằng **transfer transaction đã commit**, vì record nằm trong cùng transaction với cập nhật số dư.

**Không nên chỉ đọc local từ một secondary lag** rồi kết luận record không tồn tại. Chọn read concern/routing phù hợp cho reconciliation.

### 16.3. Không thấy record chưa đủ kết luận chắc chắn chưa commit

Nếu một read không tìm thấy transfer sau khi client mất commit response, có thể:

- Transaction thực sự chưa commit.
- Transaction đang commit hoặc outcome chưa được quan sát.
- Read đang nhìn snapshot cũ/secondary lag.
- Hệ thống chưa phục hồi đủ để đối soát.

Vì vậy thiếu record tại một thời điểm **không tự động cho phép chạy lại nghiệp vụ với ID mới**. Cần policy xác nhận outcome cuối cùng hoặc một cơ chế idempotent replay với **cùng requestId** và unique constraint.

### 16.4. Không dùng compensating transaction khi chưa biết outcome

Nếu không rõ transfer đã commit hay chưa mà lập tức gửi transfer ngược lại:

~~~text
TX-001 unknown
  |
  v
Gửi TX-002 đảo chiều
~~~

thì có thể tạo sai số dư nếu TX-001 thực sự chưa commit. Compensation thuộc workflow **saga/đối soát** cần biết trạng thái và mã nghiệp vụ, không phải cách mặc định xử lý UCTR.

### 16.5. Một status endpoint hữu ích

Ví dụ:

~~~http
GET /transfers/requests/REQ-001
~~~

Response có thể là:

~~~json
{
  "requestId": "REQ-001",
  "status": "IN_DOUBT",
  "message": "Commit is being verified"
}
~~~

Sau khi đối soát:

~~~json
{
  "requestId": "REQ-001",
  "status": "COMMITTED",
  "transferId": "TX-REQ-001"
}
~~~

Không nhất thiết phải dùng đúng những HTTP codes hoặc field names trên; quan trọng là **không đánh đồng unknown với failed**.

## 17. Transaction và write concern: durability của commit

### 17.1. Write concern đặt ở transaction level

~~~java
TransactionOptions options = TransactionOptions.builder()
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();
~~~

Write concern được áp dụng ở transaction commit theo semantics MongoDB. **Không đặt write concern riêng trên từng write operation bên trong transaction**; MongoDB không cho phép dùng per-operation write concern như vậy.

### 17.2. w:1 tại commit có hạn chế

Nếu transaction commit với **w:1**, client có thể nhận acknowledgement trước khi transaction được majority committed. Trong tình huống failover, transaction có thể rollback theo các điều kiện của replica set.

Khi nghiệp vụ cần durability mạnh, nên dùng **w:"majority"** phù hợp với topology và journaling configuration.

### 17.3. Commit được retry có thể dùng majority

MongoDB documentation nêu driver có thể áp dụng **w:"majority" khi retry commitTransaction**, kể cả nếu transaction ban đầu có write concern khác. Đây là một phần semantics của retry commit, không phải lý do bỏ qua việc cấu hình durability ban đầu.

### 17.4. wtimeout không chứng minh rollback

Nếu commit báo lỗi liên quan write concern timeout, server có thể đã áp dụng quyết định commit mà chưa đạt acknowledgement mong muốn trước deadline. Phân loại theo **label và context**, không đơn giản trả “transaction fail” rồi tạo transaction mới.

### 17.5. Read concern của transaction

Read concern thường dùng:

- **snapshot** cho consistent point-in-time read trong transaction.
- **majority** khi yêu cầu majority-committed data theo semantics liên quan commit.
- **local** trong những tình huống chấp nhận bảo đảm yếu hơn.

Trong transaction, write concern được thiết lập ở transaction level và commit. Để có majority-committed snapshot theo bảo đảm tài liệu, kết hợp **readConcern snapshot** với **writeConcern majority khi commit**.

Không đặt read concern **linearizable** hoặc **available** trong multi-document transaction.

## 18. Hiệu năng và giới hạn transaction

### 18.1. Transaction không nên chứa quá nhiều công việc

Các operations dài làm tăng rủi ro:

- Transaction lifetime exceeded.
- WiredTiger cache pressure.
- Write conflicts do nhiều document bị giữ lâu.
- Snapshot history pressure.
- Lock acquisition timeout.
- Chunk migration/metadata interaction trên sharded cluster.

Mục tiêu là **transaction ngắn và đúng business atomic unit**.

### 18.2. Thiết kế thay vì tăng retry vô hạn

Giả sử một transaction xử lý 50.000 line items và gặp **TransactionTooLargeForCache**. Chạy lại nguyên khối 100 lần không cải thiện nguyên nhân.

Cân nhắc:

1. Gộp dữ liệu phù hợp vào một document để tận dụng single-document atomicity.
2. Phân chia batch thành đơn vị nhỏ hơn nếu domain cho phép.
3. Ghi checkpoint và thiết kế workflow có thể phục hồi.
4. Cải thiện index/queries để transaction ít đọc/giữ trạng thái hơn.
5. Sử dụng saga/outbox khi nghiệp vụ trải dài nhiều hệ thống.

### 18.3. Giới hạn 16 MiB

MongoDB có giới hạn kích thước **một BSON document 16 MiB**. Với transaction, các thao tác có thể tạo nhiều oplog entries thay vì bị giới hạn tổng cả transaction vào 16 MiB như một oplog entry duy nhất, nhưng **mỗi entry/document vẫn có giới hạn riêng**.

Không coi transaction là một cách ghi document tùy ý lớn hơn giới hạn BSON.

### 18.4. Parallel operations trong một transaction

Java Sync Driver không hỗ trợ thực thi song song các operations trong cùng transaction. Không dùng **parallelStream()**, **CompletableFuture.allOf()** hoặc chia một ClientSession cho nhiều threads thực thi lệnh cùng lúc.

### 18.5. Read set và stale reads

Một transaction với snapshot read concern có thể đọc một version đã cố định trong lúc transaction khác commit state mới. Đọc snapshot nhất quán **không có nghĩa nhìn thấy tất cả writes mới nhất**.

Khi business invariant phụ thuộc vào dữ liệu đang thay đổi liên tục, cần conditional writes/guard documents hoặc protocol phù hợp. Không dùng snapshot read để thay thế mọi cơ chế concurrency control.

## 19. Observability: log gì khi transaction retry?

Một lần retry không phải một sự kiện vô nghĩa. Trong hệ thống chịu tải, metrics giúp phân biệt lỗi transient bình thường với hot documents, failover hoặc cấu hình sai.

### 19.1. Trường log nên có

| Field | Ý nghĩa |
|---|---|
| **businessRequestId** | ID ổn định xuyên các retries của một nghiệp vụ. |
| **transactionAttempt** | Attempt số mấy của toàn body. |
| **commitAttempt** | Attempt số mấy của commit. |
| **phase** | start/body/commit/abort/reconcile. |
| **errorLabels** | TTE, UCTR hoặc labels khác. |
| **errorCode/codeName** | Thông tin bổ sung từ driver/server. |
| **elapsedMs** | Thời gian đã sử dụng trong request/transaction. |
| **finalOutcome** | COMMITTED, ABORTED, IN_DOUBT, FAILED_VALIDATION... |
| **clusterTopology** | Replica set/sharded cluster và bối cảnh node khi phù hợp. |
| **correlationId** | Liên kết với tracing HTTP/message queue. |

Đừng ghi raw bank account details, personal information, tokens hay toàn bộ payload nhạy cảm vào log.

### 19.2. Metrics có ích

- **transaction_body_retry_total**
- **transaction_commit_retry_total**
- **transaction_transient_error_total**
- **transaction_unknown_commit_total**
- **transaction_in_doubt_total**
- **transaction_outcome_reconciliation_latency**
- **transaction_duration_p95/p99**
- **transaction_abort_total**
- **transaction_write_conflict_total**
- **transaction_cache_errors_total**
- **transaction_duplicate_request_total**

Các tên trên là gợi ý custom application metrics, không phải tên metric mặc định bắt buộc của MongoDB.

### 19.3. Theo dõi MongoDB server

Trong môi trường có quyền truy cập phù hợp:

~~~javascript
db.serverStatus().transactions;
~~~

Response có thể cung cấp các chỉ số liên quan đến số transactions current/committed/aborted tùy server version. Cần xem tài liệu chính xác cho version và quan sát replication lag, primary elections, cache, locks và latency.

### 19.4. Cảnh báo vận hành

Ví dụ chính sách:

~~~text
Nếu UnknownTransactionCommitResult tăng đột biến:
  Kiểm tra network, primary elections, write concern latency.

Nếu TransientTransactionError tăng đột biến:
  Kiểm tra write conflicts, hot documents, transaction duration.

Nếu TransactionTooLargeForCache tăng:
  Kiểm tra thiết kế transaction và WiredTiger cache pressure.

Nếu IN_DOUBT tích tụ:
  Kiểm tra reconciliation workers và trạng thái replica set.
~~~

Không nên tự nâng retries lên vô hạn chỉ để làm giảm số lỗi hiển thị trên dashboard.

## 20. Kiểm thử lỗi giao dịch một cách có kiểm soát

### 20.1. Kiểm thử không chỉ là một transaction thành công

Một unit/integration test gọi transfer một lần rồi thấy hai số dư đúng là chưa đủ để chứng minh error handling.

Ít nhất cần kiểm tra:

1. Body thành công và commit thành công.
2. Body gặp **TransientTransactionError** rồi attempt sau thành công.
3. Commit gặp **UnknownTransactionCommitResult** rồi retry commit thành công.
4. Commit gặp UCTR liên tiếp đến hết budget.
5. Body gặp **DuplicateKey** không được retry vô hạn.
6. Business precondition **insufficient funds** không bị biến thành transient retry.
7. Một requestId được gửi lại sau unknown outcome không bị chuyển tiền hai lần.
8. Callback chạy lại không phát thêm email/charge ngoài transaction.
9. Transaction quá lớn bị từ chối mà không retry lặp cùng khối lượng.
10. Process crash sau commit nhưng trước external publish vẫn có outbox event để xử lý.

### 20.2. Mock trạng thái ở tầng business

Không cần gây mất mạng thật để unit test state machine. Có thể thiết kế một abstraction cho:

~~~text
TransactionBodyExecutor
CommitExecutor
TransactionErrorClassifier
RetryBudget
OutcomeReconciler
~~~

Sau đó inject các kết quả lần lượt:

~~~text
Scenario A:
  executeBody attempt 1 -> TTE
  executeBody attempt 2 -> success
  commit attempt 2      -> success

Assert:
  bodyExecutionCount = 2
  commitExecutionCount = 1
~~~

~~~text
Scenario B:
  executeBody attempt 1 -> success
  commit attempt 1      -> UCTR
  commit attempt 2      -> UCTR
  commit attempt 3      -> success

Assert:
  bodyExecutionCount = 1
  commitExecutionCount = 3
~~~

~~~text
Scenario C:
  executeBody attempt 1 -> success
  commit -> UCTR đến hết retry budget

Assert:
  outcome = IN_DOUBT
  bodyExecutionCount = 1
  Không tự gửi lại payment
~~~

Đây là các assertions quan trọng nhất của bài: **TTE chạy lại body**, còn **UCTR không chạy lại body**.

### 20.3. Integration test với hai transactions cạnh tranh

Trên một replica set test:

1. Tạo account có balance/version cố định.
2. Mở **hai sessions riêng**.
3. Bắt đầu hai transactions.
4. Cho cả hai cập nhật cùng document trong tình huống cạnh tranh có kiểm soát.
5. Quan sát một transaction có thể gặp write conflict/abort và error label tương ứng.
6. Để retry toàn body khi lỗi mang TTE.
7. Kiểm tra invariant balance sau các kết quả cuối cùng.

Kết quả lỗi cụ thể có thể phụ thuộc timing/locking/server version, nên test cần có cơ chế đồng bộ hai threads hoặc fault injection thay vì tin một race tự nhiên sẽ xảy ra đúng mỗi lần.

### 20.4. Failover/network fault trong môi trường thử nghiệm

Có thể dùng chaos engineering hoặc test harness kiểm soát:

- Primary stepdown.
- Network partition ngắn.
- Độ trễ hoặc lỗi lúc commit response.
- Timeout khi commit write concern chưa đáp ứng.

Một số server/test deployments hỗ trợ **failCommand failpoint** và các failpoints khác cho việc mô phỏng lỗi; tuy nhiên availability và quyền sử dụng phụ thuộc bản MongoDB/Atlas.

**Không bật failpoints hoặc chủ động step down production primary chỉ để thử bài học.** Chỉ thao tác trên môi trường test được phép và có kịch bản rollback cấu hình.

### 20.5. Kiểm thử tính đúng sau unknown commit

Giả lập:

~~~text
Server commit transfer REQ-001 thành công
Network mất response
Client nhìn thấy UCTR
~~~

Test phải bảo đảm:

- Service **không** chạy một transaction debit/credit mới.
- Service **thử lại commit** khi session còn thích hợp.
- Nếu chưa thể xác minh, status thành **IN_DOUBT**.
- Reconciliation dùng requestId và dữ liệu majority committed để xác định kết quả.
- Khi client gửi lại requestId, không tạo duplicate transfer.

Đừng chỉ assert số lần exception được ném; cần kiểm tra **tác động cuối cùng lên documents**.

## 21. Checklist thiết kế an toàn theo từng pha

### 21.1. Trước khi bắt đầu transaction

- Xác thực người gọi, tenant và quyền truy cập.
- Validate lượng tiền, ID, currency, trạng thái nghiệp vụ.
- Đặt **business requestId** ổn định xuyên retries.
- Bảo đảm indexes/collections cần thiết đã tồn tại nếu transaction không được phép tạo.
- Chọn write concern, read concern và timeout phù hợp.
- Đặt giới hạn duration/budget của request.

### 21.2. Trong transaction body

- Mọi MongoDB operation dùng **cùng ClientSession**.
- Kiểm tra precondition trên dữ liệu mới ở **mỗi attempt**.
- Không sử dụng side effects ngoài database trực tiếp.
- Không chạy operations song song trong cùng session.
- Khi có TTE, abort/end attempt và thử lại toàn body trong transaction mới.
- Khi gặp lỗi không retryable, dừng và truyền nguyên nhân phù hợp.

### 21.3. Trong commit

- Không gọi commit nếu transaction body đã thất bại.
- Khi có UCTR, retry **commit của cùng transaction**.
- Không bắt đầu body mới chỉ vì commit response bị mất.
- Chú ý writeConcern majority, max commit time và deadline.
- Nếu không thể xác nhận, bảo tồn trạng thái **IN_DOUBT** để đối soát.

### 21.4. Sau commit

- Chỉ công bố **COMMITTED** khi có bằng chứng phù hợp.
- Phát external effects qua outbox hoặc giao thức idempotent.
- Không trả success cho payload dùng lại requestId nhưng nội dung khác.
- Ghi metrics/trace theo requestId và attempts, không lộ secrets.
- Có một workflow reconciliation chạy được khi API client đã ngắt kết nối.

## 22. Mapping kết quả transaction ra API

Một API thường cần nhiều trạng thái hơn hai giá trị boolean.

| Kết quả | HTTP gợi ý | Ý nghĩa |
|---|---|---|
| **COMMITTED** | 200/201/204 | Giao dịch đã được xác nhận. |
| **INVALID_REQUEST** | 400/422 | Payload không hợp lệ, không retry cùng payload. |
| **BUSINESS_CONFLICT** | 409 | Số dư không đủ, trạng thái không phù hợp hoặc requestId reuse conflict. |
| **RETRY_EXHAUSTED** | 503/500 tùy lỗi | Đã thử các lỗi transient đúng cách nhưng chưa thành công. |
| **IN_DOUBT** | 202 hoặc response domain-specific | Commit outcome chưa rõ, cần tra cứu status. |
| **UNAUTHORIZED/FORBIDDEN** | 401/403 | Vấn đề quyền truy cập; không được tự retry để vượt quyền. |

HTTP codes là gợi ý; thiết kế API có thể khác. Điều quan trọng nhất là **không báo chắc chắn thất bại khi commit có thể đã thành công**.

### 22.1. Client retry policy

Nếu server trả **IN_DOUBT**, client nên:

1. Giữ nguyên requestId.
2. Gọi status endpoint hoặc đợi notification.
3. Không tự gửi một transfer mới với ID khác.
4. Khi cần retry HTTP do network, dùng cùng idempotency key theo protocol được server công bố.

### 22.2. Timeout phía HTTP khác timeout phía MongoDB

API gateway có thể đóng kết nối sau 10 giây, nhưng MongoDB operation có thể vẫn đang chạy. Không được suy “HTTP 504 = transaction đã abort” nếu server chưa xác nhận điều đó.

Thiết kế cancellation, transaction deadline và reconciliation sao cho hệ thống có thể phục hồi khi caller không còn chờ.

## 23. Những lỗi tư duy thường gặp

### 23.1. “TTE là retry operation vừa lỗi”

**Sai.** Khi operation trong transaction gặp **TransientTransactionError**, thử lại **whole transaction** trên một attempt mới; không chỉ gọi lại một câu update.

### 23.2. “UCTR nghĩa là commit failed”

**Sai.** Kết quả commit **không xác định**, có thể đã thành công.

### 23.3. “Sau UCTR chỉ cần gọi lại business service”

**Nguy hiểm.** Business service có thể khởi tạo một transaction mới, dẫn đến double execution. Retry **same commit** khi session còn phù hợp hoặc đối soát outcome.

### 23.4. “Driver retryWrites=true tự retry mọi operation trong transaction”

**Sai.** Individual writes trong transaction không được retry riêng như standalone retryable writes. Callback API xử lý retry ở mức transaction; commit có retry semantics riêng.

### 23.5. “Spring @Transactional luôn tự retry giống withTransaction”

**Sai.** Spring transaction boundary không đồng nghĩa nó tự cài cùng error-label retry loop với Java Driver callback API.

### 23.6. “@Retryable cho mọi MongoException là an toàn”

**Sai.** Nếu exception phát sinh từ unknown commit, retry toàn service có thể tạo nghiệp vụ lặp. Cần phân biệt phase/error label và transaction boundary.

### 23.7. “DuplicateKey có thể retry đến khi thành công”

**Sai.** Unique constraint không biến mất chỉ vì lặp code. Với requestId trùng, cần đối chiếu request trước; với conflict dữ liệu thật, phải sửa dữ liệu.

### 23.8. “Abort sau unknown commit sẽ hoàn tác”

**Sai.** Abort không undo một transaction đã commit; nếu outcome chưa rõ, không dùng abort làm bằng chứng thất bại.

### 23.9. “Đọc không thấy record thì chắc chắn commit không xảy ra”

**Sai.** Read có thể stale hoặc commit đang ở trạng thái chưa quan sát được. Reconciliation phải có consistency/routing và retry policy phù hợp.

### 23.10. “Unique requestId tự tạo exactly-once cho email/Kafka”

**Sai.** Unique index chỉ là một thành phần. External side effects cần idempotency/outbox và quy tắc xử lý trùng riêng.

### 23.11. “Transaction có thể giữ vô hạn”

**Sai.** Transaction lifetime, cache, locks và snapshot history có giới hạn. Giao dịch cần ngắn.

### 23.12. “Lỗi thiếu tiền nên retry transaction vài chục lần”

**Sai.** Insufficient funds là business precondition failure, trừ khi có trạng thái mới hợp lệ hoặc request mới; retry y nguyên gây tải và không tạo tiền.

### 23.13. “Nếu callback chạy hai lần thì MongoDB đã trừ tiền hai lần”

Không nhất thiết. Một attempt bị abort sẽ không có các writes chưa commit hiển thị cuối cùng. Nhưng **external side effects** bên trong callback có thể thực sự lặp, nên phải tách chúng ra.

### 23.14. “Transaction commit thành công với w:1 không thể rollback”

Không đúng trong một số failovers. Khi cần majority durability, cấu hình commit write concern majority phù hợp.

### 23.15. “Mọi WriteConflict luôn có TTE”

Không được suy từ tên lỗi. Cần xem error labels và phase/driver/server version.

### 23.16. “Nếu retry budget hết thì cứ trả 500”

Không đủ. Cần phân biệt **retry-exhausted transient body errors** và **commit outcome unknown**; trường hợp sau thường cần trạng thái IN_DOUBT/reconciliation.

## 24. Bài thực hành

### Bài 1 — Xác định retry đúng

Một transaction gồm ba lệnh:

~~~text
1. debit ACC-A
2. credit ACC-B
3. insert transfer
~~~

Bước 2 gặp TransientTransactionError. Hãy viết sơ đồ restart và giải thích vì sao phải chạy lại bước 1 trong transaction mới.

### Bài 2 — Lỗi commit không xác định

Tất cả body operations thành công. Client gửi commit nhưng bị mất response và nhận UnknownTransactionCommitResult.

Yêu cầu:

1. Liệt kê hai trạng thái server có thể đang ở.
2. Chỉ ra lệnh cần retry.
3. Giải thích vì sao không mở transaction mới chạy lại debit/credit.

### Bài 3 — Cây quyết định

Thiết kế hàm nhận **phase**, **error labels** và **retry budget** để trả một trong các quyết định:

~~~text
RETRY_WHOLE_TRANSACTION
RETRY_SAME_COMMIT
FAIL_NON_RETRYABLE
IN_DOUBT
~~~

### Bài 4 — Java Driver withTransaction

Viết Java code dùng **ClientSession.withTransaction** cho ba thao tác transfer trên cùng session. Bảo đảm:

- readConcern SNAPSHOT;
- writeConcern MAJORITY;
- tất cả collection operations nhận session.

### Bài 5 — Phát hiện thiếu session

Cho đoạn code:

~~~java
session.withTransaction(() -> {
    accounts.updateOne(
            Filters.eq("_id", "ACC-A"),
            Updates.inc("balanceCents", -20000L)
    );
    return null;
});
~~~

Tìm lỗi và sửa bằng overload nhận **ClientSession**.

### Bài 6 — Spring Retry boundary

Một service dùng đồng thời **@Retryable** và **@Transactional**. Giải thích vì sao cần kiểm tra thứ tự interceptors để mỗi retry TTE nhận transaction mới.

### Bài 7 — Không retry service khi commit unknown

Đề xuất cách tách code retry commit trong **MongoTransactionManager#doCommit** hoặc một custom transaction layer, thay vì blanket retry toàn method.

### Bài 8 — Duplicate requestId

Hai HTTP requests cùng dùng REQ-001 và cùng payload. Hãy thiết kế:

- Unique index;
- business request fingerprint;
- xử lý DuplicateKey;
- reconciliation khi kết quả commit của request đầu unknown.

### Bài 9 — Idempotency key reuse conflict

Client gửi REQ-001 lần thứ hai nhưng thay **toAccount** và **amountCents**. API phải trả gì và vì sao không được coi là same request?

### Bài 10 — Transactional outbox

Thêm một outbox event vào transaction transfer và thiết kế worker publish. Mô tả tình huống worker publish xong nhưng crash trước khi mark dispatched; consumer xử lý lặp như thế nào?

### Bài 11 — Retry budget

Thiết kế maxBodyAttempts, maxCommitAttempts, deadline và backoff cho một API có thời gian đáp ứng giới hạn. Phân biệt hậu quả khi hết body budget và hết commit budget.

### Bài 12 — TransactionTooLargeForCache

Một transaction ghi hàng chục nghìn documents và gặp TransactionTooLargeForCache. Giải thích vì sao retry cùng workload không phải giải pháp tốt và đề xuất ít nhất ba cải tiến thiết kế.

### Bài 13 — Integration test

Viết test plan hai sessions cùng update một account. Dự kiến có thể xuất hiện WriteConflict/TTE; mô tả cách đồng bộ threads và assert invariant sau retry.

### Bài 14 — Failover commit

Một test replica set giả lập mất response của commit. Assert:

~~~text
bodyExecutionCount = 1
commitExecutionCount >= 2
~~~

khi UCTR và commit retry thành công. Vì sao không nên chỉ test số lỗi trả ra?

### Bài 15 — Mapping kết quả API

Thiết kế endpoint **GET /transfers/requests/REQ-001** cho trường hợp IN_DOUBT. Nêu cách client gọi lại mà không tạo nghiệp vụ mới.

### Bài 16 — Metrics

Chọn năm metrics có thể giúp phát hiện primary elections, contention và commit outcome unknown. Mô tả alert policy không gây retry storm.

## 25. Câu hỏi ôn tập

1. TransientTransactionError là error code hay error label?
2. Vì sao TTE yêu cầu retry toàn transaction chứ không retry riêng câu lệnh?
3. UnknownTransactionCommitResult có nghĩa commit thất bại chắc chắn không?
4. Khi nhận UCTR, nên retry body hay commit?
5. Khi nào cần giữ trạng thái IN_DOUBT?
6. Vì sao abort sau UCTR không phải thao tác rollback chắc chắn?
7. Java Sync Driver withTransaction xử lý TTE và UCTR thế nào?
8. Core API khác Callback API ở trách nhiệm retry ra sao?
9. Individual writes trong transaction có được retry riêng nhờ retryWrites=true không?
10. Vì sao method Java Driver trong transaction phải truyền cùng ClientSession?
11. Spring @Transactional có tự cài retry semantics như withTransaction không?
12. @Retryable có thể gây nguy hiểm ở commit phase như thế nào?
13. Tại sao side effect ngoài DB không được đặt trực tiếp trong callback có thể chạy lại?
14. Transactional outbox giải quyết khoảng trống nào giữa commit và publish?
15. Vì sao outbox consumer vẫn cần idempotency?
16. DuplicateKey trên requestId nên được xử lý thế nào?
17. Tại sao cùng requestId nhưng payload khác phải trả conflict?
18. TransactionTooLargeForCache nên được xử lý bằng retry hay thay đổi thiết kế?
19. transactionLifetimeLimitSeconds ảnh hưởng retry policy ra sao?
20. Vì sao cần write concern majority khi muốn durability của commit?
21. Khi commit response bị mất, có thể dựa vào HTTP timeout để khẳng định rollback không?
22. Khi nào reconciler có thể xác nhận transfer đã commit dựa trên majority-committed record?
23. Vì sao read không thấy transfer record chưa đủ kết luận chưa commit?
24. Những metrics nào giúp phân biệt lỗi transient bình thường và lỗi cấu hình?
25. Test nào chứng minh UCTR retry commit nhưng không chạy lại body?

## 26. Tổng kết: nhớ đúng hai loại retry

Nội dung cốt lõi của bài là **hai lỗi có ý nghĩa phục hồi khác nhau**:

~~~text
TransientTransactionError
  -> Lỗi transaction tạm thời trong body.
  -> Hủy attempt cũ nếu cần.
  -> Bắt đầu transaction mới.
  -> Chạy lại toàn bộ body và business checks.

UnknownTransactionCommitResult
  -> Không biết commit của transaction hiện tại đã thành công chưa.
  -> Thử lại commit của cùng transaction/session.
  -> KHÔNG chạy lại body chỉ vì mất response commit.
  -> Nếu không thể xác nhận: IN_DOUBT và đối soát.
~~~

Những nguyên tắc production quan trọng:

1. **Dùng error labels và phase**, không parse message hoặc retry mọi exception.
2. **Callback API** của MongoDB Driver tích hợp retry TTE/UCTR; **Core API** yêu cầu logic rõ ràng từ ứng dụng.
3. **Spring @Transactional** không tự tương đương driver withTransaction; cần thiết kế đúng transaction/retry boundaries.
4. **Retry có budget, deadline và telemetry**; lỗi validation/duplicate key/tài nguyên không tự khỏi khi retry.
5. **Business requestId cố định và unique constraint** giúp nhận diện request lặp, nhưng cần reconciliation và payload matching.
6. **External side effects** phải idempotent hoặc đi qua outbox/saga, không đặt trực tiếp trong callback có thể re-execute.
7. **Commit outcome unknown khác thất bại chắc chắn**; API cần trạng thái chờ đối soát thay vì báo lỗi sai.
8. **Transaction phải ngắn và đúng phạm vi**; kiểm thử failover và contention trên replica set/sharded cluster phù hợp.

### Tài liệu MongoDB và Spring Data chính thức

- [MongoDB — Handle Transactions in Applications with the Drivers API](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — Callback API, Core API, TTE và UCTR.
- [MongoDB — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — atomicity, write concern và các giới hạn transaction.
- [MongoDB — Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — lifetime, cache, locks, conflicts và sharding.
- [MongoDB — commitTransaction Command](https://www.mongodb.com/docs/manual/reference/command/commitTransaction/) — semantics commit và write concern.
- [MongoDB — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — phân biệt retryable writes với transaction semantics.
- [MongoDB — Java Sync Driver Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — ClientSession, withTransaction và TransactionOptions.
- [MongoDB — Read/Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — w:majority và durability.
- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — MongoTransactionManager, @Transactional và hướng dẫn retry.

Khi MongoDB báo lỗi giao dịch, hãy hỏi **“lỗi xảy ra trước commit hay ngay lúc commit?”**. Nếu body gặp **TransientTransactionError**, thử lại **toàn transaction**. Nếu commit gặp **UnknownTransactionCommitResult**, thử lại **cùng commit** và giữ khả năng đối soát nếu kết quả vẫn không rõ. Phân biệt đúng hai nhánh này là nền tảng để hệ thống phục hồi từ lỗi tạm thời mà không tự tạo ra giao dịch nghiệp vụ lặp.




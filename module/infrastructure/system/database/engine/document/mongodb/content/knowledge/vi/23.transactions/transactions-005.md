# Phân biệt gửi lại toàn giao dịch với gửi lại commit trong MongoDB

## 1. Tình huống mở đầu: lỗi ở đâu thì gửi lại phần nào?

Một hệ thống ví điện tử dùng MongoDB lưu hai tài khoản và một bản ghi giao dịch. Khi người dùng chuyển 100 đơn vị tiền từ tài khoản A sang B, hệ thống muốn ba thay đổi diễn ra cùng nhau:

1. Trừ 100 khỏi số dư A.
2. Cộng 100 vào số dư B.
3. Lưu bản ghi `transferLedger` với mã yêu cầu duy nhất.

MongoDB hỗ trợ **transaction nhiều document** để các thay đổi đó được commit như một đơn vị nguyên tử. Tuy nhiên, transaction không làm mạng trở nên tuyệt đối đáng tin cậy: server có thể đã commit nhưng **phản hồi commit bị mất**.

Hãy so sánh hai sự cố:

**Tình huống A — lỗi tạm thời khi transaction vẫn đang chạy:**

```text
startTransaction
      |
      v
  Trừ A
      |
      v
  Cộng B
      |
      X  WriteConflict / lỗi tạm thời;
         transaction không còn hoàn thành hợp lệ
      |
      v
  Bỏ lần thử này, bắt đầu transaction mới
  rồi thực hiện lại TOÀN BỘ logic.
```

**Tình huống B — lỗi khi chờ phản hồi của commit:**

```text
startTransaction
      |
      v
  Trừ A --> Cộng B --> Ghi ledger
      |
      v
commitTransaction  ----------------> MongoDB
                                      Có thể ĐÃ COMMIT
      X <---------------------------- Phản hồi bị mất
      |
      v
  Kết quả commit chưa rõ.
  Gửi lại COMMIT của CÙNG transaction;
  KHÔNG tự chạy lại logic chuyển tiền.
```

Điểm mấu chốt:

> **Gửi lại toàn giao dịch** là thực hiện lại các thao tác đọc/ghi trong một **lần thử transaction mới**, sau khi xác định lần thử trước đã thất bại/không thể commit và lỗi thuộc nhóm có thể thử lại.

> **Gửi lại commit** là yêu cầu MongoDB **xác nhận/hoàn tất commit của chính transaction hiện tại**, khi kết quả commit chưa xác định. Các thao tác đọc/ghi trong transaction **không được chạy lại** ở bước này.

Nhầm hai hành động sẽ dẫn tới nguy cơ **chuyển tiền hai lần, tạo hai đơn hàng, gửi hai thông báo hoặc ghi hai lần dữ liệu nghiệp vụ**, đặc biệt khi ứng dụng tự retry ngoài cơ chế của driver.

## 2. Mục tiêu bài học

Sau khi học, bạn có thể:

- Phân biệt **transaction body**, **commitTransaction** và **retry của một yêu cầu nghiệp vụ**.
- Nhận diện ý nghĩa của error labels **`TransientTransactionError`** và **`UnknownTransactionCommitResult`**.
- Biết khi nào cần **chạy lại cả transaction** và khi nào phải **retry commit trên cùng session/transaction identity**.
- Giải thích vì sao **mất xác nhận commit không phải bằng chứng rollback**.
- Sử dụng callback transaction như **`withTransaction()`** của MongoDB driver đúng kỳ vọng.
- Thiết kế **request ID ổn định**, unique index và bước đối soát để tránh tác động trùng khi một API được gọi lại.
- Xử lý ngoại lệ không thể tự động retry và không kéo dài vòng lặp retry vô hạn.

Phạm vi tập trung vào **MongoDB transactions** trong chương *Giao dịch*, không phải mọi lệnh ghi đơn document. Retryable writes của những lệnh riêng lẻ có cơ chế liên quan nhưng **không thay thế** transaction retry.

## 3. Ba tầng gửi lại cần phân biệt

Trong một ứng dụng thực tế có ít nhất ba mức “retry” dễ bị gọi chung một tên:

| Tầng | Đơn vị được gửi lại | Ví dụ | Điều kiện an toàn |
|---|---|---|---|
| **Retry commit** | `commitTransaction` của **cùng transaction** | Response của commit bị mất | Giữ đúng session/transaction identity; dùng protocol/driver |
| **Retry transaction** | Toàn bộ các thao tác bên trong transaction, trong **lần thử mới** | Transaction bị hủy do lỗi tạm thời có nhãn thích hợp | Chỉ khi lỗi cho biết có thể chạy lại transaction; body không có side effect ngoài kiểm soát |
| **Retry nghiệp vụ/API** | Một lệnh từ client như `POST /transfers` | Gateway trả 504, người dùng thử lại | Dùng **idempotency key** và đối soát; không tự giả định transaction trước chưa commit |

Hai tầng đầu thường do **MongoDB driver hoặc mã điều phối transaction** xử lý. Tầng thứ ba thuộc **thiết kế nghiệp vụ của ứng dụng**, không thể chỉ dựa vào error labels trong một kết nối.

### 3.1. Một API có thể được gọi hai lần dù transaction đầu đã thành công

```text
Mobile App
   |
   | POST /transfers { requestId: "TR-001", amount: 100 }
   v
Backend
   |
   | transaction + commit thành công
   v
MongoDB

Backend hoặc gateway mất kết nối khi trả HTTP response.
Mobile App không thấy kết quả, gửi lại POST.
```

Nếu backend coi request HTTP mới là một giao dịch chuyển tiền **mới hoàn toàn**, transaction MongoDB ở mỗi lần vẫn có thể **nguyên tử và thành công**, nhưng khách hàng bị trừ tiền **hai lần**.

Do đó:

- **Atomicity của transaction** ngăn tình trạng “trừ A nhưng không cộng B” trong một lần commit hợp lệ.
- **Retry protocol** xử lý sự cố tạm thời/không rõ kết quả của một lần transaction.
- **Idempotency nghiệp vụ** ngăn cùng một yêu cầu chuyển tiền được thực hiện thành **hai transaction đã commit khác nhau**.

Không được đánh đồng ba lớp bảo đảm này.

## 4. Vòng đời một transaction MongoDB

Một transaction nhiều document được quản lý thông qua **session**:

```text
Tạo session
      |
      v
startTransaction
      |
      +--> Lệnh đọc #1
      |
      +--> Lệnh ghi #1
      |
      +--> Lệnh ghi #2
      |
      v
commitTransaction
      |
      +--> Đã xác nhận commit  ---> COMMITTED
      |
      +--> Không rõ kết quả  ---> retry commit / đối soát
      |
      +--> Lỗi rõ ràng      ---> xử lý theo loại lỗi

Hoặc:

Trong body gặp lỗi làm transaction không thể hoàn tất
      |
      v
abortTransaction / transaction bị hủy
      |
      v
Nếu lỗi transient và được phép: startTransaction mới + chạy lại body
```

### 4.1. Session là gì?

`ClientSession`/logical session cho phép driver và server liên hệ các command với một ngữ cảnh session. Trong transaction, driver còn quản lý thông tin nhận diện transaction để server hiểu các lệnh thuộc cùng đơn vị giao dịch.

**Không nên tự tạo session mới** khi mục tiêu là retry commit của một transaction có kết quả chưa rõ. Làm vậy đánh mất mối liên hệ với commit cần xác nhận.

### 4.2. Transaction body gồm những gì?

Body có thể gồm nhiều lệnh có cùng session:

```javascript
// Ý tưởng nghiệp vụ, chưa phải code chạy đầy đủ.
debit(A, 100, session);
credit(B, 100, session);
insertLedger("TR-001", session);
```

Những lệnh này được thực hiện trong một transaction, nhưng chưa được công bố như dữ liệu commit trước khi commit thành công.

**Mọi thao tác MongoDB thuộc cùng transaction phải được gửi kèm đúng session**. Một lệnh vô tình chạy ngoài session có thể commit độc lập, phá vỡ atomicity mà người viết tưởng đã có.

### 4.3. Commit là bước riêng

`commitTransaction` không phải một lần gọi lại `debit()`, `credit()` hay `insertLedger()`. Nó là command yêu cầu server hoàn tất transaction đã được định danh.

Khi phải retry commit, điều cần bảo toàn là **cùng transaction identity**, chứ không phải chỉ “cùng các lệnh JavaScript/Java”.

## 5. Nhận diện lỗi: hai error labels quan trọng

MongoDB driver có thể gắn **error labels** vào ngoại lệ để hướng dẫn chiến lược retry. Hai nhãn trọng tâm là:

| Error label | Ý nghĩa định hướng | Cách xử lý thường phù hợp |
|---|---|---|
| `TransientTransactionError` | Lỗi tạm thời trong quá trình chạy transaction; lần thử đó có thể cần thực hiện lại | **Retry toàn transaction** nếu không có lý do nghiệp vụ ngăn cản |
| `UnknownTransactionCommitResult` | Client **không biết chắc** commit đã thành công hay chưa | **Retry commit của cùng transaction**; không chạy lại body |

**Không phải tên exception nào cũng mang nhãn phù hợp.** Những lỗi như duplicate key, validation error, dữ liệu nghiệp vụ không hợp lệ hoặc cấu hình hệ thống sai có thể không được giải quyết bằng retry tự động.

### 5.1. `TransientTransactionError`

Ví dụ một transaction gặp write conflict hoặc sự kiện failover trong quá trình thực thi. Driver nhận thông tin rằng lần thử hiện tại không thể hoàn tất như bình thường và có thể bắt đầu **một lần thử transaction mới**.

```text
Attempt #1
  startTransaction
  read A
  debit A
  [TransientTransactionError]
  abort/discard attempt

Attempt #2
  startTransaction
  read A lại
  debit A lại trong transaction mới
  credit B
  insert ledger
  commit
```

Điểm cốt lõi: **lần thử thứ nhất không được xem là một transaction đã commit**. Những thay đổi chưa commit của lần thử đó không trở thành một lần chuyển tiền hoàn tất. Driver/helper có thể chạy lại body trong transaction mới.

Vì transaction mới có thể đọc **trạng thái dữ liệu đã thay đổi**, body phải kiểm tra lại điều kiện nghiệp vụ, không lấy một kết quả đọc ngoài transaction làm sự thật bất biến.

### 5.2. `UnknownTransactionCommitResult`

Giả sử MongoDB đã thực hiện commit nhưng client mất phản hồi:

```text
Attempt #1
  startTransaction
  debit A
  credit B
  insert ledger
  commitTransaction  ------------> Server
                                     COMMIT thành công
  X <------------------------------ response thất lạc

Client nhận UnknownTransactionCommitResult
  |
  +--> Retry commitTransaction của Attempt #1
       KHÔNG gọi debit/credit/insertLedger lại
```

Kết quả commit có thể:

- Đã thành công, chỉ có phản hồi bị mất.
- Chưa hoàn tất hoặc chưa được xác nhận theo yêu cầu.
- Chưa thể xác định trong điều kiện mạng/failover hiện tại.

**Những khả năng đó không thể được phân biệt chỉ từ việc client không nhận response.** Vì vậy phải retry **command commit** theo protocol hoặc kết luận tạm thời là **UNKNOWN** nếu không giải quyết được trong giới hạn hợp lý.

### 5.3. Nhãn lỗi là hướng dẫn có điều kiện, không phải phép màu

Không nên viết:

```java
// SAI: mọi MongoException đều retry toàn transaction.
catch (MongoException e) {
    runBusinessTransactionAgain();
}
```

Cũng không nên viết:

```java
// SAI: mọi timeout đều có nghĩa commit thất bại chắc chắn.
catch (MongoException e) {
    return "NOT_COMMITTED";
}
```

Thay vào đó cần phân loại **lệnh đang thực hiện**, **error labels**, **trạng thái transaction**, **số lần đã thử** và **idempotency của yêu cầu nghiệp vụ**.

## 6. Khi nào gửi lại toàn giao dịch?

### 6.1. Điều kiện tư duy

Gửi lại toàn giao dịch khi có bằng chứng phù hợp rằng **lần transaction hiện tại không thể commit một cách hợp lệ** và lỗi có tính **tạm thời**, ví dụ driver nhận `TransientTransactionError` trong lúc chạy body.

Khi đó việc thực hiện lại thường gồm:

1. Kết thúc/abort lần thử cũ khi cần và còn khả thi.
2. Bắt đầu một transaction mới.
3. Đọc lại dữ liệu đầu vào trong transaction mới.
4. Thực thi lại **toàn bộ business body**.
5. Thử commit lần transaction mới.

**Không chỉ gửi lại lệnh bị lỗi cuối cùng** trong một transaction đã bị server đánh dấu aborted. Toàn bộ trạng thái đọc/ghi của lần thử cũ không còn là một ngữ cảnh commit hợp lệ.

### 6.2. Ví dụ write conflict

Hai transaction cùng sửa một document tài khoản theo các điều kiện cạnh tranh. Một transaction có thể nhận lỗi write conflict; driver có thể đánh dấu lỗi tạm thời:

```text
Transaction T1             Transaction T2
    |                           |
    | read balance              | read balance
    |                           |
    | update account A          | update account A
    |                           |
    |                           X write conflict
    | commit                    |
    |                           |
                                v
                         Retry transaction T2
                         đọc lại balance mới
```

Đây là một **mô hình có thể xảy ra**, không phải bảo đảm về thứ tự transaction nào sẽ bị lỗi trong mọi lần chạy.

T2 cần đọc lại dữ liệu trong lần thử mới; không nên giữ kết quả kiểm tra số dư của lần cũ khi dữ liệu có thể đã thay đổi bởi T1.

### 6.3. Điều gì không được lặp lại trong body?

Callback transaction có thể được driver gọi **nhiều lần**. Bởi vậy, không đặt các side effect không được rollback một cách tùy tiện trong callback:

```java
session.withTransaction(() -> {
    debitInMongoDB(session);
    creditInMongoDB(session);

    sendEmail("Transfer completed"); // Nguy hiểm nếu body bị retry.
    chargeExternalGateway();         // Càng nguy hiểm hơn.

    return null;
});
```

MongoDB transaction **không rollback email hoặc giao dịch ở cổng thanh toán bên ngoài**. Nếu body chạy lại, hai hành động đó có thể xảy ra hai lần.

Thiết kế thích hợp có thể là:

- Lưu một **outbox event** trong cùng transaction.
- Chỉ gửi side effect sau khi trạng thái commit đã được xác minh.
- Consumer của outbox sử dụng **event ID/idempotency key** để xử lý trùng.
- Hệ thống bên ngoài có idempotency key riêng nếu nó hỗ trợ.

Không chuyển mọi side effect ra sau `withTransaction()` rồi mặc định chúng exactly-once: việc ứng dụng crash sau commit, trước gửi email còn đòi hỏi outbox hoặc cách phục hồi.

### 6.4. Random ID và thời gian trong callback

Nếu callback tạo mã chuyển tiền hoặc request ID mới mỗi lần được gọi:

```java
session.withTransaction(() -> {
    String requestId = UUID.randomUUID().toString(); // Mỗi retry body khác ID.
    // ...
    return null;
});
```

thì những lần thử có thể có định danh nghiệp vụ khác nhau. Trong transaction retry thuần túy, lần cũ đã abort nên chưa hẳn gây trùng commit, nhưng **định danh nghiệp vụ không ổn định sẽ phá khả năng đối soát và chống lặp ở tầng HTTP**.

Vì vậy, nên tạo **request ID ổn định bên ngoài callback** hoặc nhận từ client trước khi bắt đầu workflow:

```java
final String requestId = incomingRequestId;

session.withTransaction(() -> {
    insertTransferLedger(session, requestId);
    debitAccount(session);
    creditAccount(session);
    return null;
});
```

Đặt thời điểm giao dịch nghiệp vụ, tỷ giá hoặc giá tham chiếu cũng cần quy tắc rõ: đọc lại trạng thái hiện hành cho mỗi lần retry, nhưng không vô tình biến cùng một yêu cầu thành một yêu cầu có thông số khác.

## 7. Khi nào chỉ gửi lại commit?

### 7.1. Vấn đề xuất hiện ở bước quyết định commit

Giả sử toàn bộ body đã chạy:

```text
debit A         OK trong transaction
credit B        OK trong transaction
insert ledger   OK trong transaction
commit          kết quả UNKNOWN
```

Nếu gọi lại debit/credit trong một transaction **mới** và lần commit đầu thực ra đã thành công, nghiệp vụ có thể được áp dụng **hai lần**.

Điều cần gửi lại là:

```text
commitTransaction của transaction ban đầu
```

Không phải:

```text
startTransaction mới
debit A
credit B
insert ledger
commit transaction mới
```

### 7.2. Vì sao commit có thể gửi lại?

MongoDB protocol và driver dùng thông tin session/transaction để nhận diện **commit của cùng một transaction**. Nhờ vậy, gửi lại commit có thể làm rõ kết quả mà **không tái thực hiện các câu lệnh nghiệp vụ**.

Điều này không đồng nghĩa client có thể bắt đầu một transaction mới với cùng nội dung rồi MongoDB sẽ tự nhận ra và bỏ qua. **Một transaction mới là một lần thực thi khác**, trừ khi lớp nghiệp vụ có cơ chế chống trùng bổ sung.

### 7.3. Không “abort để chắc chắn” sau commit unknown

Đoạn mã sau là ý tưởng sai:

```java
try {
    session.commitTransaction();
} catch (MongoException e) {
    session.abortTransaction(); // Không thể dùng để đảm bảo đã hoàn tác commit.
    throw e;
}
```

Nếu commit đã thành công, một yêu cầu abort muộn **không đảo ngược dữ liệu đã commit**. Nếu transaction vẫn chưa rõ, abort cũng không thay thế được quy trình xác minh kết quả.

**Khác biệt quan trọng:** `abortTransaction` là công cụ hủy một transaction chưa commit theo ngữ cảnh phù hợp; **không phải rollback sau commit**.

### 7.4. Retry commit phải giữ đúng identity

Trong cách quản lý thủ công, lần retry commit phải sử dụng:

- **Cùng ClientSession**.
- **Cùng transaction đang chờ kết luận**, không start transaction khác.
- **Cùng protocol commit** do MongoDB driver hỗ trợ.

Driver thường xử lý phần định danh ở tầng giao thức; ứng dụng **không nên tự xây các trường protocol** bằng tay hoặc tạo session mới chỉ để gửi lại một lệnh commit.

### 7.5. Không retry commit vô hạn

Nếu network bị cắt lâu, một loop vô hạn sẽ giữ tài nguyên và làm API không thể kết thúc:

```text
while (true) {
    try commit;
    catch any error -> retry ngay;
}
```

Đây không phải thiết kế tốt. Cần:

- **Phân loại lỗi**: chỉ retry khi kết quả commit chưa xác định và protocol cho phép.
- **Deadline tổng** hoặc giới hạn hợp lý theo driver/workflow.
- **Backoff** khi thích hợp.
- **Trạng thái UNKNOWN_OUTCOME** nếu không thể xác nhận trong thời hạn.
- **Đối soát theo business key** trước khi tái tạo nghiệp vụ.

Retry commit giúp giải quyết sự mơ hồ trong nhiều tình huống, nhưng không thể hứa rằng mọi mạng lỗi đều được khắc phục ngay.

## 8. Ma trận quyết định: retry body hay retry commit?

| Vị trí/loại lỗi | Diễn giải | Hành động phù hợp |
|---|---|---|
| Trong body, có nhãn `TransientTransactionError` | Lần transaction hiện tại không hoàn thành; có thể là lỗi tạm thời | Hủy/bỏ lần thử và **retry toàn transaction** |
| Trong body, lỗi validation/duplicate key không được xác định là transient | Có vấn đề dữ liệu/ràng buộc | **Không** retry vô hạn; xử lý nghiệp vụ |
| Trong body, lỗi không rõ và không có nhãn phù hợp | Chưa đủ điều kiện kết luận có thể retry | Phân loại theo driver/error; không tự gửi lại mù quáng |
| Commit trả thành công | Transaction đã được xác nhận commit theo yêu cầu | Kết thúc; không retry body |
| Commit có nhãn `UnknownTransactionCommitResult` | Client không biết commit đã hoàn tất chưa | **Retry commit của cùng transaction** |
| Commit vẫn unknown khi vượt deadline | Chưa chứng minh commit hay abort | Trả/ghi `UNKNOWN_OUTCOME` và **đối soát** |
| Commit lỗi chắc chắn không retryable theo protocol | Không phù hợp để thử lại commit vô hạn | Báo lỗi/đối soát theo tình huống |
| HTTP response mất sau khi driver đã trả commit success | Backend biết thành công, client chưa biết | **Retry API idempotent** bằng cùng request ID; không tạo giao dịch mới |
| Client gọi lại API sau lỗi nhưng không có business key | Không phân biệt được request cũ và mới | Thiết kế idempotency trước khi tự retry |

### 8.1. Không dựa riêng vào tên exception

Một `MongoException` có thể xuất hiện:

- Trước khi driver gửi lệnh.
- Trong transaction body.
- Ở bước commit.
- Trong lúc đọc đối soát sau commit.

Do đó, cùng một kiểu exception chưa chắc dẫn đến cùng quyết định. Phải biết **đang ở giai đoạn nào** và **error labels** nói gì.

### 8.2. Đừng suy từ lỗi network “chắc chắn chưa commit”

Nếu exception xuất hiện trong lúc commit, **mất phản hồi có thể xảy ra sau khi server đã ghi và công bố transaction**. Nhánh chính xác là “kết quả chưa biết”, không phải “đã rollback”.

## 9. Thuật toán tổng quát: hai vòng retry lồng nhau

Để hiểu cơ chế driver, hãy hình dung có hai vòng:

```text
VÒNG NGOÀI: attempt một TRANSACTION
  |
  +-- startTransaction
  |
  +-- chạy business body
  |      |
  |      +-- TransientTransactionError
  |               |
  |               +-- abort/discard attempt nếu thích hợp
  |               +-- quay lại VÒNG NGOÀI
  |
  +-- VÒNG TRONG: commitTransaction CÙNG attempt
           |
           +-- success
           |      |
           |      +-- DONE
           |
           +-- UnknownTransactionCommitResult
           |      |
           |      +-- quay lại VÒNG TRONG
           |          (không chạy body)
           |
           +-- lỗi khác
                  |
                  +-- xử lý theo phân loại thực tế
```

Đây là **mô hình thuật toán** để giải thích hai loại retry, không phải lời khuyên tự thay thế hành vi được MongoDB driver hỗ trợ bằng một loop vô hạn.

### 9.1. Pseudocode minh họa

```text
function executeTransactionWithRetry(requestId):
    repeat until transactionDeadline:
        session.startTransaction()

        try:
            runBusinessBody(session, requestId)

        catch error:
            if error has TransientTransactionError:
                abort if applicable
                continue outer loop   // THỬ LẠI TOÀN BODY

            abort if applicable
            return REJECTED_OR_FAILED(error)

        repeat until commitDeadline:
            try:
                session.commitTransaction()
                return COMMITTED

            catch error:
                if error has UnknownTransactionCommitResult:
                    continue inner loop  // CHỈ RETRY COMMIT

                return CLASSIFY_COMMIT_ERROR(error)

        return UNKNOWN_OUTCOME

    return RETRY_DEADLINE_EXCEEDED
```

Trong ứng dụng thực, driver có thể đã có logic retry tự động, còn việc abort, commit deadline và lỗi cụ thể cần tuân thủ **API/driver version**. Pseudocode không phải copy-paste runnable và cố tình không che giấu nhánh `UNKNOWN_OUTCOME`.

### 9.2. Vì sao vòng ngoài và vòng trong không được nhập làm một?

Đây là anti-pattern:

```text
repeat:
    startTransaction
    runBusinessBody
    commitTransaction
until no exception
```

Nếu lần thứ nhất đã commit nhưng phản hồi thất lạc, lần lặp thứ hai là một transaction mới. Không có đảm bảo tổng thể rằng MongoDB sẽ tự loại bỏ lần giao dịch nghiệp vụ bị trùng.

### 9.3. Không phải lỗi nào cũng được phép vào vòng retry

Nếu amount âm, thiếu quyền, thiếu unique index, dữ liệu không hợp lệ, hoặc người dùng không đủ tiền theo quy tắc nghiệp vụ, retry nguyên body 100 lần vẫn không biến request thành hợp lệ. Vòng retry phải **phân loại lỗi và có giới hạn**.

## 10. Chuẩn bị lab transaction trên replica set

Các ví dụ dùng database **`txn_retry_lab249`** trên MongoDB replica set dành cho học tập. Transaction nhiều document cần deployment hỗ trợ, chẳng hạn replica set; một standalone `mongod` thông thường không thể dùng cho bài này.

**Không chạy các lệnh mô phỏng chuyển tiền trên dữ liệu thật.** Đơn vị tiền trong ví dụ là số nguyên nhỏ để dễ quan sát.

### 10.1. Tạo dữ liệu ban đầu

Trong `mongosh`:

```javascript
const labDb = db.getSiblingDB("txn_retry_lab249");

// Sử dụng database/lab mới, không có document cùng _id.
labDb.accounts249.insertMany([
  { _id: "A", balance: 1000, currency: "UNIT" },
  { _id: "B", balance: 500, currency: "UNIT" }
]);

labDb.transferLedger249.createIndex(
  { requestId: 1 },
  { unique: true }
);
```

Ta cần bất biến:

```text
Tổng số dư A + B trước chuyển = 1500

Chuyển 100 từ A sang B:
  A: 1000 -> 900
  B:  500 -> 600
Tổng sau chuyển = 1500
Ledger có đúng 1 record cho requestId tương ứng.
```

Kiểm tra tổng số dư giúp phát hiện một số lỗi, nhưng **không đủ** để phát hiện giao dịch trùng: nếu cùng một lần chuyển 100 được thực hiện hai lần, tổng A+B vẫn bằng 1500. Vì vậy cần thêm **ledger và business ID**.

### 10.2. Chọn request ID trước khi bắt đầu

```javascript
const requestId = "TR-249-001";
```

Đây là định danh của **một ý định chuyển tiền**, không phải của một lần thử transaction. Nếu driver retry body hoặc API nhận lại cùng yêu cầu, `requestId` vẫn giữ nguyên.

### 10.3. Quy tắc viết dữ liệu trong transaction

- Dùng cùng session cho tất cả lệnh đọc/ghi cần nguyên tử.
- Kiểm tra số tiền dương và nguồn/đích hợp lệ trước khi thực thi.
- Có điều kiện `balance >= amount` khi trừ tiền.
- Kiểm tra `matchedCount` hoặc điều kiện bất biến để không commit một chuyển tiền thiếu bước.
- Ghi ledger có unique `requestId` trong cùng transaction.
- Đặt write concern ở **cấp transaction/commit**, không cố gắn write concern riêng cho từng thao tác nằm trong transaction.
- Không gọi API thanh toán bên ngoài trong transaction body.

## 11. Mongosh: transaction thủ công để hiểu vị trí commit

Đây là ví dụ **một lần thử thành công**, chưa có tự retry. Nó giúp nhìn rõ body và commit:

```javascript
const conn = db.getMongo();
const session = conn.startSession();
const txDb = session.getDatabase("txn_retry_lab249");
const requestId = "TR-249-MANUAL-001";

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  // Ledger và hai thay đổi số dư cùng session.
  txDb.transferLedger249.insertOne({
    _id: requestId,
    requestId,
    from: "A",
    to: "B",
    amount: 100,
    currency: "UNIT"
  });

  const debit = txDb.accounts249.updateOne(
    { _id: "A", balance: { $gte: 100 } },
    { $inc: { balance: -100 } }
  );
  if (debit.matchedCount !== 1) {
    throw new Error("SOURCE_NOT_FOUND_OR_INSUFFICIENT_BALANCE");
  }

  const credit = txDb.accounts249.updateOne(
    { _id: "B" },
    { $inc: { balance: 100 } }
  );
  if (credit.matchedCount !== 1) {
    throw new Error("DESTINATION_NOT_FOUND");
  }

  session.commitTransaction();
  print("Transaction commit acknowledged");
} catch (e) {
  // Chỉ nên abort khi transaction chưa commit hoặc outcome không unknown.
  // Ví dụ lab này KHÔNG cung cấp chiến lược xử lý commit không rõ.
  print("Error: " + e.message);
  throw e;
} finally {
  session.endSession();
}
```

**Giới hạn có chủ đích của ví dụ:** đoạn mã cho thấy cấu trúc session/transaction nhưng **không phải bộ điều phối retry production**. Nếu `commitTransaction()` lỗi và kết quả commit chưa rõ, `finally` kết thúc session; lúc đó ứng dụng cần quy trình retry/đối soát khác và không thể kết luận “đã rollback”.

Không copy mẫu này rồi thêm `session.abortTransaction()` trong mọi nhánh `catch`, vì commit có thể đã thành công. Phần 9 và phần Java tiếp theo giải thích cách dùng helper đúng hơn.

### 11.1. Kiểm tra kết quả sau lần chạy thành công

```javascript
labDb.accounts249.find().sort({ _id: 1 });
labDb.transferLedger249.find({ requestId: "TR-249-MANUAL-001" });
```

Nếu chạy thành công một lần trên dữ liệu ban đầu:

```javascript
{ _id: "A", balance: 900, currency: "UNIT" }
{ _id: "B", balance: 600, currency: "UNIT" }

{
  _id: "TR-249-MANUAL-001",
  requestId: "TR-249-MANUAL-001",
  from: "A",
  to: "B",
  amount: 100,
  currency: "UNIT"
}
```

Nếu chạy những ví dụ khác trên cùng database sau đó, số dư sẽ thay đổi; không so sánh với giá trị trên mà không xác định lại trạng thái ban đầu.

### 11.2. Mongosh có thể dùng session helper

`mongosh` có API quản lý session và transaction; khi tự điều phối retry, phải duy trì session đúng cách. Trong ứng dụng thực tế, cách thường được khuyến nghị là dùng **convenient transaction API** của driver, chẳng hạn `ClientSession.withTransaction()` trong driver Java, để tận dụng logic retry được hỗ trợ và tránh sai sót trong quản lý commit.

## 12. Java Sync Driver: dùng `withTransaction()`

Trong dự án Java, MongoDB Sync Driver cung cấp convenient transaction API `ClientSession.withTransaction()`. Helper có thể **gọi lại callback body** khi gặp lỗi transaction transient, và **retry commit** khi commit có kết quả không rõ, theo cơ chế của driver.

### 12.1. Chuẩn bị transaction options

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;

TransactionOptions options = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .readPreference(ReadPreference.primary())
    .build();
```

Ý nghĩa:

- `ReadConcern.SNAPSHOT`: yêu cầu kiểu đọc snapshot phù hợp trong transaction.
- `WriteConcern.MAJORITY`: cấu hình xác nhận commit theo mức majority.
- `ReadPreference.primary()`: đọc từ primary trong transaction.

Hỗ trợ thực tế còn tùy deployment và version. Transaction không thể được dùng để biến một standalone `mongod` thành replica set.

### 12.2. Ví dụ chuyển tiền đầy đủ bằng Java

Ví dụ sử dụng các lớp `Document` và `MongoCollection` để thể hiện rõ session được truyền vào từng lệnh. Cần MongoDB Sync Driver tương thích và replica set thử nghiệm.

```java
import com.mongodb.MongoException;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public class TransferWithTransaction {

    public static void main(String[] args) {
        String uri =
            "mongodb://localhost:27117,localhost:27118,localhost:27119/" +
            "?replicaSet=rsLab&retryWrites=true";

        // Một yêu cầu chuyển tiền -> một business ID ổn định.
        final String requestId = "TR-249-JAVA-001";
        final long amount = 100L;

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(WriteConcern.MAJORITY)
            .readPreference(ReadPreference.primary())
            .build();

        try (MongoClient client = MongoClients.create(uri);
             ClientSession session = client.startSession()) {

            MongoDatabase database =
                client.getDatabase("txn_retry_lab249");
            MongoCollection<Document> accounts =
                database.getCollection("accounts249");
            MongoCollection<Document> ledger =
                database.getCollection("transferLedger249");

            String outcome = session.withTransaction(() -> {
                // Driver có thể gọi lại callback khi retry toàn transaction.
                // Không gửi email, gọi payment gateway hoặc đổi requestId ở đây.

                ledger.insertOne(session,
                    new Document("_id", requestId)
                        .append("requestId", requestId)
                        .append("from", "A")
                        .append("to", "B")
                        .append("amount", amount)
                        .append("currency", "UNIT"));

                UpdateResult debit = accounts.updateOne(
                    session,
                    new Document("_id", "A")
                        .append("balance",
                            new Document("$gte", amount)),
                    new Document("$inc",
                        new Document("balance", -amount)));

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Insufficient balance or source not found");
                }

                UpdateResult credit = accounts.updateOne(
                    session,
                    new Document("_id", "B"),
                    new Document("$inc",
                        new Document("balance", amount)));

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Destination account not found");
                }

                return "COMMITTED";
            }, options);

            System.out.println(outcome);

        } catch (MongoException e) {
            System.err.println("MongoDB transaction error: " +
                e.getMessage());

            // Nếu helper không thể kết luận, KHÔNG tự chạy lại
            // business transfer bằng requestId mới.
            // Đối soát ledger theo requestId với chính sách đọc phù hợp.
        }
    }
}
```

### 12.3. Điều kiện của ví dụ

Trước khi chạy:

- Database `txn_retry_lab249` đã có hai document `A` và `B`.
- Collection `transferLedger249` có unique index `{ requestId: 1 }`.
- Replica set `rsLab` đang hoạt động và có primary.
- URI phù hợp với host/port thực tế.
- Ví dụ dùng số nguyên đơn vị; hệ thống tiền thật cần mô hình số/decimal phù hợp.
- Không chạy cùng `requestId` như một chuyển tiền mới khi ledger đã có record từ lần trước.

### 12.4. Callback có thể chạy nhiều lần, nhưng không có nghĩa có nhiều commit

Nếu lần thử đầu gặp `TransientTransactionError` trước commit, driver có thể:

1. Bỏ/hủy lần thử đó.
2. Bắt đầu một transaction mới.
3. Chạy lại callback.
4. Commit lần thành công.

Điều đó không có nghĩa các thay đổi chưa commit từ lần đầu được “để lại” rồi cộng thêm lần hai.

Nếu commit có kết quả không rõ, helper có thể **retry commit** mà không gọi lại callback. Đây chính là sự khác biệt người dùng cần nhận diện.

### 12.5. `withTransaction()` không bảo đảm mọi yêu cầu HTTP exactly-once

Giả sử `withTransaction()` trả `"COMMITTED"`, nhưng backend chết trước khi trả response cho frontend. Frontend gửi lại cùng API và backend gọi một lần `withTransaction()` **mới**:

- Transaction mới sẽ không được tự động nhận diện là lần retry commit của transaction trước.
- Nếu ledger dùng `requestId` ổn định và unique index, lần mới có thể gặp duplicate key.
- Ứng dụng phải **đối soát ledger** và trả kết quả tương ứng, không đổi `requestId` rồi chuyển tiền tiếp.

Driver retry giải quyết lỗi trong **một lần điều phối transaction**; business idempotency giải quyết những lần gọi API **độc lập**.

## 13. Java: kiểm tra error labels khi cần tự điều phối

Khi sử dụng **core transaction API** thay vì convenient helper, Java có thể kiểm tra nhãn lỗi:

```java
catch (MongoException e) {
    if (e.hasErrorLabel("TransientTransactionError")) {
        // Ở giai đoạn chạy body:
        // Xem xét retry toàn transaction, trong lần thử mới.
    } else if (e.hasErrorLabel("UnknownTransactionCommitResult")) {
        // Ở giai đoạn commit:
        // Retry commit của cùng transaction/session.
    } else {
        // Không tự retry mù quáng.
    }
}
```

Đây là đoạn **minh họa phân loại**, không phải thuật toán runnable hoàn chỉnh. Đặc biệt:

- Không áp dụng `TransientTransactionError` trong body bằng cách chỉ gọi lại lệnh cuối cùng.
- Không xử lý `UnknownTransactionCommitResult` bằng cách khởi tạo session/transaction mới.
- Không tự xây loop vô hạn ở ngoài `withTransaction()` nếu helper đã có cơ chế retry.
- Không đồng nhất mọi lỗi network với một label; driver/server quyết định nhãn theo điều kiện cụ thể.

### 13.1. Không kiểm tra error message bằng cách tìm chuỗi

Ví dụ:

```java
if (e.getMessage().contains("timeout")) {
    retryWholeTransaction();
}
```

là cách xử lý không đáng tin cậy. Một thông điệp chứa “timeout” có thể mô tả:

- Server selection timeout.
- Network timeout khi đang chạy body.
- Write concern timeout khi commit.
- Một thao tác khác đã hoàn tất nhưng response bị mất.

Mức chắc chắn và cách retry khác nhau. Ưu tiên **error labels và giao thức driver**, đồng thời giữ business ID để đối soát khi cần.

## 14. Đối chiếu ba timeline quan trọng

### 14.1. Timeline A — transaction body gặp lỗi transient

```text
T0  Start transaction X
T1  Read balance A = 1000
T2  Debit A trong X
T3  Concurrent update gây write conflict
T4  Driver nhận TransientTransactionError
T5  X bị hủy / không commit
T6  Start transaction Y
T7  Read balance A lại
T8  Debit + credit + ledger trong Y
T9  Commit Y thành công
```

Tại T6, phải **retry toàn bộ body**, không tiếp tục dùng trạng thái transaction X.

### 14.2. Timeline B — commit có kết quả chưa rõ

```text
T0  Start transaction X
T1  Debit A trong X
T2  Credit B trong X
T3  Insert ledger trong X
T4  Client gửi commit(X)
T5  Server có thể đã commit X
T6  Response bị mất
T7  Client nhận UnknownTransactionCommitResult
T8  Client gửi lại commit(X)
T9  Server trả kết quả commit theo protocol
```

Tại T8, **không chạy lại body**. Mục tiêu là làm rõ hoặc hoàn tất commit X.

### 14.3. Timeline C — một API HTTP được gửi lại

```text
T0  Client gửi POST /transfers, requestId=TR-001
T1  Backend chạy transaction X
T2  Commit X thành công
T3  HTTP response thất lạc
T4  Client retry POST /transfers, requestId=TR-001
T5  Backend kiểm tra ledger/idempotency key
T6  Trả lại trạng thái đã xử lý; không chuyển tiền lần hai
```

Ở đây T4 là **retry ở tầng nghiệp vụ**, không phải retry commit của transaction X. Vì vậy cần **một định danh yêu cầu ổn định** được kiểm tra xuyên các lần request.

## 15. Vì sao “gửi lại body sau UnknownTransactionCommitResult” nguy hiểm?

Giả sử tài khoản ban đầu:

```javascript
{ _id: "A", balance: 1000 }
{ _id: "B", balance: 500 }
```

Transaction X chuyển 100:

```text
Sau commit X:
A = 900
B = 600
```

Client không nhận được phản hồi commit X, nên **tưởng X thất bại** và chạy một transaction Y mới với cùng hai cập nhật `$inc`:

```text
Sau commit Y:
A = 800
B = 700
```

Vẫn có:

```text
A + B = 1500
```

nhưng người dùng đã chuyển **200 thay vì 100**. Bất biến “tổng tiền trong hệ thống không đổi” không đủ phát hiện lỗi này.

### 15.1. Có unique ledger thì sao?

Nếu cả X và Y dùng **cùng `requestId`** và insert ledger trong cùng transaction trước khi sửa số dư, Y sẽ gặp xung đột duplicate key khi X đã commit. Đó là một lớp bảo vệ hữu ích.

Tuy nhiên, khi nhận duplicate key:

- **Không tự coi mọi duplicate key là thành công.**
- Đọc ledger theo `requestId`.
- Xác minh `from`, `to`, `amount`, `currency` và trạng thái.
- Nếu payload khác, trả conflict, không chuyển tiền.

Một request ID ổn định ngăn nhiều transaction commit khác nhau ghi thành **hai nghiệp vụ giống nhau**, nhưng không thay việc phân loại lỗi commit.

### 15.2. Nếu lỡ dùng request ID mới

Nếu lần retry API phát sinh `TR-002` thay cho `TR-001`, unique ledger sẽ không nhận ra đây là cùng ý định chuyển tiền. Cả X và Y đều có thể commit hợp lệ theo MongoDB nhưng **sai về nghiệp vụ**.

Vì thế, cần phân biệt:

```text
Transaction identity do driver quản lý
             +
Business requestId do ứng dụng quản lý
```

Hai định danh giải quyết **hai loại trùng lặp khác nhau**.

## 16. Khi retry toàn transaction, dữ liệu đầu vào có thể thay đổi

MongoDB transactions có các mức đọc và cơ chế kiểm soát cạnh tranh riêng. Khi retry body trong một transaction **mới**, các thao tác đọc phải được thực hiện lại.

Ví dụ:

```text
Lần thử X:
  Đọc A = 1000
  Kiểm tra có đủ 100 -> Có
  Gặp TransientTransactionError, X không commit

Trong lúc đó, một giao dịch khác chuyển 950 từ A.

Lần thử Y:
  Đọc A = 50
  Kiểm tra có đủ 100 -> Không
  Y phải từ chối theo nghiệp vụ
```

Nếu callback giữ một biến `balanceAtFirstAttempt = 1000` ở ngoài rồi dùng lại sau retry, nó có thể thực thi quyết định dựa trên dữ liệu cũ.

### 16.1. Phân biệt đầu vào ổn định và trạng thái cần đọc lại

| Loại dữ liệu | Quy tắc thông thường khi retry body |
|---|---|
| `requestId` của người dùng | **Giữ ổn định** giữa các lần thử |
| Số tiền người dùng xác nhận | **Giữ nguyên** trong cùng yêu cầu |
| Tài khoản nguồn/đích | **Giữ nguyên** trong cùng yêu cầu |
| Số dư hiện hành | **Đọc lại** trong transaction mới |
| Cờ khóa tài khoản | **Đọc lại** trong transaction mới |
| Phiên bản document | **Đọc/kiểm tra lại** theo logic optimistic concurrency |
| Thời gian nghiệp vụ có nghĩa | Quy định rõ là thời điểm yêu cầu hay thời điểm xử lý |
| Email/SMS bên ngoài | Không phát trực tiếp bên trong body có thể retry |

Sự phân biệt này giúp vừa bảo toàn ý định nghiệp vụ, vừa đưa ra quyết định trên trạng thái MongoDB hiện hành của lần thử mới.

## 17. Các lỗi không nên tự động retry toàn transaction

### 17.1. Duplicate key và unique index

Nếu unique ledger đã có `requestId` tương ứng, điều đó có thể biểu thị:

- Request trước đã commit thành công.
- Một request trùng key nhưng payload khác.
- Dữ liệu được tạo bởi một tác nhân khác.

Thử lại toàn transaction nhiều lần không làm unique constraint biến mất. Cần **đối soát** và quyết định theo nghiệp vụ.

### 17.2. Validation hoặc schema error

Một document không hợp lệ, ví dụ `amount: "abc"` khi schema yêu cầu số, cần được sửa từ nguồn. Retry cùng payload là vô ích.

### 17.3. Không đủ số dư

Nếu transaction body đọc số dư không đủ, đây là quyết định nghiệp vụ:

```java
if (debit.getMatchedCount() != 1) {
    throw new IllegalStateException("INSUFFICIENT_BALANCE");
}
```

Không nên tự động retry 50 lần hy vọng tài khoản sẽ có tiền. Nếu có cơ chế chờ nạp tiền thì đó là **workflow khác**, không phải transaction retry do lỗi transient.

### 17.4. Lỗi quyền/cấu hình

Thiếu quyền trên collection, replica set chưa được cấu hình đúng, session không hợp lệ hoặc phiên bản không hỗ trợ transaction phải được giải quyết bằng **cấu hình và vận hành**, không bằng retry vô hạn.

### 17.5. Hết deadline retry

Một transaction có thể liên tục gặp write conflict vì workload cạnh tranh quá cao. Nếu sau giới hạn hợp lý vẫn không hoàn tất, trả trạng thái thích hợp và quan sát nguyên nhân, thay vì giữ thread request mãi.

### 17.6. Hết thời hạn transaction

MongoDB có giới hạn thời gian tồn tại của transaction theo cấu hình server. Một transaction giữ quá lâu có thể bị hủy, gây tốn tài nguyên hoặc làm chậm việc xử lý xung đột. Không dùng `sleep` lâu hoặc gọi HTTP chậm trong transaction body rồi nghĩ rằng tăng số retry giải quyết tận gốc.

## 18. Transaction write concern và lỗi xác nhận commit

### 18.1. Đặt write concern ở cấp transaction

Với transaction nhiều thao tác, write concern áp dụng cho **commit** và các bảo đảm tương ứng, không đặt ngẫu nhiên một write concern khác nhau trên mỗi thao tác trong body.

Ví dụ Java:

```java
TransactionOptions options = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .readPreference(ReadPreference.primary())
    .build();
```

Ví dụ mongosh:

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority", wtimeout: 5000 }
});
```

Mục tiêu là commit đạt mức xác nhận theo chính sách của hệ thống.

### 18.2. Write concern timeout có thể tạo bất định ở commit

Giả sử:

```text
Body transaction đã hoàn tất
       |
       v
commitTransaction
       |
       +-- Primary xử lý commit
       |
       +-- Chưa đủ điều kiện xác nhận majority trước wtimeout
       |
       v
Client nhận lỗi xác nhận / commit result chưa rõ
```

Lỗi mức xác nhận không phải bằng chứng transaction đã bị abort. Khi driver trả nhãn `UnknownTransactionCommitResult`, hành động thích hợp là **retry commit** theo protocol.

### 18.3. `w: 1` và `w: "majority"` không giống nhau

Một commit được xác nhận `w: 1` có thể không đáp ứng mức durable/replicated mà nghiệp vụ quan trọng cần. Trong một số trường hợp failover, các ghi chưa đạt majority có nguy cơ rollback theo các bảo đảm của deployment.

**Không được đồng nhất**:

- “Client nhận phản hồi commit success”.
- “Transaction có mức bảo đảm độ bền mà nghiệp vụ yêu cầu”.

Vì vậy, chọn write concern phù hợp **ngay từ thiết kế**, rồi mới phân loại lỗi retry dựa trên chính sách đó.

### 18.4. Retry commit không có nghĩa gửi lại một lệnh ghi đơn document

Retryable writes cho `insertOne`/`updateOne` đủ điều kiện và retry commit của transaction có thể cùng dùng khả năng nhận diện ở tầng session/protocol, nhưng **đơn vị retry khác nhau**.

Không lấy một ví dụ retryable `insertOne` rồi kết luận có thể tự lặp toàn body transaction sau lỗi commit.

## 19. Trường hợp commit vẫn không thể xác định kết quả

### 19.1. Không phải lúc nào retry commit cũng kết thúc ngay

Nếu primary bị mất, mạng chia cắt hoặc driver hết deadline, ứng dụng có thể không nhận được phản hồi commit xác định trong một thời gian.

Khi đó, thay vì trả một kết luận bừa:

```text
COMMITTED
ABORTED / REJECTED
UNKNOWN_OUTCOME
```

hãy cho phép trạng thái **UNKNOWN_OUTCOME** trong workflow nghiệp vụ.

### 19.2. Xử lý sau khi mất session hoặc request kết thúc

Nếu ứng dụng restart, session cũ có thể không còn sẵn sàng để retry commit trực tiếp qua cùng đối tượng. Điều đó **không chứng minh transaction chưa commit**. Khi khởi động lại:

1. Lấy **requestId** đã ghi nhận trước khi thực thi.
2. Đọc trạng thái nghiệp vụ từ nguồn có thẩm quyền.
3. Xác minh payload, ledger và dấu hiệu commit.
4. Nếu chưa thể xác định, tiếp tục đối soát theo chính sách.
5. Chỉ tạo một lần nghiệp vụ mới khi có căn cứ rằng đó là ý định mới hoặc đã bảo vệ chống trùng.

**Không cố tái tạo protocol session/transaction identity thủ công** từ log bằng các trường không được driver cung cấp API hỗ trợ.

### 19.3. Dùng majority read khi phù hợp

Nếu transaction commit được kỳ vọng dùng majority write concern, việc đọc ledger từ primary với read concern `majority` có thể là một bước đối soát hữu ích.

Ví dụ mongosh:

```javascript
db.getSiblingDB("txn_retry_lab249").runCommand({
  find: "transferLedger249",
  filter: { requestId: "TR-249-JAVA-001" },
  limit: 1,
  readConcern: { level: "majority" }
});
```

Nhưng **không thấy ledger trong một lần đọc** không chứng minh transaction trước “chưa từng commit hoặc chưa từng được server thực thi”. Phải xét thời điểm đọc, trạng thái replication/failover, khả năng chưa hoàn tất, network và cách session/driver báo lỗi.

### 19.4. Không chỉ nhìn số dư

Ví dụ hai lần chuyển 100 từ A sang B sẽ tạo số dư khác nhau, nhưng nếu đồng thời có một giao dịch khác chuyển ngược 100 thì số dư cuối có thể lại giống kỳ vọng.

Do đó, đối soát phải theo **ledger/requestId**, không chỉ lấy chênh lệch số dư làm bằng chứng quyết định.

## 20. Thiết kế business idempotency khi có transaction retry

### 20.1. Tạo yêu cầu duy nhất trước transaction

Một API chuyển tiền nên nhận hoặc tạo **một idempotency key cho mỗi ý định chuyển**:

```json
{
  "requestId": "TR-2026-000123",
  "fromAccount": "A",
  "toAccount": "B",
  "amount": 100,
  "currency": "UNIT"
}
```

Khi frontend retry **cùng ý định**, dùng lại `requestId`. Khi người dùng thực sự muốn chuyển thêm 100 lần nữa, dùng **request ID khác**.

### 20.2. Unique index

```javascript
db.getSiblingDB("txn_retry_lab249")
  .transferLedger249
  .createIndex({ requestId: 1 }, { unique: true });
```

Unique index ngăn hai ledger record có cùng `requestId`. Việc chèn ledger **trong cùng transaction với thay đổi số dư** giúp hai loại dữ liệu commit hoặc abort cùng nhau theo bảo đảm transaction.

### 20.3. Kiểm tra payload khi gặp request trùng

Giả sử đã có:

```javascript
{
  requestId: "TR-001",
  from: "A",
  to: "B",
  amount: 100,
  currency: "UNIT"
}
```

Một request mới cùng `requestId` nhưng `amount: 500` không được xem là retry hợp lệ. API nên trả **conflict** hoặc trạng thái lỗi có kiểm soát, không tự động coi đó là giao dịch thành công.

Một hệ thống có thể lưu **hash của payload chuẩn hóa** để đối chiếu nhanh, nhưng phải xác định chuẩn encoding, trường được so sánh và cách xử lý xung đột.

### 20.4. Đừng chỉ dựa vào duplicate key

Nếu transaction Y nhận duplicate key do ledger của X đã commit, việc Y abort là điều hợp lý. Nhưng để trả kết quả cuối, API cần:

- Đọc ledger tương ứng.
- Xác minh đó là **đúng giao dịch** người dùng yêu cầu.
- Xác định trạng thái đã commit và những bước downstream.
- Không tự động gửi lại side effect bên ngoài.

### 20.5. Đặt một state machine cho yêu cầu

```text
RECEIVED
   |
   v
PROCESSING
   |              \
   |               \  Không rõ commit/response
   v                v
COMPLETED       UNKNOWN_OUTCOME
                     |
                     v
                 RECONCILING
                 /        \
                v          v
           COMPLETED   NEEDS_REVIEW
```

Các trạng thái trên chỉ là ví dụ; hệ thống thật cần xác định transaction cập nhật trạng thái nào, thời điểm nào và cách khôi phục sau crash. Mục tiêu là không phải nói dối người dùng bằng kết quả “thất bại” khi server có thể đã commit.

## 21. Gửi email, sự kiện và thanh toán bên ngoài

### 21.1. Vấn đề side effect ngoài transaction

Giả sử callback:

```java
session.withTransaction(() -> {
    saveOrder(session);
    chargeCardViaHttp();
    return null;
});
```

Nếu MongoDB transaction gặp transient error và callback chạy lại, **chargeCardViaHttp()` có thể bị gọi hai lần**, trong khi dữ liệu MongoDB của lần thử đầu đã abort. Điều này có thể tạo thanh toán trùng dù transaction của MongoDB vận hành đúng.

### 21.2. Transactional outbox

Một giải pháp phổ biến:

```text
MongoDB transaction:
  - cập nhật order
  - ghi ledger
  - ghi outboxEvent { eventId, type, payload }
  - commit

Worker riêng:
  - đọc outboxEvent đã commit
  - gửi email/payment event
  - ghi trạng thái đã xử lý
  - consumer dùng eventId để dedupe
```

Một outbox chỉ giúp tổ chức việc gửi sự kiện; để chống lặp thật sự, **consumer/downstream cũng cần idempotency hoặc cách đối soát**. Nếu worker crash sau khi gửi nhưng trước khi đánh dấu sent, nó có thể gửi lại.

### 21.3. Phân biệt retry commit với retry side effect

Ngay cả khi driver chỉ retry `commitTransaction`, một ứng dụng có thể đã gọi cổng thanh toán **trước commit**. Khi commit unknown, không được cho rằng cổng thanh toán cũng unknown theo cùng protocol MongoDB. Hai hệ thống có **cơ chế xác nhận riêng**, cần đối soát độc lập.

## 22. Các vấn đề concurrency trong transaction retry

### 22.1. Transaction mới phải đọc lại điều kiện nghiệp vụ

Nếu transaction bị abort do write conflict, lần thử mới không được dùng lại mọi dữ liệu đọc ở lần trước. Đặc biệt:

- Số dư có thể thay đổi.
- Trạng thái order có thể chuyển từ CREATED sang CANCELLED.
- Hạn mức có thể bị điều chỉnh.
- Document có thể bị xóa hoặc thêm.

Chạy lại body không đơn giản là **phát lại lệnh ghi**, mà là **thực hiện lại quyết định nghiệp vụ dựa trên snapshot mới**.

### 22.2. Kiểm soát điều kiện bằng filter

Ví dụ:

```javascript
{
  _id: "A",
  balance: { $gte: 100 }
}
```

được dùng làm filter của update trừ tiền. Điều kiện này bảo vệ một số bất biến ngay trong lệnh ghi; nếu `matchedCount = 0`, callback phải dừng và để transaction abort thay vì vẫn cộng tiền cho B.

### 22.3. Transaction không cho phép mọi thao tác chạy song song trên cùng session

MongoDB drivers không hỗ trợ tùy tiện chạy các thao tác song song trong **cùng một transaction/session**. Trong Java, không tự mở nhiều thread dùng chung một `ClientSession` để tăng tốc debit, credit, ledger.

Các lệnh trong body nên được điều phối theo thứ tự rõ và cùng session để tránh vi phạm hợp đồng driver.

### 22.4. Thời gian transaction và contention

Một transaction giữ lock/tài nguyên lâu có thể tăng xác suất conflict và timeout. Những cách giảm rủi ro gồm:

- Giới hạn số document/thao tác trong một transaction.
- Tránh network call hoặc công việc CPU nặng trong body.
- Duy trì index phù hợp cho các lệnh trong transaction.
- Dùng truy vấn có điều kiện chặt và request ID rõ ràng.
- Điều chỉnh retry/backoff khi thực sự cần, thay vì mở transaction rất dài.

## 23. Tình huống thực tế: transaction body retry nhưng callback trả kết quả khác

Giả sử callback có logic:

```java
session.withTransaction(() -> {
    int available = readInventory(session, sku);

    if (available < quantity) {
        throw new OutOfStockException();
    }

    reserveInventory(session, sku, quantity);
    return "RESERVED";
});
```

Lần thử đầu có 10 sản phẩm, đủ cho đơn đặt 8 sản phẩm. Transaction bị abort do conflict. Trong lúc đó, người khác đặt 5 sản phẩm.

Lần retry body đọc còn 5 sản phẩm, nên throw `OutOfStockException`. Đó **không phải lỗi của retry**: trạng thái đã đổi và nghiệp vụ không còn đủ điều kiện.

Nếu lỗi là **UnknownTransactionCommitResult sau khi body đã hoàn thành**, driver không nên chạy lại `readInventory` và `reserveInventory` trong transaction mới; trước tiên phải xác định kết quả commit của lần vừa thử.

## 24. Một vòng retry production cần có giới hạn và khả năng quan sát

### 24.1. Không vô hạn ở cả hai vòng

Hệ thống có thể:

- Retry transaction vài lần nếu lỗi transient.
- Retry commit trong giới hạn thời gian khi kết quả chưa rõ.
- Chuyển yêu cầu sang `UNKNOWN_OUTCOME` nếu hết thời hạn.
- Tiếp tục đối soát bất đồng bộ bằng request ID.

Không đặt số lần retry cố định một cách tùy tiện rồi giả định mọi transaction được giải quyết trong cùng số lần. Cần dựa vào độ trễ kỳ vọng, SLA, loại nghiệp vụ và driver.

### 24.2. Ghi log những gì?

Một log điều phối có thể gồm:

```javascript
{
  requestId: "TR-001",
  operation: "transferFunds",
  phase: "COMMIT",
  errorLabel: "UnknownTransactionCommitResult",
  transactionAttempt: 1,
  commitAttempt: 2,
  outcome: "UNKNOWN_OUTCOME",
  observedAt: ISODate("2026-11-14T09:00:00Z")
}
```

Đây là **schema log mẫu do ứng dụng tự thiết kế**. Không phải MongoDB tự tạo các trường trên.

Không ghi credentials, thông tin nhạy cảm hoặc toàn bộ request payload khi không cần thiết. Nếu log các trường session/transaction nội bộ, phải theo chính sách bảo mật và tính ổn định của driver.

### 24.3. Metrics và cảnh báo

| Dấu hiệu | Câu hỏi vận hành |
|---|---|
| Nhiều `TransientTransactionError` | Có write conflict, transaction quá dài hoặc failover thường xuyên không? |
| Nhiều `UnknownTransactionCommitResult` | Mạng/primary/write concern có làm commit khó xác nhận? |
| Nhiều commit retries | Có latency hoặc replication lag tăng? |
| Tỷ lệ transaction hoàn thành sau retry | Retry có giúp phục hồi hay chỉ che giấu vấn đề hạ tầng? |
| Số yêu cầu `UNKNOWN_OUTCOME` | Có backlog đối soát không? |
| Duplicate business key | Có client gửi lại API hoặc hệ thống xử lý trùng? |
| Độ trễ replica set | Majority write concern có chờ lâu? |
| Side effect trùng | Outbox/consumer có thiếu idempotency? |

Metrics cần được diễn giải theo **thời điểm, topology và workload**. Một spike transaction retry khi failover không nhất thiết giống spike do nhiều transaction cùng cập nhật một hot document.

## 25. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| Lỗi trong transaction thì luôn chạy lại cả body | Phải phân biệt lỗi transient trước commit và lỗi xác nhận commit |
| `UnknownTransactionCommitResult` nghĩa rollback | Có thể server đã commit; client chưa biết chắc |
| Retry commit là gọi lại debit và credit | Retry **chính `commitTransaction`** của cùng transaction |
| Retry toàn transaction dùng lại snapshot cũ | Lần thử mới phải đọc lại dữ liệu và kiểm tra điều kiện |
| Gọi `abortTransaction` sau commit timeout chắc chắn hoàn tác | Abort muộn không đảo ngược commit đã thành công |
| Tạo session mới rồi commit là retry commit | Không giữ transaction identity; không phải retry commit |
| `TransientTransactionError` là lỗi dữ liệu vĩnh viễn | Đây là nhãn báo lỗi tạm thời có thể cần retry transaction |
| Mọi MongoException đều transient | Duplicate key, validation, auth hoặc lỗi nghiệp vụ có thể không retryable |
| Driver `withTransaction()` chỉ gọi callback một lần | Helper có thể gọi lại callback khi retry transaction |
| Callback chạy nhiều lần thì MongoDB tự gửi lại email đúng một lần | MongoDB không rollback side effect bên ngoài |
| Commit được retry nghĩa callback cũng được retry | Hai vòng retry khác nhau |
| Một transaction mới luôn là retry an toàn cho transaction cũ | Có thể tạo tác động nghiệp vụ trùng nếu transaction cũ đã commit |
| Unique ledger key không cần kiểm tra payload | Cùng key nhưng payload khác là xung đột nghiệp vụ |
| Tổng số dư không đổi nghĩa chuyển tiền không bị trùng | Chuyển hai lần cũng có thể giữ tổng số dư |
| Không thấy ledger ngay nghĩa không commit | Có thể do read concern, replication lag hoặc thời điểm quan sát |
| Có transaction nghĩa request HTTP exactly-once | Cần business idempotency cho các lần gọi API riêng |
| Retryable writes và retry transaction là một | Phạm vi và protocol không giống nhau |
| Retry vô hạn sẽ luôn giải quyết được sự cố | Có thể làm cạn tài nguyên hoặc che giấu lỗi cấu hình |
| Outbox đảm bảo email không bao giờ trùng mà không cần consumer logic | Downstream vẫn cần idempotency/deduplication |

## 26. Bài tập thực hành

### Bài 1 — Phân loại lỗi

Cho các tình huống:

1. `updateOne` trong transaction bị `WriteConflict` và driver gắn `TransientTransactionError`.
2. Body thành công, `commitTransaction` trả `UnknownTransactionCommitResult`.
3. Insert ledger gặp duplicate key.
4. `commitTransaction` trả thành công.
5. Application server crash sau khi commit thành công, trước khi trả HTTP response.

Với mỗi tình huống, hãy xác định:

- Có nên retry toàn transaction không?
- Có nên retry chỉ commit không?
- Có cần đối soát theo business key không?
- Có được phép tự tạo request ID mới không?

### Bài 2 — Chọn đúng vòng retry

Một hệ thống có pseudocode:

```text
repeat until success:
    startTransaction()
    debit(100)
    credit(100)
    insertLedger()
    commitTransaction()
```

Hãy chỉ ra nguy cơ nếu commit lần đầu thành công nhưng response bị mất. Vẽ lại thuật toán với **vòng ngoài cho transaction body** và **vòng trong cho commit**. Bổ sung nhánh kết quả `UNKNOWN_OUTCOME`.

### Bài 3 — Lỗi transient ở lần đọc

Lần thử transaction X đọc số dư A là 1000, rồi gặp `TransientTransactionError`. Trong khi retry, một transaction khác rút 950.

- Lần thử mới phải đọc số dư nào?
- Có thể tiếp tục dùng điều kiện `balance >= 100` từ lần cũ không?
- Nếu chỉ còn 50, nghiệp vụ nên làm gì?
- Điều đó khác gì trường hợp commit của X không rõ?

### Bài 4 — Lỗi commit không rõ

Timeline:

```text
12:00:00 start transaction X
12:00:01 debit A
12:00:02 credit B
12:00:03 insert ledger
12:00:04 commit(X) gửi đi
12:00:05 server commit X
12:00:06 network mất response
12:00:07 driver nhận UnknownTransactionCommitResult
```

Hãy trả lời:

1. Có thể khẳng định X chưa commit không?
2. Tại 12:00:08 nên gửi lại gì?
3. Vì sao không tạo transaction Y để chạy lại debit/credit?
4. Nếu không thể xác nhận trước API deadline, nên trả trạng thái gì?

### Bài 5 — `withTransaction()` callback

Xem:

```java
session.withTransaction(() -> {
    updateInventory(session);
    sendEmail();
    return null;
});
```

- Callback có thể được gọi nhiều lần không?
- Nếu lần đầu đã gửi email nhưng transaction bị abort, điều gì xảy ra khi body retry?
- Hãy đề xuất dùng outbox event với `eventId` riêng.
- Vì sao consumer vẫn cần idempotency?

### Bài 6 — Request ID ngoài callback

So sánh:

```java
session.withTransaction(() -> {
    String id = UUID.randomUUID().toString();
    insertTransfer(session, id);
    return null;
});
```

với:

```java
final String id = incomingRequestId;
session.withTransaction(() -> {
    insertTransfer(session, id);
    return null;
});
```

Giải thích cách thứ hai hỗ trợ đối soát và business idempotency tốt hơn. Nếu client gửi lại request HTTP nhưng dùng ID mới, còn rủi ro gì?

### Bài 7 — Duplicate ledger key

Một request `TR-17` chuyển 100 từ A sang B đã commit. Client gọi lại cùng `TR-17` nhưng lần này payload chuyển 300.

- Unique index `requestId` giúp gì?
- Có được trả “đã chuyển 300 thành công” khi gặp duplicate key không?
- Những trường nào cần đối chiếu?
- Nên thông báo xung đột ra sao?

### Bài 8 — Hai lần chuyển tiền, tổng số dư vẫn đúng

A ban đầu 1000, B ban đầu 500. Transaction X chuyển 100 nhưng mất response commit. Application tạo transaction Y và chuyển thêm 100.

- Số dư sau X?
- Số dư sau Y?
- Tổng số dư trước và sau?
- Vì sao phép kiểm tra tổng số dư không chứng minh yêu cầu chỉ được xử lý một lần?
- Ledger/requestId giúp phát hiện lỗi thế nào?

### Bài 9 — Lỗi không retryable

Cho ba lỗi:

```text
DuplicateKey
DocumentValidationFailure
TransientTransactionError
```

Phân loại lỗi nào có thể là điều kiện retry toàn transaction theo driver, lỗi nào cần sửa dữ liệu hoặc giải quyết nghiệp vụ. Vì sao không retry mọi lỗi theo chu kỳ 100 ms đến khi thành công?

### Bài 10 — Read concern khi đối soát

Commit trước đó có kết quả chưa rõ. Ứng dụng đọc ledger từ secondary nhưng không thấy bản ghi.

1. Có thể kết luận transaction chưa commit không?
2. Replication lag ảnh hưởng thế nào?
3. Đọc primary với read concern `majority` mang lại tín hiệu gì?
4. Vì sao một lần đọc không thấy bản ghi vẫn chưa phải bằng chứng tuyệt đối “chưa hề thực thi”?
5. Bạn sẽ giữ request ở trạng thái gì trong lúc chờ xác định?

### Bài 11 — Thiết kế chuyển tiền với Java Sync Driver

Hãy viết một phương thức Java:

```java
TransferResult transfer(
    MongoClient client,
    String requestId,
    String from,
    String to,
    long amount
);
```

Yêu cầu:

- Transaction options có read concern snapshot, write concern majority.
- Tất cả lệnh MongoDB trong body cùng session.
- Chèn ledger có unique `requestId`.
- Trừ A có điều kiện đủ số dư.
- Cộng B chỉ khi trừ A hợp lệ.
- Dùng `withTransaction()`.
- Không gửi email trong callback.
- Sau ngoại lệ commit unknown không tự chạy giao dịch mới bằng request ID khác.

Giải thích trường hợp transaction callback bị driver gọi lại.

### Bài 12 — So sánh retryable write với retry transaction

Giả sử:

```javascript
db.accounts.updateOne(
  { _id: "A" },
  { $inc: { balance: -100 } }
);
```

và:

```text
startTransaction
  debit A
  credit B
  insert ledger
commit
```

Hãy mô tả:

- Đơn vị retry của retryable single-document write.
- Đơn vị retry khi body transaction gặp `TransientTransactionError`.
- Đơn vị retry khi commit transaction có `UnknownTransactionCommitResult`.
- Vì sao ba cơ chế không được áp dụng hoán đổi?

### Bài 13 — Vận hành khi mạng chập chờn

Trong một đợt failover, hệ thống ghi nhận nhiều `TransientTransactionError` và `UnknownTransactionCommitResult`. Hãy lập một bảng ghi nhận gồm:

- Request ID.
- Phase xảy ra lỗi.
- Error label.
- Số lần retry body.
- Số lần retry commit.
- Kết quả xác nhận cuối.
- Trạng thái đối soát.

Đề xuất deadline, backoff, metrics và cách ngăn hệ thống tạo những lệnh chuyển tiền trùng do người dùng bấm lại.

### Bài 14 — Thiết kế API có hồi đáp không chắc chắn

Client gửi:

```http
POST /transfers
Idempotency-Key: TR-2026-0001

{"from":"A","to":"B","amount":100}
```

Backend commit thành công, nhưng gateway trả timeout. Client gửi lại cùng request.

- Backend phân biệt đây là retry bằng dữ kiện nào?
- Có nên mở transaction mới để trừ/cộng ngay không?
- Nếu ledger đúng payload đã tồn tại, trả trạng thái gì?
- Nếu không đọc được ledger vì network outage, có nên trả `UNKNOWN_OUTCOME` không?
- Nếu cùng idempotency key nhưng amount khác, xử lý ra sao?

## 27. Quy tắc vận hành ngắn gọn

Khi một transaction MongoDB báo lỗi, hãy hỏi theo thứ tự:

1. **Lỗi ở body hay tại commit?** Đừng chỉ đọc tên exception.
2. **Có nhãn `TransientTransactionError` không?** Nếu xảy ra trong body và đáp ứng điều kiện retry, thử lại **toàn transaction** với một lần thử mới.
3. **Có nhãn `UnknownTransactionCommitResult` khi commit không?** Thử lại **commit của cùng transaction**, không chạy lại business body.
4. **Lỗi là duplicate key/validation/business rule?** Đừng retry tự động; kiểm tra nguyên nhân và trạng thái nghiệp vụ.
5. **Đã hết deadline hoặc không thể xác nhận commit?** Ghi nhận **UNKNOWN_OUTCOME**, giữ nguyên request ID và đối soát.
6. **API hoặc side effect ngoài MongoDB có thể bị gửi lại?** Đảm bảo idempotency xuyên các lần gọi độc lập, không chỉ trong driver.

Đây là quy tắc tư duy, không thay thế tài liệu API của driver/version đang sử dụng. Khi có convenient transaction API như `withTransaction()`, hãy ưu tiên sử dụng đúng hợp đồng của nó và **không chồng thêm một vòng retry toàn body không phân loại ở phía ứng dụng**.

## 28. Tổng kết

**Retry toàn giao dịch và retry commit giải quyết hai vấn đề hoàn toàn khác nhau.** Khi body gặp lỗi transient làm lần thử hiện tại không thể commit, có thể bắt đầu **transaction mới** và chạy lại toàn bộ logic. Khi commit có kết quả không xác định, cần gửi lại **`commitTransaction` của chính transaction đó** để làm rõ hoặc hoàn tất commit, chứ không khởi động giao dịch nghiệp vụ mới.

**Hai error labels cần nhớ:** `TransientTransactionError` thường dẫn tới retry toàn transaction; `UnknownTransactionCommitResult` dẫn tới retry commit. Cả hai phải được diễn giải theo **vị trí lỗi, driver và ngữ cảnh**, không phải mọi exception đều có thể retry.

**Transaction atomicity không đồng nghĩa business exactly-once.** Driver có thể retry callback, server có thể commit rồi mất response, và frontend có thể gửi lại cùng API sau HTTP timeout. Vì vậy cần **requestId/idempotency key ổn định, unique ledger, kiểm tra payload và trạng thái đối soát**, cùng cơ chế xử lý side effect ngoài MongoDB như outbox.

**Nếu không biết commit đã xảy ra hay chưa, đừng đoán.** Giữ trạng thái `UNKNOWN_OUTCOME`, giới hạn retry, đọc đối soát theo chính sách nhất quán phù hợp và không tự trừ/cộng tiền thêm một lần. Nắm vững khác biệt giữa **gửi lại body** và **gửi lại commit** là nền tảng để xây transaction MongoDB an toàn trước write conflict, failover và mất xác nhận qua mạng.

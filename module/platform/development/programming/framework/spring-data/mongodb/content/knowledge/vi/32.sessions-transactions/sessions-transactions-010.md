# Phân biệt retry toàn giao dịch với retry commit khi kết quả chưa xác định

> **Chương:** Session và giao dịch  
> **Module:** `SPRING_DATA_MONGODB`

Trong hệ thống xử lý đơn hàng, chuyển tiền, giữ chỗ hay trừ tồn kho, một MongoDB transaction có thể gặp lỗi khi đang thực hiện các lệnh ghi, hoặc gặp lỗi **đúng lúc gửi `commitTransaction`**. Hai tình huống nhìn bề ngoài đều là “lệnh thất bại”, nhưng cách khôi phục **khác hẳn nhau**:

- Khi giao dịch **đã bị hủy do một lỗi tạm thời**, cần **mở giao dịch mới và chạy lại toàn bộ transactional body** theo chính sách retry.
- Khi **không biết commit đã thành công hay chưa**, cần ưu tiên **retry riêng lệnh commit của chính giao dịch đó trên cùng session/transaction identity**, không chạy lại nghiệp vụ như một giao dịch mới.

Phân biệt sai có thể dẫn tới **ghi trùng phiếu thanh toán, cộng điểm hai lần, gửi hàng hai lần** hoặc báo thất bại dù database đã commit. Ngược lại, không retry khi giao dịch thật sự đã bị abort sẽ khiến một lỗi cạnh tranh tạm thời làm thất bại nghiệp vụ vốn có thể thành công ở lần tiếp theo.

Trong module `SPRING_DATA_MONGODB`, chúng ta kết nối, ánh xạ document và thao tác dữ liệu qua `MongoTemplate` hoặc repository; thực hành truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng. Bài này tập trung vào **session, transaction state, error labels và thuật toán retry đúng** ở MongoDB Java Driver và Spring Data MongoDB.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt lỗi xảy ra **trong transactional body** với lỗi xảy ra khi **commit**.
2. Giải thích ý nghĩa các error labels `TransientTransactionError` và `UnknownTransactionCommitResult`; không suy đoán transaction outcome chỉ từ việc client ném exception.
3. Mô tả đúng **retry whole transaction**: bỏ transaction attempt cũ, bắt đầu attempt mới, chạy lại các thao tác trong transaction.
4. Mô tả đúng **retry commit**: giữ cùng logical session và transaction identity, **không chạy lại transactional body** khi outcome commit chưa rõ.
5. Dùng Java Driver `ClientSession.withTransaction(...)`, tự thiết kế retry có giới hạn khi thực sự cần, và hiểu chỗ Spring Data `MongoTransactionManager`/`@Transactional` khác driver callback.
6. Phân biệt retry transaction nội bộ với **HTTP request retry**, idempotency key, unique index và outbox.
7. Viết kiểm thử lỗi cạnh tranh, lỗi mạng ở commit, failover và kiểm tra kết quả dựa trên invariant thay vì số lần thực thi callback.
8. Chọn timeout, retry budget, quan sát, reconciliation và trạng thái `COMMIT_UNKNOWN` trong thực tế.

## 2. Một transaction đi qua những pha nào?

Đường đi thông thường:

```text
Client / Application
      |
      v
Start ClientSession
      |
      v
Start Transaction
      |
      v
Transactional Body
  - insert payment record
  - debit account
  - credit account
      |
      +---- body error / aborted? ----> Abort / start NEW transaction
      |                                 and RETRY WHOLE BODY if transient
      v
commitTransaction()
      |
      +---- ACK success ----------> CONFIRMED COMMITTED
      |
      +---- outcome unknown ------> RETRY COMMIT on SAME transaction
      |
      +---- definite failure -----> Handle failure; do not guess
```

Một **MongoDB session** mang ngữ cảnh cho các thao tác liên quan. Transaction được gắn với session và một định danh/`txnNumber` do driver quản lý. Khi phải retry **commit**, driver cần tiếp tục tác động tới **chính transaction đã thực hiện body**. Khi phải retry **toàn transaction**, driver bắt đầu một transaction attempt mới và thực hiện lại logic.

Không coi mọi dòng lệnh sau `startTransaction()` là một “lần gửi duy nhất”: các network request, retry, topology discovery và acknowledgment có thể thất bại độc lập. Điều client **biết chắc** khác với điều server **đã thật sự làm**.

### 2.1. Thời điểm lỗi quyết định cách xử lý

| Thời điểm | Trạng thái có thể biết | Xử lý chính |
| --- | --- | --- |
| Trước `startTransaction` | Chưa có transaction body | Xử lý lỗi kết nối/khởi tạo; chưa có business write trong transaction |
| Khi thực hiện lệnh trong body, có label `TransientTransactionError` | Attempt hiện tại không thể hoàn tất theo cách thông thường | Abort/cleanup attempt, **bắt đầu transaction mới**, chạy lại body nếu an toàn |
| Khi chạy body, lỗi validation/duplicate key không transient | Lỗi nghiệp vụ hoặc schema chưa được giải quyết | Dừng và trả lỗi; không tự retry vô hạn |
| `commitTransaction` trả thành công | Commit đã được xác nhận theo write concern được chọn | Trả thành công, không retry business logic |
| `commitTransaction` trả lỗi có `UnknownTransactionCommitResult` | **Chưa thể khẳng định commit thành công hay thất bại** | **Retry commit trên transaction cũ**, giữ session, không chạy lại body |
| Không thể xác nhận commit dù hết retry budget | Kết quả ở client **vẫn chưa xác định** | Trả/tracking trạng thái không xác định, **reconcile** theo operation ID |
| Commit trả lỗi khác | Cần phân loại chính xác; không tự giả định có thể replay | Theo đặc tả driver và lỗi thực tế, không tự restart nghiệp vụ |

Đây là các **nguyên tắc xử lý chính**, không phải danh sách đầy đủ mọi nhánh của các phiên bản MongoDB. Luôn dựa vào error label và API driver/server thực tế, không chỉ dựa vào văn bản exception.

## 3. Error labels: cơ chế phân loại thay vì đoán từ thông báo

MongoDB Java Driver hiển thị nhãn lỗi thông qua `MongoException.hasErrorLabel(...)`. Hai nhãn cốt lõi:

```java
import com.mongodb.MongoException;

boolean transientTxn =
    mongoException.hasErrorLabel("TransientTransactionError");

boolean commitUnknown =
    mongoException.hasErrorLabel("UnknownTransactionCommitResult");
```

Trong đoạn trên `mongoException` là exception do driver trả về; đây là minh họa thuộc một khối xử lý lỗi Java, không phải một chương trình Java hoàn chỉnh độc lập.

### 3.1. TransientTransactionError (TTE)

Nhãn `TransientTransactionError` báo rằng đã gặp một lỗi tạm thời liên quan transaction và **có thể cần thử lại toàn bộ giao dịch**. Ví dụ thường gặp:

- Write conflict do hai transaction đụng nhau.
- Primary stepdown/election trong lúc transaction đang thực hiện.
- Một số tình huống topology/network/transient error khi lệnh trong transaction chưa thể hoàn tất.

**Chiến lược:** bỏ transaction attempt bị lỗi; mở transaction mới; thực hiện lại **toàn bộ transactional body** sau khi đảm bảo code có thể chạy nhiều lần.

Không chỉ retry **một lệnh ghi cuối cùng** trong transaction sau write conflict rồi tin rằng phần còn lại vẫn có thể commit. Khi transaction đã bị abort, toàn bộ attempt không còn hợp lệ.

### 3.2. UnknownTransactionCommitResult (UTCR)

Nhãn `UnknownTransactionCommitResult` có ý nghĩa khác: client **không biết kết quả cuối cùng của `commitTransaction`**. Tình huống điển hình là network gián đoạn khi commit đã được gửi và server có thể đã commit, nhưng acknowledgment không về được client.

**Chiến lược:** gọi lại **`commitTransaction` cho cùng session/transaction**, không thực hiện lại insert/debit/credit như một business attempt mới.

Vì commit có thể đã thành công, việc tự tạo transaction mới và chạy lại body ngay có nguy cơ tạo side effect trùng. Nếu retry commit không thể hoàn tất trong retry budget, phải **giữ trạng thái outcome unknown**, không coi đó là rollback chắc chắn.

### 3.3. Hai nhãn không phải mô hình “true/false”

Nhãn là một phần trong thông tin lỗi. Một exception không có hai nhãn này **không tự động có nghĩa** transaction đã được commit hoặc abort theo cách nghiệp vụ mong muốn. Ví dụ validation error, duplicate key, session expired hoặc một response khác cần xử lý cụ thể.

Khi driver/framework dịch exception sang loại khác, kiểm tra **chuỗi nguyên nhân (cause chain)**; không parse câu văn log như `"connection reset"` để tự quyết định retry transaction.

## 4. Hai thuật toán retry khác nhau

### 4.1. Retry *toàn bộ transaction*

```text
Attempt 1
  session.startTransaction()
  insert ledger(op-123)
  debit wallet A
  credit wallet B
      |
      +-- TransientTransactionError -> attempt aborted

Attempt 2 (NEW transaction)
  session.startTransaction()
  insert ledger(op-123)
  debit wallet A
  credit wallet B
  commitTransaction() -> SUCCESS
```

Ở attempt 1, các thao tác transactional đã bị rollback/abort, nên attempt 2 phải thực thi lại **toàn bộ các bước bên trong transaction**. Nếu logic bên trong có đọc số dư, lần mới cần **đọc lại** để tính từ trạng thái hiện tại, không dùng giá trị cache từ attempt cũ.

### 4.2. Retry *riêng commit*

```text
Attempt 1
  session.startTransaction()
  insert ledger(op-123)       [ONLY ONCE in this attempt]
  debit wallet A             [ONLY ONCE in this attempt]
  credit wallet B            [ONLY ONCE in this attempt]
  commitTransaction()
      |
      +-- NETWORK ERROR; UNKNOWN commit result
      |
      +-- commitTransaction() AGAIN on SAME session + transaction
              |
              +-- SUCCESS / confirmed outcome
```

**Không** chạy lại ba thao tác business giữa hai lần commit. Driver dùng cùng session/transaction identity để server có thể xử lý repeated commit theo cơ chế protocol. Nếu callback bị chạy lần thứ hai trong một transaction **mới** trước khi có kết quả commit rõ ràng, đây không còn là retry commit nữa.

### 4.3. Bảng quyết định bắt buộc nhớ

| Mục | Retry whole transaction | Retry commit |
| --- | --- | --- |
| Tín hiệu chính | `TransientTransactionError` trên thao tác transaction cần restart | `UnknownTransactionCommitResult` tại commit |
| Transaction identity | **Mới** | **Giữ nguyên** |
| Chạy lại body? | **Có**, từ đầu | **Không** |
| Đọc lại dữ liệu và kiểm tra nghiệp vụ? | **Có**, trong attempt mới | **Không** (chỉ xác nhận commit cũ) |
| Side effects ngoài MongoDB trong callback | Có nguy cơ lặp, phải loại bỏ/hoãn qua outbox | Không chạy lại callback, nhưng vẫn cần xử lý trạng thái không xác định |
| Khi hết budget | Báo lỗi transient/chưa hoàn tất, tùy trạng thái | Giữ `COMMIT_UNKNOWN`, reconcile theo operation ID |
| Áp dụng cho lỗi schema cố định | Không | Không |
| Mục tiêu | Khôi phục attempt chắc chắn không thể tiếp tục | Giải quyết **sự mơ hồ của acknowledgment commit** |

## 5. Một tình huống cụ thể: chuyển tiền giữa hai ví

Giả sử tenant A có hai ví tiền:

```javascript
db.wallets.insertMany([
  {
    _id: "WALLET-A",
    tenantId: "TENANT-A",
    balanceMinor: NumberLong(100000),
    version: NumberLong(1)
  },
  {
    _id: "WALLET-B",
    tenantId: "TENANT-A",
    balanceMinor: NumberLong(20000),
    version: NumberLong(1)
  }
])
```

Yêu cầu chuyển `30000` từ A sang B, với `operationId = "TRANSFER-123"`. Khi thành công, ta mong:

```text
WALLET-A: 100000 -> 70000
WALLET-B:  20000 -> 50000

Total before = 120000
Total after  = 120000

transfers: đúng một record có _id = "TRANSFER-123"
```

Ứng dụng phải thực hiện trong **một MongoDB transaction**:

1. Ghi bản ghi chuyển tiền với `_id` là operation ID ổn định.
2. Trừ số dư của ví A **khi đủ số dư**.
3. Cộng tiền vào ví B trong cùng tenant.
4. Commit cùng lúc các thay đổi.

### 5.1. Vì sao cần operationId?

Ngoài retry trong driver, người dùng hoặc API gateway có thể **gửi lại cả HTTP request** do timeout. Việc này **không phải** retry commit của cùng session; server nhận một request/business operation mới.

Định danh `operationId` giúp ứng dụng thực hiện **idempotency** bằng kiểm tra record đã tồn tại, unique index và trạng thái giao dịch. `_id` của MongoDB đã có unique index; có thể dùng `_id` là operation ID **duy nhất trong phạm vi hệ thống**. Nếu ID chỉ duy nhất trong tenant, dùng khóa tổng hợp `tenantId + operationId` và unique compound index phù hợp.

Operation ID **không thay** retry commit khi transaction outcome chưa rõ, nhưng là tuyến phòng thủ quan trọng khi session mất, request bị gửi lại hoặc hệ thống cần reconciliation.

### 5.2. Vì sao transaction không đủ để tránh mọi lần chuyển trùng?

Một transaction bảo vệ tính nguyên tử **trong một lần thực thi**. Nó không bảo đảm client bên ngoài sẽ không gửi hai yêu cầu chuyển tiền giống nhau với hai operation IDs khác nhau. Với giao dịch thanh toán, phải thiết kế:

- Idempotency key từ caller được xác minh và gắn với nội dung request.
- Chống duplicate bằng unique key trong database.
- Kiểm tra request có cùng key nhưng payload khác → **không tái dùng im lặng**.
- Audit trail và cơ chế đối soát khi kết quả commit không xác định.

Đặc biệt, **không thực hiện gọi thanh toán bên thứ ba, gửi email hoặc publish message trực tiếp bên trong transaction callback**, vì callback có thể bị chạy lại nhiều lần sau lỗi tạm thời. Dùng transactional outbox hoặc workflow ngoài transaction với idempotent delivery.

## 6. Java Driver: dùng callback withTransaction khi có thể

MongoDB Java Driver có API `ClientSession.withTransaction(...)` giúp quản lý phiên giao dịch và thực hiện logic retry theo driver transaction specification. Đây thường là điểm bắt đầu tốt hơn việc tự viết nhiều vòng `while` bao quanh `commitTransaction` và xử lý mọi loại network exception.

### 6.1. Chuẩn bị collection và dữ liệu

Với database kiểm thử `shop`:

```javascript
use shop

db.wallets.insertMany([
  { _id: "WALLET-A", tenantId: "TENANT-A",
    balanceMinor: NumberLong(100000), version: NumberLong(1) },
  { _id: "WALLET-B", tenantId: "TENANT-A",
    balanceMinor: NumberLong(20000), version: NumberLong(1) }
])

db.transfers.createIndex(
  { tenantId: 1, operationId: 1 },
  { unique: true, name: "uq_transfer_tenant_operation" }
)
```

Trong ví dụ Java tiếp theo, dùng `_id` của transfer record là một ID ổn định và duy nhất toàn hệ thống (hoặc tạo `_id` bằng cách mã hóa không nhập nhằng từ tenant + operationId), đồng thời lưu riêng hai field tenant và operationId để kiểm tra. Unique index trên cặp tenant/operationId là lớp phòng thủ bổ sung.

**Không dùng `insertMany` nhiều lần trên cùng một database không được reset**: ví dụ seed được thực hiện đúng một lần trên database test. Các thử nghiệm thất bại và retry cần dữ liệu test riêng hoặc cleanup có giới hạn theo ID.

### 6.2. TransactionOptions

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;

TransactionOptions options = TransactionOptions.builder()
    .readPreference(ReadPreference.primary())
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .build();
```

- `ReadPreference.primary()`: dùng primary cho các thao tác transaction theo các yêu cầu hỗ trợ của MongoDB.
- `ReadConcern.SNAPSHOT`: đặt quy tắc nhìn dữ liệu trong transaction; không tự ngăn mọi dạng write skew hoặc thay thế ràng buộc nghiệp vụ.
- `WriteConcern.MAJORITY`: áp dụng cho commit/acknowledgment theo quy tắc hỗ trợ; không dùng write concern riêng lẻ tùy tiện cho từng statement trong transaction.

Driver/session sẽ phối hợp các option với session và topology; tùy chọn không bảo đảm transaction thành công nếu network, node hoặc dữ liệu đang conflict.

### 6.3. Code Java sử dụng withTransaction

File `WalletTransferService.java`:

```java
package com.example.shop.wallet;

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
import java.util.Objects;
import org.bson.Document;

public final class WalletTransferService {

    private final MongoClient client;
    private final MongoDatabase db;

    public WalletTransferService(MongoClient client) {
        this(client, "shop");
    }

    // Cho phép integration test dùng database cô lập.
    public WalletTransferService(
            MongoClient client, String databaseName) {
        this.client = Objects.requireNonNull(client);
        this.db = client.getDatabase(
            Objects.requireNonNull(databaseName));
    }

    public record TransferRequest(
        String tenantId,
        String operationId,
        String fromWalletId,
        String toWalletId,
        long amountMinor
    ) {}

    public record TransferReceipt(
        String operationId, String status) {}

    public TransferReceipt transfer(TransferRequest req) {
        validate(req);

        MongoCollection<Document> wallets =
            db.getCollection("wallets");
        MongoCollection<Document> transfers =
            db.getCollection("transfers");

        TransactionOptions txnOptions =
            TransactionOptions.builder()
                .readPreference(ReadPreference.primary())
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {
                // Callback có thể chạy NHIỀU lần khi driver
                // retry TOÀN BỘ transaction.
                transfers.insertOne(
                    session,
                    new Document("_id", req.operationId())
                        .append("tenantId", req.tenantId())
                        .append("operationId", req.operationId())
                        .append("fromWalletId", req.fromWalletId())
                        .append("toWalletId", req.toWalletId())
                        .append("amountMinor", req.amountMinor())
                        .append("state", "COMMITTED"));

                UpdateResult debit = wallets.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", req.fromWalletId()),
                        Filters.eq("tenantId", req.tenantId()),
                        Filters.gte(
                            "balanceMinor", req.amountMinor())
                    ),
                    Updates.combine(
                        Updates.inc(
                            "balanceMinor", -req.amountMinor()),
                        Updates.inc("version", 1L)
                    ));

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Ví nguồn không tồn tại hoặc thiếu số dư");
                }

                UpdateResult credit = wallets.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", req.toWalletId()),
                        Filters.eq("tenantId", req.tenantId())
                    ),
                    Updates.combine(
                        Updates.inc(
                            "balanceMinor", req.amountMinor()),
                        Updates.inc("version", 1L)
                    ));

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Ví đích không tồn tại");
                }

                // Record nằm TRONG transaction; chỉ có thể được
                // nhìn thấy sau khi commit thành công.
                return new TransferReceipt(
                    req.operationId(), "COMMITTED");
            }, txnOptions);
        }
    }

    private static void validate(TransferRequest req) {
        Objects.requireNonNull(req, "req");
        if (req.tenantId() == null || req.tenantId().isBlank()
                || req.operationId() == null
                || req.operationId().isBlank()
                || req.fromWalletId() == null
                || req.toWalletId() == null
                || req.fromWalletId().equals(req.toWalletId())
                || req.amountMinor() <= 0
                || req.amountMinor() == Long.MIN_VALUE) {
            throw new IllegalArgumentException(
                "Thông tin chuyển tiền không hợp lệ");
        }
    }
}
```

**Lưu ý về quyền:** `tenantId` trong `TransferRequest` là giá trị phải được tạo từ hoặc xác minh với thông tin xác thực phía server. Một client tự đặt `tenantId="TENANT-A"` không đủ để được phép chuyển tiền của tenant A.

`TransferReceipt("COMMITTED")` được tạo **trong body** nhưng chỉ được trả ra bởi `transfer(...)` sau khi `withTransaction(...)` kết thúc thành công. Nếu commit chưa xác định và driver trả exception, caller **không được gửi receipt thành công** chỉ vì callback đã tính ra object này.

Mã sử dụng MongoDB Java Driver sync API; hỗ trợ và tên method của `withTransaction` có thể khác nếu dự án dùng driver rất cũ. Nó minh họa cơ chế transaction, chưa phải hệ thống chuyển tiền production hoàn chỉnh: cần giới hạn số tiền, kiểm tra chống tràn số, xác thực tài khoản đích, idempotency payload, observability và đối soát.

### 6.4. withTransaction làm gì khi retry?

Driver callback API tuân theo logic retry transaction theo nhãn lỗi và quy tắc driver, bao gồm:

1. Chạy body trong transaction.
2. Nếu body gặp lỗi được phân loại `TransientTransactionError` và còn budget phù hợp, **thử transaction mới và gọi lại callback**.
3. Khi body hoàn tất, gọi commit.
4. Nếu commit trả `UnknownTransactionCommitResult` và còn điều kiện retry, **retry commit**, không gọi lại callback chỉ vì acknowledgement chưa rõ.
5. Khi không thể tự khôi phục, trả exception để ứng dụng xử lý/reconcile.

**Không được hiểu `withTransaction` là máy đảm bảo “exactly once” cho code bên trong callback.** Callback có thể chạy nhiều lần. Driver cũng có các quy tắc dừng retry và thời hạn; không tự triển khai thêm một retry loop **quanh toàn bộ `withTransaction`** khi exception báo outcome commit chưa rõ.

### 6.5. Callback không được có side effect bên ngoài transaction

**Phản ví dụ:**

```java
session.withTransaction(() -> {
    wallets.updateOne(session, filter, update);
    emailService.sendTransferSuccessEmail(userEmail);
    return null;
});
```

Nếu callback chạy lần nữa do TTE, email có thể được gửi hai lần, mặc dù MongoDB chỉ commit một attempt. Nếu commit cuối cùng thất bại, email thậm chí có thể đã gửi dù không có chuyển tiền nào được commit.

Giải pháp: lưu một **outbox event** trong cùng MongoDB transaction, sau đó một worker gửi email/message **sau commit** bằng cơ chế có idempotency/retry riêng. Outbox bảo vệ tính nguyên tử giữa dữ liệu nghiệp vụ và ý định phát sự kiện; nó **không** biến gửi thông báo qua mạng thành exactly-once nếu consumer không có deduplication.

## 7. Khi tự viết retry: hai vòng lặp và hai bất biến

Đôi khi cần điều khiển retry budget, metric hoặc exception mapping riêng. Khi đó có thể thiết kế thủ công, nhưng nên **ưu tiên helper driver** trừ khi có yêu cầu cụ thể và đủ test để kiểm chứng.

### 7.1. Pseudocode đúng cho hai nhánh

```text
function runTransactionWithRetry(body, operationId):
  for transactionAttempt in boundedAttempts:
    session = newSession()
    session.startTransaction()

    try:
      result = body(session)
    catch error:
      abortCurrentTransactionBestEffort(session)
      close(session)
      if error has "TransientTransactionError"
         and overallBudgetAllowsRetry:
         applyBackoff()
         continue  # retry WHOLE TRANSACTION
      raise error

    for commitAttempt in boundedCommitAttempts:
      try:
        session.commitTransaction()
        close(session)
        return result  # confirmed
      catch error:
        if error has "UnknownTransactionCommitResult":
          if overallBudgetAllowsCommitRetry:
            applyBackoff()
            continue  # retry COMMIT of SAME txn

          close(session)
          raise CommitOutcomeUnknown(operationId)

        # Không mặc định chạy lại business body khi commit lỗi.
        close(session)
        raise error

  raise RetryBudgetExhausted(operationId)
```

**Hai bất biến cần review trong code:**

1. `continue` của vòng **transaction** mở transaction mới và gọi lại body **chỉ khi được phép**.
2. `continue` của vòng **commit** gọi lại commit trên **cùng session và transaction**, không nhảy ra vòng transaction để gọi lại body.

Một vòng `while(true)` duy nhất bọc cả ba lệnh `insert/debit/credit/commit` là **sai** đối với `UnknownTransactionCommitResult` vì nó không phân biệt sự mơ hồ của commit với transaction bị abort.

### 7.2. Tại sao phải giữ session khi commit unknown?

Commit là một phần của protocol transaction; transaction identity gắn với logical session và transaction number. Với một commit outcome unknown, client không thể khởi tạo session hoàn toàn mới rồi gọi `commitTransaction()` để “commit nốt” transaction cũ. Một session mới không mang cùng transaction identity.

Đóng session và tạo transaction mới làm mất cơ hội dùng retry-commit của chính transaction ban đầu. Nếu session hoặc process không còn sống, chuyển sang **reconciliation dựa trên operation ID**; không tự khẳng định transaction cũ đã rollback.

### 7.3. Retry budget phải là hữu hạn

Không lặp vô hạn chỉ vì lỗi có label:

- Giới hạn số attempt và **thời gian tổng** của request.
- Tôn trọng deadline của MongoDB transaction, server selection và business SLA.
- Áp backoff + jitter ở mức hợp lý, tránh tất cả client retry đồng thời khi primary failover.
- Khi cạn commit retry budget, giữ outcome unknown và chuyển sang tra cứu/đối soát.
- Không che lỗi do validation, duplicate key, cấu hình hoặc business precondition bằng một retry không giới hạn.

Các số lần retry minh họa phải do dự án đo đạc và chốt; không có một cấu hình “retry 3 lần là luôn đủ” cho mọi workload.

### 7.4. Một tình huống phản ví dụ nguy hiểm

```java
// PHẢN VÍ DỤ: KHÔNG làm thế này khi không biết commit đã thành công.
while (true) {
    try {
        performBusinessTransaction();
        break;
    } catch (RuntimeException e) {
        // Mọi lỗi, kể cả UnknownTransactionCommitResult,
        // đều làm chạy lại TOÀN BỘ nghiệp vụ.
    }
}
```

Nếu request thứ nhất thực tế đã commit nhưng response thất lạc, vòng hai có thể trừ tiền thêm lần nữa — đặc biệt nếu caller đã tạo **operationId mới** mỗi attempt. Bắt mọi exception rồi retry không phân loại không phải cơ chế chịu lỗi.

## 8. Spring Data MongoDB: @Transactional quản lý transaction, không phải retry policy hoàn chỉnh

Spring Data MongoDB tích hợp với Spring Transaction Management thông qua `MongoTransactionManager` cho imperative API và `ReactiveMongoTransactionManager` cho reactive API. Để một repository hoặc `MongoTemplate` tham gia transaction, chúng phải sử dụng **database factory/session có transaction manager tương ứng**.

### 8.1. Cấu hình MongoTransactionManager

File `MongoTransactionConfiguration.java`:

```java
package com.example.shop.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoTransactionConfiguration {

    @Bean("mongoTransactionManager")
    public MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

MongoDB multi-document transaction yêu cầu deployment hỗ trợ transaction, ví dụ replica set hoặc sharded cluster cấu hình phù hợp. **Một MongoDB standalone thông thường không hỗ trợ transaction nhiều document**. Không mặc định tạo bean manager là đủ; phải xác minh topology, session, quyền và read/write concern thực tế.

### 8.2. Ví dụ service @Transactional

File `WalletTransferWriter.java`:

```java
package com.example.shop.wallet;

import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WalletTransferWriter {

    private final MongoTemplate template;

    public WalletTransferWriter(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void writeOnce(
            String tenantId,
            String operationId,
            String fromWalletId,
            String toWalletId,
            long amountMinor) {

        // Input và tenant quyền hạn phải được validate
        // TRƯỚC khi gọi service trong ứng dụng thật.
        template.insert(
            new Document("_id", operationId)
                .append("tenantId", tenantId)
                .append("operationId", operationId)
                .append("fromWalletId", fromWalletId)
                .append("toWalletId", toWalletId)
                .append("amountMinor", amountMinor)
                .append("state", "COMMITTED"),
            "transfers");

        Query debitQuery = Query.query(
            Criteria.where("_id").is(fromWalletId)
                .and("tenantId").is(tenantId)
                .and("balanceMinor").gte(amountMinor));

        Update debitUpdate = new Update()
            .inc("balanceMinor", -amountMinor)
            .inc("version", 1L);

        UpdateResult debit = template.updateFirst(
            debitQuery, debitUpdate, "wallets");

        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                "Ví nguồn không tồn tại hoặc không đủ tiền");
        }

        Query creditQuery = Query.query(
            Criteria.where("_id").is(toWalletId)
                .and("tenantId").is(tenantId));

        Update creditUpdate = new Update()
            .inc("balanceMinor", amountMinor)
            .inc("version", 1L);

        UpdateResult credit = template.updateFirst(
            creditQuery, creditUpdate, "wallets");

        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                "Ví đích không tồn tại");
        }

        // Spring transaction interceptor commit sau khi
        // method body return thành công.
    }
}
```

Giả định tất cả thao tác `MongoTemplate` dùng **cùng database factory** mà `mongoTransactionManager` quản lý, và lời gọi `writeOnce(...)` đi qua Spring transactional proxy. Khi một exception làm rollback theo quy tắc Spring, các thay đổi trong transaction không được commit riêng lẻ.

**Những điều cần đặc biệt chú ý:**

- `@Transactional` không có nghĩa Spring sẽ tự động chạy lại toàn bộ method khi server trả `TransientTransactionError`.
- `@Transactional` cũng không có nghĩa Spring mặc nhiên retry `commitTransaction` theo đúng `UnknownTransactionCommitResult` trong mọi phiên bản/cấu hình.
- Nếu method được gọi qua **self-invocation** trong cùng object mà không đi qua proxy, transactional annotation kiểu proxy có thể không có tác dụng.
- Quy tắc rollback mặc định của Spring tập trung vào unchecked exceptions; checked exceptions cần cấu hình rollback phù hợp nếu nghiệp vụ yêu cầu.
- Không nuốt exception bên trong transaction rồi trả thành công, nếu điều đó khiến interceptor cố commit một trạng thái nghiệp vụ không hợp lệ.

### 8.3. Commit có thể lỗi *sau khi body method trả về*

Với `@Transactional`, các bước:

```text
Caller
  |
  v
Spring transaction proxy
  |
  +-- begin transaction
  |
  +-- call writeOnce(...) method body
  |      |
  |      +-- method body returns normally
  |
  +-- commit transaction  <-- ERROR CAN OCCUR HERE
  |
  +-- return to Caller only after commit processing
```

Vì vậy, một khối `try/catch` **bên trong `writeOnce`** chỉ bao quanh các câu lệnh của body sẽ không bắt được mọi exception xảy ra **khi interceptor commit ở ngoài**. Nếu muốn xử lý outcome unknown, logic xử lý phải nằm ở **đúng ranh giới commit**, chứ không chỉ ở catch quanh `template.updateFirst(...)`.

### 8.4. TransactionTemplate cũng không tự biến thành withTransaction

`TransactionTemplate` cho phép thực hiện callback trong một Spring transaction:

```java
import org.springframework.transaction.support.TransactionTemplate;

// transactionTemplate cấu hình bằng mongoTransactionManager.
transactionTemplate.execute(status -> {
    // Các MongoTemplate/repository calls cùng factory
    // tham gia transaction do Spring quản lý.
    return transferWriterLogic.runBusinessSteps();
});
```

Khi `execute(...)` kết thúc thành công, transaction manager đã xử lý commit. Nhưng đây vẫn là **Spring transaction callback**, không thể suy luận nó mang trọn thuật toán retry toàn body và retry commit giống `ClientSession.withTransaction`.

Nếu thêm outer loop quanh `TransactionTemplate.execute(...)` và retry trên **mọi** exception, tình huống outcome commit unknown vẫn có nguy cơ thực thi body hai lần. Chỉ cho phép whole retry khi đã xác định attempt có thể được retry an toàn và đã đóng/cleanup transaction cũ.

### 8.5. Tổ chức retry với Spring

Một mô hình trách nhiệm rõ ràng:

```text
HTTP Controller
    |
    v
TransferCoordinator (validate + idempotency + retry classification)
    |
    +-- fresh transaction attempt only for retryable abort
    |
    v
WalletTransferWriter (single @Transactional invocation)
    |
    v
MongoTransactionManager
    |
    +-- commit handling at transaction boundary
```

Khi cần retry commit với `UnknownTransactionCommitResult` theo chính xác session hiện tại, nên cân nhắc:

1. Sử dụng `ClientSession.withTransaction(...)` ở một component dùng Java Driver, nơi thuật toán callback đã được hỗ trợ, **hoặc**
2. Kiểm tra extension point và implementation của `MongoTransactionManager` đang dùng để triển khai **retry commit đúng chỗ**, với test server thật và không làm mất transaction identity, **hoặc**
3. Nếu commit outcome không thể xác minh, **báo trạng thái không xác định** và chạy reconciliation/idempotency, thay vì gọi lại toàn service method.

Không copy một override của `MongoTransactionManager.doCommit(...)` từ phiên bản khác mà chưa kiểm tra API protected/internal của phiên bản Spring Data thực tế. Một override sai có thể chuyển nhánh commit unknown thành retry whole transaction, đúng kiểu lỗi cần tránh trong bài này.

### 8.6. @Retryable và thứ tự AOP

Nếu dự án dùng Spring Retry:

```java
// PHẢN VÍ DỤ nếu không xác minh điều kiện, proxy order và label.
@Retryable
@Transactional
public void transfer(...) {
    // business writes
}
```

Hai annotation **không đủ** để chứng minh:

- Transaction mới được tạo cho mỗi lần retry.
- Commit unknown sẽ chỉ retry commit.
- Việc retry không lặp side effects.
- Retry chỉ áp cho nhãn lỗi transient phù hợp.

Thứ tự advice/proxy và cơ chế exception translation có thể thay đổi ranh giới retry. Nếu cần Spring Retry, hãy viết integration test chứng minh **mỗi retry whole dùng một transaction mới**, và **commit unknown không kích hoạt retry toàn body**.

### 8.7. Với ReactiveMongoTemplate

Trong reactive stack, `ReactiveMongoTransactionManager` kết hợp `TransactionalOperator`/reactive `@Transactional`:

```java
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.context.annotation.Bean;

@Bean("reactiveMongoTransactionManager")
ReactiveMongoTransactionManager reactiveMongoTransactionManager(
        ReactiveMongoDatabaseFactory factory) {
    return new ReactiveMongoTransactionManager(factory);
}
```

Với `TransactionalOperator`:

```java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

Mono<TransferReceipt> operation = executeBusinessWritesReactive()
    .as(transactionalOperator::transactional);
```

Các biến/method trên là minh họa trong một component reactive đã cấu hình. **Không** gắn `retryWhen(...)` vô điều kiện ở ngoài publisher đã được bọc transaction: điều đó có thể **đăng ký lại toàn bộ nghiệp vụ** sau lỗi commit outcome unknown. Cần phân loại lỗi tương tự imperative API, quản lý Reactor context/session, retry budget và các side effects.

## 9. Retry tại các ranh giới khác nhau

Một hệ thống có thể có nhiều tầng tự retry:

```text
Mobile/Web client    -> retry HTTP request
API Gateway          -> retry upstream request
Service              -> retry business method
Spring Transaction   -> begin/commit/rollback
MongoDB Driver       -> retry eligible commands / transaction commit
MongoDB replica set  -> network, elections, replication
```

Không được cộng gộp các tầng này thành một “mặc định an toàn”. Ví dụ:

- Driver xử lý `UnknownTransactionCommitResult` bằng retry commit.
- API gateway lại timeout và gửi **request hoàn toàn mới**.
- Service trong request mới tạo **operationId mới**.
- Nghiệp vụ bị thực hiện hai lần, dù retry commit của driver ở request đầu là đúng.

### 9.1. Retryable writes khác retry transactions

MongoDB có cơ chế **retryable writes** cho một số lệnh ghi đơn lẻ ngoài transaction. Cơ chế đó không thay thế thuật toán retry transaction nhiều document; các statement bên trong transaction cần được xử lý theo transaction semantics.

Đừng suy luận `retryWrites=true` trong URI nghĩa là **mọi transaction sẽ tự chạy lại từ đầu**. Khả năng retry `commitTransaction` và `abortTransaction` được quản lý theo quy tắc transaction riêng của driver.

### 9.2. Cần bảo đảm gì tại HTTP boundary?

Với API chuyển tiền, một request nên có:

```json
{
  "operationId": "TRANSFER-123",
  "fromWalletId": "WALLET-A",
  "toWalletId": "WALLET-B",
  "amountMinor": 30000
}
```

Khi client retry cùng operation ID:

1. Kiểm tra actor được phép xử lý tenant/ví.
2. Tìm transfer record đã commit theo **operation ID đã xác minh**; nếu có, đối chiếu payload và trả cùng kết quả.
3. Nếu operation đang trong trạng thái outcome unknown, trả trạng thái chờ đối soát thay vì khởi chạy một transfer mới ngay.
4. Nếu chắc chắn chưa có operation và được phép tạo, thực hiện logic mới theo quy trình có idempotency.
5. Không bao giờ tự tạo operationId ngẫu nhiên **mỗi retry attempt** của cùng một yêu cầu nghiệp vụ.

Đọc không thấy một record trên secondary **không phải bằng chứng transaction đã abort**: replication lag có thể khiến record mới commit chưa hiện ra. Cần dùng đường đọc/reconciliation có read concern và yêu cầu độ mới phù hợp, thường đọc primary; ngay cả “không thấy” tức thời trên primary cũng chưa phải bằng chứng đủ mạnh trong mọi tình huống một commit khác đang chưa được giải quyết.

## 10. Idempotency: khép vòng kiểm soát lỗi không xác định

**Idempotency** là một hợp đồng nghiệp vụ: thực hiện cùng một operation ID hợp lệ nhiều lần không làm trạng thái kết quả bị áp dụng nhiều lần.

### 10.1. Unique index và payload fingerprint

```javascript
db.transfers.createIndex(
  { tenantId: 1, operationId: 1 },
  { unique: true, name: "uq_tenant_operation" }
)
```

Với `operationId="TRANSFER-123"`, lưu:

```javascript
{
  _id: "TRANSFER-123",
  tenantId: "TENANT-A",
  operationId: "TRANSFER-123",
  fromWalletId: "WALLET-A",
  toWalletId: "WALLET-B",
  amountMinor: NumberLong(30000),
  requestFingerprint: "hash-of-canonical-request",
  state: "COMMITTED"
}
```

`requestFingerprint` phải được tạo theo **quy tắc canonical hóa ổn định** và thuật toán phù hợp; không chỉ hash chuỗi JSON tự do với thứ tự field có thể đổi. Nếu cùng operation ID nhưng amount/wallet khác, trả conflict; không dùng kết quả của request cũ cho request mới không tương đương.

### 10.2. Unique index không trả lời ngay mọi commit unknown

Khi transaction A có commit outcome unknown, việc chạy một transaction B mới với cùng key có thể:

- Đụng unique key nếu A đã commit.
- Chịu cạnh tranh/chờ/kết quả khác khi A vẫn đang được giải quyết.
- Bị conflict hoặc nhận lỗi khác tùy topology/điều kiện.

Vì vậy unique index là cơ chế **phòng double-apply khi application retry**, chứ không phải giấy phép bỏ qua thuật toán **retry commit trên session cũ** hoặc tuyên bố “không có record nghĩa là chưa commit”.

### 10.3. Outbox và exactly-once end-to-end

```text
MongoDB transaction:
  - debit wallet A
  - credit wallet B
  - insert transfer ledger(opId)
  - insert outbox event(eventId)
             |
             v
Commit confirmed
             |
             v
Outbox dispatcher -> broker / email / payment integration
             |
             v
Consumer deduplicates by eventId / operationId
```

Nếu transaction callback retry do TTE, các insert outbox của attempt abort sẽ không được commit. Nếu commit unknown, **không** trực tiếp publish sự kiện mới rồi hy vọng nó đại diện transaction đã commit; dispatcher chỉ đọc những outbox records thật sự đã commit.

Message delivery có thể là at-least-once. Consumer cần idempotency; MongoDB transaction không thể bao bọc nguyên tử một lệnh gửi email hoặc một API bên thứ ba không tham gia cùng transaction.

## 11. Khi commit outcome chưa xác định sau khi đã hết retry budget

Đây là trường hợp cần xử lý thận trọng nhất:

```text
Transaction T (operationId = TRANSFER-123)
    |
    +-- body completed
    |
    +-- commitTransaction() sent
    |       |
    |       +-- server MIGHT have committed
    |       +-- acknowledgment lost
    |
    +-- retry commit on same transaction
            |
            +-- still UnknownTransactionCommitResult
            +-- deadline exceeded

Client outcome: COMMIT_UNKNOWN
Database outcome: MAY BE COMMITTED OR NOT
```

**Không được tự chuyển `COMMIT_UNKNOWN` thành `ABORTED` hoặc `FAILED` chỉ vì hết thời gian chờ.** Sự kiện “client hết thời gian chờ” không chứng minh “MongoDB đã rollback”.

### 11.1. Phân biệt outcome của client và trạng thái nghiệp vụ

| Outcome mà client biết | Phản hồi nghiệp vụ có thể đưa ra | Được chạy lại body ngay? |
| --- | --- | --- |
| Commit ACK thành công | `COMMITTED` | Không |
| Body abort chắc chắn và đã hết retry whole | `NOT_COMMITTED` / lỗi có thể retry ở request mới theo chính sách | Chỉ sau khi xác nhận an toàn, dùng cùng operation ID |
| Commit outcome unknown | `PENDING_CONFIRMATION` / `COMMIT_UNKNOWN` | **Không** chạy lại mù quáng |
| Dữ liệu đã được đối soát xác nhận commit | `COMMITTED`, trả receipt cũ | Không |
| Dữ liệu đã được đối soát đủ căn cứ là chưa commit | Cho phép request idempotent tiếp tục theo quy tắc hệ thống | Có điều kiện, dùng cùng operation ID, không tạo side effect trùng |

`COMMIT_UNKNOWN` là một **trạng thái biết của ứng dụng về độ chắc chắn**, không nhất thiết là state được lưu trong transaction record. Nếu transaction chưa commit, bản ghi chuyển tiền trong đó cũng chưa tồn tại. Có thể cần một nơi lưu yêu cầu ngoài transaction hoặc log điều phối có kiểm soát để theo dõi trạng thái pending.

### 11.2. Reconciliation theo operation ID

Khi không còn cùng session để retry commit (ví dụ process crash hoặc shutdown), cần cơ chế đối soát:

1. Giữ `operationId` ổn định, kèm tenant, loại nghiệp vụ và payload fingerprint.
2. Đọc từ nguồn có **độ mới/độ bền phù hợp**, thường primary với read concern phù hợp, không mặc định dùng secondary đang lag.
3. Nếu thấy transfer record với operation ID và payload đúng, xác nhận trạng thái đã commit và trả cùng kết quả.
4. Nếu chưa thấy record, **không kết luận ngay đã abort**: có thể còn commit đang hoàn tất, network/election hoặc request khác xử lý cùng key.
5. Áp retry/backoff/time budget và quy tắc khóa/idempotency ở tầng điều phối.
6. Nếu không thể phân loại chắc chắn, giữ trạng thái cần điều tra/đối soát, hoặc chuyển vào hàng xử lý thủ công theo yêu cầu nghiệp vụ.

### 11.3. Vì sao “không thấy record” có thể không đủ?

Giả sử một session vẫn đang cố commit trong lúc API khác đọc ledger. Truy vấn không thấy record chưa chứng minh transaction cũ sẽ **không thể** commit sau đó. Ngay cả đọc primary với `readConcern:majority` cũng không phải phép màu chứng minh **mọi giao dịch đang ở trạng thái không xác định đã kết thúc**.

Với hệ thống nhạy cảm, reconciliation cần kết hợp:

- Operation ID và unique index.
- Trạng thái yêu cầu đã được đăng ký trước khi giao dịch bắt đầu (khi kiến trúc yêu cầu).
- Thời điểm/deadline và thông tin điều phối transaction.
- Đọc có read concern phù hợp và cơ chế chờ/kiểm tra lặp có giới hạn.
- Đối soát nguồn sự thật của business event, không chỉ một câu đọc snapshot thiếu record.

Nếu không có đủ bằng chứng, trả trạng thái “đang xử lý/đang xác minh” tốt hơn tự thực hiện lại một khoản chuyển tiền có thể đã thành công.

### 11.4. API response cho trạng thái không xác định

Một API có thể trả một response có ID truy vết và trạng thái xử lý:

```json
{
  "operationId": "TRANSFER-123",
  "status": "PENDING_CONFIRMATION",
  "message": "Đang xác nhận kết quả giao dịch",
  "statusUrl": "/transfers/TRANSFER-123/status"
}
```

HTTP status và contract cụ thể phải do API/product quyết định. Không sử dụng một response **“đã chuyển tiền thành công”** khi commit chưa được xác nhận. Cũng không trả “đã thất bại, vui lòng tạo chuyển tiền mới” khiến user tạo operationId mới và có nguy cơ trừ tiền hai lần.

### 11.5. Cảnh báo về retry nền và việc đóng session

Khi một request hết budget mà session vẫn còn sử dụng được, helper driver có thể đã thử commit theo chính sách của nó. Ứng dụng không nên kết thúc request rồi âm thầm chạy một vòng retry commit **không được giám sát** trên session có thể bị đóng khi request kết thúc.

Nếu muốn tiếp tục xử lý ngoài request, phải thiết kế **workflow durable** (trạng thái operation, queue, reconciliation, ownership và timeout) rõ ràng. Không hứa với caller một kết quả chắc chắn chỉ dựa vào một background thread không có quản lý vòng đời.

## 12. Ba dòng thời gian cần thuộc lòng

### 12.1. Body gặp write conflict, transaction abort

```text
t0: startTransaction(T1)
t1: insert transfer ledger inside T1
t2: update wallet A inside T1
t3: concurrent write conflict -> TransientTransactionError
t4: abort/cleanup T1 (no commit)
t5: startTransaction(T2)
t6: rerun entire body: insert, debit, credit
t7: commit T2 -> success

Kết quả:
  chỉ các write đã commit trong T2 có hiệu lực
  các bước trong T1 không được xem là committed
```

### 12.2. Commit đã xảy ra, ACK bị mất

```text
t0: startTransaction(T1)
t1: insert transfer ledger inside T1
t2: debit and credit inside T1
t3: commitTransaction(T1) reaches server
t4: server commits T1
t5: connection drops before client sees success
t6: client gets UnknownTransactionCommitResult
t7: client retries commitTransaction(T1), same session / identity
t8: commit retry resolves outcome

Kết quả:
  business body thực hiện 1 lần trong T1
  không có T2 chỉ vì ACK của commit bị mất
```

### 12.3. Commit outcome vẫn unknown sau nhiều lần retry

```text
t0: startTransaction(T1)
t1: body completes
t2: commitTransaction(T1) sent
t3: UnknownTransactionCommitResult
t4: retry commit T1
t5: UnknownTransactionCommitResult
t6: request budget exhausted / session unavailable
t7: API returns PENDING_CONFIRMATION
t8: reconciliation uses stable operationId

Kết quả:
  không được đoán COMMITTED hoặc ABORTED tại t6
```

**Điểm chung:** code xử lý lỗi phải phản ánh **thời điểm lỗi và điều ta biết về transaction state**, không chỉ đối chiếu chuỗi “timeout” hoặc “network error”.

## 13. Retry budget, transaction lifetime và exponential backoff

Retry không miễn phí:

- Mỗi transaction attempt có thể đọc và tính toán lại từ đầu.
- Transaction lâu có thể giữ tài nguyên server, tăng xác suất conflict và gây áp lực lên replication/lock.
- Khi primary election, hàng trăm clients retry cùng lúc có thể làm tải tăng mạnh.
- Commit retry chờ acknowledgment có thể kéo dài user-facing latency.

### 13.1. Hai ngân sách phải tách biệt

| Budget | Dành cho | Khi hết |
| --- | --- | --- |
| Transaction retry budget | Số attempt **toàn body** sau lỗi transient hợp lệ | Dừng tạo attempt mới, trả lỗi hoặc chuyển xử lý theo policy |
| Commit retry budget | Số lần thử xác định kết quả commit **trên cùng transaction** | Giữ `COMMIT_UNKNOWN` nếu outcome chưa được giải quyết |

Nên có thêm **overall operation deadline**. Ví dụ minh họa:

```text
Business SLA:       10 seconds
Transaction tries:  bounded and backoff
Commit retries:     bounded and backoff
On commit unknown:  stop guessing, reconcile
```

Con số chỉ mang tính ví dụ; phải chọn từ thực nghiệm và transaction/server settings. Không đặt một retry loop dài hơn nhiều lần transaction lifetime hoặc thời gian chờ của client mà không có chủ ý.

### 13.2. Backoff chỉ áp khi có thể retry

Backoff/jitter thường hữu ích cho write conflict hoặc election, nhưng **không** được dùng để biến lỗi không retryable thành retryable. Với `UnknownTransactionCommitResult`, backoff nằm **giữa những lần retry commit**; với `TransientTransactionError` trong body, backoff nằm **giữa những transaction attempts mới**.

Không đưa `Thread.sleep` tùy tiện vào Java reactive event loop. Với reactive code, dùng retry/cancellation operators có kiểm soát, gắn đúng pha và nhãn lỗi.

### 13.3. Chọn TransactionOptions có chủ đích

Nên kiểm tra:

1. `readPreference` có phù hợp transaction không (thường primary).
2. `readConcern` có đáp ứng snapshot/consistency cần thiết không.
3. `writeConcern` của commit có yêu cầu majority không.
4. Server selection timeout và network timeout có vượt SLA ứng dụng không.
5. Session có bị đóng khi commit retry còn chạy không.
6. Transaction có thực hiện các thao tác không được hỗ trợ bởi deployment/phiên bản không.

Đừng dùng `writeConcern: 1` chỉ để giảm độ trễ khi nghiệp vụ cần nhận biết một commit bền vững qua failover; cũng không giả định `majority` tự làm kết quả commit luôn được ACK thành công trong mọi sự cố.

## 14. MongoDB error labels và driver exception translation

Với Java Driver, nên phân loại bằng `MongoException.hasErrorLabel`:

```java
import com.mongodb.MongoException;

public static boolean hasMongoErrorLabel(
        Throwable error, String label) {
    for (Throwable current = error;
            current != null;
            current = current.getCause()) {
        if (current instanceof MongoException mongo
                && mongo.hasErrorLabel(label)) {
            return true;
        }
    }
    return false;
}
```

Trong một Spring Data application, exception có thể đã được Spring exception translator bọc/biến đổi. Duyệt cause chain có thể giúp phát hiện MongoDB label **nếu còn nguyên nhân driver**; nếu label đã bị mất qua một lớp wrapping, cần điều tra cách translation và log có cấu trúc ở ranh giới transaction.

**Lưu ý:** không tự áp thuật toán:

```java
// PHẢN VÍ DỤ: chỉ dựa vào tên exception, không biết pha.
if (ex instanceof java.net.SocketTimeoutException) {
    retryEntireBusinessTransaction();
}
```

Một timeout có thể xảy ra khi body chưa commit, hoặc sau khi server đã commit nhưng trước ACK. Nếu không biết pha và error label, **retry toàn business là nguy hiểm**.

### 14.1. Có thể có nhãn khác

MongoDB còn những error labels khác cho retryable writes và các lỗi khác tùy phiên bản. `RetryableWriteError` không đồng nghĩa `TransientTransactionError`, và một error code riêng không thay thế ngữ nghĩa nhãn transaction.

Không xây bảng mã error code “nếu 91 hoặc 11600 thì retry transaction” mà bỏ qua error label, pha xảy ra lỗi và transaction state. Với tương thích nhiều server/driver versions, sử dụng API của driver cùng tài liệu transaction error handling tương ứng.

### 14.2. Write concern error tại commit

Commit có thể đã được thực thi ở server nhưng client gặp lỗi xác nhận durability/write concern. Khi driver gắn `UnknownTransactionCommitResult`, **không suy ra mọi thay đổi đã rollback**. Tình huống này khác với body bị lỗi validation hoặc duplicate key trước commit.

Đó là lý do báo cáo kết quả phải tách **“không nhận được commit ACK”** khỏi **“server xác nhận abort”** và **“server từ chối lệnh nghiệp vụ”**.

## 15. Kiểm thử tích hợp giao dịch trên replica set thật

Mock `MongoTemplate` hoặc `MongoCollection` có thể kiểm tra thứ tự gọi method, nhưng **không chứng minh** transaction thật sự atomic, commit đã được majority xác nhận hoặc một error label sẽ được driver xử lý đúng sau failover. Cần MongoDB **replica set test riêng**; một server standalone thông thường không đủ.

### 15.1. Cấu trúc kiểm thử

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Transaction thành công | Hai ví thay đổi cùng nhau, tổng tiền bảo toàn, chỉ có một ledger record |
| Throw exception giữa các bước | Không có debit một phía, không có transfer record commit |
| Retry cùng operationId như request mới | Không áp tiền lần hai; service/coordinator xử lý duplicate theo idempotency |
| Transient write conflict | Có thể chạy lại **toàn body** trong transaction mới |
| Unknown commit result | Chỉ retry commit **của transaction hiện tại**; không chạy lại body vì mất ACK |
| Driver/process mất session | Chuyển sang reconciliation dựa trên operationId |
| Tenant khác dùng ID tương tự | Không đọc/ghi chéo tenant khi thiếu quyền |
| Cạn retry budget | Kết quả commit unknown vẫn được trình bày là chưa xác định |

### 15.2. Ví dụ JUnit 5 kiểm tra atomicity và idempotency

Test sau dùng MongoDB driver trực tiếp. Nó yêu cầu biến môi trường `TX_REPLICA_TEST_URI` trỏ tới **replica set test đã được cấp phép**, không phải production. Các ID test được tạo ngẫu nhiên và cleanup **chỉ theo ID** để không xóa dữ liệu của bài test khác.

File `WalletTransferTransactionIntegrationTest.java`:

```java
package com.example.shop.wallet;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class WalletTransferTransactionIntegrationTest {

    @Test
    void transferCommitsBothWalletsAndAbortsOnMissingDestination() {
        String uri = System.getenv("TX_REPLICA_TEST_URI");
        Assumptions.assumeTrue(
            uri != null && !uri.isBlank(),
            "Cần replica set MongoDB TEST riêng");

        // Database này phải thực sự tách biệt và chỉ dành cho CI.
        String databaseName = "tx_retry_lesson_it";
        String suffix = UUID.randomUUID().toString();
        String fromId = "SRC-" + suffix;
        String toId = "DST-" + suffix;
        String operationId = "TRANSFER-" + suffix;
        String failingId = "FAILED-" + suffix;
        String nonexistentId = "MISSING-" + suffix;

        try (MongoClient client = MongoClients.create(uri)) {
            var db = client.getDatabase(databaseName);
            // Chuẩn bị collection TRƯỚC transaction đầu tiên.
            if (!db.listCollectionNames()
                    .into(new ArrayList<String>())
                    .contains("transfers")) {
                db.createCollection("transfers");
            }
            MongoCollection<Document> wallets =
                db.getCollection("wallets");
            MongoCollection<Document> transfers =
                db.getCollection("transfers");

            wallets.insertMany(List.of(
                new Document("_id", fromId)
                    .append("tenantId", "TENANT-TEST")
                    .append("balanceMinor", 100000L)
                    .append("version", 1L),
                new Document("_id", toId)
                    .append("tenantId", "TENANT-TEST")
                    .append("balanceMinor", 20000L)
                    .append("version", 1L)
            ));

            try {
                WalletTransferService service =
                    new WalletTransferService(
                        client, databaseName);

                WalletTransferService.TransferRequest request =
                    new WalletTransferService.TransferRequest(
                        "TENANT-TEST", operationId,
                        fromId, toId, 30000L);

                var receipt = service.transfer(request);
                assertThat(receipt.operationId())
                    .isEqualTo(operationId);
                assertThat(receipt.status())
                    .isEqualTo("COMMITTED");

                assertThat(wallets.find(
                    Filters.eq("_id", fromId))
                    .first().getLong("balanceMinor"))
                    .isEqualTo(70000L);

                assertThat(wallets.find(
                    Filters.eq("_id", toId))
                    .first().getLong("balanceMinor"))
                    .isEqualTo(50000L);

                assertThat(transfers.countDocuments(
                    Filters.eq("_id", operationId)))
                    .isEqualTo(1L);

                // Ví đích không tồn tại: transaction phải abort.
                var invalidDestination =
                    new WalletTransferService.TransferRequest(
                        "TENANT-TEST", failingId,
                        fromId, nonexistentId, 1000L);

                assertThatThrownBy(
                    () -> service.transfer(invalidDestination))
                    .isInstanceOf(IllegalStateException.class);

                // Debit trong transaction lỗi không được commit.
                assertThat(wallets.find(
                    Filters.eq("_id", fromId))
                    .first().getLong("balanceMinor"))
                    .isEqualTo(70000L);
                assertThat(transfers.countDocuments(
                    Filters.eq("_id", failingId)))
                    .isZero();

                // Retry HTTP cùng operationId KHÔNG phải
                // cùng một commit retry. Service thô sẽ lỗi
                // duplicate; coordinator idempotency phải
                // tra lại receipt cũ thay vì debit lần nữa.
                assertThatThrownBy(
                    () -> service.transfer(request))
                    .isInstanceOf(RuntimeException.class);

                assertThat(wallets.find(
                    Filters.eq("_id", fromId))
                    .first().getLong("balanceMinor"))
                    .isEqualTo(70000L);

            } finally {
                // Không drop collection hoặc deleteMany({}).
                wallets.deleteMany(Filters.in(
                    "_id", fromId, toId));
                transfers.deleteMany(Filters.in(
                    "_id", operationId, failingId));
            }
        }
    }
}
```

**Giới hạn cần nêu rõ:** test này xác minh atomicity, bảo toàn tổng và khả năng ngăn double-apply bằng operation ID. Nó **không chủ động tạo lỗi `TransientTransactionError` hoặc `UnknownTransactionCommitResult`**, nên **không** được xem là bằng chứng đã kiểm thử mọi nhánh retry. Để xác minh nhánh fault injection, phải bổ sung test riêng.

**Cảnh báo an toàn:** chỉ chạy nếu URI được cấp trỏ đến **replica set TEST**. Mặc dù cleanup theo ID, một test ghi vào database sai môi trường vẫn có thể gây hại. Nên kiểm tra cấu hình deployment trong CI và dùng MongoDB credentials hạn chế chỉ cho test database; không tự động chạy trên production bằng URI mặc định.

### 15.3. Test lỗi TTE và UTCR có kiểm soát

Để tái hiện chính xác hai nhánh, một môi trường test có thể sử dụng MongoDB **failpoints** hoặc fault injection có quyền hạn trên cluster thử nghiệm. Việc bật failpoint phải có fixture setup/cleanup rõ ràng, không làm trên cluster dùng chung.

**Scenario A — `TransientTransactionError` khi body:**

1. Bắt đầu transaction T1.
2. Tạo write conflict hoặc một lỗi tạm thời được driver/server gắn label TTE vào **statement trong body**.
3. Xác minh T1 không commit.
4. Quan sát callback/body được chạy lại **trong transaction attempt mới** nếu helper cho phép retry.
5. Xác minh trạng thái cuối chỉ phản ánh **một business operation**, không có ledger double-apply.

**Scenario B — `UnknownTransactionCommitResult`:**

1. Body T1 hoàn tất.
2. Fault injection được điều khiển tại `commitTransaction` để tạo lỗi với label UTCR.
3. Đếm số lần callback **không tăng chỉ vì UTCR**; commit được thử lại trên cùng transaction identity.
4. Khi ACK cuối có thể xác nhận, kiểm tra ledger và hai số dư chính xác.
5. Khi cố tình làm commit unknown kéo dài quá budget, kiểm tra application **không tự trả “ABORTED”** và **không restart nghiệp vụ với ID mới**.

**Không dùng một network disconnect bất kỳ làm test chắc chắn của UTCR.** Lỗi thực tế có thể không mang label cần kiểm thử, hoặc xảy ra trước khi commit thực sự được gửi. Test phải xác nhận **nhãn lỗi và thời điểm xảy ra**, không chỉ xem có exception.

### 15.4. Không assert số lần callback luôn bằng 1

Nếu transaction body gặp TTE, callback **có thể chạy nhiều lần** và điều đó là hành vi đúng. Chỉ số quan trọng:

- **State đã commit:** mỗi transfer hợp lệ xuất hiện một lần, tổng số tiền không đổi.
- **Callback invocation:** có thể nhiều lần với whole-transaction retry.
- **Commit invocation:** có thể nhiều lần với UTCR, nhưng không lặp callback chỉ vì kết quả commit mơ hồ.
- **External side effect:** không được chạy lặp cùng callback; kiểm tra outbox/idempotency.

Tập trung vào invariant và trạng thái cuối; đừng viết test “callback được gọi đúng một lần” rồi khiến driver retry đúng bị coi là test fail.

## 16. Một số điều kiện không retry được bằng cách chạy lại nguyên transaction

Không phải mọi transaction failure đều transient:

| Sự cố | Có nên retry whole transaction ngay? | Lý do |
| --- | --- | --- |
| `TransientTransactionError` rõ ràng khi body bị abort | **Có điều kiện** | Lỗi tạm thời, attempt mới có thể thành công |
| Duplicate `operationId` | **Không tự động** | Có thể là request đã xử lý; cần kiểm tra idempotency/payload |
| Validation error của MongoDB `$jsonSchema` | Không | Schema hoặc dữ liệu sai sẽ tiếp tục sai |
| Không đủ số dư, ví nguồn không tồn tại | Không | Business precondition không thỏa |
| Vi phạm unique index khác | Không | Cần xem nghiệp vụ/đụng khóa; không phải cứ retry sẽ sửa |
| Commit outcome unknown | **Không** | Retry **commit**, không replay body |
| Session đã mất sau commit unknown | Không mù quáng | Reconcile theo operation ID |
| Auth/permission error | Không | Cần sửa quyền/configuration |
| Transaction vượt giới hạn lifetime/resource | Không lặp vô hạn | Cần tối ưu transaction hoặc chia nhỏ |
| Network timeout không rõ pha/label | Không dựa trên tên exception | Phải biết có thể đã commit hay chưa |

### 16.1. Transaction không thay business invariant

Giao dịch nhiều document giúp **atomicity**, nhưng nhiều transaction cạnh tranh vẫn cần kiểm tra điều kiện tại **lệnh ghi**:

```java
// Đúng ý tưởng: debit chỉ khi balance >= amount.
Filters.and(
    Filters.eq("_id", fromWalletId),
    Filters.eq("tenantId", tenantId),
    Filters.gte("balanceMinor", amountMinor)
)
```

Tránh:

```text
1. read balance = 100000
2. calculate new balance = 70000
3. update without condition on current balance/version
```

Khi nhiều writers cập nhật cùng account, có thể gặp conflict và cần retry, nhưng **một transaction không làm sai logic kiểm tra điều kiện trở thành đúng**. Dùng atomic conditional update, unique constraints, expected version và mô hình account/ledger phù hợp.

### 16.2. Đừng giữ transaction mở trong lúc gọi dịch vụ khác

```text
startTransaction
  -> call external payment API (possibly seconds)
  -> wait for human approval
  -> update MongoDB
commitTransaction
```

Đây là thiết kế rủi ro: transaction kéo dài, giữ tài nguyên, dễ timeout/abort; external side effect không rollback đồng bộ với database. Với quy trình kéo dài, dùng **saga/workflow và outbox** thay vì giữ MongoDB transaction mở.

## 17. Một bộ phân loại lỗi nhỏ để kiểm tra tư duy retry

Khi chuyển thuật toán sang framework hoặc thư viện, hữu ích nếu tách quyết định **“làm gì tiếp”** ra khỏi việc thực thi side effects. Ví dụ dưới đây là **bộ phân loại minh họa**, không thay thế driver transaction callback.

```java
package com.example.shop.tx;

public final class TransactionRetryDecision {

    public enum Phase { BODY, COMMIT }

    public enum Action {
        RETRY_WHOLE_TRANSACTION,
        RETRY_SAME_COMMIT,
        RECONCILE_UNKNOWN_COMMIT,
        STOP_AND_HANDLE
    }

    private TransactionRetryDecision() {}

    public static Action decide(
            Phase phase,
            boolean hasTransientTransactionError,
            boolean hasUnknownCommitResult,
            boolean retryBudgetRemaining) {

        if (phase == Phase.COMMIT
                && hasUnknownCommitResult) {
            return retryBudgetRemaining
                ? Action.RETRY_SAME_COMMIT
                : Action.RECONCILE_UNKNOWN_COMMIT;
        }

        if (phase == Phase.BODY
                && hasTransientTransactionError
                && retryBudgetRemaining) {
            return Action.RETRY_WHOLE_TRANSACTION;
        }

        return Action.STOP_AND_HANDLE;
    }
}
```

Đây là **bộ phân loại có chủ đích giới hạn**: nó không diễn giải mọi nhãn có thể xuất hiện tại pha commit, không thực hiện session cleanup và không thay thế quy trình xác định session outcome. Nó giúp kiểm tra một bất biến tối thiểu: **UTCR tại commit không bao giờ trở thành RETRY_WHOLE_TRANSACTION**.

### 17.1. Unit test bộ phân loại

```java
package com.example.shop.tx;

import org.junit.jupiter.api.Test;

import static com.example.shop.tx.TransactionRetryDecision.Action.*;
import static com.example.shop.tx.TransactionRetryDecision.Phase.*;
import static org.assertj.core.api.Assertions.assertThat;

class TransactionRetryDecisionTest {

    @Test
    void transientBodyErrorStartsFreshTransaction() {
        assertThat(TransactionRetryDecision.decide(
            BODY, true, false, true))
            .isEqualTo(RETRY_WHOLE_TRANSACTION);
    }

    @Test
    void unknownCommitDoesNotReplayBusinessBody() {
        assertThat(TransactionRetryDecision.decide(
            COMMIT, false, true, true))
            .isEqualTo(RETRY_SAME_COMMIT);
    }

    @Test
    void exhaustedUnknownCommitMustBeReconciled() {
        assertThat(TransactionRetryDecision.decide(
            COMMIT, false, true, false))
            .isEqualTo(RECONCILE_UNKNOWN_COMMIT);
    }

    @Test
    void validationAndBusinessErrorsDoNotAutoRetry() {
        assertThat(TransactionRetryDecision.decide(
            BODY, false, false, true))
            .isEqualTo(STOP_AND_HANDLE);
    }

    @Test
    void exhaustedBodyBudgetDoesNotLoopForever() {
        assertThat(TransactionRetryDecision.decide(
            BODY, true, false, false))
            .isEqualTo(STOP_AND_HANDLE);
    }
}
```

Đây là **unit test thuần Java**, không cần MongoDB. Nó chỉ kiểm tra **decision logic**, không xác nhận driver gửi lại commit với cùng `lsid/txnNumber` hay Spring transaction manager khởi tạo session đúng. Những điều đó vẫn cần integration/fault-injection tests.

## 18. Observability: log và metrics phải phân biệt hai loại retry

Nếu hệ thống chỉ ghi `"transaction retry"` cho mọi tình huống, on-call có thể hiểu nhầm sự cố:

- Một đợt write conflict làm **transaction attempts** tăng.
- Một đợt network bất ổn khi commit làm **commit retries** tăng.
- Hai vấn đề có hậu quả, ngưỡng cảnh báo và cách sửa khác nhau.

### 18.1. Các metrics nên có

| Metric | Ý nghĩa |
| --- | --- |
| `transaction_attempts_total` | Số lần bắt đầu transaction attempt |
| `transaction_body_retries_total` | Số lần quyết định chạy lại toàn body do transient errors |
| `transaction_commit_retries_total` | Số lần thử lại commit trên transaction cũ |
| `transaction_commit_unknown_total` | Số lần nhận kết quả commit chưa xác định |
| `transaction_commit_unknown_unresolved` | Số operation cần reconciliation |
| `transaction_aborts_total` | Số attempt bị abort, phân loại nguyên nhân |
| `transaction_duration_seconds` | Tổng thời gian từ mở transaction tới kết thúc attempt |
| `transaction_commit_latency_seconds` | Chi phí xử lý commit/acknowledgment |
| `transaction_retry_budget_exhausted_total` | Số lần cạn budget theo pha |
| `transaction_reconciliation_age_seconds` | Tuổi của các operation pending confirmation |
| `duplicate_operation_key_total` | Tần suất client/API retry với operation ID đã tồn tại |

Không gắn operation ID/user ID làm **metric label cardinality cao**. Với tracing/log có kiểm soát, có thể ghi correlation ID; với metrics, dùng nhãn nhóm như phase, error label, service, collection, outcome.

### 18.2. Mẫu log có cấu trúc

```json
{
  "event": "mongo_transaction_retry",
  "operationType": "wallet_transfer",
  "operationRef": "safe-correlation-id",
  "phase": "COMMIT",
  "errorLabel": "UnknownTransactionCommitResult",
  "action": "RETRY_SAME_COMMIT",
  "transactionAttempt": 1,
  "commitAttempt": 2,
  "outcome": "UNCONFIRMED"
}
```

Không log số tài khoản thực, token, credential, payload chứa PII hoặc dữ liệu thô của session theo cách tạo rủi ro bảo mật. `operationRef` là mã theo dõi an toàn thay vì thông tin thanh toán nhạy cảm.

### 18.3. Cảnh báo hữu ích cho vận hành

- Tỉ lệ TTE tăng: kiểm tra write conflicts, giao dịch kéo dài, lock contention, election và kiểu truy cập hot documents.
- Tỉ lệ UTCR tăng: kiểm tra network giữa client và MongoDB, commit latency, write concern timeout, election và server logs.
- Pending reconciliation tăng: kiểm tra job xử lý, dữ liệu ledger, tình trạng idempotency và sự cố khẳng định outcome.
- Duplicate operation IDs tăng đột biến: kiểm tra retry của gateway/client và user UX; không tự xem tất cả duplicates là tấn công.
- Transaction duration tăng: giảm số thao tác trong transaction, tối ưu index, tránh external calls.

## 19. Chẩn đoán những tình huống thực tế

### 19.1. “Tôi thấy MongoWriteException trong body, có nên retry?”

Trước tiên xác định:

1. Lỗi có nhãn `TransientTransactionError` không?
2. Transaction attempt hiện tại còn hiệu lực không hay server đã abort?
3. Có business side effect ngoài MongoDB nào chạy rồi không?
4. Có retry budget và operation ID ổn định không?

Nếu lỗi là duplicate key của operation ID, cần kiểm tra idempotency. Nếu lỗi có TTE theo driver, retry **toàn body** trong transaction mới. Không quyết định chỉ từ tên class exception.

### 19.2. “Commit timeout; tôi thấy chưa có transfer record trên secondary”

Không được khẳng định transaction thất bại. Secondary có thể lag, và commit vẫn có thể đã thành công. Giữ `COMMIT_UNKNOWN`, ưu tiên retry commit cùng session nếu còn phù hợp; nếu không còn session, reconcile trên đường đọc có độ mới/read concern phù hợp và dựa vào operation ID, không tự dùng một lần read âm tính làm bằng chứng abort.

### 19.3. “@Transactional method chạy một lần, sao người dùng bị trừ hai lần?”

Kiểm tra các tầng ngoài Spring transaction:

- API gateway có retry POST khi timeout không?
- Client có tự retry với một operation ID **mới** không?
- Có logic service bắt mọi exception rồi gọi lại method không?
- Có hai application instances xử lý cùng request không?
- Unique key và request fingerprint đã được lưu/đối chiếu chưa?

Một transaction atomically committed **hai lần ở hai request khác nhau** vẫn có thể là lỗi nghiệp vụ nếu idempotency key không được áp dụng.

### 19.4. “Tôi thêm @Retryable quanh @Transactional, lỗi commit giảm nhưng ledger bị trùng”

Đây là dấu hiệu có thể đang retry **toàn business** sau commit unknown. Cần kiểm tra:

- Retry advice bọc ranh giới transaction thế nào.
- Lỗi commit có `UnknownTransactionCommitResult` và đã được phân loại chưa.
- Mỗi lần callback có tạo operation ID mới không.
- Có side effect ngoài transaction trong callback không.

Khắc phục ở **ranh giới commit và idempotency**, không chỉ giảm số lần retry.

### 19.5. “withTransaction vẫn ném exception dù driver có retry”

Retry không phải cam kết luôn thành công. Các lý do có thể gồm:

- Cạn retry budget/deadline của helper.
- Lỗi không transient như validation, duplicate key hoặc business exception.
- Server/network chưa phục hồi.
- Transaction vượt resource/time limits.
- Commit outcome vẫn unknown.

Không “sửa” bằng một vòng `while(true)` bên ngoài `withTransaction`. Hãy phân loại exception và xác định trạng thái cuối có thể chứng minh, rồi chuyển sang reconciliation khi cần.

### 19.6. “Dữ liệu ví nhất quán, nhưng email gửi hai lần”

MongoDB transaction có thể đã retry body sau TTE, và email được gửi **trong callback** ở mỗi lần. Cần chuyển event phát email vào **outbox record cùng transaction** và để dispatcher/consumer idempotent xử lý. Không thể rollback email đã gửi chỉ vì transaction database abort.

### 19.7. “Abort gọi xong cũng lỗi”

`abortTransaction` là thao tác cleanup tốt nhất có thể. Trong sự cố mạng/election, abort cũng có thể thất bại; không để lỗi abort phụ che toàn bộ thông tin của lỗi gốc mà không log. Nếu body đã bị abort theo thông tin đủ tin cậy, retry attempt mới theo TTE; nếu outcome commit chưa xác định, **không gọi abort rồi khẳng định transaction đã rollback**.

## 20. Checklist code review trước khi đưa retry vào production

### 20.1. Transaction và session

1. **Deployment phù hợp:** MongoDB chạy dưới replica set/sharded cluster hỗ trợ transactions, không nhầm với standalone.
2. **Đúng session:** các thao tác trong body tham gia **cùng transaction/session**; Spring repository và `MongoTemplate` cùng factory/session binding.
3. **Đúng ranh giới:** biết transaction bắt đầu và commit ở đâu, nhất là với proxy `@Transactional`.
4. **Đúng transaction options:** read preference, read concern, write concern, timeout đáp ứng hợp đồng.
5. **Không kéo dài:** transaction không chờ HTTP, gửi email hoặc external API.
6. **Không trộn clients:** một Spring transaction không tự bao bọc client/factory khác.
7. **Có cleanup:** abort/close session đúng cách khi body lỗi; không abort để “chứng minh” một commit unknown đã thất bại.

### 20.2. Retry classification

8. **Có phân loại pha:** lỗi ở body hay commit?
9. **Có kiểm tra label:** `TransientTransactionError` và `UnknownTransactionCommitResult` được xử lý khác nhau.
10. **TTE trong body:** retry toàn body trên **transaction attempt mới** sau khi cleanup.
11. **UTCR khi commit:** retry **commit trên session/transaction hiện tại**, không gọi lại body.
12. **Lỗi business/schema:** dừng ngay; không loop vô hạn.
13. **Retry có giới hạn:** attempts, overall deadline và backoff/jitter hợp lý.
14. **Commit unknown hết budget:** giữ `PENDING_CONFIRMATION`, không giả định abort.
15. **Không retry HTTP mù quáng:** gateway/client/service phải chia sẻ idempotency key.

### 20.3. Dữ liệu và hậu quả nghiệp vụ

16. **Operation ID ổn định:** cùng yêu cầu business dùng lại cùng key qua mọi attempt/request.
17. **Unique key phù hợp:** tránh double-apply và rò rỉ tenant.
18. **Payload fingerprint:** cùng ID nhưng nội dung khác phải báo conflict.
19. **No external side effects in callback:** dùng outbox và consumer deduplication.
20. **Conditional write:** đủ số dư, đúng tenant, expected version, không chỉ dựa trên read đầu transaction.
21. **Kiểm tra số tiền:** tránh overflow, âm bất hợp lệ, sai đơn vị tiền.
22. **Reconciliation durable:** có thể tra cứu theo operation ID sau restart.
23. **Phân biệt confirmed/unknown:** response HTTP và audit không nói dối về commit.

### 20.4. Validation và vận hành

24. **Test atomicity:** sau lỗi giữa các bước không có cập nhật một phía.
25. **Test TTE:** callback được phép chạy nhiều lần, business outcome chỉ một lần.
26. **Test UTCR:** commit retry không lặp body, kể cả khi ACK bị mất.
27. **Test idempotency request:** cùng operation ID trả kết quả ổn định hoặc conflict có chủ đích.
28. **Không test trên production:** failpoint, election, drop collection chỉ ở cluster test.
29. **Theo dõi riêng:** transaction attempts, commit retries, unknown outcomes, timeouts, reconciliation age.
30. **Rollout có kiểm soát:** feature flag/monitoring khi thay chính sách retry hoặc transaction manager.

## 21. Ma trận quyết định nhanh

| Quan sát | Hành động đúng | Hành động sai cần tránh |
| --- | --- | --- |
| Write conflict trong body, server/driver báo `TransientTransactionError` | Abort/cleanup và **retry whole transaction** trong attempt mới | Chỉ retry statement bị conflict trong transaction đã abort |
| `commitTransaction` bị mất ACK và báo `UnknownTransactionCommitResult` | **Retry commit trên cùng session/txn identity** | Chạy lại debit/credit trên transaction mới |
| Commit vẫn unknown sau deadline | `PENDING_CONFIRMATION`, reconciliation bằng operation ID | Tuyên bố thất bại chắc chắn, khuyến khích operation ID mới |
| Duplicate transfer operation ID | Đối chiếu payload và trạng thái đã commit | Coi là lỗi transient và tạo transfer khác |
| MongoDB validation error | Sửa request/schema/migration | Retry y nguyên vô hạn |
| API gateway retry POST sau timeout | Dùng cùng idempotency key và kiểm tra ledger | Mỗi request tạo operation ID mới |
| Callback chạy lại sau TTE | Bảo đảm callback chỉ làm việc có thể rollback/idempotent | Gửi email hoặc gọi payment bên thứ ba trực tiếp |
| Spring `@Transactional` method trả về trong body | Nhớ commit xảy ra tại interceptor sau body | Bắt lỗi commit chỉ bằng try/catch bên trong body |
| Không có replica set đủ điều kiện | Cấu hình topology/transaction support trước | Coi transaction manager bean là đủ |
| Test chỉ assert response service thành công | Test BSON và invariant sau commit/abort | Tuyên bố đã kiểm thử retry commit mà chưa fault injection |

## 22. Bài tập thực hành

Một dịch vụ giữ chỗ có collection `seats` và `reservations`. Mỗi yêu cầu đặt vé mang một `reservationId` do ứng dụng bảo đảm ổn định; người dùng có thể retry HTTP do mạng chập chờn.

### Bài tập 1 — Phân loại lỗi

Xét từng tình huống:

1. Transaction đã giảm `availableSeats`, nhưng thao tác thêm reservation nhận `TransientTransactionError` do write conflict.
2. Các lệnh trong body thành công; `commitTransaction` bị disconnect, driver gắn `UnknownTransactionCommitResult`.
3. Commit lần thứ hai vẫn có `UnknownTransactionCommitResult` và overall deadline đã hết.
4. Reservation ID bị duplicate key.
5. Bộ lọc `availableSeats >= 1` không match.
6. HTTP POST bị timeout **sau khi commit thực tế đã thành công**.

Với mỗi tình huống, hãy xác định:

- Body đã được xác nhận abort hay commit còn chưa rõ?
- Nên retry toàn transaction, retry commit hay dừng/reconcile?
- `reservationId` có phải giữ nguyên không?
- API nên trả thông điệp nào để không tạo double booking?

**Gợi ý:**

| Tình huống | Quyết định |
| --- | --- |
| 1 | Abort/cleanup attempt và retry **toàn body** nếu TTE và còn budget |
| 2 | Retry **commit của cùng transaction**, giữ session |
| 3 | `PENDING_CONFIRMATION` và reconcile, không gọi lại đặt chỗ mù quáng |
| 4 | Kiểm tra idempotency/payload; không tự đổi reservation ID |
| 5 | Lỗi nghiệp vụ hết chỗ; không có lý do retry liên tục |
| 6 | Retry HTTP với **cùng reservationId**, tra kết quả đã commit |

### Bài tập 2 — Tìm lỗi trong đoạn code

```java
// CÓ LỖI: không phân biệt commit unknown với transaction abort.
for (int i = 0; i < 5; i++) {
    try {
        createReservation(UUID.randomUUID().toString());
        break;
    } catch (Exception e) {
        Thread.sleep(100);
    }
}
```

Chỉ ra ít nhất năm lỗi:

1. Tạo `reservationId` khác nhau ở mỗi attempt.
2. Retry mọi exception kể cả lỗi nghiệp vụ.
3. Không phân loại body/commit.
4. Không phân biệt `TransientTransactionError` với `UnknownTransactionCommitResult`.
5. Không có trạng thái cần reconciliation khi commit outcome unknown.
6. Không có backoff theo loại lỗi, overall deadline và quản lý InterruptedException đúng.
7. Nếu `createReservation` gửi email trong transaction callback, có thể gửi nhiều lần.

Hãy viết **pseudocode** đúng với **hai vòng lặp retry riêng**, không chỉ thay `UUID.randomUUID()` bằng ID cố định.

### Bài tập 3 — Thiết kế Spring @Transactional

Tạo:

- `ReservationWriter` với `@Transactional` quản lý một lần insert reservation và decrement inventory.
- `ReservationCoordinator` nhận idempotency key và quyết định trả kết quả, retry transient hoặc pending confirmation.
- `MongoTransactionManager` gắn đúng `MongoDatabaseFactory`.
- Unique index trên `tenantId + reservationId`.
- Một outbox event `ReservationConfirmed` được ghi **trong cùng transaction**.

Giải thích:

1. Vì sao bắt lỗi commit trong thân method `ReservationWriter` chưa đủ?
2. Vì sao `@Retryable` đặt tùy ý ngoài `@Transactional` có nguy cơ replay body khi commit unknown?
3. Nếu buộc phải retry commit theo protocol, chỗ nào giữ được **cùng ClientSession**?
4. Nếu process chết sau khi gửi commit mà chưa có ACK, coordinator lấy thông tin đối soát từ đâu?

### Bài tập 4 — Kiểm thử fault injection

Trong replica set test riêng:

1. Seed 2 ví hoặc 5 ghế còn trống.
2. Test transaction success và kiểm tra tổng/invariant.
3. Tạo lỗi TTE đúng trong body, xác minh body có thể chạy lại và chỉ có một record commit.
4. Tạo lỗi UTCR **đúng lúc commit**, đếm retry commit và xác minh body không bị chạy lại chỉ vì UTCR.
5. Cố tình làm commit outcome không giải quyết được trong retry budget; assert ứng dụng không báo failed chắc chắn.
6. Thử HTTP retry với cùng operation ID và với một operation ID mới để thấy tầm quan trọng của idempotency.
7. Bật outbox dispatcher idempotent và chứng minh event không gửi trùng về mặt hiệu ứng nghiệp vụ.

**Không chạy failpoint hoặc mô phỏng election trên production**; thiết lập môi trường cô lập có quyền phù hợp, cleanup fault injection chắc chắn và đo thời gian/trace.

### Bài tập 5 — Sự cố production

Một đêm, số liệu cho thấy:

```text
transaction_body_retries_total     tăng nhẹ
transaction_commit_retries_total   tăng mạnh
transaction_commit_unknown_total  tăng mạnh
duplicate_operation_key_total     tăng sau vài phút
```

Nhận định được ưu tiên:

- Kiểm tra network/commit latency, write concern, election và log driver/server.
- Kiểm tra client/gateway có bắt đầu retry toàn HTTP requests sau timeout không.
- Kiểm tra mọi request có dùng **cùng operationId** khi retry không.
- Kiểm tra reconciliation có tồn đọng `PENDING_CONFIRMATION` không.
- Không tăng số lần **whole-transaction retry** chỉ để làm giảm tổng exception ở commit.

## 23. Tài liệu tham khảo

- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/): phạm vi và điều kiện dùng multi-document transactions.
- MongoDB Manual — [Transactions and Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/): quy tắc retry transaction và commit trong ứng dụng.
- MongoDB Manual — [Transactions and Sessions](https://www.mongodb.com/docs/manual/core/transactions/): session/transaction identity, write concerns và limitations.
- MongoDB Manual — [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): phân biệt retryable single writes với transaction.
- MongoDB Java Driver — [Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/): `ClientSession`, `withTransaction`, transaction options và error handling.
- MongoDB Java Driver — [ClientSession API](https://mongodb.github.io/mongo-java-driver/5.6/apidocs/mongodb-driver-sync/com/mongodb/client/ClientSession.html): session methods/transaction callback; kiểm tra phiên bản driver dự án đang dùng.
- Spring Data MongoDB — [Client Session & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, session và transaction integration.
- Spring Data MongoDB — [MongoTransactionManager API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/MongoTransactionManager.html): cách Spring quản lý session/commit.
- Spring Framework — [Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction proxy, `@Transactional` và `TransactionTemplate`.

## Ghi nhớ

**Lỗi trong transactional body có nhãn `TransientTransactionError` thường đòi hỏi retry toàn bộ transaction trên một attempt mới. Lỗi tại `commitTransaction` có nhãn `UnknownTransactionCommitResult` nghĩa là client chưa biết commit thành công hay thất bại, vì vậy cần retry riêng commit của transaction cũ, không thực hiện lại business body.** Khi không thể xác nhận commit trước deadline, trả trạng thái chưa xác định và reconciliation theo operation ID. `ClientSession.withTransaction` hỗ trợ retry theo driver semantics; `@Transactional`/`TransactionTemplate` không được tự coi là tương đương một retry policy hoàn chỉnh. Để an toàn từ database tới HTTP, cần idempotency key, unique constraint, outbox cho side effects, retry có giới hạn, kiểm thử trên replica set thật và giám sát riêng **body retries** với **commit retries**.

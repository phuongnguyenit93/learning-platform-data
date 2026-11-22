# Mất kết nối khi COMMIT và trạng thái kết quả chưa xác định

Khi một ứng dụng gửi `COMMIT` đến cơ sở dữ liệu, nó thường chờ phản hồi xác nhận transaction đã hoàn tất. Nhưng kết nối mạng có thể bị đứt đúng lúc server đang xử lý commit hoặc sau khi server đã commit nhưng trước khi phản hồi đến được client. Khi đó, ứng dụng nhận lỗi kết nối và không biết transaction đã commit hay chưa.

Đây là tình huống **kết quả chưa xác định (unknown outcome)**. Lỗi kết nối ở phía client không tự chứng minh transaction đã rollback. Server có thể đã ghi nhận commit thành công, trong khi client chỉ mất phản hồi. Nếu ứng dụng gửi lại một thao tác không idempotent như chuyển tiền, tạo đơn hàng hoặc trừ tồn kho bằng một request mới, tác dụng có thể xảy ra hai lần.

Để xử lý an toàn, ứng dụng cần phân biệt lỗi thực thi với lỗi mất xác nhận, lưu một mã định danh duy nhất cho yêu cầu nghiệp vụ và có thể tra cứu kết quả sau khi kết nối lại. Bài học này trình bày chuỗi sự kiện khi commit, cách khôi phục trạng thái, thiết kế idempotency và những điểm cần lưu ý với transaction phân tán.

## 1. Vì sao mất kết nối lúc COMMIT tạo ra sự mơ hồ?

Một transaction thông thường có thể diễn ra theo trình tự:

1. Client mở kết nối và bắt đầu transaction.
2. Client gửi các câu lệnh đọc và ghi.
3. Client gửi `COMMIT`.
4. Database kiểm tra các điều kiện cần thiết, hoàn tất commit và bảo đảm tính bền vững theo cấu hình của hệ quản trị.
5. Database gửi phản hồi thành công về client.
6. Client nhận phản hồi và trả kết quả cho người gọi.

Điểm khó là bước 4 và bước 5 xảy ra ở hai phía khác nhau. Việc database đã hoàn tất commit và việc client đã nhận được xác nhận là hai sự kiện riêng biệt.

Hãy xét một giao dịch chuyển 100.000 đồng:

```text
Client                         Database
  |                                |
  | BEGIN                          |
  |------------------------------->|
  | UPDATE account ...             |
  |------------------------------->|
  | COMMIT                         |
  |------------------------------->|
  |                         Commit hoàn tất
  |                         Gửi ACK thành công
  |<-------------------------------|
  X Kết nối bị đứt trước khi ACK đến
```

Database đã commit, nhưng client nhận lỗi mạng. Nếu client kết luận rằng thao tác thất bại rồi gửi một yêu cầu chuyển tiền mới, tài khoản có thể bị trừ thêm lần nữa.

Ngược lại, nếu kết nối đứt trước khi server nhận được `COMMIT`, transaction có thể bị rollback khi server phát hiện session đã mất. Client cũng có thể không biết chính xác thời điểm server nhận lệnh. Vì vậy, cùng một loại lỗi kết nối có thể tương ứng với những kết quả database khác nhau.

## 2. Ba trạng thái cần phân biệt

Khi client không nhận được phản hồi cuối cùng, có thể phân loại tình huống theo trạng thái thực tế ở database:

| Trạng thái thực tế | Điều đã xảy ra | Client có thể kết luận gì? |
| --- | --- | --- |
| Chưa commit và transaction đã rollback | Server chưa hoàn tất commit; thay đổi trong transaction bị hủy | Thao tác không được commit nếu có bằng chứng rollback hoặc tra cứu xác nhận |
| Commit đã hoàn tất | Database đã ghi nhận transaction; phản hồi bị mất trên đường về | Thao tác đã thành công dù client nhận lỗi |
| Chưa xác định được | Server hoặc mạng chưa cho phép xác nhận kết quả; transaction có thể còn đang xử lý hoặc trạng thái chưa tra cứu được | Client phải giữ trạng thái pending/unknown và phục hồi bằng cách tra cứu hoặc gửi lại cùng mã yêu cầu |

Trạng thái thứ ba là cách client mô tả mức độ hiểu biết của mình, không nhất thiết là một trạng thái transaction nội bộ mà mọi database đều lưu. Với một transaction cục bộ, database cuối cùng sẽ xác định commit hoặc rollback. Nhưng trong thời gian client mất kết nối, ứng dụng chưa có đủ thông tin để khẳng định kết quả.

Không nên ánh xạ mọi exception xảy ra trong `commit()` thành “transaction chắc chắn rollback”. Cũng không nên trả “thành công” chỉ vì client đã gửi hết dữ liệu. Nếu không nhận được xác nhận và chưa tra cứu được kết quả, phản hồi đúng là chưa xác định.

## 3. Vì sao gọi ROLLBACK sau lỗi COMMIT không giải quyết được?

Khi `COMMIT` trả về lỗi do kết nối đã mất, ứng dụng có thể thử gọi `ROLLBACK`. Nhưng nếu session đã đóng hoặc socket hỏng, lệnh rollback có thể cũng không đến được server. Ngay cả khi lời gọi rollback trả lỗi, điều đó không cho biết transaction trước đó đã commit hay chưa.

Ví dụ:

```java
try {
    connection.commit();
} catch (SQLException commitError) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        commitError.addSuppressed(rollbackError);
    }

    throw commitError;
}
```

Đoạn code trên có thể hữu ích để dọn dẹp khi connection vẫn còn hoạt động, nhưng nó không chứng minh được trạng thái commit nếu kết nối đã đứt. Khi server đã commit và gửi phản hồi bị mất, một lệnh rollback đến sau không thể đảo ngược transaction đã hoàn tất.

Trong JDBC, nếu connection gặp lỗi mạng trong lúc commit, ứng dụng nên coi connection đó là không còn đáng tin cậy, loại bỏ nó khỏi connection pool và không tái sử dụng session đó. Việc gọi `close()` hoặc `rollback()` trên connection hỏng không thay thế cho bước phục hồi bằng một kết nối mới.

## 4. Phân biệt lỗi trước COMMIT và lỗi trong COMMIT

Vị trí xảy ra lỗi cung cấp thông tin hữu ích, nhưng không phải lúc nào cũng đủ để kết luận kết quả.

### Lỗi khi đang thực hiện câu lệnh trước COMMIT

Nếu một câu `UPDATE` trả về lỗi rõ ràng trước khi ứng dụng gửi `COMMIT`, transaction thường chưa được commit. Ứng dụng có thể rollback theo trạng thái của session. Tuy nhiên, cần phân biệt lỗi statement với lỗi kết nối: nếu kết nối bị mất ngay sau khi gửi statement, server có thể đã thực thi statement dù client chưa nhận phản hồi. Khi transaction chưa commit và session bị đóng, server sẽ xử lý rollback theo semantics của engine.

### Lỗi khi gửi hoặc chờ COMMIT

Đây là trường hợp mơ hồ nhất. Client có thể không biết:

- Lệnh `COMMIT` chưa đến server.
- Server nhận lệnh nhưng chưa hoàn tất.
- Server đã commit và phản hồi bị mất.
- Server gặp lỗi trong quá trình hoàn tất transaction.

Client cần dùng mã yêu cầu nghiệp vụ để tra cứu hoặc thử lại an toàn. Không nên tạo một request ID mới chỉ vì kết nối bị ngắt.

### Nhận được xác nhận commit thành công

Nếu driver trả về thành công từ `commit()` và không có lỗi ở tầng ứng dụng sau đó, client có thể coi transaction đã commit theo hợp đồng của database và cấu hình durability. Nếu phản hồi HTTP hoặc thông báo đến người dùng bị mất sau đó, đây vẫn là bài toán retry cùng một request ID ở tầng API.

## 5. Idempotency key: định danh một yêu cầu nghiệp vụ

Idempotency là tính chất một thao tác có thể được gửi lại mà không làm tác dụng nghiệp vụ xảy ra thêm lần nữa. Một **idempotency key** là mã duy nhất đại diện cho một yêu cầu logic, chẳng hạn một lần thanh toán hoặc một lệnh chuyển tiền.

Client tạo mã này một lần cho yêu cầu ban đầu, lưu lại và dùng lại mã đó cho mọi lần retry của cùng yêu cầu. Server dùng mã để nhận biết yêu cầu đã được xử lý hay chưa.

Ví dụ, thay vì gửi:

```json
{
  "fromAccount": 100,
  "toAccount": 200,
  "amount": 50000
}
```

ứng dụng gửi thêm một mã yêu cầu:

```json
{
  "requestId": "transfer-7f4d9a2c",
  "fromAccount": 100,
  "toAccount": 200,
  "amount": 50000
}
```

Nếu phản hồi bị mất, client gửi lại cùng `requestId`. Server tra cứu hoặc cố ghi nhận mã này trong database. Nếu giao dịch trước đã commit, server trả kết quả đã lưu. Nếu giao dịch trước chưa commit và đã rollback, lần gửi lại có thể thực hiện nghiệp vụ. Nhờ vậy, retry không tạo một lần chuyển tiền thứ hai.

Idempotency key phải đại diện cho cùng một nội dung yêu cầu. Nếu client tái sử dụng cùng mã nhưng thay đổi số tiền hoặc tài khoản đích, server nên phát hiện payload không khớp và từ chối thay vì trả kết quả của yêu cầu cũ.

## 6. Lưu mã yêu cầu và kết quả trong cùng transaction

Một cách triển khai phổ biến là tạo bảng lưu các thao tác đã nhận:

```sql
CREATE TABLE transfer_request (
    request_id       VARCHAR(80) PRIMARY KEY,
    payload_hash     VARCHAR(128) NOT NULL,
    from_account_id  BIGINT NOT NULL,
    to_account_id    BIGINT NOT NULL,
    amount           DECIMAL(18, 2) NOT NULL,
    status            VARCHAR(20) NOT NULL,
    result_code       VARCHAR(40),
    from_balance_after DECIMAL(18, 2),
    to_balance_after   DECIMAL(18, 2),
    created_at        TIMESTAMP NOT NULL,
    CONSTRAINT ck_transfer_request_amount CHECK (amount > 0),
    CONSTRAINT ck_transfer_request_status
        CHECK (status IN ('PROCESSING', 'COMPLETED', 'REJECTED'))
);
```

`request_id` là primary key nên database không cho phép hai transaction cùng lưu hai thao tác có cùng mã. `payload_hash` hoặc các trường nghiệp vụ được lưu kèm để kiểm tra client có dùng lại mã cho nội dung giống hệt hay không.

Một luồng xử lý khái quát:

```sql
BEGIN;

-- Bước 1: ghi nhận request ID duy nhất.
INSERT INTO transfer_request (
    request_id, payload_hash,
    from_account_id, to_account_id, amount,
    status, created_at
)
VALUES (
    :request_id, :payload_hash,
    :from_id, :to_id, :amount,
    'PROCESSING', CURRENT_TIMESTAMP
);

-- Bước 2: cập nhật tài khoản theo quy tắc khóa và kiểm tra số dư.
UPDATE account
SET balance = balance - :amount
WHERE account_id = :from_id
  AND balance >= :amount;
-- Ứng dụng phải xác nhận đúng một hàng được cập nhật.

UPDATE account
SET balance = balance + :amount
WHERE account_id = :to_id;
-- Ứng dụng phải xác nhận đúng một hàng được cập nhật.

-- Bước 3: lưu kết quả cuối cùng của request.
UPDATE transfer_request
SET status = 'COMPLETED',
    result_code = 'SUCCESS'
WHERE request_id = :request_id;

COMMIT;
```

Các câu lệnh minh họa cần được bao bọc bởi xử lý lỗi đầy đủ: nếu không trừ được tiền, không cộng được tiền, hoặc không ghi được kết quả, transaction phải rollback. Trong hệ thống thật, cần khóa tài khoản theo thứ tự nhất quán, kiểm tra cả hai tài khoản tồn tại, bảo đảm số tiền hợp lệ và ghi ledger trong cùng transaction nếu ledger là một phần của nghiệp vụ.

Điểm quan trọng là **bản ghi idempotency, thay đổi nghiệp vụ và kết quả trả về được commit nguyên tử trong cùng transaction**. Nếu transaction rollback, cả bản ghi request và các thay đổi tài khoản đều bị hủy. Nếu transaction commit, cả kết quả và mã yêu cầu đều tồn tại.

Trong ví dụ, trạng thái `PROCESSING` được ghi bên trong transaction rồi chuyển sang `COMPLETED` trước commit. Transaction khác thông thường không nhìn thấy trạng thái trung gian chưa commit. Sau commit, nó nhìn thấy kết quả cuối cùng. Không nên commit một hàng `PROCESSING` riêng rồi mới thực hiện nghiệp vụ ở transaction khác trừ khi có thiết kế xử lý lease, timeout và recovery cho các request bị bỏ dở.

## 7. Xử lý request ID đã tồn tại

Khi client gửi lại cùng `request_id`, câu INSERT vào bảng idempotency sẽ gặp xung đột primary key nếu yêu cầu trước đã commit. Ứng dụng xử lý theo các bước:

1. Rollback transaction hiện tại nếu statement lỗi làm transaction ở trạng thái không thể tiếp tục.
2. Mở transaction hoặc connection mới.
3. Đọc bản ghi `transfer_request` theo `request_id` từ nguồn dữ liệu có thể xác nhận trạng thái mới nhất, thường là primary database.
4. So sánh payload hash hoặc các trường nghiệp vụ. Nếu nội dung khác, trả lỗi sử dụng lại idempotency key sai cách.
5. Nếu nội dung khớp và bản ghi có kết quả cuối, trả lại chính kết quả đã lưu mà không chạy lại thao tác chuyển tiền.

Nếu transaction đầu tiên chưa commit, INSERT trùng có thể phải chờ kết quả của transaction đang giữ khóa duy nhất. Sau đó, tùy kết quả:

- Nếu transaction đầu tiên commit, lần INSERT sau nhận xung đột duy nhất và có thể đọc kết quả đã lưu.
- Nếu transaction đầu tiên rollback, lần INSERT sau có thể thành công và thực hiện nghiệp vụ.
- Nếu database vẫn chưa truy cập được hoặc thao tác kiểm tra bị timeout, client tiếp tục giữ trạng thái unknown/pending và thử tra cứu lại sau.

Không nên đọc kết quả từ một read replica có độ trễ rồi kết luận request chưa tồn tại. Replica có thể chưa nhận được transaction vừa commit. Khi cần xác định kết quả của một request vừa xảy ra, hãy đọc từ primary hoặc dùng cơ chế đọc nhất quán mạnh được hệ quản trị cung cấp.

## 8. Không tái sử dụng idempotency key cho payload khác

Idempotency key đại diện cho một ý định nghiệp vụ cụ thể. Server nên lưu một fingerprint của request đã chuẩn hóa, bao gồm các trường có ảnh hưởng đến tác dụng như tài khoản nguồn, tài khoản đích, số tiền, loại tiền và loại thao tác.

Ví dụ:

| request_id | payload | Kết quả |
| --- | --- | --- |
| `transfer-A` | Chuyển 50.000 từ 100 sang 200 | Được xử lý lần đầu |
| `transfer-A` | Gửi lại đúng yêu cầu trên | Trả lại kết quả đã lưu |
| `transfer-A` | Chuyển 80.000 từ 100 sang 300 | Từ chối vì cùng key nhưng payload khác |
| `transfer-B` | Chuyển 80.000 từ 100 sang 300 | Một yêu cầu nghiệp vụ mới |

Fingerprint cần được tạo từ biểu diễn chuẩn hóa, tránh hai payload có thứ tự thuộc tính JSON khác nhau nhưng cùng ý nghĩa lại bị coi là khác. Không đưa dữ liệu nhạy cảm không cần thiết vào log. Có thể lưu các trường quan trọng riêng và hash phần nội dung chuẩn hóa.

Phạm vi duy nhất của key cũng cần rõ ràng. Có hệ thống dùng unique key toàn cục; hệ thống khác dùng cặp `(tenant_id, request_id)` hoặc `(client_id, request_id)`. Mục tiêu là hai người dùng khác nhau không vô tình chiếm cùng key nếu key chỉ duy nhất trong phạm vi client.

## 9. Lưu cả kết quả nghiệp vụ để retry trả cùng phản hồi

Chỉ biết request đã tồn tại chưa phải lúc nào cũng đủ. Client cần nhận lại kết quả tương đương với lần xử lý ban đầu, ví dụ:

- Mã giao dịch được tạo.
- Trạng thái thanh toán.
- Số dư sau khi chuyển.
- Mã đơn hàng.
- Mã lỗi nghiệp vụ đã được xác định và lưu.

Vì vậy, bảng idempotency có thể lưu response code và response body đã chuẩn hóa, hoặc lưu khóa tham chiếu đến bản ghi kết quả nghiệp vụ. Khi retry, server trả lại kết quả đó thay vì tính toán lại trên trạng thái hiện tại.

Ví dụ, lần đầu chuyển tiền thành công và trả `transfer_id = 987`. Client mất kết nối sau commit. Khi gửi lại cùng key, server trả lại `transfer_id = 987`, không tạo transfer ID mới.

### Có lưu kết quả từ chối hay không?

Điều này phụ thuộc semantics của API:

- Nếu yêu cầu với cùng key phải luôn có cùng kết quả, có thể lưu cả kết quả từ chối nghiệp vụ như “không đủ số dư”. Lần retry cùng key sẽ trả lại cùng kết quả, kể cả sau khi tài khoản được nạp thêm tiền.
- Nếu chỉ muốn lưu những yêu cầu đã thực hiện thành công, có thể rollback bản ghi request khi từ chối. Khi đó cùng key có thể được thử lại sau này và kết quả có thể khác.

Hãy chọn một quy tắc rõ ràng, ghi trong hợp đồng API và giữ nhất quán. Lỗi tạm thời như database unavailable thường không nên được lưu thành kết quả nghiệp vụ cuối cùng.

## 10. Retry an toàn khác với gửi một request mới

Khi timeout hoặc mất kết nối, client thường có xu hướng tạo request mới. Với thao tác không idempotent, đây là rủi ro lớn.

| Tình huống | Hành vi phù hợp |
| --- | --- |
| Client chưa gửi request nào | Tạo request ID và gửi lần đầu |
| Request đã gửi, nhận xác nhận thành công | Dùng kết quả đã nhận |
| Request đã gửi, mất kết nối trong COMMIT | Giữ nguyên request ID; tra cứu hoặc retry cùng key |
| Request đã gửi, server báo lỗi xác định trước commit | Xử lý theo mã lỗi; chỉ retry nếu lỗi cho phép |
| Không thể truy cập database để tra cứu | Giữ trạng thái unknown/pending, retry tra cứu sau |
| Người dùng thực sự muốn thực hiện một thao tác mới | Tạo request ID mới sau khi xác định đây là ý định mới |

Không thể bảo đảm “exactly once” chỉ bằng cách retry mạng. Một thông điệp có thể được gửi nhiều lần; điều cần bảo đảm là nhiều lần gửi cùng một ý định chỉ tạo một tác dụng nghiệp vụ trong database. Idempotency key cùng unique constraint và transaction giúp xây dựng ngữ nghĩa đó ở cấp ứng dụng.

## 11. Trạng thái API khi kết quả chưa xác định

API nên phân biệt trạng thái request với trạng thái kết nối của client. Nếu client không nhận được phản hồi commit, không nên trả một thông báo khẳng định “đã thất bại” khi chưa biết kết quả.

Một mô hình trạng thái có thể là:

```text
RECEIVED
   |
   v
PROCESSING
   |
   +------> COMPLETED
   |
   +------> REJECTED
   |
   +------> UNKNOWN (client chưa xác nhận được kết quả)
```

`UNKNOWN` thường là trạng thái hiểu biết ở phía client hoặc gateway. Bản ghi database đã commit có thể đã là `COMPLETED`; bản ghi chưa commit có thể không tồn tại. Khi client tra cứu bằng request ID, server sẽ trả trạng thái đã lưu hoặc thông báo chưa tìm thấy và hướng dẫn thử lại cùng key.

API có thể cung cấp endpoint tra cứu:

```http
GET /transfer-requests/transfer-7f4d9a2c
```

Phản hồi minh họa khi đã hoàn tất:

```json
{
  "requestId": "transfer-7f4d9a2c",
  "status": "COMPLETED",
  "transferId": 987,
  "resultCode": "SUCCESS"
}
```

Nếu chưa có bản ghi, không nên vội kết luận transaction trước chắc chắn rollback nếu request cũ có thể vẫn đang được xử lý hoặc dữ liệu đọc đến từ replica trễ. Hệ thống có thể yêu cầu retry cùng key, chờ một khoảng thời gian rồi tra cứu lại, hoặc trả trạng thái pending theo hợp đồng API.

## 12. Tác dụng phụ bên ngoài database và Transactional Outbox

Idempotency record trong database bảo vệ các thay đổi thuộc cùng database transaction. Nhưng nhiều nghiệp vụ còn gửi email, gọi cổng thanh toán, phát sự kiện hoặc cập nhật hệ thống khác. Nếu ứng dụng thực hiện tác dụng phụ trước commit, transaction có thể rollback sau khi email đã gửi. Nếu thực hiện sau commit, ứng dụng có thể bị ngắt kết nối sau commit và trước khi gửi sự kiện.

Transactional Outbox giải quyết khoảng trống giữa cập nhật database và phát sự kiện:

1. Trong cùng transaction, cập nhật dữ liệu nghiệp vụ.
2. Trong cùng transaction, chèn một hàng outbox có event ID duy nhất.
3. Commit cả dữ liệu nghiệp vụ và outbox atomically.
4. Một worker đọc các hàng outbox chưa gửi và phát sự kiện.
5. Worker đánh dấu đã gửi hoặc lưu kết quả gửi theo cơ chế retry.

Ví dụ:

```sql
BEGIN;

UPDATE orders
SET status = 'PAID'
WHERE order_id = :order_id;

INSERT INTO outbox_event(event_id, event_type, aggregate_id, payload, created_at)
VALUES (:event_id, 'OrderPaid', :order_id, :payload, CURRENT_TIMESTAMP);

COMMIT;
```

Nếu commit thành công nhưng phản hồi đến ứng dụng bị mất, dữ liệu đơn hàng và outbox đều đã tồn tại. Nếu transaction rollback, cả hai đều không tồn tại. Worker có thể phát lại event khi cần.

Outbox thường tạo ngữ nghĩa phát ít nhất một lần (at-least-once), vì worker có thể gửi event thành công rồi mất kết nối trước khi đánh dấu đã gửi. Consumer nên dùng `event_id` để deduplicate và xử lý idempotent. Outbox không làm mạng trở nên exactly-once; nó giúp tác dụng database và ý định phát event được lưu nguyên tử, đồng thời làm cho việc retry có thể kiểm soát.

## 13. Gọi dịch vụ thanh toán bên ngoài

Nếu transaction gọi một payment provider, không nên giữ transaction database mở trong suốt thời gian chờ mạng nếu có thể tránh. Một mô hình thường dùng:

1. Tạo payment intent hoặc operation record trong database với request ID duy nhất.
2. Commit trạng thái cần xử lý.
3. Worker gửi yêu cầu đến provider bằng idempotency key ổn định.
4. Worker lưu phản hồi provider và cập nhật trạng thái trong transaction mới.
5. Nếu worker mất kết nối sau khi provider xử lý, gửi lại cùng idempotency key để provider trả lại kết quả của thao tác cũ theo hợp đồng của họ.

Phải kiểm tra chính sách idempotency, thời hạn lưu key và khả năng tra cứu của provider. Không phải mọi API bên ngoài đều hỗ trợ idempotency. Nếu không có, cần thiết kế reconciliation, đối soát hoặc quy trình xử lý thủ công cho những trạng thái không xác định.

## 14. Transaction phân tán và trạng thái in-doubt

Trong transaction cục bộ, kết nối bị mất khi COMMIT thường tạo ra sự mơ hồ cho client. Database sẽ tự phục hồi theo log và cuối cùng xác định transaction đã commit hay rollback.

Trong distributed transaction dùng two-phase commit (2PC/XA), có thêm trạng thái **prepared**. Resource manager có thể đã ghi transaction vào trạng thái prepared và giữ tài nguyên, nhưng chưa nhận được quyết định commit/rollback cuối cùng từ coordinator. Nếu coordinator hoặc mạng gặp sự cố, transaction có thể ở trạng thái in-doubt cho đến khi recovery xác định quyết định.

Quy trình 2PC khái quát:

```text
Coordinator              Resource manager
     |                           |
     |------ PREPARE ------------>|
     |<----- PREPARED ------------|
     |                           |
     | ghi quyết định COMMIT      |
     |------ COMMIT ------------->|
     |<----- ACK -----------------|
```

Nếu coordinator ghi quyết định commit nhưng mất kết nối trước khi resource manager nhận được, recovery cần dùng log của coordinator để gửi lại quyết định. Resource manager giữ trạng thái prepared cho đến khi nhận quyết định hoặc thực hiện quy trình recovery theo cấu hình.

In-doubt trong XA là trạng thái giao dịch phân tán thực sự có thể tồn tại trong resource manager. Nó khác với việc một ứng dụng JDBC cục bộ chỉ không nhận được phản hồi `commit()`. Không nên tự ý force commit hoặc rollback một prepared transaction khi chưa kiểm tra quyết định của coordinator; hành động sai có thể làm các resource manager không nhất quán.

Với XA/JTA, cần có transaction manager, recovery log bền vững, quy trình khởi động lại và giám sát các prepared transaction tồn đọng. Khi vận hành, đối chiếu transaction ID và log coordinator với trạng thái resource manager trước khi xử lý thủ công.

## 15. Ghi log và quan sát để phục hồi

Để điều tra request có kết quả chưa xác định, hệ thống cần ghi đủ thông tin liên kết giữa request, transaction và kết quả database:

- Idempotency key hoặc request ID.
- Tenant/client ID và loại thao tác.
- Hash của payload đã chuẩn hóa.
- Mã transaction hoặc correlation ID nếu có.
- Thời điểm gửi COMMIT, thời điểm nhận lỗi và loại lỗi kết nối.
- Kết quả tra cứu sau khi reconnect.
- ID bản ghi nghiệp vụ đã tạo và kết quả cuối cùng.

Không ghi mật khẩu, token xác thực hoặc dữ liệu thẻ thanh toán nhạy cảm vào log. Dùng ID tham chiếu và thông tin đã giảm thiểu để theo dõi.

Các chỉ số hữu ích gồm số request ở trạng thái unknown/pending, thời gian chưa giải quyết, số lần retry cùng key, số duplicate key được nhận diện và số transaction phân tán ở trạng thái prepared lâu hơn ngưỡng.

## 16. Kiểm thử lỗi mất kết nối khi COMMIT

Một bài kiểm thử thông thường chỉ xác nhận `commit()` trả về thành công chưa đủ để kiểm tra tình huống này. Cần mô phỏng việc mất phản hồi tại những thời điểm khác nhau.

### Kiểm thử commit thành công nhưng ACK bị mất

1. Tạo request có idempotency key cố định.
2. Cho transaction thực hiện thay đổi nghiệp vụ và lưu operation record.
3. Cho database commit thành công.
4. Dùng proxy hoặc fault injection cắt kết nối trước khi phản hồi commit đến client.
5. Xác nhận client ghi nhận kết quả unknown thay vì khẳng định rollback.
6. Gửi lại cùng request ID.
7. Xác nhận server trả lại kết quả đã lưu và tác dụng nghiệp vụ chỉ xảy ra một lần.

### Kiểm thử lệnh COMMIT chưa hoàn tất

1. Tạo request với key cố định.
2. Ngắt kết nối trước khi server nhận được lệnh COMMIT hoặc trước khi transaction có thể hoàn tất.
3. Chờ server phát hiện session mất và xử lý rollback.
4. Kết nối lại, retry cùng request ID.
5. Xác nhận transaction mới có thể thực hiện thao tác đúng một lần.

### Kiểm thử hai request đồng thời dùng cùng key

1. Gửi hai request đồng thời với cùng idempotency key và cùng payload.
2. Xác nhận unique constraint chỉ cho phép một operation record.
3. Xác nhận request còn lại chờ, nhận duplicate hoặc đọc được kết quả đã lưu tùy cách triển khai.
4. Gửi cùng key nhưng payload khác và xác nhận server từ chối.

### Kiểm thử replica lag và dịch vụ ngoài

Nếu có read replica, kiểm thử tình huống primary đã commit nhưng replica chưa đồng bộ; endpoint tra cứu phải tránh kết luận sai rằng request chưa tồn tại. Nếu có outbox hoặc provider thanh toán, kiểm thử việc worker gửi thành công nhưng mất phản hồi trước khi đánh dấu hoàn tất, rồi xác nhận consumer/provider xử lý idempotent.

## 17. Những điểm cần ghi nhớ

- Mất kết nối khi COMMIT không chứng minh transaction đã rollback; server có thể đã commit nhưng phản hồi bị mất.
- Trạng thái unknown là sự không chắc chắn ở phía client. Cần tra cứu bằng một kết nối mới hoặc retry cùng định danh yêu cầu.
- Gọi `ROLLBACK` trên connection hỏng không thể đảo ngược một transaction đã commit và cũng không chứng minh trạng thái cuối.
- Không tạo request ID mới khi retry cùng một ý định nghiệp vụ. Dùng idempotency key ổn định để tránh tác dụng xảy ra hai lần.
- Lưu idempotency key, payload fingerprint, thay đổi nghiệp vụ và kết quả trong cùng transaction để chúng cùng commit hoặc cùng rollback.
- Nếu key đã tồn tại, rollback transaction đang lỗi, đọc kết quả cũ từ nguồn dữ liệu đủ mới và kiểm tra payload có khớp không.
- Lưu response hoặc ID kết quả để retry trả lại kết quả cũ, thay vì thực hiện lại nghiệp vụ.
- Dùng Transactional Outbox cho sự kiện cần phát sau commit; consumer vẫn phải xử lý duplicate event.
- Distributed XA có trạng thái prepared/in-doubt thực sự và cần recovery theo log của coordinator; không force commit/rollback tùy tiện.
- Kiểm thử bằng cách làm mất ACK sau commit, mất kết nối trước commit và gửi trùng request đồng thời để xác nhận tác dụng nghiệp vụ chỉ xảy ra một lần.

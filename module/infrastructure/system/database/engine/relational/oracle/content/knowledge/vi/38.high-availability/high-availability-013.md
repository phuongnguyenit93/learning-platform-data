# Thiết kế ứng dụng chịu mất kết nối, thử lại có giới hạn và chống giao dịch trùng trong Oracle

## 1. Vì sao ứng dụng phải thiết kế cho lỗi kết nối?

Một ứng dụng dùng Oracle Database không thể giả định rằng kết nối luôn tồn tại từ lúc mở session đến lúc trả kết quả. Mạng có thể chập chờn, listener hoặc instance có thể khởi động lại, node RAC có thể gặp sự cố, connection pool có thể giữ một socket đã chết, hoặc client có thể timeout trong khi database vẫn đang xử lý.

Một lỗi kết nối còn tạo ra tình huống khó hơn lỗi SQL thông thường: **client có thể không biết transaction đã commit hay chưa**. Ví dụ, database đã commit đơn hàng nhưng phản hồi COMMIT bị mất trên mạng. Nếu ứng dụng gửi lại toàn bộ thao tác mà không có cơ chế chống trùng, đơn hàng hoặc khoản thanh toán có thể được tạo hai lần.

Một ứng dụng chịu lỗi cần giải quyết đồng thời ba vấn đề:

1. **Phục hồi kết nối:** nhận diện connection hỏng, loại bỏ nó khỏi pool và tạo kết nối mới khi có thể.
2. **Retry có giới hạn:** chỉ thử lại lỗi có khả năng tạm thời, giới hạn số lần và tổng thời gian chờ, có backoff và jitter.
3. **Chống giao dịch trùng:** dùng idempotency key, ràng buộc duy nhất và transaction boundary để một request được gửi lại không tạo thêm hiệu ứng nghiệp vụ.

Trong module **Database Engine Relational Oracle**, bài học này thuộc chương **Sẵn sàng cao**. Nội dung đi từ phân loại lỗi, thiết kế timeout và retry, xử lý kết quả COMMIT không rõ ràng, đến Oracle Transaction Guard, Application Continuity, connection pool và transactional outbox/inbox.

## 2. Các kiểu lỗi mà ứng dụng cần phân biệt

Không phải mọi lỗi đều có thể giải quyết bằng cách retry. Trước khi thiết kế chính sách, cần phân loại lỗi theo nguyên nhân và trạng thái transaction.

### 2.1. Lỗi tạm thời (transient)

Lỗi có thể biến mất sau một khoảng ngắn:
- Một node hoặc instance đang chuyển trạng thái.
- Kết nối TCP bị reset.
- Listener tạm thời không nhận kết nối.
- Resource Manager hoặc hệ thống đang bận.
- Transaction gặp deadlock hoặc serialization conflict.
- Một dịch vụ phụ thuộc đang khôi phục.

Lỗi loại này có thể retry nếu thao tác an toàn, còn thời gian trong deadline và đã xác định transaction state.

### 2.2. Lỗi cấu hình hoặc xác thực (permanent/configuration)

Retry liên tục không sửa được:
- Username/password sai.
- Service name hoặc connect descriptor sai.
- Tài khoản bị khóa hoặc hết hạn.
- User thiếu quyền.
- Tên bảng/cột sai.
- SQL syntax hoặc bind type sai.
- Constraint nghiệp vụ bị vi phạm.
- Policy bảo mật từ chối thao tác.

Cần trả lỗi cho caller hoặc chuyển đến vận hành xử lý cấu hình.

### 2.3. Lỗi nghiệp vụ

Ví dụ:
- Số dư không đủ.
- Đơn hàng đã đóng.
- Mã khách hàng không hợp lệ.
- Một yêu cầu đã được xử lý trước đó.
- Giá trị đầu vào vượt quy tắc nghiệp vụ.

Đây không phải lỗi hạ tầng. Không retry tự động chỉ vì một câu SQL trả về zero rows hoặc application nhận mã lỗi nghiệp vụ.

### 2.4. Lỗi có kết quả không xác định

Đây là trường hợp nguy hiểm nhất. Client đã gửi một thao tác nhưng không nhận được phản hồi xác nhận cuối cùng.

Ví dụ:
- Connection rớt trong khi câu lệnh đang chạy.
- Client timeout ngay sau khi gửi COMMIT.
- Instance failover đúng lúc transaction kết thúc.
- Ứng dụng bị dừng sau khi database commit nhưng trước khi gửi response.

Khi đó, client không thể kết luận transaction thất bại chỉ dựa trên exception. Cần kiểm tra outcome bằng Transaction Guard nếu được hỗ trợ hoặc tra cứu idempotency record bằng một kết nối mới.

## 3. Connection failure không đồng nghĩa transaction rollback

Một request thường đi qua các bước:

```text
Client
  |
  | 1. Gửi SQL/DML
  v
Oracle session
  |
  | 2. Thực hiện transaction
  v
Database
  |
  | 3. COMMIT
  v
Oracle gửi phản hồi
  |
  X 4. Mạng đứt trước khi client nhận ACK
```

Ở thời điểm client nhận lỗi, database có thể đã commit thành công. Client chỉ biết rằng phản hồi không đến được nơi nhận.

Vì vậy cần phân biệt:

- **Chắc chắn chưa gửi thao tác:** có thể thử lại sau khi khôi phục kết nối.
- **Đã gửi thao tác nhưng chưa biết kết quả:** phải xác định outcome hoặc dùng idempotency key.
- **Đã nhận xác nhận commit:** không gửi lại transaction.
- **Đã nhận lỗi nghiệp vụ/constraint:** xử lý theo lỗi đó, không retry như lỗi mạng.

Đặc biệt, exception khi gọi `commit()` không chứng minh transaction đã rollback. Đây là nguyên nhân phổ biến dẫn đến giao dịch trùng.

## 4. Xây dựng chính sách retry có giới hạn

Retry giúp ứng dụng vượt qua lỗi tạm thời, nhưng retry vô hạn có thể biến sự cố nhỏ thành sự cố toàn hệ thống.

### 4.1. Giới hạn số lần thử

Mỗi request cần có:
- Số lần thử tối đa.
- Deadline tổng.
- Timeout riêng cho việc lấy connection.
- Connect timeout.
- Statement/query timeout.
- Khoảng nghỉ giữa các lần thử.

Ví dụ một chính sách:
- Tối đa 4 lần thực thi.
- Tổng deadline 8 giây.
- Connect timeout 1 giây mỗi lần.
- Statement timeout theo SLA nghiệp vụ.
- Backoff tăng dần, không vượt quá 2 giây.

Các giá trị chỉ là ví dụ. Cần dựa trên SLA và thời gian phục hồi thực tế của dịch vụ.

### 4.2. Exponential backoff

Exponential backoff tăng thời gian chờ sau mỗi lần thất bại:

\[
delay_n = \min(maxDelay,\ baseDelay \times 2^n)
\]

Ví dụ base delay 100 ms, max delay 2 giây:

| Lần retry | Khoảng chờ tối đa trước jitter |
|---:|---:|
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 1.600 ms |

Không nên dùng một khoảng nghỉ cố định cho tất cả client. Nếu hàng nghìn client cùng retry sau 500 ms, chúng có thể tiếp tục tạo một đợt tải đột biến.

### 4.3. Jitter

Jitter thêm yếu tố ngẫu nhiên vào thời gian backoff. Một cách thường dùng là full jitter:

\[
actualDelay_n = random(0,\ delay_n)
\]

Nhờ đó các client không cùng thức dậy và gửi request vào một thời điểm. Jitter đặc biệt quan trọng khi database hoặc service vừa phục hồi sau outage.

### 4.4. Giới hạn deadline tổng

Không chỉ giới hạn số lần thử. Mỗi lần retry tiêu thụ thời gian trong deadline của request.

Ví dụ:
- Deadline request: 8 giây.
- Lần thử đầu đã dùng 3 giây.
- Backoff dự kiến: 2 giây.
- Lần thử tiếp theo cần tối đa 4 giây.

Tổng dự kiến vượt deadline. Ứng dụng nên dừng retry và trả lỗi có thể xử lý, thay vì tiếp tục một request đã quá hạn.

### 4.5. Không giữ transaction hoặc connection trong lúc backoff

Khi transaction gặp lỗi cần retry:
1. Rollback transaction hiện tại.
2. Đóng hoặc loại connection bị lỗi.
3. Chờ backoff bên ngoài transaction.
4. Lấy connection mới.
5. Bắt đầu lại toàn bộ transaction theo cùng idempotency key.

Không `sleep` trong khi đang giữ row lock, transaction mở hoặc connection pool slot. Điều đó giữ tài nguyên trong thời gian không có công việc và làm tăng contention.

## 5. Phân loại lỗi Oracle trước khi retry

Ứng dụng nên có bảng phân loại lỗi theo mã Oracle, trạng thái kết nối và vị trí xảy ra lỗi. Không áp dụng một quy tắc chung cho tất cả exception.

| Lỗi/ví dụ | Diễn giải thường gặp | Hướng xử lý |
|---|---|---|
| `ORA-03113` | Channel bị đóng bất thường | Loại connection; xác định transaction outcome trước khi gửi lại |
| `ORA-03114` | Session không còn kết nối | Tạo connection mới; xử lý outcome nếu đã gửi DML/COMMIT |
| `ORA-03135` | Connection bị mất/timeout | Kiểm tra mạng, firewall, server; không retry mù thao tác ghi |
| `ORA-12541` | Không có listener tại endpoint | Có thể transient; kiểm tra listener/service và retry có deadline |
| `ORA-12514` | Listener không biết service được yêu cầu | Thường cần kiểm tra service registration/connect descriptor; retry liên tục không sửa cấu hình sai |
| `ORA-12170` | Connect timeout | Có thể do mạng hoặc endpoint; retry có giới hạn sau khi phân loại |
| `ORA-01017` | Credential không hợp lệ | Lỗi xác thực; không retry cùng credential |
| `ORA-28000` | Account bị khóa | Dừng và xử lý account/policy |
| `ORA-00060` | Deadlock detected | Rollback toàn bộ business transaction rồi cân nhắc retry |
| `ORA-08177` | Cannot serialize access | Rollback và retry toàn bộ transaction khi dùng serializable isolation |
| `ORA-00054` | Resource busy với NOWAIT | Có thể thử lại có giới hạn nếu nghiệp vụ cho phép |
| `ORA-00001` | Unique constraint violation | Thường là lỗi dữ liệu hoặc duplicate; kiểm tra idempotency record, không retry mù |
| `ORA-01400` | Không thể insert NULL vào cột NOT NULL | Lỗi dữ liệu/logic; không retry |
| `ORA-00942` | Table or view does not exist hoặc không có quyền phù hợp | Kiểm tra schema/quyền; không retry như lỗi mạng |
| `ORA-01555` | Snapshot too old | Điều tra undo/query duration; retry đơn thuần có thể lặp lại lỗi |
| `ORA-01013` | User requested cancel | Tôn trọng cancellation; không tự retry |
| `ORA-04021` | Timeout khi chờ lock object | Có thể transient, nhưng cần xác định DDL/deployment đang giữ lock |

Mã lỗi chỉ là một tín hiệu. Cần xem operation, transaction state, service state, driver exception và ngữ cảnh ứng dụng. Một số lỗi có nhiều nguyên nhân khác nhau.

### 5.1. Retry ở cấp transaction, không chỉ cấp câu SQL

Nếu một business transaction gồm:
1. Đọc tồn kho.
2. Trừ tồn kho.
3. Tạo đơn hàng.
4. Ghi lịch sử.

Khi bước 4 lỗi, không nên retry riêng bước 4 nếu các bước trước có thể đã thay đổi dữ liệu. Với lỗi retryable, rollback transaction và thực hiện lại toàn bộ đơn vị nghiệp vụ từ đầu.

### 5.2. Deadlock và serialization conflict

Với `ORA-00060`, Oracle phát hiện deadlock và rollback statement gây deadlock. Những statement trước đó trong transaction có thể vẫn còn hiệu lực cho đến khi caller rollback. Vì vậy, ứng dụng nên rollback toàn bộ business transaction trước khi thử lại.

Với `ORA-08177` trong serializable isolation, transaction cần được thực hiện lại để lấy snapshot phù hợp. Dùng retry có giới hạn và cùng idempotency key.

## 6. Idempotency: cùng một request có thể gửi nhiều lần mà không tạo hiệu ứng trùng

Một thao tác là **idempotent** nếu thực hiện lặp lại với cùng định danh request không làm phát sinh thêm hiệu ứng nghiệp vụ sau lần đầu.

Ví dụ:
- Đặt trạng thái đơn hàng thành `PAID` có thể idempotent nếu có điều kiện trạng thái và khóa phù hợp.
- Cộng thêm 100 vào số dư không idempotent: gửi hai lần sẽ cộng 200.
- Tạo payment mới không idempotent nếu mỗi lần gọi tạo một payment khác.
- Đặt cấu hình về giá trị cụ thể thường idempotent hơn thao tác tăng/giảm tương đối.

Không nên suy ra idempotency chỉ từ HTTP method hoặc tên API. Phải xét toàn bộ hiệu ứng database và các hệ thống bên ngoài.

### 6.1. Idempotency key

Client tạo một key duy nhất cho một ý định nghiệp vụ, ví dụ UUID:

```text
Idempotency-Key: 8e2f... (UUID)
```

Khi retry cùng request, client phải gửi lại **cùng key**. Không tạo key mới cho mỗi lần thử.

Server lưu key và kết quả xử lý. Nếu key đã hoàn tất, server trả lại kết quả đã lưu thay vì chạy nghiệp vụ lần nữa.

### 6.2. Phạm vi key

Key nên được định danh theo:
- Tenant hoặc customer.
- Operation/API.
- Idempotency key do client tạo.

Ví dụ khóa logic là `(tenant_id, operation_name, idempotency_key)`. Điều này tránh một client dùng cùng UUID cho hai tenant hoặc hai nghiệp vụ khác nhau gây xung đột ngoài ý muốn.

### 6.3. Payload hash

Lưu hash của payload đã chuẩn hóa. Nếu một client tái sử dụng cùng key nhưng gửi payload khác, server phải từ chối.

Ví dụ:
- Key K + tạo đơn 100 USD: xử lý lần đầu.
- Key K + tạo đơn 100 USD gửi lại: trả kết quả cũ.
- Key K + tạo đơn 500 USD: từ chối vì cùng key nhưng nội dung khác.

Chuẩn hóa payload trước khi hash để thứ tự thuộc tính JSON hoặc định dạng không đáng kể không làm hai request giống nhau bị coi là khác.

## 7. Bảng idempotency/deduplication trong Oracle

Có thể tạo bảng lưu trạng thái request:

```sql
CREATE TABLE app.api_request_dedup (
    tenant_id        NUMBER        NOT NULL,
    operation_name   VARCHAR2(80) NOT NULL,
    idempotency_key  VARCHAR2(128) NOT NULL,
    request_hash     RAW(32)       NOT NULL,
    request_status   VARCHAR2(16) NOT NULL,
    response_code    NUMBER,
    response_body    CLOB,
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    completed_at     TIMESTAMP WITH TIME ZONE,
    CONSTRAINT api_request_dedup_pk
        PRIMARY KEY (tenant_id, operation_name, idempotency_key),
    CONSTRAINT api_request_dedup_status_ck
        CHECK (request_status IN ('IN_PROGRESS', 'COMPLETED'))
);
```

Bảng cần được thiết kế theo dung lượng và retention thực tế. `response_body` có thể thay bằng mã kết quả hoặc reference đến response đã lưu nếu payload lớn.

### 7.1. Vì sao cần unique constraint?

Hai request cùng key có thể đến đồng thời. Nếu chỉ dùng câu `SELECT` kiểm tra trước rồi `INSERT`, cả hai transaction có thể cùng thấy chưa tồn tại và cùng chạy nghiệp vụ.

Primary key/unique constraint là điểm đồng bộ cuối cùng ở database. Chỉ một transaction có thể ghi thành công cùng một khóa.

### 7.2. Không chỉ kiểm tra ở tầng ứng dụng

Mẫu không an toàn:

```text
SELECT xem key đã tồn tại chưa
Nếu chưa:
    thực hiện nghiệp vụ
    INSERT key
```

Hai request song song có thể cùng vượt qua bước SELECT. Hãy để unique constraint bảo vệ tính duy nhất và xử lý duplicate có chủ đích.

## 8. Đặt dedup record và thay đổi nghiệp vụ trong cùng transaction

Với request ngắn, cách đơn giản và an toàn là ghi idempotency record, thực hiện thay đổi nghiệp vụ, lưu response và commit tất cả trong **một transaction Oracle**.

Luồng:

```text
BEGIN TRANSACTION
    |
    v
INSERT idempotency key (unique)
    |
    +---- Duplicate key --> đọc hash/kết quả đã lưu
    |                         |
    |                         +--> trả response cũ hoặc báo key conflict
    |
    v
Thực hiện thay đổi nghiệp vụ
    |
    v
Lưu response và đánh dấu COMPLETED
    |
    v
COMMIT
```

Nếu process chết trước COMMIT, cả idempotency row và thay đổi nghiệp vụ đều rollback. Nếu COMMIT thành công nhưng response bị mất, lần gọi lại cùng key sẽ tìm được record đã hoàn tất.

### 8.1. Trình tự xử lý khái quát

```sql
-- Pseudocode minh họa trong transaction của request.
INSERT INTO app.api_request_dedup (
    tenant_id,
    operation_name,
    idempotency_key,
    request_hash,
    request_status
)
VALUES (
    :tenant_id,
    'CREATE_ORDER',
    :idempotency_key,
    :request_hash,
    'IN_PROGRESS'
);

-- Thực hiện thay đổi đơn hàng trong cùng transaction.
INSERT INTO app.orders (
    order_id,
    tenant_id,
    status,
    amount
)
VALUES (
    app.orders_seq.NEXTVAL,
    :tenant_id,
    'CREATED',
    :amount
);

-- Lưu kết quả cần trả lại khi request được gửi lại.
UPDATE app.api_request_dedup
SET request_status = 'COMPLETED',
    response_code = 201,
    response_body = :response_json,
    completed_at = SYSTIMESTAMP
WHERE tenant_id = :tenant_id
  AND operation_name = 'CREATE_ORDER'
  AND idempotency_key = :idempotency_key;

COMMIT;
```

Đây là trình tự minh họa, không phải script triển khai đầy đủ. Ứng dụng phải rollback khi có lỗi và chỉ gửi response thành công sau khi commit đã được xác nhận hoặc outcome đã được xác minh.

### 8.2. Xử lý duplicate key

Nếu `INSERT` idempotency record gặp `ORA-00001`:
1. Xác định lỗi đến từ constraint idempotency key.
2. Đọc record theo đúng tenant, operation và key.
3. So sánh `request_hash`.
4. Nếu hash khác, trả lỗi xung đột key/payload.
5. Nếu hash giống và status `COMPLETED`, trả lại response đã lưu.
6. Nếu record đang được xử lý theo mô hình reservation riêng, áp dụng chính sách chờ hoặc trả trạng thái đang xử lý.

Trong thiết kế một transaction nguyên tử, record `IN_PROGRESS` chưa commit sẽ không hiển thị cho session khác. Unique check của request đồng thời có thể chờ transaction đầu kết thúc; sau đó request thứ hai nhận duplicate nếu transaction đầu commit, hoặc có thể insert nếu transaction đầu rollback.

### 8.3. Chỉ bắt duplicate trên đúng unique key

Không coi mọi `ORA-00001` là request trùng. Một insert đơn hàng cũng có thể vi phạm unique constraint của mã đơn hoặc khóa nghiệp vụ. Phải xác định constraint gây lỗi hoặc kiểm tra record idempotency bằng đúng key.

### 8.4. Không commit riêng idempotency record nếu chưa có state machine

Nếu insert `IN_PROGRESS` rồi commit riêng, sau đó mới xử lý nghiệp vụ, process có thể chết và để lại record đang xử lý dù không có transaction nghiệp vụ đang chạy.

Mô hình reservation riêng cần thêm:
- Owner/worker ID.
- Lease expiration.
- Heartbeat hoặc thời điểm cập nhật.
- Quy tắc takeover sau lease.
- Cách phát hiện transaction đã commit nhưng worker chết.
- Cơ chế khôi phục trạng thái.

Chỉ dùng mô hình này khi nghiệp vụ dài hoặc cần xử lý bất đồng bộ; với request ngắn, một transaction nguyên tử thường dễ kiểm soát hơn.

## 9. Xử lý kết quả COMMIT không rõ ràng

Tình huống: ứng dụng gửi `COMMIT`, database có thể đã ghi transaction vào redo và xác nhận commit nội bộ, nhưng TCP connection bị đứt trước khi client nhận phản hồi.

Không thể giải quyết bằng cách:
- Giả định commit thất bại.
- Gửi lại INSERT/UPDATE với key mới.
- Tạo một transaction mới mà không kiểm tra request cũ.

### 9.1. Quy trình kiểm tra outcome bằng idempotency key

Khi mất kết nối trong lúc commit:
1. Đánh dấu connection cũ hỏng và loại khỏi pool.
2. Không thực hiện lại nghiệp vụ ngay lập tức.
3. Lấy connection mới.
4. Tra cứu idempotency record bằng cùng tenant, operation và key.
5. Nếu record `COMPLETED`, trả response đã lưu.
6. Nếu record không tồn tại, transaction cũ có thể đã rollback; có thể thử lại cùng key trong deadline.
7. Nếu trạng thái chưa thể xác định, chờ/backoff hoặc báo kết quả chưa xác định để caller tra cứu lại cùng key.

Không dùng một truy vấn kiểm tra tức thời để kết luận transaction cũ đã rollback nếu server/session vẫn đang xử lý. Thiết kế cần tính đến thời gian transaction được database giải quyết sau lỗi mạng.

### 9.2. Idempotency record là nguồn sự thật nghiệp vụ

Nếu record dedup và business changes được commit trong cùng transaction:
- Record `COMPLETED` chứng minh thay đổi nghiệp vụ cùng transaction đã commit.
- Không có record sau khi transaction cũ đã được giải quyết cho thấy transaction đó không commit theo thiết kế này.
- Record và business data không thể lệch nhau do crash giữa hai thao tác commit riêng biệt.

Điều kiện quan trọng là tất cả hiệu ứng database cần chống trùng phải nằm trong cùng transaction và không có side effect ngoài database được thực hiện trước commit.

### 9.3. Oracle Transaction Guard

Oracle Transaction Guard giúp client xác định outcome của transaction cuối cùng sau một số lỗi outage/failover, trong các môi trường và driver được hỗ trợ. Nó sử dụng logical transaction ID (LTXID) để phân biệt transaction và cung cấp thông tin outcome.

Lợi ích:
- Tránh thực hiện lại transaction đã commit.
- Giúp client xử lý trường hợp commit response bị mất.
- Hỗ trợ xây dựng retry an toàn khi kết hợp với client stack và service configuration phù hợp.

Transaction Guard không tự làm mọi câu SQL idempotent và không thay thế idempotency key cho request nghiệp vụ. Kiểm tra phiên bản Oracle, driver, service attributes và API hỗ trợ trước khi triển khai. Oracle JDBC, OCI và các client stack khác có mức hỗ trợ khác nhau theo release.

## 10. Oracle Application Continuity và Transparent Application Continuity

Oracle có các tính năng phía client/service để hỗ trợ khôi phục request khi database service hoặc instance gặp sự cố.

### 10.1. Application Continuity (AC)

Application Continuity có thể ghi nhận và replay một request đang thực hiện khi gặp outage đủ điều kiện. Mục tiêu là che giấu một số lỗi hạ tầng đối với ứng dụng.

Replay không có nghĩa mọi request đều được chạy lại vô điều kiện. Oracle cần biết trạng thái transaction và các thao tác đã thực hiện để tránh tạo hiệu ứng trùng theo semantics được hỗ trợ.

### 10.2. Transparent Application Continuity (TAC)

TAC mở rộng khả năng replay trong các môi trường được hỗ trợ, với mục tiêu giảm thay đổi cần thiết ở application code. Hành vi cụ thể phụ thuộc release, service configuration và driver.

### 10.3. Transaction Guard kết hợp replay

Transaction Guard cung cấp thông tin outcome transaction; Application Continuity/TAC có thể sử dụng cơ chế này để quyết định replay request an toàn theo điều kiện hỗ trợ.

Cần kiểm tra:
- Database release và Release Update.
- Service attributes.
- Driver/client version.
- Các API hoặc operation không hỗ trợ replay.
- Session state và request boundary.
- Tính idempotent của side effect ngoài database.

### 10.4. Transparent Application Failover (TAF)

TAF là cơ chế failover session trong một số kiến trúc Oracle RAC/Data Guard và client được hỗ trợ. Nó có giới hạn về loại operation, trạng thái session và việc tiếp tục transaction. TAF không tương đương Application Continuity và không nên được mô tả như bảo đảm mọi transaction đang chạy sẽ tự động tiếp tục từ đúng instruction.

### 10.5. Không nhầm HA failover với business retry

RAC hoặc Data Guard có thể giúp service sẵn sàng hơn, nhưng ứng dụng vẫn cần:
- Xử lý connection exception.
- Deadline và retry policy.
- Idempotency key.
- Kiểm tra commit outcome.
- Theo dõi lỗi và tránh retry storm.

HA giảm thời gian outage; logic ứng dụng bảo vệ tính đúng đắn của nghiệp vụ.

## 11. Connection pool và quản lý connection hỏng

Ứng dụng thường không mở TCP connection mới cho từng request. Connection pool giữ các session đã mở và tái sử dụng chúng.

### 11.1. Connection chết có thể vẫn nằm trong pool

Một connection có thể bị hỏng vì:
- Database instance restart.
- RAC service chuyển sang instance khác.
- Firewall đóng connection idle.
- NAT hoặc load balancer timeout.
- Network partition.
- Database session bị kill.
- Server-side timeout.

Pool có thể không phát hiện ngay. Lần ứng dụng mượn connection tiếp theo mới nhận exception.

### 11.2. Validate và loại bỏ connection lỗi

Cấu hình pool cần xem xét:
- Validation khi borrow hoặc theo cơ chế background.
- Connection timeout.
- Idle timeout.
- Maximum lifetime.
- Keepalive/heartbeat phù hợp.
- Kiểm tra connection trước khi tái sử dụng sau failover.
- Loại connection hỏng khỏi pool.
- Giới hạn tổng connection để không làm database quá tải.

Validation query đơn giản trong Oracle có thể là:

```sql
SELECT 1 FROM dual;
```

Không nhất thiết chạy validation query cho mọi lần borrow nếu driver/pool có cơ chế kiểm tra hiệu quả hơn. Chọn theo latency, network và khả năng phát hiện stale connection.

### 11.3. Không trả connection hỏng về pool

Sau lỗi network nghiêm trọng:
- Đánh dấu connection không còn hợp lệ.
- Đóng/discard connection theo API pool.
- Không đưa session hỏng trở lại danh sách idle.
- Lấy connection mới khi retry được phép.

Không chỉ gọi `rollback()` trên một connection đã mất mạng rồi giả định trạng thái đã sạch. Nếu không thể xác nhận trạng thái, loại bỏ connection.

### 11.4. Reset session state

Connection pool tái sử dụng session, nên cần reset:
- Application context.
- `CLIENT_IDENTIFIER`.
- Module/action.
- Current schema.
- NLS settings nếu request thay đổi.
- Transaction isolation/read-only state.
- Temporary state hoặc package state theo thiết kế.

Nếu ứng dụng dùng VPD, context tenant phải được thiết lập lại cho từng request. Không để request sau kế thừa security context của request trước.

## 12. Oracle RAC, FAN, FCF và service configuration

Trong Oracle RAC, dịch vụ database có thể chuyển giữa các instance. Ứng dụng cần biết instance/service nào còn khả dụng.

### 12.1. Fast Application Notification (FAN)

FAN gửi thông báo về sự kiện service/instance/node đến client hoặc middleware được cấu hình hỗ trợ. Thông báo giúp pool nhanh chóng nhận biết connection cần loại bỏ hoặc service đang có thay đổi.

### 12.2. Fast Connection Failover (FCF)

FCF kết hợp thông báo FAN với connection pool/client stack hỗ trợ để loại connection bị ảnh hưởng và phân phối kết nối mới tới instance/service còn hoạt động.

FCF không tự retry business transaction một cách an toàn. Ứng dụng vẫn cần xử lý lỗi và transaction outcome.

### 12.3. Oracle Universal Connection Pool (UCP)

UCP có tích hợp các khả năng Oracle như FAN/FCF, connection labeling, validation và các tính năng HA theo phiên bản. Khi dùng JDBC, cần kiểm tra UCP và Oracle JDBC driver tương thích với database/service.

### 12.4. Service-level workload management

Nên định nghĩa service phù hợp với loại workload:
- OLTP service.
- Batch service.
- Reporting service.
- Service cần Application Continuity nếu kiến trúc hỗ trợ.

Service có thể mang thuộc tính failover/replay và Resource Manager mapping. Đặt thuộc tính theo SLA và kiểm thử failover thật.

## 13. Timeout ở từng lớp

Một ứng dụng có thể có nhiều timeout đồng thời. Nếu không phối hợp, client có thể bỏ request trong khi database vẫn chạy, hoặc connection pool chờ lâu hơn deadline của API.

| Timeout | Kiểm soát |
|---|---|
| Pool acquisition timeout | Thời gian chờ mượn connection |
| DNS/connect timeout | Thời gian phân giải và thiết lập kết nối |
| Socket/read timeout | Thời gian chờ phản hồi mạng |
| Oracle Net timeout | Thời gian chờ trong một số thao tác mạng |
| Statement/query timeout | Thời gian cho phép câu SQL chạy |
| Transaction deadline | Tổng thời gian business transaction |
| API/request deadline | Tổng thời gian caller chờ |
| Retry deadline | Tổng thời gian dành cho các lần thử và backoff |

### 13.1. Timeout phải có thứ tự hợp lý

Ví dụ:
- API deadline: 10 giây.
- Pool acquisition: tối đa 1 giây.
- Connect timeout: 2 giây.
- Statement timeout: 5 giây.
- Retry/backoff chỉ sử dụng phần ngân sách còn lại.

Đây là ví dụ. Tổng timeout của từng attempt và backoff phải nằm trong deadline tổng. Không đặt socket timeout quá ngắn khiến một query hợp lệ bị cắt giữa chừng.

### 13.2. Timeout không tự hủy transaction ngay lập tức

Client timeout có thể chỉ dừng việc chờ phản hồi. Tùy driver, network và trạng thái server, câu SQL có thể còn tiếp tục hoặc cancellation có thể đến trễ.

Khi timeout:
- Xác định driver đã gửi cancel hay chưa.
- Xử lý connection/session state.
- Rollback nếu còn kết nối và transaction chưa commit.
- Nếu mất kết nối ở vùng COMMIT, xác định outcome.
- Dùng cùng idempotency key nếu caller gửi lại.

## 14. Circuit breaker, bulkhead và retry budget

Retry chỉ là một phần của khả năng chịu lỗi.

### 14.1. Circuit breaker

Circuit breaker theo dõi tỷ lệ lỗi và tạm ngừng gửi request đến dependency đang gặp sự cố.

Các trạng thái thường dùng:
- **Closed:** request được phép đi qua.
- **Open:** chặn request trong một khoảng thời gian để dependency hồi phục.
- **Half-open:** cho phép một số request thử để đánh giá khả năng phục hồi.

Circuit breaker tránh việc hàng nghìn request liên tục tạo thêm tải khi database hoặc network đang không khả dụng.

### 14.2. Bulkhead

Bulkhead giới hạn tài nguyên cho từng workload:
- Pool riêng cho OLTP và batch.
- Giới hạn concurrency của API.
- Hạn chế số query/report chạy đồng thời.
- Tách worker queue theo loại công việc.

Nếu batch lỗi và retry liên tục, bulkhead giúp không chiếm toàn bộ connection của giao dịch người dùng.

### 14.3. Retry budget

Đặt ngân sách retry theo request hoặc theo dịch vụ:
- Tối đa số attempt.
- Tỷ lệ request được phép retry.
- Tổng thời gian retry.
- Giới hạn số request retry đồng thời.

Không để API gateway, service A, service B và database client mỗi tầng retry nhiều lần. Retry lồng nhau có thể nhân số lần gọi theo cấp số nhân. Chọn một tầng chịu trách nhiệm retry business operation và quy định rõ các tầng còn lại.

## 15. Retry toàn bộ transaction một cách an toàn

Một transaction nên là đơn vị công việc nguyên tử. Ví dụ chuyển tiền:
1. Kiểm tra tài khoản.
2. Trừ tiền tài khoản nguồn.
3. Cộng tiền tài khoản đích.
4. Ghi ledger.
5. Commit.

Nếu bước 3 deadlock hoặc connection lỗi trước commit, retry phải bắt đầu lại từ đầu với cùng request identity sau khi rollback/kiểm tra outcome. Không chỉ chạy lại bước 3.

### 15.1. Pseudocode cho transaction retry

```text
handle(request, idempotencyKey):
    deadline = now + requestBudget

    for attempt in 1..maxAttempts:
        connection = borrowConnection(deadline)

        try:
            begin transaction
            result = executeBusinessTransaction(
                connection,
                request,
                idempotencyKey
            )
            commit
            return result

        catch retryableFailure:
            rollback if outcome is known and connection is usable
            discard connection if broken
            if commit outcome is unknown:
                resolve outcome using idempotency key or Transaction Guard
                if already committed:
                    return stored result

            if attempt limit reached or deadline expired:
                return retryable failure

            sleep with exponential backoff and jitter
        finally:
            return only healthy, clean connection to pool
```

Đây là pseudocode kiến trúc, không phải code Java hoàn chỉnh. Cần tách rõ exception xảy ra trước COMMIT, trong COMMIT và sau COMMIT.

### 15.2. Giữ cùng idempotency key qua mọi attempt

Mỗi lần retry cùng một ý định nghiệp vụ phải dùng cùng key. Nếu mỗi attempt tạo key mới, server không thể nhận diện đó là cùng request và dedup không có tác dụng.

### 15.3. Không retry nghiệp vụ đã thất bại rõ ràng

Nếu database trả về constraint violation hoặc application phát hiện số dư không đủ, không thử lại nhiều lần. Trả kết quả nghiệp vụ tương ứng.

## 16. Giao dịch dài và mô hình reservation/lease

Với request kéo dài nhiều phút, giữ một transaction database mở trong toàn bộ quá trình có thể gây lock, undo và connection pressure. Có thể cần mô hình bất đồng bộ:

1. Nhận request và tạo idempotency record.
2. Commit trạng thái `ACCEPTED` cùng job/outbox event.
3. Worker nhận job.
4. Worker lấy lease để xử lý.
5. Worker cập nhật trạng thái `COMPLETED` hoặc `FAILED`.
6. Retry job dùng cùng request key và kiểm tra trạng thái.

Bảng job có thể có:
- `REQUEST_ID` unique.
- `STATUS`.
- `LEASE_OWNER`.
- `LEASE_EXPIRES_AT`.
- `ATTEMPT_COUNT`.
- `NEXT_ATTEMPT_AT`.
- `LAST_ERROR_CODE`.
- `COMPLETED_AT`.

### 16.1. Lease và takeover

Worker chết có thể để lại job `PROCESSING`. Lease cho phép worker khác tiếp quản sau thời gian hết hạn, nhưng phải ngăn hai worker cùng xử lý.

Có thể dùng atomic update có điều kiện:

```sql
UPDATE app.job_request
SET lease_owner = :worker_id,
    lease_expires_at = SYSTIMESTAMP + INTERVAL '60' SECOND,
    attempt_count = attempt_count + 1
WHERE request_id = :request_id
  AND status IN ('ACCEPTED', 'RETRY')
  AND (lease_expires_at IS NULL
       OR lease_expires_at < SYSTIMESTAMP);
```

Worker chỉ được xử lý nếu `SQL%ROWCOUNT = 1`. Thời lượng lease và heartbeat phải được chọn theo thời gian xử lý; một lease quá ngắn có thể khiến worker thứ hai takeover khi worker đầu vẫn còn sống.

### 16.2. Fencing token

Trong hệ thống nhiều worker, lease hết hạn không nhất thiết có nghĩa worker cũ đã dừng. Một fencing token tăng dần có thể giúp resource đích từ chối thao tác từ worker cũ có token thấp hơn. Điều này đặc biệt quan trọng khi worker có thể tiếp tục sau một network pause.

## 17. External side effects và transactional outbox

Database transaction không thể tự động rollback một email đã gửi, một lệnh gọi payment provider đã thành công hoặc một message đã publish ra broker.

Ví dụ:
1. Insert đơn hàng.
2. Gọi payment API.
3. Gửi email.
4. Commit Oracle.

Nếu connection mất sau bước 2, ứng dụng có thể không biết payment đã thành công. Retry toàn bộ có thể thu tiền hai lần.

### 17.1. Transactional outbox

Trong cùng transaction Oracle:
- Ghi thay đổi nghiệp vụ.
- Ghi một outbox event với event ID duy nhất.
- Commit.

Worker riêng đọc outbox và gửi message đến hệ thống bên ngoài. Nếu worker gửi thành công nhưng chết trước khi đánh dấu event đã gửi, nó có thể gửi lại. Vì vậy consumer cũng cần idempotency/dedup.

### 17.2. Ví dụ outbox table

```sql
CREATE TABLE app.outbox_event (
    event_id       RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    aggregate_id   VARCHAR2(128) NOT NULL,
    event_type     VARCHAR2(80) NOT NULL,
    payload        CLOB NOT NULL,
    event_status   VARCHAR2(16) DEFAULT 'NEW' NOT NULL,
    created_at     TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    published_at   TIMESTAMP WITH TIME ZONE
);
```

Trong transaction tạo đơn hàng, insert thêm outbox event. Khi đơn hàng commit, event cũng tồn tại bền vững. Worker publisher gửi event theo event ID và cập nhật trạng thái.

### 17.3. Inbox/dedup ở consumer

Consumer lưu `event_id` trong bảng inbox có unique constraint. Nếu nhận lại event:
- Nếu event ID đã xử lý, bỏ qua hiệu ứng nghiệp vụ và trả ACK.
- Nếu chưa xử lý, ghi inbox và business change trong cùng transaction của consumer.
- Chỉ ACK sau khi commit.

Cách này tạo hiệu ứng **effectively-once** ở cấp nghiệp vụ khi các ranh giới transaction và dedup được thiết kế đúng. Mạng và message broker vẫn có thể giao message nhiều lần; không nên tuyên bố transport đã bảo đảm exactly-once end-to-end.

### 17.4. Payment provider

Nếu payment provider hỗ trợ idempotency key, gửi cùng key cho mọi lần retry của cùng một khoản thanh toán. Lưu provider transaction ID và outcome trong database. Không tạo key mới khi timeout response.

## 18. Chống trùng bằng constraint nghiệp vụ

Idempotency key bảo vệ một request identity. Ngoài ra, nên dùng unique constraint cho các quy tắc nghiệp vụ vốn phải duy nhất.

Ví dụ:
- Mỗi đơn hàng có external reference duy nhất trong tenant.
- Mỗi invoice number duy nhất theo legal entity.
- Mỗi payment provider transaction ID chỉ được ghi một lần.
- Mỗi message/event ID chỉ được consumer xử lý một lần.

Ví dụ:

```sql
ALTER TABLE app.orders
ADD CONSTRAINT orders_tenant_external_ref_uq
UNIQUE (tenant_id, external_reference);
```

Nếu request đến hai lần với hai idempotency key khác nhau nhưng cùng external reference, unique constraint vẫn ngăn tạo hai đơn hàng cùng tham chiếu.

Constraint phải nằm trong database để chống race condition. Kiểm tra ở tầng ứng dụng chỉ giúp thông báo sớm, không thay thế ràng buộc duy nhất.

## 19. Các chi tiết Oracle ảnh hưởng đến thiết kế

### 19.1. Transaction atomicity

Oracle đảm bảo transaction commit hoặc rollback như một đơn vị. Hãy đặt idempotency record và thay đổi dữ liệu nghiệp vụ trong cùng transaction khi có thể.

Không commit giữa các bước chỉ để tránh lỗi tạm thời nếu điều đó phá vỡ tính nguyên tử của nghiệp vụ.

### 19.2. Sequence có thể có khoảng trống

`NEXTVAL` không phải cơ chế chống trùng request. Sequence có thể tăng dù transaction rollback hoặc do cache/instance failure. Khoảng trống trong sequence là bình thường và không chứng minh giao dịch bị mất hoặc trùng.

Dùng primary key/unique constraint cho tính duy nhất; dùng idempotency key cho request dedup.

### 19.3. Isolation và locking

Ở mức `READ COMMITTED`, mỗi statement có snapshot nhất quán theo thời điểm statement bắt đầu. Khi nhiều request cạnh tranh cùng một tài nguyên, có thể cần row lock, optimistic version hoặc conditional update.

Ví dụ cập nhật tồn kho an toàn:

```sql
UPDATE app.inventory
SET available_qty = available_qty - :quantity
WHERE product_id = :product_id
  AND available_qty >= :quantity;
```

Kiểm tra `SQL%ROWCOUNT`:
- 1 hàng: cập nhật thành công.
- 0 hàng: không tồn tại sản phẩm hoặc không đủ tồn kho theo điều kiện.

Đây là cách kết hợp kiểm tra và cập nhật trong một statement, giảm race giữa SELECT và UPDATE. Nếu cần phân biệt hai trường hợp, truy vấn thêm theo logic nghiệp vụ trong transaction.

### 19.4. Conditional update và optimistic locking

Với dữ liệu có version:

```sql
UPDATE app.account
SET balance = :new_balance,
    version_no = version_no + 1
WHERE account_id = :account_id
  AND version_no = :old_version;
```

Nếu `SQL%ROWCOUNT = 0`, một transaction khác đã thay đổi dữ liệu hoặc record không tồn tại. Ứng dụng cần đọc lại và đánh giá nghiệp vụ, không retry vô hạn với giá trị cũ.

### 19.5. DDL và implicit commit

Oracle DDL có thể gây implicit commit. Không đặt DDL vào business transaction rồi kỳ vọng rollback cùng DML. Các thao tác tạo/drop object phải tách khỏi transaction nghiệp vụ và có kế hoạch riêng.

## 20. Observability cho retry và duplicate prevention

Nếu chỉ ghi log “database error”, đội vận hành khó biết hệ thống có đang retry storm hay không.

Mỗi request nên có metadata:
- Request/correlation ID.
- Idempotency key hoặc hash an toàn (không nhất thiết log key đầy đủ).
- Tenant/operation.
- Attempt number.
- Oracle error code.
- Connection pool name.
- Service/instance nếu có.
- Thời điểm bắt đầu/kết thúc.
- Retry delay.
- Transaction phase: acquire, execute, commit, outcome resolution.
- Kết quả dedup: new, duplicate completed, key conflict, pending.
- Final status.

Không log password, token, full payment payload hoặc dữ liệu cá nhân không cần thiết.

### 20.1. Metrics cần theo dõi

| Metric | Ý nghĩa |
|---|---|
| Retry attempts/request | Request phải thử lại bao nhiêu lần |
| Retry success rate | Bao nhiêu retry phục hồi thành công |
| Retry exhaustion | Request hết ngân sách retry |
| Connection validation failure | Số connection stale bị loại |
| Pool wait time | Thời gian chờ lấy connection |
| Commit outcome unknown | Số lần client mất phản hồi quanh COMMIT |
| Duplicate key hit | Request được nhận diện là duplicate |
| Idempotency key conflict | Cùng key nhưng payload khác |
| Circuit breaker open time | Thời gian dependency bị chặn |
| Transaction duration | Thời gian giữ transaction |
| Outbox lag | Độ trễ event chưa publish |

Tăng retry success rate chưa chắc là tốt nếu tổng request rate và database load tăng mạnh. Cần theo dõi cả tỷ lệ lỗi cuối cùng, latency p95/p99 và tài nguyên database.

### 20.2. Alert

Đặt cảnh báo khi:
- Retry rate tăng đột biến.
- Nhiều connection lỗi cùng một service.
- Pool wait time vượt ngưỡng.
- Commit outcome unknown tăng.
- Idempotency conflict bất thường.
- Outbox backlog tăng liên tục.
- Circuit breaker mở quá lâu.
- `ORA-00060` hoặc `ORA-08177` tăng cao.

## 21. Kiểm thử fault injection

Chỉ test happy path là chưa đủ. Cần chủ động mô phỏng lỗi trong môi trường staging/lab.

### 21.1. Các điểm cần mô phỏng

1. Mất kết nối trước khi gửi SQL.
2. Mất kết nối khi SQL đang chạy.
3. Mất kết nối sau DML nhưng trước COMMIT.
4. Mất kết nối ngay sau khi gửi COMMIT.
5. Database instance restart trong lúc request chạy.
6. Connection pool trả về stale connection.
7. Hai request cùng idempotency key đến đồng thời.
8. Hai request cùng key nhưng payload khác.
9. Worker outbox chết sau khi publish nhưng trước khi đánh dấu hoàn tất.
10. Consumer nhận lại cùng event nhiều lần.

### 21.2. Kết quả cần chứng minh

- Không tạo đơn hàng/payment trùng.
- Không trừ/cộng số dư hai lần.
- Request cùng key trả cùng kết quả nghiệp vụ.
- Key cùng payload khác bị từ chối.
- Transaction thất bại không để lại thay đổi một phần ngoài thiết kế.
- Connection lỗi bị loại khỏi pool.
- Retry dừng khi hết deadline.
- Không giữ lock trong thời gian backoff.
- Outbox/inbox có thể phục hồi sau khi worker chết.
- Dịch vụ không bị retry storm.

### 21.3. Test concurrency

Dùng nhiều client cùng gửi một idempotency key trong cùng thời điểm. Kết quả mong muốn:
- Một transaction duy nhất thực hiện thay đổi nghiệp vụ.
- Các request còn lại nhận kết quả đã lưu hoặc trạng thái đang xử lý theo thiết kế.
- Số hàng nghiệp vụ chỉ tăng một.
- Unique constraint bảo vệ dù các request chạy đồng thời.

Không chỉ test tuần tự vì race condition thường chỉ xuất hiện dưới concurrency.

## 22. Ví dụ kiến trúc hoàn chỉnh cho API tạo đơn hàng

Giả sử `POST /orders` nhận tenant, danh sách sản phẩm và địa chỉ giao hàng.

### Bước 1. Client tạo request identity

Client tạo UUID idempotency key cho ý định tạo đơn và lưu lại cho đến khi nhận kết quả cuối cùng. Nếu timeout, client gửi lại cùng key.

### Bước 2. API xác thực

API xác thực người dùng/tenant, kiểm tra request và chuẩn hóa payload. Tạo payload hash. Không tin tenant ID chỉ vì nó xuất hiện trong body.

### Bước 3. Bắt đầu transaction

API mượn connection khỏe từ pool và bắt đầu transaction.

### Bước 4. Claim idempotency key

Insert `(tenant_id, operation, idempotency_key, request_hash)` vào bảng dedup. Unique constraint đảm bảo chỉ một request thắng.

### Bước 5. Thực hiện nghiệp vụ

Kiểm tra và trừ tồn kho bằng conditional update, tạo order, order lines và ghi audit nghiệp vụ cần thiết.

### Bước 6. Ghi outbox

Trong cùng transaction, ghi event `ORDER_CREATED` vào outbox để worker gửi message sau commit.

### Bước 7. Lưu response và commit

Cập nhật dedup record thành `COMPLETED`, lưu response/reference và commit.

### Bước 8. Trả response

Chỉ trả thành công khi commit được xác nhận. Nếu mất kết nối quanh COMMIT, mở connection mới và tra cứu key hoặc dùng Transaction Guard để xác định outcome.

### Bước 9. Retry

Nếu lỗi được phân loại transient và outcome đã được xử lý an toàn, retry toàn transaction với cùng key, backoff và jitter. Dừng khi deadline hết.

### Bước 10. Publish event

Worker đọc outbox, publish event ID. Consumer ghi inbox/dedup cùng business effect của nó và ACK sau commit.

## 23. Các anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách xử lý |
|---|---|---|
| Retry mọi exception | Lặp lỗi cấu hình/nghiệp vụ, tăng tải | Phân loại lỗi |
| Retry vô hạn | Giữ request và tài nguyên vô thời hạn | Giới hạn attempt/deadline |
| Dùng delay cố định cho mọi client | Retry đồng loạt, tạo tải đột biến | Exponential backoff + jitter |
| Retry chỉ câu SQL cuối | Transaction có thể bị thực hiện một phần | Rollback và retry toàn business transaction |
| Tạo idempotency key mới mỗi attempt | Server coi mỗi lần là request mới | Giữ nguyên key |
| SELECT trước rồi INSERT key | Race condition giữa hai request | Unique constraint làm trọng tài |
| Commit dedup trước business change | Có thể để record mồ côi hoặc trạng thái không nhất quán | Cùng transaction hoặc thiết kế lease rõ |
| Coi exception COMMIT là rollback | Có thể tạo giao dịch trùng | Resolve outcome bằng key/Transaction Guard |
| Dùng sequence làm dedup | Sequence không nhận diện ý định request | Unique idempotency/business key |
| Giữ connection trong lúc backoff | Cạn pool và giữ tài nguyên | Rollback, release rồi mới chờ |
| Retry ở mọi tầng | Số lần gọi nhân lên | Chỉ định một tầng retry chính |
| Gửi email/payment trong transaction rồi retry | Side effect ngoài database bị lặp | Outbox và external idempotency |
| Chỉ kiểm tra ở application code | Race condition vẫn xảy ra | Unique constraint/conditional DML |
| Trả connection lỗi về pool | Request tiếp theo tiếp tục thất bại | Discard broken connection |
| Không đặt timeout tổng | Request có thể kéo dài vô hạn | Deadline xuyên suốt các tầng |

## 24. Checklist triển khai

### Kết nối
- Pool có validation/eviction phù hợp.
- Connection hỏng được loại khỏi pool.
- Timeout connect, pool, socket và statement được cấu hình.
- Session state được reset giữa request.
- RAC/service failover được kiểm thử nếu sử dụng.

### Retry
- Có danh sách lỗi retryable và non-retryable.
- Retry có số lần tối đa và deadline.
- Có exponential backoff và jitter.
- Retry ở cấp transaction/business operation.
- Không giữ connection/lock trong backoff.
- Có circuit breaker, bulkhead hoặc retry budget khi phù hợp.

### Chống trùng
- Client tạo và giữ idempotency key qua các lần retry.
- Key có scope tenant/operation.
- Có payload hash để phát hiện reuse sai.
- Có unique constraint ở database.
- Dedup record và business changes cùng transaction khi phù hợp.
- Response được lưu để replay.
- Commit outcome unknown được xử lý rõ.
- Có retention đủ dài cho retry window.

### Tích hợp ngoài database
- Side effect được phát qua outbox hoặc có idempotency riêng.
- Consumer có inbox/dedup.
- Event ID ổn định.
- ACK sau commit.
- Có cơ chế retry/dead-letter và giám sát backlog.

### Vận hành
- Có metrics retry, duplicate, commit ambiguity và pool health.
- Có alert và runbook.
- Có fault injection/concurrency test.
- Có ngưỡng dừng retry và escalation.
- Không log secret hoặc payload nhạy cảm.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao mất kết nối không chứng minh transaction rollback?

**Trả lời:** Database có thể đã commit nhưng phản hồi COMMIT bị mất trên mạng, khiến client không biết outcome.

**Câu 2.** Retry có giới hạn cần những gì?

**Trả lời:** Số lần thử tối đa, deadline tổng, timeout từng tầng, backoff, jitter và phân loại lỗi.

**Câu 3.** Exponential backoff có tác dụng gì?

**Trả lời:** Tăng khoảng nghỉ giữa các lần retry để giảm áp lực lên dependency đang phục hồi.

**Câu 4.** Jitter giải quyết vấn đề gì?

**Trả lời:** Phân tán thời điểm retry của nhiều client, tránh retry đồng loạt.

**Câu 5.** Khi nào cần retry toàn transaction?

**Trả lời:** Khi lỗi retryable làm business transaction không thể tiếp tục an toàn; rollback phần đã làm và thực hiện lại toàn đơn vị nghiệp vụ.

**Câu 6.** Idempotency key là gì?

**Trả lời:** Định danh ổn định cho một ý định nghiệp vụ, giúp server nhận ra các lần gửi lại là cùng request.

**Câu 7.** Vì sao cần unique constraint cho idempotency key?

**Trả lời:** Nó giải quyết race condition ở database khi nhiều request cùng key đến đồng thời.

**Câu 8.** Vì sao cần lưu request hash?

**Trả lời:** Để phát hiện client tái sử dụng cùng key nhưng thay đổi payload.

**Câu 9.** Vì sao dedup record và business change nên cùng transaction?

**Trả lời:** Để chúng cùng commit hoặc rollback, tránh trạng thái đã đánh dấu hoàn tất nhưng nghiệp vụ chưa được ghi hoặc ngược lại.

**Câu 10.** Xử lý COMMIT timeout thế nào?

**Trả lời:** Không giả định thất bại; dùng connection mới tra cứu idempotency record hoặc Transaction Guard nếu được hỗ trợ.

**Câu 11.** Transaction Guard giúp gì?

**Trả lời:** Giúp client xác định outcome của transaction cuối cùng trong các kịch bản outage/failover được hỗ trợ.

**Câu 12.** Application Continuity làm gì?

**Trả lời:** Có thể replay request đủ điều kiện sau outage theo cấu hình và giới hạn của Oracle/client stack.

**Câu 13.** FAN/FCF giúp gì trong RAC?

**Trả lời:** Thông báo sự kiện service/instance và giúp pool loại connection bị ảnh hưởng, tạo connection mới tới service còn hoạt động.

**Câu 14.** Vì sao không retry mọi `ORA-` error?

**Trả lời:** Nhiều mã là lỗi xác thực, cấu hình, dữ liệu hoặc nghiệp vụ không thể tự hết khi chờ.

**Câu 15.** Vì sao không giữ connection trong backoff?

**Trả lời:** Connection và transaction có thể giữ lock/tài nguyên, làm cạn pool trong lúc không xử lý công việc.

**Câu 16.** Transactional outbox giải quyết vấn đề gì?

**Trả lời:** Ghi business change và event trong cùng transaction, sau đó worker publish event có thể retry mà không mất sự kiện.

**Câu 17.** Vì sao consumer vẫn cần inbox/dedup?

**Trả lời:** Publisher có thể gửi lại event sau khi không nhận được xác nhận, nên consumer phải chống xử lý cùng event nhiều lần.

**Câu 18.** Có thể bảo đảm exactly-once end-to-end chỉ bằng retry không?

**Trả lời:** Không. Cần định danh ổn định, lưu trạng thái bền vững, transaction boundary và dedup ở mỗi ranh giới side effect.

## 26. Kết luận

Ứng dụng Oracle chịu lỗi cần coi mất kết nối là tình huống bình thường phải xử lý có thiết kế. Connection lỗi phải được phát hiện và loại khỏi pool; retry chỉ áp dụng cho lỗi tạm thời, có số lần tối đa, deadline, exponential backoff và jitter. Khi retry transaction, rollback và thực hiện lại toàn bộ business operation với cùng request identity. Không giữ connection hoặc lock trong thời gian backoff.

Điểm khó nhất là kết quả COMMIT không rõ ràng. Client có thể mất phản hồi dù database đã commit. Vì vậy, không được suy luận rằng exception đồng nghĩa rollback. Idempotency key, payload hash, unique constraint và dedup record được commit cùng business data giúp request gửi lại trả về kết quả cũ thay vì tạo giao dịch mới. Oracle Transaction Guard có thể bổ sung khả năng xác định transaction outcome trong môi trường được hỗ trợ; Application Continuity/TAC, FAN/FCF và RAC service giúp cải thiện khả năng phục hồi kết nối nhưng không thay thế logic nghiệp vụ chống trùng.

Với side effect ngoài database, dùng transactional outbox và consumer inbox/dedup hoặc idempotency key của dịch vụ đích. Đo retry rate, commit ambiguity, pool health, duplicate hits và outbox lag; kiểm thử lỗi ở trước, trong và sau COMMIT cũng như các request đồng thời cùng key. Chỉ coi hệ thống sẵn sàng khi đã chứng minh được rằng outage không làm mất giao dịch đã commit, không tạo hiệu ứng trùng và không khiến retry storm làm sự cố nặng hơn.


# Định danh duy nhất trong phạm vi primary key

Trong Apache Cassandra, **`PRIMARY KEY` là định danh duy nhất của một hàng logic trong một bảng**. Nếu hai thao tác ghi có cùng *toàn bộ* giá trị primary key, chúng tác động đến cùng một hàng; Cassandra không tạo hai hàng chỉ vì lệnh `INSERT` được gọi hai lần. Ngược lại, nếu chỉ một thành phần của primary key khác nhau, đó là hai hàng logic khác nhau, ngay cả khi chúng mang cùng một `event_id`, email hoặc mã giao dịch ở một cột khác.

Phân biệt phạm vi duy nhất này rất quan trọng khi thiết kế bảng Cassandra theo truy vấn. Trong mô hình wide-column phân tán, **partition key** chọn phân vùng và tập replica, còn **clustering columns** phân biệt các hàng bên trong phân vùng. Cassandra không mặc nhiên cung cấp ràng buộc `UNIQUE` tùy ý như một số hệ quản trị quan hệ: một thuộc tính nghiệp vụ chỉ duy nhất nếu cách chọn khóa và quy trình ghi thực sự bảo vệ điều đó.

Bài học tập trung vào cách hiểu định danh hàng, xử lý ghi trùng, ghi đồng thời và kiểm soát tính duy nhất bằng CQL cũng như ứng dụng Java. Những nội dung này là nền tảng cho thiết kế bảng, mức nhất quán đọc/ghi, replication và xử lý lỗi trong hệ thống Cassandra phân tán.

Sau bài học, bạn có thể:

- Xác định tập cột tạo nên **định danh đầy đủ của một hàng**.
- Phân biệt tính duy nhất của **primary key**, **clustering key trong một phân vùng** và **mã nghiệp vụ trên toàn hệ thống**.
- Giải thích vì sao `INSERT` thông thường trong Cassandra có ngữ nghĩa **upsert**.
- Nhận biết khi nào cần `INSERT ... IF NOT EXISTS` và chi phí của **lightweight transaction (LWT)**.
- Thiết kế thao tác ghi có khả năng thử lại (*retry*) mà không vô tình tạo nhiều sự kiện.
- Triển khai ví dụ Java Driver để nhận biết kết quả ghi có điều kiện.

## 1. “Duy nhất” có nghĩa gì trong Cassandra?

Xét bảng lưu sự kiện của mỗi tài khoản theo từng ngày:

```sql
CREATE TABLE events_by_account_day (
    account_id   uuid,
    event_day    date,
    occurred_at  timestamp,
    event_id     uuid,
    event_type   text,
    amount       decimal,
    PRIMARY KEY (
        (account_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
```

Trong bảng này:

| Thành phần | Cột | Ý nghĩa |
| --- | --- | --- |
| Partition key ghép | `(account_id, event_day)` | Một tài khoản có phân vùng riêng cho từng ngày. |
| Clustering column 1 | `occurred_at` | Phân biệt/sắp xếp theo thời điểm xảy ra sự kiện. |
| Clustering column 2 | `event_id` | Phân biệt hai sự kiện có cùng `occurred_at`. |
| Primary key đầy đủ | `(account_id, event_day, occurred_at, event_id)` | **Định danh một hàng logic duy nhất** trong bảng. |
| Cột thường | `event_type`, `amount` | Nội dung của sự kiện, không tham gia xác định danh tính hàng. |

Cassandra không tạo hai hàng có cùng tuple primary key đầy đủ trong một bảng. Hàng có thể được cập nhật nhiều lần, nhưng vẫn là **cùng tọa độ logic**.

```text
Partition key: (account A, 2026-11-21)
│
├── Clustering key (08:00:00, event-1) → hàng logic X
├── Clustering key (08:00:00, event-2) → hàng logic Y
└── Clustering key (08:01:00, event-1) → hàng logic Z

X ≠ Y: khác event_id
X ≠ Z: khác occurred_at
Y ≠ Z: khác occurred_at và event_id
```

Trong một phân vùng, tuple các clustering columns xác định duy nhất một hàng. Nhưng một `event_id` vẫn có thể xuất hiện ở **nhiều thời điểm hoặc nhiều phân vùng** vì bản thân nó không phải toàn bộ primary key.

> **Quy tắc cốt lõi:** Cassandra bảo đảm mỗi **tổ hợp primary key** có tối đa một hàng logic hiện hành trong một bảng. Điều này **không** đồng nghĩa mọi cột nằm trong primary key đều có giá trị duy nhất khi xét riêng lẻ.

## 2. Phạm vi duy nhất của từng cách khai báo khóa

Cú pháp dấu ngoặc của CQL quyết định chính xác phạm vi uniqueness.

```sql
-- Ví dụ A: chỉ user_id là primary key và partition key.
PRIMARY KEY (user_id)

-- Ví dụ B: user_id là partition key; event_id là clustering column.
PRIMARY KEY (user_id, event_id)

-- Ví dụ C: partition key ghép (tenant_id, user_id).
PRIMARY KEY ((tenant_id, user_id))

-- Ví dụ D: partition key ghép, có clustering columns.
PRIMARY KEY ((tenant_id, user_id), event_day, event_id)
```

| Khai báo | Khi nào hai bản ghi trùng primary key? | Điều **không** được bảo đảm |
| --- | --- | --- |
| A | Cùng `user_id` | Không cấm trùng email ở hai `user_id` khác nhau. |
| B | Cùng `user_id` **và** `event_id` | Không cấm `event_id` xuất hiện ở hai user khác nhau. |
| C | Cùng `tenant_id` **và** `user_id` | Không cấm `user_id` xuất hiện ở tenant khác. |
| D | Cùng `tenant_id`, `user_id`, `event_day` **và** `event_id` | Không cấm cùng `event_id` ở ngày khác hoặc user khác. |

Một điều dễ nhầm:

```sql
PRIMARY KEY (tenant_id, user_id, event_id)
```

Ở đây chỉ `tenant_id` là partition key; `user_id` và `event_id` là clustering columns. **Tính duy nhất của hàng** vẫn dựa trên cả ba cột. Sự khác biệt so với `PRIMARY KEY ((tenant_id, user_id), event_id)` nằm ở cách chia phân vùng và các truy vấn được hỗ trợ.

### Trường hợp không có clustering column

```sql
CREATE TABLE customer_by_id (
    customer_id uuid PRIMARY KEY,
    email text,
    display_name text
);
```

Một `customer_id` chỉ định một hàng. Ghi lại với `customer_id` đó là thao tác trên hàng cũ, không tạo hàng thứ hai.

### Trường hợp có clustering columns

```sql
CREATE TABLE messages_by_conversation (
    conversation_id uuid,
    sent_at timestamp,
    message_id uuid,
    sender_id uuid,
    body text,
    PRIMARY KEY (conversation_id, sent_at, message_id)
);
```

Một cuộc hội thoại có nhiều hàng tin nhắn nhờ các clustering columns. Hai tin nhắn cùng `sent_at` vẫn là hai hàng nếu `message_id` khác nhau. Tuy nhiên, nếu cùng `message_id` nhưng khác `sent_at`, chúng vẫn được xem là **hai hàng**. Muốn dùng `message_id` làm định danh duy nhất trên toàn hệ thống, chỉ đặt nó làm một thành phần clustering key **chưa đủ**.

## 3. Tạo hai hàng hay cập nhật cùng một hàng?

Dùng bảng `events_by_account_day`, giả sử có một sự kiện ở thời điểm 09:00:00 UTC:

```sql
INSERT INTO events_by_account_day (
    account_id, event_day, occurred_at, event_id, event_type, amount
) VALUES (
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'purchase',
    120.00
);
```

Ghi tiếp **cùng tuple primary key**, thay đổi `amount`:

```sql
INSERT INTO events_by_account_day (
    account_id, event_day, occurred_at, event_id, event_type, amount
) VALUES (
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'purchase',
    125.00
);
```

Đây là **upsert**: nếu hàng chưa có, Cassandra tạo hàng; nếu đã có, nó ghi các giá trị cột được chỉ định vào cùng hàng logic. Trong tình huống ghi tuần tự, không có xung đột và lần ghi sau có write timestamp lớn hơn, `amount` đọc ra sẽ là `125.00`.

Truy vấn xác định hàng theo đủ primary key:

```sql
SELECT event_type, amount
FROM events_by_account_day
WHERE account_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T09:00:00Z'
  AND event_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Kết quả chỉ có **tối đa một hàng logic** tương ứng với tuple này.

Nếu đổi `event_id` sang một UUID khác, Cassandra có thể tạo thêm hàng trong **cùng phân vùng**. Nếu đổi `event_day`, đó là một **phân vùng khác**. Nếu đổi `occurred_at`, đó là hàng khác ngay cả khi `event_id` không đổi.

### `INSERT` không có nghĩa “chỉ thêm nếu chưa tồn tại”

Khác với các tình huống dùng ràng buộc duy nhất trong SQL quan hệ, câu lệnh `INSERT` thông thường của Cassandra **không tự báo lỗi vì trùng primary key**. Nó thực hiện ghi/upsert.

```sql
-- Nếu hàng đã tồn tại, vẫn có thể cập nhật giá trị amount:
UPDATE events_by_account_day
SET amount = 130.00
WHERE account_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND occurred_at = '2026-11-21T09:00:00Z'
  AND event_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

`UPDATE` thông thường trong Cassandra cũng có thể ghi dữ liệu của một khóa chưa tồn tại (upsert). Vì vậy, không thể chỉ dựa vào tên lệnh `INSERT` hay `UPDATE` để suy ra rằng hệ thống đã kiểm tra tồn tại trước khi ghi.

## 4. Ghi trùng và cập nhật từng cột: điểm quan trọng của upsert

Dữ liệu trong Cassandra có write timestamp ở mức cell. Hai lần ghi cùng primary key không nhất thiết tạo một thao tác “thay thế toàn bộ bản ghi” theo nghĩa đối tượng Java.

Ví dụ, sau khi đã có một hàng, ta chỉ ghi lại `amount`:

```sql
INSERT INTO events_by_account_day (
    account_id, event_day, occurred_at, event_id, amount
) VALUES (
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    140.00
);
```

Trường `event_type` **không được đề cập** trong lệnh này. Giá trị cũ của `event_type` không bị xóa chỉ vì câu lệnh thiếu cột đó. Điều này khác với việc gửi `null` cho cột, vốn có thể tạo tombstone theo ngữ nghĩa CQL.

Nếu hai client cùng ghi một cell và các replica nhận lệnh theo thứ tự khác nhau, Cassandra phân giải phiên bản bằng write timestamp và các quy tắc giải quyết hòa timestamp. Do đó:

- “Lệnh nào hoàn thành sau theo đồng hồ ứng dụng” không nhất thiết là “lệnh thắng” trong mọi trường hợp.
- Các cột khác nhau trong cùng hàng có thể có **write timestamp khác nhau**.
- Ghi cùng primary key với dữ liệu khác nhau trong nhiều request không tự tạo ra giao dịch cập nhật đối tượng nguyên khối.
- Khi retry sau timeout, kết quả lệnh cũ có thể **đã được áp dụng**, dù client không nhận được xác nhận.

Đối với event log, một hành vi an toàn hơn là gắn mỗi sự kiện nghiệp vụ với **một định danh ổn định** và chỉ ghi một nội dung nhất quán cho định danh ấy. Nếu cần từ chối ghi khi khóa đã tồn tại, phải dùng ghi có điều kiện.

## 5. Khi nào cần `INSERT ... IF NOT EXISTS`?

Cassandra hỗ trợ **lightweight transaction (LWT)** thông qua câu lệnh điều kiện, ví dụ `IF NOT EXISTS`. Điều kiện được kiểm tra theo giao thức đồng thuận Paxos, giúp hai client cùng cạnh tranh **một primary key** không thể cùng thành công trong việc tạo mới hàng đó.

```sql
INSERT INTO events_by_account_day (
    account_id, event_day, occurred_at, event_id, event_type, amount
) VALUES (
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'purchase',
    120.00
)
IF NOT EXISTS;
```

Khi hàng chưa tồn tại, điều kiện có thể được áp dụng thành công; khi hàng đã tồn tại, Cassandra không ghi lại dữ liệu của hàng đó theo lệnh `INSERT` có điều kiện và trả về trạng thái không áp dụng.

CQL trả kết quả có cột `[applied]`:

```text
[applied]
---------
true       -- Điều kiện đạt, bản ghi được tạo
```

Hoặc, nếu cùng khóa đã tồn tại:

```text
[applied] | ...
----------+----
false     | ... -- Các giá trị hiện hành có thể xuất hiện trong kết quả
```

Bảng hiển thị chỉ minh họa. Tập cột được trả kèm `[applied]` phụ thuộc câu lệnh và kết quả; nên kiểm tra trường `[applied]` thay vì dựa vào thứ tự cột.

### Vì sao không dùng LWT cho mọi bản ghi?

LWT phải thực hiện thêm các bước phối hợp/đồng thuận và thường có độ trễ, chi phí cao hơn ghi thông thường. Chỉ nên dùng khi nghiệp vụ **thực sự yêu cầu kiểm tra tồn tại một cách nguyên tử**.

| Nhu cầu | Cách tiếp cận phù hợp |
| --- | --- |
| Ghi cảm biến nhiều lần, cùng khóa có thể cập nhật giá trị mới | Ghi thông thường/upsert nếu semantics cập nhật là chấp nhận được. |
| Không được ghi đè payload đã chấp nhận cho cùng `event_id` và khóa | `INSERT ... IF NOT EXISTS` hoặc cơ chế kiểm soát phiên bản phù hợp. |
| Lấy khóa tự nhiên/mã giao dịch duy nhất cho một nghiệp vụ | Xác định khóa đại diện đúng phạm vi; cân nhắc LWT để cấp phát/giữ chỗ. |
| Chặn trùng trên một cột không thuộc primary key | Phải mô hình hóa thêm đường ghi kiểm tra bằng khóa riêng; LWT trên bảng gốc không tự kiểm tra cột đó ở mọi hàng. |

LWT có phạm vi phối hợp theo partition key đang thao tác. **Không** suy ra rằng hai bảng hoặc nhiều phân vùng khác nhau được cập nhật nguyên tử chỉ vì từng câu lệnh riêng lẻ có `IF NOT EXISTS`.

### Timeout của LWT cũng có thể cho kết quả chưa rõ

Nếu client nhận timeout, không nên lập tức kết luận ghi thất bại. Hành động có thể đã được áp dụng tại cluster nhưng phản hồi không đến kịp.

Khi thử lại, hãy sử dụng **đúng khóa và payload nghiệp vụ cũ**. Nếu lần retry nhận `[applied] = false`, cần đọc/đối chiếu giá trị hiện hành: đó có thể chính là bản ghi được tạo bởi lần gọi trước, hoặc do một client cạnh tranh. Kết quả `false` một mình **không** chứng minh ai đã tạo hàng.

## 6. Tính duy nhất của primary key khác gì tính duy nhất nghiệp vụ?

Giả sử hệ thống yêu cầu mỗi email chuẩn hóa chỉ thuộc **một user trên toàn ứng dụng**. Bảng sau không bảo đảm yêu cầu ấy:

```sql
CREATE TABLE users_by_id (
    user_id uuid PRIMARY KEY,
    email_normalized text,
    display_name text
);
```

Hai `user_id` khác nhau hoàn toàn có thể chứa cùng `email_normalized`. Cassandra không có ràng buộc `UNIQUE(email_normalized)` độc lập như trong nhiều hệ quản trị quan hệ.

Một mô hình phổ biến là tạo bảng **giữ quyền sở hữu email** bằng chính email làm primary key:

```sql
CREATE TABLE email_owner_by_address (
    email_normalized text PRIMARY KEY,
    user_id uuid
);
```

Khi đăng ký, thử giữ quyền sở hữu email:

```sql
INSERT INTO email_owner_by_address (
    email_normalized, user_id
) VALUES (
    'alice@example.com',
    8817a208-1858-4144-86e9-b24d9083e478
)
IF NOT EXISTS;
```

Vì `email_normalized` là primary key duy nhất của bảng claim, các yêu cầu đăng ký **cùng một chuỗi email chuẩn hóa** cạnh tranh trên cùng một hàng. LWT giúp chỉ một yêu cầu tạo claim thành công trong điều kiện cạnh tranh.

Tuy nhiên, thiết kế này có giới hạn quan trọng:

1. **Chuẩn hóa phải thống nhất** ở mọi nơi ghi/đọc: chữ hoa, chữ thường, Unicode, khoảng trắng và chính sách tên miền/email cần được xử lý theo yêu cầu sản phẩm. Hai chuỗi khác nhau tạo hai primary key khác nhau.
2. `email_owner_by_address` và `users_by_id` là **hai bảng khác nhau**. Tạo claim thành công không tự tạo user profile cùng lúc theo giao dịch nguyên tử đa bảng.
3. Nếu ghi user profile thất bại sau khi giữ email, hệ thống có thể có **claim mồ côi**. Nếu ghi profile trước rồi giữ email thất bại, có thể có **profile chưa hợp lệ**.
4. Cần định nghĩa quy trình trạng thái (*reserved*, *active* nếu dùng), retry nhất quán, kiểm tra đối chiếu và tác vụ phục hồi khi một bước thành công còn bước tiếp theo thất bại.
5. Nếu xóa claim hoặc để TTL hết hạn, email có thể trở lại trạng thái được phép cấp phát, dù dữ liệu profile cũ vẫn còn. Việc tái sử dụng phải theo quy tắc nghiệp vụ rõ ràng.

Đây là ví dụ về **thiết kế dữ liệu theo truy vấn và ràng buộc nghiệp vụ** trong Cassandra. Không nên quảng bá bảng claim như một transaction xuyên bảng hoàn chỉnh.

## 7. Idempotency khi retry: chọn ID trước khi gửi lệnh

Trong hệ thống phân tán, thao tác ghi có thể timeout hoặc kết nối bị ngắt sau khi server đã xử lý. Client thường cần thử lại để đảm bảo tiến trình nghiệp vụ. Nếu mỗi lần retry tạo ra **một primary key mới**, hệ thống có thể nhân bản sự kiện.

### Cách dễ tạo trùng sự kiện

```text
Yêu cầu nghiệp vụ: ghi sự kiện chuyển tiền T

Lần gửi 1: event_id = UUID-A, client timeout
Lần gửi 2: event_id = UUID-B, client nhận thành công

Nếu cả hai lần ghi được áp dụng:
    -> hai primary key khác nhau
    -> hai hàng sự kiện
```

Nếu dùng `now()` cho clustering key `timeuuid`, nó tạo giá trị mới ở mỗi lần thực thi; vì vậy retry `INSERT` với `now()` **không tự đảm bảo idempotency**.

### Cách giữ nguyên định danh logic

```text
Yêu cầu nghiệp vụ: ghi sự kiện chuyển tiền T
     |
     v
Tạo/tra cứu event_id ổn định cho T = UUID-A
     |
     +-- Lần gửi 1: full primary key (..., UUID-A)
     |
     +-- Lần gửi 2: full primary key (..., UUID-A)
     |
     v
Cùng tọa độ hàng logic; không tạo hàng thứ hai vì retry.
```

Điều kiện: giữ nguyên **tất cả** các thành phần primary key, bao gồm partition key, bucket thời gian và clustering timestamp. Chỉ giữ nguyên `event_id` nhưng tính lại `occurred_at` hoặc `event_day` có thể vẫn tạo hàng khác.

Một chiến lược thực tế:

- Dùng định danh nghiệp vụ ổn định `event_id`, được tạo **một lần cho sự kiện** hoặc suy ra từ idempotency key của request.
- Giữ `occurred_at` và `event_day` nhất quán giữa các lần retry.
- Ghi cùng payload cho cùng định danh logic, hoặc dùng LWT nếu cấm thay đổi một bản ghi đã được chấp nhận.
- Kiểm tra kết quả khi timeout mơ hồ; không suy đoán client timeout nghĩa là cluster chưa ghi.
- Với thao tác tài chính hoặc side effect bên ngoài, phân biệt “không tạo hai hàng Cassandra” với “thực hiện đúng một lần toàn bộ nghiệp vụ” — hai yêu cầu này **không tương đương**.

**Lưu ý:** upsert với khóa ổn định giúp không tạo thêm hàng, nhưng việc gửi lại `INSERT` có write timestamp/TTL mới có thể ảnh hưởng thời gian hết hạn hoặc xung đột ghi. Nếu logic yêu cầu “chỉ áp dụng một lần”, cần cơ chế điều kiện hoặc điều phối phù hợp.

## 8. Đổi định danh và xóa dữ liệu

Primary key là **tọa độ** của hàng. Không thể xem `UPDATE` một thành phần primary key như việc sửa một cột thường.

Ví dụ, nếu `event_day` đã ghi sai, việc sửa đúng thường là:

1. Ghi hàng với primary key **mới** có `event_day` đúng.
2. Kiểm tra kết quả và các phụ thuộc nghiệp vụ.
3. Xóa hàng cũ theo **đầy đủ primary key cũ** nếu cần.

```sql
-- Xóa hàng sự kiện theo đúng định danh đầy đủ cũ:
DELETE FROM events_by_account_day
WHERE account_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-21T09:00:00Z'
  AND event_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Cassandra dùng **tombstone** để biểu diễn xóa; compaction và cơ chế repair/tombstone cần xử lý dữ liệu đã xóa trên các replica. Thao tác ghi hàng mới rồi xóa hàng cũ ở **hai partition keys khác nhau** không tạo thành transaction nguyên tử đa phân vùng.

TTL cũng ảnh hưởng đến phạm vi tồn tại của hàng: nếu các cell hết TTL hoặc bị xóa, trạng thái “đã tồn tại một bản ghi từ trước” không tự được lưu vĩnh viễn. Một `INSERT ... IF NOT EXISTS` trong tương lai có thể được chấp nhận sau khi hàng cũ không còn tồn tại theo trạng thái dữ liệu tại thời điểm kiểm tra. Nếu cần **không tái sử dụng mã nghiệp vụ mãi mãi**, phải lưu một bản ghi định danh/claim có vòng đời thích hợp hoặc quy trình riêng; không dựa vào bảng event có TTL ngắn.

## 9. Ứng dụng Java: ghi có điều kiện theo primary key

Ví dụ dưới đây dùng API Java Driver 4.x, giả định `CqlSession` đã kết nối và keyspace chứa bảng `events_by_account_day`. Một sự kiện được đại diện bằng **full primary key** có cùng giá trị trên các lần gọi.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class EventRepository {
    private final CqlSession session;
    private final PreparedStatement insertIfAbsent;

    public EventRepository(CqlSession session) {
        this.session = session;
        this.insertIfAbsent = session.prepare(
            "INSERT INTO events_by_account_day " +
            "(account_id, event_day, occurred_at, event_id, event_type, amount) " +
            "VALUES (?, ?, ?, ?, ?, ?) IF NOT EXISTS"
        );
    }

    public boolean createIfAbsent(
            UUID accountId,
            LocalDate eventDay,
            Instant occurredAt,
            UUID eventId,
            String eventType,
            BigDecimal amount) {

        ResultSet result = session.execute(insertIfAbsent.bind(
            accountId, eventDay, occurredAt, eventId, eventType, amount
        ));
        return result.wasApplied();
    }
}
```

Sử dụng:

```java
UUID accountId = UUID.fromString(
    "327a71e9-f562-4b54-94b9-2138a9e30b12"
);
UUID eventId = UUID.fromString(
    "8817a208-1858-4144-86e9-b24d9083e478"
); // ID ổn định của một sự kiện, tái dùng khi retry.

boolean created = repository.createIfAbsent(
    accountId,
    LocalDate.of(2026, 11, 21),
    Instant.parse("2026-11-21T09:00:00Z"),
    eventId,
    "purchase",
    new BigDecimal("120.00")
);
```

Giải thích:

- `result.wasApplied() == true` cho biết lần thực thi LWT này tạo hàng khi điều kiện đạt.
- `false` cho biết hàng đã tồn tại tại thời điểm kiểm tra điều kiện; ứng dụng cần xem xét đối chiếu dữ liệu nếu đó có thể là một lần ghi thành công trước đó.
- Nếu yêu cầu timeout hoặc gặp lỗi mạng, **không** được suy ra `false` hay `true`; kết quả chưa xác định đối với client. Retry phải giữ nguyên tuple khóa và payload.
- Truy vấn LWT có chi phí đồng thuận; cần cân nhắc latency, thông số timeout và chính sách retry của ứng dụng.

Khi yêu cầu mức nhất quán cụ thể, driver cho phép cấu hình **consistency level** cho truy vấn và **serial consistency** cho LWT (chẳng hạn `SERIAL` hoặc `LOCAL_SERIAL` theo topology). Cần chọn chính sách phù hợp chiến lược replication của keyspace; tăng consistency không biến câu lệnh không điều kiện thành phép kiểm tra “chưa tồn tại”.

### Ghi thường với ID cố định

Nếu upsert là ngữ nghĩa mong muốn, cùng phương thức có thể thay câu CQL bằng `INSERT ... VALUES (...)` không có `IF NOT EXISTS`. Khi đó không có `wasApplied()` mang ý nghĩa “tạo mới”, vì ghi thông thường **không thực hiện điều kiện tồn tại**. Thành công của lệnh ghi chỉ xác nhận thao tác theo consistency level đã chọn.

## 10. Những hiểu lầm thường gặp

| Nhận định | Vì sao sai/thiếu? | Điều cần làm |
| --- | --- | --- |
| “Có `PRIMARY KEY (..., event_id)` là `event_id` duy nhất trên toàn bảng.” | Các thành phần khác có thể khác nhau trong hai hàng. | Xác định **toàn bộ tuple primary key** và phạm vi nghiệp vụ cần duy nhất. |
| “`INSERT` trùng khóa phải báo lỗi như SQL.” | `INSERT` thường là upsert. | Dùng `IF NOT EXISTS` khi cần từ chối ghi đè. |
| “Chỉ cần cùng UUID lúc retry.” | Bucket ngày hoặc timestamp clustering có thể thay đổi giữa các lần gọi. | Cố định **toàn bộ primary key**. |
| “Đặt email là cột thường trong bảng user đảm bảo không trùng.” | Cassandra không tự bảo vệ uniqueness của regular column. | Tạo cơ chế claim/index theo email với ràng buộc và LWT thích hợp. |
| “LWT ở bảng claim và ghi bảng profile là một transaction xuyên bảng.” | Hai thao tác có thể thành công/thất bại độc lập. | Thiết kế trạng thái và phục hồi khi ghi một phần. |
| “Client timeout nghĩa là ghi không diễn ra.” | Phản hồi có thể mất sau khi cluster đã xử lý. | Retry an toàn và đối chiếu trạng thái hiện hành. |
| “Tăng consistency là đủ bảo đảm một mã chỉ được tạo một lần.” | Consistency level thường không thay thế điều kiện tạo mới. | Dùng khóa đúng phạm vi, LWT hoặc cơ chế phối hợp cần thiết. |
| “Xóa một hàng là mã đó vĩnh viễn không thể tái sử dụng.” | Hàng/tombstone/TTL có vòng đời; trạng thái tồn tại có thể thay đổi. | Lưu claim tồn tại lâu dài nếu nghiệp vụ cấm tái sử dụng. |
| “Hai lần ghi cùng primary key phải thay thế nguyên bản ghi.” | Cassandra cập nhật theo cột/cell và timestamp, cột bỏ qua vẫn có thể giữ giá trị. | Hiểu upsert theo cell; định nghĩa quy tắc cập nhật rõ ràng. |

## 11. Bài tập tự kiểm tra

Xét bảng:

```sql
CREATE TABLE invoice_events_by_month (
    tenant_id      text,
    month_bucket   text,
    invoice_id     uuid,
    event_time     timestamp,
    event_id       uuid,
    event_kind     text,
    PRIMARY KEY (
        (tenant_id, month_bucket),
        invoice_id,
        event_time,
        event_id
    )
);
```

Giả sử có các hàng sau:

| Hàng | `tenant_id` | `month_bucket` | `invoice_id` | `event_time` | `event_id` |
| --- | --- | --- | --- | --- | --- |
| A | acme | 2026-11 | I-1 | 09:00 | E-1 |
| B | acme | 2026-11 | I-1 | 09:00 | E-2 |
| C | acme | 2026-12 | I-1 | 09:00 | E-1 |
| D | beta | 2026-11 | I-1 | 09:00 | E-1 |
| E | acme | 2026-11 | I-1 | 09:00 | E-1 |

Các ký hiệu `I-1` và `E-1` là cách viết ngắn của giá trị UUID giả định, không phải literal CQL.

**Câu hỏi:**

1. Hàng nào trong bảng A–E có cùng primary key với nhau?
2. A và B có cùng phân vùng không? Chúng có thể tồn tại cùng lúc không?
3. A và C có cùng `event_id` nhưng khác tháng; chúng có bị Cassandra chặn vì trùng ID không?
4. Dùng `INSERT` thường để ghi E sau A: Cassandra tạo thêm hàng hay tác động lên hàng A?
5. Nếu dùng `INSERT ... IF NOT EXISTS` cho E khi A đã tồn tại, `[applied]` dự kiến là gì?
6. Nếu một ứng dụng cần mỗi `invoice_id` duy nhất toàn hệ thống, schema trên đã bảo đảm chưa?
7. Thao tác ghi `amount` vào bảng khác sau khi claim thành công có tự động nguyên tử với LWT của claim không?

**Đáp án:**

1. **A và E** trùng toàn bộ tuple `(tenant_id, month_bucket, invoice_id, event_time, event_id)`.
2. **Có** cùng phân vùng vì chung `(tenant_id, month_bucket)`; **có** thể cùng tồn tại vì `event_id` khác.
3. **Không bị chặn**: khác `month_bucket` nên khác primary key và khác phân vùng.
4. `INSERT` thường sẽ **upsert hàng A**, không tạo hàng mới.
5. **`[applied] = false`**, vì hàng có primary key tương ứng đã tồn tại.
6. **Chưa**. Cùng `invoice_id` vẫn có thể xuất hiện ở tenant/tháng hoặc hàng sự kiện khác. Cần định nghĩa “invoice duy nhất” bằng bảng định danh phù hợp với nghiệp vụ.
7. **Không**. Các bảng và phân vùng khác nhau cần được phối hợp và phục hồi khi ghi một phần.

## 12. Nguyên tắc thiết kế mang vào thực hành

- Tính duy nhất trong Cassandra luôn được xét theo **toàn bộ primary key**, với phạm vi một bảng.
- **Partition key** xác định phân vùng; **clustering columns** xác định hàng trong phân vùng. Giá trị một clustering column riêng lẻ không mặc nhiên duy nhất toàn bảng.
- `INSERT` và `UPDATE` thông thường có semantics **upsert**, không tự từ chối khóa đã tồn tại.
- `IF NOT EXISTS` dùng LWT để thực hiện **tạo mới có điều kiện** ở đúng khóa; cần trả giá bằng chi phí phối hợp và vẫn phải xử lý timeout mơ hồ.
- Idempotency khi retry đòi hỏi **ổn định toàn bộ tuple khóa** và ngữ nghĩa payload, không chỉ tạo ngẫu nhiên một UUID mới ở mỗi lần gọi.
- Nếu một **thuộc tính nghiệp vụ** như email, số hóa đơn hoặc mã giao dịch phải duy nhất ngoài phạm vi khóa hiện tại, hãy tạo cơ chế định danh/claim phù hợp và định nghĩa rõ luồng ghi, khôi phục cùng vòng đời dữ liệu.
- Với dữ liệu được nhân bản, cần phân biệt **tính duy nhất logic của hàng**, **tính đồng thuận của ghi có điều kiện**, **consistency level của đọc/ghi** và **việc hoàn thành toàn bộ nghiệp vụ** — đây là các vấn đề khác nhau.

Hiểu đúng “duy nhất trong phạm vi primary key” giúp bạn tránh các lỗi nhân bản sự kiện, ghi đè ngoài ý muốn và kỳ vọng không đúng về uniqueness trong Cassandra. Từ nền tảng này, bạn có thể tiếp tục thiết kế bảng theo truy vấn, xây luồng ghi an toàn từ ứng dụng Java và chọn cơ chế replication, consistency cùng xử lý lỗi phù hợp.


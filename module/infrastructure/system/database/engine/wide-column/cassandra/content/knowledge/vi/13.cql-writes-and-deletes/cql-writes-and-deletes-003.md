# Chọn cột cập nhật và ảnh hưởng đến các cột không được gửi trong Cassandra

Khi cập nhật một hồ sơ khách hàng, ứng dụng có thể chỉ biết số điện thoại mới mà không biết tên, email hoặc các thiết lập hiện tại. Trong Apache Cassandra, lựa chọn **cột nào xuất hiện trong mutation** quyết định cột nào thực sự được ghi. Đây là nền tảng để triển khai cập nhật một phần an toàn bằng CQL và Java Driver.

Bài thuộc chương **Ghi và xóa bằng CQL** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Cassandra là hệ thống phân tán sử dụng mô hình wide-column: **partition key** xác định vị trí phân vùng và **full primary key** định danh hàng. Việc cập nhật từng cột phải được hiểu cùng cơ chế ghi theo timestamp, replication, TTL và tombstone; ứng dụng Java cần phân biệt chính xác giá trị mới với trường không được gửi.

Sau bài này, bạn có thể:

- Viết `INSERT` hoặc `UPDATE` chỉ chạm đến các cột cần thay đổi.
- Dự đoán trạng thái sau ghi khi một số cột vắng mặt trong câu CQL.
- Phân biệt **cột bị bỏ qua**, **cột được gán NULL**, **tham số UNSET**, và **giá trị mới**.
- Hiểu trường hợp gán toàn bộ collection khác với sửa một phần tử collection.
- Kiểm soát ảnh hưởng của TTL, timestamp và ghi cạnh tranh đến những cột khác nhau.
- Viết prepared statement Java an toàn cho API cập nhật từng phần.

## 1. Bảng ví dụ và trạng thái ban đầu

Giả sử ứng dụng quản lý tài khoản cần đọc hồ sơ bằng `account_id`. Keyspace `demo` được giả định đã có:

```sql
CREATE TABLE demo.accounts_by_id (
    account_id uuid PRIMARY KEY,
    display_name text,
    email text,
    phone text,
    locale text,
    notification_opt_in boolean,
    preferences map<text, text>,
    tags set<text>,
    updated_at timestamp
);
```

Ở ví dụ này, `account_id` là partition key và cũng là full primary key. Các trường còn lại là cột thường. Mỗi lần ghi với cùng `account_id` sẽ nhắm tới cùng hàng logic; Cassandra không tự động sinh một hàng khác cho câu `INSERT` trùng khóa.

Khởi tạo hàng ban đầu:

```sql
INSERT INTO demo.accounts_by_id (
    account_id, display_name, email, phone, locale,
    notification_opt_in, preferences, tags
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'Mai Anh',
    'mai@example.test',
    '0900000001',
    'vi-VN',
    true,
    {'theme': 'light', 'digest': 'daily'},
    {'customer', 'beta'}
);

SELECT *
FROM demo.accounts_by_id
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Trạng thái cần ghi nhớ:

| Cột | Giá trị sau `INSERT` ban đầu |
| --- | --- |
| `display_name` | `'Mai Anh'` |
| `email` | `'mai@example.test'` |
| `phone` | `'0900000001'` |
| `locale` | `'vi-VN'` |
| `notification_opt_in` | `true` |
| `preferences` | `{'theme': 'light', 'digest': 'daily'}` |
| `tags` | `{'customer', 'beta'}` |
| `updated_at` | `null` (chưa từng được ghi) |

Để tiện theo dõi các bước, giả sử không có client khác cùng ghi, không có TTL của bảng và không có timestamp tự cấp bất thường.

## 2. UPDATE chọn cột nào thì chỉ ghi cột đó

Yêu cầu: thay số điện thoại, giữ nguyên mọi thông tin khác.

```sql
UPDATE demo.accounts_by_id
SET phone = '0900000099'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Một câu `UPDATE` có phần `SET` mô tả những cột thực sự được ghi. Trong ví dụ:

- **Cột được ghi:** `phone` nhận giá trị mới.
- **Cột không nằm trong `SET`:** `display_name`, `email`, `locale`, `notification_opt_in`, `preferences`, `tags`, `updated_at` không bị chính lệnh này sửa hoặc xóa.
- **Khóa:** `account_id` xác định hàng đích; không thể sửa thành phần primary key bằng `SET`.

Trạng thái sau lệnh:

| Cột | Trước | Sau |
| --- | --- | --- |
| `phone` | `'0900000001'` | `'0900000099'` |
| `email` | `'mai@example.test'` | `'mai@example.test'` |
| `locale` | `'vi-VN'` | `'vi-VN'` |
| `updated_at` | `null` | `null` |

Không có cập nhật ngầm vào `updated_at`: nếu ứng dụng muốn ghi dấu thời điểm sửa, phải thêm cột đó vào mutation:

```sql
UPDATE demo.accounts_by_id
SET phone = '0900000088',
    updated_at = '2026-11-21 09:15:00+0700'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Thời điểm ở đây chỉ là giá trị ví dụ của cột ứng dụng. Nó **khác** với timestamp ghi mà Cassandra dùng để hòa giải phiên bản các cell.

### Một điểm dễ hiểu sai về “giữ nguyên”

“Cột không được gửi sẽ giữ nguyên” nghĩa là **mutation đang xét không ghi đè cột đó**. Giá trị vẫn có thể thay đổi vì client khác đang ghi, vì TTL của giá trị cũ hết hạn hoặc vì quá trình hòa giải replica làm lộ ra một phiên bản thắng theo timestamp. Không nên diễn giải đây là cam kết một ảnh chụp toàn hàng luôn bất biến trong hệ thống phân tán.

## 3. INSERT cũng có thể chỉ ghi một số cột

Trong Cassandra, `INSERT` thông thường cũng là **upsert**, không phải thao tác thay thế toàn bộ hàng:

```sql
INSERT INTO demo.accounts_by_id (account_id, locale)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'en-US'
);
```

Nếu cùng khóa đã tồn tại, `locale` được ghi lại thành `'en-US'`. Những cột khác, kể cả `phone` và `email`, không bị xóa chỉ vì chúng không có trong danh sách cột `INSERT`.

So sánh:

| Câu lệnh | Cột được ghi | Cột bị bỏ qua |
| --- | --- | --- |
| `INSERT INTO ... (account_id, locale) VALUES (...)` | `locale` | Các cột thường còn lại |
| `UPDATE ... SET locale = ... WHERE account_id = ...` | `locale` | Các cột thường còn lại |
| `UPDATE ... SET locale = ..., phone = ... WHERE ...` | `locale`, `phone` | Các cột thường khác |

Với bảng ví dụ, cập nhật cột thường bằng `UPDATE` cần định vị hàng thông qua primary key. Trong bảng có khóa ghép, hãy xác định đầy đủ các thành phần khóa cho hàng muốn ghi; không thể thay điều kiện khóa bằng `WHERE email = '...'` vì email ở đây là cột thường. Bảng có cột `static` có quy tắc cập nhật riêng ở cấp phân vùng, không áp dụng cho ví dụ này.

**Khi nào chọn INSERT hay UPDATE?** `UPDATE ... SET` thường dễ diễn đạt API “chỉnh sửa vài trường”, còn `INSERT` có thể phù hợp với việc nạp/upsert dữ liệu có sẵn. Việc chỉ cho phép tạo mới hoặc chỉ cho phép sửa hàng đã tồn tại **không** được quyết định bởi tên câu lệnh; hai nhu cầu đó phải dùng điều kiện thích hợp như `IF NOT EXISTS` hoặc `IF EXISTS`.

## 4. Phân biệt rõ ba trạng thái của một trường

Khi triển khai PATCH, cần xác định ba trường hợp:

| Đầu vào | Ý nghĩa của yêu cầu | Cách biểu đạt khi ghi |
| --- | --- | --- |
| Không có trường `email` | Không thay email | Không nêu `email` trong CQL, hoặc bind marker bằng **UNSET** |
| Có `"email": "new@example.test"` | Đổi email | Ghi giá trị mới cho `email` |
| Có `"email": null` | Xóa email (nếu hợp đồng API cho phép) | Ghi **NULL** hoặc `DELETE email`, tạo tombstone |

### Bỏ cột khỏi mutation

```sql
UPDATE demo.accounts_by_id
SET locale = 'en-US'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Lệnh trên **không** chạm `email`: Cassandra không nhận mutation cho cell email từ lệnh này.

### Gán NULL là một thao tác xóa

```sql
UPDATE demo.accounts_by_id
SET email = NULL
WHERE account_id = 11111111-1111-4111-8111-111111111111;

-- Cách diễn đạt xóa cột rõ ràng:
DELETE email
FROM demo.accounts_by_id
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Cả hai ví dụ đều diễn đạt ý định loại bỏ giá trị cũ của cột email. Chỉ chạy **một trong hai** khi thực hành; không cần xóa lặp lại. CQL `NULL` của cột thường không tương đương việc “không gửi cột”. Cassandra lưu dấu xóa (*tombstone*) để replica chưa nhận thao tác xóa không làm hồi sinh dữ liệu cũ.

Sau khi xóa có hiệu lực ở mức nhất quán đọc, `SELECT email` trả `null`. Kết quả `null` khi đọc không cho biết email **chưa từng có giá trị** hay **đã bị xóa**; hai trường hợp có thể cùng biểu hiện bằng `null` trong kết quả truy vấn.

### UNSET trong prepared statement

**UNSET** được dùng khi bind tham số trong prepared statement, với ý nghĩa **không cập nhật cột tương ứng**. Nó khác `NULL`:

```text
email bị bỏ khỏi SET / marker UNSET
    => mutation không ghi cell email.

email được bind NULL
    => mutation ghi dấu xóa cho cell email.

email được bind chuỗi mới
    => mutation ghi giá trị mới cho cell email.
```

Không bind `NULL` hoặc `UNSET` cho các thành phần khóa chính bắt buộc; primary key phải được cung cấp đúng giá trị để xác định hàng. Nếu toàn bộ cột cần sửa đều vắng mặt, ứng dụng nên coi đây là request **không có thay đổi** và tránh phát sinh một `UPDATE` không có phép gán hữu ích.

## 5. Cạm bẫy riêng của INSERT JSON

Với cú pháp theo danh sách cột, cột không xuất hiện được bỏ qua. Nhưng khi dùng `INSERT ... JSON`, cần xác định rõ cách xử lý **thuộc tính thiếu**.

```sql
-- Giữ nguyên những cột không có mặt trong JSON:
INSERT INTO demo.accounts_by_id JSON
'{"account_id":"11111111-1111-4111-8111-111111111111","locale":"ja-JP"}'
DEFAULT UNSET;
```

Trong CQL, `INSERT JSON` mặc định xử lý thuộc tính thiếu theo chính sách **DEFAULT NULL**, trừ khi chỉ định `DEFAULT UNSET`. Sự khác biệt có hậu quả lớn đối với hàng đã tồn tại:

| Cú pháp | Cột vắng mặt trong JSON | Hệ quả với hàng có sẵn |
| --- | --- | --- |
| `INSERT ... JSON '...' DEFAULT UNSET` | Bỏ qua | Giữ giá trị cũ của những cột này |
| `INSERT ... JSON '...' DEFAULT NULL` | Coi như NULL | Có thể tạo tombstone và xóa giá trị cũ |
| `INSERT ... JSON '...'` | Dùng mặc định DEFAULT NULL | Cũng cần chú ý nguy cơ xóa cột không gửi |

Ví dụ yêu cầu chỉ đổi `locale` có thể vô tình xóa `display_name`, `email` và `phone` nếu dùng JSON insert mà quên `DEFAULT UNSET`. Khi thiết kế API cập nhật một phần, nên chủ động dùng prepared `UPDATE` với các cột được chọn hoặc chỉ định `DEFAULT UNSET` khi thích hợp. Không tự động ghép trực tiếp JSON do client gửi vào câu CQL.

## 6. Collection: bỏ cả cột khác với thay một phần tử

Một cột collection có hai mức lựa chọn: **có ghi collection đó hay không**, và nếu ghi thì **ghi lại toàn bộ hay thay riêng phần tử**. Bảng ví dụ có:

- `preferences map<text, text>`: cặp khóa/giá trị cấu hình.
- `tags set<text>`: tập nhãn tài khoản.

### Không đề cập collection: collection giữ nguyên

```sql
UPDATE demo.accounts_by_id
SET phone = '0900000077'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Mutation không ghi `preferences` hoặc `tags`, nên không xóa các phần tử đang có.

### Gán cả collection: thay nội dung collection đó

```sql
UPDATE demo.accounts_by_id
SET preferences = {'theme': 'dark'}
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Với `map` không `frozen`, gán toàn bộ map mới thay thế nội dung map cũ: mục `'digest': 'daily'` sẽ không còn chỉ vì nó bị thiếu trong **giá trị map mới**. Đây là khác biệt rất quan trọng so với **bỏ qua cả cột map**.

### Cập nhật một phần tử của map

```sql
UPDATE demo.accounts_by_id
SET preferences['theme'] = 'dark'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Lệnh này chỉ sửa phần tử `'theme'` của map; mục `'digest'` không bị xóa do chính lệnh đó.

### Thêm một phần tử vào set

```sql
UPDATE demo.accounts_by_id
SET tags = tags + {'priority'}
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Đây là thao tác thêm phần tử vào set không `frozen`, không phải gán lại toàn bộ `tags`. Ngược lại, `SET tags = {'priority'}` thể hiện thay cả tập nhãn và có thể loại bỏ các nhãn trước đó. Những thao tác trên collection có hành vi và chi phí ghi/xóa riêng, cần chọn theo ý định nghiệp vụ.

| Tình huống | Kết quả dự kiến |
| --- | --- |
| `UPDATE ... SET phone = ...`, không nhắc `preferences` | Map giữ giá trị cũ |
| `SET preferences = {'theme': 'dark'}` | Thay toàn bộ map bằng giá trị được gán |
| `SET preferences['theme'] = 'dark'` | Chỉ thay một phần tử của map |
| `SET tags = tags + {'priority'}` | Thêm phần tử vào set |
| `SET tags = {'priority'}` | Thay toàn bộ set bằng tập được gán |

Với collection dạng `frozen`, giá trị thường được xử lý như một khối; không thể áp dụng mọi thao tác sửa riêng phần tử như collection không `frozen`. Hãy kiểm tra schema trước khi dùng phép cập nhật mức phần tử.

## 7. Timestamp, TTL và dữ liệu không được gửi

Để hiểu đúng tác động của một mutation, cần phân biệt ba khái niệm:

1. **Giá trị cột:** nội dung đang được quan sát khi đọc.
2. **Timestamp của cell:** thông tin Cassandra dùng để hòa giải các phiên bản ghi cạnh tranh.
3. **TTL của cell:** thời gian còn lại trước khi giá trị được xem là hết hạn.

### Cột không được gửi không nhận timestamp mới

Ví dụ hai lệnh liên tiếp:

```sql
UPDATE demo.accounts_by_id
SET display_name = 'Mai Anh Nguyễn'
WHERE account_id = 11111111-1111-4111-8111-111111111111;

UPDATE demo.accounts_by_id
SET phone = '0900000066'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Lệnh thứ hai không tự “làm mới timestamp” của `display_name`. Ta có thể kiểm tra thời điểm ghi ở mức cell:

```sql
SELECT display_name,
       WRITETIME(display_name) AS name_written_at,
       phone,
       WRITETIME(phone) AS phone_written_at
FROM demo.accounts_by_id
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

`WRITETIME` trả về timestamp tính bằng microsecond từ Unix epoch cho giá trị scalar được ghi. Đây không phải cột nghiệp vụ `updated_at` và không nhất thiết phản ánh thứ tự thời gian thực mà người dùng đã thực hiện yêu cầu nếu có sai lệch đồng hồ hoặc timestamp tùy chỉnh.

### TTL chỉ ảnh hưởng các giá trị được ghi

```sql
UPDATE demo.accounts_by_id USING TTL 1800
SET phone = '0900000055'
WHERE account_id = 11111111-1111-4111-8111-111111111111;

SELECT phone, TTL(phone),
       display_name, TTL(display_name)
FROM demo.accounts_by_id
WHERE account_id = 11111111-1111-4111-8111-111111111111;
```

Trong một bảng không có TTL mặc định:

- `phone` được ghi cùng TTL 1.800 giây; `TTL(phone)` cho biết thời gian còn lại.
- `display_name` không xuất hiện trong mutation, nên **không nhận TTL mới** từ lệnh này.
- `TTL(display_name)` thông thường là `null` nếu giá trị tên không có TTL.
- Khi TTL của `phone` hết hạn, cột này có thể đọc ra `null`, dù tên và email vẫn còn.

Nếu bảng có cấu hình `default_time_to_live`, các cột được ghi mà không chỉ định TTL riêng có thể nhận TTL mặc định. Khi ghi đè một cột đang có TTL, dữ liệu mới mang các đặc tính TTL của **lần ghi mới**. Việc này khác với cột bị bỏ qua: TTL cũ của cột bị bỏ qua vẫn tiếp tục đếm xuống.

### Cùng một cột có nhiều phiên bản cạnh tranh

Nếu hai client ghi cùng một cột:

```text
Client A: phone = '0900000002', timestamp = 2_000_000
Client B: phone = '0900000003', timestamp = 1_000_000

Khi hòa giải, giá trị của A được ưu tiên vì timestamp lớn hơn,
cho dù yêu cầu B đến sau trong thời gian thực.
```

Cassandra dùng cơ chế hòa giải theo timestamp cho các cell thông thường, thường được mô tả là *last-write-wins*. Hai client ghi **khác cột** thường không cần giành quyền trên cùng cell; mỗi cột có lịch sử ghi riêng. Nhưng cập nhật một phần không tự tạo giao dịch compare-and-set: nếu cần “chỉ đổi email khi giá trị cũ vẫn là X”, hãy dùng lệnh có `IF` thích hợp thay vì đọc trước rồi `UPDATE` không điều kiện.

Ví dụ:

```sql
UPDATE demo.accounts_by_id
SET email = 'mai.new@example.test'
WHERE account_id = 11111111-1111-4111-8111-111111111111
IF email = 'mai@example.test';
```

Đây là **lightweight transaction (LWT)**: ứng dụng phải kiểm tra kết quả `[applied]`. LWT đòi hỏi phối hợp nhiều hơn ghi thông thường, nhưng phù hợp khi điều kiện cũ là ràng buộc nghiệp vụ. `QUORUM` hay `ONE` là mức nhất quán xác nhận đọc/ghi giữa replica, không thay thế điều kiện `IF`.

## 8. Java Driver: triển khai cập nhật một phần theo sự hiện diện của trường

Trong ứng dụng Java, lỗi phổ biến nhất là biến payload chỉ chứa một trường thành mutation chứa **nhiều cột NULL**. Nguyên nhân thường nằm ở DTO nullable: khi ánh xạ JSON vào object, cả “trường không xuất hiện” lẫn “trường xuất hiện với null” có thể cùng được biểu diễn bằng Java `null`.

Ví dụ client gửi:

```json
{
  "phone": "0900000099"
}
```

Nếu backend bind `email = null` và `display_name = null` do hai trường không có trong JSON, nó sẽ vô tình xóa dữ liệu không liên quan. Cần theo dõi **presence** của từng field.

### Cách 1: CQL chỉ bao gồm các cột cần sửa

Ứng dụng kiểm tra danh sách trường hợp lệ trong request, sau đó chọn câu CQL thích hợp:

```sql
UPDATE demo.accounts_by_id
SET phone = ?
WHERE account_id = ?;
```

Đây là lựa chọn rõ ràng khi endpoint có số tổ hợp cột ít hoặc dùng các prepared statement đã định nghĩa. Tên cột phải đến từ danh sách trắng do ứng dụng kiểm soát; **không** lấy tên cột bất kỳ do client gửi rồi nối vào CQL. Giá trị phải được bind.

### Cách 2: Prepared statement cố định và UNSET

Với Apache Cassandra Java Driver 4.x, có thể chuẩn bị CQL chứa nhiều marker nhưng chỉ bind các trường được gửi. Ví dụ dưới đây giả định đã có `CqlSession session`, `UUID accountId`, và `JsonNode patch` (đối tượng JSON từ Jackson):

```java
PreparedStatement ps = session.prepare(
    "UPDATE demo.accounts_by_id " +
    "SET display_name = :display_name, " +
    "    email = :email, " +
    "    phone = :phone " +
    "WHERE account_id = :account_id"
);

BoundStatementBuilder builder = ps.boundStatementBuilder()
    .setUuid("account_id", accountId)
    .unset("display_name")
    .unset("email")
    .unset("phone");

boolean changed = false;

if (patch.has("phone")) {
    JsonNode value = patch.get("phone");
    if (value.isNull()) {
        builder.setToNull("phone");
    } else if (value.isTextual()) {
        builder.setString("phone", value.textValue());
    } else {
        throw new IllegalArgumentException("phone phai la chuoi hoac null");
    }
    changed = true;
}

if (patch.has("email")) {
    JsonNode value = patch.get("email");
    if (value.isNull()) {
        builder.setToNull("email");
    } else if (value.isTextual()) {
        builder.setString("email", value.textValue());
    } else {
        throw new IllegalArgumentException("email phai la chuoi hoac null");
    }
    changed = true;
}

if (patch.has("display_name")) {
    JsonNode value = patch.get("display_name");
    if (value.isNull()) {
        builder.setToNull("display_name");
    } else if (value.isTextual()) {
        builder.setString("display_name", value.textValue());
    } else {
        throw new IllegalArgumentException("display_name phai la chuoi hoac null");
    }
    changed = true;
}

if (changed) {
    session.execute(builder.build());
}
```

Các import cần thiết từ driver và Jackson được lược bỏ để tập trung vào logic xử lý patch. Trong ứng dụng thật, nên xác thực schema của payload, loại bỏ trường không cho phép, giới hạn độ dài và định dạng giá trị, rồi kiểm tra quyền cập nhật trước khi thực thi.

Chìa khóa của đoạn mã:

| Trạng thái JSON | Kiểm tra | Binder |
| --- | --- | --- |
| Không có khóa `email` | `patch.has("email") == false` | Giữ `unset("email")` |
| Có `"email": null` | `value.isNull()` | `setToNull("email")` |
| Có `"email": "..."` | `value.isTextual()` | `setString("email", ...)` |

Nếu API **không cho phép xóa email**, trường hợp JSON null phải được từ chối bằng validation thay vì gọi `setToNull`. Nếu request không có trường cập nhật hợp lệ, nên trả kết quả no-op hoặc lỗi validation theo hợp đồng API, tránh thực thi một mutation không mang thay đổi.

### Vấn đề tồn tại hàng và ghi lại khi lỗi mạng

`UPDATE` không điều kiện có thể tạo một hàng mới chỉ chứa những cột được cập nhật nếu khóa chưa tồn tại. Nếu yêu cầu chỉ sửa tài khoản đã có, dùng `UPDATE ... IF EXISTS` và đọc `[applied]`, hoặc áp dụng một cơ chế kiểm soát sự tồn tại phù hợp ở tầng nghiệp vụ. `SELECT` rồi `UPDATE` không điều kiện có khoảng trống tranh chấp.

Khi ghi bị timeout, không thể biết chắc mutation đã hoàn toàn thất bại: một số replica có thể đã nhận dữ liệu. Retry một cập nhật cùng khóa và cùng giá trị thường dễ kiểm soát hơn các thao tác cộng dồn, nhưng timestamp, TTL, LWT và các lần ghi song song vẫn có thể ảnh hưởng kết quả cuối. Ứng dụng cần xác định chính sách retry theo ý nghĩa nghiệp vụ.

## 9. Thực hành dự đoán thay đổi theo từng cột

Để kết quả độc lập với các ví dụ trước, dùng một UUID khác và chỉ chạy trong môi trường thực hành.

**Bước 1 — Tạo hàng ban đầu**

```sql
INSERT INTO demo.accounts_by_id (
    account_id, display_name, email, phone, locale,
    preferences, tags
)
VALUES (
    55555555-5555-4555-8555-555555555555,
    'Huy',
    'huy@example.test',
    '0911111111',
    'vi-VN',
    {'theme': 'light', 'digest': 'weekly'},
    {'standard'}
);

SELECT display_name, email, phone, locale, preferences, tags
FROM demo.accounts_by_id
WHERE account_id = 55555555-5555-4555-8555-555555555555;
```

**Bước 2 — Chỉ đổi phone**

```sql
UPDATE demo.accounts_by_id
SET phone = '0922222222'
WHERE account_id = 55555555-5555-4555-8555-555555555555;
```

Kỳ vọng: `phone` đổi, `email` vẫn là `'huy@example.test'` và `preferences` vẫn có cả `theme`, `digest`.

**Bước 3 — Chỉ sửa phần tử map**

```sql
UPDATE demo.accounts_by_id
SET preferences['theme'] = 'dark'
WHERE account_id = 55555555-5555-4555-8555-555555555555;
```

Kỳ vọng: `preferences` thành `{'theme': 'dark', 'digest': 'weekly'}`. Nếu thay bằng `SET preferences = {'theme': 'dark'}` thì `digest` sẽ bị loại bỏ.

**Bước 4 — Xóa một cột**

```sql
UPDATE demo.accounts_by_id
SET email = NULL
WHERE account_id = 55555555-5555-4555-8555-555555555555;

SELECT email, display_name, phone, preferences
FROM demo.accounts_by_id
WHERE account_id = 55555555-5555-4555-8555-555555555555;
```

Kỳ vọng: `email` đọc ra `null`; tên, điện thoại và map giữ nguyên giá trị ở bước trước.

**Bước 5 — INSERT JSON không làm mất cột chưa gửi**

```sql
INSERT INTO demo.accounts_by_id JSON
'{"account_id":"55555555-5555-4555-8555-555555555555","locale":"en-US"}'
DEFAULT UNSET;
```

Kỳ vọng: `locale` đổi sang `'en-US'`, những cột khác không bị lệnh này ghi lại. Quan sát lại hàng bằng `SELECT` để xác nhận.

### Bảng tổng kết kết quả mong đợi

| Sau bước | `email` | `phone` | `locale` | `preferences['theme']` | `preferences['digest']` |
| --- | --- | --- | --- | --- | --- |
| 1 | huy@example.test | 0911111111 | vi-VN | light | weekly |
| 2 | huy@example.test | 0922222222 | vi-VN | light | weekly |
| 3 | huy@example.test | 0922222222 | vi-VN | dark | weekly |
| 4 | null | 0922222222 | vi-VN | dark | weekly |
| 5 | null | 0922222222 | en-US | dark | weekly |

Những kỳ vọng này giả định không có ghi cạnh tranh, TTL hoặc timestamp đặc biệt. Dùng ví dụ để rèn cách dự đoán **cột nào được tác động**, sau đó mới quan sát bằng CQL.

## 10. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Bind Java `null` cho mọi field thiếu trong PATCH | Xóa hàng loạt cột không được yêu cầu, sinh tombstone | Theo dõi sự hiện diện trường; dùng `UNSET` hoặc bỏ cột khỏi CQL |
| Dùng `INSERT JSON` và quên `DEFAULT UNSET` | Các thuộc tính không có trong JSON có thể bị coi là NULL | Chỉ rõ `DEFAULT UNSET` hoặc dùng prepared `UPDATE` |
| Gán cả map/set khi chỉ muốn đổi một phần tử | Những phần tử khác bị loại bỏ | Dùng cú pháp cập nhật phần tử/collection phù hợp |
| Giả sử `updated_at` tự đổi khi sửa cột khác | Audit nghiệp vụ bị sai lệch | Ghi `updated_at` chủ động khi cần |
| Giả sử `UPDATE` chỉ sửa hàng tồn tại | Có thể tạo hàng thưa ở khóa chưa có | Dùng `IF EXISTS` nếu cần kiểm soát sự tồn tại |
| Cho rằng cột không gửi sẽ mãi không đổi | TTL hoặc client khác vẫn có thể thay đổi dữ liệu | Xác định tính nhất quán và điều kiện tranh chấp |
| Đọc trước rồi cập nhật không điều kiện để “tránh ghi đè” | Race condition giữa lần đọc và lần ghi | Dùng LWT/`IF` khi cần kiểm tra giá trị cũ |
| Ghép tên cột tùy ý từ payload vào CQL | Có thể tạo câu CQL không đúng hoặc nguy hiểm | Chỉ nhận tên cột trong whitelist, bind giá trị |

### Câu hỏi tự kiểm tra

1. Hàng đã có `email` và `phone`. Chạy `UPDATE ... SET phone = 'x'` thì email có bị xóa không? **Không**, chính mutation đó không ghi email.
2. Client bỏ trường email khỏi JSON PATCH. Backend có nên bind email thành NULL? **Không**; phải giữ nguyên bằng UNSET hoặc không đưa email vào câu CQL.
3. Client gửi `"email": null`, API cho phép xóa. Cassandra xử lý thế nào? **Ghi tombstone** cho email; đọc thường thấy `null` khi xóa đã được quan sát.
4. `SET preferences = {'theme': 'dark'}` có giữ `digest` cũ không? **Không**; đây là gán lại map. Dùng `preferences['theme'] = 'dark'` nếu chỉ muốn thay một mục.
5. Lệnh cập nhật phone có tự gia hạn TTL của display_name không? **Không**; cột không được ghi không nhận TTL mới từ mutation này.
6. Nếu cần bảo đảm tài khoản tồn tại trước khi sửa, cú pháp nào phù hợp? **`UPDATE ... IF EXISTS`**, rồi kiểm tra `[applied]`.

## 11. Nguyên tắc thiết kế khi đưa vào ứng dụng Java

Hãy thống nhất ý nghĩa của “cập nhật một phần” từ API tới database:

1. **Xác định full primary key** từ thiết kế bảng theo truy vấn; không cập nhật hàng dựa trên cột thường tùy ý.
2. **Ghi đúng cột cần thay đổi**; cột không gửi là no-op, không mặc định biến thành NULL.
3. **Phân biệt rõ missing và explicit null** trong JSON, DTO và prepared statement.
4. **Hiểu ranh giới collection**: bỏ qua cả cột, gán toàn bộ, hay chỉ sửa phần tử là ba thao tác khác nhau.
5. **Tự quản lý trường nghiệp vụ phụ trợ** như `updated_at`; Cassandra không tự đồng bộ toàn bộ hàng mỗi khi một cell đổi.
6. **Xem xét TTL, tombstone, compaction và repair** nếu thường xuyên xóa/ghi lại cột: đây là chi phí vật lý của thiết kế logic.
7. **Chọn mức nhất quán và điều kiện ghi** theo yêu cầu nghiệp vụ; replication và consistency giúp điều phối dữ liệu phân tán, còn `IF` giúp bảo vệ các điều kiện tranh chấp.

**Ghi nhớ:** Trong Cassandra, **chỉ các cột được ghi vào mutation mới chịu tác động trực tiếp của lần ghi đó**. Cột bị bỏ qua và marker UNSET có nghĩa “không thay đổi”; NULL có nghĩa “xóa giá trị”; còn gán cả collection có thể loại bỏ các phần tử không xuất hiện trong giá trị mới. Nắm được ranh giới này giúp xây dựng API PATCH an toàn, tránh mất dữ liệu và giảm tombstone không cần thiết.

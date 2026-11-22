# UUID, UUID_TO_BIN, BIN_TO_UUID và điều kiện sử dụng

UUID (Universally Unique Identifier) là định danh 128 bit thường được dùng khi nhiều dịch vụ cần tự tạo ID mà không phải xin một số tăng dần từ cùng một database. MySQL cung cấp hàm `UUID()` để sinh UUID dạng chuỗi, `UUID_TO_BIN()` để chuyển chuỗi UUID thành 16 byte và `BIN_TO_UUID()` để chuyển ngược về dạng văn bản.

Khi lưu UUID trong MySQL, có thể chọn dạng văn bản như `CHAR(36)` hoặc dạng nhị phân `BINARY(16)`. Dạng nhị phân gọn hơn và thường phù hợp với khóa chính/index khi ứng dụng chấp nhận việc chuyển đổi lúc đọc/ghi. Tham số `swap_flag` của `UUID_TO_BIN()` và `BIN_TO_UUID()` có thể sắp xếp lại phần thời gian của UUID version 1 để cải thiện tính cục bộ của index. Cờ này phải được dùng nhất quán ở cả hai chiều và không nên áp dụng máy móc cho mọi loại UUID.

## 1. UUID là gì?

UUID là định danh có độ dài 128 bit, thường được biểu diễn thành 32 chữ số hệ thập lục phân chia thành năm nhóm theo mẫu `8-4-4-4-12`:

```text
xxxxxxxx-xxxx-Mxxx-Nxxx-xxxxxxxxxxxx
```

Trong đó một số bit thể hiện version và variant của UUID. Dạng văn bản chuẩn có 36 ký tự tính cả bốn dấu gạch nối; phần dữ liệu nhị phân luôn dài 16 byte.

Ví dụ một UUID:

```text
6ccd780c-baba-1026-9564-5b8c656024db
```

UUID thường được dùng làm khóa định danh trong hệ thống phân tán, dịch vụ độc lập, đồng bộ dữ liệu hoặc khi cần tạo ID ở nhiều nơi. Không có nghĩa UUID luôn là lựa chọn tốt hơn `BIGINT AUTO_INCREMENT`; cần đánh giá kích thước index, tính cục bộ ghi, khả năng đọc/debug và yêu cầu tích hợp.

## 2. Hàm UUID() của MySQL

`UUID()` tạo một UUID dạng văn bản theo RFC 4122 version 1 trong MySQL. UUID version 1 có thành phần thời gian và node identifier; vì vậy nó khác UUID version 4 thường được tạo từ số ngẫu nhiên.

```sql
SELECT UUID() AS generated_uuid;
```

Kết quả có dạng:

```text
xxxxxxxx-xxxx-1xxx-xxxx-xxxxxxxxxxxx
```

Nibble version ở nhóm thứ ba thể hiện version 1. Giá trị thực tế thay đổi mỗi lần gọi.

Một câu lệnh có thể tạo nhiều UUID:

```sql
SELECT
    UUID() AS uuid_1,
    UUID() AS uuid_2,
    UUID() AS uuid_3;
```

Các UUID được sinh cho từng lần gọi. Hàm này trả về chuỗi; nếu cột đích là `BINARY(16)`, cần chuyển đổi trước khi ghi.

### 2.1. UUID() có phải token bí mật không?

Không nên dùng `UUID()` như mật khẩu, session token, reset token hoặc bí mật xác thực. UUID version 1 chứa cấu trúc liên quan thời gian và node; mục tiêu của nó là tạo định danh, không phải cung cấp bí mật khó đoán trước. Nếu cần token bảo mật, hãy sinh bằng bộ tạo số ngẫu nhiên mật mã (CSPRNG) ở ứng dụng hoặc cơ chế chuyên dụng, rồi lưu/so sánh theo thiết kế bảo mật.

UUID cũng không thay thế ràng buộc duy nhất ở database. Hãy đặt `PRIMARY KEY` hoặc `UNIQUE` trên cột ID để database bảo đảm không chấp nhận giá trị trùng, kể cả khi ID đến từ hệ thống bên ngoài.

## 3. UUID_TO_BIN(): chuyển UUID văn bản thành 16 byte

Cú pháp:

```sql
UUID_TO_BIN(string_uuid [, swap_flag])
```

- `string_uuid` là UUID dạng văn bản chuẩn.
- `swap_flag` có thể là `0` hoặc `1`; nếu bỏ qua, mặc định là `0`.
- Hàm trả về giá trị nhị phân 16 byte.

Ví dụ chuyển UUID sang binary mà không thay đổi thứ tự byte:

```sql
SELECT HEX(
    UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db', 0)
) AS uuid_hex;
```

Kết quả hex tương ứng là:

```text
6CCD780CBABA102695645B8C656024DB
```

`HEX()` chỉ giúp hiển thị byte ở dạng ký tự hex để kiểm tra; nó không chuyển giá trị thành UUID văn bản có dấu gạch nối. Giá trị trả về của `UUID_TO_BIN()` là binary string phù hợp để lưu vào `BINARY(16)`.

## 4. BIN_TO_UUID(): chuyển 16 byte về UUID văn bản

Cú pháp:

```sql
BIN_TO_UUID(binary_uuid [, swap_flag])
```

Hàm chuyển binary UUID về chuỗi dạng `8-4-4-4-12`. Ví dụ:

```sql
SELECT BIN_TO_UUID(
    UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db', 0),
    0
) AS uuid_text;
```

Kết quả là UUID ban đầu:

```text
6ccd780c-baba-1026-9564-5b8c656024db
```

Đây là phép chuyển đổi hai chiều. Nếu `UUID_TO_BIN()` dùng `swap_flag = 0`, `BIN_TO_UUID()` cũng phải dùng `0`; nếu lúc ghi dùng `1`, lúc đọc phải dùng `1`.

## 5. Hiểu swap_flag = 0 và swap_flag = 1

UUID version 1 có các trường thời gian được bố trí trong UUID văn bản theo thứ tự không thuận lợi cho việc sắp xếp theo thời gian khi so sánh byte từ trái sang phải. Phần timestamp thay đổi nhanh nằm ở nhóm đầu, còn phần thời gian có ý nghĩa cao hơn nằm ở nhóm thứ ba.

Với `swap_flag = 1`, MySQL sắp xếp lại các phần thời gian của UUID version 1 để phần thời gian có ý nghĩa cao hơn đứng trước. Mục tiêu là làm cho các UUID version 1 được tạo gần nhau có thứ tự nhị phân gần nhau hơn, cải thiện tính cục bộ khi chèn vào B-tree index.

Ví dụ:

```sql
SET @uuid_text = '6ccd780c-baba-1026-9564-5b8c656024db';

SELECT
    HEX(UUID_TO_BIN(@uuid_text, 0)) AS binary_without_swap,
    HEX(UUID_TO_BIN(@uuid_text, 1)) AS binary_with_swap;
```

Kết quả minh họa:

| Cách chuyển đổi | HEX |
| --- | --- |
| `UUID_TO_BIN(uuid, 0)` | `6CCD780CBABA102695645B8C656024DB` |
| `UUID_TO_BIN(uuid, 1)` | `1026BABA6CCD780C95645B8C656024DB` |

Khi bật swap, các nhóm thời gian được đưa về thứ tự byte phù hợp hơn với việc sắp xếp theo thời gian của UUID v1. Đây là thay đổi thứ tự byte trong binary representation; UUID logic sau khi chuyển ngược vẫn phải giống chuỗi ban đầu nếu dùng cùng cờ.

### 5.1. Khi nào nên dùng swap_flag = 1?

Nên cân nhắc `swap_flag = 1` khi:

- UUID được tạo bằng `UUID()` của MySQL, tức UUID version 1.
- UUID version 1 được lưu làm khóa chính hoặc khóa index thường xuyên chèn.
- Muốn cải thiện tính cục bộ của các lần insert vào B-tree so với lưu byte theo thứ tự mặc định.

Không nên dùng `swap_flag = 1` một cách mặc định cho mọi UUID. Với UUID version 4 được tạo ngẫu nhiên ở ứng dụng, phần thời gian không có cấu trúc version 1 để sắp xếp; swap không tạo được lợi ích locality như trên. Với UUID version 7 hoặc định dạng time-ordered khác, hãy tuân theo thứ tự byte được quy định cho loại UUID đó, không áp dụng phép swap dành cho version 1.

### 5.2. Không trộn lẫn swap flag

Giả sử ghi bằng:

```sql
INSERT INTO app_users (id)
VALUES (UUID_TO_BIN(UUID(), 1));
```

Thì đọc bằng:

```sql
SELECT BIN_TO_UUID(id, 1)
FROM app_users;
```

Nếu đọc cùng dữ liệu với `BIN_TO_UUID(id, 0)`, kết quả có thể là một UUID khác hoặc không còn phản ánh UUID gốc. MySQL không lưu metadata cho biết cột đã được chuyển với cờ nào; đó là quy ước của schema và ứng dụng cần duy trì.

Hãy ghi rõ swap flag trong tài liệu schema, code repository và quy trình import/export. Không để mỗi dịch vụ tự chọn cờ theo ý mình.

## 6. Lưu UUID bằng BINARY(16)

Một thiết kế phổ biến là dùng `BINARY(16)` cho khóa UUID:

```sql
CREATE TABLE app_users (
    id BINARY(16) NOT NULL,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_app_users_email (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Thêm bản ghi với UUID v1 do MySQL tạo:

```sql
INSERT INTO app_users (id, email, display_name)
VALUES (
    UUID_TO_BIN(UUID(), 1),
    'mai@example.test',
    'Mai Nguyễn'
);
```

Đọc ID dưới dạng văn bản:

```sql
SELECT
    BIN_TO_UUID(id, 1) AS user_id,
    email,
    display_name,
    created_at
FROM app_users;
```

Có thể xem giá trị binary bằng `HEX(id)`:

```sql
SELECT HEX(id) AS uuid_bytes
FROM app_users;
```

`BINARY(16)` có độ dài cố định 16 byte, phù hợp với binary UUID. Không ghi trực tiếp chuỗi 36 ký tự vào cột này; hãy chuyển bằng `UUID_TO_BIN()` hoặc truyền đúng 16 byte từ ứng dụng.

## 7. So sánh BINARY(16) và CHAR(36)

Hai cách lưu có ưu/nhược điểm khác nhau:

| Tiêu chí | `BINARY(16)` | `CHAR(36)` |
| --- | --- | --- |
| Dung lượng giá trị | 16 byte cố định | 36 ký tự văn bản; thường ít nhất 36 byte với chuỗi UUID ASCII |
| Hiển thị trực tiếp | Khó đọc, thường cần `BIN_TO_UUID()` hoặc `HEX()` | Dễ đọc trong SQL client |
| Index | Key nhỏ hơn, thường tiết kiệm không gian hơn | Key lớn hơn do lưu chuỗi |
| Tích hợp ứng dụng | Cần chuyển đổi UUID text sang 16 byte hoặc bind binary | Dễ trao đổi chuỗi với API và log |
| Quy ước swap | Phải quản lý thống nhất nếu dùng swap | Lưu trực tiếp dạng chuẩn, không cần swap |

`BINARY(16)` có thể giảm kích thước khóa và index so với chuỗi 36 ký tự. Với InnoDB, primary key còn được lưu kèm trong secondary index, nên kích thước primary key có ảnh hưởng lan rộng đến dung lượng index. Tuy nhiên, UUID v1 không swap vẫn có thể tạo insert phân tán theo thứ tự byte; lợi ích của binary storage và lợi ích của byte swapping là hai vấn đề liên quan nhưng khác nhau.

`CHAR(36)` phù hợp khi khả năng đọc/debug và tương thích hệ thống quan trọng hơn dung lượng index. `BINARY(16)` phù hợp khi muốn lưu gọn, có quy ước chuyển đổi rõ ràng và toàn bộ client có thể tuân thủ.

## 8. Truy vấn theo UUID mà vẫn tận dụng index

Khi cột được lưu bằng `BINARY(16)`, hãy chuyển UUID đầu vào ở phía giá trị so sánh:

```sql
SELECT id, email
FROM app_users
WHERE id = UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db', 1);
```

Điều kiện này so sánh trực tiếp cột `id` với giá trị binary được tạo trước, giúp optimizer có thể sử dụng primary key index.

Tránh viết:

```sql
-- Không ưu tiên cách này cho truy vấn tìm theo khóa
SELECT id, email
FROM app_users
WHERE BIN_TO_UUID(id, 1) = '6ccd780c-baba-1026-9564-5b8c656024db';
```

Ở cách thứ hai, hàm được áp dụng lên cột index. Điều đó thường khiến điều kiện không còn sargable và có thể ngăn optimizer dùng index theo cách trực tiếp. Hãy kiểm tra kế hoạch bằng `EXPLAIN` thay vì giả định.

Nếu ứng dụng dùng prepared statement, có thể bind chuỗi UUID rồi chuyển đổi trong biểu thức phía tham số:

```sql
SELECT id, email
FROM app_users
WHERE id = UUID_TO_BIN(?, 1);
```

Tham số `?` cần là UUID văn bản đúng định dạng và cờ phải khớp quy ước lưu trữ của cột.

## 9. UUID từ ứng dụng: UUID version 4 và các định dạng khác

Nhiều thư viện ứng dụng sinh UUID version 4 ngẫu nhiên. Nếu nhận UUID v4 từ API hoặc dịch vụ khác, có thể lưu bằng:

```sql
INSERT INTO app_users (id, email, display_name)
VALUES (
    UUID_TO_BIN('550e8400-e29b-41d4-a716-446655440000', 0),
    'an@example.test',
    'An Trần'
);
```

UUID v4 có bit version là `4` trong nhóm thứ ba. Dùng `swap_flag = 0` để giữ nguyên thứ tự byte của UUID. Không áp dụng swap dành cho UUID v1 nếu mục tiêu là giữ biểu diễn nhị phân chuẩn của UUID v4.

Nếu ứng dụng tạo UUID v7 hoặc một dạng UUID time-ordered khác, cần xác nhận thư viện, định dạng và thứ tự byte của loại UUID đó. Không giả định `swap_flag = 1` của MySQL là một cơ chế sắp xếp chung cho mọi UUID theo thời gian.

## 10. UUID trong quan hệ khóa ngoại

Nếu bảng con tham chiếu UUID của bảng cha, kiểu dữ liệu phải tương thích. Nếu khóa cha dùng `BINARY(16)`, cột khóa ngoại cũng nên dùng `BINARY(16)`:

```sql
CREATE TABLE app_user_profiles (
    user_id BINARY(16) NOT NULL,
    bio TEXT NULL,
    PRIMARY KEY (user_id),
    CONSTRAINT fk_app_user_profiles_user
        FOREIGN KEY (user_id) REFERENCES app_users (id)
) ENGINE=InnoDB;
```

Khi ghi khóa ngoại, dùng cùng quy tắc chuyển đổi:

```sql
INSERT INTO app_user_profiles (user_id, bio)
VALUES (
    UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db', 1),
    'Thông tin hồ sơ'
);
```

Giá trị binary phải giống byte-for-byte với khóa trong bảng cha. Nếu bảng cha dùng swap flag 1 mà bảng con dùng flag 0, cùng chuỗi UUID có thể chuyển thành hai giá trị binary khác nhau và foreign key sẽ không khớp.

Hãy thống nhất kiểu dữ liệu, swap flag và quy trình chuyển đổi giữa tất cả bảng liên quan. Không dùng `BINARY(16)` ở bảng cha rồi `CHAR(36)` ở bảng con nếu muốn tạo foreign key trực tiếp.

## 11. UUID và hiệu năng khóa chính InnoDB

InnoDB tổ chức bảng theo clustered primary key. Các hàng được lưu theo thứ tự khóa chính, và mỗi secondary index cũng mang theo giá trị primary key để định vị hàng. Vì vậy, loại khóa chính ảnh hưởng đến:

- Dung lượng của clustered index.
- Dung lượng tất cả secondary index.
- Mẫu chèn dữ liệu và khả năng tận dụng page cache.
- Mức độ phân tán ghi, page split và phân mảnh theo workload.
- Chi phí truyền ID giữa các dịch vụ.

`BIGINT` tăng dần thường có locality tốt và nhỏ gọn, nhưng cần cơ chế cấp ID tập trung hoặc thiết kế ID phân tán tương ứng. UUID cung cấp không gian định danh rộng và thuận tiện khi nhiều dịch vụ tự tạo ID, nhưng dạng chuỗi 36 ký tự làm khóa lớn. `BINARY(16)` giảm kích thước; với UUID v1, swap có thể cải thiện locality.

Không có kết luận rằng UUID luôn chậm hoặc UUID luôn tốt hơn auto-increment. Cần đo trên workload thật, xét tỷ lệ insert/update/read, số secondary index, kích thước buffer pool và cách ID được sinh.

## 12. Kiểm tra và chuyển đổi dữ liệu

Kiểm tra chuỗi UUID trước khi chuyển đổi. Với MySQL 8.0.13 trở lên, có thể dùng `IS_UUID()` để kiểm tra một giá trị có dạng UUID mà MySQL chấp nhận:

```sql
SELECT
    IS_UUID('6ccd780c-baba-1026-9564-5b8c656024db') AS valid_uuid,
    IS_UUID('not-a-uuid') AS invalid_uuid;
```

Nếu cần chuyển một cột chuỗi cũ sang binary, hãy kiểm tra dữ liệu và tạo cột mới trong migration có kiểm soát. Ví dụ kiểm kê dữ liệu trước:

```sql
SELECT id_text
FROM legacy_users
WHERE id_text IS NOT NULL
  AND IS_UUID(id_text) = 0;
```

Sau khi xác nhận dữ liệu hợp lệ, có thể chuyển từng batch vào cột binary mới:

```sql
UPDATE legacy_users
SET id_binary = UUID_TO_BIN(id_text, 1)
WHERE id_binary IS NULL
  AND id_text IS NOT NULL;
```

Ví dụ giả định bảng đã có cột `id_binary BINARY(16)` và UUID nguồn là version 1. Với UUID v4, dùng cờ `0`; không dùng cờ `1` nếu không theo quy ước UUID v1.

Sau khi chuyển, đối chiếu hai chiều:

```sql
SELECT
    id_text,
    BIN_TO_UUID(id_binary, 1) AS converted_text
FROM legacy_users
WHERE id_binary IS NOT NULL;
```

Kiểm tra số hàng, giá trị không khớp, unique key và mọi foreign key trước khi chuyển ứng dụng sang cột mới. Không xóa cột cũ cho đến khi toàn bộ client đã chuyển đổi và quy trình rollback đã được xác nhận.

## 13. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| `UUID()` trả về 16 byte | `UUID()` trả chuỗi 36 ký tự | Dùng `UUID_TO_BIN()` để chuyển sang binary |
| Có thể ghi chuỗi 36 ký tự trực tiếp vào `BINARY(16)` | Kiểu đích chỉ chứa 16 byte | Chuyển đổi trước hoặc bind đúng 16 byte |
| `swap_flag = 1` tốt cho mọi UUID | Swap được thiết kế cho cấu trúc thời gian của UUID v1 | Dùng cờ theo loại UUID và quy ước dữ liệu |
| Ghi bằng flag 1, đọc bằng flag 0 vẫn ra UUID cũ | Thứ tự byte bị diễn giải sai | Dùng cùng flag khi encode/decode |
| `BIN_TO_UUID()` trên cột trong WHERE luôn dùng index | Hàm trên cột có thể làm điều kiện không sargable | Chuyển tham số ở phía hằng số bằng `UUID_TO_BIN()` |
| UUID là token bảo mật | UUID v1 không được thiết kế làm bí mật khó đoán | Dùng CSPRNG cho token xác thực |
| UUID loại bỏ mọi khả năng trùng | Xác suất thấp không thay thế ràng buộc database | Giữ PRIMARY KEY hoặc UNIQUE |
| UUID v1 swap bảo đảm insert hoàn toàn tuần tự | Nó cải thiện thứ tự byte theo thời gian nhưng không bảo đảm mọi workload không phân mảnh | Đo bằng dữ liệu và workload thực tế |

## 14. Quy trình lựa chọn và sử dụng UUID

Trước khi đưa UUID vào schema, hãy trả lời:

1. Có thật sự cần ID được sinh độc lập ở nhiều dịch vụ hay `BIGINT AUTO_INCREMENT` đáp ứng được?
2. UUID đến từ MySQL `UUID()` (version 1), thư viện ứng dụng (thường version 4) hay định dạng khác?
3. Lưu dạng văn bản `CHAR(36)` hay binary `BINARY(16)` phù hợp hơn với khả năng tích hợp và vận hành?
4. Nếu là UUID v1, có cần `swap_flag = 1` để cải thiện locality không?
5. Tất cả bảng cha/con, service và job import đã thống nhất swap flag chưa?
6. Truy vấn có chuyển UUID ở phía tham số để giữ khả năng dùng index không?
7. Có ràng buộc PRIMARY KEY/UNIQUE để database kiểm tra định danh trùng không?
8. Có tránh dùng UUID như token bí mật hoặc bằng chứng phân quyền không?
9. Nếu chuyển schema cũ, có kiểm kê dữ liệu, migration theo batch và kế hoạch rollback không?

## 15. Bài tập thực hành

1. Chạy `SELECT UUID()` nhiều lần; quan sát định dạng và version trong nhóm thứ ba.
2. Chuyển một UUID mẫu bằng `UUID_TO_BIN(uuid, 0)` rồi chuyển ngược bằng `BIN_TO_UUID(binary, 0)`.
3. So sánh `HEX(UUID_TO_BIN(uuid, 0))` và `HEX(UUID_TO_BIN(uuid, 1))` với UUID version 1.
4. Lưu UUID từ `UUID()` vào cột `BINARY(16)` và truy vấn lại bằng `BIN_TO_UUID(id, 1)`.
5. Lưu một UUID version 4 từ ứng dụng với swap flag 0 và kiểm tra chuyển đổi hai chiều.
6. Thử đọc binary UUID đã swap bằng flag không khớp; giải thích vì sao kết quả không còn đúng.
7. Tạo bảng con dùng `BINARY(16)` làm foreign key đến bảng cha; kiểm tra insert với cùng và khác swap flag.
8. So sánh kích thước định nghĩa/index giữa `CHAR(36)` và `BINARY(16)` trên schema lab.
9. Dùng `EXPLAIN` so sánh truy vấn `id = UUID_TO_BIN(?, 1)` với truy vấn áp dụng `BIN_TO_UUID()` lên cột.
10. Viết kế hoạch migration từ UUID văn bản sang binary cho một bảng có foreign key và nhiều secondary index.

## 16. Ghi nhớ

`UUID()` của MySQL tạo UUID version 1 ở dạng văn bản. `UUID_TO_BIN()` chuyển UUID text thành 16 byte để lưu trong `BINARY(16)`; `BIN_TO_UUID()` chuyển ngược về chuỗi. `swap_flag = 1` sắp xếp lại các trường thời gian của UUID v1 để cải thiện tính cục bộ của index; `swap_flag = 0` giữ thứ tự byte chuẩn và phù hợp với UUID v4 hoặc định dạng không dùng cách sắp xếp riêng của v1.

Luôn dùng cùng swap flag khi ghi và đọc, thống nhất quy ước trên mọi bảng và dịch vụ, chuyển UUID ở phía tham số để truy vấn có thể dùng index, và giữ PRIMARY KEY/UNIQUE để database bảo đảm tính duy nhất. `BINARY(16)` gọn hơn `CHAR(36)` nhưng cần công cụ chuyển đổi khi quan sát/debug. UUID là định danh, không phải token bí mật; chọn cách sinh ID dựa trên yêu cầu phân tán, bảo mật, hiệu năng và chi phí vận hành.

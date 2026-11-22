# Cập nhật JSON một phần và điều kiện tối ưu lưu trữ/binary log

MySQL lưu giá trị trong cột `JSON` bằng định dạng nhị phân nội bộ đã được kiểm tra cú pháp, thay vì giữ nguyên chuỗi JSON như một cột văn bản thông thường. Khi chỉ thay đổi một vài đường dẫn trong tài liệu JSON lớn, việc gửi lại và ghi lại toàn bộ tài liệu có thể tốn CPU, I/O, undo/redo và dung lượng binary log. MySQL có thể tối ưu một số phép cập nhật bằng cách chỉ thay đổi phần cần thiết của tài liệu JSON trong storage engine và, khi được cấu hình, ghi phần thay đổi đó vào binary log.

Tối ưu này không tự động áp dụng cho mọi câu UPDATE có cột JSON. Cách viết biểu thức, hàm được dùng, kích thước giá trị mới, dung lượng trống trong biểu diễn nhị phân, định dạng binary log và cấu hình server đều ảnh hưởng. Bài học này tập trung vào `JSON_SET()`, `JSON_REPLACE()`, `JSON_REMOVE()`, cách đo bằng `JSON_STORAGE_SIZE()`/`JSON_STORAGE_FREE()` và cách bật `PARTIAL_JSON` cho row-based binary logging.

Bài học thuộc module `DATABASE_MYSQL`, nơi bạn làm chủ thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc execution plan, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Mục tiêu là cập nhật đúng semantics, giữ an toàn khi có nhiều transaction, và biết cách kiểm chứng lợi ích lưu trữ/binary log thay vì giả định rằng mọi JSON update đều là partial.

Sau bài học, bạn có thể:

- Giải thích khác biệt giữa JSON binary storage và chuỗi JSON văn bản.
- Chọn `JSON_SET`, `JSON_REPLACE` hoặc `JSON_REMOVE` theo ý nghĩa cập nhật.
- Viết UPDATE để MySQL có cơ hội thực hiện partial update tại chỗ.
- Nêu các điều kiện và trường hợp khiến MySQL phải ghi lại toàn bộ JSON document.
- Đo dung lượng bằng `JSON_STORAGE_SIZE()` và phần trống bằng `JSON_STORAGE_FREE()`.
- Phân biệt tối ưu partial update trong storage engine với partial JSON trong binary log.
- Bật và xác minh `binlog_row_value_options=PARTIAL_JSON` trong row-based logging.
- Hiểu vai trò riêng của `binlog_format`, `binlog_row_image` và `binlog_row_value_options`.
- Thiết kế cập nhật JSON an toàn trước lost update, concurrency và replication.

## 1. Chuẩn bị bảng thực hành

Tạo bảng lưu hồ sơ khách hàng với một cột JSON:

```sql
DROP TABLE IF EXISTS customer_profile;

CREATE TABLE customer_profile (
    customer_id BIGINT UNSIGNED NOT NULL,
    profile JSON NOT NULL,
    version_no BIGINT UNSIGNED NOT NULL DEFAULT 1,
    updated_at TIMESTAMP(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

INSERT INTO customer_profile (customer_id, profile)
VALUES
(101, JSON_OBJECT(
    'name', 'An',
    'preferences', JSON_OBJECT(
        'theme', 'light',
        'language', 'vi',
        'notifications', TRUE
    ),
    'usage', JSON_OBJECT('login_count', 0),
    'tags', JSON_ARRAY('new', 'newsletter'),
    'address', JSON_OBJECT(
        'city', 'Ho Chi Minh City',
        'district', 'District 1'
    )
)),
(102, JSON_OBJECT(
    'name', 'Binh',
    'preferences', JSON_OBJECT(
        'theme', 'dark',
        'language', 'en',
        'notifications', FALSE
    ),
    'usage', JSON_OBJECT('login_count', 0),
    'tags', JSON_ARRAY('returning'),
    'address', JSON_OBJECT(
        'city', 'Da Nang',
        'district', 'Hai Chau'
    )
));
```

Xem tài liệu:

```sql
SELECT
    customer_id,
    JSON_PRETTY(profile) AS profile,
    version_no,
    updated_at
FROM customer_profile
ORDER BY customer_id;
```

Cột `profile` có kiểu JSON. MySQL kiểm tra JSON hợp lệ khi ghi và lưu nó dưới dạng binary JSON để hỗ trợ truy cập theo đường dẫn. Binary JSON không phải là chuỗi văn bản có thể sửa bằng cách nối chuỗi an toàn.

## 2. Ba hàm cập nhật quan trọng

Ba hàm thường dùng cho partial update là `JSON_SET()`, `JSON_REPLACE()` và `JSON_REMOVE()`.

| Hàm | Hành vi | Khi path chưa tồn tại |
| --- | --- | --- |
| `JSON_SET(doc, path, value, ...)` | Thêm hoặc thay thế giá trị tại path | Tạo phần tử tại path nếu cấu trúc cho phép |
| `JSON_REPLACE(doc, path, value, ...)` | Chỉ thay thế giá trị đã tồn tại | Không thêm phần tử mới |
| `JSON_REMOVE(doc, path, ...)` | Xóa phần tử tại path | Không thay đổi nếu path không tồn tại |

### 2.1. JSON_SET: thêm hoặc thay thế

Đổi theme của customer 101:

```sql
UPDATE customer_profile
SET profile = JSON_SET(
    profile,
    '$.preferences.theme', 'dark'
)
WHERE customer_id = 101;
```

Nếu `$.preferences.theme` đã tồn tại, giá trị được thay bằng chuỗi JSON `"dark"`. Nếu path chưa tồn tại và đường dẫn cha hợp lệ, `JSON_SET()` có thể thêm phần tử mới.

Một lời gọi có thể cập nhật nhiều path:

```sql
UPDATE customer_profile
SET profile = JSON_SET(
    profile,
    '$.preferences.theme', 'dark',
    '$.preferences.notifications', FALSE,
    '$.last_updated_by', 'profile-service'
)
WHERE customer_id = 101;
```

Gộp các thay đổi cùng một tài liệu vào một UPDATE giúp tránh nhiều lần đọc/ghi và giữ các thay đổi trong cùng statement.

### 2.2. JSON_REPLACE: chỉ sửa path đã có

```sql
UPDATE customer_profile
SET profile = JSON_REPLACE(
    profile,
    '$.preferences.language', 'ja'
)
WHERE customer_id = 101;
```

Nếu path không tồn tại, `JSON_REPLACE()` không tạo nó. Dùng hàm này khi hợp đồng dữ liệu yêu cầu chỉ cập nhật thuộc tính đã có; nếu cần thêm thuộc tính mới, dùng `JSON_SET()`.

### 2.3. JSON_REMOVE: xóa path

```sql
UPDATE customer_profile
SET profile = JSON_REMOVE(
    profile,
    '$.address.district'
)
WHERE customer_id = 101;
```

`JSON_REMOVE()` xóa thuộc tính được chỉ định. Nếu cần loại bỏ một thuộc tính, hãy dùng hàm này thay vì gán SQL `NULL`.

### 2.4. SQL NULL và JSON null không giống nhau

Giá trị SQL `NULL` được truyền vào `JSON_SET()` là giá trị JSON null tại path, không phải lệnh xóa path:

```sql
UPDATE customer_profile
SET profile = JSON_SET(profile, '$.middle_name', NULL)
WHERE customer_id = 101;
```

Kết quả chứa:

```json
{"middle_name": null}
```

Nếu muốn xóa thuộc tính `middle_name`, dùng:

```sql
UPDATE customer_profile
SET profile = JSON_REMOVE(profile, '$.middle_name')
WHERE customer_id = 101;
```

Hãy xác định rõ contract của ứng dụng: thiếu thuộc tính, JSON null và SQL NULL có thể mang ý nghĩa nghiệp vụ khác nhau.

## 3. Viết UPDATE để có cơ hội partial update

Mẫu cơ bản:

```sql
UPDATE customer_profile
SET profile = JSON_SET(profile, '$.preferences.theme', 'dark')
WHERE customer_id = 101;
```

Điểm quan trọng là biểu thức JSON được áp dụng trực tiếp lên cột JSON và kết quả được gán trở lại chính cột đó trong UPDATE. MySQL có thể nhận diện phép biến đổi và cập nhật phần cần thiết trong binary JSON thay vì serialize rồi ghi lại toàn bộ document.

Ví dụ dưới đây thường không tạo cơ hội tương tự cho partial update:

```sql
-- Ứng dụng đọc toàn bộ document, sửa chuỗi rồi ghi lại document hoàn chỉnh
UPDATE customer_profile
SET profile = '{"name":"An","preferences":{"theme":"dark"}}'
WHERE customer_id = 101;
```

Đây là phép thay thế toàn bộ document. Các thuộc tính không có trong chuỗi mới sẽ biến mất. Nó cũng có nguy cơ ghi đè thay đổi mà transaction khác đã thực hiện trên một path khác sau lần đọc của ứng dụng.

### 3.1. Điều kiện tổng quát cho storage partial update

MySQL chỉ có thể áp dụng tối ưu partial update khi cấu trúc câu lệnh và tài liệu thỏa điều kiện của engine. Những điều kiện cần kiểm tra gồm:

1. Đối tượng được cập nhật là cột có kiểu `JSON` trong bảng.
2. Câu UPDATE sử dụng `JSON_SET()`, `JSON_REPLACE()` hoặc `JSON_REMOVE()` để tạo giá trị mới cho cột JSON.
3. Cột JSON đang cập nhật được truyền trực tiếp làm document đầu vào của hàm cập nhật và kết quả được gán lại vào cột đó.
4. Mọi thay đổi phải thay thế giá trị của phần tử object/array đã tồn tại; không được thêm phần tử mới vào object hoặc array cha. Vì vậy, `JSON_SET()` thêm key mới không đủ điều kiện partial storage update, dù document còn dung lượng trống.
5. Giá trị thay thế phải có kích thước không lớn hơn giá trị cũ. Ngoại lệ: nếu partial update trước đó đã để lại đủ vùng trống, một giá trị mới lớn hơn giá trị cũ vẫn có thể được ghi tại chỗ bằng cách dùng lại vùng trống.
6. Các path và giá trị phải hợp lệ theo quy tắc JSON path và kiểu dữ liệu của MySQL.

Nhiều cột JSON có thể được cập nhật trong cùng UPDATE; MySQL đánh giá riêng từng cột và chỉ partial update những cột được cập nhật bằng các hàm hỗ trợ. Có thể lồng `JSON_SET()`, `JSON_REPLACE()` và `JSON_REMOVE()` theo nhiều tổ hợp, miễn cột đầu vào và cột đích vẫn là cùng một cột.

Các điều kiện trên tạo cơ hội cho tối ưu; chúng không phải cam kết rằng mọi câu lệnh thỏa bề ngoài đều chắc chắn được thực hiện partial. Nếu giá trị mới cần thêm không gian không có sẵn, cấu trúc thay đổi quá nhiều hoặc câu lệnh không thuộc dạng được hỗ trợ, MySQL có thể ghi lại toàn bộ document.

### 3.2. Thay thế lớn hơn giá trị cũ

Ví dụ thay một chuỗi ngắn bằng chuỗi dài hơn đáng kể:

```sql
UPDATE customer_profile
SET profile = JSON_REPLACE(
    profile,
    '$.preferences.theme',
    'a-much-longer-preference-value-than-before'
)
WHERE customer_id = 101;
```

Nếu không gian nhị phân hiện có và phần trống được giữ lại không đủ, MySQL phải thực hiện cập nhật toàn bộ JSON document trong storage engine. Nếu document đã có free space từ lần cập nhật nhỏ hơn trước, một thay đổi thay thế path hiện có bằng giá trị lớn hơn vẫn có thể tận dụng phần trống đó. Dù storage engine phải ghi lại toàn document, row-based binary log vẫn có thể ghi JSON diff nếu đáp ứng các điều kiện riêng của partial binary logging và đã bật `PARTIAL_JSON`. Đừng dựa vào kích thước chuỗi đơn lẻ để kết luận; hãy đo trên dữ liệu thực tế.

### 3.3. Thêm path mới

`JSON_SET()` có thể thêm path mới:

```sql
UPDATE customer_profile
SET profile = JSON_SET(profile, '$.marketing.source', 'campaign-2026')
WHERE customer_id = 101;
```

Thêm thuộc tính làm thay đổi cấu trúc document. Việc thêm phần tử mới vào object/array không đáp ứng điều kiện partial storage update, kể cả khi binary JSON có free space; storage engine phải ghi lại document. Tuy nhiên, nếu các điều kiện chung về cột JSON, hàm cập nhật và cột đầu vào/đích cùng thỏa mãn, row-based binary log vẫn có thể biểu diễn thay đổi này dưới dạng JSON diff khi `PARTIAL_JSON` được bật. Đây là ví dụ rõ ràng cho thấy partial storage update và partial binary logging là hai tối ưu riêng.

### 3.4. Những cách viết thường làm mất cơ hội tối ưu

- Đọc JSON về ứng dụng, chỉnh sửa toàn bộ object rồi gửi lại một chuỗi JSON mới.
- Gán kết quả cho một cột khác hoặc chỉ SELECT kết quả mà không cập nhật lại chính cột JSON.
- Dùng hàm tổng hợp/tạo document mới không thuộc nhóm cập nhật partial được hỗ trợ.
- Nối chuỗi JSON thủ công bằng `CONCAT()`.
- Thay toàn bộ cột JSON bằng một document mới trong câu UPDATE.

Nếu cần sửa một vài path, hãy dùng hàm JSON ngay trong câu UPDATE trên server. Nếu nghiệp vụ cần thay thế toàn bộ document, hãy làm điều đó có chủ đích và có cơ chế concurrency phù hợp.

## 4. Đo dung lượng JSON

MySQL cung cấp hai hàm hữu ích để quan sát kích thước và phần không gian trống của cột JSON:

- `JSON_STORAGE_SIZE(json_val)`: số byte dùng cho biểu diễn binary JSON. Với JSON column, giá trị phản ánh kích thước document khi được lưu đầy đủ, trước các partial update tiếp theo.
- `JSON_STORAGE_FREE(json_val)`: số byte được giải phóng bên trong biểu diễn JSON column do các partial update trước đó. Với biểu thức JSON không phải cột JSON được lưu, hàm trả 0.

Kiểm tra trước/sau cập nhật:

```sql
SELECT
    customer_id,
    JSON_STORAGE_SIZE(profile) AS storage_bytes,
    JSON_STORAGE_FREE(profile) AS free_bytes
FROM customer_profile
WHERE customer_id = 101;
```

Để thấy không gian trống, hãy dùng một document có thuộc tính đủ dài rồi thay nó bằng giá trị ngắn hơn:

```sql
UPDATE customer_profile
SET profile = JSON_SET(
    profile,
    '$.address.district',
    'D1'
)
WHERE customer_id = 102;

SELECT
    JSON_STORAGE_SIZE(profile) AS storage_bytes,
    JSON_STORAGE_FREE(profile) AS free_bytes
FROM customer_profile
WHERE customer_id = 102;
```

Nếu path được thay bằng nội dung nhỏ hơn và MySQL thực hiện partial update, `JSON_STORAGE_FREE()` có thể lớn hơn 0. Giá trị trống này nằm trong vùng binary JSON của document, không phải dung lượng trống của tablespace hay filesystem.

### 4.1. Đọc hai hàm đo đúng cách

| Quan sát | Cách diễn giải |
| --- | --- |
| `JSON_STORAGE_SIZE()` lớn hơn `LENGTH(profile)` | Bình thường: binary JSON có header, offset và encoding riêng; không thể so trực tiếp như hai chuỗi cùng định dạng |
| `JSON_STORAGE_FREE()` tăng sau khi thay giá trị bằng giá trị ngắn hơn | Có không gian bên trong document được giải phóng bởi partial update |
| `JSON_STORAGE_FREE()` bằng 0 | Không chứng minh rằng partial update không xảy ra; thay giá trị cùng kích thước có thể không tạo vùng trống |
| `JSON_STORAGE_FREE()` giảm sau lần cập nhật tiếp theo | Phần trống trước đó có thể đã được tái sử dụng |
| `JSON_STORAGE_FREE()` bằng 0 sau thay toàn bộ document | Phù hợp với trường hợp full replacement tạo binary JSON mới |

`JSON_STORAGE_SIZE()` không phải số byte chắc chắn được ghi xuống đĩa trong từng UPDATE. Nó mô tả kích thước binary JSON theo semantics của hàm. Muốn đánh giá I/O, redo, undo và latency, cần kết hợp benchmark, Performance Schema và chỉ số storage engine.

### 4.2. Thí nghiệm độc lập với document lớn hơn

Tạo bảng lab:

```sql
DROP TABLE IF EXISTS json_partial_lab;

CREATE TABLE json_partial_lab (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    doc JSON NOT NULL
) ENGINE = InnoDB;

INSERT INTO json_partial_lab (id, doc)
VALUES (
    1,
    JSON_OBJECT(
        'description', REPEAT('x', 200),
        'status', 'ACTIVE',
        'counter', 0
    )
);

SELECT
    JSON_STORAGE_SIZE(doc) AS storage_bytes,
    JSON_STORAGE_FREE(doc) AS free_bytes
FROM json_partial_lab
WHERE id = 1;
```

Thay description bằng chuỗi ngắn:

```sql
UPDATE json_partial_lab
SET doc = JSON_REPLACE(doc, '$.description', 'short')
WHERE id = 1;

SELECT
    JSON_STORAGE_SIZE(doc) AS storage_bytes,
    JSON_STORAGE_FREE(doc) AS free_bytes
FROM json_partial_lab
WHERE id = 1;
```

Sau đó thử thay giá trị của một path hiện có bằng một giá trị lớn hơn nhưng vẫn nhỏ hơn hoặc bằng phần free space đã có; quan sát `JSON_STORAGE_FREE()` giảm khi vùng trống được tái sử dụng. Thử thêm path mới riêng để thấy thao tác đó không phải partial storage update. Kết quả cụ thể phụ thuộc phiên bản, binary JSON layout và chuỗi dữ liệu. Không dùng một con số free bytes cố định làm tiêu chí pass/fail cho mọi môi trường.

## 5. Binary log và partial JSON

Partial update trong storage engine và partial JSON trong binary log là hai tối ưu liên quan nhưng độc lập:

- **Storage partial update:** MySQL có thể sửa phần cần thiết của binary JSON trong cột thay vì thay toàn bộ document.
- **Binary log partial update:** với row-based logging, MySQL có thể ghi phần thay đổi của JSON column vào row event thay vì ghi lại toàn bộ giá trị JSON mới.

Một câu UPDATE có thể được tối ưu tại storage engine nhưng binary log vẫn ghi theo cấu hình đầy đủ. Muốn giảm dữ liệu JSON được ghi vào row-based binary log, cần bật tùy chọn `PARTIAL_JSON`.

### 5.1. Kiểm tra các biến liên quan

```sql
SELECT
    @@global.binlog_format AS global_binlog_format,
    @@session.binlog_format AS session_binlog_format,
    @@global.binlog_row_image AS global_row_image,
    @@session.binlog_row_image AS session_row_image,
    @@global.binlog_row_value_options AS global_row_value_options,
    @@session.binlog_row_value_options AS session_row_value_options;
```

Các biến có vai trò khác nhau:

| Biến | Điều khiển |
| --- | --- |
| `binlog_format` | Cách ghi thay đổi: STATEMENT, ROW hoặc MIXED |
| `binlog_row_image` | Những cột được ghi trong row event: FULL, MINIMAL hoặc NOBLOB |
| `binlog_row_value_options` | Cách biểu diễn một số giá trị trong row event; `PARTIAL_JSON` cho phép ghi partial JSON update |

`PARTIAL_JSON` không tự chuyển `binlog_format` sang ROW và cũng không thay thế `binlog_row_image`. Tối ưu này có ý nghĩa với row-based binary logging.

### 5.2. Bật PARTIAL_JSON cho session thử nghiệm

Trên một phiên bản MySQL hỗ trợ tùy chọn này, cấu hình session của connection chạy UPDATE:

```sql
SET SESSION binlog_row_value_options = 'PARTIAL_JSON';

SELECT
    @@session.binlog_format,
    @@session.binlog_row_value_options;
```

Để thử nghiệm cần row-based logging:

```sql
SET SESSION binlog_format = 'ROW';
```

Thay đổi `binlog_format` có giới hạn theo trạng thái transaction và ngữ cảnh routine; thực hiện trước khi mở transaction. Trong production, DBA quản lý cấu hình global và chính sách replication thay vì để từng request tùy ý đổi format.

Nếu cần áp dụng cho các connection mới, DBA có thể đặt global option:

```sql
SET GLOBAL binlog_row_value_options = 'PARTIAL_JSON';
```

Biến session của connection đang mở không tự đổi theo thay đổi global. Kiểm tra `@@session.binlog_row_value_options` trên chính connection thực hiện UPDATE. Việc thay đổi global có thể yêu cầu quyền quản trị và phải được kiểm soát qua cấu hình triển khai.

### 5.3. Điều kiện và phạm vi của partial binary logging

- Binary logging phải được bật.
- Thay đổi phải được ghi theo row-based format để sử dụng partial JSON row value.
- `binlog_row_value_options` của session thực hiện DML phải chứa `PARTIAL_JSON`.
- Cột JSON phải là cùng cột đầu vào và cột đích của một trong các hàm cập nhật được hỗ trợ. Việc thêm phần tử mới hoặc thay bằng giá trị lớn hơn có thể khiến storage engine phải full update, nhưng không nhất thiết ngăn binary log tạo JSON diff.
- Các server ở replication chain phải hỗ trợ định dạng row event được phát ra. Kiểm tra phiên bản và compatibility trước khi bật trên hệ thống nhiều thế hệ.

`binlog_row_image` vẫn quyết định cột nào được đưa vào row event. `PARTIAL_JSON` điều khiển cách biểu diễn phần thay đổi của JSON value khi row event được tạo. Hai thiết lập bổ sung cho nhau, không thay thế nhau. Khác với partial storage update, partial binary logging không yêu cầu hai điều kiện cuối của storage optimization: không thêm phần tử mới và giá trị mới không lớn hơn giá trị cũ. Vì thế một lần full update trong storage engine vẫn có thể được ghi dưới dạng partial JSON trong binary log.

### 5.4. Lợi ích vận hành

Với JSON document lớn nhưng mỗi UPDATE chỉ đổi một path nhỏ, partial binary logging có thể giảm:

- Kích thước row event trong binary log.
- Dung lượng relay log và lượng dữ liệu cần truyền tới replica.
- Lượng dữ liệu JSON phải được giải mã/áp dụng ở phía replica.
- Tác động lưu trữ và I/O liên quan đến việc ghi lại toàn bộ JSON value trong row event.

Mức giảm phụ thuộc kích thước document, kích thước phần thay đổi, số hàng được cập nhật, row image và các cột khác trong row event. Không suy ra mức giảm chỉ từ việc bật biến; hãy kiểm tra binlog thực tế và đo workload.

## 6. Kiểm tra binary log trong lab

Trong môi trường thử nghiệm có binary logging và quyền phù hợp:

1. Xác nhận `binlog_format=ROW` trên session.
2. Xác nhận `binlog_row_value_options` có `PARTIAL_JSON`.
3. Ghi lại vị trí binary log trước UPDATE.
4. Chạy một UPDATE nhỏ bằng JSON_SET/REPLACE/REMOVE.
5. Ghi lại vị trí sau UPDATE.
6. Dùng `mysqlbinlog` với chế độ giải mã row event để xem thay đổi được ghi.
7. So sánh với một lần thay toàn bộ document.

Các câu lệnh kiểm tra cơ bản:

```sql
SHOW MASTER STATUS;
SHOW BINARY LOGS;
```

Trên MySQL 8.4, `SHOW BINARY LOG STATUS` là tên lệnh mới được ưu tiên cho trạng thái binary log; dùng cú pháp phù hợp với phiên bản server đang chạy. Việc đọc file binlog thường được thực hiện bằng công cụ `mysqlbinlog` trên máy có quyền truy cập file.

Ví dụ lệnh ở terminal:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv binlog.000123
```

Output verbose giúp xem row events và phần dữ liệu được ghi. Cách hiển thị chi tiết partial JSON phụ thuộc phiên bản công cụ và server; không dùng việc output khó đọc như JSON văn bản để kết luận rằng event không phải partial. So sánh kích thước event hoặc kiểm tra trên replica là bằng chứng bổ sung.

Không bật/tắt binary logging hoặc thay đổi cấu hình production chỉ để làm bài lab. Dùng instance riêng có dữ liệu giả lập và binary log retention phù hợp.

## 7. Cập nhật JSON an toàn khi có nhiều transaction

Một ưu điểm lớn của cập nhật trực tiếp trên server là tránh quy trình read-modify-write toàn document ở ứng dụng.

### 7.1. Tránh lost update khi ứng dụng ghi lại toàn bộ document

Giả sử hai request cùng đọc document phiên bản ban đầu:

- Request A đổi `$.preferences.theme`.
- Request B đổi `$.preferences.language`.

Nếu cả hai sửa bản copy trong ứng dụng rồi ghi lại toàn bộ JSON, request ghi sau có thể xóa thay đổi của request ghi trước vì nó gửi document cũ chứa path chưa cập nhật.

Thay vào đó, mỗi request cập nhật path trực tiếp:

```sql
UPDATE customer_profile
SET profile = JSON_SET(profile, '$.preferences.theme', 'dark')
WHERE customer_id = 101;

UPDATE customer_profile
SET profile = JSON_SET(profile, '$.preferences.language', 'ja')
WHERE customer_id = 101;
```

InnoDB khóa hàng và thực hiện mỗi UPDATE trên giá trị cột hiện tại theo thứ tự transaction được xử lý. Cập nhật path khác nhau có thể cùng được giữ lại thay vì request sau ghi đè cả document cũ.

### 7.2. Cập nhật cùng path vẫn cần quy tắc nghiệp vụ

Nếu hai request cùng đặt `$.preferences.theme` thành hai giá trị khác nhau, kết quả cuối cùng phụ thuộc thứ tự commit/ghi. Partial update không giải quyết xung đột nghiệp vụ. Nếu cần phát hiện xung đột, dùng cột version và optimistic locking:

```sql
UPDATE customer_profile
SET
    profile = JSON_SET(profile, '$.preferences.theme', 'dark'),
    version_no = version_no + 1
WHERE customer_id = 101
  AND version_no = 7;
```

Ứng dụng kiểm tra affected rows. Nếu bằng 0, phiên bản đã thay đổi hoặc hàng không còn tồn tại; đọc lại và quyết định retry/merge theo quy tắc nghiệp vụ.

### 7.3. Biến đổi số nguyên tử

Nếu cần tăng bộ đếm nằm trong JSON, hãy tính dựa trên giá trị hiện tại trong cùng UPDATE:

```sql
UPDATE customer_profile
SET profile = JSON_SET(
    profile,
    '$.usage.login_count',
    COALESCE(
        CAST(
            JSON_UNQUOTE(JSON_EXTRACT(profile, '$.usage.login_count'))
            AS UNSIGNED
        ),
        0
    ) + 1
)
WHERE customer_id = 101;
```

Đoạn ví dụ giả định path có giá trị số hoặc chưa tồn tại. Nếu dữ liệu có thể chứa string, object, array hoặc số âm, cần validate JSON_TYPE và xử lý theo schema nghiệp vụ trước khi CAST. Một cột số riêng thường tốt hơn nếu bộ đếm được cập nhật thường xuyên, dùng trong điều kiện lọc hoặc cần index.

## 8. JSON path, index và chi phí còn lại

Partial update giảm công việc ghi JSON document trong các trường hợp được hỗ trợ; nó không làm mọi thao tác liên quan JSON trở nên miễn phí.

- Điều kiện `WHERE` vẫn cần access path phù hợp. Dùng primary key hoặc index trên khóa định danh để tránh scan toàn bảng.
- Nếu truy vấn thường xuyên lọc theo một thuộc tính JSON, cân nhắc generated column và index trên generated column.
- Nếu partial update thay đổi path được dùng trong generated column có index, MySQL vẫn phải duy trì index tương ứng.
- Nếu tài liệu có nhiều path được cập nhật độc lập và tần suất cao, xem xét chuẩn hóa một số thuộc tính nóng thành cột quan hệ.
- Không dùng JSON cho dữ liệu có quan hệ, constraint, join hoặc aggregate thường xuyên nếu cấu trúc quan hệ rõ ràng hơn.

Ví dụ index một thuộc tính theme:

```sql
ALTER TABLE customer_profile
ADD COLUMN theme VARCHAR(20)
    GENERATED ALWAYS AS (
        JSON_UNQUOTE(JSON_EXTRACT(profile, '$.preferences.theme'))
    ) STORED,
ADD INDEX idx_customer_profile_theme (theme);
```

Truy vấn:

```sql
SELECT customer_id
FROM customer_profile
WHERE theme = 'dark';
```

Index giúp truy vấn lọc theo theme. Nó không thay thế việc dùng `JSON_SET()` khi cập nhật document và cũng không loại bỏ chi phí duy trì index khi theme thay đổi.

## 9. Những trường hợp không nên ép partial update

- Thay đổi phần lớn document hoặc tái cấu trúc schema JSON: thay toàn bộ document có thể rõ ràng và phù hợp hơn.
- Ứng dụng cần xác thực toàn bộ object bằng schema/version trước khi ghi: dùng quy trình validation và optimistic locking, sau đó thay document có kiểm soát.
- Document rất nhỏ: chênh lệch I/O có thể không đáng kể so với độ phức tạp.
- Path được cập nhật liên tục nhưng cũng cần lọc/join/aggregate: tách thành cột quan hệ có thể phù hợp hơn.
- Câu lệnh cập nhật phải thay đổi nhiều path phụ thuộc nhau: gộp vào một JSON_SET/REPLACE nếu semantics rõ, hoặc tạo document mới một cách tường minh.

Tối ưu không phải mục tiêu độc lập. Ưu tiên semantics chính xác, tính nhất quán và khả năng vận hành; chỉ tối ưu partial khi phép đo cho thấy lợi ích.

## 10. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng chuỗi JSON mới để sửa một path | Ghi lại toàn bộ document và có thể làm mất thuộc tính khác | Dùng JSON_SET/REPLACE/REMOVE trực tiếp trên cột |
| Dùng JSON_REPLACE để thêm thuộc tính | Path chưa có không được tạo | Dùng JSON_SET nếu cần thêm |
| Gán SQL NULL để xóa path | Tạo JSON null thay vì xóa thuộc tính | Dùng JSON_REMOVE |
| Nghĩ JSON_SET luôn partial | MySQL có thể phải full update nếu không gian/điều kiện không phù hợp | Đo JSON_STORAGE_FREE và kiểm tra binlog |
| Nghĩ JSON_STORAGE_FREE bằng 0 chứng minh full update | Thay cùng kích thước có thể không tạo free space | Đọc đúng ý nghĩa hai hàm storage |
| Nghĩ PARTIAL_JSON tự bật ROW logging | Binary log vẫn phụ thuộc binlog_format | Kiểm tra format và option trên cùng session |
| Nhầm binlog_row_image với PARTIAL_JSON | Cấu hình sai mục tiêu | Hiểu row image và JSON value representation là hai tùy chọn riêng |
| Chỉ kiểm tra global variable | Session hiện tại có thể vẫn dùng giá trị cũ | Kiểm tra `@@session` trên connection chạy UPDATE |
| Không kiểm tra phiên bản replica | Replica có thể không hỗ trợ row event được phát ra | Xác minh compatibility toàn replication chain |
| Đọc-sửa-ghi toàn document trong ứng dụng | Lost update giữa các request | Cập nhật path server-side hoặc dùng version check |
| Cho rằng partial update loại bỏ index cost | Generated/secondary index vẫn cần được duy trì | Đo cả write path và index maintenance |

## 11. Quy trình kiểm chứng tối ưu

1. Chọn document JSON đại diện về kích thước và cấu trúc.
2. Ghi lại MySQL version, storage engine, `binlog_format`, `binlog_row_image` và `binlog_row_value_options`.
3. Chạy một UPDATE thay thế path bằng giá trị nhỏ hơn bằng JSON_SET/REPLACE.
4. Đo `JSON_STORAGE_SIZE()` và `JSON_STORAGE_FREE()` trước/sau.
5. Chạy một UPDATE thay path bằng giá trị lớn hơn và quan sát trường hợp cần full update.
6. Chạy một phép thay toàn bộ document để có baseline so sánh.
7. Nếu đánh giá binary log, bật ROW và PARTIAL_JSON trong lab, rồi kiểm tra row events.
8. Đo latency, bytes binlog, redo/undo, replica apply lag và tài nguyên server với workload lặp đủ lớn.
9. Thử concurrency: hai session cập nhật hai path khác nhau và cùng một path.
10. Xác nhận kết quả JSON cuối cùng đúng và không mất thuộc tính ngoài ý muốn.

Không kết luận từ một lần chạy đơn lẻ trên bảng nhỏ. Dùng dữ liệu đại diện, nhiều lần lặp, trạng thái cache tương đương và cùng điều kiện replication.

## 12. Checklist triển khai

- [ ] Cột có kiểu JSON và tài liệu hợp lệ.
- [ ] Chọn đúng JSON_SET, JSON_REPLACE hoặc JSON_REMOVE theo semantics.
- [ ] Cập nhật trực tiếp cột JSON trong UPDATE.
- [ ] Có điều kiện WHERE đủ chọn lọc, thường dựa trên khóa/index.
- [ ] Không serialize và ghi lại toàn document khi chỉ cần sửa một path.
- [ ] Đã hiểu điều kiện kích hoạt partial storage update và khả năng full update.
- [ ] Đã đo JSON_STORAGE_SIZE và JSON_STORAGE_FREE đúng ngữ nghĩa.
- [ ] Đã tách biệt storage partial update với partial JSON trong binary log.
- [ ] Nếu cần partial row logging, đã xác minh ROW và PARTIAL_JSON trên session ghi dữ liệu.
- [ ] Đã kiểm tra binlog_row_image và không nhầm nó với binlog_row_value_options.
- [ ] Đã xác minh phiên bản tương thích trên mọi replica/downstream server.
- [ ] Có chiến lược concurrency: server-side path update, version check hoặc khóa.
- [ ] Đã đánh giá index/generated column và chi phí duy trì index.
- [ ] Có benchmark và theo dõi binlog size, latency, replica lag, I/O.
- [ ] Có kế hoạch rollback cấu hình và migration nếu lợi ích không đạt kỳ vọng.

## 13. Bài tập thực hành

1. Tạo bảng `json_partial_lab` và chèn document có chuỗi dài.
2. Đổi một path bằng JSON_SET với giá trị ngắn hơn; đo JSON_STORAGE_FREE.
3. Đổi path đã có bằng JSON_REPLACE; xác nhận path không tồn tại không được tạo.
4. Thêm path mới bằng JSON_SET và so sánh kích thước trước/sau.
5. Xóa một path bằng JSON_REMOVE; kiểm tra document và phần trống.
6. Gán SQL NULL vào JSON_SET rồi so sánh với JSON_REMOVE.
7. Thay toàn bộ document và kiểm tra JSON_STORAGE_FREE sau full replacement.
8. Chạy hai session cập nhật hai path khác nhau bằng JSON_SET; xác nhận cả hai thay đổi được giữ.
9. Chạy hai session cập nhật cùng path; mô tả chính sách xung đột và kết quả cuối.
10. Bật ROW và PARTIAL_JSON trong lab; so sánh row event của partial update với full replacement.
11. Thay đổi binlog_row_image giữa FULL và MINIMAL trong môi trường thử nghiệm; giải thích vì sao nó không đồng nghĩa với PARTIAL_JSON.
12. Thêm generated column/index trên một path; cập nhật path đó và đánh giá chi phí index maintenance.
13. Viết một báo cáo benchmark gồm MySQL version, biến cấu hình, document size, free bytes, binlog bytes, latency và replica lag.

## 14. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể chọn đúng hàm JSON theo semantics, viết UPDATE trực tiếp trên cột để tạo cơ hội partial storage update, giải thích vì sao MySQL có thể vẫn phải ghi lại toàn document, đo được dung lượng và phần trống, cấu hình partial JSON row logging đúng cách, phân biệt ba biến binlog liên quan và bảo đảm cập nhật không làm mất thay đổi đồng thời. Bạn cũng cần đưa ra được bằng chứng benchmark thay vì khẳng định partial update luôn nhanh hơn.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Partial Updates of JSON Values](https://dev.mysql.com/doc/refman/8.4/en/json.html#json-partial-updates)
- [MySQL 8.4 Reference Manual — JSON Utility Functions](https://dev.mysql.com/doc/refman/8.4/en/json-utility-functions.html)
- [MySQL 8.4 Reference Manual — The Binary Log](https://dev.mysql.com/doc/refman/8.4/en/binary-log.html)
- [MySQL 8.4 Reference Manual — System Variables: binlog_row_value_options](https://dev.mysql.com/doc/refman/8.4/en/replication-options-binary-log.html#sysvar_binlog_row_value_options)
- [MySQL 8.4 Reference Manual — Row-Based Replication](https://dev.mysql.com/doc/refman/8.4/en/replication-formats.html)

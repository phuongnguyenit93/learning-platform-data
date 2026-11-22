# BIT và khác biệt với số nguyên hoặc chuỗi nhị phân

MySQL cung cấp kiểu dữ liệu `BIT(M)` để lưu một trường gồm M bit. Kiểu này phù hợp khi dữ liệu thực sự được mô hình hóa như một bit field hoặc bit mask, chẳng hạn một tập cờ có số lượng cố định. Tuy nhiên, `BIT` không đồng nghĩa với kiểu số nguyên và cũng không phải một chuỗi byte như `BINARY` hoặc `VARBINARY`.

Sự khác biệt nằm ở ý nghĩa dữ liệu, độ dài được khai báo, cách chuyển đổi, cách client hiển thị và cách truy vấn. Chọn sai kiểu có thể khiến kết quả khó đọc, driver ánh xạ không như mong đợi hoặc điều kiện lọc không tận dụng được index.

Trong phạm vi `DATABASE_MYSQL`, bài học này giúp bạn chọn đúng kiểu dữ liệu khi thiết kế bảng, hiểu cách biểu diễn và chuyển đổi bit, thực hiện các phép toán bit an toàn, đồng thời đánh giá ảnh hưởng tới truy vấn và index.

## 1. BIT(M) là gì?

`BIT(M)` là kiểu dữ liệu bit field. Mỗi giá trị có tối đa M bit, trong đó M nằm trong khoảng từ 1 đến 64. Nếu bỏ qua M, giá trị mặc định là 1.

Ví dụ:

~~~sql
CREATE TABLE bit_samples (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    enabled BIT(1) NOT NULL,
    permissions BIT(8) NOT NULL,
    feature_mask BIT(16) NOT NULL
);
~~~

- `enabled` biểu diễn một bit.
- `permissions` biểu diễn tối đa 8 bit.
- `feature_mask` biểu diễn tối đa 16 bit.

Giá trị của `BIT(M)` được xem như một số không dấu trong phạm vi:

[
0 \le value \le 2^M - 1
]

Ví dụ:

| Kiểu | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất |
|---|---:|---:|---:|
| `BIT(1)` | 1 | 0 | 1 |
| `BIT(4)` | 4 | 0 | 15 |
| `BIT(8)` | 8 | 0 | 255 |
| `BIT(16)` | 16 | 0 | 65.535 |
| `BIT(32)` | 32 | 0 | 4.294.967.295 |
| `BIT(64)` | 64 | 0 | 18.446.744.073.709.551.615 |

Giá trị lớn nhất của `BIT(64)` tương đương miền giá trị của `BIGINT UNSIGNED`. Cần lưu ý rằng `BIGINT` có thể được khai báo signed hoặc unsigned, còn `BIT(M)` biểu diễn giá trị bit không dấu.

### 1.1. Số bit và dung lượng lưu trữ

Giá trị `BIT(M)` được lưu dưới dạng bit field. Số byte cần thiết xấp xỉ:

[
\left\lceil \frac{M}{8} \right\rceil
]

Một số ví dụ:

| Kiểu | Số byte dữ liệu cần thiết |
|---|---:|
| `BIT(1)` | 1 |
| `BIT(7)` | 1 |
| `BIT(8)` | 1 |
| `BIT(9)` | 2 |
| `BIT(16)` | 2 |
| `BIT(24)` | 3 |
| `BIT(32)` | 4 |
| `BIT(64)` | 8 |

Đây là dung lượng biểu diễn của giá trị, không phải tổng dung lượng một hàng hoặc một bảng. InnoDB còn có overhead của record, NULL bitmap, index, page và các cấu trúc lưu trữ khác. Không nên chỉ nhìn số byte của một cột để kết luận tổng dung lượng bảng.

Nếu giá trị được gán có ít bit hơn M, MySQL đệm các bit 0 ở bên trái để đủ độ dài khai báo. Ví dụ, giá trị 5 trong `BIT(8)` có biểu diễn:

~~~text
00000101
~~~

Các số 0 ở đầu không làm thay đổi giá trị số, nhưng hữu ích khi hiển thị bit mask theo độ dài cố định.

## 2. Khai báo và gán giá trị BIT

### 2.1. Tạo bảng và chèn dữ liệu

MySQL hỗ trợ literal dạng bit với cú pháp `b'val'` hoặc `0bval`. `val` chỉ chứa ký tự 0 và 1.

~~~sql
CREATE TABLE device_state (
    device_id BIGINT UNSIGNED NOT NULL,
    is_online BIT(1) NOT NULL DEFAULT b'0',
    status_flags BIT(8) NOT NULL DEFAULT b'00000000',
    PRIMARY KEY (device_id)
) ENGINE = InnoDB;

INSERT INTO device_state (
    device_id,
    is_online,
    status_flags
)
VALUES
    (1, b'1', b'00000101'),
    (2, b'0', b'00000010'),
    (3, 1, 4);
~~~

Giá trị `b'00000101'` tương đương số 5. Khi gán số nguyên 4 vào cột `BIT(8)`, MySQL chuyển giá trị số đó thành biểu diễn bit tương ứng.

Với dữ liệu bit, nên dùng literal `b'...'` trong script khi mục đích là thể hiện trực quan các bit. Dùng số nguyên khi ý nghĩa của giá trị là một con số hoặc mask đã được định nghĩa rõ.

### 2.2. Bit literal và binary string literal

Các cú pháp sau không nên bị coi là đồng nghĩa:

| Cú pháp | Ý nghĩa |
|---|---|
| `b'0101'` | Bit-value literal |
| `0b0101` | Số nguyên viết ở hệ nhị phân |
| `X'05'` | Hexadecimal string literal, biểu diễn byte `0x05` |
| `0x05` | Hexadecimal literal; cách diễn giải phụ thuộc ngữ cảnh số hoặc chuỗi |

Bit-value literal `b'0101'` thể hiện bốn bit. Trong ngữ cảnh số, giá trị của nó là 5. Hexadecimal string literal `X'05'` biểu diễn một byte có giá trị hex 05. Hai cách viết có thể cùng mô tả giá trị số 5 trong một phép chuyển đổi, nhưng ý nghĩa ban đầu và ngữ cảnh kiểu dữ liệu khác nhau.

Khi gán cho cột `BIT(M)`, ưu tiên dùng `b'...'` hoặc một số nguyên nằm trong phạm vi. Khi gán chuỗi byte cho `BINARY`/`VARBINARY`, dùng literal chuỗi nhị phân hoặc hex theo đúng ý định.

### 2.3. NULL và DEFAULT

`BIT(M)` có thể cho phép hoặc không cho phép NULL như các kiểu cột khác:

~~~sql
CREATE TABLE account_flags (
    account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    is_verified BIT(1) NOT NULL DEFAULT b'0',
    flags BIT(8) NULL DEFAULT NULL
);
~~~

Phân biệt ba trạng thái:

- `b'0'`: giá trị bit bằng 0.
- `b'1'`: giá trị bit bằng 1.
- `NULL`: không có giá trị/không xác định theo mô hình dữ liệu.

Không nên dùng NULL như một cách khác để biểu diễn false. Nếu nghiệp vụ chỉ có hai trạng thái, khai báo `NOT NULL` và giá trị mặc định rõ ràng thường dễ kiểm soát hơn.

## 3. Đọc và hiển thị giá trị BIT

Một điểm dễ gây nhầm là client có thể hiển thị giá trị cột `BIT` như một chuỗi byte, thay vì một số thập phân dễ đọc. Cách hiển thị còn phụ thuộc công cụ và driver.

Ví dụ:

~~~sql
SELECT
    device_id,
    is_online,
    is_online + 0 AS is_online_number,
    HEX(is_online) AS is_online_hex,
    status_flags,
    status_flags + 0 AS flags_number,
    HEX(status_flags) AS flags_hex,
    LPAD(BIN(status_flags + 0), 8, '0') AS flags_binary
FROM device_state
ORDER BY device_id;
~~~

Các phép chuyển đổi có mục đích khác nhau:

- `column + 0`: đưa giá trị vào ngữ cảnh số để đọc dưới dạng số nguyên.
- `HEX(column)`: hiển thị biểu diễn hex của byte.
- `BIN(column + 0)`: biểu diễn giá trị số dưới dạng chuỗi nhị phân.
- `LPAD(..., M, '0')`: thêm các số 0 bên trái để hiển thị đủ M bit.

Với dữ liệu mẫu, kết quả logic của `status_flags` là:

| device_id | Giá trị số | Biểu diễn 8 bit |
|---:|---:|---|
| 1 | 5 | `00000101` |
| 2 | 2 | `00000010` |
| 3 | 4 | `00000100` |

Đừng dựa vào cách hiển thị thô của một công cụ để kết luận dữ liệu bị lỗi. Hãy dùng chuyển đổi tường minh khi cần log, so sánh hoặc xuất dữ liệu.

### 3.1. Đọc bằng ứng dụng

Một số driver có thể ánh xạ cột BIT thành kiểu byte, mảng byte hoặc kiểu boolean tùy độ dài và cấu hình. Không nên giả định mọi client đều trả về chuỗi ký tự `'0'` hoặc `'1'`.

Khi tích hợp JDBC, Connector/Python hoặc connector khác:

1. Kiểm tra metadata của result set để biết kiểu server trả về.
2. Đọc tài liệu mapping kiểu dữ liệu của đúng phiên bản driver.
3. Viết kiểm thử cho `BIT(1)`, `BIT(8)` và giá trị có bit cao được bật.
4. Nếu API cần số nguyên hoặc boolean, chuyển đổi rõ ràng trong SQL hoặc tầng mapping.
5. Khi xuất log, dùng `HEX()`, `BIN()` hoặc phép chuyển đổi số để tránh byte không in được.

Ví dụ truy vấn phục vụ API muốn nhận boolean:

~~~sql
SELECT
    device_id,
    (is_online + 0) = 1 AS is_online
FROM device_state;
~~~

Kết quả biểu thức so sánh là giá trị logic mà client thường xử lý dễ hơn cột BIT thô.

## 4. BIT khác kiểu số nguyên như thế nào?

Kiểu số nguyên được thiết kế để biểu diễn số học. `BIT(M)` được thiết kế để biểu diễn một trường bit có độ dài giới hạn.

### 4.1. So sánh với các kiểu integer

| Kiểu | Dung lượng số học | Miền giá trị signed | Miền giá trị unsigned |
|---|---:|---:|---:|
| `TINYINT` | 1 byte | -128 đến 127 | 0 đến 255 |
| `SMALLINT` | 2 byte | -32.768 đến 32.767 | 0 đến 65.535 |
| `MEDIUMINT` | 3 byte | -8.388.608 đến 8.388.607 | 0 đến 16.777.215 |
| `INT` | 4 byte | -2.147.483.648 đến 2.147.483.647 | 0 đến 4.294.967.295 |
| `BIGINT` | 8 byte | -2^63 đến 2^63-1 | 0 đến 2^64-1 |

Các kiểu integer hỗ trợ cộng, trừ, nhân, chia, so sánh và các phép toán số học thông thường. `BIT(M)` có thể tham gia biểu thức số, nhưng cần chuyển đổi rõ khi cần kết quả số hoặc thao tác mask.

Ví dụ:

~~~sql
SELECT
    10 + 5 AS integer_sum,
    CAST(b'00000101' AS UNSIGNED) AS bit_value;
~~~

### 4.2. Khi nào chọn integer?

Chọn kiểu số nguyên khi dữ liệu có ý nghĩa số học hoặc cần được đọc, tính toán và trao đổi thuận tiện:

- Số lượng sản phẩm.
- Số lần thử.
- Trạng thái dạng mã số.
- ID, số thứ tự hoặc bộ đếm.
- Giá trị tiền tệ theo đơn vị nhỏ nhất nếu thiết kế phù hợp.

Chọn `TINYINT UNSIGNED` cho một số cờ hoặc mã trạng thái nhỏ nếu cần đọc và xử lý trực tiếp như số. Đừng dùng `BIT` chỉ vì giá trị hiện tại là 0 hoặc 1.

### 4.3. BIT không phải BOOLEAN thực sự

Trong MySQL, `BOOLEAN` và `BOOL` là từ đồng nghĩa của `TINYINT(1)`. Chúng không phải một kiểu boolean độc lập có miền giá trị chỉ gồm TRUE/FALSE.

Ví dụ:

~~~sql
CREATE TABLE user_profile (
    user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT chk_user_active
        CHECK (is_active IN (0, 1))
);
~~~

Từ MySQL 8.0.16, CHECK constraint được thực thi. Với phiên bản cũ hơn, không được giả định CHECK luôn bảo vệ dữ liệu. Cũng cần nhớ `TINYINT(1)` là cách viết có display width, không tự giới hạn giá trị ở 0 và 1.

Nếu muốn lưu cờ true/false, `BOOLEAN` hoặc `TINYINT` kèm constraint thường dễ đọc và tương thích với nhiều công cụ hơn. `BIT(1)` phù hợp khi mô hình thực sự cần bit field và ứng dụng đã xử lý kiểu dữ liệu này rõ ràng.

## 5. BIT khác chuỗi nhị phân như thế nào?

MySQL có các kiểu chuỗi nhị phân như `BINARY`, `VARBINARY` và `BLOB`. Chúng lưu byte, không phải trường số học có độ dài bit.

### 5.1. BINARY và VARBINARY

| Kiểu | Độ dài khai báo | Đặc điểm |
|---|---|---|
| `BIT(M)` | M bit, 1 đến 64 | Giá trị bit field; được diễn giải như giá trị bit không dấu |
| `BINARY(M)` | M byte | Chuỗi byte độ dài cố định; được đệm byte `0x00` ở bên phải |
| `VARBINARY(M)` | Tối đa M byte | Chuỗi byte có độ dài thay đổi; không đệm cố định |
| `BLOB` | Dữ liệu nhị phân lớn | Chuỗi byte có độ dài thay đổi, dùng cho nội dung binary lớn |

Ví dụ:

~~~sql
CREATE TABLE binary_examples (
    id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    bit_value BIT(8) NOT NULL,
    fixed_bytes BINARY(2) NOT NULL,
    variable_bytes VARBINARY(8) NOT NULL
);

INSERT INTO binary_examples
    (id, bit_value, fixed_bytes, variable_bytes)
VALUES
    (1, b'00000101', X'0005', X'05');
~~~

Ở đây:

- `bit_value` mang giá trị bit 5.
- `fixed_bytes` có hai byte: `00 05`.
- `variable_bytes` có một byte: `05`.

Hai cột byte không có ý nghĩa tự động là số 5. Muốn diễn giải chuỗi byte thành số, ứng dụng phải xác định quy tắc mã hóa, thứ tự byte (endianness), độ dài và signedness.

### 5.2. Chuỗi nhị phân không có character set

`BINARY`, `VARBINARY` và các kiểu `BLOB` lưu byte, không có character set/collation như `CHAR`, `VARCHAR` hoặc `TEXT`.

Điều này phù hợp với:

- Hash (SHA-256, SHA-512).
- Binary token hoặc UUID ở dạng byte.
- Nội dung file hoặc payload.
- Dữ liệu mã hóa.
- Chuỗi byte từ giao thức.

Không nên lưu hash hoặc nội dung file trong `BIT(M)` chỉ vì chúng có thể viết dưới dạng bit. Ví dụ, SHA-256 có 256 bit, vượt quá giới hạn 64 bit của `BIT(M)`; nó cần một kiểu binary string như `BINARY(32)` hoặc `VARBINARY` phù hợp.

### 5.3. So sánh theo byte và theo giá trị

Với binary string, phép so sánh quan tâm đến byte. Với `BIT(M)`, mục đích là biểu diễn giá trị bit. Khi chuyển giữa hai dạng, cần định nghĩa rõ:

- Bao nhiêu bit hoặc byte được dùng.
- Byte nào đứng trước.
- Có thêm byte đệm hay không.
- Giá trị được xem là signed hay unsigned.
- Có cần bảo toàn các số 0 ở đầu hay không.

Nếu ứng dụng nhận một chuỗi byte từ giao thức và phải giữ nguyên byte, dùng binary string. Nếu ứng dụng cần kiểm tra hoặc bật/tắt các cờ bit có độ dài giới hạn, dùng BIT hoặc integer mask.

## 6. Phép toán bit và bit mask

Một ứng dụng phổ biến của `BIT(M)` là lưu nhiều cờ độc lập trong cùng một giá trị. Mỗi vị trí bit có ý nghĩa riêng và được gán một mask.

Ví dụ với `BIT(8)`:

| Bit index | Mask thập phân | Biểu diễn 8 bit | Ý nghĩa ví dụ |
|---:|---:|---|---|
| 0 | 1 | `00000001` | Đọc |
| 1 | 2 | `00000010` | Ghi |
| 2 | 4 | `00000100` | Xuất dữ liệu |
| 3 | 8 | `00001000` | Quản trị |
| 4 | 16 | `00010000` | Đồng bộ |
| 5 | 32 | `00100000` | Được thông báo |
| 6 | 64 | `01000000` | Dành riêng |
| 7 | 128 | `10000000` | Dành riêng |

Một mask tương ứng với lũy thừa của 2:

[
mask = 2^{bit\_index}
]

Ví dụ bit 2 có mask 4.

### 6.1. Kiểm tra một bit

Giả sử `status_flags` là `BIT(8)`, kiểm tra cờ xuất dữ liệu:

~~~sql
SELECT
    device_id,
    status_flags + 0 AS flags_value,
    ((status_flags + 0) & 4) <> 0 AS can_export
FROM device_state
ORDER BY device_id;
~~~

Phép AND bit (`&`) giữ lại các bit có giá trị 1 ở cả hai toán hạng. Nếu kết quả khác 0 thì cờ đang bật.

### 6.2. Bật một bit

Dùng OR bit (`|`) để bật cờ mà không làm thay đổi các bit khác:

~~~sql
UPDATE device_state
SET status_flags = (status_flags + 0) | 4
WHERE device_id = 1;
~~~

Nếu cờ đã bật, thao tác vẫn giữ nguyên giá trị. Câu lệnh được thực hiện ở server, tránh mô hình ứng dụng đọc mask cũ, sửa trong bộ nhớ rồi ghi đè toàn bộ mask.

### 6.3. Tắt một bit

Dùng AND với mặt nạ đảo bit:

~~~sql
UPDATE device_state
SET status_flags = (status_flags + 0) & ~4
WHERE device_id = 1;
~~~

`~4` tạo mặt nạ có bit 2 bằng 0 và các bit khác bằng 1 trong phép toán số nguyên. AND với giá trị hiện tại sẽ tắt bit 2, giữ các bit còn lại.

### 6.4. Đảo một bit

Dùng XOR (`^`) để đảo trạng thái:

~~~sql
UPDATE device_state
SET status_flags = (status_flags + 0) ^ 4
WHERE device_id = 1;
~~~

Nếu bit đang 0, nó thành 1; nếu đang 1, nó thành 0. Chỉ dùng toggle khi nghiệp vụ thực sự muốn đảo trạng thái. Nếu thao tác cần idempotent (chạy lại vẫn cùng kết quả), dùng bật bằng OR hoặc tắt bằng AND thay vì XOR.

### 6.5. Đếm số bit đang bật

Hàm `BIT_COUNT()` trả về số bit 1 trong biểu diễn nhị phân của giá trị số:

~~~sql
SELECT
    device_id,
    status_flags + 0 AS flags_value,
    BIT_COUNT(status_flags + 0) AS enabled_flag_count
FROM device_state;
~~~

Ví dụ số 5 có biểu diễn `00000101`, nên `BIT_COUNT(5)` trả về 2.

Với BIT column, dùng phép chuyển đổi số rõ ràng như `status_flags + 0` khi cần tránh cách diễn giải binary string của client hoặc biểu thức.

### 6.6. Cập nhật nhiều cờ trong một câu lệnh

Ví dụ bật cờ đọc và xuất dữ liệu:

~~~sql
UPDATE device_state
SET status_flags = (status_flags + 0) | (1 | 4)
WHERE device_id = 1;
~~~

Ví dụ chỉ giữ lại hai cờ đọc và ghi:

~~~sql
UPDATE device_state
SET status_flags = (status_flags + 0) & (1 | 2)
WHERE device_id = 1;
~~~

Cần định nghĩa mask nhất quán trong ứng dụng và tài liệu schema. Nếu hai nhóm phát triển hiểu cùng một bit theo hai ý nghĩa khác nhau, dữ liệu sẽ khó bảo trì.

## 7. BIT và thiết kế cờ trạng thái

### 7.1. Khi nào bit mask phù hợp?

Bit mask có thể phù hợp khi:

- Số lượng cờ nhỏ và đã biết trước.
- Các cờ có ý nghĩa độc lập, cố định.
- Truy vấn thường kiểm tra một hoặc vài bit.
- Ứng dụng có một định nghĩa mask thống nhất.
- Lợi ích về biểu diễn hoặc truyền tải thực sự đáng giá.

Ví dụ một thiết bị có tám tính năng bật/tắt cố định. Một cột `BIT(8)` có thể lưu toàn bộ trạng thái.

### 7.2. Khi nào nên dùng cột riêng?

Nếu các trạng thái cần truy vấn, thống kê, lọc và báo cáo thường xuyên, cột riêng dễ đọc hơn:

~~~sql
CREATE TABLE device_state_explicit (
    device_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    can_read BOOLEAN NOT NULL DEFAULT FALSE,
    can_write BOOLEAN NOT NULL DEFAULT FALSE,
    can_export BOOLEAN NOT NULL DEFAULT FALSE,
    can_admin BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Ưu điểm:

- SQL thể hiện ý nghĩa trực tiếp.
- Dễ tạo index theo từng cờ.
- Dễ đặt CHECK constraint và default.
- Dễ ánh xạ sang thuộc tính boolean của ứng dụng.
- Thêm hoặc đổi ý nghĩa một cờ không buộc mọi ứng dụng phải hiểu bit mask.

Nhược điểm là mỗi cờ chiếm một cột và schema có thể rộng hơn. Tuy nhiên, tối ưu dung lượng không phải lúc nào cũng quan trọng bằng tính rõ ràng và khả năng truy vấn.

### 7.3. Khi nào nên dùng bảng quan hệ?

Nếu quyền hoặc tính năng có thể thay đổi linh hoạt, có nhiều loại quyền, cần audit hoặc liên kết với vai trò, hãy cân nhắc mô hình quan hệ:

~~~sql
CREATE TABLE device_permission (
    device_id BIGINT UNSIGNED NOT NULL,
    permission_code VARCHAR(50) NOT NULL,
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (device_id, permission_code)
);
~~~

Mô hình này dễ thêm quyền mới mà không phải định nghĩa lại ý nghĩa từng bit. Nó cũng hỗ trợ truy vấn theo quyền, thống kê và ghi nhận từng quan hệ. Với hệ thống authorization phức tạp, không nên dùng một BIT mask duy nhất thay cho mô hình quyền và audit đầy đủ.

## 8. Index và hiệu năng truy vấn với BIT

Cột `BIT` có thể được lập index như các kiểu dữ liệu khác. Nhưng việc có index không đồng nghĩa mọi truy vấn bitwise sẽ sử dụng được index hiệu quả.

### 8.1. Index trên cột BIT

Ví dụ:

~~~sql
CREATE TABLE feature_record (
    record_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    flags BIT(8) NOT NULL,
    KEY idx_flags (flags)
);
~~~

Truy vấn so sánh toàn bộ giá trị có thể dùng index tùy cardinality, thống kê và kế hoạch thực thi:

~~~sql
SELECT record_id
FROM feature_record
WHERE flags = b'00000101';
~~~

Tuy nhiên, nếu chỉ có 256 giá trị khả dĩ và dữ liệu tập trung vào vài mask, index có thể không chọn lọc tốt.

### 8.2. Điều kiện bitwise thường khó tận dụng index trực tiếp

Ví dụ:

~~~sql
SELECT record_id
FROM feature_record
WHERE (flags + 0) & 4 <> 0;
~~~

Biểu thức thực hiện phép toán trên từng giá trị cột. Một B-tree index thông thường trên `flags` thường không thể biến điều kiện này thành một phép tra cứu range đơn giản. Optimizer có thể phải quét nhiều hoặc toàn bộ index/table.

Hãy kiểm tra bằng:

~~~sql
EXPLAIN
SELECT record_id
FROM feature_record
WHERE (flags + 0) & 4 <> 0;
~~~

Không nên khẳng định truy vấn sẽ luôn full table scan; quyết định phụ thuộc thống kê, kích thước bảng, index và phiên bản optimizer. Dùng `EXPLAIN ANALYZE` trên môi trường phù hợp để xem thực tế.

### 8.3. Generated column cho một cờ được truy vấn thường xuyên

Nếu một bit thường xuyên được lọc, có thể tạo generated column và lập index cho kết quả cờ:

~~~sql
CREATE TABLE feature_record_indexed (
    record_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    flags BIT(8) NOT NULL,
    has_export TINYINT
        GENERATED ALWAYS AS (
            ((flags + 0) & 4) <> 0
        ) STORED,
    KEY idx_has_export (has_export)
);
~~~

Sau đó truy vấn:

~~~sql
SELECT record_id
FROM feature_record_indexed
WHERE has_export = 1;
~~~

Optimizer có thể dùng index trên generated column nếu biểu thức và điều kiện phù hợp. Hãy kiểm tra bằng `EXPLAIN` và đo trên dữ liệu thực tế. Index trên cột có hai giá trị vẫn có thể không được chọn nếu phần lớn dòng cùng một giá trị.

### 8.4. Cân nhắc chi phí cập nhật và cạnh tranh

Nếu nhiều session cập nhật các cờ trên cùng một hàng, InnoDB vẫn cần khóa hàng cho thao tác cập nhật. Bit mask không loại bỏ row lock.

Dùng câu lệnh cập nhật bit ở server giúp tránh mất cập nhật do ứng dụng đọc một mask cũ rồi ghi lại toàn bộ giá trị. Tuy vậy, các transaction cạnh tranh trên cùng hàng vẫn có thể phải chờ và cần xử lý theo quy tắc concurrency thông thường.

## 9. Chuyển đổi và giới hạn giá trị

### 9.1. Giá trị vượt phạm vi

Với `BIT(4)`, giá trị hợp lệ nằm từ 0 đến 15. Giá trị 16 vượt phạm vi:

~~~sql
CREATE TABLE bit_range_test (
    id INT PRIMARY KEY,
    flags BIT(4) NOT NULL
);

INSERT INTO bit_range_test VALUES (1, 15);
~~~

Thử gán giá trị vượt phạm vi trong môi trường lab:

~~~sql
INSERT INTO bit_range_test VALUES (2, 16);
~~~

Hành vi báo lỗi, cảnh báo hoặc điều chỉnh giá trị phụ thuộc SQL mode và ngữ cảnh câu lệnh. Với chế độ strict, thao tác ngoài phạm vi thường bị từ chối. Trong chế độ không strict, server có thể phát cảnh báo và điều chỉnh giá trị. Không dựa vào hành vi cắt giá trị để kiểm soát dữ liệu nghiệp vụ.

Kiểm tra chế độ SQL:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

Thiết kế cột đủ rộng cho miền giá trị thực tế và kiểm tra dữ liệu đầu vào ở ứng dụng cũng như database.

### 9.2. Chuyển BIT thành integer

Có thể dùng phép cộng 0 hoặc CAST:

~~~sql
SELECT
    flags,
    flags + 0 AS flags_number,
    CAST(flags AS UNSIGNED) AS flags_unsigned
FROM bit_range_test;
~~~

Dùng `CAST(... AS UNSIGNED)` khi muốn thể hiện rõ ý định chuyển sang số nguyên không dấu. Với BIT(64), hãy kiểm tra cách ngôn ngữ và driver xử lý số nguyên unsigned 64-bit, vì không phải môi trường ứng dụng nào cũng có kiểu số nguyên signed 64-bit chứa được toàn bộ miền giá trị.

### 9.3. Chuyển binary string thành số

Nếu cột `VARBINARY` chứa byte, việc chuyển thành số phải có quy tắc. Không được giả định một chuỗi byte bất kỳ là số nguyên theo thứ tự byte mong muốn.

Ví dụ, `X'0102'` có hai byte `01 02`. Nếu ứng dụng xem byte đầu là byte cao, giá trị số tương ứng là 258; nếu xem byte đầu là byte thấp, giá trị là 513. Đây là quy ước endianness của ứng dụng/giao thức, không phải ý nghĩa tự động của `VARBINARY`.

Với BIT mask trong database, giữ giá trị BIT hoặc integer mask xuyên suốt thường đơn giản hơn việc chuyển qua lại giữa chuỗi byte và số.

## 10. Lựa chọn BIT, integer hay binary string

| Nhu cầu | Kiểu nên đánh giá | Lý do |
|---|---|---|
| Một cờ true/false dễ đọc trong SQL và ứng dụng | `BOOLEAN`/`TINYINT` + CHECK | Dễ ánh xạ, hiển thị và lọc |
| Một trường bit có độ dài cố định | `BIT(M)` | Thể hiện đúng ý nghĩa bit field |
| Nhiều cờ cố định trong một mask nhỏ | `BIT(M)` hoặc integer unsigned | Hỗ trợ phép toán bit |
| Số lượng, bộ đếm, ID hoặc mã trạng thái | Integer phù hợp miền giá trị | Có ngữ nghĩa số học rõ ràng |
| Hash SHA-256 | `BINARY(32)` | 32 byte dữ liệu cố định |
| UUID dạng byte | `BINARY(16)` | Lưu 16 byte, cần thống nhất byte order |
| Payload hoặc file | `BLOB`/`VARBINARY` | Lưu byte tùy độ dài |
| Chuỗi ký tự có ngữ nghĩa ngôn ngữ | `CHAR`/`VARCHAR`/`TEXT` | Có charset và collation |

Đây là hướng lựa chọn, không phải quy tắc tuyệt đối. Hãy cân nhắc cách ứng dụng đọc/ghi, truy vấn, index, tính tương thích driver, dung lượng và khả năng mở rộng schema.

## 11. Ví dụ tổng hợp: quản lý cờ tính năng thiết bị

Giả sử một hệ thống IoT có các thiết bị với bốn cờ: đọc, ghi, xuất dữ liệu và quản trị.

### 11.1. Định nghĩa schema

~~~sql
CREATE TABLE device_feature (
    device_id BIGINT UNSIGNED NOT NULL,
    flags BIT(8) NOT NULL DEFAULT b'00000000',
    PRIMARY KEY (device_id)
) ENGINE = InnoDB;
~~~

### 11.2. Gán trạng thái ban đầu

~~~sql
INSERT INTO device_feature (device_id, flags)
VALUES
    (101, b'00000101'),
    (102, b'00001011'),
    (103, b'00000000');
~~~

Theo quy ước:

- Bit 0 (mask 1): đọc.
- Bit 1 (mask 2): ghi.
- Bit 2 (mask 4): xuất dữ liệu.
- Bit 3 (mask 8): quản trị.

### 11.3. Đọc từng cờ

~~~sql
SELECT
    device_id,
    LPAD(BIN(flags + 0), 8, '0') AS flags_binary,
    ((flags + 0) & 1) <> 0 AS can_read,
    ((flags + 0) & 2) <> 0 AS can_write,
    ((flags + 0) & 4) <> 0 AS can_export,
    ((flags + 0) & 8) <> 0 AS can_admin
FROM device_feature
ORDER BY device_id;
~~~

### 11.4. Cập nhật không làm mất cờ khác

Bật quyền quản trị cho thiết bị 101:

~~~sql
UPDATE device_feature
SET flags = (flags + 0) | 8
WHERE device_id = 101;
~~~

Tắt quyền ghi:

~~~sql
UPDATE device_feature
SET flags = (flags + 0) & ~2
WHERE device_id = 101;
~~~

Kiểm tra:

~~~sql
SELECT
    device_id,
    flags + 0 AS flags_number,
    LPAD(BIN(flags + 0), 8, '0') AS flags_binary,
    BIT_COUNT(flags + 0) AS enabled_count
FROM device_feature
ORDER BY device_id;
~~~

### 11.5. Xác minh kết quả mong đợi

| Thiết bị | Trạng thái ban đầu | Bật quản trị | Tắt ghi | Kết quả cuối |
|---:|---|---|---|---|
| 101 | `00000101` | `00001101` | `00001101` | 13 |
| 102 | `00001011` | Không đổi | Không đổi | 11 |
| 103 | `00000000` | Không đổi | Không đổi | 0 |

Thiết bị 101 có giá trị ban đầu 5. Bật bit 3 (mask 8) tạo giá trị 13. Bit ghi vốn đang tắt nên thao tác tắt bit 1 không thay đổi kết quả. Bài tập này minh họa tính idempotent của phép OR để bật và AND với mặt nạ đảo để tắt.

## 12. Những lỗi thiết kế thường gặp

- **Dùng BIT cho mọi giá trị 0/1:** khiến SQL và mapping ứng dụng khó đọc hơn trong khi không có lợi ích rõ ràng.
- **Dùng BIT để lưu hash hoặc payload:** BIT tối đa 64 bit, không phù hợp dữ liệu binary tùy ý.
- **Không ghi tài liệu mask:** nhóm phát triển có thể gán cùng một bit cho hai ý nghĩa khác nhau.
- **Dùng XOR để bật cờ:** chạy lại câu lệnh sẽ đảo cờ về trạng thái cũ; dùng OR nếu muốn bật chắc chắn.
- **Đọc BIT như chuỗi văn bản:** có thể nhận byte không in được hoặc kết quả phụ thuộc client.
- **Coi BIT(1) là BOOLEAN của MySQL:** BOOLEAN là alias của TINYINT(1), không phải BIT(1).
- **Dùng điều kiện bitwise mà không kiểm tra kế hoạch:** biểu thức trên cột thường khó tận dụng B-tree index trực tiếp.
- **Ghi đè toàn bộ mask từ giá trị cũ trong ứng dụng:** có thể làm mất cập nhật của session khác.
- **Dùng mask thay mô hình phân quyền phức tạp:** khó mở rộng, audit và truy vấn theo quyền.
- **Không kiểm tra giá trị ngoài phạm vi:** có thể nhận lỗi hoặc dữ liệu bị điều chỉnh theo SQL mode.

## 13. Checklist trước khi chọn kiểu

- [ ] Đã xác định dữ liệu là bit field, số học hay chuỗi byte.
- [ ] Đã chọn M trong giới hạn 1–64 cho `BIT(M)`.
- [ ] Đã tính miền giá trị lớn nhất (2^M-1).
- [ ] Đã phân biệt NULL với bit 0.
- [ ] Đã chọn literal bit rõ ràng khi ghi script.
- [ ] Đã kiểm tra cách hiển thị và mapping của driver.
- [ ] Đã dùng chuyển đổi tường minh khi cần số nguyên hoặc chuỗi bit.
- [ ] Đã định nghĩa và tài liệu hóa mask của từng cờ.
- [ ] Đã chọn OR/AND/XOR đúng với ý nghĩa cập nhật.
- [ ] Đã kiểm tra SQL mode và hành vi khi giá trị vượt phạm vi.
- [ ] Đã đánh giá selectivity và kế hoạch thực thi nếu lập index.
- [ ] Đã cân nhắc cột riêng hoặc bảng quan hệ khi cờ cần truy vấn/audit linh hoạt.

## 14. Bài tập thực hành

### Bài 1: Quan sát biểu diễn BIT

Tạo bảng `BIT(1)`, `BIT(4)`, `BIT(8)`, `BIT(16)`. Chèn các giá trị 0, 1, 5, 15, 255 và 65535 vào cột có độ rộng phù hợp. Dùng `HEX()`, `BIN()` và phép cộng 0 để quan sát cách hiển thị.

Ghi lại sự khác nhau giữa giá trị số và số bit được hiển thị.

### Bài 2: So sánh BIT và BINARY

Tạo hai cột `BIT(8)` và `BINARY(1)`. Gán giá trị tương đương 5. Dùng `HEX()` để xem byte và giải thích vì sao một cột có ngữ nghĩa bit field còn cột kia là một byte.

### Bài 3: Thực hành bit mask

Tạo bảng thiết bị có `BIT(8)`. Định nghĩa ít nhất bốn mask. Thực hiện bật, tắt, đảo, kiểm tra và đếm số cờ đang bật. Chạy lại các lệnh bật/tắt để xác minh tính idempotent.

### Bài 4: Đọc kế hoạch thực thi

Tạo bảng lớn hơn với cột flags và index. So sánh `EXPLAIN` của:

- `WHERE flags = b'00000101'`
- `WHERE (flags + 0) & 4 <> 0`

Ghi lại access type, key, rows ước tính và giải thích vì sao điều kiện bitwise có thể không tận dụng index thông thường.

### Bài 5: Đề xuất mô hình dữ liệu

Với một hệ thống phân quyền có thể thêm quyền mới thường xuyên, hãy so sánh ba cách:

1. Một cột `BIT(16)` chứa mask.
2. Mỗi quyền là một cột BOOLEAN.
3. Bảng quan hệ `user_permission`.

Đánh giá khả năng mở rộng, truy vấn, index, audit và độ phức tạp ứng dụng.

## 15. Kết luận

`BIT(M)` là kiểu dữ liệu cho bit field có độ dài từ 1 đến 64 bit. Nó phù hợp khi cần lưu một tập bit cố định và thực hiện phép toán mask. Kiểu số nguyên phù hợp hơn với dữ liệu có ý nghĩa số học hoặc cần được đọc và xử lý thuận tiện. `BINARY`, `VARBINARY` và `BLOB` phù hợp với chuỗi byte, hash, UUID và payload.

Khi chọn kiểu, hãy xét ý nghĩa dữ liệu trước dung lượng. Nếu dùng BIT mask, cần định nghĩa rõ từng bit, chuyển đổi tường minh khi hiển thị, cập nhật bằng phép toán phù hợp và kiểm tra kế hoạch truy vấn. Nếu các cờ cần truy vấn, audit hoặc mở rộng linh hoạt, cột riêng hay bảng quan hệ thường là thiết kế dễ bảo trì hơn.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – BIT Type](https://dev.mysql.com/doc/refman/8.4/en/bit-type.html)
- [MySQL 8.4 Reference Manual – Integer Types](https://dev.mysql.com/doc/refman/8.4/en/integer-types.html)
- [MySQL 8.4 Reference Manual – BINARY and VARBINARY Types](https://dev.mysql.com/doc/refman/8.4/en/binary-varbinary.html)
- [MySQL 8.4 Reference Manual – Bit-Value Literals](https://dev.mysql.com/doc/refman/8.4/en/bit-value-literals.html)
- [MySQL 8.4 Reference Manual – Bit Functions and Operators](https://dev.mysql.com/doc/refman/8.4/en/bit-functions.html)
- [MySQL 8.4 Reference Manual – Numeric Type Attributes](https://dev.mysql.com/doc/refman/8.4/en/numeric-type-attributes.html)
- [MySQL 8.4 Reference Manual – CHECK Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)


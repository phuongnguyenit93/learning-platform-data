# DEFAULT CURRENT_TIMESTAMP và ON UPDATE CURRENT_TIMESTAMP

MySQL có thể tự gán thời điểm tạo bản ghi và tự cập nhật thời điểm sửa đổi thông qua hai thuộc tính cột `DEFAULT CURRENT_TIMESTAMP` và `ON UPDATE CURRENT_TIMESTAMP`. Chúng thường được dùng cho các cột `created_at` và `updated_at` trong bảng nghiệp vụ.

`DEFAULT CURRENT_TIMESTAMP` cung cấp giá trị thời gian khi `INSERT` không truyền giá trị cho cột. `ON UPDATE CURRENT_TIMESTAMP` yêu cầu MySQL cập nhật cột khi một hàng thay đổi. Có thể dùng riêng từng thuộc tính hoặc kết hợp cả hai. Để hành vi rõ ràng, schema thường khai báo cả hai cho `updated_at`, còn `created_at` chỉ cần giá trị mặc định.

Bài học này giải thích cách hoạt động, cú pháp, độ chính xác phần giây, khác biệt múi giờ giữa `TIMESTAMP` và `DATETIME`, các trường hợp cập nhật đặc biệt và cách kiểm thử hành vi trên MySQL 8.x.

## 1. DEFAULT CURRENT_TIMESTAMP dùng để làm gì?

`DEFAULT` xác định giá trị MySQL dùng khi câu lệnh `INSERT` không cung cấp giá trị cho cột hoặc yêu cầu rõ `DEFAULT`.

Ví dụ:

```sql
CREATE TABLE articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Khi thêm bản ghi mà bỏ qua `created_at`:

```sql
INSERT INTO articles (title)
VALUES ('Giới thiệu MySQL');

SELECT id, title, created_at
FROM articles;
```

MySQL tự lấy thời điểm hiện tại làm giá trị `created_at`. Ứng dụng không cần tự tạo timestamp cho trường hợp insert thông thường.

Có thể yêu cầu MySQL dùng default một cách tường minh:

```sql
INSERT INTO articles (title, created_at)
VALUES ('Thiết kế schema', DEFAULT);
```

Hai cách sau đều sử dụng giá trị mặc định:

- Bỏ cột khỏi danh sách `INSERT`.
- Đưa từ khóa `DEFAULT` vào vị trí giá trị của cột.

`DEFAULT CURRENT_TIMESTAMP` không có nghĩa MySQL tự ghi đè giá trị mà ứng dụng truyền vào. Nếu `INSERT` cung cấp một giá trị cụ thể hợp lệ, MySQL sử dụng giá trị đó.

## 2. ON UPDATE CURRENT_TIMESTAMP dùng để làm gì?

`ON UPDATE CURRENT_TIMESTAMP` tự cập nhật giá trị thời gian khi một hàng được thay đổi. Ví dụ:

```sql
CREATE TABLE articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Hai cột có trách nhiệm khác nhau:

- `created_at` ghi nhận thời điểm tạo. Vì không có `ON UPDATE`, giá trị không tự thay đổi khi cập nhật hàng.
- `updated_at` nhận thời điểm hiện tại khi insert và tự cập nhật khi hàng thay đổi.

Ví dụ:

```sql
INSERT INTO articles (title)
VALUES ('Thiết kế bảng');

SELECT id, title, created_at, updated_at
FROM articles;

UPDATE articles
SET title = 'Thiết kế bảng MySQL'
WHERE id = 1;

SELECT id, title, created_at, updated_at
FROM articles
WHERE id = 1;
```

Sau câu `UPDATE` làm thay đổi `title`, MySQL tự cập nhật `updated_at`. `created_at` giữ nguyên.

## 3. Kết hợp DEFAULT và ON UPDATE

Với cột cần tự nhận thời điểm lúc tạo và tự cập nhật khi sửa, khai báo cả hai thuộc tính:

```sql
updated_at DATETIME NOT NULL
    DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP
```

Đây là mẫu phổ biến cho cột thời điểm sửa đổi. Nếu chỉ khai báo `ON UPDATE CURRENT_TIMESTAMP` mà không khai báo `DEFAULT`, giá trị mặc định lúc insert sẽ phụ thuộc thuộc tính NULL/NOT NULL và quy tắc mặc định của kiểu dữ liệu. Vì vậy, hãy khai báo rõ `DEFAULT` khi muốn có thời điểm khởi tạo xác định.

Có thể dùng `CURRENT_TIMESTAMP()` với dấu ngoặc hoặc dạng không có dấu ngoặc. `NOW()` là hàm đồng nghĩa với `CURRENT_TIMESTAMP` trong các biểu thức SQL, nhưng trong DDL nên dùng dạng `CURRENT_TIMESTAMP` để thể hiện rõ thuộc tính tự động của cột.

## 4. Ví dụ thực tế với created_at và updated_at

Một bảng tài khoản có thể được thiết kế như sau:

```sql
CREATE TABLE customer_accounts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_customer_accounts_email (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Thêm tài khoản:

```sql
INSERT INTO customer_accounts (email, display_name)
VALUES ('linh@example.test', 'Nguyễn Linh');
```

Không cần truyền `created_at` hoặc `updated_at`; cả hai được MySQL gán giá trị mặc định.

Đổi tên hiển thị:

```sql
UPDATE customer_accounts
SET display_name = 'Linh Nguyễn'
WHERE email = 'linh@example.test';
```

`updated_at` được cập nhật tự động; `created_at` không thay đổi. Đây là cách đơn giản để ứng dụng có thể hiển thị thời điểm bản ghi được tạo và lần cập nhật gần nhất.

## 5. Điều kiện để ON UPDATE được kích hoạt

MySQL tự cập nhật cột có `ON UPDATE CURRENT_TIMESTAMP` khi giá trị của hàng thay đổi thực sự. Không phải cứ chạy câu lệnh `UPDATE` là timestamp luôn đổi.

Ví dụ, nếu `display_name` đã là `'Linh Nguyễn'`:

```sql
UPDATE customer_accounts
SET display_name = 'Linh Nguyễn'
WHERE email = 'linh@example.test';
```

Nếu không có cột nào thực sự thay đổi giá trị, `updated_at` không tự đổi chỉ vì câu lệnh đã được gửi.

Ngược lại, thay đổi một cột bất kỳ khác trong cùng hàng có thể kích hoạt cập nhật timestamp:

```sql
UPDATE customer_accounts
SET is_active = FALSE
WHERE email = 'linh@example.test';
```

Nếu `is_active` chuyển từ `TRUE` sang `FALSE`, `updated_at` được cập nhật. Cơ chế này không chỉ theo dõi một cột cụ thể như `display_name`; nó theo dõi thay đổi của hàng.

## 6. Chủ động ghi đè hoặc ngăn cập nhật timestamp

Ứng dụng vẫn có thể truyền giá trị tường minh cho cột có `ON UPDATE`.

### 6.1. Ghi một thời điểm cụ thể

```sql
UPDATE customer_accounts
SET display_name = 'Linh N.',
    updated_at = '2026-11-19 09:30:00'
WHERE id = 1;
```

Khi chỉ định giá trị tường minh cho `updated_at`, MySQL dùng giá trị được cung cấp thay cho việc tự sinh thời điểm hiện tại. Cách này có thể hữu ích khi nhập dữ liệu lịch sử hoặc đồng bộ dữ liệu, nhưng cần kiểm soát timezone và nguồn thời gian.

### 6.2. Không thay đổi timestamp tự động trong một lần update

Nếu muốn cập nhật cột khác nhưng giữ nguyên `updated_at`, có thể gán chính cột đó về giá trị hiện tại của nó:

```sql
UPDATE customer_accounts
SET display_name = 'Linh N.',
    updated_at = updated_at
WHERE id = 1;
```

Khi cột timestamp được gán tường minh bằng chính giá trị hiện tại, quy tắc tự động cập nhật không thay thế nó. Chỉ dùng cách này khi nghiệp vụ thực sự yêu cầu bỏ qua dấu thời gian cập nhật; nếu làm thường xuyên, nên cân nhắc thiết kế một cột hoặc luồng dữ liệu riêng để thể hiện thay đổi không mang tính nghiệp vụ.

## 7. INSERT, NULL và DEFAULT

Cần phân biệt ba trường hợp:

| Cách insert | Hành vi |
| --- | --- |
| Bỏ qua cột | MySQL dùng default của cột nếu có |
| Ghi `DEFAULT` | MySQL dùng default của cột |
| Truyền `NULL` | Cột nullable nhận `NULL`; cột `NOT NULL` thường báo lỗi trong strict mode |

Ví dụ với cột nullable:

```sql
CREATE TABLE optional_dates (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    label VARCHAR(80) NOT NULL,
    happened_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO optional_dates (label)
VALUES ('Dùng default');

INSERT INTO optional_dates (label, happened_at)
VALUES ('Chủ động để NULL', NULL);

INSERT INTO optional_dates (label, happened_at)
VALUES ('Yêu cầu default', DEFAULT);
```

Dòng thứ nhất và thứ ba nhận giá trị default; dòng thứ hai nhận `NULL`. Không dùng `NULL` với kỳ vọng MySQL luôn tự thay bằng thời điểm hiện tại. Một số hành vi lịch sử riêng của `TIMESTAMP` phụ thuộc `explicit_defaults_for_timestamp` ở các phiên bản cũ; không nên dựa vào hành vi tương thích đó trong schema mới.

Nếu cột thời gian bắt buộc phải có giá trị, khai báo `NOT NULL` và xác định default rõ ràng. Nếu `NULL` mang ý nghĩa nghiệp vụ như “chưa xác định thời điểm”, khai báo nullable và xử lý trường hợp này trong ứng dụng.

## 8. Độ chính xác phần giây (fractional seconds precision)

MySQL hỗ trợ độ chính xác phần giây từ 0 đến 6 cho `TIMESTAMP` và `DATETIME`:

- `DATETIME` hoặc `TIMESTAMP` không ghi độ chính xác: mặc định 0, chỉ lưu đến giây.
- `(3)`: lưu đến mili giây.
- `(6)`: lưu đến micro giây.

Khai báo cột và hàm thời gian nên dùng cùng độ chính xác:

```sql
CREATE TABLE api_requests (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    request_path VARCHAR(255) NOT NULL,
    created_at DATETIME(3) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(3)
        ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

`CURRENT_TIMESTAMP(3)` tạo giá trị với độ chính xác mili giây; `CURRENT_TIMESTAMP(6)` dùng micro giây. Nếu cột chỉ có độ chính xác 0 mà ứng dụng truyền giá trị có phần giây, MySQL sẽ điều chỉnh theo độ chính xác của cột. Cần kiểm tra chế độ làm tròn/cắt và driver đang sử dụng nếu dữ liệu thời gian yêu cầu độ chính xác cao.

Không nên dùng độ chính xác `(6)` cho mọi cột theo thói quen. Nó làm tăng độ chi tiết của dữ liệu và có thể ảnh hưởng kích thước index hoặc định dạng trao đổi; chỉ chọn khi nghiệp vụ cần phân biệt các sự kiện xảy ra rất gần nhau.

## 9. CURRENT_TIMESTAMP và múi giờ phiên kết nối

`CURRENT_TIMESTAMP` trả về thời điểm hiện tại theo múi giờ của session MySQL. Vì vậy, cấu hình `time_zone` ảnh hưởng đến giá trị được sinh ra.

Kiểm tra múi giờ:

```sql
SELECT
    @@GLOBAL.time_zone AS global_time_zone,
    @@SESSION.time_zone AS session_time_zone,
    NOW() AS session_now,
    UTC_TIMESTAMP() AS utc_now;
```

Khác biệt quan trọng giữa hai kiểu dữ liệu:

- `TIMESTAMP` chuyển đổi giữa múi giờ session và UTC khi lưu/đọc. MySQL lưu giá trị theo UTC và hiển thị theo múi giờ session.
- `DATETIME` lưu các thành phần ngày giờ như được cung cấp; MySQL không tự chuyển đổi múi giờ cho giá trị `DATETIME`.

Ví dụ nếu session dùng `'+07:00'`, `CURRENT_TIMESTAMP` trả thời điểm theo giờ session. Khi gán cho cột `TIMESTAMP`, MySQL chuyển giá trị về UTC để lưu rồi chuyển lại khi đọc ở session đó. Khi gán cho `DATETIME`, giá trị giờ theo session được lưu trực tiếp như một datetime không kèm timezone.

Để các kết nối sinh timestamp nhất quán, hệ thống thường cấu hình timezone session là UTC:

```sql
SET SESSION time_zone = '+00:00';
```

Trong ứng dụng có connection pool, cần đặt timezone cho mọi kết nối khi khởi tạo hoặc dùng cấu hình driver phù hợp. Không chỉ chạy `SET time_zone` một lần trên một kết nối rồi giả định tất cả connection khác cũng thay đổi.

Nếu nghiệp vụ cần lưu một thời điểm tuyệt đối, `TIMESTAMP` với session UTC thường là lựa chọn phù hợp trong phạm vi giới hạn miền giá trị của kiểu dữ liệu. Nếu cần lưu giờ địa phương như “09:00 tại cửa hàng” mà không đại diện một instant cụ thể, `DATETIME` có thể phù hợp; cần lưu thêm timezone nếu phải chuyển đổi chính xác qua DST hoặc múi giờ khác.

## 10. CURRENT_TIMESTAMP là thời điểm nào?

Trong MySQL, `CURRENT_TIMESTAMP`, `NOW()` và `LOCALTIME` là các biểu thức đồng nghĩa về giá trị thời gian hiện tại trong ngữ cảnh thông thường. Giá trị `NOW()` được cố định tại thời điểm bắt đầu thực thi câu lệnh hiện tại; nhiều lần gọi trong cùng câu lệnh trả về cùng một thời điểm.

Điều đó có nghĩa `updated_at` không phải lúc transaction được commit, cũng không nhất thiết là thời điểm cuối cùng một giao dịch dài kết thúc. Nó thường biểu diễn thời điểm câu lệnh thay đổi hàng được thực thi. Nếu nghiệp vụ cần thời điểm commit, thời điểm nhận sự kiện ở hệ thống bên ngoài hoặc lịch sử đầy đủ, cần một thiết kế audit/event riêng.

`SYSDATE()` có ngữ nghĩa khác: nó trả thời gian tại thời điểm hàm được thực thi và có thể thay đổi giữa các lần gọi trong cùng một câu lệnh. Không thay `CURRENT_TIMESTAMP` bằng `SYSDATE()` trong default/on-update nếu chưa hiểu sự khác biệt và yêu cầu replication.

## 11. Nhiều cột thời gian trong cùng bảng

MySQL hiện đại cho phép nhiều cột `TIMESTAMP` hoặc `DATETIME` có thuộc tính tự động khởi tạo/cập nhật. Ví dụ:

```sql
CREATE TABLE documents (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    published_at DATETIME NULL DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

`published_at` không tự nhận thời gian hiện tại vì nghiệp vụ chỉ ghi nhận lúc tài liệu được xuất bản; `created_at` nhận thời điểm tạo; `updated_at` tự cập nhật khi hàng thay đổi.

Các phiên bản MySQL cũ có giới hạn lịch sử đối với việc tự động khởi tạo/cập nhật nhiều cột `TIMESTAMP`. Nếu cần hỗ trợ phiên bản cũ, hãy kiểm tra tài liệu của đúng phiên bản và biến `explicit_defaults_for_timestamp`; không giả định mọi server có cùng hành vi.

## 12. INSERT ... ON DUPLICATE KEY UPDATE và REPLACE

Khi dùng upsert, quy tắc tự động cập nhật vẫn có thể áp dụng nếu hàng hiện tại thực sự thay đổi:

```sql
INSERT INTO customer_accounts (email, display_name)
VALUES ('linh@example.test', 'Linh Nguyễn') AS new
ON DUPLICATE KEY UPDATE
    display_name = new.display_name;
```

Nếu email đã tồn tại và `display_name` thay đổi, `updated_at` được tự cập nhật. Nếu giá trị vẫn giống hiện tại, hàng không đổi và timestamp không nhất thiết thay đổi. Cú pháp alias hàng mới trong ví dụ yêu cầu MySQL 8.0.19 trở lên; `VALUES(column)` trong mệnh đề `ON DUPLICATE KEY UPDATE` đã bị deprecated từ MySQL 8.0.20.

`REPLACE` có ngữ nghĩa xóa hàng xung đột rồi chèn hàng mới. Vì vậy, các cột thời gian có default có thể nhận giá trị mới như một lần insert; `created_at` có thể thay đổi. Không dùng `REPLACE` như một bản thay thế đơn giản cho `UPDATE` nếu cần giữ nguyên thời điểm tạo và các quan hệ liên quan.

## 13. Cập nhật hàng loạt và migration

Một lệnh cập nhật hàng loạt có thể làm `updated_at` thay đổi trên nhiều hàng:

```sql
UPDATE customer_accounts
SET is_active = FALSE
WHERE last_login_at < '2025-01-01';
```

Nếu điều kiện khớp nhiều hàng và `is_active` thực sự thay đổi, `updated_at` của từng hàng sẽ được cập nhật. Điều này có thể ảnh hưởng báo cáo, đồng bộ dữ liệu và job đọc theo `updated_at`.

Trước khi chạy migration hoặc backfill trên bảng lớn, cần xác định có muốn kích hoạt cập nhật timestamp hay không. Nếu đang nhập lại dữ liệu lịch sử, có thể cung cấp `updated_at` tường minh theo quy tắc dữ liệu đích; nếu không, để cơ chế tự động ghi thời điểm xử lý hiện tại. Không nên âm thầm thay đổi semantics timestamp chỉ để làm cho migration chạy qua.

## 14. Trigger và ứng dụng cùng cập nhật timestamp

Có thể cập nhật `updated_at` ở ứng dụng, trigger hoặc cơ chế `ON UPDATE CURRENT_TIMESTAMP`. Không nên triển khai nhiều cơ chế cùng ghi một cột mà không có quy tắc ưu tiên rõ ràng.

Nếu ứng dụng gửi `updated_at` tường minh, nó có thể ghi đè thời gian do MySQL tự sinh. Nếu trigger `BEFORE UPDATE` thay đổi cột, cần kiểm tra tương tác với thuộc tính `ON UPDATE`. Điều này dễ tạo ra hành vi khó hiểu khi mỗi tầng dùng timezone hoặc đồng hồ khác nhau.

Hãy chọn một nguồn có thẩm quyền cho timestamp sửa đổi. Nếu database là nguồn chính, dùng thuộc tính cột và hạn chế ứng dụng ghi đè. Nếu cần thời gian do dịch vụ nghiệp vụ xác định, truyền giá trị tường minh và thiết kế rõ cách xử lý đồng hồ, timezone, retry và đồng bộ.

## 15. Kiểm tra định nghĩa và hành vi

Đọc DDL của bảng:

```sql
SHOW CREATE TABLE customer_accounts\G
```

Kiểm tra metadata cột:

```sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA,
    DATETIME_PRECISION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer_accounts'
ORDER BY ORDINAL_POSITION;
```

`COLUMN_DEFAULT` cho biết giá trị mặc định được khai báo; `EXTRA` có thể cho biết thuộc tính `on update CURRENT_TIMESTAMP`; `DATETIME_PRECISION` cho biết độ chính xác phần giây.

Có thể kiểm thử bằng cách chụp lại timestamp trước/sau cập nhật:

```sql
SELECT id, created_at, updated_at
FROM customer_accounts
WHERE id = 1;

UPDATE customer_accounts
SET display_name = CONCAT(display_name, ' ')
WHERE id = 1;

SELECT id, created_at, updated_at
FROM customer_accounts
WHERE id = 1;
```

Trong môi trường lab, so sánh `created_at` và `updated_at` sau insert, sau update có thay đổi và sau update không làm thay đổi giá trị. Nếu dùng độ chính xác 0, hai thao tác gần nhau trong cùng một giây có thể khó phân biệt; dùng `(3)` hoặc `(6)` khi cần quan sát độ chi tiết cao hơn.

## 16. Các lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| `DEFAULT CURRENT_TIMESTAMP` tự đổi khi update | Thuộc tính này chỉ cung cấp default khi insert hoặc yêu cầu `DEFAULT` | Thêm `ON UPDATE CURRENT_TIMESTAMP` nếu cần tự cập nhật |
| `ON UPDATE` luôn đổi khi chạy UPDATE | Chỉ tự đổi khi hàng thực sự thay đổi và cột không bị gán giá trị tường minh khác | Kiểm tra giá trị trước/sau và câu lệnh cập nhật |
| Truyền `NULL` tương đương dùng default | Cột nullable nhận `NULL`; cột `NOT NULL` có thể báo lỗi | Bỏ cột khỏi INSERT hoặc dùng từ khóa `DEFAULT` |
| `TIMESTAMP` và `DATETIME` tự đổi timezone giống nhau | `TIMESTAMP` chuyển đổi theo timezone session; `DATETIME` không tự chuyển đổi | Chọn kiểu theo ngữ nghĩa và cấu hình session timezone |
| `updated_at` là thời điểm commit | `CURRENT_TIMESTAMP` phản ánh thời điểm thực thi câu lệnh | Dùng audit/event nếu cần lịch sử hoặc thời điểm commit |
| `REPLACE` giống UPDATE | `REPLACE` có ngữ nghĩa xóa rồi chèn | Dùng `UPDATE` hoặc upsert khi cần giữ lịch sử tạo |
| App và trigger cùng ghi timestamp mà không có quy tắc | Có thể ghi đè hoặc tạo lệch thời gian | Chọn một nguồn có thẩm quyền và kiểm thử tương tác |

## 17. Bài tập thực hành

1. Tạo bảng `tasks` có `created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` và `updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP`.
2. Insert một task mà không truyền hai cột thời gian; kiểm tra giá trị được tạo.
3. Cập nhật `title` sang giá trị khác; xác minh `updated_at` thay đổi và `created_at` giữ nguyên.
4. Chạy một lệnh update đặt lại `title` bằng đúng giá trị hiện tại; quan sát `updated_at`.
5. Cập nhật một cột khác như `is_done`; xác minh `updated_at` tự đổi.
6. Thử insert với cột thời gian bị bỏ qua, dùng `DEFAULT` và truyền `NULL`; giải thích kết quả theo nullability và SQL mode.
7. Tạo `DATETIME(3)` và `TIMESTAMP(6)` với `CURRENT_TIMESTAMP` cùng độ chính xác; kiểm tra phần giây.
8. Thay `time_zone` session giữa `'+00:00'` và `'+07:00'`; so sánh `NOW()`, `UTC_TIMESTAMP()`, `TIMESTAMP` và `DATETIME`.
9. Kiểm tra `INFORMATION_SCHEMA.COLUMNS` để đọc `COLUMN_DEFAULT`, `EXTRA` và `DATETIME_PRECISION`.
10. Thiết kế một migration backfill và giải thích có nên giữ timestamp lịch sử hay để database ghi thời điểm xử lý hiện tại.

## 18. Ghi nhớ

`DEFAULT CURRENT_TIMESTAMP` gán thời điểm hiện tại khi insert bỏ qua cột hoặc yêu cầu `DEFAULT`. `ON UPDATE CURRENT_TIMESTAMP` tự cập nhật thời điểm khi hàng thay đổi thực sự. Dùng cả hai cho `updated_at` nếu cần tự khởi tạo và tự cập nhật; dùng riêng `DEFAULT` cho `created_at` để giữ thời điểm tạo.

Độ chính xác phần giây có thể chọn từ 0 đến 6 và nên thống nhất giữa kiểu cột với `CURRENT_TIMESTAMP(fsp)`. `CURRENT_TIMESTAMP` phụ thuộc timezone session; `TIMESTAMP` chuyển đổi qua UTC còn `DATETIME` lưu giá trị ngày giờ nguyên trạng. Cần phân biệt `NULL` với `DEFAULT`, hiểu ảnh hưởng của upsert/REPLACE và tránh để ứng dụng, trigger cùng database ghi timestamp theo các quy tắc xung đột. Luôn kiểm tra DDL và metadata thực tế trước khi đưa hành vi thời gian vào production.

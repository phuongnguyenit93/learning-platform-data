# Nạp hoặc thay đổi dữ liệu theo lô có thể thực hiện lại an toàn

Trong module DATABASE_MYSQL, quy trình nạp và thay đổi dữ liệu phải phối hợp thiết kế bảng, kiểu dữ liệu, khóa, constraint, transaction và kiểm soát đồng thời. Một quy trình nạp dữ liệu cần chịu được timeout, mất kết nối và retry. Tính idempotent bảo đảm chạy lại cùng batch không tạo bản ghi trùng, không cộng delta lần nữa và không ghi đè phiên bản mới bằng dữ liệu cũ.

## 1. Idempotency trong thao tác dữ liệu là gì?

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng một yêu cầu mà trạng thái cuối vẫn như sau khi thực hiện một lần. Ví dụ, lần đầu nạp khách hàng có mã nguồn C-100 tạo một hàng; chạy lại cùng batch thì database nhận ra C-100 đã tồn tại và cập nhật cùng dữ liệu hoặc không làm gì. Hệ thống không tạo thêm hàng khách hàng thứ hai và không áp dụng một thay đổi cộng dồn thêm lần nữa.

Idempotency quan trọng khi ứng dụng retry sau timeout, job định kỳ chạy lại sau deploy, người vận hành khởi động lại batch bị gián đoạn, hoặc nhiều worker có thể nhận cùng một message.

Không phải mọi câu SQL chạy hai lần đều idempotent:

~~~sql
-- Không idempotent: mỗi lần chạy lại đều tăng thêm 10
UPDATE inventory
SET quantity = quantity + 10
WHERE product_id = 1001;

-- Có thể idempotent nếu giá trị đầu vào là trạng thái tuyệt đối
UPDATE inventory
SET quantity = 50
WHERE product_id = 1001;
~~~

Lệnh đầu mô tả một delta cần cộng thêm. Nếu retry cùng lệnh, số lượng bị cộng nhiều lần. Lệnh thứ hai mô tả trạng thái đích; chạy lại với cùng giá trị sẽ không tiếp tục làm thay đổi số lượng.

## 2. Xác định khóa nghiệp vụ trước khi nạp dữ liệu

Một quy trình import cần biết một bản ghi nguồn tương ứng với bản ghi nào trong bảng đích. Không nên chỉ SELECT kiểm tra rồi mới INSERT, vì hai worker có thể cùng thấy chưa có hàng và cùng chèn.

Hãy dùng khóa nghiệp vụ ổn định, chẳng hạn mã khách hàng từ hệ thống nguồn:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    external_id VARCHAR(64) NOT NULL,
    email VARCHAR(255) NULL,
    full_name VARCHAR(150) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_external_id (external_id)
) ENGINE=InnoDB;
~~~

Ràng buộc UNIQUE trên external_id là hàng rào cuối cùng chống tạo bản ghi trùng. Dù hai request đến đồng thời, database vẫn không cho phép hai hàng có cùng mã nguồn.

Khóa idempotency nên ổn định giữa lần chạy đầu và retry, đại diện cho cùng một thực thể hoặc yêu cầu nghiệp vụ, không phụ thuộc số thứ tự dòng nếu thứ tự file có thể thay đổi, và được bảo vệ bằng PRIMARY KEY hoặc UNIQUE ở database.

Không dùng email làm khóa nghiệp vụ nếu email có thể thay đổi hoặc được chia sẻ. Nếu một khách hàng có mã nguồn riêng, hãy dùng mã đó. Với khóa ghép, khai báo đầy đủ các thành phần bằng một unique index.

## 3. Phân biệt khóa bản ghi và khóa batch

Một quy trình nạp theo lô thường cần hai loại định danh:

| Định danh | Phạm vi | Mục đích |
|---|---|---|
| Business key | Một thực thể, ví dụ external_id | Nhận diện bản ghi để insert hoặc update |
| Batch key / idempotency key | Một lần giao dữ liệu logic, ví dụ source + version hoặc file checksum | Nhận diện lần nạp để retry không xử lý trùng |

Batch ID phải được tạo và lưu trước khi bắt đầu xử lý, sau đó giữ nguyên qua mọi lần retry. Nếu mỗi lần retry lại sinh UUID mới, database sẽ xem đó là batch mới và không thể nhận diện yêu cầu cũ.

## 4. Theo dõi trạng thái batch bằng bảng ledger

Tạo bảng lưu lịch sử batch:

~~~sql
CREATE TABLE import_batches (
    batch_id VARCHAR(100) NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    source_version VARCHAR(100) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    status ENUM('LOADING', 'READY', 'COMPLETED', 'FAILED') NOT NULL,
    expected_rows BIGINT UNSIGNED NULL,
    staged_rows BIGINT UNSIGNED NULL,
    processed_rows BIGINT UNSIGNED NULL,
    started_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at TIMESTAMP(6) NULL,
    PRIMARY KEY (batch_id),
    UNIQUE KEY uq_import_source_version (source_name, source_version)
) ENGINE=InnoDB;
~~~

Ý nghĩa các trường:

- batch_id là idempotency key ổn định.
- source_name và source_version xác định nguồn cùng phiên bản dữ liệu.
- content_sha256 giúp phát hiện cùng source version nhưng nội dung file bị thay đổi.
- status cho biết batch đang nạp, đã sẵn sàng merge, hoàn thành hay thất bại.
- expected_rows là số dòng nguồn dự kiến; staged_rows là số dòng đã nạp và qua bước chuẩn hóa; processed_rows là số dòng đã được merge/đánh dấu xử lý.

Đăng ký batch trước khi nạp file bằng batch key đã được xác định:

~~~sql
INSERT INTO import_batches (
    batch_id,
    source_name,
    source_version,
    content_sha256,
    status,
    expected_rows
)
VALUES (
    'customers-2026-11-v1',
    'crm',
    'v1',
    '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    'LOADING',
    10000
);
~~~

Nếu INSERT bị duplicate do batch đã đăng ký, hãy đọc hàng ledger hiện có và so sánh checksum, source version cùng trạng thái. Không đổi batch_id để né xung đột; cùng một khóa nguồn nhưng checksum khác phải được xử lý như một xung đột dữ liệu.

Chuỗi checksum trong ví dụ là giá trị minh họa; ứng dụng phải tính SHA-256 từ nội dung file thực tế và lưu đúng kết quả đó.

Khi một batch đã COMPLETED, lần retry nên đọc ledger và trả kết quả đã hoàn tất thay vì merge lại. Nếu cùng source/version nhưng checksum khác, dừng và điều tra; không âm thầm xem đó là cùng một batch.

Không chỉ lưu cờ hoàn thành ở ứng dụng. Cập nhật trạng thái COMPLETED trong cùng transaction với thay đổi bảng đích để trạng thái ledger và dữ liệu không lệch nhau.

## 5. Dùng staging table để tách nạp và áp dụng dữ liệu

Đối với file lớn hoặc dữ liệu từ nhiều nguồn, không nên nạp trực tiếp vào bảng nghiệp vụ. Dùng staging table để tiếp nhận, kiểm tra, chuẩn hóa và loại dữ liệu lỗi trước khi merge:

~~~sql
CREATE TABLE customer_stage (
    batch_id VARCHAR(100) NOT NULL,
    external_id VARCHAR(64) NOT NULL,
    email VARCHAR(255) NULL,
    full_name VARCHAR(150) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (batch_id, external_id)
) ENGINE=InnoDB;
~~~

Khóa chính ghép bảo đảm mỗi batch chỉ có một hàng cho một external_id. Nếu file có hai hàng cùng external_id, bước nạp phát hiện xung đột thay vì tự ý chọn một hàng. Nếu nguồn hợp lệ cho phép nhiều thay đổi của cùng khách hàng trong một file, cần xác định quy tắc chọn bản ghi thắng trước khi merge, ví dụ phiên bản nguồn mới nhất và một tie-breaker ổn định.

Staging giúp kiểm tra kiểu dữ liệu và giá trị bắt buộc, phát hiện duplicate, đếm số hàng hợp lệ và bị từ chối, tính checksum, và chạy lại bước merge mà không cần đọc lại nguồn bên ngoài.

Không dùng bảng staging làm nguồn dữ liệu lâu dài cho ứng dụng nghiệp vụ. Chỉ merge sau khi batch vượt qua bước kiểm tra.

## 6. Nạp file bằng LOAD DATA

MySQL hỗ trợ LOAD DATA để nạp file văn bản phân tách cột. Đây thường là lựa chọn hiệu quả hơn nhiều câu INSERT đơn lẻ khi import CSV lớn.

~~~sql
LOAD DATA LOCAL INFILE '/client/import/customers.csv'
INTO TABLE customer_stage
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(external_id, email, full_name, source_version)
SET batch_id = 'customers-2026-11-v1';
~~~

Đường dẫn trong LOAD DATA LOCAL INFILE được đọc từ máy client đang kết nối. Với LOAD DATA INFILE không có LOCAL, file được đọc từ máy chủ MySQL và chịu ảnh hưởng của cấu hình secure_file_priv cùng quyền FILE. LOCAL phải được cho phép ở cả client và server theo cấu hình triển khai.

Trước khi chạy, xác nhận file đến từ nguồn tin cậy và đúng batch; encoding, dấu phân cách, dấu quote và line ending khớp file thực tế; có xử lý NULL, chuỗi rỗng và ký tự xuống dòng trong trường được quote; staging có constraint để phát hiện dữ liệu trùng hoặc thiếu; kết quả LOAD DATA và warnings được kiểm tra trước khi merge.

Ví dụ dùng line ending LF. Nếu file được tạo trên Windows và dùng CRLF, hãy khai báo LINES TERMINATED BY '\r\n'. Chỉ bật LOCAL INFILE cho client/server và nguồn tin cậy theo chính sách triển khai; không bật rộng nếu ứng dụng không cần chức năng này.

Nếu nạp lại cùng batch vào staging có khóa chính (batch_id, external_id), các khóa đã tồn tại sẽ xung đột. Có thể xóa dữ liệu staging của đúng batch rồi nạp lại từ file đã xác minh, hoặc thiết kế raw staging với source_row_id ổn định để nhận diện từng dòng. Không thêm IGNORE một cách máy móc vì nó có thể bỏ qua cả lỗi dữ liệu ngoài dự kiến.

Với staging chuyên dùng cho import, có thể xóa riêng batch chưa merge trước khi nạp lại:

~~~sql
DELETE FROM customer_stage
WHERE batch_id = 'customers-2026-11-v1';
~~~

Chỉ xóa dữ liệu staging của batch đang ở trạng thái LOADING hoặc FAILED sau khi xác minh file nguồn. Không xóa staging của batch đang được worker khác xử lý và không xóa dữ liệu bảng đích để chuẩn bị retry.

## 7. Kiểm tra và chuẩn hóa staging trước khi merge

Đếm số dòng trong batch:

~~~sql
SELECT COUNT(*) AS staged_rows
FROM customer_stage
WHERE batch_id = 'customers-2026-11-v1';
~~~

Kiểm tra giá trị thiếu hoặc không hợp lệ:

~~~sql
SELECT external_id, full_name
FROM customer_stage
WHERE batch_id = 'customers-2026-11-v1'
  AND (
      external_id = ''
      OR full_name = ''
  );
~~~

Kiểm tra khoảng phiên bản nguồn:

~~~sql
SELECT
    MIN(source_version) AS min_version,
    MAX(source_version) AS max_version
FROM customer_stage
WHERE batch_id = 'customers-2026-11-v1';
~~~

Nếu nguồn có thể gửi trùng business key, hãy quyết định quy tắc deduplicate. Ví dụ chọn phiên bản mới nhất, sau đó dùng source_row_id làm tie-breaker:

~~~sql
WITH ranked_source AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY external_id
            ORDER BY source_version DESC, source_row_id DESC
        ) AS rn
    FROM customer_stage_raw AS s
    WHERE batch_id = 'customers-2026-11-v1'
)
SELECT external_id, email, full_name, source_version
FROM ranked_source
WHERE rn = 1;
~~~

Đoạn ví dụ này dùng raw staging có cột source_row_id duy nhất và ổn định. Không chọn dòng tùy ý bằng ANY_VALUE hoặc dựa vào thứ tự vật lý của file; quy tắc dedup phải xác định rõ bản ghi nào thắng.

Chỉ chuyển batch sang READY sau khi toàn bộ file đã nạp và validation hoàn tất:

~~~sql
UPDATE import_batches
SET
    status = 'READY',
    staged_rows = (
        SELECT COUNT(*)
        FROM customer_stage
        WHERE batch_id = 'customers-2026-11-v1'
    )
WHERE batch_id = 'customers-2026-11-v1'
  AND status = 'LOADING'
  AND (
      expected_rows IS NULL
      OR expected_rows = (
          SELECT COUNT(*)
          FROM customer_stage
          WHERE batch_id = 'customers-2026-11-v1'
      )
  );
~~~

Ứng dụng cần xác nhận đúng một hàng đã chuyển sang READY và staged_rows khớp expected_rows nếu nguồn có khai báo số dòng. Nếu validation thất bại, giữ batch ở trạng thái LOADING hoặc đánh dấu FAILED theo quy trình; không merge một phần dữ liệu chưa được xác minh.

## 8. Upsert với INSERT ... ON DUPLICATE KEY UPDATE

Upsert kết hợp insert và update: nếu khóa chính hoặc unique key chưa tồn tại, MySQL thêm hàng; nếu bị trùng khóa, MySQL thực hiện nhánh update.

~~~sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE=InnoDB;

INSERT INTO inventory (product_id, quantity, source_version)
VALUES
    (101, 20, 5),
    (102, 10, 7) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = IF(
        incoming.source_version > inventory.source_version,
        incoming.quantity,
        inventory.quantity
    ),
    source_version = GREATEST(
        inventory.source_version,
        incoming.source_version
    );
~~~

Trong MySQL 8.0.19 trở lên, row alias sau danh sách VALUES cho phép tham chiếu các giá trị đang được nạp bằng tên incoming. Cách này tránh dùng hàm VALUES(column), vốn đã deprecated từ MySQL 8.0.20. Với phiên bản cũ hơn, cú pháp VALUES(column) có thể vẫn cần thiết; hãy kiểm tra phiên bản server trước khi chọn cú pháp.

Ví dụ có quy tắc phiên bản:

- Nếu product_id chưa có, tạo hàng với quantity và source_version từ nguồn.
- Nếu hàng đã có và source_version mới lớn hơn, áp dụng trạng thái mới.
- Nếu batch cũ được gửi lại, source_version không lớn hơn nên không ghi đè dữ liệu mới.
- Chạy lại cùng phiên bản và cùng payload không cộng quantity lần nữa.

Upsert chỉ an toàn khi business key và quy tắc update được thiết kế đúng. Nếu một hàng có thể xung đột với nhiều unique index khác nhau, cần xem xét kỹ vì MySQL xử lý nhánh duplicate dựa trên khóa bị vi phạm; thiết kế nhiều unique key có thể khiến hàng được cập nhật không như ý định nghiệp vụ.

## 9. Tránh các phép cập nhật không idempotent

Không dùng phép cộng dồn nếu cùng một batch có thể chạy lại:

~~~sql
-- Không an toàn khi retry cùng batch
INSERT INTO inventory (product_id, quantity, source_version)
VALUES (101, 20, 5) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = inventory.quantity + incoming.quantity;
~~~

Nếu chạy hai lần, quantity tăng thêm 40 thay vì 20. Nếu dữ liệu nguồn là snapshot, hãy gán giá trị tuyệt đối có kiểm soát phiên bản. Nếu nguồn là delta, phải lưu transaction/event ID đã áp dụng để không áp dụng cùng delta hai lần.

Với dữ liệu dạng event, có thể tạo bảng inbox/processed_events:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id)
) ENGINE=InnoDB;
~~~

Trong cùng transaction:

1. Chèn event_id vào processed_events.
2. Nếu insert thành công, áp dụng delta vào bảng nghiệp vụ.
3. Nếu event_id đã tồn tại, bỏ qua event đã xử lý.
4. Commit cả dấu đã xử lý và thay đổi nghiệp vụ cùng nhau.

Nếu bước áp dụng delta thất bại, rollback sẽ xóa cả dấu event và thay đổi chưa hoàn tất. Khi retry, event có thể được xử lý lại một cách an toàn.

## 10. Merge staging vào bảng đích trong một transaction

Giả sử batch đã được nạp vào customer_stage, dữ liệu đã được kiểm tra và import_batches có trạng thái READY. Có thể cập nhật hàng đã tồn tại rồi chèn hàng mới trong cùng transaction:

~~~sql
START TRANSACTION;

-- Khóa batch để chỉ một worker merge batch này tại một thời điểm.
SELECT status
FROM import_batches
WHERE batch_id = 'customers-2026-11-v1'
FOR UPDATE;

-- Cập nhật khách hàng đã tồn tại, chỉ nhận phiên bản nguồn mới hơn.
UPDATE customers AS c
JOIN customer_stage AS s
  ON s.external_id = c.external_id
SET
    c.email = s.email,
    c.full_name = s.full_name,
    c.source_version = s.source_version,
    c.updated_at = CURRENT_TIMESTAMP(6)
WHERE s.batch_id = 'customers-2026-11-v1'
  AND s.source_version > c.source_version;

-- Chèn khách hàng chưa tồn tại.
INSERT INTO customers (
    external_id,
    email,
    full_name,
    source_version
)
SELECT
    s.external_id,
    s.email,
    s.full_name,
    s.source_version
FROM customer_stage AS s
LEFT JOIN customers AS c
  ON c.external_id = s.external_id
WHERE s.batch_id = 'customers-2026-11-v1'
  AND c.customer_id IS NULL;

-- Đánh dấu hoàn tất trong cùng transaction với thay đổi bảng đích.
UPDATE import_batches
SET
    status = 'COMPLETED',
    processed_rows = (
        SELECT COUNT(*)
        FROM customer_stage
        WHERE batch_id = 'customers-2026-11-v1'
    ),
    completed_at = CURRENT_TIMESTAMP(6)
WHERE batch_id = 'customers-2026-11-v1'
  AND status = 'READY';

COMMIT;
~~~

Ứng dụng phải kiểm tra hàng ledger tồn tại và status là READY trước khi chạy các câu merge. Nếu status là COMPLETED, kết thúc mà không merge; nếu là LOADING hoặc FAILED, dừng và xử lý lại giai đoạn staging/validation. Khóa hàng bằng FOR UPDATE giữ quyền xử lý batch trong transaction khi mọi worker đều tuân thủ cùng quy tắc claim này.

Điều kiện source_version > target.source_version ngăn batch cũ ghi đè trạng thái mới. Giả định source_version tăng đơn điệu cho từng external_id và payload của một version là bất biến. Nếu cùng version nhưng payload khác, cần báo xung đột thay vì tự chọn.

Khi retry tuần tự sau một commit thành công, các hàng đã merge có source_version bằng phiên bản nguồn nên không bị update lại; các hàng đã insert đã tồn tại nên không được insert thêm; ledger đã COMPLETED nên worker cần kiểm tra và bỏ qua batch.

Trong hệ thống có nhiều worker, cần bảo đảm chỉ một worker merge cùng batch tại một thời điểm hoặc dùng cơ chế claim/lock batch. Unique key trên customers vẫn là lớp bảo vệ cuối cùng. Nếu hai batch khác nhau đồng thời insert cùng external_id, một transaction có thể gặp duplicate-key; hãy rollback và retry theo quy tắc phiên bản thay vì bỏ qua lỗi.

Nếu transaction merge thất bại trước COMMIT, InnoDB rollback thay đổi customers và trạng thái ledger cùng nhau. Nếu client mất kết nối ngay sau COMMIT nhưng trước khi nhận phản hồi, lần retry đọc ledger sẽ thấy COMPLETED và không áp dụng lại batch.

Trong ví dụ, processed_rows được tính bằng số hàng staging đã được xử lý trong batch, không phải số hàng mới insert. Nếu cần thống kê riêng số insert, update, unchanged hoặc rejected, hãy ghi các bộ đếm riêng và xác định rõ thời điểm chúng được cập nhật.

## 11. Ghi nhận batch và chunk để retry có kiểm soát

Với batch rất lớn, một transaction duy nhất có thể giữ lock lâu, tạo nhiều undo log và ảnh hưởng workload khác. Có thể chia thành chunk nhỏ, nhưng mỗi chunk cần có định danh ổn định và trạng thái riêng.

~~~sql
CREATE TABLE import_chunks (
    batch_id VARCHAR(100) NOT NULL,
    chunk_no INT UNSIGNED NOT NULL,
    first_source_row BIGINT UNSIGNED NOT NULL,
    last_source_row BIGINT UNSIGNED NOT NULL,
    status ENUM('READY', 'COMPLETED') NOT NULL,
    processed_rows BIGINT UNSIGNED NULL,
    completed_at TIMESTAMP(6) NULL,
    PRIMARY KEY (batch_id, chunk_no)
) ENGINE=InnoDB;
~~~

Mỗi chunk cần có khoảng source row hoặc khóa phân trang xác định, được merge trong transaction riêng, cập nhật dữ liệu đích và trạng thái chunk COMPLETED trong cùng transaction, có thể chạy lại nếu trạng thái chưa COMPLETED, và không thay đổi phạm vi chunk khi retry.

Không commit dữ liệu đích rồi mới ghi trạng thái chunk ở transaction khác. Nếu tiến trình chết giữa hai bước, hệ thống không biết chunk đã được áp dụng hay chưa. Dữ liệu và dấu hoàn tất phải được commit cùng nhau.

Chunking không tự làm cho phép cộng dồn trở nên idempotent. Mỗi hàng vẫn phải có business key/event ID hoặc source version để nhận diện tác động đã áp dụng.

## 12. Vì sao REPLACE và INSERT IGNORE không phải giải pháp mặc định?

### REPLACE INTO

REPLACE có vẻ giống upsert nhưng ngữ nghĩa là thay hàng xung đột bằng cách xóa hàng cũ rồi chèn hàng mới. Điều này có thể:

- Kích hoạt hành vi DELETE/INSERT thay vì UPDATE.
- Ảnh hưởng đến khóa ngoại và hành động ON DELETE.
- Kích hoạt trigger tương ứng.
- Làm thay đổi giá trị cột không được cung cấp nếu dùng default.
- Tạo giá trị AUTO_INCREMENT mới hoặc khoảng trống trong dãy ID.

Không dùng REPLACE chỉ vì muốn cập nhật hàng đã tồn tại. Nếu cần cập nhật có kiểm soát, dùng UPDATE hoặc INSERT ... ON DUPLICATE KEY UPDATE.

### INSERT IGNORE

INSERT IGNORE có thể bỏ qua duplicate key, nhưng nó còn có thể hạ nhiều lỗi dữ liệu thành warning và điều chỉnh giá trị không hợp lệ tùy trường hợp. Một hàng có thể bị bỏ qua do duplicate, truncation hoặc lỗi chuyển đổi mà quy trình không nhận biết nếu không kiểm tra warnings.

Nếu yêu cầu là “trùng khóa thì cập nhật theo version, còn dữ liệu sai thì từ chối”, hãy dùng constraint, validation và upsert có quy tắc. Không dùng IGNORE như một cách che mọi lỗi.

## 13. Không cập nhật timestamp hoặc side effect không cần thiết khi retry

Một batch có thể không thay đổi giá trị nghiệp vụ nhưng câu UPDATE vẫn chạy. Nếu luôn đặt updated_at = CURRENT_TIMESTAMP(6), mỗi lần retry sẽ thay timestamp và khiến bản ghi có vẻ vừa thay đổi dù dữ liệu thực tế giống nhau.

Có thể chỉ update khi giá trị thực sự khác:

~~~sql
-- Bước 1: cập nhật timestamp khi nội dung thực sự khác.
UPDATE customers AS c
JOIN customer_stage AS s
  ON s.external_id = c.external_id
SET c.updated_at = CURRENT_TIMESTAMP(6)
WHERE s.batch_id = 'customers-2026-11-v1'
  AND s.source_version > c.source_version
  AND (
      NOT (c.email <=> s.email)
      OR NOT (c.full_name <=> s.full_name)
  );

-- Bước 2: áp dụng nội dung và ghi nhận source version mới.
UPDATE customers AS c
JOIN customer_stage AS s
  ON s.external_id = c.external_id
SET
    c.email = s.email,
    c.full_name = s.full_name,
    c.source_version = s.source_version
WHERE s.batch_id = 'customers-2026-11-v1'
  AND s.source_version > c.source_version;
~~~

Toán tử <=> là phép so sánh null-safe trong MySQL: nó xem hai NULL là bằng nhau và trả TRUE/FALSE thay vì UNKNOWN. Hai câu UPDATE chạy trong cùng transaction: bước đầu chỉ đổi updated_at khi nội dung nghiệp vụ khác; bước sau vẫn cập nhật source_version khi nhận phiên bản mới hơn. Nhờ vậy, một phiên bản mới có nội dung giống phiên bản cũ vẫn chặn được batch cũ đến muộn mà không làm timestamp thay đổi giả.

Các side effect ngoài database như gửi email, gọi API hoặc phát message không nên thực hiện trực tiếp theo cách có thể lặp lại ngoài ý muốn. Dùng transactional outbox: ghi event cần phát vào bảng outbox cùng transaction nghiệp vụ, sau đó worker gửi và đánh dấu theo event ID idempotent.

## 14. Xử lý lỗi và retry

Không retry tất cả lỗi theo cùng một cách. Phân loại lỗi:

| Loại lỗi | Hành động |
|---|---|
| Mất kết nối/timeout, không rõ commit hay chưa | Đọc batch ledger bằng batch_id; nếu COMPLETED thì kết thúc, nếu READY thì retry |
| Deadlock | Rollback transaction và retry toàn bộ transaction với cùng batch/chunk key |
| Lock wait timeout | Xem xét rollback transaction, retry có giới hạn và backoff |
| Duplicate key ngoài dự kiến | Rollback, kiểm tra business key và cạnh tranh giữa worker; không tự động bỏ qua |
| Dữ liệu sai kiểu/thiếu trường | Đưa vào reject log, sửa nguồn hoặc mapping; không retry nguyên trạng vô hạn |
| Checksum khác với batch đã đăng ký | Dừng xử lý và điều tra nguồn dữ liệu |
| Lỗi quyền hoặc cấu hình | Sửa cấu hình/permission; retry sau khi nguyên nhân được khắc phục |

Retry nên có số lần tối đa, exponential backoff kèm jitter và log batch_id/chunk_no. Không giữ transaction mở trong lúc chờ backoff; rollback trước, chờ, rồi mở transaction mới.

## 15. Kiểm chứng kết quả sau merge

Không chỉ kiểm tra câu SQL trả về thành công. Hãy đối soát dữ liệu:

~~~sql
SELECT
    COUNT(*) AS staged_count,
    COUNT(DISTINCT external_id) AS distinct_external_ids
FROM customer_stage
WHERE batch_id = 'customers-2026-11-v1';

SELECT
    COUNT(*) AS target_rows_for_batch
FROM customers AS c
JOIN customer_stage AS s
  ON s.external_id = c.external_id
WHERE s.batch_id = 'customers-2026-11-v1';

SELECT batch_id, status, expected_rows, staged_rows, processed_rows, completed_at
FROM import_batches
WHERE batch_id = 'customers-2026-11-v1';
~~~

Với stage có khóa chính (batch_id, external_id), số distinct external_id trong batch phải bằng số hàng stage. Sau merge, mọi external_id hợp lệ trong stage phải tìm được một hàng đích. Nếu một phần dữ liệu bị từ chối, cần đối soát riêng số hàng accepted và rejected thay vì ép hai con số phải bằng nhau.

Có thể so sánh dữ liệu chi tiết bằng join hai chiều hoặc checksum theo partition. Khi dữ liệu lớn, chia theo khoảng khóa để đối soát mà không quét lại toàn bộ bảng nhiều lần.

## 16. Thiết kế quy trình import có thể chạy lại

Một quy trình thực tế có thể chia thành các giai đoạn:

~~~mermaid
flowchart TD
    A[Nhận file hoặc message] --> B[Tạo batch key ổn định và checksum]
    B --> C{Batch đã COMPLETED?}
    C -->|Có| D[Trả kết quả đã hoàn tất]
    C -->|Chưa| E[Nạp vào staging]
    E --> F[Validate, deduplicate và đối soát]
    F --> G{Dữ liệu hợp lệ?}
    G -->|Không| H[Reject log và đánh dấu FAILED]
    G -->|Có| I[Claim batch / chọn worker]
    I --> J[Transaction: merge dữ liệu và cập nhật ledger]
    J --> K{Commit thành công?}
    K -->|Có| L[COMPLETED]
    K -->|Không rõ do timeout| M[Đọc lại ledger bằng batch key]
    M --> C
~~~

Mỗi giai đoạn có thể chạy lại mà không làm sai trạng thái:

- Nhận file: batch key và checksum giúp nhận diện cùng một nội dung.
- Staging: có thể xóa và nạp lại riêng batch sau khi xác minh nguồn.
- Validation: có thể chạy lại vì chỉ đọc và tạo kết quả kiểm tra.
- Merge: có business key, version và transaction.
- Completion: ledger được commit cùng thay đổi dữ liệu đích.

Idempotency giúp xử lý an toàn khi message hoặc batch được giao ít nhất một lần và có thể lặp lại. Nó không tự bảo đảm exactly-once cho side effect ở hệ thống bên ngoài; các lần gửi message, email hoặc gọi API vẫn cần event ID và cơ chế nhận diện lặp ở phía nhận.

## 17. Checklist trước khi triển khai

1. Có batch key ổn định qua các lần retry.
2. Có checksum hoặc source version để phát hiện cùng batch nhưng nội dung khác.
3. Bảng đích có PRIMARY KEY/UNIQUE cho business key.
4. Staging có khóa chống trùng và quy tắc xử lý duplicate nguồn.
5. Có bước validation, reject log và đối soát row count.
6. Upsert dùng trạng thái tuyệt đối hoặc event ID; không cộng delta lặp lại.
7. Dữ liệu nguồn cũ không ghi đè phiên bản mới hơn.
8. Merge dữ liệu và cập nhật ledger nằm trong cùng transaction.
9. Chunk có phạm vi và định danh cố định; chunk state commit cùng dữ liệu.
10. Có xử lý deadlock, timeout, duplicate key và lỗi dữ liệu riêng biệt.
11. Retry có giới hạn, backoff và log batch/chunk ID.
12. Không dùng REPLACE/IGNORE để che lỗi hoặc thay thế quy tắc nghiệp vụ.
13. Các side effect ngoài database có event ID và cơ chế outbox/idempotent riêng.
14. Đã thử tình huống tiến trình chết trước commit, sau commit và mất phản hồi sau commit.

## 18. Bài tập thực hành

1. Tạo bảng customers có external_id UNIQUE và bảng import_batches có batch_id ổn định.
2. Nạp cùng một tập khách hàng hai lần; xác minh số hàng đích không tăng và dữ liệu không bị nhân đôi.
3. Dùng INSERT ... ON DUPLICATE KEY UPDATE với source_version; thử chạy lại phiên bản cũ sau phiên bản mới và xác minh dữ liệu không bị lùi.
4. Tạo customer_stage, nạp CSV bằng LOAD DATA LOCAL INFILE, kiểm tra row count và duplicate.
5. Thử đưa hai hàng cùng external_id vào một batch; quan sát constraint phát hiện xung đột và định nghĩa quy tắc deduplicate.
6. Merge staging bằng UPDATE JOIN và INSERT missing trong transaction; chạy lại cùng batch và so sánh trạng thái cuối.
7. Giả lập lỗi trước COMMIT rồi ROLLBACK; xác minh cả target và ledger chưa hoàn tất.
8. Giả lập mất phản hồi sau COMMIT; đọc ledger bằng batch_id và xác minh retry không áp dụng lại.
9. Thử hai worker cùng merge một business key; xử lý duplicate-key/deadlock bằng rollback và retry.
10. So sánh REPLACE, INSERT IGNORE và ON DUPLICATE KEY UPDATE trên bảng thử nghiệm có trigger hoặc khóa ngoại.

Bạn hoàn thành bài khi có thể thiết kế batch key và business key, nạp dữ liệu qua staging, merge trong transaction, xử lý retry sau timeout mà không nhân đôi tác động, và chứng minh trạng thái cuối bằng ledger cùng bước đối soát. Mục tiêu là làm cho việc chạy lại trở thành một thao tác vận hành bình thường, có thể kiểm soát và kiểm chứng.

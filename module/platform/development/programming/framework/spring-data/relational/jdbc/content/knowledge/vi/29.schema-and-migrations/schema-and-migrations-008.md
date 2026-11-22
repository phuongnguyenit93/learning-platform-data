# Triển khai thay đổi schema tương thích nhiều phiên bản ứng dụng

Trong một lần triển khai rolling deployment, các instance của ứng dụng không chuyển sang phiên bản mới cùng một thời điểm. Một số instance vẫn chạy phiên bản cũ trong khi instance khác đã chạy phiên bản mới; background job, message consumer và các tiến trình tích hợp cũng có thể được nâng cấp theo lịch riêng.

Nếu phiên bản mới yêu cầu một schema khác ngay lập tức, các instance cũ có thể lỗi khi tiếp tục đọc hoặc ghi database. Ngược lại, nếu migration xóa hoặc đổi tên cột quá sớm, phiên bản cũ đang chạy có thể không còn hoạt động.

Cách tiếp cận phổ biến là **expand-migrate-contract** (còn gọi là expand-and-contract):

1. **Expand:** mở rộng schema theo cách phiên bản cũ vẫn dùng được.
2. **Migrate:** triển khai code tương thích, chuyển dữ liệu và xác nhận dữ liệu mới.
3. **Contract:** chỉ loại bỏ cấu trúc cũ sau khi mọi ứng dụng và tiến trình liên quan đã ngừng sử dụng nó.

Mục tiêu là duy trì khả năng tương thích trong suốt thời gian nhiều phiên bản cùng tồn tại. Bài học này trình bày cách lập kế hoạch, ví dụ đổi tên/tách cột, dual-write, backfill theo batch, ràng buộc database, rollout, rollback và kiểm thử tương thích.

## 1. Vì sao nhiều phiên bản ứng dụng cùng truy cập một schema?

Một hệ thống production thường không dừng toàn bộ lưu lượng để triển khai. Khi dùng rolling deployment, orchestrator thay từng instance:

~~~text
Thời điểm T1
    App instance A: version 1
    App instance B: version 1
    App instance C: version 1

Thời điểm T2
    App instance A: version 2
    App instance B: version 1
    App instance C: version 1

Thời điểm T3
    App instance A: version 2
    App instance B: version 2
    App instance C: version 1

Thời điểm T4
    App instance A: version 2
    App instance B: version 2
    App instance C: version 2
~~~

Trong các thời điểm T2 và T3, cả hai phiên bản cùng truy cập một database schema.

Ngoài web instance, còn có thể tồn tại:

- Worker xử lý message.
- Scheduled job và batch import.
- Consumer đọc change data capture (CDC).
- Service khác dùng chung database.
- Script vận hành hoặc báo cáo.
- Phiên bản ứng dụng cũ đang chạy ở một region khác.

Vì vậy, “đã deploy xong phiên bản mới” cần được hiểu theo toàn bộ hệ thống, không chỉ số lượng web instance.

### 1.1. Schema compatibility là gì?

Một schema tương thích với nhiều phiên bản khi các phiên bản đó có thể tiếp tục thực hiện những thao tác mà chúng cần trong giai đoạn rollout.

Ví dụ:

- Phiên bản cũ chỉ biết cột `customer_name`.
- Phiên bản mới cần cột `display_name`.
- Trong giai đoạn chuyển tiếp, cả hai cột cùng tồn tại.
- Code trung gian duy trì dữ liệu nhất quán để cả hai phiên bản đều dùng được.

Không có một schema “tương thích ngược” tuyệt đối cho mọi thay đổi. Cần xác định rõ tập phiên bản và luồng ghi/đọc nào phải hoạt động trong thời gian chuyển tiếp.

### 1.2. Compatibility matrix

Trước khi triển khai, lập bảng cho từng cặp phiên bản và schema:

| Schema | App cũ V1 | App chuyển tiếp V2 | App mới V3 |
|---|---|---|---|
| S1: chỉ có cột cũ | Hoạt động | Không hoạt động nếu V2 cần cột mới | Không hoạt động |
| S2: có cả cột cũ và mới | Hoạt động | Hoạt động | Hoạt động |
| S3: chỉ còn cột mới | Không hoạt động | Có thể không hoạt động | Hoạt động |

S2 là schema trung gian cần có trong rolling deployment. S3 chỉ được triển khai sau khi V1 và V2 đã ngừng truy cập cột cũ, bao gồm job và consumer.

## 2. Expand-migrate-contract

Ba giai đoạn này tách thay đổi cấu trúc, chuyển đổi dữ liệu và xóa cấu trúc cũ.

~~~text
Schema cũ + App V1
        |
        v
1. EXPAND
   Thêm cấu trúc mới, giữ cấu trúc cũ
        |
        v
Schema mở rộng + App V1 vẫn chạy được
        |
        v
2. MIGRATE
   Deploy code tương thích
   Dual-write / backfill / validate
        |
        v
Schema mở rộng + dữ liệu mới đã sẵn sàng
        |
        v
3. CONTRACT
   Ngừng dùng cấu trúc cũ
   Gỡ code cũ, rồi mới xóa cấu trúc cũ
        |
        v
Schema mới + App phiên bản mới
~~~

### 2.1. Expand

Chỉ thêm cấu trúc mà code cũ có thể bỏ qua:

- Thêm cột nullable.
- Thêm bảng mới.
- Thêm index theo cách phù hợp với database.
- Thêm constraint theo cách có thể validate riêng.
- Thêm cột mới nhưng vẫn giữ cột cũ.
- Thêm view hoặc cấu trúc hỗ trợ chuyển tiếp.

Tránh rename hoặc drop cột ngay trong giai đoạn này. App cũ có thể vẫn cần tên cột và bảng hiện tại.

### 2.2. Migrate

Đưa code mới vào hệ thống nhưng vẫn hỗ trợ schema chuyển tiếp. Tùy use case, giai đoạn này có thể gồm:

- Ghi cả cột cũ và cột mới.
- Đọc cột cũ làm nguồn chính, hoặc đọc cột mới với fallback có kiểm soát.
- Backfill dữ liệu cũ sang cấu trúc mới.
- Đối chiếu số lượng và giá trị.
- Bật tính năng mới bằng feature flag sau khi dữ liệu sẵn sàng.
- Chờ toàn bộ instance, job và consumer cũ được thay thế.

### 2.3. Contract

Chỉ thực hiện khi không còn code nào cần cấu trúc cũ:

- Ngừng ghi cột cũ.
- Ngừng đọc cột cũ.
- Gỡ code tương thích và fallback.
- Xác nhận không còn query, report, job hoặc consumer dùng cấu trúc cũ.
- Xóa cột/bảng/index cũ trong migration riêng.

Contract thường được triển khai ở một release sau. Tách riêng giúp có thời gian quan sát và giữ khả năng rollback ứng dụng trong giai đoạn chuyển tiếp.

## 3. Ví dụ: đổi tên cột customer_name thành display_name

Giả sử bảng hiện tại:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);
~~~

App V1 đọc và ghi `customer_name`:

~~~java
String name = jdbcClient
        .sql("""
            SELECT customer_name
            FROM customers
            WHERE id = :id
            """)
        .param("id", customerId)
        .query(String.class)
        .single();
~~~

Phiên bản mới muốn dùng tên cột `display_name`. Một migration chỉ rename cột:

~~~sql
ALTER TABLE customers
RENAME COLUMN customer_name TO display_name;
~~~

sẽ làm App V1 lỗi ngay khi nó tiếp tục truy vấn `customer_name`.

### 3.1. Bước Expand: thêm cột mới

Tạo migration đầu tiên:

~~~sql
ALTER TABLE customers
    ADD COLUMN display_name VARCHAR(200);
~~~

Sau migration, schema có cả hai cột:

~~~text
customers
+----+---------------+--------------+
| id | customer_name | display_name |
+----+---------------+--------------+
| 10 | An Nguyen     | NULL         |
+----+---------------+--------------+
~~~

App V1 vẫn đọc/ghi `customer_name`. Cột mới chưa bắt buộc có dữ liệu nên V1 không bị ảnh hưởng.

### 3.2. Bước Migrate: triển khai phiên bản cầu nối

App V2 có thể ghi cả hai cột trong cùng một câu lệnh:

~~~sql
UPDATE customers
SET customer_name = :name,
    display_name = :name
WHERE id = :id;
~~~

Hoặc khi insert:

~~~sql
INSERT INTO customers (
    id,
    customer_name,
    display_name
)
VALUES (
    :id,
    :name,
    :name
);
~~~

Trong giai đoạn V1 và V2 cùng chạy, V1 chỉ ghi cột cũ. Vì vậy V2 chưa thể coi `display_name` là nguồn dữ liệu duy nhất.

Một trình tự an toàn:

1. Expand schema, giữ cột cũ.
2. Deploy V2 bridge; V2 vẫn đọc `customer_name`, nhưng ghi cả hai cột.
3. Chờ tất cả V1 web instance, worker, job và consumer ngừng chạy.
4. Backfill những hàng mà `display_name` còn NULL.
5. Đối chiếu dữ liệu và xác nhận không còn hàng thiếu.
6. Deploy V3 đọc `display_name`, nhưng vẫn ghi cả hai cột trong thời gian rollback window.
7. Chờ mọi V2 bridge instance đã ngừng hoạt động.
8. Deploy V4 chỉ ghi/đọc `display_name`.
9. Sau khi hết thời gian rollback và xác nhận không còn consumer dùng cột cũ, drop `customer_name` trong một release riêng.

Lý do phải chờ V1 ngừng ghi trước khi backfill: nếu backfill copy dữ liệu cũ sang cột mới trong lúc V1 vẫn cập nhật `customer_name`, cột `display_name` có thể lại trở nên lỗi thời ngay sau khi backfill đi qua hàng đó.

### 3.3. Bước Contract: xóa cột cũ

Sau khi tất cả code đã chuyển sang `display_name`, có thể tạo migration contract:

~~~sql
ALTER TABLE customers
    DROP COLUMN customer_name;
~~~

Không gộp migration drop này vào cùng release đầu tiên thêm `display_name`. Khi deploy theo từng instance, code cũ vẫn có thể chạy sau khi migration được áp dụng.

## 4. Ví dụ: tách full_name thành first_name và last_name

Thay đổi cấu trúc dữ liệu phức tạp hơn đổi tên cột. Schema cũ:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);
~~~

Schema mới cần `first_name` và `last_name`.

Không nên xóa `full_name` và thêm hai cột mới trong một migration duy nhất nếu App V1 còn hoạt động.

### 4.1. Expand schema

~~~sql
ALTER TABLE customers
    ADD COLUMN first_name VARCHAR(100),
    ADD COLUMN last_name VARCHAR(100);
~~~

App V1 vẫn đọc/ghi `full_name`.

### 4.2. Xác định quy tắc chuyển đổi dữ liệu

Tách tên không phải lúc nào cũng là phép cắt chuỗi đơn giản. Ví dụ:

- Nguyen Van An
- Mary Jane Watson
- Jean-Claude Van Damme
- Tên chỉ có một từ.
- Tên có khoảng trắng ở đầu/cuối.
- Tên chứa ký tự Unicode hoặc quy tắc đặt tên khác nhau theo quốc gia.

Trước khi backfill, nghiệp vụ phải định nghĩa `first_name` và `last_name` có nghĩa gì. Nếu không thể tách chính xác, cần giữ nguyên `full_name` hoặc lưu thêm trường display name để tránh mất thông tin.

### 4.3. App bridge ghi cả ba trường

~~~java
jdbcClient.sql("""
        UPDATE customers
        SET full_name = :fullName,
            first_name = :firstName,
            last_name = :lastName
        WHERE id = :id
        """)
    .param("fullName", fullName)
    .param("firstName", firstName)
    .param("lastName", lastName)
    .param("id", customerId)
    .update();
~~~

Trong giai đoạn chuyển tiếp, V2 có thể tiếp tục đọc `full_name` để không phụ thuộc dữ liệu mới chưa được backfill. Sau khi V1 đã ngừng ghi, dữ liệu có thể được chuyển đổi sang hai cột mới.

### 4.4. Backfill và kiểm tra

Sau khi V1 không còn ghi `full_name`:

~~~sql
UPDATE customers
SET first_name = :derived_first_name,
    last_name = :derived_last_name
WHERE id = :id
  AND first_name IS NULL
  AND last_name IS NULL;
~~~

Điều kiện NULL giúp tiến trình có thể chạy lại mà không ghi đè các giá trị mới đã được ứng dụng ghi.

Sau backfill, cần xác định các hàng không thể chuyển đổi và xử lý theo quy tắc nghiệp vụ. Không đặt NOT NULL trước khi mọi hàng hợp lệ có dữ liệu.

## 5. Dual-write và dual-read

Dual-write là ghi cùng một thay đổi vào cả cấu trúc cũ và mới. Dual-read là đọc từ cấu trúc mới, có thể fallback về cấu trúc cũ trong giai đoạn chuyển tiếp.

Đây là kỹ thuật hữu ích, nhưng phải xác định rõ nguồn dữ liệu có thẩm quyền tại từng giai đoạn.

### 5.1. Dual-write

Ví dụ:

~~~sql
UPDATE customers
SET customer_name = :name,
    display_name = :name
WHERE id = :id;
~~~

Hai cột được ghi trong cùng statement nên cùng commit hoặc rollback. Nếu ghi bằng hai statement riêng, chúng phải nằm trong cùng transaction và cần xử lý trường hợp statement thứ hai thất bại.

Dual-write có một số rủi ro:

- Một code path chỉ ghi cột cũ.
- Một batch job quên cập nhật cột mới.
- Hai giá trị được tính bằng hai quy tắc khác nhau.
- Retry không idempotent tạo ra dữ liệu sai.
- Hai phiên bản ứng dụng cùng ghi nhưng không thống nhất nguồn dữ liệu chính.

Hãy đặt logic dual-write ở một adapter hoặc service có trách nhiệm rõ ràng, và kiểm thử mọi đường ghi.

### 5.2. Dual-read với fallback

Ví dụ đọc:

~~~sql
SELECT COALESCE(display_name, customer_name) AS effective_name
FROM customers
WHERE id = :id;
~~~

Fallback giúp code mới vẫn đọc được hàng chưa backfill.

Nhưng `COALESCE` không tự giải quyết xung đột nếu cả hai cột đều có giá trị khác nhau. Cần xác định cột nào là nguồn chính trong giai đoạn hiện tại.

Không duy trì fallback vĩnh viễn. Khi dữ liệu mới đã được xác thực và mọi writer đã chuyển đổi, gỡ fallback để tránh che giấu dữ liệu thiếu hoặc không nhất quán.

### 5.3. Ma trận nguồn dữ liệu

| Giai đoạn | Nguồn đọc chính | Writer cần làm gì? |
|---|---|---|
| Trước expand | Cột cũ | Chỉ ghi cột cũ |
| Sau expand, còn V1 | Cột cũ | V2 ghi cả hai; V1 chỉ ghi cũ |
| Sau khi V1 đã drain, backfill | Cột cũ hoặc fallback | V2 tiếp tục dual-write |
| Sau backfill, chuyển read | Cột mới | V3 đọc mới và tiếp tục dual-write |
| Sau rollback window | Cột mới | V4 chỉ ghi mới |
| Sau contract | Cột mới | Không còn tham chiếu cột cũ |

Điểm quan trọng là không chuyển nguồn đọc sang cột mới trước khi các writer cũ đã ngừng cập nhật nguồn cũ hoặc có cơ chế đồng bộ tương đương.

## 6. Backfill dữ liệu lớn theo batch

Một câu UPDATE duy nhất có thể phù hợp với bảng nhỏ, nhưng với bảng lớn có thể tạo transaction dài, lock kéo dài, WAL lớn và ảnh hưởng tải database.

Nên chia backfill thành batch có giới hạn.

Ví dụ PostgreSQL dùng ID tăng dần:

~~~sql
UPDATE customers
SET display_name = customer_name
WHERE id > :fromId
  AND id <= :toId
  AND display_name IS NULL;
~~~

Worker có thể xử lý từng khoảng ID, commit sau mỗi batch.

~~~text
Batch 1: id 1       -> 10,000
Batch 2: id 10,001  -> 20,000
Batch 3: id 20,001  -> 30,000
...
~~~

### 6.1. Tính idempotent

Backfill nên có thể chạy lại an toàn. Ví dụ:

~~~sql
UPDATE customers
SET display_name = customer_name
WHERE display_name IS NULL;
~~~

Nếu job bị dừng giữa chừng, lần chạy tiếp theo chỉ xử lý hàng chưa có giá trị mới.

Tuy nhiên, `IS NULL` chỉ phù hợp nếu NULL thực sự có nghĩa “chưa được migrate”. Nếu NULL là một giá trị nghiệp vụ hợp lệ, cần một cột trạng thái migration hoặc điều kiện khác để phân biệt.

### 6.2. Không ghi đè dữ liệu mới

Nếu ứng dụng mới đã ghi `display_name`, backfill không nên ghi đè nó bằng giá trị cũ. Điều kiện:

~~~sql
AND display_name IS NULL
~~~

giúp tránh ghi đè những giá trị mới đã được điền.

Nếu source column vẫn có thể thay đổi trong thời gian backfill, phải có chiến lược đồng bộ. Có thể:

- Chờ old writer drain rồi mới backfill.
- Dùng trigger tạm thời đồng bộ old-to-new.
- Dùng change log/CDC để áp dụng các thay đổi phát sinh trong khi backfill.
- Ghi nhận watermark và chạy vòng đối chiếu cuối.

Không chọn trigger chỉ vì tiện. Trigger làm tăng logic ẩn ở database và phải được quản lý, kiểm thử, gỡ bỏ sau giai đoạn chuyển tiếp.

### 6.3. Điều khiển batch

Một backfill vận hành tốt thường cần:

- Batch size có thể cấu hình.
- Keyset/range pagination theo khóa ổn định.
- Commit theo batch.
- Retry cho batch lỗi.
- Giới hạn tốc độ để không gây quá tải database.
- Log tiến độ và checkpoint.
- Số lượng hàng đọc, cập nhật, bỏ qua và lỗi.
- Khả năng dừng/resume.
- Không dùng OFFSET lớn cho bảng thay đổi liên tục nếu có thể dùng keyset.

Không chạy backfill hàng triệu hàng trong migration startup của mọi app instance. Tách nó thành job có thể theo dõi và điều khiển.

## 7. Thêm NOT NULL và constraint mà không làm gián đoạn

Một thay đổi thường gặp là cột mới ban đầu nullable, sau đó cần trở thành NOT NULL.

Không nên áp dụng `NOT NULL` trước khi dữ liệu cũ được backfill. Trình tự:

1. Add column nullable.
2. Deploy code ghi giá trị mới.
3. Backfill dữ liệu cũ.
4. Kiểm tra không còn NULL.
5. Thêm/validate constraint.
6. Sau khi dữ liệu và writer đã ổn định, enforce NOT NULL.

Ví dụ kiểm tra:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE display_name IS NULL;
~~~

Nếu kết quả bằng 0, có thể tiến hành bước enforce constraint theo cú pháp và chiến lược phù hợp với database.

### 7.1. PostgreSQL: validate constraint riêng

Với PostgreSQL, có thể thêm CHECK constraint dưới dạng `NOT VALID`, sau đó validate riêng:

~~~sql
ALTER TABLE customers
    ADD CONSTRAINT customers_display_name_present
    CHECK (display_name IS NOT NULL) NOT VALID;
~~~

Sau đó:

~~~sql
ALTER TABLE customers
    VALIDATE CONSTRAINT customers_display_name_present;
~~~

Khi dữ liệu đã được xác nhận và phiên bản PostgreSQL phù hợp, có thể hoàn tất việc đặt NOT NULL:

~~~sql
ALTER TABLE customers
    ALTER COLUMN display_name SET NOT NULL;
~~~

Chiến lược cụ thể cần xét phiên bản PostgreSQL, lock mode và thời gian chạy DDL. Các câu lệnh trên là ví dụ PostgreSQL, không phải cú pháp portable cho mọi database.

### 7.2. Thêm foreign key

Với bảng lớn, validate FK có thể tốn thời gian. PostgreSQL hỗ trợ:

~~~sql
ALTER TABLE order_lines
    ADD CONSTRAINT fk_order_lines_customer
    FOREIGN KEY (customer_id)
    REFERENCES customers(id)
    NOT VALID;
~~~

Sau đó:

~~~sql
ALTER TABLE order_lines
    VALIDATE CONSTRAINT fk_order_lines_customer;
~~~

Điều này cho phép tách việc thêm constraint và kiểm tra dữ liệu hiện có. Cần hiểu lock và enforcement đối với dữ liệu mới trong từng giai đoạn theo tài liệu database.

## 8. Index và DDL có thể gây lock

Không phải mọi migration chỉ thêm một cột đều an toàn về thời gian chạy. DDL có thể:

- Chờ lock từ transaction dài.
- Chặn query hoặc write.
- Quét toàn bộ bảng.
- Tạo index với chi phí I/O lớn.
- Gây tăng WAL hoặc replication lag.
- Làm tăng thời gian startup nếu migration chạy đồng bộ khi app khởi động.

Với PostgreSQL, tạo index lớn có thể dùng:

~~~sql
CREATE INDEX CONCURRENTLY idx_customers_display_name
    ON customers(display_name);
~~~

`CREATE INDEX CONCURRENTLY` có quy tắc transaction riêng và không chạy bên trong transaction block thông thường. Cấu hình migration tool cần hỗ trợ migration không transactional cho statement này.

Cú pháp và hành vi online index khác nhau giữa PostgreSQL, MySQL, SQL Server và Oracle. Hãy đọc tài liệu của database/version đang triển khai, không suy ra từ tên câu lệnh.

### 8.1. Tránh migration startup cạnh tranh

Nếu mọi instance ứng dụng cùng tự chạy migration khi khởi động, migration tool có thể dùng lock để bảo vệ lịch sử migration, nhưng điều đó không thay thế kế hoạch triển khai.

Với production, thường dễ kiểm soát hơn khi chạy migration bằng một deployment job riêng trước hoặc giữa các bước rollout, rồi mới cho app version mới hoạt động.

Cần xác định:

- Ai chạy migration?
- Migration chạy trước hay sau khi deploy app?
- Migration có thể chạy lại không?
- Nếu migration thất bại, app cũ còn hoạt động không?
- Có lock timeout và statement timeout không?
- Có giám sát thời gian và replication lag không?

## 9. Tổ chức migration với Flyway hoặc Liquibase

Spring Boot có thể tích hợp các công cụ migration như Flyway và Liquibase. Các công cụ này giúp version hóa schema và áp dụng migration theo thứ tự.

### 9.1. Flyway

Flyway thường dùng versioned migration theo tên file:

~~~text
db/migration/
  V001__create_customers.sql
  V002__add_display_name.sql
  V003__add_customer_display_name_index.sql
  V004__remove_customer_name.sql
~~~

Một migration đã được áp dụng trong môi trường dùng chung nên được xem là bất biến. Nếu cần thay đổi, tạo migration mới thay vì sửa nội dung migration cũ đã chạy.

Tách các giai đoạn expand và contract thành migration khác nhau. Backfill lớn thường nên là một job riêng thay vì nhét vào một migration DDL chạy trong startup.

### 9.2. Liquibase

Liquibase mô tả thay đổi qua changelog và changeset. Có thể dùng precondition, rollback definition và context/label để tổ chức thay đổi theo môi trường hoặc giai đoạn.

Dù dùng công cụ nào, vẫn cần thiết kế compatibility. Migration tool chỉ quản lý thứ tự và lịch sử schema; nó không tự bảo đảm code cũ và mới có thể cùng chạy.

### 9.3. Migration là một phần của release plan

Một release có thể bao gồm nhiều bước:

| Bước release | Schema | Ứng dụng |
|---|---|---|
| R0 | Schema cũ | V1 |
| R1 | Expand: thêm cột mới | V1 |
| R2 | Schema mở rộng | V2 bridge |
| R3 | Backfill và validate | V2 bridge |
| R4 | Schema mở rộng, dữ liệu mới đầy đủ | V3 đọc cột mới, dual-write |
| R5 | Ngừng dùng cột cũ | V4 chỉ dùng cột mới |
| R6 | Contract: drop cột cũ | V4 |

Schema migration và app deployment là hai lịch sử có liên quan nhưng không nhất thiết phải nằm trong một lần phát hành duy nhất.

## 10. Rollback và roll-forward

Một migration mở rộng thường dễ tương thích với app cũ. Một migration contract có thể không đảo ngược an toàn.

Ví dụ, sau khi xóa `customer_name`, dữ liệu cũ đã không còn. Nếu cần rollback app về V1, code V1 sẽ không chạy vì cột đã bị xóa.

Do đó:

- Giữ cột cũ trong thời gian rollback window.
- Chỉ contract sau khi đã xác nhận không cần rollback về phiên bản cũ.
- Lưu backup hoặc snapshot theo chính sách recovery.
- Chuẩn bị migration roll-forward nếu phát hiện lỗi sau khi contract.
- Không giả định down migration có thể khôi phục dữ liệu đã mất.

### 10.1. Rollback ứng dụng và rollback database là hai việc khác nhau

Có thể rollback container image từ V3 về V2 trong khi giữ schema mở rộng. Điều này thường an toàn nếu schema vẫn hỗ trợ cả hai phiên bản.

Ngược lại, rollback database từ schema S3 về S2 có thể cần khôi phục cột và tái tạo dữ liệu. Nếu dữ liệu mới đã được ghi vào cấu trúc mới và không thể chuyển ngược, migration down không thể phục hồi chính xác.

Một kế hoạch tốt ưu tiên **roll-forward** cho thay đổi schema không thể đảo ngược: sửa lỗi bằng migration mới và triển khai app tương thích.

### 10.2. Không contract quá sớm

Cột cũ chỉ nên được xóa khi:

- Không còn instance app cũ.
- Không còn worker, scheduler, consumer hoặc script dùng cột cũ.
- Dashboard/report/ETL/CDC đã chuyển đổi.
- Query log hoặc telemetry không còn truy cập cột cũ trong thời gian quan sát đủ dài.
- Rollback window đã hết.
- Backfill và validation hoàn tất.
- Đã có kế hoạch khôi phục phù hợp.

## 11. Feature flag trong quá trình chuyển đổi

Feature flag giúp tách thời điểm deploy code khỏi thời điểm bật hành vi mới.

Ví dụ App V3 có thể hỗ trợ hai đường đọc:

~~~java
String name = useNewColumn
        ? customer.displayName()
        : customer.customerName();
~~~

Trong thực tế, việc chọn cột nên nằm trong repository/adapter, không rải điều kiện khắp domain model.

Một trình tự:

1. Deploy code có khả năng dùng schema mới nhưng flag đang tắt.
2. Expand schema và backfill.
3. Kiểm tra dữ liệu mới.
4. Bật flag cho một nhóm traffic hoặc một tenant.
5. Quan sát lỗi, latency và dữ liệu.
6. Mở rộng dần.
7. Sau khi ổn định, gỡ nhánh code cũ trong release sau.

Feature flag không thay thế schema compatibility. Nếu code V3 yêu cầu cột mới ngay khi khởi động, flag tắt cũng không giúp V3 chạy trên schema chưa expand.

## 12. Những thành phần ngoài web app cũng cần tương thích

Một lỗi phổ biến là chỉ kiểm tra web instance. Nhưng database có thể được truy cập bởi nhiều thành phần.

| Thành phần | Rủi ro |
|---|---|
| Scheduled job | Job cũ chạy sau khi cột bị xóa |
| Message consumer | Consumer cũ xử lý payload hoặc schema cũ |
| Batch import | Ghi dữ liệu theo cấu trúc cũ |
| Report/BI | Query hoặc view phụ thuộc cột cũ |
| CDC pipeline | Mapping downstream vẫn cần field cũ |
| Data export | Script vận hành chưa được cập nhật |
| Service khác | Dùng chung database nhưng có lịch release riêng |

Trước contract, hãy tìm mọi consumer của schema. Có thể dùng query logs, database audit, source search và inventory hệ thống để xác định những phụ thuộc không nằm trong repo ứng dụng chính.

Nếu database được chia sẻ giữa nhiều service, schema nên được quản lý như một hợp đồng giữa producer và consumer. Cần thông báo, thời gian chuyển đổi và xác nhận từ các nhóm sở hữu consumer trước khi xóa cấu trúc cũ.

## 13. Kiểm thử compatibility giữa phiên bản ứng dụng

Unit test từng phiên bản không đủ chứng minh rolling deployment an toàn. Cần kiểm tra các cặp app/schema có thể cùng tồn tại.

### 13.1. Kiểm thử ma trận

Ví dụ cho thay đổi `customer_name` sang `display_name`:

| Kiểm thử | Kết quả mong đợi |
|---|---|
| V1 trên schema S1 | Hoạt động |
| V1 trên schema S2 sau expand | Hoạt động |
| V2 bridge trên schema S2 | Hoạt động |
| V1 và V2 cùng chạy trên S2 | Cả hai đọc/ghi theo quy tắc chuyển tiếp |
| Backfill khi V1 đã drain | Không còn nguồn ghi cũ làm stale dữ liệu mới |
| V3 trên S2 sau validation | Đọc cột mới thành công |
| V2 và V3 cùng chạy trên S2 | Cả hai giữ dữ liệu cũ/mới nhất quán |
| V4 trên S2 | Hoạt động dù chỉ dùng cột mới |
| V4 trên S3 sau contract | Hoạt động |
| V1 trên S3 | Không hỗ trợ; phải bảo đảm không còn V1 trước contract |

### 13.2. Test migration từ schema thực tế

Một quy trình kiểm thử hữu ích:

1. Khởi tạo database ở schema version trước migration.
2. Nạp dữ liệu đại diện, bao gồm NULL, Unicode, chuỗi dài và giá trị biên.
3. Chạy migration expand.
4. Chạy test của app cũ trên schema mở rộng.
5. Deploy app bridge và kiểm tra dual-write.
6. Chạy backfill.
7. Đối chiếu dữ liệu.
8. Chạy app mới trên schema mở rộng.
9. Chạy contract migration trong môi trường riêng.
10. Xác nhận app mới hoạt động sau khi cột cũ biến mất.

Dùng database cùng engine và phiên bản gần production. H2 có thể không mô phỏng chính xác lock, DDL, constraint, collation hoặc type semantics của PostgreSQL/MySQL/SQL Server.

### 13.3. Test rollback

Kiểm tra khả năng quay lại phiên bản ứng dụng cũ khi schema vẫn ở giai đoạn expand. Không cần rollback database nếu schema mở rộng vẫn tương thích.

Đồng thời kiểm tra tình huống migration expand thất bại giữa chừng và app cũ tiếp tục hoạt động. Với DDL có semantics transaction khác nhau giữa database, phải biết phần nào đã được commit.

## 14. Quan sát trong thời gian rollout

Không nên chuyển sang contract chỉ vì deployment dashboard báo 100% instance mới.

Theo dõi:

- Phiên bản app đang chạy theo từng instance.
- Phiên bản worker và consumer.
- Số request/statement còn truy cập cột cũ.
- Tỷ lệ NULL ở cột mới.
- Số hàng backfill thành công, bỏ qua và lỗi.
- Chênh lệch giữa giá trị cũ và mới.
- Query latency và error rate.
- Lock wait, deadlock và replication lag.
- Thời gian migration và thời gian validate constraint.

Có thể kiểm tra dữ liệu chưa chuyển:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE display_name IS NULL;
~~~

Và kiểm tra hai cột có khác nhau không:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE display_name IS DISTINCT FROM customer_name;
~~~

`IS DISTINCT FROM` là cú pháp PostgreSQL xử lý NULL-safe comparison. Với database khác, dùng cú pháp tương đương phù hợp.

Một metric bằng 0 chưa đủ nếu dữ liệu mới có thể bị ghi sai theo một quy tắc chuyển đổi. Nên lấy mẫu và kiểm tra các trường hợp biên theo nghiệp vụ.

## 15. Các thay đổi schema có rủi ro cao

Một số thay đổi thường cần expand-contract hoặc kế hoạch riêng.

| Thay đổi | Rủi ro khi deploy trực tiếp | Cách tiếp cận |
|---|---|---|
| Rename column | App cũ không tìm thấy tên cột | Add new column, dual-write, backfill, switch reads, drop old later |
| Drop column | App cũ hoặc report vẫn truy cập | Xác nhận không còn consumer rồi contract |
| Split/merge column | Cần chuyển đổi dữ liệu và quy tắc nghiệp vụ | Add fields, bridge code, backfill, validate |
| Thay kiểu dữ liệu | Parse/format hoặc range khác nhau | Add column mới, chuyển đổi có kiểm soát |
| Thêm NOT NULL | Hàng cũ chưa có giá trị | Add nullable, backfill, validate, enforce |
| Thêm FK | Dữ liệu hiện tại có thể vi phạm | Kiểm tra và làm sạch trước, validate theo khả năng DB |
| Thêm index | Có thể lock hoặc tăng tải I/O | Dùng online/concurrent index phù hợp database |
| Đổi enum/status | App cũ không hiểu giá trị mới | Deploy reader hỗ trợ trước khi writer phát giá trị mới |
| Đổi JSON shape | Consumer cũ có thể không parse được | Version payload hoặc hỗ trợ cả hai dạng |
| Đổi precision/scale | Dữ liệu bị làm tròn hoặc overflow | Kiểm tra range và backfill trước khi contract |

### 15.1. Thêm giá trị enum mới

Giả sử database có trạng thái `DRAFT`, `CONFIRMED`, `CANCELLED`, và phiên bản mới muốn thêm `ON_HOLD`.

Nếu app cũ parse enum bằng `Enum.valueOf`, nó có thể lỗi khi đọc `ON_HOLD`.

Trình tự an toàn:

1. Deploy reader có thể hiểu trạng thái mới hoặc xử lý unknown value.
2. Chờ mọi reader cũ được thay thế.
3. Bật writer bắt đầu ghi `ON_HOLD`.
4. Xác nhận consumer, report và integration hiểu trạng thái đó.

Nếu database dùng native enum type, migration thêm giá trị cũng cần xét semantics và khả năng rollback của engine.

### 15.2. Thay đổi kiểu dữ liệu

Ví dụ chuyển `amount` từ `INTEGER` sang `NUMERIC(18,2)`. App cũ có thể vẫn đọc integer, trong khi app mới ghi decimal.

Có thể thêm cột mới, chuyển đổi dữ liệu, dual-write theo quy tắc rounding rõ ràng, xác nhận không mất precision, rồi mới gỡ cột cũ. Không ép kiểu tại chỗ nếu conversion có thể gây overflow, rounding hoặc lock không chấp nhận được.

## 16. Quy trình triển khai schema compatibility

Trước một thay đổi schema production, hãy lập kế hoạch theo các bước:

**Bước 1 — Liệt kê consumer.** Xác định mọi app, job, consumer, report và script đọc/ghi bảng hoặc cột bị thay đổi.

**Bước 2 — Lập compatibility matrix.** Xác định schema nào phải hỗ trợ app version nào trong từng giai đoạn.

**Bước 3 — Thiết kế expand migration.** Chỉ thêm cấu trúc tương thích với code hiện tại; tránh rename/drop ngay.

**Bước 4 — Deploy bridge version.** Code mới phải chạy được trên schema mở rộng và giữ hành vi tương thích trong lúc app cũ còn hoạt động.

**Bước 5 — Drain old writers.** Xác nhận mọi phiên bản chỉ ghi cấu trúc cũ đã ngừng hoạt động.

**Bước 6 — Backfill theo batch.** Có checkpoint, retry, rate limit, idempotency và log tiến độ.

**Bước 7 — Validate.** Kiểm tra NULL, số lượng, giá trị mẫu, invariant và chênh lệch dữ liệu.

**Bước 8 — Switch reads.** Chuyển dần sang cấu trúc mới, dùng feature flag nếu phù hợp; tiếp tục dual-write trong rollback window.

**Bước 9 — Drain bridge versions.** Xác nhận không còn code nào cần cột cũ.

**Bước 10 — Contract.** Xóa code tương thích và cấu trúc cũ trong release riêng.

**Bước 11 — Quan sát và lưu bằng chứng.** Giữ metric, migration history, kết quả validation và kế hoạch recovery.

~~~text
Lập danh sách consumer + version
             |
             v
       Compatibility matrix
             |
             v
        EXPAND schema
             |
             v
      Deploy bridge version
             |
             v
      Drain old writers
             |
             v
       Batch backfill
             |
             v
    Validate dữ liệu mới
             |
             v
      Switch reads/writes
             |
             v
      Drain bridge version
             |
             v
       CONTRACT schema
             |
             v
     Monitor + recovery plan
~~~

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Rename/drop ngay trong một migration | App cũ lỗi trong rolling deployment | Expand-contract |
| Backfill khi old writer vẫn hoạt động | Giá trị mới bị stale sau backfill | Drain old writer hoặc dùng cơ chế đồng bộ |
| Chuyển read sang cột mới quá sớm | App mới đọc NULL hoặc dữ liệu chưa đồng bộ | Backfill, validate rồi mới switch |
| Chỉ dual-write ở web request | Job/consumer cũ vẫn chỉ ghi cột cũ | Inventory mọi writer |
| Dual-write hai câu lệnh ngoài transaction | Một cột cập nhật, cột kia thất bại | Cùng statement hoặc transaction |
| Drop cột ngay sau khi deploy code mới | Không còn thời gian rollback app | Giữ cấu trúc cũ qua rollback window |
| Chạy backfill lớn lúc app startup | Startup lâu, nhiều instance cạnh tranh, database quá tải | Tách thành job riêng |
| Dùng OFFSET lớn cho backfill | Chậm và dễ bỏ/sai hàng khi dữ liệu thay đổi | Keyset/range theo khóa ổn định |
| Sửa migration đã chạy | Lịch sử schema giữa môi trường không còn nhất quán | Tạo migration mới |
| Chỉ test app mới trên schema mới | Bỏ sót lỗi giữa các version trong rolling deploy | Test compatibility matrix |
| Chỉ theo dõi web instances | Job/consumer cũ vẫn truy cập cấu trúc cũ | Theo dõi toàn bộ consumer |
| Tin rằng rollback migration luôn an toàn | Không khôi phục được dữ liệu đã chuyển/xóa | Giữ dữ liệu cũ, chuẩn bị roll-forward/recovery |

## 18. Bài tập tự suy luận

**Tình huống A — Rename column**

App V1 đọc `customer_name`; App V2 đọc `display_name`. Vì sao không thể rename cột ngay trước khi bắt đầu rolling deployment?

**Gợi ý:** Trong quá trình rollout, V1 vẫn chạy và truy vấn `customer_name`. Cột đó phải tồn tại cho đến khi mọi V1 consumer đã drain.

**Tình huống B — Backfill**

Job copy `customer_name` sang `display_name`, nhưng một instance V1 vẫn cập nhật `customer_name`. Điều gì có thể xảy ra?

**Gợi ý:** Backfill có thể đã đi qua hàng đó trước khi V1 cập nhật. `display_name` sẽ không phản ánh giá trị mới. Cần drain old writer hoặc đồng bộ thay đổi bằng cơ chế khác.

**Tình huống C — Dual-write**

App V2 ghi cả cột cũ và mới. Nếu hai câu UPDATE chạy ở hai transaction riêng, câu thứ hai thất bại thì sao?

**Gợi ý:** Dữ liệu hai cột có thể lệch. Ghi cùng một statement hoặc cùng transaction và xử lý rollback.

**Tình huống D — NOT NULL**

Cột mới vừa được thêm và có hàng cũ chưa được backfill. Có nên thêm NOT NULL ngay không?

**Gợi ý:** Không. Thêm nullable trước, ghi dữ liệu mới, backfill, validate rồi mới enforce constraint.

**Tình huống E — Rollback**

App V3 chỉ dùng cột mới, nhưng vẫn còn cột cũ trong database. Có thể rollback app về V2 bridge không?

**Gợi ý:** Có thể nếu V2 vẫn tương thích với schema hiện tại và dữ liệu cũ vẫn được dual-write. Đây là lý do giữ cột cũ trong rollback window.

**Tình huống F — Consumer ngoài ứng dụng**

Web instance đã chuyển sang cột mới, nhưng báo cáo BI vẫn truy vấn cột cũ mỗi đêm. Có thể drop cột cũ không?

**Gợi ý:** Chưa. Báo cáo cũng là consumer của schema; cần chuyển đổi và xác nhận trước contract.

## 19. Ghi nhớ

| Khái niệm | Vai trò |
|---|---|
| Rolling deployment | Nhiều phiên bản ứng dụng cùng tồn tại trong thời gian rollout |
| Schema compatibility | Schema hỗ trợ các version cần cùng hoạt động |
| Expand | Thêm cấu trúc mới, giữ cấu trúc cũ |
| Migrate | Bridge code, dual-write/read, backfill và validate |
| Contract | Gỡ code và schema cũ sau khi không còn consumer |
| Dual-write | Ghi đồng thời cấu trúc cũ và mới |
| Dual-read | Đọc cấu trúc mới, có thể fallback trong giai đoạn chuyển tiếp |
| Backfill | Chuyển dữ liệu hiện có sang cấu trúc mới |
| Idempotency | Cho phép chạy lại batch an toàn |
| Compatibility matrix | Xác định cặp app version/schema phải hoạt động |
| Feature flag | Điều khiển thời điểm bật hành vi mới |
| Rollback window | Khoảng thời gian giữ khả năng quay lại app version trước |
| Roll-forward | Sửa schema bằng migration mới khi không thể đảo ngược an toàn |
| Consumer inventory | Danh sách mọi thành phần đọc/ghi schema |

**Thay đổi schema tương thích nhiều phiên bản cần được triển khai theo nhiều giai đoạn.** Hãy mở rộng schema trước, đưa code cầu nối vào khi cột cũ và mới cùng tồn tại, drain writer cũ rồi backfill và xác nhận dữ liệu, chuyển dần sang cấu trúc mới, sau cùng mới contract. Giữ cột cũ trong rollback window, kiểm thử cả các cặp app/schema và tính cả job, consumer, report lẫn service khác trong kế hoạch.

## Tài liệu tham khảo

- [Flyway — Versioned migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations): tổ chức migration theo phiên bản và quản lý lịch sử schema.
- [Liquibase — Changesets](https://docs.liquibase.com/concepts/changelogs/changeset.html): changelog, changeset và quản lý thứ tự thay đổi.
- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): thay đổi cấu trúc bảng, lock và validate constraint.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): tạo index và CONCURRENTLY.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): CHECK, NOT NULL, foreign key và constraint validation.


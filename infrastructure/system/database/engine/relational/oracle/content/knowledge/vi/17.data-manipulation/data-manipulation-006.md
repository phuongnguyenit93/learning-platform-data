# Nguồn MERGE trùng khóa và tính xác định của thao tác đồng bộ

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Thay đổi dữ liệu  
> **Mục tiêu:** Hiểu yêu cầu về tính duy nhất của nguồn MERGE; nhận diện duplicate key, fanout, ORA-30926 và ORA-00001; chuẩn hóa nguồn bằng ROW_NUMBER hoặc GROUP BY; bảo vệ khóa đích bằng constraint; thiết kế đồng bộ có quy tắc chọn bản ghi rõ ràng, có thể lặp lại và kiểm chứng.

## 1. MERGE đồng bộ nguồn với đích theo khóa

Oracle MERGE kết hợp logic UPDATE và INSERT trong một câu lệnh. Điều kiện ON xác định hàng nguồn nào khớp với hàng đích:

~~~sql
MERGE INTO customer_status t
USING customer_status_stage s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.status = s.status,
        t.updated_at = s.updated_at
WHEN NOT MATCHED THEN
    INSERT (customer_id, status, updated_at)
    VALUES (s.customer_id, s.status, s.updated_at);
~~~

Trong ví dụ, CUSTOMER_ID là khóa ghép nối và nghiệp vụ kỳ vọng mỗi khách hàng có một trạng thái hiện hành ở bảng đích.

Trước khi viết MERGE, cần trả lời:

1. Với một CUSTOMER_ID, nguồn cung cấp bản ghi nào để đồng bộ?
2. Trong bảng đích, một CUSTOMER_ID có xác định tối đa một hàng không?
3. Nếu nguồn có nhiều bản ghi cùng khóa, chúng là bản sao, sự kiện hợp lệ, delta cần cộng gộp hay xung đột?

**Nguyên tắc:** Nguồn MERGE phải được chuẩn hóa theo khóa ghép nối; bảng đích phải bảo vệ tính duy nhất của khóa nếu nghiệp vụ yêu cầu một hàng đích cho mỗi khóa.

## 2. Grain của nguồn và đích

Grain mô tả ý nghĩa của một dòng trong bảng hoặc tập kết quả.

| Tập dữ liệu | Grain ví dụ |
|---|---|
| CUSTOMER_STATUS | Một trạng thái hiện hành cho mỗi khách hàng |
| CUSTOMER_STATUS_STAGE | Một sự kiện cập nhật; có thể nhiều sự kiện mỗi khách hàng |
| CUSTOMER_STATUS_SOURCE | Một trạng thái được chọn cuối cùng cho mỗi khách hàng |
| CUSTOMER_STATUS_HISTORY | Một phiên bản trạng thái theo khách hàng và thời điểm hiệu lực |

Bảng staging có thể hợp lệ khi lưu nhiều sự kiện cho cùng khách hàng. Nhưng nếu dùng staging để cập nhật một hàng hiện hành, phải có quy tắc chọn hoặc tổng hợp các sự kiện trước khi MERGE.

Nguồn trùng khóa có thể do nhiều sự kiện hợp lệ, nhiều lần cập nhật trong ngày, JOIN nhân dòng, dữ liệu nạp lặp hoặc nhiều hệ thống cùng gửi bản ghi. Cần hiểu ý nghĩa dữ liệu trước khi chọn cách xử lý.

## 3. Tính xác định của MERGE và ORA-30926

Oracle mô tả MERGE là câu lệnh xác định (deterministic): cùng một hàng của bảng đích không thể bị UPDATE nhiều hơn một lần trong cùng câu lệnh MERGE.

Giả sử đích có một hàng:

~~~text
CUSTOMER_ID | STATUS
------------+--------
10          | ACTIVE
~~~

Nguồn có hai hàng cùng khóa:

~~~text
CUSTOMER_ID | STATUS
------------+---------
10          | ACTIVE
10          | BLOCKED
~~~

Cả hai hàng nguồn đều khớp cùng hàng đích qua:

~~~sql
ON (t.customer_id = s.customer_id)
~~~

Khi MERGE cố gắng cập nhật cùng một hàng đích từ nhiều hàng nguồn, Oracle có thể báo:

~~~text
ORA-30926: unable to get a stable set of rows in the source tables
~~~

Đây là tình huống thường gặp khi nguồn có nhiều hàng cùng khóa khớp một target row. ORA-30926 cũng có thể liên quan đến tập nguồn không ổn định hoặc tình huống DML đồng thời tùy trường hợp; không nên kết luận mọi lỗi ORA-30926 đều do duplicate key.

### 3.1. Không dựa vào ORDER BY của nguồn

Thêm ORDER BY vào subquery nguồn với hy vọng hàng cuối cùng sẽ thắng không phải quy tắc đồng bộ an toàn. MERGE là thao tác theo tập dữ liệu; không giả định Oracle xử lý hàng nguồn theo thứ tự hiển thị hoặc hàng cuối cùng sẽ ghi đè hàng trước.

Nếu nghiệp vụ muốn lấy bản ghi mới nhất, hãy xác định bản ghi đó trong nguồn bằng analytic function với tiêu chí tie-breaker duy nhất.

### 3.2. Nguồn trùng khóa nhưng đích chưa có hàng

Giả sử đích chưa có CUSTOMER_ID = 20, nguồn có hai dòng cùng khóa. Cả hai có thể đi vào nhánh WHEN NOT MATCHED:

- Nếu đích có PRIMARY KEY/UNIQUE trên CUSTOMER_ID, thao tác có thể gặp ORA-00001: unique constraint violated.
- Nếu không có constraint bảo vệ, hai hàng trùng khóa có thể được chèn vào đích.

Đây khác với tình huống nhiều hàng nguồn UPDATE cùng một hàng đích. Vì vậy cần kiểm tra cả nhánh MATCHED và NOT MATCHED.

## 4. Nhận diện loại duplicate

### 4.1. Bản sao hoàn toàn

~~~text
CUSTOMER_ID | STATUS | CREDIT_LIMIT
------------+--------+-------------
10          | ACTIVE | 5000
10          | ACTIVE | 5000
~~~

Nếu hai dòng giống nhau trên mọi cột có ý nghĩa và quy tắc nghiệp vụ cho phép bỏ bản sao, DISTINCT có thể loại chúng.

### 4.2. Trùng khóa nhưng khác giá trị

~~~text
CUSTOMER_ID | STATUS
------------+---------
10          | ACTIVE
10          | BLOCKED
~~~

DISTINCT vẫn giữ cả hai dòng. Đây là xung đột: phải có quy tắc nghiệp vụ như sự kiện mới nhất thắng, source priority cao hơn thắng, version lớn hơn thắng, cộng gộp delta, hoặc từ chối batch để xử lý thủ công.

Không tự dùng MAX(STATUS), MIN(STATUS) hay một giá trị tùy tiện chỉ để MERGE chạy được.

### 4.3. Trùng do JOIN nhân dòng

~~~sql
SELECT c.customer_id,
       c.status,
       p.phone_number
FROM customers c
JOIN customer_phones p
  ON p.customer_id = c.customer_id;
~~~

Nếu một khách hàng có ba số điện thoại, query nguồn tạo ba dòng cho cùng CUSTOMER_ID. Nếu MERGE theo CUSTOMER_ID để cập nhật trạng thái khách hàng, nguồn đã sai grain.

Nếu cần đồng bộ từng số điện thoại, khóa phải bao gồm PHONE_ID hoặc khóa nghiệp vụ của số điện thoại. Nếu chỉ cần trạng thái khách hàng, bỏ JOIN không cần thiết hoặc tổng hợp/chọn attribute theo quy tắc rõ ràng.

## 5. Kiểm tra khóa trùng trước MERGE

Chạy kiểm tra trên đúng phạm vi batch hoặc query nguồn sẽ được MERGE sử dụng.

### 5.1. Khóa đơn

~~~sql
SELECT customer_id,
       COUNT(*) AS source_rows
FROM customer_status_stage
WHERE batch_id = :p_batch_id
GROUP BY customer_id
HAVING COUNT(*) > 1
ORDER BY customer_id;
~~~

### 5.2. Khóa ghép

Nếu business key gồm TENANT_ID và EXTERNAL_CUSTOMER_ID:

~~~sql
SELECT tenant_id,
       external_customer_id,
       COUNT(*) AS source_rows
FROM customer_stage
WHERE batch_id = :p_batch_id
GROUP BY tenant_id, external_customer_id
HAVING COUNT(*) > 1;
~~~

Kiểm tra đúng toàn bộ cột trong ON. Chỉ kiểm tra một phần khóa có thể báo trùng giả hoặc bỏ sót trùng thật.

### 5.3. Khóa NULL

~~~sql
SELECT COUNT(*) AS null_key_rows
FROM customer_status_stage
WHERE batch_id = :p_batch_id
  AND customer_id IS NULL;
~~~

Với điều kiện `t.customer_id = s.customer_id`, NULL không bằng NULL; phép so sánh trả UNKNOWN nên hai hàng NULL không khớp nhau. Một hàng nguồn NULL có thể đi vào WHEN NOT MATCHED nếu schema cho phép.

Nếu CUSTOMER_ID là khóa đồng bộ, thường nên bắt buộc NOT NULL. Với khóa ghép, xác định rõ từng thành phần có được phép NULL hay không.

### 5.4. Duplicate trong đích

~~~sql
SELECT customer_id,
       COUNT(*) AS target_rows
FROM customer_status
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Nếu nghiệp vụ yêu cầu một hàng mỗi customer, kết quả đúng phải rỗng và bảng cần constraint bảo vệ điều đó.

## 6. Chọn một hàng bằng ROW_NUMBER

Khi nguồn có nhiều phiên bản cho cùng khóa và quy tắc là lấy bản ghi mới nhất, dùng ROW_NUMBER.

~~~sql
CREATE TABLE customer_status_stage (
    stage_row_id NUMBER PRIMARY KEY,
    batch_id NUMBER NOT NULL,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL,
    changed_at TIMESTAMP(6) WITH TIME ZONE,
    source_version NUMBER
);
~~~

Tạo thứ hạng trong từng CUSTOMER_ID:

~~~sql
SELECT stage_row_id,
       customer_id,
       status,
       changed_at,
       source_version,
       ROW_NUMBER() OVER (
           PARTITION BY customer_id
           ORDER BY changed_at DESC NULLS LAST,
                    source_version DESC NULLS LAST,
                    stage_row_id DESC
       ) AS rn
FROM customer_status_stage
WHERE batch_id = :p_batch_id;
~~~

PARTITION BY chia dữ liệu theo khách hàng. CHANGED_AT ưu tiên sự kiện mới nhất; SOURCE_VERSION là tiêu chí tiếp theo; STAGE_ROW_ID là tie-breaker cuối cùng và duy nhất vì là primary key.

Lọc RN = 1 để lấy đúng một hàng cho mỗi khách hàng:

~~~sql
SELECT customer_id,
       status,
       changed_at,
       source_version
FROM (
    SELECT s.customer_id,
           s.status,
           s.changed_at,
           s.source_version,
           ROW_NUMBER() OVER (
               PARTITION BY s.customer_id
               ORDER BY s.changed_at DESC NULLS LAST,
                        s.source_version DESC NULLS LAST,
                        s.stage_row_id DESC
           ) AS rn
    FROM customer_status_stage s
    WHERE s.batch_id = :p_batch_id
)
WHERE rn = 1;
~~~

### 6.1. MERGE từ nguồn đã chuẩn hóa

~~~sql
MERGE INTO customer_status t
USING (
    SELECT customer_id,
           status,
           changed_at,
           source_version
    FROM (
        SELECT s.customer_id,
               s.status,
               s.changed_at,
               s.source_version,
               ROW_NUMBER() OVER (
                   PARTITION BY s.customer_id
                   ORDER BY s.changed_at DESC NULLS LAST,
                            s.source_version DESC NULLS LAST,
                            s.stage_row_id DESC
               ) AS rn
        FROM customer_status_stage s
        WHERE s.batch_id = :p_batch_id
    )
    WHERE rn = 1
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.status = s.status,
        t.changed_at = s.changed_at,
        t.source_version = s.source_version
WHEN NOT MATCHED THEN
    INSERT (
        customer_id,
        status,
        changed_at,
        source_version
    )
    VALUES (
        s.customer_id,
        s.status,
        s.changed_at,
        s.source_version
    );
~~~

Nguồn MERGE có tối đa một hàng mỗi CUSTOMER_ID. Việc chọn hàng thắng được xác định bởi thứ tự analytic, không phụ thuộc thứ tự đọc ngẫu nhiên.

### 6.2. Tie-breaker cuối phải duy nhất

Nếu chỉ sắp xếp theo CHANGED_AT DESC mà hai hàng có cùng thời điểm, thứ tự tương đối giữa chúng không được xác định. Hàng được ROW_NUMBER chọn có thể thay đổi giữa các lần chạy.

Thêm STAGE_ROW_ID duy nhất vào cuối ORDER BY để tạo thứ tự toàn phần. Nếu hệ thống nguồn có event sequence, version hoặc transaction ID đáng tin cậy, ưu tiên dùng chúng làm tiêu chí nghiệp vụ. Tie-breaker kỹ thuật chỉ quyết định giữa các bản ghi vẫn hòa sau tiêu chí nghiệp vụ.

Nếu không có thông tin đủ để quyết định giữa hai nội dung xung đột, hãy đưa khóa vào báo cáo lỗi thay vì âm thầm chọn một hàng.

## 7. Tổng hợp nguồn bằng GROUP BY

ROW_NUMBER phù hợp khi cần chọn một bản ghi đại diện. Nếu nhiều dòng nguồn là các phần đóng góp hợp lệ cần kết hợp, hãy GROUP BY.

Ví dụ các sự kiện biến động số dư:

~~~text
ACCOUNT_ID | DELTA_AMOUNT
-----------+-------------
100        | 50
100        | -10
100        | 25
200        | 100
~~~

Nếu nghiệp vụ yêu cầu tổng biến động theo tài khoản:

~~~sql
SELECT account_id,
       SUM(delta_amount) AS net_delta,
       COUNT(*) AS event_count
FROM account_events_stage
WHERE batch_id = :p_batch_id
GROUP BY account_id;
~~~

Có thể dùng tập tổng hợp làm nguồn MERGE:

~~~sql
MERGE INTO account_batch_totals t
USING (
    SELECT account_id,
           SUM(delta_amount) AS net_delta,
           COUNT(*) AS event_count
    FROM account_events_stage
    WHERE batch_id = :p_batch_id
    GROUP BY account_id
) s
ON (t.account_id = s.account_id)
WHEN MATCHED THEN
    UPDATE SET
        t.net_delta = s.net_delta,
        t.event_count = s.event_count
WHEN NOT MATCHED THEN
    INSERT (account_id, net_delta, event_count)
    VALUES (s.account_id, s.net_delta, s.event_count);
~~~

Chọn aggregate theo ý nghĩa dữ liệu:

| Ý nghĩa nguồn | Cách xử lý có thể phù hợp |
|---|---|
| Nhiều delta cần cộng | SUM |
| Nhiều sự kiện, cần số lượng | COUNT |
| Cần giá trị lớn nhất theo nghiệp vụ | MAX |
| Cần giá trị nhỏ nhất theo nghiệp vụ | MIN |
| Cần bản ghi mới nhất với nhiều cột đi kèm | ROW_NUMBER rồi RN = 1 |
| Cần giữ mọi bản ghi lịch sử | Giữ nguyên, dùng khóa sự kiện/phiên bản |

Không dùng MAX trên từng cột độc lập để giả lập “lấy hàng mới nhất”. MAX(STATUS) và MAX(CHANGED_AT) có thể đến từ hai dòng khác nhau, tạo thành tổ hợp chưa từng tồn tại. Muốn lấy cả hàng mới nhất, dùng ROW_NUMBER rồi chọn toàn bộ cột từ cùng hàng.

## 8. Khi nào nên từ chối batch?

Không phải hệ thống nào cũng được phép tự chọn bản ghi thắng. Với dữ liệu tài chính, quyền truy cập hoặc trạng thái pháp lý, hai sự kiện xung đột có thể phải được xử lý thủ công.

~~~sql
SELECT customer_id,
       COUNT(*) AS row_count
FROM customer_status_stage
WHERE batch_id = :p_batch_id
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Nếu truy vấn trả về dòng, quy trình có thể:

1. Ghi nhận batch ở trạng thái VALIDATION_FAILED.
2. Lưu khóa trùng và dữ liệu liên quan vào bảng audit/quarantine.
3. Không chạy MERGE cho batch đó.
4. Yêu cầu nguồn gửi lại hoặc người có thẩm quyền xử lý xung đột.
5. Chỉ chạy lại sau khi dữ liệu được xác nhận.

Tính xác định có nghĩa là kết quả được quyết định bởi quy tắc rõ ràng; nó không bắt buộc phải tự động sửa mọi dữ liệu trùng.

## 9. Bảo vệ khóa đích bằng constraint

Nếu CUSTOMER_STATUS phải có một hàng mỗi khách hàng:

~~~sql
ALTER TABLE customer_status
MODIFY (customer_id NOT NULL);

ALTER TABLE customer_status
ADD CONSTRAINT uq_customer_status_customer
UNIQUE (customer_id);
~~~

Hoặc khai báo CUSTOMER_ID là PRIMARY KEY nếu đó là khóa chính thực sự.

Constraint bảo vệ bảng đích khỏi dữ liệu trùng đến từ mọi đường ghi: MERGE, INSERT trực tiếp, batch khác hoặc ứng dụng khác. Kiểm tra ở code ứng dụng không thay thế được ràng buộc ở database.

Nếu bảng đã có duplicate, lệnh thêm constraint sẽ thất bại. Tìm và xử lý dữ liệu cũ theo quy tắc nghiệp vụ trước khi thêm UNIQUE; không xóa tùy tiện một bản ghi chỉ để DDL thành công.

### 9.1. Khóa ghép

Nếu khóa đồng bộ là TENANT_ID và EXTERNAL_ID:

~~~sql
ALTER TABLE external_customer
ADD CONSTRAINT uq_external_customer
UNIQUE (tenant_id, external_id);
~~~

Nguồn MERGE phải duy nhất theo cả hai cột và điều kiện ON cũng phải dùng cả hai:

~~~sql
ON (
    t.tenant_id = s.tenant_id
    AND t.external_id = s.external_id
)
~~~

Chỉ kiểm tra hoặc JOIN bằng EXTERNAL_ID có thể ghép nhầm khách hàng giữa các tenant.

## 10. Khóa NULL và điều kiện ON

So sánh bằng trong SQL không coi NULL bằng NULL. Biểu thức NULL = NULL trả UNKNOWN, không phải TRUE. Vì vậy:

~~~sql
ON (t.external_id = s.external_id)
~~~

không ghép hai hàng có EXTERNAL_ID NULL. Hàng nguồn NULL có thể được xem là không khớp và đi vào nhánh INSERT.

Nếu khóa nghiệp vụ bắt buộc có giá trị, đặt NOT NULL cho mọi thành phần khóa. Nếu nghiệp vụ thật sự xem hai NULL là cùng một giá trị, phải viết điều kiện null-safe tường minh:

~~~sql
ON (
       t.external_id = s.external_id
    OR (t.external_id IS NULL AND s.external_id IS NULL)
)
~~~

Điều kiện này cần đi kèm thiết kế bảo vệ tính duy nhất tương ứng. Không giả định UNIQUE constraint với dữ liệu nullable tự biểu diễn mọi định nghĩa null-safe của khóa nghiệp vụ. Có thể dùng NOT NULL, virtual column hoặc function-based unique index với biểu thức chuẩn hóa được chọn cẩn thận.

Không dùng NVL(key, -1) hoặc sentinel chuỗi tùy tiện nếu giá trị đó có thể xuất hiện thật; sentinel có thể làm hai khóa khác nhau bị xem là một.

## 11. Thiết kế điều kiện ON đúng

ON xác định hàng nào được xem là MATCHED. Nó nên mô tả khóa nhận diện ổn định, thường là primary key hoặc business key duy nhất.

Ví dụ:

~~~sql
ON (
    t.tenant_id = s.tenant_id
    AND t.external_customer_id = s.external_customer_id
)
~~~

Tránh thêm điều kiện thay đổi theo trạng thái vào ON nếu nó không phải một phần của định danh.

~~~sql
ON (
    t.customer_id = s.customer_id
    AND t.status = 'ACTIVE'
)
~~~

Nếu khách hàng đã tồn tại nhưng status là BLOCKED, hàng đích không được xem là khớp. Nguồn có thể đi vào WHEN NOT MATCHED và cố INSERT một CUSTOMER_ID đã tồn tại, dẫn đến ORA-00001 nếu có unique constraint.

Nếu mục tiêu là chỉ UPDATE khách hàng ACTIVE, có thể giữ điều kiện khóa trong ON và đặt điều kiện cập nhật ở WHERE của nhánh UPDATE:

~~~sql
MERGE INTO customer_status t
USING customer_status_source s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET t.status = s.status
    WHERE t.status = 'ACTIVE'
WHEN NOT MATCHED THEN
    INSERT (customer_id, status)
    VALUES (s.customer_id, s.status);
~~~

Khách hàng BLOCKED vẫn được nhận diện là đã tồn tại; điều kiện UPDATE chỉ quyết định có cập nhật hàng khớp hay không. Xác định riêng nghiệp vụ xử lý hàng khớp nhưng không đủ điều kiện cập nhật.

### 11.1. Không cập nhật cột dùng trong ON

Oracle không cho cập nhật cột được tham chiếu trong điều kiện ON của MERGE; trường hợp này có thể báo ORA-38104. Nếu một giá trị khóa cần thay đổi, thiết kế quy trình khác để xử lý khóa cũ và khóa mới, thay vì cố UPDATE cột dùng để nhận diện hàng trong cùng MERGE.

## 12. Nguồn bị nhân dòng do JOIN

Một nguồn có thể trông duy nhất trước JOIN nhưng trở thành trùng sau JOIN:

~~~sql
SELECT s.customer_id,
       s.status,
       a.attribute_value
FROM customer_status_stage s
JOIN customer_attributes a
  ON a.customer_id = s.customer_id
WHERE s.batch_id = :p_batch_id;
~~~

Nếu một customer có nhiều attribute, nguồn có nhiều dòng cho cùng CUSTOMER_ID. Kiểm tra query nguồn hoàn chỉnh:

~~~sql
SELECT customer_id,
       COUNT(*) AS source_rows
FROM (
    SELECT s.customer_id,
           s.status,
           a.attribute_value
    FROM customer_status_stage s
    JOIN customer_attributes a
      ON a.customer_id = s.customer_id
    WHERE s.batch_id = :p_batch_id
)
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Cách sửa phụ thuộc mục tiêu: bỏ JOIN không cần thiết; chọn một attribute theo quy tắc; tổng hợp attribute; hoặc thêm attribute key vào ON nếu mỗi attribute là đối tượng cần đồng bộ riêng.

Không thêm DISTINCT một cách máy móc để che cardinality tăng sau JOIN.

## 13. Đồng bộ theo version và tính idempotent

Nguồn có thể đến không đúng thứ tự. Một batch cũ đến muộn không nên ghi đè trạng thái mới hơn trong đích.

Nếu SOURCE_VERSION tăng đơn điệu, chỉ UPDATE khi version nguồn mới hơn:

~~~sql
MERGE INTO customer_status t
USING (
    SELECT customer_id,
           status,
           source_version
    FROM (
        SELECT s.customer_id,
               s.status,
               s.source_version,
               ROW_NUMBER() OVER (
                   PARTITION BY s.customer_id
                   ORDER BY s.source_version DESC,
                            s.stage_row_id DESC
               ) AS rn
        FROM customer_status_stage s
        WHERE s.batch_id = :p_batch_id
    )
    WHERE rn = 1
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.status = s.status,
        t.source_version = s.source_version
    WHERE s.source_version > t.source_version
WHEN NOT MATCHED THEN
    INSERT (customer_id, status, source_version)
    VALUES (s.customer_id, s.status, s.source_version);
~~~

Điều kiện version ngăn phiên bản cũ ghi đè phiên bản mới trong nhánh MATCHED. Quy tắc version phải do hệ thống nguồn đảm bảo; không dùng timestamp client không đáng tin như thứ tự tuyệt đối nếu đồng hồ có thể lệch.

**Idempotent** trong ngữ cảnh này nghĩa là chạy lại cùng batch/nguồn không tạo thêm bản ghi trùng và không làm trạng thái đích thay đổi ngoài quy tắc đã định. Các điều kiện hỗ trợ gồm khóa đích có UNIQUE, nguồn một hàng mỗi khóa, quy tắc chọn version ổn định và batch có định danh rõ.

Có thể tránh UPDATE không cần thiết khi giá trị không đổi:

~~~sql
MERGE INTO customer_status t
USING customer_status_source s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.status = s.status,
        t.credit_limit = s.credit_limit
    WHERE DECODE(t.status, s.status, 0, 1) = 1
       OR DECODE(t.credit_limit, s.credit_limit, 0, 1) = 1
WHEN NOT MATCHED THEN
    INSERT (customer_id, status, credit_limit)
    VALUES (s.customer_id, s.status, s.credit_limit);
~~~

Trong Oracle, DECODE xem hai NULL là tương đương khi so sánh. Ví dụ này minh họa cách tránh update khi hai giá trị đã giống nhau; cần dùng đúng datatype và quy tắc so sánh của cột. Có thể thay bằng điều kiện null-safe tường minh.

## 14. Nhiều session MERGE đồng thời

MERGE không thay thế constraint và chiến lược xử lý cạnh tranh.

Ví dụ hai session gần như đồng thời MERGE cùng CUSTOMER_ID chưa tồn tại. Cả hai có thể bắt đầu từ trạng thái chưa có hàng đích khớp và cùng cố INSERT. UNIQUE constraint bảo vệ tính toàn vẹn; một session có thể phải chờ rồi nhận lỗi unique nếu session kia đã chèn.

Vì vậy:

- Luôn có PRIMARY KEY/UNIQUE cho khóa nghiệp vụ cần duy nhất.
- Xác định cách ứng dụng xử lý ORA-00001 trong tình huống retry/concurrent upsert.
- Sau lỗi cạnh tranh, có thể đọc lại hàng đích và áp dụng quy tắc version trong transaction mới.
- Nếu cần tuần tự hóa theo khóa, thiết kế cơ chế lock hoặc điều phối batch rõ ràng.
- Không dùng truy vấn kiểm tra “đã tồn tại chưa” ở ứng dụng làm bảo đảm cuối cùng; trạng thái có thể đổi trước khi INSERT.

Nếu nhiều batch chạy song song, cần phân vùng theo khóa để hai worker không cùng xử lý một business key khi nghiệp vụ yêu cầu thứ tự.

## 15. Quy trình đồng bộ nhiều bước

~~~text
Nguồn ngoài / CDC / API
          |
          v
      STAGING
  giữ dữ liệu thô + batch_id
          |
          v
     VALIDATION
  - khóa NULL?
  - khóa trùng?
  - dữ liệu xung đột?
  - datatype/miền hợp lệ?
          |
          +---- lỗi ----> QUARANTINE / báo cáo
          |
          v
   SOURCE NORMALIZATION
  - ROW_NUMBER chọn phiên bản
  - hoặc GROUP BY tổng hợp
  - một dòng mỗi khóa đích
          |
          v
        MERGE
  - match theo business key
  - update/insert theo version
  - unique constraint bảo vệ đích
          |
          v
        AUDIT
  - batch ID
  - số dòng nguồn/được chọn
  - số insert/update
  - lỗi và thời gian chạy
~~~

Bảng audit có thể lưu BATCH_ID, tên nguồn, thời điểm bắt đầu/kết thúc, số dòng thô, số khóa duy nhất, số dòng bị loại do duplicate hoặc xung đột, số insert/update nếu đo được, trạng thái và mã lỗi. Không ghi dữ liệu nhạy cảm không cần thiết.

Sau khi chuẩn hóa nguồn, có thể xác nhận không còn khóa trùng bằng cách GROUP BY trên chính query nguồn cuối cùng. Nếu nguồn có JOIN, phải kiểm tra sau JOIN, không chỉ kiểm tra bảng staging ban đầu.

## 16. Khi nào nên dùng lịch sử thay vì chọn một hàng mới nhất?

Nếu cần lưu mọi thay đổi trạng thái, không nên loại bỏ các hàng cũ bằng ROW_NUMBER. Hãy thiết kế bảng lịch sử với grain riêng:

~~~sql
CREATE TABLE customer_status_history (
    event_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL,
    effective_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    source_version NUMBER
);
~~~

Mỗi sự kiện là một hàng. Nếu cần trạng thái hiện hành, có thể tạo query hoặc view chọn phiên bản mới nhất.

| Nhu cầu | Thiết kế |
|---|---|
| Một trạng thái hiện tại mỗi customer | MERGE từ nguồn một hàng/khóa |
| Lưu mọi sự kiện thay đổi | INSERT lịch sử, khóa sự kiện duy nhất |
| Tái dựng trạng thái tại thời điểm | History với effective time/version |
| Tóm tắt nhiều giao dịch | GROUP BY theo khóa đích |
| Xung đột cần người xử lý | Quarantine, không tự chọn winner |

Nếu dữ liệu là event log, mỗi event có identity riêng. Không dùng CUSTOMER_ID làm khóa duy nhất của event history vì nhiều sự kiện cùng customer là hợp lệ.

## 17. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| MERGE trực tiếp từ staging có nhiều hàng mỗi business key | Một target row có thể bị nhiều source row tác động; ORA-30926 | Chuẩn hóa nguồn trước |
| Nghĩ ORDER BY trong source quyết định hàng thắng | Kết quả phụ thuộc cách thực thi | ROW_NUMBER với tie-breaker |
| Dùng DISTINCT để loại mọi duplicate key | Các hàng khác giá trị vẫn tồn tại | Chọn theo quy tắc hoặc GROUP BY |
| Dùng MAX trên từng cột để lấy hàng mới nhất | Giá trị có thể đến từ nhiều source row khác nhau | ROW_NUMBER rồi lấy toàn bộ hàng |
| Nguồn trùng khóa nhưng target chưa có hàng | Nhiều INSERT; có thể ORA-00001 hoặc tạo duplicate | Unique constraint và chuẩn hóa nguồn |
| Target không có unique constraint | Một business key có thể có nhiều hàng đích | PRIMARY KEY/UNIQUE |
| ON thiếu một phần khóa ghép | Ghép nhầm tenant/đối tượng | Dùng đủ business key |
| Đưa status/filter thay đổi vào ON | Hàng tồn tại có thể bị coi là NOT MATCHED | ON theo identity; điều kiện update đặt đúng nhánh |
| Khóa trong ON là NULL | Equality không match NULL | NOT NULL hoặc null-safe key contract |
| Cột ON được cập nhật | ORA-38104 | Thiết kế thao tác đổi khóa riêng |
| Không xử lý hai session MERGE cùng khóa | Cạnh tranh INSERT, ORA-00001 | Unique constraint, retry/serialize |
| Chọn bản ghi mới nhất nhưng không tie-break | Hàng được chọn có thể không ổn định khi timestamp bằng nhau | Thêm event ID/sequence duy nhất |
| Gộp sự kiện lịch sử thành một hàng | Mất lịch sử nghiệp vụ | Tách current-state và history model |

## 18. Bài thực hành

Các bài dùng schema lab hoặc staging riêng; chỉ chạy DDL/DML trên môi trường được phép.

### Bài 1 — Nhận diện duplicate source key

Tạo staging có hai dòng cùng CUSTOMER_ID nhưng khác STATUS. Viết GROUP BY/HAVING tìm khóa trùng. Giải thích vì sao DISTINCT không loại được cả hai.

### Bài 2 — Quan sát lỗi MERGE

Tạo target có một hàng CUSTOMER_ID = 10 và source có hai hàng cùng CUSTOMER_ID. Thử MERGE cập nhật cùng hàng đích. Quan sát lỗi Oracle và giải thích điều kiện khiến hai source row cùng match một target row. Không dùng production data cho bài thử.

### Bài 3 — Nguồn target chưa có khóa

Dùng target key chưa tồn tại, giữ hai source row cùng khóa. Thử MERGE với unique constraint và giải thích khác biệt giữa lỗi update nhiều lần và lỗi unique khi insert.

### Bài 4 — Chọn winner bằng ROW_NUMBER

Thêm CHANGED_AT, SOURCE_VERSION và STAGE_ROW_ID. Dùng ROW_NUMBER PARTITION BY CUSTOMER_ID ORDER BY CHANGED_AT DESC, SOURCE_VERSION DESC, STAGE_ROW_ID DESC. Xác nhận nguồn cuối có tối đa một dòng mỗi customer.

### Bài 5 — Tie-breaker

Tạo hai source row có cùng CHANGED_AT và SOURCE_VERSION nhưng STAGE_ROW_ID khác nhau. Chạy truy vấn chọn winner nhiều lần. Giải thích vì sao stage_row_id duy nhất làm thứ tự xác định.

### Bài 6 — Tổng hợp delta

Tạo nhiều dòng giao dịch cho một ACCOUNT_ID. Dùng GROUP BY và SUM để tạo một dòng mỗi account, sau đó MERGE tổng delta. So sánh với việc chỉ chọn một dòng bằng ROW_NUMBER.

### Bài 7 — Bảo vệ target

Tìm duplicate trong target, xử lý dữ liệu theo quy tắc lab rồi thêm UNIQUE constraint cho business key. Thử INSERT hai lần cùng key để thấy constraint bảo vệ mọi đường ghi.

### Bài 8 — ON condition

Viết hai câu MERGE: một câu đặt status vào ON, câu còn lại chỉ dùng business key trong ON và đặt điều kiện cập nhật ở UPDATE WHERE. Dùng target có status BLOCKED để quan sát khác biệt MATCHED/NOT MATCHED.

### Bài 9 — Idempotency và version

Chạy cùng batch hai lần. Sau đó thử batch có SOURCE_VERSION cũ hơn đích. Xác nhận điều kiện version ngăn dữ liệu cũ ghi đè dữ liệu mới.

### Bài 10 — Nguồn bị nhân bởi JOIN

Tạo một khách hàng có nhiều dòng attribute, JOIN staging với attribute rồi kiểm tra COUNT(*) theo customer. Sửa nguồn để giữ đúng grain và giải thích vì sao DISTINCT không phải cách sửa mặc định.

## 19. Checklist trước khi chạy MERGE

- [ ] Xác định grain của target và source.
- [ ] Ghi rõ toàn bộ business key trong ON.
- [ ] Kiểm tra source có khóa NULL hay không.
- [ ] Đếm duplicate key trong đúng batch/phạm vi nguồn.
- [ ] Nếu có duplicate, xác định đó là bản sao, sự kiện hợp lệ, delta hay xung đột.
- [ ] Nếu chọn winner, dùng ROW_NUMBER với thứ tự nghiệp vụ và tie-breaker duy nhất.
- [ ] Nếu cộng gộp, GROUP BY theo đúng khóa và dùng aggregate đúng ý nghĩa.
- [ ] Kiểm tra nguồn sau JOIN cuối cùng, không chỉ bảng staging ban đầu.
- [ ] Bảo vệ khóa đích bằng PRIMARY KEY/UNIQUE phù hợp.
- [ ] Xác nhận ON không chứa điều kiện làm sai nhận diện hàng và không cập nhật cột ON.
- [ ] Xác định hành vi khi nguồn không match và nhiều hàng có thể INSERT.
- [ ] Có quy tắc xử lý ORA-30926, ORA-00001 và retry đồng thời.
- [ ] Nếu dữ liệu có version, ngăn batch cũ ghi đè batch mới.
- [ ] Có audit batch, số dòng và quy trình quarantine.
- [ ] Kiểm thử chạy lại cùng batch và hai session cạnh tranh trên schema lab.

## 20. Ghi nhớ cốt lõi

- MERGE đồng bộ nguồn với đích theo ON; khóa ghép phải phản ánh đúng identity nghiệp vụ.
- Oracle không cho cùng một hàng đích bị UPDATE nhiều lần trong một MERGE. Nhiều hàng nguồn cùng khóa khớp một target row thường dẫn đến ORA-30926.
- Nếu target chưa có khóa nhưng source có nhiều hàng cùng khóa, nhánh INSERT có thể thử chèn nhiều bản ghi; unique constraint có thể báo ORA-00001.
- **ORDER BY trong source không phải quy tắc chọn winner.** Dùng ROW_NUMBER với tiêu chí nghiệp vụ và tie-breaker duy nhất.
- Dùng GROUP BY khi các dòng nguồn là thành phần cần tổng hợp; không dùng MAX tùy tiện để tạo một hàng giả.
- DISTINCT chỉ loại hàng giống nhau trên toàn bộ biểu thức SELECT, không giải quyết mọi trường hợp trùng business key.
- Target cần PRIMARY KEY/UNIQUE để bảo vệ tính duy nhất trước mọi đường ghi.
- ON nên nhận diện hàng bằng khóa ổn định; điều kiện cập nhật bổ sung đặt trong nhánh UPDATE khi phù hợp.
- NULL không bằng NULL trong phép so sánh thông thường; định nghĩa rõ chính sách khóa nullable.
- MERGE không thay thế chiến lược xử lý cạnh tranh giữa nhiều session; constraint, retry hoặc tuần tự hóa vẫn cần thiết.
- Nếu cần lưu mọi sự kiện, dùng bảng history/event với khóa riêng thay vì ép tất cả thành một hàng hiện hành.
- Tính xác định đến từ quy tắc dữ liệu, khóa và lựa chọn nguồn rõ ràng, không đến từ việc câu MERGE chạy thành công một lần.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — MERGE, analytic functions, ROW_NUMBER, joins và constraints.
- [Oracle Database Error Messages](https://docs.oracle.com/en/database/) — ORA-30926, ORA-00001 và ORA-38104.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — primary key, unique constraint, transaction và read consistency.
- [Oracle Database Data Warehousing Guide](https://docs.oracle.com/en/database/) — staging, data loading và xử lý dữ liệu theo batch.

Cú pháp MERGE và một số chi tiết lỗi có thể khác theo release Oracle và hình dạng câu nguồn. Khi triển khai, đối chiếu tài liệu đúng phiên bản, kiểm tra duplicate trên chính nguồn cuối cùng và bảo vệ business key bằng constraint ở database.


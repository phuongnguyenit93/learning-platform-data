# Thêm thuộc tính, đổi kiểu, siết ràng buộc và đánh giá dữ liệu hiện có

Một mô hình dữ liệu hiếm khi giữ nguyên từ ngày đầu đến khi hệ thống ngừng hoạt động. Ban đầu, cửa hàng chỉ lưu tổng tiền đơn hàng dưới dạng chuỗi để nhập nhanh từ một nguồn cũ. Sau vài năm, hệ thống cần tổng hợp doanh thu chính xác, bổ sung kênh bán, liên kết Customer theo tenant và ngăn các trạng thái đơn hàng không hợp lệ. Những thay đổi tưởng như đơn giản — thêm cột, đổi TEXT thành BIGINT, thêm NOT NULL hay UNIQUE — có thể khiến **dữ liệu cũ không còn hợp lệ**, **ứng dụng đang chạy bị lỗi** hoặc **các tiến trình ghi tranh chấp trong lúc migration**.

Bài học trong chương **Tiến hóa mô hình** của module **DATABASE_DATA_MODELING** tập trung vào bốn kỹ năng gắn chặt với nhau:

1. **Thêm thuộc tính** nhưng vẫn tương thích với dữ liệu và ứng dụng hiện có.
2. **Đổi kiểu dữ liệu** mà không làm mất giá trị, sai đơn vị hoặc vượt giới hạn biểu diễn.
3. **Siết ràng buộc** theo lộ trình kiểm chứng: CHECK, NOT NULL, UNIQUE, FOREIGN KEY và quy tắc nghiệp vụ.
4. **Đánh giá dữ liệu hiện có** trước, trong và sau migration để quyết định có thể áp constraint ngay, phải làm sạch, phải backfill hay phải thiết kế lại.

Trọng tâm là biến yêu cầu thay đổi thành **schema và quy trình chuyển đổi có thể kiểm tra**, trong cả mô hình quan hệ, document, graph và kho phân tích. Các ví dụ kỹ thuật sử dụng PostgreSQL; đặc tính khóa, cơ chế online DDL và syntax phụ thuộc DBMS/phiên bản, vì vậy không áp dụng máy móc cho mọi hệ thống.

> **Nguyên tắc:** Không bắt đầu từ câu lệnh ALTER TABLE. Hãy bắt đầu từ **bất biến mới**, **dữ liệu thực đang vi phạm nó**, **những phiên bản ứng dụng còn tồn tại** và **khả năng khôi phục khi thay đổi bị gián đoạn**.

## 1. Tiến hóa mô hình khác thiết kế bảng mới ở điểm nào?

Khi tạo một bảng hoàn toàn mới, có thể chọn kiểu dữ liệu và constraint lý tưởng trước khi INSERT bản ghi đầu tiên. Khi thay đổi bảng đã có, ít nhất bốn đối tượng phải được xem xét đồng thời:

- **Dữ liệu lịch sử:** hàng triệu bản ghi có NULL, chuỗi sai định dạng, mã bị dùng lặp, tham chiếu mồ côi hoặc giá trị khác quy tắc mới.
- **Ứng dụng hiện hành:** nhiều phiên bản API/worker/batch có thể cùng đọc hoặc ghi, không triển khai đồng loạt.
- **Hợp đồng dữ liệu:** API, sự kiện, báo cáo, CDC, ETL và đối tác có thể phụ thuộc tên cột, kiểu và ngữ nghĩa cũ.
- **Hoạt động hệ thống:** migration dài có thể khóa bảng, tạo WAL, ảnh hưởng replication, chiếm dung lượng, làm backup và rollback khó hơn.

Một thay đổi “đúng” có thể phải thỏa ba lớp khác nhau:

| Lớp kiểm tra | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Schema** | Có thể lưu và truy vấn dữ liệu mới? | total_amount_vnd là BIGINT |
| **Dữ liệu** | Tất cả hàng hiện có đáp ứng kiểu/quy tắc mới? | Không có amount_text không đổi được sang số |
| **Vận hành/tương thích** | Các reader/writer đang chạy có tiếp tục đúng? | Worker cũ vẫn ghi amount_text trong giai đoạn chuyển đổi |

Một migration thành công về cú pháp SQL chưa chứng minh hai lớp còn lại đã đạt.

### 1.1. Ba kiểu thay đổi và tác động

| Thay đổi | Ví dụ | Rủi ro dễ bỏ qua |
| --- | --- | --- |
| **Mở rộng (additive)** | Thêm order_channel | Dữ liệu cũ NULL; writer cũ không ghi cột mới |
| **Chuyển đổi (transformative)** | TEXT tiền sang BIGINT VND | Lỗi parse, overflow, sai đơn vị, chênh lệch khi dual-write |
| **Thu hẹp (restrictive)** | NOT NULL, CHECK, UNIQUE, FK | Hàng cũ vi phạm; bản ghi mới từ phiên bản ứng dụng cũ tiếp tục vi phạm |

Không nên đánh đồng **tương thích cú pháp** với **tương thích ngữ nghĩa**. Thêm một cột có thể không làm vỡ SELECT cụ thể, nhưng nếu consumer dùng SELECT * rồi giải mã theo thứ tự cột cố định, nó vẫn có thể bị ảnh hưởng. Đổi tên trường trong document hoặc sự kiện cũng tác động tới contract bên ngoài database.

## 2. Ca nghiên cứu xuyên suốt: Orders của một hệ bán hàng

Giả sử database đang có:

~~~sql
-- Lược đồ cũ, dùng để mô phỏng bài học trên database thử nghiệm.
CREATE TABLE customer_accounts (
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    customer_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE legacy_orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT,
    amount_text TEXT,
    currency_code TEXT,
    status TEXT,
    external_reference TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Nguồn cũ có các đặc điểm:

- **amount_text** là chuỗi biểu diễn số tiền **VND nguyên đồng**, đôi khi chứa khoảng trắng, NULL, dấu phân cách hoặc ký tự không phải số.
- **currency_code** có thể NULL dù nghiệp vụ đang sử dụng VND; một số hàng có thể ghi tiền tệ khác vì lỗi nguồn.
- **status** là TEXT tự do: PAID, paid, DONE, CANCELLED, UNKNOWN, NULL...
- **customer_id** có thể NULL và chưa có FK ghép bảo vệ đúng tenant.
- **external_reference** có thể trùng do sự kiện nhập lại, nhưng cũng có thể NULL cho đơn tạo thủ công.
- Cả API mới, API cũ và job nhập file vẫn có thể INSERT vào legacy_orders.

Mục tiêu mới cần được viết thành các bất biến, không chỉ là danh sách cột:

1. **total_amount_vnd:** số nguyên không âm, biểu diễn **VND nguyên đồng**, không trộn tiền tệ, không bị tràn BIGINT.
2. **order_channel:** một trong WEB, STORE, PARTNER, UNKNOWN; UNKNOWN chỉ được dùng nếu nguồn thực sự chưa xác định.
3. **status:** thuộc PENDING, PAID, CANCELLED theo quy trình đã được nghiệp vụ xác nhận.
4. **Customer:** khi quy tắc yêu cầu, Customer phải tồn tại trong **cùng tenant**; mục tiêu cuối là customer_id NOT NULL đối với tập đơn thuộc phạm vi áp dụng.
5. **external_reference:** phải duy nhất trong tenant đối với các đơn có reference; quyết định riêng liệu NULL còn hợp lệ hay không.
6. **Tương thích:** không ngừng ghi khi thêm trường; batch và ứng dụng được nâng cấp theo từng giai đoạn.
7. **Đối soát:** sau migration, số hàng và tổng tiền sau làm sạch phải giải thích được từ dữ liệu gốc.

Một số bất biến có thể **không áp dụng cho mọi loại đơn**. Ví dụ đơn tại quầy không có tài khoản khách, hoặc đơn di trú lịch sử chỉ có mã customer đã bị xóa. Trước khi áp NOT NULL, nghiệp vụ phải quyết định liệu tạo Unknown Customer, cho phép guest order với thuộc tính khác, tách loại bản ghi, hay loại dữ liệu ra khỏi phạm vi. Không thay NULL bằng một ID bất kỳ chỉ để constraint thông qua.

## 3. Kiểm kê dữ liệu thực trước khi thiết kế ALTER TABLE

Thay đổi bảng lớn phải có **hồ sơ dữ liệu (data profile)** để biết lượng và loại ngoại lệ, thay vì thử ALTER rồi đợi lỗi.

### 3.1. Quy mô, NULL và phân bố

~~~sql
SELECT COUNT(*) AS total_orders,
       COUNT(*) FILTER (WHERE amount_text IS NULL) AS amount_null,
       COUNT(*) FILTER (WHERE customer_id IS NULL) AS customer_null,
       COUNT(*) FILTER (WHERE currency_code IS NULL) AS currency_null,
       COUNT(*) FILTER (WHERE status IS NULL) AS status_null,
       COUNT(*) FILTER (WHERE external_reference IS NULL) AS reference_null,
       MIN(created_at) AS first_created,
       MAX(created_at) AS last_created
FROM legacy_orders;

SELECT status, COUNT(*) AS rows
FROM legacy_orders
GROUP BY status
ORDER BY rows DESC, status;

SELECT currency_code, COUNT(*) AS rows
FROM legacy_orders
GROUP BY currency_code
ORDER BY rows DESC, currency_code;
~~~

Cần đo cả phân bố theo **tenant, thời gian và nguồn dữ liệu**, vì một ngoại lệ hiếm toàn hệ có thể rất tập trung ở một tenant lớn hoặc một đợt import lịch sử.

### 3.2. Phân loại chuỗi tiền có thể đổi sang số

Trong ví dụ, tiền VND **không có phần thập phân**; chỉ nhận biểu diễn số nguyên không âm, có thể có khoảng trắng đầu/cuối.

~~~sql
SELECT order_id, amount_text
FROM legacy_orders
WHERE amount_text IS NULL
   OR btrim(amount_text) !~ '^[0-9]+$'
ORDER BY order_id
LIMIT 100;
~~~

Không tự làm sạch mọi ký tự không phải số. Chuỗi **1,200** có thể là một nghìn hai trăm hoặc 1,2 theo locale; chuỗi **-500** có thể là bút toán hoàn tiền chứ không phải lỗi đánh máy. Quy tắc chuẩn hóa phải có **nguồn giải thích và phê duyệt nghiệp vụ**.

Kiểm tra nguy cơ vượt phạm vi BIGINT bằng cast trung gian sang NUMERIC chỉ cho những chuỗi đúng định dạng:

~~~sql
WITH parsed AS (
    SELECT order_id,
           CASE
               WHEN amount_text IS NOT NULL
                AND btrim(amount_text) ~ '^[0-9]+$'
               THEN btrim(amount_text)::NUMERIC
               ELSE NULL
           END AS amount_numeric
    FROM legacy_orders
)
SELECT COUNT(*) FILTER (
           WHERE amount_numeric > 9223372036854775807
       ) AS values_exceeding_bigint,
       COUNT(*) FILTER (
           WHERE amount_numeric IS NOT NULL
             AND amount_numeric <= 9223372036854775807
       ) AS parseable_in_range
FROM parsed;
~~~

Không dùng COUNT = 0 của truy vấn này làm bằng chứng đủ nếu chưa kiểm tra NULL, giá trị ký tự sai và dữ liệu phát sinh **sau thời điểm profile**.

### 3.3. Kiểm tra lỗi quy tắc mới và tham chiếu

~~~sql
-- Trạng thái không thuộc miền mới, phân biệt NULL với giá trị rác.
SELECT status, COUNT(*) AS rows
FROM legacy_orders
WHERE status IS NULL
   OR status NOT IN ('PENDING', 'PAID', 'CANCELLED')
GROUP BY status
ORDER BY rows DESC;

-- Customer không tồn tại đúng tenant.
SELECT o.tenant_id, o.order_id, o.customer_id
FROM legacy_orders AS o
LEFT JOIN customer_accounts AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL
ORDER BY o.order_id
LIMIT 100;

-- Trùng reference theo tenant; NULL chưa được coi là tham gia uniqueness.
SELECT tenant_id, external_reference, COUNT(*) AS duplicates
FROM legacy_orders
WHERE external_reference IS NOT NULL
GROUP BY tenant_id, external_reference
HAVING COUNT(*) > 1
ORDER BY duplicates DESC, tenant_id;
~~~

**CHECK, FK, UNIQUE và NOT NULL có cách xử lý NULL khác nhau**; cần đo riêng. Trong PostgreSQL, UNIQUE thông thường cho phép nhiều NULL, còn FK cho phép khóa ngoại NULL nếu không có NOT NULL (theo quy tắc mặc định thích hợp). CHECK trả UNKNOWN với NULL vẫn có thể được coi là đạt, không ép cột có giá trị.

### 3.4. Đánh giá mức độ ảnh hưởng

Hồ sơ nên ghi:

| Phạm vi | Dữ liệu cần thu thập |
| --- | --- |
| **Quy mô** | Số hàng, độ rộng, kích thước bảng/index, tốc độ tăng |
| **Chất lượng** | Số NULL, sai định dạng, overflow, orphan FK, duplicate |
| **Độ lệch** | Tenant/source/ngày có ngoại lệ tập trung |
| **Ngữ nghĩa** | Tiền tệ, timezone, status mapping, guest account |
| **Ứng dụng** | Số writer/reader, version còn chạy, SQL/ORM phụ thuộc |
| **Vận hành** | SLO ghi/đọc, lag replication, backup, lock timeout |
| **Xử lý ngoại lệ** | Tự chuyển được, cần sửa nguồn, cần nghiệp vụ duyệt |
| **Chấp nhận** | Số lượng lỗi còn được phép, deadline và owner |

Dữ liệu mẫu nhỏ không đủ làm hồ sơ production. Nếu có hàng trăm triệu dòng, kiểm kê đầy đủ có thể tốn I/O; cần kế hoạch scan có kiểm soát, mẫu đại diện để ước lượng trước, rồi **kiểm tra toàn bộ các hàng bắt buộc** trước khi cưỡng chế invariant. Không lấy kết quả từ một mẫu ngẫu nhiên làm bằng chứng toàn bộ dữ liệu đã sạch.

## 4. Lộ trình expand → backfill → validate → contract

Một thay đổi an toàn thường tách thành nhiều pha thay vì một migration khổng lồ:

~~~mermaid
flowchart LR
    A["Profile + thiết kế invariant"] --> B["Expand schema"]
    B --> C["Tương thích reader/writer"]
    C --> D["Backfill dữ liệu cũ"]
    D --> E["Validate + đối soát"]
    E --> F["Siết constraint"]
    F --> G["Contract schema cũ"]
~~~

### 4.1. Expand: chấp nhận song song hai cách biểu diễn

- Thêm cột mới **còn nullable** hoặc giá trị mặc định an toàn.
- Bổ sung chỉ mục/constraint ở chế độ có thể triển khai dần.
- Đưa ứng dụng vào trạng thái **đọc được cả cũ và mới**.
- Dừng tạo lỗi mới bằng validation ở đường ghi.

### 4.2. Backfill: chuyển dữ liệu lịch sử

- Chỉ chuyển các bản ghi có quy tắc hợp lệ.
- Chia batch nhỏ, checkpoint/restart được, kiểm soát lock và WAL.
- Không ghi đè thay đổi mới của ứng dụng đồng thời.
- Lưu danh sách ngoại lệ cần xử lý riêng.

### 4.3. Validate: kiểm chứng toàn bộ tập dữ liệu được bảo vệ

- Đếm NULL, orphan, duplicate, sai miền giá trị và chênh lệch hai biểu diễn.
- Đối soát theo tenant/ngày/source và kiểm tra tập bất biến.
- Quan sát dữ liệu mới sau khi reader/writer đã được nâng cấp.

### 4.4. Contract: bỏ đường biểu diễn cũ

- Chuyển tất cả reader sang trường mới, ngăn writer cũ.
- Áp constraint cuối cùng và giữ giám sát.
- Chỉ bỏ cột/bảng cũ sau khi hết thời gian tương thích/rollback, có backup và khả năng phục hồi.
- Cập nhật event/API/schema registry, tài liệu và dashboard theo hợp đồng.

**Contract là giai đoạn nguy hiểm nhất cho rollback.** Sau khi xóa cột cũ hoặc thay đổi ý nghĩa không còn tương thích, muốn quay về phiên bản ứng dụng cũ có thể cần phép chuyển ngược dữ liệu, chưa chắc khả thi nếu trong thời gian đó đã nhận những giá trị mới.

## 5. Thêm thuộc tính mà không tạo ý nghĩa giả

Ví dụ cần thêm **order_channel** cho tất cả đơn.

### 5.1. Bước mở rộng

~~~sql
ALTER TABLE legacy_orders
ADD COLUMN order_channel TEXT;
~~~

Cột mới nullable cho phép phiên bản ứng dụng cũ tiếp tục INSERT (nếu các ứng dụng ấy không phụ thuộc giả định bất thường như INSERT không ghi danh sách cột). Bản ghi lịch sử có NULL là điều **đã biết** chứ không phải lỗi ngay lập tức.

Nếu muốn giá trị mặc định cho đơn mới, chỉ dùng khi default đúng cho mọi đường ghi không khai báo:

~~~sql
ALTER TABLE legacy_orders
ALTER COLUMN order_channel SET DEFAULT 'UNKNOWN';
~~~

**UNKNOWN** là nhãn “chưa xác định”, không được tự diễn giải là WEB, STORE hoặc PARTNER. Nếu nguồn hiện có không đủ thông tin để suy ra, giữ UNKNOWN rồi báo số lượng chưa xác định.

### 5.2. Chỉ backfill khi có bằng chứng

~~~sql
-- Ví dụ chỉ khi nghiệp vụ xác nhận reference bắt đầu bằng WEB- xác định kênh WEB.
UPDATE legacy_orders
SET order_channel = 'WEB'
WHERE order_channel IS NULL
  AND external_reference LIKE 'WEB-%';
~~~

Không có quy tắc nào nói tất cả đơn trước năm 2026 đều thuộc STORE. Nếu suy đoán rồi gán mặc định sai, dashboard lịch sử có thể “trông đủ dữ liệu” nhưng mất độ tin cậy.

### 5.3. Giữ trạng thái chuyển đổi dễ quan sát

~~~sql
SELECT COALESCE(order_channel, '<NULL>') AS channel,
       COUNT(*) AS rows
FROM legacy_orders
GROUP BY COALESCE(order_channel, '<NULL>')
ORDER BY rows DESC;
~~~

Khi business cho phép UNKNOWN như một giá trị có ý nghĩa, có thể thêm CHECK giới hạn miền mà chưa ép tất cả UNKNOWN biến mất:

~~~sql
ALTER TABLE legacy_orders
ADD CONSTRAINT ck_orders_channel
CHECK (order_channel IN ('WEB', 'STORE', 'PARTNER', 'UNKNOWN'))
NOT VALID;
~~~

**CHECK không yêu cầu giá trị khác NULL.** Muốn NOT NULL phải có một bước độc lập sau khi đảm bảo các writer mới không gửi NULL và dữ liệu cũ đã được làm sạch.

## 6. Đổi kiểu dữ liệu: lỗi thường nằm ở ngữ nghĩa, không chỉ cú pháp

Đổi **amount_text TEXT → total_amount_vnd BIGINT** không chỉ là thay đổi kiểu lưu:

- Chuỗi có thể sai định dạng, có dấu phân cách hoặc ký tự whitespace.
- Số có thể lớn hơn giới hạn BIGINT.
- Không phải mọi giá trị đều có cùng currency.
- Refund/credit âm có thể được lưu trong cột cũ mặc dù quy tắc mới chỉ cho đơn bán dương.
- Một số dữ liệu mang đơn vị **đồng**, một số mang **nghìn đồng** nếu nguồn nhập khác nhau.
- Các client cũ có thể ghi amount_text trong khi client mới ghi total_amount_vnd.

Nếu bỏ qua ngữ nghĩa và chạy CAST, có thể tạo một cột đúng kiểu nhưng **sai tiền**.

### 6.1. Đổi trực tiếp bằng ALTER TYPE: khi nào nên tránh?

Ví dụ câu SQL trực tiếp:

~~~sql
-- Chỉ mang tính minh họa; KHÔNG chạy trên production chưa kiểm kê.
ALTER TABLE legacy_orders
ALTER COLUMN amount_text TYPE BIGINT
USING btrim(amount_text)::BIGINT;
~~~

Phép chuyển đổi sẽ lỗi nếu có chuỗi không parse được hoặc overflow. Tùy kiểu, DBMS và phiên bản, ALTER TYPE có thể cần khóa mạnh, rewrite bảng/index, WAL và thời gian thao tác lớn. Nó cũng làm **reader/writer cũ** không còn nhìn thấy kiểu TEXT mong đợi.

Có thể thích hợp với bảng nhỏ, maintenance window đủ rộng, dữ liệu đã sạch và hợp đồng ứng dụng tương thích. Nhưng với bảng nóng, nhiều phiên bản writer và yêu cầu không downtime, nên cân nhắc **shadow column + chuyển dần**.

### 6.2. Thêm cột mới để không phá reader cũ

~~~sql
ALTER TABLE legacy_orders
ADD COLUMN total_amount_vnd BIGINT;
~~~

Giữ amount_text trong thời gian quá độ. Bước tiếp theo không phải backfill ngay rồi bỏ cột cũ, mà là xác định **một dạng canonical cho dữ liệu mới** và bảo đảm các writer đang hoạt động không tiếp tục tạo chênh lệch.

Một chiến lược rollout:

1. Deploy reader có thể hiểu cả cột mới lẫn cột cũ, trong đó cột mới được ưu tiên **chỉ khi dữ liệu đã được xác minh**.
2. Nâng cấp mọi writer hoặc thêm lớp compatibility duy nhất để ghi **cả hai cột trong cùng transaction**.
3. Khi còn writer cũ chỉ ghi amount_text, chưa được coi cột mới đã được đồng bộ; cần bridge/trigger/procedure hoặc đảm bảo writer cũ ngừng hoạt động trước cutover.
4. Backfill phần lịch sử với quy tắc chuyển đổi được phê duyệt.
5. So sánh hai cột, phát hiện bản ghi sửa đồng thời hoặc mới phát sinh.
6. Chuyển mọi reader/consumer sang cột số, áp constraint.
7. Sau khoảng tương thích được phê duyệt mới bỏ amount_text.

**Dual-write ở hai service/database riêng không tự nguyên tử.** Nếu cả hai cột cùng một hàng trong một database, cập nhật hai giá trị trong **cùng statement/transaction** đơn giản và an toàn hơn.

### 6.3. Backfill theo batch và chỉ nhận giá trị hợp lệ

Ví dụ PostgreSQL dùng CTE để chọn tối đa 500 hàng chưa chuyển, khóa hàng theo từng batch và bỏ qua hàng đang được worker khác khóa:

~~~sql
WITH batch AS (
    SELECT order_id,
           CASE
               WHEN amount_text IS NOT NULL
                AND btrim(amount_text) ~ '^[0-9]+$'
               THEN btrim(amount_text)::NUMERIC
               ELSE NULL
           END AS parsed_amount
    FROM legacy_orders
    WHERE total_amount_vnd IS NULL
      AND currency_code = 'VND'
    ORDER BY order_id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE legacy_orders AS o
SET total_amount_vnd = b.parsed_amount::BIGINT
FROM batch AS b
WHERE o.order_id = b.order_id
  AND b.parsed_amount BETWEEN 0 AND 9223372036854775807
  AND o.total_amount_vnd IS NULL
RETURNING o.order_id, o.total_amount_vnd;
~~~

Đoạn này là **một batch**, cần chạy nhiều lần với transaction và bộ điều phối có kiểm soát. Lưu ý:

- Dòng null/sai định dạng/overflow hoặc không có currency_code = VND được **bỏ qua**, không chuyển thành 0 hoặc giả làm VND.
- Các dòng không chuyển được phải có **bảng/đầu ra ngoại lệ** và người xử lý.
- SKIP LOCKED tránh đợi những dòng đang bị khóa nhưng không có nghĩa chúng sẽ không bao giờ phải xử lý; lần sau cần quay lại.
- Batch phải ngắn, theo dõi số hàng, thời gian khóa, WAL và replication lag.
- Điều kiện o.total_amount_vnd IS NULL giảm nguy cơ ghi đè giá trị mới, **nhưng không tự đảm bảo nhất quán** nếu writer đồng thời sửa amount_text mà không cập nhật cột mới.
- Nếu mọi hàng còn lại đều là ngoại lệ, cứ chạy tiếp vô hạn không giải quyết được; cần phân loại và sửa nguồn.

Không được coi truy vấn minh họa này là một công cụ migration sản xuất đã kiểm thử. Phải có chiến lược chạy/retry/log, transaction boundary, rate limiting và hợp đồng dual-write trước khi sử dụng.

### 6.4. Đối soát sau khi chuyển kiểu

~~~sql
-- Các chuỗi hợp lệ nhưng chưa có số mới hoặc khác số mới.
WITH candidates AS (
    SELECT order_id, amount_text, total_amount_vnd, currency_code,
           CASE
               WHEN currency_code = 'VND'
                AND amount_text IS NOT NULL
                AND btrim(amount_text) ~ '^[0-9]+$'
               THEN btrim(amount_text)::NUMERIC
               ELSE NULL
           END AS parsed
    FROM legacy_orders
)
SELECT order_id, amount_text, total_amount_vnd, parsed
FROM candidates
WHERE parsed BETWEEN 0 AND 9223372036854775807
  AND (
      total_amount_vnd IS NULL
      OR total_amount_vnd::NUMERIC <> parsed
  )
ORDER BY order_id
LIMIT 100;
~~~

Câu truy vấn đối soát này chỉ so sánh những hàng tiền gốc **được xác nhận là VND**; hàng currency_code NULL/khác VND phải được phân loại riêng theo chính sách nghiệp vụ. Cần kiểm tra cả:

- Số row đã backfill / chưa backfill / không chuyển được.
- Chênh lệch theo tenant, nguồn, tháng và trạng thái.
- Giá trị âm nếu có nghiệp vụ refund cần tách.
- Tổng tiền theo **định nghĩa gốc và mới**, không so những nhóm không có cùng phạm vi.
- Những bản ghi được chỉnh sửa sau khi bắt đầu backfill.

Nếu phiên bản cũ vẫn ghi amount_text một mình, một lần đối soát “0 lỗi” không bảo đảm trạng thái sẽ giữ nguyên vào phút tiếp theo. Chỉ tuyên bố sẵn sàng cutover khi **đường ghi mới đã thực sự bảo vệ hợp đồng mới**.

## 7. Siết CHECK theo hai giai đoạn

Một CHECK đơn giản về số tiền:

~~~sql
ALTER TABLE legacy_orders
ADD CONSTRAINT ck_orders_amount_nonnegative
CHECK (total_amount_vnd >= 0)
NOT VALID;
~~~

Ở PostgreSQL, **NOT VALID đối với CHECK** cho phép thêm constraint mà chưa quét toàn bộ dữ liệu cũ để xác minh ngay. Các hàng được INSERT/UPDATE sau khi constraint được thêm vẫn phải tuân theo CHECK. Những hàng cũ chưa được validate có thể còn vi phạm.

Khi dữ liệu đã được làm sạch:

~~~sql
ALTER TABLE legacy_orders
VALIDATE CONSTRAINT ck_orders_amount_nonnegative;
~~~

VALIDATE kiểm tra các hàng còn lại theo quy tắc; nếu thất bại, cần xử lý bản ghi vi phạm rồi chạy lại. Nó có thể tiêu tốn I/O và cần lock, nhưng thường tránh một số mức blocking của cách thay đổi trực tiếp; **không đồng nghĩa lock-free hoặc không có ảnh hưởng vận hành**.

### 7.1. CHECK không thay NOT NULL

Với CHECK:

~~~sql
CHECK (total_amount_vnd >= 0)
~~~

một hàng có total_amount_vnd = NULL không nhất thiết bị từ chối, vì biểu thức CHECK không trả FALSE. Nếu yêu cầu số tiền bắt buộc có mặt, phải bảo vệ **tính có giá trị**:

~~~sql
-- Chỉ làm sau khi dữ liệu và mọi writer đã đáp ứng.
ALTER TABLE legacy_orders
ALTER COLUMN total_amount_vnd SET NOT NULL;
~~~

Trên bảng lớn, SET NOT NULL có thể cần khóa và scan để chứng minh không có NULL, tùy DBMS/phiên bản và những constraint đã xác minh. Một số phiên bản PostgreSQL có thể tận dụng CHECK đã validate để giảm chi phí chứng minh NOT NULL, nhưng vẫn phải đánh giá lock/DDL thực tế.

Có thể dọn dẹp theo lộ trình:

~~~sql
ALTER TABLE legacy_orders
ADD CONSTRAINT ck_orders_amount_present
CHECK (total_amount_vnd IS NOT NULL)
NOT VALID;

-- Chỉ sau khi NULL đã được xử lý:
ALTER TABLE legacy_orders
VALIDATE CONSTRAINT ck_orders_amount_present;

-- Thực thi trong cửa sổ được phê duyệt:
ALTER TABLE legacy_orders
ALTER COLUMN total_amount_vnd SET NOT NULL;
~~~

Đây là **một kỹ thuật chuẩn bị**, không phải bảo đảm SET NOT NULL có thể chạy không khóa trong mọi phiên bản.

### 7.2. Siết miền giá trị có yêu cầu mapping chính xác

Ví dụ status mới phải thuộc ba trạng thái:

~~~sql
ALTER TABLE legacy_orders
ADD CONSTRAINT ck_orders_status_allowed
CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
NOT VALID;
~~~

Nhưng status NULL vẫn cần xử lý riêng. Trước khi UPDATE hàng loạt **DONE → PAID**, phải xác minh DONE có nghĩa “đã thanh toán” hay chỉ “đã hoàn tất nhập đơn”. Nếu mapping sai, hệ thống có thể công bố doanh thu đã thanh toán dù chưa thu tiền.

Nên có bảng mapping có hiệu lực theo **nguồn và phiên bản nghiệp vụ**, đồng thời giữ nhật ký những hàng không phân loại được. Việc lựa chọn UNKNOWN hay quarantine phải được phê duyệt; không dùng giá trị mặc định làm cách che khuất dữ liệu sai.

## 8. Siết FOREIGN KEY theo phạm vi tenant

Khi Order và Customer cùng thuộc tenant, một FK chỉ trên customer_id là sai nếu customer_id có thể lặp giữa tenant. Khóa đúng trong mô hình ca học:

~~~sql
ALTER TABLE legacy_orders
ADD CONSTRAINT fk_orders_customer_same_tenant
FOREIGN KEY (tenant_id, customer_id)
REFERENCES customer_accounts(tenant_id, customer_id)
NOT VALID;
~~~

Bảng customer_accounts có PRIMARY KEY(tenant_id, customer_id) nên có thể làm đích cho FK ghép.

Các bước đúng:

1. Profile số dòng Order có customer_id NULL.
2. Phát hiện Order có customer_id khác NULL nhưng **không có Customer cùng tenant**.
3. Quy định cách xử lý Customer đã bị xóa, tài khoản khách vãng lai và bản ghi di trú.
4. Bảo đảm writer mới tạo Customer trước/đúng transaction khi cần.
5. ADD FK NOT VALID, tránh phải xác minh mọi hàng cũ ngay.
6. Làm sạch/backfill; chạy VALIDATE.
7. Nếu customer_id bắt buộc, áp NOT NULL **sau một quyết định nghiệp vụ riêng**.

~~~sql
ALTER TABLE legacy_orders
VALIDATE CONSTRAINT fk_orders_customer_same_tenant;
~~~

**FK chưa ép customer_id NOT NULL.** Trong trường hợp khóa ghép (tenant_id, customer_id), tenant_id không NULL nhưng customer_id NULL, FK theo MATCH SIMPLE có thể không kiểm tra tham chiếu. NOT NULL giải quyết phần tồn tại bắt buộc, nhưng không thể tự quyết định một đơn guest có được phép tồn tại hay không.

### 8.1. FK không nhất thiết tự tạo index phía con

PostgreSQL không mặc định tạo index cho mọi cột FK phía bảng con. Nếu truy vấn JOIN Order theo Customer và xóa/sửa Customer có kiểm tra tham chiếu, có thể cân nhắc:

~~~sql
-- Trên bảng đang hoạt động cần chọn thời điểm và theo dõi tài nguyên.
CREATE INDEX CONCURRENTLY idx_orders_customer_tenant
ON legacy_orders (tenant_id, customer_id);
~~~

Đo query plan và chi phí ghi; không thêm index chỉ vì có FK. **CREATE INDEX CONCURRENTLY không được chạy trong transaction block PostgreSQL**; công cụ migration phải tạo pha DDL phù hợp.

## 9. Siết UNIQUE nhưng không làm mất bản ghi hợp lệ

Giả sử external_reference mới phải duy nhất **trong tenant**. Trước khi thêm UNIQUE, cần phân biệt:

- Một đơn bị **nạp hai lần** cùng external_reference: có thể merge sau khi đối soát order lines/payment.
- Hai đơn hợp lệ cùng reference do các hệ nguồn khác nhau: có thể cần khóa **(tenant_id, source_system, external_reference)** thay vì khóa hai cột.
- Reference NULL: cho phép đơn tạo thủ công hay bắt buộc mọi đơn có reference?
- Reference khác kiểu chữ hoặc dấu cách: có cần chuẩn hóa, có làm hai giá trị trở nên cùng một business ID không?

### 9.1. Không tự xóa bản ghi trùng

~~~sql
SELECT tenant_id, external_reference,
       COUNT(*) AS row_count,
       ARRAY_AGG(order_id ORDER BY order_id) AS order_ids
FROM legacy_orders
WHERE external_reference IS NOT NULL
GROUP BY tenant_id, external_reference
HAVING COUNT(*) > 1;
~~~

Không dùng DELETE giữ MIN(order_id) nếu các Order trùng còn có Payment, Shipment hoặc Refund khác nhau. Cần xác định định danh nguồn, cách merge/alias, FK cần chuyển, lịch sử và khả năng truy vết.

### 9.2. Tạo unique index theo cách ít chặn ghi hơn

Khi dữ liệu đã sạch và writer mới không phát sinh duplicate:

~~~sql
-- Chạy ngoài transaction block, trong một bước migration riêng.
CREATE UNIQUE INDEX CONCURRENTLY idx_orders_tenant_external_ref
ON legacy_orders (tenant_id, external_reference);
~~~

PostgreSQL UNIQUE thông thường cho phép nhiều NULL đối với external_reference; nếu muốn cấm NULL, cần NOT NULL độc lập. Nếu thành công, có thể gắn index thành một constraint khi index đáp ứng điều kiện sử dụng:

~~~sql
ALTER TABLE legacy_orders
ADD CONSTRAINT uq_orders_tenant_external_ref
UNIQUE USING INDEX idx_orders_tenant_external_ref;
~~~

**Không dùng index partial/expression rồi kỳ vọng gắn thành UNIQUE constraint bằng USING INDEX**; kiểu index và constraint có các điều kiện khác nhau. **CREATE UNIQUE INDEX CONCURRENTLY** có thể thất bại vì duplicate phát sinh đồng thời và để lại index không hợp lệ; cần kiểm tra catalog và kế hoạch cleanup/retry. Nó không tự giải quyết mọi vấn đề transaction/lock.

### 9.3. Uniqueness theo thời gian hay toàn vòng đời?

Một coupon có thể “chỉ một lần đang hoạt động”, nhưng vẫn cho phép lịch sử nhiều lượt thất bại. Một username có thể được tái sử dụng sau khi account bị xóa mềm hay không. Một email có thể duy nhất theo tenant nhưng không toàn hệ.

Nếu chỉ UNIQUE(active records), cần xác định **predicate**, quyền chuyển trạng thái và xử lý concurrent transitions. Một unique index partial có thể phù hợp, nhưng invariant phải được viết đúng trước khi chọn kỹ thuật. Không đánh đồng “unique hiện hành” với “chưa từng trùng trong lịch sử”.

## 10. So sánh bốn loại constraint khi siết dần

| Constraint | Bảo vệ | Dữ liệu cũ phải kiểm tra | PostgreSQL và lưu ý |
| --- | --- | --- | --- |
| **NOT NULL** | Cột bắt buộc có giá trị | COUNT NULL | SET NOT NULL sau khi backfill; đánh giá scan/lock |
| **CHECK** | Điều kiện cục bộ trên hàng | Hàng vi phạm điều kiện; NULL theo 3-valued logic | Có NOT VALID và VALIDATE |
| **FOREIGN KEY** | Tham chiếu tới khóa cha | Orphan, scope tenant và NULL | Có NOT VALID/VALIDATE; index con không tự có |
| **UNIQUE** | Không có hai khóa tương đương trong scope | Duplicate và quy tắc NULL | Dùng unique index concurrently theo điều kiện; không có lộ trình NOT VALID như CHECK/FK |
| **PRIMARY KEY** | Định danh hàng duy nhất và không NULL | Duplicate/NULL | Chọn khóa nghiệp vụ/surrogate đúng grain, xét partition |

**Sai lầm thường gặp:** nghĩ rằng thêm NOT VALID rồi chờ công việc nền chạy xong là constraint tự động validate. Trong PostgreSQL, cần gọi **VALIDATE CONSTRAINT** riêng theo kế hoạch. Bảng có constraint chưa validated vẫn cần được theo dõi và công bố trạng thái migration rõ ràng.

**Sai lầm khác:** tin UNIQUE(tenant_id,external_reference) bảo vệ uniqueness toàn hệ. Nó chỉ bảo vệ uniqueness trong tenant. Muốn global uniqueness trong hệ sharding thực sự có nhiều database, cần một owner/registry hoặc cơ chế nhất quán xuyên shard; UNIQUE trong mỗi shard không đủ.

## 11. Khả năng tương thích của ứng dụng trong thời gian chuyển đổi

Một schema migration thành công chưa đủ nếu version ứng dụng còn chạy không tương thích.

| Giai đoạn | Reader cũ | Writer cũ | Reader mới | Writer mới |
| --- | --- | --- | --- | --- |
| Expand cột mới nullable | Tiếp tục đọc cột cũ | Có thể tiếp tục nếu schema cho phép | Có thể thử đọc mới rồi fallback có kiểm soát | Có thể dual-write |
| Backfill | Tiếp tục hoạt động | **Nguy cơ tạo divergence** nếu chỉ ghi cột cũ | Cần kiểm tra tính nhất quán | Ghi cả hai theo contract |
| Cutover | Phải được rút hoặc nâng cấp | **Không được còn ghi sai** | Đọc cột canonical mới | Ghi canonical mới |
| Contract bỏ cột cũ | Có thể vỡ | Có thể vỡ | Hoạt động nếu độc lập cột cũ | Hoạt động nếu hợp đồng đầy đủ |

### 11.1. Schema version và hợp đồng API

Một thuộc tính có thể xuất hiện ở nhiều nơi:

- Cột trong database.
- Trường JSON của API.
- Trường trong sự kiện Kafka/CDC.
- Model của ORM.
- Schema Avro/Protobuf hoặc kho schema của tổ chức.
- Bảng data warehouse và dashboard.
- Script batch nhập xuất.

**Thêm cột database không tự thêm trường API.** Ngược lại, một reader API yêu cầu field mới non-null có thể lỗi dù database đã thêm cột nullable và backfill đang chạy. Cần mô tả tương thích ở từng lớp.

### 11.2. Không coi COALESCE là giải pháp lâu dài

Trong giai đoạn chuyển đổi, một query có thể đọc:

~~~sql
-- MINH HỌA bridge khi hai giá trị đã có chính sách thống nhất.
SELECT order_id,
       COALESCE(total_amount_vnd,
                CASE
                    WHEN currency_code = 'VND'
                     AND amount_text IS NOT NULL
                     AND btrim(amount_text) ~ '^[0-9]+$'
                    THEN btrim(amount_text)::NUMERIC
                    ELSE NULL
                END) AS amount_value
FROM legacy_orders;
~~~

Nhưng ví dụ trên có thể trả về NUMERIC và chưa loại overflow. Nó **không phải** hợp đồng kiểu mới cuối cùng; hơn nữa, fallback có thể che lỗi backfill và tạo kết quả khác ở từng reader. Để xuất bản KPI, nên dùng **bảng/quan điểm canonical đã được kiểm định**; chỉ dùng fallback có kiểm soát trong khoảng tương thích.

### 11.3. Một nguồn sự thật và việc chuyển quyền ghi

Trong khi dual-write, cần biết cột nào là **authoritative**:

- Khi nguồn cũ là chủ, total_amount_vnd là projection được làm mới.
- Khi nguồn mới là chủ, amount_text chỉ là representation dành cho client cũ.
- Tại cutover, quyền ghi mới phải chuyển có kiểm soát, tránh hai writer tự sửa hai cột theo hai quy tắc khác nhau.

Nếu dùng trigger để đồng bộ, cần thiết kế rõ hướng cập nhật, kiểm tra lỗi parse, tránh recursion và xử lý xung đột. Không thêm trigger tự động “cái nào vừa đổi thì ghi đè cái kia” nếu không có quy tắc chọn nguồn sự thật.

## 12. Chuyển đổi dữ liệu có ảnh hưởng tới ngữ nghĩa: không chỉ TEXT → BIGINT

Một số thay đổi có thể nhìn như đổi kiểu nhưng thực chất là **đổi mô hình nghiệp vụ**.

### 12.1. Tiền tệ, tỷ giá và đơn vị nhỏ nhất

Trong ca Orders, cột mới **total_amount_vnd** tuy là BIGINT nhưng chỉ có nghĩa khi số tiền thực sự là VND nguyên đồng. Nếu hàng cũ có currency_code = USD, không được đặt giá trị amount_text = 100 thành 100 VND.

Những hướng xử lý đúng tùy nghiệp vụ:

- Giữ **amount_minor_units BIGINT + currency_code** với đơn vị nhỏ nhất tương ứng từng tiền tệ, có danh mục currency.
- Dùng **NUMERIC(p,s)** nếu yêu cầu số thập phân có độ chính xác cố định.
- Nếu cần một chỉ tiêu VND quy đổi, lưu **tỷ giá, nguồn tỷ giá và thời điểm áp dụng**, phân biệt số tiền gốc và số quy đổi.
- Quarantine bản ghi không xác định đơn vị thay vì tự quy đổi.

Một bảng giao dịch đa tiền tệ không thể được “chuẩn hóa” bằng cách gắn hậu tố _vnd vào cột mà không có quy trình chuyển đổi.

### 12.2. Thay đổi định nghĩa trạng thái

Giả sử trạng thái cũ DONE có nghĩa “đã xử lý xong” còn trạng thái mới PAID có nghĩa “đã thanh toán”. Đây không phải mapping 1–1. Để sửa cần biết thông tin Payment hoặc event lịch sử.

~~~text
OLD: DONE
     /    \
  đã trả   chưa trả
     \    /
NEW: PAID hoặc PENDING/COMPLETED_UNPAID tùy domain
~~~

Một CHECK cho phép PENDING/PAID/CANCELLED không tự giải quyết sự thiếu hụt ngữ nghĩa này. Có thể cần **tách payment_status khỏi fulfillment_status**, thay vì ép hai tiến trình vào một cột status.

### 12.3. Chuyển timestamp và timezone

Một cột TEXT ghi 2026-11-22 08:00 không xác định một instant nếu không biết múi giờ của nguồn. Đổi trực tiếp sang TIMESTAMPTZ theo timezone session có thể tạo thời điểm khác nhau giữa các môi trường.

Cần xác định:

- Dữ liệu cũ lưu UTC, giờ cửa hàng hay giờ máy chủ?
- Có offset hoặc timezone IANA gốc không?
- Có sự kiện trong vùng DST bị lặp/không tồn tại giờ địa phương không?
- Ngày nghiệp vụ dùng múi giờ theo Store hay theo tổ chức?
- Khi không suy ra được instant, có được chọn quy tắc bảo thủ hoặc đánh dấu không xác định?

Chỉ khi quy ước rõ mới viết migration chuyển đổi. Ví dụ, với cột cũ **được xác nhận** là local time Việt Nam:

~~~sql
-- Minh họa cách diễn giải một TIMESTAMP WITHOUT TIME ZONE.
SELECT TIMESTAMP '2026-11-22 08:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh'
       AS observed_instant;
~~~

Đây là một bước đổi **ngữ nghĩa thời gian**, không chỉ đổi kiểu SQL.

### 12.4. Trường ghép thành quan hệ mới

Nếu schema cũ lưu danh sách product IDs trong TEXT/JSON và schema mới yêu cầu OrderLine có FK tới Product, cần tách từng phần tử, xác định grain và chống trùng. Một JSON chứa hai dòng cùng SKU có thể đại diện cho **hai dòng mua hợp lệ**, không nhất thiết là duplicate.

Quy trình phải xác định **định danh dòng**, số lượng, đơn giá lịch sử, khóa và quan hệ; sau đó kiểm tra tính đầy đủ dữ liệu trước khi bỏ cấu trúc cũ.

## 13. Đường ghi đồng thời và nguy cơ sai lệch trong backfill

Một job batch chạy trong vài giờ sẽ gặp dữ liệu đang được sửa cùng lúc. Chỉ việc chia batch nhỏ **không đủ** nếu không có hợp đồng concurrency.

### 13.1. Lịch đua tranh có thể gây sai

~~~text
T1: Job đọc amount_text = "100000"
T2: API sửa amount_text thành "120000" rồi COMMIT
T1: Job ghi total_amount_vnd = 100000
Kết quả: cột cũ 120000, cột mới 100000
~~~

T1 có thể có điều kiện total_amount_vnd IS NULL và vẫn ghi giá trị cũ nếu không khóa/kiểm tra lại đúng cách. CTE FOR UPDATE giúp khóa hàng trong transaction batch, nhưng **sau COMMIT**, writer cũ có thể tiếp tục sửa cột cũ mà không sửa cột mới. Vì vậy cần:

1. Bảo đảm writer đã chuyển sang ghi **hai biểu diễn cùng nhau** hoặc chỉ ghi canonical mới theo quy tắc.
2. Dùng transaction và hàng khóa phù hợp trong batch, hoặc optimistic check trên phiên bản/cột nguồn.
3. Có cơ chế phát hiện/khắc phục divergence trước cutover.
4. Đối soát liên tục trong khi backfill và trong giai đoạn ứng dụng chuyển dần.

### 13.2. Batch cần checkpoint và idempotency

Một batch được coi là an toàn khi chạy lại không tạo sai số mới. Ví dụ backfill NULL bằng giá trị xác định có thể idempotent nếu mọi điều kiện đúng; nhưng chuyển số tiền bằng **cộng dồn** thay vì gán giá trị sẽ nhân số khi retry.

Lưu metadata lần chạy ở hệ thống triển khai hiện có hoặc trong nhật ký migration được phép, gồm:

- Migration/version và tập khóa đã xử lý.
- Số hàng thành công, bỏ qua, lỗi và mã lỗi.
- Thời điểm, kích thước batch, thời gian commit.
- Dải PK hoặc cursor nếu dùng phân đoạn, lưu ý các hàng đến muộn/được sửa sau cursor.
- Checkpoint và cách quét lại những hàng chưa đủ điều kiện ở lần trước.

Nếu áp migration đồng thời trên nhiều worker, **SKIP LOCKED** giúp giảm đợi khóa nhưng không thay thế cơ chế xác nhận dữ liệu đã chuyển đúng hoặc xử lý các hàng đang bị bỏ qua.

### 13.3. Không khóa bảng dài chỉ vì tiện lập trình

Một lệnh UPDATE hàng triệu dòng trong một transaction có thể:

- Giữ row locks lâu và làm tăng chờ.
- Tạo lượng WAL lớn và replication lag.
- Tăng áp lực vacuum và bloat.
- Làm khó pause/resume và rollback.
- Gây timeout cho API quan trọng.

Chọn batch theo **kết quả đo**, không cố định 500 cho mọi bảng. Có thể khởi đầu với batch nhỏ, đo latency/lag, nâng hoặc hạ theo SLO, và tạm ngừng khi hệ thống bị quá tải.

### 13.4. Kiểm soát batch bị kẹt

Nếu còn 100 bản ghi NULL nhưng không thể parse, job chỉ quét lặp chúng sẽ tốn tài nguyên mà không tiến triển. Cần một bảng/danh sách lỗi với lý do như INVALID_FORMAT, OVERFLOW, UNKNOWN_CURRENCY, MISSING_CUSTOMER hoặc SOURCE_CONFLICT.

Quy trình sửa dữ liệu phải xác định ai được quyền xác nhận giá trị mới. Nếu cột tiền có giá trị không hợp lệ, không dùng 0 hoặc giá trị mặc định vô nghĩa để đạt NOT NULL rồi coi như đã hoàn thành.

## 14. Zero-downtime là mục tiêu cần đo, không phải thuộc tính của một cú pháp

Một số thao tác DDL trông ngắn nhưng vẫn có thể đợi lock. Cần tách:

- **Thời gian câu lệnh chạy** trên database thử.
- **Thời gian chờ lấy lock** khi production có transaction dài.
- **Ảnh hưởng tới writer/reader** đang chạy.
- **Phần dữ liệu cần scan/rewrite** và dung lượng/WAL.
- **Cơ chế rollback** nếu migration thất bại giữa chừng.

Ví dụ PostgreSQL có thể dùng timeout để fail sớm thay vì chờ lock quá lâu:

~~~sql
-- Chỉ minh họa trong session migration đã được phê duyệt.
SET lock_timeout = '2s';
SET statement_timeout = '30s';

ALTER TABLE legacy_orders
ADD COLUMN order_channel_note TEXT;
~~~

Một ADD COLUMN thường có thời gian thao tác ngắn với loại thay đổi đơn giản, nhưng vẫn có thể cần khóa metadata. Câu lệnh trên **không chứng minh zero downtime** và thêm cột order_channel_note chỉ là một ví dụ thao tác, không phải bước bắt buộc của case Orders.

### 14.1. DEFAULT và các phiên bản PostgreSQL

Việc thêm cột có DEFAULT hằng số và cách DBMS lưu giá trị cho hàng cũ có thể được tối ưu bằng metadata trong một số phiên bản PostgreSQL. Một DEFAULT có biểu thức biến đổi/volatile hoặc thay đổi kiểu khác có thể có chi phí lớn hơn.

Quan trọng về ý nghĩa:

~~~sql
ALTER TABLE legacy_orders
ALTER COLUMN order_channel SET DEFAULT 'UNKNOWN';
~~~

**SET DEFAULT chỉ áp cho những INSERT sau đó không cung cấp cột**; nó không phải câu lệnh làm sạch mọi NULL cũ. Hơn nữa, một INSERT chủ động ghi NULL không nhất thiết lấy DEFAULT. Cần phân biệt chính sách ứng dụng, DEFAULT và NOT NULL.

### 14.2. Lập thứ tự DDL phù hợp

Một lịch triển khai tham khảo:

| Pha | Thay đổi | Tiêu chí đi tiếp |
| --- | --- | --- |
| A | Cột mới nullable, code đọc mới/cũ | Không lỗi đọc/ghi |
| B | Ghi song song hoặc compatibility writer | Không phát sinh divergence mới |
| C | Backfill với checkpoint và ngoại lệ | Dữ liệu hợp lệ được chuyển đầy đủ |
| D | CHECK/FK NOT VALID và validation | Không vi phạm trong phạm vi cam kết |
| E | Unique index concurrently | Không duplicate; index hợp lệ |
| F | SET NOT NULL, chuyển reader hoàn toàn | Không NULL và không writer cũ |
| G | Bỏ cột cũ sau thời gian chờ | Có phương án khôi phục đã duyệt |

Đây không phải lịch chạy một transaction. **CREATE INDEX CONCURRENTLY** trong PostgreSQL không được đặt trong transaction block, trong khi một số bước ALTER TABLE có thể được gom theo kế hoạch khác. Không dùng “một file SQL bao mọi thứ trong BEGIN/COMMIT” mà không xét đặc tính từng lệnh.

## 15. Kiểm thử migration theo ba cấp

### 15.1. Kiểm thử schema và constraint

Tối thiểu phải thử:

- INSERT hàng hợp lệ có được chấp nhận không?
- INSERT NULL vào cột NOT NULL bị từ chối không?
- INSERT amount âm hoặc status ngoài miền bị từ chối không?
- Order trỏ Customer khác tenant bị từ chối không?
- Hai Order cùng tenant trùng external_reference có bị từ chối không?
- Hai tenant trùng external_reference có được chấp nhận theo quy tắc per-tenant không?
- DELETE/UPDATE Customer còn Order tham chiếu hoạt động theo chính sách nào?
- Những writer cũ còn dùng INSERT không khai báo danh sách cột có bị lỗi không?

Đừng dùng test chỉ chứng minh “ALTER trả mã thành công”.

### 15.2. Kiểm thử dữ liệu hiện hữu

Tạo bộ dữ liệu thử đủ các tình huống:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Amount "100000" và currency VND | Chuyển thành 100000 BIGINT |
| Amount " 100000 " và currency VND | Trim và chuyển theo chính sách |
| Amount "1,000" | Không tự diễn giải nếu chưa có quy tắc locale |
| Amount NULL | Báo missing, không biến thành 0 |
| Amount vượt BIGINT | Quarantine/đổi kiểu/giải quyết nguồn |
| Currency USD nhưng cột mới là VND | Không copy như VND |
| Customer NULL | Xử lý guest policy hoặc sửa dữ liệu |
| Customer khác tenant | Bị phát hiện và xử lý trước FK |
| External reference trùng | Điều tra nguồn, không xóa mù |
| Status DONE/NULL | Mapping có bằng chứng hoặc exception |
| Row đang bị writer sửa trong backfill | Không tạo divergence sau khi commit |
| Retry cùng batch | Không tăng tổng tiền hoặc nhân bản hàng |

### 15.3. Kiểm thử tương thích và tải đồng thời

Một bài test hoàn chỉnh cần giả lập:

1. Ứng dụng cũ đọc trường amount_text.
2. Ứng dụng mới đọc total_amount_vnd.
3. Writer đã nâng cấp ghi hai trường.
4. Job backfill đang chạy đồng thời.
5. Một số tenant có dữ liệu lỗi chưa giải quyết.
6. Constraint bắt đầu từ NOT VALID rồi được VALIDATE.
7. Một bản ghi được sửa đúng lúc job chuyển.
8. Rollback ứng dụng một phiên bản trước khi contract được thực thi.
9. Một transaction dài giữ lock trong lúc migration muốn ALTER.
10. Replication/CDC tiếp nhận lượng thay đổi lớn và phục hồi khi pause/resume.

Kết quả chấp nhận nên được đo bằng **p95/p99 request**, lock wait, throughput, replication lag, số exception, số bản ghi divergence và tính đúng của KPI. Một kết luận “staging chạy nhanh” không chứng minh môi trường production có cùng tài nguyên hay phân bố dữ liệu.

## 16. Đối soát và cổng quyết định cutover

Một phép đo số hàng chưa đủ để khẳng định migration đúng. Ví dụ hai giá trị tiền sai chiều có thể bù nhau ở tổng toàn hệ.

### 16.1. Kiểm tra số NULL và giá trị ngoài miền

~~~sql
SELECT COUNT(*) AS total_orders,
       COUNT(*) FILTER (WHERE total_amount_vnd IS NULL) AS missing_amount,
       COUNT(*) FILTER (WHERE total_amount_vnd < 0) AS negative_amount,
       COUNT(*) FILTER (WHERE order_channel IS NULL) AS missing_channel,
       COUNT(*) FILTER (
           WHERE status IS NULL
              OR status NOT IN ('PENDING','PAID','CANCELLED')
       ) AS status_invalid
FROM legacy_orders;
~~~

Nếu một tập dữ liệu lịch sử **được phép giữ NULL** nhưng dữ liệu mới bắt buộc khác NULL, cần xác định liệu constraint chung có phản ánh đúng quy tắc không. Một CHECK phụ thuộc ngày/loại đơn có thể là thiết kế khác, nhưng phải chứng minh người dùng không suy ra mọi hàng đều đã hoàn chỉnh.

### 16.2. Kiểm tra chênh lệch tiền theo tenant

~~~sql
WITH parsed AS (
    SELECT tenant_id, order_id, amount_text, total_amount_vnd,
           CASE
               WHEN currency_code = 'VND'
                AND amount_text IS NOT NULL
                AND btrim(amount_text) ~ '^[0-9]+$'
               THEN btrim(amount_text)::NUMERIC
               ELSE NULL
           END AS source_amount
    FROM legacy_orders
)
SELECT tenant_id,
       COUNT(*) AS total_rows,
       COUNT(*) FILTER (
           WHERE source_amount BETWEEN 0 AND 9223372036854775807
             AND total_amount_vnd IS NULL
       ) AS not_migrated,
       COUNT(*) FILTER (
           WHERE source_amount BETWEEN 0 AND 9223372036854775807
             AND total_amount_vnd::NUMERIC <> source_amount
       ) AS mismatched,
       SUM(source_amount) FILTER (
           WHERE source_amount BETWEEN 0 AND 9223372036854775807
       ) AS source_total,
       SUM(total_amount_vnd) FILTER (
           WHERE source_amount BETWEEN 0 AND 9223372036854775807
       ) AS migrated_total
FROM parsed
GROUP BY tenant_id
ORDER BY tenant_id;
~~~

Đây là **đối soát trên tập hàng hợp lệ có currency VND**. Nó không thay thế việc xử lý các hàng USD/NULL/sai định dạng; chúng phải xuất hiện trong báo cáo exception riêng, không biến mất khỏi phạm vi bằng cách đặt điều kiện lọc.

### 16.3. Kiểm tra tính toàn vẹn theo business key

~~~sql
SELECT tenant_id, external_reference,
       COUNT(*) AS cnt
FROM legacy_orders
WHERE external_reference IS NOT NULL
GROUP BY tenant_id, external_reference
HAVING COUNT(*) > 1;

SELECT o.tenant_id, o.order_id
FROM legacy_orders AS o
LEFT JOIN customer_accounts AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL;
~~~

Hai tập kết quả nên **rỗng** trước khi áp UNIQUE/FK trong phạm vi bắt buộc. Nếu không rỗng, ghi rõ số bản ghi, nguyên nhân và quyết định xử lý, không chỉ áp constraint rồi đổ lỗi cho database.

### 16.4. Cổng Go / No-Go

Có thể phê duyệt cutover khi:

- Writer cũ không còn được phép ghi representation cũ một mình.
- Dữ liệu cần chuyển đã chuyển hoặc có exception được phê duyệt với scope rõ.
- Tất cả kiểm thử constraint đạt; dữ liệu hiện hữu không vi phạm các bất biến cần cưỡng chế.
- Không có divergence hai cột trong tập được công bố.
- Dashboard và ETL có cùng định nghĩa money/status/customer sau migration.
- Các thao tác schema có thời gian lock/replication lag trong giới hạn.
- Có rollback plan thực tế và điểm **không thể rollback trực tiếp** được chấp thuận.
- Owner nghiệp vụ xác nhận quy tắc mapping và danh sách ngoại lệ.

**Không dùng tỷ lệ hoàn thành 99,9% thay cho quyết định business**. Nếu 0,1% còn lại là những đơn giá trị lớn, sai loại tiền hoặc thuộc hợp đồng pháp lý, chúng có thể quan trọng hơn toàn bộ 99,9% còn lại.

## 17. Rollback và forward-fix khi migration lỗi

Một migration có thể bị gián đoạn ở nhiều pha:

| Lỗi phát hiện | Có thể làm gì? | Điều cần tránh |
| --- | --- | --- |
| ADD COLUMN thất bại trước khi dùng | Retry sau khi giải quyết lock/cấu hình | Kéo dài lock vô hạn |
| Backfill dừng giữa chừng | Tiếp tục từ checkpoint với tính idempotent | Chạy lại phép cộng làm nhân dữ liệu |
| Có bản ghi sai mapping | Quarantine, sửa nguồn, backfill lại chọn lọc | Ghi giá trị mặc định vô nghĩa |
| VALIDATE FK/CHECK thất bại | Làm sạch hàng vi phạm, validate lại | Xóa constraint rồi gọi hoàn tất |
| CREATE UNIQUE INDEX CONCURRENTLY thất bại | Kiểm tra index hợp lệ/chưa hợp lệ, loại duplicate và retry có kiểm soát | Giữ index lỗi không giám sát |
| Reader mới có bug trước contract | Quay reader về cột cũ khi dữ liệu cũ còn được duy trì đồng bộ | Giả định rollback code tự hoàn nguyên mọi hàng |
| Đã DROP cột cũ | Cần forward-fix, phục hồi backup hoặc migration ngược có thể mất mát | Hứa rollback đơn giản |
| Báo cáo sai sau cutover | Dừng xuất bản, đối soát, phiên bản lại báo cáo | Sửa lén số đã công bố |

### 17.1. Rollback ứng dụng khác rollback dữ liệu

Quay về bản build trước **không** tự tạo lại amount_text nếu hệ thống đã bỏ cột đó. Ngược lại, rollback một script ALTER trong transaction có thể hoàn tác DDL trước COMMIT, nhưng không hoàn nguyên các tác động ngoài database hoặc các bước đã commit trước đó.

Nên ghi rõ:

- **Safe rollback window:** còn cả hai cột, writer vẫn giữ đồng bộ.
- **Cutover point:** canonical write chuyển sang cột mới.
- **Irreversible/contract point:** đã bỏ biểu diễn cũ hoặc cho phép giá trị mới không thể biểu diễn bằng kiểu cũ.
- **Restore strategy:** backup, snapshot, logical replay, forward migration và thời gian khôi phục thực tế.

Không để kế hoạch rollback phụ thuộc một cột cũ chưa được ghi cập nhật trong nhiều ngày.

### 17.2. Down migration có thể không tồn tại

Nếu chuyển BIGINT sang INT, giá trị mới vượt phạm vi INT không thể đổi ngược một cách không mất mát. Nếu chuẩn hóa status thành nhiều bảng mới, hợp nhất lại một TEXT cũ có thể mất ngữ nghĩa. Nếu đã merge bản ghi duplicate, muốn “undo” có thể cần giữ mapping và payload lịch sử.

Vì vậy, quy tắc “mọi migration phải có down.sql” không đủ. Điều cần là **phương án phục hồi thực tế** với dữ liệu đã phát sinh sau cutover.

## 18. Trường hợp dữ liệu đang phân vùng hoặc phân tán

Schema evolution ở hệ có partition/shard tạo thêm giới hạn:

- UNIQUE trên bảng partitioned có thể cần partition key; global uniqueness không tự có.
- Backfill theo tenant/time partition có thể hoàn tất không đồng đều.
- Một shard đang chạy schema version khác có thể phát sinh lỗi khi routing thay đổi.
- Event CDC có thể chứa cả old/new schema; consumer cần tương thích.
- Các FK xuyên database độc lập không tự hoạt động như FK nội bộ.
- Có thể cần dual-read/dual-write giữa mô hình cũ và mới nhưng phải có owner và fencing tránh split-brain.

Ví dụ khi thêm cột mới vào tất cả shard, hãy ghi **schema version khả dụng tại mỗi shard**. Đừng chuyển traffic tới shard mới chưa nhận schema rồi cho rằng retry sẽ giải quyết. Một chiến lược rollout có thể triển khai **read compatibility trước, mở schema, sau đó writer mới, backfill, siết constraint và contract** theo từng cụm, với quy tắc rõ khi một request đi giữa hai cụm.

Nếu một UNIQUE theo tenant được triển khai trên nhiều shard, phải bảo đảm mọi bản ghi cùng tenant/khóa được route tới cùng nơi có cơ chế cưỡng chế uniqueness, hoặc có registry toàn cục. Không suy ra rằng UNIQUE trong mỗi database độc lập tạo một invariant toàn hệ.

## 19. Document, graph và warehouse cũng có schema evolution

### 19.1. Document: trường có thể vắng và hình dạng khác nhau

Một document cũ:

~~~json
{
  "orderId": "O-901",
  "amount": "200000",
  "status": "DONE"
}
~~~

Document mới:

~~~json
{
  "orderId": "O-901",
  "totalAmountVnd": 200000,
  "currencyCode": "VND",
  "paymentStatus": "PAID",
  "fulfillmentStatus": "SHIPPED",
  "schemaVersion": 2
}
~~~

Thêm trường document không yêu cầu ALTER TABLE theo cách của relational DB, nhưng các document cũ vẫn thiếu field mới. Truy vấn, index, validator, consumer và logic application phải biết **version** và quy tắc chuyển.

Không tự suy ra DONE = PAID và SHIPPED như JSON minh họa; chỉ chuyển khi nguồn có bằng chứng. Document validator mới có thể từ chối document cũ khi chúng được cập nhật nếu chưa có lộ trình compatibility/backfill.

### 19.2. Graph: đổi loại cạnh hoặc ràng buộc phân cấp

Ví dụ hệ dữ liệu cũ dùng cạnh:

~~~text
Employee -[REPORTS_TO]-> Manager
~~~

Sau đó bổ sung phân quyền theo vai trò và thời gian hiệu lực:

~~~text
Employee -[REPORTS_TO {valid_from, valid_to}]-> Manager
Employee -[ACTS_AS   {role, valid_from, valid_to}]-> Organization
~~~

Khi tiến hóa, phải xác định:

- Mỗi Employee có thể có nhiều Manager tại cùng instant không?
- Các khoảng REPORTS_TO được phép chồng lấp không?
- Có cho phép chu trình trong đồ thị tổ chức không?
- Khi đổi loại cạnh, truy vấn traversal cũ có còn đúng?
- Với node/cạnh phân vùng, constraint có bảo vệ được toàn đồ thị hay chỉ subgraph?

Đổi schema đồ thị không chỉ là đổi nhãn; phải kiểm kê các edge cũ, dữ liệu thiếu thuộc tính thời gian và rủi ro nhân kết quả khi nhiều đường dẫn hợp lệ.

### 19.3. Warehouse: cột mới không đồng nghĩa KPI mới đã đầy đủ

Nếu thêm chiều OrderChannel vào FactSales, dữ liệu trước năm 2026 có thể thiếu channel. Dashboard không nên tự chia mọi doanh thu lịch sử vào WEB. Cần thể hiện **UNKNOWN**, coverage và thời gian bắt đầu đầy đủ dữ liệu.

Nếu thay đổi định nghĩa measure NetSales, phải xác định có **restatement** kỳ cũ hay tạo measure/version mới. Khi materialized view hoặc bảng tổng hợp đã lưu giá trị cũ, cần backfill/refresh theo phạm vi ảnh hưởng; không chỉ đổi công thức SQL trong dashboard rồi quên bảng dẫn xuất.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| ALTER trước khi profile | DDL fail hoặc dữ liệu bị đổi sai | Đo NULL, duplicates, overflow, orphan, skew |
| Thêm NOT NULL ngay trên bảng nóng | Writer cũ và hàng cũ không đáp ứng | Nullable → writer → backfill → validate → NOT NULL |
| Tự thay NULL bằng 0 | Che thiếu dữ liệu, sai tiền/KPI | Unknown/quarantine và quyết định nghiệp vụ |
| Đổi TEXT sang BIGINT không xét currency | USD bị lưu như VND | Định nghĩa đơn vị, conversion và nguồn |
| Mapping DONE thành PAID không có bằng chứng | Báo cáo công bố doanh thu không đúng | Tách trạng thái hoặc mapping có xác minh |
| Backfill một lần rồi bỏ cột cũ | Writer cũ tiếp tục ghi cột cũ | Phối hợp writer/trigger/dual-write và đối soát |
| Tin CHECK ép NOT NULL | NULL có thể thỏa CHECK theo logic ba trị | CHECK IS NOT NULL/NOT NULL riêng |
| Tin FK ghép luôn kiểm tra khi một thành phần NULL | Có thể bỏ kiểm tra vì MATCH SIMPLE | NOT NULL theo scope nghiệp vụ |
| Tin UNIQUE trong mỗi shard là global UNIQUE | Trùng giữa shard | Đổi routing/registry/global owner |
| Dùng NOT VALID cho UNIQUE/PK như CHECK | Kế hoạch DDL không hợp lệ | Unique index concurrently và kiểm tra kết quả |
| Chạy CREATE INDEX CONCURRENTLY trong BEGIN | PostgreSQL từ chối | Tách pha migration độc lập |
| Bỏ qua invalid index sau lỗi | Tốn tài nguyên hoặc gây khó triển khai lại | Kiểm tra catalog, dọn dẹp an toàn |
| Một UPDATE cực lớn trong một transaction | Lock/WAL/replication lag cao | Batch, checkpoint và rate limit |
| Không thử dữ liệu hot/điểm biên | Hệ thật lỗi dù staging pass | Bộ dữ liệu và tải đại diện |
| Đếm hàng bằng nhau rồi cho là đúng | Hai sai lệch có thể bù nhau | Đối soát theo business key và phân nhóm |
| Chỉ có down.sql mà không có backup | Mất dữ liệu mới sau contract | Restore/forward-fix và điểm không thể quay lại |
| Bỏ cột ngay sau khi deploy reader mới | Batch/CDC/worker cũ còn dùng | Kiểm kê toàn bộ consumer và thời gian tương thích |

## 21. Bài tập tình huống có hướng dẫn giải

### Bài 1. Thêm thuộc tính bắt buộc

**Đề bài:** Bảng Orders có 10 triệu hàng. Product muốn thêm order_channel NOT NULL cho tất cả hàng. Nguồn cũ không lưu thông tin kênh. Nên làm gì?

**Gợi ý giải:** Thêm nullable, xác định liệu UNKNOWN có được chấp nhận về nghiệp vụ, cập nhật writer mới, backfill những hàng có bằng chứng, đo coverage. Chỉ áp NOT NULL khi mọi hàng trong scope có giá trị hợp lệ và các writer không sinh NULL. Không gán mặc định WEB cho mọi lịch sử.

### Bài 2. Kiểm tra chuỗi tiền

**Đề bài:** amount_text chứa "1000", " 1000 ", "1,000", "-50", NULL. Có thể chuyển thẳng sang BIGINT bằng CAST không?

**Gợi ý giải:** Không. Phải profile và định nghĩa ý nghĩa của dấu phẩy, dấu âm, đơn vị và NULL. Chỉ convert các chuỗi hợp lệ theo chính sách, còn lại đưa vào danh sách ngoại lệ cần quyết định.

### Bài 3. Siết CHECK chưa có NOT NULL

**Đề bài:** Thêm CHECK(total_amount_vnd >= 0) rồi phát hiện hàng NULL vẫn tồn tại. Có phải PostgreSQL lỗi không?

**Gợi ý giải:** Không. CHECK không bắt biểu thức luôn TRUE theo cách xử lý NULL; NULL có thể không bị từ chối. Cần thêm NOT NULL sau khi làm sạch dữ liệu hoặc CHECK IS NOT NULL và validate theo lộ trình.

### Bài 4. Thêm FOREIGN KEY theo tenant

**Đề bài:** Customer ID 101 tồn tại ở tenant 1 và tenant 2. Order tenant 1 lưu customer_id 101. FK chỉ trên customer_id có đủ bảo vệ cùng tenant không?

**Gợi ý giải:** Không. Phải dùng FK (tenant_id,customer_id) tới khóa duy nhất tương ứng ở Customer; xử lý NULL/orphan và quy tắc guest order.

### Bài 5. UNIQUE trên reference

**Đề bài:** Hai đơn có external_reference "R001" nhưng thuộc tenant khác nhau. Business chỉ đòi duy nhất trong tenant. Khóa nên chọn thế nào?

**Gợi ý giải:** UNIQUE(tenant_id,external_reference). Không dùng UNIQUE(external_reference) toàn bảng nếu doanh nghiệp cho phép các tenant dùng cùng reference. Cần quy định cách xử lý NULL và nguồn phát ID.

### Bài 6. Trùng ngay khi CREATE INDEX

**Đề bài:** Profile phát hiện không có duplicate, nhưng CREATE UNIQUE INDEX CONCURRENTLY thất bại sau đó. Vì sao?

**Gợi ý giải:** Writer mới có thể tạo duplicate trong thời gian giữa profile và index build, hoặc còn dữ liệu sai chưa được quan sát đầy đủ. Cần bảo vệ đường ghi, điều tra duplicate, kiểm tra index invalid và retry có kiểm soát.

### Bài 7. Writer cũ đang hoạt động

**Đề bài:** Reader mới dùng total_amount_vnd. Một batch cũ chỉ UPDATE amount_text. Backfill đã đạt 100% ngày hôm qua. Có thể bỏ amount_text chưa?

**Gợi ý giải:** Chưa. Batch cũ tạo divergence mới. Cần đổi writer/compatibility, đối soát sau khi ngừng kiểu ghi cũ rồi mới cutover; contract chỉ sau khi mọi consumer không còn phụ thuộc.

### Bài 8. Chạy backfill lại

**Đề bài:** Job dùng UPDATE amount = amount + parsed_amount, chết giữa chừng rồi chạy lại. Rủi ro là gì?

**Gợi ý giải:** Các hàng đã xử lý bị cộng hai lần. Backfill phải idempotent (gán một giá trị xác định, có điều kiện/version), có checkpoint và kiểm tra source payload để restart an toàn.

### Bài 9. Dữ liệu ngoại tệ

**Đề bài:** amount_text "100" có currency_code USD. Cột mới là total_amount_vnd BIGINT. Có nên ghi 100 không?

**Gợi ý giải:** Không. Cần quyết định giữ tiền tệ gốc hoặc quy đổi có nguồn tỷ giá, thời điểm và chính sách làm tròn; 100 USD không phải 100 VND.

### Bài 10. Thay đổi trạng thái

**Đề bài:** Status DONE ở hệ cũ có thể nghĩa là giao hàng xong, còn PAID mới là thanh toán xong. Có được UPDATE tất cả DONE thành PAID không?

**Gợi ý giải:** Không. Hai trạng thái diễn đạt hai quy trình khác nhau. Cần thông tin Payment/fulfillment, có thể tách hai cột/trạng thái rồi chuyển theo bằng chứng.

### Bài 11. VALIDATE CONSTRAINT thất bại

**Đề bài:** ADD FK NOT VALID thành công, nhưng VALIDATE thất bại vì có Customer đã mất. Có nên xóa FK để hoàn thành migration không?

**Gợi ý giải:** Không. Phải xác định cách xử lý orphan, sửa tham chiếu/mapping/guest policy hoặc loại dữ liệu ra khỏi scope theo quyết định nghiệp vụ. Sau đó chạy validate lại; trong thời gian chưa validated phải công bố rõ trạng thái.

### Bài 12. PARTITION theo thời gian

**Đề bài:** Events được partition theo occurred_at. PK(occurred_at,source_event_id) nhưng cùng event có timestamp sai ở hai tháng. Có đảm bảo source_event_id duy nhất không?

**Gợi ý giải:** Không. Khóa ghép khác nhau ở occurred_at nên cả hai bản ghi có thể tồn tại. Cần owner/dedup registry theo event ID trong scope, hoặc cơ chế unique phân tán phù hợp.

### Bài 13. Rollback sau DROP

**Đề bài:** Đã DROP amount_text và nhận một tuần dữ liệu BIGINT mới. Rollback application về bản cũ có phục hồi schema/dữ liệu không?

**Gợi ý giải:** Không tự động. Có thể cần migration ngược, backup/replay hoặc forward-fix, và một số giá trị mới không biểu diễn được ở mô hình cũ. Phải đánh dấu điểm không thể rollback trực tiếp.

### Bài 14. Kiểm thử hiệu năng

**Đề bài:** Migration chạy 2 giây trên 5 nghìn Order ở staging. Production có 100 triệu Order và nhiều transaction dài. Có thể khẳng định không downtime không?

**Gợi ý giải:** Không. Cần kiểm tra lock acquisition, scan/rewrite, WAL, replication lag, batch throughput và hiệu năng API dưới tải có phân bố thực, không suy diễn tuyến tính từ bảng nhỏ.

### Bài 15. Chuyển JSON sang bảng con

**Đề bài:** Một Order document có hai dòng cùng SKU với đơn giá khác nhau. Khi tạo OrderLine dạng quan hệ, có nên dedup theo (order_id,sku_id) không?

**Gợi ý giải:** Không tự động. Hai dòng có thể là hai mục mua hợp lệ. Cần grain dòng và source_line_id/line_no, giữ giá lịch sử, số lượng và kiểm thử tổng trước/sau.

## 22. Checklist nghiệm thu một thay đổi mô hình

- [ ] **Bất biến và ngữ nghĩa mới** được business owner xác nhận: tiền tệ, status, scope khóa, guest policy.
- [ ] **Kiểm kê dữ liệu cũ** có số hàng, NULL, duplicate, orphan, overflow và phân bố theo tenant/source/time.
- [ ] **Những ngoại lệ** có quyết định rõ, không che bằng zero/default hoặc xóa mù.
- [ ] **Expand** không khiến reader/writer hiện hành lỗi ngoài các điều kiện đã định.
- [ ] **Canonical source và dual-write** được xác định; writer cũ không tạo sai lệch không được phát hiện.
- [ ] **Backfill** theo batch, có checkpoint, retry idempotent và kiểm soát transaction/lock.
- [ ] **Ràng buộc** được thêm đúng thứ tự; CHECK/FK NOT VALID được VALIDATE; UNIQUE/PK dùng cơ chế riêng phù hợp.
- [ ] **Tính tương thích** đã kiểm tra cho API, ORM, batch, CDC, event schema, warehouse và dashboard.
- [ ] **Đối soát** theo business key, currency, tenant, kỳ và nguồn đạt tiêu chí.
- [ ] **Concurrency** được thử trong khi vừa ghi vừa chuyển dữ liệu.
- [ ] **Hiệu năng** lock/WAL/replication lag/p95 được đo trên quy mô có tính đại diện.
- [ ] **Cutover** có cổng Go/No-Go, theo dõi lỗi và người phê duyệt.
- [ ] **Rollback/forward-fix** có giới hạn rõ trước/sau contract và backup/restore phù hợp.
- [ ] **Tài liệu mô hình** phản ánh khóa, kiểu, constraint, quy tắc lịch sử, dữ liệu dẫn xuất và phiên bản hợp đồng.

## 23. Ghi nhớ

- **Tiến hóa schema là thay đổi cả dữ liệu và hợp đồng**, không chỉ đổi DDL.
- **Thêm cột không đồng nghĩa dữ liệu cũ có giá trị**. Không tự gán mặc định giả nếu không có bằng chứng nghiệp vụ.
- **Đổi kiểu là đổi cách diễn giải**: kiểm tra đơn vị, độ chính xác, overflow, thời gian và cấu trúc quan hệ trước khi CAST.
- **Siết ràng buộc phải có bằng chứng từ dữ liệu thực**: COUNT NULL, kiểm tra orphan, duplicate, miền giá trị và writer hiện hành.
- **Expand → backfill → validate → contract** giúp chuyển từng bước và giữ cửa tương thích; không phải mọi bước đều nằm trong một transaction.
- **NOT VALID phù hợp cho CHECK/FK ở PostgreSQL**, còn UNIQUE/PK cần quy trình khác; CREATE INDEX CONCURRENTLY không được đặt trong transaction block.
- **Dual-write phải có một nguồn sự thật và được đối soát**. Backfill hoàn tất một lần không bảo đảm writer cũ không làm lệch dữ liệu lại.
- **Rollback ứng dụng khác rollback dữ liệu**; sau khi bỏ biểu diễn cũ hoặc cho phép giá trị mới, có thể chỉ còn phương án forward-fix/restore.
- **Khóa, constraint và dữ liệu dẫn xuất phải được cập nhật đồng bộ theo ngữ nghĩa** trong relational, document, graph và warehouse.

Một migration đáng tin không chỉ kết thúc khi câu lệnh ALTER TABLE thành công. Nó kết thúc khi **dữ liệu lịch sử và dữ liệu mới cùng tuân thủ bất biến được phê duyệt, mọi reader/writer đang hoạt động diễn giải dữ liệu nhất quán, các phép đối soát đạt và hệ thống có thể vận hành hoặc khôi phục trong giới hạn đã công bố**.



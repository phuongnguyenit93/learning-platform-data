# Nguồn có khóa trùng và yêu cầu chọn một bản ghi đại diện

> **Module:** Database SQL  
> **Chương:** Upsert và MERGE  
> **Bài học:** Nguồn có khóa trùng và yêu cầu chọn một bản ghi đại diện

Trong hệ thống đồng bộ dữ liệu, một lô đầu vào rất thường chứa **nhiều bản ghi cùng khóa nghiệp vụ**: một khách hàng được cập nhật nhiều lần, một sản phẩm đổi giá nhiều lần trong ngày, một sự kiện được đối tác gửi lại, hoặc nhiều nguồn cung cấp thông tin mâu thuẫn. Khi đưa dữ liệu đó vào bảng đích bằng **UPSERT** hoặc **MERGE**, câu hỏi không chỉ là “nếu khóa đã tồn tại thì cập nhật, nếu chưa có thì chèn”. Cần trả lời thêm:

**Nếu nguồn có nhiều dòng cho cùng khóa, dòng nào được quyền đại diện cho thực thể đó trong lần cập nhật?**

Một số hệ quản trị từ chối thao tác có nhiều dòng nguồn cùng tác động một hàng đích; hệ khác có thể xử lý theo thứ tự nhưng không hiểu phiên bản nào là đúng. Chọn bản ghi đại diện phải dựa trên **quy tắc nghiệp vụ được nêu tường minh**, thường thực hiện bằng **ROW_NUMBER() OVER(PARTITION BY ... ORDER BY ...)**, sau đó mới MERGE/UPSERT.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt khóa kỹ thuật từng dòng, khóa nghiệp vụ, khóa ghép và ràng buộc UNIQUE/PRIMARY KEY ở đích.
- Phân biệt **trùng khóa ngay trong nguồn** với **xung đột khóa giữa nguồn và đích**.
- Phân loại nguồn trùng do retry, nhiều phiên bản, dữ liệu mâu thuẫn và lỗi chuẩn hóa khóa.
- Nhận diện vì sao DISTINCT, GROUP BY, MAX, RANK và DENSE_RANK thường không đảm bảo một bản ghi đại diện.
- Viết CTE với ROW_NUMBER để lấy **tối đa một dòng đầy đủ cho mỗi khóa** theo thứ tự xác định.
- Thiết kế quy tắc ưu tiên bằng version, thời gian sự kiện, độ tin cậy nguồn, thời gian tiếp nhận và khóa phá hòa.
- Hiểu NULL, collation, case sensitivity, tenant và dữ liệu đến muộn ảnh hưởng việc chọn winner.
- Chuẩn bị nguồn duy nhất trước PostgreSQL ON CONFLICT, SQL Server MERGE, Oracle MERGE, MySQL ON DUPLICATE KEY UPDATE, SQLite UPSERT và BigQuery MERGE.
- Bảo vệ bảng đích khỏi cập nhật bằng phiên bản cũ, xử lý sự kiện DELETE và dữ liệu delta.
- Tổ chức staging, quarantine, audit, thống kê, idempotency và kiểm thử concurrency.

## 2. Bài toán mẫu: một sản phẩm xuất hiện nhiều lần

Giả sử bảng **su_kien_san_pham** nhận dữ liệu từ nhiều nguồn. Các cột quan trọng:

- **ingest_id**: ID duy nhất của mỗi lần tiếp nhận.
- **batch_id**: lô đồng bộ.
- **tenant_id** và **ma_san_pham**: hai thành phần khóa nghiệp vụ.
- **event_version**: phiên bản do hệ thống nguồn/canonical stream cung cấp.
- **event_at**: thời điểm sự kiện xảy ra hoặc có hiệu lực.
- **ingested_at**: thời điểm hệ thống hiện tại nhận được sự kiện.
- **source_priority**: độ ưu tiên của nguồn, nếu đã được quy định.
- **gia**, **trang_thai**: payload cần cập nhật.
- **operation_type**: loại sự kiện, ví dụ UPSERT hoặc DELETE.

Ví dụ một batch:

| ingest_id | tenant | sản phẩm | version | event_at | priority | giá |
|---:|---|---|---:|---|---:|---:|
| 101 | T1 | P01 | 7 | 2026-10-01 09:00 | 10 | 100000 |
| 102 | T1 | P01 | 8 | 2026-10-03 09:00 | 10 | 110000 |
| 103 | T1 | P01 | 8 | 2026-10-03 09:00 | 20 | 120000 |
| 104 | T1 | P02 | 3 | 2026-10-02 10:00 | 10 | 200000 |
| 105 | T1 | P02 | 2 | 2026-10-04 09:00 | 10 | 180000 |
| 106 | T2 | P01 | 2 | 2026-10-03 14:00 | 10 | 900000 |
| 107 | T1 | P03 | 1 | 2026-10-05 08:00 | 10 | 50000 |
| 108 | T1 | P03 | 1 | 2026-10-05 08:00 | 10 | 50000 |

Quan sát:

1. **T1/P01** có ba bản; version lớn nhất là 8 nhưng có hai dòng cùng version 8 mà **giá khác nhau**.
2. **T1/P02** có version 3 và 2. Version 2 có thời điểm sự kiện muộn hơn nhưng nếu version là thước đo thẩm quyền, **v3 vẫn thắng**.
3. **T2/P01** không trùng với T1/P01 nếu tenant là thành phần của khóa.
4. **T1/P03** có hai payload tương đương trong mẫu, có thể là một lần gửi trùng.

Mục tiêu giả định: cập nhật bảng **san_pham_hien_tai** để cuối cùng có **một hàng trên mỗi cặp (tenant_id,ma_san_pham)**.

### 2.1. Bảng đích

~~~sql
CREATE TABLE san_pham_hien_tai (
    tenant_id VARCHAR(20) NOT NULL,
    ma_san_pham VARCHAR(30) NOT NULL,
    gia DECIMAL(14, 2),
    trang_thai VARCHAR(20),
    event_version BIGINT NOT NULL,
    source_priority INTEGER,
    source_ingest_id BIGINT,
    updated_at TIMESTAMP,
    PRIMARY KEY (tenant_id, ma_san_pham)
);
~~~

PRIMARY KEY ở đích đảm bảo không thể lưu hai hàng cùng **cặp khóa**. Nó không tự giải thích bản ghi nào trong nguồn phải được chọn.

### 2.2. Bảng staging

~~~sql
CREATE TABLE su_kien_san_pham (
    ingest_id BIGINT PRIMARY KEY,
    batch_id VARCHAR(40) NOT NULL,
    tenant_id VARCHAR(20),
    ma_san_pham VARCHAR(30),
    event_version BIGINT,
    event_at TIMESTAMP,
    ingested_at TIMESTAMP NOT NULL,
    source_priority INTEGER NOT NULL,
    gia DECIMAL(14, 2),
    trang_thai VARCHAR(20),
    operation_type VARCHAR(15) NOT NULL
);
~~~

Các dòng nguồn có thể khác ingest_id nhưng vẫn giống business key. Khi xây dựng bảng nguồn thật, cần ràng buộc dữ liệu được chấp nhận từ nhiều hệ và trường nào có thể NULL.

## 3. Phân biệt hai dạng xung đột

**Dạng A — nguồn đã trùng khóa.** Batch có 101,102,103 cùng T1/P01, dù bảng đích còn trống.

**Dạng B — nguồn có một dòng/khóa nhưng khóa đã có trong bảng đích.** Ví dụ nguồn chỉ có T1/P01 version 8, target có T1/P01 version 7. Đây mới là tình huống upsert thông thường: UPDATE thay vì INSERT.

Các cú pháp ON CONFLICT hoặc MERGE chủ yếu quyết định **INSERT/UPDATE/DELETE so với trạng thái của đích**. Chúng **không mặc nhiên chọn phiên bản mới nhất giữa nhiều ứng viên cùng khóa trong nguồn**.

Sơ đồ:

~~~text
Raw source (có thể nhiều dòng/khóa)
             |
             v
    Validate và chuẩn hóa khóa
             |
             v
     Phát hiện trùng, mâu thuẫn
             |
             v
    Xếp hạng và chọn winner
      tối đa một dòng/khóa
             |
             v
       UPSERT hoặc MERGE
          /       \
      đích có     đích chưa có
       UPDATE       INSERT
      hoặc SKIP
~~~

## 4. Khóa nghiệp vụ phải phù hợp mục tiêu đích

Một dòng raw có **ingest_id duy nhất** không đồng nghĩa một sản phẩm duy nhất: P01 xuất hiện ở ba ingest_id.

Nếu bảng đích có khóa ghép:

~~~sql
PRIMARY KEY (tenant_id, ma_san_pham)
~~~

thì quá trình chọn winner phải nhóm đúng:

~~~sql
PARTITION BY tenant_id, ma_san_pham
~~~

Nếu chỉ PARTITION BY ma_san_pham, T1/P01 và T2/P01 có thể bị coi là một nhóm, khiến giá/tenant bị gộp nhầm.

Những hệ thống khác có thể cần thêm **currency, country, channel, price_type hoặc valid_from**. Trước khi loại bỏ dữ liệu trùng, phải xác định **mỗi hàng của target đại diện cho cái gì (grain)**.

### 4.1. Snapshot hiện tại và lịch sử khác nhau

- **Current-state table:** mỗi sản phẩm một hàng; lấy version có hiệu lực mới nhất có thể phù hợp.
- **Snapshot theo ngày:** mỗi (sản phẩm, ngày) một hàng; không được gộp các ngày.
- **SCD Type 2/history:** nhiều bản cùng khóa nghiệp vụ nhưng khác khoảng hiệu lực đều cần giữ.
- **Event ledger:** mỗi sự kiện hợp lệ có thể cần một hàng; không được bỏ các sự kiện trung gian chỉ vì chỉ muốn một winner.

Một bản ghi là “trùng” chỉ theo định nghĩa khóa và grain của **bảng đích cụ thể**.

## 5. Những loại trùng và cách xử lý khác nhau

| Kiểu trùng | Ví dụ | Cách tiếp cận |
|---|---|---|
| Gửi lặp cùng event ID | E123 nhận hai lần | Dedupe theo event ID, giữ audit |
| Hai dòng giống toàn payload | Cùng mã, version, giá | Có thể chọn một theo ID tiếp nhận |
| Nhiều version hợp lệ | v7,v8 cùng sản phẩm | Lấy v8 cho current-state |
| Sự kiện đến muộn | v7 nhận sau v8 | Không ghi lùi target |
| Hai dòng cùng version, khác payload | v8 giá 110000/120000 | Quarantine hoặc quy tắc precedence được phê duyệt |
| Event time bằng nhau | Hai cập nhật cùng giây | Dùng source sequence/ID phá hòa |
| Khóa thiếu | tenant_id NULL | Reject nếu khóa bắt buộc |
| Khóa khác dạng | P01,p01, P01 có khoảng trắng | Canonicalization theo contract |
| Hai nguồn có thẩm quyền khác nhau | ERP và đối tác | Source authority rõ ràng |
| UPSERT và DELETE cùng khóa | v7 UPSERT, v8 DELETE | Winner có thể là DELETE |
| Nhiều dòng thuộc các kỳ hiệu lực khác nhau | Giá tháng 10 và tháng 11 | Cần target history/as-of đúng |

**Không nên áp dụng ROW_NUMBER rn=1 cho mọi loại trùng mà không kiểm tra vì sao chúng trùng.**

## 6. Tìm các khóa xuất hiện nhiều lần

~~~sql
SELECT
    tenant_id,
    ma_san_pham,
    COUNT(*) AS so_ung_vien
FROM su_kien_san_pham
WHERE batch_id = 'B20261005'
GROUP BY tenant_id, ma_san_pham
HAVING COUNT(*) > 1
ORDER BY so_ung_vien DESC, tenant_id, ma_san_pham;
~~~

Với bảng mẫu và giả định cùng batch:

| Khóa | Số dòng |
|---|---:|
| T1/P01 | 3 |
| T1/P02 | 2 |
| T1/P03 | 2 |

Khóa T2/P01 có một dòng.

### 6.1. Trùng khóa và phiên bản

~~~sql
SELECT
    tenant_id,
    ma_san_pham,
    event_version,
    COUNT(*) AS so_dong
FROM su_kien_san_pham
WHERE batch_id = 'B20261005'
GROUP BY tenant_id, ma_san_pham, event_version
HAVING COUNT(*) > 1;
~~~

Bảng mẫu có trùng v8 của T1/P01, trùng v1 của T1/P03.

Khóa trùng **khác version** có thể hợp lệ; hai dòng **cùng version khác payload** có thể là lỗi. Đây là hai nhóm cảnh báo khác nhau.

## 7. Vì sao DISTINCT không chọn được bản đại diện?

~~~sql
SELECT DISTINCT
    tenant_id, ma_san_pham, event_version, gia
FROM su_kien_san_pham
WHERE batch_id = 'B20261005';
~~~

T1/P01 vẫn có các tổ hợp:

~~~text
T1 P01 v7 100000
T1 P01 v8 110000
T1 P01 v8 120000
~~~

DISTINCT chỉ loại các dòng **giống nhau trên tất cả cột được SELECT**, không biết “version lớn nhất” hoặc “priority cao nhất”.

Nếu chỉ chọn:

~~~sql
SELECT DISTINCT tenant_id, ma_san_pham
FROM su_kien_san_pham;
~~~

thì được một dòng/khóa nhưng **mất giá, trạng thái, version và provenance** cần cho UPSERT.

**DISTINCT không phải công cụ chọn bản đầy đủ theo thứ tự ưu tiên.**

## 8. Vì sao GROUP BY + MAX có thể tạo bản ghi giả?

Một cách sai:

~~~sql
SELECT
    tenant_id,
    ma_san_pham,
    MAX(event_version) AS version_moi_nhat,
    MAX(gia) AS gia_lon_nhat
FROM su_kien_san_pham
GROUP BY tenant_id, ma_san_pham;
~~~

Giả sử một sản phẩm có:

~~~text
v7: giá 200000
v8: giá 100000
~~~

Kết quả MAX(version)=8 và MAX(gia)=200000. Nhưng **không hề có dòng nguồn (v8,200000)**. Bạn đã ghép hai cột từ **hai bản ghi khác nhau**.

Một bản đại diện cần giữ **mọi thuộc tính từ cùng một hàng nguồn**.

### 8.1. Lấy MAX(time) rồi JOIN lại vẫn có thể trả nhiều hàng

~~~sql
WITH max_time AS (
    SELECT
        tenant_id,
        ma_san_pham,
        MAX(event_at) AS event_at_moi
    FROM su_kien_san_pham
    GROUP BY tenant_id, ma_san_pham
)
SELECT s.*
FROM su_kien_san_pham s
JOIN max_time m
  ON m.tenant_id = s.tenant_id
 AND m.ma_san_pham = s.ma_san_pham
 AND m.event_at_moi = s.event_at;
~~~

Nếu hai dòng cùng event_at mới nhất, JOIN trả **cả hai**. Nếu event_at NULL, phép bằng với NULL cũng cần xử lý.

## 9. RANK, DENSE_RANK và ROW_NUMBER

Các hàm cửa sổ đều có thể xếp thứ tự, nhưng khác nhau khi có **đồng hạng**.

| Hàm | Nếu hai dòng cùng khóa sắp xếp cao nhất | Lọc giá trị 1 |
|---|---|---|
| RANK() | Cả hai được rank=1 | Có thể trả hai dòng |
| DENSE_RANK() | Cả hai được rank=1 | Có thể trả hai dòng |
| ROW_NUMBER() | Một rn=1, một rn=2 | Tối đa một dòng |

Ví dụ:

~~~sql
RANK() OVER (
    PARTITION BY tenant_id, ma_san_pham
    ORDER BY event_version DESC
)
~~~

T1/P01 có hai dòng version 8, nên **cả hai rank=1**. Nếu MERGE từ tập rank=1, nguồn vẫn trùng.

ROW_NUMBER giải quyết cardinality, nhưng cần **ORDER BY xác định** để tránh chọn tùy ý một trong hai bản.

## 10. Mẫu cốt lõi: ROW_NUMBER và CTE

Giả sử chính sách đã được thông qua:

1. Version lớn hơn thắng.
2. Nếu version bằng, event_at muộn hơn thắng.
3. Nếu vẫn bằng, source_priority lớn hơn thắng.
4. Nếu vẫn bằng, ingested_at muộn hơn thắng.
5. Nếu vẫn bằng, ingest_id lớn hơn thắng (khóa duy nhất dùng để phá hòa).

~~~sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, ma_san_pham
            ORDER BY
                event_version DESC,
                event_at DESC,
                source_priority DESC,
                ingested_at DESC,
                ingest_id DESC
        ) AS rn
    FROM su_kien_san_pham s
    WHERE batch_id = 'B20261005'
      AND tenant_id IS NOT NULL
      AND ma_san_pham IS NOT NULL
)
SELECT
    tenant_id,
    ma_san_pham,
    gia,
    trang_thai,
    event_version,
    source_priority,
    ingest_id
FROM ranked
WHERE rn = 1;
~~~

Với bảng mẫu (và các thuộc tính không hiển thị được giả định không phá thứ tự):

| Khóa | Winner | Lý do |
|---|---:|---|
| T1/P01 | 103 | v8 thắng v7; cùng v8 và time thì priority=20 thắng |
| T1/P02 | 104 | v3 thắng v2 dù event_at v2 muộn |
| T2/P01 | 106 | Tenant khác được xếp riêng |
| T1/P03 | 108 | Cùng version/time/priority, ingest_id lớn hơn phá hòa |

### 10.1. Vì sao phải lọc rn=1 ở query bên ngoài?

Hàm cửa sổ được đánh giá sau bước WHERE của cùng query block theo logic SQL phổ biến. Vì vậy thường không thể viết:

~~~sql
SELECT
    ROW_NUMBER() OVER (...) AS rn
FROM su_kien_san_pham
WHERE rn = 1;
~~~

và mong alias rn khả dụng ngay trong WHERE. Dùng **CTE hoặc derived table** rồi lọc ngoài; ở những hệ hỗ trợ **QUALIFY**, có thể lọc kết quả window theo cú pháp riêng.

### 10.2. Thứ tự phải quyết định duy nhất dòng thắng

~~~sql
ORDER BY event_version DESC
~~~

không phân định hai dòng version 8. ROW_NUMBER vẫn tạo một rn=1 nhưng dòng nào được chọn có thể phụ thuộc kế hoạch thực thi, parallelism, index và thứ tự vật lý.

Thêm tiêu chí theo business policy và **một tie-breaker duy nhất** khi được phép chọn bằng cơ chế đó.

### 10.3. Deterministic không đồng nghĩa đúng nghiệp vụ

Nếu hai dòng cùng version nhưng **giá khác nhau** và hợp đồng dữ liệu quy định version phải có payload duy nhất, việc dùng ingest_id làm tie-break vẫn chọn được một dòng **nhưng che một lỗi nghiêm trọng**.

Với trường hợp đó, nên **quarantine khóa mâu thuẫn**, không áp giá trị tùy ý.

## 11. Nguyên tắc chọn bản đại diện theo nghiệp vụ

Không có một ORDER BY đúng cho mọi hệ:

| Mục tiêu | Thứ tự ưu tiên có thể phù hợp |
|---|---|
| Trạng thái mới nhất từ stream có version toàn cục | event_version DESC |
| CDC từ một cơ sở dữ liệu | source LSN/sequence DESC |
| Sự kiện gần nhất theo nghiệp vụ | event_at DESC, event_id DESC |
| Nguồn chính có thẩm quyền hơn nguồn phụ | source_priority DESC rồi version trong nguồn |
| Bản đã duyệt mới nhất | approved flag, approved_at DESC |
| Một mức giá theo ngày hiệu lực | valid_from/valid_to và as-of time |
| Giá cao nhất trong một tập | gia DESC nếu yêu cầu thật là giá cao nhất |
| Đồng version khác payload không hợp lệ | Quarantine/alert |

### 11.1. Hai ORDER BY khác nhau có ý nghĩa khác nhau

~~~sql
ORDER BY event_version DESC, source_priority DESC
~~~

ưu tiên version trước.

~~~sql
ORDER BY source_priority DESC, event_version DESC
~~~

ưu tiên nguồn trước.

Trong thứ tự thứ nhất, bản v9 từ nguồn ưu tiên thấp có thể thắng v8 từ nguồn ưu tiên cao. Trong thứ tự thứ hai, nguồn ưu tiên cao có thể giữ quyền dù version thấp. Phải biết **version giữa các nguồn có so sánh được không**.

### 11.2. Version riêng từng hệ không thể so thẳng

ERP version 100 và CRM version 12 không mặc nhiên chứng minh ERP mới hơn nếu mỗi hệ tăng version theo cách riêng. Có thể cần canonical version, source priority, source-specific sequence hoặc quy tắc hợp nhất theo từng trường.

## 12. Event time khác ingestion time

- **event_at**: lúc thay đổi nghiệp vụ xảy ra/có hiệu lực.
- **ingested_at**: lúc hệ tiếp nhận nhìn thấy thay đổi.
- **source_sequence/LSN**: vị trí thay đổi trong log của một nguồn.

Một sự kiện v7 có thể đến trễ sau v8. Nếu luôn chọn ingested_at lớn nhất, hệ thống có thể **ghi lùi trạng thái**.

Ví dụ:

~~~text
09:00: nhận sự kiện v8 giá 120000
09:05: nhận lại sự kiện v7 giá 100000
~~~

Chọn bản mới nhất theo ingestion time sẽ chọn v7, dù **version nguồn** thể hiện v8 mới hơn. Phải xác định tiêu chí chính thích hợp.

### 12.1. Timezone và độ chính xác

Hai hệ gửi timestamp theo timezone khác nhau; một nguồn chỉ chính xác tới giây, một nguồn tới mili giây. Cần chuẩn hóa instant và độ chính xác trước khi ORDER BY. Không tự so chuỗi thời gian định dạng lẫn lộn.

### 12.2. NULL trong thứ tự

Các DBMS có thể đặt NULL trước/sau khác nhau. Có thể ghi quy tắc NULL xuống cuối:

~~~sql
ORDER BY
    CASE WHEN event_version IS NULL THEN 1 ELSE 0 END,
    event_version DESC,
    ingest_id DESC
~~~

Nếu version bắt buộc, tốt hơn là báo lỗi dữ liệu thiếu version thay vì cho nó dự thi winner.

## 13. Phát hiện cùng version khác payload

Nếu hợp đồng sự kiện yêu cầu với mỗi (tenant,product,version) chỉ có **một payload hợp lệ**, thì hai dòng v8 có giá khác nhau cần kiểm tra.

Với giả định gia không NULL:

~~~sql
SELECT
    tenant_id,
    ma_san_pham,
    event_version,
    COUNT(*) AS so_dong,
    MIN(gia) AS gia_min,
    MAX(gia) AS gia_max
FROM su_kien_san_pham
WHERE batch_id = 'B20261005'
GROUP BY tenant_id, ma_san_pham, event_version
HAVING COUNT(*) > 1
   AND MIN(gia) <> MAX(gia);
~~~

T1/P01 v8 bị phát hiện.

**Giới hạn:** phép so trên chỉ xem **gia**, bỏ qua trang_thai và NULL. Trong hệ thật cần so **tất cả trường có ý nghĩa**, theo null-safe equality hoặc checksum có quy tắc canonicalization và xác minh đủ.

### 13.1. Nên phân biệt các nhóm kết quả

- **Invalid:** thiếu khóa/version, sai kiểu, vi phạm chính sách.
- **Duplicate replay:** cùng event ID và payload.
- **Superseded:** version cũ hợp lệ nhưng không phải winner.
- **Business conflict:** cùng key/version với thông tin mâu thuẫn.
- **Stale vs target:** winner batch vẫn thấp hơn version đã lưu ở đích.

Không nên lặng lẽ bỏ hết những dòng rn>1 rồi coi mọi trường hợp đều là “đã lọc trùng thành công”.

## 14. CTE có thống kê số ứng viên

~~~sql
WITH ranked AS (
    SELECT
        s.*,
        COUNT(*) OVER (
            PARTITION BY tenant_id, ma_san_pham
        ) AS so_ung_vien,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, ma_san_pham
            ORDER BY event_version DESC,
                     source_priority DESC,
                     ingest_id DESC
        ) AS rn
    FROM su_kien_san_pham s
    WHERE batch_id = 'B20261005'
)
SELECT
    tenant_id, ma_san_pham,
    ingest_id, event_version, gia,
    so_ung_vien
FROM ranked
WHERE rn = 1;
~~~

Cột so_ung_vien giúp audit: winner được chọn từ 1,2,3 hay nhiều bản ghi? Tuy nhiên COUNT(*)>1 không tự chứng minh dữ liệu sai, vì một batch có nhiều version hợp lệ vẫn cần một winner nếu đích là current-state.

### 14.1. Lọc trước/sau ROW_NUMBER rất quan trọng

Giả sử:

~~~text
v7: operation_type = UPSERT, status = ACTIVE
v8: operation_type = DELETE
~~~

Nếu bạn WHERE operation_type='UPSERT' **trước** ROW_NUMBER, v8 DELETE bị loại, v7 thắng và sản phẩm bị **hồi sinh**.

Đúng với current-state từ CDC:

1. Validate cả UPSERT lẫn DELETE.
2. Chọn sự kiện mới nhất theo version/sequence.
3. Đọc operation_type của winner.
4. Áp action tương ứng, có thể soft delete hoặc hard delete.

## 15. Khóa NULL và chuẩn hóa khóa

Trong SQL, PARTITION BY có thể nhóm các hàng có NULL ở các vị trí khóa vào cùng partition, trong khi UNIQUE index và ON matching có hành vi với NULL **khác nhau giữa DBMS**. MySQL thường cho phép nhiều NULL trong UNIQUE, còn nhiều cách JOIN bằng dấu = không coi NULL = NULL là TRUE.

Nếu tenant_id,ma_san_pham là khóa bắt buộc:

~~~sql
WHERE tenant_id IS NOT NULL
  AND ma_san_pham IS NOT NULL
~~~

nên là một phần đầu vào hợp lệ, còn dòng thiếu khóa cần được ghi reject/quarantine chứ không chỉ biến mất không dấu vết.

### 15.1. Canonicalization có thể làm đổi nghĩa khóa

Các biến thể:

~~~text
P01
p01
 P01
P01<space>
~~~

có thể cùng mã hoặc là mã khác nhau tùy quy tắc. Trước khi dùng TRIM/UPPER/LOWER, cần quyết định **case sensitivity, whitespace, Unicode normalization và collation**. Nếu target UNIQUE và source PARTITION dùng quy tắc khác, hệ có thể chọn một winner nhưng vẫn INSERT trùng hoặc gộp nhầm thực thể.

Hướng tốt: dùng **canonical_business_key** được định nghĩa và lưu/thực thi nhất quán ở staging, khóa đích và MERGE ON.

### 15.2. Đừng quên tenant

Nếu P01 của T1 và T2 khác nhau, mọi tầng cần cùng khóa:

~~~text
PARTITION BY (tenant_id, ma_san_pham)
staging UNIQUE (batch_id, tenant_id, ma_san_pham)
target UNIQUE (tenant_id, ma_san_pham)
MERGE ON cùng cặp tenant_id và ma_san_pham
~~~

Bỏ tenant ở một trong bốn tầng là nguy cơ sai dữ liệu.

## 16. PostgreSQL: ON CONFLICT DO UPDATE với nguồn trùng

PostgreSQL hỗ trợ upsert:

~~~sql
INSERT INTO san_pham_hien_tai (
    tenant_id, ma_san_pham, gia, trang_thai,
    event_version, source_priority, source_ingest_id
)
VALUES ('T1', 'P01', 120000, 'ACTIVE', 8, 20, 103)
ON CONFLICT (tenant_id, ma_san_pham)
DO UPDATE SET
    gia = EXCLUDED.gia,
    trang_thai = EXCLUDED.trang_thai,
    event_version = EXCLUDED.event_version,
    source_priority = EXCLUDED.source_priority,
    source_ingest_id = EXCLUDED.source_ingest_id;
~~~

**EXCLUDED** đại diện cho giá trị dòng đề xuất insert khi xảy ra conflict.

Một INSERT ... SELECT có nhiều dòng cùng business key đi cùng **ON CONFLICT DO UPDATE** có thể bị PostgreSQL từ chối với **cardinality violation**, chẳng hạn thông báo rằng một dòng đích không được cập nhật lần thứ hai trong cùng câu lệnh. Không thể coi hệ tự chọn winner.

### 16.1. Khử trùng trước INSERT SELECT

~~~sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, ma_san_pham
            ORDER BY event_version DESC,
                     event_at DESC,
                     source_priority DESC,
                     ingested_at DESC,
                     ingest_id DESC
        ) AS rn
    FROM su_kien_san_pham s
    WHERE batch_id = 'B20261005'
      AND tenant_id IS NOT NULL
      AND ma_san_pham IS NOT NULL
)
INSERT INTO san_pham_hien_tai AS t (
    tenant_id, ma_san_pham, gia, trang_thai,
    event_version, source_priority, source_ingest_id
)
SELECT
    tenant_id, ma_san_pham, gia, trang_thai,
    event_version, source_priority, ingest_id
FROM ranked
WHERE rn = 1
ON CONFLICT (tenant_id, ma_san_pham)
DO UPDATE SET
    gia = EXCLUDED.gia,
    trang_thai = EXCLUDED.trang_thai,
    event_version = EXCLUDED.event_version,
    source_priority = EXCLUDED.source_priority,
    source_ingest_id = EXCLUDED.source_ingest_id
WHERE EXCLUDED.event_version > t.event_version;
~~~

Có **hai lớp bảo vệ**:

1. **rn=1**: nguồn được đưa vào INSERT có tối đa một dòng/khóa.
2. **WHERE EXCLUDED.event_version > t.event_version**: không để winner của batch cũ ghi đè version mới hơn ở đích.

Điều kiện version phù hợp nếu **version thực sự có thứ tự toàn cục trong mỗi khóa** và **equal-version được coi là replay hoặc conflict không tự update**. Khi cần so priority trong trường hợp version bằng, phải lưu metadata và viết chính sách tương ứng.

### 16.2. DO NOTHING không phải thuật toán chọn winner

~~~sql
ON CONFLICT (tenant_id, ma_san_pham)
DO NOTHING
~~~

có thể bỏ qua những dòng gây conflict, nhưng không tự xét “dòng nào có version cao nhất”. Nếu target chưa có khóa và nguồn chứa nhiều ứng viên, việc chấp nhận một dòng nào đó trước rồi bỏ dòng sau **không phải chính sách đáng tin**. Hơn nữa DO NOTHING không cập nhật bản ghi đã có.

### 16.3. Unique constraint phải phù hợp

ON CONFLICT cần một ràng buộc/index unique phù hợp. Nếu target không thực sự có UNIQUE cho cặp (tenant,product), câu lệnh không tự bảo đảm một dòng/current key.

## 17. SQL Server: MERGE cần USING nguồn duy nhất

Mẫu SQL Server:

~~~sql
MERGE dbo.san_pham_hien_tai AS t
USING dbo.staging_winner AS s
    ON t.tenant_id = s.tenant_id
   AND t.ma_san_pham = s.ma_san_pham
WHEN MATCHED AND s.event_version > t.event_version THEN
    UPDATE SET
        gia = s.gia,
        trang_thai = s.trang_thai,
        event_version = s.event_version,
        source_priority = s.source_priority,
        source_ingest_id = s.ingest_id
WHEN NOT MATCHED BY TARGET THEN
    INSERT (
        tenant_id, ma_san_pham, gia, trang_thai,
        event_version, source_priority, source_ingest_id
    )
    VALUES (
        s.tenant_id, s.ma_san_pham, s.gia, s.trang_thai,
        s.event_version, s.source_priority, s.ingest_id
    );
~~~

Mẫu giả định **staging_winner đã có một dòng/khóa**.

### 17.1. Nhiều nguồn cùng match một target

SQL Server có thể báo lỗi khi một MERGE với WHEN MATCHED UPDATE hoặc DELETE yêu cầu **một hàng đích bị cập nhật/xóa nhiều lần** bởi nhiều dòng nguồn.

Nếu target chưa có khóa đó, hai source rows cùng khóa có thể đều được coi NOT MATCHED BY TARGET, dẫn tới hai lần INSERT và lỗi UNIQUE.

Vì vậy, dùng ROW_NUMBER và lọc rn=1 trước MERGE.

### 17.2. Tạo winner trong USING

~~~sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, ma_san_pham
            ORDER BY event_version DESC,
                     source_priority DESC,
                     ingest_id DESC
        ) AS rn
    FROM dbo.su_kien_san_pham s
    WHERE batch_id = 'B20261005'
),
winner AS (
    SELECT *
    FROM ranked
    WHERE rn = 1
)
MERGE dbo.san_pham_hien_tai AS t
USING winner AS s
   ON t.tenant_id = s.tenant_id
  AND t.ma_san_pham = s.ma_san_pham
WHEN MATCHED AND s.event_version > t.event_version THEN
    UPDATE SET
        gia = s.gia,
        trang_thai = s.trang_thai,
        event_version = s.event_version,
        source_priority = s.source_priority,
        source_ingest_id = s.ingest_id
WHEN NOT MATCHED BY TARGET THEN
    INSERT (
        tenant_id, ma_san_pham, gia, trang_thai,
        event_version, source_priority, source_ingest_id
    )
    VALUES (
        s.tenant_id, s.ma_san_pham, s.gia, s.trang_thai,
        s.event_version, s.source_priority, s.ingest_id
    );
~~~

SQL Server cần quản lý dấu chấm phẩy kết thúc câu lệnh và kết thúc câu ngay trước CTE theo cú pháp T-SQL. Với production, không nên dùng MERGE mà chưa kiểm tra đặc tính phiên bản, isolation/locking và bài kiểm thử concurrency. Có hệ thống chọn UPDATE rồi INSERT riêng trong giao dịch phù hợp để dễ kiểm soát.

### 17.3. ON chỉ nên nhận diện thực thể

Sai ý định nếu viết:

~~~sql
ON t.tenant_id = s.tenant_id
AND t.ma_san_pham = s.ma_san_pham
AND t.trang_thai = 'ACTIVE'
~~~

Hàng đích P01 với status STOP có thể bị coi NOT MATCHED và MERGE thử INSERT một P01 khác. Điều kiện trạng thái/phiên bản cần đặt trong **WHEN MATCHED AND ...** khi muốn kiểm soát cập nhật, không làm méo định nghĩa khóa.

## 18. Oracle Database: MERGE từ ranked source

Oracle có MERGE:

~~~sql
MERGE INTO san_pham_hien_tai t
USING staging_winner s
ON (
    t.tenant_id = s.tenant_id
    AND t.ma_san_pham = s.ma_san_pham
)
WHEN MATCHED THEN
    UPDATE SET
        t.gia = s.gia,
        t.trang_thai = s.trang_thai,
        t.event_version = s.event_version,
        t.source_priority = s.source_priority,
        t.source_ingest_id = s.ingest_id
    WHERE s.event_version > t.event_version
WHEN NOT MATCHED THEN
    INSERT (
        tenant_id, ma_san_pham, gia, trang_thai,
        event_version, source_priority, source_ingest_id
    )
    VALUES (
        s.tenant_id, s.ma_san_pham, s.gia, s.trang_thai,
        s.event_version, s.source_priority, s.ingest_id
    );
~~~

Nếu nguồn trùng và một hàng đích bị ảnh hưởng không ổn định, Oracle có thể báo **ORA-30926** tùy kiểu cập nhật và dữ liệu. Nếu target chưa có khóa và nhiều nguồn cùng INSERT, có thể vi phạm UNIQUE. Không dựa vào việc một lần MERGE có thể chạy được để coi Oracle đã chọn đại diện đúng.

### 18.1. CTE/inline view với ROW_NUMBER

~~~sql
MERGE INTO san_pham_hien_tai t
USING (
    SELECT
        tenant_id, ma_san_pham, gia, trang_thai,
        event_version, source_priority, ingest_id
    FROM (
        SELECT
            s.*,
            ROW_NUMBER() OVER (
                PARTITION BY tenant_id, ma_san_pham
                ORDER BY event_version DESC,
                         source_priority DESC,
                         ingest_id DESC
            ) AS rn
        FROM su_kien_san_pham s
        WHERE batch_id = 'B20261005'
    )
    WHERE rn = 1
) s
ON (
    t.tenant_id = s.tenant_id
    AND t.ma_san_pham = s.ma_san_pham
)
WHEN MATCHED THEN
    UPDATE SET
        t.gia = s.gia,
        t.trang_thai = s.trang_thai,
        t.event_version = s.event_version,
        t.source_priority = s.source_priority,
        t.source_ingest_id = s.ingest_id
    WHERE s.event_version > t.event_version
WHEN NOT MATCHED THEN
    INSERT (
        tenant_id, ma_san_pham, gia, trang_thai,
        event_version, source_priority, source_ingest_id
    )
    VALUES (
        s.tenant_id, s.ma_san_pham, s.gia, s.trang_thai,
        s.event_version, s.source_priority, s.ingest_id
    );
~~~

Mẫu đã rút gọn thứ tự so với phần 10; khi cần event_at/ingested_at thì thêm theo chính sách.

### 18.2. Không tùy ý sửa cột trong ON

Oracle MERGE có hạn chế cập nhật những cột đích đã dùng trong điều kiện ON. Đổi business key thường cần một quy trình quản lý định danh riêng, không coi như cập nhật thuộc tính thông thường.

## 19. MySQL: ON DUPLICATE KEY UPDATE khác chọn winner

Ví dụ một hàng:

~~~sql
INSERT INTO san_pham_hien_tai (
    tenant_id, ma_san_pham, gia, trang_thai,
    event_version, source_priority, source_ingest_id
)
VALUES (
    'T1', 'P01', 120000, 'ACTIVE', 8, 20, 103
)
ON DUPLICATE KEY UPDATE
    gia = 120000,
    trang_thai = 'ACTIVE',
    event_version = 8,
    source_priority = 20,
    source_ingest_id = 103;
~~~

Cú pháp này giải quyết tình huống một INSERT đụng UNIQUE/PRIMARY KEY. Nếu **một câu multi-row INSERT có nhiều dòng source cùng khóa**, MySQL có thể xử lý nhiều lần cập nhật cho khóa ấy theo logic câu lệnh, **không tự bảo đảm giữ bản version cao nhất**.

### 19.1. Dedupe bằng MySQL 8.0 ROW_NUMBER

~~~sql
SELECT
    tenant_id, ma_san_pham, gia, trang_thai,
    event_version, source_priority, ingest_id
FROM (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, ma_san_pham
            ORDER BY event_version DESC,
                     source_priority DESC,
                     ingest_id DESC
        ) AS rn
    FROM su_kien_san_pham s
    WHERE batch_id = 'B20261005'
) AS ranked
WHERE rn = 1;
~~~

Có thể đưa kết quả vào staging_winner với UNIQUE rồi dùng INSERT ... SELECT ... ON DUPLICATE KEY UPDATE tương ứng phiên bản MySQL.

### 19.2. VALUES(column) và cú pháp alias

Tài liệu MySQL 8.0 đời trước thường dùng VALUES(column) ở ON DUPLICATE KEY UPDATE để tham chiếu giá trị đề xuất. Ở các bản mới hơn, dạng dùng VALUES ở ngữ cảnh này đã bị deprecate và có cú pháp alias thay thế. Với INSERT ... SELECT có thêm những giới hạn cú pháp; không sao chép ngẫu nhiên ví dụ từ phiên bản khác.

### 19.3. Một bảng có nhiều UNIQUE

MySQL ON DUPLICATE KEY UPDATE có thể kích hoạt do **một UNIQUE khác với business key mà bạn dự kiến**. Khi thiết kế target với nhiều ràng buộc unique, cần phân tích đầy đủ tình huống conflict, không chỉ WHERE/ON theo product ID.

## 20. SQLite: UPSERT xử lý conflict theo từng dòng đề xuất

~~~sql
INSERT INTO san_pham_hien_tai (
    tenant_id, ma_san_pham, gia, trang_thai,
    event_version, source_priority, source_ingest_id
)
VALUES (
    'T1', 'P01', 120000, 'ACTIVE', 8, 20, 103
)
ON CONFLICT (tenant_id, ma_san_pham)
DO UPDATE SET
    gia = excluded.gia,
    trang_thai = excluded.trang_thai,
    event_version = excluded.event_version,
    source_priority = excluded.source_priority,
    source_ingest_id = excluded.source_ingest_id
WHERE excluded.event_version > san_pham_hien_tai.event_version;
~~~

SQLite áp UPSERT theo mỗi proposed row theo cú pháp hỗ trợ, chứ không tự chọn bản đại diện theo version giữa nhiều row nguồn.

SQLite 3.25+ có window functions; các bản nhúng cũ hơn trong thiết bị có thể không có ROW_NUMBER. Nếu dùng INSERT INTO ... SELECT ... ON CONFLICT, SQLite có tình huống cú pháp parser cần WHERE trong phần SELECT để tránh nhầm ON của JOIN với UPSERT; xem tài liệu đúng phiên bản.

### 20.1. Kiểu dữ liệu có thể ảnh hưởng ORDER BY

SQLite dùng type affinity linh hoạt. Nếu version được lưu dưới dạng chuỗi, '10' và '9' có thể bị sắp theo từ điển không như số học. Chuẩn hóa version thành kiểu số hợp lệ trước khi xếp hạng, đồng thời xử lý các chuỗi không chuyển được.

## 21. BigQuery và QUALIFY

BigQuery GoogleSQL hỗ trợ lọc kết quả hàm cửa sổ bằng QUALIFY:

~~~sql
SELECT *
FROM project.dataset.su_kien_san_pham
WHERE batch_id = 'B20261005'
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY tenant_id, ma_san_pham
    ORDER BY event_version DESC,
             source_priority DESC,
             ingest_id DESC
) = 1;
~~~

QUALIFY tiện nhưng **không phải mọi DBMS có**. PostgreSQL, SQL Server, MySQL và SQLite thường dùng CTE hoặc derived table.

Trong BigQuery MERGE, khi nhiều nguồn match một target và yêu cầu UPDATE/DELETE, có thể có lỗi do một hàng đích bị ảnh hưởng bởi nhiều nguồn. Vì thế cũng cần unique source.

## 22. So sánh ngữ nghĩa giữa các DBMS

| Hệ/cơ chế | Nếu nguồn có hai dòng cùng khóa đích | Cần làm gì |
|---|---|---|
| PostgreSQL ON CONFLICT DO UPDATE | Có thể lỗi khi cố tác động cùng hàng đích hai lần | Dedupe bằng ROW_NUMBER |
| SQL Server MERGE | Nhiều nguồn match một đích UPDATE/DELETE có thể lỗi; nhiều INSERT có thể vi phạm UNIQUE | USING một dòng/khóa |
| Oracle MERGE | Có thể lỗi do source không ổn định hoặc UNIQUE | MERGE từ inline view winner |
| MySQL ON DUPLICATE KEY UPDATE | Có thể thực hiện nhiều cập nhật, không tự chọn latest version | Tạo winner rồi upsert |
| SQLite ON CONFLICT DO UPDATE | Conflict được xử lý từng proposed row | Tạo winner trước |
| BigQuery MERGE | Nhiều nguồn match đích để UPDATE/DELETE có thể lỗi | QUALIFY/ROW_NUMBER trước |

Phải kiểm tra **phiên bản, chỉ mục unique, concurrency và câu lệnh cụ thể** trên hệ đang dùng. Một DBMS “không báo lỗi” không chứng minh rằng nó chọn dòng bạn muốn.

## 23. Winner trong batch vẫn có thể cũ hơn target

Giả sử batch chọn T1/P01 v8, nhưng bảng đích đã có v9. Nếu upsert luôn ghi đè theo khóa, target sẽ bị **hạ từ v9 về v8**.

Cần kiểm tra:

~~~sql
source.event_version > target.event_version
~~~

trong **nhánh UPDATE tại DB**, hoặc WHERE của ON CONFLICT DO UPDATE, nếu chính sách là version mới hơn thắng.

### 23.1. Hai mức bảo vệ

1. **Nguồn:** chọn một winner/khóa trong batch.
2. **Đích:** so winner với metadata đã lưu, chỉ apply nếu đủ mới.

Bỏ một trong hai có thể gây lỗi khác nhau:

- Không dedupe nguồn → một MERGE có nhiều tác động đến một khóa.
- Không kiểm tra target version → batch đến muộn ghi đè trạng thái mới.

### 23.2. Version bằng nhau

Nếu source và target cùng v8:

- Có thể coi là replay và **không UPDATE**.
- Nếu payload khác, báo lỗi/đưa vào quarantine.
- Nếu contract cho phép nguồn ưu tiên cao hơn ghi đè cùng version, phải lưu đủ source_priority ở target và so theo rule tường minh.

Không tự chọn bằng ingested_at mới nhất nếu ingested_at chỉ là thời điểm nhận dữ liệu.

## 24. CDC, sự kiện đến muộn và tombstone

Trong Change Data Capture có thể có:

~~~text
source_seq 200: INSERT P01 giá 100000
source_seq 220: UPDATE P01 giá 110000
source_seq 240: DELETE P01
~~~

Nếu target là **trạng thái hiện tại**, sự kiện seq 240 là **winner**, mặc dù nó không mang giá. Đừng lọc operation_type='UPSERT' trước ROW_NUMBER rồi lấy seq 220, vì sẽ làm P01 sống lại.

### 24.1. Xóa mềm

Có thể lưu current-state:

~~~text
tenant_id, product_id, event_version, is_deleted, deleted_at
~~~

Nếu winner là DELETE, đặt is_deleted=TRUE và lưu version/sequence đã áp. Sự kiện UPSERT cũ đến muộn không được bỏ cờ xóa nếu version thấp hơn.

### 24.2. Xóa cứng

Nếu hard DELETE khiến target **mất cả version cuối cùng đã áp dụng**, một UPSERT cũ có thể thấy target chưa có và INSERT lại. Cần tombstone/watermark ở bảng khác hoặc cơ chế ngăn replay theo sequence.

### 24.3. Snapshot và CDC cùng chạy

Một snapshot cũ có thể hoàn thành nạp muộn hơn CDC mới. Nếu so theo thời điểm tiếp nhận thay vì source sequence/consistent snapshot boundary, trạng thái cuối có thể sai. Cần thiết kế watermark và mốc chuyển tiếp giữa snapshot/CDC.

## 25. Không dùng một winner để áp các sự kiện delta

Hai loại dữ liệu:

**State event đầy đủ:**

~~~text
P01 v7 -> ton = 10
P01 v8 -> ton = 13
~~~

Chọn v8 có thể đủ nếu chỉ lưu current-state và không cần lưu history ở target đó.

**Delta event:**

~~~text
P01 v7 -> ton = ton + 5
P01 v8 -> ton = ton - 2
~~~

Nếu bỏ v7 và chỉ áp v8, kết quả sai khi v7 chưa được áp. Delta cần xử lý **đủ các sự kiện chưa áp theo thứ tự**, kèm event ID/idempotency.

Một bản đại diện cho current-state **không thể tự thay thế replay chuỗi sự kiện delta**.

## 26. Đầu vào từ nhiều nguồn có thể cần winner theo từng cột

Ví dụ:

- ERP quyết định **gia** và **ton_kho**.
- CRM quyết định **mo_ta**.
- Hệ vận hành quyết định **trang_thai**.

Nếu chọn một dòng CRM làm winner toàn bộ, có thể ghi đè giá ERP bằng giá cũ/NULL của CRM. Đúng hơn là có quy tắc quyền sở hữu **theo từng thuộc tính**, chọn dữ liệu đại diện cho mỗi nhóm thuộc tính rồi tổng hợp.

Vì vậy hãy hỏi:

**Có thật sự cần một bản ghi đại diện cho toàn bộ thực thể, hay cần một bản ghi đại diện riêng cho mỗi trường/nhóm trường?**

Nếu mỗi nguồn phụ trách thuộc tính khác nhau, một ROW_NUMBER toàn dòng có thể không phù hợp.

## 27. Khóa theo thời gian hiệu lực

Nếu đích là bảng lịch sử giá:

~~~text
tenant_id, ma_san_pham, valid_from, valid_to, gia
~~~

hai bản giá cùng sản phẩm nhưng có các khoảng hiệu lực không chồng nhau là **hai dòng hợp lệ**, không phải trùng. Dedupe chỉ theo (tenant_id,ma_san_pham) sẽ làm mất lịch sử.

Nếu mục tiêu là **giá đang có hiệu lực tại thời điểm as_of**, cần lọc khoảng thời gian hợp lệ:

~~~sql
valid_from <= :as_of
AND (valid_to IS NULL OR :as_of < valid_to)
~~~

rồi kiểm tra tại as_of có **tối đa một bản giá** cho mỗi business key. Đây là quy tắc khác với “lấy version lớn nhất, bất kể hiệu lực tương lai”.

### 27.1. Version tương lai không tự là current

Giá v9 có hiệu lực từ tháng sau nhưng hôm nay đang dùng v8. Một bảng current-as-of-today không nên áp v9 ngay chỉ vì version cao hơn. Phải định nghĩa “mới nhất đã biết” hay “đang có hiệu lực” cho target.

## 28. Tạo staging winners và ràng buộc duy nhất

Một cách làm có thể kiểm chứng là vật hóa tập winner trước khi merge:

~~~sql
CREATE TABLE staging_winner (
    batch_id VARCHAR(40) NOT NULL,
    tenant_id VARCHAR(20) NOT NULL,
    ma_san_pham VARCHAR(30) NOT NULL,
    event_version BIGINT NOT NULL,
    ingest_id BIGINT NOT NULL,
    gia DECIMAL(14, 2),
    trang_thai VARCHAR(20),
    PRIMARY KEY (batch_id, tenant_id, ma_san_pham)
);
~~~

Quy trình:

1. Ghi raw events vào staging nguồn có ID.
2. Validate và ghi reject.
3. Phát hiện mâu thuẫn theo key/version.
4. Tính ROW_NUMBER, lấy rn=1.
5. Ghi vào staging_winner với PRIMARY KEY theo batch+business key.
6. Kiểm tra số winner, số lỗi và quy tắc.
7. MERGE/UPSERT từ staging_winner.
8. Ghi kết quả và commit.

### 28.1. Tại sao khóa winner có batch_id?

Vì mỗi batch có thể có một winner P01. Bảng winner lưu lịch sử chọn theo batch, nên khóa **(batch_id,tenant_id,ma_san_pham)**. Bảng current-state đích lại dùng **(tenant_id,ma_san_pham)**. Đây là hai phạm vi duy nhất khác nhau.

### 28.2. Khi nào chỉ cần CTE?

Nếu pipeline đơn giản và chỉ dùng winner một lần, CTE với ROW_NUMBER có thể đủ. Khi cần replay/audit/kiểm tra trước ghi hoặc nhiều bước downstream, bảng winner vật lý giúp truy vết và ràng buộc tốt hơn.

## 29. Đảm bảo repeatability và idempotency

**Deterministic winner** nghĩa là với cùng input và cùng policy, thuật toán chọn cùng dòng bất kể thứ tự vật lý.

**Idempotent apply** nghĩa là chạy lại cùng lô không làm trạng thái cuối thay đổi thêm.

Hai điều khác nhau.

### 29.1. Ví dụ winner đúng nhưng UPDATE không idempotent

Nếu MERGE có:

~~~sql
SET ton_kho = target.ton_kho + source.so_luong
~~~

chạy lại batch sẽ **cộng thêm lần nữa**. Dù source được dedupe còn một dòng, phép UPDATE vẫn không idempotent.

Nếu source chứa state đầy đủ, thường cập nhật giá trị tuyệt đối có guard theo version:

~~~sql
SET ton_kho = source.ton_kho
~~~

Nếu source chứa delta, cần event identity đã xử lý và ràng buộc chống replay.

### 29.2. Khóa phá hòa và replay

Nếu tie-break bằng ingest_id nhưng mỗi lần retry raw events lại được cấp ingest_id mới, winner có thể đổi chỉ vì lần tiếp nhận sau. Điều này chỉ an toàn nếu **payload đồng hạng tương đương** hoặc chính sách thực sự ưu tiên lần nhận sau. Với dữ liệu đồng version khác nhau, cần giải quyết mâu thuẫn, không dựa vào sự may rủi của retry.

## 30. Hai batch chạy đồng thời

Giả sử:

~~~text
Batch B1: P01 version 8
Batch B2: P01 version 9
~~~

Cả hai đều có một winner/khóa. Nhưng nếu B2 ghi xong, B1 có thể ghi lùi nếu nhánh UPDATE không so version.

Ngoài ra, khi target chưa có P01, hai transaction cùng thấy “chưa tồn tại” và cùng muốn INSERT. Do đó cần:

- **PRIMARY KEY/UNIQUE** ở target.
- Điều kiện version gắn với thao tác ghi.
- Transaction/isolation và locking phù hợp.
- Xử lý deadlock/serialization failure và duplicate-key races.
- Retry idempotent, giới hạn số lần và dùng cùng chính sách winner.

**MERGE không tự động biến toàn bộ thao tác thành một quy trình exactly-once trên mọi DBMS.**

### 30.1. Không chỉ SELECT trước rồi quyết định UPDATE

Nếu ứng dụng SELECT version=7, quyết định source v8 mới hơn, rồi gửi UPDATE không có điều kiện version, một giao dịch khác có thể đã ghi v9 trong thời gian chờ. So sánh phải được gắn với thao tác ghi tại DB hoặc bảo vệ bằng transaction/lock/version predicate.

## 31. Số liệu đối soát sau MERGE

Batch mẫu có 8 dòng thuộc 4 business keys:

~~~text
raw_rows = 8
distinct_business_keys = 4
winner_rows = 4
nonwinner_rows = 4
~~~

Nếu không có reject, số winner=4. Nhưng số dòng INSERT/UPDATE ở target **không nhất thiết bằng 4**, vì target có thể mới hơn hoặc bằng version nguồn.

Nên ghi:

| Chỉ số | Ý nghĩa |
|---|---|
| raw_rows | Số dòng tiếp nhận |
| valid_rows | Số dòng hợp lệ |
| rejected_rows | Số dòng sai schema/key/contract |
| duplicate_event_replays | Lần gửi lại cùng event |
| business_keys | Số khóa thực thể phân biệt |
| winner_rows | Số dòng đại diện được chọn |
| superseded_rows | Dòng hợp lệ không thắng |
| conflict_keys | Khóa có mâu thuẫn cần điều tra |
| inserted_keys | Khóa mới tại target |
| updated_keys | Khóa được cập nhật |
| stale_or_replayed_keys | Winner bỏ qua vì version không mới |
| deleted_keys | Khóa được xóa/đánh dấu xóa |
| failed_batches | Batch lỗi cần retry/đối soát |

**Số cặp trùng** và **số khóa bị trùng** là hai chỉ số khác nhau: một khóa có ba dòng tạo ba cặp ứng viên, nhưng vẫn chỉ là **một khóa cần xử lý**.

## 32. Performance: xếp hạng và MERGE quy mô lớn

ROW_NUMBER với PARTITION BY/ORDER BY có thể cần sắp xếp dữ liệu theo khóa và thứ tự ưu tiên. Khi batch lớn:

- Lọc **batch_id và các hàng hợp lệ** sớm.
- Có chỉ mục/thứ tự vật lý phù hợp trên staging nếu DBMS hỗ trợ.
- Tránh đưa các cột payload không cần thiết vào toàn bộ bước sort khi memory hạn chế.
- Xem execution plan và kiểm tra spill/sort.
- Cân nhắc nạp theo partition/batch nhưng vẫn đảm bảo version guard ở target.
- Không hạ yêu cầu tie-break chỉ để giảm chi phí sort.
- Kiểm tra skew: một business key có hàng triệu sự kiện sẽ tạo partition lớn.

Chỉ mục có thể hữu ích cho truy vấn lựa chọn:

~~~sql
CREATE INDEX idx_su_kien_batch_key_version
ON su_kien_san_pham (
    batch_id, tenant_id, ma_san_pham,
    event_version
);
~~~

Chỉ mục này **không bảo đảm** bỏ được mọi bước sort vì ORDER BY còn event_at, source_priority, ingested_at, ingest_id và kế hoạch DBMS có thể khác. Đo trên dữ liệu thật.

### 32.1. Batch xử lý song song

Có thể chia dữ liệu theo hash của business key, để mọi sự kiện cùng key đi tới cùng shard/worker. Nếu chỉ chia theo thời gian tiếp nhận, cùng P01 có thể nằm ở hai batch/worker khác nhau; cần version guard và cơ chế phối hợp để tránh ghi lùi.

## 33. Bảng lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Coi ON CONFLICT tự khử trùng nguồn | Cardinality error hoặc chọn sai bản | Dedupe trước |
| MERGE nhiều nguồn match một target | Lỗi hoặc không xác định | USING winner unique |
| DISTINCT trên toàn payload | Vẫn có nhiều dòng/khóa | ROW_NUMBER |
| MAX từng cột | Tạo tổ hợp không có trong nguồn | Giữ nguyên hàng winner |
| MAX(timestamp) rồi JOIN | Có thể trả nhiều dòng timestamp đồng hạng | Tie-break duy nhất |
| RANK/DENSE_RANK=1 | Giữ nhiều peer | ROW_NUMBER=1 |
| ROW_NUMBER thiếu khóa phá hòa | Winner không ổn định | ORDER BY toàn phần hoặc reject |
| Ưu tiên ingested_at thay version | Late event ghi lùi | Version/LSN chuẩn |
| Version số lưu dạng text | '9' có thể xếp sai với '10' | Kiểu số |
| PARTITION thiếu tenant | Gộp dữ liệu tenant khác | Đủ business key |
| Khóa NULL lọt vào MERGE | Không match hoặc trùng bất ngờ | Validate/NOT NULL |
| Chuẩn hóa key khác target | Gộp nhầm hoặc INSERT trùng | Canonical key đồng nhất |
| Chọn arbitrary giữa payload mâu thuẫn | Che lỗi nguồn | Quarantine |
| Lọc DELETE trước xếp hạng | Hồi sinh bản cũ | Xếp tất cả operation |
| Dedupe delta thành một event | Bỏ thay đổi trung gian | Replay theo thứ tự |
| Áp batch winner v8 đè target v9 | Ghi lùi trạng thái | Compare target version |
| Update bằng +delta khi retry | Tác động nhiều lần | Idempotency |
| MERGE ON có status filter | Existing row thành NOT MATCHED | ON chỉ business key |
| Không có UNIQUE target | Hai phiên tạo cùng key | Unique+transaction |
| Không lưu losers/rejects | Không audit được | Staging, metrics |
| Hạ SCD2 thành một current row | Mất lịch sử | Đúng grain target |
| Áp future price như current | Giá chưa hiệu lực xuất hiện sớm | As-of policy |
| Tin MERGE chống race | Concurrent inserts vẫn có thể tranh chấp | Lock/isolation/retry |
| Chỉ nhìn affected rows | Không biết vì sao stale/replay/reject | Đối soát nhiều chỉ số |

## 34. Bộ ca kiểm thử đề xuất

| Test | Mong đợi |
|---|---|
| Một key, một row | Chọn row đó |
| Một key, ba version | Chọn version cao theo policy |
| Hai row đồng version, payload giống | Một winner, có thể đánh dấu replay |
| Hai row đồng version, payload khác | Quarantine hoặc áp precedence được phê duyệt |
| event_at bằng nhau | Tie-break xác định |
| ingested_at muộn nhưng version cũ | Không chọn nhầm |
| T1/P01 và T2/P01 | Hai winner |
| key NULL | Reject theo rule |
| P01, p01, mã có space | Canonicalization đúng |
| RANK=1 | Phát hiện nhiều peer |
| MAX(version)+MAX(price) | Phát hiện pha giá giả |
| Target v9, source v8 | SKIP |
| Target v8, source v8 | No-op hoặc conflict |
| Winner DELETE | Không hồi sinh v7 |
| Delta +5 rồi -2 | Không bỏ sót delta |
| Batch chạy lại | Không nhân tác động |
| Hai batch đồng thời | Target cuối theo version cao |
| Target có UNIQUE khác | Conflict được giải thích |
| Version text '9','10' | Sắp số chính xác |
| Có version tương lai | Áp đúng as-of rule |
| SCD2/history target | Không mất bản lịch sử |
| Sự kiện sai kiểu/giá âm | Reject/constraint đúng |
| Lỗi giữa transaction | Không có batch applied dở dang |
| Duplicate event ID khác payload | Phát hiện producer violation |
| Quá nhiều sự kiện một key | Không vượt tài nguyên hoặc lỗi không được xử lý |

## 35. Bài tập thực hành có gợi ý đáp án

Dùng bảng ví dụ ở phần 2. Mỗi bài độc lập trừ khi ghi chú khác.

### Bài 1 — Khóa nghiệp vụ

Vì sao ingest_id không thích hợp làm khóa current-state của sản phẩm?

<details>
<summary>Đáp án</summary>

ingest_id xác định **mỗi lần tiếp nhận**. T1/P01 có ba ingest_id nhưng là một thực thể đích. Business key là **(tenant_id,ma_san_pham)**.

</details>

### Bài 2 — Đếm khóa trùng

Viết SQL tìm khóa có hơn một dòng trong batch.

<details>
<summary>Đáp án</summary>

~~~sql
SELECT tenant_id, ma_san_pham, COUNT(*) AS so_dong
FROM su_kien_san_pham
WHERE batch_id = 'B20261005'
GROUP BY tenant_id, ma_san_pham
HAVING COUNT(*) > 1;
~~~

</details>

### Bài 3 — Chọn P02

Vì sao version 3 của T1/P02 thắng version 2 dù version 2 có event_at muộn?

<details>
<summary>Đáp án</summary>

Vì chính sách giả định **event_version có thẩm quyền và được ưu tiên trước thời gian**. Winner là ingest_id 104, giá 200000.

</details>

### Bài 4 — Hai tenant

T1/P01 và T2/P01 có thuộc cùng partition không?

<details>
<summary>Đáp án</summary>

**Không** nếu partition theo cả tenant_id và ma_san_pham; là hai thực thể khác nhau.

</details>

### Bài 5 — DISTINCT

Vì sao DISTINCT tenant_id,ma_san_pham,event_version,gia không đảm bảo một dòng P01?

<details>
<summary>Đáp án</summary>

Vì P01 có nhiều version/giá khác nhau; DISTINCT chỉ bỏ các tổ hợp hoàn toàn giống nhau trên cột được SELECT.

</details>

### Bài 6 — MAX ghép sai

Cho P01 v7 giá 200000 và v8 giá 100000. MAX(version),MAX(gia) cho gì?

<details>
<summary>Đáp án</summary>

Cho (v8,200000), một tổ hợp **không có trong nguồn**. Cần chọn hàng gốc qua ROW_NUMBER.

</details>

### Bài 7 — RANK=1

Hai dòng cùng version tối đa. RANK=1 giữ bao nhiêu?

<details>
<summary>Đáp án</summary>

Có thể giữ **hai dòng**. RANK giữ peer group đồng hạng. Muốn đúng một dùng ROW_NUMBER với tie-break phù hợp.

</details>

### Bài 8 — CTE ROW_NUMBER

Viết CTE chọn một row/key theo version và ingest_id giảm dần.

<details>
<summary>Đáp án</summary>

~~~sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, ma_san_pham
            ORDER BY event_version DESC, ingest_id DESC
        ) AS rn
    FROM su_kien_san_pham s
)
SELECT * FROM ranked WHERE rn = 1;
~~~

Cần thêm batch filter, validation và conflict policy cho production.

</details>

### Bài 9 — Tie-break priority

Cùng version và event_at, source_priority=20 hay 10 thắng nếu priority cao hơn ưu tiên?

<details>
<summary>Đáp án</summary>

Priority **20** thắng. Với T1/P01 đó là ingest_id **103** nếu hợp đồng cho phép precedence theo priority.

</details>

### Bài 10 — Một dòng xác định có nghĩa hợp lệ?

Nếu hai dòng cùng version có hai giá, ingest_id lớn hơn có thể phá hòa. Điều này có tự chứng minh giá thắng đúng không?

<details>
<summary>Đáp án</summary>

**Không.** Một tie-break kỹ thuật chỉ giúp kết quả ổn định. Nếu contract cấm mâu thuẫn cùng version, phải quarantine/điều tra.

</details>

### Bài 11 — Scalar aggregate

Vì sao MAX(event_at) rồi JOIN trở lại có thể không còn duy nhất?

<details>
<summary>Đáp án</summary>

Vì nhiều hàng có thể cùng event_at cực đại; phép JOIN trả tất cả hàng khớp. Cần tie-break hoặc ROW_NUMBER.

</details>

### Bài 12 — WHERE rn cùng cấp

Có thể dùng WHERE rn=1 trong cùng SELECT vừa tạo ROW_NUMBER() AS rn theo SQL phổ biến không?

<details>
<summary>Đáp án</summary>

Thông thường **không**. Đặt window function trong CTE/derived table rồi lọc ngoài; QUALIFY chỉ có ở một số DBMS.

</details>

### Bài 13 — PostgreSQL

Nếu INSERT ... SELECT với ON CONFLICT DO UPDATE có hai source rows cùng key, PostgreSQL có bảo đảm lấy version lớn nhất không?

<details>
<summary>Đáp án</summary>

**Không.** Có thể lỗi cardinality vì một target row bị tác động hai lần. Dedupe nguồn trước.

</details>

### Bài 14 — Target mới hơn

Nguồn winner v8 nhưng đích đã v9. Khi policy chỉ nhận version cao hơn, phải làm gì?

<details>
<summary>Đáp án</summary>

**Không UPDATE** đích. Dùng điều kiện version trong nhánh upsert/merge tại DB.

</details>

### Bài 15 — SQL Server MERGE

Vì sao hai source rows cùng match một target với WHEN MATCHED UPDATE có thể thất bại?

<details>
<summary>Đáp án</summary>

Vì SQL Server không cho một hàng đích bị nhiều dòng nguồn UPDATE/DELETE trong tình huống này. Cần một winner/key trong USING.

</details>

### Bài 16 — Target chưa có

Nguồn có hai P01; target chưa có. MERGE có thể gặp lỗi nào?

<details>
<summary>Đáp án</summary>

Hai source rows có thể đều được coi NOT MATCHED và cùng INSERT, gây **vi phạm UNIQUE/PRIMARY KEY**.

</details>

### Bài 17 — MySQL

ON DUPLICATE KEY UPDATE có phải cơ chế chọn nguồn version cao nhất không?

<details>
<summary>Đáp án</summary>

**Không.** Đây là cơ chế xử lý unique conflict khi ghi. Chọn winner trước, sau đó dùng cú pháp upsert đúng phiên bản.

</details>

### Bài 18 — SQLite

SQLite xử lý conflict theo từng proposed row; có nên gửi nhiều version cùng key và để SQLite tự quyết định không?

<details>
<summary>Đáp án</summary>

**Không.** Cần winner policy hoặc version guard và staging rõ; engine không tự hiểu quy tắc mới nhất của nghiệp vụ.

</details>

### Bài 19 — QUALIFY

QUALIFY ROW_NUMBER ... =1 dùng trên BigQuery để làm gì?

<details>
<summary>Đáp án</summary>

Lọc kết quả window để lấy một dòng/partition. Đây là cú pháp không có ở mọi DBMS.

</details>

### Bài 20 — Version khác nguồn

ERP version=100, CRM version=12. Vì sao không nên mặc định ERP mới hơn?

<details>
<summary>Đáp án</summary>

Nếu version chỉ tăng nội bộ từng nguồn, hai số **không so sánh được**. Cần source authority, canonical sequence hoặc merge policy phù hợp.

</details>

### Bài 21 — NULL key

Khi ma_san_pham NULL nhưng key là bắt buộc, nên làm gì?

<details>
<summary>Đáp án</summary>

Reject/quarantine hoặc sửa theo chính sách trước merge. Không dùng NULL như một khóa định danh ổn định.

</details>

### Bài 22 — Tombstone

v7 ACTIVE, v8 DELETE. Winner current-state là gì?

<details>
<summary>Đáp án</summary>

**v8 DELETE**. Lọc DELETE trước ROW_NUMBER sẽ chọn nhầm v7 và hồi sinh dữ liệu.

</details>

### Bài 23 — Delta

Có event +5 ở v7 và -2 ở v8, cả hai chưa áp. Chỉ giữ v8 rồi cập nhật có đúng không?

<details>
<summary>Đáp án</summary>

**Không.** Delta cần áp đủ sự kiện chưa xử lý theo thứ tự và tránh replay. Chọn một version cuối chỉ đủ với state event đầy đủ.

</details>

### Bài 24 — Concurrency

Batch B1 v8 và B2 v9 đồng thời UPSERT. Cần những biện pháp gì?

<details>
<summary>Đáp án</summary>

UNIQUE target, so version trong thao tác ghi, transaction/isolation phù hợp, xử lý lỗi cạnh tranh/retry idempotent để target cuối không lùi về v8.

</details>

### Bài 25 — Chuẩn hóa mã

Nguồn có P01 và p01. Có nên luôn UPPER để gộp?

<details>
<summary>Đáp án</summary>

**Không nếu chưa có contract.** Nếu case-insensitive thì canonicalization có thể đúng; nếu case-sensitive đó là hai khóa. Phải thống nhất với target UNIQUE/ON/collation.

</details>

### Bài 26 — SCD2

Một khách có ba version hợp lệ trong lịch sử. Có nên chỉ giữ bản mới nhất trước khi ghi SCD2?

<details>
<summary>Đáp án</summary>

**Không.** Bảng SCD2 cần giữ lịch sử hiệu lực. Một winner/khóa hợp với bảng current-state, không mặc định hợp với bảng history.

</details>

### Bài 27 — Giá tương lai

Giá v9 chỉ bắt đầu hiệu lực tháng sau, còn v8 đang có hiệu lực hôm nay. Bảng current-as-of-today phải chọn gì?

<details>
<summary>Đáp án</summary>

**v8** theo khoảng hiệu lực tại hôm nay, không tự lấy v9 lớn nhất. Cần quy tắc as-of và mô hình lịch sử giá phù hợp.

</details>

### Bài 28 — Idempotency

Winner giống nhau nhưng UPDATE đặt ton_kho=ton_kho+5. Chạy batch hai lần xảy ra gì?

<details>
<summary>Đáp án</summary>

Tồn tăng tổng **10** thay vì 5. Cần idempotency key/event tracking hoặc state snapshot tuyệt đối và version guard.

</details>

### Bài 29 — Số dòng

Batch mẫu có tám dòng và bốn business keys. Nếu không reject, winner/nonwinner bao nhiêu?

<details>
<summary>Đáp án</summary>

**4 winner, 4 nonwinner**. Nhưng số UPDATE/INSERT thật có thể ít hơn do target đã có version mới hơn.

</details>

### Bài 30 — MERGE ON

Vì sao ON target.key=source.key AND target.status='ACTIVE' có thể gây duplicate insert?

<details>
<summary>Đáp án</summary>

Target cùng key nhưng STOP sẽ bị coi không match; MERGE có thể thử INSERT một bản trùng khóa. ON nên chỉ định danh thực thể; điều kiện trạng thái đặt ở nhánh hành động.

</details>

### Bài 31 — Winner từ cùng một payload

Vì sao không nên MAX(version),MAX(price),MAX(status) để xây current-state?

<details>
<summary>Đáp án</summary>

Vì mỗi MAX có thể chọn giá trị từ dòng khác nhau, tạo bản ghi không tồn tại trong nguồn. Dùng ROW_NUMBER để chọn **nguyên một hàng**.

</details>

### Bài 32 — Thiết kế pipeline

Hãy đề xuất thứ tự các bước xử lý batch có replay, nhiều version, mâu thuẫn và stale target.

<details>
<summary>Đáp án</summary>

1. Lưu raw + event/batch IDs.
2. Validate kiểu, key, version và payload.
3. Dedupe replay theo event ID.
4. Phát hiện và quarantine đồng version mâu thuẫn.
5. ROW_NUMBER theo full business key và precedence xác định.
6. Lưu/kiểm tra staging winner UNIQUE.
7. MERGE/UPSERT chỉ khi source mới hơn target.
8. Ghi inserted/updated/skipped/rejected metrics, transaction và retry idempotent.

</details>

## 36. Quy trình tư duy trước MERGE từ nguồn có khóa trùng

**Bước 1 — Định nghĩa grain của đích.** Đích current-state, snapshot ngày hay SCD2? Mỗi hàng đại diện cho đối tượng nào?

**Bước 2 — Xác định full business key.** Có tenant, currency, channel hoặc ngày hiệu lực không? Khóa có NULL không?

**Bước 3 — Phân loại nguyên nhân trùng.** Replay, nhiều version hợp lệ, xung đột cùng version hay trùng do canonicalization?

**Bước 4 — Viết rõ precedence.** Version, LSN, event_at, source_priority, ingested_at và tie-break theo thứ tự nào? Các version giữa nguồn có so được không?

**Bước 5 — Chọn hoặc quarantine.** Chỉ chọn ROW_NUMBER winner khi chính sách xác định được một bản hợp lệ. Nếu dữ liệu mâu thuẫn trái contract, phải báo lỗi.

**Bước 6 — Chứng minh nguồn duy nhất.** CTE rn=1 hoặc staging_winner có UNIQUE/PRIMARY KEY tương ứng.

**Bước 7 — Apply có điều kiện.** ON theo business key và cập nhật chỉ khi source mới hơn, có xử lý DELETE/tombstone.

**Bước 8 — Transaction và concurrency.** Unique target, locking/isolation, deadlock/serialization retry và idempotency.

**Bước 9 — Đối soát.** Lưu số raw, duplicate, conflict, winner, inserted, updated, stale, delete và lỗi.

**Bước 10 — Kiểm thử.** Hai key trùng version, hai tenant, NULL, late events, target mới hơn, retry, concurrent batches và history target.

## 37. Tổng kết cần ghi nhớ

1. **UPSERT/MERGE không tự giải quyết việc chọn đúng một dòng đại diện giữa nhiều dòng cùng khóa trong nguồn.**
2. Khóa kỹ thuật như ingest_id khác khóa nghiệp vụ của thực thể đích.
3. **ROW_NUMBER() OVER(PARTITION BY full_business_key ORDER BY precedence...)** là mẫu quan trọng để chọn một bản ghi đầy đủ theo thứ tự.
4. **DISTINCT** loại bản giống nhau trên các cột chọn; **GROUP BY + MAX từng cột** có thể pha giá; **RANK/DENSE_RANK=1** có thể giữ nhiều bản đồng hạng.
5. Thứ tự phải xác định và mang ý nghĩa nghiệp vụ. Ingested_at không luôn là sự kiện mới nhất; source version/LSN có thể đáng tin hơn.
6. Nếu cùng version nhưng payload khác, tie-break kỹ thuật không tự biến bản được chọn thành đúng. Cần quy tắc conflict hoặc quarantine.
7. Key canonicalization, NULL, collation và tenant phải thống nhất ở staging, PARTITION, target UNIQUE và MERGE ON.
8. PostgreSQL ON CONFLICT, SQL Server/Oracle MERGE, MySQL ON DUPLICATE KEY, SQLite UPSERT và BigQuery MERGE có hành vi khác nhau đối với duplicate source.
9. Winner của batch có thể vẫn **cũ hơn target**; thêm điều kiện version/precedence để ngăn ghi lùi.
10. DELETE/tombstone tham gia chọn winner; không lọc trước rồi hồi sinh bản cũ.
11. Với **delta**, không được bỏ toàn bộ sự kiện trung gian khi chúng chưa được áp.
12. Current-state, SCD2 và snapshot theo ngày có grain khác nhau; không dùng cùng một PARTITION BY một cách máy móc.
13. Một winner cố định chưa đảm bảo idempotency nếu UPDATE cộng/trừ/tăng giá lặp lại.
14. Unique constraint, transaction, concurrency control, audit và đối soát là phần của thiết kế đúng.
15. Pipeline phải **chọn đúng bản, chỉ apply khi hợp lệ và giải thích được vì sao những bản khác không thắng**.

### Tài liệu tham khảo theo DBMS

Khi triển khai, tham khảo tài liệu chính thức **đúng phiên bản**:

- **PostgreSQL Documentation:** INSERT ... ON CONFLICT, EXCLUDED, Window Functions, Unique Constraints, Transaction Isolation.
- **Microsoft Learn — SQL Server:** MERGE (Transact-SQL), ROW_NUMBER, OUTPUT, Unique Indexes, Locking and Isolation.
- **Oracle Database SQL Language Reference:** MERGE, ROW_NUMBER, Analytic Functions, Unique Constraints, ORA-30926.
- **MySQL Reference Manual:** INSERT ... ON DUPLICATE KEY UPDATE, ROW_NUMBER, InnoDB Transactions, Unique Indexes.
- **SQLite Documentation:** UPSERT, Window Functions, ROW_NUMBER, UNIQUE, Transactions.
- **BigQuery GoogleSQL:** MERGE Statement, QUALIFY, ROW_NUMBER, DML.

**Câu hỏi cốt lõi:** **“Mỗi khóa đích có bao nhiêu ứng viên trong nguồn, vì sao một dòng được chọn, và cơ chế nào ngăn phiên bản cũ hoặc sự kiện lặp làm hỏng trạng thái đúng?”**. Trả lời rõ ba câu hỏi này là nền tảng để xử lý nguồn có khóa trùng an toàn, xác định và có thể kiểm thử trong UPSERT/MERGE.

# Phân trang bằng khóa tiếp nối và điều kiện thứ tự ổn định

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Truy vấn nâng cao  
> **Mục tiêu:** Thiết kế keyset pagination (seek pagination) trong Oracle; tạo thứ tự kết quả xác định bằng khóa duy nhất; viết điều kiện lấy trang tiếp theo cho một hoặc nhiều cột sắp xếp; chọn index phù hợp; tạo cursor token an toàn; xử lý dữ liệu thay đổi giữa các lần gọi và phân biệt phân trang hiệu quả với yêu cầu đọc trên cùng một snapshot.

## 1. Vì sao cần phân trang bằng khóa tiếp nối?

Một màn hình quản trị cần hiển thị danh sách đơn hàng, mỗi lần 25 dòng. Cách phân trang quen thuộc là OFFSET:

~~~sql
SELECT order_id, created_at, customer_id, total_amount
FROM orders
WHERE status = :p_status
ORDER BY created_at DESC
OFFSET 10000 ROWS
FETCH NEXT 25 ROWS ONLY;
~~~

Câu lệnh yêu cầu Oracle bỏ qua 10.000 dòng đầu theo thứ tự rồi trả 25 dòng tiếp. Khi offset lớn, database thường phải xử lý nhiều dòng trước khi tới vùng cần trả. Hiệu quả còn tùy execution plan và index, nhưng OFFSET lớn thường không phù hợp với danh sách rất dài hoặc người dùng thường xuyên đi sâu nhiều trang.

Dữ liệu cũng có thể thay đổi giữa hai request. Nếu có hàng mới được chèn hoặc hàng cũ bị xóa trước vị trí offset, các dòng ở trang sau có thể dịch chuyển. Người dùng có thể thấy một dòng lặp lại hoặc bỏ sót một dòng.

**Keyset pagination** lấy trang kế tiếp dựa trên giá trị của dòng cuối cùng đã trả ở trang trước. Thay vì yêu cầu “bỏ qua 10.000 dòng”, ứng dụng yêu cầu “lấy các dòng đứng sau khóa cuối cùng này theo đúng thứ tự sắp xếp”. Cách này còn gọi là **seek pagination** vì database có thể tìm từ khóa trong index phù hợp thay vì đi qua toàn bộ offset.

Ví dụ, nếu thứ tự là **created_at DESC, order_id DESC**, cursor của trang trước có thể là **created_at = 2026-11-14 09:40:00** và **order_id = 850**. Trang tiếp theo lấy các hàng đứng sau cặp khóa đó theo cùng thứ tự.

## 2. Điều kiện tiên quyết: ORDER BY phải tạo thứ tự duy nhất

### 2.1. Một cột không duy nhất chưa đủ ổn định

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC;
~~~

Oracle sắp xếp theo thời gian giảm dần, nhưng không xác định thứ tự tương đối giữa các hàng có cùng timestamp. Ở hai lần thực thi, thứ tự của những hàng bằng nhau có thể khác do execution plan, index, parallelism hoặc thay đổi dữ liệu.

Nếu trang kết thúc giữa một nhóm hàng có cùng thời điểm, cursor chỉ chứa CREATED_AT sẽ không xác định chính xác hàng tiếp theo. Kết quả có thể bỏ sót hoặc lặp lại hàng.

### 2.2. Thêm khóa duy nhất làm tie-breaker

Nếu ORDER_ID là primary key, hãy dùng:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC;
~~~

Thứ tự được xác định theo cặp: CREATED_AT giảm dần; nếu thời điểm bằng nhau, ORDER_ID giảm dần. Vì ORDER_ID duy nhất, không có hai hàng nào có cùng toàn bộ bộ khóa sắp xếp.

> **Bộ cột trong ORDER BY phải tạo thành một total order cho tập kết quả.** Thường dùng cột nghiệp vụ, sau đó thêm primary key/unique key làm tie-breaker cuối cùng.

### 2.3. Ưu tiên khóa sắp xếp ổn định

Một cột có thể thay đổi trong lúc người dùng lật trang, ví dụ UPDATED_AT, STATUS hoặc PRIORITY. Nếu giá trị đó đổi, hàng có thể di chuyển từ sau cursor lên trước cursor hoặc ngược lại.

Để giảm nguy cơ, chọn khóa sắp xếp ít thay đổi hoặc bất biến theo nghiệp vụ, ví dụ CREATED_AT và primary key. Nếu yêu cầu sort theo cột có thể cập nhật, cần xác định rõ hệ thống chấp nhận thay đổi vị trí giữa các request hay cần đọc trên snapshot cố định.

## 3. Trang đầu tiên

Giả sử bảng:

~~~sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL,
    created_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    total_amount NUMBER(14,2) NOT NULL
);
~~~

Trên Oracle Database 12c trở lên:

~~~sql
SELECT order_id,
       customer_id,
       status,
       created_at,
       total_amount
FROM lab_orders
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

:p_status và :p_page_size là bind variables. Bind đúng datatype và giới hạn page size ở server (ví dụ 1–100) để client không thể yêu cầu một lượng dữ liệu tùy ý. Trang đầu chưa có cursor nên không có điều kiện khóa tiếp nối.

### 3.1. Biết còn trang tiếp theo không

Một cách thực tế là yêu cầu database trả page_size + 1 dòng:

~~~sql
SELECT order_id,
       customer_id,
       status,
       created_at,
       total_amount
FROM lab_orders
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_fetch_size ROWS ONLY;
~~~

Ứng dụng bind p_fetch_size = page_size + 1. Nếu nhận không quá page_size dòng thì không còn trang tiếp theo tại thời điểm truy vấn. Nếu nhận page_size + 1 dòng thì có ít nhất một dòng tiếp theo. Chỉ trả page_size dòng đầu cho người dùng.

Tạo cursor từ **dòng cuối cùng thực sự được trả**, không lấy dòng phụ thứ page_size + 1 làm cursor. Nếu lấy cursor từ dòng phụ, request sau sẽ bắt đầu sau dòng đó và bỏ qua chính dòng phụ chưa được hiển thị.

## 4. Trang tiếp theo với hai khóa DESC

Giả sử trang trước kết thúc tại:

~~~text
created_at = 2026-11-14 09:40:00.000000 +00:00
order_id   = 850
~~~

Thứ tự là:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Muốn lấy các hàng đứng sau dòng cuối trang, timestamp phải nhỏ hơn cursor timestamp; hoặc timestamp bằng nhau và order_id nhỏ hơn cursor ID.

~~~sql
SELECT order_id,
       customer_id,
       status,
       created_at,
       total_amount
FROM lab_orders
WHERE status = :p_status
  AND (
        created_at < :p_last_created_at
        OR (
            created_at = :p_last_created_at
            AND order_id < :p_last_order_id
        )
      )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Đây là so sánh từ điển (lexicographic comparison) được viết tường minh cho cặp khóa.

### 4.1. Minh họa ranh giới trang

~~~text
created_at             order_id
---------------------  --------
10:00:00               900
09:59:00               898
09:59:00               897
09:45:00               870
09:40:00               850  <-- cuối trang trước
09:40:00               849
09:39:00               848
09:38:00               840
~~~

Trang tiếp theo phải bắt đầu bằng 09:40 | 849. Điều kiện created_at < 09:40 một mình sẽ bỏ sót hàng này vì nó có cùng timestamp với cursor. Nhánh thứ hai xử lý nhóm timestamp trùng.

Chỉ viết created_at < :p_last_created_at sẽ bỏ sót những hàng còn lại cùng timestamp ở cuối trang. Chỉ viết order_id < :p_last_order_id có thể lấy cả hàng có timestamp mới hơn nhưng ID nhỏ hơn, làm sai thứ tự tổng thể. Phải biểu diễn đầy đủ thứ tự của mọi khóa trong ORDER BY.

## 5. Keyset cho thứ tự ASC

Nếu thứ tự là:

~~~sql
ORDER BY created_at ASC, order_id ASC
~~~

thì các hàng sau cursor có khóa lớn hơn:

~~~sql
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM lab_orders
WHERE status = :p_status
  AND (
        created_at > :p_last_created_at
        OR (
            created_at = :p_last_created_at
            AND order_id > :p_last_order_id
        )
      )
ORDER BY created_at ASC, order_id ASC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

| Hướng sắp xếp | So sánh hàng tiếp theo |
|---|---|
| ASC | Khóa sau lớn hơn cursor |
| DESC | Khóa sau nhỏ hơn cursor |

Với nhiều cột, phải áp dụng hướng so sánh cho từng cấp khóa. Không đổi tất cả dấu cùng chiều nếu ORDER BY có hướng trộn lẫn.

## 6. Nhiều cột sắp xếp và hướng hỗn hợp

Giả sử màn hình xếp ưu tiên:

~~~sql
ORDER BY priority DESC,
         created_at ASC,
         order_id ASC
~~~

Priority cao hơn đứng trước; cùng priority, thời điểm tạo sớm hơn đứng trước; nếu hai giá trị trên bằng nhau, order ID nhỏ hơn đứng trước.

Cursor lưu ba giá trị cuối trang: last_priority, last_created_at và last_order_id.

~~~sql
SELECT order_id, priority, created_at
FROM lab_tasks
WHERE
       priority < :p_last_priority
    OR (
           priority = :p_last_priority
       AND created_at > :p_last_created_at
    )
    OR (
           priority = :p_last_priority
       AND created_at = :p_last_created_at
       AND order_id > :p_last_order_id
    )
ORDER BY priority DESC,
         created_at ASC,
         order_id ASC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Priority nhỏ hơn là đứng sau trong thứ tự DESC. Nếu priority bằng, created_at lớn hơn là đứng sau trong thứ tự ASC. Nếu cả hai bằng, order_id lớn hơn là đứng sau trong thứ tự ASC.

Với thứ tự tổng quát:

~~~sql
ORDER BY k1 DESC, k2 ASC, k3 DESC, id ASC
~~~

predicate tiếp theo có dạng:

~~~sql
WHERE
       k1 < :last_k1
    OR (k1 = :last_k1 AND k2 > :last_k2)
    OR (k1 = :last_k1 AND k2 = :last_k2
                         AND k3 < :last_k3)
    OR (k1 = :last_k1 AND k2 = :last_k2
                         AND k3 = :last_k3
                         AND id > :last_id)
~~~

Với mỗi khóa, nếu các khóa trước bằng nhau mới xét khóa tiếp theo. Khóa cuối cùng nên làm bộ thứ tự duy nhất. Khi dùng biểu thức hoặc nhiều datatype, ghi rõ cursor contract về thứ tự, phép so sánh và kiểu dữ liệu.

## 7. NULL và thứ tự sắp xếp

So sánh với NULL không cho kết quả TRUE/FALSE thông thường mà cho UNKNOWN. Vì vậy keyset trên cột nullable cần xử lý rõ NULLS FIRST/NULLS LAST.

### 7.1. Ưu tiên khóa NOT NULL

Nếu nghiệp vụ cho phép, khai báo các cột cursor NOT NULL:

~~~sql
created_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
order_id NUMBER PRIMARY KEY
~~~

Đây là cách đơn giản nhất để viết predicate.

### 7.2. Nếu cột nullable, đưa null-rank vào thứ tự

Ví dụ muốn NULL đứng cuối khi sắp priority tăng dần:

~~~sql
ORDER BY
    CASE WHEN priority IS NULL THEN 1 ELSE 0 END ASC,
    priority ASC,
    order_id ASC
~~~

Thứ tự có ba khóa: null rank (0 cho giá trị khác NULL, 1 cho NULL); priority tăng dần trong nhóm không NULL; order ID tăng dần làm tie-breaker.

Cursor cần lưu null rank, priority (nếu khác NULL) và order ID. Khi cả cursor và hàng đang xét thuộc nhóm NULL, bỏ qua so sánh priority và dùng order_id.

~~~sql
WHERE null_rank > :p_last_null_rank
   OR (
        null_rank = :p_last_null_rank
        AND (
             (
                 :p_last_null_rank = 0
                 AND (
                      priority > :p_last_priority
                      OR (
                          priority = :p_last_priority
                          AND order_id > :p_last_order_id
                      )
                 )
             )
             OR (
                 :p_last_null_rank = 1
                 AND order_id > :p_last_order_id
             )
        )
   )
~~~

Trong truy vấn thực tế, NULL_RANK có thể là biểu thức CASE được lặp lại hoặc được đặt tên trong CTE/inline view. ORDER BY và predicate phải dùng cùng biểu thức.

Không dùng sentinel tùy tiện như NVL(priority, -999999) trừ khi miền dữ liệu bảo đảm giá trị đó không bao giờ hợp lệ. Nếu sentinel trùng dữ liệu thật, các khóa có thể bị gộp và predicate sai.

## 8. Index hỗ trợ keyset pagination

Với truy vấn lọc status, sau đó sắp xếp theo thời gian và ID:

~~~sql
WHERE status = :p_status
  AND (
       created_at < :p_last_created_at
       OR (
           created_at = :p_last_created_at
           AND order_id < :p_last_order_id
       )
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY
~~~

Một index ứng viên:

~~~sql
CREATE INDEX ix_lab_orders_page
ON lab_orders (
    status,
    created_at DESC,
    order_id DESC
);
~~~

STATUS được lọc bằng equality nên đứng trước các khóa sắp xếp. Nếu có thêm tenant filter, có thể đánh giá index:

~~~sql
CREATE INDEX ix_lab_orders_tenant_page
ON lab_orders (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
);
~~~

Đây chỉ là index ứng viên. Thiết kế thật phụ thuộc predicate, độ chọn lọc, hướng sort, số cột trả về, kích thước bảng, tần suất ghi và những truy vấn khác.

### 8.1. Tie-breaker trong index

Nếu ORDER BY là CREATED_AT DESC, ORDER_ID DESC, index chỉ có status và created_at có thể chưa biểu diễn đầy đủ thứ tự khi nhiều hàng trùng timestamp. Bổ sung order_id giúp index mang thứ tự đầy đủ.

Oracle có thể quét B-tree theo chiều ngược trong một số trường hợp; không phải lúc nào cũng cần tạo hai index ASC và DESC. Với thứ tự hỗn hợp, kiểm tra chiều từng cột và execution plan.

### 8.2. Không đưa mọi cột SELECT vào index một cách máy móc

Index rộng có thể giảm table access trong một số truy vấn nhưng tốn dung lượng, tăng chi phí INSERT/UPDATE/DELETE, redo/undo và công việc bảo trì. Chỉ tạo covering index khi workload và phép đo cho thấy lợi ích.

## 9. Kiểm tra execution plan

Keyset có thể giảm công việc so với OFFSET lớn, nhưng không bảo đảm Oracle luôn chọn index seek hoặc luôn nhanh hơn.

~~~sql
EXPLAIN PLAN FOR
SELECT order_id,
       created_at,
       customer_id,
       total_amount
FROM lab_orders
WHERE status = 'OPEN'
  AND (
       created_at < TIMESTAMP '2026-11-14 09:40:00'
       OR (
           created_at = TIMESTAMP '2026-11-14 09:40:00'
           AND order_id < 850
       )
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 25 ROWS ONLY;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Khi có quyền và đã thực thi với runtime statistics phù hợp, xem cursor plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Chú ý index range scan, predicate access/filter, STOPKEY/row-limiting operation, E-Rows so với A-Rows, buffers, physical reads, elapsed time và sort lớn. EXPLAIN PLAN là plan ước tính; DISPLAY_CURSOR với actual statistics giúp quan sát lần chạy thực tế khi thống kê đã được thu thập.

## 10. OFFSET và keyset: chọn theo nhu cầu

| Tiêu chí | OFFSET/FETCH | Keyset/seek |
|---|---|---|
| Xác định trang | Bỏ qua N dòng rồi lấy tiếp | Tìm dòng sau khóa cuối trang trước |
| Trang đầu | Đơn giản | Đơn giản |
| Đi sâu nhiều trang | Có thể phải xử lý nhiều dòng bị bỏ qua | Có thể seek từ index theo cursor |
| Nhảy trực tiếp tới trang số 500 | Thuận tiện hơn | Không tự nhiên nếu chưa có cursor |
| Thứ tự ổn định | Vẫn cần ORDER BY duy nhất | Bắt buộc thứ tự duy nhất |
| Insert/delete trước vị trí trang | Có thể dịch vị trí offset | Ít bị dịch do insert/delete trước cursor |
| Khóa sort bị cập nhật | Có thể lặp/mất dòng | Vẫn có thể lặp/mất dòng nếu khóa di chuyển |
| Cursor phía client | Không cần | Cần lưu khóa cuối trang |
| Phù hợp | Bảng nhỏ, trang số tùy ý | Feed, API next/previous, danh sách lớn |

Nếu người dùng cần nhảy trực tiếp tới trang 120, OFFSET dễ mô tả hơn. Nếu giao diện chủ yếu đi tiếp tuần tự hoặc cuộn liên tục, keyset thường đáng cân nhắc.

## 11. Dữ liệu thay đổi giữa các lần lấy trang

Keyset giải quyết vị trí tiếp theo theo khóa, nhưng không tự tạo snapshot nhất quán qua nhiều request.

### 11.1. Hàng mới được thêm trước cursor

Thứ tự DESC, cursor đang ở 09:40. Sau đó có đơn mới 10:05 được chèn. Điều kiện trang tiếp theo yêu cầu khóa nhỏ hơn cursor nên đơn 10:05 nằm trước cursor và không xuất hiện ở trang kế. Người dùng có thể refresh đầu danh sách để thấy đơn mới.

### 11.2. Hàng mới được thêm sau cursor

Nếu một hàng mới được chèn với timestamp nhỏ hơn cursor (ví dụ dữ liệu import backdated), nó có thể xuất hiện ở trang tiếp theo dù chưa tồn tại lúc mở trang đầu.

### 11.3. Hàng bị xóa

Xóa một hàng đã hiển thị ở trang trước thường không làm các hàng sau bị dịch chuyển như OFFSET. Hàng chưa được đọc mà bị xóa thì không thể xuất hiện trong trang tiếp theo.

### 11.4. Khóa sắp xếp bị cập nhật

Nếu một hàng đổi CREATED_AT hoặc PRIORITY giữa các request, nó có thể di chuyển qua cursor. Hàng đã hiển thị có thể di chuyển xuống sau cursor và xuất hiện lại; hàng chưa hiển thị có thể di chuyển lên trước cursor và bị bỏ qua; thay đổi filter có thể làm hàng đi vào/ra tập kết quả.

Dùng khóa bất biến nếu có thể. Nếu sort theo cột thay đổi và cần kết quả nhất quán, cần snapshot/version rõ ràng.

## 12. Snapshot nhất quán bằng SCN

Nếu nhiều trang phải phản ánh cùng trạng thái dữ liệu tại một thời điểm, có thể giữ SCN lúc bắt đầu phiên duyệt và dùng Flashback Query AS OF SCN khi hệ thống hỗ trợ.

Lấy SCN:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS snapshot_scn
FROM dual;
~~~

Dùng cùng SCN trong mỗi request:

~~~sql
SELECT order_id,
       created_at,
       customer_id,
       total_amount
FROM lab_orders AS OF SCN :p_snapshot_scn
WHERE status = :p_status
  AND (
       created_at < :p_last_created_at
       OR (
           created_at = :p_last_created_at
           AND order_id < :p_last_order_id
       )
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Trang đầu cũng phải dùng cùng SCN, chỉ bỏ predicate cursor. Nếu JOIN nhiều bảng, áp dụng cùng SCN cho các bảng cần đọc nhất quán.

Flashback Query cần dữ liệu UNDO còn khả dụng trong khoảng thời gian đọc; quyền truy cập và cấu hình database có thể cần DBA cấp. Phiên duyệt kéo dài có thể gặp lỗi khi UNDO không còn đủ, ví dụ ORA-01555 trong các tình huống liên quan. SCN snapshot không miễn phí; cần cân nhắc thời lượng phiên, tần suất request và chi phí vận hành. Không phải mọi bảng/đối tượng hoặc kiểu truy vấn đều hỗ trợ Flashback giống nhau.

Nếu không cần snapshot nghiêm ngặt, keyset với khóa bất biến thường đơn giản hơn.

## 13. Cursor token cho API

API có thể đóng gói khóa cuối trang thành opaque cursor token. Payload nội bộ minh họa:

~~~json
{
  "version": 1,
  "sort": "createdAt_desc_orderId_desc",
  "lastCreatedAt": "2026-11-14T09:40:00.123456Z",
  "lastOrderId": 850,
  "pageSize": 25,
  "filterHash": "...",
  "snapshotScn": null
}
~~~

Server serialize rồi ký token bằng HMAC hoặc mã hóa theo chính sách. Client chỉ gửi lại token; không tự sửa giá trị.

Các trường nên ràng buộc: version token; sort definition và hướng từng cột; giá trị chính xác của toàn bộ sort keys; filter/scope liên quan (tenant, trạng thái, khoảng ngày) hoặc fingerprint của chúng; page size nếu API giữ cố định; snapshot SCN nếu dùng Flashback; thời điểm hết hạn nếu cursor có vòng đời.

Token không được cho phép client thay tenant hoặc filter để vượt quyền. Dù token có chữ ký, server vẫn phải kiểm tra authorization ở mỗi request.

### 13.1. Giữ nguyên precision và datatype

Nếu cột là TIMESTAMP(6), cursor phải giữ đủ sáu chữ số phần giây. Làm tròn timestamp có thể khiến predicate bỏ sót hoặc lặp hàng ở ranh giới.

Với NUMBER, không chuyển ID lớn sang JavaScript Number nếu có nguy cơ vượt miền số nguyên chính xác; dùng chuỗi số hoặc định dạng lossless. Với TSTZ, giữ instant và quy ước timezone rõ ràng.

Không đưa SQL tùy ý vào token. Server ánh xạ sort mode qua allowlist và bind mọi giá trị. Cursor token cũng không thay thế xác thực/ủy quyền.

## 14. Java/JDBC: bind cursor values đúng kiểu

Ví dụ trang tiếp theo với CREATED_AT TIMESTAMP WITH TIME ZONE và ORDER_ID NUMBER:

~~~java
String sql = """
    SELECT order_id, customer_id, created_at, total_amount
    FROM lab_orders
    WHERE status = ?
      AND (
            created_at < ?
            OR (created_at = ? AND order_id < ?)
          )
    ORDER BY created_at DESC, order_id DESC
    FETCH FIRST ? ROWS ONLY
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, status);
    // Ví dụ driver hỗ trợ OffsetDateTime/JDBC 4.2 cho TSTZ.
    ps.setObject(2, lastCreatedAt);
    ps.setObject(3, lastCreatedAt);
    ps.setLong(4, lastOrderId);
    ps.setInt(5, pageSize);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Map từng hàng thành response.
        }
    }
}
~~~

Hai placeholder timestamp nhận cùng giá trị cursor và datatype tương thích cột. Oracle JDBC driver cần hỗ trợ mapping OffsetDateTime cho kiểu cột thực tế; kiểm tra version driver. Nếu dùng TIMESTAMP không timezone, contract phải quy định rõ múi giờ/instant. Page size phải được validate ở server trước khi bind. Query trang đầu không có predicate cursor; không nên dùng OR tùy tiện nếu làm query khó tối ưu.

Không nối cursor thành chuỗi SQL. Cursor là dữ liệu đầu vào; bind đúng kiểu giúp tránh lỗi quote, NLS, precision và SQL injection.

## 15. Lấy trang trước

Keyset tự nhiên hỗ trợ trang tiếp. Để lấy trang trước, cần cursor ở **đầu trang hiện tại** và đảo chiều phép tìm.

Thứ tự hiển thị chuẩn:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Muốn tìm các hàng đứng trước hàng đầu trang hiện tại, dùng khóa lớn hơn và đảo thứ tự truy vấn:

~~~sql
SELECT order_id,
       created_at,
       customer_id,
       total_amount
FROM lab_orders
WHERE status = :p_status
  AND (
       created_at > :p_first_created_at
       OR (
           created_at = :p_first_created_at
           AND order_id > :p_first_order_id
       )
  )
ORDER BY created_at ASC, order_id ASC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Truy vấn lấy các hàng gần ranh giới trước nhất bằng thứ tự ngược ASC. Ứng dụng đảo thứ tự các hàng vừa nhận trước khi hiển thị theo DESC.

Ví dụ thứ tự hiển thị là 100, 99, 98, 97, 96, 95. Trang hiện tại bắt đầu tại 96. Query previous lấy 97, 98, 99 theo ASC; ứng dụng đảo thành 99, 98, 97 để hiển thị theo DESC. Kiểm thử trang đầu/cuối, nhóm khóa trùng và trường hợp không còn trang trước.

## 16. Sort theo biểu thức hoặc cột do người dùng chọn

Nếu ORDER BY là CUSTOMER_NAME ASC, CUSTOMER_ID ASC, cursor lưu cả hai giá trị. Predicate tiếp theo:

~~~sql
WHERE customer_name > :p_last_customer_name
   OR (
       customer_name = :p_last_customer_name
       AND customer_id > :p_last_customer_id
   )
~~~

Cần chú ý collation, case-insensitive sort và accent sensitivity. Nếu ORDER BY dùng LOWER(customer_name), predicate phải dùng cùng biểu thức hoặc giá trị chuẩn hóa; index cần phù hợp (ví dụ function-based index).

Với CASE:

~~~sql
ORDER BY
    CASE WHEN priority = 'URGENT' THEN 0
         WHEN priority = 'NORMAL' THEN 1
         ELSE 2
    END,
    created_at DESC,
    order_id DESC
~~~

Cursor cần chứa rank của CASE, timestamp và ID. Predicate phải so sánh đúng ba khóa. Nếu biểu thức dùng thường xuyên, cân nhắc virtual column hoặc function-based index.

Nếu API hỗ trợ nhiều sort mode (mới nhất, số tiền cao nhất hoặc tên khách hàng), mỗi mode cần ORDER BY cố định từ allowlist, bộ cursor keys đầy đủ và unique, predicate seek đúng hướng từng cột, index ứng viên phù hợp và token version/sort mode rõ ràng. Không dùng một predicate cursor chung cho mọi sort mode.

## 17. FETCH FIRST và Oracle 11g

### 17.1. Oracle 12c trở lên

~~~sql
SELECT ...
FROM ...
WHERE ...
ORDER BY ...
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Có thể dùng FETCH NEXT trong các ngữ cảnh tương đương. Đối chiếu đúng release để xác nhận rowcount bind được hỗ trợ theo cú pháp đang dùng.

### 17.2. Oracle 11g với ROWNUM

Nếu hệ thống chưa hỗ trợ FETCH FIRST, dùng inline view với ORDER BY rồi giới hạn ở query block ngoài:

~~~sql
SELECT *
FROM (
    SELECT order_id,
           customer_id,
           created_at,
           total_amount
    FROM lab_orders
    WHERE status = :p_status
      AND (
           created_at < :p_last_created_at
           OR (
               created_at = :p_last_created_at
               AND order_id < :p_last_order_id
           )
      )
    ORDER BY created_at DESC, order_id DESC
)
WHERE ROWNUM <= :p_page_size;
~~~

ROWNUM được áp dụng ở query block ngoài sau khi inline view xác định thứ tự. Nếu đặt ROWNUM cùng query block trước khi sắp xếp, có thể lấy một tập hàng rồi mới sort, không phải N hàng đầu theo thứ tự mong muốn.

Nếu đã dùng cursor predicate để tìm phần sau của thứ tự, thông thường không cần thêm OFFSET. Thêm OFFSET lớn vẫn buộc database bỏ qua dòng và làm mất lợi thế seek.

## 18. Có cần đếm tổng số kết quả?

Giao diện có thể muốn hiển thị “1–25 trên tổng 82.341 đơn”. Để biết tổng chính xác, cần COUNT trên cùng tập filter:

~~~sql
SELECT COUNT(*) AS total_rows
FROM lab_orders
WHERE status = :p_status;
~~~

COUNT có thể tốn kém với tập dữ liệu lớn, filter phức tạp hoặc JOIN. Keyset không cần tổng số trang để lấy trang tiếp. Có thể không hiển thị tổng và chỉ báo “còn trang tiếp” bằng page_size + 1; chạy COUNT riêng khi cần; hoặc dùng số ước lượng/cache nếu nghiệp vụ chấp nhận và giao diện ghi rõ tính gần đúng. Dùng cùng snapshot SCN cho COUNT và dữ liệu trang nếu phải nhất quán tại cùng thời điểm.

## 19. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| ORDER BY trên cột không duy nhất | Thứ tự giữa các hàng bằng nhau không xác định | Thêm PK/unique key làm tie-breaker |
| Cursor chỉ giữ cột đầu | Bỏ sót hàng trùng giá trị ở ranh giới | Lưu toàn bộ sort keys |
| DESC nhưng dùng > cho trang tiếp | Lấy hàng đứng trước cursor | Với DESC, dùng < theo từng khóa |
| ASC nhưng dùng < | Lấy sai phía | Với ASC, dùng > |
| Sort direction hỗn hợp nhưng đổi mọi dấu cùng chiều | Predicate không khớp ORDER BY | Viết từng nhánh lexicographic theo hướng từng cột |
| Khóa sort nullable không xử lý NULL | So sánh thành UNKNOWN, có thể bỏ sót hàng | NOT NULL hoặc null-rank và predicate tương ứng |
| Timestamp bị làm tròn trong cursor | Lặp/bỏ sót hàng gần ranh giới | Giữ đủ precision và datatype |
| Không có tie-breaker duy nhất | Nhiều hàng có cùng toàn bộ cursor key | Thêm PK/unique key cuối |
| Khóa sort thay đổi giữa request | Hàng có thể di chuyển qua cursor | Dùng khóa bất biến hoặc snapshot |
| Filter thay đổi giữa các trang | Các trang không còn cùng tập kết quả | Gắn filter vào cursor contract |
| Token bị client sửa | Thay đổi vị trí hoặc phạm vi truy vấn | Ký token, validate và authorize lại |
| OFFSET rất lớn | Phải xử lý nhiều dòng bị bỏ qua | Keyset khi điều hướng tuần tự |
| Tin keyset tự tạo snapshot | Dữ liệu mới/cập nhật vẫn có thể xuất hiện | AS OF SCN nếu cần snapshot nghiêm ngặt |
| Index quá rộng | Tăng chi phí ghi và lưu trữ | Thiết kế theo workload, đo plan |
| Cursor lấy từ dòng lookahead chưa trả | Bỏ qua dòng phụ ở trang kế | Cursor từ dòng cuối thực sự hiển thị |

## 20. Bài thực hành trên schema lab

Các ví dụ chỉ tạo bảng trong schema được phép sử dụng.

### 20.1. Tạo bảng và dữ liệu thử

~~~sql
CREATE TABLE lab_page_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20 CHAR) NOT NULL,
    created_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    total_amount NUMBER(14,2) NOT NULL
);

INSERT INTO lab_page_orders VALUES (
    101, 10, 'OPEN',
    TIMESTAMP '2026-11-14 10:00:00 +00:00', 100
);
INSERT INTO lab_page_orders VALUES (
    102, 11, 'OPEN',
    TIMESTAMP '2026-11-14 09:59:00 +00:00', 200
);
INSERT INTO lab_page_orders VALUES (
    103, 12, 'OPEN',
    TIMESTAMP '2026-11-14 09:59:00 +00:00', 300
);
INSERT INTO lab_page_orders VALUES (
    104, 13, 'OPEN',
    TIMESTAMP '2026-11-14 09:58:00 +00:00', 400
);
INSERT INTO lab_page_orders VALUES (
    105, 14, 'OPEN',
    TIMESTAMP '2026-11-14 09:57:00 +00:00', 500
);
COMMIT;
~~~

### 20.2. Tạo index

~~~sql
CREATE INDEX ix_lab_page_orders
ON lab_page_orders (
    status,
    created_at DESC,
    order_id DESC
);
~~~

### 20.3. Trang đầu (page size = 2)

~~~sql
SELECT order_id, created_at, total_amount
FROM lab_page_orders
WHERE status = 'OPEN'
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 2 ROWS ONLY;
~~~

Kết quả:

~~~text
101 | 10:00:00
103 | 09:59:00
~~~

Hai đơn 102 và 103 có cùng timestamp; order_id DESC quyết định 103 đứng trước 102.

### 20.4. Trang tiếp theo

Dòng cuối trang trước là (09:59:00 +00:00, 103):

~~~sql
SELECT order_id, created_at, total_amount
FROM lab_page_orders
WHERE status = 'OPEN'
  AND (
       created_at < TIMESTAMP '2026-11-14 09:59:00 +00:00'
       OR (
           created_at = TIMESTAMP '2026-11-14 09:59:00 +00:00'
           AND order_id < 103
       )
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 2 ROWS ONLY;
~~~

Kết quả:

~~~text
102 | 09:59:00
104 | 09:58:00
~~~

Đơn 102 có timestamp bằng cursor nhưng ID nhỏ hơn, nên được trả ở trang sau. Nếu chỉ dùng created_at < cursor, đơn 102 bị bỏ sót.

### 20.5. Trang cuối

Cursor là (09:58:00, 104):

~~~sql
SELECT order_id, created_at, total_amount
FROM lab_page_orders
WHERE status = 'OPEN'
  AND (
       created_at < TIMESTAMP '2026-11-14 09:58:00 +00:00'
       OR (
           created_at = TIMESTAMP '2026-11-14 09:58:00 +00:00'
           AND order_id < 104
       )
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 2 ROWS ONLY;
~~~

Kết quả còn lại là đơn 105.

### 20.6. So sánh OFFSET

~~~sql
SELECT order_id, created_at, total_amount
FROM lab_page_orders
WHERE status = 'OPEN'
ORDER BY created_at DESC, order_id DESC
OFFSET 2 ROWS FETCH NEXT 2 ROWS ONLY;
~~~

Với dữ liệu không đổi, kết quả logic giống trang thứ hai. Nhưng keyset xác định trang kế bằng cursor, không cần OFFSET 2. Trên tập dữ liệu lớn, khác biệt về công việc có thể rõ hơn.

### 20.7. Thử dữ liệu mới giữa hai request

1. Lấy trang đầu và giữ cursor cuối.
2. Chèn một order mới có created_at mới hơn cursor.
3. Chạy query trang tiếp với cursor cũ.
4. Quan sát order mới nằm trước cursor nên không xuất hiện ở trang kế.
5. Refresh trang đầu để thấy order mới.

Sau đó chèn một order có created_at cũ hơn cursor. Hàng này có thể xuất hiện ở trang tiếp. Đây là minh họa rằng keyset không tự tạo snapshot.

### 20.8. Dọn bảng lab

~~~sql
DROP TABLE lab_page_orders PURGE;
~~~

Chỉ xóa đối tượng lab do chính bạn tạo.

## 21. Quy trình thiết kế API phân trang

API có thể có hai dạng request:

~~~http
GET /api/orders?status=OPEN&pageSize=25
GET /api/orders?cursor=<opaque-token>
~~~

Server thực hiện:

1. Xác thực người dùng và tenant.
2. Nếu không có cursor, dùng query trang đầu.
3. Nếu có cursor, kiểm tra chữ ký, version, expiration và sort/filter contract.
4. Ánh xạ sort mode qua allowlist.
5. Bind cursor keys với datatype chính xác.
6. Lấy page_size + 1 dòng để xác định còn trang.
7. Trả page_size dòng và next cursor từ dòng cuối thực sự được trả.
8. Áp dụng lại authorization và filter bắt buộc.
9. Không trả token nếu không còn trang tiếp.

Response minh họa:

~~~json
{
  "items": [
    {
      "orderId": 103,
      "createdAt": "2026-11-14T09:59:00Z",
      "totalAmount": 300
    }
  ],
  "hasNextPage": true,
  "nextCursor": "<opaque-token>"
}
~~~

Không bắt buộc API trả totalCount. Nếu giao diện cần tổng số, xử lý bằng truy vấn COUNT riêng và xác định rõ nó có cùng snapshot với dữ liệu trang hay không.

## 22. Checklist trước khi đưa vào production

- [ ] ORDER BY có tie-breaker duy nhất ở cuối.
- [ ] Cursor chứa toàn bộ giá trị sort key của dòng cuối trang.
- [ ] Predicate tiếp theo phản ánh đúng thứ tự ASC/DESC của từng cột.
- [ ] Các khóa sort nullable được xử lý NULLS FIRST/LAST nhất quán.
- [ ] Datatype và precision của cursor giữ nguyên giá trị database.
- [ ] Filter, tenant scope và sort mode được giữ nhất quán giữa các trang.
- [ ] Cursor token được ký/kiểm tra và có version.
- [ ] Server validate page size và authorization ở mỗi request.
- [ ] Index được thiết kế theo filter + sort và đã xem execution plan.
- [ ] Dùng page_size + 1 nếu cần biết còn trang mà không chạy COUNT.
- [ ] Cursor được tạo từ dòng cuối thực sự trả, không phải dòng lookahead.
- [ ] Nếu khóa sort thay đổi, đã xác định chính sách snapshot/nhất quán.
- [ ] Nếu cần cùng snapshot, đã đánh giá AS OF SCN và UNDO retention.
- [ ] Đã kiểm thử timestamp trùng, ID tie-breaker, trang đầu/cuối và insert/delete/update giữa request.
- [ ] Đã so sánh với OFFSET trên dữ liệu có kích thước và phân bố đại diện.

## 23. Ghi nhớ cốt lõi

- **Keyset pagination** lấy trang kế dựa trên khóa của dòng cuối trang trước, không dựa trên số dòng cần bỏ qua.
- **ORDER BY phải xác định duy nhất thứ tự**; thêm primary key/unique key làm tie-breaker.
- Cursor cần giữ **mọi sort key**, với đúng datatype, precision và hướng sắp xếp.
- Với DESC, hàng tiếp theo thường có khóa nhỏ hơn; với ASC, hàng tiếp theo có khóa lớn hơn. Với thứ tự hỗn hợp, so sánh từng cấp theo hướng riêng.
- **NULL cần quy tắc rõ ràng**; NOT NULL giúp predicate đơn giản hơn.
- Index thường bắt đầu bằng filter equality, sau đó là sort keys và tie-breaker; xác nhận bằng execution plan.
- Keyset có thể tránh chi phí bỏ qua offset lớn, nhưng không bảo đảm optimizer luôn chọn index seek.
- Keyset ít bị dịch trang do insert/delete trước cursor, nhưng **không tự tạo snapshot**.
- Nếu khóa sắp xếp thay đổi, hàng vẫn có thể di chuyển qua ranh giới và bị lặp hoặc bỏ qua.
- Dùng AS OF SCN khi nghiệp vụ cần các trang đọc trên cùng snapshot và môi trường đáp ứng yêu cầu Flashback/UNDO.
- Cursor token phải được validate, gắn với filter/sort contract và không thay thế authorization.
- Nếu cần nhảy trực tiếp tới trang số bất kỳ, OFFSET có thể phù hợp hơn; nếu điều hướng tuần tự qua danh sách lớn, keyset thường đáng cân nhắc.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — SELECT, row_limiting_clause, ORDER BY, ROWNUM và Flashback Query.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/) — access paths, index range scans, stopkey và query optimization.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — execution plans, runtime statistics và DBMS_XPLAN.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — B-tree indexes, consistency và multiversion read consistency.
- [Oracle Database Application Developer's Guide - Fundamentals](https://docs.oracle.com/en/database/) — bind variables, SQL execution và application design.

Cú pháp FETCH FIRST, bind row limit, Flashback Query và chi tiết optimizer cần được đối chiếu theo đúng Oracle release và JDBC driver. Hãy xác nhận tính đúng đắn bằng thứ tự duy nhất và test dữ liệu ở ranh giới trang; sau đó đo hiệu năng trên workload đại diện.

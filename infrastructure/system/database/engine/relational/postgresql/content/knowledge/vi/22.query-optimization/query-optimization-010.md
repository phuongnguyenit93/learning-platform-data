# Ảnh hưởng của CTE, hàm tự định nghĩa và rào cản tối ưu trong PostgreSQL

**Common Table Expression (CTE)** và **hàm tự định nghĩa** giúp SQL ngắn gọn, dễ chia thành những phần có tên, tái sử dụng logic và đóng gói quy tắc nghiệp vụ. Nhưng một câu SQL dễ đọc hơn **không nhất thiết** có kế hoạch thực thi tốt hơn. Tùy phiên bản PostgreSQL, số lần tham chiếu, độ biến động của hàm và những ràng buộc ngữ nghĩa, planner có thể gộp các phần lại để tối ưu chung, hoặc phải giữ một **ranh giới tối ưu** (*optimization barrier*).

Một ranh giới tối ưu có thể khiến:

- Điều kiện `WHERE</BT> ở bên ngoài không được đẩy sâu vào phần truy vấn bên trong (*predicate pushdown*).
- Planner không đổi được thứ tự JOIN qua một bước trung gian.
- Một tập dữ liệu lớn bị tính hoặc lưu tạm trước khi chỉ còn vài hàng thực sự cần.
- Logic SQL bên trong hàm bị biểu diễn như một `Function Scan</BT> hoặc lời gọi hàm, thay vì xuất hiện dưới dạng các bảng, filter và index path mà planner có thể tối ưu trực tiếp.
- Ngược lại, một biểu thức tốn kém bị tính lặp lại khi phần truy vấn được gộp vào nhiều nơi, làm kế hoạch chậm hơn dù đã loại bỏ materialization.

Vì vậy, mục tiêu không phải “luôn bỏ CTE” hay “luôn dùng `NOT MATERIALIZED`”. Mục tiêu là **hiểu khi nào PostgreSQL được phép tối ưu xuyên qua một ranh giới, khi nào ranh giới đó hữu ích, và cách đo bằng EXPLAIN**.

Bài học thuộc chương **Tối ưu truy vấn** trong module *Database Engine Relational PostgreSQL*. Nội dung giải thích CTE từ PostgreSQL 12 trở đi, hành vi phiên bản cũ, `MATERIALIZED</BT> và `NOT MATERIALIZED</BT>, CTE đệ quy và CTE ghi dữ liệu, SQL-function inlining, PL/pgSQL, volatility, `COST</BT>/`ROWS</BT>, tính sargable của predicate, kế hoạch gọi hàm, và cách chẩn đoán hiệu năng thực tế.

## 1. Planner tối ưu điều gì?

PostgreSQL lập kế hoạch trước khi chạy phần lớn truy vấn thông thường. Planner cân nhắc nhiều cách thực thi và ước lượng chi phí dựa trên:

- Số hàng của bảng và độ chọn lọc của điều kiện.
- Thống kê dữ liệu do `ANALYZE` thu thập.
- Indexes và cách truy cập bảng.
- Thứ tự JOIN, kiểu JOIN, phương pháp sắp xếp và tổng hợp.
- Chi phí CPU, I/O và độ song song.
- Khả năng biến đổi lại biểu thức SQL mà vẫn giữ đúng ngữ nghĩa.
- Các ràng buộc khiến một phần truy vấn không thể hoặc không nên bị biến đổi tự do.

Ví dụ:

~~~sql
SELECT event_id, tenant_id
FROM events
WHERE tenant_id = 42
  AND event_type = 'purchase';
~~~

Planner có thể cân nhắc Seq Scan, Index Scan, Bitmap Scan hoặc những đường truy cập khác, tùy schema và thống kê.

Nhưng nếu cùng logic được bọc trong một CTE bắt buộc materialize hoặc một hàm khó inline, planner có thể không nhìn thấy **toàn bộ predicate cùng lúc** khi tối ưu phần quét bảng.

### 1.1. Rào cản tối ưu là gì?

Một *optimization barrier* là ranh giới khiến một số phép biến đổi đại số hoặc thay đổi thứ tự thực thi **không được phép hoặc không khả thi**. Ranh giới đó có thể đến từ:

- Yêu cầu materialize một CTE.
- Truy vấn đệ quy.
- Lệnh ghi dữ liệu trong CTE.
- Hàm `VOLATILE` hoặc có tác dụng phụ.
- Hàm PL/pgSQL không thể inline như biểu thức SQL thông thường.
- `SECURITY DEFINER`, cấu hình `SET</BT> gắn với hàm, các điều kiện an toàn/phân quyền.
- Các toán tử như `LIMIT</BT>, `DISTINCT</BT>, aggregate và window functions, vốn có những giới hạn biến đổi do ngữ nghĩa.
- `security_barrier</BT> view hoặc một số yêu cầu bảo vệ bảo mật.

Không phải mọi yếu tố trên cùng là một cơ chế. Chúng có điểm chung là **giới hạn không gian tối ưu mà planner có thể xét**.

### 1.2. Rào cản không luôn xấu

Một ranh giới có thể giúp:

- Tránh tính một biểu thức đắt đỏ nhiều lần.
- Đảm bảo một kết quả trung gian được dùng chung bởi nhiều nhánh.
- Giữ ngữ nghĩa của thao tác có tác dụng phụ.
- Bảo vệ quy tắc an toàn khi có quyền đặc biệt.
- Cho phép cấu trúc truy vấn mà không thể biểu diễn bằng phép gộp đơn giản.

Vấn đề cần giải quyết là **chọn đúng ranh giới cho đúng workload**.

## 2. CTE là gì?

CTE được khai báo với `WITH</BT> trước câu SQL chính:

~~~sql
WITH selected_events AS (
    SELECT event_id, tenant_id, event_type
    FROM events
    WHERE event_type = 'purchase'
)
SELECT *
FROM selected_events
WHERE tenant_id = 42;
~~~

`selected_events` là tên của một kết quả truy vấn dùng trong phạm vi statement đó.

### 2.1. CTE là cấu trúc đặt tên, không mặc định là bảng tạm vật lý

Người học thường hình dung:

~~~text
Bước 1: chạy selected_events và ghi hết vào bảng tạm.
Bước 2: SELECT từ bảng tạm.
~~~

Đây có thể là cách thực thi của **materialized CTE**, nhưng **không phải quy luật chung cho mọi CTE** trên PostgreSQL hiện đại.

Planner có thể gộp CTE vào truy vấn ngoài và tối ưu như một truy vấn chung.

### 2.2. CTE khác subquery ở điểm nào?

Cùng logic có thể viết:

~~~sql
SELECT *
FROM (
    SELECT event_id, tenant_id, event_type
    FROM events
    WHERE event_type = 'purchase'
) AS selected_events
WHERE tenant_id = 42;
~~~

Về ý nghĩa tập kết quả, hai truy vấn có thể tương đương. Nhưng cách planner biến đổi phụ thuộc:

- PostgreSQL version.
- Số lần CTE được tham chiếu.
- CTE có recursive hay không.
- CTE có lệnh ghi hay hàm volatile hay không.
- Chỉ thị `MATERIALIZED</BT>/`NOT MATERIALIZED</BT>.
- Cấu trúc SQL bên trong như aggregate, LIMIT hoặc window.

### 2.3. CTE giúp tổ chức logic

CTE rất hữu ích để đặt tên cho các bước:

~~~sql
WITH filtered AS (
    SELECT ...
),
aggregated AS (
    SELECT ...
    FROM filtered
    GROUP BY ...
)
SELECT ...
FROM aggregated;
~~~

Không có lý do phải bỏ CTE chỉ vì lo ngại “WITH chậm”. Cần xem **kế hoạch cụ thể**.

## 3. PostgreSQL trước và từ phiên bản 12: khác biệt quan trọng

Một nguồn nhầm lẫn lớn đến từ những bài tối ưu SQL viết cho PostgreSQL cũ.

### 3.1. PostgreSQL 11 trở về trước

Trong các phiên bản PostgreSQL cũ trước 12, CTE SELECT thông thường được xem là một **optimization fence** mạnh hơn: planner không tự gộp CTE vào truy vấn ngoài theo cơ chế hiện đại.

Một câu:

~~~sql
WITH x AS (
    SELECT *
    FROM big_table
)
SELECT *
FROM x
WHERE id = 42;
~~~

có thể cần xử lý kết quả trung gian rộng hơn nhiều so với câu lọc trực tiếp, do predicate bên ngoài không được đẩy vào phần tính CTE theo cách tối ưu.

### 3.2. PostgreSQL 12 trở đi

Với CTE **không đệ quy**, là `SELECT</BT> không có tác dụng phụ theo những quy tắc của PostgreSQL, planner có thể **fold/inline** nó vào truy vấn cha.

Quy tắc mặc định quan trọng:

- CTE đủ điều kiện và **được tham chiếu một lần** thường được gộp vào truy vấn ngoài.
- CTE đủ điều kiện nhưng **được tham chiếu nhiều lần** thường được materialize theo mặc định.
- `MATERIALIZED</BT> có thể yêu cầu giữ một ranh giới materialization.
- `NOT MATERIALIZED</BT> có thể yêu cầu folding, kể cả khi có nhiều tham chiếu, nhưng có thể làm công việc bị lặp.
- Recursive CTE, CTE ghi dữ liệu hoặc CTE có những tính chất không cho phép folding **không trở thành inline chỉ nhờ thêm NOT MATERIALIZED**.

Các từ “thường” và “đủ điều kiện” rất quan trọng. Không nên mô tả PostgreSQL 12+ là “mọi CTE đều được inline”.

### 3.3. Kiểm tra phiên bản

~~~sql
SHOW server_version;
SHOW server_version_num;
~~~

Nếu cần hỗ trợ PostgreSQL 11, không áp dụng nguyên mẫu cú pháp `AS MATERIALIZED` hoặc `AS NOT MATERIALIZED` của các phiên bản mới mà không kiểm tra.

### 3.4. Không áp đặt lịch sử lên hệ thống hiện tại

Một câu truyền miệng như “CTE luôn chặn pushdown trong PostgreSQL” là **không còn đúng chung**. Ngược lại, “CTE mới không bao giờ materialize” cũng sai.

## 4. CTE được tham chiếu một lần: folding và predicate pushdown

Xem:

~~~sql
WITH events_filtered AS (
    SELECT event_id, tenant_id, occurred_at, payload
    FROM events
    WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
)
SELECT event_id, payload
FROM events_filtered
WHERE tenant_id = 42;
~~~

Với CTE SELECT đủ điều kiện và được dùng một lần trên PostgreSQL hiện đại, planner có thể xem điều kiện:

~~~sql
WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
  AND tenant_id = 42
~~~

cùng trong bước truy cập bảng `events`.

### 4.1. Vì sao điều này có lợi?

Giả sử index là:

~~~sql
CREATE INDEX events_tenant_time_idx
ON events (tenant_id, occurred_at);
~~~

Nếu planner thấy cả hai predicate khi chọn access path, nó có thể tận dụng index phù hợp hơn so với chỉ nhìn điều kiện thời gian ở phần CTE bên trong.

### 4.2. Không có nghĩa bắt buộc dùng index

Planner có thể vẫn chọn Seq Scan nếu:

- Bảng nhỏ.
- Điều kiện chọn tỷ lệ lớn dữ liệu.
- Dữ liệu trong cache và chi phí scan thấp.
- Index không đủ phù hợp.
- Thống kê ước lượng số hàng không cho thấy lợi ích.

Hãy kiểm tra `EXPLAIN</BT> chứ không suy luận từ cú pháp `WITH</BT>.

### 4.3. Folding không thay kết quả logic

Planner chỉ được thực hiện những biến đổi giữ ngữ nghĩa SQL. Một CTE có LIMIT hoặc cấu trúc làm thay đổi kết quả khi đẩy điều kiện không phải tự động được biến thành bất kỳ query khác theo ý muốn.

## 5. AS MATERIALIZED: cố ý giữ một kết quả trung gian

Khai báo:

~~~sql
WITH events_filtered AS MATERIALIZED (
    SELECT event_id, tenant_id, occurred_at, payload
    FROM events
    WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
)
SELECT event_id, payload
FROM events_filtered
WHERE tenant_id = 42;
~~~

Trong trường hợp này, CTE có một ranh giới materialization. Điều kiện `tenant_id=42` nằm **ngoài** CTE và không được đẩy vào phần truy cập bảng bên trong như một điều kiện bình thường của CTE.

### 5.1. Mô hình hình dung

~~~text
Không materialize, đủ điều kiện folding:
  Scan events
    Filter occurred_at >= ...
    Filter tenant_id = 42
  -> trả hàng

MATERIALIZED:
  Scan events
    Filter occurred_at >= ...
  -> kết quả CTE trung gian

  CTE Scan
    Filter tenant_id = 42
  -> trả hàng
~~~

### 5.2. Materialization có thể tốn gì?

- CPU và I/O để tạo kết quả trung gian.
- Bộ nhớ và có thể lưu tạm ra disk nếu dữ liệu lớn.
- Truy vấn ngoài không đẩy được một số predicate vào trong CTE.
- JOIN reordering qua ranh giới có thể bị hạn chế.
- Kế hoạch có thể dùng `CTE Scan` thay vì xem trực tiếp các base relations.

### 5.3. Nhưng không được nói materialized CTE luôn đọc hết mọi hàng

Trong PostgreSQL, việc sản xuất kết quả của CTE có thể chịu ảnh hưởng bởi **số hàng mà consumer thật sự đòi hỏi**. Ví dụ parent query có LIMIT và không buộc đọc hết, CTE có thể không nhất thiết được tính toàn bộ trước khi parent kết thúc.

Tuy nhiên, `ORDER BY`, JOIN, aggregate hoặc nhiều consumers có thể khiến nhiều hay toàn bộ kết quả được yêu cầu. **Không dùng LIMIT ngoài cùng như một bảo đảm hiệu năng** nếu query shape đã buộc phần lớn dữ liệu được đọc.

### 5.4. Khi nào MATERIALIZED có ích?

Một CTE tính kết quả **đắt tiền** mà nhiều phần của truy vấn dùng chung có thể đáng được tính một lần và chia sẻ. Materialization cũng là một công cụ có chủ đích để ngăn những thay đổi plan không mong muốn khi có lý do đã đo đạc.

Nhưng nó không phải “chế độ an toàn/nhanh hơn” cho mọi CTE.

## 6. AS NOT MATERIALIZED: cho phép gộp vào parent

Cú pháp:

~~~sql
WITH events_filtered AS NOT MATERIALIZED (
    SELECT event_id, tenant_id, occurred_at, payload
    FROM events
    WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
)
SELECT event_id, payload
FROM events_filtered
WHERE tenant_id = 42;
~~~

Với CTE đủ điều kiện, `NOT MATERIALIZED` yêu cầu planner cho phép folding thay vì tạo một kết quả chia sẻ bắt buộc.

### 6.1. Một tham chiếu thường không cần ghi rõ

Ở PostgreSQL 12+, nếu CTE SELECT bình thường, không recursive, không volatile và chỉ được dùng một lần, mặc định thường đã fold. Thêm `NOT MATERIALIZED` có thể làm rõ ý định nhưng **không nhất thiết đổi plan**.

### 6.2. Nhiều tham chiếu mới là tình huống đáng chú ý

Khi cùng CTE xuất hiện hai lần, mặc định thường materialize. `NOT MATERIALIZED` cho phép mỗi nhánh tham chiếu được tối ưu theo điều kiện của chính nó.

### 6.3. Đổi lại có thể tính lặp

Nếu CTE chứa biểu thức tốn CPU, JOIN lớn hoặc xử lý phức tạp, folding nhiều lần có thể khiến work bị lặp ở các nhánh.

**Pushdown tốt hơn** không đồng nghĩa **tổng công việc luôn ít hơn**.

### 6.4. Không phải chỉ thị vô điều kiện

PostgreSQL không fold một CTE đệ quy hoặc CTE có những tính chất mà folding sẽ thay đổi ngữ nghĩa, chỉ vì đã viết `NOT MATERIALIZED`. Xem các phần về recursive, volatile và data-modifying CTE.

## 7. So sánh materialize và folding bằng EXPLAIN

Hai cách viết:

~~~sql
WITH filtered AS MATERIALIZED (
    SELECT event_id, tenant_id, event_type, occurred_at
    FROM events
    WHERE event_type = 'purchase'
)
SELECT event_id
FROM filtered
WHERE tenant_id = 42;
~~~

và:

~~~sql
WITH filtered AS NOT MATERIALIZED (
    SELECT event_id, tenant_id, event_type, occurred_at
    FROM events
    WHERE event_type = 'purchase'
)
SELECT event_id
FROM filtered
WHERE tenant_id = 42;
~~~

### 7.1. Dấu hiệu trong kế hoạch

Khi materialization thực sự xuất hiện, thường có phần:

~~~text
CTE filtered
  -> ...
...
CTE Scan on filtered
  Filter: tenant_id = 42
~~~

Khi folding xảy ra, bạn có thể thấy scan/join trực tiếp trên `events` và không còn node `CTE Scan` cho CTE đó.

### 7.2. Không chỉ nhìn node type

So sánh:

- `rows</BT> ước lượng và `actual rows`.
- Filter được áp dụng tại `Index Cond`, `Filter` hay CTE Scan?
- `Rows Removed by Filter`.
- `Buffers</BT>.
- Thời gian tổng và thời gian node.
- Số lần chạy mỗi node (`loops`).
- Temporary read/write khi có dữ liệu trung gian lớn.
- Planning time và execution time.

### 7.3. Không kết luận từ một lần chạy

Hệ thống cache, background workload và chi phí planning có thể làm thời gian biến động. Thực hành trên dữ liệu đại diện với các tham số giống nhau trước/sau.

## 8. CTE được tham chiếu nhiều lần

Ví dụ:

~~~sql
WITH base AS (
    SELECT event_id, tenant_id, payload
    FROM events
    WHERE payload >= 900
)
SELECT COUNT(*)
FROM base AS a
JOIN base AS b
  ON a.event_id = b.event_id
WHERE a.tenant_id = 42;
~~~

Nếu CTE đủ điều kiện nhưng được dùng ở `a</BT> và `b</BT>, PostgreSQL hiện đại thường **materialize mặc định** để tránh tính phần base nhiều lần.

### 8.1. Ưu điểm của kết quả chia sẻ

Nếu phần `base</BT> rất đắt và hai nhánh đều cần phần lớn kết quả, tính một lần có thể tiết kiệm đáng kể.

### 8.2. Nhược điểm

Điều kiện `a.tenant_id=42` có thể không đẩy vào phần CTE chung vì kết quả đó còn phục vụ `b</BT>. Như vậy phần chung có thể phải chứa nhiều tenant và nhiều hàng không cần ở nhánh a.

### 8.3. Thử NOT MATERIALIZED

~~~sql
WITH base AS NOT MATERIALIZED (
    SELECT event_id, tenant_id, payload
    FROM events
    WHERE payload >= 900
)
SELECT COUNT(*)
FROM base AS a
JOIN base AS b
  ON a.event_id = b.event_id
WHERE a.tenant_id = 42;
~~~

Planner có thể tối ưu hai tham chiếu độc lập, cho phép filter từ từng nhánh đi sâu hơn và tận dụng index phù hợp.

### 8.4. Khi NOT MATERIALIZED lại chậm

Nếu hai nhánh đều phải đọc/tính gần như toàn bộ base và có biểu thức rất đắt, folding có thể nhân đôi công việc.

### 8.5. Kết luận cho CTE nhiều tham chiếu

Không có một đáp án cố định:

| Đặc điểm workload | Hướng nên đo |
|---|---|
| Phần chung đắt, nhánh dùng gần hết kết quả | `MATERIALIZED` hoặc mặc định |
| Mỗi nhánh chỉ cần tập nhỏ khác nhau | `NOT MATERIALIZED` |
| Một lần tham chiếu, SELECT thông thường | Thường để mặc định |
| Có volatile function | Cần giữ ngữ nghĩa; NOT MATERIALIZED không ép fold vô điều kiện |
| Có recursive hoặc data modification | Cơ chế riêng, không đơn giản là fold |

## 9. Predicate pushdown qua CTE

**Predicate pushdown** là khả năng đưa điều kiện lọc xuống bước truy cập dữ liệu sớm nhất mà vẫn đúng ngữ nghĩa.

Ví dụ:

~~~sql
WITH all_events AS MATERIALIZED (
    SELECT event_id, tenant_id, payload
    FROM events
)
SELECT *
FROM all_events
WHERE tenant_id = 42;
~~~

Khi CTE bị materialize, phần quét `events</BT> không nhận được filter tenant từ truy vấn ngoài để thu hẹp kết quả CTE.

### 9.1. Đặt predicate trong CTE khi biết chắc mục tiêu

~~~sql
WITH tenant_events AS MATERIALIZED (
    SELECT event_id, tenant_id, payload
    FROM events
    WHERE tenant_id = 42
)
SELECT *
FROM tenant_events;
~~~

Ngay cả khi cần materialization, đưa filter **đúng ngữ nghĩa và được dùng bởi mọi consumer** vào trong vẫn có thể giảm dữ liệu trung gian.

### 9.2. Cẩn thận nếu CTE dùng chung

Nếu CTE phục vụ cả tenant=42 và tenant=77, đẩy `tenant_id=42` vào CTE chung sẽ đổi kết quả của nhánh tenant=77.

### 9.3. Điều kiện bên ngoài không phải luôn hợp lệ để đẩy

Nếu CTE chứa `LIMIT</BT>, window function hoặc aggregate, việc đổi thứ tự filter và operator có thể làm kết quả khác.

Ví dụ:

~~~sql
WITH top_events AS MATERIALIZED (
    SELECT event_id, tenant_id, payload
    FROM events
    ORDER BY payload DESC, event_id
    LIMIT 100
)
SELECT *
FROM top_events
WHERE tenant_id = 42;
~~~

Ngữ nghĩa là: **lấy top 100 toàn bảng, sau đó chọn tenant 42**. Không thể tự biến thành “lấy top 100 của tenant 42”, vì hai phép toán khác nhau.

## 10. CTE và JOIN reordering

Planner thường có thể chọn thứ tự JOIN của các quan hệ khi phép biến đổi được phép.

Ví dụ khái niệm:

~~~sql
SELECT ...
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
JOIN items AS i
  ON i.order_id = o.order_id
WHERE c.region = 'north';
~~~

Nếu có filter rất chọn lọc trên customers, planner có thể muốn bắt đầu từ nhóm customer nhỏ rồi JOIN với orders.

Nhưng nếu orders và items bị đóng thành một CTE materialized lớn, planner không còn quyền tối ưu lại mọi quan hệ bên trong/ngoài như một tập chung.

### 10.1. Hình dung

~~~text
Không có ranh giới:
  customers(region='north')
         |
      JOIN orders
         |
      JOIN items

CTE materialized:
  [orders JOIN items] -> CTE result lớn
                         |
                      JOIN customers(region='north')
~~~

Đây là sơ đồ khái niệm, không phải planner PostgreSQL luôn tạo đúng một thứ tự như hình.

### 10.2. Join order còn bị chi phối bởi ngữ nghĩa

Outer joins, lateral references, subquery semantics, giới hạn join-collapse, security constraints và những yếu tố khác có thể hạn chế biến đổi.

Không nên tuyên bố “NOT MATERIALIZED sẽ cho planner đổi mọi JOIN tự do”.

## 11. CTE với biểu thức đắt tiền: đôi khi materialize có lợi

Giả sử một phần truy vấn tính một điểm số phức tạp cho mỗi sự kiện và kết quả được sử dụng nhiều lần.

~~~sql
WITH scored AS MATERIALIZED (
    SELECT
        event_id,
        tenant_id,
        (payload::numeric * payload::numeric + 17) AS score
    FROM events
)
SELECT COUNT(*)
FROM scored AS a
JOIN scored AS b
  ON a.event_id = b.event_id
WHERE a.score > 100000;
~~~

Trong ví dụ này, `MATERIALIZED` cung cấp một kết quả chia sẻ thay vì planner nhân bản phần CTE cho hai nhánh.

### 11.1. Điều gì có thể đắt?

- Biểu thức tính toán với nhiều phép toán hoặc hàm.
- Tổng hợp dữ liệu nhiều hàng.
- CTE bao gồm nhiều JOIN.
- Sắp xếp.
- Đọc khối lượng lớn từ nguồn dữ liệu.

### 11.2. Nhưng materialization cũng có giá

Nếu chỉ vài hàng được cần sau filter/join, việc tính toàn bộ scored là lãng phí. `NOT MATERIALIZED` có thể cho phép filter trước hoặc loại bỏ phép tính không dùng trong từng nhánh.

### 11.3. Một function gọi hai lần có chắc thực sự chạy hai lần?

Không được suy luận chỉ từ sự xuất hiện của biểu thức trong source SQL. Planner có thể inline, loại bỏ biểu thức không cần, gộp hoặc nhân bản biểu thức theo giới hạn semantics. Hãy xem `EXPLAIN (ANALYZE, VERBOSE)</BT> và đo workload nếu số lần gọi quan trọng.

### 11.4. Không dựa vào CTE để bảo đảm thứ tự side effects

Nếu một hàm có tác dụng phụ, phải khai báo volatility đúng và thiết kế rõ thứ tự/điều kiện thực thi. Không dùng những giả định mơ hồ về materialization để điều khiển side effect nghiệp vụ.

## 12. CTE có hàm VOLATILE: vì sao không được fold tự do?

Một CTE chứa hàm có thể thay đổi kết quả theo lần gọi, ví dụ `random()</BT>, không giống CTE chỉ làm phép toán thuần.

~~~sql
WITH sample AS (
    SELECT random() AS value
)
SELECT value, value
FROM sample;
~~~

Ở đây PostgreSQL cần bảo toàn ngữ nghĩa của một giá trị do CTE tạo ra, thay vì tự tùy tiện biến thành hai lời gọi random độc lập.

### 12.1. Volatility là hợp đồng với planner

PostgreSQL phân loại hàm bằng:

- `VOLATILE`.
- `STABLE`.
- `IMMUTABLE`.

Một CTE SELECT chứa **volatile function** không thuộc nhóm side-effect-free đơn giản mà planner có thể fold như CTE SELECT thuần.

### 12.2. NOT MATERIALIZED không “ép” bỏ điều kiện an toàn

~~~sql
WITH sample AS NOT MATERIALIZED (
    SELECT random() AS value
)
SELECT value FROM sample;
~~~

Không nên kỳ vọng `NOT MATERIALIZED` khiến PostgreSQL bỏ qua cơ chế bảo vệ ngữ nghĩa cho hàm volatile. Những điều kiện eligibility vẫn áp dụng.

### 12.3. Không đổi hàm thành IMMUTABLE để ép planner

Nếu hàm dùng random, thời gian hiện tại, session state, đọc dữ liệu có thể thay đổi hoặc có side effects, khai báo sai là `IMMUTABLE` có thể tạo kết quả sai và ảnh hưởng index/planning.

Chính xác về volatility quan trọng hơn cố đạt một plan đẹp.

## 13. CTE đệ quy là loại khác

CTE đệ quy thường dùng:

~~~sql
WITH RECURSIVE tree AS (
    SELECT ...
    UNION ALL
    SELECT ...
    FROM tree ...
)
SELECT ...
FROM tree;
~~~

Phần recursive phụ thuộc kết quả vòng lặp trước đó. Nó không thể được gộp như CTE SELECT đơn giản vào mọi query ngoài.

### 13.1. Planner dùng bước recursive

Trong `EXPLAIN`, bạn có thể thấy các node như:

- `Recursive Union`.
- `WorkTable Scan`.
- `CTE Scan`.

Đây là dấu hiệu cơ chế đệ quy/working table, không tự chứng minh truy vấn bị “tối ưu kém”.

### 13.2. Chi phí tăng theo chiều sâu và số nhánh

Với đồ thị có nhiều nút và nhiều cạnh, recursive query có thể sinh nhiều hàng trung gian. Những vấn đề cần xử lý bao gồm:

- Điều kiện dừng.
- Phát hiện chu trình.
- Index trên khóa liên kết như `parent_id`.
- Loại trùng khi cần.
- Giới hạn độ sâu theo nghiệp vụ.

### 13.3. NOT MATERIALIZED không biến recursive query thành JOIN thường

Một cấu trúc phải xử lý lặp không trở thành phép scan một lần chỉ nhờ thay một từ khóa.

## 14. CTE ghi dữ liệu có ngữ nghĩa riêng

PostgreSQL hỗ trợ data-modifying statements trong WITH ở những vị trí được cho phép:

~~~sql
WITH created AS (
    INSERT INTO events (
        tenant_id, event_type, occurred_at, payload
    )
    VALUES (42, 'purchase', CURRENT_TIMESTAMP, 100)
    RETURNING event_id, tenant_id
)
SELECT event_id, tenant_id
FROM created;
~~~

### 14.1. RETURNING là kênh đưa dữ liệu ra

Phần `INSERT ... RETURNING` tạo quan hệ kết quả để truy vấn ngoài có thể đọc. Không được xem data-modifying CTE như một CTE SELECT side-effect-free chỉ vì nó xuất hiện trong WITH.

### 14.2. Tác dụng phụ và thời điểm thực thi

Data-modifying CTE được thực hiện theo ngữ nghĩa riêng của PostgreSQL; các thao tác ghi trong WITH không tùy ý bị lược bỏ như một biểu thức SELECT không dùng kết quả. Khi có nhiều nhánh ghi trong cùng WITH, thứ tự thực thi thực tế có thể không được xác định theo thứ tự các nhánh được viết; chúng cần được thiết kế không phụ thuộc vào một thứ tự ngầm.

### 14.3. Đừng ghi hai lần cùng hàng không kiểm soát

Việc cho nhiều nhánh data-modifying CTE cùng sửa một hàng trong một statement có thể dẫn tới hành vi không được xác định theo cách ứng dụng mong muốn. Nếu cần cập nhật nhiều trường của cùng hàng, hãy viết một UPDATE rõ ràng hoặc protocol được bảo đảm.

### 14.4. Folding không phải đòn bẩy chính

Ở đây, tính đúng của thay đổi dữ liệu, snapshot, RETURNING và transaction quan trọng hơn câu hỏi `MATERIALIZED</BT> có nhanh không.

## 15. SQL function và PL/pgSQL function: hai loại ranh giới khác nhau

PostgreSQL cho phép định nghĩa hàm bằng nhiều ngôn ngữ, phổ biến là:

- `LANGUAGE sql`: thân hàm được biểu diễn bằng SQL.
- `LANGUAGE plpgsql`: ngôn ngữ thủ tục, có biến, điều khiển luồng, vòng lặp và nhiều SQL statements.

Cả hai đều có thể trả scalar hoặc tập hàng. Nhưng **khả năng planner nhìn xuyên vào hàm** không giống nhau.

### 15.1. Hàm SQL đơn giản có thể được inline

Với điều kiện phù hợp, PostgreSQL có thể thay lời gọi SQL function bằng biểu thức hoặc nội dung truy vấn SQL của nó, cho phép tối ưu chung.

### 15.2. PL/pgSQL thường là ranh giới rõ hơn

Một PL/pgSQL function được thực thi qua cơ chế function call, và SQL bên trong được lập kế hoạch theo cơ chế PL/pgSQL. Planner của truy vấn gọi **không tự ghép toàn bộ control flow của PL/pgSQL vào query ngoài** như một biểu thức SQL đơn giản.

### 15.3. Không kết luận SQL function luôn inline

Ngay cả `LANGUAGE sql` có những yêu cầu eligibility: cấu trúc thân hàm, thuộc tính volatility, cách trả kết quả, `SECURITY DEFINER`, thuộc tính SET, kiểu tham số và những điều kiện khác có thể ngăn inlining.

## 16. Scalar SQL function: ví dụ hàm có thể inline

Tạo hàm tính giá gồm thuế:

~~~sql
CREATE FUNCTION calculate_price_with_tax(
    p_amount NUMERIC
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT round(p_amount * 1.10, 2);
$$;
~~~

Giả sử:

~~~sql
SELECT calculate_price_with_tax(100.00);
~~~

Về mặt biểu thức, hàm thực hiện phép tính đơn giản.

### 16.1. Điều gì có thể xảy ra trong planner?

Một lời gọi SQL function scalar đủ điều kiện có thể được inline thành biểu thức:

~~~sql
round(100.00 * 1.10, 2)
~~~

Sau đó các phép tối ưu như constant folding có thể áp dụng tùy volatility và cách truy vấn được chuẩn bị.

### 16.2. Inlining không phải một cam kết API

Đừng viết correctness dựa trên việc PostgreSQL bắt buộc inline. Đây là tối ưu nội bộ có điều kiện; phiên bản, chữ ký và thuộc tính hàm có thể làm kế hoạch khác nhau.

### 16.3. Hàm vẫn phải giữ kết quả đúng

Nếu hàm dùng dữ liệu thay đổi theo thời gian nhưng bị đánh dấu `IMMUTABLE`, planner có thể sử dụng giả định sai để rút gọn hoặc cache kết quả. Không gian tối ưu rộng không đáng giá nếu gây sai nghĩa.

## 17. Hàm PL/pgSQL có thể che giấu phép lọc

Một hàm truy vấn trả tập hàng:

~~~sql
CREATE FUNCTION get_events_plpgsql(
    p_tenant INTEGER
)
RETURNS SETOF events
LANGUAGE plpgsql
STABLE
ROWS 2000
AS $$
BEGIN
    RETURN QUERY
    SELECT e.*
    FROM events AS e
    WHERE e.tenant_id = p_tenant;
END;
$$;
~~~

Ở câu gọi:

~~~sql
SELECT *
FROM get_events_plpgsql(42)
WHERE event_type = 'purchase';
~~~

Planner ngoài có thể nhìn thấy một `Function Scan` với filter `event_type='purchase'`, thay vì tối ưu cùng điều kiện đó ngay trong scan bên trong hàm.

### 17.1. Predicate ở ngoài hàm có thể đến quá muộn

Hàm có thể đã trả một tập sự kiện của tenant 42, rồi phần query ngoài mới lọc `event_type`. Nếu hàm trả rất nhiều hàng, đây có thể là tốn kém đáng kể.

### 17.2. SQL bên trong PL/pgSQL vẫn có planner

Điều đó **không có nghĩa các SELECT bên trong PL/pgSQL chạy không có tối ưu**. Những SQL statements bên trong được PostgreSQL lập kế hoạch. Vấn đề là planner bên ngoài **không có toàn quyền đẩy filter bên ngoài xuyên qua ranh giới procedural function**.

### 17.3. Một cách cải thiện là đưa điều kiện thành tham số

~~~sql
CREATE FUNCTION get_events_plpgsql_filtered(
    p_tenant INTEGER,
    p_type TEXT
)
RETURNS SETOF events
LANGUAGE plpgsql
STABLE
ROWS 100
AS $$
BEGIN
    RETURN QUERY
    SELECT e.*
    FROM events AS e
    WHERE e.tenant_id = p_tenant
      AND e.event_type = p_type;
END;
$$;
~~~

Rồi gọi:

~~~sql
SELECT *
FROM get_events_plpgsql_filtered(42, 'purchase');
~~~

Điều này cho phép **SQL bên trong hàm** nhìn thấy cả hai điều kiện ngay từ đầu, dù chính hàm vẫn là ranh giới riêng.

### 17.4. Nhưng thêm tham số không giải quyết mọi chuyện

Join order với các bảng ngoài hàm, ước lượng số hàng trả về và chi phí function scan vẫn cần được xem xét. Nếu không có lý do cần procedural logic, có thể dùng query trực tiếp hoặc SQL-language table function phù hợp.

## 18. SQL table function: có thể được gộp vào query gọi

Tạo hàm SQL trả các event theo tenant:

~~~sql
CREATE FUNCTION get_events_sql(
    p_tenant INTEGER
)
RETURNS SETOF events
LANGUAGE sql
STABLE
ROWS 2000
AS $$
    SELECT e.*
    FROM events AS e
    WHERE e.tenant_id = p_tenant;
$$;
~~~

Gọi:

~~~sql
SELECT event_id, event_type
FROM get_events_sql(42)
WHERE event_type = 'purchase';
~~~

### 18.1. Lợi ích tiềm năng khi inline table function

Nếu hàm đủ điều kiện để được inline, planner có thể nhìn sâu vào:

~~~sql
SELECT event_id, event_type
FROM events
WHERE tenant_id = 42
  AND event_type = 'purchase';
~~~

Từ đó có thể chọn index hoặc thứ tự JOIN theo cả hai filter.

### 18.2. Dấu hiệu trên EXPLAIN

Nếu inlining xảy ra, kế hoạch có thể hiển thị scan của bảng `events` trực tiếp, không phải `Function Scan</BT> cho `get_events_sql`.

Nếu không inline, `Function Scan</BT> vẫn có thể xuất hiện. Không chỉ dựa trên chữ `LANGUAGE sql` để đoán.

### 18.3. Vì sao STABLE quan trọng?

Một SQL table function đọc bảng mà không tự thay đổi dữ liệu thường được khai báo `STABLE` khi đúng ngữ nghĩa. Thuộc tính volatility là một trong những yếu tố planner sử dụng để xác định những phép biến đổi an toàn.

### 18.4. Không đánh dấu IMMUTABLE cho truy vấn đọc bảng thay đổi

Nếu hàm trả sự kiện của tenant từ bảng `events`, kết quả phụ thuộc dữ liệu của bảng tại thời điểm query. Nó **không IMMUTABLE** theo nghĩa cùng input mãi luôn cho cùng output bất kể database thay đổi.

## 19. Inlining có những điều kiện gì?

Không có một danh sách ngắn áp dụng cho mọi kiểu SQL function và mọi phiên bản, nhưng các yếu tố thường có ảnh hưởng là:

| Yếu tố | Ảnh hưởng tiềm năng |
|---|---|
| `LANGUAGE sql` | Cho planner khả năng xem/biến đổi thân SQL khi hợp lệ |
| Body chỉ gồm SQL thích hợp | Dễ inline hơn procedural/multi-statement logic |
| Scalar hay set-returning | Có các quy tắc inlining khác nhau |
| `VOLATILE/STABLE/IMMUTABLE` | Quy định quyền tái sắp xếp hoặc tính trước |
| `STRICT` | Có thể ảnh hưởng điều kiện inlining, đặc biệt table function |
| `SECURITY DEFINER` | Thường ngăn inlining vì ngữ nghĩa quyền |
| Function-level `SET</BT> | Có thể ngăn inlining vì thay đổi môi trường thực thi |
| Kiểu dữ liệu và cách tham chiếu tham số | Có thể ảnh hưởng |
| Cấu trúc tập kết quả, ORDER BY/LIMIT | Hạn chế phép biến đổi nếu đổi nghĩa |

### 19.1. Scalar và table-function inlining không giống hệt nhau

Một scalar SQL function đơn giản có thể inline trong nhiều trường hợp mà một SQL set-returning function khác không đáp ứng được. Ngược lại, SQL table function cần giữ những quy tắc về tập hàng.

### 19.2. Không tắt bảo vệ để ép inline

Nếu hàm cần `SECURITY DEFINER` để thực thi dưới quyền của chủ sở hữu, đó là một yêu cầu bảo mật thực sự. Không được đổi sang `SECURITY INVOKER` chỉ để có plan đẹp hơn khi điều đó làm hỏng quyền.

### 19.3. Nếu hiệu năng trọng yếu, đo plan của caller

Hãy so `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)</BT> giữa:

1. Query trực tiếp.
2. Hàm SQL.
3. Hàm PL/pgSQL.

Dùng cùng predicate và dữ liệu, quan sát ranh giới cùng lượng hàng qua đó.

## 20. VOLATILE, STABLE, IMMUTABLE và tối ưu hóa

Volatility là hợp đồng khai báo quan trọng.

### 20.1. VOLATILE

Hàm có thể cho kết quả khác trong một statement hoặc có tác dụng phụ. Ví dụ built-in `random()</BT> và `clock_timestamp()</BT>.

Planner phải thận trọng hơn khi thay đổi số lần hoặc thứ tự đánh giá.

### 20.2. STABLE

Với cùng tham số, hàm được kỳ vọng trả kết quả nhất quán **trong phạm vi một statement** theo hợp đồng PostgreSQL. Nó có thể phụ thuộc dữ liệu database hoặc môi trường có thể thay đổi giữa các statement.

Ví dụ `CURRENT_TIMESTAMP`/`now()</BT> có ngữ nghĩa thời điểm transaction; nó không phải “mãi mãi bất biến”.

### 20.3. IMMUTABLE

Với cùng input, hàm phải trả cùng kết quả một cách bền vững, không phụ thuộc database thay đổi, thời gian hoặc session state theo những điều kiện mà PostgreSQL yêu cầu.

Ví dụ phép tính số học thuần có thể phù hợp:

~~~sql
CREATE FUNCTION double_integer(p_value INTEGER)
RETURNS INTEGER
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT p_value * 2;
$$;
~~~

### 20.4. Lỗi phổ biến: khai báo IMMUTABLE cho hàm đọc bảng

~~~sql
CREATE FUNCTION get_current_price(p_product_id BIGINT)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT price
    FROM products
    WHERE product_id = p_product_id;
$$;
~~~

Đây là **một ví dụ khai báo sai về ngữ nghĩa** khi giá trong bảng có thể đổi. Không chạy mẫu này như một thiết kế đúng.

### 20.5. Hậu quả của khai báo sai

Planner có thể constant-fold hay tái sử dụng giá trị theo giả định IMMUTABLE, đặc biệt với prepared statements và plan caching. Hàm cũng có thể được dùng trong index expression/generated column không phù hợp, dẫn đến kết quả không nhất quán.

### 20.6. Độ biến động không chỉ là tối ưu hiệu năng

Đánh dấu đúng volatility là yêu cầu **tính đúng**. Tối ưu không được đánh đổi bằng kết quả sai.

## 21. Hàm tự định nghĩa và chi phí COST

Planner không thể lúc nào cũng tự biết một PL/pgSQL function có tốn 1µs hay 100ms. PostgreSQL cho phép cung cấp ước lượng chi phí hàm bằng thuộc tính `COST`.

~~~sql
CREATE FUNCTION expensive_check(p_value INTEGER)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
COST 200
AS $$
BEGIN
    RETURN p_value > 0;
END;
$$;
~~~

Ví dụ chỉ minh họa cú pháp `COST`; thân hàm này thực ra rất đơn giản, nên `COST 200` không phải đề xuất hiệu chỉnh thật.

### 21.1. COST không phải mili-giây

Giá trị COST được biểu diễn theo đơn vị ước lượng planner, tương đối với tham số chi phí nội bộ như `cpu_operator_cost`, **không phải trực tiếp một số giây hay mili-giây**.

### 21.2. Mặc định khác nhau theo loại hàm

Các hàm C/internal thường có mặc định COST thấp hơn nhiều so với các hàm SQL/PL/pgSQL thông thường. Theo cơ chế PostgreSQL, mặc định thường gặp là 1 cho hàm C/internal và 100 cho các ngôn ngữ khác, trừ khi chỉ định khác.

### 21.3. COST ảnh hưởng điều gì?

Ước lượng này có thể tác động lựa chọn kế hoạch và thứ tự đánh giá khi planner được phép thay đổi.

Một hàm được đánh dấu rất đắt có thể khiến planner cân nhắc lọc bằng điều kiện rẻ trước, nếu ngữ nghĩa và kế hoạch cho phép.

### 21.4. COST không sửa rào cản inlining

Đặt `COST 1` cho PL/pgSQL function không khiến planner gộp toàn bộ logic PL/pgSQL vào query cha.

### 21.5. Không chỉnh COST theo cảm giác

Để tune, hãy đo function execution thực tế, số lần gọi và ảnh hưởng plan trên query cụ thể. COST sai có thể khiến planner đưa ra lựa chọn kém hơn.

## 22. Hàm trả tập hàng và ROWS

Một hàm set-returning cần ước lượng số hàng trả về. PostgreSQL cho phép thuộc tính `ROWS`:

~~~sql
CREATE FUNCTION tenant_events(
    p_tenant INTEGER
)
RETURNS SETOF events
LANGUAGE sql
STABLE
COST 10
ROWS 2000
AS $$
    SELECT e.*
    FROM events AS e
    WHERE e.tenant_id = p_tenant;
$$;
~~~

### 22.1. ROWS mô tả điều gì?

`ROWS 2000` là một **gợi ý ước lượng số hàng hàm trả về**, không phải LIMIT. Nó không bắt hàm chỉ trả tối đa 2.000 hàng.

### 22.2. Giá trị mặc định

Một hàm trả tập hàng thường có mặc định `ROWS 1000` nếu không đặt khác. Nếu thực tế hàm trả 2 hay 2 triệu hàng, sai số có thể làm planner chọn join order kém khi function scan không inline.

### 22.3. Kết hợp với COST

Đối với hàm trả tập hàng, COST liên quan chi phí ước lượng cho mỗi hàng kết quả theo quy tắc PostgreSQL, và ROWS liên quan cardinality của tập trả về. Cả hai có thể ảnh hưởng quyết định ở query caller.

### 22.4. Không chờ ROWS sửa mọi tính toán của inner query

Nếu SQL table function được inline, planner có thể ước lượng trực tiếp trên các base tables. Nếu không inline, metadata COST/ROWS quan trọng hơn ở node function scan.

### 22.5. Các tenant có kích thước rất khác nhau

Một ROWS cố định là ước lượng tổng quát; tenant nhỏ có 100 hàng, tenant lớn có 1 triệu hàng. Vì thế một `ROWS</BT> duy nhất không thể phản ánh mọi phân phối tham số. Cần xem query plan, phương án truyền SQL trực tiếp, statistics và custom/generic plans.

## 23. PARALLEL SAFE, RESTRICTED, UNSAFE

Hàm cũng có thuộc tính liên quan tới parallel query:

- `PARALLEL SAFE`.
- `PARALLEL RESTRICTED`.
- `PARALLEL UNSAFE`.

### 23.1. Đây là hợp đồng, không chỉ một lời gợi ý

Nếu hàm truy cập trạng thái backend không an toàn khi chạy worker, dùng temporary tables, cursor, thay đổi dữ liệu hoặc có hành vi bị giới hạn, việc đánh dấu SAFE sai có thể gây lỗi hoặc hành vi không mong muốn.

### 23.2. Mặc định của hàm tự định nghĩa

Hàm tự định nghĩa thường được xem là `PARALLEL UNSAFE` nếu chưa được khai báo khác phù hợp. Điều này có thể hạn chế việc xây parallel plan cho query gọi hàm.

### 23.3. Mẫu hàm thuần có thể SAFE

~~~sql
CREATE FUNCTION add_one(p_value INTEGER)
RETURNS INTEGER
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT p_value + 1;
$$;
~~~

Đây là ví dụ đơn giản có tính thuần, không có side effect.

### 23.4. Không sửa performance bằng việc ép SAFE cho mọi hàm

Nếu không chứng minh được hành vi an toàn, cần giữ khai báo đúng và cân nhắc thay đổi thiết kế để tránh gọi hàm procedural trong điểm nóng của query.

### 23.5. Parallelism không bảo đảm nhanh hơn

Một truy vấn trả vài hàng có thể bị overhead parallel lớn hơn lợi ích. Planner còn cân nhắc kích thước dữ liệu và chi phí tương ứng.

## 24. STRICT và NULL-handling

Hàm có thể khai báo `STRICT`, còn được gọi là `RETURNS NULL ON NULL INPUT`.

~~~sql
CREATE FUNCTION normalized_code(p_code TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT lower(btrim(p_code));
$$;
~~~

Khi tham số NULL, PostgreSQL có thể bỏ qua gọi hàm và trả NULL theo hợp đồng STRICT.

### 24.1. STRICT chỉ đúng nếu nghiệp vụ thật sự phù hợp

Một hàm biến NULL thành giá trị mặc định:

~~~sql
SELECT coalesce(p_code, 'unknown');
~~~

không thể được khai báo STRICT nếu muốn hàm có cơ hội chạy khi `p_code</BT> là NULL, bởi STRICT sẽ khiến nó trả NULL trực tiếp.

### 24.2. STRICT có thể ảnh hưởng inlining eligibility

Đặc biệt, một số quy tắc inlining SQL set-returning functions khác với scalar functions về STRICT. Đừng chỉ thay STRICT để ép plan mà bỏ qua tính đúng null semantics.

### 24.3. Function calls trên hàng loạt dữ liệu

Nếu query gọi một hàm tốn kém trên hàng triệu hàng, việc nó có được đánh giá với NULL, có được inline và có bị duplicate hay không đều ảnh hưởng CPU. Dùng `EXPLAIN</BT> và phép đo phù hợp.

## 25. SECURITY DEFINER là ranh giới bảo mật, không chỉ hiệu năng

PostgreSQL cho phép:

~~~sql
CREATE FUNCTION get_sensitive_report()
RETURNS ...
LANGUAGE sql
SECURITY DEFINER
AS $$
    SELECT ...;
$$;
~~~

Đây là khung cú pháp khái niệm, không phải một function hoàn chỉnh có thể chạy nếu chưa thay `RETURNS ...</BT> và phần body.

### 25.1. SECURITY DEFINER thay đổi ngữ nghĩa quyền

Hàm chạy với quyền của chủ hàm trong những khía cạnh tương ứng. Điều đó khác rõ so với một query SQL được inline tự do vào caller dưới quyền của người gọi.

### 25.2. PostgreSQL không thể bỏ qua ranh giới đó cho tiện tối ưu

SQL function inlining có những hạn chế liên quan `SECURITY DEFINER`. Đây là lựa chọn bảo mật, không nên đổi chỉ vì muốn loại `Function Scan`.

### 25.3. Chú ý search_path

Một SECURITY DEFINER function cần kiểm soát `search_path</BT> và tham chiếu đầy đủ đối tượng để tránh bị các object không tin cậy che tên. Nếu phải gắn `SET search_path` vào hàm, điều đó có thể ảnh hưởng khả năng inlining, nhưng bảo mật vẫn được ưu tiên.

### 25.4. Không kết hợp quyền cao và dynamic SQL không an toàn

Nếu hàm tạo SQL bằng cách nối chuỗi đầu vào từ client, có nguy cơ SQL injection với quyền của function owner. Dùng tham số, `format('%I', ...)</BT> cho identifier và `USING</BT> cho dữ liệu khi cần dynamic SQL trong PL/pgSQL.

## 26. Hàm trong WHERE có thể làm mất khả năng dùng index trực tiếp

Một câu:

~~~sql
SELECT *
FROM events
WHERE event_type = 'purchase';
~~~

có thể dùng B-tree index trên `event_type` nếu phù hợp.

Nhưng:

~~~sql
SELECT *
FROM events
WHERE lower(btrim(event_type)) = 'purchase';
~~~

là predicate trên **biểu thức**, không phải trực tiếp trên giá trị gốc.

### 26.1. Sargability là gì?

Một predicate **sargable** theo ngữ cảnh index là predicate mà planner có thể chuyển thành một index condition hữu ích.

Không phải mọi hàm bao quanh cột đều tuyệt đối cấm dùng index, nhưng index thông thường trên cột gốc có thể **không đáp ứng trực tiếp** biểu thức biến đổi đó.

### 26.2. Expression index

~~~sql
CREATE INDEX events_normalized_type_idx
ON events (lower(btrim(event_type)));
~~~

Nếu biểu thức phù hợp, PostgreSQL có thể dùng index này cho WHERE trên biểu thức tương ứng.

### 26.3. Index trên user-defined function

Nếu function thực sự IMMUTABLE theo hợp đồng:

~~~sql
CREATE INDEX events_normalized_type_fn_idx
ON events (normalized_code(event_type));
~~~

Cần định nghĩa hàm đúng và xem độ phù hợp của biểu thức. B-tree index trên function cần tuân thủ yêu cầu immutability; không được khai báo sai volatility để ép tạo index.

### 26.4. Không dùng index là chuyện riêng với inlining

Một SQL function có thể inline nhưng predicate vẫn không khớp index đang có. Ngược lại, expression index phù hợp có thể cho một expression access path ngay cả khi query chứa lời gọi function. **Inlining** và **index match** là hai vấn đề liên quan nhưng không đồng nhất.

### 26.5. Hàm có thể bị gọi quá nhiều lần

Nếu predicate áp dụng cho một triệu hàng, một hàm PL/pgSQL đắt có thể bị gọi hàng triệu lần trước khi trả vài hàng. Hãy tìm cách đẩy filter rẻ lên trước hoặc dùng SQL thuần/index phù hợp, dựa trên plan thật.

## 27. PL/pgSQL và cached plans

SQL statements viết trong PL/pgSQL được PostgreSQL chuẩn bị/lập kế hoạch theo cơ chế PL/pgSQL và SPI. Một số statements có thể dùng kế hoạch được cache và tái sử dụng.

### 27.1. Đây không phải “PL/pgSQL không có optimizer”

PostgreSQL vẫn lập kế hoạch cho SQL bên trong. Vấn đề là planner của caller không nhất thiết kết hợp câu SQL bên trong với toàn bộ JOIN/filter bên ngoài như khi inline một SQL table function.

### 27.2. Generic và custom plans có thể khác

Khi tham số đầu vào thay đổi mạnh theo tenant, selectivity có thể rất khác. SQL bên trong PL/pgSQL có thể chịu ảnh hưởng của quyết định generic/custom plan theo cơ chế plan cache.

### 27.3. Dùng EXPLAIN đúng nơi

`EXPLAIN</BT> của caller có thể chỉ hiển thị `Function Scan`, không cho bạn thấy đầy đủ plan của những SQL statements bên trong PL/pgSQL.

Để tối ưu sâu, cần giải thích những SQL đó riêng trên dữ liệu đại diện hoặc dùng instrumentation phù hợp trong môi trường được phép.

### 27.4. Không đơn giản hóa thành “đổi hết sang SQL function”

PL/pgSQL hữu ích khi cần control flow, xử lý ngoại lệ, loop hoặc transaction-aware logic trong phạm vi chức năng. Chỉ thay đổi ngôn ngữ nếu semantics, bảo mật và khả năng bảo trì vẫn đúng.

## 28. Một ví dụ so sánh ba cách tổ chức logic

Giả sử cần lấy purchase events của tenant 42.

### 28.1. Query trực tiếp

~~~sql
SELECT event_id, tenant_id, event_type, payload
FROM events
WHERE tenant_id = 42
  AND event_type = 'purchase';
~~~

Planner có đầy đủ predicate ngay trong SELECT.

### 28.2. CTE có materialization

~~~sql
WITH tenant_rows AS MATERIALIZED (
    SELECT event_id, tenant_id, event_type, payload
    FROM events
    WHERE tenant_id = 42
)
SELECT *
FROM tenant_rows
WHERE event_type = 'purchase';
~~~

Điều kiện event_type nằm ngoài ranh giới; intermediate có thể lớn hơn.

### 28.3. PL/pgSQL function

~~~sql
SELECT *
FROM get_events_plpgsql(42)
WHERE event_type = 'purchase';
~~~

Planner ngoài có thể không đẩy filter vào body của PL/pgSQL, và số hàng trả có thể dựa trên khai báo `ROWS`.

### 28.4. SQL table function đủ điều kiện inline

~~~sql
SELECT *
FROM get_events_sql(42)
WHERE event_type = 'purchase';
~~~

Nếu inlining được áp dụng, planner có thể nhìn thấy cùng hai điều kiện và chọn scan như query trực tiếp.

### 28.5. Không xếp thứ hạng khi chưa đo

Có những trường hợp CTE materialize hoặc hàm PL/pgSQL được tổ chức lại đúng chỗ vẫn đạt hiệu năng tốt. Thứ tự ưu tiên cần dựa trên:

1. Kết quả logic chính xác.
2. Dữ liệu và parameter distribution.
3. Kế hoạch thật.
4. Số hàng trung gian và số lần gọi.
5. Chi phí CPU/I/O.
6. Tính bảo trì và bảo mật.

## 29. CTE và LIMIT: đẩy điều kiện có thể đổi nghĩa

Ví dụ:

~~~sql
WITH top_purchase AS (
    SELECT *
    FROM events
    WHERE event_type = 'purchase'
    ORDER BY occurred_at DESC, event_id DESC
    LIMIT 100
)
SELECT *
FROM top_purchase
WHERE tenant_id = 42;
~~~

Câu hỏi nghiệp vụ ở đây là: **trong 100 purchase events mới nhất của toàn hệ thống, có bao nhiêu thuộc tenant 42?**

Một query khác:

~~~sql
SELECT *
FROM events
WHERE tenant_id = 42
  AND event_type = 'purchase'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 100;
~~~

lại là: **100 purchase events mới nhất của tenant 42**.

Hai query này **không tương đương**.

### 29.1. Vì sao planner không tự đẩy mọi filter?

Nếu đẩy điều kiện tenant vào trước LIMIT, tập 100 hàng được chọn thay đổi. Planner phải tôn trọng semantics, kể cả khi một biến đổi khác trông có vẻ nhanh.

### 29.2. ORDER BY trong CTE không bảo đảm thứ tự cuối

Nếu outer query không có `ORDER BY` thích hợp, không nên phụ thuộc thứ tự kết quả dựa vào việc CTE đã sắp xếp. Thứ tự trả hàng là hợp đồng của ORDER BY ở query ngoài khi cần bảo đảm.

### 29.3. Dùng LIMIT để “ngăn CTE xử lý hết” là giả định rủi ro

Một số parent queries vẫn yêu cầu đọc nhiều hàng trước khi có thể sort/join/aggregate. Cần xem EXPLAIN, không suy luận chỉ từ LIMIT.

## 30. CTE với aggregate và window function

Xem:

~~~sql
WITH totals AS (
    SELECT tenant_id, COUNT(*) AS event_count
    FROM events
    GROUP BY tenant_id
)
SELECT *
FROM totals
WHERE event_count > 1000;
~~~

Điều kiện trên `event_count` là filter **sau aggregation**. Không được tự đưa nó xuống WHERE của base table theo cách làm thay đổi phép COUNT.

### 30.1. Aggregation là ranh giới ngữ nghĩa

Ngay cả khi CTE được fold, planner vẫn phải tôn trọng thứ tự logic của GROUP BY và HAVING. Không phải tất cả filter đều được push down.

### 30.2. Window function

~~~sql
WITH ranked AS (
    SELECT
        event_id,
        tenant_id,
        occurred_at,
        row_number() OVER (
            PARTITION BY tenant_id
            ORDER BY occurred_at DESC, event_id DESC
        ) AS rn
    FROM events
)
SELECT *
FROM ranked
WHERE rn <= 3;
~~~

Đây là “top 3 mỗi tenant”. Planner có thể có tối ưu riêng, nhưng không thể tùy tiện thay đổi tập đầu vào cho window function nếu làm đổi partition/rank.

### 30.3. Bài học

Một plan vẫn có sort/aggregate/window stage sau folding không có nghĩa CTE nhất định đang materialize. **Ranh giới do ngữ nghĩa SQL** khác **rào cản do AS MATERIALIZED**.

## 31. Lab hoàn chỉnh: schema và dữ liệu

Các ví dụ tiếp theo dùng PostgreSQL trong **database thử nghiệm**. Nếu schema `optimizer_lab` đã tồn tại, chọn schema/database khác; không xóa dữ liệu đang thuộc công việc thật.

### 31.1. Tạo schema

~~~sql
CREATE SCHEMA optimizer_lab;
~~~

### 31.2. Bảng sự kiện

~~~sql
CREATE TABLE optimizer_lab.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload INTEGER NOT NULL
);
~~~

### 31.3. Tạo 200.000 hàng mẫu

~~~sql
INSERT INTO optimizer_lab.events (
    tenant_id, event_type, occurred_at, payload
)
SELECT
    (g % 100) + 1,
    CASE
        WHEN g % 10 < 6 THEN 'view'
        WHEN g % 10 < 9 THEN 'click'
        ELSE 'purchase'
    END,
    TIMESTAMPTZ '2026-01-01 00:00+00'
        + (g % 2592000) * INTERVAL '1 second',
    g % 1000
FROM generate_series(1, 200000) AS gs(g);
~~~

Giải thích:

- 100 tenant được phân bố đều theo cách sinh dữ liệu.
- Event type có ba giá trị, phân phối không đều.
- `occurred_at` nằm trong khoảng 30 ngày tính từ đầu tháng 1/2026.
- `payload` là số nguyên phục vụ filter/biểu thức.

Dữ liệu tổng hợp có quan hệ theo modulo, có thể tạo những phụ thuộc không tự nhiên như production. Mục đích là minh họa kỹ thuật, không suy ra các con số hiệu năng sẽ lặp lại ở dữ liệu thật.

### 31.4. Tạo indexes

~~~sql
CREATE INDEX optimizer_events_tenant_time_idx
ON optimizer_lab.events (tenant_id, occurred_at);

CREATE INDEX optimizer_events_type_idx
ON optimizer_lab.events (event_type);

CREATE INDEX optimizer_events_payload_idx
ON optimizer_lab.events (payload);

ANALYZE optimizer_lab.events;
~~~

### 31.5. Truy vấn baseline

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, payload
FROM optimizer_lab.events
WHERE tenant_id = 42
  AND occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00';
~~~

Ghi lại Estimated Rows, Actual Rows, scan node, buffers và execution time.

## 32. Lab CTE MATERIALIZED vs NOT MATERIALIZED

### 32.1. Có ranh giới bắt buộc

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH recent AS MATERIALIZED (
    SELECT event_id, tenant_id, occurred_at, payload
    FROM optimizer_lab.events
    WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
)
SELECT event_id, payload
FROM recent
WHERE tenant_id = 42;
~~~

Quan sát:

- Có `CTE recent` và `CTE Scan on recent` hay không.
- `Filter: tenant_id = 42` nằm ở đâu.
- Bao nhiêu hàng CTE phải tạo/truyền.
- Có temp read/write không.

### 32.2. Cho phép folding

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH recent AS NOT MATERIALIZED (
    SELECT event_id, tenant_id, occurred_at, payload
    FROM optimizer_lab.events
    WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
)
SELECT event_id, payload
FROM recent
WHERE tenant_id = 42;
~~~

Planner có thể nhìn cả tenant và time predicate, chọn index scan/bitmap scan phù hợp.

### 32.3. Để mặc định

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH recent AS (
    SELECT event_id, tenant_id, occurred_at, payload
    FROM optimizer_lab.events
    WHERE occurred_at >= TIMESTAMPTZ '2026-01-15 00:00+00'
)
SELECT event_id, payload
FROM recent
WHERE tenant_id = 42;
~~~

Vì đây là CTE SELECT một lần tham chiếu và không có volatile expression, PostgreSQL 12+ thường fold mặc định. Hãy đối chiếu với NOT MATERIALIZED trên server thực tế.

### 32.4. Đánh giá đúng

Nếu kế hoạch NOT MATERIALIZED nhanh hơn, lý do có thể là giảm số hàng trước khi xử lý hoặc dùng index phù hợp. Nếu không nhanh hơn, có thể bảng/quy mô chưa đủ lớn, filter không chọn lọc hoặc planner vẫn chọn đường truy cập tương tự.

Không báo một con số speedup cố định khi chưa chạy đo.

## 33. Lab CTE nhiều lần tham chiếu

### 33.1. Mặc định

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH base AS (
    SELECT event_id, tenant_id, payload
    FROM optimizer_lab.events
    WHERE payload >= 900
)
SELECT COUNT(*)
FROM base AS a
JOIN base AS b
  ON a.event_id = b.event_id
WHERE a.tenant_id = 42;
~~~

### 33.2. NOT MATERIALIZED

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH base AS NOT MATERIALIZED (
    SELECT event_id, tenant_id, payload
    FROM optimizer_lab.events
    WHERE payload >= 900
)
SELECT COUNT(*)
FROM base AS a
JOIN base AS b
  ON a.event_id = b.event_id
WHERE a.tenant_id = 42;
~~~

### 33.3. Điều cần ghi

| Hạng mục | Mặc định | NOT MATERIALIZED |
|---|---|---|
| CTE Scan xuất hiện? | Ghi lại | Ghi lại |
| Số lần scan base table | Ghi lại | Ghi lại |
| Index paths | Ghi lại | Ghi lại |
| Hàng trung gian | Ghi lại | Ghi lại |
| Buffers/temp | Ghi lại | Ghi lại |
| Planning/execution time | Ghi lại | Ghi lại |

### 33.4. Không nhầm “một scan” với “ít công việc”

Một scan lớn có thể tốn hơn hai index scans rất nhỏ. Ngược lại, hai scans lớn tính lại biểu thức đắt có thể tốn hơn một CTE materialized chia sẻ.

## 34. Lab SQL function và PL/pgSQL function

### 34.1. Hàm SQL

~~~sql
CREATE FUNCTION optimizer_lab.get_events_sql(
    p_tenant INTEGER
)
RETURNS SETOF optimizer_lab.events
LANGUAGE sql
STABLE
ROWS 2000
AS $$
    SELECT e.*
    FROM optimizer_lab.events AS e
    WHERE e.tenant_id = p_tenant;
$$;
~~~

### 34.2. Hàm PL/pgSQL

~~~sql
CREATE FUNCTION optimizer_lab.get_events_plpgsql(
    p_tenant INTEGER
)
RETURNS SETOF optimizer_lab.events
LANGUAGE plpgsql
STABLE
ROWS 2000
AS $$
BEGIN
    RETURN QUERY
    SELECT e.*
    FROM optimizer_lab.events AS e
    WHERE e.tenant_id = p_tenant;
END;
$$;
~~~

### 34.3. Gọi SQL function với filter ngoài

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, event_type, payload
FROM optimizer_lab.get_events_sql(42)
WHERE event_type = 'purchase';
~~~

### 34.4. Gọi PL/pgSQL function với filter ngoài

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, event_type, payload
FROM optimizer_lab.get_events_plpgsql(42)
WHERE event_type = 'purchase';
~~~

### 34.5. So với query trực tiếp

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, event_type, payload
FROM optimizer_lab.events
WHERE tenant_id = 42
  AND event_type = 'purchase';
~~~

### 34.6. Quan sát

- SQL function có được inline thành scan trên events không?
- PL/pgSQL có hiện `Function Scan` không?
- Filter event_type đặt ở đâu?
- Số hàng từ function trước filter ngoài là bao nhiêu?
- Row estimate của Function Scan có gần actual không?
- Có sự khác biệt đáng kể về buffers/time không?

### 34.7. Không phải PL/pgSQL luôn chậm hơn

Nếu hàm PL/pgSQL trả rất ít hàng hoặc làm công việc không thể biểu diễn gọn trong SQL, chênh lệch có thể nhỏ hoặc phù hợp. Kết luận phải dựa trên workload và độ phức tạp thật.

## 35. Lab giảm rào cản bằng tham số hàm

Tạo hàm PL/pgSQL nhận cả tenant và event type:

~~~sql
CREATE FUNCTION optimizer_lab.get_events_filtered(
    p_tenant INTEGER,
    p_event_type TEXT
)
RETURNS SETOF optimizer_lab.events
LANGUAGE plpgsql
STABLE
ROWS 200
AS $$
BEGIN
    RETURN QUERY
    SELECT e.*
    FROM optimizer_lab.events AS e
    WHERE e.tenant_id = p_tenant
      AND e.event_type = p_event_type;
END;
$$;
~~~

Gọi:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, tenant_id, event_type
FROM optimizer_lab.get_events_filtered(42, 'purchase');
~~~

### 35.1. Ý nghĩa

Hàm PL/pgSQL vẫn có ranh giới function call, nhưng SQL bên trong đã nhận cả hai predicate. Planner của **câu SELECT trong function** có thể lập kế hoạch từ hai điều kiện đó.

### 35.2. Chú ý plan cache

Khi nhiều bộ tham số khác nhau được gọi lặp lại, PL/pgSQL có thể sử dụng kế hoạch được cache. Nếu phân phối dữ liệu theo tenant rất lệch, cần kiểm tra generic vs custom plan behavior trên version/workload.

### 35.3. Hàm trả tập khác hàm xử lý nghiệp vụ

Nếu function chỉ che một câu SELECT nhỏ, có thể đơn giản nhất là đưa SQL trực tiếp vào repository/query layer. Nếu function là API database ổn định và được gọi từ nhiều nơi, giữ abstraction có thể có lợi về bảo trì, nhưng cần quan sát kế hoạch.

## 36. Lab function predicate và expression index

### 36.1. Hàm chuẩn hóa

~~~sql
CREATE FUNCTION optimizer_lab.normalize_type(
    p_type TEXT
)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT lower(btrim(p_type));
$$;
~~~

### 36.2. Query gọi function trên cột

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM optimizer_lab.events
WHERE optimizer_lab.normalize_type(event_type) = 'purchase';
~~~

Index thường trên `event_type` không nhất thiết là access path trực tiếp cho predicate biểu thức đó.

### 36.3. Expression index

~~~sql
CREATE INDEX optimizer_events_type_normalized_idx
ON optimizer_lab.events (
    optimizer_lab.normalize_type(event_type)
);

ANALYZE optimizer_lab.events;
~~~

Chạy lại EXPLAIN.

### 36.4. Điều cần nhớ

- Function phải thực sự immutable cho trường hợp expression index.
- Index làm tăng chi phí ghi/lưu trữ.
- Planner có thể không dùng index nếu filter trả nhiều hàng.
- Sự tương đương ngữ nghĩa của biểu thức/collation cần nhất quán.
- Inlining function và việc dùng expression index là hai cơ chế khác nhau.

### 36.5. Không chỉnh IMMUTABLE giả để tạo index

Nếu hàm đọc bảng cấu hình, `now()</BT> hoặc trạng thái session, đánh dấu IMMUTABLE không sửa được thực tế đó. Nó có thể tạo một index không phản ánh đúng kết quả về sau.

## 37. Khi nào nên bỏ hoặc đổi cách tổ chức CTE?

Một số tình huống thực tế:

### 37.1. CTE materialized tạo quá nhiều hàng

Có thể:

- Chuyển sang `NOT MATERIALIZED` nếu đủ điều kiện và có lợi.
- Đặt predicate cần dùng vào CTE nếu đúng cho mọi consumer.
- Dùng subquery trực tiếp khi ngữ nghĩa rõ và cho planner thêm cơ hội tối ưu.
- Xem lại CTE có thật sự cần dùng nhiều lần hay không.

### 37.2. CTE tính biểu thức đắt nhiều lần

Có thể:

- Thử `MATERIALIZED`.
- Tính/nhúng một kết quả tạm có vòng đời được quản lý, nếu workload lớn và có lý do.
- Tái cấu trúc logic để tránh tính cùng biểu thức ở nhiều nhánh.

### 37.3. CTE nằm sau LIMIT/aggregate/window

Trước hết xác định đúng ngữ nghĩa; có những ranh giới không thể vượt mà vẫn giữ cùng kết quả.

### 37.4. CTE viết để tạo side effects

Không coi CTE là công cụ điều phối thứ tự tác dụng phụ tùy ý. Hãy thiết kế transaction và DML rõ ràng.

### 37.5. CTE giúp bảo trì đáng kể

Nếu kết quả và kế hoạch đủ tốt, không cần “làm phẳng” mọi CTE chỉ để tránh một rào cản không hề xuất hiện.

## 38. Khi nào nên đổi cách dùng function?

### 38.1. Hàm PL/pgSQL chỉ bọc một SELECT

Cân nhắc:

- Viết query trực tiếp.
- Viết `LANGUAGE sql STABLE` table function nếu hợp đồng cho phép và đo thấy inlining.
- Thêm điều kiện filter thành tham số để nội bộ không phải trả quá nhiều hàng.

### 38.2. Hàm xử lý trên từng row trong WHERE

Cân nhắc:

- Tránh wrap cột nếu có predicate tương đương, sargable.
- Dùng expression index khi function immutable và workload phù hợp.
- Precompute dữ liệu chuẩn hóa một cách đúng ngữ nghĩa nếu có lý do.
- Kiểm tra số lần gọi và cost thực.

### 38.3. Hàm trả tập có estimate sai

Cân nhắc `ROWS</BT> và `COST</BT>, nhưng hiểu đây là ước lượng planner, không phải giới hạn output. Đặt giá trị dựa trên dữ liệu đại diện.

### 38.4. Hàm có quyền đặc biệt

Giữ `SECURITY DEFINER</BT> khi cần; tối ưu nội bộ bằng query/index thích hợp, không bỏ kiểm soát quyền chỉ để inline.

### 38.5. Hàm dễ song song hóa

Nếu chứng minh được an toàn, đặt `PARALLEL SAFE</BT> có thể mở ra lựa chọn parallel plan. Không gắn SAFE cho hàm có side effects hoặc dùng session backend state không phù hợp.

## 39. Quy trình chẩn đoán hiệu năng thực tế

Thực hiện theo thứ tự:

1. **Ghi nhận query chậm thật**, bao gồm tham số phổ biến/hiếm.
2. **Kiểm tra phiên bản PostgreSQL**, vì hành vi CTE thay đổi từ 12.
3. Chạy `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)</BT> trong môi trường phù hợp.
4. Xác định có `CTE Scan</BT>, `Function Scan</BT>, Sort/HashAggregate/Materialize nodes hay không.
5. Tìm node đầu có estimated rows khác xa actual rows.
6. Xem filter được áp dụng ở đâu, có qua ranh giới không.
7. Xem số hàng bị loại sau khi đã tạo kết quả lớn.
8. Đối chiếu số lần quét và `loops</BT>.
9. Kiểm tra index, statistics và `ANALYZE</BT>.
10. Với CTE một tham chiếu, thử mặc định so với MATERIALIZED nếu có lý do.
11. Với CTE nhiều tham chiếu, thử mặc định so với NOT MATERIALIZED.
12. Với hàm, phân biệt SQL/PLpgSQL, scalar/table, inlining và volatility.
13. Kiểm tra `COST</BT>/`ROWS</BT> nếu Function Scan ước lượng sai.
14. Kiểm tra predicate trên function và khả năng dùng expression index.
15. Đo nhiều lần với dữ liệu đại diện, tránh quy kết từ một lần.
16. Không bỏ các ranh giới bảo mật hoặc ngữ nghĩa.
17. Triển khai thay đổi có rollback và giám sát p95/p99 cùng database load.

### 39.1. Khi query chậm không liên quan CTE/function

Nếu query plan cho thấy scan 200 triệu hàng do filter không chọn lọc, hoặc dữ liệu trả qua network quá lớn, vấn đề có thể nằm ở indexing, pagination hoặc schema, không phải CTE.

### 39.2. Không dùng enable_* để chữa triệu chứng

Các tham số như `enable_nestloop` hữu ích để thăm dò plan trong môi trường debug, nhưng không nên coi việc tắt vĩnh viễn một thuật toán join là giải pháp thay cho thống kê/SQL/index đúng.

### 39.3. Đo planning time

Folding một query phức tạp qua nhiều CTE có thể tăng độ phức tạp kế hoạch. Với workload có hàng nghìn truy vấn nhỏ mỗi giây, planning time cũng có thể quan trọng.

## 40. Những hiểu lầm thường gặp

### 40.1. “CTE luôn được materialize”

**Sai trên PostgreSQL 12+** đối với CTE đủ điều kiện. CTE một tham chiếu thường được fold.

### 40.2. “CTE giờ luôn được inline”

Sai. Nhiều tham chiếu, recursion, volatile và DML có cơ chế khác.

### 40.3. “NOT MATERIALIZED chắc chắn nhanh hơn”

Sai. Nó có thể lặp lại công việc đắt tiền.

### 40.4. “MATERIALIZED chắc chắn chậm”

Sai. Tính chung một kết quả đắt cho nhiều consumers có thể nhanh hơn.

### 40.5. “MATERIALIZED CTE bắt buộc tính toàn bộ kết quả ngay trước khi query ngoài chạy”

Không luôn đúng: executor có thể chỉ yêu cầu phần kết quả cần thiết theo cấu trúc consumer, dù các operator như sort/join thường khiến phải đọc nhiều hoặc tất cả.

### 40.6. “Thêm NOT MATERIALIZED cho VOLATILE CTE sẽ ép function chạy bao nhiêu lần tùy ý”

Sai. Eligibility và bảo toàn ngữ nghĩa vẫn có hiệu lực.

### 40.7. “CTE là bảng tạm có index”

Sai. Materialized CTE result không phải một temporary table được người dùng tạo với indexes tùy ý.

### 40.8. “Subquery luôn được tối ưu tốt hơn CTE”

Sai. CTE một tham chiếu đủ điều kiện có thể được fold tương tự subquery.

### 40.9. “Đẩy mọi WHERE vào CTE đều đúng”

Sai khi CTE dùng nhiều consumers hoặc có LIMIT/aggregation/window semantics.

### 40.10. “Một CTE có ORDER BY sẽ bảo đảm kết quả ngoài cùng được sắp xếp”

Không nên dựa vào đó nếu outermost SELECT không có ORDER BY cần thiết.

### 40.11. “Function LANGUAGE sql luôn inline”

Sai. Cần đáp ứng nhiều điều kiện.

### 40.12. “Function PL/pgSQL hoàn toàn không được PostgreSQL tối ưu”

Sai. SQL bên trong vẫn được planner tối ưu, nhưng caller không tự gộp toàn bộ procedural body.

### 40.13. “Chỉ cần tăng COST là query nhanh hơn”

Sai. COST chỉ là ước lượng chi phí, không thay mã hàm hay access path.

### 40.14. “ROWS là LIMIT số hàng hàm trả”

Sai. Nó là ước lượng cardinality cho planner.

### 40.15. “PARALLEL SAFE chỉ là gợi ý không ảnh hưởng tính đúng”

Sai. Khai báo sai có thể gây lỗi/hành vi không an toàn.

### 40.16. “Có thể gắn IMMUTABLE cho hàm đọc bảng để được inline”

Sai. Hàm phụ thuộc dữ liệu thay đổi không được khai báo IMMUTABLE chỉ vì muốn plan tốt.

### 40.17. “STRICT luôn đúng cho hàm nhận NULL”

Sai nếu hàm cần xử lý NULL và trả giá trị khác NULL.

### 40.18. “Bỏ SECURITY DEFINER sẽ giúp plan nên cứ bỏ”

Sai vì có thể thay đổi quyền và tạo lỗ hổng bảo mật.

### 40.19. “Function trên cột luôn cấm mọi index”

Không tuyệt đối. Expression index phù hợp có thể dùng, và một số biểu thức được planner biến đổi.

### 40.20. “Index expression có thể dùng với mọi hàm VOLATILE”

Sai. Function trong index expression phải thỏa yêu cầu immutability.

### 40.21. “CTE có CTE Scan nghĩa query chắc chắn bị chậm”

Sai. Cần đo chi phí và workload.

### 40.22. “Không thấy CTE Scan nghĩa câu SQL không còn CTE”

Không. CTE có thể được fold, dù nguồn SQL vẫn có WITH.

### 40.23. “Mọi Function Scan đều cần đổi thành SQL inline”

Không. Có những chức năng set-returning chuyên biệt, yêu cầu bảo mật hoặc procedural semantics chính đáng.

### 40.24. “Inlining luôn cho plan tốt vì optimizer thấy nhiều hơn”

Không luôn. Có thể tăng duplicated work hoặc planning complexity; đo thực tế.

### 40.25. “EXPLAIN ANALYZE không chạy câu SQL”

Sai. Nó thực thi query. Với INSERT/UPDATE/DELETE, cần transaction thử nghiệm/rollback hoặc môi trường phù hợp.

## 41. Bài tập thực hành

### Bài 1 — CTE một lần tham chiếu

PostgreSQL 15 có một CTE non-recursive SELECT không volatile, được dùng một lần. Mặc định thường fold hay materialize?

**Gợi ý:** Thường fold.

### Bài 2 — Phiên bản cũ

Vì sao một bài tối ưu PostgreSQL 10 nói “CTE là optimization fence” có thể không áp dụng nguyên vẹn cho PostgreSQL 15?

**Gợi ý:** Folding CTE được hỗ trợ từ PostgreSQL 12.

### Bài 3 — MATERIALIZED

Lệnh nào yêu cầu CTE giữ materialization boundary?

~~~sql
WITH x AS MATERIALIZED (
    SELECT *
    FROM optimizer_lab.events
)
SELECT *
FROM x
WHERE tenant_id = 42;
~~~

### Bài 4 — Pushdown

Điều kiện tenant=42 nằm bên ngoài `x AS MATERIALIZED (SELECT * FROM events)</BT>. Nó có được tự đẩy vào base scan bên trong CTE theo cách folding không?

**Gợi ý:** Không qua ranh giới MATERIALIZED.

### Bài 5 — NOT MATERIALIZED

Một CTE được dùng hai lần với hai predicate chọn lọc khác nhau. Vì sao NOT MATERIALIZED có thể giúp?

**Gợi ý:** Mỗi nhánh được tối ưu riêng và có thể pushdown filter.

### Bài 6 — Tính lặp

Khi nào NOT MATERIALIZED có thể tệ hơn materialization?

**Gợi ý:** Phần CTE rất đắt và nhiều consumers dùng gần toàn bộ dữ liệu.

### Bài 7 — CTE Scan

Dấu hiệu nào trong EXPLAIN cho thấy một kết quả CTE riêng đang được scan?

**Gợi ý:** CTE Scan.

### Bài 8 — Query không có CTE Scan

Không thấy CTE Scan có nghĩa PostgreSQL không hiểu WITH không?

**Gợi ý:** Không, CTE có thể được fold.

### Bài 9 — LIMIT đổi nghĩa

So sánh “top 100 toàn bảng rồi lọc tenant” với “lọc tenant rồi lấy top 100”. Có giống nhau không?

**Đáp án:** Không.

### Bài 10 — ORDER BY

Vì sao nên đặt ORDER BY ở SELECT ngoài cùng khi cần bảo đảm thứ tự kết quả?

**Gợi ý:** Thứ tự giữa các bước trung gian không phải hợp đồng cuối.

### Bài 11 — VOLATILE

`WITH x AS (SELECT random()) ...</BT> có thuộc nhóm CTE side-effect-free được fold tự do không?

**Đáp án:** Không.

### Bài 12 — NOT MATERIALIZED với volatile

Có thể gắn NOT MATERIALIZED để bỏ qua giới hạn an toàn của volatile expression không?

**Đáp án:** Không.

### Bài 13 — Recursive CTE

Trong EXPLAIN của WITH RECURSIVE, tên node nào có thể xuất hiện?

**Gợi ý:** Recursive Union, WorkTable Scan.

### Bài 14 — DML CTE

Vì sao `WITH inserted AS (INSERT ... RETURNING ...)</BT> không nên được xem như một SELECT CTE side-effect-free?

**Gợi ý:** Có tác dụng ghi dữ liệu và semantics riêng.

### Bài 15 — Hàm SQL

Một scalar SQL function tính `x*2</BT> và khai báo IMMUTABLE có thể inline không?

**Gợi ý:** Có thể nếu đáp ứng điều kiện, không phải cam kết vô điều kiện.

### Bài 16 — PL/pgSQL

Vì sao filter ở caller có thể không được đẩy vào SELECT bên trong PL/pgSQL function?

**Gợi ý:** Planner ngoài không inline procedural body như SQL thông thường.

### Bài 17 — Function Scan

Nếu EXPLAIN hiển thị Function Scan và Filter bên ngoài, cần quan tâm chỉ số gì?

**Gợi ý:** ROWS estimate, actual rows, số hàng bị loại sau function và thời gian.

### Bài 18 — Hàm STABLE

Một SQL function đọc bảng events có nên khai báo IMMUTABLE không nếu bảng có thể thay đổi?

**Đáp án:** Không.

### Bài 19 — Volatility

Phân loại `random()</BT> và phép nhân số thuần theo VOLATILE/IMMUTABLE.

**Gợi ý:** random volatile; phép nhân thuần immutable.

### Bài 20 — STRICT

Một hàm cần biến NULL thành 'unknown' có nên khai báo STRICT không?

**Đáp án:** Không.

### Bài 21 — ROWS

`ROWS 1000` có giới hạn số hàng trả về ở 1.000 không?

**Đáp án:** Không.

### Bài 22 — COST

COST 100 có nghĩa 100ms không?

**Đáp án:** Không, là đơn vị ước lượng planner.

### Bài 23 — PARALLEL SAFE

Có nên đánh dấu mọi function là PARALLEL SAFE để luôn có parallel plan không?

**Đáp án:** Không.

### Bài 24 — SECURITY DEFINER

Tại sao không bỏ SECURITY DEFINER chỉ vì muốn inline?

**Gợi ý:** Nó thay đổi mô hình quyền và an toàn.

### Bài 25 — Expression index

Viết index cho `lower(btrim(event_type))` trên bảng lab.

~~~sql
CREATE INDEX optimizer_events_type_expr_idx
ON optimizer_lab.events (lower(btrim(event_type)));
~~~

### Bài 26 — Sargability

Nếu có index trên cột event_type, WHERE `lower(event_type)='purchase'` chắc chắn dùng index đó không?

**Gợi ý:** Không. Cần xem expression index và plan.

### Bài 27 — Gọi function trên mỗi row

Một PL/pgSQL function đắt được gọi ở WHERE trên một triệu hàng. Hai hướng tối ưu?

**Gợi ý:** Lọc sớm bằng điều kiện sargable, đổi thành SQL thuần/index expression nếu phù hợp.

### Bài 28 — Query trực tiếp

Trong lab, viết query trực tiếp lọc tenant=42 và event_type='purchase' rồi EXPLAIN. Đối chiếu với get_events_plpgsql.

### Bài 29 — Tham số hàm

Vì sao `get_events_filtered(tenant,type)</BT> có thể hiệu quả hơn hàm chỉ nhận tenant rồi filter type ở caller?

**Gợi ý:** Cả hai filter đã nằm trong SQL bên trong function.

### Bài 30 — Plan cache

Vì sao một tenant có 100 hàng và tenant khác có một triệu hàng có thể khiến generic plan kém phù hợp?

**Gợi ý:** Một plan dùng chung có thể không tối ưu cho mọi phân phối tham số.

### Bài 31 — EXPLAIN ANALYZE

Có thể chạy `EXPLAIN ANALYZE DELETE ...` trên production rồi nghĩ dữ liệu không đổi không?

**Đáp án:** Không; ANALYZE thực thi.

### Bài 32 — Filter và CTE

Một CTE materialized phục vụ hai consumer, một cần tenant 42, một cần tenant 77. Có thể luôn đẩy tenant=42 vào CTE chung không?

**Đáp án:** Không, sẽ đổi kết quả consumer còn lại.

### Bài 33 — Aggregate boundary

Vì sao điều kiện `event_count>1000` sau GROUP BY không thể đẩy thành WHERE trên từng event tùy ý?

**Gợi ý:** Nó lọc nhóm, không phải hàng gốc.

### Bài 34 — Index vs materialization

Nếu query chậm vì CTE materialized phải xử lý nhiều tenant, thêm index trên tenant có chắc giải quyết không?

**Gợi ý:** Không nếu filter tenant vẫn nằm ngoài CTE và không được pushdown; cần xem query shape.

### Bài 35 — Thứ tự JOIN

Tại sao materialized CTE bọc một JOIN lớn có thể khiến planner ngoài khó chọn join order tối ưu với một bảng có filter rất chọn lọc?

**Gợi ý:** Ranh giới CTE hạn chế tái sắp xếp xuyên qua nó.

### Bài 36 — Bảo mật function

Một SECURITY DEFINER function dùng dynamic SQL từ client. Cần kiểm tra gì ngoài EXPLAIN?

**Gợi ý:** search_path, quyền, SQL injection, identifier quoting và parameter binding.

### Bài 37 — Đo đúng

Cùng một query trước và sau NOT MATERIALIZED có thời gian 20ms và 19ms trong một lần chạy. Đã đủ kết luận tăng tốc chắc chắn chưa?

**Gợi ý:** Chưa; đo nhiều lần, cache, load, buffers và plan.

### Bài 38 — CTE nhiều consumers

Bạn có một CTE tính tổng hợp đắt được dùng ở 4 nhánh, tất cả cần gần toàn bộ kết quả. Nên thử gì trước?

**Gợi ý:** Mặc định materialized/MATERIALIZED và đo so với NOT MATERIALIZED.

### Bài 39 — Ranh giới an toàn

Một function cần quyền chủ sở hữu và gắn SET search_path. Bạn có nên sửa thuộc tính để ép SQL inlining không?

**Đáp án:** Không nếu làm thay security semantics.

### Bài 40 — Tóm tắt quyết định

Với ba truy vấn:

1. CTE SELECT thuần một lần tham chiếu.
2. CTE SELECT thuần hai lần tham chiếu nhưng mỗi nhánh lọc rất hẹp.
3. Function PL/pgSQL trả 200.000 hàng rồi caller lọc còn 100.

Hãy đề xuất chiến lược thử nghiệm tương ứng.

**Gợi ý:** (1) giữ mặc định và EXPLAIN, (2) thử NOT MATERIALIZED, (3) đưa filter vào function hoặc dùng query/SQL-function thích hợp rồi đo.

## 42. Bảng ghi nhớ nhanh

| Vấn đề | Điều cần nhớ |
|---|---|
| CTE trong PostgreSQL 11 trở về trước | Thường là optimization fence mạnh |
| CTE trong PostgreSQL 12+ | Có thể fold nếu đủ điều kiện |
| CTE một lần tham chiếu | Thường fold mặc định nếu SELECT side-effect-free |
| CTE nhiều lần tham chiếu | Thường materialize mặc định |
| `AS MATERIALIZED` | Yêu cầu giữ kết quả CTE riêng/ranh giới |
| `AS NOT MATERIALIZED` | Cho phép folding, có nguy cơ lặp tính |
| Volatile CTE | Không fold tự do theo NOT MATERIALIZED |
| Recursive CTE | Cơ chế recursive, không đơn giản inline |
| Data-modifying CTE | Semantics DML và RETURNING riêng |
| CTE Scan | Dấu hiệu scan kết quả CTE |
| WorkTable Scan | Thường liên quan recursive query |
| Predicate pushdown | Đưa filter xuống sớm nếu đúng ngữ nghĩa |
| Materialization cost | Công tính kết quả trung gian, memory/disk, filter muộn |
| Materialization benefit | Tính một lần cho nhiều consumers |
| SQL function | Có thể inline khi đáp ứng điều kiện |
| PL/pgSQL | Planner caller không tự inline procedural body |
| Function Scan | Lời gọi set-returning function ở plan |
| `VOLATILE` | Kết quả/tác dụng có thể đổi; hạn chế biến đổi |
| `STABLE` | Kết quả nhất quán trong statement theo hợp đồng |
| `IMMUTABLE` | Cùng input cho cùng output bền vững |
| `STRICT` | NULL input trả NULL không gọi body |
| `COST` | Giá trị chi phí tương đối, không phải milliseconds |
| `ROWS` | Ước lượng cardinality của set-returning function |
| `PARALLEL SAFE` | Phải thực sự an toàn cho parallel worker |
| `SECURITY DEFINER` | Ngữ nghĩa quyền, không bỏ để ép inlining |
| WHERE function(column) | Có thể cần expression index/query rewrite |
| Expression index | Phải dùng biểu thức/hàm thỏa immutability |
| LIMIT/aggregate/window | Ranh giới ngữ nghĩa, không pushdown tùy ý |
| EXPLAIN ANALYZE | Chạy thật, có actual rows và timing |
| So sánh plan | Scan, CTE/Function Scan, filters, buffers, loops |
| Quyết định tối ưu | Theo workload và phép đo có kiểm soát |

---

## Kết luận

**CTE và hàm tự định nghĩa không mặc nhiên chậm**. Ảnh hưởng lớn nhất của chúng đến tối ưu truy vấn nằm ở việc planner có thể **nhìn xuyên qua ranh giới** để đẩy điều kiện lọc, đổi thứ tự JOIN và chọn access path hay không.

Từ PostgreSQL 12, CTE SELECT đủ điều kiện được tham chiếu một lần thường được fold vào parent query, nên lời khuyên cũ “WITH luôn là optimization fence” không còn đúng chung. Với CTE nhiều tham chiếu, **MATERIALIZED** có thể tiết kiệm công việc lặp, còn **NOT MATERIALIZED** có thể cho phép mỗi nhánh lọc sớm và tận dụng index. Nhưng hai lựa chọn đánh đổi chi phí khác nhau, và recursive/data-modifying/volatile CTE có những giới hạn riêng.

Tương tự, **SQL function có thể được inline** khi cấu trúc và thuộc tính cho phép, còn **PL/pgSQL** thường tạo ranh giới giữa caller và SQL bên trong. Các khai báo `VOLATILE</BT>, `STABLE</BT>, `IMMUTABLE</BT>, `COST</BT>, `ROWS</BT>, `PARALLEL</BT> và `SECURITY DEFINER</BT> đều có thể ảnh hưởng kế hoạch hoặc tính đúng. Không bao giờ khai báo sai volatility hay bỏ bảo vệ quyền chỉ để có một kế hoạch đẹp hơn.

Cách tối ưu đáng tin cậy là **EXPLAIN (ANALYZE, BUFFERS)** trên dữ liệu đại diện, quan sát `CTE Scan</BT>/`Function Scan</BT>, vị trí filter, số hàng trung gian, số lần gọi, thời gian và I/O, rồi thử thay đổi có chủ đích. Giữ cấu trúc SQL dễ bảo trì khi không gây hại; loại bỏ rào cản chỉ khi đã xác định rõ **nó cản trở phép tối ưu nào và việc bỏ nó không đổi ngữ nghĩa hoặc bảo mật**.

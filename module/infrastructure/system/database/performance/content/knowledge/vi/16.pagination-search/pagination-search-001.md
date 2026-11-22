# Chi phí của OFFSET khi chuyển đến các trang sâu

Phân trang bằng OFFSET và LIMIT là cách đơn giản để chia kết quả truy vấn thành từng trang. Ở những trang đầu, cách này thường hoạt động tốt vì cơ sở dữ liệu chỉ cần đọc và bỏ qua một lượng hàng nhỏ trước khi trả kết quả. Nhưng khi người dùng chuyển đến trang sâu, chi phí có thể tăng theo số hàng phải bỏ qua. Truy vấn yêu cầu trang thứ 10.000 có thể phải duyệt qua hàng trăm nghìn hàng trước khi trả về vài chục hàng cần hiển thị.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần hiểu rằng LIMIT giới hạn số hàng trả về, còn OFFSET xác định số hàng đầu tiên phải bỏ qua trong thứ tự kết quả. OFFSET lớn không có nghĩa hệ quản trị có thể nhảy thẳng đến vị trí đó trong mọi kế hoạch. Tùy chỉ mục, thứ tự sắp xếp, điều kiện lọc và hệ quản trị, nó có thể phải duyệt, kiểm tra, sắp xếp hoặc đọc nhiều hàng rồi mới loại phần đầu.

Bài học này phân tích chi phí của OFFSET ở các trang sâu, cách đọc kế hoạch thực thi, ảnh hưởng của chỉ mục và độ rộng hàng, các phương án thay thế như keyset pagination, deferred join và cursor, cùng cách giữ thứ tự ổn định và kiểm chứng hiệu năng trong workload thực tế.

## 1. Cơ chế của LIMIT và OFFSET

Một truy vấn phân trang phổ biến:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 0;
~~~

LIMIT 20 yêu cầu tối đa 20 hàng. OFFSET 0 không bỏ qua hàng nào. Khi chuyển sang trang thứ hai với kích thước 20:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 20;
~~~

Truy vấn bỏ qua 20 hàng đầu trong thứ tự đã sắp xếp và trả 20 hàng tiếp theo. Trang thứ 1000 với kích thước 20 cần bỏ qua 19.980 hàng:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 19980;
~~~

Về mặt logic, hệ quản trị phải xác định thứ tự kết quả, loại bỏ phần đầu và trả phần tiếp theo. Với kế hoạch dựa trên scan hoặc index scan tuần tự theo thứ tự, số hàng cần xử lý tối thiểu có thể gần bằng:

\[
N_{processed}\approx OFFSET+LIMIT
\]

Đây là mô hình khái quát để hiểu xu hướng, không phải cam kết số hàng vật lý chính xác cho mọi kế hoạch. Bộ lọc, join, sort, parallelism và cách hệ quản trị thực hiện LIMIT/OFFSET có thể làm số hàng ở từng operator khác nhau.

Với OFFSET 500.000 và LIMIT 20, truy vấn có thể phải xử lý hơn nửa triệu hàng để trả 20 hàng. Nếu mỗi hàng cần truy cập bảng hoặc thực hiện phép join, chi phí có thể lớn hơn nhiều so với việc chỉ đọc một đoạn nhỏ của chỉ mục.

## 2. Vì sao OFFSET sâu thường chậm?

### 2.1. Phải duyệt qua các hàng bị bỏ qua

OFFSET biểu thị số hàng cần loại khỏi kết quả sau khi xác định thứ tự. Với B-tree index scan theo thứ tự phù hợp, cơ sở dữ liệu có thể tránh sort toàn bộ dữ liệu, nhưng vẫn có thể phải đi qua các entry của chỉ mục để bỏ qua OFFSET hàng trước khi lấy LIMIT hàng tiếp theo.

Ví dụ, chỉ mục có thể cung cấp thứ tự created_at DESC, order_id DESC. Truy vấn không cần sort riêng, nhưng khi OFFSET tăng từ 0 lên 500.000, iterator vẫn phải tiến qua số lượng entry lớn hơn trước khi trả kết quả.

### 2.2. Sort có thể phải xử lý tập dữ liệu lớn

Nếu không có chỉ mục hỗ trợ ORDER BY, hệ quản trị có thể cần đọc tất cả hàng phù hợp, sau đó sắp xếp để xác định đoạn kết quả. Một số optimizer sử dụng top-N sort hoặc thuật toán giới hạn bộ nhớ để chỉ giữ một phần ứng viên, nhưng khi OFFSET lớn, số hàng cần giữ hoặc xét vẫn có thể gần bằng OFFSET + LIMIT.

Nếu sort vượt ngân sách bộ nhớ, dữ liệu có thể được ghi ra vùng lưu trữ tạm. Khi đó truy vấn vừa tốn CPU để sắp xếp vừa phát sinh I/O tạm.

### 2.3. Truy cập bảng cho những hàng cuối cùng không cần thiết

Một truy vấn có thể đọc nhiều cột từ bảng trong khi phần lớn hàng sẽ bị OFFSET loại bỏ. Nếu chỉ mục không bao phủ các cột cần trả về, hệ quản trị có thể phải truy cập heap/table cho rất nhiều entry trước khi tìm đến 20 hàng cuối.

Đây là một lý do khiến truy vấn có OFFSET sâu và SELECT nhiều cột trở nên đắt hơn. Cần phân biệt chi phí đọc index entry với chi phí lấy payload từ bảng.

### 2.4. Join và filter có thể khuếch đại công việc

Nếu truy vấn join nhiều bảng trước khi phân trang, cơ sở dữ liệu có thể tạo hoặc xử lý tập trung gian lớn rồi mới sắp xếp và bỏ qua hàng. Nếu điều kiện lọc không được đẩy xuống sớm hoặc join làm tăng số hàng, chi phí có thể vượt xa OFFSET + LIMIT.

Với truy vấn phân trang, hãy xem LIMIT/OFFSET được áp dụng ở đâu trong cây thực thi. Nếu operator phía dưới phải tạo hàng triệu kết quả join trước khi Limit nhận dữ liệu, nút thắt có thể nằm ở join order, cardinality hoặc predicate chứ không chỉ ở OFFSET.

### 2.5. Chi phí tăng theo độ sâu trang

Với kích thước trang cố định, OFFSET tăng gần tuyến tính theo số trang. Nếu mỗi trang có 50 hàng, trang 1 bỏ qua 0 hàng, trang 1000 bỏ qua 49.950 hàng và trang 100.000 bỏ qua gần 5 triệu hàng. Thời gian thực tế không nhất thiết tăng tuyến tính hoàn hảo vì cache, I/O, sort và kế hoạch có thể thay đổi, nhưng số hàng phải duyệt thường tăng theo độ sâu.

## 3. ORDER BY phải xác định thứ tự duy nhất

Phân trang cần thứ tự xác định. Nếu ORDER BY chỉ dùng một cột không duy nhất, các hàng có cùng giá trị sắp xếp có thể xuất hiện theo thứ tự khác nhau giữa các lần chạy.

Ví dụ:

~~~sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 20 OFFSET 20;
~~~

Nếu nhiều đơn hàng có cùng created_at, thứ tự giữa chúng không được xác định đầy đủ. Cơ sở dữ liệu có thể trả các hàng đồng hạng theo thứ tự khác khi kế hoạch, dữ liệu hoặc trạng thái vật lý thay đổi. Điều này có thể gây lặp hoặc bỏ sót hàng giữa các trang.

Thêm một khóa duy nhất làm tie-breaker:

~~~sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 20;
~~~

Nếu order_id là khóa duy nhất, tổ hợp thứ tự đã xác định được vị trí của từng hàng. Quy tắc này cũng rất quan trọng với keyset pagination vì điều kiện trang tiếp theo phải so sánh đầy đủ tất cả cột trong thứ tự.

Thứ tự duy nhất giúp ổn định khi dữ liệu không đổi. Nó không tự bảo đảm các trang nhất quán khi có INSERT, DELETE hoặc UPDATE đồng thời. Vấn đề nhất quán giữa các trang cần được xem xét riêng.

## 4. Đọc kế hoạch thực thi của truy vấn OFFSET

Khi điều tra một truy vấn phân trang, hãy thu thập kế hoạch ước lượng và kế hoạch thực tế trong môi trường phù hợp. Tập trung vào các điểm sau:

- **Scan:** hệ quản trị đọc bao nhiêu hàng hoặc trang từ bảng/chỉ mục?
- **Sort:** có bước sort không, sort xử lý bao nhiêu hàng, có ghi dữ liệu tạm không?
- **Filter:** có nhiều hàng bị loại sau khi đọc không?
- **Join:** có tạo nhiều hàng trung gian trước Limit không?
- **Limit/Top:** operator nhận bao nhiêu hàng và phát ra bao nhiêu hàng?
- **Buffers/I/O:** số block hoặc logical reads tăng thế nào theo OFFSET?
- **Actual rows và loops:** số hàng thực tế cùng số lần thực thi của từng operator.

Ví dụ kế hoạch khái quát:

~~~text
Limit
  -> Index Scan using orders_customer_created_idx
       Index Cond: (customer_id = 42)
       actual rows=200020
       Rows Removed/consumed before output: approximately 200000
~~~

Nếu index scan đã cung cấp đúng thứ tự, truy vấn có thể không cần Sort. Nhưng để trả trang sâu với OFFSET 200.000 và LIMIT 20, nó vẫn phải tiến qua nhiều entry. Hãy so sánh actual rows của scan, buffers và thời gian khi OFFSET tăng.

Một kế hoạch khác:

~~~text
Limit
  -> Sort
       Sort Key: created_at DESC, order_id DESC
       -> Seq Scan on orders
            Filter: (customer_id = 42)
~~~

Kế hoạch này cho thấy truy vấn phải đọc các hàng phù hợp rồi sort trước khi Limit có thể xác định đoạn cần trả. Nếu sort spill ra đĩa, chi phí có thể rất cao. Cần kiểm tra chỉ mục phù hợp, selectivity của customer_id, thống kê và số cột cần lấy.

Không cộng thời gian của tất cả operator một cách máy móc vì thời gian ở nút cha có thể bao gồm thời gian nút con. Dùng tổng thời gian truy vấn và số liệu từng operator để định vị phần công việc.

## 5. Chỉ mục có thể giảm chi phí nào?

Một chỉ mục phù hợp có thể loại bỏ bước sort và thu hẹp vùng dữ liệu cần đọc. Ví dụ:

~~~sql
CREATE INDEX orders_customer_created_id_idx
ON orders (customer_id, created_at DESC, order_id DESC);
~~~

Truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 200000;
~~~

Điều kiện bằng trên customer_id giới hạn vùng khóa, còn created_at và order_id cung cấp thứ tự. Tùy hệ quản trị và thiết kế chỉ mục, scan có thể đọc theo thứ tự cần thiết mà không sort riêng.

Tuy nhiên, chỉ mục không làm mất chi phí phải bỏ qua OFFSET. Hệ quản trị vẫn có thể duyệt qua 200.000 entry trong vùng customer_id trước khi lấy 20 entry tiếp theo.

### 5.1. Chỉ mục bao phủ

Nếu truy vấn cần cột total_amount ngoài các cột khóa, hệ quản trị có thể phải truy cập bảng để lấy giá trị. Một số hệ quản trị hỗ trợ cột include hoặc cơ chế covering index:

~~~sql
-- Ví dụ PostgreSQL
CREATE INDEX orders_customer_created_id_cover_idx
ON orders (customer_id, created_at DESC, order_id DESC)
INCLUDE (total_amount);
~~~

Chỉ mục bao phủ có thể giảm heap/table lookup khi điều kiện visibility và các yếu tố khác cho phép. Nhưng thêm cột vào chỉ mục làm tăng kích thước, chi phí ghi và bộ nhớ cache. Không nên đưa mọi cột của SELECT vào chỉ mục mà chưa đo lợi ích.

### 5.2. Phạm vi chỉ mục và điều kiện lọc

Nếu truy vấn luôn lọc theo trạng thái đang mở, có thể cân nhắc chỉ mục một phần hoặc filtered index khi hệ quản trị hỗ trợ:

~~~sql
CREATE INDEX orders_open_customer_created_idx
ON orders (customer_id, created_at DESC, order_id DESC)
WHERE status = 'OPEN';
~~~

Điều kiện truy vấn phải phù hợp với predicate của chỉ mục và optimizer phải chứng minh được tính tương thích. Chỉ mục nhỏ hơn có thể giảm lượng entry phải duyệt, nhưng vẫn không giải quyết hoàn toàn việc bỏ qua OFFSET sâu.

## 6. Keyset pagination (seek method)

Keyset pagination, còn gọi là seek method hoặc cursor-based pagination, dùng giá trị của hàng cuối trang hiện tại làm mốc để tìm trang tiếp theo. Thay vì đếm và bỏ qua hàng đầu, truy vấn tìm các hàng đứng sau mốc trong thứ tự đã chọn.

Với thứ tự:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Giả sử hàng cuối trang hiện tại có:

- created_at = 2026-11-19 10:30:00
- order_id = 8450

Trang tiếp theo dùng điều kiện:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND (
      created_at < TIMESTAMP '2026-11-19 10:30:00'
      OR (
          created_at = TIMESTAMP '2026-11-19 10:30:00'
          AND order_id < 8450
      )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Điều kiện này yêu cầu hàng có created_at nhỏ hơn mốc; nếu bằng thời điểm thì order_id phải nhỏ hơn khóa cuối trang. Nó giữ đúng thứ tự giảm dần và tạo điểm bắt đầu để B-tree tìm vùng khóa kế tiếp.

Với chỉ mục:

~~~sql
CREATE INDEX orders_customer_created_id_idx
ON orders (customer_id, created_at DESC, order_id DESC);
~~~

truy vấn có thể seek đến vị trí gần mốc và đọc khoảng 20 hàng tiếp theo, thay vì duyệt hàng trăm nghìn hàng trước đó. Chi phí thường phụ thuộc số hàng trả về và độ chọn lọc của điều kiện, thay vì tăng theo số trang đã đi qua.

### 6.1. Dùng row-value comparison khi phù hợp

Một số hệ quản trị hỗ trợ so sánh tuple:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND (created_at, order_id) < (
      TIMESTAMP '2026-11-19 10:30:00',
      8450
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Với thứ tự giảm dần trên cả hai cột, điều kiện tuple nhỏ hơn biểu diễn các hàng đứng sau mốc. Hỗ trợ tuple comparison và cách optimizer ánh xạ nó thành range scan phụ thuộc hệ quản trị, kiểu dữ liệu và NULL. Hãy kiểm tra execution plan thay vì giả định mọi DBMS đều tối ưu giống nhau.

### 6.2. Thứ tự hỗn hợp ASC và DESC

Nếu thứ tự gồm cả chiều tăng và giảm, điều kiện keyset phải phản ánh đúng thứ tự từ điển của từng thành phần. Ví dụ:

~~~sql
ORDER BY priority ASC, created_at DESC, ticket_id ASC
~~~

Điều kiện trang tiếp theo phải gồm các nhánh so sánh:

- priority lớn hơn mốc.
- Hoặc priority bằng mốc và created_at nhỏ hơn.
- Hoặc hai cột đầu bằng mốc và ticket_id lớn hơn.

~~~sql
WHERE priority > :last_priority
   OR (
       priority = :last_priority
       AND created_at < :last_created_at
   )
   OR (
       priority = :last_priority
       AND created_at = :last_created_at
       AND ticket_id > :last_ticket_id
   )
~~~

Điều kiện này dài hơn nhưng thể hiện đúng thứ tự hỗn hợp. Cần kiểm tra khả năng sử dụng chỉ mục và số hàng thực tế trong kế hoạch.

## 7. Các trường hợp khó của keyset pagination

### 7.1. Cột sắp xếp có thể NULL

NULL không tham gia so sánh thông thường theo cách giống giá trị. Nếu cột sort có NULL, điều kiện nhỏ hơn/lớn hơn có thể bỏ qua các hàng NULL hoặc không tạo được thứ tự tiếp nối như mong đợi.

Có thể:

- Chọn cột NOT NULL làm khóa sắp xếp.
- Chuẩn hóa NULL thành một giá trị có ý nghĩa bằng biểu thức và expression index phù hợp, nếu bảo toàn nghiệp vụ.
- Xử lý riêng nhóm NULL với điều kiện rõ ràng.
- Dùng NULLS FIRST hoặc NULLS LAST nếu hệ quản trị hỗ trợ, rồi viết logic cursor tương ứng.

Phải xác định rõ thứ tự NULL của hệ quản trị và biểu thức ORDER BY. Không nên giả định thứ tự NULL mặc định giống nhau giữa PostgreSQL, MySQL, SQL Server và Oracle.

### 7.2. Giá trị sắp xếp có thể thay đổi

Nếu created_at, priority hoặc một cột sắp xếp bị cập nhật trong lúc người dùng chuyển trang, một hàng có thể di chuyển qua mốc cursor. Hàng đã hiển thị có thể xuất hiện lại hoặc hàng chưa hiển thị có thể bị bỏ qua.

Keyset giảm ảnh hưởng của insert/delete ở đầu danh sách so với OFFSET, nhưng không bảo đảm snapshot nhất quán nếu các cột sort thay đổi. Có thể dùng khóa sắp xếp bất biến, snapshot transaction phù hợp hoặc mốc dữ liệu cố định theo nghiệp vụ.

### 7.3. Composite key phải đủ duy nhất

Nếu created_at không duy nhất, cursor chỉ lưu created_at là không đủ. Hãy thêm khóa duy nhất như order_id. Nếu tổ hợp vẫn không duy nhất, cần bổ sung tie-breaker cho đến khi xác định được thứ tự ổn định.

### 7.4. Bộ lọc thay đổi giữa các lần gọi

Cursor chỉ hợp lệ với cùng điều kiện lọc và cùng thứ tự sắp xếp. Nếu người dùng đổi customer_id, status, tenant hoặc sort direction, cursor cũ không còn mô tả đúng vị trí trong tập kết quả mới.

API nên gắn cursor với phiên bản truy vấn hoặc các tham số lọc cần thiết. Có thể ký hoặc mã hóa token để tránh người dùng sửa giá trị mốc và truy cập ngoài phạm vi cho phép. Token không thay thế kiểm tra quyền truy cập dữ liệu.

## 8. OFFSET và keyset giải quyết nhu cầu khác nhau

| Tiêu chí | OFFSET/LIMIT | Keyset pagination |
|---|---|---|
| Đi đến trang đầu | Đơn giản, nhanh nếu truy vấn có chỉ mục phù hợp | Đơn giản, cursor bắt đầu từ đầu |
| Đi đến trang sâu | Chi phí duyệt hàng bị bỏ qua thường tăng theo OFFSET | Seek theo giá trị mốc, thường ổn định hơn |
| Nhảy trực tiếp đến trang số N | Hỗ trợ tự nhiên | Không hỗ trợ trực tiếp nếu chưa có cursor của vị trí đó |
| Hiển thị tổng số trang | Có thể kết hợp COUNT, nhưng COUNT cũng có chi phí | Thường không cần biết tổng số trang |
| Dữ liệu thay đổi ở đầu danh sách | Có thể gây trùng hoặc bỏ sót giữa các trang | Thường ít bị dịch vị trí do insert ở đầu, nhưng vẫn chịu ảnh hưởng khi sort key thay đổi |
| API | page/size hoặc offset/limit | cursor/next token |
| Trường hợp phù hợp | Bảng nhỏ, trang nông, yêu cầu nhảy trang số cụ thể | Feed, timeline, danh sách lớn, cuộn liên tục |

OFFSET vẫn hợp lý cho các tập dữ liệu nhỏ, trang đầu hoặc giao diện cần nhảy đến trang bất kỳ. Keyset thường phù hợp hơn cho danh sách lớn mà người dùng đi tuần tự qua các trang.

Không nên thay toàn bộ phân trang bằng keyset nếu sản phẩm yêu cầu nhập số trang bất kỳ và người dùng cần biết vị trí tuyệt đối. Có thể kết hợp hai cách: OFFSET cho trang nông hoặc chức năng nhảy trang, keyset cho luồng duyệt liên tục.

## 9. Deferred join: phân trang khóa trước, lấy payload sau

Một cách giảm chi phí của OFFSET là chỉ phân trang trên chỉ mục hẹp trước, rồi mới lấy các cột rộng cho số hàng thực sự cần trả. Cách này thường được gọi là deferred join hoặc late row lookup.

Truy vấn trực tiếp:

~~~sql
SELECT order_id, created_at, total_amount, customer_note
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 200000;
~~~

Nếu index không bao phủ các cột, hệ quản trị có thể phải truy cập bảng cho nhiều hàng trong quá trình duyệt.

Viết lại để lấy khóa trước:

~~~sql
SELECT o.order_id, o.created_at, o.total_amount, o.customer_note
FROM (
    SELECT order_id, created_at
    FROM orders
    WHERE customer_id = 42
    ORDER BY created_at DESC, order_id DESC
    LIMIT 20 OFFSET 200000
) AS page
JOIN orders AS o
  ON o.order_id = page.order_id
ORDER BY page.created_at DESC, page.order_id DESC;
~~~

Truy vấn con có thể được phục vụ từ chỉ mục hẹp chứa customer_id, created_at và order_id. Sau khi xác định 20 khóa của trang, truy vấn ngoài mới lấy các cột payload cho 20 hàng. Điều này có thể giảm số lần đọc bảng, dù vẫn phải duyệt các entry chỉ mục bị OFFSET bỏ qua.

Deferred join không xóa chi phí OFFSET sâu. Nó giảm công việc truy cập hàng rộng hoặc truy cập bảng không cần thiết cho những hàng bị bỏ qua. Cần kiểm tra optimizer có giữ được chiến lược này hay biến đổi truy vấn theo cách khác.

## 10. COUNT tổng số hàng và chi phí đi kèm

Giao diện phân trang thường hiển thị “trang 1 trên 12.345” và cần tổng số hàng:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE customer_id = 42;
~~~

COUNT có thể phải đọc toàn bộ phạm vi phù hợp để đếm chính xác, ngay cả khi trang hiện tại chỉ trả 20 hàng. Với bảng lớn, COUNT chính xác có thể tốn thời gian và I/O riêng biệt với truy vấn lấy trang.

Các lựa chọn:

- Chỉ hiển thị nút “Tiếp theo” nếu còn dữ liệu, bằng cách lấy page_size + 1 hàng.
- Đếm tổng ở thời điểm khác hoặc cache kết quả nếu độ mới phù hợp.
- Dùng số lượng gần đúng nếu sản phẩm chấp nhận và có nguồn thống kê phù hợp.
- Lưu counter theo nghiệp vụ nếu có thể cập nhật nhất quán và kiểm soát chi phí ghi.
- Chỉ thực hiện COUNT khi người dùng thực sự cần tổng số trang.

Không dùng COUNT ước lượng để hiển thị như con số chính xác. Nếu kết quả có thể cũ, giao diện cần biểu đạt đúng tính chất của số liệu.

### Kỹ thuật lấy thêm một hàng

Với keyset hoặc OFFSET, truy vấn có thể lấy page_size + 1:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
~~~

Nếu nhận được 21 hàng, có thể hiển thị 20 hàng đầu và dùng hàng thứ 21 để xác định còn trang tiếp theo. Không cần đếm toàn bộ bảng chỉ để biết có thể tiếp tục hay không.

## 11. Nhất quán dữ liệu giữa các trang

Phân trang nhiều lần gọi là nhiều truy vấn riêng. Nếu dữ liệu thay đổi giữa các lần gọi, tập kết quả có thể thay đổi.

### Với OFFSET

Giả sử trang đầu lấy hàng 1 đến 20. Trước khi người dùng lấy trang hai, một hàng mới được chèn lên đầu danh sách. Khi OFFSET 20, một hàng đã thấy có thể bị đẩy sang vị trí 21 và xuất hiện lại. Ngược lại, nếu một hàng bị xóa ở phía trước, một hàng chưa thấy có thể dịch lên và bị bỏ qua.

### Với keyset

Cursor đánh dấu khóa cuối cùng đã đọc. Hàng mới được thêm trước mốc thường không làm dịch chuyển vị trí tiếp theo, nhưng hàng mới có khóa nằm sau mốc có thể xuất hiện ở trang kế. Nếu khóa sort được cập nhật, hàng có thể đi qua mốc.

### Snapshot và mốc dữ liệu

Nếu yêu cầu nghiệp vụ cần duyệt một tập dữ liệu nhất quán, có thể cân nhắc:

- Snapshot isolation hoặc repeatable read trong một transaction được giữ xuyên suốt, nếu hệ quản trị hỗ trợ và thời gian transaction phù hợp.
- Một mốc thời gian hoặc sequence cố định, ví dụ chỉ lấy dữ liệu có created_at <= snapshot_time.
- Cursor chứa watermark hoặc phiên bản dữ liệu để giới hạn tập kết quả.
- Cơ chế export/snapshot riêng cho tác vụ cần duyệt toàn bộ dữ liệu.

Giữ transaction mở qua nhiều yêu cầu HTTP thường không phù hợp vì giữ connection, snapshot và tài nguyên lâu. Hãy đánh giá yêu cầu nhất quán thực sự và chọn cơ chế có chi phí vận hành phù hợp.

## 12. Phân trang trong API

Một API có thể hỗ trợ hai dạng:

**Offset-based:**

~~~http
GET /orders?customerId=42&page=5&size=20
~~~

Máy chủ chuyển page/size thành OFFSET và LIMIT. Cần xác thực page, size, giới hạn size tối đa và kiểm tra overflow khi tính offset.

**Cursor-based:**

~~~http
GET /orders?customerId=42&limit=20&after=eyJjcmVhdGVkQXQiOi...
~~~

Cursor chứa mốc cuối trang, ví dụ created_at và order_id, cùng thông tin cần thiết để ràng buộc bộ lọc/thứ tự. Token nên được mã hóa hoặc ký nếu client không được phép thay đổi nội dung. Máy chủ vẫn phải kiểm tra quyền, tenant và các điều kiện lọc trong mỗi request.

Một cursor hợp lệ cần:

- Gắn với đúng thứ tự sắp xếp và chiều ASC/DESC.
- Chứa đủ các cột tie-breaker để tạo thứ tự duy nhất.
- Có kiểu dữ liệu và độ chính xác giống dữ liệu trong DB.
- Gắn với bộ lọc liên quan hoặc từ chối khi bộ lọc thay đổi.
- Có phiên bản để hỗ trợ thay đổi cấu trúc token.
- Không chứa dữ liệu nhạy cảm không cần thiết.
- Có thể hết hạn nếu nghiệp vụ yêu cầu.

Đừng dựa vào vị trí hàng trong kết quả hoặc số trang để tạo cursor. Cursor phải đại diện cho khóa sắp xếp thực tế.

## 13. Khác biệt cú pháp giữa các hệ quản trị

Các hệ quản trị hỗ trợ cú pháp phân trang khác nhau:

| Hệ quản trị | OFFSET/LIMIT hoặc tương đương | Ghi chú |
|---|---|---|
| PostgreSQL | LIMIT ... OFFSET ... hoặc FETCH FIRST ... OFFSET ... | EXPLAIN (ANALYZE, BUFFERS) giúp xem số hàng và I/O |
| MySQL | LIMIT row_count OFFSET offset | Có thể dùng LIMIT offset, row_count; đọc kế hoạch bằng EXPLAIN/EXPLAIN ANALYZE tùy phiên bản |
| SQL Server | ORDER BY ... OFFSET ... ROWS FETCH NEXT ... ROWS ONLY | ORDER BY là bắt buộc cho cú pháp OFFSET/FETCH; xem Actual Execution Plan và logical reads |
| Oracle | OFFSET ... ROWS FETCH NEXT ... ROWS ONLY hoặc các cách phân trang tương thích phiên bản | Xem execution plan, row source statistics và workarea nếu có |

Ví dụ SQL Server:

~~~sql
SELECT order_id, created_at, total_amount
FROM dbo.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
OFFSET 200000 ROWS
FETCH NEXT 20 ROWS ONLY;
~~~

Ví dụ Oracle:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
OFFSET 200000 ROWS
FETCH NEXT 20 ROWS ONLY;
~~~

Cú pháp không quyết định hiệu năng. Kế hoạch phụ thuộc chỉ mục, thống kê, tham số, phân phối dữ liệu và phiên bản. Không giả định một DBMS sẽ thực hiện OFFSET bằng cách nhảy trực tiếp đến số thứ tự hàng.

## 14. Benchmark OFFSET và keyset

Muốn biết phương án nào phù hợp, hãy so sánh trên cùng dữ liệu và điều kiện tải.

### Kịch bản đo

Chọn truy vấn có điều kiện lọc và thứ tự thực tế. Đo ở nhiều độ sâu:

- Trang đầu: OFFSET 0.
- Trang nông: OFFSET 1.000.
- Trang trung bình: OFFSET 50.000.
- Trang sâu: OFFSET 500.000 hoặc mức tương đương với dữ liệu thực.

Với keyset, tạo cursor ở các vị trí tương ứng rồi chạy truy vấn sau mốc. Đảm bảo cursor đúng với dữ liệu và thứ tự.

### Chỉ số cần ghi

| Nhóm | Chỉ số |
|---|---|
| Độ trễ | p50, p95, p99, thời gian trung bình |
| Throughput | Số request/phút hoặc truy vấn/giây |
| I/O | Logical reads, buffer hits/reads, physical reads, temp reads/writes |
| CPU | CPU time và tổng thời gian xử lý |
| Kế hoạch | Scan type, sort, join, actual rows, loops |
| Bộ nhớ | Sort/hash memory, spill và memory grant nếu có |
| Chất lượng kết quả | Số hàng, thứ tự, duplicate và missing rows |

Chạy nhiều lần để quan sát độ biến thiên, tách trường hợp cache nóng/lạnh nếu mục tiêu đo yêu cầu, và tránh để truy vấn benchmark cạnh tranh không kiểm soát với workload khác. Không chỉ đo một lần rồi kết luận.

### Ví dụ so sánh

Giả sử cùng điều kiện customer_id = 42, page size 20:

| Phương án | Công việc dự kiến |
|---|---|
| OFFSET 0 | Duyệt đến 20 hàng |
| OFFSET 100.000 | Có thể duyệt khoảng 100.020 entry/hàng trước khi trả kết quả |
| OFFSET 1.000.000 | Có thể duyệt khoảng 1.000.020 entry/hàng |
| Keyset từ cursor | Seek đến mốc rồi đọc gần 20 hàng kế tiếp nếu index và predicate phù hợp |
| Deferred join + OFFSET | Vẫn duyệt entry bị bỏ qua nhưng có thể chỉ đọc payload cho 20 hàng cuối |

Đây là mô hình công việc để giải thích. Kế hoạch thật có thể đọc nhiều hơn do filter, join, sort, visibility check hoặc truy cập bảng.

## 15. Những sai lầm thường gặp

- **Cho rằng LIMIT 20 nghĩa là chỉ đọc 20 hàng.** OFFSET, sort, filter và join có thể buộc hệ quản trị xử lý rất nhiều hàng trước đó.
- **Thêm chỉ mục rồi cho rằng OFFSET sâu đã được giải quyết.** Chỉ mục có thể loại sort nhưng vẫn phải duyệt các entry bị bỏ qua.
- **ORDER BY trên cột không duy nhất.** Các hàng đồng hạng có thể đổi vị trí giữa các lần chạy.
- **Dùng keyset chỉ với một cột không duy nhất.** Cursor có thể bỏ sót hoặc lặp hàng có cùng giá trị.
- **Dùng tuple comparison khi có NULL mà không xử lý.** So sánh có thể cho UNKNOWN và bỏ qua hàng.
- **Viết lại OFFSET thành keyset nhưng đổi ngữ nghĩa sort.** Cần giữ chiều sắp xếp, tie-breaker và điều kiện lọc.
- **Cho rằng keyset tạo snapshot.** Dữ liệu mới hoặc sort key bị cập nhật vẫn có thể làm thay đổi tập kết quả.
- **Tính tổng số trang bằng COUNT ở mọi request.** COUNT chính xác có thể là một truy vấn tốn kém riêng.
- **Đưa mọi cột vào covering index.** Chỉ mục lớn làm tăng dung lượng và chi phí ghi.
- **Benchmark chỉ ở trang đầu.** Không phát hiện được chi phí tăng theo OFFSET.

## 16. Quy trình chọn và triển khai chiến lược phân trang

1. **Xác định hành vi giao diện.** Người dùng cần nhảy đến số trang bất kỳ, hay chỉ cần đi tiếp/lùi trong danh sách?
2. **Đo kích thước dữ liệu và độ sâu truy cập.** Xác định số hàng phù hợp, page size, tần suất trang sâu và mục tiêu p95/p99.
3. **Kiểm tra ORDER BY.** Bổ sung tie-breaker duy nhất và xác định quy tắc NULL.
4. **Đọc execution plan.** Tìm scan, sort, filter, join, buffers, temp I/O và số hàng phải duyệt.
5. **Đánh giá chỉ mục.** Xem điều kiện lọc, thứ tự cột, hướng sort và cột cần trả về.
6. **Chọn phương án.** OFFSET cho trang nông/nhảy trang; keyset cho duyệt tuần tự; deferred join khi payload lookup là chi phí lớn; cursor hoặc snapshot cho yêu cầu nhất quán phù hợp.
7. **Bảo toàn ngữ nghĩa.** Kiểm tra NULL, duplicate, sort direction, múi giờ, tham số và thay đổi dữ liệu đồng thời.
8. **Benchmark nhiều độ sâu.** So sánh p95/p99, CPU, I/O, temp, số hàng đọc và kết quả.
9. **Triển khai có theo dõi.** Quan sát độ trễ theo page depth, tỷ lệ request lỗi cursor, tải database và tác động đến thao tác ghi.
10. **Điều chỉnh API.** Giới hạn page size, kiểm tra offset, gắn cursor với filter/sort và cung cấp hành vi khi cursor hết hạn hoặc không còn hợp lệ.

## 17. Checklist kiểm chứng

- [ ] Truy vấn có ORDER BY xác định và tie-breaker duy nhất.
- [ ] Đã đo trang đầu, trang nông và trang sâu.
- [ ] Đã kiểm tra số hàng scan/actual rows thay vì chỉ nhìn LIMIT.
- [ ] Đã xác định có Sort hoặc spill ra vùng lưu trữ tạm không.
- [ ] Đã kiểm tra chỉ mục có hỗ trợ cả điều kiện lọc và thứ tự sắp xếp không.
- [ ] Đã xem xét độ rộng hàng và khả năng dùng deferred join/covering index.
- [ ] Nếu dùng keyset, cursor chứa đủ khóa và đúng chiều sắp xếp.
- [ ] Đã xử lý NULL và các cột sort không duy nhất.
- [ ] Đã xác định yêu cầu nhất quán khi dữ liệu thay đổi giữa các trang.
- [ ] Đã đánh giá chi phí COUNT và cách thông báo còn trang tiếp theo.
- [ ] Đã benchmark dưới tải đại diện và so sánh p95/p99, CPU, I/O, memory.
- [ ] Đã kiểm tra chi phí ghi và dung lượng của chỉ mục mới.
- [ ] Đã kiểm tra API giới hạn page size, offset và xác thực cursor.

OFFSET/LIMIT thuận tiện cho trang nông và giao diện cần nhảy đến số trang, nhưng chi phí thường tăng khi phải bỏ qua nhiều hàng. Chỉ mục có thể loại bỏ sort và giảm truy cập bảng nhưng không xóa số entry phải duyệt. Với danh sách lớn được duyệt tuần tự, keyset pagination thường hiệu quả hơn vì tìm từ khóa cuối trang trước; deferred join có thể giảm việc lấy payload cho các hàng bị bỏ qua. Hãy lựa chọn theo hành vi sản phẩm, giữ thứ tự ổn định và đo trên execution plan cùng workload thực tế để bảo đảm cải thiện hiệu năng mà không thay đổi kết quả nghiệp vụ.

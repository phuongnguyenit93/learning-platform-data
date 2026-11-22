# Chọn phương án theo mẫu truy cập và bằng chứng đo lường

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Mô tả **mẫu truy cập dữ liệu (access pattern)** của một chức năng bằng thao tác, bộ lọc, sắp xếp, tần suất, tập kết quả, độ tươi và mục tiêu độ trễ.
- Nhận diện khác biệt giữa vấn đề do mô hình dữ liệu và vấn đề do truy vấn, chỉ mục, phân trang hoặc cách ứng dụng gọi cơ sở dữ liệu.
- Đặt giả thuyết đo được để lựa chọn giữa mô hình quan hệ đã chuẩn hóa, chỉ mục, cache, materialized view, bảng tổng hợp và phi chuẩn hóa.
- Đọc các chỉ dấu quan trọng từ kế hoạch truy vấn và thiết kế phép thử với tải đọc/ghi đại diện.
- Quyết định giữ, áp dụng hoặc loại bỏ một bản sao dữ liệu dựa trên lợi ích toàn hệ thống cùng yêu cầu nhất quán và khả năng đối soát.

Trong **DATABASE_DATA_MODELING**, thiết kế lược đồ không dừng ở việc liệt kê thực thể, quan hệ và ràng buộc. Chất lượng mô hình còn thể hiện ở việc cấu trúc ấy có phục vụ đúng cách hệ thống thực sự đọc và ghi dữ liệu, có thể kiểm chứng bằng phép đo, và có thể tiến hóa khi nghiệp vụ thay đổi hay không.

## 1. Vì sao cùng một mô hình có thể tốt ở nơi này, kém ở nơi khác?

Hai hệ thống bán hàng có thể có cùng các thực thể **Customer – Order – OrderItem – Product**, nhưng mẫu truy cập hoàn toàn khác nhau:

- **Hệ thống A:** Khách thường xem danh sách 20–50 đơn gần nhất của chính mình; đơn được tạo và chỉnh sửa liên tục; tổng tiền phải đúng ngay sau khi lưu.
- **Hệ thống B:** Nhân viên phân tích thường xuyên xem số đơn và doanh thu tổng hợp theo ngày của vài năm; số liệu chậm 5 phút có thể chấp nhận; dữ liệu nguồn được ghi liên tục.
- **Hệ thống C:** Trang tìm kiếm sản phẩm đọc nhiều triệu lần, kết hợp mô tả, giá, danh mục và xếp hạng; dữ liệu tìm kiếm có thể chậm vài giây, nhưng giá khi thanh toán phải được xác nhận lại từ nguồn nghiệp vụ.

Không có một quy tắc “mọi JOIN đều chậm” hay “cứ lưu sẵn giá trị là nhanh hơn tổng thể” phù hợp cho cả ba.

**Phi chuẩn hóa (denormalization)** có thể giảm chi phí đọc bằng cách lưu bản sao, tổng hợp hoặc mô hình đọc. Đổi lại, hệ thống phải trả thêm chi phí ghi, lưu trữ, đồng bộ, thay đổi lược đồ và khôi phục. Quyết định đúng phải bắt đầu từ **những truy cập cụ thể** và **số liệu đo trên tải đại diện**.

Một mô hình quan hệ đã chuẩn hóa vẫn là điểm xuất phát hữu ích khi các phụ thuộc nghiệp vụ và khóa ngoại rõ ràng. Ta chỉ nên thêm cấu trúc phục vụ đọc khi đã biết truy vấn nào cần được hỗ trợ, mức cải thiện cần đạt và tính đúng đắn cần bảo toàn.

## 2. Mẫu truy cập cần mô tả những gì?

Một access pattern là đặc tả cách một người dùng, API, job hoặc hệ thống ngoài thao tác với dữ liệu. Thay vì viết “hay lấy thông tin đơn hàng”, hãy mô tả đủ để tạo truy vấn và phép đo.

| Trường mô tả | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Hành động | Đọc chi tiết, tìm kiếm, tổng hợp, thêm/sửa/xóa hay xử lý sự kiện? | Liệt kê đơn gần nhất của một khách |
| Bộ lọc | Lọc theo khóa, trạng thái, thời gian, khoảng giá, vị trí...? | customer_id, created_at |
| Sắp xếp/phân trang | Có ORDER BY, LIMIT, cursor hoặc OFFSET không? | Mới nhất trước, 50 đơn/trang |
| Trường cần lấy | Cần cả thực thể hay chỉ vài thuộc tính? | order_id, created_at, tổng dòng hàng |
| Quan hệ/cardinality | Một bản ghi liên kết bao nhiêu bản ghi khác? | Trung bình 4 dòng/đơn; có đơn hàng trăm dòng |
| Tần suất/tải | Bao nhiêu lần/giây, khi cao điểm thế nào? | 400 yêu cầu/phút; đỉnh gấp 5 |
| Đường ghi liên quan | Có bao nhiêu lần tạo, sửa, hủy dữ liệu nguồn? | Thêm dòng hàng, sửa số lượng, hủy dòng |
| Tính nhất quán | Có được đọc giá trị cũ không? Chậm tối đa bao lâu? | Tổng đơn đúng ngay sau khi sửa |
| SLO | Độ trễ/throughput/tỷ lệ lỗi cần đạt? | p95 của API không quá 180 ms |
| Quy mô và tăng trưởng | Bao nhiêu hàng, tăng bao nhiêu/ngày, có khách quá lớn không? | 8 triệu đơn, 35 triệu dòng hàng |

**Cardinality** là số phần tử tương ứng trong quan hệ: mỗi đơn có bao nhiêu dòng; mỗi danh mục có bao nhiêu sản phẩm. **Selectivity** thể hiện mức độ thu hẹp dữ liệu của điều kiện lọc. Hai đặc tính này ảnh hưởng trực tiếp đến kiểu JOIN, số dòng phải quét và tính hữu ích của chỉ mục.

Đối với dữ liệu phân tích, cần ghi thêm **hạt dữ liệu (grain)** của kết quả: một dòng cho mỗi đơn, mỗi khách/ngày hay mỗi sản phẩm/tháng. Với document database, ghi thêm kích thước document và số document phải cập nhật khi một giá trị hiện hành đổi. Với đồ thị, ghi thêm số bước duyệt, phân bố bậc của đỉnh và giới hạn độ sâu.

### 2.1. Tập hợp truy vấn quan trọng, không chỉ “truy vấn chậm nhất”

Một truy vấn chạy 2 giây mỗi tháng và một truy vấn chạy 80 ms hàng nghìn lần/phút gây tác động hệ thống rất khác nhau. Cần xác định:

1. Truy vấn có độ trễ vượt mục tiêu của luồng nghiệp vụ.
2. Truy vấn tiêu tốn nhiều tài nguyên cộng dồn vì được gọi rất thường xuyên.
3. Truy vấn tạo đỉnh tải, khóa chờ hoặc nghẽn I/O.
4. Đường ghi có thể chịu tác động khi thêm bản sao hoặc chỉ mục.

Một cách ưu tiên sơ bộ là xem **số lần gọi × thời gian thực thi trung bình** cho từng nhóm truy vấn trong một khoảng đo giống nhau. Chỉ số này ước lượng tổng thời gian thực thi truy vấn ghi nhận được; **không tương đương mức dùng CPU thực tế**, và không được lấy số p95 nhân với số lượt gọi để suy ra thời gian trung bình. Phải đối chiếu với CPU, I/O và mức chờ.

### 2.2. Đừng để giá trị trung bình che giấu trường hợp xấu

Ví dụ, phần lớn khách có 2–5 đơn mỗi tháng, nhưng một số tài khoản doanh nghiệp có hàng trăm nghìn đơn. Truy vấn nhanh với khách phổ biến có thể rất chậm với nhóm ít gặp này.

Khi chọn dữ liệu thử nghiệm, cần có:

- Khách ít và nhiều dữ liệu; đơn ít và nhiều dòng hàng.
- Thời gian gần đây và dữ liệu lịch sử, dữ liệu phân bố lệch.
- Truy vấn có cache nóng và cache lạnh.
- Mức đồng thời thấp, cao, và tình huống đọc/ghi cùng lúc.
- Dữ liệu đã tăng đến quy mô dự kiến, không chỉ database thử nghiệm vài nghìn hàng.

Nếu chỉ đo một truy vấn mẫu trên máy cá nhân, kết luận về phi chuẩn hóa rất dễ sai.

## 3. Chẩn đoán vấn đề trước khi thay lược đồ

Quy trình nên bắt đầu bằng câu hỏi: **Thời gian đang mất ở đâu?** Phần chậm có thể nằm ở ứng dụng, mạng, truy vấn SQL, khóa, chỉ mục, việc trả quá nhiều dòng hoặc cách dựng giao diện.

### 3.1. Thu thập dữ liệu đường đi của yêu cầu

Ở cấp ứng dụng, ghi thời gian toàn API và thời gian chờ cơ sở dữ liệu; xem số lượt truy vấn mỗi request. Mẫu **N+1 query** thường xuất hiện khi ứng dụng lấy 50 đơn rồi gọi thêm 50 truy vấn để lấy dòng hàng. Nên thử gộp truy vấn hoặc đọc theo lô trước khi thêm cột lặp.

Ở cấp cơ sở dữ liệu, công cụ phụ thuộc hệ quản trị: PostgreSQL có thể dùng thống kê truy vấn (ví dụ **pg_stat_statements** khi được cấu hình), slow query log, truy vết APM và kế hoạch truy vấn. Thông số cần theo dõi gồm thời gian thực thi, số lần gọi, số dòng, số block đọc, áp lực CPU/I/O và chờ khóa.

Đặt số liệu vào cùng một cửa sổ thời gian. Thông lượng cao điểm, cấu hình máy, phiên bản lược đồ và tập dữ liệu phải được ghi lại; nếu không, hai lần đo có thể không so sánh được.

### 3.2. Đọc kế hoạch truy vấn theo giả thuyết

Ví dụ PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE customer_id = 501
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Một số dấu hiệu đáng xem:

| Chỉ dấu trong kế hoạch | Gợi ý điều tra |
| --- | --- |
| **actual rows** khác xa **estimated rows** | Thống kê đã cũ, phân bố lệch, điều kiện tương quan; xem ANALYZE và cách đặt tham số |
| **Seq Scan** trên bảng lớn với điều kiện chọn lọc mạnh | Cân nhắc chỉ mục phù hợp; nhưng Seq Scan có thể đúng nếu đọc phần lớn bảng |
| **Sort** xử lý nhiều dòng trước LIMIT | Xem chỉ mục theo bộ lọc + thứ tự; giảm tập ứng viên sớm |
| **Nested Loop** lặp nhiều lần trên tập lớn | Kiểm tra ước lượng dòng và chỉ mục phía trong, không mặc định Nested Loop là xấu |
| **HashAggregate/GroupAggregate** trên số dòng lớn | Cân nhắc lọc sớm, tổng hợp đúng tập, hoặc bảng tổng hợp khi có bằng chứng |
| **Buffers: shared hit/read** | Phân biệt truy cập cache của PostgreSQL và đọc block; xem khối lượng I/O |
| **Actual time**, thời gian lập kế hoạch và thực thi | Kiểm tra phần thực sự gây tốn thời gian, tránh tối ưu nhầm |

**EXPLAIN (ANALYZE)** thực sự chạy câu lệnh; với SELECT như ví dụ là phù hợp để quan sát, nhưng nếu dùng trên câu lệnh thay đổi dữ liệu thì có thể tạo thay đổi thật. Đo trên môi trường và mức tải an toàn, vì thu thập số liệu thực thi có thể tạo thêm chi phí. “Cost” trong EXPLAIN là chi phí ước lượng tương đối của bộ tối ưu, không phải số mili giây.

## 4. Ví dụ xuyên suốt: trang danh sách đơn hàng

Giả sử lược đồ đã chuẩn hóa có:

- **orders(order_id, customer_id, created_at, status)**.
- **order_items(order_item_id, order_id, quantity, unit_price_at_purchase)**.

Yêu cầu: khi khách mở trang lịch sử, trả về **50 đơn gần nhất** và tổng giá trị dòng hàng trên từng đơn. Trong ví dụ này, tổng chỉ là **SUM(quantity × unit_price_at_purchase)**, chưa bao gồm thuế, vận chuyển, giảm giá hoặc hoàn tiền. Trước khi dùng cho tài chính thực, phải định nghĩa lại đầy đủ.

### 4.1. Phương án ban đầu: đọc có giới hạn, rồi mới tổng hợp

~~~sql
WITH recent_orders AS (
    SELECT
        o.order_id,
        o.created_at
    FROM orders AS o
    WHERE o.customer_id = $1
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 50
)
SELECT
    ro.order_id,
    ro.created_at,
    COALESCE(
        SUM(oi.quantity * oi.unit_price_at_purchase),
        0
    ) AS items_subtotal
FROM recent_orders AS ro
LEFT JOIN order_items AS oi
    ON oi.order_id = ro.order_id
GROUP BY ro.order_id, ro.created_at
ORDER BY ro.created_at DESC, ro.order_id DESC;
~~~

Điểm cần quan sát: truy vấn **chọn trước 50 đơn**, rồi mới cộng dòng hàng tương ứng. Điều này tránh tính tổng của mọi đơn trong lịch sử khách khi chỉ cần 50 đơn. Thứ tự sắp xếp có thêm **order_id** để ổn định khi hai đơn cùng **created_at**.

Các chỉ mục ứng viên:

~~~sql
CREATE INDEX idx_orders_customer_created_id
    ON orders (customer_id, created_at DESC, order_id DESC);

CREATE INDEX idx_order_items_order_id
    ON order_items (order_id);
~~~

Đây là ứng viên để **đo thử**; không có nghĩa bắt buộc tạo nếu đã có chỉ mục tương đương. Cần kiểm tra độ chọn lọc, kích thước chỉ mục, tốc độ ghi và kế hoạch thực tế. Nếu API phân trang sâu, có thể thử **keyset pagination** dựa trên bộ **(created_at, order_id)** thay vì OFFSET lớn.

### 4.2. Phương án thay thế: lưu tổng trên orders

Khi truy vấn sau tối ưu vẫn chậm, nhóm có thể xem xét **orders.items_subtotal**:

~~~sql
ALTER TABLE orders
ADD COLUMN items_subtotal NUMERIC(14, 2);
~~~

Trường này là **giá trị dẫn xuất**. Nó chỉ hữu ích nếu thiết kế kèm hợp đồng:

> Với mỗi đơn, **items_subtotal** bằng tổng số lượng nhân đơn giá của những dòng hàng hợp lệ, tính tại thời điểm đã thống nhất; những thay đổi dòng hàng phải được phản ánh theo cơ chế nhất quán đã chọn.

Nếu yêu cầu đúng ngay sau mỗi lần sửa và dữ liệu ở cùng PostgreSQL, cơ chế cập nhật trong cùng giao dịch có thể thích hợp. Tuy nhiên, còn phải xử lý sửa/xóa dòng, hủy, thử lại yêu cầu, tương tranh và backfill. Chỉ thêm cột và copy tổng một lần là chưa đủ.

Với giá trị lưu sẵn, truy vấn chỉ còn đọc 50 hàng **orders**, nhưng mỗi thay đổi liên quan đến dòng hàng có thêm công việc trên **orders**; việc nhiều giao dịch cập nhật chung một đơn có thể gây tranh chấp khóa.

### 4.3. So sánh bằng số liệu giả định

**Bảng sau hoàn toàn là số liệu minh họa**, để diễn giải cách quyết định; không phải benchmark đo trên hệ thống thật.

| Chỉ tiêu tại cùng một bộ tải | Truy vấn gốc | Lọc sớm + chỉ mục | Lưu items_subtotal |
| --- | ---: | ---: | ---: |
| API danh sách đơn, p95 | 340 ms | 125 ms | 96 ms |
| SLO của API danh sách | ≤ 180 ms | ≤ 180 ms | ≤ 180 ms |
| Ghi/sửa dòng hàng, p95 | 105 ms | 112 ms | 158 ms |
| Dung lượng dữ liệu/index bổ sung | 0 (mốc so sánh) | Tăng do chỉ mục | Tăng do cột + cơ chế hỗ trợ |
| Công việc đảm bảo nhất quán | Truy vấn tính lại | Truy vấn tính lại | Cập nhật đồng bộ, đối soát, backfill |
| Nguy cơ mới | Tải tổng hợp khi đọc | Chi phí duy trì chỉ mục | Khóa ghi, dữ liệu dẫn xuất sai nếu bỏ sót |

Trong giả định này, **phương án “lọc sớm + chỉ mục” đã đạt SLO đọc**. Phương án lưu tổng cải thiện thêm 29 ms ở p95 đọc nhưng làm đường ghi chậm hơn rõ rệt và tăng gánh nặng vận hành. Nếu không có yêu cầu đọc nghiêm ngặt hơn, nên **giữ mô hình chuẩn hóa đã tối ưu**, tiếp tục theo dõi tải thật rồi mới cân nhắc lưu tổng.

Lưu ý: p95 là phân vị, **không thể cộng hoặc trừ p95 của các bước để suy ra p95 toàn luồng**. Bảng thể hiện p95 được đo riêng cho từng loại hoạt động dưới cùng kịch bản tải.

## 5. Trường hợp khác: dashboard tổng hợp theo ngày

Giả sử bộ phận phân tích yêu cầu số đơn đang ở trạng thái **PAID** và tổng số tiền thu tương ứng theo ngày. Dashboard có nhiều lượt truy cập, tra cứu lịch sử dài, và người dùng chấp nhận dữ liệu có độ trễ tối đa **10 phút**.

Về mặt nghiệp vụ, giả sử:

- **orders.paid_at** là thời điểm ghi nhận thanh toán, không rỗng với đơn PAID.
- **orders.charged_amount** là khoản tiền đã được ghi nhận cho đơn, có quy tắc quản lý riêng.
- Báo cáo đếm **những đơn hiện đang có status = 'PAID' tại thời điểm làm mới**.
- Ngày báo cáo được xác định theo **UTC**. Nếu nghiệp vụ dùng múi giờ khác, phải thay định nghĩa và xử lý ranh giới ngày phù hợp.

Một truy vấn tổng hợp trực tiếp lên bảng lớn có thể tốn thời gian, nhất là khi người dùng nhiều lần yêu cầu cùng tập số liệu. Sau khi thử tối ưu bộ lọc, có thể dùng **materialized view**.

~~~sql
CREATE MATERIALIZED VIEW daily_paid_order_summary AS
SELECT
    (paid_at AT TIME ZONE 'UTC')::date AS day_utc,
    COUNT(*) AS order_count,
    SUM(charged_amount) AS charged_total
FROM orders
WHERE status = 'PAID'
  AND paid_at IS NOT NULL
GROUP BY (paid_at AT TIME ZONE 'UTC')::date
WITH NO DATA;

-- Lần đầu nạp dữ liệu:
REFRESH MATERIALIZED VIEW daily_paid_order_summary;

CREATE UNIQUE INDEX ux_daily_paid_order_summary_day
    ON daily_paid_order_summary (day_utc);

-- Những lần làm mới tiếp theo, nếu đủ điều kiện PostgreSQL:
REFRESH MATERIALIZED VIEW CONCURRENTLY daily_paid_order_summary;
~~~

**Lưu ý:** các câu lệnh trên minh họa thứ tự tạo và làm mới. **CONCURRENTLY** yêu cầu materialized view đã có dữ liệu và có unique index phù hợp; khi vận hành phải kiểm soát lịch chạy, tác vụ trùng nhau, thời gian hoàn tất và tài nguyên. PostgreSQL materialized view làm mới theo cơ chế REFRESH, không mặc nhiên cập nhật tăng dần mỗi khi hàng nguồn đổi. Với dữ liệu rất lớn, một lần refresh toàn bộ có thể quá đắt; cần cân nhắc bảng tổng hợp cập nhật tăng dần hoặc nền tảng phân tích chuyên dụng.

Giả sử phép đo đại diện cho thấy truy vấn tổng hợp trực tiếp có **p95 = 2,1 giây**, còn đọc từ view có **p95 = 80 ms**; việc làm mới kết thúc trong thời gian phù hợp, và độ trễ dữ liệu lớn nhất quan sát được trong kỳ thử là **6 phút**. Khi mục tiêu dashboard là **p95 ≤ 300 ms** và dữ liệu không cũ quá **10 phút**, materialized view là ứng viên hợp lý.

Để kết luận chắc chắn, vẫn cần kiểm tra thời điểm đỉnh tải, sự kiện thanh toán đến muộn, đổi trạng thái, khả năng tính lại và độ trễ khi job thất bại. Nếu hệ thống yêu cầu số tiền thanh toán tức thời để xác nhận giao dịch, cùng một materialized view có thể **không đủ độ tươi**.

## 6. Bản đồ lựa chọn theo mẫu truy cập

Không nên bắt đầu bằng tên kỹ thuật. Hãy bắt đầu bằng **hình dạng truy vấn**, **độ tươi** và **mức độ thay đổi nguồn**.

| Mẫu truy cập nổi bật | Phương án nên thử trước | Khi nào cân nhắc phương án bổ sung |
| --- | --- | --- |
| Tra cứu theo khóa chính/khóa ngoại, trả ít hàng | Mô hình chuẩn hóa, PK/FK, JOIN có chỉ mục | Khi nhiều dịch vụ/nguồn làm JOIN đắt và đã có bằng chứng |
| Lọc + sắp xếp + LIMIT trên tập lớn | Chỉ mục phối hợp, keyset pagination, giảm trường trả về | Khi kết quả được truy cập lặp nhiều và đáp ứng độ tươi cụ thể |
| N+1 query ở tầng ứng dụng | Gộp truy vấn, batch fetch, xử lý dữ liệu theo tập | Nếu gộp vẫn không đạt mục tiêu, đánh giá read model |
| Tổng hợp SUM/COUNT trên lịch sử lớn | Lọc sớm, chỉ mục, chiến lược phân vùng nếu phù hợp | Materialized view, bảng tổng hợp tăng dần, OLAP |
| Nội dung phổ biến đọc nhiều, thay đổi ít | Cache theo khóa và TTL/invalidation | Snapshot/materialized view nếu cần truy vấn tổng hợp ổn định |
| Danh sách/tìm kiếm nhiều tiêu chí, full-text | Chỉ mục chuyên dụng, search engine khi cần | Read model được đồng bộ qua sự kiện, có hợp đồng độ trễ |
| Chi tiết một aggregate thường đọc/ghi cùng nhau | Mô hình quan hệ hoặc document theo ranh giới giao dịch | Nhúng snapshot hay dữ liệu dẫn xuất khi ngữ nghĩa rõ |
| Truy vấn nhiều bước quan hệ, thay đổi đường đi | Chỉ mục quan hệ phù hợp, thử truy vấn recursive | Mô hình graph khi traversal là tác vụ chủ đạo và được chứng minh |
| Báo cáo đa chiều, quét lịch sử nhiều năm | Schema phân tích theo grain, mô hình fact/dimension | Pre-aggregation, materialized view, engine cột |
| Bộ đếm cập nhật rất thường xuyên trên cùng một hàng | Xem lại yêu cầu nhất quán và cách tính | Sharded counters/aggregation bất đồng bộ nếu nghiệp vụ cho phép |

Bảng là **thứ tự khảo sát**, không phải luật tuyệt đối. Chẳng hạn cache có thể tốt cho trang sản phẩm, nhưng giá và tồn kho tại thời điểm thanh toán phải được kiểm tra lại bằng nguồn đúng theo ràng buộc nghiệp vụ.

### 6.1. Khi nào nên nhân bản dữ liệu trong document?

Nếu document chứa toàn bộ một đơn hàng cùng các dòng và snapshot giá tại thời điểm đặt, ứng dụng có thể đọc bằng một thao tác. Lợi ích phụ thuộc kích thước document, ranh giới cập nhật nguyên tử và mức phát triển của danh sách con.

Ngược lại, nếu sao chép **tên người bán hiện hành** vào hàng triệu document sản phẩm, một lần đổi tên có thể gây lượng ghi rất lớn. Cần đo **fan-out cập nhật**: mỗi thay đổi nguồn tạo bao nhiêu bản ghi cần đồng bộ; thời gian cập nhật lâu nhất là bao nhiêu; có được đọc tên cũ hay không.

### 6.2. Khi nào mô hình đồ thị đáng cân nhắc?

Truy vấn “gợi ý người quen trong tối đa ba bước” hoặc đường đi qua quan hệ phụ thuộc có thể phù hợp với graph. Cần đo số đỉnh/cạnh duyệt, giới hạn độ sâu và các đỉnh bậc cao. Việc lưu sẵn số đường đi hoặc đặc trưng tổng hợp trên đỉnh có thể tăng tốc đọc, nhưng cập nhật cạnh làm nhiều giá trị dẫn xuất phải tính lại. Lựa chọn được xác nhận bằng workload traversal thực, không chỉ vì dữ liệu “có nhiều quan hệ”.

### 6.3. Khi nào đưa dữ liệu sang mô hình phân tích?

Báo cáo theo tháng, sản phẩm, kênh và khu vực có thể yêu cầu quét hàng trăm triệu dòng. Nếu làm chậm giao dịch trực tuyến, tách workload phân tích ra kho dữ liệu chuyên dụng có thể hợp lý hơn việc tạo thêm cột lặp ở database giao dịch. Cần công bố rõ kỳ dữ liệu, grain, lịch đồng bộ và chiến lược dữ liệu đến muộn.

## 7. Thiết kế phép đo để so sánh công bằng

Một benchmark hữu ích phải cho phép **bác bỏ giả thuyết**, chứ không chỉ chứng minh phương án yêu thích. Ví dụ:

> “Lưu sẵn tổng thành tiền sẽ đưa p95 của API danh sách đơn xuống dưới 180 ms trong khi p95 cập nhật dòng hàng vẫn dưới 140 ms, không làm sai tổng và không làm tăng tỷ lệ chờ khóa vượt ngưỡng.”

Đây là một giả thuyết có điều kiện chấp nhận rõ ràng. Nếu chỉ đo API đọc và bỏ qua đường ghi, kết quả chưa đủ để quyết định.

### 7.1. Cố định điều kiện thí nghiệm

Ghi lại: phiên bản DB, cấu hình tài nguyên, số hàng và phân bố, thống kê, tập chỉ mục, cơ chế kết nối, concurrency, tỷ lệ đọc/ghi, loại truy vấn, tham số, chính sách cache, tỉ lệ dữ liệu nóng/lạnh và thời gian chạy. Nếu có thể, dùng cùng tập truy vấn và cùng dữ liệu giữa các phương án.

Không đánh giá trên một thiết bị nhàn rỗi rồi áp dụng thẳng sang môi trường có nhiều yêu cầu đồng thời. Với phương án thêm cột hay chỉ mục, còn phải tính thời gian migration và cách backfill trong lúc hệ thống vẫn hoạt động.

### 7.2. Đo cả đọc, ghi, tài nguyên và độ đúng

| Nhóm chỉ số | Cần đo | Vì sao |
| --- | --- | --- |
| Trải nghiệm | API p50, p95, p99; tỷ lệ lỗi; throughput | Khẳng định có đạt SLO người dùng không |
| DB đọc | Execution time, rows, buffer hits/reads, temp files | Biết truy vấn tốn ở đâu |
| DB ghi | Độ trễ INSERT/UPDATE/DELETE, WAL, lượng ghi | Phát hiện chi phí của cột lặp/chỉ mục |
| Tương tranh | Lock waits, deadlocks, số giao dịch đồng thời | Phát hiện hàng tổng hợp trở thành điểm nghẽn |
| Tài nguyên | CPU, I/O, memory, disk/index size | Tránh dồn chi phí từ đọc sang ghi/lưu trữ |
| Nhất quán | Số bản ghi lệch, biên độ lệch, độ tuổi bản sao | Xác nhận hợp đồng dữ liệu dẫn xuất |
| Vận hành | Thời gian backfill, refresh, phục hồi, độ trễ replication | Đánh giá khả năng triển khai và mở rộng |
| Tăng trưởng | Chi phí khi số hàng, khách lớn và tần suất gọi tăng | Tránh chọn giải pháp chỉ nhanh ở dữ liệu nhỏ |

**Độ đúng** phải có oracle độc lập: tính lại từ nguồn chuẩn, so theo quy tắc nghiệp vụ và mức độ trễ đã công bố. Ví dụ, nếu **orders.items_subtotal** là số tiền của các dòng hiện hành, một truy vấn đối soát có thể viết:

~~~sql
SELECT
    o.order_id,
    o.items_subtotal AS stored_subtotal,
    COALESCE(
        SUM(oi.quantity * oi.unit_price_at_purchase),
        0
    ) AS calculated_subtotal
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY o.order_id, o.items_subtotal
HAVING o.items_subtotal IS DISTINCT FROM COALESCE(
    SUM(oi.quantity * oi.unit_price_at_purchase),
    0
);
~~~

**IS DISTINCT FROM** bắt cả trường hợp giá trị lưu là NULL, vì trong PostgreSQL phép so sánh thông thường với NULL không trả TRUE/FALSE như so với một số cụ thể. Khi cột được thêm qua migration và còn đang backfill, cần đánh giá theo trạng thái chuyển đổi thay vì coi mọi NULL là lỗi vận hành cuối cùng.

Nếu bản sao bất đồng bộ, đối soát phải chỉ áp dụng cho dữ liệu **đã hết cửa sổ đồng bộ** hoặc so cùng mốc phiên bản/sự kiện. Đếm mọi sai khác tức thời là lỗi sẽ tạo báo động giả.

### 7.3. Chạy các kịch bản đủ để thấy đánh đổi

Nên so ít nhất ba tình huống:

1. **Đọc chủ đạo:** tỷ lệ truy vấn đọc cao và nhiều yêu cầu đồng thời.
2. **Ghi chủ đạo/đỉnh cập nhật:** cập nhật, sửa, hủy, retry và giao dịch cùng thay đổi một aggregate.
3. **Tải hỗn hợp:** lưu lượng gần thực tế, gồm khách có nhiều bản ghi và sự kiện cập nhật lặp.

Sau khi chạy ấm hệ thống ở mức phù hợp, đo đủ thời gian để nhận diện p95/p99 và độ biến động. Ghi cả đường cơ sở và phương án tốt nhất sau tối ưu đơn giản, tránh lấy một bản triển khai kém hiệu quả làm điểm so sánh dễ thắng.

## 8. Khung ra quyết định: chấp nhận, thử thêm hay từ chối?

Một quyết định chọn phương án có thể được xem qua **các điều kiện bắt buộc** và **chi phí đánh đổi**.

**Điều kiện bắt buộc** bao gồm:

- Chức năng đọc và ghi đạt SLO quan trọng ở tải dự kiến.
- Kết quả phản ánh đúng ngữ nghĩa nghiệp vụ; với bản sao phải có nguồn chuẩn và hợp đồng nhất quán.
- Chi phí lưu trữ, độ trễ đồng bộ, khả năng phục hồi và di chuyển dữ liệu nằm trong giới hạn vận hành chấp nhận được.
- Phương án có thể duy trì khi thay đổi quy tắc nghiệp vụ, không phụ thuộc vào thao tác sửa thủ công không kiểm soát.

Khi nhiều phương án đều đạt, hãy ưu tiên phương án **đơn giản nhất đủ để đáp ứng các điều kiện đã thống nhất**; sự phức tạp của bản sao, pipeline và backfill là chi phí thực.

Có thể dùng bảng quyết định thử nghiệm như sau:

| Phương án | SLO đọc | SLO ghi | Độ đúng/độ tươi | Chi phí vận hành | Kết luận thử nghiệm |
| --- | --- | --- | --- | --- | --- |
| JOIN chuẩn hóa chưa tối ưu | Không đạt | Đạt | Đạt | Thấp | Cần sửa truy vấn/chỉ mục |
| JOIN đã tối ưu | Đạt | Đạt | Đạt | Thấp | **Chọn** cho trang đơn giả định |
| Cột tổng lưu sẵn | Đạt | Không đạt ngưỡng ghi giả định | Chỉ đạt khi có đủ cập nhật/đối soát | Cao hơn | Chưa chọn |
| Materialized view cập nhật định kỳ | Đạt cho dashboard | Giảm áp lực đọc nguồn | Đạt nếu độ tươi trong ngưỡng cho phép | Có job refresh/giám sát | **Chọn** cho dashboard giả định |

Các kết luận trên chỉ áp dụng cho **hai ví dụ và số liệu minh họa** của bài, không phải khuyến nghị mặc định cho mọi hệ thống.

### 8.1. Khi benchmark không rõ ràng

Nếu thay đổi chỉ giúp p95 tốt hơn vài phần trăm và số liệu dao động nhiều, đừng kết luận ngay. Có thể cần chạy lại với tải ổn định hơn, đo nhiều lần, xem phân phối độ trễ và xác định phương án còn đáp ứng tốt khi dữ liệu tăng.

Nếu phương án thắng ở tải đọc nhưng thất bại ở đỉnh ghi, có thể thử cache, pre-aggregation bất đồng bộ, phân tán điểm ghi hoặc thiết kế read model riêng. Nhưng phải đảm bảo nghiệp vụ thực sự cho phép độ trễ của phương án mới.

Nếu chưa thể mô tả nguồn chuẩn hoặc cách đối soát, phương án nhân bản dữ liệu **chưa đủ điều kiện thiết kế**, dù phép đo truy vấn cho kết quả nhanh.

## 9. Lựa chọn hôm nay phải có đường thay đổi ngày mai

Phi chuẩn hóa là một quyết định kiến trúc có thể đảo ngược, nhưng đảo ngược thường tốn công. Nên chuẩn bị:

- **Hợp đồng dữ liệu:** ý nghĩa trường dẫn xuất, nguồn chuẩn, quy tắc làm mới, độ trễ được phép, người sở hữu.
- **Đường ghi duy nhất về mặt quy tắc:** mọi code path liên quan đều dùng một cơ chế cập nhật; xử lý thao tác lặp, thiếu hoặc sai thứ tự.
- **Chiến lược backfill:** nạp dữ liệu quá khứ mà không ghi đè những cập nhật vừa xảy ra; đối soát sau khi nạp.
- **Khả năng quan sát:** đo độ trễ, số bản ghi lệch, hàng đợi sự kiện, lỗi làm mới, điểm nghẽn khóa.
- **Chuyển đổi an toàn:** chuyển dần đường đọc, so sánh kết quả với truy vấn nguồn, có thể quay về cách đọc cũ nếu phát hiện sai.
- **Tiêu chí gỡ bỏ:** khi truy vấn cũ đã được cải thiện, tần suất sử dụng giảm hoặc chi phí duy trì bản sao vượt lợi ích đo được.

Ví dụ, thêm cột **items_subtotal** cần có kế hoạch backfill và đồng bộ trong giai đoạn chuyển tiếp. Không được giả định chỉ chạy một câu lệnh UPDATE tổng là đủ nếu trong lúc đó vẫn có giao dịch thêm/xóa dòng hàng. Cần kiểm soát thứ tự triển khai, xử lý tương tranh và kiểm tra chéo trước khi chuyển hoàn toàn sang đọc giá trị lưu sẵn.

Ngược lại, nếu một materialized view không còn phục vụ dashboard nào, tiếp tục chạy refresh định kỳ chỉ làm tốn tài nguyên. Quyết định phù hợp là đánh giá và xóa khi đã xác nhận không còn người dùng hay phụ thuộc.

## 10. Một phiếu đánh giá kỹ thuật có thể dùng ngay

Trước khi chọn phi chuẩn hóa, điền các mục sau cho **một access pattern cụ thể**:

| Mục | Cần ghi |
| --- | --- |
| Use case | API/báo cáo, người sử dụng và mục đích nghiệp vụ |
| Query shape | Bộ lọc, JOIN, aggregate, ORDER BY, LIMIT, số trường trả |
| Volume | Số hàng, phân bố, tăng trưởng, khách/bản ghi đặc biệt lớn |
| Frequency | Read/write per second; đỉnh tải; concurrency |
| SLO | p95/p99 tối đa; throughput; tỷ lệ lỗi |
| Freshness/consistency | Đúng ngay hay cho phép chậm bao lâu, đo bằng gì |
| Baseline | Số liệu trước tối ưu, môi trường và điều kiện đo |
| Phương án đơn giản | Viết lại query, chỉ mục, batch, pagination, cache |
| Phương án nhân bản | Bản sao nào, nguồn chuẩn, ai sở hữu, ghi/refresh thế nào |
| Chi phí | Ghi, khóa, dung lượng, migration, backfill, phục hồi |
| Validation | Đối soát dữ liệu, thử tải hỗn hợp, kiểm tra khi sự kiện lặp |
| Kết luận | Chọn phương án, bằng chứng, điều kiện cần đo lại |

Phiếu này khiến một thảo luận “nên thêm cột để nhanh hơn” trở thành quyết định có thể xem lại. Khi số liệu hoặc mô hình nghiệp vụ đổi, nhóm có thể đánh giá lại trên cùng các tiêu chí.

## 11. Bài tập vận dụng

**Bài 1 — JOIN hay cột tổng?** Một trang đọc 50 đơn gần nhất có p95 = 300 ms, mục tiêu 180 ms. Sau khi thêm chỉ mục phù hợp và tính tổng chỉ trên 50 đơn, p95 còn 130 ms. Nếu lưu thêm tổng trên đơn, p95 đọc còn 100 ms nhưng p95 cập nhật dòng hàng tăng từ 120 lên 190 ms, trong khi mục tiêu ghi tối đa 160 ms. Nên chọn gì, và vì sao?

**Bài 2 — Bảng tổng hợp theo giờ.** Dashboard hiển thị số đơn theo khu vực và giờ, đòi hỏi p95 dưới 500 ms và cho phép số liệu trễ 15 phút. Truy vấn trực tiếp 4 giây; bảng tổng hợp bất đồng bộ cho p95 = 110 ms, nhưng trong giờ cao điểm pipeline có độ trễ 24 phút. Bảng tổng hợp đã đạt yêu cầu chưa? Đo thêm chỉ tiêu nào?

**Bài 3 — Nhúng thông tin tác giả.** Hệ thống bài viết document nhúng tên tác giả hiện hành vào mỗi bài để giảm một lần truy vấn. Mỗi tác giả có trung bình 20 bài nhưng một số tác giả có hàng triệu bài. Những dữ liệu nào phải thu thập trước khi quyết định duy trì snapshot này?

**Bài 4 — Đọc nhiều, kết quả phải tức thời.** Công cụ kiểm tra tồn kho có tần suất đọc cao; cache giảm p95 nhưng đôi lúc trả tồn kho của vài phút trước. Có thể dùng kết quả cache để cam kết bán hàng không? Nếu cache vẫn hữu ích cho trang giới thiệu sản phẩm, nên phân chia trách nhiệm thế nào?

### Hướng giải

1. **Giữ truy vấn đã tối ưu**: cả đọc 130 ms và ghi 120 ms đều đạt yêu cầu; lưu tổng làm đường ghi vượt mục tiêu, tăng độ phức tạp đồng bộ. Chỉ xem lại nếu tải hoặc SLO thay đổi.
2. **Chưa đạt**: độ trễ dữ liệu 24 phút vượt mức cho phép 15 phút. Cần đo độ tuổi dữ liệu theo p95/p99 và cực đại, backlog, thời gian hồi phục, số liệu sai/lặp và khả năng tái tính; tối ưu hoặc thiết kế lại pipeline.
3. Đo phân bố fan-out khi đổi tên, tần suất đổi tên, chi phí cập nhật hàng triệu document, độ tươi cần thiết, mức đọc, độ trễ, tính nhất quán và cách sửa dữ liệu bị bỏ sót. Nếu tên cần là *tại thời điểm đăng bài* thì đây là ngữ nghĩa khác với tên *hiện hành*.
4. Không dùng giá trị cache có thể cũ để cam kết tồn kho nếu nghiệp vụ yêu cầu kiểm tra tức thời. Cache có thể phục vụ hiển thị tham khảo, còn đường đặt hàng phải xác thực, giữ chỗ hoặc trừ tồn kho bằng cơ chế đảm bảo đúng theo thiết kế giao dịch.

## 12. Ghi nhớ

**Mẫu truy cập quyết định phép thử; phép đo quyết định phương án.** Hãy mô tả truy vấn thực, độ lớn dữ liệu, tần suất, mức đồng thời, giới hạn độ trễ và độ tươi; tối ưu đường truy vấn/khóa/chỉ mục trước khi nhân bản dữ liệu.

**Một phương án phi chuẩn hóa chỉ “thắng” khi cải thiện luồng cần tối ưu mà vẫn đáp ứng yêu cầu ghi, tính đúng đắn, khả năng vận hành và tăng trưởng.** Nếu phương án đơn giản hơn đã đạt mục tiêu, việc không thêm bản sao cũng là một quyết định mô hình hóa dựa trên bằng chứng.

Khi bảo vệ thiết kế trước nhóm kỹ thuật, câu trả lời thuyết phục không phải là “phi chuẩn hóa sẽ nhanh hơn”, mà là: **“Với access pattern này và tải đại diện này, phương án được chọn đạt những SLO nào, có chi phí gì, và được kiểm chứng bằng số liệu cùng bất biến dữ liệu ra sao?”**

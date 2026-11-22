# Phân biệt tải giao dịch OLTP, phân tích OLAP và tải hỗn hợp trong Oracle Database

Một hệ thống bán hàng vừa phải xác nhận đơn trong vài chục mili giây, vừa phải tính doanh thu theo tháng trên hàng triệu dòng dữ liệu. Cả hai thao tác đều dùng SQL, thậm chí có thể đọc cùng một bảng `ORDERS`, nhưng chúng tạo ra **hai kiểu tải công việc (workload)** rất khác nhau. Nếu thiết kế cơ sở dữ liệu chỉ theo tên bảng hoặc theo câu lệnh `SELECT`/`INSERT`, chúng ta dễ chọn sai chỉ mục, phân vùng, tài nguyên xử lý và kiến trúc triển khai.

Bài học này phân biệt ba nhóm tải trong ngữ cảnh **Oracle Database**:

- **OLTP (Online Transaction Processing):** xử lý giao dịch nghiệp vụ ngắn, đồng thời cao, yêu cầu nhất quán và thời gian phản hồi thấp.
- **OLAP (Online Analytical Processing):** đọc, tổng hợp và phân tích lượng dữ liệu lớn để trả lời các câu hỏi kinh doanh.
- **Tải hỗn hợp / HTAP (Hybrid Transactional and Analytical Processing):** vừa phục vụ hoạt động giao dịch vừa phục vụ truy vấn phân tích, thường với yêu cầu dữ liệu phân tích đủ mới để hỗ trợ quyết định vận hành.

Mục tiêu là nhận diện tải từ **mẫu truy cập, độ trễ, mức đồng thời và yêu cầu độ mới dữ liệu**, hiểu vì sao các tải ảnh hưởng lẫn nhau trên Oracle, rồi chọn cách tổ chức dữ liệu và tài nguyên phù hợp.

## 1. Workload là gì? Vì sao không thể phân loại bằng loại câu lệnh SQL?

**Workload** là tập hợp truy vấn và giao dịch thực tế chạy lên cơ sở dữ liệu trong một khoảng thời gian, kèm tần suất, số người dùng đồng thời, lượng dòng được đọc/ghi, yêu cầu phản hồi và giới hạn tài nguyên.

Ví dụ cùng một bảng `ORDERS`:

```sql
-- Tìm 20 đơn gần nhất của một khách hàng.
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = :p_customer_id
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Câu lệnh này thường thuộc tải **OLTP**: lấy ít dòng, chạy rất thường xuyên, cần phản hồi nhanh trên giao diện.

```sql
-- Tổng số đơn theo từng tháng của một khoảng thời gian dài.
SELECT TRUNC(created_at, 'MM') AS month_begin,
       COUNT(*) AS order_count
FROM orders
WHERE created_at >= :p_from_date
  AND created_at < :p_to_date
GROUP BY TRUNC(created_at, 'MM')
ORDER BY month_begin;
```

Câu lệnh thứ hai thường thuộc tải **OLAP**: có thể phải đọc nhiều dòng, nhóm dữ liệu và tính tổng hợp. Cả hai đều là `SELECT`; yếu tố quyết định là **cách truy cập và mục tiêu sử dụng**, không phải từ khóa SQL.

Một số ví dụ khác:

| Yêu cầu nghiệp vụ | Kiểu tải điển hình | Lý do |
|---|---|---|
| Khấu trừ tồn kho và tạo đơn hàng | OLTP | Nhiều thao tác nhỏ phải thành công hoặc thất bại cùng nhau |
| Xem trạng thái của một đơn theo mã đơn | OLTP | Truy vấn có tính chọn lọc cao, cần độ trễ thấp |
| Tính doanh thu 12 tháng theo vùng và danh mục | OLAP | Quét, nối và tổng hợp nhiều bản ghi |
| Tạo báo cáo chốt sổ theo quý | OLAP | Ưu tiên tính đúng đắn của phép phân tích, có thể chạy lâu |
| Màn hình vận hành cập nhật mỗi vài giây đồng thời hệ thống liên tục nhận đơn | Hỗn hợp / gần HTAP | Dữ liệu giao dịch mới phải sớm xuất hiện trong phép tổng hợp |

**Lưu ý về thuật ngữ:** “tải hỗn hợp” chỉ việc OLTP và OLAP cùng tồn tại trong một hệ thống hoặc môi trường. **HTAP** thường nhấn mạnh khả năng phân tích dữ liệu giao dịch gần thời gian thực. Không phải mọi hệ thống có cả báo cáo và ghi giao dịch đều tự động là một kiến trúc HTAP hiệu quả.

## 2. OLTP: tối ưu cho giao dịch ngắn và tính nhất quán

OLTP phục vụ các thao tác như đăng nhập, ghi nhận thanh toán, đặt hàng, chuyển tiền, cập nhật số lượng hàng còn lại hoặc thay đổi trạng thái hồ sơ.

### 2.1 Đặc điểm nhận diện

- **Nhiều yêu cầu đồng thời:** hàng trăm hoặc hàng nghìn phiên có thể cùng xử lý những giao dịch nhỏ; mức thực tế phụ thuộc phần cứng và ứng dụng.
- **Đọc/ghi ít dòng mỗi yêu cầu:** tra cứu theo khóa chính, khóa ngoại, mã đơn hoặc một điều kiện có tính chọn lọc cao.
- **Thời gian phản hồi là yếu tố cốt lõi:** giao diện và API quan tâm đến thời gian phản hồi ở các phân vị như `p95`, `p99`, đặc biệt khi tải tăng.
- **Giao dịch ngắn, có ranh giới rõ:** các thay đổi liên quan được xác nhận bằng `COMMIT` hoặc hủy bằng `ROLLBACK`.
- **Tính đúng đắn khi đồng thời:** hai người cùng mua sản phẩm cuối cùng không được khiến tồn kho trở thành số âm.
- **Dữ liệu có thể thay đổi liên tục:** nhiều `INSERT`, `UPDATE`, `DELETE`, nên chi phí bảo trì chỉ mục và tranh chấp khóa rất quan trọng.

Các thuộc tính **ACID** giải thích yêu cầu cốt lõi của giao dịch:

| Thuộc tính | Ý nghĩa trong ví dụ đặt hàng |
|---|---|
| **Atomicity** (nguyên tử) | Tạo đơn, dòng hàng và trừ tồn kho là một đơn vị công việc; lỗi thì hoàn tác toàn bộ |
| **Consistency** (nhất quán) | Các ràng buộc như khóa ngoại, số lượng không âm và quy tắc nghiệp vụ được duy trì |
| **Isolation** (cô lập) | Những giao dịch đồng thời không được làm hỏng kết quả kinh doanh của nhau |
| **Durability** (bền vững) | Sau `COMMIT` thành công, hệ thống có cơ chế phục hồi các thay đổi đã xác nhận |

### 2.2 Ví dụ giao dịch đặt hàng trên Oracle

Giả sử cơ sở dữ liệu có mô hình nhỏ như sau (DDL lược bớt một số thông tin thực tế để tập trung vào tải):

```sql
CREATE TABLE customers (
    customer_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email       VARCHAR2(255) NOT NULL UNIQUE
);

CREATE TABLE products (
    product_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name       VARCHAR2(200) NOT NULL,
    unit_price NUMBER(12,2) NOT NULL CHECK (unit_price >= 0)
);

CREATE TABLE inventory (
    product_id    NUMBER PRIMARY KEY REFERENCES products(product_id),
    available_qty NUMBER(10) NOT NULL CHECK (available_qty >= 0)
);

CREATE TABLE orders (
    order_id    NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id NUMBER NOT NULL REFERENCES customers(customer_id),
    created_at  DATE DEFAULT SYSDATE NOT NULL,
    status      VARCHAR2(16) DEFAULT 'NEW' NOT NULL
                CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TABLE order_items (
    order_id   NUMBER NOT NULL REFERENCES orders(order_id),
    product_id NUMBER NOT NULL REFERENCES products(product_id),
    quantity   NUMBER(10) NOT NULL CHECK (quantity > 0),
    unit_price NUMBER(12,2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT pk_order_items PRIMARY KEY (order_id, product_id)
);
```

Một giao dịch tạo đơn cho **một sản phẩm** có thể mô tả bằng PL/SQL. Các biến bind `:p_customer_id`, `:p_product_id`, `:p_quantity` do chương trình gọi truyền vào:

```sql
DECLARE
    v_order_id orders.order_id%TYPE;
    v_unit_price products.unit_price%TYPE;
BEGIN
    -- Chỉ trừ kho nếu hàng còn đủ tại thời điểm UPDATE.
    UPDATE inventory
       SET available_qty = available_qty - :p_quantity
     WHERE product_id = :p_product_id
       AND available_qty >= :p_quantity;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Khong du ton kho');
    END IF;

    -- Giá lấy từ cơ sở dữ liệu thay vì tin giá do client gửi lên.
    SELECT unit_price INTO v_unit_price
      FROM products
     WHERE product_id = :p_product_id;

    INSERT INTO orders (customer_id, status)
    VALUES (:p_customer_id, 'NEW')
    RETURNING order_id INTO v_order_id;

    INSERT INTO order_items (order_id, product_id, quantity, unit_price)
    VALUES (v_order_id, :p_product_id, :p_quantity, v_unit_price);

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
```

Đây là ví dụ một giao dịch độc lập và giả định ứng dụng đã kiểm tra số lượng dương, quyền mua hàng và các điều kiện nghiệp vụ. Trong ứng dụng thực, tầng quản lý giao dịch thường quyết định `COMMIT`/`ROLLBACK`; không nên để một thủ tục tự `COMMIT` nếu nó phải tham gia vào giao dịch lớn hơn. Thanh toán và cập nhật trạng thái `PAID` là luồng nghiệp vụ riêng, không được coi là đã hoàn tất chỉ vì đơn `NEW` được tạo.

Điểm đáng chú ý là câu `UPDATE ... WHERE available_qty >= :p_quantity` đưa điều kiện còn hàng vào **cùng một lệnh cập nhật**. Hai giao dịch cạnh tranh trên cùng dòng tồn kho sẽ chịu cơ chế khóa và kiểm tra điều kiện của Oracle; cách viết này tránh mẫu đọc số lượng trước rồi cập nhật vô điều kiện ở bước sau. Giao dịch cần ngắn để không giữ khóa lâu, đồng thời phải xử lý lỗi và thử lại ở mức ứng dụng khi thích hợp.

### 2.3 Kiểu truy cập và chỉ mục cho OLTP

Khi cần danh sách đơn gần đây của một khách hàng, chỉ mục tổng hợp có thể hỗ trợ cả lọc lẫn thứ tự:

```sql
CREATE INDEX idx_orders_customer_recent
    ON orders (customer_id, created_at DESC, order_id DESC);
```

Đây là ứng viên chỉ mục cho truy vấn 20 đơn gần nhất ở đầu bài, không phải một quy tắc áp dụng cho mọi hệ thống. Oracle có thể chọn `INDEX RANGE SCAN`, đường truy cập khác hoặc `TABLE ACCESS` tùy thống kê, phân bố dữ liệu, số cột cần lấy và chi phí ước tính.

Trong OLTP, các chỉ mục **B-tree** thường hiệu quả cho tra cứu có tính chọn lọc cao. Tuy nhiên, mỗi chỉ mục bổ sung cũng phải được bảo trì khi dữ liệu thay đổi. Tạo chỉ mục cho mọi cột dễ khiến ghi chậm, chiếm dung lượng và tăng chi phí vận hành.

## 3. OLAP: tối ưu cho việc đọc và tổng hợp lượng dữ liệu lớn

OLAP phục vụ báo cáo, dashboard, phân tích xu hướng, phân khúc khách hàng, dự báo hoặc điều tra nguyên nhân biến động KPI. Truy vấn có thể đọc hàng triệu dòng để trả về vài chục dòng tổng hợp.

### 3.1 Đặc điểm nhận diện

- **Quét nhiều dòng, ít kết quả trả về:** tổng hợp theo tháng, vùng, nhóm sản phẩm hoặc kênh bán hàng.
- **Thường có `JOIN`, `GROUP BY`, `SUM`, `COUNT`, window function, sắp xếp:** có thể tiêu thụ đáng kể CPU, bộ nhớ, I/O và vùng `TEMP`.
- **Độ trễ thường đo bằng giây hoặc phút:** tùy loại báo cáo và cam kết dịch vụ, không mặc nhiên phải dưới 100 ms như một thao tác API.
- **Đọc chiếm ưu thế:** dữ liệu phục vụ phân tích thường được nạp theo lô, theo luồng hoặc từ một bản sao của dữ liệu vận hành.
- **Truy vấn linh hoạt:** người phân tích có thể đổi các chiều tổng hợp, nên không thể dự đoán và lập chỉ mục cho mọi tổ hợp điều kiện.
- **Độ mới dữ liệu được định nghĩa rõ:** báo cáo ngày hôm qua, dữ liệu chậm 15 phút hay dashboard gần thời gian thực là những yêu cầu khác nhau.

### 3.2 Ví dụ truy vấn phân tích trên cùng mô hình giao dịch

```sql
SELECT TRUNC(o.created_at, 'MM') AS month_begin,
       COUNT(DISTINCT o.order_id) AS paid_order_count,
       SUM(oi.quantity * oi.unit_price) AS gross_sales
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
  AND o.created_at >= :p_from_date
  AND o.created_at < :p_to_date
GROUP BY TRUNC(o.created_at, 'MM')
ORDER BY month_begin;
```

Truy vấn có thể phải đọc rất nhiều đơn và dòng chi tiết, nối hai bảng, tính tổng rồi gom nhóm. `COUNT(DISTINCT o.order_id)` tránh đếm một đơn nhiều lần khi đơn có nhiều sản phẩm. Biểu thức `SUM(oi.quantity * oi.unit_price)` giữ lại **giá tại thời điểm tạo dòng đơn**, không dùng giá hiện tại của bảng `PRODUCTS`.

Ví dụ chỉ tính *tổng giá trị dòng hàng của các đơn đang ở trạng thái `PAID`, phân nhóm theo ngày tạo đơn*. Một hệ thống kế toán thực tế còn cần xử lý hoàn tiền, chiết khấu, thuế, phí, thời điểm ghi nhận doanh thu và việc trạng thái đơn thay đổi theo thời gian. Chọn sai định nghĩa chỉ tiêu có thể tạo báo cáo sai dù SQL chạy nhanh và không lỗi.

### 3.3 Mô hình dữ liệu phục vụ phân tích

Trong OLTP, chuẩn hóa thường giúp hạn chế lặp dữ liệu và giữ quy tắc cập nhật rõ ràng: `CUSTOMERS`, `ORDERS`, `ORDER_ITEMS`, `PRODUCTS` được tách theo các thực thể và quan hệ.

Trong OLAP, **mô hình chiều (dimensional model)** thường tiện cho tổng hợp:

```text
DIM_DATE       DIM_CUSTOMER       DIM_PRODUCT
    \              |                 /
     \             |                /
        FACT_SALES (ngày, khách, sản phẩm, số lượng, giá trị...)
                       |
                 DIM_CHANNEL
```

`FACT_SALES` lưu các phép đo tại một **mức hạt (grain)** đã định nghĩa, chẳng hạn “một dòng sản phẩm trong một đơn đã thanh toán”. Các bảng chiều chứa thuộc tính để lọc và nhóm. Cùng một chiều khách hàng có thể yêu cầu lưu lịch sử thay đổi phân khúc hoặc khu vực theo chính sách phân tích, điều mà bảng khách hàng OLTP hiện tại chưa chắc đáp ứng.

Không phải cứ OLAP là bắt buộc có data warehouse hay star schema; Oracle có thể chạy truy vấn phân tích trực tiếp trên bảng quan hệ thông thường. Nhưng khi dữ liệu lớn và người dùng hỏi nhiều câu khác nhau, mô hình phân tích được thiết kế riêng giúp truy vấn và định nghĩa KPI rõ ràng hơn.

### 3.4 Tối ưu OLAP khác gì tối ưu OLTP?

Các phương án thường gặp trên Oracle bao gồm:

1. **Partitioning:** phân vùng bảng lớn theo thời gian để giảm dữ liệu cần đọc khi điều kiện lọc cho phép *partition pruning*, đồng thời thuận lợi cho quản lý dữ liệu cũ.
2. **Parallel Query:** chia việc quét, nối hoặc tổng hợp cho nhiều tiến trình; có thể giảm thời gian chạy một truy vấn nhưng tiêu tốn nhiều tài nguyên hơn và ảnh hưởng tải giao dịch khác.
3. **Materialized view:** lưu sẵn một kết quả tổng hợp, chẳng hạn doanh thu theo ngày. Chính sách `FAST`/`COMPLETE`, `ON DEMAND`/`ON COMMIT` và điều kiện áp dụng quyết định chi phí làm mới, độ trễ và yêu cầu cấu hình.
4. **Oracle Database In-Memory:** khi phiên bản/giấy phép hỗ trợ và cấu hình phù hợp, biểu diễn dữ liệu theo cột trong bộ nhớ có thể tăng tốc các phép quét và tổng hợp; dữ liệu gốc vẫn tồn tại dưới dạng lưu trữ hàng truyền thống.
5. **Chỉ mục phù hợp:** B-tree vẫn có ích với những điều kiện chọn lọc; bitmap index có thể hữu ích trong một số môi trường phân tích đọc nhiều, nhưng thường không phù hợp với bảng OLTP cập nhật đồng thời liên tục vì chi phí ghi và tranh chấp khóa.
6. **Thống kê optimizer và execution plan:** giúp Oracle lựa chọn thứ tự nối, kiểu quét, thuật toán join và phương án tổng hợp. Chỉ định “phải dùng index” cho mọi câu truy vấn thường không phải chiến lược tốt.

Các tính năng như Partitioning, Database In-Memory, Active Data Guard hoặc một số công cụ chẩn đoán có thể phụ thuộc phiên bản, edition, dịch vụ triển khai và quyền sử dụng. Cần kiểm tra môi trường Oracle cụ thể trước khi chọn chúng trong thiết kế.

## 4. So sánh OLTP và OLAP qua các chiều quan trọng

| Tiêu chí | OLTP | OLAP |
|---|---|---|
| Câu hỏi chính | “Giao dịch này có xử lý đúng và nhanh không?” | “Dữ liệu cho thấy xu hướng và nguyên nhân gì?” |
| Đơn vị công việc | Một thao tác nghiệp vụ hoặc giao dịch ngắn | Một câu hỏi phân tích có thể gồm nhiều phép biến đổi |
| Lượng dữ liệu mỗi truy vấn | Thường ít dòng, tra cứu chọn lọc | Thường nhiều dòng, quét và tổng hợp |
| Thao tác chủ đạo | `SELECT` theo khóa, `INSERT`, `UPDATE`, `DELETE` | `SELECT` với `JOIN`, `GROUP BY`, window functions |
| Mức đồng thời | Thường rất cao, nhiều giao dịch nhỏ | Có thể ít truy vấn hơn nhưng mỗi truy vấn nặng hơn |
| Điều cần tối ưu | Độ trễ `p95/p99`, thông lượng, thời gian chờ khóa | Thời gian hoàn tất truy vấn, I/O, CPU, `TEMP`, thông lượng báo cáo |
| Mô hình dữ liệu thường gặp | Chuẩn hóa, ràng buộc nghiệp vụ, chỉ mục phục vụ truy cập ngắn | Bảng sự kiện, bảng chiều, phân vùng, tổng hợp hoặc dữ liệu dựng sẵn |
| Xu hướng truy cập | Nhiều ghi nhỏ, đọc chọn lọc | Đọc nhiều, kết quả tổng hợp |
| Độ mới cần thiết | Dữ liệu vừa `COMMIT` phải khả dụng theo quy tắc cô lập | Có thể chấp nhận độ trễ theo SLA báo cáo, hoặc yêu cầu gần thời gian thực |
| Nguy cơ khi tải tăng | Khóa chờ, tranh chấp dòng nóng, log/commit, quá nhiều kết nối | Quét lớn, chiếm CPU/I/O, tràn `TEMP`, truy vấn kéo dài |

Bảng này mô tả **xu hướng**, không phải quy tắc tuyệt đối: OLTP vẫn có nhiều `SELECT`, OLAP vẫn có quá trình ghi/nạp dữ liệu; truy vấn dashboard có thể phản hồi rất nhanh nếu tổng hợp đã được tính sẵn.

## 5. Điểm đặc thù của Oracle khi hai loại tải cùng chạy

Oracle dùng các cơ chế quản lý giao dịch và tối ưu truy vấn cho cả hai nhóm tải. Hiểu các cơ chế này giúp phân biệt **cạnh tranh khóa** với **cạnh tranh tài nguyên**.

### 5.1 Read consistency: báo cáo đọc trong khi giao dịch đang ghi

Ở mức cô lập mặc định `READ COMMITTED`, mỗi câu lệnh SQL của Oracle nhìn thấy một ảnh nhất quán của dữ liệu tính theo thời điểm bắt đầu câu lệnh (thông qua SCN và dữ liệu phiên bản cũ được tái dựng từ `UNDO` khi cần). Một `SELECT` thông thường không yêu cầu khóa các dòng đang đọc như `SELECT ... FOR UPDATE`.

Giả sử:

1. Phiên A bắt đầu truy vấn tính tổng doanh thu lúc 10:00:00.
2. Phiên B thay đổi một đơn và `COMMIT` lúc 10:00:01.
3. Truy vấn đã chạy của phiên A tiếp tục đọc theo ảnh nhất quán của chính câu lệnh đó; một truy vấn mới của A có thể thấy kết quả khác.

Điều này giảm tình huống báo cáo `SELECT` chặn cập nhật OLTP chỉ vì đọc cùng bảng. Nhưng **không có nghĩa báo cáo “miễn phí”**:

- Truy vấn dài vẫn dùng CPU, bộ nhớ, I/O và có thể phải đọc nhiều `UNDO` để dựng phiên bản dữ liệu phù hợp.
- Nếu dữ liệu `UNDO` cần cho ảnh đọc nhất quán không còn khả dụng, có thể gặp lỗi `ORA-01555: snapshot too old`.
- Cập nhật đồng thời trên cùng dòng vẫn có thể chờ khóa; `SELECT ... FOR UPDATE` cũng có hành vi khóa khác `SELECT` thông thường.

Mức `SERIALIZABLE` có ngữ nghĩa ảnh đọc theo giao dịch và các giới hạn/xung đột ghi riêng; không thể suy từ ví dụ mặc định rằng mọi chế độ cô lập đều giống nhau.

### 5.2 Vì sao phân tích có thể làm OLTP chậm dù không khóa dòng?

Giả sử một báo cáo quét hàng trăm triệu dòng cùng lúc API cần cập nhật tồn kho. Báo cáo có thể sử dụng nhiều CPU, đọc nhiều block, phát sinh sort/hash join lớn, tiêu tốn `PGA`/`TEMP` và tạo áp lực lên bộ đệm. API khi đó phải chia sẻ tài nguyên với báo cáo nên `p99` tăng, dù không có row lock trực tiếp do báo cáo gây ra.

Có thể hình dung:

```text
                  ORACLE DATABASE
             +----------------------+
API đặt hàng |  cập nhật vài dòng    | -> cần phản hồi nhanh
             |                      |
Dashboard    |  quét + JOIN + GROUP  | -> cần nhiều CPU, I/O, TEMP
             +----------------------+
                   CÙNG TÀI NGUYÊN
```

**Oracle Database Resource Manager** cho phép đặt chính sách phân bổ và giới hạn tài nguyên theo nhóm tải trong các cấu hình hỗ trợ. Cùng với thiết kế chỉ mục, giới hạn độ đồng thời truy vấn phân tích, lịch chạy, dịch vụ kết nối và quy hoạch năng lực, nó giúp giảm ảnh hưởng qua lại. Chỉ tăng số lõi CPU hoặc thêm chỉ mục chưa chắc giải quyết được mọi điểm nghẽn.

### 5.3 Tăng khả năng xử lý không đồng nghĩa với tách loại tải

Oracle RAC có thể cung cấp nhiều instance truy cập cùng một database và giúp mở rộng/duy trì sẵn sàng cho một số mẫu tải; việc triển khai RAC **không tự động cô lập** một truy vấn phân tích nặng khỏi áp lực tài nguyên chung. Tương tự, thêm partition, cache hoặc parallel query không biến một schema giao dịch thành kho phân tích được thiết kế tốt.

## 6. Tải hỗn hợp và HTAP: cân bằng tốc độ giao dịch với phân tích mới

Một hệ thống gọi là **tải hỗn hợp** khi các giao dịch vận hành và truy vấn phân tích chạy trong cùng giải pháp, có thể trên cùng một Oracle Database hoặc qua những thành phần kết nối với nhau. **HTAP** nhấn mạnh khả năng phân tích dữ liệu vận hành gần thời gian thực, trong khi vẫn giữ năng lực xử lý giao dịch.

Ví dụ cửa hàng trực tuyến:

- Khách đặt hàng làm tăng tải OLTP.
- Nhân viên kho cần thấy số đơn chờ xử lý và lượng tồn gần thời gian thực.
- Quản lý muốn dashboard doanh thu theo khu vực, cập nhật mỗi phút.
- Bộ phận tài chính chỉ cần báo cáo được đối soát theo ngày hoặc tháng.

Không nhất thiết phải đưa **mọi** câu hỏi vào cùng một đường truy vấn: số đơn chờ lấy từ bảng vận hành có thể rất nhanh, dashboard phút có thể dùng dữ liệu tổng hợp cập nhật thường xuyên, còn đối soát tài chính có thể chạy trên một kho dữ liệu chuyên biệt.

### 6.1 Ba phương án kiến trúc điển hình

**Phương án A — Cùng bảng giao dịch, cùng database**

```text
Ứng dụng/API ─┐
              ├──> Oracle (ORDERS, ORDER_ITEMS, INVENTORY)
Dashboard ────┘
```

Phù hợp khi dữ liệu còn vừa, số truy vấn phân tích nặng thấp hoặc báo cáo đã được thiết kế rất chọn lọc. Độ mới của dữ liệu tốt vì đọc trực tiếp dữ liệu đã commit, nhưng hai nhóm tải chia sẻ tài nguyên và thay đổi tải báo cáo có thể ảnh hưởng API.

**Phương án B — Vẫn trong hệ sinh thái Oracle nhưng tối ưu đường đọc**

```text
API giao dịch ──> Oracle nguồn
                     |
         +-----------+-----------------+
         |           |                 |
   Bảng tổng hợp   In-Memory     Bản sao đọc
   / materialized  (nếu có)     (nếu có)
   view
         \           |                 /
          +----------+----------------+
                     |
                 Dashboard
```

Có thể dùng tổng hợp dựng sẵn, Database In-Memory khi phù hợp, hoặc đưa truy vấn đọc sang một bản sao chỉ đọc (ví dụ giải pháp dùng Active Data Guard với cấu hình/quyền sử dụng thích hợp). Mỗi cách có cơ chế đồng bộ, độ mới, chi phí và giới hạn riêng. Một materialized view làm mới mỗi 5 phút không đảm bảo dữ liệu mới từng giây; bản sao đọc có thể có **replication/apply lag**.

**Phương án C — Tách đường phân tích sang kho dữ liệu**

```mermaid
flowchart LR
    App["Ứng dụng giao dịch"] --> O["Oracle OLTP nguồn"]
    O --> C["CDC / ETL / ELT"]
    C --> W["Kho dữ liệu / mô hình phân tích"]
    W --> D["BI / Dashboard / Báo cáo"]
```

CDC (*Change Data Capture*) chuyển tiếp thay đổi từ dữ liệu nguồn; ETL/ELT kết hợp trích xuất, làm sạch và nạp dữ liệu. Mô hình phân tích có thể được biến đổi từ lược đồ chuẩn hóa sang fact/dimension. Đây là hướng phù hợp khi dashboard có nhiều phép nối/quét lớn hoặc người dùng phân tích tự do. Đổi lại phải quản lý chất lượng pipeline, độ trễ đồng bộ, chi phí lưu trữ và đối soát số liệu.

### 6.2 Bảng chọn giải pháp theo yêu cầu

| Yêu cầu thực tế | Điểm bắt đầu hợp lý | Điều cần theo dõi |
|---|---|---|
| Lọc đơn hàng, tra cứu chi tiết, thống kê rất nhỏ | Bảng OLTP với chỉ mục tốt | `p95/p99`, số dòng quét, khóa chờ |
| Một vài dashboard cố định, cập nhật theo phút | View/tổng hợp có chính sách refresh rõ | Chi phí refresh, độ trễ dữ liệu, tranh chấp tài nguyên |
| Phân tích rộng trên dữ liệu lớn, nhiều câu hỏi tùy ý | Kho dữ liệu/mô hình phân tích riêng | Thời gian truy vấn, chi phí nạp, độ trễ và đối soát |
| Báo cáo nặng cần offload đọc khỏi primary Oracle | Bản sao đọc hoặc môi trường phân tích độc lập, nếu phù hợp | Lag, tài nguyên phía bản sao, quyền sử dụng |
| API giao dịch có SLA nghiêm ngặt, báo cáo thay đổi khó đoán | Tách tài nguyên/đường xử lý phân tích | Ảnh hưởng của đợt báo cáo lên `p99` API |

Đây là định hướng lựa chọn, chưa phải quyết định sản phẩm. Cần xét dữ liệu thực, tần suất truy vấn, SLA và các tính năng Oracle đã được cấp phép.

### 6.3 Độ mới dữ liệu là một hợp đồng, không phải khẩu hiệu

Khi người dùng nói “dashboard real-time”, hãy làm rõ **tối đa chậm bao lâu** và **tính chính xác đến thời điểm nào**:

- “Số đơn vừa tạo phải xuất hiện sau 2 giây” khác với “bảng tổng kết phải cập nhật trong 15 phút”.
- Một pipeline có độ trễ 30 giây không đồng nghĩa mọi báo cáo đều phản ánh đúng thời điểm hiện tại; còn có bước tổng hợp, cache và refresh.
- Nếu dữ liệu đang đổi trong lúc báo cáo chạy, cần xác định thời điểm ảnh đọc, chính sách late events, đơn hoàn/hủy và cách đối soát.
- Cần công bố mốc cập nhật cuối cùng của dashboard, chẳng hạn “dữ liệu đến 14:35:00”, để người đọc không nhầm số liệu với trạng thái trực tiếp.

## 7. Ví dụ lựa chọn thiết kế cho một hệ thống bán hàng

Giả sử một ứng dụng có ba nhóm yêu cầu:

| Luồng | Yêu cầu minh họa | Phân loại |
|---|---|---|
| Tạo đơn, trừ kho, tra cứu đơn | Rất nhiều yêu cầu mỗi ngày; thời gian phản hồi API được đo ở `p99` | OLTP |
| Báo cáo doanh số theo tháng, khu vực, sản phẩm | Quét lịch sử nhiều năm; chạy theo lịch hoặc theo yêu cầu nhà phân tích | OLAP |
| Dashboard số đơn vừa thanh toán theo phút | Dữ liệu phải mới trong khoảng 1–2 phút; nhiều người cùng xem | Hỗn hợp / phân tích gần thời gian thực |

Một hướng thiết kế có thể là:

1. **Đường giao dịch:** dữ liệu đơn hàng được ghi vào Oracle với khóa chính/khóa ngoại, ràng buộc và các chỉ mục phục vụ API; mỗi giao dịch ngắn và có xử lý lỗi đồng thời.
2. **Dashboard vận hành:** nếu nhóm KPI hữu hạn, cân nhắc bảng tổng hợp theo phút hoặc materialized view với lịch làm mới phù hợp. Cần xác nhận thời gian làm mới và tác động lên giao dịch trước khi đưa vào production.
3. **Báo cáo lịch sử:** chuyển thay đổi hoặc nạp dữ liệu định kỳ sang môi trường phân tích; định nghĩa các bảng fact/dimension và quy tắc xử lý thay đổi trạng thái.
4. **Đối soát:** một con số “doanh thu” phải có định nghĩa thống nhất giữa dashboard và báo cáo tài chính; việc đồng bộ thành công chưa đảm bảo chỉ tiêu được tính giống nhau.

Thiết kế này không có nghĩa hệ thống nhỏ bắt buộc có ba cụm hạ tầng. Có thể bắt đầu bằng một database và chỉ tách tải khi số liệu vận hành chứng minh nhu cầu.

## 8. Đo workload trên Oracle: cần quan sát những gì?

Trước khi quyết định tối ưu hay tách hệ thống, nên ghi lại **một khoảng tải đại diện**: giờ cao điểm giao dịch, lúc chạy dashboard, lúc chạy báo cáo định kỳ và thời điểm các tải trùng nhau.

| Nhóm cần đo | Tín hiệu hữu ích | Cách diễn giải |
|---|---|---|
| Giao dịch OLTP | TPS, request/s, thời gian `p50/p95/p99`, tỉ lệ lỗi/timeout | Đánh giá khả năng phục vụ người dùng và độ ổn định tại giờ cao điểm |
| Khóa và đồng thời | Thời gian chờ row lock, thời gian giữ giao dịch, số kết nối hoạt động | Cho biết có tranh chấp trên dữ liệu nóng hay không |
| Truy vấn phân tích | Thời gian chạy, số dòng xử lý, logical/physical reads, CPU, `TEMP` | Phân biệt chi phí quét/nối/sắp xếp với độ trễ từ ứng dụng |
| Tài nguyên chung | CPU, I/O, áp lực bộ nhớ, hàng đợi công việc | Nhận diện báo cáo ảnh hưởng đến giao dịch ngay cả khi không có khóa chờ |
| Đường đồng bộ dữ liệu | Độ trễ CDC/replica, thời điểm refresh, thời điểm dữ liệu gần nhất | Kiểm chứng SLA độ mới dữ liệu |
| Độ đúng của kết quả | Đối soát số dòng, doanh thu, hoàn/hủy, sự kiện đến muộn | Đảm bảo tăng tốc không đổi nghĩa của chỉ tiêu |

Oracle cung cấp execution plan qua các công cụ như `DBMS_XPLAN`; các tiện ích quan sát bổ sung (AWR, ASH, SQL Monitoring...) có thể có điều kiện cấp phép hoặc phạm vi hỗ trợ khác nhau. Khi đọc plan, quan sát kiểu truy cập (`INDEX RANGE SCAN` hay `TABLE ACCESS FULL`), số dòng ước tính so với thực tế nếu thu thập được, thứ tự join và hoạt động sort/hash. **Full table scan không tự động là lỗi**: đối với OLAP đọc phần lớn bảng, quét tuần tự hoặc song song có thể hợp lý hơn rất nhiều lần tra cứu chỉ mục nhỏ lẻ.

Một phép thử có ý nghĩa là đo cùng lúc: (a) tải đặt hàng đại diện, (b) riêng báo cáo, và (c) hai tải chạy đồng thời. Nếu ở (c) `p99` giao dịch tăng mạnh trong khi row-lock wait không tăng tương ứng, cần xem CPU, I/O, bộ nhớ, `TEMP` và kế hoạch truy vấn trước khi quy kết nguyên nhân cho khóa.

## 9. Những ngộ nhận thường gặp

**“OLTP dùng `INSERT/UPDATE`, OLAP dùng `SELECT`.”** Sai. Hầu hết ứng dụng OLTP đọc rất thường xuyên; điểm khác biệt là lượng dữ liệu, mẫu truy cập, thời gian phản hồi và mục tiêu công việc.

**“Oracle có read consistency nên báo cáo dài không ảnh hưởng giao dịch.”** Sai. Read consistency giảm nhu cầu khóa đọc đối với `SELECT` thông thường, nhưng không loại bỏ cạnh tranh CPU/I/O/bộ nhớ hoặc nguy cơ thiếu `UNDO` cho truy vấn dài.

**“Thêm thật nhiều index luôn làm truy vấn nhanh.”** Sai. Index giúp một số điều kiện truy vấn, nhưng tốn chi phí ghi và lưu trữ; truy vấn phân tích quét phần lớn bảng đôi khi tốt hơn với full scan và partition pruning.

**“Materialized view luôn chứa dữ liệu mới nhất.”** Sai. Độ mới phụ thuộc cơ chế và thời điểm refresh. `ON COMMIT` có chi phí riêng và không phải cấu hình phù hợp cho mọi kiểu tổng hợp.

**“Đưa truy vấn sang standby là kết quả tức thời.”** Sai. Bản sao có thể có độ trễ apply và giới hạn chức năng; cần đo lag, định nghĩa SLA và xác minh môi trường hỗ trợ.

**“Một hệ thống có dashboard là HTAP.”** Chưa đủ. Dashboard dùng dữ liệu xuất theo lô mỗi đêm là một kiến trúc có cả OLTP và OLAP, nhưng không có đặc trưng phân tích gần thời gian thực của HTAP.

**“Tốc độ truy vấn là đủ để đánh giá thiết kế.”** Chưa đủ. Phải xem dữ liệu có đúng, đủ mới, có xử lý hoàn/hủy hay không; đồng thời tránh cải thiện báo cáo bằng cách làm `p99` giao dịch vượt SLA.

## 10. Bài tập tình huống và hướng suy luận

Một doanh nghiệp có Oracle Database phục vụ ứng dụng đặt hàng. Vào giờ cao điểm, API cập nhật tồn kho bắt đầu chậm mỗi khi dashboard tổng hợp 24 tháng lịch sử chạy. Ban quản lý muốn dashboard cập nhật ít nhất mỗi 5 phút. Họ đề xuất tạo chỉ mục trên mọi cột trong `ORDERS` và tăng parallel query cho mọi báo cáo.

Hãy lần lượt tự trả lời:

1. Phần nào là OLTP, phần nào là OLAP, và vì sao đây là tải hỗn hợp?
2. Báo cáo có nhất thiết khóa các dòng tồn kho mà API đang cập nhật không?
3. Thêm nhiều chỉ mục và tăng parallel query có thể tạo tác dụng phụ gì?
4. Với SLA độ mới 5 phút, có các cách nào giảm số lần phải quét 24 tháng dữ liệu trực tiếp trên database giao dịch?
5. Cần đo tín hiệu nào để biết giải pháp cải thiện cả giao dịch và báo cáo?

**Gợi ý lập luận:**

- Ghi đơn/trừ kho là OLTP; tổng hợp lịch sử là OLAP. Chúng cùng cạnh tranh tài nguyên khi chạy trên Oracle nguồn.
- `SELECT` thông thường tận dụng read consistency, vì vậy việc API chậm có thể xuất phát từ CPU/I/O/`TEMP` dù không có khóa đọc chặn cập nhật.
- Index bổ sung làm tăng chi phí bảo trì DML; parallel query có thể sử dụng thêm CPU và I/O tại đúng thời điểm tải giao dịch cao.
- Có thể thử phân vùng và tối ưu plan, tính tổng hợp tăng dần theo khoảng thời gian, materialized view với refresh có kiểm soát hoặc tách đường phân tích qua CDC/replica/kho dữ liệu, tùy khả năng Oracle đang có.
- So sánh `p95/p99` API, lỗi giao dịch, thời gian dashboard, độ trễ số liệu và tài nguyên trong cùng một kịch bản tải hỗn hợp. Không chỉ nhìn thời gian của một câu `SELECT` đơn lẻ.

## 11. Ghi nhớ khi thiết kế trên Oracle

Một truy vấn OLTP tốt thường **truy cập ít dữ liệu, phản hồi ổn định và giữ giao dịch ngắn**. Một truy vấn OLAP tốt thường **xử lý khối dữ liệu cần thiết với chi phí hợp lý, cho ra chỉ tiêu đúng nghĩa và đạt SLA báo cáo**. Một kiến trúc tải hỗn hợp tốt phải đáp ứng cả hai, đồng thời nói rõ **độ mới dữ liệu** và **mức ảnh hưởng giữa các tải**.

Khi gặp một yêu cầu mới, đừng bắt đầu bằng câu hỏi “có cần index không?”. Hãy hỏi: *Ai chạy truy vấn? Chạy bao nhiêu lần? Đọc/ghi bao nhiêu dòng? Phản hồi phải nhanh đến mức nào? Cần dữ liệu mới đến đâu? Nó sẽ tranh tài nguyên với giao dịch nào?* Câu trả lời cho sáu câu hỏi này mới là nền tảng để chọn chỉ mục, phân vùng, tổng hợp, Resource Manager hoặc kiến trúc phân tích riêng trong Oracle Database.

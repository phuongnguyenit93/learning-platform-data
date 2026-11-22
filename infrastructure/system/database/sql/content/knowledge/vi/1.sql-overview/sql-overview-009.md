# Phạm vi SQL và mối liên hệ với thiết kế dữ liệu, hiệu năng, vận hành

SQL (Structured Query Language) là ngôn ngữ làm việc với dữ liệu có cấu trúc, đặc biệt phổ biến trong các hệ quản trị cơ sở dữ liệu quan hệ (RDBMS). Một câu lệnh SQL có thể truy vấn dữ liệu, nhưng phạm vi sử dụng SQL rộng hơn rất nhiều: định nghĩa cấu trúc lưu trữ logic, ràng buộc tính hợp lệ của dữ liệu, thay đổi dữ liệu, phân quyền và phối hợp giao dịch.

Trong một hệ thống thực tế, **thiết kế dữ liệu, câu lệnh SQL, hiệu năng và vận hành là các quyết định liên thông**. Một bảng được thiết kế tốt nhưng truy vấn sai có thể trả kết quả thiếu hoặc chậm; một truy vấn nhanh trong môi trường thử nghiệm vẫn có thể gây khóa kéo dài khi chạy đồng thời; một chỉ mục tối ưu cho đọc có thể làm tăng chi phí ghi, dung lượng và thời gian bảo trì.

Tài liệu này giải thích phạm vi của SQL, cách SQL thể hiện mô hình dữ liệu, tác động tới hiệu năng và trách nhiệm vận hành từ góc nhìn của người phát triển ứng dụng.

## 1. Phân biệt SQL, cơ sở dữ liệu và hệ quản trị cơ sở dữ liệu

Ba khái niệm liên quan nhưng không đồng nhất:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Cơ sở dữ liệu (database)** | Tập hợp dữ liệu được tổ chức và quản lý | Dữ liệu khách hàng, đơn hàng, sản phẩm |
| **Hệ quản trị CSDL (DBMS/RDBMS)** | Phần mềm lưu trữ, xử lý truy vấn, quản lý giao dịch, quyền truy cập và phục hồi | PostgreSQL, MySQL, SQL Server, Oracle Database |
| **SQL** | Ngôn ngữ để mô tả thao tác và yêu cầu đối với DBMS | CREATE TABLE, SELECT, UPDATE, COMMIT |

SQL có tính **khai báo (declarative)**: người viết mô tả dữ liệu cần lấy hoặc thay đổi và những điều kiện phải thỏa mãn; DBMS quyết định kế hoạch thực thi cụ thể, chẳng hạn quét bảng, dùng chỉ mục hay chọn thứ tự JOIN. Vì vậy, **câu SQL đúng về mặt logic không tự bảo đảm thực thi hiệu quả**.

SQL có tiêu chuẩn chung, nhưng sản phẩm DBMS có các *dialect* và khả năng riêng. Chẳng hạn, cách khai báo cột tự tăng, phân trang, hàm ngày giờ, kiểu JSON, chỉ mục hoặc thao tác đồng thời có thể khác nhau. Các ví dụ thực hành bên dưới dùng **PostgreSQL**; khi chuyển sang DBMS khác cần đối chiếu cú pháp và hành vi của hệ đó.

SQL cũng xuất hiện trong hệ thống phân tích dữ liệu và kho dữ liệu. Tuy nhiên, mỗi hệ có đặc tính lưu trữ, giao dịch và tối ưu khác nhau; không thể áp dụng nguyên xi giả định của một RDBMS giao dịch cho mọi công cụ chấp nhận cú pháp SQL.

## 2. SQL thực sự bao phủ những công việc gì?

Các nhóm lệnh thường được dùng để định hướng học tập:

| Nhóm | Mục đích | Lệnh thường gặp | Câu hỏi đang giải quyết |
| --- | --- | --- | --- |
| **DDL — Data Definition Language** | Định nghĩa và thay đổi đối tượng dữ liệu | CREATE, ALTER, DROP | Dữ liệu có cấu trúc, khóa và ràng buộc như thế nào? |
| **DML — Data Manipulation Language** | Thêm, sửa, xóa dữ liệu | INSERT, UPDATE, DELETE, MERGE | Trạng thái dữ liệu thay đổi ra sao? |
| **DQL — Data Query Language** | Đọc và kết hợp dữ liệu | SELECT, JOIN, GROUP BY, HAVING, ORDER BY | Cần trả về những bản ghi và phép tính nào? |
| **DCL — Data Control Language** | Cấp hoặc thu hồi quyền | GRANT, REVOKE | Ai được phép làm gì? |
| **TCL — Transaction Control Language** | Xác định ranh giới giao dịch | BEGIN/START TRANSACTION, COMMIT, ROLLBACK, SAVEPOINT | Nhiều thao tác có được xác nhận hoặc hủy cùng nhau không? |

**Lưu ý về thuật ngữ:** DQL là cách phân loại mang tính sư phạm; một số tài liệu xếp SELECT vào DML. Việc phân nhóm không quan trọng bằng hiểu tác dụng và đặc tính giao dịch của từng lệnh. Không phải mọi DBMS đều hỗ trợ mọi lệnh hoặc cùng cú pháp.

Vượt ra ngoài các lệnh cơ bản, SQL còn hỗ trợ truy vấn tổng hợp, truy vấn lồng, CTE (WITH), hàm cửa sổ, view, ràng buộc dữ liệu, các cấu trúc thủ tục hoặc trigger tùy DBMS. Mỗi công cụ cần được dùng theo một mục đích rõ ràng:

- **Truy vấn** diễn đạt dữ liệu cần đọc và cách kết hợp, lọc, nhóm, sắp xếp.
- **Lược đồ (schema) và ràng buộc** diễn đạt phần quy tắc dữ liệu mà DBMS có thể bảo vệ.
- **Giao dịch** gom nhiều thay đổi thành một đơn vị nhất quán.
- **Quyền và đối tượng quản trị** giới hạn truy cập và tổ chức cách khai thác dữ liệu.

SQL không tự thay thế việc thu thập yêu cầu nghiệp vụ, thiết kế kiến trúc ứng dụng, quản trị máy chủ, sao lưu, giám sát hoặc quyết định chính sách bảo mật. Nó là một giao diện quan trọng để hiện thực hóa các quyết định đó trong DBMS.

## 3. Từ yêu cầu nghiệp vụ đến thiết kế dữ liệu

Trước khi viết SELECT hoặc CREATE TABLE, cần trả lời: hệ thống quản lý thực thể nào, chúng có quan hệ gì, dữ liệu nào bắt buộc, dữ liệu nào có thể thay đổi và điều kiện nào luôn phải đúng?

Một cách chia tầng thiết kế:

1. **Mô hình khái niệm:** xác định khách hàng, đơn hàng, sản phẩm; một khách hàng có nhiều đơn hàng; mỗi đơn hàng có nhiều dòng hàng.
2. **Mô hình logic:** xác định bảng, cột, kiểu dữ liệu, khóa chính, khóa ngoại, tính duy nhất, tính tùy chọn và phụ thuộc dữ liệu.
3. **Mô hình vật lý:** quyết định chỉ mục, cách phân vùng, tổ chức lưu trữ và các đặc điểm triển khai phù hợp tải thực tế của DBMS.

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ và quy tắc dữ liệu"] --> B["Mô hình khái niệm và logic"]
    B --> C["Lược đồ SQL: bảng, khóa, ràng buộc"]
    C --> D["Câu SQL đọc/ghi và giao dịch"]
    D --> E["Kế hoạch thực thi, chỉ mục, khóa, I/O"]
    E --> F["Giám sát, sao lưu, migration, bảo mật"]
    F -->|"Số liệu và thay đổi yêu cầu"| B
~~~

### 3.1. Khóa và ràng buộc không chỉ để trình bày sơ đồ

- **PRIMARY KEY:** định danh mỗi bản ghi; cột khóa chính không nhận NULL.
- **FOREIGN KEY:** duy trì tính tham chiếu giữa các bảng, ngăn tham chiếu tới bản ghi không tồn tại theo quy tắc khai báo.
- **NOT NULL:** không cho phép thiếu giá trị ở một cột bắt buộc.
- **UNIQUE:** ngăn trùng lặp theo ngữ nghĩa so sánh của DBMS; cách xử lý NULL và phân biệt chữ hoa/thường cần kiểm tra theo hệ cụ thể.
- **CHECK:** yêu cầu biểu thức kiểm tra hợp lệ, ví dụ số lượng lớn hơn 0. Trong PostgreSQL, biểu thức CHECK trả FALSE mới vi phạm; kết quả UNKNOWN do NULL không bị CHECK từ chối, vì vậy cần kết hợp NOT NULL khi bắt buộc có giá trị.

Ràng buộc nằm trong database có giá trị đặc biệt khi nhiều dịch vụ, tác vụ nhập liệu hoặc script cùng ghi dữ liệu: tất cả các bên đều chịu chung một quy tắc. Kiểm tra ở ứng dụng vẫn cần thiết để đưa ra thông báo tốt và xử lý quy trình phức tạp, nhưng không thay thế được ràng buộc cốt lõi tại nơi lưu trữ.

### 3.2. Chuẩn hóa và phi chuẩn hóa là quyết định có chi phí

**Chuẩn hóa** giúp giảm dữ liệu lặp và các bất thường khi thêm, sửa, xóa. Ví dụ thông tin khách hàng nên được quản lý ở bảng khách hàng, thay vì sao chép tên, email hiện tại của khách hàng vào mọi dòng đơn hàng mà không có lý do nghiệp vụ.

Tuy nhiên, một số dữ liệu cần được lưu như **ảnh chụp lịch sử**. Giá sản phẩm hiện tại có thể thay đổi, nhưng đơn giá tại thời điểm đặt hàng thường phải giữ nguyên để tính lại đúng số tiền đơn cũ. Lưu đơn giá trên dòng đơn hàng là một quyết định nghiệp vụ có chủ đích, không đơn thuần là lỗi trùng lặp.

Phi chuẩn hóa, bảng tổng hợp hoặc dữ liệu dẫn xuất có thể tăng tốc đọc trong một số trường hợp, đổi lại phải giải quyết đồng bộ dữ liệu, cập nhật, kiểm tra nhất quán và phục hồi. Chỉ nên đưa vào sau khi xác định mẫu truy vấn và có số liệu tải phù hợp.

## 4. Ví dụ xuyên suốt: hệ thống đơn hàng

Giả sử cần quản lý khách hàng, sản phẩm, đơn hàng và các dòng hàng. Yêu cầu tối thiểu:

- Một khách hàng có thể có nhiều đơn hàng.
- Một đơn hàng có thể có nhiều sản phẩm, mỗi sản phẩm một dòng trong cùng đơn.
- Số lượng đặt phải dương; đơn giá tại lúc đặt không âm.
- Hệ thống có thể truy xuất lịch sử đơn hàng dù giá bán hiện tại thay đổi.
- Ví dụ có theo dõi số lượng hàng khả dụng ở mức một sản phẩm, chưa xét nhiều kho, đặt giữ chỗ hoặc hàng trả.

Lược đồ PostgreSQL tham khảo:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    current_price NUMERIC(12, 2) NOT NULL
        CHECK (current_price >= 0),
    available_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (available_quantity >= 0)
);

CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'PAID', 'CANCELED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL REFERENCES orders(id),
    product_id BIGINT NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, product_id)
);
~~~

Những quyết định thiết kế cần nhận ra:

| Quyết định | Lý do và hệ quả |
| --- | --- |
| Tách orders và order_items | Một đơn có nhiều dòng; không phải thêm cột product_1, product_2... |
| order_items có khóa ghép (order_id, product_id) | Ngăn cùng một sản phẩm xuất hiện hai dòng trong cùng đơn theo yêu cầu giả định; nếu cần nhiều dòng cho một sản phẩm thì phải đổi mô hình |
| order_items.unit_price | Giữ giá tại thời điểm giao dịch, độc lập với products.current_price |
| NUMERIC(12, 2) cho tiền | Tránh sai số biểu diễn nhị phân của kiểu số thực dấu phẩy động; vẫn cần xác định quy tắc làm tròn, thuế, tiền tệ |
| TIMESTAMPTZ cho thời điểm | Lưu một thời điểm có ý nghĩa tuyệt đối; hiển thị theo múi giờ nghiệp vụ ở biên ứng dụng |
| CHECK, NOT NULL và FOREIGN KEY | Đưa các bất biến đơn giản xuống tầng dữ liệu |
| Không khai báo xóa dây chuyền đơn hàng | Không mặc nhiên xóa lịch sử giao dịch khi xóa dữ liệu liên quan; quy định lưu trữ/xóa phải được thiết kế riêng |

Lược đồ chưa giải quyết mọi quy tắc. Ví dụ, CHECK trên status chỉ giới hạn tập giá trị, không cấm chuyển trực tiếp từ CANCELED sang PAID. Quy tắc chuyển trạng thái cần được kiểm soát bằng luồng nghiệp vụ và giao dịch thích hợp. Tính duy nhất của email cũng phụ thuộc yêu cầu có phân biệt chữ hoa/chữ thường hay không; nếu không phân biệt, cần bổ sung chính sách chuẩn hóa hoặc cơ chế so sánh phù hợp.

## 5. Từ cấu trúc bảng đến câu truy vấn

Yêu cầu: **lấy 20 đơn mới nhất của một khách hàng, kèm tổng tiền mỗi đơn**. Truy vấn PostgreSQL:

~~~sql
WITH recent_orders AS (
    SELECT id, created_at
    FROM orders
    WHERE customer_id = :customer_id
    ORDER BY created_at DESC, id DESC
    LIMIT 20
)
SELECT
    ro.id,
    ro.created_at,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_amount
FROM recent_orders AS ro
LEFT JOIN order_items AS oi ON oi.order_id = ro.id
GROUP BY ro.id, ro.created_at
ORDER BY ro.created_at DESC, ro.id DESC;
~~~

Ở đây **:customer_id** là ký hiệu tham số có tên ở tầng ứng dụng hoặc thư viện truy cập dữ liệu; câu lệnh gửi trực tiếp đến PostgreSQL cần dùng cú pháp tham số mà driver/công cụ thực sự hỗ trợ. Hãy truyền giá trị bằng cơ chế *parameter binding*, không nối chuỗi đầu vào của người dùng vào SQL.

Diễn giải các phần:

1. CTE xác định 20 đơn mới nhất của đúng khách hàng trước khi tính tổng, tránh tổng hợp toàn bộ lịch sử chỉ để hiển thị một trang ngắn.
2. ORDER BY thêm id để kết quả ổn định khi nhiều đơn có cùng created_at.
3. LEFT JOIN giữ lại cả đơn chưa có dòng hàng; SUM cộng quantity × unit_price, COALESCE đổi kết quả NULL thành 0.
4. GROUP BY gom dòng hàng theo đơn; ORDER BY cuối cùng xác định thứ tự trả về. Không nên cho rằng thứ tự trong CTE tự động là thứ tự kết quả ngoài cùng.

Một ứng dụng có thể viết SQL đúng cú pháp nhưng sai yêu cầu khi JOIN nhân bản dòng, quên điều kiện khách hàng, dùng giá hiện tại thay vì giá đã chốt, hoặc LIMIT trước/sau phép nhóm không đúng ý định. **Kiểm tra tính đúng của kết quả là bước riêng với đo tốc độ**.

## 6. SQL liên hệ trực tiếp với hiệu năng như thế nào?

### 6.1. Chi phí thực thi phụ thuộc dữ liệu và kế hoạch của DBMS

Khi nhận truy vấn, DBMS phân tích cú pháp, xác định tên và kiểu, tối ưu kế hoạch rồi thực thi. Kế hoạch có thể gồm quét tuần tự, quét chỉ mục, sắp xếp, băm, lồng vòng JOIN hoặc tổng hợp. Bộ tối ưu sử dụng thống kê về dữ liệu để ước lượng số dòng và chi phí.

Hiệu năng phụ thuộc đồng thời vào:

- **Số dòng và phân bố dữ liệu:** bảng nhỏ hoặc điều kiện lọc không chọn lọc có thể phù hợp với quét toàn bảng.
- **Mẫu truy cập:** lọc theo cột nào, JOIN theo khóa nào, lấy bao nhiêu dòng, có sắp xếp/nhóm hay không.
- **Chỉ mục:** cấu trúc hỗ trợ tìm kiếm, JOIN, sắp xếp; không phải chỉ mục nào cũng giúp mọi truy vấn.
- **Thời điểm và mức đồng thời:** khóa, giao dịch dài, nhiều truy vấn chạy cùng lúc có thể làm chậm hệ thống dù một truy vấn riêng lẻ nhanh.
- **Hạ tầng và bộ nhớ:** CPU, bộ nhớ đệm, I/O, dung lượng, kết nối mạng và cấu hình DBMS.

Với truy vấn lịch sử đơn hàng ở trên, một chỉ mục có thể phù hợp:

~~~sql
CREATE INDEX idx_orders_customer_created_id
ON orders (customer_id, created_at DESC, id DESC);
~~~

Thứ tự cột bắt đầu bằng customer_id để phục vụ điều kiện bằng, sau đó đến created_at và id để phù hợp sắp xếp lấy đơn mới nhất. Khóa chính của order_items là (order_id, product_id) thường đã tạo chỉ mục có tiền tố order_id trong PostgreSQL, hỗ trợ bước JOIN theo order_id. Ngược lại, **khóa ngoại trong PostgreSQL không tự tạo chỉ mục trên cột tham chiếu ở bảng con**; chỉ thêm chỉ mục phụ khi truy vấn và hoạt động ghi/xóa thực sự cần.

Chỉ mục không miễn phí: chiếm dung lượng, tăng công ghi và bảo trì, có thể giảm hiệu quả khi dữ liệu thay đổi thường xuyên. Không có quy tắc “mỗi cột một index” hoặc “mọi truy vấn chậm đều thêm index”.

### 6.2. Viết điều kiện thuận lợi cho chỉ mục

Giả sử cần lọc các đơn trong tháng 11 năm 2026, theo múi giờ đã được nghiệp vụ quy định. Khi có thể, ưu tiên điều kiện khoảng nửa mở trên cột thời điểm:

~~~sql
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+07'
~~~

So với việc áp dụng hàm lên từng giá trị cột, chẳng hạn DATE(created_at) = ..., lọc theo khoảng thường dễ tận dụng chỉ mục B-tree trên created_at hơn. Biểu thức trên cột có thể cần chỉ mục biểu thức riêng; DATE trên TIMESTAMPTZ còn chịu ảnh hưởng của múi giờ phiên làm việc. Ngoài ra, một chỉ mục trên (customer_id, created_at) chỉ có thể khai thác hiệu quả phần created_at tùy điều kiện trên customer_id và kế hoạch thực tế.

Những bẫy phổ biến khác là SELECT * khi chỉ cần vài cột, phân trang OFFSET quá sâu, N+1 queries khi ứng dụng truy vấn thêm từng bản ghi con, JOIN sai điều kiện hoặc thiếu giới hạn đầu ra. Với danh sách kéo dài, phân trang theo khóa (keyset pagination) thường đáng cân nhắc nếu có tiêu chí sắp xếp ổn định.

### 6.3. Đo kế hoạch, đừng suy đoán

Trong PostgreSQL:

~~~sql
EXPLAIN
SELECT id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

EXPLAIN cho biết kế hoạch ước lượng. **EXPLAIN (ANALYZE, BUFFERS)** thực sự chạy truy vấn rồi báo thời gian và số liệu thực thi (như lượng buffer đã truy cập); nên dùng trong môi trường và điều kiện an toàn, đặc biệt thận trọng với câu lệnh ghi vì ANALYZE có thể thực thi thay đổi dữ liệu.

Khi đọc kế hoạch, cần so sánh **số dòng ước lượng và số dòng thực tế**, bước chiếm thời gian, quét bảng/chỉ mục, số lần lặp, thao tác sắp xếp, lượng dữ liệu đọc và chờ khóa. Số liệu cũng thay đổi theo kích thước bảng, phân bố dữ liệu, cache, tham số truy vấn và mức đồng thời. Tối ưu dựa trên tình huống thật, sau đó đo lại.

## 7. Giao dịch và đồng thời: mối nối giữa dữ liệu đúng và hệ thống chạy đúng

Một yêu cầu nghiệp vụ thường gồm nhiều câu SQL. Ví dụ đặt hàng cần kiểm tra số lượng tồn, trừ tồn, tạo đơn và tạo các dòng hàng. Nếu bước trừ tồn thành công nhưng bước tạo đơn thất bại mà không có giao dịch, dữ liệu sẽ sai lệch.

Các tính chất **ACID** mô tả mục tiêu của giao dịch:

| Tính chất | Ý nghĩa thực tế |
| --- | --- |
| Atomicity | Các thay đổi thuộc một giao dịch được xác nhận cùng nhau hoặc được hoàn tác |
| Consistency | Giao dịch đưa database từ trạng thái hợp lệ sang trạng thái hợp lệ theo các ràng buộc được khai báo và logic được thực thi |
| Isolation | Quy định mức độ các giao dịch đồng thời có thể quan sát/tác động lẫn nhau |
| Durability | Thay đổi đã COMMIT được bảo vệ theo cơ chế bền vững của DBMS và cấu hình hạ tầng |

### 7.1. Ví dụ tránh bán vượt số lượng khả dụng

Một cách thiếu an toàn là để hai yêu cầu cùng SELECT số lượng tồn, đều thấy còn 1, rồi mỗi yêu cầu tự tính và ghi lại kết quả. Hai phép đọc không bảo đảm dữ liệu còn đúng khi UPDATE.

Với mô hình một dòng tồn kho trên products, có thể dùng UPDATE có điều kiện:

~~~sql
BEGIN;

UPDATE products
SET available_quantity = available_quantity - :quantity
WHERE id = :product_id
  AND available_quantity >= :quantity
RETURNING id, available_quantity;

-- Ứng dụng kiểm tra số dòng trả về.
-- 0 dòng: ROLLBACK và báo không đủ hàng hoặc không có sản phẩm.
-- 1 dòng: tiếp tục tạo đơn hàng trên cùng giao dịch.

INSERT INTO orders (customer_id)
VALUES (:customer_id)
RETURNING id;

-- Ứng dụng lấy id vừa tạo, rồi ghi dòng hàng tương ứng.
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES (:new_order_id, :product_id, :quantity, :trusted_unit_price);

COMMIT;
~~~

Đây là **chuỗi lệnh minh họa do ứng dụng điều phối**, không phải một script SQL độc lập có thể chạy nguyên trạng: các tham số có tên và nhánh kiểm tra số dòng cần được driver/ứng dụng xử lý. Chỉ COMMIT nếu tất cả bước thành công; nếu bất kỳ bước nào thất bại, ROLLBACK. Giá đơn vị phải được xác định từ nguồn đáng tin cậy và chính sách giá của hệ thống, không chấp nhận tùy ý từ client.

Phép UPDATE có điều kiện giúp xử lý tranh chấp ngay tại bản ghi được cập nhật. Tuy nhiên, ví dụ chưa giải quyết đặt nhiều sản phẩm, nhiều kho, giữ chỗ, hủy đơn, thanh toán bên ngoài hay xử lý yêu cầu lặp; mỗi vấn đề cần quy tắc và thiết kế bổ sung.

### 7.2. Isolation, khóa và thời lượng giao dịch

Các mức cô lập phổ biến gồm READ COMMITTED, REPEATABLE READ và SERIALIZABLE. Chi tiết đảm bảo và cách hiện thực có khác biệt giữa DBMS. Mức cô lập cao hơn có thể giảm một số bất thường nhưng cũng làm tăng tranh chấp hoặc buộc ứng dụng thử lại giao dịch.

Những điểm cần nhớ:

- **Khóa và tranh chấp:** cập nhật cùng bản ghi có thể phải chờ; nhiều giao dịch lấy khóa theo thứ tự trái ngược có thể gây deadlock.
- **Giao dịch dài:** giữ khóa, tài nguyên hoặc phiên bản dữ liệu lâu, gây ảnh hưởng truy vấn khác và công việc bảo trì.
- **Retry:** DBMS có thể yêu cầu thử lại khi deadlock hoặc xung đột tuần tự hóa; logic thử lại cần an toàn khi thực hiện nhiều lần.
- **Tác động ngoài DB:** gửi email hoặc gọi cổng thanh toán không được tự động hoàn tác khi SQL ROLLBACK. Cần thiết kế tính idempotent hoặc cơ chế phối hợp đáng tin cậy như outbox khi bài toán yêu cầu.

Vì vậy, hiệu năng không chỉ là tối ưu SELECT; còn phải kiểm soát độ dài giao dịch, thứ tự cập nhật, mức cô lập, kết nối và luồng ghi.

## 8. SQL và vận hành cơ sở dữ liệu

Một lược đồ và tập truy vấn chỉ thật sự có giá trị khi có thể triển khai, theo dõi, bảo vệ, thay đổi và phục hồi. Vận hành liên quan trực tiếp tới SQL vì chính SQL tạo ra tải đọc/ghi và thay đổi cấu trúc database.

### 8.1. Thay đổi schema an toàn

Khi hệ thống đã có dữ liệu và đang phục vụ người dùng, ALTER TABLE hoặc CREATE INDEX có thể cần khóa, quét dữ liệu, dùng thêm I/O và ảnh hưởng truy vấn đang chạy. Mức tác động phụ thuộc DBMS, phiên bản, kích thước bảng và dạng thay đổi.

Ví dụ cần bổ sung trường bắt buộc cho đơn hàng. Một lộ trình **expand → migrate → contract** thường gồm:

1. **Expand:** thêm trường hoặc cấu trúc mới ở trạng thái tương thích với phiên bản ứng dụng đang chạy.
2. **Migrate:** triển khai ứng dụng đọc/ghi phù hợp, chuyển hoặc bổ sung dữ liệu cũ theo lô có kiểm soát, kiểm tra trạng thái trước khi siết ràng buộc.
3. **Contract:** khi các phiên bản ứng dụng đã dùng cấu trúc mới, áp đặt ràng buộc cuối cùng và gỡ cấu trúc cũ nếu an toàn.

Migration cần được quản lý bằng phiên bản, thử trước trên dữ liệu có quy mô đại diện và có kế hoạch xử lý lỗi. Một số DBMS cung cấp cách tạo chỉ mục giảm khóa; trong PostgreSQL có CREATE INDEX CONCURRENTLY, nhưng lệnh này có giới hạn vận hành riêng, bao gồm không chạy trong transaction block thông thường.

Không nên giả định rằng **ROLLBACK ứng dụng** luôn có thể hoàn tác mọi thao tác DDL theo cùng cách trên mọi DBMS. Khi schema thay đổi, cần xác định rõ cách phục hồi hoặc migration tiến tới phiên bản sửa lỗi.

### 8.2. Bảo mật và phân quyền

Quyền database nên tuân theo nguyên tắc **ít quyền nhất**:

- Tài khoản ứng dụng chỉ nhận quyền đọc/ghi các đối tượng cần dùng; tài khoản chạy migration có thể cần quyền DDL riêng.
- Dùng tham số cho giá trị đầu vào để chống SQL injection; không ghép input trực tiếp thành điều kiện WHERE, ORDER BY hoặc tên bảng. Các phần định danh động thường cần danh sách cho phép rõ ràng, không thể coi chúng là giá trị bind thông thường.
- Không ghi mật khẩu, mã truy cập hoặc dữ liệu nhạy cảm vào log truy vấn; bảo vệ kết nối, bí mật cấu hình và dữ liệu sao lưu.
- Thiết kế chính sách xóa và lưu giữ dữ liệu phù hợp mục đích nghiệp vụ và yêu cầu pháp lý, bao gồm bản sao lưu và bản sao phục vụ phân tích.

Ví dụ GRANT/REVOKE thay đổi quyền tại DBMS, nhưng chỉ dùng lệnh SQL thôi chưa đủ: còn có quản lý tài khoản, xác thực, kết nối mạng, mã hóa, audit và quy trình cấp/thu hồi quyền.

### 8.3. Quan sát và phản ứng với sự cố

Các chỉ số nên theo dõi theo thời gian:

| Dấu hiệu | Cần xem gì | Liên hệ với thiết kế hoặc SQL |
| --- | --- | --- |
| Độ trễ truy vấn tăng, p95/p99 xấu | Query mẫu, EXPLAIN, số bản ghi, thống kê, tải CPU/I/O | JOIN không phù hợp, thiếu hoặc thừa chỉ mục, dữ liệu tăng |
| Giao dịch chờ lâu, deadlock | Thời gian giao dịch, truy vấn đang giữ khóa, thứ tự cập nhật | Phạm vi và thứ tự ghi quá rộng |
| Kết nối cạn | Pool ứng dụng, số kết nối mở, truy vấn chậm, giao dịch bỏ quên | Mỗi request giữ kết nối quá lâu hoặc cấu hình pool không phù hợp |
| Dung lượng tăng nhanh | Kích thước bảng/chỉ mục, dữ liệu lịch sử, chính sách lưu giữ | Bảng tăng trưởng, index thừa, bản ghi không được lưu trữ/xóa hợp lý |
| Đọc/ghi suy giảm theo thời gian | Thống kê optimizer, công việc bảo trì, I/O và bộ nhớ | Cần cập nhật thống kê, bảo trì hoặc điều chỉnh truy vấn/lược đồ |
| Phục hồi không đạt yêu cầu | Bản sao lưu, kiểm tra khôi phục, log giao dịch | Thiếu hoặc lỗi chiến lược backup/restore |

Đối với PostgreSQL, việc bảo trì và thống kê liên quan đến VACUUM/ANALYZE và cơ chế tự động tương ứng; hệ quản trị khác dùng công cụ khác. Cần đo trên hệ cụ thể thay vì coi một câu lệnh bảo trì là giải pháp chung cho mọi truy vấn chậm.

### 8.4. Sao lưu, phục hồi và khả năng sẵn sàng

**Backup** tạo khả năng lấy lại dữ liệu; **restore** là quá trình đưa dữ liệu vào trạng thái hoạt động. Chính sách cần xác định:

- **RPO (Recovery Point Objective):** tối đa chấp nhận mất bao nhiêu dữ liệu theo thời gian.
- **RTO (Recovery Time Objective):** tối đa chấp nhận mất bao lâu để phục hồi dịch vụ.
- Cách kiểm tra bản sao lưu, diễn tập khôi phục và, khi cần, phục hồi tới thời điểm cụ thể (PITR).

Replication và failover giúp tính sẵn sàng nhưng **bản sao đồng bộ không thay thế backup**: xóa nhầm hoặc lỗi logic cũng có thể được sao chép. Khả năng phục hồi chỉ được chứng minh khi đã thử khôi phục và xác minh dữ liệu có thể dùng được.

## 9. Nhìn một yêu cầu qua cả bốn góc độ

Giả sử sản phẩm yêu cầu: “Trang lịch sử đơn hàng của một khách hàng phải hiển thị nhanh, số tiền phải đúng và không làm gián đoạn lúc triển khai bản mới.”

| Góc độ | Câu hỏi cần trả lời | Quyết định mẫu |
| --- | --- | --- |
| **Thiết kế dữ liệu** | Một đơn có mấy dòng? Giá lịch sử lưu ở đâu? | Tách orders/order_items; lưu unit_price đã chốt |
| **SQL và tính đúng** | Tính tổng theo dòng nào? Có hiển thị đơn rỗng? Có thứ tự ổn định? | LEFT JOIN, SUM, GROUP BY; ORDER BY created_at và id |
| **Hiệu năng** | Lọc theo khách hàng có nhanh khi bảng lớn? | Lấy 20 đơn trước; xem chỉ mục (customer_id, created_at, id); đo EXPLAIN |
| **Vận hành** | Khi tăng dữ liệu hoặc thêm cột, triển khai và theo dõi thế nào? | Migration tương thích, theo dõi độ trễ/khóa/I/O, backup và kiểm tra restore |

Chỉ thay một tầng có thể làm lộ vấn đề ở tầng khác. Ví dụ tăng chỉ mục để tăng tốc lịch sử đơn hàng có thể làm chậm luồng tạo đơn ở tải ghi cao. Thêm bảng tổng hợp giúp trang báo cáo nhanh hơn nhưng mở thêm trách nhiệm đồng bộ và sửa dữ liệu lệch. Bởi vậy, các giải pháp phải được đánh giá theo **tính đúng, tải thực tế và khả năng vận hành**, chứ không chỉ theo độ ngắn của câu SQL.

## 10. Quy trình làm việc thực tế khi xây dựng chức năng có SQL

1. **Viết rõ quy tắc nghiệp vụ:** thực thể, quan hệ, tình huống không hợp lệ, tính lịch sử, mức đồng thời và kỳ vọng độ trễ.
2. **Thiết kế mô hình logic:** bảng, khóa, kiểu dữ liệu, nullability, ràng buộc; xác định dữ liệu nguồn và dữ liệu dẫn xuất.
3. **Viết và kiểm tra SQL với tình huống biên:** không có dòng, nhiều dòng, giá trị NULL, dữ liệu trùng, thời điểm cùng nhau, kết quả phân trang.
4. **Đặt ranh giới giao dịch:** thao tác nào phải thành công đồng thời, xung đột ghi sẽ xử lý ra sao, khi nào cần retry/idempotency.
5. **Đo với dữ liệu và tải đại diện:** xem kế hoạch, thống kê, thời gian và mức đồng thời; tạo chỉ mục dựa trên đường truy cập thực tế.
6. **Chuẩn bị vận hành:** migration có phiên bản, phân quyền, giới hạn kết nối, monitoring, cảnh báo, backup và diễn tập restore.
7. **Theo dõi sau khi phát hành:** so sánh với số liệu ban đầu, xác nhận tính đúng và điều chỉnh khi dữ liệu/mẫu truy cập thay đổi.

### Những ngộ nhận nên tránh

| Ngộ nhận | Điều cần hiểu |
| --- | --- |
| “Biết SELECT là biết hết SQL” | SQL còn quản lý cấu trúc, ràng buộc, giao dịch và quyền |
| “Mô hình chuẩn hóa thì chắc chắn truy vấn nhanh” | Chuẩn hóa bảo vệ tính nhất quán logic; tốc độ còn phụ thuộc truy vấn, chỉ mục và tải |
| “Tạo index cho mọi cột luôn tốt” | Index có chi phí ghi/lưu trữ và phải khớp mẫu truy cập |
| “COMMIT nhiều lệnh nghĩa là không còn race condition” | Vẫn phải chọn thao tác nguyên tử, mức cô lập và xử lý xung đột phù hợp |
| “Query chạy nhanh trên vài trăm dòng thì production cũng nhanh” | Kích thước, phân bố dữ liệu và số người dùng đồng thời có thể thay đổi kế hoạch lẫn thời gian |
| “Có replica thì không cần backup” | Replica có thể sao chép cả lỗi/xóa nhầm; cần backup và khả năng restore đã được kiểm chứng |
| “Thêm cột hoặc index là thay đổi không ảnh hưởng dịch vụ” | DDL có thể khóa, dùng nhiều tài nguyên hoặc yêu cầu phối hợp nhiều phiên bản ứng dụng |

## 11. Bài tập suy nghĩ theo tình huống

**Tình huống A — Giá bán thay đổi:** Sản phẩm hôm nay có giá 120.000, tuần trước khách đã đặt với giá 100.000. Một báo cáo doanh thu lấy giá từ products.current_price và nhân với quantity. Báo cáo sai ở đâu? Hãy xác định cột dữ liệu nào là nguồn đúng cho doanh thu lịch sử, và các vấn đề phát sinh nếu hệ thống có giảm giá, thuế hoặc nhiều loại tiền tệ.

**Tình huống B — Truy vấn lịch sử chậm:** Bảng orders tăng từ 1.000 lên 20 triệu dòng. Màn hình cần 20 đơn mới nhất theo customer_id, nhưng ứng dụng tải tất cả đơn rồi mới sắp xếp. Hãy mô tả cách sửa câu SQL, cách chọn chỉ mục ứng viên, dữ liệu đo cần thu thập và tác động có thể có đối với thao tác INSERT.

**Tình huống C — Hai yêu cầu đặt hàng cùng lúc:** Kho chỉ còn một sản phẩm. Hai giao dịch cùng kiểm tra rồi cập nhật tồn. Hãy giải thích vì sao tách SELECT và UPDATE mà không có phối hợp đồng thời có thể sai; đề xuất phép UPDATE có điều kiện hoặc một cơ chế khóa/giao dịch tương đương, và nêu cách xử lý khi không cập nhật được dòng nào.

**Tình huống D — Triển khai thay đổi schema:** Bảng orders có hàng triệu dòng và ứng dụng hiện tại đang hoạt động. Hãy lập kế hoạch thêm một trường mới bắt buộc mà vẫn hỗ trợ phiên bản ứng dụng cũ trong thời gian chuyển tiếp. Xác định bước migration dữ liệu, thời điểm siết ràng buộc, chỉ số giám sát và phương án phục hồi khi triển khai thất bại.

Các tình huống này cho thấy phạm vi của SQL không dừng ở câu lệnh: người dùng SQL cần hiểu **mô hình dữ liệu mà lệnh thao tác, kế hoạch mà DBMS thực thi và điều kiện vận hành để dữ liệu luôn đúng, truy cập đủ nhanh và có thể phục hồi**.

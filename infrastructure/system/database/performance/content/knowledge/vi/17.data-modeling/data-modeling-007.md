# Ràng buộc dữ liệu, kiểm tra tính duy nhất và chi phí thao tác ghi

Ràng buộc dữ liệu bảo vệ các quy tắc nghiệp vụ ngay tại cơ sở dữ liệu. PRIMARY KEY xác định bản ghi, UNIQUE ngăn các giá trị khóa bị trùng, FOREIGN KEY bảo đảm quan hệ tham chiếu, NOT NULL yêu cầu dữ liệu phải có giá trị và CHECK giới hạn miền giá trị hợp lệ. Các ràng buộc này giúp mọi ứng dụng cùng ghi vào một nguồn dữ liệu phải tuân theo một quy tắc nhất quán.

Mỗi ràng buộc cũng có chi phí khi INSERT, UPDATE hoặc DELETE. Hệ quản trị phải kiểm tra điều kiện, tra cứu khóa liên quan, cập nhật chỉ mục, ghi log và phối hợp khóa giữa các giao dịch đồng thời. Vì vậy, thiết kế mô hình dữ liệu cho DATABASE_PERFORMANCE cần cân bằng tính toàn vẹn với thông lượng ghi, độ trễ và khả năng mở rộng. Không nên bỏ ràng buộc để tăng tốc trước khi đo được nút thắt và xác định một cơ chế bảo vệ tương đương.

## 1. Vai trò của ràng buộc trong mô hình dữ liệu

Ràng buộc (constraint) mô tả điều kiện mà dữ liệu phải thỏa mãn. Khi một câu lệnh ghi vi phạm ràng buộc, hệ quản trị từ chối thao tác hoặc hoãn việc kiểm tra đến thời điểm được quy định nếu loại ràng buộc và cấu hình hỗ trợ.

Các loại thường gặp:

| Ràng buộc | Quy tắc được bảo vệ | Ví dụ |
|---|---|---|
| PRIMARY KEY | Mỗi hàng có định danh duy nhất và không NULL | orders.id |
| UNIQUE | Không có hai hàng trùng khóa theo quy tắc so sánh | users.email |
| FOREIGN KEY | Giá trị tham chiếu phải tồn tại ở bảng cha hoặc được phép NULL | orders.customer_id tham chiếu customers.id |
| NOT NULL | Cột bắt buộc có giá trị | orders.created_at |
| CHECK | Giá trị hoặc tổ hợp cột phải thỏa biểu thức | quantity > 0 |
| DEFAULT | Cung cấp giá trị khi câu lệnh không chỉ định cột | created_at mặc định thời điểm tạo |

DEFAULT thường là một thuộc tính của cột hơn là ràng buộc kiểm tra dữ liệu. Nó không tự ngăn ứng dụng ghi một giá trị không hợp lệ; NOT NULL, CHECK hoặc các ràng buộc khác mới xác định điều kiện hợp lệ.

Ràng buộc nên được đặt gần nơi lưu trữ dữ liệu có thẩm quyền. Kiểm tra ở giao diện hoặc tầng ứng dụng vẫn hữu ích để phản hồi sớm, nhưng không thay thế được kiểm tra ở database vì nhiều dịch vụ, batch job và tiến trình quản trị có thể cùng ghi vào bảng.

## 2. PRIMARY KEY và UNIQUE

### 2.1. PRIMARY KEY

PRIMARY KEY định danh duy nhất mỗi hàng. Một bảng chỉ có một primary key, nhưng khóa có thể gồm một cột hoặc nhiều cột.

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL
);
~~~

Khóa chính thường được triển khai bằng unique index và đồng thời yêu cầu các cột khóa không NULL. Các hệ quản trị có thể tổ chức dữ liệu vật lý khác nhau quanh primary key; ví dụ InnoDB dùng clustered primary key để tổ chức hàng, trong khi PostgreSQL lưu heap riêng và duy trì index.

### 2.2. UNIQUE

UNIQUE bảo đảm không có hai hàng có cùng giá trị khóa theo quy tắc so sánh của hệ quản trị, collation và kiểu dữ liệu:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_email UNIQUE (email);
~~~

Ràng buộc có thể gồm nhiều cột:

~~~sql
ALTER TABLE memberships
ADD CONSTRAINT uq_membership_tenant_user
UNIQUE (tenant_id, user_id);
~~~

Trong ví dụ, cùng một user chỉ có một membership trong một tenant, nhưng user đó có thể xuất hiện ở tenant khác. UNIQUE trên nhiều cột bảo vệ tính duy nhất của cả tổ hợp, không yêu cầu từng cột riêng lẻ phải duy nhất.

### 2.3. Unique constraint và unique index

Nhiều hệ quản trị dùng unique index để thực thi UNIQUE constraint. Cả hai có thể ngăn giá trị trùng, nhưng ý nghĩa DDL và khả năng quản trị khác nhau:

- UNIQUE constraint thể hiện quy tắc toàn vẹn trong mô hình dữ liệu.
- Unique index là cấu trúc truy cập có thuộc tính duy nhất.
- Một số engine cho phép constraint dùng một index đã có hoặc tạo index tự động.
- Một số tính năng như INCLUDE, biểu thức, predicate lọc hoặc tùy chọn online gắn với index hơn là constraint.

Khi quy tắc nghiệp vụ là duy nhất, ưu tiên khai báo constraint nếu hệ quản trị hỗ trợ đúng yêu cầu. Khi cần uniqueness chỉ trên một tập con hoặc trên biểu thức chuẩn hóa, có thể cần unique index chuyên biệt.

## 3. NULL và ngữ nghĩa của UNIQUE

NULL biểu thị giá trị chưa biết hoặc không có giá trị theo mô hình. NULL không giống chuỗi rỗng, số 0 hay một giá trị mặc định.

Hành vi UNIQUE với NULL khác nhau giữa các hệ quản trị:

- PostgreSQL mặc định xem các NULL là khác nhau trong unique constraint/index, do đó có thể có nhiều hàng NULL. PostgreSQL mới hơn còn hỗ trợ tùy chọn NULLS NOT DISTINCT để xem NULL như cùng một giá trị trong chỉ mục duy nhất.
- MySQL cho phép nhiều NULL trong unique index.
- SQL Server thường chỉ cho một giá trị NULL trong unique index một cột; unique index nhiều cột có quy tắc trên toàn bộ tổ hợp khóa.
- Oracle cho phép NULL trong unique key theo ngữ nghĩa riêng của Oracle; cần kiểm tra trường hợp khóa đơn, khóa ghép và các hàng có toàn bộ thành phần NULL.

Không nên dựa vào hành vi mặc định khi yêu cầu nghiệp vụ cần “mỗi người dùng chỉ có một email và email bắt buộc phải có”. Mô hình rõ ràng hơn là:

~~~sql
email VARCHAR(320) NOT NULL,
CONSTRAINT uq_customers_email UNIQUE (email)
~~~

Nếu NULL được phép và có ý nghĩa nghiệp vụ, hãy định nghĩa rõ có thể có bao nhiêu hàng NULL. Khi cần chỉ một hàng chưa gán giá trị, chọn cú pháp phù hợp với hệ quản trị hoặc dùng một mô hình dữ liệu khác đã được kiểm chứng.

### 3.1. Chuẩn hóa trước khi kiểm tra duy nhất

Email, tên đăng nhập hoặc mã nghiệp vụ có thể cần quy tắc so sánh không phân biệt hoa thường, bỏ khoảng trắng hoặc chuẩn hóa Unicode. UNIQUE chỉ áp dụng theo cách database so sánh giá trị; nó không tự biết quy tắc nghiệp vụ.

Ví dụ hai chuỗi User@Example.test và user@example.test có thể được xem là khác nhau trong một collation nhưng tương đương trong một collation khác. Cần thống nhất:

- Chuẩn hóa giá trị ở một nơi có thẩm quyền.
- Chọn collation hoặc biểu thức so sánh phù hợp.
- Nếu cần, lưu giá trị chuẩn hóa riêng và đặt UNIQUE trên giá trị đó.
- Kiểm tra dữ liệu lịch sử trước khi thêm constraint.

Không chuẩn hóa theo cách làm mất thông tin có ý nghĩa hoặc khiến hai định danh hợp lệ bị gộp nhầm.

## 4. FOREIGN KEY và tính toàn vẹn tham chiếu

FOREIGN KEY bảo đảm giá trị ở bảng con tham chiếu đến một khóa hợp lệ ở bảng cha:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);
~~~

Khi INSERT hoặc UPDATE hàng orders, database phải xác nhận customer_id tham chiếu một hàng customers tồn tại. Khi DELETE hoặc UPDATE khóa ở customers, database phải kiểm tra các hàng con và áp dụng hành vi đã khai báo.

Các hành vi phổ biến:

- RESTRICT hoặc NO ACTION: từ chối thay đổi nếu còn hàng con tham chiếu, tùy ngữ nghĩa và thời điểm kiểm tra của engine.
- CASCADE: lan truyền DELETE hoặc UPDATE khóa đến hàng con theo quy tắc khai báo.
- SET NULL: đặt khóa ngoại ở hàng con thành NULL khi hàng cha bị xóa hoặc khóa tham chiếu thay đổi.
- SET DEFAULT: đặt giá trị mặc định nếu hệ quản trị hỗ trợ và giá trị đó thỏa các ràng buộc khác.

Không chọn CASCADE chỉ để giảm số câu SQL của ứng dụng. Một thao tác xóa hàng cha có thể ảnh hưởng đến hàng triệu hàng con, tạo transaction lớn, khóa nhiều trang và phát sinh log đáng kể. Phải đánh giá quy mô quan hệ, thời gian transaction và khả năng khôi phục.

### 4.1. Chỉ mục ở phía bảng con

Khóa được tham chiếu ở bảng cha phải có tính duy nhất hoặc đáp ứng điều kiện được hệ quản trị cho phép. Nhưng không phải engine nào cũng tự tạo index trên cột FOREIGN KEY ở bảng con.

| Hệ quản trị | Tạo index phía bảng con khi khai báo FK |
|---|---|
| PostgreSQL | Không tự động tạo; thường cần tạo riêng |
| SQL Server | Không tự động tạo; nên đánh giá và tạo khi cần |
| MySQL InnoDB | Yêu cầu index phù hợp và có thể tự tạo nếu chưa có |
| Oracle Database | Không tự động tạo; nên đánh giá và tạo khi cần |

Ví dụ:

~~~sql
CREATE INDEX ix_orders_customer_id
ON orders (customer_id);
~~~

Index phía bảng con giúp database tìm nhanh các hàng tham chiếu khi kiểm tra hoặc xóa/cập nhật hàng cha. Nó cũng hỗ trợ truy vấn ứng dụng lọc đơn theo khách hàng. Tuy nhiên, mỗi index bổ sung làm tăng chi phí ghi orders; cần xét workload và các index hiện có để tránh trùng lặp.

## 5. CHECK và NOT NULL

### 5.1. NOT NULL

NOT NULL yêu cầu cột phải có giá trị:

~~~sql
CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL
);
~~~

NOT NULL thường có chi phí kiểm tra thấp so với một lookup hoặc cập nhật index, nhưng vẫn được kiểm tra trong mỗi thao tác ghi ảnh hưởng đến cột. Giá trị DEFAULT không thay thế NOT NULL: nếu câu lệnh cung cấp NULL tường minh, DEFAULT không tự động được dùng để thay thế.

### 5.2. CHECK

CHECK giới hạn giá trị hợp lệ:

~~~sql
CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(18, 2) NOT NULL,
    CONSTRAINT ck_order_items_positive_quantity
        CHECK (quantity > 0),
    CONSTRAINT ck_order_items_nonnegative_price
        CHECK (unit_price >= 0)
);
~~~

CHECK có thể áp dụng trên nhiều cột cùng một hàng:

~~~sql
CHECK (discount_amount <= gross_amount)
~~~

CHECK thông thường không dùng để kiểm tra dữ liệu ở bảng khác hoặc tổng hợp nhiều hàng. Nếu quy tắc cần tham chiếu bảng khác, hãy xem xét FOREIGN KEY, unique constraint, transaction logic hoặc cơ chế phù hợp của hệ quản trị.

Trong SQL, CHECK thường chỉ từ chối khi biểu thức FALSE; kết quả UNKNOWN do NULL có thể được chấp nhận. Vì vậy, nếu quantity không được NULL, phải khai báo thêm NOT NULL thay vì chỉ dựa vào CHECK (quantity > 0).

### 5.3. Chi phí của CHECK

Biểu thức CHECK đơn giản như quantity > 0 có chi phí nhỏ. Biểu thức phức tạp với hàm, chuyển đổi kiểu hoặc tính toán nhiều lần có thể tăng CPU cho mọi INSERT/UPDATE liên quan.

Hãy giữ CHECK:

- Xác định một quy tắc nghiệp vụ rõ ràng.
- Có biểu thức xác định và được hệ quản trị hỗ trợ.
- Không lặp lại tính toán đắt đỏ không cần thiết.
- Được kiểm tra với NULL và kiểu dữ liệu biên.

Nếu cùng một biểu thức được dùng ở nhiều nơi, cân nhắc chuẩn hóa quy tắc và tránh để ứng dụng, trigger và constraint diễn giải khác nhau.

## 6. Kiểm tra tính duy nhất khi nhiều giao dịch ghi đồng thời

Một lỗi thiết kế thường gặp là kiểm tra trùng ở ứng dụng bằng SELECT rồi mới INSERT:

~~~sql
SELECT id
FROM users
WHERE email = :email;

-- Nếu không tìm thấy thì INSERT.
INSERT INTO users (email)
VALUES (:email);
~~~

Hai request có thể chạy đồng thời:

1. Transaction A kiểm tra email chưa tồn tại.
2. Transaction B cũng kiểm tra và chưa thấy email.
3. Cả hai cùng cố INSERT.

Nếu không có UNIQUE constraint/index, cả hai có thể ghi thành công và tạo dữ liệu trùng. Nếu có unique index, database điều phối xung đột và chỉ cho phép một giao dịch tạo giá trị duy nhất; giao dịch còn lại phải chờ, nhận lỗi duplicate hoặc xử lý conflict theo cơ chế của engine.

Vì vậy, SELECT trước INSERT chỉ có thể cải thiện trải nghiệm hoặc tránh một số lần ghi thừa; nó không phải hàng rào bảo vệ tính duy nhất. UNIQUE constraint/index mới là cơ chế bảo đảm cuối cùng trong điều kiện cạnh tranh.

### 6.1. Xử lý lỗi duplicate đúng cách

Ứng dụng cần phân biệt lỗi vi phạm unique constraint với lỗi kết nối, timeout, deadlock hoặc lỗi dữ liệu khác. Khi hai người dùng cùng đăng ký email, có thể trả thông báo “email đã được sử dụng” thay vì coi mọi lỗi ghi là lỗi hệ thống.

Không bắt tất cả lỗi rồi bỏ qua. Việc bỏ qua có thể che giấu vi phạm constraint khác hoặc làm ứng dụng báo thành công trong khi dữ liệu không được ghi.

### 6.2. Upsert

Upsert kết hợp insert và xử lý khi khóa đã tồn tại. Cơ chế cụ thể khác nhau:

PostgreSQL:

~~~sql
INSERT INTO users (email, display_name)
VALUES (:email, :display_name)
ON CONFLICT (email)
DO UPDATE SET display_name = EXCLUDED.display_name;
~~~

MySQL:

~~~sql
INSERT INTO users (email, display_name)
VALUES (?, ?) AS incoming
ON DUPLICATE KEY UPDATE
    display_name = incoming.display_name;
~~~

SQL Server có thể dùng UPDATE rồi INSERT trong transaction với khóa phù hợp, hoặc một mẫu khác đã được kiểm thử theo isolation và unique index. Oracle hỗ trợ MERGE. Cú pháp và ngữ nghĩa khác nhau giữa phiên bản; cần kiểm tra cách xử lý nhiều unique key, trigger, affected-row count và deadlock.

Upsert không loại bỏ contention. Nếu nhiều request cùng cập nhật một khóa nóng, chúng vẫn có thể phải chờ nhau. Nếu mỗi lần conflict đều UPDATE dù giá trị không đổi, engine vẫn có thể tạo log, trigger và index maintenance không cần thiết. Chỉ cập nhật khi dữ liệu thực sự khác nếu có thể làm điều đó an toàn.

## 7. Chi phí ghi do constraint và index

Một thao tác INSERT có thể phải thực hiện nhiều công việc:

1. Kiểm tra kiểu dữ liệu, NOT NULL và CHECK.
2. Kiểm tra unique key để tránh trùng.
3. Kiểm tra FOREIGN KEY và khóa cha có tồn tại.
4. Ghi hàng vào cấu trúc lưu trữ.
5. Thêm entry vào từng index liên quan.
6. Ghi WAL/redo log hoặc cơ chế log tương đương.
7. Lấy và giữ khóa cần thiết để bảo vệ thay đổi.
8. Cập nhật thống kê hoặc cấu trúc phụ theo cơ chế engine.

DELETE phải loại bỏ entry khỏi các index và kiểm tra tham chiếu từ bảng con. UPDATE cột khóa có thể cần xóa entry cũ và tạo entry mới; UPDATE cột không nằm trong index có thể ít tốn kém hơn, tùy engine và tổ chức dữ liệu.

### 7.1. Write amplification

Write amplification là hiện tượng một thay đổi logic của ứng dụng tạo ra nhiều thao tác ghi vật lý hoặc log ở tầng lưu trữ. Một hàng được INSERT có thể tạo entry trong nhiều index; mỗi entry có thể gây page split, dirty page và log record.

Nếu bảng có nhiều index gần giống nhau, chi phí ghi tăng dù không phải truy vấn nào cũng dùng tất cả index. Vì vậy, tối ưu đọc bằng cách thêm index cần được cân đối với tốc độ ghi và dung lượng.

Các yếu tố làm chi phí tăng:

- Nhiều index trên cùng bảng.
- Key rộng, nhiều cột hoặc cột có giá trị lớn.
- Giá trị khóa phân bố khiến insert tập trung vào một vùng leaf page.
- UPDATE thường xuyên các cột được lập chỉ mục.
- CHECK phức tạp hoặc FK phải tra cứu nhiều dữ liệu.
- CASCADE tác động đến tập hàng con lớn.
- Unique check trên khóa nóng có nhiều giao dịch cạnh tranh.
- Transaction ghi kéo dài và commit nhiều thay đổi cùng lúc.

### 7.2. Page split và khóa nóng

Với B-tree, chèn khóa vào giữa hoặc một vùng đã đầy có thể làm page split. Split tạo thêm ghi, log và thay đổi cấu trúc index. Khóa tăng tuần tự có thể giảm một số kiểu split giữa cây nhưng lại tập trung insert vào trang cuối, gây latch/contention trên một vùng nóng ở một số engine và tải.

Không có một kiểu khóa tự động tốt nhất cho mọi workload. Cần xem phân bố insert, page split, latch wait, lock wait và cấu trúc index cụ thể trước khi thay đổi thứ tự khóa hoặc chiến lược sinh ID.

## 8. Chi phí và hành vi của từng loại ràng buộc khi ghi

| Loại ràng buộc | INSERT | UPDATE | DELETE |
|---|---|---|---|
| PRIMARY KEY | Kiểm tra duy nhất, không NULL; thêm index entry | Kiểm tra khóa mới và cập nhật index | Xóa index entry |
| UNIQUE | Kiểm tra trùng, có thể chờ giao dịch cùng khóa | Kiểm tra giá trị mới và cập nhật index | Xóa index entry |
| FOREIGN KEY | Tra cứu khóa cha | Kiểm tra nếu khóa ngoại thay đổi | Kiểm tra hàng con khi xóa hàng cha |
| NOT NULL | Kiểm tra cột không NULL | Kiểm tra nếu cột được cập nhật | Không kiểm tra quan hệ xóa |
| CHECK | Đánh giá biểu thức trên hàng mới | Đánh giá lại khi cột liên quan thay đổi | Thường không cần đánh giá hàng đã xóa |
| DEFAULT | Tính giá trị nếu cột được bỏ qua | Chỉ áp dụng theo câu lệnh/cách cập nhật tương ứng | Không áp dụng |

Đây là mô hình khái quát. Engine có thể tối ưu bỏ qua một số kiểm tra khi không có cột liên quan thay đổi, hoặc trì hoãn kiểm tra theo constraint mode. Chi phí thực tế còn phụ thuộc index, cache, transaction, isolation và mức độ đồng thời.

## 9. Deferrable constraints và thời điểm kiểm tra

Một số hệ quản trị hỗ trợ constraint có thể hoãn kiểm tra đến cuối transaction. Ví dụ PostgreSQL cho phép khai báo một số UNIQUE, FOREIGN KEY và constraint phù hợp là DEFERRABLE:

~~~sql
CREATE TABLE account_links (
    id BIGINT PRIMARY KEY,
    account_code VARCHAR(40),
    CONSTRAINT uq_account_code
        UNIQUE (account_code)
        DEFERRABLE INITIALLY DEFERRED
);
~~~

Trong transaction, ứng dụng có thể tạm thời đi qua trạng thái vi phạm rồi đưa dữ liệu về trạng thái hợp lệ trước COMMIT. Điều này hữu ích cho một số thao tác hoán đổi khóa hoặc cập nhật quan hệ nhiều bước.

Deferrable không có nghĩa bỏ kiểm tra; database vẫn phải xác nhận trước khi commit. Nó cũng không được mọi hệ quản trị hỗ trợ giống nhau. SQL Server và MySQL không cung cấp cùng mô hình deferrable constraint như PostgreSQL. Chỉ dùng khi thật sự cần và hiểu tác động đến lỗi commit, transaction và kế hoạch cập nhật.

## 10. Index hỗ trợ kiểm tra FOREIGN KEY và CASCADE

Khi xóa một khách hàng, database cần xác định có đơn hàng nào tham chiếu khách hàng đó không. Nếu orders.customer_id không có index, engine có thể phải quét bảng orders lớn để tìm hàng liên quan. Với bảng hàng chục triệu đơn, thao tác xóa hoặc cập nhật khóa cha có thể tốn thời gian và giữ khóa lâu.

Chỉ mục:

~~~sql
CREATE INDEX ix_orders_customer_id
ON orders (customer_id);
~~~

có thể giúp kiểm tra tham chiếu và các truy vấn theo customer_id nhanh hơn. Nếu đã có index ghép bắt đầu bằng customer_id, có thể không cần index đơn riêng; hãy kiểm tra index prefix và workload trước khi thêm.

CASCADE có thể làm một thao tác ở bảng cha kích hoạt nhiều thao tác ở bảng con. Hãy đo số hàng bị ảnh hưởng, log volume, lock duration và replication lag. Với xóa dữ liệu lớn, một quy trình batch có kiểm soát đôi khi dễ vận hành hơn một transaction CASCADE rất lớn, nhưng phải giữ nguyên tính toàn vẹn trong suốt quy trình.

## 11. Ràng buộc có điều kiện và tính duy nhất theo nghiệp vụ

Có trường hợp chỉ cần duy nhất trong một tập con, chẳng hạn email chỉ duy nhất đối với tài khoản đang hoạt động:

~~~sql
CREATE UNIQUE INDEX ux_users_active_email
ON users (email)
WHERE deleted_at IS NULL;
~~~

Đây là ví dụ PostgreSQL. SQL Server hỗ trợ filtered unique index với predicate tương ứng. MySQL không có partial unique index native theo WHERE; có thể mô hình hóa bằng generated column hoặc thiết kế khác phù hợp phiên bản. Oracle có thể dùng function-based unique index với biểu thức điều kiện.

Khi dùng unique partial/filtered index, phải bảo đảm mọi truy vấn và thao tác ghi hiểu đúng tập hàng được bảo vệ. Nếu tài khoản chuyển từ deleted sang active, thao tác UPDATE có thể va chạm với một email đang được dùng bởi tài khoản active khác và phải bị từ chối.

Không dùng soft delete để lách uniqueness mà không xác định quy tắc khôi phục. Nếu khôi phục tài khoản cũ có cùng email với tài khoản mới, hệ thống cần quy định rõ tài khoản nào được giữ email và cách xử lý xung đột.

## 12. Thêm constraint vào bảng đã có dữ liệu

Thêm UNIQUE, CHECK hoặc FOREIGN KEY vào bảng lớn có thể cần quét dữ liệu, tạo index và lấy khóa DDL. Trước khi triển khai, phải xác định dữ liệu hiện tại có thỏa quy tắc không.

### 12.1. Tìm duplicate trước khi thêm UNIQUE

Ví dụ:

~~~sql
SELECT email, COUNT(*) AS duplicate_count
FROM users
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Nếu có NULL, collation hoặc chuẩn hóa giá trị, truy vấn kiểm tra phải mô phỏng đúng quy tắc unique dự kiến. Không chỉ so sánh chuỗi thô nếu index sẽ dùng collation hoặc biểu thức khác.

### 12.2. Tìm orphan trước khi thêm FOREIGN KEY

~~~sql
SELECT o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
    ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Kết quả là các giá trị tham chiếu không có hàng cha. Cần xử lý dữ liệu mồ côi theo quy tắc nghiệp vụ trước khi thêm FK.

### 12.3. Tìm hàng vi phạm CHECK

~~~sql
SELECT id, quantity
FROM order_items
WHERE quantity <= 0
   OR quantity IS NULL;
~~~

Truy vấn kiểm tra cần bao gồm NULL nếu cột sẽ có NOT NULL. Một CHECK quantity > 0 có thể không từ chối UNKNOWN do NULL, vì vậy phải kiểm tra riêng.

### 12.4. Tránh khoảng trống giữa kiểm tra và tạo constraint

Nếu ứng dụng vẫn ghi dữ liệu trong khi chạy truy vấn tìm duplicate, một hàng trùng mới có thể xuất hiện sau bước kiểm tra nhưng trước khi constraint được tạo. Việc triển khai phải có chiến lược chặn ghi, khóa phù hợp, tạo index/constraint online hoặc xử lý lỗi khi build tùy khả năng của engine.

Không coi truy vấn kiểm tra trước là bảo đảm cuối cùng. Constraint chỉ bảo vệ sau khi được tạo và xác nhận hợp lệ. Quy trình migration cần tính đến concurrency, DDL lock, thời gian build, rollback và khả năng retry.

## 13. Bulk load và kiểm soát constraint

Nạp dữ liệu hàng loạt có thể chịu chi phí đáng kể từ index và constraint. Một số engine cung cấp chế độ bulk load, deferred validation hoặc tùy chọn tạo index sau khi nạp. Tuy nhiên, tắt constraint hoặc bỏ qua kiểm tra có thể đưa dữ liệu sai vào hệ thống và tạo ra khoảng thời gian không được bảo vệ.

Nếu cần tối ưu bulk load:

1. Xác định có thể nạp vào staging table riêng hay không.
2. Kiểm tra định dạng, NULL, duplicate và tham chiếu trong staging.
3. Nạp theo batch với transaction và kích thước phù hợp.
4. Tạo hoặc xác nhận index/constraint theo khả năng của engine.
5. Chạy truy vấn tìm dữ liệu vi phạm trước khi chuyển sang bảng chính.
6. Chỉ chuyển dữ liệu sau khi kiểm tra toàn vẹn thành công.
7. Ghi lại thời gian nạp, log, replication lag và thời gian build index.

Không dùng cơ chế bỏ qua duplicate hoặc tắt FK như một cách xử lý mặc định. Nếu bỏ qua một hàng lỗi, cần ghi nhận hàng đó, nguyên nhân và quyết định nghiệp vụ; không để dữ liệu mất âm thầm.

## 14. Đo chi phí thao tác ghi

Để đánh giá một constraint hoặc index có làm giảm thông lượng ghi hay không, cần đo workload trước và sau thay đổi trong điều kiện tương đương.

Các chỉ số nên theo dõi:

- Throughput INSERT/UPDATE/DELETE theo giây.
- p50, p95 và p99 latency của thao tác ghi.
- Tỷ lệ lỗi unique/FK/CHECK và tỷ lệ conflict hợp lệ.
- Lock wait, deadlock, latch wait hoặc wait event liên quan.
- CPU, logical reads, physical reads và I/O ghi.
- WAL/redo log volume, checkpoint và replication lag.
- Kích thước index, số page split và mức sử dụng cache.
- Thời gian commit và kích thước transaction.
- Thời gian build, reindex, vacuum/purge hoặc bảo trì liên quan.

### 14.1. Benchmark có kiểm soát

Tạo workload đại diện:

- INSERT hàng mới với phân bố khóa thực tế.
- UPDATE cột không có index.
- UPDATE cột nằm trong unique/index key.
- Thao tác làm giá trị đi vào hoặc ra khỏi filtered/partial index.
- DELETE hàng cha có nhiều hàng con.
- Nhiều giao dịch cùng ghi một khóa hoặc cùng một vùng dữ liệu.
- Bulk load theo batch.

Chạy cả trường hợp cache nóng và tải đồng thời thực tế. Dùng cùng dữ liệu, số client, transaction size và cấu hình để so sánh. Không kết luận từ một câu INSERT đơn lẻ trong môi trường nhàn rỗi.

### 14.2. Phân biệt lỗi nghiệp vụ và tranh chấp

Unique violation có thể là kết quả hợp lệ khi hai request cùng tạo một định danh. Lock timeout hoặc deadlock là vấn đề phối hợp giao dịch. Không gộp tất cả thành “database chậm”.

Ghi lại loại lỗi, constraint name, thời gian chờ và transaction liên quan. Retry chỉ phù hợp với một số lỗi tạm thời như deadlock hoặc serialization failure; retry duplicate thường không làm thao tác INSERT thành công nếu dữ liệu đã tồn tại. Upsert hoặc phản hồi conflict phải được thiết kế theo nghiệp vụ.

## 15. Ví dụ thiết kế bảng tài khoản

Yêu cầu:

- Mỗi tài khoản có id duy nhất.
- Email bắt buộc và không trùng trong nhóm tài khoản đang hoạt động.
- Trạng thái phải thuộc tập giá trị đã định nghĩa.
- Mỗi đơn hàng phải tham chiếu một khách hàng tồn tại.
- Số lượng hàng trong đơn phải lớn hơn 0.

Một thiết kế minh họa cho PostgreSQL:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    status VARCHAR(20) NOT NULL,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT ck_customers_status
        CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED'))
);

CREATE UNIQUE INDEX ux_customers_active_email
ON customers (lower(email))
WHERE deleted_at IS NULL;

CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(id)
);

CREATE INDEX ix_orders_customer_id
ON orders (customer_id);

CREATE TABLE order_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Điểm cần đánh giá:

1. Primary key tạo đường định danh cho từng hàng.
2. Email không NULL; unique partial index áp dụng duy nhất trên email chuẩn hóa của hàng chưa xóa logic.
3. CHECK bảo vệ tập trạng thái hợp lệ; NOT NULL ngăn trạng thái thiếu.
4. FK orders.customer_id ngăn đơn tham chiếu khách hàng không tồn tại.
5. Index orders.customer_id hỗ trợ tìm hàng con khi kiểm tra tham chiếu và truy vấn theo khách hàng.
6. CHECK quantity > 0 kết hợp NOT NULL để không cho số lượng thiếu.
7. Mỗi index tăng chi phí ghi; cần đo số đơn, tỷ lệ xóa logic, tần suất đổi trạng thái và truy vấn thực tế trước khi quyết định giữ mọi index.

DDL trên minh họa PostgreSQL; identity, TIMESTAMPTZ, partial index và biểu thức lower(email) cần điều chỉnh theo hệ quản trị khác. Nếu quy tắc email không phân biệt hoa thường, cần bảo đảm chuẩn hóa và collation thống nhất với ứng dụng.

## 16. Quy trình thiết kế và tối ưu ràng buộc

1. **Ghi rõ quy tắc nghiệp vụ:** định danh nào phải duy nhất, cột nào bắt buộc, quan hệ nào phải tồn tại và miền giá trị hợp lệ.
2. **Chọn nơi bảo vệ:** dùng PK, UNIQUE, FK, NOT NULL hoặc CHECK khi quy tắc có thể biểu diễn trực tiếp trong database.
3. **Xác định NULL semantics:** quyết định NULL có được phép và uniqueness với NULL cần hành vi nào.
4. **Kiểm tra kiểu dữ liệu và collation:** bảo đảm so sánh khóa phản ánh đúng quy tắc nghiệp vụ.
5. **Thiết kế index hỗ trợ:** xem unique key, FK phía bảng con, truy vấn đọc và index hiện có.
6. **Kiểm tra dữ liệu hiện tại:** tìm duplicate, orphan, NULL và hàng vi phạm CHECK.
7. **Lập kế hoạch migration:** xem DDL lock, online/concurrent build, transaction, replication và khả năng rollback.
8. **Đo baseline ghi:** throughput, latency, log volume, lock wait, deadlock và kích thước index.
9. **Thử nghiệm concurrency:** hai giao dịch cùng ghi một unique key, cập nhật khóa cha, cascade và upsert.
10. **Đo lại sau thay đổi:** dùng cùng workload, dữ liệu và mức concurrency.
11. **Xác minh toàn vẹn:** thử cả thao tác hợp lệ và không hợp lệ, xác nhận database từ chối trường hợp vi phạm.
12. **Theo dõi vận hành:** giám sát xung đột, log, index growth, lock và replication lag.

## 17. Các sai lầm thường gặp

- **Chỉ kiểm tra uniqueness ở ứng dụng:** hai giao dịch đồng thời vẫn có thể tạo duplicate.
- **Bỏ UNIQUE để tránh lỗi ghi:** dữ liệu trùng có thể lan sang các bảng và báo cáo khác.
- **Không khai báo NOT NULL cùng CHECK:** UNKNOWN do NULL có thể không bị CHECK từ chối.
- **Giả định mọi hệ quản trị xử lý NULL trong UNIQUE giống nhau:** hành vi có khác biệt.
- **Không tạo index phía bảng con cho FK:** kiểm tra và xóa hàng cha có thể quét bảng con lớn.
- **Tạo index trùng lặp:** làm tăng write amplification mà không thêm lợi ích đọc đáng kể.
- **Đặt quá nhiều cột vào unique key:** làm key rộng, tăng chi phí và có thể thay đổi ngữ nghĩa duy nhất.
- **Dùng CASCADE cho thao tác xóa rất lớn mà không đo:** transaction có thể giữ khóa và tạo log quá lâu.
- **Dùng SELECT rồi INSERT như một giao dịch nguyên tử:** vẫn có race condition nếu không có constraint hoặc khóa phù hợp.
- **Coi upsert là không có contention:** nhiều request cùng khóa vẫn phải phối hợp.
- **Tắt constraint khi bulk load mà không xác thực lại:** dữ liệu sai có thể lọt vào bảng chính.
- **Thêm constraint vào bảng lớn mà không xem DDL lock:** migration có thể ảnh hưởng ứng dụng đang chạy.
- **Chỉ đo latency SELECT:** bỏ qua chi phí INSERT, UPDATE, DELETE và log.

## 18. Checklist ràng buộc và chi phí ghi

- [ ] Primary key định danh mỗi hàng và không NULL.
- [ ] UNIQUE phản ánh đúng phạm vi và quy tắc so sánh nghiệp vụ.
- [ ] NULL semantics của unique key đã được kiểm tra trên đúng hệ quản trị.
- [ ] NOT NULL được khai báo cho dữ liệu bắt buộc.
- [ ] CHECK có biểu thức rõ ràng và đã kiểm tra trường hợp NULL.
- [ ] FOREIGN KEY bảo vệ quan hệ giữa bảng cha và bảng con.
- [ ] Đã đánh giá index ở phía bảng con và index hiện có.
- [ ] Hành vi RESTRICT/NO ACTION/CASCADE/SET NULL được chọn có chủ đích.
- [ ] Đã kiểm tra race condition khi nhiều transaction cùng ghi khóa.
- [ ] Upsert và xử lý duplicate phân biệt lỗi nghiệp vụ với lỗi tạm thời.
- [ ] Đã đo số lượng index, kích thước, write amplification và page split.
- [ ] Đã đo throughput, p95/p99 latency, log volume và lock waits.
- [ ] Dữ liệu lịch sử đã được kiểm tra trước khi thêm constraint.
- [ ] Migration có kế hoạch DDL lock, build index, rollback và replication.
- [ ] Bulk load có bước xác thực dữ liệu trước khi đưa vào bảng chính.
- [ ] Đã thử nghiệm cả workload đọc, ghi và concurrency đại diện.

Ràng buộc là hàng rào bảo vệ tính toàn vẹn của mô hình dữ liệu, còn unique index và các index liên quan cũng là cấu trúc phục vụ truy cập. Chúng có chi phí kiểm tra, cập nhật, log và phối hợp giao dịch trên mỗi lần ghi. Thiết kế tốt bắt đầu từ quy tắc nghiệp vụ rõ ràng, chọn đúng ràng buộc và index cần thiết, sau đó đo cả độ trễ ghi lẫn khả năng bảo vệ dữ liệu dưới tải đồng thời.

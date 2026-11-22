# Quan hệ một–một, một–nhiều và nhiều–nhiều

## 1. Vì sao phải thiết kế quan hệ giữa các thực thể?

Một ứng dụng Java bán hàng thường phải lưu nhiều loại dữ liệu: khách hàng, hồ sơ bổ sung của khách hàng, đơn hàng và sản phẩm. Nếu lưu tất cả vào một bảng lớn, thông tin khách hàng bị lặp ở mỗi dòng hàng; thay đổi số điện thoại dễ gây không nhất quán, còn việc tính số đơn hàng hoặc số sản phẩm cần nhiều thao tác sửa dữ liệu phức tạp.

Một cách thiết kế phù hợp là tách những sự thật có vòng đời và ý nghĩa khác nhau thành các bảng, rồi diễn đạt **mối quan hệ** bằng khóa và ràng buộc. Ba dạng quan hệ phổ biến nhất là:

- **Một–một (1:1):** một bản ghi phía A liên kết với nhiều nhất một bản ghi phía B, và ngược lại.
- **Một–nhiều (1:N):** một bản ghi phía A có thể liên kết với nhiều bản ghi phía B, nhưng mỗi B liên kết với tối đa một A theo quan hệ đang xét.
- **Nhiều–nhiều (N:M):** một bản ghi phía A có thể liên kết với nhiều B, đồng thời một B có thể liên kết với nhiều A.

Bài học thuộc chương **Định danh và quan hệ** của học phần **DATA_PERSISTENCE_FUNDAMENTALS**. Trong bức tranh lưu trữ dữ liệu bền vững của Java, thiết kế quan hệ ảnh hưởng trực tiếp tới lược đồ, tính toàn vẹn, cách truy vấn và tạo chỉ mục, giao dịch, kiểm soát đồng thời, cũng như cách ánh xạ dữ liệu sang các đối tượng Java.

Sau bài học, người học có thể:

1. Phân biệt **bội số tối đa** (1 hay nhiều) và **tính bắt buộc** (0 hay 1 trở lên) ở từng đầu quan hệ.
2. Biểu diễn ba dạng quan hệ bằng **PRIMARY KEY**, **FOREIGN KEY**, **UNIQUE**, **NOT NULL** và bảng trung gian.
3. Viết các truy vấn **JOIN** phù hợp, xử lý tình huống một hàng cha tạo ra nhiều hàng kết quả.
4. Chọn chính sách xóa, cập nhật và kiểm soát dữ liệu lịch sử.
5. Tránh những lỗi ánh xạ Java/JPA hoặc truy vấn JDBC thường gặp khi làm việc với quan hệ.

## 2. Đọc đúng bội số: 1:1, 1:N, N:M chưa nói hết câu chuyện

Khi nói “khách hàng có nhiều đơn hàng”, cần hỏi rõ:

- Một khách hàng có **bắt buộc** phải có ít nhất một đơn hàng không?
- Một đơn hàng có **bắt buộc** phải thuộc một khách hàng không?
- Đơn hàng có thể đồng thời thuộc hai khách hàng không?
- Một liên kết có được thay đổi theo thời gian hoặc cần giữ lịch sử không?

Để trả lời, mô hình thường ghi thêm **bội số tối thiểu và tối đa** ở mỗi đầu:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **0..1** | Không có hoặc có đúng một | Khách hàng có thể chưa tạo hồ sơ chi tiết |
| **1..1** | Bắt buộc có đúng một | Mỗi đơn hàng phải thuộc một khách hàng |
| **0..\*** | Không có hoặc có nhiều | Khách hàng mới có thể chưa có đơn nào |
| **1..\*** | Phải có ít nhất một; có thể có nhiều | Đơn đã xác nhận phải có ít nhất một dòng hàng, nếu nghiệp vụ quy định |

**1:N không tự động có nghĩa “mỗi A phải có N bản ghi B”.** Trong nhiều ứng dụng, quan hệ khách hàng–đơn hàng có dạng một khách hàng **0..N** đơn hàng; một đơn hàng **đúng một** khách hàng. Những con số này là **quy tắc nghiệp vụ**, còn ràng buộc SQL là công cụ thực thi một phần hoặc toàn bộ quy tắc đó.

### 2.1. Sơ đồ ví dụ xuyên suốt

~~~mermaid
erDiagram
    CUSTOMER ||--o| CUSTOMER_PROFILE : "co ho so"
    CUSTOMER ||--o{ PURCHASE_ORDER : "dat"
    PURCHASE_ORDER ||--o{ ORDER_ITEM : "gom"
    PRODUCT ||--o{ ORDER_ITEM : "xuat hien trong"

    CUSTOMER {
        bigint customer_id PK
        varchar full_name
        varchar email UK
    }
    CUSTOMER_PROFILE {
        bigint customer_id PK, FK
        varchar phone
        date birth_date
    }
    PURCHASE_ORDER {
        bigint order_id PK
        bigint customer_id FK
        timestamptz ordered_at
        varchar status
    }
    PRODUCT {
        bigint product_id PK
        varchar sku UK
        numeric current_price
    }
    ORDER_ITEM {
        bigint order_id PK, FK
        bigint product_id PK, FK
        integer quantity
        numeric unit_price
    }
~~~

Đọc sơ đồ từ trái qua phải theo nghiệp vụ:

- **Customer ↔ CustomerProfile** là **1:0..1**: một khách hàng có thể không có hồ sơ, nhưng mỗi hồ sơ thuộc đúng một khách hàng.
- **Customer → PurchaseOrder** là **1:N**: một khách hàng có thể có nhiều đơn; mỗi đơn thuộc đúng một khách.
- **PurchaseOrder ↔ Product** là **N:M** thông qua **OrderItem**: một đơn gồm nhiều sản phẩm và một sản phẩm xuất hiện trong nhiều đơn khác nhau.

Sơ đồ ER mô tả các ràng buộc dự định. Chỉ khi lược đồ và quy trình ghi thực sự kiểm soát được chúng, dữ liệu mới được bảo đảm tuân theo mô hình.

## 3. Ba yếu tố nền tảng: định danh, khóa ngoại, ràng buộc duy nhất

### 3.1. PRIMARY KEY định danh hàng

**Khóa chính (PRIMARY KEY)** phân biệt từng hàng trong một bảng; giá trị khóa chính phải duy nhất và không NULL.

Ví dụ **customer.customer_id = 42** định danh một khách hàng cụ thể. Tên hiển thị hoặc số điện thoại thường không thích hợp làm khóa chính vì có thể thay đổi hoặc không bảo đảm duy nhất.

Một khóa chính có thể gồm một cột hoặc nhiều cột; **(order_id, product_id)** trong **order_item** là khóa ghép nếu nghiệp vụ quy định mỗi sản phẩm chỉ xuất hiện **một dòng** trong mỗi đơn.

### 3.2. FOREIGN KEY biểu diễn liên kết

**Khóa ngoại (FOREIGN KEY)** yêu cầu giá trị tham chiếu khớp một khóa được phép tham chiếu ở bảng khác. Ví dụ, **purchase_order.customer_id** tham chiếu **customer.customer_id**.

Nếu đơn hàng chứa **customer_id = 999** mà khách 999 không tồn tại, cơ sở dữ liệu từ chối thao tác ghi khi ràng buộc FK có hiệu lực. Đây là **toàn vẹn tham chiếu**.

Khóa ngoại có thể nằm ở bảng “con” của một quan hệ 1:N, hoặc nằm ở bảng liên kết của quan hệ N:M. **Chỉ tạo FOREIGN KEY chưa đủ để xác định một quan hệ là 1:1**, vì nhiều hàng ở bảng tham chiếu có thể cùng trỏ về một hàng đích.

### 3.3. UNIQUE kiểm soát bội số tối đa

Muốn mỗi khách hàng có nhiều nhất một hồ sơ, cột **customer_profile.customer_id** phải có tính duy nhất. Nếu cột này đồng thời là **PRIMARY KEY**, tính duy nhất đã được bảo đảm; không cần thêm UNIQUE trùng lặp.

Với mô hình khác dùng **customer_profile.profile_id** làm khóa chính riêng, cột **customer_profile.customer_id** cần **UNIQUE** để vẫn giữ quan hệ 1:1.

Cần chú ý: trong nhiều hệ quản trị SQL, một ràng buộc UNIQUE thông thường cho phép nhiều giá trị NULL. Vì vậy nếu yêu cầu “mỗi hồ sơ bắt buộc phải thuộc đúng một khách”, phải dùng thêm **NOT NULL** hoặc để cột đó là PRIMARY KEY. Chi tiết xử lý NULL của UNIQUE khác nhau theo hệ quản trị và cấu hình.

## 4. Quan hệ một–một (1:1)

### 4.1. Khi nào dùng?

Ví dụ khách hàng (**customer**) có thể có một hồ sơ chi tiết (**customer_profile**) chứa số điện thoại và ngày sinh. Tách hai bảng có thể hữu ích khi:

- Dữ liệu hồ sơ là **tùy chọn**: khách hàng vẫn được tạo tài khoản mà không điền thông tin bổ sung.
- Hồ sơ có **quyền truy cập, vòng đời hoặc chính sách giữ dữ liệu** khác thông tin tài khoản.
- Hồ sơ được quản lý bởi một thành phần hoặc quá trình nghiệp vụ riêng.

Tuy nhiên, không phải cứ các cột có vẻ khác loại thì nên tách 1:1. Nếu chúng luôn được tạo, đọc và thay đổi cùng lúc, có thể để cùng một bảng để giảm độ phức tạp JOIN. Thiết kế cần dựa trên vòng đời và ràng buộc của dữ liệu.

### 4.2. Cách phổ biến: khóa chính đồng thời là khóa ngoại

~~~sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name   VARCHAR(200) NOT NULL,
    email       VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE customer_profile (
    customer_id BIGINT PRIMARY KEY
                REFERENCES customer(customer_id) ON DELETE CASCADE,
    phone       VARCHAR(30),
    birth_date  DATE
);
~~~

Ở bảng **customer_profile**, **customer_id** giữ hai vai trò:

1. **PRIMARY KEY**: không thể có hai hồ sơ cùng customer_id.
2. **FOREIGN KEY**: không thể có hồ sơ của khách hàng không tồn tại.

Kết quả là: mỗi hồ sơ có **đúng một** khách hàng và mỗi khách hàng có **tối đa một** hồ sơ. Khách hàng vẫn có thể **không có** hồ sơ, vì cấu trúc hiện tại không ép phải tồn tại hàng tương ứng ở bảng profile.

**ON DELETE CASCADE** ở quan hệ này nghĩa là khi xóa một khách hàng thành công, hồ sơ của khách đó cũng được xóa. Trong hệ thống thực, cần cân nhắc chính sách lưu giữ dữ liệu; không nên dùng CASCADE theo thói quen.

### 4.3. Biến thể: khóa ngoại duy nhất, tách khỏi khóa chính

Một bảng hồ sơ cũng có thể mang **profile_id** riêng, và áp dụng:

~~~sql
-- Minh họa phần định nghĩa cần có trong một biến thể lược đồ
profile_id  BIGINT PRIMARY KEY,
customer_id BIGINT NOT NULL UNIQUE REFERENCES customer(customer_id)
~~~

Cách này vẫn bảo đảm **tối đa một hồ sơ cho mỗi khách hàng**, nhưng mỗi hồ sơ có định danh độc lập. Đoạn trên là các khai báo cột minh họa, không phải một câu lệnh SQL hoàn chỉnh để chạy nguyên trạng.

**Khi nào cần 1:1 bắt buộc ở cả hai phía?** Nếu ngay khi tạo khách hàng phải có hồ sơ, chỉ FK từ profile tới customer chưa bảo đảm điều đó. Có thể hợp nhất hai bảng, hoặc kiểm soát quá trình tạo hai hàng trong cùng giao dịch và dùng cơ chế ràng buộc bổ sung phù hợp hệ quản trị. Hai bảng với FK riêng không tự động giải quyết bài toán bắt buộc hai chiều và có thể phát sinh vòng phụ thuộc lúc chèn.

### 4.4. Truy vấn 1:1 với LEFT JOIN

~~~sql
SELECT c.customer_id, c.full_name, p.phone, p.birth_date
FROM customer AS c
LEFT JOIN customer_profile AS p
       ON p.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

**LEFT JOIN** vẫn giữ khách hàng chưa có hồ sơ; các cột của **p** khi đó là NULL. Nếu thay bằng **INNER JOIN**, kết quả chỉ còn khách hàng đã tạo profile.

Cần phân biệt “không có hàng profile” với “có hàng profile nhưng **phone** bằng NULL”: hai trường hợp có ý nghĩa khác nhau, dù cùng có thể trả về NULL ở cột phone. Muốn kiểm tra sự tồn tại của hồ sơ, nên xét **p.customer_id IS NULL** hoặc **IS NOT NULL**.

## 5. Quan hệ một–nhiều (1:N)

### 5.1. Khách hàng và đơn hàng

Một khách có thể đặt nhiều đơn, còn mỗi đơn chỉ thuộc về một khách. Vì thế, **khóa ngoại nằm ở phía nhiều**: bảng **purchase_order**.

~~~sql
CREATE TABLE purchase_order (
    order_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
                REFERENCES customer(customer_id) ON DELETE RESTRICT,
    ordered_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status      VARCHAR(20) NOT NULL DEFAULT 'NEW'
                CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);
~~~

Ràng buộc ở đây thể hiện:

- **customer_id NOT NULL**: mỗi đơn bắt buộc có tham chiếu khách hàng.
- **FOREIGN KEY**: khách hàng được tham chiếu phải tồn tại.
- **Không UNIQUE trên purchase_order.customer_id**: nhiều đơn được phép cùng tham chiếu một khách.
- **ON DELETE RESTRICT**: không thể xóa vật lý một khách hàng đang có đơn tham chiếu; chính sách này giúp tránh mất liên kết lịch sử giao dịch.

Một khách hàng có thể chưa đặt đơn, vì trong cơ sở dữ liệu chưa có hàng nào của **purchase_order** trỏ đến họ. **NOT NULL của khóa ngoại chỉ bảo đảm mỗi hàng phía con có cha**, không buộc mỗi hàng phía cha phải có con.

### 5.2. Dữ liệu minh họa

**customer**

| customer_id | full_name |
| ---: | --- |
| 1 | Nguyễn An |
| 2 | Trần Bình |

**purchase_order**

| order_id | customer_id | status |
| ---: | ---: | --- |
| 100 | 1 | PAID |
| 101 | 1 | NEW |

Trong tập dữ liệu này:

- Khách **1** có hai đơn hàng.
- Khách **2** chưa có đơn nào.
- Cả hai đơn đều thuộc khách **1**; không có chuyện một đơn thuộc đồng thời hai khách qua cột customer_id hiện tại.

### 5.3. Truy vấn từ cha sang con và thống kê

~~~sql
-- Các đơn của một khách hàng
SELECT order_id, status, ordered_at
FROM purchase_order
WHERE customer_id = 1
ORDER BY ordered_at DESC, order_id DESC;
~~~

Một truy vấn tổng hợp có thể giữ cả khách hàng chưa đặt đơn:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM customer AS c
LEFT JOIN purchase_order AS o
       ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Với dữ liệu minh họa, kết quả là **2 đơn** cho Nguyễn An và **0 đơn** cho Trần Bình.

**Vì sao COUNT(o.order_id), không dùng COUNT(*)?** Khi LEFT JOIN không tìm thấy đơn, hệ thống vẫn tạo ra một hàng kết quả với phần phía đơn là NULL. **COUNT(*)** tính cả hàng này và có thể cho **1** đối với khách không có đơn; **COUNT(o.order_id)** chỉ đếm các đơn có ID khác NULL.

### 5.4. Một–nhiều có thể là quan hệ tự tham chiếu

Ví dụ bảng **employee** có **manager_id** tham chiếu lại **employee.employee_id**: một quản lý có nhiều nhân viên, mỗi nhân viên có tối đa một quản lý trực tiếp trong mô hình đang xét.

~~~sql
CREATE TABLE employee (
    employee_id BIGINT PRIMARY KEY,
    full_name   VARCHAR(200) NOT NULL,
    manager_id  BIGINT REFERENCES employee(employee_id),
    CHECK (manager_id IS NULL OR manager_id <> employee_id)
);
~~~

**manager_id NULL** có thể biểu diễn nhân viên cấp cao không có quản lý trực tiếp. **CHECK** chỉ ngăn tự quản lý trực tiếp, chưa chặn vòng gián tiếp như A quản lý B, B quản lý C, C lại quản lý A. Khi nghiệp vụ yêu cầu cấu trúc cây không chu trình, cần kiểm soát điều kiện đó riêng.

## 6. Quan hệ nhiều–nhiều (N:M)

### 6.1. Vì sao cần bảng trung gian?

Một đơn hàng có thể chứa nhiều sản phẩm. Một sản phẩm có thể xuất hiện trong nhiều đơn hàng. Không thể biểu diễn đúng cả hai phía bằng **một khóa ngoại đặt trên purchase_order** hay **một khóa ngoại đặt trên product**.

Trong mô hình quan hệ, giải pháp thông dụng là tạo **bảng liên kết (junction / association table)**: mỗi hàng đại diện cho **một lần liên kết** giữa một đơn và một sản phẩm.

~~~text
purchase_order (1) ---- (N) order_item (N) ---- (1) product

Nhìn từ purchase_order đến product:
một đơn có nhiều sản phẩm; một sản phẩm thuộc nhiều đơn.
~~~

Thay vì ghi nhiều ID sản phẩm trong một chuỗi như **"10,11,12"**, mỗi cặp **(order_id, product_id)** được lưu thành một hàng riêng. Cách này cho phép khóa ngoại, lọc theo sản phẩm, thống kê và cập nhật số lượng rõ ràng.

### 6.2. Lược đồ đầy đủ với thuộc tính của quan hệ

~~~sql
CREATE TABLE product (
    product_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku           VARCHAR(64) NOT NULL UNIQUE,
    display_name  VARCHAR(200) NOT NULL,
    current_price NUMERIC(12, 2) NOT NULL
                  CHECK (current_price >= 0)
);

CREATE TABLE order_item (
    order_id   BIGINT NOT NULL
               REFERENCES purchase_order(order_id) ON DELETE RESTRICT,
    product_id BIGINT NOT NULL
               REFERENCES product(product_id) ON DELETE RESTRICT,
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, product_id)
);
~~~

Trong ví dụ:

- **order_id** tham chiếu đơn hàng.
- **product_id** tham chiếu sản phẩm.
- **quantity** và **unit_price** mô tả *sản phẩm trong đơn cụ thể*, không chỉ mô tả đơn hàng hay sản phẩm độc lập.
- **PRIMARY KEY (order_id, product_id)** bảo đảm mỗi sản phẩm có tối đa một dòng trong cùng một đơn.

Nếu nghiệp vụ cho phép cùng một sản phẩm xuất hiện nhiều dòng trong một đơn (chẳng hạn tùy chọn đóng gói, chiết khấu hoặc lô hàng khác nhau), khóa ghép trên **(order_id, product_id)** sẽ quá chặt. Lúc đó có thể tạo **order_item_id** riêng hoặc bổ sung **line_no** vào khóa để định danh từng dòng.

### 6.3. Dữ liệu minh họa và sự khác nhau giữa giá hiện tại và giá giao dịch

**product**

| product_id | sku | current_price |
| ---: | --- | ---: |
| 10 | MOUSE-01 | 170000.00 |
| 11 | KEY-01 | 350000.00 |

**order_item**

| order_id | product_id | quantity | unit_price |
| ---: | ---: | ---: | ---: |
| 100 | 10 | 2 | 150000.00 |
| 100 | 11 | 1 | 350000.00 |
| 101 | 10 | 1 | 170000.00 |

Đơn **100** có hai loại sản phẩm; sản phẩm **10** xuất hiện ở hai đơn **100** và **101**. Đơn giá của sản phẩm 10 ở đơn cũ là **150000**, trong khi giá hiện tại là **170000**. Đây là hai sự thật khác nhau; không nên tính lại lịch sử đơn từ **product.current_price**.

Tổng tiền của đơn **100** là **2 × 150000 + 1 × 350000 = 650000**.

### 6.4. JOIN qua bảng trung gian

~~~sql
SELECT
    o.order_id,
    p.sku,
    p.display_name,
    oi.quantity,
    oi.unit_price,
    oi.quantity * oi.unit_price AS line_total
FROM purchase_order AS o
JOIN order_item AS oi ON oi.order_id = o.order_id
JOIN product AS p ON p.product_id = oi.product_id
WHERE o.order_id = 100
ORDER BY p.sku;
~~~

Kết quả gồm **hai hàng**, tương ứng hai dòng sản phẩm của đơn **100**. Cột **order_id** xuất hiện lặp lại không có nghĩa dữ liệu đơn hàng bị lưu lặp trong bảng **purchase_order**; đó là tính chất của kết quả JOIN một–nhiều.

Tổng tiền của các đơn có dòng hàng:

~~~sql
SELECT
    o.order_id,
    SUM(oi.quantity * oi.unit_price) AS total_amount
FROM purchase_order AS o
JOIN order_item AS oi ON oi.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Truy vấn dùng **INNER JOIN** nên những đơn chưa có dòng hàng sẽ không xuất hiện. Nếu cần trả cả đơn rỗng với tổng 0:

~~~sql
SELECT
    o.order_id,
    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total_amount
FROM purchase_order AS o
LEFT JOIN order_item AS oi ON oi.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

**COALESCE** đổi kết quả NULL của SUM thành 0. Điều này phù hợp với ngữ nghĩa “tổng tiền chưa có dòng hàng”; trong bài toán khác, NULL có thể mang ý nghĩa “chưa tính được” và không nên tự động thay thế.

## 7. Những ràng buộc mà sơ đồ quan hệ chưa tự bảo đảm

### 7.1. Bội số tối đa thường dễ thực thi hơn bội số tối thiểu

Các ràng buộc phổ biến có thể bảo đảm:

| Yêu cầu | Công cụ SQL điển hình |
| --- | --- |
| Mỗi hàng có định danh duy nhất | PRIMARY KEY |
| Mỗi đơn thuộc đúng một khách đang tồn tại | NOT NULL + FOREIGN KEY |
| Mỗi khách có tối đa một profile | PRIMARY KEY hoặc UNIQUE trên profile.customer_id |
| Một sản phẩm xuất hiện tối đa một dòng trong cùng đơn | PRIMARY KEY(order_id, product_id) |
| Số lượng đặt phải dương | CHECK (quantity > 0) |

Ngược lại, ràng buộc **“đơn hàng PAID phải có ít nhất một order_item”** không được bảo đảm bởi FK từ **order_item** trỏ tới **purchase_order**. Khóa ngoại chỉ yêu cầu dòng hàng (nếu tồn tại) phải trỏ tới đơn hợp lệ; nó không yêu cầu mọi đơn phải có dòng hàng.

Có thể kiểm soát quy tắc này trong **giao dịch chuyển trạng thái sang PAID**, hoặc bằng cơ chế kiểm tra bổ sung thích hợp với hệ quản trị. Với ghi đồng thời, phải xét việc các dòng hàng bị thay đổi giữa lúc kiểm tra và lúc cập nhật trạng thái.

### 7.2. Quan hệ tùy chọn và NULL

Nếu khóa ngoại có thể NULL, có thể tồn tại bản ghi chưa gắn với phía còn lại. Ví dụ **employee.manager_id** cho phép NULL vì lãnh đạo cấp cao không có quản lý.

Tuy nhiên, **NULL không đồng nghĩa “quan hệ không tồn tại nhưng ID là số 0”**. Không nên dùng các giá trị giả như **-1** hoặc **0** để biểu diễn thiếu quan hệ nếu không có yêu cầu đặc biệt; chúng có thể phá vỡ tính rõ ràng của FK và logic truy vấn.

### 7.3. Quan hệ theo thời gian

Một người có thể đổi bộ phận hoặc quản lý; một thành viên có thể tham gia nhiều dự án theo những thời kỳ khác nhau. Nếu nghiệp vụ cần lịch sử, việc lưu một cột **manager_id** hiện tại sẽ không trả lời được “ai là quản lý vào tháng trước”.

Khi một quan hệ có thời gian hiệu lực, trạng thái hoặc quyền riêng, có thể cần **bảng liên kết có thuộc tính** như **membership(user_id, team_id, valid_from, valid_to, role)**. Khóa và ràng buộc phải phản ánh quy tắc về số lần tham gia, khoảng thời gian giao nhau và tính duy nhất ở từng thời điểm.

**Không có công thức duy nhất cho mọi quan hệ N:M.** Cần quyết định hàng trung gian đại diện cho cặp liên kết đang tồn tại hay một sự kiện liên kết xảy ra nhiều lần.

## 8. Tác động của quan hệ đến xóa và cập nhật dữ liệu

Khi một hàng đang được các hàng khác tham chiếu, cần xác định chính sách rõ ràng:

| Chính sách | Ý nghĩa chung | Tình huống cân nhắc |
| --- | --- | --- |
| **RESTRICT / NO ACTION** | Ngăn hoặc kiểm tra hành động xóa/sửa khóa được tham chiếu khi còn phụ thuộc; chi tiết thời điểm kiểm tra tùy hệ quản trị | Không cho xóa khách hàng đã có lịch sử đơn |
| **ON DELETE CASCADE** | Xóa các hàng phụ thuộc khi xóa hàng cha | Xóa hồ sơ bổ sung cùng tài khoản, nếu chính sách cho phép |
| **ON DELETE SET NULL** | Đưa FK ở phía con về NULL khi xóa hàng cha | Quan hệ tùy chọn như người quản lý, nếu nghiệp vụ cho phép |
| **Xóa mềm / lưu trữ trạng thái** | Giữ hàng và khóa, đánh dấu ngừng hoạt động bằng cột nghiệp vụ | Sản phẩm ngừng bán nhưng vẫn hiện trong đơn cũ |

Để sử dụng **SET NULL**, cột khóa ngoại phải cho phép NULL và ngữ nghĩa “không còn gắn với phía kia” phải phù hợp. Trong một số hệ thống, khóa định danh không bao giờ nên được sửa; tránh phụ thuộc vào các chính sách **ON UPDATE** nếu không có yêu cầu thực tế.

Ví dụ thiết kế đang dùng **ON DELETE RESTRICT** cho khách hàng, đơn hàng và sản phẩm đã được tham chiếu; nó thể hiện ưu tiên giữ lịch sử giao dịch. Với hệ thống cần xóa dữ liệu cá nhân theo yêu cầu pháp lý, nên xây dựng quy trình xóa/ẩn danh tương thích với nghĩa vụ lưu giữ hồ sơ thay vì chỉ bật CASCADE.

### 8.1. Không nhầm cascade ở SQL với cascade ở ORM

**ON DELETE CASCADE** là hành vi của cơ sở dữ liệu khi xóa hàng cha qua FK. Còn các tùy chọn **cascade** trong ORM như JPA/Hibernate điều khiển các thao tác vòng đời đối tượng mà ORM truyền sang thực thể liên quan.

Chúng hoạt động ở hai lớp khác nhau. Việc dùng cascade của ORM không tự đảm bảo mọi thao tác SQL ngoài ORM đều được áp dụng; ngược lại, database cascade có thể xóa hàng mà các đối tượng ORM đã tải trước đó chưa phản ánh ngay trong bộ nhớ. Cần chọn và kiểm thử phối hợp hai cơ chế, đặc biệt với những bảng chứa lịch sử giao dịch.

## 9. Từ SQL sang mô hình đối tượng Java

### 9.1. Một hàng từ JOIN không nhất thiết là một đối tượng nghiệp vụ

Một truy vấn đơn và sản phẩm như phần 6 trả về **một hàng trên mỗi order_item**. Nếu dùng JDBC, có thể ánh xạ mỗi hàng vào một DTO dòng đơn hàng:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class OrderItemQueries {
    public record OrderLine(
            long productId,
            String sku,
            int quantity,
            BigDecimal unitPrice
    ) {}

    public static List<OrderLine> findLines(
            Connection connection,
            long orderId
    ) throws SQLException {
        String sql = """
                SELECT oi.product_id, p.sku, oi.quantity, oi.unit_price
                FROM order_item AS oi
                JOIN product AS p ON p.product_id = oi.product_id
                WHERE oi.order_id = ?
                ORDER BY p.sku
                """;

        List<OrderLine> lines = new ArrayList<>();

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, orderId);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    lines.add(new OrderLine(
                            rs.getLong("product_id"),
                            rs.getString("sku"),
                            rs.getInt("quantity"),
                            rs.getBigDecimal("unit_price")
                    ));
                }
            }
        }
        return lines;
    }
}
~~~

Mã ví dụ giả sử bảng đã tồn tại và lớp gọi quản lý vòng đời của **Connection**. Các trường product_id, quantity và unit_price đều NOT NULL theo lược đồ đã định, nên các lời gọi getter không cần kiểm tra NULL trong ví dụ này.

Những điểm cần nhớ:

- **PreparedStatement** tách tham số khỏi câu lệnh, tránh nối trực tiếp dữ liệu đầu vào vào chuỗi SQL.
- **BigDecimal** phù hợp với cột tiền kiểu **NUMERIC(12,2)** hơn kiểu số thực nhị phân.
- **try-with-resources** đóng statement/result set ngay cả khi phát sinh lỗi.
- DTO **OrderLine** là hình dạng kết quả truy vấn; nó không nhất thiết phải tương đương toàn bộ thực thể **Product** hay **OrderItem**.
- Nếu muốn dựng một **PurchaseOrder** với danh sách dòng, cần gom các hàng JOIN theo **order_id**, tránh tạo ra nhiều đối tượng đơn hàng trùng định danh.

### 9.2. Ánh xạ quan hệ bằng JPA/Hibernate

Trong JPA, các annotation phổ biến gồm:

| Quan hệ trong Java | Annotation thường dùng | Vị trí khóa ngoại trong ví dụ |
| --- | --- | --- |
| Customer → CustomerProfile | **@OneToOne** | **customer_profile.customer_id** |
| PurchaseOrder → Customer | **@ManyToOne** | **purchase_order.customer_id** |
| Customer → các PurchaseOrder | **@OneToMany** | Vẫn dùng **purchase_order.customer_id** khi ánh xạ hai chiều phù hợp |
| PurchaseOrder → OrderItem | **@OneToMany** | **order_item.order_id** |
| OrderItem → Product | **@ManyToOne** | **order_item.product_id** |
| N:M đơn giản không có thuộc tính riêng | **@ManyToMany** | Bảng nối với hai FK |

Ví dụ phần liên kết **PurchaseOrder → Customer** bằng JPA:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrderEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "order_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private CustomerEntity customer;

    // Các trường khác, constructor và accessor được lược bỏ.
}
~~~

**CustomerEntity** là lớp thực thể tương ứng bảng customer mà ứng dụng cần định nghĩa. Đoạn code trên minh họa đúng phần ánh xạ quan hệ; nó chưa phải một ứng dụng JPA hoàn chỉnh.

**Vì sao N:M đơn hàng–sản phẩm không nên dùng trực tiếp @ManyToMany?** Vì **order_item** có các thuộc tính nghiệp vụ **quantity** và **unit_price**. Thường nên mô hình hóa **OrderItemEntity** thành một thực thể liên kết riêng với hai quan hệ **@ManyToOne**; như vậy có thể đọc, sửa, kiểm tra và lưu lịch sử trên từng dòng.

### 9.3. “Hai chiều trong Java” không có nghĩa “hai FK trong SQL”

Có thể thiết kế Java cho phép đọc cả:

- **order.getCustomer()**;
- **customer.getOrders()**.

Đó là cách điều hướng hai chiều trong mô hình đối tượng. Về mặt vật lý, **purchase_order.customer_id** vẫn có thể là **một khóa ngoại duy nhất** lưu quan hệ. Trong JPA, phía sở hữu ánh xạ và thuộc tính **mappedBy** cần cấu hình đúng để tránh tạo bảng nối hoặc FK ngoài ý muốn.

Không nên mặc định tải toàn bộ tập đơn hàng mỗi khi đọc một customer. **FetchType.LAZY** thường giúp trì hoãn đọc liên kết lớn, nhưng phải quản lý phiên/giao dịch và tránh lỗi truy cập dữ liệu khi persistence context đã đóng.

### 9.4. N+1 queries và nhân bản hàng

Một lỗi hiệu năng phổ biến: ứng dụng truy vấn 100 khách hàng, rồi chạy thêm một câu SQL để lấy đơn của **từng** khách. Kết quả là **1 + 100** truy vấn dù dữ liệu có thể lấy hiệu quả hơn bằng JOIN, batch loading hoặc phép chọn dữ liệu chuyên biệt.

Ngược lại, JOIN nhiều bộ sưu tập một–nhiều có thể tạo ra tích Descartes ở mức kết quả: một khách có **5 đơn và 4 địa chỉ**, nếu nối cả hai tập độc lập sẽ có thể nhận **20 hàng** cho một khách. Vì vậy, tối ưu tải liên kết cần đo lượng dữ liệu thực, không chỉ đếm số câu SQL.

## 10. Giao dịch và kiểm soát đồng thời khi cập nhật quan hệ

Một thao tác nghiệp vụ “tạo đơn hàng với hai sản phẩm” thường gồm các bước ghi:

1. Thêm hàng **purchase_order**.
2. Thêm hai hàng **order_item** tham chiếu đơn vừa tạo.
3. Kiểm tra điều kiện nghiệp vụ và xác nhận giao dịch.

Nếu chỉ ghi được hàng đơn, còn thêm dòng hàng bị lỗi, trạng thái lưu trữ có thể không phản ánh một đơn hàng hoàn chỉnh. Nếu nghiệp vụ yêu cầu **tất cả hoặc không có gì**, cần thực hiện các bước trong **một giao dịch** rồi **COMMIT** hoặc **ROLLBACK**.

Ví dụ logic với JDBC:

~~~java
boolean previousAutoCommit = connection.getAutoCommit();
try {
    connection.setAutoCommit(false);

    // INSERT purchase_order; đọc khóa order_id đã tạo.
    // INSERT các order_item tham chiếu order_id.
    // Kiểm tra các điều kiện của thao tác tạo đơn.

    connection.commit();
} catch (Exception error) {
    try {
        connection.rollback();
    } catch (java.sql.SQLException rollbackError) {
        error.addSuppressed(rollbackError);
    }
    throw error;
} finally {
    connection.setAutoCommit(previousAutoCommit);
}
~~~

Đoạn mã trên chỉ minh họa **ranh giới giao dịch**; để chạy thực tế cần đặt trong phương thức có chữ ký xử lý exception phù hợp, cung cấp Connection và câu lệnh INSERT cụ thể. Với Connection được quản lý bởi pool/framework, chính sách commit và đóng kết nối phải tuân theo tầng quản lý giao dịch của ứng dụng.

**Ràng buộc tại database vẫn quan trọng khi ghi đồng thời.** Ví dụ hai yêu cầu cùng kiểm tra “khách A chưa có profile” rồi cùng cố tạo hồ sơ. Nếu chỉ kiểm tra bằng truy vấn trước khi INSERT, cả hai có thể đều thấy “chưa có”. Ràng buộc **PRIMARY KEY hoặc UNIQUE trên customer_profile.customer_id** khiến database từ chối một bản ghi trùng, duy trì quy tắc “tối đa một”.

Khi thay đổi quan hệ nhiều–nhiều, có thể phát sinh tranh chấp cập nhật số lượng và giá, chứ không chỉ tranh chấp khóa. Tùy nghiệp vụ, cần khóa hàng, version/optimistic locking hoặc mức cô lập giao dịch phù hợp. Không nên suy ra toàn bộ tính đúng đắn chỉ từ việc FK đã hợp lệ.

## 11. Chỉ mục và hiệu năng truy cập quan hệ

Truy vấn theo FK rất thường gặp:

- Lấy tất cả đơn của một khách theo thời gian.
- Lấy các dòng hàng của một đơn.
- Tìm những đơn có chứa một sản phẩm.
- JOIN đơn hàng với khách hàng hoặc dòng hàng với sản phẩm.

Trong PostgreSQL, **PRIMARY KEY** thường tạo chỉ mục duy nhất trên khóa chính, nhưng **khóa ngoại ở bảng tham chiếu không tự động tạo chỉ mục tương ứng**. Những chỉ mục bổ sung có thể hữu ích:

~~~sql
CREATE INDEX idx_order_customer_time
ON purchase_order (customer_id, ordered_at DESC);

CREATE INDEX idx_order_item_product
ON order_item (product_id);
~~~

Với khóa chính ghép **order_item(order_id, product_id)**, chỉ mục B-tree hỗ trợ tốt truy vấn bắt đầu từ **order_id** theo thứ tự cột khóa. Truy vấn chỉ lọc **product_id** có thể cần chỉ mục riêng như ví dụ trên. Việc đánh giá phải dựa trên kế hoạch thực thi và dữ liệu thực tế, không có công thức “mỗi FK đều phải có một index” áp dụng cho mọi workload.

Chỉ mục làm tăng chi phí ghi, lưu trữ và bảo trì. Dùng **EXPLAIN** hoặc **EXPLAIN ANALYZE** trong môi trường phù hợp để kiểm chứng thay vì tạo nhiều chỉ mục mà không đo.

**JOIN trả nhiều hàng không tự nó là lỗi hiệu năng.** Đó thường là kết quả đúng của quan hệ 1:N hoặc N:M. Vấn đề nằm ở chỗ ứng dụng lấy quá nhiều cột, phân trang sai, lặp truy vấn không cần thiết hoặc dùng bộ nhớ để gom dữ liệu lớn mà không kiểm soát.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Đặt FK ở phía “một” trong quan hệ khách–đơn | Khó hoặc không thể biểu diễn nhiều đơn trên một khách | Đặt **customer_id** trong **purchase_order** |
| Dùng FK nhưng quên UNIQUE cho quan hệ 1:1 | Một khách có thể có nhiều hồ sơ | Dùng shared PK hoặc **UNIQUE + NOT NULL** |
| Nhầm “tối đa một” với “bắt buộc có một” | Tin rằng mỗi khách phải có profile dù database cho phép vắng mặt | Xác định riêng bội số tối thiểu và tối đa |
| Lưu danh sách product_id trong một cột văn bản | Không có FK trên từng ID, khó JOIN, khó thay đổi dòng | Dùng bảng **order_item** |
| Dùng @ManyToMany cho liên kết có quantity, unit_price | Khó mô hình hóa thuộc tính riêng của quan hệ | Dùng thực thể liên kết **OrderItem** |
| COUNT(*) sau LEFT JOIN để đếm con | Khách không có đơn có thể bị đếm thành 1 | Dùng **COUNT(child.primary_key)** |
| COUNT đơn sau khi JOIN thêm order_item | Một đơn nhiều dòng bị đếm nhiều lần | Đếm trước khi JOIN, gom theo đơn hoặc dùng **COUNT(DISTINCT o.order_id)** khi phù hợp |
| Bật CASCADE xóa hàng loạt | Mất lịch sử hoặc dữ liệu liên quan ngoài dự kiến | Xác định chính sách xóa theo nghiệp vụ |
| Kiểm tra tồn tại bằng Java rồi tin đó là ràng buộc duy nhất | Hai yêu cầu đồng thời có thể tạo bản ghi trùng | Đặt **PRIMARY KEY/UNIQUE** ở database |
| Tải mọi collection quan hệ khi đọc một hàng cha | Truy vấn N+1 hoặc nhân bản kết quả lớn | Chọn chiến lược fetch và DTO theo use case |
| Không có chỉ mục phù hợp ở FK thường xuyên lọc | Truy vấn JOIN/WHERE có thể chậm khi dữ liệu tăng | Đánh giá chỉ mục theo truy vấn và EXPLAIN |

## 13. Bài tập tự kiểm tra

### Bài tập 1: xác định dạng quan hệ

Một hệ thống đăng ký khóa học có **Student**, **Course** và **Enrollment**. Một sinh viên có thể đăng ký nhiều khóa, mỗi khóa có nhiều sinh viên, và mỗi lượt đăng ký lưu **enrolled_at** cùng **grade**.

**Câu hỏi:** Quan hệ Student–Course thuộc loại nào? Thiết kế tối thiểu cần những khóa gì?

**Gợi ý đáp án:** Đó là **N:M**, triển khai bằng **Enrollment(student_id FK, course_id FK, enrolled_at, grade)**. Nếu mỗi sinh viên chỉ đăng ký một khóa đúng một lần thì **PRIMARY KEY(student_id, course_id)** phù hợp. Nếu cho phép đăng ký lại nhiều học kỳ, cần định danh lần đăng ký hoặc thêm kỳ học vào khóa và quy tắc duy nhất.

### Bài tập 2: kiểm tra tính bắt buộc

Một khách hàng chưa có hồ sơ chi tiết có được chèn vào **customer** không? Một đơn có **customer_id = NULL** có được chèn không?

**Đáp án:** Có thể chèn khách hàng không có profile; bảng profile chỉ là tùy chọn phía customer. Không thể chèn đơn với **customer_id = NULL** vì cột này được khai báo **NOT NULL**.

### Bài tập 3: đếm đơn sau JOIN

Khách A có hai đơn. Đơn thứ nhất có ba dòng hàng, đơn thứ hai có hai dòng hàng. Nếu JOIN **customer → purchase_order → order_item** và dùng **COUNT(*)** cho khách A, kết quả có thể là bao nhiêu?

**Đáp án:** **5 hàng** trong kết quả JOIN, nhưng chỉ có **2 đơn hàng**. Muốn đếm đơn cần thay đổi cách thống kê như **COUNT(DISTINCT o.order_id)**, hoặc nhóm/đếm từ bảng purchase_order trước khi JOIN bảng chi tiết.

### Bài tập 4: hiểu khóa ghép

Vì sao **PRIMARY KEY(order_id, product_id)** chưa đủ cho nghiệp vụ “mỗi đơn có thể chứa cùng sản phẩm hai lần với hai mức giảm giá khác nhau”?

**Đáp án:** Khóa ghép cấm hai dòng có cùng cặp order_id và product_id. Khi mỗi lần xuất hiện có ý nghĩa độc lập, cần định danh dòng bằng **line_no** hoặc **order_item_id**, sau đó lưu giá/khuyến mãi cho từng dòng.

### Bài tập 5: bảo toàn lịch sử

Sản phẩm hiện tại có giá **170000**, nhưng một đơn cũ ghi **unit_price = 150000**. Khi tính tổng đơn cũ, phải dùng cột nào?

**Đáp án:** Dùng **order_item.unit_price** vì đó là giá tại thời điểm mua. **product.current_price** là thông tin hiện tại, không thay thế được sự thật lịch sử.

## 14. Tổng kết kiến thức cốt lõi

**Quan hệ 1:1** thường được biểu diễn bằng khóa ngoại **duy nhất**, hoặc khóa chính dùng chung giữa hai bảng. **Quan hệ 1:N** thường đặt khóa ngoại ở bảng phía nhiều. **Quan hệ N:M** cần bảng trung gian với hai khóa ngoại; khi quan hệ có thuộc tính như số lượng hoặc vai trò, hàng trung gian là một phần quan trọng của mô hình nghiệp vụ.

Bội số **0..1, 1..1, 0..N, 1..N** phải được hiểu ở cả hai phía. **PRIMARY KEY, UNIQUE, FOREIGN KEY, NOT NULL, CHECK** bảo đảm nhiều quy tắc tại cơ sở dữ liệu, nhưng những quy tắc tối thiểu phức tạp hoặc liên quan nhiều hàng có thể cần giao dịch và xử lý đồng thời. Khi lập trình Java, cách tải và ánh xạ quan hệ phải phù hợp với câu truy vấn, tránh N+1 và nhầm lẫn số hàng JOIN với số thực thể. Thiết kế tốt giúp dữ liệu bền vững, nhất quán và có thể thay đổi an toàn khi yêu cầu nghiệp vụ mở rộng.

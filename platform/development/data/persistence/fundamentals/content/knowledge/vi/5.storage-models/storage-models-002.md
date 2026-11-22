# Mô hình quan hệ: Bảng, hàng và cột

## 1. Vì sao cần mô hình quan hệ?

Giả sử một ứng dụng Java bán hàng phải lưu khách hàng, sản phẩm, đơn hàng và các sản phẩm trong từng đơn. Nếu mọi thông tin được nhét vào một chuỗi hoặc một bản ghi lớn, cùng một email khách hàng có thể bị sao chép hàng trăm lần; đổi email dễ dẫn tới dữ liệu không nhất quán, còn việc tìm tổng doanh thu theo khách hàng trở nên khó khăn.

**Mô hình quan hệ (relational model)** tổ chức dữ liệu thành các *quan hệ*. Trong cách triển khai SQL phổ biến, quan hệ được biểu diễn bằng **bảng (table)**, mỗi đối tượng hoặc sự kiện được biểu diễn bởi **hàng (row)** và mỗi thuộc tính được biểu diễn bởi **cột (column)**. Các bảng liên kết với nhau bằng giá trị khóa, cho phép lưu dữ liệu có cấu trúc và truy vấn kết hợp chúng.

Bài này thuộc chương **Mô hình lưu trữ** của học phần **DATA_PERSISTENCE_FUNDAMENTALS**. Trọng tâm là cách biểu diễn dữ liệu lâu bền, thiết kế lược đồ hợp lý và nhận biết những ràng buộc quan trọng trước khi viết tầng persistence bằng Java.

Sau bài học, người học có thể:

- Phân biệt bảng, hàng, cột, lược đồ và dữ liệu hiện tại của bảng.
- Xác định khóa chính, khóa ngoại và mối quan hệ một–nhiều, nhiều–nhiều.
- Tạo một lược đồ SQL nhỏ với kiểu dữ liệu và ràng buộc toàn vẹn phù hợp.
- Đọc truy vấn kết hợp nhiều bảng, hiểu khi nào kết quả bị nhân hàng hoặc có giá trị NULL.
- Nhận diện lỗi mô hình dữ liệu thường gặp và ánh xạ kết quả SQL về đối tượng Java.

## 2. Bảng, hàng, cột và lược đồ

Ví dụ bảng **customer**:

| customer_id | full_name | email |
| ---: | --- | --- |
| 1 | Nguyễn An | an@example.com |
| 2 | Trần Bình | binh@example.com |

Ba khái niệm cốt lõi:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Bảng (table)** | Tập hợp bản ghi cùng cấu trúc trong một lược đồ SQL | **customer** |
| **Cột (column)** | Thuộc tính có tên và kiểu dữ liệu xác định | **email** có kiểu VARCHAR(255) |
| **Hàng (row)** | Một bản ghi gồm các giá trị tương ứng với các cột | Khách hàng có **customer_id = 1** |
| **Lược đồ (schema)** | Định nghĩa cấu trúc: bảng, cột, kiểu, khóa, ràng buộc và quan hệ | Định nghĩa **customer(customer_id, full_name, email)** |
| **Thể hiện dữ liệu (instance)** | Tập hàng đang tồn tại tại một thời điểm | Hai khách hàng trong bảng ví dụ |

**Lược đồ** thay đổi tương đối ít, thường thông qua migration; **dữ liệu** thay đổi liên tục qua các thao tác thêm, sửa, xóa. Trong một số hệ quản trị như PostgreSQL, từ *schema* còn chỉ một không gian tên chứa bảng. Cần xác định rõ đang nói về *cấu trúc dữ liệu* hay *không gian tên*.

Một hàng có thể được hình dung như một bộ giá trị (tuple), một cột như một thuộc tính (attribute). Trong mô hình quan hệ toán học, quan hệ là tập hợp bộ giá trị: không có thứ tự hàng cố định và không có bộ trùng lặp. SQL triển khai các ý tưởng này nhưng có những khác biệt thực dụng: bảng không có khóa vẫn có thể chứa hàng giống nhau; kết quả SELECT thường giữ bản sao trùng nếu không dùng DISTINCT hoặc phép gom nhóm. **Không được dựa vào thứ tự lưu vật lý của hàng**; muốn kết quả có thứ tự phải dùng ORDER BY.

### 2.1. Chọn kiểu dữ liệu đúng

Kiểu dữ liệu giới hạn miền giá trị mà một cột được phép chứa. Ví dụ:

- **BIGINT** cho mã định danh số nguyên có phạm vi lớn.
- **VARCHAR(n)** cho chuỗi có giới hạn độ dài; email, mã SKU cần quy tắc kiểm tra riêng ở ứng dụng hoặc cơ sở dữ liệu nếu cần.
- **INTEGER** cho số lượng.
- **NUMERIC(12,2)** cho số tiền thập phân có độ chính xác cố định; tránh dùng số thực nhị phân như FLOAT để tính tiền trực tiếp.
- **TIMESTAMPTZ** (PostgreSQL) cho thời điểm có ý nghĩa múi giờ; ứng dụng thường trao đổi thời điểm qua kiểu Java Instant hoặc OffsetDateTime phù hợp với driver.

Kiểu dữ liệu là một phần của hợp đồng giữa ứng dụng và cơ sở dữ liệu. Lựa chọn quá lỏng làm dữ liệu sai dễ lọt vào; lựa chọn quá chặt có thể gây lỗi khi yêu cầu nghiệp vụ phát triển.

## 3. Từ nghiệp vụ đến các bảng liên quan

Với ứng dụng bán hàng, có bốn thực thể chính:

1. **customer**: thông tin khách hàng.
2. **product**: thông tin sản phẩm hiện tại.
3. **purchase_order**: một đơn hàng do một khách hàng đặt.
4. **order_item**: một dòng sản phẩm thuộc một đơn hàng, gồm số lượng và đơn giá tại lúc đặt.

Quan hệ giữa chúng:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ PURCHASE_ORDER : "dat"
    PURCHASE_ORDER ||--o{ ORDER_ITEM : "gom"
    PRODUCT ||--o{ ORDER_ITEM : "duoc_mua_trong"

    CUSTOMER {
        bigint customer_id PK
        varchar email UK
        varchar full_name
    }
    PRODUCT {
        bigint product_id PK
        varchar sku UK
        numeric current_price
    }
    PURCHASE_ORDER {
        bigint order_id PK
        bigint customer_id FK
        timestamptz created_at
        varchar status
    }
    ORDER_ITEM {
        bigint order_id PK, FK
        bigint product_id PK, FK
        integer quantity
        numeric unit_price
    }
~~~

Ký hiệu **1–n** có nghĩa một khách hàng có thể có nhiều đơn hàng, nhưng mỗi đơn hàng thuộc về một khách hàng. Một đơn có nhiều dòng sản phẩm; một sản phẩm có thể xuất hiện trong nhiều đơn. Vì vậy, mối quan hệ **nhiều–nhiều** giữa đơn hàng và sản phẩm được tách thành bảng trung gian **order_item**.

Dữ liệu minh họa:

**customer**

| customer_id | full_name |
| ---: | --- |
| 1 | Nguyễn An |

**product**

| product_id | sku | current_price |
| ---: | --- | ---: |
| 10 | MOUSE-01 | 150000.00 |
| 11 | KEY-01 | 350000.00 |

**purchase_order**

| order_id | customer_id | status |
| ---: | ---: | --- |
| 100 | 1 | PAID |

**order_item**

| order_id | product_id | quantity | unit_price |
| ---: | ---: | ---: | ---: |
| 100 | 10 | 2 | 150000.00 |
| 100 | 11 | 1 | 350000.00 |

Tổng tiền của đơn **100** là **2 × 150000 + 1 × 350000 = 650000**. Cột **unit_price** lưu giá tại thời điểm mua: nếu **product.current_price** được thay đổi sau đó, lịch sử đơn hàng vẫn giữ nguyên số tiền đã giao dịch. Đây là một ví dụ *cố ý lưu một giá trị lịch sử riêng* theo yêu cầu nghiệp vụ.

## 4. Khóa định danh và ràng buộc toàn vẹn

### 4.1. Khóa chính (PRIMARY KEY)

**Khóa chính** xác định duy nhất mỗi hàng trong một bảng và không được NULL. Trong bảng **customer**, **customer_id** là khóa chính. ID số được tạo tự động là một dạng *khóa thay thế* (surrogate key); mã số định danh có ý nghĩa nghiệp vụ cũng có thể là khóa tự nhiên khi ổn định và thực sự duy nhất.

Một khóa chính có thể gồm nhiều cột. Với quy ước một sản phẩm chỉ có một dòng trong mỗi đơn, **(order_id, product_id)** là khóa chính ghép của **order_item**. Nếu nghiệp vụ cho phép cùng sản phẩm xuất hiện trên nhiều dòng (ví dụ khác cấu hình/khuyến mãi), phải đổi thiết kế khóa, chẳng hạn dùng **order_item_id** và thêm các thuộc tính phân biệt.

### 4.2. Khóa ngoại (FOREIGN KEY)

**Khóa ngoại** bảo đảm giá trị tham chiếu trỏ đến hàng tồn tại trong bảng được tham chiếu, trừ trường hợp cột được phép NULL. Ví dụ **purchase_order.customer_id** tham chiếu **customer.customer_id**.

Không thể lưu đơn hàng có **customer_id = 999** khi khách hàng 999 không tồn tại (nếu ràng buộc khóa ngoại đang được thực thi). Điều này bảo vệ **toàn vẹn tham chiếu**, kể cả khi có nhiều ứng dụng cùng ghi vào cơ sở dữ liệu.

Khi xóa hàng được tham chiếu, cần lựa chọn quy tắc phù hợp như **RESTRICT / NO ACTION**, **CASCADE** hoặc **SET NULL** (tên và thời điểm kiểm tra tùy hệ quản trị). Với dữ liệu đơn hàng cần bảo toàn lịch sử, thường nên ngăn xóa khách hàng hoặc sản phẩm đang được tham chiếu, hay áp dụng cơ chế ngừng hoạt động, thay vì xóa dây chuyền.

### 4.3. Các ràng buộc khác

- **NOT NULL**: bắt buộc có giá trị, chẳng hạn tên khách hàng và số lượng.
- **UNIQUE**: chặn giá trị trùng trên tập cột áp dụng, chẳng hạn email đã được chuẩn hóa theo quy tắc nghiệp vụ. Cách xử lý nhiều giá trị NULL trong UNIQUE có thể khác giữa các hệ quản trị.
- **CHECK**: điều kiện hợp lệ, chẳng hạn số lượng lớn hơn 0 và giá không âm.
- **DEFAULT**: điền giá trị mặc định khi câu lệnh chèn không cung cấp giá trị, chẳng hạn trạng thái NEW.

Ràng buộc nằm trong cơ sở dữ liệu bổ sung cho kiểm tra ở tầng Java: Java giúp báo lỗi dễ hiểu, còn database là hàng rào cuối cùng bảo vệ dữ liệu khi có tác nhân khác truy cập.

## 5. Khai báo lược đồ SQL cụ thể

Đoạn DDL dưới đây sử dụng **PostgreSQL** để minh họa. Cú pháp tạo ID, kiểu thời gian và một số chi tiết ràng buộc có thể khác ở MySQL, SQL Server hoặc hệ quản trị khác.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email       VARCHAR(255) NOT NULL UNIQUE,
    full_name   VARCHAR(200) NOT NULL
);

CREATE TABLE product (
    product_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku           VARCHAR(64) NOT NULL UNIQUE,
    name          VARCHAR(200) NOT NULL,
    current_price NUMERIC(12, 2) NOT NULL
                  CHECK (current_price >= 0)
);

CREATE TABLE purchase_order (
    order_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  BIGINT NOT NULL REFERENCES customer(customer_id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status       VARCHAR(20) NOT NULL DEFAULT 'NEW'
                 CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TABLE order_item (
    order_id   BIGINT NOT NULL REFERENCES purchase_order(order_id),
    product_id BIGINT NOT NULL REFERENCES product(product_id),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, product_id)
);
~~~

Quan sát một số quyết định:

- Thứ tự tạo bảng đi theo phụ thuộc khóa ngoại: tạo bảng gốc trước bảng tham chiếu.
- **order_item** chứa cả **order_id** và **product_id** để nối đơn hàng với sản phẩm.
- Giá lưu tại **order_item.unit_price** là giá đã chốt; giá hiện tại trong **product** chỉ phục vụ thông tin sản phẩm ở hiện tại.
- Đơn mới có **status = NEW** nhờ DEFAULT; CHECK chỉ cho phép ba trạng thái được liệt kê. CHECK không thể tự bảo đảm *quy trình chuyển trạng thái* (chẳng hạn NEW → PAID); quy tắc đó cần được kiểm soát bổ sung.
- Ràng buộc FK đang dùng quy tắc xóa mặc định của PostgreSQL; chính sách xóa thực tế phải được thiết kế theo yêu cầu lưu lịch sử.

DDL mô tả **hình dạng và bất biến dữ liệu**, còn thao tác thêm, sửa và truy vấn (DML) tác động đến các hàng nằm trong hình dạng đó.

## 6. Truy vấn dữ liệu từ bảng và hàng

### 6.1. Chọn cột, lọc hàng và sắp xếp

~~~sql
SELECT order_id, created_at, status
FROM purchase_order
WHERE customer_id = 1
ORDER BY created_at DESC, order_id DESC;
~~~

- **SELECT** xác định cột cần đọc.
- **FROM** xác định bảng nguồn.
- **WHERE** lọc hàng thỏa điều kiện.
- **ORDER BY** chỉ định thứ tự trả về.

Không có ORDER BY, kết quả **không được bảo đảm có thứ tự ổn định**, dù một lần chạy có vẻ trùng với thứ tự ID.

### 6.2. Kết hợp các bảng bằng JOIN

~~~sql
SELECT
    o.order_id,
    c.full_name,
    p.sku,
    oi.quantity,
    oi.unit_price
FROM purchase_order AS o
JOIN customer AS c ON c.customer_id = o.customer_id
JOIN order_item AS oi ON oi.order_id = o.order_id
JOIN product AS p ON p.product_id = oi.product_id
WHERE o.order_id = 100
ORDER BY p.sku;
~~~

Với dữ liệu minh họa, truy vấn trả **hai hàng**, mỗi hàng cho một sản phẩm thuộc đơn 100. Việc cột **order_id** và **full_name** xuất hiện lặp trong kết quả là bình thường: **JOIN một–nhiều có thể làm một hàng cha tạo ra nhiều hàng kết quả**. Lập trình viên không nên giả định mỗi đơn chỉ tương ứng một hàng sau khi JOIN với bảng chi tiết.

**INNER JOIN** chỉ giữ các cặp hàng khớp điều kiện. **LEFT JOIN** giữ mọi hàng phía trái ngay cả khi không có hàng khớp phía phải; cột của phía phải sẽ xuất hiện dưới dạng NULL. Ví dụ, muốn tìm cả đơn chưa có dòng hàng:

~~~sql
SELECT o.order_id, oi.product_id
FROM purchase_order AS o
LEFT JOIN order_item AS oi ON oi.order_id = o.order_id;
~~~

Nếu chuyển điều kiện trên **oi** sang WHERE mà không xử lý NULL, câu truy vấn có thể vô tình loại bỏ các đơn rỗng và mất ý nghĩa LEFT JOIN.

### 6.3. Gom nhóm để tính tổng

~~~sql
SELECT
    o.order_id,
    c.full_name,
    SUM(oi.quantity * oi.unit_price) AS total_amount
FROM purchase_order AS o
JOIN customer AS c ON c.customer_id = o.customer_id
JOIN order_item AS oi ON oi.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY o.order_id, c.full_name
ORDER BY o.order_id;
~~~

Với đơn 100, **total_amount = 650000.00**. **GROUP BY** gộp những hàng có cùng khóa nhóm, còn **SUM** cộng các dòng tiền. Truy vấn dùng INNER JOIN nên đơn không có dòng sản phẩm không xuất hiện trong kết quả. Muốn hiển thị cả đơn rỗng với tổng bằng 0, có thể dùng LEFT JOIN và **COALESCE(SUM(...), 0)**.

### 6.4. Thêm và sửa hàng

~~~sql
INSERT INTO customer (email, full_name)
VALUES ('lan@example.com', 'Lê Lan');

UPDATE customer
SET full_name = 'Lê Ngọc Lan'
WHERE email = 'lan@example.com';
~~~

Cần kiểm tra phạm vi của WHERE trước khi UPDATE hoặc DELETE: bỏ WHERE có thể tác động đến mọi hàng trong bảng. Trong ứng dụng, nên cập nhật theo định danh ổn định như khóa chính, đồng thời kiểm tra số hàng chịu tác động khi nghiệp vụ yêu cầu chính xác một bản ghi.

## 7. Giá trị NULL và tính đúng đắn của kết quả

**NULL** biểu diễn sự vắng mặt của một giá trị trong SQL. Nó không đồng nghĩa với chuỗi rỗng, số 0 hoặc FALSE. Phép so sánh thông thường với NULL trả về trạng thái **UNKNOWN** (logic ba giá trị: TRUE, FALSE, UNKNOWN).

~~~sql
-- Đúng: tìm hàng chưa có giá trị
SELECT customer_id
FROM customer
WHERE email IS NULL;

-- Không đúng mục đích: biểu thức email = NULL không cho TRUE
SELECT customer_id
FROM customer
WHERE email = NULL;
~~~

Ở lược đồ của bài, **customer.email** được khai báo NOT NULL nên truy vấn đầu tiên sẽ không trả hàng nào; ví dụ trên dùng để giải thích cú pháp chung. Nếu một cột cho phép NULL, hãy dùng **IS NULL / IS NOT NULL** để kiểm tra. Cần đặc biệt cẩn thận với **NOT IN** khi tập so sánh có NULL và với cách nhóm, lọc, tổng hợp giá trị thiếu.

## 8. Chuẩn hóa: đặt mỗi thông tin vào đúng chỗ

Một lỗi thiết kế phổ biến là tạo bảng đơn hàng như sau:

| order_id | customer_name | customer_email | product_1 | product_2 |
| ---: | --- | --- | --- | --- |
| 100 | Nguyễn An | an@example.com | MOUSE-01 | KEY-01 |

Thiết kế này gây nhiều vấn đề:

- Cột **product_1**, **product_2** không mở rộng được khi đơn có 3 hoặc 20 sản phẩm.
- Tên và email khách hàng bị lặp trên nhiều đơn; đổi email dễ khiến các bản ghi không đồng nhất (**update anomaly**).
- Chưa có đơn hàng thì khó biểu diễn khách hàng riêng biệt nếu hệ thống chỉ có bảng đơn (**insertion anomaly**).
- Xóa đơn duy nhất của một khách có thể làm mất thông tin khách (**deletion anomaly**).

Cách tách **customer → purchase_order → order_item** giải quyết các vấn đề chính bằng việc biểu diễn mỗi loại sự thật ở một bảng thích hợp và liên kết bằng khóa. Ý tưởng này là nền tảng của **chuẩn hóa (normalization)**: giảm dư thừa và những phụ thuộc dữ liệu không phù hợp.

Chuẩn hóa không có nghĩa là cấm lưu mọi dữ liệu lặp. **order_item.unit_price** được giữ riêng vì đó là một sự thật lịch sử khác với **product.current_price**. Khi chủ động phi chuẩn hóa để tối ưu truy vấn, cần nêu rõ nguồn dữ liệu chuẩn và cách duy trì tính nhất quán.

## 9. Từ hàng SQL về đối tượng Java

Khi làm tầng persistence, một hàng SQL thường được ánh xạ thành một đối tượng Java hoặc một bản ghi đọc dữ liệu (DTO). Ví dụ dưới đây dùng JDBC, giả sử đã có **java.sql.Connection** hợp lệ:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

final class OrderQueries {
    record OrderRow(long id, String status) {}

    static List<OrderRow> findByCustomer(Connection connection, long customerId)
            throws SQLException {
        String sql =
                "SELECT order_id, status " +
                "FROM purchase_order " +
                "WHERE customer_id = ? " +
                "ORDER BY created_at DESC, order_id DESC";

        List<OrderRow> rows = new ArrayList<>();
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, customerId);

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    rows.add(new OrderRow(
                            result.getLong("order_id"),
                            result.getString("status")
                    ));
                }
            }
        }
        return rows;
    }
}
~~~

Ở đây:

- **PreparedStatement** truyền tham số theo kiểu dữ liệu, giúp tránh ghép trực tiếp giá trị đầu vào vào chuỗi SQL và giảm rủi ro SQL injection.
- **ResultSet** cung cấp các hàng từ truy vấn; mã Java đọc từng hàng và ánh xạ cột sang trường.
- **try-with-resources** đóng statement và result set ngay cả khi xảy ra lỗi.
- **long** phù hợp với cột ID NOT NULL; nếu ánh xạ một cột số có thể NULL, cần chú ý rằng **getLong** trả 0 khi giá trị SQL là NULL và phải kiểm tra **wasNull()** hoặc dùng cách ánh xạ phù hợp.
- Ví dụ giả định vòng đời của Connection do tầng gọi quản lý; mã truy vấn không tự mở hoặc đóng kết nối.

Một đối tượng Java **không nhất thiết tương ứng một bảng**: DTO tổng tiền đơn hàng có thể lấy từ JOIN và GROUP BY, còn một aggregate nghiệp vụ có thể trải qua nhiều bảng. Đơn hàng và các dòng hàng cần được ghi trong **cùng một giao dịch** nếu nghiệp vụ yêu cầu tạo chúng như một thao tác nguyên tử. Ví dụ, nếu ghi được đầu đơn nhưng ghi dòng hàng thất bại, rollback sẽ tránh trạng thái đơn dở dang. Mức cô lập và kiểm soát đồng thời là những khía cạnh tiếp theo của persistence; chúng dựa trên lược đồ đúng nhưng không thể được thay thế bằng lược đồ.

## 10. Quan hệ logic và cách lưu trữ vật lý

Mô hình quan hệ mô tả **dữ liệu có nghĩa gì** và **các ràng buộc cần thỏa**. Nó không quy định chi tiết các trang dữ liệu được sắp trên đĩa ra sao. Hệ quản trị quyết định cách lưu trang, tổ chức chỉ mục, chọn thuật toán JOIN và thực thi truy vấn.

Tuy nhiên, thiết kế bảng ảnh hưởng trực tiếp tới hiệu năng:

- Truy vấn theo **purchase_order.customer_id** thường cần cân nhắc chỉ mục cột đó nếu lọc theo khách hàng là thao tác phổ biến.
- Khóa chính thường được hệ quản trị hỗ trợ bằng chỉ mục duy nhất, nhưng **khóa ngoại không mặc nhiên có chỉ mục ở mọi hệ quản trị**; phải kiểm tra cụ thể.
- Mỗi chỉ mục hỗ trợ một số cách đọc nhưng cũng tăng chi phí lưu trữ và ghi dữ liệu.
- SELECT chỉ các cột cần thiết giúp giảm lượng dữ liệu truyền và chi phí chuyển đổi sang Java.

Ví dụ chỉ mục tùy chọn trong PostgreSQL:

~~~sql
CREATE INDEX idx_purchase_order_customer_created
ON purchase_order (customer_id, created_at DESC);
~~~

Chỉ mục này có thể hữu ích cho truy vấn lọc theo khách hàng và sắp xếp theo thời gian. **Không thể khẳng định truy vấn luôn nhanh hơn** nếu chưa xem dữ liệu, phân bố giá trị, kế hoạch thực thi và tải hệ thống. Khi hiệu năng thành vấn đề, dùng **EXPLAIN (ANALYZE, BUFFERS)** trong môi trường kiểm soát để quan sát thực tế.

Mô hình quan hệ đặc biệt phù hợp khi dữ liệu có cấu trúc rõ, nhiều ràng buộc, quan hệ giữa thực thể và nhu cầu truy vấn tổ hợp. Đổi lại, thay đổi lược đồ phải được quản lý qua migration và các JOIN phức tạp cần chú ý hiệu năng. Không nên chọn mô hình chỉ theo việc JSON hay bảng trông thuận tiện hơn; hãy dựa vào cấu trúc dữ liệu, tính toàn vẹn và kiểu truy vấn chính.

## 11. Lỗi thường gặp và cách tự kiểm tra

| Dấu hiệu | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Lưu danh sách sản phẩm thành các cột product_1, product_2... | Số dòng chi tiết bị giới hạn; khó lọc và thống kê | Dùng bảng **order_item** nhiều hàng |
| Không có khóa chính hoặc UNIQUE cho định danh nghiệp vụ | Hàng trùng, cập nhật nhầm | Khai báo PK; dùng UNIQUE nơi phù hợp |
| Ghi customer_id mà không ràng buộc FK | Đơn có thể trỏ đến khách không tồn tại | Khai báo FOREIGN KEY và quy tắc xóa |
| Dùng FLOAT để tính tiền | Sai số biểu diễn số thập phân | Dùng NUMERIC/DECIMAL và BigDecimal ở Java |
| Lấy giá hiện tại làm giá của đơn cũ | Thay giá sản phẩm làm sai lịch sử thanh toán | Lưu đơn giá tại thời điểm giao dịch |
| Dựa vào thứ tự xuất hiện của các hàng | Trang dữ liệu/đầu ra thay đổi khó đoán | ORDER BY có tiêu chí xác định |
| JOIN một–nhiều rồi COUNT(*) như đếm đơn hàng | Đếm số dòng hàng thay vì số đơn | Gom nhóm theo đơn hoặc COUNT(DISTINCT order_id), tùy mục tiêu |
| Giả định NULL bằng 0 hoặc chuỗi rỗng | Lọc thiếu hoặc xử lý sai dữ liệu | Xác định ý nghĩa NULL, dùng IS NULL |

### Tình huống thực hành

Một hệ thống có 100 khách hàng, mỗi khách có nhiều đơn; mỗi đơn có thể có nhiều sản phẩm.

1. **Vì sao không lưu danh sách product_id trong một chuỗi ở purchase_order?** Vì khó áp dụng khóa ngoại cho từng sản phẩm, khó truy vấn/gom nhóm và khó kiểm soát số lượng hoặc đơn giá từng dòng.
2. **Dùng khóa nào để xác định một dòng trong order_item?** Trong thiết kế đã nêu, dùng khóa ghép (**order_id**, **product_id**) vì một sản phẩm xuất hiện tối đa một lần trên mỗi đơn.
3. **Khi đổi giá sản phẩm từ 150000 thành 170000, tổng đơn 100 có đổi không?** Không, vì tổng đơn dùng **order_item.unit_price** đã ghi khi giao dịch.
4. **Muốn lấy đơn hàng của một khách theo mới nhất, nên dùng gì?** Lọc **customer_id**, dùng **ORDER BY created_at DESC, order_id DESC**; cân nhắc chỉ mục dựa trên kết quả đo.
5. **Nếu Java lưu purchase_order thành công nhưng lưu order_item thất bại thì sao?** Nên dùng giao dịch để cả hai bước cùng commit hoặc cùng rollback, tránh dữ liệu không hoàn chỉnh.

## 12. Ghi nhớ

**Bảng** biểu diễn một loại thực thể hoặc quan hệ; **hàng** là một bản ghi; **cột** là một thuộc tính có miền dữ liệu cụ thể. **Khóa chính** định danh hàng, **khóa ngoại** nối các bảng, còn **NOT NULL / UNIQUE / CHECK** giúp bảo vệ tính toàn vẹn. Truy vấn SQL có thể ghép và gom nhóm dữ liệu từ nhiều bảng, nhưng phải hiểu quy tắc JOIN, NULL và thứ tự kết quả. Một lược đồ quan hệ rõ ràng là nền tảng để tầng persistence Java lưu dữ liệu bền vững, nhất quán và có thể mở rộng.

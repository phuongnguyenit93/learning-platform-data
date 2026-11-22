# SELECT, INSERT, UPDATE, DELETE và câu lệnh định nghĩa cấu trúc

Bài học thuộc **Nền tảng dữ liệu** của module **Spring Framework - data-access**. Mục tiêu là hiểu các thao tác SQL trực tiếp trước khi dùng JDBC, JdbcTemplate, Spring Data JDBC hay JPA: **SELECT** đọc dữ liệu, **INSERT** thêm hàng, **UPDATE** sửa hàng, **DELETE** xóa hàng, còn **DDL** định nghĩa và thay đổi cấu trúc chứa dữ liệu.

## 1. Nhận biết nhóm lệnh và phạm vi tác động

| Nhóm | Lệnh tiêu biểu | Tác dụng |
| --- | --- | --- |
| DQL (truy vấn; đôi khi được xếp cùng DML) | SELECT | Trả tập kết quả từ bảng, kết hợp các bảng, lọc, nhóm, sắp xếp |
| DML (thao tác dữ liệu) | INSERT, UPDATE, DELETE | Thêm, sửa, xóa hàng trong các bảng có sẵn |
| DDL (định nghĩa dữ liệu) | CREATE, ALTER, DROP; TRUNCATE thường được xếp vào DDL | Tạo, sửa, xóa bảng, chỉ mục, ràng buộc hoặc đối tượng schema |
| TCL (điều khiển giao dịch) | BEGIN/START TRANSACTION, COMMIT, ROLLBACK | Xác lập phạm vi và kết thúc/hủy giao dịch |
| DCL (phân quyền) | GRANT, REVOKE | Cấp và thu hồi quyền |

Không nên chỉ học thuộc tên nhóm: khác biệt quan trọng là **thay đổi từng hàng dữ liệu** so với **thay đổi schema và các quy tắc lưu trữ**. SQL là ngôn ngữ khai báo; ta mô tả kết quả mong muốn, còn DBMS chọn kế hoạch truy cập. Các biến thể cú pháp/phân loại có thể khác giữa PostgreSQL, MySQL, SQL Server và Oracle.

### Dữ liệu thực hành thống nhất

Các lệnh chạy được dưới đây chọn **PostgreSQL** làm hệ quản trị tham chiếu. Hãy thực hành trên database riêng, chưa có bảng categories/products trùng tên. Câu lệnh tạo cấu trúc:

~~~sql
CREATE TABLE categories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_id BIGINT NOT NULL
        REFERENCES categories(id) ON DELETE RESTRICT,
    sku VARCHAR(32) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_products_category_id ON products (category_id);
~~~

Ràng buộc **PRIMARY KEY** định danh từng hàng; **FOREIGN KEY** bảo đảm tham chiếu tới danh mục có thật; **UNIQUE** tránh giá trị SKU trùng; **NOT NULL** bắt buộc có dữ liệu; **CHECK** bảo vệ các miền giá trị; **DEFAULT** tạo giá trị khi INSERT bỏ qua cột. Riêng CHECK không thay thế NOT NULL: theo ngữ nghĩa SQL, điều kiện CHECK nhận UNKNOWN từ NULL có thể được chấp nhận.

Nạp dữ liệu mẫu vào schema vừa tạo:

~~~sql
INSERT INTO categories (name)
VALUES ('Sách'), ('Thiết bị');

INSERT INTO products (category_id, sku, name, price, stock)
VALUES
    (
        (SELECT id FROM categories WHERE name = 'Sách'),
        'BOOK-001', 'Java căn bản', 350000.00, 8
    ),
    (
        (SELECT id FROM categories WHERE name = 'Sách'),
        'BOOK-002', 'SQL thực hành', 280000.00, 0
    ),
    (
        (SELECT id FROM categories WHERE name = 'Thiết bị'),
        'DEV-001', 'Bàn phím cơ', 1200000.00, 5
    );
~~~

Không gán cứng rằng ID được sinh luôn bằng 1, 2, 3. Truy vấn con lấy danh mục qua cột name có UNIQUE nên tối đa một kết quả. Nếu tên danh mục không tồn tại, truy vấn con trả NULL và INSERT bị NOT NULL từ chối. Khi làm từng bài sau, hãy khởi tạo lại dữ liệu mẫu hoặc xét trạng thái ban đầu; các ví dụ UPDATE/DELETE có thể thay đổi số hàng.

## 2. SELECT — truy vấn dữ liệu

Các mệnh đề thường gặp (dòng sau là **sơ đồ cú pháp, không phải lệnh thực thi**):

~~~sql
SELECT [DISTINCT] cot_1, bieu_thuc_2, ...
FROM bang_nguon
[JOIN bang_khac ON dieu_kien_join]
[WHERE dieu_kien_hang]
[GROUP BY cot_nhom]
[HAVING dieu_kien_nhom]
[ORDER BY cot_sap_xep ASC | DESC]
[LIMIT so_hang OFFSET so_hang_bo_qua];
~~~

Theo thứ tự xử lý **logic**, SQL hình thành tập hàng ở FROM/JOIN, lọc hàng ở WHERE, nhóm ở GROUP BY, lọc nhóm ở HAVING, chọn biểu thức ở SELECT, xử lý DISTINCT rồi sắp xếp/giới hạn. Thứ tự **thực thi vật lý** có thể khác vì bộ tối ưu hóa được phép chọn kế hoạch tương đương.

### 2.1. SELECT, WHERE, ORDER BY, LIMIT

~~~sql
SELECT sku, name, price, stock
FROM products
WHERE price >= 300000 AND stock > 0
ORDER BY price DESC, sku ASC
LIMIT 10;
~~~

Trên dữ liệu ban đầu, kết quả gồm **DEV-001** (1.200.000) trước **BOOK-001** (350.000). SELECT liệt kê cột cần lấy, WHERE kết hợp điều kiện AND, ORDER BY sắp xếp giảm theo giá rồi tăng theo SKU, LIMIT lấy tối đa 10 hàng. **Không có ORDER BY thì không có cam kết thứ tự kết quả**, dù vài lần chạy liên tiếp có vẻ giống nhau.

Các dạng lọc phổ biến:

~~~sql
-- BETWEEN bao gồm cả hai đầu mút.
SELECT sku FROM products WHERE price BETWEEN 200000 AND 500000;

-- Chọn một phần tử trong tập.
SELECT sku FROM products WHERE sku IN ('BOOK-001', 'DEV-001');

-- % khớp 0 hoặc nhiều ký tự; _ khớp đúng một ký tự.
SELECT sku FROM products WHERE name LIKE 'Java%';

-- So sánh NULL phải dùng IS NULL / IS NOT NULL.
SELECT sku FROM products WHERE created_at IS NOT NULL;
~~~

**NULL là “không biết/không có giá trị”, không phải 0 hoặc chuỗi rỗng**. So sánh thông thường với NULL cho UNKNOWN; WHERE chỉ giữ hàng khi điều kiện TRUE. Vì vậy không dùng WHERE col = NULL hoặc WHERE col <> NULL. NOT IN cũng cần cẩn thận nếu tập bên phải chứa NULL.

DISTINCT loại các dòng có cùng giá trị trên **toàn bộ biểu thức được chọn**. Chọn cột rõ ràng thường ổn định hơn SELECT * trong API có hợp đồng dữ liệu; việc thêm cột vào bảng không nên vô tình thay đổi danh sách cột do ứng dụng sử dụng.

### 2.2. JOIN — kết hợp nhiều bảng

~~~sql
SELECT
    p.sku,
    p.name AS product_name,
    c.name AS category_name
FROM products AS p
INNER JOIN categories AS c ON c.id = p.category_id
ORDER BY p.sku;
~~~

INNER JOIN chỉ giữ các cặp hàng thỏa điều kiện ON. LEFT JOIN giữ toàn bộ hàng bên trái; nếu không có hàng phải tương ứng, các cột phía phải nhận NULL. Vị trí lọc rất quan trọng:

~~~sql
-- Danh mục vẫn xuất hiện ngay cả khi không có sản phẩm còn tồn.
SELECT c.name AS category_name, p.sku
FROM categories AS c
LEFT JOIN products AS p
    ON p.category_id = c.id AND p.stock > 0
ORDER BY c.name, p.sku;
~~~

Nếu chuyển p.stock > 0 xuống WHERE, những danh mục không có sản phẩm khớp sẽ bị loại. Cũng cần nhận diện việc JOIN thiếu điều kiện gây tích Descartes, làm số hàng tăng mạnh và dữ liệu bị nhân bản trong báo cáo.

### 2.3. GROUP BY, HAVING và hàm tổng hợp

~~~sql
SELECT
    c.name AS category_name,
    COUNT(p.id) AS product_count,
    COALESCE(SUM(p.stock), 0) AS total_stock
FROM categories AS c
LEFT JOIN products AS p ON p.category_id = c.id
GROUP BY c.id, c.name
HAVING COUNT(p.id) >= 1
ORDER BY c.name;
~~~

Kết quả từ dữ liệu ban đầu: danh mục **Sách** có 2 sản phẩm/tổng tồn 8; **Thiết bị** có 1 sản phẩm/tổng tồn 5. WHERE lọc **trước** khi nhóm, HAVING lọc **sau** khi đã tính tổng hợp. Các hàm thông dụng: COUNT, SUM, AVG, MIN, MAX. COUNT(*) đếm mọi hàng kết quả, còn COUNT(p.id) bỏ qua NULL; trong LEFT JOIN, COUNT(*) có thể đếm cả hàng không khớp từ phía phải. COALESCE thay NULL bằng giá trị thay thế. Cột được SELECT bên ngoài hàm tổng hợp phải tuân theo quy tắc GROUP BY/phụ thuộc hàm của DBMS.

### 2.4. Phân trang và hiệu năng

~~~sql
SELECT id, sku, name
FROM products
ORDER BY id
LIMIT 20 OFFSET 40;
~~~

Đây là trang thứ ba nếu mỗi trang 20 hàng và trang đầu là trang 1. ORDER BY cần ổn định, thường có khóa duy nhất. OFFSET lớn có thể khiến DBMS vẫn phải đọc/bỏ qua nhiều hàng; khi duyệt tiếp theo ID, cách phân trang theo khóa có thể hiệu quả hơn:

~~~sql
SELECT id, sku, name
FROM products
WHERE id > 100
ORDER BY id
LIMIT 20;
~~~

Ở đây 100 là ID cuối trang trước. Khi bảng thay đổi đồng thời, hai kiểu phân trang có thể quan sát tập kết quả khác nhau. LIMIT là cú pháp PostgreSQL/MySQL; một số DBMS dùng FETCH FIRST, OFFSET FETCH hoặc TOP. Với dữ liệu lớn, dùng EXPLAIN và xem chỉ mục phù hợp, tránh mặc định rằng mọi truy vấn WHERE đều dùng index.

## 3. INSERT — thêm hàng

Luôn chỉ rõ danh sách cột để câu lệnh không phụ thuộc thứ tự cột của schema:

~~~sql
INSERT INTO products (category_id, sku, name, price, stock)
VALUES (
    (SELECT id FROM categories WHERE name = 'Sách'),
    'BOOK-003', 'SQL nâng cao', 420000.00, 4
);
~~~

Nếu bỏ id, IDENTITY sinh ID; nếu bỏ stock, DEFAULT 0 được sử dụng. NOT NULL, UNIQUE, FOREIGN KEY và CHECK được kiểm tra khi ghi. INSERT có thể chèn nhiều hàng bằng VALUES nhiều bộ, như phần dữ liệu mẫu, hoặc chèn từ kết quả truy vấn:

~~~sql
INSERT INTO products (category_id, sku, name, price, stock)
SELECT c.id, 'BOOK-004', 'Thiết kế CSDL', 390000.00, 3
FROM categories AS c
WHERE c.name = 'Sách';
~~~

Nếu không có danh mục Sách, câu lệnh INSERT ... SELECT này thêm **0 hàng**; muốn đảm bảo đúng một hàng, ứng dụng phải kiểm tra update count.

### Nhận ID sinh tự động và xử lý xung đột

PostgreSQL cho phép RETURNING:

~~~sql
INSERT INTO products (category_id, sku, name, price, stock)
SELECT id, 'BOOK-005', 'JDBC nhập môn', 250000.00, 7
FROM categories
WHERE name = 'Sách'
RETURNING id, sku;
~~~

Nếu SKU trùng UNIQUE, mặc định INSERT sẽ lỗi. PostgreSQL hỗ trợ xử lý xung đột có chủ đích:

~~~sql
INSERT INTO products (category_id, sku, name, price, stock)
SELECT id, 'BOOK-001', 'Java căn bản', 350000.00, 8
FROM categories
WHERE name = 'Sách'
ON CONFLICT (sku) DO NOTHING;
~~~

DO NOTHING bỏ qua hàng trùng, **không cập nhật** dữ liệu hiện có. Khi muốn UPSERT phải định nghĩa quy tắc ON CONFLICT DO UPDATE; cú pháp tương đương giữa DBMS không đồng nhất. Không dùng bỏ qua xung đột như cách che các lỗi dữ liệu bất ngờ.

## 4. UPDATE — sửa hàng đã có

~~~sql
UPDATE products
SET price = 360000.00
WHERE sku = 'BOOK-001';
~~~

Tất cả hàng thỏa WHERE đều được sửa. Nếu thiếu WHERE, lệnh có thể sửa toàn bộ bảng:

~~~sql
-- NGUY HIỂM: đặt cùng một giá cho tất cả sản phẩm.
UPDATE products SET price = 360000.00;
~~~

Quy trình sửa dữ liệu thủ công đáng tin cậy là SELECT kiểm tra tập mục tiêu, mở transaction, UPDATE, đối chiếu số hàng ảnh hưởng hoặc dùng RETURNING, sau đó mới COMMIT; nếu phát hiện sai thì ROLLBACK trước khi commit.

### Cập nhật tương đối và điều kiện để bảo vệ nghiệp vụ

~~~sql
UPDATE products
SET stock = stock - 2
WHERE sku = 'BOOK-001' AND stock >= 2
RETURNING sku, stock;
~~~

Trên trạng thái ban đầu, một hàng được cập nhật và stock của BOOK-001 thành **6**. Nếu SKU không có hoặc tồn kho dưới 2, kết quả là 0 hàng. Ứng dụng phải xử lý trường hợp này, không coi mọi câu UPDATE không ném exception đều thành công về nghiệp vụ.

Cách UPDATE trực tiếp theo giá trị cột trong một câu lệnh có điều kiện giúp tránh mô hình đọc stock ra ứng dụng, tính giá trị mới rồi ghi đè một cách thiếu kiểm soát. Với nghiệp vụ nhiều bảng/cạnh tranh, vẫn cần hiểu transaction và mức cô lập để bảo đảm toàn bộ điều kiện nghiệp vụ.

Ví dụ sửa nhiều cột cùng lúc:

~~~sql
UPDATE products
SET name = 'Java nền tảng',
    price = ROUND(price * 1.05, 2)
WHERE sku = 'BOOK-001';
~~~

Cú pháp RETURNING và UPDATE ... FROM/JOIN khác nhau giữa DBMS. Không hiểu UPDATE như chuỗi phép gán biến Java; các biểu thức được DBMS đánh giá theo ngữ nghĩa câu lệnh SQL.

## 5. DELETE — xóa hàng

~~~sql
DELETE FROM products
WHERE sku = 'BOOK-002' AND stock = 0
RETURNING sku;
~~~

Trên trạng thái mẫu ban đầu, câu lệnh xóa một sản phẩm BOOK-002. Không có WHERE, DELETE sẽ nhắm mọi hàng:

~~~sql
-- NGUY HIỂM: xóa toàn bộ hàng trong bảng sản phẩm.
DELETE FROM products;
~~~

**Ràng buộc khóa ngoại** có thể ngăn DELETE trên bảng cha đang có hàng con tham chiếu. Trong schema mẫu, categories bị tham chiếu bởi products và ON DELETE RESTRICT ngăn việc xóa danh mục vẫn có sản phẩm. ON DELETE CASCADE làm xóa con theo cha nếu được thiết kế như vậy, có thể gây mất dữ liệu ngoài dự tính. SET NULL chỉ hợp lệ khi cột con cho phép NULL. Không tự đổi FK thành CASCADE chỉ để câu DELETE chạy được.

Nếu hệ thống cần khôi phục/audit, “xóa mềm” bằng cột deleted_at có thể phù hợp, nhưng đó là một mô hình nghiệp vụ riêng: truy vấn phải lọc hàng còn hiệu lực và quản lý uniqueness, quyền truy cập, lưu trữ đúng thiết kế. DELETE đã COMMIT có thể không khôi phục được nếu thiếu cơ chế recovery/backup.

### DELETE khác TRUNCATE

| Tiêu chí | DELETE | TRUNCATE |
| --- | --- | --- |
| Phạm vi | Có thể lọc bằng WHERE; không có WHERE là toàn bảng | Làm rỗng bảng, không hỗ trợ WHERE |
| Nhóm lệnh | DML | Thường được coi là DDL |
| Trigger, identity, khóa, FK | Theo quy tắc DELETE của DBMS | Có cơ chế riêng, khác DELETE và khác nhau giữa DBMS |
| Khôi phục trong transaction | Phụ thuộc hỗ trợ giao dịch | **Không giả định** mọi DBMS cho rollback giống nhau |

PostgreSQL hỗ trợ rollback TRUNCATE trong transaction phù hợp, nhưng MySQL có cơ chế implicit commit cho nhiều lệnh DDL. Với bảng được tham chiếu bằng FK, TRUNCATE có quy tắc hạn chế/khóa riêng. Chỉ dùng khi đã quyết định xóa toàn bộ nội dung bảng, hiểu tác động trong DBMS đang sử dụng.

## 6. DDL — định nghĩa và thay đổi cấu trúc

- **CREATE TABLE** đặt tên bảng, cột, kiểu dữ liệu, DEFAULT và các constraint; **CREATE INDEX** thêm cấu trúc truy cập.
- **ALTER TABLE** thêm/sửa/xóa cột hoặc constraint, tùy khả năng DBMS.
- **DROP TABLE/INDEX** loại bỏ đối tượng; DROP TABLE còn làm mất dữ liệu của bảng.
- **TRUNCATE** làm rỗng bảng theo quy tắc DDL của DBMS, không có WHERE.

Một ví dụ mở rộng schema theo giai đoạn:

~~~sql
ALTER TABLE products
ADD COLUMN active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX idx_products_active_price
ON products (active, price);

SELECT sku, name
FROM products
WHERE active = TRUE AND price >= 300000
ORDER BY price DESC;
~~~

Truy vấn dùng active chỉ chạy sau khi ALTER hoàn tất. Index có thể giúp một số truy vấn nhưng chiếm dung lượng, tăng chi phí INSERT/UPDATE/DELETE và không chắc được optimizer sử dụng; hãy kiểm tra kế hoạch truy vấn và workload thật.

Các lệnh gỡ cấu trúc sau chỉ để học cú pháp, **không chạy trên dữ liệu muốn giữ**:

~~~sql
DROP INDEX idx_products_active_price;
ALTER TABLE products DROP COLUMN active;
-- DROP TABLE products; -- sẽ loại bỏ bảng và dữ liệu nếu thực thi
~~~

Ở ứng dụng Spring, thay đổi schema của môi trường chung nên đi qua migration có phiên bản, chẳng hạn Flyway hoặc Liquibase. Trước khi áp dụng cần xem xét tương thích giữa bản ứng dụng cũ/mới, backfill dữ liệu, tác động khóa bảng, khả năng roll-forward/rollback và sao lưu. Không giả định mọi CREATE/ALTER/DROP đều rollback được: PostgreSQL hỗ trợ nhiều DDL trong transaction, còn MySQL thường implicit commit quanh nhiều DDL.

## 7. Giao dịch, cập nhật đồng thời và số hàng ảnh hưởng

Một thao tác nghiệp vụ có thể bao gồm nhiều lệnh DML; khi đó cần transaction. Ví dụ chuyển một đơn vị tồn kho giữa hai SKU:

~~~sql
BEGIN;

UPDATE products
SET stock = stock - 1
WHERE sku = 'BOOK-001' AND stock >= 1;

UPDATE products
SET stock = stock + 1
WHERE sku = 'BOOK-002';

-- Ứng dụng phải xác nhận MỖI UPDATE tác động đúng một hàng.
-- Đúng cả hai thì COMMIT; sai hoặc lỗi thì ROLLBACK.
~~~

Ví dụ cố tình **không COMMIT tự động**: transaction không tự kiểm tra yêu cầu “mỗi UPDATE phải ảnh hưởng đúng một hàng”. Nếu một UPDATE chạm 0 hàng nhưng ứng dụng vẫn COMMIT, kết quả có thể sai nghiệp vụ. Tính nguyên tử giao dịch và mức cô lập là hai vấn đề khác nhau; mức cô lập ảnh hưởng cách các transaction đồng thời nhìn thấy dữ liệu và có thể gây race condition/deadlock. Xác định chiến lược retry hợp lý cho lỗi tranh chấp.

Trong JDBC, SELECT trả ResultSet, còn INSERT/UPDATE/DELETE thường có update count. “Không ném lỗi” chưa chắc đồng nghĩa “đã ảnh hưởng đúng hàng mong muốn”. Trong Spring, @Transactional thường đặt ở tầng service để bao trọn đơn vị nghiệp vụ; phải hiểu transaction manager và rollback rule thực tế trước khi phụ thuộc vào annotation.

## 8. Kết nối kiến thức SQL với Spring JdbcTemplate

JdbcTemplate hỗ trợ dùng SQL thủ công trong Spring: mở/đóng tài nguyên JDBC theo đúng vòng đời, bind tham số, ánh xạ ResultSet và chuyển SQLException sang các kiểu DataAccessException của Spring. Đoạn dưới là **một class trong ứng dụng Spring có spring-jdbc, JdbcTemplate/DataSource đã được cấu hình và bảng products đã tồn tại**. Nó không phải chương trình Java độc lập để chạy chỉ bằng javac.

Tệp ProductDao.java, cú pháp Java 17+:

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductDao {
    private final JdbcTemplate jdbc;

    public ProductDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<ProductView> findAvailable(BigDecimal minPrice) {
        return jdbc.query(
            """
            SELECT sku, name, price, stock
            FROM products
            WHERE price >= ? AND stock > 0
            ORDER BY price DESC, sku
            """,
            (rs, rowNum) -> new ProductView(
                rs.getString("sku"),
                rs.getString("name"),
                rs.getBigDecimal("price"),
                rs.getInt("stock")
            ),
            minPrice
        );
    }

    public boolean reserve(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        int updated = jdbc.update(
            """
            UPDATE products
            SET stock = stock - ?
            WHERE sku = ? AND stock >= ?
            """,
            quantity, sku, quantity
        );
        return updated == 1;
    }

    public record ProductView(
        String sku, String name, BigDecimal price, int stock
    ) {}
}
~~~

Ký hiệu **?** là vị trí bind value qua PreparedStatement. MinPrice, quantity và sku được truyền dưới dạng tham số, tránh nối chuỗi tạo SQL từ dữ liệu đầu vào. Đây là cách phòng SQL injection và giữ xử lý kiểu dữ liệu rõ ràng. Tham số không đại diện được tên bảng, cột hoặc từ khóa SQL; nếu người dùng được chọn cột ORDER BY, phải ánh xạ một tập tên cột được cho phép.

reserve trả true nếu đúng một hàng đã được giảm tồn và false nếu SKU không tồn tại/thiếu hàng. Điều kiện stock >= ? bảo vệ tồn kho không âm. Với quy trình có nhiều bước, tầng service cần định nghĩa transaction và các hành vi khi update count sai. Dù dùng JPA thay cho JdbcTemplate, hiểu các câu SQL cơ bản vẫn cần thiết để đọc query ORM sinh ra, xác định lỗi constraint, quan hệ và hiệu năng.

## 9. Lỗi phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| UPDATE/DELETE thiếu WHERE | Thay đổi hoặc xóa cả bảng | SELECT tập mục tiêu trước, giao dịch và xác minh affected rows |
| WHERE col = NULL | Không tìm ra hàng NULL | Dùng IS NULL / IS NOT NULL |
| Dựa vào thứ tự SELECT không ORDER BY | Phân trang hoặc hiển thị sai kỳ vọng | ORDER BY rõ, có khóa duy nhất khi cần |
| COUNT(*) sau LEFT JOIN để đếm bảng phải | Đếm thêm hàng không khớp | Dùng COUNT(p.id) hoặc aggregate có điều kiện |
| Ghép dữ liệu người dùng vào SQL | SQL injection, lỗi escape/kiểu | Bind parameter với PreparedStatement |
| INSERT không liệt kê cột | Phụ thuộc thứ tự/biến động schema | Luôn nêu cột sẽ ghi |
| Bỏ qua update count | Tưởng thành công dù 0 hàng được sửa | Kiểm tra đúng invariant của nghiệp vụ |
| Tùy tiện dùng ON DELETE CASCADE | Có thể xóa hàng liên quan ngoài ý muốn | Thiết kế chính sách FK rõ ràng |
| Nghĩ DDL luôn rollback được | Migration lỗi khó phục hồi | Kiểm tra DBMS và chuẩn bị migration |
| Tạo index cho mọi cột | Ghi chậm, tốn dung lượng | Đo workload, đọc EXPLAIN |

## 10. Bài tập tự kiểm tra với dữ liệu mẫu

Các đáp án dưới đây áp dụng trên **trạng thái ban đầu ba sản phẩm** ở phần 1. Nếu đã thực thi các lệnh INSERT/UPDATE/DELETE thử nghiệm, hãy phục hồi dữ liệu mẫu trong môi trường thực hành trước khi đối chiếu.

**Bài 1. Tìm sản phẩm đang có hàng và giá ít nhất 300.000, đắt nhất trước.**

~~~sql
SELECT sku, price
FROM products
WHERE stock > 0 AND price >= 300000
ORDER BY price DESC, sku;
~~~

Đáp án: DEV-001 (1.200.000), rồi BOOK-001 (350.000).

**Bài 2. Tìm sản phẩm hết hàng.**

~~~sql
SELECT sku, name
FROM products
WHERE stock = 0
ORDER BY sku;
~~~

Đáp án: BOOK-002.

**Bài 3. Tìm danh mục có ít nhất hai sản phẩm, tính cả sản phẩm hết hàng.**

~~~sql
SELECT c.name, COUNT(p.id) AS product_count
FROM categories AS c
LEFT JOIN products AS p ON p.category_id = c.id
GROUP BY c.id, c.name
HAVING COUNT(p.id) >= 2;
~~~

Đáp án: Sách, product_count = 2. Nếu thay bài toán thành “hai sản phẩm **còn hàng**”, cần thay điều kiện join hoặc phép đếm cho đúng.

**Bài 4. Giảm tồn BOOK-001 đi hai đơn vị, không cho số âm.**

~~~sql
UPDATE products
SET stock = stock - 2
WHERE sku = 'BOOK-001' AND stock >= 2
RETURNING sku, stock;
~~~

Đáp án ở lần đầu: một hàng được cập nhật, stock từ 8 còn 6. Chạy lại sẽ tiếp tục trừ cho đến khi stock < 2, lúc đó affected rows bằng 0. Lệnh này không idempotent; nếu retry sau timeout cần tránh trừ hai lần khi lần trước đã commit.

**Bài 5. Phân biệt hai loại thay đổi.** UPDATE products SET price = ... là DML vì sửa giá trị hàng; ALTER TABLE products ADD COLUMN active BOOLEAN ... là DDL vì sửa schema. Schema mới cần tương thích với mã ứng dụng đang hoạt động.

### Checklist khi viết SQL trong ứng dụng Spring

1. Xác định bảng, khóa, những cột cần đọc/ghi và cách xử lý NULL.
2. Kiểm tra PK, FK, UNIQUE, NOT NULL, CHECK và quy tắc nghiệp vụ.
3. Dùng tham số được bind cho dữ liệu đầu vào; tránh SQL ghép chuỗi.
4. Với UPDATE/DELETE, xác nhận WHERE, affected rows, giao dịch và xử lý đồng thời.
5. Với SELECT, kiểm tra JOIN, ORDER BY, phân trang, lượng dữ liệu và kế hoạch thực thi.
6. Với DDL, xác nhận cú pháp riêng của DBMS và triển khai qua migration có kiểm soát.

Nắm vững SQL cơ bản giúp giải thích chính xác hành vi của tầng data-access Spring, từ kết quả truy vấn, xử lý update count đến ràng buộc và transaction trong database.
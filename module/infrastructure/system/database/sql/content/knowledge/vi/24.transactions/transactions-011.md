# Cập nhật có điều kiện theo phiên bản để tránh ghi đè

## 1. Vấn đề: hai người cùng sửa một hàng dữ liệu

Trong ứng dụng nhiều người dùng, tình huống sau rất phổ biến:

1. Nhân viên A và B cùng mở màn hình một sản phẩm.
2. Cả hai đều nhìn thấy dữ liệu tại **cùng thời điểm cũ**.
3. A lưu thay đổi trước.
4. B lưu từ biểu mẫu đã mở trước đó.
5. Nếu hệ thống không kiểm tra dữ liệu đã thay đổi hay chưa, thao tác của B có thể **ghi đè thay đổi của A**.

Hiện tượng này được gọi là **lost update** — cập nhật bị mất vì một lệnh ghi sau dựa trên trạng thái cũ.

Ví dụ ban đầu:

| product_id | unit_price | stock_qty | version_no |
| ---: | ---: | ---: | ---: |
| 101 | 100.00 | 10 | 1 |

A và B cùng đọc hàng trên. A muốn bán hai sản phẩm, còn B muốn sửa giá:

~~~text
T0  Database: price=100, qty=10, version=1
         |
         +------ A đọc (100,10,1)
         |
         +------ B đọc (100,10,1)
         |
T1  A ghi toàn bộ biểu mẫu: (price=100, qty=8)
         Database: price=100, qty=8
         |
T2  B ghi toàn bộ biểu mẫu cũ: (price=120, qty=10)
         Database: price=120, qty=10
                                  ^^^^
                        Thay đổi tồn của A bị mất!
~~~

Điều nguy hiểm là **cả hai câu UPDATE đều có thể chạy thành công**. Nếu câu SQL chỉ có `WHERE product_id = 101`, cơ sở dữ liệu không biết B đang dùng một biểu mẫu đã lỗi thời.

Giải pháp của bài này là **cập nhật có điều kiện theo phiên bản**, còn gọi là *optimistic concurrency control*, *optimistic locking* hoặc một dạng **compare-and-swap (CAS)** ở cấp hàng.

Ý tưởng:

> Mỗi hàng có một `version_no`. Ứng dụng đọc cả dữ liệu lẫn phiên bản. Khi ghi, SQL chỉ sửa hàng nếu phiên bản hiện tại vẫn bằng phiên bản đã đọc, và **tăng phiên bản ngay trong cùng câu UPDATE**.

Mẫu trọng tâm:

~~~sql
UPDATE inventory_products
SET
    unit_price = :new_price,
    stock_qty = :new_qty,
    version_no = version_no + 1
WHERE product_id = :product_id
  AND version_no = :expected_version;
~~~

Nếu hàng đã bị ai khác thay đổi và phiên bản tăng, điều kiện `version_no = :expected_version` không còn đúng. Khi đó **không có hàng nào bị ghi đè**.

Bài học thuộc chương **Giao dịch SQL**, tập trung vào:

- Mô hình lost update và cạnh tranh giữa các transaction;
- Thiết kế cột phiên bản;
- Cú pháp `UPDATE ... WHERE id = ? AND version = ?`;
- Đọc số hàng chịu tác động và phân loại lỗi;
- Quan hệ với transaction, isolation level, khóa và retry;
- Thao tác cập nhật nhiều cột, tồn kho và tiền;
- Các biến thể PostgreSQL, MySQL, SQL Server, SQLite, Oracle;
- Cách tích hợp Java/JDBC, JPA và HTTP API;
- Những tình huống giới hạn, bài tập và nguyên tắc thực hành.

## 2. Dữ liệu mẫu dùng trong bài

Các câu DDL và ví dụ SQL chính sử dụng **PostgreSQL**. Phần đối chiếu cuối bài sẽ nêu cú pháp tương ứng ở các DBMS khác.

### 2.1. Tạo bảng có cột phiên bản

~~~sql
CREATE TABLE inventory_products (
    product_id     BIGINT PRIMARY KEY,
    sku            VARCHAR(30) NOT NULL UNIQUE,
    product_name   VARCHAR(120) NOT NULL,
    unit_price     NUMERIC(12, 2) NOT NULL,
    stock_qty      INTEGER NOT NULL,
    product_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    version_no     BIGINT NOT NULL DEFAULT 1,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_product_price
        CHECK (unit_price >= 0),
    CONSTRAINT chk_product_stock
        CHECK (stock_qty >= 0),
    CONSTRAINT chk_product_status
        CHECK (product_status IN ('ACTIVE', 'ARCHIVED')),
    CONSTRAINT chk_product_version
        CHECK (version_no >= 1)
);
~~~

### 2.2. Thêm dữ liệu ban đầu

~~~sql
INSERT INTO inventory_products (
    product_id, sku, product_name,
    unit_price, stock_qty, product_status,
    version_no
)
VALUES
    (101, 'BK-001', 'So tay',       100.00, 10, 'ACTIVE', 1),
    (102, 'PN-002', 'But bi',        20.00,  5, 'ACTIVE', 4),
    (103, 'KB-003', 'Ban phim',     500.00,  2, 'ACTIVE', 8);
~~~

| ID | SKU | Giá | Tồn kho | Trạng thái | Phiên bản |
| ---: | --- | ---: | ---: | --- | ---: |
| 101 | BK-001 | 100.00 | 10 | ACTIVE | 1 |
| 102 | PN-002 | 20.00 | 5 | ACTIVE | 4 |
| 103 | KB-003 | 500.00 | 2 | ACTIVE | 8 |

Vai trò của các cột:

- `product_id` là **khóa định danh ổn định** để tìm đúng hàng.
- `version_no` là **mã trạng thái cạnh tranh**, không phải khóa chính; nó tăng khi một thay đổi cần được coi là cập nhật mới.
- `unit_price`, `stock_qty`, `product_status` là dữ liệu nghiệp vụ.
- `updated_at` dùng để hiển thị/audit thời gian thay đổi; **không dùng làm phiên bản ở các ví dụ chính**.
- `CHECK` và `NOT NULL` vẫn giữ toàn vẹn dữ liệu dù thao tác sử dụng CAS.

### 2.3. Đọc hàng và phiên bản trong cùng kết quả

~~~sql
SELECT
    product_id,
    sku,
    product_name,
    unit_price,
    stock_qty,
    product_status,
    version_no
FROM inventory_products
WHERE product_id = 101;
~~~

Giả sử kết quả vẫn là:

~~~text
product_id = 101
unit_price = 100.00
stock_qty  = 10
version_no = 1
~~~

Client cần **giữ lại version_no = 1** cùng dữ liệu đang hiển thị. Đến khi người dùng lưu biểu mẫu, `1` trở thành `expected_version` của yêu cầu ghi.

Không nên đọc dữ liệu rồi bỏ `version_no`, sau đó lúc lưu lại truy vấn lấy **phiên bản mới nhất** và dùng nó để ghi dữ liệu cũ. Làm như vậy vô hiệu hóa chính cơ chế phát hiện dữ liệu đã thay đổi.

## 3. UPDATE có điều kiện theo phiên bản hoạt động ra sao?

### 3.1. Điều kiện kép: đúng hàng và đúng phiên bản

Ví dụ A cập nhật tồn kho từ 10 xuống 8:

~~~sql
UPDATE inventory_products
SET
    unit_price = 100.00,
    stock_qty = 8,
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 101
  AND version_no = 1
RETURNING
    product_id, unit_price, stock_qty, version_no;
~~~

Trên dữ liệu ban đầu, PostgreSQL trả:

| product_id | unit_price | stock_qty | version_no |
| ---: | ---: | ---: | ---: |
| 101 | 100.00 | 8 | 2 |

Câu lệnh đồng thời thực hiện **ba nhiệm vụ**:

1. Xác định đúng hàng bằng `product_id = 101`.
2. **Chỉ ghi nếu chưa có cập nhật khác** làm phiên bản khác `1`.
3. Nếu ghi thành công, tăng `version_no` thành `2` ngay trong **cùng câu UPDATE nguyên tử**.

Đây không phải hai câu lệnh “kiểm tra phiên bản rồi sau đó cập nhật”. Kiểm tra nằm trong điều kiện của chính lệnh ghi.

### 3.2. Lệnh ghi dùng phiên bản cũ phải thất bại về mặt điều kiện

B cũng đọc bản gốc phiên bản 1 và muốn lưu giá 120 cùng tồn 10:

~~~sql
UPDATE inventory_products
SET
    unit_price = 120.00,
    stock_qty = 10,
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 101
  AND version_no = 1
RETURNING
    product_id, unit_price, stock_qty, version_no;
~~~

Sau khi A đã commit và phiên bản của hàng là 2, lệnh B **không còn hàng nào khớp cả khóa lẫn phiên bản**:

~~~text
UPDATE affected rows = 0
RETURNING: không có hàng
Dữ liệu sau cùng vẫn: price=100, qty=8, version=2
~~~

B không được âm thầm xem đây là “lưu thành công”. Ứng dụng nên thông báo bản ghi đã thay đổi, tải dữ liệu hiện tại, rồi cho người dùng quyết định giữ, sửa hoặc hợp nhất thay đổi.

### 3.3. Không tăng version = không bảo vệ được lần ghi sau

Ví dụ sai:

~~~sql
-- Sai thiết kế: kiểm tra version nhưng không đổi version.
UPDATE inventory_products
SET stock_qty = 8
WHERE product_id = 101
  AND version_no = 1;
~~~

Nếu không có trigger hoặc cơ chế khác tăng version, sau lệnh này hàng vẫn mang phiên bản 1. Một client khác giữ version 1 vẫn có thể ghi đè. `WHERE version_no = 1` **chỉ có tác dụng lâu dài nếu mọi cập nhật có ý nghĩa đều làm token thay đổi**.

Cách đúng ở mẫu dùng version số nguyên:

~~~sql
UPDATE inventory_products
SET
    stock_qty = 8,
    version_no = version_no + 1
WHERE product_id = 101
  AND version_no = 1;
~~~

### 3.4. Không tách kiểm tra và ghi thành hai thao tác thiếu bảo vệ

Mẫu không đủ an toàn:

~~~sql
-- Bước 1: kiểm tra version.
SELECT version_no
FROM inventory_products
WHERE product_id = 101;

-- Bước 2: cập nhật nhưng quên điều kiện version.
UPDATE inventory_products
SET stock_qty = 8
WHERE product_id = 101;
~~~

Giữa SELECT và UPDATE, một transaction khác có thể sửa hàng. Việc đã “kiểm tra thấy phiên bản đúng” **không đủ** nếu lệnh UPDATE cuối không kiểm tra lại trong chính `WHERE` hoặc không dùng một cơ chế khóa tương đương thích hợp.

Câu UPDATE có `WHERE id = ? AND version_no = ?` là nơi **kiểm tra và ghi được kết hợp nguyên tử theo cơ chế transaction của DBMS**.

## 4. Hai session cùng cập nhật: diễn biến từng bước

Dùng hai kết nối PostgreSQL khác nhau, A và B. Để minh họa độc lập, giả sử hàng 101 đã được khôi phục về `(price=100, qty=10, version=1)`.

### 4.1. Cả hai đọc cùng version

Session A:

~~~sql
BEGIN;

SELECT unit_price, stock_qty, version_no
FROM inventory_products
WHERE product_id = 101;
-- 100.00, 10, 1
~~~

Session B:

~~~sql
BEGIN;

SELECT unit_price, stock_qty, version_no
FROM inventory_products
WHERE product_id = 101;
-- 100.00, 10, 1
~~~

Giả sử đang dùng isolation level `READ COMMITTED` của PostgreSQL cho kịch bản này.

### 4.2. Session A cập nhật và commit

Session A:

~~~sql
UPDATE inventory_products
SET
    stock_qty = 8,
    version_no = version_no + 1
WHERE product_id = 101
  AND version_no = 1
RETURNING stock_qty, version_no;
-- 8, 2

COMMIT;
~~~

Session B vẫn giữ giá trị đã đọc lúc trước: `expected_version=1`.

### 4.3. Session B cố lưu dữ liệu cũ

Session B:

~~~sql
UPDATE inventory_products
SET
    unit_price = 120.00,
    stock_qty = 10,
    version_no = version_no + 1
WHERE product_id = 101
  AND version_no = 1
RETURNING product_id, unit_price, stock_qty, version_no;
-- 0 hàng, nếu A đã commit như mô tả.

ROLLBACK;
~~~

Sau đó mở phiên đọc mới:

~~~sql
SELECT unit_price, stock_qty, version_no
FROM inventory_products
WHERE product_id = 101;
-- 100.00, 8, 2
~~~

B không thể vô tình đưa số lượng từ 8 trở lại 10.

### 4.4. Nếu hai UPDATE chạy cùng lúc thật sự thì sao?

Khi hai session cùng cố cập nhật một hàng, DBMS dùng cơ chế khóa và điều khiển đồng thời để sắp xếp/xử lý việc ghi. Trong PostgreSQL `READ COMMITTED`, session thứ hai có thể **chờ khóa**, rồi đánh giá lại điều kiện trên phiên bản hàng phù hợp sau khi transaction trước kết thúc.

Nếu transaction A commit với version 2, điều kiện của B `version_no = 1` sẽ không khớp nên kết quả thông thường là 0 hàng. Ở isolation level khác (chẳng hạn `REPEATABLE READ` hoặc `SERIALIZABLE` của PostgreSQL), session có thể nhận **lỗi serialization** thay vì chỉ 0 hàng, tùy lịch thực thi.

Do đó client phải xử lý **cả hai lớp tín hiệu**:

- **0 hàng cập nhật**: điều kiện CAS không còn khớp, hoặc hàng không tồn tại.
- **Lỗi transaction/concurrency**: có thể cần rollback và retry theo quy tắc DBMS.

Không kết luận `UPDATE ... WHERE version` đảm bảo tất cả DBMS, mọi isolation level và mọi lịch chạy luôn trả **0** thay vì báo lỗi.

## 5. Quy tắc xử lý số hàng được cập nhật

### 5.1. Trường hợp 1 hàng

Nếu cập nhật theo `PRIMARY KEY` và phiên bản:

~~~sql
UPDATE inventory_products
SET
    unit_price = 125.00,
    version_no = version_no + 1
WHERE product_id = 101
  AND version_no = 1;
~~~

với hàng đang có version 1, kỳ vọng **đúng 1 hàng**.

Ứng dụng có thể xác nhận thao tác lưu đã được chấp nhận, sau đó dùng version mới do DBMS trả về hoặc đọc lại.

### 5.2. Trường hợp 0 hàng

Với câu SQL trên, `0` có thể mang nhiều ý nghĩa:

- `product_id=101` không tồn tại;
- Hàng tồn tại nhưng `version_no != 1`;
- Có thêm điều kiện `WHERE` khác không thỏa, ví dụ `product_status='ACTIVE'`;
- Quy tắc row-level security/khả năng nhìn thấy hàng khiến hàng không thuộc phạm vi cập nhật.

**Không tự động kết luận mọi `0 row` là “đã bị người khác sửa”.** Nếu API cần phân biệt `404 Not Found` và `409 Conflict`, có thể truy vấn trạng thái hiện tại theo khóa và quyền truy cập, với lưu ý rằng trạng thái có thể tiếp tục thay đổi giữa các truy vấn.

### 5.3. Trường hợp nhiều hơn 1 hàng

Nếu `product_id` là khóa chính và câu `WHERE product_id=? AND version_no=?` đã ràng buộc đúng, một thao tác dự kiến sửa một sản phẩm **không nên ảnh hưởng nhiều hơn một hàng**.

Nếu API/JDBC báo nhiều hàng, phải xem lại SQL, alias, điều kiện lọc, driver và thiết kế khóa. Đối với thao tác quan trọng, coi đây là tình huống bất thường chứ không “lấy hàng đầu tiên”.

### 5.4. Trả version mới bằng RETURNING

PostgreSQL:

~~~sql
UPDATE inventory_products
SET
    unit_price = 120.00,
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 101
  AND version_no = 1
RETURNING
    product_id,
    unit_price,
    stock_qty,
    version_no,
    updated_at;
~~~

Nếu câu có 1 hàng kết quả, client nhận trực tiếp **phiên bản mới** mà không cần đoán bằng cách cộng một số ở Java. Nếu không có hàng, client biết điều kiện cập nhật không khớp.

Với các hệ không hỗ trợ RETURNING theo cùng cú pháp, dùng API số hàng và cách lấy dữ liệu theo dialect trong một transaction/phạm vi nhất quán phù hợp.

## 6. Sửa hai thuộc tính khác nhau vẫn có thể xung đột

Một lập luận thường nghe:

> A chỉ sửa tồn kho, B chỉ sửa đơn giá; chúng không sửa cùng một cột nên không cần kiểm tra phiên bản.

Điều này tùy cách ứng dụng xây UPDATE.

### 6.1. Ghi toàn bộ biểu mẫu từ dữ liệu cũ gây lost update

A đọc:

~~~text
price=100, qty=10, version=1
~~~

A sửa tồn còn 8. B cũng đọc:

~~~text
price=100, qty=10, version=1
~~~

B sửa giá thành 120.

Nếu B gửi cả giá và tồn cũ:

~~~sql
UPDATE inventory_products
SET
    unit_price = 120,
    stock_qty = 10
WHERE product_id = 101;
~~~

thì B có thể ghi đè tồn mới của A. Đây là **lost update trên một trường mà B không hề muốn sửa**.

### 6.2. PATCH đúng cột giảm nguy cơ nhưng không thay CAS trong mọi tình huống

Nếu B chỉ sửa giá:

~~~sql
UPDATE inventory_products
SET unit_price = 120.00
WHERE product_id = 101;
~~~

thì câu này **không trực tiếp gán lại `stock_qty`**, nên có thể không làm mất thay đổi tồn kho của A. Tuy vậy vẫn có những trường hợp cập nhật cần kiểm tra trạng thái chung của hàng:

- Giá mới được tính dựa trên giá cũ;
- Trạng thái sản phẩm phụ thuộc tồn kho;
- Màn hình hiển thị cả nhiều trường và người dùng chấp nhận toàn bộ bản ghi;
- Một quy tắc nghiệp vụ yêu cầu thay đổi giá và tồn đi cùng phiên bản.

Do đó câu hỏi không chỉ là “có ghi cùng cột không”, mà là **“quyết định ghi dựa trên trạng thái nào và trường nào phải nhất quán với nhau?”**

### 6.3. Row-level version có thể gây xung đột bảo thủ

Nếu mọi cập nhật bất kỳ cột nào đều tăng `version_no`, thì A sửa tồn kho sẽ khiến B sửa giá bằng version cũ bị từ chối — ngay cả khi hai sửa đổi có thể hợp nhất an toàn.

Đây là **đánh đổi có chủ đích** của một token phiên bản toàn hàng:

- Ưu điểm: đơn giản, bảo vệ nhất quán cho cả hàng.
- Hạn chế: có thể báo xung đột trong những thay đổi độc lập.
- Giải pháp nghiệp vụ: đọc lại, hợp nhất các trường không xung đột, rồi gửi lại với version mới.

Nếu hệ thống thực sự cần cập nhật độc lập các miền dữ liệu rất lớn, có thể cân nhắc các token phiên bản riêng theo nhóm thuộc tính, event sourcing hoặc thiết kế bảng tách miền. Không tăng độ phức tạp trước khi có yêu cầu rõ.

## 7. Ứng dụng phải làm gì sau xung đột?

### 7.1. Không tự động ghi đè theo “last writer wins”

Khi update trả 0 hàng, một cách xử lý nguy hiểm là bỏ điều kiện phiên bản rồi thử lại:

~~~sql
-- KHÔNG NÊN: bỏ guard sau khi phát hiện conflict.
UPDATE inventory_products
SET
    unit_price = 120.00,
    stock_qty = 10
WHERE product_id = 101;
~~~

Lệnh này chính là thao tác ghi đè mà `version_no` được thêm vào để ngăn chặn.

### 7.2. Đọc lại, giải thích thay đổi, cho người dùng quyết định

Ví dụ client B giữ:

~~~text
Bản đã mở: price=100, qty=10, version=1
B muốn:    price=120, qty=10
~~~

Sau khi A cập nhật, đọc lại:

~~~text
Bản hiện tại: price=100, qty=8, version=2
~~~

B có thể đề xuất hợp nhất:

~~~text
Giữ tồn mới của A: qty=8
Áp dụng giá mong muốn của B: price=120
Expected version mới: 2
~~~

Một lệnh CAS mới:

~~~sql
UPDATE inventory_products
SET
    unit_price = 120.00,
    stock_qty = 8,
    version_no = version_no + 1
WHERE product_id = 101
  AND version_no = 2
RETURNING product_id, unit_price, stock_qty, version_no;
~~~

Nếu không có cập nhật khác chen vào, kết quả là `price=120`, `qty=8`, `version=3`.

**Đây là một yêu cầu mới dựa trên dữ liệu mới**, không phải retry mù quáng cùng payload cũ. Nếu có người thứ ba cập nhật giữa lúc B đọc lại và lưu, câu CAS mới vẫn có thể trả 0 hàng.

### 7.3. Ba chính sách xử lý xung đột

| Chính sách | Cách xử lý | Khi phù hợp |
| --- | --- | --- |
| Từ chối và yêu cầu tải lại | Trả conflict, không sửa dữ liệu | Hồ sơ cần xác nhận bằng con người |
| Hợp nhất có kiểm soát | Đọc version mới, so từng trường, tạo patch mới | Các thuộc tính độc lập và có quy tắc merge |
| Tính lại thao tác nghiệp vụ | Tải trạng thái mới, kiểm tra lại bất biến, thực thi CAS mới | Tồn kho, giới hạn số lượng, số dư hoặc thuật toán cập nhật |

Không phải xung đột nào cũng có thể hợp nhất tự động. Với số tiền, quyền truy cập, số dư hoặc quyết định đã được người dùng phê duyệt trên dữ liệu cũ, thường cần xác nhận lại.

## 8. JDBC: thực hiện compare-and-swap an toàn

### 8.1. Mẫu Java dùng PreparedStatement

Ví dụ muốn sửa giá và tồn của sản phẩm 101 theo version đã đọc:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class ProductRepository {

    public static boolean updateIfVersionMatches(
            Connection connection,
            long productId,
            long expectedVersion,
            BigDecimal newPrice,
            int newQuantity) throws SQLException {

        String sql = """
            UPDATE inventory_products
            SET unit_price = ?,
                stock_qty = ?,
                version_no = version_no + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE product_id = ?
              AND version_no = ?
            """;

        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {

            ps.setBigDecimal(1, newPrice);
            ps.setInt(2, newQuantity);
            ps.setLong(3, productId);
            ps.setLong(4, expectedVersion);

            int affected = ps.executeUpdate();

            if (affected == 1) {
                return true;
            }
            if (affected == 0) {
                return false;
            }

            throw new IllegalStateException(
                "Unexpected row count: " + affected
            );
        }
    }
}
~~~

Mã minh họa trả `true` nếu lệnh sửa **đúng một hàng** và `false` nếu **không có hàng khớp**. Nó **không tự phân biệt** hàng đã bị xóa, phiên bản sai hoặc điều kiện quyền hạn khác.

Các điểm quan trọng:

- `productId`, `expectedVersion`, giá và tồn được bind bằng tham số, không nối chuỗi vào SQL.
- `version_no = version_no + 1` tính **ngay tại database**, không tin tưởng một version mới do client đoán.
- `WHERE version_no = ?` dùng **version client đã nhìn thấy trước lúc sửa**.
- Không chuyển `affected == 0` thành thành công nếu hợp đồng yêu cầu phát hiện stale write.
- `SQLException` vẫn phải được xử lý cho deadlock, serialization, constraint, kết nối hoặc lỗi khác.

### 8.2. Số hàng tác động theo driver

Các DBMS/driver có thể có quy tắc khác nhau về “matched rows” và “changed rows”, nhất là MySQL khi update gán lại cùng một giá trị. Tuy nhiên trong mẫu này, **mỗi lần CAS thành công đều tăng `version_no`**, nên một hàng khớp thực sự có thay đổi; điều đó làm phép kiểm tra số hàng ít nhập nhằng hơn.

Vẫn cần kiểm tra hợp đồng cụ thể của JDBC driver, cấu hình và các cơ chế trigger. Không suy `affected = 1` luôn có nghĩa toàn bộ transaction đã **commit** nếu kết nối đang ở chế độ transaction thủ công.

### 8.3. Transaction và commit thuộc về ai?

Đoạn trên **không tự gọi commit**. Nếu `autoCommit=true`, driver thường commit statement theo chế độ kết nối. Nếu `autoCommit=false`, một transaction bên ngoài cần commit hoặc rollback.

Để xử lý nhiều bước liên quan:

~~~java
boolean oldAutoCommit = connection.getAutoCommit();
connection.setAutoCommit(false);

try {
    boolean updated = ProductRepository.updateIfVersionMatches(
        connection,
        101L,
        1L,
        new BigDecimal("120.00"),
        8
    );

    if (!updated) {
        connection.rollback();
        throw new IllegalStateException(
            "Product changed or no longer exists"
        );
    }

    // Các thay đổi liên quan khác trong cùng transaction.

    connection.commit();
} catch (SQLException | RuntimeException e) {
    connection.rollback();
    throw e;
} finally {
    connection.setAutoCommit(oldAutoCommit);
}
~~~

Đây là ví dụ khái niệm về transaction boundary. Trong ứng dụng thực, connection lifecycle, lỗi rollback, pool và việc khôi phục `autoCommit` cần được quản lý ở tầng hạ tầng hoặc transaction manager của framework, không sao chép nguyên mẫu này vào mọi nơi.

### 8.4. Dùng RETURNING trên PostgreSQL để nhận version mới

Khi làm việc trực tiếp với PostgreSQL:

~~~java
String sql = """
    UPDATE inventory_products
    SET unit_price = ?,
        stock_qty = ?,
        version_no = version_no + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE product_id = ?
      AND version_no = ?
    RETURNING version_no
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("120.00"));
    ps.setInt(2, 8);
    ps.setLong(3, 101L);
    ps.setLong(4, 1L);

    try (java.sql.ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long newVersion = rs.getLong("version_no");
            System.out.println(newVersion);
        } else {
            System.out.println("Conflict or not found");
        }
    }
}
~~~

Với phiên bản ban đầu 1 và một lần cập nhật thành công, kết quả là version 2. Nếu trong transaction, vẫn cần commit trước khi tuyên bố thay đổi đã được lưu bền vững theo hợp đồng ứng dụng.

## 9. Transaction isolation và optimistic locking

### 9.1. READ COMMITTED không tự chống mọi stale form

Trong PostgreSQL, `READ COMMITTED` cho phép mỗi statement thấy một snapshot phù hợp theo quy tắc của nó. Nó không tự biết rằng một người dùng đã mở form từ **mười phút trước**.

Ngay cả khi ứng dụng thực hiện:

~~~sql
BEGIN;
SELECT ... WHERE product_id = 101;
COMMIT;
~~~

rồi đến khi người dùng nhấn lưu lại mở một transaction mới, dữ liệu cũ vẫn có thể bị ghi đè nếu UPDATE chỉ dựa trên ID.

**Version check là cơ chế bảo vệ qua ranh giới nhiều request và nhiều transaction**, rất phù hợp với biểu mẫu web/mobile hoặc worker xử lý bất đồng bộ.

### 9.2. REPEATABLE READ/SERIALIZABLE có thể phát hiện xung đột nhưng không thay thiết kế ứng dụng

Isolation mạnh hơn có thể làm một số lịch ghi bị từ chối bằng serialization failure. Nhưng:

- Form được đọc trong transaction A, người dùng chờ rồi ghi ở transaction B: isolation của transaction B không biết người dùng dựa trên bản form cũ nếu không mang version/condition sang.
- Transaction serializable thường cần logic **retry toàn transaction** khi gặp lỗi serialization.
- Việc dùng isolation mạnh hơn có chi phí/tranh chấp và hành vi khác giữa DBMS.
- Không thể lấy một isolation level làm tuyên bố “mọi lost update ứng dụng đều biến mất” mà không xét phạm vi transaction và câu lệnh thực tế.

### 9.3. Optimistic locking và pessimistic locking

| Đặc điểm | Optimistic version check | Pessimistic row locking |
| --- | --- | --- |
| Ý tưởng | Không giữ khóa dài lúc người dùng suy nghĩ; lúc ghi so version | Khóa/giới hạn ghi cạnh tranh từ thời điểm đọc phù hợp |
| Câu SQL tiêu biểu | `UPDATE ... WHERE id=? AND version=?` | `SELECT ... FOR UPDATE` ở DBMS hỗ trợ |
| Khi xung đột | 0 hàng hoặc lỗi transaction, client xử lý | Giao dịch khác có thể phải chờ/timeout/deadlock |
| Phù hợp | Form web, thay đổi ít tranh chấp, request tách rời | Đọc-rồi-ghi trong transaction ngắn cần độc quyền hàng |
| Rủi ro | Xung đột phải được giải quyết đúng; mọi đường ghi phải bump version | Lock lâu, contention, deadlock, timeout |
| Điều không làm được | Không tự bảo vệ bất biến trên nhiều hàng | Không tự đảm bảo chính sách ứng dụng nếu khóa sai tập dữ liệu |

PostgreSQL:

~~~sql
BEGIN;

SELECT
    product_id, unit_price, stock_qty, version_no
FROM inventory_products
WHERE product_id = 101
FOR UPDATE;

-- Kiểm tra và ghi trong cùng transaction.

COMMIT;
~~~

`FOR UPDATE` giúp khóa hàng được chọn trong phạm vi transaction theo cơ chế PostgreSQL. Không nên giữ transaction/row lock mở trong suốt thời gian người dùng đang chỉnh một form; đó là lý do optimistic locking rất hữu ích.

### 9.4. Có thể dùng cả hai không?

Có. Một transaction có thể dùng row lock để phối hợp một chuỗi thao tác ngắn, đồng thời vẫn có version để phát hiện payload được tạo từ dữ liệu cũ trước transaction. Nhưng **không cần áp dụng cả hai cho mọi truy vấn**; chọn cơ chế theo xung đột dự kiến, độ dài transaction và tính chất nghiệp vụ.

## 10. Tồn kho: kiểm tra version cùng điều kiện nghiệp vụ

### 10.1. Không được bán vượt tồn

Sản phẩm 101 có `stock_qty=10`, `version_no=1`. Muốn trừ 3 sản phẩm:

~~~sql
UPDATE inventory_products
SET
    stock_qty = stock_qty - 3,
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 101
  AND version_no = 1
  AND stock_qty >= 3
  AND product_status = 'ACTIVE'
RETURNING product_id, stock_qty, version_no;
~~~

Nếu thành công, tồn mới là 7 và version mới là 2.

Điều kiện trong `WHERE` gồm:

- `product_id=101`: đúng sản phẩm;
- `version_no=1`: đúng phiên bản đã quan sát;
- `stock_qty>=3`: còn đủ hàng;
- `product_status='ACTIVE'`: được phép bán theo chính sách ví dụ.

Nếu 0 hàng được cập nhật, có thể do thiếu hàng, phiên bản cũ, trạng thái không hợp lệ hoặc không tìm thấy. Ứng dụng phải đọc lại/phân loại phù hợp.

### 10.2. Khi nào không cần đọc version trước cho mỗi lần trừ tồn?

Một thao tác nguyên tử dạng:

~~~sql
UPDATE inventory_products
SET
    stock_qty = stock_qty - 3,
    version_no = version_no + 1
WHERE product_id = 101
  AND stock_qty >= 3
  AND product_status = 'ACTIVE';
~~~

có thể là giải pháp đủ phù hợp cho một nghiệp vụ **“trừ 3 trên trạng thái hiện tại, miễn đủ tồn”**, nơi người dùng không phải phê duyệt một giá trị số tồn cụ thể đã đọc trước đó.

Điểm quan trọng là phép trừ và điều kiện đủ tồn nằm trong **cùng một UPDATE**, tránh read-modify-write tại client dựa trên số tồn cũ. Tuy nhiên:

- Đây không phải cùng ý nghĩa với “chỉ bán nếu hàng vẫn đúng phiên bản người dùng vừa nhìn”.
- Nó cần bảo vệ request trùng để không trừ 3 hai lần do retry.
- Nó không tự quản lý các tác động liên quan như đơn hàng, thanh toán và event log.

**Version check không phải phép thay thế cho điều kiện tồn kho; điều kiện tồn kho cũng không thay version check trong mọi luồng UI.** Chọn một hoặc cả hai theo hợp đồng nghiệp vụ.

### 10.3. Kiểm tra version không tự chống việc cộng/trừ hai lần

Giả sử một worker đã trừ 3 thành công nhưng mất kết nối trước khi nhận response. Nếu worker đọc version mới rồi **tự động trừ tiếp 3**, hệ có thể trừ hai lần dù mọi CAS đều hợp lệ về mặt kỹ thuật.

Đó là vấn đề **idempotency của yêu cầu**, không phải lost update. Các nghiệp vụ tài chính/tồn kho thường cần request key hoặc mã sự kiện duy nhất và transaction ghi sự kiện + thay đổi dữ liệu.

## 11. Một giao dịch gồm nhiều thao tác phải đồng bộ

### 11.1. Chỉ UPDATE sản phẩm chưa đủ cho việc bán hàng

Trong ứng dụng bán hàng, một lệnh bán có thể phải:

1. Tạo đơn hàng;
2. Trừ tồn;
3. Ghi sự kiện/audit;
4. Ghi trạng thái xử lý.

Nếu cập nhật tồn thành công rồi tạo đơn hàng thất bại, dữ liệu sẽ không nhất quán.

Một mô hình phù hợp trong cùng database:

~~~sql
BEGIN;

-- 1. Ghi yêu cầu/đơn hàng theo khóa nghiệp vụ duy nhất.
-- 2. UPDATE tồn có điều kiện version và stock.
-- 3. Nếu không được đúng 1 hàng, ROLLBACK.
-- 4. Ghi các hàng liên quan.
-- 5. COMMIT nếu toàn bộ thành công.

COMMIT;
~~~

Đây là mô hình luồng xử lý, không phải SQL chạy hoàn chỉnh; các câu chèn bảng đơn hàng được bỏ để tập trung vào CAS.

### 11.2. Nếu bước UPDATE CAS không khớp

Trong một transaction:

~~~sql
BEGIN;

UPDATE inventory_products
SET
    stock_qty = stock_qty - 3,
    version_no = version_no + 1
WHERE product_id = 101
  AND version_no = 1
  AND stock_qty >= 3
RETURNING product_id, stock_qty, version_no;
~~~

Nếu `RETURNING` không có hàng, ứng dụng cần quyết định **rollback toàn bộ transaction** nếu không muốn tạo một đơn hàng mà không trừ tồn thành công:

~~~sql
ROLLBACK;
~~~

Không nên `COMMIT` các bước nghiệp vụ liên quan khi thao tác điều kiện cốt lõi đã không diễn ra, trừ khi có chính sách xử lý bù trừ cụ thể.

### 11.3. CAS bảo vệ hàng, không bảo vệ mọi bất biến nhiều hàng

Ví dụ doanh nghiệp giới hạn tổng hạn mức của hai tài khoản ở mức 100. Hai transaction cập nhật **hai hàng khác nhau**, mỗi hàng đều có version check thành công, nhưng tổng sau cùng có thể vi phạm giới hạn nếu mỗi bên chỉ kiểm tra tổng từ snapshot cũ.

Đây là dạng bất biến **liên hàng** hoặc nguy cơ *write skew*. Một cột version của mỗi hàng không tự bảo đảm các ràng buộc trên tổng nhiều hàng.

Cần thiết kế thêm một hoặc nhiều cách phù hợp:

- Ràng buộc DBMS có thể biểu diễn trực tiếp;
- Cập nhật một hàng tổng/quota dùng chung có điều kiện;
- Khóa tập hàng/quy tắc khóa;
- Isolation `SERIALIZABLE` với retry phù hợp;
- Quy trình giao dịch có tính nhất quán được kiểm chứng.

**Optimistic locking trên một hàng không phải thay thế toàn bộ lý thuyết transaction isolation.**

## 12. Version phải được duy trì trên mọi đường ghi

### 12.1. Lỗ hổng khi có một UPDATE không tăng version

Giả sử ứng dụng web dùng:

~~~sql
UPDATE inventory_products
SET
    unit_price = ?,
    version_no = version_no + 1
WHERE product_id = ?
  AND version_no = ?;
~~~

nhưng một tác vụ quản trị chạy:

~~~sql
-- Nguy hiểm nếu nghiệp vụ yêu cầu mọi sửa đổi đổi version:
UPDATE inventory_products
SET unit_price = 150.00
WHERE product_id = 101;
~~~

Tác vụ quản trị đã sửa giá nhưng **không tăng version**. Một client giữ version cũ vẫn có thể cập nhật và ghi đè giá vừa sửa.

Nếu chọn cơ chế version thủ công, mọi đường ghi — API, batch job, migration, màn hình admin, script hỗ trợ, luồng import — cần áp dụng chính sách thống nhất.

### 12.2. Dùng trigger để tăng version tự động?

Một số hệ thống chọn trigger `BEFORE UPDATE` để tăng version. Cách đó có thể giảm nguy cơ script quên bump, nhưng phải thiết kế rõ:

- Nếu ứng dụng cũng `SET version_no=version_no+1`, có nguy cơ **tăng hai lần**.
- Trigger có tăng version khi giá trị thực tế không đổi không?
- Trigger có luôn chạy với các kiểu DML/bulk/import không?
- Đọc version mới từ driver/RETURNING bằng cách nào?
- Mọi write path có tuân theo guard `WHERE version_no=?` không?

**Tự động tăng version không thay điều kiện so sánh phiên bản ở câu UPDATE của client.** Nếu script không guard và được phép ghi, nó vẫn có thể ghi đè thay đổi khác; trigger chỉ giúp những client còn giữ token cũ nhận ra phiên bản đã đổi về sau.

### 12.3. JPA/Hibernate @Version

Trong Java Persistence API (JPA/Jakarta Persistence), có thể khai báo trường version:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
public class InventoryProduct {

    @Id
    private Long productId;

    private BigDecimal unitPrice;

    private Integer stockQty;

    @Version
    private Long versionNo;

    // getters/setters được lược bỏ.
}
~~~

Khi đối tượng được quản lý đúng lifecycle, ORM thường đưa version vào điều kiện update và tăng version theo chiến lược của provider, ví dụ ý tưởng:

~~~sql
UPDATE inventory_products
SET
    unit_price = ?,
    stock_qty = ?,
    version_no = ?
WHERE product_id = ?
  AND version_no = ?;
~~~

Khi hàng không còn cùng version, ORM có thể ném exception optimistic-locking khi flush/commit theo API/provider.

Những điểm cần lưu ý:

- Cần mapping chính xác tên cột/bảng (ví dụ `version_no`) tùy naming strategy.
- Không tự tăng version trong entity nếu provider đã quản lý nó.
- Một số bulk JPQL/SQL native updates hoặc thao tác ngoài ORM có thể **bỏ qua cơ chế version tự động**; phải tăng/check version theo quy tắc phù hợp.
- Transaction, flush và thời điểm lỗi xuất hiện có thể phụ thuộc provider.
- Không cho rằng annotation `@Version` bảo vệ được câu SQL viết thủ công ở một hệ thống khác.

### 12.4. Khi nào nên tăng version?

Thiết kế phổ biến: tăng version với mọi **thay đổi nghiệp vụ có ý nghĩa**. Tuy nhiên cần quyết định cả các trường hợp:

- Cập nhật `updated_at` chỉ vì một heartbeat có tính là phiên bản mới?
- Ghi cùng giá trị cũ vào cột có cần tăng version?
- Sửa metadata nội bộ không ảnh hưởng màn hình có làm form người dùng bị stale?
- Thao tác soft delete có bắt buộc tăng version?
- Có các cột audit hay trigger thay đổi tự động không?

Quy tắc cần **nhất quán và được ghi rõ**. Nếu một thay đổi ảnh hưởng quyết định của client thì thường nên làm token thay đổi.

## 13. DELETE và soft delete có điều kiện theo phiên bản

Không chỉ UPDATE; xóa dữ liệu cũng có nguy cơ tác động lên một bản ghi đã thay đổi.

### 13.1. DELETE cứng theo version

PostgreSQL:

~~~sql
DELETE FROM inventory_products
WHERE product_id = 101
  AND version_no = 1
RETURNING product_id, version_no;
~~~

Nếu hàng hiện đã là version 2, lệnh xóa **0 hàng**, thay vì xóa dữ liệu mà người dùng khác vừa sửa.

**Cẩn thận:** đây là ví dụ phá hủy dữ liệu. Chỉ chạy trong transaction thử nghiệm và rollback hoặc dùng dữ liệu demo có thể tạo lại:

~~~sql
BEGIN;

DELETE FROM inventory_products
WHERE product_id = 101
  AND version_no = 1
RETURNING product_id;

ROLLBACK;
~~~

### 13.2. Soft delete theo version

Một bảng có cột `deleted_at` hoặc `is_deleted` có thể cập nhật trạng thái xóa mềm bằng CAS:

~~~sql
-- Ví dụ giả định bảng products có các cột is_deleted, version_no:
UPDATE products
SET
    is_deleted = TRUE,
    version_no = version_no + 1
WHERE product_id = :id
  AND version_no = :expected_version
  AND is_deleted = FALSE;
~~~

`products` là tên bảng giả định, không phải `inventory_products` ở mục 2. Mẫu này còn cần chính sách khi client cố sửa một hàng đã soft delete, cách lọc mặc định và quyền phục hồi.

### 13.3. DELETE rồi INSERT lại cùng ID: nguy cơ ABA

Nếu một hàng bị xóa rồi tạo lại với **cùng ID và cùng version ban đầu**, client cũ có thể nhìn thấy cặp `(id, version)` giống lần trước và tưởng đó vẫn là thực thể ban đầu.

Vấn đề này liên quan tới *ABA*: trạng thái từ A sang B rồi trở lại A khiến một phép so sánh đơn giản không thấy lịch sử đã thay đổi.

Trong hệ thống cần nhận diện mạnh:

- Không tái sử dụng định danh thực thể;
- Dùng UUID/ID thế hệ mới hoặc **generation token** không tái sử dụng;
- Không reset version của cùng thực thể khi khôi phục/import;
- Định nghĩa rõ vòng đời xóa-phục hồi.

Một cột phiên bản số nguyên là token hữu ích, nhưng không thay bảo đảm **danh tính của hàng**.

## 14. Version số nguyên hay timestamp/rowversion?

### 14.1. BIGINT tăng dần

Mẫu:

~~~sql
version_no BIGINT NOT NULL DEFAULT 1
~~~

Ưu điểm:

- Dễ đọc, dễ diễn giải;
- So sánh chính xác, không phụ thuộc làm tròn thời gian;
- Mỗi update có thể tăng bằng `version_no = version_no + 1`;
- Phù hợp với CAS khi mọi đường ghi tuân thủ.

Hạn chế:

- Phải đảm bảo mọi cập nhật có ý nghĩa đều làm version thay đổi;
- Kiểu số có giới hạn; không để tràn khi đạt ngưỡng;
- Cần xử lý đúng reset/import/restore dữ liệu.

### 14.2. updated_at không phải token CAS tốt nếu dùng sơ sài

Một thiết kế thử dùng:

~~~sql
UPDATE inventory_products
SET
    unit_price = 120.00,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 101
  AND updated_at = :timestamp_da_doc;
~~~

Có một số rủi ro:

- Timestamp có **độ chính xác hữu hạn**; hai thay đổi có thể cùng giá trị lưu.
- Client có thể làm tròn hoặc chuyển múi giờ sai.
- PostgreSQL `CURRENT_TIMESTAMP` thường là thời điểm bắt đầu transaction; hai update trong cùng transaction có thể có cùng timestamp.
- Không phải mọi đường ghi đều cập nhật `updated_at`.
- So sánh timestamp qua driver và serialize/deserialize phức tạp hơn số nguyên chính xác.

Nếu không có lý do đặc biệt, **version số nguyên hoặc token concurrency chuyên dụng của DBMS** thường dễ quản lý hơn một timestamp ứng dụng.

### 14.3. SQL Server rowversion

SQL Server có kiểu dữ liệu `rowversion`, tạo giá trị nhị phân thay đổi khi hàng được cập nhật theo cơ chế engine:

~~~sql
-- SQL Server: bảng ví dụ riêng.
CREATE TABLE dbo.product_versions (
    product_id BIGINT NOT NULL PRIMARY KEY,
    unit_price DECIMAL(12, 2) NOT NULL,
    rv ROWVERSION
);
~~~

Client đọc `rv` rồi dùng trong điều kiện:

~~~sql
-- SQL Server; @expected_rv là binary token đã đọc.
UPDATE dbo.product_versions
SET unit_price = @new_price
OUTPUT INSERTED.rv
WHERE product_id = @product_id
  AND rv = @expected_rv;
~~~

Nếu `0 hàng`, version token đã khác hoặc hàng không tồn tại.

Cần phân biệt **`rowversion` của SQL Server không phải ngày giờ** và không nên coi như timestamp; nó là token phiên bản hệ thống. Không dùng `timestamp` trong SQL Server để diễn giải thời gian tạo/sửa, vì đó là tên cũ đồng nghĩa với `rowversion`.

### 14.4. UUID ngẫu nhiên làm token có được không?

Một token duy nhất được đổi ở mỗi lần cập nhật cũng có thể dùng cho compare-and-swap:

~~~text
WHERE id = expected_id AND token = expected_token
SET token = newly_generated_unique_token
~~~

Cách này tránh giả định số tăng liên tục nhưng cần cơ chế tạo token mới không trùng và quản lý đúng ở mọi write path. Một giá trị UUID do client tự cấp không thể được coi là đáng tin nếu ứng dụng cho phép tái sử dụng hoặc ghi đè tùy ý.

## 15. Đối chiếu SQL theo DBMS

Tư tưởng CAS giống nhau nhưng cách nhận kết quả, kiểu version và transaction details khác nhau.

### 15.1. PostgreSQL

~~~sql
UPDATE inventory_products
SET
    unit_price = 120.00,
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 101
  AND version_no = 1
RETURNING product_id, unit_price, version_no;
~~~

`RETURNING` trả hàng sau UPDATE hoặc rỗng khi không khớp. Các điều kiện kiểm tra và phép tăng version nằm cùng một lệnh. Ở isolation level cao, cần xử lý serialization failure theo chính sách transaction.

### 15.2. MySQL / InnoDB

MySQL hỗ trợ cú pháp tương tự, không có `RETURNING` theo hình thức PostgreSQL trong những phiên bản MySQL phổ biến:

~~~sql
UPDATE inventory_products
SET
    unit_price = 120.00,
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 101
  AND version_no = 1;
~~~

Sau đó kiểm tra số hàng qua driver hoặc:

~~~sql
SELECT ROW_COUNT();
~~~

`ROW_COUNT()` có quy tắc trả số hàng thay đổi/khớp theo trường hợp và cấu hình; trong ví dụ thành công, version tăng nên có thay đổi thực. Khi cần version mới, có thể đọc lại bằng SELECT trong transaction phù hợp, nhưng phải xét tính nhất quán và việc bản ghi có thể bị cập nhật tiếp theo.

Nếu dùng InnoDB, hệ hỗ trợ transaction và row locking. Không tự suy hành vi MySQL nontransactional storage engine hoặc cấu hình riêng là giống hệt InnoDB.

### 15.3. SQL Server

T-SQL với cột version số:

~~~sql
UPDATE dbo.inventory_products
SET
    unit_price = @new_price,
    version_no = version_no + 1,
    updated_at = SYSDATETIME()
OUTPUT
    INSERTED.product_id,
    INSERTED.version_no
WHERE product_id = @product_id
  AND version_no = @expected_version;
~~~

`OUTPUT INSERTED.version_no` cho token mới khi lệnh sửa thành công. Có các điều kiện/hạn chế với trigger và `OUTPUT INTO` tùy schema. Với kiểu `rowversion`, dùng token nhị phân engine tạo như mục 14.3 thay vì tự tăng.

### 15.4. SQLite

SQLite có thể dùng cùng mẫu CAS theo version số:

~~~sql
UPDATE inventory_products
SET
    unit_price = 120.00,
    version_no = version_no + 1
WHERE product_id = 101
  AND version_no = 1;
~~~

SQLite hỗ trợ `RETURNING` từ phiên bản **3.35.0**, nên trên phiên bản phù hợp có thể thêm:

~~~sql
RETURNING product_id, unit_price, version_no;
~~~

SQLite có cơ chế write serialization/locking riêng và chỉ một writer tại một thời điểm theo các giới hạn của engine. Nếu ứng dụng nhận `SQLITE_BUSY`/`SQLITE_BUSY_SNAPSHOT` hoặc lỗi khóa tương đương, cần transaction/retry thích hợp; không chỉ xét số hàng 0/1.

### 15.5. Oracle

Mẫu Oracle với bind variables:

~~~sql
UPDATE inventory_products
SET
    unit_price = :new_price,
    version_no = version_no + 1,
    updated_at = SYSTIMESTAMP
WHERE product_id = :product_id
  AND version_no = :expected_version;
~~~

Ứng dụng kiểm tra số hàng được cập nhật. Oracle cũng có cơ chế `RETURNING ... INTO` qua driver/PLSQL:

~~~sql
UPDATE inventory_products
SET
    unit_price = :new_price,
    version_no = version_no + 1
WHERE product_id = :product_id
  AND version_no = :expected_version
RETURNING version_no INTO :out_version;
~~~

Cách bind tham số OUT và xử lý khi 0 hàng phụ thuộc môi trường chạy Oracle. Không sao chép `RETURNING version_no` của PostgreSQL nguyên văn sang Oracle.

### 15.6. Bảng tóm tắt

| DBMS | Điều kiện CAS | Nhận version sau sửa | Điều cần kiểm tra |
| --- | --- | --- | --- |
| PostgreSQL | `WHERE id=? AND version_no=?` | `RETURNING` | Isolation, serialization failure |
| MySQL/InnoDB | `WHERE id=? AND version_no=?` | Row count + SELECT/API | Driver affected rows, transaction engine |
| SQL Server | `WHERE id=@id AND version_no=@v` hoặc `rv=@token` | `OUTPUT INSERTED...` | Kiểu `rowversion`, trigger |
| SQLite | `WHERE id=? AND version_no=?` | `RETURNING` nếu phiên bản hỗ trợ | Lock/busy, transaction mode |
| Oracle | `WHERE id=:id AND version_no=:v` | `RETURNING ... INTO`/driver | Bind output, isolation |
| MariaDB | Mẫu UPDATE có điều kiện | API/dialect theo phiên bản | Tính năng RETURNING, row count, engine |

**Không dùng bảng này như bảo đảm mọi DBMS có cùng hành vi trả lỗi khi hai phiên cùng ghi.** Nó chỉ cho thấy kỹ thuật điều kiện phiên bản có thể áp dụng rộng khi bảng có token thích hợp.

## 16. API HTTP: version trong payload và If-Match

### 16.1. Trả version cho client khi đọc

Một API có thể trả:

~~~http
GET /api/products/101
~~~

Response khái niệm:

~~~json
{
  "productId": 101,
  "sku": "BK-001",
  "unitPrice": "100.00",
  "stockQty": 10,
  "version": 1
}
~~~

Client chỉnh giá rồi gửi:

~~~http
PUT /api/products/101
Content-Type: application/json
~~~

~~~json
{
  "unitPrice": "120.00",
  "stockQty": 10,
  "expectedVersion": 1
}
~~~

Server thực hiện CAS với `WHERE product_id=101 AND version_no=1`. Nếu 0 hàng, server không được lén loại bỏ điều kiện chỉ để “đảm bảo lưu”.

### 16.2. HTTP ETag và If-Match

Một cách dùng chuẩn điều kiện HTTP là trả **ETag** cho representation:

~~~http
HTTP/1.1 200 OK
ETag: "product-101-v1"
Content-Type: application/json
~~~

Client chỉ cập nhật nếu tài nguyên còn đúng phiên bản:

~~~http
PUT /api/products/101
If-Match: "product-101-v1"
Content-Type: application/json
~~~

Server ánh xạ token đúng cách sang phiên bản database đã xác thực. Nếu version đã đổi, precondition không còn đúng và HTTP thường dùng **`412 Precondition Failed`** cho `If-Match` thất bại. Nếu API yêu cầu điều kiện nhưng client không gửi, có thể dùng **`428 Precondition Required`** theo chính sách.

Với API dùng `expectedVersion` trong body thay vì HTTP conditional headers, `409 Conflict` thường là cách báo xung đột nghiệp vụ. Việc phân loại `404`, `409`, `412` hoặc `428` phải thống nhất với thiết kế API và quy tắc quyền truy cập.

### 16.3. ETag không nhất thiết chỉ là chuỗi version_no

ETag phải phản ánh chính xác điều kiện thay đổi của **representation** mà client đang sửa. Nếu API cung cấp nhiều biến thể nội dung khác nhau theo locale, field selection hoặc quyền, không nên tự phát minh một ETag quá đơn giản rồi khẳng định nó là một validator mạnh cho mọi biến thể.

Một token dựa trên version có thể phù hợp khi mọi thay đổi liên quan đến representation đều tăng version và server phát/kiểm tra validator đúng quy tắc HTTP. Khi dùng `If-Match`, cần lưu ý **strong comparison** của ETag; không dùng weak ETag như một token điều kiện cập nhật tương đương.

### 16.4. API cần trả dữ liệu mới sau lần lưu thành công

Nếu CAS thành công, response có thể chứa:

~~~json
{
  "productId": 101,
  "unitPrice": "120.00",
  "stockQty": 8,
  "version": 3
}
~~~

Kết quả này giả định đã có lịch sử A cập nhật từ version 1 lên 2, rồi B hợp nhất và cập nhật version 2 lên 3. Không tự tăng version ở client mà không đối chiếu server: trigger, ORM hoặc DBMS có thể dùng quy tắc token khác.

## 17. Retry, timeout và tính idempotent

### 17.1. Conflict không có nghĩa “hãy thử lại y nguyên”

Nếu cập nhật trả 0 hàng do version cũ, retry **cùng expectedVersion=1** thường vẫn trả 0 trong khi hàng hiện là version 2. Đây là tín hiệu yêu cầu cần **đọc lại trạng thái và xét lại quyết định**.

Không dùng vòng lặp:

~~~text
while (updateCount == 0):
    expectedVersion = latestVersion
    update(stalePrice, staleQty)
~~~

vì cách này đọc version mới nhưng giữ dữ liệu cũ, cuối cùng có thể ghi đè người khác. Đây chỉ là lost update được che trong retry loop.

### 17.2. Retry lỗi serializable/deadlock khác retry conflict nghiệp vụ

Một transaction có thể thất bại vì deadlock hoặc serialization. Với lỗi loại **có thể retry**, thiết kế thường là:

1. Rollback transaction lỗi.
2. Thực hiện lại **toàn bộ thao tác** trên dữ liệu mới theo quy tắc nghiệp vụ.
3. Giới hạn số lần retry, có backoff/jitter phù hợp.
4. Không retry vô hạn khi dữ liệu không đáp ứng constraint hoặc yêu cầu cần người xác nhận.

Đối với PostgreSQL, ví dụ SQLSTATE `40001` thường là serialization failure; `40P01` là deadlock detected. Không bắt mọi SQLException rồi áp dụng cùng retry.

### 17.3. Khi không biết commit đã thành công hay chưa

Giả sử UPDATE trừ tồn đã commit nhưng client mất kết nối trước khi nhận kết quả. Nếu client thử lại như một **yêu cầu bán mới**, hàng có thể bị trừ thêm lần nữa.

Version check không phải giải pháp đầy đủ cho trường hợp **outcome unknown** này. Cần một **idempotency key/request ID** được lưu và kiểm tra, ví dụ:

~~~sql
CREATE TABLE inventory_actions (
    action_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key VARCHAR(100) NOT NULL UNIQUE,
    product_id BIGINT NOT NULL REFERENCES inventory_products(product_id),
    quantity_delta INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Một request bán 3 sản phẩm có `request_key` riêng:

~~~text
Request key = SALE-2026-000042
Product     = 101
Delta       = -3
~~~

Cần thiết kế transaction để ghi action và cập nhật tồn **chỉ một lần**, đồng thời kiểm tra cùng request key có đúng payload ban đầu. Không chỉ dùng `INSERT ... ON CONFLICT DO NOTHING` rồi vẫn trừ tồn bên ngoài transaction; như vậy lần retry có thể bỏ qua event nhưng vẫn trừ tồn tiếp.

### 17.4. Phân biệt concurrency control và idempotency

| Câu hỏi | Cơ chế |
| --- | --- |
| “Bản form tôi đang lưu còn mới không?” | Version check/CAS |
| “Hai người cùng sửa một hàng thì ai thắng?” | Conflict policy, version, transaction |
| “Request đã được thực hiện lần nào chưa?” | Idempotency key/audit |
| “Số hàng tồn có đủ để bán không?” | Điều kiện nghiệp vụ `stock_qty >= n` |
| “Các bước tạo đơn + trừ tồn có cùng thành công không?” | Transaction/atomic workflow |

Có thể cần **tất cả các cơ chế này** cho một luồng kinh doanh quan trọng. Không cố dùng một cột `version_no` để trả lời mọi câu hỏi.

## 18. Cập nhật hàng loạt với nhiều phiên bản dự kiến

### 18.1. Một batch có thể chứa nhiều cặp (id, expectedVersion)

Giả sử client đã đọc:

~~~text
product 101, expected_version 1, new_price 110
product 102, expected_version 4, new_price 22
product 103, expected_version 8, new_price 550
~~~

PostgreSQL có thể dùng bảng nguồn tạm từ `VALUES`:

~~~sql
BEGIN;

WITH proposed (
    product_id, expected_version, new_price
) AS (
    VALUES
        (101::BIGINT, 1::BIGINT, 110.00::NUMERIC),
        (102::BIGINT, 4::BIGINT, 22.00::NUMERIC),
        (103::BIGINT, 8::BIGINT, 550.00::NUMERIC)
)
UPDATE inventory_products AS p
SET
    unit_price = proposed.new_price,
    version_no = p.version_no + 1,
    updated_at = CURRENT_TIMESTAMP
FROM proposed
WHERE p.product_id = proposed.product_id
  AND p.version_no = proposed.expected_version
RETURNING p.product_id, p.version_no;

-- Ứng dụng kiểm tra số hàng và tập ID trả về
-- trước khi COMMIT/ROLLBACK.

ROLLBACK;
~~~

Nếu cả ba hàng còn đúng version, câu lệnh trả ba ID. Nhưng nếu sản phẩm 102 đã bị sửa thành version 5, thì hàng 102 **không khớp** và chỉ các hàng khác có thể được cập nhật.

**Một câu UPDATE batch có thể cập nhật một phần các hàng hợp lệ**, dù bản thân statement có tính nguyên tử khi thành công trên tập hàng mà nó chọn.

### 18.2. Muốn tất cả hoặc không gì thì phải kiểm tra kết quả

Nếu yêu cầu nghiệp vụ là “ba sản phẩm phải cùng cập nhật hoặc cùng không cập nhật”:

1. Bắt đầu transaction.
2. Chạy UPDATE batch có điều kiện.
3. So **số lượng và tập ID** được cập nhật với đầu vào hợp lệ.
4. Nếu thiếu bất kỳ ID nào, **ROLLBACK** toàn transaction.
5. Chỉ **COMMIT** khi tất cả điều kiện đều thỏa.

Không chỉ nhìn câu UPDATE không ném exception rồi kết luận toàn batch đã được áp dụng.

### 18.3. Nguồn batch phải không trùng khóa

Nếu `proposed` chứa hai dòng cùng `product_id` nhưng giá khác, câu `UPDATE ... FROM` ở nhiều hệ có thể có hành vi nguồn không đơn trị/không xác định. Trước khi UPDATE, cần bảo đảm **mỗi product_id có nhiều nhất một giá trị dự kiến**.

Có thể dùng staging table với `PRIMARY KEY(product_id)` trong phạm vi batch, hoặc kiểm tra trùng và từ chối đầu vào. Không để một UPDATE JOIN chọn tùy ý một trong hai yêu cầu mâu thuẫn.

### 18.4. Xử lý nhiều hàng từ nhiều luồng cần tránh deadlock

Các transaction cập nhật cùng tập hàng nhưng theo thứ tự khác nhau có thể deadlock khi lấy khóa. Việc định nghĩa thứ tự xử lý nhất quán, batch nhỏ hợp lý và retry lỗi deadlock có thể hỗ trợ vận hành. Tuy nhiên một câu SQL viết `ORDER BY` ở đầu ra không tự đảm bảo thứ tự lấy row lock của engine. Cần đo trên DBMS, isolation và workload thật.

## 19. Hiệu năng và thiết kế chỉ mục

### 19.1. Khóa chính thường là bộ lọc quan trọng nhất

Truy vấn CAS:

~~~sql
UPDATE inventory_products
SET
    unit_price = 120.00,
    version_no = version_no + 1
WHERE product_id = 101
  AND version_no = 1;
~~~

Với `product_id PRIMARY KEY`, DBMS có thể định vị rất ít hàng bằng index khóa chính rồi kiểm tra `version_no`. Trong nhiều trường hợp **không cần thêm index riêng trên `version_no`** chỉ để tối ưu loại UPDATE này.

Một index tổng hợp `(product_id, version_no)` không mặc định nhanh hơn, vì `product_id` đã duy nhất; nó còn tăng chi phí ghi khi `version_no` thay đổi mỗi lần.

### 19.2. Cột version thay đổi thường xuyên

Mỗi update tăng `version_no` có thể tạo thêm chi phí ghi/log/index và cạnh tranh trên hàng nóng. Nếu hàng bị nhiều worker cùng sửa liên tục, một số lượng lớn yêu cầu có thể thất bại CAS và retry, gây tranh chấp.

Tối ưu không phải “bỏ version guard”. Có thể cân nhắc:

- Gộp hoặc xếp hàng thao tác theo một khóa;
- Chuyển một số nghiệp vụ sang `UPDATE SET counter=counter+delta WHERE condition` nguyên tử;
- Tách các miền dữ liệu độc lập;
- Giảm số lần cập nhật không cần thiết;
- Thiết kế retry có giới hạn và backoff;
- Đo tần suất conflict theo bảng, khóa và endpoint.

### 19.3. EXPLAIN và phép đo

PostgreSQL:

~~~sql
EXPLAIN
UPDATE inventory_products
SET
    unit_price = 120.00,
    version_no = version_no + 1
WHERE product_id = 101
  AND version_no = 1;
~~~

`EXPLAIN` cho kế hoạch dự kiến. `EXPLAIN ANALYZE` **thực sự chạy UPDATE**, nên không dùng vô ý trên production; cần môi trường thử hoặc transaction an toàn.

Cần quan sát các thông tin như index scan, row locking, số hàng vào UPDATE và khả năng chờ khóa. Câu UPDATE bị 0 hàng do version mismatch là tín hiệu nghiệp vụ, không phải lỗi hiệu năng đơn thuần.

## 20. Những lỗi thường gặp

| Lỗi/hiểu nhầm | Vấn đề | Cách đúng |
| --- | --- | --- |
| Chỉ dùng `WHERE id=?` khi lưu form cũ | Lost update | Thêm `AND version_no=?` |
| Kiểm tra version bằng SELECT riêng rồi UPDATE không guard | Race giữa kiểm tra và ghi | Đưa version vào WHERE của UPDATE |
| Thêm điều kiện version nhưng quên tăng version | Client cũ vẫn có thể ghi đè | Bump token nguyên tử trên mọi đường ghi |
| Client tự gửi version mới và server tin luôn | Version có thể stale hoặc bị giả | Server kiểm tra expected token, tự tạo token mới |
| Đọc version mới nhất trước khi lưu payload cũ | Biến stale update thành ghi đè hợp lệ | Mang version của bản đã đọc cùng payload |
| Coi `affected=0` chắc chắn là conflict | Có thể not found, status không hợp lệ, RLS | Phân loại có kiểm soát |
| Coi `affected=1` là đã commit mọi bước | Có thể vẫn trong transaction chưa commit | Kiểm soát transaction boundary |
| Tự retry cùng payload với version mới | Có thể ghi đè dữ liệu cập nhật gần đây | Đọc lại, tính lại hoặc xin xác nhận |
| Tự động lấy version mới rồi lặp đến khi thắng | Bỏ qua conflict nghiệp vụ | Chỉ retry khi có quy tắc merge an toàn |
| Không guard thao tác DELETE | Xóa bản ghi người khác vừa sửa | DELETE theo id + version |
| Admin script/bulk UPDATE không tăng version | Lỗ hổng stale-write detection | Đồng bộ mọi write path |
| ORM `@Version` nhưng native UPDATE không kiểm tra | Native SQL bỏ qua version | Có guard/bump thủ công hoặc dùng ORM phù hợp |
| Dùng `updated_at` làm token mà không xét độ chính xác | Có thể trùng token hoặc làm tròn | Dùng BIGINT/rowversion chuyên dụng |
| Reset version khi khôi phục hàng | ABA, client cũ tưởng hàng mới là hàng cũ | Không tái sử dụng token/định danh |
| Version check thay luôn điều kiện tồn đủ | Có thể bán vượt tồn nếu logic sai | Cùng kiểm tra `stock_qty>=n` |
| CAS thay luôn idempotency | Retry có thể trừ tiền/tồn nhiều lần | Request key và transaction |
| Version trên một hàng bảo vệ mọi bất biến nhiều hàng | Write skew | Constraint/locking/serializable phù hợp |
| Batch UPDATE thiếu 1 hàng nhưng vẫn COMMIT | Cập nhật một phần khi muốn all-or-nothing | So expected IDs, rollback khi thiếu |
| Nguồn UPDATE FROM trùng ID | Cột mới có thể từ hàng bất kỳ | Dedupe/unique source |
| Thêm index trên version cho mọi UPDATE | Tăng chi phí ghi, có thể không giúp | Ưu tiên PK và đo bằng EXPLAIN |
| Coi mọi lỗi concurrency sẽ trả 0 hàng | Có thể có serialization/deadlock error | Xử lý cả exception và row count |

## 21. Bài tập thực hành và đáp án

Bộ dữ liệu ban đầu:

~~~text
ID 101: price=100, qty=10, version=1
ID 102: price= 20, qty= 5, version=4
ID 103: price=500, qty= 2, version=8
~~~

Với các bài có thay đổi dữ liệu, chạy thử trong transaction PostgreSQL và `ROLLBACK` để trở về trạng thái ban đầu. Không áp dụng trực tiếp trên production.

### Bài 1 — Phát hiện lost update

A và B cùng đọc sản phẩm 101 với `price=100, qty=10`. A ghi `qty=8`; B ghi `price=120, qty=10` bằng `UPDATE ... WHERE product_id=101` không kiểm tra version. Kết quả có thể là gì?

**Đáp án:** nếu B ghi sau A, dữ liệu có thể thành `price=120, qty=10`; thay đổi tồn của A bị ghi đè. SQL có thể không báo lỗi vì cả hai UPDATE đều hợp lệ theo khóa chính.

### Bài 2 — Viết CAS theo version

Hãy sửa sản phẩm 101 thành giá 120 và tồn 8, chỉ khi `version_no=1`; tăng version trong cùng lệnh.

**Đáp án:**

~~~sql
UPDATE inventory_products
SET
    unit_price = 120.00,
    stock_qty = 8,
    version_no = version_no + 1
WHERE product_id = 101
  AND version_no = 1
RETURNING product_id, unit_price, stock_qty, version_no;
~~~

Nếu còn version 1, kết quả là `120,8,2`. Nếu version đã khác, kết quả RETURNING rỗng.

### Bài 3 — Hai client cùng version

A và B đều có expectedVersion 1. A cập nhật thành công và commit, làm version thành 2. B tiếp tục gửi câu CAS với expectedVersion 1. Trên PostgreSQL READ COMMITTED sau commit của A, B cập nhật mấy hàng?

**Đáp án:** **0 hàng** vì điều kiện `version_no=1` không còn khớp. Nếu chạy đồng thời tại isolation level khác, cũng phải chuẩn bị xử lý serialization/deadlock errors tùy tình huống.

### Bài 4 — Vì sao phải tăng version?

Một lập trình viên viết:

~~~sql
UPDATE inventory_products
SET unit_price = 120.00
WHERE product_id = 101
  AND version_no = 1;
~~~

Vì sao chưa đủ?

**Đáp án:** câu này không tăng version, nên sau cập nhật hàng vẫn có thể mang version 1; client khác giữ version 1 vẫn được phép ghi đè. Cần `version_no = version_no + 1` hoặc cơ chế token thay đổi tương đương.

### Bài 5 — 0 hàng không luôn là stale version

Một câu CAS trả 0 hàng. Hãy nêu ba nguyên nhân có thể.

**Đáp án:** hàng không tồn tại; version không khớp; điều kiện khác như `product_status='ACTIVE'` hoặc `stock_qty>=n` không thỏa. Quyền/row-level security cũng có thể ảnh hưởng phạm vi cập nhật.

### Bài 6 — Hợp nhất hai thay đổi độc lập

Sau khi A sửa tồn từ 10 xuống 8 (version 2), B muốn sửa giá từ 100 lên 120. B phải lưu gì để không mất tồn mới?

**Đáp án:** đọc lại hàng hiện tại `(price=100,qty=8,version=2)`, hợp nhất thành `(120,8)` rồi CAS với expectedVersion 2. Nếu thành công, hàng thành `(120,8,version=3)`.

### Bài 7 — Bán hàng có điều kiện

Sản phẩm 101 tồn 10, version 1. Viết câu trừ 3 nếu đủ hàng, sản phẩm ACTIVE và version chưa đổi.

**Đáp án:**

~~~sql
UPDATE inventory_products
SET
    stock_qty = stock_qty - 3,
    version_no = version_no + 1
WHERE product_id = 101
  AND version_no = 1
  AND stock_qty >= 3
  AND product_status = 'ACTIVE'
RETURNING stock_qty, version_no;
~~~

Nếu thành công, `stock_qty=7` và `version_no=2`. Nếu 0 hàng, phải phân loại nguyên nhân thay vì tự coi bán thành công.

### Bài 8 — Có luôn cần expectedVersion khi trừ tồn không?

Một hệ thống chỉ muốn “trừ 3 nếu vẫn còn đủ hàng tại thời điểm ghi”, không yêu cầu client đã đọc đúng trạng thái trước đó. Có thể làm gì?

**Đáp án:** có thể dùng `UPDATE ... SET stock_qty=stock_qty-3 WHERE product_id=? AND stock_qty>=3` trong một statement nguyên tử theo transaction DBMS. Vẫn nên tăng version nếu các client khác dùng version token, và cần idempotency key để request retry không trừ hai lần.

### Bài 9 — Cập nhật bằng JDBC

Với `PreparedStatement`, hãy nêu bốn tham số cần bind cho lệnh cập nhật giá và tồn theo version.

**Đáp án:** `newPrice` (BigDecimal), `newStockQty` (int), `productId` (long), `expectedVersion` (long), đúng thứ tự placeholder. Kiểm tra `executeUpdate() == 1` để nhận diện cập nhật một hàng; `0` cần xử lý không tìm thấy hoặc stale version.

### Bài 10 — Thao tác DELETE không ghi đè

Viết PostgreSQL DELETE sản phẩm 102 chỉ nếu `version_no=4`.

**Đáp án:**

~~~sql
BEGIN;

DELETE FROM inventory_products
WHERE product_id = 102
  AND version_no = 4
RETURNING product_id;

ROLLBACK;
~~~

Nếu version đã khác 4, hàng không bị xóa. Câu DELETE chỉ nên chạy có kiểm soát vì nó là thao tác phá hủy.

### Bài 11 — Admin script bỏ tăng version

API dùng version check nhưng batch job chạy `UPDATE inventory_products SET unit_price=... WHERE product_id=101` mà không bump version. Vì sao nguy hiểm?

**Đáp án:** bản form cũ giữ version không đổi nên vẫn có thể vượt điều kiện CAS và ghi đè giá batch job. Mọi write path phải có chính sách version thống nhất.

### Bài 12 — Timestamp có thay số nguyên được không?

Một người đề xuất dùng `updated_at=CURRENT_TIMESTAMP` làm token cho CAS thay vì `version_no`. Nêu hai rủi ro.

**Đáp án:** timestamp có độ chính xác giới hạn và có thể không thay đổi giữa hai update; client/driver có thể làm tròn hoặc chuyển timezone sai. Với PostgreSQL, `CURRENT_TIMESTAMP` trong cùng transaction còn có thể cùng một thời điểm cho nhiều statement. BIGINT version thường đáng tin hơn cho so sánh chính xác.

### Bài 13 — CAS và request trùng

Một yêu cầu bán 3 sản phẩm đã commit nhưng response bị mất. Client tự tạo yêu cầu mới trừ 3 với version mới. Version check có ngăn lần bán thứ hai không?

**Đáp án:** không nhất thiết. Cả hai lần trừ có thể thành công tuần tự với các version khác nhau. Cần idempotency key định danh cùng yêu cầu và transaction ghi action + thay đổi tồn để không nhân đôi tác động.

### Bài 14 — Batch một phần

Một batch muốn cập nhật ba ID 101/102/103 với versions 1/4/8. Trước khi chạy, ID 102 đã thành version 5. Câu UPDATE batch có điều kiện có thể sửa bao nhiêu hàng?

**Đáp án:** có thể chỉ sửa **2 hàng** 101 và 103, còn 102 không khớp. Nếu nghiệp vụ yêu cầu all-or-nothing, phải so tập ID và rollback transaction khi thiếu một hàng.

### Bài 15 — JPA @Version

Vì sao chỉ gắn `@Version` vào entity chưa đủ khi dự án còn có các bulk native SQL updates?

**Đáp án:** ORM quản lý version cho những thao tác entity phù hợp với lifecycle/provider; native SQL hoặc bulk operations có thể bỏ qua logic optimistic locking tự động. Cần đảm bảo mọi đường ghi tăng/check version theo hợp đồng.

### Bài 16 — Isolation level

Hai người chỉnh cùng một form web nhưng thao tác đọc và lưu nằm ở hai request/transaction khác nhau. Chỉ đặt transaction lưu ở `SERIALIZABLE` có tự biết form đã cũ không?

**Đáp án:** không. Transaction lưu không có lịch sử đọc của transaction trước đó nếu không mang token/trạng thái đã đọc sang. Cần `expectedVersion` hoặc HTTP precondition; isolation giúp tính nhất quán trong phạm vi transaction hiện tại và có thể sinh serialization errors.

### Bài 17 — HTTP conditional request

Một client gửi `If-Match: "product-101-v1"` nhưng server hiện ở version 2. Theo cơ chế HTTP precondition, mã phản hồi thông thường nào phù hợp?

**Đáp án:** `412 Precondition Failed`. Nếu API yêu cầu `If-Match` nhưng client không gửi, có thể dùng `428 Precondition Required` theo chính sách; với conflict từ body version, `409 Conflict` là lựa chọn phổ biến. Cần API contract thống nhất.

### Bài 18 — ABA

Một hàng bị DELETE rồi một hàng mới được chèn lại với cùng `product_id=101` và `version_no=1`. Client cũ giữ cặp `(101,1)` có thể bị vấn đề gì?

**Đáp án:** token cũ trông giống token mới dù danh tính/vòng đời thực thể đã đổi (*ABA*). Không nên tái sử dụng ID/token một cách mơ hồ; dùng generation token hoặc định danh mới khi cần bảo vệ mạnh.

### Bài 19 — Phân biệt retry an toàn

Hãy phân loại:

- A. UPDATE trả 0 do version cũ;
- B. Transaction báo serialization failure;
- C. UPDATE bị CHECK từ chối vì giá âm;
- D. Mất kết nối sau khi gửi câu trừ tồn, chưa biết đã commit chưa.

**Đáp án gợi ý:**

- A: đọc lại và quyết định merge/xung đột, không retry mù quáng payload cũ.
- B: rollback và cân nhắc retry **toàn transaction** với dữ liệu mới, giới hạn số lần.
- C: sửa/loại dữ liệu sai; retry nguyên yêu cầu không giải quyết.
- D: tra cứu trạng thái theo idempotency key/request log; không tự coi đây là yêu cầu bán mới.

### Bài 20 — Thiết kế một luồng chỉnh sửa sản phẩm

Hãy mô tả API cho phép người dùng A và B sửa cùng sản phẩm nhưng không ghi đè lẫn nhau.

**Gợi ý đáp án:**

1. `GET` trả dữ liệu và `version_no` hoặc ETag.
2. Client giữ token gắn với dữ liệu đang chỉnh.
3. `PUT/PATCH` gửi thay đổi cùng expected token.
4. Server validate input và chạy `UPDATE ... WHERE id=? AND version=? SET version=version+1`.
5. Nếu thành công: commit rồi trả dữ liệu/token mới.
6. Nếu 0 hàng: xác định not found/conflict theo quyền và trạng thái, trả lỗi có cấu trúc.
7. Client cho người dùng xem dữ liệu mới và xử lý hợp nhất nếu thích hợp.
8. Với thao tác có side effects/retry, thêm idempotency key và transaction liên quan.

## 22. Checklist triển khai

Trước khi chốt một cơ chế version check, hãy xác nhận:

1. **Khóa định danh:** Có `PRIMARY KEY`/`UNIQUE` đủ mạnh để chọn đúng một hàng?
2. **Token:** Có cột version không `NULL`, không dễ tái sử dụng, đủ phạm vi?
3. **Đọc:** Client có lấy **version cùng dữ liệu** lúc hiển thị không?
4. **Ghi:** Điều kiện `WHERE id=? AND version=?` có nằm trực tiếp trong UPDATE/DELETE không?
5. **Bump:** Token có thay đổi trong cùng câu ghi/trigger đúng quy tắc không?
6. **Mọi write path:** ORM, native SQL, admin, migration, job nền có tuân thủ không?
7. **Row count:** Có phân biệt 0/1/bất thường và transaction commit không?
8. **Xung đột:** Có thông báo người dùng, đọc lại và hợp nhất theo nghiệp vụ không?
9. **Retry:** Có phân biệt business conflict, serialization, deadlock và lỗi dữ liệu không?
10. **Idempotency:** Có chống một request được thực hiện nhiều lần không?
11. **Điều kiện nghiệp vụ:** Có guard `stock_qty>=n`, trạng thái, quyền, tenant nếu cần không?
12. **Nhiều hàng:** Có kiểm tra toàn bộ tập ID nếu cần all-or-nothing không?
13. **Multi-row invariant:** Có ràng buộc/khóa/isolation bổ sung ngoài row version khi cần không?
14. **API:** Có phiên bản/ETag rõ ràng, mã lỗi thống nhất và payload xung đột hữu ích không?
15. **DBMS:** Đã kiểm tra `RETURNING`/`OUTPUT`/rowcount, isolation và token của đúng engine/phiên bản chưa?
16. **Giám sát:** Có log conflict rate, deadlock, retries và lỗi xác thực phiên bản mà không lộ thông tin nhạy cảm?

## 23. Tổng kết

**Cập nhật có điều kiện theo phiên bản** giải quyết một rủi ro cụ thể: người dùng hoặc tác vụ ghi dữ liệu từ **trạng thái đã cũ**, vô tình xóa mất thay đổi của người khác.

Mẫu cốt lõi:

~~~sql
UPDATE inventory_products
SET
    unit_price = :new_price,
    stock_qty = :new_qty,
    version_no = version_no + 1
WHERE product_id = :id
  AND version_no = :expected_version;
~~~

- Nếu **đúng một hàng** được cập nhật, token khớp và database đã áp dụng thay đổi theo lệnh, với điều kiện transaction được commit thành công.
- Nếu **không hàng nào** được cập nhật, không nên âm thầm ghi đè. Có thể hàng không tồn tại, version đã đổi hoặc điều kiện nghiệp vụ không thỏa.
- Nếu có **lỗi transaction**, xử lý theo loại lỗi/isolation; không coi mọi lỗi là một conflict version.
- Nếu lệnh được **retry**, còn phải bảo vệ tính idempotent của nghiệp vụ, nhất là với tiền và tồn kho.

`version_no` phát huy tác dụng khi **cả điều kiện so sánh lẫn việc thay đổi token nằm trong thao tác ghi nguyên tử**, mọi đường ghi cùng tuân thủ chính sách và ứng dụng xử lý xung đột một cách có chủ đích.

**Nguyên tắc cần nhớ:** *đừng ghi đè dựa trên thông tin cũ; hãy buộc lệnh UPDATE chứng minh rằng trạng thái nó dựa vào vẫn còn là trạng thái hiện tại*.

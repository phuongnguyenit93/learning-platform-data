# Luồng từ yêu cầu ứng dụng đến câu lệnh SQL và dữ liệu trên đĩa

Khi người dùng nhấn **“Đặt hàng”** trên một ứng dụng, dữ liệu không được ghi thẳng từ giao diện xuống một tệp trên ổ đĩa. Yêu cầu đi qua nhiều lớp: mã nghiệp vụ, trình điều khiển kết nối, tiến trình Oracle Database, bộ xử lý SQL, bộ nhớ đệm và cơ chế lưu trữ bền vững. Hiểu đường đi này giúp phân biệt lỗi ứng dụng với lỗi SQL, lý giải vì sao truy vấn nhanh hoặc chậm, và hiểu điều gì thực sự xảy ra khi gọi `COMMIT`.

Trong bài này, **Oracle Database** là hệ quản trị cơ sở dữ liệu quan hệ; **SQL** là ngôn ngữ ứng dụng dùng để yêu cầu Oracle đọc hoặc thay đổi dữ liệu. Ví dụ sử dụng một ứng dụng Java kết nối tới Oracle qua JDBC. Các khái niệm cốt lõi cũng áp dụng khi ứng dụng dùng Spring Data JPA, Hibernate hoặc một ngôn ngữ lập trình khác.

## 1. Bức tranh tổng thể: một yêu cầu đi qua những lớp nào?

~~~mermaid
flowchart TD
    A["Người dùng / HTTP request"] --> B["Controller và nghiệp vụ ứng dụng"]
    B --> C["Repository / JDBC / connection pool"]
    C --> D["Kết nối Oracle Net và phiên CSDL"]
    D --> E["Server process: parse, bind, tối ưu, thực thi SQL"]
    E <--> F["SGA: shared pool, database buffer cache"]
    E <--> G["PGA: bộ nhớ riêng cho thực thi"]
    F <--> H["Datafile: các data block của bảng và chỉ mục"]
    E --> I["Trả hàng kết quả / số dòng thay đổi"]
    I --> B
    B --> J["HTTP response cho người dùng"]
    E -. "Khi có thay đổi dữ liệu" .-> K["Redo log buffer"]
    K --> L["LGWR ghi online redo log"]
    F -. "DBWn ghi dirty block khi cần" .-> H
~~~

Sơ đồ chỉ mô tả đường đi **điển hình** của một ứng dụng có kết nối trực tiếp tới một Oracle instance. Trong thực tế có thể có API gateway, nhiều dịch vụ, bộ nhớ đệm của ứng dụng, nhiều instance hoặc cơ chế I/O đặc biệt.

| Lớp | Thành phần tiêu biểu | Trách nhiệm |
|---|---|---|
| Người dùng và giao tiếp | Web/mobile, HTTP, REST API | Gửi ý định, ví dụ “đặt 2 sản phẩm”; nhận kết quả |
| Ứng dụng | Controller, service, validation | Xác thực yêu cầu, kiểm tra nghiệp vụ, xác định thao tác dữ liệu |
| Truy cập CSDL | JDBC, driver, connection pool, ORM | Tạo/gửi lệnh SQL, truyền tham số, quản lý kết nối và giao dịch |
| Oracle instance | Server process, SGA, PGA, background process | Phân tích và thực thi SQL; quản lý bộ nhớ, khóa, giao dịch và I/O |
| Lưu trữ | Tablespace, segment, extent, block, datafile | Tổ chức bản ghi và chỉ mục thành các khối dữ liệu được lưu bền vững |
| Phục hồi | Undo, redo, online redo log | Hỗ trợ nhất quán khi đọc, hoàn tác và phục hồi sau sự cố |

Điểm cần phân biệt ngay: **Oracle instance** gồm bộ nhớ và các tiến trình chạy; **Oracle database** theo nghĩa lưu trữ gồm những tệp cần thiết như datafile, control file và online redo log. Instance mở và thao tác với database. Đây là mô hình cơ bản của một instance; Oracle RAC có thể có nhiều instance truy cập cùng database.

## 2. Tình huống xuyên suốt: đặt hàng và trừ tồn kho

Giả sử hệ thống có hai bảng:

~~~sql
CREATE TABLE products (
    product_id   NUMBER(10) PRIMARY KEY,
    product_name VARCHAR2(100) NOT NULL,
    stock_qty    NUMBER(10) NOT NULL CHECK (stock_qty >= 0)
);

CREATE TABLE orders (
    order_id   NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id NUMBER(10) NOT NULL REFERENCES products(product_id),
    quantity   NUMBER(10) NOT NULL CHECK (quantity > 0),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

INSERT INTO products (product_id, product_name, stock_qty)
VALUES (101, 'Bàn phím cơ', 8);

COMMIT;
~~~

Ví dụ sử dụng cú pháp identity column của Oracle 12c trở lên. Các bảng chứa dữ liệu nghiệp vụ; ràng buộc `PRIMARY KEY`, `REFERENCES` và `CHECK` do Oracle thực thi để bảo vệ tính hợp lệ của dữ liệu. Những ràng buộc này không thay thế toàn bộ kiểm tra nghiệp vụ trong ứng dụng.

Người dùng gửi một yêu cầu giả định:

~~~http
POST /orders
Content-Type: application/json

{"productId":101,"quantity":2}
~~~

Ứng dụng cần thực hiện **hai thay đổi trong cùng một giao dịch**:

~~~sql
UPDATE products
SET stock_qty = stock_qty - :qty
WHERE product_id = :product_id
  AND stock_qty >= :qty;

INSERT INTO orders (product_id, quantity)
VALUES (:product_id, :qty);

COMMIT;
~~~

Trong đoạn SQL minh họa, `:qty` và `:product_id` là **bind variable** (biến ràng buộc). Câu lệnh `UPDATE` có điều kiện tồn kho và ứng dụng phải kiểm tra số dòng được cập nhật. Nếu bằng 0, cần dừng đặt hàng và `ROLLBACK`; tuyệt đối không mặc định rằng cả hai câu lệnh đều thành công. Việc kiểm tra tồn kho ngay trong `UPDATE` cũng giúp thao tác an toàn hơn khi nhiều giao dịch cạnh tranh trên cùng sản phẩm.

Một cách viết JDBC rút gọn nhưng có ranh giới giao dịch rõ ràng:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderService {
    private final DataSource dataSource;

    public OrderService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void placeOrder(long productId, int quantity) throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement reduceStock = connection.prepareStatement(
                         "UPDATE products SET stock_qty = stock_qty - ? " +
                         "WHERE product_id = ? AND stock_qty >= ?");
                     PreparedStatement createOrder = connection.prepareStatement(
                         "INSERT INTO orders (product_id, quantity) VALUES (?, ?)")) {

                    reduceStock.setInt(1, quantity);
                    reduceStock.setLong(2, productId);
                    reduceStock.setInt(3, quantity);

                    if (reduceStock.executeUpdate() != 1) {
                        throw new SQLException("Không có sản phẩm hoặc không đủ hàng");
                    }

                    createOrder.setLong(1, productId);
                    createOrder.setInt(2, quantity);
                    createOrder.executeUpdate();
                }
                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
~~~

JDBC dùng dấu `?` làm vị trí tham số, sau đó `setInt`/`setLong` truyền giá trị và kiểu dữ liệu. Việc dùng `PreparedStatement` giúp ứng dụng không ghép đầu vào của người dùng vào chuỗi SQL, giảm nguy cơ SQL injection và tạo điều kiện tái sử dụng câu lệnh. Trong ứng dụng Spring, `@Transactional` và tầng repository thường quản lý nhiều phần của quá trình này; ở phía Oracle vẫn có SQL, bind, session và giao dịch.

## 3. Từ HTTP request đến phiên Oracle

**Bước 1 — Ứng dụng hiểu ý định.** Controller nhận JSON, xác thực các trường và chuyển yêu cầu xuống service. Service quyết định rằng một đơn hàng hợp lệ cần giảm tồn kho và thêm bản ghi đơn hàng. Các thao tác nghiệp vụ không tự động trở thành SQL: chúng phải được thể hiện bằng câu lệnh cụ thể của repository hoặc ORM.

**Bước 2 — Lấy kết nối.** `DataSource` thường sử dụng **connection pool** để cấp lại một kết nối vật lý đã mở. Việc lấy connection từ pool không nhất thiết tạo TCP connection và đăng nhập Oracle mới cho mọi HTTP request. Một request cũng không nhất thiết chỉ dùng một SQL statement.

**Bước 3 — Giao tiếp với Oracle.** Oracle JDBC driver gửi lệnh, tham số và thông tin giao dịch qua giao thức kết nối Oracle Net. **Listener** thường giúp thiết lập phiên ban đầu và chuyển kết nối cho cơ chế server phù hợp; listener không phải thành phần phân tích hay thực thi mọi câu SQL. Trong mô hình dedicated server, một server process phục vụ phiên ứng dụng; hệ thống có thể được cấu hình shared server hoặc các cơ chế kết nối khác.

**Bước 4 — Ranh giới giao dịch.** `setAutoCommit(false)` cho phép hai câu DML cùng thuộc một giao dịch. Nếu ứng dụng để JDBC tự commit từng câu lệnh, `UPDATE` có thể đã được commit trước khi `INSERT` thất bại, khiến tồn kho và đơn hàng không còn đồng bộ.

## 4. Oracle làm gì khi nhận một câu lệnh SQL?

Quá trình xử lý logic thường được mô tả bằng **parse → optimize → execute → fetch**. Đây là các giai đoạn khái niệm; Oracle có thể tái sử dụng kết quả xử lý, tối ưu thích ứng và chạy các bước đan xen.

### 4.1 Parse: kiểm tra và nhận diện câu lệnh

Oracle kiểm tra cú pháp SQL, xác định các đối tượng như `products`, kiểm tra khả năng tham chiếu và quyền cần thiết, rồi tìm hoặc tạo cursor nội bộ phục vụ thực thi. SQL text, thông tin thực thi dùng chung và các cấu trúc liên quan có thể được lưu trong **shared pool** thuộc **SGA**.

- **Hard parse**: Oracle phải thực hiện công việc biên dịch/tối ưu để tạo cursor thực thi phù hợp; thường tốn CPU và có thể gây cạnh tranh tài nguyên.
- **Soft parse / cursor reuse**: tìm được cấu trúc đã có và đủ điều kiện dùng lại; giảm phần việc phải tính lại.

Hai câu `WHERE product_id = 101` và `WHERE product_id = 102` viết theo kiểu nối số trực tiếp có thể tạo nhiều SQL text. Dùng một câu `WHERE product_id = :id` và truyền giá trị qua bind giúp tăng khả năng dùng chung, dù **không bảo đảm** mọi lần thực thi dùng cùng execution plan.

### 4.2 Optimize: chọn cách lấy và xử lý dữ liệu

**Cost-Based Optimizer (CBO)** cân nhắc thống kê, điều kiện lọc, chỉ mục, phép join, khối lượng dữ liệu và các yếu tố khác để chọn **execution plan**. Chẳng hạn:

~~~sql
SELECT product_name, stock_qty
FROM products
WHERE product_id = :id;
~~~

Vì `product_id` là khóa chính, Oracle có thể sử dụng chỉ mục hỗ trợ khóa chính để tìm vị trí hàng, rồi lấy các cột còn lại ở data block của bảng. Plan có thể chứa các thao tác như `INDEX UNIQUE SCAN` và `TABLE ACCESS BY INDEX ROWID`. Đây là **khả năng hợp lý**, không phải đường đi bắt buộc: optimizer cũng có thể chọn full table scan nếu chi phí ước lượng tốt hơn.

Một execution plan mô tả **cách** Oracle dự định hoặc đã thực hiện SQL; nó không phải tập bản ghi kết quả. SQL là mô tả dữ liệu cần lấy hoặc thay đổi, còn optimizer quyết định nhiều chi tiết vật lý.

### 4.3 Execute và fetch: thực thi rồi trả kết quả

Server process thực hiện các thao tác trong plan: đọc các block cần thiết, so sánh điều kiện lọc, cập nhật hàng, thao tác với index, thực hiện join/sort... PGA có thể giữ trạng thái và vùng nhớ riêng của quá trình thực thi. Nếu sort/hash vượt khả năng bộ nhớ cấp cho thao tác, Oracle có thể sử dụng vùng tạm trên **TEMP tablespace**.

Với `SELECT`, ứng dụng tiếp tục **fetch** các hàng theo các đợt rồi driver trả dữ liệu về Java. Với `UPDATE` hoặc `INSERT`, JDBC nhận số dòng thay đổi hoặc lỗi từ Oracle. Khoảng thời gian thấy ở HTTP request bao gồm cả xử lý ứng dụng và truyền mạng, vì vậy không đồng nhất với thời gian Oracle chạy SQL.

## 5. Từ hàng dữ liệu logic đến block trong datafile

Người lập trình nhìn thấy **bảng** và **dòng**. Oracle lưu dữ liệu theo nhiều cấp tổ chức:

~~~text
Tablespace (không gian lưu trữ logic)
  └── Segment (ví dụ: một bảng hoặc một chỉ mục)
       └── Extent (nhóm data block liên tiếp)
            └── Oracle data block (đơn vị lưu trữ logic)
                 └── Dữ liệu hàng / cấu trúc chỉ mục

Tablespace
  └── Một hoặc nhiều datafile / tempfile tương ứng
       └── Lưu các block lên thiết bị lưu trữ
~~~

| Khái niệm | Ý nghĩa trong đường đi của SQL |
|---|---|
| **Row** | Bản ghi logic trong bảng, ví dụ sản phẩm 101 |
| **Data block** | Đơn vị Oracle quản lý để đọc/ghi dữ liệu; thường chứa nhiều hàng hoặc phần của hàng |
| **Extent** | Tập hợp nhiều data block được cấp cho một segment |
| **Segment** | Vùng lưu trữ dành cho bảng, chỉ mục, undo... |
| **Tablespace** | Lớp tổ chức logic giữa segment và datafile |
| **Datafile** | Tệp vật lý (hoặc tệp do ASM quản lý) chứa các block thuộc tablespace |
| **ROWID** | Địa chỉ/vị trí logic-vật lý Oracle dùng để định vị hàng trong nhiều loại bảng thông thường |

Chỉ mục B-tree lưu cấu trúc khóa và thông tin chỉ tới hàng; bản thân chỉ mục cũng được lưu trong block và segment riêng. Chỉ mục giúp giảm lượng dữ liệu phải duyệt ở nhiều truy vấn, nhưng cần thêm dung lượng và chi phí duy trì khi ghi dữ liệu.

### Buffer cache: vì sao “đọc bảng” chưa chắc chạm đĩa?

Oracle có **database buffer cache** thuộc SGA. Khi cần một data block:

1. Oracle tìm block trong buffer cache.
2. Nếu đã có bản sao phù hợp, tiến trình có thể sử dụng block trong bộ nhớ (**logical read**).
3. Nếu chưa có và thao tác yêu cầu truy cập datafile, Oracle thực hiện **physical read**, rồi có thể đưa block vào cache.
4. Lệnh `UPDATE` điển hình sửa block trong bộ nhớ, đánh dấu block đã thay đổi (**dirty block**); việc ghi block này xuống datafile không đồng nghĩa diễn ra ngay lúc ứng dụng gọi `UPDATE`.

Đường đi trên là mô hình phổ biến, không phải quy tắc cho mọi I/O: Oracle còn có cơ chế direct path I/O và những tối ưu khác. **Cache miss** và **physical read** cũng không có nghĩa mỗi lần đều phát sinh một lần đọc từ đĩa quay; lớp lưu trữ bên dưới có thể có cache riêng.

## 6. Khi INSERT/UPDATE: undo, redo, khóa và COMMIT

Đây là phần dễ nhầm nhất của toàn bộ chuỗi.

### 6.1 Khóa và undo trong một giao dịch đang chạy

Khi cập nhật `products`, Oracle cần bảo vệ hàng đang được sửa. Giao dịch khác muốn thay đổi chính hàng đó có thể phải chờ khóa hàng được giải phóng; Oracle không nhất thiết khóa toàn bộ bảng.

Oracle lưu **thông tin undo** đủ để hoàn tác thay đổi khi giao dịch `ROLLBACK` và hỗ trợ **consistent read** cho truy vấn cần thấy trạng thái dữ liệu phù hợp với thời điểm đọc. Undo thường được lưu trong undo segment thuộc undo tablespace. Nó không chỉ là một chuỗi các câu SQL đảo ngược.

Trong ví dụ, hai người cùng đặt hàng sản phẩm 101: câu `UPDATE ... stock_qty >= :qty` thực hiện điều kiện tồn kho tại cơ sở dữ liệu, kết hợp cơ chế khóa và tính nhất quán của Oracle. Ứng dụng vẫn phải xử lý trường hợp cập nhật được 0 hàng, timeout hoặc lỗi cạnh tranh khi cần.

### 6.2 Redo và datafile là hai đường ghi khác nhau

Oracle tạo các **redo record** ghi lại thông tin thay đổi cần cho phục hồi (bao gồm cả những thay đổi liên quan tới undo). Redo record được đưa vào **redo log buffer** trong SGA. Tiến trình nền **LGWR (Log Writer)** ghi redo vào **online redo log** trên thiết bị lưu trữ.

Đồng thời, các data block đã sửa trong buffer cache trở thành dirty block. Tiến trình **DBWn (Database Writer)** ghi dirty block về **datafile** vào những thời điểm phù hợp, ví dụ khi cần giải phóng buffer hay phục vụ checkpoint. DBWn có thể ghi block chứa thay đổi chưa commit; điều đó vẫn an toàn nhờ phối hợp redo/undo và quy tắc ghi redo trước khi ghi data block tương ứng.

~~~mermaid
flowchart TD
    A["UPDATE / INSERT trong giao dịch"] --> B["Thay đổi block trong buffer cache"]
    A --> C["Tạo undo và redo records"]
    C --> D["Redo log buffer"]
    D --> E["LGWR ghi online redo log"]
    B --> F["Dirty data block"]
    F --> G["DBWn ghi datafile khi cần"]
    E --> H["COMMIT có thể được xác nhận khi redo commit đã bền vững"]
~~~

**`COMMIT` không có nghĩa toàn bộ data block vừa sửa đã lập tức được DBWn ghi xuống datafile.** Với cơ chế commit thông thường, Oracle bảo đảm redo cần thiết, bao gồm thông tin commit, được LGWR ghi bền vững trước khi báo commit thành công. Dữ liệu có thể được ghi vào datafile sau đó; Oracle dùng redo khi phục hồi instance nếu xảy ra sự cố trước lúc dirty block được ghi hết. Có các tùy chọn commit bất đồng bộ chuyên biệt, nhưng không phải giả định mặc định của bài này.

Sau commit, giao dịch kết thúc và khóa của giao dịch được giải phóng. Nếu trước commit ứng dụng gọi `ROLLBACK`, Oracle sử dụng undo để hoàn tác ảnh hưởng logic của giao dịch. **Rollback không xóa lịch sử redo đã được ghi**, vì redo và undo phục vụ những mục đích khác nhau.

### 6.3 Một mốc thời gian đơn giản

| Thời điểm | Điều xảy ra | Cần hiểu đúng |
|---|---|---|
| T1 | `UPDATE products` trừ số lượng và sinh undo/redo | Thay đổi có thể vẫn chưa được commit |
| T2 | `INSERT orders` tạo đơn hàng và tiếp tục sinh undo/redo | Hai lệnh thuộc cùng giao dịch |
| T3 | Ứng dụng gọi `COMMIT` | Yêu cầu Oracle kết thúc giao dịch thành công |
| T4 | LGWR bảo đảm redo/commit record được ghi bền vững rồi Oracle xác nhận commit thông thường | Đây là mốc bền vững của commit |
| T5 | DBWn ghi các dirty block xuống datafile khi cần | Có thể trước hoặc sau T4; không phải tín hiệu riêng cho commit |

Nếu `INSERT` lỗi và ứng dụng rollback trước T3, hai thay đổi nghiệp vụ được hoàn tác như một đơn vị. Nếu tiến trình Oracle bị dừng đột ngột, khi khởi động/phục hồi, Oracle dùng redo để khôi phục các thay đổi cần thiết rồi dùng undo xử lý những giao dịch chưa hoàn tất.

**Online redo log**, **archive redo log** (khi bật `ARCHIVELOG`) và **datafile** là các đối tượng vật lý khác nhau. Redo dùng cho phục hồi, không phải nơi ứng dụng truy vấn bản ghi sản phẩm như một bảng SQL.

## 7. Khi SELECT: dữ liệu trả về có phải dữ liệu mới nhất trên đĩa không?

Giả sử một người khác gọi:

~~~sql
SELECT product_name, stock_qty
FROM products
WHERE product_id = :id;
~~~

Tại isolation level mặc định **READ COMMITTED** của Oracle, mỗi câu SQL thường có một góc nhìn dữ liệu nhất quán tại thời điểm câu lệnh bắt đầu. Oracle sử dụng **System Change Number (SCN)** và thông tin undo khi cần để xây dựng phiên bản đọc phù hợp. Vì thế:

- Nếu giao dịch đặt hàng chưa commit, một `SELECT` thông thường của phiên khác không được nhìn thấy thay đổi chưa commit đó.
- Nếu giao dịch đã commit trước thời điểm bắt đầu câu `SELECT`, câu truy vấn thường có thể nhìn thấy thay đổi theo quy tắc nhất quán của nó.
- Một câu `SELECT` có thể đọc dữ liệu từ buffer cache hoặc dựng lại phiên bản nhất quán bằng undo. Không cần chờ DBWn ghi toàn bộ dữ liệu xuống datafile rồi mới đọc được bản ghi đã commit.
- Hai câu `SELECT` riêng biệt trong cùng một giao dịch `READ COMMITTED` có thể thấy kết quả khác nhau nếu giao dịch khác commit giữa hai câu. Những isolation level khác có quy tắc riêng.

Điều này giải thích vì sao “giá trị hiện thấy khi truy vấn” không thể suy ra bằng việc mở trực tiếp datafile ở hệ điều hành. Datafile không phải định dạng văn bản với từng dòng SQL; Oracle quản lý block, metadata, transaction state và các phiên bản nhất quán.

## 8. Cùng một yêu cầu nghiệp vụ có thể tạo ra nhiều SQL và nhiều lần I/O

Một màn hình hiển thị **10 sản phẩm bán chạy nhất** có thể được ứng dụng biểu diễn bằng:

~~~sql
SELECT p.product_id,
       p.product_name,
       SUM(o.quantity) AS total_sold
FROM orders o
JOIN products p ON p.product_id = o.product_id
WHERE o.created_at >= :from_time
GROUP BY p.product_id, p.product_name
ORDER BY total_sold DESC
FETCH FIRST 10 ROWS ONLY;
~~~

Ở đây, một câu SQL gồm nhiều phép toán: lọc đơn theo thời gian, kết hợp đơn với sản phẩm, gom nhóm, tính tổng, sắp xếp và lấy 10 hàng đầu. Oracle có thể chọn nhiều chiến lược như nested loops hoặc hash join; cần thống kê và execution plan thực tế để biết cách nó làm trên một database cụ thể.

Các thao tác này có thể dẫn đến:

- Đọc các block bảng hoặc chỉ mục trong buffer cache, và đọc vật lý khi cần.
- Dùng PGA cho hash/sort, hoặc dùng TEMP nếu thao tác phải tràn ra vùng tạm.
- Trả về chỉ 10 hàng **nhưng** phải xử lý nhiều hàng nguồn để tính đủ kết quả.
- Phát sinh thêm round-trip mạng khi ứng dụng fetch kết quả.

Vì vậy **số hàng trả về**, **số hàng Oracle đã xử lý**, **số logical read**, **số physical read** và **thời gian API** là các đại lượng khác nhau.

## 9. Quan sát luồng thực thi mà không đoán cách Oracle chạy

Ta có thể dùng `EXPLAIN PLAN` để xem phương án thực thi ước lượng:

~~~sql
EXPLAIN PLAN FOR
SELECT product_name, stock_qty
FROM products
WHERE product_id = 101;

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Đọc những cột/thành phần như **Operation**, **Name**, **Rows**, **Cost** để thấy hướng truy cập dữ liệu. Có thể xuất hiện `INDEX UNIQUE SCAN`, `TABLE ACCESS BY INDEX ROWID` hoặc một đường đi khác. `EXPLAIN PLAN` phản ánh kế hoạch giải thích tại thời điểm gọi, **không tự cung cấp số dòng/I/O thực tế** của lần chạy ứng dụng. Muốn phân tích thực tế, khi có quyền và công cụ thích hợp có thể xem execution plan của cursor đã chạy (ví dụ qua `DBMS_XPLAN.DISPLAY_CURSOR` với thống kê runtime được thu thập), SQL trace hoặc công cụ giám sát của hệ thống.

Khi điều tra một API chậm, hãy liên hệ bằng chứng theo chuỗi:

1. **Ứng dụng:** request nào, nghiệp vụ nào, truy vấn nào, số lần gọi DB và thời gian chờ connection?
2. **Oracle SQL:** câu SQL và bind nào, plan nào, số hàng xử lý, CPU/I/O/wait ở đâu?
3. **Bộ nhớ và lưu trữ:** dữ liệu được phục vụ từ cache hay cần physical I/O, có sort spill ra TEMP, có chờ khóa hay LGWR?
4. **Phản hồi:** thời gian tổng thể bị chi phối bởi SQL, mạng, pool, xử lý ứng dụng hay nhiều yếu tố cộng lại?

Một `SELECT` chậm không nhất thiết là vì “đĩa chậm”; nó cũng có thể do plan kém, quá nhiều hàng phải đọc, chờ tài nguyên, khóa liên quan tới DML hoặc ứng dụng gọi SQL quá nhiều lần. Ngược lại, SQL nhanh cũng chưa bảo đảm endpoint nhanh nếu phía ứng dụng xử lý hoặc truyền dữ liệu tốn thời gian.

## 10. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “Ứng dụng ghi trực tiếp bảng SQL thành file.” | Ứng dụng gửi SQL; Oracle quản lý row, block, segment, datafile và cơ chế bền vững. |
| “Listener chạy SQL.” | Listener chủ yếu hỗ trợ thiết lập kết nối; SQL được xử lý trong kiến trúc server/session của Oracle. |
| “Có primary key là Oracle luôn đọc index.” | Khóa chính thường có chỉ mục hỗ trợ, nhưng optimizer quyết định đường đi thực thi. |
| “SELECT là một lần đọc ổ đĩa.” | Oracle có buffer cache; một SELECT có thể cần không, một hoặc rất nhiều lần I/O vật lý. |
| “COMMIT ghi xong mọi bảng xuống datafile.” | Commit thông thường được bảo đảm qua redo bền vững; DBWn ghi data block theo cơ chế riêng. |
| “Redo và undo là một.” | Redo ghi thông tin phục hồi thay đổi; undo hỗ trợ hoàn tác và nhất quán khi đọc. |
| “Hai SQL liên tiếp tự động thành một giao dịch.” | Cần cấu hình ranh giới giao dịch đúng; chế độ auto-commit có thể tách chúng. |
| “Chỉ trả 10 dòng nên chắc truy vấn nhẹ.” | Oracle có thể phải quét, join, gom nhóm hoặc sắp xếp tập dữ liệu lớn trước khi trả 10 dòng. |

## 11. Tự kiểm tra bằng tình huống

**Tình huống A:** `UPDATE` trừ kho thành công, nhưng `INSERT orders` vi phạm ràng buộc. Nếu cả hai cùng trong transaction chưa commit, ứng dụng nên `ROLLBACK`. Trừ kho sẽ bị hoàn tác về mặt nghiệp vụ; HTTP response phải báo thất bại phù hợp, thay vì trả thành công chỉ vì `UPDATE` đã chạy.

**Tình huống B:** Ứng dụng nhận xác nhận `COMMIT` thành công, ngay sau đó instance gặp sự cố trước lúc mọi dirty block được ghi xuống datafile. Khi phục hồi, Oracle có thể dùng online redo log để bảo toàn thay đổi đã commit. Vì vậy thời điểm **redo bền vững** quan trọng hơn việc nhìn thấy bản ghi mới trong datafile tại thời điểm commit.

**Tình huống C:** Một phiên đang sửa sản phẩm 101 nhưng chưa commit; phiên khác `SELECT stock_qty` ở chế độ đọc nhất quán thông thường. Phiên đọc thấy phiên bản phù hợp đã commit theo snapshot của câu lệnh, không đọc bừa giá trị đang sửa dở. Undo có thể giúp tạo phiên bản này.

**Tình huống D:** Cùng một câu `SELECT` lúc nhanh lúc chậm. Hãy so sánh bind, execution plan, lượng dữ liệu, cache/I/O và các wait event thay vì kết luận chỉ từ SQL text. Chạy câu lệnh hai lần có thể cho profile I/O khác nhau vì block lần đầu đã vào cache.

## 12. Kết nối toàn bộ hành trình

Một yêu cầu đặt hàng đi theo chuỗi: **HTTP → Java service → JDBC/transaction → Oracle session → parse/optimize/execute SQL → buffer cache, undo, redo và block dữ liệu → COMMIT → kết quả trả về ứng dụng**. Dữ liệu của bảng và chỉ mục được quản lý trong **segment → extent → data block → datafile**; trong khi đó redo log hỗ trợ phục hồi và undo hỗ trợ rollback/consistent read.

Khi cần lý giải bất kỳ lỗi hay vấn đề hiệu năng nào, hãy xác định chính xác nó nằm ở đâu trong chuỗi này. “Câu SQL đã chạy”, “giao dịch đã commit”, “block đã ghi vào datafile” và “người dùng đã nhận HTTP response” là **bốn sự kiện khác nhau**, dù chúng thường xuất hiện gần nhau trong một yêu cầu thành công.

# Oracle Database là gì và vai trò trong hệ thống ứng dụng

## 1. Bức tranh tổng quan

Một ứng dụng có thể hiển thị danh sách sản phẩm, tiếp nhận đơn hàng, quản lý tài khoản hoặc lập báo cáo. Để các chức năng đó hoạt động ổn định, ứng dụng cần một nơi **lưu dữ liệu lâu dài, truy vấn chính xác, kiểm soát thay đổi đồng thời và bảo vệ tính toàn vẹn**. Oracle Database là một hệ quản trị cơ sở dữ liệu thường đảm nhiệm vai trò này.

**Oracle Database** là hệ quản trị cơ sở dữ liệu quan hệ (*Relational Database Management System — RDBMS*) do Oracle phát triển. Dữ liệu được tổ chức chủ yếu thành các bảng có hàng và cột; các bảng liên kết với nhau bằng khóa; ứng dụng dùng **SQL** để đọc và thay đổi dữ liệu. Oracle Database còn cung cấp các cơ chế quản lý giao dịch, truy cập đồng thời, bảo mật, sao lưu, phục hồi và vận hành ở quy mô lớn.

Trong hệ thống ứng dụng, Oracle Database thường đóng vai trò **hệ thống lưu trữ dữ liệu nghiệp vụ có thẩm quyền** (*system of record*): trạng thái đơn hàng, số dư, thông tin khách hàng hay lịch sử giao dịch cần được quản lý nhất quán ở đây, thay vì chỉ nằm trong bộ nhớ của ứng dụng.

Sau bài này, bạn cần phân biệt được Oracle Database với ứng dụng dùng nó, hình dung đường đi của một yêu cầu đọc/ghi dữ liệu, và giải thích vì sao giao dịch, ràng buộc, bảo mật và phục hồi dữ liệu là trách nhiệm quan trọng của database engine.

## 2. Từ dữ liệu nghiệp vụ đến mô hình quan hệ

Giả sử ứng dụng bán hàng lưu thông tin khách hàng và đơn hàng. Một cách tổ chức quan hệ cơ bản là:

```text
CUSTOMERS                                   ORDERS
-----------------------------               ---------------------------------
customer_id (PK)  101 ──────────────┐       order_id (PK)       5001
email             lan@example.com   └────── customer_id (FK)   101
full_name         Nguyễn Lan                total_amount       249000
                                              status             NEW
```

- **Bảng (table):** tập các bản ghi cùng cấu trúc, ví dụ `CUSTOMERS` và `ORDERS`.
- **Hàng (row):** một khách hàng hoặc một đơn hàng cụ thể.
- **Cột (column):** thuộc tính như `email`, `total_amount`.
- **Khóa chính (primary key — PK):** nhận diện duy nhất một hàng, ví dụ `customer_id`.
- **Khóa ngoại (foreign key — FK):** tham chiếu khóa của bảng khác, ví dụ `ORDERS.customer_id` tham chiếu `CUSTOMERS.customer_id`.
- **Ràng buộc (constraint):** quy tắc được database thực thi, chẳng hạn email không trùng, tổng tiền không âm hoặc đơn hàng phải thuộc về khách hàng hợp lệ.

Mối quan hệ này cho phép ứng dụng hỏi: “Khách hàng A đã đặt những đơn hàng nào?” bằng một câu truy vấn kết hợp hai bảng (*join*), thay vì tự dò tìm và ghép các tệp dữ liệu rời rạc.

### SQL và PL/SQL làm nhiệm vụ gì?

**SQL (Structured Query Language)** là ngôn ngữ để mô tả và thao tác dữ liệu quan hệ:

| Nhóm câu lệnh | Ví dụ | Vai trò |
|---|---|---|
| DDL (*Data Definition Language*) | `CREATE TABLE`, `ALTER TABLE` | Định nghĩa hoặc thay đổi cấu trúc đối tượng |
| DML (*Data Manipulation Language*) | `INSERT`, `UPDATE`, `DELETE` | Thêm, sửa, xóa dữ liệu |
| Truy vấn | `SELECT` | Đọc, lọc, kết hợp, tổng hợp dữ liệu |
| Điều khiển giao dịch | `COMMIT`, `ROLLBACK`, `SAVEPOINT` | Xác nhận hoặc hủy thay đổi trong giao dịch |
| Điều khiển quyền | `GRANT`, `REVOKE` | Cấp hoặc thu hồi quyền truy cập |

**PL/SQL** là ngôn ngữ thủ tục của Oracle mở rộng SQL với biến, điều kiện, vòng lặp, xử lý ngoại lệ và các đơn vị chương trình như procedure, function, package, trigger. SQL phù hợp để diễn đạt *cần lấy hoặc thay đổi dữ liệu gì*; PL/SQL hữu ích khi logic cần chạy sát dữ liệu. Không phải mọi quy tắc nghiệp vụ đều nên đưa vào PL/SQL: ứng dụng vẫn thường giữ luồng xử lý, API và tích hợp bên ngoài trong tầng dịch vụ.

## 3. Oracle Database nằm ở đâu trong kiến trúc ứng dụng?

Trong mô hình nhiều tầng, người dùng không thường kết nối trực tiếp đến cơ sở dữ liệu. Họ tương tác với giao diện; ứng dụng phía máy chủ kiểm tra yêu cầu, thực thi nghiệp vụ và gửi SQL đến Oracle.

```text
       Người dùng (web/mobile)
                 |
                 v
       API / Backend (ví dụ Java, Spring Boot)
       - Xác thực người dùng
       - Kiểm tra dữ liệu đầu vào
       - Điều phối nghiệp vụ
                 |
                 v
       Driver JDBC + connection pool
                 |
           Oracle Net
                 |
                 v
       Listener / Database service
                 |
                 v
       Oracle Database
       +------------------------------------+
       | Instance: bộ nhớ + tiến trình      |
       |   SQL processing / transaction     |
       |                 |                  |
       | Database: data files, redo logs,   |
       |           control files            |
       +------------------------------------+
                 |
                 v
       Kết quả truy vấn / trạng thái ghi
           trả về Backend -> người dùng
```

Các thành phần trong sơ đồ có trách nhiệm khác nhau:

1. **Web/mobile:** hiển thị dữ liệu và thu nhận thao tác của người dùng.
2. **Backend:** kiểm tra quyền và quy tắc nghiệp vụ, mở giao dịch, gọi SQL, xử lý kết quả hoặc lỗi. Backend không nên phụ thuộc vào việc người dùng gửi SQL trực tiếp.
3. **JDBC/driver:** giúp chương trình Java giao tiếp với Oracle bằng giao thức phù hợp. **Connection pool** tái sử dụng các kết nối để giảm chi phí tạo kết nối liên tục.
4. **Listener và service:** giúp ứng dụng tìm đúng dịch vụ Oracle khi thiết lập kết nối. Listener không phải bộ phận trực tiếp xử lý mọi câu SQL; việc thực thi gắn với phiên làm việc và các tiến trình máy chủ của Oracle.
5. **Oracle Database:** phân tích và tối ưu SQL, đọc/ghi dữ liệu, áp dụng ràng buộc, quản lý giao dịch và quyền truy cập, phục hồi khi có sự cố.

Ví dụ cú pháp URL kết nối Oracle JDBC Thin qua service name:

```properties
spring.datasource.url=jdbc:oracle:thin:@//db.example.internal:1521/app_service
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASSWORD}
```

`db.example.internal`, cổng `1521` và `app_service` chỉ là giá trị minh họa. Host, cổng và service thực tế phụ thuộc cấu hình triển khai; tên đăng nhập và mật khẩu nên lấy từ nơi quản lý bí mật của môi trường, không ghi cố định trong mã nguồn.

### Phân biệt database, instance, schema và service

Các khái niệm gần nhau nhưng không đồng nghĩa:

| Khái niệm | Hiểu đơn giản | Dùng để làm gì? |
|---|---|---|
| **Oracle Database** | Hệ quản trị Oracle và cơ sở dữ liệu đang được quản lý; trong cách nói về kiến trúc, *database* thường chỉ tập tệp lưu trữ vật lý | Lưu bền dữ liệu và cấu trúc cần thiết cho khôi phục |
| **Instance** | Bộ nhớ và các tiến trình Oracle phục vụ việc truy cập một database | Thực thi yêu cầu, quản lý cache, giao dịch và tác vụ nền |
| **Schema** | Tập đối tượng thuộc một người dùng database, như bảng, view, index, procedure | Tổ chức và quản lý các đối tượng dữ liệu của ứng dụng |
| **User** | Danh tính trong database gắn với cơ chế xác thực và quyền | Kết nối, sở hữu schema hoặc được cấp quyền trên đối tượng |
| **Service** | Tên logic mà ứng dụng dùng để kết nối đến nhóm phiên/khối lượng công việc được phục vụ | Định tuyến kết nối đến đúng nơi xử lý |
| **Tablespace** | Đơn vị lưu trữ logic gồm các datafile | Tổ chức không gian lưu trữ cho đối tượng dữ liệu |

Trong các triển khai Oracle hiện đại, kiến trúc **multitenant** có thể dùng **CDB (container database)** chứa một hoặc nhiều **PDB (pluggable database)**. Một ứng dụng thường kết nối tới service của PDB được cấp cho nó. Điều này khác với quan hệ giữa `schema` và `table`: một PDB có thể chứa nhiều schema, mỗi schema chứa nhiều đối tượng. Chi tiết quản trị CDB/PDB do DBA và nền tảng triển khai quyết định.

## 4. Điều gì xảy ra khi ứng dụng truy vấn dữ liệu?

Ví dụ người dùng mở trang “Đơn hàng của tôi”:

1. Trình duyệt gọi API, ví dụ `GET /api/orders`.
2. Backend xác thực người dùng và xác định `customer_id` được phép truy cập; ID này phải được kiểm chứng từ ngữ cảnh xác thực, không chỉ tin dữ liệu client gửi.
3. Backend mượn một kết nối từ connection pool và gửi câu `SELECT` có tham số.
4. Oracle phân tích câu SQL, kiểm tra quyền, chọn kế hoạch thực thi thông qua **optimizer**, đọc dữ liệu từ bộ nhớ đệm hoặc lưu trữ khi cần.
5. Oracle trả về các hàng kết quả. Backend chuyển thành DTO/JSON và trả cho giao diện.
6. Kết nối được trả về pool để tái sử dụng.

Oracle tự quyết định cách tìm dữ liệu dựa trên kế hoạch thực thi: có thể quét bảng, dùng index hoặc kết hợp nhiều kỹ thuật. Ứng dụng nên viết SQL rõ ràng, truyền tham số đúng kiểu và đánh giá các truy vấn quan trọng bằng dữ liệu, chỉ số cùng execution plan thực tế.

## 5. Ví dụ SQL: tạo cấu trúc, ghi và đọc đơn hàng

Đoạn sau sử dụng cú pháp Oracle SQL, minh họa hai bảng có liên kết và các ràng buộc cơ bản. Đây là mô hình tối giản phục vụ học tập, chưa phải lược đồ đầy đủ cho hệ thống bán hàng.

```sql
CREATE TABLE app_customers (
    customer_id NUMBER GENERATED BY DEFAULT AS IDENTITY,
    email       VARCHAR2(255) NOT NULL,
    full_name   VARCHAR2(200) NOT NULL,
    CONSTRAINT pk_app_customers PRIMARY KEY (customer_id),
    CONSTRAINT uk_app_customers_email UNIQUE (email)
);

CREATE TABLE app_orders (
    order_id     NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_id  NUMBER NOT NULL,
    ordered_at   TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    status       VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    total_amount NUMBER(12, 2) NOT NULL,
    CONSTRAINT pk_app_orders PRIMARY KEY (order_id),
    CONSTRAINT fk_app_orders_customer
        FOREIGN KEY (customer_id) REFERENCES app_customers(customer_id),
    CONSTRAINT ck_app_orders_amount CHECK (total_amount >= 0),
    CONSTRAINT ck_app_orders_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE INDEX ix_app_orders_customer ON app_orders(customer_id);
```

Một số điểm cần chú ý:

- `NUMBER` chứa số, `VARCHAR2` chứa chuỗi ký tự, `TIMESTAMP WITH TIME ZONE` thể hiện thời điểm có thông tin múi giờ. Không nên dùng số thực nhị phân để lưu số tiền; ở đây `NUMBER(12, 2)` biểu diễn hai chữ số phần thập phân.
- `IDENTITY` để Oracle tạo giá trị định danh theo cơ chế cột identity.
- `NOT NULL`, `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY`, `CHECK` được Oracle cưỡng chế ngay cả khi có nhiều ứng dụng cùng ghi dữ liệu.
- Index trên `customer_id` có thể giúp các thao tác lọc/join theo khách hàng, nhưng hiệu quả phụ thuộc truy vấn, phân bố dữ liệu và kế hoạch thực thi. Index cũng có chi phí lưu trữ và cập nhật.

Thêm dữ liệu minh họa:

```sql
INSERT INTO app_customers (email, full_name)
VALUES ('lan@example.com', 'Nguyễn Lan');

INSERT INTO app_orders (customer_id, total_amount)
SELECT customer_id, 249000
FROM app_customers
WHERE email = 'lan@example.com';

COMMIT;
```

Đọc đơn hàng theo email khách hàng:

```sql
SELECT o.order_id,
       o.ordered_at,
       o.status,
       o.total_amount
FROM app_orders o
JOIN app_customers c ON c.customer_id = o.customer_id
WHERE c.email = :email
ORDER BY o.ordered_at DESC;
```

`:email` là **bind variable** (biến liên kết) do công cụ hoặc driver truyền vào, không phải lời nhắc nối trực tiếp chuỗi từ người dùng thành câu SQL. Trong Java/JDBC, placeholder thường viết là dấu `?` rồi gán giá trị qua `PreparedStatement`. Cách làm này giảm nguy cơ SQL injection và giúp database xử lý câu lệnh có tham số hiệu quả hơn.

## 6. Oracle bảo đảm tính nhất quán của giao dịch như thế nào?

**Giao dịch (transaction)** là một đơn vị công việc gồm một hoặc nhiều thao tác dữ liệu. Những thay đổi trong giao dịch được xác nhận bằng `COMMIT`, hoặc bị hủy bằng `ROLLBACK`. Điều này đặc biệt quan trọng khi một hành động nghiệp vụ cần nhiều bước cùng thành công.

Ví dụ xử lý đặt hàng cần trừ tồn kho và ghi đơn hàng:

```text
Bắt đầu giao dịch
    |
    +--> Trừ tồn kho nếu số lượng còn đủ
    |         |
    |         +-- Không đủ hàng / lỗi? --> ROLLBACK
    |
    +--> Tạo đơn hàng
    |         |
    |         +-- Lỗi ràng buộc? -------> ROLLBACK
    |
    +--> Thành công tất cả bước --------> COMMIT
```

Nếu trừ tồn kho thành công nhưng chèn đơn hàng thất bại, rollback giúp tránh trạng thái “mất hàng nhưng không có đơn”. Database chịu trách nhiệm bảo đảm các thay đổi thuộc **cùng một giao dịch** có tính nguyên tử. Ứng dụng chịu trách nhiệm xác định đâu là ranh giới giao dịch và xử lý tình huống nghiệp vụ thất bại.

### ACID — bốn thuộc tính cốt lõi

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| **Atomicity** — nguyên tử | Các thay đổi trong một giao dịch thành công cùng nhau hoặc được hoàn tác | Trừ tồn kho và tạo đơn hàng phải đi cùng nhau |
| **Consistency** — nhất quán | Giao dịch hợp lệ giữ database trong trạng thái thỏa các quy tắc, ràng buộc đã khai báo | Không thể ghi đơn hàng tham chiếu khách hàng không tồn tại |
| **Isolation** — cô lập | Các giao dịch đồng thời được điều phối theo mức cô lập đã chọn | Người đọc không nhìn thấy thay đổi chưa commit từ giao dịch khác |
| **Durability** — bền vững | Khi commit thành công theo cấu hình bảo đảm của hệ thống, dữ liệu có thể được khôi phục sau sự cố theo cơ chế lưu log/phục hồi | Đơn hàng đã commit không phụ thuộc vào việc tiến trình backend còn chạy |

Oracle có những cơ chế nền tảng phục vụ ACID và truy cập đồng thời:

- **UNDO:** giữ thông tin cần thiết để hoàn tác thay đổi và tạo góc nhìn dữ liệu nhất quán cho truy vấn.
- **REDO:** ghi lại thông tin thay đổi để database có thể phục hồi các giao dịch đã được ghi nhận phù hợp khi có sự cố.
- **Read consistency / MVCC:** một truy vấn có thể đọc phiên bản dữ liệu nhất quán theo thời điểm thích hợp, giảm xung đột giữa hoạt động đọc và ghi.
- **Khóa (locking):** điều phối các thay đổi có thể xung đột; các phiên cùng sửa một hàng vẫn có thể phải chờ nhau.
- **SCN (System Change Number):** mốc logic Oracle dùng để theo dõi thứ tự và tính nhất quán của thay đổi.

Mức cô lập mặc định phổ biến trong Oracle là **READ COMMITTED**: mỗi câu lệnh thường thấy dữ liệu đã commit phù hợp với thời điểm bắt đầu câu lệnh đó. Vì thế, hai lần `SELECT` trong cùng một transaction có thể trả về kết quả khác nhau nếu giao dịch khác đã commit ở giữa. Khi cần yêu cầu đồng thời mạnh hơn, cần cân nhắc mức cô lập, khóa, kiểm soát phiên bản và quy tắc nghiệp vụ thích hợp.

**Giới hạn quan trọng:** giao dịch Oracle không tự động bao trùm một lời gọi HTTP ra cổng thanh toán hoặc việc gửi email. Nếu ứng dụng vừa `COMMIT` đơn hàng vừa gọi dịch vụ bên ngoài, cần cơ chế phối hợp như idempotency, outbox và xử lý sự kiện để giải quyết lỗi giữa các hệ thống.

## 7. Từ SQL đến mã ứng dụng Java

Với Java, Oracle JDBC driver cung cấp kết nối và `PreparedStatement`; ứng dụng thường dùng Spring JDBC, JPA/Hibernate hoặc lớp repository để thao tác. Ví dụ trực tiếp dưới đây cho thấy câu `INSERT` có tham số và quản lý commit/rollback ở JDBC:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public class OrderRepository {
    public void createOrder(DataSource dataSource,
                            long customerId,
                            BigDecimal totalAmount) throws SQLException {
        String sql = "INSERT INTO app_orders (customer_id, total_amount) VALUES (?, ?)";

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try (PreparedStatement statement = connection.prepareStatement(sql)) {
                statement.setLong(1, customerId);
                statement.setBigDecimal(2, totalAmount);
                statement.executeUpdate();
                connection.commit();
            } catch (SQLException exception) {
                connection.rollback();
                throw exception;
            }
        }
    }
}
```

Ví dụ chỉ ghi một bảng để tập trung vào cách làm việc với Oracle. Trong nghiệp vụ thật, các thao tác ghi liên quan sẽ dùng cùng một kết nối/giao dịch khi cần cam kết nguyên tử. Nếu dùng Spring `@Transactional`, framework có thể quản lý ranh giới giao dịch; không tự trộn việc tự `commit()` với transaction do framework quản lý.

Lưu ý `executeUpdate()` trả số hàng bị tác động; ứng dụng nên kiểm tra giá trị đó khi kết quả ảnh hưởng đến quy tắc nghiệp vụ. Một lỗi `SQLException` có thể đến từ mất kết nối, quyền truy cập, ràng buộc dữ liệu hoặc tranh chấp tài nguyên; phần xử lý phía trên minh họa rollback và chuyển lỗi để tầng cao hơn quyết định phản hồi.

## 8. Vai trò chính của Oracle trong hệ thống ứng dụng

| Vai trò | Oracle cung cấp | Phần ứng dụng vẫn phải làm |
|---|---|---|
| **Lưu trữ bền vững** | Bảng, index, datafile, quản lý lưu trữ | Xác định dữ liệu nào phải lưu và vòng đời dữ liệu |
| **Giữ toàn vẹn dữ liệu** | PK, FK, `UNIQUE`, `CHECK`, `NOT NULL`, transaction | Diễn đạt quy tắc nghiệp vụ và thiết kế schema đúng |
| **Truy vấn và báo cáo** | SQL, `JOIN`, tổng hợp, optimizer, index | Xây API, phân trang, giới hạn truy vấn, chọn dữ liệu phù hợp |
| **Xử lý đồng thời** | Cơ chế isolation, read consistency, locking | Xác định xung đột cần ngăn và cách thử lại khi cần |
| **Bảo mật dữ liệu** | User, role, privilege, auditing, tùy chọn mã hóa | Xác thực người dùng cuối, phân quyền nghiệp vụ, quản lý secrets |
| **Khả dụng và khôi phục** | Backup/recovery và các phương án HA/DR | Thiết kế SLA, vận hành giám sát, kiểm thử phương án khôi phục |
| **Tích hợp** | Kết nối qua driver, SQL, công cụ và cơ chế dữ liệu | Quản lý hợp đồng API, sự kiện và đồng bộ giữa dịch vụ |

Để phân định trách nhiệm rõ hơn, hãy so sánh Oracle với những thành phần hay gặp khác:

| Thành phần | Trách nhiệm điển hình | Có thay thế hoàn toàn Oracle không? |
|---|---|---|
| Backend Java/Spring | Xử lý request, xác thực, nghiệp vụ, gọi hệ thống khác | Không; trạng thái chỉ lưu trong RAM sẽ mất khi tiến trình dừng |
| Cache như Redis | Tăng tốc truy cập dữ liệu hoặc giữ dữ liệu tạm | Thường không; cache có chiến lược hết hạn/đồng bộ riêng |
| Message broker | Chuyển và điều phối thông điệp bất đồng bộ | Không; broker không tự thay schema và giao dịch nghiệp vụ quan hệ |
| Search engine | Tìm kiếm văn bản/phân tích theo chỉ mục chuyên dụng | Không; dữ liệu search thường được đồng bộ từ nguồn chuẩn |
| Oracle Database | Lưu trạng thái nghiệp vụ và thực thi các thao tác dữ liệu nhất quán | Là tầng dữ liệu; vẫn cần các tầng ứng dụng và vận hành phù hợp |

Kiến trúc thực tế có thể kết hợp tất cả thành phần này. Chẳng hạn, đơn hàng được commit trong Oracle, sự kiện được xuất sang broker, chỉ mục tìm kiếm được cập nhật bất đồng bộ và cache bị vô hiệu hóa khi dữ liệu thay đổi.

## 9. Các khả năng vận hành thường gắn với Oracle

### Bảo mật và phân quyền

Database có thể hạn chế một tài khoản chỉ được `SELECT` hoặc chỉ được thao tác trên một số bảng, view và procedure. Ứng dụng nên kết nối bằng tài khoản có **quyền tối thiểu cần thiết**, không dùng tài khoản quản trị cho lưu lượng thường ngày. Những môi trường có yêu cầu bảo mật cao có thể bổ sung mã hóa dữ liệu ở trạng thái lưu trữ, mã hóa đường truyền, auditing, chính sách truy cập theo hàng hoặc cột tùy phiên bản, tính năng và cấu hình.

Lưu ý quyền của **người dùng cuối** và quyền của **tài khoản kết nối database** không đồng nhất. Nếu mọi yêu cầu đi qua một tài khoản ứng dụng, backend vẫn phải kiểm tra ai được xem hoặc sửa đơn hàng nào; database không thể suy ra người dùng cuối chỉ từ tên tài khoản kết nối.

### Sao lưu, phục hồi và khả dụng

- **RMAN (Recovery Manager)** là công cụ Oracle hỗ trợ tác vụ sao lưu và khôi phục; chính sách backup cần phù hợp mục tiêu khôi phục của hệ thống.
- **Data Guard** cung cấp các mô hình duy trì standby database nhằm hỗ trợ sẵn sàng và phục hồi thảm họa theo cấu hình triển khai.
- **Real Application Clusters (RAC)** cho phép nhiều instance Oracle phối hợp truy cập một database trong mô hình phù hợp, phục vụ yêu cầu sẵn sàng và mở rộng năng lực xử lý.
- **Giám sát** cần theo dõi dung lượng, độ trễ truy vấn, phiên kết nối, khóa chờ, lỗi, backup và các chỉ báo phục hồi.

Có backup không đồng nghĩa chắc chắn khôi phục được. Đội vận hành còn cần thử khôi phục định kỳ, xác định **RPO** (mức dữ liệu tối đa có thể mất) và **RTO** (thời gian mục tiêu khôi phục), cùng quy trình ứng phó khi lỗi xảy ra. Khả năng và quyền sử dụng các tính năng nâng cao phụ thuộc phiên bản, edition, giấy phép và dịch vụ Oracle cụ thể.

### Hiệu năng và khả năng mở rộng

Oracle cung cấp optimizer, index, partitioning trong các môi trường hỗ trợ, thống kê dữ liệu và công cụ phân tích kế hoạch thực thi. Dù vậy, hiệu năng còn phụ thuộc thiết kế bảng, kiểu truy vấn, chỉ mục, phân trang, kích thước pool, mức độ đồng thời và tài nguyên hạ tầng. Không có một chỉ mục hoặc cấu hình “tăng tốc mọi truy vấn”.

## 10. Những nguyên tắc nên nhớ khi thiết kế ứng dụng dùng Oracle

1. **Thiết kế schema theo dữ liệu nghiệp vụ.** Chọn khóa, ràng buộc, quan hệ và kiểu dữ liệu phù hợp; tránh lưu mọi thứ vào một cột chuỗi khó kiểm soát.
2. **Để database bảo vệ các bất biến dữ liệu.** Ví dụ, dùng `UNIQUE` để ngăn email trùng; chỉ kiểm tra ở frontend/backend không đủ khi có nhiều request đồng thời.
3. **Dùng bind variable hoặc `PreparedStatement`.** Không xây SQL bằng cách ghép trực tiếp dữ liệu người dùng.
4. **Chọn ranh giới transaction có chủ ý.** Gom các bước ghi phải nguyên tử; tránh giữ giao dịch quá lâu trong lúc đợi mạng hoặc gọi dịch vụ ngoài.
5. **Sử dụng connection pool đúng cách.** Giới hạn số kết nối theo khả năng hệ thống; trả kết nối về pool qua cơ chế đóng tài nguyên phù hợp.
6. **Phân quyền theo nhu cầu.** Không nhúng mật khẩu vào repository hoặc log; ưu tiên kết nối mã hóa và quản lý bí mật tập trung.
7. **Theo dõi hiệu năng bằng số liệu.** Xem kế hoạch thực thi, số hàng đọc, thời gian chờ, khóa tranh chấp trước khi thêm index hoặc thay cấu hình.
8. **Đặt kế hoạch sao lưu và phục hồi ngay từ đầu.** Khả năng hoạt động của ứng dụng phụ thuộc cả dữ liệu có thể được phục hồi sau sự cố.

Một số nhầm lẫn phổ biến:

- **“Database chỉ là một thư mục chứa file.”** Thực tế Oracle gồm engine xử lý SQL, bộ nhớ, tiến trình, cơ chế giao dịch và thành phần lưu trữ phức tạp.
- **“Chỉ cần validate ở Java là đủ.”** Hai request đồng thời hoặc một tiến trình khác vẫn có thể tạo dữ liệu không hợp lệ nếu database thiếu ràng buộc quan trọng.
- **“`SELECT` luôn chặn `UPDATE`.”** Oracle sử dụng read consistency; nhiều truy vấn đọc thông thường có thể diễn ra đồng thời với thao tác ghi, dù một số xung đột ghi và kiểu khóa vẫn gây chờ.
- **“Mọi câu SQL đều tự rollback khi backend báo lỗi.”** Kết quả phụ thuộc ranh giới giao dịch và việc commit đã xảy ra hay chưa; DDL trong Oracle còn có hành vi commit ngầm cần đặc biệt lưu ý khi thiết kế migration.
- **“Đã có database thì không cần cơ chế chống ghi trùng.”** Khi mạng lỗi sau commit, client có thể thử lại; ứng dụng vẫn cần idempotency hoặc khóa nghiệp vụ duy nhất để tránh tạo đơn hàng/thu tiền trùng.

## 11. Tình huống tổng hợp: một yêu cầu đặt hàng

Xét hành trình một khách hàng nhấn **Đặt hàng** trên website:

```text
Người dùng
   |
   v
POST /orders
   |
   v
Backend xác thực, kiểm tra giỏ hàng và quyền mua
   |
   v
Mở transaction với Oracle
   |
   +--> Kiểm tra/cập nhật tồn kho theo điều kiện
   +--> Thêm ORDERS và ORDER_ITEMS
   +--> Áp dụng PK, FK, CHECK, UNIQUE cần thiết
   |
   +--> Nếu lỗi: ROLLBACK, trả lỗi phù hợp
   |
   +--> Nếu thành công: COMMIT
   |
   v
Trả mã đơn hàng; xử lý bước bên ngoài database
(thông báo, thanh toán, vận chuyển) theo luồng đã thiết kế
```

Trong ví dụ này, Oracle bảo đảm những thay đổi dữ liệu **thuộc cùng transaction** tuân theo cơ chế commit/rollback và các ràng buộc đã khai báo. Backend đảm bảo khách hàng có quyền đặt hàng, kiểm tra yêu cầu, điều phối API và quyết định xử lý thất bại. Với thanh toán hoặc gửi thông báo qua dịch vụ khác, hệ thống cần thêm thiết kế nhất quán liên dịch vụ.

### Tự kiểm tra hiểu bài

1. **Nếu backend Java bị khởi động lại, đơn hàng đã commit nằm ở đâu?** — Trong cơ sở dữ liệu Oracle; dữ liệu bền vững không phụ thuộc vòng đời tiến trình backend.
2. **Nếu hai request cùng ghi một email, điều gì ngăn hai hàng trùng nhau?** — Ràng buộc `UNIQUE` tại database là hàng rào cuối; ứng dụng cũng nên xử lý lỗi vi phạm ràng buộc để phản hồi rõ ràng.
3. **Vì sao Java nên dùng `PreparedStatement`?** — Để truyền tham số an toàn theo kiểu dữ liệu và tránh ghép SQL từ đầu vào chưa tin cậy.
4. **Listener có phải nơi thực thi mọi `SELECT` không?** — Không; listener hỗ trợ thiết lập kết nối đến service, còn phiên và các tiến trình Oracle phục vụ xử lý SQL.
5. **Nếu Oracle đã commit đơn hàng nhưng gửi email thất bại, có thể dùng `ROLLBACK` để thu hồi email không?** — Không; email thuộc hệ thống bên ngoài transaction Oracle, nên cần quy trình thử lại hoặc bù trừ phù hợp.

## 12. Kết luận

Oracle Database là một **hệ quản trị cơ sở dữ liệu quan hệ**, không đơn thuần là nơi lưu các bảng. Trong ứng dụng, nó đảm nhiệm lưu trữ có cấu trúc, thực thi SQL, áp dụng ràng buộc dữ liệu, điều phối các giao dịch đồng thời, hỗ trợ bảo mật và phục hồi. Các tầng web, backend và dịch vụ tích hợp giải quyết phần giao tiếp, phân quyền nghiệp vụ và điều phối quy trình; Oracle cung cấp nền tảng dữ liệu tin cậy để các tầng đó hoạt động. Hiểu rõ ranh giới trách nhiệm này là bước đầu để học tiếp thiết kế bảng, SQL, transaction, tối ưu truy vấn và vận hành Oracle trong hệ thống Java thực tế.

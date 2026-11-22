# SQL injection, prepared statement và kiểm soát định danh động

SQL injection xảy ra khi dữ liệu đầu vào làm thay đổi cấu trúc câu lệnh SQL. Với MySQL, cách phòng vệ cốt lõi là tách câu lệnh khỏi giá trị dữ liệu bằng prepared statement. Khi ứng dụng cần thay đổi tên bảng, tên cột hoặc chiều sắp xếp, phải chọn các mảnh SQL từ danh sách cho phép đã định nghĩa trong mã nguồn; placeholder không thể thay thế định danh hay từ khóa SQL.

Bài học này thuộc chương **Bảo mật** của module **DATABASE_MYSQL**. Nội dung tập trung vào cách xây dựng truy vấn an toàn trong ứng dụng dùng MySQL, đặc biệt ở những điểm thường bị bỏ sót như sắp xếp động, lọc theo danh sách và SQL động trong stored procedure.

Trong module DATABASE_MYSQL, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; đồng thời thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài này tập trung vào khía cạnh bảo mật truy vấn trong lộ trình đó: giữ dữ liệu đầu vào tách khỏi cú pháp SQL và giới hạn các định danh động.

## 1. SQL injection hình thành như thế nào?

Một câu SQL có cả **cấu trúc** và **giá trị**. Cấu trúc gồm từ khóa, tên bảng, tên cột, toán tử và điều kiện. Giá trị là dữ liệu như email, mã khách hàng hoặc ngày tạo. Lỗi injection xuất hiện khi ứng dụng ghép dữ liệu không tin cậy trực tiếp vào phần cấu trúc.

Ví dụ sau không an toàn:

~~~js
const email = req.query.email;
const sql =
  "SELECT id, email FROM users WHERE email = '" + email + "'";
const [rows] = await pool.query(sql);
~~~

Nếu người dùng gửi một giá trị chứa dấu nháy đơn, biểu thức OR 1=1 và ký hiệu comment SQL, chuỗi được ghép có thể trở thành:

~~~sql
SELECT id, email
FROM users
WHERE email = '' OR 1=1 -- ';
~~~

Điều kiện OR 1=1 làm truy vấn trả về nhiều bản ghi hơn dự kiến. Tùy vị trí ghép chuỗi và quyền của tài khoản kết nối, kẻ tấn công có thể đọc dữ liệu ngoài phạm vi, sửa hoặc xóa dữ liệu, hay tác động đến các câu lệnh khác.

Các dạng tấn công thường gặp gồm:

- **In-band injection:** kết quả hoặc lỗi SQL được trả trực tiếp về ứng dụng.
- **UNION-based injection:** cố gắng ghép kết quả từ một truy vấn khác vào kết quả hiện tại.
- **Blind injection:** suy luận dữ liệu thông qua khác biệt về phản hồi, trạng thái hoặc thời gian.
- **Second-order injection:** dữ liệu độc hại được lưu trước, sau đó gây lỗi khi một luồng xử lý khác ghép dữ liệu đó vào SQL.

Không nên xem dữ liệu đã lưu trong cơ sở dữ liệu là dữ liệu đáng tin cậy. Nó có thể bắt nguồn từ một yêu cầu bên ngoài hoặc một hệ thống khác.

## 2. Dùng prepared statement cho mọi giá trị dữ liệu

Prepared statement giữ phần cấu trúc SQL cố định và truyền giá trị qua tham số riêng. MySQL xử lý giá trị như dữ liệu, vì vậy dấu nháy, dấu chấm phẩy hoặc chuỗi giống cú pháp SQL trong tham số không thể biến thành toán tử hay mệnh đề mới.

Với thư viện **mysql2** cho Node.js, dùng **execute()** để thực thi prepared statement:

~~~js
const email = req.query.email;

const sql =
  "SELECT id, email FROM users WHERE email = ?";

const [rows] = await pool.execute(sql, [email]);
~~~

Dấu **?** là vị trí của một **giá trị**. Thứ tự phần tử trong mảng phải khớp thứ tự placeholder trong câu SQL. Nếu đầu vào chứa dấu nháy đơn, biểu thức OR 1=1 và ký hiệu comment SQL, MySQL tìm một email có đúng giá trị đó thay vì diễn giải nó thành một điều kiện mới.

Một truy vấn có nhiều tham số:

~~~js
const sql =
  "SELECT id, status, created_at " +
  "FROM orders " +
  "WHERE customer_id = ? " +
  "AND status = ? " +
  "AND created_at >= ? " +
  "ORDER BY created_at DESC " +
  "LIMIT ? OFFSET ?";

const [orders] = await pool.execute(sql, [
  customerId,
  status,
  fromDate,
  limit,
  offset
]);
~~~

Trong ví dụ này, các tham số đều là giá trị. Ứng dụng vẫn cần kiểm tra kiểu và miền hợp lệ: customerId phải là mã khách hàng hợp lệ, status phải thuộc tập trạng thái được hỗ trợ, còn limit và offset phải là số nguyên trong giới hạn cho phép.

### Những giới hạn cần nhớ

Placeholder không đại diện cho một đoạn SQL tùy ý. Các cách viết sau không có tác dụng thay thế tên cột hoặc tên bảng:

~~~sql
-- Không chọn được cột bằng cách truyền giá trị vào placeholder
SELECT id, email FROM users ORDER BY ?;

-- Không chọn được bảng bằng placeholder
SELECT id FROM ? WHERE id = ?;
~~~

Trong câu đầu, MySQL sắp xếp theo giá trị tham số hằng, chứ không coi tham số là tên cột. Trong câu thứ hai, placeholder không thể trở thành tên bảng. Tương tự, không thể bind trực tiếp từ khóa ASC, DESC, toán tử hoặc một phần mệnh đề SQL.

Cũng không đặt dấu nháy quanh placeholder:

~~~sql
-- Sai: dấu ? nằm trong chuỗi literal
SELECT id FROM users WHERE email = '?';

-- Đúng
SELECT id FROM users WHERE email = ?;
~~~

Không tự viết hàm escape rồi ghép chuỗi thay cho prepared statement. Escape thủ công rất dễ sai khi xử lý bộ ký tự, kiểu dữ liệu hoặc ngữ cảnh SQL khác nhau.

## 3. Kiểm soát tên cột, tên bảng và chiều sắp xếp động

Một màn hình danh sách thường cho phép người dùng chọn cột sắp xếp hoặc thứ tự tăng/giảm. Đây là trường hợp cần tạo một phần câu SQL động. Vì placeholder không dùng được cho định danh, ứng dụng phải ánh xạ lựa chọn bên ngoài sang các hằng số SQL đã được lập trình viên kiểm soát.

Ví dụ an toàn với mysql2:

~~~js
const sortColumns = Object.freeze({
  createdAt: "created_at",
  total: "total_amount",
  status: "status"
});

const sortKey = req.query.sortBy;
if (!Object.hasOwn(sortColumns, sortKey)) {
  throw new Error("Cột sắp xếp không được hỗ trợ");
}
const sortColumn = sortColumns[sortKey];

const sortDirections = Object.freeze({
  asc: "ASC",
  desc: "DESC"
});

const directionKey = req.query.direction;
if (!Object.hasOwn(sortDirections, directionKey)) {
  throw new Error("Chiều sắp xếp không hợp lệ");
}
const sortDirection = sortDirections[directionKey];

const limit = Number(req.query.limit);
const offset = Number(req.query.offset);

if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
  throw new Error("limit phải nằm trong khoảng 1 đến 100");
}
if (!Number.isSafeInteger(offset) || offset < 0) {
  throw new Error("offset phải là số nguyên không âm");
}

const sql =
  "SELECT id, status, total_amount, created_at " +
  "FROM orders ORDER BY " + sortColumn + " " + sortDirection +
  " LIMIT ? OFFSET ?";

const [rows] = await pool.execute(sql, [limit, offset]);
~~~

Có hai luồng xử lý riêng:

1. sortBy và direction chỉ được ánh xạ tới những chuỗi hằng có sẵn trong mã nguồn. Giá trị lạ bị từ chối.
2. limit và offset là giá trị dữ liệu nên vẫn được bind bằng placeholder, đồng thời được kiểm tra miền hợp lệ.

Các tên cột trong bản đồ là hằng số do ứng dụng định nghĩa. Nếu tên định danh cần được quote, hãy đặt cú pháp quote cố định trong chính các giá trị của bản đồ. Việc quote không thay thế allow-list: chỉ các tên đã định nghĩa mới được phép đi vào câu SQL.

Áp dụng cùng nguyên tắc cho tên bảng. Ví dụ, nếu một API nhận loại tài nguyên là orders hoặc invoices, hãy ánh xạ hai lựa chọn đó sang hai tên bảng cố định. Không nối trực tiếp req.params.table, req.query.table hoặc bất kỳ chuỗi nào do người dùng cung cấp vào câu truy vấn.

**Quy tắc quyết định:** nếu một phần đầu vào quyết định *cấu trúc SQL*, hãy ánh xạ nó qua allow-list. Nếu nó là *giá trị được so sánh, chèn hoặc cập nhật*, hãy truyền nó qua placeholder.

## 4. SQL động trong stored procedure của MySQL

Stored procedure đôi khi cần chọn bảng theo một loại nghiệp vụ. MySQL không cho bind tên bảng vào placeholder của prepared statement. Có thể tạo câu SQL động bằng cách chọn tên bảng từ allow-list, sau đó bind các giá trị lọc như bình thường.

Ví dụ minh họa:

~~~sql
DELIMITER //

CREATE PROCEDURE read_entity(
  IN p_kind VARCHAR(20),
  IN p_owner_id BIGINT
)
BEGIN
  DECLARE v_table VARCHAR(64);

  SET v_table = CASE p_kind
    WHEN 'orders' THEN 'orders'
    WHEN 'invoices' THEN 'invoices'
    ELSE NULL
  END;

  IF v_table IS NULL THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Unsupported entity';
  END IF;

  SET @sql = CONCAT(
    'SELECT id, status FROM ',
    v_table,
    ' WHERE owner_id = ?'
  );
  SET @bound_owner_id = p_owner_id;

  PREPARE entity_stmt FROM @sql;
  EXECUTE entity_stmt USING @bound_owner_id;
  DEALLOCATE PREPARE entity_stmt;
END//

DELIMITER ;
~~~

Ở đây, p_kind chỉ được dùng để chọn một trong hai tên bảng cố định. Giá trị không hợp lệ bị từ chối. p_owner_id được truyền qua placeholder nên không thể thay đổi cấu trúc câu lệnh.

Trong MySQL, câu lệnh PREPARE nhận câu SQL từ chuỗi hoặc user variable; EXECUTE ... USING nhận các user variable làm tham số. Prepared statement có phạm vi phiên kết nối, vì vậy cần giải phóng bằng DEALLOCATE PREPARE sau khi thực thi. Khi triển khai thực tế, cũng cần đặt tên statement và user variable phù hợp với quy ước của ứng dụng để tránh xung đột trong cùng phiên.

Không đưa tên bảng nhận trực tiếp từ tham số vào CONCAT(). Nếu nghiệp vụ cần thêm bảng mới, hãy cập nhật rõ ràng allow-list và kiểm tra quyền của tài khoản cơ sở dữ liệu.

## 5. Những tình huống truy vấn thường gặp

### Lọc theo danh sách với IN

Không thể truyền cả mảng như một placeholder duy nhất cho mệnh đề IN. Hãy tạo đúng số placeholder theo số phần tử, còn từng giá trị vẫn được bind:

~~~js
const ids = input.ids;

if (!Array.isArray(ids) || ids.length > 100) {
  throw new Error("Danh sách mã không hợp lệ");
}

if (ids.length === 0) {
  return [];
}

if (!ids.every((id) => Number.isSafeInteger(id) && id > 0)) {
  throw new Error("Danh sách chứa mã không hợp lệ");
}

const placeholders = ids.map(() => "?").join(", ");
const sql = "SELECT id, status FROM orders WHERE id IN (" +
  placeholders + ")";

const [rows] = await pool.execute(sql, ids);
~~~

Chỉ số lượng placeholder được tạo động; dữ liệu của từng mã vẫn được bind. Cần giới hạn kích thước mảng để tránh truy vấn quá lớn và xác định rõ hành vi khi danh sách rỗng.

### Tìm kiếm với LIKE

Prepared statement vẫn ngăn injection khi dùng LIKE:

~~~js
const sql = "SELECT id, name FROM products WHERE name LIKE ?";
const [rows] = await pool.execute(sql, ["%" + keyword + "%"]);
~~~

Ký tự % và _ có ý nghĩa wildcard trong LIKE. Nếu yêu cầu nghiệp vụ là tìm chuỗi khớp nguyên văn, ứng dụng cần escape các wildcard theo quy tắc của MySQL và khai báo mệnh đề ESCAPE tương ứng. Đây là vấn đề về ngữ nghĩa tìm kiếm; nó khác với SQL injection.

### Cập nhật dữ liệu

Bind cả giá trị mới và khóa bản ghi:

~~~js
const sql =
  "UPDATE orders SET status = ? " +
  "WHERE id = ? AND customer_id = ?";

const [result] = await pool.execute(sql, [
  newStatus,
  orderId,
  customerId
]);
~~~

Ngoài kiểm tra đầu vào, điều kiện customer_id giúp giới hạn bản ghi theo chủ sở hữu trong truy vấn. Không dựa riêng vào việc giao diện đã ẩn các bản ghi của người khác.

## 6. Lỗi triển khai cần tránh

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Nối input vào chuỗi SQL | Input có thể thay đổi cú pháp | Bind giá trị bằng prepared statement |
| Dùng ORDER BY ? để chọn cột | Placeholder là giá trị, không phải định danh | Ánh xạ tên cột qua allow-list |
| Nối trực tiếp tên bảng từ request | Người dùng kiểm soát cấu trúc truy vấn | Dùng bản đồ tên bảng cố định |
| Tự escape rồi nối chuỗi | Dễ sai theo charset và ngữ cảnh | Dùng placeholder cho giá trị |
| Chỉ tắt multi-statements | Không chặn các kiểu injection trong một câu lệnh | Sửa cách tạo truy vấn |
| Trả nguyên lỗi MySQL cho client | Có thể lộ tên bảng, cột và cấu trúc nội bộ | Trả lỗi chung; ghi chi tiết ở log nội bộ có kiểm soát |

Tắt multipleStatements trong cấu hình driver là một lớp giảm thiểu hữu ích nếu ứng dụng không cần chạy nhiều câu lệnh trong một lần gọi. Tuy nhiên, nó không thay thế prepared statement và allow-list.

## 7. Phòng vệ theo nhiều lớp

Prepared statement là biện pháp chính để tách dữ liệu khỏi cú pháp SQL. Hãy kết hợp với các nguyên tắc sau:

- **Kiểm tra đầu vào theo nghiệp vụ:** xác thực kiểu, độ dài, miền giá trị và định dạng trước khi truy vấn. Validation giúp dữ liệu hợp lệ với nghiệp vụ; parameterization mới là cơ chế ngăn giá trị trở thành cú pháp SQL.
- **Phân quyền tối thiểu:** tài khoản ứng dụng chỉ nên có quyền cần thiết trên schema và bảng mà chức năng sử dụng. Không dùng tài khoản quản trị như root cho kết nối ứng dụng.
- **Giới hạn phạm vi dữ liệu:** đưa điều kiện tenant, chủ sở hữu hoặc phạm vi truy cập vào chính câu truy vấn và kiểm tra quyền ở tầng nghiệp vụ.
- **Quản lý lỗi và log:** không trả SQL, stack trace hoặc thông tin kết nối cho người dùng. Log cần đủ để điều tra nhưng phải bảo vệ dữ liệu nhạy cảm và thông tin xác thực.
- **Rà soát mọi điểm tạo SQL:** kiểm tra cả truy vấn đọc, ghi, báo cáo, tìm kiếm, export, stored procedure và tác vụ nền. SQL động có thể nằm ngoài luồng HTTP chính.

Không nên giả định ORM tự động bảo vệ mọi truy vấn. Các hàm raw query, biểu thức SQL tự tạo và phần sắp xếp động vẫn cần tuân thủ cùng quy tắc.

## 8. Cách kiểm tra truy vấn an toàn

Có thể kiểm tra theo các tình huống sau trong môi trường thử nghiệm:

1. Gửi giá trị chứa dấu nháy, dấu gạch ngang, dấu chấm phẩy và chuỗi giống điều kiện SQL vào các trường tìm kiếm. Ứng dụng phải xử lý chúng như dữ liệu; số lượng và phạm vi bản ghi không được thay đổi ngoài logic tìm kiếm.
2. Gửi sortBy là tên cột hợp lệ, tên cột không tồn tại và chuỗi có ký tự SQL. Chỉ lựa chọn có trong allow-list được chấp nhận.
3. Gửi direction với asc, desc và các giá trị tùy ý. Chỉ hai lựa chọn được hỗ trợ mới được ánh xạ thành từ khóa SQL.
4. Kiểm tra limit, offset với số âm, số thập phân, chuỗi, giá trị quá lớn và giá trị rỗng.
5. Kiểm tra danh sách IN rỗng, có một phần tử, nhiều phần tử và vượt giới hạn kích thước.
6. Xác minh tài khoản ứng dụng không thể đọc hoặc sửa các bảng nằm ngoài quyền được cấp.

Khi rà soát mã nguồn, tìm các điểm nối chuỗi vào SELECT, INSERT, UPDATE, DELETE, ORDER BY, GROUP BY và các câu SQL động. Với mỗi điểm, xác định rõ phần nào là hằng số, phần nào là định danh đã allow-list và phần nào là giá trị phải bind.

## 9. Ghi nhớ

| Thành phần truy vấn | Cách xử lý |
|---|---|
| Email, mã khách hàng, ngày tháng, trạng thái | Prepared statement / placeholder |
| Giá trị trong LIMIT, OFFSET | Placeholder và kiểm tra miền hợp lệ |
| Danh sách cho IN | Tạo số placeholder theo kích thước danh sách, bind từng giá trị |
| Tên bảng, tên cột | Allow-list ánh xạ sang hằng số SQL |
| ASC, DESC, toán tử, từ khóa | Chọn từ tập lựa chọn cố định |
| Chuỗi tìm kiếm LIKE | Bind giá trị; xử lý wildcard theo yêu cầu nghiệp vụ |

Khi thiết kế một truy vấn MySQL, hãy phân loại từng đầu vào trước khi ghép câu SQL: dữ liệu được bind, còn mọi lựa chọn ảnh hưởng cấu trúc truy vấn phải được kiểm soát bằng danh sách cho phép. Cách phân chia này giúp ngăn SQL injection ngay tại nơi câu lệnh được tạo ra và làm cho hành vi truy vấn dễ kiểm tra hơn.


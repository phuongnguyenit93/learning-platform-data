# SQL injection và nguyên nhân từ ghép chuỗi dữ liệu

Trong một ứng dụng dùng cơ sở dữ liệu, một đầu vào tưởng như vô hại có thể làm thay đổi **ý nghĩa của câu SQL** nếu chương trình đặt trực tiếp nó vào chuỗi lệnh. Lỗi này gọi là **SQL injection** (*chèn lệnh SQL*).

Ví dụ, một màn hình tìm kiếm cho phép người dùng nhập trạng thái đơn hàng. Lập trình viên viết:

```java
// KHÔNG AN TOÀN: userStatus đến từ request của người dùng.
String sql =
    "SELECT order_id, tenant_id, status "
  + "FROM orders "
  + "WHERE tenant_id = 10 AND status = '"
  + userStatus
  + "'";

Statement stmt = connection.createStatement();
ResultSet rs = stmt.executeQuery(sql);
```

Nếu `userStatus` là `DRAFT`, câu SQL có vẻ bình thường. Nhưng **giá trị do người dùng cung cấp không còn là một giá trị riêng biệt**: nó đã được chèn vào **văn bản chương trình SQL**. Người nhập có thể đưa vào dấu nháy, toán tử hoặc cú pháp nhận xét để khiến điều kiện lọc mang ý nghĩa khác.

Cách viết đúng về nguyên tắc:

```java
String sql = """
    SELECT order_id, tenant_id, status
    FROM orders
    WHERE tenant_id = ? AND status = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, authorizedTenantId);
    ps.setString(2, userStatus);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc kết quả phù hợp.
        }
    }
}
```

Ở cách thứ hai, cấu trúc SQL được xác định **trước khi** nhận giá trị; `userStatus` được truyền như **dữ liệu**, không thể tự biến thành toán tử hay mệnh đề SQL.

Bài học này thuộc chương **Quyền và SQL an toàn** của module **Database SQL**. Ta sẽ hiểu nguyên nhân sâu xa của SQL injection, cách phân biệt mã SQL với dữ liệu đầu vào, các vị trí dễ mắc lỗi, cách sử dụng bind parameters/PreparedStatement, các giới hạn của escaping và validation, cách xử lý những thành phần SQL không thể bind, và những biện pháp phòng vệ nhiều lớp trên PostgreSQL, MySQL, MariaDB, SQL Server, Oracle và SQLite.

> Các ví dụ có đầu vào gây sai lệch SQL chỉ dùng để **giải thích và kiểm thử an toàn trong môi trường tự tạo**. Không đưa chúng vào ứng dụng, cơ sở dữ liệu hay tài khoản của người khác khi không có quyền thử nghiệm. Bài học tập trung vào cách **phòng tránh, nhận diện và khắc phục** lỗi.

## 1. SQL injection là gì?

**SQL injection** xảy ra khi ứng dụng xây dựng hoặc thực thi SQL theo cách cho phép dữ liệu không đáng tin cậy **ảnh hưởng tới cấu trúc/cú pháp** câu truy vấn ngoài ý định của lập trình viên.

Nguồn dữ liệu không đáng tin có thể là:

- Nội dung form đăng nhập, tìm kiếm hoặc lọc.
- Tham số URL và query string.
- JSON request body hoặc HTTP header.
- File CSV/Excel/XML được tải lên.
- Webhook hoặc thông điệp từ một hệ thống khác.
- Giá trị lấy ra từ cơ sở dữ liệu nhưng **trước đó do người dùng ghi vào**.
- Dữ liệu được đưa qua queue, cache, search index hoặc bộ nhớ ứng dụng.
- Cấu hình cho phép người dùng chọn trường sắp xếp, tên bảng, tên báo cáo hoặc điều kiện lọc.

Đặc điểm chung: ứng dụng **chưa thể tin** rằng nội dung đó sẽ chỉ mang ý nghĩa **giá trị dữ liệu**.

### 1.1. Công thức nhận diện nguy cơ

Một mẫu điển hình:

```text
Câu SQL = "phần SQL do lập trình viên viết"
        + dữ liệu chưa tin cậy
        + "phần SQL còn lại"
```

Nguy cơ xuất hiện khi phần dữ liệu chèn vào có thể được SQL parser hiểu là:

- Dấu kết thúc literal.
- Toán tử logic `AND`, `OR`.
- Mệnh đề `WHERE` hoặc một phần `ORDER BY`.
- Dấu comment trong phương ngữ phù hợp.
- Tên đối tượng, cột, hàm hoặc biểu thức SQL.
- Cấu trúc điều khiển một câu SQL khác.

**Không phải mọi phép nối chuỗi trong ứng dụng đều là SQL injection.** Nối hai đoạn SQL **hoàn toàn tĩnh và do code kiểm soát** không giống việc nối input không đáng tin. Ranh giới nguy hiểm là **đưa dữ liệu không đáng tin vào ngữ pháp SQL**.

### 1.2. Hậu quả có thể xảy ra

Tùy quyền của tài khoản DB, lỗi và chức năng bị ảnh hưởng, SQL injection có thể dẫn đến:

1. **Bỏ qua điều kiện lọc** — đọc cả dữ liệu ngoài phạm vi được dự định.
2. **Lộ dữ liệu nhạy cảm** — tên người dùng, địa chỉ, token, bản ghi tenant khác.
3. **Thay đổi dữ liệu** — nếu lệnh/vùng quyền cho phép ghi.
4. **Phá hỏng tính toàn vẹn** — trạng thái, số tiền, quan hệ bị sửa.
5. **Từ chối dịch vụ** — câu truy vấn rất tốn tài nguyên, khóa hoặc làm ứng dụng lỗi.
6. **Vượt ranh giới quyền ứng dụng** — ứng dụng chạy bằng DB account có đặc quyền quá rộng.
7. **Che giấu hoặc gây sai lệch báo cáo** — dữ liệu lọc không còn theo điều kiện nghiệp vụ.

Không nên khẳng định một lỗ hổng chắc chắn có thể xóa cả database hoặc chạy lệnh hệ điều hành: hậu quả cụ thể phụ thuộc **DBMS, driver, loại câu lệnh, tài khoản, cấu hình và đường thực thi**. Nhưng chỉ cần đọc nhầm dữ liệu tenant khác đã có thể là sự cố nghiêm trọng.

## 2. Nguyên nhân gốc: trộn mã SQL với giá trị dữ liệu

SQL parser hiểu **cấu trúc câu lệnh**, chứ không biết chuỗi nào được sinh từ form người dùng nếu ứng dụng đã ghép tất cả thành một SQL string.

Giả sử câu SQL cố định:

```sql
SELECT order_id, tenant_id, status
FROM orders
WHERE tenant_id = 10 AND status = 'DRAFT';
```

Parser thấy:

- `SELECT` là từ khóa.
- `tenant_id = 10` là predicate.
- `AND` là toán tử logic.
- `status = 'DRAFT'` là so sánh với **literal string**.

Trong Java không an toàn:

```java
String sql =
    "SELECT order_id FROM orders "
  + "WHERE tenant_id = 10 AND status = '"
  + userStatus
  + "'";
```

giá trị `userStatus` được ghép **vào giữa dấu nháy SQL**. Nếu nó chứa cú pháp thoát khỏi phần string literal, một phần đầu vào có thể được parser xem là **cấu trúc SQL**, không còn là dữ liệu.

### 2.1. Minh họa bằng một đầu vào trong môi trường tự tạo

Giả sử một input thử nghiệm là:

```text
' OR '1'='1' -- 
```

Nếu ứng dụng ghép nó vào câu SQL ở trên, có thể tạo chuỗi đại ý:

```sql
SELECT order_id
FROM orders
WHERE tenant_id = 10 AND status = ''
   OR '1' = '1' -- '
```

Ở một phương ngữ nhận dấu nhận xét này đúng cách, phần `OR '1'='1'` làm predicate rộng hơn dự định. Theo độ ưu tiên SQL, `AND` thường có độ ưu tiên cao hơn `OR` nên điều kiện có thể được hiểu là:

```text
(tenant_id = 10 AND status = '')
OR ('1' = '1')
```

Điều kiện thứ hai đúng, làm mất hiệu lực giới hạn tenant trong bài thử.

**Lưu ý:** cách xử lý dấu comment khác giữa DBMS; chẳng hạn cú pháp `--` trong MySQL yêu cầu ký tự khoảng trắng/điều khiển theo sau. Ví dụ này chỉ là minh họa vì sao **không được ghép dữ liệu vào câu SQL**, không phải một chuỗi bảo đảm hoạt động trên mọi ứng dụng hay DBMS.

### 2.2. Vấn đề không nằm ở từ khóa OR

Một người dùng có thể nhập `OR` như dữ liệu tìm kiếm hợp lệ. Lỗi không phải “người dùng gõ chữ OR”; lỗi là ứng dụng tạo đường cho ký tự người dùng **trở thành cú pháp SQL**.

Ví dụ nếu truy vấn đúng là:

```sql
SELECT order_id FROM orders WHERE status = ?;
```

và giá trị được bind là `' OR '1'='1' -- `, DBMS so sánh trạng thái với **một chuỗi nguyên vẹn** chứa dấu nháy, chữ `OR` và dấu comment. Nó không tạo điều kiện mới.

### 2.3. Dữ liệu phải giữ nguyên vai trò sau mọi phép biến đổi

Một lỗi tương tự có thể xảy ra sau khi input đã qua:

```text
HTTP request -> validation -> database -> queue -> export tool
             -> script SQL mới
```

Nếu một bước ở phía sau ghép giá trị đó vào lệnh SQL, vấn đề tái xuất hiện. **Dữ liệu được lưu trong DB không tự trở thành nguồn tin cậy về cú pháp SQL.**

## 3. Chuẩn bị dữ liệu mô phỏng an toàn

Dùng bảng tưởng tượng `orders`:

| order_id | tenant_id | status | total_amount |
|---:|---:|---|---:|
| 101 | 10 | DRAFT | 100.00 |
| 102 | 10 | PAID | 250.00 |
| 103 | 20 | DRAFT | 300.00 |
| 104 | 20 | PAID | 120.00 |

Truy vấn nghiệp vụ mong muốn: chỉ trả các đơn của **tenant đã xác thực** có trạng thái tương ứng.

```sql
-- Ý tưởng có thể chuyển sang các DBMS phù hợp.
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = ?
  AND status = ?;
```

Ở đây:

- `tenant_id` cần lấy từ context đã xác thực phía server, không mặc nhiên tin giá trị request.
- `status` là một giá trị được bind, có thể kiểm tra thêm là `DRAFT`/`PAID`.
- `?` là placeholder kiểu JDBC/ODBC; PostgreSQL native thường dùng `$1`, `$2` trong câu chuẩn bị trên server.

Nếu chỉ lọc đúng `status` nhưng **tenant_id do người dùng tự chọn không được kiểm tra**, ứng dụng vẫn có thể lộ dữ liệu tenant khác, ngay cả khi **không còn SQL injection**. Sửa injection là **một** lớp bảo mật, không phải toàn bộ authorization.

## 4. Biện pháp chính: câu lệnh có tham số (*parameterized query*)

**Nguyên tắc cốt lõi:** giữ **SQL code** và **SQL data** ở hai kênh logic khác nhau.

```text
Cách KHÔNG an toàn:
  SQL text = "WHERE email = '" + emailFromUser + "'"
                               |
                               v
                   dữ liệu bị ghép vào mã

Cách AN TOÀN về ranh giới cú pháp:
  SQL text = "WHERE email = ?"
  bind[1]  = emailFromUser
                 |
                 v
        DB/driver xử lý như một giá trị
```

Với cách tham số hóa:

- Ứng dụng cung cấp cấu trúc SQL riêng.
- Giá trị tham số được bind theo vị trí/tên và kiểu dữ liệu.
- Driver/DBMS bảo đảm dữ liệu không bị dùng như **cú pháp SQL** ở vị trí giá trị.
- Một chuỗi có dấu nháy, từ khóa hay dấu comment vẫn là **giá trị string**.

Đừng chỉ nhìn xem API có tên "prepare" không: phải đảm bảo **mọi giá trị không đáng tin đều được bind** ở vị trí phù hợp.

### 4.1. Parameterization không có nghĩa chỉ escaping dấu nháy

Hai cách sau khác nhau:

```java
// Không an toàn nếu userEmail chưa tin cậy.
String sql = "SELECT * FROM users WHERE email = '" + userEmail + "'";

// Đúng về mặt chống chèn cú pháp tại chỗ này.
String sql = "SELECT * FROM users WHERE email = ?";
PreparedStatement ps = connection.prepareStatement(sql);
ps.setString(1, userEmail);
```

Escaping là biến đổi chuỗi trước khi ghép vào SQL; parameterization là **thay đổi cách truyền dữ liệu** để giá trị không còn được phân tích như mã. Biện pháp thứ hai là lựa chọn mặc định.

### 4.2. Chưa chắc driver luôn gửi server-side PREPARE

Với JDBC, SQL driver có thể dùng server-side prepared statement hoặc có cơ chế xử lý tương đương phía driver tùy cấu hình. Về **an toàn**, điều quan trọng là API **bind dữ liệu đúng chuẩn**, không phải việc optimizer có tái sử dụng một execution plan hay không.

Không đánh đồng:

- *Prepared statement* để tách cú pháp khỏi dữ liệu.
- Caching/reusing query plan để tăng hiệu năng.
- Một hàm tự viết tên `prepareSql()` nhưng vẫn nối input vào SQL string.

Hàm tự đặt tên “safe”, “prepare” hoặc “sanitize” không thay bằng chứng về parameter binding.

## 5. Java JDBC: Statement và PreparedStatement

JDBC cung cấp hai cách phổ biến:

| API | Cách dùng | Điều cần lưu ý |
|---|---|---|
| `Statement` | Chạy SQL text đã hoàn chỉnh | Rất dễ mắc lỗi nếu tự nối input |
| `PreparedStatement` | SQL có `?` và `setXxx` bind tham số | Lựa chọn mặc định cho dữ liệu đầu vào |
| `CallableStatement` | Gọi stored procedure/function theo driver | Vẫn phải bind tham số; routine bên trong vẫn có thể bị injection nếu nối dynamic SQL |

`Statement` **không tự trở thành lỗ hổng** nếu SQL hoàn toàn cố định. Nhưng nó không phải giao diện thích hợp để chèn giá trị tùy ý vào string SQL.

### 5.1. Ví dụ sai: ghép email từ request

```java
String email = request.getParameter("email");

String sql =
    "SELECT user_id, email FROM users WHERE email = '"
  + email
  + "'";

try (Statement st = connection.createStatement();
     ResultSet rs = st.executeQuery(sql)) {
    while (rs.next()) {
        // ...
    }
}
```

Mọi dấu nháy và ký tự điều khiển trong `email` trở thành một phần của SQL text, chưa được phân tách thành dữ liệu.

### 5.2. Ví dụ đúng: bind email

```java
String email = request.getParameter("email");

String sql = """
    SELECT user_id, email
    FROM users
    WHERE email = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("user_id");
            String dbEmail = rs.getString("email");
            // Chỉ sử dụng các hàng hợp lệ về quyền.
        }
    }
}
```

Với `ps.setString(1, email)`, dấu nháy trong email không thể đóng dấu nháy SQL do chương trình tạo. Không cần tự thêm `'` quanh `?`.

### 5.3. Ví dụ đúng: bind cả tenant và trạng thái

```java
long authorizedTenantId = authContext.tenantId();
String requestedStatus = request.getParameter("status");

String sql = """
    SELECT order_id, total_amount
    FROM orders
    WHERE tenant_id = ?
      AND status = ?
    ORDER BY order_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, authorizedTenantId);
    ps.setString(2, requestedStatus);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // ...
        }
    }
}
```

Ở đây, **tenant** là khóa được xác thực, còn `requestedStatus` là dữ liệu tìm kiếm. Có thể kiểm tra `requestedStatus` thuộc `DRAFT`/`PAID` để tránh input sai nghiệp vụ, nhưng điều đó bổ sung cho parameterization, **không thay thế** nó.

### 5.4. Vì sao không được tự đặt nháy quanh dấu ?

Sai:

```java
String sql = "SELECT * FROM users WHERE email = '?'";
PreparedStatement ps = connection.prepareStatement(sql);
ps.setString(1, email);
```

Trong nhiều DBMS/driver, dấu `?` nằm trong literal `'?'` nên không được nhận diện là placeholder. Số lượng tham số có thể bằng 0 và `setString(1, ...)` sẽ lỗi.

Đúng:

```java
String sql = "SELECT * FROM users WHERE email = ?";
PreparedStatement ps = connection.prepareStatement(sql);
ps.setString(1, email);
```

**Không chèn cả dấu nháy SQL** bằng `setString`. Driver biết cách biểu diễn giá trị string.

### 5.5. Bind kiểu dữ liệu đúng

```java
ps.setLong(1, authorizedTenantId);
ps.setString(2, requestedStatus);
ps.setBigDecimal(3, amount);
ps.setDate(4, java.sql.Date.valueOf("2026-11-14"));
```

Kiểu tham số giúp DBMS hiểu giá trị dữ liệu theo schema. Với timestamp có timezone, JSON, array và các kiểu đặc thù, driver có API/tùy chọn riêng cần dùng đúng.

**Không** dùng `setString` cho mọi thứ rồi tự ghép `CAST('...')`. Hãy bind kiểu dữ liệu phù hợp hoặc dùng SQL cast cố định:

```sql
-- PostgreSQL: cast placeholder, không nối giá trị vào cú pháp.
WHERE payload @> CAST(? AS jsonb)
```

### 5.6. Bind SQL NULL

Nếu giá trị email được phép `NULL`, có thể dùng:

```java
ps.setNull(1, java.sql.Types.VARCHAR);
```

Nhưng:

```sql
WHERE email = NULL
```

không cho kết quả TRUE như so sánh bằng giá trị thông thường trong SQL. Với tham số NULL, cần **logic truy vấn riêng**, ví dụ:

```sql
WHERE email IS NULL
```

hoặc dựng hai mẫu SQL cố định cho hai tình huống. Đây là **vấn đề ngữ nghĩa SQL NULL**, không phải lỗi SQL injection.

## 6. Câu lệnh DML cũng phải tham số hóa

Nhiều người chỉ nghĩ SQL injection nằm ở màn hình login, nhưng `UPDATE`/`DELETE`/`INSERT` cũng có thể bị ảnh hưởng nếu ghép input.

### 6.1. UPDATE không an toàn

```java
// KHÔNG AN TOÀN.
String sql =
    "UPDATE orders SET status = '" + status
  + "' WHERE order_id = " + orderId;
```

Ở đây cả `status` và `orderId` đều không đáng tin nếu đến từ request. Chỉ cần một vùng có thể thay đổi cú pháp là đã nguy hiểm.

### 6.2. UPDATE an toàn với bind parameters và phạm vi tenant

```java
String sql = """
    UPDATE orders
    SET status = ?
    WHERE order_id = ?
      AND tenant_id = ?
      AND status = 'DRAFT'
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, newStatus);
    ps.setLong(2, orderId);
    ps.setLong(3, authorizedTenantId);

    int updated = ps.executeUpdate();

    if (updated != 1) {
        // Không tồn tại, không thuộc tenant, trạng thái không hợp lệ
        // hoặc có cạnh tranh ghi: xử lý theo nghiệp vụ.
    }
}
```

Đây là cách an toàn về **cú pháp SQL injection** cho ba giá trị. Nhưng cần bổ sung validation chuyển trạng thái: chỉ cho chuyển DRAFT → PAID khi điều kiện thanh toán được đáp ứng. `PreparedStatement` không tự quyết định ai có quyền thanh toán đơn nào.

### 6.3. DELETE cần điều kiện bảo vệ rõ

```java
String sql = """
    DELETE FROM saved_filters
    WHERE filter_id = ?
      AND owner_user_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, filterId);
    ps.setLong(2, authorizedUserId);
    int deleted = ps.executeUpdate();
}
```

Nếu chỉ có `WHERE filter_id = ?` nhưng user được phép đoán ID của người khác, ứng dụng vẫn có lỗi **Broken Object Level Authorization**, dù không có SQL injection.

### 6.4. INSERT cũng không ghép input

```java
String sql = """
    INSERT INTO customer_notes (customer_id, tenant_id, note_text)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setLong(2, authorizedTenantId);
    ps.setString(3, userNote);
    ps.executeUpdate();
}
```

Đầu vào `userNote` có thể chứa dấu nháy, dấu chấm phẩy, nội dung code hoặc xuống dòng; nó vẫn chỉ được lưu như **nội dung ghi chú**.

## 7. Parameterized query xử lý tốt giá trị nhưng không thay tên bảng hoặc tên cột

Đây là giới hạn rất quan trọng: placeholder dùng ở những vị trí **biểu thức giá trị**, không dùng để thay thế mọi thành phần **cú pháp SQL**.

Ví dụ thường **không hợp lệ/không mang nghĩa mong muốn**:

```sql
SELECT * FROM ? WHERE id = ?;
```

`?` không có nhiệm vụ thay tên bảng.

Tương tự:

```sql
SELECT * FROM orders ORDER BY ?;
```

nếu được DBMS chấp nhận, `?` có thể là một **hằng giá trị** thay vì tên cột động; câu SQL không tự biến `?` thành `created_at` chỉ vì bind chuỗi `"created_at"`.

### 7.1. Đúng: dùng danh sách cho phép cho tên cột

Giả sử UI chỉ cho chọn một trong ba trường sắp xếp:

- Ngày tạo.
- Tổng tiền.
- ID đơn hàng.

Ta tạo mapping **cố định trong code**:

```java
Map<String, String> columns = Map.of(
    "created", "created_at",
    "amount", "total_amount",
    "id", "order_id"
);

String requestedSort = request.getParameter("sort");
String orderColumn = columns.get(requestedSort);

if (orderColumn == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}
```

Vì `orderColumn` chỉ có thể là một trong **ba chuỗi do lập trình viên viết**, nó có thể được đưa vào phần `ORDER BY` an toàn về cấu trúc.

### 7.2. Đúng: hướng sắp xếp từ enum/boolean đã kiểm tra

```java
String requestedDirection = request.getParameter("direction");

String orderDirection;
if ("asc".equalsIgnoreCase(requestedDirection)) {
    orderDirection = "ASC";
} else if ("desc".equalsIgnoreCase(requestedDirection)) {
    orderDirection = "DESC";
} else {
    throw new IllegalArgumentException("Unsupported direction");
}

String sql =
    "SELECT order_id, total_amount, created_at "
  + "FROM orders "
  + "WHERE tenant_id = ? "
  + "ORDER BY " + orderColumn + " " + orderDirection
  + ", order_id ASC "
  + "LIMIT ? OFFSET ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, authorizedTenantId);
    ps.setInt(2, pageSize);
    ps.setInt(3, offset);

    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
}
```

**Phương ngữ:** ví dụ `LIMIT ? OFFSET ?` phù hợp với PostgreSQL/MySQL và một số DBMS khác; SQL Server/Oracle có cú pháp phân trang khác. Nguyên tắc không đổi: **identifier và keyword lấy từ allowlist**, còn giá trị tenant/limit/offset được bind.

### 7.3. Vì sao không dùng danh sách từ client trực tiếp?

Sai:

```java
String sql = "SELECT * FROM orders ORDER BY "
           + request.getParameter("sort");
```

Câu `ORDER BY` là phần **cú pháp**. Nếu người dùng gửi một biểu thức bất ngờ, ứng dụng cho phép họ kiểm soát SQL text ngoài mục tiêu “chọn một trường sắp xếp”.

Một allowlist đúng phải là mapping **đầu vào nghiệp vụ → SQL fragment cố định**, không phải kiểm tra “chuỗi chỉ có chữ và dấu gạch dưới” rồi cho phép tên bất kỳ.

### 7.4. Tên bảng động: phải kiểm tra cả authorization

Ví dụ một báo cáo chọn bảng từ một danh sách tên đã định nghĩa:

```java
Map<String, String> reportSources = Map.of(
    "monthlyOrders", "reporting.monthly_orders",
    "dailyRevenue", "reporting.daily_revenue"
);

String source = reportSources.get(reportType);
if (source == null) {
    throw new IllegalArgumentException("Unsupported report type");
}
```

Ngay cả khi `source` nằm trong allowlist và không thể phá cú pháp, **role người gọi vẫn cần được phép đọc báo cáo đó**. Allowlist ngăn các tên bảng không dự định; authorization quyết định user nào được chọn từng báo cáo.

### 7.5. Quote identifier không phải authorization

Các DBMS có cơ chế quote identifier:

- PostgreSQL: `quote_ident` hoặc `format('%I', identifier)` cho SQL động trong PL/pgSQL.
- SQL Server: `QUOTENAME`.
- MySQL/MariaDB: tên định danh thường dùng backtick theo SQL mode.
- SQLite: dấu nháy kép cho identifier theo cú pháp được hỗ trợ.

Quote giúp tránh nhập nhằng cú pháp. Nhưng nếu user được chọn một **tên bảng nhạy cảm có thật**, quote đúng vẫn cho phép truy vấn bảng đó nếu execution context có quyền.

**Quoting ≠ allowlist ≠ authorization.** Cả ba giải quyết những câu hỏi khác nhau.

## 8. LIKE và wildcard: tránh injection nhưng vẫn có thể tìm quá rộng

Giả sử chức năng tìm ghi chú:

```sql
SELECT note_id, note_text
FROM notes
WHERE note_text LIKE ?;
```

Bind trực tiếp:

```java
ps.setString(1, "%" + userKeyword + "%");
```

là **an toàn về SQL injection**, vì chuỗi được truyền như tham số. Nhưng nếu người dùng nhập ký tự `%` hoặc `_`, chúng có ý nghĩa **wildcard trong LIKE**:

- `%` khớp với chuỗi có độ dài bất kỳ.
- `_` khớp với một ký tự.

Điều này có thể khiến kết quả tìm quá rộng. Đây thường là **vấn đề ngữ nghĩa pattern**, không phải SQL injection.

### 8.1. Muốn tìm chính xác ký tự %, _, cần escape ở mức LIKE

Một cách cho các hệ hỗ trợ `ESCAPE '!'`:

```sql
SELECT note_id, note_text
FROM notes
WHERE note_text LIKE ? ESCAPE '!';
```

Java:

```java
String escaped = userKeyword
    .replace("!", "!!")
    .replace("%", "!%")
    .replace("_", "!_");

String pattern = "%" + escaped + "%";

try (PreparedStatement ps = connection.prepareStatement(
        "SELECT note_id FROM notes WHERE note_text LIKE ? ESCAPE '!'")) {
    ps.setString(1, pattern);
    // executeQuery() ...
}
```

Ở đây:

1. **Parameter binding** ngăn chèn cú pháp SQL.
2. **LIKE escaping** đảm bảo ký tự người dùng nhập được hiểu là nội dung, không phải wildcard, nếu đó là yêu cầu nghiệp vụ.
3. `ESCAPE '!'` là phần SQL cố định do lập trình viên chọn.

Nếu sản phẩm **chủ đích** cho wildcard trong tìm kiếm nâng cao, có thể cho dùng wildcard theo cú pháp được kiểm soát. Nhưng đừng để người dùng điều khiển **toàn bộ SQL** vì muốn hỗ trợ một vài quy tắc tìm kiếm.

### 8.2. LIKE injection khác SQL injection

Một yêu cầu tìm tất cả bản ghi vì người dùng nhập `%` có thể không mong muốn nhưng **không phải SQL injection** nếu chương trình bind tham số đúng. Cần phân loại lỗi rõ để sửa đúng lớp.

## 9. IN với danh sách động: bind từng giá trị

Giao diện có thể cho người dùng lọc nhiều trạng thái:

```sql
WHERE status IN ('DRAFT', 'PAID', 'CANCELLED')
```

Không làm:

```java
// KHÔNG AN TOÀN nếu idsCsv lấy từ request.
String sql = "SELECT * FROM orders WHERE order_id IN (" + idsCsv + ")";
```

`idsCsv` trở thành SQL text. Những giá trị được nối vào ngoặc không có ranh giới dữ liệu rõ ràng.

### 9.1. Tạo số placeholder dựa trên số phần tử

```java
List<Long> orderIds = validatedOrderIds;

if (orderIds.isEmpty()) {
    return List.of();
}
if (orderIds.size() > 100) {
    throw new IllegalArgumentException("Too many IDs");
}

String placeholders = String.join(
    ", ",
    Collections.nCopies(orderIds.size(), "?")
);

String sql =
    "SELECT order_id, tenant_id, status "
  + "FROM orders "
  + "WHERE tenant_id = ? "
  + "AND order_id IN (" + placeholders + ")";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, authorizedTenantId);

    for (int i = 0; i < orderIds.size(); i++) {
        ps.setLong(i + 2, orderIds.get(i));
    }

    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
}
```

Lưu ý:

- Dấu `?` được sinh từ code dựa trên **số lượng**, không đưa nội dung ID vào SQL text.
- Các ID được parse thành `Long` và bind từng giá trị.
- Trường hợp danh sách rỗng được xử lý riêng.
- Giới hạn số phần tử để tránh tạo câu SQL khổng lồ.
- Điều kiện tenant vẫn bắt buộc nếu đây là dữ liệu đa tenant.

### 9.2. Một dấu ? không đại diện cả danh sách

Trong SQL thông thường:

```sql
WHERE order_id IN (?)
```

không tự hiểu tham số chuỗi `"101,102,103"` là ba giá trị. Nó có thể là **một string duy nhất** được so sánh/cast. Để truyền danh sách, cần placeholder tương ứng, array/table-valued parameter hoặc cơ chế riêng của framework/DBMS.

### 9.3. PostgreSQL ANY với array đã bind

PostgreSQL có thể dùng:

```sql
WHERE order_id = ANY (?::bigint[])
```

Với JDBC PostgreSQL driver, có thể dùng `Connection.createArrayOf` theo kiểu phù hợp, rồi `setArray`. Cách này giúp tránh dựng hàng trăm placeholder nhưng phụ thuộc khả năng driver, kiểu array và quản lý tài nguyên.

Trong SQL Server có table-valued parameters; những DBMS khác có giải pháp riêng. **Không giả định một cách truyền collection hoạt động y hệt trên mọi driver.**

## 10. Phân trang: LIMIT, OFFSET, TOP và FETCH không được nối input thô

Sai:

```java
String sql = "SELECT * FROM orders LIMIT " + request.getParameter("size");
```

Không phải mọi giá trị client gửi là integer hợp lệ. Việc chuyển qua `Integer.parseInt` có thể ngăn input chứa cú pháp SQL tại vị trí đó, nhưng vẫn cần **giới hạn kích thước** và bind/tham số hóa khi phù hợp.

Đúng về ý tưởng:

```java
int pageSize = Math.min(Math.max(requestedSize, 1), 100);
int page = Math.max(requestedPage, 0);

// Tránh overflow khi nhân:
long offsetLong = (long) page * pageSize;
if (offsetLong > Integer.MAX_VALUE) {
    throw new IllegalArgumentException("Page too deep");
}
int offset = (int) offsetLong;

String sql = """
    SELECT order_id, created_at, total_amount
    FROM orders
    WHERE tenant_id = ?
    ORDER BY created_at DESC, order_id DESC
    LIMIT ? OFFSET ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, authorizedTenantId);
    ps.setInt(2, pageSize);
    ps.setInt(3, offset);
}
```

Chú ý: phương ngữ SQL Server thường dùng `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` cùng `ORDER BY`; Oracle phiên bản hiện đại cũng có `OFFSET/FETCH`. **Trật tự kết quả ổn định** cần `ORDER BY` và một cột tie-breaker; tham số hóa không tự sửa lỗi phân trang khi không có thứ tự xác định.

Với bảng rất lớn, keyset pagination có thể hiệu quả hơn OFFSET sâu. Đó là vấn đề hiệu năng, độc lập với SQL injection.

## 11. Đăng nhập: không dùng chuỗi mật khẩu để ghép vào WHERE

Một ví dụ rất dễ sai:

```java
// SAI cả về bảo mật SQL và thiết kế mật khẩu.
String sql =
    "SELECT user_id FROM users WHERE username = '"
  + username
  + "' AND password = '"
  + password
  + "'";
```

Vấn đề:

1. `username`/`password` được ghép vào SQL.
2. Có dấu hiệu hệ thống giữ hoặc so sánh mật khẩu như **giá trị thô** trong DB.
3. Không có bảo đảm chống đoán mật khẩu, giới hạn thử đăng nhập hoặc xác thực đa yếu tố.

Một hướng thiết kế thích hợp hơn:

```java
String sql = """
    SELECT user_id, password_hash, is_active
    FROM users
    WHERE username = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, username);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String storedHash = rs.getString("password_hash");
            boolean active = rs.getBoolean("is_active");

            // Gọi thư viện xác minh password hash phù hợp
            // (Argon2id, scrypt, bcrypt hoặc cơ chế được phê duyệt).
            // Không so sánh chuỗi password thô trong SQL.
        }
    }
}
```

Đây là **minh họa đường truy vấn**, chưa phải luồng đăng nhập hoàn chỉnh. Hệ thống thực tế cần chống user enumeration, timing leakage, rate limit, quản lý phiên, cấu hình hash, xử lý account bị khóa và audit.

**Sửa SQL injection không đủ để biến một luồng authentication kém an toàn thành an toàn.**

## 12. ORM không tự miễn nhiễm SQL injection

Các framework như JPA/Hibernate, Spring Data/JdbcTemplate hoặc MyBatis có cách bind tham số, nhưng ứng dụng vẫn có thể tạo lỗ hổng nếu **tự xây JPQL/HQL/SQL bằng chuỗi đầu vào**.

### 12.1. Spring JdbcTemplate: tham số hóa

```java
String sql = """
    SELECT order_id, status, total_amount
    FROM orders
    WHERE tenant_id = ? AND status = ?
    """;

List<OrderRow> rows = jdbcTemplate.query(
    sql,
    (rs, rowNum) -> new OrderRow(
        rs.getLong("order_id"),
        rs.getString("status"),
        rs.getBigDecimal("total_amount")
    ),
    authorizedTenantId,
    requestedStatus
);
```

`JdbcTemplate` sẽ bind các giá trị theo API phù hợp. Nhưng nếu `sql` trước đó đã được ghép với `requestedStatus`, dùng JdbcTemplate **không sửa được lỗ hổng**.

### 12.2. NamedParameterJdbcTemplate

```java
String sql = """
    SELECT order_id, status
    FROM orders
    WHERE tenant_id = :tenant
      AND status = :status
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("tenant", authorizedTenantId)
    .addValue("status", requestedStatus);

List<OrderRow> rows = namedParameterJdbcTemplate.query(
    sql, params, rowMapper
);
```

Named parameters giúp câu truy vấn dễ đọc khi có nhiều điều kiện, nhưng vẫn cần không đưa SQL identifiers tùy ý vào query string.

### 12.3. JPA/Hibernate: JPQL có bind parameters

```java
TypedQuery<OrderEntity> query = entityManager.createQuery(
    """
    SELECT o
    FROM OrderEntity o
    WHERE o.tenantId = :tenantId
      AND o.status = :status
    """,
    OrderEntity.class
);

query.setParameter("tenantId", authorizedTenantId);
query.setParameter("status", requestedStatus);

List<OrderEntity> orders = query.getResultList();
```

JPQL là ngôn ngữ truy vấn đối tượng, nhưng vẫn có cấu trúc biểu thức. Nếu ghép input vào JPQL/HQL, vẫn có thể xảy ra injection tương tự.

### 12.4. Ví dụ ORM sai

```java
// SAI: biến userStatus được đưa vào cấu trúc JPQL.
String jpql =
    "SELECT o FROM OrderEntity o WHERE o.status = '"
  + userStatus
  + "'";

entityManager.createQuery(jpql, OrderEntity.class).getResultList();
```

Không có chuyện ORM tự phát hiện từng chuỗi ghép là dữ liệu. Nó nhận **một truy vấn đã được tạo hoàn chỉnh**.

### 12.5. MyBatis: #{} và raw substitution

Trong MyBatis, cú pháp parameter binding điển hình:

```xml
<select id="findByStatus" resultType="OrderRow">
  SELECT order_id, status
  FROM orders
  WHERE tenant_id = #{tenantId}
    AND status = #{status}
</select>
```

`#{...}` được MyBatis xử lý như **tham số giá trị**; còn cú pháp raw text substitution kiểu `${...}` sẽ **đưa nội dung vào SQL string** và không phải phương án an toàn cho input tùy ý.

Chẳng hạn nếu ứng dụng dùng raw substitution cho `ORDER BY${sortColumn}`, phải chắc chắn `sortColumn` đến từ allowlist trong code, không phải request tùy ý.

### 12.6. Query builder và Criteria API

Query builder/Criteria API có thể giúp tạo câu SQL mà phần điều kiện là biểu thức có cấu trúc và giá trị được bind. Tuy nhiên:

- Không tự truyền raw SQL fragments từ client.
- Không cho client đặt tên cột/bảng tự do.
- Không vô hiệu hóa phân quyền/tenant filter.
- Kiểm tra cả native queries do framework phát sinh.

**Framework là công cụ**, không phải ranh giới tin cậy tự động.

## 13. Stored procedure không tự ngăn SQL injection

Một quan niệm sai: “Đã đưa SQL vào stored procedure thì không thể bị injection.”

Một procedure có SQL **tĩnh** và giá trị tham số an toàn có thể giảm nguy cơ. Nhưng nếu procedure nhận input rồi **nối input vào dynamic SQL**, lỗi vẫn xảy ra — lần này nằm trong database.

### 13.1. SQL Server: dynamic SQL không an toàn

```sql
-- SQL Server, ví dụ chống chỉ định.
DECLARE @sql nvarchar(max);

SET @sql = N'SELECT order_id FROM dbo.orders WHERE status = '''
         + @userStatus
         + N'''';

EXEC (@sql);
```

`@userStatus` vẫn trở thành một phần của SQL code. Sử dụng `EXEC(...)` không tự tách dữ liệu.

### 13.2. SQL Server: sp_executesql với tham số

```sql
-- SQL Server: query text cố định, giá trị được bind.
DECLARE @sql nvarchar(max) =
    N'SELECT order_id FROM dbo.orders
      WHERE tenant_id = @tenantId
        AND status = @status';

EXEC sys.sp_executesql
    @sql,
    N'@tenantId bigint, @status nvarchar(20)',
    @tenantId = @authorizedTenantId,
    @status = @userStatus;
```

`@userStatus` được truyền như giá trị, không ghép vào query string.

**Chú ý:** đây là ví dụ chạy bên trong ngữ cảnh đã có biến T-SQL tương ứng. Khi viết procedure thực tế, biến `@authorizedTenantId` phải được xác thực tại server/API, không mặc nhiên tin tham số tenant do client gửi.

### 13.3. PostgreSQL PL/pgSQL: USING trong EXECUTE

Với PostgreSQL, một pattern an toàn cho giá trị:

```sql
-- Bên trong PL/pgSQL function/procedure.
EXECUTE
    'SELECT count(*) FROM app_data.orders WHERE tenant_id = $1 AND status = $2'
INTO row_count
USING authorized_tenant_id, requested_status;
```

Các `$1`, `$2` trong dynamic query được cấp dữ liệu bằng `USING`. Nếu tên bảng thật sự động, dùng identifier quoting và danh sách cho phép:

```sql
EXECUTE format(
    'SELECT count(*) FROM %I.%I WHERE tenant_id = $1',
    trusted_schema,
    allowlisted_table
)
INTO row_count
USING authorized_tenant_id;
```

`%I` quote identifier về mặt cú pháp; **`allowlisted_table` vẫn phải nằm trong danh sách đối tượng được phép**, và role thực thi cần quyền tối thiểu.

### 13.4. MySQL/MariaDB: PREPARE/EXECUTE và USING

MySQL/MariaDB có dynamic SQL với `PREPARE`/`EXECUTE` và tham số `?` ở vị trí giá trị được hỗ trợ. Cách truyền tham số có thể khác JDBC, ví dụ qua user variables hoặc cú pháp routine/phiên bản tương ứng.

Không viết:

```sql
-- Ví dụ chống chỉ định, tên biến chỉ minh họa.
SET @sql = CONCAT(
    'SELECT * FROM orders WHERE status = ''',
    @user_status,
    ''''
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
```

Câu `PREPARE` phía sau **không biến nội dung đã ghép thành dữ liệu**: SQL text đã bị ảnh hưởng từ trước. Phải dùng placeholder trong template SQL, rồi truyền giá trị riêng theo cơ chế MySQL/MariaDB.

### 13.5. Oracle PL/SQL: bind variables

Trong Oracle, `EXECUTE IMMEDIATE` hỗ trợ bind placeholders cho các giá trị:

```sql
-- Bên trong khối PL/SQL có biến tương ứng:
EXECUTE IMMEDIATE
    'UPDATE orders SET status = :new_status
       WHERE order_id = :order_id'
USING p_new_status, p_order_id;
```

Nếu tên bảng/cột cần động, dùng danh sách đối tượng cho phép và cơ chế kiểm tra/quote identifier tương ứng, chẳng hạn một số API trong `DBMS_ASSERT` theo nhu cầu; **không** nối user input bất kỳ rồi cho code chạy với quyền cao.

## 14. Injection và quyền thực thi: nguy hiểm hơn khi ứng dụng có nhiều đặc quyền

Giả sử ứng dụng chỉ cần:

```sql
SELECT order_id, status
FROM orders
WHERE tenant_id = ?;
```

Nhưng DB account của ứng dụng lại có:

- Quyền SELECT mọi bảng nhạy cảm.
- Quyền UPDATE/DELETE trên mọi bảng.
- Quyền ALTER/DROP schema.
- Quyền thực thi routine quản trị.
- Quyền file/network/extension đặc biệt.

Khi truy vấn bị injection, **khả năng gây hại có thể tăng rất nhiều** vì câu SQL được thực thi trong context quyền của DB account đó.

### 14.1. Least privilege

Một tài khoản chỉ đọc báo cáo có thể được cấp:

```sql
-- Chỉ là khái niệm, cú pháp GRANT thay đổi theo DBMS.
GRANT SELECT ON reporting.monthly_sales TO report_reader;
```

Không cấp quyền `DROP TABLE`, `CREATE EXTENSION` hoặc quyền quản trị cho tài khoản báo cáo nếu không cần.

Tương tự, dịch vụ cập nhật đơn chỉ cần phạm vi UPDATE cần thiết; dùng **view, procedure có kiểm tra quyền, RLS và role chuyên biệt** nếu phù hợp.

**Least privilege không sửa nguyên nhân injection**, nhưng giảm phạm vi tác động nếu vẫn có lỗi.

### 14.2. Multi-tenant: injection có thể phá điều kiện tenant

Nếu code ghép dữ liệu vào một SQL chứa:

```sql
WHERE tenant_id = 10 AND ...
```

một sai lệch cú pháp có thể làm predicate không còn giữ giới hạn tenant. Parameterization giúp bảo vệ ý nghĩa của điều kiện, nhưng cần thêm **authorization**:

- Tenant ID phải lấy từ nguồn tin cậy.
- Các JOIN phải dùng tenant key nếu khóa chỉ duy nhất theo tenant.
- RLS có thể tăng lớp bảo vệ, nhưng phải cấu hình context chính xác.
- Người dùng không được tự đặt session context bằng SQL tự do.
- DB account không có quyền truy cập vượt phạm vi khi không cần.

## 15. SQL injection không cần nhiều câu lệnh SQL

Có người dựa vào việc driver/connection không cho gửi nhiều statement phân tách bởi dấu chấm phẩy:

```text
"Đã tắt multi-statements nên an toàn."
```

Đây là kết luận sai. Một injection có thể làm thay đổi **chính điều kiện của một câu SELECT**, không cần tạo câu lệnh thứ hai.

Tắt multi-statements có thể giảm một kiểu rủi ro, nhưng không sửa việc **dữ liệu bị hiểu thành SQL code**.

Tương tự, việc ứng dụng chỉ cho dùng `SELECT` không bảo đảm an toàn: một SELECT bị tác động có thể đọc hàng không đúng phạm vi, thực hiện tính toán quá đắt hoặc gọi hàm có tác dụng phụ tùy DBMS và quyền.

## 16. Escaping không phải lựa chọn mặc định để chống injection

Một cách tự sửa thường gặp:

```java
String escapedEmail = email.replace("'", "''");

String sql =
    "SELECT * FROM users WHERE email = '" + escapedEmail + "'";
```

Việc nhân đôi dấu nháy đơn là một quy tắc trong **SQL string literal** ở nhiều phương ngữ. Tuy nhiên, dùng nó như giải pháp tổng quát có vấn đề:

- Câu SQL có thể đang cần **number, identifier, JSON path, LIKE pattern** chứ không phải string literal.
- Character set, SQL mode và cách xử lý backslash/escape khác theo DBMS.
- Một vị trí đầu vào có thể nằm **ngoài dấu nháy**; escaping string không giúp.
- Có thể quên một trong nhiều nhánh nối chuỗi.
- Một tầng trước/sau có thể decode hoặc unescape rồi sử dụng lại.
- Một đoạn query được tạo qua ORM, stored procedure hay thư viện khác có quy tắc riêng.

**Cách làm đúng mặc định:** bind parameters cho **giá trị**; với **identifier/keyword**, dùng allowlist cố định; chỉ dùng escaping chuyên dụng trong trường hợp đặc thù được review kỹ và không có binding phù hợp.

### 16.1. Không dùng `String.replace("'", "")` để “lọc hết injection”

Xóa dấu nháy:

- Làm hỏng dữ liệu hợp lệ như tên `O'Connor`.
- Không giải quyết mọi bối cảnh injection.
- Có thể làm dữ liệu bị sửa trước khi lưu, gây mất tính chính xác.
- Không thay được parameterization.

Ví dụ tên khách hàng `O'Connor` phải được lưu như nguyên văn dữ liệu:

```java
ps.setString(1, "O'Connor");
```

Không phải bị biến thành `OConnor`.

### 16.2. “Dùng REGEX chỉ nhận chữ/số” cũng không đủ

Một field như `orderId` có thể được giới hạn là số nguyên dương, nhưng nhiều field cần:

- Tên người có dấu, nháy đơn, gạch nối.
- Email có ký tự hợp lệ khác.
- Ghi chú tự do.
- Đường dẫn, mô tả, JSON payload.

Chặn mọi dấu đặc biệt không phải chính sách dữ liệu tốt và **không thay thế** ranh giới code/data.

## 17. Kiểm tra đầu vào vẫn cần thiết — nhưng cho mục tiêu khác

Input validation giải quyết các vấn đề nghiệp vụ:

- `pageSize` nằm trong 1–100.
- `status` thuộc `DRAFT`, `PAID`, `CANCELLED`.
- `orderId` là số nguyên dương trong phạm vi kiểu SQL.
- `email` không quá dài.
- `amount` dương, không vượt hạn mức.
- `sort` thuộc một tập tên cột được hỗ trợ.
- JSON có đúng schema và kích thước cho phép.

Nhưng một input thỏa regex đơn giản **không chứng minh câu SQL an toàn** nếu nó còn bị ghép vào vị trí cú pháp.

### 17.1. Defense-in-depth

Một hệ thống an toàn sử dụng đồng thời:

1. **Parameterized SQL**.
2. **Validation** theo kiểu và nghiệp vụ.
3. **Allowlist** cho phần cú pháp phải chọn động.
4. **Least privilege** tại database.
5. **Authorization** trên hàng/tenant/đối tượng.
6. **Giới hạn tài nguyên**: timeout, số hàng, rate limit, kích thước đầu vào.
7. **Logging/audit** phù hợp, không lộ secrets.
8. **Test và code review** tập trung vào các vị trí xây query.

Không chọn chỉ một lớp rồi bỏ qua những lớp còn lại.

## 18. Second-order SQL injection: dữ liệu đã lưu vẫn có thể nguy hiểm

**Second-order SQL injection** là trường hợp đầu vào không đáng tin được lưu qua một đường an toàn, nhưng **sau này lại bị đưa vào một câu SQL khác bằng cách ghép chuỗi**.

Ví dụ:

1. Người dùng đặt tên báo cáo chứa ký tự cú pháp SQL.
2. Ứng dụng dùng PreparedStatement để lưu `report_name` vào bảng `saved_reports`. Bước này an toàn.
3. Một job đêm đọc `report_name` và ghép nó vào câu SQL động để lấy dữ liệu.
4. Job thực thi SQL với quyền rộng hơn người dùng ban đầu.

Sơ đồ:

```text
Input người dùng
      |
      v
INSERT có bind parameters    <-- an toàn ở bước ghi
      |
      v
saved_reports.report_name
      |
      v
Job đọc lại từ database
      |
      v
Ghép report_name vào SQL    <-- lỗi xuất hiện ở bước dùng lại
      |
      v
SQL parser có thể hiểu input thành cú pháp
```

**Bài học:** không dùng “dữ liệu này lấy từ DB nên chắc chắn an toàn” để biện minh cho string concatenation. Cần **parameterization tại mọi nơi dữ liệu được dùng như giá trị**, kể cả khi nguồn là bảng nội bộ, queue hoặc cache.

### 18.1. Migration và batch job

Một script migration có thể duyệt tên khách hàng, dữ liệu mô tả, tên file, cấu hình báo cáo rồi xây SQL động. Nếu nó dùng tài khoản migration có quyền ALTER/DROP, hậu quả có thể lớn hơn một request bình thường.

Trong batch job, đừng xây:

```text
UPDATE table SET note = ' + row.note + ' ...
```

Hãy dùng prepared/batch statements và bind các giá trị. Đối với tên bảng động, chỉ lấy từ metadata/allowlist được quản trị.

## 19. Những vùng dễ bỏ sót: ORDER BY, GROUP BY, JSON path và báo cáo

Một query có thể bind tốt mọi `WHERE` nhưng vẫn đưa input vào vùng khác.

| Vị trí động | Sai lầm thường gặp | Hướng xử lý |
|---|---|---|
| `WHERE col = value` | Nối value vào string | Bind value |
| `LIKE` | Nối keyword với dấu nháy | Bind pattern; escape wildcard nếu cần |
| `IN (...)` | Nhận CSV rồi nối vào ngoặc | Tạo placeholder hợp lệ, bind từng phần tử |
| `ORDER BY column` | Nối tên cột request | Allowlist tên cột |
| `ASC/DESC` | Nối chuỗi direction request | Chọn keyword cố định từ enum |
| `LIMIT/OFFSET` | Nối raw query param | Parse số, giới hạn, bind theo dialect |
| `FROM table` | Nối tên bảng từ user | Không cho tùy ý; mapping allowlist |
| `GROUP BY` | Nối expression do client gửi | Chọn expression từ tập cố định |
| JSON path | Nối raw path vào SQL | Bind/allowlist path theo API của DBMS |
| Full-text search | Nối biểu thức search syntax | Phân biệt query language và literal; bind/escape theo bộ máy tìm kiếm |
| Stored procedure | Ghép tham số vào dynamic SQL | Dynamic prepare + USING/bind |
| Reporting DSL | Cho client gửi fragment SQL | Dùng AST/query builder giới hạn phép toán |

### 19.1. Đầu vào được đặt tên “sortBy” vẫn không đáng tin

Một giá trị `sortBy` có thể được người dùng sửa qua Developer Tools, HTTP client hoặc request thủ công. Việc front-end dùng dropdown **không bảo đảm** server chỉ nhận ba giá trị trong dropdown.

**Server phải kiểm tra allowlist**, không chỉ dựa vào UI.

### 19.2. JSON path có thể là cú pháp cấp hai

Các DBMS có JSON path language riêng. Nếu một API cho chọn đường dẫn như `$.items[*].sku`, giá trị đó có thể được engine JSON path parser diễn giải như một **biểu thức**, dù không nhất thiết là SQL grammar trực tiếp.

Vì vậy, khi ứng dụng cần “tìm theo một field JSON”, tốt hơn là map tên field nghiệp vụ sang các path **cố định**, đồng thời bind giá trị tìm kiếm riêng.

### 19.3. Full-text search khác tìm chuỗi bình thường

Một search engine có cú pháp toán tử riêng (`AND`, `OR`, dấu nháy, wildcard, proximity...). Nếu product yêu cầu tìm literal text, cần escaping/quoting đúng cho **ngôn ngữ tìm kiếm**. Parameterization của SQL chỉ bảo vệ **ranh giới SQL**, không tự bảo đảm query bên trong một DSL là tìm literal.

Đừng coi mọi input có `OR` là tấn công; hãy hiểu ngôn ngữ mà input được truyền vào.

## 20. Xử lý lỗi SQL injection: không tiết lộ chi tiết database

Một ứng dụng có thể trả cho client:

```text
SQL syntax error near ...
Table private_accounts does not exist ...
permission denied for table ...
```

Những thông báo này có thể làm lộ tên bảng, schema, cột, loại DBMS hoặc cấu trúc query.

Hướng xử lý:

- Trả thông báo lỗi **phù hợp nghiệp vụ**, không bao gồm raw SQL với secrets.
- Ghi log có mã lỗi, vị trí chức năng và correlation ID để điều tra.
- Không log mật khẩu/token hay toàn bộ JSON nhạy cảm.
- Không echo SQL string ghép input ra response.
- Phân biệt lỗi validation, authorization, duplicate key, transaction conflict và server error.
- Đặt thời hạn truy vấn và giới hạn tài nguyên.

**Ẩn lỗi chi tiết không sửa SQL injection.** Nó chỉ giảm lượng thông tin vô tình tiết lộ. Gốc rễ vẫn cần bind parameters/allowlist.

### 20.1. Tránh log nguyên câu SQL và giá trị bí mật

Một số ORM/driver có chế độ debug log câu SQL cùng bind values. Trên production, điều này có thể ghi lại PII, token hoặc dữ liệu thẻ vào hệ thống logging. Hãy cấu hình phân quyền log, retention, redaction và môi trường debug thích hợp.

## 21. Kiểm soát transaction và tính toàn vẹn

Một câu SQL có tham số có thể hợp lệ về cú pháp và quyền nhưng vẫn gây lỗi nghiệp vụ khi có **ghi đồng thời**.

Ví dụ hai request cùng đặt đơn hàng:

```text
Request A kiểm tra tồn kho = 1
Request B kiểm tra tồn kho = 1
A trừ tồn kho
B cũng trừ tồn kho
```

PreparedStatement ngăn injection nhưng **không tự giải quyết race condition**.

Khi DML quan trọng:

- Sử dụng transaction.
- Kiểm tra số hàng bị UPDATE/DELETE.
- Dùng ràng buộc CHECK/UNIQUE/FK.
- Chọn isolation/locking phù hợp.
- Thiết kế retry/idempotency khi cần.
- Giới hạn quyền thực thi.

**SQL injection và transaction correctness là hai vấn đề khác nhau nhưng cùng cần cho một ứng dụng an toàn.**

## 22. Phân biệt injection với lỗi authorization

Hai lỗi có thể cho kết quả “đọc đơn hàng của người khác”:

### Trường hợp A: SQL injection

Ứng dụng viết:

```java
"SELECT * FROM orders WHERE tenant_id = " + userInput
```

Input ảnh hưởng tới cú pháp SQL, làm query thay đổi ngoài ý định.

### Trường hợp B: thiếu kiểm tra tenant

Ứng dụng viết:

```sql
SELECT * FROM orders WHERE tenant_id = ?;
```

nhưng bind `tenant_id` từ request mà không kiểm tra đó có phải tenant người dùng được phép xem không.

Trong trường hợp B, **không có SQL injection**, nhưng vẫn có lỗi authorization. Sửa B cần xác định tenant được xác thực và áp chính sách hàng/role, không chỉ thay Statement bằng PreparedStatement.

### 22.1. Khi nào cần RLS?

Row-Level Security (RLS) trên PostgreSQL và một số DBMS khác có thể áp chính sách đọc/ghi theo hàng ngay ở database. Nó hữu ích khi nhiều query/routine cùng truy cập dữ liệu tenant.

Nhưng RLS có cấu hình owner/BYPASSRLS, execution context, session state và policy riêng. Không coi việc bật RLS là bằng chứng có thể tiếp tục nối chuỗi SQL. **RLS bổ sung lớp giới hạn quyền**, không thay thế parameterization.

## 23. Khác biệt thực hành theo DBMS

Nguyên tắc tách SQL code khỏi dữ liệu là chung, nhưng **placeholder syntax** và API khác nhau.

### 23.1. PostgreSQL

Ở protocol SQL của PostgreSQL, câu chuẩn bị có thể dùng `$1`, `$2`:

```sql
PREPARE find_orders (bigint, text) AS
SELECT order_id, status
FROM orders
WHERE tenant_id = $1
  AND status = $2;
```

Gọi:

```sql
EXECUTE find_orders(10, 'DRAFT');
```

Đây là ví dụ dùng `PREPARE/EXECUTE` của PostgreSQL SQL. Trong Java **JDBC**, code vẫn thường dùng `?` và `PreparedStatement`, để driver làm việc với DBMS.

Đối với PL/pgSQL dynamic SQL, `EXECUTE ... USING` bind các giá trị; `format('%I', identifier)` hỗ trợ quote định danh, **nhưng tên đối tượng phải nằm trong allowlist**.

### 23.2. MySQL/MariaDB

JDBC dùng:

```sql
SELECT order_id
FROM orders
WHERE tenant_id = ?
  AND status = ?;
```

MySQL/MariaDB có SQL chuẩn bị trên server với `PREPARE`/`EXECUTE`. Cách đặt biến và hạn chế số statement cần tra đúng phiên bản, không phải copy lệnh PostgreSQL `PREPARE find_orders(bigint, text) AS ...`.

MySQL có option liên quan multi-query, nhưng **không bật multiple statements vẫn có thể tồn tại injection trong một statement**. Đừng dựa vào option ấy làm bảo vệ chính.

### 23.3. SQL Server

T-SQL thường dùng named parameters:

```sql
DECLARE @tenantId bigint = 10;
DECLARE @status nvarchar(20) = N'DRAFT';

SELECT order_id
FROM dbo.orders
WHERE tenant_id = @tenantId
  AND status = @status;
```

Ở JDBC, vẫn dùng dấu `?` theo API và driver. Trong dynamic T-SQL, nên dùng `sp_executesql` với danh sách tham số thay vì `EXEC('...'+userInput)`.

**Lưu ý đặc thù:** ownership chaining và `EXECUTE AS` có thể khiến dynamic SQL chạy trong context quyền không như SQL tĩnh. Quyền có thể thay đổi hậu quả của lỗi, nhưng không sửa nguy cơ từ nối input.

### 23.4. Oracle

Ở SQL/PLSQL, bind variables thường có dạng `:name`:

```sql
SELECT order_id, status
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status;
```

Trong Java JDBC, vẫn thường là dấu `?`. PL/SQL `EXECUTE IMMEDIATE ... USING` cho bind values vào dynamic SQL. Với identifier, không thể dùng bind variable để biến giá trị thành tên bảng; cần allowlist và công cụ kiểm tra/quote của Oracle phù hợp.

### 23.5. SQLite

SQLite hỗ trợ positional/named parameters trong API của nó. Ví dụ Python `sqlite3`:

```python
import sqlite3

with sqlite3.connect("demo.db") as conn:
    rows = conn.execute(
        """
        SELECT order_id, status
        FROM orders
        WHERE tenant_id = ?
          AND status = ?
        """,
        (authorized_tenant_id, requested_status)
    ).fetchall()
```

Không làm:

```python
# KHÔNG AN TOÀN.
sql = (
    "SELECT * FROM orders WHERE status = '"
    + requested_status
    + "'"
)
rows = conn.execute(sql).fetchall()
```

SQLite còn có named placeholders (theo API driver), nhưng không phải hệ thống role/server giống PostgreSQL. Nếu người dùng có quyền mở và sửa file SQLite trực tiếp, tham số hóa trong ứng dụng **không đủ** để thiết lập phân quyền trên file đó; cần bảo vệ ở lớp OS/application.

### 23.6. Bảng ghi nhớ phương ngữ

| Môi trường | Cách bind thông dụng | Cần tránh |
|---|---|---|
| JDBC nói chung | `PreparedStatement`, `?`, `setXxx` | Ghép giá trị vào `Statement` |
| PostgreSQL native SQL | `$1`, `$2` qua prepare/bind; PL/pgSQL `USING` | `EXECUTE` với chuỗi nối input |
| MySQL/MariaDB | `?` và prepare API | `CONCAT` user value thành SQL text |
| SQL Server T-SQL | `sp_executesql` + `@named` parameters | `EXEC(@sql)` với SQL text nối input |
| Oracle PL/SQL | `:bind`, `EXECUTE IMMEDIATE ... USING` | Nối tham số vào dynamic text |
| SQLite API | `?`/named placeholders theo driver | Nối input vào SQL rồi `execute` |

## 24. Phát hiện lỗi trong code review

Trong code review, tìm những biểu thức có dấu hiệu **SQL text phụ thuộc input**:

```text
"SELECT ... WHERE " + userInput
"ORDER BY " + request.sortBy
"IN (" + csvIds + ")"
"FROM " + request.table
String.format("... %s ...", userInput)
f"SELECT ... {user_input} ..."
template literals với raw user input
dynamic SQL EXEC(... concatenated input ...)
```

Đây là **dấu hiệu cần xem xét**, không phải bằng chứng chắc chắn có lỗ hổng trong mọi trường hợp.

### 24.1. Câu hỏi review quan trọng

1. Input đến từ đâu — HTTP, file, database, queue?
2. Nó nằm ở vị trí **value**, **identifier**, **keyword** hay **SQL expression**?
3. Nếu là value, có **bind parameter** thực sự không?
4. Nếu là identifier/keyword, có mapping **allowlist cố định** không?
5. Tenant/user ID được lấy từ nguồn đã xác thực chưa?
6. DB account có quyền rộng hơn nhiệm vụ không?
7. Stored procedure/ORM có tự nối query ở bên trong không?
8. Có đường xử lý lỗi, retry hoặc logging làm lộ dữ liệu nhạy cảm không?
9. Có đường dữ liệu second-order từ DB/queue sang SQL động không?
10. Test có chạy bằng role ít quyền thực tế không?

### 24.2. Tránh auto-fix bằng regex đơn giản

Một công cụ có thể phát hiện `"SELECT ..." + userInput`, nhưng không phải mọi SQL xây động đều nguy hiểm. Ngược lại, một chuỗi truy vấn có thể được ghép qua nhiều hàm/biến trung gian khiến regex không phát hiện.

Cần kết hợp:

- Static analysis/SAST phù hợp ngôn ngữ.
- Review thủ công các query builder/dynamic SQL.
- Unit/integration tests.
- Kiểm tra quyền DB và dữ liệu tenant.
- Theo dõi lỗi bất thường ở runtime.

## 25. Kiểm thử an toàn trên môi trường riêng

Một bài thử phòng vệ nên có database **không chứa dữ liệu thật** và role chỉ có quyền cần thiết.

### 25.1. Tạo bộ dữ liệu nhỏ

Ví dụ PostgreSQL:

```sql
CREATE TEMP TABLE demo_orders (
    order_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    total_amount NUMERIC(12,2) NOT NULL
);

INSERT INTO demo_orders
    (order_id, tenant_id, status, total_amount)
VALUES
    (101, 10, 'DRAFT', 100),
    (102, 10, 'PAID', 250),
    (103, 20, 'DRAFT', 300),
    (104, 20, 'PAID', 120);
```

### 25.2. SQL mẫu dùng bind thay vì ghép chuỗi

Với PostgreSQL SQL:

```sql
PREPARE demo_find_orders (integer, text) AS
SELECT order_id, tenant_id, status
FROM demo_orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY order_id;
```

Thử bình thường:

```sql
EXECUTE demo_find_orders(10, 'DRAFT');
-- Hàng 101
```

Thử với chuỗi chứa ký tự cú pháp:

```sql
EXECUTE demo_find_orders(10, ''' OR ''1''=''1'' -- ');
-- Không làm thay đổi SQL predicate.
-- Với dữ liệu mẫu: không có status khớp nguyên chuỗi này.
```

Do PostgreSQL parse giá trị đối số trong một câu `EXECUTE` tự viết ở SQL console, ta phải dùng đúng escaping cho **literal của console** để tạo ra dữ liệu chứa dấu nháy. **Trong ứng dụng**, dùng driver bind thay vì tự nối literal như thế.

### 25.3. Những trường hợp test cần có

| Loại input | Mục tiêu test |
|---|---|
| `DRAFT` | Chỉ lấy hàng dự kiến |
| Chuỗi rỗng | Không làm hỏng query |
| Dấu nháy đơn | Giữ nguyên như dữ liệu |
| Dấu nháy kép | Giữ nguyên như dữ liệu |
| Dấu chấm phẩy | Không sinh statement phụ |
| Chữ `AND`/`OR` | Chỉ là ký tự trong value |
| Dấu comment | Không biến thành comment SQL |
| Unicode và tên có dấu | Không bị sửa bằng sanitizer |
| `NULL`/thiếu field | Đúng validation và ngữ nghĩa NULL |
| Chuỗi rất dài | Bị giới hạn tài nguyên, không gây treo |
| Tenant khác | Không đọc/ghi được dữ liệu trái quyền |
| Cột sort ngoài allowlist | Bị từ chối sớm |
| Danh sách IN rỗng/quá dài | Xử lý có giới hạn |
| LIKE với % và _ | Đúng yêu cầu tìm literal hay wildcard |
| Dữ liệu đọc từ DB/queue | Không tái ghép thành SQL code |

Mục tiêu là **chứng minh ranh giới code/data và authorization vẫn đúng**, không phải gây tác động trên hệ thống không được phép.

### 25.4. Kiểm thử bằng role ít quyền

Nếu test chạy bằng superuser, một SQL injection có thể biểu hiện khác production. Hãy tạo role test có các quyền tương đương role ứng dụng thực tế, dùng dữ liệu giả và xác nhận:

- Không đọc được bảng không liên quan.
- Không truy cập hàng tenant khác.
- Không chạy DDL/DELETE ngoài phạm vi.
- Không lộ lỗi nội bộ ra response.

## 26. Khi không thể dùng tham số cho cấu trúc SQL

Có những yêu cầu nghiệp vụ thực sự cần lựa chọn cấu trúc SQL:

- Báo cáo chọn một trong vài chiều nhóm.
- UI sắp xếp theo cột được hỗ trợ.
- Chọn một bảng staging theo một danh sách được quản trị.
- Query builder cho người dùng chọn bộ lọc trong tập cố định.

Thay vì nhận **chuỗi SQL tùy ý**, hãy thiết kế một DSL nhỏ có cấu trúc:

```json
{
  "filters": [
    { "field": "status", "op": "eq", "value": "DRAFT" }
  ],
  "sort": {
    "field": "createdAt",
    "direction": "desc"
  },
  "pageSize": 20
}
```

Ứng dụng chuyển:

- `field = "status"` → cột `status` đã được allowlist.
- `op = "eq"` → toán tử `=` cố định.
- `value = "DRAFT"` → **bind parameter**.
- `sort.field` → mapping tên cột cố định.
- `sort.direction` → keyword `ASC` hoặc `DESC` cố định.
- `pageSize` → integer có giới hạn và bind.

```text
Input có cấu trúc
     |
     v
Kiểm tra field/op/sort qua allowlist
     |
     v
Dựng SQL chỉ bằng fragment tin cậy
     |
     v
Bind tất cả giá trị không đáng tin
     |
     v
DB thực thi theo quyền đã giới hạn
```

### 26.1. Tại sao không chỉ cho client gửi WHERE clause?

Nếu API nhận:

```json
{"where": "status = 'DRAFT' AND tenant_id = 10"}
```

thì client đã được cấp quyền **viết một phần SQL**. Ngay cả khi chỉ muốn lọc, nó có thể chứa biểu thức ngoài tập cho phép. Một DSL bị giới hạn chặt và query builder có AST là phương án dễ bảo vệ hơn.

### 26.2. Quoting vẫn cần khi tên được lấy từ metadata tin cậy

Đối với một số hệ tạo bảng staging động, tên đối tượng có thể đến từ metadata do server quản lý. Khi đó dùng hàm quote identifier đúng phương ngữ **sau khi** kiểm tra quyền/phạm vi. Đừng ghép raw tên từ request vào SQL, dù tên đã qua một regex “trông hợp lệ”.

## 27. Các dấu hiệu phân biệt: SQL injection, logic bug, pattern bug

| Hiện tượng | Có nhất thiết là SQL injection? | Gốc vấn đề |
|---|---|---|
| Input thay đổi số toán tử SQL trong câu query | **Có dấu hiệu mạnh** | Dữ liệu bị hiểu thành cú pháp |
| Input là `%` làm LIKE trả nhiều hàng | Không, nếu bind an toàn | Wildcard/pattern semantics |
| User tự chọn tenant_id khác dù bind đúng | Không | Thiếu authorization |
| Query thiếu `WHERE tenant_id` | Không nhất thiết | Lỗi thiết kế truy vấn |
| Cast string sang integer thất bại | Không nhất thiết | Validation/type conversion |
| SQL do người dùng có quyền DBA viết | Không nhất thiết là injection | Đây có thể là chức năng được cho phép, nhưng cần quản trị quyền |
| ORM nối JPQL với raw input | Có nguy cơ injection | Query language bị điều khiển bởi input |
| Stored procedure nối input vào dynamic SQL | Có nguy cơ injection | Dynamic SQL trộn code/data |
| Query chậm vì mảng IN 100.000 phần tử bind | Không | Resource/performance issue |
| Tham số string chứa `' OR ...` nhưng không có hàng khớp | Không phải lỗ hổng ở vị trí bind | Input vẫn được coi là dữ liệu |

Phân loại đúng giúp đội ngũ sửa đúng lớp thay vì thêm các “sanitizer” chung chung có thể tạo lỗi mới.

## 28. Sai lầm phổ biến

### 28.1. "Người dùng chỉ chọn dropdown nên không thể nhập cú pháp nguy hiểm"

Dropdown là giao diện phía client, request có thể bị sửa. Server vẫn phải bind dữ liệu và kiểm tra allowlist.

### 28.2. "Tôi đã xóa dấu nháy đơn khỏi input"

Một input hợp lệ có thể cần dấu nháy, và injection còn có thể xảy ra tại những vị trí không dùng string literal. Parameterization là giải pháp chính.

### 28.3. "Tôi đã dùng PreparedStatement nên mọi phần query đều an toàn"

Nếu câu SQL truyền cho `prepareStatement` được tạo bằng cách nối `ORDER BY`/table/filter từ request trước đó, lỗ hổng vẫn tồn tại.

### 28.4. "Tôi đã dùng stored procedure nên chắc chắn an toàn"

Stored procedure có dynamic SQL ghép chuỗi vẫn có thể bị injection.

### 28.5. "ORM sẽ tự escape mọi thứ"

ORM chỉ an toàn khi dùng API parameter binding/query builder đúng cách. Native query hoặc HQL/JPQL nối string vẫn nguy hiểm.

### 28.6. "Dữ liệu lấy từ database là dữ liệu tin cậy"

Dữ liệu đã lưu có thể bắt nguồn từ user. Khi đem ghép lại vào SQL ở bước khác, second-order injection xuất hiện.

### 28.7. "Đã tắt multi-statements là xong"

Một câu SELECT bị thay predicate có thể đã đủ làm lộ dữ liệu.

### 28.8. "Có WAF là không cần sửa code"

WAF có thể chặn một số mẫu, nhưng không hiểu toàn bộ logic SQL/ORM và không thay parameterization. Cần sửa tại nơi dựng câu truy vấn.

### 28.9. "Kiểm tra regex chỉ có chữ/số là đủ"

Không phải mọi giá trị chỉ gồm chữ/số, và regex không tách dữ liệu khỏi ngữ pháp SQL.

### 28.10. "Chỉ cần bind WHERE, tên sort tùy ý cũng không sao"

`ORDER BY` và identifier là vùng cú pháp; phải mapping từ enum/allowlist.

### 28.11. "Tôi đã quote đúng tên bảng từ người dùng"

Quote ngăn phá cú pháp nhưng không chứng minh user **được phép chọn** bảng đó.

### 28.12. "Input đã parse thành integer nên không cần limit"

Parse integer giúp chặn cú pháp lạ tại chỗ đó nhưng còn cần kiểm tra phạm vi, dấu âm, overflow, ID thuộc tenant và page size.

### 28.13. "Mật khẩu có thể so sánh thẳng trong SQL"

Không nên lưu/so sánh plaintext password. Cần password hashing và luồng xác thực phù hợp, độc lập với SQL injection.

### 28.14. "Thông báo SQL syntax error chỉ là lỗi giao diện"

Lỗi có thể lộ schema/query và là dấu hiệu code xây SQL không an toàn. Cần điều tra và sửa gốc.

### 28.15. "SQL injection chỉ xảy ra khi người ta cố tấn công"

Một chuỗi hợp lệ chứa dấu nháy hoặc ký tự đặc biệt cũng có thể làm hỏng SQL string nếu code nối dữ liệu. Lỗi có thể phát hiện ngay cả trong sử dụng bình thường.

## 29. Checklist phòng vệ theo luồng phát triển

### 29.1. Khi thiết kế API

- Xác định input là **value** hay **cấu trúc truy vấn**.
- Giữ cấu trúc truy vấn do server kiểm soát.
- Không cho client gửi raw SQL fragment nếu sản phẩm không phải công cụ SQL có quyền riêng.
- Dùng enum/allowlist cho sort field, direction, filter operator, report source.
- Định nghĩa giới hạn page size, danh sách ID, payload và timeout.
- Tách authorization khỏi dữ liệu client gửi.

### 29.2. Khi viết truy vấn

- Bind mọi giá trị: text, number, date, JSON, status, tenant, ID.
- Không tự thêm dấu nháy quanh `?`.
- Không lấy `request.sortBy` nối thẳng vào ORDER BY.
- Dùng placeholder cho danh sách IN hoặc collection parameter của DBMS.
- Dùng escaping LIKE khi muốn tìm literal `%`/`_`.
- Chú ý SQL NULL và kiểu dữ liệu.
- Với dynamic SQL trong stored procedure, sử dụng bind/USING.
- Không xây chuỗi SQL bằng dữ liệu đã lưu mà không kiểm soát.

### 29.3. Khi cấu hình database

- Tài khoản ứng dụng dùng **least privilege**.
- Tách tài khoản read-only, write và migration/admin.
- Không dùng tài khoản superuser cho request thông thường.
- Giới hạn quyền trên schema/table/procedure.
- Cân nhắc RLS/view có kiểm tra theo tenant khi phù hợp.
- Đặt statement timeout, quota và giám sát query.
- Backup, logging và audit theo chính sách.

### 29.4. Khi kiểm thử và review

- Chạy test bằng role ít quyền.
- Test chuỗi có dấu nháy, comment, Unicode, wildcard, rỗng, quá dài.
- Test trường sort không thuộc allowlist.
- Test không có dữ liệu cross-tenant.
- Review mọi vị trí nối chuỗi ra SQL, kể cả migration/job/background worker.
- Kiểm tra repository/ORM/native query và stored routine.
- Dùng SAST/DAST trong phạm vi được phép, đồng thời review logic bằng con người.
- Không đưa payload kiểm thử vào hệ thống của người khác.

## 30. Bài tập thực hành có đáp án

### Bài 1. Nhận diện nguyên nhân gốc

```java
String sql = "SELECT * FROM users WHERE email = '" + email + "'";
```

**Hỏi:** lỗi chính là gì?

**Đáp án:** `email` không đáng tin được ghép trực tiếp vào **SQL text**. Nếu có ký tự mang ý nghĩa cú pháp, nó có thể thay đổi truy vấn. Sửa bằng `WHERE email = ?` và `PreparedStatement.setString`.

### Bài 2. Sửa JDBC SELECT

**Yêu cầu:** sửa:

```java
String sql = "SELECT * FROM products WHERE category_id = " + categoryId;
```

**Đáp án:**

```java
String sql = "SELECT * FROM products WHERE category_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, categoryId);

    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
}
```

Vẫn cần kiểm tra `categoryId` có trong phạm vi người dùng được xem nếu API có phân quyền danh mục.

### Bài 3. Đâu là dữ liệu, đâu là cú pháp?

```sql
SELECT order_id FROM orders WHERE status = ? ORDER BY created_at DESC;
```

**Đáp án:**

- `status` là **giá trị cần bind**.
- `created_at` là **identifier SQL** do code quyết định.
- `DESC` là **keyword SQL** do code quyết định.

Nếu người dùng được chọn trường sort/direction, chỉ cho chọn trong allowlist, không bind tên cột như giá trị.

### Bài 4. Vì sao dấu ? trong nháy đơn là sai?

```java
String sql = "SELECT * FROM users WHERE name = '?'";
```

**Đáp án:** `'?'` là literal chứa dấu hỏi chứ thường không là placeholder. Viết `WHERE name = ?` rồi `ps.setString(1, name)`.

### Bài 5. LIKE với ký tự %

**Tình huống:** nhập `50%` và chỉ muốn tìm các chuỗi có đúng cụm `50%`.

**Đáp án:** parameter binding ngăn SQL injection, nhưng `%` có nghĩa wildcard trong LIKE. Dùng `LIKE ? ESCAPE '!'` và escape chính xác `!`, `%`, `_` trong **pattern**, sau đó bind pattern.

### Bài 6. IN danh sách ID

**Tình huống:** người dùng chọn danh sách `[101,102,103]`, code nối `idsCsv` vào `IN (...)`.

**Đáp án:** thay bằng `IN (?, ?, ?)` và bind ba ID, hoặc dùng array/table-valued parameter theo DBMS. Giới hạn số phần tử, xử lý danh sách rỗng, giữ tenant filter.

### Bài 7. ORDER BY dynamic

```java
String sql = "SELECT * FROM orders ORDER BY " + sortBy;
```

**Đáp án:** không bind tên cột bằng `?`, cũng không nối `sortBy` thô. Map `created` → `created_at`, `amount` → `total_amount` rồi chỉ nối fragment đã được chọn từ code.

### Bài 8. ASC/DESC

**Tình huống:** UI gửi `direction = "desc"`.

**Đáp án:** parse thành enum hoặc so sánh chính xác `asc`/`desc`, chọn literal cố định `ASC`/`DESC`. Không đưa nguyên string direction vào câu SQL.

### Bài 9. Tenant ID bị lấy từ request

**Tình huống:** `WHERE tenant_id = ?` với ID từ form, không kiểm tra quyền.

**Đáp án:** đã tránh SQL injection về cú pháp, nhưng vẫn có lỗi authorization. Phải lấy tenant từ context được xác thực và áp chính sách hàng thích hợp.

### Bài 10. Stored procedure SQL động

**Tình huống:** SQL Server procedure tạo `@sql` bằng cách nối `@userStatus` rồi gọi `EXEC(@sql)`.

**Đáp án:** vẫn có injection vì input trở thành SQL code. Dùng `sp_executesql` với query text cố định và tham số `@status`.

### Bài 11. PostgreSQL PL/pgSQL USING

**Yêu cầu:** truyền `status` vào dynamic query mà không nối string.

**Đáp án:**

```sql
EXECUTE
  'SELECT count(*) FROM orders WHERE status = $1'
INTO row_count
USING requested_status;
```

Đoạn này nằm trong thân PL/pgSQL có biến `row_count`, `requested_status` đã được khai báo. Nếu cần tên bảng động, dùng identifier quoting và allowlist.

### Bài 12. ORM có an toàn tuyệt đối không?

**Tình huống:** Hibernate được dùng nhưng JPQL tạo bằng `"... WHERE o.status = '" + input + "'"`.

**Đáp án:** không. ORM không sửa query string đã bị nối input. Dùng `:status` và `setParameter("status", input)`.

### Bài 13. MyBatis #{} và raw text

**Hỏi:** vì sao `#{status}` an toàn hơn kiểu raw substitution `${status}` cho giá trị người dùng?

**Đáp án:** `#{...}` dùng parameter binding; raw substitution đưa text vào câu SQL, có thể thay đổi cấu trúc query. Chỉ dùng raw fragment từ mapping cố định cho trường hợp bất khả kháng như tên cột.

### Bài 14. Second-order injection

**Tình huống:** hệ thống lưu tên báo cáo bằng PreparedStatement, nhưng job đêm lấy tên đó và nối vào dynamic SQL.

**Đáp án:** bước lưu an toàn không bảo vệ bước dùng lại. Job vẫn phải xem tên đó là không đáng tin, áp allowlist và bind các giá trị tương ứng.

### Bài 15. Nhận diện sự khác biệt giữa LIKE bug và injection

**Tình huống:** câu `WHERE name LIKE ?` được bind pattern `%` và trả hầu hết hàng.

**Đáp án:** không phải SQL injection ở vị trí tham số. Đây là wildcard semantics/logic tìm kiếm. Escape pattern nếu người dùng không được sử dụng wildcard.

### Bài 16. Không cho multi-statements có đủ không?

**Đáp án:** không. Một điều kiện `WHERE` bị thay đổi trong **một SELECT** đã có thể lộ dữ liệu. Vẫn phải bind.

### Bài 17. Escaping dấu nháy đơn có đủ không?

**Đáp án:** không. Phụ thuộc dialect/context, không áp cho identifier/number/ORDER BY/LIKE như nhau. Dùng parameter binding cho giá trị, allowlist cho cú pháp.

### Bài 18. Giá trị email có dấu nháy

**Tình huống:** người dùng có tên `O'Connor`.

**Đáp án:** giữ nguyên dữ liệu và bind bằng `setString`; không xóa dấu nháy để “bảo mật”. Dữ liệu hợp lệ không được biến dạng chỉ vì code đang xây SQL không an toàn.

### Bài 19. Cấp quyền quá rộng

**Tình huống:** service tìm kiếm chỉ cần SELECT một view nhưng đang đăng nhập DB bằng account có quyền DROP toàn schema.

**Đáp án:** giảm quyền account xuống đúng phạm vi. Đây là defense-in-depth giúp giảm hậu quả, **không thay thế** sửa SQL injection trong code.

### Bài 20. SQL NULL

**Tình huống:** `WHERE email = ?` và tham số SQL NULL.

**Đáp án:** `= NULL` không trả TRUE theo logic SQL thông thường. Dùng nhánh query cố định `email IS NULL` khi nghiệp vụ tìm giá trị NULL. Đây là vấn đề ngữ nghĩa NULL, không phải injection.

### Bài 21. Kiểm tra nguồn tin cậy

**Hỏi:** dữ liệu lấy từ bảng `saved_filters` có được tự nối vào câu SQL không?

**Đáp án:** không. Bản ghi có thể bắt nguồn từ người dùng. Khi dùng lại để dựng query, phải tiếp tục dùng allowlist, parameterization và kiểm soát quyền.

### Bài 22. Dynamic report builder

**Yêu cầu:** user chọn `field=status`, `op=eq`, `value=DRAFT`.

**Đáp án:** mapping `field` và `op` sang cột/toán tử cố định do code định nghĩa; bind `value` với placeholder. Không cho người dùng gửi nguyên `WHERE status = 'DRAFT'` như fragment SQL không kiểm soát.

### Bài 23. Phân biệt authorization và injection

**Tình huống:** chương trình bind `orderId` đúng nhưng người dùng thay `orderId` thành ID thuộc tài khoản khác rồi xem được đơn.

**Đáp án:** đây là thiếu kiểm tra ownership/tenant, không nhất thiết SQL injection. Phải bổ sung `WHERE owner_user_id = ?` với ID từ server hoặc cơ chế quyền phù hợp.

### Bài 24. Kiểm tra chống injection có cần database production không?

**Đáp án:** không. Dùng dữ liệu giả, database/container thử nghiệm và role ít quyền. Không thử payload với hệ ngoài phạm vi được phép.

### Bài 25. Tại sao code xem như an toàn mà báo lỗi khi người dùng nhập dấu nháy?

**Tình huống:** search chứa dấu nháy đơn gây `syntax error near...`.

**Đáp án:** đây là dấu hiệu code có thể đã ghép dữ liệu vào SQL string. Cần kiểm tra chỗ dựng query, sửa bằng bind parameters, thêm regression test, không chỉ đổi thông báo lỗi.

### Bài 26. Giới hạn pageSize

**Tình huống:** query đã dùng `LIMIT ?` nhưng client có thể truyền `pageSize=1000000`.

**Đáp án:** không nhất thiết là SQL injection, nhưng có nguy cơ tiêu thụ tài nguyên lớn. Giới hạn pageSize, timeout và cân nhắc pagination phù hợp.

### Bài 27. Có nên cho client chọn tên bảng không?

**Tình huống:** API nhận `table=private_payroll` và đưa vào `FROM`.

**Đáp án:** không nếu đây không phải công cụ SQL được cấp quyền đặc biệt. Chỉ cho chọn báo cáo/nguồn nằm trong allowlist, kiểm tra quyền user và tránh chạy bằng DB account quá mạnh.

### Bài 28. Sửa câu UPDATE toàn diện

Câu sai:

```java
String sql = "UPDATE orders SET status = '" + newStatus
    + "' WHERE order_id = " + orderId
    + " AND tenant_id = " + tenantIdFromRequest;
```

**Đáp án:**

```java
String sql = """
    UPDATE orders
    SET status = ?
    WHERE order_id = ?
      AND tenant_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, newStatus);
    ps.setLong(2, orderId);
    ps.setLong(3, authorizedTenantId);

    int rowsUpdated = ps.executeUpdate();
    if (rowsUpdated != 1) {
        // Xử lý theo nghiệp vụ: không tồn tại hoặc không có quyền.
    }
}
```

Cần thêm validation chuyển trạng thái, transaction và audit theo yêu cầu nghiệp vụ.

## 31. Tham khảo tài liệu chính thức

Các tài liệu bên dưới giúp đối chiếu API/bind syntax và khuyến nghị phòng ngừa. Khi triển khai, đọc đúng phiên bản driver/DBMS/framework đang dùng:

- **OWASP — SQL Injection Prevention Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- **OWASP — Query Parameterization Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Query_Parameterization_Cheat_Sheet.html
- **Oracle — Java JDBC PreparedStatement:** https://docs.oracle.com/javase/tutorial/jdbc/basics/prepared.html
- **Java SE — PreparedStatement API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html
- **PostgreSQL — PREPARE:** https://www.postgresql.org/docs/current/sql-prepare.html
- **PostgreSQL — PL/pgSQL Executing Dynamic Commands:** https://www.postgresql.org/docs/current/plpgsql-statements.html
- **MySQL — PREPARE Statement:** https://dev.mysql.com/doc/refman/8.4/en/prepare.html
- **MariaDB — PREPARE Statement:** https://mariadb.com/docs/server/reference/sql-statements/prepared-statements/prepare-statement
- **SQL Server — sp_executesql:** https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-executesql-transact-sql
- **Oracle Database — Dynamic SQL:** https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dynamic-sql.html
- **SQLite — Bind Parameters:** https://www.sqlite.org/lang_expr.html#varparam
- **Python — sqlite3 parameter substitution:** https://docs.python.org/3/library/sqlite3.html
- **Spring JDBC — JdbcTemplate:** https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- **MyBatis — SQL Mapper XML:** https://mybatis.org/mybatis-3/sqlmap-xml.html

Các hướng dẫn có thể dùng những ví dụ phương ngữ khác nhau. Không sao chép nguyên cú pháp `$1` của PostgreSQL sang JDBC hoặc cú pháp `@named` của T-SQL sang MySQL nếu driver/ngữ cảnh không hỗ trợ.

## Kết luận

**SQL injection phát sinh từ việc nhầm lẫn giữa dữ liệu và mã SQL.** Khi ứng dụng nối input không đáng tin vào chuỗi truy vấn, những ký tự vốn phải được xem là dữ liệu có thể được SQL parser hiểu thành dấu nháy, toán tử, điều kiện, tên đối tượng hay mệnh đề SQL.

Cách phòng ngừa hiệu quả nhất là **giữ SQL cố định về cấu trúc và truyền giá trị qua bind parameters**: JDBC `PreparedStatement`, named parameters của framework, `sp_executesql`, `EXECUTE ... USING` hoặc API tương ứng theo DBMS. Với những phần **không thể bind** như tên cột, tên bảng, toán tử hoặc `ASC/DESC`, chỉ lựa chọn từ **allowlist do code kiểm soát**.

Các lớp bổ sung — kiểm tra kiểu/miền dữ liệu, escape wildcard LIKE khi cần, least privilege, RLS, xác thực tenant, timeout, logging an toàn, transaction và kiểm thử role ít quyền — giúp giảm rủi ro còn lại. Nhưng **escaping, regex, WAF, ORM hoặc stored procedure không thể thay thế ranh giới code/data đúng đắn**.

Câu ghi nhớ: **“Giá trị đến từ người dùng phải là tham số, không phải một đoạn SQL.”** Và khi cần cho người dùng chọn cấu trúc truy vấn: **“Chỉ chọn từ cấu trúc mà server đã cho phép, rồi tiếp tục bind các giá trị.”**


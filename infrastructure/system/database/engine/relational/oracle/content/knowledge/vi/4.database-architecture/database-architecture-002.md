# Luồng parse, bind, execute và fetch của một câu lệnh SQL trong Oracle

Khi ứng dụng Java gọi `PreparedStatement.executeQuery()`, Oracle không đơn giản nhận chuỗi SQL rồi lập tức trả toàn bộ dữ liệu. Ở phía client và server tồn tại một vòng đời **parse → bind → execute → fetch**. Vòng đời này liên quan đến cursor, shared pool, execution plan, session, server process và Oracle Net. Hiểu đúng từng giai đoạn giúp giải thích vì sao một câu SQL chậm vì parse quá nhiều, vì thực thi tốn I/O, hay vì phải truyền và xử lý quá nhiều dòng dữ liệu.

Trong bài này, ta sẽ theo dõi một câu lệnh có tham số từ lúc ứng dụng chuẩn bị SQL đến khi đóng kết quả, sau đó liên hệ với JDBC và những công cụ quan sát thực tế của Oracle Database.

## 1. Nhìn toàn cảnh: bốn giai đoạn giải quyết việc gì?

Giả sử ứng dụng muốn lấy các đơn hàng của một khách hàng có giá trị từ một ngưỡng nhất định:

~~~sql
SELECT order_id, amount
FROM lab_orders
WHERE customer_id = :customer_id
  AND amount >= :min_amount
ORDER BY order_id;
~~~

Luồng khái niệm:

~~~text
Ứng dụng / Oracle Client                     Oracle server
──────────────────────────────────────────────────────────────────────
SQL text ─────── PARSE ─────────────────────▶ Kiểm tra cú pháp, tên, quyền
                                             Tìm cursor có thể chia sẻ
                                             Lập execution plan nếu cần

Giá trị, kiểu ─── BIND ─────────────────────▶ Gắn :customer_id, :min_amount

Yêu cầu chạy ─── EXECUTE ───────────────────▶ Bắt đầu statement
                                             SELECT: mở dòng kết quả
                                             DML: thực hiện thay đổi

Lấy kết quả ◀── FETCH nhóm dòng đầu ──────── Tạo/trả các dòng dữ liệu
Lấy tiếp    ◀── FETCH nhóm dòng sau ──────── Xử lý/trả các dòng tiếp
           ...                              ...
Hết dòng    ◀── Kết thúc kết quả ────────────

Đóng ResultSet/Statement                     Giải phóng trạng thái sử dụng
──────────────────────────────────────────────────────────────────────
~~~

| Giai đoạn | Trọng tâm | Kết quả |
|---|---|---|
| **Parse** | Phân tích SQL, kiểm tra ngữ nghĩa, tìm hoặc tạo cursor phù hợp, tối ưu kế hoạch nếu cần | Statement sẵn sàng về cấu trúc để thực thi |
| **Bind** | Gắn **giá trị có kiểu dữ liệu** vào các placeholder | Có bộ giá trị đầu vào cho lần chạy cụ thể |
| **Execute** | Khởi động statement và thực hiện công việc tương ứng với loại SQL | DML thay đổi dữ liệu; SELECT tạo trạng thái để lấy kết quả |
| **Fetch** | Sản sinh/đọc và chuyển các dòng SELECT về client theo lô | Client nhận dần các dòng cho đến hết kết quả |

**Lưu ý:** Đây là mô hình hoạt động logic, không có nghĩa luôn tồn tại bốn lần trao đổi mạng tách biệt. Driver Oracle JDBC có thể trì hoãn parse, gửi parse/bind/execute cùng một lượt, cache statement hoặc prefetch dữ liệu. Một lệnh API có thể kích hoạt nhiều giai đoạn phía server.

## 2. Cursor và các vùng bộ nhớ liên quan

**Cursor** là khái niệm trung tâm: Oracle cần lưu thông tin đã phân tích của SQL, trạng thái thực thi và vị trí đọc kết quả. Ta nên tách ba mức:

1. **SQL text** là câu lệnh ký tự mà ứng dụng gửi đi; ví dụ `SELECT ... WHERE customer_id = :customer_id`.
2. **Shared SQL area/shared cursor** tồn tại trong **library cache** thuộc **shared pool của SGA**. Thông tin SQL đã được phân tích và execution plan có thể được các session dùng lại khi tương thích.
3. **Private SQL area/trạng thái cursor của session** giữ những thông tin thuộc lần thực thi hoặc session, chẳng hạn bind, trạng thái thực thi và fetch. Hai session có thể dùng chung shared SQL nhưng không dùng chung giá trị bind hoặc vị trí đọc dòng.

~~~text
             Shared pool / Library cache trong SGA
             ┌────────────────────────────────────────┐
SQL text ───▶│ Parent cursor                          │
             │   ├── Child cursor A (ngữ cảnh A)      │
             │   └── Child cursor B (ngữ cảnh B)      │
             └─────────────────┬──────────────────────┘
                               │ chia sẻ khi phù hợp
                   ┌───────────┴────────────┐
                   ▼                        ▼
                Session A                Session B
                Bind id = 7              Bind id = 8
                Fetch đến dòng 10        Fetch đến dòng 50
~~~

**Parent cursor** nhận diện một dạng SQL text; **child cursor** chứa thông tin để thực thi theo các điều kiện tương thích, chẳng hạn kiểu bind, môi trường optimizer, quyền/đối tượng đã phân giải hoặc những yếu tố khác. Cùng SQL text có thể tồn tại nhiều child cursor; không thể mặc định một SQL sẽ mãi chỉ có một plan.

Khi đóng `ResultSet` hoặc `PreparedStatement`, ứng dụng giải phóng tài nguyên đang sử dụng. Shared cursor có thể tiếp tục được Oracle giữ trong library cache để lần khác dùng lại. **Đóng statement không có nghĩa xóa ngay shared SQL khỏi SGA.**

## 3. Parse: hiểu SQL và quyết định cách thực hiện

### 3.1. Parse kiểm tra những gì?

Oracle có thể thực hiện các công việc sau:

- **Kiểm tra cú pháp:** SQL có phù hợp với ngữ pháp Oracle không? Ví dụ `SELECT FROM lab_orders` sai vì thiếu danh sách biểu thức.
- **Kiểm tra ngữ nghĩa:** tên bảng/cột có phân giải được không, kiểu dữ liệu có phù hợp không, user có quyền cần thiết không, schema/PDB hiện tại là gì?
- **Tìm cursor có thể dùng lại:** câu SQL này đã được parse trước đó trong điều kiện tương thích chưa?
- **Tối ưu khi cần hard parse:** optimizer dựa trên statistics, index, kích thước dữ liệu, điều kiện lọc, join và các yếu tố khác để chọn **execution plan**.
- **Chuẩn bị metadata:** thông tin tham số, cột đầu ra và trạng thái cần cho thực thi.

Ví dụ:

~~~sql
SELECT order_id
FROM lab_orders
WHERE customer_id = :customer_id;
~~~

Oracle phải biết `LAB_ORDERS` là bảng nào trong **PDB và schema** của phiên làm việc; phải xác định cột `ORDER_ID` và `CUSTOMER_ID`; sau đó dùng lại cursor nếu điều kiện phù hợp hoặc chọn plan mới.

Một câu SQL không luôn có cùng ý nghĩa trong mọi session. Ví dụ `SELECT * FROM lab_orders` có thể trỏ tới các bảng khác nhau nếu `CURRENT_SCHEMA` khác nhau, hoặc nếu kết nối đến PDB khác. Đây cũng là lý do bối cảnh schema, quyền, metadata và trạng thái các đối tượng ảnh hưởng tới khả năng chia sẻ cursor.

### 3.2. Hard parse khác soft parse

| Thuật ngữ | Diễn giải | Chi phí |
|---|---|---|
| **Hard parse** | Oracle cần tạo/tái tạo cursor phù hợp và thực hiện công việc tối ưu hóa để có plan | Có thể tốn đáng kể CPU, kiểm tra metadata và đồng bộ trong shared pool |
| **Soft parse** | Oracle tìm được cursor phù hợp đã có và dùng lại thông tin phân tích | Thường rẻ hơn hard parse nhưng không miễn phí |
| **Session cursor cache / statement cache** | Cơ chế giữ handle/trạng thái statement nhằm giảm việc parse, mở/đóng lặp lại | Có thể giảm overhead ở workload lặp nhiều lần |

Ba câu lệnh dưới đây **khác SQL text** dù chỉ thay số:

~~~sql
SELECT amount FROM lab_orders WHERE customer_id = 7;
SELECT amount FROM lab_orders WHERE customer_id = 8;
SELECT amount FROM lab_orders WHERE customer_id = 9;
~~~

Nếu chương trình luôn tạo SQL bằng cách ghép literal, library cache có thể chứa nhiều cursor gần giống nhau và workload có nguy cơ tốn hard parse. Thay bằng:

~~~sql
SELECT amount FROM lab_orders WHERE customer_id = :customer_id;
~~~

SQL text ổn định, chỉ thay giá trị bind từng lần, nên **có cơ hội tái sử dụng** cursor. Tuy nhiên không thể kết luận chắc chắn mọi lần dùng cùng child cursor hay plan. Oracle có cơ chế **bind peeking** và **adaptive cursor sharing**; khi phân bố dữ liệu lệch mạnh, các bộ giá trị bind khác nhau có thể phù hợp với các kế hoạch khác nhau.

### 3.3. Execution plan xuất hiện ở đâu?

Optimizer thường chọn plan trong quá trình hard parse. Plan mô tả các **row source** và cách chúng được phối hợp: quét bảng, truy cập index, lọc, join, sort, aggregate...

~~~text
SELECT STATEMENT
└── SORT ORDER BY
    └── TABLE ACCESS FULL LAB_ORDERS
        └── Filter customer_id = :customer_id
~~~

Đây chỉ là sơ đồ minh họa. Khi bảng có index phù hợp hoặc thống kê khác, Oracle có thể chọn plan khác; một số cơ chế runtime có thể thích ứng trong quá trình thực thi. Việc ứng dụng tạo đối tượng `PreparedStatement` **chưa bảo đảm** optimizer đã chọn plan phía server ngay lúc đó.

## 4. Bind: gắn giá trị mà không viết lại cú pháp SQL

**Bind variable** đại diện cho **giá trị dữ liệu**. Trong SQL/PLSQL Oracle thường dùng `:name`; trong API JDBC `PreparedStatement` thường dùng `?` đánh số theo vị trí từ **1**.

~~~sql
SELECT order_id, amount
FROM lab_orders
WHERE customer_id = :customer_id
  AND amount >= :min_amount;
~~~

Nếu lần thứ nhất `customer_id = 7` và `min_amount = 100`, lần thứ hai `customer_id = 8` và `min_amount = 200`, SQL text vẫn là cùng câu lệnh. Oracle tách **giá trị có kiểu** khỏi cú pháp SQL, tạo điều kiện để reuse cursor và giảm rủi ro SQL injection.

Trong JDBC:

~~~java
String sql = """
    SELECT order_id, amount
    FROM lab_orders
    WHERE customer_id = ?
      AND amount >= ?
    ORDER BY order_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 7L);
    ps.setBigDecimal(2, new BigDecimal("100.00"));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("ORDER_ID");
            BigDecimal amount = rs.getBigDecimal("AMOUNT");
            System.out.println(orderId + " -> " + amount);
        }
    }
}
~~~

`setLong(1, 7L)` gắn placeholder đầu tiên theo kiểu số; `setBigDecimal(2, ...)` gắn placeholder thứ hai. Với cột ngày/giờ nên dùng kiểu thời gian và API JDBC phù hợp, tránh tự ghép chuỗi ngày phụ thuộc `NLS_DATE_FORMAT`. Khi cần bind giá trị null, `setNull(index, sqlType)` giúp driver biết kiểu mong đợi.

**Bind chỉ thay giá trị, không thay định danh hay cấu trúc SQL.** Không thể viết `SELECT * FROM ?` rồi bind tên bảng vào `?`, cũng không thể bind một từ khóa `ASC`/`DESC` như giá trị thông thường. Với tên cột do người dùng chọn, ứng dụng cần dùng một danh sách cho phép:

~~~java
String orderBy = switch (sortKey) {
    case "amount" -> "amount";
    case "created" -> "created_at";
    default -> "order_id";
};
String sql = "SELECT order_id, amount FROM lab_orders ORDER BY " + orderBy;
~~~

Ghép thẳng dữ liệu không tin cậy vào SQL vừa phá khả năng chia sẻ câu lệnh vừa mở đường cho SQL injection:

~~~java
// Không an toàn
String sql = "SELECT * FROM lab_orders WHERE customer_id = " + input;

// An toàn hơn cho một giá trị kiểu số
String safeSql = "SELECT * FROM lab_orders WHERE customer_id = ?";
try (PreparedStatement ps = connection.prepareStatement(safeSql)) {
    ps.setLong(1, customerId);
    // execute/fetch
}
~~~

### Khi bind có thể ảnh hưởng plan

Giả sử `customer_id = 1` trả 500.000 dòng, còn `customer_id = 999` trả 1 dòng. Cùng văn bản SQL có bind nhưng độ chọn lọc rất khác nhau. Khi hard parse, **bind peeking** có thể đưa thông tin giá trị bind vào ước lượng; **adaptive cursor sharing** có thể tạo hoặc chọn child cursor khác nhau. Hành vi phụ thuộc phiên bản, statistics và môi trường. Dùng bind để bảo đảm **cách truyền giá trị an toàn và cơ hội reuse cursor**; đừng mặc định mọi bind chạy với thời gian hoặc plan giống nhau.

## 5. Execute: SELECT khác DML

Khi cursor đã được chuẩn bị và bind cần thiết đã có giá trị, Oracle bắt đầu xử lý statement. **Execute của SELECT** có ngữ nghĩa khác **execute của INSERT/UPDATE/DELETE**.

### 5.1. SELECT: mở khả năng đọc kết quả

Đối với SELECT, execute khởi động trạng thái thực thi và cho phép client lấy các dòng qua fetch. Nhiều phép toán thật sự diễn ra **khi client yêu cầu dòng kế tiếp**. Cơ chế row-source của Oracle có tính **demand-driven**: một operator cần dòng thì yêu cầu operator bên dưới tạo dòng.

~~~text
Client gọi fetch
        │
        ▼
SELECT cursor cần dòng
        │
        ▼
SORT / JOIN / FILTER / TABLE ACCESS / INDEX ACCESS
        │
        ▼
Database buffers / I/O / undo để lấy phiên bản phù hợp
        │
        ▼
Trả dòng hoặc nhóm dòng cho client
~~~

Không phải lúc nào hàng đầu tiên cũng được trả ngay. Với `ORDER BY` cần sort, phép toán có thể phải đọc và sắp xếp rất nhiều dữ liệu trước khi tạo dòng đầu tiên; với index phù hợp có thể tránh một phần sort. Vì thế **`executeQuery()` trả nhanh không có nghĩa toàn bộ SQL đã hoàn tất**.

### 5.2. DML: execute thực hiện thay đổi

Với DML:

~~~sql
UPDATE lab_orders
SET amount = amount + 10
WHERE customer_id = :customer_id;
~~~

Execute thực hiện cập nhật các dòng phù hợp, có thể tạo undo/redo, giữ row lock và gặp chờ lock/I/O. API `executeUpdate()` thường trả về **số dòng bị tác động**, không tạo `ResultSet` để fetch như SELECT thông thường.

Thay đổi thuộc một **transaction**. Việc execute thành công chưa đồng nghĩa đã commit:

~~~java
connection.setAutoCommit(false);
try {
    String sql =
        "UPDATE lab_orders SET amount = amount + ? WHERE customer_id = ?";
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setBigDecimal(1, new BigDecimal("10.00"));
        ps.setLong(2, 7L);
        int count = ps.executeUpdate();
        System.out.println("Rows affected = " + count);
    }
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
~~~

Khi `autoCommit` bật, JDBC quản lý commit theo quy tắc hoàn tất statement; với tác vụ cần nhiều bước nhất quán, nên cấu hình transaction tường minh. Oracle DDL (`CREATE TABLE`, `ALTER TABLE`...) có ngữ nghĩa commit riêng, khác DML. Các lệnh PL/SQL có OUT parameter hoặc REF CURSOR có thể cần cách lấy kết quả khác.

### 5.3. Read consistency khi SELECT chạy lâu

Oracle dùng **multiversion read consistency** để SELECT thấy một tập dữ liệu nhất quán theo thời điểm snapshot và mức isolation. Khi một session đang fetch một truy vấn dài, session khác vẫn có thể commit những thay đổi; Oracle sử dụng **undo** khi cần để xây dựng phiên bản dữ liệu phù hợp cho truy vấn cũ.

Nếu một truy vấn phải đọc dữ liệu quá cũ mà thông tin undo cần thiết đã không còn, có thể xảy ra `ORA-01555: snapshot too old` trong quá trình đọc. Điều đó cho thấy một phần công việc kiểm tra/đọc nhất quán có thể diễn ra sau lời gọi execute, khi fetch.

## 6. Fetch: dữ liệu được lấy theo lô

Với SELECT, JDBC thường trả đối tượng `ResultSet`. Mỗi lần gọi `rs.next()`, client dịch chuyển tới dòng kế tiếp. Driver có thể đã **prefetch nhiều dòng** và giữ chúng trong bộ đệm phía client; một lần `rs.next()` **không bắt buộc** tạo một chuyến đi mạng.

~~~text
Oracle server                             Client / JDBC
──────────────────────────────────────────────────────────────
FETCH request ── 50 dòng ────────────────▶ Buffer 50 dòng
                                           rs.next() -> dòng 1
                                           ...
                                           rs.next() -> dòng 50
FETCH request ── 50 dòng nữa ───────────▶ Buffer 50 dòng
                                           ...
FETCH request ── hết dữ liệu ───────────▶ rs.next() -> false
──────────────────────────────────────────────────────────────
~~~

Con số 50 chỉ để minh họa. Kích thước lô thực tế tùy driver, loại cột, kích thước dữ liệu, row prefetch, fetch size và các yếu tố khác.

### 6.1. JDBC fetch size

~~~java
String sql = """
    SELECT order_id, customer_id, amount
    FROM lab_orders
    ORDER BY order_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setFetchSize(100);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong(1);
            long customerId = rs.getLong(2);
            BigDecimal amount = rs.getBigDecimal(3);
            // Xử lý một dòng ở phía Java
        }
    }
}
~~~

`setFetchSize(100)` là **gợi ý** cho JDBC driver; không bảo đảm đúng 100 dòng trong mọi round-trip. Một fetch size quá nhỏ có thể tăng số lượt mạng khi cần hàng chục nghìn dòng. Một fetch size quá lớn có thể tăng bộ nhớ client, độ trễ đến dòng đầu tiên hoặc dữ liệu tải thừa khi ứng dụng sớm dừng đọc.

**Fetch size không giới hạn số dòng kết quả của câu SQL.** Nếu ứng dụng chỉ muốn 20 dòng, hãy giới hạn ở SQL:

~~~sql
SELECT order_id, amount
FROM lab_orders
ORDER BY order_id
FETCH FIRST 20 ROWS ONLY;
~~~

Trong ví dụ trên, `FETCH FIRST 20 ROWS ONLY` là **row limiting clause** trong SQL. Nó khác với **giai đoạn fetch của cursor**. Câu lệnh phân trang cần `ORDER BY` ổn định để kết quả có thứ tự dự đoán được.

### 6.2. Vì sao fetch chậm?

Có nhiều nguyên nhân:

- Truy vấn trả hàng trăm nghìn dòng dù giao diện chỉ cần một trang.
- Mỗi dòng chứa quá nhiều cột, dữ liệu lớn hoặc LOB.
- Mạng có độ trễ cao và driver fetch theo lô quá nhỏ.
- Các phép toán sort, join, aggregate hoặc đọc block vẫn đang chạy để sản sinh các dòng tiếp theo.
- Ứng dụng ánh xạ đối tượng, ghi log, thực hiện xử lý phức tạp trên từng dòng.
- Chương trình gọi thêm một SQL cho mỗi dòng lấy được, gây **N+1 queries**.

Nên phân biệt **time to first row** với **time to consume all rows**. Một màn hình tìm kiếm cần hiện trang đầu nhanh khác với job ETL cần đọc toàn bộ tập dữ liệu hiệu quả.

### 6.3. Execute và fetch ảnh hưởng số lượt mạng thế nào?

Nếu ứng dụng gọi `prepareStatement()` một lần, `setLong()` hai lần, `executeQuery()` một lần và `rs.next()` 1.000 lần, không có nghĩa đã có 1.004 round-trip:

- `setXxx()` thường chỉ thay trạng thái giá trị bind ở client.
- Driver có thể kết hợp hoặc trì hoãn parse, bind, execute.
- `rs.next()` thường đọc bộ đệm đã fetch.
- Thao tác prefetch hoặc transaction có thể làm số lượt mạng khác đi.

Muốn đo số lượt mạng chính xác phải dùng số liệu hoặc công cụ quan sát của driver/session phù hợp, không suy từ số dòng Java code.

## 7. Thực hành đầy đủ trong SQL*Plus hoặc SQLcl

Ví dụ có thể chạy trên một schema ứng dụng trong PDB thực hành, với quyền tạo bảng. Tạo bảng:

~~~sql
CREATE TABLE lab_orders (
    order_id     NUMBER PRIMARY KEY,
    customer_id  NUMBER NOT NULL,
    amount       NUMBER(12,2) NOT NULL,
    created_at   DATE DEFAULT SYSDATE NOT NULL
);

INSERT INTO lab_orders (order_id, customer_id, amount)
VALUES (101, 7, 150.00);
INSERT INTO lab_orders (order_id, customer_id, amount)
VALUES (102, 7, 80.00);
INSERT INTO lab_orders (order_id, customer_id, amount)
VALUES (103, 8, 250.00);
INSERT INTO lab_orders (order_id, customer_id, amount)
VALUES (104, 7, 320.00);
COMMIT;
~~~

Khởi tạo bind và chạy câu lệnh:

~~~sql
VARIABLE v_customer_id NUMBER
VARIABLE v_min_amount NUMBER

EXEC :v_customer_id := 7
EXEC :v_min_amount := 100

SELECT order_id, amount
FROM lab_orders
WHERE customer_id = :v_customer_id
  AND amount >= :v_min_amount
ORDER BY order_id;
~~~

Kết quả mong đợi:

~~~text
ORDER_ID    AMOUNT
--------    ------
101         150
104         320
~~~

Không sửa SQL text, chỉ thay bind:

~~~sql
EXEC :v_customer_id := 8
EXEC :v_min_amount := 200

SELECT order_id, amount
FROM lab_orders
WHERE customer_id = :v_customer_id
  AND amount >= :v_min_amount
ORDER BY order_id;
~~~

Lúc này chỉ còn dòng `103`, amount `250`. Có thể thử `SET ARRAYSIZE 2` trong SQL*Plus để thay kích thước fetch theo mảng của client rồi chạy truy vấn nhiều dòng. `VARIABLE`, `EXEC` và `SET ARRAYSIZE` là lệnh của công cụ client SQL*Plus/SQLcl, không phải cú pháp SQL chuẩn của JDBC.

### Dòng thời gian tương ứng trong JDBC

~~~text
connection.prepareStatement(sql)
      │
      └── Chuẩn bị handle; parse thật có thể diễn ra hoặc bị trì hoãn
ps.setLong(1, ...)
ps.setBigDecimal(2, ...)
      │
      └── BIND ở tầng API: đặt giá trị và kiểu cho placeholder
ps.executeQuery()
      │
      └── EXECUTE; driver có thể gửi PARSE + BIND cùng lần giao tiếp
rs.next() ... rs.next()
      │
      └── FETCH từ buffer; cần thêm batch thì driver liên hệ server
rs.close(); ps.close()
      │
      └── Giải phóng tài nguyên dùng kết quả/statement
~~~

Java không phải gọi `parse()` như một API JDBC riêng. Đếm `prepareStatement()` cũng không đủ để xác định số hard parse thật phía Oracle vì driver/server có cơ chế cache và trì hoãn riêng.

## 8. Quan sát parse, execute, fetch trên Oracle

Một câu SQL thực tế có thể được quan sát thông qua thống kê cursor, execution plan và trace. Các view/công cụ quản trị bên dưới có thể yêu cầu quyền phù hợp; kết quả phản ánh tình trạng môi trường và lần chạy đã quan sát.

### 8.1. Thống kê từ `V$SQL`

~~~sql
SELECT
    sql_id,
    child_number,
    executions,
    parse_calls,
    fetches,
    rows_processed,
    buffer_gets,
    disk_reads,
    elapsed_time
FROM v$sql
WHERE sql_id = :target_sql_id
ORDER BY child_number;
~~~

| Cột | Cách hiểu |
|---|---|
| `SQL_ID` | Định danh SQL text |
| `CHILD_NUMBER` | Phân biệt child cursors của SQL |
| `EXECUTIONS` | Số lượt execute được ghi nhận |
| `PARSE_CALLS` | Số lần gọi parse; **không đồng nghĩa số hard parse** |
| `FETCHES` | Số lần fetch được ghi nhận; **không đồng nghĩa số dòng** |
| `ROWS_PROCESSED` | Tổng số dòng xử lý theo thống kê cursor; ý nghĩa tùy loại statement |
| `BUFFER_GETS` | Tổng lượt truy cập logical buffer |
| `DISK_READS` | Tổng số lượt đọc vật lý được ghi nhận |
| `ELAPSED_TIME` | Thời gian thực thi tích lũy (microsecond) theo thống kê Oracle |

Các con số này thường **tích lũy theo đời sống child cursor** và có thể gồm nhiều lần chạy, nhiều session. Một lần đọc `V$SQL` không tự động cho thông số duy nhất của request vừa đo. Cursor cũng có thể bị aged out/invalidated. Với RAC cần xét phạm vi từng instance; khi phù hợp có thể dùng view `GV$SQL`.

### 8.2. Plan ước lượng và hoạt động thực tế

`EXPLAIN PLAN` cho kế hoạch ước lượng theo ngữ cảnh phân tích; plan đã thực thi và các thống kê thực tế có thể xem bằng `DBMS_XPLAN.DISPLAY_CURSOR` khi có quyền:

~~~sql
SELECT /*+ gather_plan_statistics */
       order_id, amount
FROM lab_orders
WHERE customer_id = :v_customer_id
ORDER BY order_id;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(NULL, NULL, 'ALLSTATS LAST')
);
~~~

Thông tin có thể gồm `E-Rows` (dòng ước lượng), `A-Rows` (dòng thực tế), `Starts` và buffers. Nếu client chỉ fetch một phần rồi đóng, số dòng/công việc thực tế có thể phản ánh **phần đã tiêu thụ**, chứ không phải toàn bộ số dòng tiềm năng. Trong môi trường có nhiều SQL xen kẽ, nên chỉ định đúng `SQL_ID`/`CHILD_NUMBER` của câu cần phân tích.

### 8.3. SQL trace và TKPROF

SQL trace Oracle có thể hiển thị các call theo dạng:

~~~text
PARSE ...
EXEC  ...
FETCH ...
FETCH ...
FETCH ...
~~~

**TKPROF** tổng hợp thông tin từ trace, giúp so sánh số call parse/execute/fetch, CPU, elapsed time, I/O, rows và waits. Nếu session có quyền, có thể bật tracing cho một đoạn chạy thử:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        waits => TRUE,
        binds => FALSE
    );
END;
/

-- Chạy SQL mục tiêu và đọc hết các dòng kết quả.

BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE;
END;
/
~~~

`binds => FALSE` tránh chủ động ghi giá trị bind vào trace vì chúng có thể chứa dữ liệu nhạy cảm. Trace file được tạo trên server và có chi phí quan sát; cần quyền/phạm vi phù hợp, thường nhờ DBA hỗ trợ lấy file và chạy TKPROF.

### 8.4. Chẩn đoán đúng loại độ trễ

| Hiện tượng | Giai đoạn nên xem | Kiểm tra thực tế |
|---|---|---|
| CPU cao khi gửi rất nhiều SQL chỉ khác literal | Parse | Hard parse, shared pool, số SQL text, binding/caching |
| Một `UPDATE` chạy lâu hoặc chờ khóa | Execute | Plan, row lock, giao dịch, số dòng tác động |
| `executeQuery()` nhanh nhưng đọc `ResultSet` rất lâu | Fetch và row sources | Số dòng, fetch size, network, application processing, plan |
| Truy vấn chậm khi có một số giá trị bind | Parse/optimizer và execute | Selectivity, statistics, child cursor và plan thực tế |
| `rs.next()` gây thêm hàng nghìn SQL phụ | Ứng dụng và các statement lặp | N+1 queries; cân nhắc join hoặc batch query |

## 9. Lỗi thường gặp theo từng điểm trong vòng đời

Một exception tại `executeQuery()` không chắc chỉ xuất phát từ giai đoạn execute; driver có thể gửi parse/bind/execute trong cùng thao tác API.

| Thông báo/dấu hiệu | Nguồn khả dĩ | Nên kiểm tra |
|---|---|---|
| `ORA-00933` | Cú pháp SQL ở parse | Câu SQL Oracle, dấu phân cách, cú pháp driver gửi |
| `ORA-00942` | Tên đối tượng, schema/PDB hoặc quyền | User, `CURRENT_SCHEMA`, owner, grant, PDB |
| `ORA-01008` | Thiếu bind trong lần thực thi | Mọi placeholder đã có giá trị/kiểu phù hợp chưa? |
| `ORA-00001` | Vi phạm unique constraint khi DML | Key, dữ liệu đầu vào, ràng buộc |
| `ORA-00060` | Deadlock trong quá trình DML/giao dịch | Thứ tự khóa, các session liên quan |
| `ORA-01555` | Không đủ undo cho snapshot truy vấn | Truy vấn dài, undo retention, thay đổi đồng thời |
| `ORA-01000` | Quá nhiều cursor đang mở | Đóng `ResultSet`/`Statement`, quản lý statement cache |
| Nhiều fetch nhưng ít dòng trả về | Batch fetch, lọc và xử lý row sources | Kiểm tra plan/counters thay vì suy số dòng từ `FETCHES` |

**Lưu ý về `ORA-01000`:** đây là lỗi liên quan đến số cursor mở của session; mở statement/result set không đóng đúng cách là một nguyên nhân thường gặp, nhưng cũng cần đánh giá cơ chế cache và cấu hình `OPEN_CURSORS`.

## 10. Các hiểu lầm cần tránh

1. **“Mỗi lần chạy SQL đều hard parse.”** Không. Shared cursor, soft parse và cache giúp giảm công việc.
2. **“Gọi `prepareStatement()` tức server đã parse xong.”** Không chắc. Driver có thể trì hoãn parse.
3. **“Bind là thay chữ trong SQL rồi Oracle parse lại.”** Bind là truyền **giá trị có kiểu**, tách khỏi văn bản SQL.
4. **“Bind luôn tạo một plan duy nhất.”** Child cursor, bind peeking và các yếu tố optimizer có thể khiến plan khác nhau.
5. **“Execute SELECT là tính xong toàn bộ kết quả.”** Nhiều công việc tạo dòng xảy ra trong lúc fetch.
6. **“Một `rs.next()` luôn bằng một round-trip.”** Driver thường đệm kết quả theo lô.
7. **“Fetch size là giới hạn kết quả.”** Muốn giới hạn dòng phải dùng điều kiện hoặc row limiting clause trong SQL.
8. **“Đóng ResultSet làm Oracle xóa shared SQL.”** Shared cursor có thể tiếp tục ở library cache.
9. **“`PARSE_CALLS` cho biết số lần hard parse.”** Không; đây là số lần gọi parse nói chung.
10. **“Một lần execute chỉ có một lần fetch.”** Một SELECT có thể được fetch nhiều lô, hoặc client ngừng đọc sớm.

## 11. Câu hỏi và bài tập vận dụng

### Bài 1: SQL text và cursor sharing

Ứng dụng chạy ba SQL text với literal `customer_id = 1`, `= 2` và `= 3`. Tại sao thay bằng `customer_id = :id` thường hữu ích?

**Định hướng:** Giữ SQL text ổn định giúp Oracle có cơ hội reuse shared cursor; bind không đảm bảo duy nhất một child cursor/plan.

### Bài 2: Dừng đọc kết quả sớm

Một SELECT có khả năng trả 100.000 dòng, nhưng Java chỉ gọi `rs.next()` 10 lần rồi đóng ResultSet. Có thể kết luận Oracle đã gửi đủ 100.000 dòng không?

**Định hướng:** Không. Driver có thể prefetch hơn 10 dòng; một số operator có thể xử lý nhiều dữ liệu trước khi trả dòng đầu, nhưng không có quy tắc bắt buộc phải trả toàn bộ tập kết quả.

### Bài 3: Thực thi nhưng chưa commit

`executeUpdate()` trả về `1`. Ứng dụng đang ở chế độ `autoCommit = false` và sau đó gọi `rollback()`. Dữ liệu đã commit có thay đổi không?

**Định hướng:** Không. Lệnh đã thực thi và tác động một dòng trong transaction, nhưng thay đổi chưa commit có thể bị rollback.

### Bài 4: Fetch size và độ trễ

Một công việc ETL đọc 50.000 dòng qua mạng có độ trễ cao, `fetchSize = 1`. Tại sao nó có thể chậm dù parse/execute nhanh?

**Định hướng:** Số lần lấy dữ liệu qua mạng có thể rất cao; cần cân nhắc tăng fetch size, giảm dữ liệu trả về và đo thời gian toàn bộ vòng fetch.

### Bài 5: Plan khác nhau dù SQL giống nhau

Cùng SQL `WHERE customer_id = :id`, một giá trị trả một dòng, giá trị khác trả vài trăm nghìn dòng. Tại sao plan có thể khác?

**Định hướng:** Độ chọn lọc khác nhau, thống kê, bind peeking và adaptive cursor sharing có thể góp phần làm Oracle dùng child cursor/plan thích hợp.

## 12. Ghi nhớ bằng sơ đồ ngắn

~~~text
SQL TEXT
   |
   v
PARSE    Cú pháp, ngữ nghĩa, shared cursor, optimizer plan khi cần
   |
   v
BIND     Truyền giá trị tham số và kiểu, không đổi cú pháp SQL
   |
   v
EXECUTE  Khởi động SELECT hoặc thực hiện DML
   |       └── DML liên quan transaction, COMMIT / ROLLBACK
   v
FETCH    Đọc các dòng SELECT theo nhóm; xử lý row sources và I/O
   |
   v
CLOSE    Đóng tài nguyên dùng cursor ở phía client
~~~

Khi phân tích hiệu năng Oracle, hãy hỏi theo thứ tự: **Có hard parse quá nhiều không? Bind đúng kiểu và ổn định SQL text không? Execute tốn I/O hoặc chờ khóa không? Fetch có quá nhiều dòng hoặc quá nhiều round-trip không?** Việc tách bốn giai đoạn này giúp đọc đúng số liệu Oracle và chọn biện pháp tối ưu phù hợp cho ứng dụng Java/JDBC.

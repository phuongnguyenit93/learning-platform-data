# Quy tắc định danh, dấu phân cách và chữ hoa thường trong SQL đa hệ quản trị

> **Module:** Database SQL  
> **Chương:** SQL đa hệ quản trị  
> **Bài học:** Quy tắc định danh, dấu phân cách và chữ hoa thường

Một câu truy vấn có thể chạy đúng trên PostgreSQL nhưng lỗi khi chuyển sang Oracle vì tên bảng bị đổi chữ hoa thường; chạy trên SQL Server nhưng lỗi trên MySQL vì dùng dấu ngoặc vuông; hoặc tạo được bảng trên Windows nhưng không tìm thấy bảng trên Linux vì cách hệ điều hành và MySQL xử lý tên file/bảng khác nhau.

Những khác biệt này xoay quanh **identifier** — tên dùng để gọi đối tượng SQL như database, schema, table, column, view, index, constraint, sequence, procedure và alias.

Một identifier có thể được viết không có dấu phân cách (unquoted), ví dụ **don_hang**, hoặc có dấu phân cách (delimited/quoted), ví dụ **"don_hang"**, dấu backtick hoặc ngoặc vuông tùy DBMS.

Dấu phân cách ảnh hưởng cách parser nhận diện tên, cách bảo toàn chữ hoa/thường và cách xử lý ký tự đặc biệt. Nhưng **dấu phân cách không làm mọi hệ quản trị có cùng quy tắc phân biệt chữ hoa/thường**. PostgreSQL, MySQL, SQL Server, Oracle và SQLite có hành vi khác nhau; một số hành vi còn phụ thuộc phiên bản, cấu hình, collation và hệ điều hành.

Bài học này giải thích cách viết tên đối tượng có thể chuyển đổi tốt, cách đọc tên được tạo sẵn, cách định danh schema/table/column, và cách xây dựng SQL động an toàn khi tên đối tượng đến từ cấu hình hoặc metadata.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt identifier với literal/value trong SQL.
2. Giải thích regular identifier và delimited identifier.
3. Nhận biết vai trò của dấu nháy kép, backtick và ngoặc vuông.
4. Hiểu quy tắc chuyển chữ của tên không đặt trong dấu phân cách.
5. So sánh case sensitivity giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite.
6. Phân biệt việc so sánh tên đối tượng với collation khi so sánh giá trị dữ liệu.
7. Hiểu từ khóa dành riêng và lý do không nên dùng chúng làm tên bảng/cột.
8. Biết các giới hạn độ dài identifier và rủi ro bị cắt tên.
9. Hiểu khác biệt về Unicode, encoding và chuẩn hóa ký tự trong tên.
10. Viết tên database/schema/table/column có tính nhất quán.
11. Hiểu cách định danh đầy đủ và cách DBMS tìm đối tượng theo schema mặc định/search path.
12. Chuyển đổi tên có dấu phân cách từ một DBMS sang DBMS khác.
13. Tránh xung đột tên khi migration từ môi trường phân biệt hoa/thường sang môi trường không phân biệt.
14. Dùng PreparedStatement đúng chỗ và nhận ra vì sao không thể bind table name như một value.
15. Tạo SQL động với identifier được kiểm soát bằng allowlist và quy tắc quote phù hợp.
16. Xử lý metadata JDBC, ORM, alias và tên cột có chữ hoa/thường.
17. Lập checklist chuyển hệ và kiểm thử trên đúng phiên bản/cấu hình.

## 2. Identifier là gì?

Identifier là tên định danh một đối tượng hoặc thành phần trong câu SQL.

Ví dụ:

~~~sql
SELECT ten_khach_hang, email
FROM khach_hang
WHERE id = 100;
~~~

Trong câu trên:
- ten_khach_hang là tên cột.
- email là tên cột.
- khach_hang là tên bảng.
- id là tên cột.
- 100 là literal số, không phải identifier.

Một ví dụ khác:

~~~sql
UPDATE don_hang
SET trang_thai = 'PAID'
WHERE ma_don = 'ORD-001';
~~~

don_hang, trang_thai, ma_don là identifiers; 'PAID' và 'ORD-001' là string literals.

### 2.1. Vì sao cần phân biệt?

SQL xử lý tên đối tượng và giá trị theo hai cơ chế khác nhau:

- **Identifier** thường được parser phân giải thành bảng/cột/index/schema khi biên dịch câu lệnh.
- **Value** là dữ liệu được truyền vào khi thực thi; có thể bind bằng parameter marker.

Ví dụ JDBC:

~~~java
String sql = """
    SELECT id, ten_khach_hang
    FROM khach_hang
    WHERE email = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
    try (ResultSet rs = ps.executeQuery()) {
        // Xu ly ket qua.
    }
}
~~~

Dấu ? thay cho **giá trị email**, không thay cho tên bảng hoặc tên cột.

### 2.2. Không thể bind table name như bind value

Ví dụ sau không có nghĩa “đọc bảng có tên do parameter cung cấp”:

~~~sql
SELECT * FROM ?;
~~~

DBMS/driver không xem parameter đó là identifier. Parameter marker biểu diễn expression/value trong vị trí được phép, không phải token cấu trúc SQL.

Nếu cần chọn bảng động, phải tạo SQL từ một identifier đã được kiểm soát và quote theo DBMS. Không nối thẳng input người dùng vào câu lệnh.

## 3. Regular identifier và delimited identifier

Hai dạng phổ biến:

**Regular identifier (không đặt trong dấu phân cách):**

~~~sql
SELECT ten_khach_hang
FROM khach_hang;
~~~

Tên thường tuân theo tập ký tự và quy tắc lexical của DBMS. Một tên như don_hang thường dễ chuyển hệ.

**Delimited identifier (đặt trong dấu phân cách):**

~~~sql
SELECT "ten khach hang"
FROM "bang khach hang";
~~~

Dấu phân cách cho phép dùng khoảng trắng, từ khóa hoặc ký tự đặc biệt theo quy tắc hệ quản trị. Nó cũng ảnh hưởng cách bảo toàn chữ hoa/thường.

### 3.1. Dấu phân cách phổ biến

| DBMS | Dấu phân cách identifier thường dùng | Ví dụ |
|---|---|---|
| PostgreSQL | Dấu nháy kép | "Order" |
| Oracle | Dấu nháy kép | "Order" |
| SQL Server | Ngoặc vuông; dấu nháy kép khi QUOTED_IDENTIFIER ON | [Order], "Order" |
| MySQL | Backtick; dấu nháy kép khi bật ANSI_QUOTES | backtick Order backtick, "Order" |
| SQLite | Dấu nháy kép; cũng chấp nhận một số dạng tương thích | "Order", backtick Order backtick, [Order] |

Dấu nháy đơn dùng cho **string literal**, không phải cách viết identifier chuẩn. Một số DBMS có hành vi tương thích cũ với dấu nháy đơn hoặc dấu nháy kép, nhưng không nên dựa vào hành vi đó.

### 3.2. Quote không phải trang trí

Hai tên có thể khác nhau:

~~~sql
CREATE TABLE don_hang (...);
CREATE TABLE "Don_Hang" (...);
~~~

Trong PostgreSQL và Oracle, đây có thể là hai identifier khác nhau theo quy tắc fold/case. Khi đã tạo tên có dấu phân cách, mọi truy vấn phải tham chiếu đúng spelling/case theo DBMS đó.

### 3.3. Tên không có khoảng trắng thường tốt hơn

Tên như "Chi tiet don hang" có thể dùng được nhưng phải quote mỗi lần, dễ phát sinh lỗi ở ORM, migration, SQL động và công cụ quản trị. Nên chọn:

~~~sql
chi_tiet_don_hang
~~~

Tên rõ ràng và không cần quote thường có tính khả chuyển cao hơn.

## 4. Quy tắc chữ hoa/thường: khái niệm quan trọng

Cần tách ba việc:

1. **Input spelling:** cách bạn viết identifier trong câu SQL.
2. **Identifier folding/storage:** DBMS chuẩn hóa hoặc lưu cách viết đó ra sao.
3. **Name comparison/resolution:** DBMS so sánh tên khi tìm đối tượng như thế nào.

Ví dụ bạn viết Don_Hang, DBMS có thể:
- Chuyển thành chữ thường.
- Chuyển thành chữ hoa.
- Lưu spelling và so sánh không phân biệt hoa/thường.
- Lưu spelling nhưng cách so sánh còn phụ thuộc collation hoặc cấu hình.

Vì vậy, không có quy tắc chung “SQL không phân biệt hoa thường” áp dụng cho tất cả identifiers ở mọi DBMS.

### 4.1. Bảng tổng quan

| DBMS | Identifier không quote | Identifier quote | Quy tắc đáng chú ý |
|---|---|---|---|
| PostgreSQL | Fold về chữ thường | Giữ chính xác case | "Don_Hang" khác don_hang |
| Oracle | Fold về chữ hoa | Giữ chính xác case | "Don_Hang" khác DON_HANG |
| SQL Server | Theo collation của database/catalog | Delimiter không tự ép case-sensitive | Collation CI/CS quyết định so sánh |
| MySQL | Database/table phụ thuộc lower_case_table_names và nền tảng | Backtick không loại bỏ khác biệt cấu hình | Cần giữ tên nhất quán giữa OS |
| SQLite | Không phân biệt ASCII case cho identifier | Quote không biến tên thành case-sensitive | TableA và tablea cùng identifier trong thông thường |

Đây là tổng quan. Chi tiết còn phụ thuộc phiên bản, collation, SQL mode, database compatibility và cấu hình khởi tạo.

## 5. PostgreSQL: unquoted fold về lowercase

PostgreSQL chuyển identifier **không quote** về chữ thường.

Các câu sau tham chiếu cùng tên:

~~~sql
CREATE TABLE Don_Hang (
    ID BIGINT PRIMARY KEY,
    Ma_Don TEXT
);
~~~

~~~sql
SELECT id, ma_don
FROM don_hang;
~~~

PostgreSQL xem tên không quote như đã viết thành chữ thường. Do đó Don_Hang, DON_HANG và don_hang không quote đều được phân giải về don_hang.

### 5.1. Quoted identifier giữ case

~~~sql
CREATE TABLE "Don_Hang" (
    "ID" BIGINT PRIMARY KEY,
    "Ma_Don" TEXT
);
~~~

Muốn truy vấn phải dùng chính xác:

~~~sql
SELECT "ID", "Ma_Don"
FROM "Don_Hang";
~~~

Các câu sau không tương đương:

~~~sql
SELECT id FROM "Don_Hang";
~~~

~~~sql
SELECT "id" FROM "Don_Hang";
~~~

Tên cột được tạo là "ID", không phải id hoặc "id".

### 5.2. Lỗi phổ biến khi dùng ORM

Một migration tạo bảng bằng tên quote "Customer"; ORM lại phát SQL không quote:

~~~sql
SELECT id FROM Customer;
~~~

PostgreSQL tìm bảng customer chữ thường và không tìm thấy "Customer".

Giải pháp:
- Chọn tên lowercase không quote cho schema mới.
- Hoặc cấu hình ORM luôn quote đúng tên.
- Không trộn hai quy ước trong cùng schema.

### 5.3. Identifier length

PostgreSQL mặc định giới hạn identifier ở **63 bytes** (giá trị phụ thuộc NAMEDATALEN khi build). Giới hạn là bytes, không phải luôn là số ký tự Unicode.

Tên dài hơn có thể bị cắt ở server. Hai tên khác nhau ở phần sau giới hạn có thể trở thành cùng tên sau khi cắt, dẫn đến collision hoặc tham chiếu sai.

Ví dụ minh họa:

~~~text
customer_order_history_archive_2026_version_a
customer_order_history_archive_2026_version_b
~~~

Nếu tên vượt giới hạn và khác nhau chỉ ở phần bị cắt, cần rút gọn tên có chủ đích.

### 5.4. Schema và search_path

PostgreSQL tìm bảng không ghi schema theo search_path:

~~~sql
SHOW search_path;
~~~

Nếu cả public.khach_hang và app.khach_hang tồn tại, truy vấn:

~~~sql
SELECT * FROM khach_hang;
~~~

sẽ chọn đối tượng đầu tiên tìm thấy trong search_path.

Trong code ứng dụng và migration quan trọng, có thể ghi rõ:

~~~sql
SELECT * FROM app.khach_hang;
~~~

Search_path cũng có ý nghĩa bảo mật: không đặt schema mà người dùng không tin cậy có thể tạo function/table lên trước schema đáng tin trong đường tìm kiếm của ứng dụng.

## 6. Oracle: unquoted fold về UPPERCASE

Oracle chuyển identifier không quote về chữ hoa.

~~~sql
CREATE TABLE Don_Hang (
    ID NUMBER PRIMARY KEY,
    Ma_Don VARCHAR2(40)
);
~~~

Tên được tạo theo dạng không quote tương ứng với DON_HANG, ID và MA_DON.

Các cách viết không quote sau tham chiếu cùng đối tượng:

~~~sql
SELECT id, ma_don FROM don_hang;
~~~

~~~sql
SELECT ID, MA_DON FROM DON_HANG;
~~~

### 6.1. Quoted identifier giữ case

~~~sql
CREATE TABLE "Don_Hang" (
    "Id" NUMBER PRIMARY KEY,
    "Ma_Don" VARCHAR2(40)
);
~~~

Tham chiếu:

~~~sql
SELECT "Id", "Ma_Don"
FROM "Don_Hang";
~~~

Tên "Don_Hang" là tên phân biệt case. Viết DON_HANG không quote sẽ tìm DON_HANG, không phải "Don_Hang".

### 6.2. Tránh tạo tên mixed-case bằng quote

~~~sql
CREATE TABLE "OrderItem" (...);
~~~

buộc mọi truy vấn, migration, ORM và công cụ phải quote đúng case. Điều này thường làm tăng chi phí tích hợp. Nếu không có lý do đặc biệt, hãy dùng tên không quote như ORDER_ITEM.

### 6.3. Giới hạn độ dài Oracle

Oracle hỗ trợ identifier tối đa **128 bytes cho phần lớn tên đối tượng ở các phiên bản hiện đại (12.2 trở lên)**. Với phiên bản cũ hoặc database có COMPATIBLE setting thấp, giới hạn phổ biến là **30 bytes**. Một số loại identifier có quy tắc riêng.

Nếu ứng dụng phải chạy trên Oracle cũ, nên chọn tên không vượt 30 bytes cho các loại đối tượng liên quan; nếu chỉ hỗ trợ bản mới, ghi rõ minimum version và kiểm tra loại identifier cụ thể.

### 6.4. Schema trong Oracle

Schema thường gắn với user/owner. Truy vấn:

~~~sql
SELECT * FROM SALES.DON_HANG;
~~~

tham chiếu đối tượng DON_HANG trong schema SALES.

Tên schema không phải database.schema như SQL Server; database link có cú pháp riêng, ví dụ tên đối tượng kèm @database_link.

## 7. MySQL: backtick và lower_case_table_names

MySQL thường dùng backtick để quote identifier:

~~~sql
CREATE TABLE `don_hang` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `ma_don` VARCHAR(40) NOT NULL
);
~~~

Không quote cũng hợp lệ với tên thông thường:

~~~sql
SELECT id, ma_don
FROM don_hang;
~~~

### 7.1. Dấu nháy kép trong MySQL

Theo mặc định, dấu nháy kép thường biểu diễn string literal:

~~~sql
SELECT "don_hang";
~~~

Không được mặc định đây là identifier.

Khi SQL mode **ANSI_QUOTES** bật, dấu nháy kép được dùng để quote identifiers và không còn là cách viết string literal thông thường.

~~~sql
SET sql_mode = 'ANSI_QUOTES';
~~~

Mode thực tế có thể bao gồm nhiều giá trị khác; không ghi đè toàn bộ sql_mode trong production chỉ để minh họa. Khi viết SQL đa hệ, backtick là cú pháp MySQL đặc thù; dấu nháy kép chỉ dùng cho identifier khi mode được cấu hình tương ứng.

### 7.2. lower_case_table_names

Hành vi tên database và table của MySQL chịu ảnh hưởng bởi biến **lower_case_table_names** và môi trường filesystem/OS.

Các giá trị thường gặp:

| Giá trị | Mô hình tổng quát |
|---:|---|
| 0 | Lưu tên theo spelling khai báo và so sánh case-sensitive; thường là cấu hình Unix/Linux mặc định |
| 1 | Lưu tên dạng lowercase và so sánh không phân biệt case; thường gặp trên Windows |
| 2 | Lưu theo spelling khai báo nhưng tra cứu theo lowercase; từng được dùng trên một số hệ filesystem case-insensitive |

Khả năng dùng từng giá trị phụ thuộc hệ điều hành, filesystem và quy tắc khởi tạo server. Không nên đổi biến này tùy tiện trên data directory đã được tạo với cấu hình khác; hãy kiểm tra tài liệu đúng phiên bản.

Ví dụ một môi trường có thể phân biệt:

~~~sql
SELECT * FROM Don_Hang;
~~~

và:

~~~sql
SELECT * FROM don_hang;
~~~

nhưng môi trường khác lại coi chúng là cùng bảng.

### 7.3. Column names và table names

Không suy luận rằng tất cả loại identifier MySQL đều có cùng case rules. Database/table names, column names, aliases, routine names và trigger names có thể có quy tắc riêng. Khác biệt filesystem chủ yếu làm tên database/table trở nên nhạy cảm theo môi trường.

### 7.4. Quy tắc triển khai

- Dùng lowercase cho database/table names.
- Dùng cùng spelling ở mọi migration.
- Không dựa vào khác biệt hoa/thường để tạo hai bảng.
- Chạy integration tests trên đúng OS và cấu hình MySQL production.
- Không mang schema được tạo trên Windows lên Linux mà chưa kiểm tra tên đối tượng.

### 7.5. Giới hạn độ dài

MySQL có giới hạn theo từng loại identifier; database/table/column/index thường có giới hạn 64 ký tự, nhưng alias và một số đối tượng khác có giới hạn riêng. Đừng áp một con số duy nhất cho mọi loại tên; tra tài liệu phiên bản và loại đối tượng.

## 8. SQL Server: collation và QUOTED_IDENTIFIER

SQL Server hỗ trợ hai kiểu delimiters phổ biến:

~~~sql
SELECT * FROM [Order];
~~~

và:

~~~sql
SELECT * FROM "Order";
~~~

Dấu ngoặc vuông là cách SQL Server-specific. Dấu nháy kép được hiểu là delimited identifier khi **QUOTED_IDENTIFIER ON**.

### 8.1. QUOTED_IDENTIFIER

Có thể kiểm tra/cấu hình theo phiên làm việc:

~~~sql
SET QUOTED_IDENTIFIER ON;
~~~

Khi ON, "Order" là identifier. Khi OFF, dấu nháy kép có thể được hiểu như string delimiter theo hành vi T-SQL cũ; không nên dựa vào mode OFF trong code mới.

SQL Server thường yêu cầu QUOTED_IDENTIFIER ON cho một số tính năng như indexed views/computed-column indexes và các đối tượng khác theo quy tắc riêng. Dùng ON nhất quán trong scripts.

### 8.2. Bracket quoting

~~~sql
SELECT [OrderId], [Customer Name]
FROM [sales].[Order];
~~~

Nếu tên chứa dấu ngoặc vuông đóng, cần escape bằng cách nhân đôi dấu ngoặc vuông theo quy tắc SQL Server:

~~~sql
SELECT [Column]]Name]
FROM [dbo].[SomeTable];
~~~

Trong SQL động, dùng QUOTENAME() để quote identifier theo SQL Server thay vì tự nối chuỗi không an toàn.

### 8.3. Case sensitivity theo collation

SQL Server phân giải tên đối tượng theo quy tắc collation của catalog/database liên quan. Collation có thể:
- CI: case-insensitive.
- CS: case-sensitive.
- AI: accent-insensitive.
- AS: accent-sensitive.

Ví dụ trên collation CI, tên table Customer và customer thường được coi như cùng tên. Trên collation CS, case có thể ảnh hưởng việc phân giải.

**Dấu ngoặc vuông hoặc dấu nháy kép không tự biến collation CI thành CS.** Quote giúp phân định token/tên, không phải công tắc case sensitivity.

### 8.4. Giới hạn độ dài

SQL Server giới hạn identifier thông thường tối đa 128 ký tự. Local temporary table names có giới hạn hữu hiệu thấp hơn do SQL Server thêm suffix nội bộ. Một số đối tượng/alias có quy tắc cụ thể; kiểm tra loại identifier.

### 8.5. Tên đầy đủ

SQL Server hỗ trợ tên dạng:

~~~sql
[server].[database].[schema].[object]
~~~

Không phải mọi ngữ cảnh đều cho phép bốn phần; linked servers, quyền và loại câu lệnh có quy tắc riêng. Tên hai phần thường là schema.object trong database hiện tại.

## 9. SQLite: quote linh hoạt nhưng identifier không phân biệt ASCII case

SQLite chấp nhận dấu nháy kép theo chuẩn:

~~~sql
CREATE TABLE "don_hang" (
    "id" INTEGER PRIMARY KEY,
    "ma_don" TEXT NOT NULL
);
~~~

Nó cũng chấp nhận một số dạng tương thích như backtick và ngoặc vuông:

~~~sql
SELECT `id` FROM [don_hang];
~~~

Nên ưu tiên dấu nháy kép khi thực sự cần quote identifier, để gần chuẩn SQL hơn.

### 9.1. Case-insensitive identifiers

SQLite coi identifier không phân biệt ASCII chữ hoa/thường trong cách phân giải thông thường. Ví dụ Don_Hang và don_hang cùng chỉ một đối tượng.

Đây là quy tắc identifier, không phải quy tắc so sánh giá trị text trong bảng. So sánh dữ liệu vẫn phụ thuộc collation và biểu thức.

### 9.2. Không dùng quote để tạo hai bảng chỉ khác case

Không thể dựa vào:

~~~sql
CREATE TABLE "Customer" (...);
CREATE TABLE "customer" (...);
~~~

để tạo hai bảng độc lập trong SQLite thông thường. Identifier được xem là cùng tên theo quy tắc case-insensitive.

### 9.3. Database qualifier

SQLite thường dùng:
- main.table_name cho database chính.
- temp.table_name cho temporary database.
- alias.table_name cho database được ATTACH.

Đây không phải hệ schema nhiều tầng như PostgreSQL hay SQL Server.

## 10. Dấu phân cách và literal: bảng so sánh

| Cách viết | Ý nghĩa SQL chuẩn/điển hình | Lưu ý |
|---|---|---|
| 'PAID' | String literal | Dùng dấu nháy đơn |
| 100 | Numeric literal | Không quote |
| "order" | Delimited identifier | Chuẩn SQL; SQL Server cần QUOTED_IDENTIFIER ON, MySQL cần ANSI_QUOTES |
| backtick order backtick | Identifier | MySQL; SQLite cũng chấp nhận vì tương thích |
| [order] | Identifier | SQL Server; SQLite cũng chấp nhận vì tương thích |
| N'Xin chào' | Unicode string literal | T-SQL-specific prefix |
| :order_id | Bind placeholder trong một số client/DB | Không phải identifier |
| ? | Positional parameter marker | JDBC/SQLite/MySQL/driver theo hỗ trợ |
| $1 | Positional parameter của PostgreSQL protocol/SQL client | Không phải cú pháp JDBC phổ thông |
| @p1 | T-SQL variable/parameter | Không phải identifier bảng |

### 10.1. Dấu nháy đơn không phải cách quote tên bảng

Sai hoặc không portable:

~~~sql
SELECT * FROM 'don_hang';
~~~

Một DBMS có thể coi 'don_hang' là string literal, không phải table name. SQLite từng có một số compatibility quirks trong cách diễn giải token, nhưng không dựa vào chúng.

Đúng:

~~~sql
SELECT * FROM don_hang;
~~~

hoặc quote đúng dialect khi cần:

~~~sql
SELECT * FROM "don_hang";
~~~

## 11. Từ khóa dành riêng và tên đối tượng

Các từ như SELECT, TABLE, ORDER, GROUP, USER, INDEX, KEY, VALUE, LIMIT, OFFSET có thể là reserved hoặc nonreserved tùy DBMS/version/context.

Ví dụ tên bảng:

~~~sql
CREATE TABLE order (...);
~~~

có thể lỗi vì ORDER là keyword.

Nếu bắt buộc dùng tên đó, phải quote theo dialect:

~~~sql
-- PostgreSQL, Oracle, SQLite:
CREATE TABLE "order" (...);
~~~

~~~sql
-- MySQL:
CREATE TABLE `order` (...);
~~~

~~~sql
-- SQL Server:
CREATE TABLE [order] (...);
~~~

Nhưng cách tốt hơn thường là đổi tên:

~~~sql
CREATE TABLE sales_order (...);
~~~

### 11.1. Từ khóa thay đổi theo phiên bản

Một tên không reserved ở bản DBMS cũ có thể trở thành keyword ở bản mới. Một tính năng mới thêm từ khóa có thể khiến migration cũ lỗi sau khi nâng cấp.

Do đó:
- Tránh dùng tên trùng keyword phổ biến.
- Kiểm tra keyword list của DBMS đích/version.
- Nếu cần portability rộng, chọn tên nghiệp vụ rõ như sales_order, user_account, group_member.
- Không dùng quoting để che một naming convention kém.

### 11.2. Identifier giống tên hàm

Tên như user, rank, value, position, current_date hoặc function names có thể gây mơ hồ tùy DBMS. Tránh đặt cột trùng các tên đặc biệt nếu không có lợi ích rõ.

## 12. Giới hạn độ dài identifier

Độ dài không thống nhất giữa hệ và loại đối tượng:

| DBMS | Giới hạn thường gặp | Ghi chú |
|---|---|---|
| PostgreSQL | 63 bytes mặc định | NAMEDATALEN-1; có thể cắt tên dài |
| Oracle | 128 bytes trên bản hiện đại; 30 bytes ở cấu hình/version cũ | COMPATIBLE và loại đối tượng có thể ảnh hưởng |
| SQL Server | 128 ký tự cho identifiers thông thường | Local temp table có giới hạn hữu hiệu thấp hơn |
| MySQL | Thường 64 ký tự cho database/table/column/index | Loại identifier khác có thể khác |
| SQLite | Phụ thuộc build/parser limits | Không nên dựa vào tên cực dài; kiểm tra runtime/build |

### 12.1. Bytes và characters không giống nhau

Tên Unicode có thể dùng nhiều byte cho một ký tự UTF-8. Tên có chữ tiếng Việt có dấu có thể vượt giới hạn byte trước khi đạt số lượng ký tự nhìn thấy.

Đừng đo độ dài identifier chỉ bằng số ký tự hiển thị trong editor.

### 12.2. Truncation tạo collision

Nếu DBMS cắt tên dài, hai tên:

~~~text
ix_customer_order_archive_for_region_north
ix_customer_order_archive_for_region_south
~~~

có thể trùng sau khi bị cắt nếu phần khác nhau nằm ngoài giới hạn.

Nên tạo tên ngắn có chủ đích, dùng suffix phân biệt trước ngưỡng và kiểm tra metadata sau DDL.

### 12.3. Quy tắc cross-version

Nếu sản phẩm cần hỗ trợ Oracle cũ có giới hạn 30 bytes, chọn naming policy dưới ngưỡng đó cho các loại đối tượng liên quan. Nếu target chỉ gồm hệ hiện đại, có thể chọn giới hạn rộng hơn nhưng phải công bố minimum versions.

## 13. Unicode và tên đối tượng

Một số DBMS cho phép identifier chứa Unicode. Tuy nhiên, khả năng parser, giới hạn bytes, normalization và công cụ quản trị khác nhau.

Tên:

~~~text
khach_hang
khách_hàng
khach_hang_đã_xóa
~~~

có thể hợp lệ ở một hệ, nhưng khó chuyển qua client, shell script, ORM, migration tool hoặc filesystem.

### 13.1. Unicode normalization

Hai chuỗi có thể nhìn giống nhau nhưng có cách mã hóa Unicode khác:
- Ký tự có dấu được biểu diễn bằng một code point dựng sẵn.
- Hoặc chữ cái + combining mark.

Tên đối tượng có thể không được tự chuẩn hóa giống nhau giữa DBMS/toolchain. Khi tạo tên từ metadata ngoài, cần canonicalize hoặc từ chối tên không theo policy.

### 13.2. Case folding Unicode

Case folding của ASCII, tiếng Thổ Nhĩ Kỳ, tiếng Đức và các ngôn ngữ khác có quy tắc phức tạp. Không giả định mọi DBMS dùng cùng Unicode version hoặc cùng cách chuyển hoa/thường.

### 13.3. Khuyến nghị

Đối với schema cần portability:
- Dùng ASCII lowercase.
- Dùng underscore.
- Tránh dấu tiếng Việt trong identifier.
- Tránh khoảng trắng và ký tự đặc biệt.
- Giữ tên ngắn.
- Để nội dung hiển thị có dấu trong dữ liệu, không trong tên cột/bảng.

Tên dữ liệu và tên đối tượng có yêu cầu khác nhau; không hy sinh Unicode trong dữ liệu chỉ vì muốn identifier đơn giản.

## 14. Quy tắc đặt tên có tính khả chuyển

Một convention dễ chuyển hệ:

| Thành phần | Quy ước gợi ý | Ví dụ |
|---|---|---|
| Database | lowercase ASCII | sales_app |
| Schema | lowercase ASCII | sales |
| Table | snake_case | sales_order |
| Column | snake_case | created_at |
| Primary key | pk_<table> | pk_sales_order |
| Foreign key | fk_<child>_<parent> | fk_order_customer |
| Unique | uq_<table>_<column> | uq_customer_email |
| Check | ck_<table>_<rule> | ck_order_total_nonnegative |
| Index | ix_<table>_<columns> | ix_order_customer_created |
| Sequence | seq_<table>_<column> | seq_order_id |
| View | v_<purpose> hoặc tên nghiệp vụ rõ | v_open_orders |
| Procedure | prefix theo policy | usp_close_order |
| Trigger | trg_<table>_<event> | trg_order_audit |

Đây là convention, không phải luật bắt buộc. Tránh prefix sp_ cho stored procedure trong SQL Server nếu tổ chức có quy định riêng vì tên có thể va chạm với system stored procedures và ảnh hưởng phân giải; có thể chọn usp_ hoặc prefix theo schema.

### 14.1. Một bộ quy tắc ngắn

1. Bắt đầu bằng chữ cái.
2. Chỉ dùng a-z, 0-9 và underscore.
3. Dùng lowercase.
4. Không dùng khoảng trắng, dấu gạch ngang, dấu chấm trong một identifier đơn.
5. Không dùng từ khóa.
6. Không quote nếu không cần.
7. Đặt tên constraint/index rõ ràng.
8. Giữ tên trong giới hạn thấp nhất của DBMS mục tiêu.
9. Không tạo hai tên chỉ khác case.
10. Dùng tên schema đầy đủ trong SQL quan trọng.

### 14.2. Singular hay plural?

Có thể dùng sales_order hoặc orders. Điều quan trọng là thống nhất trong toàn schema và tài liệu. Không có quy tắc SQL phổ quát bắt buộc bảng phải số ít hay số nhiều.

### 14.3. Tên có ý nghĩa nghiệp vụ

Ưu tiên:

~~~text
customer_email
order_created_at
invoice_due_date
~~~

hơn:

~~~text
c1
dt2
val
data
~~~

Tên rõ giúp code, logs, metadata và migration dễ đọc hơn.

## 15. Schema, catalog và tên đầy đủ

Một đối tượng có thể được gọi bằng tên đơn giản hoặc tên có qualifier.

### 15.1. PostgreSQL

~~~sql
SELECT * FROM sales.customer;
~~~

Cấu trúc cơ bản là schema.table trong database đang kết nối. PostgreSQL không hỗ trợ tên ba phần database.schema.table để truy vấn database khác như SQL Server; cần kết nối khác hoặc cơ chế như FDW/dblink.

### 15.2. MySQL

~~~sql
SELECT * FROM sales_db.customer;
~~~

Database và schema là hai cách gọi tương đương trong MySQL. Không có namespace schema lồng bên trong database như PostgreSQL/SQL Server.

### 15.3. SQL Server

~~~sql
SELECT * FROM [SalesDB].[sales].[Customer];
~~~

Cấu trúc thường là database.schema.object; có thể có server ở phần đầu trong trường hợp hỗ trợ:

~~~sql
SELECT * FROM [LinkedServer].[SalesDB].[sales].[Customer];
~~~

### 15.4. Oracle

~~~sql
SELECT * FROM SALES.CUSTOMER;
~~~

Schema thường gắn với user/owner. Truy cập database khác có thể qua database link:

~~~sql
SELECT * FROM SALES.CUSTOMER@REMOTE_DB;
~~~

### 15.5. SQLite

~~~sql
SELECT * FROM main.customer;
~~~

Có thể ATTACH database và đặt alias:

~~~sql
ATTACH DATABASE 'archive.db' AS archive;
SELECT * FROM archive.customer;
~~~

SQLite không có schema namespace nhiều tầng giống PostgreSQL.

### 15.6. Bảng tổng hợp

| DBMS | Dạng qualifier thường gặp | Ý nghĩa |
|---|---|---|
| PostgreSQL | schema.table | Schema trong database kết nối |
| MySQL | database.table | Database/schema synonym |
| SQL Server | database.schema.object | Database + schema + object |
| Oracle | schema.object | Owner/schema + object |
| SQLite | database_alias.table | main/temp/attached database |

Không chuyển chuỗi database.schema.table giữa các hệ bằng cách thay dấu quote đơn thuần. Cấu trúc namespace thực sự khác nhau.

## 16. Name resolution: DBMS tìm đối tượng nào?

Khi viết:

~~~sql
SELECT * FROM customer;
~~~

DBMS phải tìm bảng customer ở namespace mặc định hoặc đường tìm kiếm hiện hành.

Cơ chế:
- PostgreSQL: search_path.
- MySQL: current database.
- SQL Server: default schema, database context và quy tắc phân giải tên.
- Oracle: current schema, private/public synonyms và object resolution.
- SQLite: database alias/namespace như main, temp và attached DB.

### 16.1. Hai schema có cùng tên bảng

Giả sử:
- sales.customer
- support.customer

Câu:

~~~sql
SELECT * FROM customer;
~~~

có thể lấy bảng khác nhau tùy current schema/search path/default database.

Để rõ ràng:

~~~sql
SELECT * FROM sales.customer;
~~~

hoặc qualifier tương ứng DBMS.

### 16.2. Default schema không phải quyền truy cập

Một bảng có thể được tìm thấy theo schema nhưng người dùng không có SELECT permission. Ngược lại, quyền truy cập không bảo đảm tên đơn giản sẽ phân giải đến đúng đối tượng.

Cần kiểm tra cả:
- Object resolution.
- Ownership.
- GRANT/role.
- Search path/default schema.
- Row-level security nếu có.

### 16.3. Search path và security

Nếu người dùng không tin cậy có thể tạo function/table trong schema đứng trước schema ứng dụng trong search_path, một truy vấn không qualify có thể gọi nhầm đối tượng. Trong PostgreSQL, quản lý CREATE privilege và search_path cẩn thận; schema-qualify những hàm nhạy cảm khi phù hợp.

## 17. Alias và case sensitivity

Alias đặt tên tạm cho cột hoặc bảng:

~~~sql
SELECT
    c.customer_id AS customer_id,
    c.display_name AS display_name
FROM customer AS c;
~~~

Alias không tạo một cột vật lý mới. Nó định danh output column hoặc table reference trong query.

### 17.1. Alias có quote

~~~sql
SELECT total_amount AS "Total Amount"
FROM sales_order;
~~~

Kết quả có label chứa khoảng trắng. Client/ORM phải đọc đúng column label.

Tên portable hơn:

~~~sql
SELECT total_amount AS total_amount
FROM sales_order;
~~~

### 17.2. Alias mixed-case

~~~sql
SELECT total_amount AS "TotalAmount"
FROM sales_order;
~~~

Trong PostgreSQL, alias quote giữ case; alias không quote sẽ fold thành chữ thường. Oracle cũng fold unquoted alias thành uppercase. SQL Server và MySQL có quy tắc hiển thị/metadata riêng. Nếu ứng dụng đọc bằng tên cột, hãy kiểm tra ResultSetMetaData.getColumnLabel() trên driver thực tế.

### 17.3. Alias trong WHERE

Không phải DBMS nào cũng cho dùng select-list alias trong WHERE vì WHERE được xử lý trước bước tạo output alias theo logical query processing.

Ví dụ không portable:

~~~sql
SELECT price * qty AS line_total
FROM order_item
WHERE line_total > 100000;
~~~

Có thể dùng biểu thức lặp lại hoặc subquery/CTE:

~~~sql
SELECT *
FROM (
    SELECT price * qty AS line_total
    FROM order_item
) AS x
WHERE x.line_total > 100000;
~~~

### 17.4. ORDER BY alias

ORDER BY thường có thể tham chiếu select-list alias, nhưng khi alias trùng tên cột hoặc keyword có thể phát sinh quy tắc phân giải riêng. Dùng alias đơn giản, duy nhất và tránh tên keyword.

## 18. Object names và namespace collisions

Không phải mọi loại đối tượng đều có namespace độc lập hoặc cùng phạm vi.

Ví dụ:
- Index có thể thuộc table/schema.
- Constraint có phạm vi tên khác nhau giữa DBMS.
- Sequence có thể nằm trong schema.
- Trigger thường gắn với table/schema.
- Procedure/function có thể overload theo signature ở một số DBMS.
- Temporary objects có phạm vi session/connection hoặc transaction theo DBMS.
- Synonym có thể che khuất object thật.

### 18.1. Đừng giả định tên constraint phải duy nhất toàn database

PostgreSQL, Oracle, SQL Server, MySQL có quy tắc namespace khác nhau cho constraint/index/trigger. Khi migration, các tên do DBMS tự sinh có thể khác và trùng sau khi đổi schema.

Đặt tên constraint rõ ràng trong DDL giúp:
- Dễ đọc lỗi.
- Dễ quản lý migration.
- Tránh tên tự sinh khó đoán.
- Dễ map constraint trong application error handling.

Nhưng vẫn cần theo giới hạn độ dài và phạm vi uniqueness của DBMS đích.

### 18.2. Tên index

~~~sql
CREATE INDEX ix_order_customer_created
ON sales_order(customer_id, created_at);
~~~

Cú pháp có thể khác ở vị trí schema/table hoặc option; tên index có thể phải duy nhất trong một phạm vi khác nhau. Kiểm tra DDL target thay vì chỉ thay delimiter.

## 19. Temporary tables và tên đặc biệt

Temporary table có phạm vi khác nhau:
- SQL Server: tên thường bắt đầu # hoặc ##, local/global temp tables trong tempdb.
- PostgreSQL: CREATE TEMP TABLE, thường gắn với session/transaction lifetime theo ON COMMIT.
- MySQL: CREATE TEMPORARY TABLE, session scoped.
- Oracle: global temporary table có definition lâu dài nhưng rows theo session/transaction; private temporary tables tùy version.
- SQLite: TEMP/TEMPORARY table trong temp database của connection.

Không port tên có tiền tố # từ SQL Server sang PostgreSQL hoặc dùng TEMP semantics của MySQL như Oracle global temporary table.

Tên temp table cũng có thể va chạm giữa session, database context hoặc schema; hiểu đúng lifecycle và cleanup.

## 20. Dynamic SQL: identifier không bind được, phải kiểm soát

Giả sử người dùng chọn một trường để sắp xếp:

~~~text
sort_by = "created_at"
direction = "DESC"
~~~

Không thể viết:

~~~sql
SELECT *
FROM sales_order
ORDER BY ?;
~~~

với parameter created_at rồi kỳ vọng nó trở thành tên cột. DBMS sẽ hiểu parameter là một giá trị hằng.

### 20.1. Allowlist identifier

Java:

~~~java
Map<String, String> allowedSortColumns = Map.of(
    "createdAt", "created_at",
    "total", "total_amount",
    "status", "status"
);

String column = allowedSortColumns.get(request.sortBy());
if (column == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}

String direction = switch (request.direction()) {
    case "ASC" -> "ASC";
    case "DESC" -> "DESC";
    default -> throw new IllegalArgumentException("Invalid direction");
};

String sql = "SELECT id, ma_don FROM sales_order ORDER BY "
        + column + " " + direction;
~~~

Ở đây:
- column đến từ allowlist cố định.
- direction đến từ enum/allowlist.
- Các giá trị lọc khác vẫn bind bằng PreparedStatement.
- Không nối raw user input vào SQL.

### 20.2. Quote identifier đúng dialect

Nếu identifier có ký tự đặc biệt, phải quote bằng quy tắc DBMS:
- PostgreSQL/Oracle: dấu nháy kép, escape dấu nháy kép bên trong bằng cách nhân đôi.
- MySQL: backtick, escape backtick bằng cách nhân đôi.
- SQL Server: QUOTENAME() hoặc helper an toàn, thường dùng ngoặc vuông.
- SQLite: dấu nháy kép và escape dấu nháy kép theo quy tắc SQLite.

Không dùng một hàm quote duy nhất cho cả năm hệ nếu chưa có abstraction đã kiểm thử.

### 20.3. Identifier quote không thay allowlist

Một input độc hại được quote đúng có thể chỉ trở thành tên đối tượng không tồn tại, nhưng vẫn có thể truy cập một bảng/cột mà user không được chọn theo nghiệp vụ. Vì vậy cần:
1. Allowlist đối tượng được phép.
2. Quote đúng dialect.
3. Bind mọi value.
4. Kiểm tra authorization.
5. Không dùng metadata từ input chưa xác thực.

### 20.4. Không dùng quote string function cho identifier

MySQL QUOTE(value) tạo string literal có escape; nó không phải hàm quote identifier. SQL Server QUOTENAME() dành cho identifier. PostgreSQL có quote_ident(). Oracle có DBMS_ASSERT helpers và cơ chế quote thích hợp.

## 21. Stored procedure và dynamic SQL theo DBMS

### 21.1. PostgreSQL

Có format %I trong format() để quote identifier trong PL/pgSQL:

~~~sql
EXECUTE format(
    'SELECT count(*) FROM %I.%I',
    schema_name,
    table_name
);
~~~

Dùng %I cho identifier và USING cho values:

~~~sql
EXECUTE format(
    'SELECT count(*) FROM %I.%I WHERE status = $1',
    schema_name,
    table_name
)
INTO row_count
USING wanted_status;
~~~

### 21.2. SQL Server

QUOTENAME() giúp quote một identifier:

~~~sql
DECLARE @table_name sysname = N'sales_order';
DECLARE @sql nvarchar(max);

SET @sql = N'SELECT COUNT(*) FROM '
         + QUOTENAME(N'sales')
         + N'.'
         + QUOTENAME(@table_name);

EXEC sys.sp_executesql @sql;
~~~

Nếu có value động, dùng parameter của sp_executesql, không nối value vào chuỗi SQL.

### 21.3. Oracle

Oracle có DBMS_ASSERT để kiểm tra/quote tên theo những loại identifier cụ thể. Dynamic SQL dùng EXECUTE IMMEDIATE hoặc DBMS_SQL, bind variables cho values. Không coi DBMS_ASSERT là thay thế hoàn toàn cho authorization/allowlist.

### 21.4. MySQL

MySQL dynamic SQL thường dùng PREPARE/EXECUTE. Parameter marker bind value; identifier phải được tạo trong câu SQL sau khi allowlist và quote bằng backtick đúng cách. Không nối raw input.

### 21.5. SQLite

SQLite API cho phép bind values; table/column names phải nằm trong SQL text. Ứng dụng cần allowlist và quote identifier đúng, hoặc dùng API metadata/cấu trúc query builder đã kiểm soát.

## 22. JDBC metadata và tên identifier

JDBC cung cấp metadata:

~~~java
DatabaseMetaData meta = connection.getMetaData();

String quote = meta.getIdentifierQuoteString();
String product = meta.getDatabaseProductName();
String version = meta.getDatabaseProductVersion();

System.out.println(product + " " + version);
System.out.println("Quote = " + quote);
~~~

getIdentifierQuoteString() trả chuỗi quote mà driver báo cho DBMS; có thể là dấu nháy kép, backtick hoặc chuỗi rỗng nếu driver không hỗ trợ/không dùng delimiter theo API.

### 22.1. Metadata patterns

Các phương thức như getTables/getColumns thường nhận pattern. Ký tự % và _ có thể là wildcard trong metadata pattern; muốn tìm đúng tên có wildcard, cần escape bằng getSearchStringEscape().

Ví dụ:

~~~java
String escape = meta.getSearchStringEscape();
~~~

Đừng truyền table name có underscore rồi mặc định metadata hiểu đó là dấu gạch dưới literal; có thể bị hiểu như wildcard một ký tự tùy API.

### 22.2. getColumnName và getColumnLabel

- getColumnName(): tên cột nguồn theo driver.
- getColumnLabel(): alias/output label nếu có.

Khi query có alias:

~~~sql
SELECT customer_id AS customer_ref
FROM customer;
~~~

ứng dụng thường nên đọc theo label:

~~~java
rs.getString("customer_ref");
~~~

Tên label có thể chịu quy tắc case/quote của DBMS/driver; test nếu dùng mixed-case.

### 22.3. Case-insensitive map trong ứng dụng

Một số framework map column labels không phân biệt case. Điều đó có thể che bug trên PostgreSQL/Oracle khi identifiers quote phân biệt case. Không dựa vào một map tiện ích để chứng minh schema portable.

## 23. ORM và naming strategies

ORM thường có hai hướng:
- **Implicit naming strategy:** suy ra tên table/column từ entity/property.
- **Physical naming strategy:** chuyển tên logic thành tên vật lý như snake_case.

Ví dụ Java:

~~~java
@Entity
@Table(name = "sales_order")
public class SalesOrder {
    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "created_at")
    private Instant createdAt;
}
~~~

Không để một môi trường tạo SalesOrder, môi trường khác tạo sales_order do naming strategy khác.

### 23.1. Quoted identifiers trong ORM

ORM có thể bật global quoting, khiến mọi table/column đều được quote. Điều này thay đổi semantics case folding của PostgreSQL/Oracle và có thể gây vấn đề với schema tạo bằng SQL scripts không quote.

Nếu dùng quoting:
- Quyết định từ đầu.
- Dùng thống nhất trong migrations và ORM.
- Không thay đổi giữa các môi trường.
- Kiểm thử schema validation.
- Kiểm tra tên constraint/index do ORM sinh.

### 23.2. Schema validation

Một entity mapping đúng trên H2 có thể không tương thích PostgreSQL/MySQL/SQL Server vì khác identifier folding/keywords. H2 không phải bằng chứng đầy đủ cho portability. Chạy integration tests trên DBMS production hoặc Testcontainers/runtime tương đương.

## 24. Migration: từ case-insensitive sang case-sensitive và ngược lại

Đây là nguồn lỗi lớn.

### 24.1. Hai bảng chỉ khác case

Nguồn PostgreSQL có thể chứa:

~~~sql
CREATE TABLE customer (...);
CREATE TABLE "Customer" (...);
~~~

Vì unquoted customer fold lowercase còn quoted "Customer" giữ case, hai bảng có thể cùng tồn tại.

Khi chuyển sang SQL Server collation CI, hai tên có thể va chạm. MySQL trên cấu hình case-insensitive hoặc SQLite cũng có thể không tạo được cả hai.

### 24.2. Ngược lại: tên mixed-case trên Oracle/PostgreSQL

Schema Oracle có table không quote tạo tên uppercase CUSTOMER. Migration script sang PostgreSQL nếu viết CREATE TABLE CUSTOMER không quote sẽ tạo customer lowercase, truy vấn không quote vẫn chạy; nhưng metadata và ORM có thể quan sát khác case.

Nếu migration tạo "CUSTOMER" quote ở PostgreSQL, tên được giữ uppercase và truy vấn unquoted customer không còn tìm thấy nó.

### 24.3. Tạo inventory trước migration

Cần liệt kê:
- Tên đầy đủ và schema.
- Object type.
- Case thực lưu.
- Tên sau khi fold theo DBMS đích.
- Tên sau khi truncation theo giới hạn đích.
- Collision do collation/case.
- Keyword mới.
- Ký tự Unicode/normalization.
- Index/constraint/routine phụ thuộc tên.

### 24.4. Quy tắc đổi tên

Chọn một canonical naming policy, ví dụ lowercase snake_case ASCII. Lập mapping:

| Tên nguồn | Tên đích | Lý do |
|---|---|---|
| "Customer" | customer | Bỏ mixed-case quoting |
| ORDER | sales_order | Tránh keyword |
| CustomerEmail | customer_email | Chuẩn hóa snake_case |
| ix_order_customer_created_at_archive | ix_order_cust_created | Giảm độ dài |

Mapping phải được dùng nhất quán trong DDL, foreign keys, views/procedures/triggers, ORM annotations, SQL native, reports/ETL, monitoring/metadata queries và operational scripts.

### 24.5. Không đổi tên chỉ bằng LOWER() một cách mù quáng

Nếu hai đối tượng cùng thành lowercase, có thể collision. Cần xử lý từng mapping và dữ liệu phụ thuộc trước khi ALTER/rename.

## 25. Keyword, alias và function name qua phiên bản

Keyword list thay đổi theo DBMS/version. Một identifier như rank, json, window, user, system, offset có thể được dùng ở bản cũ nhưng gây xung đột ở bản mới.

Chiến lược:
1. Chọn tên không phải keyword phổ biến.
2. Không đặt cột tên value, order, group, key, user, table, index nếu có tên nghiệp vụ rõ hơn.
3. Nếu phải giữ legacy name, quote đúng dialect.
4. Chạy parser/migration tests trên minimum và target DB versions.
5. Khi nâng cấp DBMS, kiểm tra release notes về reserved words.

### 25.1. Alias có thể đụng keyword

~~~sql
SELECT COUNT(*) AS count
FROM sales_order;
~~~

có thể hoạt động nhưng alias order, group, rank hoặc key dễ gây vấn đề tùy ngữ cảnh. Chọn alias như order_count, group_name, rank_score.

## 26. Phân biệt case của identifier và case của dữ liệu

Đây là hai lớp hoàn toàn khác.

Identifier:

~~~sql
SELECT Customer_ID FROM customer;
~~~

Dữ liệu:

~~~sql
SELECT *
FROM customer
WHERE display_name = 'Hoa';
~~~

Case sensitivity của Customer_ID là quy tắc tên cột. Case sensitivity của 'Hoa' phụ thuộc collation/operator/kiểu dữ liệu và DBMS.

Ví dụ:
- SQL Server collation CI có thể so 'Hoa' và 'hoa' bằng nhau.
- PostgreSQL text comparison mặc định thường phân biệt case; có thể dùng ILIKE/collation/citext tùy yêu cầu.
- MySQL so sánh phụ thuộc collation của cột/biểu thức.
- Oracle phụ thuộc binary/linguistic collation và hàm/cấu hình.
- SQLite phụ thuộc BINARY/NOCASE/RTRIM và quy tắc collation; NOCASE built-in không phải Unicode full case folding.

Không dùng identifier quoting để giải quyết case-insensitive search trong dữ liệu.

## 27. Tên đối tượng và collation của SQL Server/MySQL

### 27.1. SQL Server

Collation xác định nhiều quy tắc so sánh/sắp xếp, và có thể ảnh hưởng phân biệt tên đối tượng trong database/catalog. Ví dụ:
- CI_AS: không phân biệt case, phân biệt accent.
- CS_AS: phân biệt case, phân biệt accent.
- CI_AI: không phân biệt case và accent.

Chọn collation database là quyết định kiến trúc; đổi sau này có thể phức tạp vì phụ thuộc index, constraint và dữ liệu.

### 27.2. MySQL

Collation của cột ảnh hưởng so sánh dữ liệu chuỗi. Còn case của database/table names phụ thuộc lower_case_table_names và filesystem/platform. Đừng đánh đồng hai lớp.

### 27.3. PostgreSQL

Identifier folding không phải collation dữ liệu. Dữ liệu text có thể dùng collation cho sorting/comparison, nhưng quy tắc unquoted identifier vẫn fold lowercase.

### 27.4. Oracle

Identifier case và data collation cũng là hai vấn đề riêng. Quoted identifier giữ case; so sánh text phụ thuộc collation/linguistic settings và biểu thức.

### 27.5. SQLite

Identifier lookup và text collation tách biệt. NOCASE chỉ có hành vi Unicode hạn chế; cần ICU/extension hoặc xử lý ứng dụng nếu cần Unicode case folding toàn diện.

## 28. Temporary objects, synonyms và search path

Tên đơn giản có thể trỏ đến object khác tùy môi trường:
- PostgreSQL search_path có thể chọn temp table trước permanent table trong một số trường hợp.
- SQL Server có local temp table trong tempdb và object resolution riêng.
- Oracle synonym có thể làm tên ngắn trỏ tới object khác.
- MySQL current database ảnh hưởng tên không qualifier.
- SQLite temp/main/attached DB có namespace riêng.

Vì vậy, trong code ứng dụng:
- Không tạo temp table cùng tên với bảng quan trọng rồi giả định resolution.
- Không dựa vào synonym nếu portability là mục tiêu.
- Qualify schema/database khi cần.
- Dùng transaction/lifecycle rõ cho temporary objects.
- Test nhiều connection và pool.

## 29. Identifier trong generated SQL, migration và script

Một DDL migration có thể chạy trong SQL client nhưng fail khi được driver gửi như một statement duy nhất do:
- Delimiter ; và batch separator.
- SQL Server GO là lệnh của client, không phải T-SQL statement gửi qua JDBC.
- Oracle / là delimiter của SQL*Plus/SQLcl, không phải SQL statement thông thường.
- MySQL DELIMITER là lệnh client, không phải câu SQL gửi đến server.
- Quoted identifiers và embedded quote.
- Case/keyword.
- Schema resolution.

Không gửi nguyên file SQL có GO hoặc DELIMITER cho PreparedStatement nếu driver không hỗ trợ batch delimiter đó. Migration tool phải parse/execute theo dialect.

### 29.1. Dấu phân cách bên trong tên

Nếu identifier chứa dấu quote, delimiter phải được escape:
- SQL chuẩn double quote: dấu " bên trong được viết "".
- MySQL backtick: backtick bên trong được nhân đôi.
- SQL Server bracket: ] được viết ]].

Tên chứa delimiter thường là legacy cần giữ, không nên là convention mới.

### 29.2. Tên schema trong config

Nếu config có:

~~~text
schema = sales
table = sales_order
~~~

hãy lưu từng identifier riêng, validate theo policy và compose bằng dialect helper. Không lưu một chuỗi SQL hoàn chỉnh từ user rồi thực thi trực tiếp.

## 30. Ví dụ chuyển đổi tên giữa năm DBMS

Giả sử mục tiêu là bảng sales_order có cột order_id, customer_id, created_at.

**PostgreSQL:**

~~~sql
CREATE TABLE sales_order (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
~~~

**MySQL:**

~~~sql
CREATE TABLE sales_order (
    order_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

**SQL Server:**

~~~sql
CREATE TABLE dbo.sales_order (
    order_id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at DATETIME2 NOT NULL
);
~~~

**Oracle:**

~~~sql
CREATE TABLE sales_order (
    order_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id NUMBER(19) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

**SQLite:**

~~~sql
CREATE TABLE sales_order (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
~~~

Ví dụ này cố ý dùng tên lowercase ASCII không quote. Các kiểu khóa và thời gian vẫn cần mapping riêng; bài học tập trung identifier. SQLite TEXT timestamp yêu cầu ứng dụng định nghĩa format/UTC contract.

## 31. Checklist khi đặt tên schema mới

Trước khi tạo đối tượng:

- [ ] Identifier là tên đối tượng hay value? Nếu là value, bind parameter.
- [ ] Tên không phải reserved keyword trong DBMS mục tiêu.
- [ ] Dùng lowercase ASCII và underscore.
- [ ] Không có khoảng trắng, dấu tiếng Việt hoặc ký tự đặc biệt.
- [ ] Không dựa vào khác biệt case để phân biệt hai object.
- [ ] Tên nằm trong giới hạn độ dài của DBMS/phiên bản thấp nhất.
- [ ] Tên constraint/index được khai báo rõ, không để generator tạo tên quá dài.
- [ ] Schema/database qualifier được xác định.
- [ ] Search path/default schema/current database đã rõ.
- [ ] ORM naming strategy thống nhất với migration.
- [ ] Dynamic SQL dùng allowlist + quote helper.
- [ ] Driver metadata và case của column label được kiểm thử.
- [ ] Migration chạy trên đúng OS, collation, SQL mode và DB version.

## 32. Checklist migration identifiers

Trước khi chuyển schema:

1. Export danh sách toàn bộ objects và tên thực tế.
2. Xác định case folding của nguồn và đích.
3. Xác định collation/name comparison của SQL Server hoặc lower_case_table_names của MySQL.
4. Tìm cặp tên chỉ khác hoa/thường.
5. Tìm tên trùng keyword ở DBMS đích.
6. Tìm identifier vượt giới hạn bytes/chars của đích.
7. Tìm Unicode normalization/encoding đặc biệt.
8. Tạo mapping canonical source → target.
9. Kiểm tra foreign keys, views, routines, triggers, synonyms, indexes và ORM mappings.
10. Tạo DDL bằng dialect đúng, quote có chủ đích.
11. Chạy migration trên bản clone có cùng cấu hình production.
12. So metadata sau migration.
13. Chạy query integration tests bằng chính driver ứng dụng.
14. Xác minh scripts vận hành/backup/restore/ETL.
15. Có phương án rollback/rename nếu collision.

## 33. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ SQL luôn không phân biệt case | Tìm sai object | Hiểu folding/collation từng DB |
| PostgreSQL tạo "Customer" rồi query customer | Object not found | Giữ đúng quoted case hoặc đổi tên |
| Oracle tạo "OrderItem" mixed-case | Mọi query phải quote đúng | Dùng unquoted uppercase-compatible name |
| Dùng backtick trên PostgreSQL | Syntax error | Dùng double quote nếu thực sự cần |
| Dùng [] trên PostgreSQL/MySQL | Syntax error | Delimiter theo dialect |
| Dùng "name" trong MySQL mặc định | Có thể là string literal | Backtick hoặc ANSI_QUOTES có chủ đích |
| Dùng 'table' như identifier | String literal/behavior lạ | Dùng unquoted/identifier quote |
| Bật ANSI_QUOTES không đồng bộ | SQL cũ thay nghĩa | Quản lý sql_mode |
| Quote mọi identifier không thống nhất | ORM/migration không khớp | Một naming/quoting policy |
| Dùng keyword làm tên bảng | Parser error | Đổi tên nghiệp vụ |
| Dựa vào MySQL Windows case behavior | Lỗi khi deploy Linux | lowercase và test target OS |
| Đổi lower_case_table_names tùy tiện | Metadata/filesystem mismatch | Xác định từ lúc initialize |
| Nghĩ [] làm SQL Server case-sensitive | Không đúng | Collation quyết định |
| Tạo hai bảng chỉ khác case | Collision khi chuyển hệ | Inventory và rename mapping |
| Tên quá dài | Truncation/collision/DDL fail | Giới hạn bảo thủ |
| Đếm ký tự thay vì bytes | Vượt giới hạn Unicode | Đo theo quy tắc DBMS |
| Dùng dấu tiếng Việt trong identifier | Toolchain/normalization lỗi | ASCII identifiers |
| Nối user input thành table name | SQL injection | Allowlist + quote |
| Bind ? cho tên cột | Parser không coi là identifier | Compose identifier an toàn |
| Dùng quote string cho identifier | Sai escaping | Quote theo dialect |
| Không qualify schema | Lấy nhầm bảng cùng tên | schema.table |
| Search_path không kiểm soát | Object shadowing/security risk | Qualify và khóa CREATE quyền |
| Alias mixed-case rồi đọc label khác | JDBC mapping lỗi | Alias lowercase ổn định |
| Dùng alias trong WHERE | Không portable | Subquery/CTE hoặc lặp biểu thức |
| Test chỉ trên H2 | Khác behavior production | Integration test DB thật |
| Metadata pattern chứa _/% | Match quá nhiều object | Escape bằng metadata API |
| Dùng GO qua JDBC | Driver báo syntax error | Migration tool xử lý batch |
| Gửi DELIMITER cho server | Syntax error | Dùng client/tool hỗ trợ delimiter |
| Dùng tên auto-generated dài | Collision sau truncate | Đặt tên constraint/index ngắn |
| Chỉ đổi tên bảng, quên FK/view | Migration fail | Inventory dependencies |
| Case-only rename không test | Deploy khác OS/DB | Kiểm thử exact target environment |

## 34. Bài tập thực hành có đáp án

Các bài tập dùng ví dụ trong tài liệu. Mỗi câu hỏi kiểm tra một quy tắc định danh, không yêu cầu chạy trên production.

### Bài 1 — Identifier hay literal?

Trong SELECT ten_khach_hang FROM khach_hang WHERE id = 10, thành phần nào là identifiers?

<details>
<summary>Đáp án</summary>

ten_khach_hang, khach_hang và id là identifiers. 10 là numeric literal.

</details>

### Bài 2 — Value hay tên cột?

PreparedStatement với WHERE email = ? có thể bind tên cột vào dấu hỏi không?

<details>
<summary>Đáp án</summary>

Không. Dấu ? bind value/expression được phép, không thay token identifier.

</details>

### Bài 3 — Regular identifier

Tên don_hang không quote có ưu điểm gì?

<details>
<summary>Đáp án</summary>

Dễ viết, ít phụ thuộc delimiter, tránh khoảng trắng/ký tự đặc biệt và thường khả chuyển hơn.

</details>

### Bài 4 — Dấu quote chuẩn

Dấu quote identifier theo chuẩn SQL là gì?

<details>
<summary>Đáp án</summary>

Dấu nháy kép, ví dụ "don_hang". Nhưng SQL Server/MySQL có điều kiện mode, còn backtick/bracket là dialect-specific.

</details>

### Bài 5 — Dấu nháy đơn

'order' có phải identifier chuẩn không?

<details>
<summary>Đáp án</summary>

Không. Đây là string literal. Không dùng để quote table/column.

</details>

### Bài 6 — PostgreSQL folding

Trong PostgreSQL, CREATE TABLE Customer (...) không quote tạo tên nào?

<details>
<summary>Đáp án</summary>

Tên được fold về lowercase: customer.

</details>

### Bài 7 — PostgreSQL quoted

CREATE TABLE "Customer" (...) có thể được tham chiếu bằng FROM customer không?

<details>
<summary>Đáp án</summary>

Không. FROM customer tìm identifier lowercase customer; bảng quoted là "Customer" với case chính xác.

</details>

### Bài 8 — Oracle folding

Trong Oracle, CREATE TABLE customer (...) không quote tạo tên như thế nào?

<details>
<summary>Đáp án</summary>

Identifier được fold thành uppercase CUSTOMER.

</details>

### Bài 9 — Oracle mixed case

Tại sao "OrderItem" khó bảo trì?

<details>
<summary>Đáp án</summary>

Vì tên quoted giữ case và mọi query cần quote đúng spelling; ORM, migration và công cụ dễ phát SQL không khớp.

</details>

### Bài 10 — MySQL delimiter

MySQL mặc định dùng gì để quote identifier?

<details>
<summary>Đáp án</summary>

Backtick, ví dụ identifier Order được bao bởi dấu backtick.

</details>

### Bài 11 — MySQL double quote

Trong MySQL mặc định, "order" có chắc là identifier không?

<details>
<summary>Đáp án</summary>

Không. Thường là string literal; khi ANSI_QUOTES bật thì dấu nháy kép dùng cho identifiers.

</details>

### Bài 12 — lower_case_table_names

MySQL table-name case behavior phụ thuộc yếu tố nào?

<details>
<summary>Đáp án</summary>

Biến lower_case_table_names, hệ điều hành/filesystem và cách server được khởi tạo.

</details>

### Bài 13 — SQL Server bracket

Viết identifier có tên Order trong SQL Server.

<details>
<summary>Đáp án</summary>

~~~sql
SELECT * FROM [Order];
~~~

</details>

### Bài 14 — SQL Server double quote

Điều kiện thường dùng để "Order" là identifier trong SQL Server?

<details>
<summary>Đáp án</summary>

QUOTED_IDENTIFIER ON.

</details>

### Bài 15 — SQL Server case

Dấu ngoặc vuông có tự làm collation CI thành CS không?

<details>
<summary>Đáp án</summary>

Không. Delimiter không tự thay đổi collation; collation/catalog rules quyết định case comparison.

</details>

### Bài 16 — SQLite case

SQLite thông thường phân biệt TableA với tablea khi phân giải identifier không?

<details>
<summary>Đáp án</summary>

Không phân biệt ASCII case trong identifier lookup thông thường.

</details>

### Bài 17 — Reserved keyword

Tên bảng order có rủi ro gì?

<details>
<summary>Đáp án</summary>

ORDER là keyword trong nhiều hệ/ngữ cảnh; DDL/query có thể lỗi hoặc cần quote. Tốt hơn dùng sales_order.

</details>

### Bài 18 — PostgreSQL length

Giới hạn identifier mặc định của PostgreSQL tính theo gì?

<details>
<summary>Đáp án</summary>

63 bytes mặc định, không phải luôn 63 ký tự Unicode.

</details>

### Bài 19 — Oracle length

Oracle bản hiện đại có giới hạn phổ biến bao nhiêu bytes cho phần lớn identifiers?

<details>
<summary>Đáp án</summary>

128 bytes ở phiên bản hiện đại phù hợp; bản cũ hoặc COMPATIBLE thấp thường còn giới hạn 30 bytes.

</details>

### Bài 20 — SQL Server length

Giới hạn identifier thông thường của SQL Server?

<details>
<summary>Đáp án</summary>

128 ký tự; local temporary table có giới hạn hữu hiệu thấp hơn.

</details>

### Bài 21 — Unicode length

Vì sao 40 ký tự tiếng Việt có thể tốn nhiều bytes hơn 40 ký tự ASCII?

<details>
<summary>Đáp án</summary>

UTF-8 dùng số bytes khác nhau theo code point; ký tự có dấu thường chiếm nhiều hơn một byte.

</details>

### Bài 22 — Unicode normalization

Hai identifier hiển thị giống nhau có chắc có cùng chuỗi Unicode code points không?

<details>
<summary>Đáp án</summary>

Không. Một ký tự có thể được biểu diễn bằng code point dựng sẵn hoặc chữ + combining mark.

</details>

### Bài 23 — Naming convention

Đề xuất tên portable cho bảng “Chi tiết đơn hàng”.

<details>
<summary>Đáp án</summary>

chi_tiet_don_hang hoặc order_item, dùng lowercase ASCII và underscore.

</details>

### Bài 24 — Schema qualifier

Trong PostgreSQL, tên sales.customer gồm những phần nào?

<details>
<summary>Đáp án</summary>

Schema sales và table customer trong database đang kết nối.

</details>

### Bài 25 — MySQL qualifier

Trong MySQL, sales_db.customer thường có nghĩa gì?

<details>
<summary>Đáp án</summary>

Bảng customer trong database sales_db. Database và schema là hai tên gọi tương đương trong MySQL.

</details>

### Bài 26 — SQL Server qualifier

[dbo].[sales_order] gồm những phần nào?

<details>
<summary>Đáp án</summary>

Schema dbo và object sales_order trong database hiện tại.

</details>

### Bài 27 — Oracle qualifier

SALES.CUSTOMER thường có nghĩa gì?

<details>
<summary>Đáp án</summary>

Object CUSTOMER trong schema/owner SALES.

</details>

### Bài 28 — SQLite qualifier

main.customer có nghĩa gì?

<details>
<summary>Đáp án</summary>

Bảng customer trong database chính main của SQLite connection.

</details>

### Bài 29 — Search path

Hai schema có bảng cùng tên customer. Vì sao SELECT * FROM customer có thể lấy nhầm bảng?

<details>
<summary>Đáp án</summary>

DBMS phân giải tên đơn giản theo search_path/default schema/current database/synonym. Nên qualify schema khi cần rõ ràng.

</details>

### Bài 30 — Identifier injection

Vì sao không nối request.sortBy trực tiếp vào ORDER BY?

<details>
<summary>Đáp án</summary>

Input có thể chứa cú pháp SQL độc hại hoặc chọn cột không được phép. Dùng allowlist identifier, quote đúng dialect và bind các values.

</details>

### Bài 31 — Bind identifier

SELECT * FROM ? có dùng parameter để thay tên bảng không?

<details>
<summary>Đáp án</summary>

Không. Parameter marker không thay token cấu trúc SQL.

</details>

### Bài 32 — Quote identifier

PostgreSQL/Oracle dùng cách escape dấu nháy kép bên trong quoted identifier như thế nào?

<details>
<summary>Đáp án</summary>

Nhân đôi dấu nháy kép bên trong identifier, ví dụ "a""b".

</details>

### Bài 33 — SQL Server QUOTENAME

Hàm nào được dùng để quote identifier trong SQL Server?

<details>
<summary>Đáp án</summary>

QUOTENAME().

</details>

### Bài 34 — PostgreSQL format

Trong format() PL/pgSQL, placeholder nào quote identifier?

<details>
<summary>Đáp án</summary>

%I. Dùng USING hoặc cơ chế bind phù hợp cho value.

</details>

### Bài 35 — Metadata wildcard

getTables/getColumns nhận tên chứa underscore. Vì sao cần chú ý?

<details>
<summary>Đáp án</summary>

Trong metadata patterns, underscore có thể là wildcard một ký tự. Dùng DatabaseMetaData.getSearchStringEscape() khi cần tìm đúng tên.

</details>

### Bài 36 — Alias

SELECT total_amount AS "Total Amount" có nhược điểm portability nào?

<details>
<summary>Đáp án</summary>

Output label có khoảng trắng và được quote; client/ORM phải đọc đúng label/case. Alias lowercase đơn giản thường dễ chuyển hơn.

</details>

### Bài 37 — Alias trong WHERE

Có thể luôn dùng alias của select list trong WHERE không?

<details>
<summary>Đáp án</summary>

Không. Dùng subquery/CTE hoặc lặp biểu thức để portable.

</details>

### Bài 38 — Temporary table

SQL Server #temp có thể copy nguyên cú pháp sang PostgreSQL không?

<details>
<summary>Đáp án</summary>

Không. PostgreSQL dùng CREATE TEMP TABLE; vòng đời và namespace khác nhau.

</details>

### Bài 39 — GO

GO có phải câu lệnh T-SQL server hiểu qua JDBC không?

<details>
<summary>Đáp án</summary>

Không. GO là batch separator của một số client/tool, không phải T-SQL statement thông thường gửi tới server.

</details>

### Bài 40 — MySQL DELIMITER

DELIMITER có phải câu SQL chạy trên server qua PreparedStatement không?

<details>
<summary>Đáp án</summary>

Không. Đây là lệnh client để thay delimiter khi nhập routine body.

</details>

### Bài 41 — Case collision

Nguồn có customer và "Customer"; đích SQL Server collation CI. Rủi ro?

<details>
<summary>Đáp án</summary>

Hai object có thể collision vì đích không phân biệt case. Phải tạo inventory và mapping rename trước migration.

</details>

### Bài 42 — Naming policy

Một schema đa DBMS nên chọn convention nào?

<details>
<summary>Đáp án</summary>

Lowercase ASCII snake_case, tên không phải keyword, không khoảng trắng/ký tự đặc biệt, độ dài bảo thủ, schema qualifier rõ và một chính sách quote thống nhất.

</details>

### Bài 43 — Identifier vs data collation

Dùng "Customer" có làm WHERE name='Hoa' trở thành case-sensitive không?

<details>
<summary>Đáp án</summary>

Không. Quote identifier ảnh hưởng tên đối tượng; so sánh dữ liệu phụ thuộc collation/operator của biểu thức.

</details>

### Bài 44 — SQL Server CI

Collation CI_AS nghĩa là gì?

<details>
<summary>Đáp án</summary>

Case-insensitive, accent-sensitive: không phân biệt hoa/thường nhưng phân biệt dấu theo collation.

</details>

### Bài 45 — SQLite NOCASE

SQLite NOCASE có Unicode full case folding không?

<details>
<summary>Đáp án</summary>

Không. NOCASE built-in có giới hạn, chủ yếu ASCII; cần ICU/extension hoặc xử lý khác nếu cần Unicode case folding đầy đủ.

</details>

### Bài 46 — Đổi case-only name

Có nên chỉ chạy LOWER() trên mọi tên object để migration không?

<details>
<summary>Đáp án</summary>

Không. Có thể tạo collision; phải inventory, tính folding theo DBMS đích và lập mapping từng object.

</details>

### Bài 47 — Dynamic values

Khi dynamic SQL chọn table theo cấu hình, value filter có nên nối chuỗi cùng identifier không?

<details>
<summary>Đáp án</summary>

Không. Identifier được allowlist và quote; value dùng bind parameters.

</details>

### Bài 48 — Tổng hợp

Một hệ chạy PostgreSQL và SQL Server. Đề xuất naming/quoting policy cho schema mới.

<details>
<summary>Đáp án</summary>

Dùng lowercase ASCII snake_case, tránh keyword, không khoảng trắng/dấu tiếng Việt, tên ngắn (xem cả giới hạn 63 bytes PostgreSQL và 128 chars SQL Server), không tạo tên khác nhau chỉ bởi case. Không quote trong DDL/DML thông thường. Schema-qualify các object quan trọng. Với dynamic identifiers, allowlist và quote bằng helper theo dialect; values luôn bind. Test bằng hai DBMS thật, không chỉ H2.

</details>

## 35. Quy trình chuẩn khi thiết kế và chuyển identifier

**Bước 1 — Phân loại token.** Xác định phần nào là identifier, phần nào là literal/value, phần nào là keyword/operator.

**Bước 2 — Chọn convention.** Dùng lowercase ASCII, underscore, tên ngắn và không phải reserved words.

**Bước 3 — Kiểm tra folding.** PostgreSQL fold lowercase, Oracle uppercase, SQL Server theo collation, MySQL theo lower_case_table_names cho database/table, SQLite không phân biệt ASCII case.

**Bước 4 — Quyết định quoting.** Không quote nếu không cần. Nếu phải quote, dùng delimiter đúng dialect và escaping đúng.

**Bước 5 — Qualify namespace.** Chọn schema/database rõ ràng, kiểm tra search_path/default schema/current database.

**Bước 6 — Kiểm tra giới hạn.** Đo bytes/chars theo DBMS và kiểm tra truncation/collision.

**Bước 7 — Kiểm tra keyword và version.** Không dựa vào danh sách keyword cũ.

**Bước 8 — Bảo vệ dynamic SQL.** Allowlist identifier, quote đúng và bind values.

**Bước 9 — Đồng bộ ORM/migration.** Một naming strategy, một quoting policy, một nguồn schema.

**Bước 10 — Test trên môi trường thật.** Cùng OS, filesystem, collation, SQL mode, DB version và JDBC driver như production.

## 36. Kết luận cần ghi nhớ

1. **Identifier là tên đối tượng; literal là dữ liệu.** PreparedStatement bind value, không bind table/column name.
2. Regular identifier thường dễ chuyển hơn delimited identifier.
3. Dấu nháy kép là delimiter theo chuẩn SQL; backtick là kiểu MySQL; ngoặc vuông là kiểu SQL Server. SQL mode/cấu hình có thể thay đổi cách diễn giải.
4. PostgreSQL fold unquoted identifiers về **lowercase**; Oracle fold về **uppercase**.
5. SQL Server chịu ảnh hưởng **collation** khi phân giải identifier; quote không tự đổi collation.
6. MySQL database/table name phụ thuộc **lower_case_table_names**, OS và filesystem; không được dựa vào case behavior của máy phát triển.
7. SQLite thông thường phân giải identifiers không phân biệt ASCII case; quote không tạo hai object chỉ khác case.
8. Tên mixed-case có quote có thể buộc mọi truy vấn phải quote đúng spelling; tránh trong schema mới.
9. Reserved keywords thay đổi theo phiên bản; chọn tên nghiệp vụ thay vì quote keyword.
10. Identifier length khác nhau và có thể tính theo bytes hoặc characters; PostgreSQL mặc định 63 bytes, Oracle bản cũ 30 bytes và bản mới phổ biến 128 bytes, SQL Server thường 128 characters, MySQL thường 64 characters cho nhiều object.
11. Unicode identifiers có rủi ro normalization/case folding/tooling; lowercase ASCII là convention portable.
12. Schema qualification khác nhau: PostgreSQL schema.table, MySQL database.table, SQL Server database.schema.object, Oracle schema.object, SQLite alias.table.
13. Name resolution phụ thuộc search_path/default schema/current database/synonym; tên không qualifier có thể trỏ nhầm object.
14. Identifier quote không phải cách xử lý case của **giá trị dữ liệu**; collation của dữ liệu là vấn đề khác.
15. Dynamic SQL phải dùng **allowlist + quote identifier đúng dialect + bind values**.
16. JDBC metadata patterns có wildcard; dùng getSearchStringEscape khi tìm tên chính xác.
17. ORM naming strategy và migration DDL phải thống nhất về case/quote.
18. Migration cần phát hiện case collisions, keyword collisions, length truncation, Unicode và dependencies trước khi rename.
19. GO và DELIMITER là lệnh batch/client trong môi trường tương ứng, không phải SQL statement phổ quát.
20. Hãy hỏi: **“DBMS lưu tên này dưới dạng nào, tìm nó bằng quy tắc nào, và câu SQL/driver có dùng đúng spelling cùng namespace không?”**

### Tài liệu chính thức nên tham khảo

Khi triển khai, tra đúng DBMS và version:

- **PostgreSQL Documentation:** Lexical Structure; Identifiers and Key Words; Schemas; search_path; format() and Dynamic SQL.
- **MySQL Reference Manual:** Schema Object Names; Identifier Case Sensitivity; lower_case_table_names; ANSI_QUOTES; SQL Modes; Prepared Statements.
- **Microsoft Learn — SQL Server:** Database Identifiers; QUOTED_IDENTIFIER; Collations; QUOTENAME; multipart names; sp_executesql.
- **Oracle Database SQL Language Reference:** Database Object Names and Qualifiers; Naming Rules; Schema Objects; Quoted Identifiers; DBMS_ASSERT.
- **SQLite Documentation:** Keywords; SQLite SQL Language Expressions; Object Names; ATTACH DATABASE; Application-Defined SQL Functions.
- **JDBC Documentation:** DatabaseMetaData; getIdentifierQuoteString; getSearchStringEscape; ResultSetMetaData; PreparedStatement.
- **Hibernate/JPA Documentation:** PhysicalNamingStrategy; ImplicitNamingStrategy; globally quoted identifiers; schema validation.

**Thông điệp cuối cùng:** Muốn SQL đa hệ quản trị ổn định, hãy đặt tên đối tượng đơn giản và nhất quán, hiểu cách từng DBMS fold/so sánh identifier, qualify namespace khi cần, và chỉ quote theo dialect trong trường hợp thật sự cần. Với SQL động, identifier phải được allowlist và quote an toàn; mọi giá trị dữ liệu vẫn phải bind parameter. Đây là cách tránh lỗi “không tìm thấy bảng”, collision khi migration và SQL injection do tên đối tượng.

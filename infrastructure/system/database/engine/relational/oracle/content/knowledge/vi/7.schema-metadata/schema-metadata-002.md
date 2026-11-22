# Tên đối tượng, định danh có dấu ngoặc kép và phân biệt chữ hoa chữ thường trong Oracle Database

Khi viết SQL cho Oracle, bạn có thể tạo bảng bằng câu lệnh `CREATE TABLE orders (...)` rồi truy vấn lại bằng `SELECT * FROM ORDERS` hoặc `SELECT * FROM Orders` mà không gặp vấn đề về chữ hoa/chữ thường. Tuy nhiên, nếu một bảng được tạo với tên `"Orders"`, Oracle sẽ ghi nhớ đúng chữ `O` viết hoa và phần `rders` viết thường; khi tham chiếu, bạn phải dùng đúng cách viết và dấu ngoặc kép. Sự khác biệt nhỏ này có ảnh hưởng lớn đến câu lệnh SQL, metadata, mã Java, migration script và việc tìm lỗi trong hệ thống có nhiều schema.

Trong phần **Schema và metadata**, bài học này tập trung vào cách Oracle xử lý **tên đối tượng (object names)** và **định danh SQL (identifiers)**: tên bảng, cột, view, schema, alias, constraint, sequence và những thành phần có tên khác. Chúng ta sẽ phân biệt **định danh thông thường không có dấu ngoặc kép** (*nonquoted identifiers*) với **định danh có dấu ngoặc kép** (*quoted identifiers*), cách chúng xuất hiện trong data dictionary và cách truy cập chính xác.

Sau khi học, bạn có thể:

- Giải thích vì sao `orders`, `ORDERS` và `OrDeRs` tương đương khi **không** có dấu ngoặc kép.
- Phân biệt `ORDERS`, `"ORDERS"`, `"Orders"` và `"orders"` trong câu lệnh SQL.
- Viết SQL để làm việc với tên cột/tên bảng có chữ hoa thường trộn nhau, khoảng trắng hoặc từ khóa.
- Dùng `USER_OBJECTS`, `USER_TABLES` và `USER_TAB_COLUMNS` để xác định tên đối tượng thực tế Oracle đã lưu.
- Hiểu sự khác biệt giữa cách phân biệt chữ hoa thường của **identifier** và của **giá trị chuỗi**.
- Chọn quy ước đặt tên dễ bảo trì trong SQL, Java/JDBC, ORM và migration.

> **Phạm vi:** Các ví dụ dành cho một **schema thực hành** trong Oracle PDB đã mở `READ WRITE`. Những lệnh `CREATE`, `ALTER` và `DROP` thực sự thay đổi schema; chỉ chạy trong môi trường lab của bạn. Tên người dùng, bảng và các đối tượng đã có sẵn có thể khác ví dụ.

## 1. Identifier là gì, khác tên hiển thị và giá trị dữ liệu thế nào?

**Identifier** là tên mà cú pháp SQL dùng để tham chiếu đến một đối tượng hoặc một thành phần có tên. Ví dụ:

~~~sql
SELECT order_id, customer_name
FROM orders
WHERE order_id = 10;
~~~

Trong lệnh này:

| Thành phần | Loại | Ý nghĩa |
| --- | --- | --- |
| `orders` | Table identifier | Tên bảng cần truy vấn |
| `order_id` | Column identifier | Tên cột dùng trong `SELECT` và `WHERE` |
| `customer_name` | Column identifier | Tên cột khách hàng |
| `10` | Number literal | Giá trị số dùng so sánh |
| `SELECT`, `FROM`, `WHERE` | Từ khóa SQL | Cú pháp của câu lệnh, không phải tên bảng/cột |

Thử so sánh:

~~~sql
-- Ten cot: identifier
SELECT customer_name
FROM orders;

-- Chuoi ky tu: string literal, khong phai identifier
SELECT 'customer_name' AS sample_text
FROM dual;
~~~

Lệnh thứ nhất đọc giá trị của cột `CUSTOMER_NAME` từ mỗi hàng; lệnh thứ hai trả về chuỗi chữ `customer_name` cố định. **Dấu nháy đơn `'...'` được dùng cho string literal, còn dấu ngoặc kép `"..."` được dùng cho quoted identifier.**

Quy tắc tương tự áp dụng cho tên schema, bảng, view, cột, sequence, index, constraint, function, package và alias truy vấn; các loại đối tượng có thể có thêm điều kiện đặt tên riêng theo từng phiên bản Oracle.

## 2. Quy tắc cơ bản: identifier không có dấu ngoặc kép

### 2.1. Oracle chuẩn hóa thành chữ hoa

Khi bạn viết một tên đối tượng **không đặt trong dấu ngoặc kép**, Oracle xử lý identifier đó theo dạng chữ hoa khi lưu và đối chiếu tên. Trong ba câu lệnh sau, tên bảng được hiểu giống nhau:

~~~sql
SELECT * FROM orders;
SELECT * FROM ORDERS;
SELECT * FROM OrDeRs;
~~~

Các cách viết đều tham chiếu đến tên logic `ORDERS` trong ngữ cảnh schema hiện hành, nếu bảng/view phù hợp tồn tại và user có quyền. Điều này giúp SQL thông thường không phải quan tâm nhiều đến kiểu viết hoa trong mã nguồn.

Ví dụ tạo bảng:

~~~sql
CREATE TABLE customer_orders (
    order_id       NUMBER PRIMARY KEY,
    customer_name  VARCHAR2(100),
    order_total    NUMBER(12, 2)
);
~~~

Trong metadata của Oracle, tên bảng và các cột thông thường có dạng:

~~~text
TABLE_NAME       = CUSTOMER_ORDERS
COLUMN_NAME      = ORDER_ID
COLUMN_NAME      = CUSTOMER_NAME
COLUMN_NAME      = ORDER_TOTAL
~~~

Mặc dù bạn đã gõ các tên chữ thường, việc Oracle lưu tên identifier ở dạng chữ hoa **không biến dữ liệu trong cột thành chữ hoa**. Giá trị `'Alice'` trong `CUSTOMER_NAME` vẫn là `'Alice'` theo quy tắc lưu trữ chuỗi.

### 2.2. Hạn chế cú pháp thường gặp

Với tên kiểu ASCII đơn giản, một nonquoted identifier:

- Bắt đầu bằng **chữ cái**.
- Sau đó thường dùng chữ cái, chữ số, dấu gạch dưới `_`; Oracle cũng cho phép `$` và `#` trong tên thông thường, nhưng không khuyến khích dùng hai ký tự này trong quy ước ứng dụng.
- Không chứa khoảng trắng hoặc dấu gạch ngang `-` theo cách đặt tên thông thường.
- Không dùng từ khóa **reserved** của Oracle làm tên unquoted.
- Phải thỏa giới hạn độ dài **tính theo byte**, không phải số ký tự hiển thị.

Các tên dễ đọc và tương đối an toàn:

~~~text
CUSTOMER_ORDERS
ORDER_ID
CREATED_AT
EMPLOYEE2
REPORT_2026
~~~

Các tên sau không phải nonquoted identifier hợp lệ theo quy ước ASCII cơ bản:

~~~text
order status       -- co khoang trang
2orders            -- bat dau bang chu so
order-total        -- dau - bi hieu la toan tu
select             -- SELECT la tu khoa SQL reserved
~~~

Tên có ký tự quốc tế có thể chịu ảnh hưởng character set và quy tắc identifier của Oracle. Khi muốn đặt tên có dấu tiếng Việt hoặc ký tự đặc biệt, sử dụng quoted identifier về mặt cú pháp có thể khả thi, nhưng hãy cân nhắc khả năng hỗ trợ của driver, công cụ migration, shell và đội phát triển.

### 2.3. Giới hạn độ dài theo phiên bản

Trong **Oracle Database 12.2 trở lên**, phần lớn identifier phổ biến như tên bảng/cột có giới hạn tối đa **128 byte**; ở nhiều phiên bản trước 12.2, giới hạn tương ứng là **30 byte**. Một số loại tên đặc biệt vẫn có giới hạn hoặc quy tắc riêng, vì vậy không mặc định *mọi* tên trong hệ thống đều dùng được 128 byte.

Ví dụ:

~~~text
ORDER_ID                  -- 8 byte neu dung cac ky tu ASCII
CUSTOMER_DELIVERY_STATUS  -- 24 byte voi ASCII
~~~

Với UTF-8, ký tự có dấu thường chiếm nhiều byte; “128 ký tự” **không đồng nghĩa 128 byte**. Đối với dự án phải chạy trên nhiều phiên bản Oracle, cần chọn quy ước độ dài tương thích với phiên bản thấp nhất được hỗ trợ.

## 3. Quoted identifier: dấu ngoặc kép giữ nguyên tên và chữ hoa/chữ thường

### 3.1. Đặt tên đúng như đã viết

Nếu đặt identifier trong cặp **dấu ngoặc kép thẳng** `"..."`, Oracle giữ nguyên cách viết chữ hoa/chữ thường của tên đó và yêu cầu cách tham chiếu tương ứng.

~~~sql
CREATE TABLE "Invoices" (
    "InvoiceId"   NUMBER PRIMARY KEY,
    "CustomerID"  NUMBER NOT NULL,
    total_amount  NUMBER(12, 2)
);
~~~

Tên bảng thực tế là `Invoices`, còn các cột là `InvoiceId`, `CustomerID` và `TOTAL_AMOUNT`. Lúc này:

~~~sql
-- Dung: ten bang va cot co quote phai khop chinh xac.
SELECT "InvoiceId", "CustomerID", total_amount
FROM "Invoices";

-- Dung: cot TOTAL_AMOUNT duoc tao khong quote, nen co the viet hoa/thuong.
SELECT "InvoiceId", TOTAL_AMOUNT
FROM "Invoices";
~~~

Nếu chỉ có bảng `"Invoices"` mà không có bảng khác tên `INVOICES`:

~~~sql
-- Sai doi tuong: Invoices khong quote se thanh INVOICES.
SELECT * FROM Invoices;

-- Sai ten: chu hoa trong "INVOICES" khong khop "Invoices".
SELECT * FROM "INVOICES";

-- Sai ten cot: InvoiceId khong quote se thanh INVOICEID.
SELECT InvoiceId FROM "Invoices";
~~~

Các truy vấn sai có thể dẫn đến `ORA-00942` (table/view không tồn tại hoặc không thấy do quyền) hoặc `ORA-00904` (invalid identifier), tùy vị trí và quyền. Nhưng nếu schema **đã có** đối tượng tên `INVOICES` riêng, một câu lệnh không quote có thể truy vấn **đối tượng đó** thay vì báo lỗi. Đây là lý do các tên chỉ khác nhau về chữ hoa/thường dễ gây nhầm lẫn nguy hiểm.

### 3.2. Bốn cách viết không hoàn toàn giống nhau

Giả sử trong một schema bạn cân nhắc bốn cách ghi:

| Cách viết trong SQL | Tên Oracle dùng để tra cứu | Có tương đương với `orders` không? |
| --- | --- | --- |
| `orders` | `ORDERS` | Có |
| `ORDERS` | `ORDERS` | Có |
| `"ORDERS"` | `ORDERS` | Có, nếu cùng schema và loại đối tượng |
| `"Orders"` | `Orders` | Không |
| `"orders"` | `orders` | Không |

Vì thế **`"ORDERS"` có thể tham chiếu cùng đối tượng được tạo bằng `CREATE TABLE orders`**, nhưng `"Orders"` không phải biến thể tự động của tên đó.

Quan sát bằng ví dụ độc lập trong một schema lab chưa có bảng cùng tên:

~~~sql
CREATE TABLE orders (
    id NUMBER
);

CREATE TABLE "Orders" (
    id NUMBER
);

-- Truy van bang co ten luu la ORDERS:
SELECT * FROM orders;
SELECT * FROM "ORDERS";

-- Truy van bang co ten luu la Orders:
SELECT * FROM "Orders";
~~~

Hai bảng có tên **khác nhau trong cùng schema**. Trước khi áp dụng migration hoặc thao tác `DROP TABLE`, phải biết tên Oracle đã lưu thực tế. Ví dụ này chỉ nên chạy trong schema học tập bởi việc cố ý tạo hai tên chỉ khác chữ hoa/thường không phải quy ước tốt cho sản phẩm.

### 3.3. Khoảng trắng, ký tự đặc biệt và từ khóa

Quoted identifier cho phép các tên vốn không hợp lệ nếu viết không quote, chẳng hạn:

~~~sql
CREATE TABLE "Order Details" (
    "Order ID"   NUMBER PRIMARY KEY,
    "Unit-Price" NUMBER(10, 2),
    "select"     VARCHAR2(30)
);

SELECT "Order ID", "Unit-Price", "select"
FROM "Order Details";
~~~

Oracle hiểu `"Order Details"` là **một** identifier, thay vì hai từ; `"Unit-Price"` là một tên cột thay vì phép trừ; `"select"` là tên cột có dấu ngoặc kép thay vì từ khóa `SELECT`.

Những tên như vậy có thể dùng được nhưng buộc mọi truy vấn, đoạn code Java, migration, ORM mapping và công cụ báo cáo phải trích dẫn đúng tên. Nếu hệ thống đã có quy ước đặt tên, hãy **tuân thủ quy ước** thay vì sử dụng quote chỉ để tạo kiểu hiển thị “đẹp”.

Không phải mọi chuỗi ký tự đều trở thành tên hợp lệ chỉ nhờ quote. Ví dụ, Oracle có những ngoại lệ đặc biệt như identifier `"ROWID"` viết hoàn toàn chữ hoa bị cấm, và không cho dùng ký tự null hoặc dấu ngoặc kép bên trong tên theo quy tắc identifier; các loại đối tượng cụ thể cũng có thể có ràng buộc bổ sung.

## 4. Quy tắc phân biệt chữ hoa/chữ thường trong thực tế

### 4.1. Tên bảng và tên cột được xét độc lập

Tạo bảng trong schema lab:

~~~sql
CREATE TABLE demo_names (
    item_id        NUMBER PRIMARY KEY,
    "DisplayName"  VARCHAR2(80),
    "order status" VARCHAR2(20),
    created_at     DATE
);

INSERT INTO demo_names (
    item_id, "DisplayName", "order status", created_at
) VALUES (
    1, 'Keyboard', 'NEW', SYSDATE
);

COMMIT;
~~~

Các tên thực tế:

~~~text
Table:
  DEMO_NAMES

Columns:
  ITEM_ID
  DisplayName
  order status
  CREATED_AT
~~~

Truy vấn hợp lệ:

~~~sql
SELECT
    item_id,
    "DisplayName",
    "order status",
    CREATED_AT
FROM DEMO_NAMES;

-- Tuong duong ve ten table/cot khong quote.
SELECT item_id, "DisplayName", "order status"
FROM demo_names;
~~~

Truy vấn không hợp lệ đối với chính tên cột:

~~~sql
-- Oracle tim cot DISPLAYNAME, khong phai "DisplayName".
SELECT DisplayName
FROM demo_names;

-- Oracle tim cot "displayname", khong phai "DisplayName".
SELECT "displayname"
FROM demo_names;
~~~

Để truy vấn cột đã tạo bằng quoted identifier, bạn phải dùng đúng `"DisplayName"`. Tên bảng `DEMO_NAMES` không quote có thể viết thành `demo_names` vì nó được tạo bằng nonquoted identifier.

### 4.2. Qualified names: `schema.table.column`

Một object name có thể được phân giải từ **schema hiện tại** hoặc viết kèm owner:

~~~sql
-- Neu la owner cua table:
SELECT "DisplayName"
FROM demo_names;

-- Neu schema duoc tao unquoted voi ten LAB_SCHEMA:
SELECT "DisplayName"
FROM lab_schema.demo_names;

-- Tuong duong ve ten schema/table unquoted:
SELECT "DisplayName"
FROM "LAB_SCHEMA"."DEMO_NAMES";
~~~

Nếu schema của bạn được tạo với tên **quoted** như `"LabSchema"`, bạn phải ghi đúng:

~~~sql
SELECT "DisplayName"
FROM "LabSchema"."DEMO_NAMES";
~~~

Đường dẫn xác định đối tượng là **schema name + object name**, mỗi phần được phân giải theo quy tắc quoted/unquoted của chính nó. Trong câu `"LabSchema"."DEMO_NAMES"`, dấu chấm **nằm giữa hai identifier**; đó không phải là một identifier duy nhất có tên chứa dấu chấm.

Oracle cũng có các quy tắc name resolution khác như synonym, default schema, database link và loại đối tượng. Khi có nhiều object cùng tên ở các schema khác nhau, phải dùng owner/alias rõ ràng thay vì dựa vào tên viết hoa/thường.

### 4.3. Table aliases cũng tuân theo quy tắc quote

Aliasing giúp viết truy vấn join, nhưng alias vẫn là identifier:

~~~sql
-- Alias d khong quote: Oracle chuan hoa thanh D.
SELECT d.item_id, d."DisplayName"
FROM demo_names d;

-- Alias "d" co quote: phai giu nguyen chu d thuong.
SELECT "d".item_id, "d"."DisplayName"
FROM demo_names "d";
~~~

Hai truy vấn hợp lệ nhưng dùng **hai alias khác nhau về cách tham chiếu**. Nếu đã đặt alias `"d"` mà sau đó viết `D."DisplayName"`, câu SQL không tham chiếu đúng alias đó.

Lệnh join nhiều bảng nên dùng alias đơn giản, nhất quán, không quote trừ khi đang tương tác với SQL được sinh ra từ hệ thống khác và có yêu cầu rõ ràng.

### 4.4. Column alias và cách đặt tên cột trong kết quả

Tên hiển thị của cột kết quả cũng có quy tắc quoted/unquoted:

~~~sql
SELECT
    item_id AS itemId,
    "DisplayName" AS "displayName",
    "order status" AS "Order Status"
FROM demo_names;
~~~

Thông thường tên hiển thị của expression `item_id AS itemId` được Oracle chuẩn hóa thành `ITEMID`, còn các alias `"displayName"` và `"Order Status"` giữ đúng chữ hoa/thường và khoảng trắng. Một số SQL client có thể tùy biến cách hiển thị header, nhưng label SQL mà Oracle trả về vẫn phản ánh các alias đã viết.

Có thể dùng quoted alias trong `ORDER BY` của cùng query:

~~~sql
SELECT item_id AS "itemId"
FROM demo_names
ORDER BY "itemId";
~~~

**Đừng nhầm alias kết quả với cột vật lý**: câu `AS "itemId"` không đổi tên cột `ITEM_ID` trong database. Alias cũng không tự trở thành cột được sử dụng ở mọi phần của cùng query block, ví dụ `WHERE` vẫn phải tham chiếu expression/cột gốc theo cú pháp SQL.

## 5. Data dictionary: nơi xác nhận tên Oracle đã lưu

Điểm quan trọng khi xử lý lỗi là **xem metadata thay vì đoán**. Oracle lưu tên unquoted dưới dạng uppercase và lưu quoted name bằng đúng cách viết đã khai báo. Các view data dictionary phản ánh điều đó.

### 5.1. Quan sát tên bảng qua `USER_TABLES`

Sau khi tạo `DEMO_NAMES` và `"Invoices"` ở ví dụ trên, chạy:

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name IN ('DEMO_NAMES', 'Invoices')
ORDER BY table_name;
~~~

Kết quả minh họa:

~~~text
TABLE_NAME
----------
DEMO_NAMES
Invoices
~~~

Điều đáng chú ý là **`TABLE_NAME` thực sự mang giá trị `Invoices`** chứ không được chuyển thành `INVOICES`. Nếu viết:

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name = 'INVOICES';
~~~

truy vấn có thể không tìm thấy `"Invoices"`, bởi vì `'INVOICES'` là **giá trị chuỗi** được dùng so sánh với metadata, và các quy tắc so sánh chuỗi áp dụng; mặc định so sánh nhị phân sẽ phân biệt chữ hoa/thường. Đừng cố dùng quote vào **giá trị chuỗi** theo kiểu `"Invoices"` trong `WHERE`: lúc đó Oracle hiểu là identifier cột, không phải một string literal.

### 5.2. Quan sát tên cột qua `USER_TAB_COLUMNS`

~~~sql
SELECT
    column_id,
    column_name,
    data_type,
    nullable
FROM user_tab_columns
WHERE table_name = 'DEMO_NAMES'
ORDER BY column_id;
~~~

Kết quả minh họa:

~~~text
COLUMN_ID  COLUMN_NAME   DATA_TYPE  NULLABLE
---------  ------------  ---------  --------
1          ITEM_ID       NUMBER     N
2          DisplayName   VARCHAR2   Y
3          order status  VARCHAR2   Y
4          CREATED_AT    DATE       Y
~~~

`ITEM_ID` và `CREATED_AT` đã được chuẩn hóa chữ hoa khi tạo; `DisplayName` và `order status` được giữ nguyên.

Bạn cũng có thể tìm đúng một cột quoted:

~~~sql
SELECT column_name, data_type
FROM user_tab_columns
WHERE table_name = 'DEMO_NAMES'
  AND column_name = 'DisplayName';
~~~

Nếu điều kiện viết `column_name = 'DISPLAYNAME'`, nó tìm một **chuỗi khác** trong cách so sánh phân biệt chữ hoa/thường thông thường. Điều này rất hay gặp ở code Java sinh truy vấn metadata.

### 5.3. Tìm mọi loại object bằng `USER_OBJECTS`

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN ('DEMO_NAMES', 'Invoices', 'Orders')
ORDER BY object_name, object_type;
~~~

`USER_OBJECTS` chứa nhiều loại schema object, không chỉ table. Vì các namespace khác nhau của Oracle có thể có quy tắc trùng tên riêng, việc nhìn cả `OBJECT_TYPE` giúp tránh kết luận sai khi tìm object.

Nếu cần xem các object mà user hiện tại **có quyền truy cập ở schema khác**, sử dụng các view `ALL_*` phù hợp (ví dụ `ALL_TABLES`, `ALL_TAB_COLUMNS`); DBA có thể sử dụng `DBA_*` theo quyền. Trong multitenant, truy vấn từ một PDB chỉ phản ánh phạm vi container/quyền đang có; root và các `CDB_*` view có thêm ngữ cảnh `CON_ID`, không nên xem toàn CDB như một schema đơn.

### 5.4. Tìm tên gần giống khi chưa biết chữ hoa/thường

Nếu mục đích **khám phá** object đã tồn tại, có thể dùng:

~~~sql
SELECT table_name
FROM user_tables
WHERE UPPER(table_name) = 'INVOICES'
ORDER BY table_name;
~~~

Truy vấn này có thể tìm `INVOICES`, `Invoices` và `invoices` nếu cả ba tồn tại, vì hàm `UPPER` được áp dụng **trên giá trị metadata**. Nó không thay đổi quy tắc name resolution của SQL khi bạn thực sự truy vấn bảng. Sau khi tìm được tên, phải tham chiếu đúng đối tượng đích, ví dụ `"Invoices"`.

Hàm `UPPER` trong truy vấn metadata là công cụ tìm kiếm; không nên áp dụng nó tùy tiện để coi các object chỉ khác nhau về chữ hoa/thường là một. Mục đích của bài toán có thể là nhận diện chính xác một object, không phải gộp chúng.

## 6. Identifier case sensitivity khác với string comparison và collation

Đây là một nhầm lẫn quan trọng: việc Oracle không phân biệt chữ hoa/thường của **unquoted identifiers** không có nghĩa mọi so sánh **dữ liệu chuỗi** cũng không phân biệt chữ hoa/thường.

Xét:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(100)
);

INSERT INTO customers VALUES (1, 'Alice');
INSERT INTO customers VALUES (2, 'ALICE');
COMMIT;
~~~

Hai truy vấn sau tham chiếu **cùng tên cột**:

~~~sql
SELECT FULL_NAME FROM customers;
SELECT full_name FROM CUSTOMERS;
~~~

Nhưng điều kiện trên **giá trị dữ liệu** lại là vấn đề khác:

~~~sql
SELECT customer_id
FROM customers
WHERE full_name = 'Alice';
~~~

Trong cấu hình so sánh nhị phân phân biệt chữ hoa/thường thông thường, `'Alice'` khác `'ALICE'`. Oracle có khả năng cấu hình collation và những quy tắc so sánh ngôn ngữ theo phiên bản/session/cột, nên hành vi so sánh chuỗi có thể thay đổi. Quy tắc tên identifier **không tự bị đảo ngược** khi người quản trị thay collation để tìm kiếm chuỗi không phân biệt chữ hoa/thường.

Muốn thực hiện phép tìm kiếm không phân biệt chữ hoa/thường theo cách rõ ràng trong một ví dụ đơn giản, có thể viết:

~~~sql
SELECT customer_id, full_name
FROM customers
WHERE UPPER(full_name) = 'ALICE';
~~~

Phép biến đổi trên cột có thể ảnh hưởng cách sử dụng index; ứng dụng thực tế nên chọn collation, function-based index hoặc chiến lược tìm kiếm được thiết kế phù hợp. Những lựa chọn này **liên quan giá trị chuỗi**, không phải lý do dùng `"FullName"` cho tên cột.

| Bạn đang xét | Ví dụ | Quy tắc cần nhớ |
| --- | --- | --- |
| Tên cột không quote | `full_name` và `FULL_NAME` | Thường cùng identifier `FULL_NAME` |
| Tên cột quoted | `"FullName"` và `"FULLNAME"` | Hai identifier khác nhau |
| Giá trị chuỗi | `'Alice'` và `'ALICE'` | Kết quả so sánh phụ thuộc collation/cấu hình và toán tử |
| Từ khóa SQL | `select` và `SELECT` | Cùng từ khóa SQL, không phải tên đối tượng |

## 7. Schema, current schema và namespace của đối tượng

### 7.1. Phân giải tên khi không ghi owner

Với một tên không đủ điều kiện như `DEMO_NAMES`, Oracle cần xác định object trong ngữ cảnh schema của phiên, synonym và đặc quyền. Trong nhiều trường hợp đơn giản, đó là bảng thuộc schema hiện tại.

~~~sql
-- Ket noi voi user so huu DEMO_NAMES.
SELECT item_id
FROM demo_names;

-- Neu bang thuoc LAB_SCHEMA va session co quyen truy cap:
SELECT item_id
FROM LAB_SCHEMA.DEMO_NAMES;
~~~

Nếu owner được tạo bằng nonquoted identifier `lab_schema`, Oracle lưu tên là `LAB_SCHEMA`. Nếu owner được tạo bằng quoted identifier `"LabSchema"`, tham chiếu `LAB_SCHEMA.DEMO_NAMES` sẽ không tự ánh xạ sang `"LabSchema"`.

### 7.2. `CURRENT_SCHEMA` không biến bạn thành user khác

Một session có thể đặt schema mặc định cho việc phân giải tên không ghi owner:

~~~sql
-- Vi du chi thuc hien neu schema APP_SCHEMA co ton tai
-- va ban da duoc cap quyen tren cac object can truy cap.
ALTER SESSION SET CURRENT_SCHEMA = APP_SCHEMA;

SELECT * FROM DEMO_NAMES;
~~~

Thao tác `CURRENT_SCHEMA` **không thay đổi danh tính đăng nhập** (`SESSION_USER`) và **không cấp thêm quyền** trên bảng. Đây chỉ là một phần của cơ chế phân giải tên. Nếu muốn truy cập chính xác một đối tượng có quoted name, quy tắc trích dẫn vẫn phải tuân thủ.

Kiểm tra ngữ cảnh phiên:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

### 7.3. Tên object trùng nhau ở các namespace

Oracle phân loại nhiều schema object vào các **namespace**. Ví dụ, table, view và một số loại object khác dùng chung một nhóm quy tắc về tên; index và constraint có những namespace riêng theo quy định. Vì vậy:

- Không thể mặc định mọi loại object đều được phép có cùng tên trong một schema.
- Cũng không thể mặc định một tên xuất hiện trong `USER_OBJECTS` chỉ được phép xuất hiện một lần dưới mọi `OBJECT_TYPE`.
- Quoted/unquoted và chữ hoa/chữ thường chỉ là **một phần** của kiểm tra trùng tên; loại object và namespace cũng quyết định kết quả.

Nếu Oracle báo `ORA-00955: name is already used by an existing object`, hãy tìm object hiện hữu trong `USER_OBJECTS` và kiểm tra tên/loại đối tượng đúng cách. Không nên khắc phục bằng việc tạo tên chỉ khác chữ hoa/thường rồi bỏ qua ý nghĩa nghiệp vụ.

## 8. Những lỗi thường gặp và cách đọc dấu hiệu

| Tình huống | Lỗi có thể gặp | Nguyên nhân cần kiểm tra |
| --- | --- | --- |
| `SELECT DisplayName FROM DEMO_NAMES` nhưng cột được tạo là `"DisplayName"` | `ORA-00904` | Oracle tìm `DISPLAYNAME`, không có cột tương ứng |
| `SELECT * FROM Invoices` khi chỉ có bảng `"Invoices"` | `ORA-00942` | Oracle tìm `INVOICES`; lưu ý quyền và owner cũng có thể gây lỗi này |
| Tạo `CREATE TABLE ORDERS` khi đã tồn tại `orders` unquoted | `ORA-00955` | Cả hai là identifier `ORDERS` trong cùng namespace |
| Lệnh có tên bảng chứa dấu cách nhưng không quote | Lỗi cú pháp hoặc định danh | Dấu cách tách token SQL; phải quote tên đã tạo có dấu cách |
| Truy vấn metadata không thấy `"Invoices"` khi lọc `TABLE_NAME='INVOICES'` | Không có dòng kết quả | Đang so sánh giá trị chuỗi metadata khác chữ hoa/thường |
| Java/JDBC/ORM báo table/column không tồn tại | Thường `ORA-00942`, `ORA-00904` | SQL do framework sinh ra có thể quote sai hoặc chuẩn hóa tên khác DDL |
| Query thành công nhưng trả dữ liệu của bảng khác tên gần giống | Có thể không báo lỗi | Trong schema có cả `ORDERS` và `"Orders"`, cần kiểm tra tên chính xác |
| `"Alias"` trong SQL được tham chiếu bằng `alias` không quote | Thường `ORA-00904` | Alias quoted phải được tham chiếu đúng chữ hoa/thường |

### 8.1. Quy trình chẩn đoán sai tên đối tượng

Nếu gặp `ORA-00904` hoặc `ORA-00942`:

1. Xác định **user và current schema** của phiên: `SESSION_USER` và `CURRENT_SCHEMA`; trong CDB, kiểm tra thêm `CON_NAME`.
2. Xác định object thực sự thuộc **schema nào** và đã có quyền truy cập hay chưa.
3. Dùng `USER_OBJECTS`/`USER_TABLES` hoặc `ALL_OBJECTS`/`ALL_TABLES` để lấy **tên chính xác**, bao gồm kiểu viết hoa.
4. Dùng `USER_TAB_COLUMNS` hoặc `ALL_TAB_COLUMNS` để lấy **tên cột chính xác**.
5. Đối chiếu SQL: quoted identifiers có đủ và đúng chỗ không? Có nhầm `'value'` với `"Identifier"` không?
6. Nếu SQL do ứng dụng sinh, kiểm tra **SQL thực tế được gửi tới Oracle**, thay vì chỉ nhìn annotation/entity field.

Một lỗi `ORA-00942` **không luôn có nghĩa table không tồn tại**: thiếu quyền, sai schema, synonym trỏ sai, PDB khác hoặc object tên gần giống đều là nguyên nhân có thể. Tương tự, `ORA-00904` có thể do alias/phạm vi SQL không hợp lệ, chứ không phải mọi trường hợp đều do case.

### 8.2. SQL tối thiểu để tìm tên thật

~~~sql
-- Kiem tra pham vi phien.
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;

-- Liet ke table cua schema dang dang nhap, giu nguyen chu hoa/thuong.
SELECT table_name
FROM user_tables
ORDER BY table_name;

-- Liet ke cot cua bang thuong DEMO_NAMES.
SELECT column_name, data_type
FROM user_tab_columns
WHERE table_name = 'DEMO_NAMES'
ORDER BY column_id;

-- Neu can tim mot object co ten gan giong:
SELECT object_name, object_type
FROM user_objects
WHERE UPPER(object_name) LIKE '%INVOICE%'
ORDER BY object_type, object_name;
~~~

Lưu ý: `USER_*` liệt kê đối tượng thuộc **schema của user tương ứng**, không tự chuyển theo `ALTER SESSION SET CURRENT_SCHEMA` để liệt kê object của một user khác. Khi cần xem object do schema khác sở hữu, dùng các view `ALL_*` với điều kiện `OWNER` và quyền phù hợp.

## 9. Quy ước đặt tên cho schema và metadata dễ bảo trì

### 9.1. Khuyến nghị cho dự án Oracle thông thường

Một quy ước thực hành đơn giản là:

- Đặt tên table/column/constraint/index **không quoted** với các ký tự ASCII, gạch dưới khi cần phân tách từ.
- Giữ độ dài trong giới hạn phiên bản Oracle thấp nhất mà dự án hỗ trợ.
- Dùng tên có ý nghĩa nghiệp vụ như `CUSTOMER_ORDERS`, `ORDER_ID`, `CREATED_AT`; tránh đặt tên trùng từ khóa SQL.
- Tách schema/PDB rõ ràng theo môi trường và quyền truy cập; không giải quyết xung đột bằng những tên chỉ khác chữ hoa/thường.
- Chọn một chiến lược thống nhất cho migration, ORM, SQL viết tay và reporting tool.

Ví dụ cách đặt tên phổ biến:

~~~sql
CREATE TABLE customer_orders (
    order_id      NUMBER PRIMARY KEY,
    customer_id   NUMBER NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

SELECT order_id, customer_id, created_at
FROM customer_orders;
~~~

Oracle sẽ lưu `CUSTOMER_ORDERS`, `ORDER_ID`, `CUSTOMER_ID` và `CREATED_AT`, còn người viết SQL có thể dùng kiểu chữ theo chuẩn coding style của nhóm mà không cần trích dẫn lặp lại.

### 9.2. Khi nào thật sự nên dùng quoted identifier?

Quoted identifier có thể phù hợp khi:

- Bạn phải duy trì tương thích với một **schema đã tồn tại** có tên chứa chữ hoa/thường hỗn hợp hoặc dấu cách.
- Cần truy cập đối tượng nhập từ công cụ/hệ thống khác có quy ước tên bắt buộc.
- Một giao diện SQL được quản lý rõ ràng yêu cầu label/alias đầu ra có kiểu viết nhất định.

Nếu chỉ muốn tên cột hiển thị đẹp trong báo cáo, sử dụng **quoted column alias** ở câu `SELECT` thường phù hợp hơn việc đổi tên cột vật lý:

~~~sql
SELECT
    order_id AS "Order ID",
    customer_id AS "Customer",
    created_at AS "Created At"
FROM customer_orders;
~~~

Tên cột thật vẫn chuẩn và không đòi hỏi quote trong mọi truy vấn nghiệp vụ; các alias trong kết quả có thể tùy chỉnh để phục vụ giao diện.

### 9.3. Quản lý tên khi hệ thống đã có quoted objects

Nếu bắt buộc làm việc với bảng `"Invoices"`:

- Sử dụng **tên đúng từ metadata** và ghi đủ dấu ngoặc kép trong SQL.
- Không đổi `"Invoices"` thành `INVOICES` trong migration chỉ vì muốn thống nhất chữ hoa; đó có thể là đối tượng khác.
- Kiểm tra các truy vấn/view, foreign key, synonym, script, mapping và quyền phụ thuộc trước khi rename.
- Cân nhắc thêm layer view/synonym theo quy định để trình bày giao diện đặt tên dễ dùng hơn, nhưng phải hiểu namespace và quyền.

Một đổi tên trong database có thể làm SQL của ứng dụng hiện có không phân giải được; DDL của Oracle thường commit thay đổi, nên không coi thao tác rename là một thử nghiệm có thể tự rollback như một `UPDATE` chưa commit.

## 10. Liên hệ Java/JDBC, ORM và SQL sinh tự động

### 10.1. JDBC không tự sửa tên quoted giúp bạn

Giả sử schema có bảng `DEMO_NAMES` và cột `"DisplayName"` như trên. Một câu SQL JDBC đúng có thể là:

~~~java
String sql = """
    SELECT item_id, "DisplayName"
    FROM demo_names
    WHERE item_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1L);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong(1);
            String name = rs.getString(2);
            System.out.println(id + " -> " + name);
        }
    }
}
~~~

Ở đây Java text block giữ nguyên hai dấu quote bên trong SQL, giúp Oracle nhận đúng cột `"DisplayName"`. Dấu `?` là **bind parameter cho giá trị** `item_id`; nó không đại diện cho tên table/column. Bạn không thể dùng `FROM ?` rồi bind tên bảng như một chuỗi thông thường.

Khi SQL được tạo động từ tên đối tượng, hãy dùng **allowlist tên cho phép**, kiểm tra định danh theo quy tắc Oracle và dùng cơ chế quote/validation được hỗ trợ (ví dụ `DBMS_ASSERT` trong ngữ cảnh PL/SQL phù hợp). Không nối tên object không đáng tin trực tiếp vào câu SQL rồi giả định dấu quote đã loại bỏ SQL injection.

### 10.2. ORM có thể sinh SQL khác tên bạn kỳ vọng

Các framework ORM như Hibernate/JPA có naming strategy và cơ chế quote identifier riêng. Ví dụ:

- Mapping Java `displayName` có thể được chuyển thành một tên cột theo chiến lược đặt tên, chẳng hạn `DISPLAY_NAME`.
- Nếu table được tạo là `"OrderItem"` nhưng ORM sinh `ORDERITEM` không quote, Oracle sẽ tìm tên khác.
- Nếu bật cơ chế **globally quoted identifiers**, ORM có thể quote mọi tên; điều này đòi hỏi migration và bảng đã tồn tại phải tương thích chính xác với kiểu chữ mà ORM phát ra.

Khi gặp `ORA-00904`/`ORA-00942` trong Java, hãy xem **SQL đã được ORM sinh ra**, đối chiếu `USER_TABLES`/`USER_TAB_COLUMNS`, schema hiện tại và quy tắc mapping. Không suy luận từ tên class Java rằng Oracle tự lưu object cùng cách viết chữ của class.

### 10.3. Metadata APIs và tên cột trong ResultSet

JDBC có `DatabaseMetaData` để khám phá table/column; khi dùng pattern hoặc kiểm tra tên theo metadata, cần hiểu rằng các trường hợp quoted identifier có thể tồn tại dưới nhiều kiểu chữ. Việc thay mọi tên thành uppercase có thể làm mất khả năng truy cập đúng object đã được tạo với quoted mixed-case.

Tương tự, tên cột trả về trong `ResultSet` có thể là **column label** từ alias:

~~~sql
SELECT "DisplayName" AS "displayName"
FROM demo_names;
~~~

Trong truy vấn này, tên vật lý là `DisplayName`, còn label của kết quả là `displayName`. Khi xuất JSON hay mapping DTO, cần biết bạn đang đọc **tên cột database** hay **alias của truy vấn**.

## 11. Bài thực hành hoàn chỉnh

Các bước dùng schema riêng đang kết nối vào đúng PDB. Nếu đã có bảng trùng tên, thay tiền tố tên trong bài hoặc tạo schema lab mới theo quy trình của người quản trị. Không chạy lệnh DDL trên schema ứng dụng đang phục vụ người dùng.

### Bước 1 — Xác nhận schema và container

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name
FROM dual;
~~~

Ghi lại user/schema hiện tại. Nếu đang ở `CDB$ROOT` hoặc dùng tài khoản hệ thống không dành cho bài tập, hãy kết nối đúng user ứng dụng của PDB.

### Bước 2 — Tạo bảng có hai loại identifier

~~~sql
CREATE TABLE demo_identifier_lab (
    id             NUMBER PRIMARY KEY,
    full_name      VARCHAR2(100),
    "DisplayLabel" VARCHAR2(100),
    "order-status" VARCHAR2(20)
);

INSERT INTO demo_identifier_lab
    (id, full_name, "DisplayLabel", "order-status")
VALUES
    (1, 'Alice', 'Alice (VIP)', 'NEW');

INSERT INTO DEMO_IDENTIFIER_LAB
    (ID, FULL_NAME, "DisplayLabel", "order-status")
VALUES
    (2, 'Bob', 'Bob (REGULAR)', 'PAID');

COMMIT;
~~~

Chú ý: `id`, `full_name` không quote nên có thể đổi kiểu chữ; `"DisplayLabel"` và `"order-status"` phải giữ nguyên chính tả và quote.

### Bước 3 — Truy vấn theo hai cách viết

~~~sql
SELECT ID, FULL_NAME, "DisplayLabel", "order-status"
FROM DEMO_IDENTIFIER_LAB
ORDER BY id;

SELECT id, full_name, "DisplayLabel", "order-status"
FROM demo_identifier_lab
ORDER BY ID;
~~~

Cả hai đều hợp lệ với cấu trúc vừa tạo. Thử viết `DisplayLabel` không quote hoặc `"displaylabel"` để quan sát lỗi trong lab:

~~~sql
-- Du kien ORA-00904 neu khong co cot DISPLAYLABEL.
SELECT DisplayLabel FROM demo_identifier_lab;

-- Du kien ORA-00904 neu khong co cot "displaylabel".
SELECT "displaylabel" FROM demo_identifier_lab;
~~~

Đây là ví dụ lỗi có chủ đích để nhận biết quy tắc identifier, không phải lệnh cần sửa bằng quyền hệ thống.

### Bước 4 — Quan sát Oracle thực sự lưu tên gì

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name = 'DEMO_IDENTIFIER_LAB';

SELECT column_id, column_name, data_type
FROM user_tab_columns
WHERE table_name = 'DEMO_IDENTIFIER_LAB'
ORDER BY column_id;
~~~

Kết quả mong đợi đối với tên cột:

~~~text
ID
FULL_NAME
DisplayLabel
order-status
~~~

Phân biệt metadata của tên object và giá trị dữ liệu đã insert. Tên metadata viết hoa/thường theo quoted rule; `Alice` và `Bob` vẫn là nội dung của `FULL_NAME`.

### Bước 5 — Dùng alias hiển thị để tránh đổi tên vật lý

~~~sql
SELECT
    id AS "Id",
    full_name AS "Full name",
    "DisplayLabel" AS "Label",
    "order-status" AS "Status"
FROM demo_identifier_lab
ORDER BY "Id";
~~~

Các alias này chỉ áp dụng cho **kết quả truy vấn**, không thay đổi `USER_TAB_COLUMNS`.

### Bước 6 — Dọn bảng lab khi không cần nữa

~~~sql
-- Chi chay sau khi chac chan bang la do ban tao cho lab.
DROP TABLE demo_identifier_lab PURGE;
~~~

Lệnh `DROP TABLE ... PURGE` xóa bảng và bỏ qua recycle bin, nên **không thể dựa vào Flashback Drop để lấy lại bảng vừa purge**. Nếu chưa chắc chắn dữ liệu có cần giữ không, bỏ qua bước này hoặc thực hiện quy trình dọn dẹp được người quản trị phê duyệt. Không xóa bất kỳ bảng nào chỉ vì tên “trông giống” bảng lab.

## 12. Câu hỏi kiểm tra hiểu biết

1. `CREATE TABLE customer_orders (...)` được thực hiện không quote. Những câu `SELECT * FROM customer_orders`, `CUSTOMER_ORDERS` và `"CUSTOMER_ORDERS"` có cùng tham chiếu không?
2. Vì sao `"CustomerOrders"` khác `CUSTOMERORDERS`?
3. Oracle lưu tên cột nào nếu bạn tạo `"DeliveryDate"`? Làm sao viết `SELECT` cột đó?
4. Đặt `"Order Status"` làm tên cột có lợi ích và bất tiện nào?
5. Dấu `'...'` và `"..."` có ý nghĩa gì trong Oracle SQL?
6. Tại sao lọc `USER_TABLES.TABLE_NAME='INVOICES'` có thể không thấy bảng tạo bằng `"Invoices"`?
7. Một schema có cả `ORDERS` và `"Orders"`. `SELECT * FROM Orders` truy vấn bảng nào?
8. Nếu class Java tên `OrderItem` mà SQL thực tế sinh ra `FROM ORDERITEM`, liệu nó tự truy vấn được bảng `"OrderItem"` không?
9. Tại sao chạy `ALTER SESSION SET CURRENT_SCHEMA = APP_SCHEMA` không tự cấp quyền đọc bảng ở `APP_SCHEMA`?
10. Chữ hoa/thường của identifier có giống quy tắc so sánh `'Alice'` với `'ALICE'` trong một cột `VARCHAR2` không?
11. Vì sao nên tránh các tên chỉ khác chữ hoa/thường khi thiết kế schema mới?
12. Oracle hiện đại thường giới hạn độ dài identifier theo **byte** hay theo số lượng ký tự hiển thị?

**Gợi ý trả lời:**

1. Có, cùng tra tên `CUSTOMER_ORDERS`, nếu cùng schema và ngữ cảnh.
2. Quoted name giữ chính xác `CustomerOrders`, còn unquoted được chuẩn hóa `CUSTOMERORDERS`.
3. Oracle giữ `DeliveryDate`; dùng `SELECT "DeliveryDate" ...`.
4. Có thể giữ tên hiển thị nguyên dạng, nhưng phải quote đúng trong mọi SQL/mapping.
5. `'...'` là literal chuỗi, `"..."` là identifier có quote.
6. `TABLE_NAME` giữ giá trị `Invoices`, còn điều kiện dùng string literal `'INVOICES'`.
7. Bảng `ORDERS`, không phải `"Orders"`.
8. Không; `ORDERITEM` và `"OrderItem"` là hai identifier khác nhau.
9. Nó thay ngữ cảnh name resolution, không đổi `SESSION_USER` hoặc quyền.
10. Không; so sánh dữ liệu chuỗi còn phụ thuộc collation/cấu hình.
11. Chúng dễ gây nhầm khi truy vấn, migration, export, tooling và thay đổi schema.
12. Theo **byte**, với giới hạn thay đổi theo phiên bản/loại đối tượng.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — Database Object Names and Qualifiers](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Database-Object-Names-and-Qualifiers.html): quy tắc nonquoted/quoted identifier, chữ hoa/thường, các ký tự và độ dài tên.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): định nghĩa `USER_OBJECTS`, `USER_TABLES`, `USER_TAB_COLUMNS`, `ALL_*` và `DBA_*`.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): cú pháp `CREATE TABLE`, `SELECT`, column alias và `ALTER SESSION`.
- [Oracle Database Globalization Support Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/): sự khác nhau giữa quy tắc tên identifier, bộ ký tự và so sánh chuỗi/collation.

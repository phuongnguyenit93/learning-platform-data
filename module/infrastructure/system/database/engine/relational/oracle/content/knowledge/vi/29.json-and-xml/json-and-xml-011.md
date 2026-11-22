# XMLSERIALIZE, XMLCAST và chuyển đổi giữa XML với dữ liệu quan hệ

Oracle Database cung cấp các kiểu dữ liệu và hàm SQL/XML để trao đổi dữ liệu giữa tài liệu XML và mô hình bảng quan hệ. Khi một ứng dụng nhận XML, database có thể phân tích nội dung thành `XMLTYPE`, dùng XQuery hoặc `XMLTABLE` để tách các nút thành hàng và cột SQL. Theo chiều ngược lại, các hàm tạo XML như `XMLELEMENT`, `XMLFOREST` và `XMLAGG` có thể ghép dữ liệu quan hệ thành cấu trúc XML. Cuối cùng, `XMLSERIALIZE` chuyển giá trị XML thành văn bản hoặc dữ liệu nhị phân để lưu trữ hay gửi ra ngoài; `XMLCAST` chuyển một giá trị XML có nội dung phù hợp thành kiểu SQL cụ thể.

Ba thao tác này có vai trò khác nhau:

- **XMLSERIALIZE:** chuyển một giá trị XML thành biểu diễn ký tự hoặc byte.
- **XMLCAST:** chuyển giá trị XML sang kiểu dữ liệu SQL như VARCHAR2, NUMBER hoặc DATE khi nội dung có thể chuyển đổi.
- **XMLTABLE:** chiếu các nút XML thành một tập hàng quan hệ, với từng cột được khai báo kiểu SQL.

Hiểu rõ từng bước giúp tránh nhầm lẫn giữa tài liệu XML, chuỗi XML và dữ liệu quan hệ đã được trích xuất.

## 1. XMLTYPE và cách Oracle biểu diễn XML

`XMLTYPE` là kiểu dữ liệu Oracle dùng để biểu diễn nội dung XML. Có thể dùng XMLTYPE trong biến PL/SQL, biểu thức SQL hoặc cột bảng. Một giá trị XMLTYPE được Oracle quản lý như dữ liệu XML, cho phép gọi các hàm SQL/XML và các thao tác XQuery.

Ví dụ tạo bảng lưu đơn hàng dưới dạng XML:

~~~sql
CREATE TABLE purchase_order_docs (
  po_id      NUMBER PRIMARY KEY,
  xml_doc    XMLTYPE,
  created_at TIMESTAMP DEFAULT SYSTIMESTAMP
);
~~~

Thêm một tài liệu XML:

~~~sql
INSERT INTO purchase_order_docs (po_id, xml_doc)
VALUES (
  1001,
  XMLTYPE(
    '<PurchaseOrder>
       <Reference>PO-1001</Reference>
       <Requestor>Nguyen An</Requestor>
       <Status>APPROVED</Status>
       <LineItems>
         <LineItem ItemNumber="1">
           <Description>Keyboard</Description>
           <Quantity>2</Quantity>
           <UnitPrice>45.50</UnitPrice>
         </LineItem>
         <LineItem ItemNumber="2">
           <Description>Mouse</Description>
           <Quantity>3</Quantity>
           <UnitPrice>18.00</UnitPrice>
         </LineItem>
       </LineItems>
     </PurchaseOrder>'
  )
);

COMMIT;
~~~

Hàm dựng `XMLTYPE(...)` phân tích chuỗi đầu vào thành một giá trị XMLTYPE. Nội dung phải là XML well-formed; thẻ phải đóng đúng, cấu trúc lồng nhau hợp lệ và tài liệu phải tuân theo quy tắc XML.

Có thể đọc một phần tử XML bằng các hàm SQL/XML:

~~~sql
SELECT XMLQUERY(
         '/PurchaseOrder/Reference/text()'
         PASSING xml_doc
         RETURNING CONTENT
       ) AS reference_xml
  FROM purchase_order_docs
 WHERE po_id = 1001;
~~~

Kết quả của XMLQUERY vẫn là một giá trị XMLTYPE. Nếu muốn lấy văn bản để hiển thị hoặc truyền sang ứng dụng, có thể dùng XMLSERIALIZE hoặc XMLCAST tùy mục đích.

## 2. XMLSERIALIZE: chuyển XMLTYPE thành văn bản hoặc byte

`XMLSERIALIZE` chuyển một giá trị XMLTYPE thành kiểu SQL có thể lưu hoặc truyền đi. Cú pháp tổng quát:

~~~sql
XMLSERIALIZE(
  { DOCUMENT | CONTENT } xml_value
  AS { VARCHAR2(size) | CLOB | BLOB }
  [ENCODING 'character_set']
  [VERSION 'xml_version']
  [NO INDENT | INDENT [SIZE = number]]
)
~~~

Các thành phần chính:

- `DOCUMENT`: dùng khi giá trị là một XML document có đúng một phần tử gốc.
- `CONTENT`: dùng khi giá trị có thể là một XML content/fragment, không nhất thiết là một document hoàn chỉnh.
- `AS`: chọn kiểu đầu ra, thường là VARCHAR2 cho kết quả nhỏ, CLOB cho XML văn bản lớn hoặc BLOB cho biểu diễn byte.
- `ENCODING`: chỉ định encoding khi đầu ra là BLOB.
- `VERSION`: chỉ định phiên bản XML trong khai báo XML khi cần.
- `INDENT` hoặc `NO INDENT`: điều khiển định dạng khoảng trắng và thụt lề.

### Serialize thành CLOB

~~~sql
SELECT XMLSERIALIZE(
         DOCUMENT xml_doc
         AS CLOB
         INDENT SIZE = 2
       ) AS xml_text
  FROM purchase_order_docs
 WHERE po_id = 1001;
~~~

Kết quả là một CLOB chứa tài liệu XML dạng văn bản. Dùng CLOB khi XML có thể lớn hơn giới hạn VARCHAR2 hoặc cần truyền cho tầng ứng dụng như nội dung ký tự.

### Serialize thành VARCHAR2

~~~sql
SELECT XMLSERIALIZE(
         DOCUMENT xml_doc
         AS VARCHAR2(4000)
         NO INDENT
       ) AS xml_text
  FROM purchase_order_docs
 WHERE po_id = 1001;
~~~

VARCHAR2 phù hợp với XML nhỏ. Nếu kết quả vượt giới hạn kiểu dữ liệu hoặc kích thước được chỉ định, câu lệnh có thể phát sinh lỗi. Không dùng VARCHAR2 cho tài liệu có kích thước không kiểm soát.

### Serialize thành BLOB

~~~sql
SELECT XMLSERIALIZE(
         DOCUMENT xml_doc
         AS BLOB
         ENCODING 'UTF-8'
       ) AS xml_bytes
  FROM purchase_order_docs
 WHERE po_id = 1001;
~~~

BLOB chứa byte đã được serialize theo encoding được chỉ định. Đây là lựa chọn phù hợp khi gửi XML qua giao thức byte-oriented, ghi ra file hoặc tích hợp với hệ thống cần encoding xác định. Khi nhận BLOB ở ứng dụng, phải giải mã theo đúng encoding đã dùng.

### DOCUMENT và CONTENT khác nhau

Một XML document phải có một phần tử gốc duy nhất. Ví dụ:

~~~xml
<Orders>
  <Order id="1"/>
  <Order id="2"/>
</Orders>
~~~

Đây là một document hợp lệ vì chỉ có một phần tử gốc `Orders`. Một fragment có thể chỉ gồm nhiều phần tử cạnh nhau:

~~~xml
<Order id="1"/>
<Order id="2"/>
~~~

Đây là XML content gồm hai phần tử, nhưng không phải một XML document độc lập với một root duy nhất. Dùng `DOCUMENT` cho document hoàn chỉnh và `CONTENT` cho fragment phù hợp. Nếu chọn sai, Oracle có thể báo lỗi khi serialize hoặc xử lý XML.

XMLSERIALIZE chỉ tạo biểu diễn XML đầu ra. Nó không tự biến từng phần tử thành các cột quan hệ và cũng không bảo đảm giữ nguyên cách xuống dòng, thụt lề hoặc cách viết lexical ban đầu của tài liệu. Nếu cần giữ nguyên byte đầu vào để lưu trữ nguyên trạng, hãy lưu byte gốc riêng thay vì kỳ vọng XMLTYPE serialize lại giống hệt chuỗi ban đầu.

## 3. XMLCAST: chuyển giá trị XML sang kiểu SQL

`XMLCAST` dùng để chuyển một giá trị XML thành kiểu dữ liệu SQL được chỉ định. Điều này hữu ích khi một biểu thức XML như XMLQUERY trả về nội dung của một phần tử, nhưng ứng dụng cần nhận VARCHAR2, NUMBER, DATE hoặc một kiểu SQL khác.

Cú pháp tổng quát:

~~~sql
XMLCAST(xml_value AS sql_datatype)
~~~

Ví dụ lấy mã tham chiếu dưới dạng VARCHAR2:

~~~sql
SELECT XMLCAST(
         XMLQUERY(
           '/PurchaseOrder/Reference/text()'
           PASSING xml_doc
           RETURNING CONTENT
         )
         AS VARCHAR2(30)
       ) AS reference_no
  FROM purchase_order_docs
 WHERE po_id = 1001;
~~~

Ví dụ lấy số lượng của một phần tử dưới dạng NUMBER:

~~~sql
SELECT XMLCAST(
         XMLQUERY(
           '/PurchaseOrder/LineItems/LineItem[1]/Quantity/text()'
           PASSING xml_doc
           RETURNING CONTENT
         )
         AS NUMBER
       ) AS first_item_quantity
  FROM purchase_order_docs
 WHERE po_id = 1001;
~~~

XMLCAST phù hợp khi biểu thức XML trả về một giá trị đơn có thể chuyển đổi sang kiểu SQL. Nếu đường dẫn không tìm thấy dữ liệu, trả về nhiều nút hoặc nội dung không chuyển đổi được, cần xác định cách xử lý theo hợp đồng dữ liệu và phiên bản Oracle đang dùng. Không nên dựa vào việc ép kiểu ngầm để che giấu dữ liệu sai.

### XMLCAST và XMLSERIALIZE không thay thế nhau

| Nhu cầu | API nên dùng | Kết quả |
|---|---|---|
| Lấy nội dung một nút XML thành VARCHAR2 | XMLCAST | Giá trị SQL dạng chuỗi |
| Lấy nội dung số từ XML thành NUMBER | XMLCAST | Giá trị SQL dạng số |
| Chuyển toàn bộ XML document thành CLOB | XMLSERIALIZE | Văn bản XML |
| Xuất XML thành byte UTF-8 | XMLSERIALIZE AS BLOB | Byte XML |
| Tách nhiều nút XML thành nhiều hàng và cột | XMLTABLE | Tập hàng quan hệ |

Ví dụ, nếu muốn hiển thị toàn bộ XML, dùng XMLSERIALIZE. Nếu muốn tính tổng Quantity bằng SQL, nên trích xuất Quantity thành NUMBER bằng XMLTABLE hoặc XMLCAST trước khi tính.

## 4. XMLTABLE: chuyển các nút XML thành hàng quan hệ

`XMLTABLE` là công cụ chính để biến cấu trúc XML thành bảng quan hệ. Nó nhận một XQuery row expression xác định các nút tạo thành hàng, rồi khai báo các cột SQL được trích xuất từ từng nút.

Cú pháp rút gọn:

~~~sql
XMLTABLE(
  xquery_expression
  PASSING xml_expression
  COLUMNS
    column_name sql_datatype PATH 'xquery_column_expression',
    ...
)
~~~

Với tài liệu đơn hàng ở phần đầu, mỗi nút `LineItem` sẽ trở thành một hàng:

~~~sql
SELECT p.po_id,
       x.item_number,
       x.description,
       x.quantity,
       x.unit_price
  FROM purchase_order_docs p,
       XMLTABLE(
         '/PurchaseOrder/LineItems/LineItem'
         PASSING p.xml_doc
         COLUMNS
           item_number NUMBER        PATH '@ItemNumber',
           description VARCHAR2(100) PATH 'Description',
           quantity    NUMBER        PATH 'Quantity',
           unit_price  NUMBER        PATH 'UnitPrice'
       ) x
 WHERE p.po_id = 1001
 ORDER BY x.item_number;
~~~

Kết quả quan hệ:

| PO_ID | ITEM_NUMBER | DESCRIPTION | QUANTITY | UNIT_PRICE |
|---:|---:|---|---:|---:|
| 1001 | 1 | Keyboard | 2 | 45.50 |
| 1001 | 2 | Mouse | 3 | 18.00 |

Trong ví dụ:

- Row expression `/PurchaseOrder/LineItems/LineItem` xác định một hàng cho mỗi LineItem.
- `@ItemNumber` lấy giá trị thuộc tính ItemNumber.
- `Description`, `Quantity` và `UnitPrice` lấy các phần tử con tương ứng.
- Các cột NUMBER và VARCHAR2 được chuyển đổi sang kiểu SQL đã khai báo.

Sau khi XMLTABLE tạo tập hàng, có thể dùng SQL thông thường để JOIN, GROUP BY, ORDER BY hoặc INSERT vào bảng quan hệ.

### Tính tổng từ dữ liệu XML

~~~sql
SELECT p.po_id,
       SUM(x.quantity * x.unit_price) AS calculated_total
  FROM purchase_order_docs p,
       XMLTABLE(
         '/PurchaseOrder/LineItems/LineItem'
         PASSING p.xml_doc
         COLUMNS
           quantity   NUMBER PATH 'Quantity',
           unit_price NUMBER PATH 'UnitPrice'
       ) x
 GROUP BY p.po_id;
~~~

Đây là một ví dụ quan trọng của chuyển đổi XML sang dữ liệu quan hệ: XMLTABLE cung cấp các giá trị có kiểu SQL, còn phép tính tổng được thực hiện bằng SQL engine.

## 5. Lấy nút cấp cao và nút lặp bằng nhiều XMLTABLE

Một tài liệu XML có thể chứa thông tin cấp đơn hàng và một mảng/phần tử lặp ở cấp chi tiết. Có thể dùng một XMLTABLE cho phần tử gốc rồi dùng XMLTABLE khác cho danh sách chi tiết.

Ví dụ lấy Reference và Requestor cùng các LineItem:

~~~sql
SELECT p.po_id,
       h.reference_no,
       h.requestor,
       i.item_number,
       i.description,
       i.quantity
  FROM purchase_order_docs p,
       XMLTABLE(
         '/PurchaseOrder'
         PASSING p.xml_doc
         COLUMNS
           reference_no VARCHAR2(30)  PATH 'Reference',
           requestor    VARCHAR2(100) PATH 'Requestor',
           items_xml    XMLTYPE       PATH 'LineItems'
       ) h,
       XMLTABLE(
         '/LineItems/LineItem'
         PASSING h.items_xml
         COLUMNS
           item_number NUMBER        PATH '@ItemNumber',
           description VARCHAR2(100) PATH 'Description',
           quantity    NUMBER        PATH 'Quantity'
       ) i
 WHERE p.po_id = 1001;
~~~

Ở đây cột `items_xml` nhận một phần XMLTYPE để làm đầu vào cho XMLTABLE thứ hai. Cách này làm rõ ranh giới giữa phần thông tin đơn hàng và phần danh sách dòng hàng. Nếu một tài liệu không có LineItems, phép nối XMLTABLE dạng inner như trên không tạo hàng kết quả cho tài liệu đó. Hãy chọn cách nối phù hợp nếu cần giữ đơn hàng không có dòng chi tiết.

## 6. Xử lý namespace trong XMLTABLE và XMLQUERY

XML namespace là một phần của tên phần tử. Hai phần tử có cùng local name nhưng namespace URI khác nhau không được xem là cùng một tên XML.

Ví dụ tài liệu có namespace:

~~~xml
<PurchaseOrder xmlns="urn:example:purchase-order">
  <Reference>PO-2001</Reference>
  <LineItems>
    <LineItem ItemNumber="1">
      <Description>Monitor</Description>
      <Quantity>1</Quantity>
    </LineItem>
  </LineItems>
</PurchaseOrder>
~~~

Nếu bỏ qua namespace trong đường dẫn, biểu thức `/PurchaseOrder/Reference` có thể không khớp phần tử. Hãy khai báo namespace trong XMLTABLE:

~~~sql
SELECT p.po_id,
       x.reference_no,
       x.item_number,
       x.description
  FROM purchase_order_docs p,
       XMLTABLE(
         XMLNAMESPACES('urn:example:purchase-order' AS "po"),
         '/po:PurchaseOrder/po:LineItems/po:LineItem'
         PASSING p.xml_doc
         COLUMNS
           reference_no VARCHAR2(30)  PATH '../../po:Reference',
           item_number  NUMBER        PATH '@ItemNumber',
           description  VARCHAR2(100) PATH 'po:Description'
       ) x;
~~~

Namespace prefix `po` trong XQuery chỉ là bí danh được khai báo trong câu SQL. Prefix trong tài liệu XML có thể khác; điều quan trọng là namespace URI phải khớp. Nếu tài liệu dùng namespace mặc định, vẫn phải khai báo URI và dùng prefix trong đường dẫn theo cách trên.

Khi xử lý XML từ nhiều hệ thống, hãy xác định rõ namespace URI và version schema. Không nên dùng `local-name()` để bỏ qua namespace như một giải pháp mặc định, vì cách đó có thể ghép nhầm các phần tử cùng tên nhưng thuộc các namespace khác nhau.

## 7. XMLQUERY và XMLCAST khi chỉ cần một giá trị

Khi chỉ cần một hoặc một vài giá trị vô hướng, XMLQUERY kết hợp XMLCAST có thể ngắn gọn hơn XMLTABLE. XMLQUERY thực thi biểu thức XQuery và trả về XMLTYPE; XMLCAST chuyển kết quả thành kiểu SQL.

Ví dụ lọc các đơn hàng đã được phê duyệt:

~~~sql
SELECT p.po_id,
       XMLCAST(
         XMLQUERY(
           '/PurchaseOrder/Status/text()'
           PASSING p.xml_doc
           RETURNING CONTENT
         )
         AS VARCHAR2(20)
       ) AS status
  FROM purchase_order_docs p
 WHERE XMLCAST(
         XMLQUERY(
           '/PurchaseOrder/Status/text()'
           PASSING p.xml_doc
           RETURNING CONTENT
         )
         AS VARCHAR2(20)
       ) = 'APPROVED';
~~~

Nếu cần nhiều thuộc tính từ cùng một tài liệu hoặc cần tạo nhiều hàng, XMLTABLE thường dễ đọc và hiệu quả hơn việc lặp lại nhiều XMLQUERY/XMLCAST.

Có thể kiểm tra sự tồn tại của một nút bằng XMLEXISTS:

~~~sql
SELECT p.po_id
  FROM purchase_order_docs p
 WHERE XMLEXISTS(
         '/PurchaseOrder[Status = "APPROVED"]'
         PASSING p.xml_doc
       );
~~~

XMLEXISTS trả về điều kiện đúng/sai theo việc XQuery có tạo ra kết quả hay không. Nó phù hợp cho điều kiện lọc, còn XMLCAST phù hợp khi cần lấy một giá trị có kiểu SQL.

## 8. Chuyển dữ liệu quan hệ thành XML

Ở chiều ngược lại, SQL/XML cung cấp các hàm dựng XML từ hàng và cột:

| Hàm | Vai trò |
|---|---|
| `XMLELEMENT` | Tạo một phần tử XML, có thể chứa text, thuộc tính hoặc XML con |
| `XMLATTRIBUTES` | Tạo thuộc tính cho phần tử |
| `XMLFOREST` | Tạo nhiều phần tử từ các biểu thức SQL |
| `XMLAGG` | Gom nhiều giá trị XML thành một XML content |
| `XMLROOT` | Thêm khai báo hoặc version cho XML trong các trường hợp cần thiết |
| `XMLSERIALIZE` | Serialize kết quả XML thành CLOB/VARCHAR2/BLOB |

Giả sử có bảng DEPARTMENTS và EMPLOYEES. Ta muốn xuất một phòng ban thành tài liệu XML, trong đó mỗi nhân viên là một phần tử con.

~~~sql
SELECT XMLSERIALIZE(
         DOCUMENT
         XMLELEMENT(
           "Department",
           XMLATTRIBUTES(d.department_id AS "id"),
           XMLELEMENT("Name", d.department_name),
           XMLELEMENT(
             "Employees",
             (
               SELECT XMLAGG(
                        XMLELEMENT(
                          "Employee",
                          XMLATTRIBUTES(e.employee_id AS "id"),
                          XMLFOREST(
                            e.first_name AS "FirstName",
                            e.last_name  AS "LastName",
                            e.salary     AS "Salary"
                          )
                        )
                        ORDER BY e.employee_id
                      )
                 FROM employees e
                WHERE e.department_id = d.department_id
             )
           )
         )
         AS CLOB
         INDENT SIZE = 2
       ) AS department_xml
  FROM departments d
 WHERE d.department_id = 50;
~~~

Phân tích cấu trúc:

1. `XMLELEMENT("Department", ...)` tạo phần tử gốc Department.
2. `XMLATTRIBUTES` đưa department_id vào thuộc tính id.
3. `XMLELEMENT("Name", ...)` tạo phần tử Name.
4. Truy vấn con lấy nhân viên thuộc phòng ban.
5. `XMLFOREST` tạo các phần tử FirstName, LastName và Salary.
6. `XMLAGG` gom các phần tử Employee thành một XML content.
7. `XMLSERIALIZE` chuyển XMLTYPE cuối cùng thành CLOB để ứng dụng nhận được văn bản.

Nếu phòng ban không có nhân viên, XMLAGG có thể trả về NULL và phần Employees sẽ không có phần tử con. Nếu hợp đồng XML yêu cầu luôn có một phần tử Employees rỗng, cần kiểm soát cách dựng node rỗng theo schema đầu ra.

## 9. Tạo XML cho nhiều nhóm dữ liệu bằng GROUP BY

Khi cần xuất nhiều phòng ban, có thể nhóm dữ liệu theo phòng ban và dùng XMLAGG để gom nhân viên:

~~~sql
SELECT XMLSERIALIZE(
         DOCUMENT
         XMLELEMENT(
           "Department",
           XMLATTRIBUTES(d.department_id AS "id"),
           XMLELEMENT("Name", d.department_name),
           XMLAGG(
             XMLELEMENT(
               "Employee",
               XMLATTRIBUTES(e.employee_id AS "id"),
               XMLFOREST(
                 e.first_name AS "FirstName",
                 e.salary AS "Salary"
               )
             )
             ORDER BY e.employee_id
           )
         )
         AS CLOB
       ) AS department_xml
  FROM departments d
  JOIN employees e
    ON e.department_id = d.department_id
 GROUP BY d.department_id, d.department_name
 ORDER BY d.department_id;
~~~

Trong truy vấn này, mỗi nhóm phòng ban tạo ra một tài liệu XML. Nếu cần một tài liệu duy nhất chứa tất cả phòng ban, có thể đặt các phần tử Department bên trong một XMLELEMENT gốc và dùng XMLAGG ở truy vấn con hoặc truy vấn bao ngoài.

## 10. XMLCAST trong chiều chuyển đổi từ SQL sang XML

Thông thường, các hàm dựng XML tự chuyển biểu thức SQL thành nội dung XML phù hợp. XMLCAST chủ yếu được dùng để ép một giá trị XML sang kiểu SQL. Khi cần đưa một biểu thức SQL có kiểu cụ thể vào một biểu thức XML, hãy chọn hàm dựng XML phù hợp như XMLELEMENT hoặc XMLFOREST và kiểm soát kiểu dữ liệu của biểu thức đầu vào.

Ví dụ, nếu muốn định dạng timestamp theo hợp đồng XML cụ thể, hãy chuyển thành chuỗi trước khi tạo phần tử:

~~~sql
SELECT XMLELEMENT(
         "CreatedAt",
         TO_CHAR(
           created_at,
           'YYYY-MM-DD"T"HH24:MI:SS'
         )
       ) AS created_at_xml
  FROM purchase_order_docs;
~~~

Việc định dạng rõ ràng giúp tránh phụ thuộc vào NLS settings của session. Với số thập phân, ngày và thời gian, hãy thống nhất format và timezone nếu XML được trao đổi giữa nhiều hệ thống.

## 11. Ánh xạ XML sang bảng quan hệ

Một ứng dụng thường gặp là nhận XML từ đối tác, tách thông tin header và detail rồi lưu vào hai bảng:

- PO_HEADERS(po_id, reference_no, requestor, status).
- PO_LINES(po_id, line_no, description, quantity, unit_price).

Ví dụ tạo bảng đích:

~~~sql
CREATE TABLE po_headers (
  po_id        NUMBER PRIMARY KEY,
  reference_no VARCHAR2(30),
  requestor    VARCHAR2(100),
  status       VARCHAR2(20)
);

CREATE TABLE po_lines (
  po_id       NUMBER,
  line_no     NUMBER,
  description VARCHAR2(100),
  quantity    NUMBER,
  unit_price  NUMBER,
  CONSTRAINT po_lines_pk PRIMARY KEY (po_id, line_no),
  CONSTRAINT po_lines_header_fk
    FOREIGN KEY (po_id) REFERENCES po_headers(po_id)
);
~~~

Nạp phần header:

~~~sql
INSERT INTO po_headers (
  po_id,
  reference_no,
  requestor,
  status
)
SELECT p.po_id,
       h.reference_no,
       h.requestor,
       h.status
  FROM purchase_order_docs p,
       XMLTABLE(
         '/PurchaseOrder'
         PASSING p.xml_doc
         COLUMNS
           reference_no VARCHAR2(30)  PATH 'Reference',
           requestor    VARCHAR2(100) PATH 'Requestor',
           status       VARCHAR2(20)  PATH 'Status'
       ) h
 WHERE p.po_id = 1001;
~~~

Nạp các dòng chi tiết:

~~~sql
INSERT INTO po_lines (
  po_id,
  line_no,
  description,
  quantity,
  unit_price
)
SELECT p.po_id,
       x.line_no,
       x.description,
       x.quantity,
       x.unit_price
  FROM purchase_order_docs p,
       XMLTABLE(
         '/PurchaseOrder/LineItems/LineItem'
         PASSING p.xml_doc
         COLUMNS
           line_no     NUMBER        PATH '@ItemNumber',
           description VARCHAR2(100) PATH 'Description',
           quantity    NUMBER        PATH 'Quantity',
           unit_price  NUMBER        PATH 'UnitPrice'
       ) x
 WHERE p.po_id = 1001;
~~~

Hai câu INSERT có thể chạy trong cùng một giao dịch. Nếu một phần dữ liệu không hợp lệ, ứng dụng có thể rollback toàn bộ để header và lines không bị lệch nhau. Trong hệ thống thực tế, nên có bước kiểm tra dữ liệu bắt buộc, khóa ngoại, trùng line number và các quy tắc nghiệp vụ trước khi commit.

## 12. Chuyển dữ liệu quan hệ thành một XML document hoàn chỉnh

Nếu hệ thống cần gửi dữ liệu đơn hàng đã chuẩn hóa thành XML cho một đối tác, có thể đọc PO_HEADERS và PO_LINES rồi dựng tài liệu:

~~~sql
SELECT XMLSERIALIZE(
         DOCUMENT
         XMLELEMENT(
           "PurchaseOrder",
           XMLELEMENT("Reference", h.reference_no),
           XMLELEMENT("Requestor", h.requestor),
           XMLELEMENT("Status", h.status),
           XMLELEMENT(
             "LineItems",
             (
               SELECT XMLAGG(
                        XMLELEMENT(
                          "LineItem",
                          XMLATTRIBUTES(l.line_no AS "ItemNumber"),
                          XMLFOREST(
                            l.description AS "Description",
                            l.quantity AS "Quantity",
                            l.unit_price AS "UnitPrice"
                          )
                        )
                        ORDER BY l.line_no
                      )
                 FROM po_lines l
                WHERE l.po_id = h.po_id
             )
           )
         )
         AS CLOB
         INDENT SIZE = 2
       ) AS purchase_order_xml
  FROM po_headers h
 WHERE h.po_id = 1001;
~~~

Đây là chiều ngược lại của phần nạp dữ liệu: các cột quan hệ được đặt vào element và attribute, các dòng con được gom bằng XMLAGG, sau đó serialize thành CLOB. Nếu đối tác yêu cầu namespace, thứ tự, tên thẻ, kiểu dữ liệu hoặc XML Schema cụ thể, cần thiết kế cấu trúc đầu ra theo hợp đồng tích hợp.

## 13. NULL, phần tử rỗng và dữ liệu thiếu

XML và SQL có cách biểu diễn giá trị thiếu khác nhau:

- SQL NULL có thể khiến XMLFOREST bỏ qua phần tử tương ứng.
- Phần tử XML tồn tại nhưng không có text node là phần tử rỗng, ví dụ `<Comment/>`.
- Phần tử có `xsi:nil="true"` biểu thị giá trị nil theo XML Schema khi tài liệu dùng namespace và schema phù hợp.
- Chuỗi rỗng và SQL NULL không phải lúc nào cũng có thể phân biệt giống nhau khi chuyển qua lại, đặc biệt với VARCHAR2 trong Oracle.

Ví dụ, nếu LastName là NULL, `XMLFOREST(last_name AS "LastName")` thường không tạo phần tử LastName. Nếu hợp đồng yêu cầu luôn có thẻ, hãy dựng XMLELEMENT riêng và kiểm soát cách biểu diễn giá trị rỗng hoặc nil.

Khi dùng XMLTABLE, nếu một phần tử không tồn tại, cột tương ứng có thể nhận NULL. Cần phân biệt trường hợp thiếu phần tử với trường hợp phần tử có giá trị rỗng nếu quy tắc nghiệp vụ yêu cầu. Có thể dùng XMLEXISTS để kiểm tra sự hiện diện trước khi chuyển đổi hoặc bổ sung cột trạng thái trong truy vấn.

## 14. Chuyển đổi kiểu dữ liệu và lỗi dữ liệu

Khi ánh xạ XML sang quan hệ, XMLTABLE cần chuyển nội dung XML sang kiểu SQL được khai báo:

| Dữ liệu XML | Kiểu SQL thường dùng | Điều cần kiểm tra |
|---|---|---|
| Mã, tên, mô tả | VARCHAR2 hoặc NVARCHAR2 | Độ dài, encoding, khoảng trắng |
| Số lượng, đơn giá | NUMBER | Ký pháp số, dấu thập phân, độ chính xác |
| Ngày | DATE hoặc TIMESTAMP | Định dạng ngày và timezone |
| Boolean | NUMBER(1) hoặc VARCHAR2 theo quy ước | Quy ước true/false và giá trị thiếu |
| Phần tử XML lồng nhau | XMLTYPE | Giữ cấu trúc để xử lý tiếp |

Không nên giả định mọi dữ liệu đầu vào đều đúng kiểu. Ví dụ, phần tử Quantity có thể chứa `two` thay vì số. Nếu ép trực tiếp sang NUMBER, truy vấn có thể phát sinh lỗi chuyển đổi. Có thể kiểm tra dữ liệu ở tầng tích hợp, dùng XQuery để xác nhận cấu trúc hoặc dùng các cơ chế chuyển đổi có xử lý lỗi phù hợp với phiên bản Oracle.

Với ngày tháng, nên quy định một định dạng trao đổi rõ ràng, ví dụ ISO 8601, và kiểm soát timezone. Không dựa vào NLS_DATE_FORMAT hoặc NLS_NUMERIC_CHARACTERS mặc định của session khi xử lý XML từ hệ thống bên ngoài.

## 15. Hiệu năng và cách thiết kế truy vấn

Khi XML được lưu trong bảng và truy vấn thường xuyên, hãy cân nhắc các điểm sau:

**Chỉ trích xuất những gì cần dùng:** XMLTABLE có thể khai báo nhiều cột, nhưng nếu một truy vấn chỉ cần một giá trị, XMLCAST kết hợp XMLQUERY hoặc một biểu thức SQL/XML đơn giản có thể dễ đọc hơn.

**Trích xuất nhiều trường trong một lần:** nếu cần nhiều cột từ cùng một nút lặp, XMLTABLE thường phù hợp hơn việc gọi XMLQUERY lặp lại cho từng cột.

**Dùng XMLIndex khi workload phù hợp:** với tài liệu lớn và truy vấn XQuery/XMLTABLE thường xuyên, XMLIndex có thể hỗ trợ truy cập các đường dẫn XML. Cấu hình index phụ thuộc cách lưu XML, phiên bản và mẫu truy vấn; hãy đo execution plan trước khi triển khai.

**Kiểm soát kích thước serialize:** không serialize tài liệu lớn sang VARCHAR2 chỉ để hiển thị hoặc truyền đi. Dùng CLOB hoặc BLOB theo yêu cầu và xử lý theo luồng ở tầng ứng dụng khi cần.

**Giới hạn phạm vi truy vấn:** lọc bảng quan hệ theo khóa hoặc điều kiện có chỉ mục trước khi xử lý XML nếu có thể. Điều này giúp tránh phân tích các tài liệu không cần thiết.

**Không serialize rồi parse lại nếu không cần:** nếu dữ liệu đã là XMLTYPE, hãy truyền XMLTYPE trực tiếp cho XMLTABLE/XMLQUERY. Việc chuyển thành chuỗi rồi dựng XMLTYPE lại tạo thêm chi phí và có thể làm mất một số thông tin về cách biểu diễn.

## 16. Những lỗi và hiểu lầm thường gặp

**Dùng XMLCAST để lấy toàn bộ XML:** XMLCAST hướng đến chuyển một giá trị XML thành kiểu SQL cụ thể. Nếu cần xuất cả document thành văn bản, dùng XMLSERIALIZE.

**Dùng XMLSERIALIZE để tạo cột quan hệ:** XMLSERIALIZE chỉ trả về chuỗi hoặc byte XML. Muốn tạo hàng và cột SQL, dùng XMLTABLE.

**Nhầm XML document với XML fragment:** DOCUMENT yêu cầu một document hoàn chỉnh; CONTENT cho phép fragment. Chọn sai có thể gây lỗi khi serialize.

**Bỏ qua namespace:** tên phần tử XML bao gồm namespace URI. Nếu tài liệu có namespace mà XQuery không khai báo, đường dẫn có thể không tìm thấy dữ liệu.

**Ép mọi giá trị thành VARCHAR2:** số, ngày và boolean nên được ánh xạ sang kiểu SQL thích hợp để tính toán, so sánh và kiểm tra dữ liệu đúng cách.

**Giả định thứ tự nút là thứ tự kết quả quan hệ:** nếu cần thứ tự xác định, dùng ORDER BY trong câu SQL. XMLTABLE tạo tập hàng; thứ tự cuối cùng cần được chỉ định rõ.

**Ghi đè dữ liệu thiếu bằng giá trị mặc định không kiểm soát:** cần xác định rõ trường bắt buộc, trường tùy chọn, phần tử rỗng và phần tử không tồn tại.

**Tạo XML bằng cách nối chuỗi thủ công:** nối chuỗi có thể làm sai escaping ký tự như dấu `&`, `<` hoặc dấu nháy. Dùng XMLELEMENT, XMLATTRIBUTES, XMLFOREST và XMLAGG để Oracle xử lý escaping và cấu trúc.

## 17. Quy trình tích hợp XML với bảng quan hệ

Một quy trình nhận và xử lý XML thường có các bước:

1. Nhận XML từ file, HTTP, message queue hoặc hệ thống nguồn.
2. Xác định encoding và kiểm tra XML well-formed.
3. Chuyển nội dung thành XMLTYPE hoặc lưu trong cột XMLTYPE.
4. Dùng XMLTABLE để trích xuất header và các phần tử lặp thành các hàng SQL.
5. Chuyển đổi từng trường sang kiểu SQL phù hợp và kiểm tra dữ liệu bắt buộc.
6. INSERT hoặc MERGE vào các bảng quan hệ trong cùng giao dịch.
7. Xử lý lỗi, rollback nếu dữ liệu không nhất quán và ghi nhận thông tin lỗi theo quy trình ứng dụng.
8. Khi cần gửi dữ liệu ra ngoài, dựng XML từ bảng quan hệ bằng các hàm SQL/XML rồi XMLSERIALIZE thành CLOB hoặc BLOB.

Quy trình này tách phần phân tích cấu trúc XML khỏi quy tắc nghiệp vụ quan hệ. XMLTABLE chịu trách nhiệm ánh xạ nút XML thành cột; constraint và SQL xử lý tính toàn vẹn; XMLSERIALIZE tạo biểu diễn cuối cùng cho hệ thống nhận.

## 18. Kết luận

`XMLSERIALIZE`, `XMLCAST` và `XMLTABLE` giải quyết ba nhu cầu khác nhau khi làm việc với XML trong Oracle Database. XMLSERIALIZE chuyển XMLTYPE thành văn bản hoặc byte; XMLCAST chuyển một giá trị XML sang kiểu SQL; XMLTABLE biến các nút XML thành hàng và cột quan hệ. Ở chiều ngược lại, XMLELEMENT, XMLATTRIBUTES, XMLFOREST và XMLAGG dựng tài liệu XML từ dữ liệu bảng.

Một luồng xử lý điển hình là nhận tài liệu vào XMLTYPE, dùng XMLTABLE để tách header và detail, lưu dữ liệu đã kiểm tra vào các bảng quan hệ, rồi khi cần xuất thì dựng XML và serialize thành CLOB hoặc BLOB. Hãy chú ý namespace, DOCUMENT so với CONTENT, đơn vị kiểu dữ liệu, NULL, encoding và hiệu năng truy vấn. Dùng đúng API ở từng bước sẽ giúp luồng trao đổi XML rõ ràng, an toàn và dễ bảo trì.

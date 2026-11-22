# XMLType, XMLTABLE, XMLQUERY và XMLEXISTS trong Oracle Database

## 1. XML trong cơ sở dữ liệu quan hệ

Nhiều hệ thống nghiệp vụ trao đổi dữ liệu bằng XML: đơn hàng, hóa đơn điện tử, thông điệp tích hợp, hồ sơ, dữ liệu cấu hình và tài liệu từ hệ thống bên ngoài. XML có cấu trúc phân cấp, hỗ trợ namespace và có thể chứa các phần tử lặp lại. Trong khi đó, Oracle Database lưu dữ liệu quan hệ theo bảng, hàng, cột và kiểu dữ liệu SQL.

Oracle XML DB cung cấp các kiểu dữ liệu và hàm SQL/XML để làm việc với XML ngay trong database. Bốn thành phần quan trọng:

- **XMLType:** kiểu dữ liệu Oracle dùng để lưu và biểu diễn XML.
- **XMLTABLE:** chuyển các node trong XML thành các hàng và cột quan hệ để JOIN, lọc, tổng hợp hoặc nạp dữ liệu.
- **XMLQUERY:** chạy biểu thức XQuery trên XML và trả về kết quả XMLType.
- **XMLEXISTS:** kiểm tra một biểu thức XQuery có trả về sequence không rỗng hay không; thường dùng làm điều kiện lọc trong WHERE.

Các thành phần này cho phép kết hợp dữ liệu XML với SQL mà không cần lấy toàn bộ tài liệu về ứng dụng để phân tích bằng code bên ngoài.

~~~text
XML document
     |
     v
  XMLType
     |
     +--------------------+
     |                    |
     v                    v
 XMLQUERY              XMLTABLE
 trích xuất/biến đổi    tách node thành row/column
     |                    |
     v                    v
 XMLType result       relational rows
     |                    |
     +---------+----------+
               |
               v
           SQL query
               |
               v
           XMLEXISTS
      lọc theo sự tồn tại node
~~~

> Bài học dùng Oracle Database 19c và các hàm SQL/XML phổ biến. XMLType có nhiều mô hình lưu trữ; cú pháp và tính năng có thể phụ thuộc phiên bản, loại XML, schema registration và cấu hình XML DB. Ví dụ cần chạy trong schema lab có quyền tạo table, index và truy vấn các dictionary views liên quan.

## 2. XML document, well-formed và valid

Trước khi lưu XML, cần phân biệt hai khái niệm.

### 2.1. Well-formed XML

XML well-formed tuân thủ cú pháp XML:

- Có đúng một document element ở cấp cao nhất khi dùng XML document.
- Tag mở và đóng đúng cặp.
- Phần tử lồng nhau đúng thứ tự.
- Attribute được đặt trong dấu nháy.
- Ký tự đặc biệt được escape hợp lệ.
- Không có nhiều root element trong một document.

Ví dụ well-formed:

~~~xml
<PurchaseOrder>
  <Reference>PO-1001</Reference>
  <Status>APPROVED</Status>
</PurchaseOrder>
~~~

Ví dụ không well-formed:

~~~xml
<PurchaseOrder>
  <Reference>PO-1001</Status>
</PurchaseOrder>
~~~

Tag mở Reference nhưng đóng Status.

### 2.2. Valid XML

Một XML document có thể well-formed nhưng không hợp lệ theo XML Schema (XSD). Ví dụ XSD yêu cầu Quantity là số nguyên dương, nhưng XML chứa abc.

- Well-formed kiểm tra cấu trúc cú pháp XML.
- Schema-valid kiểm tra document có tuân theo định nghĩa kiểu, cardinality, namespace và ràng buộc của XSD hay không.

Không phải mọi XMLType đều tự động được kiểm tra theo một XML Schema. Cần phân biệt XMLType không gắn schema với schema-based XMLType.

### 2.3. Namespace là một phần của tên XML

Hai phần tử có cùng local name nhưng khác namespace URI là hai tên khác nhau:

~~~xml
<a:Order xmlns:a="urn:company:order">
  <a:Id>100</a:Id>
</a:Order>
~~~

~~~xml
<b:Order xmlns:b="urn:partner:order">
  <b:Id>100</b:Id>
</b:Order>
~~~

a:Order và b:Order không giống nhau vì namespace URI khác nhau. Prefix a hoặc b chỉ là bí danh; định danh thực sự là namespace URI cộng local name.

## 3. XMLType là gì?

XMLType là kiểu dữ liệu Oracle dành cho XML. Nó cho phép lưu XML trong cột hoặc trong một XMLType table và cung cấp các hàm SQL/XML để truy vấn, biến đổi và tuần tự hóa nội dung.

### 3.1. XMLType column

Ví dụ tạo bảng lưu đơn hàng:

~~~sql
CREATE TABLE purchase_orders (
    po_id NUMBER PRIMARY KEY,
    document XMLTYPE
);
~~~

DOCUMENT là tên cột XMLType. Bảng vẫn có thể chứa các cột quan hệ như PO_ID, ngày tạo hoặc mã khách hàng bên cạnh XML.

### 3.2. XMLType table

Có thể tạo bảng mà mỗi row là một XMLType instance:

~~~sql
CREATE TABLE purchase_order_documents OF XMLTYPE;
~~~

Kiểu bảng này phù hợp khi đơn vị dữ liệu chính là toàn bộ XML document. Với ứng dụng cần khóa quan hệ, trạng thái xử lý hoặc metadata nghiệp vụ, XMLType column trong một bảng quan hệ thường thuận tiện hơn.

### 3.3. XMLType khác CLOB chứa XML

Một cột CLOB chỉ lưu văn bản. Database không tự hiểu nội dung đó là một XML value khi dùng các phép toán SQL thông thường.

Một cột XMLType biểu diễn dữ liệu theo mô hình XML và có thể được dùng trực tiếp với XMLTABLE, XMLQUERY, XMLEXISTS, XMLCAST và XMLSERIALIZE.

Nếu lưu XML dưới dạng CLOB, ứng dụng thường phải parse hoặc chuyển sang XMLType trước khi truy vấn bằng SQL/XML. Với workload XML thường xuyên, nên đánh giá lưu XMLType thay vì chỉ giữ chuỗi văn bản.

### 3.4. Mô hình lưu trữ XMLType

Oracle hỗ trợ các mô hình lưu trữ XMLType, nổi bật:

- **Binary XML:** biểu diễn XML theo định dạng nhị phân của Oracle XML DB; phù hợp với nhiều workload XML tổng quát và là lựa chọn phổ biến cho thiết kế mới.
- **Object-relational storage:** ánh xạ XML schema-based vào các đối tượng/cột quan hệ của Oracle; có thể hữu ích với một số mô hình schema-aware và truy vấn có cấu trúc.
- **CLOB-based storage:** mô hình cũ dựa trên văn bản, chủ yếu gặp ở hệ thống legacy; cần cân nhắc khi thiết kế mới.

Không nên chọn storage model chỉ theo thói quen. Hãy đo workload đọc/ghi, kích thước tài liệu, cách truy vấn path, schema registration, yêu cầu tương thích và khả năng index.

Ví dụ chỉ định Binary XML cho XMLType column:

~~~sql
CREATE TABLE purchase_orders_bin (
    po_id NUMBER PRIMARY KEY,
    document XMLTYPE
)
XMLTYPE COLUMN document STORE AS SECUREFILE BINARY XML;
~~~

Ví dụ trên chỉ minh họa lựa chọn storage. Việc tạo SecureFiles còn phụ thuộc cấu hình tablespace và database.

## 4. Tạo XMLType từ chuỗi và nạp dữ liệu

### 4.1. Dùng XMLType constructor

Trong lab hoặc khi tạo dữ liệu nhỏ, có thể dùng constructor:

~~~sql
INSERT INTO purchase_orders(po_id, document)
VALUES (
    1001,
    XMLTYPE(
        '<PurchaseOrder>
           <Reference>PO-1001</Reference>
           <Status>APPROVED</Status>
         </PurchaseOrder>'
    )
);
~~~

Constructor chuyển chuỗi thành XMLType. XML đầu vào phải có cú pháp hợp lệ.

### 4.2. Dùng XMLPARSE

XMLPARSE là hàm SQL/XML để parse XML text thành XMLType:

~~~sql
INSERT INTO purchase_orders(po_id, document)
VALUES (
    1002,
    XMLPARSE(
        DOCUMENT
        '<PurchaseOrder>
           <Reference>PO-1002</Reference>
           <Status>PENDING</Status>
         </PurchaseOrder>'
    )
);
~~~

DOCUMENT dùng cho một XML document có một root element. CONTENT dành cho XML content/fragment theo các quy tắc XML DB. Với dữ liệu đơn hàng thông thường, DOCUMENT là lựa chọn dễ hiểu.

Không dùng tùy chọn WELLFORMED một cách tùy tiện. Tùy chọn này là lời khẳng định từ caller rằng dữ liệu đã well-formed; nó không thay thế validation đúng cách.

### 4.3. Nạp XML từ bind variable

Trong ứng dụng, truyền XML payload qua bind variable thay vì nối chuỗi vào câu SQL:

~~~sql
INSERT INTO purchase_orders(po_id, document)
VALUES (:p_po_id, XMLTYPE(:p_xml_text));
~~~

Bind variable giúp phân tách dữ liệu khỏi SQL text, tránh lỗi quote và giảm nguy cơ SQL injection ở tầng SQL.

### 4.4. COMMIT

~~~sql
COMMIT;
~~~

Các ví dụ INSERT ở trên là DML thông thường. Ứng dụng hoặc script caller quản lý COMMIT/ROLLBACK theo transaction boundary.

## 5. XMLSERIALIZE: xuất XMLType thành SQL text

XMLType là kiểu dữ liệu XML. Khi cần hiển thị, gửi qua ứng dụng hoặc ghi ra file, dùng XMLSERIALIZE để tuần tự hóa thành CLOB/BLOB hoặc kiểu ký tự phù hợp.

~~~sql
SELECT XMLSERIALIZE(
           DOCUMENT document
           AS CLOB
           INDENT SIZE = 2
       ) AS xml_text
FROM purchase_orders
WHERE po_id = 1001;
~~~

Các thành phần:

- DOCUMENT: yêu cầu serialize một XML document.
- AS CLOB: trả nội dung dưới dạng CLOB.
- INDENT SIZE = 2: yêu cầu định dạng thụt lề để dễ đọc.

Nếu xử lý XML content fragment thay vì document, dùng dạng CONTENT phù hợp. Không giả định mọi XMLType value đều là một document hoàn chỉnh.

### 5.1. Không dựa vào cách xuống dòng để so sánh XML

Hai XML document có thể biểu diễn cùng dữ liệu nhưng khác khoảng trắng, prefix namespace hoặc thứ tự attribute. So sánh chuỗi XML đã serialize không phải lúc nào cũng tương đương so sánh ngữ nghĩa XML.

Nếu cần đối chiếu nghiệp vụ, hãy trích các node/giá trị có ý nghĩa hoặc dùng cơ chế XML-aware phù hợp. Không dùng so sánh CLOB nguyên văn như một cách duy nhất để xác định hai document tương đương.

### 5.2. XMLSerialize và các hàm cũ

Trong code mới, ưu tiên XMLSERIALIZE để xuất XMLType. Một số method cũ như getClobVal() vẫn có thể xuất hiện trong code legacy; không nên mặc định dùng method đó cho thiết kế mới nếu SQL/XML function đã đáp ứng yêu cầu.

## 6. XQuery và XPath trong Oracle

XMLQUERY, XMLTABLE và XMLEXISTS dùng biểu thức XQuery. XQuery là ngôn ngữ truy vấn XML, có cú pháp path expression tương tự XPath và hỗ trợ biến, predicate, sequence, function và biểu thức FLWOR.

### 6.1. Path expression

Với document:

~~~xml
<PurchaseOrder>
  <Reference>PO-1001</Reference>
  <Status>APPROVED</Status>
  <LineItems>
    <LineItem>
      <PartId>BK-01</PartId>
      <Quantity>2</Quantity>
    </LineItem>
  </LineItems>
</PurchaseOrder>
~~~

Một số path:

| Path | Ý nghĩa |
| --- | --- |
| /PurchaseOrder | Root element |
| /PurchaseOrder/Reference | Phần tử Reference trực tiếp |
| /PurchaseOrder/LineItems/LineItem | Tất cả LineItem dưới LineItems |
| //LineItem | LineItem ở bất kỳ cấp nào bên dưới context |
| @id | Attribute tên id của context element |
| text() | Text node của element |

Nên dùng path cụ thể thay vì // quá rộng nếu cấu trúc XML đã biết. Path chính xác giúp người đọc hiểu schema và có thể hỗ trợ optimizer/index phù hợp.

### 6.2. Predicate

Ví dụ chọn PurchaseOrder có Status APPROVED:

~~~xquery
/PurchaseOrder[Status = "APPROVED"]
~~~

Chọn LineItem có Quantity lớn hơn 5:

~~~xquery
/PurchaseOrder/LineItems/LineItem[Quantity > 5]
~~~

### 6.3. FLWOR expression

XQuery hỗ trợ for, let, where, order by, return:

~~~xquery
for $line in /PurchaseOrder/LineItems/LineItem
where xs:integer($line/Quantity) > 1
return $line
~~~

FLWOR hữu ích khi cần lọc hoặc tái cấu trúc sequence node. Đối với việc biến các node lặp thành hàng/cột quan hệ, XMLTABLE thường dễ kết hợp với SQL hơn.

### 6.4. Context item và biến XQuery

XQuery có thể truy cập context item hoặc biến được truyền qua SQL PASSING. Ví dụ:

~~~xquery
$doc/PurchaseOrder[Status = $wanted_status]
~~~

Trong SQL, $doc và $wanted_status được liên kết qua PASSING. Đây là cách truyền dữ liệu an toàn và rõ ràng hơn việc ghép giá trị trực tiếp vào chuỗi XQuery.

## 7. Namespace trong XML và XQuery

Namespace là nguyên nhân phổ biến khiến query XML trả về rỗng dù nhìn bằng mắt thấy element tồn tại.

### 7.1. XML dùng default namespace

Document:

~~~xml
<PurchaseOrder xmlns="urn:acme:purchase-order">
  <Reference>PO-1001</Reference>
  <Status>APPROVED</Status>
</PurchaseOrder>
~~~

Các element PurchaseOrder, Reference và Status thuộc namespace urn:acme:purchase-order. Chúng không nằm trong no-namespace.

Path sau sẽ không khớp:

~~~xquery
/PurchaseOrder/Reference
~~~

Vì query đang tìm element không namespace.

### 7.2. Khai báo prefix trong XMLTABLE

XMLTABLE hỗ trợ XMLNAMESPACES:

~~~sql
SELECT x.reference,
       x.status
FROM purchase_orders p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder'
    PASSING p.document
    COLUMNS
        reference VARCHAR2(30) PATH 'po:Reference',
        status    VARCHAR2(20) PATH 'po:Status'
) x;
~~~

Prefix po do query tự chọn; nó không cần giống prefix trong document. Điều quan trọng là namespace URI phải khớp.

### 7.3. Khai báo namespace trong XMLQUERY và XMLEXISTS

Với XMLQUERY/XMLEXISTS, có thể khai báo namespace trong XQuery prolog:

~~~sql
SELECT XMLSERIALIZE(
           DOCUMENT XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:Reference'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS CLOB
       ) AS reference_xml
FROM purchase_orders p;
~~~

XMLNAMESPACES của XMLTABLE là SQL/XML clause; còn XMLQUERY và XMLEXISTS có thể dùng declare namespace trong XQuery string. Không trộn hai cú pháp.

### 7.4. Namespace lồng nhau

Một document có thể dùng nhiều namespace:

~~~xml
<po:PurchaseOrder xmlns:po="urn:acme:po"
                  xmlns:addr="urn:acme:address">
  <po:Reference>PO-1001</po:Reference>
  <addr:ShipTo>
    <addr:City>Hanoi</addr:City>
  </addr:ShipTo>
</po:PurchaseOrder>
~~~

XMLTABLE:

~~~sql
XMLTABLE(
    XMLNAMESPACES(
        'urn:acme:po' AS "po",
        'urn:acme:address' AS "addr"
    ),
    '/po:PurchaseOrder'
    PASSING document
    COLUMNS
        reference VARCHAR2(30) PATH 'po:Reference',
        ship_city VARCHAR2(100) PATH 'addr:ShipTo/addr:City'
)
~~~

Mỗi namespace URI cần được khai báo với prefix tương ứng trong query.

## 8. XMLTABLE: chuyển XML thành hàng và cột quan hệ

XMLTABLE là công cụ quan trọng nhất khi muốn JOIN XML với dữ liệu quan hệ. Nó nhận XQuery row expression và một danh sách COLUMNS. Mỗi item trong sequence kết quả tạo thành một row.

### 8.1. Cú pháp tổng quát

~~~sql
XMLTABLE(
    [XMLNAMESPACES(...),]
    xquery_string
    [PASSING xml_expression [AS identifier], ...]
    COLUMNS
        column_name datatype PATH 'xquery_column_path',
        ...
)
~~~

Các phần:

- XMLNAMESPACES: khai báo namespace prefix cho XQuery/path.
- XQuery row expression: xác định node/sequence nào tạo ra row.
- PASSING: truyền XMLType và các giá trị SQL vào XQuery.
- COLUMNS: ánh xạ node/attribute thành SQL columns.

### 8.2. Tách thông tin header

Giả sử document trong purchase_orders.document:

~~~xml
<PurchaseOrder xmlns="urn:acme:purchase-order">
  <Reference>PO-1001</Reference>
  <Status>APPROVED</Status>
  <CustomerId>501</CustomerId>
  <LineItems>
    <LineItem>
      <PartId>BK-01</PartId>
      <Quantity>2</Quantity>
      <UnitPrice>15.50</UnitPrice>
    </LineItem>
    <LineItem>
      <PartId>PN-10</PartId>
      <Quantity>4</Quantity>
      <UnitPrice>3.25</UnitPrice>
    </LineItem>
  </LineItems>
</PurchaseOrder>
~~~

Lấy header thành một row:

~~~sql
SELECT p.po_id,
       h.reference,
       h.status,
       h.customer_id
FROM purchase_orders p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder'
    PASSING p.document
    COLUMNS
        reference   VARCHAR2(30) PATH 'po:Reference',
        status      VARCHAR2(20) PATH 'po:Status',
        customer_id NUMBER       PATH 'po:CustomerId'
) h;
~~~

Row expression /po:PurchaseOrder trả một node root, nên XMLTABLE tạo một row cho mỗi document có root phù hợp.

### 8.3. Tách các phần tử lặp thành nhiều row

Để lấy từng LineItem:

~~~sql
SELECT p.po_id,
       h.reference,
       l.line_no,
       l.part_id,
       l.quantity,
       l.unit_price
FROM purchase_orders p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder'
    PASSING p.document
    COLUMNS
        reference VARCHAR2(30) PATH 'po:Reference'
) h
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem'
    PASSING p.document
    COLUMNS
        line_no    FOR ORDINALITY,
        part_id    VARCHAR2(30) PATH 'po:PartId',
        quantity   NUMBER       PATH 'po:Quantity',
        unit_price NUMBER(12,2) PATH 'po:UnitPrice'
) l
ORDER BY p.po_id, l.line_no;
~~~

Kết quả quan hệ có một row cho mỗi LineItem. FOR ORDINALITY tạo số thứ tự trong sequence XMLTABLE trả về.

### 8.4. Row expression quyết định số hàng

Nếu XQuery row expression trả về:

- Empty sequence: XMLTABLE tạo 0 row.
- Một node: XMLTABLE tạo 1 row.
- Nhiều node: XMLTABLE tạo một row cho mỗi node.

Đây là khác biệt quan trọng giữa row expression và column PATH. Row expression quyết định số hàng; từng PATH trong COLUMNS quyết định giá trị cột của mỗi hàng.

### 8.5. Lấy attribute

Với XML:

~~~xml
<LineItem lineId="10">
  <PartId>BK-01</PartId>
  <Quantity>2</Quantity>
</LineItem>
~~~

XMLTABLE:

~~~sql
XMLTABLE(
    '/LineItem'
    PASSING document
    COLUMNS
        line_id NUMBER PATH '@lineId',
        part_id VARCHAR2(30) PATH 'PartId'
)
~~~

Ký hiệu @lineId truy cập attribute của context element.

### 8.6. Trả về XMLType column

Không phải mọi cột XMLTABLE đều phải là scalar. Có thể trả một phần XML dưới dạng XMLType:

~~~sql
XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem'
    PASSING document
    COLUMNS
        part_id VARCHAR2(30) PATH 'po:PartId',
        line_xml XMLTYPE PATH '.'
)
~~~

PATH '.' trả context item hiện tại. XMLType column hữu ích khi cần xử lý tiếp node con bằng XMLQUERY hoặc XMLTABLE khác.

### 8.7. Bảo toàn document không có node lặp

CROSS APPLY hoặc cách viết tương đương inner lateral join chỉ giữ parent row có ít nhất một node phù hợp. Nếu cần giữ đơn hàng dù chưa có LineItem, dùng OUTER APPLY:

~~~sql
SELECT p.po_id,
       l.part_id,
       l.quantity
FROM purchase_orders p
OUTER APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem'
    PASSING p.document
    COLUMNS
        part_id  VARCHAR2(30) PATH 'po:PartId',
        quantity NUMBER       PATH 'po:Quantity'
) l;
~~~

OUTER APPLY giữ parent row và trả NULL cho các cột XMLTABLE khi không có item tương ứng.

### 8.8. XMLTABLE và bind variables

Có thể truyền giá trị SQL vào XQuery:

~~~sql
SELECT p.po_id,
       x.part_id,
       x.quantity
FROM purchase_orders p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem[po:Quantity > $min_qty]'
    PASSING p.document,
            :p_min_qty AS "min_qty"
    COLUMNS
        part_id  VARCHAR2(30) PATH 'po:PartId',
        quantity NUMBER       PATH 'po:Quantity'
) x;
~~~

Giá trị :p_min_qty được truyền thành XQuery variable. Không ghép giá trị input vào chuỗi XQuery.

## 9. XMLQUERY: truy vấn và tạo XML result

XMLQUERY chạy XQuery expression và trả về XMLType. Nó phù hợp khi muốn trích một node, một sequence hoặc tạo cấu trúc XML mới.

### 9.1. Cú pháp tổng quát

~~~sql
XMLQUERY(
    'xquery_expression'
    [PASSING expr [AS identifier], ...]
    RETURNING CONTENT
)
~~~

RETURNING CONTENT chỉ định kết quả là XML content. XMLQUERY không trả một SQL scalar thông thường; khi cần VARCHAR2/NUMBER/DATE, có thể kết hợp XMLCAST hoặc XMLTABLE.

### 9.2. Lấy một node từ XMLType

~~~sql
SELECT XMLSERIALIZE(
           CONTENT XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:Reference'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS CLOB
       ) AS reference_xml
FROM purchase_orders p
WHERE p.po_id = 1001;
~~~

Kết quả XMLType là node Reference; XMLSERIALIZE chuyển kết quả thành CLOB để hiển thị hoặc truyền đi.

### 9.3. Trả sequence node

~~~sql
SELECT XMLSERIALIZE(
           CONTENT XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:LineItems/po:LineItem'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS CLOB
       ) AS line_items_xml
FROM purchase_orders p;
~~~

XQuery có thể trả về nhiều LineItem. Dùng CONTENT vì kết quả có thể là sequence/fragment chứ không nhất thiết là một document có root riêng.

### 9.4. Dùng FLWOR để tạo XML mới

Ví dụ chỉ trả các line có quantity lớn hơn 1:

~~~sql
SELECT XMLSERIALIZE(
           CONTENT XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                for $line in $d/po:PurchaseOrder/po:LineItems/po:LineItem
                where xs:integer($line/po:Quantity) > 1
                return $line'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS CLOB
           INDENT SIZE = 2
       ) AS filtered_lines
FROM purchase_orders p;
~~~

XQuery lọc sequence và trả lại các node phù hợp. Đây là phép biến đổi XML result; nó không UPDATE dữ liệu gốc trong cột DOCUMENT.

### 9.5. XMLQUERY không thay đổi XMLType lưu trữ

XMLQUERY chỉ tạo kết quả truy vấn. Nếu cần lưu kết quả, phải dùng INSERT hoặc UPDATE rõ ràng:

~~~sql
INSERT INTO archived_order_fragments(po_id, fragment)
SELECT p.po_id,
       XMLQUERY(
           'declare namespace po = "urn:acme:purchase-order";
            $d/po:PurchaseOrder/po:LineItems'
           PASSING p.document AS "d"
           RETURNING CONTENT
       )
FROM purchase_orders p
WHERE p.po_id = 1001;
~~~

Không nhầm XMLQUERY với XQuery Update Facility hoặc câu lệnh UPDATE SQL.

## 10. XMLCAST: chuyển XML result sang SQL scalar

XMLCAST chuyển XMLType value có nội dung phù hợp sang kiểu SQL.

Ví dụ lấy Reference thành VARCHAR2:

~~~sql
SELECT XMLCAST(
           XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:Reference/text()'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS VARCHAR2(30)
       ) AS reference
FROM purchase_orders p;
~~~

Ví dụ lấy Quantity thành NUMBER:

~~~sql
SELECT XMLCAST(
           XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:LineItems/po:LineItem[1]/po:Quantity/text()'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS NUMBER
       ) AS first_quantity
FROM purchase_orders p;
~~~

Nếu XML text không chuyển được sang kiểu đích, phép cast có thể phát sinh lỗi. Với dữ liệu từ đối tác, cần kiểm soát định dạng, miền giá trị và trường hợp node thiếu.

### 10.1. Chuyển ngày giờ có định dạng rõ

Không phụ thuộc NLS_DATE_FORMAT của session khi chuyển chuỗi ngày từ XML. Có thể trích chuỗi rồi dùng TO_TIMESTAMP/TO_TIMESTAMP_TZ với format model tường minh.

Ví dụ chuỗi 2025-03-08T09:30:00+07:00:

~~~sql
TO_TIMESTAMP_TZ(
    l_timestamp_text,
    'YYYY-MM-DD"T"HH24:MI:SSTZH:TZM'
)
~~~

Định dạng thực tế phải khớp lexical format của XML schema/đối tác. Cần xác định timezone, offset và cách xử lý giá trị không có timezone.

### 10.2. XMLTABLE thường tiện hơn khi trích nhiều scalar

Nếu cần 5 cột từ cùng một node, dùng một XMLTABLE với 5 PATH expressions thường rõ hơn việc gọi XMLQUERY/XMLCAST lặp lại cho từng cột.

XMLCAST phù hợp khi chỉ cần chuyển một XML result thành một scalar hoặc khi biểu thức XMLQUERY đã được định nghĩa sẵn.

## 11. XMLEXISTS: kiểm tra sự tồn tại của node/sequence

XMLEXISTS đánh giá XQuery và trả kết quả SQL condition. Nó thường được dùng trong WHERE để lọc các XML documents theo nội dung.

### 11.1. Cú pháp tổng quát

~~~sql
XMLEXISTS(
    'xquery_expression'
    [PASSING expr [AS identifier], ...]
)
~~~

XMLEXISTS trả TRUE nếu XQuery trả về sequence không rỗng; trả FALSE nếu sequence rỗng.

### 11.2. Tìm đơn hàng có trạng thái APPROVED

~~~sql
SELECT p.po_id
FROM purchase_orders p
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder[po:Status = $wanted]'
    PASSING p.document AS "d",
            'APPROVED' AS "wanted"
);
~~~

XQuery trả về node PurchaseOrder nếu Status khớp APPROVED; nếu không khớp, trả empty sequence.

### 11.3. Kiểm tra có ít nhất một LineItem Quantity lớn hơn 5

~~~sql
SELECT p.po_id
FROM purchase_orders p
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder/po:LineItems/po:LineItem[
         xs:integer(po:Quantity) > 5
     ]'
    PASSING p.document AS "d"
);
~~~

Không cần trích toàn bộ LineItem về ứng dụng. Database chỉ cần đánh giá điều kiện tồn tại phù hợp với query.

### 11.4. Cạm bẫy: XMLEXISTS không kiểm tra giá trị boolean

XMLEXISTS kiểm tra sequence có item hay không, không kiểm tra item đó là boolean TRUE hay FALSE.

Ví dụ:

~~~sql
XMLEXISTS('false()' PASSING document)
~~~

Biểu thức false() trả về một sequence chứa một item boolean có giá trị FALSE. Sequence đó vẫn không rỗng, nên XMLEXISTS trả TRUE.

Tương tự, không viết XQuery trả về một giá trị boolean đơn rồi kỳ vọng XMLEXISTS kiểm tra truth value. Hãy viết path/predicate sao cho kết quả là node sequence có node khi điều kiện đúng và empty sequence khi điều kiện sai.

Ví dụ đúng:

~~~xquery
$d/PurchaseOrder[Status = "APPROVED"]
~~~

Điều kiện predicate làm sequence rỗng khi Status không phù hợp.

### 11.5. XMLEXISTS và node thiếu

Nếu path không tìm thấy node, XQuery thường trả empty sequence; XMLEXISTS trả FALSE. Điều này hữu ích để kiểm tra optional element:

~~~sql
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder/po:Approval'
    PASSING document AS "d"
)
~~~

Điều kiện trên chỉ kiểm tra element Approval tồn tại. Nếu cần kiểm tra giá trị cụ thể, thêm predicate.

## 12. Phân biệt XMLTABLE, XMLQUERY, XMLEXISTS và XMLCAST

| Thành phần | Đầu vào | Kết quả | Dùng khi |
| --- | --- | --- | --- |
| XMLType | XML text/schema/XML value | XMLType value | Lưu và biểu diễn XML |
| XMLTABLE | XQuery row expression + XML | SQL rows/columns | Tách XML để JOIN, lọc, tổng hợp |
| XMLQUERY | XQuery expression + XML | XMLType | Trích hoặc tạo XML result |
| XMLEXISTS | XQuery expression + XML | SQL condition | Lọc document theo node/điều kiện tồn tại |
| XMLCAST | XMLType value | SQL scalar | Chuyển XML result sang NUMBER/VARCHAR2/... |
| XMLSERIALIZE | XMLType value | CLOB/BLOB/character | Xuất XML thành text/binary |
| XMLPARSE | XML text | XMLType | Parse text thành XML value |

Ví dụ kết hợp:

~~~sql
SELECT p.po_id,
       x.reference,
       x.status
FROM purchase_orders p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder'
    PASSING p.document
    COLUMNS
        reference VARCHAR2(30) PATH 'po:Reference',
        status    VARCHAR2(20) PATH 'po:Status'
) x
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder[po:Status = "APPROVED"]'
    PASSING p.document AS "d"
);
~~~

XMLTABLE trả các cột quan hệ; XMLEXISTS lọc document. Cách kết hợp này thường dễ hiểu hơn khi cần vừa hiển thị giá trị vừa kiểm tra sự tồn tại.

## 13. XML schema-based và schema validation

XMLType có thể được dùng với XML Schema đã đăng ký trong Oracle XML DB. Schema-based XMLType gắn document với namespace/schema và có thể tận dụng kiểu dữ liệu, cấu trúc và metadata từ XSD.

### 13.1. Schema registration

Oracle cung cấp package DBMS_XMLSCHEMA để đăng ký XML Schema. Việc đăng ký schema là thao tác quản trị cần quyền phù hợp và cần quản lý URI, namespace, dependencies cũng như cách lưu trữ.

Ở mức khái niệm:

1. Đăng ký XSD trong XML DB.
2. Tạo XMLType column/table gắn với schema/element phù hợp.
3. Nạp XML document.
4. Validate theo schema khi quy trình yêu cầu.
5. Truy vấn bằng XMLTABLE/XMLQUERY/XMLEXISTS.

Không phải chỉ khai báo cột XMLType là database tự biết XSD của đối tác.

### 13.2. Well-formed không đồng nghĩa schema-valid

XMLPARSE đảm bảo việc parse XML theo cú pháp. Điều đó không tự động chứng minh XML đáp ứng mọi ràng buộc nghiệp vụ trong XSD.

Nếu hợp đồng tích hợp yêu cầu schema validation, cần thực hiện validation theo cơ chế XML DB tương ứng trước khi đánh dấu payload là hợp lệ.

### 13.3. Validation có chi phí

Schema validation tiêu tốn CPU và có thể làm tăng thời gian ingest. Cần quyết định validation ở đâu:

- Tại cổng nhận dữ liệu.
- Trong database trước khi ghi chính thức.
- Trong batch kiểm tra trước khi chuyển trạng thái.

Không bỏ validation nếu nó là yêu cầu hợp đồng hoặc compliance. Ngược lại, không validate lặp lại cùng document ở nhiều tầng nếu không có lý do.

## 14. Lưu XML và thiết kế mô hình dữ liệu

### 14.1. XMLType column cùng relational metadata

Một thiết kế thường gặp:

~~~sql
CREATE TABLE inbound_messages (
    message_id       NUMBER PRIMARY KEY,
    source_system    VARCHAR2(50) NOT NULL,
    received_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    processing_state VARCHAR2(20) NOT NULL,
    payload          XMLTYPE
);
~~~

Cột quan hệ giữ metadata cần lọc/join thường xuyên; payload XMLType giữ cấu trúc document gốc.

### 14.2. Tách các thuộc tính truy vấn thường xuyên

Nếu mọi truy vấn đều cần CustomerId, Status, BusinessDate, có thể cân nhắc:

- Giữ các giá trị đó thành relational columns được đồng bộ khi ingest.
- Dùng XMLTABLE để trích khi cần.
- Dùng XMLIndex phù hợp với path workload.

Không trích và lưu trùng dữ liệu mà không có quy tắc đồng bộ. Nếu XML payload và cột quan hệ mâu thuẫn, phải xác định nguồn dữ liệu nào là source of truth.

### 14.3. Giữ payload gốc khi cần audit

Trong tích hợp, có thể cần lưu payload nguyên bản để:

- Điều tra lỗi từ hệ thống gửi.
- Đối soát nội dung đã nhận.
- Replay thông điệp.
- Phục vụ audit.

Nếu cần giữ nguyên byte stream, XMLType không nhất thiết bảo toàn nguyên văn mọi chi tiết lexical như khoảng trắng, prefix hoặc cách serialize. Hãy lưu thêm BLOB/CLOB gốc khi hợp đồng audit yêu cầu chính xác byte payload.

### 14.4. Null, missing và empty element

Các trạng thái XML cần phân biệt:

~~~xml
<!-- Element không tồn tại -->
<Order><Reference>PO-1</Reference></Order>

<!-- Element tồn tại nhưng rỗng -->
<Order><Status/></Order>

<!-- Element có text -->
<Order><Status>OPEN</Status></Order>
~~~

Ngoài ra, XSD có thể cho phép xsi:nil="true" với element nillable. Missing, empty và nil không phải lúc nào cũng có cùng ý nghĩa nghiệp vụ.

Khi XMLTABLE ánh xạ sang VARCHAR2, Oracle có quy tắc NULL của SQL (chuỗi rỗng trong VARCHAR2 được xem là NULL). Nếu cần phân biệt các trạng thái, hãy kiểm tra sự tồn tại của node riêng bằng XMLEXISTS hoặc trích node XMLType trước khi cast.

## 15. Index và hiệu năng truy vấn XML

### 15.1. Không phải mọi XML query đều cần XMLIndex

Nếu bảng nhỏ hoặc truy vấn hiếm, full scan và evaluate XML có thể đủ. Với document lớn hoặc workload path-based thường xuyên, cần xem execution plan và đo hiệu năng trước khi tạo index.

### 15.2. XMLIndex

Oracle cung cấp XMLIndex để hỗ trợ truy vấn XMLType. Ví dụ tạo XMLIndex cơ bản:

~~~sql
CREATE INDEX purchase_orders_xml_ix
ON purchase_orders(document)
INDEXTYPE IS XDB.XMLINDEX;
~~~

XMLIndex có thể được cấu hình với structured component để tối ưu một số path và kiểu dữ liệu cụ thể. Thiết kế index cần dựa trên XQuery path thực tế, không phải cứ tạo XMLIndex là mọi XML query đều nhanh.

### 15.3. Index relational columns

Nếu query thường xuyên lọc theo PO_ID, SOURCE_SYSTEM hoặc PROCESSING_STATE, index relational columns có thể mang lại lợi ích rõ hơn:

~~~sql
CREATE INDEX inbound_messages_state_ix
ON inbound_messages(processing_state, received_at);
~~~

Đừng dùng XMLIndex thay cho index quan hệ khi điều kiện lọc chính nằm ở cột quan hệ.

### 15.4. Tối ưu path expression

- Dùng path cụ thể và đúng namespace.
- Tránh // nếu cấu trúc đã biết và path cụ thể có thể diễn tả.
- Không serialize XML ra CLOB rồi dùng LIKE để tìm node.
- Dùng XMLEXISTS cho điều kiện tồn tại.
- Dùng XMLTABLE một lần để trích nhiều cột thay vì gọi nhiều XMLQUERY lặp lại.
- Chỉ trích node/cột cần thiết.
- Đo execution plan, logical reads, elapsed time và cardinality.

### 15.5. XMLIndex và storage model

Khả năng sử dụng XMLIndex phụ thuộc XMLType storage model và cấu hình index. Kiểm tra Oracle XML DB Developer's Guide trước khi chọn storage/index combination. Không giả định một XMLIndex được tạo trên mọi kiểu XMLType hoặc mọi path mà không có giới hạn.

### 15.6. Kiểm tra execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT po_id
FROM purchase_orders
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder[po:Status = "APPROVED"]'
    PASSING document AS "d"
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Kiểm tra xem Oracle có sử dụng XMLIndex hoặc access path phù hợp hay không. EXPLAIN PLAN cho estimated plan; với workload production, hãy xem cursor plan và runtime statistics khi có quyền và công cụ phù hợp.

## 16. Security khi xử lý XML

XML là dữ liệu đầu vào, không phải code đáng tin cậy. Cần kiểm soát cả payload lẫn câu SQL/XQuery bao quanh nó.

### 16.1. Dùng bind variable trong SQL và PASSING trong XQuery

Không nối giá trị người dùng vào SQL text hoặc XQuery string. Ví dụ:

~~~sql
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder[po:Reference = $ref]'
    PASSING document AS "d",
            :p_reference AS "ref"
)
~~~

Giá trị reference được truyền như XQuery variable. Điều này giữ query text ổn định và tách dữ liệu khỏi biểu thức.

### 16.2. Kiểm soát kích thước và cấu trúc payload

Đối với XML từ bên ngoài:

- Giới hạn kích thước payload.
- Kiểm soát độ sâu lồng nhau và số node nếu ứng dụng có giới hạn.
- Xử lý timeout và lỗi parse.
- Kiểm tra schema/contract nếu cần.
- Không log toàn bộ payload nhạy cảm nếu không có nhu cầu.

### 16.3. External entities và DTD

XML parser có thể có các tính năng liên quan tới DTD và external entities. Khi xử lý XML không tin cậy, cần xem cấu hình parser/XML DB của phiên bản triển khai, tránh cho payload truy cập tài nguyên bên ngoài hoặc gây entity expansion ngoài kiểm soát. Không giả định mọi môi trường có cùng chính sách parser.

### 16.4. Quyền XML DB

Không cấp quyền rộng trên schema XDB hoặc các thành phần XML DB chỉ để một ứng dụng chạy được. Cấp quyền tối thiểu cần cho table, XML schema registration, XMLIndex hoặc thao tác quản trị thực tế.

### 16.5. Không coi XML schema là authorization

XSD xác nhận cấu trúc và kiểu dữ liệu; nó không chứng minh người gửi có quyền tạo hoặc sửa một đơn hàng. Authorization vẫn cần kiểm tra ở tầng nghiệp vụ và database.

## 17. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng/lỗi | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| XMLTABLE trả 0 row | Row path sai, namespace không khớp hoặc node không tồn tại | Kiểm tra XMLSerialize, namespace URI và path |
| Cột XMLTABLE toàn NULL | Column PATH sai hoặc element nằm namespace khác | Khai báo XMLNAMESPACES và kiểm tra context item |
| XMLQUERY trả NULL | XQuery trả empty sequence hoặc input XML NULL | Chạy path đơn giản và kiểm tra node có tồn tại |
| XMLEXISTS luôn TRUE | XQuery trả một item boolean FALSE thay vì empty sequence | Dùng path expression trả node sequence |
| ORA-31011 | XML parsing failed | Kiểm tra well-formedness, encoding và payload |
| ORA-19202 | Lỗi xử lý XML tổng quát; thường có lỗi XML/XQuery chi tiết đi kèm | Đọc error stack đầy đủ, kiểm tra XQuery và XML input |
| ORA-19228 | XQuery static error, ví dụ biến/namespace không được khai báo | Kiểm tra prolog, PASSING aliases và prefix |
| ORA-19279 | XQuery dynamic type/cardinality error trong một số biểu thức | Kiểm tra kiểu node, cast và số item trả về |
| ORA-19025 | Extract value gặp nhiều node hoặc kết quả không phù hợp yêu cầu scalar trong API cũ | Dùng XMLTABLE để biểu diễn nhiều row hoặc path chọn đúng một node |
| ORA-01400 sau XMLTABLE | Element thiếu/null nhưng cột bảng đích NOT NULL | Validate dữ liệu trước INSERT hoặc xử lý default |
| ORA-01722 | XML text không chuyển được sang NUMBER | Kiểm tra lexical value và cast/format |
| Kết quả sai khi XML dùng default namespace | Query path không khai báo namespace | Khai báo prefix gắn đúng URI |
| Query XML chậm | Path rộng, nhiều lần parse/extract, thiếu index phù hợp hoặc cardinality estimation kém | Dùng path cụ thể, XMLTABLE một lần, xem plan và XMLIndex |
| XML output khác chuỗi input | XML được parse/serialize lại, format/prefix/whitespace thay đổi | So sánh XML semantics; lưu payload gốc nếu cần byte-for-byte |

Không chỉ nhìn mã ORA đầu tiên nếu Oracle trả thêm stack XML/XQuery. Phần chi tiết thường cho biết lỗi nằm ở parse, namespace, static XQuery hoặc cast.

## 18. Lab tự chứa: XMLType, XMLTABLE, XMLQUERY và XMLEXISTS

Các bước sau tạo bảng riêng để thử. Không chạy trên bảng ứng dụng thật.

### 18.1. Tạo bảng XMLType

~~~sql
CREATE TABLE po_xml_lab (
    po_id NUMBER PRIMARY KEY,
    document XMLTYPE
);
~~~

### 18.2. Nạp document có namespace

~~~sql
INSERT INTO po_xml_lab(po_id, document)
VALUES (
    1,
    XMLPARSE(
        DOCUMENT
        '<PurchaseOrder xmlns="urn:acme:purchase-order">
           <Reference>PO-1001</Reference>
           <Status>APPROVED</Status>
           <CustomerId>501</CustomerId>
           <LineItems>
             <LineItem>
               <PartId>BK-01</PartId>
               <Quantity>2</Quantity>
               <UnitPrice>15.50</UnitPrice>
             </LineItem>
             <LineItem>
               <PartId>PN-10</PartId>
               <Quantity>4</Quantity>
               <UnitPrice>3.25</UnitPrice>
             </LineItem>
           </LineItems>
         </PurchaseOrder>'
    )
);

INSERT INTO po_xml_lab(po_id, document)
VALUES (
    2,
    XMLPARSE(
        DOCUMENT
        '<PurchaseOrder xmlns="urn:acme:purchase-order">
           <Reference>PO-1002</Reference>
           <Status>PENDING</Status>
           <CustomerId>502</CustomerId>
           <LineItems>
             <LineItem>
               <PartId>HD-02</PartId>
               <Quantity>10</Quantity>
               <UnitPrice>8.00</UnitPrice>
             </LineItem>
           </LineItems>
         </PurchaseOrder>'
    )
);

COMMIT;
~~~

### 18.3. Đọc lại XML bằng XMLSERIALIZE

~~~sql
SELECT po_id,
       XMLSERIALIZE(DOCUMENT document AS CLOB INDENT SIZE = 2) AS xml_text
FROM po_xml_lab
ORDER BY po_id;
~~~

### 18.4. Tách header bằng XMLTABLE

~~~sql
SELECT p.po_id,
       x.reference,
       x.status,
       x.customer_id
FROM po_xml_lab p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder'
    PASSING p.document
    COLUMNS
        reference   VARCHAR2(30) PATH 'po:Reference',
        status      VARCHAR2(20) PATH 'po:Status',
        customer_id NUMBER       PATH 'po:CustomerId'
) x
ORDER BY p.po_id;
~~~

### 18.5. Tách LineItem thành nhiều row

~~~sql
SELECT p.po_id,
       l.line_no,
       l.part_id,
       l.quantity,
       l.unit_price
FROM po_xml_lab p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem'
    PASSING p.document
    COLUMNS
        line_no    FOR ORDINALITY,
        part_id    VARCHAR2(30) PATH 'po:PartId',
        quantity   NUMBER       PATH 'po:Quantity',
        unit_price NUMBER(12,2) PATH 'po:UnitPrice'
) l
ORDER BY p.po_id, l.line_no;
~~~

Kỳ vọng có ba row: hai line của PO-1001 và một line của PO-1002.

### 18.6. Lọc bằng XMLEXISTS

~~~sql
SELECT po_id
FROM po_xml_lab p
WHERE XMLEXISTS(
    'declare namespace po = "urn:acme:purchase-order";
     $d/po:PurchaseOrder[po:Status = $s]'
    PASSING p.document AS "d",
            'APPROVED' AS "s"
);
~~~

Kỳ vọng PO_ID = 1.

### 18.7. Kiểm tra cạm bẫy boolean

~~~sql
SELECT po_id
FROM po_xml_lab p
WHERE XMLEXISTS('false()' PASSING p.document);
~~~

Biểu thức trên có thể trả mọi row có XML document vì false() là một item trong sequence, không phải empty sequence. Dùng path predicate để biểu diễn điều kiện tồn tại đúng cách.

### 18.8. Trích scalar bằng XMLQUERY và XMLCAST

~~~sql
SELECT p.po_id,
       XMLCAST(
           XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:Reference/text()'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS VARCHAR2(30)
       ) AS reference
FROM po_xml_lab p
ORDER BY p.po_id;
~~~

### 18.9. Trả XML fragment bằng XMLQUERY

~~~sql
SELECT p.po_id,
       XMLSERIALIZE(
           CONTENT XMLQUERY(
               'declare namespace po = "urn:acme:purchase-order";
                $d/po:PurchaseOrder/po:LineItems/po:LineItem'
               PASSING p.document AS "d"
               RETURNING CONTENT
           )
           AS CLOB
           INDENT SIZE = 2
       ) AS lines_xml
FROM po_xml_lab p
WHERE p.po_id = 1;
~~~

### 18.10. Thử OUTER APPLY

Tạo một document không có LineItems:

~~~sql
INSERT INTO po_xml_lab(po_id, document)
VALUES (
    3,
    XMLPARSE(
        DOCUMENT
        '<PurchaseOrder xmlns="urn:acme:purchase-order">
           <Reference>PO-1003</Reference>
           <Status>PENDING</Status>
           <CustomerId>503</CustomerId>
         </PurchaseOrder>'
    )
);

COMMIT;
~~~

So sánh:

~~~sql
SELECT p.po_id, l.part_id
FROM po_xml_lab p
CROSS APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem'
    PASSING p.document
    COLUMNS part_id VARCHAR2(30) PATH 'po:PartId'
) l;
~~~

~~~sql
SELECT p.po_id, l.part_id
FROM po_xml_lab p
OUTER APPLY XMLTABLE(
    XMLNAMESPACES('urn:acme:purchase-order' AS "po"),
    '/po:PurchaseOrder/po:LineItems/po:LineItem'
    PASSING p.document
    COLUMNS part_id VARCHAR2(30) PATH 'po:PartId'
) l;
~~~

OUTER APPLY vẫn giữ PO_ID = 3 dù không có LineItem.

### 18.11. Dọn lab

~~~sql
DROP TABLE po_xml_lab PURGE;
~~~

Chỉ chạy sau khi đã hoàn thành bài lab và không cần dữ liệu nữa.

## 19. Checklist khi triển khai XML trong Oracle

1. **XML có well-formed không?** Kiểm tra parse và encoding.
2. **Có yêu cầu schema validation không?** Phân biệt well-formed với XSD-valid.
3. **Dùng XMLType hay CLOB?** Chọn theo workload và yêu cầu giữ payload.
4. **Storage model là gì?** Binary XML, object-relational hay legacy storage.
5. **Namespace đã được khai báo đúng chưa?** So sánh namespace URI, không chỉ prefix.
6. **XMLTABLE row path có đúng không?** Xác định node nào tạo một SQL row.
7. **Column PATH có đúng context không?** Kiểm tra relative path và attribute.
8. **Có cần OUTER APPLY không?** Giữ parent row khi node con vắng mặt.
9. **Cần XMLQUERY hay XMLTABLE?** XMLQUERY trả XML; XMLTABLE trả hàng/cột.
10. **Cần XMLEXISTS hay không?** Dùng để lọc theo node sequence tồn tại; tránh trả boolean item.
11. **Có cần XMLCAST không?** Kiểm soát kiểu và lỗi chuyển đổi.
12. **Có phân biệt missing, empty và nil không?** Đừng gộp mọi trường hợp thành một ý nghĩa.
13. **Có dùng bind/PASSING không?** Không nối input vào SQL/XQuery string.
14. **Có index phù hợp không?** Đo workload trước khi tạo XMLIndex.
15. **Có lưu payload gốc không?** Xác định yêu cầu audit/byte-for-byte.
16. **Có kiểm soát XML không tin cậy không?** Kích thước, độ sâu, DTD/external entity và quyền.
17. **Đã kiểm tra execution plan chưa?** Đánh giá runtime với dữ liệu đại diện.
18. **Có kiểm thử namespace và dữ liệu thiếu node không?** Đây là các trường hợp dễ bị bỏ sót.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** XMLType khác CLOB chứa XML ở điểm nào?

**Câu 2.** Well-formed XML và schema-valid XML khác nhau thế nào?

**Câu 3.** Namespace URI có vai trò gì khi truy vấn XML?

**Câu 4.** XMLType column và XMLType table khác nhau ra sao?

**Câu 5.** XMLPARSE(DOCUMENT ...) dùng khi nào?

**Câu 6.** XMLSERIALIZE có vai trò gì?

**Câu 7.** XMLTABLE row expression quyết định điều gì?

**Câu 8.** FOR ORDINALITY dùng để làm gì?

**Câu 9.** Khi nào cần OUTER APPLY XMLTABLE?

**Câu 10.** XMLQUERY trả về kiểu dữ liệu nào?

**Câu 11.** XMLCAST dùng để làm gì?

**Câu 12.** XMLEXISTS trả TRUE khi nào?

**Câu 13.** Vì sao XMLEXISTS('false()') có thể trả TRUE?

**Câu 14.** Vì sao path /PurchaseOrder/Reference không khớp XML có default namespace?

**Câu 15.** XMLTABLE thường tiện hơn XMLQUERY/XMLCAST trong trường hợp nào?

**Câu 16.** XMLIndex có thay thế index trên cột quan hệ không?

**Câu 17.** Vì sao không nên nối input người dùng vào XQuery string?

**Câu 18.** Vì sao XMLType không nhất thiết giữ nguyên byte payload ban đầu?

<details>
<summary>Gợi ý đáp án</summary>

1. CLOB là văn bản; XMLType là kiểu XML có thể dùng trực tiếp các phép toán SQL/XML.
2. Well-formed là đúng cú pháp XML; valid là tuân theo XSD/contract schema.
3. Namespace URI là một phần của expanded name; prefix chỉ là bí danh.
4. XMLType column lưu XML trong một cột của bảng quan hệ; XMLType table có mỗi row là XMLType instance.
5. Khi parse chuỗi thành một XML document well-formed.
6. Chuyển XMLType thành CLOB/BLOB/character representation để hiển thị hoặc trao đổi.
7. Số lượng và nội dung node tạo ra từng row XMLTABLE.
8. Tạo số thứ tự cho item trong sequence.
9. Khi muốn giữ parent row dù không có node con khớp.
10. XMLType.
11. Chuyển XMLType result sang SQL scalar.
12. Khi XQuery trả sequence không rỗng.
13. Vì false() trả một boolean item; sequence vẫn không rỗng.
14. Vì element thuộc namespace URI, còn path không prefix đang tìm no-namespace element.
15. Khi cần trích nhiều scalar từ cùng cấu trúc XML thành các cột SQL.
16. Không. XMLIndex phục vụ path XML; index quan hệ vẫn cần cho các predicate relational.
17. Để tránh injection, lỗi quote và giữ query text ổn định; dùng PASSING/bind variables.
18. Parse/serialize có thể thay đổi whitespace, prefix hoặc lexical representation dù XML semantics tương đương.

</details>

## 21. Tài liệu Oracle chính thức

1. [Oracle Database 19c XML DB Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/adxdb/): XML DB, XMLType, storage, XML schema và SQL/XML.
2. [Oracle Database 19c XML DB Developer's Guide — Query and Update of XML](https://docs.oracle.com/en/database/oracle/oracle-database/19/adxdb/query-and-update-XML.html): truy vấn XML bằng SQL/XML và XQuery.
3. [Oracle Database 19c SQL Language Reference — XMLTABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLTABLE.html): cú pháp XMLTABLE, PASSING, XMLNAMESPACES và COLUMNS.
4. [Oracle Database 19c SQL Language Reference — XMLQUERY](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLQUERY.html): chạy XQuery và trả XMLType.
5. [Oracle Database 19c SQL Language Reference — XMLEXISTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLEXISTS.html): điều kiện tồn tại sequence XQuery.
6. [Oracle Database 19c SQL Language Reference — XMLCAST](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLCAST.html): chuyển XMLType value sang kiểu SQL.
7. [Oracle Database 19c SQL Language Reference — XMLSERIALIZE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLSERIALIZE.html): serialize XMLType thành kiểu SQL.
8. [Oracle Database 19c SQL Language Reference — XMLPARSE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLPARSE.html): parse XML text thành XMLType.
9. [Oracle Database 19c SQL Language Reference — XMLType](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/XMLTYPE.html): kiểu dữ liệu XMLType.
10. [Oracle Database 19c XML DB Developer's Guide — XMLIndex](https://docs.oracle.com/en/database/oracle/oracle-database/19/adxdb/indexes-for-XMLType-data.html): index cho XMLType và path-based query.
11. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_XMLSCHEMA](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XMLSCHEMA.html): đăng ký và quản lý XML Schema.

**Nguyên tắc cần nhớ:** XMLType biểu diễn XML trong database; XMLTABLE biến node thành hàng/cột quan hệ; XMLQUERY trả XML result; XMLCAST chuyển result thành scalar; XMLEXISTS lọc theo sequence không rỗng; XMLSERIALIZE xuất XML thành text. Luôn khai báo namespace đúng URI, dùng PASSING/bind variable, phân biệt well-formed với schema-valid, và tối ưu dựa trên query path cùng execution plan thực tế.

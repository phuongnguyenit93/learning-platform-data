# XML: truy vấn đường dẫn và ánh xạ thành bảng theo khả năng hỗ trợ

Trong **Database SQL**, dữ liệu không phải lúc nào cũng đến dưới dạng những hàng và cột đã chuẩn hóa. Nhiều hệ thống doanh nghiệp trao đổi hóa đơn điện tử, đơn hàng, báo cáo, cấu hình, dữ liệu tích hợp và thông điệp nghiệp vụ bằng **XML (Extensible Markup Language)**. Một trường XML có thể chứa cấu trúc lồng nhau, thuộc tính, danh sách phần tử lặp và namespace. Khi cần báo cáo hay kết hợp dữ liệu đó với bảng quan hệ, chúng ta phải biết **truy vấn theo đường dẫn** và **chuyển các nút XML thành những hàng/cột SQL**.

Câu hỏi trung tâm của bài:

> Từ một tài liệu XML chứa nhiều đơn hàng và nhiều dòng hàng, làm sao lấy đúng các giá trị cần thiết, biến **mỗi phần tử lặp thành một dòng trong bảng kết quả**, đặt kiểu dữ liệu phù hợp và xử lý được sự khác nhau về mức hỗ trợ của từng hệ quản trị cơ sở dữ liệu (DBMS)?

Ví dụ, một tài liệu đầu vào:

```xml
<orders version="1">
  <order id="1001" status="PAID" placed_on="2026-11-01">
    <customer>
      <code>C001</code>
      <name>An &amp; Bình</name>
    </customer>
    <lines>
      <line no="1" sku="BOOK-SQL">
        <quantity>2</quantity>
        <unit_price>120.50</unit_price>
      </line>
      <line no="2" sku="PEN-BLUE">
        <quantity>3</quantity>
        <unit_price>10.00</unit_price>
      </line>
    </lines>
  </order>
  <order id="1002" status="PENDING" placed_on="2026-11-02">
    <customer>
      <code>C002</code>
      <name>Chi</name>
    </customer>
    <lines>
      <line no="1" sku="NOTE-A5">
        <quantity>1</quantity>
        <unit_price>50.00</unit_price>
      </line>
    </lines>
  </order>
</orders>
```

có thể được chuyển thành bảng **đầu đơn**:

| order_id | status | placed_on | customer_code | customer_name |
| ---: | --- | --- | --- | --- |
| 1001 | PAID | 2026-11-01 | C001 | An & Bình |
| 1002 | PENDING | 2026-11-02 | C002 | Chi |

và bảng **dòng đơn**:

| order_id | line_no | sku | quantity | unit_price |
| ---: | ---: | --- | ---: | ---: |
| 1001 | 1 | BOOK-SQL | 2 | 120.50 |
| 1001 | 2 | PEN-BLUE | 3 | 10.00 |
| 1002 | 1 | NOTE-A5 | 1 | 50.00 |

Điểm then chốt: **tài liệu XML có một cây lồng nhau; SQL quan hệ cần xác định cấp phần tử nào là “một dòng”.** Chuyển một tài liệu nguyên khối thành một chuỗi đơn lẻ chưa phải là ánh xạ XML thành bảng.

## 1. XML là cây, bảng SQL là tập hàng

XML gồm các nút như **element**, **attribute**, **text**, và trong các trường hợp khác còn có comment, processing instruction, namespace...

Phân tích một đoạn:

```xml
<order id="1001" status="PAID">
  <customer>
    <code>C001</code>
    <name>An &amp; Bình</name>
  </customer>
  <lines>
    <line no="1" sku="BOOK-SQL">
      <quantity>2</quantity>
    </line>
  </lines>
</order>
```

Ta có thể nhìn như cây:

```text
order                         element
├── @id = "1001"              attribute
├── @status = "PAID"          attribute
├── customer                   element
│   ├── code                  element
│   │   └── "C001"            text
│   └── name                  element
│       └── "An & Bình"       text
└── lines                      element
    └── line                   element
        ├── @no = "1"          attribute
        ├── @sku = "BOOK-SQL"  attribute
        └── quantity           element
            └── "2"            text
```

**Element** có thể chứa element con và giá trị văn bản; **attribute** thuộc về element, thường chứa metadata ngắn như ID, trạng thái hoặc loại. Cả hai đều có thể được truy vấn.

Ký hiệu `&amp;` trong XML biểu diễn ký tự `&`; đây là **XML escaping**, không phải dữ liệu bị sai. Nếu đặt ký tự `&` trực tiếp vào text/attribute mà không escape hợp lệ, tài liệu có thể không còn *well-formed* và bị từ chối khi parse.

### 1.1. Vì sao không dùng LIKE trên XML?

Ví dụ:

```sql
-- Không nên coi chuỗi văn bản XML là cấu trúc quan hệ:
WHERE CAST(payload AS TEXT) LIKE '%status="PAID"%'
```

Cách tìm chuỗi này dễ sai vì:

- Attribute có thể đổi **thứ tự** hoặc dùng nháy đơn/nháy kép.
- Namespace và prefix có thể đổi.
- Cùng nội dung XML có nhiều cách biểu diễn khoảng trắng/escaping.
- Văn bản trong comment hoặc vùng khác có thể chứa chuỗi giống điều kiện.
- Không phân biệt đúng phần tử `order` thuộc đường dẫn nào.
- Khó chuyển đúng từng phần tử lặp thành hàng và kiểm soát kiểu dữ liệu.

**Muốn truy vấn cấu trúc XML, cần parser/XML data type và ngôn ngữ đường dẫn phù hợp**, thay vì so khớp chuỗi thô.

## 2. Ba nhiệm vụ khác nhau khi xử lý XML trong SQL

Nên tách rõ:

1. **Lưu XML:** giữ nguyên hoặc lưu một biểu diễn có cấu trúc, thường dùng kiểu `XML`/`XMLTYPE` hoặc văn bản tùy DBMS.
2. **Truy vấn XML:** tìm nút, kiểm tra phần tử có tồn tại, lấy giá trị theo đường dẫn.
3. **Ánh xạ XML thành quan hệ:** tạo **nhiều dòng SQL**, mỗi dòng có các cột và kiểu dữ liệu xác định, có thể JOIN, GROUP BY hoặc INSERT vào bảng đích.

Ví dụ:

```text
XML document
   |
   +-- /orders/order[@status="PAID"]  -> tìm đơn PAID
   |
   +-- /orders/order/@id             -> lấy các ID
   |
   +-- XMLTABLE('/orders/order'...)  -> 1 dòng / order
   |
   +-- XMLTABLE('/orders/order/lines/line'...)
                                       -> 1 dòng / line
   |
   +-- INSERT INTO normalized tables  -> lưu quan hệ thật
```

Một câu truy vấn `XMLTABLE` trả về tập hàng **trong kết quả truy vấn**; nó **không tự tạo bảng vật lý**. Chỉ khi kết hợp `INSERT INTO ... SELECT ...`, `CREATE TABLE AS ...` hoặc cơ chế tương tự thì dữ liệu mới được lưu thành bảng mới.

## 3. XPath: ngôn ngữ đường dẫn cơ bản

**XPath** là ngôn ngữ biểu diễn đường đi và điều kiện trên cây XML. Đặc biệt hữu ích khi:

- Chọn các element lặp.
- Chọn attribute.
- Lấy nút con.
- Lọc theo giá trị/thuộc tính.
- Đi từ nút hiện tại sang nút cha hoặc phần tử con.

Các biểu thức quan trọng, áp dụng với XML đầu bài:

| XPath | Ý nghĩa |
| --- | --- |
| `/orders` | Phần tử `orders` ở gốc tài liệu |
| `/orders/order` | Tất cả `order` là con trực tiếp của `orders` |
| `/orders/order[1]` | `order` đầu tiên trong ngữ cảnh đường dẫn |
| `/orders/order/@id` | Các attribute `id` của các đơn |
| `/orders/order/customer/name` | Các element `name` dưới `customer` |
| `/orders/order[@status="PAID"]` | Chỉ những `order` có attribute status bằng PAID |
| `/orders/order[quantity > 1]` | Chỉ có tác dụng khi `quantity` là con trực tiếp của order; ở ví dụ này nó nằm dưới line, nên biểu thức không phù hợp |
| `/orders/order/lines/line` | Mỗi dòng hàng thuộc một đơn |
| `/orders/order/lines/line[@sku="BOOK-SQL"]` | Dòng hàng có SKU tương ứng |
| `@sku` | Attribute sku của **nút hiện tại** |
| `quantity` | Element quantity con trực tiếp của nút hiện tại |
| `../@id` | Attribute id của **cha trực tiếp**, nếu cha có attribute đó |
| `../../@id` | Attribute id của **ông nội**, nếu cấu trúc tương ứng |
| `text()` | Nút văn bản ở cấp hiện tại |
| `//line` | Phần tử line ở nhiều cấp bất kỳ phía dưới; tiện khám phá nhưng có thể quá rộng |

### 3.1. Đường dẫn tuyệt đối và tương đối

- `/orders/order`: bắt đầu từ gốc tài liệu.
- `customer/name`: bắt đầu từ **context node** hiện tại (ví dụ một order).
- `@id`: thuộc tính của context node.
- `../../@id`: đi lên hai cấp từ context node.

Để ánh xạ **một hàng SQL cho mỗi order**, chọn row path `/orders/order`, rồi các column path như `@id`, `customer/code`.

Để ánh xạ **một hàng SQL cho mỗi line**, chọn row path `/orders/order/lines/line`, rồi các column path như `@no`, `@sku`, `quantity`, `unit_price` và `../../@id` để tìm ID order cha theo cấu trúc mẫu.

### 3.2. Predicate lọc node

Ví dụ:

```xpath
/orders/order[@status="PAID"]
```

chỉ tìm các order mang attribute trạng thái PAID. Không được nhầm:

```xpath
/orders/order/status="PAID"
```

với đường dẫn chọn order: tùy ngữ cảnh/XPath version, biểu thức so sánh có thể trả **boolean**, chứ không trả một tập nút order.

Viết predicate trên node đang chọn giúp mục đích rõ ràng hơn.

## 4. XPath không đồng nhất với XQuery

Hai tên thường xuất hiện trong tài liệu DBMS:

- **XPath:** truy vấn/chọn nút theo đường dẫn, biểu thức điều kiện và một số hàm.
- **XQuery:** ngôn ngữ truy vấn XML giàu biểu đạt hơn, hỗ trợ tạo kết quả XML và các biểu thức phức tạp, gồm các dạng *FLWOR* (`for`, `let`, `where`, `order by`, `return`) ở những implementation phù hợp.

DBMS không hỗ trợ giống nhau:

- PostgreSQL cung cấp `xpath`, `XMLEXISTS`, `XMLTABLE` với mức ngôn ngữ dựa vào **XPath 1.0** cho các expression trong các tính năng này; không phải một XQuery engine đầy đủ.
- SQL Server hỗ trợ một tập **XQuery** qua các phương thức của kiểu `xml`, như `nodes()`, `value()`, `exist()` và `query()`, với những giới hạn riêng.
- Oracle có hệ tính năng SQL/XML phong phú như `XMLTABLE`, `XMLQUERY`, `XMLTYPE` và có khả năng dùng XQuery trong ngữ cảnh phù hợp.

Không sao chép một biểu thức XQuery phức tạp từ Oracle sang PostgreSQL `xpath()` rồi kỳ vọng chạy nguyên văn. **Đường dẫn XPath cơ bản khá tương đồng về ý tưởng; ngôn ngữ đầy đủ và cú pháp nhúng SQL thay đổi nhiều.**

## 5. Các loại giá trị: phần tử thiếu, phần tử rỗng, SQL NULL

Xét ba phần XML:

```xml
<customer>
  <name>An</name>
</customer>
```

```xml
<customer>
  <name/>
</customer>
```

```xml
<customer>
</customer>
```

Về cấu trúc:

1. Trường hợp đầu: element `name` tồn tại và có text “An”.
2. Trường hợp hai: element `name` tồn tại nhưng rỗng.
3. Trường hợp ba: **không có element `name`**.

Khi ánh xạ sang cột SQL, có thể thấy:

- Chuỗi `'An'`.
- Chuỗi rỗng `''` hoặc cách biểu diễn khác theo DBMS, kiểu dữ liệu, phương pháp trích xuất.
- `NULL` khi đường dẫn không có giá trị phù hợp.

**Không mặc định “thiếu” và “rỗng” luôn giống nhau**. Một số DBMS, như Oracle đối với kiểu chuỗi văn bản thường dùng, có quy tắc coi chuỗi rỗng là NULL, gây thêm khác biệt. Với XML, element có `xsi:nil="true"` còn mang ý nghĩa được schema định nghĩa; **đừng giả định mọi XML parser tự đổi nó thành SQL NULL** nếu chưa có mapping/validation đúng.

Khi thiết kế ETL, phải quyết định:

| Tình huống | Ví dụ | Chính sách cần xác định |
| --- | --- | --- |
| Thiếu `customer/code` | Không có element | Từ chối, dùng fallback hay cho SQL NULL? |
| `<code/>` rỗng | Element tồn tại, text rỗng | Chuỗi rỗng có hợp lệ không? |
| `<quantity>abc</quantity>` | Có giá trị nhưng không chuyển thành INTEGER | Bắt lỗi dữ liệu hay đưa vào bảng lỗi? |
| Hai element `<code>` dưới một customer | Đường dẫn trả nhiều giá trị | Lấy phần tử đầu có hợp đồng hay từ chối ambiguous? |
| Attribute `status` không có | `<order id="...">` | Dùng DEFAULT nghiệp vụ, NULL hay lỗi? |

Nếu mất dữ liệu khi ép tất cả trường hợp này thành một kiểu `NULL` duy nhất, pipeline sẽ khó phân biệt lỗi nguồn với trường hợp tùy chọn hợp lệ.

## 6. Mapping một-nhiều: chọn đúng cấp hàng

Đây là bước quyết định kết quả.

Một XML order có thể có nhiều line:

```text
/orders/order                  -> cấp đầu đơn
/orders/order/lines/line       -> cấp dòng đơn
```

Nếu tạo một hàng SQL cho **mỗi order**:

| order_id | customer_code | status |
| ---: | --- | --- |
| 1001 | C001 | PAID |
| 1002 | C002 | PENDING |

Nếu tạo một hàng SQL cho **mỗi line**:

| order_id | line_no | sku |
| ---: | ---: | --- |
| 1001 | 1 | BOOK-SQL |
| 1001 | 2 | PEN-BLUE |
| 1002 | 1 | NOTE-A5 |

Mỗi row path tạo một **đơn vị hàng** khác nhau. Đừng đặt toàn bộ line vào một cột chuỗi rồi coi như đã chuyển thành bảng quan hệ. Nếu chỉ cần giữ phần XML gốc làm dữ liệu bán cấu trúc thì một cột XML vẫn hợp lý, nhưng đó là mục tiêu khác.

### 6.1. Ánh xạ phần tử lặp có thể nhân dòng

Nếu đồng thời trải phẳng hai danh sách con độc lập:

```xml
<order>
  <lines>
    <line .../>
    <line .../>
  </lines>
  <discounts>
    <discount .../>
    <discount .../>
    <discount .../>
  </discounts>
</order>
```

một phép JOIN giữa hai danh sách sau khi unnest có thể tạo **2 × 3 = 6 dòng** cho một order. Đây là hiện tượng nhân dòng trong quan hệ một-nhiều-nhiều, **không phải lỗi của XPath**.

Nếu cần cả line và discount, thường nên tạo **hai bảng con**, mỗi bảng giữ `order_id`, thay vì JOIN trực tiếp và vô tình cộng doanh thu nhiều lần.

## 7. Kiểu dữ liệu XML và lưu trữ theo DBMS

| DBMS | Hỗ trợ tiêu biểu | Ghi chú |
| --- | --- | --- |
| PostgreSQL | Kiểu `xml`, `XMLPARSE`, `xpath`, `XMLEXISTS`, `XMLTABLE` | XML path expression trong các tính năng này dùng tập khả năng XPath 1.0; không có XQuery đầy đủ như Oracle |
| Oracle Database | `XMLTYPE`, `XMLTABLE`, `XMLQUERY` và tính năng XML DB | Hỗ trợ SQL/XML và XQuery phong phú, lưu/index XML theo phiên bản/cấu hình |
| SQL Server | Kiểu `xml`, các phương thức `.nodes()`, `.value()`, `.exist()`, `.query()` | Dùng XQuery subset, có typed XML và XML indexes trong trường hợp phù hợp |
| MySQL 8.x | Không có tương đương SQL/XML `XMLTABLE` native phổ biến như PostgreSQL/Oracle | Thường xử lý XML ngoài DB hoặc lưu dạng text; các hàm legacy đã thay đổi |
| MariaDB | Có các hàm trích XML như `EXTRACTVALUE()` trong các phiên bản hỗ trợ | Chủ yếu trích giá trị; không đồng nghĩa có XMLTABLE chuẩn để unnest hàng |
| SQLite | Không có kiểu XML/XPath/XMLTABLE SQL native tích hợp | Có thể xử lý trong ứng dụng hoặc extension riêng |

**Nên kiểm tra phiên bản và tính năng thực tế của hệ đang chạy.** Không phải cứ tên “SQL” là có XMLTABLE, không phải hai DBMS cùng cú pháp XMLTABLE thì hỗ trợ chung mọi tính năng XQuery, namespace, typing hay index.

## 8. PostgreSQL: XMLPARSE, XML và tính well-formed

Trong PostgreSQL:

```sql
SELECT XMLPARSE(DOCUMENT
    '<root><item id="1">A</item></root>'
) AS document_xml;
```

`XMLPARSE(DOCUMENT ...)` yêu cầu văn bản tạo thành một **XML document hợp lệ về cấu trúc**, thường có đúng một root element.

So sánh:

```sql
-- Hợp lệ dưới dạng XML content/fragment, nhưng không phải
-- một document với một root element duy nhất:
SELECT XMLPARSE(CONTENT
    '<a>1</a><b>2</b>'
) AS xml_fragment;
```

**DOCUMENT** và **CONTENT** không giống nhau. Một số thao tác như `XMLTABLE` yêu cầu document expression phù hợp. Khi dữ liệu đầu vào là fragment, phải quyết định bọc root hoặc xử lý theo chức năng hỗ trợ, không giả định có thể dùng mọi row path như document.

### 8.1. XML well-formed không bằng nghiệp vụ hợp lệ

`XMLPARSE` xác nhận tài liệu parse được, không tự bảo đảm:

- `@id` là số nguyên dương.
- `@status` nằm trong danh sách trạng thái.
- `quantity > 0`.
- Mỗi order có ít nhất một line.
- SKU tồn tại trong danh mục sản phẩm.
- Tài liệu tuân theo hợp đồng XSD của đối tác.

PostgreSQL không tự cung cấp đầy đủ cơ chế xác thực XML Schema (XSD) ngay chỉ bằng việc khai báo một cột `xml` thông thường. Nếu cần xác thực XSD, thường phải thực hiện trong ứng dụng, pipeline hoặc một công cụ/chức năng riêng phù hợp môi trường.

Kết hợp **XML validation** ở đầu vào với **constraint SQL** ở bảng đích sẽ giúp tránh dữ liệu vừa “đúng XML” nhưng sai nghiệp vụ.

## 9. Tạo bộ dữ liệu PostgreSQL để thực hành

Các ví dụ chính của bài dùng schema riêng `sql368` trong **database học tập**. Chúng minh họa XML chứa đơn và line, đường dẫn, unnest và nạp vào bảng quan hệ.

### 9.1. Tạo schema và bảng nhận XML

```sql
CREATE SCHEMA sql368;

CREATE TABLE sql368.import_batches (
    batch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload XML NOT NULL
);
```

Đây là **bảng staging**: lưu XML gốc cùng thông tin nguồn và thời điểm nhận. Việc giữ bản XML ban đầu có ích để audit/lặp lại quá trình parse, nhưng phải áp dụng chính sách dữ liệu nhạy cảm, retention và quyền truy cập phù hợp. Không phải mọi hệ thống đều nên lưu bản XML vĩnh viễn.

### 9.2. Chèn một tài liệu có hai order và ba line

```sql
INSERT INTO sql368.import_batches (source_name, payload)
VALUES (
    'partner-demo',
    XMLPARSE(DOCUMENT
'<orders version="1">
  <order id="1001" status="PAID" placed_on="2026-11-01">
    <customer>
      <code>C001</code>
      <name>An &amp; Bình</name>
    </customer>
    <lines>
      <line no="1" sku="BOOK-SQL">
        <quantity>2</quantity>
        <unit_price>120.50</unit_price>
      </line>
      <line no="2" sku="PEN-BLUE">
        <quantity>3</quantity>
        <unit_price>10.00</unit_price>
      </line>
    </lines>
  </order>
  <order id="1002" status="PENDING" placed_on="2026-11-02">
    <customer>
      <code>C002</code>
      <name>Chi</name>
    </customer>
    <lines>
      <line no="1" sku="NOTE-A5">
        <quantity>1</quantity>
        <unit_price>50.00</unit_price>
      </line>
    </lines>
  </order>
</orders>'
    )
);
```

Vì trong lab chỉ chèn **một batch mới vào schema rỗng**, `batch_id` được tạo thường là 1; để chắc chắn hãy kiểm tra:

```sql
SELECT
    batch_id,
    source_name,
    received_at,
    XMLISDOCUMENT(payload) AS is_document
FROM sql368.import_batches;
```

`XMLISDOCUMENT` trong PostgreSQL kiểm tra một giá trị XML có phải document đúng nghĩa hay không. Kỳ vọng một hàng với `is_document = true`.

Để các câu SQL dưới đây dễ copy, các ví dụ tiếp theo lọc `WHERE b.batch_id = 1`. Nếu chạy nhiều lần và ID khác 1, **thay 1 bằng ID thật** lấy từ câu kiểm tra; không âm thầm áp dụng tất cả batch rồi gộp trùng order.

## 10. PostgreSQL: xpath() trả về giá trị gì?

PostgreSQL có hàm:

```sql
xpath(xpath_expression, xml_value [, namespace_mapping])
```

kết quả là **mảng `xml[]`** chứa các giá trị/nút phù hợp với biểu thức; không phải tự động là một bảng một-hàng-một-nút.

Ví dụ:

```sql
SELECT
    b.batch_id,
    xpath('/orders/order/@id', b.payload) AS order_ids
FROM sql368.import_batches AS b
WHERE b.batch_id = 1;
```

Kết quả có thể trình bày mảng XML chứa ID của hai order. Cách hiển thị mảng và nút XML tùy client.

### 10.1. Lấy một giá trị đơn

```sql
SELECT
    xpath('/orders/order[1]/@id', b.payload) AS first_order_id_nodes
FROM sql368.import_batches AS b
WHERE b.batch_id = 1;
```

Đây vẫn là **mảng XML**, không phải `BIGINT`. Có thể truy xuất phần tử mảng và chuyển kiểu có kiểm soát, nhưng cách biểu diễn attribute/text từ xml không nhất thiết phù hợp cho mọi đường dẫn. Nếu mục tiêu là có một hàng và các cột có kiểu `BIGINT`, `DATE`, `NUMERIC` thì **`XMLTABLE` thường là công cụ rõ ràng hơn**.

### 10.2. XPath kết quả rỗng

Nếu path không khớp element/attribute nào, `xpath` thường trả **mảng rỗng**, khác với SQL NULL và khác với một hàng XMLTABLE chứa các cột NULL.

Khi viết ETL, không nên coi “mảng rỗng” đồng nghĩa luôn “không có dữ liệu nguồn”: đôi khi chính đường dẫn sai hoặc namespace chưa được khai báo.

## 11. PostgreSQL: XMLEXISTS để kiểm tra có nút phù hợp

Nếu chỉ cần biết một tài liệu có order PAID hay không:

```sql
SELECT
    b.batch_id,
    XMLEXISTS(
        '/orders/order[@status="PAID"]'
        PASSING BY REF b.payload
    ) AS has_paid_order
FROM sql368.import_batches AS b
WHERE b.batch_id = 1;
```

Kỳ vọng `has_paid_order = true` vì order 1001 mang `status="PAID"`.

Có thể đưa vào `WHERE`:

```sql
SELECT b.batch_id, b.source_name
FROM sql368.import_batches AS b
WHERE XMLEXISTS(
    '/orders/order[@status="PAID"]'
    PASSING BY REF b.payload
);
```

**XMLEXISTS không trả các order PAID dưới dạng hàng SQL.** Nó trả kết quả logic để kiểm tra sự tồn tại/điều kiện XML. Muốn lấy từng order thì dùng `XMLTABLE` hoặc một cơ chế unnest tương ứng.

### 11.1. Đường dẫn cố định so với wildcard

`/orders/order[@status="PAID"]` nêu rõ cấu trúc mong đợi.

`//order[@status="PAID"]` có thể tìm order ở bất kỳ độ sâu nào bên dưới tài liệu, dễ bắt cả order nằm trong metadata, bản sao hoặc cấu trúc khác ngoài ý muốn. `//` tiện khi khám phá XML chưa biết cấu trúc nhưng không nên dùng thay đường dẫn rõ ràng trong hợp đồng ETL nếu đã biết schema.

## 12. PostgreSQL: XMLTABLE — mỗi order thành một hàng

Đây là phần trung tâm.

```sql
SELECT
    b.batch_id,
    x.order_id,
    x.status,
    x.placed_on,
    x.customer_code,
    x.customer_name
FROM sql368.import_batches AS b
CROSS JOIN LATERAL XMLTABLE(
    '/orders/order'
    PASSING b.payload
    COLUMNS
        order_id BIGINT PATH '@id',
        status TEXT PATH '@status',
        placed_on DATE PATH '@placed_on',
        customer_code TEXT PATH 'customer/code',
        customer_name TEXT PATH 'customer/name'
) AS x
WHERE b.batch_id = 1
ORDER BY x.order_id;
```

Giải thích lần lượt:

1. `sql368.import_batches b` là **mỗi batch XML**.
2. `XMLTABLE('/orders/order' ...)` tìm tất cả phần tử `order` trong tài liệu của batch.
3. Mỗi `order` khớp row path trở thành **một dòng SQL**.
4. `COLUMNS` định nghĩa **tên cột SQL, kiểu cột SQL và XPath tương đối với order hiện tại**.
5. `@id` lấy attribute ID của order, ép thành `BIGINT`.
6. `@status` lấy trạng thái, `@placed_on` được ép sang `DATE`.
7. `customer/code` và `customer/name` lấy element con.
8. `CROSS JOIN LATERAL` cho phép biểu thức XMLTABLE dùng `b.payload` từ hàng batch hiện tại, rồi nối các hàng được tách ra vào quan hệ SQL bên ngoài.
9. `WHERE b.batch_id = 1` giới hạn chỉ parse batch cần thiết.
10. `ORDER BY` quy định thứ tự hiển thị; thứ tự vật lý/hàng không nên dựa hoàn toàn vào thứ tự node nếu không đặt yêu cầu kết quả rõ ràng.

Kết quả:

| batch_id | order_id | status | placed_on | customer_code | customer_name |
| ---: | ---: | --- | --- | --- | --- |
| 1 | 1001 | PAID | 2026-11-01 | C001 | An & Bình |
| 1 | 1002 | PENDING | 2026-11-02 | C002 | Chi |

**Quan trọng:** không có câu `INSERT` hay `CREATE TABLE AS` ở đây; kết quả chỉ là **quan hệ tạm trong câu SELECT**. XML nguồn không bị sửa, các bảng đầu đơn/dòng đơn vật lý chưa được tạo.

## 13. XMLTABLE: phân biệt row path và column path

Hai loại XPath trong câu trước có trách nhiệm khác nhau:

| Vị trí | Ví dụ | Tác dụng |
| --- | --- | --- |
| **Row expression** | `'/orders/order'` | Chọn số **dòng** trả về |
| **Column expression** | `'@id'` | Lấy giá trị cho một **cột** của mỗi dòng |
| **Column expression** | `'customer/code'` | Đi từ node order hiện tại tới phần tử con |
| **Column expression** | `'customer/name'` | Lấy tên khách bên trong order hiện tại |
| **Column type** | `BIGINT` / `DATE` | Yêu cầu chuyển giá trị XML sang kiểu quan hệ |

Nếu row path sai:

```sql
XMLTABLE(
    '/orders/items/item'
    PASSING b.payload
    COLUMNS order_id BIGINT PATH '@id'
)
```

sẽ không cho các dòng order vì tài liệu lab không có cấu trúc `/orders/items/item`.

Nếu row path đúng nhưng column path sai:

```sql
XMLTABLE(
    '/orders/order'
    PASSING b.payload
    COLUMNS customer_code TEXT PATH 'customer/customer_id'
)
```

vẫn có **hai hàng** vì có hai order, nhưng `customer_code` có thể thành **NULL** do không có element `customer_id` trong XML.

**Tách lỗi “không có dòng” khỏi lỗi “có dòng nhưng thiếu cột”.** Đây là kỹ năng debug quan trọng nhất khi dùng XMLTABLE.

## 14. XMLTABLE: ánh xạ các dòng hàng lặp

Để lấy **mỗi `line` là một dòng SQL**, đổi row path thành:

```xpath
/orders/order/lines/line
```

Câu truy vấn PostgreSQL:

```sql
SELECT
    b.batch_id,
    x.order_id,
    x.line_no,
    x.sku,
    x.quantity,
    x.unit_price,
    (x.quantity * x.unit_price) AS line_amount
FROM sql368.import_batches AS b
CROSS JOIN LATERAL XMLTABLE(
    '/orders/order/lines/line'
    PASSING b.payload
    COLUMNS
        order_id BIGINT PATH '../../@id',
        line_no INTEGER PATH '@no',
        sku TEXT PATH '@sku',
        quantity INTEGER PATH 'quantity',
        unit_price NUMERIC(12,2) PATH 'unit_price'
) AS x
WHERE b.batch_id = 1
ORDER BY x.order_id, x.line_no;
```

Tại node `line` hiện tại:

```text
line                     <-- context node
  ..  = lines            <-- cha
  ../.. = order          <-- ông nội
  ../../@id              <-- ID của order
```

Vì vậy `../../@id` lấy ID của đơn bao quanh line, không phải ID của line.

Kết quả:

| batch_id | order_id | line_no | sku | quantity | unit_price | line_amount |
| ---: | ---: | ---: | --- | ---: | ---: | ---: |
| 1 | 1001 | 1 | BOOK-SQL | 2 | 120.50 | 241.00 |
| 1 | 1001 | 2 | PEN-BLUE | 3 | 10.00 | 30.00 |
| 1 | 1002 | 1 | NOTE-A5 | 1 | 50.00 | 50.00 |

Tổng tiền từng đơn, nếu chỉ nhân quantity × unit_price:

- Order 1001: `241.00 + 30.00 = 271.00`.
- Order 1002: `50.00`.

### 14.1. Phải cập nhật đường dẫn cha khi cấu trúc XML thay đổi

Nếu đối tác đổi XML từ `order/lines/line` sang `order/line`, đường dẫn `../../@id` trở nên sai về số cấp cha. Do đó XPath phải được xây theo **cấu trúc XML thật**, không phải mẹo cố định cho mọi tài liệu.

Trong ETL lớn, có thể tách extraction đầu đơn và extraction dòng đơn theo parent context bằng các cơ chế LATERAL/nested node context của DBMS để giảm phụ thuộc vào các phép `../..` phức tạp.

## 15. XMLTABLE: FOR ORDINALITY khác ID nghiệp vụ

Một số tài liệu XML không có attribute `no` cho từng line. Cần một số thứ tự tương ứng với **vị trí phần tử trong kết quả**.

PostgreSQL XMLTABLE hỗ trợ:

```sql
SELECT
    x.document_position,
    x.order_id,
    x.status
FROM sql368.import_batches AS b
CROSS JOIN LATERAL XMLTABLE(
    '/orders/order'
    PASSING b.payload
    COLUMNS
        document_position FOR ORDINALITY,
        order_id BIGINT PATH '@id',
        status TEXT PATH '@status'
) AS x
WHERE b.batch_id = 1
ORDER BY x.document_position;
```

Kết quả:

| document_position | order_id | status |
| ---: | ---: | --- |
| 1 | 1001 | PAID |
| 2 | 1002 | PENDING |

`FOR ORDINALITY` đánh số các dòng **theo thứ tự node được trả về trong row expression** trong một lần đánh giá, bắt đầu từ 1 trong ngữ cảnh PostgreSQL XMLTABLE.

**Không nhầm ordinal với khóa nghiệp vụ.** Nếu đối tác đổi thứ tự hai order trong XML, `document_position` thay đổi; `order_id` vẫn là 1001/1002. Trong bảng đích, khóa quan hệ nên dựa vào định danh có ý nghĩa và ổn định, không dùng ordinal như primary key toàn hệ nếu không có bảo đảm khác.

Ordinal có ích để:

- Khôi phục thứ tự trong một batch.
- Ghi vị trí dòng gây lỗi parse/validation.
- Tạo thứ tự dòng tạm khi XML không có line number.
- Đối chiếu với tài liệu nguồn.

## 16. Từ XMLTABLE đến JOIN, WHERE, GROUP BY

Khi dữ liệu đã thành cột SQL có kiểu, ta dùng các toán tử quan hệ bình thường.

### 16.1. Chỉ lấy dòng hàng của đơn PAID

```sql
WITH headers AS (
    SELECT x.order_id, x.status
    FROM sql368.import_batches AS b
    CROSS JOIN LATERAL XMLTABLE(
        '/orders/order'
        PASSING b.payload
        COLUMNS
            order_id BIGINT PATH '@id',
            status TEXT PATH '@status'
    ) AS x
    WHERE b.batch_id = 1
),
lines AS (
    SELECT
        x.order_id, x.line_no, x.sku,
        x.quantity, x.unit_price
    FROM sql368.import_batches AS b
    CROSS JOIN LATERAL XMLTABLE(
        '/orders/order/lines/line'
        PASSING b.payload
        COLUMNS
            order_id BIGINT PATH '../../@id',
            line_no INTEGER PATH '@no',
            sku TEXT PATH '@sku',
            quantity INTEGER PATH 'quantity',
            unit_price NUMERIC(12,2) PATH 'unit_price'
    ) AS x
    WHERE b.batch_id = 1
)
SELECT
    h.order_id,
    l.line_no,
    l.sku,
    l.quantity,
    l.unit_price
FROM headers AS h
JOIN lines AS l
  ON l.order_id = h.order_id
WHERE h.status = 'PAID'
ORDER BY h.order_id, l.line_no;
```

Chỉ còn hai line của order 1001. **Điều kiện PAID nằm ở cấp đầu đơn**, còn các line được JOIN theo `order_id`.

### 16.2. Tổng hợp tiền từ các dòng XML

```sql
WITH lines AS (
    SELECT
        x.order_id,
        x.quantity,
        x.unit_price
    FROM sql368.import_batches AS b
    CROSS JOIN LATERAL XMLTABLE(
        '/orders/order/lines/line'
        PASSING b.payload
        COLUMNS
            order_id BIGINT PATH '../../@id',
            quantity INTEGER PATH 'quantity',
            unit_price NUMERIC(12,2) PATH 'unit_price'
    ) AS x
    WHERE b.batch_id = 1
)
SELECT
    order_id,
    COUNT(*) AS line_count,
    SUM(quantity * unit_price) AS subtotal
FROM lines
GROUP BY order_id
ORDER BY order_id;
```

Kết quả:

| order_id | line_count | subtotal |
| ---: | ---: | ---: |
| 1001 | 2 | 271.00 |
| 1002 | 1 | 50.00 |

Cách tính `SUM` này không cần viết XPath để tự cộng từng node. XMLTABLE **chuyển cấu trúc về quan hệ**, sau đó SQL thường xử lý aggregate.

## 17. XMLTABLE: chuyển kiểu dữ liệu và lỗi ép kiểu

Dữ liệu XML ở tầng text có thể là:

```xml
<quantity>2</quantity>
<unit_price>120.50</unit_price>
<placed_on>2026-11-01</placed_on>
```

Khi khai báo:

```sql
quantity INTEGER PATH 'quantity',
unit_price NUMERIC(12,2) PATH 'unit_price',
placed_on DATE PATH '@placed_on'
```

DBMS cần chuyển giá trị trích xuất thành kiểu SQL đích.

Điều gì xảy ra nếu:

```xml
<quantity>hai</quantity>
```

hoặc:

```xml
<placed_on>ngày mai</placed_on>
```

Trong PostgreSQL, chuyển kiểu không hợp lệ thường phát sinh **lỗi câu truy vấn**; không nên giả định XMLTABLE tự bỏ qua node và trả NULL.

### 17.1. Kiểm soát kiểu ở tầng thích hợp

Các chiến lược thường gặp:

1. **Xác thực XML/XSD trước khi chuyển kiểu** bằng bộ parser/validator đã cấu hình an toàn.
2. **Trích giá trị như TEXT**, sau đó xác thực rõ ràng trước khi CAST sang INTEGER/NUMERIC/DATE.
3. Tách dữ liệu nguồn lỗi sang **bảng staging lỗi**, kèm batch ID và vị trí node.
4. Dùng constraints ở bảng đích để bảo vệ miền dữ liệu như `quantity > 0`.
5. Quy định rõ ETL là **all-or-nothing** hay cho phép tiếp tục những bản ghi hợp lệ.

### 17.2. Kiểu NUMERIC cho tiền

Trong ví dụ, `unit_price NUMERIC(12,2)` phù hợp với giá tiền có hai chữ số thập phân. Không nên dùng FLOAT cho tiền nếu cần biểu diễn thập phân chính xác. Nhưng cần kiểm soát:

- Số quá lớn vượt precision.
- Số có nhiều chữ số thập phân có thể bị làm tròn theo quy tắc kiểu đích.
- Giá âm hoặc bằng 0 có hợp lệ hay không.
- Đơn vị tiền tệ và thuế chưa được biểu diễn.

XMLTABLE xử lý **chuyển dữ liệu**, không tự xác nhận mọi quy tắc tài chính.

## 18. Missing path, DEFAULT và NOT NULL trong XMLTABLE

Trong PostgreSQL, các cột XMLTABLE có thể có biểu thức `DEFAULT` hoặc `NOT NULL` theo cú pháp của tính năng SQL/XML được hỗ trợ.

Ví dụ minh họa:

```sql
SELECT
    x.order_id,
    x.status
FROM sql368.import_batches AS b
CROSS JOIN LATERAL XMLTABLE(
    '/orders/order'
    PASSING b.payload
    COLUMNS
        order_id BIGINT PATH '@id' NOT NULL,
        status TEXT PATH '@status' DEFAULT 'UNKNOWN'
) AS x
WHERE b.batch_id = 1;
```

Ý nghĩa:

- Nếu XML thiếu `@id` và mapping yêu cầu `NOT NULL`, truy vấn không thể âm thầm tạo một ID NULL.
- Nếu thiếu `@status`, cột có thể dùng giá trị `'UNKNOWN'` theo cú pháp/default expression khi DBMS hỗ trợ và phù hợp.

**Đừng dùng DEFAULT để che mọi dữ liệu sai.** Với status là tập trạng thái bắt buộc từ đối tác, có khi phải từ chối cả batch thay vì tự chuyển trạng thái thiếu thành UNKNOWN. Trường bắt buộc về nghiệp vụ nên có chính sách validation rõ.

### 18.1. Nhiều nút trùng cùng một column path

Nếu một order chứa:

```xml
<customer>
  <code>C001</code>
  <code>C099</code>
</customer>
```

thì `PATH 'customer/code'` trả nhiều node. Khi cột mong đợi một scalar như TEXT, hành vi có thể dẫn tới lỗi hoặc phụ thuộc cơ chế/DBMS. Đừng tùy tiện lấy giá trị đầu mà không có hợp đồng dữ liệu.

Nếu tài liệu cho phép lặp code, phải xác định **mỗi code là một dòng**, hoặc khai báo rõ quy tắc “code chính”. Khi chỉ một code được phép, XSD/validation hoặc quy tắc kiểm tra tính duy nhất trong pipeline thích hợp hơn.

## 19. XML namespace: vì sao XPath đúng nhìn thấy mà không ra hàng?

XML có thể dùng namespace:

```xml
<orders xmlns="urn:demo:orders">
  <order id="1001">
    <customer>
      <code>C001</code>
    </customer>
  </order>
</orders>
```

Mắt người thấy `<orders>` và `<order>`, nhưng các element này thuộc **namespace URI `urn:demo:orders`**. XPath không gắn namespace:

```xpath
/orders/order
```

có thể không khớp nút nào vì nó tìm **element không có namespace**, không phải element thuộc URI trên.

### 19.1. Dùng prefix trong truy vấn, dù XML dùng default namespace

PostgreSQL XMLTABLE:

```sql
SELECT x.order_id, x.customer_code
FROM XMLTABLE(
    XMLNAMESPACES(
        'urn:demo:orders' AS d
    ),
    '/d:orders/d:order'
    PASSING XMLPARSE(DOCUMENT
'<orders xmlns="urn:demo:orders">
  <order id="1001">
    <customer><code>C001</code></customer>
  </order>
</orders>'
    )
    COLUMNS
        order_id BIGINT PATH '@id',
        customer_code TEXT PATH 'd:customer/d:code'
) AS x;
```

Trong câu truy vấn, `d` là **prefix do người viết XPath khai báo**. Nó không cần trùng prefix của file XML; điều phải trùng là **namespace URI**.

Đặc biệt, trong XML có **default namespace**, các **element không prefix** thuộc default namespace, nhưng **attribute không prefix** như `id="1001"` thường **không thuộc default namespace**. Vì vậy dùng `@id`, không phải `@d:id`, trừ khi attribute thực sự được khai báo có namespace riêng.

### 19.2. Namespace array của PostgreSQL xpath()

Ví dụ:

```sql
SELECT xpath(
    '/d:orders/d:order/@id',
    XMLPARSE(DOCUMENT
        '<orders xmlns="urn:demo:orders"><order id="1001"/></orders>'
    ),
    ARRAY[
        ARRAY['d', 'urn:demo:orders']
    ]
) AS ids;
```

Tham số thứ ba là mapping prefix/URI cho `xpath()`; nó không sửa tài liệu XML nguồn.

**Debug namespace trước khi viết lại toàn bộ row path.** Khi dữ liệu có root và element nhìn đúng mà XMLTABLE trả 0 dòng, thiếu namespace mapping là một trong những nguyên nhân phổ biến.

## 20. Namespace prefix và URI là hai thứ khác nhau

Hai tài liệu sau có thể biểu diễn element cùng namespace:

```xml
<a:orders xmlns:a="urn:demo:orders">
  <a:order id="1001"/>
</a:orders>
```

và:

```xml
<x:orders xmlns:x="urn:demo:orders">
  <x:order id="1001"/>
</x:orders>
```

Prefix `a` hay `x` chỉ là tên ngắn dùng trong tài liệu. Identity của tên element theo namespace phụ thuộc **namespace URI và local name**, không phải chỉ chuỗi prefix.

Do đó XPath nên khai báo một prefix theo URI:

```xpath
/d:orders/d:order
```

với `d` ánh xạ tới `urn:demo:orders`, thay vì cố tìm text `<a:order>`.

### 20.1. Những cách “né namespace” dễ có rủi ro

Một số người dùng XPath:

```xpath
//*[local-name()="order"]
```

để chọn mọi element tên order bất kể namespace. Cách này có thể hữu ích khi khám phá tạm thời, nhưng **mất phân biệt namespace**: một phần tử order trong namespace khác vẫn bị chọn, ngay cả khi có ý nghĩa nghiệp vụ khác.

Với hợp đồng dữ liệu ổn định, **khai báo URI chính xác** là cách an toàn và dễ bảo trì hơn.

## 21. Lưu vào bảng quan hệ: thiết kế đích trước khi INSERT

XMLTABLE trả bảng tạm theo truy vấn; nếu muốn truy vấn quan hệ lâu dài hoặc JOIN với dữ liệu khác thường xuyên, nên định nghĩa bảng đích.

```sql
CREATE TABLE sql368.order_headers (
    order_id BIGINT PRIMARY KEY,
    batch_id BIGINT NOT NULL
        REFERENCES sql368.import_batches(batch_id),
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    placed_on DATE NOT NULL,
    customer_code TEXT NOT NULL,
    customer_name TEXT NOT NULL
);

CREATE TABLE sql368.order_lines (
    order_id BIGINT NOT NULL
        REFERENCES sql368.order_headers(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
```

Vì sao có cả XML source và bảng quan hệ?

- **Bản XML gốc:** phục vụ đối soát nguồn, kiểm tra lại mapping, debugging và một số yêu cầu audit/retention.
- **Bảng quan hệ:** có khóa chính, khóa ngoại, kiểu dữ liệu, CHECK, index và truy vấn báo cáo thông thường.

Không nhất thiết giữ XML gốc mãi mãi. Nếu dữ liệu chứa thông tin cá nhân, phải xét quyền đọc, thời hạn lưu và chính sách xóa theo yêu cầu tổ chức.

### 21.1. Chọn khóa cẩn thận

Trong lab, `order_id` được giả định **duy nhất toàn hệ**. Nếu thực tế mỗi đối tác có thể phát order ID 1001 khác nhau, khóa đích cần bổ sung `source_system` hoặc `batch/tenant` theo định danh ổn định, thay vì ép các hệ thống nguồn vào một primary key trùng lặp.

Đối với dòng đơn, `(order_id, line_no)` có thể là khóa ghép hợp lý nếu line_no ổn định trong một order. Không dùng vị trí XML làm định danh bền vững khi thứ tự có thể thay đổi mà không có quy ước khác.

## 22. Nạp headers và lines trong cùng transaction

Nạp **đầu đơn trước**, rồi **dòng đơn** để thỏa FK.

```sql
BEGIN;

INSERT INTO sql368.order_headers (
    order_id,
    batch_id,
    status,
    placed_on,
    customer_code,
    customer_name
)
SELECT
    x.order_id,
    b.batch_id,
    x.status,
    x.placed_on,
    x.customer_code,
    x.customer_name
FROM sql368.import_batches AS b
CROSS JOIN LATERAL XMLTABLE(
    '/orders/order'
    PASSING b.payload
    COLUMNS
        order_id BIGINT PATH '@id',
        status TEXT PATH '@status',
        placed_on DATE PATH '@placed_on',
        customer_code TEXT PATH 'customer/code',
        customer_name TEXT PATH 'customer/name'
) AS x
WHERE b.batch_id = 1;

INSERT INTO sql368.order_lines (
    order_id,
    line_no,
    sku,
    quantity,
    unit_price
)
SELECT
    x.order_id,
    x.line_no,
    x.sku,
    x.quantity,
    x.unit_price
FROM sql368.import_batches AS b
CROSS JOIN LATERAL XMLTABLE(
    '/orders/order/lines/line'
    PASSING b.payload
    COLUMNS
        order_id BIGINT PATH '../../@id',
        line_no INTEGER PATH '@no',
        sku TEXT PATH '@sku',
        quantity INTEGER PATH 'quantity',
        unit_price NUMERIC(12,2) PATH 'unit_price'
) AS x
WHERE b.batch_id = 1;

COMMIT;
```

Với bộ dữ liệu mẫu:

- `order_headers` có **2** hàng.
- `order_lines` có **3** hàng.
- Các quan hệ FK từ line tới header đều hợp lệ.

**Transaction giúp đảm bảo tính nguyên tử trong mô hình nạp này**: nếu bước thứ hai thất bại và không bị cố tình bỏ qua, caller cần `ROLLBACK` để không giữ riêng headers mà thiếu lines. Trong PostgreSQL, sau lỗi trong transaction explicit, các lệnh tiếp theo không tiếp tục bình thường cho tới khi rollback/khôi phục transaction. Không cố chạy `COMMIT` như thể import đã thành công.

### 22.1. Kiểm tra kết quả

```sql
SELECT
    h.order_id,
    h.status,
    h.customer_code,
    h.customer_name,
    l.line_no,
    l.sku,
    l.quantity,
    l.unit_price
FROM sql368.order_headers AS h
JOIN sql368.order_lines AS l
  ON l.order_id = h.order_id
ORDER BY h.order_id, l.line_no;
```

Có 3 dòng kết quả JOIN. Order 1001 lặp hai lần ở mức kết quả vì có **hai line**, không phải do XMLTABLE lỗi.

Tổng hợp:

```sql
SELECT
    h.order_id,
    h.status,
    COUNT(l.line_no) AS line_count,
    SUM(l.quantity * l.unit_price) AS subtotal
FROM sql368.order_headers AS h
LEFT JOIN sql368.order_lines AS l
  ON l.order_id = h.order_id
GROUP BY h.order_id, h.status
ORDER BY h.order_id;
```

Với một order không có line, `SUM` có thể là `NULL`; nếu báo cáo muốn 0, dùng `COALESCE(SUM(...), 0)` theo định nghĩa nghiệp vụ.

## 23. Kiểm soát lỗi khi nạp XML

Trong pipeline thật, cần phân biệt **lỗi cấu trúc**, **lỗi chuyển kiểu** và **lỗi constraint**.

| Loại | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| XML không well-formed | Thiếu thẻ đóng, `&` chưa escape | Từ chối parse, báo nguồn sửa tài liệu |
| Row path không khớp | Document có namespace khác | Kiểm tra hợp đồng XML và namespace mapping |
| Node bắt buộc thiếu | Order không có `@id` | Từ chối hoặc ghi lỗi nguồn cụ thể |
| Ép kiểu thất bại | `<quantity>two</quantity>` | Không đưa vào INTEGER; kiểm tra bản nguồn |
| Miền dữ liệu sai | Quantity = -1 | `CHECK(quantity > 0)` chặn ở đích |
| Tham chiếu sai | Line của order không có header | FK chặn |
| Khóa trùng | Nạp lại cùng order ID | PK/UNIQUE chặn; cần idempotency |
| Dữ liệu không toàn vẹn | Một order được khai là 2 line nhưng thực có 1 | Quy tắc validation riêng |
| Bản XML quá lớn | File hoặc số node vượt giới hạn | Giới hạn tài nguyên, cân nhắc streaming ETL |
| Trùng một giá trị XML | Hai `@id` giống nhau trong cùng batch | Khóa đích hoặc validation từ chối |

### 23.1. Đừng nạp lỗi theo kiểu “âm thầm bỏ qua”

Nếu dùng `ON CONFLICT DO NOTHING` trên PostgreSQL để tránh lỗi khóa trùng, hãy hỏi:

- Request mới có thực sự là **cùng dữ liệu** với bản đã nạp?
- Nếu order ID giống nhưng số tiền khác, bỏ qua có che mất cập nhật quan trọng không?
- Nếu chỉ header bị bỏ qua mà line vẫn chèn, điều gì xảy ra?
- Có cần đánh dấu batch là **idempotent retry**, **update**, hay **lỗi xung đột**?

Một quy trình nạp đáng tin cần quy định rõ **rerun cùng batch** và **dữ liệu mới có cùng khóa** được xử lý khác nhau ra sao. Constraint giúp nhận diện xung đột; nó không tự định nghĩa toàn bộ chính sách nhập liệu.

## 24. SQL Server: dùng xml.nodes() để tạo hàng

SQL Server có kiểu `xml` và các phương thức đặc trưng:

| Phương thức | Mục đích |
| --- | --- |
| `.nodes(XQuery)` | Trả một rowset ngữ cảnh XML, mỗi nút khớp một dòng |
| `.value(XQuery, SQLType)` | Lấy giá trị scalar và chuyển thành kiểu SQL |
| `.exist(XQuery)` | Kiểm tra sự tồn tại theo quy tắc SQL Server |
| `.query(XQuery)` | Trả kết quả XML dạng XML |

Mẫu SQL Server độc lập:

```sql
DECLARE @doc XML = N'
<orders>
  <order id="1001" status="PAID">
    <customer><code>C001</code><name>An</name></customer>
    <lines>
      <line no="1" sku="BOOK-SQL">
        <quantity>2</quantity><unit_price>120.50</unit_price>
      </line>
      <line no="2" sku="PEN-BLUE">
        <quantity>3</quantity><unit_price>10.00</unit_price>
      </line>
    </lines>
  </order>
</orders>';

SELECT
    O.n.value('(@id)[1]', 'bigint') AS order_id,
    O.n.value('(@status)[1]', 'nvarchar(20)') AS status,
    O.n.value('(customer/code/text())[1]', 'nvarchar(30)')
        AS customer_code,
    O.n.value('(customer/name/text())[1]', 'nvarchar(100)')
        AS customer_name
FROM @doc.nodes('/orders/order') AS O(n);
```

Giải thích:

- `@doc` là biến kiểu XML.
- `.nodes('/orders/order')` tạo một tập dòng ngữ cảnh, mỗi dòng gắn với một `order`.
- `AS O(n)` đặt alias cho rowset và cột ngữ cảnh XML.
- `O.n.value('(@id)[1]', 'bigint')` lấy attribute ID từ order hiện tại; `[1]` giúp biểu thức đáp ứng yêu cầu singleton theo static typing của SQL Server XQuery.
- `.value(..., 'nvarchar(...)')` chuyển kết quả thành kiểu SQL Server.

### 24.1. Lấy các line theo quan hệ cha-con bằng CROSS APPLY

```sql
SELECT
    O.n.value('(@id)[1]', 'bigint') AS order_id,
    L.n.value('(@no)[1]', 'int') AS line_no,
    L.n.value('(@sku)[1]', 'nvarchar(30)') AS sku,
    L.n.value('(quantity/text())[1]', 'int') AS quantity,
    L.n.value('(unit_price/text())[1]', 'decimal(12,2)')
        AS unit_price
FROM @doc.nodes('/orders/order') AS O(n)
CROSS APPLY O.n.nodes('lines/line') AS L(n)
ORDER BY order_id, line_no;
```

Trong SQL Server, `CROSS APPLY` cho phép biểu thức `O.n.nodes('lines/line')` chạy dựa trên **order context của hàng bên trái**. Cách này giữ rõ parent order ID mà không cần viết XPath leo hai cấp cha từ line.

Kết quả có hai line cho order 1001 trong ví dụ SQL Server riêng.

### 24.2. Kiểm tra tồn tại

```sql
SELECT
    @doc.exist('/orders/order[@status="PAID"]') AS has_paid_order;
```

Trong SQL Server, `.exist()` trả dạng giá trị như 1/0 hoặc NULL theo input ngữ cảnh; khác với tên/cú pháp `XMLEXISTS` của PostgreSQL.

**Không chuyển nguyên `XMLTABLE` của PostgreSQL sang SQL Server rồi nghĩ chỉ cần đổi tên function.** SQL Server có bộ phương thức XML và các quy tắc XQuery riêng.

## 25. SQL Server: tránh nhân dòng khi có nhiều danh sách con

Trong SQL Server:

```sql
FROM @doc.nodes('/orders/order') AS O(n)
CROSS APPLY O.n.nodes('lines/line') AS L(n)
```

tạo dòng cho mỗi line. Nếu thêm:

```sql
CROSS APPLY O.n.nodes('discounts/discount') AS D(n)
```

mà mỗi order có 2 line và 3 discount, kết quả có thể thành 6 dòng.

Nếu muốn tổng số tiền của line và tổng discount, hãy **tính riêng từng tập**, aggregate theo order rồi JOIN các kết quả. Không sửa bằng `DISTINCT` tùy tiện: hai line độc lập có cùng số tiền vẫn là hai giao dịch cần giữ.

Đây là bài toán cardinality quan hệ, dù dữ liệu xuất phát từ XML hay bảng thông thường.

## 26. Oracle Database: XMLTYPE và XMLTABLE

Oracle có khả năng SQL/XML phong phú. Một mẫu XMLTABLE tương tự về ý tưởng nhưng cú pháp/kiểu khác PostgreSQL:

```sql
-- Oracle Database:
SELECT
    x.order_id,
    x.status,
    x.customer_code
FROM XMLTABLE(
    '/orders/order'
    PASSING XMLTYPE(
      '<orders>
         <order id="1001" status="PAID">
           <customer><code>C001</code></customer>
         </order>
         <order id="1002" status="PENDING">
           <customer><code>C002</code></customer>
         </order>
       </orders>'
    )
    COLUMNS
        order_id NUMBER PATH '@id',
        status VARCHAR2(20) PATH '@status',
        customer_code VARCHAR2(30) PATH 'customer/code'
) x
ORDER BY x.order_id;
```

Ở Oracle:

- `XMLTYPE` biểu diễn XML theo khả năng của Oracle.
- `XMLTABLE` tạo rowset từ XML.
- `COLUMNS ... PATH ...` ánh xạ giá trị vào kiểu SQL như `NUMBER`, `VARCHAR2`.
- Các tính năng XMLTABLE/XMLQUERY dùng một hệ khả năng SQL/XML/XQuery khác PostgreSQL XPath 1.0.

### 26.1. Oracle và namespace

Khi XML dùng namespace, Oracle `XMLTABLE` có thể khai báo `XMLNAMESPACES` tương ứng:

```sql
-- Phác thảo Oracle: XMLTYPE và COLUMNS theo schema thật.
XMLTABLE(
    XMLNAMESPACES('urn:demo:orders' AS "d"),
    '/d:orders/d:order'
    PASSING xml_column
    COLUMNS
        order_id NUMBER PATH '@id'
)
```

Đây là **đoạn biểu thức minh họa** đặt vào `FROM` với `xml_column` là cột XMLTYPE đã tồn tại; không phải query đầy đủ độc lập.

Các phiên bản Oracle khác nhau có khuyến nghị cụ thể về lưu XML, XML index, typed/untyped XML, và một số API cũ. Với hệ thống thực, cần xác nhận tính năng theo phiên bản, không lấy ví dụ chung làm quyết định index.

### 26.2. Oracle có cơ chế XMLQUERY, nhưng không phải lúc nào cũng cần

Nếu chỉ muốn **mỗi order/line thành hàng**, XMLTABLE có thể đủ. `XMLQUERY` phù hợp khi cần biểu thức XQuery dựng/trả XML kết quả phức tạp; nó không tự động tốt hơn XMLTABLE cho mục tiêu trích cột quan hệ đơn giản.

## 27. MySQL và MariaDB: đừng giả định XMLTABLE có sẵn

MySQL và MariaDB có sự khác biệt đáng kể về tính năng XML.

### 27.1. MySQL hiện đại

Trong dòng MySQL 8.x, các hàm XML legacy `ExtractValue()` và `UpdateXML()` đã bị loại bỏ, nên không nên dựa vào chúng như API XML chuẩn có sẵn. MySQL không cung cấp `XMLTABLE` tương tự PostgreSQL/Oracle để unnest XML tổng quát theo mẫu bài này.

Một hướng thực tế:

1. Nhận XML ở tầng ứng dụng hoặc ETL.
2. Parse bằng thư viện XML an toàn.
3. Xác thực XSD/schema và dữ liệu nghiệp vụ.
4. Chuyển thành danh sách header/line có kiểu dữ liệu rõ.
5. Ghi bằng prepared statements/bulk insert vào bảng quan hệ trong transaction.

Nếu hệ thống phải lưu bản XML gốc trong MySQL, có thể cân nhắc cột văn bản như `LONGTEXT` với chính sách encoding/kích thước phù hợp, nhưng **LONGTEXT không tự trở thành XML type có khả năng XPath/XMLTABLE chuẩn**.

### 27.2. MariaDB

MariaDB có các hàm xử lý XML như `EXTRACTVALUE()` trong những phiên bản hỗ trợ.

Ví dụ ý tưởng:

```sql
-- MariaDB: trích dữ liệu XML theo hàm được phiên bản hỗ trợ.
SELECT EXTRACTVALUE(
    '<root><name>An</name></root>',
    '/root/name'
) AS name_text;
```

Đây là thao tác **trích giá trị**; không đồng nghĩa MariaDB hỗ trợ rowset XMLTABLE như PostgreSQL. Các đường dẫn trả nhiều giá trị, thiếu giá trị, namespace và khả năng xử lý XPath còn tùy semantics của hàm.

**Không khuyến khích triển khai ETL nhiều cấp order/line bằng cách cố ghép EXTRACTVALUE và chuỗi text theo vị trí** nếu cần tính đúng đắn cao. Khi DBMS thiếu công cụ unnest XML phù hợp, parser/ETL ngoài DB thường rõ và dễ kiểm thử hơn.

### 27.3. Nếu cần chuyển XML thành JSON trước?

Một số hệ hiện đại có hệ sinh thái JSON query mạnh. Có thể parse XML tại ứng dụng rồi chuyển thành JSON có schema rõ, sau đó dùng khả năng JSON của DBMS. Nhưng chuyển đổi này **không miễn phí và không bảo đảm giữ mọi ngữ nghĩa XML** như:

- Namespace.
- Thứ tự text xen kẽ với element (*mixed content*).
- Attribute so với element.
- Comment/processing instruction.
- Các element lặp và số lượng không nhất quán.

Nếu chọn XML → JSON, phải định nghĩa **quy tắc mapping** và kiểm thử trường hợp méo dữ liệu. Không coi JSON là bản thay thế XML bảo toàn mọi cấu trúc chỉ bằng một hàm tự động.

## 28. SQLite: XML xử lý ở tầng ứng dụng hoặc extension

SQLite không cung cấp kiểu `XML`/`XMLTABLE`/`XPath` SQL native tích hợp theo mô hình PostgreSQL hay Oracle.

Nếu một ứng dụng desktop/mobile lưu XML:

```sql
CREATE TABLE inbound_documents (
    document_id INTEGER PRIMARY KEY,
    payload TEXT NOT NULL
);
```

thì cột `payload` là **văn bản**. SQLite không tự hiểu:

```sql
-- Không phải cú pháp XMLTABLE native của SQLite:
SELECT *
FROM XMLTABLE(...);
```

Hướng phổ biến là:

- Parse XML bằng thư viện của ứng dụng.
- Chuyển thành object/record có kiểu.
- Validate rồi ghi vào bảng quan hệ.
- Nếu có extension XML tự cài, xác nhận hàm/cú pháp/chi phí và rủi ro triển khai riêng.

Không gợi ý dùng các extension không có sẵn như thể đó là khả năng mặc định của SQLite.

## 29. Tính di động: cùng bài toán, API khác nhau

| Nhiệm vụ | PostgreSQL | Oracle | SQL Server | MySQL/MariaDB | SQLite |
| --- | --- | --- | --- | --- | --- |
| Lưu XML có nhận thức cấu trúc | `xml` | `XMLTYPE` | `xml` | Chủ yếu văn bản/ETL tùy hệ | TEXT/BLOB nếu cần |
| Kiểm tra nút tồn tại | `XMLEXISTS` / `xpath` | `XMLExists` hoặc tính năng SQL/XML phù hợp | `xml.exist()` | Tùy bản/hàm legacy; app thường phù hợp hơn | Ứng dụng/extension |
| Trích một giá trị | `xpath` hoặc `XMLTABLE` | `XMLTABLE`/`XMLQUERY` | `xml.value()` | `EXTRACTVALUE` ở MariaDB phiên bản hỗ trợ | Ứng dụng/extension |
| Biến nút lặp thành hàng | `XMLTABLE` | `XMLTABLE` | `xml.nodes()` với `CROSS APPLY` | Thường ETL bên ngoài | Thường ETL bên ngoài |
| Namespace | Mapping trong `XMLNAMESPACES` hoặc `xpath` | `XMLNAMESPACES`/XQuery | XQuery `declare namespace` hoặc `WITH XMLNAMESPACES` | Tùy chức năng | Ứng dụng |
| XQuery mở rộng | Không đầy đủ kiểu Oracle | Hỗ trợ sâu hơn | XQuery subset | Không giả định có | Không mặc định |
| Index XML chuyên dụng | Cân nhắc mô hình trích cột/index thông thường; tùy extension/tính năng | Tùy XML DB/XML index | XML indexes tùy tình huống | Tùy chuyển đổi/staging | Không mặc định |

**Lời khuyên thiết kế:** nếu dự án phải chạy đa DBMS, hãy xác định một **hợp đồng ánh xạ chung** (tên trường, kiểu, trường bắt buộc, cardinality, namespace, lỗi) rồi triển khai adapter theo từng DBMS hoặc parse ở tầng ứng dụng. Không cố giấu khác biệt lớn sau một câu SQL “chuẩn” nhưng thực tế không chạy được.

## 30. Index và hiệu năng khi truy vấn XML

Truy vấn XML có thể tốn CPU và bộ nhớ hơn một phép truy vấn B-tree đơn giản vì engine cần xử lý cấu trúc node/path, nhất là với tài liệu lớn.

Các yếu tố:

1. **Kích thước XML:** số byte và độ sâu cây.
2. **Số phần tử lặp:** hàng nghìn order/line có thể tạo số hàng rất lớn.
3. **Đường dẫn XPath/XQuery:** wildcard, descendant axis `//` và biểu thức phức tạp có thể tốn hơn đường dẫn rõ.
4. **Số lần parse:** gọi XMLTABLE nhiều lần trên cùng payload để lấy header và line có thể lặp lại công việc; cần đo theo workload.
5. **Lọc batch trước:** tránh parse toàn bộ kho staging khi chỉ cần một batch.
6. **Index chuyên dụng:** mức hỗ trợ XML index phụ thuộc DBMS, không đồng nhất.
7. **Khả năng cache/ETL:** có thể trích trường thường truy vấn vào cột quan hệ riêng, index bằng B-tree.
8. **Memory/temporary data:** XML unnest có thể sinh nhiều hàng trung gian, đặc biệt khi JOIN nhiều danh sách con.

### 30.1. Nên trích dữ liệu quan hệ thường dùng

Nếu một ứng dụng liên tục hỏi:

> “Đơn PAID của khách C001 trong 30 ngày qua là gì?”

mà mọi truy vấn đều parse một triệu XML document, có thể kém hiệu quả hơn lưu `order_headers` đã chuẩn hóa với index thích hợp:

```sql
CREATE INDEX ix_sql368_headers_customer_date
ON sql368.order_headers(customer_code, placed_on);
```

Rồi truy vấn:

```sql
SELECT order_id, status, placed_on
FROM sql368.order_headers
WHERE customer_code = 'C001'
  AND status = 'PAID'
  AND placed_on >= DATE '2026-11-01'
ORDER BY placed_on DESC, order_id DESC;
```

Đây là ví dụ index theo dữ liệu quan hệ đã ánh xạ, không phải XML index. Nếu cần nghiên cứu XML index của Oracle/SQL Server, phải dựa trên tính năng và workload của đúng hệ đang triển khai.

### 30.2. EXPLAIN để hiểu kế hoạch PostgreSQL

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT x.order_id, x.status
FROM sql368.import_batches AS b
CROSS JOIN LATERAL XMLTABLE(
    '/orders/order'
    PASSING b.payload
    COLUMNS
        order_id BIGINT PATH '@id',
        status TEXT PATH '@status'
) AS x
WHERE b.batch_id = 1;
```

Quan sát:

- Có lọc đúng batch trước bước parse XML không?
- Số hàng của XMLTABLE thực tế bao nhiêu?
- Có parse lặp trên nhiều batch không?
- Tổng thời gian truy vấn là bao nhiêu?

Với tài liệu lab rất nhỏ, không nên diễn giải chênh lệch vài micro/millisecond như một kết luận tối ưu chắc chắn. Khi benchmark, cần dữ liệu đủ đại diện và đo nhiều lần.

## 31. XML lớn: cân nhắc streaming thay vì một payload khổng lồ

Với file XML vài megabyte, XMLTABLE tại DBMS có thể thuận tiện. Nhưng khi file lên tới nhiều gigabyte hoặc hàng triệu phần tử, việc tải toàn bộ tài liệu vào một ô XML và parse trong một lệnh có thể gây áp lực bộ nhớ và transaction lớn.

Một hướng khác:

```text
File XML lớn
     |
     v
Streaming parser an toàn (SAX / StAX / pull parser)
     |
     +-- header events --> batch insert headers
     |
     +-- line events   --> batch insert lines
     |
     v
Validation + transaction/chunk boundary
     |
     v
Tables + load checkpoints + error records
```

Điểm mạnh của streaming:

- Không cần giữ toàn bộ cây XML trong RAM ứng dụng.
- Có thể xử lý theo từng batch/chunk.
- Dễ kiểm soát throughput, checkpoint và giới hạn kích thước.
- Có thể ghi lỗi theo vị trí dòng/bản ghi nguồn.

Nhưng streaming phải xử lý **parent context** (order hiện tại), transaction, retry và thứ tự phụ thuộc FK rất cẩn thận. Không vì dữ liệu lớn mà bỏ validate hoặc bỏ bảo vệ constraint.

## 32. Bảo mật XML: XXE, XML bomb và XPath injection

XML đến từ đối tác hoặc người dùng là **dữ liệu không đáng tin cậy cho đến khi được xác thực**.

### 32.1. External entity (XXE)

Một số parser XML có khả năng xử lý DTD và entity bên ngoài. Nếu cấu hình không an toàn, tài liệu có thể cố truy cập tài nguyên file/nội bộ hoặc gây rò rỉ thông tin.

Đối sách:

- Dùng parser/DBMS được cấu hình **không tự tải external entities** từ nguồn không tin cậy.
- Hạn chế hoặc vô hiệu hóa DTD/external entity khi ứng dụng không cần.
- Kiểm soát network/file access của tiến trình parse.
- Xác minh cấu hình **thực tế của thư viện/DBMS và phiên bản**, không tin mặc định chung.

### 32.2. XML expansion/“billion laughs”

Một tài liệu nhỏ có thể được thiết kế để nở ra khối dữ liệu rất lớn khi xử lý entity, gây cạn CPU/RAM. Cần giới hạn:

- Kích thước tài liệu.
- Độ sâu nesting.
- Số node và độ dài text.
- Entity expansion.
- Thời gian parse và tài nguyên.

### 32.3. XPath/XQuery injection

Nếu ghép chuỗi do người dùng nhập trực tiếp vào đường dẫn:

```text
XPath: /orders/order[@status="USER_INPUT"]
```

mà `USER_INPUT` chứa dấu nháy hoặc biểu thức XPath đặc biệt, người dùng có thể thay đổi ngữ nghĩa bộ lọc.

Tốt hơn:

- Dùng **đường dẫn cố định** cho hợp đồng dữ liệu.
- Bind giá trị bằng API/query variables được DBMS hỗ trợ khi có thể.
- Nếu phải tạo biểu thức động, dùng allowlist cho tên node/attribute và escape/bind đúng ngôn ngữ; không tự nối input thành XPath một cách ngây thơ.
- Kiểm soát quyền DBMS/ứng dụng để một truy vấn XML không được phép tiết lộ dữ liệu vượt phạm vi.

**Chống SQL injection không tự động chống XPath injection** nếu bạn vẫn tạo một chuỗi XPath động ở tầng khác.

## 33. Vấn đề encoding, ký tự đặc biệt và canonicalization

XML thường dùng UTF-8, nhưng tài liệu có thể mang khai báo encoding:

```xml
<?xml version="1.0" encoding="UTF-8"?>
```

Các vấn đề dễ gặp:

- Byte thực tế không đúng encoding đã khai báo.
- Chuỗi từ ứng dụng đã bị decode sai trước khi đưa vào DB.
- Ký tự XML đặc biệt `&`, `<`, dấu nháy trong attribute không được escape đúng.
- Unicode normalization khác nhau khiến hai giá trị nhìn giống nhau nhưng so sánh SQL không bằng nhau.
- Line endings/whitespace và cách serialization có thể thay đổi khi lưu/trả XML.

### 33.1. Đừng dùng so sánh chuỗi thô để xác định “cùng XML”

Hai tài liệu có thể cùng ngữ nghĩa nhưng text serialization khác nhau:

```xml
<item id="1" status="PAID"/>
```

```xml
<item status="PAID" id="1"></item>
```

Thứ tự attribute không mang ý nghĩa như thứ tự các phần tử con trong XML. So sánh hai chuỗi byte nguyên văn có thể cho “khác” dù dữ liệu cây tương đương ở góc nhìn nghiệp vụ.

Nếu cần kiểm tra chữ ký số XML, so sánh hoặc canonicalization, dùng cơ chế XML canonicalization và thư viện chữ ký đúng chuẩn; **không tự sắp xếp chuỗi hoặc loại whitespace bừa bãi** vì mixed content và chữ ký có thể bị ảnh hưởng.

## 34. Hệ quả của đổi cấu trúc và phiên bản schema XML

Một đối tác có thể thay từ:

```xml
<order id="1001">
  <customer><code>C001</code></customer>
</order>
```

sang:

```xml
<order id="1001">
  <buyer><customer_code>C001</customer_code></buyer>
</order>
```

Khi đó `PATH 'customer/code'` không còn tìm được giá trị, dù tài liệu vẫn well-formed.

Cần quản lý:

1. **Version của hợp đồng XML**, ví dụ attribute `version="1"`.
2. Danh sách namespace URI tương ứng từng version.
3. Mapping path và kiểu dữ liệu của từng version.
4. Trường bắt buộc/tùy chọn.
5. Chính sách tương thích ngược.
6. Test fixture với tài liệu thật của mỗi version.
7. Quy trình từ chối version không hỗ trợ thay vì âm thầm mất dữ liệu.

Một pattern là **router theo version** ở tầng ETL:

```text
XML v1 --> mapping v1 --> canonical relational schema
XML v2 --> mapping v2 --> canonical relational schema
XML v3 --> mapping v3 --> canonical relational schema
```

Bảng quan hệ đích có thể vẫn giữ hợp đồng ổn định cho các báo cáo, dù đường dẫn XML thay đổi theo version.

## 35. Khi nào nên giữ XML thay vì chuyển hết thành bảng?

Không phải mọi tài liệu XML đều cần bị “làm phẳng” hoàn toàn.

**Giữ XML** phù hợp khi:

- Cần lưu toàn bộ tài liệu gốc để đối soát hoặc trao đổi lại.
- Cấu trúc mở, nhiều phần tử tùy chọn hiếm khi truy vấn.
- Ứng dụng cần truyền bản XML nguyên vẹn giữa các hệ.
- Có tính năng SQL/XML và index phù hợp cho tập truy vấn thực tế.

**Chuyển về bảng** phù hợp khi:

- Cần JOIN nhiều bảng theo khóa.
- Cần ràng buộc FK/UNIQUE/CHECK.
- Thường xuyên lọc theo ngày/trạng thái/khách hàng.
- Cần aggregate, báo cáo, phân trang lớn.
- Muốn chuẩn hóa dữ liệu từ nhiều nguồn XML khác nhau về một schema chung.

**Thiết kế lai** thường hữu ích: lưu metadata và trường cần truy vấn vào cột SQL, giữ XML gốc để tham chiếu/đối soát trong thời hạn được phép.

Không nên biến một cột XML thành “kho chứa mọi thuộc tính” chỉ vì không muốn thiết kế bảng; nhưng cũng không nên tạo hàng trăm cột cho các phần XML ít dùng, luôn thay đổi và không có yêu cầu truy vấn.

## 36. Các lỗi phổ biến khi ánh xạ XML

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| XMLTABLE trả 0 dòng | Row path sai hoặc thiếu namespace | Kiểm tra root, cấp path và URI namespace |
| Có dòng nhưng cột toàn NULL | Column path sai hoặc element không tồn tại | Kiểm tra context node và path tương đối |
| Số line nhiều hơn dự kiến | Join nhiều danh sách con độc lập | Aggregate/tách bảng con theo khóa cha |
| Không đọc được attribute | Nhầm `@id` với `id` | Dùng `@...` cho attribute |
| ID order của line thành NULL | Đi lên sai số cấp `../..` | Kiểm tra cây XML; cân nhắc nested context |
| XML không parse được | Thiếu thẻ, escape sai, encoding sai | Dùng parser; báo lỗi well-formed |
| DATE/NUMERIC conversion lỗi | Giá trị không đúng format/miền | Validate trước CAST; tách bản lỗi |
| Thiếu customer code nhưng ETL vẫn chạy | Path thiếu được map thành NULL/default | Quy định trường bắt buộc, validate NOT NULL |
| Một node trả nhiều giá trị cho cột scalar | XML cho phép lặp nhưng mapping không xử lý | Xác định cardinality; unnest thành hàng |
| Dùng XPath `//order` bắt dư node | Chọn element ở mọi cấp | Dùng path tuyệt đối phù hợp |
| Namespace prefix đổi làm path vỡ | Hardcode prefix của nguồn thay vì URI | Khai báo prefix XPath theo URI |
| Nạp lại batch tạo trùng PK | Chưa có idempotency | Quản lý batch ID/key, xác minh dữ liệu nguồn |
| Query XML chậm khi bảng staging lớn | Parse nhiều payload/giảm hiệu quả index | Lọc batch, materialize trường phổ biến |
| DBMS báo không có XMLTABLE | Tính năng khác theo sản phẩm/phiên bản | Dùng XML API native hoặc ETL ngoài DB |
| XML chứa external entity nguy hiểm | Parser có cấu hình XXE chưa an toàn | Tắt external entity/network, giới hạn tài nguyên |
| Chuyển XML thành JSON mất attribute/namespace | Mapping không bảo toàn cấu trúc | Định nghĩa và test quy tắc chuyển đổi |

## 37. Bài tập thực hành

Các bài sử dụng XML và schema `sql368` của mục 9–22. Với các câu SQL cố ý tạo lỗi, thực hiện riêng trên môi trường học tập.

### Bài 1 — Nhận diện node và đường dẫn

Trong XML đầu bài, hãy chỉ ra:

a. Đường dẫn tuyệt đối tới mọi order.

b. Đường dẫn tới attribute ID của order.

c. Đường dẫn tới mọi line.

d. Đường dẫn tới element quantity dưới mỗi line.

e. Attribute SKU của một line hiện tại.

### Bài 2 — Lọc order theo attribute

Viết XPath lấy các phần tử `order` có `status="PAID"`. Mục đích của dấu `[...]` là gì?

### Bài 3 — Kiểm tra sự tồn tại

Viết truy vấn PostgreSQL `XMLEXISTS` trả boolean cho batch 1: tài liệu có ít nhất một order PAID không?

### Bài 4 — Trích header thành hàng

Viết XMLTABLE PostgreSQL tạo các cột:

- `order_id BIGINT` từ `@id`.
- `status TEXT` từ `@status`.
- `customer_code TEXT` từ `customer/code`.
- `customer_name TEXT` từ `customer/name`.

Giải thích vì sao kết quả có hai dòng.

### Bài 5 — Trích line thành hàng

Viết XMLTABLE trả `order_id`, `line_no`, `sku`, `quantity` và `unit_price`. Tại node line, đi lên mấy cấp để lấy `order/@id`?

### Bài 6 — FOR ORDINALITY

Thêm cột `position FOR ORDINALITY` khi lấy order. Vì sao không nên dùng position thay order_id làm khóa chính toàn hệ?

### Bài 7 — Tính doanh thu

Từ rowset line, tính subtotal của order 1001 và 1002 bằng `SUM(quantity * unit_price)`. Có bao nhiêu dòng cho từng order?

### Bài 8 — Row path sai và column path sai

So sánh:

a. `XMLTABLE('/orders/item' ...)`.

b. `XMLTABLE('/orders/order' ... COLUMNS customer_code TEXT PATH 'buyer/code')`.

Với XML mẫu, kết quả về **số hàng** và **giá trị cột** khác nhau thế nào?

### Bài 9 — Phần tử thiếu

Giả sử order 1003 không có `customer/code`. Hãy nêu hai chính sách ETL hợp lý khác nhau: một chính sách bắt buộc code và một chính sách cho phép chưa biết code. Lớp nào sẽ enforce?

### Bài 10 — Namespace

Với XML có `xmlns="urn:demo:orders"`, vì sao `/orders/order` có thể không khớp? Viết path với prefix `d` ánh xạ tới URI đó.

### Bài 11 — Default namespace và attribute

Trong `<orders xmlns="urn:demo:orders"><order id="1001"/></orders>`, XPath lấy element order và attribute id cần prefix ở những vị trí nào?

### Bài 12 — SQL Server

Viết ý tưởng dùng `.nodes('/orders/order')` và `.value('(@id)[1]', 'bigint')` để lấy ID. Giải thích lý do `[1]` xuất hiện thường xuyên trong `value()`.

### Bài 13 — SQL Server nested lines

Vì sao `CROSS APPLY O.n.nodes('lines/line')` phù hợp hơn việc chỉ đọc `@doc.nodes('/orders/order')` nếu mục tiêu là một dòng cho mỗi line?

### Bài 14 — Oracle

Kể tên kiểu dữ liệu XML và tính năng ánh xạ rowset trong Oracle. Viết một cột `order_id NUMBER PATH '@id'` trong XMLTABLE.

### Bài 15 — MySQL/MariaDB/SQLite

Hãy giải thích vì sao không thể mang nguyên câu PostgreSQL `XMLTABLE(...)` sang MySQL 8.x hoặc SQLite, và khi đó pipeline nên xử lý XML ở đâu.

### Bài 16 — Nạp và ràng buộc

Vì sao cần insert `order_headers` trước `order_lines` trong schema lab? Nếu line có `order_id=9999` mà không có header, cơ chế nào phát hiện?

### Bài 17 — Trùng khóa khi retry

Nếu chạy lại hai câu INSERT của mục 22 với cùng batch, có thể phát sinh lỗi gì? Vì sao `ON CONFLICT DO NOTHING` không tự bảo đảm idempotency nghiệp vụ?

### Bài 18 — XML lớn

Hệ cần xử lý file XML có 2 triệu line. Nêu khi nào có thể cân nhắc streaming parser và những thông tin nào phải giữ để mapping được line về order cha.

### Bài 19 — XXE và injection

Nêu hai biện pháp phòng XXE/XML bomb, và lý do không nên nối input người dùng trực tiếp vào XPath động.

### Bài 20 — Tư duy thiết kế

Hệ thống cần chạy báo cáo theo khách hàng mỗi ngày nhưng cũng phải lưu tài liệu XML đầy đủ từ đối tác. Đề xuất thiết kế bảng/XML lưu trữ, đường dữ liệu ETL, index quan hệ và chính sách giữ XML.

## 38. Gợi ý đáp án và giải thích

**Bài 1.** a `/orders/order`; b `/orders/order/@id`; c `/orders/order/lines/line`; d `/orders/order/lines/line/quantity`; e `@sku` từ node line.

**Bài 2.**

```xpath
/orders/order[@status="PAID"]
```

`[...]` là predicate lọc các node order theo điều kiện trong ngoặc.

**Bài 3.**

```sql
SELECT
    XMLEXISTS(
        '/orders/order[@status="PAID"]'
        PASSING BY REF b.payload
    ) AS has_paid_order
FROM sql368.import_batches AS b
WHERE b.batch_id = 1;
```

Kết quả mong đợi `TRUE`.

**Bài 4.**

```sql
SELECT
    x.order_id, x.status, x.customer_code, x.customer_name
FROM sql368.import_batches AS b
CROSS JOIN LATERAL XMLTABLE(
    '/orders/order'
    PASSING b.payload
    COLUMNS
        order_id BIGINT PATH '@id',
        status TEXT PATH '@status',
        customer_code TEXT PATH 'customer/code',
        customer_name TEXT PATH 'customer/name'
) AS x
WHERE b.batch_id = 1
ORDER BY x.order_id;
```

Có hai phần tử order nên ra hai hàng.

**Bài 5.**

```sql
SELECT
    x.order_id, x.line_no, x.sku, x.quantity, x.unit_price
FROM sql368.import_batches AS b
CROSS JOIN LATERAL XMLTABLE(
    '/orders/order/lines/line'
    PASSING b.payload
    COLUMNS
        order_id BIGINT PATH '../../@id',
        line_no INTEGER PATH '@no',
        sku TEXT PATH '@sku',
        quantity INTEGER PATH 'quantity',
        unit_price NUMERIC(12,2) PATH 'unit_price'
) AS x
WHERE b.batch_id = 1;
```

Từ line lên `lines`, rồi lên `order`, tức **hai cấp**.

**Bài 6.** `FOR ORDINALITY` đánh số thứ tự node trong rowset XMLTABLE. Nếu đối tác đổi thứ tự order trong tài liệu, ordinal thay đổi; `order_id` theo hợp đồng có thể ổn định.

**Bài 7.** Order 1001 có 2 line, subtotal `2×120.50 + 3×10.00 = 271.00`. Order 1002 có 1 line, subtotal `1×50.00 = 50.00`.

**Bài 8.** a trả 0 hàng vì tài liệu không có node `/orders/item`. b vẫn có 2 hàng order nhưng `customer_code` NULL vì không có `buyer/code`.

**Bài 9.** Nếu bắt buộc: kiểm tra XSD/mapping `NOT NULL` hoặc constraint của bảng đích rồi từ chối batch thiếu code. Nếu tùy chọn: cho NULL có chủ đích, lưu cảnh báo/ trạng thái chưa ánh xạ và xử lý bổ sung; không che thiếu dữ liệu vô tình.

**Bài 10.**

```xpath
/d:orders/d:order
```

Khai báo `d` ánh xạ tới `urn:demo:orders`. Mặc định namespace của XML không tự áp vào tên element không-prefix trong XPath.

**Bài 11.** Element cần `d:orders/d:order`; attribute `id` không prefix nên dùng `@id` (ví dụ `/d:orders/d:order/@id`).

**Bài 12.**

```sql
SELECT O.n.value('(@id)[1]', 'bigint') AS order_id
FROM @doc.nodes('/orders/order') AS O(n);
```

`[1]` giúp bảo đảm expression được xem như singleton theo static typing của SQL Server XQuery.

**Bài 13.** `.nodes('/orders/order')` chỉ tạo một hàng mỗi order. `CROSS APPLY O.n.nodes('lines/line')` tiếp tục unnest line **trong từng order**, tạo đúng cấp dòng hàng.

**Bài 14.** Oracle dùng `XMLTYPE`; `XMLTABLE` tạo rowset. Cột ví dụ:

```sql
order_id NUMBER PATH '@id'
```

**Bài 15.** MySQL 8.x không cung cấp XMLTABLE native như PostgreSQL/Oracle; SQLite cũng không có XMLTABLE/XPath SQL native. Có thể parse/validate XML bằng thư viện trong ứng dụng hoặc ETL rồi batch insert vào bảng quan hệ.

**Bài 16.** Bảng `order_lines` có FK tới `order_headers`, nên header phải có trước khi insert line theo quy tắc immediate FK. Line tham chiếu order 9999 không tồn tại bị FK chặn.

**Bài 17.** Có thể lỗi `PRIMARY KEY` hoặc `UNIQUE` tại bảng đích. `ON CONFLICT DO NOTHING` chỉ bỏ qua dòng trùng khóa, không xác minh nội dung nguồn có giống lần trước hoặc chưa làm mất cập nhật.

**Bài 18.** Streaming có ích khi một document quá lớn để parse/lưu nguyên khối thuận tiện. Parser phải giữ context của order hiện tại (ID, các trường header cần thiết), vị trí line, trạng thái validation, transaction/batch checkpoint và handling khi order bị thiếu/không hợp lệ.

**Bài 19.** Tắt external entities/DTD không cần thiết, giới hạn kích thước/độ sâu/entity expansion và tài nguyên parse. XPath động ghép từ input chưa kiểm soát có thể bị đổi điều kiện truy vấn, cần bind/allowlist/escape đúng ngữ cảnh.

**Bài 20.** Dùng bảng staging XML có batch metadata và quyền/retention rõ; ETL xác thực XML/namespace/version; nạp `order_headers` và `order_lines` có PK/FK/CHECK trong transaction; tạo index theo `customer_code` và `placed_on` cho báo cáo; giữ XML gốc theo thời hạn audit cần thiết, không giữ vĩnh viễn theo mặc định.

## 39. Dọn dữ liệu học tập

Sau khi hoàn thành bài và chắc chắn schema `sql368` chỉ chứa các đối tượng do **chính bài học tạo ra**, có thể dọn:

```sql
-- PostgreSQL: chỉ chạy trong database học tập đã xác nhận.
DROP SCHEMA sql368 CASCADE;
```

Lệnh này xóa bảng staging, bảng đầu đơn, dòng đơn, chỉ mục trong schema và các đối tượng phụ thuộc theo cơ chế PostgreSQL. **Không chạy trên schema dùng chung hoặc sản xuất** khi chưa kiểm tra dependency; `CASCADE` có thể ảnh hưởng đối tượng tham chiếu bên ngoài schema.

## 40. Kết luận

Truy vấn XML trong SQL có hai bước tư duy bắt buộc: **chọn đúng node bằng đường dẫn** và **xác định cấp node nào trở thành một hàng quan hệ**. XPath mô tả đường đi trong cây XML; các cơ chế như `XMLTABLE` của PostgreSQL/Oracle hoặc `xml.nodes()` kết hợp `value()` của SQL Server biến phần tử lặp thành hàng/cột có kiểu để SQL có thể JOIN, lọc và tổng hợp.

Một triển khai đúng cần hiểu **element khác attribute**, **đường dẫn tuyệt đối khác đường dẫn tương đối**, **namespace URI khác prefix**, **thiếu node khác node rỗng**, và **kiểu XML khác kiểu SQL của cột đích**. Khi mapping dữ liệu nhiều cấp, hãy giữ khóa cha-con rõ ràng, dùng transaction và constraint khi nạp bảng vật lý; không để một XPath sai âm thầm làm mất hàng hoặc trường bắt buộc.

Cuối cùng, **khả năng hỗ trợ XML khác nhau rõ rệt giữa các DBMS**. PostgreSQL có `xpath/XMLEXISTS/XMLTABLE`, Oracle có SQL/XML và XQuery phong phú, SQL Server có các phương thức trên kiểu `xml`, trong khi MySQL/MariaDB và SQLite thường cần giải pháp ETL hoặc cơ chế riêng tùy phiên bản. Chọn giải pháp theo **khả năng thực tế của hệ đang chạy, khối lượng dữ liệu, yêu cầu truy vấn và mức độ an toàn của quá trình parse**, chứ không chỉ theo tên một hàm SQL.

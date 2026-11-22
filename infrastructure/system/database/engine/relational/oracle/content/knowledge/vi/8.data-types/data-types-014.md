# Kiểu dữ liệu người dùng, object type và collection type trong Oracle Database

## 1. Vì sao Oracle hỗ trợ kiểu dữ liệu do người dùng định nghĩa?

Trong mô hình quan hệ, một dòng dữ liệu thường được mô tả bằng các cột kiểu `NUMBER`, `VARCHAR2`, `DATE`, `TIMESTAMP`, `CLOB`... Tuy nhiên, có những giá trị nghiệp vụ mang **cấu trúc riêng**: địa chỉ gồm đường, thành phố; một sản phẩm có mã và đơn giá; đơn hàng có nhiều dòng hàng; người dùng có danh sách số điện thoại. Oracle hỗ trợ **user-defined types (UDT)** để mô tả những cấu trúc này bằng kiểu có tên, tái sử dụng trong SQL hoặc PL/SQL tùy loại.

Ví dụ, thay vì chỉ xem địa chỉ là một chuỗi không cấu trúc:

```text
'42 Nguyen Hue, Ho Chi Minh City'
```

ta có thể biểu diễn nó thành một đối tượng có hai thuộc tính:

```text
ADDRESS_T
  ├── STREET = '42 Nguyen Hue'
  └── CITY   = 'Ho Chi Minh City'
```

Một **collection type** có thể biểu diễn nhiều giá trị cùng kiểu, như danh sách mã khuyến mãi hoặc danh sách các object chứa `SKU` và `QUANTITY`. Oracle còn hỗ trợ **associative array** trong PL/SQL, ánh xạ khóa với giá trị, rất hữu ích để xử lý dữ liệu tạm trong chương trình.

Mục tiêu của bài này là hiểu:

- Sự khác nhau giữa **object type**, **SQL collection type** và **PL/SQL collection type**.
- Cách khai báo, khởi tạo, lưu, truy vấn và thao tác object/collection.
- Sự khác biệt giữa **nested table**, **VARRAY** và **associative array**.
- Các tình huống có thể gây lỗi với `NULL`, collection thưa, thứ tự, phụ thuộc schema type và quyền sử dụng.
- Khi nào mô hình object-relational có lợi, khi nào nên dùng bảng quan hệ thông thường.

> Các ví dụ dùng cú pháp Oracle Database 19c thông dụng. Một số khả năng tích hợp SQL/PLSQL, giới hạn kích thước, JSON và driver có khác biệt theo release. Các lệnh `CREATE TYPE`, `CREATE TABLE`, `INSERT`, `DROP` chỉ nên chạy trong schema lab được phép chỉnh sửa.

## 2. Bản đồ các kiểu dữ liệu phức hợp

```text
                     Oracle composite / user-defined types
                                       │
              ┌────────────────────────┴────────────────────────┐
              │                                                 │
              ▼                                                 ▼
       SQL schema types                                    PL/SQL types
       (CREATE TYPE)                                       (TYPE / RECORD)
              │                                                 │
    ┌─────────┴──────────┐                         ┌─────────────┴──────────┐
    ▼                    ▼                         ▼                        ▼
Object type         Collection type          RECORD / %ROWTYPE       Associative array
attributes          ├─ Nested table          cấu trúc tạm            INDEX BY key
methods             └─ VARRAY                trong PL/SQL            trong PL/SQL
    │                    │                         │                        │
    └────────────┬───────┘                         └────────────┬───────────┘
                 ▼                                              ▼
      Dùng được làm kiểu cột SQL,                  Dùng chủ yếu trong PL/SQL;
      biến PL/SQL, giá trị SQL                     không tương đương SQL column type
```

Oracle phân biệt **kiểu được tạo tại schema** bằng `CREATE TYPE` và **kiểu chỉ khai báo trong PL/SQL** bằng từ khóa `TYPE` hoặc `RECORD`. Một nested table hoặc VARRAY có thể được khai báo ở cả hai phạm vi; tuy nhiên, nếu định lưu nó thành **kiểu của cột trong bảng**, cần **SQL schema-level type**.

| Loại | Cú pháp tạo | Có thể là kiểu cột SQL? | Đặc điểm chính |
| --- | --- | --- | --- |
| Object type | `CREATE TYPE ... AS OBJECT` | Có | Nhiều attribute, có thể có method, constructor, inheritance |
| Nested table SQL type | `CREATE TYPE ... AS TABLE OF ...` | Có | Collection biến độ dài; khi lưu trong table có storage table riêng |
| VARRAY SQL type | `CREATE TYPE ... AS VARRAY(n) OF ...` | Có | Collection có **giới hạn số phần tử**, giữ thứ tự phần tử về mặt giá trị |
| Nested table PL/SQL | `TYPE ... IS TABLE OF ...` trong PL/SQL | Không dùng trực tiếp làm định nghĩa cột SQL | Dữ liệu tạm cho chương trình, có thể thưa sau `DELETE` |
| VARRAY PL/SQL | `TYPE ... IS VARRAY(n) OF ...` trong PL/SQL | Không dùng trực tiếp làm định nghĩa cột SQL | Danh sách nhỏ có thứ tự và giới hạn cố định |
| Associative array | `TYPE ... IS TABLE OF ... INDEX BY ...` | Không được khai báo như cột SQL persistent | Ánh xạ khóa số nguyên hoặc chuỗi với giá trị, không có giới hạn trên khai báo |
| PL/SQL record | `TYPE ... IS RECORD (...)` hoặc `%ROWTYPE` | Không dùng như cột object SQL | Nhóm các trường trong PL/SQL, khác object type schema |

Một số **package-level PL/SQL collection types** có khả năng tham gia câu truy vấn SQL thông qua cơ chế và giới hạn riêng ở các Oracle release hiện đại; điều đó **không** biến associative array thành schema SQL collection type hay cho phép dùng nó trực tiếp trong `CREATE TABLE`.

## 3. Object type là gì?

**Object type** là kiểu SQL có tên được định nghĩa trong schema. Nó mô tả một giá trị có các **attribute** (thuộc tính) và có thể có **member method**, **static method**, **constructor** hoặc logic so sánh. Khái niệm này gần với class trong ngôn ngữ hướng đối tượng, nhưng không nên xem SQL object type tương đương hoàn toàn Java class.

Ví dụ kiểu `ADDRESS_T`:

```sql
-- Chạy trong một schema lab được quyền CREATE TYPE.
CREATE TYPE address_t AS OBJECT (
    street VARCHAR2(120 CHAR),
    city   VARCHAR2(80 CHAR)
);
/
```

Một giá trị thuộc kiểu này có thể được tạo bằng **constructor** tự động:

```sql
SELECT address_t('42 Nguyen Hue', 'Ho Chi Minh City') AS addr
FROM   dual;
```

Đối với object type gồm hai attribute, constructor mặc định được gọi với hai đối số tương ứng. Nếu định nghĩa type thay đổi hoặc có constructor tự viết, cần kiểm tra danh sách constructor thực tế.

### 3.1. Object column trong bảng quan hệ

Khi đã có SQL object type, một cột của bảng quan hệ có thể mang giá trị object:

```sql
CREATE TABLE customer_contacts (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(100 CHAR) NOT NULL,
    address     address_t
);

INSERT INTO customer_contacts (customer_id, full_name, address)
VALUES (
    1,
    'Nguyen An',
    address_t('42 Nguyen Hue', 'Ho Chi Minh City')
);
```

Đọc attribute từ object column:

```sql
SELECT c.customer_id,
       c.full_name,
       c.address.street AS street,
       c.address.city   AS city
FROM   customer_contacts c
WHERE  c.customer_id = 1;
```

**Bí quyết cú pháp:** Khi truy cập attribute/method của object column trong SQL, dùng **table alias** như `c.address.city`. Điều này giúp Oracle phân biệt tên schema, table, column và attribute khi phân giải nhiều dấu chấm.

### 3.2. Một object value, nhiều attribute

```text
CUSTOMER_CONTACTS row
  CUSTOMER_ID = 1                  -- NUMBER
  FULL_NAME   = 'Nguyen An'       -- VARCHAR2
  ADDRESS     = ADDRESS_T(...)    -- object column
                ├── STREET = '42 Nguyen Hue'
                └── CITY   = 'Ho Chi Minh City'
```

Cấu trúc này khác việc có hai cột `ADDRESS_STREET` và `ADDRESS_CITY` trực tiếp trong bảng, vì giá trị `ADDRESS` có **type identity** riêng. Hai object type khác nhau dù cùng tên attribute vẫn là **hai SQL type riêng**, không thể mặc nhiên coi như cùng một record kiểu cấu trúc.

## 4. Null object khác object có attribute `NULL`

Đây là trường hợp dễ gây lỗi nhất khi mới dùng object type.

| Biểu thức | Ý nghĩa |
| --- | --- |
| `CAST(NULL AS address_t)` hoặc biến object chưa khởi tạo | **Atomically null object**: cả object chưa có giá trị |
| `address_t(NULL, NULL)` | Một **object tồn tại**, nhưng cả hai attribute đều là `NULL` |
| `address_t('42 Nguyen Hue', NULL)` | Một object tồn tại, attribute `CITY` là `NULL` |

Ví dụ trong PL/SQL:

```sql
SET SERVEROUTPUT ON

DECLARE
  l_not_initialized address_t;
  l_empty_address   address_t := address_t(NULL, NULL);
BEGIN
  IF l_not_initialized IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('Object 1 is atomically NULL');
  END IF;

  IF l_empty_address IS NOT NULL THEN
    DBMS_OUTPUT.PUT_LINE('Object 2 exists, attributes can be NULL');
  END IF;
END;
/
```

Với object null toàn phần, không nên cố gán trực tiếp vào `l_not_initialized.street` như thể object đã tồn tại. Trước hết khởi tạo object bằng constructor. Phân biệt **object null** với **attribute null** đặc biệt quan trọng khi thiết kế dữ liệu nullable và xử lý dữ liệu từ Java/JDBC.

## 5. Member method và type body

Object type không chỉ giữ dữ liệu; nó có thể đóng gói thao tác sử dụng các attribute. Trong Oracle, **type specification** khai báo method, còn **type body** chứa triển khai PL/SQL của method cần body.

Ví dụ một item có giá gốc và tính giá sau thuế:

```sql
CREATE TYPE price_item_t AS OBJECT (
    sku        VARCHAR2(30 CHAR),
    net_amount NUMBER(12, 2),

    MEMBER FUNCTION gross_amount(p_tax_percent NUMBER)
      RETURN NUMBER
);
/

CREATE TYPE BODY price_item_t AS
  MEMBER FUNCTION gross_amount(p_tax_percent NUMBER)
    RETURN NUMBER
  IS
  BEGIN
    RETURN ROUND(SELF.net_amount * (1 + p_tax_percent / 100), 2);
  END gross_amount;
END;
/
```

`SELF` đại diện object instance đang gọi member method. Trong method này, `SELF.net_amount` là attribute của giá trị hiện tại. Mọi phép tính vẫn phải tuân thủ quy tắc `NULL` của SQL/PLSQL: `net_amount = NULL` làm kết quả phép nhân tương ứng là `NULL`.

Sử dụng trong PL/SQL:

```sql
SET SERVEROUTPUT ON

DECLARE
  l_item price_item_t := price_item_t('BK-001', 100);
BEGIN
  DBMS_OUTPUT.PUT_LINE('Net amount  : ' || l_item.net_amount);
  DBMS_OUTPUT.PUT_LINE('Gross amount: ' || l_item.gross_amount(10));
  -- Gross amount: 110
END;
/
```

Hoặc lưu trong object column và gọi method qua SQL:

```sql
CREATE TABLE price_quotes (
    quote_id NUMBER PRIMARY KEY,
    item     price_item_t
);

INSERT INTO price_quotes (quote_id, item)
VALUES (1, price_item_t('BK-001', 100));

SELECT q.quote_id,
       q.item.sku AS sku,
       q.item.net_amount AS net_amount,
       q.item.gross_amount(10) AS gross_amount
FROM   price_quotes q;
```

### 5.1. Member, static, constructor và so sánh

| Thành phần | Cách hiểu | Tình huống |
| --- | --- | --- |
| **Attribute** | Trường dữ liệu của object | `sku`, `net_amount` |
| **Member method** | Hàm/thủ tục gọi trên một object, có `SELF` | `item.gross_amount(10)` |
| **Static method** | Method thuộc kiểu, không cần một instance `SELF` | Factory/helper logic định nghĩa trong type |
| **Constructor method** | Tạo object instance; có constructor hệ thống và có thể định nghĩa constructor tùy chỉnh | `price_item_t('BK-001',100)` |
| **MAP method** | Map object thành một giá trị scalar để so sánh, sắp xếp theo quy tắc | Sắp xếp phiên bản/độ ưu tiên theo một thuộc tính |
| **ORDER method** | So sánh hai object cùng kiểu qua logic do người dùng định nghĩa | Thứ tự nghiệp vụ phức tạp |

Oracle có quy tắc riêng khi định nghĩa `MAP` hoặc `ORDER` method; không khai báo cả hai cho cùng object type. Không mặc định rằng `ORDER BY object_column` hoạt động như sắp xếp chuỗi JSON nếu chưa thiết kế phương thức so sánh phù hợp.

### 5.2. Object method khác một function package thông thường ở đâu?

Với một function trong package, dữ liệu cần truyền vào bằng tham số hoặc query. Với member method, dữ liệu attribute nằm trong object hiện tại và được truy cập qua `SELF`. Tuy nhiên, member method chạy trong engine Oracle, chịu quyền thực thi, dependency và các quy tắc PL/SQL/SQL tương tự các chương trình lưu trong database. Method có side effect, sử dụng SQL hoặc exception sẽ ảnh hưởng tính dự đoán và hiệu năng khi gọi trên rất nhiều row.

## 6. Object table: hàng của bảng chính là object

Ngoài **object column** trong bảng quan hệ thông thường, Oracle hỗ trợ **object table** được khai báo `OF <object_type>`; mỗi hàng của bảng biểu diễn một object của kiểu đó.

```sql
-- Đây là một kiểu table khác với customer_contacts(address address_t).
CREATE TABLE address_objects OF address_t;

INSERT INTO address_objects
VALUES (address_t('10 Le Loi', 'Ho Chi Minh City'));

SELECT a.street, a.city
FROM   address_objects a;
```

Một object table có identity và khả năng dùng **object identifier (OID)**/`REF` để tham chiếu object giữa các bảng khi thiết kế object-relational. Một relational table chứa object column có semantics khác. Không nên chọn object table chỉ vì cú pháp gọn: cần cân nhắc `REF`, constraint, khóa nghiệp vụ, công cụ ORM và cách truy vấn thực tế.

### 6.1. `REF`, `DEREF` và trade-off

Ở mô hình object-relational, `REF` biểu diễn tham chiếu đến object row thuộc object table; `DEREF` đọc object được tham chiếu. Oracle có quy định về phạm vi tham chiếu (`SCOPE`), quyền và tình trạng **dangling REF** nếu object đích không còn hợp lệ.

```text
Object table: CUSTOMERS_OBJECTS
  row customer #10  ◄───────────── REF trong một object khác
            │
            └── DEREF → đọc object customer
```

Đối với quan hệ đơn hàng → khách hàng đơn giản, **foreign key trên các cột NUMBER/VARCHAR2** thường dễ dùng với SQL, ORM và BI hơn. `REF` phù hợp khi ứng dụng thực sự tận dụng model object-relational và đã có chiến lược xử lý identity/vòng đời object.

## 7. Inheritance và polymorphism của object type

Oracle hỗ trợ **type hierarchy**. Type gốc được khai báo `NOT FINAL` thì có thể tạo subtype kế thừa attribute/method; subtype có thêm attribute/method và có thể override method khi quy định cho phép.

Ví dụ đơn giản:

```sql
CREATE TYPE party_t AS OBJECT (
    party_id NUMBER
) NOT FINAL;
/

CREATE TYPE person_t UNDER party_t (
    full_name VARCHAR2(100 CHAR)
);
/
```

`PERSON_T` kế thừa `PARTY_ID` của `PARTY_T` rồi bổ sung `FULL_NAME`. Type hierarchy có thể ảnh hưởng **substitutability** của object column/object table, type checking và thực thi method. Oracle có cú pháp như `IS OF (type)` và `TREAT` để kiểm tra/diễn giải subtype trong SQL.

Phần này nên được dùng có chủ đích. Nếu nghiệp vụ chỉ cần hai bảng với một khóa ngoại, inheritance của UDT không nhất thiết giúp truy vấn hoặc migration đơn giản hơn. Ngoài ra, thay đổi type cha có thể tác động nhiều subtype và bảng phụ thuộc.

## 8. Collection type: một giá trị có nhiều phần tử

Một **collection** là giá trị chứa nhiều element. Các element thuộc cùng kiểu, có thể là scalar như `NUMBER`, `VARCHAR2` hoặc object type đã tạo. Oracle hỗ trợ ba họ collection phổ biến:

```text
Nested table                        VARRAY                             Associative array
────────────                        ──────                             ─────────────────
value = ['A','B','C']                value = ['A','B','C']               map['A'] = 5
không giới hạn phần tử khai báo       giới hạn tối đa khi CREATE TYPE     map['B'] = 8
có thể thưa trong PL/SQL            có thứ tự và thường dense          khóa INTEGER/VARCHAR2
SQL schema type có thể lưu cột       SQL schema type có thể lưu cột     PL/SQL runtime collection
```

**“Mảng” không phải một từ đủ chính xác:** dùng nested table, VARRAY hay associative array sẽ quyết định cách lưu, số lượng phần tử, thứ tự, phương thức thao tác và khả năng được dùng trong SQL.

| Thuộc tính | Nested table | VARRAY | Associative array |
| --- | --- | --- | --- |
| Kiểu khóa/index trong PL/SQL | Chỉ số số nguyên | Chỉ số nguyên từ 1 đến `COUNT` | `PLS_INTEGER` hoặc `VARCHAR2` |
| Giới hạn trên cố định khi khai báo | Không | **Có**, `VARRAY(n)` | Không |
| Đảm bảo vị trí/thứ tự logic trong value | Có index PL/SQL; khi lưu/query từ storage table **không dựa vào thứ tự** | Có thứ tự phần tử logic | Duyệt theo thứ tự khóa, không theo thứ tự chèn |
| Có thể sparse sau xóa phần tử? | Có với `DELETE` | Không theo cách `DELETE(i)` | Có: khóa tùy ý có thể thiếu |
| `EXTEND`, `TRIM` | Có | Có, trong giới hạn `LIMIT` | Không |
| `DELETE(i)` | Có | Không | Có |
| Là SQL column persistent? | Có nếu là schema type | Có nếu là schema type | **Không** |
| `TABLE()` trong SQL | Có với SQL collection type | Có với SQL collection type | Hỗ trợ một số thao tác PL/SQL→SQL với giới hạn, không phải schema column type |

## 9. Nested table: tập phần tử có độ dài biến đổi

### 9.1. Tạo SQL nested table type

Ví dụ một khách hàng có nhiều số điện thoại:

```sql
CREATE TYPE phone_numbers_t AS TABLE OF VARCHAR2(30 CHAR);
/
```

`PHONE_NUMBERS_T` là **một SQL schema type**, không phải một table có rows độc lập. Muốn lưu collection vào cột, khai báo bảng chứa cột đó và cung cấp **storage table** bằng mệnh đề `NESTED TABLE ... STORE AS`:

```sql
CREATE TABLE customer_phones (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(100 CHAR),
    phones      phone_numbers_t
)
NESTED TABLE phones STORE AS customer_phones_nt;
```

Ghi dữ liệu:

```sql
INSERT INTO customer_phones (customer_id, full_name, phones)
VALUES (
    1,
    'Nguyen An',
    phone_numbers_t('0901000001', '02830000001')
);

INSERT INTO customer_phones (customer_id, full_name, phones)
VALUES (
    2,
    'Tran Binh',
    phone_numbers_t()
);
```

`phone_numbers_t('0901000001', ...)` là constructor tạo collection có hai phần tử. `phone_numbers_t()` là collection được khởi tạo nhưng **rỗng**. `CUSTOMER_PHONES_NT` là tên **nested table storage** do Oracle quản lý để lưu phần tử; nó không phải một bảng nghiệp vụ độc lập có thể tùy tiện đổi cấu trúc.

### 9.2. Truy vấn phần tử bằng toán tử `TABLE()`

```sql
SELECT c.customer_id,
       c.full_name,
       p.COLUMN_VALUE AS phone_number
FROM   customer_phones c,
       TABLE(c.phones) p
ORDER BY c.customer_id, p.COLUMN_VALUE;
```

Kết quả minh họa:

```text
CUSTOMER_ID  FULL_NAME   PHONE_NUMBER
-----------  ----------  ------------
1            Nguyen An   02830000001
1            Nguyen An   0901000001
```

Với collection của scalar (`VARCHAR2`, `NUMBER`...), phần tử trong result có tên cột **`COLUMN_VALUE`**. Bảng của khách hàng thứ hai không sinh row trong phép mở rộng `TABLE()` vì collection rỗng. Nếu muốn giữ cả người không có số điện thoại, phải thiết kế phép outer join/aggregation theo mục tiêu truy vấn.

**Không dựa vào thứ tự phần tử khi `TABLE()` đọc nested table lưu trong database.** Oracle xử lý nested table theo mô hình tập hợp, storage có thể không duy trì thứ tự chèn. Muốn thứ tự liên hệ nghiệp vụ, lưu **ordinal/position** như một attribute của element object hoặc dùng bảng con có cột thứ tự rõ ràng.

### 9.3. Collection null và collection empty trong cột

Xét ba giá trị:

```sql
-- NULL collection: không được khởi tạo thành một collection value.
INSERT INTO customer_phones (customer_id, full_name, phones)
VALUES (3, 'Le Chi', NULL);

-- Empty collection: có collection nhưng COUNT phần tử = 0.
INSERT INTO customer_phones (customer_id, full_name, phones)
VALUES (4, 'Vo Dung', phone_numbers_t());

-- Collection có một phần tử NULL.
INSERT INTO customer_phones (customer_id, full_name, phones)
VALUES (5, 'Pham Em', phone_numbers_t(NULL));
```

Các trường hợp **khác nhau về nghĩa**: `NULL collection`, `empty collection`, và `collection chứa element NULL`.

```sql
SELECT c.customer_id,
       CASE WHEN c.phones IS NULL THEN 'NULL_COLLECTION'
            ELSE 'INITIALIZED' END AS collection_state,
       CARDINALITY(c.phones) AS element_count
FROM   customer_phones c
ORDER BY c.customer_id;
```

`CARDINALITY` trả số phần tử trong collection khi được hỗ trợ trong SQL. Với collection null, giá trị có thể là `NULL`; với collection empty, số phần tử bằng `0`; collection có một `NULL` vẫn có **một element**. Khi logic ứng dụng phân biệt “chưa cung cấp” và “không có”, nên quy định rõ hai trạng thái này trong contract dữ liệu.

### 9.4. Collection chứa object thay vì scalar

Nested table cũng có thể chứa **object type**:

```sql
CREATE TYPE order_line_t AS OBJECT (
    sku      VARCHAR2(30 CHAR),
    quantity NUMBER
);
/

CREATE TYPE order_lines_t AS TABLE OF order_line_t;
/

CREATE TABLE orders_with_lines (
    order_id NUMBER PRIMARY KEY,
    lines    order_lines_t
)
NESTED TABLE lines STORE AS orders_lines_nt;

INSERT INTO orders_with_lines (order_id, lines)
VALUES (
    100,
    order_lines_t(
      order_line_t('SKU-A', 2),
      order_line_t('SKU-B', 1)
    )
);
```

Truy vấn:

```sql
SELECT o.order_id, l.sku, l.quantity
FROM   orders_with_lines o,
       TABLE(o.lines) l
ORDER BY o.order_id, l.sku;
```

Với **collection gồm object type**, phần tử được Oracle cung cấp thuộc tính trực tiếp (`l.sku`, `l.quantity`); với collection gồm **scalar**, dùng `COLUMN_VALUE`. Phân biệt này giúp tránh lỗi khi viết câu `TABLE()`.

## 10. VARRAY: danh sách có giới hạn và thứ tự logic

### 10.1. Tạo VARRAY SQL type

Ví dụ mỗi gói dịch vụ lưu tối đa bốn mức giảm giá:

```sql
CREATE TYPE discount_levels_t AS VARRAY(4) OF NUMBER(5, 2);
/

CREATE TABLE service_plans (
    plan_id         NUMBER PRIMARY KEY,
    discount_levels discount_levels_t
);

INSERT INTO service_plans (plan_id, discount_levels)
VALUES (1, discount_levels_t(5, 10, 15));
```

Đây là VARRAY với giới hạn **4 phần tử**. Giá trị có thể chứa 0–4 phần tử, nhưng không thể `EXTEND` vượt giới hạn khi thao tác trong PL/SQL. VARRAY là collection **có thứ tự logic**, nên vị trí 1, 2, 3 có ý nghĩa đối với ứng dụng.

### 10.2. Duyệt VARRAY trong PL/SQL

```sql
SET SERVEROUTPUT ON

DECLARE
  l_levels discount_levels_t := discount_levels_t(5, 10, 15);
BEGIN
  DBMS_OUTPUT.PUT_LINE('COUNT=' || l_levels.COUNT);
  DBMS_OUTPUT.PUT_LINE('LIMIT=' || l_levels.LIMIT);

  FOR i IN 1 .. l_levels.COUNT LOOP
    DBMS_OUTPUT.PUT_LINE('Position ' || i || ': ' || l_levels(i));
  END LOOP;

  l_levels.EXTEND;
  l_levels(4) := 20;
  DBMS_OUTPUT.PUT_LINE('New COUNT=' || l_levels.COUNT);
END;
/
```

`LIMIT` của VARRAY là bound khai báo (ở đây `4`). Với nested table và associative array, `LIMIT` không cung cấp bound hữu hạn tương tự.

### 10.3. Truy vấn VARRAY bằng SQL

```sql
SELECT p.plan_id,
       d.COLUMN_VALUE AS discount_percent
FROM   service_plans p,
       TABLE(p.discount_levels) d
ORDER BY p.plan_id, d.COLUMN_VALUE;
```

Đây là cách **un-nest** phần tử thành dòng quan hệ. Dù VARRAY có thứ tự phần tử logic, **tập kết quả SQL không có thứ tự được bảo đảm nếu không có `ORDER BY`**. Nếu vị trí từng phần tử cần xuất chính xác và truy vấn bằng SQL, hãy mô hình hóa position tường minh thay vì suy luận từ `ROWNUM` của `TABLE()`.

### 10.4. VARRAY lưu trong database ra sao?

VARRAY thường được xem là một giá trị collection gắn với parent row. Oracle có những quy tắc lưu **inline** hoặc qua **LOB** cho VARRAY khi có kích cỡ/thuộc tính phù hợp, tùy element type và release. Nó **không tự động có nested storage table riêng** theo cách `NESTED TABLE ... STORE AS` của nested table.

VARRAY hữu ích cho **danh sách tương đối nhỏ, bị giới hạn rõ ràng, cần giữ trật tự**. Nếu phải thường xuyên tìm kiếm/join từng phần tử, cập nhật một phần tử riêng lẻ với tần suất cao hoặc collection có thể tăng không giới hạn, bảng con quan hệ thường dễ quản lý hơn.

## 11. Associative array: ánh xạ khóa → giá trị trong PL/SQL

**Associative array** (trước đây thường gọi là *index-by table*) là kiểu collection khai báo trong PL/SQL bằng `INDEX BY`. Nó đặc biệt hữu ích cho bảng tra cứu tạm, đếm số lần xuất hiện, cache trong một chương trình PL/SQL hoặc xử lý bulk.

### 11.1. Ví dụ map mã SKU sang số lượng

```sql
SET SERVEROUTPUT ON

DECLARE
  TYPE quantity_by_sku_t IS TABLE OF PLS_INTEGER
    INDEX BY VARCHAR2(30);

  l_quantities quantity_by_sku_t;
  l_key        VARCHAR2(30);
BEGIN
  l_quantities('SKU-A') := 5;
  l_quantities('SKU-B') := 8;
  l_quantities('SKU-C') := 2;

  DBMS_OUTPUT.PUT_LINE('SKU-B=' || l_quantities('SKU-B'));

  l_key := l_quantities.FIRST;
  WHILE l_key IS NOT NULL LOOP
    DBMS_OUTPUT.PUT_LINE(l_key || ' => ' || l_quantities(l_key));
    l_key := l_quantities.NEXT(l_key);
  END LOOP;
END;
/
```

Khóa có thể là `PLS_INTEGER` hoặc một kiểu chuỗi được hỗ trợ; không bắt buộc bắt đầu tại `1`, không cần liên tục và **không có giới hạn `VARRAY(n)`**. Thứ tự duyệt bằng `FIRST`/`NEXT` là thứ tự **key**, với khóa chuỗi chịu ảnh hưởng quy tắc so sánh/national language settings; không nên dựa vào thứ tự đã chèn.

### 11.2. Khi nào associative array không phù hợp?

- Khi muốn tạo một cột SQL `sku_quantities quantity_by_sku_t`, vì associative array **không là SQL schema collection type**.
- Khi cần SQL query/join trực tiếp dữ liệu bền vững bằng index, foreign key, constraint và statistics của bảng quan hệ.
- Khi muốn chia sẻ type contract giữa nhiều ứng dụng ngoài PL/SQL mà không có mapping/binding được hỗ trợ rõ ràng.

Nếu muốn lưu bộ dữ liệu map vào bảng, thiết kế quan hệ phổ biến là `SKU_QUANTITY(parent_id, sku, quantity)` với primary/unique key rõ ràng. Ở thời gian chạy PL/SQL, associative array vẫn có thể là cấu trúc tạm rất hiệu quả.

## 12. Các collection methods cần biết

Oracle PL/SQL cung cấp một số method chung trên collection. Chúng không hoạt động giống hệt nhau trên cả ba loại.

| Method | Ý nghĩa | Cần lưu ý |
| --- | --- | --- |
| `COUNT` | Số element đang tồn tại | Khác với `LAST` nếu nested table/associative array thưa |
| `FIRST`, `LAST` | Chỉ số/khóa đầu và cuối đang tồn tại | Collection rỗng thường trả `NULL` |
| `PRIOR(i)`, `NEXT(i)` | Khóa/index tồn tại trước hoặc sau `i` | Phù hợp khi collection có gaps |
| `EXISTS(i)` | `TRUE` nếu element ở index/key `i` tồn tại | An toàn trước khi truy cập index chưa chắc có |
| `LIMIT` | Giới hạn element của VARRAY | Với nested table/associative array trả `NULL` |
| `EXTEND` | Tăng số phần tử được cấp phát | Cho nested table/VARRAY, không cho associative array |
| `TRIM` | Bỏ một hoặc nhiều element ở cuối | Cho nested table/VARRAY, không cho associative array |
| `DELETE`, `DELETE(i)` | Xóa element hoặc toàn collection | Cho nested table/associative array; VARRAY không hỗ trợ `DELETE` |

### 12.1. `COUNT` khác `LAST` với nested table thưa

```sql
SET SERVEROUTPUT ON

DECLARE
  TYPE tags_t IS TABLE OF VARCHAR2(30);
  l_tags tags_t := tags_t('db', 'sql', 'plsql');
  l_idx PLS_INTEGER;
BEGIN
  l_tags.DELETE(2); -- Bỏ element 2 nhưng giữ index 1 và 3.

  DBMS_OUTPUT.PUT_LINE('COUNT=' || l_tags.COUNT); -- 2
  DBMS_OUTPUT.PUT_LINE('LAST='  || l_tags.LAST);  -- 3

  l_idx := l_tags.FIRST;
  WHILE l_idx IS NOT NULL LOOP
    DBMS_OUTPUT.PUT_LINE(l_idx || ': ' || l_tags(l_idx));
    l_idx := l_tags.NEXT(l_idx);
  END LOOP;
END;
/
```

Sau `DELETE(2)`, `COUNT=2` nhưng `LAST=3`. Vòng lặp `FOR i IN 1 .. l_tags.COUNT` **không an toàn cho nested table thưa**, vì index `2` không còn. `FIRST` + `NEXT` là cách duyệt có thể xử lý gaps.

### 12.2. `EXTEND` và `TRIM` không giống `DELETE`

`EXTEND` thêm phần tử ở cuối collection theo cơ chế của nested table/VARRAY. `TRIM` bỏ phần tử cuối. Trong nested table đã xóa các phần tử bằng `DELETE`, việc trộn `DELETE`, `EXTEND`, `TRIM` cần chú ý vì Oracle vẫn quản lý **internal size** khác số element còn tồn tại; không thể xem `TRIM` là thao tác xóa theo `LAST` của tập element đang tồn tại.

Ví dụ VARRAY dễ dự đoán:

```sql
DECLARE
  TYPE codes_t IS VARRAY(3) OF VARCHAR2(20);
  l_codes codes_t := codes_t('A');
BEGIN
  l_codes.EXTEND;
  l_codes(2) := 'B';
  l_codes.TRIM;
  -- Còn lại 'A'.
END;
/
```

Một VARRAY có giới hạn 3 sẽ báo lỗi nếu chương trình cố vượt giới hạn. Không giả định Oracle tự tăng bound của type giống `ArrayList` trong Java.

## 13. Collection `NULL`, rỗng và chưa khởi tạo

Với nested table và VARRAY, biến chỉ khai báo kiểu nhưng **chưa gán constructor** là collection **atomically NULL**. Gọi `COUNT`, `EXTEND` hoặc truy cập element trước khi khởi tạo thường gây `COLLECTION_IS_NULL` (`ORA-06531`).

```sql
SET SERVEROUTPUT ON

DECLARE
  TYPE code_list_t IS TABLE OF VARCHAR2(20);

  l_null  code_list_t;                 -- atomically NULL
  l_empty code_list_t := code_list_t(); -- initialized, 0 elements
BEGIN
  IF l_null IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('l_null is NULL');
  END IF;

  DBMS_OUTPUT.PUT_LINE('l_empty.COUNT=' || l_empty.COUNT);
  l_empty.EXTEND;
  l_empty(1) := 'A';
  DBMS_OUTPUT.PUT_LINE('l_empty.COUNT=' || l_empty.COUNT);
END;
/
```

Trái lại, **associative array** khi được khai báo sẽ bắt đầu ở trạng thái **empty collection** và không cần constructor theo cách nested table/VARRAY. Nhưng truy cập một khóa chưa tồn tại có thể dẫn đến exception, nên dùng `EXISTS(key)` hoặc các method duyệt thích hợp.

| Trường hợp | `COUNT` | Truy cập element |
| --- | --- | --- |
| Nested table/varray chưa khởi tạo | Gây `COLLECTION_IS_NULL` | Không truy cập được |
| Nested table/varray vừa gọi constructor rỗng | `0` | Chưa có element; cần `EXTEND` hoặc gán phù hợp |
| Nested table thưa sau `DELETE(i)` | Số element còn lại | Index đã xóa không còn hợp lệ để đọc |
| Associative array mới khai báo | `0` | Chỉ truy cập khóa đã gán |

Các lỗi khác có thể gặp gồm `SUBSCRIPT_BEYOND_COUNT`, `SUBSCRIPT_OUTSIDE_LIMIT` hoặc `NO_DATA_FOUND` tùy thao tác. Nguyên nhân thực tế phải đối chiếu **kiểu collection, trạng thái khởi tạo và index** trước khi xử lý exception.

## 14. SQL collection và PL/SQL collection không phải lúc nào tương thích

So sánh hai đoạn:

```sql
-- SQL schema type, có thể dùng làm kiểu cột SQL.
CREATE TYPE number_list_sql_t AS TABLE OF NUMBER;
/
```

```sql
-- PL/SQL local type, chỉ tồn tại trong scope của block.
DECLARE
  TYPE number_list_local_t IS TABLE OF NUMBER;
  l_values number_list_local_t := number_list_local_t(10, 20);
BEGIN
  DBMS_OUTPUT.PUT_LINE(l_values.COUNT);
END;
/
```

Mặc dù hai type đều chứa `NUMBER`, **type identity và phạm vi khai báo khác nhau**. Không thể dùng `NUMBER_LIST_LOCAL_T` từ anonymous block trong `CREATE TABLE` hoặc xem tự động là `NUMBER_LIST_SQL_T` khi gọi một procedure nhận schema type.

### 14.1. `TABLE()` làm cầu nối SQL collection → rows

Với SQL nested table hoặc VARRAY type:

```sql
SELECT v.COLUMN_VALUE AS n
FROM   TABLE(number_list_sql_t(10, 20, 30)) v
ORDER BY v.COLUMN_VALUE;
```

Kết quả tạo ba rows với giá trị `10`, `20`, `30`. Không có table vật lý `NUMBER_LIST_SQL_T` được tạo chỉ vì dùng `TABLE()`: đó là constructor của một giá trị collection và phép mở rộng collection trong truy vấn.

### 14.2. `BULK COLLECT` và `FORALL`

Collection đặc biệt hữu ích trong PL/SQL khi xử lý nhiều row:

```sql
DECLARE
  TYPE id_list_t IS TABLE OF NUMBER;
  l_ids id_list_t;
BEGIN
  SELECT customer_id
  BULK COLLECT INTO l_ids
  FROM   customer_contacts
  WHERE  customer_id <= 100;

  DBMS_OUTPUT.PUT_LINE('Collected rows: ' || l_ids.COUNT);
END;
/
```

`BULK COLLECT` lấy nhiều row vào collection để giảm lượt chuyển ngữ cảnh giữa SQL và PL/SQL. `FORALL` có thể thực hiện DML hàng loạt bằng collection indices khi có thiết kế phù hợp. Với collection thưa, cú pháp như `INDICES OF` hoặc `VALUES OF` giúp tránh giả định mọi index liên tục.

**Không biến `BULK COLLECT` không giới hạn thành phương án mặc định** cho hàng triệu row: dữ liệu nằm trong bộ nhớ PGA của session, có thể gây áp lực bộ nhớ. Với dữ liệu lớn, dùng `FETCH ... BULK COLLECT ... LIMIT n` hoặc phân trang xử lý tùy yêu cầu và thiết kế transaction.

## 15. Những giới hạn khi dùng `TABLE()` và ngữ nghĩa SQL

Khi viết `FROM table_name t, TABLE(t.collection_column) x`, Oracle mở rộng phần tử collection thành rowset. Một số đặc điểm cần nhớ:

1. **Collection null/rỗng** không phát ra element row; phép join thông thường có thể làm mất parent row.
2. **Phần tử scalar** hiện dưới tên `COLUMN_VALUE`; phần tử object có thể truy cập attribute bằng alias.
3. **SQL trả tập quan hệ**: không mặc định thứ tự element được bảo toàn trong result nếu không có `ORDER BY`.
4. **Collection object type/element type** phải có quyền và khai báo phù hợp; việc gọi `TABLE()` từ client có thể cần SQL schema type hoặc một trường hợp PL/SQL integration được Oracle hỗ trợ.
5. **Predicate/aggregation trên phần tử** cần xét index, số element, khả năng pushdown và execution plan thực tế.

Ví dụ đếm số điện thoại:

```sql
SELECT c.customer_id,
       CARDINALITY(c.phones) AS phone_count
FROM   customer_phones c
ORDER BY c.customer_id;
```

Khi cần join và lọc thường xuyên theo `phone_number`, một bảng quan hệ:

```text
CUSTOMER_PHONE_ROWS(
  CUSTOMER_ID   FK → CUSTOMERS,
  PHONE_NUMBER  VARCHAR2(...),
  POSITION_NO   NUMBER,
  PRIMARY KEY (CUSTOMER_ID, PHONE_NUMBER)
)
```

có thể thuận lợi hơn để đặt constraint, index và query trực tiếp. **Có thể dùng collection trong cột** không đồng nghĩa nên dùng nó cho mọi quan hệ một-nhiều.

## 16. Khi nào nên chọn object type, nested table, VARRAY hay bảng quan hệ?

| Nhu cầu | Lựa chọn nên xem xét | Lý do |
| --- | --- | --- |
| Giá trị nghiệp vụ có nhiều trường, logic chung và được xử lý trong SQL/PLSQL | **Object type** | Có type identity, attribute và method |
| Cột chứa một cấu trúc nhỏ như địa chỉ, điểm đo, tọa độ | **Object column** | Mô tả giá trị lồng nhau có tên rõ ràng |
| Danh sách nhỏ, có số lượng tối đa và thứ tự logic | **VARRAY** | Có `LIMIT`, giữ thứ tự trong collection value |
| Danh sách element biến độ dài, có thể lưu như collection column | **Nested table** | Có thể lưu qua storage table và mở rộng bằng `TABLE()` |
| Dictionary/cache tạm trong một PL/SQL procedure | **Associative array** | Truy cập theo key, không cần storage schema object |
| Tập rows quan hệ cần FK, unique index, join và cập nhật độc lập | **Bảng con quan hệ** | Dễ truy vấn, áp constraint và tối ưu SQL |
| Trường có cấu trúc linh hoạt, tích hợp service JSON | **JSON** (nếu release hỗ trợ phù hợp) | Có operator/function và mô hình tài liệu riêng; không giống object UDT |
| Chỉ nhóm vài biến cục bộ trong PL/SQL | **RECORD** | Đơn giản, không thêm dependency schema type |

### 16.1. Ví dụ lựa chọn thiết kế đơn hàng

Giả sử hệ thống cần lưu `ORDERS` và các dòng `ORDER_ITEMS`:

**Cách A — Nested table của object:**

```text
ORDERS(order_id, lines ORDER_LINES_T)
  lines = [ORDER_LINE_T('A',2), ORDER_LINE_T('B',1)]
```

Phù hợp khi ứng dụng thường thao tác đơn hàng như một aggregate, số line hợp lý, ít cần index độc lập trên line và chấp nhận phụ thuộc vào SQL UDT.

**Cách B — Hai bảng quan hệ:**

```text
ORDERS(order_id PK, customer_id, created_at, ...)
ORDER_ITEMS(order_id FK, line_no, sku, quantity,
            PRIMARY KEY(order_id, line_no))
```

Phù hợp khi cần query theo `SKU`, phân trang line items, join với inventory, index theo tình trạng từng line, batch update và tích hợp ORM thông dụng. Phần lớn OLTP quan hệ truyền thống thích hợp với cách B hơn nếu không có yêu cầu object-relational cụ thể.

### 16.2. Không đồng nhất UDT với JSON

Object type là **schema-defined strong type**: cấu trúc attribute khai báo khi `CREATE TYPE`, thay đổi cần quản lý dependency. JSON thiên về cấu trúc document, schema có thể được kiểm soát theo cơ chế khác; Oracle 19c chủ yếu lưu JSON trong kiểu như `VARCHAR2`, `CLOB` hoặc `BLOB` có ràng buộc JSON, còn Oracle release mới có các khả năng JSON native khác. Một cột JSON không biến thành một object type chỉ vì chứa object `{ "sku": "A" }`.

## 17. Tác động của UDT lên schema, phụ thuộc và triển khai

### 17.1. Type là schema object có tên và owner

Khi tạo `APP.PRICE_ITEM_T`, Oracle lưu định nghĩa type trong data dictionary. Package, table, view, PL/SQL code hoặc một type khác có thể **phụ thuộc** vào nó. Nếu người dùng khác cần dùng type theo quyền của họ, DBA có thể cấp quyền như:

```sql
-- Chỉ là minh họa thay đổi quyền trong môi trường quản trị.
GRANT EXECUTE ON price_item_t TO reporting_user;
```

`EXECUTE` trên type cho phép dùng type theo phạm vi quyền được cấp, nhưng **không tự cấp quyền SELECT/INSERT/UPDATE** vào bảng chứa type đó. Với CDB/PDB, cần xác định đúng container và common/local grant nếu liên quan.

### 17.2. Thay đổi type là thay đổi contract

Giả sử một type đang được dùng trong cột của một triệu rows:

```text
PRICE_ITEM_T(sku, net_amount)
        │
        ├── PRICE_QUOTES.ITEM column
        ├── PACKAGE_ORDER_API parameter
        └── VIEW_ORDER_REPORT logic
```

Thêm attribute, đổi kiểu attribute hoặc xóa method có thể ảnh hưởng **lưu trữ dữ liệu object đã tồn tại, dependent objects, giao diện PL/SQL, ứng dụng JDBC và kế hoạch nâng cấp**. Oracle hỗ trợ **type evolution** qua `ALTER TYPE` với các quy tắc về `CASCADE`, invalidation, upgrade of dependent tables và các giới hạn khác. Không dùng `CREATE OR REPLACE TYPE` bừa bãi như một thao tác sửa file text độc lập.

Ví dụ lệnh cần DBA đánh giá, **không chạy như một bài lab tùy tiện**:

```sql
-- Minh họa ý tưởng type evolution, không phải migration được phê duyệt.
ALTER TYPE price_item_t
  ADD ATTRIBUTE (currency_code VARCHAR2(3 CHAR)) CASCADE;
```

Trong thực tế, đổi constructor từ hai thuộc tính sang ba thuộc tính có thể khiến code cũ `price_item_t('A',100)` không còn hợp lệ nếu không có constructor tương thích. DBA cần kiểm kê dependency, viết migration/rollback, test dữ liệu cũ và cập nhật code client trước khi nâng cấp.

### 17.3. Dùng metadata để kiểm kê UDT

Các câu lệnh sau chỉ đọc metadata, thực hiện trong schema lab hoặc với quyền dictionary thích hợp:

```sql
SELECT type_name, typecode
FROM   user_types
ORDER BY type_name;

SELECT type_name, attr_no, attr_name, attr_type_name
FROM   user_type_attrs
ORDER BY type_name, attr_no;

SELECT type_name, coll_type, upper_bound, elem_type_name
FROM   user_coll_types
ORDER BY type_name;

SELECT object_name, object_type, status
FROM   user_objects
WHERE  object_type IN ('TYPE', 'TYPE BODY')
ORDER BY object_name, object_type;
```

Một số collection type có thông tin `UPPER_BOUND` chỉ có ý nghĩa cho VARRAY; nested table không có bound hữu hạn như VARRAY. Với type thuộc schema khác và có quyền, dùng các view `ALL_*`/`DBA_*` tương ứng. Trong CDB, luôn xác định current PDB trước khi diễn giải kết quả.

### 17.4. Xuất DDL và xem dependency

```sql
-- Cần quyền metadata phù hợp và type đang tồn tại.
SELECT DBMS_METADATA.GET_DDL('TYPE', 'PRICE_ITEM_T')
FROM   dual;

SELECT name, type, referenced_name, referenced_type
FROM   user_dependencies
WHERE  referenced_name = 'PRICE_ITEM_T'
ORDER BY name, type;
```

`DBMS_METADATA` giúp xuất định nghĩa type, nhưng một script triển khai schema còn cần **type body, dependent type, bảng, index, constraint, quyền và thứ tự tạo object**. Không xem DDL của type specification đơn lẻ là bản sao lưu đầy đủ một ứng dụng.

## 18. Ứng dụng Java/JDBC và ORM: lựa chọn integration có chủ đích

Khi dùng Oracle SQL object type và collection type, dữ liệu có thể được ánh xạ sang những biểu diễn **STRUCT** và **ARRAY** theo JDBC/Oracle driver. Một ứng dụng Java có thể cần thêm mã tạo object mapping, xử lý Oracle type name, attribute order, JDBC connection unwrap và null handling.

```text
Oracle schema type                Java/JDBC layer
──────────────────                ───────────────
APP.ADDRESS_T                     STRUCT-like value / custom mapping
APP.PHONE_NUMBERS_T               ARRAY-like value / driver support
NUMBER/VARCHAR2 columns           JDBC scalar types / ORM mapping thường đơn giản hơn
```

Không giả định JPA/Hibernate tự ánh xạ Oracle nested table, VARRAY hoặc object table như `@OneToMany` chỉ bằng một annotation phổ thông. Một số framework hỗ trợ user type/custom converter, nhưng cách làm phụ thuộc **driver version, Hibernate version, DB release và dialect**. Kiểm tra round-trip insert/read, SQL null vs empty collection, type schema qualification và migration trên môi trường gần production trước khi chọn UDT cho API ứng dụng.

### 18.1. API contract có thể bị lệch khi type đổi

Khi `PRICE_ITEM_T` bổ sung `currency_code`, thứ tự attribute của constructor và representation JDBC có thể thay đổi. Nếu application vẫn tạo object theo hai attribute cũ, có thể lỗi runtime. Do đó, review thay đổi type cùng nhóm Java/backend, không chỉ DBA.

### 18.2. Những câu hỏi cần trả lời trước khi dùng UDT trong một service Java

1. Có dùng UDT trong **column persistent**, trong parameter của stored procedure, hay chỉ để **truyền batch tạm**?
2. Driver/JPA stack có hỗ trợ mapping type theo cách được kiểm thử không?
3. Có cần query/index từng phần tử collection thường xuyên không?
4. Type evolution sẽ được quản lý bằng Flyway/Liquibase/DDL migration nào?
5. Có xử lý được `NULL object`, `empty collection`, `element NULL` và schema-qualified type names không?

Nếu phần lớn code dùng relational ORM và collection chỉ để mô tả quan hệ một-nhiều, bảng con với khóa ngoại thường đơn giản hơn để duy trì.

## 19. Tối ưu và hạn chế vận hành

### 19.1. Vấn đề index và truy vấn

- Attribute trong object column có thể tham gia SQL predicate, nhưng cách tạo index và thống kê phải được đánh giá trên query workload cụ thể.
- Nested table storage có thể cần thiết kế lưu trữ/index/constraint thích hợp; không có bảo đảm mọi filter trên element đều hiệu quả như cột khóa ngoại được index.
- VARRAY thích hợp cho collection nhỏ; việc tìm kiếm/ghi phần tử của một giá trị lớn có thể tạo chi phí hơn bảng con quan hệ.
- Type methods chạy trên nhiều rows có thể gây **CPU/SQL context overhead** hoặc phát sinh truy vấn phụ; không dùng method tốn kém trong một phép scan lớn nếu chưa đo thực tế.

### 19.2. Bảo trì, backup và migration

Object values và collection columns nằm trong phạm vi backup/restore và data dictionary tương ứng của Oracle Database. Nhưng chuyển sang DBMS khác hoặc công cụ ETL có thể cần bước chuyển đổi UDT sang các bảng/cột quan hệ, JSON hoặc cấu trúc trung gian.

Khi export schema bằng Data Pump/`DBMS_METADATA`, kiểm tra **thứ tự tạo types**, quyền `EXECUTE`, type bodies, nested storage metadata, dependent tables và phiên bản target DB. Không bắt đầu bằng việc chạy các `CREATE TABLE` phụ thuộc vào một type chưa được tạo.

### 19.3. Quy tắc thiết kế dữ liệu

```text
Nếu cần:
  Strongly typed structured value + methods trong DB
      └─ Cân nhắc OBJECT TYPE.

  Danh sách nhỏ có giới hạn và thứ tự
      └─ Cân nhắc VARRAY.

  Collection biến độ dài trong một column, SQL unnest cần thiết
      └─ Cân nhắc SQL NESTED TABLE.

  Map/cache tạm trong procedure
      └─ Cân nhắc PL/SQL ASSOCIATIVE ARRAY.

  Quan hệ 1:N với FK/index/join và lifecycle độc lập
      └─ Ưu tiên BẢNG CON QUAN HỆ.
```

## 20. Bài thực hành tổng hợp trong schema lab

> Phần sau tạo và xóa object thật, chỉ dùng schema lab do bạn sở hữu. Các lệnh có implicit commit; không chạy trong schema ứng dụng production. Nếu đã chạy ví dụ các phần trên, có thể tái sử dụng type/table tương ứng và bỏ qua lệnh tạo trùng.

### Bước 1 — Tạo object type, nested table và VARRAY

```sql
CREATE TYPE lab_line_t AS OBJECT (
    sku VARCHAR2(30 CHAR),
    qty NUMBER
);
/

CREATE TYPE lab_lines_t AS TABLE OF lab_line_t;
/

CREATE TYPE lab_scores_t AS VARRAY(3) OF NUMBER;
/
```

### Bước 2 — Tạo bảng có cả nested table và VARRAY column

```sql
CREATE TABLE lab_orders_udt (
    order_id NUMBER PRIMARY KEY,
    lines    lab_lines_t,
    scores   lab_scores_t
)
NESTED TABLE lines STORE AS lab_orders_lines_nt;
```

### Bước 3 — Tạo dữ liệu bằng constructors

```sql
INSERT INTO lab_orders_udt (order_id, lines, scores)
VALUES (
    1,
    lab_lines_t(lab_line_t('SKU-A', 2), lab_line_t('SKU-B', 1)),
    lab_scores_t(10, 20, 30)
);

INSERT INTO lab_orders_udt (order_id, lines, scores)
VALUES (2, lab_lines_t(), lab_scores_t());

COMMIT;
```

### Bước 4 — Đọc phần tử và kiểm kê collection

```sql
SELECT o.order_id, l.sku, l.qty
FROM   lab_orders_udt o,
       TABLE(o.lines) l
ORDER BY o.order_id, l.sku;

SELECT o.order_id,
       CARDINALITY(o.lines) AS line_count,
       CARDINALITY(o.scores) AS score_count
FROM   lab_orders_udt o
ORDER BY o.order_id;
```

Quan sát `order_id=2` có collection rỗng, nên phép `TABLE(o.lines)` không phát sinh row cho đơn đó nhưng `CARDINALITY` trả `0`.

### Bước 5 — Xem metadata và DDL thật

```sql
SELECT type_name, typecode
FROM   user_types
WHERE  type_name LIKE 'LAB_%'
ORDER BY type_name;

SELECT type_name, coll_type, upper_bound
FROM   user_coll_types
WHERE  type_name LIKE 'LAB_%'
ORDER BY type_name;

SELECT DBMS_METADATA.GET_DDL('TABLE', 'LAB_ORDERS_UDT')
FROM   dual;
```

Trong SQL*Plus/SQLcl, thiết lập `SET LONG` đủ lớn để xem DDL đầy đủ. Kiểm tra xem `NESTED TABLE ... STORE AS` xuất hiện trong DDL của bảng theo transform profile nào. Nếu client đang cắt CLOB, không kết luận DDL đã thiếu storage clause.

### Bước 6 — Dọn lab nếu cần

Các thao tác `DROP` có tác động xóa không thể hoàn tác bằng `ROLLBACK`, nên chỉ dùng khi xác nhận đúng các object do bài lab tạo:

```sql
DROP TABLE lab_orders_udt PURGE;
DROP TYPE lab_scores_t;
DROP TYPE lab_lines_t;
DROP TYPE lab_line_t;
```

Thứ tự dọn **bảng trước type**, và type chứa object trước type element phản ánh dependency. Không xóa bằng `FORCE` khi có đối tượng khác đang phụ thuộc mà chưa kiểm kê.

## 21. Lỗi hay gặp và cách suy luận

| Hiện tượng / lỗi | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| `PLS-00306` khi gọi constructor | Sai số lượng/kiểu đối số, type đã đổi attribute | Xem `USER_TYPE_ATTRS`, constructor signature |
| `ORA-06531: Reference to uninitialized collection` | Nested table/VARRAY chưa gọi constructor | Khởi tạo `my_type()` trước `COUNT`/`EXTEND` |
| `ORA-06532` / `ORA-06533` khi truy cập collection | Chỉ số ngoài giới hạn hoặc phần tử không tồn tại | Kiểm tra `COUNT`, `LIMIT`, `FIRST`, `NEXT`, `EXISTS` |
| `NO_DATA_FOUND` khi đọc associative array | Khóa chưa có phần tử tương ứng | `IF l_map.EXISTS(key) THEN ...` |
| `ORA-00902: invalid datatype` | Dùng PL/SQL-only type hoặc loại type không hợp lệ trong SQL DDL | Tạo SQL schema type bằng `CREATE TYPE` nếu cần cột SQL |
| `ORA-02303` khi thay/drop type | Type còn dependent table/type khác | Kiểm kê dependency và dùng migration/evolution phù hợp |
| Query `TABLE()` không thấy parent row có collection rỗng | Phép mở rộng collection không sinh element | Dùng phép outer join hoặc aggregate nếu cần giữ parent |
| Kết quả nested table khác thứ tự insert | Không có trật tự được bảo đảm của rows trong SQL/nested storage | Lưu `position_no` và `ORDER BY` rõ ràng |
| Java/JDBC không map được UDT | Thiếu schema type mapping, driver support hoặc object attribute mismatch | Kiểm tra Oracle JDBC STRUCT/ARRAY, type name và constructor |
| Table tạo được nhưng app không gọi được constructor | Thiếu `EXECUTE` trên type hoặc sai schema/PDB | Kiểm tra grants và current container |
| `CREATE OR REPLACE TYPE` làm package invalid | Dependent object không tương thích với type mới | Kiểm kê dependency, migration có version, recompile và kiểm tra |

Lỗi có thể khác nhau theo code path và version; bảng trên dùng để **định vị nguyên nhân**, không thay thế việc đọc thông báo đầy đủ và stack trace.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** `CREATE TYPE address_t AS OBJECT (...)` khác `TYPE address_rec IS RECORD (...)` trong PL/SQL như thế nào về phạm vi và khả năng dùng trong SQL?

**Câu 2.** Khi `l_phones phone_numbers_t;` chưa được khởi tạo, lời gọi `l_phones.COUNT` trả `0` hay lỗi?

**Câu 3.** `phone_numbers_t()` và `phone_numbers_t(NULL)` có giống nhau không?

**Câu 4.** Vì sao sau `l_nested.DELETE(2)`, một nested table có `COUNT=2`, `LAST=3`? Nên duyệt bằng cách nào?

**Câu 5.** Một VARRAY khai báo `VARRAY(4)` có thể có năm phần tử không? Có bảo đảm kết quả của `SELECT ... FROM TABLE(varray_column)` luôn theo thứ tự chèn không?

**Câu 6.** Một associative array `INDEX BY VARCHAR2(30)` có dùng trực tiếp làm kiểu cột table không? Vì sao?

**Câu 7.** Truy vấn collection gồm `VARCHAR2` và collection gồm object type trong `TABLE()` khác nhau ở cú pháp lấy phần tử thế nào?

**Câu 8.** Một schema có `ORDER_LINES_T` phụ thuộc `ORDER_LINE_T`. Muốn drop hai types, cần xem dependency theo thứ tự nào?

**Câu 9.** Nếu muốn tìm kiếm từng số điện thoại của hàng triệu khách hàng bằng index và bảo đảm unique theo customer, nên cân nhắc mô hình nào?

**Câu 10.** `PRICE_ITEM_T` được thêm một attribute. Cần kiểm tra gì ngoài riêng câu `ALTER TYPE`?

<details>
<summary>Gợi ý đáp án</summary>

1. `ADDRESS_T` là SQL schema object type, có thể dùng làm kiểu cột SQL; PL/SQL `RECORD` local/package chỉ dùng trong phạm vi PL/SQL được hỗ trợ.
2. Gây `COLLECTION_IS_NULL`/`ORA-06531` khi chưa constructor, không mặc định là `0`.
3. Khác: constructor rỗng tạo collection **0 phần tử**; constructor với `NULL` tạo collection **1 phần tử có giá trị NULL**.
4. Nested table sau `DELETE` có thể thưa. `COUNT` đếm phần tử còn tồn tại; `LAST` là index lớn nhất còn tồn tại. Duyệt bằng `FIRST` và `NEXT`.
5. Không vượt 4; SQL rowset không có thứ tự được bảo đảm nếu thiếu `ORDER BY` tường minh, dù VARRAY có thứ tự logic.
6. Không. Associative array là kiểu PL/SQL runtime, không phải SQL schema type cho cột persistent.
7. Scalar element dùng `COLUMN_VALUE`; object element có thể dùng alias.attribute như `l.sku`.
8. Drop type collection phụ thuộc trước (`ORDER_LINES_T`), rồi element type (`ORDER_LINE_T`), sau khi bỏ các bảng/objects dùng chúng.
9. Bảng con quan hệ có khóa ngoại, unique key/index thường phù hợp hơn.
10. Dependent tables/types/packages/views, constructors, data upgrade, grants, app/JDBC mappings và rollback/test migration.

</details>

## 23. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Language Reference — `CREATE TYPE`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TYPE.html): cú pháp SQL object type, nested table và VARRAY.
2. [Oracle Database 19c SQL Language Reference — `CREATE TYPE BODY`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TYPE-BODY.html): khai báo và triển khai member/static method.
3. [Oracle Database 19c Object-Relational Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/adobj/): object attributes, constructors, object tables, `REF`, inheritance và storage.
4. [Oracle Database 19c PL/SQL Language Reference — Collections and Records](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-collections-and-records.html): nested table, VARRAY, associative array, record và collection methods.
5. [Oracle Database 19c SQL Language Reference — `TABLE` collection expression](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): chuyển collection thành relational rowset và join semantics.
6. [Oracle Database 19c SQL Language Reference — `ALTER TYPE`](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TYPE.html): type evolution, dependency và upgrade behavior.
7. [Oracle Database 19c PL/SQL Language Reference — Bulk SQL and Bulk Binding](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-optimization-and-tuning.html): `BULK COLLECT`, `FORALL`, `LIMIT` và khả năng xử lý mảng.
8. [Oracle Database 19c Database Reference — Data Dictionary](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/about-static-data-dictionary-views.html): `USER_TYPES`, `USER_TYPE_ATTRS`, `USER_COLL_TYPES`, `USER_DEPENDENCIES`.
9. [Oracle Database 19c JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): làm việc với Oracle object/collection types qua JDBC và ứng dụng Java.

**Điểm cần ghi nhớ:** Oracle có **object type** cho giá trị nhiều thuộc tính và methods, **nested table/VARRAY** cho collection có thể dùng trong SQL khi là schema type, và **associative array** cho ánh xạ linh hoạt trong PL/SQL. Mọi lựa chọn cần xét **vòng đời type, thứ tự phần tử, null semantics, quyền/schema, khả năng query, dependency và công cụ ứng dụng**; một kiểu dữ liệu phức hợp chỉ nên được đưa vào schema khi lợi ích của nó lớn hơn chi phí tích hợp và bảo trì.

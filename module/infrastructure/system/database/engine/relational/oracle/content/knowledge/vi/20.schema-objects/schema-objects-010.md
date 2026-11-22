# Object type, nested table, VARRAY và quan hệ với bảng thông thường trong Oracle

## 1. Mở rộng mô hình quan hệ bằng kiểu đối tượng

Trong mô hình quan hệ thông thường, bảng được xây từ các cột scalar như `NUMBER`, `VARCHAR2`, `DATE` và các hàng. Khi dữ liệu có cấu trúc lồng nhau, ví dụ địa chỉ gồm nhiều thuộc tính, danh sách số điện thoại hoặc danh sách dòng hàng của một đơn hàng, Oracle còn cung cấp các tính năng object-relational:

- **Object type:** định nghĩa một kiểu dữ liệu có nhiều thuộc tính, có thể chứa các kiểu scalar, object type khác hoặc collection.
- **Object table:** bảng mà mỗi hàng là một instance của một object type.
- **Object column:** một cột trong bảng thông thường có kiểu object.
- **Nested table:** collection có số phần tử không được khai báo giới hạn cố định; Oracle lưu các phần tử trong storage table riêng và liên kết với hàng cha.
- **VARRAY:** collection có giới hạn số phần tử, giữ thứ tự phần tử và được lưu như một giá trị collection của hàng.

Ví dụ, một khách hàng có tên, địa chỉ và danh sách điện thoại. Có thể biểu diễn địa chỉ thành một object type, danh sách điện thoại thành VARRAY, rồi đặt cả hai trong một object type hồ sơ khách hàng:

```sql
CREATE TYPE address_t AS OBJECT (
    street       VARCHAR2(100),
    city         VARCHAR2(50),
    postal_code  VARCHAR2(20)
);
/

CREATE TYPE phone_list_t AS VARRAY(5) OF VARCHAR2(20);
/

CREATE TYPE customer_profile_t AS OBJECT (
    full_name  VARCHAR2(100),
    address    address_t,
    phones     phone_list_t
);
/
```

Sau đó có thể dùng `CUSTOMER_PROFILE_T` làm kiểu của một cột trong bảng quan hệ:

```sql
CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    profile     customer_profile_t
);
```

Bài học thuộc chương **Đối tượng schema**, tập trung vào cách định nghĩa và sử dụng object type, nested table, VARRAY, cách truy vấn collection bằng `TABLE()`, và quan hệ giữa mô hình object-relational với các bảng quan hệ thông thường. Mục tiêu là biết Oracle hỗ trợ những cấu trúc nào, dữ liệu được lưu và truy cập ra sao, cũng như chọn cấu trúc phù hợp với nghiệp vụ và ứng dụng.

## 2. Object type là gì?

Object type là một kiểu dữ liệu do người dùng định nghĩa ở cấp schema. Nó gom nhiều thuộc tính thành một giá trị có cấu trúc. Các thuộc tính có thể là:

- Kiểu scalar như `NUMBER`, `VARCHAR2`, `DATE`, `TIMESTAMP`.
- Một object type khác.
- Một kiểu collection như nested table hoặc VARRAY.
- Một số kiểu dữ liệu khác được Oracle cho phép làm thuộc tính.

Object type có thể được dùng trong cột bảng, trong object table, trong collection và trong biến PL/SQL tương thích.

### 2.1. Định nghĩa object type đơn giản

```sql
CREATE TYPE person_t AS OBJECT (
    person_id  NUMBER,
    full_name  VARCHAR2(100),
    birth_date DATE
);
/
```

`PERSON_T` mô tả một giá trị gồm ba thuộc tính. Lệnh `CREATE TYPE` tạo kiểu ở cấp schema; dấu `/` trên dòng riêng là cách gửi PL/SQL/DDL buffer trong SQL*Plus hoặc SQLcl, không phải một phần của câu lệnh SQL.

### 2.2. Tạo object type lồng nhau

Có thể dùng một object type làm thuộc tính của object type khác:

```sql
CREATE TYPE address_t AS OBJECT (
    street       VARCHAR2(100),
    city         VARCHAR2(50),
    postal_code  VARCHAR2(20)
);
/

CREATE TYPE customer_t AS OBJECT (
    customer_id NUMBER,
    full_name   VARCHAR2(100),
    address     address_t
);
/
```

Một giá trị `CUSTOMER_T` chứa một giá trị `ADDRESS_T`. Cấu trúc này phù hợp khi địa chỉ là một phần của hồ sơ khách hàng và thường được đọc/cập nhật cùng hồ sơ.

### 2.3. Constructor của object type

Oracle tự cung cấp constructor mặc định cho object type, với tham số tương ứng thứ tự các thuộc tính:

```sql
SELECT customer_t(
           501,
           'An Nguyen',
           address_t('12 Nguyen Hue', 'Ho Chi Minh City', '700000')
       ) AS customer_value
FROM dual;
```

`CUSTOMER_T(...)` tạo một instance của kiểu khách hàng; `ADDRESS_T(...)` tạo instance địa chỉ được truyền vào thuộc tính thứ ba.

Constructor mặc định gắn với kiểu và thứ tự thuộc tính. Nếu kiểu có nhiều thuộc tính, hãy viết danh sách rõ ràng và kiểm tra đúng thứ tự. Có thể định nghĩa constructor method riêng khi cần quy tắc khởi tạo phức tạp.

### 2.4. Truy cập thuộc tính

Với một cột object:

```sql
SELECT c.customer_id,
       c.profile.full_name,
       c.profile.address.city
FROM customers c;
```

Dấu chấm dùng để đi từ cột object đến thuộc tính, rồi tiếp tục đi vào object lồng bên trong.

Nếu một object hoặc thuộc tính lồng là NULL, biểu thức truy cập thuộc tính tương ứng có thể cho kết quả NULL. Ứng dụng cần xác định object NULL khác gì object tồn tại nhưng một thuộc tính NULL.

## 3. Object type có thể chứa method

Object type không chỉ chứa dữ liệu; nó còn có thể định nghĩa member method để thao tác trên instance. Ví dụ:

```sql
CREATE TYPE person_t AS OBJECT (
    person_id NUMBER,
    full_name VARCHAR2(100),
    MEMBER FUNCTION display_name RETURN VARCHAR2
);
/
```

Phần thân kiểu định nghĩa cách method hoạt động:

```sql
CREATE TYPE BODY person_t AS
    MEMBER FUNCTION display_name RETURN VARCHAR2 IS
    BEGIN
        RETURN full_name;
    END;
END;
/
```

Khi có một object `p`, có thể gọi method:

```sql
SELECT p.display_name()
FROM person_obj_table p;
```

Method được gọi theo instance. Trong member method, `SELF` đại diện cho instance hiện tại; với member method không cần sửa instance, có thể khai báo `MEMBER`, còn các method có thể thay đổi instance có quy tắc khai báo riêng.

Trong thiết kế ứng dụng, không nên đưa mọi logic nghiệp vụ vào object type chỉ vì Oracle hỗ trợ method. Cần cân nhắc khả năng bảo trì, kiểm thử, quyền thực thi type và mức độ phụ thuộc vào Oracle.

## 4. Object table: mỗi hàng là một object instance

Object table là bảng được tạo dựa trên một object type. Thay vì khai báo từng cột riêng trong `CREATE TABLE`, ta chỉ rõ kiểu object:

```sql
CREATE TYPE person_t AS OBJECT (
    person_id NUMBER,
    full_name VARCHAR2(100),
    birth_date DATE
);
/

CREATE TABLE person_obj_table OF person_t (
    CONSTRAINT pk_person_obj PRIMARY KEY (person_id)
);
```

Mỗi hàng của `PERSON_OBJ_TABLE` là một instance `PERSON_T`. Các thuộc tính của object được thể hiện như các cột của object table khi truy vấn.

### 4.1. INSERT vào object table

```sql
INSERT INTO person_obj_table
VALUES (
    person_t(1, 'An Nguyen', DATE '1995-04-12')
);

INSERT INTO person_obj_table
VALUES (
    person_t(2, 'Binh Tran', DATE '1992-09-30')
);
```

Constructor `PERSON_T(...)` tạo object được chèn vào bảng.

### 4.2. SELECT thuộc tính từ object table

```sql
SELECT p.person_id,
       p.full_name,
       p.birth_date
FROM person_obj_table p
ORDER BY p.person_id;
```

Có thể dùng thuộc tính trong `WHERE`, `ORDER BY`, phép JOIN và nhiều biểu thức SQL khác theo quy tắc kiểu dữ liệu.

### 4.3. Lấy toàn bộ object bằng VALUE

```sql
SELECT VALUE(p)
FROM person_obj_table p;
```

`VALUE(alias)` trả về object instance đầy đủ của hàng trong object table. Điều này khác với việc liệt kê từng thuộc tính riêng lẻ.

### 4.4. UPDATE thuộc tính của object table

```sql
UPDATE person_obj_table p
SET p.full_name = 'An Nguyen Updated'
WHERE p.person_id = 1;
```

Object table vẫn hỗ trợ DML. Constraint được khai báo trên object table hoặc các thuộc tính vẫn được áp dụng theo quy tắc Oracle.

## 5. Object column: bảng quan hệ chứa một giá trị object

Không cần tạo object table mới để dùng object type. Một bảng quan hệ thông thường có thể chứa một cột object:

```sql
CREATE TYPE address_t AS OBJECT (
    street      VARCHAR2(100),
    city        VARCHAR2(50),
    postal_code VARCHAR2(20)
);
/

CREATE TYPE customer_profile_t AS OBJECT (
    full_name VARCHAR2(100),
    address   address_t
);
/

CREATE TABLE customers_rel (
    customer_id NUMBER PRIMARY KEY,
    profile     customer_profile_t,
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);
```

`CUSTOMERS_REL` vẫn là một bảng quan hệ: `CUSTOMER_ID` và `CREATED_AT` là các cột thông thường; `PROFILE` là một cột có kiểu object.

### 5.1. INSERT object column

```sql
INSERT INTO customers_rel (customer_id, profile)
VALUES (
    501,
    customer_profile_t(
        'An Nguyen',
        address_t('12 Nguyen Hue', 'Ho Chi Minh City', '700000')
    )
);
```

### 5.2. Truy vấn thuộc tính

```sql
SELECT c.customer_id,
       c.profile.full_name AS customer_name,
       c.profile.address.street AS street,
       c.profile.address.city AS city
FROM customers_rel c;
```

### 5.3. Cập nhật thuộc tính object

Có thể cập nhật một thuộc tính của object column:

```sql
UPDATE customers_rel c
SET c.profile.address.city = 'Thu Duc'
WHERE c.customer_id = 501;
```

Nếu cần thay toàn bộ object, gán một instance mới:

```sql
UPDATE customers_rel c
SET c.profile = customer_profile_t(
                    'An Nguyen',
                    address_t('12 Nguyen Hue', 'Thu Duc', '700000')
                )
WHERE c.customer_id = 501;
```

Object column hữu ích khi cấu trúc con được coi như một thuộc tính có cấu trúc của hàng cha. Tuy nhiên, nếu cần lọc, cập nhật, ràng buộc và báo cáo từng thuộc tính con độc lập thường xuyên, các cột quan hệ thông thường có thể dễ quản lý hơn.

## 6. Collection type trong Oracle

Collection là một giá trị chứa nhiều phần tử cùng kiểu. Oracle có hai collection type SQL phổ biến:

- Nested table.
- VARRAY (variable-size array).

Một collection có thể chứa scalar hoặc object type. Ví dụ:

```sql
CREATE TYPE phone_list_t AS VARRAY(5) OF VARCHAR2(20);
/

CREATE TYPE order_line_t AS OBJECT (
    product_id NUMBER,
    quantity   NUMBER,
    unit_price NUMBER(12, 2)
);
/

CREATE TYPE order_line_nt AS TABLE OF order_line_t;
/
```

`PHONE_LIST_T` là VARRAY tối đa năm chuỗi điện thoại. `ORDER_LINE_NT` là nested table chứa các object `ORDER_LINE_T`.

### 6.1. Collection constructor

Constructor của collection dùng tên kiểu và danh sách phần tử:

```sql
phone_list_t('0901000001', '0902000002')
```

Nested table:

```sql
order_line_nt(
    order_line_t(1001, 2, 15000),
    order_line_t(1002, 1, 25000)
)
```

Thứ tự tham số của object constructor phải đúng thứ tự thuộc tính trong type definition.

### 6.2. Collection rỗng và collection NULL

Hai trạng thái này khác nhau:

- **Collection NULL (atomically null):** chưa được khởi tạo, không có instance collection.
- **Collection rỗng:** collection đã được khởi tạo nhưng có 0 phần tử.

Ví dụ:

```sql
phone_list_t()  -- VARRAY đã khởi tạo, hiện có 0 phần tử
```

Một cột collection có thể nhận NULL nếu schema cho phép:

```sql
INSERT INTO customer_contacts (customer_id, phones)
VALUES (501, NULL);
```

Hoặc nhận collection rỗng:

```sql
INSERT INTO customer_contacts (customer_id, phones)
VALUES (502, phone_list_t());
```

Ứng dụng cần xác định NULL nghĩa là “chưa biết/chưa khởi tạo”, còn collection rỗng nghĩa là “đã biết danh sách hiện không có phần tử” hay không. Không tự động coi hai trạng thái là giống nhau.

## 7. Nested table: collection không khai báo giới hạn phần tử cố định

Nested table là collection type được khai báo bằng `TABLE OF`:

```sql
CREATE TYPE order_line_t AS OBJECT (
    product_id NUMBER,
    quantity   NUMBER,
    unit_price NUMBER(12, 2)
);
/

CREATE TYPE order_line_nt AS TABLE OF order_line_t;
/
```

Nested table không khai báo giới hạn phần tử tối đa như VARRAY. Oracle lưu các phần tử của nested table trong một storage table riêng, được liên kết với hàng cha bằng metadata nội bộ.

### 7.1. Dùng nested table làm cột

```sql
CREATE TABLE orders_nested (
    order_id    NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_lines order_line_nt
)
NESTED TABLE order_lines STORE AS order_lines_store;
```

`ORDER_LINES` là một collection column. `ORDER_LINES_STORE` là storage table do Oracle sử dụng để lưu các phần tử nested table. Tên storage table được đặt tường minh để dễ tra cứu và quản trị.

### 7.2. INSERT một nested table

```sql
INSERT INTO orders_nested (
    order_id,
    customer_id,
    order_lines
)
VALUES (
    100,
    501,
    order_line_nt(
        order_line_t(2001, 2, 15000),
        order_line_t(2002, 1, 25000)
    )
);
```

Hàng cha có một collection gồm hai object line item.

### 7.3. Truy vấn nested table bằng TABLE()

Để biến collection thành các hàng có thể truy vấn, dùng collection expression với toán tử `TABLE()`:

```sql
SELECT o.order_id,
       line.product_id,
       line.quantity,
       line.unit_price
FROM orders_nested o,
     TABLE(o.order_lines) line
ORDER BY o.order_id, line.product_id;
```

`TABLE(o.order_lines)` unnest collection thành một nguồn hàng. Mỗi phần tử `ORDER_LINE_T` xuất hiện như một hàng với các thuộc tính `PRODUCT_ID`, `QUANTITY`, `UNIT_PRICE`.

Nếu collection là NULL hoặc rỗng, phép unnest không tạo hàng phần tử tương ứng. Truy vấn dùng cách nối chéo như trên sẽ không trả hàng cha không có phần tử; nếu cần giữ hàng cha, phải dùng cách outer expansion phù hợp với phiên bản Oracle, chẳng hạn `OUTER APPLY` trên các phiên bản hỗ trợ.

### 7.4. Truy vấn phần tử và điều kiện

```sql
SELECT o.order_id,
       line.product_id,
       line.quantity
FROM orders_nested o,
     TABLE(o.order_lines) line
WHERE line.quantity >= 2;
```

Có thể lọc theo thuộc tính của phần tử object như lọc cột của một bảng quan hệ.

### 7.5. DML vào nested table

Có thể thao tác trên collection thông qua collection table expression:

```sql
INSERT INTO TABLE (
    SELECT o.order_lines
    FROM orders_nested o
    WHERE o.order_id = 100
)
VALUES (
    order_line_t(2003, 3, 12000)
);
```

Lệnh trên thêm một phần tử vào collection của đơn hàng 100.

Xóa một phần tử:

```sql
DELETE FROM TABLE (
    SELECT o.order_lines
    FROM orders_nested o
    WHERE o.order_id = 100
) line
WHERE line.product_id = 2002;
```

Cập nhật thuộc tính phần tử:

```sql
UPDATE TABLE (
    SELECT o.order_lines
    FROM orders_nested o
    WHERE o.order_id = 100
) line
SET line.quantity = line.quantity + 1
WHERE line.product_id = 2001;
```

Các câu DML trên làm thay đổi collection thuộc hàng cha được xác định trong subquery. Hãy giới hạn subquery chọn đúng một hàng cha và kiểm tra số phần tử bị tác động.

### 7.6. Nested table không có thứ tự tự nhiên

Nested table là collection không có thứ tự phần tử được bảo đảm. Nếu truy vấn qua `TABLE()`, không được dựa vào thứ tự vật lý hoặc thứ tự INSERT để suy ra vị trí phần tử.

Nếu cần sắp xếp đầu ra:

```sql
SELECT o.order_id,
       line.product_id,
       line.quantity
FROM orders_nested o,
     TABLE(o.order_lines) line
ORDER BY o.order_id, line.product_id;
```

Nếu thứ tự là dữ liệu nghiệp vụ, hãy lưu thêm thuộc tính như `LINE_NO` trong object hoặc dùng bảng con quan hệ có cột `LINE_NO`.

## 8. VARRAY: collection có giới hạn và giữ thứ tự

VARRAY được khai báo bằng `VARRAY(max_size) OF element_type`:

```sql
CREATE TYPE phone_list_t AS VARRAY(5) OF VARCHAR2(20);
/
```

VARRAY có các đặc điểm:

- Có giới hạn tối đa được khai báo trong type, ở ví dụ là 5 phần tử.
- Giữ thứ tự phần tử trong collection.
- Phần tử được truy cập theo chỉ số trong PL/SQL collection semantics.
- Có thể chứa scalar hoặc object type.

### 8.1. Dùng VARRAY làm cột

```sql
CREATE TABLE customer_contacts (
    customer_id NUMBER PRIMARY KEY,
    phones      phone_list_t
);
```

### 8.2. INSERT VARRAY

```sql
INSERT INTO customer_contacts (customer_id, phones)
VALUES (
    501,
    phone_list_t('0901000001', '0902000002', '0903000003')
);
```

Danh sách điện thoại có ba phần tử theo thứ tự đã truyền.

### 8.3. Truy vấn phần tử VARRAY bằng TABLE()

```sql
SELECT c.customer_id,
       p.column_value AS phone_number
FROM customer_contacts c,
     TABLE(c.phones) p
ORDER BY c.customer_id, p.column_value;
```

Với collection phần tử scalar, `COLUMN_VALUE` là tên giả (pseudocolumn) dùng để truy cập giá trị phần tử được unnest. Nếu cần trình bày đúng thứ tự vị trí, hãy dùng cách truy cập collection theo index trong PL/SQL hoặc lưu vị trí thành thuộc tính tường minh; không dựa vào thứ tự kết quả SQL khi thiếu `ORDER BY`.

### 8.4. VARRAY vượt quá giới hạn

Với `VARRAY(5)`, collection không thể chứa quá năm phần tử. Cố gắng tạo hoặc mở rộng vượt giới hạn sẽ gây lỗi collection/giới hạn phần tử. Chọn kích thước dựa trên yêu cầu nghiệp vụ thực tế, không đặt quá nhỏ nếu danh sách có thể tăng.

### 8.5. Lưu trữ VARRAY

VARRAY được lưu như một giá trị collection của hàng cha. Tùy kích thước và cách khai báo, có thể để Oracle lưu theo cơ chế mặc định hoặc chỉ định lưu bằng LOB:

```sql
CREATE TABLE customer_contacts_lob (
    customer_id NUMBER PRIMARY KEY,
    phones      phone_list_t
)
VARRAY phones STORE AS LOB;
```

`STORE AS LOB` có thể phù hợp với collection lớn; với collection nhỏ, cần cân nhắc chi phí và cách truy cập. Hãy kiểm tra tài liệu Oracle đúng phiên bản và đặc điểm lưu trữ của ứng dụng trước khi chọn.

## 9. So sánh Nested table và VARRAY

| Tiêu chí | Nested table | VARRAY |
|---|---|---|
| Giới hạn phần tử khai báo trong type | Không có giới hạn cố định như VARRAY | Có giới hạn tối đa |
| Thứ tự phần tử | Không được bảo đảm | Được giữ trong collection |
| Lưu trữ | Phần tử trong storage table riêng | Giá trị collection gắn với hàng cha; có thể dùng LOB storage |
| Phần tử trùng | Có thể có | Có thể có |
| Truy vấn phần tử | `TABLE(collection_column)` | `TABLE(collection_column)` |
| Truy cập theo vị trí | Không dựa vào vị trí ổn định | Có ngữ nghĩa chỉ số phần tử |
| Phù hợp | Danh sách con có thể lớn, cần unnest và thao tác từng phần tử | Danh sách nhỏ, có giới hạn, thứ tự có ý nghĩa |
| Cảm nhận mô hình | Gần một tập hàng con được lồng trong hàng cha | Gần một mảng có thứ tự gắn với hàng cha |

### 9.1. Khi nào dùng nested table?

Chọn nested table khi:

- Số phần tử có thể thay đổi lớn và không biết trước giới hạn nhỏ.
- Phần tử có thể được truy vấn hoặc thao tác riêng qua `TABLE()`.
- Collection là một phần của giá trị hàng cha nhưng có nhu cầu xử lý theo phần tử.
- Không cần bảo đảm thứ tự phần tử.

### 9.2. Khi nào dùng VARRAY?

Chọn VARRAY khi:

- Số phần tử có giới hạn tự nhiên nhỏ, ví dụ tối đa năm số liên hệ ưu tiên.
- Thứ tự phần tử có ý nghĩa.
- Ứng dụng thường đọc/ghi cả collection như một giá trị.
- Không cần mô hình hóa mỗi phần tử thành một thực thể quan hệ độc lập.

Nếu danh sách có thể tăng không giới hạn hoặc mỗi phần tử cần trạng thái, constraint, quyền truy cập và vòng đời riêng, bảng con quan hệ thường là lựa chọn rõ ràng hơn.

## 10. Object table và bảng quan hệ thông thường

Object table vẫn là một bảng trong database, nhưng mỗi hàng là một instance của object type. Bảng quan hệ thông thường định nghĩa từng cột trực tiếp trong DDL.

### 10.1. Bảng quan hệ

```sql
CREATE TABLE customers_rel (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(100) NOT NULL,
    street      VARCHAR2(100),
    city        VARCHAR2(50),
    postal_code VARCHAR2(20)
);
```

### 10.2. Object table

```sql
CREATE TYPE address_t AS OBJECT (
    street      VARCHAR2(100),
    city        VARCHAR2(50),
    postal_code VARCHAR2(20)
);
/

CREATE TYPE customer_t AS OBJECT (
    customer_id NUMBER,
    full_name   VARCHAR2(100),
    address     address_t
);
/

CREATE TABLE customers_obj OF customer_t (
    CONSTRAINT pk_customers_obj PRIMARY KEY (customer_id)
);
```

Hai cách có thể biểu diễn thông tin tương tự nhưng cách truy vấn, quản lý kiểu và khả năng tương tác với ứng dụng khác nhau.

| Tiêu chí | Bảng quan hệ | Object table |
|---|---|---|
| Định nghĩa hàng | Các cột scalar/kiểu SQL | Instance của object type |
| Truy cập thuộc tính | `c.full_name`, `c.city` | `c.full_name`, `c.address.city` |
| Kiểu tái sử dụng | Có thể tái sử dụng domain/type theo cách khác | Object type dùng lại trực tiếp trong nhiều bảng/cột |
| Object identity/REF | Thường dùng PK/FK | Có thể dùng OID và REF |
| Tương tác ORM/JDBC | Thường trực tiếp hơn | Cần xử lý object/collection type theo driver |
| Tính di động giữa DBMS | Thường cao hơn với SQL quan hệ phổ biến | Phụ thuộc tính năng object-relational của Oracle |
| Phù hợp | Dữ liệu nghiệp vụ dạng hàng/cột và quan hệ rõ | Dữ liệu có cấu trúc object được tái sử dụng và cần semantics object |

Không nên kết luận object table thay thế mọi bảng quan hệ. Object table là một lựa chọn mô hình hóa trong Oracle, còn mô hình quan hệ vẫn phù hợp với phần lớn dữ liệu nghiệp vụ.

## 11. Object column so với các cột quan hệ thông thường

Một bảng quan hệ có thể chứa cả scalar columns và object columns:

```sql
CREATE TABLE customer_records (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(100) NOT NULL,
    address     address_t,
    created_at  TIMESTAMP
);
```

Ở đây:

- `CUSTOMER_ID`, `FULL_NAME`, `CREATED_AT` là các cột thông thường.
- `ADDRESS` là một object column.

Có thể chọn cách object column khi địa chỉ được coi là một cấu trúc có thể tái sử dụng, ví dụ địa chỉ giao hàng và địa chỉ thanh toán cùng dùng `ADDRESS_T`.

Tuy nhiên, nếu báo cáo thường xuyên lọc theo `CITY`, `POSTAL_CODE`, cần index và constraint độc lập trên từng thuộc tính, cần xem xét thiết kế quan hệ thông thường hoặc bổ sung cấu trúc index/constraint phù hợp. Không giả định việc lồng object làm các thuộc tính tự động có cùng khả năng quản trị như các cột scalar khai báo trực tiếp trong mọi ngữ cảnh.

## 12. Nested table so với bảng con quan hệ

Một danh sách dòng đơn hàng có thể được mô hình hóa bằng nested table:

```sql
CREATE TABLE orders_nested (
    order_id NUMBER PRIMARY KEY,
    order_lines order_line_nt
)
NESTED TABLE order_lines STORE AS order_lines_store;
```

Hoặc bằng hai bảng quan hệ:

```sql
CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL
);

CREATE TABLE order_lines (
    order_id NUMBER NOT NULL,
    line_no NUMBER NOT NULL,
    product_id NUMBER NOT NULL,
    quantity NUMBER NOT NULL,
    unit_price NUMBER(12, 2) NOT NULL,
    CONSTRAINT pk_order_lines PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
);
```

### 12.1. Khác biệt về mô hình

Với bảng con quan hệ:

- Mỗi dòng hàng là một row độc lập.
- Khóa ngoại `ORDER_ID` liên kết dòng hàng với đơn hàng.
- `LINE_NO` thể hiện thứ tự nghiệp vụ.
- Có thể khai báo PK, FK, UNIQUE, CHECK trực tiếp trên dòng hàng.
- Dễ JOIN với sản phẩm, kho, thuế và các bảng nghiệp vụ khác.

Với nested table:

- Collection được gắn như một thuộc tính của hàng cha.
- Oracle lưu các phần tử trong storage table riêng.
- Truy vấn từng phần tử qua `TABLE(order_lines)`.
- Collection được quản lý như một giá trị lồng của hàng cha.
- Không có thứ tự phần tử được bảo đảm; nếu cần thứ tự, phải lưu thuộc tính vị trí.

### 12.2. So sánh thao tác

Lấy dòng hàng bằng bảng con:

```sql
SELECT o.order_id,
       l.line_no,
       l.product_id,
       l.quantity
FROM orders o
JOIN order_lines l
  ON l.order_id = o.order_id;
```

Lấy dòng hàng bằng nested table:

```sql
SELECT o.order_id,
       l.product_id,
       l.quantity
FROM orders_nested o,
     TABLE(o.order_lines) l;
```

Cả hai đều có thể trả kết quả dạng hàng quan hệ cho truy vấn. Tuy nhiên, mô hình bảng con thường dễ tích hợp hơn với các truy vấn JOIN phức tạp, constraint và công cụ BI.

### 12.3. Chọn bảng con quan hệ khi

- Dòng con là thực thể nghiệp vụ có vòng đời riêng.
- Cần khóa ngoại đến nhiều bảng khác.
- Cần ràng buộc duy nhất/kiểm tra trên từng dòng con.
- Cần cập nhật, phân quyền, audit hoặc báo cáo từng dòng độc lập.
- Cần khả năng tương thích rộng với ORM, ETL, BI và hệ thống khác.

Chọn nested table khi collection thực sự là một phần của giá trị hàng cha và việc lưu trữ/truy cập như collection giúp mô hình rõ hơn.

## 13. REF và quan hệ giữa các object table

Object-relational model còn có kiểu `REF`, là tham chiếu đến một object row trong object table. REF không giống một khóa ngoại NUMBER/VARCHAR2 thông thường; nó tham chiếu object identity của hàng.

### 13.1. Tạo object table

```sql
CREATE TYPE customer_t AS OBJECT (
    customer_id NUMBER,
    full_name   VARCHAR2(100)
);
/

CREATE TABLE customers_obj OF customer_t (
    CONSTRAINT pk_customers_obj PRIMARY KEY (customer_id)
)
OBJECT IDENTIFIER IS PRIMARY KEY;
```

`OBJECT IDENTIFIER IS PRIMARY KEY` yêu cầu dùng khóa chính làm object identifier. Điều này hữu ích khi cần REF ổn định dựa trên khóa nghiệp vụ/kỹ thuật đã chọn.

### 13.2. Bảng chứa REF

```sql
CREATE TABLE orders_with_ref (
    order_id NUMBER PRIMARY KEY,
    customer_ref REF customer_t SCOPE IS customers_obj
);
```

`SCOPE IS customers_obj` giới hạn REF trỏ đến object table `CUSTOMERS_OBJ`.

### 13.3. INSERT REF

```sql
INSERT INTO customers_obj
VALUES (customer_t(501, 'An Nguyen'));

INSERT INTO orders_with_ref (order_id, customer_ref)
SELECT 1001, REF(c)
FROM customers_obj c
WHERE c.customer_id = 501;
```

`REF(c)` tạo tham chiếu đến object row `c`.

### 13.4. Dereference REF

```sql
SELECT o.order_id,
       DEREF(o.customer_ref).customer_id AS customer_id,
       DEREF(o.customer_ref).full_name AS customer_name
FROM orders_with_ref o;
```

`DEREF` lấy object được tham chiếu để truy cập thuộc tính. Trong nhiều ứng dụng quan hệ thông thường, khóa ngoại scalar và JOIN dễ hiểu, dễ tích hợp hơn REF. REF phù hợp khi ứng dụng thực sự cần object identity/reference semantics.

### 13.5. REF không thay thế mọi foreign key

REF gắn với object table/object identity và có quy tắc quản lý riêng. Nếu dữ liệu chủ yếu được truy vấn bằng quan hệ PK/FK, bảng quan hệ thông thường vẫn là mô hình dễ triển khai và di động hơn.

## 14. Chuyển đổi dữ liệu quan hệ thành collection

Có thể tạo nested table collection từ một truy vấn bằng `CAST(MULTISET(...))`.

Giả sử đã có:

```sql
CREATE TYPE order_line_t AS OBJECT (
    product_id NUMBER,
    quantity   NUMBER,
    unit_price NUMBER(12, 2)
);
/

CREATE TYPE order_line_nt AS TABLE OF order_line_t;
/
```

Có thể lấy các dòng quan hệ thành một collection:

```sql
SELECT CAST(
           MULTISET(
               SELECT order_line_t(
                          l.product_id,
                          l.quantity,
                          l.unit_price
                      )
               FROM order_lines l
               WHERE l.order_id = 100
           )
           AS order_line_nt
       ) AS lines
FROM dual;
```

`MULTISET` biến kết quả nhiều hàng thành collection; `CAST` xác định collection type cụ thể mà biểu thức trả về. Kỹ thuật này hữu ích khi cần đưa dữ liệu quan hệ vào object-relational API hoặc truyền một tập phần tử dưới dạng collection.

### 14.1. Cập nhật collection từ bảng quan hệ

Có thể gán collection được tạo từ bảng con vào collection column:

```sql
UPDATE orders_nested o
SET order_lines = CAST(
    MULTISET(
        SELECT order_line_t(
                   l.product_id,
                   l.quantity,
                   l.unit_price
               )
        FROM order_lines l
        WHERE l.order_id = o.order_id
    )
    AS order_line_nt
)
WHERE o.order_id = 100;
```

Subquery tạo collection từ những dòng con có cùng `ORDER_ID`. Nếu không có dòng con, MULTISET tạo collection rỗng theo kết quả truy vấn, không phải một hàng line item giả.

Khi đồng bộ hai mô hình, cần quyết định bên nào là nguồn dữ liệu chuẩn. Không duy trì cùng một danh sách dòng hàng độc lập ở cả bảng con và nested table mà không có quy trình đồng bộ rõ ràng.

## 15. Collection methods trong PL/SQL

Trong PL/SQL, collection có các method để xem và thao tác phần tử. Các method phổ biến:

| Method | Ý nghĩa |
|---|---|
| `COUNT` | Số phần tử hiện có |
| `FIRST` | Chỉ số đầu tiên có phần tử |
| `LAST` | Chỉ số cuối cùng có phần tử |
| `EXISTS(i)` | Kiểm tra phần tử tại chỉ số i có tồn tại |
| `PRIOR(i)` | Chỉ số phần tử trước i |
| `NEXT(i)` | Chỉ số phần tử sau i |
| `LIMIT` | Giới hạn tối đa; hữu ích với VARRAY |
| `EXTEND` | Thêm chỗ/phần tử ở cuối collection |
| `TRIM` | Loại phần tử cuối |
| `DELETE` | Xóa phần tử; áp dụng cho nested table, không dùng để tạo khoảng trống tùy ý trong VARRAY |

Ví dụ PL/SQL với VARRAY:

```sql
DECLARE
    v_phones phone_list_t :=
        phone_list_t('0901000001', '0902000002');
BEGIN
    DBMS_OUTPUT.PUT_LINE('COUNT=' || v_phones.COUNT);
    DBMS_OUTPUT.PUT_LINE('LIMIT=' || v_phones.LIMIT);
    DBMS_OUTPUT.PUT_LINE('FIRST=' || v_phones.FIRST);

    v_phones.EXTEND;
    v_phones(3) := '0903000003';

    DBMS_OUTPUT.PUT_LINE('NEW COUNT=' || v_phones.COUNT);
END;
/
```

VARRAY có chỉ số liên tiếp và giới hạn phần tử. Nested table trong PL/SQL có thể có chỉ số thưa sau khi dùng DELETE; vì vậy, khi lặp nested table có thể dùng FIRST/NEXT thay vì giả định `1 .. COUNT` luôn là các chỉ số tồn tại.

### 15.1. NULL collection và collection rỗng trong PL/SQL

```sql
DECLARE
    v_empty phone_list_t := phone_list_t();
    v_null  phone_list_t;
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_empty.COUNT); -- 0

    IF v_null IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Collection is atomically null');
    END IF;
END;
/
```

Gọi method như `COUNT` trên collection atomically NULL có thể phát sinh `COLLECTION_IS_NULL`; hãy khởi tạo collection trước khi dùng method nếu cần thao tác.

### 15.2. Collection methods không phải tất cả đều dùng được trong SQL

Các method như `EXTEND`, `TRIM`, `DELETE`, `FIRST`, `NEXT` chủ yếu là collection methods trong PL/SQL. Khi viết SQL, hãy dùng cú pháp SQL collection được hỗ trợ như `TABLE()`, constructor, `CAST(MULTISET(...))` và các hàm SQL phù hợp. Không giả định mọi biểu thức PL/SQL có thể được gọi trực tiếp trong SELECT.

## 16. Ràng buộc và tính toàn vẹn dữ liệu

Object type định nghĩa cấu trúc thuộc tính, nhưng không thay thế toàn bộ constraint của bảng quan hệ.

### 16.1. Constraint trên object table

```sql
CREATE TABLE person_obj_table OF person_t (
    CONSTRAINT pk_person_obj PRIMARY KEY (person_id),
    CONSTRAINT ck_person_id CHECK (person_id > 0)
);
```

Có thể đặt constraint lên thuộc tính của object table theo cú pháp hỗ trợ. Khi cần quan hệ khóa ngoại với bảng khác, phải thiết kế constraint phù hợp với cấu trúc lưu trữ.

### 16.2. Constraint trên object column

Với object column, constraint có thể tham chiếu thuộc tính đủ điều kiện:

```sql
CREATE TABLE customer_records (
    customer_id NUMBER PRIMARY KEY,
    address     address_t,
    CONSTRAINT ck_customer_postal
        CHECK (address.postal_code IS NULL
               OR LENGTH(address.postal_code) <= 20)
);
```

Hãy kiểm tra cú pháp và khả năng tham chiếu thuộc tính object trong constraint trên đúng phiên bản Oracle. Khi cần constraint phức tạp, việc tách thuộc tính thành cột quan hệ có thể đơn giản hơn.

### 16.3. Nested table không tự có khóa chính nghiệp vụ

Các phần tử nested table có thể trùng nhau. Nếu mỗi dòng con phải duy nhất theo `LINE_NO` hoặc `PRODUCT_ID`, cần đưa thuộc tính khóa vào object element và thiết kế kiểm tra phù hợp; nếu cần PK/FK và constraint rõ ràng trên từng dòng con, bảng con quan hệ thường thuận lợi hơn.

### 16.4. VARRAY giới hạn số phần tử nhưng không thay thế validation nghiệp vụ

`VARRAY(5)` ngăn collection có hơn năm phần tử, nhưng không bảo đảm:

- Không có số điện thoại trùng.
- Mọi số điện thoại đúng định dạng.
- Một số điện thoại là số chính.
- Thứ tự ưu tiên đúng nghiệp vụ.

Các quy tắc đó cần được kiểm tra ở ứng dụng, bằng constraint phù hợp hoặc mô hình bảng quan hệ.

## 17. Thay đổi object type và phụ thuộc schema

Object type là schema object. Bảng, cột, collection type, method hoặc type khác có thể phụ thuộc vào nó. Khi sửa định nghĩa type, cần xem xét dependency.

Ví dụ thêm thuộc tính:

```sql
ALTER TYPE person_t
ADD ATTRIBUTE (email VARCHAR2(150))
CASCADE;
```

Đây là ví dụ về type evolution; tùy kiểu, dependency và phiên bản, có thể cần lựa chọn `CASCADE` hoặc xử lý các phụ thuộc khác. Không chạy ALTER TYPE trên schema đang dùng nếu chưa đánh giá tác động tới bảng, dữ liệu, ứng dụng và các type phụ thuộc.

Để xem type trong schema:

```sql
SELECT type_name,
       typecode,
       attributes,
       methods
FROM user_types
ORDER BY type_name;
```

Xem thuộc tính:

```sql
SELECT type_name,
       attr_no,
       attr_name,
       attr_type_name,
       length,
       precision,
       scale
FROM user_type_attrs
WHERE type_name = 'CUSTOMER_T'
ORDER BY attr_no;
```

Xem collection type:

```sql
SELECT type_name,
       coll_type,
       upper_bound,
       elem_type_name,
       elem_type_mod
FROM user_coll_types
ORDER BY type_name;
```

Các view `USER_*` hiển thị metadata trong schema hiện tại. Dùng `ALL_*` hoặc `DBA_*` khi cần xem schema khác và có quyền phù hợp.

## 18. Quyền sử dụng object type

Để tạo và dùng object type, cần các quyền phù hợp:

- `CREATE TYPE` để tạo type trong schema.
- `CREATE TABLE` để tạo bảng dùng type.
- Quyền `EXECUTE` trên type khi schema khác cần dùng type đó.
- Các quyền DML trên bảng chứa object/collection.

Ví dụ cấp quyền dùng type cho schema ứng dụng:

```sql
GRANT EXECUTE ON customer_profile_t TO app_user;
```

Nếu type chứa type khác, ứng dụng có thể cần quyền phù hợp trên các type phụ thuộc theo cách sử dụng và quyền đã được cấp. Quản trị quyền nên theo nguyên tắc tối thiểu cần thiết.

Không cấp quyền rộng như `DBA` chỉ để một ứng dụng có thể dùng object type.

## 19. JDBC và ứng dụng Java

Các cột scalar thông thường được ánh xạ trực tiếp bằng `ResultSet.getLong`, `getString`, `getBigDecimal`... Object type và collection cần xử lý kiểu phức tạp hơn.

### 19.1. Đọc object column

JDBC có các abstraction như `java.sql.Struct` cho SQL structured type. Tùy phiên bản Oracle JDBC driver, có thể có API Oracle-specific để ánh xạ object type sang Java class.

Về mặt khái niệm:

```java
Object value = resultSet.getObject("PROFILE");
```

Giá trị trả về và cách giải mã phụ thuộc driver, type mapping và cấu hình ứng dụng. Với `Struct`, ứng dụng có thể lấy các thuộc tính bằng API tương ứng; không nên giả định mọi driver đều tự chuyển object type thành POJO.

### 19.2. Đọc collection

JDBC có `java.sql.Array` cho SQL collection trong nhiều driver. Oracle JDBC có thêm các API/kiểu ánh xạ riêng theo phiên bản. Cần kiểm tra tài liệu driver đang dùng và giải phóng tài nguyên collection đúng cách nếu driver yêu cầu.

### 19.3. Tính di động của ứng dụng

Nếu ứng dụng dùng ORM hoặc framework không ánh xạ Oracle object type/collection thuận tiện, bảng quan hệ thông thường thường đơn giản hơn:

- Mỗi entity là một bảng.
- Mối quan hệ thể hiện bằng khóa ngoại.
- Collection thể hiện bằng bảng con.
- Truy vấn bằng JOIN và mapping row thông thường.

Object-relational type phù hợp khi lợi ích của cấu trúc object trong database lớn hơn chi phí tích hợp và phụ thuộc nền tảng.

## 20. Khi nào nên dùng object-relational và khi nào dùng relational?

| Nhu cầu | Thiết kế nên cân nhắc |
|---|---|
| Địa chỉ là một cấu trúc tái sử dụng, thường đọc cùng hồ sơ | Object type trong object column |
| Một hàng trong bảng biểu diễn trực tiếp một object có identity | Object table |
| Danh sách nhỏ, có giới hạn và thứ tự quan trọng | VARRAY |
| Danh sách con có thể lớn, được gắn với hàng cha như collection | Nested table |
| Dòng con có khóa, quan hệ và vòng đời độc lập | Bảng con quan hệ |
| Cần JOIN/reporting/BI/ORM phổ biến | Bảng quan hệ thông thường |
| Cần tham chiếu object identity | REF giữa object tables |
| Cần khả năng di động giữa nhiều DBMS | Mô hình quan hệ chuẩn |

### 20.1. Ví dụ chọn mô hình cho danh sách điện thoại

**VARRAY** có thể hợp lý nếu mỗi khách hàng chỉ có tối đa năm số liên hệ, thứ tự ưu tiên quan trọng và danh sách thường được đọc/ghi như một nhóm:

```sql
CREATE TYPE phone_list_t AS VARRAY(5) OF VARCHAR2(20);
/

CREATE TABLE customer_contacts (
    customer_id NUMBER PRIMARY KEY,
    phones phone_list_t
);
```

**Bảng con quan hệ** phù hợp nếu số điện thoại cần trạng thái xác minh, loại số, thời điểm xác minh, quyền nhận OTP và lịch sử:

```sql
CREATE TABLE customer_phones (
    customer_id NUMBER NOT NULL,
    phone_no VARCHAR2(20) NOT NULL,
    phone_type VARCHAR2(20),
    is_verified CHAR(1) DEFAULT 'N' NOT NULL,
    priority_no NUMBER NOT NULL,
    CONSTRAINT pk_customer_phones
        PRIMARY KEY (customer_id, phone_no),
    CONSTRAINT ck_customer_phone_verified
        CHECK (is_verified IN ('Y', 'N'))
);
```

Ở mô hình thứ hai, mỗi số điện thoại là một hàng độc lập và có thể được truy vấn/cập nhật theo các thuộc tính riêng.

### 20.2. Ví dụ chọn mô hình cho dòng đơn hàng

Dòng đơn hàng thường có số lượng, giá, thuế, giảm giá, trạng thái giao hàng và quan hệ tới sản phẩm. Bảng `ORDER_LINES` với PK/FK thường phù hợp hơn nested table vì mỗi dòng có identity nghiệp vụ và cần được JOIN với nhiều bảng khác.

Nested table vẫn có thể phù hợp khi dòng con chỉ là một collection thuộc tính của object cha, được xử lý cùng nhau và không cần quan hệ độc lập rộng.

## 21. Bài thực hành tổng hợp

Các lệnh dưới đây tạo object type, collection type và bảng riêng trong schema thực hành. Chỉ chạy khi có quyền `CREATE TYPE`/`CREATE TABLE`, và không dùng tên trùng với đối tượng hiện có.

### Bước 1. Tạo object type địa chỉ và hồ sơ

```sql
CREATE TYPE demo_address_t AS OBJECT (
    street VARCHAR2(100),
    city VARCHAR2(50)
);
/

CREATE TYPE demo_profile_t AS OBJECT (
    full_name VARCHAR2(100),
    address demo_address_t
);
/
```

### Bước 2. Tạo bảng quan hệ có object column

```sql
CREATE TABLE demo_customers (
    customer_id NUMBER PRIMARY KEY,
    profile demo_profile_t
);
```

### Bước 3. INSERT và đọc thuộc tính

```sql
INSERT INTO demo_customers
VALUES (
    1,
    demo_profile_t(
        'An Nguyen',
        demo_address_t('12 Nguyen Hue', 'Ho Chi Minh City')
    )
);

SELECT customer_id,
       profile.full_name,
       profile.address.city
FROM demo_customers;
```

### Bước 4. Tạo object type phần tử và nested table

```sql
CREATE TYPE demo_line_t AS OBJECT (
    product_id NUMBER,
    quantity NUMBER
);
/

CREATE TYPE demo_line_nt AS TABLE OF demo_line_t;
/

CREATE TABLE demo_orders_nested (
    order_id NUMBER PRIMARY KEY,
    lines demo_line_nt
)
NESTED TABLE lines STORE AS demo_order_lines_store;
```

### Bước 5. INSERT nested table và unnest

```sql
INSERT INTO demo_orders_nested
VALUES (
    100,
    demo_line_nt(
        demo_line_t(2001, 2),
        demo_line_t(2002, 1)
    )
);

SELECT o.order_id,
       l.product_id,
       l.quantity
FROM demo_orders_nested o,
     TABLE(o.lines) l
ORDER BY o.order_id, l.product_id;
```

### Bước 6. Tạo VARRAY và bảng chứa VARRAY

```sql
CREATE TYPE demo_phone_va AS VARRAY(3) OF VARCHAR2(20);
/

CREATE TABLE demo_customer_phones (
    customer_id NUMBER PRIMARY KEY,
    phones demo_phone_va
);
```

### Bước 7. INSERT và unnest VARRAY

```sql
INSERT INTO demo_customer_phones
VALUES (
    1,
    demo_phone_va('0901000001', '0902000002')
);

SELECT c.customer_id,
       p.column_value AS phone_number
FROM demo_customer_phones c,
     TABLE(c.phones) p
ORDER BY c.customer_id, p.column_value;
```

### Bước 8. Kiểm tra metadata

```sql
SELECT type_name, typecode
FROM user_types
WHERE type_name LIKE 'DEMO_%'
ORDER BY type_name;

SELECT type_name, coll_type, upper_bound, elem_type_name
FROM user_coll_types
WHERE type_name LIKE 'DEMO_%'
ORDER BY type_name;

SELECT table_name, column_name, storage_table_name
FROM user_nested_tables
WHERE table_name = 'DEMO_ORDERS_NESTED';
```

### Bước 9. Dọn các đối tượng thực hành

Chỉ sau khi chắc chắn đây là các đối tượng do bạn tạo và không cần giữ dữ liệu:

```sql
DROP TABLE demo_customer_phones PURGE;
DROP TABLE demo_orders_nested PURGE;
DROP TABLE demo_customers PURGE;

DROP TYPE demo_line_nt FORCE;
DROP TYPE demo_line_t FORCE;
DROP TYPE demo_phone_va FORCE;
DROP TYPE demo_profile_t FORCE;
DROP TYPE demo_address_t FORCE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, bỏ qua recycle bin; DDL có commit ngầm. `DROP TYPE ... FORCE` có thể làm mất hoặc vô hiệu hóa các phụ thuộc; chỉ dùng trong schema lab sau khi đã dọn các bảng/phụ thuộc đúng thứ tự. Không dùng trên schema nghiệp vụ.

## 22. Những lỗi và nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ORA-00902: invalid datatype` | Dùng type chưa tồn tại, type không hợp lệ trong ngữ cảnh hoặc sai kiểu khai báo | Tạo type phụ thuộc trước, kiểm tra kiểu và cú pháp |
| `ORA-00904` khi truy cập thuộc tính | Sai tên thuộc tính hoặc đường dẫn object | Kiểm tra type definition và alias |
| `ORA-22905: cannot access rows from a non-nested table item` | Đối số TABLE() không phải collection phù hợp | Kiểm tra collection expression và kiểu dữ liệu |
| `ORA-22908: reference to NULL table value` | Thao tác collection table trên collection NULL | Khởi tạo collection hoặc xử lý NULL trước |
| `ORA-06531: Reference to uninitialized collection` | PL/SQL gọi method trên collection atomically NULL | Khởi tạo bằng constructor trước khi dùng |
| VARRAY vượt giới hạn | Số phần tử vượt `VARRAY(n)` | Tăng giới hạn type theo thiết kế hoặc chọn nested table/bảng con |
| Nested table trả kết quả sai thứ tự | Giả định collection có thứ tự | Thêm cột thứ tự và ORDER BY |
| TABLE(collection) không giữ hàng cha rỗng | Dùng cross expansion | Dùng outer expansion phù hợp hoặc truy vấn cha riêng |
| Object type khó thay đổi | Nhiều bảng/type phụ thuộc vào type | Quản lý type evolution và dependency có kế hoạch |
| JDBC không ánh xạ object tự động | Driver/framework chưa cấu hình type mapping | Dùng Struct/Array hoặc API Oracle driver tương thích |
| Collection trùng phần tử | Collection không tự áp uniqueness theo nghiệp vụ | Kiểm tra ở ứng dụng hoặc dùng bảng con có constraint |
| Object type được dùng thay mọi bảng quan hệ | Chọn mô hình theo cú pháp thay vì nhu cầu truy vấn | Đánh giá JOIN, constraint, ORM, BI và portability |

## 23. Quy tắc ghi nhớ

| Thành phần | Ý nghĩa và cách dùng |
|---|---|
| `CREATE TYPE ... AS OBJECT` | Định nghĩa object type có thuộc tính và có thể có method |
| `CREATE TABLE ... OF object_type` | Tạo object table; mỗi hàng là object instance |
| `object_column object_type` | Tạo object column trong bảng quan hệ |
| `CREATE TYPE ... AS TABLE OF ...` | Định nghĩa nested table collection type |
| `CREATE TYPE ... AS VARRAY(n) OF ...` | Định nghĩa VARRAY có giới hạn n phần tử |
| `NESTED TABLE col STORE AS storage_table` | Khai báo storage table cho nested table column |
| `TABLE(collection_expression)` | Unnest collection thành nguồn hàng SQL |
| `VALUE(alias)` | Lấy toàn bộ object instance từ object table |
| `REF(alias)` / `DEREF(ref)` | Tạo và giải tham chiếu object reference |
| `CAST(MULTISET(subquery) AS collection_type)` | Chuyển nhiều hàng truy vấn thành collection type |
| `phone_list_t(...)` | Constructor tạo collection instance |
| Bảng con quan hệ | Lựa chọn tốt khi phần tử có PK/FK, constraint và vòng đời độc lập |

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Object type là gì?

**Trả lời:** Kiểu dữ liệu do người dùng định nghĩa ở cấp schema, gom nhiều thuộc tính thành một giá trị có cấu trúc và có thể có method.

**Câu 2.** Object table khác object column thế nào?

**Trả lời:** Object table có mỗi hàng là một object instance; object column là một cột trong bảng quan hệ thông thường có kiểu object.

**Câu 3.** Nested table được lưu như thế nào?

**Trả lời:** Oracle lưu các phần tử trong storage table riêng và liên kết chúng với hàng cha bằng metadata nội bộ.

**Câu 4.** VARRAY khác nested table ở điểm chính nào?

**Trả lời:** VARRAY có giới hạn phần tử và giữ thứ tự; nested table không khai báo giới hạn cố định như VARRAY và không bảo đảm thứ tự.

**Câu 5.** `TABLE(collection_column)` có tác dụng gì?

**Trả lời:** Unnest collection thành các hàng để có thể SELECT, JOIN và lọc theo phần tử.

**Câu 6.** Vì sao truy vấn nested table không được dựa vào thứ tự INSERT?

**Trả lời:** Nested table không có thứ tự phần tử được bảo đảm; nếu cần thứ tự, lưu thuộc tính thứ tự và ORDER BY.

**Câu 7.** Collection rỗng khác collection NULL thế nào?

**Trả lời:** Collection rỗng đã được khởi tạo nhưng có 0 phần tử; collection NULL chưa có instance collection.

**Câu 8.** Khi nào nên dùng VARRAY?

**Trả lời:** Khi danh sách có giới hạn nhỏ tự nhiên, thứ tự có ý nghĩa và thường được xử lý như một giá trị của hàng cha.

**Câu 9.** Khi nào nên dùng bảng con quan hệ thay nested table?

**Trả lời:** Khi phần tử con có identity, khóa ngoại, constraint, audit, phân quyền hoặc vòng đời riêng.

**Câu 10.** REF có giống khóa ngoại NUMBER không?

**Trả lời:** Không. REF là tham chiếu đến object identity của object row; khóa ngoại scalar tham chiếu khóa của bảng quan hệ.

**Câu 11.** `CAST(MULTISET(subquery) AS type)` dùng để làm gì?

**Trả lời:** Chuyển nhiều hàng từ truy vấn thành một collection có kiểu SQL xác định.

**Câu 12.** Object type có thay thế constraint của bảng không?

**Trả lời:** Không. Cấu trúc type mô tả thuộc tính; tính toàn vẹn vẫn cần constraint và quy tắc phù hợp trên bảng/collection hoặc ở tầng ứng dụng.

**Câu 13.** JDBC ánh xạ object type và collection như thế nào?

**Trả lời:** Có thể dùng `Struct` cho object và `Array` cho collection hoặc API Oracle driver; khả năng cụ thể phụ thuộc driver và type mapping.

**Câu 14.** Object-relational type có luôn tốt hơn bảng quan hệ thông thường không?

**Trả lời:** Không. Cần cân nhắc nhu cầu truy vấn, JOIN, constraint, ORM, BI, tính di động và mức độ phức tạp vận hành.

## 25. Kết luận

Oracle hỗ trợ object-relational model thông qua **object type**, **object table**, **object column**, **nested table**, **VARRAY** và **REF**. Object type định nghĩa một giá trị có cấu trúc; object table lưu mỗi hàng như một object instance, còn object column đặt object bên trong một bảng quan hệ thông thường. Nested table biểu diễn collection không có giới hạn cố định như VARRAY và lưu phần tử trong storage table riêng. VARRAY có giới hạn phần tử và giữ thứ tự collection.

`TABLE()` giúp unnest collection để truy vấn từng phần tử; `CAST(MULTISET(...))` có thể chuyển kết quả nhiều hàng thành collection. Tuy nhiên, collection không tự thay thế mọi quan hệ PK/FK hay constraint của mô hình quan hệ. Khi phần tử có identity, cần JOIN nhiều bảng, audit, phân quyền hoặc vòng đời riêng, bảng con quan hệ thường dễ quản lý và tích hợp hơn.

Hãy chọn object-relational khi cấu trúc object/collection phản ánh đúng cách dữ liệu được sử dụng và lợi ích tái sử dụng kiểu đáng kể. Chọn bảng quan hệ thông thường khi khả năng truy vấn, tính toàn vẹn, tương thích ORM/BI và tính di động là ưu tiên. Mô hình tốt là mô hình diễn tả đúng nghiệp vụ, dễ bảo trì và phù hợp với cách ứng dụng thực sự đọc, ghi và quản lý dữ liệu.

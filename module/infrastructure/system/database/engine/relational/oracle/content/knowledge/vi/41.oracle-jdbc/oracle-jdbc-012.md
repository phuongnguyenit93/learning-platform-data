# REF CURSOR, OUT parameter, ARRAY và object type

Oracle JDBC cho phép Java gọi procedure và function trong Oracle Database, nhận kết quả truy vấn, lấy giá trị tham số đầu ra và trao đổi dữ liệu phức hợp. Bốn cơ chế thường gặp là **REF CURSOR**, **OUT parameter**, **ARRAY** và **object type**.

- **OUT parameter** trả một giá trị hoặc một cấu trúc dữ liệu từ PL/SQL về Java thông qua CallableStatement.
- **REF CURSOR** trả một cursor đang mở cho kết quả truy vấn. Oracle JDBC biểu diễn kết quả đó dưới dạng ResultSet.
- **ARRAY** biểu diễn một collection SQL được định nghĩa trong schema, chẳng hạn nested table hoặc VARRAY.
- **Object type** là kiểu dữ liệu SQL do người dùng định nghĩa bằng CREATE TYPE ... AS OBJECT; JDBC có thể ánh xạ nó qua Struct, SQLData hoặc API Oracle.

Các kiểu dữ liệu này thường xuất hiện cùng nhau trong một API PL/SQL. Ví dụ, Java gọi procedure tìm đơn hàng, truyền danh sách mã khách hàng bằng ARRAY, nhận một REF CURSOR chứa các dòng đơn hàng, đồng thời nhận OUT parameter là tổng số dòng. Để triển khai ổn định, cần hiểu cách khai báo kiểu ở database, cách đăng ký tham số trong JDBC, cách đọc kết quả và cách quản lý transaction cùng tài nguyên.

## 1. Gọi procedure và function bằng CallableStatement

JDBC dùng CallableStatement để gọi stored procedure hoặc stored function. Cú pháp gọi phổ biến:

~~~java
CallableStatement cs = connection.prepareCall(
    "{ call app.order_api.find_orders(?, ?) }"
);
~~~

Với procedure, các placeholder ? đại diện cho tham số theo thứ tự khai báo trong PL/SQL. Với function, placeholder đầu tiên thường là giá trị trả về:

~~~java
CallableStatement cs = connection.prepareCall(
    "{ ? = call app.order_api.count_orders(?) }"
);
~~~

Trước khi gọi:

- Dùng setXxx() hoặc setObject() để gán tham số IN.
- Dùng registerOutParameter() để đăng ký tham số OUT hoặc IN OUT.
- Gọi execute() hoặc phương thức thực thi phù hợp.
- Đọc giá trị OUT bằng getXxx() hoặc getObject().

Ví dụ procedure có IN, OUT và IN OUT:

~~~sql
CREATE OR REPLACE PROCEDURE app.adjust_amount(
  p_order_id IN NUMBER,
  p_amount   IN OUT NUMBER,
  p_status   OUT VARCHAR2
) AS
BEGIN
  IF p_amount < 0 THEN
    p_status := 'INVALID';
    RETURN;
  END IF;

  UPDATE app.orders
  SET    total_amount = total_amount + p_amount
  WHERE  order_id = p_order_id;

  p_status := CASE
                WHEN SQL%ROWCOUNT = 1 THEN 'UPDATED'
                ELSE 'NOT_FOUND'
              END;

  p_amount := p_amount * 1.1;
END;
/
~~~

Java:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ call app.adjust_amount(?, ?, ?) }")) {

    cs.setLong(1, 1001L);
    cs.setBigDecimal(2, new BigDecimal("25.00"));
    cs.registerOutParameter(2, Types.NUMERIC);
    cs.registerOutParameter(3, Types.VARCHAR);

    cs.execute();

    BigDecimal adjustedAmount = cs.getBigDecimal(2);
    String status = cs.getString(3);

    // Sử dụng kết quả OUT trong ứng dụng.
}
~~~

Với tham số IN OUT, vừa gán giá trị đầu vào bằng setXxx() vừa đăng ký kiểu đầu ra bằng registerOutParameter(). JDBC không tự suy ra kiểu OUT chỉ từ giá trị IN.

### Thứ tự tham số và kiểu dữ liệu

Các vị trí trong CallableStatement bắt đầu từ 1. Thứ tự phải khớp với chữ ký procedure/function:

| PL/SQL mode | JDBC |
|---|---|
| IN | setXxx(index, value) |
| OUT | registerOutParameter(index, sqlType) |
| IN OUT | setXxx(index, value) và registerOutParameter(index, sqlType) |
| Function return | Đăng ký OUT tại vị trí 1, sau đó gán các tham số đầu vào từ vị trí 2 |

Ví dụ function trả NUMBER:

~~~sql
CREATE OR REPLACE FUNCTION app.order_count(
  p_customer_id IN NUMBER
) RETURN NUMBER AS
  l_count NUMBER;
BEGIN
  SELECT COUNT(*)
  INTO   l_count
  FROM   app.orders
  WHERE  customer_id = p_customer_id;

  RETURN l_count;
END;
/
~~~

Java:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ ? = call app.order_count(?) }")) {

    cs.registerOutParameter(1, Types.NUMERIC);
    cs.setLong(2, 200L);
    cs.execute();

    BigDecimal count = cs.getBigDecimal(1);
}
~~~

Oracle NUMBER thường được ánh xạ an toàn sang BigDecimal, đặc biệt khi cần giữ độ chính xác số thập phân. Chỉ chuyển sang long, int hoặc double khi miền giá trị và độ chính xác phù hợp.

## 2. OUT parameter và cách đọc giá trị trả về

OUT parameter dùng để trả dữ liệu scalar hoặc một giá trị có kiểu SQL/PLSQL được JDBC hỗ trợ. Một procedure có thể có nhiều OUT parameter, ví dụ mã trạng thái, số lượng xử lý, thông báo hoặc timestamp.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE app.get_order_status(
  p_order_id IN  NUMBER,
  p_status   OUT VARCHAR2,
  p_amount   OUT NUMBER,
  p_paid_at  OUT TIMESTAMP
) AS
BEGIN
  SELECT status, total_amount, paid_at
  INTO   p_status, p_amount, p_paid_at
  FROM   app.orders
  WHERE  order_id = p_order_id;
EXCEPTION
  WHEN NO_DATA_FOUND THEN
    p_status  := 'NOT_FOUND';
    p_amount  := NULL;
    p_paid_at := NULL;
END;
/
~~~

Java:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ call app.get_order_status(?, ?, ?, ?) }")) {

    cs.setLong(1, 1001L);
    cs.registerOutParameter(2, Types.VARCHAR);
    cs.registerOutParameter(3, Types.NUMERIC);
    cs.registerOutParameter(4, Types.TIMESTAMP);

    cs.execute();

    String status = cs.getString(2);
    BigDecimal amount = cs.getBigDecimal(3);
    Timestamp paidAt = cs.getTimestamp(4);

    boolean amountWasNull = cs.wasNull();
}
~~~

wasNull() kiểm tra giá trị OUT vừa đọc có phải SQL NULL hay không. Hãy gọi ngay sau getter cần kiểm tra vì lần đọc tiếp theo có thể làm thay đổi trạng thái này.

### Đăng ký kiểu OUT chính xác

Kiểu JDBC đăng ký phải tương thích với kiểu PL/SQL/SQL trả về:

| Kiểu Oracle | JDBC type thường dùng |
|---|---|
| VARCHAR2, CHAR | Types.VARCHAR, Types.CHAR |
| NUMBER | Types.NUMERIC hoặc Types.DECIMAL |
| DATE | Types.DATE hoặc Types.TIMESTAMP tùy cách ánh xạ cần dùng |
| TIMESTAMP | Types.TIMESTAMP |
| CLOB | Types.CLOB |
| BLOB | Types.BLOB |
| REF CURSOR | Types.REF_CURSOR hoặc OracleTypes.CURSOR |
| SQL collection | Types.ARRAY cùng tên kiểu collection |
| SQL object | Types.STRUCT cùng tên kiểu object |

Với kiểu dữ liệu đặc thù Oracle, driver có thể cung cấp các hằng và API mở rộng trong package oracle.jdbc. Khi dùng API mở rộng, cần bảo đảm phiên bản Oracle JDBC driver tương thích với database và JDK đang triển khai.

### NULL và kiểu OUT

Khi tham số OUT trả NULL, getter tương ứng thường trả null với object type hoặc giá trị mặc định với primitive. Ví dụ getInt() trả 0 nếu giá trị SQL NULL; phải gọi wasNull() để phân biệt NULL với số 0.

Đối với tham số IN có giá trị NULL, dùng setNull(index, sqlType):

~~~java
cs.setNull(1, Types.NUMERIC);
~~~

Đăng ký đúng kiểu SQL giúp driver xử lý chuyển đổi dữ liệu và tránh lỗi kiểu không tương thích.

## 3. REF CURSOR là gì?

REF CURSOR là biến tham chiếu đến một cursor đang mở trong PL/SQL. Procedure có thể mở cursor bằng câu SELECT rồi trả cursor đó cho Java qua OUT parameter. Java JDBC nhận kết quả dưới dạng ResultSet và đọc từng dòng.

REF CURSOR phù hợp khi procedure cần trả một tập dòng có cấu trúc nhiều cột, có thể thay đổi số dòng theo điều kiện truy vấn. Thay vì khai báo hàng loạt OUT parameter cho từng dòng, procedure chỉ trả một cursor.

Oracle thường dùng SYS_REFCURSOR cho weak REF CURSOR:

~~~sql
CREATE OR REPLACE PROCEDURE app.find_orders(
  p_customer_id IN  NUMBER,
  p_result      OUT SYS_REFCURSOR
) AS
BEGIN
  OPEN p_result FOR
    SELECT order_id,
           order_date,
           status,
           total_amount
    FROM   app.orders
    WHERE  customer_id = p_customer_id
    ORDER BY order_date DESC;
END;
/
~~~

OPEN ... FOR SELECT mở cursor và gắn nó với kết quả truy vấn. Procedure kết thúc nhưng cursor vẫn được trả về cho caller. Java có thể fetch dữ liệu từ cursor đó cho đến khi hết dòng hoặc ResultSet được đóng.

### Nhận REF CURSOR bằng JDBC

Cách phổ biến với Oracle JDBC là đăng ký OUT parameter bằng OracleTypes.CURSOR:

~~~java
import java.math.BigDecimal;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;

import oracle.jdbc.OracleTypes;

try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ call app.find_orders(?, ?) }")) {

    cs.setLong(1, 200L);
    cs.registerOutParameter(2, OracleTypes.CURSOR);

    cs.execute();

    try (ResultSet rs = (ResultSet) cs.getObject(2)) {
        while (rs.next()) {
            long orderId = rs.getLong("ORDER_ID");
            Timestamp orderDate = rs.getTimestamp("ORDER_DATE");
            String status = rs.getString("STATUS");
            BigDecimal amount = rs.getBigDecimal("TOTAL_AMOUNT");

            // Chuyển dữ liệu sang DTO hoặc xử lý tại đây.
        }
    }
}
~~~

Một số phiên bản driver hỗ trợ đăng ký theo JDBC standard Types.REF_CURSOR:

~~~java
cs.registerOutParameter(2, Types.REF_CURSOR);
~~~

Hãy kiểm tra khả năng tương thích của driver trước khi chọn cách đăng ký. OracleTypes.CURSOR là hằng Oracle-specific, thường được dùng trong ví dụ Oracle JDBC lâu đời; Types.REF_CURSOR là kiểu JDBC standard từ JDBC 4.2.

### Đọc cột trong ResultSet

Có thể đọc theo tên cột hoặc chỉ số:

~~~java
long orderId = rs.getLong("ORDER_ID");
String status = rs.getString("STATUS");
BigDecimal amount = rs.getBigDecimal("TOTAL_AMOUNT");
~~~

Dùng tên cột giúp code dễ đọc hơn, nhưng cần bảo đảm tên không bị trùng hoặc mơ hồ trong SELECT. Nếu query join nhiều bảng có cột trùng tên, hãy đặt alias:

~~~sql
SELECT o.order_id AS ORDER_ID,
       c.customer_name AS CUSTOMER_NAME,
       o.total_amount AS ORDER_AMOUNT
FROM   app.orders o
JOIN   app.customers c
  ON   c.customer_id = o.customer_id
WHERE  o.customer_id = p_customer_id;
~~~

JDBC getter trả null hoặc giá trị mặc định tùy kiểu. Với cột nullable dạng primitive, gọi wasNull() ngay sau getter:

~~~java
long maybeId = rs.getLong("OPTIONAL_ID");
boolean idIsNull = rs.wasNull();
~~~

### Nhiều REF CURSOR trong một procedure

Một procedure có thể trả nhiều cursor, ví dụ một cursor chứa thông tin đơn hàng và cursor khác chứa chi tiết mặt hàng:

~~~sql
CREATE OR REPLACE PROCEDURE app.get_order_bundle(
  p_order_id IN  NUMBER,
  p_header   OUT SYS_REFCURSOR,
  p_items    OUT SYS_REFCURSOR
) AS
BEGIN
  OPEN p_header FOR
    SELECT order_id, customer_id, status, total_amount
    FROM   app.orders
    WHERE  order_id = p_order_id;

  OPEN p_items FOR
    SELECT product_id, quantity, unit_price
    FROM   app.order_items
    WHERE  order_id = p_order_id;
END;
/
~~~

Java đăng ký hai OUT cursor riêng:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ call app.get_order_bundle(?, ?, ?) }")) {

    cs.setLong(1, 1001L);
    cs.registerOutParameter(2, OracleTypes.CURSOR);
    cs.registerOutParameter(3, OracleTypes.CURSOR);

    cs.execute();

    try (ResultSet header = (ResultSet) cs.getObject(2);
         ResultSet items = (ResultSet) cs.getObject(3)) {

        while (header.next()) {
            // Đọc header.
        }

        while (items.next()) {
            // Đọc item.
        }
    }
}
~~~

Mỗi ResultSet phải được đóng sau khi dùng. Không đóng CallableStatement trước khi đã đọc xong các ResultSet mà nó trả về.

### REF CURSOR và transaction

REF CURSOR là handle đến kết quả truy vấn, không phải một bản sao dữ liệu độc lập. Giữ Connection và CallableStatement mở trong khi fetch dữ liệu. Không trả ResultSet ra khỏi phạm vi quản lý tài nguyên nếu connection đã bị đóng hoặc trả về pool.

Nếu procedure mở cursor rồi caller commit/rollback hoặc thay đổi transaction trong lúc đang fetch, hành vi đọc và tính nhất quán phụ thuộc loại truy vấn, isolation level và trạng thái transaction. Thiết kế đơn giản và dễ kiểm soát nhất là giữ connection cho đến khi đọc xong ResultSet, sau đó đóng ResultSet/statement và kết thúc transaction theo yêu cầu.

## 4. REF CURSOR so với ResultSet thông thường

ResultSet là giao diện JDBC để duyệt dữ liệu. REF CURSOR là kiểu cursor phía Oracle có thể được trả qua PL/SQL. Khi Java nhận REF CURSOR, driver cung cấp một ResultSet.

| Tiêu chí | REF CURSOR OUT | ResultSet từ PreparedStatement |
|---|---|---|
| Cách tạo query | Query nằm trong procedure/function PL/SQL | Query nằm trong Java |
| Cách gọi | CallableStatement | PreparedStatement |
| Tập kết quả | Trả qua OUT parameter | Trả từ executeQuery() |
| Đóng gói nghiệp vụ | Có thể gom logic và quyền truy cập trong package | SQL nằm ở tầng Java |
| Nhiều tập kết quả | Có thể trả nhiều REF CURSOR OUT | Có thể dùng nhiều ResultSet từ các statement khác nhau |
| Tính tái sử dụng | Procedure có thể được nhiều ứng dụng gọi | Logic truy vấn gắn với code gọi |

REF CURSOR hữu ích khi database package là giao diện dữ liệu chính thức cho nhiều ứng dụng, hoặc khi cần tập trung logic truy vấn tại PL/SQL. PreparedStatement phù hợp khi câu SQL được quản lý ở ứng dụng và không cần đóng gói qua stored procedure.

## 5. ARRAY và SQL collection type

Oracle SQL hỗ trợ collection type ở cấp schema. Hai dạng thường dùng:

- **Nested table**: collection có số phần tử không bị giới hạn bởi một bound khai báo như VARRAY; có thể dùng làm kiểu tham số, thuộc tính object hoặc cột table.
- **VARRAY**: collection có giới hạn số phần tử tối đa được khai báo; giữ thứ tự phần tử trong collection.

Ví dụ tạo nested table chứa NUMBER:

~~~sql
CREATE TYPE app.number_list_t AS TABLE OF NUMBER;
/
~~~

Ví dụ tạo VARRAY tối đa 100 mã:

~~~sql
CREATE TYPE app.number_array_t AS VARRAY(100) OF NUMBER;
/
~~~

Cả nested table và VARRAY có thể được truyền qua Oracle JDBC dưới dạng java.sql.Array, nhưng kiểu SQL phải được tạo trước ở schema. Đối với Oracle JDBC, nên dùng OracleConnection.createOracleArray() để tạo array; Connection.createArrayOf() không được Oracle JDBC hỗ trợ theo cách triển khai chuẩn của một số database khác.

### Procedure nhận ARRAY

Tạo procedure nhận collection và trả số phần tử:

~~~sql
CREATE OR REPLACE PROCEDURE app.count_ids(
  p_ids   IN  app.number_list_t,
  p_count OUT NUMBER
) AS
BEGIN
  IF p_ids IS NULL THEN
    p_count := 0;
  ELSE
    p_count := p_ids.COUNT;
  END IF;
END;
/
~~~

Java tạo và truyền ARRAY:

~~~java
import java.math.BigDecimal;
import java.sql.Array;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.Types;

import oracle.jdbc.OracleConnection;

try (Connection connection = dataSource.getConnection()) {
    OracleConnection oracleConnection =
        connection.unwrap(OracleConnection.class);

    Object[] values = new Object[] {
        new BigDecimal("10"),
        new BigDecimal("20"),
        new BigDecimal("30")
    };

    Array ids = oracleConnection.createOracleArray(
        "APP.NUMBER_LIST_T",
        values
    );

    try (CallableStatement cs = connection.prepareCall(
            "{ call app.count_ids(?, ?) }")) {

        cs.setArray(1, ids);
        cs.registerOutParameter(2, Types.NUMERIC);
        cs.execute();

        BigDecimal count = cs.getBigDecimal(2);
    } finally {
        ids.free();
    }
}
~~~

Tên type truyền cho createOracleArray là tên collection type ở cấp schema, không phải tên kiểu phần tử. Nên dùng tên schema và type viết hoa theo cách Oracle lưu identifier thông thường, ví dụ APP.NUMBER_LIST_T.

### Nhận ARRAY từ OUT parameter

Procedure:

~~~sql
CREATE OR REPLACE PROCEDURE app.get_active_ids(
  p_ids OUT app.number_list_t
) AS
BEGIN
  SELECT CAST(
           MULTISET(
             SELECT customer_id
             FROM   app.customers
             WHERE  active_flag = 'Y'
             ORDER BY customer_id
           ) AS app.number_list_t
         )
  INTO p_ids
  FROM dual;
END;
/
~~~

Java:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ call app.get_active_ids(?) }")) {

    cs.registerOutParameter(1, Types.ARRAY, "APP.NUMBER_LIST_T");
    cs.execute();

    Array result = cs.getArray(1);
    if (result != null) {
        try {
            Object[] elements = (Object[]) result.getArray();

            for (Object element : elements) {
                BigDecimal id = (BigDecimal) element;
                // Xử lý id.
            }
        } finally {
            result.free();
        }
    }
}
~~~

Với collection NUMBER, phần tử thường được driver trả về dưới dạng BigDecimal. Kiểu Java cụ thể còn phụ thuộc kiểu SQL cơ sở, mapping và driver. Hãy kiểm tra kiểu runtime khi tích hợp với các kiểu collection phức tạp.

### Duyệt ARRAY bằng ResultSet

java.sql.Array có phương thức getResultSet() để duyệt phần tử như một ResultSet. Cách này có thể hữu ích với collection lớn hoặc khi không muốn chuyển toàn bộ phần tử thành Java array cùng lúc:

~~~java
Array ids = cs.getArray(1);

if (ids != null) {
    try (ResultSet elements = ids.getResultSet()) {
        while (elements.next()) {
            long index = elements.getLong(1);
            BigDecimal value = elements.getBigDecimal(2);
            // index là vị trí collection, value là phần tử.
        }
    } finally {
        ids.free();
    }
}
~~~

Với collection rất lớn, hãy cân nhắc memory usage và cách fetch. getArray() có thể materialize toàn bộ phần tử trong JVM; getResultSet() cung cấp giao diện duyệt theo dòng nhưng vẫn cần kiểm tra hành vi driver và kích thước dữ liệu.

## 6. Object type trong Oracle SQL

Object type là kiểu dữ liệu SQL do người dùng định nghĩa. Nó có thể chứa nhiều thuộc tính có kiểu dữ liệu khác nhau và được dùng làm:

- Kiểu tham số IN/OUT của procedure.
- Kiểu phần tử của collection.
- Kiểu cột trong table.
- Kiểu kết quả của function.
- Cấu trúc dữ liệu trao đổi giữa Java và PL/SQL.

Ví dụ tạo object type địa chỉ:

~~~sql
CREATE TYPE app.address_t AS OBJECT (
  street VARCHAR2(100),
  city   VARCHAR2(60),
  zip    VARCHAR2(15)
);
/
~~~

Procedure trả object:

~~~sql
CREATE OR REPLACE PROCEDURE app.get_address(
  p_customer_id IN  NUMBER,
  p_address     OUT app.address_t
) AS
BEGIN
  SELECT app.address_t(street, city, zip)
  INTO   p_address
  FROM   app.customers
  WHERE  customer_id = p_customer_id;
END;
/
~~~

JDBC ánh xạ SQL object qua java.sql.Struct. Struct giữ tên SQL type và danh sách thuộc tính theo thứ tự khai báo của object type.

### Nhận object qua OUT parameter bằng Struct

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(
         "{ call app.get_address(?, ?) }")) {

    cs.setLong(1, 200L);
    cs.registerOutParameter(2, Types.STRUCT, "APP.ADDRESS_T");
    cs.execute();

    Struct address = (Struct) cs.getObject(2);

    if (address != null) {
        Object[] attributes = address.getAttributes();

        String street = (String) attributes[0];
        String city = (String) attributes[1];
        String zip = (String) attributes[2];
    }
}
~~~

getAttributes() trả mảng các thuộc tính theo thứ tự khai báo trong SQL object type. Vì vậy, nếu DBA thay đổi thứ tự hoặc cấu trúc type, Java mapping có thể cần cập nhật tương ứng. Không nên dựa vào thứ tự thuộc tính mà không quản lý schema version.

Có thể kiểm tra tên SQL type:

~~~java
String sqlTypeName = address.getSQLTypeName();
~~~

### Truyền object từ Java vào PL/SQL

Với JDBC driver hỗ trợ Connection.createStruct(), có thể tạo Struct từ tên SQL type và mảng thuộc tính:

~~~java
Object[] attributes = new Object[] {
    "12 Nguyen Hue",
    "Ho Chi Minh City",
    "700000"
};

Struct address = connection.createStruct(
    "APP.ADDRESS_T",
    attributes
);

try (CallableStatement cs = connection.prepareCall(
        "{ call app.save_address(?) }")) {

    cs.setObject(1, address, Types.STRUCT);
    cs.execute();
}
~~~

Ví dụ procedure:

~~~sql
CREATE OR REPLACE PROCEDURE app.save_address(
  p_address IN app.address_t
) AS
BEGIN
  INSERT INTO app.customer_addresses(street, city, zip)
  VALUES (
    p_address.street,
    p_address.city,
    p_address.zip
  );
END;
/
~~~

Connection.createStruct() là API JDBC chuẩn. Với driver hoặc kiểu object đặc thù, có thể cần dùng API Oracle hoặc mapping riêng. Hãy xác nhận hỗ trợ trên đúng phiên bản driver đang triển khai.

## 7. Ánh xạ object type sang Java class bằng SQLData

Nếu ứng dụng thường xuyên làm việc với cùng một SQL object type, thao tác trực tiếp với Object[] có thể khó bảo trì. JDBC cung cấp interface SQLData để ánh xạ SQL object sang Java class.

Ví dụ class Java:

~~~java
import java.sql.SQLData;
import java.sql.SQLInput;
import java.sql.SQLOutput;
import java.sql.SQLException;

public class Address implements SQLData {
    private String street;
    private String city;
    private String zip;

    public Address() {
    }

    public Address(String street, String city, String zip) {
        this.street = street;
        this.city = city;
        this.zip = zip;
    }

    @Override
    public String getSQLTypeName() {
        return "APP.ADDRESS_T";
    }

    @Override
    public void readSQL(SQLInput input, String typeName)
            throws SQLException {
        street = input.readString();
        city = input.readString();
        zip = input.readString();
    }

    @Override
    public void writeSQL(SQLOutput output)
            throws SQLException {
        output.writeString(street);
        output.writeString(city);
        output.writeString(zip);
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getZip() {
        return zip;
    }
}
~~~

Đăng ký type map trên connection:

~~~java
Map<String, Class<?>> typeMap = new HashMap<>(connection.getTypeMap());
typeMap.put("APP.ADDRESS_T", Address.class);
connection.setTypeMap(typeMap);
~~~

Khi đọc object từ kết quả JDBC, driver có thể sử dụng type map để ánh xạ SQL type thành class Java tương ứng:

~~~java
Object value = cs.getObject(2);
Address address = (Address) value;
~~~

Việc mapping phụ thuộc driver và cấu hình type map. Tên SQL type trong map cần khớp tên schema/type. Với ứng dụng lớn, nên đóng gói việc đăng ký type map ở tầng truy cập dữ liệu và kiểm thử khi connection được lấy từ pool.

SQLData phù hợp với mapping portable theo JDBC. Oracle cũng có các API mở rộng như OracleData/OracleDataFactory cho các trường hợp cần khả năng riêng của Oracle JDBC.

## 8. Collection chứa object type

Một SQL collection có thể chứa scalar như NUMBER hoặc chứa object type. Đây là cách biểu diễn danh sách các cấu trúc phức hợp.

Tạo collection type:

~~~sql
CREATE TYPE app.address_list_t AS TABLE OF app.address_t;
/
~~~

Procedure nhận danh sách địa chỉ:

~~~sql
CREATE OR REPLACE PROCEDURE app.save_addresses(
  p_addresses IN app.address_list_t
) AS
BEGIN
  FOR i IN 1 .. p_addresses.COUNT LOOP
    INSERT INTO app.customer_addresses(street, city, zip)
    VALUES (
      p_addresses(i).street,
      p_addresses(i).city,
      p_addresses(i).zip
    );
  END LOOP;
END;
/
~~~

Java tạo từng Struct, sau đó đóng gói vào Oracle Array:

~~~java
OracleConnection oracleConnection =
    connection.unwrap(OracleConnection.class);

Struct a1 = connection.createStruct(
    "APP.ADDRESS_T",
    new Object[] { "12 Nguyen Hue", "Ho Chi Minh City", "700000" }
);

Struct a2 = connection.createStruct(
    "APP.ADDRESS_T",
    new Object[] { "1 Le Loi", "Ho Chi Minh City", "700000" }
);

Array addresses = oracleConnection.createOracleArray(
    "APP.ADDRESS_LIST_T",
    new Object[] { a1, a2 }
);

try (CallableStatement cs = connection.prepareCall(
        "{ call app.save_addresses(?) }")) {
    cs.setArray(1, addresses);
    cs.execute();
} finally {
    addresses.free();
}
~~~

Ví dụ này cho thấy hai tầng kiểu dữ liệu:

1. APP.ADDRESS_T là SQL object type, mỗi phần tử được biểu diễn bằng Struct.
2. APP.ADDRESS_LIST_T là SQL collection type chứa các object; Java tạo collection bằng createOracleArray().

Không truyền tên APP.ADDRESS_T cho createOracleArray() khi procedure yêu cầu APP.ADDRESS_LIST_T. Tham số này cần tên kiểu collection, không phải kiểu phần tử.

## 9. SQL object/collection và PL/SQL record/associative array

Một điểm dễ nhầm là kiểu SQL do schema định nghĩa và kiểu chỉ tồn tại trong PL/SQL package không giống nhau.

| Kiểu | Khai báo | Khả năng JDBC |
|---|---|---|
| SQL object type | CREATE TYPE ... AS OBJECT | Có thể ánh xạ bằng Struct/SQLData |
| SQL nested table | CREATE TYPE ... AS TABLE OF ... | Có thể ánh xạ bằng java.sql.Array và Oracle JDBC API |
| SQL VARRAY | CREATE TYPE ... AS VARRAY(...) OF ... | Có thể ánh xạ bằng java.sql.Array và Oracle JDBC API |
| PL/SQL RECORD | TYPE ... IS RECORD trong PL/SQL | Không phải SQL STRUCT thông thường; cần API hỗ trợ riêng hoặc wrapper |
| PL/SQL associative array | TYPE ... IS TABLE OF ... INDEX BY ... | Cần API Oracle-specific; không đồng nhất với SQL ARRAY |
| SYS_REFCURSOR | Cursor variable của Oracle | JDBC nhận dưới dạng ResultSet |

Nếu procedure khai báo tham số bằng một type chỉ tồn tại bên trong package, Java không thể mặc định đăng ký nó như Types.STRUCT hoặc Types.ARRAY. Khi cần API JDBC ổn định, thường thuận tiện hơn nếu công bố SQL object/collection type ở cấp schema, hoặc tạo wrapper PL/SQL dùng các kiểu JDBC hỗ trợ.

Oracle JDBC có API riêng để bind PL/SQL associative arrays trong các phiên bản hỗ trợ. Các phương thức và kiểu đăng ký phụ thuộc driver, ví dụ OracleCallableStatement có các API cho PL/SQL index table. Không nên dùng createOracleArray() như thể nó tự động nhận mọi associative array type.

## 10. Kết hợp OUT parameter, REF CURSOR và ARRAY trong một API

Một package có thể cung cấp nhiều kiểu kết quả trong cùng một procedure. Ví dụ procedure nhận danh sách customer ID, trả REF CURSOR chứa đơn hàng và OUT parameter chứa số khách hàng được yêu cầu.

Tạo collection type:

~~~sql
CREATE TYPE app.customer_id_list_t AS TABLE OF NUMBER;
/
~~~

Tạo package:

~~~sql
CREATE OR REPLACE PACKAGE app.order_api AS
  PROCEDURE find_orders(
    p_customer_ids IN  app.customer_id_list_t,
    p_orders       OUT SYS_REFCURSOR,
    p_row_count    OUT NUMBER
  );
END order_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY app.order_api AS
  PROCEDURE find_orders(
    p_customer_ids IN  app.customer_id_list_t,
    p_orders       OUT SYS_REFCURSOR,
    p_row_count    OUT NUMBER
  ) AS
  BEGIN
    IF p_customer_ids IS NULL OR p_customer_ids.COUNT = 0 THEN
      p_row_count := 0;

      OPEN p_orders FOR
        SELECT order_id, customer_id, status, total_amount
        FROM   app.orders
        WHERE  1 = 0;

      RETURN;
    END IF;

    SELECT COUNT(DISTINCT column_value)
    INTO   p_row_count
    FROM   TABLE(p_customer_ids);

    OPEN p_orders FOR
      SELECT order_id,
             customer_id,
             status,
             total_amount
      FROM   app.orders
      WHERE  customer_id IN (
        SELECT column_value
        FROM   TABLE(p_customer_ids)
      )
      ORDER BY order_id;
  END find_orders;
END order_api;
/
~~~

Java:

~~~java
import java.math.BigDecimal;
import java.sql.Array;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;

import oracle.jdbc.OracleConnection;
import oracle.jdbc.OracleTypes;

public void findOrders(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        OracleConnection oracleConnection =
            connection.unwrap(OracleConnection.class);

        Object[] customerIds = {
            new BigDecimal("101"),
            new BigDecimal("202"),
            new BigDecimal("303")
        };

        Array idArray = oracleConnection.createOracleArray(
            "APP.CUSTOMER_ID_LIST_T",
            customerIds
        );

        try (CallableStatement cs = connection.prepareCall(
                "{ call app.order_api.find_orders(?, ?, ?) }")) {

            cs.setArray(1, idArray);
            cs.registerOutParameter(2, OracleTypes.CURSOR);
            cs.registerOutParameter(3, Types.NUMERIC);

            cs.execute();

            BigDecimal requestedCustomerCount = cs.getBigDecimal(3);

            try (ResultSet rs = (ResultSet) cs.getObject(2)) {
                while (rs.next()) {
                    long orderId = rs.getLong("ORDER_ID");
                    long customerId = rs.getLong("CUSTOMER_ID");
                    String status = rs.getString("STATUS");
                    BigDecimal total = rs.getBigDecimal("TOTAL_AMOUNT");

                    // Map dòng kết quả sang DTO.
                }
            }
        } finally {
            idArray.free();
        }
    }
}
~~~

Ví dụ thể hiện cách phối hợp:

- ARRAY truyền một tập giá trị từ Java vào PL/SQL.
- REF CURSOR trả tập dòng từ PL/SQL về Java.
- OUT NUMBER trả thêm một giá trị scalar.
- CallableStatement là điểm kết nối cho toàn bộ lời gọi.

Trong hệ thống thật, cần xác định rõ OUT parameter đếm số customer hay số order. Ví dụ trên đếm số customer ID khác nhau trong input collection; số dòng trả về có thể lớn hơn vì một customer có nhiều order.

## 11. Transaction và quyền sở hữu Connection

Các lời gọi procedure có thể đọc dữ liệu, ghi dữ liệu hoặc thực hiện cả hai. JDBC transaction được quản lý trên Connection.

Nếu autoCommit là true, driver có thể commit sau khi statement hoàn thành theo quy tắc JDBC. Với procedure có OUT REF CURSOR hoặc nhiều thao tác DML, nên chủ động quản lý transaction khi nghiệp vụ yêu cầu tính nguyên tử:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (CallableStatement cs = connection.prepareCall(
            "{ call app.process_order(?, ?) }")) {

        cs.setLong(1, 1001L);
        cs.registerOutParameter(2, Types.VARCHAR);
        cs.execute();

        String result = cs.getString(2);

        connection.commit();
    } catch (SQLException e) {
        connection.rollback();
        throw e;
    }
}
~~~

Một số nguyên tắc:

- Procedure thường không nên tự COMMIT nếu transaction thuộc quyền điều khiển của ứng dụng gọi.
- Nếu REF CURSOR cần được fetch, giữ Connection và statement còn mở cho đến khi đọc xong.
- Không trả ResultSet ra ngoài sau khi đã đóng Connection hoặc trả connection về pool.
- Khi dùng ARRAY hoặc STRUCT, quản lý vòng đời object và gọi free() với java.sql.Array khi hoàn tất.
- Với transaction có DML, chỉ commit sau khi đã xác định kết quả procedure và hoàn tất các bước nghiệp vụ cần thiết.

Nếu ứng dụng dùng connection pool, Connection lấy từ DataSource là handle được pool quản lý. Gọi close() trả connection về pool; không đóng trực tiếp underlying physical connection.

## 12. Quản lý tài nguyên và hiệu năng

REF CURSOR, ARRAY và object type có thể tạo ra lượng dữ liệu lớn. Cần thiết kế API và cách fetch phù hợp.

### REF CURSOR trả quá nhiều dòng

Một cursor có thể trả hàng triệu dòng. Nếu Java giữ toàn bộ kết quả trong một List, heap có thể tăng nhanh. Hãy xử lý theo từng dòng, giới hạn phạm vi bằng điều kiện lọc, phân trang hoặc chia batch.

Có thể điều chỉnh fetch size:

~~~java
cs.setFetchSize(500);
~~~

Hoặc trên ResultSet/Statement tùy cách gọi:

~~~java
rs.setFetchSize(500);
~~~

Fetch size là gợi ý cho driver về số dòng lấy mỗi lượt; nó không giới hạn tổng số dòng. Giá trị tối ưu phụ thuộc độ rộng row, network latency, memory và tốc độ xử lý. Không nên đặt fetch size rất lớn theo cảm tính.

### ARRAY quá lớn

Array.getArray() có thể tạo toàn bộ collection trong bộ nhớ Java. Với danh sách hàng trăm nghìn hoặc hàng triệu phần tử, cân nhắc batch nhỏ, staging table, global temporary table hoặc cơ chế load phù hợp thay vì truyền một collection khổng lồ trong một lần gọi.

### Object type nhiều thuộc tính

Object type có thể chứa object lồng nhau, collection, LOB hoặc thuộc tính lớn. Mapping sang Struct và Object[] có thể cần chuyển đổi nhiều đối tượng. Hãy chỉ trả những trường cần thiết; nếu dữ liệu chủ yếu là bảng phẳng, REF CURSOR với các cột scalar có thể dễ quản lý hơn.

### Round trip và kích thước payload

Một procedure nhận ARRAY có thể giảm số lần gọi database so với gọi procedure một lần cho từng phần tử. Tuy nhiên, payload quá lớn làm tăng network round trip, PGA/UGA usage, parsing hoặc chi phí xử lý SQL collection. Hãy đo theo kích thước batch và workload thực tế.

## 13. Xử lý lỗi JDBC và lỗi Oracle

Khi procedure thất bại, JDBC thường ném SQLException. Cần ghi nhận SQLState, vendor error code và thông tin message:

~~~java
try {
    cs.execute();
} catch (SQLException e) {
    System.err.println("SQLState: " + e.getSQLState());
    System.err.println("ErrorCode: " + e.getErrorCode());
    System.err.println("Message: " + e.getMessage());

    for (SQLException next = e.getNextException();
         next != null;
         next = next.getNextException()) {
        System.err.println("Next: " + next.getMessage());
    }

    throw e;
}
~~~

Một số lỗi thường gặp:

| Lỗi | Nguyên nhân có thể |
|---|---|
| ORA-06550 / PLS-00306 | Sai số lượng hoặc kiểu tham số khi gọi procedure/function |
| ORA-00932 | Kiểu dữ liệu truyền vào không tương thích |
| ORA-01008 | Thiếu bind variable |
| ORA-04043 | Tên object/type/package không tồn tại hoặc không nhìn thấy |
| ORA-06512 | Dòng PL/SQL trong stack trace, thường đi kèm lỗi gốc |
| ORA-17004 | Kiểu cột/tham số không hợp lệ trong thao tác JDBC |
| ORA-17059 | Không thể chuyển đổi dữ liệu theo kiểu driver yêu cầu |
| ORA-17071 | Dữ liệu hoặc thao tác vượt giới hạn của driver/kiểu dữ liệu trong trường hợp cụ thể |

Khi gặp lỗi liên quan REF CURSOR, kiểm tra kiểu đăng ký OUT, tên procedure, quyền EXECUTE và driver version. Với ARRAY/STRUCT, kiểm tra tên SQL type có đầy đủ schema, type đã được tạo ở cấp schema và tài khoản kết nối có quyền sử dụng type.

### Kiểm tra metadata của kiểu SQL

Có thể xem object type và collection type trong data dictionary:

~~~sql
SELECT owner,
       type_name,
       typecode
FROM   all_types
WHERE  owner = 'APP'
ORDER BY type_name;
~~~

Xem thuộc tính của object type:

~~~sql
SELECT owner,
       type_name,
       attr_no,
       attr_name,
       attr_type_name,
       length,
       precision,
       scale
FROM   all_type_attrs
WHERE  owner = 'APP'
ORDER BY type_name, attr_no;
~~~

Các view ALL_TYPES, ALL_TYPE_ATTRS, DBA_TYPES và DBA_TYPE_ATTRS giúp kiểm tra tên type, loại type và cấu trúc thuộc tính theo quyền truy cập.

## 14. Quyền cần thiết khi gọi API PL/SQL

Tài khoản Java kết nối vào Oracle phải có quyền thực thi package/procedure/function và quyền sử dụng các type liên quan.

Ví dụ cấp quyền:

~~~sql
GRANT EXECUTE ON app.order_api TO app_runtime;
GRANT EXECUTE ON app.customer_id_list_t TO app_runtime;
GRANT EXECUTE ON app.address_t TO app_runtime;
GRANT EXECUTE ON app.address_list_t TO app_runtime;
~~~

Nếu package/procedure truy cập bảng trong cùng schema, quyền của definer-rights package được áp dụng theo cơ chế PL/SQL. Nếu package dùng invoker rights (AUTHID CURRENT_USER), quyền thực thi cần được đánh giá theo quyền của caller.

Không nên cấp quyền trực tiếp trên mọi bảng cho ứng dụng nếu API package đã được thiết kế làm lớp truy cập dữ liệu. Cấp đúng quyền EXECUTE giúp thu hẹp bề mặt quyền và giữ logic nghiệp vụ ở database.

## 15. Lựa chọn kiểu trả dữ liệu phù hợp

Không phải lúc nào cũng cần dùng REF CURSOR, ARRAY và object type cùng lúc. Chọn cơ chế dựa trên hình dạng dữ liệu và hướng truyền:

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Trả một mã trạng thái, tổng tiền hoặc số lượng | OUT parameter scalar |
| Trả nhiều dòng truy vấn | REF CURSOR OUT |
| Truyền danh sách ID hoặc mã nghiệp vụ | SQL nested table/VARRAY qua ARRAY |
| Trả một cấu trúc gồm nhiều thuộc tính | SQL object type qua STRUCT hoặc SQLData |
| Truyền danh sách cấu trúc object | Collection SQL chứa object type |
| Trả nhiều tập kết quả độc lập | Nhiều REF CURSOR OUT |
| Kiểu chỉ tồn tại trong PL/SQL package | Wrapper SQL type hoặc API Oracle-specific tương ứng |

Nếu chỉ cần trả một tập dòng phẳng, REF CURSOR thường đơn giản hơn object type. Nếu cần truyền danh sách scalar, SQL collection thường gọn hơn việc tạo nhiều placeholder IN. Nếu cần truyền một record có cấu trúc rõ ràng và được tái sử dụng, SQL object type có thể phù hợp.

## 16. Quy trình triển khai Oracle JDBC với các kiểu dữ liệu phức hợp

1. **Thiết kế chữ ký PL/SQL.** Xác định tham số IN, OUT, IN OUT, cursor, collection và object type.
2. **Tạo SQL type ở schema.** Tạo object type, nested table hoặc VARRAY nếu Java cần truyền/nhận kiểu phức hợp.
3. **Tạo package/procedure/function.** Giữ chữ ký ổn định và quy định rõ transaction ownership.
4. **Cấp quyền.** Cấp EXECUTE trên package và type cho user ứng dụng.
5. **Chọn driver phù hợp.** Dùng Oracle JDBC driver tương thích JDK/database; xác nhận hỗ trợ REF_CURSOR, ARRAY và object mapping.
6. **Gọi bằng CallableStatement.** Bind IN, đăng ký OUT và thực thi đúng thứ tự tham số.
7. **Đọc kết quả đúng kiểu.** REF CURSOR thành ResultSet, ARRAY thành java.sql.Array, object thành Struct/SQLData.
8. **Quản lý transaction.** Giữ Connection mở trong lúc fetch, commit/rollback theo ranh giới nghiệp vụ.
9. **Đóng tài nguyên.** Đóng ResultSet, CallableStatement, Array và Connection bằng try-with-resources hoặc finally.
10. **Kiểm thử dữ liệu biên.** Thử NULL, collection rỗng, nhiều phần tử, không có dòng, dữ liệu lớn, lỗi PL/SQL và thay đổi schema type.

## 17. Nguyên tắc quan trọng

- CallableStatement là API JDBC để gọi procedure/function và đăng ký OUT parameter.
- OUT parameter cần registerOutParameter() trước khi execute; IN OUT cần cả set value và register type.
- REF CURSOR thường được đăng ký bằng OracleTypes.CURSOR hoặc Types.REF_CURSOR tùy driver, sau đó đọc dưới dạng ResultSet.
- REF CURSOR là cursor phía database; giữ Connection/Statement mở cho đến khi fetch xong.
- ARRAY trong Oracle JDBC cần SQL collection type ở cấp schema; dùng OracleConnection.createOracleArray() để tạo array.
- createOracleArray() nhận tên collection type, không phải tên kiểu phần tử.
- SQL object type được ánh xạ qua Struct, hoặc class triển khai SQLData/API Oracle.
- getAttributes() trả thuộc tính theo thứ tự khai báo của SQL object type.
- SQL nested table/VARRAY khác PL/SQL associative array; không dùng API SQL ARRAY cho mọi PL/SQL collection.
- Gọi Array.free() sau khi dùng và đóng ResultSet/Statement/Connection đúng thứ tự.
- Dùng BigDecimal cho Oracle NUMBER khi cần giữ độ chính xác.
- Kiểm tra quyền EXECUTE trên package và type, tên schema/type, driver version và transaction boundary khi xảy ra lỗi.

Oracle JDBC cung cấp cách trao đổi dữ liệu phong phú với PL/SQL. Khi hiểu đúng OUT parameter, REF CURSOR, ARRAY và object type, Java có thể gọi API database một cách rõ ràng, truyền danh sách hoặc cấu trúc dữ liệu hiệu quả và kiểm soát được transaction cùng tài nguyên kết nối.

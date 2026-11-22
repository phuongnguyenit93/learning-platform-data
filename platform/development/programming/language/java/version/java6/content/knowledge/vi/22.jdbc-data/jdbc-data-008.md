# Array, Struct và kiểu dữ liệu có cấu trúc trong JDBC

## 1. Tư duy đúng: SQL ARRAY/STRUCT không phải mảng Java hay record Java

Trong Java, một `String[]`, `int[]` hoặc `record Address(...)` là giá trị trong bộ nhớ ứng dụng. Trong cơ sở dữ liệu, một cột hoặc tham số có thể mang **SQL ARRAY** (tập phần tử có cùng kiểu SQL) hoặc **SQL structured type** (giá trị gồm nhiều thuộc tính theo một kiểu do database định nghĩa). JDBC cung cấp các interface để ánh xạ hai loại giá trị này, nhưng **sự tồn tại của interface JDBC không bảo đảm mọi database hỗ trợ cú pháp SQL hoặc factory tương ứng**.

- `java.sql.Array` là abstraction của **SQL ARRAY value**; không phải `java.lang.reflect.Array` và cũng không phải `java.util.ArrayList`.
- `java.sql.Struct` là abstraction của **SQL structured type value**; không phải Java `record`, `Map` hoặc đối tượng domain thông thường.
- `Connection.createArrayOf(elementSqlTypeName, elements)` là factory chuẩn để yêu cầu JDBC driver tạo SQL ARRAY nếu driver/DB hỗ trợ.
- `Connection.createStruct(sqlTypeName, attributes)` là factory chuẩn tạo giá trị của một SQL structured type đã được database nhận biết.
- `PreparedStatement.setArray(...)`, `setObject(...)` và `ResultSet.getArray(...)`/`getObject(...)` đưa các giá trị ấy qua ranh giới Java–SQL.
- `java.sql.SQLData`, `SQLInput` và `SQLOutput` cho phép custom mapping giữa SQL user-defined type (UDT) và class Java.

Bài học hướng tới **Java 17+**, dùng API JDBC hiện còn được hỗ trợ, phân biệt **contract chung** với **khả năng cụ thể của PostgreSQL, Oracle Database và các driver khác**. Một ví dụ tự chạy hoàn chỉnh sử dụng dynamic proxy để mô phỏng các interface JDBC mà không cần DB; một ví dụ tùy chọn khác cho pgJDBC minh họa cách kiểm thử array trên database thật.

### 1.1. Bản đồ các tầng ánh xạ

~~~text
Java application
  |
  +--> String[] / Integer[] / Java record / POJO
  |            |
  |            v
  +--> java.sql.Array / java.sql.Struct / SQLData
               |
               v
         JDBC driver
               |
               +--> SQL ARRAY parameter/column
               +--> SQL named structured type / object type
               +--> Vendor-specific collection/composite mapping
               |
               v
         Database schema / SQL dialect
~~~

**Không nhầm lẫn:** đoạn code `connection.createArrayOf("VARCHAR", ...)` chỉ hợp lệ nếu driver nhận và hiểu tên element type cùng kiểu ARRAY tương ứng; còn `connection.createStruct("APP.ADDRESS_T", ...)` chỉ hoạt động khi kiểu struct được DB/driver hỗ trợ và định nghĩa chính xác.

## 2. Các kiểu JDBC cần biết

| JDBC type / API | Ý nghĩa | Java representation | Ghi chú |
| --- | --- | --- | --- |
| `Types.ARRAY` / `JDBCType.ARRAY` | SQL array value | `java.sql.Array` | Các phần tử có base SQL type |
| `Types.STRUCT` / `JDBCType.STRUCT` | SQL structured type | `java.sql.Struct` | Các thuộc tính có thứ tự theo định nghĩa UDT |
| `Types.DISTINCT` | SQL distinct user-defined type | Custom `SQLData` hoặc mapping mặc định của driver | Không đồng nghĩa struct có nhiều thuộc tính |
| `Types.REF` | SQL reference tới giá trị structured UDT | `java.sql.Ref` | Không giống JDBC `ResultSet` |
| `Types.JAVA_OBJECT` | SQL value tương ứng Java object | `Object` hoặc type mapping driver | Hỗ trợ DB/driver tùy thuộc |
| `java.sql.SQLData` | Custom mapping class Java ↔ SQL UDT | Class implements `SQLData` | `readSQL/writeSQL` do driver sử dụng |
| `SQLInput` / `SQLOutput` | Luồng giá trị thuộc tính UDT | Giao diện JDBC | Đọc/ghi **đúng thứ tự** SQL attributes |

JDBC cũng có `Blob`, `Clob`, `NClob`, `SQLXML` và `RowId`, nhưng chúng có chức năng riêng, **không phải `STRUCT`**. Một cột JSON hay JSONB của DB có thể lưu object phức tạp, song **không mặc định là `java.sql.Struct`**.

### 2.1. SQL ARRAY không phải là một tập hàng của SELECT

Khi query trả nhiều rows, JDBC dùng `ResultSet`. Một SQL ARRAY là **một giá trị**, có thể nằm bên trong **một ô** của hàng kết quả hoặc là một SQL parameter. Bạn có thể biến nội dung Array thành `Object` biểu diễn Java array, hoặc lấy **ResultSet của các phần tử** bằng `Array.getResultSet()`; nhưng đây là hai cách đọc **cùng một SQL ARRAY value**, không phải một truy vấn nhiều hàng hoàn toàn độc lập.

### 2.2. STRUCT khác một tuple Java tiện dụng

Một SQL structured type có **tên kiểu ở phía DB** và **các thuộc tính theo đúng thứ tự định nghĩa SQL**. Dữ liệu Java như:

~~~text
name = "Ha Noi"
postcode = 10000
~~~

không đủ để tự dựng SQL Struct hợp lệ nếu DB chưa có type tương ứng (hoặc driver không hỗ trợ). Các thứ tự, tên SQL type, quyền truy cập schema, conversion và nested fields đều là một phần của contract.

## 3. API `java.sql.Array` trong Java hiện hành

`java.sql.Array` biểu diễn SQL ARRAY. Nó có thể giữ locator/reference tới dữ liệu database thay vì copy toàn bộ giá trị. JavaDoc yêu cầu giải phóng tài nguyên bằng `free()` sau khi dùng xong.

Các phương thức:

| API | Vai trò |
| --- | --- |
| `getBaseTypeName()` | Tên SQL type của phần tử, ví dụ `VARCHAR`/`text` theo driver |
| `getBaseType()` | Mã `java.sql.Types` của kiểu phần tử |
| `getArray()` | Materialize toàn bộ nội dung SQL ARRAY thành **`Object`** mang Java array |
| `getArray(Map<String,Class<?>>)` | Nhận type map cho phần tử UDT |
| `getArray(long index, int count)` | Lấy lát cắt theo **SQL index bắt đầu từ 1** |
| `getResultSet()` | Truy cập phần tử dưới dạng ResultSet hai cột: index và value |
| `getResultSet(long index, int count)` | Truy cập một khoảng phần tử qua ResultSet |
| `free()` | Giải phóng tài nguyên do SQL ARRAY giữ |

**Khác biệt phiên bản cần lưu ý:** Java 17 định nghĩa `Array` là interface với `free()`, **chưa** extends `AutoCloseable`; Java SE 26 hiện có `Array extends AutoCloseable` và `close()` mặc định. Muốn một ví dụ chạy ổn định trên **Java 17+**, hãy dùng `try/finally` với `array.free()`, **không** đặt `Array` vào `try-with-resources` trong source build với `--release 17`.

### 3.1. `getArray()` trả `Object`, không luôn là `Object[]`

Ví dụ:

~~~java
Object raw = sqlArray.getArray();
~~~

Đây là snippet, giả sử `sqlArray` là `java.sql.Array` còn hợp lệ. Với base type và driver cụ thể, `raw` có thể là `String[]`, `Integer[]`, mảng primitive hoặc representation được driver trả theo JDBC mapping.

**Không ép một cách vô điều kiện:**

~~~java
Object[] values = (Object[]) sqlArray.getArray();
~~~

Nếu driver trả `int[]`, cast trên gây `ClassCastException`. Hãy kiểm tra kiểu thực tế hoặc viết conversion theo một base SQL type đã kiểm chứng. Với driver biết chắc trả `String[]`, cast `(String[])` có thể hợp lệ; nếu không, xem Java reflection `java.lang.reflect.Array` hoặc converter có kiểm tra.

Một lời gọi khác:

~~~java
Object subset = sqlArray.getArray(2, 3);
~~~

lấy tối đa ba phần tử bắt đầu ở **SQL array position 2**. Chỉ số này là **1-based**, không phải index `1` của Java array; lưu ý với mảng chứa SQL NULL.

### 3.2. `Array.getResultSet()`: hai cột index và value

~~~java
try (ResultSet items = sqlArray.getResultSet()) {
    while (items.next()) {
        long position = items.getLong(1);
        Object value = items.getObject(2);
        // Dùng position và value theo mapping driver.
    }
}
~~~

Đây là snippet với `sqlArray` đã tạo; `ResultSet` là `AutoCloseable` và nên đóng đúng scope. Cột **1** chứa vị trí SQL ARRAY (theo contract JDBC bắt đầu từ 1), cột **2** chứa giá trị phần tử. `items.next()` là cách tiến cursor chuẩn.

Cách đọc này hữu ích với mảng lớn hoặc mảng phần tử UDT; tuy nhiên **không tự khẳng định driver streaming thực**. Một số implementation có thể materialize/buffer các phần tử phía client, nên cần benchmark driver thật nếu Array lớn.

### 3.3. Lifetime và giải phóng

~~~java
Array tags = connection.createArrayOf(
        "VARCHAR", new String[] {"java", "jdbc"});
try {
    // Truyền tags vào PreparedStatement hoặc đọc nó khi còn hợp lệ.
} finally {
    tags.free();
}
~~~

Đây là snippet minh họa; `createArrayOf("VARCHAR", ...)` không được bảo đảm hoạt động trên mọi database. Trong môi trường Java 17, `free()` được gọi rõ ràng, kể cả khi có `SQLException`.

Các lưu ý:

- Một SQL ARRAY thường có **transaction-duration lifetime/locator semantics**; đừng giữ reference lâu hơn transaction/connection.
- Nếu `getArray()` materialize một Java array độc lập, việc `free()` SQL Array không có nghĩa các Java values đã copy tự biến mất.
- Sau `free()`, tiếp tục truy cập object SQL Array có thể ném `SQLException`.
- Đọc array từ `ResultSet.getArray(...)` có thể tạo resource riêng cần free sau khi dùng.
- Khi bind với statement, đừng free object **trước** khi driver đã tiêu thụ parameter trong `executeUpdate()/executeQuery()`.

## 4. Tạo SQL ARRAY: `Connection.createArrayOf`

Signature:

~~~java
Array createArrayOf(String typeName, Object[] elements)
        throws SQLException;
~~~

`typeName` là **SQL tên kiểu của từng phần tử**, **không** phải tên Java component class, cũng không phải tên SQL ARRAY được đặt tùy ý. Ví dụ trên PostgreSQL với `text[]`:

~~~java
Array tags = connection.createArrayOf(
        "text", new String[] {"java", "jdbc", "sql"});
~~~

Đây là snippet cho driver/database hỗ trợ `createArrayOf("text", ...)`; PostgreSQL JDBC ghi rõ cách dùng này.

Với primitive values cần lưu ý: signature nhận `Object[]`, không nhận `int[]` vì primitive array **không phải Object[]**. Dùng wrapper arrays:

~~~java
Array ids = connection.createArrayOf(
        "integer", new Integer[] {10, 20, 30});
~~~

Đây là ví dụ theo tên SQL type PostgreSQL. Một số driver có extension cho primitive arrays hoặc hỗ trợ `setObject` trực tiếp với typed Java arrays, nhưng không nên áp nó thành contract chung của `Connection.createArrayOf`.

### 4.1. Phân biệt SQL array type với SQL element type

- PostgreSQL có syntax `text[]` và hàm chuẩn `createArrayOf("text", ...)` được pgJDBC hỗ trợ.
- Oracle Database dùng **named collection types** cho VARRAY/nested table và không hỗ trợ **anonymous SQL ARRAY** theo cách factory JDBC chuẩn mong đợi. Tài liệu Oracle JDBC hiện hành nói `Connection.createArrayOf(...)` có thể **ném lỗi**; thay vào đó dùng Oracle-specific `OracleConnection.createOracleArray(namedArrayType, elements)`.
- Một DB không hỗ trợ SQL ARRAY native có thể không hỗ trợ `createArrayOf(...)`. Với SQL Server, **table-valued parameters (TVP)** và relational child tables là giải pháp khác, **không tự đồng nhất với `java.sql.Array`**.

**Quy tắc portable:** viết code theo interface JDBC trong phần chung, nhưng có **DB-specific adapter** cho creation/binding khi cần, kèm integration tests. Không ép mọi driver vào cùng câu DDL hoặc cùng `typeName`.

## 5. Bind ARRAY an toàn với `PreparedStatement`

Khi đã có `Array` hợp lệ:

~~~java
String sql = "UPDATE articles SET tags = ? WHERE id = ?";
Array tags = connection.createArrayOf(
        "text", new String[] {"java", "jdbc"});
try {
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setArray(1, tags);
        ps.setLong(2, 42L);
        ps.executeUpdate();
    }
} finally {
    tags.free();
}
~~~

Đây là **snippet tích hợp**, giả sử có PostgreSQL table `articles(id, tags text[])`, JDBC driver và `Connection`. Parameter index của `PreparedStatement` bắt đầu **từ 1**. `setArray(1, tags)` là phương thức chuẩn, driver chuyển SQL Array value sang parameter tương ứng.

Ưu điểm của bind parameter:

- Không tự ghép chuỗi SQL chứa dấu ngoặc, quote, escape hoặc comma của từng phần tử.
- Giữ sự khác nhau giữa `NULL`, array rỗng và phần tử `NULL`.
- Giảm nguy cơ SQL injection từ dữ liệu người dùng.
- Để driver chịu trách nhiệm biểu diễn wire format và type mapping.

**Đừng thay thành** `ps.setString(1, "['java','jdbc']")` rồi hy vọng DB tự hiểu JSON/list text như SQL ARRAY. Nếu hệ thống cần JSON array, đó là một loại dữ liệu khác với contract khác.

### 5.1. SQL NULL, mảng rỗng và phần tử NULL

Ba giá trị khác nhau:

| Trường hợp | Ý nghĩa |
| --- | --- |
| SQL `NULL` ở cột `tags` | Không có một SQL ARRAY value |
| SQL `ARRAY[]` / array rỗng theo DB | Có SQL ARRAY nhưng không có phần tử |
| SQL ARRAY `[null]` | Có một phần tử, nhưng phần tử là SQL NULL |

Binding SQL NULL theo target type có thể dùng:

~~~java
ps.setNull(1, Types.ARRAY);
~~~

Đây là snippet (có `ps`), nhưng một số DB/driver với UDT/named array type có thể cần overload `setNull(index, sqlType, typeName)` để xác định rõ named type. Hành vi của `createArrayOf(type, new Object[0])` hoặc `createArrayOf(type, new Object[] {null})` cần kiểm thử với driver vì nó phải tạo đúng element type và preserve SQL NULL semantics.

Không suy luận rằng `getArray() == null` nghĩa là array rỗng: `ResultSet.getArray(...)` trả **null khi cột là SQL NULL**; còn Array rỗng trả một object `Array` hợp lệ theo driver.

## 6. Đọc Array từ `ResultSet`

Giả sử DB có cột ARRAY:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT tags FROM articles WHERE id = ?")) {
    ps.setLong(1, 42L);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            Array tags = rs.getArray("tags");
            if (tags != null) {
                try {
                    Object rawElements = tags.getArray();
                    // Chuyển kiểu an toàn dựa trên base SQL type/driver.
                } finally {
                    tags.free();
                }
            }
        }
    }
}
~~~

Đây là snippet tích hợp với bảng/driver cụ thể. **Getter trả null cho SQL NULL**. Các JDBC objects nên được sử dụng trong khi `ResultSet` và transaction còn hợp lệ.

Nếu thay vì materialize toàn bộ, cần iterate:

~~~java
Array tags = rs.getArray("tags");
if (tags != null) {
    try {
        try (ResultSet elements = tags.getResultSet()) {
            while (elements.next()) {
                long sqlIndex = elements.getLong(1);
                Object element = elements.getObject(2);
                // Xử lý một phần tử tại một thời điểm.
            }
        }
    } finally {
        tags.free();
    }
}
~~~

Đây là snippet trong scope đang có `ResultSet rs` ở row hợp lệ. Lưu ý **ResultSet ở đây là resultset các phần tử**, không phải resultset của query gốc. `getArray(index,count)` hoặc `getResultSet(index,count)` có thể phục vụ partial access khi driver hỗ trợ đúng semantics.

### 6.1. Array của các SQL structured types

Nếu base SQL type là một UDT (ví dụ `APP.ADDRESS_T`), các phần tử của `Array` có thể cần custom mapping:

~~~java
Map<String, Class<?>> map = connection.getTypeMap();
map.put("APP.ADDRESS_T", AddressValue.class);
connection.setTypeMap(map);
Object raw = sqlArray.getArray(map);
~~~

Đây là snippet với `AddressValue` là class triển khai `SQLData` hợp lệ và `APP.ADDRESS_T` là tên SQL type của database. `getArray(map)` cho phép driver chuyển element UDT thành Java class theo mapping. Hãy xem driver có hỗ trợ array-of-UDT và custom type map hay không; nhiều DBMS và JDBC drivers không triển khai toàn bộ tính năng này.

**Tránh sửa connection type map đang được nhiều luồng dùng chung.** Nếu là connection từ pool, quản lý scope và reset cấu hình trước khi trả connection cho pool, theo contract của pool.

## 7. `java.sql.Struct`: giá trị SQL có các thuộc tính theo thứ tự

`Struct` mô tả một giá trị của SQL structured type (thường là UDT được định nghĩa bằng `CREATE TYPE`). Nó không có getter tên thuộc tính như `getCity()` hoặc `getPostalCode()`; interface chuẩn có:

~~~java
String getSQLTypeName() throws SQLException;
Object[] getAttributes() throws SQLException;
Object[] getAttributes(Map<String, Class<?>> map)
        throws SQLException;
~~~

**Lưu ý:**

- `getSQLTypeName()` là SQL type name, thường qualified theo schema.
- `getAttributes()` trả các giá trị **theo đúng thứ tự thuộc tính SQL type**, không theo thứ tự các field Java tự suy đoán.
- `getAttributes(map)` áp type map khi các thuộc tính chứa UDT lồng nhau.
- Giá trị attribute có thể là `null`, các scalar types Java, `Struct`, `Array` hoặc mapping vendor-specific.
- `Struct` **không có `free()`** trong interface chuẩn (khác `Array`); nhưng giá trị lồng bên trong hoặc connection/transaction có lifecycle riêng.

### 7.1. Named SQL type và vị trí thuộc tính

Nếu database hỗ trợ một kiểu:

~~~sql
CREATE TYPE ADDRESS_T AS OBJECT (
    city VARCHAR2(100),
    postal_code NUMBER(10)
);
~~~

Đây là **DDL minh họa Oracle Database**, không phải SQL portable. Khi tạo struct với attributes:

~~~java
Struct address = connection.createStruct(
        "ADDRESS_T", new Object[] {"Ha Noi", 10000});
~~~

đầu tiên là `city`, sau đó `postal_code`. Nếu đổi thứ tự thành `{10000, "Ha Noi"}`, DB/driver có thể báo lỗi type conversion hoặc tạo giá trị sai; ứng dụng không thể dựa vào Java reflection để sắp xếp các thuộc tính thay vì schema.

**Không coi type name là tùy ý.** Trong DB thật, cần chú ý schema, quyền `EXECUTE`/usage trên type và cách driver chuẩn hóa tên/case. `createStruct` có thể ném `SQLFeatureNotSupportedException` khi không được hỗ trợ.

### 7.2. Lấy Struct từ `ResultSet.getObject`

Với một cột chứa SQL structured UDT và chưa có custom mapping:

~~~java
Object value = rs.getObject("address");
if (value instanceof Struct address) {
    System.out.println(address.getSQLTypeName());
    Object[] attributes = address.getAttributes();
    // Convert theo contract đã kiểm thử.
}
~~~

Đây là snippet khi `ResultSet rs` đang ở một row. **Driver có thể dùng mapping vendor-specific thay vì trả `Struct`** tùy UDT và cấu hình type map. Hãy xem metadata và test trên driver thật. Dùng `instanceof` và xác minh type name trước khi cast attributes.

SQL NULL có thể trả `null`, khác với một Struct hợp lệ có thuộc tính null.

### 7.3. Binding Struct và `setObject`

~~~java
Struct address = connection.createStruct(
        "APP.ADDRESS_T", new Object[] {"Ha Noi", 10000});

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customers(id, address) VALUES (?, ?)")) {
    ps.setLong(1, 42L);
    ps.setObject(2, address);
    ps.executeUpdate();
}
~~~

Đây là snippet tích hợp: **bảng và UDT là giả định**, phải đổi theo vendor/schema thật. Theo JDBC contract, `PreparedStatement.setObject(...)` có thể nhận object triển khai `Struct`; driver phải chuyển tới SQL type tương ứng nếu hỗ trợ. Một driver có thể yêu cầu overload có `targetSqlType` hay API vendor-specific trong hoàn cảnh đặc thù.

Không truyền thẳng Java `record Address(String city, int postal)` vào `setObject` rồi giả định driver tự biến thành SQL UDT. Muốn custom Java class mapping, cần `SQLData`, driver extension hoặc serializer có contract rõ ràng.

## 8. `SQLData`: ánh xạ UDT thành Java class có ý nghĩa

`java.sql.SQLData` là interface chuẩn cho **custom mapping** của SQL UDT. Nó định nghĩa:

~~~java
String getSQLTypeName() throws SQLException;
void readSQL(SQLInput stream, String typeName) throws SQLException;
void writeSQL(SQLOutput stream) throws SQLException;
~~~

Một class Java có thể có fields `city` và `postalCode` tương ứng attributes SQL. Khi driver map một UDT sang Java class, nó gọi `readSQL` và cấp `SQLInput`. Khi Java object được bind trở lại DB, driver dùng `writeSQL` và `SQLOutput`.

### 8.1. Thứ tự đọc/ghi phải khớp schema

Giả sử SQL type `APP.ADDRESS_T` định nghĩa lần lượt:

1. `city VARCHAR(...)`.
2. `postal_code INTEGER`.

Một implementation đơn giản:

~~~java
public final class AddressValue implements SQLData {
    private String city;
    private int postalCode;

    public AddressValue() {}

    @Override
    public String getSQLTypeName() {
        return "APP.ADDRESS_T";
    }

    @Override
    public void readSQL(SQLInput in, String typeName)
            throws SQLException {
        city = in.readString();
        postalCode = in.readInt();
    }

    @Override
    public void writeSQL(SQLOutput out) throws SQLException {
        out.writeString(city);
        out.writeInt(postalCode);
    }
}
~~~

Đây là **snippet class minh họa**, cần import `java.sql.SQLData`, `SQLInput`, `SQLOutput`, `SQLException`. Chưa có DB/UDT hoặc getters/constructor convenience ở snippet này, nên ví dụ độc lập đầy đủ nằm ở mục 10.

Những điểm rất dễ sai:

- `readSQL` phải gọi `readString` trước `readInt` **nếu đó là thứ tự SQL attributes**.
- `writeSQL` phải ghi theo **cùng thứ tự SQL schema**, không theo thứ tự field tùy hứng.
- Nếu thuộc tính số có thể là SQL NULL, `readInt` trả `0` và gọi `in.wasNull()` ngay sau đó để phân biệt NULL với 0; dùng `Integer` nếu cần preserve NULL.
- Với SQL nested UDT, type maps/`readObject`/`readArray` có thể phức tạp; đừng tự cast nếu chưa kiểm tra mapping.
- JDBC driver mong đợi class mapped có constructor không tham số có thể truy cập theo contract provider.
- Khi schema UDT thay đổi thứ tự/kiểu attributes, mapping Java cũng phải được cập nhật và kiểm thử.

### 8.2. Thiết lập connection type map

~~~java
Map<String, Class<?>> types =
        new HashMap<>(connection.getTypeMap());
types.put("APP.ADDRESS_T", AddressValue.class);
connection.setTypeMap(types);
~~~

Đây là snippet, cần import `java.util.Map` và `java.util.HashMap` và class `AddressValue`. Tên SQL UDT thường cần **qualified chính xác**. Connection có type map chứa những mapping ứng dụng đã cài; `setTypeMap` có thể không được driver hỗ trợ đầy đủ. Nếu dùng connection pool, đừng để một request làm thay đổi mapping và làm ảnh hưởng request sau.

Với type map được cấu hình đúng, `ResultSet.getObject(...)` có thể trả `AddressValue` thay cho generic `Struct`. Một số overload getter nhận map trực tiếp:

~~~java
Object mapped = rs.getObject("address", types);
~~~

Đây là snippet trong `ResultSet rs`; driver không nhất thiết hỗ trợ mọi dạng UDT, nhưng đây là API chuẩn cần biết.

### 8.3. Tại sao `SQLInput/SQLOutput` không nên gọi thủ công trong app bình thường?

Theo JavaDoc, `SQLInput` và `SQLOutput` là những luồng dữ liệu mà **JDBC driver** cấp/phân phối khi thực hiện custom mapping. Code nghiệp vụ thường gọi `getObject` và `setObject`, không tự tạo các luồng ấy.

Trong ví dụ tự chạy ở mục 10, chúng ta dùng `javax.sql.rowset.serial.SQLInputImpl` và `SQLOutputImpl` để **minh họa mapping thuần trong bộ nhớ**. Đó là **test fixture**, không phải một driver; việc tạo các đối tượng này thủ công **không chứng minh** DB đã có SQL UDT tương ứng.

## 9. DBMS-specific: tính khả chuyển cần hiểu rõ

### 9.1. PostgreSQL và pgJDBC

PostgreSQL có array types thực sự, ví dụ `text[]`, `integer[]`, và pgJDBC chính thức tài liệu hóa:

~~~java
Array tags = connection.createArrayOf(
        "text", new String[] {"java", "sql"});
~~~

`PreparedStatement.setArray` và `ResultSet.getArray` là đường đi phổ biến với PostgreSQL JDBC.

PostgreSQL cũng có **composite types**, nhưng **không mặc định driver chuyển chúng qua `Connection.createStruct/getAttributes` như Oracle named object types**. Theo implementation pgJDBC, custom `Connection.setTypeMap` cho UDT mapping có những giới hạn không được triển khai như SQLData mapping nói chung. Hãy kiểm tra driver/version cụ thể; một composite value có thể được trả như object đặc thù pgJDBC (`PGobject`) hoặc kiểu text representation.

**Không giả định** rằng “PostgreSQL có `CREATE TYPE ... AS (...)` nên `createStruct` Java sẽ tự hoạt động”. Đây là hai hợp đồng khác nhau: khả năng DB và mapping JDBC driver.

Một schema PostgreSQL hợp lệ để thử array:

~~~sql
CREATE TABLE article_tags (
    id BIGINT PRIMARY KEY,
    tags TEXT[] NOT NULL
);
~~~

Đối với composite type của PostgreSQL:

~~~sql
CREATE TYPE address_t AS (
    city TEXT,
    postal_code INTEGER
);
~~~

Đây là PostgreSQL DDL minh họa; nếu dùng composite type trong cột, driver mapping cần được kiểm chứng riêng thay vì copy snippet `createStruct` từ Oracle.

### 9.2. Oracle Database: named object và named collections

Oracle Database hỗ trợ SQL object types và collections như VARRAY/nested table. Ví dụ:

~~~sql
CREATE TYPE ADDRESS_T AS OBJECT (
    CITY VARCHAR2(100),
    POSTAL_CODE NUMBER(10)
);
/

CREATE TYPE TAG_LIST_T AS VARRAY(20) OF VARCHAR2(100);
/
~~~

Đây là SQL/SQL*Plus-style DDL minh họa cho Oracle, không thể chạy nguyên văn trên PostgreSQL/SQL Server.

Đối với **named Oracle array type**, tài liệu Oracle JDBC hiện hành nói **`Connection.createArrayOf(...)` không phù hợp** vì SQL array loại này có tên, không phải anonymous array do method JDBC chuẩn tạo. Hướng phù hợp là Oracle-specific factory:

~~~java
oracle.jdbc.OracleConnection oracle =
        connection.unwrap(oracle.jdbc.OracleConnection.class);
Array tags = oracle.createOracleArray(
        "TAG_LIST_T", new String[] {"java", "jdbc"});
~~~

Đây là snippet **phụ thuộc Oracle JDBC driver JAR và Oracle SQL type đã tạo**, không thuộc demo Java SE thuần. `createOracleArray` nhận **tên SQL collection type**, còn `createArrayOf` nhận **tên element type** — khác biệt đó rất quan trọng. Không dùng các class `oracle.sql.ARRAY` deprecated/old constructors làm lựa chọn mặc định cho code mới.

Oracle JDBC cũng có standard `Struct`/custom SQLData mapping và các extension riêng; nên ưu tiên dùng interface `java.sql.Struct` khi được driver hỗ trợ rồi dùng extension Oracle có kiểm soát cho trường hợp factory chuẩn không đủ.

### 9.3. SQL Server và những DB không có SQL ARRAY tiêu chuẩn

Một số DBMS dùng:

- Relational child table kết hợp foreign key cho quan hệ một-nhiều.
- JSON/JSONB cho dữ liệu bán cấu trúc khi schema/engine phù hợp.
- Table-valued parameters (TVP) theo API vendor-specific.
- User-defined table/record types trong stored procedures.

Những công nghệ này có thể đáp ứng bài toán “nhiều giá trị” nhưng **không phải tất cả đều map vào `java.sql.Array` hoặc `Struct`**. Không dùng `setArray` cho TVP của SQL Server nếu driver yêu cầu `SQLServerDataTable`/`setStructured` hoặc API vendor-specific khác.

Tính khả chuyển trong dự án thật thường đến từ **adapter/repository interface** có implementation riêng cho từng DBMS, không chỉ từ việc không import class vendor trong toàn bộ code.

## 10. Ví dụ Java 17+ hoàn chỉnh: Array, Struct và SQLData (không cần database)

### 10.1. Phạm vi và tính trung thực của demo

JDK có JDBC interface nhưng **không kèm mọi database server/driver**. Để bạn có thể chạy thử ngay trên Java 17+, chương trình `JdbcStructuredDemo.java` bên dưới dùng dynamic proxies làm **in-memory test double**:

1. Proxy `Connection` trả về `Array`/`Struct` mô phỏng khi gọi `createArrayOf`/`createStruct`.
2. `DemoArray` implement `Array`, hỗ trợ `getBaseTypeName`, `getArray`, slicing, `getResultSet` và `free`.
3. `DemoStruct` implement `Struct` và trả attributes theo thứ tự.
4. Proxy `PreparedStatement` ghi nhận `setArray` và `setObject`; **không gửi SQL**.
5. `AddressValue implements SQLData` đọc và ghi thông qua rowset serial helpers `SQLInputImpl`/`SQLOutputImpl`.
6. Mọi phép kiểm tra có stdout xác định được và không cần dependency ngoài Java SE.

**Đây là unit/demo test của cách dùng API, KHÔNG PHẢI JDBC driver có khả năng thực thi truy vấn.** Các proxy chỉ implement những method dùng trong bài, các method khác ném `SQLFeatureNotSupportedException`. `Array.getResultSet` cũng chỉ là ResultSet mô phỏng trong memory.

### 10.2. Source đầy đủ: `JdbcStructuredDemo.java`

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLData;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLInput;
import java.sql.SQLOutput;
import java.sql.Struct;
import java.sql.Types;
import java.util.Arrays;
import java.util.Map;
import java.util.Vector;
import javax.sql.rowset.serial.SQLInputImpl;
import javax.sql.rowset.serial.SQLOutputImpl;

public class JdbcStructuredDemo {
    static final class DemoArray implements Array {
        private final String baseName;
        private final Object[] values;
        private boolean freed;

        DemoArray(String baseName, Object[] values) {
            this.baseName = baseName;
            this.values = values.clone();
        }

        private void ensureOpen() throws SQLException {
            if (freed) throw new SQLException("Array is freed");
        }

        @Override public String getBaseTypeName() throws SQLException {
            ensureOpen();
            return baseName;
        }

        @Override public int getBaseType() throws SQLException {
            ensureOpen();
            return Types.VARCHAR;
        }

        @Override public Object getArray() throws SQLException {
            ensureOpen();
            return values.clone();
        }

        @Override public Object getArray(Map<String, Class<?>> map)
                throws SQLException {
            return getArray();
        }

        @Override public Object getArray(long index, int count)
                throws SQLException {
            ensureOpen();
            if (index < 1 || count < 0 || index > values.length + 1L
                    || count > values.length - (index - 1L)) {
                throw new SQLException("Invalid SQL array slice");
            }
            int start = (int) index - 1;
            return Arrays.copyOfRange(values, start, start + count);
        }

        @Override public Object getArray(long index, int count,
                Map<String, Class<?>> map) throws SQLException {
            return getArray(index, count);
        }

        private ResultSet rows(long index, int count) throws SQLException {
            Object[] selected = (Object[]) getArray(index, count);
            long[] position = {-1L};
            boolean[] closed = {false};
            InvocationHandler handler = (proxy, method, args) -> {
                if ("close".equals(method.getName())) {
                    closed[0] = true;
                    return null;
                }
                if ("isClosed".equals(method.getName())) return closed[0];
                if (closed[0]) throw new SQLException("ResultSet closed");
                return switch (method.getName()) {
                    case "next" -> ++position[0] < selected.length;
                    case "getLong" -> index + position[0];
                    case "getObject" -> selected[(int) position[0]];
                    default -> throw new SQLFeatureNotSupportedException(
                            method.getName());
                };
            };
            return (ResultSet) Proxy.newProxyInstance(
                    ResultSet.class.getClassLoader(),
                    new Class<?>[] {ResultSet.class}, handler);
        }

        @Override public ResultSet getResultSet() throws SQLException {
            return rows(1, values.length);
        }

        @Override public ResultSet getResultSet(
                Map<String, Class<?>> map) throws SQLException {
            return getResultSet();
        }

        @Override public ResultSet getResultSet(long index, int count)
                throws SQLException {
            return rows(index, count);
        }

        @Override public ResultSet getResultSet(long index, int count,
                Map<String, Class<?>> map) throws SQLException {
            return rows(index, count);
        }

        @Override public void free() {
            freed = true;
        }
    }

    static final class DemoStruct implements Struct {
        private final String typeName;
        private final Object[] attributes;

        DemoStruct(String typeName, Object[] attributes) {
            this.typeName = typeName;
            this.attributes = attributes.clone();
        }

        @Override public String getSQLTypeName() {
            return typeName;
        }

        @Override public Object[] getAttributes() {
            return attributes.clone();
        }

        @Override public Object[] getAttributes(
                Map<String, Class<?>> map) {
            return getAttributes();
        }
    }

    static final class AddressValue implements SQLData {
        String city;
        int code;

        AddressValue() {}

        @Override public String getSQLTypeName() {
            return "DEMO.ADDRESS_T";
        }

        @Override public void readSQL(SQLInput stream, String typeName)
                throws SQLException {
            if (!getSQLTypeName().equals(typeName)) {
                throw new SQLException("Unexpected SQL type: " + typeName);
            }
            city = stream.readString();
            code = stream.readInt();
        }

        @Override public void writeSQL(SQLOutput stream)
                throws SQLException {
            stream.writeString(city);
            stream.writeInt(code);
        }
    }

    static Connection connection() {
        boolean[] closed = {false};
        InvocationHandler handler = (proxy, method, args) -> {
            if ("close".equals(method.getName())) {
                closed[0] = true;
                return null;
            }
            if ("isClosed".equals(method.getName())) return closed[0];
            if (closed[0]) throw new SQLException("Connection closed");
            return switch (method.getName()) {
                case "createArrayOf" -> new DemoArray(
                        (String) args[0], (Object[]) args[1]);
                case "createStruct" -> new DemoStruct(
                        (String) args[0], (Object[]) args[1]);
                default -> throw new SQLFeatureNotSupportedException(
                        method.getName());
            };
        };
        return (Connection) Proxy.newProxyInstance(
                Connection.class.getClassLoader(),
                new Class<?>[] {Connection.class}, handler);
    }

    static PreparedStatement statement(Object[] bound) {
        InvocationHandler handler = (proxy, method, args) -> {
            return switch (method.getName()) {
                case "setArray", "setObject" -> {
                    bound[(Integer) args[0] - 1] = args[1];
                    yield null;
                }
                case "close" -> null;
                default -> throw new SQLFeatureNotSupportedException(
                        method.getName());
            };
        };
        return (PreparedStatement) Proxy.newProxyInstance(
                PreparedStatement.class.getClassLoader(),
                new Class<?>[] {PreparedStatement.class}, handler);
    }

    public static void main(String[] args) throws Exception {
        try (Connection db = connection()) {
            Array tags = db.createArrayOf(
                    "VARCHAR", new String[] {"alpha", "beta", "gamma"});
            try {
                System.out.println("Array base type: " + tags.getBaseTypeName()
                        + "/" + tags.getBaseType());
                System.out.println("Array values: "
                        + Arrays.toString((Object[]) tags.getArray()));
                System.out.println("Array slice (SQL index 2): "
                        + Arrays.toString((Object[]) tags.getArray(2, 2)));

                StringBuilder items = new StringBuilder();
                try (ResultSet rows = tags.getResultSet()) {
                    while (rows.next()) {
                        if (items.length() > 0) items.append(", ");
                        items.append(rows.getLong(1)).append("=")
                                .append(rows.getObject(2));
                    }
                }
                System.out.println("Array ResultSet: " + items);

                Struct address = db.createStruct("DEMO.ADDRESS_T",
                        new Object[] {"Ha Noi", 10000});
                System.out.println("Struct type: "
                        + address.getSQLTypeName());
                Object[] attrs = address.getAttributes();
                System.out.println("Struct attributes: "
                        + Arrays.toString(attrs));

                Object[] bound = new Object[2];
                try (PreparedStatement ps = statement(bound)) {
                    ps.setArray(1, tags);
                    ps.setObject(2, address);
                }
                System.out.println("Bound JDBC types: "
                        + (bound[0] instanceof Array) + ","
                        + (bound[1] instanceof Struct));

                AddressValue value = new AddressValue();
                value.readSQL(new SQLInputImpl(
                        new Object[] {"Da Nang", 550000}, Map.of()),
                        "DEMO.ADDRESS_T");
                System.out.println("SQLData read: "
                        + value.city + "/" + value.code);
                Vector<Object> out = new Vector<>();
                value.writeSQL(new SQLOutputImpl(out, Map.of()));
                System.out.println("SQLData write: " + out);
                System.out.println("SQLData mapping: "
                        + Map.of("DEMO.ADDRESS_T", AddressValue.class)
                                .containsKey(value.getSQLTypeName()));
            } finally {
                tags.free();
            }
            try {
                Array invalid = db.createArrayOf(
                        "VARCHAR", new String[] {"x"});
                invalid.free();
                invalid.getArray();
                throw new AssertionError("Freed array should fail");
            } catch (SQLException expected) {
                System.out.println("Freed Array rejected: true");
            }
            System.out.println("Fake driver calls only: true");
        }
    }
}
~~~

**Các chi tiết cần hiểu trước khi áp dụng sang driver thật:**

- `DemoArray.getBaseType()` cố định `Types.VARCHAR` vì fixture chỉ hỗ trợ string array. Một driver thật phải trả đúng base type theo SQL schema.
- `DemoArray.getArray()` trả clone của mảng để mô phỏng việc materialize. Nó không đọc DB.
- `getArray(2,2)` lấy phần tử thứ hai và thứ ba, minh họa chỉ số SQL 1-based.
- Proxy ResultSet trả index ở cột 1 và value ở cột 2; method khác bị từ chối để không giả lập hành vi JDBC chưa viết.
- `DemoStruct` giữ SQL type name và attributes theo thứ tự, không truy vấn schema.
- Proxy PreparedStatement chỉ ghi nhận `setArray`/`setObject`, **không gọi execute** và không thực hiện transaction.
- `AddressValue` dùng `SQLInputImpl`/`SQLOutputImpl` từ module `java.sql.rowset` trong bộ JDK. Đây là công cụ mô phỏng mapping in-memory; driver thật sẽ tạo `SQLInput/SQLOutput` của riêng nó.
- `Array.free()` được gọi trong `finally`. `Array` không phải `AutoCloseable` khi build `--release 17`.
- `AddressValue.readSQL/writeSQL` dùng đúng thứ tự **city trước code**.

### 10.3. Biên dịch và chạy

Lưu source ở file **`JdbcStructuredDemo.java`** rồi chạy:

~~~sh
javac --release 17 JdbcStructuredDemo.java
java JdbcStructuredDemo
~~~

Đây là **chương trình độc lập** chỉ cần JDK 17+, không cần JDBC driver JAR hay database. `SQLInputImpl` và `SQLOutputImpl` thuộc module JDK `java.sql.rowset`.

**Stdout chính xác** đã kiểm thử trên JDK 24 bằng `javac --release 17`:

~~~text
Array base type: VARCHAR/12
Array values: [alpha, beta, gamma]
Array slice (SQL index 2): [beta, gamma]
Array ResultSet: 1=alpha, 2=beta, 3=gamma
Struct type: DEMO.ADDRESS_T
Struct attributes: [Ha Noi, 10000]
Bound JDBC types: true,true
SQLData read: Da Nang/550000
SQLData write: [Da Nang, 550000]
SQLData mapping: true
Freed Array rejected: true
Fake driver calls only: true
~~~

Đặc biệt, `Array base type: VARCHAR/12` là kết quả do **test double** trả về, trong đó `Types.VARCHAR == 12`; không có SQL catalog metadata nào được đọc từ database. `Freed Array rejected: true` mô phỏng một `SQLException` khi truy cập Array đã free.

### 10.4. Từ demo đến implementation thật

Khi có driver thật:

- **Bỏ** toàn bộ các class/proxy `DemoArray`, `DemoStruct`, `connection()`, `statement()`.
- Lấy `Connection` từ `DataSource`/pool hoặc `DriverManager`.
- Gọi các phương thức factory trên connection thật theo vendor support.
- Dùng `PreparedStatement` thực để execute SQL, và `ResultSet` thực để đọc.
- Test transaction/rollback, nullable attributes và array elements, resource lifetimes, SQL type names và exception semantics.

Không đưa dynamic proxies ở demo vào production; chúng không có data integrity, schema validation hay network I/O.

## 11. Ví dụ tích hợp PostgreSQL: Array thật qua pgJDBC

### 11.1. Chuẩn bị môi trường

Để chạy với PostgreSQL:

- PostgreSQL server có thể truy cập.
- Một database và tài khoản có quyền thực thi `SELECT`.
- PostgreSQL JDBC driver JAR phù hợp JDK 17+ nằm trong classpath.
- `JDBC_URL`, `JDBC_USER` và `JDBC_PASSWORD` theo môi trường của bạn.

Ví dụ JDBC URL:

~~~text
jdbc:postgresql://localhost:5432/appdb
~~~

Đây là **ví dụ cấu trúc URL**, không phải server có sẵn trong bài. Không ghi credentials vào source.

### 11.2. Chương trình `PgArrayLiveProbe.java`

~~~java
import java.sql.Array;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.Properties;

public class PgArrayLiveProbe {
    public static void main(String[] args) throws SQLException {
        String url = System.getenv("JDBC_URL");
        if (url == null || url.isBlank()) {
            System.out.println(
                    "Set JDBC_URL and install a PostgreSQL JDBC driver.");
            return;
        }
        Properties props = new Properties();
        String user = System.getenv("JDBC_USER");
        String password = System.getenv("JDBC_PASSWORD");
        if (user != null) props.setProperty("user", user);
        if (password != null) props.setProperty("password", password);

        try (Connection connection =
                     DriverManager.getConnection(url, props)) {
            Array tags = connection.createArrayOf(
                    "text", new String[] {"java", "jdbc", "sql"});
            try {
                try (PreparedStatement ps = connection.prepareStatement(
                        "SELECT ?::text[] AS tags")) {
                    ps.setArray(1, tags);
                    try (ResultSet rs = ps.executeQuery()) {
                        if (rs.next()) {
                            Array result = rs.getArray("tags");
                            if (result != null) {
                                try {
                                    System.out.println(Arrays.toString(
                                            (Object[]) result.getArray()));
                                } finally {
                                    result.free();
                                }
                            }
                        }
                    }
                }
            } finally {
                tags.free();
            }
        }
    }
}
~~~

**Kiểm tra tính nhất quán của code:**

- `createArrayOf("text", ...)` dùng base SQL element type PostgreSQL, không phải `"text[]"`.
- SQL `?::text[]` là PostgreSQL cast syntax, không portable qua Oracle hoặc SQL Server.
- `PreparedStatement.setArray(1, tags)` truyền tham số hóa, không ghép literal chứa user input.
- `rs.getArray("tags")` trả `Array` hoặc null; giá trị trả được free sau khi materialize.
- `tags.free()` chạy sau khi PreparedStatement hoàn tất.
- `Array.getArray()` có thể trả kiểu khác tùy driver/SQL type. Trong ví dụ pgJDBC với `text[]` cần kiểm thử cast `Object[]` trên đúng version driver.
- `try-with-resources` đóng statement/resultset/connection, còn `Array` dùng `free` cho Java 17.

### 11.3. Lệnh biên dịch và chạy

`javac` chỉ cần API Java SE:

~~~sh
javac --release 17 PgArrayLiveProbe.java
~~~

Đã biên dịch thành công trên JDK 24. Khi **chưa có `JDBC_URL`**, chạy:

~~~sh
java PgArrayLiveProbe
~~~

In ra **stdout chính xác**:

~~~text
Set JDBC_URL and install a PostgreSQL JDBC driver.
~~~

Nhánh phòng vệ này đã được chạy thành công; **chưa thực thi SQL/database thật** vì không được cung cấp server/driver/credentials.

Khi được cung cấp PostgreSQL JDBC driver JAR, ví dụ chạy trên Linux/macOS (đường dẫn driver phải thay bằng file thực):

~~~sh
java -cp ".:/path/to/postgresql.jar" PgArrayLiveProbe
~~~

Trên Windows dùng dấu `;` để phân cách classpath:

~~~text
java -cp ".;C:\drivers\postgresql.jar" PgArrayLiveProbe
~~~

Nếu DB/driver đáp ứng đúng ví dụ, dòng kết quả mong đợi:

~~~text
[java, jdbc, sql]
~~~

Đây là **kết quả dự kiến có điều kiện**, không tuyên bố đã kiểm chứng bằng PostgreSQL thật. Nếu không có driver, `DriverManager.getConnection` có thể ném `SQLException` với lỗi không tìm thấy driver phù hợp.

## 12. Kỹ thuật thiết kế schema: khi nào nên dùng ARRAY hoặc STRUCT?

### 12.1. ARRAY phù hợp khi nào?

Một cột ARRAY có thể có ích khi:

- Danh sách nhỏ có số phần tử vừa phải và **thường được đọc/ghi cùng hàng**.
- Dữ liệu có kiểu đồng nhất và DB cung cấp array operators/indexing phù hợp.
- Một số tham số của function/procedure cần truyền nhiều giá trị dưới dạng array.
- Dữ liệu telemetry, tags hoặc tính toán có SQL array native hỗ trợ tốt.

Nhưng một bảng child nhiều hàng vẫn có thể phù hợp hơn nếu:

- Cần index/search/foreign key cho **từng phần tử**.
- Cần đảm bảo uniqueness/constraints trên từng phần tử.
- Số phần tử có thể tăng mạnh, cần pagination và cập nhật từng item.
- Ứng dụng cần portable giữa nhiều DBMS không cùng hỗ trợ ARRAY.

### 12.2. STRUCT phù hợp khi nào?

Structured type hữu ích khi:

- Database được thiết kế với **named UDT/object types** dùng lặp lại giữa tables và procedures.
- Stored procedure nhận/trả một giá trị nhiều thuộc tính theo contract SQL type.
- Schema có nested objects/collections cần ánh xạ chặt với UDT.
- DB và driver hỗ trợ mapping có kiểm chứng.

Nhưng không nên tạo SQL UDT chỉ để thay cho một bảng đơn giản khi schema và tooling không cần. Đối với nhiều ứng dụng CRUD, row thông thường với các cột `city`/`postal_code` hoặc JSON/JSONB có thể đơn giản hơn và dễ di chuyển DBMS hơn.

**Cần quyết định từ nhu cầu query, constraints, schema migration và vendor support**, không chỉ từ việc Java có `Struct` interface.

## 13. Type maps, nested structures và thứ tự thuộc tính

### 13.1. Bản đồ type theo SQL name

Java có `Map<String, Class<?>>` trên Connection để ánh xạ UDT; key thường là tên qualified SQL type. Ví dụ `APP.ADDRESS_T` hoặc `SCHEMA.PERSON_T` tùy DB. Kiểm tra catalog/schema/case-folding theo driver vì SQL identifiers có quy tắc viết hoa và quoting khác nhau.

Type map không **tạo** UDT trong database. Nó chỉ nói cho JDBC driver biết, khi đọc SQL UDT hợp lệ, Java class nào được dùng để biểu diễn giá trị nếu mapping được hỗ trợ.

### 13.2. Nested Array/Struct

Nếu `PERSON_T` có trường `ADDRESS_T` và `tags ARRAY`, thì `Struct.getAttributes()` có thể trả attribute values là một `Struct` và một `Array`. Cần:

- Kiểm tra null ở từng attribute.
- Có custom type map cho nested UDT khi phù hợp.
- Dùng `Array.free()` đúng lifetime.
- Đọc attributes theo SQL declaration order.
- Tránh materialize cả một đồ thị nested rất lớn vào memory nếu có cách streaming.
- Kiểm tra depth/size để tránh tiêu thụ tài nguyên ngoài dự tính.

Không giả định `getAttributes()` tự biến nested data thành `Map<String,Object>` có field names. JDBC `Struct` tiêu chuẩn trả **mảng có thứ tự**, không phải JSON object.

### 13.3. SQL NULL của thuộc tính số

Nếu SQL STRUCT có `postal_code INTEGER` cho phép NULL, dùng primitive `int` trong `SQLData` dễ làm mất phân biệt NULL và 0. Ví dụ:

~~~java
int value = input.readInt();
Integer postalCode = input.wasNull() ? null : value;
~~~

Đây là snippet trong `SQLData.readSQL`, sau khi đọc **đúng** thuộc tính số. `wasNull()` nói về **giá trị vừa đọc gần nhất**, nên phải gọi ngay sau getter cần xét. Khi ghi, nếu attribute có thể null, dùng `writeObject`/method phù hợp với driver và SQL schema; tránh tự chuyển null thành 0.

## 14. Metadata: đừng suy đoán support của driver

Một ứng dụng có thể đọc:

~~~java
ResultSetMetaData meta = rs.getMetaData();
int jdbcType = meta.getColumnType(1);
String sqlTypeName = meta.getColumnTypeName(1);
~~~

Đây là snippet trong scope có `ResultSet rs`. Với cột array, metadata có thể báo `Types.ARRAY` hoặc vendor-specific mapping. Với structured UDT, có thể báo `Types.STRUCT` hoặc tên SQL type của vendor.

`DatabaseMetaData.getUDTs(...)` hỗ trợ khám phá UDT ở một số hệ quản trị; `getTypeInfo()` liệt kê kiểu dữ liệu được DB/driver báo hỗ trợ. Nhưng **metadata cũng chỉ tốt bằng implementation của driver**, và tồn tại không đồng nghĩa factory `createArrayOf/createStruct` đã hoạt động cho mọi type.

Khi cần kiểm chứng support:

1. Ghi lại DBMS và JDBC driver version.
2. Tạo DDL/schema và SQL types mà production thật dùng.
3. Thử `createArrayOf` / `createStruct` trong integration test.
4. Bind qua `setArray`/`setObject` và thực thi SQL.
5. Đọc lại bằng `getArray`/`getObject`/`getAttributes`.
6. Xác minh null elements, nested types, index, SQL type names, length và conversion.
7. Kiểm tra exception semantics khi type không được hỗ trợ.
8. Kiểm tra resource free/close trong transaction thật.

Đừng dùng **`getMetaData().supports...`** khi không có method JDBC được thiết kế đặc biệt cho capability ấy, rồi suy luận blanket support của tất cả structured types.

## 15. Error handling và resource ownership

Các lỗi thường gặp:

| Tình huống | Tác động | Cách xử lý |
| --- | --- | --- |
| `createArrayOf` với SQL element name sai | `SQLException` | Tra tên SQL type của driver/DB |
| Driver không hỗ trợ factory | `SQLFeatureNotSupportedException` hoặc `SQLException` theo driver | Dùng vendor-specific adapter hoặc thay schema |
| Nhầm `typeName` là tên Java class | Tạo array/struct thất bại | Dùng SQL element/UDT name |
| Gọi `getArray()` sau `free()` | `SQLException` | Giữ ownership, free sau khi dùng |
| `Array.getArray()` cast thành `Object[]` khi driver trả primitive array | `ClassCastException` | Xác minh representation/type-specific converter |
| Dùng SQL index 0 trong `getArray(index,count)` | Lỗi chỉ số | SQL ARRAY index bắt đầu từ **1** |
| Quên `Array.free()` | Giữ locator/resource phía driver/DB | Dùng `finally` trong Java 17 |
| Cố `try (Array x = ...)` với `--release 17` | Không compile: Array chưa AutoCloseable ở API 17 | `try/finally` + `free()` |
| Tạo `Struct` với attributes sai thứ tự | Conversion hoặc dữ liệu sai | Khớp SQL UDT declaration |
| `getObject` trả vendor-specific object | Cast `Struct` sai | Kiểm tra `instanceof`, metadata và mapping |
| `SQLData.readSQL` đọc attributes sai thứ tự | Dữ liệu đối tượng hỏng | Đồng bộ SQL type và Java mapping |
| SQL NULL bị convert thành primitive 0 | Mất thông tin NULL | `SQLInput.wasNull()` và wrapper type |
| Chia sẻ type map tùy tiện qua pooled connection | Rò cấu hình giữa requests | Cấu hình per-connection và reset theo pool |
| Giữ SQL Array locator sau transaction | Hết hiệu lực/DB exception | Consume trong transaction và free |
| Ghép SQL array literal từ input người dùng | SQL injection, quoting sai | `PreparedStatement.setArray` hoặc API vendor |
| Giả định PostgreSQL composite tự map thành Struct | Unsupported mapping | Kiểm tra pgJDBC UDT support thực |
| Copy Oracle `createOracleArray` vào PostgreSQL | Vendor API không tồn tại | Adapter theo database |

## 16. Bảo mật và tính nhất quán dữ liệu

### 16.1. Parameter binding thay vì SQL string concatenation

Không tự nối dữ liệu user thành SQL literal:

~~~java
String sql = "SELECT id FROM articles WHERE tags = '{" +
        userTag + "}'";
~~~

Đây là **anti-pattern minh họa**, không phải SQL portable và có rủi ro SQL injection nếu dữ liệu không được bind đúng.

Với driver hỗ trợ ARRAY:

~~~java
Array one = connection.createArrayOf(
        "text", new String[] {userTag});
try {
    try (PreparedStatement ps =
            connection.prepareStatement("SELECT ?::text[]")) {
        ps.setArray(1, one);
        // Execute và đọc result theo PostgreSQL SQL syntax.
    }
} finally {
    one.free();
}
~~~

Đây là snippet có `connection`/`userTag` và PostgreSQL. Với structured UDT, tương tự dùng `PreparedStatement.setObject`/`Struct` theo driver, không nối từng field vào SQL.

### 16.2. Không nhầm một Array nhiều giá trị với authorization scope

Nếu một request có array of tenant IDs, việc bind thành SQL array **không tự thực hiện kiểm tra quyền**. Ứng dụng vẫn phải validate từng ID và enforce row-level permission/tenant isolation trong SQL/service.

Với Struct có field nhạy cảm (address, birth date, personal info), đừng dump toàn bộ `getAttributes()` vào log. Thay vào đó log type name, độ dài/size hoặc diagnostics đã được redacted theo policy.

### 16.3. Giới hạn kích thước

Array hoặc nested struct có thể chứa rất nhiều phần tử/attributes. Trước khi materialize:

- Giới hạn số phần tử, kích thước từng phần tử và nested depth theo business policy.
- Kiểm tra memory usage và response size.
- Sử dụng partial access/ResultSet khi driver hỗ trợ hiệu quả.
- Tận dụng relational queries để lọc dữ liệu ngay phía database thay vì tải cả array về Java.
- Đặt timeout/budget cho JDBC operations, không để một UDT lớn chiếm thread/pool slot vô hạn.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `java.sql.Array` khác `String[]` như thế nào?

**Trả lời:** `Array` là JDBC representation của SQL ARRAY value, có thể giữ locator/transaction resource. `String[]` là mảng Java thông thường; `Array.getArray()` chuyển ra Java array theo driver mapping.

**Câu 2.** `Connection.createArrayOf("text", values)` nhận tên của kiểu gì?

**Trả lời:** Nhận **SQL tên kiểu phần tử** (`text` trong PostgreSQL), không phải tên SQL ARRAY `text[]` hoặc Java class name.

**Câu 3.** Trong `Array.getArray(2,2)`, index `2` tính theo Java hay SQL?

**Trả lời:** Theo SQL ARRAY, **bắt đầu từ 1**, nên nghĩa là phần tử thứ hai và thứ ba (nếu tồn tại).

**Câu 4.** `Array.getResultSet()` trả ResultSet có những cột nào?

**Trả lời:** Cột 1 là SQL index của phần tử; cột 2 là element value. `ResultSet.next()` đi qua từng phần tử.

**Câu 5.** Dưới `javac --release 17`, có thể đặt `java.sql.Array` trực tiếp trong `try-with-resources` không?

**Trả lời:** Không. Ở Java 17, `Array` chưa extends `AutoCloseable`. Dùng `try/finally` và `free()`. Java SE 26 có `Array.close()` nhờ thay đổi API hiện hành, nhưng bài demo ưu tiên tương thích Java 17+.

**Câu 6.** `Struct.getAttributes()` trả gì?

**Trả lời:** Trả `Object[]` chứa các attribute values **theo thứ tự định nghĩa SQL structured type**, không phải map theo tên field Java.

**Câu 7.** `Struct` có `free()` như `Array` không?

**Trả lời:** Không có `free()` trong interface `Struct` chuẩn. Vẫn cần quản lý resource và lifetime của connection/transaction và các giá trị nested Array/LOB.

**Câu 8.** `SQLData.readSQL` đọc `city` rồi `postal_code` nhưng SQL type khai báo ngược lại thì sao?

**Trả lời:** Mapping sai; driver có thể lỗi conversion hoặc dữ liệu bị gán sai. Thứ tự `readSQL/writeSQL` phải khớp thứ tự attributes của SQL UDT.

**Câu 9.** Tại sao `SQLInput.wasNull()` quan trọng sau `readInt()`?

**Trả lời:** Vì readInt trả giá trị primitive `0` cho SQL NULL; gọi `wasNull()` ngay sau đọc để phân biệt NULL và giá trị 0 thật.

**Câu 10.** Vì sao Oracle Database không nên dùng `Connection.createArrayOf(...)` như ví dụ PostgreSQL?

**Trả lời:** Oracle sử dụng **named collection types**, còn `createArrayOf` chuẩn JDBC thiết kế cho anonymous array với tên element type. Tài liệu Oracle khuyên dùng `OracleConnection.createOracleArray(namedTypeName, elements)`.

**Câu 11.** PostgreSQL có `CREATE TYPE address_t AS (...)` thì `createStruct("address_t", ...)` chắc chắn được pgJDBC hỗ trợ?

**Trả lời:** Không. SQL composite capability và JDBC standard Struct mapping là hai lớp khác nhau. Phải kiểm tra pgJDBC hỗ trợ chính xác API nào cho composite UDT và viết integration test.

**Câu 12.** `PreparedStatement.setArray` có thay thế relational child table trong mọi trường hợp không?

**Trả lời:** Không. Array có ích cho một số giá trị đa phần tử, nhưng quan hệ one-to-many cần index/constraints/update từng item thường phù hợp bảng liên kết hơn. Phụ thuộc SQL dialect và yêu cầu truy vấn.

**Câu 13.** Chương trình `JdbcStructuredDemo` đã chứng minh database nào?

**Trả lời:** Không có database thật nào. Nó dùng dynamic proxy và helpers `SQLInputImpl/SQLOutputImpl` để test API semantics trong memory. Kết quả DB/driver cần integration test riêng.

**Câu 14.** Làm sao kiểm tra driver đã bind được UDT thực tế?

**Trả lời:** Tạo SQL type/schema, dùng connection thật, gọi factory, bind bằng PreparedStatement, execute, đọc lại, kiểm tra type metadata/attributes/NULL và cleanup. Đừng suy luận chỉ vì interface Java biên dịch thành công.

**Ghi nhớ:** `java.sql.Array` biểu diễn một **SQL ARRAY value**, `java.sql.Struct` biểu diễn **SQL structured UDT value**. Đọc Array bằng `getArray` hoặc `getResultSet`, nhớ **SQL indexing 1-based** và `free()`. Đọc Struct bằng `getSQLTypeName` và `getAttributes` theo **thứ tự SQL attributes**. `SQLData/SQLInput/SQLOutput` hỗ trợ custom UDT mapping khi driver implement. Cả array lẫn struct đều **không portable tuyệt đối giữa DBMS**: hãy thiết kế schema, JDBC adapter và integration tests theo driver/version thật, đồng thời giữ rõ ranh giới giữa test double Java thuần và truy vấn database thực tế.

### Tài liệu chính thức và hiện hành

- [Oracle Java SE 26 — java.sql.Array](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Array.html): `getArray`, `getResultSet`, `free` và `close`.
- [Oracle Java SE 17 — java.sql.Array](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Array.html): API tương thích `--release 17` và `free()`.
- [Oracle Java SE 26 — java.sql.Struct](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Struct.html): type name và ordered attributes.
- [Oracle Java SE 26 — Connection](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `createArrayOf`, `createStruct`, type map.
- [Oracle Java SE 26 — PreparedStatement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): `setArray`/`setObject`.
- [Oracle Java SE 26 — ResultSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): `getArray`, `getObject`.
- [Oracle Java SE 26 — SQLData](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLData.html): UDT custom mapping; `readSQL/writeSQL`.
- [Oracle Java SE 26 — SQLInput/SQLOutput](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLInput.html): thuộc tính theo thứ tự; xem thêm [SQLOutput](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLOutput.html).
- [pgJDBC — PostgreSQL Arrays](https://jdbc.postgresql.org/documentation/server-prepare/): `createArrayOf` và `setArray` của PostgreSQL JDBC.
- [Oracle Database 26 — Working with Oracle Collections](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/Oracle-collections.html): named collections và Oracle JDBC mapping.
- [Oracle Database JDBC — ARRAY API](https://docs.oracle.com/en/database/oracle/oracle-database/26/jajdb/oracle/sql/ARRAY.html): `createOracleArray` dành cho named Oracle array type.

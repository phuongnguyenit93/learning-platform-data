# Làm việc với Struct và kiểu dữ liệu có cấu trúc trong JDBC

Thông thường, một ứng dụng Java dùng **JDBC** đọc và ghi từng cột SQL đơn giản như `BIGINT`, `VARCHAR`, `DECIMAL` hoặc `TIMESTAMP` thông qua `PreparedStatement` và `ResultSet`. Một số hệ quản trị còn cho phép định nghĩa **kiểu dữ liệu có cấu trúc** (*SQL structured type*): một giá trị có nhiều thuộc tính được tổ chức theo một kiểu SQL đã khai báo, chẳng hạn `ADDRESS_T` chứa đường phố, thành phố và mã bưu chính.

JDBC cung cấp giao diện `java.sql.Struct` để biểu diễn giá trị SQL có cấu trúc, cùng những API như `Connection.createStruct()`, `Struct.getAttributes()`, `PreparedStatement.setObject()` và `ResultSet.getObject()`. Đây là phần **Kiểu SQL nâng cao** của module **JDBC**, tập trung vào việc kết nối dữ liệu dạng cấu trúc với Java, xử lý SQL `NULL`, ánh xạ kiểu do người dùng định nghĩa, kiểm tra khả năng hỗ trợ driver, transaction và cách thiết kế mã truy cập dữ liệu có thể bảo trì.

**Điểm cần nhớ trước khi bắt đầu:** `Struct` là một phần của API JDBC chuẩn, nhưng **hệ quản trị không bắt buộc phải có kiểu SQL tương ứng hoặc hỗ trợ đầy đủ qua driver**. Ví dụ dùng kiểu `OBJECT` của Oracle chỉ để minh họa một hệ thống có hỗ trợ structured type; khi triển khai trên PostgreSQL, SQL Server hay MySQL cần kiểm tra kiểu SQL và cách ánh xạ thật.

## 1. Kiểu có cấu trúc khác một hàng trong `ResultSet` như thế nào?

Giả sử bảng khách hàng có địa chỉ giao hàng gồm ba thành phần:

```text
Customer
  ├─ id: 101
  └─ address
       ├─ street: "12 Nguyễn Huệ"
       ├─ city: "TP. Hồ Chí Minh"
       └─ postal_code: "700000"
```

Có ít nhất hai mô hình lưu trữ:

**Mô hình cột thông thường:**

```sql
CREATE TABLE customer_contacts (
    customer_id BIGINT PRIMARY KEY,
    street VARCHAR(120),
    city VARCHAR(80),
    postal_code VARCHAR(20)
);
```

**Mô hình giá trị có cấu trúc:** cơ sở dữ liệu định nghĩa một **kiểu SQL** như `ADDRESS_T` rồi dùng một cột thuộc kiểu đó. Cú pháp cụ thể phụ thuộc hệ quản trị; `CREATE TYPE` không giống nhau giữa các sản phẩm.

```text
customer_contacts
  customer_id | postal_address
  ------------+------------------------------------
  101         | ADDRESS_T("12 Nguyễn Huệ",
              |           "TP. Hồ Chí Minh", "700000")
```

Trong mô hình thứ hai, `postal_address` là **một giá trị SQL** bao gồm nhiều thuộc tính. Khi driver ánh xạ kiểu đó theo JDBC chuẩn, `ResultSet.getObject("postal_address")` có thể trả đối tượng triển khai `java.sql.Struct`.

Phân biệt ba đối tượng:

| Thành phần | Ý nghĩa | Có dùng `java.sql.Struct` không? |
| --- | --- | --- |
| Hàng SQL thông thường | Tập nhiều cột của một bản ghi `SELECT` | Thường đọc qua `ResultSet` và ánh xạ sang POJO/record Java |
| Giá trị SQL có cấu trúc | Một cột hoặc tham số có **kiểu người dùng định nghĩa** gồm nhiều thuộc tính | Có thể dùng `java.sql.Struct` nếu database/driver hỗ trợ |
| Đối tượng Java `Address` | Mô hình miền do ứng dụng định nghĩa | Là POJO/record riêng; chỉ trở thành SQL structured value khi có bước ánh xạ |

`Struct` **không phải** một cách thay thế mọi `ResultSet`, và cũng không phải Java `record`. Hãy xem nó là kiểu **đệm trao đổi dữ liệu ở ranh giới JDBC** giữa một SQL structured value và đối tượng Java.

## 2. API nền tảng: `Struct`, `Types.STRUCT` và vòng đời giá trị

Giao diện `java.sql.Struct` có hai thao tác trọng tâm:

```java
import java.sql.Struct;

String sqlTypeName = sqlStruct.getSQLTypeName();
Object[] attributes = sqlStruct.getAttributes();
```

- `getSQLTypeName()` trả về tên kiểu SQL của giá trị structured mà driver xác định, có thể bao gồm schema hoặc quy tắc chữ hoa/thường.
- `getAttributes()` trả về **một mảng `Object[]` theo thứ tự các thuộc tính được khai báo trong kiểu SQL**. Kiểu Java của từng phần tử phụ thuộc kiểu SQL và cách chuyển đổi của driver.
- `getAttributes(Map<String, Class<?>> map)` có thể dùng **type map** để ánh xạ các thuộc tính có kiểu structured lồng nhau, nếu driver hỗ trợ.
- `java.sql.Types.STRUCT` là mã kiểu JDBC dành cho kiểu SQL có cấu trúc. Đây là một **hằng mô tả kiểu**, không phải một đối tượng chứa giá trị.

Các API liên quan:

| API | Công dụng | Điều phải kiểm tra |
| --- | --- | --- |
| `Connection.createStruct(sqlTypeName, attributes)` | Tạo giá trị `Struct` từ tên kiểu SQL và mảng thuộc tính | Driver hỗ trợ? Tên kiểu/schema và thứ tự thuộc tính đúng? |
| `PreparedStatement.setObject(index, value)` | Truyền một `Struct` làm tham số câu SQL | Driver và cột đích có nhận kiểu structured tương ứng không? |
| `PreparedStatement.setObject(index, value, Types.STRUCT)` | Truyền đối tượng với mã kiểu JDBC được chỉ định | Overload và chuyển đổi có được driver hỗ trợ không? |
| `ResultSet.getObject(index/label)` | Nhận giá trị SQL, có thể là `Struct` | Driver thực sự trả `Struct` hay lớp riêng? Giá trị SQL có `NULL` không? |
| `Struct.getAttributes()` | Đọc từng thành phần của một giá trị đã nhận | Thuộc tính được trả theo **vị trí**, có thể chứa `NULL`/UDT lồng nhau |
| `Connection.getTypeMap()` / `setTypeMap()` | Quản lý ánh xạ tên kiểu SQL sang lớp Java implement `SQLData` | Sửa type map là sửa trạng thái kết nối; phải nghĩ tới connection pool |

Một `Struct` mới tạo bằng `createStruct()` **chưa đồng nghĩa đã ghi bản ghi vào bảng**. Chỉ khi `INSERT`, `UPDATE` hoặc lời gọi routine thực sự chạy thành công, dữ liệu mới tham gia transaction của kết nối.

## 3. Ví dụ schema: kiểu `OBJECT` trong Oracle Database

Để minh họa một structured type thật, dùng kiểu đối tượng `OBJECT` của Oracle Database:

```sql
CREATE TYPE address_t AS OBJECT (
    street      VARCHAR2(120),
    city        VARCHAR2(80),
    postal_code VARCHAR2(20)
);
```

Tạo bảng tham chiếu kiểu vừa định nghĩa:

```sql
CREATE TABLE customer_contacts (
    customer_id    NUMBER(19) PRIMARY KEY,
    postal_address address_t NOT NULL
);
```

Đây là **DDL theo cú pháp Oracle**, không phải DDL SQL đa hệ quản trị. Trước khi áp dụng, phải có quyền tạo kiểu/bảng và xác định schema chứa `ADDRESS_T`. Oracle có quy tắc đặt tên identifier không đặt dấu ngoặc kép; tên kiểu trong metadata có thể được báo về bằng chữ hoa. Nếu kiểu nằm ở schema khác, cần cân nhắc tên đủ schema, ví dụ `APP.ADDRESS_T`, theo cách driver giải quyết tên.

Kiểu `address_t` ở đây có **ba thuộc tính theo thứ tự**:

1. `street` — chuỗi đường phố.
2. `city` — chuỗi thành phố.
3. `postal_code` — chuỗi mã bưu chính.

Thứ tự chính là một phần của hợp đồng ánh xạ `Struct`. Java truyền mảng ba phần tử phải theo thứ tự này. Đổi thứ tự định nghĩa SQL mà không cập nhật Java có thể khiến giá trị bị gán sai chỗ, đặc biệt khi các thuộc tính đều có kiểu chuỗi tương tự nhau.

**Giới hạn khả chuyển:** PostgreSQL có *composite type*, nhưng driver JDBC thông dụng có thể biểu diễn qua `PGobject` hoặc API riêng thay vì `java.sql.Struct` ở mọi trường hợp. MySQL không cung cấp một kiểu đối tượng có cấu trúc tương đương chung để thay trực tiếp `ADDRESS_T`; SQL Server có các khả năng như user-defined types hoặc table-valued parameters với API riêng. Việc dùng `Struct` trong Java vì thế cần xác minh trực tiếp trên **hệ quản trị, phiên bản và driver đích**.

## 4. Ghi kiểu có cấu trúc: `Connection.createStruct()` và `PreparedStatement`

Trong ứng dụng thực tế, nên có một đối tượng Java miền như `Address` để tầng nghiệp vụ không trực tiếp thao tác với `Object[]`:

```java
public final class Address {
    private final String street;
    private final String city;
    private final String postalCode;

    public Address(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
```

DAO có nhiệm vụ **chuyển đổi giữa mô hình Java và SQL**. Trong ví dụ tiếp theo, Java đã có `DataSource` được cấu hình cho database và bảng của phần 3.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Struct;

public final class AddressRepository {
    private static final String ADDRESS_SQL_TYPE = "ADDRESS_T";

    private final DataSource dataSource;

    public AddressRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void insert(long customerId, Address address)
            throws SQLException {
        if (address == null) {
            throw new IllegalArgumentException("address is required");
        }

        String sql =
                "INSERT INTO customer_contacts " +
                "(customer_id, postal_address) VALUES (?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            Object[] attributes = {
                    address.getStreet(),
                    address.getCity(),
                    address.getPostalCode()
            };

            Struct value = connection.createStruct(
                    ADDRESS_SQL_TYPE, attributes);

            statement.setLong(1, customerId);
            statement.setObject(2, value);

            int affectedRows = statement.executeUpdate();
            if (affectedRows != 1) {
                throw new SQLException(
                        "Expected one inserted contact, got "
                        + affectedRows);
            }
        }
    }
}
```

Luồng thực thi:

```text
Address Java
   │ street, city, postalCode
   ▼
Object[] theo thứ tự khai báo ADDRESS_T
   │
   ▼
Connection.createStruct("ADDRESS_T", attributes)
   │
   ▼
Struct mang kiểu SQL + các thuộc tính
   │
   ▼
PreparedStatement.setObject(2, value)
   │
   ▼
INSERT vào cột postal_address
```

**Những điều phải xác minh trước khi dùng mã này trong hệ thống thật:**

- `Connection.createStruct()` thuộc API chuẩn nhưng có thể bị driver từ chối bằng `SQLFeatureNotSupportedException`. Nếu driver yêu cầu API riêng để tạo object type, phải cô lập phụ thuộc đó trong adapter.
- `ADDRESS_SQL_TYPE` phải đúng với tên kiểu mà driver nhận diện; có thể phải dùng tên đầy đủ schema hoặc tên/định dạng phù hợp.
- `Object[]` phải đúng **số lượng, thứ tự và kiểu tương thích** của các thuộc tính SQL. `street`, `city`, `postalCode` trong ví dụ đều là chuỗi, nhưng nếu thay bằng `DATE`, `NUMBER`, array hoặc object lồng nhau, cần chuyển đổi phù hợp.
- `setObject(2, value)` gán kiểu của giá trị JDBC; một số driver yêu cầu `setObject(2, value, Types.STRUCT)` hoặc API khác. Không mặc định biến thể nào cũng được hỗ trợ mọi nơi.
- Phương thức ví dụ chỉ thực hiện một lệnh `INSERT` với kết nối tự mượn. Nếu nghiệp vụ ghi nhiều bảng trong cùng transaction, **mọi thao tác phải dùng chung `Connection`** do tầng giao dịch sở hữu.
- Các chuỗi tiếng Việt qua driver còn phụ thuộc kiểu ký tự, mã hóa kết nối và cơ sở dữ liệu. Sử dụng `Struct` không tự khắc phục vấn đề Unicode.

## 5. Đọc `Struct` từ `ResultSet` rồi chuyển thành đối tượng miền

Khi truy vấn cột `postal_address`, một driver hỗ trợ structured type theo JDBC có thể trả một `Struct`. Bước ánh xạ nên nằm trong DAO để service chỉ nhận `Address`:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Struct;
import java.util.Optional;

public final class AddressReader {
    private final DataSource dataSource;

    public AddressReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<Address> find(long customerId) throws SQLException {
        String sql =
                "SELECT postal_address " +
                "FROM customer_contacts WHERE customer_id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, customerId);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }

                Object raw = rs.getObject("postal_address");
                if (!(raw instanceof Struct)) {
                    // Cột trong ví dụ là NOT NULL.
                    // Nếu driver trả kiểu riêng, cần adapter khác.
                    throw new SQLException(
                            "Expected JDBC Struct for postal_address");
                }

                Struct addressStruct = (Struct) raw;
                Object[] attributes = addressStruct.getAttributes();

                if (attributes.length != 3) {
                    throw new SQLException(
                            "ADDRESS_T must have three attributes");
                }

                Address address = new Address(
                        (String) attributes[0],
                        (String) attributes[1],
                        (String) attributes[2]);

                return Optional.of(address);
            }
        }
    }
}
```

Cách gọi:

```java
Address original =
        new Address("12 Nguyễn Huệ", "TP. Hồ Chí Minh", "700000");

AddressRepository writer = new AddressRepository(dataSource);
AddressReader reader = new AddressReader(dataSource);

writer.insert(101L, original);
Address loaded = reader.find(101L).orElseThrow(
        () -> new IllegalStateException("Address was not found"));

System.out.println(loaded.getCity()); // TP. Hồ Chí Minh
```

Đoạn gọi giả định chưa tồn tại hàng `customer_id = 101`. Nó cũng giả định driver hỗ trợ `Struct` và kiểu SQL `ADDRESS_T` đã được tạo đúng.

**Phân biệt giá trị `NULL` với các thuộc tính `NULL`:**

- Nếu **cả cột** `postal_address` là SQL `NULL`, `ResultSet.getObject(...)` sẽ trả `null`, không phải một `Struct` chứa ba giá trị null. Trong schema minh họa có `NOT NULL` nên trường hợp này là bất thường.
- Nếu **giá trị object tồn tại** nhưng `city` là SQL `NULL`, `getAttributes()[1]` có thể là `null` trong khi `getAttributes()` vẫn có đủ ba phần tử.
- `getAttributes()` trả về mảng `Object[]`. Các phép cast sang `String` chỉ phù hợp với kiểu `VARCHAR2` của ví dụ; với kiểu SQL khác, Java có thể nhận `BigDecimal`, `Date`, `Timestamp`, `Struct` hoặc lớp do driver sử dụng.
- `Optional.empty()` trong phương thức `find` biểu diễn **không có hàng**, không tự dùng để biểu diễn “hàng có object null”. Nếu cột có thể null và ứng dụng cần phân biệt, hãy thiết kế kiểu kết quả phù hợp.

Không trả `ResultSet` hoặc `Struct` phụ thuộc vòng đời kết nối ra các tầng nghiệp vụ khi có thể chuyển sang một DTO/POJO độc lập trong phạm vi DAO.

## 6. `SQLData`: tùy chọn ánh xạ trực tiếp một kiểu SQL sang lớp Java

Dùng `Struct` và `getAttributes()` là cách ánh xạ **thủ công** theo thứ tự thuộc tính. JDBC còn định nghĩa giao diện `java.sql.SQLData`, phối hợp với `SQLInput` và `SQLOutput` để ánh xạ kiểu SQL do người dùng định nghĩa sang một lớp Java cụ thể.

Một implementation đơn giản:

```java
import java.sql.SQLData;
import java.sql.SQLInput;
import java.sql.SQLOutput;
import java.sql.SQLException;

public final class AddressSqlData implements SQLData {
    private String sqlTypeName = "ADDRESS_T";
    private String street;
    private String city;
    private String postalCode;

    // Constructor không tham số để JDBC driver tạo instance khi đọc.
    public AddressSqlData() {
    }

    public AddressSqlData(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    @Override
    public String getSQLTypeName() {
        return sqlTypeName;
    }

    @Override
    public void readSQL(SQLInput input, String typeName)
            throws SQLException {
        sqlTypeName = typeName;

        // Đúng thứ tự khai báo trong ADDRESS_T.
        street = input.readString();
        city = input.readString();
        postalCode = input.readString();
    }

    @Override
    public void writeSQL(SQLOutput output) throws SQLException {
        output.writeString(street);
        output.writeString(city);
        output.writeString(postalCode);
    }
}
```

`readSQL(...)` nhận luồng thuộc tính và đọc **đúng thứ tự**; `writeSQL(...)` ghi trở lại theo cùng thứ tự. Không được đổi thứ tự trong Java rồi chờ driver ghép theo tên biến.

Có thể cung cấp ánh xạ kiểu riêng khi đọc `ResultSet`:

```java
import java.sql.ResultSet;
import java.util.HashMap;
import java.util.Map;

// Giả sử ResultSet rs đã ở dòng hợp lệ và driver hỗ trợ UDT map.
Map<String, Class<?>> typeMap = new HashMap<>();
typeMap.put("APP.ADDRESS_T", AddressSqlData.class);

Object value = rs.getObject("postal_address", typeMap);

if (value instanceof AddressSqlData) {
    AddressSqlData address = (AddressSqlData) value;
    // Chuyển sang đối tượng miền nếu cần.
}
```

Cần dùng **tên SQL type chính xác** mà driver báo (bao gồm schema nếu cần); `APP.ADDRESS_T` là tên ví dụ, không mặc định đúng với môi trường thực tế.

Một số driver có thể không hỗ trợ ánh xạ `SQLData` hoặc phương thức `getObject(..., Map)` cho loại UDT cụ thể. `Connection.getTypeMap()` / `setTypeMap()` cũng là API chuẩn để cấu hình ánh xạ nhưng **thay đổi map trên một kết nối là thay đổi trạng thái**: khi dùng connection pool, phải khôi phục sau khi sử dụng hoặc ưu tiên truyền map riêng cho lần đọc nếu driver hỗ trợ. Không nên cấu hình type map toàn cục mà không kiểm tra tác động tới các yêu cầu khác.

**Lựa chọn thực tế:** với một kiểu đơn giản và ít thuộc tính, `Struct.getAttributes()` cộng mapper rõ ràng thường dễ kiểm soát. `SQLData` phù hợp hơn khi driver hỗ trợ tốt và có nhiều kiểu UDT cần ánh xạ nhất quán, nhưng đi kèm việc phụ thuộc vào tên SQL type và thứ tự các thuộc tính.

## 7. Kiểu có cấu trúc lồng nhau và kiểu tập hợp

Một SQL structured type có thể chứa thuộc tính là **kiểu structured khác**, hoặc thuộc tính thuộc kiểu dữ liệu nâng cao như array và LOB tùy hệ quản trị.

Ví dụ mô hình khái niệm:

```text
ORDER_INFO_T
  ├─ order_id        NUMBER
  ├─ ship_to         ADDRESS_T
  │    ├─ street     VARCHAR
  │    ├─ city       VARCHAR
  │    └─ postal     VARCHAR
  └─ tags            ARRAY / collection type
```

Một cách khám phá các thuộc tính đã được driver chuyển đổi:

```java
Object[] orderFields = orderStruct.getAttributes();

Object shipTo = orderFields[1];
if (shipTo instanceof Struct) {
    Struct nested = (Struct) shipTo;
    Object[] addressFields = nested.getAttributes();
    // Dùng từng thuộc tính theo hợp đồng kiểu ADDRESS_T.
}

Object tags = orderFields[2];
if (tags instanceof java.sql.Array) {
    java.sql.Array sqlArray = (java.sql.Array) tags;
    try {
        Object arrayValue = sqlArray.getArray();
        // Kiểm tra kiểu Java thực tế của arrayValue.
    } finally {
        sqlArray.free();
    }
}
```

Đoạn minh họa giả sử biến `orderStruct` chứa `Struct` đã đọc, thứ tự trường là `(order_id, ship_to, tags)` và driver hỗ trợ chuyển đổi tương ứng. `java.sql.Array` là **đối tượng JDBC khác `Struct`**, có phương thức `free()` giải phóng tài nguyên; điều này đặc biệt quan trọng khi có dữ liệu lớn. Nếu sử dụng `Blob`/`Clob`/`SQLXML`, cần quản lý vòng đời theo API của từng loại.

Khi viết một `Struct` lồng nhau, có thể cần tạo `Struct` của thuộc tính con trước, rồi đặt nó vào mảng thuộc tính cha. Nhưng driver có thể không hỗ trợ đầy đủ cấu trúc lồng nhau qua `createStruct()` hoặc yêu cầu API đặc thù. Với collection SQL, đừng tự suy ra `Object[]` luôn chuyển được sang một `ARRAY`; phải kiểm tra `Connection.createArrayOf()` và khả năng của driver.

Các trường hợp nested nhiều cấp làm chi phí kiểm thử, chuyển đổi và thay đổi schema tăng lên. Nếu cấu trúc có nhiều tập hợp một-nhiều hoặc cần tìm kiếm/index từng thành phần, mô hình **bảng quan hệ với khóa ngoại** có thể dễ quản lý hơn.

## 8. Metadata giúp khám phá kiểu, nhưng không thay thế kiểm thử

`DatabaseMetaData` cung cấp các API như `getUDTs(...)` và `getAttributes(...)` để thăm dò user-defined types, nếu driver hỗ trợ:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;

public static void inspectAddressType(Connection connection)
        throws SQLException {
    DatabaseMetaData metadata = connection.getMetaData();

    try (ResultSet types = metadata.getUDTs(
            null, "APP", "ADDRESS_T",
            new int[] { Types.STRUCT })) {

        while (types.next()) {
            System.out.println(
                    "UDT=" + types.getString("TYPE_NAME")
                    + ", SQL type=" + types.getInt("DATA_TYPE"));
        }
    }

    try (ResultSet attributes = metadata.getAttributes(
            null, "APP", "ADDRESS_T", "%")) {

        while (attributes.next()) {
            System.out.println(
                    "attribute=" + attributes.getString("ATTR_NAME")
                    + ", position=" + attributes.getInt("ORDINAL_POSITION")
                    + ", SQL type=" + attributes.getInt("DATA_TYPE"));
        }
    }
}
```

`"APP"` trong ví dụ là schema giả định. Hãy thay bằng schema thực tế và xem driver có hỗ trợ tên chữ hoa, chữ thường, quoted identifier hay trả UDT ở catalog/schema khác không. Metadata có thể bị giới hạn bởi quyền xem catalog hoặc không hỗ trợ trọn vẹn chức năng cho các kiểu riêng.

Khi nhận một `Struct`, có thể kiểm tra `getSQLTypeName()` và `getAttributes().length` trước khi ánh xạ. Tuy vậy, chỉ kiểm tra số thuộc tính **không đủ**: nếu hai thuộc tính cùng kiểu bị đổi vị trí, mapper có thể vẫn chạy nhưng tạo dữ liệu sai. Cần có **kiểm thử round-trip** và hợp đồng schema rõ ràng.

## 9. SQL `NULL`, ép kiểu và lỗi ánh xạ

Những trường hợp thường gây lỗi khi xử lý structured type:

| Tình huống | Nguy cơ | Cách xử lý |
| --- | --- | --- |
| Cột structured là SQL `NULL` | `getObject(...)` trả `null`, cast sang `Struct` hoặc gọi phương thức sẽ lỗi | Kiểm tra `raw == null` trước khi sử dụng; phân biệt với không có hàng |
| Một thuộc tính bên trong là `NULL` | `getAttributes()[i]` có thể là `null` | Thiết kế DTO/validation phản ánh khả năng null của từng thuộc tính |
| Thứ tự thuộc tính SQL thay đổi | Gán sai dữ liệu giữa các trường có kiểu tương tự | Versioning schema, kiểm tra metadata và round-trip |
| Tên type sai schema hoặc cách viết | `createStruct()` báo `SQLException` | Kiểm tra tên SQL type thực, quyền, schema và driver |
| Kiểu số/temporal không khớp | `ClassCastException` hoặc lỗi chuyển đổi | Kiểm tra kiểu SQL và lớp Java thực tế; chuyển đổi có kiểm soát |
| Driver không hỗ trợ `Struct` | `SQLFeatureNotSupportedException` hoặc đối tượng driver-specific | Adapter phù hợp hoặc mô hình SQL khác |
| Cột structured được cập nhật đồng thời | Rủi ro ghi đè thuộc tính | Transaction, điều kiện phiên bản hoặc khóa phù hợp |

Ví dụ khi cột cho phép SQL `NULL` và cần phân biệt rõ:

```java
if (!rs.next()) {
    // Không có hàng.
    return;
}

Object raw = rs.getObject("postal_address");
if (raw == null) {
    // Có hàng nhưng toàn bộ giá trị địa chỉ là SQL NULL.
} else if (raw instanceof Struct) {
    Struct value = (Struct) raw;
    Object[] attributes = value.getAttributes();

    // attributes[1] == null có nghĩa là một thành phần SQL NULL.
} else {
    throw new SQLException(
            "Driver returned an unexpected structured value type");
}
```

Không nên dùng tên lớp Java nội bộ của driver làm hợp đồng chung cho tất cả hệ quản trị. Cũng không nên đoán kiểu Java từ tên SQL `NUMBER` hay `DATE`: cách chuyển đổi có thể khác theo driver và cấu hình, nhất là với ngày giờ, độ chính xác số và múi giờ.

## 10. Cập nhật một thuộc tính: ghi lại toàn bộ cấu trúc hay thao tác phía SQL?

Nếu cột `postal_address` chứa nhiều thuộc tính, để đổi riêng `city` có thể có hai cách:

1. **Đọc `Struct` → tạo lại mảng thuộc tính → tạo `Struct` mới → `UPDATE` cả cột**.
2. Dùng **cú pháp SQL riêng của hệ quản trị** để cập nhật hoặc dựng lại giá trị có cấu trúc từ phía database.

Cách 1 dễ thể hiện trong JDBC nhưng có rủi ro khi hai transaction cùng đọc giá trị cũ, thay các thành phần khác nhau rồi ghi toàn bộ object: thao tác sau có thể **ghi đè** thay đổi của thao tác trước. Nếu dùng cách này, cân nhắc khóa bản ghi, optimistic locking với cột version, hoặc transaction isolation phù hợp.

Cách 2 tránh kéo toàn bộ object về Java trong một số tình huống, nhưng cú pháp thao tác với thuộc tính structured type khác nhau giữa database. Ví dụ, nhiều hệ cho phép biểu thức truy cập trường object, nhưng cách `UPDATE` trực tiếp một thành phần có thể phải viết lại cho từng sản phẩm. Đây là đánh đổi giữa hiệu năng, tính đúng và tính khả chuyển.

Không nên mặc định rằng lưu một địa chỉ dưới dạng `Struct` mang lại khả năng tìm kiếm, lập chỉ mục hoặc update thành phần tốt hơn mô hình **ba cột SQL bình thường**. Hãy kiểm tra kế hoạch thực thi, kiểu chỉ mục có thể tạo và truy vấn nghiệp vụ thường dùng.

## 11. Transaction, batching và vòng đời tài nguyên

Một `Struct` chỉ là **giá trị đầu vào/đầu ra** của lệnh JDBC. Nó không tự tạo transaction riêng. Khi nghiệp vụ cần lưu khách hàng và địa chỉ atomically:

- Lấy **một `Connection`** từ `DataSource` và xác định bên sở hữu transaction.
- Bắt đầu transaction khi thích hợp, thực thi các lệnh với cùng kết nối.
- `commit()` sau khi toàn bộ lệnh thành công; `rollback()` khi lỗi và quản lý trạng thái kết nối trước khi trả về pool.
- Chỉ khôi phục `autoCommit` sau khi transaction đã kết thúc; không bật lại `autoCommit=true` một cách máy móc nếu `rollback()` thất bại.
- Đóng `ResultSet` và `PreparedStatement` bằng `try-with-resources`, không giữ các tài nguyên phụ thuộc kết nối sau khi đóng.

Bộ API `PreparedStatement.addBatch()`/`executeBatch()` có thể kết hợp với tham số `Struct` nếu driver hỗ trợ, nhưng **không được suy từ việc hỗ trợ batch nói chung rằng batch với UDT luôn hoạt động hoặc luôn trả update counts giống nhau**. Phải thử riêng:

```java
String sql =
        "INSERT INTO customer_contacts " +
        "(customer_id, postal_address) VALUES (?, ?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    for (Contact contact : contacts) {
        Struct address = connection.createStruct(
                "ADDRESS_T", new Object[] {
                    contact.street(), contact.city(), contact.postalCode()
                });

        statement.setLong(1, contact.customerId());
        statement.setObject(2, address);
        statement.addBatch();
    }

    int[] counts = statement.executeBatch();
    // Kiểm tra counts, lỗi và transaction theo driver thực tế.
}
```

Đây là **pseudocode Java tập trung vào JDBC**, với `Contact` là kiểu mô hình giả định có các phương thức `customerId()`, `street()`, `city()`, `postalCode()`. Nếu dự án dùng Java record, đây có thể là các accessor của record; nếu dùng POJO, thay bằng getter tương ứng. Không dùng đoạn này như chương trình độc lập nếu chưa định nghĩa `Contact` và quản lý `connection`.

Khi batch thất bại, `BatchUpdateException` có thể chứa `getUpdateCounts()` và `getNextException()`; kết quả có thể là một phần. Nếu câu SQL ghi dữ liệu đã thực thi ở server, đừng retry cả batch khi chưa biết trạng thái từng phần tử, commit và tính idempotent của nghiệp vụ.

## 12. Tính khả chuyển và chi phí bảo trì

Mô hình giá trị structured có thể rất thuận tiện khi:

- Database đã có kiểu object được chuẩn hóa và nhiều routine/bảng cùng dùng.
- Nhiều thuộc tính luôn được truyền cùng nhau như một giá trị logic.
- Quy trình nghiệp vụ chủ yếu ở database và driver hỗ trợ ánh xạ đáng tin cậy.
- Có kiểm thử tích hợp và quản lý version kiểu SQL cùng phiên bản ứng dụng.

Nhưng nó cũng tạo phụ thuộc:

| Khía cạnh | Câu hỏi nên đặt ra |
| --- | --- |
| DDL và khả chuyển | Database khác có kiểu SQL tương đương không? Nếu không, thiết kế thay thế là gì? |
| JDBC driver | `createStruct()`, `getObject()`, `SQLData` và ánh xạ kiểu lồng nhau có được hỗ trợ ở phiên bản thực tế không? |
| Schema evolution | Thêm/đổi thứ tự thuộc tính ảnh hưởng bao nhiêu DAO, procedure, view và bản ghi đã lưu? |
| Hiệu năng | Truy vấn/lọc/sắp xếp theo thuộc tính có hiệu quả và có chỉ mục hỗ trợ không? |
| Transaction | Cập nhật cả object có gây ghi đè thay đổi đồng thời không? |
| Quyền và migration | Ai được quyền tạo type, đổi type, deploy và rollback migration? |
| Kiểm thử | Có test round-trip, null, kiểu lồng nhau và các kiểu dữ liệu đặc biệt trên DB thật không? |

So sánh các lựa chọn:

| Mô hình lưu | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Nhiều cột scalar trong một bảng | SQL đơn giản, dễ index/filter, JDBC mapper rõ ràng | Các thuộc tính không được đóng gói thành một SQL value |
| Bảng riêng liên kết bằng khóa ngoại | Hỗ trợ quan hệ và tập hợp một-nhiều, constraint rõ ràng | Thêm JOIN và logic map đối tượng |
| SQL structured type + `Struct` | Biểu diễn một giá trị có nhiều thuộc tính, tích hợp với routine/UDT | Phụ thuộc kiểu SQL/driver, schema migration và mapping theo thứ tự |
| JSON hoặc kiểu tài liệu đặc thù DB | Linh hoạt khi cấu trúc thay đổi nhiều | Cú pháp truy vấn, validation, indexing và API JDBC phụ thuộc sản phẩm |

Không có một mô hình luôn đúng. Nếu dự kiến chuyển hệ quản trị thường xuyên hoặc dữ liệu được truy vấn mạnh theo từng thuộc tính, các cột scalar hay mô hình quan hệ có thể phù hợp hơn. Nếu database đã sử dụng SQL object types xuyên suốt và có tooling/migration rõ ràng, `Struct` có thể là một lựa chọn hợp lý.

## 13. Kiểm thử round-trip trên driver và schema thật

**Round-trip** là phép kiểm tra viết dữ liệu Java vào SQL rồi đọc ngược lại, so sánh giá trị thu được với kỳ vọng. Với `Struct`, nên kiểm tra cả cấu trúc và ngữ nghĩa dữ liệu, không chỉ kiểm tra câu lệnh không ném ngoại lệ.

Các ca kiểm thử tối thiểu:

| Ca thử | Điều cần xác nhận |
| --- | --- |
| Địa chỉ đầy đủ ba trường | `getAttributes()` trả đúng ba phần tử, đúng thứ tự và giá trị |
| Chuỗi Unicode như `"Đà Nẵng"` | Không mất dấu qua driver và SQL type |
| Một thuộc tính null | Giữ được `NULL` ở đúng thuộc tính, nếu schema cho phép |
| Toàn bộ cột `postal_address` null | Phân biệt hàng tồn tại với cột null và không có hàng |
| `CREATE TYPE` ở schema khác | Tên `APP.ADDRESS_T`/schema có được giải quyết đúng |
| Driver không hỗ trợ `createStruct()` | DAO báo lỗi tính năng và có phương án thiết kế khác rõ ràng |
| Đổi thứ tự hai trường cùng kiểu | Test phát hiện mapping sai, không chỉ so sánh mảng có cùng chiều dài |
| Cập nhật cạnh tranh | Không mất thay đổi theo bất biến và mức cô lập đã chọn |
| Transaction chứa nhiều thao tác | Lỗi giữa chừng rollback đúng những thao tác chưa commit |
| Batch với `Struct` | Xử lý thành công/thất bại và update counts theo driver thật |
| Kiểu lồng nhau/array | Các thuộc tính và tài nguyên JDBC được xử lý đúng vòng đời |

**Bài tập thực hành:**

1. Tạo kiểu `ADDRESS_T` và bảng `customer_contacts` theo cú pháp của hệ quản trị đang sử dụng; nếu DB không hỗ trợ kiểu structured theo JDBC, ghi lại giới hạn đó và so sánh với cột scalar.
2. Dùng `DataSource`, `Connection.createStruct()` và `PreparedStatement` viết `AddressRepository.insert(...)`. Kiểm tra loại ngoại lệ nếu driver từ chối `createStruct()`.
3. Dùng `ResultSet.getObject()`, `Struct.getSQLTypeName()` và `getAttributes()` đọc dữ liệu. So sánh ba thuộc tính với giá trị đầu vào.
4. Thử `getUDTs()` và `getAttributes()` để đối chiếu tên SQL type, thứ tự và loại thuộc tính; ghi nhận nếu metadata không đầy đủ.
5. Viết `AddressSqlData` và thử `ResultSet.getObject(column, typeMap)` nếu driver hỗ trợ. So sánh độ rõ ràng của mapper `Struct` thủ công với mapper `SQLData`.
6. Tạo hai connection cùng đọc một địa chỉ, sau đó cập nhật hai thành phần khác nhau; kiểm tra nguy cơ lost update khi ghi lại toàn bộ giá trị.
7. Ghi một bảng kết luận về **API được hỗ trợ**, **tên type/schema cần cấu hình**, **kết quả round-trip**, **transaction/batch**, và **chi phí thay đổi schema**.

## 14. Những nguyên tắc cần nhớ

1. **`Struct` là giá trị SQL có cấu trúc**, không phải `ResultSet` hay đối tượng miền Java.
2. **`Connection.createStruct()` và `getAttributes()` phụ thuộc kiểu SQL và driver**; không giả định tất cả hệ quản trị có structured type tương đương.
3. **Thứ tự thuộc tính là hợp đồng quan trọng**. Kiểm soát qua schema, mapper và kiểm thử round-trip.
4. **Phân biệt object SQL `NULL` với thuộc tính bên trong `NULL`**; thiết kế kết quả DAO phù hợp.
5. **`SQLData` và type map là lựa chọn ánh xạ nâng cao**, có thể không được driver hỗ trợ; quản lý trạng thái kết nối nếu sử dụng `setTypeMap()`.
6. **Kiểm tra cả transaction và batching** khi truyền các giá trị structured; không tự retry thao tác ghi nếu trạng thái chưa rõ.
7. **Đánh giá khả chuyển và chi phí bảo trì** trước khi chọn SQL structured type thay cho bảng/cột quan hệ thông thường.

**Kết luận:** JDBC cung cấp `java.sql.Struct` như một cầu nối chuẩn cho một số kiểu dữ liệu có cấu trúc của SQL. Sử dụng nó hiệu quả đòi hỏi hiểu đúng kiểu SQL ở database, ánh xạ từng thuộc tính theo thứ tự và kiểu tương thích, kiểm soát transaction cùng tài nguyên, và **kiểm chứng trên driver thật** trước khi coi việc đọc ghi structured data là đáng tin cậy.

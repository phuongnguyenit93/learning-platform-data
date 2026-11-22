# Vai trò của `SQLData`, `SQLInput` và `SQLOutput` trong JDBC

Trong JDBC, phần lớn ứng dụng trao đổi dữ liệu qua các kiểu SQL thông dụng như `VARCHAR`, `BIGINT`, `DECIMAL`, `DATE` và `TIMESTAMP`. Các phương thức `PreparedStatement.setXxx(...)` và `ResultSet.getXxx(...)` thường đủ để làm việc với những kiểu này. Một số cơ sở dữ liệu còn hỗ trợ **kiểu do người dùng định nghĩa** (*user-defined type*, UDT), đặc biệt là **kiểu cấu trúc** (*structured type*) có nhiều thuộc tính nằm trong một giá trị SQL. Khi ứng dụng muốn biểu diễn kiểu cấu trúc ấy bằng một lớp Java riêng, JDBC định nghĩa ba giao diện phối hợp với nhau: `SQLData`, `SQLInput` và `SQLOutput`.

Điểm cốt lõi là **`SQLData` mô tả cách ánh xạ một giá trị UDT giữa SQL và Java; `SQLInput` đọc các thuộc tính khi driver chuyển SQL sang Java; `SQLOutput` ghi các thuộc tính khi driver chuyển Java sang SQL**. Cả ba phục vụ cơ chế ánh xạ của driver; chúng không thay thế `Connection`, `PreparedStatement`, `ResultSet` hay việc quản lý transaction.

Bài thuộc chương **Kiểu SQL nâng cao** của module **JDBC**. Nội dung tập trung vào ánh xạ tùy biến kiểu cấu trúc bằng API chuẩn, cách đăng ký ánh xạ, quy tắc thứ tự thuộc tính, vòng đời tài nguyên, giới hạn hỗ trợ của driver và tình huống thực hành trên cơ sở dữ liệu quan hệ.

Sau bài học, bạn sẽ có thể:

- Nêu đúng trách nhiệm của từng giao diện `SQLData`, `SQLInput`, `SQLOutput`.
- Cài đặt lớp Java ánh xạ một UDT cấu trúc, có constructor không đối số và ba phương thức của `SQLData`.
- Đăng ký kiểu SQL với lớp Java bằng *type map* và đọc giá trị qua `ResultSet.getObject(...)`.
- Dùng `PreparedStatement.setObject(...)` để ghi giá trị UDT khi driver hỗ trợ ánh xạ tương ứng.
- Xử lý `NULL`, thứ tự thuộc tính, các kiểu lồng nhau và thay đổi schema một cách có chủ đích.
- Nhận diện giới hạn về tính di động, hiệu năng và hỗ trợ JDBC driver trước khi dùng trong sản phẩm.

## 1. Bài toán: một giá trị SQL gồm nhiều thuộc tính

Giả sử một hệ thống lưu địa chỉ giao hàng dưới dạng một kiểu cấu trúc gồm ba thuộc tính:

```text
SQL UDT: ADDRESS_T
  street       VARCHAR(...)
  city         VARCHAR(...)
  postal_code  VARCHAR(...)

Một giá trị ADDRESS_T:
  ("12 Nguyễn Huệ", "TP. Hồ Chí Minh", "700000")
```

Một số hệ quản trị có khả năng khai báo kiểu đối tượng/cấu trúc và dùng nó làm kiểu cột. Ví dụ **cú pháp Oracle SQL** (chỉ minh họa cho một DB cụ thể):

```sql
CREATE TYPE address_t AS OBJECT (
    street      VARCHAR2(120),
    city        VARCHAR2(80),
    postal_code VARCHAR2(20)
);

CREATE TABLE customer_delivery (
    customer_id   NUMBER(19) PRIMARY KEY,
    address_value address_t
);
```

Nếu kiểu được tạo trong schema `APP_SCHEMA`, tên đủ điều kiện có thể là `APP_SCHEMA.ADDRESS_T`. **Tên schema và kiểu phải được thay bằng tên thực tế**, đồng thời tuân thủ quy tắc viết hoa/chữ thường của driver và DB. Nhiều cơ sở dữ liệu không dùng cú pháp `CREATE TYPE ... AS OBJECT` này; một số có kiểu composite nhưng cách JDBC ánh xạ lại khác. Đặc biệt, việc SQL hỗ trợ UDT **không đồng nghĩa** driver chắc chắn hỗ trợ `SQLData`.

Với một cột `address_value`, ứng dụng có thể nhận về `java.sql.Struct`, một đối tượng do driver định nghĩa, hoặc một **lớp Java do lập trình viên viết**, nếu đã thiết lập ánh xạ phù hợp. `SQLData` là giao diện dùng cho lựa chọn thứ ba.

### Luồng ánh xạ khi đọc và ghi

```text
                  ĐỌC: SQL -> Java

SELECT address_value
        |
  ResultSet.getObject(...) + type map
        |
   JDBC driver nhận diện UDT
        |
   Tạo lớp implements SQLData
        |
   readSQL(SQLInput, typeName)
        |
   Đối tượng Java có các thuộc tính đã đọc

                  GHI: Java -> SQL

new AddressSqlData(...)
        |
  PreparedStatement.setObject(...)
        |
   Driver nhận diện SQLData / tên kiểu SQL
        |
   writeSQL(SQLOutput)
        |
   Giá trị UDT được bind vào câu SQL
```

Đây là **luồng trách nhiệm**, không phải cam kết về thuật toán nội bộ của mọi driver. Driver quyết định cách tạo stream, chuyển đổi từng thuộc tính, truyền dữ liệu và giao tiếp với DB.

## 2. Vai trò riêng của ba giao diện

| Giao diện JDBC | Ai thường cài đặt? | Được dùng khi nào? | Trách nhiệm |
| --- | --- | --- | --- |
| `java.sql.SQLData` | **Lập trình viên** cài đặt trong lớp ánh xạ | Khi driver đọc/ghi một SQL UDT được ánh xạ tùy biến | Khai báo tên kiểu SQL, đọc và ghi các thuộc tính của giá trị |
| `java.sql.SQLInput` | **Driver** cung cấp đối tượng stream | Driver gọi `SQLData.readSQL(...)` | Đọc tuần tự từng thuộc tính UDT từ SQL sang kiểu Java |
| `java.sql.SQLOutput` | **Driver** cung cấp đối tượng stream | Driver gọi `SQLData.writeSQL(...)` | Ghi tuần tự từng thuộc tính từ Java sang biểu diễn SQL |

`SQLInput` và `SQLOutput` không phải các stream để lập trình viên tự mở từ file hay socket. Trong cơ chế ánh xạ tùy biến, ứng dụng chủ yếu **cài đặt `SQLData`**; driver truyền đối tượng `SQLInput` hoặc `SQLOutput` vào callback thích hợp. Chúng cũng **không phải `ResultSet` hoặc `PreparedStatement`**: một lần gọi `readString()` trên `SQLInput` chuyển sang thuộc tính tiếp theo của **cùng một giá trị UDT**, chứ không phải hàng kế tiếp trong kết quả truy vấn.

### Hợp đồng ba phương thức của `SQLData`

```java
public interface SQLData {
    String getSQLTypeName() throws SQLException;

    void readSQL(SQLInput stream, String typeName)
            throws SQLException;

    void writeSQL(SQLOutput stream)
            throws SQLException;
}
```

| Phương thức | Ý nghĩa |
| --- | --- |
| `getSQLTypeName()` | Trả tên SQL UDT mà đối tượng Java biểu diễn; thường cần tên đầy đủ có schema |
| `readSQL(stream, typeName)` | Nhận giá trị UDT do driver đọc từ DB; gọi các `stream.readXxx()` **theo đúng thứ tự thuộc tính của SQL UDT** |
| `writeSQL(stream)` | Ghi các thuộc tính Java trở lại stream qua `stream.writeXxx()` **theo đúng thứ tự kiểu SQL** |

Đối số `typeName` trong `readSQL` là tên kiểu SQL driver truyền vào. Lớp ánh xạ có thể giữ tên này để trả lại qua `getSQLTypeName`; khi tạo đối tượng mới để ghi, phải biết trước tên kiểu SQL tương ứng.

## 3. Cài đặt một lớp Java `SQLData`

Ví dụ sau ánh xạ ba thuộc tính của kiểu SQL `ADDRESS_T`. Lớp được giữ **public** và có **constructor public không đối số** để driver có thể tạo đối tượng khi đọc giá trị UDT. Đây là yêu cầu thực tế của cơ chế ánh xạ phản xạ của JDBC cho lớp `SQLData`.

Tệp minh họa `AddressSqlData.java`:

```java
import java.sql.SQLData;
import java.sql.SQLInput;
import java.sql.SQLOutput;
import java.sql.SQLException;

public final class AddressSqlData implements SQLData {
    // Thay APP_SCHEMA bằng schema thực tế của kiểu ADDRESS_T.
    public static final String SQL_TYPE_NAME = "APP_SCHEMA.ADDRESS_T";

    private String sqlTypeName = SQL_TYPE_NAME;
    private String street;
    private String city;
    private String postalCode;

    // Driver cần constructor có thể truy cập khi ánh xạ SQL -> Java.
    public AddressSqlData() {
    }

    // Constructor ứng dụng dùng khi chuẩn bị giá trị ghi xuống DB.
    public AddressSqlData(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    @Override
    public String getSQLTypeName() throws SQLException {
        return sqlTypeName;
    }

    @Override
    public void readSQL(SQLInput input, String typeName)
            throws SQLException {
        this.sqlTypeName = typeName;

        // THỨ TỰ đọc phải trùng khai báo ADDRESS_T.
        this.street = input.readString();
        this.city = input.readString();
        this.postalCode = input.readString();
    }

    @Override
    public void writeSQL(SQLOutput output) throws SQLException {
        // THỨ TỰ ghi phải trùng khai báo ADDRESS_T.
        output.writeString(street);
        output.writeString(city);
        output.writeString(postalCode);
    }

    public AddressSnapshot toSnapshot() {
        return new AddressSnapshot(street, city, postalCode);
    }

    // Đối tượng bất biến phục vụ tầng nghiệp vụ / tầng API.
    public record AddressSnapshot(
            String street, String city, String postalCode) {
    }
}
```

Trong `readSQL`, ba lời gọi `readString()` không tìm thuộc tính theo tên; **mỗi lời gọi tiêu thụ thuộc tính kế tiếp** từ stream. Do kiểu SQL khai báo `street`, `city`, `postal_code`, thứ tự đúng là đọc `street` trước, `city` thứ hai và `postal_code` thứ ba. `writeSQL` phải phát chúng theo đúng thứ tự ấy.

Một lỗi rất nguy hiểm là vô tình đảo `city` với `postalCode` khi cả hai đều là `VARCHAR`: chương trình có thể **không ném lỗi chuyển kiểu** nhưng ghi sai dữ liệu. Vì vậy, khi kiểu SQL có nhiều thuộc tính cùng loại, kiểm thử đọc–ghi đối xứng đặc biệt quan trọng.

### Tại sao `SQLData` không tự là đối tượng bất biến?

`readSQL` được driver gọi **sau khi tạo một đối tượng** và có trách nhiệm gán các thuộc tính đã đọc. Do đó, lớp `SQLData` thường có các trường có thể gán lại bên trong. Một Java `record` thông thường có thành phần `final`, không phù hợp để driver gọi constructor không đối số rồi ghi lần lượt các trường qua `readSQL` như mẫu này.

Có thể giữ `AddressSqlData` ở tầng JDBC, rồi chuyển sang `AddressSnapshot` bất biến trước khi trả dữ liệu cho tầng nghiệp vụ. Đây là cách phân tách **đối tượng chuyển đổi JDBC** với **mô hình dữ liệu chỉ đọc**; không nên tự coi bất kỳ lớp `SQLData` nào là bất biến chỉ vì nó ánh xạ một giá trị SQL.

## 4. Đăng ký ánh xạ tên kiểu SQL sang lớp Java

Driver cần biết tên SQL UDT nào sẽ được biểu diễn bằng lớp `AddressSqlData`. JDBC hỗ trợ **type map**: một `Map<String, Class<?>>` ánh xạ **tên kiểu SQL** tới **lớp Java** cài đặt `SQLData`.

```java
import java.sql.Connection;
import java.util.HashMap;
import java.util.Map;

Map<String, Class<?>> typeMap =
        new HashMap<>(connection.getTypeMap());

typeMap.put(
        AddressSqlData.SQL_TYPE_NAME,
        AddressSqlData.class);

connection.setTypeMap(typeMap);
```

Đoạn mã giả định `connection` là một `Connection` JDBC đã mở và driver hỗ trợ `getTypeMap`/`setTypeMap`. Việc tạo bản sao bằng `new HashMap<>(...)` giúp tránh sửa trực tiếp map do driver trả về. Không phải driver nào cũng chấp nhận thay đổi type map; một số có thể ném `SQLFeatureNotSupportedException` hoặc `SQLException`.

Để tránh đổi trạng thái của `Connection`, JDBC còn có các overload đọc object với **type map tường minh**:

```java
Object value = resultSet.getObject("address_value", typeMap);
// Hoặc: resultSet.getObject(columnIndex, typeMap)
```

Với SQL UDT và driver hỗ trợ custom mapping, một ánh xạ phù hợp cho phép `getObject` trả về `AddressSqlData` do driver dựng qua `readSQL`. Nếu không có map phù hợp, một driver có thể trả `Struct` hoặc một lớp riêng của vendor; **không ép kiểu trực tiếp thành `AddressSqlData` trước khi kiểm tra kiểu thật**.

Một số lưu ý khi đăng ký:

- **Khớp tên kiểu SQL chính xác** theo cách driver công bố: schema, tên kiểu, quy tắc chữ hoa/chữ thường và định danh có dấu nháy.
- Type map có **phạm vi sử dụng theo kết nối**; một cấu hình trên kết nối A không mặc nhiên áp dụng cho kết nối B trong pool.
- Với connection pool, thay đổi trạng thái type map của kết nối cần được quản lý như những trạng thái session khác; không giả định pool luôn tự reset mọi thuộc tính.
- `getObject(column, map)` thường thích hợp khi chỉ một truy vấn cần mapping đặc biệt và driver hỗ trợ overload tương ứng.
- Không cần tạo type map cho mọi kiểu SQL nguyên thủy như `INTEGER`, `VARCHAR` hoặc `DECIMAL`; chúng đã có getter/setter JDBC thông dụng.

## 5. Ví dụ JDBC: đọc một giá trị UDT thành đối tượng Java

Giả sử bảng `customer_delivery` có cột `address_value` kiểu `ADDRESS_T` và khóa chính `customer_id`. Repository sau lấy một khách hàng qua SQL tham số hóa, yêu cầu driver ánh xạ cột UDT và chuyển đối tượng JDBC sang snapshot bất biến.

Tệp minh họa `DeliveryAddressRepository.java` (Java 17 trở lên):

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class DeliveryAddressRepository {
    public record CustomerAddress(
            long customerId,
            AddressSqlData.AddressSnapshot address) {
    }

    private final DataSource dataSource;

    public DeliveryAddressRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    public Optional<CustomerAddress> findById(long customerId)
            throws SQLException {
        String sql = """
                SELECT customer_id, address_value
                FROM customer_delivery
                WHERE customer_id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            Map<String, Class<?>> typeMap =
                    new HashMap<>(connection.getTypeMap());
            typeMap.put(AddressSqlData.SQL_TYPE_NAME, AddressSqlData.class);

            statement.setLong(1, customerId);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return Optional.empty(); // Không tồn tại hàng khách hàng.
                }

                Object raw = result.getObject("address_value", typeMap);

                if (raw == null) {
                    // Hàng tồn tại, nhưng giá trị UDT trong cột là SQL NULL.
                    return Optional.of(new CustomerAddress(customerId, null));
                }

                if (!(raw instanceof AddressSqlData mapped)) {
                    throw new SQLException(
                            "Driver did not map ADDRESS_T to AddressSqlData");
                }

                return Optional.of(new CustomerAddress(
                        customerId, mapped.toSnapshot()));
            }
        }
    }
}
```

Ở đây, `Optional.empty()` nghĩa là **không có hàng khớp `customer_id`**. Ngược lại, `Optional.of(new CustomerAddress(id, null))` nghĩa là có hàng nhưng cột `address_value` là SQL `NULL`. Hai tình huống này khác nhau và nên được phản ánh trong API truy cập dữ liệu.

Khi `ResultSet.getObject("address_value", typeMap)` được hỗ trợ, driver nhận ra tên UDT, tạo một `AddressSqlData` và gọi `readSQL(SQLInput, typeName)` để nạp ba thuộc tính. Sau khi `toSnapshot()` được gọi, mã nghiệp vụ dùng bản sao bất biến mà không giữ `ResultSet` hoặc `Connection` mở.

**Giới hạn của ví dụ:** Cú pháp tên kiểu Oracle và cách driver thực hiện mapping cần được xác minh bằng integration test trên DB đích. Nếu driver chỉ trả một `Struct`/giá trị vendor-specific hoặc không hỗ trợ overload `getObject(..., Map)`, ví dụ sẽ báo lỗi thay vì cố ép kiểu không an toàn. Trong một dự án thật, có thể bổ sung một nhánh ánh xạ `Struct` riêng sau khi xác nhận hợp đồng của driver.

## 6. Ví dụ JDBC: ghi `SQLData` bằng `SQLOutput`

Khi một đối tượng cài đặt `SQLData` được gán cho tham số SQL UDT, driver **có hỗ trợ tính năng** có thể dùng `getSQLTypeName()` để xác định kiểu SQL và gọi `writeSQL(SQLOutput)` để lần lượt chuyển các thuộc tính Java thành giá trị SQL.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public static int updateAddress(
        DataSource dataSource,
        long customerId,
        AddressSqlData.AddressSnapshot snapshot) throws SQLException {

    Objects.requireNonNull(snapshot, "snapshot");

    String sql = """
            UPDATE customer_delivery
            SET address_value = ?
            WHERE customer_id = ?
            """;

    AddressSqlData address = new AddressSqlData(
            snapshot.street(), snapshot.city(), snapshot.postalCode());

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setObject(1, address);
        statement.setLong(2, customerId);
        return statement.executeUpdate();
    }
}
```

Đoạn mã là **phương thức tĩnh minh họa**, có thể đặt vào một lớp utility hoặc repository và bổ sung import tương ứng. `setObject(1, address)` thể hiện đường ghi chuẩn khi driver hỗ trợ binding đối tượng `SQLData` tương ứng kiểu SQL. Một số driver yêu cầu cách binding riêng, dùng `Struct`, khai báo tên kiểu hoặc các API vendor-specific; nếu không hỗ trợ, `setObject` có thể phát sinh `SQLException`. Không coi khả năng đọc qua type map là bằng chứng chắc chắn rằng ghi qua `setObject` sẽ thành công.

`SQLOutput` **không chèn hàng vào bảng**. Nó chỉ viết phần biểu diễn các thuộc tính UDT cho driver. Câu `UPDATE` thực sự vẫn do `PreparedStatement.executeUpdate()` thực thi; việc xác nhận hay hoàn tác thuộc transaction của `Connection`. Nếu thao tác ghi địa chỉ là một bước trong quy trình cập nhật nhiều bảng, cần dùng **cùng `Connection` với `autoCommit = false`** và đặt `commit()`/`rollback()` ở ranh giới nghiệp vụ.

### Hình dung cách `writeSQL` được gọi

```text
AddressSqlData("12 Nguyễn Huệ", "TP. Hồ Chí Minh", "700000")
             |
       setObject(1, address)
             |
          JDBC driver
             |
      getSQLTypeName() -> APP_SCHEMA.ADDRESS_T
             |
        writeSQL(output)
             |
    writeString(street)
    writeString(city)
    writeString(postalCode)
             |
  Bind một giá trị SQL ADDRESS_T
             |
    executeUpdate() / transaction
```

**Không gọi `new SQLOutput(...)` hoặc tự `close()` stream trong lớp `AddressSqlData`.** Driver sở hữu stream và điều phối quá trình chuyển đổi. Tầng ứng dụng chỉ gọi các phương thức `setXxx`/`getXxx` và quản lý `Connection`, statement, result set bằng `try-with-resources`.

## 7. Thứ tự thuộc tính là một phần của hợp đồng SQL–Java

So sánh ba lớp thông tin phải khớp nhau:

| Vị trí | Thuộc tính SQL trong `ADDRESS_T` | `readSQL` | `writeSQL` |
| ---: | --- | --- | --- |
| 1 | `street` | `input.readString()` → `street` | `output.writeString(street)` |
| 2 | `city` | `input.readString()` → `city` | `output.writeString(city)` |
| 3 | `postal_code` | `input.readString()` → `postalCode` | `output.writeString(postalCode)` |

Giả sử migration đổi định nghĩa UDT thành `street`, `postal_code`, `city` nhưng Java vẫn dùng thứ tự cũ. Vì cả ba thuộc tính đều là chuỗi, mapping có thể không phát sinh ngoại lệ ngay; thay vào đó `city` và `postalCode` bị tráo giá trị. Điều này cho thấy **schema UDT và mã `SQLData` phải được version hóa, kiểm thử và cập nhật cùng nhau**.

Các quy tắc khi viết `readSQL`/`writeSQL`:

1. Đọc và ghi **đúng số lượng, kiểu và thứ tự** thuộc tính SQL thực tế.
2. Không phụ thuộc thứ tự trường Java do reflection trả về; viết rõ từng lời gọi `readXxx`/`writeXxx`.
3. Nếu SQL UDT đổi cấu trúc, cập nhật ánh xạ và kiểm thử hai chiều; đừng mong driver tự ghép tên thuộc tính Java.
4. Đối với thuộc tính phức tạp hoặc lồng nhau, dùng phương thức đọc/ghi tương ứng và bảo đảm type map có thể ánh xạ các UDT con khi cần.
5. Không âm thầm gán giá trị mặc định khi thiếu thuộc tính mà chưa có quy tắc nghiệp vụ.

### `SQLInput` là stream tuần tự

Một số phương thức tiêu biểu của `SQLInput`:

| Phương thức | Kiểu Java được đọc | Lưu ý |
| --- | --- | --- |
| `readString()` | `String` | Phù hợp thuộc tính chuỗi, có thể trả `null` |
| `readInt()`, `readLong()` | `int`, `long` | Nếu SQL `NULL`, cần kiểm tra `wasNull()` để phân biệt với `0` |
| `readBigDecimal()` | `BigDecimal` | Phù hợp giá trị `DECIMAL`/`NUMERIC` chính xác |
| `readDate()`, `readTimestamp()` | Kiểu ngày giờ JDBC | Chuyển sang `java.time` theo ngữ nghĩa dữ liệu và driver |
| `readObject()` | `Object` | Dùng khi thuộc tính SQL là một giá trị ánh xạ phức tạp; cần kiểm tra kiểu thực tế |
| `readArray()`, `readBlob()`, `readClob()` | Đối tượng SQL chuyên biệt | Có thể cần quản lý tài nguyên SQL riêng theo hợp đồng driver |
| `wasNull()` | `boolean` | Cho biết **thuộc tính vừa đọc gần nhất** có là SQL `NULL` không |

Ví dụ thuộc tính số `apartment_no` trong một UDT khác cho phép `NULL`:

```java
int rawApartmentNo = input.readInt();
Integer apartmentNo = input.wasNull() ? null : rawApartmentNo;
```

`input` ở đây là đối tượng `SQLInput` được truyền vào `readSQL`. Phải gọi `wasNull()` **ngay sau** `readInt()` tương ứng, trước khi đọc thuộc tính kế tiếp. Không tự dùng `0` để đại diện SQL `NULL`, vì số `0` có thể là dữ liệu hợp lệ. Với kiểu tham chiếu như `String` hoặc `BigDecimal`, các phương thức đọc thường có thể trả `null` trực tiếp.

### `SQLOutput` ghi cùng trình tự

Những phương thức tương ứng gồm `writeString`, `writeInt`, `writeLong`, `writeBigDecimal`, `writeDate`, `writeTimestamp`, `writeArray`, `writeBlob`, `writeClob` và `writeObject(SQLData)` cho giá trị UDT lồng nhau khi driver hỗ trợ. Việc chọn đúng `writeXxx` phụ thuộc kiểu SQL của **thuộc tính đang được ghi**, không phải tùy ý theo cách hiển thị của Java.

Ví dụ một phần `writeSQL` cho UDT có hai thuộc tính lần lượt là số lượng nguyên và đơn giá thập phân:

```java
// Trong phương thức writeSQL, theo thứ tự định nghĩa UDT:
output.writeInt(quantity);
output.writeBigDecimal(unitPrice);
```

Nếu cần ghi giá trị `NULL`, phải xác định phương thức thích hợp và khả năng hỗ trợ của driver cho kiểu thuộc tính. Đặc biệt, các phương thức ghi kiểu nguyên thủy như `writeInt(int)` không thể nhận `null`; đừng tự chuyển `null` thành `0` rồi xem như giữ nguyên ngữ nghĩa. Một mô hình có nhiều thuộc tính nullable đặc biệt có thể cần chiến lược chuyển đổi khác, `Struct` hoặc API vendor-specific được kiểm thử trên DB đích.

## 8. `SQLData` khác gì `Struct` và getter JDBC thông thường?

Trong JDBC có hai con đường chính để làm việc với một SQL structured value:

| Tiêu chí | `java.sql.Struct` | Lớp implements `SQLData` |
| --- | --- | --- |
| Kiểu đối tượng Java | Giao diện JDBC tổng quát | Lớp do ứng dụng tự định nghĩa |
| Truy cập thuộc tính | `getAttributes()` trả mảng `Object[]` | Lớp có trường/ phương thức Java cụ thể |
| Cần type map | Không nhất thiết để lấy cấu trúc thô; thuộc tính lồng có thể cần map | Cần ánh xạ tên UDT → lớp Java hoặc overload đọc có map |
| Đọc/ghi thứ tự | Ứng dụng tự giải nghĩa thứ tự `Object[]` | `readSQL`/`writeSQL` chứa logic tuần tự |
| Điểm mạnh | Khám phá cấu trúc, xử lý dữ liệu động | Tạo kiểu ứng dụng rõ ràng, tái sử dụng logic ánh xạ |
| Giới hạn | Ép kiểu từng thuộc tính và xử lý schema thủ công | Phụ thuộc hỗ trợ mapping UDT của driver/DB |

Ví dụ đọc `Struct` khi driver trả kiểu tổng quát:

```java
Object raw = rs.getObject("address_value");

if (raw instanceof java.sql.Struct structure) {
    System.out.println("Type: " + structure.getSQLTypeName());
    Object[] attributes = structure.getAttributes();

    // Chỉ số trong Object[] bắt đầu từ 0.
    // Kiểm tra độ dài và kiểu trước khi dùng.
    if (attributes.length != 3) {
        throw new SQLException("Unexpected ADDRESS_T attribute count");
    }
    String street = (String) attributes[0];
    String city = (String) attributes[1];
    String postalCode = (String) attributes[2];
}
```

Ở đây, `rs` là `ResultSet` còn mở và đoạn mã giả định driver trả `Struct` cùng ba thuộc tính dạng `String`. `Struct.getAttributes()` không tự cho biết `attributes[1]` là `city` nếu ứng dụng không biết schema. Cũng không có gì bảo đảm mọi UDT đều được driver chuyển thành `java.sql.Struct`; đây là **một lựa chọn thay thế cần kiểm thử**, không phải fallback mặc định.

Với kiểu SQL phổ biến, chẳng hạn `DECIMAL(12,2)` hoặc `VARCHAR`, tiếp tục dùng `rs.getBigDecimal(...)`, `rs.getString(...)`, `statement.setBigDecimal(...)` và `statement.setString(...)`. Dùng `SQLData` cho mọi cột có thể khiến mã phức tạp mà không đem lại lợi ích nào.

### Không nhầm UDT cấu trúc với JSON hay kiểu riêng của vendor

Nhiều DBMS có kiểu JSON, XML, UUID, array, geography hoặc enum. Một cột kiểu phức tạp **không tự động là SQL structured UDT được ánh xạ bằng `SQLData`**. Chẳng hạn JSON có thể được driver trả dạng chuỗi, `SQLXML` hoặc đối tượng vendor-specific tùy DB; UUID có thể dùng `getObject(..., UUID.class)` ở driver hỗ trợ. Chọn API theo kiểu SQL thực tế và tài liệu driver, đừng ép mọi kiểu nâng cao đi qua `SQLInput`/`SQLOutput`.

## 9. `NULL`, lỗi ánh xạ và transaction

### Phân biệt `NULL` của cả giá trị UDT với `NULL` trong thuộc tính

Cột `address_value` có thể là SQL `NULL` — khi đó `ResultSet.getObject(...)` có thể trả `null`, và driver **không cần tạo đối tượng `SQLData`**. Ngược lại, cả giá trị `ADDRESS_T` có thể tồn tại nhưng một thuộc tính bên trong (ví dụ `postal_code`) là `NULL`; lúc đó `readSQL` vẫn đọc giá trị cấu trúc và `input.readString()` cho thuộc tính tương ứng có thể trả `null`.

```text
SQL NULL ở cột address_value
    -> Không có giá trị ADDRESS_T
    -> ResultSet.getObject(...) == null

ADDRESS_T("12 Nguyễn Huệ", "TP. Hồ Chí Minh", NULL)
    -> Có giá trị cấu trúc
    -> Java AddressSqlData, postalCode == null
```

Lớp Java và business rule phải diễn giải hai trường hợp đúng theo nghiệp vụ. Không cố tạo đối tượng với chuỗi rỗng để thay SQL `NULL` nếu không có yêu cầu chuyển đổi rõ ràng.

### Lỗi thuộc tính sai thứ tự hoặc sai kiểu

`readSQL` và `writeSQL` được khai báo `throws SQLException`. Nếu driver không chuyển được dữ liệu hoặc số thuộc tính/kiểu không khớp, có thể nhận `SQLException`. Tuy vậy, với hai thuộc tính có kiểu tương thích (hai chuỗi, hai số), sai thứ tự có thể **không phát sinh lỗi kỹ thuật**, mà làm sai dữ liệu âm thầm. Vì vậy phải kiểm tra cả **giá trị đầu ra**, không chỉ kiểm tra có exception hay không.

Khi ứng dụng dùng `PreparedStatement.setObject(...)` với `SQLData`, nếu một thao tác ghi SQL nằm trong quy trình nhiều bước thì các lỗi chuyển đổi phải được xử lý như lỗi giao dịch khác. Ví dụ:

```java
connection.setAutoCommit(false);
try {
    // PreparedStatement.setObject(..., SQLData), executeUpdate() và
    // các câu lệnh khác trên CHÍNH connection này.
    connection.commit();
} catch (SQLException | RuntimeException failure) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
    }
    throw failure;
}
```

Đoạn trên là khuôn transaction minh họa và giả định caller sở hữu kết nối. Với một `Connection` do transaction manager quản lý, tầng con không tự ý đổi `autoCommit`, commit hoặc rollback toàn phần. `SQLData` chỉ giải quyết việc chuyển **một giá trị**; nó không kiểm soát tính nguyên tử của các câu SQL.

## 10. Giới hạn hỗ trợ của JDBC driver

Không phải cơ sở dữ liệu nào cũng hỗ trợ SQL UDT cấu trúc, và không phải driver hỗ trợ UDT nào cũng hỗ trợ trọn vẹn cơ chế ánh xạ `SQLData`/type map. Cần kiểm tra trên **đúng sản phẩm, phiên bản DB và phiên bản driver**.

| Tình huống | Hướng xử lý |
| --- | --- |
| DB không có kiểu cấu trúc tương thích | Dùng các cột SQL thông thường hoặc thiết kế bảng con phù hợp |
| Driver không hỗ trợ `getTypeMap`/`setTypeMap` | Cân nhắc overload `getObject(column, map)` nếu được hỗ trợ; hoặc API vendor-specific |
| `getObject` không trả lớp `SQLData` dù đã có map | Kiểm tra tên kiểu SQL, schema, case và hỗ trợ mapping thực tế |
| Có thể đọc nhưng `setObject` không ghi được UDT | Kiểm tra API binding của driver, `Struct` hoặc API chuyên biệt thay vì ép kiểu |
| `SQLFeatureNotSupportedException` | Chức năng JDBC đang dùng không được driver hỗ trợ; cần đường triển khai khác |
| `SQLException` do tên kiểu/thuộc tính sai | Kiểm tra DDL, schema, type map, thứ tự/kiểu thuộc tính và thông báo lỗi SQL |
| Driver trả kiểu vendor-specific | Chỉ chuyển đổi sau khi đã xác minh hợp đồng của kiểu đó; tránh ép kiểu mù |
| DDL thay đổi thứ tự thuộc tính UDT | Cập nhật `readSQL`/`writeSQL` và kiểm thử hai chiều trước khi triển khai |

Một số driver có thể cần cấu hình, cấp quyền truy cập kiểu SQL hoặc cơ chế tạo object riêng. Có thể dùng `Connection.getMetaData()` để khám phá thông tin hệ thống và phiên bản, hoặc `DatabaseMetaData.getUDTs(...)` để khảo sát những kiểu UDT được công bố. Tuy nhiên, **metadata cho thấy một UDT tồn tại không chứng minh driver hỗ trợ custom mapping hai chiều**; chỉ thử đọc/ghi thực tế mới xác nhận được.

Ví dụ dùng metadata (với catalog/schema/type pattern phải phù hợp DB):

```java
try (Connection connection = dataSource.getConnection();
     ResultSet types = connection.getMetaData().getUDTs(
             null, "APP_SCHEMA", "ADDRESS_T", null)) {

    while (types.next()) {
        System.out.println(types.getString("TYPE_NAME"));
        System.out.println(types.getInt("DATA_TYPE"));
    }
}
```

`getUDTs(...)` trả `ResultSet` chứa metadata do driver báo. Nếu bảng kết quả rỗng, có thể là DB không công bố UDT ở schema/pattern đang hỏi hoặc driver không hỗ trợ đầy đủ metadata; không tự kết luận UDT chắc chắn không tồn tại. Kiểm tra quyền, case, schema/catalog và tài liệu driver.

## 11. Hiệu năng, bảo trì và cách lựa chọn mô hình

Custom mapping tạo thuận lợi khi một UDT cấu trúc là hợp đồng chung dùng ở nhiều bảng hoặc nhiều câu truy vấn. Tuy nhiên, giải pháp cũng đặt thêm trách nhiệm lên đội phát triển: type map, constructor, độ tương thích driver, phiên bản UDT và kiểm thử chuyển đổi.

Một vài nguyên tắc thực tế:

1. **Chọn mô hình dữ liệu trước:** nếu ba thuộc tính thường được lọc, index hoặc cập nhật riêng, ba cột SQL hay bảng quan hệ chuẩn hóa có thể phù hợp hơn UDT cấu trúc.
2. **Giữ lớp mapping nhỏ và rõ ràng:** `SQLData` chỉ chuyển đổi thuộc tính, không gọi HTTP, không truy vấn DB và không cài nghiệp vụ phức tạp trong `readSQL`/`writeSQL`.
3. **Không tạo type map mới cho từng hàng:** đăng ký hoặc chuẩn bị map một lần cho truy vấn/kết nối phù hợp; tránh công việc thừa trong vòng lặp hàng nghìn bản ghi.
4. **Phân tách đối tượng mapping và mô hình nghiệp vụ:** chuyển đối tượng JDBC có thể thay đổi sang snapshot bất biến hoặc DTO trước khi trả khỏi repository khi cần.
5. **Giữ vòng đời tài nguyên ngắn:** dùng `try-with-resources` cho `ResultSet`, statement và `Connection`; driver chịu trách nhiệm với `SQLInput`/`SQLOutput`.
6. **Đo trên DB đích:** việc ánh xạ hàng triệu object phức tạp có thể tốn CPU và bộ nhớ. Chỉ chọn UDT mapping nếu nó đơn giản hóa mô hình hoặc giảm lỗi một cách đáng kể.

### Khi nào nên dùng `SQLData`?

| Trường hợp | Gợi ý |
| --- | --- |
| DB có SQL structured UDT ổn định, nhiều câu SQL cùng dùng | Cân nhắc `SQLData` nếu driver hỗ trợ custom mapping tốt |
| Ứng dụng cần đọc cấu trúc động, chưa biết trước lớp Java | `Struct` hoặc API vendor-specific có thể phù hợp hơn |
| Cột là `VARCHAR`, `DECIMAL`, `DATE` đơn giản | Dùng các getter/setter JDBC chuẩn |
| Cột là JSON/UUID/array không ánh xạ theo SQL structured UDT | Dùng API JDBC hoặc extension phù hợp kiểu cụ thể |
| Ứng dụng cần chạy trên nhiều DB không cùng hỗ trợ UDT | Ưu tiên mô hình cột/bảng quan hệ thông dụng hoặc lớp chuyển đổi tách riêng cho từng DB |
| Cấu trúc UDT thay đổi thường xuyên | Cần đánh giá chi phí thay đổi schema, lớp mapping và migration |

## 12. Kiểm thử ánh xạ `SQLData` trên driver thật

Một bài kiểm thử hợp lệ phải khẳng định **đúng dữ liệu**, **đúng SQL type**, **đúng thứ tự thuộc tính** và **đúng đường đọc/ghi**. Chỉ biên dịch được lớp `AddressSqlData` không đủ chứng minh driver sẽ dùng lớp này.

| Tình huống kiểm thử | Kết quả mong đợi |
| --- | --- |
| Đăng ký `APP_SCHEMA.ADDRESS_T` → `AddressSqlData` | Driver sử dụng ánh xạ phù hợp hoặc báo rõ không hỗ trợ |
| Đọc hàng có UDT ba thuộc tính | `street`, `city`, `postalCode` đúng giá trị và đúng vị trí |
| Ghi UDT bằng `setObject` rồi đọc lại | Ba thuộc tính được bảo toàn qua round trip trên DB/driver đích |
| Cột UDT là SQL `NULL` | Phương thức đọc phân biệt được hàng có cột `NULL` và không có hàng |
| UDT tồn tại nhưng một thuộc tính chuỗi là `NULL` | Đối tượng SQLData vẫn tồn tại; thuộc tính tương ứng là `null` |
| Hai thuộc tính chuỗi có giá trị dễ phân biệt | Phát hiện lỗi đảo thứ tự `city` và `postalCode` |
| Không đăng ký type map | Quan sát kiểu Java mặc định do driver trả; không ép kiểu tùy tiện |
| Dùng sai tên schema/type | Có lỗi ánh xạ hoặc kiểu trả về khác kỳ vọng; xử lý rõ ràng |
| Driver không hỗ trợ `getObject(..., Map)` | Phát hiện đúng lỗi hỗ trợ và chuyển sang giải pháp đã kiểm chứng |
| Đổi cấu trúc UDT ở môi trường thử nghiệm | Kiểm thử bắt được khác biệt số lượng/thứ tự/kiểu thuộc tính |
| Ghi UDT trong transaction rồi phát sinh lỗi bước sau | Rollback của DB hoàn tác các thay đổi chưa commit theo hợp đồng transaction |

Ví dụ dữ liệu cho kiểm thử hai chiều:

```text
Input Java:
  street     = "12 Nguyễn Huệ"
  city       = "TP. Hồ Chí Minh"
  postalCode = "700000"

Sau khi ghi vào SQL ADDRESS_T rồi đọc về Java:
  street     phải bằng "12 Nguyễn Huệ"
  city       phải bằng "TP. Hồ Chí Minh"
  postalCode phải bằng "700000"
```

Kiểm thử nên ghi nhận DBMS, phiên bản driver, tên kiểu SQL đầy đủ, cách đăng ký map và phương thức bind đã dùng. Nếu driver cần API vendor-specific, viết một adapter riêng và bảo đảm tầng nghiệp vụ vẫn nhận một mô hình ổn định.

## 13. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| `getObject(...)` trả `Struct`, không phải lớp `SQLData` | Chưa có type map, tên kiểu không khớp hoặc driver không hỗ trợ | Kiểm tra mapping và cơ chế hỗ trợ của driver |
| Driver không tạo được lớp mapping | Thiếu constructor public không đối số hoặc class không truy cập được | Cung cấp constructor và khả năng truy cập phù hợp |
| Thuộc tính Java bị tráo nội dung nhưng không ném lỗi | `readSQL`/`writeSQL` sai thứ tự so với SQL UDT | So lại DDL và kiểm thử round trip với giá trị phân biệt |
| Giá trị `NULL` trở thành `0` | Dùng `readInt()` nhưng quên `wasNull()` | Gọi `wasNull()` ngay sau getter nguyên thủy |
| `setObject` với `SQLData` bị từ chối | Driver không hỗ trợ binding hoặc cần API riêng | Kiểm tra khả năng ghi UDT, cân nhắc `Struct`/API vendor-specific |
| Có kiểu SQL nhưng `getUDTs` không thấy | Sai schema/case/permission hoặc metadata không đầy đủ | Kiểm tra metadata và tên kiểu thực tế |
| `getSQLTypeName()` trả tên không phù hợp | Hardcode nhầm schema hoặc DB báo tên khác | Đặt tên đầy đủ đúng với ánh xạ và xác minh bằng integration test |
| Đọc một UDT mà trả `ResultSet`/`Connection` ra ngoài | Tài nguyên JDBC có vòng đời riêng, dễ bị đóng trước khi dùng | Đọc và chuyển sang DTO/record trước khi thoát repository |
| Coi release/close stream là trách nhiệm của `SQLData` | `SQLInput`/`SQLOutput` do driver quản lý | Để driver quản lý stream, chỉ đóng tài nguyên JDBC của ứng dụng |
| Tự `commit()` trong `writeSQL` | Trộn chuyển đổi một giá trị với điều khiển giao dịch | Quản lý transaction bên ngoài lớp SQLData |

## 14. Bài tập tự kiểm tra

**Bài 1 — Phân biệt vai trò.** Khi driver đọc cột `ADDRESS_T` thành một đối tượng Java, ai tạo stream chứa các thuộc tính? Lập trình viên cài đặt phương thức nào để đọc chúng?

**Đáp án:** Driver cung cấp `SQLInput` và gọi `SQLData.readSQL(SQLInput, typeName)`; lập trình viên cài đặt `readSQL` để đọc tuần tự các thuộc tính.

**Bài 2 — Thứ tự bị sai.** SQL UDT khai báo `(street, city, postal_code)`, nhưng `writeSQL` lần lượt ghi `(street, postalCode, city)`. Vì sao chương trình có thể vẫn chạy mà dữ liệu sai?

**Đáp án:** `city` và `postal_code` đều là chuỗi nên driver có thể chấp nhận cả hai vị trí. Sau khi ghi, hai thuộc tính bị tráo ngữ nghĩa; cần sửa thứ tự và kiểm thử đọc–ghi hai chiều.

**Bài 3 — Constructor không đối số.** Vì sao một lớp `SQLData` chỉ có constructor nhận ba chuỗi có thể không được driver tự tạo khi đọc từ UDT?

**Đáp án:** Cơ chế custom mapping cần khởi tạo lớp Java rồi gọi `readSQL` để nạp thuộc tính; driver thường yêu cầu constructor public không đối số để tạo instance.

**Bài 4 — Phân biệt `NULL`.** Với `customer_delivery`, hãy giải thích sự khác nhau giữa `getObject("address_value", map) == null` và `AddressSqlData.toSnapshot().postalCode() == null`.

**Đáp án:** Trường hợp đầu không có giá trị UDT trong cột; trường hợp sau có UDT nhưng thuộc tính `postal_code` bên trong là SQL `NULL`.

**Bài 5 — Kiểu nguyên thủy nullable.** Một UDT chứa `floor_no INTEGER NULL`. Trong `readSQL`, vì sao chỉ gọi `int floor = input.readInt()` là chưa đủ?

**Đáp án:** `readInt()` không phân biệt `0` thực với SQL `NULL`; phải gọi ngay `input.wasNull()` rồi lưu vào kiểu tham chiếu như `Integer` nếu muốn giữ đúng ngữ nghĩa.

**Bài 6 — Hỗ trợ driver.** Cơ sở dữ liệu cho phép `CREATE TYPE`, nhưng `ResultSet.getObject(column, map)` ném `SQLFeatureNotSupportedException`. Có nên bắt lỗi rồi ép `ResultSet.getObject(column)` thành `AddressSqlData` không?

**Đáp án:** Không. Cần kiểm tra kiểu thực tế (`Struct` hoặc loại do vendor trả), đánh giá API hỗ trợ rồi cài đặt adapter phù hợp; ép kiểu khi chưa xác minh có thể tạo `ClassCastException`.

**Bài 7 — SQLData và transaction.** Trong một giao dịch cập nhật hai bảng, `statement.setObject(1, addressSqlData)` thành công nhưng câu `UPDATE` thứ hai lỗi. `SQLOutput.writeSQL` có tự rollback hay commit phần địa chỉ không?

**Đáp án:** Không. `SQLOutput` chỉ ghi biểu diễn thuộc tính. Transaction thuộc `Connection`; tầng gọi phải `rollback()` toàn bộ các thao tác chưa commit của cùng giao dịch.

**Bài 8 — Chọn mô hình.** Một ứng dụng cần chạy trên ba DBMS khác nhau, trong đó một DB không hỗ trợ structured UDT. Bạn có nên buộc toàn bộ mã nghiệp vụ sử dụng `SQLData` như kiểu dữ liệu trung tâm?

**Gợi ý:** Cân nhắc lưu địa chỉ thành các cột SQL thông dụng hoặc trừu tượng hóa adapter riêng từng DB; trả về DTO/record độc lập cho tầng nghiệp vụ để giảm phụ thuộc cơ chế UDT của vendor.

## Tổng kết

`SQLData`, `SQLInput` và `SQLOutput` phối hợp để ánh xạ **kiểu cấu trúc do người dùng định nghĩa** giữa SQL và Java trong JDBC. Lập trình viên cài đặt `SQLData`; driver cung cấp `SQLInput` khi đọc và `SQLOutput` khi ghi. `readSQL`/`writeSQL` phải theo **đúng thứ tự thuộc tính UDT**, còn type map giúp driver nhận ra lớp Java tương ứng với tên kiểu SQL. Việc tạo truy vấn, gán tham số, đọc hàng và quản lý transaction vẫn thuộc `PreparedStatement`, `ResultSet` và `Connection`. Vì hỗ trợ structured UDT rất khác nhau giữa DBMS/driver, hãy xác minh cả hai chiều đọc–ghi bằng integration test, xử lý `NULL` rõ ràng và giữ mô hình nghiệp vụ tách biệt khi cần tính di động.

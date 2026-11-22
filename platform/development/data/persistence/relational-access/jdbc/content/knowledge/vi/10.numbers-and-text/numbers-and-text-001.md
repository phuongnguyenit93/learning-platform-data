# Lựa chọn kiểu số nguyên theo miền giá trị trong JDBC

Khi làm việc với cơ sở dữ liệu quan hệ qua **JDBC (Java Database Connectivity)**, lập trình viên phải chọn kiểu dữ liệu ở **hai phía**: kiểu cột trong SQL và kiểu biến trong Java. Chọn kiểu chỉ dựa vào giá trị mẫu hiện tại rất dễ gây lỗi khi dữ liệu tăng lên. Ví dụ, mã đơn hàng đang là `12345` có thể vừa trong `int` hôm nay, nhưng sau vài năm hệ thống có thể phát sinh mã lớn hơn `2_147_483_647`.

Nguyên tắc quan trọng nhất là **xác định miền giá trị hợp lệ của dữ liệu, tính cả khả năng tăng trưởng, rồi chọn kiểu có thể biểu diễn toàn bộ miền đó**. Khi đọc/ghi bằng JDBC, cần kiểm tra thêm kiểu thực tế do hệ quản trị cơ sở dữ liệu và JDBC driver hỗ trợ.

## 1. Miền giá trị của các kiểu số nguyên Java

Các kiểu số nguyên nguyên thủy (`primitive`) trong Java đều là **số nguyên có dấu**. Kích thước và giới hạn của chúng được ngôn ngữ Java quy định:

| Kiểu Java | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất | Trường hợp sử dụng thường gặp |
| --- | ---: | ---: | ---: | --- |
| `byte` | 8 | -128 | 127 | Giá trị rất nhỏ khi thực sự cần miền 8 bit |
| `short` | 16 | -32.768 | 32.767 | Giá trị nhỏ, ít khi cần dùng trực tiếp trong mã nghiệp vụ |
| `int` | 32 | -2.147.483.648 | 2.147.483.647 | Số lượng, bộ đếm và chỉ số có giới hạn rõ ràng |
| `long` | 64 | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 | Khóa định danh lớn, bộ đếm dài hạn |
| `BigInteger` | Tùy độ lớn | Không cố định | Không cố định | Số nguyên vượt miền của `long` |

`BigInteger` là một **lớp** trong `java.math`, không phải kiểu nguyên thủy. Nó biểu diễn số nguyên với độ chính xác tùy ý, trong phạm vi tài nguyên bộ nhớ cho phép. Việc sử dụng `BigInteger` trong Java **không** làm cho cột SQL tự động lưu được số có độ dài bất kỳ: giới hạn của cột vẫn phải được thiết kế riêng.

Ví dụ, các khai báo sau đều hợp lệ:

```java
int availableUnits = 500_000;
long orderId = 3_500_000_000L; // L: literal kiểu long
BigInteger externalId = new BigInteger("18446744073709551615");
```

Đoạn mã trên cần `import java.math.BigInteger;`. Nếu bỏ hậu tố `L` trong một literal số nguyên quá miền `int`, Java có thể báo lỗi biên dịch; phép chuyển kiểu từ `long` sang `int` cũng có nguy cơ làm mất dữ liệu.

## 2. Phân biệt kiểu lưu trữ SQL với kiểu sử dụng trong Java

Các hệ quản trị cơ sở dữ liệu thường có những kiểu số nguyên sau. Bảng này là **định hướng ánh xạ phổ biến**, không phải bảo đảm rằng mọi sản phẩm SQL đều có cùng dải giá trị:

| Kiểu cột SQL | Kiểu Java phù hợp | Thao tác JDBC thường dùng | Lưu ý |
| --- | --- | --- | --- |
| `TINYINT` | `byte`, `short` hoặc `int` | `getByte` / `getShort` / `getInt`, `setInt` | Miền có dấu/không dấu thay đổi theo hệ CSDL |
| `SMALLINT` | `short` hoặc `int` | `getShort` / `getInt`, `setInt` | Dùng `int` trong Java vẫn hợp lý cho phép tính |
| `INTEGER` / `INT` | `int` | `getInt`, `setInt` | Thường tương ứng số nguyên có dấu 32 bit |
| `BIGINT` | `long` | `getLong`, `setLong` | Phù hợp khi cột lưu số nguyên có dấu 64 bit |
| `DECIMAL(p, 0)` / `NUMERIC(p, 0)` | `BigDecimal`; chuyển sang `BigInteger` khi cần | `getBigDecimal`, `setBigDecimal` | `p` giới hạn số chữ số; `scale = 0` để lưu số nguyên |

**Không nên ép mọi SQL `SMALLINT` thành Java `short`.** Ví dụ cột `package_count SMALLINT` có ràng buộc từ 0 đến 1.000 thì dùng `int` trong Java vẫn thuận tiện và an toàn, miễn là kiểm tra dữ liệu trước khi ghi. Kiểu cột quyết định dung lượng/giới hạn lưu trữ, còn kiểu biến Java phải đáp ứng cả việc xử lý nghiệp vụ.

Cần đặc biệt lưu ý sự khác biệt giữa các hệ quản trị:

- MySQL có `TINYINT` có dấu (thường -128 đến 127) và `TINYINT UNSIGNED` (0 đến 255); `BIGINT UNSIGNED` có thể lớn hơn `Long.MAX_VALUE`.
- SQL Server có `TINYINT` từ 0 đến 255. Đọc trực tiếp tất cả giá trị này bằng `byte` có dấu của Java là không phù hợp.
- PostgreSQL không cung cấp kiểu cột `TINYINT` thông thường; `SMALLINT`, `INTEGER`, `BIGINT` là các lựa chọn phổ biến.
- SQLite có quy tắc kiểu dữ liệu và lưu trữ động riêng; không được suy ra rằng một khai báo `INTEGER` sẽ áp đặt đúng cùng giới hạn như `int` của Java.

Vì vậy, trước khi quyết định ánh xạ, cần đọc tài liệu của **hệ quản trị và phiên bản JDBC driver đang sử dụng**. Với cột do người khác tạo, có thể tham khảo `ResultSetMetaData` để kiểm tra kiểu, độ chính xác và khả năng mang dấu; metadata chỉ là thông tin hỗ trợ, không thay thế hợp đồng schema.

## 3. Chọn kiểu từ miền giá trị nghiệp vụ

Hãy trả lời lần lượt bốn câu hỏi:

1. **Giá trị nhỏ nhất và lớn nhất là bao nhiêu?** Số lượng tồn kho có thể âm không? Mã định danh có tăng liên tục không?
2. **Có khả năng vượt giới hạn trong tương lai không?** Mã sự kiện tăng theo toàn hệ thống có thể vượt 2,1 tỷ dù hiện nay chỉ có vài nghìn bản ghi.
3. **Cột SQL đang dùng kiểu gì và có `UNSIGNED` hay không?** Không chọn `int` nếu cột `BIGINT` có thể chứa giá trị lớn hơn `Integer.MAX_VALUE`.
4. **Có phép tính trung gian vượt giới hạn không?** Hai toán hạng `int` có thể tạo kết quả lớn hơn `int` ngay cả khi từng toán hạng đều hợp lệ.

Ví dụ:

| Dữ liệu nghiệp vụ | Miền dự kiến | Gợi ý thiết kế |
| --- | --- | --- |
| Số kiện trong một phiếu nhập | 0–1.000 | SQL `SMALLINT`; Java `int`, kèm kiểm tra biên |
| Số đơn vị tồn kho trên một mặt hàng | 0–2.000.000.000 | SQL `INTEGER`; Java `int` |
| Mã bản ghi tăng dài hạn | Có thể vượt 2.147.483.647 | SQL `BIGINT` có dấu; Java `long` |
| Mã số ngoài hệ thống, có thể đến 18.446.744.073.709.551.615 | Vượt `Long.MAX_VALUE` | SQL `DECIMAL(20,0)`; Java `BigInteger` qua JDBC `BigDecimal` |

**Chọn theo giới hạn hợp lệ, không theo số chữ số của dữ liệu mẫu.** Với trường chỉ nhận giá trị 0–1.000, `SMALLINT` đáp ứng tốt dù Java thường xử lý nó như `int`. Với khóa định danh cần phát triển lâu dài, `BIGINT`/`long` thường thực tế hơn `INTEGER`/`int`.

## 4. Ví dụ: thiết kế bảng và ghi/đọc dữ liệu bằng JDBC

Giả sử hệ thống kho lưu mã mặt hàng, số kiện và số đơn vị tồn kho. Miền nghiệp vụ là:

- `item_id`: số dương, có thể tăng vượt 2,1 tỷ.
- `package_count`: từ 0 đến 1.000.
- `quantity`: từ 0 đến 2.000.000.000.

Một schema SQL minh họa:

```sql
CREATE TABLE warehouse_stock (
    item_id       BIGINT PRIMARY KEY,
    package_count SMALLINT NOT NULL
                  CHECK (package_count BETWEEN 0 AND 1000),
    quantity      INTEGER NOT NULL
                  CHECK (quantity BETWEEN 0 AND 2000000000)
);
```

`CHECK` là lớp kiểm soát ở phía cơ sở dữ liệu. Cú pháp và khả năng thực thi ràng buộc cần được xác minh trên hệ quản trị được triển khai.

Đoạn Java sau dùng `long` cho mã mặt hàng và `int` cho hai số lượng. Nó kiểm tra biên **trước** khi gửi dữ liệu qua `PreparedStatement`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.OptionalInt;

public final class WarehouseStockRepository {
    private WarehouseStockRepository() {}

    public static void insert(
            Connection connection,
            long itemId,
            int packageCount,
            int quantity) throws SQLException {

        if (itemId <= 0
                || packageCount < 0 || packageCount > 1_000
                || quantity < 0 || quantity > 2_000_000_000) {
            throw new IllegalArgumentException("Gia tri nam ngoai mien cho phep");
        }

        String sql =
                "INSERT INTO warehouse_stock " +
                "(item_id, package_count, quantity) VALUES (?, ?, ?)";

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, itemId);      // SQL BIGINT
            statement.setInt(2, packageCount); // SQL SMALLINT, da kiem tra mien
            statement.setInt(3, quantity);     // SQL INTEGER
            statement.executeUpdate();
        }
    }

    public static OptionalInt findQuantity(
            Connection connection, long itemId) throws SQLException {

        String sql = "SELECT quantity FROM warehouse_stock WHERE item_id = ?";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, itemId);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    return OptionalInt.empty();
                }
                // quantity duoc khai bao NOT NULL trong schema.
                return OptionalInt.of(result.getInt("quantity"));
            }
        }
    }
}
```

Các điểm cần hiểu:

- `setLong` giữ nguyên miền 64 bit của `item_id`. `setInt` dùng được với `package_count` vì dữ liệu đã được giới hạn trong miền lưu trữ của `SMALLINT`; việc chấp nhận chuyển đổi còn phụ thuộc driver và schema cụ thể.
- Dấu `?` là tham số được truyền riêng qua `PreparedStatement`; không cần nối giá trị số vào chuỗi SQL.
- `try-with-resources` đóng `PreparedStatement` và `ResultSet` sau khi dùng; `Connection` thuộc về bên gọi nên ví dụ không đóng nó.
- `OptionalInt.empty()` có nghĩa **không tìm thấy hàng**. Giá trị `quantity = 0` vẫn là một kết quả hợp lệ, phân biệt với không tìm thấy.

Nếu thao tác có thể cập nhật `quantity`, việc giữ ràng buộc trong SQL đặc biệt cần thiết: kiểm tra ở Java không loại bỏ mọi trường hợp ghi từ dịch vụ khác hay phép cộng dồn gây vượt biên.

## 5. Tránh mất dữ liệu khi chuyển đổi kiểu

### 5.1. Thu hẹp `long` sang `int`

Ví dụ sau **biên dịch được nhưng cho kết quả sai**:

```java
long orderId = 3_500_000_000L;
int narrowed = (int) orderId; // Mat phan bit cao, gia tri bi thay doi
```

Nếu bắt buộc phải đổi sang `int`, hãy dùng phép chuyển đổi có kiểm tra:

```java
int safeValue = Math.toIntExact(orderId);
// Nem ArithmeticException khi orderId nam ngoai mien int.
```

Tương tự, không chọn `ResultSet.getInt("id")` chỉ vì những mã đang tồn tại còn nhỏ trong khi cột là `BIGINT`. Khi cột vượt giới hạn `int`, hành vi ép kiểu qua driver có thể gây lỗi hoặc không bảo toàn giá trị; dùng `getLong` nếu dữ liệu nằm trong miền `long`.

### 5.2. Tràn số ngay trong phép toán trung gian

```java
int boxes = 1_500_000;
int unitsPerBox = 2_000;

long wrongTotal = boxes * unitsPerBox;        // Nhan bang int truoc
long correctTotal = (long) boxes * unitsPerBox; // Nhan bang long
```

Phép nhân đầu tiên được thực hiện với kiểu `int` nên đã tràn trước khi gán sang `long`. Nếu cần báo lỗi khi cộng/trừ/nhân vượt giới hạn, Java cung cấp các phương thức như `Math.addExact` và `Math.multiplyExact`.

Phía SQL cũng cần cân nhắc kiểu kết quả của `SUM` hoặc các biểu thức số học: cách mở rộng kiểu của phép tổng hợp có thể khác nhau giữa các hệ quản trị. Việc đọc kết quả cuối bằng `getLong` không tự sửa được phép tính đã tràn ở phía SQL.

### 5.3. Phân biệt giá trị SQL `NULL` với số 0

Các getter kiểu nguyên thủy, ví dụ `getInt` và `getLong`, trả về **0** khi cột SQL có giá trị `NULL`. Muốn phân biệt hai trường hợp, gọi `wasNull()` **ngay sau getter tương ứng**:

```java
int threshold = result.getInt("warning_threshold");
Integer warningThreshold = result.wasNull() ? null : threshold;
```

Không gọi thêm getter khác giữa `getInt` và `wasNull`, vì `wasNull` báo trạng thái của **lần đọc cột gần nhất**. Với driver hỗ trợ tốt JDBC 4.1+, cũng có thể cân nhắc `getObject("warning_threshold", Integer.class)` để nhận `null` trực tiếp.

### 5.4. Số vượt `long`: dùng `DECIMAL` và chuyển đổi chính xác

Một số hệ thống ngoài dùng ID số nguyên không âm vượt giới hạn `long`, chẳng hạn giá trị lớn nhất của số nguyên 64 bit **không dấu**. Java `BigInteger` xử lý được, còn với cột `DECIMAL(20,0)` nên chuyển qua `BigDecimal` khi giao tiếp JDBC:

```java
import java.math.BigDecimal;
import java.math.BigInteger;

BigInteger externalId = new BigInteger("18446744073709551615");

// Ghi vào tham so cua cot DECIMAL(20,0).
statement.setBigDecimal(1, new BigDecimal(externalId));

// Doc tu ResultSet cua cot DECIMAL(20,0).
BigDecimal numericValue = result.getBigDecimal("external_id");
BigInteger exactId = numericValue == null
        ? null
        : numericValue.toBigIntegerExact();
```

`toBigIntegerExact()` từ chối số có phần thập phân khác 0 thay vì âm thầm cắt bỏ. `DECIMAL(20,0)` có tối đa 20 chữ số thập phân: vẫn cần kiểm tra giới hạn độ dài theo schema trước khi ghi. Nếu giữ số nguyên chỉ để hiển thị như một mã định danh từ hệ thống ngoài, hãy đánh giá xem **chuỗi ký tự** có phù hợp hơn kiểu số hay không, đặc biệt khi mã có số 0 ở đầu và không cần phép toán số học.

## 6. Kiểm tra schema và lựa chọn getter trong JDBC

Khi tiếp nhận một bảng chưa rõ định nghĩa, có thể xem metadata của kết quả truy vấn:

```java
ResultSetMetaData meta = result.getMetaData();
int index = result.findColumn("item_id");

int jdbcType = meta.getColumnType(index); // Vi du: java.sql.Types.BIGINT
int precision = meta.getPrecision(index);
int scale = meta.getScale(index);
boolean signed = meta.isSigned(index);
```

Đoạn này cần `import java.sql.ResultSetMetaData;`. `getColumnType` trả về mã `java.sql.Types`, còn `precision`, `scale` và `signed` cung cấp thêm thông tin do driver báo cáo. Không dùng những thông số này như phép kiểm tra duy nhất: cần đối chiếu với DDL, ràng buộc `CHECK`, tùy chọn `UNSIGNED` và tài liệu driver.

Đối với câu truy vấn đếm:

```java
// COUNT(*) co the lon hon gioi han int.
long totalRows = result.getLong("total_rows");
```

Chọn `long` cho bộ đếm có khả năng vượt 2,1 tỷ, ví dụ số giao dịch trên toàn hệ thống. Với một cột cụ thể có thể chứa `NULL`, vẫn áp dụng `wasNull()` như phần trên.

## 7. Các lỗi thiết kế phổ biến và cách tránh

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chọn `int` cho khóa `BIGINT` tăng dài hạn | Mã vượt 2,1 tỷ có thể không đọc/ghi an toàn | Dùng `long` và `setLong`/`getLong` |
| Mặc định `TINYINT` luôn có dấu | Giá trị 128–255 không nằm trong `byte` Java | Xác nhận kiểu SQL và dùng `short`/`int` nếu cần |
| Cho rằng `BIGINT UNSIGNED` luôn vừa `long` | Dữ liệu vượt `Long.MAX_VALUE` | Dùng chiến lược `BigInteger`/`BigDecimal` hoặc thay đổi schema |
| Ép kiểu thu hẹp không kiểm tra | Mất bit hoặc thay đổi giá trị | Kiểm tra miền; dùng `Math.toIntExact` nếu đổi sang `int` |
| Đọc cột nullable bằng `getInt` rồi coi 0 là dữ liệu thật | Không phân biệt `NULL` với 0 | Gọi `wasNull()` ngay sau getter |
| Gán phép nhân `int * int` vào `long` | Tràn số xảy ra trước phép gán | Chuyển một toán hạng sang `long` trước khi nhân |
| Chỉ kiểm tra dữ liệu ở Java | SQL có thể nhận dữ liệu từ nhiều nguồn | Kết hợp kiểm tra Java và ràng buộc ở CSDL |

## 8. Tự kiểm tra kiến thức

**Tình huống 1.** Một cột `order_id BIGINT` đang có mã lớn nhất là 500.000. Có nên đọc bằng `getInt` để tiết kiệm bộ nhớ?

**Gợi ý:** Không. Kiểu cột cho phép miền lớn hơn `int`; nên dùng `long`/`getLong` khi schema dùng `BIGINT` có dấu.

**Tình huống 2.** Một cột `TINYINT UNSIGNED` có thể nhận giá trị 200. Java `byte` có đủ miền biểu diễn không?

**Gợi ý:** Không. `byte` có dấu chỉ tới 127; cân nhắc `short` hoặc `int` và getter tương ứng.

**Tình huống 3.** Biểu thức `long total = 2_000_000 * 2_000;` có an toàn không?

**Gợi ý:** Không. Hai toán hạng mặc định là `int`, phép nhân tràn trước khi gán. Sửa thành `2_000_000L * 2_000`.

**Tình huống 4.** Một mã số nguyên bên ngoài có 20 chữ số và lớn hơn `Long.MAX_VALUE`. Nên dùng `getLong` hay `getBigDecimal`?

**Gợi ý:** Với cột `DECIMAL(20,0)`, chọn `getBigDecimal` rồi `toBigIntegerExact()` nếu cần thao tác với `BigInteger`.

## Ghi nhớ

Với JDBC, quyết định kiểu số nguyên là quyết định **xuyên suốt từ miền giá trị nghiệp vụ → schema SQL → API đọc/ghi JDBC → phép toán Java**. `int` thuận tiện cho số lượng có biên rõ ràng, `long` phù hợp cho nhiều khóa và bộ đếm lớn, còn các giá trị vượt 64 bit cần chiến lược dữ liệu chính xác như `DECIMAL(p,0)` kết hợp `BigDecimal`/`BigInteger`. Luôn tính cả giá trị âm, `NULL`, kiểu không dấu và nguy cơ tràn số ở các bước trung gian.

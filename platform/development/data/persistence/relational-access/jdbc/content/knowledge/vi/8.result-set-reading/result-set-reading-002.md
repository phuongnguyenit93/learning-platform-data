# Duyệt bản ghi bằng next() và xử lý tập kết quả rỗng trong JDBC

Trong **JDBC (Java Database Connectivity)**, ứng dụng Java truy vấn cơ sở dữ liệu quan hệ thường nhận dữ liệu qua **ResultSet**. Khác với danh sách Java có thể truy cập ngay phần tử đầu tiên, ResultSet sử dụng **con trỏ (cursor)** để định vị dòng dữ liệu hiện tại. Trước khi đọc giá trị một dòng, chương trình thường phải gọi **next()**.

Hiểu đúng **ResultSet.next()** giúp giải quyết hai tình huống rất phổ biến: **duyệt nhiều bản ghi** và **xử lý truy vấn không trả về bản ghi nào**. Nếu viết sai, ứng dụng có thể bỏ qua dòng đầu tiên, đọc dữ liệu khi con trỏ chưa hợp lệ hoặc nhầm “không tìm thấy dữ liệu” với “truy vấn thất bại”.

## 1. ResultSet là gì và nằm ở đâu trong luồng JDBC?

Với một truy vấn SELECT, luồng làm việc điển hình là:

~~~mermaid
flowchart LR
    A[Connection] --> B[PreparedStatement]
    B --> C[executeQuery]
    C --> D[ResultSet]
    D --> E[next]
    E --> F{Có dòng tiếp theo?}
    F -- Có --> G[Đọc các cột bằng getXxx]
    G --> E
    F -- Không --> H[Hoàn tất và đóng tài nguyên]
~~~

Ví dụ truy vấn:

~~~sql
SELECT id, name, price
FROM products
WHERE active = ?
ORDER BY id
~~~

Trong Java:

~~~java
String sql = "SELECT id, name, price " +
             "FROM products WHERE active = ? ORDER BY id";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setBoolean(1, true);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long id = resultSet.getLong("id");
            String name = resultSet.getString("name");
            java.math.BigDecimal price = resultSet.getBigDecimal("price");
            System.out.println(id + " - " + name + " - " + price);
        }
    }
}
~~~

Ví dụ giả định biến **connection** là một Connection còn mở và bảng **products** có các cột được dùng trong truy vấn. Ở đây, **PreparedStatement** và **ResultSet** do đoạn mã tạo sẽ được tự động đóng nhờ **try-with-resources**. Quyền đóng Connection phụ thuộc nơi quản lý nó; nếu Connection được truyền từ bên ngoài, đoạn mã không tự đóng Connection.

Phương thức **executeQuery()** thực thi truy vấn và trả về một ResultSet để đọc. Tập kết quả có thể có **0, 1 hoặc nhiều dòng**. Khi SELECT khớp 0 dòng, phương thức thông thường vẫn trả về một ResultSet hợp lệ, nhưng lần gọi **next()** đầu tiên cho kết quả **false**.

## 2. Vị trí con trỏ trước và sau mỗi lần next()

Với ResultSet thông dụng chỉ đọc tiến về phía trước (**TYPE_FORWARD_ONLY**), con trỏ bắt đầu ở vị trí **trước dòng đầu tiên**. Mỗi lần gọi **next()**, JDBC cố chuyển con trỏ sang dòng tiếp theo.

Giả sử truy vấn trả về ba dòng theo thứ tự id = 10, 20, 30:

~~~text
Lúc vừa có ResultSet:
  [con trỏ ở trước dòng đầu]  [id=10]  [id=20]  [id=30]

Gọi next() lần 1 -> true:   [id=10]  <-- con trỏ
Gọi next() lần 2 -> true:   [id=20]  <-- con trỏ
Gọi next() lần 3 -> true:   [id=30]  <-- con trỏ
Gọi next() lần 4 -> false:  [sau dòng cuối]
~~~

Ý nghĩa của giá trị trả về:

| Giá trị từ next() | Trạng thái con trỏ | Được đọc cột bằng getXxx() không? |
| --- | --- | --- |
| **true** | Đang ở một dòng dữ liệu hợp lệ | **Có**. |
| **false** ngay lần đầu | Không có dòng nào trong kết quả | **Không**. |
| **false** sau khi đọc hết | Không còn dòng tiếp theo | **Không**. |

Phương thức **next()** có thể ném **SQLException** khi JDBC gặp lỗi. Ngoại lệ này là **lỗi truy vấn/đọc dữ liệu**, khác hoàn toàn với việc trả về **false** vì không còn dòng.

Khi vừa nhận được ResultSet, chưa có “dòng hiện tại” để đọc. Ví dụ sau sai:

~~~java
try (ResultSet resultSet = statement.executeQuery()) {
    // SAI: con trỏ chưa được next() đưa vào một dòng.
    String name = resultSet.getString("name");
}
~~~

Cách đúng:

~~~java
try (ResultSet resultSet = statement.executeQuery()) {
    if (resultSet.next()) {
        String name = resultSet.getString("name");
        System.out.println(name);
    }
}
~~~

Sau khi **next()** trả về **false**, cũng không được tiếp tục gọi **getString()**, **getLong()** hoặc những phương thức lấy cột trên một “dòng hiện tại” không còn hợp lệ.

## 3. Duyệt toàn bộ dòng với while (resultSet.next())

Nếu truy vấn có thể trả về nhiều bản ghi, mẫu thường dùng là:

~~~java
try (ResultSet resultSet = statement.executeQuery()) {
    while (resultSet.next()) {
        // Mỗi lượt lặp đang đứng trên một dòng hợp lệ.
        long id = resultSet.getLong("id");
        String name = resultSet.getString("name");
        // Xử lý dòng hiện tại.
    }
}
~~~

Lý do dùng **while**:

1. **next()** vừa kiểm tra có dòng tiếp theo hay không, vừa **di chuyển** con trỏ.
2. Nếu còn dòng, khối thân vòng lặp xử lý chính dòng đó.
3. Khi hết dòng, next() trả về false và vòng lặp dừng.
4. Nếu kết quả rỗng, thân vòng lặp **không chạy lần nào**, không gây lỗi truy cập dòng.

Với tập dữ liệu lớn, có thể xử lý từng dòng khi duyệt thay vì đưa tất cả vào List. Tuy nhiên, khả năng stream thực tế, việc tải trước dữ liệu và kích thước fetch phụ thuộc JDBC driver, câu SQL và cách cấu hình kết nối.

### Ví dụ: lấy danh sách sản phẩm thành List

Trong ứng dụng có trang danh sách sản phẩm, thường cần ánh xạ ResultSet sang các đối tượng Java để trả về tầng nghiệp vụ:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class ProductReader {
    public static final class Product {
        public final long id;
        public final String name;
        public final BigDecimal price;

        public Product(long id, String name, BigDecimal price) {
            this.id = id;
            this.name = name;
            this.price = price;
        }
    }

    public List<Product> findActiveProducts(Connection connection)
            throws SQLException {
        String sql = "SELECT id, name, price FROM products " +
                     "WHERE active = ? ORDER BY id";
        List<Product> products = new ArrayList<>();

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBoolean(1, true);

            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    Product product = new Product(
                            resultSet.getLong("id"),
                            resultSet.getString("name"),
                            resultSet.getBigDecimal("price"));
                    products.add(product);
                }
            }
        }
        return products;
    }
}
~~~

Nếu không có sản phẩm đang hoạt động, phương thức trả về **List rỗng**, không phải null. Bên gọi có thể kiểm tra **products.isEmpty()**. Nếu có nhiều dòng, mỗi dòng được chuyển thành một Product. Việc đóng ResultSet không ảnh hưởng đến các đối tượng Product đã tạo.

Nếu khối lượng dữ liệu cực lớn, trả về toàn bộ List có thể tốn bộ nhớ; khi đó nên cân nhắc **phân trang**, **giới hạn số dòng** hoặc xử lý từng dòng thông qua callback khi ResultSet còn mở.

## 4. Xử lý kết quả rỗng bằng lần gọi next() đầu tiên

Kết quả rỗng nghĩa là **câu SELECT được thực thi nhưng không tìm được dòng thỏa điều kiện**. Đây thường là tình huống nghiệp vụ bình thường, chẳng hạn:

- Tìm sản phẩm theo ID không tồn tại.
- Lọc đơn hàng của khách hàng chưa từng đặt hàng.
- Tìm bản ghi trong khoảng thời gian không có dữ liệu.
- Tra cứu email chưa được đăng ký.

Ví dụ:

~~~sql
SELECT id, email
FROM customers
WHERE id = 999999
~~~

Nếu không có customer nào phù hợp, biểu diễn khái niệm:

~~~text
ResultSet có số dòng = 0
    |
    +-- resultSet.next() -> false
    |
    +-- Không gọi getLong("id") hoặc getString("email")
~~~

Mẫu kiểm tra kết quả rỗng:

~~~java
try (ResultSet resultSet = statement.executeQuery()) {
    if (!resultSet.next()) {
        System.out.println("Không tìm thấy bản ghi nào.");
    } else {
        System.out.println("Bản ghi đầu tiên: " +
                           resultSet.getString("email"));
    }
}
~~~

Trong nhánh **else**, con trỏ đã nằm trên dòng đầu tiên nên có thể đọc các cột ngay. Nếu truy vấn có nhiều dòng, ví dụ này chỉ đọc **dòng đầu**, vì chưa gọi next() thêm lần nữa.

### Khi tìm theo khóa duy nhất, Optional là một lựa chọn tốt

Nếu truy vấn theo khóa chính và mong đợi tối đa một dòng, có thể trả về **Optional**:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

public Optional<String> findEmailById(Connection connection, long id)
        throws SQLException {
    String sql = "SELECT email FROM customers WHERE id = ?";

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, id);
        try (ResultSet resultSet = statement.executeQuery()) {
            if (!resultSet.next()) {
                return Optional.empty();
            }
            return Optional.ofNullable(resultSet.getString("email"));
        }
    }
}
~~~

Giả định cột **id** là khóa duy nhất và **email** có thể NULL. Chú ý **Optional.empty()** trong ví dụ có thể mang **hai ý nghĩa**: không có khách hàng, hoặc có khách hàng nhưng email là SQL NULL. Nếu ứng dụng phải phân biệt hai trường hợp, hãy trả về **Optional<Customer>** (một đối tượng biểu diễn cả bản ghi) thay vì Optional của một cột có thể null.

Với điều kiện bảo đảm duy nhất và cột được chọn có ràng buộc **NOT NULL**, Optional của giá trị cột có thể đủ rõ ràng.

## 5. Muốn kiểm tra rỗng rồi vẫn duyệt tất cả các dòng?

Một lỗi thường gặp là gọi **next()** để “kiểm tra có dòng” rồi mới gọi vòng **while (next())**:

~~~java
try (ResultSet resultSet = statement.executeQuery()) {
    if (resultSet.next()) {
        // SAI: lần next() ở if đã chuyển con trỏ tới dòng đầu.
        // Vòng while dưới đây bắt đầu từ dòng THỨ HAI.
        while (resultSet.next()) {
            System.out.println(resultSet.getLong("id"));
        }
    }
}
~~~

Với kết quả chỉ có một dòng, đoạn này **không in dòng nào**. Với ba dòng, nó chỉ in dòng thứ hai và thứ ba.

Có hai cách sửa:

**Cách A — Để vòng while tự xử lý rỗng, dùng biến đánh dấu:**

~~~java
boolean found = false;

try (ResultSet resultSet = statement.executeQuery()) {
    while (resultSet.next()) {
        found = true;
        System.out.println(resultSet.getLong("id"));
    }
}

if (!found) {
    System.out.println("Không có bản ghi phù hợp.");
}
~~~

**Cách B — Dùng if để kiểm tra dòng đầu, rồi do-while để không bỏ dòng đầu:**

~~~java
try (ResultSet resultSet = statement.executeQuery()) {
    if (!resultSet.next()) {
        System.out.println("Kết quả rỗng.");
    } else {
        do {
            System.out.println(resultSet.getLong("id"));
        } while (resultSet.next());
    }
}
~~~

Ở **Cách B**, khi vào nhánh else, con trỏ đang ở dòng đầu tiên. **do-while** xử lý dòng này trước, rồi mới gọi next() để chuyển sang dòng tiếp theo. Hai cách đều hoạt động với kết quả 0, 1 và nhiều dòng.

Trong hầu hết trường hợp chỉ cần đọc toàn bộ dòng, **while (resultSet.next())** là phương án ngắn gọn và dễ hiểu nhất. Chỉ thêm biến **found** hoặc nhánh kiểm tra rỗng khi nghiệp vụ cần thông báo riêng.

## 6. Không nhầm tập kết quả rỗng với cột có giá trị SQL NULL

Hai tình huống rất khác nhau:

1. **Không có dòng:** next() đầu tiên trả về false.
2. **Có dòng, nhưng một cột có SQL NULL:** next() trả về true, nhưng getter của cột tương ứng trả về null hoặc giá trị mặc định của kiểu nguyên thủy.

Ví dụ truy vấn:

~~~sql
SELECT id, phone
FROM customers
WHERE id = ?
~~~

Giả sử có khách hàng với id = 7 nhưng **phone IS NULL**. Khi đó:

~~~java
try (ResultSet resultSet = statement.executeQuery()) {
    if (resultSet.next()) {
        // Có dòng, dù giá trị phone có thể NULL.
        long id = resultSet.getLong("id");
        String phone = resultSet.getString("phone");

        if (phone == null) {
            System.out.println("Khách hàng " + id +
                               " chưa cung cấp số điện thoại.");
        }
    } else {
        System.out.println("Không tồn tại khách hàng.");
    }
}
~~~

Nếu cột mang kiểu SQL số nguyên mà ứng dụng đọc bằng **getInt()** hoặc **getLong()**, JDBC trả về **0** khi giá trị cột là NULL; cần gọi **wasNull()** ngay sau getter để phân biệt SQL NULL với số 0 thật:

~~~java
int rewardPoints = resultSet.getInt("reward_points");
boolean missingPoints = resultSet.wasNull();

if (missingPoints) {
    System.out.println("Số điểm chưa có dữ liệu (SQL NULL).");
} else {
    System.out.println("Điểm: " + rewardPoints);
}
~~~

**wasNull()** cho biết *giá trị của cột vừa được đọc* có phải SQL NULL hay không; nếu đọc cột khác giữa getInt() và wasNull(), phép kiểm tra có thể không còn phản ánh cột ban đầu.

Phương thức **getString()** trả về **null** cho SQL NULL nên có thể kiểm tra trực tiếp. Với một số driver hỗ trợ ánh xạ kiểu phù hợp, **getObject()** có thể trả về đối tượng Java nullable; phải xem kiểu SQL, kiểu Java yêu cầu và khả năng của driver.

## 7. Kết quả rỗng không đồng nghĩa câu SQL bị lỗi

Đây là ba loại kết quả cần tách biệt trong tầng truy cập dữ liệu:

| Tình huống | Dấu hiệu | Ứng dụng nên xử lý thế nào? |
| --- | --- | --- |
| Có dòng khớp | next() trả **true** | Đọc dữ liệu và chuyển thành kết quả nghiệp vụ. |
| Không có dòng khớp | next() đầu tiên trả **false** | Trả **Optional.empty()**, List rỗng, hoặc thông báo không tìm thấy tùy API. |
| Lỗi SQL/kết nối/driver | executeQuery(), next() hoặc getter ném **SQLException** | Ghi nhận/chuyển tiếp lỗi thích hợp, có thể rollback transaction. |

Không nên bắt mọi SQLException rồi trả về List rỗng:

~~~java
// KHÔNG NÊN: che giấu sự cố như thể cơ sở dữ liệu không có dữ liệu.
try {
    return loadProducts(connection);
} catch (SQLException error) {
    return java.util.Collections.emptyList();
}
~~~

Nếu đường truyền đến cơ sở dữ liệu bị mất hoặc tên cột trong SQL sai, **trả List rỗng** sẽ khiến tầng gọi hiểu nhầm rằng việc truy vấn thành công và không có sản phẩm.

Thay vào đó, để **SQLException** được chuyển lên tầng có trách nhiệm xử lý, hoặc ánh xạ nó sang lỗi ứng dụng có ngữ nghĩa rõ ràng mà vẫn giữ nguyên nguyên nhân.

### Lưu ý với COUNT(*)

Một câu **SELECT COUNT(*)** không có GROUP BY thường trả về **một dòng** chứa tổng số, ngay cả khi không có bản ghi nào thỏa điều kiện:

~~~sql
SELECT COUNT(*) AS total
FROM products
WHERE active = ?
~~~

Khi không có sản phẩm đang hoạt động:

~~~text
resultSet.next() -> true
resultSet.getLong("total") -> 0
~~~

Do đó, **số lượng bằng 0** không phải lúc nào cũng là **ResultSet rỗng**. Với truy vấn GROUP BY, tập kết quả có thể rỗng khi không có nhóm phù hợp. Cần hiểu **hình dạng kết quả của SQL** trước khi quyết định cách xử lý.

## 8. Đọc một dòng hay nhiều dòng: chọn mẫu phù hợp

| Nhu cầu truy vấn | Mẫu duyệt | Giá trị trả về gợi ý |
| --- | --- | --- |
| Tra một bản ghi theo khóa chính | **if (rs.next())** | **Optional<Entity>** |
| Lấy toàn bộ sản phẩm theo điều kiện | **while (rs.next())** | **List<Entity>**, có thể rỗng |
| Duyệt và xử lý từng dòng theo luồng | **while (rs.next())** | Gọi callback/consumer trong khi tài nguyên còn mở |
| Phát hiện rỗng và duyệt tất cả | **while** + biến found; hoặc **if** + **do-while** | Trả kết quả và trạng thái có dữ liệu |
| Đọc một số tổng hợp từ COUNT(*) | Kiểm tra **rs.next()**, đọc cột total | Số nguyên, có thể là 0 |

### Mong đợi một dòng duy nhất thì sao?

Nếu nghiệp vụ yêu cầu **tối đa một bản ghi** mà SQL không được bảo đảm bằng khóa duy nhất, có thể kiểm tra dòng thứ hai để phát hiện kết quả bất thường:

~~~java
try (ResultSet resultSet = statement.executeQuery()) {
    if (!resultSet.next()) {
        return java.util.Optional.empty();
    }

    String email = resultSet.getString("email");

    if (resultSet.next()) {
        throw new SQLException("Có nhiều bản ghi, nhưng chỉ mong đợi một.");
    }

    return java.util.Optional.ofNullable(email);
}
~~~

Mẫu này phù hợp khi cần kiểm tra tính duy nhất và **email** có ràng buộc NOT NULL, hoặc chấp nhận việc giá trị null trở thành Optional.empty(). Nếu muốn phân biệt đầy đủ một dòng có cột null với không có dòng, hãy trả một đối tượng bao gồm trường định danh.

**ORDER BY** cần thiết nếu ứng dụng quan tâm đến thứ tự bản ghi. Không có ORDER BY, thứ tự dòng SQL trả về thường không được bảo đảm; việc “lấy dòng đầu tiên” không thể coi là lấy dòng mới nhất hoặc nhỏ nhất.

## 9. Vòng đời tài nguyên trong khi duyệt ResultSet

ResultSet thường phụ thuộc vào **Statement** đã tạo ra nó và **Connection** tương ứng. Khi đóng Statement, ResultSet hiện hành liên quan tới Statement cũng bị đóng. Vì thế, không được trả ResultSet ra khỏi phương thức sau khi đã đóng Statement:

~~~java
// SAI: statement bị đóng trước khi bên gọi đọc ResultSet.
public ResultSet findAll(Connection connection) throws SQLException {
    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT id, name FROM products")) {
        return statement.executeQuery();
    }
}
~~~

Thay vào đó, **đọc và ánh xạ dữ liệu trong phạm vi ResultSet còn mở**:

~~~java
public java.util.List<String> findNames(Connection connection)
        throws SQLException {
    java.util.List<String> names = new java.util.ArrayList<>();

    try (PreparedStatement statement = connection.prepareStatement(
            "SELECT name FROM products ORDER BY name");
         ResultSet resultSet = statement.executeQuery()) {

        while (resultSet.next()) {
            names.add(resultSet.getString("name"));
        }
    }
    return names;
}
~~~

Trong **try-with-resources**, các tài nguyên được đóng theo thứ tự ngược với khai báo: ResultSet rồi PreparedStatement. Nếu Connection do phương thức tự lấy qua **DataSource.getConnection()**, cần đóng Connection sau khi đã dùng xong Statement và ResultSet; nếu Connection do tầng gọi truyền vào, phương thức chỉ mượn Connection và không tự đóng nó.

Khi xử lý tập dữ liệu rất lớn, việc giữ ResultSet mở lâu có thể làm tăng thời gian chiếm dụng kết nối/cursor hoặc các tài nguyên DB. Có thể cân nhắc **phân trang**, **fetch size** (gợi ý driver, không phải cam kết xử lý thành các đợt đúng số dòng) và đóng tài nguyên ngay khi xong.

## 10. Những lỗi thường gặp khi gọi next()

| Lỗi | Vì sao xảy ra | Cách sửa |
| --- | --- | --- |
| Đọc getString() ngay sau executeQuery() | Con trỏ đang ở trước dòng đầu tiên. | Gọi next() và chỉ đọc khi true. |
| Dùng if (rs.next()) rồi while (rs.next()) | Dòng đầu tiên đã bị bỏ qua. | Dùng **while** trực tiếp, hoặc **if + do-while**. |
| Mong next() trả về số dòng | next() trả **boolean**, không phải số lượng. | Dùng COUNT(*) nếu cần đếm tại DB, hoặc đếm trong quá trình duyệt. |
| Xem false từ next() là lỗi SQL | False chỉ báo hết dòng hoặc tập rỗng. | Xử lý false như trường hợp bình thường, SQLException như lỗi. |
| Gọi getter sau khi next() là false | Không có dòng hiện tại hợp lệ. | Chỉ đọc khi next() là true. |
| Trả null thay List rỗng mà không có hợp đồng | Buộc bên gọi kiểm tra null và dễ xảy ra NullPointerException. | Với API trả danh sách, ưu tiên List rỗng. |
| Nhầm SQL NULL với không có bản ghi | next() true vẫn có thể có cột NULL. | Kiểm tra giá trị getter và wasNull() khi phù hợp. |
| Đóng ResultSet hoặc Statement trước khi duyệt xong | Con trỏ/tài nguyên không còn hợp lệ. | Duyệt trong khối try-with-resources. |
| Dùng lại cùng ResultSet sau khi đã duyệt đến cuối | TYPE_FORWARD_ONLY thường không quay lại đầu. | Thực thi lại truy vấn hoặc sử dụng cursor cuộn nếu driver/DB hỗ trợ và thực sự cần. |
| Dựa vào “dòng đầu” mà không ORDER BY | DB không bảo đảm thứ tự kết quả. | Chỉ định ORDER BY theo yêu cầu nghiệp vụ. |

## 11. Kiểm tra bằng các trường hợp 0, 1 và nhiều dòng

Khi thiết kế một phương thức đọc dữ liệu qua ResultSet, nên xem xét ba ca sau:

| Số dòng truy vấn trả về | while (rs.next()) | if (rs.next()) | Kỳ vọng |
| --- | --- | --- | --- |
| **0** | Chạy **0** lượt | **false** | Trả rỗng hoặc không tìm thấy, không đọc getter. |
| **1** | Chạy **1** lượt | **true** một lần | Đọc đúng dòng duy nhất. |
| **3** | Chạy **3** lượt | **true** lần đầu | while đọc đủ 3; if đơn lẻ chỉ xử lý dòng đầu. |

Một kiểm tra bổ sung rất có ích là **dòng có cột NULL**: ResultSet có thể có dòng nhưng getter trả về null, hoặc getter kiểu nguyên thủy cần kiểm tra wasNull().

Khi duyệt bản ghi, tránh gọi next() một cách “thăm dò” từ nhiều helper khác nhau. Mỗi lần next() làm thay đổi vị trí con trỏ; nếu một helper lén di chuyển con trỏ, helper tiếp theo có thể bỏ qua dữ liệu. Nên để **một vòng lặp hoặc một hàm điều phối** chịu trách nhiệm di chuyển con trỏ, còn các hàm ánh xạ dòng chỉ gọi getter trên dòng hiện tại.

## 12. Câu hỏi tự kiểm tra

1. Ngay sau executeQuery(), con trỏ ResultSet nằm ở đâu và vì sao chưa được gọi getString()?
2. Nếu truy vấn trả về **0 dòng**, lần gọi next() đầu tiên trả về giá trị gì? Có ném lỗi không?
3. Vì sao **if (rs.next())** rồi **while (rs.next())** có thể bỏ qua dòng đầu tiên?
4. Nếu muốn tìm một khách hàng theo ID, nên dùng **if (rs.next())** hay **while (rs.next())**? Khi nào cần kiểm tra có dòng thứ hai?
5. Kết quả **SELECT COUNT(*)** cho 0 bản ghi có phải ResultSet rỗng không?
6. Một cột số trả về **0** từ getInt() có chắc giá trị trong DB là 0 không?
7. Tại sao không được trả ResultSet ra ngoài khối try-with-resources đóng Statement?
8. Với kết quả 10.000 dòng, việc trả List 10.000 phần tử có luôn là lựa chọn phù hợp không?

**Ghi nhớ:** Trong JDBC, **next()** là thao tác vừa **di chuyển con trỏ** vừa **xác nhận có dòng để đọc**. Dùng **while (resultSet.next())** khi muốn xử lý mọi bản ghi, dùng **if (resultSet.next())** khi cần kiểm tra sự tồn tại hoặc đọc một dòng. **False** ở lần next() đầu tiên là tập kết quả rỗng, khác với **SQLException** và khác với một dòng có cột SQL NULL. Luôn đọc dữ liệu khi ResultSet còn mở, xử lý rõ trường hợp 0 dòng và tránh gọi next() thừa làm bỏ sót bản ghi.

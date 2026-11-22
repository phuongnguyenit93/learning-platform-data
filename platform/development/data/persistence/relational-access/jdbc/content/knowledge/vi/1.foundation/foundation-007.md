# Mối liên hệ giữa bảng, hàng, cột và đối tượng Java trong JDBC

## 1. Từ dữ liệu quan hệ đến đối tượng Java

**JDBC (Java Database Connectivity)** là API chuẩn để ứng dụng Java truy cập cơ sở dữ liệu quan hệ: gửi SQL, truyền tham số, đọc kết quả, cập nhật dữ liệu và quản lý giao dịch. Khi làm việc với JDBC, chúng ta gặp hai cách tổ chức thông tin:

- **Cơ sở dữ liệu quan hệ** lưu dữ liệu trong **bảng (table)**. Mỗi bảng có **cột (column)** mô tả thuộc tính dữ liệu và **hàng (row)** chứa giá trị của một bản ghi.
- **Chương trình Java** biểu diễn dữ liệu bằng **đối tượng (object)**, các **trường (field)** hoặc thành phần của `record`, cùng các kiểu như `long`, `String`, `BigDecimal`, `LocalDate`.

Hai cách tổ chức này có thể tương ứng với nhau, nhưng không tự động trở thành một. SQL trả về **tập hàng và cột**, còn Java cần **đọc và ánh xạ (mapping)** các giá trị đó thành kiểu phù hợp. JDBC cung cấp các API như `Connection`, `PreparedStatement` và `ResultSet` để thực hiện việc này; nó không tự động biến mọi hàng thành một đối tượng nghiệp vụ.

Mục tiêu của bài:

1. Nhận diện bảng, hàng, cột, khóa chính và khóa ngoại ở góc nhìn Java.
2. Giải thích cách ánh xạ một bản ghi sang đối tượng Java và một tập bản ghi sang collection.
3. Dùng JDBC để đọc giá trị cột và tạo đối tượng, cũng như ghi các giá trị của đối tượng về bảng.
4. Nhận biết giới hạn của phép ánh xạ một bảng ↔ một lớp, nhất là khi có quan hệ nhiều bảng, giá trị `NULL` hoặc kiểu dữ liệu khác nhau.

## 2. Bảng, hàng và cột: ví dụ `customers`

Giả sử ứng dụng quản lý khách hàng có bảng SQL:

~~~sql
CREATE TABLE customers (
    id            BIGINT PRIMARY KEY,
    full_name     VARCHAR(150) NOT NULL,
    credit_limit  DECIMAL(15, 2),
    registered_on DATE,
    active        BOOLEAN NOT NULL
);
~~~

Đây là cú pháp SQL minh họa; kiểu dữ liệu, cách khai báo khóa tự tăng và một số ràng buộc có thể khác giữa các hệ quản trị cơ sở dữ liệu.

Ví dụ các hàng trong bảng:

| id | full_name | credit_limit | registered_on | active |
|---:|---|---:|---|---|
| 101 | Nguyễn An | 1500000.00 | 2026-01-12 | TRUE |
| 102 | Trần Bình | `NULL` | 2026-02-03 | TRUE |
| 103 | Lê Chi | 500000.00 | `NULL` | FALSE |

Các khái niệm:

- **Bảng** `customers` biểu diễn tập bản ghi khách hàng theo một cấu trúc chung.
- **Cột** `full_name` có tên, kiểu `VARCHAR(150)` và ràng buộc `NOT NULL`; `credit_limit` có kiểu số thập phân chính xác và được phép nhận `NULL`.
- **Hàng** có `id = 101` chứa một bộ giá trị tương ứng với từng cột. Một hàng không phải là một đối tượng Java; đó là một bản ghi trong quan hệ.
- **Khóa chính (primary key)** `id` xác định duy nhất hàng trong bảng và không nhận `NULL`.
- **Ràng buộc** `NOT NULL`, `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `CHECK` (nếu có) do database thực thi. Java có thể kiểm tra đầu vào nhưng không thay thế được các ràng buộc này.

Trong hệ quản trị quan hệ, hàng **không có thứ tự ổn định được bảo đảm** nếu truy vấn không dùng `ORDER BY`. Giá trị `id = 101` thể hiện định danh bản ghi, còn "hàng thứ nhất" chỉ là vị trí hiện thời trong kết quả truy vấn.

## 3. Cách ánh xạ dữ liệu SQL sang mô hình Java

Một kiểu Java mang dữ liệu khách hàng có thể được khai báo bằng `record` (Java 16+):

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

public record Customer(
        long id,
        String fullName,
        BigDecimal creditLimit,
        LocalDate registeredOn,
        boolean active
) {}
~~~

Sơ đồ khái niệm:

~~~mermaid
flowchart LR
    subgraph SQL["Cơ sở dữ liệu quan hệ"]
      A["Bảng customers"]
      B["Hàng id = 101"]
      C["Các cột: id, full_name,<br/>credit_limit, registered_on, active"]
      A --> B
      B --> C
    end
    C -->|"ResultSet + mapping"| D
    subgraph JAVA["Bộ nhớ Java"]
      D["Customer(id, fullName,<br/>creditLimit, registeredOn, active)"]
    end
~~~

| Cơ sở dữ liệu | Java tương ứng | Điểm cần chú ý |
|---|---|---|
| Bảng `customers` | Loại đối tượng `Customer` | Một bảng có thể được biểu diễn bởi nhiều loại DTO/view khác nhau |
| Hàng có `id = 101` | Một giá trị `Customer` chứa dữ liệu của hàng | Chỉ hình thành sau khi ứng dụng ánh xạ |
| Cột `full_name` | `fullName: String` | Tên SQL và tên Java không cần giống hệt nhau |
| Cột `credit_limit` | `creditLimit: BigDecimal` | Số thập phân chính xác; cột cho phép `NULL` |
| Cột `registered_on` | `registeredOn: LocalDate` | Chỉ có ngày; phải chuyển đổi kiểu JDBC khi cần |
| Cột `active` | `active: boolean` | Chọn primitive vì cột SQL được khai báo `NOT NULL` |
| Khóa chính `id` | `id: long` | Giúp nhận diện bản ghi khi truy vấn/cập nhật, nhưng Java `record` không tự kết nối với database |

Mối liên hệ này thường được gọi là **ánh xạ quan hệ–đối tượng (object–relational mapping)** theo nghĩa khái niệm. Với **JDBC thuần**, mã Java chủ động ánh xạ; những framework ORM như JPA/Hibernate mới cung cấp cơ chế mapping và quản lý đối tượng ở tầng cao hơn, với quy tắc riêng.

**Phân biệt định danh:** hai đối tượng Java khác nhau có thể cùng chứa `id = 101`, nhưng vẫn là hai đối tượng riêng trong bộ nhớ. Khóa chính định danh *bản ghi database*; toán tử `==` trên hai đối tượng tham chiếu so sánh *định danh đối tượng Java*. `record` cung cấp so sánh giá trị bằng `equals()`, nhưng điều đó vẫn không tạo liên kết tự động với hàng SQL.

## 4. Một bảng có nhiều hàng ↔ một tập đối tượng Java

Nếu truy vấn trả về ba hàng, ứng dụng có thể tạo ba đối tượng `Customer` và đặt vào `List<Customer>`. Luồng dữ liệu là:

~~~text
SELECT ... FROM customers
             │
             ▼
ResultSet: hàng 1 -> hàng 2 -> hàng 3
             │          │          │
             ▼          ▼          ▼
         Customer    Customer    Customer
             └──────────┼──────────┘
                        ▼
                  List<Customer>
~~~

Điều quan trọng là `ResultSet` giữ một **con trỏ (cursor)**. Ban đầu con trỏ ở trước hàng đầu; mỗi lần gọi `resultSet.next()` nó chuyển sang hàng tiếp theo. Giá trị của hàng hiện tại được lấy bằng `getLong(...)`, `getString(...)`, `getBigDecimal(...)` và các getter tương ứng.

Ứng dụng phải **tạo đối tượng cho từng lần `next()` trả `true`**. Không có bảo đảm `ResultSet` sẽ tự sinh `Customer`, và `ResultSet` không phải `List<Customer>`.

## 5. Ví dụ JDBC: truy vấn và tạo đối tượng `Customer`

Đây là ví dụ đầy đủ một repository dùng `javax.sql.DataSource` để lấy `java.sql.Connection` và `java.sql.ResultSet` để đọc dữ liệu. Giả định bảng `customers` đã tồn tại như ở phần 2, và ứng dụng có JDBC driver cùng `DataSource` đã cấu hình.

~~~java
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<Customer> findByActive(boolean active) throws SQLException {
        String sql = """
                SELECT id, full_name, credit_limit, registered_on, active
                FROM customers
                WHERE active = ?
                ORDER BY id
                """;
        List<Customer> customers = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setBoolean(1, active);

            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    long id = resultSet.getLong("id");
                    String name = resultSet.getString("full_name");

                    // Getter đối tượng trả null nếu cột SQL là NULL.
                    java.math.BigDecimal limit =
                            resultSet.getBigDecimal("credit_limit");
                    Date sqlDate = resultSet.getDate("registered_on");
                    java.time.LocalDate registeredOn =
                            sqlDate == null ? null : sqlDate.toLocalDate();

                    boolean isActive = resultSet.getBoolean("active");
                    customers.add(new Customer(
                            id, name, limit, registeredOn, isActive));
                }
            }
        }
        return customers;
    }
}
~~~

Ví dụ sử dụng Java 17+ (text block và `record`). Các API JDBC cũng có thể được dùng với phiên bản Java cũ hơn bằng cách thay `record` bằng một class và thay text block bằng chuỗi SQL thông thường.

### Đọc ví dụ theo thứ tự

1. **`DataSource.getConnection()`** lấy kết nối đến cơ sở dữ liệu.
2. **`prepareStatement(sql)`** tạo câu SQL có placeholder `?`. `setBoolean(1, active)` truyền giá trị vào tham số đầu tiên (JDBC đánh số tham số từ **1**).
3. **`executeQuery()`** chạy truy vấn, trả `ResultSet`.
4. **`next()`** đọc từng hàng, getter đọc giá trị từng cột; `new Customer(...)` tạo một bản ghi Java cho hàng đó.
5. **`customers.add(...)`** gom các đối tượng vào collection độc lập.
6. **`try-with-resources`** đóng `ResultSet`, `PreparedStatement` và `Connection` kể cả khi xảy ra `SQLException`. `List<Customer>` vẫn dùng được khi các tài nguyên JDBC đã đóng.

**Tại sao dùng `PreparedStatement`?** Giá trị tham số được bind tách khỏi cấu trúc SQL, tránh ghép trực tiếp dữ liệu người dùng vào chuỗi câu lệnh. Dấu `?` chỉ dùng cho **giá trị**, không thay thế tên bảng hoặc tên cột.

**Tại sao có `ORDER BY id`?** Chúng ta yêu cầu thứ tự kết quả một cách tường minh. Không có `ORDER BY`, database không cam kết hàng sẽ được trả theo thứ tự khóa chính hay thứ tự lưu trữ.

### Ánh xạ có thể tách khỏi vòng lặp

Với nhiều truy vấn cùng trả về cấu trúc `Customer`, có thể tách thao tác chuyển một hàng thành đối tượng:

~~~java
private static Customer mapCustomer(ResultSet rs) throws SQLException {
    Date date = rs.getDate("registered_on");
    return new Customer(
            rs.getLong("id"),
            rs.getString("full_name"),
            rs.getBigDecimal("credit_limit"),
            date == null ? null : date.toLocalDate(),
            rs.getBoolean("active")
    );
}
~~~

Hàm này được gọi **sau khi `rs.next()` đã chuyển con trỏ đến một hàng hợp lệ**, và **trước khi đóng `ResultSet`**. Đây là một *row mapper* đơn giản. Nó chuyển một hàng thành một đối tượng, nhưng không tự thực hiện query hay mở kết nối.

## 6. Phân biệt SQL `NULL` và giá trị Java

`NULL` của SQL mang nghĩa **không có giá trị được xác định**; nó không tương đương với số 0, chuỗi rỗng hoặc `false`.

Trong Java, một số kiểu tham chiếu có thể nhận `null`, nhưng kiểu nguyên thủy (`int`, `long`, `boolean`...) thì không:

| Giá trị SQL | Getter JDBC | Điều nhận được trong Java |
|---|---|---|
| `full_name = 'Nguyễn An'` | `getString("full_name")` | `String` chứa nội dung |
| `credit_limit = NULL` | `getBigDecimal("credit_limit")` | `null` |
| `registered_on = NULL` | `getDate("registered_on")` | `null` |
| `id = 101` | `getLong("id")` | `long = 101` |
| `active = TRUE` | `getBoolean("active")` | `boolean = true` |

Nếu gọi `getLong()`, `getInt()` hoặc `getBoolean()` trên cột chứa SQL `NULL`, getter trả về giá trị primitive mặc định (`0` hoặc `false`). Khi cần phân biệt với giá trị thật, phải gọi **`wasNull()` ngay sau getter**:

~~~java
long managerId = resultSet.getLong("manager_id");
Long nullableManagerId = resultSet.wasNull() ? null : managerId;
~~~

Đây là ví dụ với cột giả định `manager_id` cho phép `NULL`. Với trường không được phép `NULL` như `customers.id`, có thể sử dụng `long` trực tiếp. Với trường có thể thiếu dữ liệu, kiểu tham chiếu (`Long`, `BigDecimal`, `LocalDate`) thường biểu diễn chính xác hơn.

**Cẩn trọng:** `Optional<T>` có thể thích hợp ở API trả kết quả tìm kiếm, chẳng hạn `Optional<Customer>`. Với mô hình dữ liệu/JDBC, `Optional` không tự làm công việc mapping `NULL` và không bắt buộc dùng làm thuộc tính của đối tượng.

## 7. Các kiểu dữ liệu SQL không trùng hoàn toàn với kiểu Java

Một số cặp ánh xạ thường gặp:

| Loại SQL | Kiểu Java thông dụng | Lưu ý |
|---|---|---|
| `SMALLINT`, `INTEGER` | `short`/`Short`, `int`/`Integer` | Chọn theo miền giá trị và khả năng `NULL` |
| `BIGINT` | `long`/`Long` | Không thể biểu diễn `NULL` bằng `long` |
| `VARCHAR`, `CHAR` | `String` | Giới hạn độ dài do database kiểm tra |
| `DECIMAL`, `NUMERIC` | `BigDecimal` | Phù hợp số thập phân chính xác, ví dụ tiền |
| `REAL`, `FLOAT`, `DOUBLE` | `float`, `double` hoặc wrapper | Có tính xấp xỉ nhị phân; không lý tưởng cho tiền |
| `BOOLEAN`, `BIT` | `boolean`/`Boolean` | Hỗ trợ và cách biểu diễn phụ thuộc database/driver |
| `DATE` | `LocalDate` hoặc `java.sql.Date` | `LocalDate` thường thuận tiện ở mô hình nghiệp vụ |
| `TIME` | `LocalTime` hoặc `java.sql.Time` | Dữ liệu chỉ giờ/phút/giây |
| `TIMESTAMP` | `LocalDateTime` hoặc kiểu thời gian khác phù hợp | Phải phân biệt timestamp có/không có thông tin múi giờ |
| `BINARY`, `VARBINARY` | `byte[]` | Dữ liệu lớn có thể cần đọc theo luồng |
| `BLOB`, `CLOB` | `Blob`, `Clob` hoặc dữ liệu đã đọc ra | Cần quản lý tài nguyên, kích thước và vòng đời |

Các kiểu dữ liệu SQL và khả năng chuyển đổi phụ thuộc driver cùng hệ quản trị cơ sở dữ liệu. `ResultSet.getObject(column, SomeType.class)` có thể trực tiếp lấy một số kiểu Java hiện đại nếu driver hỗ trợ; với `DATE`, ví dụ ở trên dùng `getDate(...).toLocalDate()` để thể hiện rõ quy trình chuyển đổi.

**Tiền và số thập phân:** dùng `BigDecimal` thay cho `double` khi cần giữ độ chính xác thập phân và quy tắc làm tròn rõ ràng. `DECIMAL(15, 2)` có giới hạn về precision/scale tại database; `BigDecimal` phía Java không tự áp dụng giới hạn đó.

**Ngày giờ:** `DATE` chỉ lưu ngày, nhưng `TIMESTAMP` có ngữ nghĩa khác nhau tùy database. Không tự giả định một cột `TIMESTAMP` luôn tương đương thời điểm UTC; phải thống nhất quy ước múi giờ và kiểu Java theo dữ liệu thực tế.

## 8. Ánh xạ tên cột, chỉ số cột và alias

`ResultSet` có thể đọc cột theo **chỉ số bắt đầu từ 1** hoặc theo **nhãn cột (column label)**:

~~~java
long idByIndex = resultSet.getLong(1);
long idByLabel = resultSet.getLong("id");
~~~

Với câu SQL `SELECT id, full_name FROM customers`, cả hai cách đều có thể tham chiếu cột `id` đầu tiên. Tuy nhiên, thứ tự `SELECT` có thể đổi làm chỉ số bị lệch. Đọc theo nhãn rõ nghĩa hơn khi câu truy vấn thay đổi.

Alias giúp đặt nhãn dễ hiểu và phân biệt cột cùng tên khi join:

~~~sql
SELECT c.id AS customer_id,
       c.full_name AS customer_name
FROM customers AS c
WHERE c.id = ?
~~~

~~~java
long customerId = resultSet.getLong("customer_id");
String customerName = resultSet.getString("customer_name");
~~~

Tên thuộc tính Java như `fullName` không bắt buộc giống tên cột `full_name`. **Chính mã mapping quyết định quan hệ giữa hai tên**. Đừng giả định JDBC thuần tự đổi `snake_case` thành `camelCase`.

Khi không biết trước cấu trúc kết quả, `ResultSetMetaData` cung cấp thông tin:

~~~java
var metadata = resultSet.getMetaData();
for (int column = 1; column <= metadata.getColumnCount(); column++) {
    System.out.printf("%s : %s%n",
            metadata.getColumnLabel(column),
            metadata.getColumnTypeName(column));
}
~~~

Metadata hữu ích cho công cụ đọc bảng tổng quát; trong repository nghiệp vụ, xác định rõ cột cần chọn và kiểu cần ánh xạ sẽ dễ kiểm soát hơn.

## 9. Chiều ngược lại: ghi đối tượng Java thành một hàng SQL

Ánh xạ không chỉ xảy ra khi đọc. Khi tạo một hàng mới, ứng dụng lấy giá trị từ `Customer` rồi bind vào câu `INSERT`:

~~~java
import java.sql.Connection;
import java.sql.Date;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

public final class CustomerWriter {
    public static int insert(DataSource source, Customer customer)
            throws SQLException {
        String sql = """
                INSERT INTO customers
                    (id, full_name, credit_limit, registered_on, active)
                VALUES (?, ?, ?, ?, ?)
                """;

        try (Connection connection = source.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, customer.id());
            statement.setString(2, customer.fullName());

            if (customer.creditLimit() == null) {
                statement.setNull(3, Types.DECIMAL);
            } else {
                statement.setBigDecimal(3, customer.creditLimit());
            }

            if (customer.registeredOn() == null) {
                statement.setNull(4, Types.DATE);
            } else {
                statement.setDate(4, Date.valueOf(customer.registeredOn()));
            }
            statement.setBoolean(5, customer.active());

            return statement.executeUpdate(); // Thường là 1 khi INSERT thành công.
        }
    }
}
~~~

`PreparedStatement.setXxx(...)` nhận **chỉ số tham số** bắt đầu từ 1; `setNull(index, sqlType)` diễn đạt SQL `NULL` với kiểu SQL phù hợp. Câu `INSERT` thực thi trên database, nên ràng buộc như khóa chính trùng, độ dài chuỗi, độ chính xác số và kiểm tra khóa ngoại vẫn có thể khiến thao tác thất bại với `SQLException`.

Trong hệ thống thực tế, `id` có thể được database sinh tự động; khi đó câu `INSERT` thường không truyền `id`, và ứng dụng dùng khả năng lấy generated keys theo driver. Ví dụ trên chủ động cung cấp `id` để tập trung vào ý tưởng **trường của đối tượng → tham số SQL → giá trị cột**.

Một đối tượng Java bị sửa sau khi `INSERT` **không tự làm bản ghi SQL thay đổi**. Muốn lưu thay đổi, ứng dụng phải chạy `UPDATE` phù hợp (hoặc dùng một tầng ORM quản lý trạng thái theo cơ chế riêng).

## 10. Khi có nhiều bảng: quan hệ dữ liệu và quan hệ đối tượng

Ánh xạ một hàng `customers` thành một `Customer` chỉ là trường hợp đơn giản. Giả sử ứng dụng có bảng `orders`:

~~~sql
CREATE TABLE orders (
    id          BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total       DECIMAL(15, 2) NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~

Một khách hàng có thể có nhiều đơn hàng, còn mỗi đơn hàng tham chiếu một khách hàng:

~~~mermaid
erDiagram
    customers ||--o{ orders : "có"
    customers {
        BIGINT id PK
        VARCHAR full_name
    }
    orders {
        BIGINT id PK
        BIGINT customer_id FK
        DECIMAL total
    }
~~~

Ở phía Java, ứng dụng có thể chọn:

- `Order(long id, long customerId, BigDecimal total)` chỉ chứa khóa ngoại `customerId`.
- Hoặc `Order` chứa tham chiếu đến `Customer` nếu nghiệp vụ cần và chương trình chủ động tải/khởi tạo đối tượng liên quan.
- Hoặc `CustomerWithOrders` chứa `Customer` và `List<Order>` để trả về một cấu trúc tổng hợp.

Không có quy tắc bắt buộc mọi khóa ngoại phải biến thành một tham chiếu đối tượng, và **JDBC không tự tải quan hệ**.

### Một `JOIN` không nhất thiết tương ứng với một đối tượng Java

~~~sql
SELECT c.id AS customer_id,
       c.full_name,
       o.id AS order_id,
       o.total
FROM customers AS c
LEFT JOIN orders AS o ON o.customer_id = c.id
WHERE c.id = ?
ORDER BY o.id
~~~

Nếu khách hàng 101 có hai đơn hàng, truy vấn có thể trả:

| customer_id | full_name | order_id | total |
|---:|---|---:|---:|
| 101 | Nguyễn An | 501 | 120000.00 |
| 101 | Nguyễn An | 502 | 300000.00 |

Hai **hàng kết quả** không có nghĩa là database có hai khách hàng 101. `JOIN` kết hợp thông tin và lặp lại cột của khách hàng cho mỗi đơn hàng tương ứng. Để tạo mô hình một `Customer` có hai `Order`, mã Java phải **nhóm theo `customer_id`**, tạo một đối tượng khách hàng và gắn hai đơn hàng. Với `LEFT JOIN`, khách hàng chưa có đơn hàng vẫn có thể xuất hiện; các cột phía `orders` khi đó là SQL `NULL`.

Vì thế, cần phân biệt ba cấp độ:

1. **Hàng của bảng**: bản ghi của một quan hệ cụ thể, ví dụ `customers`.
2. **Hàng kết quả truy vấn**: tập các cột do `SELECT` trả về, có thể tổng hợp từ nhiều bảng và có hàng lặp về một thực thể.
3. **Đối tượng Java**: cấu trúc dữ liệu do ứng dụng chọn để biểu diễn kết quả, có thể chứa một hàng, một phần của hàng hoặc nhiều hàng liên quan.

## 11. Một đối tượng không bắt buộc bằng một hàng đầy đủ

Các dạng mapping thường thấy:

| Trường hợp | SQL trả về | Java có thể biểu diễn |
|---|---|---|
| Lấy khách hàng theo `id` | 0 hoặc 1 hàng | `Optional<Customer>` |
| Liệt kê khách hàng hoạt động | 0..N hàng | `List<Customer>` |
| Chỉ lấy tên và mã khách hàng | 0..N hàng, ít cột | `CustomerSummary` DTO/record |
| Đếm khách hàng | Một hàng, một cột `COUNT(*)` | `long` |
| Tính tổng đơn theo khách hàng | N hàng `customer_id, SUM(total)` | `CustomerOrderTotal` |
| Join khách hàng và đơn hàng | N hàng có cột từ hai bảng | DTO phẳng hoặc mô hình lồng nhau đã nhóm |

Ví dụ một **projection** chỉ chứa hai cột:

~~~java
public record CustomerSummary(long id, String fullName) {}
~~~

~~~sql
SELECT id, full_name
FROM customers
ORDER BY id
~~~

Ứng dụng không cần đọc `credit_limit`, `registered_on` hay `active` chỉ để hiển thị danh sách tên. Chọn đúng cột bằng SQL thường giúp giảm dữ liệu truyền và tránh lộ trường không cần thiết.

Kết quả từ SQL aggregation như `COUNT` và `SUM` cũng là hàng/cột, nhưng chúng đại diện cho **kết quả tính toán**, không nhất thiết là một hàng vật lý trong bảng gốc.

## 12. Tránh các lỗi phổ biến trong mã JDBC

### 12.1. Trả `ResultSet` sau khi đã đóng kết nối

Mã này **sai về vòng đời tài nguyên**:

~~~java
// Chỉ minh họa lỗi: không dùng thiết kế này.
ResultSet findCustomers(DataSource source) throws SQLException {
    try (Connection connection = source.getConnection();
         PreparedStatement statement =
                 connection.prepareStatement("SELECT * FROM customers")) {
        return statement.executeQuery();
    } // Statement và Connection đã đóng trước khi caller dùng ResultSet.
}
~~~

Hãy đọc `ResultSet` bên trong phạm vi kết nối, tạo các đối tượng Java rồi trả về `List<Customer>` hoặc DTO phù hợp. Nếu thực sự cần xử lý dữ liệu lớn theo luồng, hãy thiết kế API callback/consumer có vòng đời tài nguyên được quản lý rõ ràng.

### 12.2. Đọc `NULL` bằng kiểu nguyên thủy rồi hiểu nhầm `0` là dữ liệu thật

Với cột có thể `NULL`, dùng getter đối tượng hoặc `wasNull()`. Đừng gán một giá trị mặc định nếu nghiệp vụ cần phân biệt "chưa xác định" với "bằng không".

### 12.3. Dùng tên cột sai, phụ thuộc `SELECT *`

`SELECT *` có thể làm ứng dụng phụ thuộc vào thay đổi schema và tăng dữ liệu không cần thiết. Ưu tiên danh sách cột tường minh, alias rõ ràng khi `JOIN` và đặt mã mapping khớp nhãn cột.

### 12.4. Coi `List<Customer>` như dữ liệu luôn đồng bộ với bảng

Các đối tượng trong collection là **bản sao của giá trị đã đọc**. Thay đổi bản ghi trên database không tự cập nhật collection; thay đổi thuộc tính đối tượng cũng không tự ghi SQL. Khi cần dữ liệu mới, phải truy vấn lại hoặc dùng cơ chế cache/ORM với chiến lược làm mới rõ ràng.

### 12.5. Ghép SQL từ dữ liệu người dùng

Tham số của câu truy vấn nên được bind bằng `PreparedStatement`. Ví dụ sai:

~~~java
String sql = "SELECT id FROM customers WHERE full_name = '" +
             userInput + "'";
~~~

Thay bằng:

~~~java
String sql = "SELECT id FROM customers WHERE full_name = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, userInput);
    // Thực thi và xử lý ResultSet trong cùng phạm vi tài nguyên.
}
~~~

Truyền tham số tách biệt khỏi cú pháp SQL giúp giảm rủi ro SQL injection và làm mã dễ kiểm soát hơn.

## 13. Tóm tắt mô hình tư duy

~~~mermaid
flowchart TD
    DB[("Database: các bảng, hàng, cột")] -->|"SQL SELECT"| RS["JDBC ResultSet: các hàng kết quả"]
    RS -->|"Getter + mapping"| OBJ["Customer / DTO / record"]
    OBJ -->|"Thu thập"| LIST["List / Map / cấu trúc nghiệp vụ"]
    OBJ -->|"Lấy trường và bind tham số"| PS["PreparedStatement"]
    PS -->|"INSERT / UPDATE / DELETE"| DB
~~~

Trong phần **Nền tảng** của JDBC, hãy ghi nhớ:

- **Bảng** xác định cấu trúc dữ liệu quan hệ; **cột** có kiểu SQL và ràng buộc; **hàng** chứa bộ giá trị.
- Một **đối tượng Java** có thể biểu diễn một hàng, một phần hàng, kết quả tổng hợp hoặc nhiều hàng liên quan — tùy thiết kế mapping.
- `ResultSet` là phương tiện đọc **hàng kết quả SQL**, không phải là đối tượng nghiệp vụ hay collection Java.
- Đọc cột phải quan tâm kiểu dữ liệu, `NULL`, alias, chỉ số cột và vòng đời kết nối.
- Khi ghi dữ liệu, các trường Java trở thành tham số SQL; database vẫn chịu trách nhiệm thực thi ràng buộc và giao dịch.
- **JDBC thuần không tự thực hiện ORM**. Mã ứng dụng chọn và kiểm soát cách ánh xạ giữa dữ liệu quan hệ và đối tượng Java.

### Câu hỏi tự kiểm tra

1. Bảng `customers` có 500 hàng. `SELECT COUNT(*)` tạo bao nhiêu hàng kết quả và nên ánh xạ thành kiểu Java nào?
2. Vì sao hai hàng `JOIN` cùng `customer_id = 101` chưa chắc tương ứng với hai khách hàng?
3. Điều gì xảy ra nếu dùng `getLong("manager_id")` khi cột `manager_id` là SQL `NULL`?
4. Vì sao đổi `customer.fullName` trong bộ nhớ không tự chạy `UPDATE customers`?
5. Vì sao trong repository nên đọc `ResultSet` xong rồi trả về `List<Customer>` thay vì trả `ResultSet` sau khi đã đóng `Connection`?

### Tài liệu tham khảo

- [Java SE 21 API — `java.sql`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/package-summary.html)
- [Java SE 21 API — `ResultSet`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html)
- [Java SE 21 API — `PreparedStatement`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html)
- [Java SE 21 API — `ResultSetMetaData`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSetMetaData.html)

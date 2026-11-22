# Tránh tạo trùng đối tượng khi kết quả JOIN nhân số hàng trong JDBC

Khi ánh xạ kết quả truy vấn SQL sang đối tượng Java, một lỗi thường gặp là tạo một đối tượng cha mới **cho mỗi dòng của `ResultSet`**, ngay cả khi nhiều dòng cùng mô tả một bản ghi cha. Lỗi này xuất hiện rõ nhất khi truy vấn `JOIN` quan hệ một-nhiều: một khách hàng có nhiều đơn hàng, một bài viết có nhiều bình luận, hoặc một hóa đơn có nhiều dòng chi tiết.

Bài học thuộc chương **Ánh xạ bản ghi** của **JDBC**. Mục tiêu là đọc `ResultSet` bằng API chuẩn, tạo **một đối tượng Java cho mỗi khóa chính của bản ghi cha**, gắn đúng các đối tượng con, và tránh nhân đôi con khi truy vấn chứa nhiều quan hệ một-nhiều. Ví dụ sử dụng `DataSource`, `PreparedStatement`, SQL tham số hóa, `ResultSet` và cấu trúc dữ liệu Java; không cần ORM.

## 1. Vì sao JOIN tạo nhiều dòng cho cùng một bản ghi?

Giả sử cơ sở dữ liệu có hai bảng:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    active BOOLEAN NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    order_code VARCHAR(40) NOT NULL
);
```

> DDL trên dùng kiểu dữ liệu và cú pháp minh họa; có thể phải điều chỉnh theo hệ quản trị. Mối quan hệ chính cần lưu ý là `orders.customer_id` tham chiếu `customers.id`.

Giả sử dữ liệu đang có:

**`customers`**

| id | full_name | active |
| ---: | --- | --- |
| 1 | An | true |
| 2 | Bình | true |

**`orders`**

| id | customer_id | order_code |
| ---: | ---: | --- |
| 101 | 1 | A-01 |
| 102 | 1 | A-02 |

Truy vấn:

```sql
SELECT
    c.id AS customer_id,
    c.full_name AS customer_name,
    o.id AS order_id,
    o.order_code AS order_code
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
ORDER BY c.id, o.id;
```

Trả về kết quả logic:

| customer_id | customer_name | order_id | order_code |
| ---: | --- | ---: | --- |
| 1 | An | 101 | A-01 |
| 1 | An | 102 | A-02 |
| 2 | Bình | `NULL` | `NULL` |

Ba dòng SQL nhưng chỉ có **hai khách hàng**. Thông tin khách hàng `1` xuất hiện hai lần vì khách hàng này có hai đơn hàng. Đó là cách biểu diễn kết quả JOIN quan hệ một-nhiều; bản ghi `customers` trong cơ sở dữ liệu không tự nhiên bị nhân bản.

Mô hình đối tượng mong muốn:

```text
Customer(id=1, name="An")
  ├── Order(id=101, code="A-01")
  └── Order(id=102, code="A-02")

Customer(id=2, name="Bình")
  └── orders = []
```

Số đối tượng `Customer` nên là **2**, trong khi số dòng `ResultSet` là **3**. Không thể dùng số dòng SQL như số thực thể cha.

## 2. Cách ánh xạ sai: tạo cha mới trong mỗi lượt `next()`

Đoạn mã sau có lỗi nếu mục tiêu là trả về một danh sách khách hàng, mỗi khách hàng chứa toàn bộ đơn hàng:

```java
List<Customer> customers = new ArrayList<>();

while (rs.next()) {
    Customer customer = new Customer(
            rs.getLong("customer_id"),
            rs.getString("customer_name"));

    long orderId = rs.getLong("order_id");
    if (!rs.wasNull()) {
        customer.addOrder(new Order(
                orderId, rs.getString("order_code")));
    }
    customers.add(customer);
}
```

Với dữ liệu phía trên, đoạn mã tạo:

```text
Customer(1) → [Order(101)]
Customer(1) → [Order(102)]  // Khách hàng 1 được tạo lần thứ hai
Customer(2) → []
```

Ngay cả khi ghi đè `equals()`/`hashCode()` cho `Customer` rồi gọi `distinct()` hoặc chuyển sang `Set`, vấn đề vẫn chưa được giải quyết: hai đối tượng `Customer(1)` giữ **hai danh sách con khác nhau**. Loại bỏ một đối tượng có thể làm mất đơn hàng. Muốn tổng hợp chính xác, phải dùng lại cùng đối tượng cha **ngay khi đang đọc từng dòng**.

## 3. Giải pháp chính: một bản đồ khóa chính → đối tượng cha

Ý tưởng là giữ một *identity map* có phạm vi **một lần ánh xạ kết quả truy vấn**:

```text
Map<customerId, Customer>

Dòng 1: customerId=1 → chưa có → tạo Customer(1), thêm Order(101)
Dòng 2: customerId=1 → đã có   → dùng lại Customer(1), thêm Order(102)
Dòng 3: customerId=2 → chưa có → tạo Customer(2), không có Order

Kết quả: [Customer(1), Customer(2)]
```

Các bước cho mỗi dòng:

1. Đọc khóa chính cha (ví dụ `customer_id`).
2. Tra `Map`. Nếu chưa có, tạo đối tượng cha và lưu ngay vào `Map`.
3. Đọc khóa con; nếu con có tồn tại, thêm vào tập hợp con của đối tượng cha đã lấy từ `Map`.
4. Sau khi duyệt hết `ResultSet`, trả các giá trị trong `Map` thành danh sách.

`LinkedHashMap` rất hữu ích vì bảo toàn **thứ tự lần đầu gặp khóa cha**; kết hợp `ORDER BY` giúp kết quả ổn định. `HashMap` cũng giúp tìm theo khóa, nhưng không bảo đảm thứ tự duyệt. Giá trị khóa chính (`long`, `UUID`, hoặc khóa ghép thích hợp) xác định danh tính; không nên dùng tên khách hàng vì có thể trùng hoặc thay đổi.

## 4. Ví dụ đầy đủ: ánh xạ một-nhiều bằng `DataSource` và `ResultSet`

Ví dụ sau dành cho Java 8 trở lên. `Customer` là đối tượng cha có danh sách `Order`. Repository mở kết nối, chạy `PreparedStatement`, và đọc từng dòng một lần mà không phát sinh thêm truy vấn SQL bên trong vòng lặp:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<Customer> findActiveCustomersWithOrders()
            throws SQLException {
        String sql =
                "SELECT c.id AS customer_id, " +
                "c.full_name AS customer_name, " +
                "o.id AS order_id, " +
                "o.order_code AS order_code " +
                "FROM customers c " +
                "LEFT JOIN orders o ON o.customer_id = c.id " +
                "WHERE c.active = ? " +
                "ORDER BY c.id, o.id";

        Map<Long, Customer> customersById = new LinkedHashMap<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setBoolean(1, true);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    long customerId = rs.getLong("customer_id");

                    Customer customer = customersById.get(customerId);
                    if (customer == null) {
                        customer = new Customer(
                                customerId, rs.getString("customer_name"));
                        customersById.put(customerId, customer);
                    }

                    long orderId = rs.getLong("order_id");
                    if (!rs.wasNull()) {
                        customer.addOrder(new Order(
                                orderId, rs.getString("order_code")));
                    }
                }
            }
        }

        return new ArrayList<>(customersById.values());
    }

    public static final class Customer {
        private final long id;
        private final String fullName;
        private final List<Order> orders = new ArrayList<>();

        public Customer(long id, String fullName) {
            this.id = id;
            this.fullName = fullName;
        }

        public long getId() {
            return id;
        }

        public String getFullName() {
            return fullName;
        }

        public List<Order> getOrders() {
            return Collections.unmodifiableList(orders);
        }

        private void addOrder(Order order) {
            orders.add(order);
        }
    }

    public static final class Order {
        private final long id;
        private final String orderCode;

        public Order(long id, String orderCode) {
            this.id = id;
            this.orderCode = orderCode;
        }

        public long getId() {
            return id;
        }

        public String getOrderCode() {
            return orderCode;
        }
    }
}
```

Nếu áp dụng cho dữ liệu ví dụ, phương thức trả về hai đối tượng `Customer`. Đối tượng `Customer(1)` có hai phần tử `Order`, còn `Customer(2)` có danh sách rỗng.

Những điểm quan trọng:

- **Tái sử dụng cha:** `customersById.get(customerId)` là bước ngăn tạo trùng; chỉ gọi `new Customer(...)` khi khóa chưa có.
- **`LEFT JOIN` và khóa con `NULL`:** nếu khách hàng không có đơn hàng, cột `order_id` là SQL `NULL`. `getLong(...)` trả `0` cho `NULL`, nên phải gọi **`rs.wasNull()` ngay sau khi đọc**. Không kiểm tra `orderId != 0` vì `0` không phải tín hiệu `NULL` chung của JDBC.
- **Tên cột rõ ràng:** alias `customer_id` và `order_id` giúp tránh nhầm khi cả hai bảng đều có cột `id`.
- **Tài nguyên:** `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` ngay cả khi có `SQLException`; với connection pool, `close()` thường trả kết nối về pool.
- **SQL tham số hóa:** `?` và `setBoolean(1, true)` minh họa quy tắc gán tham số. Với giá trị do người dùng cung cấp, không nối trực tiếp chúng vào câu SQL.
- **Thứ tự:** `ORDER BY c.id, o.id` cùng `LinkedHashMap` cho danh sách khách hàng và đơn hàng theo ID. Nếu không có `ORDER BY`, thứ tự dòng do cơ sở dữ liệu trả về không được bảo đảm.

> Trong chính truy vấn **một cha → một tập con** ở đây, mỗi đơn hàng xuất hiện một lần nếu `orders.id` là khóa duy nhất và không có phép JOIN khác nhân hàng. Vì thế chỉ cần khử trùng đối tượng cha. Khi truy vấn nối thêm tập con khác, cần khử trùng **cả các đối tượng con** như phần tiếp theo.

## 5. JOIN nhiều quan hệ một-nhiều: nhân số hàng theo tích

Giả sử mỗi khách hàng có **2 đơn hàng** và **3 địa chỉ**. Truy vấn JOIN đồng thời hai tập hợp:

```sql
SELECT
    c.id AS customer_id,
    c.full_name AS customer_name,
    o.id AS order_id,
    o.order_code AS order_code,
    a.id AS address_id,
    a.city AS address_city
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
LEFT JOIN customer_addresses a ON a.customer_id = c.id
ORDER BY c.id, o.id, a.id;
```

Với một khách hàng có đơn hàng `101`, `102` và địa chỉ `201`, `202`, `203`, kết quả tạo **2 × 3 = 6 dòng**:

| customer_id | order_id | address_id |
| ---: | ---: | ---: |
| 1 | 101 | 201 |
| 1 | 101 | 202 |
| 1 | 101 | 203 |
| 1 | 102 | 201 |
| 1 | 102 | 202 |
| 1 | 102 | 203 |

Nếu chỉ giữ một `Customer(1)` nhưng cứ thêm `Order` và `Address` trên **mỗi dòng**, đối tượng sẽ có sáu phần tử đơn hàng và sáu phần tử địa chỉ, trong khi dữ liệu thực chỉ có hai đơn hàng và ba địa chỉ. Đó là tình huống **nhân đôi cả tập hợp con**.

### Khử trùng từng tập con bằng khóa chính

Dùng một tập khóa con đã gặp **theo từng cha và theo từng quan hệ**:

```java
Map<Long, CustomerAggregate> customersById = new LinkedHashMap<>();
Map<Long, Set<Long>> seenOrderIds = new HashMap<>();
Map<Long, Set<Long>> seenAddressIds = new HashMap<>();

while (rs.next()) {
    long customerId = rs.getLong("customer_id");
    CustomerAggregate customer = customersById.get(customerId);
    if (customer == null) {
        customer = new CustomerAggregate(
                customerId, rs.getString("customer_name"));
        customersById.put(customerId, customer);
    }

    long orderId = rs.getLong("order_id");
    if (!rs.wasNull()
            && seenOrderIds.computeIfAbsent(
                    customerId, id -> new HashSet<>()).add(orderId)) {
        customer.addOrder(new Order(
                orderId, rs.getString("order_code")));
    }

    long addressId = rs.getLong("address_id");
    if (!rs.wasNull()
            && seenAddressIds.computeIfAbsent(
                    customerId, id -> new HashSet<>()).add(addressId)) {
        customer.addAddress(new Address(
                addressId, rs.getString("address_city")));
    }
}
```

Đây là **đoạn lõi của mapper**, giả sử truy vấn phía trên đang được đọc bằng `ResultSet rs`, đã import `Map`, `Set`, `HashMap`, `HashSet`, `LinkedHashMap`, và có các lớp mô hình `CustomerAggregate`, `Order`, `Address` với constructor/phương thức được gọi. Khác với ví dụ repository đầy đủ ở phần 4, đây là phần thay thế cho **vòng lặp xử lý dữ liệu** khi bổ sung quan hệ địa chỉ; `CustomerAggregate` chứa cả hai danh sách.

`Set.add(id)` trả `true` **chỉ ở lần đầu** thấy ID trong tập. Với sáu dòng:

- `Order(101)` chỉ được thêm một lần, dù xuất hiện ở ba dòng.
- `Order(102)` chỉ được thêm một lần.
- `Address(201)`, `Address(202)`, `Address(203)` mỗi đối tượng chỉ được thêm một lần dù xuất hiện hai lần.

**Không dùng cùng một `Set<Long>` cho hai bảng**: `orders.id = 101` và `addresses.id = 101` hoàn toàn có thể cùng tồn tại. Mỗi quan hệ cần không gian nhận dạng riêng. Nếu khóa chính là tổ hợp nhiều cột hoặc dữ liệu thuộc nhiều tenant, khóa dùng trong `Map`/`Set` phải bao gồm đủ thành phần định danh; không chỉ lấy một cột có nguy cơ trùng.

### Khi cần lưu chính đối tượng con theo khóa

Thay vì `Set<Long>` kiểm tra ID trước khi tạo đối tượng con, có thể dùng cấu trúc hai tầng:

```java
Map<Long, Map<Long, Order>> ordersByCustomer = new HashMap<>();

Map<Long, Order> children = ordersByCustomer.computeIfAbsent(
        customerId, id -> new LinkedHashMap<>());

if (!children.containsKey(orderId)) {
    children.put(orderId, new Order(orderId, orderCode));
}
```

Đoạn này minh họa với `customerId`, `orderId`, `orderCode` đã được đọc và **`orderId` đã được xác nhận không phải SQL `NULL`**. Cấu trúc `Map<customerId, Map<orderId, Order>>` còn cho phép tìm lại đối tượng `Order` để gắn thêm thuộc tính hoặc tập con của chính đơn hàng khi cần. Dù dùng cách nào, **khóa định danh và phạm vi của bộ nhớ ánh xạ phải rõ ràng**.

## 6. Vì sao `DISTINCT` hoặc `GROUP BY` không tự giải quyết ánh xạ?

Một phản xạ thường gặp là thêm `DISTINCT`:

```sql
SELECT DISTINCT c.id, c.full_name, o.id, o.order_code
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id;
```

Nếu hai dòng khác nhau ở `o.id`, cả hai vẫn được giữ lại. `DISTINCT` loại bỏ **những dòng có toàn bộ giá trị cột được chọn giống nhau**, chứ không phải gom tất cả dòng về một đối tượng `Customer`. Nếu chỉ chọn `DISTINCT c.id, c.full_name`, kết quả không chứa dữ liệu đơn hàng để dựng danh sách con.

`GROUP BY` cũng thay đổi ý nghĩa truy vấn: có thể dùng để lấy số đơn hàng hoặc một giá trị tổng hợp cho mỗi khách hàng, nhưng không tự biến các dòng con thành danh sách đối tượng Java. Một số hệ quản trị hỗ trợ gom JSON hoặc array trong SQL, song đó là thiết kế khác, có cách đọc/ánh xạ và sự phụ thuộc driver riêng.

**Quy tắc:** xử lý trùng lặp ở tầng SQL nếu chúng thực sự là dòng dư thừa cần loại bỏ; xử lý **danh tính đối tượng** ở mapper khi nhiều dòng hợp lệ cùng biểu diễn một thực thể cha hoặc con.

## 7. Những tình huống cần xử lý đặc biệt

### 7.1. Không có hàng con và `LEFT JOIN`

Một hàng cha không có bản ghi con vẫn xuất hiện dưới dạng một dòng với cột phía con là `NULL`. Đừng tạo `Order(0, null)`; giữ danh sách con rỗng. Với `INNER JOIN`, những hàng cha không có hàng con **bị loại khỏi kết quả**. Chọn kiểu JOIN theo yêu cầu nghiệp vụ.

Chú ý vị trí đặt điều kiện cho bảng con:

```sql
-- Giữ khách hàng dù không có đơn hàng ở trạng thái PAID.
LEFT JOIN orders o
    ON o.customer_id = c.id AND o.status = 'PAID'

-- Nếu đặt o.status = 'PAID' tại WHERE, các hàng có o.* NULL
-- sẽ bị loại, khiến LEFT JOIN mất tác dụng giữ cha không có con.
```

Đây là khác biệt ngữ nghĩa của câu SQL, không phải lỗi của mapper.

### 7.2. Chỉ tiêu thụ đúng những cột được lấy

Mỗi cột nên có alias duy nhất khi nhiều bảng cùng có tên `id`, `name` hoặc `created_at`. Đọc `rs.getLong("id")` khi truy vấn chọn hai cột `id` mơ hồ và dễ lấy nhầm. Với kiểu khóa `UUID` hoặc khóa dạng chuỗi, dùng `getObject(...)`/`getString(...)` phù hợp; không ép tất cả khóa thành `long`.

Khi dữ liệu cha xuất hiện trong nhiều dòng, có thể chỉ đọc tên cha lúc tạo đối tượng lần đầu. Nếu một ID cha lại đi kèm tên không nhất quán, cần kiểm tra nguyên nhân từ SQL, dữ liệu, phép JOIN hoặc tính nhất quán của giao dịch, thay vì tạo thêm cha để né lỗi.

### 7.3. `NULL` không đồng nghĩa ID bằng 0

Phương thức `ResultSet.getLong()` trả `0` khi giá trị SQL là `NULL`. `wasNull()` cho biết **cột vừa đọc** có phải `NULL` hay không. Không đọc cột khác giữa `getLong("order_id")` và `wasNull()`, vì khi đó kết quả kiểm tra có thể thuộc về cột khác.

### 7.4. Một-nhiều và nhiều-nhiều

Với quan hệ nhiều-nhiều như `students ↔ courses`, một dòng JOIN có thể tương ứng với một **cạnh liên kết** giữa hai thực thể. Có thể cần một `Map` cho sinh viên, một `Map` cho môn học, và một `Set` theo sinh viên để tránh thêm cùng môn học vào danh sách nhiều lần. Tránh dùng khóa là tên hoặc nhãn hiển thị: hai môn khác nhau có thể cùng tên.

### 7.5. Không lưu `Map` ánh xạ toàn cục

Identity map dành cho việc tổng hợp **một tập kết quả**. Đặt nó ở biến cục bộ trong phương thức repository giúp tránh lẫn dữ liệu giữa hai yêu cầu, các tenant, hoặc các phiên giao dịch. Nếu cần cache ở cấp ứng dụng, phải thiết kế riêng việc làm mới dữ liệu, đồng bộ và phạm vi quyền truy cập. `HashMap` cục bộ cũng không đặt ra vấn đề truy cập đồng thời khi mỗi lời gọi dùng map riêng.

## 8. Tác động đến phân trang, hiệu năng và transaction

### `LIMIT`/`OFFSET` trên JOIN đang giới hạn số dòng

Giả sử cần trang gồm **10 khách hàng** kèm danh sách đơn hàng. Nếu viết:

```sql
SELECT c.id, c.full_name, o.id, o.order_code
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
ORDER BY c.id, o.id
LIMIT 10 OFFSET 0;
```

`LIMIT 10` giới hạn **10 dòng JOIN**, không phải 10 khách hàng. Nếu khách hàng đầu tiên có 12 đơn hàng, trang này chỉ chứa **một phần** các đơn hàng của khách hàng đó; mapper không thể tự khôi phục hàng đã bị SQL loại bỏ. `LIMIT`/`OFFSET` ở ví dụ là cú pháp của các hệ quản trị hỗ trợ chúng; hệ khác có cú pháp phân trang riêng.

Một chiến lược an toàn hơn:

1. Truy vấn danh sách **ID khách hàng** thuộc trang, theo thứ tự ổn định; áp dụng phân trang ở cấp cha.
2. Truy vấn khách hàng và đơn hàng của **chỉ các ID đó**, chẳng hạn bằng `WHERE c.id IN (?, ?, ...)` với số placeholder phù hợp, hoặc cơ chế bảng tạm/quan hệ dẫn xuất mà hệ quản trị hỗ trợ.
3. Ánh xạ các dòng JOIN bằng `Map` và phục hồi thứ tự trang ban đầu theo danh sách ID nếu cần.

Khi danh sách ID rỗng, trả trang rỗng mà không tạo câu `IN ()` không hợp lệ. Với danh sách ID rất lớn, cân nhắc giới hạn số tham số, kế hoạch truy vấn và đặc điểm hệ quản trị. Hai lượt truy vấn có thể nhìn thấy các trạng thái dữ liệu khác nhau nếu ghi đồng thời diễn ra; nếu nghiệp vụ cần một ảnh chụp nhất quán, cấu hình transaction và mức cô lập phù hợp cho cả hai truy vấn.

### JOIN nhiều tập hợp có thể gây bùng nổ hàng

Nếu một cha có `m` đơn hàng và `n` địa chỉ, JOIN hai tập con thường tạo `m × n` dòng cho cha đó khi cả hai tập không rỗng. JOIN thêm một tập con khác có thể nhân kích thước lên nữa, kéo theo:

- Nhiều dòng truyền qua mạng hơn.
- Nhiều lượt lặp `ResultSet` và nhiều giá trị lặp lại của cha.
- Tăng bộ nhớ cho `Map`, tập ID đã thấy và các đối tượng tổng hợp.

Với dữ liệu lớn, có thể hiệu quả hơn khi chạy **một truy vấn lấy danh sách cha, một truy vấn lấy toàn bộ con cho các cha đã chọn**, rồi ghép bằng khóa. Cách này khác với lỗi **N+1 query**: không truy vấn con riêng cho từng cha. Quyết định nên dựa trên kích thước thực tế, chỉ mục, kế hoạch SQL và đo đạc.

### Thời điểm dựng đối tượng và vòng đời kết nối

Mapper trên thu thập đủ dữ liệu trước khi đóng `ResultSet`/`Connection`, rồi trả ra danh sách đối tượng Java độc lập. Không giữ `ResultSet` bên trong đối tượng miền để dùng sau khi kết nối đóng. Nếu đang trong một transaction có nhiều truy vấn, cần dùng **cùng `Connection`** do tầng giao dịch quản lý; mã repository không nên mở kết nối riêng cho từng truy vấn trong transaction đó.

## 9. Kiểm thử ánh xạ: kiểm số thực thể, không chỉ số dòng

Với dữ liệu ví dụ, các điều kiện kiểm tra cơ bản:

| Trường hợp | Số dòng JOIN | Kết quả ánh xạ cần có |
| --- | ---: | --- |
| Khách hàng có 2 đơn hàng | 2 | 1 khách hàng, 2 đơn hàng khác nhau |
| Khách hàng không có đơn hàng (`LEFT JOIN`) | 1 | 1 khách hàng, danh sách đơn hàng rỗng |
| 1 khách hàng có 2 đơn hàng và 3 địa chỉ | 6 | 1 khách hàng, 2 đơn hàng, 3 địa chỉ |
| 2 khách hàng khác nhau cùng tên | Tùy số con | 2 đối tượng cha riêng vì ID khác nhau |
| Hai bảng con có cùng trị số ID | Tùy số con | Không nhầm danh tính giữa hai quan hệ |

Ví dụ kiểm thử hành vi sau khi đã dựng repository và dữ liệu thử:

```java
List<CustomerRepository.Customer> result =
        repository.findActiveCustomersWithOrders();

// Với dữ liệu minh họa: An có 2 đơn, Bình không có đơn.
if (result.size() != 2) {
    throw new AssertionError("Expected 2 customers");
}
if (result.get(0).getId() != 1L
        || result.get(0).getOrders().size() != 2) {
    throw new AssertionError("Customer 1 was mapped incorrectly");
}
if (result.get(1).getId() != 2L
        || !result.get(1).getOrders().isEmpty()) {
    throw new AssertionError("Customer 2 was mapped incorrectly");
}
```

Ví dụ này giả định dữ liệu đã được nạp đúng như hai bảng minh họa và truy vấn có `ORDER BY` như ở phần 4. Trong bài kiểm thử độc lập, nên tạo dữ liệu trong transaction thử nghiệm rồi hoàn tác hoặc dùng cơ sở dữ liệu thử nghiệm chuyên biệt để không phụ thuộc dữ liệu sản phẩm.

### Bài tập thực hành

1. Tạo bảng `departments` và `employees` theo quan hệ một-nhiều. Dùng `LEFT JOIN` và `LinkedHashMap` để trả danh sách phòng ban kèm nhân viên, kể cả phòng ban không có nhân viên.
2. Thêm bảng `department_locations`, tạo dữ liệu một phòng ban có 3 nhân viên và 2 địa điểm. Đọc 6 dòng JOIN thành **một** phòng ban có đúng 3 nhân viên và 2 địa điểm bằng tập khóa riêng cho từng quan hệ.
3. Thử dùng `DISTINCT` trong SQL và so sánh kết quả. Giải thích vì sao `DISTINCT` không thay thế việc tập hợp đối tượng theo khóa chính.
4. Thử phân trang trên câu JOIN và trên danh sách ID cha trước JOIN. Kiểm tra trường hợp một cha có nhiều con vượt kích thước trang.

## 10. Tổng kết nguyên tắc

| Điều cần bảo đảm | Cách thực hiện với JDBC |
| --- | --- |
| Một đối tượng cha cho một bản ghi cha | Dùng `Map<ParentId, Parent>` cục bộ khi duyệt `ResultSet`. |
| Không thêm con giả khi `LEFT JOIN` không khớp | Kiểm tra khóa con `NULL` bằng `getXxx()` và `wasNull()` đúng thứ tự. |
| Không nhân đôi con khi JOIN nhiều quan hệ | Dùng `Set<ChildId>` hoặc `Map<ChildId, Child>` **cho từng quan hệ và từng cha**. |
| Không nhầm định danh | Dùng khóa chính hoặc khóa ghép đầy đủ, alias cột duy nhất. |
| Kết quả ổn định và không thất thoát con | Áp dụng `ORDER BY`; phân trang ở cấp cha khi cần danh sách con đầy đủ. |
| Tránh truy vấn và bộ nhớ quá mức | Đo kích thước JOIN; cân nhắc tải cha và tập con bằng một số ít truy vấn theo lô. |

**Ghi nhớ:** số dòng SQL là số tổ hợp mà JOIN tạo ra; số đối tượng trong mô hình Java phải được quyết định bằng **danh tính của thực thể**. Khi viết mapper cho `ResultSet`, hãy tạo cha theo khóa chính, tái sử dụng cha ở những dòng tiếp theo và khử trùng từng tập con theo khóa của chính nó. Đây là nền tảng để xây dựng tầng truy cập dữ liệu JDBC đúng, dễ kiểm thử và phù hợp với các nghiệp vụ CRUD phức tạp.

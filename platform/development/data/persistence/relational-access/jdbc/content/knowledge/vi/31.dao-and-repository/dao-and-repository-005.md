# Phối hợp nhiều DAO trong cùng thao tác nghiệp vụ bằng JDBC

Trong ứng dụng Java truy cập cơ sở dữ liệu quan hệ qua **JDBC**, một DAO (*Data Access Object*) thường chỉ phụ trách một nhóm thao tác SQL: đọc sản phẩm, cập nhật tồn kho, tạo đơn hàng hoặc lưu dòng chi tiết. Nhưng một thao tác nghiệp vụ hoàn chỉnh hiếm khi chỉ cần một DAO. Chẳng hạn, khi khách đặt hàng, hệ thống phải **giảm tồn kho**, **tạo đơn hàng** và **ghi các dòng hàng**. Nếu bước cuối thất bại mà hai bước đầu đã được commit, dữ liệu sẽ bị lệch: kho đã bị trừ nhưng đơn hàng chưa được lưu đầy đủ.

Điểm mấu chốt là **ranh giới transaction phải bao trùm toàn bộ thao tác nghiệp vụ**, không bị chia nhỏ theo số DAO. Với JDBC thuần, cách rõ ràng nhất là để **tầng Service mượn một `Connection`**, tắt auto-commit, truyền chính kết nối đó qua các DAO, rồi `commit()` khi tất cả bước thành công hoặc `rollback()` khi có lỗi.

Bài thuộc chương **DAO và Repository** của module **JDBC**, tập trung vào cách phân chia trách nhiệm giữa Service, DAO và các API chuẩn `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`. Ta sẽ xây dựng ví dụ đặt đơn hàng với ba DAO, khóa sinh, cập nhật tồn kho có điều kiện, quản lý lỗi, concurrency và kiểm thử tích hợp.

Sau bài học, bạn sẽ có thể:

- Xác định **Service sở hữu transaction**, còn DAO sở hữu SQL và mapping.
- Phối hợp nhiều DAO thông qua **cùng một `Connection`** mà không tự commit trong từng DAO.
- Chống tình trạng trừ tồn kho vượt mức bằng một câu `UPDATE` có điều kiện và kiểm tra update count.
- Đọc khóa đơn hàng sinh tự động qua `RETURN_GENERATED_KEYS`/`getGeneratedKeys()` trước khi ghi dòng con.
- Đảm bảo `rollback()` bao phủ cả các DAO đã chạy thành công khi một bước sau thất bại.
- Phân biệt vấn đề transaction, transaction isolation, lock, timeout, deadlock và retry.
- Viết integration test chứng minh dữ liệu **hoặc được lưu đầy đủ, hoặc không có thay đổi một phần**.

## 1. Vì sao một DAO thành công chưa có nghĩa nghiệp vụ thành công?

Giả sử khách hàng đặt hai sản phẩm:

```text
Khách đặt: SKU-A × 2 và SKU-B × 3

CheckoutService
   |
   +-- InventoryDao: trừ tồn kho SKU-A
   |
   +-- InventoryDao: trừ tồn kho SKU-B
   |
   +-- OrderDao: tạo một purchase_order
   |
   +-- OrderItemDao: tạo dòng hàng thứ nhất
   |
   +-- OrderItemDao: tạo dòng hàng thứ hai
   |
   +-- Trả orderId cho caller
```

Nếu mỗi DAO tự mở kết nối và dùng `autoCommit = true`, một sự cố ở lần chèn dòng thứ hai có thể để lại:

- Tồn kho SKU-A và SKU-B đã giảm.
- Đơn hàng cha và dòng thứ nhất đã tồn tại.
- Dòng thứ hai không được lưu.

Kết quả này không thỏa hợp đồng **đặt một đơn hàng nguyên vẹn**. Ngược lại, nếu tất cả SQL chạy trong cùng transaction, lỗi ở bất kỳ bước nào có thể kích hoạt rollback toàn bộ thay đổi chưa commit.

### Hai cách tổ chức đối lập

| Thiết kế | Vòng đời kết nối | Điều xảy ra nếu DAO cuối lỗi |
| --- | --- | --- |
| **Sai với nghiệp vụ nguyên tử:** mỗi DAO tự `getConnection()`, `executeUpdate()`, `close()` | Nhiều kết nối / nhiều transaction độc lập | Có thể để lại dữ liệu đã commit một phần |
| **Phù hợp:** Service lấy một `Connection`; mọi DAO dùng kết nối được truyền vào | Một transaction bao trùm nhiều DAO | Service có thể rollback toàn bộ trước khi commit |

`DataSource` nên là đối tượng được dùng chung để **cấp kết nối**, nhưng gọi `dataSource.getConnection()` hai lần **không bảo đảm nhận cùng transaction**, ngay cả khi cả hai kết nối đi qua cùng connection pool. Phải truyền rõ ràng **chính đối tượng `Connection` đang sở hữu transaction** hoặc dùng một transaction manager đã cấu hình đúng.

## 2. Chia trách nhiệm: Service làm gì, DAO làm gì?

Một thiết kế có thể kiểm thử và bảo trì:

| Thành phần | Trách nhiệm | Không nên làm |
| --- | --- | --- |
| **Controller / API** | Nhận yêu cầu, xác thực đầu vào ở lớp giao tiếp, gọi Service | Ghép trực tiếp một loạt SQL và tự điều khiển transaction ở nhiều nơi |
| **Application Service** | Điều phối bước nghiệp vụ, xác định transaction boundary, xử lý kết quả/thất bại | Chứa mọi chi tiết mapping từng cột `ResultSet` nếu đã có DAO |
| **InventoryDao** | Cập nhật và tra cứu tồn kho qua SQL tham số hóa | Tự `commit()` khi chỉ mới trừ được một SKU của đơn |
| **OrderDao** | Chèn/đọc đơn hàng cha, lấy generated key | Tự tạo transaction mới làm mất liên kết với các DAO khác |
| **OrderItemDao** | Chèn/đọc các dòng hàng của đơn | Dùng một connection khác không thuộc transaction đặt hàng |
| **Connection / transaction owner** | `setAutoCommit(false)`, `commit()`, `rollback()`, `close()` | Để DAO thấp hơn kết thúc transaction của toàn bộ nghiệp vụ |

Sơ đồ luồng kết nối:

```text
                        DataSource / pool
                              |
                   CheckoutService.getConnection()
                              |
                   setAutoCommit(false)
                              |
                +-------------+-------------+
                |             |             |
                v             v             v
          InventoryDao    OrderDao     OrderItemDao
                |             |             |
                +------ CÙNG Connection ----+
                              |
                   Thành công tất cả?
                         /         \
                       Có          Không
                        |            |
                      commit       rollback
                         \          /
                          close Connection
```

Trong bài này, DAO nhận `Connection` như đối số để hợp đồng sở hữu transaction hiển thị ngay trong chữ ký phương thức. Đây không phải cách duy nhất: framework như Spring có thể quản lý transaction qua proxy/context. Tuy nhiên, **đừng trộn hai mô hình một cách ngẫu nhiên**; nếu một tầng đã có transaction manager, DAO phải tham gia đúng transaction đó thay vì tự mở connection ngoài context.

### DAO và Repository khác nhau ở đâu?

Tên gọi *DAO* thường nhấn mạnh các thao tác truy cập dữ liệu như `insert`, `update`, `find`, còn *Repository* thường nhấn mạnh cách tập hợp và truy xuất các đối tượng miền nghiệp vụ. Trong dự án thực tế, tên gọi có thể giao nhau. Dù gọi là `OrderDao` hay `OrderRepository`, **ranh giới transaction vẫn dựa theo use case**, không dựa theo tên lớp.

## 3. Mô hình dữ liệu cho ví dụ đặt hàng

Ta dùng ba bảng quan hệ:

```sql
-- DDL minh họa gần SQL chuẩn; tùy DBMS có thể cần đổi cú pháp IDENTITY.
CREATE TABLE product_stock (
    sku           VARCHAR(64) PRIMARY KEY,
    available_qty INTEGER NOT NULL CHECK (available_qty >= 0)
);

CREATE TABLE purchase_order (
    order_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_ref  VARCHAR(64) NOT NULL,
    order_status  VARCHAR(20) NOT NULL,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE purchase_order_item (
    order_id BIGINT NOT NULL,
    line_no  INTEGER NOT NULL,
    sku      VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),

    PRIMARY KEY (order_id, line_no),
    UNIQUE (order_id, sku),
    FOREIGN KEY (order_id) REFERENCES purchase_order(order_id),
    FOREIGN KEY (sku) REFERENCES product_stock(sku)
);
```

Quan hệ chính:

```text
product_stock (sku)             purchase_order (order_id)
       ^                                ^
       |                                |
       | FK sku                         | FK order_id
       +-------- purchase_order_item ---+
                 (order_id, line_no)
```

Những điểm thiết kế đáng lưu ý:

1. `available_qty >= 0` được bảo vệ cả bằng constraint và câu `UPDATE` có điều kiện.
2. `purchase_order.order_id` do DB sinh; Service cần lấy khóa này để chèn hàng con.
3. `purchase_order_item` có khóa chính ghép `(order_id, line_no)` và ràng buộc `UNIQUE (order_id, sku)`.
4. Một mã SKU chỉ xuất hiện **một lần** trong một đơn của ví dụ; Service sẽ từ chối đầu vào trùng để không trừ kho hai lần ngoài ý muốn.
5. `customer_ref` là định danh khách hàng ở mức ví dụ; hệ thống thật có thể thêm bảng và ràng buộc khóa ngoại tới khách hàng.

Sử dụng `GENERATED ALWAYS AS IDENTITY`, `CHECK` và cú pháp schema phải phù hợp DBMS cụ thể (PostgreSQL, SQL Server, MySQL, Oracle, H2...). Các ví dụ Java dùng API JDBC chuẩn, nhưng **DDL và khả năng `getGeneratedKeys()` phải được xác minh trên đúng DB/driver**.

### Dữ liệu ban đầu để thực hành

```sql
INSERT INTO product_stock(sku, available_qty)
VALUES ('SKU-A', 8);

INSERT INTO product_stock(sku, available_qty)
VALUES ('SKU-B', 5);

INSERT INTO product_stock(sku, available_qty)
VALUES ('SKU-Z', 0);
```

Một đơn đặt `SKU-A × 2` và `SKU-B × 3` có thể hoàn thành, để lại số lượng `6` và `2`. Nếu đơn thứ hai chứa `SKU-Z × 1`, thao tác phải **thất bại và không giữ thay đổi một phần của các SKU đã trừ trước đó**.

## 4. Định nghĩa đầu vào nghiệp vụ và lỗi thiếu tồn kho

Dữ liệu đầu vào nên được kiểm tra **trước khi mượn kết nối** và trước khi thực hiện bất kỳ SQL nào. Với Java 17+, một `record` có thể biểu diễn một dòng đặt hàng:

**Tệp `PurchaseLine.java`**

```java
import java.util.Objects;

public record PurchaseLine(String sku, int quantity) {
    public PurchaseLine {
        Objects.requireNonNull(sku, "sku");
        if (sku.isBlank() || sku.length() > 64) {
            throw new IllegalArgumentException(
                    "sku must contain 1..64 characters");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
    }
}
```

Các quy tắc này trùng với một phần schema; DB constraint vẫn cần thiết vì **nhiều ứng dụng hoặc tiến trình khác** có thể ghi vào DB mà không đi qua validation Java. Mã production còn phải xác định quy tắc độ dài ký tự/byte, Unicode và chuẩn hóa SKU theo hệ thống.

Một lỗi nghiệp vụ có thể được biểu diễn riêng:

**Tệp `InsufficientStockException.java`**

```java
public final class InsufficientStockException extends RuntimeException {
    public InsufficientStockException(String sku) {
        super("Product unavailable or insufficient stock: " + sku);
    }
}
```

Trong ví dụ, lỗi này có thể nghĩa là **không có sản phẩm** hoặc **không còn đủ số lượng**, vì câu `UPDATE` trả `0` trong cả hai tình huống. Nếu API cần phân biệt chính xác hai lý do, có thể truy vấn chẩn đoán sau khi thất bại hoặc thiết kế hợp đồng riêng. Tuy nhiên, **không được dùng một câu `SELECT` trước `UPDATE` làm kiểm tra duy nhất**, vì tồn kho có thể thay đổi giữa hai câu lệnh.

## 5. `InventoryDao`: trừ kho bằng `UPDATE` có điều kiện

**Tệp `InventoryDao.java`**

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class InventoryDao {
    private static final String RESERVE = """
            UPDATE product_stock
            SET available_qty = available_qty - ?
            WHERE sku = ? AND available_qty >= ?
            """;

    public void reserve(
            Connection connection, String sku, int quantity)
            throws SQLException {

        try (PreparedStatement statement =
                     connection.prepareStatement(RESERVE)) {
            statement.setInt(1, quantity);
            statement.setString(2, sku);
            statement.setInt(3, quantity);

            int affected = statement.executeUpdate();
            if (affected == 0) {
                throw new InsufficientStockException(sku);
            }
            if (affected != 1) {
                throw new SQLException(
                        "Expected one stock row for SKU " + sku
                                + ", got " + affected);
            }
        }
    }
}
```

Tại sao câu SQL này tốt hơn cách **đọc số lượng rồi cập nhật**?

```sql
-- Không nên tách thành một kiểm tra duy nhất rồi tin rằng kết quả không đổi:
SELECT available_qty FROM product_stock WHERE sku = ?;

-- Sau đó lấy kết quả cũ ở Java để tính và ghi lại:
UPDATE product_stock SET available_qty = ? WHERE sku = ?;
```

Hai transaction có thể đọc cùng một số lượng ban đầu rồi cố ghi đè. Ngược lại, biểu thức `available_qty = available_qty - ?` kết hợp `WHERE available_qty >= ?` cho phép DB kiểm tra điều kiện ngay khi thực thi thao tác cập nhật. Trên DBMS hỗ trợ transaction và khóa hàng phù hợp, đây là nền tảng thực tế để tránh bán vượt số lượng tồn kho.

### Số hàng cập nhật là một phần hợp đồng nghiệp vụ

| `executeUpdate()` | Diễn giải trong ví dụ |
| ---: | --- |
| `1` | Đã giảm đúng một hàng tồn kho trong transaction hiện tại, **chưa commit** |
| `0` | Không tìm thấy SKU hoặc số lượng sẵn có không đáp ứng điều kiện |
| `> 1` | Không phù hợp với kỳ vọng một SKU là khóa chính, cần báo lỗi |

`executeUpdate() == 1` **không có nghĩa transaction đã commit**, và cũng không có nghĩa toàn đơn hàng đã thành công. Service còn phải chèn đơn hàng và các dòng, sau đó mới commit. DAO không tự quyết định rollback riêng trong trường hợp thiếu tồn kho; nó báo lỗi cho Service đang sở hữu transaction.

## 6. `OrderDao`: tạo đơn cha và lấy khóa được sinh

**Tệp `OrderDao.java`**

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public final class OrderDao {
    private static final String INSERT = """
            INSERT INTO purchase_order(customer_ref, order_status)
            VALUES (?, ?)
            """;

    public long insert(
            Connection connection, String customerRef)
            throws SQLException {

        try (PreparedStatement statement =
                     connection.prepareStatement(
                             INSERT, Statement.RETURN_GENERATED_KEYS)) {

            statement.setString(1, customerRef);
            statement.setString(2, "PLACED");

            if (statement.executeUpdate() != 1) {
                throw new SQLException(
                        "Expected exactly one purchase_order row");
            }

            try (ResultSet keys = statement.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException(
                            "Driver did not return generated order_id");
                }

                long orderId = keys.getLong(1);
                if (keys.wasNull() || orderId <= 0) {
                    throw new SQLException("Invalid generated order_id");
                }
                if (keys.next()) {
                    throw new SQLException(
                            "Unexpected multiple generated-key rows");
                }

                return orderId;
            }
        }
    }
}
```

Khóa `orderId` được lấy sau khi chèn đơn cha **trong cùng transaction chưa commit**. Các dòng con chèn bằng chính `Connection` đó có thể tham chiếu khóa vừa sinh theo ràng buộc foreign key.

`RETURN_GENERATED_KEYS` là API chuẩn JDBC, nhưng **driver/DB có thể khác nhau ở việc hỗ trợ, thứ tự cột khóa và loại giá trị được trả**. Trong môi trường có nhiều cột tự sinh hoặc trigger, nên kiểm tra metadata và, khi thích hợp, yêu cầu các cột khóa cụ thể qua overload `prepareStatement(sql, columnNames)` được driver hỗ trợ.

**Không dùng `SELECT MAX(order_id)` để tìm ID vừa chèn**: câu đó có thể lấy khóa của transaction khác khi nhiều request đặt hàng đồng thời. Cũng không assert ID tăng liên tiếp: sequence/identity có thể tạo khoảng trống khi transaction rollback.

## 7. `OrderItemDao`: lưu dòng con bằng cùng transaction

**Tệp `OrderItemDao.java`**

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class OrderItemDao {
    private static final String INSERT = """
            INSERT INTO purchase_order_item
                (order_id, line_no, sku, quantity)
            VALUES (?, ?, ?, ?)
            """;

    public void insert(
            Connection connection, long orderId,
            int lineNo, PurchaseLine line) throws SQLException {

        try (PreparedStatement statement =
                     connection.prepareStatement(INSERT)) {
            statement.setLong(1, orderId);
            statement.setInt(2, lineNo);
            statement.setString(3, line.sku());
            statement.setInt(4, line.quantity());

            if (statement.executeUpdate() != 1) {
                throw new SQLException(
                        "Expected one purchase_order_item row");
            }
        }
    }
}
```

`OrderItemDao` không cần biết `DataSource`, connection pool hay cách Service lấy khóa đơn hàng. Nó chỉ nhận `orderId` và `Connection` đã có. Với số lượng dòng rất lớn, DAO có thể dùng `PreparedStatement.addBatch()`/`executeBatch()`, nhưng **batch vẫn phải ở trong transaction của Service** và phải xử lý `BatchUpdateException`, `SUCCESS_NO_INFO` cùng chính sách rollback. Ví dụ hiện tại chọn chèn từng dòng để tập trung vào **ranh giới giữa nhiều DAO**, không giả định batching là bắt buộc.

## 8. `CheckoutService`: nơi sở hữu transaction thực sự

Service là thành phần quyết định trình tự thao tác, không phải DAO. Nó kiểm tra dữ liệu đầu vào, sắp thứ tự khóa theo SKU để giảm khả năng deadlock, mở **một `Connection`**, gọi từng DAO, rồi `commit()` **một lần**.

**Tệp `CheckoutService.java`**

```java
import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import javax.sql.DataSource;

public final class CheckoutService {
    private final DataSource dataSource;
    private final InventoryDao inventoryDao;
    private final OrderDao orderDao;
    private final OrderItemDao orderItemDao;

    public CheckoutService(
            DataSource dataSource,
            InventoryDao inventoryDao,
            OrderDao orderDao,
            OrderItemDao orderItemDao) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
        this.inventoryDao = Objects.requireNonNull(
                inventoryDao, "inventoryDao");
        this.orderDao = Objects.requireNonNull(orderDao, "orderDao");
        this.orderItemDao = Objects.requireNonNull(
                orderItemDao, "orderItemDao");
    }

    public long placeOrder(
            String customerRef, List<PurchaseLine> requestedLines)
            throws SQLException {

        // Kiểm tra đầu vào TRƯỚC KHI mượn kết nối.
        Objects.requireNonNull(customerRef, "customerRef");
        if (customerRef.isBlank() || customerRef.length() > 64) {
            throw new IllegalArgumentException("Invalid customerRef");
        }

        List<PurchaseLine> lines = List.copyOf(
                Objects.requireNonNull(requestedLines, "requestedLines"));
        if (lines.isEmpty() || lines.size() > 200) {
            throw new IllegalArgumentException(
                    "Order must contain 1..200 lines");
        }

        Set<String> seen = new HashSet<>();
        for (PurchaseLine line : lines) {
            if (!seen.add(line.sku())) {
                throw new IllegalArgumentException(
                        "Duplicate SKU in one order: " + line.sku());
            }
        }

        // Giữ thứ tự dòng gốc để chèn vào purchase_order_item.
        // Chỉ sắp xếp BẢN SAO cho bước khóa/cập nhật tồn kho.
        List<PurchaseLine> stockOrder = new ArrayList<>(lines);
        stockOrder.sort(Comparator.comparing(PurchaseLine::sku));

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                // Bước 1: giảm kho theo thứ tự SKU nhất quán.
                for (PurchaseLine line : stockOrder) {
                    inventoryDao.reserve(
                            connection, line.sku(), line.quantity());
                }

                // Bước 2: tạo đơn cha và lấy khóa sinh.
                long orderId = orderDao.insert(connection, customerRef);

                // Bước 3: tạo các dòng con theo thứ tự yêu cầu ban đầu.
                for (int index = 0; index < lines.size(); index++) {
                    orderItemDao.insert(
                            connection, orderId, index + 1,
                            lines.get(index));
                }

                // Không có bước nào lỗi; xác nhận toàn transaction.
                connection.commit();
                return orderId;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
```

Cách gọi:

```java
CheckoutService service = new CheckoutService(
        dataSource,
        new InventoryDao(),
        new OrderDao(),
        new OrderItemDao());

long orderId = service.placeOrder(
        "CUSTOMER-42",
        List.of(
                new PurchaseLine("SKU-A", 2),
                new PurchaseLine("SKU-B", 3)));

System.out.println("Created order: " + orderId);
```

Nếu dữ liệu mẫu có `SKU-A = 8` và `SKU-B = 5`, một lời gọi hợp lệ có thể kết thúc với `SKU-A = 6` và `SKU-B = 2`, một đơn `PLACED` và hai dòng con. **Mọi kết quả đó chỉ được coi là hoàn thành sau khi `connection.commit()` trả về thành công.**

### Phân tích vòng đời của từng bước

| Bước | DAO liên quan | Trạng thái transaction |
| --- | --- | --- |
| `setAutoCommit(false)` | Không phải DAO | Transaction được ứng dụng quản lý rõ ràng |
| Trừ `SKU-A` và `SKU-B` | `InventoryDao` | Thay đổi chưa commit; có thể rollback |
| Chèn `purchase_order` | `OrderDao` | Đơn cha chưa commit; khóa sinh có thể dùng trong cùng transaction |
| Chèn `purchase_order_item` | `OrderItemDao` | Dòng con chưa commit, FK được kiểm tra theo DB |
| `commit()` | Service | Toàn bộ thay đổi đủ điều kiện được xác nhận |
| Bất kỳ `SQLException`/`RuntimeException` nào trước commit | Service | Cố rollback toàn transaction, sau đó ném lỗi lên caller |
| `close()` của `Connection` | Service | Trả hoặc đóng kết nối đúng vòng đời; không giữ connection trong DAO |

### Vì sao lỗi rollback được gắn vào lỗi gốc?

Nếu `OrderItemDao` gặp `SQLException` do foreign key, unique constraint hay lỗi kết nối, sau đó `connection.rollback()` cũng ném lỗi, chương trình cần bảo toàn **nguyên nhân đầu tiên**. Đoạn `failure.addSuppressed(rollbackFailure)` giúp caller thấy lỗi gốc cùng lỗi cleanup. Nếu chỉ ném lỗi rollback, quá trình chẩn đoán có thể bỏ sót lệnh SQL gây thất bại ban đầu.

Mã trên xử lý các lỗi `SQLException` và `RuntimeException` thông thường. Lỗi nghiêm trọng cấp JVM (`Error`) cần chiến lược vận hành riêng; không dùng `catch (Throwable)` để im lặng tiếp tục nghiệp vụ khi JVM không còn ổn định. `try-with-resources` vẫn chịu trách nhiệm đóng connection theo hợp đồng Java khi thoát phạm vi.

### Có cần `connection.setAutoCommit(true)` trong `finally` không?

Ở ví dụ, Service **sở hữu và đóng connection** sau mỗi thao tác. Một connection pool có trách nhiệm quản lý/reset trạng thái connection logic theo cấu hình của nó; hệ thống phải kiểm chứng việc này. Nếu một helper nhận **connection do caller sở hữu**, helper không được tự ý đổi auto-commit, commit hoặc đóng connection. Nếu thực sự cần khôi phục trạng thái connection dùng lại, phải đảm bảo transaction đã kết thúc trước khi đổi `autoCommit`, vì **bật lại auto-commit có thể commit transaction còn đang mở** theo hợp đồng JDBC.

## 9. Tại sao chỉ đọc số lượng rồi ghi lại có thể làm mất cập nhật?

Một anti-pattern phổ biến:

```text
Tồn kho ban đầu: 5

Transaction A đọc: available = 5
Transaction B đọc: available = 5
Transaction A tính còn 2, ghi available = 2
Transaction B tính còn 1, ghi available = 1

Giá trị cuối 1 có thể không phản ánh tổng lượng đã bán.
```

Cách `InventoryDao.reserve` dùng:

```sql
UPDATE product_stock
SET available_qty = available_qty - ?
WHERE sku = ? AND available_qty >= ?;
```

Đó là thao tác cập nhật **trên giá trị hiện tại trong DB**, kèm điều kiện đủ hàng. DBMS quản lý xung đột ghi trên cùng hàng theo cơ chế locking/MVCC của nó. Nếu transaction A giữ khóa, transaction B có thể phải chờ; khi có thể cập nhật, điều kiện số lượng được đánh giá theo quy tắc transaction và engine. Cần kiểm thử theo isolation level thực tế, nhưng không nên giải quyết bằng một `SELECT` thường rồi ghi đè dữ liệu đã đọc trước đó.

### Cùng khóa, cùng thứ tự để giảm deadlock

Nếu đơn A cập nhật `SKU-A` rồi `SKU-B`, còn đơn B cập nhật `SKU-B` rồi `SKU-A`, hai transaction có thể giữ khóa mà đối phương đang cần, tạo **deadlock**. Ví dụ Service tạo bản sao `stockOrder` và sắp theo SKU để tất cả đơn đi qua thứ tự cập nhật nhất quán.

Thứ tự nhất quán **giảm** khả năng deadlock, không triệt tiêu mọi deadlock: trigger, index bổ sung, foreign key, các quy trình khác và cách optimizer thực thi vẫn có thể thay đổi thứ tự khóa thực tế. Khi DB thông báo deadlock hoặc serialization failure, transaction thất bại thường cần được rollback trước khi thử lại **toàn bộ nghiệp vụ**, không chỉ lặp lại một câu `UPDATE`.

## 10. Nhiều DAO dùng chung transaction nhưng không nên dùng chung state tùy tiện

Một nguyên tắc quan trọng là **chia sẻ `Connection` của thao tác**, không phải chia sẻ `PreparedStatement` hoặc `ResultSet` giữa các DAO/thread:

```text
ĐƯỢC:
  Service -> same Connection -> InventoryDao
                              -> OrderDao
                              -> OrderItemDao

KHÔNG NÊN:
  singleton PreparedStatement dùng chung cho mọi request
  một Connection mutable được chia sẻ đồng thời giữa các thread
  trả ResultSet ra ngoài sau khi DAO đã đóng statement/connection
```

`Connection` là tài nguyên có trạng thái: auto-commit, isolation, transaction, warning và các lựa chọn session. Việc gọi nhiều DAO **tuần tự** trên cùng connection là một mô hình hợp lý cho một use case. Trái lại, đưa connection đó cho nhiều thread ghi song song có thể dẫn đến race, lỗi driver hoặc thứ tự thao tác không thể kiểm soát. Muốn xử lý nhiều tác vụ độc lập đồng thời, hãy cho mỗi tác vụ một transaction và connection phù hợp.

Để không nhầm, chữ ký DAO nên rõ ràng:

```java
// DAO dùng connection được truyền vào, không sở hữu transaction.
int update(Connection connection, ... ) throws SQLException;

// Service sở hữu transaction và connection.
long placeOrder(...) throws SQLException;
```

Đoạn trên là **chữ ký minh họa**, không phải mã Java có thể biên dịch vì `...` là ký hiệu lược bỏ. Mục đích là nhấn mạnh hợp đồng sở hữu.

## 11. Khi nào một DAO nên tự mở `DataSource.getConnection()`?

Không phải mọi DAO đều bắt buộc nhận `Connection`. Một phương thức **đọc độc lập** như `findById(id)` có thể mượn connection, chạy truy vấn và đóng tài nguyên ngay trong DAO. Vấn đề xảy ra khi cùng phương thức đó được gọi **giữa một transaction nghiệp vụ lớn** mà caller kỳ vọng nó đọc được dữ liệu chưa commit trên connection khác hoặc cùng tham gia rollback.

Có hai kiểu API nên phân biệt:

| Kiểu API | Ai sở hữu `Connection`? | Trường hợp thích hợp |
| --- | --- | --- |
| `findById(DataSource)` hoặc DAO tự mượn connection | DAO | Truy vấn độc lập, không cần tham gia transaction của caller |
| `findById(Connection connection, id)` | Caller / Service | Đọc dữ liệu trong transaction hoặc snapshot đang dùng |
| `insert(Connection connection, ...)` | Caller / Service | Bước ghi phối hợp với nhiều DAO trong một use case |

Một dự án có thể cung cấp **hai overload** hoặc dùng một `TransactionContext`/Unit of Work được quản lý tập trung. Nhưng phải tránh “DAO thỉnh thoảng tự mượn connection dù caller đang truyền transaction”, vì mô hình không nhất quán này gây lỗi khó nhận ra.

### Unit of Work và transaction helper

Trong ứng dụng lớn, có thể trích logic boilerplate `setAutoCommit(false)`/`commit()`/`rollback()` sang một **transaction helper**:

```text
Service
   |
TransactionRunner.inTransaction(connection -> {
    inventoryDao.reserve(connection, ...);
    long orderId = orderDao.insert(connection, ...);
    orderItemDao.insert(connection, ...);
    return orderId;
})
```

Helper phải thực hiện một transaction duy nhất, bảo toàn lỗi và đóng connection. Không tạo helper mà mỗi DAO lại tự gọi `inTransaction`, vì khi ấy ranh giới nghiệp vụ bị chia nhỏ trở lại. Ví dụ `CheckoutService` ở phần trước chủ động viết transaction inline để người học thấy rõ chính xác từng bước.

## 12. Các lỗi giữa chừng: kết quả nào phải rollback?

Xét những điểm thất bại có thể xuất hiện:

| Lỗi | Thời điểm | Kết quả mong muốn |
| --- | --- | --- |
| SKU không tồn tại | `InventoryDao.reserve` trả update count 0 | Không có đơn/dòng, không giữ bất kỳ lần giảm kho trước đó |
| Tồn kho không đủ | Câu `UPDATE` có điều kiện không tác động hàng | Rollback mọi thay đổi trước đó trong cùng transaction |
| Không lấy được generated key | `OrderDao.insert` đã chạy nhưng `getGeneratedKeys` lỗi | Rollback giảm kho và hàng đơn cha chưa commit |
| Vi phạm khóa ngoại ở dòng con | `OrderItemDao.insert` ném `SQLException` | Rollback đơn cha, các dòng đã chèn và giảm kho |
| Bị deadlock hoặc serialization failure | DB hủy hoặc đánh dấu transaction không dùng tiếp | Rollback, sau đó quyết định retry toàn transaction nếu an toàn |
| Connection lỗi trước commit | Driver ném `SQLException` | Cố rollback/đóng, báo thất bại; không giữ connection lỗi |
| Lỗi ngay lúc `commit()` | Có thể mất phản hồi từ DB | Trạng thái commit **có thể không rõ**, cần đối soát/idempotency |
| Gửi email xác nhận trước commit rồi transaction lỗi | Email đã ra hệ thống bên ngoài | Rollback DB **không** hủy email; phải đổi thiết kế side effect |

### Lỗi commit không rõ trạng thái

Một trường hợp quan trọng: `connection.commit()` đã được gửi tới DB, DB có thể đã commit nhưng kết nối bị mất trước khi Java nhận phản hồi. Khi ấy, caller nhận `SQLException` nhưng **không thể mặc định đơn hàng chắc chắn chưa được tạo**. `rollback()` được gọi trong nhánh xử lý lỗi là cố gắng tốt nhất; nó không thể chứng minh transaction đã bị hoàn tác nếu server đã hoàn tất commit.

Vì vậy, hệ thống nhận yêu cầu đặt hàng từ HTTP nên cân nhắc một **`request_id` duy nhất** kèm unique constraint, bảng idempotency hoặc cơ chế đối soát để nhận biết lần đặt trước đã hoàn thành hay chưa. Không tự retry nguyên hàm `placeOrder` vô hạn sau mọi lỗi mạng; có thể tạo hai đơn và giảm tồn kho hai lần nếu lần đầu thực tế đã commit.

## 13. Transaction isolation, lock và retry trong Service

Một transaction bảo đảm tính nguyên tử của các bước ghi theo khả năng DB, nhưng **không giải quyết mọi vấn đề đồng thời**. Các DAO vẫn cần SQL đúng và chiến lược khóa hợp lý.

### Không tùy tiện tăng isolation chỉ để “an toàn hơn”

`Connection.setTransactionIsolation(...)` cho phép yêu cầu mức cô lập như `READ_COMMITTED`, `REPEATABLE_READ` hoặc `SERIALIZABLE` khi DB/driver hỗ trợ. Mức cô lập cao hơn có thể tăng tranh chấp, phát sinh serialization failure hoặc giảm thông lượng. Với thao tác giảm tồn kho có điều kiện, nhiều hệ thống có thể thiết kế an toàn ở `READ_COMMITTED` nhờ atomic `UPDATE`, nhưng phải **kiểm chứng ngữ nghĩa của DBMS mục tiêu**.

Nếu Service thay đổi isolation level của kết nối, cần xác định ai quản lý trạng thái khi trả về pool. Không để một DAO tự thay isolation ở giữa giao dịch mà không báo cho Service.

### Retry phải ở ngoài transaction đã lỗi

Mẫu về mặt khái niệm:

```text
attempt #1:
  mở connection -> bắt đầu transaction -> gọi nhiều DAO
  DB báo deadlock
  rollback/close

attempt #2 (nếu lỗi retryable và an toàn):
  mở connection mới -> bắt đầu transaction mới
  gọi LẠI TOÀN BỘ use case với request ID kiểm soát được
  commit hoặc tiếp tục báo lỗi
```

Không thực thi tiếp `OrderItemDao` trong transaction mà DB đã đánh dấu lỗi. Không retry riêng `InventoryDao.reserve` sau khi các bước khác đã chạy mà không định nghĩa rõ trạng thái. Chiến lược retry cần:

- **Phân loại đúng** SQLState/mã lỗi của DBMS, thay vì bắt mọi `SQLException`.
- **Giới hạn số lần thử** và áp dụng backoff/jitter khi nhiều request cùng tranh chấp.
- **Idempotency** nếu có khả năng lần chạy trước đã commit hoặc gọi tới hệ thống bên ngoài.
- **Metrics và logging** đủ để biết số lần retry, nguyên nhân và độ trễ.
- Tránh retry đối với lỗi schema, constraint, dữ liệu không hợp lệ hoặc thiếu tồn kho đã được xác nhận.

## 14. Thao tác nghiệp vụ và tác động bên ngoài database

Một use case đặt hàng thường muốn gửi email, ghi sự kiện vào message broker hoặc gọi cổng thanh toán. Những hệ thống này **không thuộc transaction của một `Connection` JDBC thông thường**.

### Sai: gọi API bên ngoài trước khi commit DB

```text
transaction DB:
  InventoryDao.reserve
  OrderDao.insert
  PaymentGateway.chargeCard  <-- tác động ngoài DB đã xảy ra
  OrderItemDao.insert        <-- gặp lỗi
  rollback DB               <-- không hoàn tiền tự động
```

Nếu Service chỉ bắt `SQLException` rồi rollback DB, trạng thái hai hệ thống có thể lệch. Với các luồng cần phối hợp DB và broker, một giải pháp thường dùng là **transactional outbox**:

```text
Một JDBC transaction:
  InventoryDao.reserve
  OrderDao.insert
  OrderItemDao.insert
  OutboxDao.insert(event)
  COMMIT
          |
          v
Worker riêng đọc outbox đã commit
          |
          v
Gửi event tới broker (có retry + deduplication)
```

`OutboxDao` cũng phải dùng **cùng `Connection`**. Nếu transaction rollback, event outbox chưa commit cũng biến mất. Tuy nhiên, worker gửi event **sau commit** cần xử lý ít nhất một lần gửi có thể bị lặp: consumer cần idempotency hoặc cơ chế deduplication. Outbox không biến hai tài nguyên độc lập thành một transaction phân tán hoàn hảo; nó cung cấp cách tổ chức đáng tin cậy hơn việc gửi trước commit.

Với thanh toán thật, có thể cần thiết kế trạng thái đơn hàng, reservation, idempotency key, API hoàn tiền hoặc **saga/compensation**. Một JDBC transaction chỉ bao phủ thao tác trên những tài nguyên cùng tham gia transaction mà DB hỗ trợ; nó không thể tự rollback một HTTP request đã thành công.

## 15. Kiểm thử tích hợp để chứng minh các DAO phối hợp đúng

Unit test mock từng DAO có thể kiểm tra **thứ tự gọi phương thức**, nhưng không chứng minh **foreign key, khóa, isolation, commit/rollback hay update count**. Vì vậy, cần ít nhất một số integration test trên DBMS/driver gần môi trường triển khai.

### Ma trận kiểm thử

| Tình huống | Dữ liệu đầu vào / thao tác | Điều cần xác minh sau khi kết thúc |
| --- | --- | --- |
| Đặt đơn thành công | SKU-A 8 chiếc, SKU-B 5 chiếc; đặt 2 và 3 | Kho còn 6 và 2; có một đơn với hai dòng con |
| SKU thiếu ở bước đầu | Đặt SKU không tồn tại | Không có đơn/dòng, không thay đổi kho |
| SKU thiếu ở bước sau | `SKU-A × 2` rồi `SKU-Z × 1` | SKU-A được rollback về 8; không có đơn/dòng |
| DAO ghi dòng con ném lỗi | Kích hoạt unique/FK constraint ở môi trường test | Trừ kho và đơn cha đều rollback |
| Sai số lượng | `quantity = 0` hoặc âm | Java từ chối trước khi mở kết nối |
| SKU trùng trong danh sách | Hai dòng cùng SKU | Java từ chối trước khi tạo transaction |
| `getGeneratedKeys` không hỗ trợ | Thử DB/driver hoặc giả lập lỗi hợp đồng | Báo lỗi, không commit thay đổi trước đó |
| Hai checkout đồng thời khi kho chỉ đủ một đơn | Hai transaction đặt cùng SKU | Tối đa một thao tác ghi thành công, không có `available_qty < 0` |
| Deadlock/serialization failure | Chạy kịch bản đồng thời có kiểm soát | Transaction thất bại được rollback; retry toàn use case nếu có |
| Lỗi commit/mất kết nối | Mô phỏng trường hợp có thể xảy ra | Không retry mù; kiểm tra thiết kế request ID/idempotency |
| Connection pool size nhỏ | Nhiều request đồng thời | Kiểm tra timeout khi mượn connection, không nhầm với lỗi SQL |

### Ví dụ kiểm tra rollback khi một SKU thiếu ở bước sau

Sau khi nạp dữ liệu nền độc lập:

```sql
INSERT INTO product_stock(sku, available_qty)
VALUES ('IT-A', 8);

INSERT INTO product_stock(sku, available_qty)
VALUES ('IT-Z', 0);
```

Một test JUnit 5 có thể gọi `placeOrder` theo thứ tự SKU tăng dần:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

@Test
void insufficientSecondSkuRollsBackFirstReservation()
        throws SQLException {

    CheckoutService service = new CheckoutService(
            testDataSource,
            new InventoryDao(),
            new OrderDao(),
            new OrderItemDao());

    assertThrows(
            InsufficientStockException.class,
            () -> service.placeOrder(
                    "IT-CUSTOMER",
                    List.of(
                            new PurchaseLine("IT-A", 2),
                            new PurchaseLine("IT-Z", 1))));

    // Query lại bằng một Connection mới, không dùng giá trị cache.
    try (Connection observer = testDataSource.getConnection();
         PreparedStatement statement = observer.prepareStatement(
                 "SELECT available_qty FROM product_stock WHERE sku = ?")) {

        statement.setString(1, "IT-A");
        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                throw new AssertionError("Missing fixture IT-A");
            }
            assertEquals(8, result.getInt(1));
        }
    }
}
```

Đoạn test minh họa giả định `testDataSource` được suite cung cấp, `IT-A`/`IT-Z` đã được seed và import `java.sql.*` cùng `java.util.List` có sẵn. Đây **chưa phải toàn bộ fixture JUnit độc lập**: dự án cần chuẩn bị dữ liệu trong database test, dọn nó sau test, và nên kiểm tra thêm rằng **không có đơn hàng hay dòng con** mới nào được tạo cho yêu cầu thất bại. Với test chạy song song, dùng SKU và customer reference riêng theo test run thay vì những khóa cố định `IT-A`/`IT-Z`.

### Vì sao không bọc toàn bộ test trong rollback của một connection khác?

`CheckoutService` ở ví dụ **tự mở connection và tự commit/rollback**. Nếu test framework mở `testConnection` khác rồi rollback ở cuối, thao tác của Service **không tự tham gia** transaction đó. Để kiểm tra một Service sở hữu transaction, dùng **database/schema test riêng và fixture có cleanup**; hoặc cung cấp một cơ chế transaction manager đúng để test và SUT chia sẻ cùng transaction khi thiết kế cho phép.

Khi test thành công đã commit đơn hàng, cleanup phải xóa dòng con trước đơn cha, sau đó khôi phục tồn kho **có kiểm soát** hoặc hủy toàn database/schema test. Tránh `TRUNCATE` các bảng đang được nhiều test dùng song song. Dùng tên khóa riêng và kiểm tra trạng thái DB sau cleanup để phát hiện test bị nhiễm dữ liệu.

## 16. Các lỗi thiết kế phổ biến

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| Mỗi DAO tự gọi `dataSource.getConnection()` cho từng bước checkout | Nhiều transaction độc lập, có thể ghi một phần | Service lấy một connection và truyền vào mọi DAO |
| DAO tự `commit()` sau mỗi `UPDATE` | Service không rollback được các bước đã commit | Chỉ transaction owner quyết định commit |
| Service gọi DAO bằng kết nối A, DAO khác dùng B | Đọc không thấy dữ liệu chưa commit, FK/lỗi khóa | Dùng đúng cùng `Connection` |
| DAO đóng `Connection` do Service truyền vào | Service mất quyền điều khiển transaction | DAO chỉ đóng statement/result set do mình tạo |
| Không đóng `PreparedStatement`/`ResultSet` | Rò rỉ cursor, handle hoặc tài nguyên DB | `try-with-resources` trong từng DAO |
| Đọc tồn kho rồi cập nhật bằng giá trị cũ | Race/lost update, nguy cơ bán vượt tồn kho | Dùng `UPDATE` có điều kiện và kiểm tra count |
| Chỉ kiểm tra exception, bỏ qua update count `0` | Có thể báo đặt hàng thành công dù chưa trừ kho | Diễn giải count đúng hợp đồng từng câu SQL |
| Hai checkout lấy khóa theo thứ tự đối nghịch | Tăng nguy cơ deadlock | Thứ tự cập nhật nhất quán, retry đúng chỗ |
| Dùng `SELECT MAX(id)` để lấy khóa đơn | Có thể lấy khóa của transaction khác | `getGeneratedKeys()` theo driver đã kiểm chứng |
| Chèn hàng con qua connection khác | FK có thể không thấy hàng cha chưa commit | Dùng cùng transaction/connection |
| `catch (SQLException)` rồi nuốt lỗi | Service có thể commit dữ liệu thiếu | Truyền lỗi lên transaction owner để rollback |
| Retry một DAO bên trong transaction lỗi | Trạng thái transaction có thể đã bị hỏng | Rollback, mở transaction mới, retry toàn use case |
| Gửi email/charge thẻ trước commit và nghĩ rollback đủ | Side effect bên ngoài không được hoàn tác | Outbox, idempotency, compensation phù hợp |
| Không kiểm tra lỗi `commit()` không rõ trạng thái | Có thể tạo đơn trùng khi retry | Request ID độc nhất và đối soát |
| Chia sẻ một `Connection` giữa nhiều request đồng thời | Tranh chấp trạng thái, lỗi không xác định | Mượn connection cho từng use case/transaction |
| Bật `autoCommit(true)` khi transaction chưa xong | Có thể xác nhận thay đổi ngoài ý muốn | Kết thúc transaction trước khi khôi phục state |
| Test chỉ mock DAO mà không thử DB thật | Không bắt lỗi FK, rollback, isolation và driver | Thêm integration test trên DBMS mục tiêu |

## 17. Câu hỏi và bài tập tự kiểm tra

**Bài 1 — Xác định transaction owner.** Một Service gọi ba DAO để giảm kho, tạo đơn và chèn dòng. Ai nên quyết định `commit()`? Tại sao?

**Đáp án:** Service (hoặc transaction manager của use case), vì chỉ nó biết cả ba bước đã thành công. Nếu từng DAO tự commit, một bước sau lỗi sẽ để lại kết quả một phần.

**Bài 2 — Cùng `DataSource` có đủ không?** Ba DAO đều lấy connection từ cùng một pool. Có thể khẳng định chúng cùng transaction không?

**Đáp án:** Không. Mỗi lần mượn có thể là logical/physical connection khác và transaction độc lập. Phải truyền cùng connection hoặc tham gia transaction manager đúng cách.

**Bài 3 — `executeUpdate() == 0`.** `InventoryDao` dùng `UPDATE ... WHERE sku = ? AND available_qty >= ?`. Khi kết quả là `0`, Service có nên tiếp tục chèn đơn?

**Đáp án:** Không. Theo hợp đồng ví dụ, SKU không tồn tại hoặc không đủ hàng. Ném lỗi nghiệp vụ và rollback những cập nhật tồn kho đã chạy trước đó.

**Bài 4 — Lỗi dòng cuối.** Kho đã giảm cho hai SKU, đơn cha đã được tạo và dòng đầu tiên đã chèn, nhưng dòng cuối vi phạm foreign key. `rollback()` có vai trò gì?

**Đáp án:** Nếu tất cả thao tác cùng transaction và chưa commit, rollback có thể hoàn tác giảm kho, đơn cha và dòng đã chèn. Việc mỗi DAO báo thành công trước đó không làm chúng được commit.

**Bài 5 — Sinh khóa.** Vì sao không dùng `SELECT MAX(order_id)` để chèn `purchase_order_item` khi nhiều người cùng đặt hàng?

**Đáp án:** Có thể lấy ID của giao dịch khác. Dùng `getGeneratedKeys()` của statement vừa chèn trên cùng connection; kiểm tra driver thực tế.

**Bài 6 — Thứ tự khóa.** Hai giỏ hàng chứa cùng các SKU nhưng được gửi theo thứ tự khác nhau. Vì sao Service sắp xếp SKU trước khi trừ kho?

**Đáp án:** Để các transaction có xu hướng lấy khóa theo thứ tự nhất quán, giảm khả năng vòng chờ/deadlock. Không bảo đảm loại bỏ mọi deadlock do SQL/DB phức tạp hơn.

**Bài 7 — Transaction sau commit.** Câu `commit()` ném lỗi vì mất kết nối. Có thể chắc chắn DB chưa tạo đơn và retry ngay không?

**Đáp án:** Không. Server có thể đã commit nhưng client mất phản hồi. Phải dùng idempotency/đối soát trước khi quyết định thử lại, tránh tạo hai đơn.

**Bài 8 — Outbox.** Một hệ thống cần phát `OrderPlaced` tới broker sau khi đặt hàng. Vì sao nên lưu bản ghi outbox trong cùng transaction JDBC?

**Đáp án:** Nếu transaction rollback, outbox cũng rollback. Chỉ những event đã commit được worker phát sau đó. Worker và consumer vẫn cần xử lý gửi lặp/idempotency.

**Bài 9 — Integration test.** Test Service tự mở connection riêng. Vì sao rollback connection của test framework không chứng minh dữ liệu Service đã được rollback?

**Đáp án:** Hai connection có transaction độc lập. Cần kiểm tra DB qua connection khác và dọn fixture, hoặc thiết kế để test chia sẻ transaction thật.

**Bài 10 — Retry.** Khi DB báo deadlock ở DAO thứ hai, có nên gọi lại riêng DAO thứ hai trên cùng transaction và tiếp tục DAO thứ ba?

**Đáp án:** Không nên. DB có thể đã hủy hoặc làm transaction không thể tiếp tục. Rollback transaction thất bại rồi, nếu nguyên nhân retryable và an toàn, mở transaction mới để thực hiện lại toàn use case.

## Tổng kết

**Phối hợp nhiều DAO trong một thao tác nghiệp vụ JDBC** đòi hỏi một ranh giới transaction rõ ràng. DAO tập trung vào `PreparedStatement`, `ResultSet`, SQL tham số hóa và mapping; **Service hoặc transaction manager** tập trung vào trình tự nghiệp vụ, dùng chung `Connection`, `commit()` và `rollback()`. Với ví dụ đặt hàng, `InventoryDao` trừ kho bằng một `UPDATE` có điều kiện, `OrderDao` tạo đơn và lấy `getGeneratedKeys()`, `OrderItemDao` ghi các dòng con, nhưng chỉ `CheckoutService` mới xác nhận toàn bộ thành công. Để hệ thống đúng khi chạy đồng thời, cần kiểm tra update count, thống nhất thứ tự khóa, xử lý deadlock và không retry mù khi kết quả commit chưa rõ. Cuối cùng, dùng integration test trên DB thật để chứng minh cả đường thành công lẫn rollback, và thiết kế outbox/idempotency khi use case cần phối hợp với những tài nguyên ngoài transaction JDBC.

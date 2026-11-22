# Bảng, hàng, cột và quan hệ với đối tượng Java

Trong ứng dụng Java dùng Spring Framework để truy cập cơ sở dữ liệu quan hệ, cần hiểu hai cách tổ chức dữ liệu: **mô hình quan hệ** trong database và **mô hình đối tượng** trong Java. Một bên lưu dữ liệu theo bảng, hàng, cột và khóa; bên kia biểu diễn dữ liệu bằng class, object, field và quan hệ giữa các object. Hai mô hình liên quan chặt chẽ nhưng không đồng nhất.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt bảng (table), hàng/bản ghi (row/record), cột (column), ô giá trị (cell), schema và kiểu dữ liệu SQL.
- Giải thích khóa chính, khóa ngoại, ràng buộc và quan hệ một-một, một-nhiều, nhiều-nhiều.
- Ánh xạ một hàng SQL thành object Java, hiểu vai trò của DTO, entity, JDBC `ResultSet` và Spring `RowMapper`.
- Hiểu tại sao `JOIN` tạo nhiều hàng kết quả và cách gom dữ liệu thành object có collection.
- Nhận biết khác biệt giữa tham chiếu object Java và khóa ngoại database; chọn cách đọc/ghi dữ liệu an toàn.

## 2. Bảng, hàng, cột thực sự là gì?

Xét bảng **customer**:

| customer_id | full_name | email |
| ---: | --- | --- |
| 1 | An | an@example.com |
| 2 | Bình | binh@example.com |

- **Bảng (table)** là tập các hàng cùng cấu trúc cột, ví dụ `customer`. Tên bảng giúp xác định một loại dữ liệu theo thiết kế nghiệp vụ.
- **Cột (column)** là một thuộc tính có tên và kiểu dữ liệu được định nghĩa ở schema: `customer_id BIGINT`, `full_name VARCHAR(100)`, `email VARCHAR(255)`.
- **Hàng (row)** là một bản ghi chứa giá trị cho các cột của bảng. Hàng `(1, 'An', 'an@example.com')` mô tả một khách hàng.
- **Ô (cell)** là giá trị tại giao điểm hàng và cột; `'An'` là giá trị cột `full_name` của hàng có `customer_id = 1`.
- **Schema** mô tả cấu trúc bảng, kiểu cột, khóa và các ràng buộc. Dữ liệu cụ thể là các hàng được lưu theo schema đó.

Một bảng không đồng nghĩa với một mảng Java; database quản lý dữ liệu lâu dài, truy vấn theo tập hợp, bảo đảm ràng buộc và phối hợp nhiều giao dịch. Thứ tự các hàng **không được bảo đảm** nếu truy vấn không có `ORDER BY`. Một kết quả `SELECT` có thể chứa ít/nhiều cột hơn bảng gốc, hoặc cột được tính từ biểu thức.

### Kiểu dữ liệu và giá trị NULL

Kiểu SQL giúp database kiểm tra, lưu và xử lý giá trị. Ví dụ `VARCHAR(100)` lưu văn bản có giới hạn độ dài, `BIGINT` lưu số nguyên lớn, `DECIMAL(12,2)` lưu số thập phân chính xác theo độ rộng quy định, `TIMESTAMP` lưu thời điểm dạng ngày-giờ (ngữ nghĩa múi giờ còn tùy kiểu cụ thể và hệ quản trị).

**SQL NULL** biểu thị giá trị chưa biết/không có; nó khác chuỗi rỗng `''`, số `0` và boolean `false`. So sánh bằng `= NULL` là sai ý định; dùng `IS NULL` hoặc `IS NOT NULL`. Biểu thức liên quan đến `NULL` thường tuân theo logic ba giá trị (true/false/unknown), nên phải để ý khi `WHERE` lọc dữ liệu.

Ví dụ: `email VARCHAR(255) NOT NULL` bắt buộc có giá trị khác NULL, nhưng tự nó chưa kiểm tra cú pháp email; cần validation nghiệp vụ riêng.

## 3. Thiết kế bảng ví dụ và các ràng buộc

Ta dùng ba bảng: khách hàng, đơn hàng, dòng hàng của đơn. SQL sau minh họa cấu trúc tương thích với các database hỗ trợ cú pháp phổ biến như PostgreSQL và H2; chi tiết DDL có thể khác theo hệ quản trị.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    full_name   VARCHAR(100) NOT NULL,
    email       VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE purchase_order (
    order_id     BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    created_at   TIMESTAMP NOT NULL,
    status       VARCHAR(20) NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id),
    CONSTRAINT ck_order_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TABLE order_item (
    order_item_id BIGINT PRIMARY KEY,
    order_id      BIGINT NOT NULL,
    product_name  VARCHAR(150) NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    DECIMAL(12,2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT fk_item_order
        FOREIGN KEY (order_id) REFERENCES purchase_order(order_id)
);
~~~

Ý nghĩa:

- **`PRIMARY KEY`** định danh duy nhất từng hàng; không được trùng và không được NULL. Ở ví dụ này, khóa là một cột. Thực tế cũng có **khóa ghép** gồm nhiều cột.
- **`FOREIGN KEY`** là ràng buộc tham chiếu: `purchase_order.customer_id` phải tham chiếu một `customer.customer_id` đang tồn tại, trừ khi cột cho phép NULL. Khóa ngoại **không tự tạo object Java**.
- **`NOT NULL`** cấm SQL NULL; **`UNIQUE`** yêu cầu giá trị duy nhất theo quy tắc của database; **`CHECK`** kiểm tra điều kiện tại database.
- **`DEFAULT`** (nếu khai báo) cung cấp giá trị khi thao tác INSERT bỏ qua cột tương ứng, theo quy tắc SQL/database.
- **Index** hỗ trợ một số kiểu tra cứu/join nhanh hơn, nhưng tốn không gian và chi phí cập nhật; khóa chính/unique thường được thực thi qua cấu trúc index, tùy database. Khóa ngoại không bảo đảm luôn tự tạo index trên cột tham chiếu.

Có thể thêm dữ liệu mẫu:

~~~sql
INSERT INTO customer (customer_id, full_name, email) VALUES
    (1, 'An', 'an@example.com'),
    (2, 'Bình', 'binh@example.com');

INSERT INTO purchase_order (order_id, customer_id, created_at, status) VALUES
    (100, 1, '2026-10-01 09:00:00', 'NEW'),
    (101, 1, '2026-10-02 10:30:00', 'PAID');

INSERT INTO order_item (order_item_id, order_id, product_name, quantity, unit_price) VALUES
    (1000, 100, 'Sách', 2, 120000.00),
    (1001, 100, 'Bút', 1, 10000.00),
    (1002, 101, 'Vở', 3, 15000.00);
~~~

Vì khóa được cấp thủ công trong ví dụ, khi thiết kế hệ thống thật cần chọn cơ chế sinh ID phù hợp (identity/sequence/UUID hoặc chiến lược khác), tránh trùng khóa và xử lý lỗi khi nhiều giao dịch ghi đồng thời.

## 4. Khóa biểu diễn quan hệ giữa các hàng

Mô hình trên có quan hệ:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ PURCHASE_ORDER : places
    PURCHASE_ORDER ||--o{ ORDER_ITEM : contains
    CUSTOMER {
        BIGINT customer_id PK
        VARCHAR full_name
        VARCHAR email
    }
    PURCHASE_ORDER {
        BIGINT order_id PK
        BIGINT customer_id FK
        TIMESTAMP created_at
        VARCHAR status
    }
    ORDER_ITEM {
        BIGINT order_item_id PK
        BIGINT order_id FK
        VARCHAR product_name
        INTEGER quantity
        DECIMAL unit_price
    }
~~~

**Một-nhiều (1:N):** Một khách hàng có thể có nhiều đơn hàng, nhưng mỗi `purchase_order` trong thiết kế này thuộc đúng một khách hàng. Một đơn hàng có nhiều dòng hàng. Trong schema ví dụ, database cho phép một đơn hàng chưa có dòng hàng; muốn yêu cầu ít nhất một dòng hàng cần bổ sung quy tắc nghiệp vụ/giao dịch phù hợp.

**Một-một (1:1):** Ví dụ bảng `customer_profile` có `customer_id` vừa là khóa chính vừa là khóa ngoại sang `customer`. Khi đó mỗi customer có tối đa một profile; muốn bắt buộc mọi customer phải có profile cần thêm cách bảo đảm riêng, không chỉ khóa ngoại ở phía profile.

**Nhiều-nhiều (N:M):** Ví dụ sinh viên tham gia nhiều khóa học và mỗi khóa học có nhiều sinh viên. Database quan hệ thường dùng bảng liên kết `enrollment(student_id, course_id, enrolled_at)` với hai khóa ngoại. Cặp `(student_id, course_id)` có thể làm khóa chính ghép để ngăn liên kết trùng. Không nên tưởng tượng rằng một cột SQL thông thường tự lưu được `List<Course>`.

**Tính toàn vẹn tham chiếu:** Không thể thêm một đơn hàng có `customer_id = 999` khi không có khách hàng 999, vì foreign key từ chối. Khi xóa khách hàng đang được tham chiếu, kết quả phụ thuộc chính sách `ON DELETE` (mặc định thường ngăn xóa; có thể cấu hình CASCADE/SET NULL theo thiết kế). Không tự suy ra cách xóa từ annotation Java.

## 5. Từ hàng SQL sang object Java

Cấu trúc tương ứng dễ nhớ nhưng chỉ mang tính quy ước:

| Database | Java | Cần chú ý |
| --- | --- | --- |
| Bảng `customer` | Class/record `Customer` | Không bắt buộc một bảng phải có đúng một class |
| Một hàng `customer` | Một instance `Customer` | Một object có thể kết hợp dữ liệu từ nhiều bảng |
| Cột `full_name` | Field/component `name` | Tên khác nhau, cần mapping rõ ràng |
| Khóa chính `customer_id` | Field `id` | ID database khác với địa chỉ bộ nhớ object |
| Khóa ngoại `customer_id` | Field `customerId` hoặc reference `customer` | Chọn theo mô hình và công nghệ truy cập |
| Nhiều hàng liên quan | `List<Order>`, `Set<Order>` | Cần query/join/ORM để lấy dữ liệu |
| SQL NULL | `null` hoặc mô hình tùy loại dữ liệu | Primitive `long`/`int` không chứa null |

Ví dụ Java 17+ cho **đối tượng đọc dữ liệu/DTO**:

~~~java
import java.time.LocalDateTime;

record Customer(long id, String name, String email) {}

record PurchaseOrder(
        long id,
        long customerId,
        LocalDateTime createdAt,
        String status
) {}
~~~

Đây là các kiểu dữ liệu Java hợp lệ; chúng chỉ mô tả đối tượng trong bộ nhớ, **không tự kết nối hoặc tạo bảng**. `Customer` dùng component `name` trong khi cột database tên `full_name`; lớp mapping phải quyết định hai tên này tương ứng. `PurchaseOrder.customerId` lưu khóa ngoại như số nguyên, nhưng chưa chứa object `Customer`; muốn có customer cần truy vấn rồi gắn kết quả hoặc dùng ORM.

**Java reference không phải foreign key:** Biến `Customer customer` chứa tham chiếu tới object trong bộ nhớ JVM. Cột `customer_id BIGINT` lưu một giá trị định danh. ORM có thể ánh xạ reference thành khóa ngoại, nhưng đó là hành vi của mapping/persistence layer, không phải bản chất của biến Java.

**Danh tính object và danh tính hàng:** `a == b` với hai reference Java kiểm tra cùng instance; `customer_id` kiểm tra cùng bản ghi logic trong database. Hai object Java khác instance có thể cùng mang ID 1. Việc định nghĩa `equals/hashCode` cho entity cần cân nhắc ID chưa được sinh, proxy và collection; không đồng nhất một cách máy móc.

### Kiểu SQL thường gặp và Java tương ứng

| SQL | Kiểu Java thường dùng | Lưu ý |
| --- | --- | --- |
| `INTEGER` | `int` / `Integer` | Dùng wrapper khi cột nullable |
| `BIGINT` | `long` / `Long` | `getLong()` trả 0 nếu SQL NULL; kiểm tra `wasNull()` nếu cần |
| `VARCHAR`, `TEXT` | `String` | SQL NULL vẫn có thể thành Java `null` |
| `DECIMAL(p,s)` | `BigDecimal` | Phù hợp tiền/số chính xác; tránh `double` nếu cần chính xác thập phân |
| `BOOLEAN` | `boolean` / `Boolean` | Tùy khả năng NULL và driver |
| `DATE` | `LocalDate` | Chỉ ngày, không có giờ |
| `TIMESTAMP` không có time zone | `LocalDateTime` | Không tự mang múi giờ; mapping tùy driver |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` hoặc ánh xạ được driver hỗ trợ | Ngữ nghĩa và khả năng truy xuất khác theo database/driver |

Đây là ánh xạ thông dụng, không phải cam kết mọi JDBC driver đều hỗ trợ mọi `ResultSet.getObject(column, Type.class)` hay cùng hành vi chuyển đổi. Khi làm việc với thời điểm, phải thống nhất kiểu cột, time zone và quy tắc hiển thị.

## 6. SQL trả về hàng kết quả, chưa phải đồ thị object

Với dữ liệu mẫu:

~~~sql
SELECT c.customer_id, c.full_name, o.order_id, o.status
FROM customer AS c
JOIN purchase_order AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 1
ORDER BY o.order_id;
~~~

Kết quả:

| customer_id | full_name | order_id | status |
| ---: | --- | ---: | --- |
| 1 | An | 100 | NEW |
| 1 | An | 101 | PAID |

**Hai hàng kết quả không có nghĩa là có hai khách hàng.** `JOIN` kết hợp các hàng khớp điều kiện, vì vậy dữ liệu phía `customer` lặp lại cho từng đơn hàng. Ứng dụng muốn hiển thị một object customer chứa danh sách đơn hàng phải **nhóm theo khóa** `customer_id`; không được tạo hai object customer rồi coi đó là hai thực thể nghiệp vụ khác nhau.

Đối với khách hàng chưa có đơn, `INNER JOIN` không sinh hàng. `LEFT JOIN` vẫn trả về customer và đặt cột phía order là NULL:

~~~sql
SELECT c.customer_id, c.full_name, o.order_id
FROM customer AS c
LEFT JOIN purchase_order AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 2;
~~~

Kết quả có một hàng `(2, 'Bình', NULL)`. Nếu mapping sang Java, trường `orderId` phải có khả năng biểu diễn NULL (ví dụ `Long`), hoặc mapper phải nhận ra không có đơn hàng. Khi join thêm `order_item`, một đơn có thể xuất hiện nhiều lần; nếu gom thành danh sách đơn, cần khử trùng theo `order_id` trước khi thêm item.

### Java 17+ chạy độc lập: gom các hàng JOIN thành object lồng nhau

Đây là mô phỏng các hàng `JOIN` đã được đọc từ database. Ví dụ dùng Java thuần để làm rõ bước **row → object graph**, không cần JDBC hay Spring. Lưu vào tệp `MappingDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record JoinedRow(long customerId, String customerName,
                 long orderId, String status) {}
record OrderView(long id, String status) {}
record CustomerOrders(long id, String name, List<OrderView> orders) {}

public class MappingDemo {
    public static void main(String[] args) {
        List<JoinedRow> rows = List.of(
                new JoinedRow(1, "An", 100, "NEW"),
                new JoinedRow(1, "An", 101, "PAID")
        );

        Map<Long, String> names = new LinkedHashMap<>();
        Map<Long, List<OrderView>> ordersByCustomer = new LinkedHashMap<>();

        for (JoinedRow row : rows) {
            names.putIfAbsent(row.customerId(), row.customerName());
            ordersByCustomer
                    .computeIfAbsent(row.customerId(), k -> new ArrayList<>())
                    .add(new OrderView(row.orderId(), row.status()));
        }

        for (Map.Entry<Long, String> entry : names.entrySet()) {
            long customerId = entry.getKey();
            CustomerOrders customer = new CustomerOrders(
                    customerId,
                    entry.getValue(),
                    List.copyOf(ordersByCustomer.get(customerId))
            );

            String ids = customer.orders().stream()
                    .map(order -> Long.toString(order.id()))
                    .collect(Collectors.joining(", "));
            System.out.println(
                    customer.name() + " có " + customer.orders().size()
                            + " đơn: " + ids
            );
        }
    }
}
~~~

Chạy:

~~~bash
javac MappingDemo.java
java MappingDemo
~~~

Stdout chính xác:

~~~text
An có 2 đơn: 100, 101
~~~

`LinkedHashMap` giữ thứ tự gặp dữ liệu trong ví dụ, `computeIfAbsent` tạo danh sách cho ID chưa có, `List.copyOf` tạo bản sao danh sách không cho sửa trực tiếp. Với query thật, cần xét thêm khách hàng không có đơn, bản ghi NULL, đơn bị lặp khi join nhiều bảng và chi phí bộ nhớ nếu kết quả rất lớn.

## 7. Spring JDBC: biến ResultSet thành object bằng RowMapper

Khi dùng JDBC, câu SQL tạo ra `ResultSet`. Con trỏ kết quả được duyệt theo hàng; mỗi hàng gồm các giá trị cột được đọc theo tên hoặc vị trí. Với Spring JDBC, `JdbcTemplate` đảm nhận phần lớn thao tác lấy kết nối, chuẩn bị/chạy lệnh và đóng tài nguyên; `RowMapper<T>` chuyển **một hàng kết quả** thành một object `T`.

Ví dụ sau dùng trong ứng dụng Spring đã cấu hình `DataSource` và dependency `spring-jdbc`. Lưu là `CustomerRepository.java` trong package tương ứng của dự án:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerRepository {
    public record CustomerDto(long id, String name, String email) {}

    private final JdbcTemplate jdbc;

    public CustomerRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<CustomerDto> findById(long customerId) {
        List<CustomerDto> rows = jdbc.query(
                """
                SELECT customer_id, full_name, email
                FROM customer
                WHERE customer_id = ?
                """,
                (rs, rowNum) -> new CustomerDto(
                        rs.getLong("customer_id"),
                        rs.getString("full_name"),
                        rs.getString("email")
                ),
                customerId
        );

        return rows.stream().findFirst();
    }
}
~~~

Cách đọc ví dụ:

1. `WHERE customer_id = ?` có **tham số ràng buộc**, Spring/JDBC truyền `customerId` như dữ liệu, thay vì nối trực tiếp nội dung từ người dùng vào SQL.
2. Khi truy vấn có kết quả, lambda `RowMapper` đọc từng cột và tạo một `CustomerDto`. `rowNum` là chỉ số hàng trong callback (bắt đầu từ 0), ở đây không cần sử dụng.
3. `jdbc.query(...)` trả `List<CustomerDto>`; `findFirst()` trả `Optional.empty()` nếu không tìm thấy. Khóa chính bảo đảm tối đa một hàng phù hợp trong trường hợp dữ liệu hợp lệ.
4. Vì các cột ví dụ đều `NOT NULL`, dùng `long` và `String` trực tiếp phù hợp. Nếu ID nullable, không nên đọc bằng `getLong` rồi mặc nhiên coi 0 là giá trị thật.

Để ghi, Spring JDBC có thể dùng `jdbc.update("INSERT INTO customer (...) VALUES (?, ?, ?)", id, name, email)`. Giá trị trả về cho biết số hàng bị tác động; vẫn cần xử lý ngoại lệ do unique/foreign key/check constraint. `RowMapper` xử lý ánh xạ từng hàng, không tự động ghép danh sách con hoặc thực hiện cascade.

Có thể dùng `BeanPropertyRowMapper` khi quy tắc đặt tên/kiểu dữ liệu phù hợp, nhưng mapping tường minh thường rõ ràng hơn với DTO quan trọng hoặc tên cột khác tên field. Không nên xem tên cột và tên thuộc tính Java là tự khớp trong mọi trường hợp.

## 8. ORM/JPA: ánh xạ bảng thành entity và quan hệ object

ORM (Object–Relational Mapping) cung cấp lớp ánh xạ giữa object Java và bảng SQL. Với JPA, một class gắn `@Entity` có thể biểu diễn thực thể bền vững; field gắn `@Id` tương ứng định danh, `@Column` tùy chỉnh tên cột, còn `@ManyToOne`/`@OneToMany` mô tả liên kết object.

Ví dụ các **đoạn khai báo minh họa** cho cùng quan hệ, dùng các annotation từ `jakarta.persistence`:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
class CustomerEntity {
    @Id
    @Column(name = "customer_id")
    Long id;

    @Column(name = "full_name", nullable = false)
    String fullName;

    protected CustomerEntity() {}
}

@Entity
@Table(name = "purchase_order")
class PurchaseOrderEntity {
    @Id
    @Column(name = "order_id")
    Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    CustomerEntity customer;

    protected PurchaseOrderEntity() {}
}
~~~

Đây là ví dụ mapping để đặt trong dự án có Jakarta Persistence provider và cấu hình entity scanning; nó không phải chương trình Java chạy độc lập. Cột `purchase_order.customer_id` vẫn là **foreign key SQL**; object `PurchaseOrderEntity.customer` là cách Java truy cập quan hệ đó. `@JoinColumn` nêu tên cột liên kết; database cần schema/ràng buộc tương ứng được quản lý bằng migration hoặc cơ chế tạo schema đã chủ ý cấu hình.

Các điểm quan trọng:

- **Entity không đồng nghĩa DTO.** Entity có vòng đời persistence context, trạng thái managed/detached, cơ chế đồng bộ thay đổi; DTO/record thường chỉ là dữ liệu trả về hoặc truyền giữa các lớp. Record Java thông thường phù hợp DTO; không coi record là JPA entity di động giữa provider.
- **`LAZY`** cho biết dự định tải quan hệ theo nhu cầu, nhưng thời điểm truy vấn cụ thể phụ thuộc provider và ngữ cảnh. Đọc quan hệ ngoài persistence context/transaction thích hợp có thể lỗi do dữ liệu chưa được tải.
- **N+1 query:** Lấy N đơn hàng rồi chạm `order.customer` cho từng đơn có thể làm phát sinh nhiều query bổ sung. Cân nhắc `JOIN FETCH`, entity graph, projection hoặc query phù hợp dựa trên nhu cầu thực tế.
- **Cascade và fetch là hai khái niệm khác nhau.** Fetch quyết định tải dữ liệu; cascade quyết định lan truyền thao tác persistence. Không bật xóa cascade vô điều kiện vì có thể xóa dữ liệu liên quan ngoài ý định.
- **Annotation không thay thế hiểu biết SQL.** Một field `List<PurchaseOrderEntity>` có thể cần nhiều hàng, khóa ngoại và query riêng; nó không trở thành một cột SQL dạng list chỉ vì xuất hiện trong class.

Nếu dùng Spring Data JDBC, chiến lược mapping và aggregate khác JPA; không mặc định áp dụng cùng lazy-loading/proxy/quan hệ entity. Dù thư viện nào được chọn, cần nhìn schema và SQL thực sự để hiểu dữ liệu được đọc/ghi ra sao.

## 9. Chọn dạng dữ liệu cho nhu cầu đọc/ghi

| Nhu cầu | Cách nghĩ phù hợp |
| --- | --- |
| Trang danh sách khách hàng | Chỉ query các cột cần hiển thị, trả `List<CustomerDto>` |
| Xem một khách hàng theo ID | `Optional<CustomerDto>` hoặc kết quả tương đương khi không có dữ liệu |
| Xem khách hàng kèm đơn | Join + gom hàng; hoặc nhiều query hợp lý; hoặc mapping ORM có kiểm soát |
| Tạo đơn và các dòng hàng | Ghi nhiều bảng trong cùng transaction, tuân thủ foreign key |
| Trả JSON cho API | Thường dùng DTO/projection để kiểm soát dữ liệu, tránh lộ toàn bộ entity hoặc vòng lặp quan hệ |

Việc chọn **một query join** hay **nhiều query** phụ thuộc kích thước dữ liệu, phân trang, tính chọn lọc, index và nhu cầu hiển thị. Join 1:N có thể nhân số hàng, khiến phân trang theo customer sai nếu áp dụng `LIMIT` trực tiếp lên tập hàng join. Với tập dữ liệu lớn, nên phân trang ID của thực thể cha trước rồi lấy children phù hợp, hoặc dùng chiến lược truy xuất có kiểm soát.

## 10. Đọc, ghi và tính nhất quán dữ liệu

Một luồng ứng dụng Spring thường là:

~~~text
HTTP / job / message
        |
        v
Service (nghiệp vụ, transaction)
        |
        v
Repository / JDBC / JPA
        |
        v
SQL query + database constraints
        |
        v
Rows / ResultSet -> DTO hoặc entity -> kết quả nghiệp vụ
~~~

Ví dụ tạo một `purchase_order` và hai `order_item`: cả ba lệnh ghi nên được xử lý như một đơn vị nghiệp vụ khi cần tính nguyên tử. Trong Spring, `@Transactional` trên service phù hợp có thể yêu cầu transaction manager commit toàn bộ nếu thành công hoặc rollback khi ngoại lệ phù hợp; cần cấu hình transaction manager và hiểu các quy tắc rollback, self-invocation và ranh giới transaction cụ thể. Foreign key ngăn item trỏ tới order không tồn tại, nhưng không thay thế transaction để tránh trạng thái ghi dở.

SQL xử lý dữ liệu theo tập hợp. Các thao tác như `UPDATE purchase_order SET status = 'PAID' WHERE order_id = ?` ảnh hưởng hàng thỏa điều kiện; số lượng hàng chịu tác động cần được kiểm tra khi nghiệp vụ yêu cầu đúng một hàng. Với cập nhật đồng thời, đọc rồi ghi không tự bảo đảm tránh mất cập nhật; có thể cần optimistic locking (version), khóa phù hợp hoặc isolation level tương ứng.

Ràng buộc database là lớp bảo vệ cuối cho dữ liệu chung; validation ở Java giúp báo lỗi dễ hiểu sớm hơn. Cả hai phục vụ các mục đích bổ sung cho nhau.

## 11. Lỗi phổ biến và cách tránh

1. **Nhầm hàng với object:** `JOIN` trả hai hàng cho khách hàng An nên tưởng có hai customer. Hãy nhóm bằng khóa định danh và hiểu cardinality của query.
2. **Giả định tên field = tên cột:** `full_name` không mặc nhiên bằng `name`. Dùng mapping tường minh hoặc một quy tắc đặt tên được cấu hình, kiểm thử.
3. **Đánh đồng foreign key với reference:** `customer_id` chỉ là giá trị; object `Customer` phải được nạp, ánh xạ và quản lý vòng đời nếu cần.
4. **Bỏ qua NULL:** Dùng primitive cho cột nullable, hoặc so sánh `= NULL`, dẫn đến kết quả sai. Kiểm tra schema và cách API JDBC xử lý NULL.
5. **Dùng floating-point cho tiền:** `double` có thể gây sai khác nhị phân; ưu tiên `DECIMAL` ở SQL và `BigDecimal` ở Java khi cần chính xác.
6. **Nối dữ liệu đầu vào vào câu SQL:** Dễ gây SQL injection và lỗi quoting. Dùng prepared statements/tham số hóa qua JDBC/JdbcTemplate.
7. **Không khai báo khóa/ràng buộc:** Dữ liệu trùng, order mồ côi, quantity âm có thể lọt vào database. Thiết kế PK, FK, UNIQUE, NOT NULL và CHECK thích hợp.
8. **Truy cập quan hệ ORM tùy tiện:** Gây N+1, lỗi lazy initialization hoặc tải quá nhiều bản ghi. Quan sát SQL thực thi và chọn query/projection theo trường hợp.
9. **Tưởng kết quả query có thứ tự mặc định:** Không có `ORDER BY` thì không nên dựa vào thứ tự trả về.
10. **Quên transaction khi ghi nhiều bảng:** Lỗi giữa chuỗi ghi có thể để lại dữ liệu không hoàn chỉnh nếu không có transaction đúng phạm vi.
11. **Trả thẳng entity qua API:** Có thể kéo theo tham chiếu vòng, dữ liệu nhạy cảm hoặc lazy loading khó kiểm soát. Dùng DTO cho hợp đồng API rõ ràng.
12. **Tin rằng mọi association đều đã được lưu:** Tạo object Java có `List<Order>` không đủ để tạo các hàng SQL; việc lưu phụ thuộc repository, mapping, cascade và transaction.

## 12. Tự kiểm tra

**Câu 1.** Bảng `customer` có 2 hàng, `purchase_order` có 2 hàng đều thuộc khách hàng 1. `INNER JOIN` theo `customer_id` có bao nhiêu hàng?  
**Đáp án:** 2 hàng. Khách hàng 2 không có đơn nên không xuất hiện; thông tin khách hàng 1 lặp hai lần.

**Câu 2.** Vì sao cột `purchase_order.customer_id` không tương đương `CustomerEntity customer`?  
**Đáp án:** Cột lưu giá trị khóa ngoại và được database kiểm tra; field Java là tham chiếu object trong bộ nhớ. Persistence layer cần mapping và tải/lưu phù hợp để kết nối hai phía.

**Câu 3.** Nếu cột `discount_amount DECIMAL(12,2)` cho phép NULL, nên cân nhắc kiểu Java nào?  
**Đáp án:** `BigDecimal` với khả năng `null` và quy tắc nghiệp vụ cụ thể; không dùng `double` chỉ vì dữ liệu là số thập phân.

**Câu 4.** Muốn tìm khách hàng chưa có đơn hàng, `INNER JOIN` có đủ không?  
**Đáp án:** Không. Có thể dùng `LEFT JOIN` và lọc `o.order_id IS NULL`, hoặc `NOT EXISTS` để xác định những khách hàng không có hàng liên quan.

**Câu 5.** Khi tạo order trước rồi tạo các item, cơ chế nào giúp tránh đơn hàng chỉ được lưu một phần nếu thao tác thứ hai lỗi?  
**Đáp án:** Một transaction bao trùm chuỗi thao tác, phối hợp với PK/FK/CHECK và xử lý lỗi đúng cách.

## 13. Ghi nhớ

**Bảng/cột/hàng là cấu trúc lưu trữ và truy vấn của database; class/field/object là cấu trúc dữ liệu và hành vi của Java.** Khóa chính xác định bản ghi, khóa ngoại liên kết các bản ghi, còn JDBC/Spring/JPA thực hiện phép chuyển đổi giữa hàng dữ liệu và object. Hiểu rõ cardinality, NULL, kiểu dữ liệu, truy vấn JOIN và transaction là nền tảng để đọc/ghi dữ liệu đúng trước khi đi sâu vào các cơ chế data access của Spring.
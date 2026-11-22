# Ánh xạ quan hệ một-nhiều từ kết quả JOIN trong Spring JDBC

## 1. Mục tiêu và vấn đề cần giải quyết

Trong cơ sở dữ liệu quan hệ, dữ liệu thường được chuẩn hóa thành nhiều bảng: **một đơn hàng có nhiều dòng hàng**, **một phòng ban có nhiều nhân viên**, **một bài viết có nhiều bình luận**. Khi dùng SQL `JOIN` để lấy cha và con cùng lúc, kết quả không còn là “một hàng SQL = một đối tượng cha”:

- Cha có 3 con thường xuất hiện trong **3 hàng kết quả**, với cột của cha được lặp lại.
- Cha **không có con** vẫn cần xuất hiện khi dùng `LEFT JOIN`, với các cột của con là SQL `NULL`.
- Nếu chỉ dùng `RowMapper<Parent>` và thêm từng kết quả vào `List<Parent>`, bạn có thể vô tình tạo nhiều bản sao của cùng một cha.
- Nếu dùng `queryForObject(...)` để lấy một cha có nhiều con, nhiều hàng JOIN có thể gây lỗi về số hàng dù bảng cha có khóa chính duy nhất.

Bài này hướng dẫn cách **gom nhóm (fold/aggregate)** nhiều hàng JOIN thành một cấu trúc Java kiểu `Parent { List<Child> children; }` bằng Spring JDBC, bảo toàn dữ liệu và tính thứ tự, xử lý NULL đúng cách, kiểm thử độc lập và tránh các lỗi hiệu năng.

Sau khi học, bạn có thể:

1. Tính số hàng của `INNER JOIN` và `LEFT JOIN` trên quan hệ một-nhiều.
2. Phân biệt `RowMapper` (một hàng → một object) với `ResultSetExtractor` (toàn `ResultSet` → một cấu trúc kết quả).
3. Dùng `LinkedHashMap<ParentId, Accumulator>` để chỉ tạo một cha, bổ sung đúng các con và tạo các DTO/record bất biến sau khi đọc.
4. Đọc khóa của con có thể là `NULL` đúng cách; cha không có con phải nhận danh sách rỗng.
5. Ngăn trùng con khi JOIN thêm quan hệ khác, nhận diện phép nhân hàng và tránh phân trang trực tiếp trên JOIN.
6. Viết ứng dụng Spring Boot + `JdbcTemplate` chạy được với Java 17+, SQL mẫu và JUnit test xác nhận quan hệ 1–N.

**Nguyên tắc xuyên suốt:** kết quả SQL JOIN là **tập hàng phẳng**; cấu trúc cha–con trong Java là **mô hình phân cấp**. Bạn cần một bước ánh xạ có ý thức giữa hai biểu diễn đó.

## 2. Ví dụ dữ liệu: một đơn hàng có nhiều dòng hàng

Giả sử có hai bảng:

```text
purchase_orders
+----+--------------+
| id | order_number |
+----+--------------+
| 10 | ORD-A        |
| 20 | ORD-B        |
| 30 | ORD-C        |
+----+--------------+

purchase_order_lines
+-----+----------+---------+------+----------+
| id  | order_id | line_no | sku  | quantity |
+-----+----------+---------+------+----------+
| 101 | 10       | 1       | BOOK | 2        |
| 102 | 10       | 2       | PEN  | 5        |
| 201 | 20       | 1       | PAD  | 1        |
+-----+----------+---------+------+----------+
```

Ràng buộc nghiệp vụ:

- `purchase_orders.id` định danh duy nhất từng đơn.
- `purchase_order_lines.id` định danh duy nhất từng dòng.
- `purchase_order_lines.order_id` là khóa ngoại tới đơn.
- Một đơn có **0..N dòng**; dòng hàng chỉ thuộc một đơn.
- `line_no` duy nhất trong phạm vi một đơn, xác định thứ tự hiển thị dòng hàng.

Khi lập trình Java, ta muốn kết quả:

```text
Order(10, ORD-A)
  - Line(101, BOOK, quantity=2)
  - Line(102, PEN, quantity=5)

Order(20, ORD-B)
  - Line(201, PAD, quantity=1)

Order(30, ORD-C)
  - [] (không có dòng hàng)
```

Đây là **3 đối tượng cha** với tổng **3 đối tượng con**. Nhưng `LEFT JOIN` sẽ trả **4 hàng**: 2 cho ORD-A, 1 cho ORD-B và 1 hàng có cột con NULL cho ORD-C.

### 2.1. Xem kết quả JOIN thực tế

```sql
SELECT
    o.id AS order_id,
    o.order_number,
    l.id AS line_id,
    l.line_no,
    l.sku AS line_sku,
    l.quantity AS line_quantity
FROM purchase_orders o
LEFT JOIN purchase_order_lines l ON l.order_id = o.id
ORDER BY o.id, l.line_no, l.id;
```

Kết quả logic với dữ liệu ở trên:

| order_id | order_number | line_id | line_no | line_sku | line_quantity |
| ---: | --- | ---: | ---: | --- | ---: |
| 10 | ORD-A | 101 | 1 | BOOK | 2 |
| 10 | ORD-A | 102 | 2 | PEN | 5 |
| 20 | ORD-B | 201 | 1 | PAD | 1 |
| 30 | ORD-C | NULL | NULL | NULL | NULL |

Có bốn hàng SQL vì một hàng cha được lặp theo số dòng con được nối. Hàng cuối là **cha hợp lệ không có con**; không được tạo đối tượng dòng hàng giả với `id = 0`, `sku = null` hoặc `quantity = 0`.

### 2.2. Quy tắc đếm hàng

Trong JOIN đúng một bảng con và không có bộ lọc thêm, mỗi cha có `n` con tạo ra:

- `INNER JOIN`: `n` hàng; cha có `n=0` biến mất.
- `LEFT JOIN`: `max(1, n)` hàng; cha có `n=0` vẫn xuất hiện một lần với cột con NULL.

Với ba đơn có lần lượt 2, 1, 0 con: `LEFT JOIN` tạo `2 + 1 + 1 = 4` hàng; `INNER JOIN` tạo `2 + 1 + 0 = 3` hàng, nhưng không bao gồm ORD-C.

Mục tiêu ánh xạ không phải là “mỗi hàng thành một Order”, mà là **mỗi khóa cha thành một Order duy nhất**, rồi đưa con tương ứng vào collection của Order đó.

## 3. Chọn đúng callback của Spring JDBC

### 3.1. RowMapper hoạt động trên từng hàng

Một `RowMapper<T>` ánh xạ hàng hiện tại trong `ResultSet` thành một đối tượng `T`. `JdbcTemplate` chịu trách nhiệm di chuyển con trỏ qua các hàng; `RowMapper.mapRow(rs, rowNum)` **không được tự gọi `rs.next()`**.

Ví dụ dưới đây là mapping một hàng phẳng, **chưa** nhóm cha–con:

```java
record FlatOrderLine(
        long orderId,
        String orderNumber,
        Long lineId,
        Integer lineNo,
        String sku,
        Integer quantity
) {}

RowMapper<FlatOrderLine> mapper = (rs, rowNum) ->
        new FlatOrderLine(
                rs.getLong("order_id"),
                rs.getString("order_number"),
                rs.getObject("line_id", Long.class),
                rs.getObject("line_no", Integer.class),
                rs.getString("line_sku"),
                rs.getObject("line_quantity", Integer.class)
        );
```

Đây là fragment Java trong code có import `org.springframework.jdbc.core.RowMapper` và `java.sql.ResultSet` khi cần; nó giả định truy vấn ở mục 2.1. Nếu gọi `jdbcTemplate.query(sql, mapper)`, bạn nhận **4 FlatOrderLine**, trong đó cha id=10 lặp hai lần và dòng thứ tư có `lineId == null`.

Điều đó **không sai** nếu yêu cầu thật là xuất các hàng phẳng. Nó **chưa đủ** để tạo mô hình `List<OrderWithLines>` với cha không trùng và collection con.

### 3.2. ResultSetExtractor xử lý toàn bộ tập kết quả

`ResultSetExtractor<T>` nhận toàn `ResultSet` của một lần query và tự duyệt các hàng để tạo kết quả `T`:

```java
ResultSetExtractor<List<OrderView>> extractor = rs -> {
    // Tự gọi rs.next(), gom các hàng theo ID cha,
    // rồi trả danh sách các cha kèm danh sách con.
};
```

Đây là fragment minh họa kiến trúc; `OrderView` và cách triển khai đầy đủ xuất hiện trong phần ứng dụng chạy được. Trong `ResultSetExtractor`, **bạn** duyệt `rs.next()`; `JdbcTemplate` vẫn sở hữu và đóng `ResultSet`/`Statement`/connection theo đường gọi thông thường và chuyển `SQLException` thành ngoại lệ truy cập dữ liệu thích hợp.

| Công cụ Spring JDBC | Phạm vi xử lý | Phù hợp với |
| --- | --- | --- |
| `RowMapper<T>` | Một hàng tại một thời điểm, JDBC template điều khiển con trỏ | `List<T>` phẳng, một object cho mỗi hàng |
| `ResultSetExtractor<T>` | Toàn bộ tập hàng, extractor điều khiển con trỏ | Một aggregate, grouping 1–N, cấu trúc phân cấp |
| `RowCallbackHandler` | Callback được gọi cho từng hàng; template điều khiển con trỏ | Xử lý tuần tự/side effect có kiểm soát, có thể gom vào state bên ngoài callback |
| `queryForObject(...)` | Đòi đúng một **hàng kết quả** | Truy vấn theo ID không tạo nhiều hàng JOIN, scalar/row object |
| `queryForList(...)` | Tập kết quả phẳng | Danh sách scalar/map theo cấu trúc từng hàng |

Không nhầm `queryForObject` với “lấy đúng một cha”: nếu đơn id=10 có hai dòng, JOIN cho hai hàng; truy vấn trả một đơn theo **nghĩa nghiệp vụ** nhưng có **hai hàng SQL**, nên `queryForObject` không phù hợp để gom quan hệ 1–N.

### 3.3. Vì sao cần map theo khóa định danh?

Sai:

```text
for each JOIN row:
    result.add(new Order(row.orderId, row.number, [row.child]))
```

Với ORD-A sẽ tạo hai `Order` độc lập, không phải một đơn có hai dòng. Đúng:

```text
map = LinkedHashMap<OrderId, MutableOrder>

for each JOIN row:
    id = row.order_id
    if id not in map:
        map[id] = new MutableOrder(id, row.order_number)

    if row.line_id is not NULL:
        map[id].lines.add(mappedLine)

return map.values().map(MutableOrder::toImmutableView)
```

`LinkedHashMap` có hai lợi ích: tra cứu cha trung bình O(1) theo khóa và giữ **thứ tự lần xuất hiện đầu tiên** của cha theo `ORDER BY`. Với một số lượng vừa phải các đơn, độ phức tạp gom nhóm là xấp xỉ O(R), với `R` là số hàng SQL; bộ nhớ cho kết quả là O(P+C), với `P` số cha và `C` số con.

Việc gom theo **id** quan trọng hơn gom theo tên hoặc vị trí: hai đơn có cùng mô tả vẫn là hai đơn khác nhau; tên đơn/khách có thể thay đổi, còn khóa chính dùng để nhận diện bản ghi.

## 4. Những điều kiện để ánh xạ 1–N đúng

Trước khi viết mapper, xác định đầy đủ:

1. **Khóa cha:** cột `order_id` không NULL, duy nhất trong bảng cha. Mỗi khóa cha chỉ tạo một đối tượng cha trong map.
2. **Khóa con:** cột `line_id` là dấu hiệu tồn tại của con. `LEFT JOIN` sẽ cho `NULL` khi cha không có con.
3. **Cột và bí danh:** dùng `AS order_id` và `AS line_id` để tránh nhiều bảng có cột tên `id` hoặc `name`, làm `rs.getLong("id")` mơ hồ.
4. **Thứ tự:** có `ORDER BY o.id, l.line_no, l.id` để giữ thứ tự cha và con rõ ràng; không dựa vào thứ tự vật lý trên đĩa.
5. **Bất biến của con:** `id`, `order_id`, `line_no` bắt buộc và FK/UNIQUE được xác thực bằng DB; nếu join bổ sung tạo trùng hàng, phải xử lý khác.
6. **Dữ liệu cha không thay đổi giữa các hàng JOIN:** các cột cha trong một câu SELECT thống nhất từ cùng hàng gốc; nếu tự ghép dữ liệu từ nhiều nguồn khác nhau, phải có chính sách hợp nhất riêng.
7. **Kiểu dữ liệu:** dùng getter tương ứng `BIGINT`, `INTEGER`, `VARCHAR`; kiểm tra `NULL` ở cột có thể NULL.
8. **Ranh giới dữ liệu:** repository ánh xạ trước khi trả về; không đưa `ResultSet` còn mở lên controller/service.

Đặc biệt, `ResultSet.getLong("line_id")` trả `0` khi SQL NULL; muốn biết đó có phải NULL thật hay không phải gọi `rs.wasNull()` ngay sau getter. Một cách dễ đọc là `rs.getObject("line_id", Long.class)` với driver JDBC hỗ trợ, để nhận `Long null` khi không có dòng con. Ví dụ chạy được dưới đây dùng cách thứ hai.

## 5. Ứng dụng Spring Boot/JDBC chạy được với Java 17+

Ví dụ tự chứa sử dụng **Spring Boot 3.3.x, Spring JDBC và H2 in-memory** để chạy mà không phải cài PostgreSQL. SQL trong ví dụ là SQL quan hệ thông dụng, trọng tâm ở mapping. Trong production bạn có thể dùng PostgreSQL/MySQL/SQL Server theo dialect thực tế; thuật toán gom cha–con vẫn tương tự.

Cấu trúc thư mục:

```text
one-to-many-join-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/joinmapping/
    │   │   ├── JoinMappingApplication.java
    │   │   ├── OrderView.java
    │   │   └── OrderJdbcRepository.java
    │   └── resources/
    │       ├── application.yml
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/demo/joinmapping/
        └── OrderJdbcRepositoryTest.java
```

### 5.1. Gradle và dependency

`settings.gradle`:

```groovy
rootProject.name = 'one-to-many-join-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot starter JDBC cung cấp `JdbcTemplate`, hỗ trợ `DataSource` và connection pool; H2 được dùng trong ví dụ. `spring-boot-starter-test` gồm JUnit/AssertJ và công cụ test Spring. Các phiên bản plugin ở đây là một bộ cụ thể của Spring Boot 3.3, Java 17; nếu tích hợp vào repo hiện có, giữ version management chuẩn của repo thay vì tạo thêm nguồn version xung đột.

### 5.2. Schema có PK, FK và UNIQUE đúng quan hệ

Tệp `src/main/resources/schema.sql`:

```sql
CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(30) NOT NULL UNIQUE
);

CREATE TABLE purchase_order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(60) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_purchase_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id),
    CONSTRAINT uq_purchase_lines_position
        UNIQUE (order_id, line_no),
    CONSTRAINT ck_purchase_lines_quantity
        CHECK (quantity > 0)
);
```

Ràng buộc khóa ngoại làm rõ một dòng hàng phải thuộc một đơn hợp lệ. `UNIQUE(order_id, line_no)` ngăn hai dòng có cùng vị trí trong một đơn; không ngăn hai đơn khác nhau đều có dòng số 1. Khóa chính riêng cho cha và con giúp gom và nhận diện chính xác.

Tệp `src/main/resources/data.sql`:

```sql
INSERT INTO purchase_orders (id, order_number)
VALUES
    (10, 'ORD-A'),
    (20, 'ORD-B'),
    (30, 'ORD-C');

INSERT INTO purchase_order_lines
    (id, order_id, line_no, sku, quantity)
VALUES
    (101, 10, 1, 'BOOK', 2),
    (102, 10, 2, 'PEN', 5),
    (201, 20, 1, 'PAD', 1);
```

Dữ liệu có chủ đích gồm đơn có hai dòng, một dòng và không có dòng, để test cả ba trường hợp. Các tệp `schema.sql`/`data.sql` là fixture học tập; trên production nên quản lý thay đổi schema bằng migration phù hợp, không để seed mẫu chạy vào dữ liệu thật.

### 5.3. Cấu hình H2

Tệp `src/main/resources/application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:join_mapping;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always
```

Spring Boot tạo datasource in-memory, rồi chạy `schema.sql` và `data.sql` trong lúc khởi tạo. `DB_CLOSE_DELAY=-1` giữ database H2 in-memory tồn tại trong thời gian JVM chạy dù các connection tạm đóng; khi kết thúc JVM, dữ liệu mất. Ví dụ không yêu cầu frontend, HTTP server hoặc một DB external.

### 5.4. Domain/read model dạng record

Tệp `src/main/java/demo/joinmapping/OrderView.java`:

```java
package demo.joinmapping;

import java.util.List;

public record OrderView(
        long id,
        String orderNumber,
        List<OrderLine> lines
) {
    public OrderView {
        lines = List.copyOf(lines);
    }

    public record OrderLine(
            long id,
            int lineNumber,
            String sku,
            int quantity
    ) {}
}
```

`OrderView` là một mô hình đọc (read model) biểu diễn cha và collection con. `List.copyOf(lines)` tạo bản sao không thể sửa từ bên ngoài: repository có thể dùng `ArrayList` trong lúc gom, nhưng caller không thể vô tình thêm/xóa dòng của object đã trả về.

`OrderLine` là record lồng trong `OrderView`; truy cập bằng `OrderView.OrderLine`. Việc record bất biến không tự biến dữ liệu quan hệ thành aggregate nhất quán nghiệp vụ: đây là cấu trúc đọc, còn việc ghi/cập nhật nhiều bảng cần transaction và constraint phù hợp.

### 5.5. Repository: ResultSetExtractor gom toàn bộ JOIN

Tệp `src/main/java/demo/joinmapping/OrderJdbcRepository.java`:

```java
package demo.joinmapping;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcRepository {

    private static final String JOIN_SELECT = """
            SELECT
                o.id AS order_id,
                o.order_number AS order_number,
                l.id AS line_id,
                l.line_no AS line_no,
                l.sku AS line_sku,
                l.quantity AS line_quantity
            FROM purchase_orders o
            LEFT JOIN purchase_order_lines l
                   ON l.order_id = o.id
            """;

    private static final String ORDERING = """
            ORDER BY o.id, l.line_no, l.id
            """;

    private static final ResultSetExtractor<List<OrderView>> EXTRACTOR =
            rs -> {
                LinkedHashMap<Long, Accumulator> orders =
                        new LinkedHashMap<>();

                while (rs.next()) {
                    long orderId = rs.getLong("order_id");

                    Accumulator order = orders.get(orderId);
                    if (order == null) {
                        order = new Accumulator(
                                orderId,
                                rs.getString("order_number")
                        );
                        orders.put(orderId, order);
                    }

                    Long lineId = rs.getObject("line_id", Long.class);
                    if (lineId != null) {
                        order.lines.add(new OrderView.OrderLine(
                                lineId,
                                rs.getInt("line_no"),
                                rs.getString("line_sku"),
                                rs.getInt("line_quantity")
                        ));
                    }
                }

                return orders.values().stream()
                        .map(Accumulator::toView)
                        .toList();
            };

    private final JdbcTemplate jdbc;

    public OrderJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderView> findAllWithLines() {
        return jdbc.query(JOIN_SELECT + ORDERING, EXTRACTOR);
    }

    public Optional<OrderView> findByIdWithLines(long id) {
        List<OrderView> orders = jdbc.query(
                JOIN_SELECT + " WHERE o.id = ? " + ORDERING,
                EXTRACTOR,
                id
        );
        return orders.stream().findFirst();
    }

    private static final class Accumulator {
        final long id;
        final String orderNumber;
        final List<OrderView.OrderLine> lines = new ArrayList<>();

        Accumulator(long id, String orderNumber) {
            this.id = id;
            this.orderNumber = orderNumber;
        }

        OrderView toView() {
            return new OrderView(id, orderNumber, lines);
        }
    }
}
```

**Phân tích từng bước:**

1. `JOIN_SELECT` khai báo cột cụ thể, với alias `order_id` và `line_id` để tránh mơ hồ. Không dùng `SELECT *`.
2. `LEFT JOIN` giữ đơn ORD-C ngay cả khi không có dòng hàng; `INNER JOIN` sẽ loại đơn này.
3. `ORDER BY o.id, l.line_no, l.id` cho thứ tự xác định. `l.id` làm tie-breaker; dữ liệu mẫu đã có uniqueness của `line_no` trong từng đơn.
4. `EXTRACTOR` được giữ ở biến `static final` nhưng **không giữ trạng thái kết quả giữa các lần gọi**. `LinkedHashMap` được tạo **bên trong lambda mỗi lần thực thi query**, nên các lần gọi độc lập không trộn kết quả.
5. Mỗi hàng đi qua `rs.next()` lấy `order_id` và tra map. Chỉ khi gặp một ID cha lần đầu, code tạo `Accumulator`.
6. `rs.getObject("line_id", Long.class)` trả `null` cho SQL NULL do `LEFT JOIN`. Chỉ khi `lineId != null` mới thêm `OrderLine`.
7. Sau khi đọc hết ResultSet, mỗi accumulator được chuyển sang `OrderView` mới với list bất biến. Chỉ một đối tượng cha được trả cho mỗi ID.
8. `findByIdWithLines` lọc theo **khóa chính cha** bằng tham số `?` và dùng cùng extractor. Có thể nhận 0, 1 hoặc nhiều hàng SQL cho cùng cha; kết quả vẫn là `Optional<OrderView>` cho 0 hoặc 1 cha.

Điều kiện ngầm của đoạn này: **mỗi dòng con chỉ xuất hiện một lần trong JOIN**. Với JOIN từ đơn sang **một bảng** dòng hàng như ví dụ, điều này đúng vì `l.id` là khóa chính. Nếu nối thêm nhiều collection khác, có thể xuất hiện cùng con nhiều lần; mục 8 sẽ giải thích cách xử lý.

### 5.6. Entry point và output dự kiến

Tệp `src/main/java/demo/joinmapping/JoinMappingApplication.java`:

```java
package demo.joinmapping;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JoinMappingApplication {

    public static void main(String[] args) {
        SpringApplication.run(JoinMappingApplication.class, args);
    }

    @Bean
    CommandLineRunner showOrders(OrderJdbcRepository repository) {
        return args -> {
            var orders = repository.findAllWithLines();

            System.out.println("orders=" + orders.size());

            for (var order : orders) {
                var skus = order.lines().stream()
                        .map(OrderView.OrderLine::sku)
                        .toList();

                System.out.println(
                        order.orderNumber() + " -> " + skus
                );
            }

            System.out.println(
                    "found(999)="
                    + repository.findByIdWithLines(999L).isPresent()
            );
        };
    }
}
```

Với **Gradle wrapper đã có** trong project hoặc Gradle đã cài, chạy:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu bạn tạo dự án thủ công từ các tệp trên nhưng chưa có Gradle wrapper, tạo wrapper bằng Gradle đã cài hoặc chạy `gradle bootRun`. Tên class ứng dụng và package phải khớp đúng tệp như trong ví dụ. Java 17 đủ chạy `record`, text block và `Stream.toList()`.

Sau các log khởi động Spring Boot, năm dòng do `CommandLineRunner` in ra là:

```text
orders=3
ORD-A -> [BOOK, PEN]
ORD-B -> [PAD]
ORD-C -> []
found(999)=false
```

Dòng `ORD-C -> []` chứng minh cha không con vẫn có mặt. `orders=3` chứng minh không vô tình tạo bốn object cha từ bốn hàng JOIN. Dòng `found(999)=false` chứng minh truy vấn theo khóa chính không tìm thấy trả `Optional.empty()`, không tạo đối tượng giả.

## 6. So sánh hai cách ánh xạ: flatten rồi group hay extract trực tiếp

### 6.1. Cách 1: RowMapper tạo FlatRow, rồi Java group

Bước đầu: một row thành một record phẳng như `FlatOrderLine` ở mục 3.1. Sau đó:

```java
List<FlatOrderLine> rows = jdbcTemplate.query(sql, flatMapper);

LinkedHashMap<Long, List<FlatOrderLine>> grouped =
        new LinkedHashMap<>();

for (FlatOrderLine row : rows) {
    grouped.computeIfAbsent(
            row.orderId(),
            ignored -> new ArrayList<>()
    ).add(row);
}
```

Đây là fragment cần biến `sql` và `flatMapper` đã khai báo; trong project thực tế phải import `java.util.ArrayList`, `java.util.LinkedHashMap` và `java.util.List`. Kết quả là map chứa các **hàng phẳng** theo cha, chưa phải DTO cuối cùng. Cần bước tiếp theo để tạo Order, bỏ row có `lineId == null` và không lặp các trường cha.

Ưu điểm: dễ kiểm thử `RowMapper` một hàng và dễ tái sử dụng flat projections. Nhược điểm: giữ đồng thời một `List<FlatRow>` và cấu trúc gom, tăng phân bổ bộ nhớ khi kết quả lớn. Không phải cách sai; phù hợp khi code cần flat data độc lập.

### 6.2. Cách 2: ResultSetExtractor vừa duyệt vừa gom

`ResultSetExtractor` ở mục 5.5 làm grouping ngay trong lúc Spring trả `ResultSet`, không cần xây danh sách trung gian. Có thể trả DTO cuối cùng ngay khi query kết thúc. Với nhu cầu cha–con rõ ràng, đây là cách trực tiếp và giảm phần dữ liệu trung gian.

Tuy nhiên extractor vẫn phải giữ danh sách cha/con cuối cùng trong bộ nhớ cho đến khi trả kết quả; nó **không biến toàn bộ kết quả thành stream không giới hạn**. Khi số hàng rất lớn, cần cân nhắc phân trang, tải theo batch, hạn chế trường hoặc xử lý streaming thật sự.

### 6.3. Khi nào dùng RowCallbackHandler?

`RowCallbackHandler` được Spring gọi cho từng hàng; bạn có thể cộng dồn vào một `LinkedHashMap` nằm ngoài callback. Nhưng callback không có giá trị trả về trực tiếp, nên repository phải quản lý state của một lần query rồi chuyển thành kết quả sau khi gọi `jdbc.query(...)`. Đối với “toàn bộ result set → một cấu trúc object”, `ResultSetExtractor` thường rõ ý định hơn.

Một `RowCallbackHandler.processRow(rs)` **không** tự gọi `rs.next()`; template đã di chuyển con trỏ. Nếu đổi từ `ResultSetExtractor` sang `RowCallbackHandler` mà giữ vòng `while (rs.next())` trong callback, bạn có thể bỏ qua hàng và gây lỗi khó tìm.

## 7. LEFT JOIN và SQL NULL: những bẫy dữ liệu

### 7.1. Phải kiểm tra ID con, không kiểm tra thuộc tính tùy chọn

Nếu con có các trường nullable (ví dụ `description` hoặc `discount_code`), không dùng trường đó để quyết định “có con hay không”:

```java
// Sai nếu sku/description có thể NULL:
if (rs.getString("description") != null) {
    // add child
}

// Đúng khi line.id là PK NOT NULL:
Long lineId = rs.getObject("line_id", Long.class);
if (lineId != null) {
    // add child
}
```

Một child hợp lệ có thể có mô tả NULL. Dùng khóa chính con `NOT NULL` để xác định sự tồn tại. Với khóa ghép, cần xác định cột khóa phù hợp và ngữ nghĩa NULL của JOIN.

### 7.2. getLong/getInt với NULL phải dùng wasNull

Với `rs.getLong("line_id")` và dữ liệu SQL NULL, JDBC thường trả `0L`; `rs.wasNull()` mới biết giá trị thật là NULL:

```java
long lineId = rs.getLong("line_id");
if (!rs.wasNull()) {
    // Đây mới thực sự là một dòng con.
}
```

`wasNull()` phản ánh giá trị getter **vừa đọc gần nhất**. Nếu gọi thêm getter khác trước `wasNull()`, việc kiểm tra có thể sai. Dùng `rs.getObject("line_id", Long.class)` sẽ rõ ràng hơn khi driver hỗ trợ. Đừng tạo `Line(0,...)` cho ORD-C.

### 7.3. Đặt điều kiện ở ON hay WHERE?

Hai truy vấn sau **khác ngữ nghĩa** khi có cha không có dòng con phù hợp:

```sql
-- Giữ mọi đơn; chỉ nối các dòng có quantity >= 2.
SELECT o.id, l.id
FROM purchase_orders o
LEFT JOIN purchase_order_lines l
  ON l.order_id = o.id AND l.quantity >= 2;

-- Điều kiện WHERE loại các hàng có l.quantity NULL.
SELECT o.id, l.id
FROM purchase_orders o
LEFT JOIN purchase_order_lines l
  ON l.order_id = o.id
WHERE l.quantity >= 2;
```

Ở truy vấn đầu, cha không có dòng đạt ngưỡng vẫn có một hàng với `l.id = NULL`. Ở truy vấn sau, hàng con NULL không thỏa `WHERE l.quantity >= 2` và cha biến mất khỏi kết quả. Với bài toán “hiển thị tất cả đơn và những dòng thỏa bộ lọc”, đặt predicate bên con ở `ON` (hoặc thiết kế bộ lọc/subquery tương đương).

Nếu yêu cầu ngược lại là “chỉ trả đơn có ít nhất một dòng đủ điều kiện”, dùng `WHERE`/`EXISTS` theo ý nghĩa đó; đừng chọn `LEFT JOIN` chỉ theo thói quen.

### 7.4. COUNT(*) trên LEFT JOIN có thể đánh lừa

```sql
SELECT
    o.id,
    COUNT(*) AS joined_rows,
    COUNT(l.id) AS actual_lines
FROM purchase_orders o
LEFT JOIN purchase_order_lines l ON l.order_id = o.id
GROUP BY o.id
ORDER BY o.id;
```

Với ORD-C không có dòng: `joined_rows = 1` nhưng `actual_lines = 0`. `COUNT(*)` đếm cả hàng “placeholder” do `LEFT JOIN`; `COUNT(l.id)` bỏ qua NULL và cho đúng số dòng con nếu mỗi con chỉ xuất hiện một lần. Nếu JOIN thêm bảng làm trùng con, cân nhắc `COUNT(DISTINCT l.id)` hoặc đếm riêng bằng subquery.

## 8. Nối thêm nhiều quan hệ: phép nhân hàng và khử trùng theo khóa

Giả sử một đơn có **2 dòng hàng** và **3 ghi chú**, rồi join cả hai tập con:

```sql
SELECT o.id, l.id AS line_id, n.id AS note_id
FROM purchase_orders o
LEFT JOIN purchase_order_lines l ON l.order_id = o.id
LEFT JOIN order_notes n ON n.order_id = o.id
WHERE o.id = 10;
```

`order_notes` là bảng giả định có khóa chính `id` và FK `order_id` tới bảng đơn. Kết quả có thể gồm **2 × 3 = 6 hàng**, vì mỗi dòng hàng được ghép với mỗi ghi chú. Nếu cứ `order.lines.add(...)` cho mỗi hàng, hai dòng sẽ được thêm ba lần mỗi dòng. Đây là **cartesian multiplication** của các collection độc lập, không phải sáu dòng hàng thật.

### 8.1. Dedupe bằng child ID trong accumulator

Trong một phép JOIN đa collection mà cần gom, có thể lưu con theo ID:

```java
// Đoạn minh họa bên trong một accumulator.
LinkedHashMap<Long, OrderView.OrderLine> uniqueLines =
        new LinkedHashMap<>();

Long lineId = rs.getObject("line_id", Long.class);
if (lineId != null) {
    uniqueLines.putIfAbsent(
            lineId,
            new OrderView.OrderLine(
                    lineId,
                    rs.getInt("line_no"),
                    rs.getString("line_sku"),
                    rs.getInt("line_quantity")
            )
    );
}

// Sau khi duyệt hết:
List<OrderView.OrderLine> lines =
        List.copyOf(uniqueLines.values());
```

Ở đây `rs` là `ResultSet` trong extractor, các import `Map`/`List` tương ứng. `putIfAbsent` chỉ có ý nghĩa khi ID con thực sự định danh một con duy nhất và mọi hàng lặp là cùng một con. Nếu dữ liệu chứa hai bản ghi con khác nhau nhưng cùng mô tả, không được gộp chúng bằng tên hoặc `line_no` thiếu ngữ cảnh cha.

### 8.2. Khử trùng không xóa được chi phí JOIN

Dedupe bằng ID giúp object tree không bị lặp, nhưng DB vẫn có thể trả `N × M` hàng. Điều này tăng truyền dữ liệu, CPU JDBC và bộ nhớ. Với hai hoặc nhiều collection lớn, thường nên cân nhắc:

- Query cha trước, sau đó query **tất cả dòng hàng của các cha đã chọn trong một lần** bằng `WHERE order_id IN (...)`; gom trong Java.
- Query các collection độc lập theo batch thay vì JOIN tất cả cùng lúc.
- Dùng SQL aggregation/JSON aggregation riêng của DBMS khi phù hợp, sau đó kiểm tra cách map, thứ tự, NULL và kích thước payload.
- Trả projection DTO vừa đủ cho màn hình, thay vì “tải mọi quan hệ” mặc định.

Dedupe trong Java không thay cho UNIQUE/FK trong DB và không giải quyết dữ liệu trùng thật sự.

## 9. Phân trang đúng với dữ liệu một-nhiều

### 9.1. Vì sao LIMIT/OFFSET trực tiếp trên JOIN thường sai?

Ví dụ:

```sql
SELECT o.id AS order_id, l.id AS line_id
FROM purchase_orders o
LEFT JOIN purchase_order_lines l ON l.order_id = o.id
ORDER BY o.id, l.line_no
LIMIT 1;
```

Dữ liệu mẫu có ORD-A gồm hai dòng. `LIMIT 1` chỉ giữ **một hàng JOIN** đầu tiên, tức ORD-A với BOOK; khi gom lại, bạn nhận ORD-A nhưng thiếu PEN. Đây là lỗi dữ liệu **partial child collection**. `LIMIT 2` có thể chỉ trả ORD-A đầy đủ nhưng không trả hai đơn dù màn hình yêu cầu “2 đơn”.

Nói cách khác, `LIMIT/OFFSET` trong SQL hoạt động trên **hàng kết quả sau JOIN**, không hiểu khái niệm một Order aggregate trong Java. Phân trang của Spring/JDBC không tự sửa điều này.

### 9.2. Chiến lược hai bước: chọn ID cha rồi tải children theo batch

Bước 1, phân trang **cha** theo thứ tự ổn định:

```sql
SELECT o.id
FROM purchase_orders o
ORDER BY o.id
LIMIT ? OFFSET ?;
```

Bước 2, lấy đầy đủ dòng của **những cha trong trang**, chẳng hạn với danh sách ID `[10, 20]`:

```sql
SELECT
    o.id AS order_id,
    o.order_number,
    l.id AS line_id,
    l.line_no,
    l.sku AS line_sku,
    l.quantity AS line_quantity
FROM purchase_orders o
LEFT JOIN purchase_order_lines l ON l.order_id = o.id
WHERE o.id IN (10, 20)
ORDER BY o.id, l.line_no, l.id;
```

Truy vấn 2 phải bind các ID bằng tham số (ví dụ `NamedParameterJdbcTemplate` với `IN (:ids)`), không ghép input thô của người dùng vào chuỗi SQL. Trong ví dụ này, trang hai cha ORD-A và ORD-B sẽ đầy đủ 2+1 con, tổng 3 hàng JOIN.

Một triển khai khái niệm bằng Spring JDBC:

```java
List<Long> ids = jdbc.query(
        """
        SELECT id FROM purchase_orders
        ORDER BY id
        LIMIT ? OFFSET ?
        """,
        (rs, rowNum) -> rs.getLong(1),
        pageSize,
        offset
);

if (ids.isEmpty()) {
    return List.of();
}

return namedJdbc.query(
        JOIN_SELECT
            + " WHERE o.id IN (:ids) "
            + ORDERING,
        new MapSqlParameterSource("ids", ids),
        EXTRACTOR
);
```

Đây là **fragment trong repository** có sẵn `jdbc`, `namedJdbc` (`NamedParameterJdbcTemplate`), `JOIN_SELECT`, `ORDERING`, `EXTRACTOR` và import `MapSqlParameterSource`; không phải một phương thức Java hoàn chỉnh riêng. Đầu vào `pageSize` cần giới hạn hợp lý, `offset` không âm. `IN (:ids)` cần danh sách không rỗng; vì vậy kiểm tra `ids.isEmpty()` trước khi gửi.

**Chú ý đồng thời:** hai câu SQL tách biệt có thể thấy hai snapshot khác nhau khi request khác cập nhật dữ liệu; transaction `readOnly` với isolation mặc định không nhất thiết tạo snapshot ổn định qua hai câu, tùy DBMS. Nếu yêu cầu trang phải nhất quán tuyệt đối, xem xét isolation/snapshot, keyset pagination hoặc mô hình đọc phù hợp. Không kéo transaction đọc qua xử lý network dài chỉ để giữ snapshot.

### 9.3. Tránh N+1 khi tải children

Cách kém:

```text
SELECT * FROM purchase_orders ... LIMIT 20
for each order:
    SELECT * FROM purchase_order_lines WHERE order_id = ?
```

Tức một query cha + 20 query con, gây vấn đề **N+1 queries**. Giải pháp batch `WHERE order_id IN (...)` thường dùng hai câu SQL tổng cộng cho một trang, giảm round trip mà vẫn giữ collection đầy đủ.

Đặt index trên `purchase_order_lines(order_id, line_no)` nếu truy vấn hay lấy dòng theo đơn và cần sắp xếp dòng. `UNIQUE(order_id, line_no)` trong schema mẫu thường đã tạo index phù hợp tại nhiều DBMS; xác minh bằng execution plan của DB thực tế, đừng tạo index trùng lặp không cần thiết.

## 10. Bất biến, thứ tự và mức độ tin cậy của dữ liệu

### 10.1. Parent identity phải ổn định

Trong `LinkedHashMap<Long, Accumulator>`, khóa là ID cha. Nếu mô hình cần tenant isolation, có thể phải dùng khóa ghép `(tenantId, orderId)` hoặc bảo đảm `orderId` thực sự global unique và query đã lọc tenant. Không dùng `orderNumber` nếu nó chỉ unique trong tenant; không dùng tên hiển thị làm identity.

### 10.2. Child identity phải ổn định

Khi chỉ join một bảng con và PK con unique, mỗi hàng của con xuất hiện một lần; thêm con vào `List` là đủ. Với join nhiều bảng, dùng `Map<ChildId, Child>` trong từng cha để dedupe. **Không** dedupe bằng `equals` nếu equality không phản ánh đúng PK; hai dòng hàng cùng SKU vẫn có thể là hai bản ghi khác nhau.

### 10.3. ORDER BY quyết định thứ tự trong list

Không có `ORDER BY`, SQL không bảo đảm thứ tự hàng. `LinkedHashMap` chỉ giữ thứ tự **bắt gặp**, nên nếu dữ liệu đầu vào thay đổi thứ tự, thứ tự cha và con cũng thay đổi. Trong màn hình cần sắp xếp, chọn order keys rõ ràng: `ORDER BY o.created_at DESC, o.id DESC, l.line_no, l.id`; nếu backend không hỗ trợ expression đó, điều chỉnh theo DBMS.

Một thuật toán tối ưu bộ nhớ đôi khi chỉ giữ **cha hiện tại** rồi chuyển sang cha tiếp theo khi `order_id` đổi. Cách này cần JOIN rows được sắp theo cha liên tục; nếu thiếu `ORDER BY` và rows của cùng cha xen kẽ, bạn có thể tạo nhiều cha. Dùng map thường an toàn và dễ hiểu hơn khi số bản ghi vừa phải.

### 10.4. Không trộn quy tắc dữ liệu và ánh xạ

ResultSetExtractor chỉ chuyển kết quả DB sang Java, không nên âm thầm sửa dữ liệu sai như một con tham chiếu sai cha, dòng có quantity âm hay bản ghi bị trùng thực. Dùng PK, FK, UNIQUE và CHECK trong DB để bảo vệ bất biến, dùng transaction khi ghi aggregate. Mapper nên fail rõ khi gặp schema không mong đợi thay vì tự điền dữ liệu giả.

### 10.5. Lưu ý về null và optional

`Optional<OrderView>` biểu diễn “có đơn / không có đơn” khi tìm theo ID. Một đơn **có nhưng không có dòng** nên là `Optional.of(new OrderView(..., List.of()))`, không phải `Optional.empty()`. Điều này khác việc child collection rỗng.

Một dòng hàng có trường nullable, như `discount_code`, vẫn là con hợp lệ nếu `line_id` không-null. Đừng biến một con thành “không tồn tại” chỉ vì thuộc tính tùy chọn rỗng.

## 11. Kiểm thử mapping bằng JUnit 5

Một mapper 1–N cần được kiểm thử **theo cấu trúc object graph**, không chỉ theo số hàng JOIN. Dùng `@SpringBootTest` cho ví dụ H2 ở mục 5; Spring SQL initialization nạp dữ liệu fixture, không cần service HTTP.

Tệp `src/test/java/demo/joinmapping/OrderJdbcRepositoryTest.java`:

```java
package demo.joinmapping;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class OrderJdbcRepositoryTest {

    @Autowired
    OrderJdbcRepository repository;

    @Test
    void createsOneParentForEachOrderId() {
        List<OrderView> orders = repository.findAllWithLines();

        assertEquals(3, orders.size());
        assertEquals(
                List.of(10L, 20L, 30L),
                orders.stream().map(OrderView::id).toList()
        );
    }

    @Test
    void groupsTwoLinesUnderSingleParentInOrder() {
        OrderView order = repository.findByIdWithLines(10L)
                .orElseThrow();

        assertEquals("ORD-A", order.orderNumber());
        assertEquals(
                List.of(101L, 102L),
                order.lines().stream().map(
                        OrderView.OrderLine::id
                ).toList()
        );
        assertEquals(
                List.of("BOOK", "PEN"),
                order.lines().stream().map(
                        OrderView.OrderLine::sku
                ).toList()
        );
        assertEquals(2, order.lines().get(0).quantity());
    }

    @Test
    void preservesParentWithoutChildren() {
        OrderView emptyOrder = repository.findByIdWithLines(30L)
                .orElseThrow();

        assertEquals("ORD-C", emptyOrder.orderNumber());
        assertTrue(emptyOrder.lines().isEmpty());
    }

    @Test
    void missingParentIsDifferentFromEmptyChildList() {
        assertTrue(repository.findByIdWithLines(999L).isEmpty());
        assertTrue(repository.findByIdWithLines(30L).isPresent());
    }

    @Test
    void returnedChildCollectionIsNotMutable() {
        OrderView order = repository.findByIdWithLines(10L)
                .orElseThrow();

        assertThrows(
                UnsupportedOperationException.class,
                () -> order.lines().clear()
        );
    }
}
```

Chạy kiểm thử:

```bash
./gradlew test
```

Với mã và dữ liệu mẫu nguyên vẹn, cả năm test được thiết kế để pass. Chúng bảo vệ những yêu cầu quan trọng: 3 cha riêng biệt, hai dòng đúng thứ tự trong ORD-A, đơn rỗng ORD-C vẫn có mặt, không tìm thấy ID khác với child list rỗng, và danh sách không bị sửa từ ngoài.

Đây là **integration test với H2** chứ chưa kiểm tra hiệu năng hay ngữ nghĩa JOIN của PostgreSQL/MySQL trên production. Nếu ứng dụng thật dùng dialect đặc thù, hãy bổ sung integration test bằng DBMS đó (ví dụ Testcontainers PostgreSQL) và thử các bộ dữ liệu lớn, phân trang, concurrent changes.

### 11.1. Các ca kiểm thử thêm cần có cho dữ liệu thực tế

| Ca | Kỳ vọng |
| --- | --- |
| 0 cha | Trả `List.of()`, không có object giả |
| 1 cha, 0 con | Một cha với `lines=[]` |
| 1 cha, 1 con | Một cha và một con |
| 1 cha, 100 con | Một cha, 100 con theo thứ tự |
| 100 cha, một số không có con | Không mất cha; tổng con đúng |
| Hai cha cùng `orderNumber` theo mô hình cho phép | Không gộp hai cha chỉ vì tên giống |
| JOIN có thêm bảng làm nhân bản mỗi con | Dedupe theo child ID hoặc đổi query để tránh phép nhân |
| Child optional field NULL | Con vẫn tồn tại nếu child PK không NULL |
| JOIN bị giới hạn `LIMIT` theo hàng | Test phải phát hiện child list bị cắt |
| Hai query phân trang trong môi trường ghi đồng thời | Đánh giá consistency contract và isolation phù hợp |

Đừng chỉ assert tổng số `OrderView`: có thể số cha đúng nhưng các dòng bị thiếu, trùng hoặc gắn nhầm cha. Kiểm tra **ID cha, ID con, số lượng, thứ tự và dữ liệu** để phát hiện đúng lỗi mapping.

## 12. Hiệu năng và an toàn tài nguyên

Một query JOIN có thể loại bỏ N+1 nhưng không tự động nhanh hơn mọi cách tải dữ liệu:

- **Số hàng truyền:** một cha với 1.000 dòng làm cột cha được lặp 1.000 lần trên mạng JDBC. Nếu cha có nhiều cột dài, chi phí truyền dữ liệu tăng.
- **Bộ nhớ:** extractor giữ aggregate trong RAM; đừng mặc định trả hàng triệu con về một request không phân trang.
- **Projection:** chỉ chọn cột thực sự cần, tránh `SELECT *` và dữ liệu lớn như BLOB ở danh sách.
- **Index:** FK child `order_id` và trường sắp xếp `line_no` cần index tương ứng với workload; kiểm tra bằng `EXPLAIN` thay vì đoán.
- **Tài nguyên JDBC:** `JdbcTemplate` quản lý mở/đóng statement/result set theo lifecycle. Đừng trả `ResultSet` ra ngoài và để service/web serialize chậm trong khi connection đang mượn.
- **Transaction:** một truy vấn chỉ đọc ngắn có thể không cần service transaction dài. Nếu cần snapshot nhất quán qua nhiều query, quyết định isolation/range hợp lý, tránh gọi HTTP chậm trong transaction.
- **Giới hạn tải:** phân trang theo cha, batch tải children, áp dụng max page size. Kết quả đa collection thường nên dùng nhiều query hơn một JOIN khổng lồ.
- **Quan sát:** đo thời gian query, số hàng từ DB, số cha/con sau mapping, memory, p95/p99 và số connection chờ trong pool.

Một phép đo hữu ích với một trang: **returned SQL rows**, **distinct parent IDs**, **distinct child IDs**, **time to map** và **response size**. Nếu SQL trả 100.000 hàng chỉ để tạo 100 cha và 200 con, có thể đang gặp JOIN explosion hoặc chọn quá nhiều dữ liệu.

## 13. Các lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `RowMapper<Order>` trực tiếp cho JOIN 1–N | Tạo nhiều Order trùng ID | Dùng `ResultSetExtractor`/grouping theo parent ID |
| `queryForObject` trên JOIN cha có nhiều con | Ném `IncorrectResultSizeDataAccessException` | Dùng `query` với extractor trả aggregate |
| `INNER JOIN` khi cần cha không con | Mất các cha có collection rỗng | `LEFT JOIN` |
| Không kiểm tra `line_id IS NULL` | Tạo child giả từ hàng LEFT JOIN | Kiểm tra PK con nullable đúng cách |
| Dùng `getLong` rồi không gọi `wasNull` | SQL NULL bị hiểu thành ID 0 | `getObject(..., Long.class)` hoặc `wasNull()` ngay sau getter |
| Gom cha theo `name` hoặc `orderNumber` không unique | Gộp nhầm hai cha khác nhau | Gom theo khóa chính/khóa ghép thật |
| Dựa vào thứ tự DB không có `ORDER BY` | Child list đổi thứ tự khó dự đoán | Sắp theo parent ID và child position/ID |
| JOIN hai collection độc lập | Mỗi con bị lặp theo tích hai collection | Dedupe theo ID, hoặc batch query tách biệt |
| Dedupe bằng SKU/text | Gộp nhầm hai dòng hợp lệ cùng SKU | Dedupe bằng child PK |
| `LIMIT/OFFSET` trực tiếp trên joined rows | Cắt dở child collection | Phân trang ID cha trước, tải children theo batch |
| Query children từng cha trong vòng lặp | N+1 database round trips | Một query theo tập ID cha |
| `WHERE child.condition` trên LEFT JOIN | Có thể mất cha không con phù hợp | Xem lại `ON`/`WHERE` theo nghiệp vụ |
| `COUNT(*)` để đếm child ở LEFT JOIN | Cha rỗng bị đếm là một | `COUNT(child.id)` khi đúng mô hình |
| Không đặt alias cho cột `id` của hai bảng | Đọc nhầm/mơ hồ cột | `AS order_id`, `AS line_id` |
| Dùng ResultSetExtractor lưu map vào field dùng chung | Trộn trạng thái giữa các request, race condition | Khởi tạo accumulator cục bộ trong mỗi query |
| Tạo list mutable và đưa thẳng cho caller | Caller vô tình làm hỏng aggregate đọc | `List.copyOf` ở DTO cuối cùng |
| Trả `ResultSet`/`Connection` ra khỏi repository | Resource leak, coupling JDBC | Map toàn bộ trong repository rồi trả DTO |
| Quá nhiều rows/columns từ JOIN | Tốn RAM và bandwidth | Projection, paging, batch loading, index |

## 14. Bài tập áp dụng

**Bài 1 — dự đoán số hàng.** Cho 4 đơn, lần lượt có 0, 1, 3, 5 dòng hàng. Hỏi `INNER JOIN` và `LEFT JOIN` tạo bao nhiêu hàng? Vì sao số hàng LEFT JOIN không trùng số đối tượng Order cần trả?

**Bài 2 — phát hiện bug.** Một mapper chạy:

```java
List<OrderView> result = new ArrayList<>();
while (rs.next()) {
    result.add(new OrderView(
            rs.getLong("order_id"),
            rs.getString("order_number"),
            List.of()
    ));
}
```

Đây là fragment xử lý ResultSet, bỏ qua con. Với ORD-A có hai dòng, nó tạo mấy cha? Hãy thay bằng map theo ID, phát hiện `line_id == null` và thêm con đúng nơi.

**Bài 3 — LEFT JOIN.** Viết truy vấn chỉ lấy các dòng `quantity >= 2` nhưng vẫn giữ tất cả đơn, kể cả ORD-C không có con. Đặt điều kiện ở `ON` hay `WHERE`? Giải thích bằng hàng con NULL.

**Bài 4 — nhiều collection.** Một Order có 3 lines và 4 notes. JOIN cả hai cho tối đa bao nhiêu hàng? Nếu chưa dedupe, mỗi line bị thêm mấy lần? Hãy chọn giữa dedupe bằng child ID hoặc thực hiện query riêng theo batch.

**Bài 5 — phân trang.** Màn hình muốn hiển thị 10 đơn, mỗi đơn có toàn bộ dòng. Vì sao `LIMIT 10` trên JOIN dễ trả thiếu dữ liệu? Hãy đề xuất câu SQL chọn 10 ID cha và câu SQL tải dòng của 10 ID bằng bind parameters.

**Bài 6 — kiểm thử.** Bổ sung dữ liệu một Order có 10 lines với `line_no` đảo thứ tự insert, xác minh `ORDER BY` tạo list đúng. Tạo thêm test xác minh cùng child ID xuất hiện nhiều hàng sau JOIN thêm bảng phụ thì không sinh child trùng.

**Gợi ý:** Bài 1 cho `INNER JOIN = 0+1+3+5 = 9` và `LEFT JOIN = 1+1+3+5 = 10`, nhưng đều chỉ có tối đa 4 cha và `INNER JOIN` mất cha không con. Bài 3 dùng điều kiện lọc child trong `ON` để vẫn giữ cha không có dòng thỏa. Bài 4 có `3×4=12` hàng và mỗi dòng lặp 4 lần; khử trùng không xóa chi phí vận chuyển 12 hàng. Bài 5 cần phân trang theo **cha**, không theo các hàng JOIN.

## 15. Checklist khi thiết kế mapper 1–N

- Đã xác định đúng **khóa chính cha** và **khóa chính con** chưa?
- SQL JOIN đang trả đúng tập cha theo yêu cầu, kể cả cha không có con chưa?
- Cột cha/con có alias rõ ràng, tránh `id` mơ hồ chưa?
- Dùng `ResultSetExtractor` hoặc một bước grouping minh bạch để biến nhiều hàng thành một cha chưa?
- Có kiểm tra `NULL` của **PK con** trước khi tạo object con chưa?
- Nếu JOIN thêm bảng, đã tính **độ nhân hàng** và chiến lược dedupe/tải tách biệt chưa?
- Có `ORDER BY` cho thứ tự cha/con mà UI cần chưa?
- Nếu có phân trang, đang phân trang **parent IDs** thay vì raw joined rows chưa?
- Có tránh N+1 bằng một query con theo danh sách cha chưa?
- Đã đóng vòng đời JDBC trong repository, không truyền `ResultSet`/connection sang controller chưa?
- Có test 0, 1, nhiều con; cha không con; null; thứ tự; join nhiều tập; phân trang và hiệu năng chưa?

**Kết luận:** ánh xạ quan hệ một-nhiều từ SQL JOIN đòi hỏi hiểu sự khác biệt giữa **số hàng SQL** và **số đối tượng nghiệp vụ**. Trong Spring JDBC, `ResultSetExtractor` kết hợp `LinkedHashMap` theo khóa cha là mẫu dễ hiểu: duyệt một lần, tạo một cha cho mỗi ID, thêm con khi PK con khác NULL, giữ thứ tự có chủ đích và trả object tree bất biến. Với nhiều collection hoặc phân trang, điều chỉnh hình dạng query để tránh nhân hàng và cắt dở dữ liệu trước khi tối ưu mapper.

## Tài liệu tham khảo

- Spring Framework — JDBC Core và truy vấn/ánh xạ kết quả: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — `ResultSetExtractor` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html
- Spring Framework — `RowMapper` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/RowMapper.html
- Spring Framework — `JdbcTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework — `NamedParameterJdbcTemplate` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- PostgreSQL — Combining Queries/Joined Tables: https://www.postgresql.org/docs/current/queries-table-expressions.html#QUERIES-JOIN
- PostgreSQL — `SELECT` và `ORDER BY`/`LIMIT`: https://www.postgresql.org/docs/current/sql-select.html

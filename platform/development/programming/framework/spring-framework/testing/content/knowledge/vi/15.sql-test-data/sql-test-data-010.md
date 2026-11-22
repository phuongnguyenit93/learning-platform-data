# JdbcTestUtils để đếm, kiểm tra và dọn dữ liệu

Khi viết kiểm thử Spring có truy cập cơ sở dữ liệu, ta thường cần xác nhận một bảng có bao nhiêu hàng, kiểm tra số hàng thỏa điều kiện hoặc dọn dữ liệu giữa các trường hợp kiểm thử. Spring Test cung cấp lớp tiện ích `JdbcTestUtils` để thực hiện các thao tác phổ biến đó trên `JdbcTemplate`.

`JdbcTestUtils` không phải một repository, không quản lý transaction và cũng không tạo database. Đây là tập hợp các phương thức tiện ích dùng câu SQL đơn giản để đếm, xóa hàng hoặc xóa bảng. Test vẫn cần một `DataSource`, một `JdbcTemplate` và transaction manager phù hợp nếu muốn thao tác tham gia transaction do Spring quản lý.

Các phương thức thường dùng:

| Phương thức | Công việc |
|---|---|
| `countRowsInTable(jdbcTemplate, tableName)` | Đếm tất cả hàng trong bảng. |
| `countRowsInTableWhere(jdbcTemplate, tableName, whereClause)` | Đếm hàng thỏa điều kiện WHERE. |
| `deleteFromTableWhere(jdbcTemplate, tableName, whereClause)` | Xóa hàng thỏa điều kiện WHERE. |
| `deleteFromTables(jdbcTemplate, tableNames...)` | Xóa toàn bộ hàng trong các bảng được chỉ định. |
| `dropTables(jdbcTemplate, tableNames...)` | Thực thi DROP TABLE cho các bảng được chỉ định. |

Các phương thức này thuộc package `org.springframework.test.jdbc` trong module `spring-test`.

## 1. Dependency và cách sử dụng cơ bản

Với ứng dụng Spring Boot, `spring-boot-starter-test` thường đã đưa Spring Test vào test classpath. Với dự án Spring Framework không dùng Boot, khai báo module `spring-test` ở test scope cùng các module JDBC và JUnit mà dự án cần.

Ví dụ Gradle:

```groovy
dependencies {
    testImplementation("org.springframework:spring-test")
    testImplementation("org.springframework:spring-jdbc")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core")
}

tasks.test {
    useJUnitPlatform()
}
```

Import lớp tiện ích:

```java
import org.springframework.test.jdbc.JdbcTestUtils;
```

Các phương thức của `JdbcTestUtils` là static. Có thể gọi bằng tên lớp để thể hiện rõ nguồn API:

```java
int total = JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders");
```

Hoặc dùng static import trong test:

```java
import static org.springframework.test.jdbc.JdbcTestUtils.countRowsInTable;
import static org.springframework.test.jdbc.JdbcTestUtils.countRowsInTableWhere;
```

Đối số đầu tiên luôn là `JdbcTemplate`. JdbcTestUtils dùng template này để thực thi SQL và lấy kết quả. Vì vậy, các thao tác đếm hoặc xóa được thực hiện trên đúng datasource mà template đang sử dụng.

## 2. Đếm toàn bộ hàng bằng countRowsInTable

`countRowsInTable(jdbcTemplate, tableName)` trả về số hàng hiện có trong bảng được chỉ định. Đây là cách ngắn gọn để xác nhận dữ liệu đã được thêm, đã bị xóa hoặc trạng thái fixture có đúng số lượng mong đợi hay không.

Ví dụ:

```java
int orderCount = JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders");

assertThat(orderCount).isEqualTo(3);
```

Phương thức này thực hiện truy vấn đếm hàng tương ứng với bảng. Nó trả về một giá trị số nguyên, không trả về danh sách entity hoặc nội dung các cột.

Một test hoàn chỉnh có thể kiểm tra số lượng trước và sau khi gọi repository:

```java
@SpringJUnitConfig(classes = JdbcTestConfiguration.class)
@Transactional
class OrderRepositoryTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void insertsOneOrder() {
        int before = JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders");

        orderRepository.save(new Order("ORD-100", "PAID"));

        int after = JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders");
        assertThat(after).isEqualTo(before + 1);
    }
}
```

So sánh trước/sau giúp test không phụ thuộc bảng ban đầu phải rỗng. Điều này hữu ích khi database có dữ liệu seed hoặc một test fixture đã tạo sẵn nhiều hàng.

### 2.1. Đếm theo schema hoặc tên bảng có qualifier

Tham số `tableName` là tên bảng được ghép vào câu SQL. Nếu database dùng schema, có thể truyền tên đã bao gồm schema theo cú pháp mà database hỗ trợ, ví dụ `sales.orders`. Với tên có chữ hoa, ký tự đặc biệt hoặc từ khóa SQL, cần dùng cách quote identifier phù hợp với database.

JdbcTestUtils không tự suy luận schema hoặc chuẩn hóa mọi quy tắc đặt tên của từng hệ quản trị cơ sở dữ liệu. Hãy dùng đúng tên bảng mà JDBC/database nhận diện được trong câu SQL.

## 3. Đếm hàng theo điều kiện bằng countRowsInTableWhere

`countRowsInTableWhere(jdbcTemplate, tableName, whereClause)` đếm số hàng trong bảng thỏa một biểu thức WHERE.

Ví dụ:

```java
int paidOrders = JdbcTestUtils.countRowsInTableWhere(
        jdbcTemplate,
        "orders",
        "status = 'PAID'"
);

assertThat(paidOrders).isEqualTo(2);
```

Đối số `whereClause` chỉ chứa phần điều kiện, không cần viết từ khóa `WHERE` ở đầu. JdbcTestUtils tự ghép điều kiện vào câu truy vấn đếm.

Có thể kết hợp nhiều điều kiện:

```java
int recentPaidOrders = JdbcTestUtils.countRowsInTableWhere(
        jdbcTemplate,
        "orders",
        "status = 'PAID' AND total_amount >= 100"
);
```

Biểu thức WHERE tuân theo cú pháp SQL của database đang sử dụng. Nếu cần kiểm tra null, khoảng giá trị, ngày hoặc nhiều cột, hãy viết điều kiện rõ ràng theo dialect phù hợp.

### 3.1. Kiểm tra trạng thái trước và sau một thao tác

Ví dụ repository chuyển các đơn hàng đang chờ sang trạng thái đã thanh toán:

```java
@Test
void marksPendingOrdersAsPaid() {
    int pendingBefore = JdbcTestUtils.countRowsInTableWhere(
            jdbcTemplate, "orders", "status = 'PENDING'"
    );
    int paidBefore = JdbcTestUtils.countRowsInTableWhere(
            jdbcTemplate, "orders", "status = 'PAID'"
    );

    orderRepository.markAllPendingAsPaid();

    int pendingAfter = JdbcTestUtils.countRowsInTableWhere(
            jdbcTemplate, "orders", "status = 'PENDING'"
    );
    int paidAfter = JdbcTestUtils.countRowsInTableWhere(
            jdbcTemplate, "orders", "status = 'PAID'"
    );

    assertThat(pendingAfter).isZero();
    assertThat(paidAfter).isEqualTo(pendingBefore + paidBefore);
}
```

Trong ví dụ trên, biến `paidBefore` cần được lấy trước thao tác nếu test muốn so sánh chính xác số lượng ban đầu. Việc lưu snapshot trước và sau giúp assertion diễn đạt rõ điều kiện thay đổi của dữ liệu.

### 3.2. Điều kiện có giá trị động

`countRowsInTableWhere` nhận một chuỗi SQL điều kiện, không nhận danh sách bind parameter riêng. Không nối dữ liệu đầu vào không tin cậy vào `whereClause`. Nếu điều kiện phụ thuộc giá trị runtime, hãy dùng `JdbcTemplate` với prepared statement:

```java
int count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE status = ? AND customer_id = ?",
        Integer.class,
        status,
        customerId
);
```

Cách này cho phép JDBC bind giá trị đúng kiểu và tránh lỗi khi giá trị chứa dấu nháy hoặc ký tự đặc biệt. JdbcTestUtils phù hợp với điều kiện cố định, do test author kiểm soát; truy vấn tham số hóa phù hợp khi điều kiện cần thay đổi theo dữ liệu.

## 4. Xóa các hàng thỏa điều kiện bằng deleteFromTableWhere

`deleteFromTableWhere(jdbcTemplate, tableName, whereClause)` xóa các hàng trong bảng thỏa điều kiện. Phương thức trả về số hàng bị ảnh hưởng theo kết quả update của JDBC.

Ví dụ xóa các đơn hàng đã hủy:

```java
int deleted = JdbcTestUtils.deleteFromTableWhere(
        jdbcTemplate,
        "orders",
        "status = 'CANCELLED'"
);

assertThat(deleted).isEqualTo(2);
```

Có thể xác nhận trạng thái sau khi xóa:

```java
int remaining = JdbcTestUtils.countRowsInTableWhere(
        jdbcTemplate,
        "orders",
        "status = 'CANCELLED'"
);

assertThat(remaining).isZero();
```

Đếm trước hoặc sau khi xóa giúp test kiểm tra đúng phạm vi dữ liệu bị tác động. Nếu chỉ cần kiểm tra số hàng bị xóa, giá trị trả về từ `deleteFromTableWhere` thường đã đủ.

### 4.1. Điều kiện xóa phải giới hạn đúng hàng

Điều kiện `whereClause` được ghép vào câu DELETE. Nếu điều kiện quá rộng hoặc rỗng theo cách tạo ra câu SQL không có WHERE, test có thể xóa nhiều dữ liệu hơn dự kiến. Hãy đặt điều kiện cụ thể và chỉ rõ mục tiêu dữ liệu.

Ví dụ:

```java
int deleted = JdbcTestUtils.deleteFromTableWhere(
        jdbcTemplate,
        "orders",
        "customer_id = 'C-100' AND status = 'CANCELLED'"
);
```

Nếu cần bind customer id từ biến, dùng prepared statement thay vì nối chuỗi SQL:

```java
int deleted = jdbcTemplate.update(
        "DELETE FROM orders WHERE customer_id = ? AND status = ?",
        customerId,
        "CANCELLED"
);
```

## 5. Xóa toàn bộ dữ liệu trong nhiều bảng bằng deleteFromTables

`deleteFromTables(jdbcTemplate, tableNames...)` xóa tất cả hàng khỏi từng bảng được truyền vào. Phương thức nhận tên bảng dạng varargs và trả về tổng số hàng bị xóa từ các bảng.

Ví dụ:

```java
int deletedRows = JdbcTestUtils.deleteFromTables(
        jdbcTemplate,
        "order_items",
        "orders",
        "customers"
);
```

Phương thức này tương đương việc thực hiện thao tác DELETE trên các bảng được liệt kê. Nó không xóa cấu trúc bảng, không reset schema và không tự động thay thế bằng TRUNCATE.

### 5.1. Thứ tự xóa khi có foreign key

Nếu bảng con tham chiếu bảng cha bằng foreign key, database có thể từ chối xóa hàng ở bảng cha khi vẫn còn hàng con. Khi đó, cần xóa bảng con trước rồi mới xóa bảng cha, trừ khi schema có chính sách cascade phù hợp.

Ví dụ quan hệ:

```text
customers
    |
    +----< orders
                |
                +----< order_items
```

Thứ tự truyền phù hợp thường là:

```java
JdbcTestUtils.deleteFromTables(
        jdbcTemplate,
        "order_items",
        "orders",
        "customers"
);
```

Thứ tự thực tế phụ thuộc vào quan hệ khóa ngoại và quy tắc cascade của schema. JdbcTestUtils không phân tích metadata để tự sắp xếp dependency giữa các bảng. Test phải truyền danh sách theo thứ tự mà database cho phép.

### 5.2. Kiểm tra kết quả dọn dữ liệu

Sau khi xóa, có thể xác nhận từng bảng:

```java
JdbcTestUtils.deleteFromTables(
        jdbcTemplate,
        "order_items",
        "orders"
);

assertThat(JdbcTestUtils.countRowsInTable(jdbcTemplate, "order_items")).isZero();
assertThat(JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders")).isZero();
```

Khi bảng có dữ liệu nền được seed và cần giữ lại, không dùng `deleteFromTables` cho toàn bảng. Hãy xóa theo điều kiện cụ thể hoặc dùng fixture có khóa riêng cho test.

## 6. Xóa cấu trúc bảng bằng dropTables

`dropTables(jdbcTemplate, tableNames...)` thực thi câu lệnh `DROP TABLE` cho các bảng được chỉ định. Khác với `deleteFromTables`, thao tác này xóa cả cấu trúc bảng và dữ liệu của bảng.

Ví dụ trong bước teardown của một database/schema do test sở hữu:

```java
@AfterAll
static void dropTestTables(@Autowired JdbcTemplate jdbcTemplate) {
    JdbcTestUtils.dropTables(
            jdbcTemplate,
            "order_items",
            "orders",
            "customers"
    );
}
```

Đoạn ví dụ minh họa ý tưởng dọn schema; việc inject tham số vào `@AfterAll` cần được cấu hình theo JUnit Jupiter và SpringExtension của test class, hoặc có thể đặt thao tác teardown trong một fixture chuyên biệt.

`dropTables` là DDL, không phải thao tác dọn dữ liệu thông thường. Khả năng rollback DDL phụ thuộc hệ quản trị cơ sở dữ liệu; một số database tự commit quanh DDL hoặc không rollback được thay đổi schema như transaction DML. Chỉ dùng phương thức này trên schema/database tạm thời thuộc quyền kiểm soát của test.

Nếu bảng có foreign key, view hoặc object phụ thuộc, thứ tự drop cũng cần phù hợp với dependency của schema. JdbcTestUtils không tự tính thứ tự phụ thuộc.

## 7. JdbcTestUtils và transaction của Spring Test

JdbcTestUtils thực thi SQL thông qua JdbcTemplate. Bản thân lớp tiện ích không bắt đầu hoặc kết thúc transaction. Nếu test đang có test-managed transaction và JdbcTemplate dùng cùng DataSource với transaction manager, thao tác đếm/xóa sẽ tham gia transaction đó trên cùng thread.

Ví dụ:

```java
@SpringJUnitConfig(classes = JdbcTestConfiguration.class)
@Transactional
class JdbcCleanupTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void deletesFixtureRowsWithinTestTransaction() {
        int deleted = JdbcTestUtils.deleteFromTableWhere(
                jdbcTemplate,
                "orders",
                "test_batch = 'BATCH-1'"
        );

        assertThat(deleted).isGreaterThanOrEqualTo(0);
    }
}
```

Khi test kết thúc, Spring Test mặc định rollback test-managed transaction. Nếu thao tác DELETE nằm trong transaction đó, dữ liệu đã xóa có thể được phục hồi sau rollback. Điều này hữu ích khi test chỉ cần xác nhận logic dọn dữ liệu mà không muốn làm thay đổi database sau khi test hoàn tất.

Nếu test không có transaction bao quanh, thao tác DELETE thường được commit theo cấu hình connection/autocommit hoặc transaction do ứng dụng quản lý. Khi đó, dữ liệu bị xóa có thể tồn tại ở trạng thái đã xóa sau khi test kết thúc.

### 7.1. Dọn fixture trong @BeforeEach

Khi test cần một bảng ở trạng thái xác định, có thể dọn fixture trước mỗi test:

```java
@SpringJUnitConfig(classes = JdbcTestConfiguration.class)
@Transactional
class OrderRepositoryTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void prepareDatabase() {
        JdbcTestUtils.deleteFromTables(
                jdbcTemplate,
                "order_items",
                "orders"
        );
    }

    @Test
    void startsWithNoOrders() {
        assertThat(JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders"))
                .isZero();
    }
}
```

Với test-managed transaction, callback `@BeforeEach` chạy trong transaction của test method. Vì vậy, thao tác dọn dữ liệu và fixture được tạo sau đó thường cùng được rollback khi test kết thúc.

Nếu các test chạy song song hoặc dùng chung database, xóa toàn bộ bảng trong `@BeforeEach` có thể ảnh hưởng test khác. Khi đó, nên dùng schema/database riêng, khóa dữ liệu theo test id hoặc transaction isolation phù hợp.

### 7.2. Dọn dữ liệu sau test

Có thể gọi `deleteFromTableWhere` trong `@AfterEach` để xóa dữ liệu theo test id. Tuy nhiên, khi callback vẫn chạy bên trong test-managed transaction, thao tác DELETE sẽ bị rollback cùng transaction. Điều này có nghĩa dữ liệu fixture ban đầu có thể quay lại sau khi transaction kết thúc.

Nếu cần dọn dữ liệu đã commit bên ngoài transaction test, hãy dùng một cơ chế cleanup độc lập và xác định rõ transaction manager/connection. Không giả định một DELETE chạy trong `@AfterEach` của test transactional sẽ tồn tại sau rollback.

## 8. Ví dụ hoàn chỉnh: đếm, kiểm tra và dọn dữ liệu

Giả sử bảng `orders` có các cột `id`, `customer_id`, `status` và `total_amount`. Test dùng JdbcTemplate để tạo dữ liệu, JdbcTestUtils để kiểm tra số lượng và xóa theo điều kiện:

```java
@SpringJUnitConfig(classes = JdbcTestConfiguration.class)
@Transactional
class JdbcTestUtilsExampleTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void insertFixtures() {
        jdbcTemplate.update(
                "INSERT INTO orders (id, customer_id, status, total_amount) VALUES (?, ?, ?, ?)",
                1001L, "C-100", "PAID", new BigDecimal("120.00")
        );
        jdbcTemplate.update(
                "INSERT INTO orders (id, customer_id, status, total_amount) VALUES (?, ?, ?, ?)",
                1002L, "C-100", "CANCELLED", new BigDecimal("50.00")
        );
        jdbcTemplate.update(
                "INSERT INTO orders (id, customer_id, status, total_amount) VALUES (?, ?, ?, ?)",
                1003L, "C-200", "PAID", new BigDecimal("200.00")
        );
    }

    @Test
    void countsAllRowsAndRowsMatchingCondition() {
        assertThat(JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders"))
                .isEqualTo(3);

        assertThat(JdbcTestUtils.countRowsInTableWhere(
                jdbcTemplate, "orders", "status = 'PAID'"
        )).isEqualTo(2);

        assertThat(JdbcTestUtils.countRowsInTableWhere(
                jdbcTemplate, "orders", "customer_id = 'C-100'"
        )).isEqualTo(2);
    }

    @Test
    void deletesOnlyCancelledOrders() {
        int deleted = JdbcTestUtils.deleteFromTableWhere(
                jdbcTemplate,
                "orders",
                "status = 'CANCELLED'"
        );

        assertThat(deleted).isEqualTo(1);
        assertThat(JdbcTestUtils.countRowsInTable(jdbcTemplate, "orders"))
                .isEqualTo(2);
    }
}
```

Mỗi test chạy trong transaction riêng theo Spring Test. Fixture được tạo trong `@BeforeEach` thuộc transaction test, nên thay đổi dữ liệu được rollback sau test theo mặc định. Nhờ đó, test đếm và test xóa không phụ thuộc thứ tự chạy.

## 9. Phân biệt JdbcTestUtils với JdbcTemplate

JdbcTestUtils là lớp tiện ích cấp cao cho một số thao tác kiểm thử phổ biến. JdbcTemplate là API JDBC tổng quát hơn, dùng để thực thi query, update, batch, map kết quả và bind parameter.

| Nhu cầu | Công cụ phù hợp |
|---|---|
| Đếm toàn bộ hàng của một bảng | JdbcTestUtils.countRowsInTable |
| Đếm hàng theo một điều kiện SQL cố định | JdbcTestUtils.countRowsInTableWhere |
| Xóa hàng theo điều kiện SQL cố định | JdbcTestUtils.deleteFromTableWhere |
| Xóa mọi hàng trong một số bảng | JdbcTestUtils.deleteFromTables |
| Drop bảng trong schema test | JdbcTestUtils.dropTables |
| Truy vấn với bind parameter | JdbcTemplate.query / queryForObject |
| Insert/update với bind parameter | JdbcTemplate.update |
| Truy vấn entity hoặc ánh xạ DTO | JdbcTemplate.query với RowMapper |
| Batch insert/update | JdbcTemplate.batchUpdate |
| Thực thi SQL phức tạp hoặc DDL đặc thù | JdbcTemplate hoặc công cụ migration/schema phù hợp |

Ví dụ, nếu cần đếm theo một customer id động, dùng JdbcTemplate:

```java
int count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE customer_id = ?",
        Integer.class,
        customerId
);
```

Nếu cần xóa theo danh sách id, có thể dùng named parameter hoặc câu SQL phù hợp thay vì ghép danh sách vào whereClause. Việc dùng JdbcTemplate trực tiếp cho truy vấn động giúp bind giá trị đúng cách.

## 10. Lưu ý về tên bảng và SQL fragment

JdbcTestUtils nhận tên bảng và điều kiện WHERE dưới dạng chuỗi. Các giá trị này được dùng để xây dựng SQL, không phải bind parameter.

Vì thế:

- Chỉ truyền tên bảng/schema do test author kiểm soát.
- Không lấy tên bảng trực tiếp từ request hoặc input không tin cậy.
- Không nối giá trị runtime tùy ý vào `whereClause`.
- Với giá trị động, dùng prepared statement qua JdbcTemplate.
- Kiểm tra quy tắc quote identifier nếu tên bảng có chữ hoa, khoảng trắng hoặc từ khóa SQL.
- Dùng đúng cú pháp của database đang chạy, đặc biệt khi điều kiện có kiểu ngày giờ, boolean hoặc hàm đặc thù.

Ví dụ điều kiện cố định phù hợp:

```java
JdbcTestUtils.countRowsInTableWhere(
        jdbcTemplate,
        "orders",
        "status = 'PAID' AND total_amount > 0"
);
```

Ví dụ giá trị động nên dùng bind parameter:

```java
Integer count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE status = ?",
        Integer.class,
        requestedStatus
);
```

## 11. Những lỗi thường gặp

### Thiếu spring-test trong test classpath

Nếu IDE không tìm thấy `JdbcTestUtils`, kiểm tra dependency `spring-test`. Dự án dùng starter test có thể đã có module này; dự án Spring Framework thuần cần khai báo trực tiếp.

### Dùng nhầm JdbcTemplate hoặc DataSource

JdbcTestUtils thực thi trên template được truyền vào. Nếu template trỏ tới database/schema khác với repository đang kiểm thử, kết quả đếm hoặc xóa không phản ánh dữ liệu mà test quan tâm. Hãy inject cùng datasource hoặc đúng test datasource.

### Thêm WHERE vào whereClause

Tham số `whereClause` chỉ cần biểu thức điều kiện, ví dụ `status = 'PAID'`. Không thêm từ khóa `WHERE` nếu phương thức tự xây dựng câu SQL.

### Dùng bind placeholder trong whereClause

JdbcTestUtils không nhận mảng giá trị bind parameter cho các phương thức `countRowsInTableWhere` và `deleteFromTableWhere`. Nếu cần dấu hỏi `?` cùng giá trị runtime, dùng JdbcTemplate với prepared statement.

### Xóa bảng cha trước bảng con

Foreign key có thể ngăn xóa hàng ở bảng cha khi bảng con còn tham chiếu. Truyền bảng con trước bảng cha hoặc cấu hình cascade đúng với mục tiêu test.

### Nhầm DELETE với TRUNCATE

`deleteFromTables` xóa hàng bằng thao tác DELETE. Nó không tự truncate bảng, không đảm bảo reset identity/sequence và vẫn chịu ảnh hưởng của foreign key, trigger hoặc rule của database.

### Dùng dropTables để dọn dữ liệu thường xuyên

`dropTables` xóa cấu trúc bảng. Nếu chỉ cần làm rỗng dữ liệu, dùng `deleteFromTables` hoặc `deleteFromTableWhere`. DDL có thể có quy tắc commit riêng của database.

### Nghĩ thao tác cleanup trong test transactional sẽ tồn tại sau test

Nếu DELETE chạy trong test-managed transaction, rollback cuối test có thể phục hồi các hàng đã xóa. Hãy hiểu transaction đang hoạt động và thời điểm callback cleanup được thực thi.

### Đếm bảng khi test khác đang ghi song song

Kết quả count có thể bị ảnh hưởng bởi transaction khác tùy isolation level và database. Tránh để nhiều test dùng chung bảng dữ liệu không cô lập; dùng schema riêng hoặc fixture có khóa phân biệt.

## 12. Chọn phương thức phù hợp

| Mục tiêu | API |
|---|---|
| Biết bảng có bao nhiêu hàng | `countRowsInTable` |
| Đếm hàng theo điều kiện cố định | `countRowsInTableWhere` |
| Xóa một nhóm hàng | `deleteFromTableWhere` |
| Làm rỗng nhiều bảng | `deleteFromTables` |
| Xóa bảng khỏi schema test | `dropTables` |
| Điều kiện cần bind giá trị động | `JdbcTemplate` với prepared statement |
| Cần kiểm tra nội dung từng cột | `JdbcTemplate`, RowMapper và assertion |

JdbcTestUtils giúp giảm mã lặp khi test cần đếm hoặc dọn dữ liệu SQL. Hãy truyền đúng JdbcTemplate, dùng tên bảng và điều kiện do test kiểm soát, sắp xếp thứ tự dọn theo foreign key và hiểu transaction hiện tại. Với truy vấn có giá trị động hoặc yêu cầu ánh xạ dữ liệu phức tạp, JdbcTemplate vẫn là công cụ phù hợp hơn.

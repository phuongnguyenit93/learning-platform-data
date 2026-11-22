# @Sql cho script hoặc câu lệnh SQL

Trong kiểm thử Spring, dữ liệu đầu vào thường cần được chuẩn bị trực tiếp trong database. Một bài test repository có thể cần một khách hàng và vài đơn hàng đã tồn tại; một bài test service có thể cần dữ liệu ở nhiều bảng để kiểm tra truy vấn, quan hệ hoặc transaction. Nếu mỗi test tự viết JDBC setup và cleanup, code kiểm thử dễ dài, lặp lại và khó đọc.

Spring TestContext cung cấp annotation **@Sql** để thực thi SQL trước hoặc sau test method. Bạn có thể dùng file SQL bên ngoài hoặc khai báo trực tiếp các câu lệnh ngay trong annotation. Cơ chế này giúp dữ liệu kiểm thử được chuẩn bị theo một quy tắc rõ ràng, gắn với test class hoặc test method và được thực thi qua DataSource của Spring.

Bài học này trình bày hai cách dùng chính của @Sql — script và câu lệnh SQL inline — cùng cách chọn thời điểm thực thi, cấu hình DataSource và transaction, kết hợp với @Transactional, quản lý dữ liệu lặp lại và xử lý các lỗi thường gặp.

## 1. @Sql dùng để làm gì?

**@Sql** yêu cầu Spring TestContext thực thi một hoặc nhiều script SQL hoặc câu lệnh SQL trong vòng đời của test. Các lệnh được chạy qua DataSource được cấu hình trong ApplicationContext, vì vậy có thể thao tác với database thật hoặc database dành riêng cho test.

Những mục đích phổ biến:

- Chèn dữ liệu mẫu trước khi kiểm tra repository.
- Tạo trạng thái ban đầu cho một quy trình nghiệp vụ.
- Cập nhật hoặc xóa dữ liệu trước một test case.
- Chuẩn bị dữ liệu ở nhiều bảng mà không phải viết nhiều dòng JDBC trong Java.
- Dọn dữ liệu sau test khi dữ liệu không được rollback cùng transaction của test.
- Dùng chung một tập dữ liệu nền cho nhiều test method.

Ví dụ đơn giản:

~~~java
@SpringBootTest
@Sql("/sql/insert-customers.sql")
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void shouldFindCustomerByEmail() {
        var customer =
                customerRepository.findByEmail("lan@example.test");

        assertTrue(customer.isPresent());
        assertEquals("Lan", customer.get().getName());
    }
}
~~~

Khi test method được chạy, Spring thực thi script trước phần thân test theo execution phase mặc định. Sau đó test truy vấn dữ liệu đã được script chèn vào.

@Sql không tự tạo database và cũng không tự định nghĩa schema. Database, DataSource, bảng và quyền thực thi SQL phải được chuẩn bị bởi cấu hình ứng dụng hoặc môi trường test. Script chỉ thực thi trên database mà Spring đã kết nối.

## 2. Hai cách khai báo SQL: script và statements

@Sql hỗ trợ hai cách cung cấp nội dung SQL:

1. **scripts**: chỉ định đường dẫn đến một hoặc nhiều file SQL.
2. **statements**: khai báo trực tiếp từng câu SQL trong annotation.

Có thể dùng thuộc tính value như bí danh của scripts:

~~~java
@Sql("/sql/seed-customers.sql")
~~~

Tương đương:

~~~java
@Sql(scripts = "/sql/seed-customers.sql")
~~~

Trong cùng một khai báo @Sql, nên chọn scripts hoặc statements theo đúng mục đích. Nếu cần thực thi nhiều nhóm lệnh với cấu hình hoặc thời điểm khác nhau, hãy khai báo các @Sql riêng biệt hoặc dùng @SqlGroup.

### 2.1. Dùng scripts khi dữ liệu có nhiều câu lệnh

Tạo file:

~~~text
src/test/resources/sql/seed-customers.sql
~~~

Nội dung:

~~~sql
DELETE FROM customer;

INSERT INTO customer (id, name, email)
VALUES (101, 'Lan', 'lan@example.test');

INSERT INTO customer (id, name, email)
VALUES (102, 'Minh', 'minh@example.test');
~~~

Khai báo trong test:

~~~java
@DataJpaTest
@Sql(scripts = "classpath:/sql/seed-customers.sql")
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void shouldLoadSeededCustomers() {
        assertEquals(2, customerRepository.count());
    }
}
~~~

Đặt script trong src/test/resources giúp file được đưa vào test classpath mà không nằm trong artifact production. Prefix classpath: làm rõ tài nguyên được lấy từ classpath.

Script riêng phù hợp khi:

- Có nhiều lệnh SQL hoặc dữ liệu liên quan nhiều bảng.
- Nhiều test dùng chung một tập dữ liệu.
- Muốn review dữ liệu test như một file độc lập.
- Muốn quản lý DDL, seed data và cleanup bằng các file riêng.
- SQL dài hoặc cần comment giải thích.

### 2.2. Dùng statements cho một số lệnh ngắn

Nếu chỉ cần một vài câu SQL đơn giản, có thể khai báo trực tiếp:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    @Sql(statements = {
            "DELETE FROM customer",
            "INSERT INTO customer (id, name, email) " +
                    "VALUES (101, 'Lan', 'lan@example.test')"
    })
    void shouldFindSeededCustomer() {
        var customer =
                customerRepository.findByEmail("lan@example.test");

        assertTrue(customer.isPresent());
        assertEquals("Lan", customer.get().getName());
    }
}
~~~

Mỗi phần tử trong mảng statements là một câu lệnh SQL được thực thi. Có thể xuống dòng trong Java để dễ đọc, nhưng cần bảo đảm chuỗi cuối cùng là câu SQL hợp lệ đối với database đang dùng.

Statements phù hợp khi:

- Chỉ có một vài lệnh ngắn.
- Dữ liệu chỉ phục vụ một test method.
- Muốn nhìn thấy setup ngay cạnh test.
- Không cần tái sử dụng một file SQL.

Nếu annotation chứa nhiều câu SQL dài, hãy chuyển sang script để test class gọn hơn.

## 3. Đường dẫn đến file SQL

Spring ResourceLoader hỗ trợ nhiều dạng đường dẫn tài nguyên. Với @Sql, nên ghi rõ prefix để người đọc hiểu nguồn file.

| Dạng đường dẫn | Ý nghĩa | Ví dụ |
|---|---|---|
| classpath: | Tìm tài nguyên trên classpath | classpath:/sql/seed.sql |
| file: | Đọc file từ filesystem | file:./config/test-data.sql |
| Đường dẫn tương đối | Được phân giải theo quy tắc tài nguyên của Spring | /sql/seed.sql hoặc tên resource tương ứng |

Trong dự án Maven hoặc Gradle, file trong src/test/resources thường được copy vào test classpath. Vì vậy, đường dẫn phổ biến là:

~~~java
@Sql("classpath:/sql/orders/seed-orders.sql")
~~~

Dùng đường dẫn tuyệt đối trong classpath giúp tránh phụ thuộc package của test class. Nếu sử dụng đường dẫn tương đối, cần hiểu cách Spring phân giải resource để không vô tình trỏ tới file khác khi di chuyển test class.

Nên tổ chức file theo chức năng:

~~~text
src/test/resources/
    sql/
        schema/
            create-customer-tables.sql
        customer/
            seed-customers.sql
            cleanup-customers.sql
        order/
            seed-orders.sql
            cleanup-orders.sql
~~~

Tên file nên thể hiện hành động và dữ liệu liên quan. Khi một script được dùng ở nhiều test class, hãy giữ nó độc lập với thứ tự chạy của các test khác.

Tránh đặt dữ liệu test trong src/main/resources nếu không có lý do rõ ràng. Dữ liệu phục vụ test thường không nên được đóng gói vào artifact ứng dụng.

## 4. Thực thi SQL trước hoặc sau test method

Thuộc tính **executionPhase** xác định thời điểm Spring chạy SQL.

Hai giá trị thường dùng:

- **BEFORE_TEST_METHOD**: chạy trước test method. Đây là mặc định.
- **AFTER_TEST_METHOD**: chạy sau test method.

### 4.1. Chuẩn bị dữ liệu trước test

~~~java
@Test
@Sql(
        scripts = "classpath:/sql/seed-orders.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
void shouldFindOpenOrders() {
    var orders = orderRepository.findByStatus(OrderStatus.OPEN);

    assertEquals(2, orders.size());
}
~~~

Khai báo phase tường minh giúp người đọc biết script phục vụ setup. Trong nhiều trường hợp có thể bỏ executionPhase vì BEFORE_TEST_METHOD là mặc định.

### 4.2. Dọn dữ liệu sau test

~~~java
@Test
@Sql(
        scripts = "classpath:/sql/seed-orders.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
        scripts = "classpath:/sql/cleanup-orders.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void shouldProcessOrders() {
    // Thực hiện và xác minh hành vi xử lý đơn hàng.
}
~~~

Script cleanup có thể xóa dữ liệu được tạo riêng cho test. Cần xem xét transaction mode để biết lệnh cleanup có được commit hay bị rollback cùng transaction khác.

Nếu test đã chạy trong một transaction được rollback, dữ liệu được chèn trong cùng transaction có thể tự biến mất khi test kết thúc. Trong trường hợp đó, cleanup script có thể không cần thiết. Nhưng nếu test ghi dữ liệu qua HTTP server chạy trên thread khác, dùng transaction riêng hoặc gọi hệ thống bên ngoài, rollback của test method không tự động xóa các side effect đó.

### 4.3. @Sql ở cấp class

Có thể đặt @Sql trên test class để script được áp dụng cho các test method trong class:

~~~java
@DataJpaTest
@Sql("classpath:/sql/seed-reference-data.sql")
class ProductRepositoryTest {

    @Test
    void shouldFindProductByCode() {
        // ...
    }

    @Test
    void shouldFindProductsByCategory() {
        // ...
    }
}
~~~

Khai báo ở cấp class thường phù hợp với dữ liệu nền dùng chung. Theo execution phase mặc định, script chạy trước mỗi test method trong class. Vì vậy, script phải có thể chạy lặp lại và không được giả định chỉ chạy một lần cho cả class.

Nếu muốn một tập dữ liệu riêng cho từng test method, khai báo @Sql trên method tương ứng.

## 5. Kết hợp @Sql cấp class và cấp method

Khi test class có dữ liệu nền và mỗi method cần dữ liệu riêng, cần hiểu quy tắc merge.

Mặc định, khai báo @Sql ở cấp method **ghi đè** khai báo @Sql ở cấp class cho method đó. Nếu muốn cả hai cùng được áp dụng, dùng **@SqlMergeMode(MERGE)**.

Ví dụ:

~~~java
@DataJpaTest
@Sql("classpath:/sql/seed-reference-data.sql")
class ProductRepositoryTest {

    @Test
    void shouldFindActiveProduct() {
        // Sử dụng dữ liệu nền của class.
    }

    @Test
    @Sql("classpath:/sql/seed-discontinued-product.sql")
    void shouldFindDiscontinuedProduct() {
        // Mặc định, khai báo method thay cho khai báo class.
    }
}
~~~

Nếu muốn method dùng cả dữ liệu nền và dữ liệu riêng:

~~~java
@DataJpaTest
@Sql("classpath:/sql/seed-reference-data.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class ProductRepositoryTest {

    @Test
    @Sql("classpath:/sql/seed-discontinued-product.sql")
    void shouldFindDiscontinuedProduct() {
        // Class-level script và method-level script đều được áp dụng.
    }
}
~~~

Có thể đặt @SqlMergeMode ở class để các method trong class dùng cùng quy tắc, hoặc đặt ở method để chỉ thay đổi một test. Khi dùng MERGE, hãy kiểm tra thứ tự và khả năng chạy lặp lại của các script, vì script cấp class và cấp method đều có thể tác động đến cùng bảng.

Không nên dựa vào thứ tự ngẫu nhiên giữa các test method để tạo dữ liệu. Mỗi method phải có trạng thái đầu vào xác định.

## 6. Dùng nhiều script hoặc nhiều khai báo @Sql

Một test có thể cần nhiều script, chẳng hạn tạo dữ liệu khách hàng, sau đó tạo đơn hàng tham chiếu khách hàng.

~~~java
@Test
@Sql(scripts = {
        "classpath:/sql/customer/seed-customers.sql",
        "classpath:/sql/order/seed-orders.sql"
})
void shouldLoadOrdersForCustomer() {
    // ...
}
~~~

Khi cần phase hoặc cấu hình khác nhau cho từng nhóm script, có thể khai báo nhiều @Sql. @Sql là annotation có thể lặp lại; cũng có thể dùng @SqlGroup để gom các khai báo:

~~~java
@Test
@SqlGroup({
        @Sql(
                scripts = "classpath:/sql/seed-orders.sql",
                executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
        ),
        @Sql(
                scripts = "classpath:/sql/cleanup-orders.sql",
                executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
        )
})
void shouldProcessOrder() {
    // ...
}
~~~

Dùng nhiều khai báo giúp tách setup và cleanup. Hãy đặt tên script rõ ràng và không để cleanup xóa dữ liệu nền mà test class khác đang dùng chung.

## 7. Cấu hình script bằng @SqlConfig

**@SqlConfig** cho phép tùy chỉnh cách Spring phân tích và thực thi script SQL. Có thể khai báo cấu hình ngay trong @Sql hoặc đặt ở cấp class để làm cấu hình mặc định cho các @Sql trong class.

Ví dụ:

~~~java
@SpringBootTest
@Sql(
        scripts = "classpath:/sql/seed-orders.sql",
        config = @SqlConfig(
                encoding = "UTF-8",
                separator = ";",
                commentPrefix = "--"
        )
)
class OrderRepositoryTest {
}
~~~

Các thuộc tính thường cần quan tâm:

| Thuộc tính | Mục đích |
|---|---|
| dataSource | Chỉ định tên bean DataSource |
| transactionManager | Chỉ định tên bean PlatformTransactionManager |
| transactionMode | Chọn cách chạy SQL trong transaction |
| encoding | Encoding của file SQL |
| separator | Dấu phân tách câu lệnh |
| commentPrefix / commentPrefixes | Tiền tố comment một dòng |
| blockCommentStartDelimiter | Dấu mở comment nhiều dòng |
| blockCommentEndDelimiter | Dấu đóng comment nhiều dòng |
| errorMode | Cách xử lý khi một câu SQL lỗi |

### 7.1. Chọn DataSource khi có nhiều database

Nếu ứng dụng có nhiều DataSource, Spring có thể không suy luận được database nào cần chạy script. Khi đó, chỉ rõ bean:

~~~java
@Sql(
        scripts = "classpath:/sql/order/seed-orders.sql",
        config = @SqlConfig(dataSource = "ordersDataSource")
)
~~~

Nếu có nhiều transaction manager, chỉ rõ manager tương ứng:

~~~java
@Sql(
        scripts = "classpath:/sql/order/seed-orders.sql",
        config = @SqlConfig(
                dataSource = "ordersDataSource",
                transactionManager = "ordersTransactionManager"
        )
)
~~~

DataSource và transaction manager phải thuộc cùng database hoặc cùng transaction resource mà script cần thao tác. Chọn nhầm manager có thể khiến script chạy ngoài transaction mà test đang mong đợi.

Nếu chỉ có một DataSource và một transaction manager phù hợp, Spring thường có thể suy luận chúng từ ApplicationContext.

### 7.2. Encoding và comment

Script SQL nên dùng encoding nhất quán, đặc biệt khi có dữ liệu tiếng Việt:

~~~java
@Sql(
        scripts = "classpath:/sql/seed-vietnamese-customers.sql",
        config = @SqlConfig(encoding = "UTF-8")
)
~~~

Ví dụ file:

~~~sql
INSERT INTO customer (id, name, email)
VALUES (201, 'Nguyễn Lan', 'lan@example.test');
~~~

Spring hỗ trợ comment một dòng và comment dạng block. Nếu script dùng quy ước comment riêng, có thể cấu hình comment prefix hoặc delimiter tương ứng.

Không nên dùng ký tự phân tách tùy chỉnh nếu script không cần. Giữ mặc định giúp SQL dễ đọc và tương thích với công cụ database phổ biến.

### 7.3. Dấu phân tách câu lệnh

Mặc định, script parser sử dụng dấu chấm phẩy để nhận diện ranh giới câu SQL. Ví dụ:

~~~sql
DELETE FROM order_item;
DELETE FROM orders;
~~~

Với stored procedure hoặc block SQL có dấu chấm phẩy bên trong, dấu phân tách mặc định có thể không phù hợp. Khi đó có thể chọn separator riêng:

~~~java
@Sql(
        scripts = "classpath:/sql/create-procedure.sql",
        config = @SqlConfig(separator = "@@")
)
~~~

File script tương ứng:

~~~sql
CREATE PROCEDURE cleanup_orders()
BEGIN
    DELETE FROM order_item;
    DELETE FROM orders;
END
@@
~~~

Cú pháp procedure phụ thuộc database. Ví dụ trên chỉ minh họa cách dùng separator tùy chỉnh; hãy điều chỉnh cú pháp và delimiter theo hệ quản trị đang dùng.

### 7.4. ErrorMode

Theo mặc định, lỗi SQL được xử lý theo chế độ mặc định của Spring và lỗi không được bỏ qua tùy tiện. @SqlConfig cho phép chọn errorMode:

- DEFAULT: dùng chính sách xử lý lỗi mặc định.
- CONTINUE_ON_ERROR: tiếp tục thực thi các câu lệnh sau khi một câu lệnh gặp lỗi.
- IGNORE_FAILED_DROPS: bỏ qua lỗi từ các lệnh DROP phù hợp, hữu ích trong một số script dọn dẹp.

Chỉ nên tiếp tục khi lỗi đã được dự liệu và không làm dữ liệu ở trạng thái nửa vời. Với script setup tạo dữ liệu cần thiết cho assertion, mặc định fail-fast thường an toàn hơn: test dừng ngay khi dữ liệu không được chuẩn bị đúng.

## 8. TransactionMode: SQL chạy trong transaction nào?

Một câu hỏi quan trọng là script có tham gia transaction của test hay không. @SqlConfig cung cấp thuộc tính **transactionMode** với hai lựa chọn chính:

- **INFERRED**: Spring suy luận DataSource và transaction manager. Nếu có transaction đang hoạt động, script có thể tham gia transaction đó; nếu có transaction manager phù hợp nhưng chưa có transaction, Spring có thể tạo transaction cho việc thực thi script. Nếu không có transaction manager phù hợp, script được thực thi mà không có transaction do Spring quản lý.
- **ISOLATED**: Spring chạy script trong transaction độc lập, dùng propagation tương đương REQUIRES_NEW và commit transaction đó sau khi script hoàn tất.

INFERRED là chế độ mặc định.

### 8.1. Script tham gia transaction của test

~~~java
@DataJpaTest
@Transactional
@Sql("classpath:/sql/seed-customers.sql")
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void shouldReadSeededCustomer() {
        assertEquals(2, customerRepository.count());
    }
}
~~~

Với test-managed transaction, script BEFORE_TEST_METHOD thường chạy trong transaction của test khi Spring có thể suy luận đúng transaction manager. Khi test kết thúc, transaction mặc định rollback. Dữ liệu do script chèn trong transaction đó cũng được rollback.

Cách này phù hợp với test cần dữ liệu ban đầu nhưng không muốn để lại bản ghi sau mỗi lần chạy.

### 8.2. Script cần transaction độc lập

~~~java
@Sql(
        scripts = "classpath:/sql/seed-reference-data.sql",
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
~~~

ISOLATED tạo transaction riêng và commit script độc lập. Dữ liệu có thể vẫn tồn tại sau khi transaction của test rollback. Đây là lựa chọn có chủ đích khi cần dữ liệu được commit trước test hoặc khi script phải chạy tách biệt với transaction hiện tại.

Vì script đã commit, cần có kế hoạch cleanup rõ ràng. Nếu không, các lần chạy sau có thể gặp duplicate key hoặc dữ liệu cũ làm sai kết quả.

### 8.3. Không nhầm rollback của test với mọi side effect

Rollback test-managed transaction chỉ hoàn tác những thao tác tham gia transaction đó. Nó không tự động hoàn tác:

- SQL chạy trong transaction độc lập đã commit.
- Request HTTP được xử lý trong transaction của server ở thread khác.
- Ghi dữ liệu qua một DataSource hoặc transaction manager khác.
- File được tạo, message được gửi hoặc API bên ngoài được gọi.
- Tác động của một dịch vụ không hỗ trợ transaction chung.

Nếu dùng @Sql để chuẩn bị dữ liệu cho test có RANDOM_PORT, hãy xem request được xử lý trong transaction nào. Transaction của thread test không tự động bao trùm transaction phía HTTP server.

## 9. Kết hợp @Sql với @Transactional

Một mẫu phổ biến trong repository test là dùng @DataJpaTest hoặc @SpringBootTest cùng @Transactional.

~~~java
@DataJpaTest
@Transactional
@Sql(
        scripts = "classpath:/sql/order/seed-orders.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void shouldFindOrdersForCustomer() {
        var orders =
                orderRepository.findByCustomerId("customer-1");

        assertEquals(2, orders.size());
    }
}
~~~

Spring TestContext tích hợp @Sql với transaction test thông qua các TestExecutionListener. Transaction listener quản lý test transaction; SQL listener thực thi script ở các phase tương ứng.

Một số lưu ý:

- @DataJpaTest mặc định có transaction cho mỗi test method và rollback sau khi test kết thúc.
- @SpringBootTest không tự động có test transaction trừ khi khai báo @Transactional hoặc dùng cơ chế transaction phù hợp.
- Script BEFORE_TEST_METHOD có thể tham gia test transaction theo transactionMode và cấu hình DataSource.
- Script ISOLATED được commit riêng, vì vậy dữ liệu không bị rollback cùng test transaction.
- Nếu test dùng nhiều DataSource, phải xác định rõ DataSource và transaction manager.
- Nếu test thực hiện thao tác bất đồng bộ hoặc HTTP request qua server thật, cần quản lý transaction và cleanup riêng.

Không nên dựa vào rollback để làm sạch dữ liệu nếu script hoặc ứng dụng ghi qua transaction khác. Hãy xác minh ranh giới transaction trước khi chọn chiến lược cleanup.

## 10. Ví dụ đầy đủ: seed dữ liệu bằng script và kiểm tra repository

Giả sử có hai bảng:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Script dữ liệu:

~~~sql
DELETE FROM orders;
DELETE FROM customer;

INSERT INTO customer (id, name, email)
VALUES (101, 'Lan', 'lan@example.test');

INSERT INTO customer (id, name, email)
VALUES (102, 'Minh', 'minh@example.test');

INSERT INTO orders (id, customer_id, status, total_amount)
VALUES (1001, 101, 'PAID', 250000.00);

INSERT INTO orders (id, customer_id, status, total_amount)
VALUES (1002, 101, 'OPEN', 150000.00);
~~~

Test:

~~~java
@DataJpaTest
@Sql(
        scripts = "classpath:/sql/order/seed-customer-orders.sql",
        config = @SqlConfig(encoding = "UTF-8")
)
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void shouldFindOrdersByCustomer() {
        var orders = orderRepository.findByCustomerId(101L);

        assertEquals(2, orders.size());
        assertTrue(orders.stream()
                .anyMatch(order -> order.getStatus() == OrderStatus.PAID));
        assertTrue(orders.stream()
                .anyMatch(order -> order.getStatus() == OrderStatus.OPEN));
    }
}
~~~

Ví dụ này giả định schema đã được tạo trước khi @Sql chạy. Với @DataJpaTest, schema có thể được tạo từ entity, schema.sql hoặc cấu hình database test tùy dự án. Nếu cần kiểm tra migration, hãy dùng database test tương thích và chạy migration trước script seed.

Script xóa dữ liệu trong hai bảng trước khi chèn. Nếu database có foreign key, cần xóa bảng con trước bảng cha. Thứ tự insert cũng phải theo quan hệ khóa ngoại.

Trong test transaction mặc định, các thao tác SQL có thể được rollback sau test. Nếu script chạy trong transaction độc lập, dữ liệu đã commit sẽ cần cleanup riêng.

## 11. Ví dụ dùng statements cho một test method

Với một test chỉ cần một bản ghi, statements có thể ngắn gọn:

~~~java
@DataJpaTest
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    @Sql(statements = {
            "DELETE FROM account WHERE id = 501",
            "INSERT INTO account (id, owner, balance) " +
                    "VALUES (501, 'Lan', 100000.00)"
    })
    void shouldFindAccountById() {
        var account = accountRepository.findById(501L);

        assertTrue(account.isPresent());
        assertEquals("Lan", account.get().getOwner());
        assertEquals(
                new BigDecimal("100000.00"),
                account.get().getBalance()
        );
    }
}
~~~

Statements giúp dữ liệu setup nằm ngay cạnh test. Nhưng nếu một câu lệnh cần nhiều dòng hoặc có nhiều bản ghi, script thường dễ đọc và dễ tái sử dụng hơn.

Tránh chèn dữ liệu bằng cách ghép chuỗi từ dữ liệu người dùng không tin cậy. @Sql statements là SQL tĩnh gắn với test; nếu cần tham số động, dùng JDBC/JPA hoặc một test data builder có parameter binding thay vì nối chuỗi SQL tùy tiện.

## 12. Sử dụng @Sql trong @DataJpaTest và @JdbcTest

@Sql không chỉ dành cho @SpringBootTest. Nó hoạt động với các test tích hợp Spring TestContext có DataSource phù hợp.

### Với @DataJpaTest

~~~java
@DataJpaTest
@Sql("/sql/seed-products.sql")
class ProductRepositoryTest {
}
~~~

@DataJpaTest tải slice JPA và thường dùng database nhúng nếu dependency và cấu hình cho phép. Script chạy trên DataSource của slice.

Nếu muốn dùng đúng hệ quản trị production, có thể kết hợp Testcontainers và DynamicPropertySource để cung cấp URL database test. Khi đó, @Sql vẫn thực thi script trên DataSource được cấu hình từ container.

### Với @JdbcTest

~~~java
@JdbcTest
@Sql("/sql/seed-products.sql")
class ProductJdbcRepositoryTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void shouldCountSeededProducts() {
        var count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM product",
                Integer.class
        );

        assertEquals(3, count);
    }
}
~~~

@JdbcTest tập trung vào JDBC components. @Sql giúp seed dữ liệu trước khi JdbcTemplate thực hiện truy vấn.

Với cả hai slice test, cần nhớ transaction mặc định và rollback của test. Nếu dùng script ở phase khác hoặc transaction mode khác, hãy xác minh dữ liệu có được commit hay không.

## 13. SQL script có thể chứa DDL không?

Có thể dùng @Sql để thực thi DDL như CREATE TABLE, ALTER TABLE hoặc các lệnh tạo index. Tuy nhiên, cần cân nhắc khả năng rollback và khác biệt giữa các database.

Ví dụ:

~~~java
@Sql(
        scripts = "classpath:/sql/schema/create-test-table.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
~~~

Một số hệ quản trị database tự commit hoặc có quy tắc transaction đặc biệt với DDL. Vì vậy, không nên giả định mọi DDL đều rollback cùng test transaction.

Với schema dùng chung cho nhiều test, thường nên dùng schema initialization hoặc migration tool trong bước chuẩn bị môi trường. @Sql phù hợp hơn với dữ liệu test và các thay đổi schema rất cụ thể cho một nhóm test.

Nếu script tạo bảng tạm hoặc object riêng, hãy xác định cách xóa chúng. Một số database hỗ trợ temporary table theo connection hoặc transaction; hành vi có thể khác nhau giữa H2, PostgreSQL, MySQL và các hệ quản trị khác.

## 14. Dùng @Sql để kiểm tra migration và dữ liệu đặc biệt

@Sql có thể giúp chuẩn bị dữ liệu ở các trạng thái khó tạo qua API:

- Bản ghi legacy thiếu một trường mới.
- Dữ liệu ở trạng thái chờ xử lý.
- Quan hệ nhiều-nhiều với nhiều bản ghi liên quan.
- Giá trị biên về ngày tháng, số tiền hoặc trạng thái.
- Dữ liệu cần vi phạm constraint để kiểm tra lỗi.
- Bản ghi có timestamp hoặc id xác định.

Ví dụ, để kiểm tra code đọc dữ liệu legacy:

~~~sql
INSERT INTO customer (
    id,
    name,
    email,
    created_at
)
VALUES (
    301,
    'Legacy Customer',
    'legacy@example.test',
    TIMESTAMP '2020-01-01 00:00:00'
);
~~~

Test có thể xác minh ứng dụng xử lý đúng bản ghi cũ. Cú pháp literal timestamp có thể khác theo database; nếu cần tương thích nhiều hệ quản trị, hãy dùng cú pháp phù hợp hoặc một data builder qua JDBC.

Với migration, nên phân biệt:
- Test migration xác minh schema và dữ liệu sau khi chạy migration.
- Test repository xác minh truy vấn trên schema đã được chuẩn bị.
- @Sql seed data tạo trạng thái đầu vào cho từng test.

Không nên dùng một script seed để thay thế việc kiểm tra migration nếu mục tiêu là bảo đảm migration production chạy đúng.

## 15. Quản lý dữ liệu để test có thể chạy độc lập

Một script @Sql tốt cần có tính lặp lại và không phụ thuộc vào test khác.

Các nguyên tắc quan trọng:

**Dùng ID và dữ liệu xác định**

Chọn id, email hoặc mã nghiệp vụ riêng cho test để assertion dễ đọc và tránh va chạm với dữ liệu khác.

**Xóa theo phạm vi test**

Ưu tiên DELETE theo id hoặc key riêng của test. Tránh DELETE toàn bảng nếu database có thể được dùng chung bởi nhiều test chạy song song.

**Tuân thủ foreign key**

Xóa bảng con trước bảng cha; insert bảng cha trước bảng con. Điều này tránh lỗi constraint và làm script dễ dự đoán.

**Không phụ thuộc thứ tự test**

Mỗi test phải tự chuẩn bị dữ liệu cần thiết. Không để test B dựa vào script chỉ chạy trong test A.

**Cẩn thận với chạy song song**

Nếu nhiều test cùng dùng một id hoặc cùng xóa dữ liệu trong một bảng, chúng có thể can thiệp lẫn nhau. Dùng key riêng cho từng test hoặc database/schema riêng cho worker.

**Chọn transaction mode có chủ đích**

INFERRED thường phù hợp khi script cần tham gia transaction của test. ISOLATED chỉ nên dùng khi cần commit riêng và có cleanup tương ứng.

**Không dùng dữ liệu production thật**

Seed data nên là dữ liệu giả, không chứa thông tin cá nhân hoặc secret thật. Test cần tái hiện cấu trúc dữ liệu, không cần sao chép dữ liệu nhạy cảm.

## 16. @Sql và dữ liệu được tạo bởi ứng dụng

Không phải mọi test đều nên dùng SQL để seed dữ liệu. Có hai cách tiếp cận:

- Dùng SQL khi cần kiểm soát trực tiếp trạng thái database hoặc tạo dữ liệu phức tạp.
- Dùng repository/service hoặc test data builder khi muốn tạo dữ liệu thông qua API của ứng dụng.

SQL trực tiếp có ưu điểm là ngắn và chính xác đối với trạng thái database. Nhưng nó có thể bỏ qua validation, default value hoặc logic nghiệp vụ được thực hiện ở service.

Ví dụ, nếu muốn kiểm tra quy trình tạo khách hàng, hãy gọi service hoặc API tạo khách hàng để xác minh logic đó. Nếu muốn kiểm tra truy vấn tìm khách hàng theo trạng thái, @Sql seed dữ liệu trực tiếp là phù hợp.

Một test có thể dùng kết hợp:
- @Sql tạo dữ liệu nền phức tạp.
- Service tạo object chính đang được kiểm tra.
- Repository đọc lại dữ liệu để xác minh persistence.

Hãy chọn cách setup dựa trên hành vi đang kiểm tra. Không dùng SQL để tạo chính trạng thái mà test cần chứng minh ứng dụng có thể tạo ra.

## 17. Những lỗi thường gặp khi dùng @Sql

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy file SQL | Sai classpath hoặc tên file | Đặt trong src/test/resources và dùng classpath:/... |
| SQL chạy nhưng không có dữ liệu khi assertion | Script chạy trên DataSource khác hoặc transaction đã rollback | Kiểm tra DataSource, transaction manager và phase |
| Duplicate key | Script được chạy nhiều lần hoặc dữ liệu cũ còn tồn tại | Dùng dữ liệu riêng, cleanup đúng cách hoặc script idempotent |
| Vi phạm foreign key | Sai thứ tự xóa/chèn bảng | Xóa child trước parent, insert parent trước child |
| Method-level script không chạy cùng class-level script | Mặc định method-level @Sql override class-level | Dùng @SqlMergeMode(MERGE) nếu cần hợp nhất |
| Script lỗi vì separator | Stored procedure có dấu chấm phẩy bên trong | Cấu hình separator riêng trong @SqlConfig |
| Ký tự tiếng Việt bị lỗi | Encoding không thống nhất | Lưu UTF-8 và khai báo encoding khi cần |
| Lệnh cleanup không xóa dữ liệu | Cleanup chạy trong transaction bị rollback hoặc dùng DataSource khác | Kiểm tra phase, transactionMode và transaction manager |
| Test chạy riêng xanh nhưng chạy song song lỗi | Dùng chung ID hoặc DELETE toàn bảng | Cô lập key, schema hoặc database |
| Script tiếp tục sau câu SQL lỗi | ErrorMode cho phép tiếp tục | Dùng chế độ mặc định/fail-fast khi dữ liệu setup bắt buộc |
| Không tìm thấy transaction manager | Context có nhiều hoặc thiếu manager phù hợp | Chỉ rõ transactionManager trong @SqlConfig |

Khi debug, hãy xác minh theo thứ tự:

1. Resource SQL có được tìm thấy không?
2. Script có được chạy ở phase mong muốn không?
3. Script đang dùng DataSource nào?
4. Có transaction nào đang hoạt động?
5. Transaction mode có phải ISOLATED không?
6. Lệnh có thực sự commit không?
7. Assertion đang đọc từ cùng database/schema không?
8. Dữ liệu có bị cleanup hoặc rollback trước assertion không?

Không nên sửa bằng cách tắt toàn bộ transaction hoặc bỏ qua mọi lỗi SQL nếu chưa xác định nguyên nhân.

## 18. Ví dụ kết hợp setup và cleanup với hai phase

Một test có thể dùng script riêng cho setup và cleanup:

~~~java
@SpringBootTest
class InventoryRepositoryTest {

    @Autowired
    private InventoryRepository inventoryRepository;

    @Test
    @Sql(
            scripts = "classpath:/sql/inventory/seed-item.sql",
            executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
    )
    @Sql(
            scripts = "classpath:/sql/inventory/cleanup-item.sql",
            executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
    )
    void shouldFindInventoryItem() {
        var item = inventoryRepository.findBySku("SKU-TEST-1");

        assertTrue(item.isPresent());
        assertEquals(20, item.get().getQuantity());
    }
}
~~~

Script setup:

~~~sql
DELETE FROM inventory WHERE sku = 'SKU-TEST-1';

INSERT INTO inventory (id, sku, quantity)
VALUES (9001, 'SKU-TEST-1', 20);
~~~

Script cleanup:

~~~sql
DELETE FROM inventory WHERE sku = 'SKU-TEST-1';
~~~

Ví dụ này minh họa dữ liệu có key riêng. Trong ứng dụng thực tế, nếu test method được quản lý trong transaction và script setup tham gia transaction đó, rollback có thể đã đủ để dọn dữ liệu. Cleanup script vẫn có ích khi dữ liệu được commit riêng hoặc test có side effect nằm ngoài transaction.

Nếu dùng transaction độc lập cho cleanup, cấu hình ISOLATED một cách có chủ đích và xác minh rằng nó trỏ tới đúng database.

## 19. Khi nào dùng script, khi nào dùng statements?

| Tiêu chí | scripts | statements |
|---|---|---|
| Số lượng SQL | Nhiều câu hoặc nhiều bảng | Một vài câu ngắn |
| Khả năng tái sử dụng | Cao, dùng chung nhiều test | Thường gắn với một test |
| Dễ review dữ liệu | File riêng, dễ xem toàn bộ | Xem ngay tại annotation |
| Comment và format SQL | Linh hoạt | Bị giới hạn bởi chuỗi Java |
| Cấu hình parser | Có thể cấu hình qua @SqlConfig | Thường ít cần tùy chỉnh |
| Phù hợp với DDL hoặc seed phức tạp | Phù hợp | Khó bảo trì nếu quá dài |
| Tình huống điển hình | Seed nhiều bảng, setup/cleanup | Chèn một bản ghi đơn giản |

Quy tắc thực tế:

- Dùng statements nếu có một hoặc hai lệnh ngắn và dữ liệu chỉ phục vụ method hiện tại.
- Dùng scripts nếu SQL dài, nhiều bảng, được dùng lại hoặc cần comment.
- Dùng @SqlMergeMode khi cần kết hợp dữ liệu nền cấp class và dữ liệu riêng cấp method.
- Dùng @SqlConfig khi cần chọn DataSource, transaction manager, encoding, separator hoặc error mode.
- Dùng JDBC/JPA fixture builder khi dữ liệu cần tham số động hoặc cần chạy qua logic của ứng dụng.

## 20. Giới hạn và lưu ý về database

SQL trong @Sql được thực thi trên database thực tế của test. Vì vậy, cú pháp SQL phụ thuộc hệ quản trị đang sử dụng.

Một script chạy được trên H2 chưa chắc chạy được trên PostgreSQL hoặc MySQL do khác biệt về:

- Kiểu dữ liệu.
- Cú pháp identity/sequence.
- Cách viết timestamp.
- Hàm SQL và JSON.
- Constraint và index.
- Cú pháp stored procedure.
- Hành vi transaction của DDL.

Nếu ứng dụng production dùng PostgreSQL, hãy cân nhắc chạy repository integration test với PostgreSQL Testcontainers. Điều này giúp script kiểm thử phản ánh đúng dialect và constraint của hệ quản trị mục tiêu.

Ngoài ra:

- Tránh hard-code schema hoặc tên database phụ thuộc môi trường.
- Dùng dữ liệu test giả và key riêng.
- Không trỏ script test vào database production.
- Không dùng lệnh phá hủy rộng như DROP DATABASE trong script test.
- Cẩn thận với sequence sau khi insert ID thủ công; có thể cần cập nhật sequence theo cách phù hợp với database.
- Xác minh timezone và locale nếu script chứa ngày giờ hoặc dữ liệu phụ thuộc môi trường.

## 21. Quy trình áp dụng @Sql trong dự án

Khi thêm @Sql cho một bài test, có thể thực hiện theo các bước:

1. Xác định trạng thái database cần có trước test.
2. Chọn script nếu dữ liệu dài hoặc được dùng lại; chọn statements nếu chỉ có vài câu đơn giản.
3. Đặt file SQL trong test resources và dùng classpath path rõ ràng.
4. Chọn executionPhase phù hợp: BEFORE_TEST_METHOD cho setup, AFTER_TEST_METHOD cho cleanup.
5. Nếu có @Sql ở cấp class và method, xác định có cần @SqlMergeMode(MERGE) hay không.
6. Kiểm tra DataSource và transaction manager được chọn.
7. Chọn INFERRED hoặc ISOLATED dựa trên transaction boundary cần kiểm tra.
8. Dùng key riêng và thứ tự insert/delete phù hợp với foreign key.
9. Chạy test riêng và cả test suite để phát hiện phụ thuộc dữ liệu.
10. Nếu dùng nhiều database hoặc chạy song song, cô lập schema và dữ liệu giữa các test.

Một script tốt phải có thể chạy lặp lại trong phạm vi dữ liệu test và không phụ thuộc vào test khác. Hãy xem SQL setup là một phần của fixture, có trách nhiệm rõ ràng và được đặt đúng vòng đời.

## 22. Kết luận

@Sql giúp Spring TestContext chuẩn bị hoặc dọn dữ liệu database bằng file SQL hoặc câu lệnh inline.

- Dùng scripts cho SQL dài, nhiều bảng hoặc có thể tái sử dụng.
- Dùng statements cho một số lệnh ngắn gắn với test method.
- BEFORE_TEST_METHOD là phase mặc định; AFTER_TEST_METHOD phù hợp với cleanup.
- @Sql cấp class và method mặc định có quy tắc override; dùng @SqlMergeMode(MERGE) khi cần hợp nhất.
- @SqlConfig điều khiển DataSource, transaction manager, encoding, separator và error handling.
- INFERRED là mặc định và có thể tham gia transaction của test; ISOLATED chạy script trong transaction riêng được commit độc lập.
- Rollback của test không hoàn tác dữ liệu đã commit riêng hoặc side effect chạy ngoài transaction.
- Dữ liệu cần có key riêng, thứ tự SQL đúng với foreign key và không phụ thuộc thứ tự chạy test.

Khi lựa chọn đúng giữa script và statements, hiểu rõ phase và transaction mode, @Sql giúp các bài kiểm thử database có dữ liệu đầu vào xác định, dễ đọc và có thể chạy lặp lại trong môi trường CI.


# ExecutionPhase để chạy trước hoặc sau kiểm thử

Trong kiểm thử tích hợp với Spring, dữ liệu ban đầu thường được chuẩn bị bằng SQL: tạo bản ghi mẫu, đặt trạng thái cần kiểm tra hoặc dựng một tập dữ liệu cố định. Sau khi test chạy xong, có thể cần dọn dữ liệu hoặc xác nhận trạng thái đã được lưu. Spring Test cung cấp `@Sql` để thực thi script SQL và `ExecutionPhase` để chọn thời điểm thực thi trong vòng đời test.

`ExecutionPhase` có bốn giá trị: `BEFORE_TEST_METHOD`, `AFTER_TEST_METHOD`, `BEFORE_TEST_CLASS` và `AFTER_TEST_CLASS`. Hai phase theo method cho phép chuẩn bị hoặc dọn dữ liệu quanh từng test method. Hai phase theo class cho phép thiết lập một lần trước toàn bộ test class và dọn một lần sau khi tất cả test method hoàn tất. Việc chọn đúng phase giúp tránh chạy lại SQL không cần thiết và làm rõ vòng đời của dữ liệu kiểm thử.

## 1. @Sql và ExecutionPhase

`@Sql` thuộc package `org.springframework.test.context.jdbc`:

```java
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.Sql.ExecutionPhase;
```

Annotation có thể khai báo trên test method hoặc test class. Nó cho Spring Test biết script nào cần chạy và ở phase nào. Ví dụ đơn giản:

```java
@Test
@Sql(
        scripts = "/sql/insert-customer.sql",
        executionPhase = ExecutionPhase.BEFORE_TEST_METHOD
)
void findsCustomer() {
    // Test runs after the SQL fixture has been applied.
}
```

Nếu không chỉ định `executionPhase`, giá trị mặc định là `BEFORE_TEST_METHOD`. Do đó, `@Sql(scripts = "/sql/insert-customer.sql")` trên method sẽ chạy script trước method đó.

`@Sql` được thực thi bởi `SqlScriptsTestExecutionListener` trong Spring TestContext Framework. Listener này đọc script từ test classpath, chọn `DataSource` và transaction manager phù hợp, rồi thực thi SQL theo cấu hình. `ExecutionPhase` điều khiển thời điểm listener chạy script; nó không tự tạo dữ liệu và cũng không quyết định toàn bộ transaction semantics. Phần transaction được điều khiển thêm bởi `@SqlConfig` và transaction context của test.

## 2. Bốn phase của ExecutionPhase

| Phase | Thời điểm | Tần suất thông thường | Mục đích điển hình |
|---|---|---|---|
| `BEFORE_TEST_METHOD` | Trước mỗi test method | Mỗi method có khai báo hoặc kế thừa cấu hình tương ứng | Nạp fixture riêng cho test |
| `AFTER_TEST_METHOD` | Sau mỗi test method | Sau từng method | Dọn dữ liệu hoặc thực hiện SQL hậu kiểm |
| `BEFORE_TEST_CLASS` | Trước các test method của class | Một lần cho test class | Tạo schema hoặc nạp dữ liệu dùng chung |
| `AFTER_TEST_CLASS` | Sau khi các test method của class hoàn tất | Một lần cho test class | Xóa schema hoặc dọn dữ liệu dùng chung |

`BEFORE_TEST_METHOD` và `AFTER_TEST_METHOD` có từ các phiên bản Spring Test trước. `BEFORE_TEST_CLASS` và `AFTER_TEST_CLASS` được bổ sung trong Spring Framework 6.1. Hai phase theo class chỉ được dùng trên khai báo `@Sql` ở cấp class; không đặt chúng trên một method riêng lẻ.

Hai phase theo class không có nghĩa SQL chạy một lần cho toàn bộ test suite. Nếu nhiều test class cùng khai báo script class-level, script sẽ được thực hiện theo vòng đời của từng class. Việc cache `ApplicationContext` giữa các test class không biến `BEFORE_TEST_CLASS` thành phase một lần cho toàn bộ context.

## 3. BEFORE_TEST_METHOD: chuẩn bị dữ liệu trước mỗi test

Đây là phase mặc định và thường dùng nhất. Mỗi test method có thể nhận một tập dữ liệu xác định trước khi thực thi.

Ví dụ, file `src/test/resources/sql/insert-customer.sql`:

```sql
INSERT INTO customer (id, email, status)
VALUES (101, 'lan@example.test', 'ACTIVE');
```

Test repository:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.test.context.jdbc.Sql;

import static org.assertj.core.api.Assertions.assertThat;

@JdbcTest
class CustomerRepositoryTests {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    @Sql("/sql/insert-customer.sql")
    void findsCustomerByEmail() {
        var customer = customerRepository.findByEmail("lan@example.test");

        assertThat(customer).isPresent();
        assertThat(customer.orElseThrow().getStatus()).isEqualTo("ACTIVE");
    }
}
```

Vì không khai báo phase, Spring chạy `insert-customer.sql` trước method `findsCustomerByEmail()`. `@JdbcTest` tạo test slice cho JDBC và mặc định chạy test trong transaction được rollback sau method, nên fixture được tạo trong transaction test thường không tồn tại sau khi test kết thúc.

Phase này phù hợp khi mỗi test cần một bộ dữ liệu độc lập. Nếu một class có nhiều method với dữ liệu khác nhau, khai báo `@Sql` trên từng method giúp người đọc biết rõ dữ liệu nào phục vụ test nào.

## 4. AFTER_TEST_METHOD: chạy SQL sau mỗi test method

`AFTER_TEST_METHOD` chạy sau khi test method hoàn tất. Phase này thường dùng để dọn dữ liệu đã được tạo bên ngoài transaction test, hoặc thực hiện thao tác SQL hậu kiểm.

Ví dụ:

```java
@Test
@Sql(scripts = "/sql/insert-customer.sql")
@Sql(
        scripts = "/sql/delete-test-customer.sql",
        executionPhase = ExecutionPhase.AFTER_TEST_METHOD
)
void findsCustomerByEmail() {
    // Exercise the repository using the inserted customer.
}
```

File `delete-test-customer.sql`:

```sql
DELETE FROM customer
WHERE email = 'lan@example.test';
```

Khai báo này làm rõ ý định chuẩn bị và dọn fixture quanh method. Tuy nhiên, cần xét transaction của test trước khi kết luận câu lệnh `DELETE` sẽ được commit. Với transactional test, script ở phase `AFTER_TEST_METHOD` thường được thực thi khi test-managed transaction vẫn đang hoạt động. Nếu SQL cleanup tham gia transaction đó, nó có thể bị rollback cùng transaction khi Spring kết thúc test.

Điều này không nhất thiết gây vấn đề. Nếu fixture được insert trong chính test transaction và transaction bị rollback, bản ghi cũng tự biến mất; cleanup riêng có thể không cần thiết. Nhưng nếu dữ liệu được commit độc lập trước test hoặc được tạo bởi `REQUIRES_NEW`, cleanup cần chạy trong transaction độc lập để thay đổi được lưu lại.

## 5. BEFORE_TEST_CLASS: chuẩn bị một lần cho cả class

Từ Spring Framework 6.1, có thể đặt `@Sql` ở cấp class với `BEFORE_TEST_CLASS` để chạy script một lần trước các test method trong class.

Ví dụ tạo schema hoặc dữ liệu tham chiếu dùng chung:

```java
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.Sql.ExecutionPhase;

@SpringBootTest
@Sql(
        scripts = {
                "/sql/create-test-schema.sql",
                "/sql/insert-reference-data.sql"
        },
        executionPhase = ExecutionPhase.BEFORE_TEST_CLASS
)
class OrderIntegrationTests {

    @Test
    void createsOrderForExistingCustomer() {
        // Uses schema and reference data prepared once for this class.
    }

    @Test
    void listsOrdersForExistingCustomer() {
        // Uses the same class-level setup.
    }
}
```

Các script trong mảng `scripts` được thực thi theo thứ tự khai báo, vì vậy có thể đặt script tạo schema trước script nạp dữ liệu phụ thuộc vào schema đó.

`BEFORE_TEST_CLASS` phù hợp với dữ liệu nền dùng chung, ví dụ bảng danh mục, cấu hình mẫu hoặc schema cần có trước khi mọi method chạy. Không nên đặt dữ liệu biến đổi theo từng test ở phase này nếu các method có thể làm thay đổi dữ liệu và ảnh hưởng lẫn nhau.

Phase class-level chạy ngoài test-managed transaction của từng method, vì transaction của method chưa bắt đầu. Do đó, nếu script cần transaction, `SqlScriptsTestExecutionListener` sẽ xử lý theo `@SqlConfig` và transaction manager được chọn. Với cấu hình mặc định và transaction manager phù hợp, script có thể được chạy trong transaction riêng và commit trước khi các method bắt đầu.

## 6. AFTER_TEST_CLASS: dọn dữ liệu sau toàn bộ class

`AFTER_TEST_CLASS` chạy một lần sau khi tất cả test method trong class đã hoàn tất. Đây là vị trí phù hợp để xóa dữ liệu dùng chung hoặc loại bỏ schema được tạo ở phase `BEFORE_TEST_CLASS`.

Ví dụ:

```java
@SpringBootTest
@Sql(
        scripts = "/sql/create-test-schema.sql",
        executionPhase = ExecutionPhase.BEFORE_TEST_CLASS
)
@Sql(
        scripts = "/sql/drop-test-schema.sql",
        executionPhase = ExecutionPhase.AFTER_TEST_CLASS,
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
class OrderIntegrationTests {
    // All test methods use the schema created before the class.
}
```

File `drop-test-schema.sql` có thể chứa:

```sql
DROP SCHEMA IF EXISTS order_test CASCADE;
```

Ví dụ giả định test có quyền tạo và xóa schema riêng. Trong dự án thực tế, cần bảo đảm script chỉ tác động schema/database được dành riêng cho test. Không dùng script drop trên database dùng chung với dữ liệu ngoài phạm vi test.

`AFTER_TEST_CLASS` hữu ích khi muốn dọn tài nguyên SQL cấp class. Tuy nhiên, nó không thay thế việc quản lý vòng đời container hoặc server bên ngoài. Nếu test dùng Testcontainers, hãy để Testcontainers quản lý container và dùng SQL phase cho dữ liệu/schema bên trong database.

## 7. Phạm vi khai báo: method-level và class-level

`@Sql` có thể được khai báo ở cấp class hoặc method. Cần phân biệt phạm vi khai báo với execution phase:

- Class-level `@Sql` với phase mặc định `BEFORE_TEST_METHOD` sẽ áp dụng script trước mỗi test method trong class.
- Class-level `@Sql` với `BEFORE_TEST_CLASS` chỉ chạy một lần trước các method của class.
- Method-level `@Sql` mặc định chạy trước method đó.
- Method-level `@Sql` có thể chọn `AFTER_TEST_METHOD` để chạy sau method.

Ví dụ class-level fixture được chạy trước từng method:

```java
@SpringBootTest
@Sql("/sql/common-reference-data.sql")
class CatalogIntegrationTests {

    @Test
    void findsCategory() {
    }

    @Test
    void listsCategories() {
    }
}
```

Vì phase mặc định là `BEFORE_TEST_METHOD`, script `common-reference-data.sql` được chạy trước từng method, không phải chỉ một lần cho class. Nếu dữ liệu chỉ cần nạp một lần, hãy chỉ định `BEFORE_TEST_CLASS`.

### 7.1. Class-level và method-level cùng tồn tại

Spring Test có `@SqlMergeMode` để quyết định cách kết hợp khai báo `@Sql` ở class và method. Mặc định, method-level `@Sql` dùng chế độ `OVERRIDE`, nghĩa là khai báo ở method thay thế khai báo class-level theo quy tắc merge của Spring Test.

Nếu muốn method-level script được bổ sung bên cạnh script class-level, có thể dùng:

```java
import org.springframework.test.context.jdbc.SqlMergeMode;

@SpringBootTest
@Sql("/sql/common-reference-data.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class CatalogIntegrationTests {

    @Test
    @Sql("/sql/insert-special-category.sql")
    void findsSpecialCategory() {
    }
}
```

Ở chế độ `MERGE`, cấu hình SQL cấp class và cấp method được kết hợp theo quy tắc của Spring Test. Điều này hữu ích khi mỗi method cần dữ liệu riêng nhưng vẫn cần fixture chung. Hãy chỉ định phase rõ ràng nếu các script cần chạy ở thời điểm khác nhau.

Khi dùng `BEFORE_TEST_CLASS` hoặc `AFTER_TEST_CLASS` cùng method-level SQL, cần đọc metadata và phase của từng khai báo để xác định chính xác script nào chạy một lần và script nào chạy quanh từng method. Nếu test phụ thuộc thứ tự setup/cleanup phức tạp, hãy tách các script và ghi phase rõ ràng thay vì dựa vào mặc định.

## 8. Nhiều script trong một @Sql và thứ tự thực thi

Thuộc tính `scripts` nhận một mảng resource. Có thể khai báo nhiều script trong một annotation:

```java
@Sql(
        scripts = {
                "/sql/01-create-schema.sql",
                "/sql/02-insert-users.sql",
                "/sql/03-insert-orders.sql"
        },
        executionPhase = ExecutionPhase.BEFORE_TEST_CLASS
)
class OrderRepositoryTests {
}
```

Cách viết này làm rõ thứ tự phụ thuộc: tạo schema trước, nạp user rồi mới nạp order. Nếu script sau tham chiếu dữ liệu do script trước tạo, thứ tự là một phần của fixture và cần được thể hiện rõ.

`@Sql` là annotation repeatable, nên có thể khai báo nhiều lần trên cùng class hoặc method. `@SqlGroup` cũng có thể dùng để nhóm nhiều khai báo, đặc biệt trong trường hợp cần cấu trúc annotation rõ ràng hoặc tương thích với cách khai báo annotation lồng nhau.

Ví dụ với `@SqlGroup`:

```java
@SqlGroup({
        @Sql(
                scripts = "/sql/insert-customer.sql",
                executionPhase = ExecutionPhase.BEFORE_TEST_METHOD
        ),
        @Sql(
                scripts = "/sql/delete-customer.sql",
                executionPhase = ExecutionPhase.AFTER_TEST_METHOD
        )
})
class CustomerSqlTests {
}
```

Với Java hiện đại, có thể dùng trực tiếp nhiều `@Sql` vì annotation hỗ trợ repeatable. Chọn cách viết giúp người đọc nhìn thấy thứ tự và phase dễ nhất.

## 9. Dùng statements thay cho file script

Ngoài `scripts`, `@Sql` có thuộc tính `statements` để khai báo SQL ngắn trực tiếp trong annotation:

```java
@Test
@Sql(
        statements = {
                "INSERT INTO customer(id, email) VALUES (201, 'minh@example.test')"
        },
        executionPhase = ExecutionPhase.BEFORE_TEST_METHOD
)
void findsCustomer() {
}
```

Có thể dùng `statements` ở phase sau để xóa một bản ghi:

```java
@Sql(
        statements = "DELETE FROM customer WHERE id = 201",
        executionPhase = ExecutionPhase.AFTER_TEST_METHOD
)
```

`statements` phù hợp với SQL ngắn, ít thay đổi. Với fixture dài, nhiều câu lệnh, dữ liệu dùng lại hoặc script có comment và cấu trúc phức tạp, file `.sql` thường dễ đọc và bảo trì hơn.

Không nên đặt dữ liệu nhạy cảm hoặc giá trị phụ thuộc môi trường vào script test dùng chung. Dùng dữ liệu giả định, ID rõ ràng và database test riêng để tránh ảnh hưởng dữ liệu thật.

## 10. Transaction của SQL script và @SqlConfig

Execution phase xác định thời điểm script chạy; transaction mode xác định script tham gia hoặc tạo transaction như thế nào. `@SqlConfig` cho phép cấu hình `DataSource`, transaction manager, encoding, comment prefix, separator và transaction mode.

Hai transaction mode thường cần hiểu là:

- `INFERRED`: Spring suy luận cách chạy dựa trên transaction hiện tại và transaction manager. Nếu có transaction đang hoạt động, script có thể tham gia transaction đó; nếu không, Spring dùng transaction manager phù hợp để chạy script trong transaction riêng khi có thể.
- `ISOLATED`: script được chạy trong một transaction độc lập với propagation `REQUIRES_NEW` và commit transaction đó khi hoàn tất.

Nếu không cấu hình khác, Spring Test sử dụng hành vi transaction mặc định tương ứng với `INFERRED`. Có thể cấu hình riêng cho một script:

```java
@Sql(
        scripts = "/sql/insert-reference-data.sql",
        executionPhase = ExecutionPhase.BEFORE_TEST_CLASS,
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
class OrderIntegrationTests {
}
```

Ở đây script được chạy trong transaction độc lập và commit trước khi test method bắt đầu. Các test method có thể sử dụng dữ liệu tham chiếu đã được commit.

### 10.1. Fixture tham gia transaction test

Với test method có `@Transactional`, script `BEFORE_TEST_METHOD` dùng transaction mode `INFERRED` thường tham gia test-managed transaction đang hoạt động. Nếu test kết thúc bằng rollback, fixture cũng rollback theo.

Điều này thường là lựa chọn tốt cho dữ liệu riêng của một method:

```java
@DataJpaTest
class CustomerRepositoryTests {

    @Test
    @Sql("/sql/insert-customer.sql")
    void readsCustomer() {
        // Setup and test participate in the test-managed transaction.
    }
}
```

Không cần thêm cleanup script chỉ để xóa dữ liệu được tạo trong cùng transaction nếu toàn bộ thao tác đều tham gia transaction đó và test rollback như dự kiến.

### 10.2. Khi nào cần ISOLATED?

Dùng `ISOLATED` khi dữ liệu phải được commit độc lập với transaction của test, hoặc khi cleanup phải tồn tại sau khi test transaction rollback. Ví dụ, một script class-level tạo dữ liệu tham chiếu cần được commit trước khi các method chạy; hoặc một test gọi code dùng `REQUIRES_NEW` tạo dữ liệu cần dọn bằng transaction độc lập.

Ví dụ cleanup độc lập:

```java
@Sql(
        scripts = "/sql/delete-committed-fixture.sql",
        executionPhase = ExecutionPhase.AFTER_TEST_METHOD,
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
```

Script cleanup chạy trong transaction riêng và commit. Hãy dùng cách này khi bản ghi cần xóa đã được commit và có thể nhìn thấy từ transaction độc lập. Nếu bản ghi chỉ tồn tại trong transaction test chưa commit, transaction độc lập khác không thể nhìn thấy nó; rollback của transaction test sẽ tự loại bỏ bản ghi đó.

### 10.3. Chỉ định DataSource và transaction manager

Nếu context có nhiều `DataSource` hoặc nhiều transaction manager, Spring có thể không suy luận được thành phần cần dùng. Có thể chỉ định trong `@SqlConfig`:

```java
@Sql(
        scripts = "/sql/seed-reporting-data.sql",
        config = @SqlConfig(
                dataSource = "reportingDataSource",
                transactionManager = "reportingTransactionManager",
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
```

Tên bean phải khớp với cấu hình trong application context. Nếu dùng sai datasource hoặc transaction manager, script có thể chạy trên database khác với nơi repository đang đọc dữ liệu.

## 11. Kết hợp phase với @Transactional

Để hiểu kết quả, cần xem thứ tự giữa test-managed transaction và SQL listener.

Với transactional test thông thường, Spring Test bắt đầu transaction cho method và chạy script `BEFORE_TEST_METHOD` theo transaction mode đã cấu hình. Sau test method, script `AFTER_TEST_METHOD` được xử lý trong lifecycle kết thúc method; với `INFERRED`, nó có thể tham gia transaction test vẫn đang hoạt động. Transactional listener sau đó kết thúc transaction theo chính sách commit/rollback của test.

Sơ đồ khái quát:

```text
BEFORE_TEST_METHOD
       |
       v
Test-managed transaction active (if @Transactional)
       |
       v
@Sql BEFORE_TEST_METHOD
       |
       v
JUnit test method and test callbacks
       |
       v
@Sql AFTER_TEST_METHOD
       |
       v
Commit or rollback test-managed transaction
```

Sơ đồ thể hiện luồng thường gặp khi SQL script dùng transaction mode `INFERRED` và test có transaction được quản lý bởi Spring. Khi dùng `ISOLATED`, script chạy trong transaction độc lập; nó không bị rollback cùng transaction test.

Class-level `BEFORE_TEST_CLASS` và `AFTER_TEST_CLASS` chạy ở vòng đời class, ngoài transaction test của từng method. Vì vậy, dữ liệu được tạo ở phase class có thể tồn tại xuyên suốt các method nếu script đã commit. Cần có cleanup tương ứng ở phase class hoặc cơ chế dọn dữ liệu khác.

Không nên suy luận rằng `AFTER_TEST_METHOD` luôn chạy sau khi rollback. Script `AFTER_TEST_METHOD` là một phần của Spring Test lifecycle; transaction listener mới quyết định thời điểm kết thúc test-managed transaction. Nếu mục tiêu là kiểm tra dữ liệu sau commit/rollback, dùng callback `@AfterTransaction` hoặc một transaction mới phù hợp thay vì chỉ dựa vào phase SQL after-method.

## 12. Chọn phase theo mục tiêu kiểm thử

| Mục tiêu | Phase phù hợp | Lý do |
|---|---|---|
| Nạp bản ghi riêng cho một method | `BEFORE_TEST_METHOD` | Mỗi method nhận fixture trước khi chạy |
| Xóa dữ liệu đã commit do method tạo ra | `AFTER_TEST_METHOD` | Cleanup ngay sau từng method |
| Tạo schema hoặc bảng dùng chung trong class | `BEFORE_TEST_CLASS` | Chạy một lần thay vì lặp lại trước từng method |
| Nạp dữ liệu danh mục bất biến dùng chung | `BEFORE_TEST_CLASS` | Các method cùng sử dụng một tập dữ liệu nền |
| Xóa schema hoặc dữ liệu nền sau class | `AFTER_TEST_CLASS` | Dọn một lần sau khi class hoàn tất |
| Kiểm tra một trạng thái ngay sau commit/rollback của test transaction | Callback `@AfterTransaction` hoặc transaction mới | SQL after-method có thể vẫn tham gia test transaction |

Ví dụ, một test repository thường chỉ cần `BEFORE_TEST_METHOD` để insert fixture và rollback mặc định. Một bộ integration test cần schema riêng cho cả class có thể dùng `BEFORE_TEST_CLASS` để tạo schema, sau đó `AFTER_TEST_CLASS` để drop schema. Một test xác nhận dữ liệu do `REQUIRES_NEW` commit có thể cần `AFTER_TEST_METHOD` với `ISOLATED` để cleanup.

## 13. Những lỗi thường gặp khi chọn ExecutionPhase

### 13.1. Nghĩ rằng class-level @Sql luôn chạy một lần

Class-level `@Sql` mặc định vẫn dùng `BEFORE_TEST_METHOD`, nên script có thể chạy trước mỗi method. Nếu chỉ muốn chạy một lần, hãy đặt `executionPhase = BEFORE_TEST_CLASS`.

### 13.2. Dùng phase theo class trên method-level annotation

`BEFORE_TEST_CLASS` và `AFTER_TEST_CLASS` dành cho khai báo `@Sql` ở cấp class. Nếu đặt chúng trên method, cấu hình không hợp lệ. Hãy chuyển annotation lên class hoặc dùng phase theo method.

### 13.3. Dùng AFTER_TEST_METHOD để kiểm tra sau rollback

Script `AFTER_TEST_METHOD` không mặc nhiên chạy sau khi transaction test đã rollback. Với `INFERRED`, script có thể tham gia transaction đang hoạt động và bị rollback cùng test. Dùng `@AfterTransaction` hoặc một transaction độc lập nếu cần xác nhận trạng thái hậu rollback.

### 13.4. Cleanup bị rollback cùng test

Nếu cleanup SQL tham gia transaction test, các câu lệnh delete có thể bị rollback. Điều này không ảnh hưởng fixture cùng transaction nhưng không dọn được dữ liệu đã commit độc lập. Cân nhắc `ISOLATED` khi cần cleanup được commit.

### 13.5. Dùng ISOLATED cho mọi script

Mỗi script isolated transaction có thể commit độc lập và để lại dữ liệu ngay cả khi test thất bại. Việc này làm tăng yêu cầu cleanup và có thể gây ảnh hưởng giữa các test. Chỉ dùng `ISOLATED` khi cần transaction riêng.

### 13.6. Nạp dữ liệu dùng chung trước từng method

Nếu class-level script insert một bản ghi có khóa cố định và chạy trước từng method, method thứ hai có thể gặp duplicate key vì method đầu đã commit hoặc dữ liệu không nằm trong cùng transaction. Hãy quyết định rõ dữ liệu đó cần được tạo một lần ở class phase hay được rollback riêng cho từng method.

### 13.7. Chọn nhầm DataSource

Ứng dụng nhiều datasource có thể khiến SQL script chạy vào database khác với repository. Dùng `@SqlConfig(dataSource = ...)` và `transactionManager = ...` khi cần xác định rõ.

### 13.8. Đường dẫn resource không đúng

Script được nạp từ classpath hoặc vị trí được chỉ định. Với resource trong `src/test/resources/sql`, thường dùng `/sql/file-name.sql`. Kiểm tra tên file, chữ hoa/chữ thường và test runtime classpath nếu Spring báo không tìm thấy script.

### 13.9. Nhầm phase class với context cache

Spring có thể cache `ApplicationContext`, nhưng `BEFORE_TEST_CLASS` vẫn là phase của từng test class. Không dùng context cache như một bảo đảm rằng script chỉ chạy một lần cho cả suite.

## 14. Quy trình thiết kế SQL fixture

Khi thiết kế script cho một test class, hãy xác định vòng đời của dữ liệu trước:

1. **Dữ liệu cần thiết cho một method hay cả class?** Nếu chỉ phục vụ một method, dùng `BEFORE_TEST_METHOD`; nếu dùng chung, cân nhắc `BEFORE_TEST_CLASS`.
2. **Dữ liệu có cần commit độc lập không?** Nếu fixture phải tồn tại ngoài transaction test, cân nhắc `ISOLATED`; nếu không, để `INFERRED` tham gia transaction hiện tại.
3. **Test có transaction không?** Kiểm tra `@Transactional` hoặc annotation test slice như `@JdbcTest`/`@DataJpaTest`.
4. **Có cần cleanup tường minh không?** Dữ liệu cùng transaction thường được rollback; dữ liệu đã commit hoặc được tạo ngoài transaction cần cleanup riêng.
5. **Cleanup chạy ở đâu?** Dùng `AFTER_TEST_METHOD` cho dữ liệu theo method, `AFTER_TEST_CLASS` cho dữ liệu dùng chung cấp class. Dùng `ISOLATED` nếu cleanup phải commit độc lập.
6. **Có nhiều datasource không?** Chỉ định datasource và transaction manager qua `@SqlConfig` khi Spring không thể suy luận chính xác.
7. **Class và method có nhiều khai báo SQL không?** Kiểm tra `@SqlMergeMode` để biết khai báo method override hay merge với class.
8. **Xác nhận trạng thái ở đúng thời điểm.** Nếu cần kiểm tra sau commit/rollback, dùng callback hoặc transaction mới; không chỉ kiểm tra ngay trong test method.

Một bộ test ổn định thường dùng fixture method-level trong transaction test và rollback mặc định. Chỉ đưa dữ liệu lên phase class khi thực sự có dữ liệu dùng chung hoặc cần chuẩn bị schema. Script cleanup cần phản ánh nơi dữ liệu được tạo và transaction đã commit hay chưa.

## 15. Ví dụ tổng hợp: schema cấp class và fixture cấp method

Một test class có thể kết hợp setup cấp class với dữ liệu riêng từng method:

```java
@SpringBootTest
@Sql(
        scripts = "/sql/create-order-test-schema.sql",
        executionPhase = ExecutionPhase.BEFORE_TEST_CLASS
)
@Sql(
        scripts = "/sql/drop-order-test-schema.sql",
        executionPhase = ExecutionPhase.AFTER_TEST_CLASS,
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
class OrderRepositoryIntegrationTests {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    @Sql("/sql/insert-pending-order.sql")
    void findsPendingOrder() {
        assertThat(orderRepository.findByStatus("PENDING")).isNotEmpty();
    }

    @Test
    @Sql("/sql/insert-completed-order.sql")
    void findsCompletedOrder() {
        assertThat(orderRepository.findByStatus("COMPLETED")).isNotEmpty();
    }
}
```

Ví dụ minh họa cách phân chia phase: schema được tạo một lần trước class; mỗi method nạp fixture riêng trước khi chạy; schema được dọn sau class. Trong dự án thực tế, cần điều chỉnh transaction mode, tên schema và cách tạo datasource theo database test đang sử dụng. Nếu method dùng test-managed transaction rollback, fixture method-level có thể được rollback tự động. Nếu schema được tạo ở transaction riêng và cần xóa sau cùng, cleanup class-level phải chạy trong transaction phù hợp.

`ExecutionPhase` giúp đặt SQL fixture đúng vị trí trong vòng đời kiểm thử. Dùng `BEFORE_TEST_METHOD` và `AFTER_TEST_METHOD` cho dữ liệu riêng từng method; dùng `BEFORE_TEST_CLASS` và `AFTER_TEST_CLASS` để chuẩn bị hoặc dọn tài nguyên SQL dùng chung trong một class. Kết hợp phase với `@SqlConfig` và hiểu transaction mode `INFERRED`/`ISOLATED` để biết dữ liệu được rollback hay commit. Khi cần xác nhận trạng thái sau khi transaction test kết thúc, hãy dùng `@AfterTransaction` hoặc một transaction mới thay vì giả định SQL after-method luôn chạy sau rollback.

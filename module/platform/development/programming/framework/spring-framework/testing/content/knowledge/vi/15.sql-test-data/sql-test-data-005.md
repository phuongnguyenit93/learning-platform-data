# `@SqlConfig`: encoding, dấu phân cách và xử lý lỗi

Spring Test cho phép chạy SQL script trước hoặc sau một test method bằng `@Sql`. Cách này thường được dùng để tạo schema, nạp dữ liệu mẫu hoặc dọn dữ liệu sau khi kiểm thử repository và service. Khi script có tiếng Việt hoặc ký tự ngoài ASCII, chứa stored procedure với nhiều dấu chấm phẩy, hoặc chạy trên database có cú pháp comment riêng, cấu hình mặc định có thể không còn phù hợp.

`@SqlConfig` cung cấp các tùy chọn để kiểm soát cách Spring đọc và thực thi script: encoding của file, dấu phân cách giữa các câu lệnh, tiền tố comment, dấu comment nhiều dòng, datasource, transaction manager, transaction mode và cách xử lý lỗi SQL. Cấu hình đúng giúp test đọc script nhất quán trên máy developer và CI, đồng thời tránh tình huống setup thất bại nhưng test vẫn tiếp tục với dữ liệu không đầy đủ.

## 1. `@Sql` và `@SqlConfig` phối hợp như thế nào?

`@Sql` khai báo SQL script hoặc câu lệnh SQL cần thực thi trong test. Ví dụ:

```java
@SpringBootTest
@Sql("/db/test-data.sql")
class CustomerRepositoryTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    void findsCustomerInsertedByScript() {
        assertThat(customers.findByEmail("lan@example.test")).isPresent();
    }
}
```

Script được đặt trong test classpath, ví dụ `src/test/resources/db/test-data.sql`. `@Sql` mặc định chạy script trước mỗi test method (`BEFORE_TEST_METHOD`).

`@SqlConfig` cấu hình cách Spring đọc và thực thi các script. Có hai phạm vi sử dụng phổ biến:

- **Cấu hình toàn cục cho test class:** đặt `@SqlConfig` trực tiếp trên class. Các thuộc tính áp dụng cho những `@Sql` trong class và phạm vi kế thừa tương ứng.
- **Cấu hình cục bộ cho một nhóm script:** đặt `@SqlConfig` trong thuộc tính `config` của một `@Sql`. Cấu hình cục bộ chỉ áp dụng cho script được khai báo ở `@Sql` đó và có thể ghi đè cấu hình toàn cục.

Ví dụ cấu hình toàn cục:

```java
@SpringBootTest
@SqlConfig(
        encoding = "UTF-8",
        separator = ";",
        commentPrefixes = {"--"},
        errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR)
class CustomerRepositoryTest {
    @Test
    @Sql("/db/customers.sql")
    void loadsCustomerFixture() {
        // Script dùng cấu hình chung của class.
    }
}
```

Ví dụ cấu hình cục bộ:

```java
@Test
@Sql(
        scripts = "/db/create-procedure.sql",
        config = @SqlConfig(
                encoding = "UTF-8",
                separator = "@@",
                errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR))
void createsProcedureWithCustomDelimiter() {
    // Chỉ script này dùng separator @@.
}
```

Khi cấu hình một thuộc tính ở cả hai phạm vi, giá trị cục bộ được dùng cho `@Sql` tương ứng. Các thuộc tính không được override tiếp tục nhận cấu hình toàn cục hoặc giá trị mặc định của Spring.

## 2. Encoding: đọc SQL script đúng bảng mã

Thuộc tính `encoding` chỉ định charset Spring sử dụng khi đọc nội dung file SQL. Nếu không khai báo, Spring sử dụng encoding mặc định của nền tảng. Encoding mặc định có thể khác giữa máy developer, container CI và hệ điều hành, vì vậy script chứa ký tự ngoài ASCII nên khai báo rõ.

Ví dụ script có dữ liệu tiếng Việt:

```sql
INSERT INTO customer (id, full_name, city)
VALUES (101, 'Nguyễn Thị Lan', 'Thành phố Hồ Chí Minh');
```

Nếu file được lưu bằng UTF-8, khai báo:

```java
@SqlConfig(encoding = "UTF-8")
```

Hoặc đặt cấu hình cho một script:

```java
@Sql(
        scripts = "/db/vietnamese-fixtures.sql",
        config = @SqlConfig(encoding = "UTF-8"))
```

Tên charset được truyền dưới dạng chuỗi theo tên charset Java, chẳng hạn `UTF-8`, `UTF-16` hoặc một charset được JVM hỗ trợ. Trong dự án hiện đại, UTF-8 thường là lựa chọn phù hợp cho file SQL lưu trong Git.

### 2.1. Encoding của file phải khớp với cấu hình

Chỉ khai báo `encoding = "UTF-8"` không tự chuyển đổi nội dung file. File thực tế cũng phải được lưu bằng UTF-8. Nếu file được lưu bằng Windows-1258 nhưng Spring đọc như UTF-8, dữ liệu tiếng Việt có thể bị lỗi ký tự hoặc SQL literal không còn đúng.

Khi gặp lỗi encoding:

1. Kiểm tra encoding thực tế của file trong editor hoặc công cụ kiểm tra file.
2. Chọn một encoding thống nhất cho toàn bộ SQL fixture.
3. Lưu lại file bằng encoding đó.
4. Khai báo cùng charset trong `@SqlConfig`.
5. Chạy test trên môi trường CI để xác nhận kết quả không phụ thuộc cấu hình máy cá nhân.

Không nên dùng encoding mặc định của hệ điều hành như một quy ước ngầm cho fixture dùng chung. Khai báo rõ encoding giúp hành vi đọc script ổn định hơn.

### 2.2. Encoding không thay thế cấu hình collation của database

`encoding` chỉ điều khiển cách Java đọc file SQL thành ký tự. Nó không quyết định charset, collation hoặc kiểu dữ liệu của cột trong database. Nếu script được đọc đúng nhưng dữ liệu lưu hoặc so sánh sai, cần kiểm tra cấu hình database, column type và collation riêng.

## 3. Dấu phân cách câu lệnh SQL (`separator`)

Thuộc tính `separator` xác định chuỗi ký tự dùng để phân tách các câu lệnh trong script. Mặc định, Spring dùng dấu chấm phẩy (`;`). Ví dụ:

```sql
INSERT INTO department (id, name) VALUES (1, 'Engineering');
INSERT INTO department (id, name) VALUES (2, 'Support');
UPDATE department SET name = 'Platform Engineering' WHERE id = 1;
```

Spring tách script thành các statement theo separator rồi thực thi lần lượt. Có thể khai báo tường minh:

```java
@SqlConfig(separator = ";")
```

Khi script chỉ chứa SQL thông thường, giữ separator mặc định thường là đủ. Chỉ đổi separator khi cú pháp của script khiến dấu `;` xuất hiện bên trong một statement phức tạp.

### 3.1. Stored procedure có dấu chấm phẩy bên trong

Stored procedure hoặc function có thể chứa nhiều câu lệnh nội bộ, mỗi câu kết thúc bằng dấu `;`. Nếu Spring dùng `;` làm separator của toàn file, script có thể bị chia sai thành các mảnh.

Ví dụ một thủ tục có thân chứa nhiều statement:

```sql
CREATE PROCEDURE update_customer_status(IN customer_id BIGINT)
BEGIN
    UPDATE customer
       SET status = 'ACTIVE'
     WHERE id = customer_id;

    INSERT INTO audit_log (entity_id, action)
    VALUES (customer_id, 'CUSTOMER_ACTIVATED');
END
@@
```

Với database hỗ trợ cú pháp này, có thể dùng separator riêng ở cuối định nghĩa:

```java
@Sql(
        scripts = "/db/procedures.sql",
        config = @SqlConfig(
                encoding = "UTF-8",
                separator = "@@"))
```

Lúc này dấu `;` bên trong procedure thuộc cú pháp của statement, còn `@@` đánh dấu ranh giới statement để Spring gửi toàn bộ định nghĩa đến database. Cú pháp procedure cụ thể phụ thuộc database; hãy dùng delimiter phù hợp với dialect đang chạy.

### 3.2. Separator phải khớp chính xác với script

Nếu cấu hình `separator = "@@"` nhưng file vẫn kết thúc statement bằng `;`, Spring có thể coi toàn bộ file là một statement hoặc không tách theo cách mong đợi. Ngược lại, nếu file dùng `@@` nhưng cấu hình giữ `;`, procedure có thể bị tách sai.

Hãy giữ separator trong file và annotation như một cặp cấu hình. Có thể ghi chú ở đầu script để người đọc biết delimiter:

```sql
-- This script uses @@ as the statement separator.
CREATE PROCEDURE refresh_summary()
BEGIN
    UPDATE summary_table SET refreshed = TRUE;
END
@@
```

Separator là chuỗi literal, không phải regular expression. Chọn một delimiter ít có khả năng xuất hiện trong nội dung statement.

### 3.3. Script có một statement hoặc delimiter đặc biệt

Nếu một script chỉ chứa một câu lệnh phức tạp, có thể chọn delimiter phù hợp để Spring gửi statement như một đơn vị. Spring cũng có hằng `ScriptUtils.EOF_STATEMENT_SEPARATOR` dành cho trường hợp dùng cuối file làm ranh giới statement. Khi dùng delimiter đặc biệt này, hãy bảo đảm script chỉ có statement mà test dự định thực thi và không dựa vào việc parser tách theo dấu chấm phẩy bên trong.

Với phần lớn fixture, separator mặc định `;` dễ đọc và tương thích với SQL thông thường. Chỉ dùng delimiter đặc biệt khi cú pháp của database yêu cầu.

## 4. Comment prefix và block comment

SQL script thường có comment giải thích fixture hoặc tạm thời vô hiệu hóa một câu lệnh. `@SqlConfig` cho phép cấu hình cú pháp comment để parser bỏ qua phần comment khi tách statement.

### 4.1. Comment một dòng

Mặc định, Spring nhận diện `--` là tiền tố comment một dòng. Ví dụ:

```sql
-- Seed a customer used by repository tests.
INSERT INTO customer (id, name) VALUES (101, 'Lan');
```

Có thể chỉ định tiền tố comment bằng `commentPrefix`:

```java
@SqlConfig(commentPrefix = "--")
```

Từ Spring Framework 6.1, `commentPrefixes` cho phép khai báo nhiều tiền tố:

```java
@SqlConfig(commentPrefixes = {"--", "#"})
```

Điều này hữu ích khi script có comment theo cú pháp của nhiều công cụ hoặc database. Hãy chỉ khai báo các prefix thực sự được dùng; một ký tự có thể xuất hiện trong SQL literal hoặc toán tử của dialect và cần được xử lý đúng theo parser.

### 4.2. Block comment

Mặc định, Spring nhận diện block comment theo cặp `/*` và `*/`:

```sql
/*
  Fixture for the customer repository integration test.
  Keep the IDs stable so assertions remain deterministic.
*/
INSERT INTO customer (id, name) VALUES (101, 'Lan');
```

Có thể cấu hình delimiter tường minh:

```java
@SqlConfig(
        blockCommentStartDelimiter = "/*",
        blockCommentEndDelimiter = "*/")
```

Nếu script sử dụng một kiểu block comment riêng do công cụ sinh SQL tạo ra, khai báo đúng cặp delimiter tương ứng. Hai giá trị phải phản ánh đúng cú pháp trong file.

### 4.3. Comment không được gửi như SQL statement

Parser loại comment khi chuẩn bị statement. Điều này cho phép file có phần giải thích mà không làm database nhận một câu lệnh không hợp lệ. Tuy nhiên, không dùng comment để thay thế việc cấu hình separator hoặc để che một phần SQL đang lỗi. Nếu script chứa cú pháp đặc thù mà parser không hiểu, hãy điều chỉnh comment delimiter hoặc tách script theo mục đích.

## 5. Chọn datasource và transaction manager cho script

`@SqlConfig` không chỉ điều khiển cách đọc file mà còn có các thuộc tính xác định nơi và transaction mà script sử dụng:

- `dataSource`: tên bean `DataSource` dùng để thực thi SQL.
- `transactionManager`: tên bean `PlatformTransactionManager` dùng để quản lý transaction của script.
- `transactionMode`: cách script tham gia hoặc tạo transaction.

Nếu ứng dụng chỉ có một datasource và một transaction manager phù hợp, Spring có thể suy luận chúng. Khi có nhiều nguồn dữ liệu, hãy chỉ định tên bean để tránh script chạy nhầm database.

Ví dụ:

```java
@SpringBootTest
@SqlConfig(
        dataSource = "ordersDataSource",
        transactionManager = "ordersTransactionManager",
        encoding = "UTF-8",
        separator = ";")
class OrderSqlIntegrationTest {
    @Test
    @Sql("/db/orders-fixture.sql")
    void loadsOrderFixture() {
        // Script chạy trên orders datasource.
    }
}
```

Nếu script dùng datasource audit, cấu hình `dataSource` và `transactionManager` tương ứng. Hai bean cần quản lý cùng resource hoặc cùng persistence setup mà script định tác động.

Khi test method đã có `@Transactional`, transaction mode quyết định script tham gia transaction hiện tại hay chạy trong transaction riêng. Đây là điểm cần hiểu rõ để biết dữ liệu setup có bị rollback cùng test hay không.

## 6. Transaction mode của `@SqlConfig`

`SqlConfig.TransactionMode` có ba giá trị:

| Giá trị | Ý nghĩa |
|---|---|
| `DEFAULT` | Dùng chế độ mặc định được suy ra từ cấu hình toàn cục hoặc hành vi mặc định của Spring. |
| `INFERRED` | Dùng transaction đang hoạt động nếu có; nếu không có, Spring có thể tạo transaction riêng khi tìm được transaction manager phù hợp. |
| `ISOLATED` | Chạy script trong transaction riêng, độc lập với transaction hiện tại và commit transaction riêng đó khi hoàn tất thành công. |

Trong đa số test, chế độ suy luận là đủ. Nếu test method có transaction do Spring Test quản lý, script setup thường tham gia transaction đó. Khi test kết thúc và transaction bị rollback, dữ liệu setup cũng bị rollback.

### 6.1. Dùng script trong transaction test-managed

```java
@SpringBootTest
@Transactional
class CustomerRepositoryTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    @Sql("/db/customer-fixture.sql")
    void readsFixtureInsideTestTransaction() {
        assertThat(customers.findByEmail("lan@example.test")).isPresent();
    }
}
```

Với transaction mode suy luận, script có thể tham gia transaction test đang hoạt động. Dữ liệu được tạo trong cùng transaction và rollback sau test theo mặc định. Đây là cách thuận tiện để setup fixture mà không để lại dữ liệu sau mỗi method.

### 6.2. Dùng `ISOLATED` khi cần commit setup riêng

Có trường hợp dữ liệu setup phải được commit trước khi test chạy, ví dụ test một thành phần đọc dữ liệu từ transaction khác hoặc kiểm tra hành vi phụ thuộc vào dữ liệu đã commit. Có thể chọn `ISOLATED`:

```java
@Test
@Transactional
@Sql(
        scripts = "/db/committed-fixture.sql",
        config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
void readsCommittedFixture() {
    // Fixture được commit trong transaction riêng.
}
```

Script được chạy trong transaction riêng và commit khi thành công. Vì transaction đó độc lập với transaction test, rollback của test method không tự hoàn tác dữ liệu đã commit bởi script. Test cần cleanup dữ liệu này bằng script khác hoặc cơ chế dọn fixture riêng.

Không chọn `ISOLATED` chỉ vì script không chạy được. Hãy xác định rõ transaction boundary cần kiểm tra. Nếu muốn setup được rollback cùng test, giữ chế độ suy luận và bảo đảm script dùng đúng manager.

## 7. `errorMode`: cách xử lý lỗi khi thực thi script

`@SqlConfig.errorMode` quyết định điều gì xảy ra khi một statement trong script thất bại. Đây là cấu hình quan trọng vì một script có thể gồm nhiều câu lệnh; nếu một câu lỗi, Spring có thể dừng hoặc tiếp tục tùy chế độ.

Các giá trị của `SqlConfig.ErrorMode`:

| Giá trị | Hành vi |
|---|---|
| `DEFAULT` | Dùng hành vi lỗi mặc định của Spring ScriptUtils. Mặc định là dừng khi có lỗi SQL, đồng thời có xử lý riêng cho một số lệnh `DROP` thất bại. |
| `FAIL_ON_ERROR` | Báo lỗi và dừng script ngay khi một statement thất bại, kể cả lệnh `DROP`. |
| `CONTINUE_ON_ERROR` | Ghi nhận lỗi và tiếp tục thực thi các statement còn lại. |
| `IGNORE_FAILED_DROPS` | Bỏ qua lỗi của statement `DROP`, nhưng vẫn thất bại với các loại statement khác. |

### 7.1. `DEFAULT`

Nếu không chỉ định `errorMode`, Spring dùng hành vi mặc định của `ScriptUtils`. Theo mặc định, lỗi của statement thông thường làm script thất bại; các lỗi của lệnh `DROP` có thể được bỏ qua để hỗ trợ script dọn dẹp có tính lặp lại.

Ví dụ, một script có thể xóa bảng tạm trước khi tạo lại:

```sql
DROP TABLE temporary_customer;
CREATE TABLE temporary_customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
```

Nếu bảng chưa tồn tại, `DROP` có thể thất bại nhưng script vẫn tiếp tục theo hành vi mặc định dành cho failed drops. Các lỗi ở `CREATE TABLE` hoặc `INSERT` vẫn cần được phát hiện.

### 7.2. `FAIL_ON_ERROR`

Dùng chế độ này khi mọi statement đều bắt buộc thành công:

```java
@SqlConfig(errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR)
```

Đây thường là lựa chọn phù hợp cho fixture tạo dữ liệu mà test phụ thuộc trực tiếp. Nếu một `INSERT` sai constraint hoặc một cột bị đổi tên, test nên thất bại ngay tại bước setup thay vì tiếp tục với dữ liệu thiếu.

`FAIL_ON_ERROR` cũng làm một `DROP` thất bại trở thành lỗi. Nếu script có lệnh xóa object có thể chưa tồn tại, hãy dùng cú pháp idempotent phù hợp với database như `DROP TABLE IF EXISTS` hoặc chọn chế độ xử lý failed drops khi điều đó đúng với mục đích script.

### 7.3. `CONTINUE_ON_ERROR`

Chế độ này yêu cầu Spring tiếp tục thực thi các statement còn lại khi gặp lỗi:

```java
@SqlConfig(errorMode = SqlConfig.ErrorMode.CONTINUE_ON_ERROR)
```

Nó có thể hữu ích cho script migration hoặc teardown đặc biệt khi muốn thu thập nhiều lỗi trong một lần chạy. Tuy nhiên, với fixture của unit/integration test, chế độ này dễ che giấu setup không hoàn chỉnh. Test có thể thất bại ở assertion sau đó và khiến nguyên nhân thật khó nhận ra, hoặc thậm chí vẫn qua nếu statement lỗi không ảnh hưởng assertion.

Chỉ dùng `CONTINUE_ON_ERROR` khi script được thiết kế để tiếp tục sau lỗi và người viết hiểu rõ trạng thái dữ liệu có thể còn lại. Không dùng nó như một cách làm test xanh khi SQL có lỗi.

### 7.4. `IGNORE_FAILED_DROPS`

Chế độ này bỏ qua lỗi từ statement `DROP`, nhưng các lỗi khác vẫn làm script thất bại:

```java
@SqlConfig(errorMode = SqlConfig.ErrorMode.IGNORE_FAILED_DROPS)
```

Nó phù hợp với script teardown cần xóa object nếu tồn tại, nhưng vẫn muốn phát hiện lỗi ở `INSERT`, `UPDATE`, `CREATE` hoặc câu lệnh khác. Nếu database hỗ trợ `IF EXISTS`, cú pháp đó thường làm ý định rõ ràng hơn:

```sql
DROP TABLE IF EXISTS temporary_customer;
```

Hãy chọn cú pháp theo dialect. Không phải mọi database đều hỗ trợ cùng một biến thể `IF EXISTS` cho mọi loại object.

## 8. Kết hợp encoding, separator và error mode

Một script có thể cần nhiều cấu hình cùng lúc. Ví dụ, script tạo stored procedure chứa dấu chấm phẩy bên trong, có comment và dữ liệu Unicode:

```java
@Test
@Sql(
        scripts = "/db/customer-procedures.sql",
        config = @SqlConfig(
                encoding = "UTF-8",
                separator = "@@",
                commentPrefixes = {"--"},
                blockCommentStartDelimiter = "/*",
                blockCommentEndDelimiter = "*/",
                errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR))
void installsCustomerProcedures() {
    // Script được đọc bằng UTF-8, tách theo @@ và dừng nếu có lỗi.
}
```

Mỗi thuộc tính điều khiển một khía cạnh riêng:

- `encoding` xác định cách đọc byte của file thành ký tự.
- `separator` xác định ranh giới statement.
- `commentPrefixes` và block delimiters xác định phần comment cần bỏ qua.
- `errorMode` xác định phản ứng khi database báo lỗi khi thực thi statement.

Các cấu hình này không sửa cú pháp SQL của database. Nếu statement không hợp lệ theo dialect, chọn encoding hoặc separator khác không làm nó trở thành SQL hợp lệ; chỉ có error mode quyết định Spring phản ứng thế nào khi database trả lỗi.

## 9. Cấu hình toàn cục và cục bộ

Một test class có thể chứa nhiều script với yêu cầu khác nhau. Ví dụ, fixture thông thường dùng `;`, còn stored procedure dùng `@@`:

```java
@SpringBootTest
@SqlConfig(
        encoding = "UTF-8",
        separator = ";",
        errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR)
class CustomerDatabaseTest {
    @Test
    @Sql("/db/customer-fixture.sql")
    void loadsCustomerData() {
        // Dùng cấu hình toàn cục: UTF-8, ; và fail on error.
    }

    @Test
    @Sql(
            scripts = "/db/customer-procedure.sql",
            config = @SqlConfig(separator = "@@"))
    void createsCustomerProcedure() {
        // Chỉ separator được override; encoding và error mode kế thừa.
    }
}
```

Khi cấu hình cục bộ chỉ đặt `separator`, những thuộc tính khác tiếp tục nhận giá trị từ cấu hình toàn cục hoặc mặc định. Điều này giúp tránh lặp lại toàn bộ cấu hình cho từng script.

### 9.1. Khi một script cần cấu hình hoàn toàn khác

Nếu script dùng dialect, datasource hoặc transaction mode khác, khai báo cục bộ đầy đủ những thuộc tính khác biệt:

```java
@Sql(
        scripts = "/db/audit-fixture.sql",
        config = @SqlConfig(
                dataSource = "auditDataSource",
                transactionManager = "auditTransactionManager",
                transactionMode = SqlConfig.TransactionMode.ISOLATED,
                encoding = "UTF-8",
                separator = ";",
                errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR))
```

Script này chạy trên audit datasource và transaction manager đã chỉ định. Vì dùng `ISOLATED`, dữ liệu có thể được commit độc lập với transaction test; cần có cleanup phù hợp.

### 9.2. Kế thừa cấu hình trong test class hierarchy

Nếu `@SqlConfig` được đặt trên base test class, nó có thể làm cấu hình toàn cục cho các `@Sql` trong class hierarchy. Lớp con có thể thêm hoặc override cấu hình theo quy tắc merged annotation của Spring Test.

Hãy giữ cấu hình base class ở mức thật sự dùng chung, ví dụ UTF-8 và error mode nghiêm ngặt. Nếu subclass dùng datasource khác, khai báo `dataSource` và `transactionManager` riêng ở nơi cần để tránh chạy nhầm database.

## 10. `@Sql` với nhiều script và execution phase

`@Sql` có thể khai báo nhiều script:

```java
@Test
@Sql(scripts = {
        "/db/schema.sql",
        "/db/reference-data.sql",
        "/db/customer-fixture.sql"
})
void runsScriptsInDeclaredOrder() {
    // Các script được thực thi theo thứ tự khai báo.
}
```

Thứ tự có ý nghĩa khi script sau phụ thuộc bảng hoặc dữ liệu được tạo bởi script trước. Giữ các script nhỏ theo trách nhiệm giúp dễ tái sử dụng và chẩn đoán hơn một file setup lớn.

`executionPhase` xác định script chạy trước hay sau test method:

```java
@Test
@Sql(
        scripts = "/db/cleanup-customer.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
void createsCustomer() {
    // Dọn dữ liệu sau method theo cấu hình transaction tương ứng.
}
```

Giá trị mặc định là `BEFORE_TEST_METHOD`. Có thể dùng `AFTER_TEST_METHOD` cho teardown. Khi test có transaction, hãy hiểu script teardown tham gia transaction nào và transaction đó được commit hay rollback ra sao. Nếu cleanup phải tác động độc lập với transaction test, cấu hình `transactionMode = ISOLATED` và transaction manager phù hợp.

### 10.1. `@Sql` ở cấp class và method

`@Sql` có thể đặt trên class để chạy script cho các test method trong class, hoặc trên method để setup một kịch bản cụ thể. Khi cả hai phạm vi cùng khai báo script, Spring có các chế độ merge/override để xác định tập script được thực thi. Nếu test class dùng setup chung và một số method có fixture riêng, hãy khai báo ý định merge rõ ràng bằng `@SqlMergeMode` khi cần.

Đừng giả định một `@Sql` ở method luôn thay thế hoặc luôn bổ sung script class-level mà không xem chế độ merge đang áp dụng. Cấu hình mặc định và annotation `@SqlMergeMode` quyết định cách kết hợp. Với test quan trọng, giữ setup class-level ngắn và dùng method-level script cho dữ liệu riêng.

## 11. Cấu hình SQL script khi có nhiều datasource

Nếu ứng dụng có nhiều `DataSource` hoặc `PlatformTransactionManager`, Spring có thể không suy luận được nguồn cần dùng cho script. Hãy chỉ rõ bean name:

```java
@SpringBootTest
class MultiDatabaseSqlTest {
    @Test
    @Sql(
            scripts = "/db/orders-fixture.sql",
            config = @SqlConfig(
                    dataSource = "ordersDataSource",
                    transactionManager = "ordersTransactionManager",
                    encoding = "UTF-8"))
    void loadsOrders() {
        // Fixture được thực thi trên orders database.
    }

    @Test
    @Sql(
            scripts = "/db/audit-fixture.sql",
            config = @SqlConfig(
                    dataSource = "auditDataSource",
                    transactionManager = "auditTransactionManager",
                    encoding = "UTF-8"))
    void loadsAuditEntries() {
        // Fixture được thực thi trên audit database.
    }
}
```

Nếu test method có `@Transactional`, cần bảo đảm transaction manager của `@SqlConfig` phù hợp với transaction mà script cần tham gia. Một script chạy trên datasource audit không tự được rollback bởi transaction của orders manager.

Với JPA, `@Sql` thực thi SQL trực tiếp qua datasource. Nếu test đang có persistence context chứa entity đã cache, script có thể thay đổi database mà entity trong persistence context không tự cập nhật. Khi cần đọc lại trạng thái do script tạo, cân nhắc flush/clear `EntityManager` hoặc dùng repository trong một transaction/persistence context mới.

## 12. Cách chẩn đoán lỗi SQL script

### 12.1. Ký tự tiếng Việt bị lỗi

Kiểm tra encoding thực tế của file và `@SqlConfig.encoding`. Đồng bộ file và cấu hình về UTF-8. Nếu ký tự được đọc đúng nhưng lưu sai, kiểm tra charset/collation của database và kiểu cột.

### 12.2. Stored procedure bị tách thành nhiều statement

Kiểm tra dấu `;` bên trong procedure. Chọn separator riêng như `@@` và đặt delimiter tương ứng ở cuối mỗi statement trong file. Đảm bảo separator không xuất hiện ngoài ý muốn trong nội dung SQL.

### 12.3. Parser gửi comment như một phần SQL

Kiểm tra `commentPrefixes`, `blockCommentStartDelimiter` và `blockCommentEndDelimiter`. Đảm bảo chúng khớp cú pháp comment trong file và phiên bản Spring hỗ trợ thuộc tính đang dùng.

### 12.4. Script tiếp tục dù setup đã lỗi

Kiểm tra `errorMode`. Nếu đang dùng `CONTINUE_ON_ERROR`, Spring có thể tiếp tục sau statement thất bại. Với fixture cần đầy đủ, dùng `FAIL_ON_ERROR` hoặc hành vi `DEFAULT` phù hợp.

### 12.5. Script thất bại vì bảng chưa tồn tại

Nếu lỗi đến từ `DROP`, cân nhắc `DROP TABLE IF EXISTS` theo dialect hoặc `IGNORE_FAILED_DROPS`. Nếu lỗi đến từ `INSERT`/`UPDATE`/`CREATE`, không nên bỏ qua chỉ để script tiếp tục.

### 12.6. Script chạy nhầm database

Kiểm tra `dataSource` và `transactionManager` trong `@SqlConfig`, bean name và datasource mà repository đang dùng. Với nhiều datasource, không dựa vào suy luận tự động nếu context có nhiều candidate.

### 12.7. Dữ liệu fixture biến mất sau test

Nếu script tham gia test-managed transaction, dữ liệu có thể bị rollback sau method. Nếu fixture cần commit độc lập, dùng `ISOLATED` và nhớ cleanup vì rollback của test sẽ không xóa dữ liệu đã commit riêng.

## 13. Ví dụ tổng hợp: fixture UTF-8 và stored procedure

Giả sử test cần tạo dữ liệu khách hàng có tiếng Việt và cài một stored procedure. Script fixture thông thường dùng dấu `;`:

```sql
-- src/test/resources/db/customer-fixture.sql
INSERT INTO customer (id, full_name, city)
VALUES (101, 'Nguyễn Thị Lan', 'Thành phố Hồ Chí Minh');

INSERT INTO customer (id, full_name, city)
VALUES (102, 'Trần Minh Đức', 'Đà Nẵng');
```

Script procedure dùng `@@` làm separator:

```sql
-- src/test/resources/db/customer-procedure.sql
CREATE PROCEDURE activate_customer(IN p_id BIGINT)
BEGIN
    UPDATE customer
       SET status = 'ACTIVE'
     WHERE id = p_id;

    INSERT INTO audit_log (entity_id, action)
    VALUES (p_id, 'CUSTOMER_ACTIVATED');
END
@@
```

Test class có cấu hình chung:

```java
@SpringBootTest
@SqlConfig(
        encoding = "UTF-8",
        separator = ";",
        commentPrefixes = {"--"},
        errorMode = SqlConfig.ErrorMode.FAIL_ON_ERROR)
class CustomerSqlIntegrationTest {
    @Autowired
    private CustomerRepository customers;

    @Test
    @Sql("/db/customer-fixture.sql")
    void readsUnicodeFixture() {
        Customer customer = customers.findById(101L).orElseThrow();

        assertThat(customer.name()).isEqualTo("Nguyễn Thị Lan");
        assertThat(customer.city()).isEqualTo("Thành phố Hồ Chí Minh");
    }

    @Test
    @Sql(
            scripts = "/db/customer-procedure.sql",
            config = @SqlConfig(separator = "@@"))
    void installsProcedureUsingCustomSeparator() {
        // Xác nhận procedure tồn tại hoặc thực thi nó theo dialect database.
    }
}
```

Script fixture kế thừa cấu hình UTF-8, separator mặc định và fail-on-error. Script procedure chỉ override separator thành `@@`; các thuộc tính khác tiếp tục kế thừa. Cú pháp stored procedure trong ví dụ cần điều chỉnh theo database mà dự án sử dụng.

## 14. Quy trình cấu hình `@SqlConfig`

Khi một SQL script không chạy đúng hoặc có yêu cầu đặc biệt, hãy xác định theo thứ tự:

1. Xác định file script và phạm vi `@Sql` đang áp dụng: class-level hay method-level.
2. Kiểm tra encoding thực tế của file; khai báo `encoding` rõ ràng nếu script chứa Unicode.
3. Kiểm tra delimiter của từng statement; nếu có procedure chứa dấu `;` nội bộ, chọn `separator` riêng.
4. Khai báo đúng comment prefix và block comment delimiter nếu script dùng cú pháp khác mặc định.
5. Chọn `dataSource` và `transactionManager` nếu ứng dụng có nhiều nguồn dữ liệu.
6. Chọn transaction mode theo yêu cầu tham gia transaction test hay commit riêng.
7. Chọn error mode: nghiêm ngặt cho fixture bắt buộc; chỉ tiếp tục hoặc bỏ qua failed drops khi script có chủ đích.
8. Chạy test và đọc lỗi SQL đầu tiên để xác định statement nào thất bại.
9. Nếu dùng `ISOLATED` hoặc script commit độc lập, bổ sung cleanup cho dữ liệu đã tồn tại sau test.

Giữ cấu hình chung ở class-level khi nhiều script có cùng encoding, delimiter và error policy. Dùng cấu hình cục bộ cho procedure hoặc script đặc biệt để thay đúng thuộc tính cần thiết mà không làm các fixture khác thay đổi.

## 15. Nguyên tắc cần nhớ

- `@Sql` khai báo script; `@SqlConfig` điều khiển cách đọc và thực thi script.
- `encoding` nên khớp với encoding thực tế của file; UTF-8 là lựa chọn ổn định cho fixture có Unicode.
- `separator` mặc định là `;`; dùng delimiter riêng khi statement như stored procedure chứa dấu chấm phẩy nội bộ.
- `commentPrefix` cấu hình comment một dòng; `commentPrefixes` hỗ trợ nhiều prefix từ Spring Framework 6.1.
- `blockCommentStartDelimiter` và `blockCommentEndDelimiter` cấu hình comment nhiều dòng.
- `dataSource` và `transactionManager` giúp chọn đúng nguồn dữ liệu khi context có nhiều bean.
- `DEFAULT`, `FAIL_ON_ERROR`, `CONTINUE_ON_ERROR` và `IGNORE_FAILED_DROPS` có hành vi khác nhau; fixture quan trọng thường cần chính sách lỗi nghiêm ngặt.
- `INFERRED` có thể tham gia transaction hiện tại; `ISOLATED` chạy và commit transaction riêng.
- Cấu hình `@SqlConfig` ở class-level dùng chung; cấu hình trong `@Sql(config = ...)` chỉ áp dụng cục bộ và override thuộc tính tương ứng.
- SQL script được thực thi bởi database thật nên vẫn phải đúng dialect, schema, constraint và quyền truy cập của database.

`@SqlConfig` giúp kiểm soát rõ cách Spring đọc file, phân tách statement và phản ứng khi SQL thất bại. Khi encoding, delimiter, transaction manager và error mode được chọn theo đúng script, dữ liệu setup của test sẽ nhất quán và lỗi SQL sẽ được báo ở đúng bước thay vì bị che giấu bởi trạng thái dữ liệu không đầy đủ.

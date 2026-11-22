# Đường dẫn script và cơ chế tìm script mặc định

Trong kiểm thử Spring, SQL script thường được dùng để tạo schema, nạp dữ liệu mẫu, chuẩn bị trạng thái trước test hoặc dọn dữ liệu sau test. Spring TestContext cung cấp annotation `@Sql` để khai báo các script cần thực thi và quy tắc xác định resource tương ứng.

Hai việc cần hiểu rõ là **cách Spring phân giải đường dẫn resource** và **cách Spring tự tìm script khi annotation không khai báo đường dẫn**. Nếu nhầm đường dẫn tương đối với đường dẫn tính từ thư mục chạy ứng dụng, hoặc không biết quy ước tên file mặc định, test có thể báo không tìm thấy script dù file đã nằm trong project.

## 1. Vai trò của @Sql trong Spring TestContext

`@Sql` thuộc package `org.springframework.test.context.jdbc`. Annotation này cho phép khai báo SQL script hoặc câu lệnh SQL trực tiếp cho test class và test method. Spring TestContext dùng `SqlScriptsTestExecutionListener` để đọc metadata, tìm resource và thực thi SQL tại thời điểm được cấu hình.

Ví dụ khai báo script trên một test method:

```java
@Test
@Sql("classpath:/db/test/insert-order.sql")
void findsInsertedOrder() {
    // Test truy vấn dữ liệu do script chuẩn bị.
}
```

Thuộc tính `value` là alias của `scripts`, vì vậy hai cách sau tương đương:

```java
@Sql("classpath:/db/test/insert-order.sql")
```

```java
@Sql(scripts = "classpath:/db/test/insert-order.sql")
```

Khi có nhiều file, truyền một mảng đường dẫn:

```java
@Sql(scripts = {
        "classpath:/db/test/clear-orders.sql",
        "classpath:/db/test/insert-orders.sql"
})
```

Các script trong cùng khai báo được xử lý theo thứ tự được liệt kê. Điều này hữu ích khi script đầu tiên xóa hoặc tạo cấu trúc cần thiết trước khi script tiếp theo nạp dữ liệu.

`@Sql` có thể khai báo ở cấp class hoặc method. Khai báo cấp class thường được áp dụng cho các test method trong class; khai báo cấp method mô tả script dành riêng cho method đó. Mặc định script được thực thi trước test method, trừ khi `executionPhase` được cấu hình khác.

## 2. Các quy tắc phân giải đường dẫn resource

Mỗi phần tử trong `scripts` được Spring diễn giải như một resource. Đường dẫn có thể được hiểu theo package của test class hoặc theo prefix resource tường minh.

| Cách khai báo | Cách Spring phân giải | Ví dụ |
|---|---|---|
| Không có prefix, không bắt đầu bằng `/` | Classpath resource tương đối với package của test class | `db/seed.sql` |
| Bắt đầu bằng `/` | Classpath resource tuyệt đối từ classpath root | `/db/seed.sql` |
| Có prefix `classpath:` | Resource trên classpath theo vị trí chỉ định | `classpath:/db/seed.sql` |
| Có prefix `file:` | Resource trên filesystem | `file:/opt/test-data/seed.sql` |

Điểm cần nhớ: đường dẫn package-relative được tính từ package Java của test class, không tính từ thư mục hiện tại của terminal, thư mục project hay vị trí file Java trên filesystem.

### 2.1. Đường dẫn tương đối với package của test class

Giả sử test class khai báo package:

```java
package com.example.orders;
```

Và có annotation:

```java
@Sql("db/seed-orders.sql")
class OrderRepositoryTest {
}
```

Spring tìm resource trên classpath tại:

```text
com/example/orders/db/seed-orders.sql
```

Trong một dự án Maven hoặc Gradle thông thường, file tương ứng được đặt tại:

```text
src/test/resources/com/example/orders/db/seed-orders.sql
```

Khi build, nội dung trong `src/test/resources` được đưa vào test runtime classpath. Annotation dùng đường dẫn logic trên classpath, không dùng đường dẫn source filesystem `src/test/resources/...`.

Ví dụ cấu trúc:

```text
src/
  test/
    java/
      com/
        example/
          orders/
            OrderRepositoryTest.java
    resources/
      com/
        example/
          orders/
            db/
              seed-orders.sql
              clean-orders.sql
```

Với cấu trúc này, `@Sql("db/seed-orders.sql")` là đường dẫn tương đối phù hợp với package `com.example.orders`.

### 2.2. Đường dẫn classpath tuyệt đối bắt đầu bằng dấu /

Nếu đường dẫn bắt đầu bằng `/`, Spring xem đó là vị trí tính từ classpath root:

```java
@Sql("/db/test/seed-orders.sql")
class OrderRepositoryTest {
}
```

Resource tương ứng:

```text
src/test/resources/db/test/seed-orders.sql
```

Không thêm package `com/example/orders` vào trước đường dẫn này. Dấu `/` có ý nghĩa chuyển từ package-relative sang classpath-absolute.

### 2.3. Prefix classpath:

Có thể dùng `classpath:` để thể hiện rõ resource nằm trên classpath:

```java
@Sql("classpath:/db/test/seed-orders.sql")
```

Cách viết này thường dễ đọc trong dự án có nhiều loại resource vì người đọc biết ngay script được lấy từ classpath root. Nó cũng tránh phụ thuộc vào package của test class.

Nếu dùng `classpath:` mà không có dấu `/` sau dấu hai chấm, resource vẫn được phân giải theo quy tắc classpath của Spring; để thể hiện rõ đường dẫn từ root, nên viết `classpath:/...`.

### 2.4. Prefix file:

Nếu script nằm ngoài classpath, có thể dùng resource prefix `file:`:

```java
@Sql("file:/opt/test-fixtures/orders/seed.sql")
```

Với Windows, URI file thường có dạng:

```java
@Sql("file:///C:/test-fixtures/orders/seed.sql")
```

Đường dẫn filesystem tuyệt đối có thể phụ thuộc máy chạy và hệ điều hành. Vì vậy, `file:` phù hợp với fixture do môi trường test cung cấp hoặc một đường dẫn được cấu hình rõ ràng; các script được commit cùng dự án thường nên đặt trong `src/test/resources` để test có thể chạy nhất quán trên local và CI.

### 2.5. Không nhầm đường dẫn resource với đường dẫn source

Các cách khai báo sau có ý nghĩa khác nhau:

```java
// Package-relative classpath resource
@Sql("seed.sql")

// Absolute classpath resource
@Sql("/db/seed.sql")

// Explicit classpath resource
@Sql("classpath:/db/seed.sql")

// Filesystem resource
@Sql("file:/opt/fixtures/seed.sql")
```

Không nên viết `@Sql("src/test/resources/db/seed.sql")` với kỳ vọng Spring tự hiểu đây là vị trí source resource. Không prefix, chuỗi này được xử lý như classpath path tương đối với package test class. Nếu muốn lấy file từ filesystem, dùng `file:` và đường dẫn filesystem thực tế.

## 3. Cơ chế tìm script mặc định

Spring TestContext có thể tự phát hiện script mặc định khi `@Sql` không khai báo script và cũng không khai báo câu lệnh inline trong `statements`.

Quy ước phụ thuộc vị trí khai báo annotation:

- Nếu `@Sql` nằm ở cấp class, Spring tìm file có tên bằng tên đơn giản của test class cộng phần mở rộng `.sql`, trong cùng package với test class.
- Nếu `@Sql` nằm ở cấp method, Spring tìm file có tên bằng tên đơn giản của test class, tiếp theo là dấu chấm, tên method, rồi `.sql`, cũng trong cùng package.

### 3.1. Script mặc định ở cấp class

Giả sử test class:

```java
package com.example.orders;

@SpringJUnitConfig(TestConfiguration.class)
@Sql
class OrderRepositoryTest {

    @Test
    void findsPendingOrders() {
        // ...
    }

    @Test
    void findsCompletedOrders() {
        // ...
    }
}
```

Vì `@Sql` được khai báo ở cấp class và không chỉ định `scripts` hoặc `statements`, Spring tìm script mặc định:

```text
com/example/orders/OrderRepositoryTest.sql
```

Trong project, file thường nằm tại:

```text
src/test/resources/com/example/orders/OrderRepositoryTest.sql
```

Script cấp class được áp dụng cho các test method trong class theo execution phase đã khai báo. Với mặc định `BEFORE_TEST_METHOD`, script được thực thi trước từng method thuộc class.

### 3.2. Script mặc định ở cấp method

Giả sử test method có tên `findByStatus`:

```java
package com.example.orders;

class OrderRepositoryTest {

    @Test
    @Sql
    void findByStatus() {
        // ...
    }
}
```

Spring tìm script theo quy ước:

```text
com/example/orders/OrderRepositoryTest.findByStatus.sql
```

File tương ứng trong source resources:

```text
src/test/resources/com/example/orders/OrderRepositoryTest.findByStatus.sql
```

Tên method Java được dùng để tạo tên file. `@DisplayName` không thay thế tên method trong quy ước phát hiện script mặc định.

### 3.3. Bảng quy ước tên file mặc định

| Vị trí `@Sql` | Tên test class | Tên test method | Script Spring tìm |
|---|---|---|---|
| Cấp class | `OrderRepositoryTest` | Không áp dụng | `OrderRepositoryTest.sql` |
| Cấp method | `OrderRepositoryTest` | `findById` | `OrderRepositoryTest.findById.sql` |
| Cấp method | `AccountServiceTest` | `createsAccount` | `AccountServiceTest.createsAccount.sql` |

Các file được tìm trong package của test class. Ví dụ test class thuộc `com.example.account`, file mặc định của method `createsAccount` có classpath path:

```text
com/example/account/AccountServiceTest.createsAccount.sql
```

Quy ước này giúp tổ chức script gần với test class và tránh phải lặp lại một đường dẫn dài trong annotation.

### 3.4. Khi nào Spring không tìm script mặc định?

Spring chỉ áp dụng default script detection khi không có script path và không có inline statement được khai báo. Nếu `scripts` đã được chỉ định, Spring dùng resource đó. Nếu `statements` có giá trị, Spring thực thi các câu SQL inline thay vì tự suy ra file mặc định.

Ví dụ không dùng default script vì đã khai báo đường dẫn:

```java
@Test
@Sql("classpath:/db/orders/seed.sql")
void findsOrder() {
}
```

Ví dụ không dùng default script vì khai báo câu SQL trực tiếp:

```java
@Test
@Sql(statements = "delete from orders where status = 'TEMP'")
void ignoresTemporaryOrders() {
}
```

Nếu Spring cần phát hiện default script nhưng resource theo quy ước không tồn tại, test sẽ thất bại khi xử lý SQL annotation. Khi đó, hãy tạo đúng file mặc định hoặc khai báo đường dẫn tường minh. Không nên tạo một file rỗng chỉ để che lỗi cấu hình nếu test thực sự cần dữ liệu.

## 4. Ví dụ đầy đủ về script mặc định

Giả sử có repository test:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.jdbc.Sql;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(OrderTestConfiguration.class)
@Sql
class OrderRepositoryTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void findsPendingOrders() {
        assertEquals(2, repository.countByStatus("PENDING"));
    }

    @Test
    @Sql
    void findsCompletedOrders() {
        assertEquals(1, repository.countByStatus("COMPLETED"));
    }
}
```

Với cấu hình mặc định, Spring sẽ tìm hai loại script:

```text
src/test/resources/com/example/orders/OrderRepositoryTest.sql
src/test/resources/com/example/orders/OrderRepositoryTest.findsCompletedOrders.sql
```

File class-level có thể tạo schema hoặc dữ liệu nền cần thiết cho các test trong class. File method-level cung cấp dữ liệu riêng cho trường hợp `findsCompletedOrders`.

Tuy nhiên, mặc định method-level `@Sql` **ghi đè** khai báo class-level cho method đó. Vì vậy, khi `findsCompletedOrders()` có `@Sql` riêng, Spring không tự động chạy script class-level cho method này theo chế độ mặc định. Nếu cần chạy cả script nền của class và script riêng của method, hãy dùng `@SqlMergeMode(MERGE)` hoặc khai báo rõ các script cần chạy.

## 5. Tường minh đường dẫn khi cần kiểm soát cấu trúc resource

Default script detection hữu ích khi mỗi test class/method có script tương ứng. Với dự án có cấu trúc SQL dùng chung, tên file không gắn chặt với test class hoặc script nằm trong module resource riêng, nên khai báo path tường minh.

### 5.1. Một script dùng chung cho nhiều test

```java
@Sql("classpath:/db/test/schema.sql")
class AccountRepositoryTest {
    // ...
}
```

### 5.2. Script nền và script riêng cho method

```java
@SpringJUnitConfig(TestConfiguration.class)
@Sql("classpath:/db/test/clean-and-schema.sql")
class OrderRepositoryTest {

    @Test
    @Sql("classpath:/db/test/orders/pending-orders.sql")
    void findsPendingOrders() {
        // ...
    }
}
```

Ở cấu hình mặc định, method có `@Sql` riêng sẽ override khai báo class-level. Nếu `clean-and-schema.sql` vẫn cần chạy cho method này, hãy dùng merge mode hoặc gộp các script cần thiết trong một khai báo.

### 5.3. Nhiều script theo thứ tự

```java
@Test
@Sql(scripts = {
        "classpath:/db/test/cleanup.sql",
        "classpath:/db/test/insert-customers.sql",
        "classpath:/db/test/insert-orders.sql"
})
void loadsOrdersForCustomers() {
    // ...
}
```

Thứ tự khai báo giúp đảm bảo dữ liệu tham chiếu được tạo trước dữ liệu phụ thuộc. Ví dụ, nếu bảng `orders` có foreign key tới `customers`, script khách hàng cần được thực thi trước script đơn hàng.

## 6. Tương tác giữa class-level và method-level @Sql

Spring cho phép khai báo SQL script ở cả class và method. Mặc định, khai báo method-level thay thế khai báo class-level cho method đó. Cơ chế này được gọi là `OVERRIDE`.

### 6.1. OVERRIDE mặc định

```java
@Sql("classpath:/db/test/base-data.sql")
class OrderRepositoryTest {

    @Test
    void usesBaseData() {
        // Chỉ script base-data.sql được áp dụng.
    }

    @Test
    @Sql("classpath:/db/test/special-order-data.sql")
    void usesSpecialData() {
        // Method-level @Sql thay thế class-level @Sql.
    }
}
```

Đây là hành vi mặc định của `@SqlMergeMode`. Nó hữu ích khi mỗi method muốn một fixture độc lập hoàn toàn.

### 6.2. MERGE để kết hợp script class và method

Nếu muốn method-level script được chạy bổ sung sau class-level script, dùng `@SqlMergeMode`:

```java
@SpringJUnitConfig(TestConfiguration.class)
@Sql("classpath:/db/test/base-data.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class OrderRepositoryTest {

    @Test
    @Sql("classpath:/db/test/pending-orders.sql")
    void findsPendingOrders() {
        // base-data.sql và pending-orders.sql cùng được áp dụng.
    }
}
```

Trong chế độ merge, khai báo cấp class được kết hợp với khai báo cấp method. Thứ tự thực thi theo nhóm khai báo class trước, sau đó tới method, phù hợp với cách chuẩn bị dữ liệu nền rồi bổ sung fixture riêng.

`@SqlMergeMode` có thể được đặt ở cấp class hoặc method. Nếu đặt ở method, cấu hình đó có thể thay đổi cách merge cho method cụ thể. Khi test class có nhiều tầng kế thừa, hãy xác định merge mode hiệu lực để tránh ngạc nhiên về script được áp dụng.

### 6.3. Script mặc định trong chế độ merge

Khi dùng `@Sql` không khai báo script ở class hoặc method, Spring có thể phát hiện file mặc định tương ứng ở từng vị trí. Nếu cần kết hợp cả class-level default script và method-level default script, dùng `@SqlMergeMode(MERGE)` để khai báo rõ ý định.

Ví dụ cấu trúc resource:

```text
OrderRepositoryTest.sql
OrderRepositoryTest.findsPendingOrders.sql
```

Với `MERGE`, script nền của class có thể chuẩn bị schema/dữ liệu chung và script của method bổ sung dữ liệu cho kịch bản đang kiểm tra. Nếu không cần kết hợp, giữ `OVERRIDE` mặc định để mỗi method tự xác định fixture của nó.

## 7. Thời điểm thực thi script

`@Sql` có thuộc tính `executionPhase` để quyết định script chạy trước hay sau test method:

| Giá trị | Thời điểm | Mục đích thường gặp |
|---|---|---|
| `BEFORE_TEST_METHOD` | Trước mỗi test method; mặc định | Tạo schema, xóa dữ liệu cũ hoặc nạp fixture |
| `AFTER_TEST_METHOD` | Sau mỗi test method | Dọn dữ liệu hoặc chạy script hậu kiểm |

Ví dụ:

```java
@Test
@Sql(
        scripts = "classpath:/db/test/seed.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(
        scripts = "classpath:/db/test/cleanup.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
void processesSeededData() {
    // ...
}
```

Hai khai báo trên minh họa việc chuẩn bị và cleanup ở hai thời điểm. Nếu cleanup chỉ xóa dữ liệu thuộc transaction test, cần xem transaction mode và rollback mặc định; một lệnh DELETE chạy trong transaction sắp rollback có thể cũng bị rollback. Không nên dựa vào script AFTER để dọn dữ liệu đã commit ở một transaction độc lập nếu chưa cấu hình đúng transaction mode.

## 8. Cấu hình cách Spring đọc SQL script

Đường dẫn resource xác định **file nào được đọc**. `@SqlConfig` điều khiển **nội dung file được phân tích và thực thi như thế nào**.

Ví dụ:

```java
@Sql(
        scripts = "classpath:/db/test/seed.sql",
        config = @SqlConfig(
                encoding = "UTF-8",
                separator = ";",
                commentPrefix = "--"))
```

Một số thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| `encoding` | Encoding dùng để đọc file, ví dụ `UTF-8` |
| `separator` | Dấu phân tách statement, mặc định là `;` |
| `commentPrefix` | Prefix của dòng comment, mặc định là `--` |
| `blockCommentStartDelimiter` | Dấu mở block comment, mặc định là `/*` |
| `blockCommentEndDelimiter` | Dấu đóng block comment, mặc định là `*/` |
| `dataSource` | Tên bean DataSource cần dùng nếu có nhiều datasource |
| `transactionManager` | Tên transaction manager cần dùng |
| `transactionMode` | Cách script tham gia hoặc tạo transaction |
| `errorMode` | Cách xử lý lỗi khi thực thi SQL script |

Có thể khai báo `@SqlConfig` ở cấp class để cấu hình chung cho các `@Sql` trong class, hoặc lồng trực tiếp trong một `@Sql` để cấu hình riêng. Khi khai báo local config, cần chú ý các thuộc tính không được chỉ định sẽ được hợp nhất theo quy tắc của Spring với cấu hình toàn cục.

### 8.1. Encoding

Nếu SQL script chứa tiếng Việt hoặc ký tự Unicode, nên lưu file UTF-8 và khai báo encoding tương ứng khi cần:

```java
@Sql(
        scripts = "classpath:/db/test/vietnamese-data.sql",
        config = @SqlConfig(encoding = "UTF-8"))
```

Encoding không đúng có thể khiến chuỗi tiếng Việt bị lỗi khi insert hoặc khiến database nhận dữ liệu khác mong đợi.

### 8.2. Statement separator và comment

Spring mặc định tách các câu lệnh SQL bằng dấu `;`. Nếu script sử dụng delimiter khác, cấu hình `separator` phù hợp. Script cũng có thể chứa line comment và block comment theo cấu hình parser.

```sql
-- Tạo dữ liệu mẫu cho test
insert into customer(id, name)
values (101, 'Nguyen Van A');

/* Đơn hàng tham chiếu khách hàng ở trên */
insert into orders(id, customer_id, status)
values (501, 101, 'PENDING');
```

Nếu một stored procedure hoặc block SQL chứa dấu `;` nội bộ, cần xem parser và delimiter của database; có thể cấu hình separator khác hoặc tách phần tạo procedure ra thành script phù hợp với dialect.

### 8.3. Transaction mode của script

`@SqlConfig(transactionMode = ...)` điều khiển script chạy trong transaction hiện có hay transaction riêng:

- `INFERRED` là mặc định: nếu có transaction đang hoạt động phù hợp, script tham gia transaction đó; nếu không, script được thực thi theo cơ chế của `ResourceDatabasePopulator` mà không tự tạo transaction test mới.
- `ISOLATED`: script được chạy trong transaction độc lập và transaction đó được commit khi hoàn tất.

Ví dụ:

```java
@Sql(
        scripts = "classpath:/db/test/reference-data.sql",
        config = @SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED))
```

Với `ISOLATED`, dữ liệu có thể tồn tại sau khi test-managed transaction rollback vì script đã commit trong transaction riêng. Chỉ dùng khi đó là mục đích mong muốn; nếu fixture cần được rollback cùng test, giữ transaction mode phù hợp để script tham gia transaction của test.

## 9. Script mặc định và inline SQL statements

Không phải mọi thao tác chuẩn bị dữ liệu đều cần một file `.sql`. `@Sql` có thể nhận `statements` để thực thi SQL inline:

```java
@Test
@Sql(statements = {
        "delete from orders where status = 'TEMP'",
        "insert into orders(id, status) values (900, 'PENDING')"
})
void loadsTemporaryOrder() {
    // ...
}
```

Inline statements phù hợp với một vài câu SQL ngắn, rõ ràng. Với schema hoặc fixture lớn, file script dễ tổ chức, đọc và tái sử dụng hơn.

Nếu `statements` được khai báo, Spring không cần suy ra default script. Tương tự, khi `scripts` được khai báo, đường dẫn được chỉ định quyết định resource cần nạp.

Không nên trộn quá nhiều SQL dài trong annotation vì khó đọc, khó quản lý thứ tự và dễ làm test class chứa chi tiết dữ liệu. Hãy chuyển sang file resource khi fixture có nhiều statement hoặc được dùng lại.

## 10. Phân biệt @Sql với SQL initialization của Spring Boot

Một nhầm lẫn phổ biến là cho rằng file `schema.sql` hoặc `data.sql` luôn là default script của `@Sql`. Đây là hai cơ chế khác nhau.

| Cơ chế | Thành phần quản lý | Mục đích |
|---|---|---|
| `@Sql` | Spring TestContext Framework | Chạy script gắn với test class/method theo execution phase |
| `schema.sql`, `data.sql` trong Spring Boot | Spring Boot SQL database initialization | Khởi tạo schema và dữ liệu khi ứng dụng khởi động theo cấu hình Boot |
| Default script detection của `@Sql` | Quy ước tên test class/method của Spring TestContext | Tìm file `TestClass.sql` hoặc `TestClass.testMethod.sql` |

Nếu một test dùng Spring Boot và ứng dụng tự động nạp `schema.sql`/`data.sql`, những file đó có thể chạy khi context khởi động. Điều này không có nghĩa `@Sql` tự tìm chúng cho từng test method. `@Sql` không có đường dẫn và không có inline statement sẽ tìm file theo tên test class/method đã nêu ở trên.

Để tránh dữ liệu bị nạp hai lần, hãy xác định script nào được chạy lúc khởi động context và script nào được chạy cho từng test. Không nên đặt cùng một lệnh insert trong cả `data.sql` lẫn method-level `@Sql` nếu không có chủ đích.

## 11. Các lỗi thường gặp khi Spring không tìm thấy script

### 11.1. Dùng nhầm đường dẫn tính từ project root

Sai kỳ vọng:

```java
@Sql("src/test/resources/db/seed.sql")
```

Đây không phải đường dẫn classpath root. Nếu file nằm trong `src/test/resources/db/seed.sql`, hãy dùng:

```java
@Sql("/db/seed.sql")
```

hoặc:

```java
@Sql("classpath:/db/seed.sql")
```

### 11.2. Quên package-relative resolution

Test class ở package `com.example.orders` dùng:

```java
@Sql("seed.sql")
```

thì Spring tìm `com/example/orders/seed.sql`, không tìm `seed.sql` ngay ở classpath root. Nếu muốn ở root, thêm dấu `/` hoặc prefix `classpath:/`.

### 11.3. Đặt file sai source resource directory

File trong `src/test/java` không tự động được đưa vào classpath như resource thông thường. Script nên nằm trong `src/test/resources` hoặc một test resource directory được cấu hình cho build tool.

### 11.4. Sai chữ hoa/chữ thường

Filesystem Windows có thể không phân biệt chữ hoa/chữ thường, trong khi Linux CI thường phân biệt. `Seed.sql` và `seed.sql` có thể được coi là hai tên khác nhau. Hãy giữ tên file và annotation khớp chính xác.

### 11.5. Default script không khớp tên method

Nếu method có tên `findByStatus`, file mặc định phải có phần tên:

```text
OrderRepositoryTest.findByStatus.sql
```

Không dùng tên `@DisplayName`, tên test case hiển thị hoặc tên mô tả tiếng Việt để thay cho tên method Java.

### 11.6. Method-level @Sql vô tình override class-level

Test class có script nền nhưng một method khai báo `@Sql` riêng có thể không chạy script nền do merge mode mặc định là `OVERRIDE`. Nếu cần cả hai, dùng `@SqlMergeMode(MERGE)` hoặc khai báo tất cả script cần thiết.

### 11.7. Script được tìm thấy nhưng SQL không thực thi được

Khi resource đã được nạp, lỗi tiếp theo có thể đến từ SQL syntax, tên bảng, schema, dialect, quyền database, encoding hoặc transaction mode. Hãy phân biệt lỗi không tìm thấy resource với lỗi thực thi statement; chúng xảy ra ở các giai đoạn khác nhau.

## 12. Cách tổ chức SQL resource trong dự án

Một cấu trúc phổ biến:

```text
src/test/resources/
  db/
    test/
      schema.sql
      cleanup.sql
      common/
        reference-data.sql
      orders/
        seed-pending-orders.sql
        seed-completed-orders.sql
      accounts/
        seed-active-accounts.sql
```

Sau đó test khai báo đường dẫn classpath rõ ràng:

```java
@Sql("classpath:/db/test/common/reference-data.sql")
```

Với script riêng của test class, có thể dùng default script detection và đặt file trong package resource tương ứng với package test class. Cả hai cách đều hợp lệ; chọn một quy ước nhất quán trong module để thành viên khác dễ tìm file.

Một số nguyên tắc tổ chức:

- Đặt script test trong `src/test/resources`, không đặt chung với migration production nếu không có lý do rõ ràng.
- Dùng `classpath:/...` cho script dùng chung giữa nhiều package.
- Dùng package-relative hoặc default detection khi script thuộc riêng một test class.
- Đặt tên file mô tả dữ liệu hoặc trạng thái được tạo.
- Tách cleanup, schema và fixture khi cần kiểm soát thứ tự.
- Giữ SQL tương thích với database test đang dùng; nếu có nhiều dialect, tổ chức fixture theo database hoặc profile phù hợp.
- Không đưa credential hoặc dữ liệu cá nhân thật vào SQL fixture được commit.

## 13. Quy trình chẩn đoán đường dẫn script

Khi `@Sql` không tìm được file hoặc chạy nhầm script, hãy kiểm tra theo thứ tự:

1. `@Sql` nằm ở class hay method?
2. Annotation có khai báo `scripts` hoặc `statements` không? Nếu không, Spring sẽ tìm default script.
3. Nếu dùng default detection, tên class/method và package có khớp quy ước không?
4. Nếu khai báo path, path có bắt đầu bằng `/`, có prefix `classpath:` hoặc `file:` không?
5. Nếu path package-relative, đã tính đúng package của test class chưa?
6. File có nằm trong test runtime classpath, thường là `src/test/resources`, không?
7. Chữ hoa/chữ thường và phần mở rộng `.sql` có khớp không?
8. Method-level `@Sql` có override class-level declaration không?
9. `executionPhase` có đúng thời điểm cần chạy không?
10. Resource đã được tìm thấy nhưng statement thất bại do SQL, datasource, transaction hoặc schema chưa?

Nếu cần giảm sự mơ hồ, hãy đổi sang đường dẫn tường minh như `classpath:/db/test/seed.sql`. Khi default script detection là một quy ước có chủ đích của test suite, hãy giữ tên file theo đúng tên test class và method.

## 14. Ví dụ tổng hợp với đường dẫn tường minh và default detection

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.jdbc.SqlConfig;

@SpringJUnitConfig(OrderTestConfiguration.class)
@Sql(
        scripts = "classpath:/db/test/schema-and-reference-data.sql",
        config = @SqlConfig(encoding = "UTF-8"))
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class OrderRepositoryTest {

    @Test
    @Sql // Tìm OrderRepositoryTest.findsPendingOrders.sql cùng package
    void findsPendingOrders() {
        // Script nền và script method cùng được thực thi.
    }

    @Test
    @Sql("db/seed-completed-orders.sql")
    void findsCompletedOrders() {
        // Đường dẫn package-relative: com/example/orders/db/seed-completed-orders.sql
        // Script nền class-level cũng được merge.
    }
}
```

Ví dụ này minh họa ba cơ chế cùng lúc:

- Script class-level dùng `classpath:` để trỏ tới resource dùng chung từ classpath root.
- Method `findsPendingOrders` không khai báo path nên Spring tìm file mặc định theo tên class và method trong package `com.example.orders`.
- Method `findsCompletedOrders` dùng path package-relative, vì vậy Spring tìm thư mục `db` bên dưới package test.
- `@SqlMergeMode(MERGE)` yêu cầu kết hợp khai báo method-level với script class-level.

Trong dự án thực tế, cần bảo đảm các file trên tồn tại trong test runtime classpath và nội dung script phù hợp với schema. Nếu không cần script nền cho method nào đó, giữ `OVERRIDE` mặc định hoặc điều chỉnh merge mode ở phạm vi method phù hợp.

## 15. Tài liệu tham khảo

- [Spring Framework Reference — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): hướng dẫn `@Sql`, đường dẫn resource, default script detection, execution phase và SQL configuration.
- [Spring Framework Javadoc — @Sql](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/jdbc/Sql.html): định nghĩa thuộc tính `scripts`, `statements`, `executionPhase` và cách khai báo annotation.
- [Spring Framework Javadoc — @SqlMergeMode](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/jdbc/SqlMergeMode.html): mô tả chế độ `OVERRIDE` và `MERGE` giữa khai báo class-level và method-level.
- [Spring Framework Javadoc — @SqlConfig](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/jdbc/SqlConfig.html): mô tả encoding, separator, datasource, transaction manager và các tùy chọn thực thi script.

Đường dẫn script của `@Sql` được phân giải theo quy tắc Spring Resource: path không có prefix và không bắt đầu bằng `/` được tính tương đối với package của test class; path bắt đầu bằng `/` là classpath tuyệt đối; `classpath:` và `file:` cho phép chỉ rõ loại resource. Khi không khai báo script hoặc inline statement, Spring tìm file mặc định theo tên test class ở cấp class hoặc tên test class cộng tên method ở cấp method. Hiểu hai quy tắc này giúp tổ chức fixture SQL rõ ràng, tránh lỗi resource không tồn tại và kiểm soát chính xác dữ liệu được chuẩn bị cho từng test.

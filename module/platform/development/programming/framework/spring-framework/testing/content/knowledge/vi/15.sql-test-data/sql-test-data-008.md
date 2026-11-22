# @SqlMergeMode khi kết hợp cấu hình lớp và phương thức

Spring TestContext Framework cho phép khai báo SQL script bằng @Sql ở cấp test class hoặc test method. Cấu hình cấp class thường chứa dữ liệu nền dùng chung cho nhiều test; cấu hình cấp method bổ sung dữ liệu riêng cho một tình huống. Khi cả hai cấp cùng khai báo @Sql, Spring cần một quy tắc để quyết định script nào được thực thi. @SqlMergeMode cung cấp quy tắc đó.

Mặc định, cấu hình @Sql ở cấp method **ghi đè** cấu hình @Sql ở cấp class đối với method tương ứng. Nếu muốn giữ script chung của class và chạy thêm script riêng của method, hãy dùng @SqlMergeMode(MERGE). Khi merge, script cấp class được thực thi trước script cấp method trong cùng một pha.

## 1. @Sql ở cấp class và cấp method

@Sql thuộc package org.springframework.test.context.jdbc. Annotation này yêu cầu Spring thực thi một hoặc nhiều SQL script trong vòng đời test. Có thể dùng nó trên class để áp dụng dữ liệu chung cho các method, hoặc trên method để chuẩn bị dữ liệu đặc thù.

@SqlMergeMode cũng thuộc package này và được giới thiệu trong Spring Framework 5.2. Khi @Sql được khai báo ở cấp class, script cấp class được áp dụng cho từng test method trong class, trừ khi một khai báo ở cấp method thay thế nó theo chế độ merge đang có hiệu lực.

Ví dụ khai báo ở cấp class:

~~~java
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/inventory-baseline.sql")
class InventoryRepositoryTest {
    // Các test method đều nhận cấu hình SQL cấp class,
    // trừ khi method có @Sql riêng và quy tắc merge không yêu cầu kết hợp.
}
~~~

Ví dụ khai báo ở cấp method:

~~~java
@Test
@Sql("/sql/inventory-with-zero-stock.sql")
void rejectsReservationWhenStockIsEmpty() {
    // Kiểm tra trường hợp tồn kho bằng 0.
}
~~~

Khi chỉ có một trong hai cấp khai báo @Sql, Spring thực thi script ở cấp đó. Khi cả class và method cùng khai báo, kết quả phụ thuộc vào chế độ merge. Đây là điểm cần hiểu rõ để tránh một test vô tình chạy thiếu dữ liệu nền hoặc chạy thêm dữ liệu không mong muốn.

@Sql có thể khai báo scripts, statements, hoặc cả hai. Ví dụ:

~~~java
@Sql(
        scripts = "/sql/clear-inventory.sql",
        statements = "INSERT INTO inventory(sku, available) VALUES ('SKU-01', 8)"
)
~~~

Các script và câu lệnh được thực thi bởi SqlScriptsTestExecutionListener của Spring TestContext Framework. Pha mặc định là BEFORE_TEST_METHOD, nghĩa là SQL được chạy trước phần thân mỗi test method.

## 2. Chế độ mặc định: OVERRIDE

Nếu không khai báo @SqlMergeMode, Spring dùng chế độ OVERRIDE. Khi một test method có @Sql riêng, các khai báo @Sql ở cấp class không được áp dụng cho method đó. Các method không khai báo @Sql riêng vẫn dùng cấu hình cấp class.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/inventory-baseline.sql")
class InventoryRepositoryTest {
    @Test
    void findsAnExistingItem() {
        // Chạy inventory-baseline.sql trước test.
    }

    @Test
    @Sql("/sql/inventory-with-zero-stock.sql")
    void rejectsReservationWhenStockIsEmpty() {
        // Chạy inventory-with-zero-stock.sql.
        // inventory-baseline.sql ở cấp class bị override cho method này.
    }
}
~~~

Đây là một quy tắc override toàn bộ các khai báo @Sql cấp class trong phạm vi method đó. Spring không tự động hiểu script method là phần bổ sung vào script class. Vì vậy, nếu inventory-baseline.sql tạo dữ liệu tham chiếu bắt buộc mà method chỉ khai báo script cho một bản ghi cụ thể, method có thể chạy thiếu dữ liệu nền.

Có thể viết rõ chế độ mặc định để người đọc không phải suy luận:

~~~java
import org.springframework.test.context.jdbc.SqlMergeMode;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/inventory-baseline.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.OVERRIDE)
class InventoryRepositoryTest {
    // Method có @Sql sẽ thay thế khai báo @Sql cấp class.
}
~~~

Thông thường không cần khai báo OVERRIDE vì đó đã là mặc định. Việc viết tường minh có thể hữu ích trong một nhóm test có quy ước merge khác nhau, hoặc khi một method chủ động quay về hành vi override của class.

## 3. Dùng MERGE để kết hợp script class và method

@SqlMergeMode(SqlMergeMode.MergeMode.MERGE) yêu cầu Spring kết hợp các khai báo @Sql ở cấp class và method. Trong cùng một pha thực thi, script cấp class chạy trước, sau đó script cấp method chạy.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/inventory-baseline.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class InventoryRepositoryMergeTest {
    @Test
    void findsAnExistingItem() {
        // Chạy script baseline cấp class.
    }

    @Test
    @Sql("/sql/inventory-with-zero-stock.sql")
    void rejectsReservationWhenStockIsEmpty() {
        // Chạy baseline trước, rồi chạy script zero-stock của method.
    }
}
~~~

Với method rejectsReservationWhenStockIsEmpty(), thứ tự là:

1. inventory-baseline.sql được khai báo ở cấp class.
2. inventory-with-zero-stock.sql được khai báo ở cấp method.
3. Spring chạy test method.

Nhờ đó, script class có thể thiết lập dữ liệu tham chiếu chung, còn script method chỉ cần thêm hoặc điều chỉnh dữ liệu phục vụ tình huống cụ thể.

### Minh họa bằng nội dung SQL

Giả sử ứng dụng có bảng inventory và bảng warehouse. Script cấp class thiết lập kho mặc định cùng một mặt hàng cơ bản:

~~~sql
-- /sql/inventory-baseline.sql
DELETE FROM inventory;
DELETE FROM warehouse;

INSERT INTO warehouse(id, name)
VALUES (1, 'Main warehouse');

INSERT INTO inventory(sku, warehouse_id, available)
VALUES ('SKU-01', 1, 8);
~~~

Script cấp method bổ sung tình huống hết hàng:

~~~sql
-- /sql/inventory-with-zero-stock.sql
INSERT INTO inventory(sku, warehouse_id, available)
VALUES ('SKU-EMPTY', 1, 0);
~~~

Với chế độ MERGE, test method có thể sử dụng cả kho mặc định, mặt hàng SKU-01 và mặt hàng SKU-EMPTY. Script method được thực thi sau script class nên có thể dựa vào dữ liệu mà script class đã tạo.

Trong thực tế, câu lệnh SQL phải phù hợp với hệ quản trị cơ sở dữ liệu và schema của dự án. Nếu test được chạy nhiều lần, script cấp class cần có chiến lược dọn dữ liệu an toàn, ví dụ xóa theo khóa test hoặc dùng transaction rollback. Tránh giả định một câu DELETE không điều kiện là an toàn khi nhiều test hoặc tiến trình đang dùng chung database.

## 4. Đặt @SqlMergeMode ở cấp class

Đặt @SqlMergeMode(MERGE) trên class là cách phổ biến khi phần lớn method cần dùng dữ liệu nền của class rồi bổ sung dữ liệu riêng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/reference-data.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class CustomerRepositoryTest {
    @Test
    @Sql("/sql/customer-active.sql")
    void findsAnActiveCustomer() {
        // reference-data.sql chạy trước customer-active.sql.
    }

    @Test
    @Sql("/sql/customer-suspended.sql")
    void findsASuspendedCustomer() {
        // reference-data.sql chạy trước customer-suspended.sql.
    }

    @Test
    void canReadReferenceData() {
        // Chỉ có script cấp class vì method không khai báo @Sql riêng.
    }
}
~~~

Khi class dùng MERGE, method không khai báo @Sql vẫn nhận script cấp class như bình thường. Method có khai báo @Sql nhận cả hai cấp. Đây là lựa chọn phù hợp khi script chung thực sự là dữ liệu nền cần thiết cho mọi test trong class.

Không nên bật MERGE chỉ vì muốn mọi script được chạy. Hãy xác định liệu dữ liệu cấp class có hợp lệ cho từng method hay không. Nếu một method cần database hoàn toàn độc lập, việc chạy thêm dữ liệu nền có thể làm test khó hiểu hoặc tạo xung đột khóa.

## 5. Ghi đè chế độ MERGE tại một method

Một class có thể dùng MERGE làm mặc định nhưng có một method cần dữ liệu riêng biệt. Đặt @SqlMergeMode(OVERRIDE) trên method đó để method quay về hành vi override.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/customer-reference-data.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class CustomerRepositoryTest {
    @Test
    @Sql("/sql/customer-active.sql")
    void findsActiveCustomer() {
        // Chạy reference data, sau đó active customer.
    }

    @Test
    @Sql("/sql/customer-isolated-case.sql")
    @SqlMergeMode(SqlMergeMode.MergeMode.OVERRIDE)
    void runsWithAnIsolatedDataset() {
        // Chỉ chạy customer-isolated-case.sql.
        // Script cấp class bị override cho method này.
    }
}
~~~

Thiết lập ở method có độ ưu tiên cho method đó. Điều này cho phép class duy trì một quy tắc chung mà vẫn có ngoại lệ rõ ràng tại những test cần bộ dữ liệu độc lập.

Ngược lại, nếu class không khai báo @SqlMergeMode hoặc dùng OVERRIDE, một method có thể chọn MERGE:

~~~java
@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql("/sql/customer-reference-data.sql")
class CustomerRepositoryOverrideByDefaultTest {
    @Test
    @Sql("/sql/customer-active.sql")
    @SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
    void mergesClassAndMethodScriptsForThisMethod() {
        // Chạy customer-reference-data.sql trước,
        // sau đó customer-active.sql.
    }
}
~~~

Như vậy, @SqlMergeMode có thể được khai báo ở cấp class để đặt mặc định cho class, hoặc ở cấp method để quyết định cách kết hợp cho một method cụ thể. Cấu hình ở cấp method được ưu tiên trong phạm vi method đó.

## 6. Bảng so sánh OVERRIDE và MERGE

| Tình huống | OVERRIDE (mặc định) | MERGE |
|---|---|---|
| Chỉ class có @Sql | Chạy script class | Chạy script class |
| Chỉ method có @Sql | Chạy script method | Chạy script method |
| Cả class và method có @Sql | Chạy khai báo method; bỏ khai báo class cho method đó | Chạy cả hai cấp |
| Thứ tự trong cùng pha | Chỉ có khai báo được chọn | Class trước, method sau |
| Method có @SqlMergeMode(OVERRIDE) | Giữ override | Ghi đè chế độ MERGE của class |
| Method có @SqlMergeMode(MERGE) | Kết hợp hai cấp | Giữ chế độ merge |

Có thể nhớ quy tắc theo cách sau:

- OVERRIDE: method có @Sql riêng sẽ thay thế cấu hình class cho method đó.
- MERGE: method có @Sql riêng sẽ bổ sung vào cấu hình class cho method đó.
- Method không có @Sql riêng: script class vẫn được áp dụng, bất kể chế độ merge.
- Method-level @SqlMergeMode quyết định cách xử lý cho method cụ thể nếu có khai báo.

## 7. @SqlMergeMode và executionPhase

@Sql có thuộc tính executionPhase để chỉ định thời điểm chạy script:

- BEFORE_TEST_METHOD: trước mỗi test method; đây là giá trị mặc định.
- AFTER_TEST_METHOD: sau mỗi test method.

@SqlMergeMode quyết định có kết hợp các khai báo cấp class và method hay không. executionPhase quyết định từng khai báo được thực thi ở thời điểm nào. Hai cấu hình này giải quyết hai câu hỏi khác nhau.

Ví dụ, class chuẩn bị dữ liệu trước test, còn method chạy script cleanup sau test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Sql(
        scripts = "/sql/inventory-baseline.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class InventoryLifecycleTest {
    @Test
    @Sql(
            scripts = "/sql/inventory-after-test.sql",
            executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
    )
    void performsAnInventoryOperation() {
        // SQL baseline chạy trước test method.
        // SQL cleanup chạy sau test method.
    }
}
~~~

Khai báo class và method được kết hợp theo chế độ MERGE, nhưng mỗi script vẫn chạy ở phase của chính nó. Script BEFORE_TEST_METHOD được xử lý ở callback trước method; script AFTER_TEST_METHOD được xử lý ở callback sau method.

Nếu class và method đều khai báo script ở cùng phase, với MERGE, script class chạy trước script method. Nếu chúng thuộc hai phase khác nhau, phase quyết định thời điểm thực thi; không nên suy luận rằng tất cả script class luôn chạy trước mọi script method bất kể phase.

Có thể khai báo nhiều @Sql ở cùng cấp bằng cách lặp annotation:

~~~java
@Sql("/sql/clear-inventory.sql")
@Sql("/sql/inventory-baseline.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class MultipleSqlScriptsTest {
    @Test
    @Sql("/sql/inventory-special-case.sql")
    void usesSeveralScripts() {
        // Các khai báo cùng cấp được xử lý theo quy tắc của @Sql
        // và khai báo cấp method được merge với cấp class.
    }
}
~~~

@Sql là annotation repeatable. Có thể dùng nhiều khai báo để tách nhiệm vụ dọn dữ liệu, tạo dữ liệu tham chiếu và thêm dữ liệu tình huống. Việc chia script nên phản ánh các bước chuẩn bị có ý nghĩa, không nên làm cho thứ tự phụ thuộc trở nên khó theo dõi.

## 8. Phân biệt @SqlMergeMode với @SqlConfig

@SqlMergeMode điều khiển việc kết hợp các khai báo @Sql ở cấp class và method. @SqlConfig cấu hình cách thực thi SQL, ví dụ chọn datasource, transaction manager, transaction mode, encoding, comment prefix hoặc separator.

Hai annotation không thay thế nhau:

| Annotation | Câu hỏi được giải quyết |
|---|---|
| @SqlMergeMode | Script cấp class và method có được kết hợp hay method override class? |
| @SqlConfig | Spring thực thi script bằng datasource, transaction và quy tắc phân tích SQL nào? |

Ví dụ cấu hình SQL:

~~~java
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlConfig;

@Sql(
        scripts = "/sql/inventory-baseline.sql",
        config = @SqlConfig(
                dataSource = "testDataSource",
                transactionManager = "testTransactionManager",
                encoding = "UTF-8"
        )
)
~~~

Trong một test class, có thể kết hợp @SqlMergeMode(MERGE) với @SqlConfig. Một annotation quyết định tập script được áp dụng; annotation còn lại quyết định cách script được chạy.

Nếu method cần cấu hình SQL khác class, hãy khai báo config trên @Sql của method theo nhu cầu. Không nên kỳ vọng @SqlMergeMode sẽ tự hợp nhất hoặc ghi đè từng thuộc tính của @SqlConfig; đó là một cơ chế cấu hình riêng.

## 9. Tương tác với transaction của test

SQL script thường được chạy trong bối cảnh transaction do Spring TestContext quản lý. Nếu test method có @Transactional, Spring thường bắt đầu test-managed transaction trước khi test chạy và rollback sau method theo mặc định. SqlScriptsTestExecutionListener thực thi script ở các callback tương ứng, phối hợp với transaction listener theo thứ tự của TestContext.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.annotation.Transactional;

@SpringJUnitConfig(DatabaseTestConfig.class)
@Transactional
@Sql("/sql/inventory-baseline.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class TransactionalInventoryTest {
    @Test
    @Sql("/sql/inventory-special-case.sql")
    void readsTheMergedDataset() {
        // Script class và method chạy trong ngữ cảnh transaction
        // do test quản lý theo cấu hình mặc định phù hợp.
    }
}
~~~

Với cấu hình transaction thông thường, dữ liệu setup tham gia transaction của test và được rollback khi test kết thúc. Tuy nhiên, hành vi cụ thể phụ thuộc vào transaction manager, datasource và @SqlConfig. Nếu script được cấu hình chạy trong transaction độc lập, hoặc code ứng dụng mở transaction riêng, dữ liệu có thể không nằm trong transaction mà test rollback.

@SqlConfig(transactionMode = SqlConfig.TransactionMode.ISOLATED) yêu cầu script chạy trong transaction riêng và commit transaction đó khi hoàn tất. Chế độ này có thể hữu ích khi dữ liệu setup phải tồn tại ngoài test-managed transaction, nhưng cần cân nhắc kỹ vì dữ liệu có thể còn lại sau test và ảnh hưởng lần chạy sau.

Không nên dùng ISOLATED chỉ để tránh hiểu cơ chế rollback. Trước tiên hãy xác định dữ liệu cần sống trong phạm vi test hay phải tồn tại độc lập. Dùng transaction mặc định cho dữ liệu fixture cần rollback thường đơn giản hơn.

## 10. Lưu ý về thứ tự chuẩn bị và dọn dữ liệu

Khi dùng MERGE, class-level SQL được kết hợp với method-level SQL. Tuy nhiên, việc script nào chạy trước còn phụ thuộc executionPhase và thứ tự khai báo trong cùng một nhóm. Hãy thiết kế script theo các bước có thể đọc được:

1. Xóa hoặc chuẩn bị dữ liệu nền theo phạm vi test.
2. Tạo các bản ghi tham chiếu mà tình huống cần.
3. Thêm dữ liệu riêng cho test method.
4. Chạy assertion trong test.
5. Dọn dữ liệu nếu cleanup không được transaction rollback đảm nhiệm.

Nếu class-level script chạy trước mọi method, dữ liệu nó tạo phải phù hợp với tất cả method sử dụng cấu hình đó. Nếu một method cần database hoàn toàn trống, có thể dùng OVERRIDE và cung cấp script riêng, hoặc tổ chức setup theo phase để làm rõ ý định.

Tránh để class-level script tạo một bản ghi có khóa cố định mà method-level script lại chèn bản ghi trùng khóa. Trong chế độ MERGE, cả hai script đều chạy; xung đột khóa là kết quả tự nhiên nếu dữ liệu không được thiết kế để bổ sung cho nhau.

Một số chiến lược giảm xung đột:

- Dùng khóa khác nhau cho dữ liệu nền và dữ liệu tình huống.
- Dùng UPDATE khi mục đích là điều chỉnh một bản ghi nền đã được tạo.
- Chỉ dùng DELETE theo khóa hoặc nhóm dữ liệu test có kiểm soát.
- Dùng transaction rollback để cô lập dữ liệu nếu phù hợp.
- Chọn OVERRIDE khi method phải thay toàn bộ fixture cấp class.

## 11. Ví dụ tổng hợp: class dùng MERGE, method có ngoại lệ

Giả sử test repository khách hàng có dữ liệu tham chiếu chung, nhưng một method cần chạy trên bộ dữ liệu độc lập để kiểm tra trường hợp trùng email.

Script cấp class:

~~~sql
-- /sql/customer-reference-data.sql
DELETE FROM customer;

INSERT INTO customer(id, email, status)
VALUES (1, 'active@example.test', 'ACTIVE');

INSERT INTO customer(id, email, status)
VALUES (2, 'suspended@example.test', 'SUSPENDED');
~~~

Script bổ sung cho method:

~~~sql
-- /sql/customer-duplicate-email.sql
INSERT INTO customer(id, email, status)
VALUES (3, 'duplicate@example.test', 'ACTIVE');

INSERT INTO customer(id, email, status)
VALUES (4, 'duplicate@example.test', 'SUSPENDED');
~~~

Script độc lập:

~~~sql
-- /sql/customer-isolated-empty-case.sql
DELETE FROM customer;
~~~

Test class:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.SqlMergeMode;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(CustomerRepositoryTestConfig.class)
@Sql("/sql/customer-reference-data.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class CustomerRepositoryMergeTest {
    @Test
    @Sql("/sql/customer-duplicate-email.sql")
    void findsAllCustomersWithTheSameEmail() {
        // reference data được tạo trước, sau đó thêm hai bản ghi trùng email.
    }

    @Test
    void findsTheActiveCustomer() {
        // Chỉ dùng dữ liệu tham chiếu cấp class.
    }

    @Test
    @Sql("/sql/customer-isolated-empty-case.sql")
    @SqlMergeMode(SqlMergeMode.MergeMode.OVERRIDE)
    void returnsNoCustomerForAnEmptyDatabase() {
        // Chỉ chạy script method, không chạy reference data.
    }
}
~~~

Hai method đầu dùng MERGE: method đầu bổ sung hai khách hàng trùng email, method thứ hai dùng riêng dữ liệu tham chiếu. Method cuối đặt OVERRIDE để bỏ dữ liệu nền của class và chỉ chạy script dành cho database rỗng.

Ví dụ này thể hiện cách đặt một quy ước chung ở cấp class và khai báo ngoại lệ ngay tại method. Người đọc test có thể nhận ra ngay method nào kế thừa fixture, method nào bổ sung fixture và method nào thay thế hoàn toàn fixture chung.

## 12. Các lỗi thường gặp

### Nghĩ rằng method-level @Sql luôn bổ sung script class

Đây là nhầm lẫn phổ biến nhất. Mặc định là OVERRIDE, vì vậy method có @Sql riêng sẽ không chạy các khai báo @Sql cấp class. Nếu cần kết hợp, khai báo @SqlMergeMode(MERGE).

### Dùng MERGE nhưng script method chèn trùng khóa

Trong chế độ merge, cả script class và method đều chạy. Nếu cùng chèn một khóa chính hoặc giá trị unique, database có thể báo lỗi constraint. Kiểm tra dữ liệu nền và dữ liệu riêng có bổ sung cho nhau không.

### Đặt MERGE nhưng quên context test

@SqlMergeMode là annotation của Spring TestContext. Test cần được tích hợp với Spring TestContext phù hợp để listener xử lý @Sql và merge mode. Nếu chỉ chạy JUnit test thuần mà không có Spring Extension/TestContext, các annotation này không tự thực thi script.

### Dùng nhầm package annotation

@Sql và @SqlMergeMode thuộc org.springframework.test.context.jdbc. Kiểm tra import khi IDE tự động hoàn thành annotation hoặc khi dự án có thư viện kiểm thử khác.

### Cho rằng MERGE thay đổi executionPhase

MERGE chỉ điều khiển việc kết hợp các khai báo. Nó không đổi BEFORE_TEST_METHOD thành AFTER_TEST_METHOD hoặc ngược lại. Hãy đọc executionPhase của từng khai báo.

### Cho rằng @SqlConfig được merge bởi @SqlMergeMode

@SqlMergeMode không phải cơ chế hợp nhất các thuộc tính cấu hình SQL. Nó quyết định khai báo script ở cấp nào được áp dụng. Datasource, transaction manager, encoding và transaction mode vẫn được điều khiển bằng @SqlConfig.

### Dùng script cleanup nhưng dữ liệu vẫn còn

Kiểm tra transaction mode, test-managed transaction, script cleanup đang ở phase nào và script có thực sự chạy không. Nếu dữ liệu được commit trong transaction độc lập, rollback của test không xóa dữ liệu đó.

### Dùng @DirtiesContext để xử lý dữ liệu SQL

@DirtiesContext loại ApplicationContext khỏi cache, không phải lệnh xóa bản ghi trong database. Hãy dùng SQL cleanup hoặc transaction rollback cho dữ liệu; chỉ dùng @DirtiesContext khi context thực sự bị thay đổi và không thể tái sử dụng an toàn.

## 13. Chọn chế độ phù hợp

| Nhu cầu | Cách cấu hình |
|---|---|
| Method cần thay hoàn toàn fixture class | Dùng mặc định OVERRIDE hoặc khai báo tường minh |
| Mọi method cần dữ liệu nền rồi thêm dữ liệu riêng | Đặt @SqlMergeMode(MERGE) ở cấp class |
| Một method trong class MERGE cần fixture độc lập | Đặt @SqlMergeMode(OVERRIDE) trên method |
| Class mặc định OVERRIDE nhưng một method cần kết hợp | Đặt @SqlMergeMode(MERGE) trên method |
| Script chạy trước test | executionPhase = BEFORE_TEST_METHOD hoặc dùng mặc định |
| Script chạy sau test | executionPhase = AFTER_TEST_METHOD |
| Cần datasource hoặc transaction riêng | Cấu hình @SqlConfig phù hợp |

Một cách chọn thực tế là bắt đầu từ dữ liệu mà test cần:

- Nếu method cần đúng một bộ dữ liệu độc lập, OVERRIDE thể hiện rõ rằng fixture method thay thế fixture class.
- Nếu class có dữ liệu tham chiếu mà mọi method đều cần, MERGE giúp method chỉ khai báo phần dữ liệu bổ sung.
- Nếu chỉ một số method cần merge, giữ chế độ mặc định của class và bật MERGE riêng cho những method đó.
- Nếu dữ liệu phải được dọn sau test, xác định rõ transaction có rollback được hay cần script ở AFTER_TEST_METHOD.

## 14. Nguyên tắc cần ghi nhớ

- Mặc định của @SqlMergeMode là OVERRIDE.
- Với OVERRIDE, khi method có @Sql, các khai báo @Sql cấp class không áp dụng cho method đó.
- Với MERGE, script class và method cùng được thực thi; script class chạy trước script method trong cùng một pha.
- Có thể đặt @SqlMergeMode ở cấp class để áp dụng cho cả class, hoặc ở cấp method để ghi đè chế độ của class.
- Method không có @Sql riêng vẫn dùng script cấp class.
- executionPhase quyết định script chạy trước hay sau test method; @SqlMergeMode không thay đổi phase.
- @SqlConfig cấu hình cách thực thi script, độc lập với quy tắc merge.
- Kiểm tra khóa chính, unique constraint và dữ liệu nền khi dùng MERGE để tránh script xung đột.
- Hiểu transaction mode và cleanup để biết dữ liệu có được rollback hay tồn tại sau test.
- Không dùng @DirtiesContext thay cho việc dọn dữ liệu database.

@SqlMergeMode giúp tổ chức fixture SQL theo hai cấp mà vẫn kiểm soát rõ dữ liệu của từng test. OVERRIDE phù hợp khi method cần một bộ dữ liệu riêng; MERGE phù hợp khi method cần kế thừa dữ liệu nền của class rồi bổ sung tình huống cụ thể. Đặt chế độ ở đúng phạm vi và hiểu thứ tự script sẽ giúp test database dễ đọc, ít xung đột và có thể tái sử dụng fixture chung một cách có chủ đích.

## Tài liệu tham khảo

- [Spring Framework Reference — Executing SQL Scripts](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html)
- [Spring Framework Javadoc — SqlMergeMode](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/jdbc/SqlMergeMode.html)
- [Spring Framework Javadoc — Sql](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/jdbc/Sql.html)
- [Spring Framework Javadoc — SqlConfig](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/jdbc/SqlConfig.html)

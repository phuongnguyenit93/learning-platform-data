# Chuẩn bị schema và dữ liệu kiểm thử có chủ đích

Một test làm việc với database chỉ đáng tin cậy khi nó biết rõ cấu trúc dữ liệu nào đang tồn tại, dữ liệu nào được tạo cho kịch bản và dữ liệu nào phải được dọn sau khi chạy. Schema và test data là hai phần khác nhau của môi trường kiểm thử: schema định nghĩa bảng, cột, khóa, index, constraint và quan hệ; test data là các bản ghi cụ thể được chuẩn bị để kiểm tra hành vi.

Trong Spring Framework Testing, có thể chuẩn bị database bằng SQL script, bằng code trong fixture hoặc bằng công cụ tạo database dành cho test. Spring TestContext Framework cung cấp `@Sql` và `@SqlConfig` để khai báo việc chạy script theo vòng đời test. Các lựa chọn này cần được kết hợp với transaction, context cache và cách cô lập dữ liệu để test có thể chạy độc lập, lặp lại và theo thứ tự bất kỳ.

## Phân biệt schema, dữ liệu nền và dữ liệu theo kịch bản

Trước khi viết SQL, hãy phân loại thứ cần chuẩn bị:

| Thành phần | Nội dung | Ví dụ |
|---|---|---|
| Schema | Cấu trúc database và các ràng buộc | Bảng customer, khóa chính, khóa ngoại, unique constraint, index |
| Dữ liệu tham chiếu | Dữ liệu nền được nhiều kịch bản sử dụng | Quốc gia, loại tiền tệ, trạng thái đơn hàng |
| Dữ liệu theo kịch bản | Bản ghi chỉ phục vụ một hành vi cần kiểm tra | Khách hàng C-100, đơn hàng chưa thanh toán |
| Dữ liệu phát sinh trong test | Bản ghi do chính hành động đang kiểm tra tạo ra | Đơn hàng được service lưu trong test |

Ví dụ, test kiểm tra truy vấn tìm khách hàng theo email cần một bảng customer có cột email và một bản ghi cụ thể. Test kiểm tra unique constraint cần hai lần ghi có cùng email để xác nhận database từ chối bản ghi trùng. Hai kịch bản có thể dùng cùng schema nhưng cần bộ dữ liệu khác nhau.

Một cách tổ chức rõ ràng là chia thành ba lớp:

1. **Schema nền:** được tạo một lần cho database hoặc test suite.
2. **Dữ liệu tham chiếu:** được nạp sau schema nếu nhiều test cần chung và không sửa đổi dữ liệu đó.
3. **Dữ liệu theo test:** được tạo trước từng test method hoặc ngay trong test, sau đó rollback hoặc cleanup.

Không nên trộn dữ liệu của một kịch bản cụ thể vào script schema. Schema nên mô tả cấu trúc; fixture dữ liệu nên mô tả điều kiện đầu vào của test.

## Xác định schema mà test cần sử dụng

Test cần chạy trên schema phù hợp với ứng dụng. Nếu ứng dụng có migration scripts, cách đáng tin cậy là dựng schema test bằng cùng chuỗi migration mà ứng dụng sử dụng, thay vì tự viết một schema đơn giản khác rồi kết luận database production hoạt động đúng.

Có thể dùng Flyway hoặc Liquibase trong cấu hình kiểm thử để áp dụng migration lên database test. Đây là công cụ migration, không phải API cốt lõi của Spring TestContext Framework. Spring Test có trách nhiệm khởi tạo context và kết nối test với database; migration tool chịu trách nhiệm đưa schema tới phiên bản cần thiết.

Khi chọn schema cho test, cần lưu ý:

- Bảng và cột phải phản ánh phiên bản schema mà code đang sử dụng.
- Kiểu dữ liệu cần tương thích với database thực tế, đặc biệt với decimal, timestamp, JSON, sequence và generated identity.
- Khóa ngoại và unique constraint nên được giữ nếu hành vi test phụ thuộc vào chúng.
- Index có thể ảnh hưởng kế hoạch truy vấn và hiệu năng; test hiệu năng không nên dựa vào schema giản lược không có index.
- Các trigger, view, stored procedure và default value cần được tạo nếu ứng dụng dựa vào chúng.
- Nếu dùng nhiều schema hoặc tenant, test phải chỉ rõ schema đang truy cập và cách reset dữ liệu.

Embedded database như H2 hữu ích cho một số test nhanh, nhưng không thay thế hoàn toàn database engine production. SQL dialect, kiểu dữ liệu, isolation, locking, sequence, constraint và hành vi DDL có thể khác. Khi test cần chứng minh truy vấn hoặc migration tương thích với PostgreSQL, MySQL hay một engine cụ thể, hãy dùng chính engine đó trong môi trường test, thường qua Testcontainers hoặc database test chuyên dụng.

## Chuẩn bị schema bằng SQL script

Spring TestContext Framework có thể thực thi SQL script bằng `@Sql`. Cách này hữu ích khi schema hoặc fixture có nhiều câu lệnh, cần đọc được bằng mắt và được chia sẻ giữa nhiều test.

Ví dụ một script schema:

~~~sql
create table customer (
    id bigint primary key,
    email varchar(255) not null unique,
    name varchar(120) not null,
    active boolean not null
);

create table customer_order (
    id bigint primary key,
    customer_id bigint not null,
    status varchar(30) not null,
    total_amount decimal(12, 2) not null,
    constraint fk_order_customer
        foreign key (customer_id) references customer(id)
);
~~~

Test có thể yêu cầu Spring chạy script trước khi các test method trong class bắt đầu:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Sql(
    scripts = "/sql/customer-schema.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS
)
@Sql(
    scripts = "/sql/customer-drop-schema.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_CLASS
)
class CustomerRepositoryIntegrationTest {
    // Các test sử dụng schema đã chuẩn bị.
}
~~~

Các phase ở cấp class như `BEFORE_TEST_CLASS` và `AFTER_TEST_CLASS` có từ Spring Framework 6.1. Với phiên bản cũ hơn, có thể dùng initializer, cấu hình database hoặc lifecycle fixture phù hợp để chuẩn bị schema trước khi test method chạy.

Script dọn schema phải phù hợp với thứ tự phụ thuộc. Nếu bảng order có khóa ngoại tới customer, cần xóa bảng con trước bảng cha:

~~~sql
drop table if exists customer_order;
drop table if exists customer;
~~~

Cú pháp DDL có thể khác giữa database engine. Nếu cần hỗ trợ nhiều engine, hãy dùng migration hoặc script riêng theo dialect, không giả định một câu lệnh SQL có cùng hành vi ở mọi database.

### Schema một lần và fixture từng method

Không phải test nào cũng cần tạo lại schema. Schema thường ổn định trong suốt vòng đời một ApplicationContext hoặc database test, trong khi dữ liệu theo kịch bản cần được cô lập theo từng test method.

Một cấu trúc thư mục dễ đọc:

~~~text
src/test/resources/
  sql/
    schema/
      customer-schema.sql
      customer-drop-schema.sql
    reference/
      countries.sql
      currencies.sql
    fixtures/
      customer-active.sql
      customer-inactive.sql
      orders-for-customer.sql
    cleanup/
      customer-fixture-cleanup.sql
~~~

Tên file nên mô tả mục đích dữ liệu. Tránh một file lớn tên `test-data.sql` chứa hàng trăm bản ghi không rõ test nào cần.

## @Sql: chạy script theo vòng đời test

`@Sql` thuộc package `org.springframework.test.context.jdbc` và cho phép khai báo script hoặc câu lệnh SQL cần thực thi cho test class hoặc test method.

Một ví dụ chuẩn bị fixture cho từng test method:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    @Sql("/sql/fixtures/customer-active.sql")
    void findsActiveCustomer() {
        var result = repository.findActiveByEmail("lan@example.test");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getName()).isEqualTo("Lan");
    }
}
~~~

Mặc định, script của `@Sql` được thực thi ở phase `BEFORE_TEST_METHOD`. Vì vậy, dữ liệu trong file fixture có sẵn trước khi test method chạy.

Có thể khai báo nhiều script:

~~~java
@Test
@Sql(scripts = {
    "/sql/fixtures/customer-active.sql",
    "/sql/fixtures/orders-for-customer.sql"
})
void findsCustomerOrders() {
    // Kiểm tra truy vấn đơn hàng.
}
~~~

Thứ tự khai báo script có ý nghĩa nếu script sau phụ thuộc dữ liệu do script trước tạo ra. Ví dụ, script customer phải chạy trước script order nếu order tham chiếu customer qua khóa ngoại.

`@Sql` cũng cho phép khai báo trực tiếp câu lệnh SQL bằng thuộc tính `statements`:

~~~java
@Test
@Sql(statements = {
    "insert into customer(id, email, name, active) " +
        "values (9101, 'lan@example.test', 'Lan', true)"
})
void loadsCustomer() {
    // ...
}
~~~

Với fixture ngắn, `statements` tiện lợi. Với dữ liệu dài hoặc được nhiều test dùng, file script thường dễ đọc và quản lý hơn.

## Các execution phase của @Sql

`Sql.ExecutionPhase` xác định thời điểm script được thực thi:

| Phase | Thời điểm | Mục đích |
|---|---|---|
| `BEFORE_TEST_METHOD` | Trước mỗi test method | Chuẩn bị dữ liệu riêng cho method |
| `AFTER_TEST_METHOD` | Sau mỗi test method | Dọn dữ liệu hoặc thực hiện cleanup |
| `BEFORE_TEST_CLASS` | Trước các test method của class | Chuẩn bị schema hoặc dữ liệu nền dùng chung trong class |
| `AFTER_TEST_CLASS` | Sau các test method của class | Xóa schema hoặc tài nguyên database của class |

Hai phase theo class được hỗ trợ từ Spring Framework 6.1. Với phase theo method, có thể khai báo cả script setup và cleanup:

~~~java
@Test
@Sql(
    scripts = "/sql/fixtures/customer-active.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
    scripts = "/sql/cleanup/customer-active-cleanup.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
void readsCustomer() {
    // ...
}
~~~

Không phải lúc nào cũng cần script cleanup. Nếu fixture và hành động của test nằm trong test-managed transaction rồi transaction được rollback, dữ liệu có thể được hoàn tác tự động. Cleanup script hữu ích khi test commit dữ liệu, dùng transaction độc lập hoặc thao tác với trạng thái nằm ngoài transaction.

Nếu script cleanup xóa dữ liệu đã commit, nó phải xác định đúng phạm vi dữ liệu của test. Không dùng câu lệnh xóa rộng như `delete from customer` trên database dùng chung.

## @SqlConfig: điều khiển cách thực thi SQL script

`@SqlConfig` cho phép cấu hình cách Spring đọc và chạy script, ví dụ encoding, separator, comment prefix, datasource, transaction manager và transaction mode.

Có thể cấu hình ở cấp class để áp dụng cho các khai báo `@Sql` trong class:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@SqlConfig(
    encoding = "UTF-8",
    separator = ";",
    commentPrefix = "--"
)
class CustomerRepositoryTest {
    // ...
}
~~~

Hoặc cấu hình riêng cho một bộ script:

~~~java
@Test
@Sql(
    scripts = "/sql/fixtures/customer-active.sql",
    config = @SqlConfig(
        encoding = "UTF-8",
        separator = ";",
        commentPrefix = "--"
    )
)
void findsCustomer() {
    // ...
}
~~~

Một số thuộc tính đáng chú ý:

| Thuộc tính | Ý nghĩa |
|---|---|
| `dataSource` | Tên bean DataSource dùng để thực thi script |
| `transactionManager` | Tên bean PlatformTransactionManager |
| `transactionMode` | Cách script tham gia hoặc tạo transaction |
| `encoding` | Encoding của resource script |
| `separator` | Ký tự phân tách câu lệnh SQL |
| `commentPrefix` | Tiền tố comment một dòng |
| `blockCommentStartDelimiter` / `blockCommentEndDelimiter` | Dấu bắt đầu và kết thúc comment nhiều dòng |
| `errorMode` | Cách xử lý lỗi khi chạy script |

Nếu context có nhiều datasource hoặc transaction manager, cần chỉ định bean phù hợp. Nếu để Spring suy luận, tên và kiểu bean trong context phải đủ rõ để chọn đúng database.

### TransactionMode.INFERRED và ISOLATED

`SqlConfig.TransactionMode` có hai lựa chọn chính:

- `INFERRED`: Spring cố gắng suy luận cách chạy script dựa trên transaction hiện có và transaction manager trong context. Nếu test đang chạy trong test-managed transaction, script có thể tham gia transaction đó. Nếu không có transaction hiện tại nhưng có transaction manager phù hợp, Spring có thể tạo transaction cho việc thực thi script.
- `ISOLATED`: script được chạy trong transaction độc lập, với propagation kiểu `REQUIRES_NEW`. Transaction này được commit độc lập theo cơ chế transaction manager, không bị rollback cùng test-managed transaction bên ngoài.

Ví dụ yêu cầu fixture được commit độc lập:

~~~java
@Test
@Sql(
    scripts = "/sql/fixtures/reference-customer.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED
    )
)
void readsCommittedFixture() {
    // Fixture được tạo trong transaction riêng.
}
~~~

Không nên chọn `ISOLATED` chỉ để tránh hiểu transaction. Khi fixture cần biến mất sau test, chạy trong test-managed transaction và rollback thường đơn giản hơn. Transaction độc lập có thể để lại dữ liệu sau khi test kết thúc, do đó cần cleanup rõ ràng.

Nếu không có transaction manager phù hợp, Spring không thể thực hiện các yêu cầu transaction của script như mong muốn. Hãy kiểm tra datasource và transaction manager trong context khi gặp lỗi khởi tạo hoặc thực thi script.

## Kết hợp @Sql với @Transactional

Spring Test hỗ trợ test-managed transaction khi test class hoặc method được đánh dấu `@Transactional` và có transaction manager phù hợp. Mặc định, transaction do Spring Test quản lý sẽ rollback khi test kết thúc.

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class CustomerRepositoryTransactionalTest {

    @Autowired
    CustomerRepository repository;

    @Test
    @Sql("/sql/fixtures/customer-active.sql")
    void readsFixtureInsideTestTransaction() {
        var customer = repository.findByEmail("lan@example.test");

        assertThat(customer).isPresent();
    }
}
~~~

Với transaction mode mặc định là inferred, script setup thường tham gia transaction test-managed. Test đọc dữ liệu trong cùng transaction, và rollback cuối test hoàn tác dữ liệu đã tạo trong transaction đó.

Cần phân biệt các trường hợp:

1. **Fixture tham gia test-managed transaction:** rollback của test có thể hoàn tác dữ liệu fixture và thay đổi của test.
2. **Script dùng transaction ISOLATED:** dữ liệu có thể đã commit riêng và tồn tại sau rollback của test.
3. **Test được đánh dấu @Commit hoặc @Rollback(false):** thay đổi trong transaction test có thể được commit, nên phải có cleanup.
4. **Tác động ngoài database transaction:** ghi file, gửi HTTP, message hoặc công việc chạy thread khác không tự động được rollback.
5. **Database engine có hành vi DDL riêng:** một số lệnh DDL có thể implicit commit hoặc không rollback như thao tác DML thông thường.

Nếu test cần kiểm tra commit thật, hãy thiết kế dữ liệu riêng và cleanup rõ ràng. Đừng dựa vào rollback mặc định khi code thực tế mở transaction mới hoặc commit độc lập.

## Kết hợp script cấp class và cấp method

Có thể khai báo dữ liệu nền ở class và fixture riêng ở method. Mặc định, khi có cả class-level và method-level `@Sql`, khai báo ở method có thể thay thế khai báo ở class. `@SqlMergeMode` cho phép chọn hành vi merge.

Ví dụ giữ script nền ở class và bổ sung script theo method:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Sql("/sql/reference/currencies.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class PaymentRepositoryTest {

    @Test
    @Sql("/sql/fixtures/payment-pending.sql")
    void findsPendingPayment() {
        // Script currencies và payment-pending cùng được áp dụng.
    }
}
~~~

Nếu không dùng `@SqlMergeMode(MERGE)`, method-level `@Sql` mặc định có thể override khai báo ở class-level. Có thể đặt `@SqlMergeMode` ở class để áp dụng chung hoặc ở method để thay đổi cho một kịch bản cụ thể.

Merge hữu ích khi mọi test đều cần dữ liệu tham chiếu, còn mỗi method chỉ thêm fixture riêng. Tuy nhiên, nếu script nền tạo dữ liệu mutable hoặc bị test sửa, việc merge có thể làm trạng thái rò rỉ. Dữ liệu nền nên bất biến trong các test hoặc được khôi phục theo transaction/cleanup.

## Chuẩn bị dữ liệu bằng code và fixture builder

Không phải mọi test đều cần SQL script. Nếu dữ liệu đơn giản và hành vi đang kiểm tra liên quan trực tiếp đến repository hoặc service, tạo dữ liệu qua API của ứng dụng có thể giúp test thể hiện rõ hơn ý định.

~~~java
@Test
@Transactional
void createsCustomerAndFindsIt() {
    Customer customer = new Customer(
        "C-9101",
        "lan@example.test",
        "Lan",
        true
    );

    repository.save(customer);

    var result = repository.findByEmail("lan@example.test");

    assertThat(result).isPresent();
}
~~~

Cách này phù hợp khi test muốn kiểm tra chính thao tác lưu của repository hoặc service. Nếu mục tiêu chỉ là chuẩn bị trạng thái database cho một truy vấn, SQL script có thể trực tiếp và ngắn gọn hơn.

Một fixture builder giúp tạo dữ liệu có cấu trúc mà không lặp constructor dài:

~~~java
class CustomerFixture {

    static Customer activeCustomer(String id, String email) {
        return new Customer(id, email, "Lan", true);
    }

    static Customer inactiveCustomer(String id, String email) {
        return new Customer(id, email, "Lan", false);
    }
}
~~~

Test gọi builder để tạo object mới cho mỗi kịch bản. Tránh dùng một object mutable static rồi sửa field qua nhiều test, vì các test có thể vô tình chia sẻ cùng một tham chiếu.

Nên chọn cách tạo dữ liệu theo mục tiêu:

| Mục tiêu | Cách phù hợp |
|---|---|
| Tạo cấu trúc database và constraint | Migration hoặc schema SQL script |
| Chuẩn bị nhiều bản ghi có quan hệ phức tạp | SQL fixture hoặc builder có quan hệ rõ |
| Kiểm tra chính thao tác ghi qua repository | Tạo object và gọi repository trong test |
| Kiểm tra truy vấn trên dữ liệu có sẵn | Fixture SQL hoặc data builder trước hành động truy vấn |
| Kiểm tra migration | Chạy migration trên database test sạch |
| Kiểm tra constraint do database thực thi | Ghi dữ liệu thật vào database test và xác nhận lỗi |

## Thiết kế test data ổn định và có thể lặp lại

Dữ liệu kiểm thử nên được chọn có chủ đích. Một fixture tốt giúp người đọc hiểu ngay điều kiện của test và không phụ thuộc vào dữ liệu còn sót từ lần chạy trước.

### Dùng dữ liệu tối thiểu nhưng đủ ý nghĩa

Chỉ tạo các bản ghi cần thiết cho hành vi đang kiểm tra. Nếu test tìm customer theo email, không cần tạo thêm hàng chục order, payment và shipment nếu chúng không tham gia truy vấn.

Dữ liệu quá lớn khiến test chậm và khó biết bản ghi nào quyết định kết quả. Dữ liệu quá đơn giản lại có thể bỏ sót quan hệ, constraint hoặc trường hợp biên. Hãy giữ đúng các thuộc tính cần thiết cho điều kiện kiểm thử.

### Chọn khóa và định danh không va chạm

Nếu nhiều test chạy trên cùng database, dùng ID hoặc key có phạm vi riêng cho từng test. Có thể dùng mã định danh cố định trong database/schema riêng của test, hoặc tạo UUID khi cần tránh trùng giữa các lần chạy.

~~~java
String email = "customer-" + UUID.randomUUID() + "@example.test";
~~~

Dữ liệu duy nhất giảm xung đột, nhưng không thay thế cleanup. Nếu test commit dữ liệu, những bản ghi đó vẫn tồn tại và có thể làm database phình to.

### Khai báo dữ liệu có quan hệ theo thứ tự hợp lệ

Nếu bảng order có foreign key tới customer, phải tạo customer trước order. Khi cleanup, xóa order trước customer trừ khi database có cơ chế cascade được chủ đích sử dụng.

Không nên vô hiệu hóa constraint chỉ để script fixture dễ chạy. Test cần phản ánh các điều kiện mà ứng dụng thực sự phải tuân theo.

### Tránh phụ thuộc vào thứ tự tự tăng

Đừng giả định bản ghi đầu tiên luôn có ID là 1 hoặc sequence luôn reset sau mỗi test. Nhiều database không đảm bảo sequence/identity quay về giá trị cũ khi transaction rollback. Nếu test cần một bản ghi cụ thể, hãy truy vấn bằng business key hoặc dùng ID được tạo có chủ đích.

### Dùng giá trị thời gian rõ ràng

Không nên dùng thời gian hệ thống hiện tại làm fixture nếu test cần kiểm tra hạn thanh toán, ngày tạo hoặc thời điểm hết hạn. Hãy ghi timestamp cụ thể và timezone rõ ràng để kết quả ổn định giữa máy developer và CI.

### Không dùng dữ liệu cá nhân thật

Fixture nên dùng dữ liệu giả lập, có ý nghĩa và không chứa thông tin khách hàng thật. Email dùng miền dành cho test, tên và số định danh cần được tạo cho mục đích minh họa.

## Dọn dữ liệu an toàn

Có ba chiến lược phổ biến:

1. **Rollback transaction:** phù hợp khi toàn bộ thao tác ghi tham gia transaction do Spring Test quản lý.
2. **Cleanup script:** phù hợp khi test commit hoặc fixture được tạo ngoài transaction của test.
3. **Database/schema riêng:** phù hợp khi test cần cô lập mạnh, chạy song song hoặc kiểm tra migration/DDL.

Ví dụ cleanup theo business key:

~~~sql
delete from customer_order
where customer_id = 9101;

delete from customer
where id = 9101;
~~~

Cleanup có phạm vi rõ và tôn trọng khóa ngoại. Nếu dùng ID động, có thể truyền giá trị qua fixture script được sinh theo test hoặc dùng một namespace chung cho test run.

Tránh các thao tác sau trên database dùng chung:

- `delete from customer` không có điều kiện.
- `truncate table` khi test khác có thể đang sử dụng bảng.
- Drop schema chung trong khi test khác đang chạy.
- Reset sequence toàn cục làm thay đổi giả định của test khác.
- Dùng chung khóa cố định giữa các test chạy song song.

Nếu cần reset toàn bộ database, hãy thực hiện trên database hoặc schema chỉ thuộc test run đó.

## @SqlConfig và script nhiều câu lệnh

Một SQL script có thể chứa comment, câu lệnh nhiều dòng hoặc thủ tục có dấu phân cách đặc biệt. `@SqlConfig` cho phép điều chỉnh separator và delimiter để Spring phân tích script đúng.

Ví dụ:

~~~java
@Sql(
    scripts = "/sql/fixtures/customer-procedure.sql",
    config = @SqlConfig(
        encoding = "UTF-8",
        separator = ";",
        commentPrefix = "--",
        blockCommentStartDelimiter = "/*",
        blockCommentEndDelimiter = "*/"
    )
)
~~~

Nếu script chứa stored procedure hoặc block có dấu chấm phẩy bên trong, separator mặc định có thể không phù hợp. Cần cấu hình delimiter theo cú pháp database và cách viết script. Không nên sửa separator toàn cục nếu chỉ một script có yêu cầu đặc biệt; đặt config cục bộ cho script đó.

Thuộc tính `errorMode` quyết định cách xử lý lỗi khi thực thi script. Mặc định lỗi SQL làm test thất bại, đây thường là hành vi mong muốn vì schema hoặc fixture không được chuẩn bị đúng. Chỉ bỏ qua lỗi có chủ đích trong trường hợp script được thiết kế cho nhiều trạng thái database và đã có cách xác nhận kết quả.

## Công cụ hỗ trợ: ResourceDatabasePopulator và JdbcTestUtils

Ngoài `@Sql`, Spring JDBC cung cấp công cụ để thực thi script theo cách lập trình.

`ResourceDatabasePopulator` nhận một hoặc nhiều SQL resource, cấu hình encoding/separator và thực thi chúng trên database. Nó hữu ích khi cần khởi tạo database từ cấu hình Java hoặc khi fixture cần được điều khiển bằng code.

~~~java
ResourceDatabasePopulator populator =
    new ResourceDatabasePopulator(
        new ClassPathResource("sql/customer-schema.sql"),
        new ClassPathResource("sql/reference-data.sql")
    );

DatabasePopulatorUtils.execute(populator, dataSource);
~~~

Cách này phù hợp cho initializer hoặc test infrastructure cần khởi tạo schema trước khi context được sử dụng. Với kịch bản gắn trực tiếp vào lifecycle test method, `@Sql` thường diễn đạt ý định rõ hơn.

`JdbcTestUtils` cung cấp các helper hữu ích khi thao tác database trong test, chẳng hạn đếm số hàng hoặc xóa dữ liệu từ bảng:

~~~java
int count = JdbcTestUtils.countRowsInTable(jdbcTemplate, "customer");
int deleted = JdbcTestUtils.deleteFromTables(
    jdbcTemplate,
    "customer_order",
    "customer"
);
~~~

Các helper không thay thế việc thiết kế cleanup an toàn. Khi dùng `deleteFromTables`, cần biết dữ liệu nào thuộc test và thứ tự bảng có tôn trọng foreign key hay không. Không gọi helper xóa toàn bảng trên database được chia sẻ với test khác.

## Chạy test song song và chia sẻ database

Nếu test chạy song song trên cùng database, dữ liệu fixture cần được cô lập theo test method hoặc worker. Hai test dùng cùng email, cùng ID và cùng bảng có thể đụng unique constraint, xóa dữ liệu của nhau hoặc đọc kết quả không ổn định.

Một số cách cô lập:

- Database riêng cho từng test suite hoặc worker.
- Schema riêng cho mỗi test class hoặc test run.
- Namespace/tenant riêng cho dữ liệu.
- UUID hoặc business key duy nhất cho fixture.
- Transaction riêng khi các thao tác thực sự tham gia transaction.
- Khóa đồng bộ khi tài nguyên không thể được chia sẻ an toàn.

Transaction rollback không giải quyết mọi xung đột. Hai transaction đồng thời vẫn có thể tranh chấp unique key hoặc lock. Một cleanup script cũng có thể xóa dữ liệu của test khác nếu điều kiện xóa quá rộng.

Nếu test cần kiểm tra isolation, locking hoặc concurrent update, hãy thiết kế kịch bản nhiều transaction rõ ràng và dùng database engine thực tế. Một test đơn giản có thể chạy tuần tự; một test concurrency cần quản lý thread, transaction và thời gian chờ có chủ đích.

## Kiểm tra migration và tương thích schema

Nếu schema production được quản lý bằng migration, test migration nên bắt đầu từ database sạch và chạy toàn bộ chuỗi migration theo đúng thứ tự. Sau đó, kiểm tra schema và hành vi cần thiết.

Ví dụ các điều cần xác nhận:

- Migration tạo đủ bảng và cột mà repository sử dụng.
- Constraint và index được tạo đúng.
- Dữ liệu tham chiếu được thêm hoặc chuyển đổi đúng.
- Migration tiếp theo có thể chạy trên trạng thái do migration trước tạo ra.
- Nâng cấp từ phiên bản schema cũ không làm mất dữ liệu cần giữ.
- Ứng dụng có thể đọc/ghi trên schema sau migration.

Không nên chỉ chạy một file schema giản lược trong test rồi coi đó là bằng chứng migration production đúng. Schema giản lược vẫn có ích cho unit/integration test nhanh, nhưng test migration cần chạy migration thực tế.

## Ví dụ tổng hợp với @Sql và transaction rollback

Ví dụ sau minh họa một test repository dùng Spring context, fixture SQL theo từng method và test-managed transaction:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    @Sql(
        scripts = "/sql/fixtures/customer-active.sql",
        config = @SqlConfig(
            encoding = "UTF-8",
            transactionMode = SqlConfig.TransactionMode.INFERRED
        )
    )
    void findsActiveCustomerByEmail() {
        var customer = repository.findByEmail("lan@example.test");

        assertThat(customer).isPresent();
        assertThat(customer.orElseThrow().isActive()).isTrue();
    }

    @Test
    @Sql("/sql/fixtures/customer-inactive.sql")
    void excludesInactiveCustomerFromActiveSearch() {
        var result = repository.findActiveByEmail("mai@example.test");

        assertThat(result).isEmpty();
    }
}
~~~

Script fixture thứ nhất có thể chứa:

~~~sql
insert into customer(id, email, name, active)
values (9101, 'lan@example.test', 'Lan', true);
~~~

Script thứ hai có thể chứa:

~~~sql
insert into customer(id, email, name, active)
values (9102, 'mai@example.test', 'Mai', false);
~~~

Vì test class dùng `@Transactional` và script dùng transaction mode inferred, dữ liệu fixture thường tham gia test-managed transaction. Khi từng test kết thúc và transaction rollback, bản ghi được tạo cho test đó được hoàn tác. Hai method không dựa vào dữ liệu do method kia tạo.

Ví dụ giả định repository và schema được cấu hình sẵn trong `PersistenceTestConfig`. Trong dự án thực tế, cần chọn ID, unique key và transaction manager phù hợp với database test đang sử dụng.

## Những nhầm lẫn thường gặp

**Đặt dữ liệu nghiệp vụ vào schema script.** Schema và fixture có vòng đời khác nhau. Giữ cấu trúc trong schema/migration và dữ liệu kịch bản trong fixture riêng.

**Nghĩ rằng @Sql luôn chạy trong transaction của test.** Điều đó phụ thuộc transaction manager, transaction hiện có và `transactionMode`. Kiểm tra `INFERRED` hay `ISOLATED` trước khi dựa vào rollback.

**Dùng ISOLATED rồi mong rollback của test xóa fixture.** Transaction độc lập có thể commit riêng. Cần cleanup hoặc database/schema riêng.

**Dùng cleanup xóa cả bảng.** Trên database dùng chung, thao tác đó có thể xóa dữ liệu test khác. Hãy dùng business key hoặc namespace riêng.

**Giả định H2 tương đương database production.** SQL dialect, DDL, locking, type và constraint có thể khác. Test những hành vi phụ thuộc engine trên đúng engine.

**Dựa vào ID tự tăng bắt đầu từ một giá trị cố định.** Sequence có thể không rollback/reset như mong đợi. Truy vấn bằng business key hoặc chỉ định ID có chủ đích.

**Cho rằng @Sql ở method luôn cộng với @Sql ở class.** Mặc định method-level script có thể override class-level script. Dùng `@SqlMergeMode(MERGE)` khi cần hợp nhất.

**Đặt script quá lớn cho mọi test.** Script nền nên chứa dữ liệu tham chiếu thật sự dùng chung; mỗi method chỉ nạp fixture cần cho kịch bản của nó.

**Dùng migration production như một fixture nhỏ cho mọi test.** Migration nên kiểm tra schema; fixture test nên tập trung vào dữ liệu. Có thể dùng cả hai nhưng cần xác định rõ trách nhiệm.

## Quy trình chuẩn bị schema và dữ liệu cho một test

Khi viết test cần database, hãy xác định lần lượt:

1. Test cần kiểm tra schema, truy vấn, constraint hay logic nghiệp vụ sử dụng dữ liệu?
2. Schema cần giống database production tới mức nào? Có cần chạy migration thật hoặc dùng đúng database engine không?
3. Dữ liệu nào là tham chiếu chung, dữ liệu nào chỉ thuộc test method?
4. Chuẩn bị schema ở cấp database/suite/class hay method?
5. Dùng `@Sql`, builder, repository hay `ResourceDatabasePopulator` để tạo fixture?
6. Script chạy ở phase nào và dùng transaction mode nào?
7. Dữ liệu có được rollback không? Nếu commit, cleanup xóa chính xác phạm vi nào?
8. Test có thể chạy độc lập và song song mà không va chạm key hoặc resource không?

Schema ổn định tạo nền tảng cho các test. Fixture dữ liệu tối thiểu và có định danh rõ ràng tạo điều kiện để từng test kiểm tra một hành vi cụ thể. Khi lựa chọn đúng phase, transaction mode và phạm vi cleanup, Spring Test giúp việc chuẩn bị database trở nên có thể lặp lại, dễ đọc và ít phụ thuộc vào trạng thái còn sót từ lần chạy trước.

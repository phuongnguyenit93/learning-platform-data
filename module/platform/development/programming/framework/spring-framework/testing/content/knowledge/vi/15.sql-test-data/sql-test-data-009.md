# @SqlGroup và nhiều bộ script

Spring Framework Testing cho phép nạp dữ liệu SQL trước hoặc sau khi test chạy bằng annotation `@Sql`. Khi một tình huống cần nhiều script, hoặc một test class cần nhiều bộ dữ liệu cho các mục đích khác nhau, có thể khai báo nhiều `@Sql` và gom chúng bằng `@SqlGroup`.

`@SqlGroup` là annotation chứa một tập các khai báo `@Sql`. Nó giúp tổ chức các script theo từng giai đoạn của test, chẳng hạn chuẩn bị schema, nạp dữ liệu nền, tạo dữ liệu riêng cho một test method và dọn dữ liệu sau khi kiểm tra. Điều quan trọng là phân biệt việc nhóm annotation với việc nhóm transaction: `@SqlGroup` tổ chức các khai báo script, còn transaction của từng khai báo được quyết định bởi cấu hình Spring Test.

## 1. @Sql dùng để làm gì?

`@Sql` yêu cầu Spring chạy một hoặc nhiều SQL script tại một thời điểm trong vòng đời kiểm thử. Annotation có thể đặt trên test class hoặc test method.

Ví dụ nạp dữ liệu trước một test method:

```java
@SpringBootTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    @Sql("/sql/customer/insert-customer.sql")
    void findsCustomerByEmail() {
        assertTrue(
                customerRepository.findByEmail("lan@example.test").isPresent()
        );
    }
}
```

Spring chạy script trước khi test method thực thi. Script có thể tạo bản ghi mà repository cần để thực hiện truy vấn.

Có thể khai báo script rõ ràng bằng thuộc tính `scripts`:

```java
@Sql(scripts = "classpath:/sql/customer/insert-customer.sql")
```

Thuộc tính `value` là alias của `scripts`, vì vậy hai cách sau có cùng ý nghĩa:

```java
@Sql("/sql/customer/insert-customer.sql")
@Sql(scripts = "/sql/customer/insert-customer.sql")
```

Một `@Sql` có thể nhận nhiều đường dẫn script:

```java
@Sql(scripts = {
        "classpath:/sql/common/insert-country.sql",
        "classpath:/sql/customer/insert-customer.sql",
        "classpath:/sql/customer/insert-address.sql"
})
```

Các script trong danh sách được thực thi theo thứ tự khai báo. Điều này hữu ích khi script sau phụ thuộc vào dữ liệu hoặc bảng được tạo bởi script trước.

## 2. @SqlGroup là gì?

`@SqlGroup` là annotation container dùng để nhóm nhiều khai báo `@Sql` trên cùng một class hoặc method.

Ví dụ:

```java
@SpringBootTest
class OrderRepositoryTest {

    @Test
    @SqlGroup({
            @Sql(scripts = "classpath:/sql/order/insert-customer.sql"),
            @Sql(scripts = "classpath:/sql/order/insert-order.sql"),
            @Sql(scripts = "classpath:/sql/order/insert-order-line.sql")
    })
    void findsOrderWithLines() {
        // Kiểm tra repository
    }
}
```

Ba khai báo `@Sql` tạo thành một nhóm script chuẩn bị dữ liệu. Spring xử lý từng khai báo theo thứ tự và mỗi khai báo có thể có cấu hình riêng.

Trong Java hiện đại, `@Sql` là repeatable annotation nên có thể khai báo nhiều `@Sql` trực tiếp trên cùng phần tử. `@SqlGroup` cung cấp cách viết tường minh thông qua annotation container, hữu ích khi muốn thể hiện rõ một nhóm script hoặc khi cần tương thích với cách xử lý annotation dựa trên container.

Hai cách viết:

```java
@Sql(scripts = "classpath:/sql/common/insert-customer.sql")
@Sql(scripts = "classpath:/sql/common/insert-address.sql")
class CustomerRepositoryTest {
}
```

Và:

```java
@SqlGroup({
        @Sql(scripts = "classpath:/sql/common/insert-customer.sql"),
        @Sql(scripts = "classpath:/sql/common/insert-address.sql")
})
class CustomerRepositoryTest {
}
```

đều thể hiện nhiều khai báo `@Sql`. Chọn một phong cách nhất quán trong dự án để người đọc dễ nhận ra cách tổ chức script.

## 3. Nhóm nhiều script theo mục đích

Một nhóm script thường dễ hiểu hơn khi mỗi file đảm nhiệm một phần dữ liệu cụ thể. Ví dụ, một bài kiểm thử đơn hàng có thể cần:

| Script | Vai trò |
|---|---|
| `schema.sql` | Tạo cấu trúc bảng nếu test tự quản lý schema |
| `reference-data.sql` | Nạp dữ liệu danh mục dùng chung |
| `insert-customer.sql` | Tạo khách hàng cho tình huống |
| `insert-order.sql` | Tạo đơn hàng |
| `insert-order-lines.sql` | Tạo các dòng hàng |
| `cleanup-order.sql` | Xóa dữ liệu của tình huống |

Có thể gom các script chuẩn bị dữ liệu trong một `@SqlGroup`:

```java
@Test
@SqlGroup({
        @Sql(scripts = "classpath:/sql/order/insert-customer.sql"),
        @Sql(scripts = "classpath:/sql/order/insert-order.sql"),
        @Sql(scripts = "classpath:/sql/order/insert-order-lines.sql")
})
void loadsOrderDetails() {
    // ...
}
```

Cách chia file nên phản ánh quan hệ dữ liệu. Nếu `insert-order.sql` tham chiếu customer, script tạo customer phải chạy trước. Nếu order line có khóa ngoại tới order, script tạo order phải chạy trước script tạo line.

Không nên chia thành quá nhiều file nhỏ nếu điều đó khiến người đọc phải lần qua một chuỗi dài mới hiểu fixture. Có thể gộp những lệnh luôn đi cùng nhau và chỉ tách khi chúng có thể tái sử dụng hoặc có vòng đời riêng.

## 4. Đặt script ở vị trí dễ tìm

Các script SQL kiểm thử thường được lưu trong test resources:

```text
src/test/resources/
└── sql/
    ├── common/
    │   ├── schema.sql
    │   └── reference-data.sql
    ├── customer/
    │   ├── insert-customer.sql
    │   └── insert-address.sql
    └── order/
        ├── insert-order.sql
        ├── insert-order-lines.sql
        └── cleanup-order.sql
```

Có thể dùng đường dẫn classpath rõ ràng:

```java
@Sql(scripts = "classpath:/sql/order/insert-order.sql")
```

Các cách định vị tài nguyên thường gặp:

- `classpath:/sql/order/insert-order.sql`: đường dẫn tuyệt đối trong classpath.
- `/sql/order/insert-order.sql`: đường dẫn classpath tuyệt đối.
- `insert-order.sql`: đường dẫn tương đối theo package của test class.
- `file:/path/to/script.sql`: file bên ngoài filesystem, khi môi trường kiểm thử cho phép.

Đường dẫn classpath thường phù hợp với test vì script được đóng gói cùng test resources và có thể chạy nhất quán trong IDE lẫn build tool. Tránh phụ thuộc vào đường dẫn tuyệt đối trên máy lập trình viên.

Tên file nên cho biết hành động hoặc dữ liệu mà nó tạo ra. Các tên như `data1.sql`, `setup.sql` hoặc `script-final.sql` khó truy tìm hơn những tên như `insert-active-customer.sql`, `insert-pending-order.sql` và `delete-order-fixture.sql`.

## 5. Chọn thời điểm chạy bằng executionPhase

Mặc định, `@Sql` chạy script trước mỗi test method. Thuộc tính `executionPhase` cho phép chọn thời điểm chạy.

Các phase chính:

| Phase | Thời điểm |
|---|---|
| `BEFORE_TEST_METHOD` | Trước test method; đây là mặc định |
| `AFTER_TEST_METHOD` | Sau test method |
| `BEFORE_TEST_CLASS` | Trước các test method trong class |
| `AFTER_TEST_CLASS` | Sau khi các test method trong class hoàn tất |

Hai phase cấp class `BEFORE_TEST_CLASS` và `AFTER_TEST_CLASS` được hỗ trợ từ Spring Framework 6.1. Với phiên bản cũ hơn, cần dùng các phase method và cách chuẩn bị/dọn dẹp phù hợp.

Ví dụ, một test class có thể nạp dữ liệu nền một lần trước class, nạp fixture riêng trước từng method và dọn dữ liệu nền sau class:

```java
@SpringBootTest
@SqlGroup({
        @Sql(
                scripts = "classpath:/sql/common/reference-data.sql",
                executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS
        ),
        @Sql(
                scripts = "classpath:/sql/common/cleanup-reference-data.sql",
                executionPhase = Sql.ExecutionPhase.AFTER_TEST_CLASS
        )
})
class ProductRepositoryTest {

    @Test
    @Sql(scripts = "classpath:/sql/product/insert-product.sql")
    void findsProduct() {
        // ...
    }
}
```

Script cấp class chỉ phù hợp khi dữ liệu được tạo một lần có thể dùng chung cho các method trong class. Nếu test method sửa hoặc xóa dữ liệu nền, cần có cách khôi phục trạng thái trước method tiếp theo.

Nếu một script cần chạy trước và script khác chạy sau từng method, có thể gom cả hai:

```java
@Test
@SqlGroup({
        @Sql(
                scripts = "classpath:/sql/order/insert-order.sql",
                executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
        ),
        @Sql(
                scripts = "classpath:/sql/order/delete-order.sql",
                executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
        )
})
void readsOrder() {
    // ...
}
```

Nhóm này tổ chức hai khai báo có phase khác nhau. Script chuẩn bị chạy trước method, còn script cleanup được lên lịch sau method.

## 6. Class-level @Sql và method-level @Sql

Có thể khai báo SQL script trên class để áp dụng cho các test method, và khai báo thêm script riêng trên method.

Ví dụ:

```java
@SpringBootTest
@Sql(scripts = "classpath:/sql/common/insert-default-customer.sql")
class OrderRepositoryTest {

    @Test
    void findsDefaultCustomer() {
        // ...
    }

    @Test
    @Sql(scripts = "classpath:/sql/order/insert-order.sql")
    void findsOrder() {
        // ...
    }
}
```

Theo mặc định, khi method có khai báo `@Sql`, các khai báo SQL ở cấp method sẽ override khai báo cấp class cho method đó. Vì vậy, test method thứ hai có thể chỉ chạy script của nó thay vì chạy cả script customer ở cấp class.

Đây là điểm dễ gây nhầm lẫn: việc đặt `@Sql` trên class không luôn có nghĩa mọi script cấp class và method đều tự động cộng lại.

## 7. Dùng @SqlMergeMode khi cần kết hợp script cấp class và method

`@SqlMergeMode` điều khiển cách Spring kết hợp khai báo `@Sql` ở cấp class với khai báo ở cấp method.

Có hai chế độ:

| Chế độ | Hành vi |
|---|---|
| `OVERRIDE` | Mặc định; khai báo method-level thay thế khai báo class-level cho method đó |
| `MERGE` | Kết hợp khai báo class-level và method-level |

Ví dụ dùng `MERGE`:

```java
@SpringBootTest
@Sql(scripts = "classpath:/sql/common/insert-default-customer.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class OrderRepositoryTest {

    @Test
    void findsDefaultCustomer() {
        // Nhận script cấp class
    }

    @Test
    @SqlGroup({
            @Sql(scripts = "classpath:/sql/order/insert-order.sql"),
            @Sql(scripts = "classpath:/sql/order/insert-order-lines.sql")
    })
    void findsOrderWithLines() {
        // Script cấp class và nhóm script cấp method cùng được áp dụng
    }
}
```

Với `MERGE`, script cấp class được kết hợp với script cấp method. Các script cấp class được thực hiện trước script cấp method. Điều này phù hợp khi mọi test đều cần dữ liệu nền, còn từng method bổ sung fixture riêng.

Nếu chỉ một số method cần dữ liệu nền, có thể giữ mặc định `OVERRIDE` và khai báo đầy đủ nhóm script ở method tương ứng. Cách chọn phụ thuộc vào ý nghĩa của dữ liệu chung và mức độ rõ ràng mong muốn.

Có thể đặt `@SqlMergeMode` ở class để áp dụng cho các method trong class, hoặc đặt trên method để thay đổi cách merge cho một tình huống cụ thể.

## 8. Nhiều bộ script cho nhiều tình huống

Một test class có thể kiểm tra nhiều tình huống với các bộ dữ liệu khác nhau. Hãy chia fixture theo hành vi để mỗi method chỉ nạp dữ liệu cần thiết.

Ví dụ:

```java
@SpringBootTest
class OrderQueryTest {

    @Test
    @SqlGroup({
            @Sql(scripts = "classpath:/sql/order/insert-pending-order.sql"),
            @Sql(scripts = "classpath:/sql/order/insert-pending-order-lines.sql")
    })
    void findsPendingOrder() {
        // Kiểm tra đơn hàng PENDING
    }

    @Test
    @SqlGroup({
            @Sql(scripts = "classpath:/sql/order/insert-cancelled-order.sql"),
            @Sql(scripts = "classpath:/sql/order/insert-cancelled-order-lines.sql")
    })
    void findsCancelledOrder() {
        // Kiểm tra đơn hàng CANCELLED
    }
}
```

Hai test có fixture riêng, tên file phản ánh trạng thái nghiệp vụ. Người đọc có thể lần từ test method đến bộ script tương ứng mà không phải đọc một file dữ liệu lớn chứa nhiều tình huống không liên quan.

Nếu các test cùng cần dữ liệu customer hoặc danh mục dùng chung, có thể đặt bộ script đó ở class-level và dùng `@SqlMergeMode(MERGE)`. Nếu dữ liệu khác nhau hoàn toàn, method-level `@SqlGroup` với mặc định `OVERRIDE` thường dễ hiểu hơn.

## 9. Dùng @SqlConfig để cấu hình cách chạy script

`@SqlConfig` cho phép điều chỉnh cách Spring phân tích và thực thi SQL script. Có thể khai báo cấu hình chung trên test class hoặc cấu hình riêng cho một `@Sql`.

Một số thuộc tính thường gặp:

| Thuộc tính | Mục đích |
|---|---|
| `dataSource` | Tên bean DataSource được dùng |
| `transactionManager` | Tên bean PlatformTransactionManager |
| `transactionMode` | Cách script tham gia hoặc tạo transaction |
| `encoding` | Charset dùng để đọc file script |
| `separator` | Ký tự phân tách câu lệnh SQL |
| `commentPrefix` | Tiền tố comment một dòng |
| `blockCommentStartDelimiter` | Dấu bắt đầu block comment |
| `blockCommentEndDelimiter` | Dấu kết thúc block comment |
| `errorMode` | Cách xử lý lỗi khi thực thi script |

Ví dụ cấu hình chung:

```java
@SpringBootTest
@SqlConfig(
        dataSource = "dataSource",
        transactionManager = "transactionManager",
        encoding = "UTF-8",
        separator = ";"
)
class CustomerSqlTest {
    // Các @Sql trong class sử dụng cấu hình chung
}
```

Cũng có thể đặt cấu hình riêng trên một khai báo:

```java
@Sql(
        scripts = "classpath:/sql/customer/insert-customer.sql",
        config = @SqlConfig(
                encoding = "UTF-8",
                separator = ";"
        )
)
```

Cấu hình cục bộ hữu ích khi một script có quy tắc phân tách hoặc encoding khác. Nếu tất cả script trong class dùng cùng quy ước, cấu hình cấp class giảm lặp lại.

Khi dùng `@SqlConfig` cấp class làm cấu hình toàn cục cho các khai báo `@Sql`, cần lưu ý các giá trị mặc định và cách Spring hợp nhất cấu hình cục bộ với cấu hình toàn cục. Chỉ override những thuộc tính thực sự cần thay đổi để tránh tạo cấu hình khó truy tìm.

## 10. Transaction mode của SQL script

SQL script có thể chạy trong transaction test hiện tại, trong transaction riêng hoặc không có transaction Spring tùy cấu hình và môi trường.

Thuộc tính `transactionMode` của `@SqlConfig` có các lựa chọn:

- `DEFAULT`: sử dụng chính sách mặc định của Spring để suy luận cách chạy script.
- `INFERRED`: suy luận dựa trên transaction hiện có và các thành phần transaction được cấu hình.
- `ISOLATED`: chạy script trong một transaction độc lập và commit transaction đó.

Trong chế độ suy luận thông thường, nếu test-managed transaction đang hoạt động và script dùng cùng transaction manager/tài nguyên, script có thể chạy trong transaction của test. Khi test kết thúc và rollback, dữ liệu do script chuẩn bị cũng được rollback.

Nếu không có transaction hiện tại nhưng có transaction manager phù hợp, Spring có thể tạo transaction cho script và commit sau khi script chạy thành công. Nếu không có transaction manager, script có thể được thực thi không có transaction Spring.

Ví dụ yêu cầu script chạy trong transaction độc lập:

```java
@Sql(
        scripts = "classpath:/sql/audit/insert-audit-fixture.sql",
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
```

`ISOLATED` hữu ích khi dữ liệu script phải được commit độc lập với test-managed transaction. Nó cũng có nghĩa rollback mặc định của test không thể tự hoàn tác dữ liệu đã commit bởi script này.

Cần thận trọng khi chọn `ISOLATED`: dữ liệu có thể tồn tại sau test và cần cleanup rõ ràng. Với fixture thông thường của test có `@Transactional`, để script tham gia transaction test thường giúp dữ liệu được rollback cùng test.

## 11. Cleanup bằng script sau test

Có thể dùng `executionPhase = AFTER_TEST_METHOD` để chạy script sau test method:

```java
@Test
@SqlGroup({
        @Sql(
                scripts = "classpath:/sql/customer/insert-customer.sql",
                executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
        ),
        @Sql(
                scripts = "classpath:/sql/customer/delete-customer.sql",
                executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
        )
})
void readsCustomer() {
    // ...
}
```

Cần hiểu transaction của script cleanup. Nếu script chạy trong test-managed transaction rồi test transaction rollback, thao tác cleanup cũng có thể bị rollback. Điều này không nhất thiết gây vấn đề nếu toàn bộ dữ liệu fixture ban đầu cũng nằm trong cùng transaction và rollback sẽ xóa cả fixture.

Nhưng nếu dữ liệu đã được commit độc lập, ví dụ được tạo bởi `REQUIRES_NEW` hoặc script dùng `ISOLATED`, cleanup cần chạy trong transaction độc lập và commit để xóa dữ liệu đó:

```java
@Sql(
        scripts = "classpath:/sql/audit/delete-audit-fixture.sql",
        executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD,
        config = @SqlConfig(
                transactionMode = SqlConfig.TransactionMode.ISOLATED
        )
)
```

Không nên mặc định mọi script `AFTER_TEST_METHOD` đều dọn dữ liệu vĩnh viễn. Hãy xem script chạy trong transaction nào và transaction đó kết thúc bằng commit hay rollback.

## 12. Phân biệt @SqlGroup với @SqlMergeMode

Hai annotation giải quyết hai vấn đề khác nhau:

| Annotation | Câu hỏi được giải quyết |
|---|---|
| `@SqlGroup` | Có nhiều khai báo `@Sql` tại cùng một class hoặc method thì tổ chức chúng ra sao? |
| `@SqlMergeMode` | Khai báo SQL ở class và method có được kết hợp hay method thay thế class? |

Ví dụ:

```java
@SpringBootTest
@Sql(scripts = "classpath:/sql/common/insert-tenant.sql")
@SqlMergeMode(SqlMergeMode.MergeMode.MERGE)
class TenantOrderTest {

    @Test
    @SqlGroup({
            @Sql(scripts = "classpath:/sql/order/insert-order.sql"),
            @Sql(scripts = "classpath:/sql/order/insert-order-lines.sql")
    })
    void loadsTenantOrder() {
        // ...
    }
}
```

`@SqlGroup` gom hai script của test method. `@SqlMergeMode(MERGE)` quyết định nhóm script đó được kết hợp với script tenant ở class-level. Một annotation không thay thế chức năng của annotation kia.

## 13. Tổ chức nhiều bộ script theo vòng đời

Với một test class có nhiều tình huống, có thể phân chia script theo ba lớp:

```text
SQL fixture của test class
    |
    +--> BEFORE_TEST_CLASS
    |       schema hoặc dữ liệu nền dùng chung
    |
    +--> BEFORE_TEST_METHOD
    |       fixture riêng cho từng test
    |
    +--> AFTER_TEST_METHOD
    |       cleanup dữ liệu riêng của test
    |
    +--> AFTER_TEST_CLASS
            cleanup dữ liệu nền hoặc tài nguyên của class
```

Ví dụ cấu trúc thư mục:

```text
src/test/resources/sql/
├── shared/
│   ├── schema.sql
│   ├── reference-data.sql
│   └── cleanup-reference-data.sql
├── customer/
│   ├── insert-customer.sql
│   └── delete-customer.sql
└── order/
    ├── insert-pending-order.sql
    ├── insert-cancelled-order.sql
    ├── insert-order-lines.sql
    └── delete-order-fixture.sql
```

Không phải test class nào cũng cần đủ bốn phase. Chỉ sử dụng những phase phù hợp với vòng đời dữ liệu. Với database được tạo mới cho mỗi test run, việc tạo schema có thể do migration hoặc container setup đảm nhiệm; không cần lặp lại schema script ở từng class.

## 14. Những lưu ý về thứ tự và phụ thuộc dữ liệu

Khi có nhiều script, thứ tự thực thi là một phần của fixture. Hãy xác định rõ quan hệ phụ thuộc:

- Tạo bảng trước khi insert dữ liệu.
- Tạo bản ghi cha trước bản ghi con có foreign key.
- Tạo danh mục trước bản ghi nghiệp vụ tham chiếu danh mục.
- Xóa bản ghi con trước bản ghi cha nếu database áp dụng ràng buộc khóa ngoại.
- Dùng mã định danh cố định hoặc duy nhất để tránh trùng dữ liệu giữa các test.

Ví dụ, nếu `order_line.order_id` tham chiếu `orders.id`, thứ tự chuẩn bị phải là:

```text
insert-customer.sql
        |
        v
insert-order.sql
        |
        v
insert-order-lines.sql
```

Khi cleanup:

```text
delete-order-lines.sql
        |
        v
delete-order.sql
        |
        v
delete-customer.sql
```

Nếu script phụ thuộc trạng thái được tạo bởi một script khác, hãy giữ chúng trong cùng một nhóm hoặc đặt tên và tài liệu rõ ràng để người dùng không vô tình tách chúng ra.

## 15. Lỗi thường gặp khi dùng @SqlGroup

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Script class-level không chạy ở method có @Sql riêng | Mặc định method-level override class-level | Dùng `@SqlMergeMode(MERGE)` nếu cần kết hợp |
| Script chạy sai thứ tự | Danh sách script hoặc quan hệ phụ thuộc chưa rõ | Sắp xếp script theo quan hệ khóa ngoại |
| Bản ghi còn sau khi test kết thúc | Script hoặc mã ứng dụng đã commit transaction độc lập | Kiểm tra transactionMode và propagation; thêm cleanup độc lập |
| Script cleanup chạy nhưng dữ liệu vẫn còn | Cleanup tham gia transaction test rồi bị rollback | Dùng cleanup transaction độc lập khi cần commit |
| Không tìm thấy file SQL | Đường dẫn classpath tương đối hoặc sai | Dùng `classpath:/...` và kiểm tra test resources |
| Script có ký tự tiếng Việt lỗi | Encoding không phù hợp | Khai báo `@SqlConfig(encoding = "UTF-8")` |
| SQL bị tách câu lệnh sai | Separator hoặc comment delimiter không phù hợp | Cấu hình `@SqlConfig` theo dialect/script |
| Script tiếp tục sau lỗi ngoài dự kiến | Error mode không phù hợp | Chọn chính sách lỗi phù hợp, thường cần fail rõ ràng |
| Fixture của test này ảnh hưởng test khác | Dữ liệu được commit hoặc dùng chung | Dùng transaction rollback, ID riêng và cleanup |
| Dùng @SqlGroup nhưng mong tất cả script nằm trong một transaction | Nhầm grouping annotation với transaction boundary | Cấu hình transaction mode và hiểu transaction của từng khai báo |

Khi có lỗi, hãy xác định script nào đã chạy, phase nào đã kích hoạt, cấu hình merge class/method ra sao và transaction nào đang quản lý thao tác SQL. Chỉ nhìn thấy `@SqlGroup` trên test class chưa đủ để kết luận mọi script sẽ chạy cùng một lần hoặc cùng một transaction.

## 16. Cách chọn cách tổ chức phù hợp

| Nhu cầu | Cách dùng |
|---|---|
| Một script đơn giản cho một test | Một `@Sql` |
| Nhiều script cần chạy theo thứ tự | Một `@Sql(scripts = {...})` hoặc `@SqlGroup` |
| Mỗi script cần phase hoặc cấu hình riêng | `@SqlGroup` với nhiều `@Sql` |
| Nhiều test cùng dùng dữ liệu nền | Class-level `@Sql` |
| Mỗi test cần fixture riêng và thay thế dữ liệu nền | Method-level `@Sql` với mặc định override |
| Mỗi test cần bổ sung dữ liệu vào bộ chung | `@SqlMergeMode(MERGE)` |
| Script cần encoding/separator hoặc transaction riêng | `@SqlConfig` |
| Script phải commit độc lập với test transaction | `transactionMode = ISOLATED`, kèm cleanup |
| Cần nạp/dọn dữ liệu một lần cho cả class | Class-level phase nếu dùng Spring Framework 6.1 trở lên |

`@SqlGroup` giúp mô tả nhiều bộ script ngay tại nơi kiểm thử sử dụng chúng. Khi kết hợp đúng với phase, merge mode và transaction configuration, dữ liệu được chuẩn bị theo một trình tự có thể hiểu và lặp lại. Hãy đặt tên file theo mục đích, giữ thứ tự phụ thuộc rõ ràng và xác định nơi cleanup thực sự được commit để tránh dữ liệu còn sót sau test.


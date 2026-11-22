# Propagation của mã được gọi và nguy cơ tạo giao dịch độc lập

Spring TestContext Framework có thể mở một giao dịch do test quản lý cho mỗi test method được đánh dấu `@Transactional`. Theo mặc định, giao dịch này được rollback khi method kết thúc. Cơ chế đó rất hữu ích để cô lập dữ liệu kiểm thử: test có thể ghi dữ liệu, đọc lại và kiểm tra kết quả mà không để lại thay đổi trong database.

Tuy nhiên, rollback của test chỉ tác động đến giao dịch test đang quản lý. Mã ứng dụng được gọi bên trong test có thể khai báo propagation khác, tạm ngưng giao dịch hiện tại hoặc mở một giao dịch độc lập. Nếu giao dịch độc lập commit, rollback của test không thể hoàn tác thay đổi đã commit đó. Đây là nguyên nhân phổ biến khiến dữ liệu kiểm thử vẫn còn trong database sau khi test đã kết thúc.

## 1. Giao dịch do test quản lý là gì?

Khi Spring TestContext Framework phát hiện test class hoặc test method có `@Transactional`, `TransactionalTestExecutionListener` có thể bắt đầu một test-managed transaction trước khi test method chạy. Sau khi method kết thúc, Spring rollback giao dịch theo mặc định.

Ví dụ:

```java
@SpringBootTest
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void savesAccount() {
        accountRepository.save(new Account("ACC-01"));

        assertTrue(accountRepository.findById("ACC-01").isPresent());
    }
}
```

Trong lúc test chạy, thao tác lưu và truy vấn tham gia cùng giao dịch test nếu chúng dùng cùng transaction manager và cùng tài nguyên giao dịch. Assertion có thể đọc được bản ghi vừa lưu. Khi test method kết thúc, Spring rollback giao dịch, vì vậy bản ghi không được commit vào database.

Có thể hình dung:

```text
Spring TestContext
       |
       v
Bắt đầu test-managed transaction T0
       |
       v
Chạy test method
       |
       +--> accountRepository.save(...)
       |
       +--> accountRepository.findById(...)
       |
       v
Kết thúc test method
       |
       v
Rollback T0
       |
       v
Dữ liệu trong T0 không được commit
```

Giao dịch test được quản lý bởi Spring TestContext Framework. Nó khác với giao dịch do một service tự mở và tự commit. Việc test có `@Transactional` không có nghĩa mọi thao tác database trong toàn bộ hệ thống đều chắc chắn nằm trong T0.

## 2. Propagation quyết định mã được gọi tham gia giao dịch nào

Propagation là chính sách xác định cách một phương thức transactional tương tác với giao dịch đang tồn tại tại thời điểm nó được gọi. Spring khai báo các chính sách này qua `Propagation` trong `@Transactional`.

Ví dụ:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void updateAccount() {
    // ...
}
```

Khi phương thức này được gọi qua Spring transaction proxy, Spring kiểm tra có giao dịch phù hợp đang tồn tại hay không. Tùy propagation, phương thức sẽ tham gia giao dịch hiện tại, tạm ngưng nó hoặc tạo giao dịch mới.

Các propagation chính:

| Propagation | Khi đã có giao dịch | Khi chưa có giao dịch |
|---|---|---|
| `REQUIRED` | Tham gia giao dịch hiện tại | Tạo giao dịch mới |
| `REQUIRES_NEW` | Tạm ngưng giao dịch hiện tại và tạo giao dịch mới | Tạo giao dịch mới |
| `SUPPORTS` | Tham gia giao dịch hiện tại | Chạy không có giao dịch |
| `NOT_SUPPORTED` | Tạm ngưng giao dịch hiện tại và chạy không có giao dịch | Chạy không có giao dịch |
| `MANDATORY` | Tham gia giao dịch hiện tại | Ném lỗi vì không có giao dịch |
| `NEVER` | Ném lỗi vì đang có giao dịch | Chạy không có giao dịch |
| `NESTED` | Tham gia giao dịch hiện tại theo một điểm lưu (savepoint), nếu transaction manager hỗ trợ | Tạo giao dịch mới |

Bảng mô tả ý nghĩa chung. Hành vi thực tế còn phụ thuộc transaction manager, loại tài nguyên, cách gọi qua proxy và khả năng hỗ trợ của nền tảng giao dịch.

## 3. REQUIRED: mã được gọi tham gia giao dịch test

`REQUIRED` là propagation mặc định của `@Transactional`. Nếu đã có giao dịch, phương thức tham gia giao dịch đó. Nếu chưa có, Spring bắt đầu giao dịch mới.

Ví dụ:

```java
@Service
public class AccountService {

    private final AccountRepository accountRepository;

    public AccountService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void createAccount(String accountId) {
        accountRepository.save(new Account(accountId));
    }
}
```

Test:

```java
@SpringBootTest
@Transactional
class AccountServiceTest {

    @Autowired
    private AccountService accountService;

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void createsAccountInsideTestTransaction() {
        accountService.createAccount("ACC-02");

        assertTrue(accountRepository.findById("ACC-02").isPresent());
    }
}
```

Nếu `accountService` được gọi qua Spring proxy và dùng cùng transaction manager với test, phương thức `createAccount()` tham gia T0 do test mở. Repository cũng tham gia T0. Khi test kết thúc, rollback T0 sẽ hoàn tác thao tác lưu.

```text
Test-managed transaction T0
       |
       +--> AccountService.createAccount() [REQUIRED]
       |        |
       |        +--> AccountRepository.save() [REQUIRED]
       |
       v
Test kết thúc
       |
       v
Rollback T0
```

Đây là trường hợp mà test rollback hoạt động như nhiều người mong đợi: mã ứng dụng được gọi tham gia cùng giao dịch test, không tự commit một giao dịch độc lập.

## 4. REQUIRES_NEW: tạo giao dịch độc lập

`REQUIRES_NEW` luôn yêu cầu một giao dịch mới. Nếu đã có giao dịch, Spring tạm ngưng giao dịch hiện tại, tạo giao dịch mới cho phương thức được gọi, sau đó tiếp tục giao dịch cũ khi giao dịch mới kết thúc.

Ví dụ:

```java
@Service
public class AuditService {

    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String event) {
        auditRepository.save(new AuditRecord(event));
    }
}
```

Một service khác gọi audit service:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AuditService auditService;

    public OrderService(
            OrderRepository orderRepository,
            AuditService auditService
    ) {
        this.orderRepository = orderRepository;
        this.auditService = auditService;
    }

    @Transactional
    public void createOrder(String orderId) {
        orderRepository.save(new Order(orderId));
        auditService.record("Created order " + orderId);
    }
}
```

Giả sử test method có test-managed transaction T0 và gọi `orderService.createOrder()`:

1. `OrderService.createOrder()` dùng `REQUIRED`, nên tham gia T0.
2. `AuditService.record()` dùng `REQUIRES_NEW`, nên Spring tạm ngưng T0.
3. Spring bắt đầu giao dịch T1 cho `record()`.
4. `AuditRepository.save()` tham gia T1.
5. Khi `record()` hoàn tất bình thường, T1 commit.
6. Spring tiếp tục T0 và `createOrder()` kết thúc.
7. Sau test method, Spring rollback T0.

```text
Test-managed transaction T0
       |
       +--> OrderService.createOrder() [REQUIRED]
       |        |
       |        +--> lưu Order trong T0
       |        |
       |        +--> AuditService.record() [REQUIRES_NEW]
       |                   |
       |                   +--> Tạm ngưng T0
       |                   |
       |                   +--> Bắt đầu T1
       |                   |
       |                   +--> lưu AuditRecord trong T1
       |                   |
       |                   +--> Commit T1
       |                   |
       |                   +--> Tiếp tục T0
       |
       v
Test kết thúc
       |
       v
Rollback T0

Kết quả:
  Order       -> rollback
  AuditRecord -> đã commit, vẫn còn
```

Điểm cần nhớ: rollback T0 không thể hoàn tác T1 đã commit. Dữ liệu audit có thể vẫn tồn tại dù test method được đánh dấu rollback.

## 5. Ví dụ kiểm chứng nguy cơ dữ liệu còn lại

Giả sử ứng dụng có hai bảng `orders` và `audit_log`. Service tạo đơn hàng và ghi log audit trong một giao dịch độc lập:

```java
@Service
public class AuditService {

    private final JdbcTemplate jdbcTemplate;

    public AuditService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordOrderCreated(String orderId) {
        jdbcTemplate.update(
                "insert into audit_log(order_id, event) values (?, ?)",
                orderId,
                "ORDER_CREATED"
        );
    }
}
```

```java
@Service
public class OrderService {

    private final JdbcTemplate jdbcTemplate;
    private final AuditService auditService;

    public OrderService(
            JdbcTemplate jdbcTemplate,
            AuditService auditService
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.auditService = auditService;
    }

    @Transactional
    public void createOrder(String orderId) {
        jdbcTemplate.update(
                "insert into orders(id) values (?)",
                orderId
        );

        auditService.recordOrderCreated(orderId);
    }
}
```

Test:

```java
@SpringBootTest
@Transactional
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void createsOrderAndAuditRecord() {
        orderService.createOrder("ORDER-100");

        Integer orderCount = jdbcTemplate.queryForObject(
                "select count(*) from orders where id = ?",
                Integer.class,
                "ORDER-100"
        );

        Integer auditCount = jdbcTemplate.queryForObject(
                "select count(*) from audit_log where order_id = ?",
                Integer.class,
                "ORDER-100"
        );

        assertEquals(1, orderCount);
        assertEquals(1, auditCount);
    }
}
```

Trong lúc test chạy, cả hai truy vấn có thể nhìn thấy bản ghi của mình: đơn hàng nằm trong T0, audit record đã được commit trong T1. Khi test method kết thúc, Spring rollback T0. Bản ghi trong `orders` biến mất, còn audit record vẫn được lưu.

Nếu test này chạy nhiều lần với cùng mã `ORDER-100`, test sau có thể thất bại do dữ liệu audit từ lần trước còn tồn tại. Đây là lỗi cô lập dữ liệu thường gặp khi test chỉ dựa vào rollback của giao dịch ngoài cùng.

Ví dụ giả định các bảng đã được tạo và database hỗ trợ transaction phù hợp. Với JPA, JDBC hoặc transaction manager khác nhau, cách cấu hình repository và tài nguyên cần điều chỉnh theo ứng dụng.

## 6. NOT_SUPPORTED: mã được gọi chạy ngoài giao dịch hiện tại

`NOT_SUPPORTED` yêu cầu Spring tạm ngưng giao dịch đang tồn tại và thực thi phương thức không có giao dịch. Nếu phương thức ghi dữ liệu, việc ghi có thể được thực hiện qua cơ chế tự quản lý giao dịch của thành phần được gọi hoặc ở chế độ autocommit của tài nguyên.

Ví dụ:

```java
@Service
public class ExternalSyncService {

    private final JdbcTemplate jdbcTemplate;

    public ExternalSyncService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public void synchronize(String key) {
        jdbcTemplate.update(
                "insert into sync_log(sync_key) values (?)",
                key
        );
    }
}
```

Nếu test-managed transaction T0 đang tồn tại và gọi `synchronize()` qua proxy, T0 bị tạm ngưng trong lúc phương thức chạy. Thao tác ghi không tham gia T0, vì vậy rollback T0 không tự động hoàn tác thao tác đó.

Tuy nhiên, không nên kết luận rằng `NOT_SUPPORTED` luôn tự commit mọi lệnh SQL. Phương thức không có giao dịch Spring hiện tại; hành vi commit cụ thể phụ thuộc tài nguyên và các thành phần bên dưới. Ví dụ, một repository khác được gọi bên trong có thể tự mở giao dịch `REQUIRED` mới nếu không có giao dịch hiện hành. Với JDBC connection ở chế độ autocommit, mỗi câu lệnh có thể được commit ngay.

Do đó, khi dùng `NOT_SUPPORTED` trong đường đi của test, hãy kiểm tra cách các thao tác ghi được quản lý. Đừng trông chờ rollback của T0 dọn được thay đổi xảy ra khi T0 đã bị tạm ngưng.

## 7. NESTED: giao dịch lồng nhau và savepoint

`NESTED` yêu cầu một phạm vi giao dịch lồng bên trong giao dịch hiện tại. Với transaction manager và tài nguyên hỗ trợ savepoint, Spring có thể tạo một savepoint để rollback phần thao tác lồng mà vẫn giữ giao dịch ngoài tiếp tục.

Ví dụ khái niệm:

```text
Giao dịch ngoài T0
       |
       +--> Thao tác A
       |
       +--> Savepoint S1
       |       |
       |       +--> Phương thức NESTED
       |       |
       |       +--> Rollback về S1 nếu cần
       |
       +--> Thao tác B
       |
       v
Commit hoặc rollback T0
```

Nếu toàn bộ T0 là test-managed transaction và cuối test bị rollback, các thay đổi còn lại trong T0 cũng bị rollback. `NESTED` không tương đương `REQUIRES_NEW`: nested transaction dựa trên savepoint trong giao dịch ngoài, còn `REQUIRES_NEW` có một giao dịch độc lập với commit riêng.

Khả năng hỗ trợ `NESTED` phụ thuộc transaction manager. Một số transaction manager JDBC hỗ trợ savepoint; không nên mặc định mọi cấu hình JPA hoặc mọi nền tảng giao dịch đều hỗ trợ đầy đủ nested transaction. Hãy kiểm tra loại transaction manager và tài nguyên thực tế của ứng dụng.

## 8. SUPPORTS, MANDATORY và NEVER trong test

Ba propagation còn lại cũng có thể ảnh hưởng đến đường gọi từ test:

**SUPPORTS** tham gia giao dịch hiện tại nếu có. Nếu không có, phương thức chạy không có giao dịch. Khi test-managed transaction T0 tồn tại, phương thức thường tham gia T0 nếu cùng transaction manager.

**MANDATORY** yêu cầu phải có giao dịch hiện hành. Khi được gọi trong test có T0, nó có thể tham gia T0. Nếu test không mở giao dịch và không có giao dịch nào khác, Spring ném lỗi trạng thái giao dịch.

**NEVER** yêu cầu không có giao dịch hiện hành. Nếu test đang chạy trong T0, gọi một phương thức `NEVER` qua proxy sẽ dẫn đến lỗi vì giao dịch đang tồn tại. Nếu không có giao dịch, phương thức chạy không có giao dịch.

Bảng ví dụ:

| Test setup | Propagation của service | Kết quả mong đợi |
|---|---|---|
| Test có `@Transactional` | `SUPPORTS` | Tham gia T0 |
| Test không có transaction | `SUPPORTS` | Chạy không có transaction |
| Test có `@Transactional` | `MANDATORY` | Tham gia T0 |
| Test không có transaction | `MANDATORY` | Ném lỗi vì thiếu transaction |
| Test có `@Transactional` | `NEVER` | Ném lỗi vì đang có transaction |
| Test không có transaction | `NEVER` | Chạy không có transaction |

Các trường hợp trên giả định lời gọi được Spring transaction interceptor xử lý. Nếu lời gọi không đi qua proxy, annotation propagation trên phương thức có thể không được áp dụng.

## 9. Phân biệt propagation của test method và phương thức service

Không nên nhầm `@Transactional` trên test method với `@Transactional` trên mã ứng dụng.

Spring TestContext Framework có một số giới hạn riêng đối với propagation được khai báo trực tiếp trên test method hoặc test class. Trong test-managed transaction, các propagation được hỗ trợ cho annotation của test là `NOT_SUPPORTED` và `NEVER`; các giá trị khác không nên dùng để mô phỏng giao dịch của service.

Ví dụ, đây không phải cách phù hợp để yêu cầu test method tự tạo một giao dịch độc lập:

```java
@Test
@Transactional(propagation = Propagation.REQUIRES_NEW)
void testSomething() {
    // Không dùng propagation này để mô phỏng giao dịch độc lập của service
}
```

Để kiểm tra mã ứng dụng dùng `REQUIRES_NEW`, hãy để test-managed transaction tạo giao dịch ngoài và gọi một bean Spring có phương thức `@Transactional(propagation = REQUIRES_NEW)`. Chính phương thức ứng dụng được gọi sẽ yêu cầu giao dịch độc lập.

Cách phân tách trách nhiệm:

- Annotation trên test class/method xác định test-managed transaction và chính sách rollback/commit của test.
- Annotation trên service/repository xác định propagation của nghiệp vụ.
- Transaction manager điều phối các giao dịch thực tế.
- Database quyết định dữ liệu nào đã được commit và tồn tại sau khi test kết thúc.

## 10. Propagation chỉ có hiệu lực khi lời gọi đi qua Spring proxy

Trong chế độ proxy mặc định của Spring, transaction được áp dụng khi lời gọi đi qua proxy do Spring tạo. Một lời gọi nội bộ từ phương thức này sang phương thức khác trong cùng object (*self-invocation*) không đi qua proxy, nên annotation trên phương thức được gọi có thể không được áp dụng.

Ví dụ dễ gây hiểu nhầm:

```java
@Service
public class AuditService {

    public void recordFromOrder(String orderId) {
        record(orderId);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId) {
        // Ghi audit record
    }
}
```

Nếu `recordFromOrder()` được gọi qua proxy nhưng bên trong nó gọi trực tiếp `this.record()`, lời gọi `record()` là self-invocation. Transaction interceptor mặc định không chặn lời gọi nội bộ đó; vì vậy không thể dựa vào annotation `REQUIRES_NEW` để chắc chắn tạo T1.

Cách tổ chức rõ ràng hơn là đặt phương thức độc lập vào một bean khác:

```java
@Service
public class AuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId) {
        // Ghi audit record trong giao dịch riêng
    }
}
```

```java
@Service
public class OrderService {

    private final AuditWriter auditWriter;

    public OrderService(AuditWriter auditWriter) {
        this.auditWriter = auditWriter;
    }

    @Transactional
    public void createOrder(String orderId) {
        // Lưu đơn hàng trong giao dịch hiện tại
        auditWriter.record(orderId);
    }
}
```

`OrderService` gọi `AuditWriter` qua bean được inject, do đó lời gọi có thể đi qua transaction proxy và áp dụng `REQUIRES_NEW`.

Nếu propagation dường như không hoạt động, hãy kiểm tra không chỉ annotation mà cả đường đi của lời gọi, bean có được Spring quản lý hay không và phương thức có thực sự được gọi qua proxy không.

## 11. Giao dịch mới có thể tiêu thụ thêm kết nối database

Khi `REQUIRES_NEW` được gọi trong lúc T0 đang giữ kết nối, Spring thường phải giữ tài nguyên của T0 ở trạng thái tạm ngưng và lấy tài nguyên khác cho T1. Với JDBC, điều này có thể cần thêm một connection từ pool.

Nếu nhiều request hoặc test chạy đồng thời, mỗi luồng giữ một connection cho giao dịch ngoài rồi chờ thêm connection cho giao dịch `REQUIRES_NEW`, connection pool nhỏ có thể bị cạn. Đây là một trong những nguyên nhân gây treo hoặc timeout khi hệ thống dùng nhiều giao dịch độc lập lồng nhau.

Vì vậy:

- Dùng `REQUIRES_NEW` khi nghiệp vụ thực sự cần commit độc lập, ví dụ ghi audit phải tồn tại dù giao dịch nghiệp vụ ngoài rollback.
- Kiểm tra kích thước connection pool khi nhiều giao dịch ngoài có thể đồng thời mở giao dịch mới.
- Tránh lạm dụng `REQUIRES_NEW` cho mọi thao tác phụ.
- Trong test, quan sát cả dữ liệu còn lại và việc giải phóng tài nguyên sau khi test kết thúc.

Không phải mọi transaction manager đều quản lý connection theo cùng một cách, nhưng chi phí tài nguyên của giao dịch độc lập cần được tính đến.

## 12. Tác động của exception và rollback rule

Propagation xác định giao dịch nào được dùng; rollback rule xác định giao dịch đó kết thúc bằng commit hay rollback khi có lỗi.

Với `REQUIRES_NEW`, giao dịch T1 có kết quả độc lập với T0. Nếu phương thức trong T1 ném một runtime exception và lỗi được truyền ra khỏi ranh giới transactional, T1 thường rollback theo mặc định. Nếu T1 hoàn tất bình thường, nó có thể commit trước khi T0 tiếp tục.

Nếu lỗi từ phương thức `REQUIRES_NEW` truyền ra ngoài, phương thức gọi trong T0 cũng có thể thất bại. Khi đó T0 có thể rollback khi test kết thúc hoặc bị đánh dấu rollback-only tùy đường xử lý. Nhưng nếu exception bị bắt và xử lý, T0 có thể tiếp tục; điều đó không làm thay đổi kết quả T1 đã rollback hoặc commit.

Ví dụ:

```java
@Transactional
public void processOrder(String orderId) {
    orderRepository.save(new Order(orderId));

    try {
        auditWriter.record(orderId);
    } catch (AuditException ex) {
        // Quyết định nghiệp vụ: tiếp tục hay ném lỗi
    }
}
```

Nếu `auditWriter.record()` đã commit T1 rồi mới trả về bình thường, việc sau đó T0 rollback không thể undo audit record. Nếu T1 rollback do lỗi, T0 có thể tiếp tục nếu lỗi được xử lý và transaction ngoài chưa bị đánh dấu rollback-only.

Để kiểm thử hành vi này, cần xác định rõ kỳ vọng nghiệp vụ: audit phải tồn tại kể cả khi đơn hàng rollback, hay audit phải cùng thành công/thất bại với đơn hàng? Câu trả lời quyết định propagation nào phù hợp.

## 13. Vì sao test rollback vẫn để lại dữ liệu?

Có một số nguyên nhân phổ biến:

| Nguyên nhân | Vì sao rollback test không dọn được | Cách điều tra |
|---|---|---|
| Service dùng `REQUIRES_NEW` | Giao dịch mới đã commit độc lập | Tìm các phương thức transactional trên đường gọi |
| Service dùng `NOT_SUPPORTED` | T0 bị tạm ngưng; thao tác ghi có thể được quản lý ngoài T0 | Xác định transaction thực tế của lệnh ghi |
| Repository hoặc component tự mở transaction mới | Lệnh ghi có thể commit trước khi test rollback | Xem transaction manager và propagation ở bean được gọi |
| Code chạy trên thread khác | Thread mới không tự tham gia giao dịch test gắn với thread ban đầu | Kiểm tra `@Async`, executor, future hoặc callback |
| Dữ liệu đã được commit trước test | Rollback T0 không ảnh hưởng dữ liệu có sẵn | Kiểm tra fixture và trạng thái database ban đầu |
| Test dùng transaction manager khác | T0 không quản lý tài nguyên của transaction manager khác | Kiểm tra `transactionManager` và cấu hình datasource |
| Tự gọi phương thức trong cùng bean | Transaction annotation có thể không được proxy áp dụng | Kiểm tra self-invocation và bean boundary |

Giao dịch imperative của Spring thường gắn với thread hiện tại. Một task chạy qua executor hoặc `@Async` không tự động tham gia test-managed transaction của thread gọi. Nếu task đó mở và commit giao dịch riêng, rollback test không thể dọn thay đổi đã commit. Test cũng cần chờ tác vụ bất đồng bộ hoàn tất trước khi kiểm tra dữ liệu hoặc cleanup.

Với reactive transaction, context giao dịch được truyền qua Reactor Context thay vì dựa đơn thuần vào thread-local. Không nên áp dụng nguyên xi giả định về thread của giao dịch imperative cho luồng reactive.

## 14. Dọn dữ liệu được ghi bởi giao dịch độc lập

Nếu test cần kiểm tra `REQUIRES_NEW`, dữ liệu được commit độc lập cần được dọn bằng một chiến lược riêng. Rollback T0 không đủ.

Một cách là dùng `@AfterTransaction` để cleanup sau khi test-managed transaction đã kết thúc. Phương thức cleanup gọi một bean chuyên trách có giao dịch riêng:

```java
@Service
public class AuditCleanupService {

    private final JdbcTemplate jdbcTemplate;

    public AuditCleanupService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void deleteByOrderId(String orderId) {
        jdbcTemplate.update(
                "delete from audit_log where order_id = ?",
                orderId
        );
    }
}
```

```java
@SpringBootTest
@Transactional
class OrderServiceIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private AuditCleanupService auditCleanupService;

    private final String orderId = "ORDER-100";

    @Test
    void createsOrderAndAuditRecord() {
        orderService.createOrder(orderId);

        // Kiểm tra dữ liệu trong lúc test đang chạy
    }

    @AfterTransaction
    void cleanCommittedAuditRecord() {
        auditCleanupService.deleteByOrderId(orderId);
    }
}
```

`@AfterTransaction` được gọi sau khi test-managed transaction kết thúc. Vì vậy, thao tác xóa audit record không nằm trong T0 đã rollback. Cleanup service mở giao dịch riêng và commit thao tác xóa.

Trong dự án thực tế, mã định danh test nên duy nhất để cleanup không xóa dữ liệu của test khác. Nếu có thể, hãy dùng UUID hoặc khóa có namespace cho từng test run. Với test chạy song song, cleanup phải chỉ nhắm đến dữ liệu do chính test tạo ra.

Các lựa chọn khác gồm:

- Dùng script cleanup chạy ngoài test transaction.
- Reset database hoặc schema kiểm thử sau test suite.
- Dùng container database riêng cho test run và hủy container sau khi hoàn tất.
- Dùng fixture có mã định danh duy nhất và xóa bằng cleanup transaction độc lập.

Không nên dựa vào `@Sql` hoặc repository delete mà chưa xác định transaction của chính thao tác cleanup. Nếu cleanup vô tình tham gia T0, lệnh xóa cũng sẽ bị rollback và dữ liệu độc lập vẫn còn.

## 15. Kiểm tra hành vi propagation một cách có chủ đích

Khi viết test cho propagation, cần xác định giao dịch nào đang hoạt động tại từng bước và dữ liệu nào dự kiến tồn tại sau khi test kết thúc.

Một tình huống kiểm thử hữu ích có thể chia thành ba phần:

1. Gọi service trong test-managed transaction.
2. Xác nhận dữ liệu có thể đọc được trong lúc test đang chạy.
3. Sau khi transaction test kết thúc, kiểm tra trạng thái đã commit bằng một test hoặc truy vấn chạy ngoài transaction tương ứng.

Có thể dùng `TestTransaction` của Spring Test để điều khiển test-managed transaction trong test method. Ví dụ, `flagForCommit()` và `end()` cho phép đánh dấu giao dịch test sẽ commit và kết thúc nó; `start()` có thể bắt đầu một test-managed transaction mới nếu điều kiện cho phép. Đây là công cụ điều khiển giao dịch test, không phải cách thay thế propagation của service.

Ví dụ khái niệm:

```java
@Test
@Transactional
void explicitlyEndsTestTransaction() {
    orderService.createOrder("ORDER-200");

    TestTransaction.flagForRollback();
    TestTransaction.end();

    // T0 đã kết thúc tại đây.
    // Có thể truy vấn trạng thái bên ngoài T0 theo cách phù hợp.
}
```

Nếu muốn kiểm tra dữ liệu đã commit bởi `REQUIRES_NEW`, hãy quan sát sau khi T0 kết thúc hoặc từ một transaction/connection độc lập. Một truy vấn chạy bên trong T0 trước khi kết thúc có thể bị ảnh hưởng bởi snapshot isolation hoặc cache của persistence context và không phải lúc nào cũng thể hiện trạng thái commit từ giao dịch khác theo cách mong đợi.

Không cần dùng `TestTransaction` cho mọi test. Nó hữu ích khi test cần kiểm tra rõ ranh giới trước và sau khi giao dịch test kết thúc.

## 16. Cách đọc propagation trên đường gọi

Khi một test gọi một service và dữ liệu vẫn còn sau rollback, hãy lần theo toàn bộ chuỗi lời gọi:

```text
Test method (@Transactional)
       |
       v
Service A (@Transactional)
       |
       +--> Repository A
       |
       +--> Service B (@Transactional)
                  |
                  +--> Repository B
                  |
                  +--> Async worker?
```

Ở mỗi bước, hãy ghi nhận:

- Phương thức có được gọi qua Spring proxy hay không.
- Propagation của phương thức là gì.
- Có transaction hiện hành tại thời điểm gọi không.
- Transaction manager nào quản lý tài nguyên.
- Phương thức có mở thread hoặc tác vụ bất đồng bộ không.
- Giao dịch được commit, rollback hay chỉ bị tạm ngưng.
- Có thao tác nào nằm ngoài transaction test không.

Ví dụ, nếu Service A dùng `REQUIRED`, Service B dùng `REQUIRES_NEW`, và Repository B tham gia giao dịch hiện hành, dữ liệu ở Repository B được ghi trong giao dịch mới của Service B. Nếu Service B commit, rollback của test chỉ hoàn tác phần nằm trong giao dịch ngoài.

Nếu Service B dùng `NOT_SUPPORTED`, giao dịch ngoài bị tạm ngưng trong lúc Service B chạy. Cần tiếp tục lần xuống repository để biết nó có mở transaction riêng hay dùng autocommit. Chỉ nhìn annotation ở Service B chưa đủ để kết luận dữ liệu sẽ commit như thế nào.

## 17. Lựa chọn propagation theo yêu cầu nghiệp vụ

Không nên chọn propagation chỉ để làm test dễ viết. Hãy xác định quan hệ nhất quán dữ liệu mà nghiệp vụ cần.

| Yêu cầu | Propagation thường phù hợp |
|---|---|
| Tất cả thao tác phải cùng commit hoặc rollback | `REQUIRED` |
| Một phần ghi nhận phải commit độc lập với nghiệp vụ ngoài | Cân nhắc `REQUIRES_NEW` |
| Một phần xử lý không được chạy trong transaction hiện tại | Cân nhắc `NOT_SUPPORTED` |
| Phần thao tác con có thể rollback về savepoint trong giao dịch ngoài | `NESTED`, nếu transaction manager hỗ trợ |
| Phương thức có thể chạy trong hoặc ngoài transaction | `SUPPORTS` |
| Phương thức bắt buộc phải có transaction từ caller | `MANDATORY` |
| Phương thức phải chạy khi không có transaction | `NEVER` |

Ví dụ, ghi audit độc lập có thể cần `REQUIRES_NEW` nếu quy tắc yêu cầu audit phải tồn tại ngay cả khi nghiệp vụ chính rollback. Nhưng nếu audit record chỉ có ý nghĩa khi đơn hàng được commit, `REQUIRED` có thể phù hợp hơn để cả hai cùng thành công hoặc thất bại.

Propagation là một quyết định về tính nhất quán và ranh giới commit, không chỉ là một tùy chọn kỹ thuật.

## 18. Quy trình chẩn đoán khi test rollback không dọn hết dữ liệu

Khi dữ liệu vẫn còn sau một test có `@Transactional`, có thể điều tra theo trình tự:

1. **Xác nhận test-managed transaction:** kiểm tra test có được Spring TestContext quản lý transaction và rollback hay không.
2. **Xác định transaction manager:** kiểm tra datasource hoặc tài nguyên mà test đang sử dụng.
3. **Lần theo bean được gọi:** tìm các phương thức có `@Transactional` trên toàn bộ đường gọi.
4. **Đọc propagation:** chú ý `REQUIRES_NEW`, `NOT_SUPPORTED` và các propagation yêu cầu hoặc cấm transaction.
5. **Kiểm tra proxy:** xác định lời gọi có đi qua Spring proxy hay là self-invocation.
6. **Kiểm tra ranh giới thread:** xem code có chạy trong executor, `@Async` hoặc callback khác thread không.
7. **Xác định commit thực tế:** tìm nơi giao dịch độc lập kết thúc bình thường và commit.
8. **Chọn cleanup phù hợp:** dùng `@AfterTransaction`, cleanup transaction riêng hoặc reset database.
9. **Chạy lại nhiều lần:** bảo đảm test không để lại dữ liệu khiến lần chạy sau thất bại.

Khi hiểu propagation của mã được gọi, ta có thể giải thích vì sao một test-managed transaction rollback nhưng một phần dữ liệu vẫn tồn tại. `REQUIRED` thường cho phép mã ứng dụng tham gia giao dịch test; `REQUIRES_NEW` có thể commit độc lập; `NOT_SUPPORTED` tạm ngưng giao dịch test; còn `NESTED` dựa trên savepoint nếu tài nguyên hỗ trợ. Kiểm tra đúng ranh giới transaction, proxy và thread giúp thiết kế test có cleanup phù hợp và tránh dữ liệu rò rỉ giữa các lần chạy.


# Cơ chế proxy, lời gọi nội bộ và tình huống giao dịch không hoạt động trong Spring Data JPA

## Mục tiêu

Sau bài này, bạn có thể giải thích Spring áp dụng `@Transactional` qua proxy như thế nào, nhận diện lỗi **self-invocation** khi một phương thức gọi phương thức khác trong cùng bean, chọn cách tổ chức ranh giới giao dịch phù hợp và chẩn đoán những nguyên nhân phổ biến khiến giao dịch không bắt đầu hoặc không rollback như mong đợi.

Phạm vi là ứng dụng Spring dùng Spring Data JPA và giao dịch đồng bộ kiểu imperative với `PlatformTransactionManager`.

## 1. `@Transactional` được thực thi qua proxy

`@Transactional` chủ yếu là metadata mô tả chính sách giao dịch. Trong chế độ proxy mặc định, Spring tạo một proxy bao quanh Spring bean. Khi một bean khác gọi phương thức transactional thông qua proxy, bộ chặn giao dịch (`TransactionInterceptor`) đọc metadata, làm việc với transaction manager, rồi mới gọi phương thức thật.

Luồng điển hình:

1. Bean A gọi phương thức của bean B thông qua tham chiếu được Spring inject.
2. Lời gọi đi vào proxy của B.
3. Proxy tìm cấu hình `@Transactional` và yêu cầu transaction manager bắt đầu giao dịch mới hoặc tham gia giao dịch đang có, tùy `propagation`.
4. Proxy gọi phương thức trên đối tượng đích.
5. Khi phương thức kết thúc, proxy commit hoặc rollback theo kết quả thực thi và quy tắc rollback.

Spring có thể dùng JDK dynamic proxy hoặc class-based proxy (CGLIB). Chi tiết loại proxy không thay đổi nguyên tắc cốt lõi: **lời gọi phải đi qua proxy thì transaction advice mới được áp dụng**.

Ví dụ về một ranh giới giao dịch thông thường:

```java
@Service
public class OrderService {
    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void createOrder(Order order) {
        orderRepository.save(order);
    }
}
```

Khi một controller hoặc service khác gọi `orderService.createOrder(order)` qua bean được inject, lời gọi đi qua proxy và giao dịch được mở trước khi thân phương thức chạy.

Nếu gọi trực tiếp một đối tượng được tạo bằng `new OrderService(...)`, đối tượng đó không được Spring quản lý và không có proxy giao dịch do Spring tạo ra. Annotation trên đối tượng ấy không tự khởi tạo giao dịch.

## 2. Self-invocation: lời gọi nội bộ bỏ qua proxy

Self-invocation xảy ra khi một phương thức trong bean gọi một phương thức khác của chính bean đó, chẳng hạn `this.saveOne()` hoặc gọi trực tiếp `saveOne()`.

Ví dụ:

```java
@Service
public class ImportService {
    private final ImportRepository repository;

    public ImportService(ImportRepository repository) {
        this.repository = repository;
    }

    public void importAll(List<ImportRow> rows) {
        for (ImportRow row : rows) {
            saveOne(row); // Lời gọi nội bộ trên cùng đối tượng
        }
    }

    @Transactional
    public void saveOne(ImportRow row) {
        repository.save(row);
    }
}
```

Khi bean bên ngoài gọi `importAll()`, proxy có thể nhận lời gọi đó. Tuy nhiên, trong thân `importAll()`, lệnh `saveOne(row)` gọi thẳng phương thức trên đối tượng đích. Lời gọi này không quay lại proxy, vì vậy annotation trên `saveOne()` không được xử lý ở lần gọi nội bộ đó.

Hệ quả phụ thuộc vào việc có giao dịch bên ngoài hay không:

- **Không có giao dịch bên ngoài:** `saveOne()` không tự mở giao dịch dù có `@Transactional`. Nếu nó gọi các phương thức CRUD của Spring Data repository, từng lời gọi repository vẫn có thể dùng giao dịch riêng theo cấu hình mặc định của repository. Vì thế, toàn bộ vòng lặp không tự động trở thành một giao dịch nguyên tử.
- **Có giao dịch bên ngoài:** `saveOne()` chạy trong ngữ cảnh giao dịch hiện có nếu có. Tuy nhiên, các thuộc tính đặt riêng trên `saveOne()` bị bỏ qua. Ví dụ `propagation = REQUIRES_NEW` không tạo giao dịch mới, `readOnly` và `timeout` riêng cũng không được áp dụng.

Ví dụ thứ hai làm rõ lỗi thường gặp:

```java
@Service
public class OrderService {
    @Transactional
    public void placeOrder(Order order) {
        saveAudit(order); // Không đi qua proxy
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit(Order order) {
        // Người viết mong đợi một giao dịch độc lập
    }
}
```

`placeOrder()` được gọi từ bean khác nên giao dịch ngoài bắt đầu. Nhưng `saveAudit()` được gọi nội bộ, do đó `REQUIRES_NEW` không có hiệu lực. Phần ghi audit vẫn nằm trong giao dịch của `placeOrder()`. Nếu giao dịch ngoài rollback, phần audit cũng rollback theo.

Lưu ý: nếu `placeOrder()` không có `@Transactional`, lời gọi nội bộ tới `saveAudit()` cũng không tạo giao dịch. Không nên kết luận rằng cứ nhìn thấy annotation trên phương thức là phương thức đó chắc chắn đang chạy trong transaction.

## 3. Cách khắc phục self-invocation

### 3.1. Tách ranh giới giao dịch sang một bean khác

Đây thường là cách dễ hiểu và dễ kiểm thử nhất. Bean điều phối gọi bean nghiệp vụ khác thông qua dependency được Spring inject, vì vậy lời gọi đi qua proxy của bean đích.

```java
@Service
public class ImportCoordinator {
    private final ImportItemService itemService;

    public ImportCoordinator(ImportItemService itemService) {
        this.itemService = itemService;
    }

    public void importAll(List<ImportRow> rows) {
        for (ImportRow row : rows) {
            itemService.saveOne(row); // Gọi qua proxy của bean khác
        }
    }
}

@Service
public class ImportItemService {
    private final ImportRepository repository;

    public ImportItemService(ImportRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveOne(ImportRow row) {
        repository.save(row);
    }
}
```

Trong ví dụ này, mỗi lần gọi `saveOne()` có thể mở một giao dịch mới. Nếu muốn cả lô dữ liệu thành công hoặc thất bại cùng nhau, hãy đặt `@Transactional` trên phương thức điều phối và dùng propagation phù hợp, thường là `REQUIRED` ở các phương thức được gọi. Hãy chọn chính sách dựa trên yêu cầu nhất quán dữ liệu, vì `REQUIRES_NEW` cố ý tách commit/rollback của từng phần.

### 3.2. Gọi qua self-reference hoặc proxy hiện tại

Có thể inject một tham chiếu tới chính bean, hoặc dùng `AopContext.currentProxy()` khi bật `exposeProxy`. Cách này khiến bean phụ thuộc trực tiếp vào cơ chế AOP, dễ gây khó hiểu và khó kiểm thử. Chỉ cân nhắc khi không thể tách trách nhiệm thành bean khác và đã hiểu rõ cách Spring giải quyết self-reference.

### 3.3. Dùng AspectJ weaving khi thực sự cần

Chế độ AspectJ weaving có thể áp dụng advice cả với self-invocation vì nó can thiệp vào bytecode thay vì chỉ dựa vào proxy. Cách này cần cấu hình weaving và quy trình build/runtime phù hợp, phức tạp hơn proxy mode thông thường. Phần lớn ứng dụng Spring Data JPA không cần chuyển sang AspectJ chỉ để sửa một lời gọi nội bộ.

## 4. Những trường hợp phổ biến khiến giao dịch không hoạt động

| Nguyên nhân | Biểu hiện | Cách kiểm tra hoặc xử lý |
|---|---|---|
| Self-invocation | Phương thức nội bộ có `@Transactional` nhưng không mở giao dịch hoặc không áp dụng propagation riêng | Tách sang bean khác và gọi qua dependency được inject |
| Đối tượng không do Spring quản lý | Annotation không có tác dụng trên đối tượng được tạo bằng `new` | Đăng ký bean bằng component scanning hoặc cấu hình bean, rồi inject bean |
| Transaction management chưa được bật hoặc thiếu manager | Không có transaction advice hoặc không có transaction manager phù hợp | Với Spring Boot và starter Data JPA, kiểm tra auto-configuration; cấu hình thủ công cần bật transaction management và khai báo `PlatformTransactionManager` |
| Phương thức không thể được proxy intercept | Lời gọi không qua phương thức proxy có thể ghi đè hoặc phương thức không nằm trên interface proxy | Ưu tiên phương thức public; kiểm tra loại proxy, class/method `final`, phương thức `private` và interface được proxy |
| Chọn sai transaction manager | Một phần thao tác chạy trong manager khác với manager được mong đợi | Kiểm tra các bean transaction manager và chỉ rõ qualifier trong `@Transactional("...")` khi có nhiều manager |
| Propagation không tạo giao dịch | Phương thức chạy mà không có transaction đang hoạt động | Kiểm tra `SUPPORTS`, `NOT_SUPPORTED`, `NEVER` và ngữ cảnh của lời gọi |
| Exception không kích hoạt rollback | Dữ liệu vẫn commit dù có exception | Kiểm tra loại exception, `rollbackFor`, việc bắt exception và trạng thái rollback-only |
| Chuyển sang thread khác | Giao dịch của thread gọi không hiện diện ở thread mới | Mở giao dịch trong bean chạy ở thread đích; không dựa vào việc truyền transaction imperative qua `@Async` hoặc `new Thread` |
| Chỉ có thao tác đọc hoặc chưa flush | Chưa thấy SQL hoặc lỗi ràng buộc tại thời điểm mong đợi | Hiểu cơ chế flush của JPA; dùng `flush()` khi cần đẩy SQL sớm để phát hiện lỗi |

### 4.1. Giới hạn của proxy và visibility

Với JDK dynamic proxy, lời gọi phải đi qua phương thức được khai báo trên interface proxy. Với class-based proxy, proxy dựa trên kế thừa; phương thức `final` không thể được override để thêm advice, còn phương thức `private` không thể được intercept theo cách proxy thông thường.

Spring Framework 6 hỗ trợ phương thức `protected` và package-visible cho class-based proxy trong cấu hình transaction annotation mặc định tương ứng; với interface-based proxy, phương thức transactional cần public và nằm trên interface. Để tránh khác biệt giữa loại proxy và cấu hình, nên đặt ranh giới giao dịch ở phương thức public của service bean.

### 4.2. Exception và quy tắc rollback

Mặc định, Spring rollback khi phương thức transactional ném `RuntimeException` hoặc `Error`. Checked exception không tự động kích hoạt rollback theo quy tắc mặc định.

```java
@Transactional(rollbackFor = Exception.class)
public void importFile() throws Exception {
    repository.save(...);
    validateFile(); // Checked exception cũng yêu cầu rollback
}
```

Nếu nghiệp vụ cần rollback khi có checked exception, khai báo `rollbackFor` phù hợp. Có thể dùng `noRollbackFor` cho trường hợp ngoại lệ cần commit, nhưng phải cân nhắc kỹ vì dữ liệu có thể được lưu dù phương thức báo lỗi.

Nếu phương thức bắt exception rồi kết thúc bình thường, transaction interceptor nhìn thấy một lần thực thi thành công và có thể commit. Nếu đã bắt lỗi nhưng vẫn cần rollback, hãy ném lại exception hoặc chủ động đánh dấu transaction rollback-only bằng API phù hợp. Không nên nuốt exception rồi kỳ vọng Spring tự biết cần rollback.

### 4.3. Giao dịch không tự truyền qua thread

Giao dịch imperative của Spring thường gắn với thread hiện tại. Khi một phương thức đang có transaction gọi `@Async`, tạo `new Thread` hoặc gửi công việc sang executor, thread mới không tự kế thừa transaction của thread gọi.

Nếu công việc nền cần transaction, hãy để phương thức được gọi trên thread nền là một Spring bean và đặt ranh giới `@Transactional` tại đó. Với ứng dụng reactive, transaction được quản lý qua Reactor context và cần reactive transaction manager; không áp dụng giả định thread-local của JPA imperative cho luồng reactive.

## 5. Hiểu propagation để đọc đúng hành vi

`Propagation` xác định phương thức xử lý thế nào khi đã có hoặc chưa có transaction. Giá trị mặc định của `@Transactional` là `REQUIRED`.

| Propagation | Khi đã có transaction | Khi chưa có transaction |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện có | Bắt đầu transaction mới |
| `REQUIRES_NEW` | Tạm ngưng transaction hiện có và bắt đầu transaction mới | Bắt đầu transaction mới |
| `SUPPORTS` | Tham gia transaction hiện có | Chạy mà không cần transaction |
| `NOT_SUPPORTED` | Tạm ngưng transaction hiện có | Chạy không có transaction |
| `MANDATORY` | Tham gia transaction hiện có | Ném lỗi vì không có transaction |
| `NEVER` | Ném lỗi nếu đang có transaction | Chạy không có transaction |
| `NESTED` | Có thể dùng savepoint nếu transaction manager hỗ trợ | Bắt đầu transaction mới |

Một số lưu ý khi áp dụng với JPA:

- `REQUIRES_NEW` có thể cần một connection khác trong khi transaction ngoài đang bị suspend. Nếu lặp nhiều lần với connection pool nhỏ, cần xem xét nguy cơ cạn connection.
- `NESTED` phụ thuộc transaction manager và khả năng hỗ trợ savepoint của nền tảng; không nên mặc định rằng mọi cấu hình `JpaTransactionManager` đều cung cấp nested transaction theo cách mong muốn.
- Propagation chỉ được áp dụng khi lời gọi đi qua proxy. Nếu `REQUIRES_NEW` nằm trên một phương thức bị self-invocation, cấu hình đó không được thực thi.
- `readOnly = true` là gợi ý/optimization cho transaction manager và persistence provider, không phải cơ chế phân quyền bảo đảm mọi lệnh ghi đều bị chặn.

## 6. Ranh giới giao dịch với Spring Data JPA repository

Các phương thức CRUD kế thừa từ `CrudRepository`/`JpaRepository` có cấu hình giao dịch mặc định của Spring Data JPA: thao tác ghi thường có `@Transactional`, còn thao tác đọc thường dùng `readOnly = true`. Tuy nhiên, các query method do ứng dụng tự khai báo không tự động có cấu hình transaction riêng theo mặc định.

Với nghiệp vụ gồm nhiều thao tác repository, nên đặt ranh giới giao dịch ở service:

```java
@Service
public class TransferService {
    private final AccountRepository accountRepository;

    public TransferService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Transactional
    public void transfer(Long fromId, Long toId, BigDecimal amount) {
        Account from = accountRepository.findById(fromId).orElseThrow();
        Account to = accountRepository.findById(toId).orElseThrow();

        from.withdraw(amount);
        to.deposit(amount);

        accountRepository.save(from);
        accountRepository.save(to);
    }
}
```

Khi service được gọi qua proxy, các thao tác đọc và ghi tham gia cùng transaction của service. Nếu cập nhật tài khoản thứ hai thất bại và exception kích hoạt rollback, thay đổi của tài khoản thứ nhất cũng được rollback trong cùng transaction.

Đừng nhầm việc một lệnh `repository.save()` chạy thành công với việc toàn bộ use case đã được bảo vệ bởi một transaction duy nhất. Nếu không có service transaction, nhiều lệnh repository có thể commit độc lập.

## 7. Cách kiểm tra transaction khi debug

Có thể dùng `TransactionSynchronizationManager` để quan sát trạng thái transaction trong lúc chạy:

```java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean readOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();

System.out.println("transactionActive=" + active);
System.out.println("transactionReadOnly=" + readOnly);
```

Đặt phép kiểm tra ở đầu phương thức cần chẩn đoán và so sánh khi gọi từ bean khác với khi gọi nội bộ. Kết quả `false` ở đầu phương thức là dấu hiệu hữu ích cho biết tại thời điểm đó không có transaction thực sự đang hoạt động; nó không tự chỉ ra nguyên nhân.

Quy trình chẩn đoán:

1. Xác nhận service là Spring bean và caller đang dùng bean được inject.
2. Xác nhận lời gọi đi qua proxy, không phải self-invocation.
3. Xác nhận transaction management và transaction manager phù hợp đã được cấu hình.
4. Kiểm tra loại proxy, visibility và modifier của phương thức.
5. Kiểm tra propagation, đặc biệt là `SUPPORTS`, `NOT_SUPPORTED`, `NEVER` và các lời gọi `REQUIRES_NEW`.
6. Kiểm tra exception có thoát khỏi phương thức hay bị bắt; đối chiếu với `rollbackFor`/`noRollbackFor`.
7. Kiểm tra thao tác có chạy trên thread khác hay không.
8. Nếu SQL hoặc lỗi constraint xuất hiện muộn, kiểm tra thời điểm JPA flush và commit.

Có thể bật log DEBUG cho transaction infrastructure của Spring khi cần xem thời điểm transaction được mở, tham gia, commit hoặc rollback. Khi debug, tránh chỉ dựa vào việc annotation có xuất hiện trên source code; hãy kiểm tra trạng thái transaction tại đúng điểm thực thi.

## 8. Checklist trước khi đưa code lên môi trường chạy

- [ ] Service được Spring quản lý và được inject từ container.
- [ ] Caller gọi phương thức transactional qua proxy.
- [ ] Không dựa vào self-invocation để kích hoạt `@Transactional`.
- [ ] Ranh giới giao dịch bao trùm đúng toàn bộ nghiệp vụ cần nguyên tử.
- [ ] Propagation phù hợp với yêu cầu commit/rollback.
- [ ] Checked exception có `rollbackFor` nếu nghiệp vụ yêu cầu rollback.
- [ ] Không nuốt exception khi cần rollback.
- [ ] Không giả định transaction imperative tự truyền sang thread nền.
- [ ] Các query method tự khai báo có transaction khi cần.
- [ ] Đã kiểm tra kết quả commit/rollback và trạng thái dữ liệu bằng integration test.

## Kết luận

Trong Spring Data JPA, `@Transactional` hoạt động thông qua transaction advice được gắn vào proxy của Spring bean. Lời gọi từ bean khác có thể đi qua proxy, còn lời gọi nội bộ trong cùng đối tượng bỏ qua proxy và không áp dụng cấu hình giao dịch của phương thức được gọi. Khi giao dịch không hoạt động như mong đợi, hãy lần lượt kiểm tra bean/proxy, self-invocation, cấu hình transaction manager, propagation, rollback rules và thread thực thi. Đặt ranh giới giao dịch ở service bean và tách các thao tác cần chính sách riêng sang bean khác thường giúp hành vi rõ ràng, dễ kiểm thử và dễ bảo trì hơn.

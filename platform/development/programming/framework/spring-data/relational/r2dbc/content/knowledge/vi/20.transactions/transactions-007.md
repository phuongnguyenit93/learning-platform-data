# Quy tắc rollback theo loại lỗi và cấu hình

Trong Spring Data Relational R2DBC, transaction gom nhiều thao tác database thành một đơn vị: hoặc tất cả được commit, hoặc các thay đổi được rollback theo chính sách transaction. Tuy nhiên, không phải mọi exception đều khiến Spring rollback. Kết quả phụ thuộc vào loại lỗi, cấu hình rollback rule, cách lỗi đi qua reactive pipeline và transaction manager đang quản lý kết nối.

Với declarative transaction qua annotation @Transactional, mặc định Spring rollback khi phương thức kết thúc bằng RuntimeException hoặc Error. Checked exception không kích hoạt rollback theo quy tắc mặc định. Có thể thay đổi hành vi bằng rollbackFor và noRollbackFor.

Trong reactive code, điều quan trọng là exception phải được phát ra như tín hiệu onError trong Publisher để transaction interceptor nhận biết. Nếu ứng dụng bắt lỗi và chuyển thành kết quả hoàn tất bình thường bên trong ranh giới transaction, Spring có thể commit. Cancellation của reactive transaction cũng cần được chú ý vì việc hủy subscription dẫn tới rollback.

## 1. Transaction và rollback trong R2DBC

Một transaction thường gồm các thao tác như:

1. Đọc số dư tài khoản.
2. Trừ tiền ở tài khoản nguồn.
3. Cộng tiền ở tài khoản đích.
4. Ghi lịch sử giao dịch.
5. Commit khi tất cả thao tác thành công.

Nếu bước cộng tiền hoặc ghi lịch sử thất bại, ứng dụng thường cần rollback để không giữ lại trạng thái dở dang.

~~~text
BEGIN
  |
  v
Đọc dữ liệu
  |
  v
UPDATE tài khoản nguồn
  |
  v
UPDATE tài khoản đích
  |
  v
INSERT lịch sử
  |
  +---- Tất cả thành công ----> COMMIT
  |
  +---- Có lỗi cần rollback --> ROLLBACK
~~~

R2DBC là API truy cập database reactive. Spring dùng ReactiveTransactionManager để quản lý transaction và connection theo reactive context. Với Spring Data R2DBC, transaction manager phổ biến là R2dbcTransactionManager.

Rollback là thao tác kết thúc transaction và hủy các thay đổi chưa commit. Nó không tự hoàn tác các tác động bên ngoài database như gửi email, gọi HTTP service, ghi file hoặc phát message đến hệ thống không tham gia cùng transaction.

## 2. Cấu hình ReactiveTransactionManager

Spring cần một ReactiveTransactionManager phù hợp với ConnectionFactory mà các repository và DatabaseClient sử dụng.

Ví dụ cấu hình:

~~~java
@Configuration
public class R2dbcTransactionConfiguration {

    @Bean
    public ReactiveTransactionManager r2dbcTransactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

R2dbcTransactionManager quản lý transaction trên một R2DBC ConnectionFactory. Khi bắt đầu transaction, manager lấy connection và bind tài nguyên đó vào Reactor Context để các thao tác database tham gia cùng transaction có thể dùng lại.

Các điều kiện quan trọng:

- Repository và DatabaseClient phải sử dụng cùng ConnectionFactory được transaction manager quản lý.
- Phương thức reactive phải trả về Publisher như Mono hoặc Flux để Spring áp dụng reactive transaction semantics.
- Các thao tác phải được nối trong cùng reactive chain để transaction context được truyền tiếp.
- Không tự gọi subscribe() bên trong service để chạy một thao tác database tách rời.

Trong Spring Boot, transaction manager có thể được auto-configure khi ứng dụng có cấu hình R2DBC phù hợp. Nếu tự khai báo nhiều ConnectionFactory hoặc nhiều transaction manager, cần chỉ định manager đúng cho từng use case.

Có thể chỉ rõ bean transaction manager trong annotation:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> process() {
    // Reactive database operations
    return Mono.empty();
}
~~~

Nếu dùng transaction manager không phù hợp, annotation có thể không quản lý đúng các thao tác R2DBC. Hãy kiểm tra loại manager, ConnectionFactory và transaction boundary của phương thức.

## 3. Quy tắc rollback mặc định của @Transactional

Với declarative transaction, Spring mặc định:

- Rollback khi exception là RuntimeException hoặc một lớp con của RuntimeException.
- Rollback khi exception là Error hoặc một lớp con của Error.
- Không rollback mặc định khi exception là checked exception, tức Throwable không thuộc RuntimeException hoặc Error.

Ví dụ:

~~~java
public class InventoryUnavailableException extends RuntimeException {
}

public class ExportFormatException extends Exception {
}
~~~

Nếu hai exception được phát ra khỏi một phương thức @Transactional:

| Loại lỗi | Quy tắc mặc định | Kết quả thường gặp |
|---|---|---|
| RuntimeException | Rollback | Transaction rollback |
| IllegalArgumentException | Rollback | Transaction rollback |
| Error | Rollback | Transaction rollback |
| Checked exception | Không rollback | Spring cố commit rồi truyền lỗi |

Điều này có nghĩa một checked exception có thể được truyền tới caller nhưng các thay đổi database vẫn được commit. Đây là hành vi dễ gây bất ngờ nếu lập trình viên cho rằng cứ có exception là rollback.

Quy tắc mặc định là chính sách của Spring transaction abstraction. Database hoặc driver vẫn có thể đánh dấu transaction là lỗi và từ chối commit sau một lỗi SQL. Vì vậy, kết quả cuối cùng còn phụ thuộc trạng thái transaction mà database duy trì.

## 4. Dùng rollbackFor để rollback với checked exception

Nếu một checked exception phải làm transaction rollback, khai báo rollbackFor:

~~~java
@Transactional(rollbackFor = ExportFormatException.class)
public Mono<Void> createExportRecord() {
    return exportRepository.save(new ExportRecord())
        .then(Mono.error(new ExportFormatException()));
}
~~~

Trong ví dụ, ExportFormatException kế thừa Exception. Theo mặc định, checked exception này không yêu cầu rollback. Với rollbackFor, Spring áp dụng rollback rule cho loại exception đó.

Có thể khai báo nhiều loại:

~~~java
@Transactional(
    rollbackFor = {
        ExportFormatException.class,
        BusinessValidationException.class
    }
)
public Mono<Void> executeExport() {
    return performExport();
}
~~~

rollbackFor nhận các lớp exception. Nên dùng kiểu class cụ thể thay vì tên chuỗi để tránh lỗi do tên class hoặc pattern khớp ngoài dự kiến.

Có thể dùng rollbackFor = Exception.class để rollback với cả checked và unchecked exception. Tuy nhiên, rule rộng như vậy có thể không phù hợp nếu nghiệp vụ có các exception mà transaction vẫn được phép commit. Hãy chọn đúng loại lỗi cần rollback.

## 5. Dùng noRollbackFor để không rollback với một loại lỗi

Đôi khi một exception biểu thị cảnh báo nghiệp vụ nhưng thay đổi database vẫn cần được commit. Có thể dùng noRollbackFor:

~~~java
@Transactional(noRollbackFor = NotificationPendingException.class)
public Mono<Customer> activateCustomer(Long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(id)
        ))
        .flatMap(customer -> {
            customer.activate();
            return customerRepository.save(customer);
        })
        .flatMap(saved ->
            notificationService.sendActivationNotice(saved)
                .thenReturn(saved)
                .onErrorMap(error ->
                    new NotificationPendingException(
                        "Customer activated but notification failed",
                        error
                    )
                )
        );
}
~~~

Nếu NotificationPendingException thoát khỏi phương thức transactional, Spring áp dụng noRollbackFor và không yêu cầu rollback chỉ vì exception này. Exception vẫn có thể được truyền về caller; noRollbackFor không có nghĩa là nuốt lỗi hoặc trả kết quả thành công.

Đây chỉ là ví dụ về rollback policy. Nếu notification là lời gọi HTTP hoặc gửi email, transaction database không thể rollback tác động bên ngoài đó. Trong hệ thống thực tế, nên cân nhắc outbox pattern hoặc cơ chế retry độc lập để xử lý việc gửi notification đáng tin cậy.

## 6. Khi rollbackFor và noRollbackFor cùng khớp

Spring chọn rule khớp cụ thể nhất với loại exception thực tế. Có thể hiểu là rule có khoảng cách kế thừa gần nhất trong exception hierarchy sẽ có ưu tiên.

Ví dụ:

~~~java
@Transactional(
    rollbackFor = Exception.class,
    noRollbackFor = NotificationPendingException.class
)
public Mono<Void> process() {
    return performWork();
}
~~~

Nếu lỗi là NotificationPendingException, rule noRollbackFor cụ thể hơn rule rollbackFor rộng cho Exception, nên transaction không rollback theo rule đó. Nếu lỗi là một checked exception khác, rollbackFor = Exception.class áp dụng và transaction rollback.

Bảng minh họa:

| Exception thực tế | Rule khớp | Kết quả |
|---|---|---|
| NotificationPendingException | noRollbackFor cụ thể | Không rollback |
| ExportFormatException | rollbackFor Exception.class | Rollback |
| IllegalStateException | rollbackFor Exception.class và mặc định runtime | Rollback |

Không nên khai báo nhiều rule chồng chéo nếu không cần thiết. Khi có nhiều rule, hãy kiểm tra loại exception thực tế và rule cụ thể nhất để tránh hiểu nhầm.

## 7. Cấu hình rollback trong reactive method

Với R2DBC, phương thức transactional thường trả về Mono hoặc Flux:

~~~java
@Service
public class TransferService {

    private final AccountRepository accountRepository;
    private final TransferRepository transferRepository;

    @Transactional
    public Mono<Void> transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        return accountRepository.debit(fromId, amount)
            .then(accountRepository.credit(toId, amount))
            .then(transferRepository.record(
                fromId, toId, amount
            ))
            .then();
    }
}
~~~

Nếu một thao tác phát RuntimeException hoặc Error ra khỏi reactive chain, transaction mặc định rollback. Các thao tác trước đó trong cùng transaction không được commit.

Nếu nghiệp vụ dùng checked exception:

~~~java
@Transactional(rollbackFor = InsufficientFundsException.class)
public Mono<Void> transfer(
        Long fromId,
        Long toId,
        BigDecimal amount) {

    return accountRepository.findById(fromId)
        .switchIfEmpty(Mono.error(
            new AccountNotFoundException(fromId)
        ))
        .flatMap(account -> {
            if (account.getBalance().compareTo(amount) < 0) {
                return Mono.error(
                    new InsufficientFundsException()
                );
            }

            return performTransfer(account, toId, amount);
        });
}
~~~

InsufficientFundsException có thể kế thừa Exception. rollbackFor khai báo rõ rằng lỗi này phải làm transaction rollback.

Không cần và không nên gọi subscribe() trong phương thức service để bắt đầu thao tác. Spring transaction interceptor bọc publisher được trả về và quản lý transaction khi publisher được subscribe bởi tầng gọi.

## 8. Reactive error signal quyết định ranh giới rollback

Trong reactive programming, lỗi được phát ra qua tín hiệu onError. Spring cần nhận được tín hiệu này ở ranh giới transaction để áp dụng rollback policy.

Ví dụ giữ nguyên lỗi:

~~~java
return repository.save(entity)
    .then(Mono.error(new IllegalStateException("failed")));
~~~

Lỗi đi ra khỏi publisher, nên transaction interceptor có thể áp dụng rollback rule.

### onErrorMap vẫn phát lỗi

~~~java
return repository.save(entity)
    .then(Mono.error(new IllegalArgumentException("invalid")))
    .onErrorMap(
        IllegalArgumentException.class,
        error -> new BusinessOperationException(error)
    );
~~~

onErrorMap chuyển loại exception nhưng vẫn phát onError. Spring đánh giá rollback dựa trên exception sau khi mapping nếu đó là exception đi ra khỏi ranh giới transactional.

### onErrorResume có thể biến lỗi thành hoàn tất bình thường

~~~java
@Transactional
public Mono<Void> process() {
    return repository.save(entity)
        .then(Mono.error(new IllegalStateException("failed")))
        .onErrorResume(error -> Mono.empty());
}
~~~

Ở đây onErrorResume bắt lỗi và thay bằng Mono.empty(). Publisher kết thúc bình thường. Transaction interceptor có thể xem phương thức đã hoàn tất thành công và commit.

Nếu muốn rollback, đừng nuốt lỗi bên trong transaction. Có thể ghi log bằng doOnError rồi để lỗi tiếp tục đi ra:

~~~java
return repository.save(entity)
    .then(Mono.error(new IllegalStateException("failed")))
    .doOnError(error -> log.error("Operation failed", error));
~~~

doOnError chỉ thực hiện side effect; nó không thay thế onError bằng kết quả thành công.

## 9. Vị trí đặt onErrorResume ảnh hưởng đến transaction

Với TransactionalOperator, vị trí recover có thể làm thay đổi kết quả commit/rollback.

### Recover bên trong transaction

~~~java
Mono<Void> work =
    debit()
        .then(credit())
        .onErrorResume(error -> Mono.empty());

return transactionalOperator.transactional(work);
~~~

Lỗi được xử lý trước khi đi tới TransactionalOperator. Operator nhìn thấy publisher hoàn tất bình thường và có thể commit.

### Recover bên ngoài transaction

~~~java
Mono<Void> work =
    debit().then(credit());

return transactionalOperator.transactional(work)
    .onErrorResume(error -> {
        log.error("Transaction rolled back", error);
        return Mono.empty();
    });
~~~

Ở cách này, lỗi đi qua ranh giới TransactionalOperator trước. Operator thực hiện rollback rồi mới truyền lỗi ra ngoài. onErrorResume phía sau mới chuyển lỗi thành kết quả hoàn tất cho caller.

Nếu cần trả fallback nhưng vẫn rollback, đặt recovery sau transaction boundary hoặc đánh dấu transaction rollback-only bằng API status phù hợp. Không nên vô tình recover lỗi trước khi transaction manager nhìn thấy nó.

## 10. Cancellation trong reactive transaction

Reactive transaction có thể kết thúc bằng complete, error hoặc cancel. Cancellation xảy ra khi subscriber hủy subscription, chẳng hạn:

- Client HTTP ngắt kết nối.
- Operator timeout hủy upstream.
- take() hoặc next() dừng tiêu thụ Flux trước khi nguồn hoàn tất.
- Tầng gọi chủ động dispose subscription.

Đối với reactive transaction, cancellation dẫn tới rollback để tránh commit một luồng đã bị hủy giữa chừng.

Ví dụ:

~~~java
Flux<Customer> result =
    transactionalOperator.transactional(
        customerRepository.findAll()
            .doOnNext(this::process)
    );
~~~

Nếu subscriber chỉ lấy một phần dữ liệu rồi hủy, transaction có thể rollback. Không nên dùng next(), take(1) hoặc cancel sớm trong một transactional Flux nếu mục đích là commit toàn bộ thao tác.

Với truy vấn chỉ cần một kết quả, dùng Mono và API phù hợp. Với tác vụ cần xử lý toàn bộ tập dữ liệu, hãy tiêu thụ publisher đến khi hoàn tất hoặc chia thành các transaction/batch có chủ đích.

## 11. Dùng TransactionalOperator

TransactionalOperator là API programmatic để bao một reactive pipeline trong transaction:

~~~java
public Mono<Void> transfer(Long fromId, Long toId, BigDecimal amount) {
    Mono<Void> work =
        accountRepository.debit(fromId, amount)
            .then(accountRepository.credit(toId, amount))
            .then(transferRepository.record(fromId, toId, amount))
            .then();

    return transactionalOperator.transactional(work);
}
~~~

Cấu hình operator:

~~~java
@Bean
public TransactionalOperator transactionalOperator(
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
~~~

TransactionalOperator phù hợp khi:

- Chỉ một phần của service cần transaction.
- Muốn nhìn thấy transaction boundary ngay trong reactive chain.
- Cần kết hợp transaction với các operator khác theo cách rõ ràng.
- Muốn xử lý lỗi bên ngoài transaction boundary sau khi rollback.

Khi dùng TransactionalOperator với pipeline được truyền vào, lỗi reactive thoát khỏi pipeline và cancellation được operator xử lý như đường rollback. Khác với annotation @Transactional, TransactionalOperator không cấu hình rollbackFor/noRollbackFor bằng annotation trên method; nó quản lý transaction qua API programmatic và transaction definition.

Nếu cần điều khiển rollback-only trong callback, có thể dùng transaction status mà callback cung cấp để đánh dấu rollback-only. Chỉ thực hiện điều này khi nghiệp vụ thật sự cần hoàn tất publisher nhưng vẫn không commit.

## 12. Cấu hình @Transactional chi tiết

Annotation @Transactional cho phép cấu hình nhiều khía cạnh:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    readOnly = false,
    rollbackFor = InsufficientFundsException.class
)
public Mono<Void> transfer(...) {
    return performTransfer(...);
}
~~~

Các thuộc tính thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| transactionManager | Chọn transaction manager |
| propagation | Cách tham gia hoặc tạo transaction |
| isolation | Mức cô lập của transaction |
| timeout | Thời gian tối đa theo cấu hình manager hỗ trợ |
| readOnly | Gợi ý hoặc chế độ chỉ đọc tùy manager/database |
| rollbackFor | Loại exception cần rollback |
| noRollbackFor | Loại exception không yêu cầu rollback |

### Propagation

Propagation xác định cách một thao tác tham gia transaction hiện có hoặc tạo transaction mới.

- REQUIRED là mặc định phổ biến: tham gia transaction hiện tại nếu có, nếu không thì tạo transaction mới.
- REQUIRES_NEW yêu cầu transaction mới theo khả năng hỗ trợ của transaction manager; transaction hiện tại có thể được suspend.
- SUPPORTS có thể chạy trong transaction hiện có hoặc không có transaction.
- MANDATORY yêu cầu phải có transaction hiện tại.
- NEVER yêu cầu không chạy trong transaction.

Không nên chọn propagation chỉ để chữa lỗi rollback. Trước tiên cần xác định các thao tác nào phải commit hoặc rollback cùng nhau.

### Isolation

Isolation điều khiển mức độ các transaction đồng thời nhìn thấy thay đổi của nhau. Các mức phổ biến gồm READ_COMMITTED, REPEATABLE_READ và SERIALIZABLE, nhưng mức hỗ trợ và semantics phụ thuộc database.

Nếu một phương thức tham gia transaction hiện có, cấu hình isolation của lời gọi bên trong thường không thay đổi isolation đã chọn lúc transaction ngoài bắt đầu. Cần cấu hình tại boundary thực sự tạo transaction.

### Timeout

Timeout giúp giới hạn thời gian transaction theo khả năng của transaction manager và driver. Nó không thay thế timeout ở HTTP client, pool acquire hoặc từng câu SQL. Cần hiểu timeout ở từng lớp có thể hủy publisher và làm reactive transaction rollback.

### Read-only

readOnly là một gợi ý hoặc thuộc tính transaction tùy khả năng manager/database. Không nên xem nó như cơ chế authorization hoặc bảo đảm mọi câu lệnh ghi đều bị database từ chối. Nếu cần ngăn ghi, hãy dùng quyền database và quy tắc ứng dụng phù hợp.

## 13. Transaction boundary và Reactor Context

Reactive transaction không dựa vào ThreadLocal như mô hình imperative truyền thống. Spring gắn transaction resource vào Reactor Context và các thao tác tham gia transaction lấy resource từ context đó.

Vì vậy, cần giữ các thao tác trong cùng reactive chain:

~~~java
@Transactional
public Mono<Void> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            orderLineRepository.saveAll(saved.getLines())
                .then()
        );
}
~~~

Không nên:

~~~java
@Transactional
public Mono<Void> createOrder(Order order) {
    orderRepository.save(order).subscribe();
    return Mono.empty();
}
~~~

subscribe() tạo một subscription độc lập. Phương thức transactional có thể hoàn tất trước khi thao tác save thực sự kết thúc; subscription mới cũng có thể không còn cùng transaction context. Hãy trả về publisher và nối bằng then, flatMap, concatMap hoặc operator phù hợp.

### Self-invocation

Spring thường áp dụng @Transactional qua proxy. Nếu một phương thức trong cùng class gọi trực tiếp một phương thức khác có @Transactional, lời gọi nội bộ có thể bỏ qua proxy và annotation không được áp dụng như mong đợi.

Hãy đặt transaction boundary ở public service method được gọi qua Spring bean proxy, hoặc tách phần cần transaction sang bean riêng. Cũng cần kiểm tra cấu hình proxy và visibility của method theo cách Spring transaction management đang dùng.

## 14. Nhiều transaction manager hoặc nhiều ConnectionFactory

Một transaction manager R2DBC quản lý connection thuộc ConnectionFactory mà nó được cấu hình. Nếu ứng dụng có hai database hoặc hai ConnectionFactory, một transaction manager không tự tạo transaction phân tán trên cả hai.

Ví dụ:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Void> updateOrder(...) {
    return ordersRepository.save(...);
}
~~~

Tên manager phải khớp bean được cấu hình cho database đó. Repository hoặc DatabaseClient truy cập database khác có thể không tham gia cùng transaction.

Nếu nghiệp vụ cần cập nhật nhiều database độc lập, cần một thiết kế nhất quán phù hợp, chẳng hạn saga, outbox hoặc quy trình bù trừ. Không giả định một annotation @Transactional sẽ rollback mọi database và dịch vụ bên ngoài.

## 15. Lỗi database và trạng thái transaction

Một số lỗi SQL có thể khiến database đánh dấu transaction là aborted. Trong tình huống đó, dù rollback rule của Spring không yêu cầu rollback với exception cụ thể, database vẫn có thể từ chối các câu lệnh tiếp theo hoặc không cho commit.

Ví dụ một unique constraint violation:

~~~java
return repository.save(entity)
    .onErrorResume(DuplicateKeyException.class, error ->
        repository.findByNaturalKey(entity.getNaturalKey())
            .then()
    );
~~~

Nếu lỗi duplicate xảy ra bên trong transaction, việc recover rồi tiếp tục truy vấn phụ thuộc database và trạng thái transaction sau lỗi. Một số database yêu cầu rollback transaction sau lỗi statement. Không nên giả định onErrorResume luôn cho phép tiếp tục transaction.

Với lỗi database, thường nên để transaction rollback và xử lý retry hoặc trả kết quả ở ngoài transaction boundary, trừ khi database và driver bảo đảm trạng thái transaction vẫn dùng được.

## 16. Retry và rollback

Retry có thể thực hiện lại publisher sau khi một transaction thất bại. Vị trí đặt retry rất quan trọng.

~~~java
return transactionalOperator.transactional(
        performTransfer()
    )
    .retryWhen(
        Retry.max(2)
            .filter(this::isTransientFailure)
    );
~~~

Với cấu trúc này, mỗi lần retry có thể subscribe lại publisher transaction và tạo một lần thực thi transaction mới, tùy cách operator được tạo và subscription. Điều này thường phù hợp hơn việc retry một câu lệnh bên trong transaction đã bị đánh dấu rollback-only.

Chỉ retry lỗi tạm thời như một số lỗi kết nối hoặc serialization failure theo chính sách của hệ thống. Không retry vô điều kiện lỗi validation, duplicate key hoặc lỗi nghiệp vụ.

Đảm bảo thao tác có tính idempotent hoặc có khóa idempotency nếu việc thực thi lại có thể gây side effect. Transaction database không tự bảo đảm một request chỉ được xử lý đúng một lần.

## 17. Bảng tình huống rollback thường gặp

| Tình huống | Hành vi mặc định hoặc cần cấu hình | Lưu ý |
|---|---|---|
| RuntimeException thoát khỏi @Transactional | Rollback | Mặc định |
| Error thoát khỏi @Transactional | Rollback | Mặc định |
| Checked exception thoát khỏi @Transactional | Không rollback mặc định | Dùng rollbackFor nếu cần |
| Exception nằm trong noRollbackFor | Không yêu cầu rollback theo rule đó | Lỗi vẫn có thể truyền ra caller |
| onErrorMap chuyển exception | Vẫn là onError | Rule áp dụng cho lỗi đi ra |
| onErrorResume bên trong transaction chuyển thành empty | Có thể commit | Transaction thấy completion bình thường |
| Lỗi được recover bên ngoài TransactionalOperator | Operator đã thấy lỗi trước recovery | Rollback rồi mới recover |
| Subscriber cancel reactive transaction | Rollback | Tránh hủy luồng trước khi hoàn tất nếu cần commit |
| SQL error làm database abort transaction | Thường cần rollback | Phụ thuộc database/driver |
| Tự subscribe bên trong service | Có thể tách khỏi transaction | Trả publisher cho caller |
| Hai ConnectionFactory khác nhau | Không mặc định cùng transaction | Cần manager và kiến trúc riêng |

## 18. Các lỗi cấu hình thường gặp

### Chỉ dùng @Transactional mà không có ReactiveTransactionManager

Annotation không tự tạo R2DBC transaction manager. Cần cấu hình manager phù hợp hoặc xác nhận auto-configuration đã tạo đúng bean.

### Chọn nhầm transaction manager

Ứng dụng có thể có cả PlatformTransactionManager và ReactiveTransactionManager. Hãy chỉ rõ transactionManager nếu có nhiều manager hoặc nhiều database.

### Dùng checked exception nhưng quên rollbackFor

Exception được truyền ra ngoài nhưng transaction có thể commit theo mặc định. Khai báo rollbackFor cho loại checked exception cần rollback.

### Nuốt lỗi bằng onErrorResume

Nếu lỗi được đổi thành kết quả hoàn tất bình thường bên trong transaction, rollback rule không còn thấy lỗi đó. Giữ tín hiệu onError hoặc đánh dấu rollback-only một cách tường minh.

### Tự gọi subscribe()

Subscription tách rời có thể chạy ngoài transaction context và không được chờ trong transaction boundary. Hãy compose publisher.

### Dùng transaction annotation trên method không trả Publisher

Reactive transaction cần phương thức trả về reactive type. Với method trả về void hoặc kiểu đồng bộ, reactive transaction manager không thể quản lý lifecycle theo cách mong đợi.

### Nghĩ readOnly ngăn mọi thao tác ghi

readOnly không phải ranh giới bảo mật. Dùng quyền database và validation phù hợp nếu phải cấm ghi.

## 19. Kiểm thử rollback

Nên dùng integration test với R2DBC driver và database thực tế hoặc Testcontainers. Kiểm thử rollback cần xác nhận trạng thái database sau khi publisher kết thúc, không chỉ xác nhận exception được phát ra.

Các trường hợp nên kiểm tra:

1. RuntimeException sau thao tác save: dữ liệu trước đó trong transaction không được commit.
2. Checked exception không có rollbackFor: xác nhận hành vi mặc định của declarative transaction.
3. Checked exception có rollbackFor: dữ liệu được rollback.
4. Exception có noRollbackFor: xác nhận transaction được phép commit nếu database vẫn cho commit.
5. Lỗi được recover bên trong transaction: kiểm tra transaction có commit do pipeline hoàn tất bình thường hay không.
6. Lỗi được recover bên ngoài TransactionalOperator: kiểm tra rollback xảy ra trước khi trả fallback.
7. Cancellation trước khi hoàn tất: kiểm tra transaction rollback.
8. Nhiều thao tác repository dùng cùng ConnectionFactory: xác nhận chúng tham gia cùng transaction.
9. Nhiều ConnectionFactory: xác nhận transaction manager được chọn đúng.
10. Lỗi SQL constraint: kiểm tra database có đánh dấu transaction aborted hay không.

Ví dụ ý tưởng cho test:

~~~java
StepVerifier.create(service.createThenFail())
    .expectError(IllegalStateException.class)
    .verify();

StepVerifier.create(repository.findByNaturalKey("test-key"))
    .verifyComplete();
~~~

Test đầu xác nhận publisher phát lỗi. Test thứ hai xác nhận dữ liệu chưa được commit. Chỉ kiểm tra expectError là chưa đủ để chứng minh rollback đã xảy ra.

Khi kiểm tra cancellation, cần tạo một publisher có thể giữ transaction mở, cancel subscription rồi truy vấn lại bằng một transaction mới để xác nhận dữ liệu chưa commit. Không dùng một truy vấn đọc trong chính transaction đã bị hủy làm bằng chứng.

## 20. Quy trình quyết định rollback policy

Trước khi cấu hình transaction cho một use case:

1. Xác định các thao tác database nào phải commit hoặc rollback cùng nhau.
2. Xác định transaction manager và ConnectionFactory sẽ quản lý các thao tác đó.
3. Liệt kê exception có thể thoát khỏi reactive pipeline.
4. Phân loại RuntimeException, Error và checked exception.
5. Chọn rollbackFor cho checked exception thực sự cần rollback.
6. Chỉ dùng noRollbackFor khi nghiệp vụ chấp nhận commit dù exception được truyền ra ngoài.
7. Kiểm tra các onErrorResume/onErrorComplete có nuốt lỗi bên trong transaction không.
8. Kiểm tra cancellation, timeout và các operator có thể hủy upstream.
9. Kiểm tra transaction propagation, isolation và timeout theo yêu cầu.
10. Viết integration test xác nhận dữ liệu sau commit và rollback.

Không nên dùng rollbackFor = Exception.class hoặc noRollbackFor = Exception.class một cách máy móc. Rule quá rộng có thể làm thay đổi hành vi của nhiều lỗi ngoài dự kiến.

## 21. Ghi nhớ

- Với @Transactional, Spring mặc định rollback RuntimeException và Error; checked exception không rollback mặc định.
- Dùng rollbackFor để chỉ định checked exception cần rollback.
- Dùng noRollbackFor khi một loại exception vẫn được phép commit; lỗi vẫn có thể được truyền tới caller.
- Khi nhiều rollback rule cùng khớp, rule cụ thể nhất với exception thực tế được ưu tiên.
- Reactive method phải trả Mono/Flux hoặc Publisher để Spring áp dụng reactive transaction.
- Lỗi phải đi ra dưới dạng onError để transaction boundary áp dụng rollback rule.
- onErrorResume bên trong transaction có thể biến lỗi thành completion và khiến transaction commit.
- Recover bên ngoài TransactionalOperator cho phép operator rollback trước khi caller nhận fallback.
- Cancellation của reactive transaction dẫn tới rollback; tránh cancel sớm nếu cần commit toàn bộ luồng.
- TransactionalOperator là cách quản lý transaction programmatic; không cấu hình rollbackFor/noRollbackFor như annotation.
- R2dbcTransactionManager quản lý connection theo ConnectionFactory và Reactor Context.
- Không tự subscribe trong service và không giả định nhiều ConnectionFactory hoặc dịch vụ ngoài cùng nằm trong một transaction.
- Kiểm thử phải xác nhận trạng thái dữ liệu sau transaction, không chỉ kiểm tra exception.

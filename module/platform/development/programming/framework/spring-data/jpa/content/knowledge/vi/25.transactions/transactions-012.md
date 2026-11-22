# TransactionTemplate: điều khiển giao dịch bằng mã

Trong Spring Data JPA, một giao dịch gom nhiều thao tác đọc/ghi thành một đơn vị công việc. Nếu một bước thất bại, các thay đổi trong giao dịch cần được rollback để dữ liệu không rơi vào trạng thái dở dang.

Thông thường, ta khai báo ranh giới giao dịch bằng `@Transactional`. Khi cần quyết định ranh giới giao dịch ngay trong luồng xử lý, chẳng hạn chạy từng lô dữ liệu trong một giao dịch riêng, chọn propagation theo tình huống hoặc chủ động đánh dấu rollback, Spring cung cấp `TransactionTemplate`.

`TransactionTemplate` là API giao dịch lập trình (programmatic transaction management). Nó nhận một callback, mở hoặc tham gia giao dịch thông qua `PlatformTransactionManager`, chạy callback, rồi commit hoặc rollback theo kết quả thực thi.

## 1. Khi nào nên dùng TransactionTemplate?

Dùng `@Transactional` khi ranh giới giao dịch gắn ổn định với một phương thức nghiệp vụ. Ví dụ: tạo đơn hàng, trừ tồn kho và ghi lịch sử đơn hàng luôn phải thành công hoặc thất bại cùng nhau.

Dùng `TransactionTemplate` khi ranh giới cần được thể hiện trực tiếp trong mã:

- Mỗi lô dữ liệu cần một giao dịch độc lập.
- Chỉ một nhánh điều kiện nhất định mới cần mở giao dịch.
- Một thành phần cần gọi một đoạn công việc có giao dịch mà không muốn đặt annotation lên toàn bộ phương thức gọi.
- Cần chủ động gọi `setRollbackOnly()` khi đã bắt và xử lý ngoại lệ bên trong callback.
- Cần chọn propagation hoặc timeout cho một đoạn công việc cụ thể.

Không cần dùng template cho mọi thao tác repository. Nếu `@Transactional` diễn đạt rõ ranh giới nghiệp vụ, annotation thường ngắn gọn và dễ đọc hơn.

## 2. Các thành phần tham gia

`TransactionTemplate` không tự quản lý kết nối cơ sở dữ liệu. Nó ủy quyền việc bắt đầu, tham gia, commit và rollback cho một `PlatformTransactionManager`.

Với một ứng dụng Spring Data JPA sử dụng một `EntityManagerFactory`, transaction manager thường là `JpaTransactionManager`. Spring Boot thường tự cấu hình transaction manager này khi ứng dụng có starter JPA và datasource phù hợp.

Luồng thực thi cơ bản:

1. Ứng dụng gọi `transactionTemplate.execute(...)` hoặc `executeWithoutResult(...)`.
2. Template yêu cầu transaction manager lấy giao dịch theo cấu hình propagation.
3. Callback chạy trong giao dịch. Các repository JPA tham gia cùng giao dịch đó khi dùng đúng transaction manager.
4. Nếu callback kết thúc bình thường và giao dịch chưa bị đánh dấu rollback-only, template yêu cầu commit.
5. Nếu callback ném ngoại lệ ra ngoài hoặc giao dịch đã bị đánh dấu rollback-only, template thực hiện rollback.

Propagation mặc định là `PROPAGATION_REQUIRED`: tham gia giao dịch đang tồn tại nếu có; nếu chưa có thì tạo giao dịch mới. Vì vậy, gọi template không đồng nghĩa lúc nào cũng tạo một giao dịch vật lý mới.

## 3. Khai báo TransactionTemplate thành bean

Có thể tạo template từ transaction manager do Spring quản lý và inject vào service:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class TransactionConfig {

    @Bean
    TransactionTemplate transactionTemplate(
            PlatformTransactionManager transactionManager) {

        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        // Có thể bỏ dòng này vì REQUIRED cũng là mặc định.
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);

        // Timeout tính bằng giây; chỉ có ý nghĩa khi bắt đầu giao dịch mới.
        template.setTimeout(30);

        return template;
    }
}
```

Trong ứng dụng chỉ có một transaction manager, Spring có thể inject trực tiếp bean `PlatformTransactionManager`. Nếu ứng dụng có nhiều datasource hoặc nhiều transaction manager, hãy dùng `@Qualifier` để chỉ rõ manager tương ứng với repository đang thao tác. Chọn nhầm manager có thể khiến thao tác JPA không tham gia giao dịch mà template đang điều khiển.

Template nên được cấu hình một lần rồi dùng lại. Các instance `TransactionTemplate` an toàn khi dùng đồng thời sau khi đã cấu hình; tránh thay đổi propagation, isolation hoặc timeout của bean dùng chung theo từng request. Nếu cần chính sách khác nhau, khai báo các bean template riêng.

## 4. Ví dụ: chuyển tiền giữa hai tài khoản

Giả sử hai tài khoản được lưu bằng entity `Account`. Khi chuyển tiền, thao tác trừ tiền và cộng tiền phải nằm trong cùng một giao dịch. Nếu tài khoản nguồn không đủ tiền hoặc tài khoản đích không tồn tại, toàn bộ thay đổi phải rollback.

Entity minh họa:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal balance;

    protected Account() {
    }

    public void debit(BigDecimal amount) {
        if (balance.compareTo(amount) < 0) {
            throw new InsufficientFundsException();
        }
        balance = balance.subtract(amount);
    }

    public void credit(BigDecimal amount) {
        balance = balance.add(amount);
    }
}
```

Ngoại lệ nghiệp vụ là unchecked exception:

```java
public class InsufficientFundsException extends RuntimeException {
    public InsufficientFundsException() {
        super("Số dư không đủ để thực hiện giao dịch");
    }
}
```

Repository:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository
        extends JpaRepository<Account, Long> {
}
```

Service sử dụng template:

```java
import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class TransferService {

    private final AccountRepository accounts;
    private final TransactionTemplate transactionTemplate;

    public TransferService(
            AccountRepository accounts,
            TransactionTemplate transactionTemplate) {
        this.accounts = accounts;
        this.transactionTemplate = transactionTemplate;
    }

    public TransferResult transfer(
            long fromId, long toId, BigDecimal amount) {

        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Số tiền chuyển phải lớn hơn 0");
        }
        if (fromId == toId) {
            throw new IllegalArgumentException(
                    "Tài khoản nguồn và đích phải khác nhau");
        }

        return transactionTemplate.execute(status -> {
            Account from = accounts.findById(fromId)
                    .orElseThrow(() ->
                            new IllegalArgumentException(
                                    "Không tìm thấy tài khoản nguồn"));

            Account to = accounts.findById(toId)
                    .orElseThrow(() ->
                            new IllegalArgumentException(
                                    "Không tìm thấy tài khoản đích"));

            from.debit(amount);
            to.credit(amount);

            // Hai entity đang được quản lý bởi persistence context.
            // JPA dirty checking sẽ ghi thay đổi khi flush/commit.
            return new TransferResult(fromId, toId, amount);
        });
    }

    public record TransferResult(
            long fromId, long toId, BigDecimal amount) {
    }
}
```

Khi callback chạy, hai entity lấy từ `findById` được quản lý trong persistence context của giao dịch hiện tại. Vì vậy, thay đổi `balance` được JPA dirty checking phát hiện và ghi xuống cơ sở dữ liệu khi flush hoặc commit; không bắt buộc gọi `save()` lại cho hai entity đang được quản lý.

Nếu `debit()` ném `InsufficientFundsException`, ngoại lệ thoát khỏi callback và template rollback. Thao tác cộng tiền cho tài khoản đích không được commit riêng lẻ. Tương tự, nếu không tìm thấy tài khoản đích sau khi đã đọc tài khoản nguồn, giao dịch cũng rollback.

Ví dụ giả định entity có constructor, getter hoặc các phương thức truy cập cần thiết cho phần còn lại của ứng dụng. Các class entity, repository, exception và record nên được đặt trong những file Java riêng theo cấu trúc project.

## 5. execute và executeWithoutResult

Dùng `execute(TransactionCallback<T>)` khi cần trả kết quả từ callback:

```java
String status = transactionTemplate.execute(txStatus -> {
    // Thực hiện các thao tác repository trong giao dịch.
    return "COMPLETED";
});
```

Kiểu trả về của `execute` là kiểu generic `T` của callback. Trong ví dụ chuyển tiền, callback trả về `TransferResult`.

Dùng `executeWithoutResult(Consumer<TransactionStatus>)` khi không cần trả kết quả:

```java
transactionTemplate.executeWithoutResult(txStatus -> {
    accounts.save(newAccount);
});
```

Cả hai cách đều để template quản lý vòng đời giao dịch. Không tự gọi commit, rollback hoặc đóng `EntityManager` bên trong callback.

## 6. Rollback chủ động bằng TransactionStatus

Khi một ngoại lệ thoát khỏi callback, template rollback giao dịch. Tuy nhiên, nếu callback bắt ngoại lệ rồi tiếp tục trả về bình thường, template có thể hiểu công việc đã thành công và commit các thay đổi trước đó.

Nếu đã bắt ngoại lệ nhưng vẫn muốn rollback, hãy đánh dấu giao dịch:

```java
transactionTemplate.executeWithoutResult(status -> {
    try {
        performBusinessOperations();
    } catch (BusinessRuleException ex) {
        status.setRollbackOnly();
        // Có thể ghi log hoặc chuẩn bị kết quả nghiệp vụ tại đây.
    }
});
```

`setRollbackOnly()` yêu cầu rollback khi kết thúc phạm vi giao dịch. Việc bắt ngoại lệ không tự động có nghĩa là rollback; hãy quyết định rõ callback cần thất bại hay cần đánh dấu rollback-only.

Nếu lỗi cần được thông báo cho tầng gọi, thường nên để ngoại lệ unchecked thoát khỏi callback thay vì nuốt ngoại lệ. Callback của `TransactionCallback` không khai báo checked exception; nếu cần chuyển một lỗi checked thành lỗi thoát khỏi callback, hãy bọc nó trong một unchecked exception phù hợp.

Khi template tham gia một giao dịch bên ngoài bằng `PROPAGATION_REQUIRED`, đánh dấu rollback-only có thể ảnh hưởng đến toàn bộ giao dịch bên ngoài. Nếu tầng gọi vẫn cố commit, Spring có thể ném `UnexpectedRollbackException` để thông báo rằng giao dịch đã bị đánh dấu rollback-only.

## 7. Cấu hình propagation, isolation, timeout và read-only

Các thiết lập được đặt trên template trước khi chạy callback:

```java
TransactionTemplate template =
        new TransactionTemplate(transactionManager);

template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);

template.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);

template.setTimeout(10);
template.setReadOnly(false);
```

Các lựa chọn propagation thường gặp:

| Propagation | Hành vi |
|---|---|
| `REQUIRED` | Tham gia giao dịch hiện tại; nếu chưa có thì tạo mới. Đây là mặc định. |
| `REQUIRES_NEW` | Tạm treo giao dịch hiện tại và tạo giao dịch độc lập mới. |
| `SUPPORTS` | Tham gia giao dịch nếu có; nếu không thì chạy không có giao dịch. |
| `MANDATORY` | Yêu cầu phải có giao dịch hiện tại; nếu không sẽ phát sinh lỗi. |
| `NOT_SUPPORTED` | Tạm treo giao dịch hiện tại và chạy ngoài giao dịch. |
| `NEVER` | Yêu cầu không có giao dịch hiện tại; nếu có sẽ phát sinh lỗi. |
| `NESTED` | Yêu cầu giao dịch lồng nhau, thường dựa trên savepoint và phụ thuộc transaction manager. |

Một số điểm cần hiểu khi cấu hình:

- `REQUIRED` phù hợp khi các thao tác phải cùng tham gia một giao dịch nghiệp vụ. Nếu template được gọi bên trong phương thức `@Transactional`, nó thường tham gia giao dịch đó.
- `REQUIRES_NEW` phù hợp khi một công việc cần commit hoặc rollback độc lập với giao dịch bên ngoài, ví dụ ghi một bản ghi audit riêng. Giao dịch bên ngoài bị tạm treo trong lúc giao dịch mới chạy.
- Isolation và timeout được áp dụng khi transaction manager bắt đầu giao dịch mới. Khi tham gia giao dịch đã tồn tại, thiết lập của giao dịch hiện tại thường là thiết lập có hiệu lực.
- `readOnly=true` là gợi ý cho transaction manager và persistence provider tối ưu thao tác đọc. Nó không phải cơ chế phân quyền và không bảo đảm mọi thao tác ghi đều bị chặn.
- `NESTED` phụ thuộc khả năng hỗ trợ savepoint của transaction manager. Với JPA, savepoint ở JDBC không đồng nghĩa có một persistence context lồng nhau; `JpaTransactionManager` không bật nested transaction mặc định.

Ví dụ cấu hình template chỉ đọc:

```java
TransactionTemplate readTemplate =
        new TransactionTemplate(transactionManager);
readTemplate.setReadOnly(true);

List<Account> result = readTemplate.execute(status ->
        accounts.findAll());
```

Nếu ứng dụng cần nhiều chính sách giao dịch, hãy tạo template riêng cho từng chính sách thay vì thay đổi cấu hình của một bean dùng chung trong lúc xử lý request.

## 8. Chia lô dữ liệu thành các giao dịch độc lập

Một trường hợp hữu ích là import dữ liệu theo từng lô. Nếu mỗi lô cần được commit độc lập, có thể cấu hình template với `REQUIRES_NEW`:

```java
TransactionTemplate batchTemplate =
        new TransactionTemplate(transactionManager);
batchTemplate.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);

for (List<ImportRow> batch : batches) {
    batchTemplate.executeWithoutResult(status ->
            importRepository.saveAll(batch));
}
```

Mỗi lần gọi tạo một giao dịch độc lập, miễn là transaction manager có thể bắt đầu giao dịch mới. Nếu một lô lỗi, lô đó rollback; các lô đã commit trước đó vẫn được giữ. Cách này giúp giới hạn thời gian giữ transaction và lượng dữ liệu trong persistence context.

Nếu vòng lặp đang nằm bên trong một giao dịch bên ngoài, `REQUIRES_NEW` sẽ tạm treo giao dịch ngoài trong mỗi lượt. Hãy cân nhắc thời gian giữ kết nối và cấu hình connection pool khi dùng nhiều giao dịch lồng theo kiểu này.

## 9. Lưu ý riêng khi dùng với JPA

**Dirty checking và flush:** Entity được tải trong giao dịch thường ở trạng thái managed. JPA phát hiện thay đổi và đồng bộ khi flush. Lệnh `save()` không thay thế ranh giới giao dịch; nó cũng không đồng nghĩa dữ liệu đã commit.

**Lỗi tại thời điểm flush/commit:** Một số lỗi ràng buộc dữ liệu chỉ xuất hiện khi Hibernate/JPA flush hoặc khi transaction manager commit. Nếu cần phát hiện lỗi SQL sớm bên trong callback, có thể gọi `EntityManager.flush()`. Nếu bắt lỗi persistence bên trong callback, hãy đánh dấu rollback-only trước khi kết thúc callback.

**Đúng transaction manager:** Repository và template phải làm việc với transaction manager quản lý đúng `EntityManagerFactory`. Ứng dụng nhiều datasource cần chỉ định rõ manager bằng qualifier.

**Luồng thực thi:** Giao dịch Spring thông thường gắn với thread hiện tại. Không giả định giao dịch tự truyền sang thread mới, `@Async` hoặc tác vụ chạy nền. Nếu công việc bất đồng bộ cần giao dịch, hãy mở giao dịch riêng trong luồng thực thi đó.

**Giữ giao dịch ngắn:** Tránh gọi HTTP, gửi email hoặc chờ thao tác bên ngoài trong callback nếu không cần thiết. Những thao tác này kéo dài thời gian giữ kết nối và khóa cơ sở dữ liệu. Nếu cần phát sự kiện sau commit, cân nhắc `@TransactionalEventListener(phase = AFTER_COMMIT)` hoặc cơ chế đồng bộ giao dịch phù hợp.

## 10. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Bắt ngoại lệ rồi không đánh dấu rollback-only | Các thay đổi trước lỗi có thể được commit. | Để ngoại lệ thoát khỏi callback hoặc gọi `status.setRollbackOnly()`. |
| Nghĩ rằng `REQUIRED` luôn tạo giao dịch mới | Callback có thể đang tham gia giao dịch bên ngoài. | Dùng `REQUIRES_NEW` khi thực sự cần giao dịch độc lập. |
| Dùng nhầm transaction manager | Repository JPA có thể không tham gia giao dịch của template. | Inject đúng `PlatformTransactionManager` bằng qualifier khi có nhiều manager. |
| Thay đổi cấu hình template dùng chung theo từng request | Các lần gọi đồng thời có thể dùng cấu hình không mong muốn. | Cấu hình bean một lần hoặc tạo template riêng theo chính sách. |
| Thực hiện I/O mạng lâu trong callback | Kết nối và khóa DB bị giữ lâu hơn cần thiết. | Giữ callback tập trung vào thao tác dữ liệu; xử lý việc bên ngoài sau commit. |
| Giả định giao dịch truyền sang thread khác | Công việc bất đồng bộ chạy ngoài giao dịch ban đầu. | Mở giao dịch riêng trong thread thực thi. |
| Cho rằng `readOnly=true` cấm ghi | Đây chỉ là gợi ý tối ưu, tùy manager/provider. | Dùng kiểm soát quyền và quy tắc nghiệp vụ riêng khi cần ngăn ghi. |

## 11. Chọn @Transactional hay TransactionTemplate?

| Tiêu chí | `@Transactional` | `TransactionTemplate` |
|---|---|---|
| Cách khai báo | Annotation trên class hoặc method | Callback trong mã Java |
| Ranh giới giao dịch | Thường ổn định theo method | Có thể đặt quanh một đoạn lệnh cụ thể |
| Giá trị trả về | Method trả về như bình thường | Callback trả về qua `execute` |
| Rollback thủ công | Có thể dùng cơ chế đánh dấu rollback phù hợp | Có trực tiếp `TransactionStatus.setRollbackOnly()` |
| Trường hợp phù hợp | Nghiệp vụ có ranh giới giao dịch rõ ràng | Ranh giới động, xử lý theo lô hoặc cần điều khiển trực tiếp |

Hai cách dùng chung cơ chế `PlatformTransactionManager` và có thể tham gia cùng một giao dịch theo propagation. Chọn cách diễn đạt rõ ràng nhất cho ranh giới nghiệp vụ; tránh lồng nhiều tầng giao dịch nếu không có lý do cụ thể.

## 12. Checklist trước khi đưa vào ứng dụng

- Chọn đúng `PlatformTransactionManager` quản lý datasource và persistence context của repository.
- Đặt toàn bộ thao tác cần nguyên tử bên trong cùng callback.
- Xác định rõ callback sẽ để ngoại lệ thoát ra hay bắt và đánh dấu rollback-only.
- Kiểm tra propagation khi template được gọi từ một phương thức đã có `@Transactional`.
- Chỉ đặt isolation, timeout và read-only khi có nhu cầu cụ thể.
- Giữ giao dịch ngắn và không dựa vào giao dịch của thread khác.
- Kiểm thử cả trường hợp thành công và trường hợp lỗi giữa chừng để xác nhận dữ liệu được commit hoặc rollback đúng như yêu cầu.

`TransactionTemplate` hữu ích khi ứng dụng cần điều khiển ranh giới giao dịch ngay trong luồng Java. Với Spring Data JPA, hãy để template và repository dùng đúng transaction manager; khi đó các thay đổi entity, thao tác repository và quyết định commit/rollback sẽ được phối hợp trong cùng một giao dịch.
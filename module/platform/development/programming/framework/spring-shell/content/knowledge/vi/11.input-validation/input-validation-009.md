# Kiểm tra trước tác dụng phụ để tránh trạng thái cập nhật một phần

## 1. Vì sao phải kiểm tra trước khi thay đổi dữ liệu?

Một command có thể thực hiện nhiều bước: đọc dữ liệu, kiểm tra điều kiện, cập nhật database, ghi tệp, gửi thông báo hoặc gọi một hệ thống bên ngoài. Nếu chương trình thay đổi trạng thái ngay khi bắt đầu rồi mới phát hiện đầu vào không hợp lệ, hệ thống có thể rơi vào trạng thái chỉ hoàn thành một phần.

Ví dụ, một command chuyển tiền giữa hai tài khoản cần kiểm tra:

- Mã tài khoản nguồn và đích có tồn tại không?
- Hai tài khoản có khác nhau không?
- Cả hai tài khoản có đang hoạt động không?
- Hai tài khoản có cùng loại tiền không?
- Số dư nguồn có đủ cho số tiền cần chuyển không?

Nếu chương trình trừ tiền tài khoản nguồn trước, sau đó mới phát hiện tài khoản đích bị khóa, dữ liệu có thể bị sai lệch nếu thao tác đầu tiên đã được lưu hoặc commit. Cách tổ chức an toàn là kiểm tra toàn bộ điều kiện cần thiết trước lần thay đổi đầu tiên, sau đó thực hiện các thay đổi trong một transaction phù hợp.

Với Spring Shell, validation trên tham số command giúp loại bỏ đầu vào sai ngay trước khi phương thức command được gọi. Những điều kiện phụ thuộc database hoặc trạng thái nghiệp vụ vẫn cần được kiểm tra trong service, tại nơi có thể kiểm soát transaction và các tác dụng phụ.

## 2. Xác định ranh giới giữa các bước

Một luồng xử lý command có thể chia thành các giai đoạn:

1. **Phân tích cú pháp và chuyển đổi kiểu:** xác định command, option, argument và chuyển token thành kiểu Java.
2. **Kiểm tra tham số:** kiểm tra trường bắt buộc, định dạng, giới hạn số học và các ràng buộc cục bộ.
3. **Kiểm tra nghiệp vụ:** đọc trạng thái cần thiết và xác nhận tất cả điều kiện trước khi ghi.
4. **Thực hiện thay đổi:** cập nhật các đối tượng liên quan trong transaction.
5. **Phát sinh tác dụng phụ bên ngoài:** gửi email, thông báo, gọi API hoặc xuất sự kiện sau khi dữ liệu đã commit.
6. **Trả kết quả:** chỉ báo thành công khi service đã hoàn thành thao tác theo hợp đồng.

~~~mermaid
flowchart TD
    A[Người dùng gọi command] --> B[Parse và chuyển đổi kiểu]
    B --> C[Bean Validation trên tham số]
    C --> D[Command gọi service]
    D --> E[Đọc trạng thái và kiểm tra nghiệp vụ]
    E --> F{Tất cả điều kiện hợp lệ?}
    F -->|Không| X[Trả lỗi, không ghi dữ liệu]
    F -->|Có| G[Bắt đầu thay đổi trong transaction]
    G --> H[Lưu tất cả thay đổi]
    H --> I[Commit transaction]
    I --> J[Tác dụng phụ sau commit]
    J --> K[Command trả kết quả]
~~~

Đây là mô hình tổ chức phổ biến. Tùy ứng dụng, transaction có thể bắt đầu trước khi đọc trạng thái để giữ khóa hoặc cung cấp isolation phù hợp. Điểm cốt lõi là không thực hiện mutation hay tác dụng phụ không thể đảo ngược trước khi hoàn tất các kiểm tra cần thiết.

## 3. Kiểm tra đầu vào ngay tại command

Spring Shell tích hợp Bean Validation. Các constraint trên tham số command được kiểm tra trước khi phương thức command thực thi. Nếu đầu vào không thỏa mãn, shell báo lỗi và không gọi phần thân phương thức.

Ví dụ command nhận yêu cầu chuyển tiền:

~~~java
package com.example.transfer;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class TransferCommands {

    private final TransferService transferService;

    public TransferCommands(TransferService transferService) {
        this.transferService = transferService;
    }

    @Command(
            name = "account transfer",
            description = "Chuyển tiền giữa hai tài khoản",
            group = "Account",
            help = "Ví dụ: account transfer --from=A001 --to=A002 --amount=125000.00")
    public String transfer(
            @Option(longName = "from", required = true,
                    description = "Mã tài khoản nguồn")
            @NotBlank String from,
            @Option(longName = "to", required = true,
                    description = "Mã tài khoản đích")
            @NotBlank String to,
            @Option(longName = "amount", required = true,
                    description = "Số tiền cần chuyển")
            @DecimalMin("0.01")
            @Digits(integer = 12, fraction = 2) BigDecimal amount) {

        TransferRequest request = new TransferRequest(from, to, amount);
        TransferReceipt receipt = transferService.transfer(request);

        return "Đã chuyển " + receipt.amount()
                + " từ " + receipt.sourceId()
                + " đến " + receipt.destinationId();
    }
}
~~~

Các constraint có trách nhiệm rõ ràng:

- `required = true` yêu cầu người dùng truyền option.
- `@NotBlank` từ chối mã tài khoản null, rỗng hoặc chỉ có khoảng trắng.
- `@DecimalMin("0.01")` yêu cầu số tiền tối thiểu là 0,01.
- `@Digits(integer = 12, fraction = 2)` giới hạn số chữ số phần nguyên và phần thập phân.

Các kiểm tra này không cần truy cập database nên có thể thực hiện trước khi gọi service. Để dùng constraint Jakarta trong ứng dụng Spring Boot, cần có implementation Bean Validation, thường được cung cấp qua `spring-boot-starter-validation`.

Ví dụ các lệnh sai bị chặn trước khi phương thức `transfer(...)` được gọi:

~~~text
account transfer --from=A001 --to=A002 --amount=0
account transfer --from="   " --to=A002 --amount=100
account transfer --from=A001 --to=A002 --amount=12.345
~~~

Tuy nhiên, command-level validation không thể xác nhận số dư hiện tại, trạng thái tài khoản hay quyền thao tác. Những điều kiện này thuộc service vì chúng phụ thuộc dữ liệu hệ thống và có thể thay đổi đồng thời.

## 4. Kiểm tra toàn bộ điều kiện nghiệp vụ trước lần ghi đầu tiên

Tạo request object để truyền một yêu cầu đã có cấu trúc rõ ràng:

~~~java
package com.example.transfer;

import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record TransferRequest(
        @NotBlank String sourceId,
        @NotBlank String destinationId,
        @NotNull
        @DecimalMin("0.01")
        @Digits(integer = 12, fraction = 2)
        BigDecimal amount) {
}
~~~

Service kiểm tra request và trạng thái hai tài khoản trước khi cập nhật:

~~~java
package com.example.transfer;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {

    private final AccountRepository accountRepository;
    private final Validator validator;
    private final ApplicationEventPublisher eventPublisher;

    public TransferService(
            AccountRepository accountRepository,
            Validator validator,
            ApplicationEventPublisher eventPublisher) {
        this.accountRepository = accountRepository;
        this.validator = validator;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public TransferReceipt transfer(TransferRequest request) {
        validateRequest(request);

        if (request.sourceId().equals(request.destinationId())) {
            throw new InvalidTransferException(
                    "Tài khoản nguồn và tài khoản đích phải khác nhau");
        }

        // Khóa theo thứ tự ID ổn định để giảm nguy cơ deadlock khi có
        // một giao dịch khác chuyển tiền theo chiều ngược lại.
        String firstId = request.sourceId().compareTo(request.destinationId()) < 0
                ? request.sourceId() : request.destinationId();
        String secondId = request.sourceId().equals(firstId)
                ? request.destinationId() : request.sourceId();

        Account first = accountRepository.findByIdForUpdate(firstId)
                .orElseThrow(() -> new AccountNotFoundException(firstId));
        Account second = accountRepository.findByIdForUpdate(secondId)
                .orElseThrow(() -> new AccountNotFoundException(secondId));

        Account source = request.sourceId().equals(firstId) ? first : second;
        Account destination = request.destinationId().equals(firstId) ? first : second;

        // Giai đoạn kiểm tra: chưa thay đổi bất kỳ tài khoản nào.
        validateAccountCanTransfer(source, request.amount());
        validateDestinationCanReceive(destination);
        validateCurrencyMatches(source, destination);

        // Chỉ bắt đầu mutation sau khi tất cả kiểm tra đã thành công.
        source.debit(request.amount());
        destination.credit(request.amount());

        accountRepository.saveAll(java.util.List.of(source, destination));

        eventPublisher.publishEvent(new TransferCompletedEvent(
                source.id(), destination.id(), request.amount()));

        return new TransferReceipt(
                source.id(), destination.id(), request.amount());
    }

    private void validateRequest(TransferRequest request) {
        Set<ConstraintViolation<TransferRequest>> violations =
                validator.validate(request);

        if (!violations.isEmpty()) {
            String message = violations.stream()
                    .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                    .sorted()
                    .collect(Collectors.joining("; "));
            throw new InvalidTransferException(message);
        }
    }

    private void validateAccountCanTransfer(Account source,
            java.math.BigDecimal amount) {
        if (!source.isActive()) {
            throw new InvalidTransferException("Tài khoản nguồn không hoạt động");
        }
        if (source.balance().compareTo(amount) < 0) {
            throw new InsufficientFundsException(source.id());
        }
    }

    private void validateDestinationCanReceive(Account destination) {
        if (!destination.isActive()) {
            throw new InvalidTransferException("Tài khoản đích không hoạt động");
        }
    }

    private void validateCurrencyMatches(Account source, Account destination) {
        if (!source.currency().equals(destination.currency())) {
            throw new InvalidTransferException(
                    "Hai tài khoản phải sử dụng cùng loại tiền");
        }
    }
}
~~~

`Account`, `AccountRepository`, `TransferReceipt`, `TransferCompletedEvent` và các exception miền là kiểu của ứng dụng ví dụ, cần được định nghĩa trong project. Repository phải triển khai `findByIdForUpdate(...)` bằng cơ chế khóa phù hợp với database đang dùng.

Các exception miền như `InvalidTransferException`, `AccountNotFoundException` và `InsufficientFundsException` nên kế thừa `RuntimeException` nếu muốn Spring áp dụng quy tắc rollback mặc định. Nếu chúng là checked exception, cần khai báo `rollbackFor` tương ứng trên transaction.

`findByIdForUpdate(...)` là tên phương thức repository minh họa cho việc đọc tài khoản kèm khóa phù hợp. Với JPA, có thể triển khai bằng `@Lock(LockModeType.PESSIMISTIC_WRITE)` và một truy vấn lấy tài khoản theo ID. Nếu hệ thống dùng optimistic locking, có thể dùng `@Version` và xử lý xung đột khi commit. Ví dụ sắp xếp ID trước khi lấy khóa để giảm nguy cơ deadlock khi hai giao dịch chuyển tiền theo hai chiều ngược nhau.

Trình tự rất quan trọng: cả tài khoản nguồn lẫn đích được đọc, sau đó mọi điều kiện được kiểm tra. Chỉ khi không còn lỗi mới gọi `debit`, `credit` và lưu dữ liệu. Nếu tài khoản đích không tồn tại, không hoạt động hoặc sai loại tiền, tài khoản nguồn chưa bị trừ.

Việc gọi `validator.validate(request)` ở service giúp bảo vệ nghiệp vụ khi service được gọi từ nơi khác ngoài CLI, chẳng hạn REST API, tác vụ nền hoặc một command khác. Không nên giả định mọi caller đều đã đi qua Bean Validation của Spring Shell.

## 5. Transaction bảo vệ tính nguyên tử của thay đổi dữ liệu

Kiểm tra trước khi ghi giúp tránh nhiều lỗi có thể phát hiện sớm. Nhưng vẫn có thể xảy ra lỗi trong lúc lưu, chẳng hạn database mất kết nối, vi phạm constraint hoặc một cập nhật thất bại. Với nhiều thay đổi thuộc cùng một cơ sở dữ liệu, cần đặt thao tác trong transaction để các thay đổi được commit cùng nhau hoặc rollback khi có lỗi.

`@Transactional` thường được đặt ở service method:

~~~java
@Transactional
public TransferReceipt transfer(TransferRequest request) {
    // Đọc, kiểm tra, thay đổi và lưu các tài khoản
}
~~~

Khi có một `RuntimeException` hoặc `Error` thoát khỏi phương thức trong transaction, Spring mặc định đánh dấu transaction rollback. Exception checked không kích hoạt rollback theo mặc định; nếu nghiệp vụ sử dụng checked exception, hãy cấu hình `rollbackFor` phù hợp hoặc chuyển sang exception runtime theo quy ước của ứng dụng.

Transaction cần được kích hoạt trong ứng dụng và lời gọi phải đi qua proxy transaction của Spring. Đặt `@Transactional` lên một phương thức rồi tự gọi phương thức đó từ một phương thức khác trong cùng object (self-invocation) không kích hoạt proxy ở chế độ mặc định.

Transaction bảo vệ tính nguyên tử đối với các tài nguyên tham gia cùng transaction manager, thường là các thao tác database. Nó không tự động rollback email đã gửi, tệp đã ghi, HTTP request đã gửi hoặc message đã chuyển tới một hệ thống không tham gia transaction.

### Phân biệt pre-validation và rollback

| Cơ chế | Bảo vệ điều gì? | Khi cần dùng |
|---|---|---|
| Kiểm tra trước mutation | Ngăn thay đổi khi đầu vào hoặc trạng thái hiện tại đã không hợp lệ. | Trước lần ghi đầu tiên, nhất là khi command có nhiều bước. |
| Transaction | Đảm bảo các thay đổi thuộc transaction cùng commit hoặc rollback. | Khi một nghiệp vụ cập nhật nhiều bản ghi hoặc bảng. |
| Lock hoặc optimistic version | Ngăn hai luồng đồng thời dựa trên cùng trạng thái cũ để ghi đè lẫn nhau. | Khi điều kiện hợp lệ có thể thay đổi giữa lúc đọc và ghi. |
| Outbox hoặc cơ chế phối hợp hệ thống | Đảm bảo việc phát thông báo hoặc đồng bộ bên ngoài có thể được thử lại đáng tin cậy. | Khi nghiệp vụ kết hợp database và message broker/API/email. |

Các cơ chế này bổ sung cho nhau. Transaction không thay thế việc kiểm tra nghiệp vụ, còn pre-validation không thay thế transaction khi có nhiều thay đổi cần tính nguyên tử.

## 6. Tránh tác dụng phụ trước khi transaction commit

Giả sử service cập nhật hai tài khoản rồi gửi email ngay trong transaction:

~~~java
@Transactional
public void transfer(...) {
    source.debit(amount);
    destination.credit(amount);
    accountRepository.saveAll(...);

    notificationService.sendTransferEmail(...); // Không an toàn
}
~~~

Nếu email đã được gửi nhưng transaction database thất bại sau đó, người nhận nhận thông báo về một giao dịch chưa được commit. Rollback database không thể thu hồi email.

Một lựa chọn là phát application event trong transaction và xử lý sau commit bằng `@TransactionalEventListener`:

~~~java
public record TransferCompletedEvent(
        String sourceId,
        String destinationId,
        java.math.BigDecimal amount) {
}
~~~

Trong service, publish event sau khi đã chuẩn bị các thay đổi:

~~~java
eventPublisher.publishEvent(new TransferCompletedEvent(
        source.id(), destination.id(), request.amount()));
~~~

Listener chỉ xử lý sau khi transaction commit thành công:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class TransferNotificationListener {

    private final NotificationService notificationService;

    public TransferNotificationListener(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onTransferCompleted(TransferCompletedEvent event) {
        notificationService.sendTransferNotification(event);
    }
}
~~~

`AFTER_COMMIT` là phase mặc định của `@TransactionalEventListener`. Nếu transaction rollback, listener này không chạy. Nhờ đó, thông báo không được gửi cho một giao dịch chưa commit.

Listener giao dịch thường chạy đồng bộ nếu không cấu hình thực thi bất đồng bộ. Nếu việc gửi thông báo ném exception, exception có thể đi ngược về caller sau khi database đã commit; caller nhìn thấy lỗi dù giao dịch đã hoàn tất. Vì vậy, listener cần bắt và ghi nhận lỗi để retry, hoặc ghi công việc vào outbox. Không để lỗi thông báo làm người gọi hiểu nhầm rằng giao dịch database đã rollback.

Tuy nhiên, listener chạy sau commit không tạo ra bảo đảm giao nhận bền vững. Nếu tiến trình dừng sau khi database commit nhưng trước khi listener gửi thông báo, event trong bộ nhớ có thể bị mất. Với yêu cầu giao nhận tin cậy, hãy ghi một bản ghi **transactional outbox** cùng transaction nghiệp vụ; một worker riêng đọc outbox, gửi thông điệp và đánh dấu đã xử lý. Worker cần hỗ trợ retry và xử lý idempotent để tránh gửi trùng khi nhận lại cùng một sự kiện.

## 7. Kiểm tra toàn bộ batch trước khi cập nhật

Nguyên tắc tương tự áp dụng cho command nhập hoặc cập nhật nhiều bản ghi. Không nên xử lý tuần tự theo kiểu “đọc một dòng, kiểm tra, lưu ngay” nếu yêu cầu là cả batch phải hợp lệ mới được cập nhật.

Ví dụ một file nhập có ba dòng:

~~~text
SKU-001,10
SKU-002,5
SKU-003,-2
~~~

Nếu chương trình lưu SKU-001 và SKU-002 rồi mới phát hiện SKU-003 có số lượng âm, dữ liệu đã bị cập nhật một phần. Hãy tách thành hai lượt:

1. Đọc và parse toàn bộ file thành danh sách request.
2. Kiểm tra từng dòng: SKU không rỗng, số lượng hợp lệ, không có dòng trùng ngoài chính sách, sản phẩm tồn tại và có thể cập nhật.
3. Nếu có lỗi, trả danh sách lỗi theo số dòng và dừng trước lần ghi đầu tiên.
4. Nếu tất cả hợp lệ, áp dụng các thay đổi trong một transaction.

Ví dụ cấu trúc:

~~~java
@Transactional
public ImportResult importStock(List<StockChange> changes) {
    List<ValidatedStockChange> plan = preflight(changes);

    // preflight hoàn tất cho toàn bộ danh sách trước khi thay đổi dữ liệu.
    for (ValidatedStockChange change : plan) {
        change.product().adjustStock(change.quantity());
    }

    productRepository.saveAll(
            plan.stream().map(ValidatedStockChange::product).toList());

    return new ImportResult(plan.size());
}
~~~

`preflight(...)` cần hoàn tất các kiểm tra cấu trúc, trùng lặp và trạng thái sản phẩm, sau đó trả về kế hoạch cập nhật đã được xác thực. Nếu số lượng dữ liệu lớn đến mức không thể giữ một transaction dài, cần thiết kế chính sách batch rõ ràng: chia lô, lưu trạng thái từng lô, hỗ trợ resume và báo cáo chính xác các dòng thành công/thất bại. Không nên tuyên bố “all-or-nothing” nếu mỗi lô được commit độc lập.

## 8. Xử lý lỗi và trả kết quả cho người dùng

Command chỉ nên trả thông báo thành công sau khi service method hoàn tất và transaction đã commit thông qua proxy. Không in “đã cập nhật” trước khi thao tác lưu hoàn tất.

Các lỗi nên được phân biệt:

| Lỗi | Ví dụ thông báo | Kết quả mong đợi |
|---|---|---|
| Đầu vào sai | `--amount phải lớn hơn 0` | Không gọi service nếu lỗi được phát hiện ở tham số command. |
| Quy tắc nghiệp vụ không hợp lệ | `Số dư tài khoản A001 không đủ` | Không thực hiện mutation. |
| Tài nguyên không tồn tại | `Không tìm thấy tài khoản A002` | Không thực hiện mutation. |
| Xung đột đồng thời | `Tài khoản vừa được cập nhật bởi giao dịch khác; hãy thử lại` | Rollback và yêu cầu caller retry theo chính sách. |
| Lỗi lưu dữ liệu | `Không thể hoàn tất giao dịch` | Transaction rollback nếu exception kích hoạt rollback. |
| Lỗi gửi thông báo sau commit | `Giao dịch đã hoàn tất; thông báo đang chờ gửi lại` | Không đảo ngược giao dịch đã commit; retry notification/outbox. |

Có thể dùng `ExitStatusExceptionMapper` để ánh xạ exception nghiệp vụ thành trạng thái phù hợp cho shell. Cần nhớ mapper của command không thể biến một transaction đã commit thành rollback; việc xử lý lỗi sau commit phải có cơ chế riêng.

Với command chạy từ script, hãy duy trì mã thoát khác `0` khi nghiệp vụ thất bại. Nếu giao dịch đã commit nhưng thông báo đang chờ retry, thông điệp và mã thoát cần phản ánh đúng trạng thái thực tế; đừng báo toàn bộ giao dịch thất bại nếu chỉ có phần thông báo bị chậm.

## 9. Kiểm thử để chứng minh không có cập nhật một phần

Một bài kiểm thử chỉ xác nhận thông báo lỗi chưa đủ. Cần kiểm tra trạng thái dữ liệu và xác nhận các collaborator không được gọi khi validation thất bại.

### Kiểm thử command-level validation

Với Spring Shell test support (`@ShellTest`, `ShellTestClient` và `ShellAssertions`), gửi command có số tiền không hợp lệ và xác nhận:

- Shell hiển thị lỗi constraint.
- `TransferService.transfer(...)` không được gọi.
- Không có notification hoặc repository write nào được thực hiện.

### Kiểm thử service preflight

Ví dụ dùng Mockito để xác nhận tài khoản nguồn không bị lưu khi tài khoản đích không hợp lệ:

~~~java
@Test
void shouldNotSaveAnyAccountWhenDestinationIsInactive() {
    Account source = activeAccount("A001", "VND", "500000");
    Account destination = inactiveAccount("A002", "VND", "100000");

    when(accountRepository.findByIdForUpdate("A001"))
            .thenReturn(Optional.of(source));
    when(accountRepository.findByIdForUpdate("A002"))
            .thenReturn(Optional.of(destination));

    assertThatThrownBy(() -> transferService.transfer(
            new TransferRequest("A001", "A002", new BigDecimal("100000"))))
            .isInstanceOf(InvalidTransferException.class);

    assertThat(source.balance()).isEqualByComparingTo("500000");
    verify(accountRepository, never()).saveAll(anyList());
    verifyNoInteractions(eventPublisher);
}
~~~

Tên factory `activeAccount(...)`, `inactiveAccount(...)` và fixture có thể được định nghĩa trong test. `eventPublisher` là mock được inject vào service. Kiểm thử đơn vị này xác nhận preflight chặn trước thao tác lưu và trước khi publish event.

### Kiểm thử rollback bằng database thật hoặc test container

Để xác nhận transaction rollback, cần một kiểm thử tích hợp có transaction manager và database thực tế tương ứng. Thiết lập dữ liệu ban đầu, ép thao tác lưu hoặc một bước nghiệp vụ sau lần mutation đầu tiên phát sinh runtime exception, rồi đọc lại dữ liệu trong transaction mới để xác nhận cả hai tài khoản giữ số dư ban đầu.

Không nên chỉ kiểm tra object Java trong bộ nhớ: JPA persistence context có thể vẫn giữ trạng thái object đã thay đổi dù transaction đã rollback. Hãy đọc lại từ database sau khi transaction kết thúc để kiểm tra kết quả bền vững.

### Kiểm thử event sau commit

Kiểm thử listener để xác nhận:

- Event được publish trong transaction nhưng listener `AFTER_COMMIT` chỉ chạy sau commit thành công.
- Khi transaction rollback, notification service không được gọi.
- Nếu notification thất bại sau commit, dữ liệu nghiệp vụ vẫn ở trạng thái đã commit và cơ chế retry/outbox ghi nhận được công việc còn lại.

## 10. Danh sách kiểm tra trước khi phát hành command có tác dụng phụ

- Các constraint cục bộ được khai báo trên tham số command.
- Service kiểm tra lại request ở ranh giới nghiệp vụ để bảo vệ mọi caller.
- Tất cả điều kiện phụ thuộc trạng thái được xác nhận trước mutation đầu tiên.
- Những cập nhật cần tính nguyên tử nằm trong cùng transaction.
- Có lock, optimistic version hoặc constraint phù hợp khi dữ liệu có thể thay đổi đồng thời.
- Không gửi email, gọi API hoặc ghi file không thể đảo ngược trước commit.
- Sự kiện sau commit có retry; dùng outbox nếu cần giao nhận bền vững.
- Command chỉ báo thành công sau khi service hoàn tất.
- Kiểm thử xác nhận không có write khi preflight thất bại và rollback khi lỗi giữa transaction.

## Kết luận

Để tránh trạng thái cập nhật một phần, hãy kiểm tra đầu vào ngay ở command, kiểm tra toàn bộ quy tắc nghiệp vụ trong service trước mutation đầu tiên, rồi thực hiện các thay đổi liên quan trong transaction. Transaction bảo vệ các thao tác database cùng phạm vi, còn tác dụng phụ bên ngoài cần được trì hoãn đến sau commit hoặc phối hợp bằng transactional outbox. Kết hợp preflight, transaction, concurrency control và kiểm thử trạng thái cuối cùng giúp command Spring Shell an toàn hơn khi thực hiện các thao tác có ảnh hưởng đến dữ liệu.

## Tài liệu tham khảo

- [Spring Shell 4.x – Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html)
- [Spring Framework – Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework – Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)

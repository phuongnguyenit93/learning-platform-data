# Tách kiểm tra quy tắc nghiệp vụ khỏi kiểm tra cú pháp đầu vào

Trong kiến trúc phân tầng, dữ liệu đi vào hệ thống thường phải qua hai nhóm kiểm tra có mục đích khác nhau. **Kiểm tra cú pháp và cấu trúc đầu vào** xác định dữ liệu có được gửi đúng định dạng mà giao diện công bố hay không. **Kiểm tra quy tắc nghiệp vụ** xác định yêu cầu đó có hợp lệ theo trạng thái, chính sách và bất biến của hoạt động kinh doanh hay không.

Phân biệt hai nhóm này giúp đặt mã vào đúng tầng. Tầng trình bày xử lý việc phân tích request, kiểu dữ liệu, trường bắt buộc và định dạng giao thức. Tầng ứng dụng điều phối ca sử dụng và những kiểm tra cần ngữ cảnh của ca sử dụng. Mô hình nghiệp vụ bảo vệ các bất biến và quy tắc phải đúng dù hành động được gọi từ REST API, CLI, message consumer hay tác vụ nền. Nhờ vậy, một request hợp lệ về mặt JSON vẫn phải tuân thủ quy tắc nghiệp vụ, và các quy tắc quan trọng không bị bỏ qua khi hệ thống có thêm kênh giao tiếp.

## 1. Hai câu hỏi kiểm tra khác nhau

Hãy xem một API chuyển tiền giữa hai tài khoản. Người gọi gửi JSON có mã tài khoản nguồn, mã tài khoản nhận và số tiền. Có hai câu hỏi cần trả lời:

- **Dữ liệu có đúng hợp đồng giao tiếp không?** JSON có phân tích được không? Mã tài khoản có đúng định dạng UUID không? Trường số tiền có phải là số và có nằm trong giới hạn biểu diễn mà API chấp nhận không?
- **Giao dịch có được phép theo nghiệp vụ không?** Tài khoản nguồn có đang hoạt động không? Tài khoản có đủ số dư không? Hai tài khoản có được phép chuyển tiền cho nhau không? Giao dịch có vượt hạn mức không?

Một JSON hoàn toàn hợp lệ vẫn có thể yêu cầu chuyển tiền từ tài khoản bị khóa hoặc tài khoản không đủ số dư. Ngược lại, một yêu cầu có ý nghĩa nghiệp vụ hợp lệ cũng không thể được xử lý nếu nội dung gửi lên sai cú pháp hoặc thiếu trường bắt buộc.

| Tiêu chí | Kiểm tra cú pháp/cấu trúc đầu vào | Kiểm tra quy tắc nghiệp vụ |
|---|---|---|
| Câu hỏi | Dữ liệu có đúng định dạng và hợp đồng của kênh không? | Hành động có hợp lệ trong ngữ cảnh nghiệp vụ hiện tại không? |
| Ví dụ | JSON hợp lệ, UUID phân tích được, trường bắt buộc có mặt, số tiền có định dạng thập phân phù hợp. | Tài khoản đang hoạt động, đủ số dư, người dùng được phép chuyển tiền, giao dịch không vượt hạn mức. |
| Nơi thực hiện thường gặp | Adapter ở tầng trình bày: controller, parser, request DTO validator. | Tầng ứng dụng, domain model hoặc domain policy tùy nơi sở hữu quy tắc. |
| Phụ thuộc vào | Giao thức, cấu trúc request và hợp đồng đầu vào. | Trạng thái nghiệp vụ, chính sách, dữ liệu liên quan và ngữ cảnh ca sử dụng. |
| Phạm vi tái sử dụng | Có thể khác nhau giữa REST, CLI và message. | Phải được bảo vệ ở mọi đường gọi có thể thực hiện hành động đó. |

Không nên hiểu “kiểm tra đầu vào” là mọi điều kiện đều thuộc controller. Một điều kiện có thể được kiểm tra sớm ở biên để phản hồi thân thiện, nhưng nếu nó là bất biến nghiệp vụ thì domain vẫn phải bảo vệ điều kiện đó. Ví dụ, số tiền chuyển phải lớn hơn 0 có thể được kiểm tra bằng annotation trên request, đồng thời được bảo vệ trong kiểu giá trị nghiệp vụ để một adapter khác không thể tạo khoản chuyển có số tiền bằng 0 hoặc âm.

## 2. Đặt từng nhóm kiểm tra vào đúng tầng

### Tầng trình bày: bảo vệ hợp đồng giao tiếp

Tầng trình bày nhận dữ liệu từ một kênh cụ thể và chuyển nó sang kiểu mà ứng dụng hiểu. Với REST API, các việc phù hợp ở đây gồm:

- Phân tích JSON, query parameter, path variable và header.
- Phát hiện JSON sai cú pháp hoặc giá trị không thể chuyển sang kiểu đích.
- Kiểm tra trường bắt buộc, độ dài chuỗi, định dạng email, định dạng ngày hoặc giới hạn biểu diễn của request.
- Chuyển request DTO thành command của ca sử dụng.
- Chuyển lỗi đầu vào thành phản hồi theo giao thức, chẳng hạn HTTP 400.

Các kiểm tra này có thể dùng Bean Validation trong Spring. Chúng giúp từ chối dữ liệu sai ngay tại biên và cung cấp thông báo lỗi dễ hiểu. Tuy nhiên, request DTO chỉ đại diện cho hợp đồng của kênh đó. Một CLI hoặc message consumer có thể có kiểu đầu vào khác và không đi qua cùng controller.

### Tầng ứng dụng: kiểm tra cần ngữ cảnh ca sử dụng

Tầng ứng dụng điều phối hành động. Một số điều kiện chỉ có thể đánh giá sau khi tải dữ liệu hoặc xác định người đang thực hiện hành động. Ví dụ:

- Tài khoản nguồn có thuộc khách hàng đang đăng nhập không?
- Người gọi có quyền thực hiện ca sử dụng chuyển tiền không?
- Tài khoản nhận có tồn tại trong hệ thống không?
- Hạn mức chuyển tiền áp dụng cho loại giao dịch và khách hàng hiện tại là bao nhiêu?

Tùy bản chất, quy tắc có thể được thực thi trong domain hoặc một domain policy/service. Tầng ứng dụng chịu trách nhiệm cung cấp dữ liệu và ngữ cảnh cần thiết, gọi đúng quy tắc, điều phối kết quả và quản lý ranh giới giao dịch. Nó không nên chỉ gom mọi điều kiện vào một lớp service lớn.

### Tầng nghiệp vụ: bảo vệ quy tắc và bất biến

Domain model hoặc domain policy giữ những điều kiện phải luôn đúng đối với khái niệm nghiệp vụ. Ví dụ:

- Số tiền của một giao dịch chuyển tiền phải dương.
- Tài khoản bị khóa không được ghi nợ.
- Tài khoản không được chi vượt số dư nếu sản phẩm không cho phép thấu chi.
- Một đơn hàng đã giao không thể quay lại trạng thái nháp.
- Một phiếu hoàn tiền không được vượt quá số tiền đã thanh toán còn đủ điều kiện hoàn.

Quy tắc thuộc domain không được phụ thuộc vào HttpServletRequest, ResponseEntity, cấu trúc JSON hoặc annotation của controller. Nó cần được thực thi dù lệnh đến từ REST API, CLI, message consumer hoặc một bài kiểm thử trực tiếp gọi mô hình nghiệp vụ.

### Tầng dữ liệu/hạ tầng: bảo vệ tính nhất quán lưu trữ

Cơ sở dữ liệu có thể có các ràng buộc NOT NULL, UNIQUE, CHECK, khóa ngoại và cơ chế khóa/phiên bản. Những ràng buộc này bảo vệ dữ liệu khi có nhiều tiến trình hoặc đường ghi cùng hoạt động. Chúng là lớp bảo vệ bổ sung; không nên thay thế toàn bộ việc kiểm tra nghiệp vụ trong ứng dụng/domain.

Ví dụ, constraint CHECK (amount > 0) có thể ngăn lưu giao dịch có số tiền không dương. Nhưng thông báo lỗi thân thiện, quyết định tài khoản nào được phép chuyển tiền và cách phản hồi cho từng kênh vẫn cần được xử lý ở các tầng bên trong và adapter tương ứng.

## 3. Ví dụ với Java và Spring: API chuyển tiền

Giả sử API nhận request như sau:

~~~json
{
  "sourceAccountId": "6e9e7e1b-58d5-4a4c-aef2-6e5d5bb6a9e2",
  "targetAccountId": "d10a4b5a-93c5-4e1a-9d28-2ef71c2c8c10",
  "amount": 500000,
  "description": "Thanh toán hóa đơn"
}
~~~

JSON này có cú pháp hợp lệ và các trường có thể chuyển sang kiểu dữ liệu tương ứng. Điều đó chưa chứng minh giao dịch được phép. Tài khoản nguồn có thể đã bị đóng, số dư có thể không đủ, hoặc khách hàng có thể đã chạm hạn mức trong ngày.

### Kiểm tra cấu trúc request tại biên

Một request DTO có thể dùng Bean Validation để kiểm tra những điều kiện thuộc hợp đồng HTTP:

~~~java
public record TransferRequest(
    @NotNull UUID sourceAccountId,
    @NotNull UUID targetAccountId,
    @NotNull
    @DecimalMin("0.01")
    @Digits(integer = 12, fraction = 2)
    BigDecimal amount,
    @Size(max = 140) String description
) {}
~~~

Các annotation trên kiểm tra trường có mặt, số tiền nằm trong miền biểu diễn mà API công bố và mô tả không quá dài. Spring MVC kích hoạt kiểm tra khi tham số được đánh dấu @Valid:

~~~java
@RestController
@RequestMapping("/transfers")
class TransferController {
    private final TransferUseCase transferUseCase;

    TransferController(TransferUseCase transferUseCase) {
        this.transferUseCase = transferUseCase;
    }

    @PostMapping
    ResponseEntity<TransferResponse> transfer(
            @Valid @RequestBody TransferRequest request) {
        TransferCommand command = new TransferCommand(
            request.sourceAccountId(),
            request.targetAccountId(),
            request.amount(),
            request.description()
        );

        TransferResult result = transferUseCase.handle(command);

        return ResponseEntity.ok(
            new TransferResponse(result.transferId(), result.status()));
    }
}
~~~

Nếu JSON sai cú pháp, chẳng hạn thiếu dấu ngoặc hoặc gửi chuỗi không thể chuyển thành UUID, Spring không thể tạo request DTO và quá trình binding thất bại. Nếu JSON phân tích được nhưng thiếu trường bắt buộc hoặc số tiền vượt giới hạn biểu diễn, Bean Validation báo lỗi. Đây là các lỗi của hợp đồng HTTP, chưa cần gọi domain để quyết định tài khoản có được phép chuyển tiền hay không.

### Điều phối ca sử dụng ở tầng ứng dụng

Tầng ứng dụng tải các tài khoản, áp dụng những kiểm tra cần ngữ cảnh, gọi hành vi nghiệp vụ và lưu kết quả:

~~~java
public record TransferCommand(
    UUID sourceAccountId,
    UUID targetAccountId,
    BigDecimal amount,
    String description
) {}

@Service
class TransferService implements TransferUseCase {
    private final AccountRepository accounts;
    private final TransferRepository transfers;

    TransferService(
            AccountRepository accounts,
            TransferRepository transfers) {
        this.accounts = accounts;
        this.transfers = transfers;
    }

    @Override
    @Transactional
    public TransferResult handle(TransferCommand command) {
        Account source = accounts.findById(command.sourceAccountId())
            .orElseThrow(AccountNotFoundException::new);

        Account target = accounts.findById(command.targetAccountId())
            .orElseThrow(AccountNotFoundException::new);

        TransferAmount amount = new TransferAmount(command.amount());

        source.transferTo(target, amount);

        Transfer transfer = Transfer.record(
            source.id(), target.id(), amount, command.description());

        transfers.save(transfer);
        accounts.save(source);
        accounts.save(target);

        return new TransferResult(
            transfer.id().value(), transfer.status().name());
    }
}
~~~

Đây là ví dụ minh họa ranh giới trách nhiệm, các kiểu repository và đối tượng kết quả được lược giản. Trong hệ thống thật, việc kiểm tra người thực hiện có quyền sử dụng tài khoản nguồn có thể được thực hiện tại ca sử dụng hoặc một policy phù hợp. Quy tắc hạn mức có thể cần dữ liệu lịch sử và chính sách của khách hàng; ứng dụng cung cấp dữ liệu đó cho policy, sau đó điều phối kết quả trong giao dịch.

### Bảo vệ quy tắc trong domain

Kiểu giá trị TransferAmount bảo vệ bất biến số tiền chuyển phải dương:

~~~java
public record TransferAmount(BigDecimal value) {
    public TransferAmount {
        Objects.requireNonNull(value, "value");
        if (value.signum() <= 0) {
            throw new InvalidTransferAmountException();
        }
    }
}
~~~

Đối tượng tài khoản bảo vệ điều kiện trạng thái và số dư:

~~~java
public class Account {
    private final AccountId id;
    private AccountStatus status;
    private BigDecimal balance;

    public void transferTo(Account recipient, TransferAmount amount) {
        if (status != AccountStatus.ACTIVE) {
            throw new AccountNotActiveException();
        }
        if (recipient.status != AccountStatus.ACTIVE) {
            throw new RecipientAccountNotActiveException();
        }
        if (id.equals(recipient.id)) {
            throw new SameSourceAndTargetAccountException();
        }
        if (balance.compareTo(amount.value()) < 0) {
            throw new InsufficientFundsException();
        }

        balance = balance.subtract(amount.value());
        recipient.balance = recipient.balance.add(amount.value());
    }
}
~~~

Domain không biết yêu cầu đến từ HTTP hay message. Nó chỉ biết tài khoản, trạng thái, số dư và số tiền chuyển. Vì vậy, nếu ngày mai có thêm một tác vụ nền chuyển tiền theo lịch, tác vụ đó vẫn phải tuân thủ cùng các quy tắc khi gọi hành vi domain.

Ví dụ trên giả định số dư không được âm và đã lược bỏ chi tiết tiền tệ, làm tròn, khóa đồng thời và ghi sổ kép. Hệ thống tài chính thực tế cần mô hình tiền tệ có đơn vị tiền rõ ràng, kiểm soát giao dịch đồng thời và cơ chế ghi nhận bút toán phù hợp. Những chi tiết đó không làm thay đổi nguyên tắc phân tầng: quy tắc nghiệp vụ phải được bảo vệ trong mô hình/policy, còn cách nhận và trình bày dữ liệu thuộc adapter.

## 4. Khi nào một điều kiện cần kiểm tra ở cả biên và domain?

Có những điều kiện xuất hiện ở nhiều nơi vì mỗi nơi bảo vệ một hợp đồng khác nhau. Số tiền phải lớn hơn 0 là ví dụ điển hình:

- DTO dùng @DecimalMin("0.01") để API trả lỗi sớm, rõ ràng nếu người gọi gửi số tiền bằng 0 hoặc âm.
- TransferAmount kiểm tra lại điều kiện dương để bảo vệ bất biến của domain khi command đến từ CLI, message consumer hoặc mã nội bộ.
- Cơ sở dữ liệu có thể có constraint để ngăn dữ liệu sai được lưu do lỗi lập trình hoặc đường ghi ngoài dự kiến.

Đây không phải là lý do để sao chép toàn bộ quy tắc nghiệp vụ vào controller. Kiểm tra ở biên nên tập trung vào định dạng, cấu trúc và giới hạn của hợp đồng giao tiếp. Domain vẫn là nơi quyết định cuối cùng đối với bất biến mà nó sở hữu.

Một số điều kiện có vẻ giống nhau nhưng có ý nghĩa khác nhau:

| Điều kiện | Kiểm tra ở biên | Kiểm tra bên trong |
|---|---|---|
| Mã tài khoản phải là UUID hợp lệ | Có, để parser chuyển được thành kiểu UUID. | Không cần kiểm tra lại cú pháp UUID nếu kiểu AccountId đã được tạo hợp lệ; nhưng phải xác định tài khoản có tồn tại hay không. |
| Số tiền phải lớn hơn 0 | Có thể kiểm tra để phản hồi sớm theo hợp đồng API. | Domain bắt buộc bảo vệ vì đây là bất biến của giao dịch. |
| Mô tả không quá 140 ký tự | Có, nếu giới hạn là hợp đồng của request. | Chỉ cần thêm giới hạn trong domain nếu đó là quy tắc nghiệp vụ phải đúng với mọi nguồn dữ liệu. |
| Tài khoản phải đang hoạt động | Không thể kết luận chỉ từ cú pháp request. | Domain kiểm tra trạng thái tại thời điểm thực hiện hành động. |
| Người dùng có quyền chuyển từ tài khoản nguồn | Có thể xác thực danh tính tại biên. | Ca sử dụng/policy kiểm tra quyền trên tài nguyên và hành động cụ thể. |
| Số dư đủ để chuyển | Không thể xác minh đáng tin cậy chỉ từ dữ liệu request. | Domain kiểm tra trên trạng thái tài khoản thích hợp, có kiểm soát đồng thời. |

Tránh hai cách làm cực đoan. Nếu chỉ kiểm tra ở controller, các đường gọi khác có thể bỏ qua quy tắc. Nếu đưa mọi chi tiết định dạng HTTP vào domain, domain bị phụ thuộc vào một kênh giao tiếp và khó tái sử dụng. Hãy đặt cùng một điều kiện ở nhiều tầng chỉ khi mỗi lần kiểm tra bảo vệ một ranh giới hoặc bất biến cụ thể.

## 5. Phân loại lỗi và phản hồi phù hợp

Khi kiểm tra được đặt đúng tầng, lỗi cũng có thể được phân loại rõ hơn:

| Loại lỗi | Ví dụ | Nơi phát hiện thường gặp | Phản hồi có thể dùng |
|---|---|---|---|
| Lỗi cú pháp/phân tích | JSON hỏng, UUID không phân tích được, kiểu dữ liệu sai. | Parser hoặc binding của tầng trình bày. | HTTP 400. |
| Lỗi hợp đồng đầu vào | Thiếu trường bắt buộc, chuỗi quá dài, số tiền sai miền biểu diễn. | Bean Validation ở tầng trình bày. | HTTP 400; API có thể trả danh sách lỗi theo trường. |
| Không tìm thấy tài nguyên | Tài khoản có mã hợp lệ nhưng không tồn tại. | Tầng ứng dụng khi tải dữ liệu. | HTTP 404 nếu hợp đồng API biểu diễn tài nguyên không tồn tại. |
| Xung đột trạng thái nghiệp vụ | Tài khoản bị khóa, đơn đã giao nhưng vẫn yêu cầu hủy. | Domain hoặc policy nghiệp vụ. | HTTP 409 nếu yêu cầu xung đột với trạng thái hiện tại. |
| Không thỏa điều kiện nghiệp vụ | Giao dịch vượt hạn mức hoặc không đủ điều kiện theo chính sách. | Domain/policy hoặc tầng ứng dụng điều phối policy. | HTTP 422 hoặc 409 tùy ý nghĩa và hợp đồng API. |
| Lỗi hạ tầng | Cơ sở dữ liệu không khả dụng, dịch vụ ngoài hết thời gian chờ. | Adapter hạ tầng. | HTTP 5xx hoặc cơ chế retry phù hợp với kênh. |

Mã HTTP chỉ là cách adapter REST trình bày lỗi. CLI có thể trả mã thoát và thông báo văn bản; message consumer có thể retry lỗi tạm thời hoặc chuyển message không thể xử lý sang dead-letter queue. Không nên để domain ném ResponseStatusException hoặc tạo ResponseEntity, vì các kiểu đó thuộc Spring Web và làm quy tắc nghiệp vụ phụ thuộc HTTP.

Một RestControllerAdvice có thể chuyển lỗi của tầng trình bày và lỗi nghiệp vụ thành định dạng API thống nhất:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {
    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleInvalidRequest(
            MethodArgumentNotValidException exception) {
        return ResponseEntity.badRequest()
            .body(new ApiError("INVALID_REQUEST",
                "Dữ liệu đầu vào không hợp lệ"));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> handleUnreadableMessage(
            HttpMessageNotReadableException exception) {
        return ResponseEntity.badRequest()
            .body(new ApiError("MALFORMED_REQUEST",
                "Không thể phân tích nội dung request"));
    }

    @ExceptionHandler(InsufficientFundsException.class)
    ResponseEntity<ApiError> handleInsufficientFunds(
            InsufficientFundsException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError("INSUFFICIENT_FUNDS",
                "Tài khoản không đủ số dư"));
    }
}

record ApiError(String code, String message) {}
~~~

Đây là ví dụ rút gọn; ứng dụng thực tế nên tránh trả thông tin nội bộ hoặc dữ liệu nhạy cảm trong thông báo lỗi. Các lỗi nghiệp vụ khác cần được ánh xạ theo ý nghĩa và hợp đồng API cụ thể. Không nên gom tất cả ngoại lệ thành HTTP 400, vì như vậy người gọi khó phân biệt request sai định dạng với một hành động không được phép theo trạng thái nghiệp vụ.

## 6. Kiểm thử từng loại kiểm tra ở phạm vi phù hợp

Ranh giới kiểm tra rõ ràng giúp chọn phạm vi kiểm thử phù hợp:

- **Test parser/controller:** gửi JSON sai cú pháp, UUID không hợp lệ, thiếu trường, số tiền sai định dạng và chuỗi vượt giới hạn. Xác minh adapter trả lỗi theo hợp đồng HTTP và không gọi ca sử dụng khi request không thể chuyển đổi.
- **Domain unit test:** tạo tài khoản bị khóa, số dư không đủ, hai tài khoản trùng nhau hoặc số tiền không dương. Xác minh domain từ chối hành động bất kể nguồn gọi.
- **Application test:** kiểm tra tài khoản không tồn tại, quyền truy cập, hạn mức và thứ tự phối hợp repository/policy. Có thể dùng fake hoặc mock cho các cổng để tập trung vào ca sử dụng.
- **Integration test:** xác minh giao dịch, constraint cơ sở dữ liệu và xử lý đồng thời trong môi trường gần với thực tế.

Ví dụ, một domain unit test cho số dư không đủ có thể gọi trực tiếp hành vi tài khoản:

~~~java
@Test
void rejectsTransferWhenBalanceIsInsufficient() {
    Account source = Account.activeWithBalance(
        AccountId.newId(), new BigDecimal("100.00"));
    Account target = Account.activeWithBalance(
        AccountId.newId(), new BigDecimal("50.00"));

    assertThrows(InsufficientFundsException.class,
        () -> source.transferTo(
            target, new TransferAmount(new BigDecimal("150.00"))));
}
~~~

Bài kiểm thử này không cần khởi động Spring MVC, tạo JSON hay kết nối cơ sở dữ liệu. Nó kiểm tra đúng quy tắc mà domain sở hữu. Một test controller riêng sẽ kiểm tra JSON sai hoặc trường thiếu và xác minh ca sử dụng không bị gọi trong trường hợp request không hợp lệ.

Nếu muốn kiểm tra một bất biến domain mà phải dựng HTTP server và cơ sở dữ liệu, có thể quy tắc đang bị đặt quá xa mô hình nghiệp vụ hoặc bị gắn chặt với hạ tầng. Ngược lại, nếu controller chứa nhiều truy vấn và nhánh điều kiện về trạng thái tài khoản, tầng trình bày có thể đang gánh cả công việc của ứng dụng và domain.

## 7. Quy trình xác định nơi đặt một điều kiện kiểm tra

Khi thêm một điều kiện mới, hãy đi theo các bước sau:

1. Xác định điều kiện đó nói về định dạng của dữ liệu hay tính hợp lệ của hành động. “Ngày có đúng định dạng ISO không?” thuộc hợp đồng đầu vào; “ngày giao hàng có nằm trong khoảng được phép theo chính sách không?” thuộc nghiệp vụ.
2. Xác định điều kiện có phụ thuộc vào giao thức hay không. Nếu nó chỉ có ý nghĩa với JSON hoặc tham số CLI, hãy đặt ở adapter tương ứng.
3. Nếu điều kiện phải đúng với mọi nguồn gọi, đặt quy tắc có thẩm quyền ở domain hoặc policy phù hợp. Đừng giả định mọi tác nhân đều đi qua cùng controller.
4. Nếu cần tải dữ liệu hoặc xác định người thực hiện, để tầng ứng dụng cung cấp ngữ cảnh và điều phối việc kiểm tra.
5. Nếu tính nhất quán phải được bảo vệ ở cấp lưu trữ, bổ sung constraint hoặc cơ chế giao dịch thích hợp; xem đây là lớp bảo vệ bổ sung cho mô hình nghiệp vụ.
6. Viết kiểm thử ở phạm vi của trách nhiệm đó, rồi kiểm tra adapter ánh xạ lỗi đúng với giao thức của nó.

Một thiết kế phân tầng tốt cho phép người đọc nhận ra vì sao một yêu cầu bị từ chối. Dữ liệu sai cú pháp bị chặn ở biên; điều kiện cần ngữ cảnh được đánh giá trong ca sử dụng; bất biến và chính sách nghiệp vụ được bảo vệ bởi domain; ràng buộc lưu trữ củng cố tính nhất quán. Khi các trách nhiệm này được tách rõ, hệ thống có thể bổ sung kênh giao tiếp mới mà vẫn giữ nguyên các quy tắc nghiệp vụ quan trọng.


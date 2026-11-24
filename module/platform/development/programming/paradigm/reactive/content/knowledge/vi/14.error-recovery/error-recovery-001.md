# Lỗi và phục hồi

## Phân loại lỗi dữ liệu, lỗi nghiệp vụ và lỗi hạ tầng

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi một pipeline thất bại, bước đầu tiên để chọn cách phục hồi đúng là hiểu lỗi thuộc loại nào. Lỗi dữ liệu, lỗi nghiệp vụ và lỗi hạ tầng có thể cùng xuất hiện dưới dạng `onError`, nhưng nguyên nhân và cách xử lý của chúng rất khác nhau.

Một payload sai định dạng thường cần được từ chối hoặc đưa vào hàng đợi xử lý lỗi. Một yêu cầu vi phạm quy tắc nghiệp vụ cần trả lời rõ lý do từ chối cho caller. Một dịch vụ cơ sở dữ liệu tạm thời không khả dụng có thể cần retry có giới hạn hoặc chuyển sang cơ chế dự phòng. Nếu gom tất cả thành một lỗi chung rồi retry, hệ thống có thể lặp lại công việc vô ích, làm tăng tải hoặc che mất vấn đề dữ liệu.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt lỗi dữ liệu, lỗi nghiệp vụ và lỗi hạ tầng theo nguyên nhân và ý nghĩa.
- Xác định lỗi nào nên được biểu diễn thành giá trị kết quả và lỗi nào nên đi qua tín hiệu `onError`.
- Thiết kế kiểu exception và thông tin lỗi giúp tầng gọi chọn cách xử lý.
- Dùng các toán tử Reactor như `onErrorMap`, `onErrorResume` và `doOnError` ở đúng ranh giới.
- Chỉ retry lỗi hạ tầng có khả năng phục hồi và giới hạn tổng số lần thử.
- Xử lý lỗi riêng cho từng phần tử trong `Flux` mà không vô tình dừng cả luồng.
- Kiểm thử việc phân loại và truyền lỗi bằng `StepVerifier`.

## 1. Vì sao cần phân loại lỗi?

Một lỗi kỹ thuật chỉ cho biết một thao tác không hoàn tất như mong đợi. Để quyết định bước tiếp theo, ứng dụng cần biết điều gì đã xảy ra và ai có thể khắc phục.

Ví dụ, cùng một API tạo đơn hàng có thể thất bại vì:

- JSON thiếu trường bắt buộc hoặc trường ngày tháng không hợp lệ.
- Khách hàng không đủ hạn mức hoặc đơn hàng không thể chuyển từ trạng thái hiện tại.
- Cơ sở dữ liệu tạm thời mất kết nối.
- Dịch vụ thanh toán hết thời gian chờ.
- Một message bị hỏng do phiên bản schema không tương thích.

Những trường hợp này không nên được xử lý như nhau. Payload không hợp lệ không trở nên hợp lệ sau khi gọi lại cùng một request. Một giao dịch bị từ chối theo quy tắc nghiệp vụ cũng không nên được retry vô hạn. Ngược lại, lỗi kết nối tạm thời có thể thành công nếu thử lại sau một khoảng nghỉ.

~~~mermaid
flowchart TD
    E[Lỗi trong pipeline] --> C{Phân loại theo nguyên nhân và ngữ nghĩa}
    C --> D[Lỗi dữ liệu]
    C --> B[Lỗi nghiệp vụ]
    C --> I[Lỗi hạ tầng]
    D --> D1[Từ chối / sửa dữ liệu / DLQ]
    B --> B1[Trả kết quả hoặc lỗi nghiệp vụ]
    I --> I1[Retry có giới hạn / fallback / báo lỗi]
~~~

Phân loại nên dựa trên hai câu hỏi:

1. **Điều gì đã sai?** Dữ liệu đầu vào, quy tắc của miền nghiệp vụ hay một thành phần kỹ thuật?
2. **Ai hoặc điều gì có thể làm thao tác thành công?** Caller sửa payload, nghiệp vụ thay đổi trạng thái hoặc hệ thống hạ tầng phục hồi?

Nguồn phát sinh là một manh mối, nhưng ngữ nghĩa mới quyết định cách xử lý. Ví dụ, lỗi unique constraint ở cơ sở dữ liệu có thể đại diện cho xung đột nghiệp vụ như mã đơn đã tồn tại; lỗi schema hoặc tablespace đầy lại là vấn đề dữ liệu/hạ tầng khác. Không nên phân loại chỉ bằng tên lớp exception.

## 2. Lỗi dữ liệu: đầu vào hoặc bản ghi không đáp ứng hợp đồng

Lỗi dữ liệu xảy ra khi dữ liệu không thể được đọc, giải mã, xác thực cấu trúc hoặc sử dụng theo hợp đồng dữ liệu mà ứng dụng yêu cầu.

Các ví dụ thường gặp:

- JSON/XML sai cú pháp hoặc không giải mã được.
- Trường bắt buộc bị thiếu, sai kiểu hoặc sai định dạng.
- Giá trị nằm ngoài miền hợp lệ về cấu trúc, chẳng hạn số lượng âm khi schema yêu cầu số không âm.
- Bản ghi lưu trữ bị thiếu trường bắt buộc hoặc vi phạm invariant dữ liệu.
- Message không tương thích schema mà consumer đang hỗ trợ.

Có thể chia lỗi dữ liệu thành hai nhóm để chọn hướng xử lý:

| Nhóm | Ví dụ | Hướng xử lý thường gặp |
|---|---|---|
| Lỗi đầu vào từ caller | JSON sai, email sai định dạng, thiếu trường | Trả lỗi validation, yêu cầu caller sửa |
| Lỗi dữ liệu đã lưu hoặc message | Bản ghi hỏng, schema không tương thích, message không giải mã được | Cách ly, ghi nhận, sửa dữ liệu hoặc chuyển DLQ |

### Xác thực dữ liệu trước khi thực hiện nghiệp vụ

Không nên để dữ liệu sai đi sâu vào các bước ghi hoặc gọi dịch vụ bên ngoài. Có thể xác thực ngay khi giải mã hoặc tại ranh giới ứng dụng:

~~~java
Mono<CreateOrderCommand> validate(CreateOrderRequest request) {
    if (request.customerId() == null || request.customerId().isBlank()) {
        return Mono.error(new InvalidDataException("customerId is required"));
    }

    if (request.items() == null || request.items().isEmpty()) {
        return Mono.error(new InvalidDataException("items must not be empty"));
    }

    boolean invalidQuantity = request.items().stream()
        .anyMatch(item -> item.quantity() <= 0);

    if (invalidQuantity) {
        return Mono.error(new InvalidDataException("quantity must be positive"));
    }

    return Mono.just(toCommand(request));
}
~~~

Nếu kiểm tra là đồng bộ và thuần túy, có thể dùng `map` để biến đổi và ném exception khi dữ liệu sai; Reactor sẽ chuyển exception phát sinh trong toán tử thành tín hiệu lỗi. Dùng `Mono.error` như trên giúp thể hiện rõ hợp đồng trả về Publisher.

Với nhiều lỗi validation, thường hữu ích hơn nếu thu thập danh sách vi phạm và trả về cùng lúc, thay vì dừng ở lỗi đầu tiên. Điều đó giúp caller sửa dữ liệu trong một lần gửi lại.

### Không phải mọi giá trị bất thường đều là lỗi dữ liệu

Một giá trị có định dạng đúng vẫn có thể không được nghiệp vụ chấp nhận. Ví dụ, số dư là số thập phân hợp lệ nhưng nhỏ hơn số tiền cần thanh toán. Đây thường là lỗi nghiệp vụ, không phải lỗi cấu trúc dữ liệu.

Tương tự, một bản ghi không tìm thấy có thể có ý nghĩa khác nhau: nếu caller gửi ID sai thì đó là lỗi yêu cầu; nếu bản ghi được kỳ vọng phải tồn tại theo invariant nội bộ thì có thể là lỗi nhất quán dữ liệu. Cần xác định hợp đồng của từng use case.

## 3. Lỗi nghiệp vụ: yêu cầu không thể được chấp nhận theo quy tắc miền

Lỗi nghiệp vụ xảy ra khi dữ liệu có thể hợp lệ về mặt cấu trúc, nhưng hành động được yêu cầu vi phạm quy tắc của miền ứng dụng hoặc trạng thái hiện tại.

Ví dụ:

- Tài khoản không đủ số dư để chuyển tiền.
- Đơn hàng đã bị hủy nên không thể giao hàng.
- Khách hàng vượt hạn mức tín dụng.
- Mã khuyến mãi đã hết hiệu lực.
- Một thao tác chuyển trạng thái không được phép trong state machine.
- Một yêu cầu tạo tài nguyên trùng với tài nguyên đã tồn tại theo quy tắc nghiệp vụ.

Các lỗi này thường không được giải quyết bằng retry cùng một dữ liệu. Caller hoặc người dùng cần thay đổi yêu cầu, hoặc trạng thái miền cần thay đổi trước khi thao tác có thể thành công.

### Biểu diễn kết quả nghiệp vụ dự kiến

Không phải mọi trường hợp nghiệp vụ không được chấp nhận đều phải là exception. Nếu việc từ chối là một kết quả bình thường mà caller cần xử lý như một nhánh của quy trình, có thể biểu diễn thành kiểu kết quả:

~~~java
sealed interface PaymentDecision {
    record Approved(Receipt receipt) implements PaymentDecision {}
    record Rejected(String code, String reason) implements PaymentDecision {}
}

Mono<PaymentDecision> authorize(PaymentCommand command) {
    return accountRepository.findById(command.accountId())
        .map(account -> {
            if (account.availableBalance().compareTo(command.amount()) < 0) {
                return new PaymentDecision.Rejected(
                    "INSUFFICIENT_FUNDS",
                    "Available balance is too low"
                );
            }

            return new PaymentDecision.Approved(
                createReceipt(command, account)
            );
        });
}
~~~

Trong ví dụ, quyết định từ chối là một giá trị hợp lệ của `PaymentDecision`. Pipeline vẫn hoàn tất bình thường bằng `onNext` và `onComplete`; caller có thể hiển thị thông báo hoặc thực hiện nhánh nghiệp vụ tương ứng.

Nếu việc từ chối đại diện cho một điều kiện bất thường ở ranh giới use case, có thể dùng exception nghiệp vụ có kiểu cụ thể:

~~~java
final class BusinessRuleViolationException extends RuntimeException {
    private final String code;

    BusinessRuleViolationException(String code, String message) {
        super(message);
        this.code = code;
    }

    String code() {
        return code;
    }
}
~~~

Ví dụ dùng exception:

~~~java
Mono<Receipt> authorize(PaymentCommand command) {
    return accountRepository.findById(command.accountId())
        .switchIfEmpty(Mono.error(
            new BusinessRuleViolationException(
                "ACCOUNT_NOT_FOUND",
                "The requested account does not exist"
            )
        ))
        .flatMap(account -> {
            if (account.availableBalance().compareTo(command.amount()) < 0) {
                return Mono.error(
                    new BusinessRuleViolationException(
                        "INSUFFICIENT_FUNDS",
                        "Available balance is too low"
                    )
                );
            }

            return paymentRepository.save(createPayment(command));
        });
}
~~~

Chọn giữa giá trị kết quả và exception dựa trên hợp đồng. Nếu caller thường xuyên cần phân nhánh theo quyết định nghiệp vụ, kiểu kết quả tường minh thường dễ hiểu và ít phụ thuộc vào exception. Nếu thao tác không thể tiếp tục và use case xem đó là thất bại, exception có kiểu cụ thể có thể phù hợp.

## 4. Lỗi hạ tầng: thành phần kỹ thuật không thể hoàn thành công việc

Lỗi hạ tầng xuất hiện khi ứng dụng không thể tương tác bình thường với tài nguyên hoặc dịch vụ kỹ thuật.

Ví dụ:

- Database hoặc connection pool tạm thời không khả dụng.
- HTTP client gặp lỗi kết nối, DNS hoặc timeout.
- Message broker từ chối kết nối hoặc consumer bị mất session.
- Một dịch vụ phụ thuộc trả HTTP 503 hoặc 429.
- Thread pool, bộ nhớ hoặc giới hạn tài nguyên bị cạn.
- Lỗi TLS, cấu hình endpoint hoặc chứng thực dịch vụ.

Không phải mọi lỗi hạ tầng đều tạm thời. Timeout hoặc connection reset có thể phục hồi; sai chứng thư, sai credentials hoặc endpoint cấu hình sai thường không tự hết khi retry. Vì vậy, cần phân biệt **transient** (có khả năng tạm thời) và **permanent/configuration** (cần sửa cấu hình hoặc vận hành).

| Tình huống | Có thể retry? | Điều kiện |
|---|---|---|
| Connection reset, lỗi mạng thoáng qua | Có thể | Giới hạn số lần, backoff, jitter |
| HTTP 503 từ dịch vụ phụ thuộc | Có thể | Tôn trọng Retry-After nếu có và deadline tổng |
| HTTP 429 | Có thể | Điều tiết tốc độ và tuân thủ thời gian chờ phía server |
| Timeout khi đọc dữ liệu | Có thể | Request có thể lặp an toàn và còn ngân sách thời gian |
| Sai credentials hoặc TLS config | Thường không | Cần sửa cấu hình hoặc chứng thư |
| Database schema không tương thích | Không nên retry liên tục | Cần triển khai/sửa schema |
| Hết bộ nhớ hoặc quá tải kéo dài | Không nên retry mù quáng | Cần giảm tải hoặc phục hồi tài nguyên |

Một lỗi HTTP 404 cũng không tự động là lỗi hạ tầng; thường nó có ý nghĩa nghiệp vụ hoặc yêu cầu. Một lỗi database constraint cũng cần được diễn giải theo constraint và use case cụ thể.

## 5. Thiết kế hệ phân loại lỗi trong Java

Có thể xây dựng các lớp exception riêng để giữ ngữ nghĩa qua các tầng:

~~~java
abstract class ApplicationException extends RuntimeException {
    private final String code;

    protected ApplicationException(String code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    String code() {
        return code;
    }
}

final class InvalidDataException extends ApplicationException {
    InvalidDataException(String message) {
        super("INVALID_DATA", message, null);
    }
}

final class BusinessRuleException extends ApplicationException {
    BusinessRuleException(String code, String message) {
        super(code, message, null);
    }
}

final class DependencyUnavailableException extends ApplicationException {
    DependencyUnavailableException(String dependency, Throwable cause) {
        super("DEPENDENCY_UNAVAILABLE",
              dependency + " is unavailable",
              cause);
    }
}
~~~

Lớp exception giữ mã lỗi ổn định cho hệ thống, message có thể đọc được và nguyên nhân gốc khi chuyển đổi từ exception thư viện. Tránh đưa thông tin nhạy cảm như token, mật khẩu, dữ liệu thanh toán hoặc query chứa dữ liệu cá nhân vào message/log.

### Phân loại gần ranh giới phát sinh lỗi

Ví dụ một client gọi dịch vụ tồn kho có thể chuyển exception kỹ thuật của thư viện thành lỗi ứng dụng:

~~~java
Mono<Stock> loadStock(String sku) {
    return inventoryClient.fetchStock(sku)
        .onErrorMap(
            WebClientRequestException.class,
            error -> new DependencyUnavailableException("inventory", error)
        );
}
~~~

`onErrorMap` chuyển lỗi đi qua pipeline thành một loại lỗi có ý nghĩa trong ứng dụng, đồng thời giữ exception gốc làm cause. Không nên chuyển mọi exception thành `DependencyUnavailableException`: lỗi decode payload có thể là lỗi dữ liệu, còn lỗi 4xx có thể là từ chối nghiệp vụ hoặc lỗi yêu cầu.

Nếu thư viện phát nhiều loại lỗi, hãy phân loại có điều kiện:

~~~java
Mono<Stock> loadStock(String sku) {
    return inventoryClient.fetchStock(sku)
        .onErrorMap(error -> {
            if (error instanceof WebClientRequestException) {
                return new DependencyUnavailableException("inventory", error);
            }

            if (error instanceof DecodingException) {
                return new InvalidDataException("Inventory response is malformed");
            }

            return error;
        });
}
~~~

Đây chỉ là ví dụ minh họa. Trong ứng dụng thực tế, lỗi decode có thể cần một exception riêng giữ cause; lớp `InvalidDataException` ở trên đơn giản hóa constructor để làm rõ cách phân loại. Hãy giữ đủ thông tin kỹ thuật cho log nội bộ nhưng chỉ trả chi tiết an toàn cho caller.

## 6. Tín hiệu onError và cách xử lý trong Reactor

Reactive Streams có ba tín hiệu chính từ Publisher tới Subscriber: `onNext`, `onError` và `onComplete`. `onError` là tín hiệu kết thúc; sau khi một Publisher phát lỗi, nó không tiếp tục phát thêm phần tử trên cùng subscription.

Reactor cung cấp các toán tử để quan sát, chuyển đổi hoặc phục hồi lỗi:

| Toán tử | Vai trò | Dùng khi |
|---|---|---|
| `doOnError` | Quan sát lỗi, không thay thế lỗi | Ghi metric, log, tracing |
| `onErrorMap` | Chuyển exception thành exception khác | Chuẩn hóa lỗi ở ranh giới tầng |
| `onErrorResume` | Chuyển sang Publisher thay thế | Fallback hoặc ánh xạ lỗi thành kết quả |
| `onErrorReturn` | Trả một giá trị thay thế | Giá trị mặc định thực sự hợp lệ |
| `retryWhen` | Subscribe lại khi lỗi thỏa điều kiện | Lỗi tạm thời và thao tác an toàn khi lặp |

Ví dụ kết hợp quan sát và chuẩn hóa:

~~~java
Mono<Customer> customer =
    customerRepository.findById(customerId)
        .doOnError(error -> metrics.recordRepositoryFailure())
        .onErrorMap(
            DataAccessResourceFailureException.class,
            error -> new DependencyUnavailableException("customer-db", error)
        );
~~~

`doOnError` được đặt trước `onErrorMap`, vì vậy nó quan sát exception từ repository. Nếu cần metric theo loại lỗi đã chuẩn hóa, có thể đặt một callback quan sát khác sau `onErrorMap`.

Không nên dùng `doOnError` để phục hồi. Callback này chỉ chạy khi lỗi đi qua; nó không biến lỗi thành giá trị và không làm pipeline tiếp tục.

## 7. Chọn recovery theo loại lỗi

Một chính sách phục hồi tốt phải dựa trên loại lỗi, tính an toàn khi lặp và yêu cầu của caller.

### Lỗi dữ liệu: từ chối hoặc cách ly

Với payload sai, retry cùng dữ liệu thường không có ích. Có thể trả lỗi validation ở API hoặc chuyển message hỏng vào dead-letter queue (DLQ) để kiểm tra sau:

~~~java
Mono<Order> createOrder(CreateOrderRequest request) {
    return validate(request)
        .flatMap(orderService::create);
}
~~~

Nếu validation thất bại, pipeline kết thúc trước khi gọi service tạo đơn. Với consumer xử lý message, cần ghi nhận ID message, mã lỗi và thông tin chẩn đoán an toàn trước khi ack hoặc chuyển DLQ theo semantics của broker. Không được âm thầm bỏ message quan trọng.

### Lỗi nghiệp vụ: trả kết quả có ý nghĩa

Nếu việc từ chối là một kết quả được dự kiến, trả một kiểu kết quả như `PaymentDecision.Rejected`. Nếu dùng exception, có thể ánh xạ nó thành phản hồi phù hợp ở tầng API:

~~~java
Mono<ServerResponse> handlePayment(PaymentCommand command) {
    return paymentService.authorize(command)
        .flatMap(result ->
            ServerResponse.ok().bodyValue(result)
        )
        .onErrorResume(BusinessRuleException.class, error ->
            ServerResponse.unprocessableEntity()
                .bodyValue(Map.of(
                    "code", error.code(),
                    "message", error.getMessage()
                ))
        );
}
~~~

Mã HTTP cụ thể phụ thuộc hợp đồng API. Ví dụ, dữ liệu không hợp lệ có thể là 400 hoặc 422; tài nguyên không tồn tại có thể là 404; xung đột trạng thái có thể là 409. Hãy nhất quán và không để exception nội bộ bị trả nguyên văn cho client.

### Lỗi hạ tầng tạm thời: retry có giới hạn hoặc fallback

Với lỗi mạng tạm thời, có thể retry bằng backoff:

~~~java
Mono<Stock> stock =
    Mono.defer(() -> inventoryClient.fetchStock(sku))
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(100))
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(DependencyUnavailableException.class::isInstance)
        );
~~~

Trong ví dụ, có tối đa ba lần retry sau lần gọi ban đầu. Khoảng nghỉ tăng dần, có giới hạn tối đa và jitter để giảm nguy cơ nhiều client cùng retry tại một thời điểm. Chỉ lỗi đã phân loại là dịch vụ phụ thuộc không khả dụng mới được retry.

Nếu dịch vụ dự phòng có dữ liệu phù hợp, có thể dùng `onErrorResume` có điều kiện:

~~~java
Mono<Stock> stock =
    inventoryClient.fetchStock(sku)
        .onErrorResume(
            DependencyUnavailableException.class,
            error -> stockCache.findRecent(sku)
        );
~~~

Fallback cần được đánh giá theo độ mới và độ chính xác dữ liệu. Dữ liệu cache cũ có thể phù hợp cho hiển thị nhưng không phù hợp để quyết định bán một sản phẩm cuối cùng trong kho.

## 8. Retry không phải là cách xử lý chung cho mọi lỗi

Retry subscribe lại Publisher nguồn. Nếu nguồn thực hiện tác dụng phụ, mỗi lần thử có thể lặp thao tác. Vì vậy, trước khi retry cần trả lời:

- Lỗi có khả năng tạm thời không?
- Thao tác có idempotent không?
- Server có thể đã commit trước khi client nhận timeout không?
- Số lần retry và backoff có nằm trong deadline của request không?
- Retry có làm tăng tải lên dịch vụ đang quá tải không?

Không retry lỗi dữ liệu như JSON sai, lỗi nghiệp vụ như thiếu số dư hoặc sai trạng thái, hay lỗi cấu hình như credentials không hợp lệ. Retry có thể phù hợp với connection reset hoặc lỗi 503 thoáng qua, nhưng phải có giới hạn.

Với thao tác ghi, sử dụng idempotency key ổn định cho cùng một lệnh qua các lần retry. Nếu không thể bảo đảm tính idempotent, hãy truy vấn trạng thái trước khi gửi lại hoặc để workflow đối soát kết quả không xác định.

## 9. Lỗi trong Flux: dừng toàn luồng hay xử lý từng phần tử?

Với `Flux`, lỗi không được xử lý thường kết thúc cả subscription. Giả sử một nguồn chứa nhiều bản ghi:

~~~java
Flux<EnrichedOrder> enriched =
    orders.flatMap(order ->
        enrichmentService.enrich(order)
    );
~~~

Nếu Publisher con của một đơn phát lỗi, lỗi có thể kết thúc luồng kết quả và các inner còn lại do toán tử quản lý có thể bị hủy. Điều này phù hợp nếu một lỗi làm hỏng toàn bộ batch, nhưng không phù hợp nếu mỗi bản ghi độc lập và cần tiếp tục xử lý các bản ghi khác.

Nếu muốn cách ly lỗi theo từng phần tử, đặt recovery bên trong mapper:

~~~java
Flux<ProcessingOutcome> outcomes =
    orders.flatMap(order ->
        enrichmentService.enrich(order)
            .map(ProcessingOutcome::success)
            .onErrorResume(error ->
                Mono.just(ProcessingOutcome.failure(order.id(), classify(error)))
            ),
        16
    );
~~~

Mỗi lỗi của một đơn được chuyển thành một kết quả thất bại; các đơn khác vẫn tiếp tục. `classify(error)` nên trả một mã lỗi an toàn và ổn định, không đưa stack trace hoặc thông tin nhạy cảm vào kết quả nghiệp vụ.

Nếu cần xử lý tuần tự, có thể dùng `concatMap` với recovery bên trong mapper. Khi inner lỗi đã được chuyển thành giá trị kết quả và hoàn tất bình thường, toán tử tiếp tục phần tử tiếp theo.

Không nên dùng `onErrorContinue` như một cách tổng quát để bỏ qua lỗi. Hành vi của nó phụ thuộc toán tử upstream hỗ trợ và có thể làm khó xác định phần tử nào đã bị bỏ. Recovery theo từng phần tử với `onErrorResume` thường rõ ràng hơn.

## 10. Giữ ngữ cảnh lỗi khi đi qua nhiều tầng

Khi một lỗi được chuyển đổi qua nhiều lớp, đừng làm mất nguyên nhân gốc. Ví dụ, tầng repository có thể ném exception driver, tầng ứng dụng chuyển thành `DependencyUnavailableException`, còn tầng API ánh xạ thành phản hồi 503. Chuỗi cause giúp người vận hành tìm ra lỗi kỹ thuật ban đầu.

~~~java
Mono<Profile> loadProfile(String id) {
    return profileRepository.findById(id)
        .onErrorMap(error ->
            new DependencyUnavailableException("profile-db", error)
        );
}
~~~

Ở ranh giới HTTP, chỉ trả mã và thông điệp phù hợp với client:

~~~java
Mono<ServerResponse> handleProfile(String id) {
    return profileService.loadProfile(id)
        .flatMap(profile ->
            ServerResponse.ok().bodyValue(profile)
        )
        .onErrorResume(DependencyUnavailableException.class, error ->
            ServerResponse.status(HttpStatus.SERVICE_UNAVAILABLE)
                .bodyValue(Map.of(
                    "code", error.code(),
                    "message", "Profile service is temporarily unavailable"
                ))
        );
}
~~~

Log nội bộ có thể ghi exception cùng cause, trace ID và dependency liên quan. Không trả trực tiếp `error.getMessage()` của exception driver hoặc HTTP client ra ngoài vì nó có thể chứa host, query, thông tin xác thực hoặc dữ liệu nhạy cảm.

Một lỗi nên có các thông tin hữu ích:

- Mã lỗi ổn định để caller và dashboard phân loại.
- Loại lỗi và dependency liên quan.
- Correlation/trace ID để liên kết log giữa các dịch vụ.
- Cause gốc để điều tra kỹ thuật.
- ID nghiệp vụ hoặc message ID nếu được phép ghi nhận an toàn.

## 11. Kiểm thử phân loại và phục hồi

`StepVerifier` cho phép xác minh tín hiệu lỗi, kiểu exception, fallback và hành vi tiếp tục của luồng.

### Kiểm thử lỗi dữ liệu

~~~java
Mono<Order> invalidOrder =
    Mono.defer(() -> validate(new CreateOrderRequest(null, List.of())));

StepVerifier.create(invalidOrder)
    .expectError(InvalidDataException.class)
    .verify();
~~~

Test xác nhận dữ liệu không hợp lệ kết thúc bằng loại lỗi được thiết kế. Có thể kiểm tra thêm mã lỗi hoặc nội dung danh sách vi phạm.

### Kiểm thử lỗi nghiệp vụ

~~~java
Mono<Receipt> rejected =
    Mono.error(new BusinessRuleException(
        "INSUFFICIENT_FUNDS",
        "Available balance is too low"
    ));

StepVerifier.create(rejected)
    .expectErrorSatisfies(error -> {
        assertThat(error).isInstanceOf(BusinessRuleException.class);
        assertThat(((BusinessRuleException) error).code())
            .isEqualTo("INSUFFICIENT_FUNDS");
    })
    .verify();
~~~

Test xác nhận lỗi nghiệp vụ giữ mã ổn định để tầng API có thể ánh xạ đúng phản hồi.

### Kiểm thử retry cho lỗi hạ tầng tạm thời

~~~java
AtomicInteger attempts = new AtomicInteger();

Mono<String> source =
    Mono.defer(() -> {
        if (attempts.incrementAndGet() < 3) {
            return Mono.error(
                new DependencyUnavailableException("inventory", null)
            );
        }

        return Mono.just("available");
    });

StepVerifier.withVirtualTime(() ->
        source.retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .filter(DependencyUnavailableException.class::isInstance)
        )
    )
    .thenAwait(Duration.ofSeconds(1))
    .expectNext("available")
    .verifyComplete();

assertThat(attempts.get()).isEqualTo(3);
~~~

Nguồn thất bại hai lần rồi thành công ở lần thứ ba. Thời gian ảo giúp kiểm thử backoff mà không phải chờ thật. Trong test thực tế, nên tạo Publisher bên trong supplier của `withVirtualTime` khi cần scheduler ảo được cài trước khi lắp ráp các toán tử thời gian.

### Kiểm thử cách ly lỗi từng phần tử

~~~java
Flux<ProcessingOutcome> outcomes =
    Flux.just("valid-1", "invalid", "valid-2")
        .flatMap(value ->
            process(value)
                .map(ProcessingOutcome::success)
                .onErrorResume(error ->
                    Mono.just(ProcessingOutcome.failure(value, classify(error)))
                )
        );

StepVerifier.create(outcomes)
    .expectNextMatches(ProcessingOutcome::isSuccess)
    .expectNextMatches(ProcessingOutcome::isFailure)
    .expectNextMatches(ProcessingOutcome::isSuccess)
    .verifyComplete();
~~~

Test xác nhận lỗi của một phần tử được biểu diễn thành kết quả thất bại và các phần tử sau vẫn được xử lý. Nếu dùng `flatMap`, thứ tự phát kết quả có thể không theo nguồn; nếu test cần xác nhận thứ tự đầu vào, dùng nguồn đồng bộ phù hợp hoặc `concatMap`.

## 12. Những nhầm lẫn thường gặp

- **Mọi exception đều là lỗi hạ tầng:** exception chỉ là biểu diễn kỹ thuật; cần xét ngữ nghĩa và nguyên nhân thực tế.
- **Lỗi dữ liệu có thể retry:** gửi lại cùng payload sai thường cho cùng kết quả; caller phải sửa dữ liệu hoặc message cần được cách ly.
- **Lỗi nghiệp vụ là lỗi hệ thống:** từ chối do thiếu số dư hoặc sai trạng thái có thể là kết quả nghiệp vụ dự kiến.
- **Lỗi database luôn là lỗi hạ tầng:** unique constraint có thể thể hiện xung đột nghiệp vụ; schema mismatch có thể là lỗi triển khai hoặc dữ liệu.
- **HTTP 5xx luôn retry an toàn:** một số lỗi 5xx xảy ra sau khi server đã thực hiện tác dụng phụ; cần idempotency và phân loại theo hợp đồng.
- **`doOnError` phục hồi pipeline:** nó chỉ quan sát lỗi; dùng `onErrorResume` hoặc toán tử recovery khác để thay thế luồng.
- **Một lỗi trong Flux chỉ ảnh hưởng một phần tử:** theo mặc định, `onError` kết thúc subscription; muốn cách ly phải recovery bên trong mapper.
- **Fallback luôn tốt hơn báo lỗi:** fallback dữ liệu cũ hoặc giá trị mặc định sai có thể gây quyết định nghiệp vụ nguy hiểm.
- **Chuyển exception thành lỗi chung là đủ:** giữ mã lỗi, cause và ngữ cảnh giúp các tầng xử lý đúng và vận hành dễ điều tra.

## 13. Bài tập vận dụng

Một consumer nhận message tạo đơn hàng. Trong quá trình xử lý, hệ thống có thể gặp ba tình huống:

1. Message có JSON sai định dạng hoặc thiếu `customerId`.
2. Dữ liệu đúng định dạng nhưng khách hàng đã bị khóa nên không được tạo đơn.
3. Dịch vụ khách hàng tạm thời không kết nối được.

Hãy thiết kế chính sách:

1. Phân loại từng trường hợp thành lỗi dữ liệu, lỗi nghiệp vụ hay lỗi hạ tầng.
2. Trường hợp nào nên trả lỗi validation, trường hợp nào nên trả kết quả từ chối nghiệp vụ?
3. Trường hợp nào có thể retry? Cần giới hạn và backoff ra sao?
4. Nếu message lỗi dữ liệu không thể xử lý, nên ghi nhận và chuyển DLQ ở thời điểm nào?
5. Nếu consumer xử lý một batch bằng `Flux.flatMap`, làm sao để lỗi của một message không vô tình kết thúc toàn bộ batch?
6. Những thông tin nào nên được ghi vào log/metric để điều tra mà không làm lộ dữ liệu nhạy cảm?
7. Nếu dịch vụ khách hàng timeout, làm sao xác định request tạo đơn có thể retry an toàn?

**Gợi ý:** message sai định dạng cần được cách ly hoặc DLQ; khách hàng bị khóa là kết quả nghiệp vụ từ chối và không retry cùng dữ liệu; lỗi kết nối tạm thời có thể retry có giới hạn nếu thao tác an toàn khi lặp. Với batch, đặt recovery bên trong mapper cho từng message và biểu diễn kết quả thành công/thất bại rõ ràng. Với thao tác ghi, dùng idempotency key hoặc đối soát trước khi retry.

## Kết luận

Lỗi dữ liệu cho biết đầu vào hoặc bản ghi không đáp ứng hợp đồng; lỗi nghiệp vụ cho biết yêu cầu không thể được chấp nhận theo quy tắc miền; lỗi hạ tầng cho biết một thành phần kỹ thuật không thể hoàn thành công việc. Dù cả ba có thể xuất hiện dưới dạng `onError`, chính sách đúng khác nhau: sửa hoặc cách ly dữ liệu, trả quyết định nghiệp vụ có ý nghĩa, hoặc retry/fallback lỗi hạ tầng có khả năng phục hồi. Trong Reactor, hãy chuẩn hóa lỗi bằng `onErrorMap`, phục hồi có điều kiện bằng `onErrorResume`, quan sát bằng `doOnError` và cách ly lỗi từng phần tử ở đúng vị trí trong `Flux`. Giữ nguyên cause, mã lỗi và ngữ cảnh cần thiết, rồi kiểm thử các nhánh bằng `StepVerifier` để pipeline dễ dự đoán và vận hành an toàn.

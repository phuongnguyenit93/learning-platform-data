# Biểu diễn lý do từ chối thay vì chỉ trả về boolean

Trong Domain-Driven Design (DDD), nhiều quyết định nghiệp vụ không chỉ cần trả lời “được” hay “không”. Khi một yêu cầu bị từ chối, người dùng, application service hoặc một quy trình khác thường cần biết **vì sao quyết định đó không được chấp nhận** để có thể sửa dữ liệu, chọn hành động tiếp theo, giải thích kết quả hoặc ghi nhận kiểm toán.

Một phương thức chỉ trả về `boolean` có thể đủ cho một điều kiện nội bộ đơn giản. Nhưng nếu kết quả là một quyết định nghiệp vụ có ý nghĩa, chẳng hạn duyệt tín dụng, áp dụng khuyến mãi, xác nhận đơn hoặc cho phép hoàn tiền, chỉ trả về `true`/`false` thường làm mất thông tin quan trọng.

Nguyên tắc là **biểu diễn kết quả và lý do từ chối bằng một kiểu dữ liệu có ngữ nghĩa**. Hãy giữ boolean cho câu hỏi thực sự chỉ cần đúng/sai; dùng kết quả có cấu trúc khi caller cần hiểu, xử lý hoặc trình bày lý do.

## 1. Hạn chế của kết quả boolean

### 1.1. Boolean cho biết kết quả nhưng không giải thích quyết định

Ví dụ:

~~~java
public boolean canApprove(CreditRequest request) {
    return request.amount().compareTo(availableCredit) <= 0
        && !accountBlocked
        && customerIsVerified;
}
~~~

Khi phương thức trả về false, caller không biết:

- Số tiền yêu cầu vượt hạn mức?
- Tài khoản đang bị khóa?
- Khách hàng chưa hoàn tất xác minh?
- Có nhiều điều kiện cùng không đạt?
- Điều kiện nào người dùng có thể khắc phục?
- Có cần nhân viên xem xét thủ công không?

Caller thường phải chạy lại từng điều kiện ở nơi khác để tạo thông báo. Khi đó quy tắc bị lặp, có nguy cơ khác nhau giữa nơi quyết định và nơi giải thích.

### 1.2. Boolean khuyến khích suy đoán nguyên nhân

~~~java
if (!policy.canApprove(request)) {
    if (request.amount().compareTo(availableCredit) > 0) {
        showMessage("Vượt hạn mức");
    } else if (accountBlocked) {
        showMessage("Tài khoản bị khóa");
    } else {
        showMessage("Không đủ điều kiện");
    }
}
~~~

Đoạn code hiển thị đang tự tái hiện logic của policy. Nếu policy thay đổi thứ tự hoặc thêm điều kiện, thông báo có thể không còn khớp với quyết định thực tế.

Một nguồn duy nhất nên chịu trách nhiệm đánh giá điều kiện và tạo lý do. Application layer chỉ nên chuyển kết quả đó đến giao diện, API hoặc quy trình tiếp theo.

### 1.3. Boolean không thể diễn đạt nhiều loại kết quả

Trong nghiệp vụ, kết quả có thể gồm:

- Được chấp thuận.
- Bị từ chối vì một lý do cụ thể.
- Bị từ chối vì nhiều lý do độc lập.
- Chưa thể quyết định vì thiếu dữ liệu.
- Cần người có thẩm quyền xem xét.
- Yêu cầu xung đột với trạng thái hiện tại.

Không phải mọi trường hợp đều nên gộp thành false. Ví dụ, “không đủ hạn mức” là một quyết định nghiệp vụ đã có kết luận; “không thể kết nối dịch vụ kiểm tra tín dụng” là lỗi kỹ thuật khiến hệ thống chưa thể kết luận.

## 2. Khi nào boolean vẫn phù hợp?

Không cần thay mọi boolean bằng một hệ thống Result phức tạp. Boolean vẫn phù hợp khi:

- Câu hỏi chỉ phục vụ một nhánh điều khiển nội bộ.
- Caller không cần giải thích hoặc xử lý khác nhau theo nguyên nhân.
- Điều kiện là một predicate đơn giản, ổn định và không có ngữ nghĩa từ chối riêng.
- Kết quả không được trình bày cho người dùng hoặc ghi nhận như một quyết định nghiệp vụ.

Ví dụ:

~~~java
public boolean isEmpty() {
    return lines.isEmpty();
}

public boolean contains(ProductId productId) {
    return lines.stream()
        .anyMatch(line -> line.productId().equals(productId));
}
~~~

Đây là các câu hỏi về thuộc tính hoặc phép kiểm tra đơn giản. Caller chỉ cần kết quả đúng/sai.

Ngược lại, nếu canRefund() được dùng để quyết định có cho phép hoàn tiền và giao diện cần hiển thị nguyên nhân từ chối, hãy cân nhắc một phương thức như evaluateRefund() trả về kết quả có ngữ nghĩa.

## 3. Biểu diễn quyết định bằng kết quả có ngữ nghĩa

### 3.1. Tách kết quả chấp thuận và từ chối

Một kiểu kết quả có thể mô tả rõ hai nhánh:

- **Accepted / Approved:** yêu cầu được chấp thuận.
- **Rejected / Denied:** yêu cầu bị từ chối và có ít nhất một lý do.

Ví dụ dùng sealed interface và record trong Java:

Ví dụ này dùng sealed interface nên cần Java 17 trở lên; record là tính năng chính thức từ Java 16.

~~~java
public final class CreditApprovalPolicy {

    public Decision evaluate(
            CreditRequest request,
            CreditProfile profile) {

        List<RejectionReason> reasons = new ArrayList<>();

        if (profile.isBlocked()) {
            reasons.add(new RejectionReason(
                RejectionCode.ACCOUNT_BLOCKED,
                Map.of()
            ));
        }

        if (request.amount().compareTo(profile.availableCredit()) > 0) {
            reasons.add(new RejectionReason(
                RejectionCode.CREDIT_LIMIT_EXCEEDED,
                Map.of(
                    "requested", request.amount().toPlainString(),
                    "available", profile.availableCredit().toPlainString()
                )
            ));
        }

        if (reasons.isEmpty()) {
            return new Approved();
        }
        return new Rejected(reasons);
    }

    public sealed interface Decision
            permits Approved, Rejected {
    }

    public record Approved() implements Decision {
    }

    public record Rejected(
            List<RejectionReason> reasons
    ) implements Decision {
        public Rejected {
            reasons = List.copyOf(reasons);
            if (reasons.isEmpty()) {
                throw new IllegalArgumentException(
                    "A rejection must have at least one reason"
                );
            }
        }
    }

    public record RejectionReason(
            RejectionCode code,
            Map<String, String> parameters
    ) {
        public RejectionReason {
            Objects.requireNonNull(code);
            parameters = Map.copyOf(parameters);
        }
    }

    public enum RejectionCode {
        ACCOUNT_BLOCKED,
        CREDIT_LIMIT_EXCEEDED,
        ORDER_ALREADY_COMPLETED
    }
}
~~~

Ví dụ giả định request và profile đã được kiểm tra hợp lệ, cùng đơn vị tiền tệ và có các accessor tương ứng. Phần quan trọng là policy tạo ra quyết định cùng lý do ngay tại nơi đánh giá quy tắc.

### 3.2. Không tạo trạng thái kết quả mâu thuẫn

Một thiết kế yếu có thể dùng:

~~~java
public record Decision(
    boolean approved,
    String rejectionReason
) {}
~~~

Kiểu này cho phép các trạng thái vô nghĩa:

- approved = true nhưng vẫn có rejectionReason.
- approved = false nhưng rejectionReason là null hoặc rỗng.
- approved = false nhưng lý do chỉ là một chuỗi tùy ý không có mã ổn định.

Sealed type hoặc các kiểu riêng như Approved và Rejected làm rõ những trạng thái hợp lệ. Constructor của Rejected có thể bảo đảm luôn có ít nhất một lý do.

Nếu dùng một record chung, cần thiết kế validation và kiểu dữ liệu để loại bỏ các tổ hợp không hợp lệ. Tuy nhiên, khi hai nhánh có cấu trúc khác nhau rõ ràng, kiểu kết quả phân biệt thường dễ đọc hơn.

### 3.3. Dùng Result/Either khi cần cả thành công và thất bại

Một số codebase dùng kiểu tổng quát như Result<T, E> hoặc Either<E, T>:

- T biểu diễn giá trị thành công.
- E biểu diễn lỗi hoặc lý do thất bại.

Ví dụ khái niệm:

~~~text
Result<ApprovedCredit, Rejection>

Success(ApprovedCredit)
Failure(Rejection)
~~~

Kiểu này hữu ích khi thao tác có thể trả về một giá trị thành công và một loại kết quả thất bại có cấu trúc. Tuy nhiên, cần xác định rõ Failure ở đây là từ chối nghiệp vụ, lỗi validation hay lỗi kỹ thuật. Không nên dùng chung một kiểu Error mơ hồ cho mọi tình huống.

Nếu dự án chưa có thư viện Result/Either, không cần thêm dependency chỉ để áp dụng mẫu. Sealed interface, record hoặc một class kết quả nhỏ có thể đủ.

## 4. Mô hình hóa lý do từ chối

### 4.1. Dùng reason code ổn định

Lý do từ chối nên có mã định danh ổn định, chẳng hạn:

| Mã | Ý nghĩa nghiệp vụ | Hành động có thể thực hiện |
|---|---|---|
| ACCOUNT_BLOCKED | Tài khoản không đủ điều kiện giao dịch | Liên hệ bộ phận hỗ trợ nếu được phép |
| CREDIT_LIMIT_EXCEEDED | Giá trị yêu cầu vượt hạn mức khả dụng | Giảm số tiền hoặc xin tăng hạn mức |
| CUSTOMER_NOT_VERIFIED | Hồ sơ chưa hoàn tất xác minh | Hoàn tất quy trình xác minh |
| PROMOTION_EXPIRED | Khuyến mãi đã hết hiệu lực | Chọn chương trình còn hiệu lực |
| MINIMUM_ORDER_NOT_MET | Đơn chưa đạt giá trị tối thiểu | Bổ sung mặt hàng phù hợp |
| REFUND_WINDOW_CLOSED | Yêu cầu nằm ngoài thời hạn hoàn tiền | Liên hệ hỗ trợ nếu chính sách có ngoại lệ |

Reason code giúp các lớp khác xử lý theo mã thay vì so sánh chuỗi thông báo. Nó cũng giúp thống kê, theo dõi thay đổi chính sách và giữ hợp đồng ổn định hơn.

### 4.2. Tách mã lý do khỏi thông báo hiển thị

Không nên lưu câu thông báo đã dịch trực tiếp trong domain model:

~~~java
new RejectionReason("Bạn đã vượt quá hạn mức tín dụng");
~~~

Thông báo này phụ thuộc ngôn ngữ, kênh giao tiếp và cách diễn đạt của sản phẩm. Domain nên trả về mã cùng dữ liệu cần thiết:

~~~java
new RejectionReason(
    RejectionCode.CREDIT_LIMIT_EXCEEDED,
    Map.of(
        "requested", "15000000",
        "available", "10000000"
    )
);
~~~

Presentation layer hoặc adapter có thể ánh xạ mã sang thông báo tiếng Việt, tiếng Anh hoặc ngôn ngữ khác. API có thể trả reason code và parameters; giao diện dùng chúng để hiển thị nội dung phù hợp.

### 4.3. Parameters phải có ngữ nghĩa và giới hạn

Parameters bổ sung dữ kiện để giải thích lý do, ví dụ:

- Số tiền yêu cầu.
- Hạn mức còn lại.
- Ngày hết hiệu lực.
- Giá trị tối thiểu cần đạt.
- Mã sản phẩm không đủ điều kiện.

Chỉ đưa vào parameters dữ liệu cần thiết cho người nhận kết quả. Tránh chứa thông tin cá nhân nhạy cảm, bí mật chống gian lận, token, dữ liệu xác thực hoặc toàn bộ object nội bộ.

Nếu lý do phụ thuộc vào một giá trị, hãy xác định đơn vị, loại tiền, múi giờ hoặc thời điểm áp dụng. Một số 100 không có ngữ nghĩa nếu không biết đó là tiền, phần trăm hay số lượng.

### 4.4. Không dùng chuỗi tự do làm hợp đồng chính

Chuỗi như "Not enough credit" dễ viết nhưng khó quản lý:

- Cách viết có thể thay đổi mà không báo cho consumer.
- Consumer phải phân tích văn bản để quyết định hành động.
- Dịch thuật làm chuỗi khác nhau theo ngôn ngữ.
- Khó thống kê các nhóm lý do một cách nhất quán.

Có thể bổ sung mô tả cho log hoặc debug, nhưng reason code và dữ liệu có cấu trúc nên là hợp đồng chính.

## 5. Một lý do hay nhiều lý do?

### 5.1. Trả về một lý do khi chỉ có một nguyên nhân có ý nghĩa

Một số quyết định có thứ tự kiểm tra hoặc nguyên nhân chính:

- Mã khuyến mãi không tồn tại.
- Yêu cầu đã hết thời hạn.
- Trạng thái đơn không cho phép hủy.

Trong trường hợp này, trả về lý do đầu tiên có thể rõ ràng và tránh tính toán không cần thiết.

Ví dụ:

~~~java
public Optional<RejectionReason> evaluateCancellation(Order order) {
    if (order.status() == OrderStatus.COMPLETED) {
        return Optional.of(new RejectionReason(
            RejectionCode.ORDER_ALREADY_COMPLETED,
            Map.of()
        ));
    }
    return Optional.empty();
}
~~~

Ví dụ giả định kiểu RejectionReason và RejectionCode đã được định nghĩa. Optional thể hiện rõ rằng việc đánh giá có thể không tìm thấy lý do từ chối.

### 5.2. Trả về nhiều lý do khi các điều kiện độc lập

Với một form đăng ký hoặc hồ sơ xét duyệt, người dùng thường muốn biết tất cả lỗi có thể sửa cùng lúc:

- Thiếu giấy tờ A.
- Địa chỉ không đầy đủ.
- Ngày bắt đầu không hợp lệ.
- Chưa chấp thuận điều khoản.

Nếu chỉ trả về lỗi đầu tiên, người dùng phải gửi lại nhiều lần. Một tập hợp lý do có thể cải thiện trải nghiệm và giảm số vòng tương tác.

~~~java
List<RejectionReason> reasons = new ArrayList<>();

if (!application.hasIdentityDocument()) {
    reasons.add(reason(IDENTITY_DOCUMENT_REQUIRED));
}
if (!application.hasValidAddress()) {
    reasons.add(reason(ADDRESS_INVALID));
}
if (!application.termsAccepted()) {
    reasons.add(reason(TERMS_NOT_ACCEPTED));
}

return reasons.isEmpty()
    ? new Accepted()
    : new Rejected(reasons);
~~~

Đây là phần thân minh họa của một policy; các mã IDENTITY_DOCUMENT_REQUIRED, ADDRESS_INVALID, TERMS_NOT_ACCEPTED và hàm reason() cần được định nghĩa trong mô hình tương ứng. Chỉ nên gom các điều kiện vào cùng danh sách khi chúng độc lập và có thể đánh giá an toàn.

### 5.3. Không phải lúc nào cũng nên trả về tất cả

Có những lý do:

- Phụ thuộc vào điều kiện trước đó nên không có ý nghĩa nếu điều kiện nền chưa đạt.
- Đòi hỏi truy vấn tốn kém hoặc gọi hệ thống bên ngoài.
- Không an toàn khi tiết lộ cho người dùng.
- Có thể tiết lộ quy tắc chống gian lận hoặc thông tin nội bộ.
- Có thứ tự ưu tiên theo chính sách.

Ví dụ, nếu tài khoản bị khóa vì điều tra gian lận, API công khai có thể chỉ trả mã chung REQUEST_NOT_ALLOWED. Chi tiết nội bộ được ghi trong audit log hoặc chỉ hiển thị cho nhân viên có thẩm quyền.

Quyết định trả một hay nhiều lý do phải dựa trên mục tiêu nghiệp vụ, chi phí đánh giá và quyền được biết của người nhận.

## 6. Phân biệt từ chối nghiệp vụ, lỗi validation và lỗi kỹ thuật

Không phải mọi thất bại đều là một lý do từ chối nghiệp vụ.

| Loại kết quả | Ý nghĩa | Ví dụ | Cách xử lý thường gặp |
|---|---|---|---|
| Business rejection | Hệ thống đã đánh giá và quyết định không chấp thuận | Vượt hạn mức, đơn hết thời hạn hủy | Trả quyết định cùng reason code |
| Input validation failure | Dữ liệu đầu vào không đáp ứng cấu trúc hoặc định dạng | Thiếu mã đơn, số lượng âm | Trả lỗi trường hoặc lỗi yêu cầu |
| Domain invariant violation | Một hành vi được gọi trong trạng thái không hợp lệ | Confirm một Order đã Completed | Từ chối hành vi; có thể là lỗi lập trình hoặc xung đột luồng |
| Technical failure | Hệ thống không thể hoàn tất đánh giá do hạ tầng hoặc phụ thuộc lỗi | Database timeout, không gọi được dịch vụ tín dụng | Retry, fallback, báo lỗi hệ thống |
| Concurrency conflict | Trạng thái đã thay đổi bởi một giao dịch khác | Đơn bị hủy trong lúc yêu cầu xác nhận | Tải lại và đánh giá lại hoặc trả conflict |

### 6.1. Từ chối nghiệp vụ thường là kết quả bình thường

Nếu khách hàng yêu cầu hoàn tiền sau thời hạn cho phép và policy trả về REFUND_WINDOW_CLOSED, hệ thống đã thực hiện đúng quyết định nghiệp vụ. Đây không nhất thiết là exception.

Application layer có thể nhận kết quả, trả thông tin phù hợp và cho phép người dùng chọn hành động khác.

### 6.2. Exception dành cho tình huống bất thường hoặc vi phạm hợp đồng

Exception có thể phù hợp khi:

- Một invariant nội bộ bị phá vỡ do lỗi lập trình.
- Hệ thống không thể truy cập dependency bắt buộc.
- Persistence hoặc message broker gặp lỗi.
- Một thao tác được gọi trong trạng thái mà hợp đồng không cho phép và đây là lỗi của caller.

Tuy nhiên, không có luật rằng mọi business rejection đều không được dùng exception. Quyết định phụ thuộc vào hợp đồng của use case. Nếu từ chối là kết quả dự kiến mà caller cần xử lý, kiểu kết quả tường minh thường giúp luồng dễ đọc hơn.

### 6.3. Không biến lỗi kỹ thuật thành từ chối nghiệp vụ

Nếu dịch vụ kiểm tra tín dụng timeout, không nên trả CREDIT_LIMIT_EXCEEDED. Hệ thống chưa biết hạn mức có đủ hay không.

Có thể biểu diễn kết quả kiểm tra bằng các nhánh riêng:

- Approved.
- Rejected với lý do.
- UnableToEvaluate hoặc lỗi kỹ thuật được chuyển qua application boundary.

Điều này tránh đưa ra quyết định sai và giúp hệ thống retry hoặc yêu cầu xử lý lại đúng cách.

## 7. Policy và Specification

Trong DDD, Policy và Specification có thể giúp tổ chức các quy tắc, nhưng cần phân biệt mục tiêu sử dụng.

### 7.1. Policy đưa ra quyết định

Policy diễn đạt một quy tắc hoặc chính sách quyết định điều gì được phép xảy ra.

Ví dụ:

- Chính sách duyệt tín dụng.
- Chính sách hoàn tiền.
- Chính sách áp dụng khuyến mãi.
- Chính sách xác nhận đơn.

Khi caller cần biết lý do từ chối, policy nên trả về một kết quả có ngữ nghĩa thay vì chỉ trả boolean.

### 7.2. Specification mô tả điều kiện

Specification đóng gói một điều kiện có thể kiểm tra trên một đối tượng. Nó thường có dạng isSatisfiedBy(candidate) và có thể kết hợp các điều kiện bằng AND, OR hoặc NOT.

~~~java
public interface Specification<T> {
    boolean isSatisfiedBy(T candidate);
}
~~~

Boolean phù hợp khi Specification chỉ cần trả lời một predicate, chẳng hạn lọc các đơn có tổng tiền trên một ngưỡng.

Nếu cần giải thích vì sao candidate không đạt, có thể mở rộng bằng một API đánh giá:

~~~java
public interface ExplainableSpecification<T> {
    Evaluation evaluate(T candidate);
}
~~~

Trong đó Evaluation có thể chứa kết quả đạt/không đạt và danh sách lý do. Không phải Specification nào cũng cần giải thích; chỉ bổ sung khi caller có nhu cầu nghiệp vụ cụ thể.

### 7.3. Tránh để Specification trở thành nơi phát sinh side effect

Một Specification dùng để đánh giá điều kiện nên có hành vi dễ dự đoán. Tránh để việc gọi isSatisfiedBy tự động ghi database, gửi email, khóa tài khoản hoặc thay đổi trạng thái.

Nếu quyết định cần hành động, hãy để application service hoặc domain behavior thực hiện sau khi nhận kết quả.

## 8. Đặt trách nhiệm tạo lý do ở đúng nơi

### Domain model hoặc Policy

Nơi sở hữu quy tắc phải xác định điều kiện và reason code tương ứng. Đây là nguồn chân lý cho ý nghĩa quyết định.

### Application layer

Application layer điều phối use case:

- Gọi policy hoặc hành vi miền.
- Quyết định tiếp tục, dừng, yêu cầu bổ sung hoặc chuyển phê duyệt.
- Chuyển kết quả qua output port hoặc API adapter.
- Không tự tính lại lý do bằng cách sao chép điều kiện.

### Presentation/API adapter

Adapter chịu trách nhiệm:

- Chuyển reason code sang thông báo phù hợp ngôn ngữ.
- Chuyển kết quả sang HTTP status hoặc response schema.
- Ẩn lý do nhạy cảm theo quyền truy cập.
- Định dạng số tiền, ngày tháng và dữ liệu theo locale.

### Logging và audit

Log và audit phục vụ mục đích khác nhau:

- Log hỗ trợ chẩn đoán vận hành.
- Audit ghi lại quyết định có ý nghĩa, thời điểm, chủ thể và căn cứ theo chính sách lưu trữ.

Không nên dùng một chuỗi log tự do làm nguồn dữ liệu duy nhất để giải thích quyết định đã xảy ra.

## 9. Đưa lý do từ chối qua API và giao diện

Domain model không nên phụ thuộc HTTP, nhưng API có thể chuyển đổi kết quả thành hợp đồng phù hợp.

Ví dụ response:

~~~json
{
  "decision": "REJECTED",
  "reasons": [
    {
      "code": "CREDIT_LIMIT_EXCEEDED",
      "parameters": {
        "requested": "15000000",
        "available": "10000000"
      }
    }
  ]
}
~~~

Giao diện có thể dùng mã để hiển thị thông báo đã dịch và hướng dẫn bước tiếp theo. Nếu client cần xử lý tự động, reason code phải ổn định và được tài liệu hóa.

### 9.1. Ánh xạ HTTP status theo hợp đồng API

Không có một status code duy nhất cho mọi business rejection. Có thể cân nhắc:

| Tình huống | HTTP status có thể dùng | Lưu ý |
|---|---:|---|
| Dữ liệu request không hợp lệ | 400 hoặc 422 | Phụ thuộc quy ước API |
| Yêu cầu xung đột với trạng thái hiện tại | 409 | Ví dụ đơn đã hoàn tất nên không thể hủy |
| Không có quyền thực hiện | 403 | Không tiết lộ thông tin vượt quyền |
| Tài nguyên không tồn tại hoặc không được phép biết | 404 | Có thể dùng để tránh lộ sự tồn tại |
| Lỗi dependency hoặc hệ thống | 5xx phù hợp | Không biến timeout thành business rejection |

Một quyết định nghiệp vụ bị từ chối không nhất thiết là HTTP 4xx trong mọi API. Hãy thiết kế status code, response body và reason code như một hợp đồng nhất quán với client.

### 9.2. Thông báo cho người dùng phải có thể hành động

Thông báo tốt nên giúp người dùng hiểu:

- Điều gì không được chấp thuận?
- Lý do nào họ được phép biết?
- Họ có thể làm gì tiếp theo?
- Có cần liên hệ nhân viên hay chờ xử lý không?

Ví dụ, MINIMUM_ORDER_NOT_MET có thể hiển thị giá trị tối thiểu còn thiếu. ACCOUNT_BLOCKED có thể chỉ hướng dẫn liên hệ hỗ trợ thay vì tiết lộ chi tiết bảo mật.

Không nên hiển thị stack trace, tên bảng database, tên class, câu SQL hoặc nội dung exception kỹ thuật cho người dùng cuối.

## 10. Lưu vết và giải thích quyết định

Với các quyết định quan trọng như tín dụng, bảo hiểm, hoàn tiền hoặc phê duyệt, chỉ lưu reason code có thể chưa đủ. Có thể cần ghi nhận:

- ID của yêu cầu hoặc đối tượng được đánh giá.
- Thời điểm và phiên bản policy.
- Chủ thể hoặc hệ thống yêu cầu quyết định.
- Kết quả chấp thuận/từ chối.
- Các reason code được phép lưu.
- Dữ kiện đầu vào cần thiết để giải thích quyết định.
- Người hoặc quy trình đã thực hiện bước tiếp theo.

Không lưu tràn lan toàn bộ dữ liệu cá nhân hoặc bí mật chỉ để phục vụ audit. Cần tuân thủ quyền truy cập, thời hạn lưu trữ và chính sách bảo vệ dữ liệu.

Nếu policy thay đổi theo thời gian, ghi phiên bản hoặc định danh chính sách giúp giải thích vì sao một yêu cầu cũ được xử lý theo quy tắc tại thời điểm đó.

## 11. Ví dụ: đánh giá điều kiện hoàn tiền

Giả sử chính sách hoàn tiền có các điều kiện:

- Đơn đã được thanh toán.
- Đơn không ở trạng thái bị khóa xử lý.
- Yêu cầu nằm trong thời hạn hoàn tiền.
- Số tiền yêu cầu không vượt quá số tiền còn có thể hoàn.

### 11.1. Cách chỉ trả boolean

~~~java
public boolean canRefund(Order order, RefundRequest request) {
    return order.isPaid()
        && !order.isUnderReview()
        && !request.requestedAt().isAfter(order.refundDeadline())
        && request.amount().compareTo(order.refundableAmount()) <= 0;
}
~~~

Khi kết quả là false, caller không biết cần thông báo điều gì hoặc có thể cho phép nhân viên xem xét ngoại lệ không.

### 11.2. Cách trả quyết định có lý do

Kiểu RefundDecision có thể được định nghĩa theo cùng cấu trúc phân biệt hai nhánh như Decision ở ví dụ trước. Hàm reason tạo RejectionReason từ mã và parameters tương ứng:

~~~java
public RefundDecision evaluate(
        Order order,
        RefundRequest request) {

    List<RejectionReason> reasons = new ArrayList<>();

    if (!order.isPaid()) {
        reasons.add(reason(NOT_PAID));
    }
    if (order.isUnderReview()) {
        reasons.add(reason(ORDER_UNDER_REVIEW));
    }
    if (request.requestedAt().isAfter(order.refundDeadline())) {
        reasons.add(reason(REFUND_WINDOW_CLOSED));
    }
    if (request.amount().compareTo(order.refundableAmount()) > 0) {
        reasons.add(reason(AMOUNT_EXCEEDS_REFUNDABLE_BALANCE));
    }

    if (reasons.isEmpty()) {
        return new RefundAllowed();
    }
    return new RefundRejected(reasons);
}
~~~

Hai ví dụ dùng cùng quy tắc thời hạn: yêu cầu tại đúng thời điểm deadline vẫn được chấp nhận. Ví dụ này giả định các điều kiện có thể đánh giá độc lập. Trong thực tế, nếu đơn chưa thanh toán thì việc kiểm tra số tiền có thể không còn ý nghĩa; policy có thể chọn dừng sớm hoặc chỉ trả các lý do người dùng có thể xử lý.

### 11.3. Application layer xử lý kết quả

Application service nhận kết quả và quyết định bước tiếp theo:

- Nếu được phép, tạo lệnh hoàn tiền và lưu theo transaction phù hợp.
- Nếu bị từ chối, trả reason code cho adapter.
- Nếu cần nhân viên xem xét, tạo một yêu cầu review riêng theo chính sách.
- Nếu không thể đánh giá do lỗi dịch vụ thanh toán, trả lỗi kỹ thuật và áp dụng retry/fallback.

Policy chỉ đánh giá điều kiện. Việc gọi cổng thanh toán, lưu yêu cầu hoàn tiền hoặc gửi thông báo thuộc các thành phần điều phối và tích hợp tương ứng.

## 12. Những lỗi thiết kế thường gặp

**Trả boolean rồi kiểm tra lại ở UI.** Logic bị lặp và thông báo có thể không khớp với quyết định. Hãy để policy trả về lý do ngay khi đánh giá.

**Dùng exception cho mọi trường hợp từ chối.** Luồng điều khiển trở nên khó đọc khi từ chối là kết quả dự kiến. Hãy cân nhắc kiểu kết quả tường minh cho business rejection.

**Gộp lỗi kỹ thuật và từ chối nghiệp vụ.** Timeout không có nghĩa là khách hàng không đủ điều kiện. Giữ các loại kết quả riêng để retry và báo cáo chính xác.

**Chỉ trả chuỗi thông báo.** Chuỗi không ổn định, khó dịch và khó xử lý tự động. Dùng reason code cùng parameters có ngữ nghĩa.

**Trả mọi lý do nội bộ cho người dùng.** Điều đó có thể tiết lộ quy tắc bảo mật, chống gian lận hoặc dữ liệu riêng tư. Áp dụng chính sách hiển thị theo quyền.

**Thu thập quá nhiều lý do.** Một số điều kiện phụ thuộc nhau hoặc tốn kém. Chỉ đánh giá và trả các lý do có ích cho người nhận.

**Cho phép kết quả từ chối không có lý do.** Kiểu dữ liệu phải bảo vệ invariant rằng Rejected có ít nhất một reason.

**Dùng mã lý do không ổn định.** Đổi tên mã tùy tiện có thể phá client, báo cáo và dữ liệu lịch sử. Quản lý mã như một phần hợp đồng.

**Đặt logic policy trong controller.** Controller không nên tự tính lại điều kiện nghiệp vụ. Hãy gọi policy hoặc domain behavior.

**Ghi audit bằng câu log tự do.** Khi cần giải thích quyết định lịch sử, hãy lưu dữ liệu có cấu trúc, phiên bản policy và thời điểm phù hợp.

## 13. Quy trình thiết kế kết quả từ chối

1. Xác định quyết định nghiệp vụ cần đưa ra.
2. Liệt kê các điều kiện chấp thuận và phạm vi sở hữu của từng điều kiện.
3. Phân biệt điều kiện có thể đánh giá độc lập với điều kiện phụ thuộc thứ tự.
4. Xác định người hoặc hệ thống sẽ nhận kết quả.
5. Chọn trả một lý do hay nhiều lý do theo nhu cầu hành động và bảo mật.
6. Định nghĩa reason code ổn định và parameters có ngữ nghĩa.
7. Tách business rejection khỏi input validation, invariant violation và technical failure.
8. Tạo kiểu kết quả bảo đảm không có tổ hợp trạng thái mâu thuẫn.
9. Để application layer điều phối, adapter chuyển mã thành thông báo hoặc API response.
10. Kiểm thử cả quyết định, lý do, thứ tự ưu tiên và quyền được xem lý do.

~~~mermaid
flowchart TD
    A["Yêu cầu cần đánh giá"] --> B["Policy / Specification kiểm tra điều kiện"]
    B --> C{"Đủ điều kiện?"}
    C -->|Có| D["Accepted / Approved"]
    C -->|Không| E["Tạo reason code và parameters"]
    E --> F["Kiểm tra quyền được biết và số lý do cần trả"]
    F --> G["Rejected với lý do"]
    D --> H["Application layer điều phối"]
    G --> H
    H --> I["API / UI / Workflow / Audit"]
~~~

## 14. Checklist tự kiểm tra

**Về quyết định**

- Kết quả boolean có thực sự đủ cho mọi caller không?
- Quyết định có ý nghĩa nghiệp vụ và cần được giải thích không?
- Các điều kiện được đánh giá ở đúng nơi sở hữu quy tắc chưa?
- Có phân biệt kết quả từ chối với việc không thể đánh giá không?

**Về lý do**

- Mỗi lý do có reason code ổn định chưa?
- Code có ý nghĩa nghiệp vụ rõ và không phụ thuộc ngôn ngữ hiển thị không?
- Parameters có tên, đơn vị và kiểu giá trị rõ ràng không?
- Có tránh dữ liệu nhạy cảm hoặc thông tin nội bộ không được tiết lộ không?
- Rejected có luôn chứa ít nhất một lý do không?
- Có quyết định rõ trả lý do đầu tiên hay nhiều lý do không?

**Về kiến trúc**

- Policy hoặc Specification có tạo kết quả thay vì để UI suy đoán không?
- Application layer có điều phối mà không sao chép điều kiện không?
- Adapter có chịu trách nhiệm dịch và ánh xạ API không?
- Lỗi kỹ thuật có được giữ riêng để xử lý retry/fallback không?
- Audit có lưu dữ liệu có cấu trúc và phiên bản policy khi cần không?

**Về kiểm thử**

- Mỗi điều kiện từ chối có test cho reason code tương ứng không?
- Khi nhiều điều kiện cùng sai, danh sách lý do có đúng không?
- Những lý do nhạy cảm có bị ẩn với caller không đủ quyền không?
- Thay đổi policy có làm thay đổi reason code hoặc hợp đồng một cách có kiểm soát không?

Biểu diễn lý do từ chối giúp mô hình nghiệp vụ nói rõ quyết định của nó, giảm việc lặp quy tắc ở giao diện và tạo cơ sở cho quy trình xử lý tiếp theo. Boolean vẫn hữu ích cho các predicate đơn giản; khi một quyết định cần được hiểu, giải thích và hành động, hãy trả về kết quả có ngữ nghĩa cùng lý do có cấu trúc.

# Rút gọn phần mô hình không phục vụ quyết định cần thiết

Một Domain Model tốt không phải là bản sao đầy đủ của thế giới nghiệp vụ. Nó là mô hình có chọn lọc, giúp hệ thống diễn đạt và thực thi những quyết định mà một Bounded Context chịu trách nhiệm. Khi mô hình chứa quá nhiều thuộc tính, quan hệ, trạng thái và abstraction không ảnh hưởng đến quyết định nghiệp vụ, người đọc khó nhận ra điều gì thực sự quan trọng. Mỗi thay đổi cũng trở nên tốn kém vì nhiều thành phần phải được cập nhật dù quy tắc cốt lõi không đổi.

Trong Domain-Driven Design (DDD), rút gọn mô hình không có nghĩa là làm nghèo hiểu biết nghiệp vụ hoặc xóa dữ liệu tùy tiện. Đó là quá trình xác định quyết định nào cần được hỗ trợ, tìm ra khái niệm và quy tắc thực sự tham gia vào quyết định ấy, rồi loại bỏ hoặc chuyển những chi tiết không thuộc trách nhiệm của mô hình. Mô hình có thể nhỏ hơn về số lượng khái niệm nhưng sâu hơn về ngữ nghĩa: mỗi khái niệm có vai trò rõ, hành vi có tên đúng và bất biến được bảo vệ tại nơi phù hợp.

## 1. Domain Model tồn tại để hỗ trợ quyết định nghiệp vụ

Một hệ thống có thể lưu rất nhiều dữ liệu về một khách hàng, đơn hàng hoặc khoản vay. Nhưng không phải dữ liệu nào cũng cần xuất hiện trong Domain Model của mọi Bounded Context.

Hãy xét một hệ thống xét duyệt tín dụng. Quyết định cần đưa ra là:

> Có cấp khoản tín dụng này cho người nộp đơn hay không, với hạn mức và điều kiện nào?

Để hỗ trợ quyết định đó, mô hình có thể cần:

- Thu nhập đủ điều kiện đã được xác minh.
- Nghĩa vụ nợ hiện tại.
- Lịch sử thanh toán có liên quan.
- Mức rủi ro theo chính sách tín dụng.
- Hạn mức tối đa được phép cấp.
- Trạng thái và kết quả thẩm định.

Màn hình của nhân viên có thể cần thêm ảnh đại diện, ngôn ngữ ưa thích, lịch sử đăng nhập, địa chỉ nhận thư và nhiều dữ liệu khác. Những dữ liệu này có thể quan trọng với các use case khác, nhưng không nhất thiết thuộc mô hình quyết định cấp tín dụng.

Nếu đưa tất cả vào một Applicant Aggregate chỉ vì chúng cùng nói về một người, mô hình sẽ trở thành một kho dữ liệu lớn thay vì một mô hình có trách nhiệm rõ.

### 1.1. Câu hỏi kiểm tra một khái niệm

Với mỗi khái niệm, thuộc tính hoặc quan hệ trong mô hình, hãy hỏi:

1. Nó tham gia vào quyết định nghiệp vụ nào?
2. Nó bảo vệ bất biến nào?
3. Nó giúp diễn đạt một quy tắc hoặc chính sách nào?
4. Nếu bỏ nó khỏi mô hình này, quyết định có thay đổi hoặc mất khả năng giải thích không?
5. Nếu vẫn cần dữ liệu đó, nó thuộc Bounded Context, read model hay hệ thống lưu trữ nào?

Nếu không thể chỉ ra một vai trò cụ thể, khái niệm đó cần được xem xét. Nó có thể là dữ liệu chỉ phục vụ giao diện, chi tiết persistence, metadata kỹ thuật hoặc một khái niệm chưa được hiểu đúng.

### 1.2. Mô hình không phải sơ đồ dữ liệu của toàn doanh nghiệp

Một người có thể được mô tả khác nhau trong các Bounded Context:

| Bounded Context | Khái niệm trung tâm | Câu hỏi cần hỗ trợ |
|---|---|---|
| Customer Care | Customer Profile | Nhân viên cần thông tin gì để hỗ trợ khách? |
| Credit Assessment | Credit Applicant | Hồ sơ có đáp ứng chính sách tín dụng không? |
| Billing | Bill-to Party | Ai chịu trách nhiệm thanh toán? |
| Identity | Account / Principal | Danh tính này có được xác thực không? |

Các context có thể chia sẻ một định danh tham chiếu, nhưng không cần chia sẻ một Entity khổng lồ với mọi thuộc tính. Mỗi mô hình chọn những khái niệm phù hợp với trách nhiệm của nó.

## 2. Phân biệt mô hình sâu với mô hình rộng

Mô hình rộng có thể chứa nhiều lớp, trường và quan hệ nhưng vẫn không thể hiện được quy tắc quan trọng. Mô hình sâu tập trung vào một số khái niệm có ý nghĩa, mỗi khái niệm giúp diễn đạt nhiều quyết định liên quan.

| Mô hình rộng nhưng nông | Mô hình sâu và tập trung |
|---|---|
| Nhiều DTO và Entity phản ánh mọi cột dữ liệu | Một số khái niệm miền có trách nhiệm rõ |
| Service tự kiểm tra và thay đổi nhiều field | Hành vi nằm trong Entity/Aggregate hoặc Domain Service |
| Một trạng thái có thể được gán tùy ý | State transition được bảo vệ bởi bất biến |
| Quan hệ được tạo vì dữ liệu có liên quan | Quan hệ tồn tại vì quy tắc cần chúng |
| Mọi màn hình dùng chung một model | Read model được thiết kế theo nhu cầu truy vấn |
| Thêm abstraction để biểu diễn mọi biến thể | Abstraction chỉ xuất hiện khi có ý nghĩa nghiệp vụ |

Độ sâu không đo bằng số lượng pattern hoặc số tầng class. Một Value Object nhỏ như CreditLimit có thể làm mô hình sâu hơn nếu nó gom được ý nghĩa, đơn vị và quy tắc hạn mức vào một khái niệm rõ ràng.

## 3. Bắt đầu từ quyết định, không bắt đầu từ danh sách field

Khi nhận yêu cầu xây dựng một tính năng, cách dễ làm nhưng dễ dẫn đến mô hình rộng là hỏi: “Màn hình cần những trường nào?” Câu hỏi này hữu ích cho API hoặc read model, nhưng chưa đủ để thiết kế Domain Model.

Hãy bắt đầu bằng việc mô tả quyết định:

- Ai đưa ra quyết định?
- Quyết định được đưa ra trong tình huống nào?
- Những lựa chọn hợp lệ là gì?
- Dữ kiện nào có thể làm thay đổi kết quả?
- Quy tắc nào giới hạn lựa chọn?
- Hệ thống phải giải thích hoặc lưu lại điều gì sau quyết định?

Ví dụ với xét duyệt tín dụng:

| Quyết định | Dữ kiện có ảnh hưởng |
|---|---|
| Hồ sơ có đủ điều kiện sơ bộ không? | Tuổi theo quy định, loại sản phẩm, tình trạng xác minh |
| Khả năng trả nợ có đạt ngưỡng không? | Thu nhập đủ điều kiện, nghĩa vụ nợ, chi phí sinh hoạt theo chính sách |
| Mức rủi ro thuộc nhóm nào? | Lịch sử thanh toán, dữ liệu tín dụng được phép sử dụng, mô hình rủi ro |
| Hạn mức tối đa là bao nhiêu? | Khả năng trả nợ, chính sách sản phẩm, giới hạn pháp lý |
| Hồ sơ được duyệt hay từ chối? | Kết quả các bước và quyền phê duyệt |

Một field chỉ nên nằm trong mô hình quyết định nếu nó có ý nghĩa với một hoặc nhiều quy tắc này, hoặc cần thiết để giải thích, kiểm toán và tái dựng quyết định.

## 4. Truy vết từ quyết định đến khái niệm

Một kỹ thuật hữu ích là tạo bảng truy vết:

| Quyết định | Quy tắc | Khái niệm miền | Hành vi |
|---|---|---|---|
| Tính khả năng trả nợ | Nghĩa vụ định kỳ phải được tính theo chính sách | Income, DebtObligation, RepaymentCapacity | calculateCapacity() |
| Xác định hạn mức | Không vượt giới hạn sản phẩm và khả năng trả nợ | CreditLimit, ProductPolicy | determineLimit() |
| Phê duyệt hồ sơ | Chỉ hồ sơ đủ điều kiện và đúng quyền mới được duyệt | CreditApplication, ApprovalAuthority | approve() |
| Từ chối hồ sơ | Phải có mã lý do hợp lệ | Decision, RejectionReason | reject() |

Nếu một thuộc tính không thể liên kết với quyết định, quy tắc hoặc yêu cầu lưu vết nào, có thể nó không thuộc mô hình này.

Không phải mọi khái niệm đều cần một class riêng. Một giá trị đơn giản có thể là field nếu nó không có ngữ nghĩa hoặc hành vi riêng. Ngược lại, một khái niệm có quy tắc và được dùng ở nhiều nơi có thể xứng đáng trở thành Value Object hoặc Domain Service.

## 5. Ví dụ trước khi rút gọn: Applicant Aggregate ôm quá nhiều dữ liệu

Giả sử ban đầu hệ thống tạo một Applicant class để chứa tất cả dữ liệu tìm thấy trong các hệ thống khác nhau:

~~~java
public class Applicant {
    private ApplicantId id;
    private String fullName;
    private String preferredName;
    private String avatarUrl;
    private String language;
    private String email;
    private String phone;
    private Address homeAddress;
    private Address mailingAddress;
    private List<LoginRecord> loginHistory;
    private List<SupportTicket> supportTickets;
    private List<EmploymentRecord> employmentHistory;
    private List<IncomeRecord> incomeRecords;
    private List<DebtRecord> debtRecords;
    private List<PaymentRecord> paymentHistory;
    private CreditScore creditScore;
    private CreditStatus status;
    private BigDecimal requestedAmount;
    private BigDecimal approvedAmount;
    private Instant lastLoginAt;
    private Instant createdAt;
    private Instant updatedAt;
}
~~~

Class này trộn lẫn dữ liệu hồ sơ khách hàng, định danh, chăm sóc khách hàng, lịch sử đăng nhập, việc làm, thu nhập, nghĩa vụ nợ và quyết định tín dụng. Nó có thể khiến mọi thay đổi ở một context ảnh hưởng đến những context khác.

Vấn đề không nằm ở việc class có nhiều field theo một con số tuyệt đối. Vấn đề là các field phục vụ những mục tiêu khác nhau và không cùng một tập bất biến.

Ví dụ:

- Đổi ngôn ngữ hiển thị không nên làm thay đổi logic xét duyệt.
- Thêm một support ticket không nên yêu cầu tải toàn bộ lịch sử tín dụng.
- Cập nhật ảnh đại diện không nên ghi lại Aggregate đang xét duyệt.
- Thay đổi nghĩa vụ nợ có thể ảnh hưởng khả năng trả nợ và cần được xác minh theo quy tắc tín dụng.

## 6. Rút gọn mô hình theo trách nhiệm

Thay vì giữ một Applicant chứa mọi thứ, hãy xác định mô hình nào sở hữu quyết định tín dụng. Một mô hình minh họa có thể là:

~~~java
public final class CreditApplication {
    private final CreditApplicationId id;
    private final ApplicantReference applicant;
    private final RequestedCredit requestedCredit;
    private final VerifiedFinancialPosition financialPosition;
    private CreditDecision decision;

    public CreditDecision assess(CreditPolicy policy) {
        if (decision != null) {
            throw new ApplicationAlreadyDecided();
        }

        RepaymentCapacity capacity =
                financialPosition.calculateCapacity(policy);

        decision = policy.decide(requestedCredit, capacity);
        return decision;
    }
}
~~~

Mô hình này tập trung vào hồ sơ và quyết định tín dụng. ApplicantReference có thể chỉ chứa định danh cần thiết để liên kết với context sở hữu hồ sơ khách hàng. Thông tin trình bày như avatar hoặc ngôn ngữ không cần nằm trong Aggregate này.

Đây là ví dụ khái niệm. Trong hệ thống thật, cần quyết định CreditPolicy là Domain Service, Policy object hay một collaborator được truyền vào; cũng cần xác định việc quyết định có thuộc vòng đời Aggregate hay một use case khác.

### 6.1. Những gì được giữ lại?

- Định danh hồ sơ.
- Tham chiếu đến người nộp đơn.
- Khoản tín dụng được yêu cầu.
- Vị thế tài chính đã xác minh.
- Quyết định và lý do.

### 6.2. Những gì được chuyển ra?

- Avatar và ngôn ngữ: Customer Profile hoặc read model.
- Lịch sử đăng nhập: Identity/Security context.
- Support ticket: Customer Care context.
- Thông tin hiển thị cho danh sách hồ sơ: query projection.
- Chi tiết lưu trữ như createdAt/updatedAt kỹ thuật: persistence metadata nếu không có ý nghĩa nghiệp vụ.

### 6.3. Những gì không được xóa khỏi hệ thống?

Rút gọn Aggregate không đồng nghĩa xóa dữ liệu nguồn. Lịch sử đăng nhập có thể cần cho bảo mật; hồ sơ hỗ trợ có thể cần cho chăm sóc khách hàng; ảnh và địa chỉ có thể cần cho một use case khác. Chúng chỉ không cần nằm trong mô hình quyết định tín dụng.

## 7. Phân biệt dữ liệu quyết định với dữ liệu hiển thị

Một dữ liệu có thể cần cho màn hình nhưng không cần cho quyết định. Điều này không làm dữ liệu đó vô ích; nó chỉ gợi ý một mô hình đọc khác.

Ví dụ, màn hình danh sách hồ sơ có thể hiển thị:

- Tên người nộp đơn.
- Ảnh đại diện.
- Mã hồ sơ.
- Số tiền yêu cầu.
- Trạng thái xử lý.
- Nhân viên phụ trách.
- Thời điểm cập nhật gần nhất.

Query service có thể tổng hợp dữ liệu từ Credit Assessment và Customer Profile thành một projection:

~~~java
public record CreditApplicationListItem(
        String applicationId,
        String applicantName,
        String avatarUrl,
        BigDecimal requestedAmount,
        String status,
        String assignedOfficer,
        Instant updatedAt
) {}
~~~

Projection phục vụ hiển thị không cần trở thành Aggregate. Nó có thể được tạo từ nhiều nguồn, tối ưu cho truy vấn và cập nhật theo chiến lược read model.

### 7.1. Command model và read model có mục tiêu khác nhau

| Command/Domain Model | Read Model |
|---|---|
| Bảo vệ quyết định và bất biến | Trả dữ liệu thuận tiện cho truy vấn |
| Có hành vi nghiệp vụ | Thường là projection dữ liệu |
| Tập trung vào consistency của Aggregate | Có thể chấp nhận eventual consistency |
| Chỉ giữ dữ kiện cần cho hành vi | Có thể tổng hợp nhiều context |
| Thay đổi theo quy tắc miền | Thay đổi theo nhu cầu hiển thị và báo cáo |

Không nên nhồi mọi trường hiển thị vào Aggregate chỉ để tránh viết query projection. Cũng không nên dùng read model làm nguồn sự thật để thực hiện quyết định quan trọng nếu nó có thể bị trễ.

## 8. Một khái niệm nên tồn tại khi có ngữ nghĩa

Rút gọn không phải là xóa mọi class nhỏ. Một khái niệm đáng giữ khi nó giúp diễn đạt ý nghĩa hoặc bảo vệ quy tắc mà kiểu dữ liệu nguyên thủy không thể hiện rõ.

Ví dụ, thay vì dùng BigDecimal cho mọi loại tiền:

~~~java
public record Money(
        BigDecimal amount,
        Currency currency
) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new CurrencyMismatch();
        }
        return new Money(amount.add(other.amount), currency);
    }
}
~~~

Money có ý nghĩa miền: số tiền luôn gắn với tiền tệ và phép cộng cần kiểm tra cùng loại tiền. Đây là abstraction có ích.

Ngược lại, tạo một class ApplicantDisplayLabel chỉ bọc một String, không có quy tắc hoặc ngữ nghĩa riêng và chỉ được dùng ở một chỗ có thể không tạo thêm giá trị. Hãy cân nhắc dựa trên ý nghĩa, không dựa trên mong muốn “mỗi field một class”.

### 8.1. Dấu hiệu một abstraction có giá trị

- Có tên nghiệp vụ được chuyên gia hiểu.
- Có quy tắc hoặc bất biến riêng.
- Gom nhiều thao tác liên quan vào một khái niệm.
- Ngăn việc sử dụng sai kiểu hoặc sai đơn vị.
- Làm cho hành vi của Aggregate rõ hơn.
- Được dùng lại ở nhiều nơi với cùng ngữ nghĩa.

### 8.2. Dấu hiệu abstraction có thể thừa

- Chỉ đổi tên một kiểu nguyên thủy mà không thêm ngữ nghĩa.
- Không có hành vi, bất biến hoặc ranh giới rõ.
- Chỉ tồn tại để tuân theo một pattern.
- Tạo nhiều lớp chuyển tiếp nhưng không làm rõ use case.
- Thay đổi cùng lúc với class duy nhất đang sử dụng nó.

Một abstraction có thể bắt đầu nhỏ và trở nên có giá trị khi quy tắc xuất hiện. Không cần dự đoán tất cả biến thể tương lai.

## 9. Loại bỏ quan hệ không phục vụ quyết định

Quan hệ giữa các Entity cũng có chi phí. Một mô hình có thể tạo quan hệ hai chiều giữa Applicant, Address, SupportTicket, LoginRecord, Payment và Product chỉ vì chúng có liên quan đến cùng một người.

Trước khi thêm quan hệ, hãy hỏi:

- Hành vi nào cần đi qua quan hệ này?
- Aggregate nào sở hữu vòng đời của đối tượng liên quan?
- Có cần tải toàn bộ đối tượng hay chỉ cần ID?
- Quan hệ có thể được truy vấn qua repository/read model không?
- Việc thêm quan hệ có làm tăng consistency boundary không?

Ví dụ, CreditApplication thường chỉ cần ApplicantId thay vì giữ toàn bộ Customer Aggregate. Khi cần hiển thị tên khách, query service có thể lấy thông tin từ Customer Profile.

~~~java
public record ApplicantReference(ApplicantId value) {
    public ApplicantReference {
        Objects.requireNonNull(value);
    }
}
~~~

Tham chiếu bằng ID giữ ranh giới ownership rõ ràng. Nó cũng tránh việc một Aggregate phụ thuộc trực tiếp vào vòng đời của Aggregate thuộc context khác.

## 10. Không đưa mọi dữ kiện vào một Aggregate

Aggregate là ranh giới nhất quán và bảo vệ bất biến. Nếu một Aggregate chứa quá nhiều dữ kiện không liên quan, transaction và cập nhật đồng thời có thể trở nên nặng nề.

Ví dụ, CreditApplication không nhất thiết phải chứa toàn bộ Customer Profile và Login History. Nó chỉ cần dữ liệu tài chính đã được xác minh và tham chiếu người nộp đơn.

Một số dấu hiệu Aggregate đang quá rộng:

- Một thay đổi giao diện làm khóa hoặc ghi lại Aggregate nghiệp vụ.
- Nhiều nhóm người dùng cập nhật các phần không liên quan cùng lúc.
- Aggregate cần tải một graph lớn để thực hiện hành vi nhỏ.
- Quy tắc của một đối tượng gần như không liên quan đến các đối tượng còn lại.
- Một transaction thường xuyên kéo dài vì cập nhật dữ liệu ngoài quyết định.

Tuy nhiên, không nên tách Aggregate chỉ để giảm số field. Nếu các đối tượng phải thay đổi nguyên tử để giữ bất biến, chúng có thể cần ở cùng consistency boundary.

## 11. Phân biệt dữ liệu đầu vào, dữ liệu đã xác minh và kết quả quyết định

Trong một quy trình nghiệp vụ, cùng một thông tin có thể có trạng thái tin cậy khác nhau.

Ví dụ:

- Applicant khai thu nhập là 40 triệu đồng/tháng.
- Hệ thống xác minh thu nhập là 36 triệu đồng/tháng.
- Chính sách chỉ chấp nhận 34 triệu đồng/tháng sau khi điều chỉnh.

Không nên lưu tất cả vào một field income rồi ghi đè qua từng bước. Các khái niệm có ngữ nghĩa khác nhau:

~~~java
public record DeclaredIncome(Money monthlyAmount) {}

public record VerifiedIncome(
        Money monthlyAmount,
        VerificationReference evidence
) {}

public record EligibleIncome(Money monthlyAmount) {}
~~~

Mô hình này có thể cần cả ba giá trị nếu hệ thống phải giải thích quyết định, kiểm toán hoặc xử lý tranh chấp. Nếu use case không cần phân biệt chúng và không có yêu cầu lưu vết, có thể không cần giữ mọi biểu diễn ở cấp Domain.

Điểm quan trọng là không rút gọn bằng cách làm mất sự khác nhau về ý nghĩa.

## 12. Quyết định nào cần được giải thích?

Một số quyết định nghiệp vụ cần giải thích vì sao hệ thống chọn một kết quả. Trong trường hợp này, lý do quyết định là dữ kiện của mô hình, không phải metadata phụ.

Ví dụ, từ chối tín dụng có thể cần:

- Mã lý do từ chối.
- Phiên bản chính sách đã áp dụng.
- Các chỉ số đầu vào được phép lưu.
- Thời điểm đánh giá.
- Người hoặc hệ thống đưa ra quyết định.

~~~java
public record CreditDecision(
        DecisionOutcome outcome,
        CreditLimit approvedLimit,
        List<DecisionReason> reasons,
        PolicyVersion policyVersion,
        Instant decidedAt
) {}
~~~

Nếu pháp luật, kiểm toán hoặc chính sách nội bộ yêu cầu lưu những dữ liệu này, không được loại bỏ chỉ vì chúng không tham gia vào phép tính cuối cùng. Chúng phục vụ khả năng giải thích và chứng minh quyết định.

Rút gọn mô hình cần tính đến các quyết định vận hành, tuân thủ và kiểm toán được yêu cầu, không chỉ quyết định trực tiếp của người dùng.

## 13. Phân biệt metadata kỹ thuật với dữ kiện nghiệp vụ

Một số trường thường xuất hiện trong Entity:

| Trường | Có thể thuộc đâu? | Câu hỏi cần hỏi |
|---|---|---|
| createdAt | Persistence hoặc Domain | Thời điểm tạo có ý nghĩa nghiệp vụ hay chỉ phục vụ kỹ thuật? |
| updatedAt | Persistence | Có quy tắc nào phụ thuộc vào lần cập nhật cuối không? |
| version | Persistence/concurrency | Có dùng để bảo vệ cập nhật đồng thời không? |
| approvedAt | Domain | Có cần chứng minh thời điểm phê duyệt không? |
| approvedBy | Domain/audit | Danh tính người duyệt có ý nghĩa và cần lưu không? |
| correlationId | Application/Integration | Có phục vụ truy vết workflow không? |
| rowVersion | Persistence | Có phải chi tiết optimistic locking không? |

Không nên xóa một field chỉ vì tên nó trông kỹ thuật. Nếu nghiệp vụ dùng thời điểm phê duyệt để tính thời hạn hoặc cần danh tính người duyệt để kiểm toán, đó là dữ kiện có ý nghĩa.

Ngược lại, một trường phục vụ ORM không nhất thiết phải xuất hiện trong Domain Model. Có thể giữ nó ở Persistence Entity và mapping.

## 14. Đừng rút gọn bằng cách chuyển quy tắc ra ngoài Domain

Một phản ứng sai khi muốn làm Domain Model nhỏ hơn là xóa hành vi khỏi Aggregate rồi đặt tất cả điều kiện vào Application Service.

Ví dụ không tốt:

~~~java
public void approve(CreditApplication application) {
    if (application.getStatus() != PENDING) {
        throw new IllegalStateException();
    }
    if (application.getIncome().compareTo(minimumIncome) < 0) {
        throw new IllegalStateException();
    }
    application.setStatus(APPROVED);
}
~~~

Application đang tự kiểm tra trạng thái và quy tắc thu nhập. Các use case khác có thể quên hoặc áp dụng khác nhau.

Nên giữ hành vi ở mô hình miền:

~~~java
public void approve(CreditDecision decision, ApprovalAuthority authority) {
    if (status != ApplicationStatus.PENDING) {
        throw new ApplicationNotPending(status);
    }
    if (!authority.canApprove(decision)) {
        throw new ApprovalLimitExceeded();
    }
    this.decision = decision;
    this.status = ApplicationStatus.APPROVED;
}
~~~

Ví dụ minh họa; trong thiết kế thật, có thể tách quyết định thẩm định khỏi hành vi phê duyệt cuối cùng. Mục tiêu là giữ bất biến tại nơi có trách nhiệm bảo vệ nó, không chuyển chúng thành các câu if rải rác.

## 15. Tránh mô hình hóa quy trình bằng một tập boolean

Một mô hình nông thường có nhiều cờ:

~~~java
public class CreditApplication {
    boolean submitted;
    boolean verified;
    boolean assessed;
    boolean approved;
    boolean rejected;
    boolean cancelled;
}
~~~

Nhiều boolean cho phép tổ hợp mâu thuẫn như approved=true và rejected=true. Chúng cũng không diễn đạt thứ tự hợp lệ.

Nếu quy trình có state machine, hãy dùng một trạng thái có ngữ nghĩa và hành vi chuyển trạng thái:

~~~java
public enum ApplicationStatus {
    DRAFT,
    SUBMITTED,
    VERIFYING,
    ASSESSED,
    APPROVED,
    REJECTED,
    WITHDRAWN
}
~~~

Enum không tự bảo vệ quy tắc. Aggregate vẫn phải quyết định chuyển trạng thái nào hợp lệ và những dữ kiện nào cần có ở mỗi bước.

Không phải mọi trạng thái đều phải được lưu trong một enum. Nếu một khái niệm có vòng đời độc lập, có thể nó nên là Entity hoặc Aggregate riêng. Hãy để ngữ nghĩa nghiệp vụ quyết định.

## 16. Tách mô hình theo Bounded Context

Một cách rút gọn hiệu quả là đưa khái niệm về đúng context sở hữu nó thay vì giữ một mô hình dùng chung cho toàn hệ thống.

Ví dụ:

~~~mermaid
flowchart LR
    subgraph Customer["Customer Care Context"]
        CP[Customer Profile]
        ST[Support History]
    end
    subgraph Credit["Credit Assessment Context"]
        CA[Credit Application]
        FP[Verified Financial Position]
        CD[Credit Decision]
    end
    subgraph Identity["Identity Context"]
        ID[Account and Principal]
    end
    CP -->|Applicant reference| CA
    ID -->|Authenticated identity| Credit
    FP --> CA
    CA --> CD
~~~

Sơ đồ chỉ minh họa trách nhiệm. Customer Care sở hữu thông tin phục vụ chăm sóc; Identity sở hữu danh tính xác thực; Credit Assessment sở hữu dữ liệu và quyết định tín dụng. Các context giao tiếp qua contract hoặc tham chiếu phù hợp, không chia sẻ một Aggregate lớn.

### 16.1. Không chia context theo từng bảng

Tách context không phải là tạo một service cho mỗi Entity. Bounded Context phản ánh ranh giới ngôn ngữ và mô hình, không phải ranh giới kỹ thuật tùy tiện.

Nếu hai nhóm khái niệm luôn thay đổi cùng nhau vì cùng một chính sách nghiệp vụ, chúng có thể thuộc cùng context. Nếu chúng có quy tắc, ownership và nhịp thay đổi khác nhau, cần xem xét ranh giới riêng.

## 17. Đặt dữ liệu không phục vụ quyết định vào đúng mô hình

Khi loại một field khỏi Domain Model, cần xác định nó sẽ đi đâu:

| Loại dữ liệu | Vị trí có thể phù hợp |
|---|---|
| Dữ liệu trình bày màn hình | Read DTO / Projection |
| Dữ liệu tìm kiếm | Search index hoặc query model |
| Metadata ORM | Persistence Entity |
| Thông tin xác thực | Identity Context |
| Lịch sử hỗ trợ | Customer Care Context |
| Audit bắt buộc | Audit store hoặc mô hình audit |
| Dữ liệu tích hợp | Integration contract |
| Dữ liệu phân tích | Analytics/Warehouse |

Đừng mặc định chuyển mọi thứ sang một bảng JSON hoặc metadata bag. Một dữ liệu có ý nghĩa nghiệp vụ cần được đặt ở nơi có ownership và chính sách vòng đời rõ ràng.

## 18. Khi nào dữ liệu phụ vẫn phải nằm trong mô hình?

Một số dữ liệu trông không trực tiếp tham gia quyết định nhưng vẫn cần thiết:

### 18.1. Giải thích quyết định

Lý do từ chối, phiên bản policy và bằng chứng xác minh có thể cần để giải thích tại sao hệ thống đưa ra kết quả.

### 18.2. Tái dựng trạng thái tại thời điểm quyết định

Nếu chính sách thay đổi theo thời gian, hệ thống có thể cần lưu snapshot dữ liệu hoặc policy version đã dùng. Nếu chỉ lưu kết quả cuối cùng, việc kiểm tra lại quyết định cũ có thể không khả thi.

### 18.3. Kiểm toán và tuân thủ

Danh tính actor, thời điểm, nguồn yêu cầu và dấu vết thay đổi có thể là nghĩa vụ pháp lý hoặc nội bộ.

### 18.4. Phục hồi và tích hợp

Correlation ID, message ID hoặc version có thể không thuộc ngôn ngữ miền, nhưng cần ở Application/Infrastructure để retry, replay và quan sát.

Điều quan trọng là đặt đúng tầng. Không phải dữ liệu nào cần thiết cho hệ thống cũng cần nằm trong Domain Entity.

## 19. Dấu hiệu mô hình đang có quá nhiều chi tiết

Hãy xem xét tinh giản khi gặp các dấu hiệu:

- Một Aggregate có nhiều field không được bất kỳ hành vi nào sử dụng.
- Nhiều Entity chỉ tồn tại để phản chiếu bảng hoặc JSON.
- Domain Service chủ yếu chuyển dữ liệu giữa các DTO.
- Application Service chứa nhiều nhánh if để kiểm tra cùng một quy tắc.
- Một thay đổi không liên quan buộc phải tải và lưu Aggregate lớn.
- Các quan hệ hai chiều được tạo nhưng không phục vụ hành vi.
- Một class có nhiều trách nhiệm từ nhiều Bounded Context.
- Mọi màn hình đều dùng chung một object model.
- Các abstraction không có ngôn ngữ nghiệp vụ hoặc quy tắc riêng.
- Người mới đọc mô hình không thể trả lời nó bảo vệ quyết định nào.

Một dấu hiệu riêng đáng chú ý: nếu phải giải thích một field bằng câu “nó có thể sẽ cần sau này”, hãy ghi nhận giả định đó và chờ nhu cầu thực tế thay vì tự động đưa nó vào mô hình cốt lõi.

## 20. Dấu hiệu đã rút gọn quá mức

Tinh giản quá đà cũng tạo ra mô hình nông:

- Aggregate chỉ còn các getter/setter.
- Quy tắc nghiệp vụ bị chuyển vào Controller hoặc Application.
- Các kiểu tiền, số lượng, tỷ lệ hoặc khoảng thời gian bị biểu diễn bằng primitive không có đơn vị.
- Không lưu lý do hoặc bằng chứng dù quyết định cần giải thích.
- Một status chung thay thế nhiều khái niệm có vòng đời khác nhau.
- Dữ liệu cần bảo vệ bất biến bị tách ra khỏi Aggregate.
- Các context phải tự suy đoán ý nghĩa từ ID hoặc mã trạng thái.

Mục tiêu không phải là số field ít nhất. Mục tiêu là mô hình có đủ thông tin để thực hiện và giải thích các quyết định cần thiết, đồng thời không mang trách nhiệm của những context khác.

## 21. Refactor mô hình một cách an toàn

Không nên xóa field hoặc quan hệ chỉ dựa trên cảm giác. Hãy thực hiện có kiểm soát:

1. Liệt kê các quyết định và use case hiện tại.
2. Truy vết field, method và association đến các quyết định đó.
3. Tìm các field không có consumer hoặc quy tắc sử dụng.
4. Xác định dữ liệu có cần cho audit, báo cáo, tích hợp hoặc lịch sử không.
5. Xác định context hoặc mô hình khác sẽ sở hữu dữ liệu nếu chuyển ra.
6. Tạo read model hoặc contract thay thế nếu use case vẫn cần dữ liệu.
7. Chuyển hành vi và bất biến về đúng Entity/Aggregate/Domain Service.
8. Xóa abstraction hoặc association chỉ sau khi không còn caller.
9. Cập nhật test theo hành vi và quyết định, không chỉ theo cấu trúc class.
10. Theo dõi thay đổi với chuyên gia nghiệp vụ để xác nhận mô hình vẫn diễn đạt đúng ngôn ngữ.

### 21.1. Thực hiện theo lát cắt use case

Thay vì tái cấu trúc toàn bộ Applicant cùng lúc, có thể bắt đầu với use case AssessCreditApplication:

- Xác định dữ liệu thực sự được dùng.
- Tạo kiểu miền cho các giá trị có quy tắc.
- Chuyển quyết định vào mô hình miền.
- Tách dữ liệu hiển thị khỏi Aggregate.
- Chạy test cho các trường hợp quyết định.
- Sau đó mới xử lý các use case khác.

Cách này giảm rủi ro và giúp nhóm quan sát lợi ích của mô hình mới.

## 22. Kiểm thử mô hình dựa trên quyết định

Test nên thể hiện quy tắc và kết quả, không chỉ kiểm tra getter/setter.

Ví dụ:

~~~java
class CreditApplicationTest {
    @Test
    void rejectsApplicationWhenRepaymentCapacityIsInsufficient() {
        CreditPolicy policy = policyWithMinimumCapacity(0.35);
        VerifiedFinancialPosition position =
                financialPositionWithCapacity(0.20);
        CreditApplication application =
                CreditApplication.pending(
                        new CreditApplicationId("CA-1"),
                        RequestedCredit.of(100_000_000),
                        position
                );

        CreditDecision decision = application.assess(policy);

        assertEquals(DecisionOutcome.REJECTED, decision.outcome());
        assertTrue(decision.reasons().contains(
                DecisionReason.INSUFFICIENT_REPAYMENT_CAPACITY
        ));
    }
}
~~~

Ví dụ minh họa, các factory và kiểu miền được giả định đã tồn tại. Test tốt cho biết quyết định nào được đưa ra và vì sao. Nếu test chỉ xác nhận một field status đã đổi, nó có thể bỏ lỡ việc mô hình không còn bảo vệ quy tắc.

### 22.1. Test những gì bị loại bỏ

Khi rút gọn, cũng cần kiểm tra các use case vẫn hoạt động:

- Màn hình vẫn có thể lấy avatar từ Customer Profile projection.
- Audit vẫn lưu actor và thời điểm.
- API vẫn trả dữ liệu cần thiết.
- Quyết định tín dụng vẫn có đủ dữ kiện và lý do.
- Các context không truy cập trực tiếp vào persistence model của nhau.

Điều này chứng minh việc chuyển trách nhiệm không làm mất khả năng của hệ thống.

## 23. Làm việc với chuyên gia nghiệp vụ

Không thể xác định khái niệm thừa chỉ bằng cách nhìn code. Một field tưởng như không được sử dụng có thể đại diện cho một ngoại lệ hiếm nhưng rất quan trọng. Một quy tắc tưởng như kỹ thuật có thể thực ra là chính sách nghiệp vụ.

Khi trao đổi với chuyên gia, hãy hỏi:

- Quyết định này dựa trên những dữ kiện nào?
- Dữ kiện nào có thể thay đổi kết quả?
- Có ngoại lệ nào cần được phân biệt?
- Vì sao phải lưu lý do hoặc bằng chứng?
- Khái niệm nào có ý nghĩa riêng trong ngôn ngữ của bộ phận?
- Nếu bỏ thông tin này, có thể giải thích quyết định sau này không?

Sử dụng ví dụ cụ thể và tình huống biên thay vì chỉ hỏi “field này có cần không?”. Chuyên gia nghiệp vụ có thể không quan tâm tên class, nhưng họ hiểu điều kiện, ngoại lệ và hậu quả của quyết định.

## 24. Một ví dụ so sánh hoàn chỉnh

Giả sử yêu cầu ban đầu là “nhân viên có thể duyệt hồ sơ tín dụng”. Mô hình nông có thể dẫn đến:

~~~java
public void approve(String applicationId) {
    Applicant applicant = repository.find(applicationId);
    applicant.setApproved(true);
    applicant.setStatus("APPROVED");
    repository.save(applicant);
}
~~~

Đoạn code không cho biết:

- Hồ sơ có đủ điều kiện không?
- Ai có quyền duyệt hạn mức này?
- Hạn mức được xác định thế nào?
- Lý do từ chối được ghi ở đâu?
- Có thể duyệt lại hồ sơ đã từ chối không?
- Chính sách nào được áp dụng?

Một mô hình tập trung hơn:

~~~java
public final class CreditApplication {
    private final CreditApplicationId id;
    private final RequestedCredit requestedCredit;
    private final VerifiedFinancialPosition financialPosition;
    private ApplicationStatus status;
    private CreditDecision decision;

    public void decide(
            CreditPolicy policy,
            ApprovalAuthority authority,
            Instant now
    ) {
        requireStatus(ApplicationStatus.ASSESSED);

        CreditDecision proposed =
                policy.evaluate(requestedCredit, financialPosition);

        if (proposed.isApproved()) {
            authority.requireCanApprove(proposed);
        }

        this.decision = proposed.withDecisionTime(now);
        this.status = proposed.isApproved()
                ? ApplicationStatus.APPROVED
                : ApplicationStatus.REJECTED;

        raise(new CreditApplicationDecided(id, decision));
    }
}
~~~

Ví dụ thể hiện một quyết định có ý nghĩa. Nó không chứa ảnh đại diện, lịch sử đăng nhập hay support ticket vì các dữ liệu đó không giúp quyết định cấp tín dụng. Nhưng nó giữ dữ kiện tài chính đã xác minh, chính sách, thẩm quyền, kết quả và thời điểm quyết định.

Trong thiết kế thật, cần xác định ApprovalAuthority kiểm tra quyền tổ chức hay giới hạn nghiệp vụ, CreditPolicy sở hữu phép đánh giá nào, và liệu thẩm định với phê duyệt có phải hai use case riêng. Những câu hỏi này cần được giải quyết bằng ngôn ngữ và quy tắc thực tế của domain.

## 25. Sơ đồ quyết định có giữ một khái niệm trong Domain Model không

~~~mermaid
flowchart TD
    A[Khái niệm hoặc field mới] --> B{Có ảnh hưởng quyết định nghiệp vụ?}
    B -->|Có| C{Có quy tắc hoặc ngữ nghĩa riêng?}
    C -->|Có| D[Giữ trong Domain Model với kiểu/hành vi rõ]
    C -->|Không| E[Giữ như dữ liệu đầu vào phù hợp]
    B -->|Không| F{Có yêu cầu audit, tuân thủ hoặc lịch sử?}
    F -->|Có| G[Giữ ở mô hình audit/lịch sử phù hợp]
    F -->|Không| H{Có use case đọc hoặc trình bày cần?}
    H -->|Có| I[Đưa vào Read Model/Projection]
    H -->|Không| J[Không đưa vào mô hình này]
~~~

Sơ đồ là gợi ý để đặt câu hỏi, không phải quy tắc tự động. Một khái niệm có thể cần ở nhiều mô hình với biểu diễn khác nhau. Điều cần tránh là giữ nó trong một Aggregate chỉ vì nó tồn tại ở đâu đó trong hệ thống.

## 26. Checklist rút gọn Domain Model

- [ ] Mỗi Aggregate có trách nhiệm nghiệp vụ và bất biến xác định.
- [ ] Các hành vi quan trọng có tên theo ngôn ngữ domain.
- [ ] Mỗi field có thể liên kết với quyết định, quy tắc, giải thích hoặc yêu cầu lưu vết.
- [ ] Dữ liệu hiển thị không bị nhồi vào Aggregate chỉ để tái sử dụng.
- [ ] Quan hệ giữa Entity tồn tại vì hành vi cần, không chỉ vì dữ liệu có liên quan.
- [ ] Aggregate không ôm dữ liệu thuộc Bounded Context khác.
- [ ] Value Object được dùng khi có ngữ nghĩa hoặc quy tắc riêng.
- [ ] Primitive không làm mất đơn vị, loại hoặc ý nghĩa nghiệp vụ.
- [ ] Quy tắc không bị chuyển ra Controller hoặc Application để làm Domain nhỏ hơn.
- [ ] Dữ liệu audit, tuân thủ và giải thích quyết định vẫn được bảo toàn.
- [ ] Read Model/Projection có ownership và nguồn dữ liệu rõ.
- [ ] Persistence metadata được đặt ở đúng tầng.
- [ ] Việc loại bỏ field có kiểm tra consumer và use case phụ thuộc.
- [ ] Test mô tả quyết định, bất biến và các trường hợp biên.
- [ ] Chuyên gia nghiệp vụ xác nhận mô hình vẫn diễn đạt đúng quyết định.

## 27. Kết luận

Rút gọn phần mô hình không phục vụ quyết định cần thiết là quá trình làm rõ trách nhiệm của Domain Model. Bắt đầu từ những quyết định mà Bounded Context phải hỗ trợ, truy vết ngược đến quy tắc, khái niệm và dữ kiện cần thiết, rồi đặt những phần còn lại vào đúng mô hình như read projection, persistence metadata, audit hoặc context sở hữu dữ liệu.

Một mô hình sâu không phải mô hình ít field nhất. Nó là mô hình có đủ ngữ nghĩa để bảo vệ và giải thích quyết định, nhưng không mang theo những chi tiết không liên quan. Khi mỗi Aggregate có ranh giới rõ, mỗi Value Object biểu đạt một ý nghĩa thực và mỗi hành vi bảo vệ một quy tắc cụ thể, hệ thống dễ hiểu hơn, ít coupling hơn và có thể tiến hóa theo ngôn ngữ nghiệp vụ.

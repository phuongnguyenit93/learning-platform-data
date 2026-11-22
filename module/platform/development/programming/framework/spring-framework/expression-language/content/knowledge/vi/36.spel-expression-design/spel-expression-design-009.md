# Thiết kế điểm thay thế khi biểu thức không còn phù hợp

SpEL phù hợp khi cần mô tả một phép tính hoặc điều kiện nhỏ trên dữ liệu đã có. Khi biểu thức bắt đầu chứa nhiều nhánh nghiệp vụ, truy cập sâu vào object graph, gọi nhiều service, thực hiện I/O hoặc cần xử lý lỗi phức tạp, việc giữ logic trong expression sẽ làm hệ thống khó đọc, khó kiểm thử và khó thay đổi.

Thiết kế điểm thay thế nghĩa là xác định phần nào nên chuyển từ SpEL sang Java và chọn đúng cơ chế thay thế. Có thể dùng method có tên rõ ràng, service nghiệp vụ, class Condition, @ConfigurationProperties, validator hoặc một DSL có cấu trúc. Mục tiêu là giữ SpEL ở vai trò diễn đạt rule đơn giản, còn logic có nhiều trách nhiệm nằm trong code có cấu trúc và có thể kiểm soát.

## 1. Vai trò phù hợp của SpEL

SpEL hữu ích khi biểu thức ngắn, dữ liệu đầu vào đã được chuẩn bị và kết quả có thể hiểu ngay từ cú pháp.

Ví dụ:

~~~text
#order.total >= #minimum
#user.active and #user.region == 'APAC'
items.?[active].size() > 0
~~~

Các biểu thức này đọc property, so sánh và kết hợp một số điều kiện. Người đọc có thể hiểu kết quả mà không cần biết nhiều chi tiết triển khai.

SpEL cũng phù hợp để tính giá trị cấu hình nhỏ, chọn property, lọc collection vừa phải hoặc tạo điều kiện trong một rule engine nội bộ.

Expression không nên trở thành nơi điều phối quy trình, truy vấn dữ liệu, thực hiện transaction hoặc chứa toàn bộ chính sách nghiệp vụ. Khi biểu thức phải giải quyết nhiều trách nhiệm, hãy chuyển phần phức tạp ra khỏi SpEL.

## 2. Dấu hiệu cho thấy expression đã vượt quá phạm vi phù hợp

Một số dấu hiệu thường gặp:

- Biểu thức có nhiều cấp property lồng nhau và nhiều phép kiểm tra null.
- Điều kiện chứa nhiều nhánh AND/OR, ngoặc và selection lồng nhau.
- Expression gọi nhiều method hoặc tham chiếu nhiều bean.
- Method được gọi thực hiện truy vấn database, gọi API hoặc thay đổi trạng thái.
- Logic cần nhiều bước xử lý lỗi hoặc fallback.
- Nhiều expression lặp lại cùng một đoạn điều kiện.
- Người vận hành khó giải thích vì sao rule trả true hoặc false.
- Cần unit test riêng cho từng nhánh nhưng expression khó chia nhỏ.
- Thay đổi một quy tắc nhỏ buộc phải sửa nhiều chuỗi expression.
- Expression được chỉnh sửa bởi người dùng nhưng cú pháp SpEL quá rộng so với nhu cầu.

Không có ngưỡng ký tự cố định để quyết định thay thế. Một expression ngắn vẫn có thể không phù hợp nếu nó gọi method có side effect; một expression dài hơn đôi chút vẫn có thể chấp nhận được nếu nó chỉ diễn đạt một điều kiện thuần, rõ ràng.

Hãy xem số trách nhiệm, số dependency, khả năng kiểm thử và mức độ an toàn là tiêu chí quan trọng hơn chiều dài chuỗi.

## 3. Chuyển điều kiện thành method có tên mô tả

Khi expression chứa một điều kiện nghiệp vụ có ý nghĩa, hãy đưa điều kiện vào method có tên thể hiện kết quả.

Ví dụ expression:

~~~text
#user != null and
#user.account != null and
#user.account.active and
#user.account.region == 'APAC' and
#user.account.ageDays >= 30
~~~

Có thể chuyển thành Java:

~~~java
public boolean isEligibleForRegionalFeature(User user) {
    return user != null
            && user.getAccount() != null
            && user.getAccount().isActive()
            && "APAC".equals(user.getAccount().getRegion())
            && user.getAccount().getAgeDays() >= 30;
}
~~~

Method có tên isEligibleForRegionalFeature thể hiện ý nghĩa nghiệp vụ. Nó có thể được unit test trực tiếp với user null, account null, trạng thái inactive, region khác và tuổi tài khoản chưa đủ.

Nếu SpEL chỉ cần dùng kết quả Boolean, hãy tính trong Java rồi đưa kết quả vào context:

~~~java
boolean eligible =
        eligibilityPolicy.isEligibleForRegionalFeature(user);

context.setVariable("eligible", eligible);
~~~

Expression sau đó chỉ cần đọc eligible. Cách này giữ việc truy cập object và kiểm tra null ở nơi có thể tổ chức code rõ ràng.

## 4. Chuyển quy trình nhiều bước sang service

Nếu logic cần truy vấn repository, gọi API, kiểm tra quyền hoặc phối hợp nhiều thành phần, hãy đặt nó trong application service hoặc domain service.

Ví dụ không phù hợp khi đặt trực tiếp trong expression:

~~~text
@accountService.isActive(#userId) and
@riskService.score(#userId) < 50 and
@paymentService.hasNoDebt(#userId)
~~~

Biểu thức này ẩn ba dependency và có thể thực hiện nhiều truy vấn trong một lần evaluate.

Có thể tạo service điều phối:

~~~java
@Service
public class EligibilityService {

    private final AccountService accounts;
    private final RiskService risks;
    private final PaymentService payments;

    public EligibilityService(
            AccountService accounts,
            RiskService risks,
            PaymentService payments) {
        this.accounts = accounts;
        this.risks = risks;
        this.payments = payments;
    }

    public boolean isEligible(String userId) {
        if (!accounts.isActive(userId)) {
            return false;
        }

        if (risks.score(userId) >= 50) {
            return false;
        }

        return payments.hasNoDebt(userId);
    }
}
~~~

Service có thể kiểm soát thứ tự gọi, short-circuit, timeout, transaction và xử lý exception. Nếu kết quả được dùng trong nhiều nơi, method service cũng tránh lặp lại cùng một expression.

Không nên chuyển mọi điều kiện nhỏ thành service riêng. Hãy tạo service khi có trách nhiệm nghiệp vụ hoặc phối hợp dependency thực sự.

## 5. Dùng Condition cho quyết định đăng ký bean

Trong Spring, điều kiện tạo bean có thể được biểu diễn bằng annotation hoặc class Condition.

Nếu chỉ kiểm tra một property, @ConditionalOnProperty thường là lựa chọn rõ ràng:

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
)
public class AuditConfiguration {
}
~~~

Nếu điều kiện cần nhiều nhánh hoặc đọc nhiều giá trị từ Environment, có thể tạo Condition:

~~~java
public class ProductionAuditCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Environment environment = context.getEnvironment();

        boolean enabled = environment.getProperty(
                "feature.audit.enabled",
                Boolean.class,
                false
        );

        String region = environment.getProperty(
                "app.region",
                "local"
        );

        return enabled && "prod".equals(region);
    }
}
~~~

Áp dụng:

~~~java
@Configuration
@Conditional(ProductionAuditCondition.class)
public class ProductionAuditConfiguration {
}
~~~

Condition riêng có tên mô tả mục tiêu và có thể kiểm thử với nhiều bộ Environment. Nó phù hợp khi @ConditionalOnExpression trở nên dài hoặc khó đọc.

Không tạo Condition riêng cho một phép kiểm tra đơn giản nếu annotation có sẵn đã thể hiện rõ ý định.

## 6. Dùng @ConfigurationProperties cho cấu hình có cấu trúc

Nếu nhiều expression cùng đọc các property liên quan, hãy gom cấu hình vào một class thay vì lặp lại placeholder và phép tính ở nhiều nơi.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.retry")
@Validated
public class RetryProperties {

    @Min(0)
    private int maxAttempts = 3;

    @Min(1)
    private long baseDelayMillis = 500;

    private boolean enabled;

    // getters and setters
}
~~~

Cấu hình được bind vào object có kiểu rõ ràng. Có thể dùng Jakarta Bean Validation để kiểm tra giới hạn và giá trị bắt buộc.

Sau đó, logic tính toán sử dụng RetryProperties trong Java:

~~~java
public Duration delayForAttempt(
        RetryProperties properties,
        int attempt) {

    long multiplier = 1L << Math.max(0, attempt);

    return Duration.ofMillis(
            properties.getBaseDelayMillis() * multiplier
    );
}
~~~

Cách này phù hợp khi cấu hình có nhiều field, default, validation hoặc được nhiều bean sử dụng. SpEL vẫn có thể dùng cho một phép tính nhỏ, nhưng không nên trở thành cơ chế binding chính cho cả một cây cấu hình.

## 7. Dùng validator cho quy tắc dữ liệu

Nếu expression chủ yếu xác nhận object có hợp lệ hay không, hãy cân nhắc Jakarta Bean Validation hoặc validator domain.

Ví dụ:

~~~java
public class RegistrationRequest {

    @NotBlank
    private String email;

    @Min(18)
    private int age;

    @NotNull
    private AccountType accountType;

    // getters and setters
}
~~~

Validator có thể kiểm tra các ràng buộc field và object. Với quy tắc liên quan nhiều field hoặc phụ thuộc dữ liệu khác, có thể tạo class validator hoặc domain method.

SpEL có thể kiểm tra một điều kiện đơn giản, nhưng không nên thay thế validation framework nếu ứng dụng cần constraint metadata, thông báo lỗi theo field hoặc tích hợp với binding.

Tách validation khỏi expression giúp lỗi được gắn đúng field và có thể trả về cho API hoặc giao diện người dùng theo cấu trúc thống nhất.

## 8. Dùng DSL có cấu trúc khi người dùng cần tạo rule

Nếu quản trị viên hoặc người dùng nghiệp vụ cần tự tạo rule, không nhất thiết phải cho họ nhập chuỗi SpEL tự do.

Có thể cung cấp một DSL có cấu trúc:

~~~json
{
  "field": "accountAgeDays",
  "operator": "GREATER_THAN_OR_EQUAL",
  "value": 30
}
~~~

Backend kiểm tra field và operator nằm trong allowlist, xác nhận kiểu value, sau đó đánh giá rule bằng code riêng.

Ví dụ mô hình:

~~~java
public record RuleDefinition(
        String field,
        RuleOperator operator,
        Object value) {
}

public enum RuleOperator {
    EQUALS,
    NOT_EQUALS,
    GREATER_THAN,
    GREATER_THAN_OR_EQUAL,
    IN
}
~~~

DSL giúp giao diện chỉ cung cấp các lựa chọn được hỗ trợ. Backend có thể validate cấu trúc, giới hạn độ sâu, kiểu dữ liệu và quyền sử dụng field.

Nếu vẫn chọn SpEL cho rule do người dùng tạo, hãy giới hạn cú pháp và EvaluationContext ở server side. Không đánh giá trực tiếp chuỗi tùy ý bằng StandardEvaluationContext rộng quyền.

## 9. Chuyển nhiều expression lặp lại thành một policy

Nhiều expression có thể lặp lại cùng một đoạn logic, chẳng hạn kiểm tra account active, region hoặc quyền của người dùng.

Nếu cùng một điều kiện xuất hiện ở nhiều nơi, hãy đặt nó vào một policy hoặc method dùng chung:

~~~java
public interface AccountPolicy {
    boolean canUseFeature(Account account);
}
~~~

Implementation có thể chứa quy tắc và được unit test độc lập.

Các nơi sử dụng chỉ gọi policy:

~~~java
if (accountPolicy.canUseFeature(account)) {
    // Cho phép xử lý tiếp.
}
~~~

Không nên copy cùng một expression vào nhiều annotation hoặc file cấu hình. Khi quy tắc thay đổi, các bản sao có thể không được cập nhật đồng bộ.

Nếu mỗi rule thực sự khác nhau, hãy giữ chúng riêng và đặt tên theo mục đích thay vì gom mọi điều kiện vào một policy tổng quát khó hiểu.

## 10. Chuyển logic có side effect ra khỏi SpEL

Expression nên đọc dữ liệu và tính kết quả. Các hành động thay đổi hệ thống nên được thực hiện trong application service hoặc lifecycle hook.

Không phù hợp:

~~~text
@notificationService.sendWelcomeEmail(#user)
@paymentService.capture(#payment)
@repository.deleteExpiredRecords()
~~~

Các method này có side effect. Việc evaluate expression có thể vô tình gửi email, thu tiền hoặc xóa dữ liệu nếu expression được gọi nhiều lần hoặc được đánh giá trong giai đoạn không mong đợi.

Hãy tách quyết định và hành động:

~~~java
boolean shouldNotify = notificationPolicy.shouldNotify(user);

if (shouldNotify) {
    notificationService.sendWelcomeEmail(user);
}
~~~

Policy trả về quyết định thuần; service thực hiện hành động ở vị trí có transaction, authorization và xử lý lỗi phù hợp.

Không dựa vào số lần expression được đánh giá để đảm bảo một side effect chỉ xảy ra một lần.

## 11. Chuyển expression cần truy vấn dữ liệu sang query/service

Selection và projection của SpEL phù hợp với collection đã có trong bộ nhớ và có kích thước phù hợp.

Nếu expression lọc một tập dữ liệu lớn hoặc getter trong predicate gây lazy loading, hãy chuyển việc lọc về database hoặc service layer.

Ví dụ:

~~~text
#orders.?[#this.customer.active and #this.total >= #minimum]
~~~

Nếu orders có hàng chục nghìn phần tử và customer.active kích hoạt truy vấn cho từng phần tử, expression có thể tạo chi phí lớn.

Có thể dùng repository query:

~~~java
List<Order> findByCustomerActiveTrueAndTotalGreaterThanEqual(
        BigDecimal minimum);
~~~

Database có thể lọc dữ liệu gần nguồn, dùng index và chỉ trả về các bản ghi cần thiết. Service layer vẫn có thể áp dụng thêm policy sau khi truy vấn.

Không nên đưa một truy vấn dữ liệu lớn vào SpEL chỉ để viết điều kiện ngắn hơn.

## 12. Chuyển phép tính phức tạp sang value object hoặc domain method

Nếu expression chứa công thức giá, phí, hạn mức hoặc thời gian, hãy đặt phép tính vào domain object hoặc calculator có kiểu đầu vào/đầu ra rõ ràng.

Ví dụ:

~~~java
public class PriceCalculator {

    public Money calculateFinalPrice(
            Money basePrice,
            Discount discount,
            TaxRate taxRate) {

        Money discounted = discount.applyTo(basePrice);

        return taxRate.applyTo(discounted);
    }
}
~~~

Method có thể dùng kiểu domain như Money, Discount và TaxRate thay vì nhiều số rời rạc. Nó có thể được kiểm thử với quy tắc làm tròn, giới hạn và trường hợp biên.

SpEL có thể đọc kết quả đã tính:

~~~text
#finalPrice.amount >= #minimumAmount
~~~

Không nên để expression thực hiện nhiều phép tính tài chính bằng kiểu số không phù hợp hoặc giấu quy tắc làm tròn trong một chuỗi khó kiểm tra.

## 13. Chuyển logic phụ thuộc trạng thái sang nơi có lifecycle phù hợp

Một expression trong @Value hoặc điều kiện cấu hình thường được đánh giá trong quá trình tạo bean hoặc xử lý ApplicationContext.

Nếu logic phụ thuộc trạng thái runtime thay đổi theo request, không nên tính nó một lần trong @Value rồi kỳ vọng kết quả tự cập nhật.

Ví dụ, trạng thái người dùng hiện tại, quota còn lại hoặc số dư tài khoản nên được truy vấn ở service tại thời điểm nghiệp vụ cần quyết định.

Ngược lại, một giá trị cấu hình ổn định như port, tên ứng dụng hoặc giới hạn cố định có thể được inject khi khởi tạo bean.

Hãy đặt logic tại lifecycle đúng: cấu hình lúc startup, policy lúc xử lý nghiệp vụ, và side effect trong application service có kiểm soát.

## 14. Chuyển logic cần xử lý lỗi rõ ràng sang Java

SpEL có thể phát sinh lỗi khi property không tồn tại, object null, conversion thất bại hoặc method ném exception. Nếu ứng dụng cần phân biệt nhiều loại lỗi và ánh xạ chúng thành phản hồi cụ thể, Java thường là nơi phù hợp hơn.

Ví dụ method có thể trả về kết quả có cấu trúc:

~~~java
public sealed interface EligibilityResult {

    record Allowed() implements EligibilityResult {
    }

    record Rejected(String reason) implements EligibilityResult {
    }

    record InvalidInput(String field) implements EligibilityResult {
    }
}
~~~

Caller có thể phân biệt được cho phép, từ chối nghiệp vụ và dữ liệu đầu vào không hợp lệ.

Một expression Boolean đơn giản không thể hiện đầy đủ lý do từ chối nếu caller chỉ nhận true/false. Nếu lý do là một phần của hợp đồng ứng dụng, hãy dùng result type hoặc exception domain có chủ đích.

Không nên bắt mọi EvaluationException rồi trả false mà không ghi nhận nguyên nhân. Điều đó có thể che giấu lỗi cấu hình hoặc lỗi lập trình.

## 15. Giữ SpEL làm lớp diễn đạt rule, không phải rule engine toàn diện

SpEL là một ngôn ngữ biểu thức mạnh, nhưng một rule engine đầy đủ có thể cần:

- Quản lý phiên bản rule.
- Phân quyền người tạo và người duyệt.
- Kiểm tra cú pháp trước khi publish.
- Mô tả dữ liệu đầu vào và kiểu của từng field.
- Audit thay đổi rule.
- Giải thích lý do rule được kích hoạt.
- Giới hạn thời gian và tài nguyên đánh giá.
- Kiểm soát function, property và method được phép.
- Rollback hoặc vô hiệu hóa rule lỗi.

Nếu ứng dụng cần các khả năng này, hãy thiết kế lớp quản lý rule riêng hoặc dùng một rule engine phù hợp. Không nên dùng việc lưu chuỗi SpEL trong database như giải pháp thay thế toàn bộ vòng đời quản trị rule.

SpEL vẫn có thể là một thành phần đánh giá bên trong hệ thống, nhưng cần có parser, context, validation và policy quản lý xung quanh.

## 16. Bảo mật khi thay thế expression do người dùng cung cấp

Nếu expression đến từ người dùng, thay bằng Java code không có nghĩa là cho phép người dùng chọn tên method tùy ý.

Một DSL hoặc rule template nên giới hạn:

- Field được phép truy cập.
- Operator được phép dùng.
- Kiểu và phạm vi value.
- Độ sâu nhóm điều kiện.
- Kích thước collection hoặc dữ liệu đầu vào.
- Số bước đánh giá và thời gian thực thi.
- Khả năng đọc/ghi dữ liệu.
- Không cho phép gọi method có side effect.

Authorization phải được kiểm tra ở server side. Giao diện chỉ ẩn lựa chọn không đủ để bảo vệ backend.

Nếu cần SpEL, dùng root object nhỏ, context read-only và chỉ expose accessor/function đã chọn. Không cung cấp toàn bộ ApplicationContext, repository hoặc service rộng quyền.

## 17. Cách chuyển đổi từng bước

Không cần thay toàn bộ SpEL trong một lần. Có thể chuyển một rule theo các bước:

1. Xác định expression, nơi đánh giá và dữ liệu đầu vào.
2. Ghi lại kết quả mong đợi cho các trường hợp chính và trường hợp biên.
3. Xác định phần logic thuần, phần truy cập dữ liệu và phần side effect.
4. Chọn method, policy, Condition, validator, query hoặc DSL phù hợp.
5. Viết unit test cho implementation mới.
6. Chuyển caller sang dùng implementation mới.
7. So sánh kết quả trên cùng bộ input trong giai đoạn chuyển đổi nếu rule quan trọng.
8. Xóa expression cũ sau khi tất cả caller đã chuyển.
9. Theo dõi log và metric để phát hiện sai khác khi triển khai.

Giữ thay đổi nhỏ giúp dễ xác định nguyên nhân nếu kết quả mới khác với rule cũ. Với logic quan trọng, có thể chạy chế độ shadow để so sánh kết quả trước khi chuyển hẳn, nhưng không thực hiện side effect hai lần.

## 18. Kiểm thử sau khi chuyển sang Java

Method hoặc service thay thế cần test theo hợp đồng nghiệp vụ, không chỉ test rằng method trả về một giá trị.

Các nhóm trường hợp nên có:

- Dữ liệu hợp lệ và kết quả cho phép.
- Dữ liệu hợp lệ nhưng bị từ chối.
- Object hoặc property null.
- Giá trị biên và giới hạn.
- Nhiều nhánh điều kiện.
- Lỗi từ repository hoặc service phụ thuộc.
- Timeout hoặc lỗi tích hợp nếu có I/O.
- Quyền truy cập không đủ.
- Giá trị cấu hình thiếu hoặc sai kiểu.
- Không có side effect khi điều kiện không được đáp ứng.

Với Condition, kiểm thử nhiều bộ Environment để xác nhận bean được đăng ký đúng. Với @ConfigurationProperties, kiểm tra binding, default và validation. Với DSL, kiểm tra cả cấu trúc hợp lệ lẫn cấu trúc bị từ chối.

Nếu cần giữ SpEL cho một phần nhỏ, vẫn có thể test expression riêng bằng đúng EvaluationContext và root object production-like.

## 19. Bảng chọn điểm thay thế

| Dấu hiệu hoặc nhu cầu | Cơ chế phù hợp |
|---|---|
| Một phép tính ngắn trên giá trị cấu hình | SpEL trong @Value |
| Một property cấu hình đơn giản | Placeholder hoặc @ConfigurationProperties |
| Nhiều property cùng nhóm | @ConfigurationProperties |
| Bật/tắt bean theo một property | @ConditionalOnProperty |
| Điều kiện đăng ký bean có nhiều bước | Condition implementation |
| Một điều kiện nghiệp vụ có tên và dùng lại | Java method hoặc policy |
| Phối hợp repository và nhiều service | Application service |
| Kiểm tra object theo constraint | Jakarta Bean Validation hoặc domain validator |
| Lọc tập dữ liệu lớn | Repository/query service |
| Rule do người dùng tạo | DSL có cấu trúc hoặc rule engine |
| Cần nhiều loại kết quả và lý do lỗi | Result type hoặc domain exception |
| Hành động có side effect | Application service/lifecycle hook |

Bảng là hướng dẫn lựa chọn, không phải quy tắc tuyệt đối. Có thể kết hợp nhiều cơ chế: Java chuẩn bị dữ liệu, SpEL đánh giá một điều kiện nhỏ và service thực hiện hành động sau đó.

## 20. Ví dụ hoàn chỉnh: chuyển expression dài thành policy

Giả sử rule cũ được viết:

~~~text
#order != null and
#order.customer != null and
#order.customer.active and
#order.total >= #minimum and
#order.customer.region == #allowedRegion
~~~

Tạo policy:

~~~java
public class OrderPolicy {

    public boolean canSubmit(
            Order order,
            BigDecimal minimum,
            String allowedRegion) {

        if (order == null || order.getCustomer() == null) {
            return false;
        }

        Customer customer = order.getCustomer();

        return customer.isActive()
                && order.getTotal().compareTo(minimum) >= 0
                && allowedRegion.equals(customer.getRegion());
    }
}
~~~

Sử dụng:

~~~java
boolean canSubmit = orderPolicy.canSubmit(
        order,
        minimum,
        allowedRegion
);

if (canSubmit) {
    orderService.submit(order);
}
~~~

Policy giữ điều kiện trong một method có tên, có thể test độc lập. Application service chỉ thực hiện submit khi policy cho phép.

Trong ví dụ thật, cần quyết định rõ cách xử lý total null, minimum null và allowedRegion null. Hãy thể hiện các invariant đó trong domain type hoặc validation thay vì để chúng trở thành lỗi ngẫu nhiên trong expression.

## 21. Ghi nhớ

Thay SpEL khi expression không còn là một phép tính hoặc điều kiện nhỏ, dễ hiểu và thuần. Dấu hiệu quan trọng gồm nhiều nhánh, nhiều dependency, truy cập object sâu, I/O, side effect, xử lý lỗi phức tạp hoặc nhu cầu quản trị rule vượt quá khả năng của một chuỗi expression.

Dùng Java method hoặc policy cho điều kiện nghiệp vụ có tên; service cho quy trình nhiều dependency; Condition cho quyết định đăng ký bean phức tạp; @ConfigurationProperties cho cấu hình có cấu trúc; validator cho constraint dữ liệu; repository query cho tập dữ liệu lớn; DSL hoặc rule engine cho rule do người dùng quản lý.

Chuyển đổi theo từng bước, giữ hợp đồng đầu vào/đầu ra rõ ràng, kiểm thử các trường hợp biên và chỉ xóa expression cũ sau khi caller đã chuyển. SpEL vẫn hữu ích ở phần nhỏ mà nó diễn đạt tốt; phần còn lại nên nằm trong cơ chế có cấu trúc, có thể kiểm thử và có quyền truy cập rõ ràng.
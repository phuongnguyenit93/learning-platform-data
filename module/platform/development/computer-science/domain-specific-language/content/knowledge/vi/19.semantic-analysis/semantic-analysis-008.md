# Quy tắc có thể mở rộng

## 1. Quy tắc có thể mở rộng là gì?

Trong một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), kiểm tra ngữ nghĩa xác định một chương trình có hợp lệ theo ý nghĩa của ngôn ngữ hay không. Ngoài các kiểm tra cố định như tên chưa được khai báo, kiểu không tương thích hoặc tham chiếu vòng, nhiều DSL cần cho phép bổ sung quy tắc theo miền nghiệp vụ, dự án hoặc plugin.

**Quy tắc có thể mở rộng (extensible semantic rule)** là một đơn vị kiểm tra được đăng ký vào hệ thống phân tích ngữ nghĩa thông qua một giao diện hoặc cơ chế mở rộng đã định nghĩa. Mỗi quy tắc nhận thông tin về chương trình, kiểm tra một điều kiện và trả về kết quả hoặc diagnostic.

Ví dụ, một DSL dùng để mô tả chính sách giá có thể có các quy tắc mặc định:

- Mức giảm giá phải nằm trong khoảng cho phép.
- Tiền tệ của hai toán hạng phải tương thích.
- Mọi tên thuộc tính phải được khai báo.

Một tổ chức có thể cần thêm quy tắc riêng:

- Mọi chương trình phải có mã chủ sở hữu.
- Chính sách giảm giá trên 30% phải có người phê duyệt.
- Rule liên quan dữ liệu cá nhân phải ghi lý do sử dụng dữ liệu.

Nếu phải sửa compiler mỗi khi thêm một chính sách mới, hệ thống sẽ khó mở rộng và khó duy trì. Một cơ chế rule extension cho phép nhóm phát triển thêm kiểm tra mà không phải thay đổi lõi parser hoặc type checker cho từng yêu cầu.

Quy tắc mở rộng cần có hợp đồng rõ ràng: chạy ở giai đoạn nào, được đọc dữ liệu gì, có được thay đổi cây hay không, trả lỗi bằng cách nào, thứ tự chạy ra sao và phiên bản nào tương thích với runtime.

## 2. Phân biệt quy tắc lõi và quy tắc mở rộng

Không phải mọi kiểm tra đều nên trở thành plugin.

| Loại quy tắc | Ví dụ | Nơi thường triển khai |
|---|---|---|
| Quy tắc cú pháp | Thiếu dấu đóng ngoặc | Lexer/parser |
| Quy tắc ngữ nghĩa lõi | Tên chưa được khai báo, kiểu không tương thích | Name resolver/type checker |
| Quy tắc miền dùng chung | Ngày kết thúc phải sau ngày bắt đầu | Semantic validation framework |
| Quy tắc riêng tổ chức | Mọi policy phải có owner | Extension hoặc plugin |
| Quy tắc phong cách | Tên biến theo quy ước | Linter |
| Quy tắc môi trường chạy | Dữ liệu thực tế không thỏa điều kiện | Runtime validation |

Quy tắc lõi thường bảo đảm tính đúng cơ bản của ngôn ngữ. Quy tắc mở rộng bổ sung chính sách hoặc ràng buộc có phạm vi cụ thể.

Một quy tắc phong cách có thể chỉ tạo warning, trong khi lỗi kiểu có thể ngăn chương trình biên dịch. Hệ thống cần cho phép phân biệt severity và khả năng chặn quá trình xử lý.

## 3. Vì sao cần cơ chế mở rộng?

Một DSL thường được dùng trong nhiều tổ chức hoặc nhiều miền nghiệp vụ. Nhu cầu kiểm tra có thể thay đổi theo:

- Loại dự án.
- Môi trường triển khai.
- Quy định nội bộ.
- Phiên bản schema.
- Quyền của người dùng.
- Loại dữ liệu hoặc tài nguyên được mô tả.
- Chính sách tuân thủ và audit.

Một framework mở rộng tốt mang lại:

**Tách biệt trách nhiệm:** lõi ngôn ngữ giữ các quy tắc chung; module mở rộng giữ chính sách chuyên biệt.

**Tái sử dụng:** một rule có thể được dùng trong nhiều project hoặc nhiều file DSL.

**Cấu hình:** tổ chức có thể bật, tắt hoặc thay severity của một rule theo profile.

**Khả năng kiểm thử:** từng rule có thể được kiểm thử độc lập với compiler.

**Khả năng tích hợp:** công cụ bên ngoài có thể bổ sung kiểm tra qua SPI, plugin API hoặc cấu hình.

**Tiến hóa:** rule có thể được cập nhật theo phiên bản mà không buộc thay đổi grammar.

Tuy vậy, mỗi extension cũng tạo thêm một hợp đồng cần quản lý. Một hệ thống cho phép plugin tùy ý có thể trở nên khó dự đoán nếu không kiểm soát quyền, thứ tự, phiên bản và tác dụng phụ.

## 4. Kiến trúc tổng quát của semantic rule engine

Một pipeline kiểm tra ngữ nghĩa có thể tổ chức như sau:

~~~text
DSL source
    |
    v
Lexer / Parser
    |
    v
AST / Semantic model
    |
    v
Core semantic analysis
    |
    v
Rule registry
    |
    v
Rule scheduler
    |
    +--> Rule A
    +--> Rule B
    +--> Rule C
    |
    v
Diagnostic collector
    |
    v
Result / IDE / CLI
~~~

Các thành phần chính:

- **Rule API:** hợp đồng mà mỗi quy tắc phải triển khai.
- **Rule registry:** lưu các rule đã được đăng ký và metadata.
- **Rule provider:** cách tìm và nạp rule từ lõi, module hoặc plugin.
- **Rule context:** dữ liệu mà rule được phép sử dụng.
- **Scheduler:** quyết định thứ tự, dependency và khả năng chạy song song.
- **Diagnostic collector:** thu thập và chuẩn hóa kết quả.
- **Configuration:** bật/tắt, severity, phạm vi và tham số của rule.

Không phải hệ thống nào cũng cần đủ các thành phần này. DSL nhỏ có thể dùng một danh sách rule cố định. Khi số rule, plugin và profile tăng lên, registry và scheduler riêng sẽ giúp quản lý rõ ràng hơn.

## 5. Thiết kế hợp đồng cho một rule

Một rule nên có định danh ổn định, mô tả, phạm vi áp dụng và phương thức kiểm tra.

Ví dụ Java:

~~~java
interface SemanticRule {
    RuleDescriptor descriptor();

    void evaluate(
        SemanticModel model,
        RuleContext context,
        DiagnosticSink diagnostics
    );
}
~~~

Trong đó:

- SemanticModel cung cấp AST hoặc mô hình ngữ nghĩa đã được chuẩn hóa.
- RuleContext cung cấp cấu hình và dịch vụ được phép sử dụng.
- DiagnosticSink nhận kết quả kiểm tra.
- RuleDescriptor mô tả metadata và yêu cầu chạy.

Một descriptor có thể được biểu diễn:

~~~java
record RuleDescriptor(
    String id,
    String name,
    String description,
    String version,
    RuleCategory category,
    Severity defaultSeverity
) {}
~~~

Đây là mô hình minh họa. API thực tế có thể trả về một danh sách RuleFinding thay vì nhận DiagnosticSink, hoặc dùng generic type theo loại node mà rule xử lý.

### 5.1 Định danh rule

Rule ID nên ổn định và duy nhất trong một namespace:

~~~text
core.type-mismatch
core.undefined-symbol
company.policy-owner-required
finance.discount-limit
~~~

Không nên dùng tên hiển thị làm ID vì tên có thể được dịch hoặc đổi cách diễn đạt. Namespace giúp tránh xung đột giữa rule lõi và plugin của tổ chức.

### 5.2 Metadata của rule

Metadata hữu ích có thể gồm:

- ID và tên.
- Mô tả và tài liệu.
- Phiên bản rule.
- Nhà cung cấp hoặc namespace.
- Severity mặc định.
- Loại rule: correctness, security, style hoặc domain.
- Giai đoạn chạy.
- Node hoặc phạm vi mà rule quan tâm.
- Dependency với rule khác.
- Khả năng chạy song song.
- Khả năng tạo quick fix.

Metadata giúp công cụ hiển thị rule, cấu hình và lập kế hoạch chạy mà không phải biết chi tiết implementation.

## 6. Ví dụ một rule mở rộng

Giả sử DSL có khai báo policy:

~~~text
policy "Seasonal discount"
  owner "pricing-team"
  when order.total >= 1000000 VND
  then discount 15 percent
~~~

Một tổ chức yêu cầu mọi policy phải có owner. Có thể viết rule:

~~~java
final class PolicyOwnerRequiredRule implements SemanticRule {
    @Override
    public RuleDescriptor descriptor() {
        return new RuleDescriptor(
            "company.policy-owner-required",
            "Policy owner required",
            "Every policy must declare an owner.",
            "1.0.0",
            RuleCategory.GOVERNANCE,
            Severity.ERROR
        );
    }

    @Override
    public void evaluate(
        SemanticModel model,
        RuleContext context,
        DiagnosticSink diagnostics
    ) {
        for (PolicyDeclaration policy : model.policies()) {
            if (policy.owner().isEmpty()) {
                diagnostics.report(new Diagnostic(
                    descriptor().id(),
                    Severity.ERROR,
                    "Policy must declare an owner.",
                    policy.nameRange()
                ));
            }
        }
    }
}
~~~

Rule duyệt các policy trong semantic model và tạo diagnostic cho policy chưa có owner. Nó không cần biết parser hoạt động thế nào nếu semantic model đã cung cấp cấu trúc cần thiết.

Nếu owner là tùy chọn trong một số project, rule có thể được bật theo profile hoặc đọc cấu hình đã được xác thực. Không nên nhúng điều kiện riêng của từng tổ chức vào lõi compiler.

## 7. Rule registry và đăng ký extension

Registry chịu trách nhiệm lưu các rule được hệ thống biết đến.

Một registry tối giản:

~~~java
final class RuleRegistry {
    private final Map<String, SemanticRule> rules =
        new LinkedHashMap<>();

    void register(SemanticRule rule) {
        String id = rule.descriptor().id();
        if (rules.putIfAbsent(id, rule) != null) {
            throw new IllegalArgumentException(
                "Duplicate rule id: " + id
            );
        }
    }

    Optional<SemanticRule> find(String id) {
        return Optional.ofNullable(rules.get(id));
    }

    Collection<SemanticRule> all() {
        return List.copyOf(rules.values());
    }
}
~~~

Registry nên từ chối ID trùng thay vì âm thầm ghi đè. Nếu plugin muốn thay thế một rule mặc định, việc override cần là một tính năng tường minh với quyền và thứ tự ưu tiên được định nghĩa.

### 7.1 Đăng ký tường minh

Ứng dụng có thể đăng ký rule trực tiếp:

~~~java
RuleRegistry registry = new RuleRegistry();
registry.register(new PolicyOwnerRequiredRule());
registry.register(new DiscountLimitRule());
~~~

Cách này đơn giản, dễ kiểm soát và phù hợp với ứng dụng có tập extension cố định.

### 7.2 Service Provider Interface

Java có thể dùng ServiceLoader để phát hiện provider:

~~~java
interface SemanticRuleProvider {
    Collection<SemanticRule> rules();
}
~~~

Provider:

~~~java
public final class CompanyRuleProvider
        implements SemanticRuleProvider {

    @Override
    public Collection<SemanticRule> rules() {
        return List.of(
            new PolicyOwnerRequiredRule(),
            new DiscountLimitRule()
        );
    }
}
~~~

Ứng dụng nạp provider:

~~~java
ServiceLoader.load(SemanticRuleProvider.class)
    .stream()
    .map(ServiceLoader.Provider::get)
    .flatMap(provider -> provider.rules().stream())
    .forEach(registry::register);
~~~

Để ServiceLoader tìm provider theo cách truyền thống, module hoặc JAR cần khai báo provider theo quy ước Java tương ứng. Cần quản lý classpath/module path và phiên bản API rõ ràng.

### 7.3 Cấu hình bật/tắt rule

Không nên bắt buộc mọi rule đã được nạp đều chạy. Một profile có thể bật các rule cụ thể:

~~~yaml
rules:
  core.undefined-symbol:
    enabled: true
  company.policy-owner-required:
    enabled: true
  finance.discount-limit:
    enabled: false
~~~

Định dạng cấu hình chỉ là ví dụ. Hệ thống cần kiểm tra ID tồn tại, kiểu giá trị, quyền cấu hình và cách xử lý rule không được cài đặt.

## 8. Rule context và ranh giới dữ liệu

Rule cần dữ liệu để đánh giá, nhưng không nên được cấp quyền truy cập không giới hạn.

Một context có thể chứa:

- Semantic model hoặc phần model liên quan.
- Symbol table đã được phân giải.
- Type information.
- Project profile.
- Phiên bản schema.
- Source map.
- Diagnostic configuration.
- Cancellation token.
- Dịch vụ đọc metadata được cho phép.

Ví dụ:

~~~java
interface RuleContext {
    ProjectConfiguration configuration();
    SymbolIndex symbols();
    TypeSystem types();
    SourceRepository sources();
    CancellationToken cancellation();
}
~~~

### 8.1 Chỉ cung cấp dữ liệu cần thiết

Một rule kiểm tra owner không cần quyền truy cập database giao dịch hoặc file hệ thống tùy ý. Cung cấp quá nhiều dịch vụ làm tăng rủi ro và khiến rule khó kiểm thử.

Thiết kế capability nhỏ giúp:

- Giảm quyền của plugin.
- Dễ mock trong test.
- Làm rõ dependency.
- Tạo cache hoặc snapshot ổn định.
- Tránh rule vô tình thay đổi trạng thái ứng dụng.

### 8.2 Snapshot ngữ nghĩa

Các rule trong cùng một lần phân tích nên thường đọc cùng một snapshot semantic model. Nếu một rule sửa model trong khi rule khác đang đọc, kết quả có thể phụ thuộc thứ tự chạy.

Một lựa chọn an toàn là coi model là immutable trong giai đoạn validation. Nếu cần biến đổi cây, hãy dùng một phase transformation riêng và tạo model mới trước khi chạy các rule tiếp theo.

## 9. Rule thuần và rule có tác dụng phụ

Một rule validation lý tưởng:

- Đọc semantic model.
- Đọc cấu hình.
- Tạo diagnostics.
- Không sửa AST.
- Không ghi file hoặc gọi dịch vụ bên ngoài.

Đây là rule thuần theo nghĩa tác động lên chương trình phân tích được giới hạn. Cùng input và cùng cấu hình nên cho cùng kết quả.

Một số hệ thống có thể cho phép rule gọi dịch vụ ngoài hoặc đọc dữ liệu runtime, nhưng điều đó làm giảm tính xác định và tăng độ phức tạp.

### 9.1 Tách validation khỏi hành động

Thay vì để rule tự cập nhật dữ liệu:

~~~text
rule detects missing approval
        |
        v
diagnostic / proposed action
        |
        v
application or user decides
        |
        v
perform external action
~~~

Rule engine nên mô tả vấn đề và đề xuất. Việc thực hiện hành động có tác động nên thuộc một lớp điều phối có quyền riêng.

### 9.2 Không dùng thời gian hoặc random ẩn

Nếu rule dựa vào ngày hiện tại, hãy đưa clock hoặc evaluation timestamp vào context. Nếu rule dùng dữ liệu ngoài, hãy cung cấp snapshot hoặc phiên bản dữ liệu. Điều này giúp kết quả có thể tái lập.

## 10. Các giai đoạn chạy rule

Không phải rule nào cũng có thể chạy ngay sau khi parse. Một pipeline thường chia thành các phase:

| Phase | Thông tin đã có | Ví dụ rule |
|---|---|---|
| AST validation | Cấu trúc cây và source range | Cấm block rỗng |
| Name resolution | Symbol và scope | Cấm tên khai báo trùng |
| Type checking | Kiểu biểu thức và chữ ký | Yêu cầu Money cùng currency |
| Domain validation | Mô hình miền đã liên kết | Giới hạn discount |
| Cross-reference validation | Quan hệ giữa nhiều khai báo | Mọi workflow transition phải có đích |
| Policy/lint phase | Toàn bộ model và profile | Bắt buộc owner, naming convention |

Mỗi rule nên khai báo phase cần chạy. Nếu một rule cần type information nhưng được chạy trước type checking, nó có thể đưa ra kết quả sai hoặc không đầy đủ.

### 10.1 Phase dependency

Có thể định nghĩa dependency:

~~~text
parse
  -> resolve-names
  -> type-check
  -> domain-validation
  -> policy-rules
~~~

Một rule trong domain-validation phụ thuộc vào kết quả type-check. Scheduler phải bảo đảm phase trước hoàn tất thành công hoặc cung cấp trạng thái lỗi đủ để rule xử lý.

### 10.2 Rule có thể chạy khi model chưa hoàn chỉnh?

Trong IDE, người dùng thường đang gõ dở. Model có thể chứa node lỗi hoặc symbol chưa phân giải. Rule cần khai báo khả năng xử lý incomplete model.

Có thể:

- Bỏ qua node không đủ thông tin.
- Tạo diagnostic tạm thời với độ tin cậy thấp.
- Chỉ chạy khi phase liên quan đã hoàn tất.
- Chạy trên phần model hợp lệ và bỏ qua vùng lỗi cú pháp.

Không nên tạo nhiều lỗi thứ cấp gây nhiễu khi nguyên nhân gốc là parser chưa hiểu được cấu trúc.

## 11. Thứ tự và dependency giữa các rule

Nếu rule độc lập và chỉ tạo diagnostics, thứ tự thường không ảnh hưởng đến kết quả. Nhưng một số rule có thể cần output của rule khác hoặc cần chạy sau một phase cụ thể.

Ví dụ:

~~~text
Rule A: resolve policy references
Rule B: validate policy ownership
Rule C: check cross-policy conflicts
~~~

Nếu B cần symbol đã resolve, nó phải chạy sau A hoặc sau phase name resolution. C có thể cần kết quả chuẩn hóa của A và B.

### 11.1 Khai báo dependency

Metadata có thể chứa:

~~~text
requires:
  - core.name-resolution
  - core.type-check
~~~

Scheduler dùng dependency để lập thứ tự chạy. Nếu dependency không tồn tại hoặc tạo chu trình không được hỗ trợ, cần báo lỗi cấu hình.

### 11.2 Không dùng thứ tự đăng ký làm hợp đồng ngầm

Nếu rule A cần chạy trước B, hãy khai báo dependency thay vì dựa vào thứ tự plugin được nạp. Thứ tự nạp có thể thay đổi theo classpath, hệ điều hành hoặc cấu hình.

### 11.3 Topological scheduling

Các rule có dependency dạng DAG có thể được sắp xếp bằng topological sort. Các rule không phụ thuộc nhau có thể chạy cùng một nhóm hoặc song song nếu thỏa điều kiện an toàn.

Nếu dependency graph có chu trình, scheduler cần từ chối, gom thành một phase đặc biệt hoặc dùng semantics lặp được định nghĩa. Không nên lặp rule vô hạn chỉ vì chúng phụ thuộc lẫn nhau.

## 12. Chạy song song và tính xác định

Nhiều rule độc lập có thể chạy song song để giảm thời gian phân tích. Nhưng chỉ nên làm khi:

- Rule không sửa shared model.
- Rule không ghi vào cùng mutable state.
- Context thread-safe hoặc immutable.
- Diagnostic collector hỗ trợ concurrent reporting.
- Dependency đã được đáp ứng.
- Thứ tự hiển thị kết quả được chuẩn hóa.

### 12.1 Diagnostic order

Nếu nhiều rule chạy song song, thứ tự chúng báo lỗi có thể thay đổi giữa các lần chạy. Để kết quả ổn định, collector có thể sắp xếp theo:

1. URI hoặc file.
2. Source start offset.
3. Severity.
4. Rule ID.
5. Diagnostic code.

Thứ tự sắp xếp là chính sách hiển thị, không nên làm mất thông tin về thứ tự thực thi nếu thông tin đó có ý nghĩa.

### 12.2 Cancellation

IDE có thể hủy một lần phân tích cũ khi người dùng tiếp tục gõ. Rule API nên cung cấp cancellation token hoặc cơ chế tương tự. Rule chạy lâu cần kiểm tra cancellation định kỳ và dừng nhanh.

### 12.3 Timeout và giới hạn tài nguyên

Plugin có thể chạy chậm hoặc lặp vô hạn. Runtime có thể đặt:

- Timeout theo rule.
- Giới hạn số node được duyệt.
- Giới hạn số diagnostic.
- Giới hạn bộ nhớ hoặc kích thước dữ liệu.
- Hủy toàn bộ lượt phân tích khi vượt ngưỡng.

Giới hạn cần được thiết kế sao cho một rule lỗi không làm treo toàn bộ IDE hoặc compiler.

## 13. Severity, cấu hình và profile

Một rule có thể có severity mặc định nhưng được thay đổi theo project.

Ví dụ:

~~~yaml
rules:
  company.policy-owner-required:
    enabled: true
    severity: warning
  finance.discount-limit:
    enabled: true
    severity: error
~~~

### 13.1 Severity khác với tính hợp lệ

Một rule style có thể tạo warning nhưng không ngăn compile. Một rule correctness có thể tạo error. Tuy nhiên, severity hiển thị không nhất thiết quyết định trực tiếp việc build có thất bại hay không.

Nên có một chính sách riêng như failOnSeverity hoặc rule category được xem là blocking.

### 13.2 Profile

Có thể định nghĩa profile:

- development: bật nhiều warning và gợi ý.
- production: bật các rule bắt buộc.
- regulated: bật kiểm tra audit và governance.
- legacy: giảm severity cho một số rule cũ trong thời gian chuyển đổi.

Profile cần được phiên bản hóa hoặc lưu cùng kết quả phân tích để biết một chương trình đã được kiểm tra theo bộ quy tắc nào.

### 13.3 Suppression

Đôi khi một rule đúng nhưng không phù hợp với một đoạn cụ thể. DSL có thể hỗ trợ suppression:

~~~text
@suppress("company.naming")
let legacyCode = ...
~~~

Suppression nên:

- Chỉ áp dụng cho rule ID cụ thể.
- Có phạm vi rõ ràng.
- Có thể yêu cầu lý do.
- Có thể hết hạn hoặc bị giới hạn.
- Được ghi nhận trong audit khi cần.

Không nên cho phép một comment chung tắt mọi rule bảo mật hoặc correctness mà không có quyền thích hợp.

## 14. Diagnostic từ rule mở rộng

Rule nên dùng cùng một mô hình diagnostic với compiler lõi để IDE, CLI và CI có thể xử lý thống nhất.

Một diagnostic thường gồm:

- Rule ID và diagnostic code.
- Severity.
- Message.
- Primary source range.
- Related information.
- Tags hoặc metadata.
- Data cho code action nếu được hỗ trợ.

Ví dụ:

~~~text
company.policy-owner-required:
  severity: error
  message: Policy must declare an owner.
  range: policy declaration
~~~

### 14.1 Source range

Rule cần trỏ đến node hoặc token thực tế. Nếu diagnostic nói policy thiếu owner, có thể đánh dấu tên policy hoặc toàn bộ khai báo policy. Cần chọn range giúp người dùng hiểu vị trí cần sửa.

### 14.2 Related information

Với rule kiểm tra trùng lặp, related information có thể trỏ đến khai báo khác. Với rule cross-reference, nó có thể trỏ đến cả hai đầu quan hệ.

### 14.3 Diagnostic data

Có thể đính kèm metadata nội bộ như:

- SymbolId.
- Rule configuration key.
- Expected type.
- Candidate names.
- Node identity.

Không nên nhúng object lớn hoặc dữ liệu nhạy cảm vào diagnostic gửi cho client. Metadata nên nhỏ, có thể serialize và được kiểm soát.

## 15. Rule có thể tạo gợi ý sửa lỗi

Một số rule có thể cung cấp code action nếu biết cách sửa an toàn.

Ví dụ, rule naming phát hiện biến viết sai quy ước:

~~~text
let CustomerName = "..."
~~~

Nếu quy ước yêu cầu lowerCamelCase, có thể đề xuất:

~~~text
let customerName = "..."
~~~

Tuy nhiên, đổi tên cần cập nhật mọi tham chiếu đã được resolve. Không nên thay chuỗi văn bản toàn file vì có thể sửa nhầm comment hoặc literal.

### 15.1 Tách phát hiện và tạo action

Rule có thể tạo diagnostic cùng metadata cần thiết. Một action provider riêng nhận diagnostic và context rồi tạo text edit.

Tách như vậy giúp:

- Rule vẫn thuần và dễ kiểm thử.
- Action chỉ được tính khi người dùng yêu cầu.
- Có thể dùng nhiều client khác nhau.
- Có thể kiểm tra edit theo phiên bản tài liệu.

### 15.2 Không phải rule nào cũng có quick fix

Rule kiểm tra chính sách phê duyệt có thể chỉ báo lỗi. Công cụ không thể tự quyết định người phê duyệt thay người dùng. Một gợi ý tạo trường owner rỗng cũng có thể không giải quyết vấn đề.

Chỉ tạo quick fix khi công cụ có đủ thông tin và thay đổi không làm sai ý định nghiệp vụ.

## 16. Versioning và tương thích API

Rule plugin phụ thuộc vào API của semantic engine. Nếu compiler thay đổi AST, context hoặc diagnostic model, plugin cũ có thể không còn chạy đúng.

### 16.1 Phiên bản API

Nên phân biệt:

- Phiên bản DSL language.
- Phiên bản semantic model.
- Phiên bản extension API.
- Phiên bản của từng rule.
- Phiên bản cấu hình rule.

Không nên gộp tất cả thành một số phiên bản duy nhất nếu chúng có vòng đời khác nhau.

### 16.2 Semantic versioning

Nếu dùng semantic versioning:

- MAJOR: thay đổi không tương thích.
- MINOR: thêm API tương thích ngược.
- PATCH: sửa lỗi không đổi hợp đồng công khai.

Compiler có thể từ chối plugin khai báo API version không tương thích thay vì cố chạy rồi phát sinh lỗi khó hiểu.

### 16.3 Capability negotiation

Một plugin có thể khai báo khả năng cần thiết:

~~~text
requires:
  semantic-model >= 2
  source-map
  type-information
~~~

Host kiểm tra capability trước khi kích hoạt. Nếu thiếu capability, có thể bỏ qua rule và báo cấu hình, hoặc từ chối khởi động tùy mức độ quan trọng.

### 16.4 Deprecation

Khi API sắp bị loại bỏ, nên:

- Đánh dấu deprecated.
- Cung cấp API thay thế.
- Nêu phiên bản dự kiến loại bỏ.
- Duy trì thời gian chuyển đổi.
- Cảnh báo plugin đang dùng API cũ.

## 17. Cô lập và bảo mật plugin

Rule plugin là mã chạy trong tiến trình hoặc môi trường do compiler quản lý. Nếu plugin không đáng tin cậy, nó có thể đọc file, truy cập mạng, tiêu thụ CPU hoặc làm thay đổi trạng thái ứng dụng.

Các nguyên tắc:

- Chỉ nạp plugin từ nguồn được tin cậy.
- Xác thực danh tính hoặc chữ ký artifact nếu chính sách yêu cầu.
- Giới hạn quyền truy cập file và mạng.
- Cung cấp context theo nguyên tắc quyền tối thiểu.
- Đặt timeout và giới hạn tài nguyên.
- Cô lập plugin lỗi để không làm hỏng toàn bộ phiên phân tích.
- Ghi log provider, phiên bản và lỗi khởi tạo.

### 17.1 Plugin trong cùng JVM

ClassLoader riêng có thể giúp quản lý dependency và namespace, nhưng không phải sandbox bảo mật hoàn chỉnh. Mã Java trong cùng process thường có thể truy cập nhiều tài nguyên mà process được phép sử dụng.

Nếu plugin đến từ bên thứ ba và không thể tin cậy, cần cân nhắc process isolation, container hoặc một giao thức RPC có giới hạn.

### 17.2 Không để rule tự sửa semantic model

Một plugin có thể làm sai kết quả của plugin khác nếu được quyền thay đổi AST hoặc symbol table. Model bất biến và output dạng diagnostics giúp giảm rủi ro này.

Nếu cần transformation, hãy dùng API riêng có phase, contract và validation rõ ràng.

### 17.3 Dữ liệu nhạy cảm

Rule có thể đọc tên khách hàng, cấu hình hoặc metadata nội bộ. Chỉ cung cấp dữ liệu cần thiết, tránh log nội dung nhạy cảm và xác định rõ dữ liệu nào được gửi đến dịch vụ ngoài.

## 18. Rule theo cấu hình và rule do người dùng định nghĩa

Không phải extension nào cũng cần viết Java. Một số DSL cho phép người dùng khai báo thêm rule bằng chính DSL hoặc bằng cấu hình.

Ví dụ:

~~~text
semantic_rule "discount-limit"
  applies_to Policy
  require policy.discount <= 30 percent
  message "Discount must not exceed 30 percent"
  severity error
~~~

Rule này được biên dịch thành một biểu thức kiểm tra trong semantic model.

### 18.1 Lợi ích

- Người dùng nghiệp vụ có thể viết chính sách mà không cần plugin Java.
- Rule có thể được lưu cùng project.
- Cấu hình dễ review và version control.
- Cùng một rule engine có thể đánh giá nhiều rule khai báo.

### 18.2 Giới hạn

Rule do người dùng viết cần một tập biểu thức được kiểm soát. Không nên cho phép gọi tùy ý mọi method hoặc thực thi mã không giới hạn.

### 18.3 Kiểu hóa rule expression

Nếu điều kiện yêu cầu Boolean, compiler nên kiểm tra biểu thức có kiểu Boolean phù hợp. Nếu rule trả về nullable Boolean, semantics phải xác định unknown được xử lý thế nào.

### 18.4 Rule meta-rule

Một số hệ thống cần quy tắc kiểm tra chính các rule khác, ví dụ:

- Rule không được dùng API deprecated.
- Rule phải có message.
- Rule phải có owner.
- Rule không được phụ thuộc vào một rule không tồn tại.

Đây là validation của định nghĩa rule, khác với việc áp dụng rule lên chương trình người dùng.

## 19. Rule composition và nhóm quy tắc

Một chính sách có thể gồm nhiều rule:

~~~text
Profile "regulated"
  include core.correctness
  include security.baseline
  include company.governance
  override finance.discount-limit severity = error
~~~

Composition cần định nghĩa:

- Rule group có thể bao gồm group khác không?
- Include trùng có được loại bỏ không?
- Hai cấu hình cùng đặt severity thì cái nào thắng?
- Rule bị disable ở group con có thể được enable ở group cha không?
- Xung đột cấu hình được báo lỗi hay dùng ưu tiên?

### 19.1 Tránh cấu hình khó đoán

Một thứ tự ưu tiên có thể là:

1. Default của rule.
2. Cấu hình profile.
3. Cấu hình project.
4. Override cục bộ được cho phép.

Đây chỉ là một ví dụ. Thứ tự thực tế cần được công bố và hiển thị để người dùng biết severity cuối cùng đến từ đâu.

### 19.2 Rule group và tag

Tag giúp nhóm rule theo chủ đề như security, performance, style, governance hoặc correctness. Người dùng có thể bật một nhóm mà không phải liệt kê từng rule.

Tag không thay thế ID ổn định. Một rule có thể thuộc nhiều nhóm.

## 20. Hiệu năng và incremental analysis

Khi project lớn, chạy mọi rule trên toàn bộ AST sau mỗi lần gõ có thể chậm.

### 20.1 Phạm vi áp dụng

Rule có thể khai báo phạm vi:

- Node đơn lẻ.
- Một declaration.
- Một file.
- Một module.
- Toàn project.

Ví dụ, rule cấm tên biến ngắn có thể chạy trên từng declaration. Rule kiểm tra hai policy xung đột cần xem toàn project.

### 20.2 Dependency của rule với dữ liệu

Để incremental analysis, engine cần biết rule phụ thuộc vào phần dữ liệu nào. Nếu một policy đổi, chỉ rule liên quan đến policy hoặc nhóm policy bị ảnh hưởng cần chạy lại.

Một rule đọc toàn bộ project configuration có thể bị vô hiệu hóa khi profile thay đổi. Một rule chỉ đọc một declaration có thể được tính lại khi node đó đổi.

### 20.3 Cache

Cache kết quả chỉ an toàn nếu key bao gồm mọi yếu tố ảnh hưởng:

- Nội dung hoặc phiên bản semantic node.
- Rule ID và version.
- Cấu hình rule.
- Profile.
- Phiên bản schema.
- Dữ liệu phụ thuộc.

Thiếu một yếu tố có thể khiến engine dùng kết quả cũ sau khi semantics đã thay đổi.

### 20.4 Cancellation và giới hạn

Rule chạy trên IDE nên hỗ trợ cancellation. Rule chạy trên project lớn cần giới hạn số node, thời gian và diagnostic để tránh ảnh hưởng trải nghiệm.

## 21. Kiểm thử rule mở rộng

Mỗi rule nên có test độc lập với semantic engine và test tích hợp với registry/scheduler.

### 21.1 Unit test

Với PolicyOwnerRequiredRule:

- Policy có owner: không có diagnostic.
- Policy thiếu owner: tạo một diagnostic.
- Nhiều policy: chỉ báo các policy thiếu owner.
- Source range trỏ đúng khai báo.
- Rule dùng severity và ID đúng.

Ví dụ:

~~~java
@Test
void reportsPolicyWithoutOwner() {
    SemanticModel model = modelWithPolicyWithoutOwner();
    DiagnosticCollector diagnostics = new DiagnosticCollector();

    rule.evaluate(model, testContext(), diagnostics);

    assertEquals(1, diagnostics.all().size());
    assertEquals(
        "company.policy-owner-required",
        diagnostics.all().getFirst().ruleId()
    );
}
~~~

Tên factory và kiểu collector là ví dụ minh họa. Test thật cần dùng fixture của semantic model trong project.

### 21.2 Registry test

- Rule ID duy nhất được đăng ký.
- ID trùng bị từ chối.
- Provider trả về các rule mong đợi.
- Plugin API version không tương thích bị từ chối.
- Rule bị disable không được scheduler gọi.

### 21.3 Scheduler test

- Dependency được chạy đúng thứ tự.
- Dependency thiếu tạo lỗi cấu hình.
- Chu trình rule dependency được phát hiện.
- Rule độc lập có thể chạy song song khi được phép.
- Cancellation dừng rule đang chạy.
- Diagnostic order ổn định.

### 21.4 Integration test

Chạy toàn bộ pipeline trên DSL source:

1. Parse.
2. Resolve name và type.
3. Nạp profile.
4. Chạy rule mở rộng.
5. Thu thập diagnostics.
6. Kiểm tra code, severity và source range.

Test tích hợp xác nhận extension nhận đúng semantic model mà compiler tạo ra.

### 21.5 Compatibility test

Khi nâng phiên bản compiler hoặc extension API, chạy bộ test với plugin đã phát hành để phát hiện thay đổi hợp đồng. Có thể duy trì một bộ sample plugin nhỏ làm kiểm tra tương thích.

## 22. Những sai lầm thường gặp

### Đưa mọi kiểm tra vào plugin

Các quy tắc cốt lõi như phân giải tên hoặc type safety có thể bị bỏ qua nếu chỉ là extension tùy chọn.

**Cách khắc phục:** giữ invariant ngôn ngữ trong lõi; dành extension cho chính sách có thể thay đổi.

### Không có rule ID ổn định

Dùng tên hiển thị làm ID khiến cấu hình và suppression bị hỏng khi đổi wording.

**Cách khắc phục:** cấp ID có namespace và quản lý vòng đời.

### Cho plugin sửa AST tùy ý

Thứ tự chạy có thể làm thay đổi kết quả và khiến rule khác đọc model không nhất quán.

**Cách khắc phục:** dùng model bất biến trong validation; transformation cần phase riêng.

### Dựa vào thứ tự nạp plugin

Thứ tự classpath không phải hợp đồng dependency.

**Cách khắc phục:** khai báo dependency và dùng scheduler.

### Cấp quá nhiều quyền cho rule

Plugin có thể truy cập file, mạng hoặc dữ liệu không cần thiết.

**Cách khắc phục:** áp dụng quyền tối thiểu, capability nhỏ và cô lập mã không tin cậy.

### Không kiểm soát thời gian chạy

Một rule lặp hoặc duyệt project quá rộng có thể làm treo compiler.

**Cách khắc phục:** cancellation, timeout và giới hạn tài nguyên.

### Không phân biệt lỗi rule với lỗi chương trình DSL

Plugin có thể crash hoặc cấu hình sai. Không nên báo lỗi plugin như thể người dùng viết DSL sai.

**Cách khắc phục:** phân loại infrastructure/plugin failure riêng với semantic diagnostic.

### Cấu hình override không rõ ràng

Nhiều profile có thể đặt severity khác nhau cho cùng rule.

**Cách khắc phục:** định nghĩa thứ tự ưu tiên, hiển thị giá trị cuối và nguồn cấu hình.

### Không kiểm thử tương thích

Thay đổi AST hoặc context có thể làm plugin cũ hỏng.

**Cách khắc phục:** version API, capability negotiation và compatibility tests.

## 23. Quy trình thiết kế hệ thống rule có thể mở rộng

Khi xây dựng semantic rule framework cho DSL, có thể đi theo các bước:

1. **Phân loại kiểm tra:** xác định phần nào là invariant lõi, phần nào là chính sách mở rộng.
2. **Chọn mô hình dữ liệu:** quyết định rule đọc AST, semantic model hay một IR chuyên biệt.
3. **Thiết kế API:** quy định input, output, context, source range và cancellation.
4. **Định danh rule:** tạo namespace, ID ổn định, metadata và version.
5. **Thiết kế registration:** chọn đăng ký tường minh, ServiceLoader hay plugin manifest.
6. **Thiết kế phase:** xác định rule chạy sau parse, name resolution, type checking hay domain analysis.
7. **Khai báo dependency:** tạo thứ tự chạy rõ ràng và phát hiện dependency cycle.
8. **Quản lý cấu hình:** bật/tắt, severity, profile, group và suppression.
9. **Giới hạn quyền:** chỉ cấp dữ liệu và dịch vụ cần thiết; kiểm soát tài nguyên.
10. **Chuẩn hóa diagnostics:** dùng cùng mô hình với compiler và IDE.
11. **Hỗ trợ incremental:** xác định dependency dữ liệu và cache key.
12. **Kiểm thử:** unit, registry, scheduler, integration và compatibility.

Hãy bắt đầu bằng một API nhỏ. Chỉ thêm dependency graph, plugin isolation hoặc incremental scheduling khi quy mô và nhu cầu thực tế đòi hỏi.

## 24. Ví dụ tổng hợp: bộ quy tắc cho DSL chính sách giá

Một tổ chức có profile:

~~~yaml
profile: pricing-production

rules:
  core.undefined-symbol:
    enabled: true
    severity: error

  finance.discount-limit:
    enabled: true
    severity: error
    options:
      maximumPercent: 30

  company.policy-owner-required:
    enabled: true
    severity: warning

  company.audit-reason-required:
    enabled: true
    severity: error
~~~

Các rule:

**core.undefined-symbol**

Rule lõi do compiler cung cấp. Nó chạy sau name resolution và không thể bị tắt nếu ngôn ngữ yêu cầu mọi identifier phải được phân giải.

**finance.discount-limit**

Rule miền kiểm tra discount không vượt maximumPercent. Nó chạy sau type checking để biết literal và đơn vị đã được chuẩn hóa.

**company.policy-owner-required**

Rule governance kiểm tra mỗi policy có owner. Nó chạy trên semantic model của policy.

**company.audit-reason-required**

Rule kiểm tra hành động nhạy cảm có lý do audit. Nó có thể phụ thuộc vào kết quả phân loại action của phase trước.

Scheduler tạo thứ tự:

~~~text
parse
  -> name resolution
  -> type checking
  -> action classification
  -> finance.discount-limit
  -> company.policy-owner-required
  -> company.audit-reason-required
  -> diagnostic aggregation
~~~

Các rule độc lập ở cùng phase có thể chạy song song nếu context bất biến. Diagnostic được sắp xếp theo source range và rule ID để kết quả ổn định.

## 25. Câu hỏi tự kiểm tra

1. Quy tắc ngữ nghĩa lõi khác quy tắc mở rộng như thế nào?
2. Một semantic rule cần hợp đồng và metadata nào?
3. Vì sao rule ID cần ổn định và có namespace?
4. Rule registry có trách nhiệm gì?
5. ServiceLoader có thể được dùng để đăng ký extension Java như thế nào?
6. Vì sao rule nên đọc semantic model bất biến?
7. Rule phase và dependency ảnh hưởng thứ tự chạy ra sao?
8. Khi nào có thể chạy nhiều rule song song?
9. Severity, profile và suppression cần được cấu hình như thế nào?
10. Vì sao plugin cần giới hạn quyền và tài nguyên?
11. Phân biệt lỗi của plugin với diagnostic của chương trình DSL.
12. Rule có thể tạo quick fix trong trường hợp nào?
13. Versioning và capability negotiation giúp tương thích ra sao?
14. Incremental analysis cần biết những dependency nào của rule?
15. Cần những nhóm test nào để bảo đảm framework mở rộng hoạt động ổn định?

Quy tắc có thể mở rộng giúp DSL thích ứng với nhiều miền và chính sách mà không làm lõi ngôn ngữ phình to. Khi API, phase, dependency, quyền truy cập, diagnostic và versioning được định nghĩa rõ, các rule bổ sung có thể hoạt động nhất quán, dễ kiểm thử và dễ quản lý theo từng project.

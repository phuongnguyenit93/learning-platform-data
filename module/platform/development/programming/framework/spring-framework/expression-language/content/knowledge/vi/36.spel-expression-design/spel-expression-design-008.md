# Quản lý SpEL expression như mã nguồn có phiên bản và review

Trong ứng dụng Spring, một SpEL expression có thể quyết định cách tính giá trị, lọc dữ liệu, hiển thị tính năng hoặc thực thi một quy tắc nghiệp vụ. Khi expression được lưu trong cấu hình, database hoặc hệ thống quản trị, nó vẫn là logic có thể ảnh hưởng đến hành vi ứng dụng. Vì vậy, cần quản lý expression có kỷ luật tương tự mã nguồn: có định danh ổn định, lịch sử phiên bản, người chịu trách nhiệm, review, kiểm thử và quy trình phát hành.

Không nên xem expression là một chuỗi có thể sửa trực tiếp trong production mà không để lại dấu vết. Một thay đổi nhỏ như sửa ngưỡng, đổi property hoặc thêm lời gọi method có thể làm thay đổi kết quả nghiệp vụ. Quản lý phiên bản giúp biết chính xác expression nào đang chạy, ai đã thay đổi, thay đổi được kiểm tra ra sao và có thể quay lại phiên bản trước như thế nào.

Bài này trình bày cách thiết kế vòng đời cho expression, từ lưu trữ và đặt định danh đến review, test, phát hành, rollback và vận hành runtime.

## 1. Vì sao expression cần được quản lý như mã nguồn?

Expression có thể ngắn hơn một class Java nhưng vẫn chứa logic thực thi. Ví dụ:

~~~text
status == 'ACTIVE' and balance >= 100
~~~

Thay đổi ngưỡng 100 thành 500 có thể làm một nhóm tài khoản không còn đủ điều kiện. Thêm lời gọi method hoặc tham chiếu bean có thể mở rộng đáng kể hành vi được thực hiện khi đánh giá.

Nếu expression chỉ được sửa trong database mà không có version hoặc audit trail, nhóm phát triển khó trả lời các câu hỏi:

- Giá trị nào đang chạy trong môi trường production?
- Ai đã thay đổi expression và vào thời điểm nào?
- Thay đổi đó đã được review và kiểm thử chưa?
- Expression có tương thích với phiên bản DTO và property hiện tại không?
- Khi phát sinh lỗi, có thể khôi phục phiên bản trước một cách xác định không?

Quản lý expression như mã nguồn tạo ra lịch sử thay đổi có thể truy vết và giúp kiểm soát tác động của từng lần phát hành.

## 2. Đặt định danh ổn định cho mỗi expression

Mỗi expression nên có một ID ổn định, độc lập với nội dung và số phiên bản.

Ví dụ:

~~~text
account.eligibility
checkout.free-shipping
invoice.tax-rate
document.read-policy
~~~

ID dùng để tham chiếu expression trong cấu hình, log, test và hệ thống phát hành. Không nên dùng chính nội dung expression làm định danh, vì nội dung sẽ thay đổi theo từng revision.

Một bản ghi expression có thể gồm các trường:

| Trường | Mục đích |
|---|---|
| expressionId | Định danh ổn định của quy tắc |
| version | Phiên bản bất biến của nội dung |
| expressionText | Chuỗi SpEL được lưu |
| description | Mô tả mục đích nghiệp vụ |
| owner | Nhóm hoặc người chịu trách nhiệm |
| inputSchemaVersion | Phiên bản cấu trúc dữ liệu đầu vào |
| expectedResultType | Kiểu kết quả được mong đợi |
| status | Draft, reviewed, approved, active hoặc retired |
| createdAt / createdBy | Thời điểm và người tạo |
| reviewedAt / reviewedBy | Thời điểm và người review |
| changeReference | Liên kết đến pull request hoặc ticket |

Tách expressionId khỏi version giúp một quy tắc có thể có nhiều phiên bản mà các hệ thống gọi vẫn dùng cùng một định danh.

## 3. Lưu revision bất biến

Khi một expression đã được phê duyệt hoặc phát hành, không sửa trực tiếp nội dung của revision đó. Thay đổi tạo ra revision mới.

Ví dụ:

| Expression ID | Version | Nội dung |
|---|---:|---|
| account.eligibility | 1 | status == 'ACTIVE' |
| account.eligibility | 2 | status == 'ACTIVE' and age >= 18 |
| account.eligibility | 3 | status == 'ACTIVE' and age >= 21 |

Revision 1, 2 và 3 vẫn được giữ để tra cứu lịch sử. Trạng thái active chỉ xác định revision đang được dùng cho môi trường hoặc tenant cụ thể.

Không ghi đè nội dung của một revision đã phát hành. Nếu cần sửa lỗi, tạo revision mới và liên kết nó với revision trước. Cách làm này giúp audit, rollback và tái hiện kết quả của một quyết định cũ.

Có thể dùng số nguyên tăng dần cho version. Nếu tổ chức có quy ước rõ ràng, cũng có thể dùng semantic versioning hoặc mã build. Điều quan trọng là version phải duy nhất, có thứ tự hoặc có quan hệ kế thừa rõ ràng, và không bị tái sử dụng cho nội dung khác.

## 4. Quản lý expression trong source control

Nếu expression thay đổi cùng chu kỳ phát triển phần mềm, lưu chúng trong repository giúp tận dụng quy trình Git hiện có: branch, pull request, diff, review và release tag.

Ví dụ cấu trúc thư mục:

~~~text
config/
  expressions/
    account-eligibility.spel
    free-shipping.spel
    document-read-policy.spel
  expression-manifest.yml
  expression-tests/
    AccountEligibilityTest.java
    FreeShippingTest.java
~~~

Manifest có thể mô tả ID, file, version và kiểu kết quả:

~~~yaml
expressions:
  - id: account.eligibility
    version: 3
    file: expressions/account-eligibility.spel
    inputSchema: account-rule-view-v2
    resultType: Boolean
    owner: account-platform
~~~

Trong thực tế, schema và format manifest cần được tổ chức thống nhất với công cụ build của dự án. Manifest là metadata quản lý, còn file expression chứa nội dung SpEL nguyên gốc.

Ưu điểm của source control:

- Xem được diff chính xác giữa các revision.
- Review expression cùng với thay đổi DTO hoặc Java code liên quan.
- Gắn revision với commit hoặc release.
- Chạy test tự động trong CI.
- Khôi phục phiên bản trước bằng một thay đổi được review.

Nếu nghiệp vụ yêu cầu người dùng quản trị thay đổi rule mà không cần phát hành ứng dụng, có thể lưu revision trong database hoặc rule service. Khi đó vẫn nên có export/import, audit log, approval và cơ chế đồng bộ revision đã duyệt về kho lưu trữ có kiểm soát.

## 5. Ghi lại mục đích và hợp đồng dữ liệu

Expression chỉ có ý nghĩa khi biết nó đọc dữ liệu nào và kết quả được sử dụng ra sao. Mỗi expression nên có mô tả nghiệp vụ cùng hợp đồng đầu vào/đầu ra.

Ví dụ:

~~~text
ID: account.eligibility
Mục đích: Xác định tài khoản đủ điều kiện sử dụng tính năng.
Root type: AccountRuleView
Input schema: account-rule-view-v2
Result type: Boolean
Allowed properties: status, age, balance
Owner: account-platform
~~~

Hợp đồng đầu vào nên mô tả:

- Các property được phép đọc.
- Kiểu dữ liệu của từng property.
- Property nào có thể null.
- Collection có thể có kích thước tối đa bao nhiêu.
- Quy tắc chuyển đổi hoặc chuẩn hóa dữ liệu.
- Phiên bản DTO hoặc schema mà expression phụ thuộc.

Hợp đồng đầu ra nên xác định kiểu kết quả, ví dụ Boolean, String hoặc BigDecimal, cùng ý nghĩa nghiệp vụ của từng giá trị.

Nếu đổi tên property hoặc thay đổi kiểu dữ liệu, hãy xem đó là thay đổi tương thích cần được kiểm tra với tất cả expression phụ thuộc vào schema đó.

## 6. Review expression như review code

Review không chỉ kiểm tra expression có parse được hay không. Reviewer cần hiểu ý nghĩa nghiệp vụ và các đối tượng mà expression có thể truy cập.

Một quy trình review có thể kiểm tra:

1. ID và mô tả có phản ánh đúng mục đích không?
2. Expression có đọc đúng property và dùng đúng kiểu dữ liệu không?
3. Các trường hợp null, rỗng và giá trị biên đã được xác định chưa?
4. Expression có gọi method hoặc tham chiếu bean không? Nếu có, lý do và quyền truy cập đã rõ chưa?
5. Root object có chứa dữ liệu hoặc hành vi vượt quá nhu cầu không?
6. Kết quả có đúng kiểu mà nơi gọi mong đợi không?
7. Có test cho kết quả đúng, sai và các trường hợp biên không?
8. Thay đổi có tương thích với phiên bản input schema đang dùng không?
9. Có phương án phát hành và rollback không?

Review nên có người hiểu nghiệp vụ và người hiểu kỹ thuật khi expression ảnh hưởng đến quyết định quan trọng. Không nên phê duyệt chỉ vì biểu thức ngắn hoặc dễ đọc.

## 7. Viết test gắn với từng revision

Mỗi revision nên có bộ test thể hiện các trường hợp đầu vào và kết quả mong đợi. Test dùng parser và EvaluationContext trực tiếp nếu mục tiêu là kiểm tra expression.

Ví dụ:

~~~java
class AccountEligibilityTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    private final Expression expression =
            parser.parseExpression(
                    "status == 'ACTIVE' and age >= 18 and balance > 0"
            );

    @Test
    void acceptsEligibleAccount() {
        AccountRuleView source =
                new AccountRuleView(
                        "ACTIVE",
                        25,
                        new BigDecimal("150.00")
                );

        SimpleEvaluationContext context =
                SimpleEvaluationContext.forReadOnlyDataBinding()
                        .build();

        Boolean result = expression.getValue(
                context,
                source,
                Boolean.class
        );

        assertTrue(result);
    }

    @Test
    void rejectsInactiveAccount() {
        AccountRuleView source =
                new AccountRuleView(
                        "SUSPENDED",
                        25,
                        new BigDecimal("150.00")
                );

        SimpleEvaluationContext context =
                SimpleEvaluationContext.forReadOnlyDataBinding()
                        .build();

        Boolean result = expression.getValue(
                context,
                source,
                Boolean.class
        );

        assertFalse(result);
    }
}
~~~

Bộ test nên bao gồm:

- Trường hợp thông thường trả về true.
- Trường hợp thông thường trả về false.
- Giá trị đúng tại ngưỡng và ngay hai phía của ngưỡng.
- Null và property lồng nhau thiếu dữ liệu.
- Collection rỗng hoặc collection đạt kích thước giới hạn.
- Kiểu kết quả không đúng hợp đồng.
- Property không tồn tại sau khi schema thay đổi.
- Lỗi parse và lỗi evaluation.

Test phải gắn với revision cụ thể để có thể tái hiện kết quả của phiên bản đã phát hành. Khi expression thay đổi, chạy lại toàn bộ test liên quan thay vì chỉ sửa expected value cho test đang lỗi.

## 8. Kiểm tra tương thích với input schema

Expression thường phụ thuộc vào property của DTO hoặc read model. Thay đổi schema có thể làm expression cũ không còn chạy.

Ví dụ revision 2 dùng property accountStatus:

~~~text
accountStatus == 'ACTIVE'
~~~

Nếu DTO mới đổi tên property thành status, expression cũ có thể phát sinh lỗi evaluation.

Có thể quản lý bằng một trong các cách:

- Gắn mỗi revision với inputSchemaVersion cụ thể.
- Duy trì DTO adapter tương thích trong thời gian chuyển đổi.
- Tạo revision expression mới cùng thời điểm schema thay đổi.
- Kiểm tra toàn bộ expression active trước khi phát hành schema mới.
- Có chính sách thời hạn ngừng hỗ trợ schema cũ.

Không nên đổi tên hoặc xóa property rồi đợi lỗi xuất hiện trong production. CI có thể nạp tất cả expression đã đăng ký và đánh giá chúng trên fixture tương ứng với schema mục tiêu.

## 9. Quy trình phát hành theo môi trường

Một expression revision nên đi qua các trạng thái rõ ràng. Ví dụ:

<escape>Draft → Reviewed → Approved → Staged → Active → Retired</escape>

- Draft: tác giả đang soạn và chạy test ban đầu.
- Reviewed: đã có review về kỹ thuật và nghiệp vụ.
- Approved: đã được người có thẩm quyền chấp thuận.
- Staged: được triển khai vào môi trường thử nghiệm hoặc một nhóm nhỏ.
- Active: được chọn để xử lý request thực tế.
- Retired: không còn được chọn cho request mới nhưng vẫn giữ lịch sử.

Không nên cho phép một bản nháp tự động trở thành active chỉ vì nó được lưu thành công. Việc lưu revision và việc kích hoạt revision là hai thao tác khác nhau.

Có thể phát hành theo môi trường development, staging và production. Ở mỗi bước, giữ lại version và cấu hình kích hoạt để biết môi trường nào đang dùng revision nào.

## 10. Kích hoạt revision an toàn

Thay vì cập nhật trực tiếp expression text đang chạy, hãy dùng một tham chiếu active version:

~~~text
account.eligibility -> version 3
~~~

Quá trình kích hoạt có thể thực hiện theo các bước:

1. Xác định revision đã được approve.
2. Xác nhận test và input schema tương thích.
3. Nạp revision vào môi trường staging.
4. Đánh giá trên bộ dữ liệu mẫu hoặc shadow traffic nếu phù hợp.
5. So sánh kết quả với revision đang active.
6. Phê duyệt chuyển active pointer sang revision mới.
7. Theo dõi lỗi parse/evaluation và phân bố kết quả sau khi chuyển.

Active pointer nên được cập nhật nguyên tử hoặc qua một cơ chế cấu hình có tính nhất quán rõ ràng. Tránh trạng thái một request dùng nửa nội dung của version cũ và nửa metadata của version mới.

Nếu nhiều tenant hoặc nhóm người dùng có phiên bản khác nhau, active version cần được xác định theo scope đó và ghi rõ trong log.

## 11. Rollback và tái hiện quyết định cũ

Vì revision cũ không bị ghi đè, rollback có thể là thao tác chuyển active pointer về một revision đã biết là ổn định.

Ví dụ:

~~~text
account.eligibility
  active: 3
  previous: 2
~~~

Nếu version 3 gây lỗi, có thể kích hoạt lại version 2 sau khi xác nhận input schema và dependency vẫn tương thích.

Để tái hiện một quyết định đã xảy ra, cần lưu đủ thông tin:

- Expression ID và version đã được dùng.
- Input schema version.
- Phiên bản ứng dụng hoặc rule runtime.
- Thời điểm đánh giá.
- Correlation ID hoặc ID nghiệp vụ phù hợp.
- Kết quả và mã lỗi nếu có.

Không nhất thiết phải lưu toàn bộ dữ liệu cá nhân đầu vào trong log. Có thể lưu snapshot đã được giảm thiểu hoặc dữ liệu kiểm thử có kiểm soát nếu cần tái hiện. Tuân thủ chính sách bảo vệ dữ liệu của ứng dụng.

## 12. Quản lý cache Expression và cập nhật revision

Phân tích expression thành đối tượng Expression có thể được cache để tránh parse lại cùng một nội dung liên tục. Cache nên được khóa theo định danh và version, không chỉ theo ID.

Ví dụ key:

~~~text
account.eligibility:v3
~~~

Khi version mới được kích hoạt, tạo cache entry mới hoặc làm mới cache theo cơ chế có kiểm soát. Không sửa một Expression object đang được request khác sử dụng bằng cách thay đổi context dùng chung.

Một số nguyên tắc:

- Cache có giới hạn dung lượng.
- Dùng key gồm expression ID và revision.
- Không dùng cache không giới hạn cho expression do người dùng tạo.
- Không chia sẻ EvaluationContext mutable giữa các request.
- Tạo context/root object phù hợp cho từng lần đánh giá.
- Xác định cách invalidation khi active version thay đổi.
- Theo dõi số cache hit, miss và lỗi parse.

Parser và Expression có thể được tái sử dụng theo thiết kế phù hợp, nhưng context thường chứa biến và root object riêng của từng lần đánh giá. Quản lý hai vòng đời này tách biệt giúp tránh rò rỉ dữ liệu giữa request.

## 13. Audit trail và quyền thay đổi

Hệ thống quản lý expression nên ghi lại ai đã tạo, sửa, review, approve, kích hoạt hoặc retire một revision.

Audit record có thể gồm:

| Thuộc tính | Nội dung |
|---|---|
| expressionId | ID của quy tắc |
| fromVersion / toVersion | Revision trước và sau |
| actor | Người hoặc service thực hiện |
| action | Create, edit, review, approve, activate, rollback |
| timestamp | Thời điểm |
| changeReference | Pull request, ticket hoặc lý do |
| environment | Môi trường bị ảnh hưởng |
| outcome | Thành công hoặc thất bại |

Phân quyền nên tách vai trò:

- Author có thể tạo revision.
- Reviewer có thể review và yêu cầu sửa.
- Approver có thể phê duyệt.
- Operator có thể kích hoạt revision đã được phê duyệt.
- Auditor có thể đọc lịch sử và trạng thái.

Một người có thể đảm nhiệm nhiều vai trò theo chính sách tổ chức, nhưng các thao tác nhạy cảm cần có dấu vết và quy trình kiểm soát phù hợp.

## 14. Kiểm soát bảo mật của expression đã được version hóa

Versioning và review không tự làm expression an toàn. Expression vẫn được đánh giá trong EvaluationContext với những khả năng được cung cấp.

Đối với expression được lưu hoặc thay đổi ngoài mã nguồn:

- Xem nội dung như mã thực thi, không phải chuỗi cấu hình vô hại.
- Chỉ cho phép người có quyền tạo hoặc sửa revision.
- Giới hạn root object và property được phép truy cập.
- Không cung cấp bean reference, type access hoặc method invocation nếu không cần.
- Dùng SimpleEvaluationContext khi tập tính năng giới hạn đáp ứng yêu cầu.
- Không nối dữ liệu request trực tiếp vào expression text.
- Xác thực kiểu kết quả và giới hạn tài nguyên đầu vào.
- Không cho phép revision chưa review tự động được kích hoạt.

Nếu người dùng cần tự xây dựng điều kiện, cân nhắc rule model hoặc DSL có allowlist. Không dựa vào việc parse thành công, hash nội dung hoặc có version để thay thế kiểm soát quyền và giới hạn khả năng đánh giá.

## 15. Theo dõi và xử lý sự cố sau phát hành

Sau khi kích hoạt revision mới, theo dõi các chỉ số giúp phát hiện lỗi sớm:

- Số lần đánh giá theo expression ID và version.
- Tỷ lệ kết quả true/false hoặc phân bố kết quả phù hợp với nghiệp vụ.
- Lỗi parse và evaluation.
- Thời gian đánh giá.
- Số lần cache miss.
- Tần suất fallback hoặc sử dụng revision cũ.
- Chênh lệch kết quả giữa revision mới và cũ trong giai đoạn thử nghiệm.

Không ghi nội dung nhạy cảm của root object hoặc expression vào log nếu không cần thiết. Dùng expression ID, version, correlation ID và mã lỗi để truy vết.

Khi có sự cố:

1. Xác định expression ID và version đang được sử dụng.
2. Kiểm tra thay đổi gần nhất và người phê duyệt.
3. Xác định lỗi nằm ở parse, evaluation, schema, dữ liệu hay logic nghiệp vụ.
4. Nếu ảnh hưởng nghiêm trọng, chuyển active pointer về revision ổn định.
5. Tạo revision sửa lỗi và bổ sung test tái hiện sự cố.
6. Ghi lại nguyên nhân và kết quả xử lý trong change history.

## 16. Ví dụ mô hình dữ liệu quản lý revision

Một mô hình đơn giản có thể tách thông tin định danh khỏi nội dung từng revision:

~~~java
public class ExpressionDefinition {
    private final String id;
    private final String description;
    private final String owner;

    public ExpressionDefinition(
            String id,
            String description,
            String owner) {
        this.id = id;
        this.description = description;
        this.owner = owner;
    }

    public String getId() {
        return id;
    }

    public String getDescription() {
        return description;
    }

    public String getOwner() {
        return owner;
    }
}

public class ExpressionRevision {
    private final String expressionId;
    private final int version;
    private final String expressionText;
    private final String inputSchemaVersion;
    private final String resultType;

    public ExpressionRevision(
            String expressionId,
            int version,
            String expressionText,
            String inputSchemaVersion,
            String resultType) {
        this.expressionId = expressionId;
        this.version = version;
        this.expressionText = expressionText;
        this.inputSchemaVersion = inputSchemaVersion;
        this.resultType = resultType;
    }

    public String getExpressionId() {
        return expressionId;
    }

    public int getVersion() {
        return version;
    }

    public String getExpressionText() {
        return expressionText;
    }

    public String getInputSchemaVersion() {
        return inputSchemaVersion;
    }

    public String getResultType() {
        return resultType;
    }
}
~~~

Mô hình trên chỉ minh họa cách tách metadata và revision. Ứng dụng thực tế có thể lưu các đối tượng này trong Git, database hoặc một rule registry. Nên giữ revision bất biến sau khi approve và lưu trạng thái active ở một cấu trúc riêng.

## 17. Checklist cho một thay đổi expression

| Giai đoạn | Điều cần xác nhận |
|---|---|
| Authoring | ID, mục đích, owner và input schema đã rõ |
| Revision | Tạo version mới; không ghi đè version đã phát hành |
| Review | Có review nghiệp vụ, property access và hành vi method/bean |
| Testing | Có test đúng, sai, null, biên và kiểu kết quả |
| Compatibility | DTO và schema tương thích với revision |
| Approval | Người có thẩm quyền đã phê duyệt |
| Staging | Đã kiểm tra trên môi trường và dữ liệu thử nghiệm |
| Activation | Active pointer được chuyển có kiểm soát |
| Monitoring | Có metric, log và cảnh báo cho version mới |
| Rollback | Có thể quay lại revision ổn định |
| Audit | Actor, thời điểm và change reference được lưu |

## 18. Ghi nhớ

- SpEL expression chứa logic có thể ảnh hưởng đến hành vi ứng dụng, vì vậy cần quản lý như mã nguồn.
- Mỗi expression nên có ID ổn định, owner, mô tả, input schema và kiểu kết quả.
- Revision đã phát hành nên bất biến; mọi thay đổi tạo version mới.
- Source control giúp review diff, chạy test và liên kết expression với commit/release.
- Review phải xét cả ý nghĩa nghiệp vụ, property, method, quyền truy cập và trường hợp null/biên.
- Gắn test với từng revision để có thể tái hiện kết quả.
- Kiểm tra tương thích giữa expression version và input schema version.
- Tách trạng thái draft, approved và active; lưu revision không đồng nghĩa với kích hoạt.
- Rollback bằng cách chuyển active pointer về revision ổn định.
- Cache Expression theo ID và version; không chia sẻ EvaluationContext mutable giữa request.
- Audit create, review, approve, activate và rollback.
- Versioning không thay thế kiểm soát bảo mật, quyền truy cập hoặc giới hạn tài nguyên của EvaluationContext.

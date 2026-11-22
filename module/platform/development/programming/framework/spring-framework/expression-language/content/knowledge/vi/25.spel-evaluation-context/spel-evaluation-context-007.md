# Xây context theo từng use case thay vì dùng context toàn quyền

EvaluationContext quyết định SpEL có thể nhìn thấy dữ liệu nào và thực hiện những thao tác nào khi đánh giá biểu thức. Một context có thể cung cấp root object, biến, function, property accessor, method resolver, constructor resolver, TypeLocator và bean resolver. Cấu hình càng rộng thì biểu thức càng linh hoạt, nhưng phạm vi tác động và rủi ro cũng càng lớn.

Vì vậy, ứng dụng nên xây context theo từng use case. Quy tắc chỉ đọc thuộc tính nên dùng context chỉ đọc; quy tắc cần một số phép gọi method nên chỉ bật những method đã được phép; biểu thức cần type reference hoặc constructor phải có context riêng với giới hạn rõ ràng. Không nên dùng một StandardEvaluationContext nhiều quyền cho mọi loại biểu thức chỉ vì nó tiện khởi tạo.

## 1. EvaluationContext là ranh giới giữa biểu thức và ứng dụng

SpEL không tự biết đối tượng nghiệp vụ nào được phép truy cập. Ứng dụng cung cấp môi trường đánh giá thông qua EvaluationContext.

Context có thể chứa hoặc điều khiển:

- Root object: đối tượng gốc mà property path không có tiền tố bắt đầu đọc.
- Variables: các giá trị được tham chiếu bằng tiền tố #.
- Functions: các Method được đăng ký để biểu thức gọi bằng cú pháp function.
- PropertyAccessors: cách đọc hoặc ghi property trên các đối tượng.
- MethodResolvers: cách tìm và gọi method.
- ConstructorResolvers: cách tìm và gọi constructor.
- TypeLocator: cách phân giải tên lớp trong T(...).
- BeanResolver: cách biểu thức tham chiếu bean theo tên.

Không phải use case nào cũng cần mọi khả năng này. Ví dụ, một biểu thức chỉ kiểm tra order.total có thể chỉ cần root object và quyền đọc property. Nó không cần tạo object mới, gọi service, truy cập bean hoặc gọi method tùy ý.

Hãy coi context là hợp đồng về những gì một biểu thức được phép làm. Khi hợp đồng được thiết kế rõ, rule dễ hiểu hơn và dễ kiểm soát hơn.

## 2. Phân biệt StandardEvaluationContext và SimpleEvaluationContext

Spring cung cấp hai lựa chọn thường gặp với mức tính năng khác nhau.

### StandardEvaluationContext

StandardEvaluationContext cung cấp bộ khả năng SpEL rộng. Theo cấu hình mặc định, nó có các cơ chế reflective để truy cập property, gọi method và tạo object; nó cũng dùng StandardTypeLocator để phân giải type reference. Ứng dụng có thể đăng ký biến, function, resolver và các thành phần tùy chỉnh.

Ví dụ khởi tạo:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

Context này phù hợp khi biểu thức thực sự cần các tính năng nâng cao, nhưng cần cấu hình có chủ đích. Nếu đưa đối tượng nhiều quyền vào root hoặc cho phép gọi method rộng, biểu thức có thể tác động tới nhiều phần của ứng dụng hơn dự định.

Bean reference không tự xuất hiện chỉ vì dùng StandardEvaluationContext; ứng dụng phải cấu hình BeanResolver nếu muốn hỗ trợ tham chiếu bean. Dù vậy, các khả năng reflective mặc định đã đủ rộng để cần xem xét cẩn thận nguồn biểu thức và object graph được cung cấp.

### SimpleEvaluationContext

SimpleEvaluationContext được thiết kế cho một tập con SpEL giới hạn hơn, thường phù hợp với các quy tắc truy cập dữ liệu. Builder cho phép chọn chế độ property access và có thể bật instance method access khi use case cần.

Ví dụ chỉ đọc dữ liệu:

    EvaluationContext context =
            SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .build();

Nếu cần cho phép instance method theo nhu cầu cụ thể:

    EvaluationContext context =
            SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .withInstanceMethods()
                    .build();

SimpleEvaluationContext không hỗ trợ type references, constructor references hoặc bean references theo mặc định. Vì vậy, nó là lựa chọn phù hợp khi biểu thức chỉ cần đọc dữ liệu và một tập thao tác giới hạn. Hãy kiểm tra đúng builder option mà use case cần thay vì bật thêm khả năng theo thói quen.

## 3. Bắt đầu từ yêu cầu nhỏ nhất

Trước khi tạo context, hãy mô tả chính xác biểu thức cần làm gì. Một số câu hỏi hữu ích:

1. Biểu thức chỉ đọc property hay cần ghi giá trị?
2. Nó có cần gọi method không? Nếu có, method nào và trên kiểu đối tượng nào?
3. Nó có cần T(...) để tham chiếu lớp hoặc new để tạo object không?
4. Nó có cần truy cập Spring bean không?
5. Những biến và function nào thật sự cần thiết?
6. Root object có chứa dữ liệu hoặc hành vi vượt quá nhu cầu không?
7. Ai có quyền tạo hoặc sửa biểu thức: đội phát triển, quản trị viên hay người dùng cuối?

Nếu câu trả lời chỉ là “đọc vài thuộc tính và so sánh”, SimpleEvaluationContext ở chế độ read-only thường là điểm bắt đầu phù hợp. Nếu cần một function cụ thể, có thể cung cấp function đó trong context riêng. Nếu cần type reference hoặc constructor, hãy dùng StandardEvaluationContext nhưng giới hạn các resolver và kiểu được phép.

Không nên chọn context chỉ dựa trên việc biểu thức hiện tại chạy được. Hãy xét cả những biểu thức khác có thể được đánh giá trong cùng use case và dữ liệu mà chúng được phép nhìn thấy.

## 4. Use case chỉ đọc property

Ví dụ một quy tắc xác định đơn hàng có đạt ngưỡng tối thiểu hay không. Biểu thức chỉ cần đọc total và minimumTotal từ một DTO đầu vào.

    public class OrderRuleInput {
        private final BigDecimal total;
        private final BigDecimal minimumTotal;

        public OrderRuleInput(
                BigDecimal total, BigDecimal minimumTotal) {
            this.total = total;
            this.minimumTotal = minimumTotal;
        }

        public BigDecimal getTotal() {
            return total;
        }

        public BigDecimal getMinimumTotal() {
            return minimumTotal;
        }
    }

Đánh giá bằng context chỉ đọc:

    OrderRuleInput input =
            new OrderRuleInput(orderTotal, configuredMinimum);

    EvaluationContext context =
            SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("total >= minimumTotal");

    Boolean accepted =
            expression.getValue(context, input, Boolean.class);

Root object là OrderRuleInput; total và minimumTotal được đọc từ hai property của DTO. Context không cần quyền gọi service, truy cập bean hay tạo object.

Nếu cần truyền biến được đặt tên bằng setVariable(), hãy chọn một context có API biến phù hợp, chẳng hạn StandardEvaluationContext đã được giới hạn theo nhu cầu. Với quy tắc chỉ cần vài giá trị, một DTO đầu vào nhỏ cũng giúp hợp đồng dữ liệu rõ ràng và tránh phụ thuộc vào nhiều biến rời rạc.

## 5. Use case cần instance method có giới hạn

Đôi khi quy tắc cần gọi một method đơn giản trên dữ liệu đầu vào, chẳng hạn kiểm tra một chuỗi hoặc lấy giá trị đã chuẩn hóa. SimpleEvaluationContext có thể bật instance method access qua builder khi cần.

    EvaluationContext context =
            SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .withInstanceMethods()
                    .build();

Ví dụ biểu thức:

    customerCode.startsWith('AB-')

Việc bật instance methods mở thêm khả năng gọi method trên đối tượng mà property accessor cung cấp. Do đó, chỉ dùng tùy chọn này khi đó là một phần của hợp đồng use case. Không đưa service, repository hoặc object có nhiều hành vi vào root chỉ để gọi một method tiện lợi.

Nếu chỉ cần một phép kiểm tra cụ thể, một DTO có property đã tính sẵn hoặc một function hẹp do ứng dụng cung cấp có thể làm phạm vi truy cập dễ kiểm soát hơn. Hãy cân nhắc chi phí của việc mở method access so với việc chuẩn bị dữ liệu trước.

## 6. Use case cần function do ứng dụng cho phép

Nếu rule cần gọi một phép tính Java được chọn trước, có thể đăng ký một public static method dưới dạng function. Điều này phù hợp khi muốn biểu thức có một bí danh ổn định nhưng không muốn cho phép gọi mọi method trên root object.

Ví dụ:

    Method normalizeMethod =
            RuleFunctions.class.getMethod(
                    "normalizeCode", String.class);

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    context.setMethodResolvers(Collections.emptyList());
    context.setConstructorResolvers(Collections.emptyList());

    context.registerFunction(
            "normalizeCode", normalizeMethod);

    Expression expression =
            parser.parseExpression(
                    "#normalizeCode(customerCode)");

    String code =
            expression.getValue(context, String.class);

Function đã đăng ký vẫn là mã Java chạy với quyền của ứng dụng. Vì vậy, chỉ đăng ký method cần thiết, ưu tiên hàm thuần, có đầu vào/đầu ra rõ ràng và không thực hiện I/O hoặc thay đổi trạng thái nghiệp vụ.

Trong ví dụ, các method resolver và constructor resolver mặc định được loại bỏ để biểu thức không thể gọi method instance hoặc tạo object tùy ý qua những resolver đó. Function được đăng ký trực tiếp trong context. Nếu biểu thức còn cần type reference, phải xem xét và cấu hình TypeLocator riêng; không mặc định bật mọi capability chỉ vì function cần StandardEvaluationContext.

Không đăng ký toàn bộ utility class hoặc nhiều function chỉ để tiện cho những rule có thể xuất hiện trong tương lai. Hãy cung cấp đúng tập function mà từng nhóm rule cần.

## 7. Use case cần type reference hoặc constructor

Một số biểu thức cần T(...) để tham chiếu kiểu, gọi thành viên static hoặc dùng new để tạo object. SimpleEvaluationContext không hỗ trợ các tính năng này theo mặc định. Khi thật sự cần, có thể dùng StandardEvaluationContext.

Ví dụ type reference:

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    Expression expression =
            parser.parseExpression(
                    "T(java.time.LocalDate).of(2026, 11, 12)");

    LocalDate date =
            expression.getValue(context, LocalDate.class);

Tuy nhiên, StandardTypeLocator mặc định có thể phân giải nhiều lớp trên classpath. Nếu biểu thức đến từ nguồn không hoàn toàn đáng tin cậy, hãy giới hạn TypeLocator bằng danh sách kiểu được phép thay vì cho phép tham chiếu lớp tùy ý.

Tương tự, constructor resolver mặc định của StandardEvaluationContext có thể cho phép tạo instance của kiểu được phân giải. Nếu use case không cần new, hãy loại bỏ constructor resolver hoặc thay bằng resolver chỉ cho phép constructor đã chọn.

Đừng dùng registerImport() như một allowlist bảo mật. Đăng ký package prefix giúp rút gọn tên lớp; nó không phải cơ chế giới hạn chặt chẽ các kiểu mà biểu thức có thể tham chiếu.

## 8. Giới hạn method và constructor resolver

StandardEvaluationContext cho phép thay danh sách resolver. Nếu use case không cần gọi method, có thể loại bỏ method resolver mặc định:

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    context.setMethodResolvers(Collections.emptyList());

Tương tự, nếu biểu thức không cần tạo instance:

    context.setConstructorResolvers(Collections.emptyList());

Các đoạn trên minh họa việc tắt toàn bộ khả năng tương ứng. Nếu cần một số thao tác được chọn, hãy cung cấp resolver tùy chỉnh có allowlist method hoặc constructor cụ thể. Việc chỉ xóa resolver mặc định sẽ khiến mọi method call hoặc constructor call không có resolver phù hợp bị từ chối.

Cần nhớ rằng method invocation và property access là hai khả năng khác nhau. Đọc property JavaBean thường đi qua getter thông qua PropertyAccessor; việc bỏ MethodResolver không tự động biến mọi getter thành dữ liệu không thể đọc. Nếu cần chỉ đọc, hãy dùng context read-only hoặc PropertyAccessor chỉ đọc phù hợp.

## 9. Giới hạn property access và object graph

Root object là một phần quan trọng của bề mặt truy cập. Nếu đưa một JPA entity lớn hoặc một service object vào context, biểu thức có thể nhìn thấy nhiều property và getter hơn mức cần thiết.

Nên ưu tiên:

- DTO hoặc projection object chỉ chứa dữ liệu phục vụ rule.
- Property accessor chỉ đọc khi rule không cần cập nhật dữ liệu.
- Object graph nông, có kích thước và quan hệ được kiểm soát.
- Tránh getter có side effect, truy vấn lazy không mong muốn hoặc chi phí cao.
- Không đưa password, token, thông tin thanh toán hoặc dữ liệu bí mật vào root nếu rule không cần.

Nếu cần property accessor tùy chỉnh, hãy đăng ký đúng accessor cho kiểu dữ liệu cụ thể. Không thêm accessor tổng quát có thể đọc mọi field hoặc gọi mọi getter trên mọi object trong ứng dụng.

Đọc property không phải lúc nào cũng là thao tác thuần. Getter có thể chạy mã Java, tải dữ liệu hoặc ném exception. Hãy xem xét hành vi của object đầu vào chứ không chỉ tên property trong biểu thức.

## 10. BeanResolver và quyền truy cập Spring bean

Biểu thức SpEL có thể tham chiếu bean bằng cú pháp @beanName khi EvaluationContext được cấu hình BeanResolver. Khả năng này tiện cho một số cấu hình do ứng dụng quản lý, nhưng nó có thể mở đường tới service hoặc component có nhiều quyền.

Không nên cấu hình BeanResolver cho mọi context chỉ vì một rule cần truy cập một bean. Nếu biểu thức chỉ cần kết quả của một phép tính, hãy tính trước trong Java và truyền kết quả qua biến hoặc root DTO. Nếu thực sự cần bean, chỉ cho phép biểu thức đáng tin cậy và cân nhắc một BeanResolver giới hạn theo danh sách bean được phép.

StandardEvaluationContext không tự có quyền truy cập tất cả bean trong ApplicationContext nếu chưa cấu hình BeanResolver. Tuy nhiên, một khi ứng dụng gắn BeanFactoryResolver hoặc resolver tương tự, phạm vi bean mà biểu thức có thể tham chiếu cần được quản lý rõ ràng.

Service được gọi từ biểu thức có thể thực hiện I/O, ghi dữ liệu hoặc hành động bên ngoài. Không coi một biểu thức chỉ là phép tính vô hại nếu nó có quyền gọi các bean đó.

## 11. Tạo context riêng theo nhóm use case

Có thể đóng gói việc xây context vào các factory method có tên theo mục đích. Ví dụ:

    public final class RuleContexts {

        private RuleContexts() {
        }

        public static EvaluationContext forReadOnlyOrder() {
            return SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .build();
        }

        public static StandardEvaluationContext
                forTrustedTypeRules(Object root) {
            StandardEvaluationContext context =
                    new StandardEvaluationContext(root);

            // Đăng ký đúng TypeLocator và resolver
            // đã được phê duyệt cho nhóm rule này.

            return context;
        }
    }

Tên factory làm rõ mức quyền và mục đích của context. Không nên tạo một factory tên chung chung như createDefaultContext() rồi dần dần thêm mọi capability mà các nhóm khác nhau yêu cầu.

Trong hệ thống lớn, có thể tách context theo các nhóm:

| Use case | Context khởi đầu | Capability cần cân nhắc |
|---|---|---|
| Đọc property và so sánh | SimpleEvaluationContext read-only | Root DTO, property cần thiết |
| Đọc property và gọi instance method giới hạn | SimpleEvaluationContext với instance methods | DTO có method an toàn |
| Gọi function Java đã chọn | StandardEvaluationContext được cấu hình | Danh sách function hẹp |
| Type reference hoặc constructor | StandardEvaluationContext được cấu hình | TypeLocator và resolver allowlist |
| Rule có bean reference | Context riêng cho rule tin cậy | BeanResolver giới hạn |

Bảng này là điểm bắt đầu để thiết kế. Capability thực tế cần được xác định theo phiên bản Spring, kiểu dữ liệu và biểu thức mà ứng dụng hỗ trợ.

## 12. Không dùng chung context mutable giữa các request

EvaluationContext chứa dữ liệu có thể thay đổi như root object, biến và danh sách resolver. Nếu một context được dùng chung giữa nhiều request và mỗi request thay đổi root hoặc biến, dữ liệu của các lần đánh giá có thể lẫn vào nhau.

Ví dụ rủi ro:

    sharedContext.setRootObject(orderForCurrentRequest);
    sharedContext.setVariable("tenantId", currentTenantId);

Nếu hai request chạy đồng thời, một request có thể thay đổi context trong lúc request kia đang đánh giá biểu thức. Điều này có thể làm rule đọc nhầm dữ liệu hoặc tạo lỗi khó tái hiện.

Một mô hình an toàn hơn là parse Expression ổn định một lần, sau đó tạo context riêng cho từng lần đánh giá:

    Expression expression =
            parser.parseExpression("total >= #minimumTotal");

    StandardEvaluationContext context =
            new StandardEvaluationContext(orderView);

    context.setMethodResolvers(Collections.emptyList());
    context.setConstructorResolvers(Collections.emptyList());
    context.setVariable("minimumTotal", configuredMinimum);

    Boolean result =
            expression.getValue(context, Boolean.class);

Nếu context được chia sẻ có chủ đích, cần bảo đảm cấu hình bất biến sau khi khởi tạo và không cập nhật root/variables/resolvers đồng thời. Đừng dựa vào giả định rằng một context mutable tự an toàn cho mọi luồng.

## 13. Phân tách context theo mức độ tin cậy của biểu thức

Nguồn tạo biểu thức là một yếu tố quyết định mức quyền phù hợp.

- Rule viết trong mã ứng dụng và được review có thể cần một số capability đã định trước.
- Rule do quản trị viên cấu hình cần kiểm tra, lưu vết và giới hạn capability theo vai trò.
- Biểu thức do người dùng cuối nhập cần phạm vi rất hẹp; trong nhiều trường hợp nên thay bằng một DSL hoặc bộ lọc có cấu trúc thay vì nhận SpEL tùy ý.

Không nên dùng cùng một context cho cả rule nội bộ và biểu thức người dùng chỉ vì chúng có chung cú pháp. Một biểu thức không đáng tin cậy không nên được cấp quyền gọi method, tạo object hoặc truy cập bean chỉ vì một use case nội bộ cần các quyền đó.

Tách context theo trust boundary giúp kiểm soát thay đổi. Khi một nhóm rule cần thêm khả năng, có thể đánh giá riêng capability đó mà không tự động mở rộng quyền cho mọi nhóm còn lại.

## 14. Kiểm thử context như một phần của hợp đồng rule

Kiểm thử không chỉ xác nhận biểu thức trả về kết quả mong đợi. Cần xác nhận context cho phép đúng thao tác cần thiết và từ chối thao tác ngoài phạm vi.

Một bộ kiểm thử phù hợp có thể bao gồm:

- Biểu thức đọc property hợp lệ chạy thành công.
- Property không được cung cấp hoặc không được phép truy cập bị từ chối.
- Method call chỉ chạy khi use case bật đúng capability.
- Constructor reference bị từ chối trong context không cho tạo object.
- Type reference chỉ phân giải kiểu nằm trong allowlist nếu đã cấu hình giới hạn.
- Bean reference không hoạt động khi context không có BeanResolver.
- Biến thiếu, null hoặc sai kiểu được xử lý theo hợp đồng.
- Root object không chứa dữ liệu hoặc hành vi vượt nhu cầu.
- Context của hai request không làm rò rỉ root object hay biến của nhau.

Khi kiểm thử hành vi từ chối, hãy xác nhận lỗi được xử lý rõ ràng và không làm lộ dữ liệu nội bộ. Việc một biểu thức bị từ chối là kết quả mong đợi nếu nó vượt capability của context.

## 15. Những sai lầm thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
|---|---|---|
| Dùng StandardEvaluationContext cho mọi rule | Mọi use case kế thừa tập capability rộng | Chọn context theo nhu cầu nhỏ nhất |
| Đưa entity hoặc service vào root object | Biểu thức nhìn thấy object graph và hành vi quá rộng | Dùng DTO chỉ đọc |
| Đăng ký nhiều function dự phòng | Tăng số method mà rule có thể gọi | Chỉ đăng ký function cần thiết |
| Bật BeanResolver cho tất cả context | Rule có thể tham chiếu bean ngoài nhu cầu | Không cấu hình hoặc dùng resolver allowlist |
| Coi registerImport() là allowlist | Package prefix chỉ hỗ trợ phân giải tên ngắn | Dùng TypeLocator kiểm soát kiểu cụ thể |
| Chia sẻ context mutable giữa request | Root và biến có thể bị ghi đè lẫn nhau | Tạo context riêng cho lần đánh giá |
| Chỉ kiểm thử kết quả đúng | Không phát hiện capability ngoài ý muốn | Kiểm thử cả thao tác được phép và bị từ chối |

## Kết luận

EvaluationContext nên phản ánh đúng use case của biểu thức. Với quy tắc chỉ đọc dữ liệu, bắt đầu bằng SimpleEvaluationContext ở chế độ read-only. Khi cần instance method, function, type reference, constructor hoặc bean reference, chỉ bật capability tương ứng và giới hạn đối tượng, resolver hoặc kiểu được phép truy cập.

Hãy dùng DTO nhỏ thay cho entity hoặc service object có quyền rộng, đăng ký đúng biến và function cần thiết, tạo context riêng cho mỗi lần đánh giá có dữ liệu mutable, và kiểm thử cả hành vi cho phép lẫn từ chối. StandardEvaluationContext là công cụ linh hoạt cho các trường hợp cần tính năng nâng cao; nó không nên trở thành context mặc định cho mọi rule chỉ vì có sẵn nhiều tính năng.
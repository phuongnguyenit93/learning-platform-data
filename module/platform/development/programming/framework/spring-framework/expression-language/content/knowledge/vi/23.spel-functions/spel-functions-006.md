# Kiểm soát danh sách function được expose

## 1. Function trong SpEL là gì?

Spring Expression Language (SpEL) cho phép ứng dụng mở rộng ngôn ngữ bằng các function do lập trình viên định nghĩa. Function là một thao tác có tên được đăng ký trong EvaluationContext và có thể được gọi từ expression.

Cú pháp gọi:

    #functionName(argument1, argument2, ...)

Ví dụ:

    #normalizeCode('  vn-hcm  ')

Expression trên gọi function có tên normalizeCode và truyền vào một chuỗi.

Function không tự xuất hiện chỉ vì một class Java có method public static. Ứng dụng phải chủ động đăng ký method hoặc MethodHandle tương ứng vào EvaluationContext trước khi expression được đánh giá.

Điều này tạo ra một cơ chế allow-list: context chỉ cần đăng ký những function mà loại expression đó được phép sử dụng.

## 2. Phân biệt function với method invocation

Function và method invocation đều có thể gọi logic Java, nhưng cách tìm target khác nhau.

| Cách viết | Cách hoạt động |
| --- | --- |
| #normalizeCode('vn') | Tìm function tên normalizeCode đã đăng ký trong EvaluationContext |
| #text.trim() | Lấy variable text rồi gọi method trim() trên object đó |
| text.trim() | Gọi method trên property text của root object |
| @pricingService.calculate(#amount) | Tìm bean pricingService qua BeanResolver rồi gọi method |

Function được gọi bằng tên sau dấu #. Method invocation cần một object làm target, có thể là root object, variable hoặc bean reference.

Đăng ký một function không có nghĩa là mọi method khác trong class chứa function đó cũng tự động được đăng ký. Chỉ method hoặc MethodHandle được gắn với tên function mới được gọi theo cú pháp function.

Tuy nhiên, nếu context còn expose một object có nhiều method, expression có thể truy cập các method đó qua đường method invocation riêng. Vì vậy, kiểm soát function registry là một phần của việc giới hạn khả năng expression, không phải toàn bộ ranh giới bảo mật.

## 3. Đăng ký function bằng Method

Cách phổ biến là lấy một java.lang.reflect.Method rồi đăng ký method đó vào EvaluationContext.

Ví dụ utility class:

    public final class RuleFunctions {

        private RuleFunctions() {
        }

        public static String normalizeCode(String value) {
            if (value == null) {
                return null;
            }
            return value.trim().toUpperCase(Locale.ROOT);
        }

        public static boolean isWithinRange(
                BigDecimal value,
                BigDecimal minimum,
                BigDecimal maximum) {
            return value != null
                && value.compareTo(minimum) >= 0
                && value.compareTo(maximum) <= 0;
        }
    }

Lấy Method và đăng ký vào context:

    Method normalizeMethod =
        RuleFunctions.class.getMethod(
            "normalizeCode",
            String.class
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.registerFunction(
        "normalizeCode",
        normalizeMethod
    );

Gọi function trong expression:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
        parser.parseExpression(
            "#normalizeCode('  vn-hcm  ')"
        );

    String result =
        expression.getValue(context, String.class);

Kết quả:

    VN-HCM

Method trong ví dụ là static. Đây là cách triển khai thông dụng cho function vì function được gọi theo tên mà không cần một instance target trong expression.

## 4. Đăng ký function qua setVariable

Theo API SpEL, function cũng có thể được đăng ký như một variable chứa Method hoặc MethodHandle bằng phương thức setVariable của EvaluationContext.

Ví dụ:

    Method normalizeMethod =
        RuleFunctions.class.getMethod(
            "normalizeCode",
            String.class
        );

    EvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    context.setVariable(
        "normalizeCode",
        normalizeMethod
    );

Sau đó gọi bằng cú pháp function:

    String result = parser
        .parseExpression("#normalizeCode('  spring  ')")
        .getValue(context, String.class);

    // result = "SPRING"

Cách này hữu ích khi cần đăng ký function trong một EvaluationContext implementation có hỗ trợ variable lookup, kể cả SimpleEvaluationContext.

Đừng nhầm hai cách:

- StandardEvaluationContext.registerFunction(name, method) là API tiện ích riêng của StandardEvaluationContext.
- EvaluationContext.setVariable(name, method) đăng ký Method như một function thông qua namespace variable/function chung.

Cả hai đều cho phép expression gọi function bằng #functionName(...).

## 5. Đăng ký nhiều function theo allow-list

Nếu rule chỉ cần một số thao tác được xác định trước, hãy đăng ký từng function một cách tường minh.

Ví dụ:

    Method normalizeMethod =
        RuleFunctions.class.getMethod(
            "normalizeCode",
            String.class
        );

    Method rangeMethod =
        RuleFunctions.class.getMethod(
            "isWithinRange",
            BigDecimal.class,
            BigDecimal.class,
            BigDecimal.class
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.registerFunction(
        "normalizeCode",
        normalizeMethod
    );

    context.registerFunction(
        "isWithinRange",
        rangeMethod
    );

Expression chỉ có thể gọi các function theo những tên đã đăng ký:

    #normalizeCode(#region) == 'VN'
        and #isWithinRange(#amount, #minimum, #maximum)

Đây là một allow-list dễ review. Người quản lý rule có thể nhìn vào danh sách và biết expression được cấp những thao tác nào.

Không nên đăng ký toàn bộ method của một utility class hoặc tự động expose mọi public static method bằng reflection. Một thay đổi nhỏ trong utility class có thể vô tình mở rộng API mà expression được phép gọi.

Hãy coi danh sách function là một phần của hợp đồng giữa ứng dụng và rule.

## 6. Function name và variable dùng chung namespace

Trong EvaluationContext, function và variable dùng chung một namespace. Vì vậy, tên function không nên trùng với tên variable.

Ví dụ không nên:

    context.setVariable("normalize", "VN");

    context.registerFunction(
        "normalize",
        normalizeMethod
    );

Cùng một tên normalize đang được dùng cho hai mục đích. Việc ghi đè hoặc lookup có thể khiến expression không gọi được function như dự kiến.

Nên đặt tên rõ ràng và có quy ước:

    normalizeCode
    isWithinRange
    calculateDiscount
    hasPermission

Đồng thời tránh dùng cùng tên cho variable:

    context.setVariable("regionCode", "VN");
    context.registerFunction("normalizeCode", normalizeMethod);

Một quy tắc đơn giản là dùng động từ hoặc cụm động từ cho function, còn danh từ cho variable. Điều này giúp expression dễ đọc và giảm xung đột tên.

## 7. Function hỗ trợ varargs

SpEL hỗ trợ varargs cho function, tương tự cách gọi method thông thường.

Ví dụ utility method:

    public static String joinLabels(String... labels) {
        return String.join(", ", labels);
    }

Lấy Method:

    Method joinMethod =
        RuleFunctions.class.getMethod(
            "joinLabels",
            String[].class
        );

Đăng ký:

    context.registerFunction(
        "joinLabels",
        joinMethod
    );

Gọi trong expression:

    #joinLabels('Java', 'Spring', 'SpEL')

Kết quả:

    Java, Spring, SpEL

Varargs hữu ích khi số lượng đối số thay đổi. Tuy nhiên, hãy xác định rõ số lượng và kiểu đối số được chấp nhận để tránh expression khó kiểm soát hoặc tạo đầu vào quá lớn.

Nếu function chỉ cần hai hoặc ba tham số cố định, chữ ký method tường minh thường dễ hiểu hơn varargs.

## 8. Đăng ký function bằng MethodHandle

Từ Spring Framework 6.1, StandardEvaluationContext cung cấp overload registerFunction nhận java.lang.invoke.MethodHandle.

Ví dụ về ý tưởng:

    MethodHandle handle = ...;

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.registerFunction(
        "formatMessage",
        handle
    );

MethodHandle có thể phù hợp khi ứng dụng đã có handle tới target và tham số được bind trước. Spring cũng hỗ trợ đăng ký MethodHandle qua setVariable trong EvaluationContext.

Một MethodHandle đã bind target hoặc một số đối số có thể làm đơn giản expression và có tiềm năng giảm công việc gọi method trong một số trường hợp.

Tuy nhiên, không nên chuyển sang MethodHandle chỉ vì nghĩ rằng nó luôn nhanh hơn Method. Hãy đo trên workload thực tế và chọn cách đăng ký dễ kiểm soát nhất.

Khi dùng MethodHandle, cần kiểm tra chính xác kiểu trả về, kiểu tham số, receiver đã bind và số đối số mà expression được phép truyền.

## 9. Thiết kế function nhỏ, rõ và ít side effect

Function được expose trở thành một capability mà expression có thể sử dụng. Vì vậy, method được chọn cần có phạm vi trách nhiệm rõ ràng.

Nên ưu tiên function:

- Có tên mô tả đúng hành vi.
- Có số lượng và kiểu tham số rõ ràng.
- Trả về một giá trị dễ dự đoán.
- Có validation cho dữ liệu đầu vào.
- Không thay đổi trạng thái dùng chung nếu không cần thiết.
- Không thực hiện I/O hoặc gọi hệ thống bên ngoài trong quá trình đánh giá rule.
- Không trả về object service hoặc object có quyền truy cập rộng.

Ví dụ phù hợp:

    #normalizeCode(#region)
    #isWithinRange(#amount, #minimum, #maximum)

Các function này thực hiện biến đổi hoặc kiểm tra dữ liệu đã được cung cấp.

Cần thận trọng với function như:

    #executeCommand(#input)
    #readFile(#path)
    #callExternalService(#url)
    #deleteAccount(#accountId)

Những thao tác này có thể tạo side effect, truy cập tài nguyên hoặc mở rộng quyền của expression. Nếu nghiệp vụ cần các thao tác đó, hãy thực hiện trong service có kiểm soát quyền và chỉ đưa kết quả đã được xác minh vào context.

## 10. Tách registry theo mục đích sử dụng

Không nên có một danh sách function toàn cục chứa mọi thao tác của ứng dụng rồi dùng chung cho tất cả rule.

Hãy tạo registry theo mục đích:

| Loại expression | Function có thể cần |
| --- | --- |
| Kiểm tra điều kiện đơn hàng | normalizeCode, isWithinRange |
| Tính giá hiển thị | roundMoney, calculateTax |
| Rule phân loại khách hàng | isEligible, hasLoyaltyTier |
| Kiểm tra dữ liệu đầu vào | isValidPostalCode, normalizePhone |

Mỗi loại rule chỉ nên nhận các function cần thiết cho nhiệm vụ đó.

Ví dụ tạo context cho rule đơn hàng:

    StandardEvaluationContext createOrderRuleContext(
            OrderFacts facts) throws NoSuchMethodException {

        StandardEvaluationContext context =
            new StandardEvaluationContext(facts);

        context.registerFunction(
            "normalizeCode",
            RuleFunctions.class.getMethod(
                "normalizeCode",
                String.class
            )
        );

        context.registerFunction(
            "isWithinRange",
            RuleFunctions.class.getMethod(
                "isWithinRange",
                BigDecimal.class,
                BigDecimal.class,
                BigDecimal.class
            )
        );

        return context;
    }

Context này không cần các function liên quan tới file, thanh toán, quản trị tài khoản hoặc dịch vụ ngoài phạm vi rule đơn hàng.

Nếu ứng dụng có nhiều nhóm rule, hãy giữ registry riêng và review thay đổi registry như review một API công khai.

## 11. Function và SimpleEvaluationContext

SimpleEvaluationContext cung cấp tập con tính năng SpEL để hỗ trợ các trường hợp data binding hoặc property-based expression cần giới hạn quyền.

Function có thể được đăng ký bằng setVariable với một Method hoặc MethodHandle:

    EvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    context.setVariable(
        "normalizeCode",
        normalizeMethod
    );

    String result = parser
        .parseExpression("#normalizeCode('vn')")
        .getValue(context, String.class);

Ví dụ này cho thấy việc gọi function không đòi hỏi phải dùng StandardEvaluationContext.registerFunction.

SimpleEvaluationContext không hỗ trợ toàn bộ tính năng của SpEL như type references, constructor invocation và bean references. Nó yêu cầu chọn rõ mức hỗ trợ property và method phù hợp với use case.

Tuy nhiên, không nên hiểu SimpleEvaluationContext là bảo đảm an toàn tuyệt đối. Function đã đăng ký vẫn là một thao tác mà expression có thể gọi. Hãy đánh giá chính method đó và tất cả object có thể truy cập từ context.

## 12. Danh sách function không phải ranh giới bảo mật duy nhất

Đăng ký tường minh một số function giúp kiểm soát các function có tên. Nhưng expression còn có thể truy cập các khả năng khác thông qua:

- Root object.
- Variables chứa object có method.
- PropertyAccessor.
- MethodResolver.
- BeanResolver.
- ConstructorResolver.
- TypeLocator.
- Function hoặc MethodHandle được đăng ký.

Ví dụ, dù chỉ đăng ký function normalizeCode, nếu root object là một service có method quản trị hoặc thực hiện I/O và method invocation vẫn được phép, expression có thể tìm cách gọi các method đó theo đường khác.

Vì vậy, cần thiết kế toàn bộ EvaluationContext theo least privilege:

1. Root object chỉ chứa dữ liệu cần thiết.
2. Variables chỉ gồm dữ kiện hoặc object cần thiết.
3. Function registry chỉ gồm method được duyệt.
4. Không đăng ký BeanResolver nếu expression không cần bean.
5. Không cấp constructor hoặc type access nếu không cần.
6. PropertyAccessor và MethodResolver cần giới hạn theo mục tiêu.

Tài liệu Spring cảnh báo không dùng StandardEvaluationContext để đánh giá expression lấy từ nguồn không tin cậy. SimpleEvaluationContext giới hạn một phần ngôn ngữ theo best-effort, nhưng cũng không bảo đảm an toàn nếu object, resolver, variable hoặc function được expose có thao tác nguy hiểm.

Nếu người dùng cuối có thể tự nhập SpEL, hãy cân nhắc một rule language có cấu trúc hoặc DSL giới hạn thay vì cho phép expression tổng quát.

## 13. Kiểm soát đối số và kết quả function

Một function an toàn vẫn cần xử lý đầu vào đúng cách.

Ví dụ:

    public static BigDecimal calculateDiscount(
            BigDecimal amount,
            BigDecimal rate) {

        if (amount == null || rate == null) {
            throw new IllegalArgumentException(
                "Amount and rate are required"
            );
        }

        if (rate.compareTo(BigDecimal.ZERO) < 0
                || rate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                "Rate must be between 0 and 1"
            );
        }

        return amount.multiply(rate);
    }

Không nên mặc định rằng expression sẽ luôn truyền giá trị hợp lệ. Rule có thể chứa null, giá trị vượt giới hạn hoặc kiểu dữ liệu không tương thích.

Các điểm cần kiểm soát:

- Nullability của từng tham số.
- Giới hạn số lượng phần tử nếu nhận collection hoặc varargs.
- Kiểu dữ liệu và quy tắc chuyển đổi.
- Miền giá trị hợp lệ.
- Kiểu kết quả trả về.
- Hành vi khi function thất bại.

Tránh để function nhận một object quá rộng chỉ để đọc một field. Truyền trực tiếp giá trị cần thiết hoặc một DTO hẹp sẽ dễ kiểm soát hơn.

## 14. Quản lý context và vòng đời function

Function được đăng ký trong EvaluationContext. Context có thể chứa variables thay đổi theo từng lần đánh giá.

Một cách tổ chức dễ kiểm soát là:

- Giữ parser và expression đã parse nếu source rule không đổi.
- Tạo context theo request hoặc theo lần đánh giá khi context chứa dữ liệu động.
- Đăng ký cùng một allow-list function đã được duyệt.
- Không thay đổi registry tùy tiện trong khi expression đang được sử dụng.
- Không chia sẻ mutable variable giữa các request nếu chưa kiểm soát concurrency.

Ví dụ:

    Expression rule =
        parser.parseExpression(
            "#isWithinRange(#amount, #minimum, #maximum)"
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.registerFunction(
        "isWithinRange",
        rangeMethod
    );

    context.setVariable("amount", amount);
    context.setVariable("minimum", minimum);
    context.setVariable("maximum", maximum);

    Boolean allowed =
        rule.getValue(context, Boolean.class);

Expression được parse một lần. Context cung cấp dữ liệu và function cho lần đánh giá hiện tại.

Nếu function phụ thuộc vào state hoặc dịch vụ thay đổi, hãy xác định rõ vòng đời target và cách đồng bộ thay vì đưa một object mutable dùng chung vào mọi context.

## 15. Lỗi thường gặp khi expose function

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Function not found | Chưa đăng ký hoặc tên gọi sai | Kiểm tra registry và tên sau dấu # |
| Method không phù hợp | Sai chữ ký hoặc kiểu đối số | Kiểm tra parameter types và conversion |
| Function name bị ghi đè | Trùng tên với variable | Dùng namespace tên riêng và tránh overlap |
| Không gọi được MethodHandle | Handle có receiver hoặc kiểu tham số chưa bind đúng | Kiểm tra MethodType, target và số đối số |
| Function hoạt động trong context này nhưng không hoạt động ở context khác | Context khác chưa đăng ký cùng function | Kiểm tra nơi tạo EvaluationContext |
| Expression gọi được thao tác ngoài dự kiến | Root object hoặc resolver expose thêm quyền | Thu hẹp context và method access |
| SimpleEvaluationContext không thực hiện được thao tác mong muốn | Tính năng cần dùng không nằm trong tập được bật | Kiểm tra builder và chọn đúng tập tính năng |
| Function tạo side effect ngoài ý muốn | Method thực hiện I/O hoặc thay đổi trạng thái | Tách thao tác sang service có kiểm soát quyền |

Khi debug, kiểm tra theo thứ tự:

1. Expression có cú pháp gọi đúng #functionName(...) không?
2. Context đang đánh giá có đăng ký tên đó không?
3. Tên function có trùng variable không?
4. Method hoặc MethodHandle có đúng chữ ký không?
5. Kiểu đối số có tương thích không?
6. Function có ném exception trong lúc chạy không?

Parse thành công không có nghĩa function đã được đăng ký. Function lookup và invocation xảy ra khi expression được đánh giá.

## 16. Checklist khi thiết kế function registry

Trước khi expose function cho SpEL, hãy xác định:

1. Expression thực sự cần thao tác nào?
2. Có thể thực hiện thao tác đó bằng một function nhỏ, thuần và không có side effect không?
3. Method có public signature rõ ràng và kiểu tham số cụ thể không?
4. Có cần varargs hay số lượng tham số cố định là đủ?
5. Tên function có trùng variable hiện có không?
6. Function có trả về object quá rộng hoặc nhạy cảm không?
7. Function có thể truy cập file, network, database hoặc thay đổi trạng thái không?
8. Có thể tách registry theo từng loại rule không?
9. Root object và các resolver khác có expose thêm method ngoài danh sách function không?
10. Expression có đến từ nguồn không tin cậy không?
11. Context có được tạo và quản lý theo đúng vòng đời request không?
12. Có thể dùng SimpleEvaluationContext hoặc DSL giới hạn hơn không?

Nếu một function không cần cho rule, đừng đăng ký nó chỉ vì tiện.

## 17. Những điểm cần nhớ

- Function do ứng dụng đăng ký và được gọi bằng cú pháp #functionName(...).
- Có thể đăng ký Method qua EvaluationContext.setVariable().
- StandardEvaluationContext cung cấp registerFunction() cho Method và MethodHandle.
- MethodHandle registration qua StandardEvaluationContext có từ Spring Framework 6.1.
- Function invocation hỗ trợ varargs.
- Function và variable dùng chung namespace; tên phải tránh trùng nhau.
- Đăng ký function không tự expose mọi method trong class chứa nó.
- Method invocation trên root object hoặc variable là một cơ chế riêng và cũng cần được kiểm soát.
- Tạo allow-list tường minh theo từng loại rule, không tự động expose cả utility class.
- Ưu tiên function nhỏ, rõ, ít side effect và kiểm tra đầu vào.
- SimpleEvaluationContext có thể dùng function qua setVariable nhưng vẫn cần kiểm soát những capability được expose.
- Không dùng StandardEvaluationContext để đánh giá expression từ nguồn không tin cậy; SimpleEvaluationContext cũng không phải bảo đảm an toàn tuyệt đối.
- Function registry chỉ là một phần của quyền truy cập; root object, variables, accessors và resolvers cũng cần được giới hạn.

Hãy xem mỗi function được đăng ký như một quyền mà expression nhận được. Chỉ expose những thao tác thực sự cần cho rule, giữ chữ ký đơn giản và giới hạn toàn bộ EvaluationContext theo nguyên tắc least privilege.

## Tài liệu tham khảo

- Spring Framework Reference — Functions: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/functions.html
- Spring Framework Reference — Evaluation: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Javadoc — StandardEvaluationContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html
- Spring Framework Javadoc — SimpleEvaluationContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html

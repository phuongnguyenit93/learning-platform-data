# Đe dọa khi đánh giá expression từ dữ liệu không tin cậy

## 1. Vì sao đánh giá SpEL không tin cậy nguy hiểm?

Spring Expression Language (SpEL) là ngôn ngữ biểu thức có khả năng tương tác sâu với Java object. Tùy EvaluationContext, một expression có thể đọc và ghi property, gọi method, tạo object bằng constructor, tham chiếu Spring bean, truy cập collection và thực hiện chuyển đổi kiểu.

Những khả năng đó hữu ích khi expression do nhà phát triển hoặc quản trị viên đáng tin cậy cấu hình. Nhưng nếu người dùng hoặc hệ thống bên ngoài có thể kiểm soát nội dung expression, họ có thể khiến ứng dụng thực hiện thao tác ngoài ý định ban đầu.

Spring cảnh báo rằng đánh giá SpEL lấy từ nguồn không tin cậy vốn nguy hiểm và nhìn chung nên tránh. StandardEvaluationContext cung cấp đầy đủ tính năng của ngôn ngữ và tuyệt đối không được dùng để đánh giá expression từ nguồn không tin cậy. SimpleEvaluationContext giới hạn một phần tính năng nhưng chỉ cung cấp bảo vệ theo best-effort, không phải sandbox bảo đảm an toàn.

Nguồn expression chỉ được xem là đáng tin cậy khi do nhà phát triển ứng dụng hoặc quản trị viên chịu trách nhiệm cấu hình/vận hành cung cấp. Expression do người dùng cuối, khách hàng, tenant khác hoặc hệ thống bên ngoài gửi đến phải được coi là không tin cậy, kể cả khi nó được lưu trong database hoặc file cấu hình.

## 2. Expression injection và CWE-917

Expression Language Injection xảy ra khi dữ liệu do bên ngoài kiểm soát được đưa vào câu lệnh expression rồi được interpreter đánh giá như mã.

Ví dụ thiết kế nguy hiểm:

    String source =
        "#customerName == '" + userInput + "'";

    Expression expression =
        parser.parseExpression(source);

Nếu userInput chứa dấu nháy và cú pháp SpEL, nội dung đầu vào có thể thay đổi cấu trúc expression. Ứng dụng đã biến dữ liệu thành một phần của chương trình được thực thi.

Đây là dạng lỗi được phân loại là CWE-917: Improper Neutralization of Special Elements used in an Expression Language Statement.

Không nên cố giải quyết bằng cách chỉ xóa một vài ký tự đặc biệt như dấu nháy, dấu # hoặc dấu ngoặc. SpEL có nhiều cách biểu diễn và cú pháp; một bộ lọc ký tự đơn giản rất dễ bỏ sót trường hợp khác.

Biện pháp tốt nhất là không ghép dữ liệu không tin cậy vào expression source. Hãy giữ source cố định và truyền dữ liệu qua variable.

## 3. Truyền dữ liệu bằng variable thay vì ghép chuỗi

Nếu mục tiêu là so sánh một giá trị do người dùng gửi, hãy parse expression cố định rồi truyền giá trị vào EvaluationContext.

Cách an toàn hơn:

    Expression expression =
        parser.parseExpression(
            "#customerName == #expectedName"
        );

    SimpleEvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    context.setVariable("customerName", customerName);
    context.setVariable("expectedName", userInput);

    Boolean matches =
        expression.getValue(context, Boolean.class);

Trong ví dụ này, userInput chỉ là dữ liệu. Nó không được parse lại thành cú pháp SpEL.

Cần phân biệt hai tình huống:

- Người dùng cung cấp giá trị cho một expression do ứng dụng viết sẵn: truyền qua variable hoặc tham số của API có cấu trúc.
- Người dùng được phép viết toàn bộ expression: đây là một ngôn ngữ lập trình do người dùng kiểm soát và cần thiết kế ranh giới thực thi riêng.

Không có một hàm escape tổng quát nào biến mọi expression SpEL không tin cậy thành an toàn. Nếu nghiệp vụ cần người dùng tự tạo rule, hãy cân nhắc DSL hoặc rule model giới hạn, chỉ hỗ trợ các phép so sánh và toán tử được xác định trước.

## 4. Gọi method và thực thi hành động ngoài ý muốn

Với StandardEvaluationContext và các resolver mặc định, SpEL có thể gọi method trên object mà expression truy cập được.

Ví dụ expression:

    #accountService.disableAccount(#accountId)

Nếu accountService được đưa vào context hoặc có thể được tìm qua bean resolver, expression có thể kích hoạt một thao tác thay đổi trạng thái tài khoản.

Các method khác có thể gửi email, ghi dữ liệu, xóa file, gọi API, thực hiện thanh toán hoặc thay đổi quyền. Khi expression có thể gọi chúng, người kiểm soát expression có thể điều khiển hành vi của ứng dụng trong phạm vi object được expose.

Không nên đưa service có quyền rộng vào root object, variable hoặc BeanResolver của expression không tin cậy. Nếu rule chỉ cần biết tài khoản có được phép tiếp tục hay không, hãy thực hiện kiểm tra quyền trong service đáng tin cậy rồi truyền kết quả boolean vào context.

Việc chỉ cho phép một vài function có tên cũng chưa đủ nếu root object hoặc variable khác vẫn expose method nguy hiểm qua cơ chế method invocation.

## 5. Truy cập class, constructor và bean

StandardEvaluationContext có thể hỗ trợ nhiều tính năng mở rộng như:

- Type reference bằng T(...).
- Tạo object bằng new.
- Gọi static method.
- Tham chiếu bean qua BeanResolver.
- Gọi method và truy cập property trên object đã tìm được.

Ví dụ các biểu thức sau minh họa những khả năng cần được kiểm soát:

    T(java.lang.System).getProperty('user.name')

    new java.util.Date()

    @pricingService.calculate(#amount)

Expression đầu có thể đọc một system property, expression thứ hai tạo object mới, còn expression thứ ba gọi method trên bean được resolve.

Không nên cấp TypeLocator, ConstructorResolver hoặc BeanResolver cho expression không tin cậy nếu nghiệp vụ không cần chúng. Đặc biệt, không đưa toàn bộ ApplicationContext hoặc các service quản trị vào phạm vi expression chỉ để tiện tra cứu.

SimpleEvaluationContext loại trừ type references, constructor invocation và bean references. Tuy nhiên, các object và method vẫn có thể truy cập thông qua root object, variables, property accessors, method resolvers và functions đã cấu hình.

## 6. Lộ dữ liệu qua root object và variable

Expression có thể đọc mọi property mà accessor hiện tại cho phép trên object mà nó tiếp cận được.

Nếu root object là một entity lớn hoặc một service, expression có thể đi theo các property lồng nhau để tiếp cận thông tin ngoài mục tiêu ban đầu.

Ví dụ:

    #customer.profile.email

    #customer.paymentDetails.accountNumber

    #configuration.internalEndpoint

Ngay cả khi expression chỉ cần kiểm tra một điều kiện đơn giản, việc đưa toàn bộ entity vào context có thể vô tình mở ra nhiều dữ liệu khác.

Không nên cung cấp password, access token, private key, session credential hoặc thông tin cá nhân không cần thiết trong variables. Variable không phải secret store; nó chỉ là dữ liệu mà expression có thể tham chiếu bằng dấu #.

Hãy tạo DTO hoặc record chuyên dùng cho evaluation, chỉ chứa những dữ kiện cần thiết:

    public record AccountFacts(
        boolean active,
        boolean verified,
        String region
    ) {}

    SimpleEvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    context.setRootObject(
        new AccountFacts(true, true, "VN")
    );

Expression chỉ nhìn thấy active, verified và region. Nó không cần tiếp cận entity, repository, credential hoặc service nội bộ.

## 7. Property getter cũng có thể gây side effect

Một hiểu nhầm nguy hiểm là cho rằng read-only expression luôn chỉ đọc dữ liệu và không thể thay đổi trạng thái.

SpEL có thể truy cập property thông qua method có hình dạng accessor: method public, không có tham số và trả về một giá trị. Hình dạng này không chứng minh method thực sự chỉ đọc.

Ví dụ các method sau có thể bị nhìn như property accessor:

    file.delete()
    queue.poll()
    counter.incrementAndGet()

Khi object tương ứng được expose và accessor cho phép, một expression có thể truy cập chúng dưới dạng property-like operation. Các method này thay đổi trạng thái dù cú pháp nhìn giống đọc property.

Spring chỉ rõ rằng ReflectivePropertyAccessor và DataBindingPropertyAccessor không thể tự xác định một accessor-shaped method có side effect hay không.

Do đó, read-only trong SimpleEvaluationContext chỉ kiểm soát việc assignment vào property. Nó không chứng minh getter hoặc accessor method là thuần, không có side effect.

Hãy review tất cả method không tham số trả về giá trị trên object được expose. Chỉ đưa vào context các object có API đọc an toàn và có phạm vi hẹp.

## 8. Khả năng truy cập lan truyền qua object lồng nhau

Giới hạn root object chưa đủ nếu property của nó trả về một object có quyền rộng.

Ví dụ:

    #facts.customer.address.city

Nếu facts.customer trả về một entity lớn, expression có thể tiếp tục điều hướng vào những property khác của entity đó. Tương tự, object được lấy qua indexer hoặc variable cũng có thể mở ra một nhánh truy cập mới.

Hãy kiểm tra toàn bộ object graph mà expression có thể đi tới:

- Root object và các property được trả về.
- Object trong List, array và Map.
- Variable chứa object.
- Kết quả trả về từ method hoặc function.
- Bean được tìm qua BeanResolver.
- Object trả về từ custom PropertyAccessor.

Một DTO chỉ chứa vài field nhưng lại trả về entity hoặc service qua getter vẫn có thể mở rộng phạm vi truy cập. Ranh giới cần được giữ ở mọi cấp, không chỉ ở object đầu tiên.

Ưu tiên kiểu dữ liệu chuyên biệt, immutable và chỉ expose các giá trị cần thiết. Tránh getter trả về infrastructure object, repository, connection, file handle hoặc service có quyền rộng.

## 9. Ghi property và thay đổi trạng thái

SpEL hỗ trợ assignment và Expression.setValue khi EvaluationContext cùng PropertyAccessor cho phép ghi.

Ví dụ:

    #account.enabled = false

    Expression expression =
        parser.parseExpression("enabled");

    expression.setValue(context, account, false);

Nếu expression không tin cậy có thể ghi property, nó có thể thay đổi trạng thái object và ảnh hưởng tới request hoặc người dùng khác đang dùng chung object đó.

Một số biện pháp:

- Dùng DTO immutable hoặc context chỉ đọc khi chỉ cần đánh giá điều kiện.
- Không expose entity đang được quản lý bởi persistence context nếu rule không cần ghi.
- Không cấp PropertyAccessor có quyền ghi rộng.
- Không cho phép assignment nếu nghiệp vụ không yêu cầu.
- Thực hiện thay đổi trạng thái qua service có authorization, validation và transaction.
- Không coi việc dùng SimpleEvaluationContext read-only là đủ nếu accessor-shaped method vẫn có thể thay đổi state.

Nếu expression cần cập nhật dữ liệu, hãy xác định rõ property nào được phép ghi và validate giá trị trước khi áp dụng.

## 10. Denial of service và tiêu thụ tài nguyên

Expression không tin cậy có thể tiêu thụ CPU, bộ nhớ hoặc kích hoạt nhiều thao tác lặp lại.

Các nguyên nhân thường gặp:

- Expression quá dài hoặc có cấu trúc lồng nhau sâu.
- Selection/projection duyệt collection lớn.
- Method được gọi lặp lại trên từng phần tử và thực hiện I/O.
- Regex phức tạp hoặc pattern có backtracking tốn kém.
- Phép toán số học với giá trị rất lớn.
- Function hoặc method tạo collection/object quá lớn.
- Nhiều expression được đánh giá đồng thời mà không có giới hạn.

Ví dụ:

    #orders.?[customer.isEligible()].![total]

Nếu orders chứa rất nhiều phần tử và isEligible thực hiện truy vấn database, một expression ngắn có thể gây ra số lượng truy vấn lớn.

Giới hạn đầu vào và chi phí mỗi lần evaluation quan trọng hơn độ dài câu expression nhìn bằng mắt.

## 11. Các giới hạn parser và phép toán của SpEL

Spring cung cấp một số giới hạn cấu hình để giảm nguy cơ expression tiêu thụ tài nguyên quá mức. Theo tài liệu Spring hiện hành, các mặc định gồm:

| Giới hạn | Mặc định được tài liệu mô tả | Mục đích |
| --- | ---: | --- |
| Maximum expression length | 10.000 ký tự | Hạn chế source expression quá dài |
| Maximum operations | 10.000 thao tác | Hạn chế số operation trong evaluation |
| Maximum BigDecimal/BigInteger power result | 1.000.000 bit | Giới hạn kích thước kết quả phép lũy thừa |

Có thể cấu hình các giá trị thấp hơn theo workload:

    SpelParserConfiguration configuration =
        SpelParserConfiguration.builder()
            .maximumExpressionLength(5_000)
            .maximumOperations(1_000)
            .maximumBigPowerBits(100_000)
            .build();

    SpelExpressionParser parser =
        new SpelExpressionParser(configuration);

Các con số trên là giá trị mặc định được tài liệu hiện hành mô tả, không nên coi là mặc định giống nhau cho mọi phiên bản hoặc mọi cấu hình. Hãy kiểm tra phiên bản Spring đang dùng và cấu hình parser thực tế.

Các giới hạn này giúp bounded một số dạng chi phí. Chúng không thay thế timeout, giới hạn collection, kiểm soát method, giới hạn concurrency hoặc thiết kế context an toàn. Một method được expose vẫn có thể block hoặc thực hiện I/O dù expression nằm dưới giới hạn operation.

## 12. Tách expression parsing khỏi dữ liệu đầu vào

Nếu người dùng chỉ cung cấp một giá trị, không parse giá trị đó thành expression.

Ví dụ, khi cần lọc theo trạng thái, dùng expression cố định:

    #order.status == #expectedStatus

Đưa expectedStatus vào context:

    context.setVariable(
        "expectedStatus",
        userSuppliedStatus
    );

Nếu người dùng được chọn một field trong danh sách cho phép, ánh xạ lựa chọn đó sang property path do ứng dụng định nghĩa:

    Map<String, Expression> allowedRules = Map.of(
        "active", parser.parseExpression("active"),
        "verified", parser.parseExpression("verified")
    );

    Expression selected =
        allowedRules.get(userSelectedRule);

Không lấy trực tiếp userSelectedRule rồi nối vào expression source.

Nếu người dùng phải tự viết rule, hãy xây dựng một DSL giới hạn hoặc một cấu trúc dữ liệu khai báo có schema, rồi chuyển cấu trúc đó thành expression đã được kiểm soát. Việc chỉ kiểm tra một số chuỗi con hoặc blacklist token không tạo thành parser bảo mật.

## 13. SimpleEvaluationContext không phải sandbox

SimpleEvaluationContext được thiết kế cho các trường hợp cần một tập con tính năng SpEL, chẳng hạn data binding hoặc property-based filtering.

Có thể bắt đầu bằng read-only data binding:

    SimpleEvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

Cấu hình này không hỗ trợ type references, constructor invocation hoặc bean references như StandardEvaluationContext. Nó cũng không bật toàn bộ method resolution.

Tuy nhiên, Spring nhấn mạnh rằng các giới hạn của SimpleEvaluationContext chỉ là best-effort và không bảo đảm evaluation an toàn. Bất kỳ property, method hoặc function nào có thể đi tới từ root object, accessor, resolver, variable hoặc function vẫn cần được kiểm soát.

Read-only data binding cũng không xác nhận getter không có side effect. Vì vậy, phải thiết kế object đầu vào an toàn ngay từ đầu.

## 14. Không tái sử dụng Expression giữa các mức quyền khác nhau

Một chi tiết bảo mật quan trọng liên quan đến cache bên trong AST của Expression.

Để tăng hiệu năng, các node của parsed Expression có thể cache PropertyAccessor, IndexAccessor, MethodExecutor hoặc ConstructorExecutor đã được dùng trong lần đánh giá trước.

Vì vậy, không được đánh giá cùng một instance Expression trước tiên bằng context có quyền rộng rồi sau đó tái sử dụng nó với context có quyền hạn chế hơn, với kỳ vọng các hạn chế mới sẽ luôn được áp dụng.

Ví dụ thiết kế cần tránh:

    Expression shared =
        parser.parseExpression("customer.profile");

    shared.getValue(
        privilegedContext,
        privilegedRoot
    );

    // Không tái sử dụng shared với context có security policy khác.
    shared.getValue(
        restrictedContext,
        restrictedRoot
    );

Spring xem việc tái sử dụng một Expression giữa các context có security implications khác nhau là cách dùng không được hỗ trợ.

Nếu cùng một source expression cần được đánh giá theo nhiều security profile, hãy parse thành các instance Expression riêng cho từng profile và không chuyển instance đã dùng trong context quyền rộng sang context quyền thấp.

Tốt nhất là giữ cấu hình resolver/accessor ổn định trong vòng đời expression. Không thay đổi security policy của context sau khi expression đã được đánh giá rồi giả định cache cũ không còn ảnh hưởng.

## 15. Cô lập EvaluationContext giữa request và tenant

EvaluationContext có thể chứa root object, variable, function và các resolver. Nếu context mutable được dùng chung giữa nhiều request, dữ liệu hoặc quyền của một request có thể ảnh hưởng request khác.

Ví dụ nguy hiểm:

    sharedContext.setVariable("tenantId", tenantId);
    sharedContext.setVariable("account", account);

Hai request đồng thời có thể ghi đè variables hoặc dùng nhầm object của tenant khác nếu state bị chia sẻ không đúng cách.

Nên tạo context riêng cho mỗi request hoặc lần đánh giá khi context chứa dữ liệu động:

    SimpleEvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    context.setRootObject(accountFacts);

Expression đã parse có thể được tái sử dụng giữa các context có cấu hình bảo mật tương đương theo hướng dẫn của Spring. Nhưng không được dùng chung instance Expression giữa các context có mức quyền khác nhau.

Với hệ thống multi-tenant, hãy xác định tenant trước khi tạo root object, chỉ đưa dữ liệu thuộc tenant đó vào context và không dùng một context mutable toàn cục để chứa dữ liệu request.

## 16. Không log expression và context một cách tùy tiện

Expression source, variable values và lỗi evaluation có thể chứa thông tin nhạy cảm.

Tránh ghi toàn bộ context vào log:

    log.debug("Evaluation context: {}", context);
    log.debug("Rule variables: {}", variables);

Không đưa password, token, private key, dữ liệu cá nhân hoặc nội dung expression do người dùng nhập vào log nếu không có nhu cầu và biện pháp bảo vệ phù hợp.

Nên log metadata tối thiểu:

- Rule ID hoặc phiên bản rule.
- Thời gian đánh giá và thời lượng.
- Kết quả thành công/thất bại.
- Loại lỗi và vị trí lỗi đã được làm sạch.
- Correlation ID để truy vết request.
- Tenant hoặc actor ID theo chính sách log của ứng dụng.

Nếu cần ghi input để điều tra, hãy redact hoặc pseudonymize field nhạy cảm và giới hạn quyền truy cập, thời gian lưu log.

## 17. Phân biệt expression injection với XSS và SQL injection

Expression injection là lỗi khi dữ liệu không tin cậy được interpreter hiểu như cú pháp thực thi.

Nó khác với:

- SQL injection: dữ liệu làm thay đổi cấu trúc câu truy vấn SQL.
- Command injection: dữ liệu làm thay đổi lệnh được chuyển cho shell hoặc process.
- Cross-site scripting: dữ liệu được render thành mã script trong trình duyệt.

Một giá trị SpEL trả về String không tự động được HTML-escape. Nếu kết quả được đưa vào trang web, ứng dụng vẫn phải output encode theo đúng ngữ cảnh HTML, attribute, JavaScript hoặc URL.

Tương tự, dùng SpEL không thay thế prepared statements khi truy vấn database. Hãy dùng API tham số hóa cho SQL và API an toàn cho từng interpreter.

Một hệ thống có thể đồng thời mắc nhiều loại injection nếu cùng dữ liệu không tin cậy được chuyển qua nhiều interpreter.

## 18. Checklist bảo vệ expression evaluation

Trước khi cho phép một expression được đánh giá, hãy kiểm tra:

1. Ai kiểm soát expression source: developer, administrator, end user hay hệ thống bên ngoài?
2. Có thể tránh đánh giá expression do người dùng cung cấp không?
3. Nếu chỉ cần dữ liệu, đã truyền qua variable thay vì nối chuỗi chưa?
4. Có thể thay SpEL tổng quát bằng DSL hoặc rule model có schema không?
5. Context có dùng SimpleEvaluationContext với tính năng tối thiểu cần thiết không?
6. Root object có phải DTO hẹp, immutable và chỉ chứa dữ liệu cần thiết không?
7. Tất cả object lồng nhau và kết quả index có API an toàn không?
8. Getter/accessor-shaped method có side effect không?
9. Có function, method, bean, type hoặc constructor nào được expose quá rộng không?
10. Có cho phép property assignment hoặc method thay đổi trạng thái không?
11. Parser có giới hạn độ dài, operation và kích thước phép toán không?
12. Collection và input có giới hạn kích thước, thời gian và concurrency không?
13. Expression instance có bị tái sử dụng giữa context có mức quyền khác nhau không?
14. Context mutable có bị chia sẻ giữa request hoặc tenant không?
15. Log và output có làm lộ dữ liệu hoặc tạo XSS không?
16. Spring Framework có đang ở phiên bản được cập nhật security fixes không?

Nếu không thể trả lời rõ một quyền truy cập có cần thiết hay không, hãy bỏ quyền đó khỏi context trước khi đưa expression vào sử dụng.

## 19. Những điểm cần nhớ

- Đánh giá SpEL từ nguồn không tin cậy vốn nguy hiểm; tránh làm việc đó nếu có thể.
- StandardEvaluationContext không được dùng để đánh giá expression không tin cậy.
- SimpleEvaluationContext chỉ giới hạn tính năng theo best-effort, không phải sandbox.
- Không ghép dữ liệu người dùng vào expression source; dùng variable hoặc API tham số hóa.
- Expression có thể gọi method, tạo object, đọc/ghi property và tham chiếu bean theo quyền của context.
- Không expose entity, ApplicationContext, service hoặc object chứa secret nếu rule không cần.
- Getter có hình dạng accessor vẫn có thể xóa file, thay đổi queue hoặc cập nhật counter.
- Kiểm tra toàn bộ object graph, bao gồm object lồng nhau, collection, variables và function results.
- Dùng DTO chuyên biệt, immutable và có phạm vi dữ liệu hẹp.
- Giới hạn expression length, operation count, kích thước số và collection, đồng thời kiểm soát timeout/concurrency.
- Không tái sử dụng cùng parsed Expression instance giữa context có security implications khác nhau.
- Cô lập context mutable theo request và tenant.
- Không log toàn bộ expression, context hoặc secret.
- Output encoding, SQL parameterization và command safety vẫn là các trách nhiệm riêng.

Hãy xem EvaluationContext như một tập quyền mà expression được cấp. Một expression chỉ nên nhìn thấy dữ liệu và thao tác cần cho nhiệm vụ của nó. Thiết kế context hẹp, truyền dữ liệu như dữ liệu, giới hạn tài nguyên và giữ expression ngoài tầm kiểm soát của người dùng là các lớp bảo vệ quan trọng nhất.

## Tài liệu tham khảo

- Spring Framework Reference — Evaluation and Security Considerations: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Reference — SpEL Parser Configuration and Compiler: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/expressions.html
- MITRE CWE-917 — Expression Language Injection: https://cwe.mitre.org/data/definitions/917.html
- OWASP — Expression Language Injection: https://owasp.org/www-community/vulnerabilities/Expression_Language_Injection
- OWASP — Injection Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Injection_Prevention_Cheat_Sheet.html

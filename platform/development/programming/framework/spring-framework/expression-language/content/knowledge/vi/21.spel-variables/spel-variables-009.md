# Không đưa dữ liệu bí mật vào context nếu biểu thức không cần

## 1. EvaluationContext có thể cung cấp dữ liệu cho SpEL

Spring Expression Language (SpEL) đánh giá biểu thức trong một môi trường gọi là EvaluationContext. Context có thể cung cấp root object, variables, functions và các cơ chế truy cập property, method, type hoặc bean tùy cấu hình.

Ví dụ:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("orderTotal", 1200);
    context.setVariable("member", true);

    Expression expression = parser.parseExpression(
        "#member and #orderTotal >= 1000"
    );

    Boolean eligible =
        expression.getValue(context, Boolean.class);

Biểu thức chỉ cần hai dữ kiện: orderTotal và member. Vì vậy context chỉ cần chứa hai giá trị đó.

Nếu ứng dụng còn đưa password, access token, private key, session credential hoặc thông tin cá nhân không liên quan vào cùng context, những dữ liệu đó không giúp biểu thức thực hiện nhiệm vụ và tạo thêm rủi ro khi expression được đánh giá hoặc truy cập ngoài dự kiến.

Nguyên tắc quan trọng: chỉ cung cấp dữ liệu mà biểu thức thực sự cần để đưa ra kết quả.

## 2. Variable không phải secret store

Variable trong SpEL được đăng ký bằng setVariable và tham chiếu bằng ký hiệu #:

    context.setVariable("minimum", 1000);

    #minimum

Ví dụ với dữ liệu nhạy cảm:

    context.setVariable("apiToken", token);
    context.setVariable("password", password);
    context.setVariable("privateKey", privateKey);

Các giá trị này vẫn là dữ liệu trong EvaluationContext. SpEL không tự mã hóa, che dấu hoặc phân loại chúng thành secret chỉ vì chúng được đặt trong variable.

Nếu expression có quyền truy cập context và biết tên variable, nó có thể tham chiếu variable tương ứng:

    #apiToken
    #password

Do đó, không nên xem việc đặt dữ liệu vào variable là một biện pháp bảo vệ bí mật. Variable chỉ là cách truyền dữ liệu vào expression.

Nếu biểu thức không cần token, password hoặc private key, đừng đăng ký chúng vào context.

## 3. Chỉ truyền những dữ kiện tối thiểu

Giả sử một rule cần quyết định đơn hàng có đủ điều kiện miễn phí vận chuyển hay không.

Không nên đưa toàn bộ object chứa nhiều thông tin nhạy cảm vào context chỉ để expression đọc một vài field:

    context.setVariable("customer", entireCustomerEntity);
    context.setVariable("order", entireOrderEntity);

Các entity này có thể chứa email, số điện thoại, địa chỉ, ghi chú nội bộ, thông tin thanh toán hoặc quan hệ tới những object khác.

Hãy tạo dữ liệu đầu vào hẹp, chỉ gồm các giá trị cần thiết:

    context.setVariable("orderTotal", order.getTotal());
    context.setVariable("member", customer.isMember());
    context.setVariable("shippingRegion", order.getShippingRegion());

    Expression rule = parser.parseExpression(
        "#member and #orderTotal >= 1000 and #shippingRegion == 'VN'"
    );

Expression không cần biết password, token hay thông tin thanh toán để đánh giá rule này.

Một cách tổ chức tốt là tạo DTO hoặc record chuyên dùng cho evaluation:

    public record ShippingFacts(
        BigDecimal orderTotal,
        boolean member,
        String shippingRegion
    ) {}

    ShippingFacts facts = new ShippingFacts(
        order.getTotal(),
        customer.isMember(),
        order.getShippingRegion()
    );

    StandardEvaluationContext context =
        new StandardEvaluationContext(facts);

Khi dùng root object, biểu thức có thể đọc:

    orderTotal >= 1000 and member and shippingRegion == 'VN'

DTO hẹp giúp người đọc biết chính xác expression được phép sử dụng dữ liệu nào.

## 4. Phân biệt root object, variable và bean reference

Dữ liệu có thể đi vào expression qua nhiều đường khác nhau:

| Cách cung cấp | Cách tham chiếu | Ví dụ |
| --- | --- | --- |
| Root object | Tên property trực tiếp | orderTotal |
| Variable | Prefix # | #orderTotal |
| Bean reference | Prefix @, khi có BeanResolver | @pricingService |

Không chỉ variables mới cần được kiểm soát. Root object cũng có thể cung cấp nhiều property và method hơn expression thực sự cần.

Ví dụ, nếu root object là một service hoặc entity lớn, expression có thể truy cập thêm những thành phần mà người viết rule ban đầu không dự định sử dụng, tùy property accessor và method resolver được cấu hình.

Tương tự, nếu đăng ký BeanResolver cho phép tham chiếu nhiều bean, expression có thể truy cập các bean đó bằng cú pháp @beanName.

Vì vậy, hãy kiểm soát tất cả nguồn dữ liệu và quyền truy cập của context:

- Root object nên là DTO hoặc object có phạm vi dữ liệu hẹp.
- Variables chỉ nên chứa dữ kiện cần thiết.
- Functions chỉ nên thực hiện thao tác được cho phép.
- BeanResolver chỉ nên được cung cấp khi biểu thức đáng tin cậy thực sự cần bean.
- PropertyAccessor và MethodResolver cần được cấu hình theo mục đích sử dụng.

## 5. Không đặt secret trực tiếp trong chuỗi expression

Không viết token hoặc password thành literal trong expression:

    #apiClient.call('sk-live-sensitive-value')

Nội dung expression có thể được lưu trong cấu hình, database, log, trace, cache hoặc thông báo lỗi tùy cách ứng dụng quản lý. Đưa secret vào chuỗi làm tăng số nơi có thể vô tình lưu hoặc hiển thị nó.

Nếu một thao tác thật sự cần credential, hãy để Java service có trách nhiệm lấy credential từ secret manager hoặc cơ chế quản lý bí mật của ứng dụng. Expression chỉ nên quyết định một điều kiện nghiệp vụ không nhạy cảm hoặc gọi một API giới hạn nếu use case được kiểm soát.

Ví dụ, thay vì đưa token vào context:

    context.setVariable("apiToken", token);

hãy thực hiện xác thực hoặc gọi API trong service được kiểm soát, rồi chỉ cung cấp kết quả cần thiết:

    context.setVariable("authorized", authorizationResult.isAllowed());

    Boolean canContinue = parser
        .parseExpression("#authorized and #orderTotal <= #limit")
        .getValue(context, Boolean.class);

Expression chỉ cần biết quyết định authorized là true hay false; nó không cần biết credential đã tạo ra quyết định đó.

## 6. Tránh đưa toàn bộ ApplicationContext vào expression

ApplicationContext là một object có phạm vi rộng, có thể cung cấp quyền truy cập tới nhiều bean và dịch vụ của ứng dụng.

Không nên đặt ApplicationContext làm root object hoặc variable chỉ để expression có thể tìm dữ liệu tùy ý:

    context.setRootObject(applicationContext);

    context.setVariable("applicationContext", applicationContext);

Cách này mở rộng đáng kể bề mặt truy cập của expression. Tùy cấu hình accessor và resolver, biểu thức có thể tiếp cận nhiều object hơn nhu cầu nghiệp vụ ban đầu.

Nếu expression cần một bean cụ thể trong một luồng đáng tin cậy, hãy cấp đúng bean đó qua BeanResolver hoặc cung cấp một wrapper hẹp với API được phép.

Nếu expression chỉ cần một vài giá trị, hãy truyền các giá trị đó thay vì truyền cả container.

## 7. Giới hạn tính năng của EvaluationContext

StandardEvaluationContext cung cấp nhiều khả năng của SpEL, bao gồm root object, variables, functions, property accessors, method resolvers, type locator, constructor resolvers và bean resolver.

Đây là lựa chọn linh hoạt cho expression do ứng dụng kiểm soát. Nhưng không nên mặc định cung cấp toàn bộ khả năng này cho biểu thức không đáng tin cậy.

SimpleEvaluationContext được thiết kế cho các trường hợp data binding và property-based expression cần giới hạn tính năng. Tùy builder và cấu hình, có thể chọn property access và một số khả năng method invocation phù hợp.

SimpleEvaluationContext không cung cấp đầy đủ tính năng của StandardEvaluationContext; cụ thể, nó không hỗ trợ type references, constructors và bean references.

Ví dụ tạo context chỉ đọc cho data binding:

    SimpleEvaluationContext context =
        SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

Nếu chỉ cần đọc property trên một object dữ liệu, context giới hạn như vậy có thể phù hợp hơn context đầy đủ.

Tuy nhiên, SimpleEvaluationContext không phải cam kết tự động an toàn cho mọi biểu thức. Hãy xem chính xác property accessor và method resolver nào được bật, object nào được cung cấp và expression đến từ nguồn nào.

## 8. Expression do người dùng cung cấp cần được kiểm soát riêng

Rủi ro tăng lên khi người dùng có thể tự nhập hoặc sửa chuỗi SpEL.

Ví dụ, ứng dụng cho phép người dùng tạo rule:

    #orderTotal >= 1000

Nếu context chỉ chứa orderTotal, phạm vi dữ liệu được cung cấp khá hẹp.

Nhưng nếu cùng expression engine được cấp một object service rộng, các bean hoặc method có side effect, một expression khác có thể tìm cách truy cập thêm khả năng ngoài mục tiêu ban đầu.

Các biện pháp nên áp dụng:

- Ưu tiên expression do ứng dụng kiểm soát và lưu trong nguồn tin cậy.
- Nếu cho phép người dùng tạo rule, chỉ hỗ trợ một tập cú pháp và tính năng rõ ràng.
- Không đưa credential, token, private key hoặc object chứa secret vào context.
- Dùng DTO chỉ đọc, property accessor và method resolver giới hạn.
- Không đăng ký BeanResolver hoặc constructor resolver nếu use case không cần.
- Không cho phép expression gọi method có side effect hoặc I/O tùy ý.
- Xác thực kiểu và phạm vi giá trị đầu vào trước khi đánh giá.

Nếu nghiệp vụ chỉ cần vài phép so sánh hoặc toán tử logic, có thể cân nhắc một DSL hoặc rule model có cấu trúc thay cho việc cho người dùng nhập SpEL tổng quát.

Không nên dựa vào việc ẩn tên variable để bảo vệ dữ liệu. Ranh giới bảo vệ phải được thiết lập bằng việc không đưa secret vào context và giới hạn khả năng truy cập.

## 9. Cô lập context giữa các request

EvaluationContext có thể chứa variables và state thay đổi theo từng lần đánh giá. Nếu ứng dụng dùng chung một context mutable giữa nhiều request, dữ liệu của request này có thể bị ghi đè hoặc được quan sát trong request khác nếu việc đồng bộ và vòng đời không được kiểm soát.

Ví dụ không nên tùy tiện dùng chung context rồi cập nhật variable cho mỗi request:

    sharedContext.setVariable("customerId", customerId);
    sharedContext.setVariable("orderTotal", total);

Nếu hai request chạy đồng thời, chúng có thể ghi đè dữ liệu của nhau.

Cách đơn giản hơn là tạo context riêng cho mỗi lần đánh giá hoặc mỗi request:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("customerId", customerId);
    context.setVariable("orderTotal", total);

    Boolean allowed =
        expression.getValue(context, Boolean.class);

Expression đã parse có thể được giữ lại để tái sử dụng nếu source là cố định và đáng tin cậy. Context chứa dữ liệu request nên có vòng đời riêng, không chia sẻ state mutable giữa các request.

Nếu cần tối ưu hiệu năng, hãy tách phần cấu hình resolver/accessor bất biến khỏi dữ liệu động của từng request và bảo đảm cách tái sử dụng đó an toàn với concurrency.

## 10. Không log nội dung context hoặc secret

Debug expression không đồng nghĩa với việc ghi toàn bộ context vào log.

Tránh:

    log.debug("SpEL context: {}", context);
    log.debug("Evaluation variables: {}", variables);

Tùy cách triển khai, log object hoặc map có thể hiển thị token, password, dữ liệu cá nhân hoặc thông tin nội bộ.

Nên log thông tin kỹ thuật tối thiểu:

- Mã rule hoặc tên expression đã được kiểm soát.
- Thời điểm đánh giá và thời gian xử lý.
- Kết quả thành công/thất bại.
- Loại lỗi và vị trí expression nếu không chứa dữ liệu nhạy cảm.
- Correlation ID để tra cứu request.

Nếu cần quan sát giá trị đầu vào, chỉ log các field không nhạy cảm hoặc đã được redact. Không đưa secret vào expression literal vì nội dung expression cũng có thể xuất hiện trong log hoặc lỗi.

## 11. Nếu expression thực sự cần thông tin nhạy cảm

Có một số nghiệp vụ có thể cần quyết định dựa trên dữ liệu nhạy cảm. Khi đó, không nhất thiết phải đưa raw secret vào SpEL.

Ưu tiên thực hiện thao tác nhạy cảm trong một thành phần Java có quyền rõ ràng:

    boolean verified =
        credentialVerifier.verify(candidateCredential);

    context.setVariable("credentialVerified", verified);

    Boolean canProceed = parser
        .parseExpression("#credentialVerified and #accountEnabled")
        .getValue(context, Boolean.class);

Expression chỉ nhận kết quả boolean. Credential được xử lý trong verifier và không cần xuất hiện trong context.

Nếu bắt buộc phải cung cấp một giá trị nhạy cảm cho expression, hãy giới hạn:

- Chỉ một expression đã được kiểm soát mới được đánh giá.
- Context chỉ tồn tại trong phạm vi ngắn nhất cần thiết.
- Chỉ cung cấp giá trị cho lần đánh giá đó.
- Không cho phép expression khác hoặc người dùng khác truy cập context.
- Không log hoặc serialize context.
- Xóa tham chiếu tới dữ liệu sau khi hoàn thành nếu phù hợp với cách quản lý bộ nhớ của ứng dụng.

Việc xóa tham chiếu trong Java không bảo đảm secret đã biến mất tức thì khỏi bộ nhớ JVM. Với credential có yêu cầu bảo vệ cao, hãy dùng cơ chế secret management phù hợp và hạn chế tối đa số thành phần nhận được raw secret.

## 12. Những lỗi thiết kế thường gặp

| Thiết kế | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Đưa toàn bộ entity vào context | Expression có thể đọc nhiều field và quan hệ không cần thiết | Dùng DTO hẹp |
| Đưa password hoặc token vào variable | Expression có thể tham chiếu giá trị đó | Không đăng ký secret nếu không cần |
| Đặt ApplicationContext làm root | Mở rộng phạm vi truy cập tới container | Cung cấp object hoặc bean cụ thể |
| Cấp BeanResolver cho rule không tin cậy | Có thể mở đường truy cập bean ngoài dự kiến | Không cấp bean resolver nếu không cần |
| Cho phép method invocation rộng | Có thể gọi method có side effect hoặc I/O | Giới hạn MethodResolver và API được expose |
| Dùng chung mutable context giữa request | Có nguy cơ lẫn dữ liệu giữa các lần đánh giá | Context riêng theo request |
| Ghi toàn bộ context vào log | Secret có thể xuất hiện trong log và hệ thống quan sát | Redact và chỉ log metadata cần thiết |
| Tin rằng #variable được mã hóa | Variable chỉ là dữ liệu trong context | Thiết kế theo least privilege |

## 13. Checklist trước khi đánh giá expression

Trước khi gọi getValue, hãy xác định:

1. Expression có thực sự cần dữ liệu này không?
2. Root object có chứa field hoặc method nhạy cảm không?
3. Variables có chứa token, password, private key hoặc dữ liệu cá nhân không cần thiết không?
4. Có thể thay raw secret bằng một kết quả boolean hoặc dữ kiện đã được xử lý không?
5. Có cần BeanResolver, ConstructorResolver hoặc method invocation không?
6. Expression có đến từ nguồn người dùng không tin cậy không?
7. Context có được cô lập giữa các request không?
8. Log và thông báo lỗi có thể làm lộ expression hoặc dữ liệu đầu vào không?
9. Có thể dùng SimpleEvaluationContext hoặc một rule model giới hạn hơn không?
10. Các object được expose có đúng phạm vi quyền mà rule cần không?

Nếu câu trả lời cho một quyền truy cập là không cần thiết, hãy loại bỏ quyền đó khỏi context.

## 14. Những điểm cần nhớ

- EvaluationContext là nơi cung cấp root object, variables và các cơ chế truy cập cho SpEL.
- Variable được đăng ký bằng setVariable và tham chiếu bằng #name.
- Variable không tự được mã hóa hoặc che giấu; không phải secret store.
- Chỉ truyền dữ liệu cần thiết cho expression, không đưa toàn bộ entity hoặc ApplicationContext vào context.
- Không đưa password, token hoặc private key vào context nếu biểu thức không cần.
- Không đặt secret trực tiếp trong chuỗi expression.
- Root object, BeanResolver, PropertyAccessor và MethodResolver cũng là các đường truy cập dữ liệu cần kiểm soát.
- SimpleEvaluationContext cung cấp tập tính năng giới hạn hơn nhưng vẫn cần cấu hình phù hợp.
- Expression do người dùng cung cấp cần được kiểm soát chặt chẽ; cân nhắc DSL giới hạn nếu chỉ cần một tập rule nhỏ.
- Tạo context riêng cho dữ liệu động của từng request và tránh chia sẻ mutable state.
- Không log toàn bộ context hoặc variable values; redact dữ liệu nhạy cảm.
- Nếu logic cần secret, xử lý trong service có quyền rõ ràng rồi chỉ đưa kết quả cần thiết vào expression.

Thiết kế EvaluationContext theo nguyên tắc least privilege: mỗi expression chỉ nhìn thấy những dữ kiện và thao tác cần cho nhiệm vụ của nó. Giảm dữ liệu và quyền truy cập ngay từ đầu là cách rõ ràng nhất để tránh lộ secret ngoài ý muốn.

## Tài liệu tham khảo

- Spring Framework Reference — Evaluation: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework Reference — Variables: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html
- Spring Framework Reference — Security: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html
- Spring Framework Javadoc — SimpleEvaluationContext: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html

# Chẩn đoán khác biệt giữa môi trường test và runtime

Một biểu thức Spring Expression Language (SpEL) có thể chạy đúng trong unit test nhưng thất bại khi ứng dụng chạy thật. Cũng có trường hợp test trả về một kết quả, còn runtime lại cho kết quả khác dù source expression không thay đổi.

Nguyên nhân thường không nằm riêng ở cú pháp SpEL. Kết quả đánh giá phụ thuộc vào nhiều thành phần: parser và cấu hình parser, EvaluationContext, root object, biến, property accessor, method resolver, bean resolver, TypeConverter, dữ liệu thực tế, profile, classpath và thời điểm đánh giá.

Muốn chẩn đoán chính xác, cần so sánh toàn bộ điều kiện thực thi của expression giữa hai môi trường. Không nên chỉ sao chép source expression từ runtime về test rồi kết luận rằng hai nơi đang chạy cùng một cấu hình.

## 1. Hiểu vì sao test và runtime có thể khác nhau

### 1.1. Expression giống nhau chưa chắc có cùng kết quả

Ví dụ:

~~~java
Expression expression =
        parser.parseExpression("customer.active && total >= #minimum");
~~~

Trong test, root object có thể là một DTO đơn giản:

~~~java
OrderView order = new OrderView(true, new BigDecimal("150"));
context.setVariable("minimum", new BigDecimal("100"));
~~~

Trong runtime, root object có thể là entity được ORM quản lý, một proxy, một DTO được map từ request hoặc một object chứa property null. Biến minimum cũng có thể được lấy từ cấu hình môi trường khác.

Cùng một chuỗi expression nhưng kết quả có thể khác vì:

- Property có giá trị khác nhau hoặc null.
- Kiểu runtime của property khác nhau.
- Getter thực hiện logic khác nhau.
- Collection rỗng hoặc có thứ tự khác.
- Biến context thiếu hoặc có kiểu khác.
- Accessor hoặc resolver được đăng ký khác nhau.
- ConversionService khác nhau.
- Bean được tham chiếu có cấu hình hoặc trạng thái khác.
- Parser dùng cấu hình khác.
- Expression được evaluate ở thời điểm hoặc thread khác.

Vì vậy, khi so sánh test và runtime, hãy ghi nhận source cùng context và dữ liệu, thay vì chỉ so sánh kết quả cuối.

### 1.2. Tách các giai đoạn thực thi

Một luồng SpEL thông thường có thể chia thành các giai đoạn:

1. Nhận source expression hoặc template.
2. Parse source bằng ExpressionParser và ParserContext.
3. Tạo hoặc lấy Expression đã parse.
4. Chuẩn bị EvaluationContext, root object và biến.
5. Evaluate expression.
6. Chuyển đổi kết quả hoặc dùng kết quả trong nghiệp vụ.

Lỗi ở mỗi giai đoạn có nguyên nhân khác nhau:

| Giai đoạn | Khác biệt thường gặp | Dấu hiệu |
|---|---|---|
| Source | Test dùng chuỗi khác runtime | AST hoặc message parse khác |
| Parse | Parser configuration hoặc parser context khác | ParseException hoặc cấu trúc expression khác |
| Context | Accessor, resolver, converter khác | Property/method/bean không được phân giải |
| Input | Root object hoặc biến khác | Kết quả Boolean hoặc giá trị khác |
| Evaluate | Getter, method, proxy hoặc backend khác | EvaluationException hoặc lỗi nghiệp vụ |
| Kết quả | Kiểu đích hoặc converter khác | ConversionException hoặc cast lỗi |

Hãy xác định giai đoạn đầu tiên mà hai môi trường khác nhau. Việc này thu hẹp phạm vi điều tra và tránh thay đổi expression khi nguyên nhân nằm ở cấu hình hoặc dữ liệu.

## 2. So sánh source expression và parser

### 2.1. Ghi đúng source đã parse

Nếu expression được tạo từ cấu hình, database hoặc request, test có thể đang dùng một literal viết trong code còn runtime dùng giá trị đã được load hoặc ghép động.

Giữ source trước khi parse:

~~~java
String source = rule.getExpression();

Expression expression = parser.parseExpression(source);
~~~

Khi cần chẩn đoán, ghi nhận:

- ID hoặc tên rule.
- Phiên bản rule/cấu hình.
- Độ dài source.
- Hash của source.
- Source đã redact nếu được phép ghi log.
- ParserContext nếu dùng template.

Không chỉ ghi một tên rule chung. Một rule có thể được cập nhật trong database hoặc cache mà test fixture vẫn đang sử dụng phiên bản cũ.

### 2.2. Parse riêng trước khi evaluate

Tách parse khỏi evaluate giúp xác định lỗi thuộc cú pháp hay runtime:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
} catch (SpelParseException ex) {
    logger.error(
            "Cannot parse ruleId={}, position={}, code={}",
            ruleId,
            ex.getPosition(),
            ex.getMessageCode(),
            ex
    );
    throw ex;
}

try {
    Object result = expression.getValue(context);
    return result;
} catch (SpelEvaluationException ex) {
    logger.error(
            "Cannot evaluate ruleId={}, position={}, code={}",
            ruleId,
            ex.getPosition(),
            ex.getMessageCode(),
            ex
    );
    throw ex;
}
~~~

Nếu test parse thành công nhưng runtime parse thất bại, hãy so sánh source chính xác, phiên bản Spring và parser context trước khi xem xét dữ liệu.

Nếu cả hai parse thành công nhưng kết quả khác, chuyển sang so sánh context và input.

### 2.3. So sánh ParserContext và template

Một expression thuần và template expression không có cùng quy tắc parse:

~~~java
parser.parseExpression("total >= #minimum");
~~~

~~~java
parser.parseExpression(
        "Order total: #{total}",
        new TemplateParserContext()
);
~~~

Nếu runtime dùng TemplateParserContext nhưng test dùng parser mặc định, cùng một chuỗi có thể được hiểu khác nhau hoặc parse thất bại.

Ghi nhận loại ParserContext, prefix/suffix của template nếu tùy chỉnh và parser implementation thực tế.

### 2.4. So sánh SpelParserConfiguration

SpelParserConfiguration có thể thay đổi hành vi evaluate:

- Auto-grow null references.
- Auto-grow collections.
- Maximum auto-grow size.
- Compiler mode.
- Một số tùy chọn khác tùy phiên bản Spring.

Ví dụ:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                false,
                false,
                128
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Nếu test dùng parser mặc định nhưng runtime bật auto-grow, biểu thức truy cập nested path hoặc collection index có thể cho kết quả khác. Một nơi có thể tự tạo object trung gian trong khi nơi kia ném lỗi vì null.

Hãy ghi nhận cấu hình parser ở cả hai nơi, không suy luận từ source expression.

## 3. So sánh phiên bản Spring và classpath

### 3.1. Spring Framework và Spring Boot version

Khác biệt phiên bản có thể ảnh hưởng tới:

- Cú pháp hoặc tính năng SpEL được hỗ trợ.
- API builder và default behavior.
- PropertyAccessor, MethodResolver và TypeConverter.
- Compiler và các giới hạn thực thi.
- Cách Spring tích hợp expression trong annotation hoặc binding.
- Lỗi đã được sửa giữa các bản phát hành.

Kiểm tra dependency thực tế trong test và runtime. Không chỉ nhìn phiên bản khai báo trong build file; dependency management, transitive dependency hoặc packaging có thể khiến artifact triển khai dùng phiên bản khác.

Với Maven, có thể xem dependency tree:

~~~bash
mvn dependency:tree
~~~

Với Gradle:

~~~bash
./gradlew dependencies
~~~

Đối chiếu các module liên quan, đặc biệt spring-expression, spring-core, spring-context và Spring Boot dependency management. Các module Spring Framework nên được quản lý theo bộ phiên bản tương thích.

### 3.2. Kiểm tra dependency bị override

Một thư viện khác có thể kéo theo phiên bản Spring không mong muốn. Test runtime classpath và packaged application classpath cũng có thể khác nhau.

Khi cần xác nhận class được load từ đâu, có thể ghi nhận code source:

~~~java
static void logClassOrigin(Class<?> type) {
    var protectionDomain = type.getProtectionDomain();
    var codeSource = protectionDomain == null
            ? null
            : protectionDomain.getCodeSource();

    logger.info(
            "class={}, origin={}",
            type.getName(),
            codeSource == null
                    ? "unknown"
                    : codeSource.getLocation()
    );
}
~~~

Dùng cho các class như SpelExpressionParser, StandardEvaluationContext hoặc một converter tùy chỉnh. Thông tin này giúp phát hiện classpath hoặc packaging khác dự kiến.

### 3.3. ClassLoader và môi trường triển khai

Plugin, application server, module system hoặc custom class loader có thể làm cho một lớp được tìm thấy trong test nhưng không tìm thấy ở runtime.

Điều này thường ảnh hưởng đến:

- TypeLocator và constructor expression.
- Reflection trên class hoặc method.
- Converter có kiểu miền riêng.
- Bean được load từ module hoặc plugin.
- Proxy và class được tạo động.

Nếu lỗi liên quan tới type resolution hoặc reflection, ghi nhận ClassLoader của target và class mà expression muốn truy cập.

## 4. So sánh EvaluationContext

EvaluationContext quyết định expression có thể nhìn thấy và thực hiện những gì. Hai môi trường dùng cùng source nhưng tạo context khác nhau là nguyên nhân rất phổ biến của lỗi.

### 4.1. StandardEvaluationContext và SimpleEvaluationContext

Test có thể dùng StandardEvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);
~~~

Trong khi runtime dùng SimpleEvaluationContext:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

Hai loại context không có cùng tập tính năng. SimpleEvaluationContext giới hạn type reference, constructor và bean reference; method invocation cũng không được bật mặc định trong builder thông dụng.

Nếu test gọi method hoặc tham chiếu bean thành công nhưng runtime thất bại, hãy xác định context thực tế trước khi thay đổi expression.

Không chuyển runtime sang context rộng quyền chỉ để làm test và production có cùng kết quả. Chọn context theo quyền thực sự cần thiết của use case.

### 4.2. Root object

So sánh:

- Class thực tế của root object.
- Object có phải proxy hay không.
- Giá trị và kiểu của các property được expression truy cập.
- Object trung gian có null không.
- Getter có thể truy cập dữ liệu lazy không.
- Object có bị thay đổi giữa lúc chuẩn bị và evaluate không.

Có thể ghi nhận kiểu root:

~~~java
Object root = rootObject;

logger.debug(
        "SpEL root type={}",
        root == null ? "null" : root.getClass().getName()
);
~~~

Không log toàn bộ root object nếu nó chứa dữ liệu cá nhân, token hoặc thông tin nhạy cảm. Thay vào đó, ghi các field cần thiết theo dạng đã redact.

### 4.3. Biến context

Test thường set biến trực tiếp:

~~~java
context.setVariable("minimum", new BigDecimal("100"));
~~~

Runtime có thể lấy biến từ request, cấu hình hoặc một component khác. Hãy so sánh:

- Tên biến có giống nhau không.
- Biến có tồn tại không.
- Kiểu runtime của giá trị.
- Giá trị có null không.
- Giá trị có được chuẩn hóa trước khi evaluate không.

Ví dụ, Integer 100 và BigDecimal 100 có thể tham gia phép toán hoặc overload resolution khác nhau. Đừng chỉ ghi giá trị hiển thị; hãy ghi cả class của giá trị.

Có thể dùng helper an toàn:

~~~java
static String describeValue(Object value) {
    if (value == null) {
        return "null";
    }

    return value.getClass().getName();
}
~~~

Với dữ liệu nhạy cảm, chỉ log kiểu và metadata, không log giá trị.

### 4.4. PropertyAccessor và thứ tự đăng ký

Một context có thể đăng ký accessor tùy chỉnh:

~~~java
context.addPropertyAccessor(customAccessor);
~~~

Nếu test và runtime đăng ký các accessor khác nhau hoặc theo thứ tự khác nhau, cùng property có thể được đọc qua các đường khác nhau.

So sánh:

- Loại accessor.
- Target class mà accessor hỗ trợ.
- Thứ tự đăng ký.
- Hành vi canRead/read/canWrite/write.
- Accessor có gọi backend hoặc getter khác không.

Accessor tùy chỉnh nên giới hạn getSpecificTargetClasses() chính xác. Không khai báo hỗ trợ mọi target nếu chỉ xử lý một loại object.

### 4.5. MethodResolver, ConstructorResolver và BeanResolver

Method call, constructor expression và bean reference phụ thuộc resolver của context.

Ví dụ bean reference:

~~~java
@pricingService.calculate(order)
~~~

Chỉ hoạt động nếu context có BeanResolver phù hợp. Test có thể dùng một context được cấu hình BeanFactoryResolver trong khi runtime không có resolver hoặc dùng allowlist khác.

Method resolver tùy chỉnh cũng có thể làm thay đổi overload được chọn. Constructor resolver và TypeLocator có thể khiến constructor expression hoạt động ở test nhưng thất bại trong artifact triển khai.

Hãy so sánh các resolver thực tế và danh sách bean/type/method được cho phép. Không log secret hoặc toàn bộ cấu trúc ApplicationContext.

## 5. So sánh TypeConverter và ConversionService

### 5.1. Chuyển đổi kiểu ảnh hưởng kết quả

SpEL có thể cần chuyển đổi khi:

- Gán giá trị vào property.
- Gọi method với argument có kiểu khác.
- Gọi constructor.
- Yêu cầu getValue với kiểu kết quả đích.

StandardEvaluationContext thường dùng StandardTypeConverter. Ứng dụng có thể thay TypeConverter bằng một converter dựa trên ConversionService riêng.

Ví dụ:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);
~~~

Nếu test đăng ký converter CustomerCode còn runtime không đăng ký, một expression có thể chạy trong test nhưng lỗi khi evaluate ở production.

### 5.2. So sánh converter đã đăng ký

Không chỉ so sánh tên bean ConversionService. Hãy xác định cấu hình converter:

- Converter và ConverterFactory tùy chỉnh.
- GenericConverter và ConditionalGenericConverter.
- Formatter có liên quan.
- Converter phụ thuộc TypeDescriptor hoặc annotation.
- Quy tắc null và dữ liệu sai định dạng.

Một ConversionService có thể hỗ trợ cùng cặp kiểu nhưng vẫn cho kết quả khác do converter tùy chỉnh hoặc locale.

### 5.3. Giá trị hiển thị giống nhưng kiểu khác

Ví dụ chuỗi "100", Integer 100 và BigDecimal 100 có thể được hiển thị giống nhau nhưng không phải cùng kiểu.

Trong test, dữ liệu fixture có thể tạo BigDecimal trực tiếp. Runtime nhận chuỗi từ JSON hoặc request và chuyển thành Integer. Điều này có thể ảnh hưởng so sánh, overload hoặc kết quả getValue.

Ghi nhận source type và target type khi điều tra lỗi conversion.

## 6. So sánh dữ liệu và object model

### 6.1. Fixture test thường đơn giản hơn dữ liệu thật

Test có thể dùng object được tạo trực tiếp:

~~~java
Order order = new Order("O-100", "PAID", new BigDecimal("150"));
~~~

Runtime có thể nhận object qua:

- JSON deserialization.
- Database/ORM.
- Mapping giữa DTO và entity.
- Message broker.
- Cache.
- Một service khác.

Các nguồn này có thể tạo null, default value, kiểu collection hoặc trạng thái khác nhau.

Hãy dùng một snapshot dữ liệu đã được redact để tái hiện lỗi, thay vì chỉ tạo một object gần giống bằng tay.

### 6.2. Null, empty và missing không giống nhau

Cần phân biệt:

- Property không có trong payload.
- Property có nhưng giá trị null.
- Collection rỗng.
- Collection không được khởi tạo.
- Map thiếu key.
- Map có key với value null.

Các trường hợp này có thể dẫn tới kết quả SpEL khác nhau, đặc biệt khi dùng safe navigation, selection, projection hoặc indexer.

### 6.3. Kiểu collection và thứ tự

Test thường dùng List.of hoặc LinkedHashMap với thứ tự xác định. Runtime có thể dùng HashSet, HashMap hoặc collection từ ORM.

Nếu expression dùng first/last selection hoặc phụ thuộc thứ tự duyệt, kết quả có thể khác. Selection không tự sắp xếp dữ liệu.

Khi thứ tự có ý nghĩa nghiệp vụ, hãy sắp xếp dữ liệu trước khi evaluate hoặc dùng cấu trúc collection có hợp đồng thứ tự rõ ràng.

### 6.4. Proxy và lazy loading

Entity được ORM quản lý có thể là proxy. Property getter có thể kích hoạt lazy loading hoặc yêu cầu một transaction/session đang mở.

Test dùng DTO không proxy nên expression đọc property thành công. Runtime dùng proxy sau khi transaction đóng có thể phát sinh lỗi khi getter truy cập quan hệ lazy.

Khi nghi ngờ, ghi nhận class thực tế của object và kiểm tra getter có kích hoạt truy vấn hay không. Không gọi thêm getter tùy tiện trong diagnostic logging vì chính thao tác log có thể kích hoạt lazy loading.

Cách ổn định hơn là tạo DTO/view chứa dữ liệu cần thiết trong transaction rồi đánh giá expression trên DTO đó.

## 7. So sánh profile và cấu hình môi trường

### 7.1. Active profiles

Spring profile có thể làm thay đổi bean, converter, property source hoặc cấu hình parser:

~~~java
@Profile("test")
@Configuration
class TestExpressionConfiguration {
}
~~~

~~~java
@Profile("prod")
@Configuration
class ProductionExpressionConfiguration {
}
~~~

Nếu test dùng profile test còn runtime dùng profile production, các bean cùng tên hoặc cùng vai trò có thể có implementation khác nhau.

Ghi nhận active profiles và cấu hình được chọn. Không đưa giá trị secret vào log.

### 7.2. Property sources và Environment

Các giá trị trong expression có thể phụ thuộc property placeholder hoặc bean cấu hình:

~~~java
@Value("$" + "{rules.minimum-total:100}")
private BigDecimal minimumTotal;
~~~

Test có thể dùng application-test.yml hoặc @TestPropertySource. Runtime có thể lấy giá trị từ environment variable, ConfigMap, secret store hoặc external configuration service.

So sánh tên property và nguồn cấu hình, không chỉ giá trị cuối. Cũng cần kiểm tra default value có được áp dụng ở một môi trường nhưng không ở môi trường kia hay không.

### 7.3. Property placeholder và SpEL khác nhau

Hai cú pháp thường gặp:

~~~java
@Value("${app.minimum-total:100}")
private BigDecimal minimumTotal;
~~~

~~~java
@Value("#{pricingPolicy.minimumTotal}")
private BigDecimal minimumTotal;
~~~

Placeholder ${...} lấy giá trị từ Environment/property source. SpEL #{...} đánh giá biểu thức, có thể truy cập object hoặc bean theo context.

Nếu test chỉ khai báo property nhưng runtime lại tham chiếu bean, hai luồng có thể có thứ tự khởi tạo và dependency khác nhau.

### 7.4. Environment variable và cách đặt tên

Tên biến môi trường có thể được ánh xạ sang property theo quy tắc của Spring Boot. Cần kiểm tra giá trị thực tế sau khi binding, đặc biệt khi key có dấu gạch ngang, dấu chấm hoặc cấu hình lồng nhau.

Không log secret; chỉ ghi nhận property đã có, nguồn được chọn và kiểu sau binding.

## 8. Locale, timezone và định dạng dữ liệu

### 8.1. Locale

Locale có thể ảnh hưởng đến Formatter hoặc conversion giữa String và kiểu ngày, số. Test chạy với locale mặc định của máy developer có thể khác container production.

Ví dụ, chuỗi số có dấu phẩy hoặc dấu chấm thập phân có thể được parse khác nhau tùy formatter và locale.

Nếu expression phụ thuộc formatting, hãy cấu hình locale rõ ràng thay vì dựa vào default locale của JVM.

### 8.2. Timezone và ngày giờ

So sánh các giá trị:

- ZoneId mặc định.
- TimeZone mặc định của JVM.
- Clock được inject.
- Kiểu ngày giờ được sử dụng.
- Formatter và parser pattern.

Test thường dùng ngày cố định hoặc Clock giả. Runtime dùng thời gian hệ thống và timezone của container. Một điều kiện so sánh ngày có thể đổi kết quả gần ranh giới ngày hoặc daylight saving.

Nên inject Clock vào logic nghiệp vụ và dùng Instant/OffsetDateTime/LocalDate theo semantics cần thiết. Tránh gọi trực tiếp thời gian hệ thống bên trong getter hoặc method mà expression sử dụng.

### 8.3. Precision và rounding

Số tiền hoặc số thập phân có thể khác do dữ liệu được deserialize, chuyển đổi hoặc làm tròn ở các tầng khác nhau.

Dùng BigDecimal với scale và rounding policy rõ ràng. Không chuyển sang double chỉ để làm expression dễ viết.

## 9. Compiler mode và caching

### 9.1. Interpreted và compiled mode

SpEL hỗ trợ compiler mode với các lựa chọn như OFF, IMMEDIATE và MIXED tùy phiên bản Spring.

Test có thể dùng parser mặc định ở interpreted mode trong khi runtime bật compiler. Một số expression có thể không phù hợp với compiler hoặc có hành vi cần được kiểm thử riêng theo mode.

Khi lỗi chỉ xuất hiện ở runtime, hãy tái hiện bằng đúng compiler mode và cấu hình parser. Nếu cần cô lập nguyên nhân, chạy một test so sánh interpreted và compiled với cùng source, context và dữ liệu.

Không coi compiler mode là cơ chế bảo mật hoặc giả định compiled luôn nhanh hơn cho mọi expression.

### 9.2. Cache Expression

Ứng dụng thường cache Expression đã parse để tránh parse lặp lại. Test có thể parse mới mỗi lần trong khi runtime dùng expression cache.

Hãy xác định cache key có bao gồm đúng source, parser context và cấu hình liên quan không. Nếu rule source thay đổi nhưng cache vẫn trả Expression cũ, runtime có thể chạy nội dung khác với cấu hình hiện tại.

Không cache một Expression theo key quá rộng nếu source hoặc parser configuration có thể khác nhau.

### 9.3. Không chia sẻ EvaluationContext mutable tùy tiện

Expression có thể được cache và tái sử dụng; EvaluationContext thường chứa root object, biến và các resolver/accessor. Không nên chia sẻ một context mutable giữa các request nếu mỗi request cần root hoặc biến riêng.

Một context dùng chung có thể khiến request này nhìn thấy biến hoặc root object do request khác thiết lập. Hãy tách phần cấu hình bất biến khỏi dữ liệu theo lần evaluate và tạo context theo request hoặc operation.

## 10. Thread, transaction và security context

### 10.1. Thread-local context

Một số dữ liệu ứng dụng được lấy từ ThreadLocal, SecurityContextHolder, RequestContextHolder hoặc MDC. Test chạy đồng bộ trên một thread có thể nhìn thấy context, trong khi runtime chuyển sang executor khác lại không có.

Nếu getter hoặc method mà expression gọi dựa vào thread-local, kết quả có thể khác khi chạy async.

Không giả định thread-local tự truyền qua mọi executor. Hãy truyền dữ liệu cần thiết qua argument/context một cách tường minh hoặc cấu hình context propagation phù hợp.

### 10.2. Transaction boundary

Expression có thể gọi getter hoặc method truy cập repository. Test có thể chạy trong @Transactional test, trong khi runtime gọi sau khi transaction kết thúc.

Điều này ảnh hưởng lazy loading, session và khả năng đọc dữ liệu. Xác định transaction đang hoạt động tại thời điểm evaluate, đặc biệt nếu expression được chạy trong event listener hoặc async task.

### 10.3. Security principal và tenant

Test có thể dùng user có quyền quản trị hoặc mock SecurityContext. Runtime dùng principal và tenant thực tế.

Nếu expression gọi bean policy hoặc getter phụ thuộc security context, kết quả có thể khác do quyền, tenant hoặc scope dữ liệu.

Không dùng expression để thay thế authorization. Hãy kiểm tra quyền ở service và chỉ đưa dữ liệu thuộc phạm vi principal vào root object.

## 11. Kiểm tra bean và proxy được tham chiếu

### 11.1. Cùng tên bean nhưng implementation khác

Profile hoặc conditional configuration có thể đăng ký các implementation khác nhau dưới cùng tên hoặc cùng interface. Test có thể dùng fake/mock bean; runtime dùng service thật.

Nếu expression gọi method trên bean, hãy ghi nhận:

- Bean name.
- Class target thực tế.
- Có phải Spring proxy không.
- Method signature được gọi.
- Kết quả và lỗi của method.
- Dependency và profile đã tạo bean đó.

### 11.2. Proxy và method invocation

Spring AOP có thể bọc bean bằng proxy. Một method call trong expression có thể đi qua proxy và kích hoạt transaction, security, cache hoặc advice khác.

Test dùng object trực tiếp không có proxy nên không tái hiện các interceptor.

Khi cần kiểm tra proxy, có thể ghi nhận class runtime và dùng AopUtils ở diagnostic code nếu dependency có sẵn. Tránh ép unwrap proxy trong logic nghiệp vụ chỉ để làm expression chạy.

### 11.3. Không log object nhạy cảm

Không log toàn bộ bean, root object hoặc argument. Ghi nhận tên bean, class, ID kỹ thuật đã redact và metadata cần thiết. Log method arguments chỉ khi dữ liệu không nhạy cảm và có chính sách phù hợp.

## 12. Tạo bản ghi chẩn đoán có thể tái hiện

Một bản ghi chẩn đoán hữu ích nên chứa đủ thông tin để dựng lại lần evaluate mà không làm lộ dữ liệu nhạy cảm.

Có thể ghi nhận:

| Nhóm | Thông tin |
|---|---|
| Rule | ID, version, source hash, độ dài |
| Runtime | Application version, Spring version, Java version |
| Parser | Parser class, ParserContext, compiler mode, auto-grow settings |
| Context | Standard/Simple context, root class, biến và kiểu biến |
| Resolver | Accessor, method/constructor resolver, bean resolver |
| Conversion | TypeConverter và ConversionService implementation |
| Environment | Active profile, locale, timezone, cấu hình không nhạy cảm |
| Execution | Thời điểm, thread, transaction state nếu cần |
| Result | Kiểu kết quả, trạng thái thành công/thất bại |
| Error | Exception class, SpEL position, message code, cause chain |

Không cần ghi toàn bộ mọi trường cho mọi request. Có thể bật diagnostics có chọn lọc theo rule ID hoặc chỉ khi lỗi xảy ra.

### 12.1. Helper ghi nhận kiểu và metadata

~~~java
static String typeOf(Object value) {
    return value == null
            ? "null"
            : value.getClass().getName();
}
~~~

~~~java
logger.debug(
        "ruleId={}, sourceLength={}, rootType={}, minimumType={}",
        ruleId,
        source.length(),
        typeOf(rootObject),
        typeOf(context.lookupVariable("minimum"))
);
~~~

Ví dụ chỉ ghi kiểu và độ dài, không ghi giá trị thực tế. Hãy chọn metadata phù hợp với chính sách bảo vệ dữ liệu của ứng dụng.

### 12.2. Lưu source hash

Có thể tạo hash để so sánh expression giữa test và runtime:

~~~java
MessageDigest digest =
        MessageDigest.getInstance("SHA-256");

byte[] hash = digest.digest(
        source.getBytes(StandardCharsets.UTF_8)
);

String sourceHash =
        HexFormat.of().formatHex(hash);
~~~

Hash giúp xác nhận hai môi trường có dùng cùng source mà không cần ghi toàn bộ source vào log. Nếu source chứa secret hoặc literal nhạy cảm, vẫn cần bảo vệ dữ liệu ở kho lưu trữ và diagnostic record.

## 13. Quy trình tái hiện lỗi test/runtime

Thực hiện theo trình tự để tìm khác biệt đầu tiên:

1. **Xác nhận source.** So sánh source hash, rule ID và version.
2. **Xác nhận dependency.** So sánh Spring Framework, Spring Boot, Java và classpath thực tế.
3. **Xác nhận parser.** So sánh ParserContext và SpelParserConfiguration.
4. **Xác nhận context.** So sánh loại context, accessor, resolver và TypeConverter.
5. **Xác nhận root.** So sánh class runtime, proxy, null và trạng thái property liên quan.
6. **Xác nhận biến.** So sánh tên, kiểu và miền giá trị của từng biến.
7. **Xác nhận môi trường.** So sánh profile, property source, locale, timezone và security context.
8. **Xác nhận thời điểm.** So sánh thread, transaction, lifecycle phase và async behavior.
9. **Tái hiện bằng fixture đã redact.** Dùng snapshot dữ liệu thực tế thay vì object giả định gần giống.
10. **Tách parse/evaluate.** Xác định lỗi xảy ra trước hay trong lúc đánh giá.
11. **So sánh compiler mode/cache.** Chỉ khi các điều kiện trước đã tương đương.
12. **Sửa nguyên nhân gốc.** Đồng bộ cấu hình cần thiết hoặc thay đổi thiết kế dữ liệu/context; không nới quyền toàn bộ chỉ để hết lỗi.

Hãy ghi lại khác biệt đầu tiên có thể giải thích kết quả. Nhiều thay đổi đồng thời sẽ khiến khó xác định thay đổi nào thực sự giải quyết vấn đề.

## 14. Ví dụ: kiểm tra cấu hình parser và context

Có thể gom việc tạo parser vào một factory để test và runtime dùng cùng cấu hình:

~~~java
@Configuration
public class SpelConfiguration {

    @Bean
    public ExpressionParser expressionParser() {
        SpelParserConfiguration configuration =
                new SpelParserConfiguration(
                        false,
                        false,
                        128
                );

        return new SpelExpressionParser(configuration);
    }

    @Bean
    public ConversionService expressionConversionService() {
        return new DefaultConversionService();
    }
}
~~~

Tạo context theo lần đánh giá:

~~~java
@Component
public class RuleEvaluator {

    private final ExpressionParser parser;
    private final ConversionService conversionService;

    public RuleEvaluator(
            ExpressionParser parser,
            ConversionService conversionService) {
        this.parser = parser;
        this.conversionService = conversionService;
    }

    public Boolean evaluate(
            String source,
            Object rootObject,
            BigDecimal minimum) {

        StandardEvaluationContext context =
                new StandardEvaluationContext(rootObject);

        context.setVariable("minimum", minimum);
        context.setTypeConverter(
                new StandardTypeConverter(conversionService)
        );

        Expression expression = parser.parseExpression(source);

        return expression.getValue(context, Boolean.class);
    }
}
~~~

Test nên dùng chính RuleEvaluator hoặc cùng factory cấu hình thay vì tự tạo một parser và context khác biệt:

~~~java
@Test
void evaluatesRuleWithProductionConfiguration() {
    Boolean result = evaluator.evaluate(
            "status == 'PAID' && total >= #minimum",
            orderView,
            new BigDecimal("100")
    );

    assertTrue(result);
}
~~~

Cấu hình dùng chung làm giảm khả năng test vô tình chạy một tập tính năng khác runtime. Dữ liệu test vẫn cần đại diện cho các trường hợp runtime có thể gặp.

## 15. Kiểm thử theo tầng

### 15.1. Unit test cho expression

Unit test nên kiểm tra source, root object và biến với dữ liệu xác định. Nó phù hợp để kiểm tra logic expression nhanh và dễ tái hiện.

Không mock parser hoặc context quá mức nếu mục tiêu là xác nhận SpEL thực sự phân tích và đánh giá biểu thức.

### 15.2. Integration test cho Spring context

Integration test cần dùng cấu hình bean, converter, profile và resolver gần với runtime. Nếu expression tham chiếu bean, test nên tạo ApplicationContext và sử dụng bean thật hoặc test double được cấu hình đúng phạm vi.

Kiểm tra cả thứ tự khởi tạo nếu expression được dùng trong @Value hoặc bean definition.

### 15.3. Test với profile và property source

Dùng profile và property source giống từng môi trường quan trọng. Không giả định application-test.yml và cấu hình triển khai có cùng giá trị.

Có thể dùng @ActiveProfiles và @TestPropertySource để tạo test có chủ đích. Với Spring Boot, kiểm tra cách property source được ưu tiên khi có nhiều nguồn cấu hình.

### 15.4. Test trên artifact triển khai

Một số lỗi chỉ xuất hiện sau packaging do classpath, resource, class loader hoặc cấu hình môi trường. Khi có nghi ngờ, chạy integration test hoặc smoke test trên artifact/container được build theo cách gần với triển khai.

Không cần sao chép toàn bộ production data vào test. Dùng fixture đã redact và cấu hình tương đương ở những điểm có ảnh hưởng đến expression.

## 16. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Khác biệt có thể có | Hướng điều tra |
|---|---|---|
| Test parse được, runtime parse lỗi | Source, Spring version hoặc ParserContext khác | So sánh source hash và parser |
| Property tồn tại trong test nhưng không có ở runtime | Root class, proxy hoặc accessor khác | Ghi class thực tế và kiểm tra getter |
| Test gọi method được, runtime không được | Simple/Standard context hoặc MethodResolver khác | So sánh context và resolver |
| Bean reference chỉ lỗi ở runtime | BeanResolver, profile hoặc bean name khác | Kiểm tra resolver và bean configuration |
| String conversion chỉ lỗi ở production | Converter chưa đăng ký hoặc TypeDescriptor khác | So sánh ConversionService |
| Kết quả selection khác | Collection data hoặc thứ tự khác | So sánh dữ liệu và collection implementation |
| Nested path chỉ lỗi ngoài production | Null, lazy proxy hoặc auto-grow khác | Kiểm tra object graph và parser configuration |
| Ngưỡng số cho kết quả khác | Integer/Long/BigDecimal hoặc rounding khác | Ghi source/target type và converter |
| Điều kiện ngày giờ lệch | Locale, timezone hoặc Clock khác | Cấu hình thời gian rõ ràng |
| Chỉ lỗi khi chạy async | Thread-local, transaction hoặc security context không được truyền | Kiểm tra executor và context propagation |
| Chỉ lỗi khi bật compiler | Interpreted/compiled mode khác | Tái hiện với cùng compiler mode |
| Rule cũ vẫn chạy sau khi cập nhật | Expression cache key hoặc invalidation sai | Kiểm tra cache và version |
| Startup lỗi do bean đang tạo | SpEL bean lookup tạo dependency vòng | Kiểm tra @Value và dependency graph |
| Log không đủ thông tin | Chỉ ghi message ngoài | Ghi position, message code và cause chain |

Không sửa bằng cách bắt mọi exception rồi trả false/null. Hãy giữ nguyên nguyên nhân và phân loại parse failure, evaluation failure, conversion failure, lỗi backend và lỗi quyền.

## 17. Nguyên tắc vận hành

Để giảm khác biệt giữa test và runtime:

- Dùng một nơi cấu hình parser và TypeConverter khi các luồng cần cùng chính sách.
- Tạo EvaluationContext theo lần evaluate với root và biến rõ ràng.
- Dùng DTO/view thay vì truyền entity hoặc service có object graph lớn.
- Đăng ký converter/accessor/resolver ở cấu hình có thể kiểm thử.
- Khóa phiên bản dependency theo dependency management của dự án.
- Kiểm soát profile và property source.
- Dùng Clock, locale và timezone rõ ràng khi rule phụ thuộc thời gian hoặc định dạng.
- Kiểm thử cả interpreted và compiled mode nếu runtime dùng compiler.
- Có chính sách cache expression và invalidation theo version.
- Không chia sẻ context mutable giữa request.
- Không log dữ liệu nhạy cảm khi bật diagnostics.
- Giữ authorization và validation ở tầng nghiệp vụ.

Test tốt không phải là test có nhiều mock nhất; test cần tái hiện đúng parser, context và điều kiện dữ liệu có ảnh hưởng đến biểu thức.

## 18. Tổng kết

Khác biệt giữa test và runtime thường xuất phát từ môi trường thực thi SpEL chứ không chỉ từ source expression.

Khi điều tra, hãy so sánh lần lượt:

- Source expression, rule version và ParserContext.
- Spring/Java version, classpath và ClassLoader.
- SpelParserConfiguration và compiler mode.
- StandardEvaluationContext hoặc SimpleEvaluationContext.
- Root object, proxy, property và biến.
- PropertyAccessor, MethodResolver, ConstructorResolver và BeanResolver.
- TypeConverter, ConversionService và Formatter.
- Profile, property source, locale, timezone và dữ liệu.
- Thread, transaction, security context, cache và thời điểm evaluate.

Hãy tách parse khỏi evaluate, ghi nhận metadata có thể tái hiện, dùng fixture đã redact và tìm khác biệt đầu tiên giải thích được lỗi. Khi test và runtime dùng chung cấu hình parser/context ở những điểm cần thiết, đồng thời dữ liệu được chuẩn bị theo hợp đồng rõ ràng, hành vi SpEL sẽ dễ dự đoán và dễ chẩn đoán hơn.
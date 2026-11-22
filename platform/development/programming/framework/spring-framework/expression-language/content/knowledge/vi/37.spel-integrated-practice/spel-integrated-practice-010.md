# Hồ sơ hoàn chỉnh: cú pháp, context, kiểm thử, bảo mật và hiệu năng

## Mục tiêu

Bài thực hành này kết nối các phần quan trọng của Spring Expression Language (SpEL) thành một hồ sơ triển khai có thể bàn giao và vận hành. Bạn sẽ xác định cú pháp và cách parse expression; mô tả root object, variables, bean và function; cấu hình EvaluationContext theo quyền tối thiểu; đánh giá kết quả và xử lý lỗi; xây dựng kiểm thử chức năng, dữ liệu biên và quyền truy cập; bảo vệ expression khỏi việc sử dụng ngoài dự kiến; và đo hiệu năng trước khi chọn compiler mode.

Kết quả mong muốn là mỗi expression có một hợp đồng rõ ràng: dùng để làm gì, nhận dữ liệu nào, được phép truy cập những gì, trả về kiểu nào, xử lý null và lỗi ra sao, được kiểm thử bằng trường hợp nào và có chi phí runtime như thế nào.

## 1. Vòng đời của một expression

Một expression thường đi qua các giai đoạn:

1. Xác định mục đích nghiệp vụ và nguồn dữ liệu.
2. Viết chuỗi SpEL hoặc template expression.
3. Cấu hình parser và ParserContext nếu cần.
4. Parse chuỗi thành Expression.
5. Chuẩn bị root object và EvaluationContext.
6. Đánh giá expression với dữ liệu runtime.
7. Chuyển đổi hoặc kiểm tra kiểu kết quả nếu cần.
8. Xử lý lỗi, ghi nhận thông tin vận hành và sử dụng kết quả.
9. Kiểm thử lại khi expression, model hoặc context thay đổi.

Parse và evaluate là hai giai đoạn khác nhau. Parse thành công chỉ xác nhận cú pháp có thể được phân tích; nó không bảo đảm các variable, bean, property hoặc method cần thiết đã tồn tại khi chạy.

Expression cố định nên được parse và kiểm tra dependency càng sớm càng tốt. Dữ liệu thay đổi theo request được cung cấp ở giai đoạn đánh giá. Cách tách này giúp phát hiện lỗi cấu hình trước khi chúng xuất hiện trong luồng xử lý thật.

## 2. Chọn cú pháp phù hợp với mục đích

SpEL hỗ trợ truy cập property, toán tử, gọi method, function, collection operation và nhiều cấu trúc khác. Hãy chọn biểu thức ngắn, thể hiện trực tiếp quy tắc cần thực hiện.

Ví dụ đọc property:

~~~text
customer.name
~~~

So sánh và logic:

~~~text
total >= #minimumTotal and active
~~~

Điều kiện:

~~~text
status == 'PAID' ? 'Complete' : 'Pending'
~~~

Truy cập phần tử:

~~~text
#orders[0].id
~~~

Selection và projection:

~~~text
#orders.?[total >= #minimumTotal].![id]
~~~

Cú pháp nên phản ánh đúng nguồn dữ liệu. Property không có tiền tố # được đọc từ evaluation object hiện tại; variable có tiền tố # được tra cứu trong EvaluationContext; bean reference dùng @. Trong collection operation, #this có thể đại diện phần tử hiện tại còn #root giữ root object ban đầu.

Nếu biểu thức quá dài, lồng nhiều điều kiện hoặc gọi nhiều method có tác dụng phụ, hãy chuyển phần logic phức tạp sang Java và chỉ truyền kết quả hoặc đầu vào cần thiết vào SpEL.

## 3. Parse expression và tái sử dụng Expression

Ví dụ cơ bản:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimumTotal");
~~~

Expression có thể được tái sử dụng cho nhiều lần đánh giá:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable(
    "minimumTotal",
    new BigDecimal("100.00")
);

Boolean accepted =
    expression.getValue(context, orderView, Boolean.class);
~~~

Nếu cùng một chuỗi được dùng nhiều lần, parse một lần thường hợp lý hơn parse lại trong từng request. Context có thể được tạo riêng cho từng lần xử lý để cung cấp root object và variables phù hợp.

Không chia sẻ một EvaluationContext mutable giữa các request không liên quan nếu các biến hoặc root object thay đổi. Expression được tái sử dụng và context được cô lập là một cách tổ chức dễ kiểm soát.

Với expression được lưu trong cấu hình ngoài code, hãy gắn identifier và version để biết chính xác chuỗi nào đang chạy. Khi cập nhật, parse và kiểm tra nó trước khi đưa vào sử dụng.

## 4. ParserContext và template expression

Expression thuần coi toàn bộ chuỗi là cú pháp SpEL. Template expression cho phép trộn văn bản literal với đoạn SpEL.

Ví dụ:

~~~java
Expression message = parser.parseExpression(
    "Order #{#orderId} is now #{#status}.",
    new TemplateParserContext()
);
~~~

Với delimiter mặc định, đoạn nằm giữa `#{` và `}` được đánh giá; phần còn lại được giữ nguyên. Có thể dùng TemplateParserContext với prefix/suffix tùy chỉnh khi delimiter mặc định dễ xung đột với nội dung.

ParserContext chỉ quyết định cách parser phân tách chuỗi. Nó không đăng ký variables, bean, function hoặc quyền truy cập. Những dependency đó thuộc EvaluationContext.

Trong cấu hình Spring, cần phân biệt placeholder cấu hình và SpEL: placeholder dùng cú pháp `${...}` để lấy giá trị từ property source; SpEL dùng `#{...}` để đánh giá biểu thức. Hai cơ chế có thể được kết hợp trong những vị trí cấu hình Spring hỗ trợ.

## 5. Xác định root object

Root object là đối tượng bắt đầu cho các property không có tiền tố #. Nếu expression dùng:

~~~text
total >= #minimumTotal and customer.active
~~~

thì total và customer phải có trên root object hoặc được xử lý bởi PropertyAccessor tương ứng.

Hồ sơ expression nên ghi:

- Kiểu Java cụ thể của root object.
- Những property được đọc.
- Kiểu dữ liệu và nullability của từng property.
- Các property lồng nhau và điều kiện tồn tại.
- Nguồn tạo root object.
- Root object có mutable hay không.
- Root object có chứa dữ liệu nhạy cảm hoặc object có quyền rộng không.

Ưu tiên DTO hoặc view chuyên biệt chỉ chứa dữ liệu cần thiết. Nếu expression chỉ cần total, status và customerActive, không cần truyền toàn bộ entity cùng các quan hệ tới repository, credential hoặc service.

Root object nhỏ giúp expression dễ hiểu, test dễ viết và giới hạn dữ liệu mà expression có thể tiếp cận.

## 6. Khai báo variables rõ ràng

Variable được đăng ký trong EvaluationContext và tham chiếu bằng dấu #:

~~~java
context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("currentUserId", "U-1024");
context.setVariable("featureEnabled", true);
~~~

Với từng variable, ghi:

| Thuộc tính | Nội dung |
|---|---|
| Name | Tên sau dấu # |
| Java type | Kiểu cụ thể được đăng ký |
| Required | Có bắt buộc phải cung cấp không |
| Nullable | Có thể nhận null không |
| Source | Thành phần Java cung cấp giá trị |
| Constraints | Miền giá trị hoặc định dạng |
| Lifecycle | Thời điểm tạo và cập nhật |
| Purpose | Ý nghĩa trong quy tắc |

Không chỉ ghi variable là "number" hoặc "user". Ví dụ minimumTotal nên được mô tả là BigDecimal, bắt buộc, không null và lấy từ chính sách giá.

Phân biệt variable chưa được đăng ký với variable đã đăng ký nhưng có giá trị null. Nếu variable bắt buộc, hãy xác thực trước khi evaluate. Nếu variable tùy chọn, ghi rõ expression xử lý bằng điều kiện null, safe navigation hoặc Elvis như thế nào.

## 7. Phân biệt root property, variable và bean

Ba cú pháp có ý nghĩa khác nhau:

| Cú pháp | Nguồn |
|---|---|
| `name` | Property của evaluation object hiện tại |
| `#name` | Variable trong EvaluationContext |
| `@name` | Bean được phân giải qua BeanResolver |
| `#root.name` | Property name của root object ban đầu |
| `#this.name` | Property name của evaluation object hiện tại |

Nếu root object có property name và context cũng có variable name, `name` và `#name` vẫn đọc hai nguồn khác nhau.

Bean reference cần BeanResolver. Trong context được tạo thủ công, ứng dụng có thể kết nối BeanFactory bằng BeanFactoryResolver:

~~~java
context.setBeanResolver(
    new BeanFactoryResolver(beanFactory)
);
~~~

Hãy ghi bean name hoặc alias, kiểu bean, method được gọi, scope/lifecycle, side effect và quyền cần thiết. Không cung cấp cả container nếu expression chỉ cần một giá trị đã được service tính sẵn.

## 8. Ghi nhận functions và method invocation

Function là Method Java được đăng ký trong EvaluationContext và gọi bằng cú pháp `#functionName(arguments)`.

~~~java
Method method =
    TextFunctions.class.getMethod("normalize", String.class);

context.registerFunction("normalize", method);
~~~

Method invocation trên object có cú pháp khác:

~~~text
#customer.getDisplayName()
~~~

Bean method được gọi qua bean reference:

~~~text
@pricingService.calculate(#order)
~~~

Hồ sơ nên ghi riêng từng loại: function name và Method signature; target object và instance method; bean name và method được gọi. Với mỗi method, ghi kiểu đối số, kiểu trả về, null handling, exception, side effect và khả năng bị gọi lặp.

Ưu tiên function thuần, có kết quả xác định và không thay đổi trạng thái. Nếu logic cần dependency, transaction hoặc truy cập hệ thống ngoài, giữ nó trong service Java và chỉ cung cấp dữ liệu cần thiết cho expression.

## 9. Chọn EvaluationContext theo quyền tối thiểu

EvaluationContext quyết định cách SpEL đọc property, gọi method, tìm bean, chuyển đổi kiểu và sử dụng function. Hai lựa chọn thường gặp:

- StandardEvaluationContext: linh hoạt, hỗ trợ nhiều resolver và tính năng SpEL.
- SimpleEvaluationContext: giới hạn tập tính năng và cho phép chọn cách truy cập property/method phù hợp.

Với biểu thức chỉ đọc dữ liệu:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();
~~~

Nếu cần read-write data binding hoặc instance method invocation, chỉ bật đúng khả năng cần thiết. Không đổi sang context rộng chỉ để expression chạy qua một lỗi mà chưa hiểu dependency.

Hãy ghi rõ loại context, PropertyAccessor, MethodResolver, BeanResolver, TypeConverter và function đã đăng ký. Các khả năng không dùng cũng nên được ghi là "Không dùng" để tránh hiểu nhầm rằng chúng đã được xem xét nhưng bị bỏ sót.

## 10. Property access và quyền ghi

PropertyAccessor kiểm soát việc đọc và ghi property. Quyền đọc không đồng nghĩa quyền ghi.

Nếu expression chỉ phục vụ tính toán hoặc hiển thị, dùng context read-only. Nếu cần ghi, hãy xác định rõ property được phép thay đổi và dùng accessor allowlist khi cần giới hạn theo từng trường.

Với custom PropertyAccessor, tài liệu nên nêu target type, property được đọc, property được ghi, kiểu giá trị chấp nhận và hành vi khi property không được phép. Cần kiểm soát cả đường dẫn lồng nhau và accessor fallback.

Không coi setter public là bằng chứng rằng expression được cấp quyền ghi. Các thay đổi nghiệp vụ nhạy cảm như role, balance hoặc ownership nên đi qua service Java có authorization và validation rõ ràng.

## 11. Type conversion và validation

SpEL sử dụng TypeConverter của EvaluationContext khi một thao tác cần kiểu đích khác với kiểu nguồn. StandardTypeConverter có thể kết nối với Spring ConversionService.

Ví dụ, một chuỗi có thể chuyển thành Integer nếu converter hỗ trợ. Tuy nhiên, chuyển đổi thành công không chứng minh giá trị hợp lệ. Số 500 có thể là Integer hợp lệ nhưng vượt giới hạn nghiệp vụ.

Phân biệt:

- Conversion: thay đổi kiểu hoặc cách biểu diễn.
- Validation: kiểm tra cấu trúc, miền giá trị, quan hệ giữa trường và quy tắc nghiệp vụ.
- Authorization: xác định người gọi có được thực hiện hành động hay không.

Ghi rõ converter, ConversionService, cặp kiểu được hỗ trợ, format, locale, timezone và cách xử lý null/chuỗi rỗng. Validation và authorization cần được thực hiện ở tầng phù hợp, không giao toàn bộ trách nhiệm cho expression.

## 12. Collection operation và kiểu dữ liệu

SpEL hỗ trợ selection, projection và first/last selection:

~~~text
#orders.?[total >= #minimumTotal]
#orders.![id]
#orders.^[status == 'PAID']
#orders.$[status == 'PAID']
~~~

Hồ sơ cần mô tả kiểu collection, kiểu phần tử, thứ tự, nullability và kết quả khi không có phần tử phù hợp.

Selection thường trả về collection rỗng khi không có phần tử khớp. Projection tạo kết quả tương ứng với các phần tử nguồn và không tự lọc. First/last selection trả về null nếu không tìm thấy phần tử.

Phân biệt collection rỗng với null. Collection rỗng là object hợp lệ không có phần tử; null là không có tham chiếu collection. Nếu hai trạng thái có cùng ý nghĩa nghiệp vụ, chuẩn hóa trước khi evaluate. Nếu khác nhau, giữ chúng riêng và kiểm thử riêng.

Trong collection operation, #this có thể là phần tử đang xét; #root vẫn là root object ban đầu. Ghi rõ nguồn dữ liệu của từng property để tránh đọc nhầm giữa phần tử và root.

## 13. Nullability và biểu thức an toàn

Các object trung gian có thể null. Ví dụ:

~~~text
#customer?.address?.city ?: 'Not provided'
~~~

Safe navigation bảo vệ việc truy cập trên tham chiếu null; Elvis cung cấp giá trị thay thế khi vế trái phù hợp với quy tắc của toán tử.

Không dùng fallback để che giấu dữ liệu bắt buộc bị thiếu. Nếu customer là bắt buộc, hãy xác thực trước khi evaluate hoặc báo lỗi nghiệp vụ rõ ràng.

Ghi nullability của root object, variables, property lồng nhau, collection và phần tử. Test cả null được phép lẫn null phải bị từ chối. Với collection, kiểm tra riêng null, empty, no-match và có kết quả.

## 14. Kiểu kết quả và hợp đồng đầu ra

Mỗi expression nên có kiểu kết quả mong đợi:

- Boolean cho điều kiện.
- String cho message hoặc nhãn.
- BigDecimal cho phép tính tiền.
- Collection cho selection/projection.
- DTO hoặc object cụ thể nếu cần cấu trúc dữ liệu.

Ghi rõ kết quả có thể null không, có yêu cầu conversion đầu ra không, collection có kiểu phần tử nào và giá trị được dùng ở đâu.

Ví dụ:

~~~java
Boolean eligible =
    expression.getValue(context, orderView, Boolean.class);
~~~

Yêu cầu kiểu đích giúp người gọi thể hiện hợp đồng đầu ra. Nếu kết quả được dùng cho tiền, ghi rõ currency, scale và quy tắc làm tròn ở tầng nghiệp vụ.

Không giả định kết quả có kiểu mong muốn chỉ vì một lần chạy thử trả về giá trị đúng. Kiểm thử các nhánh có thể trả về kiểu khác nhau.

## 15. Phân loại lỗi theo giai đoạn

Các lỗi cần được tách theo giai đoạn:

| Giai đoạn | Ví dụ |
|---|---|
| Parse | Sai cú pháp, delimiter thiếu, ParserContext sai |
| Context setup | Thiếu variable, resolver hoặc function |
| Property/method access | Property không tồn tại, method không được phép |
| Conversion | Không chuyển được giá trị sang kiểu đích |
| Runtime data | Root hoặc property trung gian null, index ngoài phạm vi |
| Business validation | Giá trị có kiểu đúng nhưng ngoài giới hạn |
| Authorization | Người gọi không có quyền thực hiện hành động |

ParseException/SpelParseException thường liên quan đến phân tích cú pháp. EvaluationException/SpelEvaluationException liên quan đến đánh giá. Method hoặc getter được gọi cũng có thể ném exception riêng; hãy giữ cause chain để xác định nguồn gốc.

Expression cố định nên được parse và kiểm tra dependency khi khởi động. Dữ liệu request được xác thực ở runtime. Không bắt mọi exception rồi trả về null hoặc giá trị mặc định tùy tiện vì có thể che giấu lỗi cấu hình.

## 16. Xây dựng bộ kiểm thử chức năng

Mỗi expression cần test cho:

- Giá trị bình thường.
- Mỗi nhánh điều kiện.
- Giá trị đúng tại biên và ngay ngoài biên.
- Variable thiếu hoặc null.
- Root object null nếu có thể.
- Property lồng nhau null.
- Collection null, empty, no-match và có kết quả.
- Kiểu dữ liệu không tương thích.
- Function hoặc method ném exception.
- Kiểu kết quả và nội dung trả về.

JUnit 5 có thể dùng parameterized test để chạy cùng một expression với nhiều bộ dữ liệu:

~~~java
@ParameterizedTest
@CsvSource({
    "true, PAID",
    "false, PENDING"
})
void mapsPaymentState(boolean paid, String expected) {
    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    context.setVariable("paid", paid);

    Expression expression =
        new SpelExpressionParser().parseExpression(
            "#paid ? 'PAID' : 'PENDING'"
        );

    assertEquals(
        expected,
        expression.getValue(context, String.class)
    );
}
~~~

Test phải xác nhận cả kết quả lẫn kiểu khi kiểu là một phần của hợp đồng. Với first/last selection, kiểm soát thứ tự collection. Với projection, kiểm tra từng phần tử kết quả thay vì chỉ kiểm tra collection không null.

## 17. Positive tests và negative tests cho quyền truy cập

Positive tests xác nhận thao tác cần thiết được phép: đọc property, sử dụng variable, gọi function hoặc truy cập bean đã được duyệt.

Negative tests xác nhận thao tác ngoài nhu cầu bị từ chối:

- Ghi property trong context chỉ đọc.
- Đọc property không nằm trong allowlist.
- Gọi method không được bật.
- Tham chiếu bean không được cung cấp.
- Gọi function chưa đăng ký.
- Dùng type reference hoặc constructor ngoài phạm vi.

Sau khi thao tác bị từ chối, kiểm tra object không bị thay đổi. Không chỉ assert rằng có exception; cần xác nhận trạng thái vẫn nguyên vẹn.

Khi thu hẹp context, chạy cùng bộ test trên cấu hình cũ và cấu hình mới. Hành vi được chấp thuận phải giữ nguyên; capability dư thừa phải bị loại bỏ.

## 18. Bảo vệ expression và dữ liệu đầu vào

Expression là mã có thể thực thi. Nếu người dùng hoặc nguồn bên ngoài có thể sửa expression, hãy xem quyền chỉnh sửa template như quyền thay đổi logic.

Nguyên tắc:

1. Không nối trực tiếp dữ liệu người dùng vào expression source.
2. Truyền dữ liệu qua variables có kiểu rõ ràng.
3. Dùng root DTO nhỏ, không chứa service hoặc bí mật.
4. Ưu tiên context chỉ đọc và giới hạn accessor.
5. Không cung cấp BeanResolver nếu không cần bean reference.
6. Chỉ đăng ký function đã duyệt.
7. Giới hạn method invocation, type reference và constructor invocation.
8. Kiểm tra độ dài và nguồn gốc expression.
9. Encode output theo ngữ cảnh HTML, attribute, URL hoặc email.
10. Ghi log identifier/version và lỗi đã làm sạch, không ghi token hoặc toàn bộ object nhạy cảm.

ParserContext không phải sandbox. Việc parse thành công cũng không chứng minh expression an toàn. Ranh giới thực tế nằm ở dữ liệu được cung cấp, resolver/accessor và quyền của các object mà expression có thể truy cập.

## 19. Quản lý template và thay đổi dependency

Khi expression thay đổi, dependency có thể thay đổi theo. Thêm `#discountRate` tạo variable dependency; thêm `@pricingService.calculate(...)` tạo bean dependency; thêm function hoặc method tạo thêm yêu cầu về quyền và kiểu dữ liệu.

Với expression lưu ngoài code, quản lý:

- Identifier và version.
- Source expression hoặc template.
- ParserContext và parser configuration.
- Root object type và property paths.
- Variable names, Java types và nullability.
- Bean names, aliases và method signatures.
- Function signatures.
- Accessor, resolver và converter.
- Result type và lỗi dự kiến.
- Positive/negative tests.
- Người hoặc quy trình được phép thay đổi expression.

Khi cập nhật, kiểm tra expression với context dự kiến trước khi phát hành. Không sửa chuỗi mà quên cập nhật code tạo context; cũng không thêm capability toàn cục chỉ để hỗ trợ một expression riêng.

## 20. Đo hiệu năng trước khi bật compiler

SpEL có interpreted mode và compiler mode. Compiler có thể giúp expression được đánh giá lặp lại với kiểu dữ liệu ổn định, nhưng không bảo đảm mọi expression đều nhanh hơn.

Ba chế độ thường gặp:

| Mode | Hành vi |
|---|---|
| OFF | Chỉ interpreted |
| IMMEDIATE | Ưu tiên compiled execution khi có thể |
| MIXED | Có thể quay lại interpreted khi compiled expression không còn phù hợp trong các trường hợp được hỗ trợ |

Đo riêng parse, evaluate, warm-up/compile và context setup. Nếu production parse một lần nhưng benchmark parse ở mỗi vòng lặp, phép đo không phản ánh đúng workload.

Dùng expression và kiểu dữ liệu đại diện. Kiểm tra root object, variable, null, implementation khác nhau và collection size. Một microbenchmark trên biểu thức số học đơn giản không đại diện cho toàn bộ ứng dụng.

## 21. Benchmark và chỉ số vận hành

JMH phù hợp hơn một vòng lặp tự viết dùng System.nanoTime() cho microbenchmark. Tách setup khỏi method đo nếu production cũng tái sử dụng Expression:

~~~java
@State(Scope.Thread)
public class SpelBenchmark {

    private Expression expression;
    private StandardEvaluationContext context;

    @Setup(Level.Trial)
    public void setup() {
        ExpressionParser parser = new SpelExpressionParser();
        expression = parser.parseExpression(
            "#order.total >= #minimum"
        );

        context = new StandardEvaluationContext();
        context.setVariable("order", createOrder());
        context.setVariable("minimum", new BigDecimal("100.00"));
    }

    @Benchmark
    public Boolean evaluate() {
        return expression.getValue(context, Boolean.class);
    }
}
~~~

So sánh OFF, IMMEDIATE và MIXED với cùng expression, dữ liệu, warm-up, measurement và fork. Theo dõi throughput, average, p50, p95, p99, allocation rate, GC, CPU, startup time và error rate.

Đo cả microbenchmark và end-to-end. Nếu expression gọi database hoặc service mạng, thời gian bên ngoài có thể lấn át chi phí SpEL. Tách overhead của expression khỏi chi phí service để biết compiler thực sự cải thiện phần nào.

## 22. Điều kiện để chọn compiler mode

Trước khi bật compiler, xác định:

- Expression được gọi đủ thường xuyên để thu hồi chi phí compile không.
- Cấu trúc AST có được compiler hỗ trợ không.
- Kiểu root object và variables có ổn định không.
- Compiled execution có giữ kết quả tương đương interpreted không.
- Latency đuôi, allocation và GC có thay đổi bất lợi không.
- ClassLoader có phù hợp với kiểu được truy cập không.
- Có thể quay lại OFF khi có lỗi hoặc lợi ích biến mất không.

OFF là baseline. Chỉ chọn IMMEDIATE hoặc MIXED khi benchmark và test chức năng xác nhận lợi ích. MIXED không phải cơ chế xử lý mọi exception; lỗi nghiệp vụ hoặc exception trong getter/service vẫn cần xử lý theo hợp đồng.

Triển khai có kiểm soát ở staging hoặc canary, theo dõi đủ workload đại diện và giữ khả năng rollback.

## 23. Ví dụ hồ sơ expression tích hợp

Một bản ghi ngắn có thể được tổ chức như sau:

~~~text
Expression ID: order-eligibility-v1
Purpose: Kiểm tra đơn hàng đạt ngưỡng tối thiểu

Source:
  total >= #minimumTotal and active

Parser:
  Type: SpelExpressionParser
  ParserContext: Expression thuần
  CompilerMode: OFF

Root:
  Type: OrderView
  total: BigDecimal, required, non-null
  active: boolean

Variables:
  minimumTotal:
    Type: BigDecimal
    Required: Yes
    Nullable: No
    Source: PricingPolicy

Beans: None
Functions: None
Method invocation: Not required
Property access: Read-only data binding
BeanResolver: Not configured
Custom TypeConverter: None

Result:
  Type: Boolean
  Nullable: No

Errors:
  Invalid expression syntax
  Missing minimumTotal
  Incompatible total type

Tests:
  Below threshold
  Equal to threshold
  Above threshold
  Missing variable
  Null root
  Access denied for writes

Security:
  Root is a read-only view
  No bean or side-effecting method exposed

Performance:
  Parse once
  Evaluate per request
  Compiler mode selected after benchmark
~~~

Đây là mẫu minh họa. Khi áp dụng, thay toàn bộ kiểu, tên và điều kiện bằng dữ liệu thật của ứng dụng. Những capability không dùng cần được ghi rõ là None hoặc Not required.

## 24. Checklist trước khi đưa expression vào production

**Cú pháp và parser**

- Expression có mục đích và identifier rõ ràng.
- ParserContext đúng với expression thuần hoặc template.
- Expression được parse trước khi sử dụng nếu source cố định.
- Parser configuration và compiler mode được ghi nhận.

**Dữ liệu và context**

- Root object có kiểu cụ thể và phạm vi nhỏ.
- Variables có kiểu, nguồn, required và nullable rõ ràng.
- Bean/function chỉ được cung cấp khi cần.
- Accessor và resolver phù hợp với quyền yêu cầu.
- Context mutable không bị chia sẻ sai phạm vi.

**Kết quả và lỗi**

- Result type và nullability được xác định.
- Conversion tách khỏi validation.
- Parse error và evaluation error được phân loại.
- Cause chain được giữ lại.
- Log không chứa bí mật hoặc dữ liệu nhạy cảm.

**Kiểm thử và bảo mật**

- Cả hai nhánh điều kiện được kiểm thử.
- Null, empty, no-match và boundary được kiểm thử.
- Positive và negative permission tests tồn tại.
- Expression từ nguồn ngoài được xem như mã có thể thực thi.
- Output được encode theo ngữ cảnh.

**Hiệu năng và vận hành**

- Parse, evaluate và context setup được đo riêng.
- Benchmark dùng workload thực tế và warm-up phù hợp.
- Throughput, latency distribution, allocation, GC và error rate được theo dõi.
- Compiler chỉ được bật sau khi lợi ích được xác nhận.
- Có kế hoạch canary và rollback.

## 25. Ghi nhớ

Một SpEL expression không chỉ là chuỗi cú pháp. Nó là một thành phần chạy trong một hợp đồng gồm parser, root object, variables, beans, functions, accessors, resolvers, converter, kiểu kết quả và dữ liệu runtime.

Hãy ghi rõ dependency và quyền truy cập; dùng root DTO nhỏ và context có quyền tối thiểu; tách parse khỏi evaluate, conversion khỏi validation và lỗi cấu hình khỏi lỗi dữ liệu; kiểm thử cả nhánh hợp lệ lẫn thao tác bị từ chối; và chỉ tối ưu compiler dựa trên benchmark đại diện.

Expression nên tập trung vào quy tắc ngắn, dễ đọc và có thể kiểm thử. Logic nghiệp vụ phức tạp, authorization và thao tác có side effect nên được đặt trong Java service có hợp đồng rõ ràng. Duy trì hồ sơ, test và số liệu hiệu năng cùng nhau để mỗi thay đổi expression đều có thể được đánh giá và vận hành có kiểm soát.

## Tài liệu tham khảo

- [Spring Framework Reference — Spring Expression Language](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [SpelParserConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParserConfiguration.html)
- [JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh)
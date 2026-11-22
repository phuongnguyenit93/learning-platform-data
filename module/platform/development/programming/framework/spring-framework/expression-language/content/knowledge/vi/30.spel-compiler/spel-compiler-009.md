# Kiểm thử tương đương giữa interpreted và compiled expression trong SpEL

Spring Expression Language (SpEL) có thể đánh giá expression theo hai cách: interpreted, trong đó engine phân tích và thực thi cấu trúc expression ở runtime, và compiled, trong đó SpEL tạo bytecode để thực thi nhanh hơn cho những expression được hỗ trợ. Compiler có thể cải thiện hiệu năng khi một expression được đánh giá lặp lại nhiều lần, nhưng việc bật compiler không tự bảo đảm mọi expression đều được biên dịch hoặc hai đường thực thi luôn phù hợp với mọi kiểu dữ liệu động.

Kiểm thử tương đương nhằm xác nhận cùng một expression, cùng dữ liệu đầu vào và cùng ngữ cảnh nghiệp vụ cho kết quả tương đương khi chạy ở chế độ interpreted và compiled. Việc này đặc biệt quan trọng khi expression phụ thuộc vào kiểu runtime, property lồng nhau, method invocation, collection hoặc object có trạng thái thay đổi.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Phân biệt interpreted evaluation với compiled evaluation.
- Cấu hình SpEL compiler bằng SpelParserConfiguration và SpelCompilerMode.
- Hiểu các chế độ OFF, IMMEDIATE và MIXED.
- Nhận biết expression nào có thể được compiler hỗ trợ và trường hợp nào tiếp tục interpreted.
- Thiết kế test chạy cùng expression trên dữ liệu giống nhau ở nhiều chế độ.
- So sánh giá trị, kiểu kết quả, exception và hành vi nghiệp vụ.
- Kiểm thử với nhiều kiểu runtime và dữ liệu biên.
- Phát hiện khác biệt do type assumption, overload, null hoặc object mutable.
- Đo hiệu năng đúng cách mà không nhầm benchmark với kiểm thử tính đúng đắn.

Bạn nên biết cách tạo SpelExpressionParser, Expression, EvaluationContext và cách SpEL truy cập property, gọi method, xử lý collection và chuyển đổi kiểu.

## 2. Interpreted và compiled evaluation

Ở chế độ interpreted, SpEL thực thi expression thông qua engine đánh giá của nó. Đây là cách hoạt động linh hoạt, phù hợp với nhiều cấu trúc expression và dữ liệu có kiểu runtime thay đổi.

Ở chế độ compiled, SpEL có thể tạo bytecode cho các expression nằm trong tập cú pháp được hỗ trợ. Bytecode giúp giảm chi phí diễn giải lặp lại và có thể cải thiện throughput khi cùng expression được đánh giá nhiều lần.

Các điểm cần phân biệt:

| Đặc điểm | Interpreted | Compiled |
|---|---|---|
| Cách thực thi | Engine diễn giải expression | Bytecode được tạo cho expression được hỗ trợ |
| Tính linh hoạt kiểu runtime | Linh hoạt hơn với nhiều thay đổi kiểu | Có thể dựa trên kiểu đã quan sát khi đánh giá |
| Khả năng hỗ trợ cú pháp | Rộng hơn | Chỉ hỗ trợ một tập con |
| Hiệu năng | Có chi phí diễn giải mỗi lần | Có thể nhanh hơn khi chạy lặp lại |
| Trường hợp không biên dịch được | Vẫn có thể chạy interpreted | Có thể tiếp tục interpreted tùy chế độ và expression |

Compiler là một tối ưu hóa thực thi. Nó không thay đổi mục đích nghiệp vụ của expression và không thay thế việc kiểm thử logic.

## 3. Cấu hình SpEL compiler

Compiler được cấu hình thông qua SpelParserConfiguration. Có ba chế độ chính trong SpelCompilerMode:

- OFF: tắt compiler; expression được thực thi theo interpreted mode.
- IMMEDIATE: SpEL cố gắng biên dịch expression sớm sau khi đã có thông tin đánh giá cần thiết. Nếu đường compiled gặp lỗi do giả định kiểu không còn đúng, lỗi có thể được đưa ra cho caller.
- MIXED: SpEL có thể chuyển lại sang interpreted evaluation khi đường compiled gặp lỗi, giúp thích ứng tốt hơn với một số thay đổi kiểu runtime.

Ví dụ tạo parser ở chế độ OFF:

~~~java
SpelParserConfiguration offConfiguration =
    new SpelParserConfiguration(
        SpelCompilerMode.OFF,
        getClass().getClassLoader()
    );

ExpressionParser interpretedParser =
    new SpelExpressionParser(offConfiguration);
~~~

Ví dụ tạo parser ở chế độ IMMEDIATE:

~~~java
SpelParserConfiguration immediateConfiguration =
    new SpelParserConfiguration(
        SpelCompilerMode.IMMEDIATE,
        getClass().getClassLoader()
    );

ExpressionParser compiledParser =
    new SpelExpressionParser(immediateConfiguration);
~~~

Ví dụ chế độ MIXED:

~~~java
SpelParserConfiguration mixedConfiguration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        getClass().getClassLoader()
    );

ExpressionParser mixedParser =
    new SpelExpressionParser(mixedConfiguration);
~~~

Có thể dùng class loader của ứng dụng để compiler tạo và nạp class được sinh ra trong môi trường phù hợp. Trong ứng dụng có class loader tùy chỉnh, plugin hoặc module riêng, hãy cấu hình và kiểm thử với class loader thực tế.

Không nên bật compiler trên toàn ứng dụng chỉ vì một expression benchmark chạy nhanh hơn. Hãy đo trên workload thật và xác nhận tính tương đương trước khi triển khai.

## 4. Tạo hai parser để so sánh

Một cách kiểm thử rõ ràng là tạo parser riêng cho interpreted và compiled mode, sau đó parse cùng một source expression.

~~~java
String source = "#order.total * #taxRate";

ExpressionParser interpretedParser =
    new SpelExpressionParser(
        new SpelParserConfiguration(
            SpelCompilerMode.OFF,
            getClass().getClassLoader()
        )
    );

ExpressionParser compiledParser =
    new SpelExpressionParser(
        new SpelParserConfiguration(
            SpelCompilerMode.IMMEDIATE,
            getClass().getClassLoader()
        )
    );

Expression interpretedExpression =
    interpretedParser.parseExpression(source);

Expression compiledExpression =
    compiledParser.parseExpression(source);
~~~

Dùng cùng một source giúp loại bỏ khác biệt do vô tình viết hai expression không giống nhau. Không tái sử dụng Expression được parse bởi parser OFF để kết luận parser compiled hoạt động như mong muốn; mỗi parser nên parse source riêng theo cấu hình tương ứng.

Một test nên giữ nguyên:

- Source expression.
- Root object và các biến.
- EvaluationContext capabilities.
- TypeConverter và property/method accessors.
- Dữ liệu đầu vào.
- Trạng thái object trước mỗi lần evaluate.

## 5. So sánh kết quả với cùng input

Ví dụ expression tính tổng sau thuế:

~~~java
String source = "#subtotal * (1 + #taxRate)";

Expression interpreted =
    interpretedParser.parseExpression(source);

Expression compiled =
    compiledParser.parseExpression(source);

StandardEvaluationContext contextA =
    new StandardEvaluationContext();

contextA.setVariable("subtotal", new BigDecimal("100.00"));
contextA.setVariable("taxRate", new BigDecimal("0.10"));

StandardEvaluationContext contextB =
    new StandardEvaluationContext();

contextB.setVariable("subtotal", new BigDecimal("100.00"));
contextB.setVariable("taxRate", new BigDecimal("0.10"));

Object interpretedResult = interpreted.getValue(contextA);
Object compiledResult = compiled.getValue(contextB);
~~~

Hai context độc lập nhưng có cùng dữ liệu giúp tránh việc lần đánh giá đầu làm thay đổi biến hoặc object dùng cho lần đánh giá sau.

Với BigDecimal, không nên chỉ so sánh chuỗi hiển thị nếu scale có thể khác nhau. Hãy dùng quy tắc so sánh phù hợp với domain, ví dụ compareTo nếu nghiệp vụ quan tâm giá trị số mà không yêu cầu scale giống hệt.

Nếu kiểu kết quả là DTO hoặc collection, cần so sánh nội dung theo hợp đồng dữ liệu, không chỉ so sánh identity của object.

## 6. Kiểm tra kiểu kết quả, không chỉ giá trị hiển thị

Hai kết quả có thể in ra cùng một chuỗi nhưng khác kiểu runtime. Ví dụ Integer 10 và Long 10 đều có thể hiển thị là 10, nhưng code tiêu thụ có thể xử lý chúng khác nhau.

Một test tương đương nên kiểm tra:

- Kết quả có null hay không.
- Kiểu runtime có đúng hợp đồng không.
- Giá trị có bằng nhau theo quy tắc domain không.
- Collection có đúng số phần tử và thứ tự yêu cầu không.
- Map có đúng key và value không.
- Object lồng nhau có đúng property cần thiết không.

Ví dụ:

~~~java
assertThat(interpretedResult)
    .isInstanceOf(BigDecimal.class);

assertThat(compiledResult)
    .isInstanceOf(BigDecimal.class);

assertThat(((BigDecimal) interpretedResult)
    .compareTo((BigDecimal) compiledResult))
    .isZero();
~~~

Nếu ứng dụng yêu cầu chính xác scale, precision hoặc kiểu cụ thể, hãy assert những thuộc tính đó riêng. Đừng để phép so sánh quá rộng che giấu khác biệt mà downstream code phụ thuộc.

## 7. Kiểm thử expression có property và method

Compiler có thể hỗ trợ nhiều property/method expression phổ biến, nhưng khả năng biên dịch phụ thuộc cấu trúc expression và thông tin kiểu mà SpEL quan sát được.

Ví dụ:

~~~text
#customer.address.city
~~~

Hoặc:

~~~text
#priceCalculator.calculate(#order.total)
~~~

Hãy kiểm tra với object thực tế và context thực tế. Đặc biệt chú ý:

- Getter có trả kiểu ổn định không?
- Method có overload không?
- Method có trả kiểu khác nhau theo dữ liệu không?
- Proxy có làm thay đổi kiểu runtime hoặc đường gọi không?
- Có property accessor tùy chỉnh không?
- Method có side effect hoặc phụ thuộc trạng thái bên ngoài không?

Khi so sánh hai mode, method nên thuần và dữ liệu đầu vào phải độc lập. Nếu method ghi database hoặc tăng counter, việc chạy hai lần có thể tạo tác động kép và làm test không còn so sánh cùng điều kiện.

## 8. Kiểm thử thay đổi kiểu runtime

Một nguyên nhân quan trọng khiến interpreted và compiled có hành vi khác nhau là kiểu runtime thay đổi giữa các lần đánh giá.

Ví dụ một biến có lúc tham chiếu Customer, lúc khác tham chiếu một implementation khác hoặc null. Expression có thể được compiler tối ưu dựa trên kiểu đã quan sát trước đó.

Hãy tạo các trường hợp:

| Lần đánh giá | Kiểu/dữ liệu | Điều cần xác nhận |
|---|---|---|
| 1 | Object kiểu A | Kết quả đúng |
| 2 | Object kiểu A khác giá trị | Kết quả vẫn đúng |
| 3 | Object kiểu B có cùng hợp đồng cần dùng | Kiểm tra compiler xử lý kiểu mới |
| 4 | Giá trị null | Hành vi null đúng với expression |
| 5 | Object thiếu property/method cần thiết | Lỗi được xử lý nhất quán |
| 6 | Collection có kiểu phần tử khác | Kết quả hoặc lỗi đúng theo hợp đồng |

Nếu ứng dụng có dữ liệu đa hình, hãy kiểm thử mọi implementation thực sự xuất hiện trong production. Không chỉ test một object mẫu rồi suy luận rằng mọi subclass/proxy đều tương thích.

MIXED mode có thể quay lại interpreted khi compiled path thất bại, nhưng không nên xem điều đó là lý do bỏ qua test. Cần quan sát hành vi và exception mà caller thực sự nhận được.

## 9. Kiểm thử null và safe navigation

Null là trường hợp biên cần có trong test matrix. Ví dụ:

~~~text
#customer?.address?.city
~~~

Kiểm thử ít nhất:

- customer khác null và address khác null.
- customer null.
- customer khác null nhưng address null.
- address tồn tại nhưng city null.

Nếu collection được dùng với projection hoặc selection, hãy kiểm tra collection null, rỗng và có phần tử null. Compiler có thể không hỗ trợ mọi cấu trúc collection hoặc null-safe syntax ở mọi phiên bản Spring; nếu expression không được compile, nó có thể tiếp tục interpreted theo cấu hình và khả năng của engine.

Đừng kết luận compiled mode tương đương chỉ từ một trường hợp dữ liệu đầy đủ. Dữ liệu thiếu thường là nơi giả định kiểu và null behavior bộc lộ khác biệt.

## 10. Kiểm thử exception và lỗi runtime

Một bài test equivalence cần so sánh cả hành vi lỗi khi expression không thể đánh giá.

Các loại lỗi nên kiểm tra:

- Property hoặc method không tồn tại.
- Đối số không chuyển đổi được.
- Method ném exception.
- Receiver null ở vị trí không được bảo vệ.
- Type runtime thay đổi sau khi compiler đã có thông tin.
- Expression không được compiler hỗ trợ.
- Class loader không thể nạp class sinh ra hoặc kiểu liên quan.

Không bắt mọi exception rồi coi hai kết quả là tương đương. Hãy xác định loại lỗi nào được phép xuất hiện theo hợp đồng ứng dụng và loại lỗi nào cho thấy một khác biệt không chấp nhận được.

Có thể viết helper chạy expression và thu lại outcome gồm result hoặc exception type. Sau đó so sánh hai outcome theo chính sách test. Không so sánh message exception tuyệt đối nếu message phụ thuộc implementation hoặc phiên bản; ưu tiên exception class, nguyên nhân và hành vi ứng dụng quan sát được.

## 11. Kiểm thử expression không được compiler hỗ trợ

SpEL compiler chỉ hỗ trợ một tập con các cấu trúc expression. Khi expression không thể compile, việc đánh giá có thể tiếp tục bằng interpreted mode tùy cấu hình và trạng thái expression.

Do đó cần phân biệt:

1. Expression chạy đúng ở interpreted mode.
2. Expression có được compiler hỗ trợ hay không.
3. Expression thực sự được thực thi bằng bytecode hay vẫn interpreted.
4. Kết quả và lỗi của đường compiled có tương đương với đường interpreted không.

Một test chỉ gọi getValue thành công không chứng minh expression đã được compile. Nếu cần xác nhận compiled path được sử dụng, hãy dùng cơ chế quan sát/logging hoặc instrumentation phù hợp với phiên bản Spring của ứng dụng. Không suy luận trạng thái compiler chỉ từ việc parser được cấu hình IMMEDIATE hoặc MIXED.

Với expression không được hỗ trợ, hành vi fallback cần được ghi nhận rõ. Nếu hiệu năng là mục tiêu, hãy đo riêng những expression thực sự được compile.

## 12. Dùng cùng EvaluationContext hay context độc lập?

Về nguyên tắc, hai mode cần cùng dữ liệu và cùng cấu hình để so sánh công bằng. Có thể dùng hai context độc lập được tạo từ cùng factory để tránh side effect và biến mutable bị chia sẻ.

Ví dụ:

~~~java
StandardEvaluationContext newContext(Order order, BigDecimal rate) {
    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("order", order);
    context.setVariable("taxRate", rate);

    return context;
}
~~~

Sau đó tạo context riêng cho mỗi lần evaluate:

~~~java
Object interpretedResult =
    interpreted.getValue(newContext(orderCopyA, rate));

Object compiledResult =
    compiled.getValue(newContext(orderCopyB, rate));
~~~

orderCopyA và orderCopyB cần có cùng trạng thái dữ liệu. Nếu object không thể copy, hãy bảo đảm expression chỉ đọc và method được gọi không làm thay đổi object.

Không dùng chung context mutable giữa nhiều test song song nếu test có cập nhật variable hoặc property.

## 13. Kiểm tra tương đương với nhiều bộ dữ liệu

Một bộ dữ liệu duy nhất thường không đủ. Hãy tạo test cases đại diện cho:

- Giá trị bình thường.
- Giá trị biên như 0, số âm, số rất lớn.
- Giá trị null.
- Collection rỗng và collection lớn.
- Nhiều implementation của cùng interface.
- Kiểu số khác nhau như Integer, Long và BigDecimal.
- Chuỗi có định dạng hợp lệ và không hợp lệ.
- Object proxy nếu ứng dụng dùng AOP.
- Property lồng nhau có một tầng null.

Có thể dùng parameterized test để chạy cùng bộ dữ liệu trên hai parser mode. Với mỗi input, tạo context độc lập, evaluate và so sánh outcome.

Nếu expression có side effect, không nên chạy cùng một object lần lượt ở hai mode rồi so sánh kết quả. Hãy loại bỏ side effect khỏi expression hoặc chuẩn bị hai fixture tương đương độc lập.

## 14. Ví dụ cấu trúc test JUnit

Ví dụ sau minh họa cách tạo parser cho hai mode và so sánh kết quả của một expression thuần:

~~~java
class SpelCompilerEquivalenceTest {

    private ExpressionParser parser(SpelCompilerMode mode) {
        SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                mode,
                getClass().getClassLoader()
            );

        return new SpelExpressionParser(configuration);
    }

    @Test
    void interpretedAndCompiledReturnEquivalentValues() {
        String source = "#subtotal * (1 + #taxRate)";

        Expression interpreted =
            parser(SpelCompilerMode.OFF).parseExpression(source);

        Expression compiled =
            parser(SpelCompilerMode.IMMEDIATE).parseExpression(source);

        StandardEvaluationContext contextA =
            new StandardEvaluationContext();
        contextA.setVariable("subtotal", new BigDecimal("100.00"));
        contextA.setVariable("taxRate", new BigDecimal("0.10"));

        StandardEvaluationContext contextB =
            new StandardEvaluationContext();
        contextB.setVariable("subtotal", new BigDecimal("100.00"));
        contextB.setVariable("taxRate", new BigDecimal("0.10"));

        BigDecimal resultA =
            interpreted.getValue(contextA, BigDecimal.class);

        BigDecimal resultB =
            compiled.getValue(contextB, BigDecimal.class);

        assertThat(resultA.compareTo(resultB)).isZero();
    }
}
~~~

Đây là một mẫu test cho expression thuần. Trong test suite thực tế, hãy bổ sung nhiều input, kiểm tra kiểu kết quả, null, exception và các expression có cấu trúc được ứng dụng sử dụng. Nếu muốn so sánh MIXED, chạy thêm parser được cấu hình SpelCompilerMode.MIXED.

## 15. Đo hiệu năng riêng với kiểm thử tương đương

Tính đúng đắn và hiệu năng là hai mục tiêu khác nhau.

Kiểm thử tương đương trả lời: hai mode có cho kết quả và hành vi phù hợp không?

Benchmark trả lời: với workload cụ thể, compiled mode có nhanh hơn không?

Khi đo hiệu năng:

- Parse expression ngoài vùng đo nếu mục tiêu là đo evaluation.
- Warm up JVM và đường thực thi trước khi lấy số đo.
- Dùng nhiều vòng lặp và nhiều lần fork nếu dùng JMH.
- Tránh đo bằng một lần gọi duy nhất.
- Dùng dữ liệu đại diện cho production.
- Đo cả throughput và latency nếu phù hợp.
- Đo chi phí context creation riêng với chi phí evaluate.
- Kiểm tra expression có thực sự được compile hay không.
- Theo dõi allocation và GC nếu expression tạo nhiều object.
- So sánh cùng phiên bản JDK, Spring và class loader.

Không bật compiler chỉ dựa trên microbenchmark quá nhỏ. Nếu expression chỉ chạy một vài lần trong vòng đời ứng dụng, chi phí compilation có thể không mang lại lợi ích đáng kể.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Hai mode trả kết quả khác nhau | Kiểu runtime thay đổi hoặc compiled path dùng giả định kiểu | Kiểm thử nhiều kiểu và dữ liệu biên |
| Expression không được compile | Cấu trúc nằm ngoài tập cú pháp được hỗ trợ | Chấp nhận interpreted hoặc đơn giản hóa expression nếu hợp lý |
| IMMEDIATE ném lỗi khi kiểu thay đổi | Compiled expression không còn phù hợp với dữ liệu mới | Dùng kiểu ổn định hoặc cân nhắc MIXED nếu fallback phù hợp |
| MIXED chạy nhưng hiệu năng không ổn định | Expression liên tục chuyển giữa compiled và interpreted | Kiểm tra dữ liệu đa hình, type stability và log |
| Test thành công nhưng không biết đã compile chưa | getValue thành công không chứng minh bytecode đã được dùng | Dùng logging/instrumentation theo phiên bản |
| Kết quả so sánh không đáng tin | Hai lần evaluate dùng object/context đã bị thay đổi | Dùng fixture và context độc lập có cùng trạng thái |
| Exception khác nhau | Hai đường thực thi gặp lỗi ở các tầng khác nhau | So sánh exception type và hợp đồng ứng dụng |
| Compiled mode không nhanh hơn | Expression ít lặp, không được compile hoặc chi phí khác chi phối | Benchmark workload thật trước khi bật |
| Lỗi class loader | Class sinh ra hoặc kiểu liên quan không được nạp đúng | Kiểm tra class loader và môi trường triển khai |

## 17. Bài tập thực hành

1. Tạo parser OFF và IMMEDIATE; chạy cùng expression số học trên cùng bộ dữ liệu.
2. So sánh kiểu runtime và giá trị kết quả, không chỉ chuỗi hiển thị.
3. Thêm parser MIXED và chạy lại bộ test.
4. Kiểm thử expression đọc property lồng nhau và method invocation.
5. Thử biến có kiểu Integer, Long và BigDecimal.
6. Thử receiver null, property null và collection rỗng.
7. Tạo một expression không được compiler hỗ trợ và xác định nó tiếp tục interpreted như thế nào.
8. Thử thay đổi kiểu object giữa các lần evaluate để quan sát khác biệt giữa IMMEDIATE và MIXED.
9. Viết parameterized test với dữ liệu bình thường, biên và không hợp lệ.
10. Dùng JMH để benchmark một expression thuần được đánh giá nhiều lần.
11. Xác nhận benchmark không bao gồm parse hoặc context setup nếu đó không phải chi phí đang cần đo.
12. Chạy test với class loader thực tế của ứng dụng.

## 18. Checklist trước khi bật compiled mode

- [ ] Đã xác định expression nào được đánh giá đủ thường xuyên để có lợi ích không?
- [ ] Đã kiểm thử source giống hệt trên OFF và compiled mode chưa?
- [ ] Dữ liệu đầu vào và EvaluationContext có tương đương không?
- [ ] Đã kiểm tra kiểu runtime và kiểu kết quả chưa?
- [ ] Đã thử nhiều implementation, overload và proxy chưa?
- [ ] Đã kiểm thử null, collection rỗng và dữ liệu biên chưa?
- [ ] Đã so sánh exception và hành vi lỗi chưa?
- [ ] Đã biết expression có thực sự được compiler hỗ trợ không?
- [ ] Đã hiểu khác biệt fallback giữa IMMEDIATE và MIXED chưa?
- [ ] Expression có side effect khiến test chạy hai lần không an toàn không?
- [ ] Class loader production đã được kiểm tra chưa?
- [ ] Benchmark có warm-up và workload đại diện không?
- [ ] Kết quả benchmark có chứng minh lợi ích thực tế không?
- [ ] Có thể giữ OFF cho expression không phù hợp không?

## 19. Kết luận

Interpreted evaluation linh hoạt và hỗ trợ phạm vi expression rộng; compiled evaluation có thể cải thiện tốc độ cho tập expression được hỗ trợ khi được đánh giá lặp lại. SpelParserConfiguration cho phép chọn OFF, IMMEDIATE hoặc MIXED, nhưng cấu hình compiler không chứng minh một expression đã được compile. Hãy parse cùng source trên các mode, dùng context và dữ liệu tương đương, kiểm tra giá trị, kiểu, exception và các trường hợp thay đổi kiểu runtime. Chỉ quyết định bật compiler sau khi kiểm thử tính đúng đắn và benchmark trên workload thực tế của ứng dụng.
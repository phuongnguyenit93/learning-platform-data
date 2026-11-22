# Kiểm thử parser với expression hợp lệ và không hợp lệ

SpEL parser chuyển chuỗi biểu thức thành đối tượng Expression để ứng dụng có thể đánh giá sau đó. Kiểm thử parser cần xác nhận hai nhóm đầu vào: expression có cú pháp hợp lệ được parse thành công, còn expression sai cú pháp bị từ chối với lỗi parse phù hợp. Cần tách bước parse khỏi bước evaluate, vì một expression có thể đúng cú pháp nhưng vẫn thất bại khi chạy do thiếu property, kiểu dữ liệu không tương thích hoặc type không thể phân giải.

Một bộ kiểm thử tốt giúp phát hiện lỗi cấu hình ngay khi nạp rule, ghi nhận vị trí cú pháp sai và phân biệt lỗi do parser với lỗi do dữ liệu runtime. Nên kiểm thử cả expression thông thường và template expression nếu ứng dụng sử dụng ParserContext.

## 1. Parse và evaluate là hai giai đoạn riêng

SpEL thường được sử dụng theo trình tự:

1. ExpressionParser nhận chuỗi đầu vào.
2. parseExpression() phân tích cú pháp và tạo Expression.
3. Ứng dụng cung cấp EvaluationContext hoặc root object.
4. getValue() đánh giá expression và trả kết quả.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("total >= 100");

    Boolean accepted =
            expression.getValue(order, Boolean.class);

Lệnh parseExpression() kiểm tra cấu trúc cú pháp và tạo Expression. Nó chưa nhất thiết đọc property total hoặc xác minh toàn bộ dữ liệu runtime. Những thao tác đó xảy ra khi gọi getValue().

Vì vậy, không nên coi việc parse thành công là bằng chứng expression chắc chắn chạy thành công với mọi root object. Kiểm thử parser và kiểm thử evaluation cần có mục tiêu riêng.

## 2. Expression hợp lệ là gì?

Expression hợp lệ là chuỗi tuân theo cú pháp SpEL mà parser của phiên bản Spring đang sử dụng chấp nhận.

Một số ví dụ:

    1 + 2

    'Spring Framework'

    total >= 100

    #minimumTotal > 0

    customer.active and customer.score >= 80

    T(java.lang.Math).max(10, 20)

Các biểu thức trên có thể được parse mà không cần cung cấp root object. Tuy nhiên, để đánh giá các biểu thức có property, biến hoặc type reference, ứng dụng cần context và dữ liệu phù hợp.

Có thể kiểm tra parse thành công bằng assertDoesNotThrow:

    ExpressionParser parser = new SpelExpressionParser();

    assertDoesNotThrow(
            () -> parser.parseExpression("1 + 2"));

Cách kiểm tra này phù hợp khi mục tiêu của test chỉ là xác nhận cú pháp. Nếu muốn kiểm tra cả kết quả, hãy gọi getValue() và assert giá trị trả về.

## 3. Expression không hợp lệ và SpelParseException

Khi chuỗi không tuân theo cú pháp SpEL, parser thường ném SpelParseException, một loại ParseException của Spring Expression.

Ví dụ các chuỗi sai cú pháp:

    total >

    customer.name(

    (1 + 2

    'unterminated

Những chuỗi này thiếu toán hạng, dấu ngoặc đóng hoặc dấu nháy kết thúc. Parser không thể tạo Expression hợp lệ nên quá trình parse thất bại.

Ví dụ kiểm thử:

    ExpressionParser parser = new SpelExpressionParser();

    assertThrows(
            SpelParseException.class,
            () -> parser.parseExpression("total >"));

Không nên chỉ kiểm tra rằng có bất kỳ RuntimeException nào bị ném. Kiểm tra SpelParseException giúp test thể hiện đúng hợp đồng: đầu vào sai cú pháp phải bị từ chối ở giai đoạn parse.

Thông báo lỗi có thể thay đổi giữa các phiên bản Spring. Tránh khóa test vào toàn bộ chuỗi message nếu không có yêu cầu cụ thể; nội dung thông báo và vị trí lỗi có thể khác theo phiên bản hoặc bản địa hóa.

## 4. Viết unit test cho expression hợp lệ bằng JUnit 5

JUnit 5 cung cấp assertDoesNotThrow để xác nhận parser chấp nhận đầu vào. Có thể viết một test đơn giản:

    import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

    import org.junit.jupiter.api.Test;
    import org.springframework.expression.ExpressionParser;
    import org.springframework.expression.spel.standard.SpelExpressionParser;

    class SpelParserTest {

        private final ExpressionParser parser =
                new SpelExpressionParser();

        @Test
        void parsesValidArithmeticExpression() {
            assertDoesNotThrow(
                    () -> parser.parseExpression("1 + 2"));
        }
    }

Test này chỉ kiểm tra cú pháp. Nếu muốn xác nhận expression còn trả về kết quả đúng:

    @Test
    void evaluatesValidArithmeticExpression() {
        Expression expression =
                parser.parseExpression("1 + 2");

        Integer result = expression.getValue(Integer.class);

        assertEquals(3, result);
    }

Hai test có mục đích khác nhau: test thứ nhất kiểm tra parser, test thứ hai kiểm tra cả parser và evaluator.

## 5. Dùng parameterized test cho nhiều expression hợp lệ

Khi có nhiều expression cần kiểm tra, JUnit 5 hỗ trợ @ParameterizedTest và @ValueSource. Nhờ vậy, một phương thức test có thể chạy với nhiều chuỗi đầu vào.

    import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

    import org.junit.jupiter.params.ParameterizedTest;
    import org.junit.jupiter.params.provider.ValueSource;

    class ValidSpelExpressionTest {

        private final ExpressionParser parser =
                new SpelExpressionParser();

        @ParameterizedTest
        @ValueSource(strings = {
                "1 + 2",
                "'Spring'",
                "total >= 100",
                "#minimumTotal > 0",
                "customer.active and customer.score >= 80"
        })
        void parsesValidExpressions(String source) {
            assertDoesNotThrow(
                    () -> parser.parseExpression(source));
        }
    }

Danh sách này nên đại diện cho cú pháp mà ứng dụng thực sự sử dụng: literal, toán tử số học, so sánh, biến, property path và logic boolean.

Nếu hệ thống dùng selection, projection, type reference hoặc function đã đăng ký, hãy thêm expression đại diện cho những tính năng đó. Việc parse không yêu cầu function phải tồn tại trong context, nhưng evaluation sẽ cần đăng ký đúng function.

Parameterized test cũng giúp thêm một trường hợp mới mà không phải tạo một test method riêng cho mỗi chuỗi.

## 6. Kiểm thử expression sai cú pháp bằng parameterized test

Có thể dùng @ValueSource để xác nhận parser từ chối nhiều đầu vào sai:

    import static org.junit.jupiter.api.Assertions.assertThrows;

    import org.junit.jupiter.params.ParameterizedTest;
    import org.junit.jupiter.params.provider.ValueSource;
    import org.springframework.expression.spel.SpelParseException;

    class InvalidSpelExpressionTest {

        private final ExpressionParser parser =
                new SpelExpressionParser();

        @ParameterizedTest
        @ValueSource(strings = {
                "total >",
                "customer.name(",
                "(1 + 2",
                "'unterminated"
        })
        void rejectsInvalidExpressions(String source) {
            assertThrows(
                    SpelParseException.class,
                    () -> parser.parseExpression(source));
        }
    }

Mỗi chuỗi phải đại diện cho một lỗi cú pháp rõ ràng. Tránh dùng một đầu vào mà parser có thể chấp nhận như một identifier hợp lệ chỉ vì người viết nghĩ rằng property đó không tồn tại.

Ví dụ unknownProperty thường vẫn là cú pháp hợp lệ. Parser không thể biết root object lúc chạy có property đó hay không. Đây là trường hợp cần kiểm tra ở evaluation test, không phải parser test.

## 7. Phân biệt lỗi parse với lỗi evaluate

Đây là điểm quan trọng nhất khi xây bộ test cho SpEL.

**Lỗi parse** xảy ra khi parser không thể tạo Expression từ chuỗi đầu vào. Lỗi thường thuộc SpelParseException.

**Lỗi evaluate** xảy ra sau khi Expression đã được tạo, khi SpEL thực thi biểu thức với root object, biến hoặc context cụ thể. Ví dụ property không tồn tại có thể gây SpelEvaluationException.

Ví dụ:

    Expression expression =
            parser.parseExpression("missingProperty");

    StandardEvaluationContext context =
            new StandardEvaluationContext(new Order());

    assertThrows(
            SpelEvaluationException.class,
            () -> expression.getValue(context));

Trong ví dụ, missingProperty là một property expression có cú pháp hợp lệ. Parser tạo được Expression; lỗi chỉ xuất hiện khi evaluator tìm property trên root object Order.

Một số tình huống khác cũng có thể chỉ lỗi lúc evaluate:

- Biến hoặc property trả về null rồi bị truy cập tiếp.
- Type reference có cú pháp đúng nhưng TypeLocator không tìm thấy lớp.
- Method tồn tại trong expression nhưng không có method resolver hoặc đối số phù hợp.
- Dữ liệu runtime không chuyển đổi được sang kiểu cần thiết.
- Function chưa được đăng ký hoặc function thực thi ném exception.

Hãy phân loại đúng lỗi để test chỉ ra giai đoạn cần sửa.

## 8. Kiểm thử parse và evaluate với một root object cụ thể

Có thể dùng một fixture đơn giản để kiểm tra expression đọc property và biến:

    class Order {
        private final BigDecimal total;

        Order(BigDecimal total) {
            this.total = total;
        }

        public BigDecimal getTotal() {
            return total;
        }
    }

Test:

    @Test
    void parsesAndEvaluatesOrderExpression() {
        Order order =
                new Order(new BigDecimal("150.00"));

        StandardEvaluationContext context =
                new StandardEvaluationContext(order);

        context.setVariable(
                "minimumTotal", new BigDecimal("100.00"));

        Expression expression =
                parser.parseExpression(
                        "total >= #minimumTotal");

        Boolean result =
                expression.getValue(context, Boolean.class);

        assertEquals(Boolean.TRUE, result);
    }

Test này kiểm tra nhiều phần cùng lúc: parser chấp nhận cú pháp, context cung cấp biến, root object có property total và evaluator trả kết quả boolean mong đợi.

Nên giữ fixture nhỏ để khi test lỗi có thể xác định nguyên nhân. Không cần dùng database hoặc khởi động toàn bộ Spring ApplicationContext cho một unit test parser đơn giản.

## 9. Kiểm tra thông tin Expression sau khi parse

Sau khi parse thành công, đối tượng Expression cung cấp thông tin về biểu thức đã nhận. Có thể kiểm tra chuỗi gốc qua getExpressionString():

    String source = "1 + 2";

    Expression expression =
            parser.parseExpression(source);

    assertEquals(
            source,
            expression.getExpressionString());

Có thể kiểm tra kết quả evaluate riêng:

    assertEquals(
            3,
            expression.getValue(Integer.class));

Không nên kiểm thử cấu trúc AST bằng reflection vào các lớp nội bộ của SpEL trừ khi đang viết integration test cho chính framework hoặc có lý do đặc biệt. Các lớp nội bộ có thể thay đổi giữa các phiên bản Spring. Với ứng dụng, hợp đồng cần kiểm tra thường là parse thành công/thất bại và kết quả đánh giá.

## 10. Kiểm thử template expression với ParserContext

Nếu ứng dụng dùng template expression, phải parse bằng ParserContext tương ứng. Cú pháp hợp lệ trong template mode có thể khác cách parser xử lý một expression độc lập.

Ví dụ:

    Expression expression =
            parser.parseExpression(
                    "Hello, #{#name}!",
                    ParserContext.TEMPLATE_EXPRESSION);

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("name", "An");

    String result =
            expression.getValue(context, String.class);

    assertEquals("Hello, An!", result);

Một template thiếu dấu đóng có thể gây lỗi parse:

    assertThrows(
            SpelParseException.class,
            () -> parser.parseExpression(
                    "Hello, #{#name",
                    ParserContext.TEMPLATE_EXPRESSION));

Khi kiểm thử template, luôn dùng đúng ParserContext giống lúc chạy production. Không parse template bằng overload mặc định rồi kết luận cú pháp template sai.

Nếu ứng dụng dùng TemplateParserContext với prefix/suffix tùy chỉnh, test phải dùng đúng cùng cặp delimiter đó.

## 11. Kiểm tra expression có type reference và function

Một expression có thể parse thành công dù kiểu hoặc function chưa sẵn sàng trong EvaluationContext.

Ví dụ type reference:

    Expression expression =
            parser.parseExpression(
                    "T(com.example.domain.Customer)");

Chuỗi có thể được parse về mặt cú pháp. Việc TypeLocator có tìm được lớp Customer hay không là vấn đề của evaluation.

Tương tự, function:

    Expression expression =
            parser.parseExpression(
                    "#normalizeCode(customer.code)");

Parser không xác minh rằng context đã đăng ký function normalizeCode. Khi đánh giá, context phải có Method tương ứng:

    context.registerFunction(
            "normalizeCode", normalizeMethod);

Vì vậy, nên có hai loại test:

- Parser test xác nhận cú pháp của type reference/function.
- Context integration test xác nhận lớp được phân giải và function được gọi thành công với dữ liệu thật.

Nếu chỉ có parser test, lỗi thiếu function hoặc sai TypeLocator vẫn có thể lọt tới runtime.

## 12. Kiểm thử với SpelParserConfiguration

Nếu ứng dụng dùng SpelParserConfiguration, hãy tạo parser trong test với cùng cấu hình quan trọng như production. Ví dụ:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.OFF,
                    getClass().getClassLoader());

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

    Expression expression =
            parser.parseExpression("total >= 100");

Với compiler mode IMMEDIATE hoặc MIXED, cần kiểm thử riêng hành vi đánh giá và các kiểu runtime thực tế. Một expression parse thành công không có nghĩa nó chắc chắn biên dịch được.

Khi mục tiêu chỉ là kiểm tra cú pháp, OFF thường giúp test tập trung vào parser và tránh trộn chi phí compilation vào test. Nếu production bật compiler, hãy có test riêng để xác nhận các expression quan trọng hoạt động với cấu hình đó.

Không nên phụ thuộc vào số lần gọi nội bộ để buộc MIXED biên dịch trong một unit test. Hãy xác nhận kết quả và hành vi quan sát được, không kiểm tra chi tiết triển khai không ổn định.

## 13. Tổ chức bộ test theo loại lỗi

Có thể tổ chức test thành các nhóm sau:

| Nhóm test | Điều cần xác nhận | Ví dụ lỗi |
|---|---|---|
| Parse hợp lệ | Expression được tạo thành công | Không có |
| Parse không hợp lệ | Parser ném SpelParseException | Thiếu ngoặc hoặc toán hạng |
| Evaluate hợp lệ | Expression trả kết quả đúng với context | So sánh property và biến |
| Evaluate không hợp lệ | Expression parse được nhưng runtime thất bại | Property không tồn tại |
| Context integration | Function, type và resolver được cấu hình đúng | Function chưa đăng ký |
| Template parsing | ParserContext và delimiter khớp | Thiếu suffix template |
| Compiler integration | Expression hoạt động với parser configuration | Kiểu runtime thay đổi |

Cách phân nhóm này giúp thông báo lỗi của test có ý nghĩa. Khi test thất bại, người phát triển biết cần sửa chuỗi expression, dữ liệu, context hay cấu hình parser.

## 14. Nạp và xác thực rule từ cấu hình

Nếu ứng dụng lưu expression trong file hoặc database, nên parse và xác thực cú pháp khi nạp rule thay vì đợi request đầu tiên sử dụng.

Ví dụ:

    Map<String, Expression> compiledRules =
            new HashMap<>();

    for (RuleDefinition rule : ruleDefinitions) {
        Expression expression =
                parser.parseExpression(rule.getExpression());

        compiledRules.put(rule.getId(), expression);
    }

Nếu một rule sai cú pháp, có thể báo lỗi kèm rule ID và dừng nạp cấu hình theo chính sách của ứng dụng. Với hệ thống yêu cầu khả dụng từng phần, có thể từ chối riêng rule lỗi và không đưa nó vào registry hoạt động.

Cần phân biệt parse/validation lúc khởi động với evaluate theo dữ liệu của từng request. Không phải mọi lỗi runtime đều có thể phát hiện khi nạp rule, vì root object và biến có thể chỉ tồn tại khi request đến.

Không log toàn bộ expression nếu nó có thể chứa secret hoặc dữ liệu nhạy cảm. Dùng rule ID, vị trí lỗi và thông tin cần thiết để chẩn đoán; giới hạn quyền đọc cấu hình gốc.

## 15. Kiểm thử expression không đáng tin cậy

Parser test không phải một cơ chế bảo mật. Một expression parse thành công vẫn có thể gọi method, đọc dữ liệu hoặc sử dụng capability mà EvaluationContext cung cấp.

Nếu expression do người dùng hoặc quản trị viên nhập:

- Giới hạn độ dài và số lượng expression được lưu.
- Chỉ chấp nhận người có quyền tạo hoặc sửa rule.
- Dùng EvaluationContext với capability tối thiểu, chẳng hạn SimpleEvaluationContext cho use case đọc property.
- Không đưa service, bean hoặc object có quyền rộng vào root/context nếu không cần.
- Kiểm thử cả expression hợp lệ bị từ chối khi vượt quyền.
- Giới hạn thời gian và tài nguyên của luồng đánh giá ở cấp ứng dụng nếu rule có thể tiêu tốn nhiều CPU.
- Ghi nhận lỗi theo rule ID và tránh lộ dữ liệu nội bộ.

Không nên đánh giá expression tùy ý chỉ vì parser không báo lỗi. Parse xác nhận cú pháp; quyền truy cập và tác động khi chạy phải được kiểm soát riêng.

## 16. Ví dụ bộ test tổng hợp

Một lớp test có thể kết hợp parse hợp lệ, parse sai cú pháp và evaluate sai property:

    class SpelParserTest {

        private final ExpressionParser parser =
                new SpelExpressionParser();

        @Test
        void acceptsValidExpression() {
            assertDoesNotThrow(
                    () -> parser.parseExpression("1 + 2"));
        }

        @Test
        void rejectsInvalidSyntax() {
            assertThrows(
                    SpelParseException.class,
                    () -> parser.parseExpression("total >"));
        }

        @Test
        void distinguishesEvaluationFailure() {
            Expression expression =
                    parser.parseExpression("missingProperty");

            StandardEvaluationContext context =
                    new StandardEvaluationContext(new Order());

            assertThrows(
                    SpelEvaluationException.class,
                    () -> expression.getValue(context));
        }
    }

Lớp test trên minh họa ba kết quả khác nhau:

- 1 + 2 có cú pháp hợp lệ.
- total > sai cú pháp nên bị parser từ chối.
- missingProperty có cú pháp hợp lệ nhưng không tồn tại trên root object, nên thất bại khi evaluate.

Trong project thực tế, bổ sung import, fixture Order và các test case nghiệp vụ cần thiết. Giữ parser test độc lập với Spring container nếu không cần dependency injection.

## 17. Những sai lầm thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
|---|---|---|
| Chỉ gọi parseExpression rồi cho rằng rule chạy được | Parse không xác minh toàn bộ dữ liệu runtime | Có evaluation test với context thật |
| Dùng RuntimeException cho mọi lỗi | Không phân biệt parse và evaluate | Kiểm tra SpelParseException và SpelEvaluationException |
| Xem unknownProperty là cú pháp sai | Identifier/property vẫn có cú pháp hợp lệ | Kiểm tra lỗi khi evaluate |
| Kiểm tra toàn bộ error message | Message có thể đổi theo phiên bản | Kiểm tra loại exception và thông tin ổn định |
| Parse template bằng overload mặc định | Parser không dùng delimiter template | Truyền đúng ParserContext |
| Chỉ test expression literal | Không bao phủ property, variable, function hoặc type | Dùng bộ expression đại diện cho rule production |
| Dùng Spring context đầy đủ cho mọi parser test | Test chậm và phụ thuộc môi trường | Dùng SpelExpressionParser trực tiếp khi đủ |
| Coi parse thành công là an toàn | Expression có thể thực thi capability khi evaluate | Giới hạn EvaluationContext và nguồn rule |

## Kết luận

Kiểm thử SpEL parser cần xác nhận expression hợp lệ được parse thành công và expression sai cú pháp bị từ chối bằng SpelParseException. Đồng thời, phải tách lỗi parse khỏi lỗi evaluate: một chuỗi như unknownProperty có thể parse bình thường nhưng thất bại khi evaluator tìm property trên root object.

Dùng JUnit 5 với assertDoesNotThrow, assertThrows và parameterized tests để kiểm tra nhiều trường hợp. Kiểm thử template bằng đúng ParserContext, kiểm tra function/type reference ở tầng context integration, và đánh giá các rule quan trọng với root object cùng dữ liệu thực tế. Parse thành công chỉ xác nhận cú pháp; EvaluationContext, quyền truy cập và hành vi runtime vẫn cần được kiểm soát và kiểm thử riêng.
# Chi phí parse expression và thời điểm tạo parser

Khi dùng Spring Expression Language (SpEL) trong đường xử lý thường xuyên, cần tách ba công việc có chi phí khác nhau: **tạo parser**, **parse chuỗi thành Expression** và **evaluate Expression**. Việc tạo một SpelExpressionParser không đồng nghĩa biểu thức đã được parse. Công việc phân tích cú pháp thực sự diễn ra khi gọi **parseExpression(...)**; còn việc đọc dữ liệu, tính toán và gọi thao tác cần thiết diễn ra khi gọi **getValue(...)** hoặc **setValue(...)**.

Nếu ứng dụng parse lại cùng một chuỗi trong mỗi request, nó lặp lại công việc tạo cấu trúc Expression dù cú pháp không thay đổi. Với expression cố định hoặc rule được cập nhật theo đợt, cách hiệu quả hơn thường là parse một lần tại thời điểm khởi tạo hoặc nạp cấu hình, sau đó tái sử dụng Expression cho nhiều lần đánh giá.

## Phân biệt ba loại chi phí

Một luồng sử dụng SpEL thường có các bước:

1. Tạo hoặc lấy một ExpressionParser đã được cấu hình.
2. Gọi parseExpression để chuyển chuỗi thành một Expression.
3. Chuẩn bị root object và EvaluationContext cho lần đánh giá.
4. Gọi getValue hoặc setValue để thực hiện biểu thức.

Ba chi phí đầu tiên không nên bị gộp thành một:

| Công việc | Thời điểm xảy ra | Nội dung chính |
|---|---|---|
| Tạo parser | Khi khởi tạo parser | Tạo đối tượng parser và gắn SpelParserConfiguration |
| Parse expression | Mỗi lần gọi parseExpression | Đọc cú pháp, tạo cấu trúc biểu thức và kiểm tra cú pháp |
| Evaluate expression | Mỗi lần gọi getValue/setValue | Truy cập dữ liệu, thực hiện toán tử, chuyển đổi kiểu và gọi thao tác cần thiết |

Parser có thể được tái sử dụng để parse nhiều chuỗi. Expression sau khi parse có thể được đánh giá nhiều lần với root object hoặc context khác nhau.

## Tạo parser một lần và tái sử dụng

Với cấu hình parser không thay đổi, thường nên tạo một SpelExpressionParser ở thời điểm khởi tạo ứng dụng hoặc component rồi dùng lại:

~~~java
public class PricingEvaluator {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    public Expression parse(String source) {
        return parser.parseExpression(source);
    }
}
~~~

Không cần tạo parser mới cho từng lần evaluate. Parser là thành phần dùng để phân tích chuỗi; nó không chứa dữ liệu riêng của từng request như root object hoặc biến nghiệp vụ.

Nếu ứng dụng cần compiler mode, auto-grow hoặc cấu hình parser khác, hãy tạo parser với SpelParserConfiguration tương ứng và giữ cấu hình đó ổn định trong vòng đời parser:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.OFF,
                MyApplication.class.getClassLoader());

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Một parser riêng cho mỗi bộ cấu hình giúp tránh nhầm lẫn giữa expression được parse theo chính sách khác nhau. Nếu ứng dụng có nhiều chế độ parsing, hãy quản lý chúng như các dependency riêng thay vì thay đổi cấu hình tùy tiện theo từng request.

## Parse expression một lần khi khởi tạo

Nếu biểu thức được biết trước trong mã nguồn, có thể parse ngay khi tạo component. Khi ứng dụng khởi động, lỗi cú pháp được phát hiện sớm thay vì chỉ xuất hiện khi một request hiếm gặp đi qua nhánh xử lý đó.

~~~java
public class OrderEvaluator {

    private final Expression eligibleExpression;

    public OrderEvaluator() {
        ExpressionParser parser =
                new SpelExpressionParser();

        this.eligibleExpression =
                parser.parseExpression(
                        "active and total >= #minimum");
    }

    public boolean isEligible(
            EvaluationContext context,
            Order order) {
        Boolean result = eligibleExpression.getValue(
                context,
                order,
                Boolean.class);

        return Boolean.TRUE.equals(result);
    }
}
~~~

Trong ví dụ, Expression được tạo một lần trong constructor. Mỗi lần gọi isEligible chỉ thực hiện evaluation với context và Order hiện tại. Không có thao tác parse lặp lại trong đường xử lý request.

Nếu expression sai cú pháp, component có thể không khởi tạo được. Đây thường là hành vi tốt đối với cấu hình tĩnh: ứng dụng phát hiện lỗi ngay khi khởi động thay vì âm thầm chạy với rule sai.

## Parse khi nạp cấu hình hoặc rule động

Không phải mọi expression đều được viết cố định trong source code. Một số ứng dụng lưu rule trong database, file cấu hình hoặc trang quản trị. Với các trường hợp đó, thời điểm phù hợp thường là lúc **nạp hoặc cập nhật rule**, không phải mỗi lần rule được áp dụng.

Một quy trình có thể gồm:

1. Đọc source của rule.
2. Kiểm tra độ dài và quyền sử dụng rule.
3. Parse source bằng parser có cấu hình đúng.
4. Nếu parse thất bại, từ chối bản cập nhật và giữ phiên bản rule đang hoạt động.
5. Nếu parse thành công, lưu hoặc publish Expression mới.
6. Những request tiếp theo lấy Expression đã parse để evaluate.

Ví dụ minh họa:

~~~java
public final class RuleEntry {
    private final String source;
    private final Expression expression;

    public RuleEntry(
            String source,
            Expression expression) {
        this.source = source;
        this.expression = expression;
    }

    public String getSource() {
        return source;
    }

    public Expression getExpression() {
        return expression;
    }
}
~~~

~~~java
public RuleEntry loadRule(
        String source,
        ExpressionParser parser) {
    Expression expression =
            parser.parseExpression(source);

    return new RuleEntry(source, expression);
}
~~~

Khi quản trị viên cập nhật rule, ứng dụng tạo RuleEntry mới rồi thay phiên bản đang dùng sau khi parse thành công. Cách này tránh để request đang chạy phải parse lại cùng rule và giúp lỗi cú pháp được xử lý ngay tại bước lưu hoặc publish cấu hình.

Nếu rule có template expression, hãy dùng đúng ParserContext khi parse. ParserContext là một phần của cách hiểu chuỗi; không nên parse template bằng overload expression thuần rồi kỳ vọng kết quả tương đương.

## So sánh parse mỗi lần với parse một lần

Cách parse trong mỗi request:

~~~java
public boolean evaluate(Order order) {
    ExpressionParser parser =
            new SpelExpressionParser();

    Expression expression =
            parser.parseExpression(
                    "active and total >= #minimum");

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable(
            "minimum",
            new BigDecimal("100.00"));

    Boolean result =
            expression.getValue(context, Boolean.class);

    return Boolean.TRUE.equals(result);
}
~~~

Mỗi lần gọi evaluate, ứng dụng tạo parser, parse chuỗi và đánh giá expression. Nếu source không thay đổi, hai bước đầu bị lặp lại không cần thiết.

Cách parse một lần và tái sử dụng:

~~~java
public class OrderEvaluator {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    private final Expression expression =
            parser.parseExpression(
                    "active and total >= #minimum");

    public boolean evaluate(Order order) {
        StandardEvaluationContext context =
                new StandardEvaluationContext(order);

        context.setVariable(
                "minimum",
                new BigDecimal("100.00"));

        Boolean result =
                expression.getValue(context, Boolean.class);

        return Boolean.TRUE.equals(result);
    }
}
~~~

Trong cách thứ hai, parser và Expression được giữ lại. Mỗi lần gọi chỉ tạo context phù hợp với Order và đánh giá biểu thức. Đây thường là lựa chọn phù hợp hơn khi cùng một expression được dùng lặp lại.

## Parse cost phụ thuộc độ phức tạp biểu thức

Không phải mọi expression đều có cùng chi phí parse. Một biểu thức đơn giản như:

~~~text
price > 100
~~~

thường ít công việc hơn một biểu thức có nhiều tầng property, lời gọi method, toán tử, selection/projection hoặc template chứa nhiều đoạn expression.

Một số yếu tố có thể ảnh hưởng đến chi phí parse:

- Độ dài chuỗi source.
- Số lượng token và độ sâu cấu trúc cú pháp.
- Số lượng biểu thức con, toán tử và lời gọi method.
- Số đoạn expression nhúng trong template.
- Cấu hình parser và các tính năng được bật.
- Chi phí cấp phát các node và object phục vụ biểu diễn Expression.

Parse một expression phức tạp một lần rồi dùng lại thường tiết kiệm hơn parse lại nhiều lần. Tuy nhiên, nếu expression chỉ được dùng một lần, việc duy trì cache hoặc cơ chế quản lý phức tạp có thể không đem lại lợi ích đáng kể.

## Parse không đồng nghĩa với evaluate

Gọi parseExpression chỉ tạo một Expression từ source. Nó không tự động chạy toàn bộ logic trên root object.

~~~java
Expression expression =
        parser.parseExpression("customer.address.city");
~~~

Ở thời điểm này, parser đã phân tích cú pháp và tạo Expression. Việc truy cập customer, address và city chỉ xảy ra khi gọi getValue với một root object và EvaluationContext phù hợp:

~~~java
String city =
        expression.getValue(
                context,
                order,
                String.class);
~~~

Vì vậy, một expression có thể parse thành công nhưng vẫn thất bại khi evaluate nếu property không tồn tại, một object trung gian null, method không được phép gọi hoặc kiểu dữ liệu không tương thích.

Parse sớm giúp phát hiện lỗi cú pháp. Nó không chứng minh expression sẽ chạy thành công với mọi dữ liệu runtime.

## Expression có thể dùng với nhiều root object

Expression đã parse không cần gắn cố định với một root object. Cùng một Expression có thể được đánh giá trên nhiều đối tượng nếu chúng đáp ứng cấu trúc mà biểu thức yêu cầu:

~~~java
Expression expression =
        parser.parseExpression("total >= #minimum");

StandardEvaluationContext firstContext =
        new StandardEvaluationContext();
firstContext.setVariable(
        "minimum",
        new BigDecimal("100.00"));

StandardEvaluationContext secondContext =
        new StandardEvaluationContext();
secondContext.setVariable(
        "minimum",
        new BigDecimal("250.00"));

boolean firstResult = Boolean.TRUE.equals(
        expression.getValue(
                firstContext,
                firstOrder,
                Boolean.class));

boolean secondResult = Boolean.TRUE.equals(
        expression.getValue(
                secondContext,
                secondOrder,
                Boolean.class));
~~~

Cùng một Expression được dùng với hai root object và hai context khác nhau. Giá trị biến không được lưu vào source Expression; nó đến từ context được truyền vào mỗi lần evaluate.

Điều này giúp tách phần cú pháp ổn định khỏi dữ liệu thay đổi theo request.

## Không cache EvaluationContext cùng Expression

Expression thường là phần có thể tái sử dụng. EvaluationContext lại có thể chứa root object, variable và dữ liệu riêng của một lần xử lý.

Nếu context chứa biến theo request, không nên lưu nó cùng Expression trong một cache dùng chung:

~~~java
// Không nên dùng một context mutable chung cho mọi request
StandardEvaluationContext sharedContext =
        new StandardEvaluationContext();
~~~

Nếu nhiều request cùng cập nhật variable trên context này, giá trị của request này có thể ghi đè giá trị của request khác. Điều đó có thể dẫn đến kết quả không ổn định hoặc rò rỉ dữ liệu giữa các lần đánh giá.

Nên giữ Expression trong cache và tạo context riêng cho mỗi lần đánh giá hoặc cho mỗi đơn vị công việc có vòng đời rõ ràng:

~~~java
public boolean evaluate(
        Expression expression,
        Order order,
        BigDecimal minimum) {

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimum", minimum);

    return Boolean.TRUE.equals(
            expression.getValue(context, Boolean.class));
}
~~~

Nếu context chỉ chứa cấu hình cố định và được dùng đồng thời, hãy kiểm tra rõ tính an toàn luồng của mọi thành phần tùy chỉnh. Đặc biệt, không chia sẻ context mutable nếu các variable hoặc root object có thể thay đổi.

## Cache Expression cho rule động

Nếu source của expression đến từ database hoặc người dùng có quyền cấu hình rule, cache Expression có thể tránh parse lặp lại. Với một bộ parser và ParserContext cố định, source có thể được dùng làm khóa cache.

Ví dụ minh họa với ConcurrentHashMap:

~~~java
private final ExpressionParser parser =
        new SpelExpressionParser();

private final ConcurrentMap<String, Expression> expressionCache =
        new ConcurrentHashMap<>();

public Expression getExpression(String source) {
    return expressionCache.computeIfAbsent(
            source,
            parser::parseExpression);
}
~~~

Ví dụ trên minh họa nguyên tắc cache theo source. Trong ứng dụng thực tế, nếu có nhiều parser configuration hoặc ParserContext, khóa cache phải phân biệt các cấu hình đó. Cùng một chuỗi có thể được hiểu khác nhau giữa expression thuần và template expression.

Một cache production nên có giới hạn kích thước, chính sách eviction và cơ chế invalidation. Không nên dùng một ConcurrentHashMap không giới hạn cho source do người dùng tự do cung cấp, vì mỗi chuỗi khác nhau có thể tạo thêm một Expression và làm bộ nhớ tăng liên tục.

Có thể dùng cache có giới hạn như Caffeine hoặc một cơ chế quản lý cache tương đương. Cần quyết định rõ thời gian sống, số entry tối đa và hành vi khi rule bị xóa hoặc cập nhật.

## Khóa cache phải phản ánh cấu hình parse

Không phải chỉ source text quyết định kết quả parse. Một số thông tin khác cũng có thể ảnh hưởng:

- **ParserContext:** expression thuần và template expression có cách parse khác nhau.
- **Template prefix/suffix:** delimiter tùy chỉnh làm thay đổi cách chia literal và expression.
- **SpelParserConfiguration:** compiler mode, auto-grow và các thiết lập parser khác.
- **Phiên bản hoặc loại rule:** nếu ứng dụng có nhiều bộ grammar hoặc chính sách parsing riêng.

Nếu một cache dùng chung nhiều cấu hình, khóa cần bao gồm những thông tin ảnh hưởng đến cách tạo Expression. Cách đơn giản hơn là duy trì cache riêng cho từng parser đã cấu hình cố định.

Không nên lấy Expression được parse theo một chính sách rộng rồi dùng lại trong một ngữ cảnh bảo mật khác mà không kiểm tra. Expression không chứa EvaluationContext, nhưng parser configuration và chính sách đánh giá của ứng dụng vẫn cần nhất quán.

## Invalidation khi expression thay đổi

Khi một rule được cập nhật, Expression cũ không còn đại diện cho source mới. Ứng dụng cần loại bỏ hoặc thay entry cache tương ứng.

Một quy trình an toàn:

1. Nhận source mới.
2. Parse source mới thành Expression.
3. Nếu parse thất bại, giữ rule đang hoạt động và trả lỗi cho người cập nhật.
4. Nếu parse thành công, publish phiên bản mới một cách nguyên tử.
5. Loại bỏ entry cũ hoặc thay nó bằng entry mới.
6. Ghi nhận version để log và truy vết khi cần.

Nếu nhiều request đang dùng Expression cũ, việc publish reference mới giúp các request tiếp theo nhận bản mới trong khi request hiện tại có thể hoàn tất với bản đã lấy trước đó. Cách thay thế cần phù hợp với mô hình đồng bộ và cache mà ứng dụng đang dùng.

Không nên xóa cache trước khi parse source mới thành công. Nếu source mới sai cú pháp và entry cũ đã bị xóa, ứng dụng có thể mất rule đang chạy dù bản mới chưa thể sử dụng.

## Parse ngay khi startup hay parse lười?

Hai chiến lược thường gặp:

| Chiến lược | Cách làm | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|---|
| Parse lúc startup | Parse tất cả expression tĩnh khi ứng dụng khởi động | Phát hiện lỗi sớm, request đầu tiên không chịu parse cost | Startup có thể lâu hơn nếu có nhiều rule |
| Parse khi nạp cấu hình | Parse khi đọc hoặc publish rule | Gắn lỗi với thao tác cập nhật, không parse lại mỗi request | Cần quản lý phiên bản và invalidation |
| Parse lười | Chỉ parse khi expression được dùng lần đầu | Không tốn công parse rule không bao giờ dùng | Request đầu tiên chịu chi phí và có thể gặp lỗi |
| Parse mỗi lần | Parse lại ở mọi lần đánh giá | Cách triển khai đơn giản | Lặp chi phí và tạo object không cần thiết |

Với expression tĩnh, parse lúc startup thường là lựa chọn rõ ràng. Với rule động, parse lúc lưu hoặc publish rule giúp phát hiện lỗi trước khi rule đi vào đường xử lý chính. Parse lười phù hợp khi số lượng rule lớn nhưng chỉ một phần được dùng, miễn là có cache giới hạn và xử lý lỗi đúng cách.

Parse mỗi lần chỉ hợp lý khi expression thực sự khác nhau ở mỗi lần gọi hoặc tần suất thấp đến mức chi phí không đáng kể. Ngay cả khi source thay đổi, hãy cân nhắc cache theo source đã chuẩn hóa và có giới hạn thay vì tạo parser mới liên tục.

## Template expression cũng cần parse một lần

Nếu ứng dụng dùng template expression, parser phải nhận đúng ParserContext:

~~~java
ParserContext templateContext =
        new TemplateParserContext();

Expression messageTemplate =
        parser.parseExpression(
                "Xin chào, #{#name}!",
                templateContext);
~~~

Sau khi parse, có thể tái sử dụng messageTemplate với nhiều EvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("name", "An");

String message =
        messageTemplate.getValue(context, String.class);
~~~

Nếu parse cùng source bằng parseExpression(String) thay vì overload có ParserContext, parser sẽ hiểu toàn bộ chuỗi theo chế độ expression thuần. Vì vậy, cache template cần giữ đúng ParserContext hoặc dùng cache riêng cho template parser.

## Compiler mode và chi phí lần đánh giá đầu

SpEL có các chế độ compiler **OFF**, **IMMEDIATE** và **MIXED**. Đây là một phần của chi phí evaluation sau khi Expression đã được parse.

Parse một lần không có nghĩa mọi chi phí đã kết thúc. Với compiler mode, những lần đánh giá đầu có thể dùng interpreter, thu thập thông tin kiểu và thử tạo bytecode tùy chế độ. Nếu benchmark chỉ đo một vài lần gọi đầu tiên, kết quả có thể không phản ánh hiệu năng ổn định.

Khi đo, cần tách:

- Thời gian tạo parser.
- Thời gian parse source.
- Thời gian evaluate bằng interpreter.
- Thời gian warm-up và compile nếu có.
- Thời gian evaluate sau khi compiled form được dùng.

Không nên bật compiler chỉ để giải quyết việc parse lặp lại. Compiler tối ưu một phần chi phí evaluation; cache Expression mới giải quyết việc parse lại cùng source.

## Đo parse cost và evaluate cost riêng biệt

Để biết tối ưu nào có ích, benchmark cần đo các đường đi riêng:

1. **Parser construction:** tạo SpelExpressionParser với cùng cấu hình.
2. **Parse only:** gọi parseExpression trên source đã chọn.
3. **Evaluate only:** dùng một Expression đã parse trước rồi gọi getValue nhiều lần.
4. **Parse plus evaluate:** mô phỏng đường xử lý hiện tại nếu ứng dụng đang làm cả hai trong mỗi request.
5. **Warm-up/steady state:** nếu dùng compiler mode, đo cả giai đoạn trước và sau compile.

Nên dùng JMH cho benchmark Java thay vì đo một lần bằng System.nanoTime trong test thông thường. JMH giúp xử lý warm-up, lặp, fork và các vấn đề tối ưu hóa của JVM tốt hơn.

Benchmark cần dùng expression và dữ liệu đại diện cho production. Một phép tính ngắn không đại diện cho selection trên collection lớn hoặc truy cập property lồng nhau. Hãy đo cả throughput, latency và allocation nếu chi phí tạo Expression là mối quan tâm.

## Xử lý expression source không đáng tin cậy

Parse source do người dùng cung cấp cũng tiêu tốn CPU và bộ nhớ. Nếu ứng dụng cho phép người dùng tạo nhiều expression khác nhau, cache không giới hạn có thể bị lợi dụng để làm tăng bộ nhớ.

Một số biện pháp:

- Giới hạn độ dài source trước khi parse.
- Giới hạn số lượng rule hoặc expression mỗi tenant/người dùng.
- Dùng cache có giới hạn và eviction.
- Giới hạn tần suất tạo hoặc cập nhật expression.
- Parse ở bước lưu/publish và từ chối source sai cú pháp.
- Dùng EvaluationContext có capability allowlist nếu source không đáng tin cậy.
- Không nối dữ liệu đầu vào vào source; truyền dữ liệu qua variable.
- Theo dõi thời gian parse và số lượng cache miss.

Cache giúp giảm parse cost nhưng không làm expression an toàn hơn. Việc đánh giá vẫn phụ thuộc root object, EvaluationContext, property accessor, method resolver, type locator và các capability được expose.

## Lỗi parse nên được phát hiện ở thời điểm phù hợp

Parse có thể thất bại với **ParseException** khi chuỗi sai cú pháp hoặc ParserContext không phù hợp. Evaluation có thể thất bại với **EvaluationException** khi dữ liệu runtime hoặc context không đáp ứng expression.

Nếu parse lúc startup, lỗi cú pháp có thể làm ứng dụng không khởi động. Nếu parse khi lưu rule, lỗi nên được trả về cho người quản trị và rule cũ tiếp tục hoạt động. Nếu parse lười, lỗi có thể chỉ xuất hiện ở request đầu tiên dùng rule đó.

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
} catch (ParseException ex) {
    throw new IllegalArgumentException(
            "Rule has invalid SpEL syntax", ex);
}

try {
    Object result =
            expression.getValue(context, rootObject);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Rule cannot be evaluated with current data", ex);
}
~~~

Tách hai giai đoạn giúp log đúng nguyên nhân. Không nên bắt mọi lỗi rồi trả về một giá trị mặc định vì có thể che giấu source sai, biến thiếu hoặc dữ liệu runtime không hợp lệ.

## Quy trình khuyến nghị

Với expression tĩnh trong ứng dụng:

1. Tạo parser khi khởi tạo component hoặc cấu hình ứng dụng.
2. Parse các expression một lần.
3. Giữ Expression trong field final hoặc registry có vòng đời rõ ràng.
4. Tạo root object và context phù hợp cho từng lần evaluate.
5. Theo dõi lỗi evaluation riêng với lỗi parse.

Với rule động:

1. Giới hạn và xác thực source khi người dùng tạo hoặc cập nhật.
2. Parse bằng parser và ParserContext đúng.
3. Chỉ publish rule nếu parse thành công.
4. Cache Expression theo source và cấu hình parse, có giới hạn dung lượng.
5. Invalidate hoặc thay thế entry khi rule đổi.
6. Tạo context riêng cho dữ liệu của từng lần đánh giá.
7. Benchmark đường parse và evaluate riêng trước khi tối ưu compiler.

## Kết luận

Chi phí cần phân biệt là **tạo parser**, **parse source thành Expression** và **evaluate Expression**. Tạo parser thường là bước khởi tạo nhẹ; parseExpression thực hiện công việc phân tích cú pháp và tạo cấu trúc biểu thức; getValue/setValue mới truy cập dữ liệu và thực hiện logic. Nếu source không đổi, parse lại ở mỗi request thường lãng phí.

Hãy tạo parser với cấu hình ổn định và tái sử dụng. Parse expression tĩnh lúc startup; parse rule động khi nạp hoặc publish cấu hình; cache Expression có giới hạn và invalidation rõ ràng. Chỉ cache phần cú pháp, không cache context chứa dữ liệu request. Khi benchmark, đo parse và evaluate riêng, bao gồm warm-up nếu bật compiler. Cách tổ chức này giảm công việc lặp lại mà vẫn giữ dữ liệu runtime và quyền truy cập trong đúng EvaluationContext của từng lần đánh giá.

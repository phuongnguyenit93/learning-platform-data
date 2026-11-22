# Interpreter mode, immediate mode và mixed mode

Spring Expression Language (SpEL) có thể đánh giá biểu thức bằng **interpreter** hoặc biên dịch biểu thức thành bytecode để thực thi nhanh hơn. Cách chọn được điều khiển bởi **SpelCompilerMode**, thường được truyền vào **SpelParserConfiguration** khi tạo SpelExpressionParser.

Ba chế độ chính là **OFF**, **IMMEDIATE** và **MIXED**. Chúng quyết định SpEL có thử biên dịch biểu thức hay không, khi nào bắt đầu thử và cách xử lý nếu biểu thức đã biên dịch không còn phù hợp với dữ liệu runtime. Không có một chế độ tốt nhất cho mọi ứng dụng: lựa chọn phụ thuộc tần suất đánh giá, độ ổn định kiểu dữ liệu và khả năng biên dịch của biểu thức.

## Interpreter mode là gì?

Ở chế độ thông dịch, SpEL đánh giá cấu trúc Expression bằng interpreter. Parser phân tích chuỗi một lần để tạo Expression; mỗi lần gọi getValue hoặc setValue, interpreter thực hiện các thao tác cần thiết theo cấu trúc đó.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("price * quantity");

BigDecimal total =
        expression.getValue(order, BigDecimal.class);
~~~

Biểu thức được parse thành Expression. Khi ứng dụng gọi getValue, SpEL đọc các property price và quantity từ root object order rồi thực hiện phép nhân.

Interpreter phù hợp với nhiều trường hợp vì hỗ trợ linh hoạt các tính năng của SpEL và không cần tạo bytecode riêng cho biểu thức. Đây cũng là cách đánh giá mặc định khi compiler bị tắt.

Một điểm tối ưu quan trọng là **parse một lần và tái sử dụng Expression**. Nếu ứng dụng tạo parser và parse lại cùng một chuỗi trong mỗi request, chi phí parse lặp lại có thể lớn hơn phần chi phí mà compiler giúp tiết kiệm. Trước khi bật compiler, hãy bảo đảm Expression được cache hoặc giữ trong thành phần có vòng đời phù hợp.

## SpelCompilerMode

SpEL cung cấp enum **SpelCompilerMode** với ba giá trị:

| Chế độ | Hành vi chính | Phù hợp khi |
|---|---|---|
| **OFF** | Không biên dịch; tiếp tục dùng interpreter | Ưu tiên tính linh hoạt hoặc biểu thức không cần tối ưu compile |
| **IMMEDIATE** | Thử biên dịch sớm, thường sau lần đánh giá thông dịch đầu tiên | Kiểu dữ liệu ổn định và muốn chuyển sang bytecode nhanh |
| **MIXED** | Bắt đầu bằng interpreter, sau một số lần đánh giá mới thử biên dịch; có thể quay lại interpreter nếu compiled form thất bại | Workload lặp lại nhưng kiểu runtime có thể thay đổi |

Chế độ được chọn khi tạo parser configuration. Đây là chính sách áp dụng cho các Expression được parser đó tạo ra, không phải một cờ bật/tắt riêng trên từng lời gọi getValue.

## OFF mode

**SpelCompilerMode.OFF** tắt compiler. Biểu thức được đánh giá bằng interpreter trong suốt vòng đời sử dụng.

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.OFF,
                MyApplication.class.getClassLoader());

ExpressionParser parser =
        new SpelExpressionParser(configuration);

Expression expression =
        parser.parseExpression("price * quantity");
~~~

OFF là lựa chọn mặc định khi không cấu hình compiler mode khác. Chế độ này phù hợp khi biểu thức chỉ được đánh giá ít lần, khi cấu trúc biểu thức không được compiler hỗ trợ hoặc khi dữ liệu có kiểu biến động khiến lợi ích compile không rõ ràng.

OFF không có chi phí tạo bytecode cho biểu thức. Đổi lại, mỗi lần đánh giá vẫn đi qua interpreter. Với biểu thức đơn giản hoặc workload không nóng, sự khác biệt hiệu năng có thể không đáng kể.

## IMMEDIATE mode

**SpelCompilerMode.IMMEDIATE** yêu cầu SpEL thử biên dịch biểu thức sớm nhất có thể. Thông thường, biểu thức được đánh giá bằng interpreter trước để thu thập thông tin runtime cần thiết; sau lần đánh giá đầu tiên, SpEL có thể thử tạo phiên bản bytecode cho những biểu thức compiler hỗ trợ.

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.IMMEDIATE,
                MyApplication.class.getClassLoader());

ExpressionParser parser =
        new SpelExpressionParser(configuration);

Expression expression =
        parser.parseExpression("price * quantity");
~~~

Khi biểu thức có thể biên dịch, những lần đánh giá sau có thể chạy phiên bản compiled. Điều này có thể giảm chi phí đánh giá lặp lại trong workload phù hợp.

Đổi lại, compiled expression thường dựa vào kiểu dữ liệu và cấu trúc object đã quan sát khi biên dịch. Nếu dữ liệu runtime sau đó thay đổi theo cách không còn phù hợp với bytecode, việc thực thi compiled expression có thể thất bại và phát sinh exception.

Ví dụ, một biểu thức được biên dịch khi property payload có kiểu String nhưng sau đó nhận object có kiểu khác. Phiên bản compiled có thể giả định kiểu đã thấy trước đó và không xử lý được thay đổi này như interpreter.

Vì vậy, IMMEDIATE phù hợp hơn khi kiểu của root object, property và các giá trị liên quan ổn định qua các lần đánh giá. Nếu cùng một Expression được dùng với nhiều loại object hoặc dữ liệu không đồng nhất, cần kiểm tra kỹ hành vi trước khi chọn chế độ này.

Nếu compiler không thể biên dịch một biểu thức, SpEL có thể tiếp tục dùng interpreter cho biểu thức đó. Bật IMMEDIATE không có nghĩa mọi biểu thức đều chắc chắn tạo được bytecode.

## MIXED mode

**SpelCompilerMode.MIXED** bắt đầu bằng interpreter. Sau một số lần đánh giá, SpEL thử biên dịch biểu thức nếu có đủ thông tin và biểu thức được hỗ trợ.

Nếu compiled expression chạy thành công, SpEL có thể tiếp tục dùng phiên bản đã biên dịch. Nếu compiled form thất bại do thay đổi kiểu hoặc cấu trúc runtime, MIXED có thể quay lại interpreter và tiếp tục đánh giá theo cơ chế thông dịch. Sau đó, SpEL có thể thử biên dịch lại khi điều kiện phù hợp.

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.MIXED,
                MyApplication.class.getClassLoader());

ExpressionParser parser =
        new SpelExpressionParser(configuration);

Expression expression =
        parser.parseExpression("price * quantity");
~~~

MIXED hữu ích khi biểu thức được đánh giá lặp lại nhưng dữ liệu có thể thay đổi kiểu trong thực tế. Khả năng quay lại interpreter giúp ứng dụng linh hoạt hơn so với IMMEDIATE khi compiled form không còn phù hợp.

Không nên xem MIXED là cơ chế bảo đảm mọi biểu thức đều chạy nhanh hoặc mọi lỗi runtime đều được xử lý tự động. Lỗi do dữ liệu null, property không tồn tại, phép toán không hợp lệ hoặc logic nghiệp vụ vẫn có thể xảy ra trong interpreter. MIXED chỉ điều chỉnh việc chuyển đổi giữa compiled và interpreted form khi quá trình thực thi compiled expression gặp vấn đề thuộc phạm vi xử lý của compiler.

## So sánh cách xử lý khi kiểu runtime thay đổi

Giả sử cùng một Expression được đánh giá trên các object có property với kiểu dữ liệu không đồng nhất. Interpreter có thể xử lý linh hoạt hơn vì mỗi lần đánh giá nó sử dụng cơ chế truy cập và chuyển đổi theo context hiện tại. Compiled expression có thể dựa trên kiểu đã được quan sát khi biên dịch.

| Tình huống | OFF | IMMEDIATE | MIXED |
|---|---|---|---|
| Kiểu dữ liệu ổn định | Tiếp tục thông dịch | Có thể dùng compiled form sau khi compile | Có thể chuyển sang compiled form sau giai đoạn thông dịch |
| Kiểu thay đổi sau compile | Interpreter xử lý theo kiểu runtime nếu biểu thức hợp lệ | Compiled form có thể phát sinh lỗi | Có thể quay lại interpreter khi compiled form thất bại |
| Biểu thức không được hỗ trợ compile | Tiếp tục thông dịch | Tiếp tục thông dịch nếu không compile được | Tiếp tục thông dịch nếu không compile được |
| Chi phí tạo bytecode | Không có | Thử sớm | Thử sau khi đã được đánh giá nhiều lần |

Sự khác biệt này đặc biệt quan trọng với biểu thức dùng chung cho nhiều loại DTO, object proxy hoặc dữ liệu đến từ nguồn có schema không đồng nhất. Nếu kiểu runtime không ổn định, OFF hoặc MIXED thường dễ dự đoán hơn IMMEDIATE.

## Cấu hình parser và ClassLoader

Compiler tạo bytecode cho biểu thức và cần một **ClassLoader** để nạp lớp được sinh ra. Có thể truyền compiler mode và ClassLoader vào SpelParserConfiguration:

~~~java
ClassLoader compilerClassLoader =
        MyApplication.class.getClassLoader();

SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.MIXED,
                compilerClassLoader);

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

ClassLoader cần nhìn thấy những kiểu mà compiled expression tham chiếu đến. Trong ứng dụng có plugin, application server, module riêng hoặc class loader phân tầng, việc chọn class loader phù hợp có thể ảnh hưởng đến khả năng compile và nạp bytecode.

Nếu không chỉ định class loader riêng, các overload cấu hình khác hoặc cơ chế mặc định của phiên bản Spring đang dùng sẽ quyết định cách nạp lớp. Với môi trường triển khai phức tạp, nên cấu hình tường minh và kiểm tra trong đúng môi trường runtime thay vì chỉ kiểm tra trên máy phát triển.

Compiler mode và class loader được gắn vào SpelParserConfiguration. Nếu ứng dụng cần các parser có chính sách khác nhau, có thể tạo các SpelExpressionParser riêng với cấu hình tương ứng.

## Không phải mọi biểu thức đều biên dịch được

SpEL compiler hỗ trợ một tập con các biểu thức. Khả năng compile phụ thuộc vào cấu trúc expression, thông tin kiểu thu thập được trong các lần đánh giá và những tính năng mà compiler hỗ trợ.

Các biểu thức có kiểu dữ liệu ổn định, truy cập property và thực hiện phép toán rõ ràng thường dễ phù hợp hơn. Những biểu thức phụ thuộc nhiều vào hành vi động, kiểu thay đổi, hoặc các khả năng không được compiler hỗ trợ có thể tiếp tục chạy bằng interpreter.

Không nên suy luận rằng một biểu thức chắc chắn compile chỉ vì parser chấp nhận cú pháp của nó. Parse thành công và compile thành công là hai việc khác nhau:

1. Parser xác nhận chuỗi đúng cú pháp SpEL và tạo Expression.
2. Interpreter có thể đánh giá Expression trên context và dữ liệu hiện tại.
3. Compiler có thể hoặc không thể tạo bytecode cho cấu trúc expression đó.
4. Nếu đã compile, compiled form vẫn cần phù hợp với dữ liệu ở những lần chạy tiếp theo.

Một biểu thức không compile được không nhất thiết là biểu thức sai. Nó có thể hoàn toàn hợp lệ và tiếp tục được interpreter đánh giá.

## Khi compiled expression không còn phù hợp

Compiled form có thể dựa trên kiểu dữ liệu đã quan sát trước đó. Nếu kiểu runtime thay đổi, compiled code có thể không còn thực hiện đúng thao tác đã được sinh ra.

Ví dụ, một biểu thức truy cập property hoặc gọi method trên một kiểu cụ thể có thể được biên dịch với giả định về kiểu đó. Nếu lần đánh giá sau nhận một object có kiểu khác hoặc một giá trị không tương thích, compiled form có thể thất bại.

Cách ứng xử khác nhau theo mode:

- Với **IMMEDIATE**, lỗi từ compiled expression có thể được đưa ra cho caller. Ứng dụng cần xử lý hoặc chọn mode khác nếu dữ liệu thực tế cho phép kiểu thay đổi.
- Với **MIXED**, SpEL có thể chuyển trở lại interpreter sau lỗi compiled execution, rồi tiếp tục thử compile lại ở thời điểm sau.
- Với **OFF**, không có compiled form nên không có tình huống lỗi do compiled code giả định kiểu cũ.

Dù dùng mode nào, ứng dụng vẫn cần xác thực dữ liệu và xử lý lỗi evaluation. Không nên dựa vào compiler mode để thay thế validation.

## Đo hiệu năng trước khi chọn mode

Compiler được thiết kế để cải thiện hiệu năng cho biểu thức được đánh giá nhiều lần, nhưng việc compile cũng có chi phí. Với biểu thức ít dùng, chi phí khởi tạo và sinh bytecode có thể không được bù lại bởi thời gian tiết kiệm ở các lần chạy sau.

Một quy trình lựa chọn thực tế:

1. Parse expression một lần và tái sử dụng Expression.
2. Đo thời gian đánh giá ở OFF trên workload đại diện.
3. Thử MIXED hoặc IMMEDIATE với cùng dữ liệu và số lần đánh giá.
4. Đo cả chi phí khởi động, giai đoạn warm-up và throughput sau khi ổn định.
5. Kiểm tra dữ liệu có thay đổi kiểu hoặc cấu trúc giữa các lần đánh giá không.
6. Chọn mode dựa trên lợi ích đo được và yêu cầu ổn định của ứng dụng.

Benchmark cần dùng dữ liệu gần với production. Nếu test chỉ dùng một object có kiểu cố định, kết quả có thể không phản ánh hệ thống thật khi nhiều loại object hoặc proxy được đưa vào cùng một expression.

Không nên chỉ so sánh một lần gọi getValue. Cần đo đủ số lần đánh giá để phản ánh thời điểm compiler bắt đầu hoạt động và chi phí warm-up.

## Parse một lần và tái sử dụng Expression

Trước khi bật compiler, hãy tránh parse lại cùng một chuỗi trong đường xử lý nóng:

~~~java
public class PricingEvaluator {
    private final Expression totalExpression;

    public PricingEvaluator() {
        ExpressionParser parser =
                new SpelExpressionParser();

        this.totalExpression =
                parser.parseExpression("price * quantity");
    }

    public BigDecimal calculate(Order order) {
        return totalExpression.getValue(
                order,
                BigDecimal.class);
    }
}
~~~

Expression được tạo một lần khi khởi tạo PricingEvaluator rồi dùng lại cho từng Order. Khi cần tối ưu thêm, có thể thay parser bằng parser được tạo từ SpelParserConfiguration có compiler mode phù hợp.

Cần quản lý EvaluationContext theo dữ liệu của từng lần đánh giá. Nếu context chứa biến mutable theo request, không nên chia sẻ nó giữa nhiều luồng mà không có chính sách đồng bộ hoặc cách tạo context riêng.

## Lỗi parse, lỗi evaluation và lỗi compile

Ba giai đoạn cần được phân biệt:

- **ParseException:** chuỗi biểu thức sai cú pháp nên parser không tạo được Expression.
- **EvaluationException:** biểu thức hợp lệ nhưng không thể đánh giá với root object, biến hoặc context hiện tại.
- **Compile failure:** compiler không thể tạo bytecode cho expression hoặc compiled form không thể thực thi với dữ liệu runtime hiện tại.

Compile failure không đồng nghĩa với ParseException. Một expression có thể parse và evaluate bình thường bằng interpreter nhưng không được compiler hỗ trợ.

Ví dụ xử lý parse và evaluation:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("price * quantity");
} catch (ParseException ex) {
    throw new IllegalArgumentException(
            "Invalid SpEL syntax", ex);
}

try {
    BigDecimal total =
            expression.getValue(order, BigDecimal.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot evaluate pricing expression", ex);
}
~~~

Khi bật compiler, cần quan sát thêm lỗi liên quan đến compiled execution theo mode đã chọn. Không nên bắt mọi exception rồi trả về một giá trị mặc định vì cách đó có thể che giấu dữ liệu không hợp lệ hoặc lỗi nghiệp vụ.

## Chọn mode theo đặc điểm ứng dụng

| Đặc điểm workload | Hướng lựa chọn |
|---|---|
| Biểu thức ít được đánh giá | OFF thường đã đủ |
| Biểu thức có kiểu dữ liệu ổn định và được gọi rất nhiều | Đo thử IMMEDIATE hoặc MIXED |
| Biểu thức dùng trên nhiều loại object | Ưu tiên kiểm tra OFF/MIXED; thận trọng với IMMEDIATE |
| Cần hành vi linh hoạt khi compiled form thất bại | MIXED |
| Biểu thức không được compiler hỗ trợ | OFF hoặc tiếp tục dùng interpreter |
| Ứng dụng chạy trong môi trường class loader phức tạp | Kiểm tra và cấu hình ClassLoader phù hợp |

Đây là hướng dẫn lựa chọn, không phải quy tắc cứng. Kết quả thực tế phụ thuộc biểu thức, phiên bản Spring, JDK, class loader, dữ liệu và tần suất đánh giá.

## Kết luận

SpEL cung cấp ba compiler mode: **OFF** luôn dùng interpreter; **IMMEDIATE** thử biên dịch sớm và có thể đưa lỗi compiled execution ra caller khi kiểu runtime thay đổi; **MIXED** bắt đầu bằng interpreter, thử compile sau nhiều lần đánh giá và có thể quay lại interpreter nếu compiled form thất bại.

Hãy chọn mode dựa trên tần suất đánh giá, độ ổn định kiểu dữ liệu và khả năng compile của biểu thức. Parse một lần rồi tái sử dụng Expression trước khi tối ưu sâu hơn, cấu hình ClassLoader phù hợp và benchmark với workload thực tế. Compiler là một tối ưu tùy chọn; nó không thay thế validation, xử lý lỗi hoặc việc hiểu rõ dữ liệu mà biểu thức sẽ nhận.

# Giới hạn kích thước expression và dữ liệu đầu vào

Một expression SpEL có thể rất ngắn nhưng xử lý dữ liệu lớn, hoặc rất dài dù chỉ thực hiện vài phép so sánh. Vì vậy, giới hạn kích thước chuỗi expression là cần thiết nhưng chưa đủ để bảo vệ hiệu năng và tài nguyên của ứng dụng. Cần kiểm soát đồng thời độ dài biểu thức, cấu trúc biểu thức, số lượng và kích thước dữ liệu được đưa vào, khả năng tự mở rộng collection, số lần parse và chi phí của các hàm được phép gọi.

Mục tiêu là để mỗi rule chỉ xử lý lượng công việc nằm trong ngân sách mà ứng dụng chấp nhận. Hãy đặt giới hạn ngay tại ranh giới nhận cấu hình hoặc request, cung cấp root object nhỏ và có kiểu rõ ràng, giới hạn collection/string, tắt khả năng tự mở rộng nếu không cần, và theo dõi lỗi cũng như thời gian đánh giá.

## 1. Hai loại kích thước cần kiểm soát

Có hai nhóm đầu vào khác nhau:

- **Expression source:** chuỗi SpEL mà parser phải phân tích, ví dụ total >= #minimumTotal.
- **Evaluation data:** root object, biến, chuỗi, collection, map và các object mà expression truy cập khi chạy.

Giới hạn expression source ngăn chuỗi quá dài hoặc cố tình phức tạp đi vào parser. Giới hạn evaluation data ngăn một expression ngắn như items.![name] phải xử lý hàng trăm nghìn phần tử hoặc tạo ra kết quả quá lớn.

Ví dụ, expression sau rất ngắn:

    items.?[active].![name]

Nhưng nếu items chứa một triệu phần tử, selection và projection vẫn phải xử lý lượng dữ liệu lớn. Ngược lại, một expression dài chứa nhiều literal có thể gây tốn thời gian parse dù dữ liệu đầu vào nhỏ.

Do đó, không dùng một giới hạn duy nhất để đại diện cho toàn bộ chi phí SpEL. Đặt ngân sách riêng cho chuỗi expression, dữ liệu, collection, kết quả và tần suất đánh giá.

## 2. Giới hạn độ dài expression

Độ dài expression ảnh hưởng đến thời gian parse, bộ nhớ cần để giữ chuỗi và cấu trúc biểu thức. Ứng dụng nhận rule từ file, database, API hoặc người quản trị nên kiểm tra độ dài trước khi parse.

Trong các phiên bản Spring Framework có hỗ trợ maximumExpressionLength (Spring Framework 6.2 trở lên), có thể cấu hình giới hạn này bằng SpelParserConfiguration.

Ví dụ giới hạn expression ở 4.000 ký tự:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.OFF,
                    getClass().getClassLoader(),
                    false,
                    false,
                    128,
                    4_000);

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

Các tham số trong ví dụ lần lượt cấu hình compiler mode, class loader, tự mở rộng tham chiếu null, tự mở rộng collection, kích thước tự mở rộng tối đa và độ dài expression tối đa. Chọn giới hạn theo rule thực tế; 4.000 chỉ là giá trị minh họa.

Với phiên bản Spring chưa có constructor hỗ trợ maximumExpressionLength, hãy kiểm tra ở tầng ứng dụng trước khi gọi parser:

    private static final int MAX_EXPRESSION_LENGTH = 4_000;

    Expression parseRule(
            ExpressionParser parser, String source) {

        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException(
                    "Expression must not be empty");
        }

        if (source.length() > MAX_EXPRESSION_LENGTH) {
            throw new IllegalArgumentException(
                    "Expression exceeds the configured limit");
        }

        return parser.parseExpression(source);
    }

Kiểm tra trước parser giúp ứng dụng có cùng chính sách giới hạn trên các phiên bản Spring khác nhau. String.length() đo độ dài theo đơn vị UTF-16 của Java; nếu API bên ngoài còn có giới hạn byte, hãy kiểm tra cả kích thước payload theo encoding được sử dụng.

## 3. Chọn giới hạn theo use case

Không có một độ dài tối đa phù hợp cho mọi loại rule. Một rule so sánh vài thuộc tính thường cần ít ký tự hơn một template thông báo hoặc một rule tính toán nhiều bước.

Có thể bắt đầu bằng cách phân loại:

| Loại đầu vào | Giới hạn cần cân nhắc |
|---|---|
| Rule boolean đơn giản | Độ dài expression nhỏ, ít toán tử và property path ngắn |
| Rule có selection/projection | Độ dài expression và số phần tử collection |
| Template thông báo | Độ dài template, số expression segment và độ dài kết quả |
| Rule do quản trị viên tạo | Độ dài, số lượng rule, tần suất cập nhật và quyền chỉnh sửa |
| Expression từ request người dùng | Giới hạn rất chặt hoặc thay bằng bộ lọc có cấu trúc |

Hãy thu thập các expression hợp lệ hiện có để biết phân bố độ dài và độ phức tạp. Đặt ngưỡng có khoảng dự phòng cho rule hợp lệ, nhưng không để ngưỡng cao đến mức vô hiệu hóa kiểm soát.

Nếu rule có thể được tạo bởi nhiều nhóm, hãy định nghĩa giới hạn theo loại rule hoặc tenant khi có lý do nghiệp vụ. Mọi giới hạn cần được cấu hình tập trung và có thể giải thích, tránh mỗi service tự chọn một con số khác nhau.

## 4. Độ dài không phản ánh toàn bộ độ phức tạp

Hai expression có cùng độ dài có thể tạo ra lượng công việc rất khác nhau. Ví dụ:

    total >= #minimumTotal

và:

    items.?[active and price > #minimumPrice]
         .![product.category.name]

Biểu thức thứ hai truy cập nhiều tầng property và duyệt collection. Chi phí lúc chạy phụ thuộc số phần tử, object graph và hành vi getter.

Các yếu tố ảnh hưởng đến độ phức tạp gồm:

- Số phép toán và số nhánh điều kiện.
- Độ sâu của property path.
- Số tầng selection/projection lồng nhau.
- Số lượng phần tử collection và entry của map.
- Số lần gọi method hoặc function.
- Độ dài chuỗi được so sánh hoặc xử lý.
- Chi phí getter, lazy loading và logic bên trong method.
- Số lượng expression segment trong một template.

SpEL không cung cấp một ngân sách CPU chung cho mọi expression. Giới hạn độ dài cần được kết hợp với giới hạn dữ liệu và tập capability được phép. Với nguồn expression không đáng tin cậy, nên giới hạn cú pháp được hỗ trợ hoặc dùng một DSL/bộ lọc có cấu trúc thay vì cho phép toàn bộ ngôn ngữ SpEL.

## 5. Giới hạn dữ liệu trước khi tạo EvaluationContext

Không đưa trực tiếp payload tùy ý vào root object. Hãy kiểm tra dữ liệu ở tầng API/service, sau đó tạo một DTO chỉ chứa những trường mà rule cần.

Ví dụ:

    public record OrderRuleInput(
            BigDecimal total,
            String customerTier,
            List<LineRuleInput> lines) {
    }

    public record LineRuleInput(
            String productCode,
            int quantity,
            boolean active) {
    }

Trước khi tạo context, kiểm tra:

- Số lượng phần tử trong lines không vượt ngưỡng.
- productCode không vượt độ dài cho phép.
- total nằm trong miền giá trị nghiệp vụ.
- Các trường bắt buộc không null.
- Collection không chứa phần tử null nếu rule không hỗ trợ trường hợp đó.

Sau đó mới đánh giá selection:

    EvaluationContext context =
            SimpleEvaluationContext
                    .forReadOnlyDataBinding()
                    .build();

    Expression expression =
            parser.parseExpression(
                    "lines.?[active and quantity > 0]");

    List<?> activeLines =
            expression.getValue(
                    context, input, List.class);

    boolean hasActiveLines = !activeLines.isEmpty();

DTO giới hạn object graph mà expression nhìn thấy và giúp dữ liệu được kiểm tra trước khi đánh giá. Với rule chỉ đọc, ưu tiên context read-only phù hợp với các property accessor cần dùng. Phép kiểm tra danh sách rỗng được thực hiện trong Java, không cần mở quyền gọi instance method trong context chỉ đọc.

## 6. Giới hạn collection, map và phép chiếu

Selection và projection thường có chi phí tăng theo số phần tử đầu vào. Một phép lọc đơn giản thường phải kiểm tra từng phần tử; projection phải tạo giá trị đầu ra cho từng phần tử được xử lý.

Ví dụ:

    lines.?[quantity > #minimumQuantity]

    lines.![productCode]

Nếu lines có N phần tử, biểu thức phải đi qua các phần tử tương ứng. Với collection lồng nhau, lượng công việc có thể tăng theo tích kích thước các tầng.

Hãy đặt giới hạn trước khi đưa collection vào context:

    private static final int MAX_LINES = 500;

    if (input.lines() == null
            || input.lines().size() > MAX_LINES) {
        throw new IllegalArgumentException(
                "Too many order lines");
    }

Giới hạn 500 chỉ là ví dụ; chọn giá trị theo tải và nghiệp vụ. Nếu dữ liệu lớn hơn ngưỡng, cân nhắc lọc hoặc tổng hợp trong repository/service trước rồi đưa kết quả nhỏ vào SpEL.

Cũng cần giới hạn số entry của Map, số phần tử trong nested collection và kích thước kết quả projection. Một expression ngắn không nên có quyền tạo ra một danh sách kết quả không giới hạn.

## 7. Giới hạn chuỗi và dữ liệu dạng văn bản

Các phép toán chuỗi có thể tốn tài nguyên khi đầu vào rất dài. Điều này áp dụng cho so sánh, nối chuỗi, tìm kiếm, chuyển chữ hoa/thường và regex.

Ví dụ:

    #input.matches(#pattern)

Nếu input hoặc pattern do bên ngoài cung cấp, cần giới hạn độ dài của cả hai. Một số regular expression có thể gây backtracking rất lớn với chuỗi được thiết kế đặc biệt. Giới hạn độ dài giúp giảm rủi ro nhưng không bảo đảm mọi regex đều có chi phí thấp.

Không nối một chuỗi lớn vào expression source để truyền dữ liệu. Thay vào đó, dùng biến hoặc root object:

    Expression expression =
            parser.parseExpression(
                    "customerCode == #expectedCode");

    context.setVariable("expectedCode", suppliedCode);

Cách này giữ expression ổn định và giúp kiểm tra độ dài dữ liệu riêng. Nếu cần chuẩn hóa Unicode, khoảng trắng hoặc chữ hoa/thường, hãy thực hiện theo quy tắc nghiệp vụ trước khi đưa dữ liệu vào context.

## 8. Kiểm soát auto-grow cho null reference và collection

SpEL có thể được cấu hình để tự tạo object khi gặp tham chiếu null hoặc tự mở rộng collection khi truy cập index vượt kích thước hiện tại. Những tính năng này tiện cho data binding, nhưng có thể làm tăng lượng object hoặc phần tử được tạo.

Nếu rule chỉ cần đọc dữ liệu, thường nên tắt cả hai:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    false,
                    false,
                    128);

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

Hai cờ đầu lần lượt tắt auto-grow null references và auto-grow collections. Tham số 128 là giới hạn auto-grow tối đa nếu tính năng được bật trong một use case khác.

Trong phiên bản Spring có constructor nhận cả maximumExpressionLength, có thể kết hợp hai loại giới hạn trong một cấu hình:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.OFF,
                    getClass().getClassLoader(),
                    false,
                    false,
                    128,
                    4_000);

Không bật auto-grow chỉ để tránh null hoặc index lỗi trong rule. Hãy xác định dữ liệu hợp lệ ở tầng ứng dụng và xử lý null rõ ràng. Nếu một use case data binding thực sự cần auto-grow, hãy giới hạn kích thước tối đa và kiểm thử các index lớn, âm hoặc ngoài phạm vi.

## 9. Không ghép dữ liệu bên ngoài vào expression source

Một lỗi thiết kế thường gặp là tạo expression bằng cách nối chuỗi với dữ liệu request:

    String source =
            "customerCode == '" + suppliedCode + "'";

    Expression expression =
            parser.parseExpression(source);

Cách làm này khiến dữ liệu đầu vào trở thành một phần cú pháp SpEL. Dấu nháy hoặc ký tự đặc biệt có thể làm thay đổi ý nghĩa expression; đồng thời mỗi giá trị khác nhau tạo ra một chuỗi cần parse và cache riêng.

Hãy parse một expression cố định và truyền dữ liệu bằng biến:

    Expression expression =
            parser.parseExpression(
                    "customerCode == #suppliedCode");

    StandardEvaluationContext context =
            new StandardEvaluationContext(input);

    context.setVariable("suppliedCode", suppliedCode);

    Boolean matches =
            expression.getValue(context, Boolean.class);

Expression source giờ ổn định, còn suppliedCode được xử lý như dữ liệu. Vẫn cần giới hạn độ dài và xác thực suppliedCode theo nghiệp vụ, nhưng dữ liệu không thể tự biến thành toán tử hoặc cú pháp SpEL.

## 10. Giới hạn số lượng expression và cache

Ngay cả khi từng expression đều ngắn, một hệ thống có thể bị tiêu tốn bộ nhớ nếu nhận vô hạn rule khác nhau và giữ mọi Expression trong cache.

Ví dụ, cache không giới hạn theo source:

    Map<String, Expression> expressionCache =
            new ConcurrentHashMap<>();

Nếu mỗi request gửi một chuỗi mới, cache có thể tăng liên tục. Điều này tạo rủi ro memory exhaustion dù từng expression đều nằm dưới ngưỡng độ dài.

Nên áp dụng:

- Giới hạn số rule hoạt động theo tenant hoặc ứng dụng.
- Chỉ parse expression đã được xác thực và có quyền lưu.
- Dùng cache có giới hạn dung lượng và chính sách loại bỏ.
- Parse lại khi rule thay đổi có kiểm soát, không parse lại trong mỗi request.
- Không cache EvaluationContext chứa root object hoặc biến riêng của request.
- Theo dõi kích thước cache, tỷ lệ hit/miss và số lần parse.

Nếu rule có vòng đời cấu hình, có thể parse khi nạp rule và lưu Expression cùng rule ID. Khi rule bị xóa hoặc thay đổi, cập nhật registry/cache tương ứng để tránh giữ expression cũ mãi mãi.

## 11. Giới hạn chi phí của method và function

Expression có thể ngắn nhưng gọi method tốn thời gian:

    customer.loadFullProfile()

Hoặc function có thể thực hiện truy vấn, I/O hay vòng lặp lớn. Giới hạn độ dài expression không kiểm soát được chi phí bên trong method.

Đối với rule chỉ đọc:

- Không đưa service hoặc repository vào root object.
- Chỉ đăng ký function có đầu vào/đầu ra rõ ràng.
- Ưu tiên function thuần, không thực hiện I/O hoặc side effect.
- Giới hạn số phần tử mà function nhận và trả về.
- Tránh method có thể tải object graph lớn hoặc thực hiện truy vấn không giới hạn.
- Không cho expression không đáng tin cậy gọi method tùy ý.

SpEL không cung cấp một timeout tổng quát để dừng an toàn mọi expression đang chạy. Chạy expression trên executor riêng không tự tạo sandbox; việc interrupt thread không bảo đảm dừng được mã Java hoặc I/O bên trong method. Cách kiểm soát chính là giới hạn cú pháp, dữ liệu và capability trước khi đánh giá.

## 12. Kiểm soát độ sâu và cấu trúc expression

Giới hạn độ dài làm giảm kích thước đầu vào nhưng không trực tiếp mô tả độ sâu lồng nhau hoặc số thao tác. Một chuỗi tương đối ngắn vẫn có thể chứa nhiều dấu ngoặc, toán tử hoặc collection lồng nhau.

Nếu rule đến từ nguồn bên ngoài, có thể xác định một tập cú pháp cho phép, ví dụ:

- Literal, so sánh và toán tử boolean.
- Property path trên DTO được chọn.
- Một số biến có tên cố định.
- Một số function thuần đã đăng ký.
- Selection/projection chỉ trên collection đã giới hạn.

Từ chối hoặc không hỗ trợ các cấu trúc ngoài hợp đồng của use case. Nếu cần phân tích cấu trúc sâu hơn, hãy xây validation layer hoặc DSL có grammar riêng; không dùng regex đơn giản để cố phân tích đầy đủ cú pháp SpEL.

Không nên giả định maximumExpressionLength là giới hạn AST depth, số node, CPU hoặc số lần gọi method. Đây là giới hạn độ dài chuỗi đầu vào. Các ngân sách khác phải được kiểm soát riêng ở ứng dụng.

## 13. Giới hạn template và kết quả đầu ra

Với template expression, cần giới hạn toàn bộ template source, số expression segment và dữ liệu được thay vào từng segment.

Ví dụ:

    "Hello, #{#userName}. Order: #{#orderNumber}"

Dù các segment ngắn, kết quả có thể lớn nếu biến userName hoặc orderNumber chứa chuỗi rất dài. Hãy giới hạn kích thước từng trường trước khi render và giới hạn tổng độ dài kết quả nếu template được gửi qua email, ghi log hoặc trả về API.

Không dùng template SpEL để ghép tùy ý những payload lớn hoặc nội dung không đáng tin cậy. Nếu mục tiêu chỉ là thay thế placeholder văn bản, một template engine hoặc formatter đơn giản có thể phù hợp hơn và dễ giới hạn hơn.

Nếu kết quả được ghi vào database hoặc truyền qua mạng, hãy áp dụng giới hạn theo byte/encoding ở tầng đầu ra, vì số ký tự và số byte không phải lúc nào cũng bằng nhau.

## 14. Xử lý khi vượt giới hạn

Khi expression hoặc dữ liệu vượt ngưỡng, hãy từ chối sớm với lỗi có thể hiểu được. Không âm thầm cắt chuỗi, bỏ bớt phần tử hoặc tiếp tục đánh giá một phần dữ liệu nếu điều đó có thể làm thay đổi ý nghĩa nghiệp vụ.

Ví dụ:

    if (source.length() > MAX_EXPRESSION_LENGTH) {
        throw new RuleValidationException(
                "Rule expression is too long");
    }

    if (input.lines().size() > MAX_LINES) {
        throw new RuleValidationException(
                "Rule input contains too many lines");
    }

Ở tầng API, ánh xạ lỗi validation sang phản hồi phù hợp và không trả stack trace nội bộ. Với rule được nạp từ cấu hình, ghi nhận rule ID và lý do bị từ chối để người quản trị sửa cấu hình.

Nếu parser ném SpelParseException do cú pháp hoặc giới hạn parser, hãy giữ thông tin vị trí lỗi cần thiết để chẩn đoán. Tránh log toàn bộ expression hoặc dữ liệu đầu vào nếu có thể chứa secret hay thông tin cá nhân.

## 15. Kiểm thử các ranh giới kích thước

Kiểm thử giới hạn cần tập trung vào các điểm ngay dưới, đúng bằng và ngay trên ngưỡng.

Các trường hợp nên có:

- Expression rỗng hoặc chỉ chứa khoảng trắng.
- Expression có độ dài nhỏ hơn giới hạn.
- Expression có độ dài đúng bằng giới hạn.
- Expression dài hơn giới hạn một đơn vị.
- Chuỗi Unicode có ký tự ngoài ASCII.
- Template có nhiều expression segment.
- Property string ở sát giới hạn độ dài.
- Collection rỗng, collection ở đúng ngưỡng và collection vượt ngưỡng.
- Map có nhiều entry.
- Nested collection có tổng số phần tử lớn.
- Index lớn khi auto-grow bị tắt hoặc được giới hạn.
- Projection tạo kết quả gần giới hạn đầu ra.
- Regex hoặc function có thể tốn nhiều thời gian.

Ví dụ test cho giới hạn ở tầng ứng dụng:

    @Test
    void rejectsExpressionAboveConfiguredLimit() {
        String source =
                "1".repeat(MAX_EXPRESSION_LENGTH + 1);

        assertThrows(
                RuleValidationException.class,
                () -> ruleParser.parse(source));
    }

Nên kiểm thử cả trường hợp hợp lệ ở đúng ngưỡng để tránh đặt giới hạn quá thấp hoặc có lỗi off-by-one.

## 16. Theo dõi tài nguyên khi vận hành

Các metric hữu ích gồm:

- Độ dài expression được nhận và số expression bị từ chối.
- Thời gian parse và số lần parse theo rule ID.
- Thời gian evaluate và số lần đánh giá.
- Kích thước collection/map đầu vào.
- Độ dài chuỗi và kết quả đầu ra.
- Số lượng Expression trong cache và tỷ lệ hit/miss.
- Tỷ lệ SpelParseException và SpelEvaluationException.
- CPU, allocation và heap khi xử lý các nhóm rule lớn.

Dùng rule ID hoặc nhóm rule để phân loại metric. Không gắn toàn bộ expression, root object hoặc payload nhạy cảm vào label metric vì có thể làm lộ dữ liệu và tạo cardinality rất lớn.

Khi có latency tăng, kiểm tra đồng thời expression source, kích thước dữ liệu và method/function được gọi. Một rule ngắn vẫn có thể chậm vì getter truy vấn database hoặc collection đầu vào tăng đột biến.

## 17. Những sai lầm thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
|---|---|---|
| Chỉ giới hạn độ dài expression | Dữ liệu collection/string vẫn có thể rất lớn | Đặt giới hạn riêng cho dữ liệu |
| Nối request value vào expression source | Dữ liệu có thể thay đổi cú pháp và tạo nhiều expression | Dùng biến hoặc root DTO |
| Dùng cache không giới hạn | Mỗi expression mới làm tăng bộ nhớ | Dùng cache bounded và giới hạn số rule |
| Bật auto-grow cho mọi rule | Có thể tạo object/collection ngoài nhu cầu | Tắt mặc định hoặc đặt maximumAutoGrowSize |
| Cho phép collection không giới hạn | Selection/projection có thể xử lý lượng lớn phần tử | Giới hạn dữ liệu trước khi đánh giá |
| Dùng method có I/O trong expression | Chi phí không thể suy ra từ độ dài expression | Chỉ cung cấp function hẹp, thuần và có ngân sách |
| Xem parser length limit là timeout | Giới hạn chuỗi không giới hạn CPU lúc evaluate | Kiểm soát dữ liệu và capability |
| Cắt bớt expression vượt ngưỡng | Có thể biến đổi ý nghĩa rule | Từ chối và yêu cầu sửa cấu hình |

## Kết luận

Giới hạn kích thước expression là một lớp bảo vệ cần thiết, nhưng không đủ để kiểm soát toàn bộ chi phí SpEL. Hãy giới hạn expression source, số lượng rule, kích thước string, collection/map, độ sâu dữ liệu và kết quả đầu ra. Với phiên bản Spring hỗ trợ, cấu hình maximumExpressionLength; với phiên bản cũ hơn, kiểm tra độ dài ở tầng ứng dụng. Tắt auto-grow nếu rule chỉ đọc và đặt maximumAutoGrowSize khi use case thực sự cần tự mở rộng.

Giữ expression ổn định và truyền dữ liệu qua biến hoặc DTO đã xác thực. Chỉ cung cấp method/function có phạm vi hẹp, cache Expression có giới hạn, từ chối đầu vào vượt ngưỡng và đo cả thời gian parse lẫn evaluate. Những giới hạn này cần được chọn theo tải thực tế và kiểm thử tại ranh giới để rule không thể vô tình tiêu thụ tài nguyên vượt ngân sách ứng dụng.
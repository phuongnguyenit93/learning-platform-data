# Hiệu năng warm-up và chi phí biên dịch

Hiệu năng của SpEL không chỉ phụ thuộc vào độ phức tạp của biểu thức. Thời gian xử lý còn chịu ảnh hưởng của việc parse chuỗi, tạo EvaluationContext, đánh giá biểu thức lần đầu, biên dịch biểu thức sang bytecode và quá trình JVM tối ưu mã đang chạy. Nếu chỉ đo một lần gọi getValue(), rất dễ nhầm chi phí khởi động với chi phí xử lý ổn định.

SpEL mặc định đánh giá biểu thức bằng interpreter. Với biểu thức được dùng lặp lại và có kiểu dữ liệu ổn định, có thể bật SpEL compiler để tạo bytecode và giảm chi phí đánh giá. Tuy nhiên, biên dịch cũng có chi phí riêng, chỉ hỗ trợ một tập biểu thức nhất định và dựa trên thông tin kiểu thu được khi chạy. Vì vậy, cần đo riêng từng giai đoạn và chọn chế độ compiler theo cách ứng dụng thực sự sử dụng biểu thức.

## 1. Những thành phần tạo nên thời gian xử lý

Một luồng xử lý SpEL thường có các giai đoạn:

1. Tạo hoặc cấu hình ExpressionParser.
2. Parse chuỗi thành đối tượng Expression và cây cú pháp nội bộ.
3. Chuẩn bị EvaluationContext cùng root object, biến và resolver cần thiết.
4. Gọi getValue() để đánh giá biểu thức.
5. Nếu bật compiler, SpEL có thể tạo mã bytecode từ biểu thức sau một hoặc nhiều lần đánh giá diễn giải.
6. JVM tiếp tục có thể tối ưu bytecode được thực thi thường xuyên bằng JIT compiler của JVM.

Các giai đoạn này có chi phí và vòng đời khác nhau. Parse là công việc xử lý chuỗi và cấu trúc cú pháp. Evaluation là công việc thực hiện biểu thức trên dữ liệu hiện tại. SpEL compilation tạo một lớp bytecode để thực hiện biểu thức. JVM JIT tối ưu mã bytecode đang chạy trong tiến trình.

Không nên gộp tất cả thành một con số “thời gian SpEL”. Khi một biểu thức chậm, cần biết thời gian nằm ở parse, khởi tạo context, đánh giá bằng interpreter, compilation hay logic getter/method của chính ứng dụng.

## 2. Parse expression và evaluate expression là hai chi phí khác nhau

ExpressionParser chuyển chuỗi SpEL thành một Expression. Việc parse thường nên thực hiện một lần khi nạp cấu hình hoặc khi rule được tạo, sau đó tái sử dụng Expression cho nhiều lần đánh giá.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("order.total > 1000");

    for (Order order : orders) {
        Boolean accepted =
                expression.getValue(
                        order, Boolean.class);
    }

Trong ví dụ, parser chỉ parse một lần. Mỗi vòng lặp chỉ đánh giá Expression với root object khác nhau.

Nếu parse bên trong vòng lặp:

    for (Order order : orders) {
        Expression expression =
                parser.parseExpression("order.total > 1000");

        Boolean accepted =
                expression.getValue(
                        order, Boolean.class);
    }

ứng dụng phải trả chi phí parse lặp lại dù chuỗi biểu thức không đổi. Khi một rule được dùng nhiều lần, chi phí này có thể lớn hơn phần tiết kiệm mà compiler mang lại.

Expression đã parse có thể được cache theo nội dung và cấu hình parser. Cache cần có giới hạn kích thước nếu biểu thức được tạo từ cấu hình động hoặc người dùng; không nên giữ vô hạn mọi chuỗi từng xuất hiện. Cần cache Expression, không nên mặc định cache một EvaluationContext chứa root object hoặc biến của request.

## 3. Interpreter là chế độ mặc định

Khi không cấu hình compiler, SpEL đánh giá expression bằng interpreter. Interpreter duyệt cây biểu thức và thực hiện các phép toán, truy cập property hoặc gọi method theo ngữ cảnh hiện tại.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression(
                    "customer.address.city");

    String city =
            expression.getValue(order, String.class);

Cách đánh giá này linh hoạt và là lựa chọn mặc định. Nó phù hợp với biểu thức ít được gọi, biểu thức có cấu trúc động hoặc trường hợp chưa có bằng chứng cho thấy chi phí đánh giá là nút thắt.

Interpreter vẫn có thể chạy nhanh cho biểu thức đơn giản. Không nên bật compiler chỉ vì một biểu thức có nhiều dấu chấm hoặc nhìn có vẻ dài. Hãy đo trên dữ liệu và tải thực tế, vì chi phí truy cập object, getter, collection và chuyển đổi kiểu có thể chi phối tổng thời gian.

## 4. SpEL compiler làm gì?

SpEL compiler chuyển một số expression đã parse thành bytecode JVM. Thay vì diễn giải cây biểu thức ở mỗi lần gọi, mã được biên dịch thực hiện các thao tác tương ứng trực tiếp hơn.

Compiler có thể giảm overhead đánh giá đối với biểu thức được gọi lặp lại, đặc biệt khi đường đi qua các property và kiểu dữ liệu ổn định. Nó không làm giảm chi phí đọc dữ liệu từ database, gọi mạng, chạy getter tốn thời gian hoặc thực hiện logic nghiệp vụ bên trong method.

SpEL compilation cũng không giống JVM JIT compilation:

- SpEL compiler nhận cây cú pháp SpEL và tạo bytecode thực thi expression.
- JVM JIT tối ưu bytecode của ứng dụng và bytecode được tạo trong lúc chạy dựa trên hành vi thực tế của tiến trình.

Hai cơ chế có thể cùng xuất hiện. Một expression được SpEL compiler biên dịch vẫn có thể được JVM JIT tối ưu thêm sau khi được thực thi đủ thường xuyên.

Compiler không bảo đảm mọi expression đều có thể biên dịch. Các tính năng phụ thuộc resolver tùy chỉnh, chuyển đổi động hoặc cấu trúc biểu thức không được hỗ trợ có thể tiếp tục cần interpreter. Phạm vi hỗ trợ thay đổi theo phiên bản Spring; hãy kiểm tra phiên bản đang dùng và thử với chính expression của ứng dụng.

## 5. Ba chế độ SpelCompilerMode

Có thể chọn chế độ compiler qua SpelParserConfiguration:

- OFF: tắt SpEL compilation. Đây là chế độ mặc định.
- IMMEDIATE: SpEL cố gắng biên dịch expression sớm sau lần đánh giá diễn giải đầu tiên.
- MIXED: expression bắt đầu ở chế độ diễn giải; sau khi đạt ngưỡng đánh giá nội bộ, SpEL thử biên dịch. Nếu expression đã biên dịch gặp vấn đề lúc chạy, chế độ MIXED có thể quay lại diễn giải.

Ví dụ bật MIXED:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.MIXED,
                    MyService.class.getClassLoader());

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

    Expression expression =
            parser.parseExpression(
                    "customer.address.city");

ClassLoader được truyền vào là loader dùng để định nghĩa lớp bytecode được tạo. Dùng loader phù hợp với ứng dụng và vòng đời triển khai. Nếu không cần compilation, có thể giữ cấu hình mặc định hoặc đặt OFF rõ ràng để thể hiện ý định.

Ngưỡng chuyển từ interpreter sang compiler trong MIXED là chi tiết triển khai của Spring, không nên xem là một con số cố định để thiết kế logic ứng dụng. Không viết mã phụ thuộc vào số lần đánh giá chính xác trước khi compilation xảy ra.

## 6. Chọn OFF, IMMEDIATE hay MIXED?

| Chế độ | Hành vi | Phù hợp khi |
|---|---|---|
| OFF | Luôn đánh giá bằng interpreter | Biểu thức ít dùng, động hoặc chưa cần tối ưu |
| IMMEDIATE | Thử biên dịch sau lần diễn giải đầu tiên | Kiểu dữ liệu và cấu trúc expression ổn định, được kiểm soát |
| MIXED | Bắt đầu bằng interpreter, sau đó thử compile; có thể quay lại interpreter nếu compiled expression lỗi | Rule dùng lặp lại nhưng dữ liệu runtime có khả năng thay đổi kiểu |

OFF là lựa chọn an toàn để làm mốc đo và là lựa chọn hợp lý nếu compilation không đem lại lợi ích rõ ràng.

IMMEDIATE có thể hữu ích cho rule có kiểu dữ liệu ổn định, chẳng hạn biểu thức đọc một DTO có cấu trúc cố định. Vì compilation xảy ra sớm, giai đoạn khởi động hoặc request đầu có thể chịu thêm chi phí.

MIXED hữu ích khi muốn SpEL tự chuyển đổi giữa diễn giải và biên dịch. Tuy nhiên, khả năng quay lại interpreter không loại bỏ nhu cầu kiểm thử kiểu dữ liệu. Nếu kiểu thay đổi liên tục, compiler có thể không đem lại lợi ích ổn định.

## 7. Ví dụ cấu hình parser với compiler

Có thể tạo parser dùng IMMEDIATE:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.IMMEDIATE,
                    OrderRuleService.class.getClassLoader());

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

    Expression expression =
            parser.parseExpression(
                    "total >= minimumTotal");

    Boolean result =
            expression.getValue(
                    orderRuleInput, Boolean.class);

Hoặc tạo parser dùng MIXED:

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.MIXED,
                    OrderRuleService.class.getClassLoader());

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

Cấu hình compiler được áp dụng cho expression được parse bởi parser đó. Nếu ứng dụng có nhiều nhóm rule, có thể dùng parser/configuration riêng cho từng nhóm thay vì thay đổi chế độ toàn cục hoặc tạo parser mới theo từng request.

Đừng tạo parser và SpelParserConfiguration mới trong mỗi lần getValue(). Hãy tạo parser theo vòng đời ứng dụng hoặc theo nhóm cấu hình, parse rule khi nạp và tái sử dụng Expression.

## 8. Warm-up là gì?

Warm-up là giai đoạn đưa đường chạy vào trạng thái gần với vận hành ổn định trước khi đo hoặc phục vụ tải thực tế. Với SpEL, warm-up có thể bao gồm:

- Nạp cấu hình và parse các expression cần thiết.
- Đánh giá thử bằng interpreter.
- Cho SpEL compiler cơ hội biên dịch nếu chế độ được bật.
- Thực thi thêm để JVM JIT có cơ hội tối ưu mã.
- Chuẩn bị cache hoặc dữ liệu phụ thuộc mà biểu thức truy cập.

Warm-up không đồng nghĩa với chỉ gọi getValue() một lần. Lần gọi đầu có thể chịu chi phí khởi tạo class, tải class, tạo context, parse expression hoặc compilation. JVM JIT cũng cần thời gian quan sát đường chạy trước khi tối ưu.

Nếu hệ thống nhạy với độ trễ request đầu tiên, có thể nạp và warm-up một tập expression đã biết trong quá trình khởi động. Việc warm-up phải dùng dữ liệu thử an toàn và không gây side effect.

## 9. Tách cold-start latency và steady-state latency

Cold-start latency là độ trễ trong giai đoạn đầu, khi parser, expression, class hoặc compiler chưa được sử dụng. Steady-state latency là độ trễ sau khi hệ thống đã khởi tạo và thực thi đủ nhiều.

Hai con số trả lời hai câu hỏi khác nhau:

- Người dùng đầu tiên sau khi triển khai có phải chờ lâu không?
- Khi hệ thống đã chạy ổn định, mỗi lần đánh giá expression tốn bao nhiêu?

Một chế độ compiler có thể làm tăng chi phí ban đầu nhưng giảm chi phí cho các lần đánh giá tiếp theo. Với biểu thức chỉ chạy một vài lần, tổng chi phí có thể cao hơn chế độ OFF. Với biểu thức chạy hàng triệu lần và có kiểu ổn định, chi phí biên dịch có thể được bù lại.

Khi báo cáo hiệu năng, hãy ghi riêng thời gian parse, thời gian đánh giá đầu tiên, thời gian compilation nếu quan sát được, và phân phối latency sau warm-up. Đừng chỉ lấy trung bình của tất cả lần gọi vì nó che mất giai đoạn khởi động và các đuôi latency.

## 10. Chi phí compilation và điểm hòa vốn

Biên dịch expression tiêu tốn CPU và bộ nhớ. SpEL phải tạo bytecode, định nghĩa lớp và có thể phải thực hiện thêm công việc khi kiểu runtime thay đổi. Vì vậy, compilation chỉ có lợi khi phần overhead tiết kiệm được trên các lần đánh giá sau đủ bù chi phí ban đầu.

Có thể mô tả đơn giản:

    Total cost =
        parse cost
        + evaluation cost
        + compilation cost
        + later compiled evaluation cost

Với OFF, phần compilation cost bằng không nhưng mỗi lần đánh giá tiếp tục dùng interpreter.

Với IMMEDIATE hoặc MIXED, có thể phát sinh compilation cost; đổi lại, những lần đánh giá sau có thể rẻ hơn nếu expression được hỗ trợ và kiểu ổn định.

Điểm hòa vốn phụ thuộc vào expression, dữ liệu, số lần gọi, phiên bản Spring, JVM và phần cứng. Không có một số lần gọi chung phù hợp cho mọi ứng dụng. Hãy đo tổng chi phí trong một khoảng vận hành thực tế thay vì chỉ so sánh một lần gọi compiled với một lần gọi interpreted.

## 11. Kiểu dữ liệu ổn định ảnh hưởng đến compilation

SpEL compiler sử dụng thông tin kiểu thu được trong quá trình đánh giá để tạo mã. Nếu một property lúc đầu trả về String nhưng về sau trả về một kiểu không tương thích, mã đã biên dịch có thể không còn phù hợp.

Ví dụ một expression đọc:

    customer.address.city

Nếu customer luôn có cùng kiểu, address luôn có kiểu cụ thể và city luôn là String, compiler có thể tạo mã hiệu quả hơn. Nếu object graph thay đổi kiểu theo request hoặc property có kiểu runtime rất khác nhau, compilation có thể thất bại hoặc expression đã biên dịch không chạy được với dữ liệu mới.

Các điểm cần kiểm soát:

- Dùng DTO và kiểu property ổn định cho rule được biên dịch.
- Tránh thay đổi kiểu trả về của getter giữa các lần đánh giá.
- Tránh tái sử dụng một expression với nhiều root object không cùng cấu trúc.
- Kiểm thử với các giá trị biên và các kiểu runtime thực tế.
- Chọn MIXED nếu cần khả năng quay lại interpreter khi compiled expression không còn phù hợp.

MIXED giúp tăng khả năng chịu thay đổi kiểu so với IMMEDIATE, nhưng không thay thế việc thiết kế hợp đồng kiểu dữ liệu rõ ràng.

## 12. Giới hạn của SpEL compiler

SpEL compiler không hỗ trợ toàn bộ ngôn ngữ SpEL. Một số biểu thức có thể không biên dịch được do cấu trúc, resolver tùy chỉnh, chuyển đổi kiểu hoặc tính năng động mà compiler không thể biểu diễn an toàn.

Các tình huống cần kiểm tra kỹ gồm:

- Selection và projection trên collection.
- Phép chuyển đổi dựa vào ConversionService.
- Method hoặc property được xử lý bởi resolver/accessor tùy chỉnh.
- Biểu thức có kiểu runtime thay đổi giữa các lần đánh giá.
- Cấu trúc động phụ thuộc vào dữ liệu hoặc object graph không ổn định.

Đây là các ví dụ cần kiểm tra, không phải danh sách đầy đủ hoặc cam kết rằng mọi phiên bản Spring đều có cùng giới hạn. Hãy kiểm tra tài liệu và mã nguồn đúng phiên bản Spring mà ứng dụng đang sử dụng.

Nếu expression không thể biên dịch, ứng dụng cần tiếp tục hoạt động đúng với interpreter hoặc dùng chế độ compiler phù hợp. Không thiết kế nghiệp vụ phụ thuộc vào giả định rằng mọi expression đều sẽ được biên dịch thành công.

## 13. Parser, Expression và EvaluationContext nên có vòng đời khác nhau

Một mô hình thường dùng là:

- Parser/configuration: tạo theo vòng đời ứng dụng hoặc theo nhóm rule.
- Expression: parse một lần và cache theo rule.
- EvaluationContext: tạo hoặc chuẩn bị riêng cho lần đánh giá, với root object và biến của request.
- Root object: chỉ chứa dữ liệu cần thiết cho rule hiện tại.

Ví dụ:

    public class RuleEvaluator {

        private final Expression expression;

        public RuleEvaluator() {
            SpelParserConfiguration config =
                    new SpelParserConfiguration(
                            SpelCompilerMode.MIXED,
                            getClass().getClassLoader());

            ExpressionParser parser =
                    new SpelExpressionParser(config);

            this.expression =
                    parser.parseExpression(
                            "total >= #minimumTotal");
        }

        public boolean evaluate(
                OrderRuleInput input,
                BigDecimal minimumTotal) {

            StandardEvaluationContext context =
                    new StandardEvaluationContext(input);

            context.setVariable(
                    "minimumTotal", minimumTotal);

            return Boolean.TRUE.equals(
                    expression.getValue(
                            context, Boolean.class));
        }
    }

Ví dụ minh họa việc tái sử dụng Expression và tạo context cho từng lần gọi. Trong ứng dụng thực tế, cần chọn loại context và resolver phù hợp với quyền mà rule cần. Không chia sẻ một context mutable giữa các request đồng thời nếu mỗi request cập nhật root hoặc biến.

## 14. Thiết kế warm-up an toàn

Nếu muốn warm-up expression trong lúc khởi động, hãy xác định danh sách rule cần thiết và chuẩn bị dữ liệu thử đại diện.

Một quy trình có thể gồm:

1. Nạp các rule được cấu hình và kiểm tra cú pháp.
2. Parse từng rule bằng parser/configuration sẽ dùng khi chạy.
3. Đánh giá với fixture chỉ đọc có kiểu dữ liệu tương ứng.
4. Nếu bật compiler, cho expression đi qua số lần đánh giá cần thiết để chế độ đã chọn thử compilation.
5. Ghi nhận lỗi parse, lỗi evaluate hoặc lỗi compilation theo rule.
6. Chỉ đưa rule hợp lệ vào registry phục vụ request.

Không dùng đơn hàng thật, object mutable dùng chung hoặc dữ liệu có thể gây gửi email, ghi database hay thay đổi trạng thái để warm-up. Nếu expression có function hoặc getter có side effect, warm-up có thể thực hiện hành động ngoài ý muốn.

Với MIXED, không nên hard-code số lần warm-up dựa trên ngưỡng nội bộ của Spring. Có thể thực thi một số lần trên fixture an toàn, nhưng cần kiểm tra hành vi thực tế của phiên bản framework và không coi việc gọi đủ N lần là bằng chứng chắc chắn expression đã compiled.

## 15. Đo hiệu năng đúng cách

Benchmark cần tách các kịch bản để kết quả có ý nghĩa:

- Parse-only: đo chi phí tạo Expression từ chuỗi.
- Evaluate interpreted: dùng parser OFF và Expression đã parse.
- Evaluate compiled: dùng IMMEDIATE hoặc MIXED, cho warm-up phù hợp rồi đo steady state.
- End-to-end: bao gồm lấy dữ liệu, tạo context, đánh giá và các thao tác mà request thực sự thực hiện.

Nên dùng JMH cho microbenchmark Java thay vì viết vòng lặp đơn giản với System.nanoTime(). JMH hỗ trợ warm-up iteration, measurement iteration, fork JVM và giảm các sai lệch do JIT, dead-code elimination hoặc constant folding.

Một số nguyên tắc:

- Dùng cùng dữ liệu đầu vào và cùng logic expression khi so sánh chế độ.
- Không tính parse cost vào một bên nhưng bỏ khỏi bên còn lại.
- Đưa kết quả ra Blackhole hoặc sử dụng kết quả để tránh JVM loại bỏ công việc.
- Dùng nhiều fork và báo cáo phân vị hoặc phân phối, không chỉ một giá trị trung bình.
- Đo cả throughput và latency nếu hệ thống cần cả hai.
- Benchmark với object graph và kiểu dữ liệu giống production.
- Đo riêng biểu thức đơn giản và biểu thức có getter/method tốn thời gian.
- Không chạy benchmark trong lúc CPU hoặc hệ thống khác đang gây nhiễu mà không ghi nhận điều kiện.

Nếu expression chỉ chiếm một phần nhỏ thời gian request, benchmark micro có thể cho thấy cải thiện lớn nhưng tác động end-to-end gần như không đáng kể. Hãy kiểm tra cả hai mức.

## 16. Quan sát trong production

Khi triển khai compiler, nên theo dõi các chỉ số liên quan:

- Số expression được parse và số lần parse lặp lại.
- Số lần đánh giá và latency theo nhóm rule.
- Tỷ lệ lỗi parse/evaluate.
- Tỷ lệ rule được sử dụng đủ thường xuyên để có cơ hội compile.
- Lỗi khi expression đã biên dịch chạy với dữ liệu runtime.
- CPU, allocation và thời gian khởi động sau khi thay đổi compiler mode.

Không nên ghi toàn bộ expression hoặc dữ liệu root vào log nếu chúng chứa thông tin nhạy cảm. Dùng rule ID hoặc tên cấu hình đã được kiểm soát để gắn metric.

Có thể dùng Java Flight Recorder, profiler hoặc tracing để xác định thời gian đang nằm ở parser, SpEL, getter, method nghiệp vụ hay hệ thống bên ngoài. Đừng quy mọi latency cao cho interpreter trước khi đo.

Nếu có thể, triển khai thay đổi compiler mode theo từng nhóm rule hoặc môi trường, so sánh với baseline OFF và có khả năng quay lại cấu hình cũ khi lỗi hoặc latency tăng.

## 17. Lỗi và nhầm lẫn thường gặp

| Tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Bật compiler nhưng không thấy cải thiện | Expression ít được gọi hoặc phần tốn thời gian nằm ở getter/I/O | Đo số lần gọi và profile toàn luồng |
| Request đầu chậm hơn | Parse, class loading hoặc compilation diễn ra lúc khởi động/lần đầu | Nạp rule và warm-up an toàn trước khi nhận tải |
| Expression không biên dịch được | Cấu trúc nằm ngoài tập compiler hỗ trợ | Dùng interpreter hoặc viết lại rule phù hợp |
| Compiled expression lỗi với dữ liệu mới | Kiểu runtime thay đổi so với lúc compile | Ổn định DTO/type hoặc dùng MIXED |
| Benchmark cho kết quả thất thường | Đo lẫn parse, warm-up, JIT và evaluation | Tách giai đoạn và dùng JMH |
| Parse lại trong mỗi request | Không tái sử dụng Expression | Cache Expression theo rule |
| Cache tăng không giới hạn | Biểu thức động sinh nhiều khóa | Dùng cache có giới hạn và chính sách loại bỏ |
| Warm-up gây thay đổi dữ liệu | Function/getter có side effect | Dùng fixture an toàn và biểu thức thuần |
| Dùng chung EvaluationContext giữa request | Context mutable chứa root/variables | Tạo context theo lần đánh giá |

## Kết luận

SpEL mặc định dùng interpreter. Có thể bật compiler với OFF, IMMEDIATE hoặc MIXED thông qua SpelParserConfiguration, nhưng lợi ích chỉ xuất hiện khi expression được dùng đủ thường xuyên, được hỗ trợ bởi compiler và có kiểu runtime ổn định. Compilation có chi phí CPU, bộ nhớ và độ trễ ban đầu; nó không loại bỏ chi phí parse, I/O hoặc logic getter.

Hãy parse và cache Expression thay vì parse theo từng request, tách cold-start khỏi steady-state, warm-up bằng dữ liệu an toàn, benchmark bằng JMH và theo dõi latency cùng lỗi trong production. Chọn compiler mode dựa trên phép đo của chính rule và phiên bản Spring đang chạy; giữ OFF khi compilation không tạo ra lợi ích thực tế.
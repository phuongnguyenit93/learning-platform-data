# Đo đạc trước khi bật compiler

## Mục tiêu

Sau bài này, bạn có thể xác định khi nào Spring Expression Language (SpEL) compiler thực sự mang lại lợi ích; thiết lập đường cơ sở ở chế độ interpreted; đo riêng chi phí parse, đánh giá và biên dịch; so sánh các chế độ OFF, IMMEDIATE và MIXED; và chọn workload đại diện để benchmark. Bạn cũng sẽ biết cách theo dõi độ trễ, throughput, cấp phát bộ nhớ, tính ổn định kiểu dữ liệu và lỗi sau khi bật compiler; triển khai có kiểm soát; và quay lại interpreted mode khi kết quả không đạt yêu cầu.

## 1. Compiler không mặc nhiên làm mọi expression nhanh hơn

SpEL có thể đánh giá expression theo cách interpreted hoặc biên dịch expression thành bytecode để chạy trên JVM. Compiler có thể giảm chi phí đánh giá lặp lại đối với những expression phù hợp, nhưng nó không bảo đảm mọi expression đều nhanh hơn.

Một expression đơn giản được gọi rất ít lần có thể không thu hồi được chi phí biên dịch. Một expression phụ thuộc nhiều vào resolver, converter hoặc cấu trúc dữ liệu thay đổi có thể không được compiler hỗ trợ đầy đủ. Một expression chạy nhanh trong microbenchmark cũng chưa chắc cải thiện thời gian phản hồi của toàn request nếu phần lớn thời gian nằm ở database, network hoặc xử lý khác.

Vì vậy, trước khi bật compiler, cần trả lời bằng số liệu:

- Expression nào đang tiêu tốn thời gian đáng kể?
- Tần suất đánh giá của expression là bao nhiêu?
- Chi phí nằm ở parse, evaluate hay thao tác bên ngoài?
- Expression có cấu trúc và kiểu dữ liệu ổn định không?
- Chế độ compiler cải thiện throughput hoặc latency bao nhiêu?
- Chi phí khởi động, biên dịch và cấp phát có tăng không?
- Kết quả có đúng trong mọi trường hợp dữ liệu thực tế không?

Mục tiêu là tối ưu phần có ảnh hưởng đáng kể đến ứng dụng, không bật compiler chỉ vì tính năng đó tồn tại.

## 2. Hiểu ba chế độ compiler

SpEL cung cấp ba chế độ qua enum SpelCompilerMode:

| Chế độ | Hành vi |
|---|---|
| OFF | Không biên dịch expression; tiếp tục đánh giá theo interpreted mode |
| IMMEDIATE | Ưu tiên biên dịch expression khi compiler có thể thực hiện; lỗi khi chạy bản compiled cần được xem xét nghiêm túc |
| MIXED | Cho phép chuyển đổi giữa compiled và interpreted mode; khi bản compiled không còn chạy được do thay đổi điều kiện runtime, SpEL có thể quay lại interpreted mode |

Compiler bị tắt mặc định nếu ứng dụng không cấu hình chế độ khác.

OFF là baseline hữu ích để đo chi phí hiện tại. IMMEDIATE giúp đánh giá hiệu năng khi expression có thể được biên dịch và kiểu dữ liệu phù hợp với các giả định của compiler. MIXED có cơ chế linh hoạt hơn khi ứng dụng gặp thay đổi kiểu hoặc trường hợp compiled expression không còn phù hợp.

Tên chế độ không thay thế benchmark. Hãy kiểm tra hành vi trên đúng phiên bản Spring Framework mà ứng dụng đang chạy, vì chi tiết biên dịch và tập expression được hỗ trợ phụ thuộc phiên bản.

## 3. Tách parse, evaluate và compile thành các chi phí riêng

Một quy trình SpEL thường có các bước:

1. Tạo parser và cấu hình.
2. Parse chuỗi thành Expression.
3. Chuẩn bị EvaluationContext và dữ liệu.
4. Đánh giá expression.
5. Khi compiler được bật và expression phù hợp, SpEL có thể biên dịch expression sau quá trình đánh giá interpreted ban đầu.
6. Các lần đánh giá tiếp theo có thể sử dụng bản compiled.

Nếu benchmark parseExpression() và getValue() trong cùng một vòng lặp, kết quả sẽ trộn chi phí phân tích cú pháp với chi phí đánh giá. Trong ứng dụng thực tế, expression thường được parse một lần rồi tái sử dụng, nên phép đo đó có thể không phản ánh đúng workload production.

Hãy đo riêng:

- **Parse cost:** thời gian tạo Expression từ chuỗi.
- **Interpreted evaluation cost:** thời gian getValue() khi compiler OFF.
- **Compilation/warm-up cost:** chi phí ban đầu khi expression chuyển sang compiled mode.
- **Steady-state cost:** thời gian đánh giá sau khi expression đã đạt trạng thái chạy ổn định.
- **Context setup cost:** chi phí tạo EvaluationContext, đăng ký biến và root object nếu ứng dụng thực hiện việc này cho từng request.

Nếu production tái sử dụng Expression nhưng tạo context mới cho mỗi request, benchmark cần mô phỏng đúng vòng đời đó. Không đưa context setup vào phép đo evaluate nếu production không làm như vậy; cũng không bỏ qua nó nếu ứng dụng thực sự phải trả chi phí đó.

## 4. Thiết lập baseline ở chế độ OFF

Trước tiên, đo hành vi hiện tại với compiler OFF. Có thể cấu hình parser rõ ràng:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.OFF,
        getClass().getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Sau đó parse expression và đánh giá bằng context giống với cách ứng dụng đang sử dụng:

~~~java
Expression expression =
    parser.parseExpression("#order.total >= #minimum");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("order", order);
context.setVariable("minimum", minimum);

Boolean accepted =
    expression.getValue(context, Boolean.class);
~~~

Ghi lại baseline cho từng nhóm expression, không chỉ một expression đại diện duy nhất. Bao gồm expression đơn giản, expression truy cập property lồng nhau, biểu thức số học, điều kiện và những expression thực sự xuất hiện trong luồng xử lý.

Baseline cần có cả kết quả hiệu năng và kết quả chức năng. Nếu chỉ đo thời gian mà không xác nhận giá trị trả về, benchmark có thể vô tình so sánh hai cách xử lý không tương đương.

## 5. Bật compiler có cấu hình rõ ràng

Có thể cấu hình parser ở IMMEDIATE mode:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.IMMEDIATE,
        getClass().getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Hoặc dùng MIXED mode:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        getClass().getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

ClassLoader được truyền vào cấu hình là nơi compiler dùng để định nghĩa class được sinh ra. Trong ứng dụng có classloader tùy chỉnh, plugin hoặc môi trường hot reload, cần kiểm tra classloader phù hợp với các kiểu mà expression truy cập.

Hãy tạo parser theo cấu hình muốn đo. Không nên thay đổi một parser đang được dùng chung trong khi benchmark hoặc trong runtime mà không hiểu vòng đời của expression đã được parse từ parser đó.

Cũng cần nhớ compiler mode là cấu hình cho parser/expression được tạo ra. Đổi cấu hình ở một parser khác không tự thay đổi những Expression đã tồn tại.

## 6. Chọn expression đại diện cho workload thực tế

Một benchmark chỉ hữu ích khi expression đại diện cho cách ứng dụng đang chạy.

Nên chọn các nhóm:

- Đọc một property đơn giản từ root object.
- Đọc nhiều property lồng nhau.
- Tính toán số học trên các giá trị có kiểu ổn định.
- Kết hợp điều kiện boolean.
- Đọc biến trong EvaluationContext.
- Truy cập phần tử mảng hoặc List.
- Selection hoặc projection nếu ứng dụng thực sự sử dụng.
- Gọi method, converter hoặc accessor tùy chỉnh nếu chúng nằm trong luồng thực tế.

Không nên chỉ benchmark expression số học ngắn rồi kết luận toàn bộ SpEL workload sẽ được cải thiện. Compiler có thể hỗ trợ một số dạng AST tốt hơn những dạng khác.

Với từng expression, lưu lại chuỗi nguồn, kiểu root object, kiểu biến, kích thước collection, kiểu trả về và tần suất gọi. Những thông tin này giúp tái tạo benchmark và giải thích kết quả.

## 7. Đo bằng dữ liệu và kiểu thực tế

Expression có thể chạy trên nhiều object có cấu trúc khác nhau. Nếu benchmark chỉ dùng một object giả lập, kết quả có thể bỏ sót vấn đề kiểu dữ liệu.

Hãy chuẩn bị dữ liệu đại diện:

- Kiểu concrete của root object.
- Kiểu trả về thực tế của getter.
- Giá trị null nếu mô hình cho phép.
- Các kiểu con hoặc implementation khác nhau của interface.
- Collection có kích thước nhỏ, trung bình và lớn.
- Biến có kiểu và giá trị tương tự production.
- Các trường hợp biên mà expression phải xử lý.

Compiled expression có thể dựa vào giả định về kiểu được quan sát trong các lần đánh giá trước. Nếu cùng expression sau đó nhận object có kiểu khác, bản compiled có thể không còn phù hợp.

Ví dụ, một getter được quan sát trả về một kiểu cụ thể trong warm-up nhưng ở runtime có thể trả về implementation khác. Hãy kiểm tra cả các trường hợp thay đổi kiểu hợp lệ, không chỉ dữ liệu bình thường.

## 8. Warm-up và trạng thái steady-state

JVM có JIT compiler riêng. Vì vậy, khi đo SpEL compiler, cần phân biệt hai cơ chế:

- SpEL compiler biên dịch một expression thành bytecode.
- JVM có thể tiếp tục tối ưu bytecode đó trong quá trình thực thi.

Một lần chạy đầu tiên thường không đại diện cho steady-state. Kết quả có thể chịu ảnh hưởng bởi class loading, JIT compilation, cache, garbage collection và hoạt động khởi tạo khác.

Quy trình benchmark nên có:

1. Warm-up đủ lâu để loại bỏ phần lớn chi phí khởi tạo.
2. Đo nhiều iteration hoặc nhiều fork độc lập.
3. Giữ workload và dữ liệu tương đương giữa các chế độ.
4. Báo cáo phân phối kết quả thay vì chỉ một con số trung bình.
5. Đo riêng lần đầu và giai đoạn ổn định nếu startup latency quan trọng.
6. Lặp lại trên môi trường có cấu hình gần production.

Không chọn số lần warm-up chỉ vì một hướng dẫn chung. Hãy tăng warm-up cho tới khi kết quả ổn định và kiểm tra sự biến động giữa các lần chạy.

## 9. Dùng JMH thay cho vòng lặp đo thời gian đơn giản

Java Microbenchmark Harness (JMH) giúp kiểm soát warm-up, measurement iteration, fork và cách tiêu thụ kết quả. Nó phù hợp hơn một vòng lặp tự viết dùng System.nanoTime() cho benchmark nhỏ.

Một benchmark tối giản có thể có dạng:

~~~java
@State(Scope.Thread)
public class SpelBenchmark {

    private Expression expression;
    private StandardEvaluationContext context;

    @Setup(Level.Trial)
    public void setup() {
        ExpressionParser parser = createParser();
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

Ví dụ này minh họa cách tách setup khỏi phép đo evaluate. Trong benchmark thực tế, hãy tạo các cấu hình parser khác nhau cho OFF, IMMEDIATE và MIXED, rồi chạy cùng expression và dữ liệu.

Nếu production tạo context mỗi lần gọi, cần thêm benchmark riêng đo toàn bộ đường đi đó. Nếu production parse expression theo từng request, đo cả parse cost vì nó là một phần của workload thực.

Không dùng log, println hoặc thao tác I/O trong method benchmark. Hãy để JMH tiêu thụ kết quả để tránh JVM loại bỏ phần tính toán không có tác dụng.

## 10. Những chỉ số cần theo dõi

Không chỉ nhìn vào thời gian trung bình. Tối thiểu nên ghi nhận:

| Chỉ số | Ý nghĩa |
|---|---|
| Throughput | Số lần đánh giá hoàn tất trong một đơn vị thời gian |
| Average time | Thời gian trung bình của một thao tác |
| p50 | Độ trễ ở trung vị |
| p95 và p99 | Đuôi phân phối độ trễ, quan trọng với request |
| Allocation rate | Lượng bộ nhớ được cấp phát theo thời gian |
| GC activity | Tần suất và thời gian garbage collection |
| CPU utilization | Mức sử dụng CPU khi workload chạy |
| Error rate | Số lần đánh giá hoặc compiled expression thất bại |
| Startup/warm-up time | Chi phí trước khi đạt steady-state |

Một chế độ có throughput cao hơn nhưng p99 xấu hơn có thể không phù hợp với API nhạy cảm độ trễ. Một chế độ giảm thời gian evaluate nhưng tăng cấp phát hoặc GC cũng cần được cân nhắc theo tải tổng thể.

Đo trên cùng phần cứng, phiên bản JVM, Spring Framework, heap, collector và cấu hình ứng dụng. Ghi lại các thông số này cùng kết quả để có thể so sánh lại sau khi nâng phiên bản.

## 11. So sánh OFF, IMMEDIATE và MIXED

Nên chạy cùng một bộ expression qua ba cấu hình:

| Nội dung đo | OFF | IMMEDIATE | MIXED |
|---|---|---|---|
| Baseline interpreted | Có | Có thể có ở giai đoạn đầu | Có thể có ở giai đoạn đầu |
| Compiled execution | Không | Khi expression được biên dịch thành công | Khi expression được biên dịch thành công |
| Hành vi khi compiled expression không còn phù hợp | Không áp dụng | Có thể phát sinh lỗi đánh giá | Có cơ chế quay lại interpreted |
| Chi phí biên dịch | Không | Có | Có |
| Dùng làm baseline | Rất phù hợp | Không | Không |

Không nên suy luận rằng IMMEDIATE luôn nhanh hơn MIXED hoặc ngược lại. Kết quả phụ thuộc expression, kiểu dữ liệu, số lần đánh giá và hành vi runtime.

Hãy so sánh cùng số lượng thao tác, cùng dữ liệu và cùng điều kiện warm-up. Báo cáo rõ expression nào được biên dịch thành công, expression nào tiếp tục interpreted và những trường hợp nào làm compiled mode thất bại.

## 12. Nhận biết expression không phù hợp để biên dịch

Không phải mọi cấu trúc SpEL đều có thể được compiler hỗ trợ. Một số expression có thể tiếp tục chạy interpreted vì có node hoặc cơ chế truy cập không được biên dịch trong phiên bản hiện tại.

Những yếu tố cần kiểm tra:

- Expression dùng selection hoặc projection.
- Expression gọi method qua resolver tùy chỉnh.
- Expression phụ thuộc TypeConverter hoặc PropertyAccessor riêng.
- Expression có kiểu trả về hoặc kiểu trung gian thay đổi.
- Expression sử dụng các tính năng ngôn ngữ mà compiler chưa hỗ trợ.
- Expression có cấu trúc dữ liệu không ổn định giữa các lần đánh giá.

Không nên giả định rằng parser ở IMMEDIATE mode đồng nghĩa mọi expression đã được biên dịch. Hãy quan sát trạng thái hoặc hành vi compiler bằng API được phiên bản Spring cung cấp và kiểm tra log/exception trong môi trường thử nghiệm.

Nếu expression không thể biên dịch, interpreted mode vẫn có thể là cách chạy phù hợp. Không cần cố ép mọi expression vào compiler nếu benchmark không cho thấy lợi ích.

## 13. Kiểm tra tính ổn định kiểu dữ liệu

Một rủi ro quan trọng là expression chạy với kiểu dữ liệu khác nhau qua thời gian.

Ví dụ, một property có thể trả về các implementation khác nhau hoặc biến context có thể được cập nhật bằng kiểu khác:

~~~java
context.setVariable("value", Integer.valueOf(10));
expression.getValue(context);

context.setVariable("value", Long.valueOf(10));
expression.getValue(context);
~~~

Nếu expression đã được biên dịch dựa trên giả định kiểu trước đó, lần đánh giá với kiểu mới có thể không còn phù hợp.

Hãy kiểm thử:

- Cùng tên biến nhưng giá trị có kiểu khác.
- Getter trả về các kiểu implementation hợp lệ khác nhau.
- Property có thể null ở một số lần đánh giá.
- Collection thay đổi kiểu phần tử hoặc implementation.
- Các nhánh điều kiện tạo ra kiểu kết quả khác nhau.

Nếu hợp đồng dữ liệu yêu cầu một kiểu duy nhất, hãy chuẩn hóa kiểu trước khi đưa vào context. Nếu thay đổi kiểu là hợp lệ, hãy xác minh MIXED mode và xử lý lỗi của IMMEDIATE mode theo yêu cầu ứng dụng.

## 14. Đo tác động của collection operation

Selection và projection có thể gọi một đoạn expression cho từng phần tử. Nếu expression chứa nhiều truy cập property hoặc method, tổng chi phí tăng theo số phần tử.

Benchmark nên dùng các kích thước collection đại diện, chẳng hạn:

- Collection nhỏ tương ứng request thông thường.
- Collection trung bình tương ứng workload phổ biến.
- Collection lớn tương ứng trường hợp cao điểm hoặc dữ liệu biên.

Đo riêng thời gian tổng và số phần tử được xử lý. Một expression có thời gian 2 ms trên 10 phần tử không thể so trực tiếp với expression 2 ms trên 1.000 phần tử mà không xét throughput theo phần tử.

Nếu selection/projection không được compiler hỗ trợ trong phiên bản đang dùng, bật compiler có thể không thay đổi chi phí của phần đó. Hãy xác định node thực sự được biên dịch thay vì chỉ nhìn compiler mode.

## 15. Tách chi phí SpEL khỏi chi phí bên ngoài

Một expression có thể gọi method, bean hoặc getter thực hiện truy vấn. Nếu benchmark toàn bộ expression, thời gian database hoặc network có thể lấn át phần SpEL.

Ví dụ:

~~~text
#orderService.loadSummary(#orderId)
~~~

Nếu loadSummary truy vấn database, kết quả benchmark chủ yếu phản ánh truy vấn và tầng kết nối, không phải tốc độ đánh giá SpEL.

Nên thực hiện hai phép đo:

1. **Microbenchmark expression:** thay method bên ngoài bằng dữ liệu hoặc stub có chi phí ổn định để đo overhead của SpEL.
2. **End-to-end benchmark:** giữ nguyên service thật để đo tác động tổng thể tới request.

Cả hai đều hữu ích nhưng trả lời câu hỏi khác nhau. Microbenchmark giúp hiểu compiler; end-to-end benchmark xác nhận người dùng thực sự nhận được cải thiện hay không.

## 16. Phân tích chi phí khởi động và biên dịch

Compiler có thể tạo thêm chi phí ở những lần đánh giá đầu tiên. Nếu ứng dụng có thời gian sống ngắn hoặc expression chỉ được gọi vài lần, chi phí này có thể lớn hơn phần tiết kiệm sau đó.

Hãy đo:

- Thời gian khởi tạo parser.
- Thời gian parse expression.
- Số lần evaluate trước khi compiled mode được sử dụng.
- Thời gian compile nếu có thể quan sát.
- Độ trễ trong giai đoạn chuyển chế độ.
- Tổng thời gian cần để thu hồi chi phí biên dịch.

Nếu expression chỉ chạy vài lần trong vòng đời ứng dụng, OFF có thể phù hợp hơn. Nếu expression chạy hàng triệu lần với kiểu dữ liệu ổn định, compiled mode có cơ hội tạo lợi ích rõ hơn.

Không suy luận điểm hòa vốn từ một lần benchmark. Hãy đo với tần suất thực tế và vòng đời thật của từng expression.

## 17. Theo dõi lỗi và tính đúng đắn sau khi bật compiler

Benchmark phải xác nhận kết quả trả về giống baseline cho cùng dữ liệu.

So sánh:

- Giá trị trả về.
- Kiểu trả về.
- Hành vi với null.
- Exception được ném.
- Tác dụng phụ nếu expression gọi method có trạng thái.
- Kết quả trên dữ liệu biên và kiểu dữ liệu thay đổi.

IMMEDIATE mode cần được kiểm thử kỹ khi compiled expression có thể không còn phù hợp với kiểu runtime. MIXED mode có thể quay lại interpreted mode khi bản compiled gặp vấn đề, nhưng điều đó không có nghĩa mọi lỗi nghiệp vụ hoặc mọi exception đều được tự động sửa.

Không được coi fallback của MIXED là cơ chế xử lý lỗi chung. Nếu getter, service hoặc method ném exception vì dữ liệu sai, ứng dụng vẫn phải xử lý lỗi theo hợp đồng của nó.

## 18. Kế hoạch triển khai có kiểm soát

Sau benchmark trong môi trường thử nghiệm, hãy triển khai theo từng bước:

1. Giữ OFF làm baseline đã ghi nhận.
2. Chọn một nhóm expression có tần suất cao và kiểu ổn định.
3. Bật compiler trong môi trường staging với dữ liệu gần production.
4. Chạy kiểm thử chức năng và tải.
5. So sánh latency, throughput, CPU, allocation và error rate.
6. Triển khai canary cho một tỷ lệ nhỏ traffic nếu kiến trúc cho phép.
7. Theo dõi trong khoảng thời gian đủ để gặp các kiểu dữ liệu và workload đại diện.
8. Mở rộng dần khi lợi ích được xác nhận.
9. Giữ khả năng quay về OFF nếu latency hoặc lỗi xấu đi.

Không thay đổi compiler mode cho toàn bộ expression chỉ dựa trên một microbenchmark. Một số expression có thể được lợi, trong khi nhóm khác không thay đổi hoặc phát sinh chi phí.

## 19. Tiêu chí quyết định bật compiler

Có thể dùng bảng quyết định:

| Kết quả đo | Quyết định gợi ý |
|---|---|
| Expression ít được gọi, không có bottleneck | Giữ OFF |
| Expression chạy thường xuyên, kiểu ổn định, compiled nhanh hơn rõ ràng | Cân nhắc IMMEDIATE hoặc MIXED sau kiểm thử |
| Kiểu dữ liệu thay đổi hợp lệ giữa các lần đánh giá | Kiểm tra MIXED và chuẩn hóa dữ liệu nếu phù hợp |
| Expression không được compiler hỗ trợ | Giữ interpreted; tối ưu cấu trúc hoặc logic khác |
| Throughput tăng nhưng p99 xấu đi | Chưa bật rộng; điều tra tail latency |
| CPU giảm nhưng allocation/GC tăng đáng kể | Đánh giá tác động toàn ứng dụng |
| Có lỗi compiled mode hoặc kết quả khác baseline | Không triển khai cho expression đó |
| End-to-end latency không cải thiện | Không bật chỉ vì microbenchmark đẹp |

Mức cải thiện cần thiết phụ thuộc SLO và chi phí vận hành của ứng dụng. Hãy xác định ngưỡng chấp nhận trước khi benchmark để tránh chọn kết quả có lợi sau khi đã xem số liệu.

## 20. Ví dụ cấu hình benchmark ba chế độ

Có thể tạo parser theo từng mode để chạy cùng một expression:

~~~java
private ExpressionParser parserFor(
        SpelCompilerMode mode,
        ClassLoader classLoader) {

    SpelParserConfiguration configuration =
        new SpelParserConfiguration(mode, classLoader);

    return new SpelExpressionParser(configuration);
}
~~~

Dùng cùng expression source:

~~~java
String source = "#order.total >= #minimum";
~~~

Tạo ba Expression riêng:

~~~java
Expression interpreted =
    parserFor(SpelCompilerMode.OFF, getClass().getClassLoader())
        .parseExpression(source);

Expression immediate =
    parserFor(SpelCompilerMode.IMMEDIATE, getClass().getClassLoader())
        .parseExpression(source);

Expression mixed =
    parserFor(SpelCompilerMode.MIXED, getClass().getClassLoader())
        .parseExpression(source);
~~~

Chuẩn bị các context và dữ liệu tương đương, sau đó warm-up và đo từng expression trong các fork độc lập. Không dùng cùng một expression instance cho nhiều mode vì compiler mode được cấu hình khi parser tạo expression.

Trong benchmark thực tế, nên chạy từng mode trong tiến trình hoặc fork riêng để giảm ảnh hưởng của class loading, JIT profile và trạng thái dùng chung từ lần chạy trước.

## 21. Ghi lại kết quả để có thể tái lập

Một báo cáo benchmark nên lưu:

- Phiên bản Spring Framework và JDK.
- Compiler mode và cấu hình parser.
- ClassLoader được sử dụng.
- Expression source và số lượng expression.
- Kiểu root object, biến và dữ liệu mẫu.
- Cách tạo EvaluationContext.
- Số lần warm-up và measurement.
- Số fork, thread và kích thước collection.
- Throughput, p50, p95, p99 và average time.
- Allocation, GC và CPU.
- Tỷ lệ expression được biên dịch hoặc tiếp tục interpreted nếu có thể quan sát.
- Số lỗi và sai khác kết quả so với OFF.
- Cấu hình máy và giới hạn heap.

Lưu cả kết quả không cải thiện. Những lần đo này giúp tránh lặp lại thử nghiệm và cho biết expression nào không phù hợp với compiler.

## 22. Ghi nhớ

SpEL compiler có thể tăng tốc những expression được đánh giá lặp lại và có cấu trúc phù hợp, nhưng không phải expression nào cũng được biên dịch hoặc chạy nhanh hơn. OFF là baseline interpreted; IMMEDIATE ưu tiên compiled execution; MIXED có thể quay lại interpreted khi compiled expression không còn phù hợp.

Hãy đo riêng parse, evaluate, warm-up/compile và context setup. Dùng workload, kiểu dữ liệu, kích thước collection và vòng đời gần production. Warm-up JVM, chạy nhiều fork, đo throughput, latency distribution, allocation, GC, CPU và error rate. JMH phù hợp hơn vòng lặp đo thời gian tự viết.

Kiểm tra tính đúng đắn với null, kiểu dữ liệu thay đổi, getter, method và collection operation. Compiler mode là tối ưu hiệu năng, không phải sandbox bảo mật và không thay thế validation hay giới hạn quyền của EvaluationContext.

Chỉ bật compiler khi benchmark cho thấy cải thiện có ý nghĩa đối với SLO của ứng dụng và kiểm thử xác nhận kết quả tương đương baseline. Triển khai có kiểm soát, theo dõi sau khi bật và giữ đường quay lại OFF khi lợi ích không còn hoặc lỗi tăng.

## Tài liệu tham khảo

- [Spring Framework Reference — SpEL Compilation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SpelCompilerMode Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelCompilerMode.html)
- [SpelParserConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParserConfiguration.html)
- [JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh)
# Đo độ trễ, cấp phát và thông lượng trước khi tối ưu trong Spring Expression Language

Khi một biểu thức Spring Expression Language (SpEL) được đánh giá thường xuyên, chi phí nhỏ ở mỗi lần gọi có thể cộng dồn thành độ trễ đáng kể hoặc tạo áp lực lên CPU và bộ nhớ. Tuy nhiên, không nên tối ưu chỉ vì một expression trông phức tạp hoặc vì compiler mode có vẻ nhanh hơn. Trước hết cần đo trên workload đại diện để biết thời gian nằm ở parsing, evaluation, tạo context, chuyển đổi dữ liệu hay chính logic nghiệp vụ.

Một phép đo có ích cần nhìn ít nhất ba khía cạnh:

- **Độ trễ (latency):** một lần xử lý mất bao lâu, bao gồm cả các percentile như p50, p95 và p99.
- **Cấp phát bộ nhớ (allocation):** mỗi lần xử lý tạo bao nhiêu object/byte và ảnh hưởng đến garbage collection ra sao.
- **Thông lượng (throughput):** hệ thống xử lý được bao nhiêu lần đánh giá hoặc request trong một đơn vị thời gian khi có tải.

Đo riêng từng phần giúp tìm đúng nút thắt. Sau khi có baseline, mới thử cache Expression, tái sử dụng cấu hình, thay đổi compiler mode hoặc đơn giản hóa expression; cuối cùng đo lại cùng điều kiện để xác nhận cải thiện.

## 1. Vì sao cần đo trước khi tối ưu?

Một lời gọi \`getValue()\` có thể bao gồm nhiều công việc khác nhau:

1. Tra cứu property trên root object hoặc object lồng nhau.
2. Gọi method thông qua MethodResolver.
3. Đọc variables từ EvaluationContext.
4. Chuyển đổi kiểu qua TypeConverter.
5. Thực hiện selection, projection, indexing hoặc phép toán.
6. Tạo object kết quả hoặc chuỗi template.
7. Xử lý lỗi nếu dữ liệu không hợp lệ.

Ngoài bản thân evaluation, ứng dụng còn có thể tạo parser, parse expression, tạo EvaluationContext, đăng ký variables, chuẩn bị dữ liệu và ghi log.

Nếu benchmark gộp tất cả các bước vào một con số, rất khó biết nên tối ưu phần nào. Ví dụ, nếu parse expression ở mỗi request, chi phí parse có thể lớn hơn phần evaluation mà ứng dụng đang muốn cải thiện.

Mục tiêu của benchmark là trả lời các câu hỏi cụ thể:

- Parse một expression mất bao lâu?
- Đánh giá một Expression đã parse mất bao lâu?
- Tạo EvaluationContext mới có đáng kể không?
- Expression có allocation nhiều không?
- Khi tải tăng, throughput có tăng tuyến tính hay bị giới hạn bởi CPU, GC hoặc lock?
- Compiler mode có cải thiện workload thực tế không?
- Thay đổi có làm p95/p99 xấu đi dù average tốt hơn không?

## 2. Ba nhóm chỉ số cần theo dõi

### 2.1. Độ trễ

Latency là thời gian hoàn thành một lần xử lý. Có thể đo bằng nanosecond hoặc microsecond trong benchmark, và millisecond trong luồng request thực tế.

Không nên chỉ nhìn average. Một số lần đánh giá có thể chậm do GC, JIT compilation, cache miss, tải hệ thống hoặc dữ liệu đặc biệt.

Các percentile thường hữu ích:

| Chỉ số | Ý nghĩa |
|---|---|
| p50 | Một nửa số lần xử lý hoàn thành trong khoảng thời gian này hoặc nhanh hơn |
| p90 | 90% số lần xử lý hoàn thành trong khoảng thời gian này hoặc nhanh hơn |
| p95 | 95% số lần xử lý hoàn thành trong khoảng thời gian này hoặc nhanh hơn |
| p99 | 99% số lần xử lý hoàn thành trong khoảng thời gian này hoặc nhanh hơn |
| max | Lần chậm nhất trong cửa sổ đo; nhạy với outlier |

p50 mô tả trải nghiệm điển hình, còn p95 và p99 giúp phát hiện tail latency. Nếu p50 giảm nhưng p99 tăng mạnh, tối ưu đó có thể không phù hợp với hệ thống cần thời gian phản hồi ổn định.

### 2.2. Cấp phát bộ nhớ

Allocation đo lượng bộ nhớ được cấp phát trong một đơn vị công việc, thường biểu diễn bằng bytes/op hoặc objects/op.

Một expression có thể chạy nhanh nhưng tạo nhiều object tạm, khiến GC hoạt động thường xuyên. Khi tải cao, chi phí GC có thể làm tăng latency và giảm throughput.

Các chỉ số nên xem:

- Bytes allocated per operation.
- Allocation rate theo thời gian.
- Số lần và thời gian garbage collection.
- Heap occupancy trước và sau các đợt tải.
- Object type được cấp phát nhiều nhất khi profiling.

Đừng đồng nhất allocation với retained heap. Object được cấp phát rồi thu hồi nhanh vẫn làm tăng áp lực GC dù không còn được giữ lại trong heap lâu dài.

### 2.3. Thông lượng

Throughput cho biết số lần xử lý hoàn tất trong một đơn vị thời gian, ví dụ operations/second hoặc requests/second.

Khi benchmark tăng số luồng, throughput có thể tăng đến một điểm rồi chững lại. Nguyên nhân có thể là CPU bão hòa, contention, allocation/GC, tài nguyên dùng chung hoặc dependency bên ngoài.

Cần đo throughput cùng latency. Throughput cao hơn nhưng p99 tăng quá mức có thể không phải cải thiện tốt cho người dùng.

## 3. Tách chi phí parsing khỏi evaluation

\`ExpressionParser.parseExpression(...)\` biến chuỗi thành một đối tượng Expression. Sau đó, \`Expression.getValue(...)\` đánh giá đối tượng đã parse.

Hai thao tác có chi phí khác nhau:

~~~java
ExpressionParser parser =
    new SpelExpressionParser();

Expression expression =
    parser.parseExpression("price * #quantity");

Object result =
    expression.getValue(context);
~~~

Nếu ứng dụng sử dụng cùng một expression nhiều lần, thường nên parse một lần rồi tái sử dụng Expression. Nếu benchmark parse và evaluate trong cùng một phương thức, kết quả sẽ phản ánh cả hai chi phí và không thể hiện riêng tốc độ evaluation.

Nên có ít nhất hai benchmark:

- **Parse benchmark:** đo chi phí tạo Expression từ chuỗi.
- **Evaluation benchmark:** parse trước trong setup, chỉ đo getValue trong phần benchmark.

Có thể thêm benchmark end-to-end để đo cả việc tạo context, đăng ký variables và evaluation nếu đó là cách ứng dụng thực sự chạy.

## 4. Dùng JMH cho microbenchmark Java

JMH (Java Microbenchmark Harness) được thiết kế để đo hiệu năng JVM. Nó xử lý nhiều vấn đề dễ làm sai benchmark tự viết như warm-up, dead-code elimination, JIT compilation và fork process.

Một benchmark JMH nên:

- Có warm-up đủ để JVM đạt trạng thái ổn định.
- Có nhiều measurement iteration.
- Dùng nhiều fork để giảm ảnh hưởng trạng thái JVM của lần chạy trước.
- Trả kết quả hoặc đưa kết quả vào Blackhole để tránh compiler loại bỏ công việc.
- Dùng dữ liệu đại diện và không tạo thêm công việc ngoài ý muốn trong vùng đo.
- Ghi lại phiên bản JDK, Spring và cấu hình máy.

Ví dụ cấu trúc benchmark đánh giá Expression đã parse:

~~~java
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
public class SpelEvaluationBenchmark {

    private Expression expression;
    private StandardEvaluationContext context;

    @Setup(Level.Trial)
    public void setup() {
        Product product =
            new Product(new BigDecimal("250000"));

        context = new StandardEvaluationContext(product);
        context.setVariable("quantity", 3);

        ExpressionParser parser =
            new SpelExpressionParser();

        expression =
            parser.parseExpression("price * #quantity");
    }

    @Benchmark
    public Object evaluate() {
        return expression.getValue(context);
    }
}
~~~

Trong benchmark này, parser, Expression và context được tạo trong setup, không nằm trong vùng đo của phương thức evaluate. Kết quả phản ánh chủ yếu chi phí đánh giá expression với context đã chuẩn bị.

Nếu ứng dụng thực tế tạo context mới cho mỗi request, cần benchmark riêng trường hợp đó; không nên chỉ dùng kết quả của context tái sử dụng để đại diện toàn bộ luồng production.

## 5. Benchmark parsing riêng

Để đo chi phí parsing, đặt thao tác parse trong phương thức benchmark:

~~~java
@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
public class SpelParsingBenchmark {

    private ExpressionParser parser;

    @Setup(Level.Trial)
    public void setup() {
        parser = new SpelExpressionParser();
    }

    @Benchmark
    public Expression parse() {
        return parser.parseExpression(
            "price * #quantity + tax"
        );
    }
}
~~~

Benchmark này đo việc tạo Expression từ chuỗi. Nó không đo getValue.

Nên dùng đúng expression có độ dài và cấu trúc gần với ứng dụng. Một expression chỉ có phép cộng hai số không đại diện cho template dài, selection trên collection hoặc method invocation có nhiều property lồng nhau.

Nếu ứng dụng có cache Expression theo key, cũng nên đo tỷ lệ cache hit/miss và chi phí lookup trong benchmark end-to-end.

## 6. Đo riêng chi phí tạo EvaluationContext

EvaluationContext chứa root object, variables và các dịch vụ truy cập. Tạo context mới mỗi lần có thể tạo thêm object và allocation.

So sánh hai trường hợp:

- Reuse context trong phạm vi phù hợp.
- Tạo context mới cho mỗi lần xử lý rồi đăng ký variables.

Ví dụ benchmark tạo context:

~~~java
@Benchmark
public Object evaluateWithNewContext(BenchmarkState state) {
    StandardEvaluationContext context =
        new StandardEvaluationContext(state.product);

    context.setVariable("quantity", state.quantity);

    return state.expression.getValue(context);
}
~~~

So sánh với benchmark dùng context đã chuẩn bị trong setup sẽ cho thấy chi phí bổ sung của context creation và variable registration.

Không nên dùng chung một context có variables thay đổi giữa các request độc lập hoặc các thread mà không kiểm soát trạng thái. Việc tái sử dụng phải phù hợp với vòng đời dữ liệu và yêu cầu concurrency của ứng dụng.

Một lựa chọn thường rõ ràng là tái sử dụng Expression đã parse, nhưng tạo EvaluationContext riêng cho từng đơn vị công việc nếu context chứa dữ liệu thay đổi theo request.

## 7. Chọn workload SpEL đại diện

Không nên chỉ benchmark một expression đơn giản rồi suy rộng kết quả cho mọi expression. Hãy lập một tập workload phản ánh những dạng expression ứng dụng thực sự sử dụng.

| Nhóm expression | Ví dụ | Đặc điểm cần đo |
|---|---|---|
| Property access | \`customer.address.city\` | Số cấp property, accessor |
| Method invocation | \`customer.calculate(#amount)\` | MethodResolver, đối số |
| Variable lookup | \`#minimum\` | Tra cứu variable |
| Arithmetic | \`price * #quantity\` | Toán tử, kiểu số |
| Conversion | Gán String vào property số | TypeConverter, converter |
| Selection | \`#items.?[active]\` | Số phần tử, predicate |
| Projection | \`#items.![name]\` | Số phần tử, object kết quả |
| Template | \`"Total: #{#total}"\` | Số đoạn và tạo String |
| Null-safe access | \`#customer?.address?.city\` | Nhánh null và non-null |
| Custom accessor/resolver | Domain-specific access | Chi phí extension |

Với selection và projection, cần thay đổi số phần tử đầu vào. Một biểu thức chạy trên 5 phần tử có thể có đặc điểm hiệu năng khác nhiều so với cùng biểu thức chạy trên 5.000 phần tử.

Cũng nên đo cả dữ liệu bình thường và dữ liệu biên như collection rỗng, property null, chuỗi dài hoặc trường hợp không có phần tử phù hợp.

## 8. Đo latency distribution thay vì chỉ average

JMH hỗ trợ nhiều benchmark mode. Có thể chọn mode phù hợp với câu hỏi:

- \`Mode.AverageTime\`: thời gian trung bình cho một operation.
- \`Mode.Throughput\`: số operation mỗi đơn vị thời gian.
- \`Mode.SampleTime\`: lấy mẫu thời gian từng operation để quan sát phân phối latency.
- \`Mode.SingleShotTime\`: đo từng lần chạy đơn lẻ, hữu ích cho một số trường hợp cold-start nhưng không thay thế benchmark steady-state.

Ví dụ chọn SampleTime:

~~~java
@BenchmarkMode(Mode.SampleTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 10)
@Fork(3)
public class SpelLatencyBenchmark {
    // State và benchmark method.
}
~~~

Kết quả SampleTime có thể cung cấp percentile và histogram theo cấu hình JMH. Khi chạy production, nên dùng metrics hoặc histogram của hệ thống quan sát để theo dõi p50, p95 và p99 theo cửa sổ thời gian.

Không nên so sánh percentile của hai lần chạy nếu tải nền, cấu hình máy hoặc cách lấy mẫu khác nhau đáng kể.

## 9. Đo thông lượng ở nhiều mức concurrency

Một benchmark một thread cho biết chi phí đơn lẻ nhưng không thể hiện đầy đủ hành vi khi nhiều request đánh giá expression đồng thời.

Có thể dùng JMH với \`Scope.Thread\` để mỗi thread có state riêng, sau đó thay số thread khi chạy. Ví dụ:

~~~bash
java -jar target/benchmarks.jar SpelEvaluationBenchmark -t 1
java -jar target/benchmarks.jar SpelEvaluationBenchmark -t 4
java -jar target/benchmarks.jar SpelEvaluationBenchmark -t 8
~~~

Quan sát:

- Throughput tăng như thế nào khi tăng thread?
- Latency p95/p99 có tăng nhanh không?
- CPU có đạt mức bão hòa không?
- Allocation rate và GC có tăng theo tải không?
- Có contention trên object dùng chung hoặc cache không?

Nếu throughput không tăng khi thêm thread, cần profiling để tìm tài nguyên giới hạn. Không nên kết luận SpEL chậm nếu bottleneck thực tế nằm ở database, network, lock hoặc code nghiệp vụ được gọi từ expression.

## 10. Đo allocation và GC bằng JMH

JMH có GC profiler để quan sát allocation và hoạt động garbage collection:

~~~bash
java -jar target/benchmarks.jar SpelEvaluationBenchmark -prof gc
~~~

Các kết quả hữu ích thường gồm:

- \`gc.alloc.rate\`: tốc độ cấp phát.
- \`gc.alloc.rate.norm\`: lượng cấp phát chuẩn hóa trên mỗi operation.
- \`gc.count\`: số lần GC trong khoảng đo.
- \`gc.time\`: tổng thời gian GC.

Tên và định dạng output có thể khác theo phiên bản JMH và profiler. Hãy đọc phần header của kết quả để biết đơn vị và ý nghĩa chính xác.

Nếu bytes/op cao, dùng Java Flight Recorder (JFR) hoặc profiler allocation để tìm loại object được tạo nhiều. Đừng mặc định mọi allocation đều do SpEL; có thể object đến từ method nghiệp vụ được gọi trong expression, converter, logger hoặc dữ liệu test.

## 11. Dùng Java Flight Recorder và profiler

JFR ghi lại sự kiện runtime của JVM, hữu ích để quan sát:

- CPU hot methods.
- Allocation theo class.
- Garbage collection và pause.
- Lock contention.
- Thread scheduling.
- Class loading và JIT compilation.
- Exception hoặc sự kiện runtime tùy cấu hình recording.

Có thể thu recording trong một lần chạy đại diện rồi mở bằng Java Mission Control. JFR giúp chuyển từ câu hỏi "expression này chậm" sang câu hỏi cụ thể hơn: method nào chiếm CPU, object nào được cấp phát nhiều, hay GC pause nào ảnh hưởng tail latency.

Profiler cần được dùng có chủ đích. Profiling có overhead; hãy so sánh recording có và không có profiler để hiểu ảnh hưởng của công cụ.

## 12. So sánh interpreted và compiled mode công bằng

SpEL có các compiler mode:

- \`OFF\`: interpreted execution.
- \`IMMEDIATE\`: yêu cầu compiled execution sớm khi có thể.
- \`MIXED\`: có thể chuyển từ interpreted sang compiled và quay lại interpreted khi compiled execution không còn phù hợp.

Cấu hình parser:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        Product.class.getClassLoader()
    );

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

Để so sánh công bằng:

1. Dùng cùng expression và cùng dữ liệu đầu vào.
2. Tách thời gian parsing khỏi evaluation.
3. Cho JVM và expression đủ warm-up.
4. Chạy nhiều fork.
5. Xác nhận expression thực sự có thể được compiler xử lý.
6. Đo cả latency, throughput và allocation.
7. Kiểm tra kết quả logic giữa các mode có giống nhau.
8. Thử kiểu runtime ổn định và trường hợp kiểu thay đổi nếu production có cả hai.

Không nên chỉ đo một vài lần gọi đầu tiên rồi kết luận compiler mode nhanh hay chậm. Chi phí warm-up và compile có thể làm kết quả ban đầu khác với steady-state.

Compiler không hỗ trợ mọi cấu trúc expression. Một expression evaluate được ở interpreted mode chưa chắc compile được. MIXED có khả năng fallback, còn IMMEDIATE cần được kiểm thử cẩn thận với workload thật.

## 13. Đo cache Expression như một thay đổi riêng

Nếu ứng dụng parse cùng một chuỗi nhiều lần, cache Expression có thể giảm chi phí parsing.

Một cache nên có giới hạn và chính sách eviction phù hợp nếu expression key có thể tăng không giới hạn. Nếu expression đến từ cấu hình cố định, có thể parse lúc khởi động rồi lưu lại theo key.

Khi benchmark cache, đo riêng:

- Cache hit: lookup và sử dụng Expression đã parse.
- Cache miss: parse expression rồi lưu.
- Chi phí đồng bộ hoặc contention khi nhiều thread cùng miss.
- Bộ nhớ giữ lại bởi cache.
- Tác động của kích thước cache và eviction.

Không nên cache EvaluationContext chứa root object hoặc variables của một request như thể đó là Expression bất biến. Context thường mang dữ liệu runtime và phải có vòng đời phù hợp.

## 14. Đo luồng Spring end-to-end

Microbenchmark cô lập giúp tìm chi phí của SpEL, nhưng quyết định tối ưu production cần được xác nhận ở mức ứng dụng.

Một luồng thực tế có thể gồm:

~~~text
HTTP request
    |
    v
Controller / service
    |
    v
Tạo hoặc lấy EvaluationContext
    |
    v
Lấy Expression từ cache
    |
    v
SpEL getValue(...)
    |
    v
Gọi method nghiệp vụ / repository
    |
    v
Serialize response
~~~

Nếu chỉ benchmark getValue, các bước còn lại không được tính. Điều đó phù hợp để tìm chi phí SpEL, nhưng không thể thay thế benchmark request end-to-end.

Dùng metrics ở ranh giới phù hợp để đo tổng latency và, nếu có thể, thêm timer riêng cho parsing/evaluation. So sánh hai lớp đo sẽ cho biết SpEL chiếm tỷ trọng bao nhiêu trong tổng thời gian request.

Nếu evaluation chỉ chiếm 1% latency, tối ưu SpEL dù cải thiện gấp đôi cũng chỉ tác động nhỏ đến tổng thời gian. Hãy ưu tiên bottleneck có ảnh hưởng lớn hơn.

## 15. Metrics trong ứng dụng Spring

Với ứng dụng Spring Boot có Micrometer, có thể ghi thời gian evaluation bằng Timer:

~~~java
@Service
public class RuleEvaluator {

    private final MeterRegistry meterRegistry;
    private final Expression expression;

    public RuleEvaluator(
            MeterRegistry meterRegistry,
            Expression expression) {
        this.meterRegistry = meterRegistry;
        this.expression = expression;
    }

    public Object evaluate(EvaluationContext context) {
        return Timer.builder("spel.evaluation")
            .description("Time spent evaluating SpEL expressions")
            .tag("rule", "order-eligibility")
            .register(meterRegistry)
            .record(() -> expression.getValue(context));
    }
}
~~~

Trong production, nên đăng ký Timer một lần hoặc inject meter đã đăng ký thay vì tạo lookup/registration lặp lại trong hot path nếu điều đó gây overhead. Ví dụ trên minh họa API; cách triển khai thực tế có thể giữ Timer trong field.

Giữ tag có cardinality thấp. Không đưa toàn bộ expression string, user ID, order ID hoặc dữ liệu đầu vào làm tag vì số lượng time series có thể tăng rất lớn.

Có thể theo dõi thêm:

- Tổng số evaluation.
- Số evaluation lỗi theo nhóm lỗi có giới hạn.
- Latency histogram.
- Số cache hit/miss nếu có expression cache.
- Throughput theo endpoint hoặc rule category.
- GC và JVM metrics từ Micrometer.

Không ghi nội dung nhạy cảm của expression hoặc dữ liệu biến vào metric label.

## 16. Thiết kế benchmark với dữ liệu thực tế

Dữ liệu benchmark nên phản ánh phân phối production:

- Kích thước collection thường gặp và trường hợp lớn.
- Tỷ lệ property null.
- Tỷ lệ selection không có kết quả.
- Độ dài chuỗi và template.
- Số biến và số cấp property.
- Kiểu root object và implementation runtime.
- Tần suất lỗi và conversion failure nếu chúng có trong workload.
- Số lần đánh giá cùng một Expression.

Nếu chỉ dùng dữ liệu lý tưởng, benchmark có thể bỏ qua các nhánh xử lý null, exception hoặc collection lớn vốn xuất hiện thường xuyên trong production.

Cũng cần tránh benchmark chỉ với một object cố định nếu production dùng nhiều kiểu runtime khác nhau. JIT có thể tối ưu rất mạnh cho một kiểu duy nhất, tạo ra kết quả không đại diện cho ứng dụng.

## 17. Kiểm soát các yếu tố gây nhiễu

Một benchmark đáng tin cậy cần giữ điều kiện đo ổn định.

Trước khi so sánh:

1. Dùng cùng JDK vendor và version.
2. Dùng cùng phiên bản Spring Framework và dependency.
3. Ghi lại CPU, số core, RAM và hệ điều hành.
4. Tránh chạy tác vụ nặng khác trên máy trong lúc đo.
5. Dùng cùng heap và JVM flags.
6. Chạy nhiều fork và iteration.
7. Đảm bảo warm-up đủ.
8. Tránh log trong hot path benchmark.
9. Không tạo dữ liệu test ngoài ý muốn trong mỗi operation.
10. Dùng kết quả trả về hoặc Blackhole để tránh dead-code elimination.

Khi kết quả dao động lớn giữa các lần chạy, hãy tìm nguyên nhân trước khi chọn con số có lợi nhất. Noise có thể đến từ CPU frequency scaling, GC, JIT, tác vụ nền hoặc cấu hình container.

## 18. Quy trình tối ưu dựa trên bằng chứng

Một quy trình thực tế có thể gồm:

1. **Xác định mục tiêu:** ví dụ giảm p95 evaluation latency hoặc giảm allocation bytes/op.
2. **Tạo baseline:** đo workload hiện tại với cấu hình và dữ liệu cố định.
3. **Tách chi phí:** parse, context creation, evaluation và end-to-end.
4. **Profile:** tìm method CPU hot, allocation và GC thực sự.
5. **Đặt giả thuyết:** ví dụ parse lặp lại, tạo quá nhiều context hoặc selection trên collection quá lớn.
6. **Thử một thay đổi:** cache Expression, giảm object trung gian hoặc thử compiler mode.
7. **Đo lại:** chạy cùng benchmark và điều kiện.
8. **So sánh:** latency percentiles, throughput, allocation và correctness.
9. **Kiểm tra production:** rollout có giám sát nếu thay đổi ảnh hưởng hành vi runtime.
10. **Giữ hoặc hoàn tác:** chỉ giữ thay đổi nếu cải thiện mục tiêu mà không làm xấu chỉ số quan trọng khác.

Mỗi lần chỉ thay đổi một yếu tố chính giúp kết quả dễ giải thích hơn. Nếu cùng lúc đổi compiler mode, cache, context và expression, sẽ khó xác định yếu tố nào tạo ra khác biệt.

## 19. Đọc kết quả và quyết định có nên tối ưu

Ví dụ một benchmark so sánh trước và sau:

| Chỉ số | Trước | Sau | Cách diễn giải |
|---|---:|---:|---|
| p50 latency | 80 µs | 60 µs | Cải thiện thời gian điển hình |
| p95 latency | 150 µs | 120 µs | Tail latency tốt hơn |
| Allocation | 1.2 KB/op | 0.8 KB/op | Ít object/byte hơn mỗi lần |
| Throughput | 20k ops/s | 25k ops/s | Nhiều operation hơn mỗi giây |

Các con số trong bảng chỉ minh họa cách đọc kết quả, không phải benchmark mặc định của SpEL.

Một thay đổi có thể cải thiện một chỉ số và làm xấu chỉ số khác. Ví dụ compiler có thể tăng throughput steady-state nhưng tăng warm-up cost; cache có thể giảm parse time nhưng tăng retained heap; tái sử dụng context có thể giảm allocation nhưng tạo rủi ro chia sẻ state nếu quản lý sai.

Quyết định cuối cùng cần dựa trên mục tiêu hệ thống và workload thật, không dựa vào một chỉ số đơn lẻ.

## 20. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Đo thời gian parse và evaluate cùng nhau là đủ.**  
Nếu cần tối ưu evaluation, hãy parse trước và đo getValue riêng. End-to-end benchmark vẫn cần thiết nhưng trả lời câu hỏi khác.

**Nhầm lẫn 2: Average latency đại diện cho mọi request.**  
p95 và p99 có thể xấu dù average tốt. Hãy xem phân phối latency.

**Nhầm lẫn 3: Throughput cao hơn luôn có nghĩa trải nghiệm tốt hơn.**  
Latency tail có thể tăng khi tải cao. Cần xem throughput cùng latency.

**Nhầm lẫn 4: Ít CPU hơn đồng nghĩa ít allocation hơn.**  
CPU time và allocation là hai chỉ số riêng. Dùng GC profiler hoặc JFR để đo allocation.

**Nhầm lẫn 5: Compiler mode luôn nhanh hơn interpreted mode.**  
Chỉ expression phù hợp và workload có đủ lần đánh giá mới có thể hưởng lợi; warm-up và compile có chi phí.

**Nhầm lẫn 6: Context nên được dùng chung để tiết kiệm allocation.**  
Context chứa root và variables có thể thay đổi. Chia sẻ sai phạm vi gây lỗi dữ liệu và concurrency; hãy đo và thiết kế vòng đời đúng.

**Nhầm lẫn 7: Microbenchmark là đủ để quyết định production.**  
JMH cô lập chi phí, còn request thực tế có controller, service, database, serialization và contention. Cần xác nhận ở mức end-to-end.

**Nhầm lẫn 8: Tối ưu một expression đơn giản đại diện cho toàn bộ SpEL.**  
Property access, method call, selection, projection, template và conversion có đặc điểm chi phí khác nhau.

## 21. Ghi nhớ

- Đo trước khi tối ưu để xác định bottleneck thực sự.
- Theo dõi latency distribution, đặc biệt p50, p95 và p99; không chỉ average.
- Đo allocation bytes/op, allocation rate và GC để hiểu áp lực bộ nhớ.
- Đo throughput ở nhiều mức concurrency và quan sát điểm bão hòa.
- Tách parsing, EvaluationContext creation và getValue thành các benchmark riêng.
- Dùng JMH với warm-up, measurement iteration, fork và kết quả không bị dead-code elimination.
- Benchmark workload đại diện gồm property, method, variables, conversion, selection, projection và template.
- So sánh OFF, IMMEDIATE và MIXED sau warm-up, trên cùng expression và dữ liệu.
- Dùng JMH GC profiler, JFR hoặc profiler phù hợp để tìm nguồn allocation và CPU hot spots.
- Đo cả microbenchmark lẫn request end-to-end trước khi quyết định tối ưu.
- Cache Expression có thể giảm parse cost; context cần vòng đời phù hợp với root object và variables.
- Giữ điều kiện benchmark nhất quán và thay đổi từng yếu tố để kết quả có thể giải thích.
- Chỉ giữ tối ưu khi chỉ số mục tiêu cải thiện mà correctness và các chỉ số quan trọng khác vẫn đạt yêu cầu.

Khi tối ưu SpEL, hãy bắt đầu bằng một baseline có thể tái lập, tách riêng chi phí parse và evaluate, đo latency, allocation và throughput trên dữ liệu gần production, rồi dùng profiler để xác định nguyên nhân. Một thay đổi chỉ đáng giữ khi phép đo sau thay đổi chứng minh được lợi ích trong workload mà ứng dụng thực sự chạy.

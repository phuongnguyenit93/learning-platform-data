# Đo interpreted expression và compiled expression trên cùng dữ liệu

SpEL có thể đánh giá expression theo hai cách chính: interpreted evaluation, trong đó cây biểu thức được thực thi thông qua cơ chế thông dịch, và compiled evaluation, trong đó một expression đủ điều kiện được biên dịch thành bytecode Java. So sánh hai cách trên cùng dữ liệu giúp xác định compiler có cải thiện thời gian chạy của workload thực tế hay không.

Một phép đo công bằng phải giữ nguyên expression, root object, variables, kiểu dữ liệu, EvaluationContext và số lần đánh giá. Cần tách thời gian parse, tạo context, warm-up và steady-state evaluation. Nếu một bên phải parse hoặc tạo dữ liệu mỗi lần còn bên kia tái sử dụng sẵn, kết quả sẽ không phản ánh riêng khác biệt giữa interpreted và compiled.

## 1. Interpreted và compiled evaluation

Ở chế độ interpreted, SpEL thực thi các node trong cây expression bằng runtime evaluation. Đây là chế độ mặc định và hỗ trợ phạm vi biểu thức rộng.

Ở chế độ compiled, SpEL cố gắng tạo bytecode Java cho expression để giảm chi phí thông dịch trong các lần đánh giá tiếp theo. Compiler cần biết kiểu runtime của các object và chỉ hỗ trợ một tập construct nhất định. Không phải expression nào cũng biên dịch được.

Compiled evaluation có thể hữu ích khi:

- Cùng một expression được đánh giá rất nhiều lần.
- Kiểu root object và các property ổn định.
- Expression dùng các construct mà compiler hỗ trợ.
- Chi phí thông dịch chiếm tỷ trọng đáng kể trong tổng thời gian.
- Các resolver và accessor tùy biến không cản trở đường biên dịch.

Nếu expression chỉ chạy một vài lần hoặc phần lớn thời gian nằm trong database, HTTP call hay method nghiệp vụ, biên dịch SpEL có thể không tạo khác biệt đáng kể.

## 2. Giữ nguyên dữ liệu trong cả hai phép đo

Khi so sánh, hãy dùng cùng một bộ dữ liệu đầu vào:

- Cùng chuỗi expression.
- Cùng kiểu và cùng giá trị root object.
- Cùng giá trị context variables.
- Cùng kiểu dữ liệu cho property và đối số.
- Cùng TypeConverter, PropertyAccessor và resolver nếu có.
- Cùng cách lấy kết quả và kiểu đích.
- Cùng số lần evaluate trong từng giai đoạn.

Ví dụ, nếu expression kiểm tra tổng đơn hàng:

~~~text
total >= #minimum
~~~

hãy dùng cùng một OrderData và cùng minimum cho cả hai chế độ. Không nên dùng một object đơn giản cho interpreted nhưng một object có getter lồng nhau cho compiled.

Tốt nhất là tạo dữ liệu một lần trong setup của benchmark. Cả hai expression có thể được parse riêng bằng hai parser cấu hình khác nhau, nhưng cùng dùng một root object và cùng giá trị biến.

## 3. Chọn expression đại diện

Một expression nhỏ giúp kiểm tra overhead cơ bản:

~~~text
total >= #minimum
~~~

Một expression gần workload thực tế có thể kết hợp vài property và toán tử:

~~~text
active and total >= #minimum and region == #allowedRegion
~~~

Không nên chỉ benchmark một expression cực ngắn rồi kết luận compiler luôn nhanh hơn. Cũng không nên chọn một expression chứa truy vấn database hoặc gọi API rồi quy toàn bộ thời gian cho SpEL.

Hãy chọn các expression đại diện cho rule thực tế, bao gồm kiểu dữ liệu, độ sâu property và toán tử thường dùng. Nếu ứng dụng có nhiều nhóm expression khác nhau, benchmark từng nhóm thay vì gộp chúng thành một con số.

## 4. Cấu hình compiler mode

SpEL compiler được điều khiển bằng SpelCompilerMode trong SpelParserConfiguration.

Ba chế độ thường dùng:

| Chế độ | Hành vi |
|---|---|
| OFF | Không tự động biên dịch; expression được đánh giá theo interpreted mode |
| IMMEDIATE | Thử biên dịch sớm khi có đủ thông tin kiểu |
| MIXED | Bắt đầu bằng interpreted evaluation, sau đó thử biên dịch khi expression được đánh giá đủ nhiều |

OFF là baseline tự nhiên để đo interpreted evaluation. IMMEDIATE phù hợp khi muốn thử compiled evaluation sớm. MIXED phù hợp với ứng dụng có expression được đánh giá lặp lại và muốn runtime tự chuyển đổi theo cơ chế compiler.

Không nên giả định mọi expression ở IMMEDIATE hoặc MIXED chắc chắn đã được biên dịch. Compiler có thể không hỗ trợ một construct hoặc không đủ thông tin kiểu để tạo bytecode.

## 5. Tạo parser cho hai chế độ

Có thể tạo hai SpelExpressionParser với cùng class loader nhưng khác compiler mode:

~~~java
ClassLoader classLoader = OrderData.class.getClassLoader();

SpelParserConfiguration interpretedConfiguration =
        new SpelParserConfiguration(
                SpelCompilerMode.OFF,
                classLoader
        );

SpelParserConfiguration compiledConfiguration =
        new SpelParserConfiguration(
                SpelCompilerMode.IMMEDIATE,
                classLoader
        );

ExpressionParser interpretedParser =
        new SpelExpressionParser(interpretedConfiguration);

ExpressionParser compiledParser =
        new SpelExpressionParser(compiledConfiguration);
~~~

Dùng cùng class loader giúp tránh khác biệt không cần thiết trong việc tạo class đã biên dịch. Trong ứng dụng có class loader riêng, hãy dùng loader phù hợp với các kiểu được tham chiếu trong expression.

Parser cấu hình OFF dùng làm baseline. Parser IMMEDIATE thử biên dịch expression khi runtime có đủ thông tin. Nếu cần đo MIXED, tạo parser thứ ba với cùng cấu hình còn lại và chỉ đổi compiler mode.

## 6. Tạo root object và context giống nhau

Ví dụ root object đơn giản:

~~~java
public class OrderData {

    private final int total;
    private final boolean active;
    private final String region;

    public OrderData(
            int total,
            boolean active,
            String region) {
        this.total = total;
        this.active = active;
        this.region = region;
    }

    public int getTotal() {
        return total;
    }

    public boolean isActive() {
        return active;
    }

    public String getRegion() {
        return region;
    }
}
~~~

Tạo cùng dữ liệu cho hai lần đánh giá:

~~~java
OrderData order = new OrderData(
        250,
        true,
        "APAC"
);

StandardEvaluationContext interpretedContext =
        new StandardEvaluationContext(order);

StandardEvaluationContext compiledContext =
        new StandardEvaluationContext(order);

interpretedContext.setVariable("minimum", 100);
interpretedContext.setVariable("allowedRegion", "APAC");

compiledContext.setVariable("minimum", 100);
compiledContext.setVariable("allowedRegion", "APAC");
~~~

Hai context riêng giúp tránh thay đổi state giữa các phép đo. Cả hai vẫn dùng cùng root object và cùng giá trị variables.

Nếu expression có custom converter hoặc resolver, hãy cấu hình hai context tương đương. Không dùng resolver tùy biến ở một bên nhưng resolver mặc định ở bên còn lại.

## 7. Parse hai Expression từ cùng source

Dùng một chuỗi source duy nhất:

~~~java
String source =
        "active and total >= #minimum and region == #allowedRegion";

Expression interpretedExpression =
        interpretedParser.parseExpression(source);

Expression compiledExpression =
        compiledParser.parseExpression(source);
~~~

Hai Expression là hai instance riêng, vì mỗi parser có compiler mode khác nhau. Tuy nhiên, nội dung source phải giống hệt.

Không đưa parseExpression vào phương thức benchmark evaluate nếu mục tiêu là đo steady-state evaluation. Parse có chi phí riêng và nên được đo trong một benchmark khác.

Nếu production parse expression một lần khi khởi động rồi tái sử dụng, benchmark chính cũng nên tái sử dụng Expression.

## 8. Xác nhận kết quả giống nhau trước khi đo tốc độ

Trước khi so sánh hiệu năng, hãy xác nhận hai cách đánh giá cho kết quả tương đương:

~~~java
Boolean interpretedResult =
        interpretedExpression.getValue(
                interpretedContext,
                Boolean.class
        );

Boolean compiledResult =
        compiledExpression.getValue(
                compiledContext,
                Boolean.class
        );

if (!Objects.equals(
        interpretedResult,
        compiledResult)) {
    throw new IllegalStateException(
            "Interpreted and compiled results differ"
    );
}
~~~

Nếu expression trả về object hoặc số, hãy so sánh theo semantics của kiểu đó. Với BigDecimal, quyết định rõ có so sánh scale hay chỉ so sánh giá trị số.

Kết quả đúng là điều kiện tiên quyết. Một compiled expression nhanh hơn nhưng trả kết quả khác không phải là một tối ưu hợp lệ.

Hãy kiểm tra nhiều input, bao gồm true/false, null nếu được phép, giá trị biên và các kiểu runtime mà ứng dụng thực sự sử dụng.

## 9. Warm-up trước khi lấy số đo

Thời gian đánh giá đầu tiên có thể bao gồm class loading, JIT compilation của JVM, khởi tạo metadata và các chi phí cold-start khác.

Với compiled mode, runtime cũng cần có cơ hội thu thập thông tin kiểu và thử biên dịch expression. Nếu đo ngay lần gọi đầu tiên, kết quả có thể bao gồm cả chi phí chuyển chế độ.

Một quy trình đo nên có:

1. Parse expression ngoài vùng đo steady-state.
2. Tạo root object và context trước khi đo.
3. Chạy warm-up cho cả hai chế độ.
4. Đảm bảo compiled expression đã có cơ hội biên dịch.
5. Chỉ đo sau warm-up.
6. Chạy nhiều iteration và nhiều fork.
7. So sánh phân bố kết quả, không chỉ một lần chạy.

Warm-up của interpreted mode cũng cần thiết vì JVM có thể tối ưu code thông dịch và các method accessor thường dùng.

## 10. Hiểu chi phí biên dịch và chi phí steady-state

Tổng chi phí sử dụng compiled expression có thể gồm:

- Parse expression.
- Các lần interpreted evaluation ban đầu.
- Thời gian compiler tạo bytecode.
- Chi phí class loading cho class được sinh.
- Các lần compiled evaluation sau đó.

Nếu expression chỉ được chạy vài lần, chi phí biên dịch có thể lớn hơn phần thời gian tiết kiệm được.

Với expression chạy hàng nghìn hoặc hàng triệu lần, chi phí khởi tạo có thể được phân bổ trên nhiều lần đánh giá. Khi đó steady-state throughput mới là số đo quan trọng, nhưng vẫn cần xem thời gian khởi động nếu ứng dụng thường xuyên restart hoặc rule thay đổi liên tục.

Hãy đo cả cold-start và steady-state nếu cả hai đều quan trọng với sản phẩm. Đừng gộp chúng thành một số duy nhất mà không nói rõ phạm vi.

## 11. Ví dụ benchmark JMH

JMH phù hợp để đo các thao tác Java nhỏ với warm-up, measurement và fork có kiểm soát.

Ví dụ benchmark:

~~~java
@State(Scope.Thread)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class SpelModeBenchmark {

    private static final String SOURCE =
            "active and total >= #minimum and region == #allowedRegion";

    private Expression interpretedExpression;
    private Expression compiledExpression;

    private EvaluationContext interpretedContext;
    private EvaluationContext compiledContext;

    private OrderData order;

    @Setup(Level.Trial)
    public void setup() {
        ClassLoader loader =
                OrderData.class.getClassLoader();

        SpelExpressionParser interpretedParser =
                new SpelExpressionParser(
                        new SpelParserConfiguration(
                                SpelCompilerMode.OFF,
                                loader
                        )
                );

        SpelExpressionParser compiledParser =
                new SpelExpressionParser(
                        new SpelParserConfiguration(
                                SpelCompilerMode.IMMEDIATE,
                                loader
                        )
                );

        interpretedExpression =
                interpretedParser.parseExpression(SOURCE);

        compiledExpression =
                compiledParser.parseExpression(SOURCE);

        order = new OrderData(250, true, "APAC");

        interpretedContext =
                new StandardEvaluationContext(order);

        compiledContext =
                new StandardEvaluationContext(order);

        interpretedContext.setVariable("minimum", 100);
        interpretedContext.setVariable("allowedRegion", "APAC");

        compiledContext.setVariable("minimum", 100);
        compiledContext.setVariable("allowedRegion", "APAC");

        Boolean interpreted = interpretedExpression.getValue(
                interpretedContext,
                Boolean.class
        );

        Boolean compiled = compiledExpression.getValue(
                compiledContext,
                Boolean.class
        );

        if (!Objects.equals(interpreted, compiled)) {
            throw new IllegalStateException("Results differ");
        }
    }

    @Benchmark
    public Boolean interpreted() {
        return interpretedExpression.getValue(
                interpretedContext,
                Boolean.class
        );
    }

    @Benchmark
    public Boolean compiled() {
        return compiledExpression.getValue(
                compiledContext,
                Boolean.class
        );
    }
}
~~~

JMH warm-up cho benchmark compiled tạo cơ hội để compiler chuyển expression sang bytecode. Tuy nhiên, nếu expression không đủ điều kiện biên dịch, phương thức compiled vẫn có thể chạy theo interpreted path. Cần xác nhận khả năng biên dịch thay vì chỉ dựa vào tên compiler mode.

Ví dụ chỉ minh họa cấu trúc benchmark. Hãy dùng phiên bản JMH và Spring tương ứng với dự án, đồng thời bổ sung các kiểu dữ liệu và expression đại diện cho workload thực tế.

## 12. Đo parse riêng nếu cần

Nếu ứng dụng tạo expression động thường xuyên, parse cost có thể đáng kể. Khi đó, tạo benchmark riêng cho parse:

~~~java
@Benchmark
public Expression parseExpression() {
    return parser.parseExpression(SOURCE);
}
~~~

Benchmark này đo việc tạo Expression từ source. Không dùng kết quả đó để kết luận compiled evaluation nhanh hay chậm.

Có thể có ba số đo riêng:

| Benchmark | Phạm vi |
|---|---|
| Parse | Tạo Expression từ source |
| Context setup | Tạo EvaluationContext và gắn root/variables |
| Evaluate | Chạy Expression đã parse với context có sẵn |

Nếu production cache Expression nhưng tạo context theo request, benchmark evaluate và context setup cần được xem riêng để phản ánh kiến trúc thật.

## 13. Kiểm tra expression có biên dịch được hay không

Compiler chỉ hỗ trợ một tập construct và kiểu truy cập. Một expression có thể chạy đúng ở interpreted mode nhưng không thể compile.

Các yếu tố có thể ảnh hưởng:

- Kiểu runtime không ổn định.
- Property hoặc method được truy cập qua resolver tùy biến.
- Construct SpEL không nằm trong tập compiler hỗ trợ.
- Kiểu trả về hoặc kiểu trung gian không thể xác định.
- Class loader không thể truy cập class cần thiết.
- Object thay đổi cấu trúc hoặc kiểu giữa các lần evaluate.

Trong các phiên bản có API SpelExpression.compileExpression(), có thể thử biên dịch tường minh và kiểm tra giá trị Boolean trả về để biết thao tác compile có thành công hay không:

~~~java
SpelExpression spelExpression =
        (SpelExpression) parser.parseExpression(SOURCE);

boolean compiled = spelExpression.compileExpression();

if (!compiled) {
    // Expression không được biên dịch thành công.
}
~~~

API và khả năng compile cần được xác nhận theo phiên bản Spring đang dùng. Không nên ép expression vào compiled path nếu compiler không hỗ trợ construct của nó.

Hãy giữ interpreted mode làm baseline hợp lệ cho mọi expression cần hỗ trợ.

## 14. Ý nghĩa của IMMEDIATE và MIXED khi có lỗi

IMMEDIATE ưu tiên biên dịch sớm. Nếu compiled form được sử dụng nhưng không thể thực thi với kiểu runtime thực tế, lỗi có thể được truyền ra thay vì tự động quay lại interpreted mode.

MIXED được thiết kế linh hoạt hơn: nếu compiled form gặp vấn đề trong quá trình thực thi, runtime có thể quay lại interpreted evaluation và tiếp tục theo cơ chế của compiler mode này.

Điều đó không có nghĩa MIXED luôn nhanh hơn hoặc tự sửa mọi lỗi. Việc fallback có thể làm một số lần đánh giá chậm hơn và cần được quan sát trong benchmark.

Nếu ứng dụng dùng nhiều kiểu root object hoặc expression có tính động cao, hãy kiểm thử cả các kiểu runtime khác nhau. Đừng chỉ benchmark trường hợp compile thành công với một object rồi kết luận cho mọi dữ liệu.

## 15. So sánh throughput và latency

Throughput đo số lần đánh giá hoàn thành trong một đơn vị thời gian. Latency đo thời gian cho một lần đánh giá hoặc một request.

Hai số đo có thể kể những câu chuyện khác nhau. Compiled mode có thể tăng throughput trong workload lặp lại nhưng không cải thiện đáng kể latency của request vốn bị chi phối bởi database hoặc network.

Nên theo dõi:

- Operations per second.
- Average time nếu benchmark tool cung cấp.
- Median và các percentile như p95, p99 trong benchmark phù hợp.
- CPU usage.
- Allocation rate và garbage collection.
- Thời gian warm-up và thời điểm compiler kích hoạt.
- Tỷ lệ expression compile thành công.

Không chỉ nhìn một con số trung bình. Một thay đổi có thể cải thiện trung bình nhưng làm tail latency xấu hơn do compilation hoặc fallback xảy ra trong request.

## 16. Tránh các sai lệch thường gặp

Một số lỗi làm phép đo không công bằng:

| Sai lệch | Vì sao kết quả sai | Cách khắc phục |
|---|---|---|
| Một bên parse mỗi lần | Gộp parse cost vào evaluate | Parse cả hai trước benchmark |
| Dùng input khác nhau | Workload không tương đương | Dùng cùng root object và variables |
| Chỉ đo lần đầu | Bao gồm class loading và compilation | Warm-up trước measurement |
| Compiled expression chưa compile | So sánh interpreted với interpreted | Xác nhận compile eligibility |
| Một bên dùng custom converter | Khác đường chuyển đổi | Cấu hình context tương đương |
| Chỉ đo một expression rất nhỏ | Không đại diện workload | Dùng bộ expression thực tế |
| Chạy một lần trên máy bận | Nhiễu hệ thống lớn | Nhiều fork, iteration và môi trường ổn định |
| Gộp parse, context và evaluate | Không biết chi phí nằm ở đâu | Benchmark từng giai đoạn |
| Bỏ qua kết quả trả về | JVM có thể tối ưu công việc không được quan sát | Trả kết quả hoặc tiêu thụ bằng Blackhole |
| Chỉ so sánh trung bình | Che khuất tail latency và biến động | Xem phân bố và nhiều lần chạy |

Hãy ghi lại phiên bản JDK, Spring Framework, JVM flags, CPU, hệ điều hành và cấu hình benchmark để có thể lặp lại phép đo.

## 17. Đo với resolver và converter tùy biến

Nếu production dùng custom PropertyAccessor, MethodResolver hoặc TypeConverter, benchmark nên dùng đúng các thành phần đó. Nếu không, kết quả có thể quá lạc quan.

Tuy nhiên, hãy tách benchmark cơ sở và benchmark production-like:

1. Baseline chỉ dùng property access và phép toán đơn giản.
2. Benchmark có converter tùy biến.
3. Benchmark có accessor hoặc resolver tùy biến.
4. Benchmark với expression đầy đủ và dữ liệu đại diện.

Cách này giúp xác định chi phí tăng thêm đến từ extension nào.

Nếu custom resolver không được compiler hỗ trợ, compiled mode có thể không áp dụng được cho expression đó. Không loại bỏ resolver cần thiết chỉ để có một benchmark đẹp hơn; hãy đo trên cấu hình mà ứng dụng thực sự phải chạy.

## 18. Cân nhắc collection operation

Selection và projection có thể duyệt nhiều phần tử. Nếu expression chạy trên collection lớn, số phần tử và logic predicate thường ảnh hưởng mạnh đến tổng thời gian.

Ví dụ:

~~~text
orders.?[active and total >= #minimum]
~~~

Khi so sánh interpreted và compiled, dùng cùng collection, cùng thứ tự phần tử và cùng predicate. Đo nhiều kích thước collection nếu đó là workload thực tế.

Không để method trong predicate truy vấn database hoặc gọi API. Nếu một phần tử kích hoạt một truy vấn, chi phí I/O sẽ lấn át khác biệt giữa interpreter và compiler.

Nếu collection rất lớn, cân nhắc lọc ở repository hoặc service trước khi đưa kết quả vào SpEL.

## 19. Diễn giải kết quả benchmark

Kết quả cần được đọc cùng bối cảnh:

- Nếu compiled nhanh hơn rõ rệt ở steady-state, expression có thể hưởng lợi khi được đánh giá thường xuyên.
- Nếu chênh lệch nhỏ, parse, context setup hoặc method execution có thể chiếm phần lớn chi phí.
- Nếu compiled không chạy được, expression hoặc resolver có thể không đủ điều kiện compile.
- Nếu cold-start chậm hơn nhưng steady-state nhanh hơn, quyết định phụ thuộc số lần expression được đánh giá trong vòng đời thực tế.
- Nếu MIXED có các đợt latency tăng, hãy xem thời điểm compile hoặc fallback.
- Nếu một kiểu root object chạy nhanh nhưng kiểu khác lỗi, expression có thể phụ thuộc kiểu runtime đã được quan sát khi compile.

Không có một tỷ lệ tăng tốc chung cho mọi expression. Chỉ áp dụng kết quả benchmark cho các kiểu expression, dữ liệu và môi trường đã được đo.

## 20. Checklist cho một phép so sánh có thể lặp lại

Trước khi chấp nhận kết luận:

1. Dùng cùng source expression.
2. Dùng cùng root object và variables.
3. Dùng cùng kiểu dữ liệu và kích thước collection.
4. Dùng context có cấu hình accessor, resolver và converter tương đương.
5. Parse hai expression ngoài vùng đo steady-state.
6. Xác nhận kết quả logic giống nhau.
7. Warm-up đủ để JVM và SpEL compiler ổn định.
8. Xác nhận expression thực sự có thể compile.
9. Đo parse, setup và evaluate riêng.
10. Chạy nhiều iteration và fork.
11. Ghi nhận throughput, latency và allocation.
12. Lặp lại trên workload đại diện production.
13. Kiểm tra trường hợp compiler không hỗ trợ hoặc kiểu runtime thay đổi.
14. Không đánh đổi correctness hoặc giới hạn bảo mật để đạt tốc độ.

## 21. Ghi nhớ

Interpreted mode là baseline mặc định và hỗ trợ phạm vi expression rộng. Compiled mode có thể giảm chi phí evaluate lặp lại bằng bytecode Java, nhưng chỉ có lợi khi expression đủ điều kiện compile và số lần chạy đủ lớn để bù chi phí warm-up, compilation và class loading.

Để so sánh công bằng, dùng cùng source, root object, variables, kiểu dữ liệu, context và kết quả mong đợi. Parse expression và tạo dữ liệu ngoài vùng đo steady-state; warm-up cả hai chế độ; xác nhận expression có thể compile; đo parse, context setup và evaluate riêng.

OFF dùng làm baseline interpreted, IMMEDIATE thử biên dịch sớm, còn MIXED cho phép chuyển đổi linh hoạt hơn khi compiled form gặp vấn đề. Hãy dùng JMH hoặc công cụ benchmark phù hợp, đo nhiều iteration/fork và xem cả throughput, latency, allocation cùng hành vi fallback. Chỉ chọn compiler mode sau khi kết quả được xác nhận trên workload thực tế và cùng yêu cầu correctness.
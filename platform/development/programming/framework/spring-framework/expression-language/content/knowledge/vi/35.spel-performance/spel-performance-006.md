# Expression compiler và tiêu chí đo hiệu quả của SpEL

Spring Expression Language (SpEL) có thể đánh giá expression theo hai cách: **interpreted** (thông dịch) và **compiled** (biên dịch thành bytecode). Ở chế độ thông dịch, SpEL duyệt cấu trúc expression và thực hiện từng thao tác trong lúc chạy. Khi biên dịch được, SpEL tạo bytecode để những lần đánh giá sau thực thi trực tiếp hơn, có thể giảm chi phí lặp lại.

Compiler không làm mọi expression nhanh hơn và cũng không hỗ trợ mọi cấu trúc SpEL. Hiệu quả phụ thuộc vào số lần đánh giá, độ ổn định của kiểu dữ liệu, cấu trúc expression và chi phí của các method được gọi. Cần đo trên workload đại diện trước khi bật compiler trong ứng dụng.

## 1. Interpreted evaluation và compiled evaluation

Khi parse một expression, SpEL tạo một cấu trúc biểu diễn expression. Ở chế độ interpreted, mỗi lần đánh giá, SpEL sử dụng cấu trúc đó để thực hiện các thao tác như đọc property, gọi method, tính toán và chuyển đổi kiểu.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression =
            parser.parseExpression("customer.age >= 18");

    Boolean result = expression.getValue(context, Boolean.class);

Ở interpreted mode, expression được thực thi thông qua cơ chế đánh giá của SpEL. Nếu cùng một Expression được đánh giá nhiều lần, framework vẫn phải thực hiện các bước diễn giải tương ứng.

SpEL compiler có thể tạo một class Java được sinh tại runtime, chứa bytecode biểu diễn hành vi của expression. Sau khi compile thành công, các lần đánh giá tiếp theo có thể chạy compiled form thay vì đi qua toàn bộ đường interpreted.

Compiler tối ưu **evaluation**, không thay thế việc parse expression và không tự tối ưu các method bên ngoài mà expression gọi. Nếu expression gọi một method truy vấn database mất nhiều mili giây, việc giảm chi phí diễn giải SpEL có thể không đáng kể so với thời gian của database.

## 2. Khi nào compilation có lợi?

Compilation thường có lợi khi:

- Cùng một Expression được tái sử dụng nhiều lần.
- Expression được đánh giá thường xuyên trong một luồng xử lý nóng.
- Các kiểu object và property được truy cập ổn định giữa các lần đánh giá.
- Chi phí diễn giải là phần đáng kể trong tổng thời gian xử lý.
- Expression sử dụng các thao tác nằm trong tập cấu trúc mà compiler hỗ trợ.

Compilation thường ít có lợi khi expression chỉ chạy một vài lần, phần lớn thời gian nằm ở I/O hoặc method bên ngoài, hoặc expression thay đổi liên tục khiến chi phí parse/compile không được phân bổ qua đủ số lần đánh giá.

Nếu mỗi request tạo parser và parse lại cùng một chuỗi, chi phí đó có thể lớn hơn phần tiết kiệm từ compiled evaluation. Hãy tái sử dụng Expression khi phù hợp và đo riêng chi phí parse, lần đánh giá đầu tiên, compilation và các lần đánh giá ổn định.

## 3. Các chế độ SpEL compiler

SpEL cung cấp ba chế độ qua enum `SpelCompilerMode`:

| Chế độ | Hành vi |
|---|---|
| `OFF` | Không sử dụng compiler; đây là mặc định |
| `IMMEDIATE` | Thử compile sau lần interpreted evaluation đầu tiên |
| `MIXED` | Ban đầu diễn giải, sau một số lần đánh giá thì thử compile; có thể quay lại interpreted nếu compiled form gặp lỗi runtime |

**OFF** phù hợp khi muốn hành vi interpreted nhất quán hoặc chưa có bằng chứng compilation mang lại lợi ích.

**IMMEDIATE** phù hợp khi expression có kiểu ổn định và ứng dụng muốn chuyển sang compiled evaluation sớm. Lần đầu vẫn cần interpreted evaluation để thu thập thông tin cần thiết cho compilation. Nếu compiled form sau đó ném exception, lỗi được chuyển tới caller; chế độ này không tự động quay về interpreted để che lỗi.

**MIXED** phù hợp hơn khi kiểu runtime có thể thay đổi hoặc chưa chắc compiled form luôn áp dụng được. Framework có thể chuyển lại interpreted mode nếu compiled expression thất bại và thử compile lại sau đó. Việc chuyển chế độ này có thể làm thời gian đánh giá biến động, vì vậy cần kiểm tra cả hiệu năng lẫn tính đúng đắn.

Không nên dựa vào một ngưỡng số lần đánh giá cố định cho MIXED nếu không có cam kết từ phiên bản Spring đang dùng. Hãy xem hành vi của phiên bản framework cụ thể và đo trong môi trường thực tế.

## 4. Cấu hình compiler qua SpelParserConfiguration

Compiler mode được cấu hình khi tạo parser bằng `SpelParserConfiguration`:

    ClassLoader classLoader =
            Order.class.getClassLoader();

    SpelParserConfiguration configuration =
            new SpelParserConfiguration(
                    SpelCompilerMode.IMMEDIATE,
                    classLoader
            );

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

    Expression expression =
            parser.parseExpression("total * taxRate");

    BigDecimal result =
            expression.getValue(context, BigDecimal.class);

Ví dụ dùng IMMEDIATE. Để tắt compiler, có thể dùng `SpelCompilerMode.OFF`; để dùng chế độ thích ứng, dùng `SpelCompilerMode.MIXED`.

ClassLoader truyền vào cấu hình được dùng để nạp class bytecode do compiler sinh ra. Nó cần nhìn thấy các kiểu mà expression tham chiếu. Trong ứng dụng có plugin, module, classloader riêng hoặc hot reload, hãy chọn classloader phù hợp với vòng đời của các domain class được dùng trong context.

Compiler mode thuộc parser configuration. Khi so sánh các chế độ, nên tạo parser và Expression tương ứng riêng cho từng chế độ để tránh trộn trạng thái compilation giữa các lần đo.

## 5. Compilation diễn ra sau khi có thông tin runtime

SpEL compiler dựa vào thông tin thu được khi expression được đánh giá. Vì vậy, expression thường cần ít nhất một interpreted evaluation trước khi có thể compile.

Ví dụ:

    Expression expression =
            parser.parseExpression("customer.age + 1");

    Integer first =
            expression.getValue(context, Integer.class);

    Integer second =
            expression.getValue(context, Integer.class);

Ở chế độ compiler phù hợp, lần đánh giá đầu tiên cung cấp thông tin về kiểu target và kết quả; các lần tiếp theo có thể dùng compiled form nếu expression đủ điều kiện.

Đừng coi việc tạo Expression hoặc parse thành công là bằng chứng rằng expression đã được compile. Parse và compile là các giai đoạn khác nhau. Một expression có thể parse và chạy interpreted bình thường nhưng không thuộc tập cấu trúc mà compiler hỗ trợ.

Một số API cụ thể của SpEL cho phép yêu cầu compile hoặc quay về interpreted mode thông qua implementation `SpelExpression`. Nếu dùng API mức thấp này, hãy kiểm tra tài liệu đúng phiên bản Spring và xử lý trường hợp compilation không thành công; không giả định mọi Expression đều có thể compile.

## 6. Những giới hạn cần biết

SpEL compiler chỉ hỗ trợ một tập con các dạng expression. Khả năng compile phụ thuộc phiên bản Spring và các node có trong expression. Một số cấu trúc động hoặc thao tác collection như selection và projection có thể tiếp tục chạy interpreted.

Không nên dựa vào việc expression có cú pháp đơn giản để kết luận chắc chắn nó compile được. Cần xác nhận trên đúng phiên bản framework và context thực tế.

Các yếu tố có thể ảnh hưởng:

- Node trong expression có hỗ trợ sinh bytecode hay không.
- Kiểu runtime của root object và các property có ổn định không.
- Method được gọi có chữ ký và kiểu trả về phù hợp qua các lần đánh giá không.
- Property có lúc null, lúc khác kiểu hoặc thay đổi cấu trúc không.
- ClassLoader có nhìn thấy các kiểu cần thiết không.
- Expression có dùng collection operation hoặc cấu trúc động không.

Nếu compiler không thể tạo compiled form, expression vẫn có thể hoạt động ở interpreted mode. Điều đó không nhất thiết là lỗi nghiệp vụ; chỉ có nghĩa compiler không áp dụng được cho expression đó.

## 7. Ổn định kiểu runtime và lỗi khi compiled form chạy

Compiled expression có thể dựa trên kiểu runtime quan sát được trong quá trình diễn giải. Nếu những lần đánh giá sau đưa vào object có kiểu khác hoặc giá trị có hình dạng không tương thích, compiled code có thể thất bại.

Ví dụ, một expression được đánh giá lần đầu với một loại Customer có property `age` là Integer, nhưng lần sau root object lại là một implementation khác hoặc property trả về kiểu khác. Compiled form có thể không xử lý được tình huống đó như interpreted evaluator.

Các trường hợp cần chú ý:

- Root object thay đổi giữa nhiều class không tương thích.
- Property có lúc trả null, lúc trả object thuộc kiểu khác.
- Method overload hoặc kiểu trả về khác nhau theo target.
- Collection chứa phần tử thuộc nhiều kiểu.
- Dữ liệu thay đổi làm một đường truy cập không còn hợp lệ.
- Class được nạp từ classloader khác sau khi expression đã compile.

Nếu kiểu đầu vào biến động đáng kể, MIXED có thể phù hợp hơn IMMEDIATE vì có cơ chế quay lại interpreted khi compiled execution lỗi. Tuy vậy, fallback không thay thế kiểm thử; ứng dụng vẫn cần xác định kết quả và exception có đúng hợp đồng hay không.

## 8. ClassLoader và vòng đời ứng dụng

Compiler tạo bytecode tại runtime và cần một ClassLoader có thể định nghĩa, nạp class được sinh cũng như truy cập các class mà expression sử dụng.

Trong ứng dụng đơn giản, classloader của domain class thường là lựa chọn phù hợp. Với ứng dụng dùng plugin, application server, nhiều module hoặc DevTools reload, classloader có thể thay đổi theo vòng đời context.

Nếu compiled expression giữ tham chiếu tới classloader cũ trong khi ứng dụng đã reload domain class, có thể phát sinh lỗi kiểu dữ liệu hoặc vấn đề vòng đời classloader. Hãy tạo lại parser và Expression khi context hoặc classloader liên quan được thay thế; tránh giữ compiled expression lâu hơn vòng đời của các kiểu mà nó phụ thuộc.

Không chọn classloader chỉ dựa vào việc compile thành công trong một test nhỏ. Hãy kiểm tra cách ứng dụng triển khai và nạp class trong môi trường chạy thực tế.

## 9. Tái sử dụng Expression để phân bổ chi phí

Nếu một expression được dùng nhiều lần, hãy parse một lần và tái sử dụng đối tượng Expression khi phù hợp:

    ExpressionParser parser =
            new SpelExpressionParser(configuration);

    Expression expression =
            parser.parseExpression(
                    "#order.total >= #minimum"
            );

    Boolean evaluate(
            Order order,
            BigDecimal minimum,
            EvaluationContext context) {

        context.setVariable("order", order);
        context.setVariable("minimum", minimum);

        return expression.getValue(context, Boolean.class);
    }

Đây là ví dụ minh họa về vòng đời Expression; context và dữ liệu mutable phải được quản lý an toàn theo từng request hoặc thread. Không chia sẻ một EvaluationContext đang bị thay đổi đồng thời giữa nhiều luồng.

Nếu expression được tạo từ cấu hình động, có thể cache theo chuỗi expression hoặc một mã cấu hình có phiên bản. Cache cần có giới hạn kích thước và chính sách invalidation khi cấu hình hoặc classloader thay đổi. Không để người dùng tạo số lượng expression không giới hạn làm cache tăng vô hạn.

## 10. Tiêu chí đo hiệu quả đúng cách

Một benchmark hữu ích phải trả lời được liệu compiler có giảm chi phí của workload thật hay không. Không chỉ đo một lần gọi `getValue()` rồi kết luận.

Nên đo riêng:

1. **Parse cost:** thời gian tạo Expression từ chuỗi.
2. **First evaluation:** chi phí đánh giá đầu tiên, bao gồm diễn giải và hoạt động chuẩn bị compilation nếu có.
3. **Compilation cost:** phần overhead để sinh và nạp bytecode, nếu có thể đo tách biệt trong harness.
4. **Steady-state evaluation:** thời gian hoặc throughput sau warm-up khi compiled form đã được dùng.
5. **Allocation và GC:** lượng object tạo ra và ảnh hưởng tới garbage collection.
6. **Tail latency:** độ trễ p95/p99 nếu ứng dụng nhạy với latency.

Hãy so sánh OFF, IMMEDIATE và MIXED với cùng expression, cùng dữ liệu, cùng EvaluationContext và cùng môi trường JVM. Đảm bảo kết quả được tiêu thụ để JIT hoặc benchmark harness không loại bỏ công việc cần đo.

## 11. Dùng JMH thay cho vòng lặp đo thủ công

JMH là công cụ phù hợp để đo microbenchmark Java. Một benchmark tối giản có thể có dạng:

    @State(Scope.Thread)
    public class SpelBenchmark {

        private EvaluationContext context;
        private Expression expression;

        @Setup(Level.Trial)
        public void setup() {
            SpelParserConfiguration config =
                    new SpelParserConfiguration(
                            SpelCompilerMode.IMMEDIATE,
                            getClass().getClassLoader()
                    );

            ExpressionParser parser =
                    new SpelExpressionParser(config);

            expression = parser.parseExpression(
                    "#root.total >= #minimum"
            );

            context = new StandardEvaluationContext(
                    new OrderView(new BigDecimal("150"))
            );
            context.setVariable(
                    "minimum",
                    new BigDecimal("100")
            );
        }

        @Benchmark
        public Object evaluate() {
            return expression.getValue(context);
        }
    }

Đây là khung minh họa; benchmark thực tế nên có các cấu hình riêng cho OFF, IMMEDIATE và MIXED, đồng thời tách setup khỏi phần được đo. Dùng `@Warmup`, `@Measurement` và nhiều fork để giảm ảnh hưởng của khởi động JVM và JIT.

Với MIXED, warm-up phải đủ để expression đi qua giai đoạn interpreted và đạt trạng thái ổn định có thể đo. Không dùng thời gian của vài invocation đầu làm đại diện cho steady state.

Tránh viết một vòng lặp `System.nanoTime()` duy nhất trong test thông thường. Kết quả dễ bị nhiễu bởi JIT, GC, scheduler, dead-code elimination và trạng thái JVM giữa các lần chạy.

## 12. Chọn workload đại diện

Benchmark cần phản ánh cách expression được dùng trong ứng dụng:

- Expression có độ phức tạp tương đương production.
- Root object, variables và property có kiểu giống dữ liệu thật.
- Số lần đánh giá và tỷ lệ cache/reuse tương đương thực tế.
- Collection có kích thước và kiểu phần tử phù hợp.
- Method được gọi bên trong expression có chi phí tương đương production.
- Tỷ lệ null, kiểu thay đổi và dữ liệu biên được đại diện.
- Cấu hình JVM, JDK, Spring và classloader giống môi trường mục tiêu.

Nên có ít nhất một benchmark expression tính toán đơn giản, một expression đọc nested property hoặc gọi method, và một workload gần với use case thực tế. Không dùng một biểu thức số học nhỏ để suy ra toàn bộ ứng dụng sẽ nhanh hơn cùng tỷ lệ.

Nếu expression chủ yếu gọi database hoặc API, hãy đo cả thời gian end-to-end. Khi đó, compiled evaluation có thể cải thiện microbenchmark nhưng gần như không thay đổi latency người dùng.

## 13. Đọc kết quả và tính điểm hòa vốn

Compilation có chi phí ban đầu. Lợi ích chỉ xuất hiện khi số lần đánh giá đủ lớn để phần tiết kiệm trên mỗi lần gọi bù được chi phí compile.

Có thể ước lượng điểm hòa vốn:

    breakEvenEvaluations =
        compileOverhead /
        (interpretedTimePerCall - compiledTimePerCall)

Công thức chỉ có ý nghĩa khi thời gian interpreted mỗi lần lớn hơn thời gian compiled mỗi lần và các số đo được lấy từ workload ổn định. Nó là ước lượng, không thay thế benchmark end-to-end.

Khi đọc kết quả, hãy xem:

- Throughput tăng bao nhiêu phần trăm?
- Average time và p95/p99 thay đổi thế nào?
- Compilation overhead mất bao lâu để được bù lại?
- Allocation và GC có tăng không?
- Có expression nào không compile được hoặc phải fallback không?
- Có lỗi runtime xuất hiện khi kiểu dữ liệu thay đổi không?
- Mức cải thiện có đủ lớn để đáng thêm độ phức tạp vận hành không?

Không chỉ nhìn một con số trung bình. Một chế độ có throughput tốt hơn nhưng tail latency dao động hoặc fallback thường xuyên có thể không phù hợp với hệ thống nhạy latency.

## 14. Kiểm thử tính đúng đắn giữa interpreted và compiled

Trước khi bật compiler, hãy so sánh kết quả và hành vi của expression trong các chế độ:

1. Cùng input tạo cùng kết quả.
2. Giá trị null được xử lý theo đúng hợp đồng.
3. Kiểu runtime khác nhau không gây lỗi ngoài dự kiến.
4. Method overload và TypeConverter hoạt động nhất quán.
5. Exception được phát sinh đúng trường hợp.
6. Expression không compile được vẫn có đường interpreted phù hợp.
7. MIXED fallback không làm thay đổi kết quả nghiệp vụ.
8. ClassLoader của môi trường test giống môi trường triển khai cần xác nhận.

Kiểm thử cả giá trị biên và dữ liệu production-like. Nếu expression đọc property lồng nhau, thử object trung gian null. Nếu expression gọi method, thử các kiểu đối số và trạng thái method có thể gặp. Nếu expression chạy trên collection, thử collection rỗng và phần tử có kiểu khác nhau.

Compilation là tối ưu hóa thực thi; nó không được phép làm thay đổi hợp đồng chức năng mà ứng dụng mong đợi.

## 15. Các lỗi đánh giá hiệu năng thường gặp

- **Chỉ đo lần gọi đầu tiên:** kết quả bao gồm parse, warm-up hoặc compile overhead, không đại diện steady state.
- **Không tái sử dụng Expression:** benchmark chủ yếu đo parser thay vì compiler.
- **Warm-up quá ngắn:** MIXED chưa chuyển sang compiled mode hoặc JVM chưa ổn định.
- **Dùng dữ liệu quá đơn giản:** không phản ánh kiểu, null, collection và method trong production.
- **Bỏ qua compile overhead:** không tính số lần gọi cần để bù chi phí ban đầu.
- **Đo bằng một vòng lặp tự viết:** dễ bị nhiễu bởi JIT, GC và dead-code elimination.
- **Chỉ đo throughput:** bỏ qua latency tail, allocation và fallback.
- **Giả định mọi expression compile được:** một số node không nằm trong tập hỗ trợ.
- **Bỏ qua classloader:** expression có thể chạy trong test nhưng lỗi trong môi trường reload hoặc plugin.
- **Coi compiler là giải pháp cho I/O chậm:** compiler chỉ tối ưu phần đánh giá SpEL, không làm database hoặc API tự nhanh hơn.

## 16. Quy trình quyết định bật compiler

Một quy trình thực tế:

1. Xác định expression nào được đánh giá thường xuyên và chiếm chi phí đáng kể.
2. Tái sử dụng parser/Expression thay vì parse lại trong đường nóng.
3. Đo baseline với `SpelCompilerMode.OFF`.
4. Kiểm tra expression có thuộc tập được compiler hỗ trợ và kiểu dữ liệu có ổn định không.
5. Đo IMMEDIATE và MIXED bằng benchmark có warm-up.
6. Kiểm thử tính đúng đắn với dữ liệu biên và thay đổi kiểu.
7. Kiểm tra classloader, vòng đời context và hành vi fallback.
8. Chỉ triển khai khi lợi ích đo được có ý nghĩa với workload thực tế.

Nếu không có bằng chứng rằng evaluation SpEL là nút thắt, giữ OFF là lựa chọn hợp lý. Đơn giản hóa expression, cache Expression và giảm số lần đánh giá thường là những bước nên đo trước khi thêm compilation.

## 17. Ghi nhớ

SpEL compiler sinh bytecode để giảm chi phí đánh giá lặp lại; nó không thay thế parser và không tối ưu các thao tác I/O bên ngoài expression. `OFF` tắt compiler, `IMMEDIATE` thử compile sau lần interpreted evaluation đầu tiên và không tự fallback khi compiled execution lỗi, còn `MIXED` có thể quay lại interpreted khi compiled form thất bại. Compilation chỉ áp dụng cho một tập expression và phụ thuộc độ ổn định kiểu runtime cùng ClassLoader. Hãy tái sử dụng Expression, đo riêng parse/first evaluation/steady state, dùng JMH với warm-up và workload đại diện, kiểm tra allocation, tail latency và tính đúng đắn. Chỉ bật compiler khi benchmark cho thấy lợi ích đủ lớn trong môi trường triển khai thực tế.

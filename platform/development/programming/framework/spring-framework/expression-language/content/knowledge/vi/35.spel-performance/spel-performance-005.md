# Ảnh hưởng của conversion và resolver tùy biến

SpEL có thể mở rộng bằng TypeConverter, PropertyAccessor, MethodResolver, TypeLocator, BeanResolver và các thành phần tùy biến khác. Những extension này giúp biểu thức làm việc với kiểu dữ liệu và mô hình object riêng của ứng dụng, nhưng cũng có thể làm tăng chi phí đánh giá. Một expression đơn giản có thể trở nên chậm nếu mỗi lần chạy phải thử nhiều accessor, tìm method qua nhiều resolver hoặc thực hiện conversion tốn kém.

Khi tối ưu, cần phân biệt chi phí parse expression, chi phí thiết lập context và chi phí evaluate từng lần. Cũng cần xác định thành phần nào thực sự nằm trên đường chạy nóng. Đừng mặc định custom resolver luôn chậm hoặc luôn nhanh hơn resolver mặc định; hiệu năng phụ thuộc cách triển khai, thứ tự đăng ký, cache, kiểu object và số lần expression được đánh giá.

## 1. Các giai đoạn tạo chi phí

Một lần xử lý SpEL có thể phát sinh chi phí ở nhiều giai đoạn:

| Giai đoạn | Công việc | Yếu tố ảnh hưởng |
|---|---|---|
| Parse | Phân tích chuỗi và tạo Expression | Độ dài, độ phức tạp cú pháp, số lần parse |
| Tạo context | Đặt root object, variables, accessors và resolvers | Số thành phần, việc tạo object lặp lại |
| Property access | Đọc hoặc ghi property | Accessor, reflection, cache, getter |
| Method resolution | Tìm method phù hợp | Số resolver, số overload, kiểu đối số |
| Type conversion | Chuyển giá trị sang kiểu đích | Converter lookup và logic converter |
| Bean/type resolution | Phân giải bean hoặc class | Resolver, TypeLocator, class loading |
| Evaluate | Thực hiện các phép toán và collection operation | Số bước, kích thước dữ liệu, method được gọi |

Một expression được parse một lần rồi evaluate hàng nghìn lần có hồ sơ hiệu năng khác với expression được parse lại trong từng request. Vì vậy, trước khi tối ưu resolver, hãy đo xem chi phí thực tế nằm ở parse, context setup hay evaluate.

## 2. Chi phí của TypeConverter

TypeConverter được dùng khi SpEL cần chuyển một giá trị sang kiểu đích, chẳng hạn typed getValue, gán property bằng setValue hoặc chuẩn bị đối số cho method invocation.

Ví dụ:

~~~java
Expression expression = parser.parseExpression("#rawAmount");

BigDecimal amount = expression.getValue(
        context,
        BigDecimal.class
);
~~~

Nếu rawAmount có kiểu String, SpEL có thể yêu cầu TypeConverter chuyển String thành BigDecimal. Conversion thường gồm việc tìm converter phù hợp và chạy logic chuyển đổi.

Một converter tùy biến có thể làm tăng chi phí nếu nó:

- Thực hiện truy vấn database hoặc gọi API.
- Phân tích chuỗi phức tạp lặp lại.
- Tạo nhiều object trung gian.
- Dùng reflection hoặc tra cứu metadata không có cache.
- Thực hiện validation hoặc logic nghiệp vụ không thuộc trách nhiệm conversion.

Converter nên tập trung chuyển đổi kiểu. Không nên dùng nó để truy vấn dữ liệu, kiểm tra quyền hoặc thực hiện I/O. Những công việc đó có chi phí lớn và làm conversion khó dự đoán.

## 3. Thiết kế converter nhẹ và có thể dự đoán

Một converter tốt có đầu vào, đầu ra và quy tắc rõ ràng. Nó nên tránh side effect và không phụ thuộc trạng thái bên ngoài nếu không cần.

Ví dụ converter cho mã tài khoản:

~~~java
public record AccountCode(String value) {
}

public class StringToAccountCodeConverter
        implements Converter<String, AccountCode> {

    @Override
    public AccountCode convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException(
                    "Account code is required"
            );
        }

        return new AccountCode(source.trim());
    }
}
~~~

Logic này chỉ chuẩn hóa chuỗi và tạo value object. Nó không truy vấn repository hoặc gọi service khác.

Nếu conversion cần tra cứu một thực thể trong database, hãy cân nhắc lấy thực thể trước rồi truyền vào context thay vì đặt truy vấn bên trong converter. Khi converter chạy nhiều lần trong collection operation hoặc method invocation, I/O ẩn có thể tạo N+1 query và làm thời gian evaluate tăng mạnh.

Nếu một phép chuyển đổi có thể được tính trước, hãy chuẩn hóa dữ liệu trước khi đưa vào EvaluationContext.

## 4. Tránh conversion lặp lại không cần thiết

Nếu cùng một giá trị được dùng nhiều lần trong expression, hãy xem có thể chuyển đổi trước một lần trong Java hay không.

Ví dụ, thay vì truyền chuỗi vào nhiều lời gọi cần BigDecimal:

~~~text
#calculateTax(#rawAmount)
#calculateFee(#rawAmount)
#calculateDiscount(#rawAmount)
~~~

có thể chuẩn hóa trước:

~~~java
BigDecimal amount = new BigDecimal(rawAmount);

context.setVariable("amount", amount);
~~~

Sau đó expression sử dụng cùng kiểu dữ liệu:

~~~text
#calculateTax(#amount)
#calculateFee(#amount)
#calculateDiscount(#amount)
~~~

Cách này tránh phụ thuộc vào conversion lặp lại và làm kiểu dữ liệu trong context rõ ràng hơn.

Không phải lúc nào cũng cần chuyển đổi trước. Nếu converter mặc định rẻ và expression chỉ chạy một lần, việc thêm code chuẩn hóa có thể không tạo lợi ích đáng kể. Hãy đo trước khi thay đổi.

## 5. Chi phí của PropertyAccessor

PropertyAccessor quyết định cách SpEL đọc hoặc ghi property trên object. StandardEvaluationContext thường sử dụng reflective property access cho Java object; SimpleEvaluationContext có thể dùng accessor phù hợp cho data binding.

Khi có nhiều accessor, SpEL cần xác định accessor nào hỗ trợ object và property đang được truy cập. Một accessor tùy biến có thể được hỏi qua canRead hoặc canWrite trước khi thực hiện thao tác thực tế.

Nếu danh sách accessor dài hoặc nhiều accessor kiểm tra kiểu object theo cách tốn kém, chi phí property access có thể tăng.

Một accessor nên:

- Kiểm tra nhanh kiểu target mà nó hỗ trợ.
- Từ chối sớm kiểu object không phù hợp.
- Kiểm tra tên property bằng allowlist hoặc metadata đã chuẩn bị.
- Tránh quét toàn bộ field bằng reflection trong mỗi lần đọc.
- Không thực hiện I/O trong canRead, canWrite, read hoặc write.
- Chỉ làm đúng phần việc mà accessor được giao.

Nếu accessor chỉ hỗ trợ một DTO cụ thể, hãy kiểm tra class hoặc interface phù hợp trước khi xử lý tên property.

## 6. Thứ tự PropertyAccessor

Thứ tự đăng ký accessor có thể ảnh hưởng đến số lần SpEL phải kiểm tra trước khi tìm được accessor phù hợp. Accessor chuyên biệt thường nên đứng trước accessor tổng quát nếu nó được dùng thường xuyên cho kiểu object tương ứng.

Ví dụ, nếu ứng dụng có accessor cho một DTO và accessor tổng quát cho JavaBean, việc đặt accessor chuyên biệt trước có thể tránh thử accessor tổng quát không cần thiết.

Tuy nhiên, thay đổi thứ tự có thể thay đổi semantics nếu nhiều accessor cùng tuyên bố hỗ trợ một property. Hãy bảo đảm các accessor không xung đột và thứ tự phản ánh chính sách truy cập đã định.

Không nên thêm nhiều accessor dự phòng mà không có use case cụ thể. Mỗi accessor mới làm tăng bề mặt truy cập và có thể tăng chi phí phân giải property.

## 7. Cache metadata trong custom PropertyAccessor

Nếu accessor cần tra cứu metadata như getter, setter hoặc field, có thể chuẩn bị và cache metadata theo class thay vì tìm lại trong mỗi lần truy cập.

Ví dụ minh họa:

~~~java
private final Map<Class<?>, Map<String, Method>> getterCache =
        new ConcurrentHashMap<>();
~~~

Cache nên có key phù hợp với kiểu target và property. Cần xử lý class loader, class động và vòng đời ứng dụng theo kiến trúc thực tế.

Không cache object nghiệp vụ hoặc giá trị property theo cách làm kết quả cũ sau khi object thay đổi. Cache metadata truy cập khác với cache dữ liệu.

Trước khi tự viết cache, hãy kiểm tra accessor mặc định hoặc framework đã cache phần metadata cần thiết hay chưa. Tránh xây dựng cache trùng lặp làm tăng bộ nhớ và độ phức tạp mà không giảm được chi phí đáng kể.

## 8. Chi phí của MethodResolver

MethodResolver tìm method phù hợp khi expression gọi một method trên object:

~~~text
#customer.calculateDiscount(#orderTotal)
#text.substring(0, 5)
~~~

Một context có nhiều MethodResolver có thể phải thử lần lượt cho tới khi tìm được resolver xử lý lời gọi. Resolver tùy biến có thể làm tăng chi phí nếu nó quét nhiều method, phân tích annotation hoặc kiểm tra quyền truy cập phức tạp trong mỗi lần resolve.

Resolver nên từ chối nhanh target type không thuộc phạm vi hỗ trợ. Nếu chỉ cần một số method, hãy dùng allowlist hoặc metadata đã chuẩn bị thay vì duyệt toàn bộ method của class mỗi lần.

Không nên đặt truy vấn database, gọi API hoặc logic nghiệp vụ trong quá trình resolve method. MethodResolver nên quyết định cách tìm executor; công việc của method chỉ diễn ra khi expression thực sự gọi nó.

## 9. Phân biệt method resolution với method execution

Method resolution xác định method nào sẽ được gọi và tạo cơ chế thực thi phù hợp. Method execution chạy logic Java của method đó.

Hai phần có chi phí khác nhau:

- Resolution có thể tốn thời gian khi phải tìm method, kiểm tra overload và kiểu đối số.
- Execution có thể tốn thời gian vì logic bên trong method, I/O, database hoặc tính toán.

Nếu một expression chậm, đừng mặc định MethodResolver là nguyên nhân. Một method được resolve nhanh vẫn có thể chạy rất lâu vì truy vấn database hoặc gọi service bên ngoài.

Đo thời gian tổng và profile call stack để xác định phần nào chiếm chi phí. Nếu method execution là nút thắt, tối ưu resolver sẽ không giải quyết được vấn đề.

## 10. Overload và conversion làm tăng công việc phân giải

Khi một class có nhiều overload cùng tên, resolver có thể phải xem xét kiểu tham số và khả năng conversion để chọn method phù hợp.

Ví dụ:

~~~java
public String format(Integer value) {
    return "integer";
}

public String format(BigDecimal value) {
    return "decimal";
}

public String format(String value) {
    return "text";
}
~~~

Một expression truyền kiểu String có thể khiến việc lựa chọn method phụ thuộc vào kiểu runtime và các conversion được hỗ trợ.

Nếu API được dùng thường xuyên từ SpEL, hãy thiết kế method có chữ ký rõ ràng, tránh quá nhiều overload gần giống nhau. Có thể tạo method wrapper với tên riêng để giảm mơ hồ:

~~~java
public String formatInteger(Integer value) {
    return format(value);
}
~~~

Tên method rõ ràng giúp expression dễ hiểu và giảm số khả năng cần phân giải.

## 11. TypeLocator và BeanResolver

TypeLocator phân giải class được tham chiếu bằng T(...). BeanResolver phân giải bean theo tên với cú pháp @beanName.

Các thao tác này thường không cần thiết trong expression chỉ đọc property đơn giản. Nếu không cần, đừng cấu hình hoặc expose khả năng này trong context.

Khi cần, tránh resolver tùy biến thực hiện quét classpath hoặc tìm bean qua nhiều nguồn trong mỗi lần gọi. Hãy dùng metadata hoặc registry đã được chuẩn bị trong quá trình cấu hình ứng dụng.

Đối với expression được đánh giá thường xuyên, cần đo chi phí phân giải type/bean nếu chúng nằm trên đường chạy nóng. Nếu bean hoặc class đã được xác định từ trước, cân nhắc đưa object/giá trị cần thiết vào context thay vì phân giải lặp lại theo tên.

Giới hạn resolver cũng giúp giảm bề mặt truy cập. Hiệu năng và an toàn thường cùng được cải thiện khi context chỉ cung cấp những khả năng cần thiết.

## 12. Reuse Expression thay vì parse lặp lại

Parse expression có chi phí. Nếu cùng một chuỗi được dùng nhiều lần, hãy parse một lần và tái sử dụng Expression.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("#order.total >= #minimum");

for (Order order : orders) {
    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable(
            "minimum",
            new BigDecimal("100.00")
    );

    Boolean accepted = expression.getValue(
            context,
            Boolean.class
    );
}
~~~

Ở đây parser chỉ tạo Expression một lần. Mỗi lần lặp sử dụng context riêng cho order hiện tại.

Nếu parse lại trong từng vòng lặp, ứng dụng phải lặp lại công việc phân tích cú pháp không cần thiết. Với rule cố định, cache Expression theo chuỗi hoặc mã rule có thể giảm chi phí parse.

Cache cần có giới hạn kích thước và chính sách invalidation nếu rule có thể thay đổi. Không dùng cache không giới hạn cho expression tùy ý do người dùng gửi vì có thể làm tăng bộ nhớ.

## 13. Reuse Expression nhưng quản lý EvaluationContext riêng

Expression thường được thiết kế để tái sử dụng, trong khi EvaluationContext có thể chứa root object và variables thay đổi theo từng lượt đánh giá.

Không nên chia sẻ một context mutable giữa nhiều request hoặc thread nếu các request ghi đè root object, variables hoặc resolver state. Việc dùng chung có thể tạo race condition và kết quả không nhất quán.

Một cách tổ chức an toàn hơn:

- Cache parser hoặc Expression bất biến theo rule/version.
- Tạo EvaluationContext cho mỗi lượt đánh giá hoặc mỗi đơn vị xử lý phù hợp.
- Đưa root object và variables của lượt hiện tại vào context đó.
- Không thay đổi registry hoặc resolver sau khi bắt đầu đánh giá đồng thời.

Việc tạo context có chi phí riêng. Nếu context setup là nút thắt, hãy đo và cân nhắc factory hoặc object cấu hình dùng chung bất biến. Đừng tối ưu bằng cách chia sẻ state mutable nếu điều đó làm mất tính đúng đắn.

## 14. SpEL compiler và các chế độ thực thi

SpEL có chế độ compiler để biên dịch một số expression sang bytecode Java nhằm giảm chi phí đánh giá lặp lại.

Các chế độ thường gặp:

| Chế độ | Hành vi |
|---|---|
| OFF | Chỉ dùng interpreted evaluation |
| IMMEDIATE | Biên dịch expression khi đủ điều kiện; lỗi thực thi ở compiled form có thể được truyền ra |
| MIXED | Có thể chuyển đổi giữa interpreted và compiled evaluation khi cần |

Có thể cấu hình parser:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                SpelCompilerMode.MIXED,
                getClass().getClassLoader()
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

Compiler có thể giúp expression được đánh giá thường xuyên, nhưng không phải mọi expression đều biên dịch được. Khả năng phụ thuộc các construct được dùng, kiểu runtime và những thành phần tùy biến trong context.

Đừng bật compiler chỉ vì muốn tối ưu chung. Hãy đo trên workload thực tế và xác nhận biểu thức vẫn cho kết quả đúng khi kiểu dữ liệu hoặc object thay đổi.

## 15. Khi expression thay đổi kiểu runtime

Compiled expression có thể giả định một số kiểu đã được quan sát trong quá trình đánh giá. Nếu cùng một expression được dùng với object có kiểu runtime khác, compiled code có thể không còn phù hợp.

MIXED mode được thiết kế để có thể quay lại interpreted evaluation khi compiled form gặp vấn đề và tiếp tục thích nghi theo cơ chế compiler. IMMEDIATE mode có thể truyền lỗi khi compiled expression không chạy được.

Vì vậy, hãy cân nhắc tính ổn định của kiểu dữ liệu trước khi chọn compiler mode. Expression dùng trên một DTO ổn định thường dễ tối ưu hơn expression được chạy trên nhiều kiểu object không liên quan.

Nếu rule nhận dữ liệu đa hình, hãy benchmark với tất cả kiểu runtime thực tế, không chỉ một fixture đại diện.

## 16. Giới hạn của custom accessor và compiler

Expression sử dụng custom PropertyAccessor, custom MethodResolver hoặc các tính năng động có thể không được compiler hỗ trợ đầy đủ như interpreted evaluation. Một số đường truy cập cần cơ chế resolver tùy biến chỉ có thể chạy ở chế độ interpreted.

Hãy kiểm tra khả năng compile trên phiên bản Spring đang dùng và đúng cấu hình context của ứng dụng. Nếu expression không biên dịch được, việc bật compiler không tự làm resolver tùy biến nhanh hơn.

Không thay đổi semantics của accessor hoặc resolver chỉ để ép compiler hoạt động. Đúng đắn và giới hạn truy cập quan trọng hơn một benchmark nhanh hơn nhưng không phản ánh hành vi production.

## 17. Giảm số lần gọi resolver trong expression

Một expression có thể đọc cùng property hoặc gọi cùng method nhiều lần. Nếu thao tác đó đắt, hãy cân nhắc tính trước giá trị trong Java hoặc đưa vào context variable.

Ví dụ:

~~~text
#customer.profile.account.region == 'APAC' and
#customer.profile.account.active and
#customer.profile.account.ageDays > 30
~~~

Nếu việc truy cập account có lazy loading hoặc getter thực hiện tính toán, expression có thể lặp lại chi phí đó.

Có thể chuẩn bị dữ liệu:

~~~java
context.setVariable("accountRegion", account.getRegion());
context.setVariable("accountActive", account.isActive());
context.setVariable("accountAgeDays", account.getAgeDays());
~~~

Expression trở nên đơn giản hơn:

~~~text
#accountRegion == 'APAC' and
#accountActive and
#accountAgeDays > 30
~~~

Không nên tạo variables dư thừa cho property rẻ hoặc chỉ dùng một lần. Chuẩn hóa trước chỉ có lợi khi nó loại bỏ công việc lặp hoặc làm rõ kiểu dữ liệu.

## 18. Hiệu năng của selection và projection

Selection .?[...] phải kiểm tra các phần tử để tìm tất cả kết quả phù hợp. Projection .![...] phải biến đổi từng phần tử. Nếu predicate hoặc projection gọi method có chi phí cao, tổng chi phí tăng theo số phần tử.

Ví dụ:

~~~text
#orders.?[#this.customer.loadRiskScore() < 50]
~~~

Nếu loadRiskScore truy vấn database, collection có nhiều đơn có thể tạo nhiều truy vấn. Vấn đề nằm ở method execution và dữ liệu, không chỉ ở resolver.

Hãy chuẩn bị risk score trước hoặc batch load dữ liệu trong service rồi đưa giá trị cần thiết vào DTO. Tránh lazy loading và I/O trong predicate.

Nếu chỉ cần phần tử phù hợp đầu tiên, first selection có thể dừng khi tìm thấy kết quả. Nếu cần tất cả kết quả, phải xử lý toàn bộ collection theo yêu cầu.

## 19. Đo hiệu năng thay vì suy đoán

Một benchmark có ích cần phản ánh cách ứng dụng thực sự sử dụng SpEL:

- Parse một lần hay parse mỗi request.
- Số lần evaluate trên một Expression.
- Kiểu root object và mức độ đa hình.
- Số lượng accessor và resolver.
- Converter mặc định hay converter tùy biến.
- Kích thước collection.
- Method được gọi có thực hiện I/O hay không.
- Context được tạo mới hay tái sử dụng.
- Compiler mode đang dùng.

JMH phù hợp để benchmark micro-operation Java có kiểm soát. Với ứng dụng thực tế, profiler hoặc tracing giúp nhận diện thời gian trong converter, accessor, resolver và method được gọi.

Đo cả throughput và latency, bao gồm phân vị cao nếu hệ thống phục vụ request. Chạy nhiều vòng warm-up và measurement, tránh đưa khởi động JVM hoặc class loading lần đầu vào kết luận về steady-state.

Không so sánh hai cấu hình bằng một lần chạy ngắn hoặc chỉ dựa vào thời gian trung bình.

## 20. Ví dụ JMH so sánh expression tái sử dụng

Ví dụ phác thảo benchmark:

~~~java
@State(Scope.Thread)
public class SpelBenchmark {

    private Expression expression;
    private StandardEvaluationContext context;
    private Order order;

    @Setup
    public void setup() {
        ExpressionParser parser =
                new SpelExpressionParser();

        expression = parser.parseExpression("total >= 100");

        order = new Order(new BigDecimal("250.00"));
        context = new StandardEvaluationContext(order);
    }

    @Benchmark
    public Boolean evaluateReusedExpression() {
        return expression.getValue(context, Boolean.class);
    }
}
~~~

Benchmark này đo evaluate trên một Expression đã parse. Nếu muốn đo chi phí parse, tạo benchmark riêng gọi parseExpression trong phương thức được đo.

Không gộp parse, tạo context, tạo object và evaluate vào một benchmark rồi kết luận resolver nào chậm. Tách các phần giúp biết tối ưu nào thực sự có tác dụng.

Trong benchmark production-like, hãy bổ sung converter và resolver tùy biến đang được ứng dụng sử dụng, cùng dữ liệu có kiểu và kích thước tương ứng.

## 21. Quản lý cache và bộ nhớ

Cache Expression có thể giảm chi phí parse, nhưng cache không giới hạn có thể giữ quá nhiều expression và làm tăng bộ nhớ.

Nếu expression được quản trị viên thay đổi, cache key nên bao gồm mã rule và phiên bản hoặc nội dung expression. Khi rule thay đổi, cần invalidation để không tiếp tục dùng expression cũ.

Không cache EvaluationContext chứa root object, request data hoặc variables của người dùng. Điều đó có thể gây rò rỉ dữ liệu giữa request và giữ object lâu hơn vòng đời cần thiết.

Cache metadata accessor/resolver nên có giới hạn và key ổn định. Theo dõi số entry, hit rate và memory usage để tránh tối ưu thời gian bằng cách tiêu tốn bộ nhớ không kiểm soát.

## 22. Cân bằng hiệu năng với an toàn

Resolver tùy biến thường được thêm để kiểm soát quyền truy cập hoặc tích hợp kiểu domain. Không nên bỏ allowlist, validation hoặc giới hạn accessor chỉ để giảm vài lần kiểm tra.

Một resolver nhanh nhưng cho phép đọc hoặc gọi mọi property/method có thể tạo rủi ro bảo mật. Hãy tối ưu implementation bên trong chính sách được phép:

- Kiểm tra target type nhanh.
- Cache metadata đã xác thực.
- Dùng allowlist bất biến.
- Tránh reflection scan lặp lại.
- Tránh I/O và side effect.
- Giữ thứ tự resolver rõ ràng.
- Kiểm thử cả property/method được phép và bị từ chối.

Hiệu năng phải được đo trên cùng chính sách quyền truy cập mà production sẽ sử dụng.

## 23. Các dấu hiệu cần điều tra

| Dấu hiệu | Vùng có thể là nút thắt | Hướng điều tra |
|---|---|---|
| CPU tăng khi evaluate nhiều lần | Expression hoặc resolver lặp lại công việc | Profile call stack |
| Nhiều allocation khi đọc property | Accessor tạo metadata/object trung gian | Kiểm tra cache và implementation |
| Latency tăng khi có custom converter | Converter phân tích hoặc truy vấn quá nhiều | Đo riêng conversion |
| Method lookup tốn thời gian | Nhiều resolver hoặc nhiều overload | Kiểm tra thứ tự và chữ ký method |
| Rule chạy chậm theo số phần tử | Predicate/projection gọi method đắt | Batch dữ liệu và giảm I/O |
| Parse chiếm tỷ trọng lớn | Expression bị parse lặp | Reuse/cache Expression |
| Compiled mode không cải thiện | Expression không compile hoặc bottleneck ở method/I/O | Kiểm tra compile eligibility và profile |
| Bộ nhớ tăng theo số rule | Cache expression không giới hạn | Dùng bounded cache và invalidation |

Các dấu hiệu này chỉ giúp định hướng. Cần profiler hoặc benchmark để xác nhận nguyên nhân trước khi thay đổi thiết kế.

## 24. Ghi nhớ

TypeConverter có thể làm tăng chi phí khi conversion lặp lại hoặc converter thực hiện công việc nặng. PropertyAccessor và MethodResolver ảnh hưởng đến việc tìm cách đọc/ghi property hoặc gọi method; số resolver, thứ tự và cách cache metadata đều có thể tác động đến đường chạy. TypeLocator và BeanResolver cũng cần được giới hạn và tối ưu nếu được dùng thường xuyên.

Parse expression một lần và tái sử dụng Expression khi phù hợp. Quản lý EvaluationContext theo từng lượt đánh giá để tránh chia sẻ state mutable. Giữ converter và resolver nhẹ, từ chối nhanh kiểu không hỗ trợ, cache metadata thay vì dữ liệu nghiệp vụ và tránh I/O trong quá trình evaluate.

SpEL compiler có thể giúp một số expression chạy thường xuyên, nhưng không hỗ trợ mọi construct hoặc resolver tùy biến. Hãy chọn OFF, IMMEDIATE hoặc MIXED dựa trên kiểu dữ liệu và hành vi runtime thực tế. Dùng JMH, profiler và workload đại diện để đo parse, context setup, conversion, resolution và method execution riêng biệt.
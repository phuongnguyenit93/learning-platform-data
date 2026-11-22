# Chi phí selection, projection và method invocation trong SpEL

## Mục tiêu

Collection operations của Spring Expression Language (SpEL) giúp lọc và biến đổi dữ liệu ngay trong expression. Selection `.?[...]` giữ lại phần tử thỏa điều kiện; projection `.![...]` tính một giá trị cho từng phần tử. Khi expression còn gọi method, chi phí thực tế phụ thuộc vào số phần tử được duyệt, số lần biểu thức con chạy, công việc bên trong getter/method và lượng collection kết quả được tạo.

Với collection nhỏ và biểu thức đơn giản, SpEL thường dễ đọc và đủ nhanh. Với dữ liệu lớn, nested collection hoặc method đắt tiền, cùng một expression có thể tạo nhiều lần gọi và nhiều object trung gian. Cần hiểu chi phí theo từng bước, đo trên workload thực tế và chuyển phần xử lý nặng sang Java hoặc tầng truy vấn dữ liệu khi phù hợp.

## 1. Chi phí cơ bản của selection

Selection dùng `.?[condition]` để kiểm tra từng phần tử:

~~~spel
users.?[active == true]
orders.?[total >= #minimum]
~~~

Với một nguồn có `n` phần tử, selection thông thường phải đánh giá điều kiện cho từng phần tử. Vì vậy, nếu điều kiện có chi phí hằng số, thời gian tăng tuyến tính theo số phần tử: O(n). Kết quả là collection mới chứa các phần tử được giữ lại.

Ví dụ:

~~~text
Input:  [A: active, B: inactive, C: active, D: active]
Output: [A, C, D]
~~~

Selection trên array hoặc `Iterable` tạo kết quả dạng List. Selection trên Map giữ các entry thỏa điều kiện trong một Map kết quả. Kích thước kết quả phụ thuộc số phần tử phù hợp; trong trường hợp tất cả phần tử đều phù hợp, collection kết quả có kích thước gần bằng nguồn.

Với first selection `.^[...]`, SpEL có thể dừng khi tìm thấy phần tử phù hợp đầu tiên. Nếu phần tử phù hợp ở cuối hoặc không có phần tử nào phù hợp, gần như toàn bộ nguồn vẫn phải được duyệt. Last selection `.$[...]` cần tiếp tục duyệt để xác định phần tử phù hợp cuối cùng.

## 2. Chi phí cơ bản của projection

Projection dùng `.![expression]` để đánh giá một biểu thức cho từng phần tử:

~~~spel
users.![name]
products.![price * #quantity]
~~~

Với `n` phần tử, projection thông thường đánh giá expression con `n` lần và tạo collection kết quả có một giá trị cho mỗi phần tử. Nếu biểu thức con có chi phí hằng số, thời gian là O(n); bộ nhớ kết quả cũng tăng O(n).

Projection trên array, `Iterable` hoặc Map trả về List các giá trị được chiếu. Với Map, expression con chạy trên từng entry (`key`, `value`); kết quả vẫn là List chứ không tự giữ cấu trúc Map.

Projection không tự lọc giá trị null, loại duplicate hoặc sắp xếp kết quả. Nếu biểu thức con trả về null, kết quả null vẫn chiếm một vị trí. Nếu nhiều phần tử tạo ra cùng giá trị, tất cả kết quả vẫn được giữ.

## 3. Kết hợp selection và projection

Biểu thức sau vừa lọc vừa biến đổi:

~~~spel
orders.?[status == 'PAID'].![id]
~~~

Với nguồn có `n` order và `k` order thỏa điều kiện:

1. Selection kiểm tra tối đa `n` phần tử và tạo collection gồm `k` order.
2. Projection chạy trên `k` order và tạo List gồm `k` ID.

Nếu điều kiện và projection đều có chi phí hằng số, tổng thời gian vẫn là O(n + k), tức O(n) vì `k <= n`. Tuy nhiên, expression có thể tạo collection trung gian từ selection rồi tạo collection kết quả từ projection. Với nguồn lớn, allocation và garbage collection có thể đáng kể dù độ phức tạp thời gian là tuyến tính.

Nếu chỉ cần một kết quả cuối cùng hoặc cần xử lý streaming, một vòng lặp Java có thể lọc và chiếu trong cùng một lượt, tránh giữ collection trung gian. Hãy chọn cách viết theo độ rõ ràng và đo hiệu năng trước khi tối ưu.

## 4. Method invocation trong selection và projection

Method bên trong biểu thức con được gọi mỗi khi SpEL đánh giá biểu thức đó:

~~~spel
users.?[#this.isEligible()]
products.![#this.calculateDisplayPrice()]
~~~

Trong selection, method predicate có thể được gọi một lần cho mỗi phần tử được kiểm tra. Trong projection, method được gọi một lần cho mỗi phần tử được chiếu. Nếu collection có 10.000 phần tử, một method trong projection có thể được gọi 10.000 lần trong một lần đánh giá expression.

Chi phí của method có thể lớn hơn nhiều so với chi phí duyệt collection. Một getter tưởng như đơn giản có thể kích hoạt ORM lazy loading; method có thể thực hiện phép tính phức tạp, parse dữ liệu hoặc gọi service. Nếu method thực hiện I/O, database query hoặc network call, tổng chi phí có thể tăng mạnh và phụ thuộc hệ thống bên ngoài.

Không đưa method có side effect vào selection/projection. Việc đánh giá lại expression, retry request hoặc chạy trên từng phần tử có thể khiến method được gọi nhiều lần và gây hành động lặp.

## 5. Tránh lặp lại cùng một phép tính đắt tiền

Nếu một phép tính được dùng nhiều lần trong cùng expression hoặc trong nhiều bước collection operation, hãy kiểm tra số lần nó thực sự được gọi.

Ví dụ không nên lặp lại method đắt tiền trong điều kiện:

~~~spel
products.?[#this.calculateScore() > #minimum and #this.calculateScore() < #maximum]
~~~

Trong điều kiện trên, `calculateScore()` có thể được gọi hai lần cho mỗi product vì hai toán hạng đều tham chiếu method. Với `n` product, số lần gọi có thể lên đến khoảng `2n`.

Nếu phép tính có thể được chuẩn bị trước, tính một lần trong Java rồi đưa giá trị vào DTO/view object:

~~~java
List<ProductView> views = products.stream()
        .map(product -> new ProductView(
                product.getId(),
                product.calculateScore()))
        .toList();
~~~

Expression sau chỉ đọc giá trị đã tính:

~~~spel
views.?[score >= #minimum and score < #maximum]
~~~

Cách này làm rõ thời điểm tính toán và tránh gọi lại method trong expression. Nếu dữ liệu có thể thay đổi, hãy xác định rõ thời điểm snapshot và vòng đời của view object.

## 6. Nested selection và projection

Collection operations lồng nhau có thể làm số lần đánh giá tăng theo tích kích thước của các collection:

~~~spel
departments.![employees.?[active == true].![email]]
~~~

Giả sử có `d` department và mỗi department có trung bình `e` employee. Selection bên trong có thể kiểm tra khoảng `d * e` employee; projection chạy trên những employee được giữ lại. Tổng chi phí tăng theo tổng số employee được duyệt, không chỉ theo số department.

Với cấu trúc nhiều cấp, hãy ước lượng tổng số phần tử được duyệt ở mỗi cấp. Nếu expression gọi method hoặc truy cập getter đắt tiền ở cấp trong cùng, chi phí được nhân lên theo số phần tử ở tất cả cấp ngoài.

Không dùng nested collection operations để che giấu nhiều vòng lặp phức tạp. Khi logic có nhiều nhánh, grouping, join, flatten hoặc aggregate lớn, Java Stream/loop hoặc truy vấn ở data layer thường dễ kiểm soát hơn.

## 7. Chi phí bộ nhớ và collection trung gian

Selection và projection thường tạo collection kết quả mới. Khi nối nhiều operation, có thể xuất hiện nhiều collection trung gian:

~~~spel
orders.?[status == 'PAID'].![customer.address.city]
~~~

Selection tạo collection order được giữ; projection tạo List city. Các object được giữ trong collection selection thường là reference tới object nguồn, không phải deep copy. Projection tạo các giá trị mới trong List nhưng cũng có thể trả về reference tới object gốc.

Với collection lớn, hãy cân nhắc:

- Kích thước nguồn và tỷ lệ phần tử được selection giữ lại.
- Số collection kết quả/trung gian được tạo trong một lần đánh giá.
- Kích thước object được projection trả về.
- Số lần expression được đánh giá đồng thời.
- Áp lực garbage collection khi request chạy thường xuyên.

Nếu chỉ cần một boolean hoặc một phần tử đầu tiên, không nên tạo cả một danh sách lớn rồi mới kiểm tra kết quả. Dùng biểu thức phù hợp như first selection khi semantics cho phép, hoặc xử lý bằng Java với short-circuit.

## 8. Property access và lazy loading

Property access trong SpEL thường đi qua `PropertyAccessor`. Việc metadata reflection có thể được tái sử dụng không có nghĩa getter không chạy lại. Mỗi lần expression đọc property, getter hoặc accessor tương ứng vẫn có thể được thực thi.

Ví dụ:

~~~spel
orders.?[customer.address.country == 'VN']
~~~

Nếu `customer.address` là quan hệ lazy của ORM, việc duyệt hàng nghìn order có thể phát sinh nhiều truy vấn database (N+1). Chi phí không còn chỉ là O(n) trong bộ nhớ; nó có thể bao gồm hàng nghìn lượt I/O.

Để tránh điều này:

- Dùng DTO/view object có dữ liệu đã được nạp theo kế hoạch.
- Fetch các quan hệ cần thiết bằng query phù hợp trước khi đánh giá SpEL.
- Không để getter gọi repository hoặc service.
- Dùng projection trên dữ liệu phẳng khi chỉ cần một vài field.
- Đo số query thực tế trong integration test hoặc profiler.

## 9. Parse một lần và tái sử dụng Expression

Parse source expression có chi phí riêng. Nếu cùng một rule được đánh giá nhiều lần, parse lại trong mỗi request sẽ cộng thêm công việc không cần thiết.

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "users.?[active == true].![name]");

// Tái sử dụng expression đã parse cho các lần đánh giá tiếp theo.
List<?> names = expression.getValue(context, users, List.class);
~~~

Trong ứng dụng, có thể lưu expression đã parse theo rule ID và version. Khi source rule thay đổi, tạo expression mới cho version mới. Nếu expression được cung cấp từ bên ngoài, giới hạn số lượng và kích thước expression được lưu để tránh cache tăng vô hạn.

Tái sử dụng AST không có nghĩa kết quả selection/projection hoặc method invocation được cache. Mỗi lần gọi `getValue()` vẫn đánh giá expression theo dữ liệu và context của lần gọi đó.

Không chia sẻ một `EvaluationContext` mutable giữa các request đồng thời nếu request thay đổi variables hoặc root state. Có thể tái sử dụng expression trong khi tạo context phù hợp cho từng lần đánh giá.

## 10. SpEL compiler và hiệu năng

SpEL có compiler tùy chọn để biên dịch một số expression sang bytecode. Compiler mode có thể được cấu hình bằng `SpelParserConfiguration`, gồm các chế độ như `OFF`, `IMMEDIATE` và `MIXED`.

Compiler có thể giúp các expression được đánh giá lặp lại nhanh hơn khi AST và kiểu dữ liệu nằm trong tập được hỗ trợ. Tuy nhiên:

- Không phải mọi expression hoặc mọi AST node đều có thể biên dịch.
- Collection selection, projection, method dispatch hoặc kiểu dữ liệu thay đổi có thể ảnh hưởng khả năng biên dịch và lợi ích thực tế.
- Compilation có chi phí ban đầu; expression chỉ chạy ít lần có thể không được lợi.
- `MIXED` có thể bắt đầu bằng interpreted evaluation rồi thử compile theo ngưỡng; không nên giả định mọi expression cuối cùng đều được compile.
- Compiler mode là lựa chọn hiệu năng, không phải biện pháp bảo mật hay thay thế việc giới hạn quyền trong context.

Hãy kiểm tra khả năng biên dịch của đúng expression và Spring version đang dùng, sau đó benchmark với dữ liệu đại diện. Nếu expression không được hỗ trợ, interpreted evaluation vẫn có thể hoạt động bình thường.

Ví dụ cấu hình:

~~~java
SpelParserConfiguration configuration = new SpelParserConfiguration(
        SpelCompilerMode.MIXED,
        getClass().getClassLoader());

ExpressionParser parser = new SpelExpressionParser(configuration);
~~~

Đừng bật compiler chỉ dựa trên giả định rằng mọi expression sẽ nhanh hơn. Đo cả warm-up, thời gian ổn định và allocation.

## 11. Khi nào nên chuyển xử lý sang Java hoặc database?

SpEL phù hợp với biểu thức ngắn, dễ đọc, hoạt động trên object đã có trong bộ nhớ. Nên cân nhắc Java hoặc data layer khi:

- Collection có hàng trăm nghìn hoặc hàng triệu phần tử.
- Selection/projection lồng nhiều cấp hoặc có nhiều bước trung gian.
- Biểu thức gọi method đắt tiền hoặc cần memoization.
- Logic cần grouping, join, sorting phức tạp, pagination hoặc streaming.
- Getter có thể phát sinh database query hoặc I/O.
- Cần kiểm soát transaction, timeout, retry, cancellation hoặc concurrency.
- Cần profiling và tối ưu từng đoạn code rõ ràng.

Nếu dữ liệu nằm trong database, đẩy điều kiện lọc xuống repository/query thường tiết kiệm hơn việc tải toàn bộ rows rồi selection trong SpEL. Chỉ tải các field cần thiết, phân trang và chiếu sang DTO nếu phù hợp.

Không phải cứ collection lớn là phải bỏ SpEL. Nếu expression đơn giản, được đánh giá ít lần và dữ liệu đã có sẵn, đo trước khi thay đổi thiết kế.

## 12. Benchmark đúng cách

Đừng đánh giá hiệu năng chỉ bằng một lần gọi `System.nanoTime()` quanh expression. Kết quả dễ bị ảnh hưởng bởi JIT warm-up, garbage collection, compilation, dữ liệu cache và tải máy.

Đối với benchmark Java, JMH là lựa chọn phù hợp. Nên tách các trường hợp:

1. Parse expression và evaluate trong cùng một benchmark để đo tổng chi phí khi source mới.
2. Parse một lần trong setup, chỉ đo `getValue()` để đo evaluation.
3. So sánh selection/projection SpEL với vòng lặp Java hoặc Stream có cùng semantics.
4. So sánh có và không có method invocation.
5. Dùng nhiều kích thước collection và tỷ lệ selection khác nhau.
6. Đo throughput/latency và allocation; dùng warm-up, measurement iterations và forks.

Ví dụ khung JMH:

~~~java
@State(Scope.Thread)
public class SpelCollectionBenchmark {
    private Expression expression;
    private EvaluationContext context;
    private List<UserView> users;

    @Setup(Level.Trial)
    public void setup() {
        ExpressionParser parser = new SpelExpressionParser();
        expression = parser.parseExpression(
                ".?[active == true].![name]");
        context = SimpleEvaluationContext
                .forReadOnlyDataBinding()
                .build();
        users = TestData.users(10_000);
    }

    @Benchmark
    public Object selectionAndProjection() {
        return expression.getValue(context, users);
    }
}
~~~

Trong benchmark này, parser và expression được tạo ở setup để phép đo tập trung vào evaluation. Tạo benchmark khác nếu muốn đo parse cost. Dùng cùng dataset, cùng điều kiện và cùng kết quả đầu ra khi so sánh với Java.

Không đưa benchmark số liệu từ máy developer thành cam kết production. Dùng profiler và metrics trên workload gần thực tế để xác định bottleneck.

## 13. Ví dụ so sánh với Java loop

SpEL:

~~~spel
users.?[active == true].![name]
~~~

Java một lượt:

~~~java
List<String> names = new ArrayList<>();
for (UserView user : users) {
    if (user.isActive()) {
        names.add(user.getName());
    }
}
~~~

Java loop có thể lọc và chiếu trong cùng một lượt, chỉ tạo collection kết quả cuối. SpEL expression ngắn hơn và thể hiện ý định rõ, nhưng selection rồi projection có thể tạo collection trung gian. Lựa chọn cuối cùng nên dựa trên readability, yêu cầu maintainability và benchmark thực tế.

## 14. Checklist tối ưu

Trước khi tối ưu một expression, hãy xác định:

1. Nguồn có bao nhiêu phần tử ở mỗi cấp collection?
2. Selection duyệt bao nhiêu phần tử và giữ lại bao nhiêu?
3. Projection tạo bao nhiêu giá trị và có cần toàn bộ không?
4. Method/getter nào được gọi, mỗi method bao nhiêu lần?
5. Getter có lazy loading hoặc I/O không?
6. Có phép tính đắt tiền bị lặp lại trong điều kiện hoặc projection không?
7. Có collection trung gian lớn hoặc nested result không?
8. Expression đã được parse một lần và tái sử dụng chưa?
9. Compiler có hỗ trợ expression cụ thể này không, và có cải thiện trong benchmark không?
10. Có thể lọc ở database, chuẩn bị DTO hoặc dùng Java loop/Stream để giảm allocation không?

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Selection chậm khi collection lớn | Điều kiện phải được đánh giá trên nhiều hoặc tất cả phần tử. | Giảm dữ liệu đầu vào, filter ở database hoặc dùng cấu trúc tra cứu phù hợp. |
| Projection chậm dù biểu thức ngắn | Expression con chạy một lần cho mỗi phần tử. | Đo method/getter bên trong; chuẩn bị dữ liệu trước nếu cần. |
| Method bị gọi nhiều hơn dự kiến | Method xuất hiện nhiều lần trong expression hoặc collection operation duyệt từng phần tử. | Tính trước giá trị, tránh lặp method trong cùng điều kiện và giữ method thuần. |
| Nhiều truy vấn database khi selection | Getter kích hoạt lazy loading hoặc method gọi repository. | Fetch dữ liệu trước, dùng DTO và kiểm tra số query. |
| Tốn bộ nhớ khi nối selection và projection | Collection trung gian và kết quả đều được tạo. | Dùng một vòng lặp Java nếu cần một lượt xử lý hoặc streaming. |
| Nested expression tăng thời gian mạnh | Số phần tử ở các cấp nhân lên; method trong vòng lặp trong cùng có chi phí cao. | Giảm cấp lồng, flatten/aggregate ở Java hoặc database. |
| Parse expression lặp lại | Parser được gọi trong mỗi request. | Parse một lần và cache expression theo ID/version với giới hạn dung lượng. |
| Bật compiler nhưng không nhanh hơn | Expression không được hỗ trợ, chi phí compilation hoặc bottleneck nằm ở method/I/O. | Xác minh compile support và benchmark; tối ưu phần chi phí lớn nhất. |
| Benchmark không ổn định | Thiếu warm-up/fork hoặc đo chung parse, JIT và GC. | Dùng JMH, tách parse/evaluate và dùng dữ liệu đại diện. |

## Ghi nhớ

- Selection thông thường duyệt nguồn và đánh giá predicate theo từng phần tử: O(n) nếu predicate có chi phí hằng số.
- Projection đánh giá biểu thức con cho từng phần tử và tạo List kết quả: O(n) thời gian và O(n) bộ nhớ kết quả.
- Selection rồi projection có thể tạo collection trung gian; với `n` phần tử và `k` phần tử được giữ, công việc cơ bản là O(n + k).
- Method trong selection/projection có thể chạy một lần cho mỗi phần tử; method đắt tiền hoặc I/O có thể chi phối toàn bộ chi phí.
- First selection có thể dừng ở match đầu tiên; last selection phải tiếp tục duyệt để xác định match cuối.
- Nested collection operations nhân số lần đánh giá theo kích thước từng cấp.
- Getter/property access vẫn có thể thực thi code; chú ý ORM lazy loading và N+1 queries.
- Parse một lần và tái sử dụng Expression; điều này không cache kết quả evaluation.
- SpEL compiler chỉ hỗ trợ một tập expression; xác minh khả năng biên dịch và benchmark đúng expression.
- Dùng JMH để đo parse, evaluation, allocation và so sánh với Java loop/Stream.
- Chuyển lọc lớn xuống database hoặc xử lý bằng Java khi cần streaming, pagination, join hoặc kiểm soát chi phí chi tiết.

## Tài liệu tham khảo

- [Spring Framework Reference — Collection Selection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework Reference — SpEL Compilation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — SpelParserConfiguration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParserConfiguration.html)
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh)
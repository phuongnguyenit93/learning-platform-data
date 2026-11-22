# Tái sử dụng parsed Expression khi biểu thức lặp lại

## 1. Vì sao nên parse một lần và evaluate nhiều lần?

SpEL tách việc phân tích cú pháp khỏi việc đánh giá expression:

- `ExpressionParser.parseExpression(source)` phân tích chuỗi và tạo một đối tượng `Expression`.
- `Expression.getValue(...)` đánh giá expression đã parse trên root object và EvaluationContext.

Một expression có thể được đánh giá nhiều lần, trên cùng hoặc trên các root object khác nhau. Vì vậy, nếu cùng một quy tắc được dùng trong nhiều request hoặc nhiều bản ghi, hãy parse một lần rồi tái sử dụng đối tượng Expression.

Ví dụ không nên làm trong vòng lặp:

```java
for (Customer customer : customers) {
    Expression expression =
            parser.parseExpression("age >= 18");

    Boolean eligible =
            expression.getValue(customer, Boolean.class);
}
```

Mỗi vòng lặp lại phân tích cùng một chuỗi và tạo AST mới. Cách phù hợp hơn:

```java
Expression expression =
        parser.parseExpression("age >= 18");

for (Customer customer : customers) {
    Boolean eligible =
            expression.getValue(customer, Boolean.class);
}
```

Trong ví dụ thứ hai, parser chỉ tạo Expression một lần; mỗi lần gọi `getValue()` vẫn đánh giá trên dữ liệu Customer hiện tại.

## 2. Vai trò của ExpressionParser và Expression

Hai abstraction có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Vòng đời sử dụng |
|---|---|---|
| `ExpressionParser` | Phân tích chuỗi SpEL và trả về Expression. | Có thể tái sử dụng để parse nhiều source. |
| `Expression` | Đại diện cho expression đã parse và thực hiện evaluation. | Được thiết kế để parse một lần, evaluate lặp lại. |
| `EvaluationContext` | Cung cấp root object, variables, property/method/type resolvers và các strategy khác. | Có thể được tạo một lần rồi tái sử dụng cho nhiều lần evaluation nếu cấu hình phù hợp. |

`SpelExpressionParser` có thể được tái sử dụng và thread-safe. Có thể tạo một parser dùng chung trong bean hoặc service:

```java
@Component
public class RuleEvaluator {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    public Expression parse(String source) {
        return parser.parseExpression(source);
    }
}
```

Tính thread-safe của parser không đồng nghĩa mọi object được truyền vào EvaluationContext cũng thread-safe. Root object, variable, custom PropertyAccessor, MethodResolver và các service được gọi từ expression vẫn phải tuân theo quy tắc đồng bộ của ứng dụng.

## 3. Ví dụ parse một lần, evaluate trên nhiều root object

Một Expression có thể được đánh giá trên các root object khác nhau:

```java
ExpressionParser parser = new SpelExpressionParser();

Expression eligibilityRule =
        parser.parseExpression("age >= #minimumAge and active");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumAge", 18);

Customer first = new Customer("Ada", 20, true);
Customer second = new Customer("Grace", 16, true);
Customer third = new Customer("Linus", 25, false);

Boolean firstResult =
        eligibilityRule.getValue(context, first, Boolean.class);

Boolean secondResult =
        eligibilityRule.getValue(context, second, Boolean.class);

Boolean thirdResult =
        eligibilityRule.getValue(context, third, Boolean.class);

// true, false, false
```

Expression giữ nguyên source và AST. Mỗi lần gọi `getValue(context, root, Boolean.class)`, SpEL đánh giá trên root object được truyền cho lần gọi đó.

Biến `#minimumAge` được lấy từ EvaluationContext. Nếu ngưỡng thay đổi theo request, có thể tạo EvaluationContext riêng và đặt variable tương ứng, miễn các context có cùng loại và cấu hình bảo mật tương đương.

## 4. Expression tái sử dụng không có nghĩa là kết quả được cache

Cần phân biệt ba loại dữ liệu:

- **Expression cache:** giữ đối tượng Expression đã parse để tránh parse lại source.
- **Evaluation metadata cache:** một số AST node có thể cache accessor hoặc executor đã tìm được trong lần evaluation trước.
- **Result cache:** giữ kết quả evaluation để trả lại mà không chạy expression lần nữa.

SpEL hỗ trợ hai loại đầu ở các mức phù hợp, nhưng việc tái sử dụng Expression không có nghĩa kết quả được cache.

Ví dụ:

```java
Expression expression =
        parser.parseExpression("balance >= #minimum");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimum", new BigDecimal("100"));

Boolean first = expression.getValue(
        context, account, Boolean.class);

// Account thay đổi balance.
account.setBalance(new BigDecimal("50"));

Boolean second = expression.getValue(
        context, account, Boolean.class);
```

Lần evaluation thứ hai đọc trạng thái hiện tại của object và có thể cho kết quả khác lần đầu. Nếu ứng dụng muốn cache kết quả, đó là một chính sách riêng ở tầng ứng dụng, cần xác định key, thời hạn, invalidation và tác động của dữ liệu thay đổi.

## 5. AST có thể cache accessor và executor

Để tránh phải tìm lại mọi strategy ở mỗi lần evaluation, các node trong AST của Expression có thể cache thành phần đã xử lý thành công, ví dụ:

- `PropertyAccessor`: truy cập property.
- `IndexAccessor`: truy cập phần tử theo index/key.
- `MethodExecutor`: thực hiện method invocation.
- `ConstructorExecutor`: thực hiện constructor invocation.

Khi expression được đánh giá lại, SpEL có thể dùng metadata đã cache nếu strategy đó vẫn phù hợp với EvaluationContext hiện tại. Nhờ vậy, các lần đánh giá sau có thể giảm công việc phân giải accessor/resolver.

Ví dụ, với expression:

```text
customer.address.city
```

Sau lần đánh giá đầu tiên, SpEL có thể ghi nhớ accessor phù hợp để đọc các property tương ứng. Những lần tiếp theo trên object tương thích có thể tái sử dụng đường truy cập đó.

Đây là cache nội bộ phục vụ evaluation. Ứng dụng không cần tự quản lý hoặc sửa các accessor cache trong AST. Cần chú ý rằng việc cache này có hệ quả đối với cách tái sử dụng Expression qua các EvaluationContext khác nhau.

## 6. Điều kiện tái sử dụng giữa các EvaluationContext

Spring hỗ trợ tái sử dụng một Expression trên:

- Các root object khác nhau.
- Các EvaluationContext khác nhau nhưng cùng loại và có cấu hình tương đương.
- Ví dụ: nhiều StandardEvaluationContext cùng đăng ký cùng loại custom PropertyAccessor và MethodResolver.

Nếu context có cấu hình khác nhau về security implication, không được dùng chung một Expression instance. Một Expression có thể đã cache accessor/executor từ lần đánh giá trước; metadata đó có thể được tái sử dụng trong lần đánh giá sau.

Đặc biệt, không đánh giá cùng một Expression trước bằng `StandardEvaluationContext`, rồi dùng lại nó bằng `SimpleEvaluationContext`. Context đầu tiên có thể cho phép nhiều khả năng hơn context thứ hai; cache từ lần đánh giá rộng quyền có thể làm mất hiệu lực các giới hạn mà ứng dụng mong đợi ở lần đánh giá sau.

Nếu cùng một source cần chạy ở hai security profile, hãy parse thành hai Expression riêng:

```java
ExpressionParser parser = new SpelExpressionParser();

String source = "customer.name";

Expression trustedExpression =
        parser.parseExpression(source);

Expression restrictedExpression =
        parser.parseExpression(source);

StandardEvaluationContext trustedContext =
        new StandardEvaluationContext();

SimpleEvaluationContext restrictedContext =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

// Chỉ dùng trustedExpression với context tin cậy.
// Chỉ dùng restrictedExpression với context giới hạn.
```

Không tái sử dụng Expression instance giữa hai nhóm context có quyền khác nhau, bất kể chúng là implementation EvaluationContext nào.

## 7. Không thay đổi resolver/accessor tùy tiện sau khi đã dùng Expression

Các context cùng loại và có cấu hình tương đương có thể dùng chung Expression. Tuy nhiên, việc thay đổi danh sách PropertyAccessor, IndexAccessor, MethodResolver, ConstructorResolver hoặc TypeLocator giữa các lần evaluation là điều không nên làm trong luồng thông thường.

Hãy cấu hình EvaluationContext một lần trước khi dùng:

```java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.addPropertyAccessor(customPropertyAccessor);
context.addMethodResolver(customMethodResolver);
context.setTypeConverter(customTypeConverter);

// Sau khi cấu hình xong, dùng context theo một policy ổn định.
```

Nếu một nhóm rule cần một tập accessor/resolver khác, tạo context và Expression riêng cho nhóm đó. Điều này làm rõ ranh giới quyền truy cập và tránh việc một expression cache bị dùng trong nhiều policy không tương đương.

## 8. Tạo cache Expression theo rule

Với rule cấu hình cố định, có thể parse khi ứng dụng khởi động và giữ Expression trong một registry:

```java
@Component
public class RuleRegistry {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    private final Map<String, Expression> expressions;

    public RuleRegistry() {
        Map<String, Expression> rules = new HashMap<>();

        rules.put(
                "adult-customer",
                parser.parseExpression("age >= 18"));

        rules.put(
                "active-customer",
                parser.parseExpression("active == true"));

        this.expressions = Map.copyOf(rules);
    }

    public Expression get(String ruleId) {
        Expression expression = expressions.get(ruleId);

        if (expression == null) {
            throw new IllegalArgumentException(
                    "Unknown rule: " + ruleId);
        }

        return expression;
    }
}
```

Registry trên chỉ minh họa cho tập rule cố định. Trong ứng dụng thực tế, nên giữ thông tin version và security profile của rule cùng Expression tương ứng.

Parse sớm có thêm lợi ích: lỗi cú pháp được phát hiện khi nạp cấu hình thay vì xuất hiện bất ngờ trong request đầu tiên. Nếu rule không parse được, ứng dụng có thể từ chối phiên bản cấu hình mới và giữ phiên bản đang hoạt động.

## 9. Cache expression động có giới hạn

Nếu administrator có thể tạo hoặc cập nhật rule trong lúc ứng dụng chạy, số lượng source có thể thay đổi. Một cache không giới hạn có nguy cơ tăng bộ nhớ theo số expression khác nhau.

Khi cần cache động:

- Dùng cache có giới hạn số entry hoặc giới hạn bộ nhớ.
- Dùng rule ID và version để nhận diện phiên bản expression.
- Đưa parser configuration và security profile vào chính sách phân tách cache.
- Loại bỏ entry cũ khi rule được thay thế hoặc thu hồi.
- Không cache source tùy ý từ người dùng cuối mà không có giới hạn kích thước và số lượng.
- Không ghi đè Expression của security profile này bằng Expression của profile khác.

Ví dụ key logic:

```java
record ExpressionCacheKey(
        String ruleId,
        long ruleVersion,
        String securityProfile) {
}
```

Cache thực tế còn cần đảm bảo source được gắn với đúng version của rule. Khi source thay đổi, tăng version hoặc tạo key mới để tránh dùng lại AST của nội dung cũ.

Không dùng source đã nối dữ liệu request làm key nếu có thể truyền dữ liệu qua variables. Cách này tạo nhiều expression gần giống nhau, làm cache phình ra và tăng chi phí parse.

## 10. Truyền dữ liệu qua variable thay vì tạo source mới

Một lỗi thường gặp là ghép dữ liệu đầu vào trực tiếp vào chuỗi expression:

```java
String source =
        "age >= " + request.getMinimumAge();

Expression expression =
        parser.parseExpression(source);
```

Mỗi giá trị minimumAge tạo một source khác nhau và có thể dẫn tới parse/cache entry mới. Cách này cũng khiến dữ liệu đầu vào bị trộn với cú pháp expression.

Nên giữ source ổn định và truyền dữ liệu qua variable:

```java
Expression expression =
        parser.parseExpression("age >= #minimumAge");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable(
        "minimumAge",
        request.getMinimumAge());

Boolean result = expression.getValue(
        context, customer, Boolean.class);
```

Cách này giúp tái sử dụng cùng Expression cho nhiều giá trị đầu vào, đồng thời tách dữ liệu khỏi cú pháp SpEL. Vẫn phải xác thực kiểu và phạm vi của variable theo quy tắc nghiệp vụ.

## 11. Tách context theo request khi dữ liệu thay đổi

Expression có thể dùng lại, nhưng EvaluationContext có thể chứa variables, root object hoặc dữ liệu phụ thuộc request. Không nên đặt dữ liệu nhạy cảm hoặc biến thay đổi theo request vào một context dùng chung rồi cập nhật đồng thời từ nhiều thread.

Ví dụ tạo context riêng cho mỗi lần đánh giá:

```java
private final Expression eligibility =
        parser.parseExpression("age >= #minimumAge");

public boolean isEligible(
        Customer customer,
        int minimumAge) {

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("minimumAge", minimumAge);

    Boolean result = eligibility.getValue(
            context, customer, Boolean.class);

    return Boolean.TRUE.equals(result);
}
```

Expression được tái sử dụng; context và variable được tạo theo lần gọi. Nếu context được tái sử dụng trong một luồng đồng bộ và cấu hình không thay đổi, điều đó cũng có thể phù hợp. Nhưng với request đồng thời, context mutable dùng chung có thể làm lẫn variable hoặc root object giữa các request.

Custom PropertyAccessor, MethodResolver và object được expose cũng cần có hành vi an toàn khi dùng đồng thời.

## 12. Không dùng chung parsed Expression giữa security profile

Đây là quy tắc đặc biệt quan trọng khi cache expression.

Ví dụ không an toàn:

```java
Expression shared =
        parser.parseExpression("customer.name");

Object trustedValue =
        shared.getValue(standardEvaluationContext, trustedRoot);

// Không dùng lại shared với context bị giới hạn quyền:
Object restrictedValue =
        shared.getValue(simpleEvaluationContext, untrustedRoot);
```

Spring không hỗ trợ cách dùng này vì AST có thể cache accessor/executor từ lần đánh giá đầu. Một context ít hạn chế hơn có thể đã làm lộ khả năng truy cập mà context sau không cho phép.

Cách đúng là tạo expression riêng cho từng security profile:

```java
Expression trusted =
        parser.parseExpression("customer.name");

Expression restricted =
        parser.parseExpression("customer.name");
```

Sau đó mỗi instance chỉ được đánh giá trong nhóm context tương ứng. Nếu rule có nhiều tenant hoặc nhiều quyền, hãy phân loại theo policy thực tế và tạo cache riêng khi security implication khác nhau.

## 13. Parse và evaluation có lỗi ở thời điểm khác nhau

Parse một lần giúp chuyển lỗi cú pháp về giai đoạn đăng ký rule:

```java
Expression expression;

try {
    expression = parser.parseExpression(source);
}
catch (ParseException ex) {
    throw new IllegalArgumentException(
            "Invalid rule syntax: " + ruleId,
            ex);
}
```

Evaluation vẫn có thể lỗi trên dữ liệu thực tế:

```java
try {
    Boolean result = expression.getValue(
            context, rootObject, Boolean.class);
}
catch (EvaluationException ex) {
    // Ghi nhận rule ID và nguyên nhân.
    throw new RuleEvaluationException(ruleId, ex);
}
```

Không cache một kết quả lỗi như thể expression hợp lệ. Nếu source không parse được, không tạo cache entry Expression thành công; hãy trả lỗi cấu hình rõ ràng. Nếu evaluation lỗi do một root object, điều đó không nhất thiết có nghĩa expression cần parse lại.

## 14. Đo lợi ích của việc tái sử dụng Expression

Để đo chính xác, cần tách chi phí parse và chi phí evaluation:

| Phần đo | Nội dung |
|---|---|
| Parse | Thời gian tạo Expression từ source. |
| Evaluate sau parse | Thời gian đánh giá một Expression đã có. |
| Parse mỗi lần | Mô phỏng cách tạo parser/expression lặp trong hot path. |
| Reuse | Parse một lần rồi đánh giá nhiều root object. |
| Cache hit/miss | Chi phí tra cache và parse khi cache miss. |

Benchmark nên:

- Dùng cùng expression và cùng dữ liệu cho hai cách.
- Warm-up JVM trước khi đo.
- Chạy đủ nhiều lần và nhiều vòng đo.
- Không gộp thời gian khởi động Spring context vào thời gian evaluation.
- Đo riêng trường hợp interpreted và compiled nếu parser bật compiler.
- Dùng JMH hoặc công cụ benchmark phù hợp khi cần số liệu tin cậy.
- Theo dõi cả allocation và GC nếu expression được gọi với tần suất cao.

Không mặc định rằng parse một lần sẽ làm toàn bộ evaluation nhanh hơn theo một tỷ lệ cố định. Lợi ích phụ thuộc độ phức tạp expression, số lần gọi, kiểu dữ liệu và accessor/resolver.

## 15. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| CPU cao trong vòng lặp | Gọi parseExpression cho cùng source ở mỗi vòng. | Parse một lần rồi tái sử dụng Expression. |
| Bộ nhớ tăng theo số request | Cache expression động không giới hạn hoặc tạo source khác nhau cho từng request. | Dùng cache bounded và truyền dữ liệu qua variables. |
| Rule mới vẫn chạy logic cũ | Cache key không có version hoặc không invalidate khi source thay đổi. | Gắn rule version vào key và loại bỏ entry cũ. |
| Expression chạy với quyền rộng sau đó vẫn dùng được ở context hạn chế | Cùng instance Expression được tái sử dụng giữa context có security implication khác nhau. | Parse Expression riêng cho từng security profile. |
| Context nhận nhầm variable của request khác | EvaluationContext mutable được chia sẻ đồng thời. | Tạo context riêng theo request hoặc cô lập state. |
| Parser được tạo liên tục | Không tái sử dụng SpelExpressionParser. | Dùng parser singleton; parser instance có thể tái sử dụng và thread-safe. |
| Nghĩ Expression cache luôn lưu kết quả | Nhầm AST/accessor cache với result cache. | Hiểu mỗi getValue vẫn đánh giá trên root/context hiện tại. |
| Thay resolver sau khi expression đã chạy gây khó dự đoán | Context thay đổi cấu hình giữa các lần evaluation. | Cấu hình context ổn định trước khi dùng. |
| Parse lỗi chỉ xuất hiện ở request đầu tiên | Chưa parse rule khi đăng ký/cấu hình. | Parse sớm và từ chối source sai cú pháp. |
| Benchmark không cho thấy lợi ích | Workload ít gọi, expression đơn giản hoặc đo sai giai đoạn. | Tách parse/evaluate, warm-up và đo workload thực. |

## 16. Quy trình triển khai parse-once/evaluate-many

1. Xác định expression nào được dùng lặp lại và có source ổn định.
2. Tạo SpelExpressionParser dùng chung với parser configuration phù hợp.
3. Parse source một lần khi khởi tạo hoặc khi đăng ký/version rule.
4. Xử lý ParseException ngay tại thời điểm nạp rule.
5. Lưu Expression trong registry/cache có giới hạn phù hợp.
6. Gắn cache entry với rule ID, version, parser configuration và security profile.
7. Khi evaluate, truyền root object và EvaluationContext phù hợp cho lần gọi đó.
8. Tái sử dụng Expression trên root object khác nhau hoặc context cùng loại/cấu hình tương đương.
9. Không tái sử dụng một Expression giữa context có security implication khác nhau.
10. Tạo context riêng khi variables/root object phụ thuộc request hoặc có thể thay đổi đồng thời.
11. Invalidate cache khi rule thay đổi hoặc bị thu hồi.
12. Benchmark parse và evaluation riêng biệt trước khi tối ưu thêm.

## 17. Ghi nhớ

- `ExpressionParser` parse source; `Expression` đánh giá AST đã parse.
- `parseExpression()` trả về Expression dùng được cho repeated evaluation.
- `SpelExpressionParser` instance có thể tái sử dụng và thread-safe.
- Parse một lần, evaluate nhiều lần giúp tránh parse cùng source trong hot path.
- AST có thể cache PropertyAccessor, IndexAccessor, MethodExecutor và ConstructorExecutor; đây không phải result cache.
- Có thể dùng cùng Expression với root object khác nhau và EvaluationContext cùng loại/cấu hình tương đương.
- Không tái sử dụng Expression giữa các context có security implication khác nhau; parse riêng cho từng profile.
- Tạo EvaluationContext riêng khi variables hoặc root object phụ thuộc request; đừng chia sẻ mutable context đồng thời nếu chưa có thiết kế đồng bộ.
- Cache động phải có giới hạn, versioning và invalidation.
- Dùng variables thay vì nối dữ liệu request vào source expression.
- Parse sớm để phát hiện lỗi cú pháp; evaluation vẫn có thể lỗi theo dữ liệu runtime.
- Đo parse/evaluate riêng biệt để xác định lợi ích thực tế.

## Tài liệu tham khảo

- [Spring Framework Reference — Evaluation, Lifecycle and Reuse](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [ExpressionParser Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ExpressionParser.html)
- [Expression Javadoc — Reuse and Security Implications](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/Expression.html)
- [EvaluationContext Javadoc — Lifecycle and Reuse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
- [SpelExpressionParser Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/standard/SpelExpressionParser.html)

# Thay đổi API đánh giá biểu thức giữa các phiên bản

## 1. Vì sao cần đọc API theo phiên bản?

Trong chương **Biểu thức giá trị** của module `SPRING_DATA_COMMONS`, việc nâng phiên bản có thể làm thay đổi lớp parser, kiểu context và điểm mở rộng được repository factory truyền xuống bộ xử lý truy vấn. Một biểu thức trong annotation có thể vẫn giữ nguyên, trong khi thư viện tùy biến của ứng dụng phải chuyển sang một API đánh giá khác.

Cần phân biệt ba loại mã:

| Loại mã | Ví dụ | Mức độ liên quan đến thay đổi API |
| --- | --- | --- |
| Khai báo repository thông thường | Interface CRUD, derived query, `@Query` | Chủ yếu cần xác minh hành vi module và cú pháp được hỗ trợ |
| Gọi parser trực tiếp | Utility tự parse và đánh giá biểu thức | Phải kiểm tra cú pháp đầu vào, kiểu kết quả và context |
| Tích hợp hạ tầng repository/mapping | Query lookup strategy, evaluator, factory tùy biến | Dễ bị tác động bởi deprecation, thay chữ ký và loại bỏ API |

Mục tiêu không phải thay mọi nơi có chữ `SpEL`. Mục tiêu là giữ đúng ý nghĩa biểu thức khi chuyển sang hợp đồng API mới, đồng thời giữ nguyên nguồn cấu hình, tham số lời gọi và khả năng mở rộng cần thiết.

Các mốc trong bài là **phiên bản Spring Data Commons**. Ví dụ API mới được trình bày theo hợp đồng của dòng 3.5.x, cùng những mốc xuất hiện từ 3.3/3.4 và thay đổi loại bỏ ở 4.0. Đây không phải kết luận về phiên bản dependency của một dự án cụ thể.

## 2. Phân biệt API Spring Framework với API Spring Data

### 2.1. Spring Framework tiếp tục cung cấp SpEL

Nhóm kiểu nền tảng của Spring Framework gồm:

```text
org.springframework.expression.Expression
org.springframework.expression.EvaluationContext
org.springframework.expression.spel.standard.SpelExpressionParser
org.springframework.expression.spel.support.StandardEvaluationContext
```

Các kiểu này biểu diễn ngôn ngữ SpEL, parser và context để giải quyết biến, property, method trong biểu thức. Việc Spring Data chuyển một số API sang tên `ValueExpression` không có nghĩa `SpelExpressionParser` đã bị thay thế trên toàn Spring Framework.

Ví dụ SpEL trực tiếp:

```java
import org.springframework.expression.Expression;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("code", "P-204");

Expression expression = new SpelExpressionParser().parseExpression("#code");
String result = expression.getValue(context, String.class);
```

Đầu vào `#code` ở đây là **SpEL thuần**. Ví dụ này không dựa vào property placeholder và chưa có context của một query method.

### 2.2. Spring Data bổ sung abstraction value expression

Nhóm API của Commons bao gồm:

```text
org.springframework.data.expression.ValueExpression
org.springframework.data.expression.ValueExpressionParser
org.springframework.data.expression.ValueEvaluationContext
org.springframework.data.expression.ValueEvaluationContextProvider
```

Abstraction mới tiếp nhận biểu thức có dạng template, placeholder cấu hình và literal. Chẳng hạn:

```text
#{#code}
${inventory.prefix:product}
${inventory.prefix:product}-#{#code}
```

Điểm chuyển đổi nằm ở hợp đồng xử lý đầu vào và context, không chỉ ở tên lớp. `ValueEvaluationContext` kết hợp nguồn `Environment` với context đánh giá SpEL được cung cấp. [ValueEvaluationContext, Commons 3.5](https://docs.spring.io/spring-data/commons/reference/3.5/api/java/org/springframework/data/expression/ValueEvaluationContext.html).

## 3. Những mốc thay đổi cần nhớ

| Mốc Commons | Thay đổi có liên quan | Ý nghĩa khi đọc hoặc chuyển mã |
| --- | --- | --- |
| Trước 3.3 | Nhiều đường tích hợp dùng API có tên `SpelQueryContext`, `SpelEvaluator` và SpEL evaluator cho mapping | Nhận diện đúng điểm tích hợp cũ; không áp dụng ví dụ mới khi artifact chưa có API tương ứng |
| 3.3 | Có `ValueExpressionParser`, `ValueExpression`, `ValueEvaluationContext` và abstraction liên quan | Có thể biểu diễn SpEL template, placeholder và literal qua API value expression |
| 3.3 | `SpelQueryContext` bị deprecate, hướng sang `ValueExpressionQueryRewriter` | Phần tách biểu thức khỏi query và thay bằng bind variable có hướng chuyển đổi mới |
| 3.4 | Có `QueryMethodValueEvaluationContextAccessor`; query-method provider cũ bị deprecate | Tách bước tạo provider theo metadata phương thức và bước lấy context theo giá trị argument |
| 3.4 | Có thêm một số tiện ích như `ValueExpressionParser.create()` không tham số | Phiên bản xuất hiện của interface không bảo đảm mọi overload đã tồn tại từ đầu |
| 3.5.x | API cũ còn được công bố nhưng có các đánh dấu deprecated/for removal | Có thể chuẩn bị chuyển đổi trước khi nâng sang major tiếp theo |
| 4.0 | Loại bỏ nhóm query-method provider cũ, `SpelEvaluator`, `SpelQueryContext` và một số evaluator/provider mapping cũ | Mã tích hợp trực tiếp phải dùng API thay thế; không thể chỉ ẩn cảnh báo |

Các mốc 3.3/3.4 được thể hiện ở Javadoc của [ValueExpressionParser](https://docs.spring.io/spring-data/commons/reference/3.5/api/java/org/springframework/data/expression/ValueExpressionParser.html), [SpelQueryContext](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/repository/query/SpelQueryContext.html) và [QueryMethodEvaluationContextProvider](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/repository/query/QueryMethodEvaluationContextProvider.html). Việc loại bỏ nhóm API cũ được ghi trong [Spring Data 2025.1 Release Notes, phần SpEL to Value Expression Migration](https://github.com/spring-projects/spring-data-commons/wiki/Spring-Data-2025.1-Release-Notes#-breaking-change-removal-of-deprecated-api).

Không đọc `@Deprecated(since = "3.4")` thành “API đã bị xóa ở 3.4”. Nó nêu mốc deprecation. `forRemoval` diễn đạt định hướng loại bỏ, còn mốc loại bỏ thực tế phải tra theo phiên bản đích.

Tương tự, Javadoc của một interface ghi `Since: 3.3` không chứng minh phương thức tiện ích thêm về sau cũng dùng được trên 3.3. Đây là nguyên nhân phổ biến của ví dụ trông đúng nhưng không biên dịch trên phiên bản đang học.

## 4. Bảng chuyển đổi theo trách nhiệm

| Điểm đang dùng trong mã cũ | Hướng chuyển đổi | Điều phải giữ lại |
| --- | --- | --- |
| `QueryMethodEvaluationContextProvider` | `QueryMethodValueEvaluationContextAccessor` tạo `ValueEvaluationContextProvider` | Metadata tham số, giá trị argument, environment và extensions |
| `ExtensionAwareQueryMethodEvaluationContextProvider` | Accessor với nguồn bean factory hoặc provider phù hợp | Các extension ứng dụng thực sự cần |
| Reactive query-method provider cũ | Hạ tầng accessor/provider hỗ trợ reactive | Việc lấy context trong reactive flow |
| `SpelQueryContext` và `SpelEvaluator` | `ValueExpressionQueryRewriter` và evaluator tương ứng | Query sau rewrite và quan hệ giữa biểu thức với bind value |
| Hook nhận query-method provider cũ | Chữ ký mới nhận `EvaluationContextProvider` hoặc `ValueExpressionDelegate`, tùy hook | Phân biệt cấu hình factory với điểm tạo query lookup strategy |
| `SpELExpressionParameterValueProvider` | `ValueExpressionParameterValueProvider` | Mapping parameter, cách đánh giá và chuyển kiểu |

Đây là bảng trách nhiệm, không phải quy tắc tìm-thay tên lớp một lần cho toàn dự án. Một API cũ có thể được tách thành nhiều bước mới; các kiểu cùng có tên “provider” có thể nằm ở các tầng khác nhau.

Ví dụ, factory setter mới nhận `org.springframework.data.spel.EvaluationContextProvider`, còn API đánh giá value expression dùng `org.springframework.data.expression.ValueEvaluationContextProvider`. Hai interface không phải hai tên viết khác nhau của cùng một kiểu.

## 5. Chuyển parser: giữ đúng cú pháp đầu vào

### 5.1. SpEL thuần và template không có cùng đầu vào

Với parser SpEL trực tiếp:

```java
Expression oldExpression = spelParser.parseExpression("#code");
```

Với value-expression parser:

```java
ValueExpression newExpression = valueParser.parse("#{#code}");
```

Nếu đưa nguyên chuỗi `#code` vào parser mới, chuỗi không có phần đánh dấu template có thể được xử lý như literal. Chương trình khi đó có thể trả lại `#code` thay vì giá trị biến mà không phát sinh lỗi cú pháp. Vì vậy kiểm chứng phải so sánh kết quả, không chỉ xác nhận “không ném exception”.

Đối với đoạn mã cũ đã dùng template parser context, đầu vào có thể vốn đã chứa `#{...}`. Cần xem đường parse thực tế trước khi thêm dấu ngoặc; không bọc mọi chuỗi một cách máy móc.

### 5.2. Khởi tạo parser theo mốc API

Dạng cấu hình parser được dùng với API từ 3.3:

```java
import org.springframework.data.expression.ValueExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ValueExpressionParser parser =
        ValueExpressionParser.create(SpelExpressionParser::new);
```

Từ 3.4 có thêm dạng tiện ích:

```java
ValueExpressionParser parser = ValueExpressionParser.create();
```

Cả hai cùng phục vụ việc tạo parser nhưng không có cùng mốc xuất hiện. Khi thư viện cần giữ baseline 3.3, không sao chép overload không tham số từ ví dụ thuộc dòng mới hơn.

### 5.3. Ví dụ đầy đủ: ghép cấu hình với biến của lần đánh giá

Lớp sau minh họa API có trên dòng 3.5.x và dùng dạng khởi tạo parser đã có từ 3.3:

```java
import java.util.Objects;
import org.springframework.core.env.Environment;
import org.springframework.data.expression.ValueEvaluationContext;
import org.springframework.data.expression.ValueExpression;
import org.springframework.data.expression.ValueExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public final class CodeLabelEvaluator {

    private final Environment environment;
    private final ValueExpression expression;

    public CodeLabelEvaluator(Environment environment) {
        this.environment = Objects.requireNonNull(environment);
        ValueExpressionParser parser =
                ValueExpressionParser.create(SpelExpressionParser::new);
        this.expression = parser.parse(
                "${inventory.prefix:product}-#{#code}");
    }

    public String evaluate(String code) {
        Objects.requireNonNull(code, "Code is required");
        StandardEvaluationContext spelContext = new StandardEvaluationContext();
        spelContext.setVariable("code", code);

        Object value = expression.evaluate(
                ValueEvaluationContext.of(environment, spelContext));

        if (!(value instanceof String label)) {
            throw new IllegalStateException("Label must be a String");
        }
        return label;
    }
}
```

Cách tạo dữ liệu minh họa:

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

StandardEnvironment environment = new StandardEnvironment();
environment.getPropertySources().addFirst(
        new MapPropertySource("lesson", Map.of("inventory.prefix", "sku")));

CodeLabelEvaluator evaluator = new CodeLabelEvaluator(environment);
String first = evaluator.evaluate("P-204");
String second = evaluator.evaluate("P-205");
```

Kết quả mong muốn:

```text
first  = sku-P-204
second = sku-P-205
```

Biểu thức được parse một lần khi tạo evaluator. Biến `code` được đưa vào context riêng cho từng lần đánh giá. Environment được truyền tường minh, nên việc lấy cấu hình không phụ thuộc một nguồn cấu hình ngầm do utility tự tạo.

Ví dụ không đăng ký bean resolver hay security extension. Việc một ứng dụng dùng thêm `@beanName`, tenant hoặc principal cần cấu hình context tương ứng; parser mới không tự cấp các đối tượng đó chỉ vì cú pháp hợp lệ.

## 6. Chuyển context cho query method

### 6.1. Mô hình cũ

Trong mã tích hợp cũ, có thể gặp ý tưởng sau:

```java
// Minh họa API cũ; không dùng đoạn này làm mã đích cho Commons 4.0.
EvaluationContext context = oldProvider.getEvaluationContext(
        queryMethod.getParameters(), argumentValues);
```

Provider nhận cả metadata tham số và giá trị của lần gọi để tạo context. Nếu utility cũ gọi parser SpEL trực tiếp, kết quả context này được truyền cho `Expression.getValue(...)`.

Điều quan trọng là context không chỉ chứa một object bất kỳ. Nó có thể còn chứa biến đặt tên theo metadata của query method và dữ liệu do extension cung cấp.

### 6.2. Mô hình mới tách thành hai bước

```text
Metadata của một query method
  -> accessor tạo provider phù hợp với Parameters
     -> provider nhận argument của lần gọi
        -> ValueEvaluationContext
           -> ValueExpression.evaluate(context)
```

`QueryMethodValueEvaluationContextAccessor` là factory tạo provider theo `Parameters`. Các constructor cho phép sử dụng environment, application context, bean factory hoặc evaluation-context provider tùy nhu cầu. [QueryMethodValueEvaluationContextAccessor, Commons 3.5](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/repository/query/QueryMethodValueEvaluationContextAccessor.html).

Ví dụ adapter dùng cho một query method cụ thể:

```java
import org.springframework.beans.factory.ListableBeanFactory;
import org.springframework.core.env.Environment;
import org.springframework.data.expression.ValueEvaluationContext;
import org.springframework.data.expression.ValueEvaluationContextProvider;
import org.springframework.data.expression.ValueExpression;
import org.springframework.data.expression.ValueExpressionParser;
import org.springframework.data.repository.query.QueryMethod;
import org.springframework.data.repository.query.QueryMethodValueEvaluationContextAccessor;
import org.springframework.expression.spel.standard.SpelExpressionParser;

public final class FirstArgumentEvaluator {

    private final ValueEvaluationContextProvider contextProvider;
    private final ValueExpression expression;

    public FirstArgumentEvaluator(
            QueryMethod queryMethod,
            Environment environment,
            ListableBeanFactory beanFactory) {

        QueryMethodValueEvaluationContextAccessor accessor =
                new QueryMethodValueEvaluationContextAccessor(
                        environment, beanFactory);

        this.contextProvider = accessor.create(queryMethod.getParameters());
        this.expression = ValueExpressionParser
                .create(SpelExpressionParser::new)
                .parse("#{[0]}");
    }

    public Object evaluate(Object[] argumentValues) {
        ValueEvaluationContext context =
                contextProvider.getEvaluationContext(argumentValues);
        return expression.evaluate(context);
    }
}
```

`QueryMethod` trong ví dụ do hạ tầng module cung cấp. Adapter yêu cầu phương thức có argument đầu tiên và mảng giá trị tương ứng đúng metadata của phương thức đó. Nó chỉ minh họa đánh giá argument, chưa bind vào query hay gọi database.

Provider đã tạo được gắn với metadata tham số đã chọn. Không dùng cùng một instance adapter cho mọi phương thức chỉ vì biểu thức `#{[0]}` giống nhau. Nếu hai phương thức có tham số đặc biệt hoặc biến đặt tên khác nhau, context được tạo có thể không tương đương.

### 6.3. Tránh mất environment và extensions khi dùng default

`QueryMethodValueEvaluationContextAccessor.create()` tạo accessor với `StandardEnvironment` và provider không có extension. Nó hữu ích cho trường hợp mặc định nhưng không tương đương việc lấy đầy đủ environment và bean factory của ứng dụng đang chạy.

Nếu mã cũ đọc cấu hình từ application context hoặc dùng security extension, thay nó bằng một default accessor có thể làm mất hành vi mà vẫn biên dịch. Trong tình huống đó, truyền environment và nguồn extension tương ứng rõ ràng hơn việc dựa vào mặc định.

`ValueEvaluationContextProvider` mới trả về `ValueEvaluationContext`, không phải `EvaluationContext` của Spring Framework. Không ép kiểu trực tiếp để làm compiler im lặng; cần truyền wrapper cho value expression hoặc truy cập đúng thành phần SpEL khi thực sự có nhu cầu. [ValueEvaluationContextProvider](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/expression/ValueEvaluationContextProvider.html).

## 7. Chuyển bộ xử lý biểu thức trong query

### 7.1. Trách nhiệm vẫn gồm rewrite và evaluate

Mã dùng `SpelQueryContext` trước đây thường thực hiện hai công việc:

1. Tìm biểu thức trong query và thay bằng các bind variable.
2. Đánh giá biểu thức với argument/context để có giá trị cho các biến đó.

Với `ValueExpressionQueryRewriter`, hai công việc này vẫn cần được nối với phần bind của module. Tên mới phản ánh khả năng xử lý value expressions, không phải một bộ thực thi SQL hoặc một cơ chế chuyển đổi toàn bộ query giữa các store.

Ví dụ hạ tầng theo API 3.5.x:

```java
import java.util.Map;
import org.springframework.data.expression.ValueExpressionParser;
import org.springframework.data.repository.query.ValueExpressionQueryRewriter;

// parser, accessor, queryMethod và argumentValues do lớp tích hợp chuẩn bị.
ValueExpressionQueryRewriter.EvaluatingValueExpressionQueryRewriter rewriter =
        ValueExpressionQueryRewriter.of(
                parser,
                (index, source) -> "expr_" + index,
                String::concat)
        .withEvaluationContextAccessor(accessor);

ValueExpressionQueryRewriter.QueryExpressionEvaluator evaluator =
        rewriter.parse(
                "select x from Example x where x.code = :#{[0]}",
                queryMethod.getParameters());

Map<String, Object> expressionBindings = evaluator.evaluate(argumentValues);
```

Đoạn mã minh họa cách chuẩn bị evaluator; query và các tên `expr_...` chỉ phục vụ ví dụ tích hợp. Module phải đưa query đã rewrite cùng các giá trị tương ứng vào bộ bind thực tế. Không đưa nguyên query còn marker biểu thức xuống driver rồi kỳ vọng driver hiểu SpEL.

Javadoc của rewriter mô tả cả `ParsedQuery`, evaluator và các hàm tạo tên/replacement cho bind variable. [ValueExpressionQueryRewriter](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/repository/query/ValueExpressionQueryRewriter.html).

### 7.2. Vai trò của ValueExpressionDelegate

Trong các điểm mở rộng mới, có thể gặp `ValueExpressionDelegate` thay cho việc truyền riêng parser và query-method provider. Delegate cung cấp parser cùng factory tạo context; phương thức `createValueContextProvider(parameters)` tạo provider cho một bộ metadata tham số cụ thể. [ValueExpressionDelegate](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/repository/query/ValueExpressionDelegate.html).

Nếu framework đã truyền delegate vào một hook, nên xem nó là nguồn cấu hình của điểm tích hợp đó. Tự tạo parser hoặc accessor mặc định khác có thể bỏ mất lựa chọn parser, environment hay context đã được framework chuẩn bị.

Không nhầm lớp Commons này với một query rewriter riêng của module chỉ có nhiệm vụ chỉnh văn bản query. Cùng có chữ “rewrite” chưa đủ để kết luận hai API có cùng hợp đồng.

## 8. Factory hook: cùng tên phương thức nhưng khác chữ ký

Trong dòng chuyển đổi 3.4, có các cặp API như:

| Điểm mở rộng | Chữ ký cũ | Hướng chữ ký mới |
| --- | --- | --- |
| Factory setter | `setEvaluationContextProvider(QueryMethodEvaluationContextProvider)` | `setEvaluationContextProvider(EvaluationContextProvider)` |
| Factory bean tạo provider mặc định | `createDefaultQueryMethodEvaluationContextProvider(...)` | `createDefaultEvaluationContextProvider(...)` |
| Factory tạo query lookup strategy | `getQueryLookupStrategy(Key, QueryMethodEvaluationContextProvider)` | `getQueryLookupStrategy(Key, ValueExpressionDelegate)` |

Các thay đổi được liệt kê trong [Deprecated API của Commons 3.4](https://docs.spring.io/spring-data/commons/docs/3.4.x/api/deprecated-list.html). Setter mới của factory dùng `org.springframework.data.spel.EvaluationContextProvider`; kiểu này tạo context SpEL nền tảng và khác với value-context provider ở lớp đánh giá. [EvaluationContextProvider](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/spel/EvaluationContextProvider.html).

Khi sửa subclass, giữ `@Override` để compiler phát hiện việc framework đã đổi điểm mở rộng. Một phương thức tình cờ giữ tên cũ nhưng không còn override đúng hook có thể trở thành phương thức không bao giờ được hạ tầng gọi.

Đừng truyền `null` chỉ để vượt qua một overload không còn phù hợp. Hãy xác định hook cần provider tầng nào, default của phiên bản đích là gì và phần tùy biến cũ có còn được bảo toàn hay không.

## 9. Đánh giá reactive không phải ép về đồng bộ

API reactive mới có `ReactiveValueEvaluationContextProvider` với `getEvaluationContextLater(...)` trả về `Mono<ValueEvaluationContext>`. Interface này xuất hiện từ 3.4. [ReactiveValueEvaluationContextProvider](https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/expression/ReactiveValueEvaluationContextProvider.html).

Một helper minh họa giữ việc lấy context trong flow:

```java
import org.springframework.data.expression.ReactiveValueEvaluationContextProvider;
import org.springframework.data.expression.ValueExpression;
import reactor.core.publisher.Mono;

public static Mono<String> evaluateText(
        ReactiveValueEvaluationContextProvider provider,
        ValueExpression expression,
        Object[] argumentValues) {

    return Mono.defer(() -> provider.getEvaluationContextLater(argumentValues))
            .flatMap(context -> Mono.justOrEmpty(expression.evaluate(context)))
            .map(value -> {
                if (!(value instanceof String text)) {
                    throw new IllegalStateException("Expression must return text");
                }
                return text;
            });
}
```

Helper cố ý biểu diễn kết quả null bằng `Mono.empty()`. Đây là hợp đồng của ví dụ, không phải quy tắc rằng null trong một query phải làm truy vấn biến mất hoặc được bỏ qua.

Không gọi `.block()` để chuyển API reactive thành kiểu context cũ chỉ cho dễ thay thế. Cũng không tạo context theo người dùng một lần lúc khởi tạo singleton rồi dùng lại cho mọi subscription. Việc accessor hỗ trợ reactive còn phụ thuộc provider nền tảng được cấu hình; đổi tên lớp không tự tạo tích hợp với nguồn context reactive của ứng dụng.

## 10. API mới không mở rộng đồng đều mọi khả năng của store

Thay đổi parser/context ở Commons không làm mọi annotation mapping, query language hoặc module store nhận cùng cú pháp.

| Giả định khi nâng cấp | Điều phải xác nhận |
| --- | --- |
| Có `ValueExpressionParser` nên mọi `@Query` nhận `${...}` | Parser của đúng module và phiên bản có tích hợp dạng đó không? |
| Query SpEL cũ giữ nguyên là đủ | Context biến, nguồn environment và giá trị bind có còn tương đương không? |
| Có API mới nên được dùng mọi bean trong context | Bean resolver/extension thực tế được cấu hình thế nào? |
| Query đọc chạy được nên count query cũng đúng | Predicate và context của query đếm có nhất quán không? |
| Đã đổi evaluator nên projection, sort và paging tự thích nghi | Query và mapping kết quả của store hỗ trợ gì? |
| Lấy username bằng biểu thức là đã có auditing | Auditing và đường lưu/cập nhật thực tế có được tích hợp riêng không? |

Cú pháp bind vẫn phải theo module: một dạng biểu thức bắt đầu bằng `:#{...}` trong SQL không được suy thành dạng `?#{...}` của một query JSON. Việc nâng API đánh giá không phải lý do đổi mọi marker trong annotation.

Số phiên bản artifact giữa các module cũng không nhất thiết giống nhau. Chọn tập dependency tương thích theo nền tảng quản lý dependency của ứng dụng; không ép mọi artifact Spring Data về cùng một số chỉ vì muốn đồng bộ Commons.

## 11. Một quy trình chuyển đổi có thể kiểm chứng

### 11.1. Ghi nhận hợp đồng hiện tại

Trước khi thay API trong một dự án thực tế, xác định:

- Phiên bản Commons, Spring Framework và module store đang được giải quyết ở build/runtime.
- Mã chỉ khai báo annotation hay trực tiếp gọi parser, provider và factory hook.
- Chuỗi đầu vào là SpEL thuần, template, placeholder hay query có marker bind.
- Context đến từ environment, argument, root object, biến đặt tên hay extension nào.
- Kiểu kết quả và chính sách cho null, thiếu cấu hình, thiếu biến.

Đây là công việc khảo sát khi thực hiện migration ứng dụng, không phải lý do tự sửa dependency trong một bài học về API.

### 11.2. Chuyển theo trách nhiệm

Một thứ tự thực hành hợp lý:

1. Chọn baseline đích và đối chiếu Javadoc đúng phiên bản.
2. Chuyển parser cùng định dạng chuỗi biểu thức tương ứng.
3. Chuyển context/provider, bảo toàn environment và các extension cần thiết.
4. Chuyển query rewriter và việc đưa kết quả vào bind parameters.
5. Chuyển factory hook hoặc constructor của module store đang tùy biến.
6. Kiểm chứng kết quả nghiệp vụ trước khi loại bỏ adapter cũ.

Nếu thư viện phải hỗ trợ nhiều dòng Spring Data, có thể tách adapter theo baseline hoặc tạo các bản phát hành phù hợp. Không mặc định một file bytecode tham chiếu trực tiếp API đã bị loại bỏ vẫn chạy được trên cả hai major chỉ vì đặt nhánh `if` quanh một lời gọi.

### 11.3. Phân biệt biên dịch, liên kết và hành vi

| Dấu hiệu | Nhóm vấn đề cần xem |
| --- | --- |
| `cannot find symbol` | API không có trong dependency biên dịch hoặc import không đúng |
| `NoSuchMethodError` | Dependency runtime khác với chữ ký được dùng khi biên dịch |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Còn tham chiếu đến kiểu không có trên classpath runtime |
| Override không còn hợp lệ | Hook đã đổi chữ ký hoặc đổi kiểu tham số |
| Trả lại nguyên `#code` | Chuỗi SpEL thuần bị xử lý như literal theo API mới |
| Placeholder không dùng cấu hình ứng dụng | Environment bị thay bằng nguồn mặc định hoặc không được truyền đúng |
| Không tìm thấy principal/hàm tùy biến | Context bị mất extension hoặc khởi tạo sai tầng |
| Giá trị từ lần gọi trước xuất hiện lại | Lưu nhầm context hoặc kết quả đánh giá vào trạng thái dùng chung |

Xóa cảnh báo deprecated không phải cách xử lý các lỗi này. Đồng thời, một lần biên dịch thành công chưa đủ chứng minh bind value, kiểu kết quả hoặc dữ liệu theo người dùng vẫn đúng.

## 12. Các tình huống thực hành nên kiểm chứng

Với ví dụ `CodeLabelEvaluator`, có thể xác định các kỳ vọng sau:

| Tình huống | Kết quả hoặc hợp đồng mong muốn |
| --- | --- |
| Prefix `sku`, code `P-204` | `sku-P-204` |
| Cùng evaluator, code tiếp theo `P-205` | `sku-P-205`, không giữ code cũ |
| Không có prefix ở bất kỳ nguồn property nào | Dùng fallback `product` trong biểu thức |
| Code chứa ký tự `#{...}` | Được giữ là dữ liệu của biến, không tự đánh giá lần hai |
| Thiếu biến mà biểu thức bắt buộc dùng | Xử lý theo chính sách lỗi/null đã công bố |
| Biểu thức cho kiểu khác String | Bị từ chối theo hợp đồng lớp ví dụ |

Với phần tích hợp repository, cần bổ sung tình huống biến đặt tên từ metadata phương thức, argument thay đổi, extension được cấp đúng phạm vi và dữ liệu bind tới query cuối cùng. Nếu ứng dụng dùng phân trang hoặc reactive, kiểm chứng các đường đó riêng theo khả năng store.

Biểu thức nên đến từ nguồn tin cậy như mã ứng dụng hoặc cấu hình do ứng dụng quản lý. Khi chuyển sang context mới, không mở rộng quyền truy cập chỉ để một biểu thức từ nguồn không xác định chạy được. Giữ dữ liệu người dùng ở vai trò giá trị argument và giữ phạm vi context đúng nhu cầu.

Khi học hoặc nâng cấp, hãy đọc đồng thời tên kiểu, chữ ký phương thức, mục `Since` và ghi chú deprecation của đúng phiên bản. Một chuyển đổi hoàn chỉnh phải bảo toàn được chuỗi biểu thức, nguồn context, kiểu kết quả và cách bind vào store; thay tên API chỉ là một phần của công việc đó.

# Cache, thời điểm đánh giá và chi phí thực thi

## 1. Mục tiêu và phạm vi

Trong chương **Biểu thức giá trị** của module **Spring Data Commons**, bài này giải thích một vấn đề thường gây nhầm lẫn: khi biểu thức được cache, phần nào thực sự được giữ lại và phần nào vẫn phải chạy ở mỗi lần sử dụng?

Sau bài học, bạn cần có khả năng:

- Phân biệt cache biểu thức đã parse với cache kết quả đánh giá.
- Xác định thời điểm đánh giá theo điểm tích hợp của repository hoặc mapper.
- Nhận diện chi phí tạo context, phân giải placeholder và thực thi SpEL.
- Tối ưu biểu thức mà vẫn giữ đúng dữ liệu của từng lần gọi.
- Thiết kế phép đo để chứng minh một thay đổi có ích.

Spring Data Commons cung cấp abstraction chung. Module store quyết định cách tích hợp abstraction đó vào truy vấn và mapping metadata. Vì vậy, không có một lịch đánh giá duy nhất áp dụng cho mọi annotation, mọi repository và mọi loại kho dữ liệu.

## 2. Tách ba đối tượng trước khi nói về cache

Xét biểu thức:

```text
orders-${app.stage:dev}-#{#tenant}
```

Giả sử `app.stage=qa` và biến SpEL `tenant=shop-a`. Kết quả mong đợi là chuỗi `orders-qa-shop-a`.

Trong quá trình xử lý có ba đối tượng khác nhau:

| Đối tượng | Nội dung | Có phụ thuộc dữ liệu của lần gọi không? |
| --- | --- | --- |
| Chuỗi khai báo | Văn bản chứa literal, placeholder và SpEL | Có thể cố định trong mã hoặc metadata |
| Biểu thức đã parse | Cấu trúc có thể được đánh giá với context | Có thể tái sử dụng cho nhiều context |
| Kết quả đánh giá | Ví dụ `orders-qa-shop-a` | Có thể phụ thuộc tenant, cấu hình và dữ liệu khác |

Tài liệu [Value Expressions Fundamentals](https://docs.spring.io/spring-data/commons/reference/value-expressions.html) nêu rằng các instance `ValueExpression` có thể được cache để tránh parse lặp lại, còn việc đánh giá vẫn có chi phí ở những lần sử dụng.

Từ đó cần phân biệt hai thao tác:

```text
parse("orders-${app.stage:dev}-#{#tenant}")
    -> một ValueExpression

expression.evaluate(contextA)
    -> "orders-qa-shop-a"

expression.evaluate(contextB)
    -> "orders-qa-shop-b"
```

Cùng một biểu thức đã parse vẫn có thể tạo ra nhiều kết quả đúng với các context khác nhau.

### 2.1. Cache biểu thức đã parse

Mục tiêu là tránh phân tích lại một chuỗi khai báo quen thuộc.

Cache giữ một đối tượng có thể thực thi lại. Nó không cần đóng băng giá trị `tenant` hoặc `app.stage` tại lần đầu tiên gặp biểu thức.

Đây thường là điểm bắt đầu phù hợp khi ứng dụng có tập biểu thức khai báo ổn định.

### 2.2. Cache kết quả đánh giá

Mục tiêu là bỏ qua cả bước đánh giá nếu đã có kết quả phù hợp.

Việc này làm thay đổi câu hỏi thiết kế. Ngoài chuỗi biểu thức, bạn phải xác định những đầu vào nào ảnh hưởng đến kết quả, chúng thay đổi lúc nào và cache được làm mới ra sao.

Nếu chỉ dùng chuỗi khai báo làm khóa cho kết quả, hai tenant có thể nhận cùng một tên đích dù context của họ khác nhau.

### 2.3. Các loại cache ở tầng khác

| Loại cache | Thứ được giữ lại | Không được suy ra từ đó |
| --- | --- | --- |
| Cache metadata repository | Thông tin phương thức và cấu trúc truy vấn | Mọi tham số động đã được tính sẵn |
| Cache parse biểu thức | ValueExpression hoặc cấu trúc tương ứng | Kết quả không còn phụ thuộc context |
| Cache kết quả biểu thức | Giá trị đã tính với chính sách cache cụ thể | Đó là hành vi mặc định của Commons |
| Cache plan hoặc statement của database/driver | Kế hoạch hay đối tượng phục vụ truy vấn | SpEL không còn phải chạy |
| Cache dữ liệu nghiệp vụ | Dữ liệu ứng dụng đọc được | Biểu thức định tuyến đã được cache đúng |

Một ứng dụng có thể sử dụng nhiều loại cache cùng lúc. Khi phân tích hiệu năng, cần gọi đúng tên phần đang được đo.

## 3. Biểu thức được đánh giá lúc nào?

### 3.1. Parse và evaluate có vòng đời riêng

Có thể hình dung luồng xử lý như sau:

```text
Đọc chuỗi khai báo
    -> parse khi cần
    -> giữ biểu thức đã parse

Khi nơi tích hợp cần giá trị:
    -> lấy dữ liệu và context phù hợp
    -> evaluate biểu thức
    -> dùng kết quả cho truy vấn hoặc mapping
```

Parse có thể diễn ra khi khởi tạo hạ tầng, khi tạo metadata hoặc ở lần sử dụng đầu tiên. Chi tiết tùy module, cấu hình khởi tạo và phiên bản.

Không xem việc ứng dụng khởi động thành công là bằng chứng mọi biểu thức đã được đánh giá với đầy đủ dữ liệu thực tế. Một biểu thức đúng cú pháp vẫn có thể lỗi khi thiếu property, thiếu biến hoặc gọi một phương thức không hợp lệ trong context.

### 3.2. Query method của repository

Khi biểu thức phụ thuộc tham số phương thức, context dùng để tính giá trị cần phản ánh những tham số của lần gọi tương ứng.

Ví dụ, một biểu thức tham chiếu mã tenant của lần gọi không thể được thay bằng kết quả tính từ tenant đầu tiên chỉ vì metadata phương thức đã được cache.

`ValueExpressionDelegate` phối hợp parser với cơ chế tạo context provider cho tham số query method. API của nó phân biệt tạo provider theo metadata tham số và tạo context dựa trên giá trị tham số thực tế; xem [ValueExpressionDelegate](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/ValueExpressionDelegate.html).

Tuy nhiên, không đặt giả định “một lần gọi repository luôn bằng đúng một lần evaluate”:

- Một thao tác có thể sử dụng nhiều biểu thức.
- Truy vấn phân trang có thể có nhánh lấy dữ liệu và nhánh count tùy trường hợp.
- Những đường xử lý bổ sung hoặc cách tái sử dụng context khác nhau có thể thay đổi số lần đánh giá.

Cần đo đường thực thi cụ thể của module đang dùng. Không đưa tác dụng phụ vào biểu thức rồi dựa vào một số lần gọi ngầm định.

### 3.3. Mapping metadata của store

Annotation là nơi khai báo biểu thức, nhưng không tự quyết định rằng biểu thức chỉ được đánh giá một lần khi khởi động.

Một ví dụ cụ thể: API `@Document` của Spring Data MongoDB mô tả thuộc tính `collection` hỗ trợ SpEL để tính tên collection theo từng operation. Xem [Document.collection](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Document.html).

Như vậy, trong trường hợp được module hỗ trợ, tên đích động có thể cần được tính khi thực hiện thao tác, dù metadata entity đã tồn tại từ trước.

Không suy rộng hợp đồng này sang mọi annotation mapping hoặc store khác. Những nơi xử lý tên trường, chỉ mục, tên bảng hay giá trị thuộc tính có thể có thời điểm và cơ chế riêng.

### 3.4. Luồng reactive

Với API reactive, cần phân biệt thời điểm:

1. Gọi phương thức để tạo publisher.
2. Subscribe publisher.
3. Thực thi đoạn pipeline cần đến giá trị biểu thức.

Thời điểm cụ thể do đường tích hợp quyết định. Không chỉ nhìn kiểu trả về `Mono` hoặc `Flux` rồi kết luận biểu thức luôn được đánh giá tại cùng một mốc.

Nếu giá trị phụ thuộc context của subscriber, cần xác minh dữ liệu được lấy tại đúng thời điểm. Cache kết quả ở bước tạo publisher có thể giữ một giá trị không còn phù hợp khi publisher được sử dụng về sau.

## 4. Chi phí vẫn còn sau khi cache parse

Cache parse chỉ loại bỏ một phần công việc.

| Thành phần | Công việc có thể xảy ra | Cache parse có loại bỏ không? |
| --- | --- | --- |
| Parse | Phân tích cú pháp và tạo cấu trúc biểu thức | Có thể tránh khi cache hit |
| Tra cache | Tìm biểu thức đã parse | Vẫn có nếu dùng cache tra theo khóa |
| Tạo context | Chuẩn bị root object, biến, extension, provider | Thường vẫn cần theo đường tích hợp |
| Placeholder | Tìm property qua Environment | Vẫn có khi đánh giá placeholder |
| SpEL | Truy cập thuộc tính, toán tử, điều kiện, gọi phương thức | Vẫn có khi đánh giá |
| Công việc trong phương thức được gọi | Tính toán, truy vấn hoặc I/O do ứng dụng viết | Không bị loại bỏ bởi cache parse |
| Tạo kết quả | Nối chuỗi, tạo đối tượng, xử lý kiểu | Vẫn có theo biểu thức |
| Database chính | Gửi và thực thi truy vấn của thao tác repository | Là chi phí riêng |

Hai biểu thức có độ dài tương tự có thể có chi phí rất khác:

```text
#{#tenant}
#{#policy.resolveTarget(#tenant)}
```

Biểu thức đầu chỉ đọc một biến. Biểu thức sau còn thực thi logic của `policy`. Nếu `resolveTarget` gọi database hoặc dịch vụ mạng, chi phí đó có thể lớn hơn nhiều so với parse.

Cache đối tượng biểu thức không làm phương thức `resolveTarget` tự trở thành hàm ghi nhớ kết quả.

### 4.1. Mô hình chi phí đơn giản

Đặt:

- `N`: số lần đánh giá thực tế.
- `M`: số lần parse do cache miss.
- `P`: chi phí parse trung bình.
- `L`: chi phí tra cache trung bình.
- `C`: chi phí chuẩn bị context trung bình.
- `E`: chi phí đánh giá biểu thức, gồm logic được nó gọi.
- `F`: chi phí tạo hoặc xử lý kết quả.

Một mô hình gần đúng:

```text
Parse lại mỗi lần:
T ≈ N × (P + C + E + F)

Cache biểu thức đã parse:
T ≈ M × P + N × (L + C + E + F)
```

Nếu giữ trực tiếp một biểu thức trong field, có thể không cần bước tra cache theo chuỗi ở mỗi lần gọi. Mô hình này chưa tính mọi chi phí quản lý bộ nhớ, cạnh tranh giữa thread hoặc database bên ngoài phần biểu thức.

Nếu `E` rất lớn do I/O, chỉ giảm `P` sẽ có tác dụng giới hạn. Nếu có nhiều biểu thức đơn giản được gọi liên tục, giảm parse lặp lại có thể đáng kể hơn.

### 4.2. Ví dụ bằng số lần công việc

Giả sử thực thi tuần tự 10.000 lượt, chỉ có 5 chuỗi khai báo khác nhau, cache đủ giữ cả 5 và không có eviction:

| Công việc | Parse lại mỗi lượt | Cache parse sau khi được làm nóng |
| --- | --- | --- |
| Parse | 10.000 lần | 5 lần cache miss ban đầu |
| Evaluate | 10.000 lần | 10.000 lần |
| Chuẩn bị context riêng cho từng lượt trong kịch bản | 10.000 lần | 10.000 lần |
| Gọi phương thức trong biểu thức, nếu mỗi evaluate gọi nó một lần | 10.000 lần | 10.000 lần |

Đây là mô hình minh họa, không phải số liệu benchmark. Với đồng thời, eviction hoặc cách tổ chức khác, số lần parse có thể khác; không dùng bảng này như cam kết “mỗi khóa chỉ parse đúng một lần” cho mọi cache.

## 5. Ví dụ: parse một lần, đánh giá theo từng context

Ví dụ sau dùng API Commons để minh họa vòng đời rõ ràng. Nó không tự đăng ký vào mapper hoặc repository của một store.

Biểu thức cố định:

```text
orders-${app.stage:dev}-#{#tenant}
```

Biến `tenant` là chuỗi trong mỗi context. Cả placeholder và đoạn SpEL của mẫu đều tạo các mảnh chuỗi.

```java
package com.example.expressions;

import java.util.Map;
import java.util.Objects;

import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;
import org.springframework.data.expression.ValueEvaluationContext;
import org.springframework.data.expression.ValueExpression;
import org.springframework.data.expression.ValueExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public final class OrderTargetResolver {

    private static final String SOURCE =
            "orders-${app.stage:dev}-#{#tenant}";

    private final Environment environment;
    private final ValueExpression parsedExpression;

    public OrderTargetResolver(Environment environment) {
        this.environment = Objects.requireNonNull(environment);

        ValueExpressionParser parser =
                ValueExpressionParser.create(SpelExpressionParser::new);

        this.parsedExpression = parser.parse(SOURCE);
    }

    public String resolve(String tenant) {
        StandardEvaluationContext spelContext =
                new StandardEvaluationContext();

        spelContext.setVariable(
                "tenant", Objects.requireNonNull(tenant));

        ValueEvaluationContext context =
                ValueEvaluationContext.of(environment, spelContext);

        Object result = parsedExpression.evaluate(context);

        if (!(result instanceof String value)) {
            throw new IllegalStateException(
                    "The target expression must return a String");
        }

        return value;
    }

    public static void main(String[] args) {
        StandardEnvironment environment = new StandardEnvironment();

        environment.getPropertySources().addFirst(
                new MapPropertySource(
                        "demo",
                        Map.of("app.stage", "qa")));

        OrderTargetResolver resolver =
                new OrderTargetResolver(environment);

        System.out.println(resolver.resolve("shop-a"));
        System.out.println(resolver.resolve("shop-b"));

        environment.getPropertySources().replace(
                "demo",
                new MapPropertySource(
                        "demo",
                        Map.of("app.stage", "prod")));

        System.out.println(resolver.resolve("shop-a"));
    }
}
```

Kết quả dự kiến:

```text
orders-qa-shop-a
orders-qa-shop-b
orders-prod-shop-a
```

Với một instance `resolver` trong ví dụ:

- Constructor gọi parse một lần.
- Mỗi lần `resolve` đánh giá lại cùng đối tượng biểu thức.
- Dữ liệu tenant được đặt vào context riêng của lần gọi.
- Lần cuối đọc được property source đã được thay tường minh.

Việc thay property source trong `main` chỉ minh họa rằng cache parse không đóng băng giá trị cấu hình. Nó không có nghĩa sửa file cấu hình trên đĩa sẽ tự cập nhật Environment của mọi ứng dụng.

Nếu tạo lại `OrderTargetResolver` cho từng request, lợi ích parse một lần theo instance cũng bị mất. Vòng đời đối tượng giữ biểu thức phải phù hợp với cách ứng dụng sử dụng.

Các API `ValueExpression`, `ValueExpressionParser` và `ValueEvaluationContext` xuất hiện từ Spring Data Commons 3.3; khi áp dụng, đối chiếu dependency của dự án.

## 6. Những cơ chế cache có sẵn trong Commons

### 6.1. CachingValueExpressionDelegate

Spring Data Commons cung cấp `CachingValueExpressionDelegate`, một biến thể có cache của `ValueExpressionDelegate`. Nó có từ phiên bản 3.4; xem [CachingValueExpressionDelegate API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/CachingValueExpressionDelegate.html).

Ví dụ khởi tạo parser có cache để tái sử dụng:

```java
import org.springframework.data.expression.ValueExpression;
import org.springframework.data.expression.ValueExpressionParser;
import org.springframework.data.repository.query.CachingValueExpressionDelegate;
import org.springframework.data.repository.query.ValueExpressionDelegate;

ValueExpressionParser cachedParser =
        new CachingValueExpressionDelegate(
                ValueExpressionDelegate.create());

ValueExpression first =
        cachedParser.parse("orders-#{#tenant}");

ValueExpression next =
        cachedParser.parse("orders-#{#tenant}");
```

Đoạn này minh họa cache ở thao tác parse. Kết quả đánh giá vẫn chỉ được tạo khi gọi `evaluate` với context thích hợp.

Không khởi tạo `cachedParser` mới ở mỗi lần sử dụng rồi kỳ vọng các lần gọi chia sẻ cache cũ.

Factory `ValueExpressionDelegate.create()` cung cấp cấu hình mặc định, không tự thay thế parser và context provider của repository đang chạy. Nếu cần Environment hoặc extension của ứng dụng, phải dùng đúng điểm tích hợp của hạ tầng thực tế.

Trong mã nguồn nhánh 3.5.x, delegate này dùng `ConcurrentLruCache<String, ValueExpression>` với dung lượng 256; xem [CachingValueExpressionDelegate 3.5.x](https://github.com/spring-projects/spring-data-commons/blob/3.5.x/src/main/java/org/springframework/data/repository/query/CachingValueExpressionDelegate.java). Đây là chi tiết của implementation và phiên bản được dẫn, không phải quy tắc dung lượng cho mọi cache biểu thức của Spring.

### 6.2. CachingValueExpressionEvaluatorFactory

Ở hạ tầng mapping, `CachingValueExpressionEvaluatorFactory` là một thành phần khác. Factory tạo evaluator gắn với source/root object và có cấu hình kích thước cache; xem [CachingValueExpressionEvaluatorFactory API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/mapping/model/CachingValueExpressionEvaluatorFactory.html).

Không đánh đồng việc factory tồn tại lâu dài với việc root object của lần đọc trước sẽ được dùng cho mọi lần đọc tiếp theo. Cần phân biệt hạ tầng có thể dùng chung và evaluator/context gắn với dữ liệu cụ thể.

Thông thường, trước khi thêm cache tự viết, hãy kiểm tra store đã sử dụng cơ chế nào. Xếp thêm nhiều tầng cache parse cho cùng một tập biểu thức có thể chỉ tăng bộ nhớ và độ phức tạp mà không giải quyết nút thắt thực tế.

## 7. Context, dependency và tính đúng khi chạy đồng thời

### 7.1. Chia sẻ biểu thức không có nghĩa chia sẻ mọi trạng thái

Một đối tượng biểu thức đã parse có thể tái sử dụng, nhưng việc đánh giá còn phụ thuộc:

- Root object.
- Biến gắn với từng lần gọi.
- Bean, function hoặc extension được expose.
- Environment và các property source.
- Trạng thái mà những phương thức được gọi tiếp tục đọc.

Nếu hai thread sửa cùng một biến `tenant` trong một context dùng chung, cache parse đúng vẫn không đảm bảo kết quả đúng cho từng thread.

Ví dụ ở mục 5 chủ động tạo context riêng cho mỗi lần gọi để làm rõ vòng đời dữ liệu. Không phải mọi ứng dụng đều bắt buộc tạo mới toàn bộ hạ tầng context; việc tái sử dụng context chỉ phù hợp khi trạng thái và cách truy cập của nó đã được kiểm soát.

Các phương thức được biểu thức gọi cũng phải phù hợp với việc thực thi đồng thời. Tính chất của đối tượng biểu thức không biến dependency có trạng thái thay đổi thành dependency an toàn để dùng chung.

### 7.2. ExpressionDependencies hỗ trợ context, không chứng minh tính thuần

`ValueExpression` có API `getExpressionDependencies()`. `ValueEvaluationContextProvider` có overload nhận dependency để tạo context phù hợp với những phần biểu thức cần truy cập; xem [ValueExpression API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/expression/ValueExpression.html) và [ValueEvaluationContextProvider API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/expression/ValueEvaluationContextProvider.html).

Mẫu sử dụng ở mức ý tưởng:

```java
ValueEvaluationContext context =
        provider.getEvaluationContext(
                rootObject,
                expression.getExpressionDependencies());

Object value = expression.evaluate(context);
```

Mức tối ưu phụ thuộc implementation của provider. Việc truyền dependency không tự đảm bảo mọi chi phí tạo context đã biến mất.

Ngoài ra, danh sách dependency được phát hiện không phải bằng chứng rằng kết quả chỉ phụ thuộc một vài tên xuất hiện trong biểu thức. Một phương thức như `policy.resolveTarget(...)` có thể đọc cấu hình, thời gian hoặc dữ liệu bên ngoài.

Không dùng thông tin dependency này như một khóa cache kết quả hoàn chỉnh nếu chưa kiểm tra hợp đồng nghiệp vụ.

## 8. Khi nào có thể giữ lại kết quả?

Chỉ giữ kết quả khi có chính sách rõ ràng về phạm vi hợp lệ của nó.

| Dữ liệu ảnh hưởng kết quả | Câu hỏi phải giải quyết trước khi giữ kết quả |
| --- | --- |
| Cấu hình cố định trong vòng đời ứng dụng | Ứng dụng có chủ đích dùng snapshot cấu hình từ lúc khởi tạo không? |
| Tenant hoặc tham số phương thức | Khóa và phạm vi cache có phân biệt đúng dữ liệu của lần gọi không? |
| Người dùng và chính sách quyền | Khi trạng thái chính sách thay đổi, kết quả cũ còn hợp lệ không? |
| Cấu hình định tuyến có phiên bản | Cơ chế invalidation hoặc thay phiên bản hoạt động thế nào? |
| Thời gian hiện tại hoặc dữ liệu biến động | Hợp đồng nghiệp vụ có cho phép dùng giá trị cũ trong khoảng thời gian nào? |

Một TTL bất kỳ chỉ giới hạn tuổi dữ liệu. Nó không tự chứng minh kết quả là đúng trong thời gian đó.

### 8.1. Cấu hình được đọc một lần phải là quyết định có chủ đích

Có những giá trị ứng dụng muốn cố định trong suốt vòng đời một component. Khi đó, đọc và xác thực chúng lúc khởi tạo có thể là thiết kế phù hợp.

Tuy nhiên, cần gọi đúng bản chất: đây là một snapshot cấu hình theo vòng đời đã chọn. Nó khác với tối ưu cache parse trong khi vẫn đánh giá lại mỗi lần.

Nếu hệ thống hỗ trợ refresh cấu hình, phải xác định component nào được tạo lại hoặc kết quả nào phải bị loại bỏ khi cấu hình thay đổi.

### 8.2. Tránh cache kết quả chỉ theo chuỗi biểu thức

Ví dụ một thiết kế sai về phạm vi:

```text
Khóa:
"orders-${app.stage}-#{#tenant}"

Giá trị cache sau lần đầu:
"orders-qa-shop-a"
```

Tenant `shop-b` dùng cùng chuỗi khai báo nhưng cần kết quả khác. Chuỗi biểu thức là khóa phù hợp cho cấu trúc đã parse trong một cấu hình parser ổn định; nó thường không đủ để định danh kết quả đánh giá.

Ngay cả cache parse tự viết cũng cần có phạm vi rõ ràng. Nếu cùng một chuỗi được parse với các cấu hình ngôn ngữ khác nhau, không trộn các cấu hình đó trong một cache toàn cục chỉ có khóa chuỗi.

## 9. Tối ưu theo thứ tự có ích

### 9.1. Giữ ổn định nguồn biểu thức

Thay vì tạo một chuỗi khai báo riêng cho từng giá trị tenant, dùng một biểu thức ổn định và truyền dữ liệu qua context:

```text
Một biểu thức:
orders-#{#tenant}

Nhiều context:
tenant = shop-a
tenant = shop-b
tenant = shop-c
```

Cách này giữ số lượng khóa parse nhỏ và thể hiện rõ phần nào là dữ liệu.

Nếu liên tục sinh nhiều chuỗi mới, cache có giới hạn có thể phải loại bỏ các biểu thức cũ. Lúc đó cache miss tăng dù ứng dụng đã bật cache.

Nguồn biểu thức cũng nên do ứng dụng kiểm soát. Dữ liệu của request được truyền như giá trị, không cần biến thành mã SpEL mới.

### 9.2. Đưa công việc nặng ra khỏi biểu thức

Biểu thức ngắn gọn có thể phù hợp cho việc chọn một giá trị, truy cập tham số hoặc tạo một nhãn đơn giản.

Nếu biểu thức gọi một chuỗi xử lý dài, truy vấn dữ liệu lặp lại hoặc thực hiện I/O, hãy xem xét tính toán ở tầng nghiệp vụ rồi cung cấp kết quả cần thiết vào context. Khi đó có thể quản lý rõ hơn:

- Số lần truy cập dữ liệu.
- Vòng đời và phạm vi tái sử dụng kết quả.
- Lỗi, timeout và hành vi khi dữ liệu thay đổi.
- Khả năng quan sát và đo hiệu năng.

Đây là thay đổi cách tổ chức công việc, không phải chỉ tăng kích thước cache.

### 9.3. Tránh biểu thức cho giá trị cố định không cần tính toán

Literal `orders` không cần viết thành `#{'orders'}` chỉ để tạo ra cùng một chuỗi.

`isLiteral()` giúp nhận diện biểu thức literal theo API. Đừng chỉ thấy một SpEL có vẻ đơn giản rồi giả định nó được framework tự tính sẵn một lần hoặc tự chuyển thành cache kết quả.

### 9.4. Đừng tối ưu bằng cách làm sai thời điểm

Những thay đổi như lấy tenant một lần lúc khởi tạo, giữ context request trong singleton hoặc tính tên đích trước khi context thực tế có mặt có thể làm giảm số lần chạy nhưng cũng làm sai dữ liệu.

Một tối ưu hợp lệ phải giữ nguyên hợp đồng về dữ liệu đầu vào, thời điểm cần giá trị và phạm vi sử dụng kết quả.

## 10. Đo chi phí và xác minh kết quả

### 10.1. Tách cold path và warm path

Cần phân biệt:

- Lần đầu: có thể gồm khởi tạo class, parse và chuẩn bị hạ tầng.
- Sau khi làm nóng: biểu thức có thể đã có trong cache.
- Khi cache bị thay thế nhiều khóa: hành vi có thể khác cả hai trường hợp trên.

Đo duy nhất lần gọi đầu không phản ánh toàn bộ lưu lượng ổn định. Ngược lại, chỉ đo một biểu thức lặp lại mãi có thể bỏ qua chi phí do tập biểu thức thực tế quá lớn.

### 10.2. Đếm đúng loại công việc

Các chỉ số hữu ích gồm:

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| Số lần gọi parser thật | Cache đã tránh được bao nhiêu lần parse? |
| Số lần evaluate | Điểm tích hợp thực sự cần giá trị bao nhiêu lần? |
| Số lần tạo context hoặc truy cập extension | Chi phí còn lại tập trung ở đâu? |
| Số lần gọi service trong SpEL | Có công việc lặp lại ẩn sau biểu thức không? |
| Cache hit/miss/eviction nếu cơ chế cho phép quan sát | Dung lượng có phù hợp với tập biểu thức không? |
| Phân bổ bộ nhớ và thời gian xử lý | Lợi ích CPU có đi kèm chi phí bộ nhớ không? |
| Thời gian operation và truy vấn database | Tối ưu biểu thức có cải thiện toàn đường đi không? |

Có thể dùng parser trang trí để đếm parse thật khi thiết kế phép thử, nhưng phải đặt bộ đếm ở phía sau lớp cache. Nếu chỉ đếm số lần gọi phương thức parse của wrapper cache, bạn có thể đang đếm cả cache hit.

Không đưa `System.out.println` vào vòng lặp rồi xem thời gian đó là chi phí riêng của biểu thức. Với phép đo vi mô, cần công cụ và cách làm nóng phù hợp; với repository, cần thêm phép đo trên hạ tầng store thật.

### 10.3. Kiểm tra tính đúng song song với hiệu năng

Một tập kiểm tra hữu ích cho ví dụ định tuyến gồm:

1. Cùng biểu thức, hai tenant khác nhau cho kết quả khác nhau.
2. Cùng tenant, cấu hình đã được cập nhật theo cơ chế được hỗ trợ cho kết quả mong đợi.
3. Hai lượt thực thi đồng thời không dùng lẫn biến của nhau.
4. Property bắt buộc bị thiếu vẫn báo lỗi theo hợp đồng.
5. Khi cache bị eviction, kết quả vẫn đúng dù phải parse lại.
6. Lời gọi phương thức trong biểu thức không bị giả định chỉ chạy một lần nếu framework cần đánh giá lại.

Các phép kiểm tra này chứng minh vòng đời và phạm vi dữ liệu. Một con số thời gian nhỏ hơn không thể thay thế chúng.

## 11. Bài thực hành

Bắt đầu với `OrderTargetResolver` ở mục 5:

1. Giữ một instance resolver và gọi nhiều lần với các tenant khác nhau.
2. Ghi nhận số lần constructor parse và số lần `resolve` evaluate.
3. So sánh với một biến thể tạo lại resolver cho từng lần gọi.
4. Thay property source tường minh rồi giải thích vì sao đối tượng biểu thức không cần parse lại trong ví dụ.
5. Thử một tập nhỏ biểu thức cố định và một tập lớn chuỗi khai báo khác nhau để quan sát hành vi cache có giới hạn.
6. Thêm một phương thức tính toán được biểu thức gọi, đếm số lần gọi đó và xác minh cache parse không tự loại bỏ nó.
7. Chọn một điểm tích hợp thật của store đang học, xác định thời điểm đánh giá bằng tài liệu và bằng phép quan sát thực tế.

Bài thực hành đạt yêu cầu khi bạn chỉ rõ **đối tượng được cache**, **dữ liệu của context**, **thời điểm đánh giá** và **chi phí thực sự được giảm**, đồng thời chứng minh kết quả vẫn đúng cho các lần gọi khác nhau.

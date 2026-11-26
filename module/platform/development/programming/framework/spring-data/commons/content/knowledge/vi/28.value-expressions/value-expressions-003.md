# Environment, bean và ngữ cảnh đánh giá

## 1. Một biểu thức lấy dữ liệu từ đâu?

Một biểu thức như `orders-${app.stage:local}-#{#region}` có hai nhu cầu khác nhau: lấy cấu hình `app.stage` và lấy biến `region` của lần xử lý hiện tại. Nếu biểu thức còn gọi `@routingNames.suffixFor(...)`, nó cần thêm khả năng tra cứu bean. Chuỗi biểu thức không tự mang theo những nguồn dữ liệu đó.

Trong chương **Biểu thức giá trị** của module **SPRING_DATA_COMMONS**, bài này tập trung vào cách cung cấp `Environment`, bean và ngữ cảnh đánh giá cho Value Expressions. Đây là kiến thức hạ tầng dùng chung; điểm tích hợp vào mapping, repository và truy vấn vẫn phụ thuộc module dữ liệu.

Một thiết kế đúng cần làm rõ bốn điều: biểu thức được định nghĩa ở đâu, dữ liệu của lần đánh giá đến từ đâu, context cho phép truy cập những gì và kết quả được bên gọi dùng vào việc gì. Phân biệt được bốn điều này giúp tránh lấy nhầm cấu hình, tra sai bean hoặc dùng dữ liệu của request trước cho request sau.

| Thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| `Environment` | Cung cấp property và thông tin profile | Giá trị của `app.stage` |
| SpEL `EvaluationContext` | Cung cấp root, biến, resolver và các khả năng đánh giá | `#root.tenantId`, `#region` |
| `BeanResolver` | Tra bean theo tên khi biểu thức yêu cầu | `@routingNames` |
| `ValueEvaluationContext` | Kết hợp Environment với SpEL context | Một ngữ cảnh hoàn chỉnh cho Value Expression |
| Context provider | Tạo hoặc cung cấp ngữ cảnh theo đầu vào | Root và biến của lần gọi repository |

## 2. Phân biệt placeholder, SpEL và biểu thức ghép

### 2.1. Placeholder dùng Environment

`${app.stage}` yêu cầu tìm property `app.stage`. `${app.stage:local}` có giá trị mặc định `local` khi property không được giải quyết theo hợp đồng placeholder đang dùng.

Tên property không phải tên biến SpEL. Khai báo biến `stage` bằng `setVariable` không làm `${stage}` lấy giá trị của biến đó. Ngược lại, thêm property `app.stage` vào Environment không tự tạo biến `#stage`.

### 2.2. SpEL dùng ngữ cảnh đánh giá

`#{#region}` lấy biến `region`; `#{#root.tenantId}` đọc property của root; `#{@routingNames.suffixFor('tenant-a')}` yêu cầu tra bean rồi gọi phương thức.

Value Expressions cho phép dùng từng dạng riêng hoặc ghép với phần chữ cố định. Khi triển khai, chỉ nên đánh giá biểu thức do nguồn tin cậy định nghĩa, chẳng hạn annotation hoặc mã ứng dụng. [Spring Data Commons: Value Expressions Fundamentals](https://docs.spring.io/spring-data/commons/reference/value-expressions.html).

| Chuỗi đầu vào | Nguồn dữ liệu cần có |
| --- | --- |
| `orders` | Không cần dữ liệu động |
| `${app.stage:local}` | Environment |
| `#{#region}` | Biến đã được đặt trong SpEL context |
| `#{#root.tenantId}` | Root có property tương ứng |
| `#{@routingNames.suffixFor(#root.tenantId)}` | Root, bean resolver và bean có tên đúng |
| `orders-${app.stage:local}-#{#region}` | Cả Environment lẫn SpEL context |

Cú pháp `#{...}` ở đây là phần bao của Value Expression. Nếu sử dụng trực tiếp `SpelExpressionParser.parseExpression(...)` theo chế độ biểu thức thông thường, cách truyền chuỗi khác với API Value Expression. Không thay parser mà mặc nhiên giữ nguyên mọi quy ước template.

## 3. Environment và thứ tự PropertySource

### 3.1. Một Environment có nhiều nguồn property

`Environment` không đồng nghĩa với một tệp cấu hình cụ thể. Giá trị có thể đến từ property source được ứng dụng thêm vào, JVM system properties hoặc environment variables của tiến trình.

`StandardEnvironment` mặc định tra system properties trước system environment. Các nguồn có thể được thêm, bỏ hoặc sắp xếp lại thông qua property sources. [API StandardEnvironment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/StandardEnvironment.html).

```java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

var environment = new StandardEnvironment();
Map<String, Object> settings = Map.of(
        "app.stage", "demo",
        "app.prefix", "orders");

environment.getPropertySources().addFirst(
        new MapPropertySource("lesson-settings", settings));

System.out.println(environment.getProperty("app.stage")); // demo
```

`addFirst` đặt nguồn của ví dụ ở đầu danh sách. Đây là quyết định chủ động của ví dụ; trong ứng dụng thực, hãy kiểm tra thứ tự nguồn cấu hình hiện có trước khi thêm một nguồn có khả năng ghi đè.

Tự tạo `new StandardEnvironment()` không tự đọc `application.yml` của Spring Boot. Boot có quy trình nạp cấu hình riêng. Khi tích hợp vào ứng dụng đã có container, thường cần dùng chính Environment của application context thay vì tạo một Environment mới rồi mong có cùng cấu hình.

### 3.2. Giá trị thiếu và giá trị rỗng

`PropertyResolver` phân biệt `getProperty`, `getRequiredProperty`, `resolvePlaceholders` và `resolveRequiredPlaceholders`. Biến thể bắt buộc yêu cầu giải quyết được giá trị tương ứng, trong khi phương thức đọc thông thường có thể trả `null` khi không tìm thấy. [API PropertyResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertyResolver.html).

Trong implementation placeholder của Spring Data được dẫn dưới đây, quá trình đánh giá sử dụng `Environment.resolveRequiredPlaceholders` và chuyển lỗi giải quyết placeholder thành lỗi đánh giá. Vì vậy, không nên kỳ vọng một placeholder bắt buộc bị thiếu sẽ luôn được giữ nguyên như văn bản. [Mã nguồn PlaceholderExpression](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/expression/PlaceholderExpression.java).

Có giá trị mặc định không thay thế việc kiểm tra dữ liệu. Một property tồn tại với chuỗi rỗng hoặc nội dung không hợp lệ cần được xử lý theo hợp đồng của ứng dụng. Ví dụ, tên collection rỗng vẫn không dùng được chỉ vì `${data.collection:orders}` có một fallback.

### 3.3. Environment không phải nơi giữ trạng thái request

Property `app.stage` phù hợp với cấu hình triển khai. Tenant đang đăng nhập, người dùng hiện tại hoặc mã giao dịch phù hợp hơn với dữ liệu của lần gọi.

Không đổi property chung trong Environment trước mỗi request để làm `${tenant.id}` trả về tenant hiện hành. Hai request đồng thời có thể quan sát cùng nguồn cấu hình đang bị thay đổi. Hãy truyền dữ liệu theo root, biến hoặc provider có vòng đời thích hợp.

## 4. Root object, biến và bean là ba đường truy cập khác nhau

### 4.1. Root object

`StandardEvaluationContext` có thể nhận một đối tượng gốc. Các property hoặc lời gọi phương thức không chỉ rõ đối tượng có thể được giải quyết dựa trên root. `#root` giúp biểu thức thể hiện rõ nguồn dữ liệu. [API StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html).

Ví dụ root có getter `getTenantId()`:

```text
#{#root.tenantId}
```

Nếu root là mảng đối số repository, ý nghĩa của root khác với root là đối tượng request. Không coi `#root` luôn là entity hoặc luôn là người dùng đăng nhập.

### 4.2. Biến đặt tên

```java
spelContext.setVariable("region", "apac");
```

Biến được tham chiếu bằng `#region`. Khi biến cùng tên với property trên root, `#region` vẫn thể hiện yêu cầu đọc biến, còn `#root.region` thể hiện yêu cầu đọc property của root.

Đặt tên rõ mục đích giúp tránh nhầm lẫn. Trong một luồng có nhiều context extension, cũng cần tránh công bố các property hoặc function có tên quá chung làm hợp đồng biểu thức khó theo dõi.

### 4.3. Bean reference

Cú pháp SpEL `@beanName` yêu cầu context có bean resolver. Một bean tồn tại trong Spring container không tự làm mọi `StandardEvaluationContext` được tạo thủ công tìm thấy bean ấy. [Spring Framework: Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html).

```java
spelContext.setBeanResolver(new BeanFactoryResolver(applicationContext));
```

`BeanFactoryResolver` thực hiện tra cứu dựa trên `BeanFactory` được truyền vào. [API BeanFactoryResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/expression/BeanFactoryResolver.html).

Với bean tên `routingNames`, biểu thức của ví dụ là:

```text
#{@routingNames.suffixFor(#root.tenantId)}
```

`@routingNames` không phải `#routingNames`. Dạng thứ hai là biến và chỉ hoạt động theo nghĩa đó khi biến đã được cung cấp. Một context tích hợp có thể thêm property accessor hoặc extension để giải quyết tên theo cách khác, nhưng không nên suy rộng hành vi ấy sang context tự tạo.

## 5. Ví dụ hoàn chỉnh: ghép Environment, root, biến và bean

Ví dụ dùng Java 17, Spring Context, Spring Expression và Spring Data Commons có API `ValueExpressionParser.create()`; overload không tham số này có từ Commons 3.4. Đây là chương trình đánh giá trong bộ nhớ, không cần kết nối database.

```java
import java.util.Map;
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;
import org.springframework.data.expression.ValueEvaluationContext;
import org.springframework.data.expression.ValueExpression;
import org.springframework.data.expression.ValueExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public class ValueExpressionContextDemo {

    public static final class RequestRoot {
        private final String tenantId;

        public RequestRoot(String tenantId) {
            this.tenantId = tenantId;
        }

        public String getTenantId() {
            return tenantId;
        }
    }

    public static final class RoutingNames {
        public String suffixFor(String tenantId) {
            return switch (tenantId) {
                case "tenant-a" -> "east";
                case "tenant-b" -> "west";
                default -> throw new IllegalArgumentException(
                        "Tenant chưa được cấu hình");
            };
        }
    }

    public static void main(String[] args) {
        var environment = new StandardEnvironment();
        Map<String, Object> settings = Map.of(
                "app.prefix", "orders",
                "app.stage", "demo");

        environment.getPropertySources().addFirst(
                new MapPropertySource("lesson-settings", settings));

        try (var applicationContext = new GenericApplicationContext()) {
            applicationContext.setEnvironment(environment);
            applicationContext.registerBean("routingNames", RoutingNames.class);
            applicationContext.refresh();

            var root = new RequestRoot("tenant-a");
            var spelContext = new StandardEvaluationContext(root);
            spelContext.setVariable("region", "apac");
            spelContext.setBeanResolver(
                    new BeanFactoryResolver(applicationContext));

            ValueEvaluationContext context = ValueEvaluationContext.of(
                    applicationContext.getEnvironment(), spelContext);

            ValueExpressionParser parser = ValueExpressionParser.create();
            ValueExpression expression = parser.parse(
                    "${app.prefix}-"
                    + "#{@routingNames.suffixFor(#root.tenantId)}-"
                    + "#{#region}");

            System.out.println(expression.evaluate(context));
            // orders-east-apac

            System.out.println(parser.parse("${app.stage:local}")
                    .evaluate(context));
            // demo

            System.out.println(parser.parse("${lesson.missing:default}")
                    .evaluate(context));
            // default

            System.out.println(parser.parse("#{#root.tenantId}")
                    .evaluate(context));
            // tenant-a
        }
    }
}
```

Chuỗi kết quả được hình thành từ ba nguồn có thể chỉ ra riêng: Environment cung cấp `orders`, bean trả về `east` sau khi nhận tenant từ root, còn biến `region` cung cấp `apac`.

`ValueEvaluationContext.of(environment, evaluationContext)` ghép hai thành phần context; API không nói rằng nó tự quét application context hay tự thêm bean resolver. [API ValueEvaluationContext](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/expression/ValueEvaluationContext.html).

`ValueExpressionParser` tạo đối tượng biểu thức đã phân tích để đánh giá lại về sau. [API ValueExpressionParser](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/expression/ValueExpressionParser.html).

Nếu bỏ cấu hình bean resolver khỏi ví dụ, phần placeholder vẫn có nguồn dữ liệu nhưng bean reference mất cơ chế tra cứu. Nếu bỏ biến `region`, root vẫn tồn tại nhưng điều đó không tạo ra giá trị cho `#region`. Mỗi nguồn có hợp đồng độc lập.

## 6. Truy cập Environment bên trong SpEL phải được cung cấp rõ

Việc Environment có trong `ValueEvaluationContext` phục vụ giải quyết placeholder. Nó không đồng nghĩa một context SpEL tự tạo đã có biến `#environment`.

Nếu cần biểu thức SpEL gọi Environment, có thể đưa nó thành biến một cách rõ ràng:

```java
spelContext.setVariable("environment", environment);

Object stage = parser.parse(
        "#{#environment.getProperty('app.stage', 'local')}")
        .evaluate(context);
```

Đoạn trên giả định các biến `spelContext`, `environment`, `parser` và `context` đang có trong cùng phạm vi như ví dụ trước. `#environment` hoạt động vì có lệnh `setVariable`.

Dạng `#{@environment.getProperty('app.stage')}` lại yêu cầu bean resolver và bean tên `environment`. Dạng `#{environment.getProperty('app.stage')}` không có `#` hoặc `@` cần được giải quyết theo root, property accessor hay extension do context cung cấp.

Không đổi qua lại giữa ba dạng chỉ vì tên nhìn giống nhau. Khi một đoạn biểu thức chạy trong annotation nhưng thất bại khi gọi API thủ công, hãy so sánh context và resolver trước khi sửa nội dung biểu thức.

Cũng không nên tự xây dựng chuỗi SpEL bằng cách chèn trực tiếp giá trị property hoặc dữ liệu request vào mã biểu thức. Nếu giá trị chỉ là dữ liệu, truyền qua biến hoặc root để giữ rõ ranh giới giữa dữ liệu và cú pháp.

## 7. Context provider: cung cấp ngữ cảnh cho từng lần gọi

### 7.1. Context là dữ liệu và khả năng; provider là cách lấy context

`ValueEvaluationContextProvider` cung cấp `ValueEvaluationContext` theo root object. API còn có overload nhận expression dependencies để provider có thể tạo context phù hợp với nhu cầu biểu thức. [API ValueEvaluationContextProvider](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/expression/ValueEvaluationContextProvider.html).

Một provider thủ công có thể tạo SpEL context mới cho mỗi root:

```java
import org.springframework.context.expression.BeanFactoryResolver;
import org.springframework.data.expression.ValueEvaluationContext;
import org.springframework.data.expression.ValueEvaluationContextProvider;
import org.springframework.expression.spel.support.StandardEvaluationContext;

ValueEvaluationContextProvider provider = rootObject -> {
    var evaluationContext = new StandardEvaluationContext(rootObject);
    evaluationContext.setVariable("region", "apac");
    evaluationContext.setBeanResolver(
            new BeanFactoryResolver(applicationContext));

    return ValueEvaluationContext.of(
            applicationContext.getEnvironment(), evaluationContext);
};

Object first = expression.evaluate(provider.getEvaluationContext(
        new ValueExpressionContextDemo.RequestRoot("tenant-a")));
Object second = expression.evaluate(provider.getEvaluationContext(
        new ValueExpressionContextDemo.RequestRoot("tenant-b")));

System.out.println(first);  // orders-east-apac
System.out.println(second); // orders-west-apac
```

Đoạn này đặt trong phạm vi application context và expression của ví dụ trước, trước khi context bị đóng. Hai lần đánh giá dùng cùng biểu thức đã parse nhưng có root và SpEL context riêng. Bean `RoutingNames` không giữ tenant trong field thay đổi nên có thể xử lý các đầu vào khác nhau mà không cần sửa trạng thái dùng chung.

Một provider không mặc nhiên tạo mới mọi thứ; đó là lựa chọn của implementation. Khi thiết kế provider riêng, cần xác định phần nào là cấu hình dùng chung và phần nào thuộc lần gọi.

### 7.2. Context của query method có thêm metadata của phương thức

`QueryMethodValueEvaluationContextAccessor` là factory tạo value evaluation context provider cho các tham số của query method; nó có các cách khởi tạo từ application context hoặc từ Environment cùng hạ tầng context tương ứng. [API QueryMethodValueEvaluationContextAccessor](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/query/QueryMethodValueEvaluationContextAccessor.html).

Vì repository có metadata tham số và cơ chế binding riêng, không thay context query method bằng một `StandardEvaluationContext` trống rồi mong có cùng biến hoặc helper.

Tương tự, tên biến tham số, cú pháp truy cập đối số theo chỉ số và các function hỗ trợ không phải bộ tên toàn cục có trong mọi context. Khi dùng trong repository, hãy dựa vào tài liệu của module và cấu hình query method thực tế.

## 8. Context extension: công bố thêm dữ liệu theo hợp đồng

### 8.1. Thêm property qua EvaluationContextExtension

`EvaluationContextExtension` cho phép bổ sung property, function và root object cho context được hạ tầng extension-aware cung cấp. [API EvaluationContextExtension](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/spel/spi/EvaluationContextExtension.html).

Ví dụ dưới đây chỉ công bố một property có tên riêng để dễ quan sát:

```java
import java.util.Map;
import java.util.Objects;
import org.springframework.data.spel.spi.EvaluationContextExtension;

public final class TenantExtension implements EvaluationContextExtension {
    private final String tenantId;

    public TenantExtension(String tenantId) {
        this.tenantId = Objects.requireNonNull(tenantId);
    }

    @Override
    public String getExtensionId() {
        return "tenant";
    }

    @Override
    public Map<String, Object> getProperties() {
        return Map.of("currentTenantId", tenantId);
    }
}
```

Dùng extension với provider phù hợp:

```java
import java.util.List;
import org.springframework.data.expression.ValueEvaluationContext;
import org.springframework.data.expression.ValueExpressionParser;
import org.springframework.data.spel.ExtensionAwareEvaluationContextProvider;

var extensions = new ExtensionAwareEvaluationContextProvider(
        List.of(new TenantExtension("tenant-a")));

var spelContext = extensions.getEvaluationContext(new Object());
var context = ValueEvaluationContext.of(environment, spelContext);
var expression = ValueExpressionParser.create().parse("#{currentTenantId}");

System.out.println(expression.evaluate(context)); // tenant-a
```

`ExtensionAwareEvaluationContextProvider` lắp context từ các extension được truyền vào, hoặc tra các extension từ bean factory khi sử dụng constructor tương ứng. [API ExtensionAwareEvaluationContextProvider](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/spel/ExtensionAwareEvaluationContextProvider.html).

Đây là ví dụ tạo extension với dữ liệu cố định cho một lần minh họa. Trong ứng dụng nhiều tenant, không khởi tạo một singleton từ tenant của request đầu tiên rồi dùng mãi. Nguồn tenant cần gắn đúng lần xử lý, và quyền truy cập tenant vẫn phải được xác thực bởi ứng dụng.

Nếu mở rộng bằng `getRootObject()`, nên khai báo kiểu trả về cụ thể để hạ tầng có thông tin rõ về những thành phần được công bố. Không đưa toàn bộ application service vào root chỉ vì thuận tiện gọi nhiều phương thức.

### 8.2. Ngữ cảnh reactive cần đường cung cấp dữ liệu phù hợp

Commons có `ReactiveEvaluationContextExtension` để giải quyết extension qua `Mono` trong luồng thực thi tương ứng. [API ReactiveEvaluationContextExtension](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/spel/spi/ReactiveEvaluationContextExtension.html).

Một request reactive có thể chuyển thread; không suy ra tenant từ một ThreadLocal theo cùng giả định của luồng đồng bộ. Cần chọn provider và cách truyền ngữ cảnh phù hợp với module reactive, thay vì gọi chặn trong biểu thức để lấy dữ liệu còn thiếu.

## 9. Phân biệt parse, evaluate, kiểu kết quả và cache

### 9.1. Parse thành công chưa chứng minh đánh giá thành công

Parse kiểm tra và tạo biểu diễn của chuỗi biểu thức. Đến lúc evaluate mới cần các dữ liệu như property, root, biến và bean thực tế. Một biểu thức đúng cú pháp vẫn có thể thất bại vì không tìm thấy bean, gọi sai phương thức hoặc nhận root không có property cần thiết.

SpEL phân biệt lỗi parse và lỗi đánh giá; các khả năng truy cập phụ thuộc evaluation context. [Spring Framework: Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html).

### 9.2. Không giả định mọi kết quả đều là String

`ValueExpression.evaluate(...)` trả `Object` và kết quả có thể là `null`. [API ValueExpression](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/expression/ValueExpression.html).

```text
#{2 + 3}               -> giá trị số 5
${lesson.limit:20}     -> chuỗi "20" từ placeholder
limit-#{2 + 3}         -> chuỗi "limit-5"
```

Nếu bên nhận yêu cầu số nguyên, hãy quy định và thực hiện chuyển đổi kiểu ở ranh giới phù hợp. Đừng ép `(Integer)` kết quả một placeholder chỉ vì nội dung của nó trông giống số.

Với dữ liệu bắt buộc như tenant, không tự coi một kết quả null là quyền đọc toàn bộ tenant. Bên gọi phải kiểm tra giá trị và từ chối luồng xử lý không có ngữ cảnh hợp lệ theo chính sách ứng dụng.

### 9.3. Tái sử dụng biểu thức khác với giữ kết quả đánh giá

Có thể tránh parse lặp bằng cách lưu biểu thức đã phân tích. Tuy nhiên, kết quả `orders-east-apac` phụ thuộc root và biến hiện tại. Lưu kết quả lần đầu dưới một khóa chỉ gồm chuỗi biểu thức có thể làm request sau nhận kết quả của tenant trước.

Nguyên tắc thực hành là tái sử dụng biểu thức trong cùng mô hình cấu hình đánh giá, cung cấp dữ liệu đúng cho mỗi lần evaluate, và chỉ cache kết quả nếu đã chứng minh đầy đủ các đầu vào ảnh hưởng đến nó.

Cũng không dùng chung một SpEL context mutable rồi liên tục sửa root hoặc biến giữa các request đồng thời. Một wrapper context không biến trạng thái của root hoặc bean thành bất biến.

Bean được gọi từ biểu thức nên có hành vi dễ dự đoán. Nếu phương thức bean thực hiện I/O hoặc thay đổi dữ liệu, mỗi lần đánh giá có thể tạo thêm chi phí hoặc tác dụng phụ. Không giả định một biểu thức trong annotation chỉ được gọi đúng một lần trong suốt vòng đời ứng dụng.

## 10. Áp dụng vào module dữ liệu và giữ đúng ranh giới

Value Expressions xuất hiện trong mapping annotations của các module có hỗ trợ và trong repository query methods. Khả năng hỗ trợ mapping expression khác với khả năng hỗ trợ biểu thức trong query; đặc biệt không suy từ ví dụ MongoDB sang mapping do JPA provider quản lý.

Với query methods, phần đánh dấu tham số có thể mang dạng `:#{...}`, `?#{...}`, `:${...}` hoặc `?${...}` tùy module. Khi gọi trực tiếp `ValueExpressionParser`, chỉ dùng cú pháp Value Expression; các dấu đánh dấu binding của query thuộc lớp tích hợp truy vấn.

Một property Environment là cấu hình ứng dụng, không tự trở thành property entity. Tương tự, tính được tên collection không chứng minh index, quyền truy cập hoặc cấu trúc dữ liệu của collection đó đã sẵn sàng.

Trong phạm vi module Commons, cần giữ rõ các ranh giới sau:

- Derived query dựa trên tên phương thức không trở thành nơi thực thi chuỗi biểu thức tùy ý chỉ vì ứng dụng có parser.
- QBE dùng probe và matcher theo khả năng module; không tự đánh giá mọi chuỗi trong probe như SpEL.
- Projection và auditing có hạ tầng ngữ cảnh riêng; context tự tạo trong bài không tự thay thế chúng.
- Phân trang, sort và binding tham số vẫn phải tuân theo khả năng store, kể cả khi một giá trị được tính bằng biểu thức.

Nếu biểu thức góp phần xác định tenant hoặc đích dữ liệu, ứng dụng phải kiểm tra tenant và đích đó nằm trong phạm vi được phép. Một chuỗi hợp lệ về cú pháp không tự bảo đảm quyền truy cập.

## 11. Chẩn đoán theo nguồn dữ liệu bị thiếu

| Hiện tượng | Điểm cần kiểm tra trước |
| --- | --- |
| Placeholder không giải quyết được | Đúng Environment chưa, property source có khóa không, có fallback hợp lệ không |
| Property có giá trị khác mong đợi | Thứ tự property sources và Environment thực tế của application context |
| Không tìm thấy `@routingNames` | Bean resolver, tên bean, bean factory đang được sử dụng |
| `#region` không có giá trị | Biến có được đặt trong đúng context của lần evaluate không |
| Không đọc được `#root.tenantId` | Kiểu root, getter và root của đường thực thi hiện tại |
| Chạy trong annotation nhưng không chạy thủ công | So sánh resolver, property accessor, extension và biến được cung cấp |
| Tenant sau nhận đích dữ liệu của tenant trước | Cache kết quả, root hoặc biến dùng chung, bean giữ trạng thái request |
| Kết quả nhìn giống số nhưng ép kiểu lỗi | Kiểu thực tế của kết quả và cách chuyển đổi ở bên nhận |
| Parse thành công nhưng evaluate lỗi | Dữ liệu, bean và phương thức chỉ được giải quyết khi đánh giá |

Khi ghi log để chẩn đoán, ưu tiên tên property, tên bean, loại root, vị trí biểu thức và loại lỗi. Không ghi toàn bộ Environment hoặc kết quả chứa bí mật chỉ để tìm một khóa cấu hình thiếu.

## 12. Thực hành quan sát ngữ cảnh

Trong chương trình demo, thực hiện lần lượt các tình huống sau:

1. Đánh giá biểu thức ghép và chỉ ra phần nào do Environment, root, bean và biến cung cấp.
2. Thay property source của ví dụ, sau đó so sánh giá trị `environment.getProperty(...)` với kết quả placeholder.
3. Dùng một khóa thiếu có fallback rồi một khóa thiếu bắt buộc. Phân biệt dữ liệu thiếu với property có chuỗi rỗng.
4. Bỏ bean resolver để quan sát lỗi của bean reference; giữ nguyên Environment để thấy placeholder có hợp đồng riêng.
5. Đổi root từ `tenant-a` sang `tenant-b` thông qua hai context riêng. Giải thích vì sao một biểu thức đã parse có thể cho hai kết quả.
6. Đặt biến tên `environment` rồi so sánh `#environment`, `@environment` và tên không có tiền tố trong đúng context của ví dụ.
7. Thêm `TenantExtension`, sau đó tạo context không có extension ấy. Xác định tên `currentTenantId` được công bố từ đâu.
8. So sánh kiểu kết quả của biểu thức số, placeholder số dạng chuỗi và biểu thức ghép có literal.
9. Trong ứng dụng repository đã chọn module, đối chiếu context thực tế với context thủ công trước khi dùng cùng một biểu thức trong query hoặc mapping annotation.

Khi giải thích kết quả, luôn nêu được Environment nào đang được dùng, root thuộc kiểu gì, biến nào đã được đặt, bean resolver tra ở container nào và provider tạo ngữ cảnh ở thời điểm nào. Những thông tin này quyết định ý nghĩa thực tế của Value Expression.

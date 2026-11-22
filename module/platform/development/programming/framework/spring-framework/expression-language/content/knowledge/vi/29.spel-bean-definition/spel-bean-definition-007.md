# Vòng phụ thuộc khi expression tham chiếu bean khác

Spring Expression Language (SpEL) cho phép một biểu thức tham chiếu bean Spring bằng cú pháp **@beanName**. Khả năng này hữu ích khi cấu hình bean cần lấy một giá trị hoặc gọi một method từ bean khác. Tuy nhiên, nếu biểu thức được đánh giá trong lúc Spring đang tạo bean, việc tham chiếu đó có thể kích hoạt quá trình khởi tạo bean khác và tạo ra vòng phụ thuộc.

Vòng phụ thuộc thường khó phát hiện hơn khi dependency bị ẩn trong chuỗi SpEL. Nhìn vào constructor hoặc field injection của một class, ta có thể không thấy bean nào đang phụ thuộc vào bean nào. Chỉ khi biểu thức được đánh giá, Spring mới tra cứu bean và có thể gặp một bean đang trong quá trình tạo.

Nguyên tắc quan trọng: **không dùng bean reference trong SpEL để tạo dependency vòng hoặc che giấu dependency giữa các bean**. Hãy khai báo dependency rõ ràng, tách phần dùng chung hoặc trì hoãn việc tra cứu tới đúng thời điểm runtime khi điều đó thực sự cần thiết.

## 1. Bean reference trong SpEL

### 1.1. Cú pháp @beanName

SpEL dùng ký hiệu @ để tham chiếu bean theo tên:

~~~java
@currencyRules.defaultCurrency
@pricingService.calculate(order)
~~~

Biểu thức cần một EvaluationContext có BeanResolver. Trong ngữ cảnh Spring, BeanFactoryResolver có thể phân giải tên bean thông qua BeanFactory hoặc ApplicationContext.

Ví dụ trong cấu hình:

~~~java
@Value("#{currencyRules.defaultCurrency}")
private String currency;
~~~

Spring đánh giá biểu thức và lấy property defaultCurrency từ bean currencyRules để gán vào field currency.

### 1.2. Bean reference không chỉ là đọc một giá trị

Khi resolver xử lý @currencyRules, nó phải tìm bean tương ứng. Nếu bean chưa được tạo, việc tra cứu có thể khiến Spring bắt đầu khởi tạo bean đó.

Vì vậy, biểu thức:

~~~java
@Value("#{currencyRules.defaultCurrency}")
private String currency;
~~~

có thể tạo ra quan hệ phụ thuộc trong quá trình khởi tạo:

1. Spring đang tạo bean chứa field currency.
2. Spring đánh giá biểu thức @Value.
3. BeanResolver tra cứu currencyRules.
4. Nếu currencyRules chưa được tạo, Spring bắt đầu tạo bean này.
5. Nếu quá trình tạo currencyRules lại cần bean ban đầu, vòng phụ thuộc xuất hiện.

Đây là lý do một biểu thức ngắn có thể ảnh hưởng tới thứ tự khởi tạo và trạng thái của toàn bộ ApplicationContext.

### 1.3. Thời điểm đánh giá rất quan trọng

SpEL expression có thể được parse và evaluate ở các thời điểm khác nhau:

- Trong lúc xử lý bean definition hoặc tạo bean, ví dụ biểu thức trong XML hoặc annotation @Value.
- Trong lúc một bean đang được populate property hoặc inject dependency.
- Khi ứng dụng tự parse và đánh giá Expression tại runtime.
- Khi một method gọi logic đánh giá expression trong một luồng nghiệp vụ.

Một biểu thức được đánh giá sau khi ApplicationContext đã khởi tạo xong có thể không gây vòng khởi tạo lúc startup. Nhưng nếu biểu thức được đánh giá trong constructor, field initializer, @PostConstruct hoặc quá trình tạo bean, nó vẫn có thể kích hoạt một chuỗi khởi tạo vòng.

Không chỉ nhìn vào cú pháp; hãy xác định chính xác biểu thức được evaluate ở giai đoạn nào.

## 2. Vòng phụ thuộc hình thành như thế nào?

### 2.1. Ví dụ hai bean phụ thuộc lẫn nhau qua SpEL

Giả sử có hai bean:

~~~java
@Component
public class PricingPolicy {

    @Value("#{currencyRules.defaultCurrency}")
    private String currency;

    public String getCurrency() {
        return currency;
    }
}
~~~

~~~java
@Component
public class CurrencyRules {

    @Value("#{pricingPolicy.currency}")
    private String defaultCurrency;

    public String getDefaultCurrency() {
        return defaultCurrency;
    }
}
~~~

Quan hệ phụ thuộc:

~~~text
PricingPolicy -> CurrencyRules
CurrencyRules -> PricingPolicy
~~~

Tạo PricingPolicy cần đọc currencyRules.defaultCurrency. Tạo CurrencyRules lại cần đọc pricingPolicy.currency. Spring bắt đầu tạo một bean, đánh giá biểu thức để lấy bean còn lại, rồi bean còn lại lại cần bean đầu tiên. Tùy thời điểm và cấu hình, quá trình có thể kết thúc bằng lỗi bean đang được tạo.

Ví dụ này chỉ minh họa cấu trúc vòng phụ thuộc. Không nên dùng hai bean như vậy trong ứng dụng thực tế.

### 2.2. Vòng phụ thuộc trực tiếp và vòng phụ thuộc ẩn

Vòng phụ thuộc trực tiếp thường dễ nhận ra:

~~~java
@Component
public class ServiceA {

    public ServiceA(ServiceB serviceB) {
    }
}
~~~

~~~java
@Component
public class ServiceB {

    public ServiceB(ServiceA serviceA) {
    }
}
~~~

Vòng phụ thuộc ẩn có thể nằm trong biểu thức:

~~~java
@Value("#{serviceB.someValue}")
private String value;
~~~

Class có thể không khai báo ServiceB trong constructor hoặc field, nhưng SpEL vẫn yêu cầu Spring tra cứu ServiceB khi evaluate.

Dependency ẩn khó phát hiện hơn vì:

- Không xuất hiện rõ trong constructor signature.
- Công cụ đọc dependency graph có thể không thể hiện đầy đủ quan hệ phát sinh từ chuỗi expression.
- Việc khởi tạo bean phụ thuộc vào thời điểm evaluate.
- Thay đổi một biểu thức cấu hình có thể làm xuất hiện vòng mới mà không sửa code Java của bean.
- Lỗi có thể chỉ xuất hiện ở một profile hoặc một cấu hình môi trường.

Hãy coi mọi bean reference trong expression được đánh giá lúc startup là một dependency cần được xem xét trong thiết kế.

### 2.3. Vòng phụ thuộc qua nhiều bean

Vòng không nhất thiết chỉ gồm hai bean:

~~~text
OrderService
    -> PricingPolicy
    -> CurrencyRules
    -> ApplicationSettings
    -> OrderService
~~~

Một bean có thể tham chiếu bean thứ hai bằng SpEL; bean thứ hai lại inject bean thứ ba; bean thứ ba dùng @Value tham chiếu bean thứ tư; cuối cùng bean thứ tư lại cần bean đầu tiên.

Khi điều tra, hãy lần theo toàn bộ chuỗi bean đang tạo thay vì chỉ xem bean xuất hiện đầu tiên trong exception.

## 3. Vì sao vòng phụ thuộc gây lỗi?

### 3.1. Bean đang trong quá trình tạo

Spring quản lý vòng đời bean và theo dõi những singleton đang được tạo. Nếu một bean cần chính nó trực tiếp hoặc gián tiếp trước khi quá trình tạo hoàn tất, container có thể phát hiện trạng thái bean đang được tạo và ném lỗi.

Một exception thường gặp là:

~~~text
BeanCurrentlyInCreationException
~~~

Exception này có thể được bọc trong BeanCreationException hoặc một lỗi khởi tạo ApplicationContext khác. Cần xem chuỗi cause để xác định bean nào yêu cầu bean nào tại thời điểm lỗi xảy ra.

### 3.2. Constructor cycle

Vòng phụ thuộc qua constructor thường không thể giải quyết bằng cách tạo một instance chưa hoàn chỉnh:

~~~java
@Component
public class ServiceA {

    public ServiceA(ServiceB serviceB) {
    }
}
~~~

~~~java
@Component
public class ServiceB {

    public ServiceB(ServiceA serviceA) {
    }
}
~~~

Để tạo ServiceA, Spring cần ServiceB hoàn chỉnh. Để tạo ServiceB, Spring lại cần ServiceA hoàn chỉnh. Không có instance nào có thể được tạo trước để phá vòng.

Nếu SpEL tham chiếu bean trong lúc constructor hoặc dependency của bean đang được xử lý, nó cũng có thể dẫn tới một chuỗi phụ thuộc tương tự.

### 3.3. Setter/property cycle và early references

Một số vòng phụ thuộc giữa singleton bean dùng setter hoặc field injection có thể được Spring giải quyết trong một số cấu hình bằng cơ chế early singleton reference. Cơ chế này cho phép một bean được tham chiếu trước khi quá trình khởi tạo hoàn tất.

Tuy nhiên, khả năng này có giới hạn:

- Không giải quyết được constructor cycle.
- Không phải mọi kiểu proxy hoặc bean post-processor đều tương thích với early reference.
- Không áp dụng như một cách giải quyết chung cho mọi scope.
- Không bảo đảm bean được dùng ở trạng thái đã khởi tạo đầy đủ.
- Có thể làm thứ tự khởi tạo và lỗi runtime khó hiểu hơn.

Không nên thiết kế ứng dụng dựa vào việc Spring tình cờ giải quyết được vòng setter injection. Nếu có vòng, hãy xem lại trách nhiệm và quan hệ giữa các bean.

### 3.4. Prototype và các scope khác

Cơ chế xử lý circular reference của singleton không thể được suy rộng cho prototype hoặc mọi scope khác. Prototype bean được tạo theo yêu cầu và container không quản lý một cache singleton để cung cấp early reference theo cùng cách.

Nếu prototype A và prototype B cần nhau trong quá trình tạo, vòng phụ thuộc vẫn có thể thất bại. Với request, session hoặc custom scope, hành vi còn phụ thuộc scope và proxy được cấu hình.

Hãy kiểm tra scope thực tế của từng bean khi điều tra lỗi.

## 4. Tại sao SpEL làm dependency khó nhận biết?

### 4.1. Dependency nằm trong chuỗi

So sánh hai cách:

~~~java
public PricingPolicy(CurrencyRules currencyRules) {
    this.currencyRules = currencyRules;
}
~~~

và:

~~~java
@Value("#{currencyRules.defaultCurrency}")
private String currency;
~~~

Cách thứ nhất thể hiện rõ dependency trong constructor. Cách thứ hai đặt tên bean trong chuỗi expression; người đọc phải biết cơ chế SpEL và thời điểm @Value được đánh giá mới thấy được quan hệ.

Dependency khai báo tường minh thường dễ:

- Đọc và review.
- Tạo dependency graph.
- Viết unit test.
- Phát hiện vòng phụ thuộc.
- Refactor mà không bỏ sót chuỗi bean reference.

### 4.2. Property expression có thể kích hoạt khởi tạo bean

Một expression chỉ đọc property có thể trông vô hại:

~~~java
@Value("#{appSettings.defaultLocale}")
private Locale locale;
~~~

Nhưng nếu appSettings là một bean chưa được tạo, việc tra cứu bean vẫn có thể kích hoạt khởi tạo. Nếu appSettings phụ thuộc bean hiện tại, vòng xuất hiện dù expression không gọi method có tác dụng phụ.

### 4.3. Method expression làm chuỗi phụ thuộc phức tạp hơn

Ví dụ:

~~~java
@Value("#{pricingService.defaultPriceList()}")
private PriceList priceList;
~~~

Ngoài việc tra cứu pricingService, expression còn gọi method. Method có thể đọc repository, gọi service khác hoặc yêu cầu thêm bean thông qua logic nội bộ.

Một chuỗi gọi method dài trong @Value làm cho quá trình tạo bean khó dự đoán. Hãy tránh dùng SpEL để thực hiện orchestration hoặc truy cập nhiều service trong lúc khởi tạo.

### 4.4. Không nhầm với placeholder cấu hình

Property placeholder:

~~~java
@Value("$" + "{app.currency:VND}")
private String currency;
~~~

khác với bean reference:

~~~java
@Value("#{currencyRules.defaultCurrency}")
private String currency;
~~~

Placeholder lấy giá trị từ Environment hoặc property source. Bean reference yêu cầu BeanResolver tra cứu bean trong container.

Nếu chỉ cần một giá trị cấu hình như currency, endpoint hoặc giới hạn, ưu tiên cấu hình qua application properties, environment variable hoặc @ConfigurationProperties thay vì tạo một bean chỉ để biểu thức đọc giá trị của nó.

## 5. Cách phát hiện vòng phụ thuộc

### 5.1. Đọc exception đầy đủ

Khi ApplicationContext không khởi động, hãy xem:

- BeanCreationException ở lớp ngoài.
- BeanCurrentlyInCreationException nếu có.
- Tên bean đang được tạo tại thời điểm lỗi.
- Chuỗi cause và bean được yêu cầu trong quá trình tạo.
- Stack trace tại bước evaluate expression hoặc resolve bean.

Thông báo cụ thể phụ thuộc phiên bản Spring và đường đi khởi tạo. Không chỉ dựa vào dòng exception đầu tiên; hãy tìm nguyên nhân gốc và bean reference được evaluate.

### 5.2. Tìm bean reference trong cấu hình

Tìm các biểu thức có cú pháp @beanName trong:

- Annotation @Value.
- XML bean definition.
- Java configuration có gọi parser hoặc Expression.
- File cấu hình chứa SpEL.
- Các class tự tạo StandardEvaluationContext và gắn BeanResolver.
- Policy hoặc helper đánh giá expression trong startup.

Khi tìm thấy, xác định expression được evaluate lúc startup hay runtime. Sau đó lần theo bean được tham chiếu và dependency của bean đó.

### 5.3. Dựng sơ đồ dependency

Ghi lại quan hệ theo chiều bean cần bean khác:

~~~text
Bean A --SpEL--> Bean B
Bean B --constructor--> Bean C
Bean C --@Value SpEL--> Bean A
~~~

Sơ đồ giúp nhìn ra chu trình mà mỗi class riêng lẻ có thể không thể hiện đầy đủ.

Nếu có nhiều bean, liệt kê từng cạnh và đánh dấu cạnh nào đến từ constructor injection, setter injection, @Value, @DependsOn hoặc bean lookup trong method.

### 5.4. Kiểm thử khởi tạo ApplicationContext

Một test tạo ApplicationContext tối thiểu có thể tái hiện lỗi mà không cần chạy toàn bộ ứng dụng:

~~~java
@Test
void applicationContextShouldStart() {
    try (AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(TestConfig.class)) {
        assertNotNull(context.getBean(PricingPolicy.class));
    }
}
~~~

Nếu context không khởi động, test sẽ chỉ ra lỗi trong quá trình tạo bean. Nên tạo test nhỏ với đúng cấu hình liên quan để rút ngắn chuỗi điều tra.

Với Spring Boot, có thể dùng context test hoặc ApplicationContextRunner để kiểm tra cấu hình riêng. Đảm bảo test tải đúng profile, property source và bean condition giống môi trường gặp lỗi.

## 6. Cách xử lý tốt nhất: loại bỏ dependency vòng

### 6.1. Tách logic dùng chung thành bean thứ ba

Giả sử PricingPolicy và CurrencyRules cần cùng một quy tắc tiền tệ. Nếu chúng tham chiếu lẫn nhau, hãy tách dữ liệu hoặc quy tắc dùng chung thành một bean độc lập:

~~~text
PricingPolicy -----> CurrencySettings
CurrencyRules -----> CurrencySettings
~~~

Ví dụ:

~~~java
@Component
public class CurrencySettings {

    public String defaultCurrency() {
        return "VND";
    }
}
~~~

~~~java
@Component
public class PricingPolicy {

    private final CurrencySettings settings;

    public PricingPolicy(CurrencySettings settings) {
        this.settings = settings;
    }
}
~~~

~~~java
@Component
public class CurrencyRules {

    private final CurrencySettings settings;

    public CurrencyRules(CurrencySettings settings) {
        this.settings = settings;
    }
}
~~~

Cả hai bean phụ thuộc vào một abstraction hoặc nguồn dữ liệu chung, không phụ thuộc ngược vào nhau.

Đây thường là cách sửa bền vững nhất vì nó làm rõ trách nhiệm và dependency graph.

### 6.2. Chuyển dữ liệu cấu hình sang @ConfigurationProperties

Nếu expression chỉ tham chiếu bean để đọc các giá trị cấu hình, hãy đưa các giá trị đó vào một configuration properties class:

~~~java
@ConfigurationProperties(prefix = "app.currency")
public record CurrencyProperties(String defaultCurrency) {
}
~~~

Cấu hình:

~~~yaml
app:
  currency:
    default-currency: VND
~~~

Các bean cần giá trị có thể inject CurrencyProperties:

~~~java
@Component
public class PricingPolicy {

    private final CurrencyProperties properties;

    public PricingPolicy(CurrencyProperties properties) {
        this.properties = properties;
    }
}
~~~

Cách này loại bỏ nhu cầu tra cứu một bean khác thông qua SpEL chỉ để lấy một giá trị. Nó cũng giúp kiểu dữ liệu, validation và nguồn cấu hình rõ ràng hơn.

### 6.3. Đưa dependency vào constructor

Nếu một bean thực sự cần một bean khác để hoạt động, khai báo dependency bằng constructor injection:

~~~java
@Component
public class PricingPolicy {

    private final CurrencyRules currencyRules;

    public PricingPolicy(CurrencyRules currencyRules) {
        this.currencyRules = currencyRules;
    }
}
~~~

Dependency được thể hiện rõ trong chữ ký class. Nếu constructor injection tạo vòng, đó là dấu hiệu kiến trúc cần được xem lại thay vì che giấu bằng SpEL.

Ưu tiên constructor injection cho dependency bắt buộc. Nó giúp object không thể được tạo trong trạng thái thiếu dependency.

## 7. Khi cần trì hoãn việc tra cứu bean

Một số trường hợp thực sự cần tra cứu bean tại thời điểm sử dụng thay vì lúc tạo bean. Có thể dùng các cơ chế provider hoặc proxy để trì hoãn việc lấy dependency, nhưng chúng chỉ thay đổi thời điểm tra cứu; chúng không tự loại bỏ vòng logic.

### 7.1. ObjectProvider

Spring cung cấp ObjectProvider để lấy bean theo yêu cầu:

~~~java
@Component
public class PricingPolicy {

    private final ObjectProvider<CurrencyRules> rulesProvider;

    public PricingPolicy(
            ObjectProvider<CurrencyRules> rulesProvider) {
        this.rulesProvider = rulesProvider;
    }

    public String currencyForOrder(Order order) {
        CurrencyRules rules = rulesProvider.getObject();
        return rules.currencyFor(order);
    }
}
~~~

ObjectProvider được inject mà không cần tạo ngay CurrencyRules. Bean chỉ được tra cứu khi getObject() được gọi.

Điều này có thể trì hoãn lookup cho tới khi method runtime chạy, sau khi các bean đã khởi tạo. Nhưng nếu currencyFor() được gọi trong lúc CurrencyRules vẫn đang tạo và lại cần PricingPolicy, vòng vẫn xảy ra.

### 7.2. @Lazy

Có thể dùng @Lazy ở dependency để tạo proxy và trì hoãn việc khởi tạo bean đích cho tới khi proxy được sử dụng:

~~~java
@Component
public class PricingPolicy {

    private final CurrencyRules currencyRules;

    public PricingPolicy(@Lazy CurrencyRules currencyRules) {
        this.currencyRules = currencyRules;
    }
}
~~~

@Lazy có thể giúp trì hoãn khởi tạo trong một số trường hợp. Tuy nhiên, khi expression truy cập property hoặc gọi method trên bean lazy, proxy có thể kích hoạt việc tạo bean đích ngay lúc đó.

Vì vậy, @Lazy không phải giải pháp tổng quát cho vòng phụ thuộc. Chỉ dùng khi việc trì hoãn là một phần có chủ đích của thiết kế và thời điểm sử dụng đã được kiểm soát.

### 7.3. Provider và lookup method

Jakarta Inject Provider hoặc các cơ chế lookup method cũng có thể trì hoãn việc lấy dependency. Chúng phù hợp khi object có vòng đời khác nhau hoặc khi cần lấy một instance mới theo yêu cầu.

Cần kiểm tra vòng đời và thời điểm gọi provider. Nếu hai bean vẫn gọi lẫn nhau ngay trong giai đoạn khởi tạo, việc đổi cách lookup không giải quyết được nguyên nhân.

### 7.4. Dùng bean reference trong SpEL ở runtime

Nếu một expression cần tham chiếu bean nhưng không cần giá trị tại startup, có thể trì hoãn việc evaluate tới một method nghiệp vụ được gọi sau khi context đã sẵn sàng:

~~~java
public boolean isEligible(
        String expressionSource,
        EvaluationContext context) {

    Expression expression =
            parser.parseExpression(expressionSource);

    return Boolean.TRUE.equals(
            expression.getValue(context, Boolean.class)
    );
}
~~~

Cách này chỉ phù hợp khi source và context được kiểm soát, và việc evaluate không diễn ra trong quá trình khởi tạo bean. Không nên chuyển mọi logic khởi tạo sang runtime chỉ để né lỗi nếu dependency thực chất vẫn tạo thành một vòng logic.

## 8. Vì sao @DependsOn không phá được vòng?

@DependsOn cho Spring biết một bean cần được khởi tạo sau bean khác:

~~~java
@DependsOn("currencyRules")
@Component
public class PricingPolicy {
}
~~~

Nó điều khiển thứ tự khởi tạo và hủy bean trong một số tình huống. Nó không loại bỏ quan hệ phụ thuộc hai chiều.

Nếu PricingPolicy cần CurrencyRules và CurrencyRules cũng cần PricingPolicy, thêm @DependsOn theo một trong hai hướng có thể chỉ làm container đi vào chuỗi tạo bean khác trước rồi vẫn quay lại bean đang được tạo.

Không dùng @DependsOn như cách chữa dependency cycle. Hãy dùng nó cho quan hệ thứ tự khởi tạo thực sự độc lập, không có phụ thuộc ngược.

Tương tự, @Order điều khiển thứ tự ở một số cơ chế như collection injection hoặc xử lý có thứ tự; nó không giải quyết vòng khởi tạo bean.

## 9. Circular references và cấu hình Spring Boot

### 9.1. Khả năng hỗ trợ phụ thuộc vòng

Spring Framework có cơ chế xử lý một số vòng phụ thuộc singleton, đặc biệt trong các trường hợp setter/property injection. Khả năng này phụ thuộc kiểu dependency, scope, proxy, bean post-processor và cấu hình container.

Constructor cycle không thể giải quyết bằng early singleton reference vì chưa có instance để cung cấp.

### 9.2. Spring Boot có thể từ chối circular references

Một số phiên bản Spring Boot mặc định không cho phép circular references và có thể dừng startup khi phát hiện vòng. Cấu hình và hành vi cụ thể phụ thuộc phiên bản Boot đang sử dụng.

Trong các phiên bản có hỗ trợ thuộc tính:

~~~properties
spring.main.allow-circular-references=true
~~~

việc bật tùy chọn này có thể cho phép một số vòng singleton mà Spring có thể giải quyết. Nó không làm cho mọi vòng trở nên hợp lệ và không giải quyết constructor cycle.

Không nên bật tùy chọn này chỉ để ứng dụng khởi động được. Hãy xem exception là tín hiệu cần kiểm tra dependency graph và refactor.

### 9.3. Khác biệt giữa startup và runtime lookup

Một bean reference trong @Value có thể được evaluate trong quá trình khởi tạo. Một expression được ứng dụng tự evaluate sau startup có thể tra cứu bean khi context đã hoàn chỉnh.

Hai trường hợp có thời điểm và rủi ro khác nhau. Khi xử lý lỗi, hãy xác định expression được dùng trong bean definition, field injection, lifecycle callback hay trong một luồng nghiệp vụ runtime.

## 10. Các lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
|---|---|---|
| @Value tham chiếu bean đang phụ thuộc ngược | Tạo dependency ẩn | Tách bean hoặc dùng cấu hình rõ ràng |
| Hai bean gọi property của nhau qua SpEL | Vòng khởi tạo khó nhận biết | Chuyển dữ liệu chung sang bean thứ ba |
| Gọi method service trong @Value | Khởi tạo bean có thể kích hoạt logic nghiệp vụ | Đưa logic vào service/runtime sau startup |
| Dùng @Lazy để che vòng | Chỉ trì hoãn thời điểm lỗi có thể xảy ra | Xác định và loại bỏ quan hệ vòng |
| Dùng @DependsOn theo cả hai hướng | Chỉ điều khiển thứ tự, không phá dependency | Thiết kế lại quan hệ |
| Bật allow-circular-references để bỏ qua lỗi | Có thể che giấu thiết kế mong manh | Refactor và ưu tiên constructor injection |
| Dùng ApplicationContext.getBean trong constructor | Tạo lookup ẩn và phụ thuộc runtime khó kiểm soát | Inject dependency tường minh hoặc provider |
| Dùng SpEL để đọc giá trị cấu hình đơn giản | Tăng liên kết không cần thiết | Dùng @ConfigurationProperties hoặc placeholder |
| Bắt BeanCurrentlyInCreationException rồi trả mặc định | Che giấu lỗi khởi tạo | Sửa dependency graph và giữ nguyên nguyên nhân |

## 11. Quy trình điều tra và sửa lỗi

Khi gặp vòng phụ thuộc do expression tham chiếu bean khác, có thể thực hiện theo trình tự:

1. **Tìm bean trong exception.** Ghi nhận bean đang tạo và bean được yêu cầu tại thời điểm lỗi.
2. **Tìm expression liên quan.** Kiểm tra @Value, XML bean definition và các đoạn code tự evaluate SpEL.
3. **Xác định thời điểm evaluate.** Phân biệt lúc startup, populate property, @PostConstruct và runtime.
4. **Lần theo dependency tiếp theo.** Kiểm tra constructor, field, setter, @DependsOn và bean reference khác của bean được tra cứu.
5. **Vẽ chu trình.** Ghi rõ từng cạnh dependency và đánh dấu cạnh đến từ SpEL.
6. **Xác định dữ liệu thật sự cần.** Có thể chỉ cần một giá trị cấu hình, một predicate hoặc một policy nhỏ.
7. **Refactor.** Tách shared component, chuyển cấu hình sang @ConfigurationProperties, inject dependency tường minh hoặc trì hoãn lookup nếu đúng yêu cầu.
8. **Kiểm thử startup.** Tạo ApplicationContext với cấu hình thực tế và xác nhận không còn vòng.
9. **Kiểm thử hành vi runtime.** Bảo đảm biểu thức vẫn cho kết quả đúng và không kích hoạt lookup trong giai đoạn ngoài dự kiến.

Không chỉ thêm @Lazy hoặc bật circular references rồi kết luận lỗi đã được xử lý. Hãy xác nhận chu trình dependency thực sự đã được loại bỏ hoặc việc trì hoãn lookup có chủ đích và an toàn.

## 12. Kiểm thử vòng phụ thuộc

### 12.1. Kiểm thử context khởi động

Có thể viết integration test để bảo đảm ApplicationContext tạo được các bean liên quan:

~~~java
@SpringBootTest
class ApplicationContextTest {

    @Autowired
    private PricingPolicy pricingPolicy;

    @Test
    void contextStartsAndPricingPolicyIsAvailable() {
        assertNotNull(pricingPolicy);
    }
}
~~~

Nếu test thất bại khi tạo context, xem chuỗi cause để tìm bean và expression gây vòng.

### 12.2. Kiểm thử biểu thức riêng

Nếu expression chỉ cần lấy một giá trị, có thể kiểm thử nó trong context đã khởi tạo:

~~~java
Expression expression =
        parser.parseExpression("@currencyRules.defaultCurrency");

String currency =
        expression.getValue(evaluationContext, String.class);

assertEquals("VND", currency);
~~~

Test này xác nhận bean reference và property resolution hoạt động trong runtime context. Nó không thay thế test khởi tạo ApplicationContext nếu expression được dùng trong @Value hoặc bean definition.

### 12.3. Kiểm thử trường hợp lỗi

Nếu ứng dụng có cấu hình expression theo môi trường, hãy kiểm thử cả các profile hoặc property source có thể làm thay đổi bean reference.

Nên có test xác nhận:

- Context khởi động với cấu hình hợp lệ.
- Bean được tham chiếu tồn tại.
- Expression trả về đúng kiểu và giá trị.
- Không có lookup ngoài dự kiến trong constructor hoặc @PostConstruct.
- Cấu hình thiếu bean được báo lỗi rõ ràng.
- Không có fallback âm thầm che giấu lỗi khởi tạo.

## 13. Tổng kết

Bean reference trong SpEL dùng cú pháp **@beanName** và có thể khiến Spring tra cứu hoặc khởi tạo bean khi expression được evaluate. Nếu bean được tham chiếu lại phụ thuộc vào bean đang tạo, ứng dụng có thể gặp vòng phụ thuộc và lỗi như BeanCurrentlyInCreationException.

- Dependency ẩn trong chuỗi SpEL khó nhận biết hơn constructor injection.
- Property expression cũng có thể kích hoạt bean lookup, không chỉ method call.
- Constructor cycle thường không thể giải quyết; một số singleton setter cycle chỉ có thể được xử lý trong điều kiện giới hạn.
- @Lazy và ObjectProvider có thể trì hoãn lookup nhưng không tự loại bỏ vòng logic.
- @DependsOn chỉ điều khiển thứ tự, không phá dependency hai chiều.
- Không bật circular references chỉ để che lỗi.
- Ưu tiên tách shared component, chuyển giá trị cấu hình sang @ConfigurationProperties và khai báo dependency tường minh.
- Kiểm thử cả thời điểm startup lẫn runtime evaluate.

SpEL phù hợp để biểu đạt một giá trị hoặc predicate ngắn. Khi expression phải tra cứu nhiều bean hoặc điều phối logic khởi tạo, hãy chuyển dependency sang Java và thiết kế lại các bean để mỗi thành phần có trách nhiệm rõ ràng, không cần tham chiếu ngược lẫn nhau.
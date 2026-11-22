# Tên tầng context và quy tắc hợp nhất hoặc ghi đè

Trong Spring TestContext Framework, một bài kiểm thử có thể nạp ApplicationContext từ nhiều class cấu hình hoặc nhiều resource. Khi test class kế thừa test class khác, cấu hình context còn có thể được kế thừa, hợp nhất hoặc thay thế. Với ứng dụng web nhiều tầng, một context có thể làm cha của context khác. Nếu không hiểu rõ các quy tắc này, test dễ nạp thừa bean, thiếu cấu hình, tạo context mới ngoài dự kiến hoặc vô tình giữ lại cấu hình từ lớp cha.

Spring cung cấp **@ContextConfiguration** để khai báo nguồn cấu hình và **@ContextHierarchy** để mô tả quan hệ nhiều tầng. Thuộc tính **name** của từng @ContextConfiguration giúp nhận diện một tầng trong hierarchy. Các thuộc tính như **inheritLocations** và **inheritInitializers** quyết định cấu hình từ lớp cha được kế thừa hay thay thế. Những quy tắc này cần được phân biệt với việc ghi đè bean definition hoặc chọn bean khi có nhiều ứng viên.

Bài học này tập trung vào cách đặt tên tầng context, cách Spring hợp nhất hoặc thay thế metadata cấu hình trong hệ thống test kế thừa, quan hệ parent-child giữa các ApplicationContext và cách thiết kế test hierarchy có thể dự đoán được.

## 1. ApplicationContext trong Spring TestContext

ApplicationContext là container quản lý bean, dependency injection, event và các dịch vụ nền tảng của Spring. Trong kiểm thử, Spring TestContext Framework tạo và quản lý context dựa trên metadata của test class.

Nguồn cấu hình có thể đến từ:

- Class Java có @Configuration.
- Class được khai báo trong thuộc tính classes của @ContextConfiguration.
- Resource XML được khai báo trong locations.
- ApplicationContextInitializer được đăng ký để tùy chỉnh context trước khi refresh.
- Các cấu hình bổ sung do test hoặc framework cung cấp.

Ví dụ một test class dùng Java configuration:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfig.class)
class OrderServiceTest {
    @Autowired
    OrderService orderService;
}
~~~

SpringExtension kết nối JUnit Jupiter với TestContext Framework. @ContextConfiguration khai báo rằng OrderTestConfig là nguồn cấu hình dùng để tạo context. Spring nạp context trước khi chạy test và inject các dependency cần thiết vào test instance.

Một test class khác có cùng metadata cấu hình có thể tái sử dụng context đã được cache. Vì vậy, metadata cấu hình không chỉ quyết định bean nào được nạp mà còn ảnh hưởng đến khả năng chia sẻ context giữa các test.

### 1.1. Context configuration là metadata, không phải bean

Các giá trị classes, locations, initializers, profiles và properties mô tả cách tạo context. Chúng không phải là tên bean và cũng không phải instance của bean.

Ví dụ:

- OrderTestConfig là class cấu hình.
- orderService là tên bean có thể được đăng ký trong context.
- "web" có thể là tên một tầng trong @ContextHierarchy.

Ba khái niệm này phục vụ các mục đích khác nhau. Đặt tên tầng context là "web" không tạo ra bean tên "web". Tương tự, hai context cùng có bean tên orderService không có nghĩa chúng là cùng một context hoặc cùng một instance.

## 2. @ContextConfiguration và quy tắc kế thừa

@ContextConfiguration khai báo nguồn cấu hình cho một context. Các thuộc tính thường dùng gồm:

| Thuộc tính | Vai trò |
| --- | --- |
| classes | Các class cấu hình hoặc component cần nạp |
| locations / value | Đường dẫn resource cấu hình, thường là XML |
| initializers | Các ApplicationContextInitializer |
| inheritLocations | Cho phép kế thừa và hợp nhất locations/classes từ test class cha |
| inheritInitializers | Cho phép kế thừa initializer từ test class cha |
| name | Đặt tên cho một tầng khi dùng trong context hierarchy |
| loader | Chọn ContextLoader tạo context |

Với test class kế thừa, mặc định **inheritLocations = true**. Khi lớp con khai báo thêm @ContextConfiguration, các class hoặc locations của lớp con được hợp nhất với cấu hình được kế thừa từ lớp cha.

Ví dụ:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = BaseTestConfig.class)
abstract class BaseServiceTest {
}

@ContextConfiguration(classes = PaymentTestConfig.class)
class PaymentServiceTest extends BaseServiceTest {
}
~~~

Với cấu hình kế thừa mặc định, Spring sử dụng cả BaseTestConfig và PaymentTestConfig để tạo context cho PaymentServiceTest. Việc hợp nhất ở đây là hợp nhất nguồn cấu hình, không phải hợp nhất hai ApplicationContext đã tồn tại thành một object.

### 2.1. Hợp nhất cấu hình của lớp cha và lớp con

Khi inheritLocations là true, nguồn cấu hình được khai báo ở lớp con được thêm vào nguồn cấu hình kế thừa. Điều này hữu ích khi lớp cha cung cấp các bean nền tảng mà nhiều nhóm test cùng dùng, còn lớp con chỉ bổ sung một số bean chuyên biệt.

Ví dụ:

~~~java
@Configuration
class SharedTestConfig {
    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}

@Configuration
class BillingTestConfig {
    @Bean
    BillingPolicy billingPolicy() {
        return new BillingPolicy();
    }
}

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SharedTestConfig.class)
abstract class SharedServiceTest {
}

@ContextConfiguration(classes = BillingTestConfig.class)
class BillingServiceTest extends SharedServiceTest {
}
~~~

BillingServiceTest nhận được cả testClock và billingPolicy nếu hai cấu hình được đăng ký mà không có xung đột bean definition. Lớp cha có thể cung cấp các thành phần dùng chung như clock, converter, fixture adapter hoặc cấu hình test cơ bản.

### 2.2. Thay thế nguồn cấu hình được kế thừa

Nếu lớp con không muốn dùng các locations/classes của lớp cha, hãy đặt **inheritLocations = false**:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = LegacyBaseConfig.class)
abstract class LegacyBaseTest {
}

@ContextConfiguration(
    classes = IsolatedPaymentConfig.class,
    inheritLocations = false
)
class IsolatedPaymentTest extends LegacyBaseTest {
}
~~~

Trong trường hợp này, IsolatedPaymentConfig thay thế nguồn cấu hình được kế thừa cho context của lớp con. Nó không tự động nạp thêm LegacyBaseConfig.

Đây là lựa chọn hữu ích khi lớp cha chứa cấu hình mặc định không phù hợp với một nhóm test chuyên biệt. Tuy nhiên, hãy kiểm tra xem lớp con còn cần các bean nền tảng nào của lớp cha hay không. Nếu cần, hãy import chúng có chủ đích vào cấu hình mới.

### 2.3. inheritInitializers là một quy tắc riêng

inheritLocations và inheritInitializers kiểm soát hai loại metadata khác nhau:

- inheritLocations điều khiển việc kế thừa locations/classes.
- inheritInitializers điều khiển việc kế thừa ApplicationContextInitializer.

Mặc định, initializer được kế thừa. Nếu lớp con đặt inheritInitializers = false, các initializer từ lớp cha không được kế thừa cho cấu hình đó.

Không nên nghĩ rằng inheritLocations = false cũng tự động loại bỏ initializer. Nếu cần thay thế cả nguồn cấu hình và initializer, hãy đặt từng thuộc tính theo mục tiêu rõ ràng.

## 3. Vì sao cần đặt tên cho tầng context?

Một ứng dụng web truyền thống có thể có nhiều ApplicationContext:

- Root context chứa service, repository, transaction manager và các bean dùng chung.
- Web context chứa controller, MVC configuration, view resolver và web-specific component.
- Một số ứng dụng còn có context riêng cho từng DispatcherServlet hoặc một module web độc lập.

Các context này tạo thành một hierarchy: context con có thể truy cập bean từ context cha, nhưng context cha không nhìn thấy bean chỉ tồn tại ở context con.

Khi test class kế thừa một hierarchy, Spring cần biết cấu hình mà lớp con khai báo thuộc tầng nào. Thuộc tính **name** của @ContextConfiguration giúp xác định danh tính của từng tầng để ghép đúng cấu hình với tầng tương ứng.

Ví dụ:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = BaseWebConfig.class
    )
})
abstract class BaseWebTest {
}
~~~

Ở đây hierarchy có hai tầng theo thứ tự từ trên xuống:

1. root: context gốc, dùng RootConfig.
2. web: context con của root, dùng BaseWebConfig.

Tên "root" và "web" là nhãn nhận diện tầng trong metadata của test. Chúng không phải tên bean, tên profile hoặc tên URL.

### 3.1. Thứ tự tầng trong @ContextHierarchy

Các @ContextConfiguration trong @ContextHierarchy được khai báo theo thứ tự từ parent đến child. Cấu hình đầu tiên tạo context cha; cấu hình kế tiếp tạo context con sử dụng context trước làm parent.

Ví dụ:

~~~text
Root ApplicationContext
  - service
  - repository
  - transaction manager
        |
        v
Web ApplicationContext
  - controller
  - handler mapping
  - view resolver
~~~

Bean trong Web ApplicationContext có thể sử dụng bean từ Root ApplicationContext. Bean chỉ đăng ký trong Web ApplicationContext không tự động xuất hiện khi truy vấn Root ApplicationContext.

Không nên đảo thứ tự chỉ để làm một bean dễ truy cập. Hãy mô tả hierarchy theo ranh giới thực của ứng dụng.

### 3.2. Tên tầng và chỉ số tầng

Spring cần phân biệt các level khi so sánh cấu hình hierarchy giữa lớp cha và lớp con. Nếu không đặt name tường minh, framework có thể sử dụng tên mặc định dựa trên vị trí của level trong hierarchy.

Với hierarchy đơn giản và không có kế thừa phức tạp, tên mặc định có thể đủ. Nhưng khi lớp con chỉ khai báo bổ sung hoặc thay thế một tầng cụ thể, tên tường minh như "root", "web", "adminWeb" làm ý định rõ hơn và giảm nguy cơ ghép sai level.

Hãy dùng tên ổn định, có ý nghĩa và nhất quán giữa các test class. Tránh đổi tên tùy tiện ở lớp con vì việc nhận diện tầng dựa trên tên có thể ảnh hưởng cách Spring kế thừa, hợp nhất hoặc thay thế metadata.

## 4. Hợp nhất cấu hình tại cùng một tầng hierarchy

Khi test class con khai báo một @ContextHierarchy, Spring cần xác định cấu hình mới thuộc tầng nào của hierarchy kế thừa. Nếu tên tầng trùng với tầng ở lớp cha, cấu hình có thể được hợp nhất vào đúng tầng đó theo quy tắc kế thừa của @ContextConfiguration.

Ví dụ lớp cha:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = CommonWebConfig.class
    )
})
abstract class BaseWebTest {
}
~~~

Lớp con bổ sung cấu hình web:

~~~java
@ContextHierarchy({
    @ContextConfiguration(
        name = "web",
        classes = AdminWebConfig.class
    )
})
class AdminControllerTest extends BaseWebTest {
}
~~~

Tên "web" ở lớp con khớp với tầng "web" của lớp cha. Theo mặc định inheritLocations là true, nguồn cấu hình AdminWebConfig được hợp nhất với CommonWebConfig ở tầng web. Tầng root được kế thừa từ lớp cha.

Kết quả mong muốn về mặt cấu trúc:

~~~text
root
  RootConfig
    |
    v
web
  CommonWebConfig
  AdminWebConfig
~~~

Ví dụ này giả định các cấu hình có thể cùng tồn tại. Nếu chúng đăng ký bean trùng tên hoặc nhiều bean cùng type mà không có cách phân giải phù hợp, context có thể gặp lỗi hoặc injection trở nên mơ hồ. Hợp nhất metadata không tự giải quyết xung đột bean.

### 4.1. Tên khác nhau có thể tạo ra tầng khác

Nếu lớp con khai báo name khác với tầng muốn bổ sung, Spring không thể hiểu đó là cùng một level chỉ dựa trên ý nghĩa tên mà người viết nghĩ tới. Một tên mới có thể được xem là một cấu hình level khác trong metadata kế thừa.

Ví dụ, nếu lớp cha đặt tầng web là "web" nhưng lớp con đặt "mvc" với ý định bổ sung cấu hình vào tầng web, hai tên không khớp. Đừng dựa vào việc chúng cùng chứa chữ "web" hoặc cùng dùng WebConfig để mong framework tự ghép.

Khi muốn merge, hãy dùng cùng một tên tầng. Khi muốn tạo một level mới, hãy dùng tên mới và khai báo vị trí parent-child đúng theo hierarchy.

### 4.2. Hợp nhất không đồng nghĩa với bean override

Giả sử CommonWebConfig và AdminWebConfig cùng khai báo một bean tên "menuService". Việc hai configuration class được hợp nhất vào tầng web không có nghĩa Spring sẽ tự động kết hợp hai object thành một hoặc luôn chọn bean của lớp con.

Việc đăng ký bean trùng tên phụ thuộc cách bean definition được đăng ký và chính sách cho phép overriding của context. Nếu có nhiều bean cùng type nhưng tên khác nhau, autowiring có thể cần @Primary, @Qualifier hoặc một cách phân giải rõ ràng khác.

Hãy phân biệt:

- **Merge context metadata:** hợp nhất danh sách class/resource cấu hình cho cùng một context level.
- **Bean definition overriding:** một bean definition thay thế bean definition khác cùng tên trong một registry, nếu cơ chế và chính sách hiện hành cho phép.
- **Dependency candidate resolution:** Spring chọn bean phù hợp để inject khi có một hoặc nhiều ứng viên.

Ba việc này có liên quan nhưng không phải cùng một thao tác.

## 5. Ghi đè cấu hình của một tầng mà vẫn giữ tầng cha

Đôi khi lớp con muốn giữ Root ApplicationContext nhưng thay hoàn toàn cấu hình của Web ApplicationContext. Khi đó, cần khớp tên tầng và đặt inheritLocations = false cho cấu hình của tầng đó.

Ví dụ:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = CommonWebConfig.class
    )
})
abstract class BaseWebTest {
}

@ContextHierarchy({
    @ContextConfiguration(
        name = "web",
        classes = IsolatedAdminWebConfig.class,
        inheritLocations = false
    )
})
class IsolatedAdminControllerTest extends BaseWebTest {
}
~~~

Ý nghĩa:

- Tầng root vẫn được kế thừa.
- Tầng web vẫn là tầng cần cấu hình.
- IsolatedAdminWebConfig thay thế nguồn cấu hình web được kế thừa.
- CommonWebConfig không được hợp nhất vào tầng web của lớp con qua cấu hình này.

Sơ đồ:

~~~text
root
  RootConfig
    |
    v
web
  IsolatedAdminWebConfig
~~~

Điểm quan trọng là inheritLocations = false áp dụng cho metadata cấu hình của level tương ứng. Nó không có nghĩa xóa bean khỏi một context cha khác, không thay đổi source code của configuration class và không tự xóa mọi bean được import gián tiếp bởi cấu hình mới.

### 5.1. Khi nào nên thay thế thay vì hợp nhất?

Hợp nhất phù hợp khi lớp con thực sự cần thêm bean vào cấu hình chung. Ghi đè phù hợp khi cấu hình kế thừa không tương thích hoặc khi test cần một context cô lập.

Ví dụ:

| Tình huống | Lựa chọn |
| --- | --- |
| Lớp cha cung cấp Clock, lớp con thêm BillingService | Merge |
| Lớp cha cung cấp cấu hình database mặc định, lớp con cần database test khác hoàn toàn | Override hoặc dùng cấu hình test chuyên biệt |
| Lớp cha nạp MVC config chung, lớp con thêm controller/configuration riêng | Merge nếu không có xung đột |
| Lớp cha nạp bean thật, lớp con cần một cấu hình isolated để kiểm tra failure path | Override có chủ đích |
| Lớp con chỉ muốn thay một bean collaborator | Cân nhắc bean override/test configuration thay vì thay toàn bộ locations/classes |

Không nên dùng inheritLocations = false như cách dọn context tùy tiện. Nó có thể làm mất các cấu hình nền mà test vẫn cần.

## 6. Tên tầng context không phải tên bean

Một nguồn nhầm lẫn phổ biến là sử dụng từ "name" ở nhiều API khác nhau:

| Tên | Được dùng ở đâu | Ý nghĩa |
| --- | --- | --- |
| Context hierarchy level name | @ContextConfiguration(name = "...") | Nhận diện một tầng trong hierarchy của TestContext |
| Bean name | @Bean("..."), @Component("...") | Định danh bean trong BeanFactory |
| Profile name | @ActiveProfiles("...") | Chọn nhóm cấu hình theo profile |
| Property key | @TestPropertySource(properties = "...") | Cung cấp giá trị cấu hình |
| Context display/id trong logging | Framework/runtime | Phục vụ nhận diện hoặc chẩn đoán context |

Ví dụ:

~~~java
@Configuration
class RootConfig {
    @Bean("orderService")
    OrderService orderService() {
        return new OrderService();
    }
}

@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = WebConfig.class
    )
})
class OrderWebTest {
}
~~~

"root" là tên level trong test hierarchy. "orderService" là tên bean trong Root ApplicationContext. Đổi tên level không đổi bean name; đổi bean name không đổi cách Spring ghép level cấu hình.

## 7. Quy tắc parent-child và bean visibility

Context hierarchy tạo ra quan hệ cha-con thực sự giữa các ApplicationContext.

### 7.1. Context con nhìn thấy bean của context cha

Nếu root context có OrderService và web context có OrderController, OrderController có thể inject OrderService từ parent context:

~~~text
Root context
  orderService
  orderRepository
  transactionManager
       |
       v
Web context
  orderController
  mvcHandlerMapping
~~~

Bean ở context con được tìm trong context con trước, sau đó Spring có thể tìm lên parent khi cần. Vì vậy, controller ở web context có thể dùng service ở root context.

### 7.2. Context cha không nhìn thấy bean của context con

Chiều nhìn không đối xứng. Root context không thể inject bean chỉ được đăng ký trong web context. Nếu service ở root cần phụ thuộc một controller ở child, đó thường là dấu hiệu phân tầng bị đảo.

Hãy giữ dependency theo hướng:

~~~text
Web layer -> Application/Service layer -> Persistence/Infrastructure ports
~~~

Context hierarchy nên phản ánh hướng phụ thuộc đó.

### 7.3. Bean cùng tên ở parent và child

Nếu parent và child đều có bean cùng tên, bean ở child có thể che khuất bean parent khi tra cứu từ child context. Điều này không xóa bean definition khỏi parent context. Một truy vấn trực tiếp ở parent vẫn nhìn thấy bean của parent.

Đây khác với hai bean cùng tên được đăng ký vào cùng một BeanFactory. Ở trường hợp sau, chính sách bean definition overriding và cách đăng ký quyết định có cho phép thay thế hay báo lỗi.

Nếu việc che khuất là chủ đích, hãy ghi rõ trong cấu hình test và kiểm tra bean được inject tại đúng context. Nếu không, nên chọn tên khác hoặc dùng @Qualifier/@Primary để biểu đạt lựa chọn dependency rõ ràng.

## 8. Hợp nhất nguồn cấu hình và xung đột bean

Khi nhiều configuration class cùng được nạp vào một context, Spring xử lý bean definition theo quy tắc đăng ký bean. Có một số tình huống khác nhau:

### 8.1. Hai bean khác tên, cùng type

Ví dụ:

~~~java
@Configuration
class PaymentConfig {
    @Bean
    PaymentGateway primaryGateway() {
        return new PrimaryPaymentGateway();
    }

    @Bean
    PaymentGateway fallbackGateway() {
        return new FallbackPaymentGateway();
    }
}
~~~

Hai bean cùng type không nhất thiết xung đột khi đăng ký, nhưng injection theo type có thể mơ hồ nếu không có quy tắc lựa chọn. Có thể dùng @Primary hoặc @Qualifier tùy hợp đồng.

~~~java
@Bean
@Primary
PaymentGateway primaryGateway() {
    return new PrimaryPaymentGateway();
}
~~~

@Primary không ghi đè bean definition của fallbackGateway. Nó chỉ đánh dấu ứng viên ưu tiên khi Spring cần chọn bean phù hợp trong một số kiểu injection.

### 8.2. Hai bean cùng tên

Nếu hai cấu hình đăng ký bean cùng tên trong một BeanFactory, hành vi phụ thuộc chính sách bean definition overriding và cách các cấu hình được nạp. Một số môi trường cho phép bean definition sau thay thế bean trước; một số cấu hình, đặc biệt trong Spring Boot, có thể từ chối việc overriding và báo lỗi khởi tạo context.

Do đó, không nên dựa vào thứ tự nạp configuration để âm thầm thay bean. Hãy chọn một trong các cách rõ ràng:

- Chỉ import cấu hình chứa bean cần dùng.
- Dùng @Profile hoặc @Conditional để chọn cấu hình.
- Dùng @Primary hoặc @Qualifier khi có nhiều bean hợp lệ cùng type.
- Dùng cơ chế bean override dành cho test khi mục tiêu là thay một collaborator trong context.
- Tách cấu hình test riêng thay cho việc nạp cả hai cấu hình xung đột.

### 8.3. Hợp nhất class cấu hình không có nghĩa hợp nhất method

Nếu lớp cha và lớp con khai báo hai configuration class, TestContext có thể hợp nhất hai class đó thành nguồn tạo context. Spring vẫn xử lý từng bean definition, điều kiện đăng ký, import và dependency theo cơ chế container.

Không có thao tác tự động gộp nội dung hai phương thức @Bean cùng tên thành một bean. Một bean definition là một đơn vị đăng ký; việc trùng tên cần được xử lý theo chính sách container.

## 9. Kế thừa initializer và các cấu hình test khác

Ngoài locations/classes, TestContext còn có các nguồn metadata khác. Cần biết chúng có quy tắc riêng.

### 9.1. ApplicationContextInitializer

Initializer chạy trước khi context được refresh và có thể đăng ký property source, bean definition hoặc tùy chỉnh context. Khi test class con kế thừa cấu hình, initializer cũng được kế thừa theo mặc định nếu inheritInitializers là true.

Ví dụ:

~~~java
class SharedTestInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext context) {
        TestPropertyValues.of(
            "feature.enabled=false"
        ).applyTo(context);
    }
}

@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    classes = SharedTestConfig.class,
    initializers = SharedTestInitializer.class
)
abstract class BaseFeatureTest {
}
~~~

Lớp con có thể bổ sung initializer. Nếu không muốn kế thừa initializer của lớp cha, hãy cấu hình inheritInitializers = false cho @ContextConfiguration tương ứng.

### 9.2. @ActiveProfiles

Active profiles là metadata lựa chọn profile cho TestContext. Nó không phải tên hierarchy level. Khi test kế thừa, profile có quy tắc kế thừa và hợp nhất riêng; thuộc tính inheritProfiles có thể được dùng để kiểm soát việc kế thừa profile.

Không dùng inheritLocations để thay đổi profile. Nếu lớp con cần profile khác, hãy cấu hình @ActiveProfiles theo mục tiêu và kiểm tra chính sách kế thừa profile độc lập.

### 9.3. @TestPropertySource

@TestPropertySource cung cấp property cho Environment của test context. Nó có cơ chế kế thừa và độ ưu tiên riêng. Việc thay locations/classes trong @ContextConfiguration không đồng nghĩa mọi property source được kế thừa cũng bị loại bỏ.

Khi test cần thay một giá trị cấu hình, hãy cân nhắc khai báo property trực tiếp thay vì thay toàn bộ context configuration. Điều này giúp giới hạn thay đổi vào đúng phần metadata cần điều chỉnh.

### 9.4. Bean override cho test

Một số phiên bản Spring Test cung cấp annotation để thay bean trong context bằng mock hoặc bean test. Đây là cơ chế bean override, khác với việc thay toàn bộ locations/classes của context.

Nếu chỉ muốn thay PaymentGateway trong một test, không nhất thiết phải dùng inheritLocations = false rồi tạo lại toàn bộ root/web configuration. Hãy dùng cơ chế bean override phù hợp với phiên bản Spring của dự án hoặc đăng ký một test configuration có chủ đích.

## 10. Context caching và ảnh hưởng của cấu hình

Spring TestContext Framework lưu cache ApplicationContext để tái sử dụng giữa các test có cùng cấu hình. Việc cache giúp suite chạy nhanh hơn vì context không phải tạo lại cho mỗi test method.

Cache key được xây dựng từ metadata cấu hình như:

- Context locations và classes.
- Context initializer classes.
- Active profiles.
- Property source descriptors và inline properties.
- Context customizers.
- Context loader.
- Parent context trong hierarchy.
- Các thuộc tính liên quan khác của test context.

Vì vậy, hai test class gần giống nhau nhưng có khác biệt metadata vẫn có thể tạo context cache entry khác nhau. Ngược lại, các test có cùng cấu hình có thể dùng chung context.

### 10.1. Tên tầng ảnh hưởng đến việc ghép hierarchy

Trong context hierarchy, tên level giúp Spring nhận diện cấu hình tương ứng giữa lớp cha và lớp con. Nếu đổi tên level mà không cập nhật lớp kế thừa, metadata có thể không còn ghép như mong đợi.

Hãy xem tên level như một phần của hợp đồng cấu hình test. Chọn tên có ý nghĩa, ổn định và tái sử dụng nhất quán.

### 10.2. Đừng dùng @DirtiesContext để sửa cấu hình sai

@DirtiesContext đánh dấu context cần loại khỏi cache sau một test hoặc nhóm test. Nó hữu ích khi test làm thay đổi trạng thái singleton hoặc context theo cách không thể khôi phục.

Nó không phải cách giải quyết xung đột bean definition, sai tên hierarchy level hoặc kế thừa metadata không đúng. Những vấn đề đó cần được sửa ở cấu hình.

Với context hierarchy, Spring hỗ trợ các chế độ đóng context ở cấp hiện tại hoặc toàn bộ hierarchy. Chọn chế độ phù hợp khi test thực sự làm hỏng một level hoặc các level liên quan. Không dùng @DirtiesContext rộng rãi nếu chỉ cần rollback dữ liệu database hoặc reset fake.

## 11. Ví dụ hoàn chỉnh: root context và web context

Giả sử một ứng dụng Spring MVC có service dùng chung ở root context và controller ở web context.

Root configuration:

~~~java
@Configuration
class RootConfig {

    @Bean
    OrderService orderService() {
        return new OrderService();
    }
}
~~~

Web configuration:

~~~java
@Configuration
@EnableWebMvc
class WebConfig {

    @Bean
    OrderController orderController(OrderService orderService) {
        return new OrderController(orderService);
    }
}
~~~

Test base:

~~~java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(
        name = "root",
        classes = RootConfig.class
    ),
    @ContextConfiguration(
        name = "web",
        classes = WebConfig.class
    )
})
abstract class BaseOrderWebTest {
}
~~~

Test class:

~~~java
class OrderControllerContextTest extends BaseOrderWebTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    @Test
    void web_context_can_resolve_service_from_parent() {
        assertThat(webApplicationContext.getBean(OrderController.class))
            .isNotNull();
        assertThat(webApplicationContext.getBean(OrderService.class))
            .isNotNull();
    }
}
~~~

Ví dụ trên minh họa việc web context nhìn thấy service từ root context. Trong một ứng dụng thực tế, root context thường là context cha được khởi tạo trước và web context là child.

### 11.1. Bổ sung cấu hình web cho một nhóm test

~~~java
@Configuration
class AdminWebTestConfig {
    @Bean
    AdminController adminController(OrderService orderService) {
        return new AdminController(orderService);
    }
}

@ContextHierarchy({
    @ContextConfiguration(
        name = "web",
        classes = AdminWebTestConfig.class
    )
})
class AdminControllerContextTest extends BaseOrderWebTest {
}
~~~

Vì tên "web" khớp với level ở lớp cha và inheritLocations mặc định là true, cấu hình admin được hợp nhất với cấu hình web kế thừa. Root level vẫn được kế thừa.

### 11.2. Thay cấu hình web cho một test cô lập

~~~java
@Configuration
class IsolatedWebTestConfig {
    @Bean
    IsolatedController isolatedController() {
        return new IsolatedController();
    }
}

@ContextHierarchy({
    @ContextConfiguration(
        name = "web",
        classes = IsolatedWebTestConfig.class,
        inheritLocations = false
    )
})
class IsolatedControllerTest extends BaseOrderWebTest {
}
~~~

Test này giữ root context từ lớp cha nhưng thay nguồn cấu hình web bằng IsolatedWebTestConfig. Nếu isolated web configuration vẫn cần MVC infrastructure hoặc các bean khác, chúng phải được khai báo hoặc import tường minh.

## 12. Những lỗi thường gặp

### Đổi tên level giữa lớp cha và lớp con

Lớp cha dùng "web", lớp con dùng "mvc" nhưng mong Spring ghép hai cấu hình vào cùng level. Hãy dùng cùng tên nếu muốn merge/override một level đã tồn tại.

### Dùng inheritLocations = false và vô tình bỏ mất cấu hình cần thiết

Thuộc tính này thay nguồn cấu hình được kế thừa tại level tương ứng. Nếu lớp con vẫn cần bean của lớp cha, hãy import hoặc khai báo lại một cách rõ ràng.

### Nghĩ rằng merge metadata sẽ tự giải quyết bean trùng tên

Hai configuration class cùng được nạp không có nghĩa bean cùng tên tự hợp nhất. Hãy kiểm tra bean definition overriding, @Primary, @Qualifier hoặc tách cấu hình.

### Nhầm context level name với bean name

Tên level phục vụ hierarchy metadata; bean name phục vụ BeanFactory. Thay một tên không tự thay tên còn lại.

### Đặt nhầm thứ tự parent và child

Context đầu tiên là parent, các context sau là child theo thứ tự khai báo. Đảo thứ tự có thể khiến bean visibility và dependency direction sai.

### Tạo hierarchy không cần thiết

Một ứng dụng không có root/web context tách biệt không nhất thiết cần @ContextHierarchy. Thêm level chỉ làm tăng số context phải khởi tạo và làm cấu hình khó hiểu.

### Dùng @DirtiesContext để né lỗi metadata

Cache eviction không sửa tên level hoặc quy tắc kế thừa. Hãy sửa nguồn cấu hình trước.

### Tạo nhiều context gần giống nhau không chủ đích

Khác biệt nhỏ về classes, profiles hoặc properties có thể tạo cache entry riêng. Hãy tái sử dụng cấu hình chung và chỉ tách context khi mục tiêu test thực sự khác.

## 13. Quy trình thiết kế context hierarchy

Khi xây dựng một nhóm test có kế thừa, hãy làm theo trình tự:

**Bước 1 – Xác định các ranh giới ứng dụng.** Phân biệt bean dùng chung, web-specific bean và module-specific bean.

**Bước 2 – Quyết định có cần nhiều context không.** Nếu một ApplicationContext là đủ, dùng @ContextConfiguration hoặc composed annotation tương ứng.

**Bước 3 – Vẽ thứ tự parent-child.** Tầng nào chứa service/repository? Tầng nào chứa controller và MVC infrastructure?

**Bước 4 – Đặt tên level ổn định.** Dùng tên rõ nghĩa như root, web hoặc adminWeb và nhất quán trong các lớp kế thừa.

**Bước 5 – Xác định cấu hình lớp cha.** Đưa vào base test những cấu hình thực sự dùng chung.

**Bước 6 – Chọn merge hay replace cho lớp con.** Dùng cùng tên và inheritLocations mặc định để bổ sung; dùng cùng tên với inheritLocations = false để thay nguồn cấu hình tại level đó.

**Bước 7 – Kiểm soát initializer và metadata khác.** Xem xét inheritInitializers, active profiles, test properties và bean override riêng biệt.

**Bước 8 – Kiểm tra bean visibility và xung đột.** Xác nhận child nhìn thấy parent, parent không phụ thuộc child và bean trùng tên/type được xử lý rõ ràng.

**Bước 9 – Quan sát context cache.** Tránh tạo cấu hình khác nhau không cần thiết và chỉ dùng @DirtiesContext khi context thực sự không thể tái sử dụng.

**Bước 10 – Kiểm tra đúng hành vi.** Không dừng ở việc context khởi động; gửi request hoặc gọi bean theo hành vi mà test cần chứng minh.

## 14. Bảng tham chiếu nhanh

| Nhu cầu | Cấu hình cần xem |
| --- | --- |
| Thêm class cấu hình vào test class con | @ContextConfiguration với inheritLocations mặc định |
| Thay nguồn classes/locations của lớp cha ở một context đơn | inheritLocations = false |
| Thêm initializer từ lớp con | initializers và inheritInitializers |
| Không kế thừa initializer của lớp cha | inheritInitializers = false |
| Khai báo nhiều context cha-con | @ContextHierarchy |
| Nhận diện level tương ứng giữa lớp cha và lớp con | @ContextConfiguration(name = "...") |
| Merge cấu hình vào một level đã có | Cùng name, inheritLocations mặc định |
| Replace cấu hình của một level đã có | Cùng name, inheritLocations = false |
| Chọn bean khi nhiều bean cùng type | @Primary hoặc @Qualifier |
| Thay một bean cho test | Cơ chế bean override hoặc test configuration |
| Loại context khỏi cache sau test | @DirtiesContext khi thực sự cần |

## Kết luận

Tên tầng context giúp Spring TestContext Framework nhận diện đúng level trong một hierarchy khi test class kế thừa hoặc bổ sung cấu hình. @ContextHierarchy mô tả các ApplicationContext theo thứ tự parent-child; @ContextConfiguration(name = "...") đặt tên ổn định cho từng level. Khi tên trùng nhau, cấu hình lớp con có thể được hợp nhất vào level tương ứng theo quy tắc kế thừa mặc định. Đặt inheritLocations = false cho phép thay nguồn classes/locations được kế thừa tại level đó.

Hãy phân biệt việc hợp nhất metadata cấu hình với bean definition overriding và dependency resolution. Việc hai configuration class cùng được nạp không tự quyết định bean nào thắng khi trùng tên hoặc cùng type. Thiết kế rõ tên level, hướng parent-child, chính sách merge/replace và cách chọn bean sẽ giúp context dễ dự đoán, tận dụng cache tốt hơn và làm cho test hierarchy dễ bảo trì.

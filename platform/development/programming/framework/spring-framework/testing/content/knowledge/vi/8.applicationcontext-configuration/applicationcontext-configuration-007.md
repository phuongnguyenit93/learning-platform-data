# Kế thừa cấu hình từ lớp cha

Trong một dự án Spring, nhiều integration test cần cùng một nhóm bean nền: datasource, repository, service dùng chung, cấu hình transaction hoặc các thành phần hạ tầng dành cho test. Nếu mỗi test class khai báo lại toàn bộ cấu hình, mã kiểm thử sẽ lặp và khó giữ nhất quán.

Spring TestContext Framework cho phép đặt cấu hình chung trên lớp test cha rồi để các lớp con kế thừa. Khi lớp con khai báo thêm cấu hình, framework có thể hợp nhất thông tin từ các lớp trong cây kế thừa. Nhờ đó, mỗi lớp con chỉ cần mô tả phần cấu hình riêng của kịch bản mà nó kiểm tra.

Cơ chế này có quy tắc rõ ràng: cấu hình có thể được kế thừa và bổ sung, hoặc được thay thế có chủ đích bằng các thuộc tính `inherit...` tương ứng. Hiểu cách merge giúp tránh nạp thiếu bean, vô tình giữ profile không mong muốn hoặc tạo nhiều ApplicationContext khác nhau.

## Vì sao nên đặt cấu hình chung ở lớp cha?

Giả sử nhiều test của tầng persistence đều cần:

- Một datasource dành cho test.
- Cấu hình transaction manager.
- Các bean repository và service nền.
- Một profile chung như `integration`.
- Các property dùng chung cho database hoặc dịch vụ giả lập.

Ta có thể tạo một lớp test cha trừu tượng chứa cấu hình nền:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = PersistenceTestConfig.class)
@ActiveProfiles("integration")
abstract class AbstractPersistenceTest {
}
~~~

Các test cụ thể kế thừa lớp cha:

~~~java
class CustomerRepositoryTest extends AbstractPersistenceTest {

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void findsCustomerByEmail() {
        // Kiểm thử repository.
    }
}
~~~

Test class con nhận cấu hình Spring từ lớp cha. Nếu nhiều test class cùng kế thừa một cấu hình đã hợp nhất tương đương, TestContext Framework có thể tái sử dụng ApplicationContext qua context cache.

Lớp cha thường được khai báo `abstract` để thể hiện đây là nền tảng dùng chung, không phải một kịch bản kiểm thử độc lập. Lớp cha có thể chứa fixture hoặc helper method dùng chung, nhưng nên giữ trách nhiệm ở mức nền tảng. Mỗi lớp con vẫn cần tự mô tả hành vi cụ thể mà nó kiểm tra.

## Spring Test hợp nhất cấu hình theo cây kế thừa

Khi một lớp con khai báo `@ContextConfiguration`, Spring TestContext Framework xem xét cấu hình của lớp đó cùng các lớp cha liên quan. Các thuộc tính kế thừa quyết định metadata nào được giữ lại và metadata nào được thay thế.

~~~mermaid
flowchart TD
    A["AbstractPersistenceTest"] --> B["Cấu hình nền: PersistenceTestConfig"]
    A --> C["Profile nền: integration"]
    D["CustomerRepositoryTest"] --> E["Cấu hình riêng: CustomerTestConfig"]
    D --> F["Profile riêng: customer"]
    B --> G["Cấu hình đã hợp nhất"]
    E --> G
    C --> H["Danh sách profile đã hợp nhất"]
    F --> H
    G --> I["ApplicationContext cho test"]
    H --> I
~~~

Với mặc định kế thừa, cấu hình của lớp cha được đưa vào trước, sau đó cấu hình khai báo ở lớp con được bổ sung. Cần phân biệt việc bổ sung cấu hình với việc tạo context cha/con: kế thừa `@ContextConfiguration` thông thường tạo một cấu hình đã hợp nhất cho context của test; nó không tự động tạo hai ApplicationContext theo quan hệ parent-child.

Các nhóm metadata phổ biến có quy tắc kế thừa riêng:

| Annotation / thuộc tính | Mặc định | Cách lớp con điều chỉnh |
|---|---|---|
| `@ContextConfiguration` – locations/classes | Kế thừa cấu hình lớp cha | `inheritLocations = false` để thay thế cấu hình kế thừa |
| `@ContextConfiguration` – initializers | Kế thừa initializer | `inheritInitializers = false` để không nhận initializer từ lớp cha |
| `@ActiveProfiles` | Hợp nhất profile lớp cha và lớp con | `inheritProfiles = false` để chỉ dùng profile của lớp con |
| `@TestPropertySource` – locations | Kế thừa resource locations | `inheritLocations = false` để bỏ locations từ lớp cha |
| `@TestPropertySource` – properties | Kế thừa inline properties | `inheritProperties = false` để bỏ inline properties từ lớp cha |

Không phải mọi annotation của test đều có cùng thuộc tính kế thừa. Cần xem hợp đồng của annotation cụ thể thay vì giả định rằng mọi metadata trên lớp cha đều được nối hoặc thay thế theo một quy tắc duy nhất.

## Kế thừa locations và classes của @ContextConfiguration

`@ContextConfiguration` cho phép khai báo resource locations, annotated classes hoặc cả hai tùy cách cấu hình. Thuộc tính `inheritLocations` mặc định là `true`. Khi lớp con khai báo cấu hình riêng, Spring hợp nhất cấu hình lớp cha với cấu hình lớp con.

### Bổ sung cấu hình của lớp con

Ví dụ lớp cha cung cấp bean nền, còn lớp con thêm cấu hình riêng cho Customer:

~~~java
@Configuration
class SharedTestConfig {

    @Bean
    Clock testClock() {
        return Clock.systemUTC();
    }
}

@Configuration
class CustomerTestConfig {

    @Bean
    CustomerPolicy customerPolicy() {
        return new CustomerPolicy();
    }
}

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SharedTestConfig.class)
abstract class AbstractServiceTest {
}

@ContextConfiguration(classes = CustomerTestConfig.class)
class CustomerServiceTest extends AbstractServiceTest {

    @Autowired
    Clock testClock;

    @Autowired
    CustomerPolicy customerPolicy;
}
~~~

Với `inheritLocations = true` mặc định, các annotated classes từ lớp cha và lớp con được hợp nhất để tạo context. Test có thể nhận cả bean nền `testClock` và bean riêng `customerPolicy`.

Tương tự, nếu lớp cha khai báo XML resource location và lớp con khai báo thêm location, framework có thể hợp nhất danh sách locations theo quy tắc kế thừa. Loader được chọn sẽ xử lý nguồn cấu hình đã hợp nhất.

### Thay thế cấu hình kế thừa

Đôi khi test class con cần một context hoàn toàn khác. Ví dụ, lớp cha dùng cấu hình database thật cho integration test, còn lớp con cần một context nhỏ chỉ chứa cấu hình giả lập. Khi đó, có thể đặt `inheritLocations = false`:

~~~java
@Configuration
class FastTestConfig {

    @Bean
    CustomerRepository customerRepository() {
        return new InMemoryCustomerRepository();
    }
}

@ContextConfiguration(
    classes = FastTestConfig.class,
    inheritLocations = false
)
class CustomerFastTest extends AbstractServiceTest {
    // Chỉ dùng FastTestConfig làm cấu hình context.
}
~~~

Thuộc tính này có tên là `inheritLocations`, nhưng trong mô hình cấu hình hiện đại nó điều khiển việc kế thừa cả resource locations lẫn annotated classes của `@ContextConfiguration`. Khi đặt `false`, các cấu hình được khai báo ở lớp cha không được đưa vào danh sách kế thừa cho lớp con.

Hãy dùng cách thay thế khi lớp con thật sự cần một bộ cấu hình độc lập. Nếu chỉ cần thêm một bean, nên bổ sung class cấu hình hoặc dùng `@Import` thay vì bỏ toàn bộ cấu hình nền.

## Kế thừa ContextInitializer

`@ContextConfiguration` cũng hỗ trợ `initializers` để khai báo các `ApplicationContextInitializer`. Initializer được gọi trong quá trình chuẩn bị context, trước khi context được refresh, và có thể điều chỉnh môi trường hoặc đăng ký cấu hình cần thiết.

Ví dụ:

~~~java
class SharedContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.getEnvironment()
            .getPropertySources()
            .addFirst(new MapPropertySource(
                "shared-test",
                Map.of("feature.audit.enabled", "false")
            ));
    }
}

class CustomerContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.getEnvironment()
            .getPropertySources()
            .addFirst(new MapPropertySource(
                "customer-test",
                Map.of("customer.region", "test-region")
            ));
    }
}

@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    classes = SharedTestConfig.class,
    initializers = SharedContextInitializer.class
)
abstract class AbstractInitializedTest {
}

@ContextConfiguration(
    classes = CustomerTestConfig.class,
    initializers = CustomerContextInitializer.class
)
class CustomerInitializedTest extends AbstractInitializedTest {
}
~~~

Mặc định `inheritInitializers = true`, vì vậy initializer từ lớp cha được kế thừa cùng initializer lớp con. Spring gọi initializer theo thứ tự đã được framework hợp nhất; initializer lớp cha được áp dụng trước initializer lớp con. Nếu cần thay thế danh sách initializer, đặt `inheritInitializers = false` ở lớp con.

Initializer có thể thay đổi property source hoặc tùy chỉnh context, nên thứ tự thực thi có ý nghĩa. Tránh để hai initializer cùng ghi đè một property mà không có lý do rõ ràng. Khi có thể, dùng `@TestPropertySource` hoặc `@DynamicPropertySource` cho cấu hình property thông thường để ý định dễ đọc hơn.

## Kế thừa profile với @ActiveProfiles

`@ActiveProfiles` cho phép kích hoạt một hoặc nhiều profile khi tạo ApplicationContext. Thuộc tính `inheritProfiles` mặc định là `true`, nghĩa là profile của lớp cha và lớp con được hợp nhất.

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SharedTestConfig.class)
@ActiveProfiles("integration")
abstract class AbstractIntegrationTest {
}

@ContextConfiguration(classes = CustomerTestConfig.class)
@ActiveProfiles("customer")
class CustomerIntegrationTest extends AbstractIntegrationTest {
}
~~~

Test con có thể chạy với cả profile `integration` và `customer`. Điều này hữu ích khi profile cha bật các cấu hình chung của môi trường tích hợp, còn profile con bật cấu hình đặc thù cho một nhóm chức năng.

Nếu lớp con cần profile riêng hoàn toàn, có thể đặt `inheritProfiles = false`:

~~~java
@ActiveProfiles(
    profiles = "isolated",
    inheritProfiles = false
)
class IsolatedCustomerTest extends AbstractIntegrationTest {
}
~~~

Khi đó, profile `integration` của lớp cha không được kế thừa vào test con. Hãy cẩn thận vì profile bị loại bỏ có thể chứa bean hoặc property mà cấu hình con vẫn cần. Profile là một phần của cấu hình context và ảnh hưởng đến việc chọn bean cũng như context cache.

## Kế thừa property source với @TestPropertySource

`@TestPropertySource` có hai nhóm thông tin: resource locations trỏ tới file property và inline properties được khai báo trực tiếp. Hai nhóm này có thuộc tính kế thừa riêng:

- `inheritLocations` mặc định là `true`.
- `inheritProperties` mặc định là `true`.

Ví dụ lớp cha khai báo property chung:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SharedTestConfig.class)
@TestPropertySource(properties = {
    "service.retry.max=3",
    "service.region=global-test"
})
abstract class AbstractPropertyTest {
}
~~~

Lớp con bổ sung property riêng:

~~~java
@TestPropertySource(properties = {
    "service.region=customer-test",
    "customer.feature.enabled=true"
})
class CustomerPropertyTest extends AbstractPropertyTest {
}
~~~

Khi kế thừa mặc định, các inline properties của lớp cha được kết hợp với properties của lớp con. Nếu cùng một key xuất hiện nhiều lần, cần lưu ý thứ tự ưu tiên property source: các khai báo của lớp con có độ ưu tiên cao hơn khai báo được kế thừa từ lớp cha, và inline properties có độ ưu tiên cao hơn resource property locations. Vì vậy, `service.region` có giá trị `customer-test` trong ví dụ.

Nếu chỉ muốn bỏ inline properties của lớp cha nhưng vẫn giữ resource locations, dùng:

~~~java
@TestPropertySource(
    properties = "customer.feature.enabled=true",
    inheritProperties = false
)
class CustomerWithoutBaseInlinePropertiesTest extends AbstractPropertyTest {
}
~~~

Nếu chỉ muốn thay thế resource locations, đặt `inheritLocations = false`. Hai thuộc tính điều khiển độc lập nên không cần loại bỏ cả hai nhóm khi chỉ muốn thay một nhóm.

`@DynamicPropertySource` là cơ chế khác để đăng ký property động, thường dùng với Testcontainers khi cổng hoặc endpoint chỉ biết lúc runtime. Khi kế thừa test class, phương thức static được framework phát hiện theo cơ chế của nó; nên giữ phương thức đăng ký property ở lớp cha nếu mọi lớp con dùng chung tài nguyên, và tránh khai báo nhiều phương thức cùng ghi đè một key mà không chủ đích.

## Kết hợp nhiều annotation trên cây kế thừa

Một lớp test cha có thể tập trung cấu hình nền, còn lớp con bổ sung từng nhóm metadata. Ví dụ:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    classes = SharedTestConfig.class,
    initializers = SharedContextInitializer.class
)
@ActiveProfiles("integration")
@TestPropertySource(properties = {
    "feature.audit.enabled=false",
    "service.retry.max=2"
})
abstract class AbstractIntegrationTest {
}

@ContextConfiguration(
    classes = BillingTestConfig.class,
    initializers = BillingContextInitializer.class
)
@ActiveProfiles("billing")
@TestPropertySource(properties = {
    "billing.currency=VND",
    "service.retry.max=4"
})
class BillingIntegrationTest extends AbstractIntegrationTest {

    @Autowired
    BillingService billingService;
}
~~~

Cấu hình của Billing test được hình thành từ metadata của cả hai lớp:

- Annotated classes: cấu hình chung và cấu hình Billing.
- Initializers: initializer chung và initializer Billing.
- Profiles: `integration` và `billing`.
- Inline properties: property chung và property Billing; giá trị `service.retry.max` ở lớp con ghi đè giá trị được kế thừa.
- Extension JUnit: `SpringExtension` được khai báo ở lớp cha và được áp dụng cho lớp con theo cơ chế tìm extension của JUnit.

Nếu lớp con muốn loại bỏ một phần metadata, hãy chọn đúng thuộc tính kế thừa tương ứng. Ví dụ, chỉ đặt `inheritProfiles = false` không loại bỏ cấu hình class; chỉ đặt `inheritLocations = false` không tự động xóa profile hoặc property source.

## Kế thừa cấu hình khác với context hierarchy

Đây là điểm dễ nhầm. Kế thừa `@ContextConfiguration` thông thường hợp nhất danh sách cấu hình của lớp cha và lớp con để nạp một ApplicationContext cho test. Nó không tự động tạo context cha và context con.

Nếu ứng dụng thật sự cần nhiều ApplicationContext có quan hệ parent-child, dùng `@ContextHierarchy`:

~~~java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextHierarchy({
    @ContextConfiguration(classes = RootTestConfig.class),
    @ContextConfiguration(classes = WebTestConfig.class)
})
class WebApplicationIntegrationTest {
    // RootTestConfig tạo context cha.
    // WebTestConfig tạo web context con.
}
~~~

Trong trường hợp này, mỗi cấp cấu hình trong hierarchy tương ứng với một context. TestContext Framework quản lý thứ tự tạo context và quan hệ parent-child. Có thể kết hợp hierarchy với kế thừa test class, nhưng cần hiểu hai cơ chế đang hoạt động: một cơ chế hợp nhất metadata theo cây kế thừa, cơ chế kia mô tả nhiều context theo tầng.

Không nên dùng `@ContextHierarchy` chỉ để chia cấu hình chung và cấu hình riêng. Nếu tất cả bean cần nằm trong cùng một ApplicationContext, kế thừa cấu hình thông thường đơn giản hơn.

## Kế thừa cấu hình trong nested test class

TestContext Framework còn có khái niệm cấu hình cho nested test class, tức class test lồng bên trong một class khác. Đây là quan hệ bao ngoài, không phải quan hệ superclass.

`@NestedTestConfiguration` quyết định nested test class kế thừa cấu hình từ enclosing class hay không. Chế độ mặc định là `INHERIT`; có thể đặt `OVERRIDE` để nested class không kế thừa cấu hình từ enclosing class theo cơ chế này.

~~~java
@SpringJUnitConfig(SharedTestConfig.class)
class CustomerTests {

    @Nested
    class ActiveCustomerTests {
        // Mặc định nhận cấu hình TestContext từ enclosing class.
    }
}
~~~

Đừng nhầm `@NestedTestConfiguration` với `inheritLocations` của `@ContextConfiguration`. Một cái điều khiển việc nested test class nhận metadata từ enclosing class; cái còn lại điều khiển việc lớp con kế thừa locations/classes trong cây superclass.

## Ảnh hưởng đến ApplicationContext cache

Spring Test sử dụng cache để tái sử dụng ApplicationContext khi các test có cấu hình đã hợp nhất tương đương. Cấu hình kế thừa ảnh hưởng trực tiếp đến cấu hình cuối cùng và do đó ảnh hưởng đến cache key.

Nếu hai test class cùng kế thừa một lớp cha và không bổ sung cấu hình khác nhau, chúng có thể chia sẻ context. Nếu một lớp con thêm profile, property, initializer hoặc annotated class riêng, cấu hình đã hợp nhất có thể khác và framework tạo một cache entry khác.

Một số hệ quả:

- Cấu hình chung ổn định giúp tăng khả năng tái sử dụng context.
- Mỗi biến thể profile/property không cần thiết có thể tạo thêm context.
- Dùng `@DirtiesContext` khiến context bị loại khỏi cache theo phạm vi chỉ định.
- Bean singleton trong context được tái sử dụng; test không nên để trạng thái mutable rò rỉ giữa các test.

Kế thừa cấu hình không có nghĩa mọi test con luôn dùng cùng một context. Context phụ thuộc vào cấu hình đã hợp nhất, loader, customizer và các yếu tố khác của cache key.

## Tổ chức lớp test cha dễ bảo trì

Một lớp test cha tốt nên chứa những cấu hình thật sự dùng chung cho các lớp con:

- Cấu hình datasource hoặc service hạ tầng của test.
- Profile chung của nhóm test.
- Property mặc định ổn định.
- Các helper method không giữ state mutable giữa test.
- Fixture factory tạo dữ liệu mới cho từng test.

Tránh đưa mọi cấu hình của toàn bộ dự án vào một superclass lớn. Khi một lớp con chỉ cần một phần nhỏ nhưng phải kế thừa quá nhiều bean, profile và property, cấu trúc test trở nên khó hiểu. Có thể tách nhiều base class theo năng lực, chẳng hạn `AbstractRepositoryTest`, `AbstractWebIntegrationTest` hoặc `AbstractMessagingTest`, rồi chọn đúng base class cho từng test.

Không nên dùng một superclass để truyền dữ liệu được tạo bởi test method của lớp cha sang test method của lớp con. Test class cha là nơi chia sẻ cấu hình và tiện ích; dữ liệu kiểm thử cần được chuẩn bị độc lập theo từng test method để tránh phụ thuộc thứ tự.

## Khi nào cần thay thế cấu hình của lớp cha?

| Nhu cầu của lớp con | Thuộc tính phù hợp | Kết quả |
|---|---|---|
| Thêm annotated class hoặc XML location | Giữ `inheritLocations = true` | Hợp nhất cấu hình cha và con |
| Chỉ dùng cấu hình context riêng | `inheritLocations = false` | Không kế thừa locations/classes từ cha |
| Thêm initializer đặc thù | Giữ `inheritInitializers = true` | Kế thừa và bổ sung initializer |
| Chỉ dùng initializer riêng | `inheritInitializers = false` | Bỏ initializer kế thừa |
| Thêm profile cho kịch bản con | Giữ `inheritProfiles = true` | Hợp nhất profile cha và con |
| Dùng profile hoàn toàn riêng | `inheritProfiles = false` | Chỉ dùng profile được khai báo ở lớp con |
| Bổ sung property cho test con | Giữ hai thuộc tính kế thừa của `@TestPropertySource` | Kế thừa resource và inline properties |
| Thay riêng inline properties | `inheritProperties = false` | Không nhận inline properties từ cha |
| Thay riêng file property | `inheritLocations = false` | Không nhận resource locations từ cha |

Đặt thuộc tính kế thừa ở đúng annotation trên lớp con. Không có một cờ chung để tắt toàn bộ kế thừa của mọi annotation cấu hình Spring Test.

## Những nhầm lẫn thường gặp

**Cho rằng lớp con luôn thay thế toàn bộ cấu hình của lớp cha.** Mặc định, `@ContextConfiguration` kế thừa và hợp nhất locations/classes. Muốn thay thế, phải đặt `inheritLocations = false`.

**Cho rằng chỉ cần tắt inheritLocations là mọi cấu hình cha biến mất.** Profile, initializer và property source có cờ kế thừa riêng. Cần điều chỉnh đúng annotation chứa metadata muốn thay thế.

**Cho rằng kế thừa cấu hình tạo context cha/con.** Kế thừa thông thường tạo một cấu hình đã hợp nhất. Muốn nhiều context theo quan hệ parent-child, dùng `@ContextHierarchy`.

**Cho rằng profile của lớp con luôn ghi đè profile của lớp cha.** Mặc định chúng được hợp nhất. Nếu muốn profile riêng, dùng `inheritProfiles = false`.

**Cho rằng mọi test con dùng chung một ApplicationContext.** Context cache phụ thuộc vào cấu hình đã hợp nhất. Khác profile, property hoặc class cấu hình có thể tạo context khác.

**Đặt quá nhiều trạng thái mutable trong superclass.** Các test có thể vô tình phụ thuộc vào dữ liệu hoặc trạng thái do test khác thay đổi. Hãy giữ superclass ở vai trò cấu hình nền và tạo fixture riêng cho mỗi test.

**Dùng context hierarchy thay cho cấu hình kế thừa.** Hai cơ chế giải quyết hai vấn đề khác nhau. Chỉ tạo nhiều context khi kiến trúc ứng dụng thực sự cần parent-child context.

## Cách kiểm tra cấu hình cuối cùng

Khi lớp con thiếu bean hoặc sử dụng nhầm property, hãy lần theo từng lớp trong hierarchy:

1. Đọc `@ContextConfiguration` trên superclass gần nhất và các superclass phía trên.
2. Đọc annotation trên lớp con và xác định `inheritLocations`, `inheritInitializers`.
3. Tổng hợp active profile, kiểm tra `inheritProfiles`.
4. Kiểm tra resource locations và inline properties, cùng hai cờ kế thừa của `@TestPropertySource`.
5. Kiểm tra các initializer và thứ tự áp dụng.
6. Xem test có dùng `@ContextHierarchy`, `@NestedTestConfiguration` hoặc bootstrapper tùy chỉnh không.
7. Kiểm tra context cache để xác định cấu hình cuối cùng có được tái sử dụng hay tạo context mới.

Có thể bật log phù hợp của Spring TestContext để quan sát quá trình tìm cấu hình, tạo context và cache. Khi cần kiểm tra property thực tế, có thể inject `Environment` vào test rồi đọc key cụ thể:

~~~java
@Autowired
Environment environment;

@Test
void usesCustomerSpecificRegion() {
    assertThat(environment.getProperty("service.region"))
        .isEqualTo("customer-test");
}
~~~

Việc kiểm tra cấu hình hiệu lực giúp phân biệt lỗi do annotation merge với lỗi do property source có độ ưu tiên khác. Khi thiếu bean, hãy kiểm tra class cấu hình được hợp nhất và component scan; không nên vội thêm một bean trùng lặp vào lớp con trước khi hiểu vì sao cấu hình cha không được nạp.

## Nguyên tắc ghi nhớ

Đặt cấu hình nền ổn định ở lớp test cha, để lớp con bổ sung cấu hình riêng theo mặc định. Dùng `inheritLocations` của `@ContextConfiguration` và `@TestPropertySource`, `inheritInitializers`, `inheritProfiles` và `inheritProperties` đúng nơi khi cần thay thế từng nhóm metadata. Kế thừa cấu hình thông thường tạo một ApplicationContext theo cấu hình đã hợp nhất; `@ContextHierarchy` mới mô tả nhiều context có quan hệ cha-con.

Khi tổ chức test theo cách này, cấu hình dùng chung được khai báo một lần, các lớp con thể hiện rõ nhu cầu riêng và TestContext Framework có thể tái sử dụng context khi cấu hình tương đương.

# TestContextBootstrapper, ContextLoader và SmartContextLoader

Spring TestContext Framework cần thực hiện hai việc trước khi một integration test có thể dùng Spring: xác định cách xây dựng môi trường kiểm thử, rồi nạp ApplicationContext theo cấu hình đã hợp nhất. Ba thành phần TestContextBootstrapper, ContextLoader và SmartContextLoader tham gia vào hai công việc đó ở những tầng khác nhau.

- **TestContextBootstrapper** chuẩn bị bộ khung TestContext: chọn cách khởi tạo TestContext, ContextLoader mặc định và danh sách TestExecutionListener.
- **ContextLoader** là hợp đồng nạp ApplicationContext từ cấu hình kiểm thử.
- **SmartContextLoader** mở rộng hợp đồng loader để hiểu cấu hình đã hợp nhất của Spring Test, bao gồm class cấu hình, active profile, initializer và các thuộc tính khác.

Hiểu rõ vai trò của từng thành phần giúp đọc được cách Spring tạo context, biết annotation nào đang quyết định hành vi, và chọn đúng extension point khi cần tùy biến.

## Vị trí của ba thành phần trong TestContext Framework

TestContext Framework không chỉ là một lệnh gọi trực tiếp đến `new AnnotationConfigApplicationContext(...)`. Nó có một quy trình khởi tạo để kết hợp metadata từ test class, cấu hình context, listener và cache.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["JUnit gọi SpringExtension"] --> B["TestContextManager"]
    B --> C["BootstrapUtils tìm TestContextBootstrapper"]
    C --> D["Bootstrapper xây dựng TestContext và listeners"]
    D --> E["TestContext cần ApplicationContext"]
    E --> F["CacheAwareContextLoaderDelegate"]
    F --> G["ContextLoader / SmartContextLoader"]
    G --> H["ApplicationContext"]
    H --> I["Test sử dụng bean và môi trường Spring"]
~~~

Các thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm | Câu hỏi nó trả lời |
|---|---|---|
| `TestContextManager` | Điều phối các callback của Spring Test trong lifecycle của test | Khi nào cần chuẩn bị test instance, chạy listener và thông báo kết thúc test? |
| `TestContextBootstrapper` | Tạo TestContext và cung cấp cấu hình nền cho framework | Test class này dùng bootstrap strategy nào? |
| `TestContext` | Giữ ngữ cảnh của test và cung cấp ApplicationContext khi cần | Test hiện tại thuộc class/method nào và context của nó là gì? |
| `ContextLoader` | Nạp ApplicationContext theo cấu hình đã chọn | Làm thế nào để tạo context? |
| `SmartContextLoader` | Loader hiểu cấu hình kiểm thử hợp nhất của Spring | Cấu hình class, profile, initializer và property được xử lý thế nào? |
| `CacheAwareContextLoaderDelegate` | Điều phối việc lấy context từ cache hoặc yêu cầu loader tạo mới | Context tương ứng đã có trong cache chưa? |
| `TestExecutionListener` | Tham gia các giai đoạn của vòng đời test | Cần thực hiện hành động nào trước hoặc sau một giai đoạn test? |

Bootstrapper và loader không thay thế nhau. Bootstrapper thiết lập cách TestContext Framework hoạt động; loader chịu trách nhiệm tạo ApplicationContext. Listener tham gia vào lifecycle, còn context cache được điều phối qua delegate.

## TestContextBootstrapper: thiết lập bộ khung kiểm thử

`TestContextBootstrapper` là SPI (Service Provider Interface) dùng để bootstrap Spring TestContext Framework cho một test class. Nó cung cấp những thành phần mà `TestContextManager` cần để quản lý test.

Một bootstrapper thường quyết định hoặc cung cấp:

- Cách tạo đối tượng `TestContext` gắn với test class.
- Danh sách `TestExecutionListener` sẽ được đăng ký.
- ContextLoader mặc định nếu test không chỉ định loader riêng.
- Cách kết hợp metadata từ các annotation cấu hình test.
- Các thông tin cấu hình đã hợp nhất để chuyển cho loader.

Spring tìm bootstrapper thông qua cơ chế của `BootstrapUtils`. Annotation `@BootstrapWith` cho phép chỉ định bootstrapper cho test class hoặc một annotation tổ hợp. Nếu không có lựa chọn tùy chỉnh, framework sử dụng bootstrapper mặc định phù hợp với loại test.

### Bootstrapper mặc định và bootstrapper chuyên biệt

Spring Framework cung cấp `DefaultTestContextBootstrapper` cho test thông thường. Với web test, framework có bootstrapper chuyên biệt như `WebTestContextBootstrapper` để làm việc với web application context và các thành phần liên quan.

Ví dụ, một test dùng cấu hình Java thông thường:

~~~java
@SpringJUnitConfig(BillingTestConfig.class)
class BillingServiceIntegrationTest {

    @Autowired
    BillingService billingService;

    @Test
    void calculatesInvoice() {
        // Kiểm tra hành vi với bean trong ApplicationContext.
    }
}
~~~

`@SpringJUnitConfig` là annotation kết hợp việc mở rộng JUnit Jupiter bằng `SpringExtension` và khai báo cấu hình context qua `@ContextConfiguration`. SpringExtension dùng TestContextManager; TestContextManager sử dụng bootstrapper để thiết lập TestContext.

Nếu test thuộc ứng dụng Spring Boot, `@SpringBootTest` sử dụng cơ chế bootstrap riêng của Spring Boot, tiêu biểu là `SpringBootTestContextBootstrapper`. Boot bổ sung cách khởi tạo ứng dụng qua SpringApplication và auto-configuration. Đây là phần mở rộng của Spring Boot trên nền TestContext Framework.

### Tùy chỉnh bootstrapper bằng @BootstrapWith

Khi một nhóm test cần chính sách bootstrap riêng, có thể chỉ định class triển khai `TestContextBootstrapper` qua `@BootstrapWith`:

~~~java
@BootstrapWith(ProjectTestContextBootstrapper.class)
@ContextConfiguration(classes = ProjectTestConfig.class)
class ProjectIntegrationTest {
    // ...
}
~~~

`ProjectTestContextBootstrapper` là bootstrapper do dự án cung cấp, thường được xây dựng bằng cách kế thừa một bootstrapper có sẵn và ghi đè những điểm mở rộng cần thiết. Nó có thể thay đổi listener mặc định, ContextLoader mặc định hoặc cách xây dựng cấu hình test.

Không nên tạo bootstrapper tùy chỉnh chỉ để thêm một bean hoặc bật một profile. Những nhu cầu cấu hình thông thường đã có annotation như `@ContextConfiguration`, `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource` và `@ContextHierarchy`. Bootstrapper phù hợp khi cần thay đổi chính sách bootstrap ở cấp framework hoặc chuẩn hóa cách nhiều test class được thiết lập.

## ContextLoader: hợp đồng nạp ApplicationContext

`ContextLoader` mô tả trách nhiệm nạp Spring `ApplicationContext` cho một test. Nó nhận thông tin vị trí cấu hình và tạo context để test có thể sử dụng bean.

Trong mô hình API cũ, loader làm việc với danh sách resource location. Các phương thức legacy của `ContextLoader` xử lý location theo test class và nạp context từ các location đó. Cách này phù hợp với cấu hình XML truyền thống nhưng chưa thể hiện đầy đủ các loại metadata mà TestContext Framework hiện đại cần quản lý.

Ví dụ một test dùng XML:

~~~java
@ContextConfiguration(locations = "/test-context.xml")
class LegacyXmlContextTest {
    // Spring nạp ApplicationContext từ resource XML.
}
~~~

Nếu không chỉ định loader, bootstrapper và cơ chế mặc định của Spring sẽ chọn loader phù hợp. Test thường chỉ cần khai báo resource hoặc class cấu hình; không cần tự gọi loader.

### ContextLoader không phải TestContextBootstrapper

Hai thành phần thường bị nhầm vì đều tham gia giai đoạn chuẩn bị context:

- Bootstrapper chọn và cung cấp cấu trúc bootstrap cho TestContext Framework.
- Loader đọc cấu hình đã được chọn và tạo ApplicationContext.

Ví dụ, một bootstrapper có thể chọn loader mặc định phù hợp cho nhóm test. Loader đó sau đó tạo context từ các class cấu hình hoặc resource location của từng test class.

Loader không chịu trách nhiệm điều phối `@BeforeEach`, `@AfterEach`, callback của listener hoặc thứ tự chạy phương thức JUnit. Những việc đó thuộc lifecycle do JUnit, SpringExtension, TestContextManager và TestExecutionListener phối hợp.

### Chỉ định loader cho một test

`@ContextConfiguration` có thuộc tính `loader` để chỉ định ContextLoader hoặc SmartContextLoader mà test muốn dùng:

~~~java
@ContextConfiguration(
    locations = "/billing-test-context.xml",
    loader = ProjectContextLoader.class
)
class BillingXmlIntegrationTest {
    // ...
}
~~~

`ProjectContextLoader` là implementation do dự án cung cấp. Nếu loader cần hiểu cấu hình hiện đại như annotated classes, active profiles, initializer hoặc property source, nên triển khai SPI `SmartContextLoader`. Loader legacy chỉ phù hợp với hợp đồng location đơn giản và có thể không hỗ trợ đầy đủ metadata mới.

Chỉ định loader là một quyết định về cơ chế nạp context. Nó không thay thế việc khai báo bean, profile hoặc property; các nội dung đó vẫn phải có trong cấu hình mà loader nhận được.

## SmartContextLoader: loader hiểu cấu hình hợp nhất

`SmartContextLoader` là phần mở rộng của `ContextLoader` để hỗ trợ mô hình cấu hình phong phú hơn. Nó làm việc với `ContextConfigurationAttributes` khi xử lý metadata cấu hình và `MergedContextConfiguration` khi nạp context cuối cùng.

Hai bước chính có ý nghĩa khác nhau:

1. **Xử lý cấu hình:** `processContextConfiguration(...)` cho phép loader xem metadata của `@ContextConfiguration`, suy ra cấu hình mặc định khi cần hoặc điều chỉnh thông tin cấu hình.
2. **Nạp context:** `loadContext(MergedContextConfiguration)` nhận cấu hình đã hợp nhất và tạo ApplicationContext.

`MergedContextConfiguration` chứa thông tin đã được TestContext Framework tổng hợp từ test class và các lớp cha hoặc annotation liên quan. Tùy loại test, cấu hình có thể bao gồm:

- Resource locations và annotated classes.
- Context initializer classes.
- Active profiles.
- Property source descriptors và property khai báo trực tiếp.
- Context customizers.
- ContextLoader được chọn.
- Parent context nếu dùng context hierarchy.
- Thông tin resource base path đối với web context.

Nhờ đó, loader không cần tự tìm và phân tích lại mọi annotation trên toàn bộ cây kế thừa. Nó nhận một đối tượng cấu hình đã được framework chuẩn bị để thực hiện việc nạp context nhất quán.

### DelegatingSmartContextLoader

Spring Framework cung cấp `DelegatingSmartContextLoader` làm loader thông minh mặc định cho nhiều test không phải web. Nó có thể ủy quyền cho loader phù hợp với kiểu cấu hình:

- `AnnotationConfigContextLoader` khi test khai báo cấu hình bằng class hoặc component configuration.
- `GenericXmlContextLoader` khi test khai báo resource XML.

Với web test, có loader ủy quyền tương ứng là `WebDelegatingSmartContextLoader`, làm việc với các loại web context loader như `AnnotationConfigWebContextLoader` và `GenericXmlWebContextLoader`.

Ví dụ cấu hình bằng Java:

~~~java
@Configuration
@ComponentScan(basePackageClasses = BillingService.class)
class BillingTestConfig {
    // Bean và cấu hình dành cho test.
}

@ContextConfiguration(classes = BillingTestConfig.class)
class BillingContextTest {
    @Autowired
    BillingService billingService;
}
~~~

Test chỉ khai báo class cấu hình. Smart loader nhận metadata đó và tạo context từ annotated configuration. Khi chuyển sang XML, test có thể khai báo `locations`; loader ủy quyền tương ứng xử lý resource XML.

Cơ chế ủy quyền giúp test dùng nhiều kiểu nguồn cấu hình mà không phải tự chọn implementation loader trong mọi trường hợp.

## Quan hệ giữa @ContextConfiguration và loader

`@ContextConfiguration` là nơi test mô tả nguồn cấu hình. Loader là thành phần thực hiện việc nạp nguồn cấu hình đó.

Một số dạng khai báo thường gặp:

~~~java
// Cấu hình Java
@ContextConfiguration(classes = BillingTestConfig.class)
class JavaConfigTest {
}

// Cấu hình XML
@ContextConfiguration(locations = "/billing-context.xml")
class XmlConfigTest {
}

// Chỉ định loader riêng
@ContextConfiguration(
    classes = BillingTestConfig.class,
    loader = ProjectSmartContextLoader.class
)
class CustomLoaderTest {
}
~~~

Các thuộc tính này có thể kết hợp với annotation khác:

- `@ActiveProfiles` kích hoạt profile.
- `@TestPropertySource` khai báo property cho test.
- `@DynamicPropertySource` đăng ký property được xác định lúc chạy.
- `@ContextHierarchy` mô tả quan hệ parent/child giữa các context.
- `@WebAppConfiguration` đánh dấu test cần web application context.

Spring tổng hợp các thông tin liên quan trước khi yêu cầu loader nạp context. Khi cấu hình kế thừa từ superclass hoặc annotation tổ hợp, quy tắc merge của TestContext Framework quyết định cấu hình cuối cùng. Loader làm việc với cấu hình đã hợp nhất đó.

### Context hierarchy

Một số ứng dụng có cấu trúc context cha và con, chẳng hạn context gốc chứa service/repository và web context con chứa controller hoặc web infrastructure. `@ContextHierarchy` mô tả cấu trúc này để TestContext Framework nạp các context theo quan hệ cha/con.

~~~java
@ContextHierarchy({
    @ContextConfiguration(classes = RootTestConfig.class),
    @ContextConfiguration(classes = WebTestConfig.class)
})
@WebAppConfiguration
class WebLayerIntegrationTest {
    // Kiểm thử trong web application context có parent context.
}
~~~

Loader cần nhận thông tin parent context trong cấu hình hợp nhất để tạo context con đúng quan hệ. Việc quản lý cache và quan hệ context được TestContext Framework điều phối; không nên tự tạo context con trong test method rồi kỳ vọng Spring tự quản lý vòng đời của nó.

## Bootstrapper, loader và context cache

Khởi tạo ApplicationContext có thể tốn thời gian. Spring Test sử dụng context cache để tái sử dụng context giữa các test có cấu hình tương đương.

Bootstrapper chuẩn bị cấu hình và loader cho TestContext. Khi test cần ApplicationContext, TestContext thông qua `CacheAwareContextLoaderDelegate` kiểm tra cache. Nếu đã có context phù hợp, framework có thể tái sử dụng; nếu chưa, delegate gọi loader để tạo context rồi lưu lại.

~~~mermaid
flowchart TD
    A["MergedContextConfiguration"] --> B["CacheAwareContextLoaderDelegate"]
    B --> C{"Context có trong cache?"}
    C -->|Có| D["Dùng ApplicationContext đã cache"]
    C -->|Không| E["Gọi SmartContextLoader"]
    E --> F["Tạo ApplicationContext"]
    F --> G["Lưu context vào cache"]
    G --> D
~~~

Cache key được hình thành từ cấu hình context đã hợp nhất và các yếu tố liên quan. Vì vậy, thay đổi cấu hình như class cấu hình, profile, property, initializer hoặc context customizer có thể khiến test sử dụng một context cache entry khác.

`@DirtiesContext` đánh dấu context đã bị thay đổi và không còn phù hợp để tái sử dụng theo phạm vi khai báo. Nó ảnh hưởng đến cache context; nó không thay thế việc dọn dữ liệu database hoặc cleanup các side effect ngoài context.

Nếu test liên tục tạo nhiều cấu hình gần giống nhau, số context được cache có thể tăng và suite chạy chậm. Hãy dùng cấu hình nhất quán khi có thể, đồng thời chỉ đánh dấu context dirty khi test thực sự làm thay đổi trạng thái context không thể khôi phục.

## Khi nào cần tùy chỉnh từng thành phần?

Chọn extension point theo phần trách nhiệm cần thay đổi:

| Nhu cầu | Thành phần nên xem xét | Lý do |
|---|---|---|
| Thay đổi cách nhóm test được bootstrap, listener mặc định hoặc chính sách cấu hình chung | `TestContextBootstrapper` | Nó thiết lập bộ khung TestContext |
| Dùng một cơ chế nạp ApplicationContext riêng | `ContextLoader` / `SmartContextLoader` | Nó tạo context từ cấu hình |
| Khai báo thêm bean, profile hoặc property cho một test | Annotation cấu hình hiện có | Đây là metadata cấu hình, chưa cần SPI tùy chỉnh |
| Thay đổi hành vi trước/sau các giai đoạn test | `TestExecutionListener` | Listener tham gia lifecycle của test |
| Thêm hành vi riêng cho JUnit Jupiter | JUnit Extension hoặc `SpringExtension` integration phù hợp | Đây là tầng thực thi test |
| Dùng Spring Boot auto-configuration | `@SpringBootTest` và cơ chế bootstrap/loader của Boot | Boot đã cung cấp tích hợp chuyên biệt |

Một custom `SmartContextLoader` chỉ nên xuất hiện khi dự án có nguồn cấu hình hoặc quy tắc nạp context đặc thù mà loader có sẵn không hỗ trợ. Một custom bootstrapper chỉ nên xuất hiện khi cần thay đổi cách framework chuẩn bị TestContext cho một nhóm test.

Không nên tự triển khai loader để thay thế một vài bean trong test. Hãy dùng `@TestConfiguration`, `@Import`, `@ContextConfiguration`, profile hoặc test property source. Các cơ chế đó thể hiện ý định rõ ràng và dễ bảo trì hơn.

## Quy trình truy tìm cách Spring tạo context

Khi một test nạp nhầm cấu hình, thiếu bean hoặc tạo nhiều ApplicationContext ngoài dự kiến, có thể lần theo quy trình sau:

1. Xác định test class và các annotation cấu hình: `@ContextConfiguration`, `@BootstrapWith`, `@WebAppConfiguration`, `@SpringBootTest` hoặc annotation tổ hợp.
2. Xác định bootstrapper được chọn. Nếu có `@BootstrapWith`, kiểm tra class được chỉ định; nếu không, xem bootstrapper mặc định hoặc bootstrapper chuyên biệt của loại test.
3. Xem bootstrapper cung cấp TestExecutionListener nào và ContextLoader mặc định nào.
4. Xem cấu hình cuối cùng đã hợp nhất: classes, locations, profiles, properties, initializer, customizer và parent context.
5. Xác định loader thực tế. Nếu dùng `DelegatingSmartContextLoader`, kiểm tra nó đang ủy quyền sang loader annotation hay XML.
6. Theo dõi context cache để biết context được tái sử dụng hay được tạo mới.
7. Nếu context tạo sai, kiểm tra loader và nguồn cấu hình; nếu context đúng nhưng test lifecycle sai, kiểm tra listener và TestContextManager.

Cách lần theo này giúp tách lỗi cấu hình context khỏi lỗi trong logic test. Ví dụ, thiếu bean có thể do component không nằm trong scan, profile không được kích hoạt hoặc custom loader bỏ qua annotated classes. Tạo context quá nhiều lần có thể do cấu hình hợp nhất khác nhau hoặc context bị đánh dấu dirty.

## Những nhầm lẫn thường gặp

**Cho rằng bootstrapper trực tiếp khởi tạo mọi bean.** Bootstrapper thiết lập TestContext và các thành phần framework. ContextLoader mới thực hiện việc nạp ApplicationContext.

**Cho rằng ContextLoader quản lý lifecycle của JUnit.** Loader không điều phối `@BeforeEach`, `@AfterEach` hoặc các callback test. TestContextManager và TestExecutionListener đảm nhiệm việc phối hợp lifecycle.

**Cho rằng SmartContextLoader là một bootstrapper khác.** SmartContextLoader là một SPI về nạp context. Nó được bootstrapper chọn hoặc cung cấp để tạo ApplicationContext.

**Cho rằng @ContextConfiguration luôn dùng một loader duy nhất cho mọi loại test.** Loader mặc định có thể khác theo test thường, web test hoặc cơ chế mở rộng như Spring Boot. Thuộc tính `loader` cũng cho phép chỉ định implementation riêng.

**Cho rằng custom loader là cách thông thường để thêm cấu hình.** Hầu hết trường hợp chỉ cần class cấu hình, profile, property source, initializer hoặc import. Tạo loader mới làm tăng trách nhiệm hạ tầng cần duy trì.

**Cho rằng context cache do loader tự quản lý.** Cache được điều phối qua `CacheAwareContextLoaderDelegate`; loader chịu trách nhiệm nạp context khi framework cần tạo mới.

## Cách ghi nhớ

TestContextBootstrapper trả lời câu hỏi “framework sẽ được thiết lập như thế nào cho test này?”. ContextLoader trả lời “làm thế nào để nạp ApplicationContext?”. SmartContextLoader trả lời câu hỏi đó với một cấu hình kiểm thử phong phú đã được Spring hợp nhất.

Trong phần lớn test thông thường, chỉ cần khai báo `@ContextConfiguration`, `@SpringJUnitConfig`, profile và property. Spring chọn bootstrapper và smart loader mặc định phù hợp. Chỉ mở rộng bootstrapper khi cần thay đổi chính sách khởi tạo TestContext ở cấp framework; chỉ mở rộng SmartContextLoader khi cần cơ chế nạp ApplicationContext đặc thù. Phân biệt đúng hai extension point giúp cấu hình test rõ ràng, giảm code hạ tầng tự viết và dễ lần theo nguyên nhân khi Spring tạo context không như mong đợi.

# Các thành phần tạo khóa context cache

Spring TestContext Framework lưu các `ApplicationContext` đã khởi tạo vào một cache dùng chung trong tiến trình test. Khi một test khác yêu cầu context có cấu hình tương đương, Spring có thể lấy lại context đang có thay vì khởi tạo lại toàn bộ bean.

Để quyết định hai yêu cầu có thể dùng chung context hay không, Spring tạo một **cache key** từ metadata cấu hình đã được hợp nhất. Vì vậy, việc hai test cùng chạy trên một test class hoặc cùng dùng một service không đủ để kết luận chúng sẽ dùng chung context. Những thuộc tính tạo nên cấu hình context mới là yếu tố quyết định.

Hiểu cache key giúp giải thích vì sao một thay đổi nhỏ như thêm profile, đổi property inline, thêm mock bean hoặc đổi resource base path có thể làm cache miss và tạo context mới.

## 1. Context cache hoạt động như thế nào?

Khi Spring Test chuẩn bị một test có tích hợp Spring, TestContext Framework đọc annotation và metadata trên test class, hợp nhất cấu hình được kế thừa, rồi tạo một mô tả cấu hình context. Mô tả đó được dùng để tìm context trong cache.

```text
Test class A ──┐
               ├── metadata cấu hình tương đương ──► cùng cache key
Test class B ──┘                                      │
                                                      ▼
                                            ApplicationContext đã cache

Test class C ───── metadata có khác biệt ─────────► cache key khác
                                                      │
                                                      ▼
                                            tạo ApplicationContext mới
```

Cache key được xây dựng từ đối tượng cấu hình đã hợp nhất, thường được biểu diễn qua `MergedContextConfiguration`. Các trường trong đối tượng này tham gia phép so sánh bằng `equals()` và `hashCode()`. Nếu key bằng nhau, Spring có thể tái sử dụng context tương ứng; nếu khác nhau, Spring cần tìm hoặc tạo một entry khác.

Điều này có nghĩa tên test class không tự nó là thành phần của key. Hai class test khác tên vẫn có thể dùng chung context nếu metadata context của chúng tương đương. Ngược lại, hai test nằm trong cùng một class vẫn có thể yêu cầu context khác nhau nếu chúng sử dụng các cấu hình lồng nhau hoặc cơ chế tùy chỉnh tạo ra metadata khác nhau.

## 2. Những trường chính tạo nên cache key

Trong Spring Framework TestContext, cache key dựa trên các thành phần cấu hình sau:

| Thành phần | Nguồn cấu hình thường gặp | Vì sao ảnh hưởng đến key |
|---|---|---|
| Resource locations | `@ContextConfiguration(locations = ...)` | Xác định file cấu hình hoặc resource cần nạp. |
| Configuration classes | `@ContextConfiguration(classes = ...)` | Xác định các class Java cấu hình hoặc component dùng để tạo context. |
| Context initializer classes | `@ContextConfiguration(initializers = ...)` | Xác định initializer được gọi trước khi context refresh. |
| Context customizers | Các `ContextCustomizerFactory`, ví dụ dynamic property hoặc bean override | Mang các tùy chỉnh bổ sung được áp dụng trong quá trình tạo context. |
| Context loader | `@ContextConfiguration(loader = ...)` | Xác định chiến lược nạp context. |
| Parent context | `@ContextHierarchy` | Xác định context cha trong cấu trúc phân cấp. |
| Active profiles | `@ActiveProfiles` | Xác định profile được bật khi tạo context. |
| Property source descriptors | `@TestPropertySource(locations = ...)` | Mô tả các file property source cần nạp. |
| Inline property source values | `@TestPropertySource(properties = ...)` | Bổ sung các giá trị property trực tiếp trong annotation. |
| Web resource base path | `@WebAppConfiguration` | Xác định thư mục gốc resource của web application context. |

Đây là các thành phần của metadata đã hợp nhất; một annotation cụ thể có thể đóng góp vào một hoặc nhiều trường. Các trường không được dùng trong loại test hiện tại thường mang giá trị mặc định hoặc rỗng.

### 2.1. Resource locations

Thuộc tính `locations` của `@ContextConfiguration` chỉ định resource cấu hình, chẳng hạn file XML:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = "classpath:/orders-test-context.xml")
class XmlConfiguredOrderTest {
}
```

Nếu test khác sử dụng file XML khác, metadata locations khác nhau và thường tạo cache key khác:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = "classpath:/billing-test-context.xml")
class BillingContextTest {
}
```

Resource location có thể là classpath resource hoặc đường dẫn resource phù hợp với loader đang dùng. Spring so sánh cấu hình resource đã hợp nhất, vì vậy thay đổi file được tham chiếu có thể dẫn đến context khác. Việc chỉ sửa nội dung của cùng một file trong khi tên resource và các metadata khác giữ nguyên không tự tạo một key mới; nếu context cũ đã cache, test có thể tiếp tục nhận context đã được tạo trước đó.

### 2.2. Configuration classes

Khi dùng Java configuration, các class được chỉ định qua thuộc tính `classes` tham gia key:

```java
@SpringJUnitConfig(classes = {
        OrderServiceTestConfiguration.class,
        RepositoryTestConfiguration.class
})
class OrderServiceContextTest {
}
```

Một test khác chỉ dùng một cấu hình:

```java
@SpringJUnitConfig(classes = OrderServiceTestConfiguration.class)
class OrderServiceOnlyTest {
}
```

Hai cấu hình trên không tương đương chỉ vì cùng chứa `OrderServiceTestConfiguration`. Test thứ nhất yêu cầu thêm `RepositoryTestConfiguration` nên object graph có thể khác. Spring cần phân biệt metadata class cấu hình để tránh đưa test vào context thiếu bean hoặc chứa bean không phù hợp.

Các class nested configuration, cấu hình được import và cấu hình được phát hiện bằng component scan cũng ảnh hưởng đến nội dung context. Tuy nhiên, cần phân biệt class được ghi trực tiếp trong `classes` với class được nạp gián tiếp: key chứa metadata cấu hình đầu vào và các customizer liên quan; Spring không đơn giản dùng tên mọi bean runtime làm một danh sách độc lập để so sánh.

### 2.3. Context initializer classes

`ApplicationContextInitializer` được gọi trước khi context refresh. Initializer có thể bổ sung property source, đăng ký bean definition hoặc điều chỉnh environment. Vì initializer có thể làm thay đổi context được tạo, danh sách class initializer tham gia cache key.

```java
class TestEnvironmentInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        Map<String, Object> values = Map.of("feature.enabled", "true");
        context.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource("testOverrides", values)
        );
    }
}

@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = FeatureConfiguration.class,
        initializers = TestEnvironmentInitializer.class
)
class FeatureContextTest {
}
```

Nếu một test dùng initializer khác, hoặc thêm initializer vào danh sách, metadata initializer thay đổi và context có thể không được dùng chung. Nếu initializer có trạng thái động nhưng class initializer vẫn giống nhau, Spring không tự suy ra rằng mọi giá trị runtime bên trong initializer là một key field riêng. Khi dữ liệu động thay đổi, cần cân nhắc cơ chế quản lý vòng đời context thay vì trông chờ cache tự nhận biết mọi thay đổi.

### 2.4. Context customizers

`ContextCustomizer` là một trong những thành phần quan trọng nhất để hiểu các annotation kiểm thử hiện đại. Spring Test có thể phát hiện các `ContextCustomizerFactory` và dùng chúng tạo các tùy chỉnh được áp dụng khi context được dựng. Tập customizer này tham gia cache key.

Các trường hợp thường gặp:

- `@DynamicPropertySource` đăng ký property động vào environment của test.
- Các annotation thay thế bean bằng mock hoặc spy, chẳng hạn `@MockitoBean` và `@MockitoSpyBean` trong các phiên bản Spring Framework hỗ trợ chúng.
- Các tùy chỉnh kiểm thử do Spring Boot hoặc thư viện test khác cung cấp.
- Các context customizer do dự án tự viết và đăng ký qua cơ chế factory phù hợp.

Ví dụ test có mock bean:

```java
@SpringJUnitConfig(classes = OrderServiceTestConfiguration.class)
class OrderServiceWithMockGatewayTest {

    @MockitoBean
    NotificationGateway notificationGateway;

    @Autowired
    OrderService orderService;
}
```

Việc khai báo bean override có thể làm context customizer khác với test không có override. Nếu các test dùng tập mock/spy khác nhau, chúng có thể tạo key khác nhau và không chia sẻ context. API cụ thể và quy tắc override phụ thuộc phiên bản Spring Framework; dự án cũ có thể dùng cơ chế mock bean do Spring Boot Test cung cấp.

Không nên coi mọi annotation trên test class đều trực tiếp là một trường của key. Một số annotation được chuyển thành context customizer; một số annotation chỉ tác động đến việc thực thi test sau khi context đã được tạo. Điều quyết định là metadata nào được đưa vào `MergedContextConfiguration`.

### 2.5. Context loader

Context loader chịu trách nhiệm tạo và nạp `ApplicationContext` từ cấu hình đã hợp nhất. Loader mặc định thường đủ cho Java configuration hoặc XML configuration thông dụng.

Có thể chỉ định loader tùy chỉnh:

```java
@ContextConfiguration(
        classes = OrderTestConfiguration.class,
        loader = CustomOrderContextLoader.class
)
class CustomLoaderTest {
}
```

Khi loader class khác nhau, Spring phải xem đó là cấu hình context khác vì cách tạo context có thể khác nhau. Chỉ nên dùng custom loader khi cách nạp context thực sự cần tùy biến; một loader tự viết không cần thiết sẽ làm cấu hình khó chia sẻ và khó bảo trì.

### 2.6. Parent context

Với `@ContextHierarchy`, một ứng dụng có thể có context cha và context con. Ví dụ context cha chứa service và repository, còn context con chứa cấu hình web:

```java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
        @ContextConfiguration(
                name = "root",
                classes = RootTestConfiguration.class
        ),
        @ContextConfiguration(
                name = "web",
                classes = WebTestConfiguration.class
        )
})
class WebLayerContextTest {
}
```

Metadata parent context tham gia key của context con. Nếu cấu hình context cha khác nhau, context con tương ứng cũng không thể mặc nhiên xem là cùng context. Điều này bảo đảm context web không được tái sử dụng với parent chứa bean hoặc dependency khác.

### 2.7. Active profiles

Profile quyết định các bean có điều kiện `@Profile` nào được đăng ký. Danh sách profile được kích hoạt bằng `@ActiveProfiles` tham gia cache key:

```java
@SpringJUnitConfig(classes = PaymentConfiguration.class)
@ActiveProfiles("test")
class TestPaymentContext {
}

@SpringJUnitConfig(classes = PaymentConfiguration.class)
@ActiveProfiles("integration")
class IntegrationPaymentContext {
}
```

Hai test yêu cầu profile khác nhau nên context có thể chứa các bean khác nhau và phải được phân biệt. Nếu test dùng cùng tập profile, metadata profile có thể cho phép dùng chung context, miễn các trường key khác cũng tương đương.

Nếu dự án có resolver profile tùy chỉnh, giá trị profile được resolve cho test cũng cần được hiểu trong bối cảnh metadata đã hợp nhất. Đừng giả định profile của shell, IDE hoặc môi trường chạy tự động thay thế `@ActiveProfiles`; Spring Test có quy tắc riêng để xác định active profiles.

### 2.8. Property source descriptors và inline properties

`@TestPropertySource` có thể nạp property từ file:

```java
@SpringJUnitConfig(classes = FeatureConfiguration.class)
@TestPropertySource(locations = "classpath:/feature-test.properties")
class FeatureFilePropertyTest {
}
```

Hoặc khai báo trực tiếp:

```java
@SpringJUnitConfig(classes = FeatureConfiguration.class)
@TestPropertySource(properties = {
        "feature.enabled=true",
        "orders.max-items=25"
})
class FeatureInlinePropertyTest {
}
```

Các property source descriptor và các giá trị inline đều tham gia key. Vì vậy, đổi đường dẫn file, thêm hoặc đổi property inline có thể tạo cache key khác. Hai test dùng cùng Java configuration nhưng một test bật `feature.enabled` và test kia tắt nó không nên dùng chung context.

Property được cung cấp bởi các nguồn khác, ví dụ system property hoặc environment variable, không nhất thiết được biểu diễn giống hệt `@TestPropertySource`. Nếu test cần một giá trị riêng ổn định, hãy khai báo nguồn đó một cách tường minh trong cấu hình test.

### 2.9. Web resource base path

Với test web dùng `@WebAppConfiguration`, thuộc tính resource base path xác định gốc resource của web application context:

```java
@WebAppConfiguration("src/test/webapp")
@SpringJUnitConfig(classes = WebMvcTestConfiguration.class)
class WebApplicationContextTest {
}
```

Resource base path tham gia key. Hai test dùng các thư mục web resource khác nhau có thể nhận context khác nhau, ngay cả khi các class cấu hình Java giống nhau.

Nếu không chỉ định đường dẫn, Spring sử dụng giá trị mặc định của `@WebAppConfiguration`. Khi test không dùng web application context, thành phần resource base path thường không có ý nghĩa trong key.

## 3. Những thay đổi nào tạo cache hit hoặc cache miss?

Một cách thực tế để hiểu key là so sánh hai test và xác định metadata có khác nhau hay không.

| Thay đổi | Tác động thường gặp |
|---|---|
| Chỉ đổi tên test class, giữ nguyên toàn bộ cấu hình context | Có thể dùng chung context. |
| Dùng cùng class cấu hình và cùng profile | Có thể cache hit nếu các trường khác tương đương. |
| Thêm hoặc bỏ một class trong `classes` | Cache key khác. |
| Đổi resource location | Cache key khác. |
| Thêm một initializer class | Cache key khác. |
| Đổi active profile | Cache key khác. |
| Đổi property inline hoặc file property source | Cache key khác. |
| Đổi context loader | Cache key khác. |
| Đổi parent context trong hierarchy | Cache key của context con khác. |
| Đổi web resource base path | Cache key khác. |
| Thêm hoặc đổi bean override/context customizer | Có thể tạo cache key khác. |
| Chỉ đổi assertion hoặc dữ liệu local của một test method | Thông thường không đổi cache key. |

Ví dụ hai test có thể chia sẻ context:

```java
@SpringJUnitConfig(classes = SharedTestConfiguration.class)
class CustomerServiceTest {
    @Autowired
    CustomerService customerService;
}

@SpringJUnitConfig(classes = SharedTestConfiguration.class)
class CustomerRepositoryIntegrationTest {
    @Autowired
    CustomerRepository customerRepository;
}
```

Nếu cả hai test có cùng metadata context và không có customizer khác biệt, Spring có thể dùng lại một context. Test class khác nhau không bắt buộc phải tạo context mới.

Ngược lại, một khác biệt nhỏ ở property cũng đủ tách cache:

```java
@SpringJUnitConfig(classes = SharedTestConfiguration.class)
@TestPropertySource(properties = "feature.mode=compact")
class CompactModeTest {
}

@SpringJUnitConfig(classes = SharedTestConfiguration.class)
@TestPropertySource(properties = "feature.mode=full")
class FullModeTest {
}
```

Hai test có cùng class cấu hình nhưng yêu cầu environment khác nhau. Chúng cần context riêng để bean được tạo với property phù hợp.

## 4. @DynamicPropertySource và giá trị động

`@DynamicPropertySource` cho phép đăng ký property có giá trị được cung cấp bởi method static, thường dùng khi test khởi động một tài nguyên bên ngoài như database container hoặc message broker container:

```java
abstract class BaseDatabaseIntegrationTest {

    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16");

    static {
        database.start();
    }

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }
}
```

Các method `@DynamicPropertySource` được phản ánh qua context customizer trong cache key. Tuy nhiên, cần chú ý rằng key không phải lúc nào cũng phản ánh mọi giá trị trả về tại runtime của supplier. Hai lớp con có thể kế thừa cùng một method dynamic property nhưng supplier lại đọc tài nguyên khác nhau.

Ví dụ, nếu cùng một method được kế thừa nhưng tài nguyên bên ngoài thay đổi giữa các lớp con, Spring có thể xem metadata customizer là tương đương và tái sử dụng context cũ. Khi dynamic property thực sự thay đổi giữa các lớp con, tài liệu Spring khuyến nghị dùng `@DirtiesContext` ở lớp cha hoặc điều chỉnh cách tổ chức test để context được tạo lại đúng lúc.

Điểm cần ghi nhớ: khai báo method dynamic property là một phần của metadata; thay đổi giá trị mà supplier trả về không đồng nghĩa chắc chắn với việc cache key tự đổi.

## 5. Bean override và mock ảnh hưởng cache key

Trong context test, các annotation mock/spy bean có thể thay đổi bean definition được đưa vào context. Vì thế, chúng thường được xử lý qua context customizer và ảnh hưởng cache key.

Ví dụ với API Spring Framework mới:

```java
@SpringJUnitConfig(classes = OrderServiceTestConfiguration.class)
class OrderServiceWithMockRepositoryTest {

    @MockitoBean
    OrderRepository orderRepository;
}
```

Một test khác có thể thay bean khác:

```java
@SpringJUnitConfig(classes = OrderServiceTestConfiguration.class)
class OrderServiceWithMockGatewayTest {

    @MockitoBean
    NotificationGateway notificationGateway;
}
```

Hai test có thể có các context customizer khác nhau vì tập bean được override không giống nhau. Khi số lượng tổ hợp mock/spy tăng, số cache key cũng có thể tăng theo và làm giảm tỷ lệ cache hit.

Để tránh phân mảnh cache không cần thiết:

- Dùng chung một cấu hình test khi các test thật sự cần cùng object graph.
- Tránh khai báo mock bean khác nhau ở từng class nếu có thể kiểm tra bằng mock thủ công ngoài context.
- Chỉ thay bean trong context khi test cần xác nhận tích hợp giữa bean Spring với collaborator được thay thế.
- Gom các test có cùng bộ override vào cùng cấu hình khi cách tổ chức đó vẫn rõ ràng.

Tên annotation và khả năng override bean thay đổi theo phiên bản. Với các dự án Spring Boot cũ, có thể gặp `@MockBean`; ở Spring Framework mới, ưu tiên API thuộc Spring Test như `@MockitoBean` và `@MockitoSpyBean` khi phiên bản hỗ trợ.

## 6. Kế thừa cấu hình và tác động đến cache key

TestContext Framework hợp nhất cấu hình từ lớp cha và lớp con theo quy tắc kế thừa của các annotation Spring Test. Vì vậy, khi so sánh cache key, cần nhìn vào cấu hình đã hợp nhất chứ không chỉ annotation khai báo ngay trên test class.

```java
@SpringJUnitConfig(classes = SharedServiceTestConfiguration.class)
abstract class BaseServiceTest {
}

class CreateOrderTest extends BaseServiceTest {
}

class CancelOrderTest extends BaseServiceTest {
}
```

Hai lớp con không bổ sung cấu hình khác có thể dùng chung metadata được kế thừa từ lớp cha. Nếu một lớp con bổ sung class cấu hình, profile, property source hoặc customizer, key có thể khác.

Các thuộc tính kế thừa như `inheritLocations` và `inheritInitializers` điều khiển việc cấu hình từ lớp cha có được gộp vào lớp con hay không. Khi thay đổi quy tắc kế thừa, metadata cuối cùng thay đổi và có thể tạo key mới.

Với nested test class, Spring còn có quy tắc `@NestedTestConfiguration` để quyết định annotation test context có được kế thừa hay không. Nếu test nested cần context khác, hãy khai báo rõ ràng thay vì giả định rằng mọi nested class đều có key riêng hoặc đều chia sẻ key.

## 7. Context hierarchy và cache

Với ứng dụng web phân tầng, có thể tạo root context và web context con. Context con tham chiếu parent trong metadata. Điều này có hai hệ quả:

1. Nếu root context tương đương, các test có thể tái sử dụng phần context cha.
2. Nếu parent context khác, key của context con cũng khác vì parent là một phần của cấu hình.

Ví dụ:

```java
@ExtendWith(SpringExtension.class)
@ContextHierarchy({
        @ContextConfiguration(
                name = "root",
                classes = RootConfiguration.class
        ),
        @ContextConfiguration(
                name = "dispatcher",
                classes = DispatcherConfiguration.class
        )
})
class DispatcherContextTest {
}
```

Khi dùng hierarchy, `@DirtiesContext` có thể áp dụng cho cấp hierarchy cụ thể bằng thuộc tính `hierarchyMode`. Nếu đánh dấu dirty một context cha, các context con phụ thuộc vào nó cũng có thể cần bị loại khỏi cache. Chọn chế độ phù hợp với phạm vi thay đổi để không loại bỏ nhiều context hơn cần thiết.

## 8. @DirtiesContext có phải là một thành phần của cache key?

`@DirtiesContext` thường bị nhầm là một trường cấu hình của key. Vai trò chính của annotation này là yêu cầu Spring loại context đã dùng khỏi cache ở một thời điểm xác định, ví dụ sau method hoặc sau class.

```java
@SpringJUnitConfig(classes = MutableStateConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MutatesSharedContextTest {
}
```

Khi context bị đánh dấu dirty, Spring đóng và loại entry tương ứng theo quy tắc hierarchy đã chọn. Lần test sau có cùng cache key vẫn có thể phải tạo context mới vì entry cũ đã bị loại.

Vì vậy:

- Cache key trả lời câu hỏi: “Test đang yêu cầu loại context cấu hình nào?”
- `@DirtiesContext` trả lời câu hỏi: “Context đã dùng có còn được phép tái sử dụng không?”

Nếu chỉ cần xóa dữ liệu trong repository hoặc reset một bean có trạng thái, hãy dùng cơ chế dọn dữ liệu phù hợp. Không nên dùng `@DirtiesContext` để xử lý mọi thay đổi trạng thái nhỏ vì việc tạo lại context có thể tốn thời gian đáng kể.

## 9. Cache size, LRU và vòng đời context

Context cache mặc định có giới hạn kích thước. Trong Spring TestContext Framework, giới hạn mặc định thường là 32 context. Khi cache đầy, Spring dùng chính sách least-recently-used (LRU): entry ít được sử dụng gần đây nhất có thể bị loại để nhường chỗ cho context mới.

Có thể điều chỉnh giới hạn bằng thuộc tính:

```text
spring.test.context.cache.maxSize=64
```

Thuộc tính có thể được cung cấp qua system property hoặc cơ chế cấu hình property của Spring phù hợp với cách chạy test. Tăng cache size có thể giảm việc tạo lại context khi suite có nhiều cấu hình khác nhau, nhưng cũng làm tăng lượng bộ nhớ mà các context được giữ lại có thể sử dụng.

Khi context bị loại do LRU hoặc `@DirtiesContext`, Spring đóng context để giải phóng tài nguyên. Các bean có callback hủy, connection pool hoặc tài nguyên được quản lý có thể được đóng theo vòng đời context.

Cache là cache tĩnh trong tiến trình test. Vì vậy:

- Các test chạy trong cùng JVM có thể chia sẻ context.
- Các fork JVM riêng biệt có cache riêng và không chia sẻ context đã khởi tạo.
- Chạy từng test riêng trong IDE có thể không cho thấy cùng mức cache hit như khi chạy cả suite trong một tiến trình.
- Thứ tự thực thi test có thể ảnh hưởng việc entry bị LRU eviction, dù không làm thay đổi cache key.

## 10. Quan sát cache hit và cache miss

Khi cần hiểu vì sao test khởi tạo context nhiều lần, hãy bật log DEBUG cho cache:

```text
logging.level.org.springframework.test.context.cache=DEBUG
```

Hoặc cấu hình logger tương ứng trong hệ thống logging đang dùng. Spring Test có thể ghi nhận số lần cache hit, cache miss, kích thước cache và thống kê liên quan. Các thông tin này giúp phân biệt:

- Key mới xuất hiện lần đầu và cần tạo context.
- Key đã có entry nên được tái sử dụng.
- Entry cũ đã bị loại hoặc eviction nên context phải được tạo lại.

Khi đọc log, hãy đối chiếu test class với metadata cấu hình đã hợp nhất: classes, locations, profiles, properties, initializer, customizer, loader, parent và resource base path. Không nên kết luận chỉ dựa vào tên test class.

## 11. Cách tổ chức test để tận dụng context cache

Muốn cache có hiệu quả, cần làm cho những test có cùng nhu cầu thực sự dùng cùng metadata:

1. Tạo các class Java configuration dùng chung cho nhóm test có cùng object graph.
2. Đặt active profiles nhất quán trong nhóm test cần chia sẻ context.
3. Dùng cùng property source và cùng giá trị inline nếu các test cần cùng môi trường.
4. Tránh tạo nhiều biến thể bean override không cần thiết.
5. Tái sử dụng initializer và context customizer khi mục đích cấu hình giống nhau.
6. Dùng cùng resource base path cho các test cùng web application context.
7. Chỉ dùng `@DirtiesContext` khi context thực sự không thể tái sử dụng.

Không nên ép các test dùng chung context nếu chúng cần môi trường khác nhau. Ví dụ test cho profile `test` và profile `integration` có thể cần các bean khác nhau; tách context là hành vi đúng. Mục tiêu là tránh khác biệt vô tình, không phải tối đa hóa cache hit bằng mọi giá.

## 12. Những nguyên nhân thường làm cache key khác nhau

### Thêm property riêng cho từng test class

Hai class có cùng `classes` nhưng khai báo các giá trị `@TestPropertySource` khác nhau sẽ tạo metadata property khác nhau. Nếu test không cần môi trường riêng, hãy gom property chung vào cấu hình dùng chung.

### Active profile không đồng nhất

Một test dùng `test`, test khác dùng `local` có thể tạo các bean graph khác nhau. Hãy khai báo profile có chủ đích và thống nhất trong nhóm test.

### Khai báo mock bean khác nhau

Các context customizer dùng để override bean có thể khác khi test khai báo mock/spy khác nhau. Nếu không cần thay bean trong context, mock collaborator thủ công trong unit test sẽ tránh phải tạo một context mới chỉ vì mock.

### Mỗi test dùng một class cấu hình riêng dù nội dung giống nhau

Hai class cấu hình có tên và danh tính class khác nhau vẫn là hai metadata class khác nhau. Nếu nội dung cấu hình thực tế giống hệt, hãy cân nhắc tái sử dụng cùng một class cấu hình thay vì sao chép thành nhiều class.

### Dynamic property thay đổi nhưng cache key không phản ánh giá trị

Nếu một supplier dynamic property thay đổi kết quả nhưng customizer vẫn tương đương, context cũ có thể được dùng lại. Hãy thiết kế vòng đời tài nguyên và context rõ ràng, dùng `@DirtiesContext` khi phù hợp.

### Context hierarchy không nhất quán

Test có cùng cấu hình web nhưng parent khác nhau không thể dùng chung context con. Hãy tái sử dụng cấu hình root khi các test thực sự dùng chung tầng nền.

### Resource base path khác nhau

Hai test web dùng các thư mục resource khác nhau có thể yêu cầu context riêng. Thống nhất base path nếu các test cần cùng tập resource.

## 13. Cách phân tích một trường hợp cache miss

Giả sử hai test đều dùng `OrderTestConfiguration` nhưng log cho thấy Spring tạo context hai lần. Có thể phân tích theo thứ tự:

| Bước | Câu hỏi cần trả lời |
|---|---|
| 1 | Hai test có cùng danh sách `classes` và `locations` không? |
| 2 | Các `ApplicationContextInitializer` có giống nhau không? |
| 3 | Có `@DynamicPropertySource` hoặc context customizer nào khác nhau không? |
| 4 | Tập `@MockitoBean`, `@MockitoSpyBean` hoặc bean override có giống nhau không? |
| 5 | Active profiles có giống nhau không? |
| 6 | `@TestPropertySource` có cùng file và inline properties không? |
| 7 | Context loader và parent context có tương đương không? |
| 8 | Nếu là web context, resource base path có giống nhau không? |
| 9 | Context cũ có bị `@DirtiesContext` hoặc LRU eviction loại khỏi cache không? |
| 10 | Hai test có chạy trong cùng JVM hay đang ở các fork/process khác nhau? |

Việc lần lượt đối chiếu metadata giúp tìm ra nguyên nhân cụ thể thay vì chỉ tăng cache size hoặc loại bỏ annotation một cách thử-sai.

## 14. Tổng kết các thành phần của key

Cache key của Spring TestContext phản ánh cấu hình dùng để tạo `ApplicationContext`: resource locations, configuration classes, initializer classes, context customizers, context loader, parent context, active profiles, property source descriptors, inline properties và web resource base path.

Những khác biệt ở các trường này có thể tạo cache key khác và làm Spring tạo context riêng. Ngược lại, hai test class khác tên vẫn có thể chia sẻ context khi metadata đã hợp nhất tương đương và entry vẫn còn trong cache.

Khi tối ưu thời gian chạy test, hãy quan sát cache hit/miss, chuẩn hóa cấu hình dùng chung và chỉ tạo context riêng khi test thực sự cần một môi trường khác. Cách đó vừa giữ đúng tính cô lập của test, vừa tận dụng được cơ chế tái sử dụng context của Spring TestContext Framework.

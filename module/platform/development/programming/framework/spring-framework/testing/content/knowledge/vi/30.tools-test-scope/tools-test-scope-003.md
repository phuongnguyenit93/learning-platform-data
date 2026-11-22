# Test slice của Spring Boot khác với @ContextConfiguration

Khi viết test cho ứng dụng Spring Boot, hai cách cấu hình thường được nhắc đến là test slice như `@WebMvcTest`, `@DataJpaTest` và annotation `@ContextConfiguration` của Spring TestContext Framework. Chúng đều có thể tạo một Spring application context cho test, nhưng giải quyết hai bài toán khác nhau.

**Test slice xác định phạm vi thành phần và auto-configuration cần nạp cho một lớp của ứng dụng.** Ví dụ, `@WebMvcTest` tập trung vào Spring MVC, còn `@DataJpaTest` tập trung vào JPA repository và entity.

**`@ContextConfiguration` xác định nguồn cấu hình dùng để tạo application context.** Nó cho Spring biết cần nạp các Java configuration class, XML resource, context initializer hoặc context loader nào. Bản thân annotation này không tự tạo quy tắc lọc component và không tự kích hoạt một Boot test slice.

Vì vậy, test slice và `@ContextConfiguration` không phải hai annotation thay thế trực tiếp cho nhau. Một bên chọn phạm vi kiểm thử; bên kia khai báo nguồn cấu hình của context.

## 1. Test slice là gì?

Spring Boot cung cấp các annotation kiểm thử theo từng lát cắt của ứng dụng. Mỗi slice nạp những thành phần phù hợp với một tầng, đồng thời loại bớt các bean không liên quan để test khởi động nhanh và tập trung hơn.

Ví dụ, một ứng dụng có thể gồm các tầng:

```text
HTTP request
    |
    v
Controller / Spring MVC
    |
    v
Service / business logic
    |
    v
Repository / JPA
    |
    v
Database
```

Khi chỉ kiểm tra controller, test thường không cần tạo database và toàn bộ service thật. `@WebMvcTest` nạp hạ tầng MVC và controller được chọn, còn các phụ thuộc nghiệp vụ có thể được thay bằng mock. Khi chỉ kiểm tra JPA repository, `@DataJpaTest` nạp entity, repository và cấu hình persistence cần thiết.

Test slice thường có các đặc điểm:

- Dùng Spring TestContext Framework để quản lý application context và lifecycle của test.
- Nạp một nhóm auto-configuration phù hợp với tầng đang kiểm tra.
- Dùng bộ lọc component để giới hạn loại bean được phát hiện.
- Không khởi tạo toàn bộ ứng dụng như `@SpringBootTest`.
- Có thể bổ sung bean hoặc cấu hình cần thiết bằng `@Import`, `@TestConfiguration` hoặc cơ chế mock bean.

Các slice phổ biến:

| Annotation | Phạm vi chính | Ví dụ thành phần được kiểm tra |
| --- | --- | --- |
| `@WebMvcTest` | Spring MVC | Controller, mapping, converter, validation, controller advice |
| `@WebFluxTest` | Spring WebFlux | Reactive controller và hạ tầng WebFlux |
| `@DataJpaTest` | JPA | Entity, repository, mapping và truy vấn JPA |
| `@JdbcTest` | JDBC | JDBC component và thao tác với database |
| `@JsonTest` | JSON serialization | Jackson/Gson/Jsonb mapper và serializer |
| `@RestClientTest` | REST client | Thành phần gọi HTTP service và mock server hỗ trợ |
| `@DataMongoTest` | MongoDB | Mongo mapping và repository |

Danh sách cụ thể tùy phiên bản Spring Boot và các module đang có trên classpath. Có thể kiểm tra tài liệu của phiên bản Boot dự án đang sử dụng để biết các slice được hỗ trợ.

## 2. @ContextConfiguration là gì?

`@ContextConfiguration` thuộc Spring TestContext Framework, nằm trong package:

```java
org.springframework.test.context.ContextConfiguration
```

Annotation này chỉ định metadata để Spring tạo application context cho test. Những thuộc tính thường dùng gồm:

- `classes`: các Java configuration class hoặc component class được dùng làm nguồn cấu hình.
- `locations`: đường dẫn resource cấu hình, thường là XML.
- `initializers`: các `ApplicationContextInitializer` chạy trong quá trình chuẩn bị context.
- `loader`: context loader tùy chỉnh nếu cần.
- `inheritLocations` và `inheritInitializers`: điều khiển việc kế thừa cấu hình từ test class cha.
- `name`: tên context configuration trong một số trường hợp cần quản lý hierarchy.

Ví dụ khai báo cấu hình Java:

```java
@Configuration
public class PricingTestConfig {

    @Bean
    DiscountPolicy discountPolicy() {
        return new FixedDiscountPolicy(0.10);
    }

    @Bean
    PricingService pricingService(DiscountPolicy discountPolicy) {
        return new PricingService(discountPolicy);
    }
}
```

Test sử dụng `@ContextConfiguration`:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = PricingTestConfig.class)
class PricingServiceTest {

    @Autowired
    private PricingService pricingService;

    @Test
    void appliesConfiguredDiscount() {
        BigDecimal result = pricingService.calculate(
                new BigDecimal("100.00"));

        assertThat(result).isEqualByComparingTo("90.00");
    }
}
```

`SpringExtension` tích hợp JUnit Jupiter với Spring TestContext Framework. `@ContextConfiguration` chỉ định lớp cấu hình được dùng để tạo context, sau đó Spring inject `PricingService` vào test.

Trong ví dụ này, test không cần Spring Boot test slice. Nó dùng một Spring context được định nghĩa trực tiếp bằng Java configuration.

### Dùng XML làm nguồn cấu hình

`@ContextConfiguration` cũng có thể trỏ đến XML resource:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = "classpath:/test-context.xml")
class LegacyServiceTest {

    @Autowired
    private LegacyService legacyService;
}
```

Cách này hữu ích với ứng dụng Spring cũ hoặc khi test cần xác nhận một cấu hình XML cụ thể. `@ContextConfiguration` không yêu cầu dự án phải dùng Spring Boot.

## 3. So sánh hai khái niệm

| Tiêu chí | Test slice của Spring Boot | `@ContextConfiguration` |
| --- | --- | --- |
| Mục đích | Tạo test context tập trung vào một tầng | Khai báo nguồn cấu hình của test context |
| Phạm vi bean | Được giới hạn theo loại slice và bộ lọc của Boot | Phụ thuộc các class/resource được khai báo và cấu hình chúng import/scan |
| Auto-configuration | Nạp nhóm auto-configuration phù hợp với slice | Không tự kích hoạt Boot slice auto-configuration |
| Component scanning | Có bộ lọc riêng cho từng slice | Theo cấu hình component scan được khai báo |
| Ví dụ | `@WebMvcTest`, `@DataJpaTest`, `@JsonTest` | `@ContextConfiguration(classes = TestConfig.class)` |
| Có cần Spring Boot không? | Có, đây là các annotation kiểm thử của Boot | Không, thuộc Spring TestContext Framework |
| Có thể kết hợp không? | Có thể bổ sung nguồn cấu hình hoặc bean khi cần | Có thể xuất hiện cùng cấu hình test Boot nếu dùng đúng bootstrapper |

Điểm khác biệt quan trọng nhất: `@ContextConfiguration` trả lời câu hỏi “nạp cấu hình nào?”, còn test slice trả lời “đang kiểm tra tầng nào và Boot cần chuẩn bị những gì cho tầng đó?”.

## 4. Ví dụ: kiểm thử controller bằng @WebMvcTest

Giả sử controller phụ thuộc vào một service:

```java
public interface OrderService {
    OrderResponse findById(long id);
}

@RestController
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/orders/{id}")
    public OrderResponse find(@PathVariable long id) {
        return orderService.findById(id);
    }
}
```

Test slice:

```java
@WebMvcTest(OrderController.class)
class OrderControllerWebMvcTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsOrderAsJson() throws Exception {
        given(orderService.findById(42L))
                .willReturn(new OrderResponse(42L, "READY"));

        mockMvc.perform(get("/orders/{id}", 42))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.status").value("READY"));
    }
}
```

`@WebMvcTest(OrderController.class)` tập trung vào controller được chỉ định và hạ tầng Spring MVC. `OrderService` không phải bean MVC mặc định được slice này tự nạp, vì vậy test cung cấp một mock bean bằng `@MockitoBean`.

`@MockitoBean` thuộc Spring Framework 6.2 trở lên. Với các phiên bản Spring Boot cũ hơn chưa có annotation này, dự án thường dùng `@MockBean` của Spring Boot Test. Hãy dùng annotation phù hợp với phiên bản dependency đang quản lý.

Test này kiểm tra controller nhận request, bind path variable, gọi service và serialize kết quả. Nó không kiểm tra implementation thật của service hoặc database.

### Thêm controller advice hoặc cấu hình web

Nếu controller dùng `@RestControllerAdvice`, converter hoặc cấu hình web riêng, có thể đưa các thành phần cần thiết vào slice bằng `@Import`:

```java
@WebMvcTest(OrderController.class)
@Import({OrderExceptionHandler.class, ApiWebConfiguration.class})
class OrderControllerWebMvcTest {
    // MockMvc test.
}
```

`@Import` bổ sung các bean vào context đang được slice cấu hình. Đây thường là cách rõ ràng để thêm cấu hình test hoặc production configuration cần thiết mà vẫn giữ phạm vi của `@WebMvcTest`.

## 5. Ví dụ: kiểm thử repository bằng @DataJpaTest

Với tầng JPA, có thể dùng:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void findsOrderByStatus() {
        orderRepository.save(new Order("READY"));
        orderRepository.save(new Order("CANCELLED"));

        List<Order> result = orderRepository.findByStatus("READY");

        assertThat(result)
                .extracting(Order::getStatus)
                .containsExactly("READY");
    }
}
```

`@DataJpaTest` nạp các thành phần JPA cần thiết, phát hiện entity và Spring Data repository. Cấu hình mặc định thường dùng database nhúng nếu có trên test classpath và chạy test trong transaction được rollback sau mỗi method.

Nếu muốn dùng database đã cấu hình thay vì database nhúng, có thể dùng `@AutoConfigureTestDatabase(replace = Replace.NONE)` cùng datasource test phù hợp. Với database đặc thù production, có thể kết hợp Testcontainers.

Nếu viết `@ContextConfiguration(classes = OrderRepositoryTestConfig.class)` cho test repository, chính lớp cấu hình đó phải cung cấp hoặc import các thành phần cần thiết như entity manager factory, transaction manager, repository scanning và datasource. `@DataJpaTest` chuẩn bị phần lớn các cấu hình đó theo quy ước Boot, vì vậy thường ngắn gọn hơn cho mục tiêu kiểm thử JPA.

## 6. @ContextConfiguration không tự tạo Boot test slice

Một test chỉ dùng:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class SomeSpringTest {
}
```

đang yêu cầu Spring Test nạp `TestConfig`. Nó không tự có các hành vi riêng của `@WebMvcTest`, `@DataJpaTest` hay `@JsonTest`.

Ví dụ, nếu `TestConfig` chỉ khai báo một controller bean, điều đó không tự đảm bảo đã có đầy đủ:

- `DispatcherServlet` và các `HandlerMapping` cần thiết.
- Message converter cho JSON.
- Validation infrastructure.
- View resolver.
- Các interceptor hoặc controller advice cần thiết.
- Cấu hình auto-configuration của Spring Boot.

Những thành phần đó cần được cấu hình/import rõ ràng hoặc được một slice/Boot test annotation chuẩn bị.

Tương tự, `@ContextConfiguration` không tự tạo database nhúng, không tự scan JPA entity và repository, và không tự cấu hình `TestEntityManager`. Những việc đó thuộc cấu hình JPA test slice hoặc configuration do dự án tự viết.

## 7. Kết hợp test slice với cấu hình bổ sung

Test slice có thể cần thêm bean đặc thù cho test hoặc cấu hình production không được slice tự phát hiện. Spring Boot hỗ trợ các cách bổ sung sau:

### Dùng @Import

```java
@WebMvcTest(OrderController.class)
@Import(OrderWebConfiguration.class)
class OrderControllerTest {
}
```

`@Import` thích hợp khi cần đưa một hoặc vài configuration class, component hoặc bean cụ thể vào context.

### Dùng @TestConfiguration

```java
@TestConfiguration
class OrderTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }
}
```

Import cấu hình test:

```java
@WebMvcTest(OrderController.class)
@Import(OrderTestConfiguration.class)
class OrderControllerTest {
}
```

`@TestConfiguration` đánh dấu cấu hình bổ sung dành cho test. Với cấu hình lồng trong test class, Boot có quy tắc riêng để không tự động đưa nó vào component scan production thông thường; dùng `@Import` giúp ý định thêm cấu hình vào test context rõ ràng.

### Dùng @ContextConfiguration khi thực sự cần chỉ định nguồn context

Có thể kết hợp metadata cấu hình của Spring Test với các test annotation phù hợp, nhưng cần hiểu bootstrapper đang được dùng. Test slice Boot có bootstrapper và type filter riêng. Nếu mục đích chỉ là bổ sung bean vào slice, `@Import` hoặc `@TestConfiguration` thường rõ ràng hơn việc tự khai báo lại toàn bộ `@ContextConfiguration`.

Nếu khai báo `@ContextConfiguration(classes = ...)` trên test dùng Boot slice, hãy chắc chắn rằng danh sách class đó không vô tình thay thế hoặc làm mất cấu hình ứng dụng mà slice cần. Khi cần chọn nguồn cấu hình cho toàn bộ ứng dụng Boot, `@SpringBootTest(classes = ...)` thường diễn đạt ý định rõ hơn.

## 8. Phân biệt với @SpringBootTest

`@SpringBootTest` là annotation kiểm thử của Spring Boot dùng để tạo context theo cơ chế khởi động ứng dụng Boot. Phạm vi thường rộng hơn test slice.

| Annotation | Phạm vi | Khi nên dùng |
| --- | --- | --- |
| `@WebMvcTest` | MVC slice | Kiểm tra controller và web infrastructure |
| `@DataJpaTest` | JPA slice | Kiểm tra repository, entity và persistence |
| `@JsonTest` | JSON slice | Kiểm tra serialization/deserialization |
| `@SpringBootTest` | Toàn bộ application context theo cấu hình Boot | Kiểm tra tích hợp nhiều tầng |
| `@ContextConfiguration` | Nguồn cấu hình cho Spring Test context | Tạo context Java/XML tùy chỉnh, thường không cần toàn bộ Boot |

`@SpringBootTest` có thể kết hợp với `@AutoConfigureMockMvc` để kiểm tra MVC trong toàn bộ application context mà không mở cổng HTTP. Nếu cần server thật, có thể chọn `webEnvironment = RANDOM_PORT`.

`@ContextConfiguration` có thể dùng trong nhiều loại Spring Test, nhưng không phải một biến thể của `@SpringBootTest`. Nếu muốn Spring Boot khởi động context theo quy ước của ứng dụng, dùng annotation Boot phù hợp thay vì kỳ vọng `@ContextConfiguration` tự tìm và chạy toàn bộ Boot configuration.

## 9. WebApplicationContext và @WebAppConfiguration

Trong Spring Test thuần, nếu test cần `WebApplicationContext`, có thể kết hợp `@ContextConfiguration` với `@WebAppConfiguration`:

```java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = WebMvcTestConfig.class)
class WebApplicationContextTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    @Test
    void createsWebApplicationContext() {
        assertThat(webApplicationContext.getServletContext()).isNotNull();
    }
}
```

`@WebAppConfiguration` yêu cầu Spring Test tạo môi trường web với `MockServletContext`. `@ContextConfiguration` cung cấp nguồn cấu hình cho context. Hai annotation có vai trò bổ sung nhau.

Điều này vẫn không tương đương với `@WebMvcTest`: `@WebAppConfiguration` tạo web application context, nhưng không tự áp dụng bộ lọc và auto-configuration dành riêng cho MVC slice của Spring Boot. Cần cấu hình MVC phù hợp trong `WebMvcTestConfig` hoặc dùng Boot slice nếu mục tiêu là kiểm thử MVC theo quy ước Boot.

## 10. Context caching và ảnh hưởng đến test suite

Spring TestContext Framework có thể cache application context giữa các test class có cấu hình tương đương. Cache key có thể chịu ảnh hưởng bởi các nguồn cấu hình, active profiles, property sources, context customizers, context loader và các metadata khác.

Điều này áp dụng cho cả test slice và test dùng `@ContextConfiguration`:

- Hai test có cấu hình tương đương có thể dùng lại context để giảm thời gian khởi động.
- Hai test có cấu hình khác nhau có thể tạo các context riêng.
- `@DirtiesContext` đánh dấu context cần được loại khỏi cache hoặc đóng theo phạm vi khai báo.
- Thay đổi cấu hình hoặc mock bean có thể khiến test dùng một context cache key khác.

Không nên giả định mọi test dùng cùng annotation đều chia sẻ cùng một context. Ví dụ hai `@WebMvcTest` chọn controller khác nhau hoặc dùng cấu hình bổ sung khác nhau có thể tạo cache entry khác nhau.

Với test slice, context thường nhỏ hơn và ít phụ thuộc hơn, nhưng vẫn có bean singleton dùng chung trong context đó. Với `@ContextConfiguration`, nếu nhiều test dùng cùng configuration class và metadata tương đương, context cũng có thể được tái sử dụng. Tránh thay đổi mutable singleton state giữa các test nếu không có cơ chế reset phù hợp.

## 11. Các annotation bổ trợ thường dùng

`@ContextConfiguration` và test slice có thể đi cùng các annotation hỗ trợ cấu hình môi trường test:

| Annotation | Mục đích |
| --- | --- |
| `@ActiveProfiles` | Chọn Spring profile cho test context |
| `@TestPropertySource` | Khai báo properties bổ sung hoặc ghi đè trong test |
| `@DynamicPropertySource` | Đăng ký property động, thường dùng với Testcontainers |
| `@Import` | Thêm configuration hoặc bean cụ thể |
| `@TestConfiguration` | Định nghĩa cấu hình dành riêng cho test |
| `@DirtiesContext` | Đánh dấu context cần được làm mới/loại khỏi cache |
| `@WebAppConfiguration` | Yêu cầu WebApplicationContext với Servlet context mô phỏng |

Các annotation này không làm mất vai trò của test slice. Ví dụ `@ActiveProfiles("test")` có thể dùng với `@DataJpaTest` để chọn profile test; `@DynamicPropertySource` có thể cung cấp URL database container cho JPA slice.

## 12. Cách chọn trong từng tình huống

| Nhu cầu | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Kiểm tra controller và mapping HTTP | `@WebMvcTest` | Nạp MVC slice, không cần toàn bộ ứng dụng |
| Kiểm tra JPA repository và entity mapping | `@DataJpaTest` | Nạp JPA infrastructure và repository |
| Kiểm tra JSON serializer | `@JsonTest` | Nạp JSON test infrastructure |
| Kiểm tra REST client | `@RestClientTest` | Chuẩn bị client test và mock server |
| Kiểm tra một service với vài bean Java tự định nghĩa | `@ContextConfiguration` | Chỉ định context nhỏ theo cấu hình của test |
| Kiểm tra ứng dụng Spring thuần dùng XML | `@ContextConfiguration(locations = ...)` | Nạp đúng XML resource |
| Kiểm tra nhiều tầng của ứng dụng Boot cùng nhau | `@SpringBootTest` | Nạp application context rộng |
| Bổ sung advice hoặc converter vào MVC slice | `@Import` trên slice | Giữ nguyên slice và thêm bean cần thiết |
| Tạo bean hỗ trợ riêng cho một slice | `@TestConfiguration` kết hợp `@Import` | Cấu hình test tách biệt, dễ đọc |

Một quy trình chọn nhanh:

1. Xác định tầng cần kiểm tra: MVC, JPA, JSON, REST client hay toàn ứng dụng.
2. Nếu có test slice phù hợp, bắt đầu bằng slice đó.
3. Thêm dependency còn thiếu bằng mock bean hoặc `@Import`/`@TestConfiguration`.
4. Nếu cần một context Spring tùy chỉnh và không cần Boot slice, dùng `@ContextConfiguration`.
5. Nếu cần khởi động nhiều tầng theo cấu hình Boot, dùng `@SpringBootTest`.
6. Chỉ dùng `@ContextConfiguration` cùng annotation Boot khi có lý do cụ thể về nguồn context và đã hiểu cách bootstrapper của annotation Boot ghép cấu hình.

## 13. Các lỗi nhầm lẫn thường gặp

### Nghĩ rằng @ContextConfiguration tự động bật auto-configuration

`@ContextConfiguration` chỉ chỉ định nguồn context. Nếu test cần Boot auto-configuration, hãy dùng `@SpringBootTest`, test slice Boot hoặc khai báo cơ chế auto-configuration thích hợp trong cấu hình tùy chỉnh.

### Dùng @WebMvcTest nhưng mong đợi service thật được tự động nạp

MVC slice tập trung vào web layer và thường loại service/repository khỏi component scan. Hãy mock service hoặc import cấu hình rất cụ thể nếu mục tiêu test thực sự cần bean đó.

### Dùng @ContextConfiguration cho một test MVC nhưng quên cấu hình MVC

`@WebAppConfiguration` tạo WebApplicationContext và MockServletContext; nó không tự đăng ký toàn bộ Spring MVC infrastructure. Cần cấu hình MVC rõ ràng hoặc dùng `@WebMvcTest`.

### Dùng @SpringBootTest cho mọi test nhỏ

Full application context thường tốn thời gian và kéo theo database hoặc dịch vụ ngoài. Nếu chỉ cần controller hoặc repository, slice thường tập trung và nhanh hơn.

### Thêm @ContextConfiguration vào slice chỉ để bổ sung một bean

Nếu chỉ cần một configuration class hoặc một bean test, `@Import` thường thể hiện ý định rõ hơn và ít nguy cơ thay đổi nguồn context mà Boot slice đang sử dụng.

### Nhầm slice với một mock test thuần

Test slice vẫn tạo Spring application context và chạy các thành phần thật trong phạm vi slice. Ví dụ `@DataJpaTest` thực sự khởi tạo JPA repository và database test; `@WebMvcTest` chạy Spring MVC infrastructure. Các dependency ngoài phạm vi thường được mock hoặc bổ sung có chủ đích.

## 14. Kết luận

Test slice của Spring Boot như `@WebMvcTest`, `@DataJpaTest` và `@JsonTest` giúp kiểm tra một tầng với nhóm auto-configuration và component filter phù hợp. `@ContextConfiguration` là annotation nền tảng của Spring TestContext Framework, dùng để chỉ định Java configuration, XML resource, initializer hoặc loader tạo application context.

Hãy chọn test slice khi muốn kiểm tra một tầng theo quy ước Spring Boot. Dùng `@ContextConfiguration` khi cần một Spring context được định nghĩa trực tiếp và kiểm soát nguồn cấu hình. Khi slice cần thêm bean, ưu tiên `@Import` hoặc `@TestConfiguration`; khi cần toàn bộ ứng dụng Boot, dùng `@SpringBootTest`. Hiểu đúng vai trò của từng annotation giúp test có phạm vi rõ ràng, khởi động vừa đủ và phản ánh chính xác tầng đang được kiểm tra.
